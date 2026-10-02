"""Python libraries, theme time/money/scheduling (batch money-c): royalty statements for a record label."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# royaltyrun: royalty statements with channel fees, tiered rates on lifetime receipts, advance recoupment, reserves
# ======================================================================================================================

RR_README = dd('''
    # royaltyrun

    Royalty statements for a small record label. Money is `int` cents and rates are **basis points** (bp, a hundredth of a
    percent). "Rounded half up" means the exact value is rounded to the nearest cent, halves going up. No amount in this
    package is ever negative, except where a function says so.

    ## Receipts (`royaltyrun/receipts.py`)

    The label deducts a fee per sales channel before royalties are computed: `physical` 2500 bp, `download` 1500 bp,
    `stream` 0 bp and `sync` 500 bp.

    * `rnd(num, den)`: `num / den` rounded half up, for `num >= 0` and `den > 0`.
    * `fee_bp(channel)`: the fee of the channel in bp. An unknown channel is a `ValueError`.
    * `net_of(channel, gross)`: `gross` minus the fee, the fee being `gross * fee_bp(channel) / 10 000` rounded half up
      (for this one amount). A negative `gross` is a `ValueError`.
    * `net_receipts(lines)`: `lines` is a list of `(channel, gross)` pairs. Returns a dict from channel to the sum of the
      `net_of` values of its lines (every line is rounded on its own). Only channels that occur are in it, in order of
      their first occurrence.
    * `total_net(lines)`: the sum of all the net receipts of `lines` (`0` for no lines).

    An unknown channel or a negative gross amount is a `ValueError` in all of these functions and in the statement methods
    below that use them.

    ## Terms (`royaltyrun/terms.py`)

    The royalty rate depends on the artist's **lifetime net receipts**, the net receipts of all earlier statements, and it
    applies to slices like tax bands do: net receipts up to 1 000 000 cents earn 1000 bp, the part between 1 000 000 and
    5 000 000 cents earns 1200 bp, and everything above 5 000 000 cents earns 1500 bp.

    * `tier_slices(lifetime_before, net)`: the `net` receipts move the lifetime total from `lifetime_before` to
      `lifetime_before + net`; the result is `[(rate_bp, amount), ...]`, the amount of that movement that falls into each
      tier, lowest tier first, tiers with nothing in them left out. A negative argument is a `ValueError`.
    * `royalty_on(lifetime_before, net)`: the royalty earned, that is `rate_bp * amount` summed over the slices, divided
      by 10 000 and rounded half up **once** (not slice by slice).
    * `split_payment(amount, shares)`: `shares` maps payee names to basis points. The shares must be positive and add up
      to exactly 10 000, and `amount` must not be negative; otherwise (also for an empty `shares`) it is a `ValueError`.
      Every payee gets `amount * share // 10 000`; the cents still missing go one each to the payees with the largest
      remainder `amount * share % 10 000`, a tie going to the payee that comes first in `shares`. Returns a dict in the
      order of `shares`.

    ## Statements (`royaltyrun/statement.py`)

    An `Account(advance=0, shares=None)` carries the state from one statement to the next. A negative `advance` is a
    `ValueError`. `shares` is the payee split used for `payouts` below (or `None`).

    `account.close_period(label, lines)` makes one statement and returns a `Statement` namedtuple with the fields
    `label, net, earned, recouped, withheld, released, carried_in, paid, carried_out, lifetime, unrecouped, payouts` (in
    this order), worked out as follows:

    1. `net` is `total_net(lines)` and `earned` is `royalty_on(lifetime so far, net)`. The lifetime total then grows by
       `net`; `lifetime` is the new total.
    2. The royalty pays back the advance first: `recouped = min(advance still unrecouped, earned)`. `unrecouped` is the
       advance still open afterwards and `available = earned - recouped`.
    3. A reserve against returns: 10% (1000 bp) of `available`, rounded half up, is `withheld`. The reserve withheld on a
       statement is `released` (added to what is paid) on the statement **two statements later**; on the first two
       statements `released` is 0.
    4. `carried_in` is the amount carried forward by the previous statement (0 on the first). The amount due is
       `available - withheld + released + carried_in`.
    5. If the amount due is below 2500 cents nothing is paid (`paid` is 0) and it is carried forward (`carried_out` is the
       amount due). Otherwise `paid` is the amount due and `carried_out` is 0.
    6. `payouts` is `tuple(split_payment(paid, shares).items())` when the account has `shares` and `paid` is above 0, and
       the empty tuple otherwise.

    `account.wind_up(label)` closes the contract and returns a `Statement` with `net`, `earned`, `recouped` and
    `withheld` all 0 and `carried_out` 0. All the reserves still held are released at once: `released` is their sum,
    `carried_in` is the carried-forward amount, and `paid` is their sum however small it is. `lifetime` and `unrecouped`
    are the current ones and `payouts` is made as in step 6. Afterwards the account holds no reserve and no carried
    amount.

    `run_statements(periods, advance=0, shares=None)`: makes an `Account` and closes every `(label, lines)` pair of
    `periods` in order; returns the list of statements.

    `money(cents)` formats an amount as `1,234.50`: thousands separated by commas, two decimals, and a leading `-` for a
    negative amount (`-5` gives `-0.05`).

    `render(statement)` returns the text of a statement, lines joined by `"\\n"` without a trailing newline: the first line
    is `Statement ` followed by the label; then one line per row below, made of the row name left-justified to 20
    characters and the amount (through `money`) right-justified to 14 characters:
    `Net receipts` (net), `Royalty earned` (earned), `Advance recouped` (minus `recouped`), `Reserve withheld` (minus
    `withheld`), `Reserve released` (released), `Carried in` (carried_in), `Paid` (paid), `Carried forward`
    (carried_out) and `Unrecouped advance` (unrecouped).
''')

RR_RECEIPTS = dd('''
    FEE_BP = {"physical": 2500, "download": 1500, "stream": 0, "sync": 500}


    def rnd(num, den):
        return (2 * num + den) // (2 * den)


    def fee_bp(channel):
        if channel not in FEE_BP:
            raise ValueError("unknown channel: " + repr(channel))
        return FEE_BP[channel]


    def net_of(channel, gross):
        if gross < 0:
            raise ValueError("gross receipts must not be negative")
        return gross - rnd(gross * fee_bp(channel), 10_000)


    def net_receipts(lines):
        out = {}
        for channel, gross in lines:
            out[channel] = out.get(channel, 0) + net_of(channel, gross)
        return out


    def total_net(lines):
        return sum(net_receipts(lines).values())
''')

RR_TERMS = dd('''
    from .receipts import rnd

    TIERS = ((1_000_000, 1000), (5_000_000, 1200), (None, 1500))
    MIN_PAYOUT = 2500
    RESERVE_BP = 1000


    def tier_slices(lifetime_before, net):
        if lifetime_before < 0 or net < 0:
            raise ValueError("receipts must not be negative")
        slices = []
        low, high = lifetime_before, lifetime_before + net
        prev = 0
        for limit, bp in TIERS:
            top = high if limit is None else min(limit, high)
            start = max(prev, low)
            if top > start:
                slices.append((bp, top - start))
            prev = limit
        return slices


    def royalty_on(lifetime_before, net):
        return rnd(sum(bp * amount for bp, amount in tier_slices(lifetime_before, net)), 10_000)


    def split_payment(amount, shares):
        if amount < 0 or not shares or sum(shares.values()) != 10_000 or min(shares.values()) <= 0:
            raise ValueError("bad payment or shares")
        names = list(shares)
        paid = dict((name, amount * shares[name] // 10_000) for name in names)
        missing = amount - sum(paid.values())
        order = sorted(range(len(names)), key=lambda i: (-(amount * shares[names[i]] % 10_000), i))
        for i in order[:missing]:
            paid[names[i]] += 1
        return paid
''')

RR_STATEMENT = dd('''
    from collections import namedtuple

    from .receipts import rnd, total_net
    from .terms import MIN_PAYOUT, RESERVE_BP, royalty_on, split_payment

    Statement = namedtuple(
        "Statement", "label net earned recouped withheld released carried_in paid carried_out lifetime unrecouped payouts")


    class Account:
        def __init__(self, advance=0, shares=None):
            if advance < 0:
                raise ValueError("the advance must not be negative")
            self.lifetime = 0
            self.unrecouped = advance
            self.reserves = []
            self.carried = 0
            self.shares = shares

        def _payouts(self, paid):
            if self.shares and paid > 0:
                return tuple(split_payment(paid, self.shares).items())
            return ()

        def close_period(self, label, lines):
            net = total_net(lines)
            earned = royalty_on(self.lifetime, net)
            self.lifetime += net
            recouped = min(self.unrecouped, earned)
            self.unrecouped -= recouped
            available = earned - recouped
            released = self.reserves.pop(0) if len(self.reserves) == 2 else 0
            withheld = rnd(available * RESERVE_BP, 10_000)
            self.reserves.append(withheld)
            carried_in = self.carried
            due = available - withheld + released + carried_in
            if due < MIN_PAYOUT:
                paid, self.carried = 0, due
            else:
                paid, self.carried = due, 0
            return Statement(label, net, earned, recouped, withheld, released, carried_in, paid, self.carried,
                             self.lifetime, self.unrecouped, self._payouts(paid))

        def wind_up(self, label):
            released = sum(self.reserves)
            carried_in = self.carried
            self.reserves = []
            self.carried = 0
            paid = released + carried_in
            return Statement(label, 0, 0, 0, 0, released, carried_in, paid, 0, self.lifetime, self.unrecouped,
                             self._payouts(paid))


    def run_statements(periods, advance=0, shares=None):
        account = Account(advance, shares)
        return [account.close_period(label, lines) for label, lines in periods]


    def money(cents):
        sign = "-" if cents < 0 else ""
        whole, frac = divmod(abs(cents), 100)
        return "%s%s.%02d" % (sign, format(whole, ","), frac)


    def render(st):
        rows = [("Net receipts", st.net), ("Royalty earned", st.earned), ("Advance recouped", -st.recouped),
                ("Reserve withheld", -st.withheld), ("Reserve released", st.released), ("Carried in", st.carried_in),
                ("Paid", st.paid), ("Carried forward", st.carried_out), ("Unrecouped advance", st.unrecouped)]
        return "\\n".join(["Statement " + st.label] + [name.ljust(20) + money(value).rjust(14) for name, value in rows])
''')

RR_VISIBLE = dd('''
    import unittest

    from royaltyrun.receipts import net_of
    from royaltyrun.statement import money, run_statements
    from royaltyrun.terms import royalty_on


    class BasicTests(unittest.TestCase):
        def test_net_of(self):
            self.assertEqual(net_of("download", 1000), 850)

        def test_royalty_in_the_first_tier(self):
            self.assertEqual(royalty_on(0, 400_000), 40_000)

        def test_money(self):
            self.assertEqual(money(123_456), "1,234.56")

        def test_one_statement(self):
            st = run_statements([("Q1", [("stream", 100_000)])])[0]
            self.assertEqual((st.net, st.earned, st.withheld, st.paid), (100_000, 10_000, 1000, 9000))


    if __name__ == "__main__":
        unittest.main()
''')

RR_HIDDEN = dd('''
    import unittest
    from fractions import Fraction

    from royaltyrun.receipts import fee_bp, net_of, net_receipts, rnd, total_net
    from royaltyrun.statement import Account, money, render, run_statements
    from royaltyrun.terms import royalty_on, split_payment, tier_slices

    Q1 = [("stream", 400_000), ("download", 200_000), ("physical", 300_000), ("sync", 100_000)]
    SHARES = {"band": 7000, "label_fund": 2000, "mgr": 1000}
    PERIODS = [("Q1", Q1), ("Q2", [("stream", 100_000)]), ("Q3", [("stream", 50_000), ("sync", 20_000)]),
               ("Q4", [("download", 10_000)]), ("Q5", Q1 + Q1 + Q1)]


    def stream(*amounts):
        return [("stream", a) for a in amounts]


    class Receipts(unittest.TestCase):
        def test_rnd(self):
            table = {(1, 2): 1, (1, 3): 0, (2, 3): 1, (5, 10): 1, (4, 10): 0, (0, 7): 0, (3, 2): 2, (7, 2): 4, (14_999, 10_000): 1,
                     (15_000, 10_000): 2}
            for (num, den), want in table.items():
                self.assertEqual(rnd(num, den), want, (num, den))

        def test_fees(self):
            self.assertEqual([fee_bp(c) for c in ("physical", "download", "stream", "sync")], [2500, 1500, 0, 500])
            for channel in ("vinyl", "", "radio"):
                with self.assertRaises(ValueError):
                    fee_bp(channel)

        def test_net_of(self):
            table = {("download", 3): 3, ("download", 4): 3, ("sync", 10): 9, ("sync", 9): 9, ("sync", 11): 10, ("physical", 3): 2,
                     ("physical", 2): 1, ("stream", 7): 7, ("physical", 0): 0, ("download", 1000): 850, ("physical", 10_001): 7501}
            for (channel, gross), want in table.items():
                self.assertEqual(net_of(channel, gross), want, (channel, gross))

        def test_net_of_errors(self):
            with self.assertRaises(ValueError):
                net_of("stream", -1)
            with self.assertRaises(ValueError):
                net_of("vinyl", 10)

        def test_net_receipts(self):
            self.assertEqual(net_receipts(Q1), {"stream": 400_000, "download": 170_000, "physical": 225_000, "sync": 95_000})
            self.assertEqual(net_receipts([]), {})

        def test_every_line_is_rounded_on_its_own(self):
            self.assertEqual(net_receipts([("download", 4), ("download", 4)]), {"download": 6})
            self.assertEqual(net_receipts([("sync", 100), ("stream", 5), ("sync", 100), ("physical", 4)]),
                             {"sync": 190, "stream": 5, "physical": 3})

        def test_channels_come_in_order_of_first_occurrence(self):
            got = net_receipts([("sync", 1), ("stream", 1), ("physical", 1), ("stream", 1), ("sync", 1)])
            self.assertEqual(list(got), ["sync", "stream", "physical"])

        def test_total_net(self):
            self.assertEqual(total_net(Q1), 890_000)
            self.assertEqual(total_net([]), 0)
            self.assertEqual(total_net([("download", 4), ("download", 4)]), 6)


    class Tiers(unittest.TestCase):
        def test_slices(self):
            table = {
                (0, 1_000_000): [(1000, 1_000_000)],
                (0, 1_000_001): [(1000, 1_000_000), (1200, 1)],
                (900_000, 200_000): [(1000, 100_000), (1200, 100_000)],
                (900_000, 5_000_000): [(1000, 100_000), (1200, 4_000_000), (1500, 900_000)],
                (4_999_999, 2): [(1200, 1), (1500, 1)],
                (6_000_000, 1000): [(1500, 1000)],
                (0, 0): [],
                (1_000_000, 1): [(1200, 1)],
                (5_000_000, 1): [(1500, 1)],
                (2_000_000, 500_000): [(1200, 500_000)],
                (0, 6_000_000): [(1000, 1_000_000), (1200, 4_000_000), (1500, 1_000_000)],
            }
            for (before, net), want in table.items():
                self.assertEqual(tier_slices(before, net), want, (before, net))

        def test_errors(self):
            for args in ((-1, 5), (5, -1), (-3, -3)):
                with self.assertRaises(ValueError):
                    tier_slices(*args)
                with self.assertRaises(ValueError):
                    royalty_on(*args)


    class Royalty(unittest.TestCase):
        def test_values(self):
            table = {(0, 1_000_000): 100_000, (900_000, 200_000): 22_000, (900_000, 5_000_000): 625_000, (6_000_000, 1000): 150,
                     (0, 0): 0, (1_000_000, 1): 0, (2_000_000, 100_000): 12_000}
            for (before, net), want in table.items():
                self.assertEqual(royalty_on(before, net), want, (before, net))

        def test_half_up(self):
            self.assertEqual([royalty_on(0, n) for n in (4, 5, 14, 15)], [0, 1, 1, 2])
            self.assertEqual([royalty_on(1_000_000, n) for n in (4, 5, 6, 8, 9)], [0, 1, 1, 1, 1])

        def test_rounded_once_not_per_slice(self):
            self.assertEqual(royalty_on(999_995, 10), 1)
            self.assertEqual(royalty_on(4_999_995, 10), 1)

        def test_matches_the_exact_rule(self):
            bands = ((0, 1_000_000, 1000), (1_000_000, 5_000_000, 1200), (5_000_000, 10 ** 12, 1500))
            for before in (0, 999_990, 1_000_000, 4_999_990, 5_000_000, 7_000_000):
                for net in (0, 1, 5, 9, 10, 15, 19, 20, 25, 1000, 10_000, 4_100_000):
                    exact = sum(Fraction(max(0, min(hi, before + net) - max(lo, before)) * rate, 10_000) for lo, hi, rate in bands)
                    want = int(exact + Fraction(1, 2)) if exact >= 0 else 0
                    self.assertEqual(royalty_on(before, net), want, (before, net))


    class Split(unittest.TestCase):
        def test_exact(self):
            self.assertEqual(split_payment(1000, {"a": 7000, "b": 3000}), {"a": 700, "b": 300})
            self.assertEqual(split_payment(5, {"solo": 10_000}), {"solo": 5})
            self.assertEqual(split_payment(0, {"a": 3333, "b": 6667}), {"a": 0, "b": 0})

        def test_largest_remainder(self):
            self.assertEqual(split_payment(10, {"a": 3333, "b": 3333, "c": 3334}), {"a": 3, "b": 3, "c": 4})
            self.assertEqual(split_payment(100, {"a": 3334, "b": 3333, "c": 3333}), {"a": 34, "b": 33, "c": 33})
            self.assertEqual(split_payment(5, {"a": 5500, "b": 2500, "c": 2000}), {"a": 3, "b": 1, "c": 1})

        def test_ties_go_to_the_earlier_payee(self):
            self.assertEqual(split_payment(101, {"a": 5000, "b": 5000}), {"a": 51, "b": 50})
            self.assertEqual(split_payment(7, {"a": 2500, "b": 2500, "c": 2500, "d": 2500}), {"a": 2, "b": 2, "c": 2, "d": 1})
            self.assertEqual(split_payment(101, {"z": 5000, "a": 5000}), {"z": 51, "a": 50})

        def test_order_of_the_result(self):
            self.assertEqual(list(split_payment(100, {"z": 2000, "a": 3000, "m": 5000})), ["z", "a", "m"])

        def test_the_parts_add_up(self):
            shares = {"a": 3333, "b": 3333, "c": 3334}
            for amount in range(0, 70):
                got = split_payment(amount, shares)
                self.assertEqual(sum(got.values()), amount)
                for name, share in shares.items():
                    self.assertIn(got[name] - amount * share // 10_000, (0, 1))

        def test_errors(self):
            bad = [(100, {}), (100, {"a": 5000, "b": 4999}), (100, {"a": 5000, "b": 5001}), (100, {"a": 10_000, "b": 0}),
                   (100, {"a": 11_000, "b": -1000}), (-1, {"a": 10_000})]
            for amount, shares in bad:
                with self.assertRaises(ValueError, msg=(amount, shares)):
                    split_payment(amount, shares)


    class Statements(unittest.TestCase):
        def test_five_statements(self):
            got = run_statements(PERIODS, advance=60_000, shares=SHARES)
            want = [
                ("Q1", 890_000, 89_000, 60_000, 2900, 0, 0, 26_100, 0, 890_000, 0,
                 (("band", 18_270), ("label_fund", 5220), ("mgr", 2610))),
                ("Q2", 100_000, 10_000, 0, 1000, 0, 0, 9000, 0, 990_000, 0, (("band", 6300), ("label_fund", 1800), ("mgr", 900))),
                ("Q3", 69_000, 8080, 0, 808, 2900, 0, 10_172, 0, 1_059_000, 0,
                 (("band", 7121), ("label_fund", 2034), ("mgr", 1017))),
                ("Q4", 8500, 1020, 0, 102, 1000, 0, 0, 1918, 1_067_500, 0, ()),
                ("Q5", 2_670_000, 320_400, 0, 32_040, 808, 1918, 291_086, 0, 3_737_500, 0,
                 (("band", 203_760), ("label_fund", 58_217), ("mgr", 29_109))),
            ]
            self.assertEqual(len(got), 5)
            for st, row in zip(got, want):
                self.assertEqual(tuple(st), row, row[0])

        def test_fields_by_name(self):
            st = run_statements(PERIODS[:1], advance=60_000)[0]
            self.assertEqual((st.label, st.net, st.earned, st.recouped, st.withheld, st.released), ("Q1", 890_000, 89_000, 60_000, 2900, 0))
            self.assertEqual((st.carried_in, st.paid, st.carried_out, st.lifetime, st.unrecouped, st.payouts), (0, 26_100, 0, 890_000, 0, ()))

        def test_without_shares_there_are_no_payouts(self):
            for st in run_statements(PERIODS, advance=60_000):
                self.assertEqual(st.payouts, ())

        def test_reserve_comes_back_two_statements_later(self):
            got = run_statements([("S%d" % i, stream(20_000)) for i in range(1, 6)])
            self.assertEqual([st.withheld for st in got], [200] * 5)
            self.assertEqual([st.released for st in got], [0, 0, 200, 200, 200])

        def test_small_amounts_are_carried(self):
            got = run_statements([("S%d" % i, stream(20_000)) for i in range(1, 6)])
            self.assertEqual([st.paid for st in got], [0, 3600, 0, 4000, 0])
            self.assertEqual([st.carried_in for st in got], [0, 1800, 0, 2000, 0])
            self.assertEqual([st.carried_out for st in got], [1800, 0, 2000, 0, 2000])

        def test_the_minimum_payout(self):
            for gross, paid, carried in ((27_770, 0, 2499), (27_780, 2500, 0), (27_790, 2501, 0)):
                st = run_statements([("S", stream(gross))])[0]
                self.assertEqual((st.paid, st.carried_out), (paid, carried), gross)

        def test_a_large_advance_is_recouped_over_several_statements(self):
            got = run_statements([(x, stream(300_000)) for x in "abcd"], advance=100_000)
            self.assertEqual([st.recouped for st in got], [30_000, 30_000, 30_000, 10_000])
            self.assertEqual([st.unrecouped for st in got], [70_000, 40_000, 10_000, 0])
            self.assertEqual([st.earned for st in got], [30_000, 30_000, 30_000, 34_000])
            self.assertEqual([st.paid for st in got], [0, 0, 0, 21_600])
            self.assertEqual([st.withheld for st in got], [0, 0, 0, 2400])

        def test_tiers_follow_the_lifetime_total(self):
            got = run_statements([("a", stream(900_000)), ("b", stream(200_000)), ("c", stream(4_000_000)), ("d", stream(1000))])
            self.assertEqual([st.earned for st in got], [90_000, 22_000, 483_000, 150])
            self.assertEqual([st.lifetime for st in got], [900_000, 1_100_000, 5_100_000, 5_101_000])
            self.assertEqual([st.paid for st in got], [81_000, 19_800, 443_700, 0])
            self.assertEqual([st.carried_out for st in got], [0, 0, 0, 2335])

        def test_payouts_only_when_something_is_paid(self):
            account = Account(0, {"x": 5000, "y": 5000})
            first = account.close_period("1", stream(20_000))
            second = account.close_period("2", stream(20_000))
            self.assertEqual((first.paid, first.payouts), (0, ()))
            self.assertEqual((second.paid, second.payouts), (3600, (("x", 1800), ("y", 1800))))

        def test_the_account_keeps_its_state(self):
            account = Account(advance=1000)
            one = account.close_period("1", stream(10_000))
            two = account.close_period("2", stream(10_000))
            self.assertEqual((one.recouped, one.unrecouped, one.lifetime), (1000, 0, 10_000))
            self.assertEqual((two.recouped, two.unrecouped, two.lifetime), (0, 0, 20_000))

        def test_errors(self):
            with self.assertRaises(ValueError):
                Account(advance=-1)
            with self.assertRaises(ValueError):
                run_statements([], advance=-5)
            with self.assertRaises(ValueError):
                Account().close_period("x", [("vinyl", 5)])
            self.assertEqual(run_statements([]), [])


    class WindUp(unittest.TestCase):
        def test_everything_is_paid(self):
            account = Account(0, {"x": 5000, "y": 5000})
            for label in "123":
                account.close_period(label, stream(20_000))
            end = account.wind_up("end")
            self.assertEqual(tuple(end), ("end", 0, 0, 0, 0, 400, 2000, 2400, 0, 60_000, 0, (("x", 1200), ("y", 1200))))

        def test_nothing_is_left_afterwards(self):
            account = Account()
            for label in "123":
                account.close_period(label, stream(20_000))
            account.wind_up("end")
            again = account.wind_up("again")
            self.assertEqual(tuple(again), ("again", 0, 0, 0, 0, 0, 0, 0, 0, 60_000, 0, ()))

        def test_small_amounts_are_paid_anyway(self):
            account = Account()
            account.close_period("1", stream(20_000))
            end = account.wind_up("end")
            self.assertEqual((end.released, end.carried_in, end.paid), (200, 1800, 2000))

        def test_the_open_advance_stays_on_the_statement(self):
            account = Account(50_000)
            account.close_period("1", stream(100_000))
            end = account.wind_up("end")
            self.assertEqual(tuple(end), ("end", 0, 0, 0, 0, 0, 0, 0, 0, 100_000, 40_000, ()))


    class Text(unittest.TestCase):
        def test_money(self):
            table = {0: "0.00", 5: "0.05", -5: "-0.05", 100: "1.00", 123_456: "1,234.56", -123_456_789: "-1,234,567.89",
                     99_999_999: "999,999.99", 99_900: "999.00", 100_000: "1,000.00", 999: "9.99"}
            for cents, text in table.items():
                self.assertEqual(money(cents), text, cents)

        def test_render(self):
            got = run_statements(PERIODS, advance=60_000, shares=SHARES)
            self.assertEqual(render(got[0]), "\\n".join([
                "Statement Q1",
                "Net receipts              8,900.00",
                "Royalty earned              890.00",
                "Advance recouped           -600.00",
                "Reserve withheld            -29.00",
                "Reserve released              0.00",
                "Carried in                    0.00",
                "Paid                        261.00",
                "Carried forward               0.00",
                "Unrecouped advance            0.00"]))
            self.assertEqual(render(got[3]), "\\n".join([
                "Statement Q4",
                "Net receipts                 85.00",
                "Royalty earned               10.20",
                "Advance recouped              0.00",
                "Reserve withheld             -1.02",
                "Reserve released             10.00",
                "Carried in                    0.00",
                "Paid                          0.00",
                "Carried forward              19.18",
                "Unrecouped advance            0.00"]))


    if __name__ == "__main__":
        unittest.main()
''')

ROYALTYRUN = Lib(
    name="royaltyrun", lang="python", title="the royalty statement engine (`royaltyrun/`)",
    blurb="The label settles with its artists every quarter, recouping advances and holding reserves, using royaltyrun.",
    files={"royaltyrun/__init__.py": "", "royaltyrun/receipts.py": RR_RECEIPTS, "royaltyrun/terms.py": RR_TERMS,
           "royaltyrun/statement.py": RR_STATEMENT, "README.md": RR_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": RR_VISIBLE},
    hidden_tests={"tests/test_full.py": RR_HIDDEN},
    mutate=["royaltyrun/receipts.py", "royaltyrun/terms.py", "royaltyrun/statement.py"], difficulty=4,
    tags=["royalties", "tiers", "recoupment", "rounding"],
    probes=[
        "rnd(5, 10)", "net_of('physical', 2)", "net_of('sync', 10)", "net_receipts([('download', 4), ('download', 4)])",
        "total_net([('stream', 400_000), ('download', 200_000), ('physical', 300_000), ('sync', 100_000)])",
        "tier_slices(900_000, 200_000)", "tier_slices(4_999_999, 2)", "tier_slices(0, 6_000_000)", "royalty_on(999_995, 10)",
        "royalty_on(0, 5)", "royalty_on(900_000, 5_000_000)", "royalty_on(5_000_000, 1000)",
        "split_payment(10, {'a': 3333, 'b': 3333, 'c': 3334})", "split_payment(101, {'a': 5000, 'b': 5000})",
        "split_payment(5, {'a': 5500, 'b': 2500, 'c': 2000})", "split_payment(7, {'a': 2500, 'b': 2500, 'c': 2500, 'd': 2500})",
        "run_statements([('Q1', [('stream', 400_000), ('download', 200_000)]), ('Q2', [('stream', 100_000)])], advance=60_000)",
        "[st.released for st in run_statements([('S%d' % i, [('stream', 20_000)]) for i in range(1, 6)])]",
        "[st.paid for st in run_statements([('S%d' % i, [('stream', 20_000)]) for i in range(1, 6)])]",
        "[st.paid for st in run_statements([('S', [('stream', g)]) for g in (27_770, 27_780, 27_790)])]",
        "[st.unrecouped for st in run_statements([(x, [('stream', 300_000)]) for x in 'abcd'], advance=100_000)]",
        "run_statements([('a', [('stream', 4_000_000)]), ('b', [('stream', 1_000_000)])], shares={'x': 5000, 'y': 5000})[1].payouts",
        "money(-5)", "money(123_456_789)", "render(run_statements([('Q4', [('download', 10_000)])])[0])",
    ],
    probe_import="from royaltyrun.receipts import *\nfrom royaltyrun.terms import *\nfrom royaltyrun.statement import *",
)

register_libs([ROYALTYRUN], n=10)
