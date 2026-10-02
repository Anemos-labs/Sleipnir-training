"""Bank modules, part A: tidal, ferryfare, stampduty, samplelabel, initiative, chapters."""
from fx import dd

from ._bank import Bug, Mod, add

# ---------------------------------------------------------------------------------------------------------- tidal
add(Mod(
    key="tidal",
    title="tidal: safe berthing windows",
    blurb="The harbour office schedules arrivals around the tide with the `tidal` helpers.",
    names=["depth_at", "safe_windows", "best_slot"],
    spec=dd('''
        # tidal: safe berthing windows

        Helpers for a small harbour office that schedules arrivals around the tide. A *tide table* is a list of
        `(minute, height_cm)` samples with integer values, sorted by minute (minutes since midnight; a table may run past 1440).
        Between two neighbouring samples the water height changes linearly. A table needs at least two samples and
        strictly increasing minutes; anything else is a `ValueError`.

        ## `depth_at(table, t) -> Fraction`
        The exact height at minute `t`. `ValueError` if `t` lies before the first or after the last sample.

        ## `safe_windows(table, draft_cm, clearance_cm, min_minutes=1) -> list[tuple[int, int]]`
        The whole minutes during which a vessel may be at the berth: those where the depth is at least
        `draft_cm + clearance_cm` (equal is fine).

        * Each window is `(first_minute, last_minute)`, both inclusive, both integers.
        * Windows that overlap or touch (the next starts at most one minute after the previous ends) are merged
          into one.
        * After merging, a window with fewer than `min_minutes` minutes (counting both ends) is dropped.
        * Windows come back in time order; if the water never gets deep enough the result is `[]`.

        ## `best_slot(windows, length) -> tuple[int, int] | None`
        The earliest stay of exactly `length` minutes (both ends inclusive) that fits inside one of the windows:
        `(start, start + length - 1)` of the first window with at least `length` minutes, or `None`.
    '''),
    core=dd('''
        """Safe berthing windows from a tide table."""
        from fractions import Fraction
        from math import ceil, floor

        __all__ = ["depth_at", "safe_windows", "best_slot"]


        def _check(table):
            if len(table) < 2:
                raise ValueError("a tide table needs at least two samples")
            for (t0, _), (t1, _) in zip(table, table[1:]):
                if t1 <= t0:
                    raise ValueError("sample minutes must be strictly increasing")


        def depth_at(table, t):
            _check(table)
            if t < table[0][0] or t > table[-1][0]:
                raise ValueError("time outside the tide table")
            for (t0, h0), (t1, h1) in zip(table, table[1:]):
                if t0 <= t <= t1:
                    return Fraction(h0) + Fraction(h1 - h0, t1 - t0) * (t - t0)


        def _segment_window(t0, h0, t1, h1, need):
            """Whole minutes of [t0, t1] where the depth is at least `need`, as (first, last) or None."""
            if h0 >= need and h1 >= need:
                return (t0, t1)
            if h0 < need and h1 < need:
                return None
            cross = t0 + Fraction(need - h0, h1 - h0) * (t1 - t0)
            if h0 < need:  # rising through the threshold
                lo, hi = ceil(cross), t1
            else:  # falling through it
                lo, hi = t0, floor(cross)
            return (lo, hi) if lo <= hi else None


        def safe_windows(table, draft_cm, clearance_cm, min_minutes=1):
            _check(table)
            need = draft_cm + clearance_cm
            spans = []
            for (t0, h0), (t1, h1) in zip(table, table[1:]):
                w = _segment_window(t0, h0, t1, h1, need)
                if w:
                    spans.append(w)
            merged = []
            for lo, hi in spans:
                if merged and lo <= merged[-1][1] + 1:
                    merged[-1][1] = max(merged[-1][1], hi)
                else:
                    merged.append([lo, hi])
            return [(lo, hi) for lo, hi in merged if hi - lo + 1 >= min_minutes]


        def best_slot(windows, length):
            for lo, hi in windows:
                if hi - lo + 1 >= length:
                    return (lo, lo + length - 1)
            return None
    '''),
    visible=dd('''
        from fractions import Fraction
        from tidal import best_slot, depth_at, safe_windows

        TABLE = [(0, 100), (60, 300), (120, 100)]


        class VisibleTests(unittest.TestCase):
            def test_depth_midway(self):
                self.assertEqual(depth_at(TABLE, 30), Fraction(200))

            def test_depth_outside(self):
                with self.assertRaises(ValueError):
                    depth_at(TABLE, 121)

            def test_one_window(self):
                self.assertEqual(safe_windows(TABLE, 250, 0), [(45, 75)])

            def test_slot(self):
                self.assertEqual(best_slot([(10, 20), (40, 90)], 30), (40, 69))
    '''),
    hidden=dd('''
        import random
        from fractions import Fraction
        from tidal import best_slot, depth_at, safe_windows


        def oracle_depth(table, t):
            for (t0, h0), (t1, h1) in zip(table, table[1:]):
                if t0 <= t <= t1:
                    return Fraction(h0) + Fraction(h1 - h0, t1 - t0) * (t - t0)


        def oracle_windows(table, need, min_minutes):
            mins = [m for m in range(table[0][0], table[-1][0] + 1) if oracle_depth(table, m) >= need]
            runs = []
            for m in mins:
                if runs and m <= runs[-1][1] + 1:
                    runs[-1][1] = m
                else:
                    runs.append([m, m])
            return [(a, b) for a, b in runs if b - a + 1 >= min_minutes]


        def random_table(rng):
            t = rng.randint(0, 60)
            out = []
            for _ in range(rng.randint(2, 8)):
                out.append((t, rng.randint(0, 400)))
                t += rng.randint(20, 180)
            return out


        class TidalTests(unittest.TestCase):
            def test_depth_examples(self):
                table = [(100, 50), (160, 110), (400, 10)]
                self.assertEqual(depth_at(table, 100), 50)
                self.assertEqual(depth_at(table, 130), 80)
                self.assertEqual(depth_at(table, 160), 110)
                self.assertEqual(depth_at(table, 280), 60)
                self.assertEqual(depth_at(table, 400), 10)
                self.assertEqual(depth_at(table, 101), Fraction(51))

            def test_depth_errors(self):
                table = [(100, 50), (160, 110)]
                for t in (99, 161):
                    with self.assertRaises(ValueError):
                        depth_at(table, t)
                for bad in ([], [(0, 1)], [(5, 1), (5, 2)], [(9, 1), (3, 2)]):
                    with self.assertRaises(ValueError):
                        depth_at(bad, 5)
                    with self.assertRaises(ValueError):
                        safe_windows(bad, 1, 0)

            def test_windows_differential(self):
                rng = random.Random(20240611)
                for _ in range(260):
                    table = random_table(rng)
                    draft, clearance = rng.randint(40, 300), rng.randint(0, 80)
                    min_minutes = rng.choice([1, 1, 5, 30])
                    want = oracle_windows(table, draft + clearance, min_minutes)
                    self.assertEqual(safe_windows(table, draft, clearance, min_minutes), want, (table, draft, clearance, min_minutes))

            def test_clearance_is_added(self):
                table = [(0, 100), (60, 300), (120, 100)]
                self.assertEqual(safe_windows(table, 150, 20), oracle_windows(table, 170, 1))
                self.assertNotEqual(safe_windows(table, 150, 20), safe_windows(table, 150, 0))

            def test_windows_share_a_minute_and_merge(self):
                table = [(0, 100), (60, 300), (120, 100)]
                self.assertEqual(len(safe_windows(table, 150, 0)), 1)

            def test_equal_depth_counts(self):
                table = [(0, 100), (10, 200), (20, 100)]
                self.assertEqual(safe_windows(table, 200, 0), [(10, 10)])
                self.assertEqual(safe_windows(table, 100, 0), [(0, 20)])

            def test_min_minutes_is_inclusive(self):
                table = [(0, 100), (10, 300), (20, 100)]
                self.assertEqual(safe_windows(table, 150, 0, 15), [(3, 17)])
                self.assertEqual(safe_windows(table, 150, 0, 16), [])

            def test_never_deep_enough(self):
                self.assertEqual(safe_windows([(0, 10), (50, 20)], 100, 5), [])

            def test_best_slot(self):
                self.assertEqual(best_slot([(0, 3), (20, 24)], 5), (20, 24))
                self.assertEqual(best_slot([(0, 3), (20, 24)], 4), (0, 3))
                self.assertEqual(best_slot([(0, 9), (20, 40)], 3), (0, 2))
                self.assertIsNone(best_slot([(0, 3)], 5))
                self.assertIsNone(best_slot([], 1))
    '''),
    bugs=[
        Bug("no-clearance", "need = draft_cm + clearance_cm", "need = draft_cm",
            ["safe_windows([(0, 100), (60, 300), (120, 100)], 150, 20)"], "safe_windows",
            "clearance forgotten when computing the required depth"),
        Bug("start-floor", "lo, hi = ceil(cross), t1", "lo, hi = floor(cross), t1",
            ["safe_windows([(0, 100), (60, 300), (120, 100)], 155, 0)"], "safe_windows",
            "a rising crossing rounds the first safe minute down"),
        Bug("end-ceil", "lo, hi = t0, floor(cross)", "lo, hi = t0, ceil(cross)",
            ["safe_windows([(0, 100), (60, 300), (120, 100)], 155, 0)"], "safe_windows",
            "a falling crossing rounds the last safe minute up"),
        Bug("merge-strict", "if merged and lo <= merged[-1][1] + 1:", "if merged and lo < merged[-1][1]:",
            ["safe_windows([(0, 100), (60, 300), (120, 100)], 150, 0)"], "safe_windows",
            "windows that share one minute are not merged"),
        Bug("min-len", "if hi - lo + 1 >= min_minutes]", "if hi - lo >= min_minutes]",
            ["safe_windows([(0, 100), (10, 300), (20, 100)], 150, 0, 15)"], "safe_windows",
            "minimum window length off by one"),
        Bug("slot-strict", "        if hi - lo + 1 >= length:\n            return", "        if hi - lo + 1 > length:\n            return",
            ["best_slot([(0, 3), (20, 24)], 5)"], "best_slot",
            "a window exactly as long as the stay is rejected"),
    ],
))

