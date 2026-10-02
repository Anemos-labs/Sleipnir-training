"""Python libraries, theme time/money/scheduling (batch misc-c): water bills with prorated blocks, sprint capacity
planning, backup retention."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# waterbill: tiered water tariff with blocks prorated by days, sewerage cap, leak adjustment
# ======================================================================================================================

WB_README = dd('''
    # waterbill

    Bills of a municipal water company. Water use is in whole litres, money in `int` cents, dates are `datetime.date`.
    A billing period `[start, end)` lasts `(end - start).days` days.

    ## Tariff (`waterbill/tariff.py`)

    * `scaled(litres_per_30_days, days)`: a per-30-days quantity prorated to `days`: `litres_per_30_days * days // 30`.
    * `water_charge(litres, days)`: block tariff. The cumulative block limits per 30 days are 10 000 litres and 30 000
      litres (each scaled to the period with `scaled`), the prices per cubic metre (1000 litres) are 180 cents up to the
      first limit, 260 cents between the limits and 410 cents above the second. The sum `litres_in_block * price` of all
      blocks is divided by 1000 and rounded half up to a cent **once**. Negative litres or a period shorter than one day
      is a `ValueError`.
    * `sewer_charge(litres, days)`: sewerage is charged on at most `scaled(25 000, days)` litres: it is 85% of the
      `water_charge` of `min(litres, scaled(25 000, days))` (same period length), rounded half up.
    * `fixed_charge(days)`: 21 cents per day.

    ## Bill (`waterbill/bill.py`)

    * `leak_adjusted_water(litres, days, prev_litres)`: when `prev_litres` is given and positive and `litres` is more than
      three times `prev_litres`, the litres up to `3 * prev_litres` are charged with `water_charge` and every litre beyond
      that is charged at the price of the first block (180 cents per m3, `excess * 180 / 1000` rounded half up); the two
      parts are added. In every other case it is simply `water_charge(litres, days)`.
    * `make_bill(litres, start, end, prev_litres=None)`: a dict with `days`, `water` (the leak-adjusted charge), `sewer`
      (always from the real consumption, not leak-adjusted), `fixed` and `total` (water + sewer + fixed). A period that
      does not last at least one day is a `ValueError`.
''')

WB_TARIFF = dd('''
    BLOCKS = [(10_000, 180), (30_000, 260), (None, 410)]
    SEWER_PERCENT = 85
    SEWER_CAP = 25_000
    FIXED_PER_DAY = 21
    BASE_DAYS = 30


    def scaled(litres_per_30_days, days):
        return litres_per_30_days * days // BASE_DAYS


    def water_charge(litres, days):
        if litres < 0 or days < 1:
            raise ValueError("litres must not be negative and a period has at least one day")
        numerator = 0
        low = 0
        for limit, rate in BLOCKS:
            if litres <= low:
                break
            high = litres if limit is None else min(litres, scaled(limit, days))
            if high > low:
                numerator += (high - low) * rate
                low = high
        return (2 * numerator + 1000) // 2000


    def sewer_charge(litres, days):
        billed = min(litres, scaled(SEWER_CAP, days))
        return (water_charge(billed, days) * SEWER_PERCENT * 2 + 100) // 200


    def fixed_charge(days):
        return FIXED_PER_DAY * days
''')

WB_BILL = dd('''
    from .tariff import BLOCKS, fixed_charge, sewer_charge, water_charge

    LEAK_FACTOR = 3


    def leak_adjusted_water(litres, days, prev_litres):
        if prev_litres is None or prev_litres <= 0 or litres <= LEAK_FACTOR * prev_litres:
            return water_charge(litres, days)
        normal = LEAK_FACTOR * prev_litres
        excess = litres - normal
        return water_charge(normal, days) + (2 * excess * BLOCKS[0][1] + 1000) // 2000


    def make_bill(litres, start, end, prev_litres=None):
        days = (end - start).days
        if days < 1:
            raise ValueError("the billing period must end after it starts")
        water = leak_adjusted_water(litres, days, prev_litres)
        sewer = sewer_charge(litres, days)
        fixed = fixed_charge(days)
        return {"days": days, "water": water, "sewer": sewer, "fixed": fixed, "total": water + sewer + fixed}
''')

WB_VISIBLE = dd('''
    import unittest

    from waterbill.tariff import fixed_charge, scaled, water_charge


    class BasicTests(unittest.TestCase):
        def test_first_block(self):
            self.assertEqual(water_charge(1000, 30), 180)

        def test_fixed(self):
            self.assertEqual(fixed_charge(30), 630)

        def test_scaled(self):
            self.assertEqual(scaled(10_000, 60), 20_000)


    if __name__ == "__main__":
        unittest.main()
''')

WB_HIDDEN = dd('''
    import unittest
    from datetime import date

    from waterbill.bill import leak_adjusted_water, make_bill
    from waterbill.tariff import fixed_charge, scaled, sewer_charge, water_charge

    D = date


    class Scaling(unittest.TestCase):
        def test_values(self):
            table = {(10_000, 30): 10_000, (10_000, 60): 20_000, (10_000, 15): 5000, (10_000, 31): 10_333, (10_000, 28): 9333,
                     (25_000, 1): 833, (0, 30): 0}
            for (litres, days), want in table.items():
                self.assertEqual(scaled(litres, days), want, (litres, days))


    class Water(unittest.TestCase):
        def test_blocks_for_thirty_days(self):
            table = {0: 0, 1: 0, 1000: 180, 10_000: 1800, 10_001: 1800, 20_000: 4400, 30_000: 7000, 30_001: 7000, 50_000: 15_200}
            for litres, cents in table.items():
                self.assertEqual(water_charge(litres, 30), cents, litres)

        def test_blocks_scale_with_the_period(self):
            self.assertEqual([water_charge(l, 60) for l in (10_000, 20_000, 60_000, 70_000)], [1800, 3600, 14_000, 18_100])
            self.assertEqual([water_charge(l, 15) for l in (5000, 5001, 10_000, 15_000)], [900, 900, 2200, 3500])
            self.assertEqual([water_charge(l, 31) for l in (10_333, 10_334, 30_999, 31_000)], [1860, 1860, 7233, 7233])

        def test_single_rounding_half_up(self):
            self.assertEqual(water_charge(3, 30), 1)     # 0.54
            self.assertEqual(water_charge(2, 30), 0)     # 0.36
            self.assertEqual(water_charge(25, 30), 5)    # 4.5
            self.assertEqual(water_charge(24, 30), 4)    # 4.32
            self.assertEqual(water_charge(10_001, 30), 1800)   # 1800.26 in one go

        def test_errors(self):
            with self.assertRaises(ValueError):
                water_charge(-1, 30)
            with self.assertRaises(ValueError):
                water_charge(5, 0)
            with self.assertRaises(ValueError):
                water_charge(5, -3)
            water_charge(0, 1)


    class Sewer(unittest.TestCase):
        def test_percentage_and_cap(self):
            table = {0: 0, 10_000: 1530, 25_000: 4845, 25_001: 4845, 40_000: 4845}
            for litres, cents in table.items():
                self.assertEqual(sewer_charge(litres, 30), cents, litres)

        def test_cap_scales_with_the_period(self):
            self.assertEqual(sewer_charge(50_000, 60), 9690)
            self.assertEqual(sewer_charge(60_000, 60), 9690)
            self.assertEqual(sewer_charge(49_999, 60), 9690)
            self.assertEqual(sewer_charge(20_000, 60), 3060)

        def test_rounding(self):
            self.assertEqual(sewer_charge(3, 30), 1)      # water 1 cent, 85% = 0.85 -> 1
            self.assertEqual(sewer_charge(25, 30), 4)     # water 5 cents, 4.25 -> 4
            self.assertEqual(sewer_charge(2000, 30), 306)


    class Fixed(unittest.TestCase):
        def test_per_day(self):
            self.assertEqual((fixed_charge(1), fixed_charge(30), fixed_charge(60)), (21, 630, 1260))


    class Leak(unittest.TestCase):
        def test_no_previous_reading(self):
            self.assertEqual(leak_adjusted_water(30_000, 30, None), 7000)
            self.assertEqual(leak_adjusted_water(30_000, 30, 0), 7000)

        def test_within_three_times_the_previous_use(self):
            self.assertEqual(leak_adjusted_water(12_000, 30, 4000), 2320)
            self.assertEqual(leak_adjusted_water(12_000, 30, 4000), water_charge(12_000, 30))

        def test_excess_is_charged_at_the_first_block_price(self):
            self.assertEqual(leak_adjusted_water(30_000, 30, 4000), 2320 + 3240)
            self.assertEqual(leak_adjusted_water(12_001, 30, 4000), 2320)
            self.assertEqual(leak_adjusted_water(12_010, 30, 4000), 2320 + 2)     # 10 litres: 1.8 cents

        def test_each_part_is_rounded(self):
            self.assertEqual(leak_adjusted_water(100, 30, 30), 16 + 2)    # 90 litres 16.2 -> 16, 10 litres 1.8 -> 2
            self.assertEqual(leak_adjusted_water(100, 30, 33), 18)        # 99 litres 17.82 -> 18, 1 litre 0.18 -> 0
            self.assertEqual(leak_adjusted_water(100, 30, 34), 18)

        def test_the_normal_part_uses_the_blocks(self):
            self.assertEqual(leak_adjusted_water(100_000, 30, 10_000), water_charge(30_000, 30) + (70_000 * 180 + 500) // 1000)


    class Bill(unittest.TestCase):
        def test_ordinary_bill(self):
            got = make_bill(12_000, D(2025, 3, 1), D(2025, 3, 31))
            self.assertEqual(got, {"days": 30, "water": 2320, "sewer": 1972, "fixed": 630, "total": 4922})

        def test_other_period_lengths(self):
            got = make_bill(20_000, D(2025, 1, 1), D(2025, 3, 2))
            self.assertEqual(got, {"days": 60, "water": 3600, "sewer": 3060, "fixed": 1260, "total": 7920})
            got = make_bill(1000, D(2025, 3, 1), D(2025, 3, 2))
            self.assertEqual((got["days"], got["fixed"]), (1, 21))

        def test_leak_adjustment_only_changes_the_water_line(self):
            got = make_bill(30_000, D(2025, 3, 1), D(2025, 3, 31), prev_litres=4000)
            self.assertEqual(got, {"days": 30, "water": 5560, "sewer": 4845, "fixed": 630, "total": 11_035})

        def test_no_adjustment_when_the_use_is_normal(self):
            self.assertEqual(make_bill(12_000, D(2025, 3, 1), D(2025, 3, 31), prev_litres=4000), make_bill(12_000, D(2025, 3, 1), D(2025, 3, 31)))
            self.assertEqual(make_bill(30_000, D(2025, 3, 1), D(2025, 3, 31), prev_litres=0), make_bill(30_000, D(2025, 3, 1), D(2025, 3, 31)))

        def test_period_must_have_a_day(self):
            with self.assertRaises(ValueError):
                make_bill(5, D(2025, 3, 1), D(2025, 3, 1))
            with self.assertRaises(ValueError):
                make_bill(5, D(2025, 3, 2), D(2025, 3, 1))


    if __name__ == "__main__":
        unittest.main()
''')

WATERBILL = Lib(
    name="waterbill", lang="python", title="the water bill calculator (`waterbill/`)",
    blurb="The municipal water company bills households with block prices prorated by period length, using waterbill.",
    files={"waterbill/__init__.py": "", "waterbill/tariff.py": WB_TARIFF, "waterbill/bill.py": WB_BILL, "README.md": WB_README,
           ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": WB_VISIBLE},
    hidden_tests={"tests/test_full.py": WB_HIDDEN},
    mutate=["waterbill/tariff.py", "waterbill/bill.py"], difficulty=3, tags=["water", "tariff", "proration"],
    probes=[
        "scaled(10_000, 31)", "water_charge(10_001, 30)", "water_charge(20_000, 60)", "water_charge(5001, 15)", "water_charge(25, 30)",
        "water_charge(31_000, 31)", "sewer_charge(40_000, 30)", "sewer_charge(60_000, 60)", "sewer_charge(25, 30)", "fixed_charge(60)",
        "leak_adjusted_water(30_000, 30, 4000)", "leak_adjusted_water(100, 30, 30)", "leak_adjusted_water(12_001, 30, 4000)",
        "make_bill(12_000, date(2025, 3, 1), date(2025, 3, 31))", "make_bill(30_000, date(2025, 3, 1), date(2025, 3, 31), prev_litres=4000)",
        "make_bill(20_000, date(2025, 1, 1), date(2025, 3, 2))",
    ],
    probe_import="from datetime import date\nfrom waterbill.tariff import *\nfrom waterbill.bill import *",
)

# ======================================================================================================================
# sprintcap: team capacity of a sprint from allocations, leave and holidays, and a delivery forecast
# ======================================================================================================================

SC_README = dd('''
    # sprintcap

    Sprint planning arithmetic for a software team. Dates are `datetime.date`. Capacity is counted in **percent-days**: one
    working day of one person at 100% allocation is 100 percent-days (so a person at 50% working 8 days has 400).

    ## Capacity (`sprintcap/capacity.py`)

    A working day is a weekday (Mon to Fri) that is not in `holidays` (a collection of dates). Ranges are **closed**
    (both ends included).

    * `working_days(start, end, holidays=())`: working days in `[start, end]`; `0` when `end < start`.
    * `available_days(start, end, leave=(), holidays=())`: the working days of `[start, end]` that are not inside any of the
      `leave` ranges (`(first, last)` pairs; overlapping ranges do not count a day twice).
    * `member_capacity(allocation, start, end, leave=(), holidays=())`: `available_days * allocation`. An `allocation`
      outside `0..100` is a `ValueError`.
    * `team_capacity(team, start, end, holidays=())`: `team` maps names to dicts with `allocation` and an optional `leave`
      list; the sum of the member capacities.
    * `format_person_days(percent_days)`: `"18.40"` for `1840`.

    ## Forecast (`sprintcap/forecast.py`)

    A sprint lasts 14 calendar days: `[start, start + 13 days]`; the next one starts the day after it ends.

    * `sprint_points(team, start, tenths_per_person_day, holidays=())`: the story points a sprint delivers:
      `team_capacity * tenths_per_person_day // 1000` (the velocity is given in tenths of a point per person-day, so 8
      means 0.8 points per person-day).
    * `forecast(backlog, team, start, tenths_per_person_day, holidays=())`: `(sprints, last_day)`, the number of sprints
      needed to deliver `backlog` points (cumulative points reaching the backlog) and the last day of the final sprint.
      A backlog of 0 is `(0, None)`. A negative backlog is a `ValueError`, and so is a backlog not finished within 100
      sprints.
''')

SC_CAPACITY = dd('''
    from datetime import timedelta


    def is_working_day(d, holidays=()):
        return d.weekday() < 5 and d not in holidays


    def working_days(start, end, holidays=()):
        count = 0
        d = start
        while d <= end:
            if is_working_day(d, holidays):
                count += 1
            d += timedelta(days=1)
        return count


    def available_days(start, end, leave=(), holidays=()):
        count = 0
        d = start
        while d <= end:
            if is_working_day(d, holidays) and not any(a <= d <= b for a, b in leave):
                count += 1
            d += timedelta(days=1)
        return count


    def member_capacity(allocation, start, end, leave=(), holidays=()):
        if not 0 <= allocation <= 100:
            raise ValueError("allocation is a percentage")
        return available_days(start, end, leave, holidays) * allocation


    def team_capacity(team, start, end, holidays=()):
        return sum(member_capacity(m["allocation"], start, end, m.get("leave", ()), holidays) for m in team.values())


    def format_person_days(percent_days):
        return "%d.%02d" % divmod(percent_days, 100)
''')

SC_FORECAST = dd('''
    from datetime import timedelta

    from .capacity import team_capacity

    SPRINT_DAYS = 14
    MAX_SPRINTS = 100


    def sprint_points(team, start, tenths_per_person_day, holidays=()):
        end = start + timedelta(days=SPRINT_DAYS - 1)
        return team_capacity(team, start, end, holidays) * tenths_per_person_day // 1000


    def forecast(backlog, team, start, tenths_per_person_day, holidays=()):
        if backlog < 0:
            raise ValueError("backlog must not be negative")
        if backlog == 0:
            return 0, None
        done = 0
        sprint_start = start
        for n in range(1, MAX_SPRINTS + 1):
            done += sprint_points(team, sprint_start, tenths_per_person_day, holidays)
            if done >= backlog:
                return n, sprint_start + timedelta(days=SPRINT_DAYS - 1)
            sprint_start += timedelta(days=SPRINT_DAYS)
        raise ValueError("the backlog is not done within 100 sprints")
''')

SC_VISIBLE = dd('''
    import unittest
    from datetime import date

    from sprintcap.capacity import format_person_days, working_days


    class BasicTests(unittest.TestCase):
        def test_two_weeks(self):
            self.assertEqual(working_days(date(2025, 3, 3), date(2025, 3, 16)), 10)

        def test_format(self):
            self.assertEqual(format_person_days(1840), "18.40")


    if __name__ == "__main__":
        unittest.main()
''')

SC_HIDDEN = dd('''
    import unittest
    from datetime import date

    from sprintcap.capacity import available_days, format_person_days, member_capacity, team_capacity, working_days
    from sprintcap.forecast import forecast, sprint_points

    D = date
    S, E = D(2025, 3, 3), D(2025, 3, 16)   # Monday to Sunday two weeks later
    TEAM = {"ann": {"allocation": 100}, "bo": {"allocation": 50, "leave": [(D(2025, 3, 10), D(2025, 3, 14))]},
            "cy": {"allocation": 80, "leave": [(D(2025, 3, 4), D(2025, 3, 4))]}}


    class Days(unittest.TestCase):
        def test_working_days(self):
            self.assertEqual(working_days(S, E), 10)
            self.assertEqual(working_days(S, E, {D(2025, 3, 5)}), 9)
            self.assertEqual(working_days(D(2025, 3, 8), D(2025, 3, 9)), 0)
            self.assertEqual(working_days(S, S), 1)
            self.assertEqual(working_days(E, S), 0)
            self.assertEqual(working_days(D(2025, 3, 8), D(2025, 3, 8), {D(2025, 3, 8)}), 0)

        def test_holiday_on_a_weekend_changes_nothing(self):
            self.assertEqual(working_days(S, E, {D(2025, 3, 8), D(2025, 3, 9)}), 10)

        def test_range_ends_are_included(self):
            self.assertEqual(working_days(D(2025, 3, 7), D(2025, 3, 10)), 2)
            self.assertEqual(working_days(D(2025, 3, 7), D(2025, 3, 7)), 1)

        def test_available_days(self):
            self.assertEqual(available_days(S, E), 10)
            self.assertEqual(available_days(S, E, [(D(2025, 3, 5), D(2025, 3, 7))]), 7)
            self.assertEqual(available_days(S, E, [(D(2025, 3, 1), D(2025, 3, 3)), (D(2025, 3, 14), D(2025, 3, 20))]), 8)
            self.assertEqual(available_days(S, E, [(D(2025, 3, 8), D(2025, 3, 9))]), 10)

        def test_overlapping_leave_counts_once(self):
            leave = [(D(2025, 3, 4), D(2025, 3, 6)), (D(2025, 3, 5), D(2025, 3, 7))]
            self.assertEqual(available_days(S, E, leave), 6)

        def test_leave_and_holiday_on_the_same_day(self):
            self.assertEqual(available_days(S, E, [(D(2025, 3, 5), D(2025, 3, 5))], {D(2025, 3, 5)}), 9)


    class Capacity(unittest.TestCase):
        def test_member(self):
            self.assertEqual(member_capacity(100, S, E), 1000)
            self.assertEqual(member_capacity(50, S, E, [(D(2025, 3, 5), D(2025, 3, 7))]), 350)
            self.assertEqual(member_capacity(0, S, E), 0)
            self.assertEqual(member_capacity(80, S, E, holidays={D(2025, 3, 5)}), 720)

        def test_allocation_range(self):
            for allocation in (-1, 101, 1000):
                with self.assertRaises(ValueError):
                    member_capacity(allocation, S, E)
            member_capacity(100, S, E)
            member_capacity(0, S, E)

        def test_team(self):
            self.assertEqual(team_capacity(TEAM, S, E), 1000 + 250 + 720)
            self.assertEqual(team_capacity(TEAM, S, E, {D(2025, 3, 7)}), 900 + 200 + 640)
            self.assertEqual(team_capacity({}, S, E), 0)

        def test_leave_is_optional(self):
            self.assertEqual(team_capacity({"x": {"allocation": 100}}, S, E), 1000)

        def test_format(self):
            table = {0: "0.00", 5: "0.05", 100: "1.00", 1840: "18.40", 1970: "19.70", 12_345: "123.45"}
            for value, text in table.items():
                self.assertEqual(format_person_days(value), text, value)


    class Forecast(unittest.TestCase):
        def test_points_per_sprint(self):
            self.assertEqual(sprint_points(TEAM, S, 8), 15)
            self.assertEqual(sprint_points(TEAM, S, 10), 19)
            self.assertEqual(sprint_points(TEAM, S, 8, {D(2025, 3, 7)}), 1740 * 8 // 1000)
            self.assertEqual(sprint_points(TEAM, D(2025, 3, 17), 8), 18)

        def test_the_sprint_has_fourteen_days(self):
            team = {"x": {"allocation": 100, "leave": [(D(2025, 3, 3), D(2025, 3, 14))]}}
            self.assertEqual(sprint_points(team, S, 10), 0)
            team = {"x": {"allocation": 100}}
            self.assertEqual(sprint_points(team, D(2025, 3, 8), 10), 10)
            self.assertEqual(sprint_points(team, D(2025, 3, 10), 10), 10)

        def test_empty_backlog(self):
            self.assertEqual(forecast(0, TEAM, S, 8), (0, None))

        def test_sprints_needed(self):
            self.assertEqual(forecast(1, TEAM, S, 8), (1, D(2025, 3, 16)))
            self.assertEqual(forecast(15, TEAM, S, 8), (1, D(2025, 3, 16)))
            self.assertEqual(forecast(16, TEAM, S, 8), (2, D(2025, 3, 30)))
            self.assertEqual(forecast(33, TEAM, S, 8), (2, D(2025, 3, 30)))
            self.assertEqual(forecast(34, TEAM, S, 8), (3, D(2025, 4, 13)))

        def test_holidays_slow_the_forecast(self):
            self.assertEqual(forecast(33, TEAM, S, 8, {D(2025, 3, 20), D(2025, 3, 21), D(2025, 3, 24), D(2025, 3, 25)}), (3, D(2025, 4, 13)))

        def test_errors(self):
            with self.assertRaises(ValueError):
                forecast(-1, TEAM, S, 8)
            with self.assertRaises(ValueError):
                forecast(5, {}, S, 8)
            with self.assertRaises(ValueError):
                forecast(10_000, TEAM, S, 8)


    if __name__ == "__main__":
        unittest.main()
''')

SPRINTCAP = Lib(
    name="sprintcap", lang="python", title="the sprint capacity planner (`sprintcap/`)",
    blurb="The team's planning tool works out how much a sprint can deliver, allowing for part-timers, leave and holidays, with sprintcap.",
    files={"sprintcap/__init__.py": "", "sprintcap/capacity.py": SC_CAPACITY, "sprintcap/forecast.py": SC_FORECAST,
           "README.md": SC_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": SC_VISIBLE},
    hidden_tests={"tests/test_full.py": SC_HIDDEN},
    mutate=["sprintcap/capacity.py", "sprintcap/forecast.py"], difficulty=2, tags=["planning", "capacity", "leave"],
    probes=[
        "working_days(date(2025, 3, 3), date(2025, 3, 16))", "working_days(date(2025, 3, 7), date(2025, 3, 10))",
        "working_days(date(2025, 3, 16), date(2025, 3, 3))",
        "available_days(date(2025, 3, 3), date(2025, 3, 16), [(date(2025, 3, 4), date(2025, 3, 6)), (date(2025, 3, 5), date(2025, 3, 7))])",
        "member_capacity(50, date(2025, 3, 3), date(2025, 3, 16), [(date(2025, 3, 5), date(2025, 3, 7))])",
        "member_capacity(101, date(2025, 3, 3), date(2025, 3, 16))", "team_capacity({'ann': {'allocation': 100}, 'bo': {'allocation': 50, 'leave': [(date(2025, 3, 10), date(2025, 3, 14))]}}, date(2025, 3, 3), date(2025, 3, 16))",
        "team_capacity({'ann': {'allocation': 100}, 'bo': {'allocation': 50, 'leave': [(date(2025, 3, 10), date(2025, 3, 14))]}}, date(2025, 3, 3), date(2025, 3, 16), {date(2025, 3, 7)})", "format_person_days(1840)",
        "sprint_points({'ann': {'allocation': 100}, 'bo': {'allocation': 50, 'leave': [(date(2025, 3, 10), date(2025, 3, 14))]}}, date(2025, 3, 3), 8)", "sprint_points({'ann': {'allocation': 100}, 'bo': {'allocation': 50, 'leave': [(date(2025, 3, 10), date(2025, 3, 14))]}}, date(2025, 3, 17), 8)",
        "forecast(10, {'ann': {'allocation': 100}, 'bo': {'allocation': 50, 'leave': [(date(2025, 3, 10), date(2025, 3, 14))]}}, date(2025, 3, 3), 8)", "forecast(11, {'ann': {'allocation': 100}, 'bo': {'allocation': 50, 'leave': [(date(2025, 3, 10), date(2025, 3, 14))]}}, date(2025, 3, 3), 8)", "forecast(0, {'ann': {'allocation': 100}, 'bo': {'allocation': 50, 'leave': [(date(2025, 3, 10), date(2025, 3, 14))]}}, date(2025, 3, 3), 8)",
    ],
    probe_import=("from datetime import date\nfrom sprintcap.capacity import *\nfrom sprintcap.forecast import *"),
)

# ======================================================================================================================
# retention: grandfather-father-son backup retention (which backups to keep)
# ======================================================================================================================

RT_README = dd('''
    # retention

    Backup pruning for a storage server. Backups are `datetime.datetime` values, `today` is a `datetime.date`.

    `retain(backups, today, **policy)` returns the sorted list of backups to keep. The policy keys are `daily=7`,
    `weekly=4`, `monthly=12` and `yearly=3` (defaults shown); any other key or a negative number is a `ValueError`.
    Backups dated after `today` (by their date) are ignored (never kept); duplicates count once. A backup is kept when it
    is the **newest backup of its bucket** for one of these rules:

    * `daily`: the buckets are the last `daily` calendar days, `today` and the days before it (`daily=7` is today and the
      6 days before);
    * `weekly`: the last `weekly` weeks, counted from the week of `today` (weeks start on Monday and the week of `today`
      is the first one);
    * `monthly`: the last `monthly` calendar months, the month of `today` being the first;
    * `yearly`: the last `yearly` calendar years, the year of `today` being the first.

    A value of 0 switches a rule off.

    `reasons(backups, today, **policy)` returns `{backup: [labels]}` for the kept backups, the labels (`daily`, `weekly`,
    `monthly`, `yearly`) in that order for every rule that keeps the backup.
    `prune(backups, today, **policy)` returns `(keep, delete)`: two sorted lists splitting the distinct backups; ignored
    (future) backups are in `delete`.
''')

RT_SRC = dd('''
    from datetime import timedelta

    DEFAULT = {"daily": 7, "weekly": 4, "monthly": 12, "yearly": 3}


    def week_start(d):
        return d - timedelta(days=d.weekday())


    def month_index(d):
        return d.year * 12 + d.month - 1


    def _newest_per_bucket(backups, bucket_of, wanted):
        best = {}
        for b in backups:
            key = bucket_of(b)
            if key in wanted and (key not in best or b > best[key]):
                best[key] = b
        return set(best.values())


    def reasons(backups, today, **policy):
        rules = dict(DEFAULT)
        rules.update(policy)
        if set(rules) - set(DEFAULT) or any(n < 0 for n in rules.values()):
            raise ValueError("bad retention policy")
        existing = [b for b in set(backups) if b.date() <= today]
        keep = {}

        def mark(found, label):
            for b in found:
                keep.setdefault(b, []).append(label)

        days = {today - timedelta(days=i) for i in range(rules["daily"])}
        mark(_newest_per_bucket(existing, lambda b: b.date(), days), "daily")
        weeks = {week_start(today) - timedelta(days=7 * i) for i in range(rules["weekly"])}
        mark(_newest_per_bucket(existing, lambda b: week_start(b.date()), weeks), "weekly")
        months = {month_index(today) - i for i in range(rules["monthly"])}
        mark(_newest_per_bucket(existing, lambda b: month_index(b.date()), months), "monthly")
        years = {today.year - i for i in range(rules["yearly"])}
        mark(_newest_per_bucket(existing, lambda b: b.year, years), "yearly")
        return keep


    def retain(backups, today, **policy):
        return sorted(reasons(backups, today, **policy))


    def prune(backups, today, **policy):
        keep = set(reasons(backups, today, **policy))
        distinct = sorted(set(backups))
        return [b for b in distinct if b in keep], [b for b in distinct if b not in keep]
''')

RT_VISIBLE = dd('''
    import unittest
    from datetime import date, datetime

    from retention.policy import retain


    class BasicTests(unittest.TestCase):
        def test_single_backup_is_kept(self):
            b = datetime(2025, 3, 12, 2)
            self.assertEqual(retain([b], date(2025, 3, 12)), [b])

        def test_nothing(self):
            self.assertEqual(retain([], date(2025, 3, 12)), [])


    if __name__ == "__main__":
        unittest.main()
''')

RT_HIDDEN = dd('''
    import unittest
    from datetime import date, datetime, timedelta

    from retention.policy import prune, reasons, retain

    DT = datetime
    TODAY = date(2025, 3, 12)    # a Wednesday
    BACKUPS = [DT(2025, 3, 12, 2), DT(2025, 3, 12, 14), DT(2025, 3, 11, 2), DT(2025, 3, 10, 2), DT(2025, 3, 9, 2), DT(2025, 3, 5, 2),
               DT(2025, 3, 3, 2), DT(2025, 2, 28, 2), DT(2025, 2, 1, 2), DT(2025, 1, 15, 2), DT(2024, 12, 31, 2), DT(2024, 6, 1, 2),
               DT(2023, 2, 2, 2), DT(2022, 12, 31, 23), DT(2025, 3, 13, 2)]


    class Defaults(unittest.TestCase):
        def test_reasons(self):
            got = reasons(BACKUPS, TODAY)
            self.assertEqual(got, {
                DT(2023, 2, 2, 2): ["yearly"],
                DT(2024, 6, 1, 2): ["monthly"],
                DT(2024, 12, 31, 2): ["monthly", "yearly"],
                DT(2025, 1, 15, 2): ["monthly"],
                DT(2025, 2, 28, 2): ["weekly", "monthly"],
                DT(2025, 3, 9, 2): ["daily", "weekly"],
                DT(2025, 3, 10, 2): ["daily"],
                DT(2025, 3, 11, 2): ["daily"],
                DT(2025, 3, 12, 14): ["daily", "weekly", "monthly", "yearly"]})

        def test_retain(self):
            self.assertEqual(retain(BACKUPS, TODAY), sorted(reasons(BACKUPS, TODAY)))
            self.assertEqual(len(retain(BACKUPS, TODAY)), 9)

        def test_prune(self):
            keep, delete = prune(BACKUPS, TODAY)
            self.assertEqual(keep, retain(BACKUPS, TODAY))
            self.assertEqual(delete, [DT(2022, 12, 31, 23), DT(2025, 2, 1, 2), DT(2025, 3, 3, 2), DT(2025, 3, 5, 2), DT(2025, 3, 12, 2), DT(2025, 3, 13, 2)])
            self.assertEqual(sorted(keep + delete), sorted(set(BACKUPS)))


    class SingleRules(unittest.TestCase):
        def only(self, **rule):
            policy = {"daily": 0, "weekly": 0, "monthly": 0, "yearly": 0}
            policy.update(rule)
            return retain(BACKUPS, TODAY, **policy)

        def test_everything_off(self):
            self.assertEqual(self.only(), [])

        def test_daily(self):
            self.assertEqual(self.only(daily=1), [DT(2025, 3, 12, 14)])
            self.assertEqual(self.only(daily=3), [DT(2025, 3, 10, 2), DT(2025, 3, 11, 2), DT(2025, 3, 12, 14)])
            self.assertEqual(self.only(daily=4), [DT(2025, 3, 9, 2), DT(2025, 3, 10, 2), DT(2025, 3, 11, 2), DT(2025, 3, 12, 14)])
            self.assertEqual(self.only(daily=8)[0], DT(2025, 3, 5, 2))

        def test_weekly(self):
            self.assertEqual(self.only(weekly=1), [DT(2025, 3, 12, 14)])
            self.assertEqual(self.only(weekly=2), [DT(2025, 3, 9, 2), DT(2025, 3, 12, 14)])
            self.assertEqual(self.only(weekly=3), [DT(2025, 2, 28, 2), DT(2025, 3, 9, 2), DT(2025, 3, 12, 14)])

        def test_monthly(self):
            self.assertEqual(self.only(monthly=1), [DT(2025, 3, 12, 14)])
            self.assertEqual(self.only(monthly=3), [DT(2025, 1, 15, 2), DT(2025, 2, 28, 2), DT(2025, 3, 12, 14)])
            self.assertEqual(self.only(monthly=4), [DT(2024, 12, 31, 2), DT(2025, 1, 15, 2), DT(2025, 2, 28, 2), DT(2025, 3, 12, 14)])
            self.assertEqual(self.only(monthly=10)[0], DT(2024, 6, 1, 2))
            self.assertEqual(self.only(monthly=9)[0], DT(2024, 12, 31, 2))

        def test_yearly(self):
            self.assertEqual(self.only(yearly=1), [DT(2025, 3, 12, 14)])
            self.assertEqual(self.only(yearly=2), [DT(2024, 12, 31, 2), DT(2025, 3, 12, 14)])
            self.assertEqual(self.only(yearly=3), [DT(2023, 2, 2, 2), DT(2024, 12, 31, 2), DT(2025, 3, 12, 14)])
            self.assertEqual(self.only(yearly=4)[0], DT(2022, 12, 31, 23))


    class Details(unittest.TestCase):
        def test_future_backups_are_ignored(self):
            self.assertEqual(retain([DT(2025, 3, 13, 0, 0)], TODAY), [])
            self.assertEqual(retain([DT(2025, 3, 12, 23, 59)], TODAY), [DT(2025, 3, 12, 23, 59)])
            self.assertEqual(prune([DT(2025, 3, 13, 0, 0)], TODAY), ([], [DT(2025, 3, 13, 0, 0)]))

        def test_week_boundaries_are_mondays(self):
            sunday, monday = DT(2025, 3, 9, 23), DT(2025, 3, 10, 1)
            self.assertEqual(retain([sunday, monday], TODAY, daily=0, weekly=1, monthly=0, yearly=0), [monday])
            self.assertEqual(retain([sunday, monday], TODAY, daily=0, weekly=2, monthly=0, yearly=0), [sunday, monday])
            self.assertEqual(retain([sunday], TODAY, daily=0, weekly=1, monthly=0, yearly=0), [])

        def test_month_and_year_edges(self):
            backups = [DT(2024, 12, 31, 23), DT(2025, 1, 1, 0), DT(2025, 2, 28, 12), DT(2025, 3, 1, 0)]
            self.assertEqual(retain(backups, TODAY, daily=0, weekly=0, monthly=1, yearly=0), [DT(2025, 3, 1, 0)])
            self.assertEqual(retain(backups, TODAY, daily=0, weekly=0, monthly=2, yearly=0), [DT(2025, 2, 28, 12), DT(2025, 3, 1, 0)])
            self.assertEqual(retain(backups, TODAY, daily=0, weekly=0, monthly=0, yearly=1), [DT(2025, 3, 1, 0)])
            self.assertEqual(retain(backups, TODAY, daily=0, weekly=0, monthly=0, yearly=2), [DT(2024, 12, 31, 23), DT(2025, 3, 1, 0)])

        def test_months_count_across_years(self):
            today = date(2025, 1, 20)
            backups = [DT(2024, 2, 1), DT(2024, 1, 31), DT(2024, 12, 5), DT(2025, 1, 2)]
            got = retain(backups, today, daily=0, weekly=0, monthly=12, yearly=0)
            self.assertEqual(got, [DT(2024, 2, 1), DT(2024, 12, 5), DT(2025, 1, 2)])
            got = retain(backups, today, daily=0, weekly=0, monthly=13, yearly=0)
            self.assertEqual(got, [DT(2024, 1, 31), DT(2024, 2, 1), DT(2024, 12, 5), DT(2025, 1, 2)])

        def test_duplicates_and_order(self):
            b = DT(2025, 3, 12, 2)
            self.assertEqual(retain([b, b, b], TODAY), [b])
            self.assertEqual(retain(list(reversed(BACKUPS)), TODAY), retain(BACKUPS, TODAY))
            self.assertEqual(prune([b, b], TODAY), ([b], []))

        def test_newest_of_a_bucket_wins(self):
            early, late = DT(2025, 3, 12, 1), DT(2025, 3, 12, 23)
            self.assertEqual(retain([late, early], TODAY), [late])

        def test_bad_policies(self):
            for policy in ({"hourly": 3}, {"daily": -1}, {"yearly": -5}, {"weekly": 1, "decade": 1}):
                with self.assertRaises(ValueError, msg=policy):
                    retain(BACKUPS, TODAY, **policy)
                with self.assertRaises(ValueError, msg=policy):
                    prune(BACKUPS, TODAY, **policy)
                with self.assertRaises(ValueError, msg=policy):
                    reasons(BACKUPS, TODAY, **policy)

        def test_matches_a_brute_force_check(self):
            backups = [DT(2021, 1, 1, 3) + timedelta(days=i, hours=i % 5) for i in range(1600)]
            today = date(2025, 2, 10)
            backups = [b for b in backups if b.date() <= date(2025, 2, 20)]
            days = [today - timedelta(days=i) for i in range(7)]
            expect = {max(b for b in backups if b.date() == d) for d in days}
            monday = today - timedelta(days=today.weekday())
            for i in range(4):
                start = monday - timedelta(days=7 * i)
                expect.add(max(b for b in backups if start <= b.date() < start + timedelta(days=7) and b.date() <= today))
            year, month = today.year, today.month
            for _ in range(12):
                expect.add(max(b for b in backups if (b.year, b.month) == (year, month) and b.date() <= today))
                month -= 1
                if month == 0:
                    year, month = year - 1, 12
            for year in (2025, 2024, 2023):
                expect.add(max(b for b in backups if b.year == year and b.date() <= today))
            self.assertEqual(retain(backups, today), sorted(expect))


    if __name__ == "__main__":
        unittest.main()
''')

RETENTION = Lib(
    name="retention", lang="python", title="the backup retention policy (`retention/policy.py`)",
    blurb="The storage server decides which nightly backups to keep, with daily, weekly, monthly and yearly generations, using retention.",
    files={"retention/__init__.py": "", "retention/policy.py": RT_SRC, "README.md": RT_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": RT_VISIBLE},
    hidden_tests={"tests/test_full.py": RT_HIDDEN},
    mutate=["retention/policy.py"], difficulty=3, tags=["backup", "retention", "dates"],
    probes=[
        "retain([datetime(2025, 3, 12, 2), datetime(2025, 3, 10, 2), datetime(2025, 3, 5, 2), datetime(2025, 2, 1, 2), datetime(2024, 6, 1, 2)], date(2025, 3, 12))", "retain([datetime(2025, 3, 12, 2), datetime(2025, 3, 10, 2), datetime(2025, 3, 5, 2), datetime(2025, 2, 1, 2), datetime(2024, 6, 1, 2)], date(2025, 3, 12), daily=2, weekly=0, monthly=0, yearly=0)",
        "retain([datetime(2025, 3, 12, 2), datetime(2025, 3, 10, 2), datetime(2025, 3, 5, 2), datetime(2025, 2, 1, 2), datetime(2024, 6, 1, 2)], date(2025, 3, 12), daily=0, weekly=2, monthly=0, yearly=0)", "retain([datetime(2025, 3, 12, 2), datetime(2025, 3, 10, 2), datetime(2025, 3, 5, 2), datetime(2025, 2, 1, 2), datetime(2024, 6, 1, 2)], date(2025, 3, 12), daily=0, weekly=0, monthly=2, yearly=0)",
        "retain([datetime(2025, 3, 12, 2), datetime(2025, 3, 10, 2), datetime(2025, 3, 5, 2), datetime(2025, 2, 1, 2), datetime(2024, 6, 1, 2)], date(2025, 3, 12), daily=0, weekly=0, monthly=0, yearly=2)", "reasons([datetime(2025, 3, 12, 2), datetime(2025, 3, 10, 2), datetime(2025, 3, 5, 2), datetime(2025, 2, 1, 2), datetime(2024, 6, 1, 2)], date(2025, 3, 12))[datetime(2025, 3, 12, 2)]",
        "prune([datetime(2025, 3, 12, 2), datetime(2025, 3, 10, 2), datetime(2025, 3, 5, 2), datetime(2025, 2, 1, 2), datetime(2024, 6, 1, 2)], date(2025, 3, 12))[1]", "retain([datetime(2025, 3, 13)], date(2025, 3, 12))", "retain([datetime(2025, 3, 9, 23), datetime(2025, 3, 10, 1)], date(2025, 3, 12), daily=0, weekly=1, monthly=0, yearly=0)",
        "retain([datetime(2025, 3, 12, 2), datetime(2025, 3, 10, 2), datetime(2025, 3, 5, 2), datetime(2025, 2, 1, 2), datetime(2024, 6, 1, 2)], date(2025, 3, 12), hourly=2)",
    ],
    probe_import="from datetime import date, datetime\nfrom retention.policy import *",
)

register_libs([WATERBILL, SPRINTCAP, RETENTION], n=10)
