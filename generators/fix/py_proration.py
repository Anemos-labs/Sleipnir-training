"""Seat-based invoice proration (python): bugs injected into a small billing library."""
from fx import Lib, dd, register_libs

README = dd('''
    # billing.proration

    Small helpers a subscription-billing service uses to charge part of a billing period. All money is an `int`
    number of cents; never use floats for money.

    A *period* is a half-open range of dates `[start, end)`: `start` is included, `end` is not.

    ## `days_between(start, end) -> int`
    Number of days in `[start, end)`. `ValueError` if `end < start`. Equal dates give `0`.

    ## `prorate(amount_cents, used_start, used_end, period_start, period_end) -> int`
    The part of `amount_cents` that belongs to the used range `[used_start, used_end)` within the billing period
    `[period_start, period_end)`.

    * The used range is clamped to the period; a range that does not overlap the period costs `0`.
    * An empty period (`period_start == period_end`) is a `ValueError`; so is `period_end < period_start`.
    * Rounding is *half up* to the nearest cent, using integer arithmetic only.
    * Negative amounts (credits) are prorated by magnitude and keep their sign: `prorate(-100, ...)` is the
      negative of `prorate(100, ...)`.

    ## `split_evenly(total_cents, parts) -> list[int]`
    Split a total into `parts` integer amounts that add up to exactly `total_cents`. Remainder cents go one each to
    the *first* entries. `parts < 1` is a `ValueError`. A negative total is split by magnitude and negated, so the
    first entries still carry the larger magnitude: `split_evenly(-10, 3) == [-4, -3, -3]`.

    ## `seat_days_charge(price_cents, seat_log, period_start, period_end) -> int`
    Charge for a per-seat monthly price when the number of seats changes during the period. `seat_log` is a list
    of `(date, seats)` events, in any order; from an event's date until the next event the seat count is `seats`.
    Before the first event there are `0` seats. The charge is

        price_cents * (sum of seats over every day in the period) / (days in the period)

    rounded half up *once*, at the end. An empty period is a `ValueError`.
''')

SRC = dd('''
    from datetime import date, timedelta


    def days_between(start: date, end: date) -> int:
        if end < start:
            raise ValueError("end is before start")
        return (end - start).days


    def _round_div(n: int, d: int) -> int:
        """n / d rounded half up, for n >= 0 and d > 0."""
        return (2 * n + d) // (2 * d)


    def prorate(amount_cents: int, used_start: date, used_end: date, period_start: date, period_end: date) -> int:
        total = days_between(period_start, period_end)
        if total == 0:
            raise ValueError("empty billing period")
        lo = max(used_start, period_start)
        hi = min(used_end, period_end)
        if hi <= lo:
            return 0
        used = days_between(lo, hi)
        sign = -1 if amount_cents < 0 else 1
        return sign * _round_div(abs(amount_cents) * used, total)


    def split_evenly(total_cents: int, parts: int) -> list:
        if parts < 1:
            raise ValueError("parts must be at least 1")
        sign = -1 if total_cents < 0 else 1
        base, rem = divmod(abs(total_cents), parts)
        out = []
        for i in range(parts):
            out.append(sign * (base + (1 if i < rem else 0)))
        return out


    def seat_days_charge(price_cents: int, seat_log: list, period_start: date, period_end: date) -> int:
        total = days_between(period_start, period_end)
        if total == 0:
            raise ValueError("empty billing period")
        events = sorted(seat_log)
        seat_days = 0
        seats = 0
        idx = 0
        day = period_start
        while day < period_end:
            while idx < len(events) and events[idx][0] <= day:
                seats = events[idx][1]
                idx += 1
            seat_days += seats
            day += timedelta(days=1)
        return _round_div(price_cents * seat_days, total)
''')