# ------------------------------------------------------------------------------------------------------- ferryfare
add(Mod(
    key="ferryfare",
    title="ferryfare: island ferry fares",
    blurb="The island ferry's booking desk prices tickets with the `ferryfare` helpers.",
    names=["passenger_fare", "vehicle_fare", "fare"],
    spec=dd('''
        # ferryfare: island ferry fares

        Fare rules of a small island ferry. Money is an integer number of cents.

        ## `passenger_fare(zones) -> int`
        The adult one-way fare for crossing `zones` zones (`zones >= 1`, otherwise `ValueError`): 450 for one zone,
        700 for two, and 175 more for every zone beyond the second.

        ## `vehicle_fare(length_dm) -> int`
        The vehicle surcharge by length in decimetres. `None` means no vehicle and costs 0; a length of 0 or less is a
        `ValueError`. Up to and including 30 dm costs 1200, up to 55 dm costs 2600, up to 80 dm costs 4800. A longer
        vehicle costs 4800 plus 900 for every *started* 10 dm beyond 80.

        ## `fare(zones, ages, length_dm=None, depart=(9, 0)) -> int`
        The total of one booking.

        * Passengers aged 16 or over pay the adult fare; ages 5 to 15 pay half of it (half a cent rounds up, per
          child); children under 5 travel free. A negative age is a `ValueError`.
        * A sailing that departs from 10:00 (inclusive) up to 15:00 (exclusive) is off-peak: the *passenger* total
          (not the vehicle surcharge) is reduced by 15%, rounded half up to a whole cent.
        * The vehicle surcharge is added, and the booking total is rounded *up* to the next multiple of 5 cents.
        * `depart` is `(hour, minute)` on a 24-hour clock.
    '''),
    core=dd('''
        """Fare rules of an island ferry."""

        __all__ = ["passenger_fare", "vehicle_fare", "fare"]


        def passenger_fare(zones):
            if zones < 1:
                raise ValueError("zones must be at least 1")
            if zones == 1:
                return 450
            return 700 + 175 * (zones - 2)


        def vehicle_fare(length_dm):
            if length_dm is None:
                return 0
            if length_dm <= 0:
                raise ValueError("vehicle length must be positive")
            if length_dm <= 30:
                return 1200
            if length_dm <= 55:
                return 2600
            if length_dm <= 80:
                return 4800
            started = -(-(length_dm - 80) // 10)
            return 4800 + 900 * started


        def fare(zones, ages, length_dm=None, depart=(9, 0)):
            adult = passenger_fare(zones)
            pax = 0
            for age in ages:
                if age < 0:
                    raise ValueError("negative age")
                if age >= 16:
                    pax += adult
                elif age >= 5:
                    pax += (adult + 1) // 2
            minute = depart[0] * 60 + depart[1]
            if 10 * 60 <= minute < 15 * 60:
                pax = (pax * 85 + 50) // 100
            total = pax + vehicle_fare(length_dm)
            return -(-total // 5) * 5
    '''),
    visible=dd('''
        from ferryfare import fare, passenger_fare, vehicle_fare


        class VisibleTests(unittest.TestCase):
            def test_zone_fares(self):
                self.assertEqual([passenger_fare(z) for z in (1, 2, 4)], [450, 700, 1050])

            def test_vehicle_bands(self):
                self.assertEqual([vehicle_fare(x) for x in (None, 20, 45, 70)], [0, 1200, 2600, 4800])

            def test_simple_fare(self):
                self.assertEqual(fare(1, [30, 40]), 900)

            def test_children_free_under_five(self):
                self.assertEqual(fare(2, [35, 3]), 700)
    '''),
    hidden=dd('''
        import random
        from fractions import Fraction
        from ferryfare import fare, passenger_fare, vehicle_fare


        def adult(zones):
            return {1: 450, 2: 700}.get(zones, 700 + 175 * (zones - 2))


        def veh(dm):
            if dm is None:
                return 0
            if dm <= 30:
                return 1200
            if dm <= 55:
                return 2600
            if dm <= 80:
                return 4800
            extra = 0
            while 80 + 10 * extra < dm:
                extra += 1
            return 4800 + 900 * extra


        def half_up(x):
            return int((Fraction(x) * 2 + 1) // 2)


        def oracle(zones, ages, dm, depart):
            a = adult(zones)
            pax = 0
            for age in ages:
                if age >= 16:
                    pax += a
                elif age >= 5:
                    pax += half_up(Fraction(a, 2))
            mins = depart[0] * 60 + depart[1]
            if 600 <= mins < 900:
                pax = half_up(Fraction(pax * 85, 100))
            total = pax + veh(dm)
            while total % 5:
                total += 1
            return total


        class FerryTests(unittest.TestCase):
            def test_passenger_fare(self):
                self.assertEqual([passenger_fare(z) for z in (1, 2, 3, 4, 7)], [450, 700, 875, 1050, 1575])
                for z in (0, -2):
                    with self.assertRaises(ValueError):
                        passenger_fare(z)

            def test_vehicle_fare_bands(self):
                got = [vehicle_fare(x) for x in (1, 30, 31, 55, 56, 80, 81, 90, 91, 100, 101, 135)]
                self.assertEqual(got, [1200, 1200, 2600, 2600, 4800, 4800, 5700, 5700, 6600, 6600, 7500, 10200])
                self.assertEqual(vehicle_fare(None), 0)
                for bad in (0, -5):
                    with self.assertRaises(ValueError):
                        vehicle_fare(bad)

            def test_age_boundaries(self):
                self.assertEqual(fare(1, [4]), 0)
                self.assertEqual(fare(1, [5]), 225)
                self.assertEqual(fare(3, [5]), 440)  # 875 / 2 = 437.5 -> 438 -> 440
                self.assertEqual(fare(3, [15, 15]), 880)  # 876 -> 880
                self.assertEqual(fare(3, [16]), 875)
                with self.assertRaises(ValueError):
                    fare(1, [20, -1])

            def test_child_halves_round_per_child(self):
                self.assertEqual(fare(3, [6, 7]), 880)  # 438 + 438 = 876 (not 875)
                self.assertEqual(fare(3, [30, 6, 7]), 1755)

            def test_offpeak_window(self):
                self.assertEqual(fare(2, [30], depart=(9, 59)), 700)
                self.assertEqual(fare(2, [30], depart=(10, 0)), 595)
                self.assertEqual(fare(2, [30], depart=(14, 59)), 595)
                self.assertEqual(fare(2, [30], depart=(15, 0)), 700)

            def test_offpeak_does_not_touch_the_vehicle(self):
                self.assertEqual(fare(1, [30], 40, (12, 0)), 2985)  # 383 + 2600 = 2983 -> 2985

            def test_offpeak_rounds_half_up_to_cents(self):
                self.assertEqual(fare(3, [30, 30], depart=(11, 0)), 1490)  # 1487.5 -> 1488 -> 1490
                self.assertEqual(fare(1, [30], depart=(11, 0)), 385)  # 382.5 -> 383 -> 385
                self.assertEqual(fare(3, [30, 6, 6, 6], depart=(11, 0)), 1865)
                self.assertEqual(fare(3, [30, 6, 6, 6], depart=(11, 0)), oracle(3, [30, 6, 6, 6], None, (11, 0)))

            def test_total_rounds_up_to_five(self):
                self.assertEqual(fare(3, [30, 5]), 1315)  # 875 + 438 = 1313

            def test_differential(self):
                rng = random.Random(77)
                for _ in range(600):
                    zones = rng.randint(1, 6)
                    ages = [rng.choice([0, 3, 4, 5, 6, 9, 15, 16, 40, 70]) for _ in range(rng.randint(0, 6))]
                    dm = rng.choice([None, None, 12, 30, 31, 55, 56, 80, 81, 89, 90, 91, 140])
                    depart = (rng.choice([6, 9, 10, 12, 14, 15, 18]), rng.choice([0, 1, 30, 59]))
                    self.assertEqual(fare(zones, ages, dm, depart), oracle(zones, ages, dm, depart), (zones, ages, dm, depart))
    '''),
    bugs=[
        Bug("child-age", "elif age >= 5:", "elif age > 5:", ["fare(1, [5])"], "fare", "a five-year-old travels free"),
        Bug("child-half", "pax += (adult + 1) // 2", "pax += adult // 2", ["fare(3, [6, 7])"], "fare",
            "half fares round down instead of up"),
        Bug("offpeak-end", "if 10 * 60 <= minute < 15 * 60:", "if 10 * 60 <= minute <= 15 * 60:",
            ["fare(2, [30], depart=(15, 0))"], "fare", "the 15:00 sailing is priced off-peak"),
        Bug("offpeak-start", "if 10 * 60 <= minute < 15 * 60:", "if 10 * 60 < minute < 15 * 60:",
            ["fare(2, [30], depart=(10, 0))"], "fare", "the 10:00 sailing is priced peak"),
        Bug("offpeak-floor", "pax = (pax * 85 + 50) // 100", "pax = (pax * 85) // 100",
            ["fare(3, [30, 6, 6, 6], depart=(11, 0))"], "fare", "off-peak discount rounds down"),
        Bug("round-down", "return -(-total // 5) * 5", "return total // 5 * 5", ["fare(3, [30, 5])"], "fare",
            "the booking total is rounded down to 5 cents"),
        Bug("vehicle-started", "started = -(-(length_dm - 80) // 10)", "started = (length_dm - 80) // 10",
            ["vehicle_fare(81)", "vehicle_fare(95)"], "vehicle_fare", "partial 10 dm steps are not charged"),
        Bug("vehicle-band", "if length_dm <= 55:", "if length_dm < 55:", ["vehicle_fare(55)"], "vehicle_fare",
            "a 55 dm vehicle is charged the larger band"),
        Bug("zone-slope", "return 700 + 175 * (zones - 2)", "return 700 + 175 * (zones - 1)", ["passenger_fare(3)", "fare(4, [30])"],
            "passenger_fare", "zones beyond the second cost too much"),
    ],
))

