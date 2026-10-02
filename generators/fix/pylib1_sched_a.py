"""Python libraries, theme time/money/scheduling (batch sched-a): shift pay, tide-window docking, crew duty limits,
meeting-room bookings."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# shiftroster: weekly pay for shift workers (statutory breaks, night differential, tiered and daily overtime)
# ======================================================================================================================

SR_README = dd('''
    # shiftroster

    Weekly pay for hourly shift workers. Instants are naive `datetime` objects (seconds are ignored); money is an
    `int` number of cents.

    ## Shifts (`shiftroster/shifts.py`)

    `Shift(start, end, break_min)`: `break_min` is the recorded unpaid break in minutes.

    * `statutory_break(duration)`: the minimum unpaid break for a shift of `duration` minutes: `45` when the shift
      is longer than 540 minutes, `30` when longer than 360, otherwise `0`.
    * `paid_span(shift)`: `(a, b)` in absolute minutes (`date.toordinal() * 1440 + hour * 60 + minute`) of the paid
      part. The unpaid break is `max(break_min, statutory_break(duration))` and is taken off the **end** of the shift,
      so `b = end - break` (and `b >= a`). A shift must end after it starts and last at most 24 hours; a negative
      `break_min` is a `ValueError`.
    * `night_minutes(a, b)`: how many minutes of the absolute range `[a, b)` fall between 22:00 and 06:00.
    * `week_of(dt)`: the Monday (a `date`) of the week holding `dt`.

    ## Pay (`shiftroster/pay.py`)

    All shifts of one week are processed in order of their start; a shift belongs to the week in which it **starts**
    (even if it runs past Sunday midnight). Shifts from different weeks or shifts that overlap (the next one starts
    before the previous one ends) are a `ValueError`.

    Every paid minute has a multiplier, counted in quarters of the base rate:

    * base: `4` (x1.0) for the first 40 paid hours (2400 minutes) of the week, `6` (x1.5) for the next 8 hours (up to
      2880 minutes) and `8` (x2.0) after that;
    * daily overtime: inside one shift, paid minutes after the first 600 (ten hours) have at least `6`;
    * night: `+1` quarter on every paid minute between 22:00 and 06:00.

    `week_breakdown(shifts)` returns a dict: `regular` (minutes whose base-or-daily multiplier is 4), `ot15` (6),
    `ot20` (8), `night` (paid minutes at night) and `quarters` (the sum of all minute multipliers, night included).
    No shifts give all zeros.

    `week_pay(rate, shifts)`: `rate` is cents per hour; the pay is `rate * quarters / 240` rounded half up to a cent
    (once, for the whole week).
''')

SR_SHIFTS = dd('''
    from collections import namedtuple
    from datetime import timedelta

    Shift = namedtuple("Shift", "start end break_min")

    NIGHT_FROM = 22 * 60
    NIGHT_TO = 6 * 60


    def minutes_of(dt):
        return dt.toordinal() * 1440 + dt.hour * 60 + dt.minute


    def statutory_break(duration):
        if duration > 540:
            return 45
        if duration > 360:
            return 30
        return 0


    def paid_span(shift):
        a, b = minutes_of(shift.start), minutes_of(shift.end)
        if b <= a:
            raise ValueError("a shift must end after it starts")
        if b - a > 1440:
            raise ValueError("a shift lasts at most 24 hours")
        if shift.break_min < 0:
            raise ValueError("negative break")
        unpaid = max(shift.break_min, statutory_break(b - a))
        return a, max(a, b - unpaid)


    def night_minutes(a, b):
        total = 0
        for day in range(a // 1440 - 1, b // 1440 + 1):
            lo = day * 1440 + NIGHT_FROM
            hi = (day + 1) * 1440 + NIGHT_TO
            total += max(0, min(b, hi) - max(a, lo))
        return total


    def week_of(dt):
        d = dt.date()
        return d - timedelta(days=d.weekday())
''')

SR_PAY = dd('''
    from .shifts import minutes_of, night_minutes, paid_span, week_of

    REGULAR_LIMIT = 2400
    OT15_LIMIT = 2880
    DAILY_LIMIT = 600


    def _tier(done):
        if done < REGULAR_LIMIT:
            return 4
        if done < OT15_LIMIT:
            return 6
        return 8


    def week_breakdown(shifts):
        out = {"regular": 0, "ot15": 0, "ot20": 0, "night": 0, "quarters": 0}
        ordered = sorted(shifts, key=lambda s: s.start)
        if not ordered:
            return out
        week = week_of(ordered[0].start)
        done = 0
        previous_end = None
        for shift in ordered:
            if week_of(shift.start) != week:
                raise ValueError("shifts belong to different weeks")
            a, b = paid_span(shift)
            if previous_end is not None and minutes_of(shift.start) < previous_end:
                raise ValueError("shifts overlap")
            previous_end = minutes_of(shift.end)
            length = b - a
            cuts = {0, length}
            for limit in (REGULAR_LIMIT, OT15_LIMIT):
                if 0 < limit - done < length:
                    cuts.add(limit - done)
            if length > DAILY_LIMIT:
                cuts.add(DAILY_LIMIT)
            points = sorted(cuts)
            for lo, hi in zip(points, points[1:]):
                q = _tier(done + lo)
                if lo >= DAILY_LIMIT:
                    q = max(q, 6)
                minutes = hi - lo
                night = night_minutes(a + lo, a + hi)
                key = {4: "regular", 6: "ot15", 8: "ot20"}[q]
                out[key] += minutes
                out["night"] += night
                out["quarters"] += minutes * q + night
            done += length
        return out


    def week_pay(rate, shifts):
        quarters = week_breakdown(shifts)["quarters"]
        return (2 * rate * quarters + 240) // 480
''')

SR_VISIBLE = dd('''
    import unittest
    from datetime import datetime

    from shiftroster.pay import week_breakdown
    from shiftroster.shifts import Shift, statutory_break


    class BasicTests(unittest.TestCase):
        def test_statutory_break(self):
            self.assertEqual(statutory_break(480), 30)

        def test_one_day_shift(self):
            shift = Shift(datetime(2025, 3, 3, 9), datetime(2025, 3, 3, 17), 0)
            got = week_breakdown([shift])
            self.assertEqual(got["regular"], 450)
            self.assertEqual(got["night"], 0)


    if __name__ == "__main__":
        unittest.main()
''')

SR_HIDDEN = dd('''
    import unittest
    from datetime import date, datetime

    from shiftroster.pay import week_breakdown, week_pay
    from shiftroster.shifts import Shift, night_minutes, paid_span, statutory_break, week_of


    def at(day, hh, mm=0):
        return datetime(2025, 3, day, hh, mm)  # Monday is the 3rd


    def shift(d1, h1, d2, h2, brk=0, m1=0, m2=0):
        return Shift(at(d1, h1, m1), at(d2, h2, m2), brk)


    A = datetime(2025, 3, 3).toordinal() * 1440  # midnight of Monday 3 March


    class Breaks(unittest.TestCase):
        def test_statutory(self):
            table = {0: 0, 1: 0, 360: 0, 361: 30, 540: 30, 541: 45, 1440: 45}
            for minutes, brk in table.items():
                self.assertEqual(statutory_break(minutes), brk, minutes)

        def test_paid_span(self):
            self.assertEqual(paid_span(shift(3, 9, 3, 17)), (A + 540, A + 990))
            self.assertEqual(paid_span(shift(3, 9, 3, 15)), (A + 540, A + 900))
            self.assertEqual(paid_span(shift(3, 9, 3, 15, m2=1)), (A + 540, A + 871))
            self.assertEqual(paid_span(shift(3, 8, 3, 19)), (A + 480, A + 1140 - 45))

        def test_recorded_break_wins_when_longer(self):
            self.assertEqual(paid_span(shift(3, 9, 3, 17, brk=60)), (A + 540, A + 960))
            self.assertEqual(paid_span(shift(3, 9, 3, 17, brk=20)), (A + 540, A + 990))
            self.assertEqual(paid_span(shift(3, 9, 3, 12, brk=15)), (A + 540, A + 705))

        def test_short_shift_and_huge_break(self):
            self.assertEqual(paid_span(shift(3, 9, 3, 10, brk=90)), (A + 540, A + 540))

        def test_errors(self):
            with self.assertRaises(ValueError):
                paid_span(shift(3, 9, 3, 9))
            with self.assertRaises(ValueError):
                paid_span(shift(3, 10, 3, 9))
            with self.assertRaises(ValueError):
                paid_span(shift(3, 9, 4, 9, m2=1))
            with self.assertRaises(ValueError):
                paid_span(shift(3, 9, 3, 12, brk=-1))
            paid_span(shift(3, 9, 4, 9))

        def test_week_of(self):
            self.assertEqual(week_of(at(3, 0)), date(2025, 3, 3))
            self.assertEqual(week_of(at(9, 23, 59)), date(2025, 3, 3))
            self.assertEqual(week_of(at(10, 0)), date(2025, 3, 10))
            self.assertEqual(week_of(datetime(2025, 3, 1, 12)), date(2025, 2, 24))


    class Night(unittest.TestCase):
        def test_ranges(self):
            self.assertEqual(night_minutes(A + 600, A + 900), 0)
            self.assertEqual(night_minutes(A + 1320, A + 1440), 120)
            self.assertEqual(night_minutes(A + 1319, A + 1321), 1)
            self.assertEqual(night_minutes(A + 0, A + 360), 360)
            self.assertEqual(night_minutes(A + 359, A + 361), 1)
            self.assertEqual(night_minutes(A + 1300, A + 1440 + 400), 120 + 360)
            self.assertEqual(night_minutes(A + 300, A + 1500), 60 + 120 + 60)

        def test_long_range(self):
            self.assertEqual(night_minutes(A, A + 1440), 360 + 120)
            self.assertEqual(night_minutes(A, A + 3 * 1440), 3 * 480)
            self.assertEqual(night_minutes(A + 600, A + 600 + 1440), 480)

        def test_empty(self):
            self.assertEqual(night_minutes(A + 1400, A + 1400), 0)
            self.assertEqual(night_minutes(A + 1400, A + 1300), 0)


    class Breakdown(unittest.TestCase):
        def test_empty(self):
            self.assertEqual(week_breakdown([]), {"regular": 0, "ot15": 0, "ot20": 0, "night": 0, "quarters": 0})

        def test_one_day(self):
            self.assertEqual(week_breakdown([shift(3, 9, 3, 17)]), {"regular": 450, "ot15": 0, "ot20": 0, "night": 0, "quarters": 1800})

        def test_night_shift_across_midnight(self):
            got = week_breakdown([shift(3, 20, 4, 4)])
            # 8 hours: 30 minutes statutory break at the end -> 20:00 to 03:30 paid = 450 minutes; night from 22:00 = 330
            self.assertEqual(got, {"regular": 450, "ot15": 0, "ot20": 0, "night": 330, "quarters": 450 * 4 + 330})

        def test_night_only_inside_the_paid_part(self):
            got = week_breakdown([shift(3, 22, 4, 6)])
            self.assertEqual(got["night"], 450)
            got = week_breakdown([shift(3, 21, 4, 5, brk=60)])
            # 8 hours with a 60 minute break at the end: 21:00 to 04:00 is paid, 22:00 to 04:00 of it at night
            self.assertEqual(got["regular"], 420)
            self.assertEqual(got["night"], 360)

        def test_weekly_tiers(self):
            days = [shift(d, 8, d, 18, brk=0) for d in (3, 4, 5, 6)]  # four 10 hour shifts, 45 minute break -> 555 paid
            got = week_breakdown(days)
            self.assertEqual(got["regular"], 4 * 555)
            self.assertEqual(got["ot15"], 0)
            fifth = days + [shift(7, 8, 7, 18)]
            got = week_breakdown(fifth)
            self.assertEqual(got["regular"], 2400)
            self.assertEqual(got["ot15"], 5 * 555 - 2400)
            self.assertEqual(got["quarters"], 2400 * 4 + (5 * 555 - 2400) * 6)

        def test_second_overtime_tier(self):
            days = [shift(d, 8, d, 18) for d in (3, 4, 5, 6, 7)] + [shift(8, 8, 8, 18)]
            got = week_breakdown(days)
            self.assertEqual(got["regular"], 2400)
            self.assertEqual(got["ot15"], 480)
            self.assertEqual(got["ot20"], 6 * 555 - 2880)
            self.assertEqual(got["quarters"], 2400 * 4 + 480 * 6 + (6 * 555 - 2880) * 8)

        def test_tier_boundary_inside_a_shift(self):
            # four shifts of 600 paid minutes (645 on the clock) -> 2400 exactly; the fifth starts in overtime
            days = [shift(d, 6, d, 16, m2=45) for d in (3, 4, 5, 6)]
            self.assertEqual(sum(paid_span(s)[1] - paid_span(s)[0] for s in days), 4 * 600)
            got = week_breakdown(days)
            self.assertEqual(got["regular"], 2400)
            self.assertEqual(got["ot15"], 0)
            got = week_breakdown(days + [shift(7, 6, 7, 10)])
            self.assertEqual(got["ot15"], 240)
            self.assertEqual(got["ot20"], 0)

        def test_daily_overtime(self):
            got = week_breakdown([shift(3, 6, 3, 18, m2=0)])
            # 12 hours -> 45 minutes break -> 675 paid; the 75 after the first 600 count x1.5
            self.assertEqual(got["regular"], 600)
            self.assertEqual(got["ot15"], 75)
            self.assertEqual(got["quarters"], 600 * 4 + 75 * 6)

        def test_daily_overtime_boundary(self):
            exact = week_breakdown([shift(3, 6, 3, 16, m2=45)])
            self.assertEqual((exact["regular"], exact["ot15"]), (600, 0))
            over = week_breakdown([shift(3, 6, 3, 16, m2=46)])
            self.assertEqual((over["regular"], over["ot15"]), (600, 1))

        def test_daily_overtime_never_lowers_a_weekly_tier(self):
            days = [shift(d, 6, d, 16, m2=45) for d in (3, 4, 5, 6)] + [shift(7, 6, 7, 18)]
            got = week_breakdown(days)
            # the fifth shift pays 675 minutes: 480 more at x1.5 to reach 48 hours, then 195 at x2.0 (also past its 600th)
            self.assertEqual(got["regular"], 2400)
            self.assertEqual(got["ot15"], 480)
            self.assertEqual(got["ot20"], 195)
            self.assertEqual(got["quarters"], 2400 * 4 + 480 * 6 + 195 * 8)

        def test_night_overtime_stacks(self):
            days = [shift(d, 6, d, 16, m2=45) for d in (3, 4, 5, 6)] + [shift(7, 20, 8, 2)]
            got = week_breakdown(days)
            # fifth shift: 6 hours, no statutory break -> 360 paid, 240 of them (22:00-02:00) at night, all at x1.5
            self.assertEqual(got["ot15"], 360)
            self.assertEqual(got["night"], 240)
            self.assertEqual(got["quarters"], 2400 * 4 + 360 * 6 + 240)

        def test_input_order_does_not_matter(self):
            days = [shift(d, 8, d, 18) for d in (3, 4, 5, 6, 7)]
            self.assertEqual(week_breakdown(list(reversed(days))), week_breakdown(days))

        def test_shift_belongs_to_the_week_it_starts_in(self):
            sunday = Shift(datetime(2025, 3, 9, 20), datetime(2025, 3, 10, 4), 0)
            got = week_breakdown([sunday])
            self.assertEqual(got["regular"], 450)
            self.assertEqual(got["night"], 330)

        def test_different_weeks_are_an_error(self):
            with self.assertRaises(ValueError):
                week_breakdown([shift(9, 8, 9, 12), shift(10, 8, 10, 12)])

        def test_overlap_is_an_error(self):
            with self.assertRaises(ValueError):
                week_breakdown([shift(3, 8, 3, 12), shift(3, 11, 3, 15)])
            week_breakdown([shift(3, 8, 3, 12), shift(3, 12, 3, 15)])

        def test_bad_shift(self):
            with self.assertRaises(ValueError):
                week_breakdown([shift(3, 12, 3, 8)])


    class Pay(unittest.TestCase):
        def test_simple(self):
            self.assertEqual(week_pay(1800, [shift(3, 9, 3, 17)]), 13_500)
            self.assertEqual(week_pay(1800, []), 0)

        def test_rounding_half_up(self):
            # 1 paid minute at 3000 cents/hour = 50 cents ; at 30 cents/hour = 0.5 cents
            self.assertEqual(week_pay(30, [shift(3, 9, 3, 10, brk=59)]), 1)
            self.assertEqual(week_pay(29, [shift(3, 9, 3, 10, brk=59)]), 0)
            self.assertEqual(week_pay(3000, [shift(3, 9, 3, 10, brk=59)]), 50)
            self.assertEqual(week_pay(31, [shift(3, 9, 3, 10, brk=58)]), 1)

        def test_rounding_happens_once_for_the_week(self):
            tiny = [shift(d, 9, d, 10, brk=59) for d in (3, 4, 5)]
            self.assertEqual(week_pay(30, tiny), 2)
            self.assertEqual(week_pay(20, tiny), 1)

        def test_with_overtime_and_night(self):
            days = [shift(d, 6, d, 16, m2=45) for d in (3, 4, 5, 6)] + [shift(7, 20, 8, 2)]
            # 12 000 quarters in total, i.e. exactly 50 hours-equivalents of the base rate
            self.assertEqual(week_pay(2000, days), 100_000)
            self.assertEqual(week_pay(1234, days), 61_700)


    if __name__ == "__main__":
        unittest.main()
''')

SHIFTROSTER = Lib(
    name="shiftroster", lang="python", title="the shift-pay calculator (`shiftroster/`)",
    blurb="The staffing office computes a shift worker's weekly pay, with breaks, night work and overtime, using shiftroster.",
    files={"shiftroster/__init__.py": "", "shiftroster/shifts.py": SR_SHIFTS, "shiftroster/pay.py": SR_PAY,
           "README.md": SR_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": SR_VISIBLE},
    hidden_tests={"tests/test_full.py": SR_HIDDEN},
    mutate=["shiftroster/shifts.py", "shiftroster/pay.py"], difficulty=4, tags=["payroll", "overtime", "shifts"],
    probes=[
        "statutory_break(360)", "statutory_break(361)", "statutory_break(541)",
        "night_minutes(1319, 1321)", "night_minutes(1300, 1840)", "night_minutes(300, 1500)",
        "paid_span(Shift(datetime(2025, 3, 3, 9), datetime(2025, 3, 3, 15, 1), 0))[1] - paid_span(Shift(datetime(2025, 3, 3, 9), datetime(2025, 3, 3, 15, 1), 0))[0]",
        "week_breakdown([Shift(datetime(2025, 3, 3, 20), datetime(2025, 3, 4, 4), 0)])",
        "week_breakdown([Shift(datetime(2025, 3, 3, 6), datetime(2025, 3, 3, 18), 0)])",
        "week_breakdown([Shift(datetime(2025, 3, 3 + d, 6), datetime(2025, 3, 3 + d, 16, 45), 0) for d in range(5)])",
        "week_pay(30, [Shift(datetime(2025, 3, 3, 9), datetime(2025, 3, 3, 10), 59)])",
        "week_pay(1800, [Shift(datetime(2025, 3, 3, 9), datetime(2025, 3, 3, 17), 0)])",
    ],
    probe_import="from datetime import datetime\nfrom shiftroster.shifts import *\nfrom shiftroster.pay import *",
)

# ======================================================================================================================
# tidedock: single-berth scheduling inside tide windows
# ======================================================================================================================

TD_README = dd('''
    # tidedock

    Berth planning for a tidal harbour. Times are whole minutes from the start of the planning day; heights are whole
    centimetres.

    ## Tide (`tidedock/tide.py`)

    A tide table is a list of `(minute, height)` turning points with strictly increasing minutes (at least two
    points; anything else is a `ValueError`).

    * `height_at(table, t)`: the height at minute `t`, interpolated linearly between the two surrounding points and
      rounded **down** (`math.floor` of the exact value, so it also rounds down on a falling tide). `t` outside the
      table's first and last minute (both included) is a `ValueError`.
    * `windows(table, min_height, start, end)`: the maximal runs `(a, b)` of consecutive minutes `a <= t < b` inside
      `[start, end)` at which the table covers `t` and `height_at(table, t) >= min_height`. Minutes the table does
      not cover never qualify. Runs are ordered by time.
    * `needed_tide(draft, chart_depth, clearance=50)`: the tide height a ship needs at the berth: its draft plus the
      clearance, minus the charted depth of the berth (`draft + clearance - chart_depth`).

    ## Plan (`tidedock/plan.py`)

    `Ship(name, draft, arrival, duration)` (minutes; `duration` must be positive, otherwise `ValueError`).

    `schedule(ships, table, chart_depth, horizon_end, clearance=50)` serves one berth. Ships are served in order of
    arrival (ties: the larger draft first, then the name). A ship gets the earliest start `s` with
    `s >= max(arrival, time the berth becomes free)` such that all minutes of `[s, s + duration)` have at least the
    needed tide and `s + duration <= horizon_end`. The berth is then busy until `s + duration`. A ship that finds no
    such start is skipped (it does not block the berth). Returns `(plan, skipped)`: `plan` is a list of
    `(name, start, end)` in service order, `skipped` the names of the skipped ships in service order.

    `total_wait(plan, ships)`: the sum over the planned ships of `start - arrival`.
''')

TD_TIDE = dd('''
    def _check(table):
        if len(table) < 2:
            raise ValueError("a tide table needs at least two points")
        for (t0, _), (t1, _) in zip(table, table[1:]):
            if t1 <= t0:
                raise ValueError("tide table minutes must increase")


    def height_at(table, t):
        _check(table)
        if t < table[0][0] or t > table[-1][0]:
            raise ValueError("minute outside the tide table")
        for (t0, h0), (t1, h1) in zip(table, table[1:]):
            if t0 <= t <= t1:
                return h0 + (h1 - h0) * (t - t0) // (t1 - t0)


    def windows(table, min_height, start, end):
        _check(table)
        out = []
        first = None
        for t in range(start, end):
            covered = table[0][0] <= t <= table[-1][0]
            ok = covered and height_at(table, t) >= min_height
            if ok and first is None:
                first = t
            elif not ok and first is not None:
                out.append((first, t))
                first = None
        if first is not None:
            out.append((first, end))
        return out


    def needed_tide(draft, chart_depth, clearance=50):
        return draft + clearance - chart_depth
''')

TD_PLAN = dd('''
    from collections import namedtuple

    from .tide import needed_tide, windows

    Ship = namedtuple("Ship", "name draft arrival duration")


    def schedule(ships, table, chart_depth, horizon_end, clearance=50):
        for ship in ships:
            if ship.duration <= 0:
                raise ValueError("duration must be positive")
        order = sorted(ships, key=lambda s: (s.arrival, -s.draft, s.name))
        free_at = 0
        plan = []
        skipped = []
        for ship in order:
            need = needed_tide(ship.draft, chart_depth, clearance)
            earliest = max(ship.arrival, free_at)
            start = None
            for a, b in windows(table, need, earliest, horizon_end):
                if b - a >= ship.duration:
                    start = a
                    break
            if start is None:
                skipped.append(ship.name)
                continue
            plan.append((ship.name, start, start + ship.duration))
            free_at = start + ship.duration
        return plan, skipped


    def total_wait(plan, ships):
        arrival = {s.name: s.arrival for s in ships}
        return sum(start - arrival[name] for name, start, _ in plan)
''')

TD_VISIBLE = dd('''
    import unittest

    from tidedock.plan import Ship, schedule
    from tidedock.tide import height_at, needed_tide, windows

    TABLE = [(0, 100), (360, 500), (720, 80), (1080, 520), (1440, 90)]


    class BasicTests(unittest.TestCase):
        def test_height_midway(self):
            self.assertEqual(height_at(TABLE, 180), 300)

        def test_needed(self):
            self.assertEqual(needed_tide(500, 250), 300)

        def test_first_window(self):
            self.assertEqual(windows(TABLE, 300, 0, 600)[0], (180, 532))

        def test_single_ship(self):
            plan, skipped = schedule([Ship("Gannet", 500, 100, 120)], TABLE, 250, 1440)
            self.assertEqual(plan, [("Gannet", 180, 300)])
            self.assertEqual(skipped, [])


    if __name__ == "__main__":
        unittest.main()
''')

TD_HIDDEN = dd('''
    import unittest

    from tidedock.plan import Ship, schedule, total_wait
    from tidedock.tide import height_at, needed_tide, windows

    TABLE = [(0, 100), (360, 500), (720, 80), (1080, 520), (1440, 90)]


    class Height(unittest.TestCase):
        def test_turning_points(self):
            for t, h in TABLE:
                self.assertEqual(height_at(TABLE, t), h, t)

        def test_rising(self):
            self.assertEqual(height_at(TABLE, 180), 300)
            self.assertEqual(height_at(TABLE, 1), 101)
            self.assertEqual(height_at(TABLE, 359), 498)
            self.assertEqual(height_at(TABLE, 721), 81)
            self.assertEqual(height_at(TABLE, 900), 300)

        def test_falling_rounds_down(self):
            self.assertEqual(height_at(TABLE, 361), 498)   # 500 - 1.17 -> 498.83 -> 498
            self.assertEqual(height_at(TABLE, 540), 290)
            self.assertEqual(height_at(TABLE, 1081), 518)  # 520 - 1.19 -> 518.81 -> 518
            self.assertEqual(height_at(TABLE, 1439), 91)  # 520 - 428.8 = 91.2 -> 91

        def test_outside(self):
            for t in (-1, 1441, 5000):
                with self.assertRaises(ValueError):
                    height_at(TABLE, t)

        def test_bad_tables(self):
            for table in ([], [(0, 100)], [(0, 100), (0, 200)], [(0, 100), (50, 200), (40, 100)]):
                with self.assertRaises(ValueError, msg=table):
                    height_at(table, 0)
                with self.assertRaises(ValueError, msg=table):
                    windows(table, 0, 0, 10)

        def test_two_point_table(self):
            self.assertEqual(height_at([(10, 0), (20, 100)], 15), 50)
            self.assertEqual(height_at([(10, 0), (20, 100)], 10), 0)
            self.assertEqual(height_at([(10, 0), (20, 100)], 20), 100)


    class Windows(unittest.TestCase):
        def test_both_high_tides(self):
            self.assertEqual(windows(TABLE, 300, 0, 1440), [(180, 532), (900, 1265)])

        def test_clipped_to_range(self):
            self.assertEqual(windows(TABLE, 300, 200, 1000), [(200, 532), (900, 1000)])
            self.assertEqual(windows(TABLE, 300, 0, 180), [])
            self.assertEqual(windows(TABLE, 300, 0, 181), [(180, 181)])
            self.assertEqual(windows(TABLE, 300, 531, 532), [(531, 532)])
            self.assertEqual(windows(TABLE, 300, 532, 533), [])

        def test_high_threshold(self):
            self.assertEqual(windows(TABLE, 500, 0, 1440), [(360, 361), (1064, 1097)])
            self.assertEqual(windows(TABLE, 1000, 0, 1440), [])

        def test_uncovered_minutes_never_qualify(self):
            self.assertEqual(windows(TABLE, 0, 0, 1500), [(0, 1441)])
            self.assertEqual(windows(TABLE, 0, -10, 20), [(0, 20)])
            self.assertEqual(windows(TABLE, 0, 1441, 1500), [])
            self.assertEqual(windows(TABLE, 0, -30, -5), [])

        def test_threshold_is_inclusive(self):
            self.assertEqual(windows(TABLE, 100, 0, 3), [(0, 3)])
            self.assertEqual(windows(TABLE, 101, 0, 3), [(1, 3)])

        def test_empty_range(self):
            self.assertEqual(windows(TABLE, 0, 100, 100), [])
            self.assertEqual(windows(TABLE, 0, 100, 50), [])

        def test_matches_pointwise_check(self):
            for need in (50, 150, 300, 450):
                got = windows(TABLE, need, 0, 1441)
                inside = {t for a, b in got for t in range(a, b)}
                self.assertEqual(inside, {t for t in range(0, 1441) if height_at(TABLE, t) >= need}, need)
                for (a1, b1), (a2, b2) in zip(got, got[1:]):
                    self.assertLess(b1, a2)

        def test_needed_tide(self):
            self.assertEqual(needed_tide(500, 250), 300)
            self.assertEqual(needed_tide(500, 250, 0), 250)
            self.assertEqual(needed_tide(200, 250), 0)
            self.assertEqual(needed_tide(400, 500, 100), 0)
            self.assertEqual(needed_tide(300, 100, 20), 220)


    class Schedule(unittest.TestCase):
        def test_sequence(self):
            ships = [Ship("Heron", 500, 150, 300), Ship("Gannet", 500, 100, 120), Ship("Wren", 200, 0, 60)]
            plan, skipped = schedule(ships, TABLE, 250, 1440)
            self.assertEqual(plan, [("Wren", 0, 60), ("Gannet", 180, 300), ("Heron", 900, 1200)])
            self.assertEqual(skipped, [])
            self.assertEqual(total_wait(plan, ships), 0 + 80 + 750)

        def test_ties_larger_draft_then_name(self):
            ships = [Ship("Mid", 300, 50, 30), Ship("Zeal", 400, 50, 30), Ship("Alba", 400, 50, 30)]
            plan, skipped = schedule(ships, TABLE, 250, 1440)
            self.assertEqual(plan, [("Alba", 90, 120), ("Zeal", 120, 150), ("Mid", 150, 180)])

        def test_berth_busy_until_end(self):
            ships = [Ship("A", 200, 0, 100), Ship("B", 200, 10, 100)]
            plan, _ = schedule(ships, TABLE, 250, 1440)
            self.assertEqual(plan, [("A", 0, 100), ("B", 100, 200)])

        def test_arrival_is_respected(self):
            plan, _ = schedule([Ship("A", 200, 77, 10)], TABLE, 250, 1440)
            self.assertEqual(plan, [("A", 77, 87)])

        def test_window_length_boundary(self):
            plan, skipped = schedule([Ship("Plover", 560, 0, 247)], TABLE, 250, 1440)
            self.assertEqual((plan, skipped), ([("Plover", 234, 481)], []))
            plan, skipped = schedule([Ship("Plover", 560, 0, 248)], TABLE, 250, 1440)
            self.assertEqual((plan, skipped), ([("Plover", 950, 1198)], []))

        def test_skipped_ship_does_not_block_the_berth(self):
            ships = [Ship("Plover", 560, 0, 300), Ship("Wren", 200, 10, 20)]
            plan, skipped = schedule(ships, TABLE, 250, 1440)
            self.assertEqual(plan, [("Wren", 10, 30)])
            self.assertEqual(skipped, ["Plover"])

        def test_horizon(self):
            ship = [Ship("Plover", 560, 0, 247)]
            self.assertEqual(schedule(ship, TABLE, 250, 481), ([("Plover", 234, 481)], []))
            self.assertEqual(schedule(ship, TABLE, 250, 480), ([], ["Plover"]))

        def test_late_arrival_misses_the_first_window(self):
            plan, _ = schedule([Ship("Gannet", 500, 412, 120)], TABLE, 250, 1440)
            self.assertEqual(plan, [("Gannet", 412, 532)])
            plan, _ = schedule([Ship("Gannet", 500, 413, 120)], TABLE, 250, 1440)
            self.assertEqual(plan, [("Gannet", 900, 1020)])

        def test_started_inside_a_window(self):
            plan, _ = schedule([Ship("Gannet", 500, 200, 100)], TABLE, 250, 1440)
            self.assertEqual(plan, [("Gannet", 200, 300)])

        def test_clearance(self):
            ships = [Ship("Gannet", 500, 0, 100)]
            plan, _ = schedule(ships, TABLE, 250, 1440, clearance=0)
            self.assertEqual(plan, [("Gannet", 135, 235)])

        def test_empty(self):
            self.assertEqual(schedule([], TABLE, 250, 1440), ([], []))
            self.assertEqual(total_wait([], []), 0)

        def test_bad_duration(self):
            with self.assertRaises(ValueError):
                schedule([Ship("A", 200, 0, 0)], TABLE, 250, 1440)
            with self.assertRaises(ValueError):
                schedule([Ship("A", 200, 0, -5), Ship("B", 200, 0, 5)], TABLE, 250, 1440)

        def test_input_is_not_modified(self):
            ships = [Ship("B", 200, 10, 5), Ship("A", 200, 0, 5)]
            schedule(ships, TABLE, 250, 1440)
            self.assertEqual([s.name for s in ships], ["B", "A"])

        def test_total_wait(self):
            ships = [Ship("A", 200, 0, 100), Ship("B", 200, 10, 100), Ship("C", 560, 0, 400)]
            plan, skipped = schedule(ships, TABLE, 250, 1440)
            self.assertEqual(skipped, ["C"])
            self.assertEqual(total_wait(plan, ships), 0 + 90)


    if __name__ == "__main__":
        unittest.main()
''')

TIDEDOCK = Lib(
    name="tidedock", lang="python", title="the tidal berth planner (`tidedock/`)",
    blurb="The harbour master plans which deep-draught ships may use the berth and when, given the tide table, with tidedock.",
    files={"tidedock/__init__.py": "", "tidedock/tide.py": TD_TIDE, "tidedock/plan.py": TD_PLAN,
           "README.md": TD_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": TD_VISIBLE},
    hidden_tests={"tests/test_full.py": TD_HIDDEN},
    mutate=["tidedock/tide.py", "tidedock/plan.py"], difficulty=4, tags=["tides", "scheduling", "windows"],
    probes=[
        "height_at([(0, 100), (360, 500), (720, 80), (1080, 520), (1440, 90)], 361)", "height_at([(0, 100), (360, 500), (720, 80), (1080, 520), (1440, 90)], 1081)", "height_at([(0, 100), (360, 500), (720, 80), (1080, 520), (1440, 90)], 1441)", "windows([(0, 100), (360, 500), (720, 80), (1080, 520), (1440, 90)], 300, 0, 1440)",
        "windows([(0, 100), (360, 500), (720, 80), (1080, 520), (1440, 90)], 500, 0, 1440)", "windows([(0, 100), (360, 500), (720, 80), (1080, 520), (1440, 90)], 0, -10, 20)", "windows([(0, 100), (360, 500), (720, 80), (1080, 520), (1440, 90)], 0, 0, 1500)", "needed_tide(500, 250)",
        "schedule([Ship('Gannet', 500, 100, 120), Ship('Wren', 200, 0, 60), Ship('Heron', 500, 150, 300)], [(0, 100), (360, 500), (720, 80), (1080, 520), (1440, 90)], 250, 1440)",
        "schedule([Ship('Plover', 560, 0, 247)], [(0, 100), (360, 500), (720, 80), (1080, 520), (1440, 90)], 250, 1440)", "schedule([Ship('Plover', 560, 0, 248)], [(0, 100), (360, 500), (720, 80), (1080, 520), (1440, 90)], 250, 1440)",
        "schedule([Ship('Plover', 560, 0, 247)], [(0, 100), (360, 500), (720, 80), (1080, 520), (1440, 90)], 250, 480)",
        "schedule([Ship('Mid', 300, 50, 30), Ship('Zeal', 400, 50, 30), Ship('Alba', 400, 50, 30)], [(0, 100), (360, 500), (720, 80), (1080, 520), (1440, 90)], 250, 1440)[0]",
    ],
    probe_import="from tidedock.tide import *\nfrom tidedock.plan import *",
)

# ======================================================================================================================
# crewrest: duty-time and rest limits for a flight crew
# ======================================================================================================================

CR_README = dd('''
    # crewrest

    Duty-limit checks for an airline crew-planning tool. A duty is a `(start, end)` pair of whole minutes on one
    absolute time line (minute `0` is some Monday midnight). A list of duties is **valid** when every duty has
    `end > start`, they are sorted by start and no duty starts before the previous one ends (touching is allowed);
    anything else is a `ValueError` in every function below.

    ## Limits (`crewrest/limits.py`)

    * A duty may last at most `780` minutes.
    * `required_rest(length)`: the rest needed after a duty of `length` minutes: `720` minutes after a duty longer than
      `600`, otherwise `600`.
    * In any `10080`-minute (7 day) window the duty minutes add up to at most `3600`; in any `40320`-minute (28 day)
      window at most `11400`.
    * No more than `6` duties in a row without a long break: a break of at least `1800` minutes between two duties
      starts a new run.

    `window_total(duties, end, window)`: the duty minutes inside `[end - window, end)` (duties are clipped to the
    window).

    `violations(duties)`: a sorted list of `(index, code)` pairs, one for each broken rule at each duty:

    * `"duty-too-long"`: the duty is longer than 780 minutes;
    * `"short-rest"`: the gap since the end of the previous duty is shorter than `required_rest(previous length)`;
    * `"weekly-cap"`: `window_total(duties, end of this duty, 10080)` exceeds 3600;
    * `"monthly-cap"`: `window_total(duties, end of this duty, 40320)` exceeds 11400;
    * `"no-break"`: this duty is the 7th or later duty of its run.

    The list is sorted by index, then by code (alphabetically).

    `earliest_next_start(duties, length)`: the earliest minute at which a further duty of `length` minutes could start
    so that it respects the rest rule after the last duty (`0` is the lower bound when there are no duties), and
    after it ends neither the 7-day nor the 28-day cap would be exceeded (it looks at minutes one by one). `length`
    must be between 1 and 780, otherwise `ValueError`. (The 7-duty run rule is not considered here.)
''')

CR_LIMITS = dd('''
    MAX_DUTY = 780
    LONG_DUTY = 600
    REST_SHORT = 600
    REST_LONG = 720
    WEEK = 10_080
    WEEK_CAP = 3_600
    MONTH = 40_320
    MONTH_CAP = 11_400
    BREAK_GAP = 1_800
    MAX_RUN = 6


    def required_rest(length):
        return REST_LONG if length > LONG_DUTY else REST_SHORT


    def validate(duties):
        previous_end = None
        for start, end in duties:
            if end <= start:
                raise ValueError("a duty must end after it starts")
            if previous_end is not None and start < previous_end:
                raise ValueError("duties must be sorted and must not overlap")
            previous_end = end


    def window_total(duties, end, window):
        low = end - window
        return sum(max(0, min(e, end) - max(s, low)) for s, e in duties)


    def violations(duties):
        validate(duties)
        found = []
        run = 0
        for i, (start, end) in enumerate(duties):
            if end - start > MAX_DUTY:
                found.append((i, "duty-too-long"))
            if i == 0:
                run = 1
            else:
                prev_start, prev_end = duties[i - 1]
                gap = start - prev_end
                if gap < required_rest(prev_end - prev_start):
                    found.append((i, "short-rest"))
                run = run + 1 if gap < BREAK_GAP else 1
            if run > MAX_RUN:
                found.append((i, "no-break"))
            if window_total(duties, end, WEEK) > WEEK_CAP:
                found.append((i, "weekly-cap"))
            if window_total(duties, end, MONTH) > MONTH_CAP:
                found.append((i, "monthly-cap"))
        return sorted(found)


    def earliest_next_start(duties, length):
        validate(duties)
        if not 1 <= length <= MAX_DUTY:
            raise ValueError("duty length out of range")
        start = 0
        if duties:
            last_start, last_end = duties[-1]
            start = last_end + required_rest(last_end - last_start)
        while True:
            end = start + length
            if (window_total(duties, end, WEEK) + length <= WEEK_CAP
                    and window_total(duties, end, MONTH) + length <= MONTH_CAP):
                return start
            start += 1
''')

CR_VISIBLE = dd('''
    import unittest

    from crewrest.limits import earliest_next_start, required_rest, violations


    class BasicTests(unittest.TestCase):
        def test_rest(self):
            self.assertEqual(required_rest(500), 600)

        def test_clean_roster(self):
            self.assertEqual(violations([(480, 1080), (1920, 2520)]), [])

        def test_next_start(self):
            self.assertEqual(earliest_next_start([(480, 1080)], 600), 1680)


    if __name__ == "__main__":
        unittest.main()
''')

CR_HIDDEN = dd('''
    import unittest

    from crewrest.limits import earliest_next_start, required_rest, validate, violations, window_total


    def duty(day, hour, length):
        start = day * 1440 + hour * 60
        return (start, start + length)


    class Rest(unittest.TestCase):
        def test_required_rest(self):
            table = {1: 600, 300: 600, 600: 600, 601: 720, 700: 720, 780: 720, 781: 720}
            for length, rest in table.items():
                self.assertEqual(required_rest(length), rest, length)


    class Validation(unittest.TestCase):
        def test_valid(self):
            validate([])
            validate([(0, 10)])
            validate([(0, 10), (10, 20)])

        def test_invalid(self):
            for duties in ([(5, 5)], [(10, 5)], [(10, 20), (0, 5)], [(0, 10), (9, 20)], [(0, 10), (5, 6)], [(0, 10), (10, 10)]):
                with self.assertRaises(ValueError, msg=duties):
                    validate(duties)
                with self.assertRaises(ValueError, msg=duties):
                    violations(duties)
                with self.assertRaises(ValueError, msg=duties):
                    earliest_next_start(duties, 100)


    class WindowTotal(unittest.TestCase):
        def test_totals(self):
            d = [(0, 600), (1440, 2040)]
            self.assertEqual(window_total(d, 2040, 10_080), 1200)
            self.assertEqual(window_total(d, 2040, 1440), 600)
            self.assertEqual(window_total(d, 1000, 500), 100)
            self.assertEqual(window_total(d, 600, 600), 600)
            self.assertEqual(window_total(d, 600, 599), 599)
            self.assertEqual(window_total(d, 1440, 840), 0)
            self.assertEqual(window_total(d, 1441, 842), 2)
            self.assertEqual(window_total(d, 1441, 841), 1)
            self.assertEqual(window_total(d, 100, 10_080), 100)
            self.assertEqual(window_total([], 100, 10), 0)

        def test_future_duties_do_not_count(self):
            d = [(0, 100), (500, 600)]
            self.assertEqual(window_total(d, 300, 1000), 100)
            self.assertEqual(window_total(d, 550, 1000), 150)


    class Violations(unittest.TestCase):
        def test_clean(self):
            self.assertEqual(violations([]), [])
            self.assertEqual(violations([duty(0, 8, 600), duty(1, 8, 600)]), [])

        def test_duty_length(self):
            self.assertEqual(violations([(0, 780)]), [])
            self.assertEqual(violations([(0, 781)]), [(0, "duty-too-long")])
            self.assertEqual(violations([duty(0, 8, 500), duty(2, 8, 900)]), [(1, "duty-too-long")])

        def test_rest_after_a_short_duty(self):
            self.assertEqual(violations([(0, 600), (1200, 1500)]), [])
            self.assertEqual(violations([(0, 600), (1199, 1500)]), [(1, "short-rest")])
            self.assertEqual(violations([(0, 500), (1100, 1400)]), [])
            self.assertEqual(violations([(0, 500), (1099, 1400)]), [(1, "short-rest")])

        def test_rest_after_a_long_duty(self):
            self.assertEqual(violations([(0, 601), (1321, 1500)]), [])
            self.assertEqual(violations([(0, 601), (1320, 1500)]), [(1, "short-rest")])
            self.assertEqual(violations([(0, 780), (1500, 1600)]), [])
            self.assertEqual(violations([(0, 780), (1499, 1600)]), [(1, "short-rest")])

        def test_rest_is_checked_for_every_pair(self):
            d = [(0, 100), (700, 800), (1000, 1100), (1700, 1800)]
            self.assertEqual(violations(d), [(2, "short-rest")])

        def test_weekly_cap(self):
            six = [duty(d, 8, 600) for d in range(6)]
            self.assertEqual(violations(six), [])
            seven = six + [duty(6, 8, 600)]
            self.assertEqual(violations(seven), [(6, "no-break"), (6, "weekly-cap")])

        def test_weekly_window_slides(self):
            d = [duty(day, 8, 600) for day in (0, 1, 2, 3, 4, 5)] + [duty(7, 8, 600)]
            self.assertEqual(violations(d), [])
            d = [duty(day, 8, 600) for day in (0, 1, 2, 3, 4, 5)] + [duty(7, 7, 600)]
            self.assertEqual(violations(d), [(6, "weekly-cap")])

        def test_weekly_cap_is_not_exceeded_at_exactly_3600(self):
            d = [duty(day, 8, 720) for day in range(5)]
            self.assertEqual(violations(d), [])
            d = [duty(day, 8, 720) for day in range(5)] + [duty(5, 8, 1)]
            self.assertEqual(violations(d), [(5, "weekly-cap")])

        def test_no_break_runs(self):
            six_days = [duty(d, 8, 300) for d in range(6)]
            self.assertEqual(violations(six_days), [])
            days = [duty(d, 8, 300) for d in range(8)]
            self.assertEqual(violations(days), [(6, "no-break"), (7, "no-break")])

        def test_break_resets_the_run(self):
            d = [duty(day, 8, 300) for day in (0, 1, 2, 3, 4, 5)] + [duty(8, 8, 300), duty(9, 8, 300)]
            self.assertEqual(violations(d), [])
            d = [duty(day, 8, 300) for day in (0, 1, 2, 3, 4, 5)] + [duty(7, 8, 300)]
            self.assertEqual(violations(d), [])

        def test_break_gap_boundary(self):
            base = [duty(day, 8, 300) for day in range(6)]
            last_end = base[-1][1]
            self.assertEqual(violations(base + [(last_end + 1799, last_end + 1799 + 300)]), [(6, "no-break")])
            self.assertEqual(violations(base + [(last_end + 1800, last_end + 1800 + 300)]), [])

        def test_monthly_cap(self):
            roster = []
            for week in range(4):
                for day in range(6):
                    roster.append(duty(week * 7 + day, 8, 600))
            got = violations(roster)
            self.assertEqual(got, [(i, "monthly-cap") for i in range(19, 24)])

        def test_several_codes_at_one_duty_are_sorted(self):
            d = [(0, 700), (710, 1500)]
            self.assertEqual(violations(d), [(1, "duty-too-long"), (1, "short-rest")])


    class EarliestStart(unittest.TestCase):
        def test_no_duties(self):
            self.assertEqual(earliest_next_start([], 600), 0)

        def test_rest_only(self):
            self.assertEqual(earliest_next_start([(480, 1080)], 600), 1680)
            self.assertEqual(earliest_next_start([(480, 1181)], 600), 1181 + 720)
            self.assertEqual(earliest_next_start([(480, 1080), (1920, 2400)], 100), 3000)

        def test_weekly_cap_pushes_the_start(self):
            six = [duty(d, 8, 600) for d in range(6)]
            self.assertEqual(earliest_next_start(six, 600), 10_560)
            self.assertEqual(earliest_next_start(six, 1), 10_560)
            self.assertEqual(earliest_next_start(six, 300), 10_560)
            heavy = [duty(0, 8, 780)] + [duty(d, 8, 600) for d in range(1, 6)]
            self.assertEqual(earliest_next_start(heavy, 600), 10_740)

        def test_result_is_legal_and_tight(self):
            six = [duty(d, 8, 600) for d in range(6)]
            for length in (1, 120, 300, 600, 780):
                start = earliest_next_start(six, length)
                end = start + length
                self.assertLessEqual(window_total(six, end, 10_080) + length, 3600)
                if start > 8280 + 600:
                    self.assertGreater(window_total(six, end - 1, 10_080) + length, 3600)

        def test_monthly_cap_pushes_the_start(self):
            roster = [duty(week * 7 + day, 8, 600) for week in range(4) for day in range(6)]
            # the six duties of the first week must have left the 28 day window: 8280 + 40320 - 600
            self.assertEqual(earliest_next_start(roster, 600), 48_000)

        def test_length_limits(self):
            for length in (0, -1, 781, 5000):
                with self.assertRaises(ValueError):
                    earliest_next_start([], length)
            self.assertEqual(earliest_next_start([], 780), 0)
            self.assertEqual(earliest_next_start([], 1), 0)


    if __name__ == "__main__":
        unittest.main()
''')

CREWREST = Lib(
    name="crewrest", lang="python", title="the crew duty-limit checker (`crewrest/limits.py`)",
    blurb="The airline's crew-planning tool checks rosters against duty-time and rest limits with crewrest.",
    files={"crewrest/__init__.py": "", "crewrest/limits.py": CR_LIMITS, "README.md": CR_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": CR_VISIBLE},
    hidden_tests={"tests/test_full.py": CR_HIDDEN},
    mutate=["crewrest/limits.py"], difficulty=3, tags=["rostering", "limits", "windows"],
    probes=[
        "required_rest(600)", "required_rest(601)", "window_total([(0, 600), (1440, 2040)], 1000, 500)",
        "violations([(0, 781)])", "violations([(0, 600), (1199, 1500)])", "violations([(0, 601), (1320, 1500)])",
        "violations([(i * 1440 + 480, i * 1440 + 1080) for i in range(7)])",
        "violations([(i * 1440 + 480, i * 1440 + 780) for i in range(8)])",
        "violations([(0, 700), (710, 1500)])",
        "earliest_next_start([(i * 1440 + 480, i * 1440 + 1080) for i in range(6)], 600)",
        "earliest_next_start([(480, 1181)], 600)", "earliest_next_start([], 780)",
    ],
    probe_import="from crewrest.limits import *",
)

register_libs([SHIFTROSTER, TIDEDOCK, CREWREST], n=10)
