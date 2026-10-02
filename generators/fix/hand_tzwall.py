"""Wall-clock vs UTC arithmetic around daylight-saving changes, in invented time zones (no tz database needed)."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, sub, subtree, tasks_from

ZONES_SRC = dd('''
    """Invented time zones with a one-rule daylight saving scheme (the real tz database is not used)."""
    from datetime import datetime, timedelta


    class Zone:
        def __init__(self, name, std_minutes, dst_minutes=0, dst_start=(4, 1), dst_end=(10, 1)):
            self.name = name
            self.std = std_minutes
            self.dst = dst_minutes
            self.dst_start = dst_start
            self.dst_end = dst_end

        def _bounds(self, year):
            """(start, end) of daylight time in UTC for `year`. Daylight time begins at 02:00 standard time on
            `dst_start` and ends at 03:00 daylight time on `dst_end`."""
            start = datetime(year, self.dst_start[0], self.dst_start[1], 2, 0) - timedelta(minutes=self.std)
            end = datetime(year, self.dst_end[0], self.dst_end[1], 3, 0) - timedelta(minutes=self.std + self.dst)
            return start, end

        def offset_at(self, utc):
            """Offset from UTC, in minutes, at the UTC instant `utc` (a naive datetime)."""
            if not self.dst:
                return self.std
            start, end = self._bounds(utc.year)
            if start < end:  # northern hemisphere: daylight time inside one calendar year
                inside = start <= utc < end
            else:  # southern hemisphere: daylight time wraps around New Year
                inside = utc >= start or utc < end
            return self.std + self.dst if inside else self.std

        def from_utc(self, utc):
            """Naive local wall-clock time at the UTC instant `utc`."""
            return utc + timedelta(minutes=self.offset_at(utc))

        def to_utc(self, local, fold=0):
            """UTC instant of a naive local wall-clock time.

            A local time that does not exist (skipped when clocks go forward) is read as if the clocks had
            already moved: it is pushed forward by the length of the gap. A local time that happens twice
            (clocks go back) means its first occurrence for fold=0 and its second for fold=1."""
            daylight = local - timedelta(minutes=self.std + self.dst)
            standard = local - timedelta(minutes=self.std)
            dst_ok = self.offset_at(daylight) == self.std + self.dst
            std_ok = self.offset_at(standard) == self.std
            if dst_ok and std_ok:
                return daylight if fold == 0 else standard
            if dst_ok:
                return daylight
            return standard
''')

ZONE_README = dd('''
    ## Zones
    `{{pkg}}.zones.Zone(name, std_minutes, dst_minutes=0, dst_start=(month, day), dst_end=(month, day))` is an
    invented time zone. All datetimes are *naive*: UTC instants are naive datetimes in UTC, local times are naive
    wall-clock datetimes of the zone.

    * Daylight time (offset `std + dst`) begins at 02:00 standard time on `dst_start` (the clocks jump forward by
      `dst` minutes) and ends at 03:00 daylight time on `dst_end` (the clocks go back by `dst` minutes). If
      `dst_start` is later in the year than `dst_end` the zone is in the southern hemisphere and daylight time
      spans New Year.
    * `offset_at(utc)` is the offset in minutes at an instant; `from_utc(utc)` the local wall-clock time.
    * `to_utc(local, fold=0)`: a skipped local time is pushed forward by the gap; an ambiguous one is its first
      occurrence for `fold=0` and its second for `fold=1`.
''')

ZONE_TESTS = dd('''
    import unittest
    from datetime import datetime, timedelta

    from {{pkg}}.zones import Zone

    K = Zone("Kestrel", 300, 60, (4, 1), (10, 1))   # UTC+5, +1h from 1 April 02:00 to 1 October 03:00 (daylight)
    T = Zone("Tarn", 600, 30, (10, 1), (4, 1))      # UTC+10, +30min from 1 October to 1 April (southern)
    U = Zone("Utica", 0)
    O = Zone("Orrin", -210)                         # UTC-3:30, no daylight time


    def D(*a):
        return datetime(*a)


    class OffsetTests(unittest.TestCase):
        def test_kestrel_offsets(self):
            cases = [((2025, 1, 1, 0, 0), 300), ((2025, 3, 31, 20, 59), 300), ((2025, 3, 31, 21, 0), 360),
                     ((2025, 6, 15, 0, 0), 360), ((2025, 9, 30, 20, 59), 360), ((2025, 9, 30, 21, 0), 300),
                     ((2025, 12, 31, 23, 59), 300)]
            for when, want in cases:
                self.assertEqual(K.offset_at(D(*when)), want, when)

        def test_tarn_offsets_wrap_new_year(self):
            cases = [((2025, 1, 10, 0, 0), 630), ((2025, 3, 31, 16, 29), 630), ((2025, 3, 31, 16, 30), 600),
                     ((2025, 6, 1, 0, 0), 600), ((2025, 9, 30, 15, 59), 600), ((2025, 9, 30, 16, 0), 630),
                     ((2025, 12, 25, 0, 0), 630), ((2026, 1, 1, 0, 0), 630)]
            for when, want in cases:
                self.assertEqual(T.offset_at(D(*when)), want, when)

        def test_no_dst_zones(self):
            self.assertEqual(U.offset_at(D(2025, 7, 1)), 0)
            self.assertEqual(O.offset_at(D(2025, 7, 1)), -210)
            self.assertEqual(O.from_utc(D(2025, 1, 1, 0, 0)), D(2024, 12, 31, 20, 30))

        def test_from_utc_around_changes(self):
            self.assertEqual(K.from_utc(D(2025, 3, 31, 20, 59)), D(2025, 4, 1, 1, 59))
            self.assertEqual(K.from_utc(D(2025, 3, 31, 21, 0)), D(2025, 4, 1, 3, 0))
            self.assertEqual(K.from_utc(D(2025, 9, 30, 20, 59)), D(2025, 10, 1, 2, 59))
            self.assertEqual(K.from_utc(D(2025, 9, 30, 21, 0)), D(2025, 10, 1, 2, 0))
            self.assertEqual(K.from_utc(D(2025, 9, 30, 22, 0)), D(2025, 10, 1, 3, 0))
            self.assertEqual(T.from_utc(D(2025, 9, 30, 15, 59)), D(2025, 10, 1, 1, 59))
            self.assertEqual(T.from_utc(D(2025, 9, 30, 16, 0)), D(2025, 10, 1, 2, 30))


    class ToUtcTests(unittest.TestCase):
        def test_ordinary_times(self):
            self.assertEqual(K.to_utc(D(2025, 7, 1, 18, 0)), D(2025, 7, 1, 12, 0))
            self.assertEqual(K.to_utc(D(2025, 1, 15, 17, 0)), D(2025, 1, 15, 12, 0))
            self.assertEqual(T.to_utc(D(2025, 1, 15, 10, 30)), D(2025, 1, 15, 0, 0))
            self.assertEqual(U.to_utc(D(2025, 1, 15, 10, 30)), D(2025, 1, 15, 10, 30))

        def test_gap_is_pushed_forward(self):
            self.assertEqual(K.to_utc(D(2025, 4, 1, 1, 59)), D(2025, 3, 31, 20, 59))
            self.assertEqual(K.to_utc(D(2025, 4, 1, 2, 0)), D(2025, 3, 31, 21, 0))
            self.assertEqual(K.to_utc(D(2025, 4, 1, 2, 30)), D(2025, 3, 31, 21, 30))
            self.assertEqual(K.to_utc(D(2025, 4, 1, 3, 0)), D(2025, 3, 31, 21, 0))
            self.assertEqual(T.to_utc(D(2025, 10, 1, 2, 15)), D(2025, 9, 30, 16, 15))
            self.assertEqual(T.to_utc(D(2025, 10, 1, 2, 30)), D(2025, 9, 30, 16, 0))

        def test_overlap_follows_fold(self):
            self.assertEqual(K.to_utc(D(2025, 10, 1, 1, 59)), D(2025, 9, 30, 19, 59))
            self.assertEqual(K.to_utc(D(2025, 10, 1, 2, 30)), D(2025, 9, 30, 20, 30))
            self.assertEqual(K.to_utc(D(2025, 10, 1, 2, 30), fold=1), D(2025, 9, 30, 21, 30))
            self.assertEqual(K.to_utc(D(2025, 10, 1, 3, 0)), D(2025, 9, 30, 22, 0))
            self.assertEqual(K.to_utc(D(2025, 10, 1, 3, 0), fold=1), D(2025, 9, 30, 22, 0))
            self.assertEqual(T.to_utc(D(2025, 4, 1, 2, 29)), D(2025, 3, 31, 15, 59))
            self.assertEqual(T.to_utc(D(2025, 4, 1, 2, 45)), D(2025, 3, 31, 16, 15))
            self.assertEqual(T.to_utc(D(2025, 4, 1, 2, 45), fold=1), D(2025, 3, 31, 16, 45))
            self.assertEqual(T.to_utc(D(2025, 4, 1, 3, 0)), D(2025, 3, 31, 17, 0))

        def test_round_trip_every_15_minutes(self):
            for zone in (K, T, U, O):
                t = D(2025, 3, 28, 0, 0)
                while t < D(2025, 4, 4, 0, 0) or (D(2025, 9, 28) <= t < D(2025, 10, 4)):
                    local = zone.from_utc(t)
                    self.assertIn(t, {zone.to_utc(local, 0), zone.to_utc(local, 1)}, (zone.name, t))
                    t += timedelta(minutes=15)
                    if t >= D(2025, 4, 4) and t < D(2025, 9, 28):
                        t = D(2025, 9, 28)
''')

# ---------------------------------------------------------------- base A: reminder scheduling ---------------------------

A_README = dd('''
    # pingdesk

    Scheduling helpers of a reminder service whose customers live in zones with daylight saving. Everything is
    computed with the invented `Zone` class below; no tz database is involved.

    {{ZONES}}
    ## `pingdesk.schedule`
    * `next_daily(zone, after, hour, minute)`: the first UTC instant *strictly after* `after` at which the local clock
      of `zone` reads `hour:minute` (a local time that does not exist that day, or that happens twice, is resolved
      by `Zone.to_utc` with its defaults, so such a reminder fires once a day).
    * `add_local_days(zone, utc, n)`: the instant that has the same local wall-clock time `n` days later (negative
      `n` goes back), resolved with the `to_utc` defaults.
    * `local_midnight(zone, utc)`: the UTC instant of the start (00:00 local) of the local day containing `utc`.
    * `day_length_minutes(zone, utc)`: length in minutes of the local day containing `utc` (1440 on an ordinary day).
    * `days_between(zone, a, b)`: number of local calendar days from the local date of `a` to the local date of `b`
      (negative when `b` is earlier).
''')

A_SCHEDULE = dd('''
    from datetime import datetime, time, timedelta


    def next_daily(zone, after, hour, minute):
        local = zone.from_utc(after)
        day = local.date()
        for _ in range(3):
            cand = zone.to_utc(datetime.combine(day, time(hour, minute)))
            if cand > after:
                return cand
            day += timedelta(days=1)
        raise AssertionError("unreachable")


    def add_local_days(zone, utc, n):
        return zone.to_utc(zone.from_utc(utc) + timedelta(days=n))


    def local_midnight(zone, utc):
        day = zone.from_utc(utc).date()
        return zone.to_utc(datetime.combine(day, time(0, 0)))


    def day_length_minutes(zone, utc):
        day = zone.from_utc(utc).date()
        start = zone.to_utc(datetime.combine(day, time(0, 0)))
        end = zone.to_utc(datetime.combine(day + timedelta(days=1), time(0, 0)))
        return int((end - start).total_seconds() // 60)


    def days_between(zone, a, b):
        return (zone.from_utc(b).date() - zone.from_utc(a).date()).days
''')

A_VISIBLE = {
    "tests/test_schedule.py": dd('''
        import unittest
        from datetime import datetime

        from pingdesk.schedule import add_local_days, next_daily
        from pingdesk.zones import Zone

        KESTREL = Zone("Kestrel", 300, 60, (4, 1), (10, 1))


        class ScheduleTests(unittest.TestCase):
            def test_next_daily_ordinary_day(self):
                got = next_daily(KESTREL, datetime(2025, 6, 10, 2, 59), 9, 0)
                self.assertEqual(got, datetime(2025, 6, 10, 3, 0))

            def test_next_daily_is_strictly_after(self):
                got = next_daily(KESTREL, datetime(2025, 6, 10, 3, 0), 9, 0)
                self.assertEqual(got, datetime(2025, 6, 11, 3, 0))

            def test_add_days_in_summer(self):
                self.assertEqual(add_local_days(KESTREL, datetime(2025, 6, 1, 3, 0), 7), datetime(2025, 6, 8, 3, 0))


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_zones.py": sub(ZONE_TESTS, pkg="pingdesk"),
    "tests/test_hidden_schedule.py": dd('''
        import unittest
        from datetime import datetime

        from pingdesk.schedule import add_local_days, day_length_minutes, days_between, local_midnight, next_daily
        from pingdesk.zones import Zone

        K = Zone("Kestrel", 300, 60, (4, 1), (10, 1))
        T = Zone("Tarn", 600, 30, (10, 1), (4, 1))
        U = Zone("Utica", 0)


        def D(*a):
            return datetime(*a)


        class NextDaily(unittest.TestCase):
            def test_plain(self):
                self.assertEqual(next_daily(K, D(2025, 6, 10, 3, 0), 9, 0), D(2025, 6, 11, 3, 0))
                self.assertEqual(next_daily(K, D(2025, 6, 10, 2, 59), 9, 0), D(2025, 6, 10, 3, 0))
                self.assertEqual(next_daily(U, D(2025, 5, 5, 9, 0), 9, 0), D(2025, 5, 6, 9, 0))
                self.assertEqual(next_daily(U, D(2025, 5, 5, 9, 0), 0, 0), D(2025, 5, 6, 0, 0))

            def test_the_day_clocks_go_forward(self):
                # local 09:00 on 31 March is UTC+5, on 1 April UTC+6
                self.assertEqual(next_daily(K, D(2025, 3, 31, 4, 0), 9, 0), D(2025, 4, 1, 3, 0))
                self.assertEqual(next_daily(K, D(2025, 3, 30, 12, 0), 9, 0), D(2025, 3, 31, 4, 0))

            def test_the_day_clocks_go_back(self):
                self.assertEqual(next_daily(K, D(2025, 9, 30, 3, 0), 9, 0), D(2025, 10, 1, 4, 0))
                self.assertEqual(next_daily(K, D(2025, 9, 29, 3, 0), 9, 0), D(2025, 9, 30, 3, 0))

            def test_time_inside_the_gap(self):
                self.assertEqual(next_daily(K, D(2025, 3, 31, 12, 0), 2, 30), D(2025, 3, 31, 21, 30))

            def test_time_inside_the_overlap_fires_on_first_pass_only(self):
                self.assertEqual(next_daily(K, D(2025, 9, 30, 12, 0), 2, 30), D(2025, 9, 30, 20, 30))
                self.assertEqual(next_daily(K, D(2025, 9, 30, 20, 30), 2, 30), D(2025, 10, 1, 21, 30))

            def test_southern_zone(self):
                self.assertEqual(next_daily(T, D(2025, 9, 30, 10, 0), 9, 0), D(2025, 9, 30, 22, 30))
                self.assertEqual(next_daily(T, D(2025, 1, 5, 0, 0), 9, 0), D(2025, 1, 5, 22, 30))

            def test_new_year(self):
                self.assertEqual(next_daily(K, D(2025, 12, 31, 20, 0), 0, 30), D(2026, 1, 1, 19, 30))


        class AddLocalDays(unittest.TestCase):
            def test_across_the_changes(self):
                self.assertEqual(add_local_days(K, D(2025, 3, 31, 4, 0), 1), D(2025, 4, 1, 3, 0))
                self.assertEqual(add_local_days(K, D(2025, 9, 30, 3, 0), 1), D(2025, 10, 1, 4, 0))
                self.assertEqual(add_local_days(K, D(2025, 4, 2, 3, 0), -1), D(2025, 4, 1, 3, 0))
                self.assertEqual(add_local_days(K, D(2025, 4, 1, 3, 0), -1), D(2025, 3, 31, 4, 0))

            def test_plain_and_zero(self):
                self.assertEqual(add_local_days(K, D(2025, 6, 1, 3, 0), 7), D(2025, 6, 8, 3, 0))
                self.assertEqual(add_local_days(K, D(2025, 6, 1, 3, 0), 0), D(2025, 6, 1, 3, 0))
                self.assertEqual(add_local_days(U, D(2025, 6, 1, 3, 0), 30), D(2025, 7, 1, 3, 0))

            def test_lands_in_the_gap(self):
                self.assertEqual(add_local_days(K, D(2025, 3, 30, 21, 30), 1), D(2025, 3, 31, 21, 30))


        class Midnight(unittest.TestCase):
            def test_local_midnight(self):
                self.assertEqual(local_midnight(K, D(2025, 6, 15, 12, 0)), D(2025, 6, 14, 18, 0))
                self.assertEqual(local_midnight(K, D(2025, 3, 31, 19, 0)), D(2025, 3, 31, 19, 0))
                self.assertEqual(local_midnight(U, D(2025, 6, 15, 12, 0)), D(2025, 6, 15, 0, 0))

            def test_local_midnight_after_a_change_on_the_same_day(self):
                self.assertEqual(local_midnight(K, D(2025, 4, 1, 6, 0)), D(2025, 3, 31, 19, 0))
                self.assertEqual(local_midnight(K, D(2025, 10, 1, 12, 0)), D(2025, 9, 30, 18, 0))
                self.assertEqual(local_midnight(T, D(2025, 10, 1, 8, 0)), D(2025, 9, 30, 14, 0))

            def test_day_length(self):
                self.assertEqual(day_length_minutes(K, D(2025, 6, 15, 12, 0)), 1440)
                self.assertEqual(day_length_minutes(K, D(2025, 3, 31, 12, 0)), 1440)
                self.assertEqual(day_length_minutes(K, D(2025, 4, 1, 6, 0)), 1380)
                self.assertEqual(day_length_minutes(K, D(2025, 10, 1, 12, 0)), 1500)
                self.assertEqual(day_length_minutes(T, D(2025, 10, 1, 0, 0)), 1410)
                self.assertEqual(day_length_minutes(T, D(2025, 4, 1, 12, 0)), 1470)


        class DaysBetween(unittest.TestCase):
            def test_calendar_days_not_24h_blocks(self):
                self.assertEqual(days_between(K, D(2025, 6, 10, 17, 0), D(2025, 6, 10, 19, 0)), 1)
                self.assertEqual(days_between(K, D(2025, 6, 10, 18, 0), D(2025, 6, 11, 17, 59)), 0)
                self.assertEqual(days_between(K, D(2025, 3, 31, 19, 30), D(2025, 4, 1, 18, 10)), 1)
                self.assertEqual(days_between(K, D(2025, 12, 31, 12, 0), D(2026, 1, 2, 12, 0)), 2)

            def test_negative(self):
                self.assertEqual(days_between(K, D(2025, 6, 12, 17, 0), D(2025, 6, 11, 19, 0)), 0)
                self.assertEqual(days_between(K, D(2025, 6, 12, 12, 0), D(2025, 6, 10, 12, 0)), -2)
                self.assertEqual(days_between(U, D(2025, 6, 12, 0, 30), D(2025, 6, 11, 23, 30)), -1)


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_files():
    readme = sub(A_README, ZONES=sub(ZONE_README, pkg="pingdesk"))
    return {"README.md": readme, "pingdesk/__init__.py": '"""Reminder scheduling."""\n', "pingdesk/zones.py": ZONES_SRC, "pingdesk/schedule.py": A_SCHEDULE}


def _a_prompts():
    p = {}
    p["offset-of-now"] = (
        "Our 09:00 \"daily digest\" reminder goes out an hour off on the first run after the clocks change in a customer's "
        "zone (10:00 or 08:00 their time), and is right again from the day after. It uses `next_daily` in "
        "`pingdesk/schedule.py`. I have not been able to reproduce it outside the days around 1 April and 1 October."
    )
    p["days-absolute"] = lambda c: (
        "ticket PD-88: \"same time next week\" reminders drift by one hour when the week contains a clock change. "
        "Example: a reminder set for 09:00 local on 31 March (Kestrel zone) and moved forward one day lands at "
        + c.probe("from datetime import datetime\nfrom pingdesk.schedule import add_local_days\nfrom pingdesk.zones import Zone\n"
                  "K = Zone('Kestrel', 300, 60, (4, 1), (10, 1))\n"
                  "u = add_local_days(K, datetime(2025, 3, 31, 4, 0), 1)\nprint(K.from_utc(u).strftime('%H:%M'))\n")[1]
        + " local on 1 April instead of 09:00. Please make `add_local_days` keep the wall-clock time as documented."
    )
    p["days-between-utc"] = lambda c: (
        "The usage report counts \"days since last login\" wrongly for evening/morning pairs: a customer who logged in at "
        "23:00 local and came back at 01:00 the next local day is reported as 0 days apart. Here is what I get for the "
        "Kestrel zone: `days_between(K, 2025-06-10 17:00 UTC, 2025-06-10 19:00 UTC)` -> "
        + c.probe("from datetime import datetime\nfrom pingdesk.schedule import days_between\nfrom pingdesk.zones import Zone\n"
                  "K = Zone('Kestrel', 300, 60, (4, 1), (10, 1))\nprint(days_between(K, datetime(2025, 6, 10, 17, 0), datetime(2025, 6, 10, 19, 0)))\n")[1]
        + ". It should count calendar days in the customer's zone."
    )
    p["fold-swapped"] = (
        "Audit finding: on the night clocks go back, reminders scheduled for a time that occurs twice (02:30 on 1 October in "
        "Kestrel) fire on the *second* pass of 02:30, an hour late, although the docs say a repeated time means its first "
        "occurrence unless asked otherwise. The reminder code just calls the zone helper, so I suspect the helper. "
        "Please fix what is wrong, keeping the documented `fold` argument working."
    )
    p["end-bound-local"] = (
        "This looks like a scheduler bug but I cannot find it in the scheduler. `next_daily(K, 2025-09-30 12:00 UTC, 2, 30)` should be the first time 02:30 shows on the "
        "wall clocks on 1 October, 20:30 UTC, but we get 21:30 UTC, an hour later; times in the repeated hour on that day "
        "also convert to the wrong instant in the audit export. I assumed `next_daily`'s loop is at fault, but nothing "
        "in there looks wrong. Find out where the hour goes."
    )
    p["midnight-elapsed"] = (
        "The nightly rollup that sums usage per local day cuts the day at the wrong instant on the day clocks change, "
        "but only for events after the change: for an event at 06:00 UTC on 1 April in Kestrel the day start comes out an "
        "hour before local midnight. Other days are fine. `local_midnight` in `schedule.py` is the place to look."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = _a_files()
    z = "pingdesk/zones.py"
    s = "pingdesk/schedule.py"
    bugs = [
        Bug("digest-offset-of-now", 3, {s: [("        cand = zone.to_utc(datetime.combine(day, time(hour, minute)))",
                                             "        cand = datetime.combine(day, time(hour, minute)) - timedelta(minutes=zone.offset_at(after))")]}, P["offset-of-now"]),
        Bug("add-days-absolute", 2, {s: [("    return zone.to_utc(zone.from_utc(utc) + timedelta(days=n))", "    return utc + timedelta(days=n)")]}, P["days-absolute"]),
        Bug("days-between-utc-diff", 2, {s: [("    return (zone.from_utc(b).date() - zone.from_utc(a).date()).days", "    return (b - a).days")]}, P["days-between-utc"]),
        Bug("overlap-fold-swapped", 3, {z: [("            return daylight if fold == 0 else standard", "            return standard if fold == 0 else daylight")]}, P["fold-swapped"]),
        Bug("dst-end-bound", 4, {z: [("        end = datetime(year, self.dst_end[0], self.dst_end[1], 3, 0) - timedelta(minutes=self.std + self.dst)",
                                      "        end = datetime(year, self.dst_end[0], self.dst_end[1], 3, 0) - timedelta(minutes=self.std)")]}, P["end-bound-local"]),
        Bug("midnight-by-elapsed", 3, {s: [("    day = zone.from_utc(utc).date()\n    return zone.to_utc(datetime.combine(day, time(0, 0)))\n\n\ndef day_length_minutes",
                                            "    local = zone.from_utc(utc)\n    return utc - timedelta(hours=local.hour, minutes=local.minute, seconds=local.second)\n\n\ndef day_length_minutes")]}, P["midnight-elapsed"]),
    ]
    return Base("pingdesk", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ---------------------------------------------------------------- base B: shift pay -------------------------------------

B_README = dd('''
    # shiftpay

    Payroll helper for shift workers in zones with daylight saving. Shifts are recorded as *local wall-clock* start
    and end times (naive datetimes of the worker's zone); pay follows the minutes that really elapsed.

    {{ZONES}}
    ## `shiftpay.roster`
    * `worked_minutes(zone, start, end)`: real minutes elapsed between the two local times. When a time is
      ambiguous (it happens twice because the clocks went back) the **start** of a shift means its first occurrence
      and the **end** of a shift means its second occurrence; a time that does not exist is resolved as `to_utc`
      does.
    * `pay_cents(zone, start, end, hourly_cents)`: the first 480 worked minutes are paid at the hourly rate, minutes
      beyond that at 1.5 times the rate. Each part is rounded *down* to a whole cent on its own:
      `hourly * regular_minutes // 60` plus `hourly * overtime_minutes * 3 // 120`.
    * `shift_end_local(zone, start, minutes)`: the local wall-clock time at which a shift that starts at local time
      `start` and lasts `minutes` real minutes ends.
''')

B_ROSTER = dd('''
    from datetime import timedelta

    REGULAR_MINUTES = 480


    def worked_minutes(zone, start, end):
        a = zone.to_utc(start, fold=0)
        b = zone.to_utc(end, fold=1)
        return int((b - a).total_seconds() // 60)


    def pay_cents(zone, start, end, hourly_cents):
        minutes = worked_minutes(zone, start, end)
        regular = min(minutes, REGULAR_MINUTES)
        overtime = minutes - regular
        return hourly_cents * regular // 60 + hourly_cents * overtime * 3 // 120


    def shift_end_local(zone, start, minutes):
        return zone.from_utc(zone.to_utc(start, fold=0) + timedelta(minutes=minutes))
''')

B_VISIBLE = {
    "tests/test_roster.py": dd('''
        import unittest
        from datetime import datetime

        from shiftpay.roster import pay_cents, worked_minutes
        from shiftpay.zones import Zone

        K = Zone("Kestrel", 300, 60, (4, 1), (10, 1))


        class RosterTests(unittest.TestCase):
            def test_ordinary_night_shift(self):
                self.assertEqual(worked_minutes(K, datetime(2025, 6, 2, 22, 0), datetime(2025, 6, 3, 6, 0)), 480)

            def test_pay_for_a_regular_shift(self):
                self.assertEqual(pay_cents(K, datetime(2025, 6, 2, 22, 0), datetime(2025, 6, 3, 6, 0), 1500), 12000)


        if __name__ == "__main__":
            unittest.main()
    '''),
}

B_HIDDEN = {
    "tests/test_hidden_zones.py": sub(ZONE_TESTS, pkg="shiftpay"),
    "tests/test_hidden_roster.py": dd('''
        import unittest
        from datetime import datetime

        from shiftpay.roster import pay_cents, shift_end_local, worked_minutes
        from shiftpay.zones import Zone

        K = Zone("Kestrel", 300, 60, (4, 1), (10, 1))
        T = Zone("Tarn", 600, 30, (10, 1), (4, 1))
        U = Zone("Utica", 0)


        def D(*a):
            return datetime(*a)


        class WorkedMinutes(unittest.TestCase):
            def test_ordinary(self):
                self.assertEqual(worked_minutes(K, D(2025, 6, 2, 22, 0), D(2025, 6, 3, 6, 0)), 480)
                self.assertEqual(worked_minutes(U, D(2025, 6, 2, 9, 0), D(2025, 6, 2, 17, 30)), 510)
                self.assertEqual(worked_minutes(K, D(2025, 6, 2, 9, 0), D(2025, 6, 2, 9, 0)), 0)

            def test_northern_changes(self):
                self.assertEqual(worked_minutes(K, D(2025, 3, 31, 22, 0), D(2025, 4, 1, 6, 0)), 420)
                self.assertEqual(worked_minutes(K, D(2025, 9, 30, 22, 0), D(2025, 10, 1, 6, 0)), 540)

            def test_southern_changes_with_half_hour_shift(self):
                self.assertEqual(worked_minutes(T, D(2025, 9, 30, 22, 0), D(2025, 10, 1, 6, 0)), 450)
                self.assertEqual(worked_minutes(T, D(2025, 3, 31, 22, 0), D(2025, 4, 1, 6, 0)), 510)
                self.assertEqual(worked_minutes(T, D(2025, 1, 10, 22, 0), D(2025, 1, 11, 6, 0)), 480)

            def test_ambiguous_and_skipped_times(self):
                self.assertEqual(worked_minutes(K, D(2025, 9, 30, 22, 0), D(2025, 10, 1, 2, 30)), 330)
                self.assertEqual(worked_minutes(K, D(2025, 10, 1, 2, 30), D(2025, 10, 1, 6, 0)), 270)
                self.assertEqual(worked_minutes(K, D(2025, 4, 1, 2, 15), D(2025, 4, 1, 6, 0)), 165)


        class Pay(unittest.TestCase):
            def test_regular_and_changes(self):
                self.assertEqual(pay_cents(K, D(2025, 6, 2, 22, 0), D(2025, 6, 3, 6, 0), 1500), 12000)
                self.assertEqual(pay_cents(K, D(2025, 3, 31, 22, 0), D(2025, 4, 1, 6, 0), 1500), 10500)
                self.assertEqual(pay_cents(K, D(2025, 9, 30, 22, 0), D(2025, 10, 1, 6, 0), 1500), 14250)

            def test_each_part_rounds_down(self):
                self.assertEqual(pay_cents(T, D(2025, 3, 31, 22, 0), D(2025, 4, 1, 6, 0), 1333), 11663)
                self.assertEqual(pay_cents(U, D(2025, 6, 2, 9, 0), D(2025, 6, 2, 10, 40), 1333), 2221)

            def test_only_minutes_beyond_480_get_the_premium(self):
                self.assertEqual(pay_cents(U, D(2025, 6, 2, 8, 0), D(2025, 6, 2, 16, 1), 1200), 9630)
                self.assertEqual(pay_cents(U, D(2025, 6, 2, 8, 0), D(2025, 6, 2, 18, 0), 1200), 9600 + 3600)
                self.assertEqual(pay_cents(U, D(2025, 6, 2, 8, 0), D(2025, 6, 2, 8, 0), 1200), 0)


        class ShiftEnd(unittest.TestCase):
            def test_ordinary(self):
                self.assertEqual(shift_end_local(K, D(2025, 6, 2, 9, 0), 90), D(2025, 6, 2, 10, 30))
                self.assertEqual(shift_end_local(U, D(2025, 12, 31, 20, 0), 480), D(2026, 1, 1, 4, 0))

            def test_across_changes(self):
                self.assertEqual(shift_end_local(K, D(2025, 3, 31, 22, 0), 480), D(2025, 4, 1, 7, 0))
                self.assertEqual(shift_end_local(K, D(2025, 9, 30, 22, 0), 480), D(2025, 10, 1, 5, 0))
                self.assertEqual(shift_end_local(T, D(2025, 9, 30, 22, 0), 480), D(2025, 10, 1, 6, 30))
                self.assertEqual(shift_end_local(T, D(2025, 3, 31, 22, 0), 480), D(2025, 4, 1, 5, 30))


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _b_prompts():
    p = {}
    p["naive-elapsed"] = lambda c: (
        "Payroll complaint from the night crew: on the night the clocks went forward they were paid for a full eight hours "
        "although the shift lasted seven. For `worked_minutes(K, 2025-03-31 22:00, 2025-04-01 06:00)` (Kestrel zone) we "
        "get "
        + c.probe("from datetime import datetime\nfrom shiftpay.roster import worked_minutes\nfrom shiftpay.zones import Zone\n"
                  "K = Zone('Kestrel', 300, 60, (4, 1), (10, 1))\nprint(worked_minutes(K, datetime(2025, 3, 31, 22, 0), datetime(2025, 4, 1, 6, 0)))\n")[1]
        + " minutes. It should be the minutes that really elapsed."
    )
    p["overtime-all"] = lambda c: (
        "Overtime looks too generous. Somebody who works 8 h 30 min at 12.00 an hour gets "
        + c.probe("from datetime import datetime\nfrom shiftpay.roster import pay_cents\nfrom shiftpay.zones import Zone\n"
                  "U = Zone('Utica', 0)\nprint(pay_cents(U, datetime(2025, 6, 2, 8, 0), datetime(2025, 6, 2, 16, 30), 1200))\n")[1]
        + " cents; only the 30 minutes past the eighth hour should be paid at the higher rate. Please check the pay rule against the README."
    )
    p["southern-wrap"] = (
        "HR says shifts that straddle the daylight-saving changes in Tarn (southern zone, UTC+10 with a 30 minute change) "
        "are paid as if nothing happened: the night of 30 September/1 October counts as a full 8 hours instead of 7.5. "
        "The northern zone Kestrel is fine. Please find out why Tarn is different."
    )
    p["end-offset-of-start"] = (
        "The roster printout shows when each shift ends in local time. For shifts that run across a clock change the end "
        "time is an hour off (a 480 minute shift starting 22:00 on 31 March in Kestrel shows 06:00 instead of 07:00 the "
        "next morning). `shift_end_local` is the function behind that printout."
    )
    p["two-causes"] = (
        "Payroll for Tarn (southern zone, 30 minute change) is off by 30 minutes for some shifts around the changes and "
        "right for others. Kestrel looks fine in the same run, but when I tried a shift that ends during the repeated hour in Kestrel "
        "it was paid short too. I could not tell whether that is the same problem. The visible tests all pass. Please "
        "work out every cause."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    readme = sub(B_README, ZONES=sub(ZONE_README, pkg="shiftpay"))
    good = {"README.md": readme, "shiftpay/__init__.py": '"""Shift pay."""\n', "shiftpay/zones.py": ZONES_SRC, "shiftpay/roster.py": B_ROSTER}
    z, r = "shiftpay/zones.py", "shiftpay/roster.py"
    wrap = ("        if start < end:  # northern hemisphere: daylight time inside one calendar year\n            inside = start <= utc < end\n"
            "        else:  # southern hemisphere: daylight time wraps around New Year\n            inside = utc >= start or utc < end\n",
            "        inside = start <= utc < end\n")
    fold0 = ("    b = zone.to_utc(end, fold=1)", "    b = zone.to_utc(end, fold=0)")
    bugs = [
        Bug("elapsed-ignores-zone", 2, {r: [("    a = zone.to_utc(start, fold=0)\n    b = zone.to_utc(end, fold=1)\n    return int((b - a).total_seconds() // 60)",
                                             "    return int((end - start).total_seconds() // 60)")]}, P["naive-elapsed"]),
        Bug("overtime-on-everything", 2, {r: [("    return hourly_cents * regular // 60 + hourly_cents * overtime * 3 // 120",
                                               "    if overtime:\n        return hourly_cents * minutes * 3 // 120\n    return hourly_cents * regular // 60")]}, P["overtime-all"]),
        Bug("southern-no-wrap", 4, {z: [wrap]}, P["southern-wrap"]),
        Bug("end-uses-start-offset", 3, {r: [("    return zone.from_utc(zone.to_utc(start, fold=0) + timedelta(minutes=minutes))",
                                              "    begin = zone.to_utc(start, fold=0)\n    return begin + timedelta(minutes=zone.offset_at(begin) + minutes)")]}, P["end-offset-of-start"]),
        Bug("wrap-and-fold", 5, {z: [wrap], r: [fold0]}, P["two-causes"]),
    ]
    return Base("shiftpay", "python", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-tz-wallclock", category="fix", lang="python", kind="fix", n=11,
        summary="wall-clock versus UTC arithmetic around daylight-saving changes in invented zones")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