# ------------------------------------------------------------------------------------------------------- stampduty
add(Mod(
    key="stampduty",
    title="stampduty: land transfer duty",
    blurb="The conveyancing desk quotes land transfer duty for the Hollin district with the `stampduty` helpers.",
    names=["duty", "effective_rate_bp"],
    spec=dd('''
        # stampduty: land transfer duty (district of Hollin)

        Prices and duty are whole currency units (`int`). All arithmetic is exact (use fractions, never floats); only the
        final amount is rounded, **once**, half up to a whole unit.

        ## `duty(price, first_home=False, resident=True) -> int`
        `price <= 0` is a `ValueError`.

        1. **Marginal bands.** Each rate applies only to the slice of the price inside its band:
           up to 180 000 at 0%; from 180 000 up to 350 000 at 2.5%; from 350 000 up to 700 000 at 5%; above
           700 000 at 8%.
        2. **First-home relief** (only when `first_home` is true): a price of 300 000 or less pays no duty at all; a price
           above 300 000 up to and including 450 000 pays the marginal duty multiplied by
           `(450 000 - price) / 150 000`; above 450 000 there is no relief.
        3. **Non-resident surcharge** (only when `resident` is false): 4% of the *full price*, added after the relief
           (the relief never reduces it).

        ## `effective_rate_bp(price, first_home=False, resident=True) -> int`
        Duty as a share of the price in basis points (1/100 of a percent), `duty * 10000 / price`, computed from the
        already rounded duty and rounded half up to an integer.
    '''),
    core=dd('''
        """Land transfer duty for the district of Hollin."""
        from fractions import Fraction

        __all__ = ["duty", "effective_rate_bp"]

        BANDS = [
            (180_000, Fraction(0)),
            (350_000, Fraction(25, 1000)),
            (700_000, Fraction(5, 100)),
            (None, Fraction(8, 100)),
        ]


        def _round_half_up(x):
            return int((Fraction(x) * 2 + 1) // 2)


        def _marginal(price):
            total, lo = Fraction(0), 0
            for hi, rate in BANDS:
                if price <= lo:
                    break
                top = price if hi is None else min(price, hi)
                total += (top - lo) * rate
                if hi is None:
                    break
                lo = hi
            return total


        def duty(price, first_home=False, resident=True):
            if price <= 0:
                raise ValueError("price must be positive")
            d = _marginal(price)
            if first_home:
                if price <= 300_000:
                    d = Fraction(0)
                elif price <= 450_000:
                    d = d * Fraction(450_000 - price, 150_000)
            if not resident:
                d += Fraction(price * 4, 100)
            return _round_half_up(d)


        def effective_rate_bp(price, first_home=False, resident=True):
            d = duty(price, first_home, resident)
            return _round_half_up(Fraction(d * 10_000, price))
    '''),
    visible=dd('''
        from stampduty import duty, effective_rate_bp


        class VisibleTests(unittest.TestCase):
            def test_below_first_band(self):
                self.assertEqual(duty(150_000), 0)

            def test_two_bands(self):
                self.assertEqual(duty(300_000), 3000)

            def test_rejects_non_positive(self):
                with self.assertRaises(ValueError):
                    duty(0)

            def test_rate(self):
                self.assertEqual(effective_rate_bp(400_000), 169)
    '''),
    hidden=dd('''
        import random
        from fractions import Fraction
        from stampduty import duty, effective_rate_bp


        def rhu(x):
            return int((Fraction(x) * 2 + 1) // 2)


        def oracle(price, first_home, resident):
            d = Fraction(0)
            d += max(0, min(price, 350_000) - 180_000) * Fraction(25, 1000)
            d += max(0, min(price, 700_000) - 350_000) * Fraction(5, 100)
            d += max(0, price - 700_000) * Fraction(8, 100)
            if first_home:
                if price <= 300_000:
                    d = Fraction(0)
                elif price <= 450_000:
                    d *= Fraction(450_000 - price, 150_000)
            if not resident:
                d += Fraction(4 * price, 100)
            return rhu(d)


        class DutyTests(unittest.TestCase):
            def test_known_values(self):
                self.assertEqual(duty(180_000), 0)
                self.assertEqual(duty(180_001), 0)  # 0.025 rounds down
                self.assertEqual(duty(350_000), 4250)
                self.assertEqual(duty(700_000), 21750)
                self.assertEqual(duty(900_000), 37750)
                self.assertEqual(duty(180_020), 1)  # 0.5 rounds up

            def test_first_home_relief_edges(self):
                self.assertEqual(duty(300_000, first_home=True), 0)
                self.assertEqual(duty(300_000), 3000)
                self.assertEqual(duty(300_001, first_home=True), 3000)  # 3000.025 * 149999 / 150000
                self.assertEqual(duty(450_000, first_home=True), 0)
                self.assertEqual(duty(450_001, first_home=True), 9250)
                self.assertEqual(duty(450_001, first_home=True), duty(450_001))

            def test_taper_is_exact_before_rounding(self):
                self.assertEqual(duty(375_000, first_home=True), 2750)
                self.assertEqual(duty(420_000, first_home=True), 1550)
                self.assertEqual(duty(449_999, first_home=True), 0)
                self.assertEqual(duty(300_223, first_home=True), oracle(300_223, True, True))
                self.assertEqual(duty(300_260, first_home=True), oracle(300_260, True, True))

            def test_non_resident_surcharge_uses_full_price(self):
                self.assertEqual(duty(300_000, first_home=True, resident=False), 12_000)
                self.assertEqual(duty(500_000, resident=False), 31_750)
                self.assertEqual(duty(400_000, first_home=True, resident=False), 18_250)

            def test_errors(self):
                for p in (0, -1, -500_000):
                    with self.assertRaises(ValueError):
                        duty(p)

            def test_differential(self):
                rng = random.Random(4242)
                for _ in range(500):
                    price = rng.choice([rng.randint(1, 1_500_000), rng.randint(290_000, 460_000), rng.choice([180_000, 350_000, 700_000, 300_000, 450_000])])
                    fh, res = rng.random() < 0.5, rng.random() < 0.6
                    self.assertEqual(duty(price, fh, res), oracle(price, fh, res), (price, fh, res))

            def test_effective_rate(self):
                self.assertEqual(effective_rate_bp(400_000), 169)  # 6750 / 400000 = 168.75 bp
                self.assertEqual(effective_rate_bp(100_000), 0)
                self.assertEqual(effective_rate_bp(200_000), 25)
                self.assertEqual(effective_rate_bp(300_000, resident=False), 500)
                rng = random.Random(5)
                for _ in range(120):
                    p = rng.randint(1, 1_200_000)
                    self.assertEqual(effective_rate_bp(p, False, True), rhu(Fraction(oracle(p, False, True) * 10_000, p)))
    '''),
    bugs=[
        Bug("rate-drift", "(350_000, Fraction(25, 1000)),", "(350_000, Fraction(2, 100)),", ["duty(300_000)", "duty(600_000)"],
            "BANDS", "the second band's rate is 2% instead of 2.5%"),
        Bug("taper-denominator", "d = d * Fraction(450_000 - price, 150_000)", "d = d * Fraction(450_000 - price, 450_000)",
            ["duty(420_000, first_home=True)"], "duty", "relief taper divides by the wrong span"),
        Bug("relief-edge", "if price <= 300_000:", "if price < 300_000:", ["duty(300_000, first_home=True)"], "duty",
            "a price of exactly 300 000 gets no full relief"),
        Bug("relief-top", "elif price <= 450_000:", "elif price < 450_000:", ["duty(450_000, first_home=True)"], "duty",
            "a price of exactly 450 000 loses the taper"),
        Bug("surcharge-base", "d += Fraction(price * 4, 100)", "d += d * Fraction(4, 100)", ["duty(300_000, resident=False)"], "duty",
            "surcharge taken on the duty instead of the price"),
        Bug("round-floor", "return int((Fraction(x) * 2 + 1) // 2)", "return int(Fraction(x))", ["duty(180_020)", "effective_rate_bp(200_000)"],
            "_round_half_up", "final rounding truncates"),
        Bug("round-early", "d = _marginal(price)", "d = Fraction(_round_half_up(_marginal(price)))", ["duty(300_223, first_home=True)", "duty(300_667, first_home=True)"],
            "duty", "marginal duty is rounded before the relief"),
        Bug("bp-from-exact", "d = duty(price, first_home, resident)\n    return _round_half_up(Fraction(d * 10_000, price))",
            "d = duty(price, first_home, resident)\n    return d * 10_000 // price", ["effective_rate_bp(200_000)", "effective_rate_bp(333_333)"],
            "effective_rate_bp", "basis points truncated instead of rounded"),
    ],
))

