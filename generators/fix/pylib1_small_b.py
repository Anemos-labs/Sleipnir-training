"""Python libraries, theme time/money/scheduling (batch small-b): utility-bill split, harbour dues, loyalty points with
expiry, subscription renewals."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# flatshare: split a utility bill between flatmates by presence
# ======================================================================================================================

FS_README = dd('''
    # flatshare

    Splits a shared utility bill between flatmates. Money is an `int` number of cents; dates are `datetime.date`.
    Billing periods are half-open `[start, end)`.

    * `person_days(move_in, move_out, start, end)`: the number of days of `[start, end)` that a tenant lives in the
      flat. The tenant lives there from `move_in` (included) to `move_out` (excluded); `move_out` is `None` for
      somebody who has not moved out. A tenant who is not there at all gets `0`. `move_out < move_in` is a `ValueError`.
    * `split_bill(total, tenants, start, end)`: `tenants` is a list of `(name, move_in, move_out)`; returns a dict
      `{name: cents}` that adds up to `total`.
      - 40% of the bill (`total * 40 // 100`, rounded down) is the **fixed part**, shared equally by every tenant
        who lives there at least one day of the period. The rest is the **variable part**, shared in proportion to
        the person-days.
      - Both parts are first rounded down for every tenant. The cents that are left over are handed out one at a
        time, to the tenants ordered by person-days (most first, ties by name), going round again if there are more
        cents than tenants.
      - A tenant without a single day pays `0` (and is still in the result). Nobody living there at all is a
        `ValueError`, and so are duplicate names.
''')

FS_SRC = dd('''
    FIXED_PERCENT = 40


    def person_days(move_in, move_out, start, end):
        if move_out is not None and move_out < move_in:
            raise ValueError("move-out before move-in")
        low = max(move_in, start)
        high = end if move_out is None else min(move_out, end)
        return max(0, (high - low).days)


    def split_bill(total, tenants, start, end):
        days = {}
        for name, move_in, move_out in tenants:
            if name in days:
                raise ValueError(f"duplicate tenant {name!r}")
            days[name] = person_days(move_in, move_out, start, end)
        present = sorted(n for n, d in days.items() if d > 0)
        if not present:
            raise ValueError("nobody lives in the flat in this period")
        fixed = total * FIXED_PERCENT // 100
        variable = total - fixed
        all_days = sum(days.values())
        shares = {name: 0 for name in days}
        for name in present:
            shares[name] = fixed // len(present) + variable * days[name] // all_days
        left = total - sum(shares.values())
        order = sorted(present, key=lambda n: (-days[n], n))
        for k in range(left):
            shares[order[k % len(order)]] += 1
        return shares
''')

FS_VISIBLE = dd('''
    import unittest
    from datetime import date

    from flatshare.split import person_days, split_bill


    class BasicTests(unittest.TestCase):
        def test_days(self):
            self.assertEqual(person_days(date(2025, 3, 16), None, date(2025, 3, 1), date(2025, 4, 1)), 16)

        def test_even_split(self):
            tenants = [("ada", date(2025, 1, 1), None), ("bo", date(2025, 1, 1), None)]
            got = split_bill(10_000, tenants, date(2025, 3, 1), date(2025, 4, 1))
            self.assertEqual(got, {"ada": 5000, "bo": 5000})


    if __name__ == "__main__":
        unittest.main()
''')

FS_HIDDEN = dd('''
    import unittest
    from datetime import date

    from flatshare.split import person_days, split_bill

    D = date
    START, END = D(2025, 3, 1), D(2025, 4, 1)  # 31 days
    LONG_AGO = D(2024, 1, 1)


    class PersonDays(unittest.TestCase):
        def test_whole_period(self):
            self.assertEqual(person_days(LONG_AGO, None, START, END), 31)
            self.assertEqual(person_days(LONG_AGO, D(2026, 1, 1), START, END), 31)
            self.assertEqual(person_days(START, END, START, END), 31)

        def test_partial(self):
            self.assertEqual(person_days(D(2025, 3, 16), None, START, END), 16)
            self.assertEqual(person_days(LONG_AGO, D(2025, 3, 11), START, END), 10)
            self.assertEqual(person_days(D(2025, 3, 10), D(2025, 3, 20), START, END), 10)
            self.assertEqual(person_days(D(2025, 3, 31), None, START, END), 1)

        def test_outside(self):
            self.assertEqual(person_days(LONG_AGO, START, START, END), 0)
            self.assertEqual(person_days(END, None, START, END), 0)
            self.assertEqual(person_days(D(2025, 5, 1), None, START, END), 0)
            self.assertEqual(person_days(LONG_AGO, D(2024, 6, 1), START, END), 0)

        def test_zero_stay_and_bad_order(self):
            self.assertEqual(person_days(D(2025, 3, 5), D(2025, 3, 5), START, END), 0)
            with self.assertRaises(ValueError):
                person_days(D(2025, 3, 5), D(2025, 3, 4), START, END)
            with self.assertRaises(ValueError):
                person_days(D(2030, 3, 5), D(2030, 3, 4), START, END)


    class Split(unittest.TestCase):
        TENANTS = [("ada", LONG_AGO, None), ("bo", D(2025, 3, 16), None), ("cy", LONG_AGO, D(2025, 3, 11))]

        def test_three_tenants(self):
            # 57 person-days: fixed 4000 / 3 = 1333 each; variable 6000 split 31 : 16 : 10 -> 3263, 1684, 1052
            got = split_bill(10_000, self.TENANTS, START, END)
            self.assertEqual(got, {"ada": 4597, "bo": 3018, "cy": 2385})
            self.assertEqual(sum(got.values()), 10_000)

        def test_sum_is_always_the_total(self):
            for total in (0, 1, 2, 7, 99, 100, 101, 12_345, 99_999):
                got = split_bill(total, self.TENANTS, START, END)
                self.assertEqual(sum(got.values()), total, total)
                self.assertEqual(set(got), {"ada", "bo", "cy"})

        def test_single_tenant_pays_everything(self):
            self.assertEqual(split_bill(12_345, [("ada", LONG_AGO, None)], START, END), {"ada": 12_345})

        def test_absent_tenant_pays_nothing(self):
            tenants = [("ada", LONG_AGO, None), ("bo", END, None), ("cy", LONG_AGO, START)]
            self.assertEqual(split_bill(1000, tenants, START, END), {"ada": 1000, "bo": 0, "cy": 0})

        def test_fixed_part_is_equal_even_for_one_day(self):
            tenants = [("ada", LONG_AGO, None), ("bo", D(2025, 3, 31), None)]
            got = split_bill(31_000, tenants, START, END)
            # fixed 12400 -> 6200 each ; variable 18600 -> ada 18600 * 31 // 32 = 18018 ; bo 581 ; one cent left for ada
            self.assertEqual(got, {"ada": 6200 + 18_018 + 1, "bo": 6200 + 581})

        def test_leftover_goes_by_days_then_name(self):
            tenants = [("bo", LONG_AGO, None), ("ada", LONG_AGO, None)]
            self.assertEqual(split_bill(101, tenants, START, END), {"ada": 51, "bo": 50})
            self.assertEqual(split_bill(1, tenants, START, END), {"ada": 1, "bo": 0})
            tenants = [("zed", LONG_AGO, None), ("ada", D(2025, 3, 11), None), ("bo", D(2025, 3, 11), None)]
            got = split_bill(10, tenants, START, END)
            self.assertEqual(sum(got.values()), 10)
            self.assertEqual(got["zed"], max(got.values()))

        def test_leftover_cycles_over_the_tenants(self):
            tenants = [("a", LONG_AGO, None), ("b", LONG_AGO, None), ("c", LONG_AGO, None)]
            self.assertEqual(split_bill(7, tenants, START, END), {"a": 3, "b": 2, "c": 2})

        def test_zero_total(self):
            self.assertEqual(split_bill(0, self.TENANTS, START, END), {"ada": 0, "bo": 0, "cy": 0})

        def test_errors(self):
            with self.assertRaises(ValueError):
                split_bill(100, [], START, END)
            with self.assertRaises(ValueError):
                split_bill(100, [("ada", END, None)], START, END)
            with self.assertRaises(ValueError):
                split_bill(100, [("ada", LONG_AGO, None), ("ada", LONG_AGO, None)], START, END)
            with self.assertRaises(ValueError):
                split_bill(100, [("ada", LONG_AGO, None), ("ada", END, None)], START, END)


    if __name__ == "__main__":
        unittest.main()
''')

FLATSHARE = Lib(
    name="flatshare", lang="python", title="the shared-flat bill splitter (`flatshare/split.py`)",
    blurb="The flatmates' budgeting app divides a utility bill by who lived in the flat on which days, using flatshare.",
    files={"flatshare/__init__.py": "", "flatshare/split.py": FS_SRC, "README.md": FS_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": FS_VISIBLE},
    hidden_tests={"tests/test_full.py": FS_HIDDEN},
    mutate=["flatshare/split.py"], difficulty=2, tags=["bills", "allocation", "dates"],
    probes=[
        "person_days(date(2025, 3, 16), None, date(2025, 3, 1), date(2025, 4, 1))",
        "person_days(date(2024, 1, 1), date(2025, 3, 11), date(2025, 3, 1), date(2025, 4, 1))",
        "person_days(date(2025, 4, 1), None, date(2025, 3, 1), date(2025, 4, 1))",
        "split_bill(10_000, [('ada', date(2024, 1, 1), None), ('bo', date(2025, 3, 16), None), ('cy', date(2024, 1, 1), date(2025, 3, 11))], date(2025, 3, 1), date(2025, 4, 1))",
        "split_bill(101, [('bo', date(2024, 1, 1), None), ('ada', date(2024, 1, 1), None)], date(2025, 3, 1), date(2025, 4, 1))",
        "split_bill(7, [('a', date(2024, 1, 1), None), ('b', date(2024, 1, 1), None), ('c', date(2024, 1, 1), None)], date(2025, 3, 1), date(2025, 4, 1))",
        "split_bill(31_000, [('ada', date(2024, 1, 1), None), ('bo', date(2025, 3, 31), None)], date(2025, 3, 1), date(2025, 4, 1))",
    ],
    probe_import="from datetime import date\nfrom flatshare.split import *",
)

# ======================================================================================================================
# harborfees: harbour dues, long-stay discount, pilotage and tugs
# ======================================================================================================================

HF_README = dd('''
    # harborfees

    Charges of the port of Skarvik for a ship's call. Money is an `int` number of cents; ships are measured in gross
    tonnage (`gt`); times are minutes.

    ## Dues (`harborfees/dues.py`)

    * `daily_due(gt)`: marginal bands per gross tonne and day: 8 cents for the first 500 GT, 5 cents for the GT from
      501 to 3000, 3 cents above 3000. `gt <= 0` is a `ValueError`, and so it is in every function below; a call of
      `minutes <= 0` is a `ValueError` in all of them as well.
    * `days_charged(minutes)`: every started 24 hours (1440 minutes) is a day. `minutes <= 0` is a `ValueError`.
    * `stay_dues(gt, minutes)`: a call of at most 120 minutes is a turnaround and pays half of one daily due (rounded
      down). Otherwise the first 7 days pay the full daily due and every further day 70% of it, each such day rounded
      half up to a cent.
    * `harbour_dues(gt, minutes, green=False)`: `stay_dues`; for a ship with a green certificate 15% of that is taken
      off (the discount is rounded down); the result is never below the minimum charge of 2500.

    ## Pilotage and tugs (`harborfees/pilot.py`)

    * `is_night(minute)`: from 22:00 (inclusive) until 06:00 (exclusive).
    * `pilot_fee(gt, arrival_minute)`: ships below 500 GT take no pilot (`0`). Otherwise 30000 plus 12 cents for every
      GT above 1000. A night arrival (`is_night(arrival_minute)`) pays 25% more.
    * `tugs_required(gt)`: `2` above 8000 GT, `1` above 3000 GT, otherwise `0`. `tug_fee(gt)` is 18000 per tug.
    * `call_cost(gt, minutes, arrival_minute, green=False)`: a dict with `dues`, `pilot`, `tugs` and `total` (their sum).
''')

HF_DUES = dd('''
    BANDS = [(0, 8), (500, 5), (3000, 3)]
    TURNAROUND_MINUTES = 120
    DAY_MINUTES = 1440
    FULL_RATE_DAYS = 7
    LONG_STAY_PERCENT = 70
    GREEN_PERCENT = 15
    MINIMUM = 2500


    def daily_due(gt):
        if gt <= 0:
            raise ValueError("gross tonnage must be positive")
        total = 0
        for i, (low, rate) in enumerate(BANDS):
            high = BANDS[i + 1][0] if i + 1 < len(BANDS) else None
            if gt <= low:
                break
            top = gt if high is None else min(gt, high)
            total += (top - low) * rate
        return total


    def days_charged(minutes):
        if minutes <= 0:
            raise ValueError("a call lasts at least one minute")
        return -(-minutes // DAY_MINUTES)


    def stay_dues(gt, minutes):
        day = daily_due(gt)
        days = days_charged(minutes)
        if minutes <= TURNAROUND_MINUTES:
            return day // 2
        full = min(days, FULL_RATE_DAYS)
        reduced = (day * LONG_STAY_PERCENT + 50) // 100
        return full * day + (days - full) * reduced


    def harbour_dues(gt, minutes, green=False):
        total = stay_dues(gt, minutes)
        if green:
            total -= total * GREEN_PERCENT // 100
        return max(total, MINIMUM)
''')

HF_PILOT = dd('''
    from .dues import harbour_dues

    PILOT_FROM_GT = 500
    PILOT_FLAT = 30_000
    PILOT_OVER_GT = 1000
    PILOT_PER_GT = 12
    NIGHT_PERCENT = 25
    TUG_FEE = 18_000


    def is_night(minute):
        return minute >= 22 * 60 or minute < 6 * 60


    def pilot_fee(gt, arrival_minute):
        if gt < PILOT_FROM_GT:
            return 0
        fee = PILOT_FLAT + max(0, gt - PILOT_OVER_GT) * PILOT_PER_GT
        if is_night(arrival_minute):
            fee += fee * NIGHT_PERCENT // 100
        return fee


    def tugs_required(gt):
        if gt > 8000:
            return 2
        if gt > 3000:
            return 1
        return 0


    def tug_fee(gt):
        return tugs_required(gt) * TUG_FEE


    def call_cost(gt, minutes, arrival_minute, green=False):
        dues = harbour_dues(gt, minutes, green)
        pilot = pilot_fee(gt, arrival_minute)
        tugs = tug_fee(gt)
        return {"dues": dues, "pilot": pilot, "tugs": tugs, "total": dues + pilot + tugs}
''')

HF_VISIBLE = dd('''
    import unittest

    from harborfees.dues import daily_due, days_charged
    from harborfees.pilot import pilot_fee


    class BasicTests(unittest.TestCase):
        def test_small_ship(self):
            self.assertEqual(daily_due(100), 800)

        def test_days(self):
            self.assertEqual(days_charged(1440), 1)

        def test_pilot(self):
            self.assertEqual(pilot_fee(1000, 700), 30_000)


    if __name__ == "__main__":
        unittest.main()
''')

HF_HIDDEN = dd('''
    import unittest

    from harborfees.dues import daily_due, days_charged, harbour_dues, stay_dues
    from harborfees.pilot import call_cost, is_night, pilot_fee, tug_fee, tugs_required


    class Daily(unittest.TestCase):
        def test_bands(self):
            table = {1: 8, 100: 800, 500: 4000, 501: 4005, 1000: 6500, 3000: 16_500, 3001: 16_503, 10_000: 37_500}
            for gt, cents in table.items():
                self.assertEqual(daily_due(gt), cents, gt)

        def test_invalid(self):
            for gt in (0, -5):
                with self.assertRaises(ValueError):
                    daily_due(gt)


    class Days(unittest.TestCase):
        def test_started_days(self):
            table = {1: 1, 120: 1, 1439: 1, 1440: 1, 1441: 2, 2880: 2, 2881: 3, 10_080: 7, 10_081: 8}
            for minutes, days in table.items():
                self.assertEqual(days_charged(minutes), days, minutes)

        def test_invalid(self):
            for minutes in (0, -1):
                with self.assertRaises(ValueError):
                    days_charged(minutes)


    class Stay(unittest.TestCase):
        def test_turnaround(self):
            self.assertEqual(stay_dues(1000, 1), 3250)
            self.assertEqual(stay_dues(1000, 120), 3250)
            self.assertEqual(stay_dues(1000, 121), 6500)
            self.assertEqual(stay_dues(501, 60), 2002)   # 4005 // 2

        def test_full_days(self):
            self.assertEqual(stay_dues(1000, 1440), 6500)
            self.assertEqual(stay_dues(1000, 1441), 13_000)
            self.assertEqual(stay_dues(1000, 10_080), 45_500)

        def test_long_stay_discount(self):
            self.assertEqual(stay_dues(1000, 10_081), 45_500 + 4550)
            self.assertEqual(stay_dues(1000, 14_400), 45_500 + 3 * 4550)

        def test_long_stay_rounds_half_up(self):
            # 70% of 4005 is 2803.5
            self.assertEqual(stay_dues(501, 10_081), 7 * 4005 + 2804)
            self.assertEqual(stay_dues(501, 11_521), 7 * 4005 + 2 * 2804)

        def test_errors(self):
            with self.assertRaises(ValueError):
                stay_dues(0, 100)
            with self.assertRaises(ValueError):
                stay_dues(100, 0)


    class Dues(unittest.TestCase):
        def test_plain(self):
            self.assertEqual(harbour_dues(1000, 1440), 6500)
            self.assertEqual(harbour_dues(1000, 1441), 13_000)

        def test_minimum(self):
            self.assertEqual(harbour_dues(100, 600), 2500)
            self.assertEqual(harbour_dues(100, 60), 2500)
            self.assertEqual(harbour_dues(400, 1440), 3200)
            self.assertEqual(harbour_dues(312, 1440), 2500)
            self.assertEqual(harbour_dues(313, 1440), 2504)

        def test_green_discount(self):
            self.assertEqual(harbour_dues(1000, 1440, green=True), 5525)
            self.assertEqual(harbour_dues(501, 1440, green=True), 3405)   # 4005 - 600 (600.75 rounded down)
            self.assertEqual(harbour_dues(1000, 1440, green=False), 6500)

        def test_minimum_comes_after_the_discount(self):
            self.assertEqual(harbour_dues(300, 1440, green=True), 2500)
            self.assertEqual(harbour_dues(400, 1440, green=True), 2720)

        def test_errors(self):
            with self.assertRaises(ValueError):
                harbour_dues(-1, 100)


    class Pilot(unittest.TestCase):
        def test_night_window(self):
            table = {0: True, 359: True, 360: False, 720: False, 1319: False, 1320: True, 1439: True}
            for minute, night in table.items():
                self.assertEqual(is_night(minute), night, minute)

        def test_fee(self):
            table = {1: 0, 499: 0, 500: 30_000, 1000: 30_000, 1001: 30_012, 3000: 54_000}
            for gt, cents in table.items():
                self.assertEqual(pilot_fee(gt, 720), cents, gt)

        def test_night_arrival(self):
            self.assertEqual(pilot_fee(1000, 1320), 37_500)
            self.assertEqual(pilot_fee(1000, 1319), 30_000)
            self.assertEqual(pilot_fee(1000, 359), 37_500)
            self.assertEqual(pilot_fee(1000, 360), 30_000)
            self.assertEqual(pilot_fee(499, 1400), 0)
            self.assertEqual(pilot_fee(3000, 0), 67_500)

        def test_tugs(self):
            table = {100: 0, 3000: 0, 3001: 1, 8000: 1, 8001: 2, 20_000: 2}
            for gt, n in table.items():
                self.assertEqual(tugs_required(gt), n, gt)
                self.assertEqual(tug_fee(gt), n * 18_000, gt)


    class CallCost(unittest.TestCase):
        def test_everything(self):
            got = call_cost(3001, 1500, 700)
            self.assertEqual(got, {"dues": 33_006, "pilot": 54_012, "tugs": 18_000, "total": 105_018})

        def test_green_only_changes_the_dues(self):
            got = call_cost(3001, 1500, 700, green=True)
            self.assertEqual(got, {"dues": 28_056, "pilot": 54_012, "tugs": 18_000, "total": 100_068})

        def test_small_ship(self):
            got = call_cost(100, 60, 1400)
            self.assertEqual(got, {"dues": 2500, "pilot": 0, "tugs": 0, "total": 2500})

        def test_big_ship_at_night(self):
            # turnaround: half of 34 500; pilot 30 000 + 8000 * 12 = 126 000, plus 25% at night; two tugs
            got = call_cost(9000, 100, 1330)
            self.assertEqual(got, {"dues": 17_250, "pilot": 157_500, "tugs": 36_000, "total": 210_750})


    if __name__ == "__main__":
        unittest.main()
''')

HARBORFEES = Lib(
    name="harborfees", lang="python", title="the Skarvik port charges (`harborfees/`)",
    blurb="The Skarvik harbour office invoices a ship's call (dues, pilot and tugs) with the harborfees package.",
    files={"harborfees/__init__.py": "", "harborfees/dues.py": HF_DUES, "harborfees/pilot.py": HF_PILOT,
           "README.md": HF_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": HF_VISIBLE},
    hidden_tests={"tests/test_full.py": HF_HIDDEN},
    mutate=["harborfees/dues.py", "harborfees/pilot.py"], difficulty=2, tags=["port", "tariff", "money"],
    probes=[
        "daily_due(501)", "daily_due(3001)", "days_charged(1441)", "stay_dues(1000, 120)", "stay_dues(1000, 121)",
        "stay_dues(501, 10_081)", "stay_dues(1000, 14_400)", "harbour_dues(100, 600)", "harbour_dues(501, 1440, green=True)",
        "harbour_dues(313, 1440)", "pilot_fee(499, 720)", "pilot_fee(1000, 1320)", "pilot_fee(1001, 720)", "tugs_required(8001)",
        "call_cost(3001, 1500, 700)", "call_cost(3001, 1500, 700, green=True)",
    ],
    probe_import="from harborfees.dues import *\nfrom harborfees.pilot import *",
)

# ======================================================================================================================
# pointsbank: loyalty points in lots with month-end expiry, redemption order and tiers
# ======================================================================================================================

PB_README = dd('''
    # pointsbank

    Loyalty points for a shop chain. Points are whole numbers; dates are `datetime.date`. A **lot** is a tuple
    `(earned_on, points, expires_on)`.

    ## Lots (`pointsbank/lots.py`)

    * `expiry_of(earned_on)`: points expire at the **end of the month, 18 months after the month in which they were
      earned**: a lot earned on 2025-01-15 expires on 2026-07-31. A lot is still usable on its expiry date.
    * `earn(lots, points, on)`: a new list holding the old lots and a new lot `(on, points, expiry_of(on))`, sorted
      (as tuples). `points <= 0` is a `ValueError`. The argument list is not modified.
    * `balance(lots, today)`: the points in lots that have not expired on `today`.
    * `redeem(lots, points, today)`: spends `points` from the lots that have not expired, **earliest expiry first**
      (lots with the same expiry date: earliest earned first). Returns a new sorted list of the lots that still hold
      points; lots that are used up and lots that have already expired are not in it. `points <= 0`, or more points
      than `balance(lots, today)`, is a `ValueError`. The argument list is not modified.
    * `expiring(lots, today, days=30)`: the points in unexpired lots whose expiry date is at most `days` days after
      `today` (that day included).

    ## Tiers (`pointsbank/tiers.py`)

    Tiers by points earned in the last 365 days (the window is the 365 days ending on `today`, `today` included):
    `bronze` from 0, `silver` from 1000, `gold` from 5000, `platinum` from 15000.

    * `earned_in_window(history, today)`: the sum of the points of the `(date, points)` entries of `history` inside the
      window (entries after `today` do not count).
    * `tier_for(points)`: the tier name.
    * `purchase_points(amount_cents, tier)`: one point per full 100 cents, plus a bonus of 50 points when the purchase
      is 10000 cents or more; the total is then multiplied by the tier's percentage (`bronze` 100, `silver` 125,
      `gold` 150, `platinum` 200) and rounded down.
    * `earn_purchase(lots, history, amount_cents, on)`: the tier is the member's tier on `on` according to `history`
      (before this purchase). Returns `(lots, history, points)` where, when `points > 0`, the new lot is added with
      `earn` and `(on, points)` is appended to a copy of `history`; with no points both lists come back unchanged.
''')

PB_LOTS = dd('''
    import calendar
    from datetime import date, timedelta

    EXPIRY_MONTHS = 18


    def expiry_of(earned_on):
        index = earned_on.year * 12 + earned_on.month - 1 + EXPIRY_MONTHS
        year, month0 = divmod(index, 12)
        month = month0 + 1
        return date(year, month, calendar.monthrange(year, month)[1])


    def earn(lots, points, on):
        if points <= 0:
            raise ValueError("points must be positive")
        return sorted(list(lots) + [(on, points, expiry_of(on))])


    def balance(lots, today):
        return sum(points for _, points, expires in lots if expires >= today)


    def redeem(lots, points, today):
        if points <= 0:
            raise ValueError("points must be positive")
        live = sorted((lot for lot in lots if lot[2] >= today), key=lambda lot: (lot[2], lot[0]))
        if sum(lot[1] for lot in live) < points:
            raise ValueError("not enough points")
        left = points
        kept = []
        for earned_on, have, expires in live:
            take = min(have, left)
            left -= take
            if have > take:
                kept.append((earned_on, have - take, expires))
        return sorted(kept)


    def expiring(lots, today, days=30):
        horizon = today + timedelta(days=days)
        return sum(points for _, points, expires in lots if today <= expires <= horizon)
''')

PB_TIERS = dd('''
    from datetime import timedelta

    from .lots import earn

    TIERS = [("bronze", 0, 100), ("silver", 1000, 125), ("gold", 5000, 150), ("platinum", 15000, 200)]
    WINDOW_DAYS = 365
    BONUS_FROM = 10_000
    BONUS_POINTS = 50


    def earned_in_window(history, today):
        first = today - timedelta(days=WINDOW_DAYS - 1)
        return sum(points for when, points in history if first <= when <= today)


    def tier_for(points):
        name = TIERS[0][0]
        for tier, threshold, _ in TIERS:
            if points >= threshold:
                name = tier
        return name


    def purchase_points(amount_cents, tier):
        base = amount_cents // 100
        if amount_cents >= BONUS_FROM:
            base += BONUS_POINTS
        percent = {name: pct for name, _, pct in TIERS}[tier]
        return base * percent // 100


    def earn_purchase(lots, history, amount_cents, on):
        tier = tier_for(earned_in_window(history, on))
        points = purchase_points(amount_cents, tier)
        if points <= 0:
            return lots, history, 0
        return earn(lots, points, on), list(history) + [(on, points)], points
''')

PB_VISIBLE = dd('''
    import unittest
    from datetime import date

    from pointsbank.lots import balance, earn, expiry_of
    from pointsbank.tiers import tier_for


    class BasicTests(unittest.TestCase):
        def test_expiry(self):
            self.assertEqual(expiry_of(date(2025, 1, 15)), date(2026, 7, 31))

        def test_earn_and_balance(self):
            lots = earn([], 100, date(2025, 1, 15))
            self.assertEqual(balance(lots, date(2025, 6, 1)), 100)

        def test_tier(self):
            self.assertEqual(tier_for(1200), "silver")


    if __name__ == "__main__":
        unittest.main()
''')

PB_HIDDEN = dd('''
    import unittest
    from datetime import date

    from pointsbank.lots import balance, earn, expiring, expiry_of, redeem
    from pointsbank.tiers import earn_purchase, earned_in_window, purchase_points, tier_for

    D = date
    A = (D(2025, 1, 10), 100, D(2026, 7, 31))
    B = (D(2024, 12, 5), 50, D(2026, 6, 30))
    C = (D(2024, 3, 1), 40, D(2025, 9, 30))
    LOTS = [A, B, C]


    class Expiry(unittest.TestCase):
        def test_end_of_month_eighteen_months_on(self):
            table = {D(2025, 1, 15): D(2026, 7, 31), D(2025, 1, 1): D(2026, 7, 31), D(2025, 1, 31): D(2026, 7, 31),
                     D(2024, 8, 31): D(2026, 2, 28), D(2023, 8, 31): D(2025, 2, 28), D(2022, 8, 10): D(2024, 2, 29),
                     D(2025, 12, 3): D(2027, 6, 30), D(2024, 6, 30): D(2025, 12, 31)}
            for earned, expires in table.items():
                self.assertEqual(expiry_of(earned), expires, earned)


    class Earn(unittest.TestCase):
        def test_new_lot(self):
            self.assertEqual(earn([], 100, D(2025, 1, 15)), [(D(2025, 1, 15), 100, D(2026, 7, 31))])

        def test_sorted_and_not_in_place(self):
            lots = [A]
            got = earn(lots, 5, D(2024, 1, 1))
            self.assertEqual(got, [(D(2024, 1, 1), 5, D(2025, 7, 31)), A])
            self.assertEqual(lots, [A])
            self.assertEqual(earn([B, A], 7, D(2025, 3, 1))[-1], (D(2025, 3, 1), 7, D(2026, 9, 30)))

        def test_points_must_be_positive(self):
            for points in (0, -3):
                with self.assertRaises(ValueError):
                    earn([], points, D(2025, 1, 1))


    class Balance(unittest.TestCase):
        def test_expiry_day_is_inclusive(self):
            table = {D(2025, 6, 1): 190, D(2025, 9, 30): 190, D(2025, 10, 1): 150, D(2026, 6, 30): 150, D(2026, 7, 1): 100,
                     D(2026, 7, 31): 100, D(2026, 8, 1): 0}
            for today, points in table.items():
                self.assertEqual(balance(LOTS, today), points, today)

        def test_empty(self):
            self.assertEqual(balance([], D(2025, 1, 1)), 0)


    class Redeem(unittest.TestCase):
        def test_earliest_expiry_first(self):
            got = redeem(LOTS, 70, D(2025, 6, 1))
            self.assertEqual(got, [(D(2024, 12, 5), 20, D(2026, 6, 30)), A])

        def test_exact_lot(self):
            self.assertEqual(redeem(LOTS, 40, D(2025, 6, 1)), [B, A])
            self.assertEqual(redeem(LOTS, 41, D(2025, 6, 1)), [(D(2024, 12, 5), 49, D(2026, 6, 30)), A])
            self.assertEqual(redeem(LOTS, 39, D(2025, 6, 1)), sorted([(D(2024, 3, 1), 1, D(2025, 9, 30)), B, A]))

        def test_everything(self):
            self.assertEqual(redeem(LOTS, 190, D(2025, 6, 1)), [])

        def test_expired_lots_are_skipped_and_dropped(self):
            self.assertEqual(redeem(LOTS, 70, D(2025, 10, 1)), [(D(2025, 1, 10), 80, D(2026, 7, 31))])
            self.assertEqual(redeem(LOTS, 150, D(2025, 10, 1)), [])
            self.assertEqual(redeem(LOTS, 10, D(2025, 9, 30))[0], (D(2024, 3, 1), 30, D(2025, 9, 30)))

        def test_same_expiry_earliest_earned_first(self):
            late = (D(2025, 1, 20), 10, D(2026, 7, 31))
            early = (D(2025, 1, 5), 10, D(2026, 7, 31))
            self.assertEqual(redeem([late, early], 10, D(2025, 6, 1)), [late])
            self.assertEqual(redeem([early, late], 5, D(2025, 6, 1)), [(D(2025, 1, 5), 5, D(2026, 7, 31)), late])

        def test_not_enough(self):
            with self.assertRaises(ValueError):
                redeem(LOTS, 191, D(2025, 6, 1))
            with self.assertRaises(ValueError):
                redeem(LOTS, 151, D(2025, 10, 1))
            with self.assertRaises(ValueError):
                redeem([], 1, D(2025, 10, 1))

        def test_points_must_be_positive(self):
            for points in (0, -1):
                with self.assertRaises(ValueError):
                    redeem(LOTS, points, D(2025, 6, 1))

        def test_input_is_not_modified(self):
            lots = list(LOTS)
            redeem(lots, 70, D(2025, 6, 1))
            self.assertEqual(lots, [A, B, C])


    class Expiring(unittest.TestCase):
        def test_thirty_days(self):
            self.assertEqual(expiring(LOTS, D(2025, 9, 1)), 40)
            self.assertEqual(expiring(LOTS, D(2025, 8, 31)), 40)
            self.assertEqual(expiring(LOTS, D(2025, 8, 30)), 0)
            self.assertEqual(expiring(LOTS, D(2025, 9, 30)), 40)
            self.assertEqual(expiring(LOTS, D(2025, 10, 1)), 0)

        def test_custom_horizon(self):
            self.assertEqual(expiring(LOTS, D(2026, 6, 1), days=60), 150)
            self.assertEqual(expiring(LOTS, D(2026, 6, 1), days=59), 50)
            self.assertEqual(expiring(LOTS, D(2026, 6, 1), days=0), 0)
            self.assertEqual(expiring(LOTS, D(2026, 6, 30), days=0), 50)


    class Tiers(unittest.TestCase):
        def test_thresholds(self):
            table = {0: "bronze", 999: "bronze", 1000: "silver", 4999: "silver", 5000: "gold", 14_999: "gold",
                     15_000: "platinum", 100_000: "platinum"}
            for points, tier in table.items():
                self.assertEqual(tier_for(points), tier, points)

        def test_window(self):
            history = [(D(2024, 6, 1), 500), (D(2024, 6, 2), 300), (D(2025, 6, 1), 200), (D(2025, 6, 2), 999)]
            self.assertEqual(earned_in_window(history, D(2025, 6, 1)), 500)
            self.assertEqual(earned_in_window(history, D(2025, 6, 2)), 1199)
            self.assertEqual(earned_in_window(history, D(2024, 6, 1)), 500)
            self.assertEqual(earned_in_window([], D(2025, 6, 1)), 0)

        def test_purchase_points(self):
            table = {(99, "bronze"): 0, (100, "bronze"): 1, (100, "silver"): 1, (100, "gold"): 1, (100, "platinum"): 2,
                     (199, "bronze"): 1, (800, "silver"): 10, (9999, "bronze"): 99, (9999, "silver"): 123, (9999, "gold"): 148,
                     (9999, "platinum"): 198, (10_000, "bronze"): 150, (10_000, "silver"): 187, (10_000, "gold"): 225,
                     (10_000, "platinum"): 300, (12_345, "gold"): 259}
            for (cents, tier), points in table.items():
                self.assertEqual(purchase_points(cents, tier), points, (cents, tier))

        def test_earn_purchase(self):
            lots, history, points = earn_purchase([], [], 10_000, D(2025, 6, 1))
            self.assertEqual(points, 150)
            self.assertEqual(lots, [(D(2025, 6, 1), 150, D(2026, 12, 31))])
            self.assertEqual(history, [(D(2025, 6, 1), 150)])

        def test_tier_comes_from_the_history(self):
            before = [(D(2025, 5, 1), 1000)]
            lots, history, points = earn_purchase([], before, 10_000, D(2025, 6, 1))
            self.assertEqual(points, 187)
            self.assertEqual(history, [(D(2025, 5, 1), 1000), (D(2025, 6, 1), 187)])
            self.assertEqual(before, [(D(2025, 5, 1), 1000)])

        def test_tier_is_taken_before_the_purchase(self):
            before = [(D(2025, 5, 1), 999)]
            _, _, points = earn_purchase([], before, 100, D(2025, 6, 1))
            self.assertEqual(points, 1)

        def test_old_history_does_not_count(self):
            _, _, points = earn_purchase([], [(D(2024, 5, 1), 5000)], 10_000, D(2025, 6, 1))
            self.assertEqual(points, 150)

        def test_no_points_no_change(self):
            lots, history, points = earn_purchase([A], [(D(2025, 1, 10), 100)], 50, D(2025, 6, 1))
            self.assertEqual((lots, history, points), ([A], [(D(2025, 1, 10), 100)], 0))


    if __name__ == "__main__":
        unittest.main()
''')

POINTSBANK = Lib(
    name="pointsbank", lang="python", title="the loyalty-points ledger (`pointsbank/`)",
    blurb="The shop chain's loyalty scheme tracks points in expiring lots, redemptions and member tiers with pointsbank.",
    files={"pointsbank/__init__.py": "", "pointsbank/lots.py": PB_LOTS, "pointsbank/tiers.py": PB_TIERS,
           "README.md": PB_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": PB_VISIBLE},
    hidden_tests={"tests/test_full.py": PB_HIDDEN},
    mutate=["pointsbank/lots.py", "pointsbank/tiers.py"], difficulty=3, tags=["loyalty", "expiry", "dates"],
    probes=[
        "expiry_of(date(2024, 8, 31))", "expiry_of(date(2022, 8, 10))", "balance([(date(2025, 1, 10), 100, date(2026, 7, 31)), (date(2024, 12, 5), 50, date(2026, 6, 30)), (date(2024, 3, 1), 40, date(2025, 9, 30))], date(2025, 9, 30))", "balance([(date(2025, 1, 10), 100, date(2026, 7, 31)), (date(2024, 12, 5), 50, date(2026, 6, 30)), (date(2024, 3, 1), 40, date(2025, 9, 30))], date(2025, 10, 1))",
        "redeem([(date(2025, 1, 10), 100, date(2026, 7, 31)), (date(2024, 12, 5), 50, date(2026, 6, 30)), (date(2024, 3, 1), 40, date(2025, 9, 30))], 70, date(2025, 6, 1))", "redeem([(date(2025, 1, 10), 100, date(2026, 7, 31)), (date(2024, 12, 5), 50, date(2026, 6, 30)), (date(2024, 3, 1), 40, date(2025, 9, 30))], 70, date(2025, 10, 1))", "redeem([(date(2025, 1, 10), 100, date(2026, 7, 31)), (date(2024, 12, 5), 50, date(2026, 6, 30)), (date(2024, 3, 1), 40, date(2025, 9, 30))], 40, date(2025, 6, 1))",
        "expiring([(date(2025, 1, 10), 100, date(2026, 7, 31)), (date(2024, 12, 5), 50, date(2026, 6, 30)), (date(2024, 3, 1), 40, date(2025, 9, 30))], date(2025, 8, 31))", "expiring([(date(2025, 1, 10), 100, date(2026, 7, 31)), (date(2024, 12, 5), 50, date(2026, 6, 30)), (date(2024, 3, 1), 40, date(2025, 9, 30))], date(2025, 8, 30))", "tier_for(999)", "tier_for(5000)",
        "purchase_points(9999, 'silver')", "purchase_points(10_000, 'platinum')",
        "earned_in_window([(date(2024, 6, 1), 500), (date(2024, 6, 2), 300), (date(2025, 6, 1), 200)], date(2025, 6, 1))",
        "earn_purchase([], [(date(2025, 5, 1), 1000)], 10_000, date(2025, 6, 1))[2]",
    ],
    probe_import="from datetime import date\nfrom pointsbank.lots import *\nfrom pointsbank.tiers import *",
)

# ======================================================================================================================
# billcycle: subscription billing dates with an anchor day, grace periods, plan changes and cancellation refunds
# ======================================================================================================================

BC_README = dd('''
    # billcycle

    Billing-cycle rules of a subscription service. Money is an `int` number of cents; dates are `datetime.date`.

    ## Dates (`billcycle/cycles.py`)

    * `add_months(d, n, anchor=None)`: the date `n` months after (or, for negative `n`, before) `d`. The day of the
      month is `anchor` when given and `d.day` otherwise, cut back to the last day of the target month: 31 January
      plus one month is 28 February (29 in a leap year).
    * `billing_dates(start, count, every=1)`: the first `count` billing dates, `start + i * every` months for
      `i = 0, 1, ...`, each computed from `start` (so a month-end anchor survives short months: 31 Jan, 28 Feb,
      31 Mar). `count == 0` gives `[]`.
    * `first_charge(signup, trial_days)`: the signup date plus the trial length (`trial_days < 0` is a `ValueError`).

    ## Account rules (`billcycle/account.py`)

    * `next_renewal(first, every, today)`: the first billing date (see `billing_dates`, every `every` months from
      `first`) that is on or after `today`; `first` itself when `today` is not after it.
    * `status(today, paid_through, grace_days=5)`: `"active"` while `today <= paid_through`, `"grace"` for the next
      `grace_days` days (the last of them included), otherwise `"lapsed"`.
    * `change_plan_charge(old_price, new_price, cycle_start, cycle_end, change_on)`: the cycle is `[cycle_start,
      cycle_end)`; `change_on` must lie inside it (`cycle_start <= change_on < cycle_end`, else `ValueError`). With
      `remaining = (cycle_end - change_on).days` and `total = (cycle_end - cycle_start).days` the unused part of the
      old plan is credited `old_price * remaining // total` (rounded down) and the rest of the cycle on the new plan
      costs `new_price * remaining / total` rounded **up**. The amount due is the charge minus the credit, never below
      `0`.
    * `cancel_refund(price, cycle_start, cycle_end, cancel_on)`: same cycle rules (`ValueError` outside the cycle).
      A cancellation at most 14 days after `cycle_start` (`(cancel_on - cycle_start).days <= 14`) refunds the full
      price. Later, the unused days are refunded: `price * remaining // total` (rounded down) minus an administration
      fee of 10% of that amount (rounded up), never below `0`.
''')

BC_CYCLES = dd('''
    import calendar
    from datetime import date, timedelta


    def add_months(d, n, anchor=None):
        day = d.day if anchor is None else anchor
        index = d.year * 12 + d.month - 1 + n
        year, month0 = divmod(index, 12)
        month = month0 + 1
        return date(year, month, min(day, calendar.monthrange(year, month)[1]))


    def billing_dates(start, count, every=1):
        return [add_months(start, i * every) for i in range(count)]


    def first_charge(signup, trial_days):
        if trial_days < 0:
            raise ValueError("trial length must not be negative")
        return signup + timedelta(days=trial_days)
''')

BC_ACCOUNT = dd('''
    from datetime import timedelta

    from .cycles import add_months

    FULL_REFUND_DAYS = 14
    ADMIN_FEE_PERCENT = 10


    def next_renewal(first, every, today):
        if today <= first:
            return first
        k = ((today.year - first.year) * 12 + today.month - first.month) // every
        while add_months(first, k * every) < today:
            k += 1
        while k > 0 and add_months(first, (k - 1) * every) >= today:
            k -= 1
        return add_months(first, k * every)


    def status(today, paid_through, grace_days=5):
        if today <= paid_through:
            return "active"
        if today <= paid_through + timedelta(days=grace_days):
            return "grace"
        return "lapsed"


    def _cycle(cycle_start, cycle_end, on):
        if not cycle_start <= on < cycle_end:
            raise ValueError("date outside the billing cycle")
        return (cycle_end - on).days, (cycle_end - cycle_start).days


    def change_plan_charge(old_price, new_price, cycle_start, cycle_end, change_on):
        remaining, total = _cycle(cycle_start, cycle_end, change_on)
        credit = old_price * remaining // total
        charge = -(-new_price * remaining // total)
        return max(0, charge - credit)


    def cancel_refund(price, cycle_start, cycle_end, cancel_on):
        remaining, total = _cycle(cycle_start, cycle_end, cancel_on)
        if (cancel_on - cycle_start).days <= FULL_REFUND_DAYS:
            return price
        unused = price * remaining // total
        fee = -(-unused * ADMIN_FEE_PERCENT // 100)
        return max(0, unused - fee)
''')

BC_VISIBLE = dd('''
    import unittest
    from datetime import date

    from billcycle.account import next_renewal, status
    from billcycle.cycles import add_months, billing_dates


    class BasicTests(unittest.TestCase):
        def test_clamp(self):
            self.assertEqual(add_months(date(2025, 1, 31), 1), date(2025, 2, 28))

        def test_dates(self):
            self.assertEqual(billing_dates(date(2025, 1, 15), 3), [date(2025, 1, 15), date(2025, 2, 15), date(2025, 3, 15)])

        def test_status(self):
            self.assertEqual(status(date(2025, 3, 10), date(2025, 3, 10)), "active")

        def test_next(self):
            self.assertEqual(next_renewal(date(2025, 1, 15), 1, date(2025, 2, 1)), date(2025, 2, 15))


    if __name__ == "__main__":
        unittest.main()
''')

BC_HIDDEN = dd('''
    import unittest
    from datetime import date

    from billcycle.account import cancel_refund, change_plan_charge, next_renewal, status
    from billcycle.cycles import add_months, billing_dates, first_charge

    D = date


    class AddMonths(unittest.TestCase):
        def test_clamping(self):
            self.assertEqual(add_months(D(2025, 1, 31), 1), D(2025, 2, 28))
            self.assertEqual(add_months(D(2024, 1, 31), 1), D(2024, 2, 29))
            self.assertEqual(add_months(D(2025, 1, 31), 2), D(2025, 3, 31))
            self.assertEqual(add_months(D(2025, 11, 30), 3), D(2026, 2, 28))
            self.assertEqual(add_months(D(2024, 2, 29), 12), D(2025, 2, 28))
            self.assertEqual(add_months(D(2024, 2, 29), 48), D(2028, 2, 29))

        def test_year_rollover(self):
            self.assertEqual(add_months(D(2025, 12, 15), 1), D(2026, 1, 15))
            self.assertEqual(add_months(D(2025, 1, 15), -2), D(2024, 11, 15))
            self.assertEqual(add_months(D(2025, 1, 15), 25), D(2027, 2, 15))
            self.assertEqual(add_months(D(2025, 1, 15), -13), D(2023, 12, 15))

        def test_zero_and_negative(self):
            self.assertEqual(add_months(D(2025, 3, 31), 0), D(2025, 3, 31))
            self.assertEqual(add_months(D(2025, 3, 31), -1), D(2025, 2, 28))
            self.assertEqual(add_months(D(2025, 5, 31), -3), D(2025, 2, 28))

        def test_anchor(self):
            self.assertEqual(add_months(D(2025, 2, 28), 1, anchor=31), D(2025, 3, 31))
            self.assertEqual(add_months(D(2025, 3, 31), 1, anchor=15), D(2025, 4, 15))
            self.assertEqual(add_months(D(2025, 1, 10), 1, anchor=31), D(2025, 2, 28))


    class BillingDates(unittest.TestCase):
        def test_month_end_anchor(self):
            got = billing_dates(D(2025, 1, 31), 5)
            self.assertEqual(got, [D(2025, 1, 31), D(2025, 2, 28), D(2025, 3, 31), D(2025, 4, 30), D(2025, 5, 31)])

        def test_every_n_months(self):
            self.assertEqual(billing_dates(D(2025, 1, 31), 3, every=3), [D(2025, 1, 31), D(2025, 4, 30), D(2025, 7, 31)])
            self.assertEqual(billing_dates(D(2025, 5, 15), 3, every=12), [D(2025, 5, 15), D(2026, 5, 15), D(2027, 5, 15)])

        def test_counts(self):
            self.assertEqual(billing_dates(D(2025, 1, 31), 0), [])
            self.assertEqual(billing_dates(D(2025, 1, 31), 1), [D(2025, 1, 31)])
            self.assertEqual(len(billing_dates(D(2025, 1, 31), 14)), 14)


    class FirstCharge(unittest.TestCase):
        def test_trial(self):
            self.assertEqual(first_charge(D(2025, 3, 1), 14), D(2025, 3, 15))
            self.assertEqual(first_charge(D(2025, 2, 20), 14), D(2025, 3, 6))
            self.assertEqual(first_charge(D(2025, 3, 1), 0), D(2025, 3, 1))

        def test_negative(self):
            with self.assertRaises(ValueError):
                first_charge(D(2025, 3, 1), -1)


    class NextRenewal(unittest.TestCase):
        FIRST = D(2025, 1, 31)

        def test_before_or_on_first(self):
            self.assertEqual(next_renewal(self.FIRST, 1, D(2024, 12, 1)), self.FIRST)
            self.assertEqual(next_renewal(self.FIRST, 1, self.FIRST), self.FIRST)

        def test_monthly(self):
            table = {D(2025, 2, 1): D(2025, 2, 28), D(2025, 2, 28): D(2025, 2, 28), D(2025, 3, 1): D(2025, 3, 31),
                     D(2025, 3, 31): D(2025, 3, 31), D(2025, 4, 1): D(2025, 4, 30), D(2025, 2, 27): D(2025, 2, 28),
                     D(2025, 12, 31): D(2025, 12, 31), D(2026, 1, 1): D(2026, 1, 31)}
            for today, want in table.items():
                self.assertEqual(next_renewal(self.FIRST, 1, today), want, today)

        def test_every_three_months(self):
            table = {D(2025, 2, 1): D(2025, 4, 30), D(2025, 4, 30): D(2025, 4, 30), D(2025, 5, 1): D(2025, 7, 31),
                     D(2025, 7, 31): D(2025, 7, 31), D(2025, 8, 1): D(2025, 10, 31), D(2026, 2, 1): D(2026, 4, 30)}
            for today, want in table.items():
                self.assertEqual(next_renewal(self.FIRST, 3, today), want, today)

        def test_far_in_the_future(self):
            self.assertEqual(next_renewal(self.FIRST, 1, D(2030, 6, 15)), D(2030, 6, 30))
            self.assertEqual(next_renewal(D(2025, 1, 15), 12, D(2030, 1, 16)), D(2031, 1, 15))
            self.assertEqual(next_renewal(D(2025, 1, 15), 12, D(2030, 1, 15)), D(2030, 1, 15))

        def test_result_is_a_billing_date_and_the_first_one_not_before_today(self):
            first = D(2025, 1, 29)
            dates = billing_dates(first, 40, every=2)
            day = D(2025, 1, 1)
            for _ in range(500):
                got = next_renewal(first, 2, day)
                self.assertIn(got, dates)
                self.assertGreaterEqual(got, day)
                self.assertEqual(got, min(d for d in dates if d >= day), day)
                day = D.fromordinal(day.toordinal() + 3)


    class Status(unittest.TestCase):
        def test_phases(self):
            paid = D(2025, 3, 10)
            table = {D(2025, 3, 1): "active", D(2025, 3, 10): "active", D(2025, 3, 11): "grace", D(2025, 3, 15): "grace",
                     D(2025, 3, 16): "lapsed", D(2025, 6, 1): "lapsed"}
            for today, want in table.items():
                self.assertEqual(status(today, paid), want, today)

        def test_custom_grace(self):
            paid = D(2025, 3, 10)
            self.assertEqual(status(D(2025, 3, 11), paid, grace_days=0), "lapsed")
            self.assertEqual(status(D(2025, 3, 11), paid, grace_days=1), "grace")
            self.assertEqual(status(D(2025, 3, 12), paid, grace_days=1), "lapsed")
            self.assertEqual(status(D(2025, 3, 31), paid, grace_days=21), "grace")
            self.assertEqual(status(D(2025, 4, 1), paid, grace_days=21), "lapsed")


    class PlanChange(unittest.TestCase):
        START, END = D(2025, 3, 1), D(2025, 3, 31)  # 30 days

        def test_upgrade(self):
            self.assertEqual(change_plan_charge(3000, 6000, self.START, self.END, D(2025, 3, 11)), 2000)
            self.assertEqual(change_plan_charge(3000, 6000, self.START, self.END, self.START), 3000)
            self.assertEqual(change_plan_charge(3000, 6000, self.START, self.END, D(2025, 3, 30)), 100)

        def test_rounding(self):
            # credit 1000 * 20 // 30 = 666 ; charge ceil(2000 * 20 / 30) = 1334
            self.assertEqual(change_plan_charge(1000, 2000, self.START, self.END, D(2025, 3, 11)), 668)
            self.assertEqual(change_plan_charge(1000, 1001, self.START, self.END, D(2025, 3, 11)), 2)   # credit 666, charge 668

        def test_downgrade_costs_nothing(self):
            self.assertEqual(change_plan_charge(6000, 3000, self.START, self.END, D(2025, 3, 11)), 0)
            self.assertEqual(change_plan_charge(3000, 3000, self.START, self.END, D(2025, 3, 11)), 0)

        def test_outside_the_cycle(self):
            for day in (D(2025, 2, 28), self.END, D(2025, 4, 2)):
                with self.assertRaises(ValueError):
                    change_plan_charge(3000, 6000, self.START, self.END, day)


    class Cancel(unittest.TestCase):
        START, END = D(2025, 3, 1), D(2025, 3, 31)

        def test_full_refund_window(self):
            self.assertEqual(cancel_refund(3000, self.START, self.END, self.START), 3000)
            self.assertEqual(cancel_refund(3000, self.START, self.END, D(2025, 3, 15)), 3000)

        def test_after_the_window(self):
            self.assertEqual(cancel_refund(3000, self.START, self.END, D(2025, 3, 16)), 1350)
            self.assertEqual(cancel_refund(3000, self.START, self.END, D(2025, 3, 30)), 90)   # unused 100, fee 10

        def test_rounding(self):
            self.assertEqual(cancel_refund(1001, self.START, self.END, D(2025, 3, 16)), 450)
            self.assertEqual(cancel_refund(1010, self.START, self.END, D(2025, 3, 16)), 454)

        def test_nothing_left(self):
            self.assertEqual(cancel_refund(5, self.START, self.END, D(2025, 3, 30)), 0)
            self.assertEqual(cancel_refund(0, self.START, self.END, D(2025, 3, 20)), 0)

        def test_outside_the_cycle(self):
            for day in (D(2025, 2, 28), self.END, D(2025, 4, 2)):
                with self.assertRaises(ValueError):
                    cancel_refund(3000, self.START, self.END, day)


    if __name__ == "__main__":
        unittest.main()
''')

BILLCYCLE = Lib(
    name="billcycle", lang="python", title="the subscription billing-cycle rules (`billcycle/`)",
    blurb="The subscription service schedules renewals and works out plan-change charges and cancellation refunds with billcycle.",
    files={"billcycle/__init__.py": "", "billcycle/cycles.py": BC_CYCLES, "billcycle/account.py": BC_ACCOUNT,
           "README.md": BC_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": BC_VISIBLE},
    hidden_tests={"tests/test_full.py": BC_HIDDEN},
    mutate=["billcycle/cycles.py", "billcycle/account.py"], difficulty=3, tags=["subscriptions", "dates", "proration"],
    probes=[
        "add_months(date(2025, 1, 31), 1)", "add_months(date(2025, 3, 31), -1)", "add_months(date(2025, 2, 28), 1, anchor=31)",
        "billing_dates(date(2025, 1, 31), 4)", "billing_dates(date(2025, 1, 31), 3, every=3)", "first_charge(date(2025, 2, 20), 14)",
        "next_renewal(date(2025, 1, 31), 1, date(2025, 3, 1))", "next_renewal(date(2025, 1, 31), 3, date(2025, 5, 1))",
        "status(date(2025, 3, 15), date(2025, 3, 10))", "status(date(2025, 3, 16), date(2025, 3, 10))",
        "change_plan_charge(1000, 2000, date(2025, 3, 1), date(2025, 3, 31), date(2025, 3, 11))",
        "change_plan_charge(6000, 3000, date(2025, 3, 1), date(2025, 3, 31), date(2025, 3, 11))",
        "cancel_refund(3000, date(2025, 3, 1), date(2025, 3, 31), date(2025, 3, 15))",
        "cancel_refund(3000, date(2025, 3, 1), date(2025, 3, 31), date(2025, 3, 16))",
        "cancel_refund(1010, date(2025, 3, 1), date(2025, 3, 31), date(2025, 3, 16))",
    ],
    probe_import="from datetime import date\nfrom billcycle.cycles import *\nfrom billcycle.account import *",
)

register_libs([FLATSHARE, HARBORFEES, POINTSBANK, BILLCYCLE], n=10)