VISIBLE = dd('''
    import unittest
    from datetime import date

    from billing.proration import days_between, prorate, split_evenly


    class BasicTests(unittest.TestCase):
        def test_days_between(self):
            self.assertEqual(days_between(date(2025, 3, 1), date(2025, 4, 1)), 31)

        def test_prorate_half_month(self):
            self.assertEqual(prorate(3000, date(2025, 3, 1), date(2025, 3, 16), date(2025, 3, 1), date(2025, 3, 31)), 1500)

        def test_split_simple(self):
            self.assertEqual(split_evenly(9, 3), [3, 3, 3])


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd('''
    import unittest
    from datetime import date

    from billing.proration import days_between, prorate, seat_days_charge, split_evenly

    D = date


    class DaysBetween(unittest.TestCase):
        def test_values(self):
            self.assertEqual(days_between(D(2024, 2, 1), D(2024, 3, 1)), 29)
            self.assertEqual(days_between(D(2025, 2, 1), D(2025, 3, 1)), 28)
            self.assertEqual(days_between(D(2025, 5, 5), D(2025, 5, 5)), 0)
            self.assertEqual(days_between(D(2025, 5, 5), D(2025, 5, 6)), 1)

        def test_backwards(self):
            with self.assertRaises(ValueError):
                days_between(D(2025, 5, 6), D(2025, 5, 5))


    class Prorate(unittest.TestCase):
        P = (D(2025, 6, 1), D(2025, 7, 1))  # 30 days

        def pr(self, amount, a, b):
            return prorate(amount, a, b, *self.P)

        def test_full_period(self):
            self.assertEqual(self.pr(999, D(2025, 6, 1), D(2025, 7, 1)), 999)

        def test_one_day(self):
            self.assertEqual(self.pr(3000, D(2025, 6, 10), D(2025, 6, 11)), 100)

        def test_rounding_half_up(self):
            # 15 / 30 of 5 cents is 2.5 -> 3
            self.assertEqual(self.pr(5, D(2025, 6, 1), D(2025, 6, 16)), 3)
            # 10 / 30 of 10 cents is 3.33 -> 3
            self.assertEqual(self.pr(10, D(2025, 6, 1), D(2025, 6, 11)), 3)
            # 20 / 30 of 10 cents is 6.67 -> 7
            self.assertEqual(self.pr(10, D(2025, 6, 1), D(2025, 6, 21)), 7)
            # 1 / 30 of 14 is 0.47 -> 0 ; 1 / 30 of 15 is 0.5 -> 1
            self.assertEqual(self.pr(14, D(2025, 6, 1), D(2025, 6, 2)), 0)
            self.assertEqual(self.pr(15, D(2025, 6, 1), D(2025, 6, 2)), 1)

        def test_clamped_to_period(self):
            self.assertEqual(self.pr(3000, D(2025, 5, 1), D(2025, 6, 11)), 1000)
            self.assertEqual(self.pr(3000, D(2025, 6, 21), D(2025, 9, 1)), 1000)
            self.assertEqual(self.pr(3000, D(2025, 1, 1), D(2026, 1, 1)), 3000)

        def test_no_overlap(self):
            self.assertEqual(self.pr(3000, D(2025, 5, 1), D(2025, 6, 1)), 0)
            self.assertEqual(self.pr(3000, D(2025, 7, 1), D(2025, 8, 1)), 0)
            self.assertEqual(self.pr(3000, D(2025, 6, 10), D(2025, 6, 10)), 0)
            self.assertEqual(self.pr(3000, D(2025, 6, 20), D(2025, 6, 10)), 0)

        def test_credits_keep_sign(self):
            self.assertEqual(self.pr(-3000, D(2025, 6, 1), D(2025, 6, 11)), -1000)
            self.assertEqual(self.pr(-5, D(2025, 6, 1), D(2025, 6, 16)), -3)
            self.assertEqual(self.pr(-14, D(2025, 6, 1), D(2025, 6, 2)), 0)
            self.assertEqual(self.pr(0, D(2025, 6, 1), D(2025, 6, 16)), 0)

        def test_bad_period(self):
            with self.assertRaises(ValueError):
                prorate(100, D(2025, 6, 1), D(2025, 6, 2), D(2025, 6, 1), D(2025, 6, 1))
            with self.assertRaises(ValueError):
                prorate(100, D(2025, 6, 1), D(2025, 6, 2), D(2025, 7, 1), D(2025, 6, 1))

        def test_leap_february(self):
            self.assertEqual(prorate(2900, D(2024, 2, 1), D(2024, 2, 11), D(2024, 2, 1), D(2024, 3, 1)), 1000)


    class SplitEvenly(unittest.TestCase):
        def test_exact(self):
            self.assertEqual(split_evenly(12, 4), [3, 3, 3, 3])

        def test_remainder_goes_first(self):
            self.assertEqual(split_evenly(10, 3), [4, 3, 3])
            self.assertEqual(split_evenly(11, 3), [4, 4, 3])
            self.assertEqual(split_evenly(1, 4), [1, 0, 0, 0])

        def test_sum_preserved(self):
            for total in range(0, 40):
                for parts in range(1, 9):
                    got = split_evenly(total, parts)
                    self.assertEqual(len(got), parts)
                    self.assertEqual(sum(got), total)
                    self.assertLessEqual(max(got) - min(got), 1)
                    self.assertEqual(got, sorted(got, reverse=True))

        def test_negative(self):
            self.assertEqual(split_evenly(-10, 3), [-4, -3, -3])
            self.assertEqual(split_evenly(-1, 3), [-1, 0, 0])
            self.assertEqual(split_evenly(-9, 3), [-3, -3, -3])

        def test_zero_and_single(self):
            self.assertEqual(split_evenly(0, 3), [0, 0, 0])
            self.assertEqual(split_evenly(7, 1), [7])

        def test_bad_parts(self):
            with self.assertRaises(ValueError):
                split_evenly(10, 0)
            with self.assertRaises(ValueError):
                split_evenly(10, -2)


    class SeatDays(unittest.TestCase):
        P = (D(2025, 6, 1), D(2025, 7, 1))

        def test_constant_seats(self):
            self.assertEqual(seat_days_charge(1000, [(D(2025, 1, 1), 5)], *self.P), 5000)

        def test_no_seats_before_first_event(self):
            self.assertEqual(seat_days_charge(1000, [(D(2025, 6, 16), 2)], *self.P), 1000)

        def test_change_mid_period(self):
            log = [(D(2025, 6, 1), 2), (D(2025, 6, 11), 5)]
            # 10 days * 2 + 20 days * 5 = 120 seat-days; 1500 * 120 / 30 = 6000
            self.assertEqual(seat_days_charge(1500, log, *self.P), 6000)

        def test_unsorted_log(self):
            log = [(D(2025, 6, 11), 5), (D(2025, 6, 1), 2)]
            self.assertEqual(seat_days_charge(1500, log, *self.P), 6000)

        def test_event_after_period_ignored(self):
            log = [(D(2025, 6, 1), 1), (D(2025, 7, 1), 9)]
            self.assertEqual(seat_days_charge(300, log, *self.P), 300)

        def test_event_before_period_sets_count(self):
            log = [(D(2025, 3, 1), 4), (D(2025, 5, 1), 3)]
            self.assertEqual(seat_days_charge(300, log, *self.P), 900)

        def test_seats_drop_to_zero(self):
            log = [(D(2025, 6, 1), 3), (D(2025, 6, 11), 0)]
            self.assertEqual(seat_days_charge(300, log, *self.P), 300)

        def test_single_rounding_at_end(self):
            # 1 seat for 1 day of a 30 day period at 100 cents: 100 / 30 = 3.33 -> 3
            log = [(D(2025, 6, 30), 1)]
            self.assertEqual(seat_days_charge(100, log, *self.P), 3)
            # 1 seat for 15 days at 5 cents -> 2.5 -> 3
            self.assertEqual(seat_days_charge(5, [(D(2025, 6, 16), 1)], *self.P), 3)

        def test_empty_period(self):
            with self.assertRaises(ValueError):
                seat_days_charge(100, [], D(2025, 6, 1), D(2025, 6, 1))

        def test_empty_log(self):
            self.assertEqual(seat_days_charge(100, [], *self.P), 0)


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="proration", lang="python", title="invoice proration (`billing/proration.py`)",
    blurb="The subscription-billing service uses these helpers to charge customers for part of a billing period.",
    files={"billing/__init__.py": "", "billing/proration.py": SRC, "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": VISIBLE},
    hidden_tests={"tests/test_full.py": HIDDEN},
    mutate=["billing/proration.py"], difficulty=2, tags=["billing", "dates", "money"],
    probes=[
        "days_between(date(2025, 3, 1), date(2025, 4, 1))",
        "prorate(5, date(2025, 6, 1), date(2025, 6, 16), date(2025, 6, 1), date(2025, 7, 1))",
        "prorate(3000, date(2025, 5, 1), date(2025, 6, 11), date(2025, 6, 1), date(2025, 7, 1))",
        "prorate(-5, date(2025, 6, 1), date(2025, 6, 16), date(2025, 6, 1), date(2025, 7, 1))",
        "split_evenly(10, 3)",
        "split_evenly(-10, 3)",
        "split_evenly(1, 4)",
        "seat_days_charge(1500, [(date(2025, 6, 11), 5), (date(2025, 6, 1), 2)], date(2025, 6, 1), date(2025, 7, 1))",
        "seat_days_charge(300, [(date(2025, 6, 1), 1), (date(2025, 7, 1), 9)], date(2025, 6, 1), date(2025, 7, 1))",
    ],
    probe_import="from datetime import date\nfrom billing.proration import *",
)

register_libs([LIB], n=10)