# ----------------------------------------------------------------------------------------------------- samplelabel
add(Mod(
    key="samplelabel",
    title="samplelabel: sample tube labels",
    blurb="The sample-tracking system of a small lab prints and checks tube labels with the `samplelabel` helpers.",
    names=["check_char", "make_label", "parse_label", "next_label"],
    probe_pre="from datetime import date",
    spec=dd('''
        # samplelabel: sample tube labels

        A label looks like `SMP-KEL-20240229-0042-R`: the prefix `SMP`, a site code, a date, a sequence number and a
        check character, separated by dashes.

        * **site**: two to four capital letters `A`-`Z`.
        * **date**: eight digits `YYYYMMDD`, a real calendar date in the years 2000 to 2099.
        * **seq**: four digits, `0001` to `9999` (`0000` is not valid).
        * **check**: one character of the alphabet `ACDEFGHJKLMNPQRTUVWXY2346789` (28 symbols).

        ## `check_char(body) -> str`
        `body` is the text `<site><YYYYMMDD><seq>` without dashes. A letter has the value of its position in the
        alphabet (`A` = 1 ... `Z` = 26), a digit its own value. Number the characters of `body` from 1; the sum of
        `position * value` over all characters, modulo 28, indexes the alphabet above.

        ## `make_label(site, day, seq) -> str`
        `day` is a `datetime.date`. `ValueError` for a bad site code, a year outside 2000-2099, or a `seq` outside
        1..9999.

        ## `parse_label(text) -> dict`
        Returns `{"site": str, "date": date, "seq": int}`. `ValueError` for anything that is not exactly a valid
        label: wrong shape (also trailing characters, lower-case letters), impossible date, year outside 2000-2099,
        `seq` 0, or a wrong check character.

        ## `next_label(existing, site, day) -> str`
        The label for the next sample of that site and date: sequence number one above the **largest** sequence number
        among the valid labels in `existing` with the same site and the same date (labels that fail to parse are
        ignored); `1` if there are none. `OverflowError` when the largest is already 9999.
    '''),
    core=dd('''
        """Sample tube labels with a check character."""
        import re
        from datetime import date

        __all__ = ["check_char", "make_label", "parse_label", "next_label"]

        ALPHABET = "ACDEFGHJKLMNPQRTUVWXY2346789"
        _LABEL = re.compile(r"SMP-([A-Z]{2,4})-([0-9]{8})-([0-9]{4})-(.)")


        def _value(ch):
            return ord(ch) - 64 if ch.isalpha() else int(ch)


        def check_char(body):
            total = sum(i * _value(ch) for i, ch in enumerate(body, start=1))
            return ALPHABET[total % len(ALPHABET)]


        def make_label(site, day, seq):
            if not re.fullmatch(r"[A-Z]{2,4}", site):
                raise ValueError("bad site code")
            if not 2000 <= day.year <= 2099:
                raise ValueError("year out of range")
            if not 1 <= seq <= 9999:
                raise ValueError("seq out of range")
            ymd = f"{day.year:04d}{day.month:02d}{day.day:02d}"
            body = f"{site}{ymd}{seq:04d}"
            return f"SMP-{site}-{ymd}-{seq:04d}-{check_char(body)}"


        def parse_label(text):
            m = _LABEL.fullmatch(text)
            if not m:
                raise ValueError("malformed label")
            site, ymd, seq, check = m.groups()
            try:
                day = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:]))
            except ValueError:
                raise ValueError("impossible date") from None
            if not 2000 <= day.year <= 2099:
                raise ValueError("year out of range")
            n = int(seq)
            if n == 0:
                raise ValueError("sequence number 0")
            if check_char(site + ymd + seq) != check:
                raise ValueError("bad check character")
            return {"site": site, "date": day, "seq": n}


        def next_label(existing, site, day):
            top = 0
            for text in existing:
                try:
                    p = parse_label(text)
                except ValueError:
                    continue
                if p["site"] == site and p["date"] == day:
                    top = max(top, p["seq"])
            if top >= 9999:
                raise OverflowError("no sequence numbers left")
            return make_label(site, day, top + 1)
    '''),
    visible=dd('''
        from datetime import date
        from samplelabel import make_label, next_label, parse_label


        class VisibleTests(unittest.TestCase):
            def test_roundtrip(self):
                text = make_label("KEL", date(2024, 2, 29), 42)
                p = parse_label(text)
                self.assertEqual((p["site"], p["date"], p["seq"]), ("KEL", date(2024, 2, 29), 42))

            def test_bad_site(self):
                with self.assertRaises(ValueError):
                    make_label("K", date(2024, 1, 1), 1)

            def test_first_label(self):
                self.assertTrue(next_label([], "AB", date(2024, 5, 1)).startswith("SMP-AB-20240501-0001-"))
    '''),
    hidden=dd('''
        import random
        from datetime import date, timedelta
        from samplelabel import check_char, make_label, next_label, parse_label

        ALPHA = "ACDEFGHJKLMNPQRTUVWXY2346789"


        def oracle_check(body):
            total = 0
            for i, ch in enumerate(body):
                v = int(ch) if ch.isdigit() else "ABCDEFGHIJKLMNOPQRSTUVWXYZ".index(ch) + 1
                total += (i + 1) * v
            return ALPHA[total % 28]


        def oracle_label(site, day, seq):
            ymd = day.strftime("%Y%m%d")
            return f"SMP-{site}-{ymd}-{seq:04d}-{oracle_check(site + ymd + '%04d' % seq)}"


        class LabelTests(unittest.TestCase):
            def test_check_char_values(self):
                self.assertEqual(check_char("A"), ALPHA[1])  # 1 * 1 = 1
                self.assertEqual(check_char("AB"), ALPHA[(1 + 4) % 28])
                self.assertEqual(check_char("Z"), ALPHA[26])
                self.assertEqual(check_char("Z9"), ALPHA[(26 + 18) % 28])
                self.assertEqual(check_char("00000"), "A")  # index 0

            def test_check_char_differential(self):
                rng = random.Random(9)
                chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                for _ in range(300):
                    body = "".join(rng.choice(chars) for _ in range(rng.randint(1, 20)))
                    self.assertEqual(check_char(body), oracle_check(body), body)

            def test_make_label_matches_oracle(self):
                rng = random.Random(10)
                for _ in range(200):
                    site = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(rng.randint(2, 4)))
                    day = date(2000, 1, 1) + timedelta(days=rng.randint(0, 36524))
                    seq = rng.choice([1, 9, 10, 99, 100, 999, 1000, 9998, 9999, rng.randint(1, 9999)])
                    self.assertEqual(make_label(site, day, seq), oracle_label(site, day, seq))

            def test_make_label_errors(self):
                for site in ("K", "KELLY", "kel", "K3L", ""):
                    with self.assertRaises(ValueError):
                        make_label(site, date(2024, 1, 1), 1)
                for seq in (0, 10000, -1):
                    with self.assertRaises(ValueError):
                        make_label("KEL", date(2024, 1, 1), seq)
                for day in (date(1999, 12, 31), date(2100, 1, 1)):
                    with self.assertRaises(ValueError):
                        make_label("KEL", day, 5)
                make_label("KEL", date(2000, 1, 1), 1)
                make_label("KEL", date(2099, 12, 31), 9999)

            def test_parse_roundtrip(self):
                rng = random.Random(11)
                for _ in range(150):
                    day = date(2000, 1, 1) + timedelta(days=rng.randint(0, 36524))
                    seq = rng.randint(1, 9999)
                    text = oracle_label("QX", day, seq)
                    self.assertEqual(parse_label(text), {"site": "QX", "date": day, "seq": seq})

            def test_parse_rejects(self):
                good = oracle_label("KEL", date(2024, 2, 29), 42)
                self.assertEqual(parse_label(good)["date"], date(2024, 2, 29))
                bad = [
                    good + "x", good + "\\n", " " + good, good.lower(), good.replace("SMP", "SMQ"), good[:-1], good[:-1] + "B",
                    "SMP-KEL-20230229-0042-A", "SMP-KEL-20241301-0042-A", "SMP-KEL-19991231-0001-A", "SMP-KEL-21000101-0001-A",
                    oracle_label("KEL", date(2024, 2, 29), 1)[:-1] + "A" if not oracle_label("KEL", date(2024, 2, 29), 1).endswith("A") else "x",
                    "SMP-K-20240101-0001-A", "SMP-KELLY-20240101-0001-A", "SMP-KEL-20240101-001-A", "SMP-KEL-2024010-0001-A",
                ]
                for text in bad:
                    with self.assertRaises(ValueError, msg=text):
                        parse_label(text)

            def test_seq_zero_is_invalid_even_with_valid_check(self):
                text = f"SMP-KEL-20240301-0000-{oracle_check('KEL202403010000')}"
                with self.assertRaises(ValueError):
                    parse_label(text)

            def test_year_range_edges_parse(self):
                for day in (date(2000, 1, 1), date(2099, 12, 31)):
                    self.assertEqual(parse_label(oracle_label("AB", day, 7))["date"], day)

            def test_next_label(self):
                d = date(2024, 6, 5)
                existing = [oracle_label("AB", d, 3), oracle_label("AB", d, 12), oracle_label("AB", d, 7),
                            oracle_label("CD", d, 40), oracle_label("AB", date(2024, 6, 6), 50), "garbage",
                            "SMP-AB-20240605-0099-A"]
                self.assertEqual(next_label(existing, "AB", d), oracle_label("AB", d, 13))
                self.assertEqual(next_label(existing, "CD", d), oracle_label("CD", d, 41))
                self.assertEqual(next_label(existing, "EF", d), oracle_label("EF", d, 1))
                self.assertEqual(next_label(existing, "AB", date(2024, 6, 7)), oracle_label("AB", date(2024, 6, 7), 1))

            def test_next_label_ignores_invalid_labels_but_not_valid_ones(self):
                d = date(2024, 6, 5)
                bad_check = "SMP-AB-20240605-0500-" + ("A" if oracle_check("AB202406050500") != "A" else "C")
                self.assertEqual(next_label([bad_check, oracle_label("AB", d, 2)], "AB", d), oracle_label("AB", d, 3))

            def test_next_label_overflow(self):
                d = date(2024, 6, 5)
                self.assertEqual(next_label([oracle_label("AB", d, 9998)], "AB", d), oracle_label("AB", d, 9999))
                with self.assertRaises(OverflowError):
                    next_label([oracle_label("AB", d, 9999)], "AB", d)
    '''),
    bugs=[
        Bug("weights-from-zero", "enumerate(body, start=1)", "enumerate(body, start=0)",
            ["make_label('KEL', date(2024, 2, 29), 42)"], "check_char",
            "positions are numbered from 0 instead of 1"),
        Bug("modulus-26", "ALPHABET[total % len(ALPHABET)]", "ALPHABET[total % 26]",
            ["check_char('Z9')", "check_char('QQQQ')"], "check_char", "check index taken modulo 26 instead of 28"),
        Bug("letter-offset", "ord(ch) - 64 if ch.isalpha()", "ord(ch) - 65 if ch.isalpha()",
            ["check_char('KEL20240229')"], "_value", "letters are valued from 0"),
        Bug("trailing-text", "m = _LABEL.fullmatch(text)", "m = _LABEL.match(text)",
            ["parse_label(make_label('KEL', date(2024, 2, 29), 42) + '-extra')"], "parse_label",
            "text after the label is accepted"),
        Bug("seq-last", 'top = max(top, p["seq"])', 'top = p["seq"]',
            ["next_label([make_label('AB', date(2024, 6, 5), n) for n in (12, 3)], 'AB', date(2024, 6, 5))"],
            "next_label", "the last matching label decides the next sequence number instead of the largest"),
        Bug("overflow-edge", "if top >= 9999:", "if top > 9999:",
            ["next_label([make_label('AB', date(2024, 6, 5), 9999)], 'AB', date(2024, 6, 5))"],
            "next_label", "a full day raises ValueError instead of OverflowError"),
        Bug("seq-zero", "if n == 0:", "if n < 0:",
            ["parse_label('SMP-KEL-20240301-0000-' + check_char('KEL202403010000'))"], "parse_label", "sequence 0 is accepted"),
        Bug("site-or-date", 'if p["site"] == site and p["date"] == day:', 'if p["site"] == site or p["date"] == day:',
            ["next_label([make_label('CD', date(2024, 6, 5), 40)], 'AB', date(2024, 6, 5))"],
            "next_label", "labels of another site count towards the sequence"),
        Bug("year-edge", "if not 2000 <= day.year <= 2099:\n        raise ValueError(\"year out of range\")\n    n = int(seq)",
            "if not 2000 < day.year < 2099:\n        raise ValueError(\"year out of range\")\n    n = int(seq)",
            ["parse_label(make_label('AB', date(2000, 1, 1), 7))"], "parse_label", "years 2000 and 2099 are rejected"),
    ],
))

