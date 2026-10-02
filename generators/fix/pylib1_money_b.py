"""Python libraries, theme time/money/scheduling (batch money-b): invoice numbering and allocation, currency desk."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# billnum: invoice numbers with a check character, largest-remainder allocation of discounts and tax, text summary
# ======================================================================================================================

BN_README = dd('''
    # billnum

    Invoice numbering and amount allocation for the billing back-office. Money is an `int` number of cents.

    ## Numbers (`billnum/numbering.py`)

    An invoice number looks like `SLS-2025-000042-V`: a series prefix, the year, a six-digit sequence and a check
    character. Symbols come from `ALPHABET`, the 34 characters `0123456789ABCDEFGHJKLMNPQRSTUVWXYZ` (no `I`, no `O`);
    their values are their positions in that string (`0` is 0, `A` is 10, `Z` is 33).

    * `check_char(body)`: upper-cases `body`, multiplies the value of the i-th character (from 0) by the weight
      `7, 3, 1, 7, 3, 1, ...`, adds everything up and returns `ALPHABET[total % 34]`. A character outside the
      alphabet is a `ValueError`.
    * `make_number(prefix, year, seq)`: `prefix` is 2 to 4 upper-case letters from the alphabet, `year` is 2000 to
      2099, `seq` is 1 to 999999 (anything else is a `ValueError`). The check character is computed over
      `prefix + year + six-digit seq` (no dashes).
    * `parse_number(text)`: strips and upper-cases the text, returns `(prefix, year, seq)` for a well-formed number
      with a correct check character and sequence of at least 1; anything else is a `ValueError`.
    * `next_number(prefix, year, last)`: the number that follows `last` (the previously issued number as text, or
      `None` for the first one). The sequence counts up inside one prefix and one year and restarts at 1 for a later
      year. A `last` that is not a valid number, one of another prefix or of a later year is a `ValueError`, and so is
      running past 999999.

    ## Allocation (`billnum/alloc.py`)

    * `allocate(total, weights)`: splits `total` in proportion to the non-negative integer `weights` so that the shares
      add up to `total` exactly (largest-remainder method): each share is first rounded down, then the leftover cents
      go one each to the shares with the largest remainders, ties to the earlier index. A negative total is allocated
      by magnitude and negated. No weights, a negative weight or weights adding up to 0 is a `ValueError`.
    * `spread_discount(lines, discount)`: reduces the line amounts by `allocate(discount, lines)`. A negative line or
      discount, or a discount larger than the sum of the lines is a `ValueError`; a zero discount returns the lines
      unchanged (even if they are all zero).
    * `tax_split(lines, rate_bp)`: the invoice tax is `sum(lines) * rate_bp / 10000` rounded half up to a cent, and
      it is allocated to the lines in proportion to their net amounts. Returns `(net, tax, gross)` per line (all
      taxes are `0` when the lines add up to 0).

    ## Rendering (`billnum/render.py`)

    * `format_amount(cents, currency="EUR")`: `"1,234.50 EUR"`; thousands separated by commas, always two decimals,
      a minus sign in front of negative amounts.
    * `summary(lines, discount=0, rate_bp=0, currency="EUR")`: a list of text rows. `net` is the sum of the original
      lines. When `discount > 0` there is a `discount` row showing the negative discount; the tax is computed on the
      discounted lines (`tax_split`); a `tax` row appears only when `rate_bp > 0`; `total` is discounted net plus tax.
      Each row is the label padded to 9 characters followed by the amount right-aligned to the width of the widest
      amount.
''')

BN_NUMBERING = dd('''
    import re

    ALPHABET = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    WEIGHTS = (7, 3, 1)
    MAX_SEQ = 999_999

    _NUMBER = re.compile(r"^([A-Z]{2,4})-(20\\d\\d)-(\\d{6})-([0-9A-Z])$")


    def check_char(body):
        total = 0
        for i, ch in enumerate(body.upper()):
            value = ALPHABET.find(ch)
            if value < 0:
                raise ValueError(f"character {ch!r} is not in the alphabet")
            total += value * WEIGHTS[i % 3]
        return ALPHABET[total % len(ALPHABET)]


    def make_number(prefix, year, seq):
        if not (2 <= len(prefix) <= 4 and prefix.isalpha() and prefix.isupper()):
            raise ValueError("prefix must be 2 to 4 upper-case letters")
        if not 2000 <= year <= 2099:
            raise ValueError("year out of range")
        if not 1 <= seq <= MAX_SEQ:
            raise ValueError("sequence out of range")
        body = prefix + str(year) + format(seq, "06d")
        return "-".join([prefix, str(year), format(seq, "06d"), check_char(body)])


    def parse_number(text):
        m = _NUMBER.match(text.strip().upper())
        if not m:
            raise ValueError("malformed invoice number")
        prefix, year, seq, check = m.group(1), m.group(2), m.group(3), m.group(4)
        if int(seq) < 1:
            raise ValueError("sequence must be at least 1")
        if check_char(prefix + year + seq) != check:
            raise ValueError("wrong check character")
        return prefix, int(year), int(seq)


    def next_number(prefix, year, last):
        if last is None:
            seq = 1
        else:
            last_prefix, last_year, last_seq = parse_number(last)
            if last_prefix != prefix:
                raise ValueError("last number belongs to another series")
            if last_year > year:
                raise ValueError("last number is from a later year")
            seq = last_seq + 1 if last_year == year else 1
        return make_number(prefix, year, seq)
''')

BN_ALLOC = dd('''
    def allocate(total, weights):
        if not weights or any(w < 0 for w in weights):
            raise ValueError("weights must be a non-empty list of non-negative numbers")
        weight_sum = sum(weights)
        if weight_sum == 0:
            raise ValueError("weights add up to zero")
        sign = -1 if total < 0 else 1
        magnitude = abs(total)
        shares = [magnitude * w // weight_sum for w in weights]
        remainders = [magnitude * w % weight_sum for w in weights]
        order = sorted(range(len(weights)), key=lambda i: (-remainders[i], i))
        for i in order[: magnitude - sum(shares)]:
            shares[i] += 1
        return [sign * s for s in shares]


    def spread_discount(lines, discount):
        if discount < 0 or any(x < 0 for x in lines):
            raise ValueError("negative amount")
        if discount > sum(lines):
            raise ValueError("discount exceeds the invoice")
        if discount == 0:
            return list(lines)
        return [line - share for line, share in zip(lines, allocate(discount, lines))]


    def tax_split(lines, rate_bp):
        total = sum(lines)
        if total == 0:
            return [(net, 0, net) for net in lines]
        tax = (2 * total * rate_bp + 10_000) // 20_000
        return [(net, t, net + t) for net, t in zip(lines, allocate(tax, lines))]
''')

BN_RENDER = dd('''
    from .alloc import spread_discount, tax_split


    def format_amount(cents, currency="EUR"):
        sign = "-" if cents < 0 else ""
        whole, frac = divmod(abs(cents), 100)
        return sign + format(whole, ",") + "." + format(frac, "02d") + " " + currency


    def summary(lines, discount=0, rate_bp=0, currency="EUR"):
        net = sum(lines)
        after = spread_discount(lines, discount)
        rows = [("net", net)]
        if discount > 0:
            rows.append(("discount", -discount))
        tax = 0
        if rate_bp > 0:
            tax = sum(t for _, t, _ in tax_split(after, rate_bp))
            rows.append(("tax", tax))
        rows.append(("total", sum(after) + tax))
        texts = [format_amount(value, currency) for _, value in rows]
        width = max(len(t) for t in texts)
        return [label.ljust(9) + text.rjust(width) for (label, _), text in zip(rows, texts)]
''')

BN_VISIBLE = dd('''
    import unittest

    from billnum.alloc import allocate
    from billnum.numbering import check_char, make_number
    from billnum.render import format_amount


    class BasicTests(unittest.TestCase):
        def test_check_char_single(self):
            self.assertEqual(check_char("1"), "7")

        def test_make_number_shape(self):
            self.assertRegex(make_number("SLS", 2025, 42), r"^SLS-2025-000042-[0-9A-Z]$")

        def test_allocate_even(self):
            self.assertEqual(allocate(90, [1, 1, 1]), [30, 30, 30])

        def test_format(self):
            self.assertEqual(format_amount(123450), "1,234.50 EUR")


    if __name__ == "__main__":
        unittest.main()
''')

BN_HIDDEN = dd('''
    import unittest

    from billnum.alloc import allocate, spread_discount, tax_split
    from billnum.numbering import ALPHABET, check_char, make_number, next_number, parse_number
    from billnum.render import format_amount, summary


    def independent_check(body):
        values = {c: i for i, c in enumerate("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ")}
        total = 0
        for i, c in enumerate(body):
            total += values[c] * (7, 3, 1)[i % 3]
        return "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"[total % 34]


    class CheckChar(unittest.TestCase):
        def test_alphabet(self):
            self.assertEqual(len(ALPHABET), 34)
            self.assertNotIn("I", ALPHABET)
            self.assertNotIn("O", ALPHABET)

        def test_known_values(self):
            table = {"0": "0", "1": "7", "9": "V", "Z": "T", "10": "7", "01": "3", "001": "1", "AB12": "G", "": "0"}
            for body, want in table.items():
                self.assertEqual(check_char(body), want, body)

        def test_weights_cycle(self):
            self.assertEqual(check_char("1111"), independent_check("1111"))
            self.assertEqual(check_char("11111111"), independent_check("11111111"))
            self.assertEqual(check_char("ABCDEFGH1234567"), independent_check("ABCDEFGH1234567"))

        def test_lowercase_is_accepted(self):
            self.assertEqual(check_char("ab12"), "G")

        def test_bad_symbols(self):
            for body in ("I", "O", "12-3", "A B", "\\u00e9"):
                with self.assertRaises(ValueError, msg=body):
                    check_char(body)

        def test_modulus(self):
            # 'Z' * 7 = 231 = 6 * 34 + 27 ; 'Y' (32) * 7 = 224 = 6 * 34 + 20
            self.assertEqual(check_char("Y"), "L")
            self.assertEqual(check_char("ZZ"), independent_check("ZZ"))


    class MakeAndParse(unittest.TestCase):
        def test_make(self):
            for prefix, year, seq in (("SLS", 2025, 42), ("AC", 2000, 1), ("RTLX", 2099, 999_999), ("BK", 2031, 123_456)):
                text = make_number(prefix, year, seq)
                body = prefix + str(year) + "%06d" % seq
                self.assertEqual(text, f"{prefix}-{year}-{seq:06d}-{independent_check(body)}")

        def test_make_errors(self):
            bad = [("S", 2025, 1), ("SLSXX", 2025, 1), ("sls", 2025, 1), ("S1S", 2025, 1), ("", 2025, 1), ("SLS", 1999, 1),
                   ("SLS", 2100, 1), ("SLS", 2025, 0), ("SLS", 2025, 1_000_000), ("SLS", 2025, -4), ("SIS", 2025, 1)]
            for args in bad:
                with self.assertRaises(ValueError, msg=args):
                    make_number(*args)

        def test_make_edges_are_valid(self):
            make_number("AB", 2000, 1)
            make_number("ABCD", 2099, 999_999)

        def test_parse_round_trip(self):
            for prefix, year, seq in (("SLS", 2025, 42), ("AC", 2000, 1), ("RTLX", 2099, 999_999), ("BK", 2031, 123_456)):
                self.assertEqual(parse_number(make_number(prefix, year, seq)), (prefix, year, seq))

        def test_parse_normalises(self):
            text = make_number("SLS", 2025, 42)
            self.assertEqual(parse_number("  " + text.lower() + "\\n"), ("SLS", 2025, 42))

        def test_parse_rejects_wrong_check(self):
            text = make_number("SLS", 2025, 42)
            other = ALPHABET[(ALPHABET.index(text[-1]) + 1) % 34]
            with self.assertRaises(ValueError):
                parse_number(text[:-1] + other)

        def test_parse_rejects_changed_digit(self):
            text = make_number("SLS", 2025, 42)
            with self.assertRaises(ValueError):
                parse_number(text.replace("000042", "000043"))

        def test_parse_malformed(self):
            ok = make_number("SLS", 2025, 42)
            for bad in ("", "SLS-2025-000042", "SLS-2025-42-" + ok[-1], "S-2025-000042-" + ok[-1], "SLS-1999-000042-" + ok[-1],
                        "SLS2025000042" + ok[-1], ok + "-", "SLS-2025-000042-", "SLS-2025-0000042-" + ok[-1], "SLSXX-2025-000042-" + ok[-1],
                        "SLS-2025-000000-0"):
                with self.assertRaises(ValueError, msg=bad):
                    parse_number(bad)

        def test_parse_zero_sequence_with_valid_check(self):
            body = "SLS2025000000"
            with self.assertRaises(ValueError):
                parse_number(f"SLS-2025-000000-{independent_check(body)}")


    class NextNumber(unittest.TestCase):
        def test_first(self):
            self.assertEqual(next_number("SLS", 2025, None), make_number("SLS", 2025, 1))

        def test_counts_up(self):
            self.assertEqual(next_number("SLS", 2025, make_number("SLS", 2025, 41)), make_number("SLS", 2025, 42))
            self.assertEqual(next_number("SLS", 2025, make_number("SLS", 2025, 999_998)), make_number("SLS", 2025, 999_999))

        def test_new_year_restarts(self):
            self.assertEqual(next_number("SLS", 2026, make_number("SLS", 2025, 777)), make_number("SLS", 2026, 1))

        def test_errors(self):
            with self.assertRaises(ValueError):
                next_number("SLS", 2025, make_number("SLS", 2025, 999_999))
            with self.assertRaises(ValueError):
                next_number("SLS", 2025, make_number("RTL", 2025, 5))
            with self.assertRaises(ValueError):
                next_number("SLS", 2024, make_number("SLS", 2025, 5))
            with self.assertRaises(ValueError):
                next_number("SLS", 2025, "garbage")


    class Allocate(unittest.TestCase):
        def test_exact(self):
            self.assertEqual(allocate(90, [1, 1, 1]), [30, 30, 30])
            self.assertEqual(allocate(100, [1, 3]), [25, 75])
            self.assertEqual(allocate(0, [3, 4]), [0, 0])

        def test_largest_remainder(self):
            self.assertEqual(allocate(100, [1, 1, 1]), [34, 33, 33])
            self.assertEqual(allocate(10, [1, 1, 1]), [4, 3, 3])
            self.assertEqual(allocate(100, [1, 2, 3]), [17, 33, 50])
            self.assertEqual(allocate(5, [1, 1, 1, 1]), [2, 1, 1, 1])
            self.assertEqual(allocate(10, [5, 3, 2, 0]), [5, 3, 2, 0])
            self.assertEqual(allocate(7, [2, 3, 5]), [1, 2, 4])

        def test_remainder_order_not_weight_order(self):
            # shares 0.9, 1.8, 1.3: floors 0, 1, 1; the two leftover cents go to the remainders 0.9 and 0.8
            self.assertEqual(allocate(4, [9, 18, 13]), [1, 2, 1])
            self.assertEqual(allocate(3, [1, 4, 5]), [0, 1, 2])
            self.assertEqual(allocate(3, [5, 4, 1]), [2, 1, 0])
            self.assertEqual(allocate(3, [4, 5, 1]), [1, 2, 0])
            self.assertEqual(allocate(11, [3, 3, 4, 0, 1]), [3, 3, 4, 0, 1])

        def test_ties_go_to_the_earlier_index(self):
            self.assertEqual(allocate(1, [1, 1]), [1, 0])
            self.assertEqual(allocate(2, [1, 1, 1]), [1, 1, 0])
            self.assertEqual(allocate(1, [0, 1, 1]), [0, 1, 0])

        def test_zero_weights_get_nothing(self):
            self.assertEqual(allocate(10, [0, 1, 0, 1]), [0, 5, 0, 5])
            self.assertEqual(allocate(11, [0, 1, 0, 1]), [0, 6, 0, 5])

        def test_negative_total(self):
            self.assertEqual(allocate(-100, [1, 1, 1]), [-34, -33, -33])
            self.assertEqual(allocate(-1, [1, 1]), [-1, 0])
            self.assertEqual(allocate(-90, [1, 2]), [-30, -60])

        def test_sum_is_preserved(self):
            for total in range(-30, 120, 7):
                for weights in ([1], [1, 2], [3, 3, 3], [5, 0, 7, 1], [2, 2, 2, 2, 2, 2, 2]):
                    got = allocate(total, weights)
                    self.assertEqual(sum(got), total, (total, weights))
                    self.assertEqual(len(got), len(weights))

        def test_errors(self):
            for total, weights in ((10, []), (10, [0, 0]), (10, [1, -1]), (10, [-1, 5])):
                with self.assertRaises(ValueError, msg=weights):
                    allocate(total, weights)


    class Discount(unittest.TestCase):
        def test_proportional(self):
            self.assertEqual(spread_discount([1000, 3000], 400), [900, 2700])
            self.assertEqual(spread_discount([1000, 1000, 1000], 100), [966, 967, 967])
            self.assertEqual(spread_discount([100, 200, 300], 7), [99, 198, 296])

        def test_whole_invoice(self):
            self.assertEqual(spread_discount([500, 700], 1200), [0, 0])

        def test_zero_discount(self):
            self.assertEqual(spread_discount([500, 700], 0), [500, 700])
            self.assertEqual(spread_discount([0, 0], 0), [0, 0])

        def test_zero_line_stays_zero(self):
            self.assertEqual(spread_discount([0, 1000, 500], 150), [0, 900, 450])

        def test_does_not_mutate_input(self):
            lines = [10, 20]
            spread_discount(lines, 0)
            spread_discount(lines, 3)
            self.assertEqual(lines, [10, 20])

        def test_errors(self):
            for lines, discount in (([500, 700], 1201), ([500, 700], -1), ([500, -700], 10), ([0, 0], 1)):
                with self.assertRaises(ValueError, msg=(lines, discount)):
                    spread_discount(lines, discount)


    class Tax(unittest.TestCase):
        def test_split(self):
            self.assertEqual(tax_split([1000, 3000], 1900), [(1000, 190, 1190), (3000, 570, 3570)])
            self.assertEqual(tax_split([1000], 2000), [(1000, 200, 1200)])

        def test_tax_is_computed_on_the_total(self):
            # per line: 33 * 5% = 1.65 -> 2 each (6 in total); on the invoice: 99 * 5% = 4.95 -> 5
            got = tax_split([33, 33, 33], 500)
            self.assertEqual(sum(t for _, t, _ in got), 5)
            self.assertEqual([t for _, t, _ in got], [2, 2, 1])
            self.assertEqual([g for _, _, g in got], [35, 35, 34])

        def test_half_up(self):
            self.assertEqual(sum(t for _, t, _ in tax_split([10], 500)), 1)   # 0.5 -> 1
            self.assertEqual(sum(t for _, t, _ in tax_split([9], 500)), 0)    # 0.45 -> 0
            self.assertEqual(sum(t for _, t, _ in tax_split([30], 500)), 2)   # 1.5 -> 2
            self.assertEqual(sum(t for _, t, _ in tax_split([29], 500)), 1)   # 1.45 -> 1

        def test_zero(self):
            self.assertEqual(tax_split([0, 0], 1900), [(0, 0, 0), (0, 0, 0)])
            self.assertEqual(tax_split([], 1900), [])
            self.assertEqual(tax_split([100, 200], 0), [(100, 0, 100), (200, 0, 200)])


    class Rendering(unittest.TestCase):
        def test_format_amount(self):
            table = {0: "0.00 EUR", 5: "0.05 EUR", 99: "0.99 EUR", 100: "1.00 EUR", 123450: "1,234.50 EUR",
                     99999: "999.99 EUR", 100000: "1,000.00 EUR", 123456789: "1,234,567.89 EUR", -5: "-0.05 EUR",
                     -123450: "-1,234.50 EUR", -100: "-1.00 EUR"}
            for cents, text in table.items():
                self.assertEqual(format_amount(cents), text, cents)

        def test_currency(self):
            self.assertEqual(format_amount(1999, "USD"), "19.99 USD")
            self.assertEqual(format_amount(1999, "kr"), "19.99 kr")

        def test_summary_plain(self):
            self.assertEqual(summary([1000, 2000]), ["net      30.00 EUR", "total    30.00 EUR"])

        def test_summary_with_everything(self):
            rows = summary([100000, 50000], discount=15000, rate_bp=1900)
            self.assertEqual(rows, ["net      1,500.00 EUR",
                                    "discount  -150.00 EUR",
                                    "tax        256.50 EUR",
                                    "total    1,606.50 EUR"])

        def test_summary_discount_only(self):
            rows = summary([100000], discount=1, currency="USD")
            self.assertEqual(rows, ["net      1,000.00 USD", "discount    -0.01 USD", "total      999.99 USD"])

        def test_summary_tax_only(self):
            rows = summary([1000], rate_bp=500)
            self.assertEqual(rows, ["net      10.00 EUR", "tax       0.50 EUR", "total    10.50 EUR"])

        def test_summary_tax_follows_the_discounted_lines(self):
            rows = summary([33, 33, 33], discount=33, rate_bp=500)
            self.assertEqual(rows, ["net       0.99 EUR", "discount -0.33 EUR", "tax       0.03 EUR", "total     0.69 EUR"])

        def test_summary_errors(self):
            with self.assertRaises(ValueError):
                summary([100], discount=101)


    if __name__ == "__main__":
        unittest.main()
''')

BILLNUM = Lib(
    name="billnum", lang="python", title="the invoice numbering and allocation helpers (`billnum/`)",
    blurb="The billing back-office issues invoice numbers, spreads discounts over lines and splits tax with billnum.",
    files={"billnum/__init__.py": "", "billnum/numbering.py": BN_NUMBERING, "billnum/alloc.py": BN_ALLOC,
           "billnum/render.py": BN_RENDER, "README.md": BN_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": BN_VISIBLE},
    hidden_tests={"tests/test_full.py": BN_HIDDEN},
    mutate=["billnum/numbering.py", "billnum/alloc.py", "billnum/render.py"], difficulty=3,
    tags=["invoicing", "allocation", "rounding"],
    probes=[
        "check_char('AB12')", "check_char('Z')", "make_number('SLS', 2025, 42)", "parse_number(make_number('RTLX', 2099, 999_999))",
        "next_number('SLS', 2026, make_number('SLS', 2025, 777))", "allocate(100, [1, 1, 1])", "allocate(10, [5, 3, 2, 0])",
        "allocate(-100, [1, 1, 1])", "allocate(3, [4, 5, 1])", "spread_discount([1000, 1000, 1000], 100)",
        "tax_split([33, 33, 33], 500)", "tax_split([30], 500)", "format_amount(123450)", "format_amount(-5)",
        "summary([100000, 50000], discount=15000, rate_bp=1900)",
    ],
    probe_import="from billnum.numbering import *\nfrom billnum.alloc import *\nfrom billnum.render import *",
)

# ======================================================================================================================
# fxdesk: currency desk with per-currency margins, fees, minor units and an exact inverse quote
# ======================================================================================================================

FXD_README = dd('''
    # fxdesk

    Retail currency exchange for a bureau. Amounts are `int` minor units (cents, yen, fils) of the stated currency.

    ## Tables (`fxdesk/tables.py`)

    | code | minor-unit digits | mid rate per 1 EUR, in millionths | margin (bp) | fee minimum | fee maximum |
    |------|------:|------------:|----:|-----:|------:|
    | EUR | 2 | 1 000 000 | 0 | 150 | 2500 |
    | USD | 2 | 1 085 000 | 25 | 150 | 2500 |
    | GBP | 2 | 855 000 | 25 | 125 | 2000 |
    | CHF | 2 | 960 000 | 30 | 150 | 2500 |
    | JPY | 0 | 160 500 000 | 40 | 200 | 4000 |
    | KWD | 3 | 332 000 | 120 | 500 | 8000 |

    An unknown currency code anywhere is a `ValueError`; so is a negative amount.

    ## Conversion (`fxdesk/convert.py`)

    `convert(amount, src, dst)`: the exact value of `amount` in `dst` at the mid rates, reduced by the combined margin
    `(10000 - margin[src] - margin[dst]) / 10000`, rounded **down** to a whole minor unit of `dst`. The same currency
    on both sides returns `amount` unchanged (no margin).

    `fee(amount, currency)`: 0.5% of the amount (50 bp) **rounded up** to a minor unit, but at least the currency's
    minimum and at most its maximum. `fee(0, c)` is the minimum.

    `exchange(amount, src, dst)`: the fee is taken from the source amount first, the rest is converted:
    `{"fee": fee, "converted": convert(amount - fee, src, dst)}`. When `src == dst` the fee is `0` and nothing is
    converted away. An amount that does not exceed the fee (`amount <= fee`) is a `ValueError`.

    `quote_inverse(target, src, dst)`: the smallest source amount whose `exchange(...)["converted"]` is at least
    `target` (a positive integer; `target <= 0` is a `ValueError`).

    `round_trip_loss(amount, a, b)`: `amount - convert(convert(amount, a, b), b, a)` (what is lost when converting to
    `b` and straight back without fees).
''')

FXD_TABLES = dd('''
    EXPONENT = {"EUR": 2, "USD": 2, "GBP": 2, "CHF": 2, "JPY": 0, "KWD": 3}
    RATE = {"EUR": 1_000_000, "USD": 1_085_000, "GBP": 855_000, "CHF": 960_000, "JPY": 160_500_000, "KWD": 332_000}
    MARGIN_BP = {"EUR": 0, "USD": 25, "GBP": 25, "CHF": 30, "JPY": 40, "KWD": 120}
    FEE_MIN = {"EUR": 150, "USD": 150, "GBP": 125, "CHF": 150, "JPY": 200, "KWD": 500}
    FEE_MAX = {"EUR": 2500, "USD": 2500, "GBP": 2000, "CHF": 2500, "JPY": 4000, "KWD": 8000}
    FEE_BP = 50


    def check_code(code):
        if code not in EXPONENT:
            raise ValueError(f"unknown currency {code!r}")
        return code
''')

FXD_CONVERT = dd('''
    from .tables import EXPONENT, FEE_BP, FEE_MAX, FEE_MIN, MARGIN_BP, RATE, check_code


    def _check_amount(amount):
        if amount < 0:
            raise ValueError("amount must not be negative")


    def convert(amount, src, dst):
        check_code(src)
        check_code(dst)
        _check_amount(amount)
        if src == dst:
            return amount
        margin = 10_000 - MARGIN_BP[src] - MARGIN_BP[dst]
        numerator = amount * RATE[dst] * 10 ** EXPONENT[dst] * margin
        denominator = RATE[src] * 10 ** EXPONENT[src] * 10_000
        return numerator // denominator


    def fee(amount, currency):
        check_code(currency)
        _check_amount(amount)
        raw = -(-amount * FEE_BP // 10_000)
        return max(FEE_MIN[currency], min(FEE_MAX[currency], raw))


    def exchange(amount, src, dst):
        check_code(src)
        check_code(dst)
        _check_amount(amount)
        charged = 0 if src == dst else fee(amount, src)
        if amount <= charged:
            raise ValueError("amount does not cover the fee")
        return {"fee": charged, "converted": convert(amount - charged, src, dst)}


    def quote_inverse(target, src, dst):
        check_code(src)
        check_code(dst)
        if target <= 0:
            raise ValueError("target must be positive")
        if src == dst:
            return target
        margin = 10_000 - MARGIN_BP[src] - MARGIN_BP[dst]
        numerator = RATE[dst] * 10 ** EXPONENT[dst] * margin
        denominator = RATE[src] * 10 ** EXPONENT[src] * 10_000
        net = -(-target * denominator // numerator)
        amount = net + FEE_MIN[src]
        while amount - fee(amount, src) < net:
            amount += 1
        return amount


    def round_trip_loss(amount, a, b):
        return amount - convert(convert(amount, a, b), b, a)
''')

FXD_VISIBLE = dd('''
    import unittest

    from fxdesk.convert import convert, exchange, fee


    class BasicTests(unittest.TestCase):
        def test_same_currency(self):
            self.assertEqual(convert(1234, "USD", "USD"), 1234)

        def test_eur_to_usd(self):
            self.assertEqual(convert(10_000, "EUR", "USD"), 10_822)

        def test_minimum_fee(self):
            self.assertEqual(fee(1000, "EUR"), 150)

        def test_exchange_pays_fee_first(self):
            self.assertEqual(exchange(10_000, "EUR", "EUR"), {"fee": 0, "converted": 10_000})


    if __name__ == "__main__":
        unittest.main()
''')

FXD_HIDDEN = dd('''
    import math
    import unittest
    from fractions import Fraction

    from fxdesk.convert import convert, exchange, fee, quote_inverse, round_trip_loss

    EXP = {"EUR": 2, "USD": 2, "GBP": 2, "CHF": 2, "JPY": 0, "KWD": 3}
    RATE = {"EUR": 1_000_000, "USD": 1_085_000, "GBP": 855_000, "CHF": 960_000, "JPY": 160_500_000, "KWD": 332_000}
    MARGIN = {"EUR": 0, "USD": 25, "GBP": 25, "CHF": 30, "JPY": 40, "KWD": 120}
    FEE_MIN = {"EUR": 150, "USD": 150, "GBP": 125, "CHF": 150, "JPY": 200, "KWD": 500}
    FEE_MAX = {"EUR": 2500, "USD": 2500, "GBP": 2000, "CHF": 2500, "JPY": 4000, "KWD": 8000}
    CODES = sorted(EXP)


    def oracle_convert(amount, src, dst):
        if src == dst:
            return amount
        major = Fraction(amount, 10 ** EXP[src])
        eur = major / Fraction(RATE[src], 10 ** 6)
        out = eur * Fraction(RATE[dst], 10 ** 6) * 10 ** EXP[dst]
        out *= Fraction(10_000 - MARGIN[src] - MARGIN[dst], 10_000)
        return math.floor(out)


    def oracle_fee(amount, cur):
        raw = math.ceil(Fraction(amount * 50, 10_000))
        return max(FEE_MIN[cur], min(FEE_MAX[cur], raw))


    class Convert(unittest.TestCase):
        def test_known_values(self):
            self.assertEqual(convert(10_000, "EUR", "USD"), 10_822)   # 108.50 * (1 - 0.0025) = 108.22875
            self.assertEqual(convert(10_000, "USD", "EUR"), 9_193)    # 100 / 1.085 * 0.9975 = 91.9355
            self.assertEqual(convert(100, "EUR", "JPY"), 159)         # 160.5 * 0.996 = 159.858

        def test_matches_the_formula(self):
            amounts = [0, 1, 7, 99, 100, 1234, 99_999, 1_000_000, 123_456_789]
            for src in CODES:
                for dst in CODES:
                    for amount in amounts:
                        self.assertEqual(convert(amount, src, dst), oracle_convert(amount, src, dst), (amount, src, dst))

        def test_same_currency_is_unchanged(self):
            for code in CODES:
                self.assertEqual(convert(12_345, code, code), 12_345)
                self.assertEqual(convert(0, code, code), 0)

        def test_rounds_down(self):
            # 1 cent of EUR in USD: 0.01 * 1.085 * 0.9975 = 0.0108 -> 1 cent ; 1 yen in EUR is far below a cent
            self.assertEqual(convert(1, "EUR", "USD"), 1)
            self.assertEqual(convert(1, "JPY", "EUR"), 0)
            self.assertEqual(convert(160, "JPY", "EUR"), 99)

        def test_minor_unit_digits(self):
            self.assertEqual(convert(10_000, "EUR", "KWD"), oracle_convert(10_000, "EUR", "KWD"))
            self.assertEqual(convert(1_000, "KWD", "EUR"), oracle_convert(1_000, "KWD", "EUR"))
            self.assertEqual(convert(5_000, "JPY", "KWD"), oracle_convert(5_000, "JPY", "KWD"))

        def test_errors(self):
            with self.assertRaises(ValueError):
                convert(100, "EUR", "XXX")
            with self.assertRaises(ValueError):
                convert(100, "XXX", "EUR")
            with self.assertRaises(ValueError):
                convert(-1, "EUR", "USD")
            with self.assertRaises(ValueError):
                convert(-1, "EUR", "EUR")
            with self.assertRaises(ValueError):
                convert(100, "usd", "USD")


    class Fee(unittest.TestCase):
        def test_minimum_and_maximum(self):
            for cur in CODES:
                self.assertEqual(fee(0, cur), FEE_MIN[cur], cur)
                self.assertEqual(fee(10 ** 9, cur), FEE_MAX[cur], cur)

        def test_percentage_rounds_up(self):
            # 0.5% of 100_001 = 500.005 -> 501 ; of 100_000 = 500 exactly
            self.assertEqual(fee(100_000, "EUR"), 500)
            self.assertEqual(fee(100_001, "EUR"), 501)
            self.assertEqual(fee(300_000, "EUR"), 1500)
            self.assertEqual(fee(300_001, "EUR"), 1501)

        def test_boundaries_with_min_and_max(self):
            self.assertEqual(fee(29_999, "EUR"), 150)
            self.assertEqual(fee(30_000, "EUR"), 150)
            self.assertEqual(fee(30_001, "EUR"), 151)
            self.assertEqual(fee(30_201, "EUR"), 152)
            self.assertEqual(fee(500_000, "EUR"), 2500)
            self.assertEqual(fee(499_999, "EUR"), 2500)
            self.assertEqual(fee(499_800, "EUR"), 2499)
            self.assertEqual(fee(400_000, "GBP"), 2000)
            self.assertEqual(fee(399_999, "GBP"), 2000)
            self.assertEqual(fee(399_000, "GBP"), 1995)

        def test_matches_formula(self):
            for cur in CODES:
                for amount in (0, 1, 999, 10_000, 25_000, 40_000, 80_001, 123_457, 400_000, 800_001, 5_000_000):
                    self.assertEqual(fee(amount, cur), oracle_fee(amount, cur), (amount, cur))

        def test_errors(self):
            with self.assertRaises(ValueError):
                fee(100, "XXX")
            with self.assertRaises(ValueError):
                fee(-100, "EUR")


    class Exchange(unittest.TestCase):
        def test_fee_first(self):
            r = exchange(10_000, "EUR", "USD")
            self.assertEqual(r["fee"], 150)
            self.assertEqual(r["converted"], oracle_convert(10_000 - 150, "EUR", "USD"))
            self.assertEqual(set(r), {"fee", "converted"})

        def test_formula_everywhere(self):
            for src in CODES:
                for dst in CODES:
                    for amount in (10_000, 123_456, 7_654_321):
                        r = exchange(amount, src, dst)
                        f = 0 if src == dst else oracle_fee(amount, src)
                        self.assertEqual(r, {"fee": f, "converted": oracle_convert(amount - f, src, dst)}, (amount, src, dst))

        def test_same_currency_has_no_fee(self):
            self.assertEqual(exchange(10_000, "USD", "USD"), {"fee": 0, "converted": 10_000})
            self.assertEqual(exchange(1, "JPY", "JPY"), {"fee": 0, "converted": 1})

        def test_amount_must_cover_fee(self):
            with self.assertRaises(ValueError):
                exchange(150, "EUR", "USD")
            with self.assertRaises(ValueError):
                exchange(0, "EUR", "USD")
            with self.assertRaises(ValueError):
                exchange(200, "JPY", "EUR")
            self.assertEqual(exchange(151, "EUR", "USD")["fee"], 150)
            self.assertEqual(exchange(201, "JPY", "EUR")["fee"], 200)

        def test_same_currency_zero(self):
            with self.assertRaises(ValueError):
                exchange(0, "EUR", "EUR")

        def test_errors(self):
            with self.assertRaises(ValueError):
                exchange(10_000, "EUR", "XXX")
            with self.assertRaises(ValueError):
                exchange(-5, "EUR", "USD")


    class Inverse(unittest.TestCase):
        def test_is_minimal_and_sufficient(self):
            for src, dst in (("EUR", "USD"), ("USD", "EUR"), ("EUR", "JPY"), ("JPY", "KWD"), ("GBP", "CHF"), ("KWD", "EUR")):
                for target in (1, 2, 99, 1000, 12_345, 250_000, 1_000_000):
                    amount = quote_inverse(target, src, dst)
                    self.assertGreaterEqual(exchange(amount, src, dst)["converted"], target, (src, dst, target))
                    if amount - 1 > fee(amount - 1, src):
                        self.assertLess(exchange(amount - 1, src, dst)["converted"], target, (src, dst, target))

        def test_known(self):
            self.assertEqual(quote_inverse(10_000, "EUR", "EUR"), 10_000)
            self.assertEqual(quote_inverse(1, "EUR", "EUR"), 1)
            self.assertEqual(quote_inverse(10_000, "EUR", "USD"), 9_390)
            self.assertGreaterEqual(exchange(9_390, "EUR", "USD")["converted"], 10_000)
            self.assertLess(exchange(9_389, "EUR", "USD")["converted"], 10_000)

        def test_errors(self):
            for target in (0, -5):
                with self.assertRaises(ValueError):
                    quote_inverse(target, "EUR", "USD")
            with self.assertRaises(ValueError):
                quote_inverse(10, "EUR", "XXX")


    class RoundTrip(unittest.TestCase):
        def test_loss(self):
            self.assertEqual(round_trip_loss(10_000, "EUR", "EUR"), 0)
            self.assertEqual(round_trip_loss(0, "EUR", "USD"), 0)
            for a, b in (("EUR", "USD"), ("EUR", "KWD"), ("JPY", "GBP")):
                for amount in (1_000, 54_321):
                    back = oracle_convert(oracle_convert(amount, a, b), b, a)
                    self.assertEqual(round_trip_loss(amount, a, b), amount - back, (a, b, amount))
                    self.assertGreaterEqual(round_trip_loss(amount, a, b), 0)

        def test_loss_reflects_margins(self):
            # EUR <-> KWD pays 120 bp on each leg: roughly 2.4% of 10 000 is lost
            loss = round_trip_loss(100_000, "EUR", "KWD")
            self.assertTrue(2_300 <= loss <= 2_500, loss)


    if __name__ == "__main__":
        unittest.main()
''')

FXDESK = Lib(
    name="fxdesk", lang="python", title="the bureau currency desk (`fxdesk/`)",
    blurb="The currency-exchange bureau quotes and books customer conversions with the fxdesk package.",
    files={"fxdesk/__init__.py": "", "fxdesk/tables.py": FXD_TABLES, "fxdesk/convert.py": FXD_CONVERT,
           "README.md": FXD_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": FXD_VISIBLE},
    hidden_tests={"tests/test_full.py": FXD_HIDDEN},
    mutate=["fxdesk/tables.py", "fxdesk/convert.py"], difficulty=3, tags=["currency", "rounding", "fees"],
    probes=[
        "convert(10_000, 'EUR', 'USD')", "convert(160, 'JPY', 'EUR')", "convert(1_000, 'KWD', 'EUR')", "convert(500, 'GBP', 'GBP')",
        "fee(100_001, 'EUR')", "fee(30_201, 'EUR')", "fee(499_800, 'EUR')", "fee(0, 'KWD')", "fee(399_000, 'GBP')",
        "exchange(10_000, 'EUR', 'USD')", "exchange(10_000, 'USD', 'USD')", "exchange(151, 'EUR', 'USD')",
        "quote_inverse(10_000, 'EUR', 'USD')", "quote_inverse(250_000, 'JPY', 'KWD')", "round_trip_loss(100_000, 'EUR', 'KWD')",
    ],
    probe_import="from fxdesk.convert import *",
)

register_libs([BILLNUM, FXDESK], n=10)
