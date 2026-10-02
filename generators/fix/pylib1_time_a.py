"""Python libraries, theme time/money/scheduling (batch time-a): business calendars, SLA clocks, ship-log durations,
recurring-event expansion."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# workcal: business-day arithmetic with a configurable weekend and holidays
# ======================================================================================================================

WC_README = dd('''
    # workcal

    Business-day arithmetic for a payroll scheduler. Dates are `datetime.date`. A weekday is numbered like
    `date.weekday()` (Monday is `0`, Sunday is `6`).

    ## `Calendar(weekend=(5, 6), holidays=())` (`workcal/core.py`)

    A calendar knows its weekend days and a collection of holiday dates. A calendar whose weekend contains all seven
    weekdays is a `ValueError`.

    * `is_business_day(d)`: true when `d` is neither on a weekend day nor a holiday.
    * `add_business_days(d, n)`: `n > 0` moves forward over `n` business days (the starting day is never counted, and
      it need not be a business day itself). `n < 0` moves the same way backwards. `n == 0` returns `d` when it is a
      business day, otherwise the **next** business day.
    * `count_between(start, end)`: the number of business days in the half-open range `[start, end)`. When
      `end < start` it is the negative of `count_between(end, start)`. For a business day `d` and `n >= 0`,
      `count_between(d, add_business_days(d, n)) == n`.

    ## Rolling and pay dates (`workcal/rolls.py`)

    * `roll(cal, d, convention="following")`: a business day is returned unchanged. Otherwise `"following"` is the
      next business day, `"preceding"` the previous one and `"modified_following"` is the following business day
      unless that falls in another month, in which case it is the preceding one. An unknown convention is a
      `ValueError` (even when `d` is a business day).
    * `observed_holidays(holidays, weekend=(5, 6))`: returns the set of dates on which the holidays are observed.
      Holidays that fall on a working weekday stay where they are. A holiday on a weekend day moves to the next day
      that is not a weekend day and not already taken by another holiday; weekend holidays are handled in date
      order.
    * `nth_business_day(cal, year, month, n)`: the `n`-th business day of the month counted from the start (`n >= 1`)
      or from the end (`n <= -1`, so `-1` is the last one). `n == 0` or a month that has fewer than `abs(n)` business
      days is a `ValueError`.
    * `pay_date(cal, year, month, day)`: the pay date for "pay on the `day`-th": `day` must be 1 to 31 (`ValueError`
      otherwise) and is cut back to the last day of short months. If that date is not a business day, pay on the
      preceding business day (which can be in the previous month).
''')

WC_CORE = dd('''
    from datetime import timedelta


    class Calendar:
        def __init__(self, weekend=(5, 6), holidays=()):
            self.weekend = frozenset(weekend)
            self.holidays = frozenset(holidays)
            if len(self.weekend) >= 7:
                raise ValueError("a calendar needs at least one working weekday")

        def is_business_day(self, d):
            return d.weekday() not in self.weekend and d not in self.holidays

        def step(self, d, direction):
            """The nearest business day strictly after (direction 1) or before (direction -1) d."""
            d += timedelta(days=direction)
            while not self.is_business_day(d):
                d += timedelta(days=direction)
            return d

        def add_business_days(self, d, n):
            if n == 0:
                while not self.is_business_day(d):
                    d += timedelta(days=1)
                return d
            direction = 1 if n > 0 else -1
            for _ in range(abs(n)):
                d = self.step(d, direction)
            return d

        def count_between(self, start, end):
            if end < start:
                return -self.count_between(end, start)
            n = 0
            d = start
            while d < end:
                if self.is_business_day(d):
                    n += 1
                d += timedelta(days=1)
            return n
''')

WC_ROLLS = dd('''
    import calendar
    from datetime import date, timedelta

    from .core import Calendar

    CONVENTIONS = ("following", "preceding", "modified_following")


    def roll(cal, d, convention="following"):
        if convention not in CONVENTIONS:
            raise ValueError(f"unknown convention {convention!r}")
        if cal.is_business_day(d):
            return d
        if convention == "preceding":
            return cal.step(d, -1)
        following = cal.step(d, 1)
        if convention == "modified_following" and following.month != d.month:
            return cal.step(d, -1)
        return following


    def observed_holidays(holidays, weekend=(5, 6)):
        weekend = frozenset(weekend)
        result = {h for h in holidays if h.weekday() not in weekend}
        for h in sorted(h for h in holidays if h.weekday() in weekend):
            d = h + timedelta(days=1)
            while d.weekday() in weekend or d in result:
                d += timedelta(days=1)
            result.add(d)
        return result


    def nth_business_day(cal, year, month, n):
        if n == 0:
            raise ValueError("n must not be 0")
        last = calendar.monthrange(year, month)[1]
        days = [date(year, month, i) for i in range(1, last + 1)]
        days = [d for d in days if cal.is_business_day(d)]
        if abs(n) > len(days):
            raise ValueError("the month has fewer business days")
        return days[n - 1] if n > 0 else days[n]


    def pay_date(cal, year, month, day):
        if not 1 <= day <= 31:
            raise ValueError("day must be 1..31")
        day = min(day, calendar.monthrange(year, month)[1])
        return roll(cal, date(year, month, day), "preceding")
''')

WC_VISIBLE = dd('''
    import unittest
    from datetime import date

    from workcal.core import Calendar
    from workcal.rolls import roll


    class BasicTests(unittest.TestCase):
        def test_weekend(self):
            cal = Calendar()
            self.assertFalse(cal.is_business_day(date(2025, 3, 8)))
            self.assertTrue(cal.is_business_day(date(2025, 3, 7)))

        def test_add_over_weekend(self):
            self.assertEqual(Calendar().add_business_days(date(2025, 3, 7), 1), date(2025, 3, 10))

        def test_roll_following(self):
            self.assertEqual(roll(Calendar(), date(2025, 3, 8)), date(2025, 3, 10))


    if __name__ == "__main__":
        unittest.main()
''')

WC_HIDDEN = dd('''
    import unittest
    from datetime import date, timedelta

    from workcal.core import Calendar
    from workcal.rolls import nth_business_day, observed_holidays, pay_date, roll

    D = date
    EASTERISH = Calendar(holidays={D(2025, 4, 18), D(2025, 4, 21)})


    class Basics(unittest.TestCase):
        def test_is_business_day(self):
            c = EASTERISH
            self.assertTrue(c.is_business_day(D(2025, 4, 14)))
            self.assertTrue(c.is_business_day(D(2025, 4, 17)))
            self.assertFalse(c.is_business_day(D(2025, 4, 18)))
            self.assertFalse(c.is_business_day(D(2025, 4, 19)))
            self.assertFalse(c.is_business_day(D(2025, 4, 20)))
            self.assertFalse(c.is_business_day(D(2025, 4, 21)))
            self.assertTrue(c.is_business_day(D(2025, 4, 22)))

        def test_custom_weekend(self):
            c = Calendar(weekend=(4, 5))
            self.assertFalse(c.is_business_day(D(2025, 3, 7)))
            self.assertFalse(c.is_business_day(D(2025, 3, 8)))
            self.assertTrue(c.is_business_day(D(2025, 3, 9)))
            self.assertTrue(c.is_business_day(D(2025, 3, 10)))

        def test_single_day_weekend_and_no_weekend(self):
            self.assertTrue(Calendar(weekend=()).is_business_day(D(2025, 3, 8)))
            self.assertFalse(Calendar(weekend=(6,)).is_business_day(D(2025, 3, 9)))
            self.assertTrue(Calendar(weekend=(6,)).is_business_day(D(2025, 3, 8)))

        def test_all_days_weekend_is_an_error(self):
            with self.assertRaises(ValueError):
                Calendar(weekend=range(7))
            Calendar(weekend=range(6))


    class AddBusinessDays(unittest.TestCase):
        def test_plain(self):
            c = Calendar()
            self.assertEqual(c.add_business_days(D(2025, 3, 7), 1), D(2025, 3, 10))
            self.assertEqual(c.add_business_days(D(2025, 3, 10), -1), D(2025, 3, 7))
            self.assertEqual(c.add_business_days(D(2025, 3, 5), 10), D(2025, 3, 19))
            self.assertEqual(c.add_business_days(D(2025, 3, 5), 5), D(2025, 3, 12))
            self.assertEqual(c.add_business_days(D(2025, 3, 19), -10), D(2025, 3, 5))

        def test_holidays_are_skipped(self):
            c = EASTERISH
            self.assertEqual(c.add_business_days(D(2025, 4, 17), 1), D(2025, 4, 22))
            self.assertEqual(c.add_business_days(D(2025, 4, 17), 2), D(2025, 4, 23))
            self.assertEqual(c.add_business_days(D(2025, 4, 14), 4), D(2025, 4, 22))
            self.assertEqual(c.add_business_days(D(2025, 4, 14), 5), D(2025, 4, 23))
            self.assertEqual(c.add_business_days(D(2025, 4, 22), -1), D(2025, 4, 17))
            self.assertEqual(c.add_business_days(D(2025, 4, 22), -2), D(2025, 4, 16))

        def test_zero_rolls_forward(self):
            c = EASTERISH
            self.assertEqual(c.add_business_days(D(2025, 4, 14), 0), D(2025, 4, 14))
            self.assertEqual(c.add_business_days(D(2025, 4, 19), 0), D(2025, 4, 22))
            self.assertEqual(c.add_business_days(D(2025, 4, 18), 0), D(2025, 4, 22))

        def test_start_on_a_non_business_day(self):
            c = EASTERISH
            self.assertEqual(c.add_business_days(D(2025, 4, 19), 1), D(2025, 4, 22))
            self.assertEqual(c.add_business_days(D(2025, 4, 19), 2), D(2025, 4, 23))
            self.assertEqual(c.add_business_days(D(2025, 4, 19), -1), D(2025, 4, 17))
            self.assertEqual(c.add_business_days(D(2025, 3, 8), -1), D(2025, 3, 7))
            self.assertEqual(c.add_business_days(D(2025, 3, 9), 1), D(2025, 3, 10))

        def test_custom_weekend(self):
            c = Calendar(weekend=(4, 5))
            self.assertEqual(c.add_business_days(D(2025, 3, 6), 1), D(2025, 3, 9))
            self.assertEqual(c.add_business_days(D(2025, 3, 9), -1), D(2025, 3, 6))
            self.assertEqual(c.add_business_days(D(2025, 3, 6), 3), D(2025, 3, 11))

        def test_long_jump(self):
            c = Calendar()
            self.assertEqual(c.add_business_days(D(2025, 1, 1), 100), D(2025, 5, 21))
            self.assertEqual(c.add_business_days(D(2025, 5, 21), -100), D(2025, 1, 1))


    class CountBetween(unittest.TestCase):
        def test_ranges(self):
            c = EASTERISH
            self.assertEqual(c.count_between(D(2025, 4, 14), D(2025, 4, 21)), 4)
            self.assertEqual(c.count_between(D(2025, 4, 14), D(2025, 4, 22)), 4)
            self.assertEqual(c.count_between(D(2025, 4, 14), D(2025, 4, 23)), 5)
            self.assertEqual(c.count_between(D(2025, 4, 19), D(2025, 4, 23)), 1)
            self.assertEqual(c.count_between(D(2025, 4, 14), D(2025, 4, 15)), 1)

        def test_empty_and_reversed(self):
            c = EASTERISH
            self.assertEqual(c.count_between(D(2025, 4, 14), D(2025, 4, 14)), 0)
            self.assertEqual(c.count_between(D(2025, 4, 22), D(2025, 4, 14)), -4)
            self.assertEqual(c.count_between(D(2025, 4, 23), D(2025, 4, 19)), -1)

        def test_long_range(self):
            self.assertEqual(Calendar().count_between(D(2025, 1, 1), D(2026, 1, 1)), 261)
            self.assertEqual(Calendar(weekend=(6,)).count_between(D(2025, 1, 1), D(2026, 1, 1)), 313)

        def test_round_trip_with_add(self):
            c = EASTERISH
            d = D(2025, 3, 1)
            while d < D(2025, 5, 15):
                if c.is_business_day(d):
                    for n in range(0, 13):
                        self.assertEqual(c.count_between(d, c.add_business_days(d, n)), n, (d, n))
                        self.assertEqual(c.count_between(c.add_business_days(d, -n), d), n, (d, -n))
                d += timedelta(days=1)


    class Roll(unittest.TestCase):
        def test_business_day_unchanged(self):
            for conv in ("following", "preceding", "modified_following"):
                self.assertEqual(roll(EASTERISH, D(2025, 4, 17), conv), D(2025, 4, 17))

        def test_conventions(self):
            c = EASTERISH
            self.assertEqual(roll(c, D(2025, 4, 19)), D(2025, 4, 22))
            self.assertEqual(roll(c, D(2025, 4, 19), "following"), D(2025, 4, 22))
            self.assertEqual(roll(c, D(2025, 4, 19), "preceding"), D(2025, 4, 17))
            self.assertEqual(roll(c, D(2025, 4, 19), "modified_following"), D(2025, 4, 22))
            self.assertEqual(roll(c, D(2025, 4, 18), "preceding"), D(2025, 4, 17))

        def test_modified_following_stays_in_month(self):
            c = Calendar()
            self.assertEqual(roll(c, D(2025, 5, 31), "following"), D(2025, 6, 2))
            self.assertEqual(roll(c, D(2025, 5, 31), "modified_following"), D(2025, 5, 30))
            self.assertEqual(roll(c, D(2025, 6, 1), "modified_following"), D(2025, 6, 2))
            c = Calendar(holidays={D(2025, 4, 30)})
            self.assertEqual(roll(c, D(2025, 4, 30), "following"), D(2025, 5, 1))
            self.assertEqual(roll(c, D(2025, 4, 30), "modified_following"), D(2025, 4, 29))
            c = Calendar(holidays={D(2025, 4, 30), D(2025, 4, 29)})
            self.assertEqual(roll(c, D(2025, 4, 30), "modified_following"), D(2025, 4, 28))

        def test_unknown_convention(self):
            with self.assertRaises(ValueError):
                roll(EASTERISH, D(2025, 4, 19), "nearest")
            with self.assertRaises(ValueError):
                roll(EASTERISH, D(2025, 4, 17), "nearest")


    class Observed(unittest.TestCase):
        def test_weekday_holiday_stays(self):
            self.assertEqual(observed_holidays({D(2025, 3, 5), D(2025, 3, 7)}), {D(2025, 3, 5), D(2025, 3, 7)})

        def test_weekend_holidays_move(self):
            self.assertEqual(observed_holidays({D(2025, 3, 8)}), {D(2025, 3, 10)})
            self.assertEqual(observed_holidays({D(2025, 3, 9)}), {D(2025, 3, 10)})

        def test_collisions(self):
            self.assertEqual(observed_holidays({D(2025, 3, 8), D(2025, 3, 9)}), {D(2025, 3, 10), D(2025, 3, 11)})
            self.assertEqual(observed_holidays({D(2025, 3, 8), D(2025, 3, 10)}), {D(2025, 3, 10), D(2025, 3, 11)})
            self.assertEqual(observed_holidays([D(2025, 3, 9), D(2025, 3, 8), D(2025, 3, 11)]),
                             {D(2025, 3, 10), D(2025, 3, 11), D(2025, 3, 12)})

        def test_custom_weekend(self):
            w = (4, 5)
            self.assertEqual(observed_holidays({D(2025, 3, 7)}, w), {D(2025, 3, 9)})
            self.assertEqual(observed_holidays({D(2025, 3, 8)}, w), {D(2025, 3, 9)})
            self.assertEqual(observed_holidays({D(2025, 3, 7), D(2025, 3, 8)}, w), {D(2025, 3, 9), D(2025, 3, 10)})
            self.assertEqual(observed_holidays({D(2025, 3, 9)}, w), {D(2025, 3, 9)})

        def test_empty(self):
            self.assertEqual(observed_holidays(set()), set())


    class NthBusinessDay(unittest.TestCase):
        def test_from_start(self):
            c = Calendar()
            self.assertEqual(nth_business_day(c, 2025, 3, 1), D(2025, 3, 3))
            self.assertEqual(nth_business_day(c, 2025, 3, 5), D(2025, 3, 7))
            self.assertEqual(nth_business_day(c, 2025, 3, 6), D(2025, 3, 10))
            self.assertEqual(nth_business_day(c, 2025, 3, 21), D(2025, 3, 31))
            self.assertEqual(nth_business_day(c, 2025, 6, 1), D(2025, 6, 2))
            self.assertEqual(nth_business_day(c, 2025, 4, 1), D(2025, 4, 1))
            self.assertEqual(nth_business_day(c, 2025, 4, 22), D(2025, 4, 30))

        def test_from_end(self):
            c = Calendar()
            self.assertEqual(nth_business_day(c, 2025, 3, -1), D(2025, 3, 31))
            self.assertEqual(nth_business_day(c, 2025, 3, -2), D(2025, 3, 28))
            self.assertEqual(nth_business_day(c, 2025, 3, -21), D(2025, 3, 3))
            self.assertEqual(nth_business_day(c, 2025, 5, -1), D(2025, 5, 30))

        def test_out_of_range(self):
            c = Calendar()
            for n in (0, 22, -22, 40):
                with self.assertRaises(ValueError):
                    nth_business_day(c, 2025, 3, n)

        def test_holidays_and_weekend(self):
            c = Calendar(holidays={D(2025, 3, 3)})
            self.assertEqual(nth_business_day(c, 2025, 3, 1), D(2025, 3, 4))
            self.assertEqual(nth_business_day(c, 2025, 3, 20), D(2025, 3, 31))
            with self.assertRaises(ValueError):
                nth_business_day(c, 2025, 3, 21)
            f = Calendar(weekend=(4, 5))
            self.assertEqual(nth_business_day(f, 2025, 3, 1), D(2025, 3, 2))
            self.assertEqual(nth_business_day(f, 2025, 3, 2), D(2025, 3, 3))
            self.assertEqual(nth_business_day(f, 2025, 3, -1), D(2025, 3, 31))
            self.assertEqual(nth_business_day(f, 2025, 3, -2), D(2025, 3, 30))

        def test_leap_february(self):
            self.assertEqual(nth_business_day(Calendar(), 2024, 2, -1), D(2024, 2, 29))
            self.assertEqual(nth_business_day(Calendar(), 2025, 2, -1), D(2025, 2, 28))


    class PayDate(unittest.TestCase):
        def test_rolls_back(self):
            c = Calendar()
            self.assertEqual(pay_date(c, 2025, 3, 14), D(2025, 3, 14))
            self.assertEqual(pay_date(c, 2025, 3, 15), D(2025, 3, 14))
            self.assertEqual(pay_date(c, 2025, 3, 16), D(2025, 3, 14))
            self.assertEqual(pay_date(c, 2025, 3, 17), D(2025, 3, 17))

        def test_short_months(self):
            c = Calendar()
            self.assertEqual(pay_date(c, 2025, 4, 31), D(2025, 4, 30))
            self.assertEqual(pay_date(c, 2025, 2, 30), D(2025, 2, 28))
            self.assertEqual(pay_date(c, 2024, 2, 31), D(2024, 2, 29))
            self.assertEqual(pay_date(c, 2025, 3, 31), D(2025, 3, 31))
            self.assertEqual(pay_date(c, 2025, 6, 30), D(2025, 6, 30))

        def test_previous_month(self):
            self.assertEqual(pay_date(Calendar(), 2025, 6, 1), D(2025, 5, 30))

        def test_holiday(self):
            c = Calendar(holidays={D(2025, 3, 14)})
            self.assertEqual(pay_date(c, 2025, 3, 14), D(2025, 3, 13))
            self.assertEqual(pay_date(c, 2025, 3, 15), D(2025, 3, 13))

        def test_bad_day(self):
            for day in (0, -3, 32):
                with self.assertRaises(ValueError):
                    pay_date(Calendar(), 2025, 3, day)


    if __name__ == "__main__":
        unittest.main()
''')

WORKCAL = Lib(
    name="workcal", lang="python", title="the payroll business-day calendar (`workcal/`)",
    blurb="The payroll scheduler uses workcal to move deadlines and pay dates around weekends and holidays.",
    files={"workcal/__init__.py": "", "workcal/core.py": WC_CORE, "workcal/rolls.py": WC_ROLLS,
           "README.md": WC_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": WC_VISIBLE},
    hidden_tests={"tests/test_full.py": WC_HIDDEN},
    mutate=["workcal/core.py", "workcal/rolls.py"], difficulty=3, tags=["calendar", "business-days", "dates"],
    probes=[
        "Calendar(holidays={date(2025, 4, 18), date(2025, 4, 21)}).add_business_days(date(2025, 4, 17), 1)",
        "Calendar().add_business_days(date(2025, 3, 8), 0)",
        "Calendar().add_business_days(date(2025, 3, 10), -1)",
        "Calendar().count_between(date(2025, 3, 3), date(2025, 3, 10))",
        "Calendar().count_between(date(2025, 3, 10), date(2025, 3, 3))",
        "roll(Calendar(), date(2025, 5, 31), 'modified_following')",
        "roll(Calendar(), date(2025, 3, 8), 'preceding')",
        "sorted(observed_holidays({date(2025, 3, 8), date(2025, 3, 9)}))",
        "nth_business_day(Calendar(), 2025, 3, -2)",
        "nth_business_day(Calendar(), 2025, 3, 21)",
        "pay_date(Calendar(), 2025, 2, 30)",
        "pay_date(Calendar(), 2025, 6, 1)",
    ],
    probe_import="from datetime import date\nfrom workcal.core import *\nfrom workcal.rolls import *",
)

# ======================================================================================================================
# slaclock: support-ticket SLA clock that only runs inside opening hours and stops while the ticket is paused
# ======================================================================================================================

SC_README = dd('''
    # slaclock

    SLA timers for a support desk. A ticket's clock only runs during the desk's opening hours and only while the
    ticket is not paused. Instants are naive `datetime` objects; **seconds and microseconds are ignored** (everything
    is counted in whole minutes). A duration is a whole number of minutes.

    ## Parsing (`slaclock/spec.py`)

    * `parse_hhmm("09:30") -> 570`: minutes after midnight. Exactly two digits, a colon, two digits; `00:00` to
      `24:00`, minutes below 60 (`24:00` is `1440`, `24:01` is invalid). Anything else is a `ValueError`.
    * `parse_window("09:00-12:30") -> (540, 750)`. Whitespace around the two times is ignored. The end must be after
      the start, otherwise `ValueError`.
    * `parse_days("mon-fri")`: the sorted list of weekday numbers (Monday is `0`). The text is case-insensitive and
      is a comma-separated list of single days (`mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun`) and ranges
      `a-b` (inclusive; a range may wrap around the end of the week: `fri-mon` is Fri, Sat, Sun, Mon). Spaces around
      names and hyphens are ignored. Duplicates are merged. Unknown names, empty items and empty text are a
      `ValueError`.

    ## `Schedule` (`slaclock/schedule.py`)

    `Schedule(windows, holidays=())`: `windows` maps a weekday number to a list of `(start, end)` minute windows. The
    windows of one day must lie within `0..1440`, have `start < end`, and must not overlap (touching is fine),
    otherwise `ValueError`. Holidays are `date`s: no window is open on them.
    `Schedule.from_spec(spec, holidays=())` builds one from `{"mon-fri": ["09:00-12:00", "13:00-17:00"], "sat":
    ["10:00-12:00"]}`; a weekday that appears under several keys gets all their windows (overlaps are an error).

    * `minutes_between(start, end)`: opening-hours minutes in `[start, end)`; `0` when `end <= start`.
    * `add_minutes(start, minutes)`: the instant at which `minutes` opening-hours minutes have elapsed since `start`.
      Negative `minutes` is a `ValueError`; `0` returns `start` unchanged (even outside opening hours). When the last
      minute is the last minute of a window, the result is the end of that window (not the next opening). A schedule
      that never opens raises `ValueError`.

    ## Ticket clocks (`slaclock/clock.py`)

    Events are `(instant, kind)` pairs in time order, kind one of `open`, `pause`, `resume`, `close`. The first event
    must be `open`; `pause` is only allowed while running, `resume` only while paused, `close` only while running;
    nothing may follow `close`. Events out of time order or in an illegal state are a `ValueError`. Events later than
    `now` are not looked at at all.

    * `sla_elapsed(schedule, events, now)`: opening-hours minutes during which the clock was running up to `now`.
      A clock that is still running at `now` counts up to `now`.
    * `sla_status(schedule, events, now, target)`: `(status, remaining)` with `remaining = target - elapsed`.
      For a closed ticket the status is `"met"` when `elapsed <= target`, else `"breached"`. For an open ticket:
      `"breached"` when `elapsed > target`; `"at_risk"` when at most a quarter of the target is left
      (`remaining * 4 <= target`); otherwise `"ok"`.
    * `projected_deadline(schedule, events, now, target)`: while the clock is running, the instant at which the
      target is used up, `schedule.add_minutes(now, remaining)` (just `now` if nothing remains). While paused,
      closed or not yet opened: `None`.
''')

SC_SPEC = dd('''
    import re

    DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    _HHMM = re.compile(r"^(\\d\\d):(\\d\\d)$")


    def parse_hhmm(text):
        m = _HHMM.match(text)
        if not m:
            raise ValueError(f"bad time {text!r}")
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 24 or mi > 59 or (h == 24 and mi != 0):
            raise ValueError(f"bad time {text!r}")
        return h * 60 + mi


    def parse_window(text):
        start, sep, end = text.partition("-")
        if not sep:
            raise ValueError(f"bad window {text!r}")
        a, b = parse_hhmm(start.strip()), parse_hhmm(end.strip())
        if b <= a:
            raise ValueError("window must end after it starts")
        return (a, b)


    def _day(name):
        name = name.strip().lower()
        if name not in DAYS:
            raise ValueError(f"unknown day {name!r}")
        return DAYS.index(name)


    def parse_days(text):
        days = set()
        for part in text.split(","):
            if "-" in part:
                first, _, last = part.partition("-")
                i, stop = _day(first), _day(last)
                while True:
                    days.add(i)
                    if i == stop:
                        break
                    i = (i + 1) % 7
            else:
                days.add(_day(part))
        return sorted(days)
''')

SC_SCHEDULE = dd('''
    from datetime import date, datetime, timedelta

    from .spec import parse_days, parse_window

    MAX_DAYS = 3700


    def to_minutes(dt):
        return dt.toordinal() * 1440 + dt.hour * 60 + dt.minute


    def from_minutes(m):
        return datetime.fromordinal(m // 1440) + timedelta(minutes=m % 1440)


    class Schedule:
        def __init__(self, windows, holidays=()):
            self.windows = {}
            for weekday, spans in windows.items():
                spans = sorted(spans)
                edge = 0
                for start, end in spans:
                    if not 0 <= start < end <= 1440 or start < edge:
                        raise ValueError(f"bad windows for weekday {weekday!r}: {spans!r}")
                    edge = end
                self.windows[weekday] = spans
            self.holidays = frozenset(holidays)

        @classmethod
        def from_spec(cls, spec, holidays=()):
            windows = {}
            for days, texts in spec.items():
                for weekday in parse_days(days):
                    windows.setdefault(weekday, []).extend(parse_window(t) for t in texts)
            return cls(windows, holidays)

        def _spans(self, day):
            if day in self.holidays:
                return []
            return self.windows.get(day.weekday(), [])

        def minutes_between(self, start, end):
            a, b = to_minutes(start), to_minutes(end)
            if b <= a:
                return 0
            total = 0
            day = start.date()
            while day <= end.date():
                base = day.toordinal() * 1440
                for s, e in self._spans(day):
                    lo = max(a, base + s)
                    hi = min(b, base + e)
                    if hi > lo:
                        total += hi - lo
                day += timedelta(days=1)
            return total

        def add_minutes(self, start, minutes):
            if minutes < 0:
                raise ValueError("minutes must not be negative")
            if minutes == 0:
                return start
            left = minutes
            t = to_minutes(start)
            day = start.date()
            for _ in range(MAX_DAYS):
                base = day.toordinal() * 1440
                for s, e in self._spans(day):
                    lo = max(t, base + s)
                    room = base + e - lo
                    if room <= 0:
                        continue
                    if left <= room:
                        return from_minutes(lo + left)
                    left -= room
                day += timedelta(days=1)
            raise ValueError("the schedule never opens")
''')

SC_CLOCK = dd('''
    TRANSITIONS = {
        None: {"open": "running"},
        "running": {"pause": "paused", "close": "closed"},
        "paused": {"resume": "running"},
        "closed": {},
    }


    def _replay(schedule, events, now):
        state = None
        since = None
        total = 0
        last = None
        for at, kind in events:
            if last is not None and at < last:
                raise ValueError("events are out of order")
            last = at
            if at > now:
                break
            nxt = TRANSITIONS[state].get(kind)
            if nxt is None:
                raise ValueError(f"cannot {kind!s} a ticket that is {state or 'not opened'}")
            if kind in ("open", "resume"):
                since = at
            else:
                total += schedule.minutes_between(since, at)
                since = None
            state = nxt
        if state == "running":
            total += schedule.minutes_between(since, now)
        return state, total


    def sla_elapsed(schedule, events, now):
        return _replay(schedule, events, now)[1]


    def sla_status(schedule, events, now, target):
        state, used = _replay(schedule, events, now)
        remaining = target - used
        if state == "closed":
            return ("met" if used <= target else "breached", remaining)
        if used > target:
            return ("breached", remaining)
        if remaining * 4 <= target:
            return ("at_risk", remaining)
        return ("ok", remaining)


    def projected_deadline(schedule, events, now, target):
        state, used = _replay(schedule, events, now)
        if state != "running":
            return None
        return schedule.add_minutes(now, max(0, target - used))
''')

SC_VISIBLE = dd('''
    import unittest
    from datetime import datetime

    from slaclock.schedule import Schedule
    from slaclock.spec import parse_hhmm, parse_window

    DESK = Schedule.from_spec({"mon-fri": ["09:00-12:00", "13:00-17:00"]})


    class BasicTests(unittest.TestCase):
        def test_parse_hhmm(self):
            self.assertEqual(parse_hhmm("09:30"), 570)

        def test_parse_window(self):
            self.assertEqual(parse_window("09:00-12:30"), (540, 750))

        def test_minutes_in_one_day(self):
            self.assertEqual(DESK.minutes_between(datetime(2025, 3, 3, 8, 0), datetime(2025, 3, 3, 18, 0)), 420)

        def test_add_within_a_window(self):
            self.assertEqual(DESK.add_minutes(datetime(2025, 3, 3, 9, 0), 60), datetime(2025, 3, 3, 10, 0))


    if __name__ == "__main__":
        unittest.main()
''')

SC_HIDDEN = dd('''
    import unittest
    from datetime import date, datetime, timedelta

    from slaclock.clock import projected_deadline, sla_elapsed, sla_status
    from slaclock.schedule import Schedule
    from slaclock.spec import parse_days, parse_hhmm, parse_window

    DESK = Schedule.from_spec({"mon-fri": ["09:00-12:00", "13:00-17:00"]})


    def at(day, hh, mm=0, ss=0):
        # March 2025: Monday is the 3rd
        return datetime(2025, 3, day, hh, mm, ss)


    class Parsing(unittest.TestCase):
        def test_hhmm(self):
            self.assertEqual(parse_hhmm("09:30"), 570)
            self.assertEqual(parse_hhmm("00:00"), 0)
            self.assertEqual(parse_hhmm("00:01"), 1)
            self.assertEqual(parse_hhmm("23:59"), 1439)
            self.assertEqual(parse_hhmm("24:00"), 1440)

        def test_hhmm_errors(self):
            for bad in ("24:01", "25:00", "09:60", "9:30", "09:5", "09-30", "", "ab:cd", "0930", "09:30:00", " 09:30"):
                with self.assertRaises(ValueError, msg=bad):
                    parse_hhmm(bad)

        def test_window(self):
            self.assertEqual(parse_window("09:00-12:30"), (540, 750))
            self.assertEqual(parse_window(" 09:00 - 12:30 "), (540, 750))
            self.assertEqual(parse_window("00:00-24:00"), (0, 1440))

        def test_window_errors(self):
            for bad in ("12:00-09:00", "09:00-09:00", "09:00", "09:00-", "-10:00", "09:00-25:00"):
                with self.assertRaises(ValueError, msg=bad):
                    parse_window(bad)

        def test_days(self):
            self.assertEqual(parse_days("mon"), [0])
            self.assertEqual(parse_days("mon-fri"), [0, 1, 2, 3, 4])
            self.assertEqual(parse_days("sat,sun"), [5, 6])
            self.assertEqual(parse_days("Sun"), [6])
            self.assertEqual(parse_days("mon,wed-fri"), [0, 2, 3, 4])
            self.assertEqual(parse_days("tue-tue"), [1])
            self.assertEqual(parse_days("mon,mon"), [0])
            self.assertEqual(parse_days("THU - Sat"), [3, 4, 5])
            self.assertEqual(parse_days("sat, mon"), [0, 5])

        def test_days_wrap(self):
            self.assertEqual(parse_days("fri-mon"), [0, 4, 5, 6])
            self.assertEqual(parse_days("sun-mon"), [0, 6])
            self.assertEqual(parse_days("sat-wed,thu"), [0, 1, 2, 3, 5, 6])

        def test_days_errors(self):
            for bad in ("", "funday", "mon-", "-fri", "mon,,tue", "mon-fri-sun", "monday"):
                with self.assertRaises(ValueError, msg=bad):
                    parse_days(bad)


    class ScheduleBuilding(unittest.TestCase):
        def test_from_spec_merges_keys(self):
            s = Schedule.from_spec({"mon-fri": ["09:00-12:00", "13:00-17:00"], "sat": ["10:00-12:00"], "fri": ["18:00-19:00"]})
            self.assertEqual(s.windows[0], [(540, 720), (780, 1020)])
            self.assertEqual(s.windows[4], [(540, 720), (780, 1020), (1080, 1140)])
            self.assertEqual(s.windows[5], [(600, 720)])
            self.assertNotIn(6, s.windows)

        def test_overlap_is_an_error(self):
            with self.assertRaises(ValueError):
                Schedule.from_spec({"mon-fri": ["09:00-12:00"], "mon": ["11:00-13:00"]})
            with self.assertRaises(ValueError):
                Schedule({0: [(540, 720), (700, 800)]})

        def test_touching_windows_are_fine(self):
            s = Schedule({0: [(540, 720), (720, 780)]})
            self.assertEqual(s.minutes_between(datetime(2025, 3, 3, 8), datetime(2025, 3, 3, 20)), 240)

        def test_unsorted_windows_are_sorted(self):
            s = Schedule({0: [(780, 1020), (540, 720)]})
            self.assertEqual(s.windows[0], [(540, 720), (780, 1020)])

        def test_bad_windows(self):
            for w in ([(600, 600)], [(700, 600)], [(-1, 60)], [(0, 1441)]):
                with self.assertRaises(ValueError, msg=w):
                    Schedule({1: w})
            Schedule({1: [(0, 1440)]})


    class MinutesBetween(unittest.TestCase):
        def test_inside_a_day(self):
            self.assertEqual(DESK.minutes_between(at(3, 9), at(3, 17)), 420)
            self.assertEqual(DESK.minutes_between(at(3, 8), at(3, 18)), 420)
            self.assertEqual(DESK.minutes_between(at(3, 10, 30), at(3, 14, 15)), 165)
            self.assertEqual(DESK.minutes_between(at(3, 12), at(3, 13)), 0)
            self.assertEqual(DESK.minutes_between(at(3, 11, 59), at(3, 13, 1)), 2)
            self.assertEqual(DESK.minutes_between(at(3, 9), at(3, 9, 1)), 1)

        def test_across_days(self):
            self.assertEqual(DESK.minutes_between(at(3, 16), at(4, 10)), 120)
            self.assertEqual(DESK.minutes_between(at(7, 16), at(10, 10)), 120)
            self.assertEqual(DESK.minutes_between(at(7, 17), at(10, 9)), 0)
            self.assertEqual(DESK.minutes_between(at(3, 0), at(10, 0)), 2100)
            self.assertEqual(DESK.minutes_between(at(1, 0), at(31, 23)), 21 * 420)

        def test_empty_and_reversed(self):
            self.assertEqual(DESK.minutes_between(at(3, 10), at(3, 10)), 0)
            self.assertEqual(DESK.minutes_between(at(3, 14), at(3, 10)), 0)
            self.assertEqual(DESK.minutes_between(at(5, 10), at(3, 10)), 0)

        def test_seconds_are_ignored(self):
            self.assertEqual(DESK.minutes_between(at(3, 9, 0, 59), at(3, 9, 1, 30)), 1)
            self.assertEqual(DESK.minutes_between(at(3, 9, 0, 30), at(3, 9, 0, 59)), 0)
            self.assertEqual(DESK.minutes_between(at(3, 9, 59, 59), at(3, 10, 0, 0)), 1)

        def test_holiday(self):
            s = Schedule.from_spec({"mon-fri": ["09:00-12:00", "13:00-17:00"]}, holidays={date(2025, 3, 4)})
            self.assertEqual(s.minutes_between(at(3, 16), at(5, 10)), 120)
            self.assertEqual(s.minutes_between(at(4, 0), at(5, 0)), 0)

        def test_weekend_windows(self):
            s = Schedule.from_spec({"mon-fri": ["09:00-17:00"], "sat": ["10:00-12:00"]})
            self.assertEqual(s.minutes_between(at(8, 9), at(8, 13)), 120)
            self.assertEqual(s.minutes_between(at(7, 16), at(10, 10)), 60 + 120 + 60)

        def test_midnight_and_overnight_window(self):
            s = Schedule({0: [(1380, 1440)], 1: [(0, 60)]})
            self.assertEqual(s.minutes_between(at(3, 22), at(4, 2)), 120)


    class AddMinutes(unittest.TestCase):
        def test_within_a_window(self):
            self.assertEqual(DESK.add_minutes(at(3, 9), 60), at(3, 10))
            self.assertEqual(DESK.add_minutes(at(3, 10, 15), 1), at(3, 10, 16))

        def test_ending_exactly_at_a_window_end(self):
            self.assertEqual(DESK.add_minutes(at(3, 9), 180), at(3, 12))
            self.assertEqual(DESK.add_minutes(at(3, 9), 420), at(3, 17))
            self.assertEqual(DESK.add_minutes(at(3, 11), 60), at(3, 12))

        def test_crossing_windows(self):
            self.assertEqual(DESK.add_minutes(at(3, 9), 181), at(3, 13, 1))
            self.assertEqual(DESK.add_minutes(at(3, 11, 30), 60), at(3, 13, 30))
            self.assertEqual(DESK.add_minutes(at(3, 9), 421), at(4, 9, 1))
            self.assertEqual(DESK.add_minutes(at(3, 16, 30), 45), at(4, 9, 15))

        def test_many_days(self):
            self.assertEqual(DESK.add_minutes(at(3, 9), 2100), at(7, 17))
            self.assertEqual(DESK.add_minutes(at(3, 9), 2101), at(10, 9, 1))
            self.assertEqual(DESK.add_minutes(at(3, 9), 420 * 11 + 5), at(18, 9, 5))

        def test_start_outside_hours(self):
            self.assertEqual(DESK.add_minutes(at(3, 8), 30), at(3, 9, 30))
            self.assertEqual(DESK.add_minutes(at(3, 12, 30), 30), at(3, 13, 30))
            self.assertEqual(DESK.add_minutes(at(3, 18), 30), at(4, 9, 30))
            self.assertEqual(DESK.add_minutes(at(8, 10), 30), at(10, 9, 30))
            self.assertEqual(DESK.add_minutes(at(9, 10), 30), at(10, 9, 30))

        def test_zero_returns_start(self):
            self.assertEqual(DESK.add_minutes(at(8, 10, 20), 0), at(8, 10, 20))
            self.assertEqual(DESK.add_minutes(at(3, 9), 0), at(3, 9))

        def test_negative(self):
            with self.assertRaises(ValueError):
                DESK.add_minutes(at(3, 9), -1)

        def test_holiday_is_skipped(self):
            s = Schedule.from_spec({"mon-fri": ["09:00-12:00", "13:00-17:00"]}, holidays={date(2025, 3, 4)})
            self.assertEqual(s.add_minutes(at(3, 16), 90), at(5, 9, 30))

        def test_never_opens(self):
            with self.assertRaises(ValueError):
                Schedule({}).add_minutes(at(3, 9), 5)
            tuesdays = Schedule({1: [(0, 60)]})
            self.assertEqual(tuesdays.add_minutes(at(3, 9), 5), at(4, 0, 5))

        def test_inverse_of_minutes_between(self):
            starts = [at(3, 8), at(3, 9), at(3, 11, 59), at(3, 12), at(3, 16, 59), at(7, 17), at(8, 11), at(9, 0)]
            for start in starts:
                for m in (1, 2, 59, 60, 61, 179, 180, 181, 419, 420, 421, 840, 1000):
                    end = DESK.add_minutes(start, m)
                    self.assertEqual(DESK.minutes_between(start, end), m, (start, m))
                    self.assertEqual(DESK.minutes_between(start, end - timedelta(minutes=1)), m - 1, (start, m))


    EVENTS = [(at(3, 10), "open"), (at(3, 11), "pause"), (at(4, 9), "resume"), (at(4, 10), "close")]


    class Elapsed(unittest.TestCase):
        def test_progress(self):
            expect = [(at(3, 9), 0), (at(3, 10), 0), (at(3, 10, 30), 30), (at(3, 11), 60), (at(3, 11, 30), 60),
                      (at(4, 9), 60), (at(4, 9, 30), 90), (at(4, 10), 120), (at(4, 15), 120), (at(9, 12), 120)]
            for now, minutes in expect:
                self.assertEqual(sla_elapsed(DESK, EVENTS, now), minutes, now)

        def test_still_running_over_a_weekend(self):
            ev = [(at(7, 16), "open")]
            self.assertEqual(sla_elapsed(DESK, ev, at(10, 10)), 120)
            self.assertEqual(sla_elapsed(DESK, ev, at(7, 16)), 0)

        def test_pause_outside_hours(self):
            ev = [(at(3, 16, 30), "open"), (at(3, 18), "pause"), (at(4, 8), "resume"), (at(4, 9, 10), "close")]
            self.assertEqual(sla_elapsed(DESK, ev, at(5, 9)), 40)

        def test_two_pauses(self):
            ev = [(at(3, 9), "open"), (at(3, 10), "pause"), (at(3, 11), "resume"), (at(3, 14), "pause"),
                  (at(3, 15), "resume")]
            self.assertEqual(sla_elapsed(DESK, ev, at(3, 16)), 60 + 120 + 60)
            self.assertEqual(sla_elapsed(DESK, ev, at(3, 14, 30)), 60 + 120)

        def test_no_events(self):
            self.assertEqual(sla_elapsed(DESK, [], at(3, 10)), 0)

        def test_events_after_now_are_ignored_even_if_invalid(self):
            ev = [(at(3, 10), "open"), (at(3, 12), "resume")]
            self.assertEqual(sla_elapsed(DESK, ev, at(3, 11)), 60)

        def test_event_at_now_counts(self):
            self.assertEqual(sla_elapsed(DESK, [(at(3, 10), "open"), (at(3, 11), "pause")], at(3, 11)), 60)
            self.assertEqual(sla_elapsed(DESK, [(at(3, 10), "open")], at(3, 10)), 0)

        def test_illegal_sequences(self):
            bad = [
                [(at(3, 10), "pause")],
                [(at(3, 10), "resume")],
                [(at(3, 10), "close")],
                [(at(3, 10), "open"), (at(3, 11), "open")],
                [(at(3, 10), "open"), (at(3, 11), "resume")],
                [(at(3, 10), "open"), (at(3, 11), "pause"), (at(3, 12), "pause")],
                [(at(3, 10), "open"), (at(3, 11), "pause"), (at(3, 12), "close")],
                [(at(3, 10), "open"), (at(3, 11), "close"), (at(3, 12), "pause")],
                [(at(3, 10), "open"), (at(3, 11), "close"), (at(3, 12), "open")],
            ]
            for ev in bad:
                with self.assertRaises(ValueError, msg=ev):
                    sla_elapsed(DESK, ev, at(5, 9))

        def test_out_of_order(self):
            ev = [(at(3, 11), "open"), (at(3, 10), "pause")]
            with self.assertRaises(ValueError):
                sla_elapsed(DESK, ev, at(5, 9))
            with self.assertRaises(ValueError):
                sla_elapsed(DESK, ev, at(3, 11, 30))

        def test_simultaneous_events_are_in_order(self):
            ev = [(at(3, 10), "open"), (at(3, 10), "pause"), (at(3, 10), "resume")]
            self.assertEqual(sla_elapsed(DESK, ev, at(3, 10, 30)), 30)


    class Status(unittest.TestCase):
        def test_open_ticket_bands(self):
            ev = [(at(3, 9), "open")]
            expect = [(at(3, 9), "ok", 120), (at(3, 10), "ok", 60), (at(3, 10, 29), "ok", 31), (at(3, 10, 30), "at_risk", 30),
                      (at(3, 10, 59), "at_risk", 1), (at(3, 11), "at_risk", 0), (at(3, 11, 1), "breached", -1),
                      (at(3, 12), "breached", -60)]
            for now, status, left in expect:
                self.assertEqual(sla_status(DESK, ev, now, 120), (status, left), now)

        def test_closed_ticket(self):
            ev = [(at(3, 9), "open"), (at(3, 11), "close")]
            self.assertEqual(sla_status(DESK, ev, at(3, 15), 120), ("met", 0))
            self.assertEqual(sla_status(DESK, ev, at(3, 15), 121), ("met", 1))
            self.assertEqual(sla_status(DESK, ev, at(3, 15), 119), ("breached", -1))

        def test_paused_ticket_keeps_its_state(self):
            ev = [(at(3, 9), "open"), (at(3, 10), "pause")]
            self.assertEqual(sla_status(DESK, ev, at(5, 15), 120), ("ok", 60))
            self.assertEqual(sla_status(DESK, ev, at(5, 15), 240), ("ok", 180))
            self.assertEqual(sla_status(DESK, ev, at(5, 15), 80), ("at_risk", 20))

        def test_not_opened(self):
            self.assertEqual(sla_status(DESK, [], at(3, 9), 100), ("ok", 100))


    class Deadline(unittest.TestCase):
        def test_running(self):
            ev = [(at(3, 10), "open")]
            self.assertEqual(projected_deadline(DESK, ev, at(3, 11), 120), at(3, 12))
            self.assertEqual(projected_deadline(DESK, ev, at(3, 11, 30), 120), at(3, 12))
            self.assertEqual(projected_deadline(DESK, ev, at(3, 11, 30), 150), at(3, 13, 30))
            self.assertEqual(projected_deadline(DESK, ev, at(3, 10), 120), at(3, 12))
            self.assertEqual(projected_deadline(DESK, ev, at(3, 10), 180), at(3, 14))

        def test_resumed(self):
            ev = [(at(3, 10), "open"), (at(3, 11), "pause"), (at(4, 9), "resume")]
            self.assertEqual(projected_deadline(DESK, ev, at(4, 9, 30), 120), at(4, 10))
            self.assertEqual(projected_deadline(DESK, ev, at(4, 8), 120), None)

        def test_target_already_used(self):
            ev = [(at(3, 10), "open")]
            self.assertEqual(projected_deadline(DESK, ev, at(3, 14), 120), at(3, 14))
            self.assertEqual(projected_deadline(DESK, ev, at(3, 14), 0), at(3, 14))

        def test_not_running(self):
            paused = [(at(3, 10), "open"), (at(3, 11), "pause")]
            closed = [(at(3, 10), "open"), (at(3, 11), "close")]
            self.assertIsNone(projected_deadline(DESK, paused, at(3, 12), 120))
            self.assertIsNone(projected_deadline(DESK, closed, at(3, 12), 120))
            self.assertIsNone(projected_deadline(DESK, [], at(3, 12), 120))
            self.assertIsNone(projected_deadline(DESK, [(at(3, 13), "open")], at(3, 12), 120))


    if __name__ == "__main__":
        unittest.main()
''')

SLACLOCK = Lib(
    name="slaclock", lang="python", title="the support-desk SLA clock (`slaclock/`)",
    blurb="The support desk's ticketing tool uses slaclock to count how much of a ticket's SLA target is used up.",
    files={"slaclock/__init__.py": "", "slaclock/spec.py": SC_SPEC, "slaclock/schedule.py": SC_SCHEDULE,
           "slaclock/clock.py": SC_CLOCK, "README.md": SC_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": SC_VISIBLE},
    hidden_tests={"tests/test_full.py": SC_HIDDEN},
    mutate=["slaclock/spec.py", "slaclock/schedule.py", "slaclock/clock.py"], difficulty=4,
    tags=["sla", "business-hours", "scheduling"],
    probes=[
        "parse_hhmm('24:00')", "parse_hhmm('24:01')", "parse_window('09:00-09:00')", "parse_days('fri-mon')",
        "parse_days('mon,wed-fri')",
        "DESK.minutes_between(datetime(2025, 3, 7, 16), datetime(2025, 3, 10, 10))",
        "DESK.minutes_between(datetime(2025, 3, 3, 11, 59), datetime(2025, 3, 3, 13, 1))",
        "DESK.add_minutes(datetime(2025, 3, 3, 9), 180)", "DESK.add_minutes(datetime(2025, 3, 3, 9), 181)",
        "DESK.add_minutes(datetime(2025, 3, 3, 18), 30)",
        "sla_elapsed(DESK, [(datetime(2025, 3, 3, 10), 'open'), (datetime(2025, 3, 3, 11), 'pause'), (datetime(2025, 3, 4, 9), 'resume')], datetime(2025, 3, 4, 9, 30))",
        "sla_status(DESK, [(datetime(2025, 3, 3, 9), 'open')], datetime(2025, 3, 3, 11), 120)",
        "sla_status(DESK, [(datetime(2025, 3, 3, 9), 'open'), (datetime(2025, 3, 3, 11), 'close')], datetime(2025, 3, 3, 15), 120)",
        "projected_deadline(DESK, [(datetime(2025, 3, 3, 10), 'open')], datetime(2025, 3, 3, 11, 30), 120)",
    ],
    probe_import=("from datetime import datetime\nfrom slaclock.spec import *\nfrom slaclock.schedule import *\nfrom slaclock.clock import *\n"
                  "DESK = Schedule.from_spec({'mon-fri': ['09:00-12:00', '13:00-17:00']})"),
)

register_libs([WORKCAL, SLACLOCK], n=10)