# ------------------------------------------------------------------------------------------------------- initiative
add(Mod(
    key="initiative",
    title="initiative: skirmish turn order",
    blurb="The game-night skirmish tracker orders turns with the house rules implemented in `initiative`.",
    names=["order", "turns", "delay", "drop"],
    spec=dd('''
        # initiative: turn order for a skirmish tracker

        A combatant is a dict `{"name": str, "roll": int, "dex": int}` with an optional `"surprised": bool`
        (default false). Names are unique; a duplicate name is a `ValueError`.

        ## `order(combatants) -> list[str]`
        Names in turn order: the higher `roll` acts first. Equal rolls: the higher `dex` first. Still equal: by
        name alphabetically, ignoring case (`"anna"` before `"Bo"`), and if the names then still tie, uppercase first.

        ## `turns(combatants, rounds) -> list[tuple[int, str]]`
        The sequence of `(round, name)` for rounds `1..rounds`, each round in `order()`. A *surprised* combatant skips
        round 1 only and acts normally from round 2.

        ## `delay(order_list, name, after) -> list[str]`
        A new list in which `name` has been moved to stand directly behind `after`. `ValueError` if either name is
        missing or both are the same.

        ## `drop(order_list, name, current) -> tuple[list[str], int]`
        Remove a combatant who has left the fight. `current` is the index (in `order_list`) of whoever has the turn.
        Returns the new list and the index of whoever has the turn now:

        * if someone *before* the current combatant left, the same combatant keeps the turn (the index shrinks);
        * if the current combatant left, the turn passes to the next one in the list (the same index), wrapping to 0
          when the last one left;
        * if someone after the current combatant left, nothing changes;
        * an empty list gives `([], 0)`. `ValueError` if `name` is not in the list.
    '''),
    core=dd('''
        """Turn order for a skirmish tracker, with house rules."""

        __all__ = ["order", "turns", "delay", "drop"]


        def order(combatants):
            names = [c["name"] for c in combatants]
            if len(set(names)) != len(names):
                raise ValueError("duplicate name")
            ranked = sorted(combatants, key=lambda c: (-c["roll"], -c["dex"], c["name"].lower(), c["name"]))
            return [c["name"] for c in ranked]


        def turns(combatants, rounds):
            sequence = order(combatants)
            surprised = {c["name"] for c in combatants if c.get("surprised")}
            out = []
            for r in range(1, rounds + 1):
                for name in sequence:
                    if r == 1 and name in surprised:
                        continue
                    out.append((r, name))
            return out


        def delay(order_list, name, after):
            if name == after or name not in order_list or after not in order_list:
                raise ValueError("cannot delay")
            rest = [n for n in order_list if n != name]
            i = rest.index(after)
            return rest[: i + 1] + [name] + rest[i + 1 :]


        def drop(order_list, name, current):
            if name not in order_list:
                raise ValueError("no such combatant")
            idx = order_list.index(name)
            rest = [n for n in order_list if n != name]
            if not rest:
                return [], 0
            if idx < current:
                current -= 1
            elif idx == current and current >= len(rest):
                current = 0
            return rest, current
    '''),
    visible=dd('''
        from initiative import delay, drop, order, turns

        C = [
            {"name": "Ruk", "roll": 14, "dex": 2},
            {"name": "Ines", "roll": 17, "dex": 1},
            {"name": "Tomas", "roll": 9, "dex": 3},
        ]


        class VisibleTests(unittest.TestCase):
            def test_order_by_roll(self):
                self.assertEqual(order(C), ["Ines", "Ruk", "Tomas"])

            def test_delay(self):
                self.assertEqual(delay(["a", "b", "c"], "a", "b"), ["b", "a", "c"])

            def test_turns_two_rounds(self):
                self.assertEqual(turns(C, 2)[3], (2, "Ines"))

            def test_drop_last(self):
                self.assertEqual(drop(["a", "b", "c"], "c", 0), (["a", "b"], 0))
    '''),
    hidden=dd('''
        import random
        from initiative import delay, drop, order, turns


        def mk(name, roll, dex=0, surprised=None):
            c = {"name": name, "roll": roll, "dex": dex}
            if surprised is not None:
                c["surprised"] = surprised
            return c


        class InitiativeTests(unittest.TestCase):
            def test_order_ties(self):
                cs = [mk("bo", 10, 1), mk("Cy", 10, 4), mk("Al", 10, 1), mk("dee", 12), mk("al", 10, 1), mk("Zed", 3)]
                self.assertEqual(order(cs), ["dee", "Cy", "Al", "al", "bo", "Zed"])

            def test_order_name_ignores_case(self):
                cs = [mk("bea", 5), mk("Ann", 5), mk("anna", 5), mk("Carl", 5)]
                self.assertEqual(order(cs), ["Ann", "anna", "bea", "Carl"])

            def test_order_random_matches_sorted_key(self):
                rng = random.Random(3)
                for _ in range(100):
                    names = rng.sample(["ann", "Bob", "cy", "Dee", "eve", "Fox", "gus", "Hal", "ida"], rng.randint(1, 9))
                    cs = [mk(n, rng.randint(1, 5), rng.randint(0, 3)) for n in names]
                    want = [c["name"] for c in sorted(cs, key=lambda c: (-c["roll"], -c["dex"], c["name"].lower()))]
                    self.assertEqual(order(cs), want)

            def test_duplicate_names(self):
                with self.assertRaises(ValueError):
                    order([mk("a", 1), mk("a", 2)])
                with self.assertRaises(ValueError):
                    turns([mk("a", 1), mk("a", 2)], 1)

            def test_surprised_skips_round_one_only(self):
                cs = [mk("a", 15, surprised=True), mk("b", 10), mk("c", 5, surprised=False)]
                self.assertEqual(turns(cs, 3), [(1, "b"), (1, "c"), (2, "a"), (2, "b"), (2, "c"), (3, "a"), (3, "b"), (3, "c")])

            def test_optional_surprised_flag(self):
                self.assertEqual(turns([mk("a", 1)], 2), [(1, "a"), (2, "a")])
                self.assertEqual(turns([mk("a", 1)], 0), [])

            def test_everyone_surprised(self):
                cs = [mk("a", 2, surprised=True), mk("b", 1, surprised=True)]
                self.assertEqual(turns(cs, 2), [(2, "a"), (2, "b")])

            def test_delay_moves_back_and_forward(self):
                base = ["a", "b", "c", "d", "e"]
                self.assertEqual(delay(base, "a", "c"), ["b", "c", "a", "d", "e"])
                self.assertEqual(delay(base, "a", "e"), ["b", "c", "d", "e", "a"])
                self.assertEqual(delay(base, "e", "a"), ["a", "e", "b", "c", "d"])
                self.assertEqual(delay(base, "d", "b"), ["a", "b", "d", "c", "e"])
                self.assertEqual(delay(base, "c", "b"), base)
                self.assertEqual(base, ["a", "b", "c", "d", "e"])

            def test_delay_errors(self):
                for args in (("a", "a"), ("a", "z"), ("z", "a")):
                    with self.assertRaises(ValueError):
                        delay(["a", "b"], *args)

            def test_drop_before_current(self):
                self.assertEqual(drop(["a", "b", "c", "d"], "a", 2), (["b", "c", "d"], 1))
                self.assertEqual(drop(["a", "b", "c", "d"], "b", 2), (["a", "c", "d"], 1))

            def test_drop_current(self):
                self.assertEqual(drop(["a", "b", "c", "d"], "c", 2), (["a", "b", "d"], 2))
                self.assertEqual(drop(["a", "b", "c", "d"], "a", 0), (["b", "c", "d"], 0))

            def test_drop_current_last_wraps(self):
                self.assertEqual(drop(["a", "b", "c", "d"], "d", 3), (["a", "b", "c"], 0))

            def test_drop_after_current(self):
                self.assertEqual(drop(["a", "b", "c", "d"], "d", 1), (["a", "b", "c"], 1))
                self.assertEqual(drop(["a", "b", "c", "d"], "c", 0), (["a", "b", "d"], 0))

            def test_drop_last_remaining_and_errors(self):
                self.assertEqual(drop(["a"], "a", 0), ([], 0))
                with self.assertRaises(ValueError):
                    drop(["a", "b"], "z", 0)

            def test_drop_keeps_turn_holder_random(self):
                rng = random.Random(8)
                for _ in range(200):
                    n = rng.randint(2, 8)
                    lst = [f"n{i}" for i in range(n)]
                    cur = rng.randrange(n)
                    gone = rng.choice(lst)
                    new, idx = drop(lst, gone, cur)
                    if gone != lst[cur]:
                        self.assertEqual(new[idx], lst[cur])
                    else:
                        want = lst[(cur + 1) % n] if n > 1 else None
                        self.assertEqual(new[idx], want)
    '''),
    bugs=[
        Bug("dex-ascending", 'key=lambda c: (-c["roll"], -c["dex"],', 'key=lambda c: (-c["roll"], c["dex"],',
            ["order([{'name': 'a', 'roll': 10, 'dex': 1}, {'name': 'b', 'roll': 10, 'dex': 4}])"], "order",
            "equal rolls are ordered by lower dex first"),
        Bug("case-sensitive-names", 'c["name"].lower(), c["name"]))', 'c["name"], c["name"].lower()))',
            ["order([{'name': 'bea', 'roll': 5, 'dex': 0}, {'name': 'Carl', 'roll': 5, 'dex': 0}, {'name': 'Ann', 'roll': 5, 'dex': 0}])"],
            "order", "ties by name are case sensitive"),
        Bug("surprised-all-rounds", "if r == 1 and name in surprised:", "if name in surprised:",
            ["turns([{'name': 'a', 'roll': 3, 'dex': 0, 'surprised': True}, {'name': 'b', 'roll': 1, 'dex': 0}], 2)"], "turns",
            "surprised combatants never act"),
        Bug("surprised-required", 'c.get("surprised")', 'c["surprised"]',
            ["turns([{'name': 'a', 'roll': 3, 'dex': 0}], 1)"], "turns", "the surprised flag is mandatory"),
        Bug("delay-stale-index", "i = rest.index(after)", "i = order_list.index(after)",
            ["delay(['a', 'b', 'c', 'd'], 'a', 'c')"], "delay", "delaying a combatant past a later one lands one slot too far"),
        Bug("drop-index-before", "if idx < current:\n        current -= 1", "if idx <= current:\n        current -= 1",
            ["drop(['a', 'b', 'c', 'd'], 'c', 2)"], "drop", "dropping the current combatant gives the turn to the previous one"),
        Bug("drop-no-wrap", "elif idx == current and current >= len(rest):", "elif idx == current and current > len(rest):",
            ["drop(['a', 'b', 'c'], 'c', 2)"], "drop", "the turn index points past the end when the last combatant leaves"),
    ],
))

