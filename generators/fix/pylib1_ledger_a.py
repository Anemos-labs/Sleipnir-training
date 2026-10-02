"""Python libraries, theme time/money/scheduling (batch ledger-a): bank reconciliation."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# ledgermatch: reconcile bank statement lines with ledger entries in four passes
# ======================================================================================================================

LM_README = dd('''
    # ledgermatch

    Bank reconciliation for a small accounting tool. A **line** is `Line(id, date, amount, ref)`: an integer `id`
    (unique on its side), a `datetime.date`, an `int` amount in cents (negative for money going out) and a free-text
    reference. Bank lines come from the statement, ledger lines from the books.

    ## Helpers (`ledgermatch/normalize.py`)

    * `normalize_ref(text)`: the text upper-cased with everything but `A-Z` and `0-9` removed.
    * `days_apart(a, b)`: the absolute number of days between two dates.
    * `batch_key(ref)`: the reference stripped and upper-cased; without a `-` it is `""` (no batch), otherwise
      everything before the **last** `-`, stripped (`"payrun-07-a"` gives `"PAYRUN-07"`).

    ## Matching (`ledgermatch/match.py`)

    `match(bank, ledger)` pairs bank lines with ledger lines. Duplicate ids on one side are a `ValueError`. Both sides
    are first ordered by `(date, id)`. There are four passes, each one over all remaining bank lines in that order;
    a line matched in a pass is out of the later ones.

    1. **exact**: equal amounts, equal normalized references that are not empty, dates at most 5 days apart.
    2. **contained**: equal amounts, dates at most 10 days apart, the shorter normalized reference is at least 4
       characters long and is contained in the other one.
    3. **loose**: equal amounts and dates at most 3 days apart, but only when the pair is unambiguous: among the
       lines still unmatched at that moment, the bank line has exactly one such ledger partner and that ledger line
       has exactly one such bank partner.
    4. **batch**: a bank line whose amount equals the sum of **two or more** still unmatched ledger lines that share
       the same non-empty `batch_key` and are each at most 7 days from the bank line's date. When several keys
       qualify the alphabetically first wins; all lines of the group are matched to the bank line.

    In the exact and contained passes a bank line takes the qualifying ledger line with the fewest days apart, ties to
    the lower id.

    The result is `Result(matches, unmatched_bank, unmatched_ledger)`: `matches` is a list of `(bank_id, ledger_ids)`
    sorted by bank id with `ledger_ids` a sorted tuple; the two unmatched lists are sorted lists of ids.

    ## Report (`ledgermatch/report.py`)

    * `summarize(result, bank, ledger)` returns a dict: `matched` (number of matches), `matched_amount` (sum of the
      matched bank amounts), `bank_only` and `ledger_only` (counts of unmatched lines), `bank_only_amount`,
      `ledger_only_amount` (their sums) and `difference` (all bank amounts minus all ledger amounts).
    * `format_amount(cents)`: `"1,234.50"`, negative amounts with a leading `-`.
    * `format_report(summary)`: four text lines: `matched: 3 lines, 1,234.50`, `bank only: ...`, `ledger only: ...` and
      `difference: +12.30` (the difference has an explicit `+` when positive, `-` when negative, nothing when zero).
''')

LM_NORMALIZE = dd('''
    import re

    _STRIP = re.compile(r"[^A-Z0-9]")


    def normalize_ref(text):
        return _STRIP.sub("", text.upper())


    def days_apart(a, b):
        return abs((a - b).days)


    def batch_key(ref):
        ref = ref.strip().upper()
        if "-" not in ref:
            return ""
        return ref.rsplit("-", 1)[0].strip()
''')

LM_MATCH = dd('''
    from collections import namedtuple

    from .normalize import batch_key, days_apart, normalize_ref

    Line = namedtuple("Line", "id date amount ref")
    Result = namedtuple("Result", "matches unmatched_bank unmatched_ledger")

    EXACT_DAYS = 5
    CONTAINED_DAYS = 10
    CONTAINED_MIN = 4
    LOOSE_DAYS = 3
    BATCH_DAYS = 7


    def _exact(b, l):
        nb = normalize_ref(b.ref)
        return b.amount == l.amount and nb != "" and nb == normalize_ref(l.ref) and days_apart(b.date, l.date) <= EXACT_DAYS


    def _contained(b, l):
        nb, nl = normalize_ref(b.ref), normalize_ref(l.ref)
        if b.amount != l.amount or days_apart(b.date, l.date) > CONTAINED_DAYS:
            return False
        if min(len(nb), len(nl)) < CONTAINED_MIN:
            return False
        return nb in nl or nl in nb


    def _loose(b, l):
        return b.amount == l.amount and days_apart(b.date, l.date) <= LOOSE_DAYS


    def _closest(b, pool, test):
        best = None
        for l in pool:
            if test(b, l):
                key = (days_apart(b.date, l.date), l.id)
                if best is None or key < best[0]:
                    best = (key, l)
        return None if best is None else best[1]


    def _check_ids(lines):
        ids = [x.id for x in lines]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate line id")


    def match(bank, ledger):
        _check_ids(bank)
        _check_ids(ledger)
        bank_left = sorted(bank, key=lambda x: (x.date, x.id))
        ledger_left = sorted(ledger, key=lambda x: (x.date, x.id))
        found = []
        for test in (_exact, _contained):
            for b in list(bank_left):
                l = _closest(b, ledger_left, test)
                if l is not None:
                    found.append((b.id, (l.id,)))
                    bank_left.remove(b)
                    ledger_left.remove(l)
        for b in list(bank_left):
            partners = [l for l in ledger_left if _loose(b, l)]
            if len(partners) != 1:
                continue
            l = partners[0]
            if sum(1 for x in bank_left if _loose(x, l)) != 1:
                continue
            found.append((b.id, (l.id,)))
            bank_left.remove(b)
            ledger_left.remove(l)
        for b in list(bank_left):
            groups = {}
            for l in ledger_left:
                key = batch_key(l.ref)
                if key and days_apart(b.date, l.date) <= BATCH_DAYS:
                    groups.setdefault(key, []).append(l)
            for key in sorted(groups):
                group = groups[key]
                if len(group) >= 2 and sum(x.amount for x in group) == b.amount:
                    found.append((b.id, tuple(sorted(x.id for x in group))))
                    bank_left.remove(b)
                    for x in group:
                        ledger_left.remove(x)
                    break
        return Result(sorted(found), sorted(x.id for x in bank_left), sorted(x.id for x in ledger_left))
''')

LM_REPORT = dd('''
    def format_amount(cents):
        sign = "-" if cents < 0 else ""
        whole, frac = divmod(abs(cents), 100)
        return sign + format(whole, ",") + "." + format(frac, "02d")


    def summarize(result, bank, ledger):
        bank_by_id = {b.id: b for b in bank}
        ledger_by_id = {l.id: l for l in ledger}
        return {
            "matched": len(result.matches),
            "matched_amount": sum(bank_by_id[bid].amount for bid, _ in result.matches),
            "bank_only": len(result.unmatched_bank),
            "bank_only_amount": sum(bank_by_id[i].amount for i in result.unmatched_bank),
            "ledger_only": len(result.unmatched_ledger),
            "ledger_only_amount": sum(ledger_by_id[i].amount for i in result.unmatched_ledger),
            "difference": sum(b.amount for b in bank) - sum(l.amount for l in ledger),
        }


    def format_report(summary):
        diff = summary["difference"]
        shown = ("+" if diff > 0 else "") + format_amount(diff)
        return [
            "matched: %d lines, %s" % (summary["matched"], format_amount(summary["matched_amount"])),
            "bank only: %d lines, %s" % (summary["bank_only"], format_amount(summary["bank_only_amount"])),
            "ledger only: %d lines, %s" % (summary["ledger_only"], format_amount(summary["ledger_only_amount"])),
            "difference: " + shown,
        ]
''')

LM_VISIBLE = dd('''
    import unittest
    from datetime import date

    from ledgermatch.match import Line, match
    from ledgermatch.normalize import normalize_ref


    class BasicTests(unittest.TestCase):
        def test_normalize(self):
            self.assertEqual(normalize_ref("inv-22 31"), "INV2231")

        def test_exact_match(self):
            bank = [Line(1, date(2025, 3, 3), 5000, "INV 2231")]
            ledger = [Line(10, date(2025, 3, 4), 5000, "inv-2231")]
            self.assertEqual(match(bank, ledger).matches, [(1, (10,))])


    if __name__ == "__main__":
        unittest.main()
''')

LM_HIDDEN = dd('''
    import unittest
    from datetime import date

    from ledgermatch.match import Line, match
    from ledgermatch.normalize import batch_key, days_apart, normalize_ref
    from ledgermatch.report import format_amount, format_report, summarize

    D = date


    def d(day):
        return D(2025, 3, day)


    class Helpers(unittest.TestCase):
        def test_normalize(self):
            table = {"PMT INV-2231 ACME LTD": "PMTINV2231ACMELTD", "inv-22 31": "INV2231", "": "", "---": "", "a.b/c_9": "ABC9",
                     "Abc123": "ABC123"}
            for text, want in table.items():
                self.assertEqual(normalize_ref(text), want, text)

        def test_days_apart(self):
            self.assertEqual(days_apart(d(3), d(8)), 5)
            self.assertEqual(days_apart(d(8), d(3)), 5)
            self.assertEqual(days_apart(d(3), d(3)), 0)
            self.assertEqual(days_apart(D(2025, 2, 27), D(2025, 3, 2)), 3)

        def test_batch_key(self):
            table = {"payrun-07-a": "PAYRUN-07", "A-B-C": "A-B", "NODASH": "", "": "", " x-y ": "X", "x -y": "X", "-": "",
                     "PAY RUN 7": "", "a-": "A"}
            for ref, key in table.items():
                self.assertEqual(batch_key(ref), key, ref)


    class ExactPass(unittest.TestCase):
        def test_simple(self):
            bank = [Line(1, d(3), 5000, "inv 2231")]
            ledger = [Line(10, d(5), 5000, "INV-2231")]
            self.assertEqual(match(bank, ledger), ([(1, (10,))], [], []))

        def test_five_days_is_the_limit_for_short_references(self):
            for gap, matched in ((5, True), (6, False)):
                got = match([Line(1, d(3), 800, "A1")], [Line(10, d(3 + gap), 800, "a-1")])
                self.assertEqual(got.matches, [(1, (10,))] if matched else [], gap)

        def test_amount_must_be_equal(self):
            got = match([Line(1, d(3), 5000, "INV2231")], [Line(10, d(3), 5001, "INV2231")])
            self.assertEqual(got, ([], [1], [10]))
            got = match([Line(1, d(3), -5000, "INV2231")], [Line(10, d(3), 5000, "INV2231")])
            self.assertEqual(got, ([], [1], [10]))

        def test_empty_references_never_match_each_other_here(self):
            bank = [Line(1, d(3), 100, ""), Line(2, d(3), 100, "")]
            ledger = [Line(10, d(3), 100, ""), Line(11, d(3), 100, "")]
            self.assertEqual(match(bank, ledger), ([], [1, 2], [10, 11]))

        def test_closest_date_wins_then_lower_id(self):
            bank = [Line(1, d(4), 5000, "INV1234")]
            ledger = [Line(10, d(9), 5000, "INV1234"), Line(11, d(5), 5000, "INV1234")]
            self.assertEqual(match(bank, ledger), ([(1, (11,))], [], [10]))
            ledger = [Line(13, d(5), 5000, "INV1234"), Line(12, d(3), 5000, "INV1234")]
            self.assertEqual(match(bank, ledger), ([(1, (12,))], [], [13]))

        def test_bank_lines_are_served_by_date_then_id(self):
            bank = [Line(1, d(10), 5000, "INV1234"), Line(2, d(5), 5000, "INV1234")]
            ledger = [Line(10, d(7), 5000, "INV1234")]
            self.assertEqual(match(bank, ledger), ([(2, (10,))], [1], []))
            bank = [Line(2, d(5), 5000, "INV1234"), Line(1, d(5), 5000, "INV1234")]
            self.assertEqual(match(bank, ledger), ([(1, (10,))], [2], []))

        def test_ledger_line_is_used_once(self):
            bank = [Line(1, d(3), 5000, "INV1234"), Line(2, d(4), 5000, "INV1234")]
            ledger = [Line(10, d(3), 5000, "INV1234")]
            got = match(bank, ledger)
            self.assertEqual(got.matches, [(1, (10,))])
            self.assertEqual(got.unmatched_bank, [2])


    class ContainedPass(unittest.TestCase):
        def test_bank_text_contains_the_ledger_reference(self):
            bank = [Line(1, d(3), 12000, "PMT INV-2231 ACME LTD")]
            ledger = [Line(10, d(6), 12000, "INV-2231")]
            self.assertEqual(match(bank, ledger), ([(1, (10,))], [], []))

        def test_ledger_text_contains_the_bank_reference(self):
            bank = [Line(1, d(3), 12000, "INV 2231")]
            ledger = [Line(10, d(6), 12000, "Invoice INV-2231 for ACME")]
            self.assertEqual(match(bank, ledger), ([(1, (10,))], [], []))

        def test_ten_days_is_the_limit(self):
            for gap, matched in ((10, True), (11, False)):
                got = match([Line(1, d(3), 12000, "PMT INV-2231")], [Line(10, d(3 + gap), 12000, "INV2231")])
                self.assertEqual(bool(got.matches), matched, gap)

        def test_short_references_do_not_count(self):
            got = match([Line(1, d(3), 700, "PMT A12 X")], [Line(10, d(9), 700, "A12")])
            self.assertEqual(got, ([], [1], [10]))
            got = match([Line(1, d(3), 700, "PMT A123 X")], [Line(10, d(9), 700, "A123")])
            self.assertEqual(got.matches, [(1, (10,))])

        def test_amount_must_be_equal(self):
            got = match([Line(1, d(3), 700, "PMT INV2231")], [Line(10, d(4), 701, "INV2231")])
            self.assertEqual(got, ([], [1], [10]))

        def test_exact_pass_goes_first(self):
            bank = [Line(1, d(10), 100, "INV2231")]
            ledger = [Line(10, d(14), 100, "INV2231"), Line(11, d(10), 100, "PMT INV2231")]
            self.assertEqual(match(bank, ledger), ([(1, (10,))], [], [11]))

        def test_closest_candidate_in_this_pass_too(self):
            bank = [Line(1, d(10), 100, "PMT INV2231")]
            ledger = [Line(10, d(14), 100, "INV2231"), Line(11, d(9), 100, "PMT INV2231 X")]
            got = match(bank, ledger)
            self.assertEqual(got.matches, [(1, (11,))])
            self.assertEqual(got.unmatched_ledger, [10])


    class LoosePass(unittest.TestCase):
        def test_same_amount_close_dates(self):
            got = match([Line(1, d(3), 7777, "x")], [Line(10, d(6), 7777, "something else")])
            self.assertEqual(got.matches, [(1, (10,))])
            got = match([Line(1, d(3), 7777, "x")], [Line(10, d(7), 7777, "something else")])
            self.assertEqual(got.matches, [])

        def test_ledger_before_bank_date(self):
            got = match([Line(1, d(6), 7777, "x")], [Line(10, d(3), 7777, "other")])
            self.assertEqual(got.matches, [(1, (10,))])

        def test_ambiguous_ledger_side(self):
            bank = [Line(1, d(3), 7777, "x")]
            ledger = [Line(10, d(3), 7777, "a"), Line(11, d(4), 7777, "b")]
            self.assertEqual(match(bank, ledger), ([], [1], [10, 11]))

        def test_ambiguous_bank_side(self):
            bank = [Line(1, d(3), 7777, "x"), Line(2, d(4), 7777, "y")]
            ledger = [Line(10, d(3), 7777, "a")]
            self.assertEqual(match(bank, ledger), ([], [1, 2], [10]))

        def test_unambiguous_once_the_others_are_gone(self):
            bank = [Line(1, d(3), 7777, "INV9999"), Line(2, d(4), 7777, "unrelated")]
            ledger = [Line(10, d(3), 7777, "INV9999"), Line(11, d(5), 7777, "something")]
            self.assertEqual(match(bank, ledger), ([(1, (10,)), (2, (11,))], [], []))

        def test_distant_candidates_do_not_make_it_ambiguous(self):
            bank = [Line(1, d(3), 7777, "x")]
            ledger = [Line(10, d(4), 7777, "a"), Line(11, d(20), 7777, "b")]
            self.assertEqual(match(bank, ledger), ([(1, (10,))], [], [11]))

        def test_different_amounts_never_match(self):
            got = match([Line(1, d(3), 7777, "x")], [Line(10, d(3), 7778, "x")])
            self.assertEqual(got, ([], [1], [10]))


    class BatchPass(unittest.TestCase):
        LEDGER = [Line(10, d(3), 1000, "PAYRUN-07-A"), Line(11, d(4), 2000, "PAYRUN-07-B"), Line(12, d(4), 3500, "payrun-07-c")]

        def test_group_sum(self):
            got = match([Line(1, d(5), 6500, "BULK PAYMENT")], self.LEDGER)
            self.assertEqual(got, ([(1, (10, 11, 12))], [], []))

        def test_sum_must_be_exact(self):
            for amount in (6499, 6501, 3000 + 1):
                got = match([Line(1, d(5), amount, "BULK PAYMENT")], self.LEDGER)
                self.assertEqual(got.matches, [], amount)

        def test_two_of_three_is_a_group_only_if_they_are_all_there_is(self):
            got = match([Line(1, d(5), 3000, "BULK PAYMENT")], self.LEDGER[:2])
            self.assertEqual(got.matches, [(1, (10, 11))])
            got = match([Line(1, d(5), 3000, "BULK PAYMENT")], self.LEDGER)
            self.assertEqual(got.matches, [])

        def test_seven_days(self):
            ledger = [Line(10, d(3), 1000, "RUN-1-A"), Line(11, d(12), 2000, "RUN-1-B")]
            got = match([Line(1, d(10), 3000, "BULK")], ledger)
            self.assertEqual(got.matches, [(1, (10, 11))])
            got = match([Line(1, d(11), 3000, "BULK")], ledger)
            self.assertEqual(got.matches, [])
            ledger = [Line(10, d(3), 1000, "RUN-1-A"), Line(11, d(3), 2000, "RUN-1-B")]
            self.assertEqual(match([Line(1, d(10), 3000, "BULK")], ledger).matches, [(1, (10, 11))])
            self.assertEqual(match([Line(1, d(11), 3000, "BULK")], ledger).matches, [])

        def test_single_line_is_not_a_batch(self):
            got = match([Line(1, d(8), 1000, "BULK")], [Line(10, d(3), 1000, "RUN-1-A")])
            self.assertEqual(got, ([], [1], [10]))

        def test_lines_without_a_key_do_not_group(self):
            ledger = [Line(10, d(3), 1000, "RUN1A"), Line(11, d(3), 2000, "RUN1B")]
            self.assertEqual(match([Line(1, d(5), 3000, "BULK")], ledger), ([], [1], [10, 11]))

        def test_different_keys_do_not_mix(self):
            ledger = [Line(10, d(3), 1000, "RUN-1-A"), Line(11, d(3), 2000, "RUN-2-A")]
            self.assertEqual(match([Line(1, d(5), 3000, "BULK")], ledger).matches, [])

        def test_alphabetically_first_key_wins(self):
            ledger = [Line(10, d(3), 1000, "BBB-1-A"), Line(11, d(3), 2000, "BBB-1-B"), Line(12, d(3), 1500, "AAA-1-A"),
                      Line(13, d(3), 1500, "AAA-1-B")]
            self.assertEqual(match([Line(1, d(5), 3000, "BULK")], ledger), ([(1, (12, 13))], [], [10, 11]))

        def test_earlier_passes_take_their_lines_first(self):
            bank = [Line(1, d(5), 1000, "RUN-1-A"), Line(2, d(5), 3000, "BULK")]
            ledger = [Line(10, d(5), 1000, "RUN-1-A"), Line(11, d(5), 2000, "RUN-1-B"), Line(12, d(5), 1000, "RUN-1-C")]
            got = match(bank, ledger)
            self.assertEqual(got.matches, [(1, (10,)), (2, (11, 12))])


    class Result(unittest.TestCase):
        def test_ordering(self):
            bank = [Line(5, d(9), 100, "ZZZZ"), Line(2, d(3), 200, "INV2222"), Line(9, d(1), 300, "INV3333"), Line(1, d(20), 50, "nothing")]
            ledger = [Line(30, d(3), 300, "INV3333"), Line(20, d(3), 200, "INV2222"), Line(40, d(12), 999, "other"),
                      Line(10, d(9), 100, "ZZZZ")]
            got = match(bank, ledger)
            self.assertEqual(got.matches, [(2, (20,)), (5, (10,)), (9, (30,))])
            self.assertEqual(got.unmatched_bank, [1])
            self.assertEqual(got.unmatched_ledger, [40])

        def test_empty(self):
            self.assertEqual(match([], []), ([], [], []))
            self.assertEqual(match([Line(1, d(3), 5, "a")], []), ([], [1], []))
            self.assertEqual(match([], [Line(1, d(3), 5, "a")]), ([], [], [1]))

        def test_duplicate_ids(self):
            with self.assertRaises(ValueError):
                match([Line(1, d(3), 5, "a"), Line(1, d(4), 6, "b")], [])
            with self.assertRaises(ValueError):
                match([], [Line(1, d(3), 5, "a"), Line(1, d(4), 6, "b")])
            match([Line(1, d(3), 5, "a")], [Line(1, d(3), 6, "a")])

        def test_inputs_are_not_modified(self):
            bank = [Line(2, d(5), 100, "AAAA"), Line(1, d(3), 100, "AAAA")]
            ledger = [Line(11, d(5), 100, "AAAA"), Line(10, d(3), 100, "AAAA")]
            match(bank, ledger)
            self.assertEqual([b.id for b in bank], [2, 1])
            self.assertEqual([x.id for x in ledger], [11, 10])


    class Report(unittest.TestCase):
        BANK = [Line(1, d(3), 120_000, "INV2231"), Line(2, d(4), -4500, "CARD"), Line(3, d(5), 300, "FEE")]
        LEDGER = [Line(10, d(3), 120_000, "INV2231"), Line(11, d(6), 999, "SOMETHING")]

        def test_summary(self):
            res = match(self.BANK, self.LEDGER)
            self.assertEqual(summarize(res, self.BANK, self.LEDGER), {
                "matched": 1, "matched_amount": 120_000, "bank_only": 2, "bank_only_amount": -4200,
                "ledger_only": 1, "ledger_only_amount": 999, "difference": 120_000 - 4500 + 300 - 120_000 - 999})

        def test_nothing_matched(self):
            res = match([Line(1, d(3), 5, "a")], [Line(2, d(20), 7, "b")])
            got = summarize(res, [Line(1, d(3), 5, "a")], [Line(2, d(20), 7, "b")])
            self.assertEqual((got["matched"], got["matched_amount"], got["difference"]), (0, 0, -2))

        def test_format_amount(self):
            table = {0: "0.00", 5: "0.05", 100: "1.00", 123_450: "1,234.50", -5: "-0.05", -123_450: "-1,234.50",
                     100_000_000: "1,000,000.00", 99_999: "999.99"}
            for cents, text in table.items():
                self.assertEqual(format_amount(cents), text, cents)

        def test_format_report(self):
            res = match(self.BANK, self.LEDGER)
            lines = format_report(summarize(res, self.BANK, self.LEDGER))
            self.assertEqual(lines, ["matched: 1 lines, 1,200.00", "bank only: 2 lines, -42.00", "ledger only: 1 lines, 9.99",
                                     "difference: -51.99"])

        def test_difference_signs(self):
            base = {"matched": 0, "matched_amount": 0, "bank_only": 0, "bank_only_amount": 0, "ledger_only": 0, "ledger_only_amount": 0}
            self.assertEqual(format_report({**base, "difference": 1230})[-1], "difference: +12.30")
            self.assertEqual(format_report({**base, "difference": -1230})[-1], "difference: -12.30")
            self.assertEqual(format_report({**base, "difference": 0})[-1], "difference: 0.00")


    if __name__ == "__main__":
        unittest.main()
''')

LEDGERMATCH = Lib(
    name="ledgermatch", lang="python", title="the bank reconciliation matcher (`ledgermatch/`)",
    blurb="The bookkeeping tool matches bank statement lines against ledger entries with ledgermatch.",
    files={"ledgermatch/__init__.py": "", "ledgermatch/normalize.py": LM_NORMALIZE, "ledgermatch/match.py": LM_MATCH,
           "ledgermatch/report.py": LM_REPORT, "README.md": LM_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": LM_VISIBLE},
    hidden_tests={"tests/test_full.py": LM_HIDDEN},
    mutate=["ledgermatch/normalize.py", "ledgermatch/match.py", "ledgermatch/report.py"], difficulty=4,
    tags=["reconciliation", "matching", "ledger"],
    probes=[
        "normalize_ref('PMT INV-2231 ACME LTD')", "batch_key('payrun-07-a')", "batch_key('NODASH')", "days_apart(date(2025, 2, 27), date(2025, 3, 2))",
        "match([Line(1, date(2025, 3, 3), 800, 'A1')], [Line(10, date(2025, 3, 9), 800, 'a-1')])",
        "match([Line(1, date(2025, 3, 3), 12000, 'PMT INV-2231')], [Line(10, date(2025, 3, 14), 12000, 'INV2231')]).matches",
        "match([Line(1, date(2025, 3, 3), 7777, 'x')], [Line(10, date(2025, 3, 3), 7777, 'a'), Line(11, date(2025, 3, 4), 7777, 'b')])",
        "match([Line(1, date(2025, 3, 5), 6500, 'BULK')], [Line(10, date(2025, 3, 3), 1000, 'PAYRUN-07-A'), Line(11, date(2025, 3, 4), 2000, 'PAYRUN-07-B'), Line(12, date(2025, 3, 4), 3500, 'payrun-07-c')])",
        "match([Line(1, date(2025, 3, 5), 3000, 'BULK')], [Line(10, date(2025, 3, 3), 1000, 'BBB-1-A'), Line(11, date(2025, 3, 3), 2000, 'BBB-1-B'), Line(12, date(2025, 3, 3), 1500, 'AAA-1-A'), Line(13, date(2025, 3, 3), 1500, 'AAA-1-B')])",
        "format_amount(-123450)", "format_report(summarize(match([Line(1, date(2025, 3, 3), 5, 'a')], []), [Line(1, date(2025, 3, 3), 5, 'a')], []))",
    ],
    probe_import="from datetime import date\nfrom ledgermatch.normalize import *\nfrom ledgermatch.match import *\nfrom ledgermatch.report import *",
)

register_libs([LEDGERMATCH], n=10)
