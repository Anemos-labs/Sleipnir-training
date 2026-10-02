"""Python libraries, theme time/money/scheduling (batch misc-a): hotel seasonal pricing, vaccination dose intervals,
leave accrual."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# stayprice: hotel prices with year-wrapping seasons, weekend uplift, minimum stays, weekly discount and tourist tax
# ======================================================================================================================

SP_README = dd('''
    # stayprice

    Room pricing for the Gull Cove hotel. Money is an `int` number of cents; dates are `datetime.date`. A night belongs to
    the date on which the guest checks in for it (a stay from the 3rd for two nights has the nights of the 3rd and 4th).

    ## Seasons (`stayprice/seasons.py`)

    `season_of(d)` returns the season of a date (the year does not matter), checking the periods in this order:

    1. `festive`: 20 December to 5 January (both included);
    2. `high`: 15 June to 10 September (both included);
    3. `shoulder`: 1 April to 14 June, and 11 September to 31 October;
    4. `low`: every other date.

    The price percentages are `festive` 180, `high` 150, `shoulder` 120, `low` 100; the minimum stays (in nights, judged by
    the season of the check-in date) are `festive` 3, `high` 2, others 1. `min_nights(season)` returns the minimum stay.

    * `night_rate(base, d)`: the rate of the night of `d`: `base * percent / 100`; on a Friday or Saturday night a further
      10% is added. Both factors are applied together and the result is rounded half up to a cent **once**.
    * `room_cost(base, checkin, nights)`: the sum of the nightly rates. `nights < 1` is a `ValueError`, and so is a stay
      shorter than the minimum of its check-in season.
    * `weekly_discount(room)`: 10% of the room cost, rounded half up (applies to stays of 7 nights or more).
    * `tourist_tax(adults, nights)`: 150 cents per adult for each of the first 7 nights (children pay nothing).
    * `quote(base, checkin, nights, adults)`: a dict with `room`, `discount` (the weekly discount when `nights >= 7`, else
      `0`), `tax` and `total` = `room - discount + tax`.
''')

SP_SEASONS = dd('''
    PERCENT = {"festive": 180, "high": 150, "shoulder": 120, "low": 100}
    MIN_NIGHTS = {"festive": 3, "high": 2, "shoulder": 1, "low": 1}
    WEEKEND_PERCENT = 110


    def season_of(d):
        md = (d.month, d.day)
        if md >= (12, 20) or md <= (1, 5):
            return "festive"
        if (6, 15) <= md <= (9, 10):
            return "high"
        if (4, 1) <= md <= (10, 31):
            return "shoulder"
        return "low"


    def min_nights(season):
        return MIN_NIGHTS[season]


    def night_rate(base, d):
        percent = PERCENT[season_of(d)]
        weekend = WEEKEND_PERCENT if d.weekday() in (4, 5) else 100
        return (2 * base * percent * weekend + 10_000) // 20_000
''')

SP_PRICING = dd('''
    from datetime import timedelta

    from .seasons import min_nights, night_rate, season_of

    DISCOUNT_FROM_NIGHTS = 7
    DISCOUNT_PERCENT = 10
    TAX_PER_NIGHT = 150
    TAX_NIGHTS = 7


    def room_cost(base, checkin, nights):
        if nights < 1:
            raise ValueError("a stay lasts at least one night")
        if nights < min_nights(season_of(checkin)):
            raise ValueError("stay is shorter than the minimum for this season")
        return sum(night_rate(base, checkin + timedelta(days=i)) for i in range(nights))


    def weekly_discount(room):
        return (2 * room * DISCOUNT_PERCENT + 100) // 200


    def tourist_tax(adults, nights):
        return TAX_PER_NIGHT * adults * min(nights, TAX_NIGHTS)


    def quote(base, checkin, nights, adults):
        room = room_cost(base, checkin, nights)
        discount = weekly_discount(room) if nights >= DISCOUNT_FROM_NIGHTS else 0
        tax = tourist_tax(adults, nights)
        return {"room": room, "discount": discount, "tax": tax, "total": room - discount + tax}
''')

SP_VISIBLE = dd('''
    import unittest
    from datetime import date

    from stayprice.pricing import room_cost
    from stayprice.seasons import season_of


    class BasicTests(unittest.TestCase):
        def test_low_season(self):
            self.assertEqual(season_of(date(2025, 2, 10)), "low")

        def test_one_weekday_night(self):
            self.assertEqual(room_cost(10_000, date(2025, 2, 10), 1), 10_000)


    if __name__ == "__main__":
        unittest.main()
''')

SP_HIDDEN = dd('''
    import unittest
    from datetime import date

    from stayprice.pricing import quote, room_cost, tourist_tax, weekly_discount
    from stayprice.seasons import min_nights, night_rate, season_of

    D = date


    class Seasons(unittest.TestCase):
        def test_edges(self):
            table = {D(2025, 12, 19): "low", D(2025, 12, 20): "festive", D(2025, 12, 31): "festive", D(2025, 1, 1): "festive",
                     D(2025, 1, 5): "festive", D(2025, 1, 6): "low", D(2025, 3, 31): "low", D(2025, 4, 1): "shoulder",
                     D(2025, 6, 14): "shoulder", D(2025, 6, 15): "high", D(2025, 9, 10): "high", D(2025, 9, 11): "shoulder",
                     D(2025, 10, 31): "shoulder", D(2025, 11, 1): "low", D(2025, 11, 30): "low", D(2025, 12, 1): "low"}
            for day, season in table.items():
                self.assertEqual(season_of(day), season, day)

        def test_the_year_does_not_matter(self):
            for year in (2024, 2025, 2026, 2028):
                self.assertEqual(season_of(D(year, 12, 25)), "festive")
                self.assertEqual(season_of(D(year, 1, 2)), "festive")
                self.assertEqual(season_of(D(year, 7, 1)), "high")
                self.assertEqual(season_of(D(year, 2, 29 if year % 4 == 0 else 28)), "low")

        def test_minimum_stays(self):
            self.assertEqual([min_nights(s) for s in ("festive", "high", "shoulder", "low")], [3, 2, 1, 1])


    class NightRate(unittest.TestCase):
        def test_weekday_rates(self):
            self.assertEqual(night_rate(10_000, D(2025, 2, 10)), 10_000)     # Monday, low
            self.assertEqual(night_rate(10_000, D(2025, 5, 7)), 12_000)      # Wednesday, shoulder
            self.assertEqual(night_rate(10_000, D(2025, 7, 9)), 15_000)      # Wednesday, high
            self.assertEqual(night_rate(10_000, D(2025, 12, 24)), 18_000)    # Wednesday, festive

        def test_weekend_uplift(self):
            self.assertEqual(night_rate(10_000, D(2025, 2, 14)), 11_000)     # Friday
            self.assertEqual(night_rate(10_000, D(2025, 2, 15)), 11_000)     # Saturday
            self.assertEqual(night_rate(10_000, D(2025, 2, 16)), 10_000)     # Sunday
            self.assertEqual(night_rate(10_000, D(2025, 2, 13)), 10_000)     # Thursday
            self.assertEqual(night_rate(10_000, D(2025, 7, 11)), 16_500)     # Friday, high
            self.assertEqual(night_rate(10_000, D(2025, 12, 27)), 19_800)    # Saturday, festive

        def test_rounded_once_half_up(self):
            # 9999 * 1.2 * 1.1 = 13198.68 ; 4999 * 1.5 = 7498.5 ; 5 * 1.1 = 5.5 ; 1 * 1.1 = 1.1
            self.assertEqual(night_rate(9999, D(2025, 5, 9)), 13_199)
            self.assertEqual(night_rate(4999, D(2025, 7, 9)), 7499)
            self.assertEqual(night_rate(5, D(2025, 2, 14)), 6)
            self.assertEqual(night_rate(1, D(2025, 2, 14)), 1)
            self.assertEqual(night_rate(3, D(2025, 7, 11)), 5)               # 3 * 1.5 * 1.1 = 4.95


    class RoomCost(unittest.TestCase):
        def test_stay_over_a_weekend(self):
            # Thursday 13 Feb: Thu 10000, Fri 11000, Sat 11000, Sun 10000
            self.assertEqual(room_cost(10_000, D(2025, 2, 13), 4), 42_000)
            self.assertEqual(room_cost(10_000, D(2025, 2, 13), 1), 10_000)

        def test_each_night_has_its_own_season(self):
            # nights of 12, 13, ... March are low; 31 March low, 1 April shoulder
            self.assertEqual(room_cost(10_000, D(2025, 3, 30), 3), 10_000 + 10_000 + 12_000)
            self.assertEqual(room_cost(10_000, D(2025, 6, 13), 3), 13_200 + 13_200 + 15_000)   # Fri, Sat (shoulder) and Sun (high)

        def test_year_end(self):
            # 30 Dec (Tue), 31 Dec (Wed), 1 Jan (Thu), all festive
            self.assertEqual(room_cost(10_000, D(2025, 12, 30), 3), 3 * 18_000)

        def test_minimum_stay_follows_the_checkin_date(self):
            with self.assertRaises(ValueError):
                room_cost(10_000, D(2025, 12, 24), 2)
            self.assertEqual(room_cost(10_000, D(2025, 12, 24), 3), 18_000 + 18_000 + 19_800)   # Wed, Thu, Fri
            with self.assertRaises(ValueError):
                room_cost(10_000, D(2025, 7, 9), 1)
            self.assertEqual(room_cost(10_000, D(2025, 7, 9), 2), 15_000 + 15_000)
            self.assertEqual(room_cost(10_000, D(2025, 12, 19), 1), 11_000)    # a Friday, still low season
            self.assertEqual(room_cost(10_000, D(2025, 6, 14), 1), 13_200)    # a Saturday in the shoulder season

        def test_nights_must_be_positive(self):
            for nights in (0, -1):
                with self.assertRaises(ValueError):
                    room_cost(10_000, D(2025, 2, 10), nights)


    class Extras(unittest.TestCase):
        def test_discount(self):
            self.assertEqual(weekly_discount(100_000), 10_000)
            self.assertEqual(weekly_discount(12_345), 1235)    # 1234.5 -> 1235
            self.assertEqual(weekly_discount(12_344), 1234)
            self.assertEqual(weekly_discount(0), 0)

        def test_tax(self):
            self.assertEqual(tourist_tax(2, 3), 900)
            self.assertEqual(tourist_tax(2, 7), 2100)
            self.assertEqual(tourist_tax(2, 8), 2100)
            self.assertEqual(tourist_tax(2, 30), 2100)
            self.assertEqual(tourist_tax(0, 5), 0)
            self.assertEqual(tourist_tax(1, 1), 150)


    class Quote(unittest.TestCase):
        def test_short_stay(self):
            got = quote(10_000, D(2025, 2, 13), 4, 2)
            self.assertEqual(got, {"room": 42_000, "discount": 0, "tax": 1200, "total": 43_200})

        def test_week_long_stay(self):
            got = quote(10_000, D(2025, 2, 10), 7, 2)
            # Mon..Thu 10000, Fri 11000, Sat 11000, Sun 10000
            self.assertEqual(got, {"room": 72_000, "discount": 7200, "tax": 2100, "total": 72_000 - 7200 + 2100})

        def test_six_nights_get_no_discount(self):
            got = quote(10_000, D(2025, 2, 10), 6, 1)
            self.assertEqual((got["room"], got["discount"], got["tax"]), (62_000, 0, 900))

        def test_longer_stay(self):
            got = quote(10_000, D(2025, 2, 10), 10, 2)
            self.assertEqual(got["room"], 102_000)   # Monday to Wednesday of the second week all cost 10000, Fri and Sat 11000
            self.assertEqual(got["discount"], 10_200)
            self.assertEqual(got["tax"], 2100)

        def test_errors_propagate(self):
            with self.assertRaises(ValueError):
                quote(10_000, D(2025, 12, 24), 2, 2)


    if __name__ == "__main__":
        unittest.main()
''')

STAYPRICE = Lib(
    name="stayprice", lang="python", title="the hotel stay pricing (`stayprice/`)",
    blurb="The Gull Cove hotel's booking site prices stays with seasonal rates, weekend uplifts and a tourist tax using stayprice.",
    files={"stayprice/__init__.py": "", "stayprice/seasons.py": SP_SEASONS, "stayprice/pricing.py": SP_PRICING,
           "README.md": SP_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": SP_VISIBLE},
    hidden_tests={"tests/test_full.py": SP_HIDDEN},
    mutate=["stayprice/seasons.py", "stayprice/pricing.py"], difficulty=3, tags=["hotel", "seasons", "pricing"],
    probes=[
        "season_of(date(2025, 12, 19))", "season_of(date(2025, 12, 20))", "season_of(date(2025, 1, 5))", "season_of(date(2025, 1, 6))",
        "season_of(date(2025, 6, 14))", "season_of(date(2025, 9, 11))", "season_of(date(2025, 11, 1))", "min_nights('high')",
        "night_rate(10_000, date(2025, 7, 11))", "night_rate(9999, date(2025, 5, 9))", "night_rate(3, date(2025, 7, 11))",
        "room_cost(10_000, date(2025, 3, 30), 3)", "room_cost(10_000, date(2025, 12, 24), 2)", "weekly_discount(12_345)", "tourist_tax(2, 8)",
        "quote(10_000, date(2025, 2, 10), 7, 2)",
    ],
    probe_import="from datetime import date\nfrom stayprice.seasons import *\nfrom stayprice.pricing import *",
)

# ======================================================================================================================
# dosegap: vaccine series with minimum intervals and a four-day grace period
# ======================================================================================================================

DG_README = dd('''
    # dosegap

    Vaccination-schedule checks for a clinic. Dates are `datetime.date`.

    ## Series (`dosegap/series.py`)

    A series lists, for every dose after the first, `(minimum_days, recommended_days)` counted from the previous **valid**
    dose. The series are `coralvax` (3 doses): `[(28, 42), (150, 180)]`; `tidevax` (2 doses): `[(56, 56)]`; `gullshot`
    (4 doses): `[(7, 14), (14, 28), (180, 365)]`. `get_series(name)` returns the list (`ValueError` for an unknown name).

    * `classify(history, name)`: `history` is the list of dates on which a dose was given, in any order. Returns
      `(valid, invalid)`, both sorted lists of dates. Doses are looked at in date order. The first dose is always valid.
      A later dose is valid when it is given at least `minimum_days - 4` days after the previous **valid** dose (a
      4-day grace period); a dose given too early is invalid and does **not** restart the clock. Once the series is
      complete every further dose is invalid. A dose on the same date as an earlier one is judged like any other.
    * `valid_doses(history, name)` and `invalid_doses(history, name)` are the two lists.
    * `next_window(history, name)`: `(earliest, recommended)`, the first date on which the next dose would count
      (`last valid dose + minimum_days - 4`) and the recommended date (`last valid dose + recommended_days`). `None`
      when no dose has been given or the series is complete.
    * `status(history, name, today)`: `"not_started"` without a valid dose; `"complete"` when the whole series is valid;
      otherwise `"too_early"` before the earliest date, `"due"` from the earliest date up to and including the
      recommended date, and `"overdue"` after it.
    * `days_overdue(history, name, today)`: the days after the recommended date when the status is `overdue`, else `0`.
''')

DG_SERIES = dd('''
    from datetime import timedelta

    GRACE_DAYS = 4
    SERIES = {
        "coralvax": [(28, 42), (150, 180)],
        "tidevax": [(56, 56)],
        "gullshot": [(7, 14), (14, 28), (180, 365)],
    }


    def get_series(name):
        try:
            return SERIES[name]
        except KeyError:
            raise ValueError(f"unknown series {name!r}") from None


    def classify(history, name):
        series = get_series(name)
        valid = []
        invalid = []
        for given in sorted(history):
            if not valid:
                valid.append(given)
            elif len(valid) > len(series):
                invalid.append(given)
            else:
                minimum = series[len(valid) - 1][0]
                if (given - valid[-1]).days >= minimum - GRACE_DAYS:
                    valid.append(given)
                else:
                    invalid.append(given)
        return valid, invalid


    def valid_doses(history, name):
        return classify(history, name)[0]


    def invalid_doses(history, name):
        return classify(history, name)[1]


    def next_window(history, name):
        series = get_series(name)
        valid = valid_doses(history, name)
        if not valid or len(valid) > len(series):
            return None
        minimum, recommended = series[len(valid) - 1]
        last = valid[-1]
        return last + timedelta(days=minimum - GRACE_DAYS), last + timedelta(days=recommended)
''')

DG_STATUS = dd('''
    from .series import get_series, next_window, valid_doses


    def status(history, name, today):
        series = get_series(name)
        valid = valid_doses(history, name)
        if not valid:
            return "not_started"
        if len(valid) > len(series):
            return "complete"
        earliest, recommended = next_window(history, name)
        if today < earliest:
            return "too_early"
        if today <= recommended:
            return "due"
        return "overdue"


    def days_overdue(history, name, today):
        if status(history, name, today) != "overdue":
            return 0
        return (today - next_window(history, name)[1]).days
''')

DG_VISIBLE = dd('''
    import unittest
    from datetime import date

    from dosegap.series import get_series, valid_doses


    class BasicTests(unittest.TestCase):
        def test_series_lengths(self):
            self.assertEqual(len(get_series("tidevax")), 1)

        def test_first_dose_is_valid(self):
            self.assertEqual(valid_doses([date(2025, 1, 1)], "coralvax"), [date(2025, 1, 1)])


    if __name__ == "__main__":
        unittest.main()
''')

DG_HIDDEN = dd('''
    import unittest
    from datetime import date

    from dosegap.series import classify, get_series, invalid_doses, next_window, valid_doses
    from dosegap.status import days_overdue, status

    D = date


    class Series(unittest.TestCase):
        def test_tables(self):
            self.assertEqual(get_series("coralvax"), [(28, 42), (150, 180)])
            self.assertEqual(get_series("tidevax"), [(56, 56)])
            self.assertEqual(get_series("gullshot"), [(7, 14), (14, 28), (180, 365)])

        def test_unknown(self):
            for name in ("", "Coralvax", "mist"):
                with self.assertRaises(ValueError):
                    get_series(name)
                with self.assertRaises(ValueError):
                    classify([D(2025, 1, 1)], name)
                with self.assertRaises(ValueError):
                    next_window([], name)


    class Classify(unittest.TestCase):
        def test_valid_with_grace(self):
            first = D(2025, 1, 1)
            for days, ok in ((23, False), (24, True), (28, True), (60, True)):
                got = classify([first, D.fromordinal(first.toordinal() + days)], "coralvax")
                self.assertEqual(len(got[0]) == 2, ok, days)
                self.assertEqual(len(got[1]) == 0, ok, days)

        def test_early_dose_does_not_restart_the_clock(self):
            history = [D(2025, 1, 1), D(2025, 1, 20), D(2025, 1, 25)]
            self.assertEqual(classify(history, "coralvax"), ([D(2025, 1, 1), D(2025, 1, 25)], [D(2025, 1, 20)]))

        def test_clock_runs_from_the_last_valid_dose(self):
            history = [D(2025, 1, 1), D(2025, 1, 20), D(2025, 2, 10)]
            self.assertEqual(valid_doses(history, "coralvax"), [D(2025, 1, 1), D(2025, 2, 10)])
            self.assertEqual(invalid_doses(history, "coralvax"), [D(2025, 1, 20)])

        def test_full_series_with_grace_everywhere(self):
            history = [D(2025, 1, 1), D(2025, 1, 25), D(2025, 6, 20)]
            self.assertEqual(valid_doses(history, "coralvax"), history)
            self.assertEqual(invalid_doses(history, "coralvax"), [])

        def test_third_dose_boundaries(self):
            base = [D(2025, 1, 1), D(2025, 1, 29)]
            self.assertEqual(len(valid_doses(base + [D(2025, 6, 24)], "coralvax")), 3)    # 146 days after the second dose
            self.assertEqual(len(valid_doses(base + [D(2025, 6, 23)], "coralvax")), 2)    # 145 days: too early
            self.assertEqual(len(valid_doses(base + [D(2025, 7, 28)], "coralvax")), 3)

        def test_surplus_doses_are_invalid(self):
            history = [D(2025, 1, 1), D(2025, 3, 1), D(2025, 4, 1)]
            valid, invalid = classify(history, "tidevax")
            self.assertEqual(valid, [D(2025, 1, 1), D(2025, 3, 1)])
            self.assertEqual(invalid, [D(2025, 4, 1)])

        def test_history_order_and_input(self):
            history = [D(2025, 1, 25), D(2025, 1, 1), D(2025, 1, 20)]
            self.assertEqual(classify(history, "coralvax"), ([D(2025, 1, 1), D(2025, 1, 25)], [D(2025, 1, 20)]))
            self.assertEqual(history, [D(2025, 1, 25), D(2025, 1, 1), D(2025, 1, 20)])

        def test_same_day_twice(self):
            self.assertEqual(classify([D(2025, 1, 1), D(2025, 1, 1)], "coralvax"), ([D(2025, 1, 1)], [D(2025, 1, 1)]))

        def test_empty(self):
            self.assertEqual(classify([], "coralvax"), ([], []))

        def test_short_minimums(self):
            history = [D(2025, 1, 1), D(2025, 1, 4), D(2025, 1, 18)]
            self.assertEqual(valid_doses(history, "gullshot"), [D(2025, 1, 1), D(2025, 1, 4), D(2025, 1, 18)])
            history = [D(2025, 1, 1), D(2025, 1, 3)]
            self.assertEqual(valid_doses(history, "gullshot"), [D(2025, 1, 1)])


    class Window(unittest.TestCase):
        def test_after_the_first_dose(self):
            self.assertEqual(next_window([D(2025, 1, 1)], "coralvax"), (D(2025, 1, 25), D(2025, 2, 12)))
            self.assertEqual(next_window([D(2025, 1, 1)], "tidevax"), (D(2025, 2, 22), D(2025, 2, 26)))

        def test_after_the_second_dose(self):
            self.assertEqual(next_window([D(2025, 1, 1), D(2025, 1, 25)], "coralvax"), (D(2025, 6, 20), D(2025, 7, 24)))

        def test_early_doses_are_ignored(self):
            self.assertEqual(next_window([D(2025, 1, 1), D(2025, 1, 20)], "coralvax"), (D(2025, 1, 25), D(2025, 2, 12)))

        def test_nothing_to_schedule(self):
            self.assertIsNone(next_window([], "coralvax"))
            self.assertIsNone(next_window([D(2025, 1, 1), D(2025, 3, 1)], "tidevax"))
            self.assertIsNone(next_window([D(2025, 1, 1), D(2025, 3, 1), D(2025, 5, 1)], "tidevax"))


    class Status(unittest.TestCase):
        H = [D(2025, 1, 1)]

        def test_phases(self):
            table = {D(2025, 1, 1): "too_early", D(2025, 1, 24): "too_early", D(2025, 1, 25): "due", D(2025, 2, 12): "due",
                     D(2025, 2, 13): "overdue", D(2026, 1, 1): "overdue"}
            for today, want in table.items():
                self.assertEqual(status(self.H, "coralvax", today), want, today)

        def test_not_started_and_complete(self):
            self.assertEqual(status([], "coralvax", D(2025, 1, 1)), "not_started")
            self.assertEqual(status([D(2025, 1, 1), D(2025, 3, 1)], "tidevax", D(2025, 1, 2)), "complete")
            self.assertEqual(status([D(2025, 1, 1), D(2025, 1, 10)], "tidevax", D(2025, 1, 11)), "too_early")

        def test_complete_series_stays_complete(self):
            history = [D(2025, 1, 1), D(2025, 1, 25), D(2025, 6, 20)]
            self.assertEqual(status(history, "coralvax", D(2030, 1, 1)), "complete")

        def test_days_overdue(self):
            self.assertEqual(days_overdue(self.H, "coralvax", D(2025, 2, 12)), 0)
            self.assertEqual(days_overdue(self.H, "coralvax", D(2025, 2, 13)), 1)
            self.assertEqual(days_overdue(self.H, "coralvax", D(2025, 2, 14)), 2)
            self.assertEqual(days_overdue(self.H, "coralvax", D(2025, 1, 10)), 0)
            self.assertEqual(days_overdue([], "coralvax", D(2025, 1, 10)), 0)
            self.assertEqual(days_overdue([D(2025, 1, 1), D(2025, 3, 1)], "tidevax", D(2026, 1, 1)), 0)


    if __name__ == "__main__":
        unittest.main()
''')

DOSEGAP = Lib(
    name="dosegap", lang="python", title="the vaccine dose-interval checks (`dosegap/`)",
    blurb="The clinic's records system checks vaccine doses against minimum intervals and works out the next due date with dosegap.",
    files={"dosegap/__init__.py": "", "dosegap/series.py": DG_SERIES, "dosegap/status.py": DG_STATUS, "README.md": DG_README,
           ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": DG_VISIBLE},
    hidden_tests={"tests/test_full.py": DG_HIDDEN},
    mutate=["dosegap/series.py", "dosegap/status.py"], difficulty=2, tags=["vaccination", "intervals", "dates"],
    probes=[
        "classify([date(2025, 1, 1), date(2025, 1, 20), date(2025, 1, 25)], 'coralvax')",
        "classify([date(2025, 1, 1), date(2025, 1, 24)], 'coralvax')", "classify([date(2025, 1, 1), date(2025, 1, 23)], 'coralvax')",
        "classify([date(2025, 1, 1), date(2025, 3, 1), date(2025, 4, 1)], 'tidevax')",
        "next_window([date(2025, 1, 1)], 'coralvax')", "next_window([date(2025, 1, 1), date(2025, 1, 25)], 'coralvax')",
        "next_window([date(2025, 1, 1), date(2025, 3, 1)], 'tidevax')", "status([date(2025, 1, 1)], 'coralvax', date(2025, 1, 24))",
        "status([date(2025, 1, 1)], 'coralvax', date(2025, 1, 25))", "status([date(2025, 1, 1)], 'coralvax', date(2025, 2, 13))",
        "days_overdue([date(2025, 1, 1)], 'coralvax', date(2025, 2, 14))", "status([], 'tidevax', date(2025, 1, 1))",
    ],
    probe_import="from datetime import date\nfrom dosegap.series import *\nfrom dosegap.status import *",
)

# ======================================================================================================================
# leavecalc: paid-leave accrual by tenure with a cap, leave taken, carry-over
# ======================================================================================================================

LC_README = dd('''
    # leavecalc

    Paid-leave balances for an HR system. Leave is counted in **hundredths of a day** (`125` is 1.25 days); dates are
    `datetime.date`.

    * `tenure_months(hire, at)`: `(at.year - hire.year) * 12 + at.month - hire.month`.
    * `rate_for(tenure)`: hundredths earned per month: `125` for a tenure of 0 to 23 months, `167` from 24 to 59 months,
      `200` from 60 months on.
    * `month_end(year, month)`: the last day of the month.
    * `month_accrual(hire, year, month)`: what the employee earns for that calendar month. `0` for months that end before
      the hire date. The rate is `rate_for(tenure_months(hire, month_end))`. In the month of hiring the rate is
      prorated by the days employed: `rate * days // days_in_month`, with `days = last day of month - hire day + 1`.
    * `balance(hire, as_of, taken=(), cap=3000)`: the balance on `as_of`. Walk the months from the hiring month to the
      month of `as_of`. In each month first take the leave dated in that month and not after `as_of` (`taken` is a list
      of `(date, amount)`; every amount must be positive and dated on or after `hire`, and the balance must never go
      below 0, otherwise `ValueError`), **then**, only if the month has ended on or before `as_of`, add the month's
      accrual, but never let the balance exceed `cap`. Leave dated after `as_of` is ignored. Before the month of hiring
      the balance is `0`.
    * `carryover(balance, limit=500)`: what may be carried into the new year: `min(balance, limit)`; a negative balance is
      a `ValueError`.
    * `format_days(hundredths)`: `"12.50"` for `1250` (whole days, a point and two digits).
''')

LC_SRC = dd('''
    import calendar
    from datetime import date

    RATES = [(0, 125), (24, 167), (60, 200)]
    CAP = 3000
    CARRYOVER = 500


    def tenure_months(hire, at):
        return (at.year - hire.year) * 12 + at.month - hire.month


    def rate_for(tenure):
        rate = RATES[0][1]
        for start, per_month in RATES:
            if tenure >= start:
                rate = per_month
        return rate


    def month_end(year, month):
        return date(year, month, calendar.monthrange(year, month)[1])


    def month_accrual(hire, year, month):
        end = month_end(year, month)
        if end < hire:
            return 0
        rate = rate_for(tenure_months(hire, end))
        if (year, month) == (hire.year, hire.month):
            return rate * (end.day - hire.day + 1) // end.day
        return rate


    def balance(hire, as_of, taken=(), cap=CAP):
        events = sorted(taken)
        for when, amount in events:
            if amount <= 0 or when < hire:
                raise ValueError("leave must be positive and not before the hire date")
        left = 0
        i = 0
        year, month = hire.year, hire.month
        while (year, month) <= (as_of.year, as_of.month):
            end = month_end(year, month)
            while i < len(events) and events[i][0] <= end and events[i][0] <= as_of:
                left -= events[i][1]
                if left < 0:
                    raise ValueError("more leave taken than earned")
                i += 1
            if end <= as_of:
                left = min(cap, left + month_accrual(hire, year, month))
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return left


    def carryover(balance_hundredths, limit=CARRYOVER):
        if balance_hundredths < 0:
            raise ValueError("balance must not be negative")
        return min(balance_hundredths, limit)


    def format_days(hundredths):
        return "%d.%02d" % divmod(hundredths, 100)
''')

LC_VISIBLE = dd('''
    import unittest
    from datetime import date

    from leavecalc.accrual import format_days, month_accrual, rate_for


    class BasicTests(unittest.TestCase):
        def test_rate(self):
            self.assertEqual(rate_for(10), 125)

        def test_full_month(self):
            self.assertEqual(month_accrual(date(2024, 3, 16), 2024, 4), 125)

        def test_format(self):
            self.assertEqual(format_days(1250), "12.50")


    if __name__ == "__main__":
        unittest.main()
''')

LC_HIDDEN = dd('''
    import unittest
    from datetime import date

    from leavecalc.accrual import balance, carryover, format_days, month_accrual, month_end, rate_for, tenure_months

    D = date
    HIRE = D(2024, 3, 16)


    class Basics(unittest.TestCase):
        def test_tenure(self):
            self.assertEqual(tenure_months(D(2024, 3, 16), D(2024, 3, 31)), 0)
            self.assertEqual(tenure_months(D(2024, 3, 16), D(2025, 3, 1)), 12)
            self.assertEqual(tenure_months(D(2024, 12, 31), D(2025, 1, 1)), 1)
            self.assertEqual(tenure_months(D(2020, 1, 1), D(2026, 1, 31)), 72)

        def test_rates(self):
            table = {0: 125, 1: 125, 23: 125, 24: 167, 25: 167, 59: 167, 60: 200, 61: 200, 200: 200}
            for tenure, rate in table.items():
                self.assertEqual(rate_for(tenure), rate, tenure)

        def test_month_end(self):
            self.assertEqual(month_end(2025, 2), D(2025, 2, 28))
            self.assertEqual(month_end(2024, 2), D(2024, 2, 29))
            self.assertEqual(month_end(2025, 12), D(2025, 12, 31))
            self.assertEqual(month_end(2025, 4), D(2025, 4, 30))


    class Accrual(unittest.TestCase):
        def test_hiring_month_is_prorated(self):
            self.assertEqual(month_accrual(HIRE, 2024, 3), 64)                        # 125 * 16 // 31
            self.assertEqual(month_accrual(D(2024, 1, 31), 2024, 1), 4)               # 125 * 1 // 31
            self.assertEqual(month_accrual(D(2024, 3, 1), 2024, 3), 125)
            self.assertEqual(month_accrual(D(2024, 2, 15), 2024, 2), 125 * 15 // 29)
            self.assertEqual(month_accrual(D(2025, 2, 15), 2025, 2), 125 * 14 // 28)

        def test_before_hire(self):
            self.assertEqual(month_accrual(HIRE, 2024, 2), 0)
            self.assertEqual(month_accrual(HIRE, 2023, 12), 0)

        def test_full_months_follow_the_tenure_tier(self):
            self.assertEqual(month_accrual(HIRE, 2024, 4), 125)
            self.assertEqual(month_accrual(HIRE, 2026, 2), 125)
            self.assertEqual(month_accrual(HIRE, 2026, 3), 167)
            self.assertEqual(month_accrual(HIRE, 2029, 2), 167)
            self.assertEqual(month_accrual(HIRE, 2029, 3), 200)
            self.assertEqual(month_accrual(D(2020, 1, 1), 2024, 12), 167)
            self.assertEqual(month_accrual(D(2020, 1, 1), 2025, 1), 200)

        def test_the_hiring_month_uses_the_tier_of_tenure_zero(self):
            self.assertEqual(month_accrual(D(2020, 1, 1), 2020, 1), 125)


    class Balance(unittest.TestCase):
        def test_without_leave(self):
            self.assertEqual(balance(HIRE, D(2024, 4, 30)), 64 + 125)
            self.assertEqual(balance(HIRE, D(2024, 4, 29)), 64)
            self.assertEqual(balance(HIRE, D(2024, 3, 31)), 64)
            self.assertEqual(balance(HIRE, D(2024, 3, 30)), 0)
            self.assertEqual(balance(HIRE, D(2025, 3, 31)), 64 + 12 * 125)

        def test_before_the_hire_month(self):
            self.assertEqual(balance(HIRE, D(2024, 2, 29)), 0)
            self.assertEqual(balance(HIRE, D(2023, 1, 1)), 0)

        def test_leave_is_taken_before_the_month_end_accrual(self):
            taken = [(D(2024, 4, 10), 50)]
            self.assertEqual(balance(HIRE, D(2024, 5, 31), taken), 64 - 50 + 125 + 125)
            self.assertEqual(balance(HIRE, D(2024, 4, 30), taken), 64 - 50 + 125)
            self.assertEqual(balance(HIRE, D(2024, 4, 9), taken), 64)

        def test_cannot_use_the_months_own_accrual(self):
            with self.assertRaises(ValueError):
                balance(HIRE, D(2024, 6, 30), [(D(2024, 3, 20), 100)])
            with self.assertRaises(ValueError):
                balance(HIRE, D(2024, 6, 30), [(D(2024, 4, 5), 65)])
            self.assertEqual(balance(HIRE, D(2024, 6, 30), [(D(2024, 4, 5), 64)]), 125 + 125 + 125)

        def test_leave_on_the_last_day_of_a_month(self):
            self.assertEqual(balance(HIRE, D(2024, 5, 31), [(D(2024, 4, 30), 64)]), 125 + 125)

        def test_leave_after_the_date_is_ignored(self):
            self.assertEqual(balance(HIRE, D(2024, 4, 30), [(D(2030, 1, 1), 100)]), 64 + 125)
            self.assertEqual(balance(HIRE, D(2024, 4, 30), [(D(2024, 5, 1), 100)]), 64 + 125)
            self.assertEqual(balance(HIRE, D(2024, 4, 30), [(D(2024, 4, 30), 10)]), 64 - 10 + 125)

        def test_several_takes_and_any_order(self):
            taken = [(D(2024, 6, 20), 100), (D(2024, 5, 5), 30), (D(2024, 5, 6), 30)]
            self.assertEqual(balance(HIRE, D(2024, 6, 30), taken), (64 + 125 - 60 + 125) - 100 + 125)
            self.assertEqual(balance(HIRE, D(2024, 6, 30), list(reversed(taken))), balance(HIRE, D(2024, 6, 30), taken))

        def test_cap(self):
            hire = D(2020, 1, 1)
            self.assertEqual(balance(hire, D(2021, 12, 31)), 3000)
            self.assertEqual(balance(hire, D(2022, 1, 31)), 3000)
            self.assertEqual(balance(hire, D(2030, 1, 31)), 3000)
            self.assertEqual(balance(hire, D(2020, 12, 31), cap=1000), 1000)
            self.assertEqual(balance(hire, D(2020, 6, 30), cap=1000), 750)
            self.assertEqual(balance(hire, D(2020, 8, 31), cap=1000), 1000)

        def test_leave_makes_room_under_the_cap(self):
            hire = D(2020, 1, 1)
            self.assertEqual(balance(hire, D(2022, 1, 31), [(D(2022, 1, 10), 1000)]), 3000 - 1000 + 167)
            # the 100 taken in January are earned back by the January accrual, the cap clips the February one
            self.assertEqual(balance(hire, D(2022, 2, 28), [(D(2022, 1, 10), 100)]), 3000)
            self.assertEqual(balance(hire, D(2022, 1, 31), [(D(2022, 1, 10), 300)]), 3000 - 300 + 167)

        def test_tier_changes_inside_the_walk(self):
            hire = D(2022, 1, 1)
            # 24 months at 125, then 167 from tenure 24 (January 2024)
            self.assertEqual(balance(hire, D(2023, 12, 31), cap=10_000), 24 * 125)
            self.assertEqual(balance(hire, D(2024, 1, 31), cap=10_000), 24 * 125 + 167)
            self.assertEqual(balance(hire, D(2024, 2, 29), cap=10_000), 24 * 125 + 2 * 167)
            self.assertEqual(balance(hire, D(2024, 1, 31)), 3000)

        def test_bad_leave_entries(self):
            for entry in ((D(2024, 4, 10), 0), (D(2024, 4, 10), -5), (D(2024, 3, 15), 10)):
                with self.assertRaises(ValueError, msg=entry):
                    balance(HIRE, D(2024, 6, 30), [entry])
            with self.assertRaises(ValueError):
                balance(HIRE, D(2024, 4, 30), [(D(2030, 1, 1), -1)])

        def test_leave_on_the_hire_date(self):
            with self.assertRaises(ValueError):
                balance(HIRE, D(2024, 6, 30), [(HIRE, 10)])


    class Year(unittest.TestCase):
        def test_carryover(self):
            self.assertEqual(carryover(1250), 500)
            self.assertEqual(carryover(500), 500)
            self.assertEqual(carryover(499), 499)
            self.assertEqual(carryover(0), 0)
            self.assertEqual(carryover(1250, limit=1000), 1000)
            self.assertEqual(carryover(80, limit=1000), 80)

        def test_negative_balance(self):
            with self.assertRaises(ValueError):
                carryover(-1)

        def test_format(self):
            table = {0: "0.00", 5: "0.05", 100: "1.00", 125: "1.25", 1250: "12.50", 3000: "30.00", 12_345: "123.45"}
            for value, text in table.items():
                self.assertEqual(format_days(value), text, value)


    if __name__ == "__main__":
        unittest.main()
''')

LEAVECALC = Lib(
    name="leavecalc", lang="python", title="the paid-leave accrual rules (`leavecalc/accrual.py`)",
    blurb="The HR system works out employees' paid-leave balances, with accrual tiers, a cap and carry-over, using leavecalc.",
    files={"leavecalc/__init__.py": "", "leavecalc/accrual.py": LC_SRC, "README.md": LC_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": LC_VISIBLE},
    hidden_tests={"tests/test_full.py": LC_HIDDEN},
    mutate=["leavecalc/accrual.py"], difficulty=2, tags=["leave", "accrual", "hr"],
    probes=[
        "tenure_months(date(2024, 12, 31), date(2025, 1, 1))", "rate_for(23)", "rate_for(24)", "rate_for(59)", "rate_for(60)",
        "month_accrual(date(2024, 3, 16), 2024, 3)", "month_accrual(date(2024, 1, 31), 2024, 1)", "month_accrual(date(2024, 3, 16), 2026, 3)",
        "month_accrual(date(2024, 3, 16), 2024, 2)", "balance(date(2024, 3, 16), date(2024, 4, 30))", "balance(date(2024, 3, 16), date(2024, 4, 29))",
        "balance(date(2024, 3, 16), date(2024, 5, 31), [(date(2024, 4, 10), 50)])", "balance(date(2020, 1, 1), date(2022, 1, 31))",
        "balance(date(2020, 1, 1), date(2020, 12, 31), cap=1000)", "balance(date(2024, 3, 16), date(2024, 6, 30), [(date(2024, 4, 5), 65)])",
        "carryover(1250)", "format_days(12_345)",
    ],
    probe_import="from datetime import date\nfrom leavecalc.accrual import *",
)

register_libs([STAYPRICE, DOSEGAP, LEAVECALC], n=10)
