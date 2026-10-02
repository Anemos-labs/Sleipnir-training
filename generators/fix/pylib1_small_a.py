"""Python libraries, theme time/money/scheduling (batch small-a): timesheet rounding, library fines, taxi fares,
utility-bill split. Deliberately small single-module libraries."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# punchclock: timesheet rounding with a 6 minute grid, schedule snapping, automatic lunch
# ======================================================================================================================

PC_README = dd('''
    # punchclock

    Timesheet rounding for a factory time clock. All times are whole minutes since midnight; hours are counted in
    tenths of an hour (6 minutes).

    * `round_in(punch, sched_start)`: a punch up to 7 minutes before the scheduled start (inclusive, so
      `sched_start - 7 <= punch <= sched_start`) snaps to `sched_start`. Any other punch is rounded to the **nearest**
      multiple of 6 minutes; a punch exactly half way (3 minutes past a multiple) goes to the later one.
    * `round_out(punch, sched_end)`: a punch up to 7 minutes after the scheduled end (`sched_end <= punch <=
      sched_end + 7`) snaps to `sched_end`. Any other punch is rounded **down** to a multiple of 6 minutes.
    * `paid_minutes(punch_in, punch_out, sched_start, sched_end)`: the rounded out time minus the rounded in time.
      If that is zero or negative the result is `0`. A day of at least 300 minutes loses a 30 minute unpaid lunch.
    * `tenths(minutes)`: minutes converted to tenths of an hour, rounded half up (`3` minutes is one tenth).
    * `week_hours(days)`: `days` is a list of `(punch_in, punch_out, sched_start, sched_end)`. Every day is converted
      with `tenths(paid_minutes(...))` and the days are added up. Returns `{"tenths": total, "regular": min(total,
      400), "overtime": the rest}`.
    * `format_hours(tenths)`: `75` is `"7.5"`, `0` is `"0.0"`, `1234` is `"123.4"`.
''')

PC_SRC = dd('''
    GRID = 6
    SNAP = 7
    LUNCH_AFTER = 300
    LUNCH = 30
    WEEK_LIMIT = 400


    def round_in(punch, sched_start):
        if sched_start - SNAP <= punch <= sched_start:
            return sched_start
        return (punch + GRID // 2) // GRID * GRID


    def round_out(punch, sched_end):
        if sched_end <= punch <= sched_end + SNAP:
            return sched_end
        return punch // GRID * GRID


    def paid_minutes(punch_in, punch_out, sched_start, sched_end):
        start = round_in(punch_in, sched_start)
        end = round_out(punch_out, sched_end)
        if end <= start:
            return 0
        length = end - start
        if length >= LUNCH_AFTER:
            length -= LUNCH
        return length


    def tenths(minutes):
        return (minutes + GRID // 2) // GRID


    def week_hours(days):
        total = 0
        for punch_in, punch_out, sched_start, sched_end in days:
            total += tenths(paid_minutes(punch_in, punch_out, sched_start, sched_end))
        regular = min(total, WEEK_LIMIT)
        return {"tenths": total, "regular": regular, "overtime": total - regular}


    def format_hours(value):
        whole, frac = divmod(value, 10)
        return str(whole) + "." + str(frac)
''')

PC_VISIBLE = dd('''
    import unittest

    from punchclock.rounding import format_hours, paid_minutes, round_in, round_out


    class BasicTests(unittest.TestCase):
        def test_round_in_snaps(self):
            self.assertEqual(round_in(535, 540), 540)

        def test_round_out_down(self):
            self.assertEqual(round_out(1031, 1020), 1026)

        def test_full_day(self):
            self.assertEqual(paid_minutes(535, 1023, 540, 1020), 450)

        def test_format(self):
            self.assertEqual(format_hours(75), "7.5")


    if __name__ == "__main__":
        unittest.main()
''')

PC_HIDDEN = dd('''
    import unittest

    from punchclock.rounding import format_hours, paid_minutes, round_in, round_out, tenths, week_hours


    class RoundIn(unittest.TestCase):
        def test_early_snaps_to_schedule(self):
            for punch in (533, 534, 535, 539, 540):
                self.assertEqual(round_in(punch, 540), 540, punch)

        def test_too_early_goes_to_the_grid(self):
            table = {532: 534, 531: 534, 530: 528, 529: 528, 500: 498, 0: 0, 2: 0, 3: 6}
            for punch, want in table.items():
                self.assertEqual(round_in(punch, 540), want, punch)

        def test_late_punches_round_to_nearest_ties_later(self):
            table = {541: 540, 542: 540, 543: 546, 544: 546, 545: 546, 546: 546, 547: 546, 548: 546, 549: 552, 560: 558}
            for punch, want in table.items():
                self.assertEqual(round_in(punch, 540), want, punch)

        def test_schedule_off_the_grid(self):
            self.assertEqual(round_in(540, 545), 545)
            self.assertEqual(round_in(538, 545), 545)
            self.assertEqual(round_in(537, 545), 540)
            self.assertEqual(round_in(546, 545), 546)
            self.assertEqual(round_in(545, 545), 545)


    class RoundOut(unittest.TestCase):
        def test_late_snaps_to_schedule(self):
            for punch in (1020, 1021, 1025, 1026, 1027):
                self.assertEqual(round_out(punch, 1020), 1020, punch)

        def test_beyond_the_snap_window(self):
            table = {1028: 1026, 1031: 1026, 1032: 1032, 1100: 1098}
            for punch, want in table.items():
                self.assertEqual(round_out(punch, 1020), want, punch)

        def test_leaving_early_rounds_down(self):
            table = {1019: 1014, 1018: 1014, 1014: 1014, 1013: 1008, 600: 600, 601: 600, 605: 600}
            for punch, want in table.items():
                self.assertEqual(round_out(punch, 1020), want, punch)

        def test_schedule_off_the_grid(self):
            self.assertEqual(round_out(1022, 1021), 1021)
            self.assertEqual(round_out(1028, 1021), 1021)
            self.assertEqual(round_out(1029, 1021), 1026)
            self.assertEqual(round_out(1020, 1021), 1020)


    class Paid(unittest.TestCase):
        def test_full_day_with_lunch(self):
            self.assertEqual(paid_minutes(535, 1023, 540, 1020), 450)
            self.assertEqual(paid_minutes(540, 1020, 540, 1020), 450)

        def test_lunch_threshold(self):
            self.assertEqual(paid_minutes(540, 839, 540, 1020), 294)
            self.assertEqual(paid_minutes(540, 840, 540, 1020), 270)
            self.assertEqual(paid_minutes(540, 845, 540, 1020), 270)
            self.assertEqual(paid_minutes(540, 846, 540, 1020), 276)

        def test_late_arrival_and_early_exit(self):
            # in at 09:15 rounds to 09:18 (558), out at 16:40 rounds down to 16:36 (996): 438 minutes less lunch
            self.assertEqual(paid_minutes(555, 1000, 540, 1020), 408)
            self.assertEqual(paid_minutes(543, 1000, 540, 1020), 420)

        def test_nothing_or_negative(self):
            self.assertEqual(paid_minutes(600, 600, 540, 1020), 0)
            self.assertEqual(paid_minutes(600, 590, 540, 1020), 0)
            self.assertEqual(paid_minutes(600, 603, 540, 1020), 0)
            self.assertEqual(paid_minutes(600, 606, 540, 1020), 6)

        def test_schedule_snaps_on_both_ends(self):
            self.assertEqual(paid_minutes(300, 1200, 300, 1200), 870)


    class Tenths(unittest.TestCase):
        def test_values(self):
            table = {0: 0, 1: 0, 2: 0, 3: 1, 5: 1, 6: 1, 8: 1, 9: 2, 450: 75, 449: 75, 446: 74, 447: 75}
            for minutes, want in table.items():
                self.assertEqual(tenths(minutes), want, minutes)


    class Week(unittest.TestCase):
        DAY = (535, 1023, 540, 1020)

        def test_five_days(self):
            got = week_hours([self.DAY] * 5)
            self.assertEqual(got, {"tenths": 375, "regular": 375, "overtime": 0})

        def test_six_days(self):
            got = week_hours([self.DAY] * 6)
            self.assertEqual(got, {"tenths": 450, "regular": 400, "overtime": 50})

        def test_exactly_forty(self):
            got = week_hours([(540, 1050, 540, 1050)] * 5)
            self.assertEqual(got, {"tenths": 400, "regular": 400, "overtime": 0})
            got = week_hours([(540, 1050, 540, 1050)] * 4 + [(540, 1056, 540, 1050)])
            self.assertEqual(got, {"tenths": 400, "regular": 400, "overtime": 0})
            got = week_hours([(540, 1050, 540, 1050)] * 4 + [(540, 1080, 540, 1050)])
            self.assertEqual(got, {"tenths": 405, "regular": 400, "overtime": 5})

        def test_days_are_rounded_one_by_one(self):
            # a 15 minute day is 3 tenths (2.5 rounds up); three of them are 9 tenths, not 45 minutes = 8 tenths
            got = week_hours([(541, 556, 541, 556)] * 3)
            self.assertEqual(got["tenths"], 9)

        def test_empty_week(self):
            self.assertEqual(week_hours([]), {"tenths": 0, "regular": 0, "overtime": 0})

        def test_mixed_days(self):
            days = [(535, 1023, 540, 1020), (543, 1000, 540, 1020), (540, 839, 540, 1020), (600, 590, 540, 1020)]
            got = week_hours(days)
            self.assertEqual(got["tenths"], 75 + 70 + 49 + 0)


    class Format(unittest.TestCase):
        def test_values(self):
            table = {0: "0.0", 5: "0.5", 10: "1.0", 75: "7.5", 400: "40.0", 405: "40.5", 1234: "123.4"}
            for value, text in table.items():
                self.assertEqual(format_hours(value), text, value)


    if __name__ == "__main__":
        unittest.main()
''')

PUNCHCLOCK = Lib(
    name="punchclock", lang="python", title="the timesheet rounding rules (`punchclock/rounding.py`)",
    blurb="The factory's time clock turns raw punches into paid time with the punchclock helpers.",
    files={"punchclock/__init__.py": "", "punchclock/rounding.py": PC_SRC, "README.md": PC_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": PC_VISIBLE},
    hidden_tests={"tests/test_full.py": PC_HIDDEN},
    mutate=["punchclock/rounding.py"], difficulty=1, tags=["timesheet", "rounding"],
    probes=[
        "round_in(532, 540)", "round_in(543, 540)", "round_in(542, 540)", "round_out(1027, 1020)", "round_out(1028, 1020)",
        "round_out(1019, 1020)", "paid_minutes(540, 839, 540, 1020)", "paid_minutes(540, 840, 540, 1020)",
        "paid_minutes(600, 590, 540, 1020)", "tenths(3)", "tenths(2)", "tenths(449)", "format_hours(1234)",
        "week_hours([(535, 1023, 540, 1020)] * 6)",
    ],
    probe_import="from punchclock.rounding import *",
)

# ======================================================================================================================
# libfines: overdue fines for a public library
# ======================================================================================================================

LF_README = dd('''
    # libfines

    Overdue fines for the Marlow public library. Money is an `int` number of cents; dates are `datetime.date`.

    * `open_days(due, returned, closed=(6,), holidays=())`: the number of days in the half-open range
      `(due, returned]` (the due date itself is not counted, the return date is) on which the library was open: not
      on a `closed` weekday (Monday is `0`; by default only Sunday is closed) and not in `holidays`. Returning on or
      before the due date gives `0`.
    * `charged_days(days_open)`: the first 2 open overdue days are a grace period: `max(0, days_open - 2)`.
    * `item_fine(kind, days)`: `days * rate`, but never more than the item's cap. Rates per day and caps in cents:
      `book` 20 / 1500, `magazine` 10 / 500, `dvd` 100 / 2000, `tool` 250 / 5000. An unknown kind is a `ValueError`
      (even for 0 days).
    * `member_fine(kind, due, returned, category="adult", closed=(6,), holidays=())`: the fine for one loan after the
      member's discount. Discounts in percent: `adult` 0, `senior` 50, `child` 75, `staff` 100. The discount amount is
      rounded **down** (`fine * percent // 100`) and subtracted. An unknown category is a `ValueError`.
    * `account(items, category="adult", closed=(6,), holidays=())`: `items` is a list of `(kind, due, returned)`.
      Returns `(total, blocked)`: the sum of the member fines and whether it reaches 1000 cents (a member with
      1000 or more owed cannot borrow).
''')

LF_SRC = dd('''
    from datetime import timedelta

    RATE = {"book": 20, "magazine": 10, "dvd": 100, "tool": 250}
    CAP = {"book": 1500, "magazine": 500, "dvd": 2000, "tool": 5000}
    GRACE_DAYS = 2
    BLOCK_AT = 1000
    DISCOUNT = {"adult": 0, "senior": 50, "child": 75, "staff": 100}


    def open_days(due, returned, closed=(6,), holidays=()):
        count = 0
        day = due + timedelta(days=1)
        while day <= returned:
            if day.weekday() not in closed and day not in holidays:
                count += 1
            day += timedelta(days=1)
        return count


    def charged_days(days_open):
        return max(0, days_open - GRACE_DAYS)


    def item_fine(kind, days):
        if kind not in RATE:
            raise ValueError(f"unknown item kind {kind!r}")
        return min(CAP[kind], RATE[kind] * days)


    def member_fine(kind, due, returned, category="adult", closed=(6,), holidays=()):
        if category not in DISCOUNT:
            raise ValueError(f"unknown member category {category!r}")
        fine = item_fine(kind, charged_days(open_days(due, returned, closed, holidays)))
        return fine - fine * DISCOUNT[category] // 100


    def account(items, category="adult", closed=(6,), holidays=()):
        total = 0
        for kind, due, returned in items:
            total += member_fine(kind, due, returned, category, closed, holidays)
        return total, total >= BLOCK_AT
''')

LF_VISIBLE = dd('''
    import unittest
    from datetime import date

    from libfines.fines import charged_days, item_fine, open_days


    class BasicTests(unittest.TestCase):
        def test_open_days_skips_sunday(self):
            self.assertEqual(open_days(date(2025, 3, 7), date(2025, 3, 10)), 2)

        def test_grace(self):
            self.assertEqual(charged_days(2), 0)

        def test_book_rate(self):
            self.assertEqual(item_fine("book", 10), 200)


    if __name__ == "__main__":
        unittest.main()
''')

LF_HIDDEN = dd('''
    import unittest
    from datetime import date, timedelta

    from libfines.fines import account, charged_days, item_fine, member_fine, open_days

    D = date
    FRI = D(2025, 3, 7)


    class OpenDays(unittest.TestCase):
        def test_default_closing(self):
            self.assertEqual(open_days(FRI, D(2025, 3, 8)), 1)
            self.assertEqual(open_days(FRI, D(2025, 3, 9)), 1)
            self.assertEqual(open_days(FRI, D(2025, 3, 10)), 2)
            self.assertEqual(open_days(FRI, D(2025, 3, 14)), 6)

        def test_not_overdue(self):
            self.assertEqual(open_days(FRI, FRI), 0)
            self.assertEqual(open_days(FRI, D(2025, 3, 1)), 0)

        def test_due_day_is_not_counted_return_day_is(self):
            self.assertEqual(open_days(D(2025, 3, 6), D(2025, 3, 7)), 1)
            self.assertEqual(open_days(D(2025, 3, 7), D(2025, 3, 8)), 1)

        def test_custom_closed_days(self):
            self.assertEqual(open_days(FRI, D(2025, 3, 8), closed=(5, 6)), 0)
            self.assertEqual(open_days(FRI, D(2025, 3, 10), closed=(5, 6)), 1)
            self.assertEqual(open_days(FRI, D(2025, 3, 10), closed=()), 3)
            self.assertEqual(open_days(FRI, D(2025, 3, 14), closed=(0, 1, 2)), 4)  # Sat, Sun, Thu, Fri

        def test_holidays(self):
            self.assertEqual(open_days(FRI, D(2025, 3, 10), holidays={D(2025, 3, 10)}), 1)
            self.assertEqual(open_days(FRI, D(2025, 3, 14), holidays={D(2025, 3, 11)}), 5)
            self.assertEqual(open_days(FRI, D(2025, 3, 14), holidays=[D(2025, 3, 11), D(2025, 3, 12)]), 4)

        def test_holiday_on_a_closed_day_counts_once(self):
            self.assertEqual(open_days(FRI, D(2025, 3, 10), holidays={D(2025, 3, 9)}), 2)

        def test_holiday_on_the_due_date_or_outside_is_ignored(self):
            self.assertEqual(open_days(FRI, D(2025, 3, 10), holidays={FRI, D(2025, 3, 11), D(2025, 3, 1)}), 2)


    class Charged(unittest.TestCase):
        def test_grace(self):
            table = {0: 0, 1: 0, 2: 0, 3: 1, 4: 2, 10: 8}
            for open_, charged in table.items():
                self.assertEqual(charged_days(open_), charged, open_)


    class ItemFine(unittest.TestCase):
        def test_rates(self):
            self.assertEqual(item_fine("book", 0), 0)
            self.assertEqual(item_fine("book", 10), 200)
            self.assertEqual(item_fine("magazine", 10), 100)
            self.assertEqual(item_fine("dvd", 4), 400)
            self.assertEqual(item_fine("tool", 4), 1000)

        def test_caps(self):
            table = [("book", 75, 1500), ("book", 76, 1500), ("book", 74, 1480), ("magazine", 50, 500), ("magazine", 51, 500),
                     ("magazine", 49, 490), ("dvd", 20, 2000), ("dvd", 21, 2000), ("dvd", 19, 1900), ("tool", 20, 5000),
                     ("tool", 21, 5000), ("tool", 19, 4750), ("tool", 400, 5000)]
            for kind, days, want in table:
                self.assertEqual(item_fine(kind, days), want, (kind, days))

        def test_unknown_kind(self):
            for kind in ("cd", "", "Book"):
                with self.assertRaises(ValueError, msg=kind):
                    item_fine(kind, 0)
                with self.assertRaises(ValueError, msg=kind):
                    item_fine(kind, 5)


    class MemberFine(unittest.TestCase):
        RETURN = D(2025, 3, 14)  # six open days after FRI, so four are charged

        def test_adult(self):
            self.assertEqual(member_fine("dvd", FRI, self.RETURN), 400)
            self.assertEqual(member_fine("book", FRI, self.RETURN), 80)
            self.assertEqual(member_fine("book", FRI, self.RETURN, "adult"), 80)

        def test_discounts(self):
            self.assertEqual(member_fine("dvd", FRI, self.RETURN, "senior"), 200)
            self.assertEqual(member_fine("dvd", FRI, self.RETURN, "child"), 100)
            self.assertEqual(member_fine("dvd", FRI, self.RETURN, "staff"), 0)

        def test_discount_rounds_down_so_the_member_pays_more(self):
            third = D(2025, 3, 11)  # open days 8, 10, 11 minus the grace period: one charged day
            self.assertEqual(open_days(FRI, third), 3)
            self.assertEqual(member_fine("magazine", FRI, third), 10)
            self.assertEqual(member_fine("magazine", FRI, third, "child"), 3)
            self.assertEqual(member_fine("magazine", FRI, third, "senior"), 5)
            self.assertEqual(member_fine("book", FRI, third, "child"), 5)
            self.assertEqual(member_fine("book", FRI, third, "senior"), 10)

        def test_grace_period(self):
            self.assertEqual(member_fine("dvd", FRI, D(2025, 3, 10)), 0)
            self.assertEqual(member_fine("dvd", FRI, D(2025, 3, 11)), 100)
            self.assertEqual(member_fine("dvd", FRI, FRI), 0)

        def test_closed_days_and_holidays_are_passed_on(self):
            self.assertEqual(member_fine("dvd", FRI, self.RETURN, closed=(5, 6)), 300)
            self.assertEqual(member_fine("dvd", FRI, self.RETURN, holidays={D(2025, 3, 12)}), 300)

        def test_cap_applies_before_the_discount(self):
            late = FRI + timedelta(days=60)
            self.assertEqual(member_fine("dvd", FRI, late, closed=()), 2000)
            self.assertEqual(member_fine("dvd", FRI, late, "senior", closed=()), 1000)
            self.assertEqual(member_fine("dvd", FRI, late, "child", closed=()), 500)

        def test_unknown_category(self):
            with self.assertRaises(ValueError):
                member_fine("book", FRI, self.RETURN, "visitor")
            with self.assertRaises(ValueError):
                member_fine("book", FRI, FRI, "visitor")


    class Account(unittest.TestCase):
        def test_empty(self):
            self.assertEqual(account([]), (0, False))

        def test_blocking_threshold(self):
            def loan(kind, extra):
                return (kind, FRI, FRI + timedelta(days=extra))

            self.assertEqual(account([loan("dvd", 12)], closed=()), (1000, True))
            self.assertEqual(account([loan("dvd", 11)], closed=()), (900, False))
            self.assertEqual(account([loan("dvd", 8), loan("dvd", 6)], closed=()), (600 + 400, True))
            self.assertEqual(account([loan("dvd", 8), loan("book", 12)], closed=()), (600 + 200, False))

        def test_category_and_calendar_are_used(self):
            items = [("dvd", FRI, D(2025, 3, 14)), ("book", FRI, D(2025, 3, 14))]
            self.assertEqual(account(items), (480, False))
            self.assertEqual(account(items, "senior"), (240, False))
            self.assertEqual(account(items, closed=(5, 6)), (300 + 60, False))
            self.assertEqual(account(items, holidays={D(2025, 3, 12)}), (300 + 60, False))

        def test_total_is_the_sum_of_discounted_fines(self):
            third = D(2025, 3, 11)
            items = [("magazine", FRI, third), ("magazine", FRI, third), ("book", FRI, third)]
            self.assertEqual(account(items, "child"), (3 + 3 + 5, False))


    if __name__ == "__main__":
        unittest.main()
''')

LIBFINES = Lib(
    name="libfines", lang="python", title="the library overdue-fine rules (`libfines/fines.py`)",
    blurb="The Marlow public library's lending desk computes overdue fines and borrowing blocks with libfines.",
    files={"libfines/__init__.py": "", "libfines/fines.py": LF_SRC, "README.md": LF_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": LF_VISIBLE},
    hidden_tests={"tests/test_full.py": LF_HIDDEN},
    mutate=["libfines/fines.py"], difficulty=2, tags=["library", "fines", "calendar"],
    probes=[
        "open_days(date(2025, 3, 7), date(2025, 3, 10))", "open_days(date(2025, 3, 7), date(2025, 3, 14))",
        "open_days(date(2025, 3, 7), date(2025, 3, 10), closed=(5, 6))",
        "open_days(date(2025, 3, 7), date(2025, 3, 14), holidays={date(2025, 3, 11)})",
        "charged_days(2)", "charged_days(3)", "item_fine('book', 75)", "item_fine('tool', 19)", "item_fine('magazine', 49)",
        "member_fine('dvd', date(2025, 3, 7), date(2025, 3, 14), 'senior')",
        "member_fine('magazine', date(2025, 3, 7), date(2025, 3, 11), 'child')",
        "member_fine('dvd', date(2025, 3, 7), date(2025, 3, 11))",
        "account([('dvd', date(2025, 3, 7), date(2025, 3, 19))], closed=())",
    ],
    probe_import="from datetime import date\nfrom libfines.fines import *",
)

# ======================================================================================================================
# taxifare: taxi meter with tiered distance, waiting time, night surcharge, airport fee and rounding
# ======================================================================================================================

TX_README = dd('''
    # taxifare

    The meter of a city taxi. Money is an `int` number of cents; distances are metres; times of day are minutes since
    midnight.

    * `distance_charge(meters)`: tiered by cumulative distance: the first 5000 m cost 190 cents per km, the next 10000
      m (up to 15000 m) 160 cents per km, everything beyond 140 cents per km. The sum is rounded half up to a whole
      cent.
    * `wait_charge(seconds)`: 15 cents for every **started** 30 seconds of waiting.
    * `is_night(minute)`: from 22:00 (inclusive) until 06:00 (exclusive).
    * `fare(meters, wait_seconds, minute, airport=False)`: the metered part is `distance_charge + wait_charge`. At
      night it is increased by 20% (rounded half up to a cent). The total is the flag fall of 350 cents plus the metered
      part plus 400 cents when `airport` is true. The total is at least 600 cents, and is finally rounded half up to a
      multiple of 10 cents.
''')

TX_SRC = dd('''
    FLAG_FALL = 350
    TIERS = [(5000, 190), (15000, 160), (None, 140)]
    WAIT_UNIT = 30
    WAIT_RATE = 15
    NIGHT_FROM = 22 * 60
    NIGHT_TO = 6 * 60
    NIGHT_PERCENT = 20
    AIRPORT_FEE = 400
    MIN_FARE = 600


    def distance_charge(meters):
        total = 0
        low = 0
        for limit, per_km in TIERS:
            if meters <= low:
                break
            high = meters if limit is None else min(meters, limit)
            total += (high - low) * per_km
            low = high
        return (2 * total + 1000) // 2000


    def wait_charge(seconds):
        return -(-seconds // WAIT_UNIT) * WAIT_RATE


    def is_night(minute):
        return minute >= NIGHT_FROM or minute < NIGHT_TO


    def fare(meters, wait_seconds, minute, airport=False):
        metered = distance_charge(meters) + wait_charge(wait_seconds)
        if is_night(minute):
            metered = (metered * (100 + NIGHT_PERCENT) + 50) // 100
        total = FLAG_FALL + metered
        if airport:
            total += AIRPORT_FEE
        total = max(total, MIN_FARE)
        return (total + 5) // 10 * 10
''')

TX_VISIBLE = dd('''
    import unittest

    from taxifare.meter import distance_charge, fare, wait_charge


    class BasicTests(unittest.TestCase):
        def test_first_tier(self):
            self.assertEqual(distance_charge(1000), 190)

        def test_wait(self):
            self.assertEqual(wait_charge(30), 15)

        def test_minimum_fare(self):
            self.assertEqual(fare(0, 0, 720), 600)


    if __name__ == "__main__":
        unittest.main()
''')

TX_HIDDEN = dd('''
    import unittest

    from taxifare.meter import distance_charge, fare, is_night, wait_charge


    class Distance(unittest.TestCase):
        def test_tier_boundaries(self):
            table = {0: 0, 1000: 190, 5000: 950, 5001: 950, 6000: 1110, 10_000: 1750, 15_000: 2550, 15_001: 2550,
                     16_000: 2690, 20_000: 3250}
            for meters, cents in table.items():
                self.assertEqual(distance_charge(meters), cents, meters)

        def test_rounding_half_up(self):
            table = {1: 0, 2: 0, 3: 1, 50: 10, 150: 29, 49: 9, 51: 10}
            for meters, cents in table.items():
                self.assertEqual(distance_charge(meters), cents, meters)

        def test_second_tier_rounding(self):
            # 5000 m = 950.00, then 3 m * 0.16 = 0.48 -> 950.48 -> 950 ; 4 m = 0.64 -> 950.64 -> 951
            self.assertEqual(distance_charge(5003), 950)
            self.assertEqual(distance_charge(5004), 951)
            self.assertEqual(distance_charge(5003 + 10_000), 2550)
            self.assertEqual(distance_charge(15_004), 2551)


    class Wait(unittest.TestCase):
        def test_started_units(self):
            table = {0: 0, 1: 15, 29: 15, 30: 15, 31: 30, 60: 30, 61: 45, 300: 150}
            for seconds, cents in table.items():
                self.assertEqual(wait_charge(seconds), cents, seconds)


    class Night(unittest.TestCase):
        def test_edges(self):
            table = {0: True, 359: True, 360: False, 720: False, 1319: False, 1320: True, 1439: True}
            for minute, night in table.items():
                self.assertEqual(is_night(minute), night, minute)


    class Fare(unittest.TestCase):
        def test_minimum(self):
            self.assertEqual(fare(0, 0, 720), 600)
            self.assertEqual(fare(1000, 0, 720), 600)
            self.assertEqual(fare(1200, 0, 720), 600)

        def test_just_above_the_minimum(self):
            self.assertEqual(fare(1400, 0, 720), 620)
            self.assertEqual(fare(1350, 0, 720), 610)
            self.assertEqual(fare(1340, 0, 720), 610)
            self.assertEqual(fare(1330, 0, 720), 600)

        def test_plain_trips(self):
            self.assertEqual(fare(3000, 0, 720), 920)
            self.assertEqual(fare(20_000, 0, 720), 3600)
            self.assertEqual(fare(5000, 0, 720), 1300)

        def test_waiting(self):
            self.assertEqual(fare(3000, 90, 720), 970)
            self.assertEqual(fare(3000, 60, 720), 950)
            self.assertEqual(fare(3000, 1, 720), 940)

        def test_final_rounding_half_up_to_ten(self):
            self.assertEqual(fare(3000, 90, 720), 970)   # 965 -> 970
            self.assertEqual(fare(3000, 0, 720), 920)    # 920
            self.assertEqual(fare(2973, 0, 720), 920)    # 350 + 565 = 915 -> 920
            self.assertEqual(fare(2900, 0, 720), 900)    # 350 + 551 = 901 -> 900

        def test_night(self):
            self.assertEqual(fare(3000, 0, 1400), 1030)
            self.assertEqual(fare(3000, 0, 100), 1030)
            self.assertEqual(fare(3000, 0, 359), 1030)
            self.assertEqual(fare(3000, 0, 360), 920)
            self.assertEqual(fare(3000, 0, 1319), 920)
            self.assertEqual(fare(3000, 0, 1320), 1030)

        def test_night_surcharge_rounds_half_up_on_the_metered_part(self):
            # 1234 m = 234 cents; x1.2 = 280.8 -> 281; total 631 -> 630 ; by day 584 -> minimum 600
            self.assertEqual(fare(1234, 0, 1400), 630)
            self.assertEqual(fare(1234, 0, 720), 600)
            self.assertEqual(fare(2000, 0, 1400), 810)   # 380 * 1.2 = 456; 350 + 456 = 806 -> 810

        def test_night_surcharge_does_not_touch_the_flag_or_airport_fee(self):
            self.assertEqual(fare(0, 0, 1400, airport=True), 750)
            self.assertEqual(fare(3000, 0, 1400, airport=True), 1430)

        def test_airport(self):
            self.assertEqual(fare(3000, 0, 720, airport=True), 1320)
            self.assertEqual(fare(0, 0, 720, airport=True), 750)
            self.assertEqual(fare(0, 0, 720, airport=False), 600)

        def test_minimum_is_applied_before_rounding(self):
            self.assertEqual(fare(1190, 0, 720), 600)   # 350 + 226 = 576 -> 600
            self.assertEqual(fare(1250, 0, 720), 600)   # 350 + 238 = 588 -> 600
            self.assertEqual(fare(1320, 0, 720), 600)   # 350 + 251 = 601 is above the minimum but rounds to 600


    if __name__ == "__main__":
        unittest.main()
''')

TAXIFARE = Lib(
    name="taxifare", lang="python", title="the taxi meter (`taxifare/meter.py`)",
    blurb="The city's taxi meters price each ride with the taxifare module.",
    files={"taxifare/__init__.py": "", "taxifare/meter.py": TX_SRC, "README.md": TX_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": TX_VISIBLE},
    hidden_tests={"tests/test_full.py": TX_HIDDEN},
    mutate=["taxifare/meter.py"], difficulty=1, tags=["taxi", "tariff", "rounding"],
    probes=[
        "distance_charge(5001)", "distance_charge(5003)", "distance_charge(6000)", "distance_charge(15_000)", "distance_charge(20_000)",
        "distance_charge(50)", "wait_charge(30)", "wait_charge(31)", "is_night(1320)", "is_night(360)",
        "fare(3000, 90, 720)", "fare(3000, 0, 1400)", "fare(1234, 0, 1400)", "fare(0, 0, 720, airport=True)", "fare(1000, 0, 720)",
    ],
    probe_import="from taxifare.meter import *",
)

register_libs([PUNCHCLOCK, LIBFINES, TAXIFARE], n=10)