# ---------------------------------------------------------------------------------------------------------- chapters
add(Mod(
    key="chapters",
    title="chapters: podcast chapter lists",
    blurb="The podcast publishing tool reads hand-written chapter lists with the `chapters` helpers.",
    names=["parse_stamp", "parse_chapters", "chapter_at", "format_stamp"],
    spec=dd('''
        # chapters: podcast chapter lists

        ## `parse_stamp(text) -> int`
        A timestamp in one of three shapes, returning **milliseconds**:

        * `S`: seconds only (`90`),
        * `M:SS`: minutes (any number of digits) and exactly two digits of seconds (`75:30`),
        * `H:MM:SS`: hours (any number of digits), exactly two digits of minutes and of seconds (`1:02:03`),

        each optionally followed by a fraction `.f` of one to three digits, read as a decimal fraction of a second
        (`.5` is 500 ms, `.05` is 50 ms, `.005` is 5 ms). Seconds must be below 60 whenever there is more than one
        component, and minutes below 60 in the `H:MM:SS` shape. Anything else (empty text, signs, spaces, four
        components, more than three fraction digits) is a `ValueError`.

        ## `parse_chapters(text, total_ms) -> list[dict]`
        Each line is blank, a comment (first non-blank character `#`) or `<stamp><spaces or tabs><title>`; the title is
        the rest of the line, trimmed. Result items are `{"start": ms, "end": ms, "title": str}` where a chapter ends
        where the next begins and the last one ends at `total_ms`.

        * The first chapter must start at 0; starts must be strictly increasing and below `total_ms`.
        * At least one chapter is required.
        * Every `ValueError` message begins with `line N:` (1-based, counting blank and comment lines) for problems
          tied to a line; "no chapters" has no line.

        ## `chapter_at(chapters, ms) -> dict | None`
        The chapter with `start <= ms < end`, or `None`.

        ## `format_stamp(ms) -> str`
        `H:MM:SS` when at least one hour, otherwise `M:SS`; milliseconds are dropped (truncated, never rounded).
        Negative input is a `ValueError`.
    '''),
    core=dd('''
        """Podcast chapter lists."""
        import re

        __all__ = ["parse_stamp", "parse_chapters", "chapter_at", "format_stamp"]


        def parse_stamp(text):
            m = re.fullmatch(r"([0-9]+(?::[0-9]{2}){0,2})(?:\\.([0-9]{1,3}))?", text)
            if not m:
                raise ValueError(f"bad timestamp {text!r}")
            parts = [int(p) for p in m.group(1).split(":")]
            if len(parts) >= 2 and parts[-1] >= 60:
                raise ValueError("seconds must be below 60")
            if len(parts) == 3 and parts[1] >= 60:
                raise ValueError("minutes must be below 60")
            secs = 0
            for p in parts:
                secs = secs * 60 + p
            frac = int(m.group(2).ljust(3, "0")) if m.group(2) else 0
            return secs * 1000 + frac


        def parse_chapters(text, total_ms):
            rows = []
            for no, raw in enumerate(text.splitlines(), start=1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.fullmatch(r"(\\S+)[ \\t]+(.+)", line)
                if not m:
                    raise ValueError(f"line {no}: expected '<timestamp> <title>'")
                try:
                    start = parse_stamp(m.group(1))
                except ValueError as e:
                    raise ValueError(f"line {no}: {e}") from None
                rows.append((no, start, m.group(2).strip()))
            if not rows:
                raise ValueError("no chapters")
            if rows[0][1] != 0:
                raise ValueError(f"line {rows[0][0]}: the first chapter must start at 0")
            out = []
            for i, (no, start, title) in enumerate(rows):
                if i and start <= rows[i - 1][1]:
                    raise ValueError(f"line {no}: starts must be strictly increasing")
                if start >= total_ms:
                    raise ValueError(f"line {no}: starts at or after the end")
                end = rows[i + 1][1] if i + 1 < len(rows) else total_ms
                out.append({"start": start, "end": end, "title": title})
            return out


        def chapter_at(chapters, ms):
            for c in chapters:
                if c["start"] <= ms < c["end"]:
                    return c
            return None


        def format_stamp(ms):
            if ms < 0:
                raise ValueError("negative time")
            s = ms // 1000
            h, rem = divmod(s, 3600)
            m, sec = divmod(rem, 60)
            return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
    '''),
    visible=dd('''
        from chapters import chapter_at, format_stamp, parse_chapters, parse_stamp

        TEXT = "0:00 Intro\\n4:30 Main story\\n# ads\\n52:10 Outro\\n"


        class VisibleTests(unittest.TestCase):
            def test_stamp(self):
                self.assertEqual(parse_stamp("1:02:03"), 3_723_000)

            def test_chapters(self):
                cs = parse_chapters(TEXT, 3_600_000)
                self.assertEqual([c["title"] for c in cs], ["Intro", "Main story", "Outro"])
                self.assertEqual(cs[0]["end"], 270_000)

            def test_chapter_at(self):
                cs = parse_chapters(TEXT, 3_600_000)
                self.assertEqual(chapter_at(cs, 300_000)["title"], "Main story")

            def test_format(self):
                self.assertEqual(format_stamp(75_000), "1:15")
    '''),
    hidden=dd('''
        import random
        from chapters import chapter_at, format_stamp, parse_chapters, parse_stamp


        class StampTests(unittest.TestCase):
            def test_shapes(self):
                cases = {"0": 0, "90": 90_000, "1:05": 65_000, "75:30": 4_530_000, "1:02:03": 3_723_000, "10:00:00": 36_000_000,
                         "0:00": 0, "100:00:00": 360_000_000, "59:59": 3_599_000, "1:59:59": 7_199_000}
                for text, ms in cases.items():
                    self.assertEqual(parse_stamp(text), ms, text)

            def test_fractions(self):
                self.assertEqual(parse_stamp("1.5"), 1500)
                self.assertEqual(parse_stamp("0:01.05"), 1050)
                self.assertEqual(parse_stamp("0:01.005"), 1005)
                self.assertEqual(parse_stamp("0:01.250"), 1250)
                self.assertEqual(parse_stamp("2:00:00.9"), 7_200_900)
                self.assertEqual(parse_stamp("5.050"), 5050)

            def test_limits(self):
                bad = ["", " ", "1:60", "1:5", "1:2:03", "1:60:00", "1:00:60", "1:02:03:04", "-1", "+1", "1 :00", " 1:00", "1:00 ",
                       "1.5555", "1.", ".5", "1:00.", "a", "1:0a", "0:00,5"]
                for text in bad:
                    with self.assertRaises(ValueError, msg=repr(text)):
                        parse_stamp(text)

            def test_limit_edges_pass(self):
                self.assertEqual(parse_stamp("0:59"), 59_000)
                self.assertEqual(parse_stamp("1:59:59"), 7_199_000)
                self.assertEqual(parse_stamp("120:59"), 7_259_000)


        class ChapterTests(unittest.TestCase):
            TEXT = "0:00 Intro\\n  # an indented comment\\n\\n4:30\\tMain story  \\n52:10   Outro and credits\\n"

            def test_parse(self):
                cs = parse_chapters(self.TEXT, 3_600_000)
                self.assertEqual(cs, [
                    {"start": 0, "end": 270_000, "title": "Intro"},
                    {"start": 270_000, "end": 3_130_000, "title": "Main story"},
                    {"start": 3_130_000, "end": 3_600_000, "title": "Outro and credits"},
                ])

            def test_last_chapter_ends_at_total(self):
                cs = parse_chapters("0:00 A\\n0:10 B", 25_000)
                self.assertEqual([c["end"] for c in cs], [10_000, 25_000])

            def assertLine(self, text, total, line):
                with self.assertRaises(ValueError) as cm:
                    parse_chapters(text, total)
                self.assertTrue(str(cm.exception).startswith(f"line {line}:"), str(cm.exception))

            def test_error_lines(self):
                self.assertLine("0:00 A\\n\\n# c\\nbad stamp here\\n", 100_000, 4)
                self.assertLine("\\n0:05 A\\n", 100_000, 2)
                self.assertLine("0:00 A\\n0:10 B\\n0:10 C\\n", 100_000, 3)
                self.assertLine("0:00 A\\n0:10 B\\n0:05 C\\n", 100_000, 3)
                self.assertLine("0:00 A\\n\\n0:100 B\\n", 100_000, 3)
                self.assertLine("0:00 A\\n1:40 B\\n", 100_000, 2)
                self.assertLine("0:00\\n", 100_000, 1)
                self.assertLine("0:00 A\\n0:30 B\\n9:99 C", 100_000, 3)

            def test_equal_starts_rejected_but_adjacent_ok(self):
                parse_chapters("0:00 A\\n0:01 B", 100_000)
                with self.assertRaises(ValueError):
                    parse_chapters("0:00 A\\n0:01 B\\n0:01 C", 100_000)

            def test_no_chapters(self):
                for text in ("", "\\n\\n", "# only a comment\\n   # another\\n"):
                    with self.assertRaises(ValueError):
                        parse_chapters(text, 1000)

            def test_first_must_be_zero(self):
                with self.assertRaises(ValueError):
                    parse_chapters("0:01 A", 1000 * 60)

            def test_start_below_total(self):
                parse_chapters("0:00 A\\n0:09 B", 10_000)
                with self.assertRaises(ValueError):
                    parse_chapters("0:00 A\\n0:10 B", 10_000)

            def test_chapter_at_boundaries(self):
                cs = parse_chapters("0:00 A\\n0:10 B", 25_000)
                self.assertEqual(chapter_at(cs, 0)["title"], "A")
                self.assertEqual(chapter_at(cs, 9_999)["title"], "A")
                self.assertEqual(chapter_at(cs, 10_000)["title"], "B")
                self.assertEqual(chapter_at(cs, 24_999)["title"], "B")
                self.assertIsNone(chapter_at(cs, 25_000))
                self.assertIsNone(chapter_at(cs, -1))

            def test_format(self):
                self.assertEqual(format_stamp(0), "0:00")
                self.assertEqual(format_stamp(999), "0:00")
                self.assertEqual(format_stamp(59_999), "0:59")
                self.assertEqual(format_stamp(1_500), "0:01")
                self.assertEqual(format_stamp(1_999), "0:01")
                self.assertEqual(format_stamp(3_599_999), "59:59")
                self.assertEqual(format_stamp(3_600_000), "1:00:00")
                self.assertEqual(format_stamp(3_723_900), "1:02:03")
                self.assertEqual(format_stamp(360_000_000), "100:00:00")
                with self.assertRaises(ValueError):
                    format_stamp(-1)

            def test_roundtrip(self):
                rng = random.Random(1)
                for _ in range(100):
                    ms = rng.randint(0, 400_000_000)
                    self.assertEqual(parse_stamp(format_stamp(ms)), ms // 1000 * 1000)
    '''),
    bugs=[
        Bug("fraction-pad", 'int(m.group(2).ljust(3, "0"))', 'int(m.group(2).rjust(3, "0"))',
            ["parse_stamp('0:01.5')", "parse_stamp('2.25')"], "parse_stamp", "`.5` is read as 5 ms"),
        Bug("seconds-limit", "parts[-1] >= 60", "parts[-1] > 60", ["parse_stamp('1:60')"], "parse_stamp", "`1:60` is accepted"),
        Bug("minutes-limit", "len(parts) == 3 and parts[1] >= 60", "len(parts) == 3 and parts[1] > 60",
            ["parse_stamp('1:60:00')"], "parse_stamp", "`1:60:00` is accepted"),
        Bug("increasing-nonstrict", "if i and start <= rows[i - 1][1]:", "if i and start < rows[i - 1][1]:",
            ["parse_chapters('0:00 A\\n0:10 B\\n0:10 C', 100000)"], "parse_chapters", "two chapters may start at the same time"),
        Bug("last-end", "else total_ms\n", "else start\n", ["parse_chapters('0:00 A\\n0:10 B', 25000)"], "parse_chapters",
            "the last chapter has no length"),
        Bug("at-end-inclusive", 'if c["start"] <= ms < c["end"]:', 'if c["start"] <= ms <= c["end"]:',
            ["chapter_at(parse_chapters('0:00 A\\n0:10 B', 25000), 10000)['title']"], "chapter_at",
            "the boundary between two chapters belongs to the earlier one"),
        Bug("format-rounds", "s = ms // 1000", "s = round(ms / 1000)", ["format_stamp(1999)", "format_stamp(59_999)"], "format_stamp",
            "milliseconds are rounded instead of dropped"),
        Bug("indented-comment", 'line.startswith("#")', 'raw.startswith("#")',
            ["parse_chapters('0:00 A\\n  # note\\n0:10 B', 25000)"], "parse_chapters", "an indented comment is parsed as a chapter"),
        Bug("line-numbers-from-zero", "enumerate(text.splitlines(), start=1)", "enumerate(text.splitlines(), start=0)",
            ["parse_chapters('0:00 A\\nbad line\\n', 25000)"], "parse_chapters", "error messages count lines from 0"),
    ],
))
