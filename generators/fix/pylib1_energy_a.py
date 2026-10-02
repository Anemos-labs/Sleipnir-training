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

POWERBILL = Lib(
    name="powerbill", lang="python", title="the electricity bill calculator (`powerbill/`)",
    blurb="The utility's billing system turns meter readings into a time-of-use electricity bill with powerbill.",
    files={"powerbill/__init__.py": "", "powerbill/readings.py": PB_READINGS, "powerbill/tariff.py": PB_TARIFF,
           "powerbill/bill.py": PB_BILL, "README.md": PB_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": PB_VISIBLE},
    hidden_tests={},
    mutate=["powerbill/readings.py", "powerbill/tariff.py", "powerbill/bill.py"], difficulty=4,
    tags=["energy", "tariff", "meter"],
    probes=[],
    probe_import="from powerbill.readings import *\nfrom powerbill.tariff import *\nfrom powerbill.bill import *",
)
