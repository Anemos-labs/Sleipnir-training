"""Python libraries, theme time/money/scheduling (batch energy-a): electricity bill from meter readings."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# powerbill: meter readings -> hourly use -> time-of-use charges, demand charge, standing charge, VAT
# ======================================================================================================================

PB_README = dd('''
    # powerbill

    Electricity bills for a small utility. Energy is an `int` number of watt-hours (Wh), money an `int` number of
    cents; instants are naive `datetime` objects (**seconds are ignored** everywhere).

    ## Readings (`powerbill/readings.py`)

    A reading is `(instant, wh)`: the cumulative register of the meter. The register shows `0 .. 99_999_999` Wh
    (`METER_MAX = 100_000_000`) and wraps around to 0.

    * `deltas(readings)`: the readings are sorted by time; every consecutive pair gives `(start, end, wh)`. A reading
      outside `0 <= wh < METER_MAX`, or two readings at exactly the same instant (before seconds are dropped:
      `t1 <= t0`), is a `ValueError`. When the register went down the meter has wrapped, which is only believable when
      the earlier value is above 90% of `METER_MAX` **and** the later one is below 10% of it; then the use is
      `later + METER_MAX - earlier`. Any other decrease is a `ValueError`.
    * `hourly(intervals)`: spreads every interval over the clock hours it touches, in proportion to the whole minutes
      spent in each hour (seconds dropped); each hour gets `wh * minutes // total_minutes`, and the Wh lost to rounding
      go to the **last** hour touched. Returns a dict `{hour_start: wh}` adding up over all intervals. An interval of
      zero minutes is skipped when its `wh` is 0 and a `ValueError` otherwise.

    ## Tariff (`powerbill/tariff.py`)

    * `classify(hour_start, holidays=())`: `"night"` for the hours starting at 23:00 to 06:00, else `"peak"` for the hours
      starting 16:00 to 19:00 on a weekday (Mon to Fri) that is not in `holidays`, else `"day"`.
    * `rate(cls, month)`: tenths of a cent per kWh: `night` 118, `day` 214, `peak` 389 in winter (November to March) and
      301 in the other months.

    ## Bill (`powerbill/bill.py`)

    * `energy_cost(buckets, holidays=())`: a dict with the keys `night`, `day`, `peak`: for each class the sum of
      `wh * rate` over its hours, divided by 10000 and rounded half up to a cent.
    * `demand_kw(buckets, holidays=())`: the largest peak-hour consumption, in kW rounded **up** (`ceil(wh / 1000)`); `0`
      without peak hours.
    * `make_bill(readings, period_start, period_end, holidays=())`: `period_end` must be after `period_start`
      (`ValueError` otherwise). Returns a dict with `energy` (the `energy_cost` dict), `standing` (41 cents for each day
      of `period_end - period_start`), `demand` (650 cents per demand kW), `subtotal` (all energy costs + standing +
      demand), `vat` (20% of the subtotal, half up) and `total`.
''')

PB_READINGS = dd('''
    from datetime import timedelta

    METER_MAX = 100_000_000


    def deltas(readings):
        for _, wh in readings:
            if not 0 <= wh < METER_MAX:
                raise ValueError("reading out of range")
        ordered = sorted(readings, key=lambda r: r[0])
        out = []
        for (t0, w0), (t1, w1) in zip(ordered, ordered[1:]):
            if t1 <= t0:
                raise ValueError("two readings at the same instant")
            if w1 >= w0:
                used = w1 - w0
            elif w0 > METER_MAX * 9 // 10 and w1 < METER_MAX // 10:
                used = w1 + METER_MAX - w0
            else:
                raise ValueError("the meter went backwards")
            out.append((t0, t1, used))
        return out


    def hourly(intervals):
        buckets = {}
        for start, end, wh in intervals:
            a = start.replace(second=0, microsecond=0)
            b = end.replace(second=0, microsecond=0)
            total = int((b - a).total_seconds() // 60)
            if total <= 0:
                if wh:
                    raise ValueError("energy used in no time")
                continue
            pieces = []
            cursor = a
            while cursor < b:
                hour_start = cursor.replace(minute=0)
                following = min(b, hour_start + timedelta(hours=1))
                pieces.append((hour_start, int((following - cursor).total_seconds() // 60)))
                cursor = following
            shares = [wh * minutes // total for _, minutes in pieces]
            shares[-1] += wh - sum(shares)
            for (hour_start, _), share in zip(pieces, shares):
                buckets[hour_start] = buckets.get(hour_start, 0) + share
        return buckets
''')

PB_TARIFF = dd('''
    WINTER = (11, 12, 1, 2, 3)
    RATES = {"night": 118, "day": 214}
    PEAK_WINTER = 389
    PEAK_SUMMER = 301


    def classify(hour_start, holidays=()):
        hour = hour_start.hour
        if hour >= 23 or hour < 7:
            return "night"
        if hour_start.weekday() < 5 and hour_start.date() not in holidays and 16 <= hour < 20:
            return "peak"
        return "day"


    def rate(cls, month):
        if cls == "peak":
            return PEAK_WINTER if month in WINTER else PEAK_SUMMER
        return RATES[cls]
''')

PB_BILL = dd('''
    from .readings import deltas, hourly
    from .tariff import classify, rate

    STANDING_PER_DAY = 41
    DEMAND_PER_KW = 650
    VAT_PERCENT = 20


    def _half_up(numerator, denominator):
        return (2 * numerator + denominator) // (2 * denominator)


    def energy_cost(buckets, holidays=()):
        weighted = {"night": 0, "day": 0, "peak": 0}
        for hour_start, wh in buckets.items():
            cls = classify(hour_start, holidays)
            weighted[cls] += wh * rate(cls, hour_start.month)
        return {cls: _half_up(total, 10_000) for cls, total in weighted.items()}


    def demand_kw(buckets, holidays=()):
        peak = [wh for hour_start, wh in buckets.items() if classify(hour_start, holidays) == "peak"]
        return -(-max(peak) // 1000) if peak else 0


    def make_bill(readings, period_start, period_end, holidays=()):
        if period_end <= period_start:
            raise ValueError("the billing period must end after it starts")
        buckets = hourly(deltas(readings))
        energy = energy_cost(buckets, holidays)
        standing = STANDING_PER_DAY * (period_end - period_start).days
        demand = DEMAND_PER_KW * demand_kw(buckets, holidays)
        subtotal = sum(energy.values()) + standing + demand
        vat = _half_up(subtotal * VAT_PERCENT, 100)
        return {"energy": energy, "standing": standing, "demand": demand, "subtotal": subtotal, "vat": vat,
                "total": subtotal + vat}
''')

PB_VISIBLE = dd('''
    import unittest
    from datetime import datetime

    from powerbill.readings import deltas
    from powerbill.tariff import classify, rate


    class BasicTests(unittest.TestCase):
        def test_deltas(self):
            got = deltas([(datetime(2025, 1, 6, 15), 50_000), (datetime(2025, 1, 6, 21), 56_000)])
            self.assertEqual(got, [(datetime(2025, 1, 6, 15), datetime(2025, 1, 6, 21), 6000)])

        def test_classify(self):
            self.assertEqual(classify(datetime(2025, 1, 6, 17)), "peak")

        def test_rates(self):
            self.assertEqual(rate("night", 7), 118)


    if __name__ == "__main__":
        unittest.main()
''')

PB_HIDDEN = dd('''
    import unittest
    from datetime import date, datetime

    from powerbill.bill import demand_kw, energy_cost, make_bill
    from powerbill.readings import METER_MAX, deltas, hourly
    from powerbill.tariff import classify, rate

    DT = datetime
    D = date
    READINGS = [(DT(2025, 1, 6, 15), 50_000), (DT(2025, 1, 6, 21), 56_000), (DT(2025, 1, 7, 3), 56_900)]


    class Deltas(unittest.TestCase):
        def test_consecutive_pairs(self):
            self.assertEqual(deltas(READINGS), [(DT(2025, 1, 6, 15), DT(2025, 1, 6, 21), 6000), (DT(2025, 1, 6, 21), DT(2025, 1, 7, 3), 900)])

        def test_unsorted_input(self):
            self.assertEqual(deltas([READINGS[2], READINGS[0], READINGS[1]]), deltas(READINGS))

        def test_fewer_than_two_readings(self):
            self.assertEqual(deltas([]), [])
            self.assertEqual(deltas([READINGS[0]]), [])

        def test_no_use(self):
            self.assertEqual(deltas([(DT(2025, 1, 1), 5), (DT(2025, 1, 2), 5)])[0][2], 0)

        def test_wrap_around(self):
            self.assertEqual(deltas([(DT(2025, 1, 1), 99_950_000), (DT(2025, 1, 2), 1000)])[0][2], 51_000)
            self.assertEqual(METER_MAX, 100_000_000)

        def test_wrap_thresholds(self):
            self.assertEqual(deltas([(DT(2025, 1, 1), 90_000_001), (DT(2025, 1, 2), 5)])[0][2], 10_000_004)
            self.assertEqual(deltas([(DT(2025, 1, 1), 95_000_000), (DT(2025, 1, 2), 9_999_999)])[0][2], 14_999_999)
            for before, after in ((90_000_000, 5), (95_000_000, 10_000_000), (5000, 4000), (50_000_000, 10)):
                with self.assertRaises(ValueError, msg=(before, after)):
                    deltas([(DT(2025, 1, 1), before), (DT(2025, 1, 2), after)])

        def test_out_of_range_readings(self):
            for bad in (-1, METER_MAX, METER_MAX + 5):
                with self.assertRaises(ValueError, msg=bad):
                    deltas([(DT(2025, 1, 1), 10), (DT(2025, 1, 2), bad)])
                with self.assertRaises(ValueError, msg=bad):
                    deltas([(DT(2025, 1, 1), bad), (DT(2025, 1, 2), 10)])
            deltas([(DT(2025, 1, 1), 0), (DT(2025, 1, 2), METER_MAX - 1)])

        def test_same_instant(self):
            with self.assertRaises(ValueError):
                deltas([(DT(2025, 1, 1, 10), 5), (DT(2025, 1, 1, 10), 6)])
            with self.assertRaises(ValueError):
                deltas([(DT(2025, 1, 1, 10), 5), (DT(2025, 1, 1, 11), 6), (DT(2025, 1, 1, 10), 7)])


    class Hourly(unittest.TestCase):
        def test_proportional(self):
            got = hourly([(DT(2025, 3, 3, 10, 30), DT(2025, 3, 3, 12, 30), 1000)])
            self.assertEqual(got, {DT(2025, 3, 3, 10): 250, DT(2025, 3, 3, 11): 500, DT(2025, 3, 3, 12): 250})

        def test_rounding_goes_to_the_last_hour(self):
            got = hourly([(DT(2025, 3, 3, 10, 30), DT(2025, 3, 3, 12, 30), 1001)])
            self.assertEqual(got, {DT(2025, 3, 3, 10): 250, DT(2025, 3, 3, 11): 500, DT(2025, 3, 3, 12): 251})
            got = hourly([(DT(2025, 3, 3, 10), DT(2025, 3, 3, 13), 100)])
            self.assertEqual(got, {DT(2025, 3, 3, 10): 33, DT(2025, 3, 3, 11): 33, DT(2025, 3, 3, 12): 34})

        def test_ending_on_the_hour_does_not_touch_the_next_hour(self):
            self.assertEqual(hourly([(DT(2025, 3, 3, 10), DT(2025, 3, 3, 11), 100)]), {DT(2025, 3, 3, 10): 100})

        def test_seconds_are_dropped(self):
            self.assertEqual(hourly([(DT(2025, 3, 3, 10, 10, 59), DT(2025, 3, 3, 10, 40, 30), 100)]), {DT(2025, 3, 3, 10): 100})
            got = hourly([(DT(2025, 3, 3, 10, 59, 59), DT(2025, 3, 3, 11, 59, 59), 100)])
            self.assertEqual(got, {DT(2025, 3, 3, 10): 1, DT(2025, 3, 3, 11): 99})   # 1 and 59 minutes: 1 + 98, one Wh left for the last hour

        def test_across_midnight(self):
            got = hourly([(DT(2025, 3, 3, 23, 30), DT(2025, 3, 4, 0, 30), 10)])
            self.assertEqual(got, {DT(2025, 3, 3, 23): 5, DT(2025, 3, 4, 0): 5})

        def test_intervals_add_up_in_the_same_hour(self):
            got = hourly([(DT(2025, 3, 3, 10, 0), DT(2025, 3, 3, 10, 30), 100), (DT(2025, 3, 3, 10, 30), DT(2025, 3, 3, 11, 30), 60)])
            self.assertEqual(got, {DT(2025, 3, 3, 10): 130, DT(2025, 3, 3, 11): 30})

        def test_zero_length_intervals(self):
            self.assertEqual(hourly([(DT(2025, 3, 3, 10), DT(2025, 3, 3, 10), 0)]), {})
            self.assertEqual(hourly([(DT(2025, 3, 3, 10, 0, 0), DT(2025, 3, 3, 10, 0, 30), 0)]), {})
            with self.assertRaises(ValueError):
                hourly([(DT(2025, 3, 3, 10), DT(2025, 3, 3, 10), 5)])
            with self.assertRaises(ValueError):
                hourly([(DT(2025, 3, 3, 10, 0, 0), DT(2025, 3, 3, 10, 0, 30), 5)])

        def test_total_is_preserved(self):
            intervals = deltas(READINGS)
            self.assertEqual(sum(hourly(intervals).values()), 6900)

        def test_hours_of_the_example(self):
            got = hourly(deltas(READINGS))
            self.assertEqual([got[DT(2025, 1, 6, h)] for h in range(15, 21)], [1000] * 6)
            self.assertEqual([got[DT(2025, 1, 6, h)] for h in (21, 22, 23)], [150, 150, 150])
            self.assertEqual([got[DT(2025, 1, 7, h)] for h in (0, 1, 2)], [150, 150, 150])


    class Tariff(unittest.TestCase):
        def test_weekday_classes(self):
            hours = {0: "night", 6: "night", 7: "day", 15: "day", 16: "peak", 19: "peak", 20: "day", 22: "day", 23: "night"}
            for hour, cls in hours.items():
                self.assertEqual(classify(DT(2025, 1, 6, hour), ()), cls, hour)

        def test_weekend_has_no_peak(self):
            self.assertEqual(classify(DT(2025, 1, 11, 17)), "day")
            self.assertEqual(classify(DT(2025, 1, 12, 16)), "day")
            self.assertEqual(classify(DT(2025, 1, 11, 23)), "night")

        def test_holidays_have_no_peak(self):
            self.assertEqual(classify(DT(2025, 1, 6, 17), {D(2025, 1, 6)}), "day")
            self.assertEqual(classify(DT(2025, 1, 7, 17), {D(2025, 1, 6)}), "peak")
            self.assertEqual(classify(DT(2025, 1, 6, 23), {D(2025, 1, 6)}), "night")

        def test_every_weekday_has_a_peak(self):
            for day in range(6, 11):
                self.assertEqual(classify(DT(2025, 1, day, 18)), "peak", day)

        def test_rates(self):
            self.assertEqual([rate("night", m) for m in range(1, 13)], [118] * 12)
            self.assertEqual([rate("day", m) for m in range(1, 13)], [214] * 12)
            self.assertEqual([rate("peak", m) for m in range(1, 13)], [389, 389, 389, 301, 301, 301, 301, 301, 301, 301, 389, 389])


    class Costs(unittest.TestCase):
        def test_example(self):
            buckets = hourly(deltas(READINGS))
            self.assertEqual(energy_cost(buckets), {"night": 7, "day": 49, "peak": 156})
            self.assertEqual(demand_kw(buckets), 1)

        def test_holiday_moves_peak_to_day(self):
            buckets = hourly(deltas(READINGS))
            self.assertEqual(energy_cost(buckets, {D(2025, 1, 6)}), {"night": 7, "day": 135, "peak": 0})
            self.assertEqual(demand_kw(buckets, {D(2025, 1, 6)}), 0)

        def test_half_up_per_class(self):
            self.assertEqual(energy_cost({DT(2025, 1, 6, 2): 2500}), {"night": 30, "day": 0, "peak": 0})
            self.assertEqual(energy_cost({DT(2025, 1, 6, 12): 2500}), {"night": 0, "day": 54, "peak": 0})
            self.assertEqual(energy_cost({DT(2025, 1, 6, 17): 5000}), {"night": 0, "day": 0, "peak": 195})
            self.assertEqual(energy_cost({DT(2025, 7, 7, 17): 5000}), {"night": 0, "day": 0, "peak": 151})
            self.assertEqual(energy_cost({DT(2025, 1, 6, 17): 1}), {"night": 0, "day": 0, "peak": 0})

        def test_classes_are_rounded_after_summing(self):
            buckets = {DT(2025, 1, 6, 12): 25, DT(2025, 1, 6, 13): 25, DT(2025, 1, 6, 14): 25, DT(2025, 1, 6, 15): 25}
            self.assertEqual(energy_cost(buckets)["day"], 2)    # 100 Wh * 214 / 10000 = 2.14, not 4 times 0

        def test_rate_follows_the_month_of_each_hour(self):
            buckets = {DT(2025, 3, 31, 17): 1000, DT(2025, 4, 1, 17): 1000}
            self.assertEqual(energy_cost(buckets)["peak"], 69)
            self.assertEqual(energy_cost({DT(2025, 10, 31, 17): 1000, DT(2025, 11, 3, 17): 1000})["peak"], 69)

        def test_demand_rounds_up(self):
            self.assertEqual(demand_kw({DT(2025, 1, 6, 17): 1001, DT(2025, 1, 6, 18): 500}), 2)
            self.assertEqual(demand_kw({DT(2025, 1, 6, 17): 1000}), 1)
            self.assertEqual(demand_kw({DT(2025, 1, 6, 17): 1}), 1)
            self.assertEqual(demand_kw({DT(2025, 1, 6, 17): 0}), 0)

        def test_demand_only_counts_peak_hours(self):
            self.assertEqual(demand_kw({DT(2025, 1, 6, 12): 9999}), 0)
            self.assertEqual(demand_kw({DT(2025, 1, 6, 12): 9999, DT(2025, 1, 6, 16): 3000}), 3)
            self.assertEqual(demand_kw({}), 0)

        def test_demand_is_the_maximum_not_the_sum(self):
            self.assertEqual(demand_kw({DT(2025, 1, 6, 16): 2000, DT(2025, 1, 6, 17): 2500, DT(2025, 1, 7, 18): 1500}), 3)


    class Bill(unittest.TestCase):
        def test_winter_bill(self):
            got = make_bill(READINGS, D(2025, 1, 6), D(2025, 1, 8))
            self.assertEqual(got, {"energy": {"night": 7, "day": 49, "peak": 156}, "standing": 82, "demand": 650, "subtotal": 944,
                                   "vat": 189, "total": 1133})

        def test_summer_bill(self):
            readings = [(DT(2025, 7, 7, 15), 50_000), (DT(2025, 7, 7, 21), 56_000), (DT(2025, 7, 8, 3), 56_900)]
            got = make_bill(readings, D(2025, 7, 7), D(2025, 7, 9))
            self.assertEqual(got["energy"], {"night": 7, "day": 49, "peak": 120})
            self.assertEqual((got["subtotal"], got["vat"], got["total"]), (908, 182, 1090))

        def test_holiday(self):
            got = make_bill(READINGS, D(2025, 1, 6), D(2025, 1, 8), holidays={D(2025, 1, 6)})
            self.assertEqual(got["energy"], {"night": 7, "day": 135, "peak": 0})
            self.assertEqual((got["demand"], got["subtotal"], got["vat"], got["total"]), (0, 224, 45, 269))

        def test_standing_charge_counts_days(self):
            got = make_bill(READINGS, D(2025, 1, 6), D(2025, 2, 6))
            self.assertEqual(got["standing"], 41 * 31)
            got = make_bill(READINGS, D(2025, 1, 6), D(2025, 1, 7))
            self.assertEqual(got["standing"], 41)

        def test_no_readings(self):
            got = make_bill([], D(2025, 1, 1), D(2025, 1, 11))
            self.assertEqual(got, {"energy": {"night": 0, "day": 0, "peak": 0}, "standing": 410, "demand": 0, "subtotal": 410,
                                   "vat": 82, "total": 492})

        def test_vat_rounds_half_up(self):
            got = make_bill([], D(2025, 1, 1), D(2025, 1, 2))
            self.assertEqual((got["subtotal"], got["vat"], got["total"]), (41, 8, 49))
            got = make_bill([], D(2025, 1, 1), D(2025, 1, 4))
            self.assertEqual((got["subtotal"], got["vat"], got["total"]), (123, 25, 148))

        def test_period_must_be_positive(self):
            for end in (D(2025, 1, 6), D(2025, 1, 5)):
                with self.assertRaises(ValueError):
                    make_bill(READINGS, D(2025, 1, 6), end)

        def test_reading_errors_propagate(self):
            with self.assertRaises(ValueError):
                make_bill([(DT(2025, 1, 6, 15), 500), (DT(2025, 1, 6, 16), 400)], D(2025, 1, 6), D(2025, 1, 7))


    if __name__ == "__main__":
        unittest.main()
''')

POWERBILL = Lib(
    name="powerbill", lang="python", title="the electricity bill calculator (`powerbill/`)",
    blurb="The utility's billing system turns meter readings into a time-of-use electricity bill with powerbill.",
    files={"powerbill/__init__.py": "", "powerbill/readings.py": PB_READINGS, "powerbill/tariff.py": PB_TARIFF,
           "powerbill/bill.py": PB_BILL, "README.md": PB_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": PB_VISIBLE},
    hidden_tests={"tests/test_full.py": PB_HIDDEN},
    mutate=["powerbill/readings.py", "powerbill/tariff.py", "powerbill/bill.py"], difficulty=4,
    tags=["energy", "tariff", "meter"],
    probes=[
        "deltas([(datetime(2025, 1, 1), 99_950_000), (datetime(2025, 1, 2), 1000)])[0][2]",
        "deltas([(datetime(2025, 1, 1), 90_000_000), (datetime(2025, 1, 2), 5)])",
        "hourly([(datetime(2025, 3, 3, 10, 30), datetime(2025, 3, 3, 12, 30), 1001)])",
        "hourly([(datetime(2025, 3, 3, 10), datetime(2025, 3, 3, 11), 100)])",
        "hourly([(datetime(2025, 3, 3, 10), datetime(2025, 3, 3, 13), 100)])",
        "classify(datetime(2025, 1, 6, 16))", "classify(datetime(2025, 1, 6, 20))", "classify(datetime(2025, 1, 11, 17))",
        "classify(datetime(2025, 1, 6, 17), {date(2025, 1, 6)})", "rate('peak', 3)", "rate('peak', 4)", "rate('peak', 11)",
        "energy_cost({datetime(2025, 1, 6, 12): 2500})", "energy_cost({datetime(2025, 1, 6, 17): 5000})",
        "energy_cost({datetime(2025, 3, 31, 17): 1000, datetime(2025, 4, 1, 17): 1000})",
        "demand_kw({datetime(2025, 1, 6, 17): 1001, datetime(2025, 1, 6, 18): 500})",
        "make_bill([(datetime(2025, 1, 6, 15), 50_000), (datetime(2025, 1, 6, 21), 56_000), (datetime(2025, 1, 7, 3), 56_900)], date(2025, 1, 6), date(2025, 1, 8))", "make_bill([(datetime(2025, 1, 6, 15), 50_000), (datetime(2025, 1, 6, 21), 56_000), (datetime(2025, 1, 7, 3), 56_900)], date(2025, 1, 6), date(2025, 1, 8), holidays={date(2025, 1, 6)})",
    ],
    probe_import="from datetime import date, datetime\nfrom powerbill.readings import *\nfrom powerbill.tariff import *\nfrom powerbill.bill import *",
)

# ======================================================================================================================
# loanplan: day-count conventions, level payment and an amortisation schedule
# ======================================================================================================================

LP_README = dd('''
    # loanplan

    Loan schedules for a small lender. Money is an `int` number of cents; dates are `datetime.date`; rates are annual,
    in basis points (1 bp = 0.01%).

    ## Day counts (`loanplan/daycount.py`)

    `day_count(start, end, convention)` returns `(days, basis)`; `end < start` is a `ValueError`, and so is an unknown
    convention.

    * `"act365"`: the real number of days, basis 365. `"act360"`: the real number of days, basis 360.
    * `"30e360"` (European): both day numbers are capped at 30, then
      `days = 360 * dy + 30 * dm + (d2 - d1)`; basis 360.
    * `"30u360"` (US bond basis): like `30e360` but with the day numbers adjusted in this order: if both dates are the
      last day of February, `d2` becomes 30; if `start` is the last day of February, `d1` becomes 30; if `d2` is 31 and
      `d1` is 30 or 31, `d2` becomes 30; if `d1` is 31 it becomes 30. A `d2` of 31 stays 31 when `d1` is below 30.

    ## Payment (`loanplan/annuity.py`)

    `level_payment(principal, rate_bp, months)`: the equal monthly payment that repays `principal` over `months` months
    at the monthly rate `rate_bp / 10000 / 12`: `P * r / (1 - (1 + r) ** -months)`, computed exactly (use
    `fractions.Fraction`) and rounded half up to a cent; with a rate of 0 it is `principal / months` rounded half up.
    `principal <= 0`, `months < 1` or a negative rate is a `ValueError`. `half_up(fraction)` rounds a `Fraction`
    (non-negative) half up to an `int`.

    ## Schedule (`loanplan/schedule.py`)

    `amortize(principal, rate_bp, months, start, convention="30e360", extra=None)` returns a list of rows
    `(due, payment, interest, principal_part, balance)`.

    * The due dates are `start` plus 1, 2, ... months with the day of month of `start`, cut back to the end of short
      months (31 Jan, then 28 Feb, 31 Mar from the same start).
    * The interest of a period is `balance * rate_bp / 10000 * days / basis`, where `(days, basis)` is the day count
      from the previous due date (the start for the first period) to this due date; exact arithmetic, rounded half up
      to a cent.
    * The payment of period `k` is `level_payment + extra.get(k, 0)` (`extra` maps period numbers to extra cents; keys that match no period are ignored), but
      never more than the balance plus the interest; the last period (`k == months`) always pays everything that is
      owed. `principal_part = payment - interest`; the new balance is the old one minus the principal part. When the
      balance reaches 0 early the schedule ends there.

    `summary(rows)`: a dict with `periods` (number of rows), `total_paid`, `total_interest` and `last_due` (`None` for an
    empty list).
''')

LP_DAYCOUNT = dd('''
    import calendar


    def _last_day_of_february(d):
        return d.month == 2 and d.day == calendar.monthrange(d.year, 2)[1]


    def day_count(start, end, convention):
        if end < start:
            raise ValueError("end is before start")
        if convention == "act365":
            return (end - start).days, 365
        if convention == "act360":
            return (end - start).days, 360
        if convention in ("30e360", "30u360"):
            d1, d2 = start.day, end.day
            if convention == "30e360":
                d1, d2 = min(d1, 30), min(d2, 30)
            else:
                if _last_day_of_february(start) and _last_day_of_february(end):
                    d2 = 30
                if _last_day_of_february(start):
                    d1 = 30
                if d2 == 31 and d1 >= 30:
                    d2 = 30
                if d1 == 31:
                    d1 = 30
            days = 360 * (end.year - start.year) + 30 * (end.month - start.month) + (d2 - d1)
            return days, 360
        raise ValueError(f"unknown convention {convention!r}")
''')

LP_ANNUITY = dd('''
    from fractions import Fraction


    def half_up(x):
        return (2 * x.numerator + x.denominator) // (2 * x.denominator)


    def level_payment(principal, rate_bp, months):
        if principal <= 0 or months < 1 or rate_bp < 0:
            raise ValueError("principal and months must be positive and the rate not negative")
        if rate_bp == 0:
            return half_up(Fraction(principal, months))
        r = Fraction(rate_bp, 10_000 * 12)
        return half_up(principal * r / (1 - (1 + r) ** -months))
''')

LP_SCHEDULE = dd('''
    import calendar
    from datetime import date
    from fractions import Fraction

    from .annuity import half_up, level_payment
    from .daycount import day_count


    def _months_after(start, k):
        index = start.year * 12 + start.month - 1 + k
        year, month0 = divmod(index, 12)
        month = month0 + 1
        return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


    def amortize(principal, rate_bp, months, start, convention="30e360", extra=None):
        extra = extra or {}
        level = level_payment(principal, rate_bp, months)
        balance = principal
        previous = start
        rows = []
        for k in range(1, months + 1):
            due = _months_after(start, k)
            days, basis = day_count(previous, due, convention)
            interest = half_up(Fraction(balance * rate_bp * days, 10_000 * basis))
            owed = balance + interest
            payment = owed if k == months else min(level + extra.get(k, 0), owed)
            balance -= payment - interest
            rows.append((due, payment, interest, payment - interest, balance))
            previous = due
            if balance == 0:
                break
        return rows


    def summary(rows):
        return {
            "periods": len(rows),
            "total_paid": sum(r[1] for r in rows),
            "total_interest": sum(r[2] for r in rows),
            "last_due": rows[-1][0] if rows else None,
        }
''')

LP_VISIBLE = dd('''
    import unittest
    from datetime import date

    from loanplan.annuity import level_payment
    from loanplan.daycount import day_count


    class BasicTests(unittest.TestCase):
        def test_act365(self):
            self.assertEqual(day_count(date(2025, 1, 1), date(2025, 2, 1), "act365"), (31, 365))

        def test_30e360(self):
            self.assertEqual(day_count(date(2025, 1, 15), date(2025, 3, 15), "30e360"), (60, 360))

        def test_zero_rate_payment(self):
            self.assertEqual(level_payment(120_000, 0, 12), 10_000)


    if __name__ == "__main__":
        unittest.main()
''')

LP_HIDDEN = dd('''
    import unittest
    from datetime import date
    from fractions import Fraction

    from loanplan.annuity import half_up, level_payment
    from loanplan.daycount import day_count
    from loanplan.schedule import amortize, summary

    D = date
    CONVENTIONS = ("act365", "act360", "30e360", "30u360")


    class DayCount(unittest.TestCase):
        def test_table(self):
            table = [((2025, 1, 1), (2025, 2, 1), [31, 31, 30, 30]),
                     ((2025, 1, 31), (2025, 3, 31), [59, 59, 60, 60]),
                     ((2025, 2, 28), (2025, 3, 31), [31, 31, 32, 30]),
                     ((2024, 2, 29), (2024, 3, 31), [31, 31, 31, 30]),
                     ((2025, 1, 30), (2025, 3, 31), [60, 60, 60, 60]),
                     ((2025, 1, 29), (2025, 3, 31), [61, 61, 61, 62]),
                     ((2025, 2, 28), (2025, 2, 28), [0, 0, 0, 0]),
                     ((2025, 2, 28), (2026, 2, 28), [365, 365, 360, 360]),
                     ((2024, 2, 29), (2025, 2, 28), [365, 365, 359, 360]),
                     ((2025, 1, 31), (2025, 2, 28), [28, 28, 28, 28]),
                     ((2025, 5, 31), (2025, 6, 30), [30, 30, 30, 30]),
                     ((2025, 12, 15), (2026, 1, 15), [31, 31, 30, 30]),
                     ((2025, 3, 31), (2025, 4, 30), [30, 30, 30, 30])]
            for a, b, want in table:
                got = [day_count(D(*a), D(*b), c)[0] for c in CONVENTIONS]
                self.assertEqual(got, want, (a, b))

        def test_basis(self):
            for convention, basis in zip(CONVENTIONS, (365, 360, 360, 360)):
                self.assertEqual(day_count(D(2025, 1, 1), D(2025, 6, 1), convention)[1], basis)

        def test_us_rules_in_isolation(self):
            self.assertEqual(day_count(D(2025, 2, 28), D(2025, 3, 31), "30u360"), (30, 360))
            self.assertEqual(day_count(D(2025, 2, 27), D(2025, 3, 31), "30u360"), (34, 360))
            self.assertEqual(day_count(D(2025, 1, 30), D(2025, 1, 31), "30u360"), (0, 360))
            self.assertEqual(day_count(D(2025, 1, 31), D(2025, 1, 31), "30u360"), (0, 360))
            self.assertEqual(day_count(D(2025, 1, 29), D(2025, 1, 31), "30u360"), (2, 360))
            self.assertEqual(day_count(D(2024, 2, 28), D(2024, 3, 31), "30u360"), (33, 360))
            self.assertEqual(day_count(D(2024, 2, 29), D(2024, 3, 31), "30u360"), (30, 360))

        def test_european_rules_in_isolation(self):
            self.assertEqual(day_count(D(2025, 2, 28), D(2025, 3, 31), "30e360"), (32, 360))
            self.assertEqual(day_count(D(2025, 1, 29), D(2025, 1, 31), "30e360"), (1, 360))
            self.assertEqual(day_count(D(2025, 1, 31), D(2025, 1, 31), "30e360"), (0, 360))
            self.assertEqual(day_count(D(2025, 3, 31), D(2025, 4, 1), "30e360"), (1, 360))

        def test_errors(self):
            for convention in CONVENTIONS:
                with self.assertRaises(ValueError):
                    day_count(D(2025, 3, 2), D(2025, 3, 1), convention)
            for convention in ("", "act/act", "ACT365", "30/360"):
                with self.assertRaises(ValueError):
                    day_count(D(2025, 3, 1), D(2025, 3, 2), convention)


    class Annuity(unittest.TestCase):
        def test_half_up(self):
            table = [(Fraction(5, 2), 3), (Fraction(7, 2), 4), (Fraction(1, 3), 0), (Fraction(2, 3), 1), (Fraction(0, 1), 0),
                     (Fraction(1, 2), 1), (Fraction(49, 100), 0), (Fraction(10, 1), 10)]
            for x, want in table:
                self.assertEqual(half_up(x), want, x)

        def test_payments(self):
            self.assertEqual(level_payment(100_000, 1200, 12), 8885)
            self.assertEqual(level_payment(100_000, 1200, 3), 34_002)
            self.assertEqual(level_payment(100_000, 600, 1), 100_500)
            self.assertEqual(level_payment(1_000_000, 500, 360), 5368)

        def test_zero_rate(self):
            self.assertEqual(level_payment(120_000, 0, 12), 10_000)
            self.assertEqual(level_payment(50_000, 0, 7), 7143)
            self.assertEqual(level_payment(5, 0, 2), 3)
            self.assertEqual(level_payment(4, 0, 8), 1)
            self.assertEqual(level_payment(1000, 0, 1), 1000)

        def test_errors(self):
            for args in ((0, 500, 12), (-5, 500, 12), (1000, 500, 0), (1000, 500, -1), (1000, -1, 12), (1000, -1, 0)):
                with self.assertRaises(ValueError, msg=args):
                    level_payment(*args)


    class Schedule(unittest.TestCase):
        def test_three_month_loan(self):
            rows = amortize(100_000, 1200, 3, D(2025, 1, 31))
            self.assertEqual(rows, [(D(2025, 2, 28), 34_002, 933, 33_069, 66_931),
                                    (D(2025, 3, 31), 34_002, 714, 33_288, 33_643),
                                    (D(2025, 4, 30), 33_979, 336, 33_643, 0)])

        def test_other_convention(self):
            rows = amortize(100_000, 1200, 3, D(2025, 1, 31), convention="act365")
            self.assertEqual(rows, [(D(2025, 2, 28), 34_002, 921, 33_081, 66_919),
                                    (D(2025, 3, 31), 34_002, 682, 33_320, 33_599),
                                    (D(2025, 4, 30), 33_930, 331, 33_599, 0)])

        def test_zero_rate(self):
            rows = amortize(120_000, 0, 12, D(2025, 1, 15))
            self.assertEqual(len(rows), 12)
            self.assertEqual(rows[0], (D(2025, 2, 15), 10_000, 0, 10_000, 110_000))
            self.assertEqual(rows[-1], (D(2026, 1, 15), 10_000, 0, 10_000, 0))

        def test_single_period(self):
            rows = amortize(100_000, 600, 1, D(2025, 1, 1))
            self.assertEqual(rows, [(D(2025, 2, 1), 100_500, 500, 100_000, 0)])

        def test_due_dates_follow_the_start_day(self):
            rows = amortize(100_000, 1200, 6, D(2025, 1, 31))
            self.assertEqual([r[0] for r in rows], [D(2025, 2, 28), D(2025, 3, 31), D(2025, 4, 30), D(2025, 5, 31), D(2025, 6, 30), D(2025, 7, 31)])
            rows = amortize(100_000, 1200, 2, D(2024, 1, 31))
            self.assertEqual([r[0] for r in rows], [D(2024, 2, 29), D(2024, 3, 31)])
            rows = amortize(100_000, 1200, 3, D(2025, 12, 15))
            self.assertEqual([r[0] for r in rows], [D(2026, 1, 15), D(2026, 2, 15), D(2026, 3, 15)])

        def test_extra_payment(self):
            rows = amortize(100_000, 1200, 12, D(2025, 1, 1), extra={2: 50_000})
            self.assertEqual(rows, [(D(2025, 2, 1), 8885, 1000, 7885, 92_115),
                                    (D(2025, 3, 1), 58_885, 921, 57_964, 34_151),
                                    (D(2025, 4, 1), 8885, 342, 8543, 25_608),
                                    (D(2025, 5, 1), 8885, 256, 8629, 16_979),
                                    (D(2025, 6, 1), 8885, 170, 8715, 8264),
                                    (D(2025, 7, 1), 8347, 83, 8264, 0)])

        def test_extra_larger_than_the_debt(self):
            rows = amortize(100_000, 1200, 12, D(2025, 1, 1), extra={1: 500_000})
            self.assertEqual(rows, [(D(2025, 2, 1), 101_000, 1000, 100_000, 0)])

        def test_extra_for_unknown_periods_is_ignored(self):
            base = amortize(100_000, 1200, 6, D(2025, 1, 1))
            self.assertEqual(amortize(100_000, 1200, 6, D(2025, 1, 1), extra={0: 5000, 7: 5000, 99: 1}), base)
            self.assertEqual(amortize(100_000, 1200, 6, D(2025, 1, 1), extra={}), base)

        def test_balance_and_parts_add_up(self):
            for principal, rate, months, convention in ((250_000, 750, 24, "act365"), (99_999, 1999, 18, "30u360"), (1_000_000, 500, 36, "act360"),
                                                        (12_345, 1, 10, "30e360")):
                rows = amortize(principal, rate, months, D(2025, 3, 31), convention=convention)
                self.assertEqual(len(rows), months)
                self.assertEqual(rows[-1][4], 0)
                self.assertEqual(sum(r[3] for r in rows), principal)
                balance = principal
                for due, payment, interest, part, left in rows:
                    self.assertEqual(payment, interest + part)
                    self.assertEqual(left, balance - part)
                    balance = left
                level = level_payment(principal, rate, months)
                self.assertTrue(all(r[1] == level for r in rows[:-1]))
                dues = [r[0] for r in rows]
                self.assertEqual(dues, sorted(dues))

        def test_interest_follows_the_day_count(self):
            rows = amortize(250_000, 750, 12, D(2025, 3, 31), convention="act365")
            balance = 250_000
            previous = D(2025, 3, 31)
            for due, payment, interest, part, left in rows:
                exact = Fraction(balance * 750 * (due - previous).days, 10_000 * 365)
                self.assertEqual(interest, half_up(exact), due)
                balance, previous = left, due

        def test_errors(self):
            with self.assertRaises(ValueError):
                amortize(0, 500, 12, D(2025, 1, 1))
            with self.assertRaises(ValueError):
                amortize(1000, 500, 0, D(2025, 1, 1))
            with self.assertRaises(ValueError):
                amortize(1000, 500, 3, D(2025, 1, 1), convention="nope")


    class Summary(unittest.TestCase):
        def test_values(self):
            rows = amortize(100_000, 1200, 3, D(2025, 1, 31))
            self.assertEqual(summary(rows), {"periods": 3, "total_paid": 101_983, "total_interest": 1983, "last_due": D(2025, 4, 30)})

        def test_empty(self):
            self.assertEqual(summary([]), {"periods": 0, "total_paid": 0, "total_interest": 0, "last_due": None})

        def test_early_payoff(self):
            rows = amortize(100_000, 1200, 12, D(2025, 1, 1), extra={2: 50_000})
            got = summary(rows)
            self.assertEqual(got["periods"], 6)
            self.assertEqual(got["last_due"], D(2025, 7, 1))
            self.assertEqual(got["total_interest"], 1000 + 921 + 342 + 256 + 170 + 83)
            self.assertEqual(got["total_paid"], 100_000 + got["total_interest"])


    if __name__ == "__main__":
        unittest.main()
''')

LOANPLAN = Lib(
    name="loanplan", lang="python", title="the loan schedule calculator (`loanplan/`)",
    blurb="The lender's quoting tool builds amortisation schedules, with several day-count conventions, using loanplan.",
    files={"loanplan/__init__.py": "", "loanplan/daycount.py": LP_DAYCOUNT, "loanplan/annuity.py": LP_ANNUITY,
           "loanplan/schedule.py": LP_SCHEDULE, "README.md": LP_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": LP_VISIBLE},
    hidden_tests={"tests/test_full.py": LP_HIDDEN},
    mutate=["loanplan/daycount.py", "loanplan/annuity.py", "loanplan/schedule.py"], difficulty=4,
    tags=["loans", "day-count", "interest"],
    probes=[
        "day_count(date(2025, 2, 28), date(2025, 3, 31), '30e360')", "day_count(date(2025, 2, 28), date(2025, 3, 31), '30u360')",
        "day_count(date(2025, 1, 29), date(2025, 3, 31), '30u360')", "day_count(date(2025, 1, 29), date(2025, 3, 31), '30e360')",
        "day_count(date(2024, 2, 29), date(2025, 2, 28), '30e360')", "day_count(date(2025, 1, 1), date(2025, 2, 1), 'act360')",
        "level_payment(100_000, 1200, 12)", "level_payment(50_000, 0, 7)", "level_payment(5, 0, 2)", "level_payment(1_000_000, 500, 360)",
        "amortize(100_000, 1200, 3, date(2025, 1, 31))", "amortize(100_000, 1200, 3, date(2025, 1, 31), convention='act365')",
        "amortize(100_000, 1200, 12, date(2025, 1, 1), extra={2: 50_000})[-1]", "amortize(100_000, 1200, 12, date(2025, 1, 1), extra={1: 500_000})",
        "summary(amortize(100_000, 1200, 3, date(2025, 1, 31)))",
    ],
    probe_import="from datetime import date\nfrom loanplan.daycount import *\nfrom loanplan.annuity import *\nfrom loanplan.schedule import *",
)

register_libs([POWERBILL, LOANPLAN], n=10)
