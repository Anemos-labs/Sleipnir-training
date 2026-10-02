"""Python libraries, theme time/money/scheduling (batch zone-a): fixed-offset time zones with invented daylight-saving
rules (no zoneinfo)."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# zonetab: a tiny time-zone table with DST rules, gaps and ambiguous local times
# ======================================================================================================================

ZT_README = dd('''
    # zonetab

    Time conversion for a ferry timetable that must not depend on a system time-zone database. Instants are naive
    `datetime` objects (seconds count); offsets are whole minutes east of UTC.

    ## Rules (`zonetab/rules.py`)

    `nth_weekday(year, month, weekday, n)` returns the `date` of the `n`-th `weekday` (Monday is 0) of the month for
    `n >= 1`, or the last one for `n == -1`. `n` of 0 or below -1, and a month that has no `n`-th such weekday, is a
    `ValueError`.

    ## Zones (`zonetab/zones.py`)

    A zone is `Zone(name, std, save, start, end)`: its standard offset, the daylight-saving shift (`save` minutes) and
    the two `Rule(month, nth, weekday, minute, clock)` transitions (both `None` for a zone without daylight saving).
    A rule fires on the `nth_weekday` of its month at `minute` minutes after midnight, measured on its `clock`:
    `"utc"`, `"standard"` (the zone's standard time) or `"daylight"` (the zone's daylight time).

    `ZONES` holds Skerry (UTC+00:00, no DST), Veld (UTC+01:00, DST from the last Sunday of March 01:00 UTC to the last
    Sunday of October 01:00 UTC), Northport (UTC+03:30, DST from the 2nd Sunday of March at 02:00 standard time to the
    1st Sunday of November at 02:00 daylight time), Tasmin (UTC-09:30, southern hemisphere: DST from the 1st Sunday of
    October at 02:00 standard time to the 1st Sunday of April at 03:00 daylight time) and Quill (UTC+12:45, no DST); the
    shift is 60 minutes. `get_zone(name)` looks one up (`ValueError` when unknown).

    * `transitions(zone, year)`: the UTC instants `(start, end)` of the two rules in that year.
    * `is_dst(zone, utc)`: daylight saving is in force from the start instant (included) to the end instant (excluded) of
      the year of `utc`; for a southern zone (start after end in the year) it is in force before the end instant and
      from the start instant on. Never for a zone without DST.
    * `offset_at_utc(zone, utc)`: `std`, plus `save` while DST is in force. `to_local(zone, utc)`: `utc` plus that offset.

    ## Conversion (`zonetab/convert.py`)

    * `to_utc(zone, local, prefer="earlier")`: the UTC instant of a local wall-clock time. A local time that happens
      **twice** (when DST ends and the clock goes back) is resolved by `prefer`: `"earlier"` is the earlier instant (the
      daylight-time occurrence), `"later"` the later one. A local time that **never happens** (when DST starts and the
      clock jumps forward) is a `ValueError`. Any other `prefer` is a `ValueError` too.
    * `convert(local, src, dst, prefer="earlier")`: the wall-clock time in zone `dst` of a local time in zone `src`.
    * `utc_offset_str(minutes)`: `"+03:30"`, `"-09:30"`, `"+00:00"` (a sign, hours and minutes with two digits).
    * `describe(zone, utc)`: `"2025-07-01 12:00 Veld (UTC+02:00, daylight)"`; the label is `daylight` or `standard`.
''')

ZT_RULES = dd('''
    import calendar
    from datetime import date, timedelta


    def nth_weekday(year, month, weekday, n):
        last_day = calendar.monthrange(year, month)[1]
        if n >= 1:
            first = date(year, month, 1)
            day = 1 + (weekday - first.weekday()) % 7 + 7 * (n - 1)
            if day > last_day:
                raise ValueError("the month has no such weekday")
            return date(year, month, day)
        if n == -1:
            last = date(year, month, last_day)
            return last - timedelta(days=(last.weekday() - weekday) % 7)
        raise ValueError("n must be 1 or more, or -1")
''')

ZT_ZONES = dd('''
    from collections import namedtuple
    from datetime import datetime, timedelta

    from .rules import nth_weekday

    Rule = namedtuple("Rule", "month nth weekday minute clock")
    Zone = namedtuple("Zone", "name std save start end")

    SUNDAY = 6

    ZONES = {
        "Skerry": Zone("Skerry", 0, 0, None, None),
        "Veld": Zone("Veld", 60, 60, Rule(3, -1, SUNDAY, 60, "utc"), Rule(10, -1, SUNDAY, 60, "utc")),
        "Northport": Zone("Northport", 210, 60, Rule(3, 2, SUNDAY, 120, "standard"), Rule(11, 1, SUNDAY, 120, "daylight")),
        "Tasmin": Zone("Tasmin", -570, 60, Rule(10, 1, SUNDAY, 120, "standard"), Rule(4, 1, SUNDAY, 180, "daylight")),
        "Quill": Zone("Quill", 765, 0, None, None),
    }


    def get_zone(name):
        try:
            return ZONES[name]
        except KeyError:
            raise ValueError(f"unknown zone {name!r}") from None


    def _rule_utc(zone, rule, year):
        day = nth_weekday(year, rule.month, rule.weekday, rule.nth)
        wall = datetime(day.year, day.month, day.day) + timedelta(minutes=rule.minute)
        if rule.clock == "utc":
            return wall
        if rule.clock == "standard":
            return wall - timedelta(minutes=zone.std)
        return wall - timedelta(minutes=zone.std + zone.save)


    def transitions(zone, year):
        return _rule_utc(zone, zone.start, year), _rule_utc(zone, zone.end, year)


    def is_dst(zone, utc):
        if zone.start is None:
            return False
        start, end = transitions(zone, utc.year)
        if start < end:
            return start <= utc < end
        return utc < end or utc >= start


    def offset_at_utc(zone, utc):
        return zone.std + (zone.save if is_dst(zone, utc) else 0)


    def to_local(zone, utc):
        return utc + timedelta(minutes=offset_at_utc(zone, utc))
''')

ZT_CONVERT = dd('''
    from datetime import timedelta

    from .zones import is_dst, offset_at_utc, to_local


    def to_utc(zone, local, prefer="earlier"):
        if prefer not in ("earlier", "later"):
            raise ValueError("prefer must be 'earlier' or 'later'")
        found = []
        for offset in {zone.std, zone.std + zone.save}:
            utc = local - timedelta(minutes=offset)
            if offset_at_utc(zone, utc) == offset:
                found.append(utc)
        if not found:
            raise ValueError("this local time does not exist")
        found.sort()
        return found[0] if prefer == "earlier" else found[-1]


    def convert(local, src, dst, prefer="earlier"):
        return to_local(dst, to_utc(src, local, prefer))


    def utc_offset_str(minutes):
        sign = "+" if minutes >= 0 else "-"
        hours, rest = divmod(abs(minutes), 60)
        return "%s%02d:%02d" % (sign, hours, rest)


    def describe(zone, utc):
        label = "daylight" if is_dst(zone, utc) else "standard"
        shown = to_local(zone, utc).strftime("%Y-%m-%d %H:%M")
        return "%s %s (UTC%s, %s)" % (shown, zone.name, utc_offset_str(offset_at_utc(zone, utc)), label)
''')

ZT_VISIBLE = dd('''
    import unittest
    from datetime import date, datetime

    from zonetab.convert import to_utc, utc_offset_str
    from zonetab.rules import nth_weekday
    from zonetab.zones import get_zone, to_local


    class BasicTests(unittest.TestCase):
        def test_nth_weekday(self):
            self.assertEqual(nth_weekday(2025, 3, 6, 2), date(2025, 3, 9))

        def test_skerry_is_utc(self):
            self.assertEqual(to_local(get_zone("Skerry"), datetime(2025, 7, 1, 12)), datetime(2025, 7, 1, 12))

        def test_offset_text(self):
            self.assertEqual(utc_offset_str(210), "+03:30")

        def test_plain_conversion(self):
            self.assertEqual(to_utc(get_zone("Quill"), datetime(2025, 1, 1, 12, 45)), datetime(2025, 1, 1, 0, 0))


    if __name__ == "__main__":
        unittest.main()
''')

ZT_HIDDEN = dd('''
    import unittest
    from datetime import date, datetime, timedelta

    from zonetab.convert import convert, describe, to_utc, utc_offset_str
    from zonetab.rules import nth_weekday
    from zonetab.zones import ZONES, get_zone, is_dst, offset_at_utc, to_local, transitions

    D = date
    DT = datetime
    SKERRY, VELD, NORTH, TASMIN, QUILL = (get_zone(n) for n in ("Skerry", "Veld", "Northport", "Tasmin", "Quill"))


    class Weekdays(unittest.TestCase):
        def test_nth(self):
            self.assertEqual(nth_weekday(2025, 3, 6, 2), D(2025, 3, 9))
            self.assertEqual(nth_weekday(2025, 11, 6, 1), D(2025, 11, 2))
            self.assertEqual(nth_weekday(2025, 10, 6, 1), D(2025, 10, 5))
            self.assertEqual(nth_weekday(2025, 4, 6, 1), D(2025, 4, 6))
            self.assertEqual(nth_weekday(2025, 3, 0, 1), D(2025, 3, 3))
            self.assertEqual(nth_weekday(2025, 3, 5, 1), D(2025, 3, 1))
            self.assertEqual(nth_weekday(2025, 3, 0, 5), D(2025, 3, 31))

        def test_last(self):
            self.assertEqual(nth_weekday(2025, 3, 6, -1), D(2025, 3, 30))
            self.assertEqual(nth_weekday(2025, 10, 6, -1), D(2025, 10, 26))
            self.assertEqual(nth_weekday(2024, 3, 6, -1), D(2024, 3, 31))
            self.assertEqual(nth_weekday(2024, 2, 3, -1), D(2024, 2, 29))
            self.assertEqual(nth_weekday(2025, 2, 4, -1), D(2025, 2, 28))
            self.assertEqual(nth_weekday(2025, 3, 0, -1), D(2025, 3, 31))

        def test_errors(self):
            for args in ((2025, 4, 0, 5), (2025, 3, 6, 0), (2025, 3, 6, -2), (2025, 3, 6, 6), (2025, 2, 6, 5)):
                with self.assertRaises(ValueError, msg=args):
                    nth_weekday(*args)


    class Table(unittest.TestCase):
        def test_zones(self):
            self.assertEqual(sorted(ZONES), ["Northport", "Quill", "Skerry", "Tasmin", "Veld"])
            self.assertEqual([get_zone(n).std for n in ("Skerry", "Veld", "Northport", "Tasmin", "Quill")], [0, 60, 210, -570, 765])
            self.assertEqual([get_zone(n).save for n in ("Skerry", "Veld", "Northport", "Tasmin", "Quill")], [0, 60, 60, 60, 0])

        def test_unknown_zone(self):
            for name in ("Atlantis", "", "veld"):
                with self.assertRaises(ValueError):
                    get_zone(name)


    class Transitions(unittest.TestCase):
        def test_values(self):
            self.assertEqual(transitions(VELD, 2025), (DT(2025, 3, 30, 1, 0), DT(2025, 10, 26, 1, 0)))
            self.assertEqual(transitions(VELD, 2024), (DT(2024, 3, 31, 1, 0), DT(2024, 10, 27, 1, 0)))
            self.assertEqual(transitions(NORTH, 2025), (DT(2025, 3, 8, 22, 30), DT(2025, 11, 1, 21, 30)))
            self.assertEqual(transitions(TASMIN, 2025), (DT(2025, 10, 5, 11, 30), DT(2025, 4, 6, 11, 30)))


    class Offsets(unittest.TestCase):
        def test_no_dst_zones(self):
            for utc in (DT(2025, 1, 1), DT(2025, 7, 1, 12), DT(2025, 10, 26, 1)):
                self.assertEqual(offset_at_utc(SKERRY, utc), 0)
                self.assertEqual(offset_at_utc(QUILL, utc), 765)
                self.assertFalse(is_dst(QUILL, utc))

        def test_veld_edges(self):
            self.assertEqual(offset_at_utc(VELD, DT(2025, 3, 30, 0, 59)), 60)
            self.assertEqual(offset_at_utc(VELD, DT(2025, 3, 30, 1, 0)), 120)
            self.assertEqual(offset_at_utc(VELD, DT(2025, 10, 26, 0, 59)), 120)
            self.assertEqual(offset_at_utc(VELD, DT(2025, 10, 26, 1, 0)), 60)
            self.assertEqual(offset_at_utc(VELD, DT(2025, 1, 15)), 60)
            self.assertEqual(offset_at_utc(VELD, DT(2025, 7, 15)), 120)
            self.assertEqual(offset_at_utc(VELD, DT(2025, 12, 31, 23, 59)), 60)

        def test_northport_edges(self):
            self.assertEqual(offset_at_utc(NORTH, DT(2025, 3, 8, 22, 29)), 210)
            self.assertEqual(offset_at_utc(NORTH, DT(2025, 3, 8, 22, 30)), 270)
            self.assertEqual(offset_at_utc(NORTH, DT(2025, 11, 1, 21, 29)), 270)
            self.assertEqual(offset_at_utc(NORTH, DT(2025, 11, 1, 21, 30)), 210)

        def test_tasmin_is_southern(self):
            self.assertEqual(offset_at_utc(TASMIN, DT(2025, 1, 15)), -510)
            self.assertEqual(offset_at_utc(TASMIN, DT(2025, 4, 6, 11, 29)), -510)
            self.assertEqual(offset_at_utc(TASMIN, DT(2025, 4, 6, 11, 30)), -570)
            self.assertEqual(offset_at_utc(TASMIN, DT(2025, 7, 1)), -570)
            self.assertEqual(offset_at_utc(TASMIN, DT(2025, 10, 5, 11, 29)), -570)
            self.assertEqual(offset_at_utc(TASMIN, DT(2025, 10, 5, 11, 30)), -510)
            self.assertEqual(offset_at_utc(TASMIN, DT(2025, 12, 31, 23, 0)), -510)
            self.assertTrue(is_dst(TASMIN, DT(2025, 1, 1)))
            self.assertFalse(is_dst(TASMIN, DT(2025, 6, 1)))

        def test_to_local(self):
            self.assertEqual(to_local(VELD, DT(2025, 3, 30, 1, 0)), DT(2025, 3, 30, 3, 0))
            self.assertEqual(to_local(VELD, DT(2025, 3, 30, 0, 59)), DT(2025, 3, 30, 1, 59))
            self.assertEqual(to_local(VELD, DT(2025, 10, 26, 1, 0)), DT(2025, 10, 26, 2, 0))
            self.assertEqual(to_local(NORTH, DT(2025, 11, 1, 21, 30)), DT(2025, 11, 2, 1, 0))
            self.assertEqual(to_local(NORTH, DT(2025, 11, 1, 21, 29)), DT(2025, 11, 2, 1, 59))
            self.assertEqual(to_local(TASMIN, DT(2025, 1, 15, 12, 0)), DT(2025, 1, 15, 3, 30))
            self.assertEqual(to_local(TASMIN, DT(2025, 7, 1, 12, 0)), DT(2025, 7, 1, 2, 30))
            self.assertEqual(to_local(QUILL, DT(2025, 7, 1, 12, 0)), DT(2025, 7, 2, 0, 45))


    class ToUtc(unittest.TestCase):
        def test_ordinary_times(self):
            self.assertEqual(to_utc(VELD, DT(2025, 1, 15, 12, 0)), DT(2025, 1, 15, 11, 0))
            self.assertEqual(to_utc(VELD, DT(2025, 7, 15, 12, 0)), DT(2025, 7, 15, 10, 0))
            self.assertEqual(to_utc(QUILL, DT(2025, 7, 1, 0, 45)), DT(2025, 6, 30, 12, 0))
            self.assertEqual(to_utc(SKERRY, DT(2025, 7, 1, 8, 0)), DT(2025, 7, 1, 8, 0))

        def test_ambiguous_times(self):
            local = DT(2025, 10, 26, 2, 30)
            self.assertEqual(to_utc(VELD, local), DT(2025, 10, 26, 0, 30))
            self.assertEqual(to_utc(VELD, local, "earlier"), DT(2025, 10, 26, 0, 30))
            self.assertEqual(to_utc(VELD, local, "later"), DT(2025, 10, 26, 1, 30))
            local = DT(2025, 11, 2, 1, 30)
            self.assertEqual(to_utc(NORTH, local, "earlier"), DT(2025, 11, 1, 21, 0))
            self.assertEqual(to_utc(NORTH, local, "later"), DT(2025, 11, 1, 22, 0))
            local = DT(2025, 4, 6, 2, 30)
            self.assertEqual(to_utc(TASMIN, local, "earlier"), DT(2025, 4, 6, 11, 0))
            self.assertEqual(to_utc(TASMIN, local, "later"), DT(2025, 4, 6, 12, 0))

        def test_edges_of_the_repeated_hour(self):
            self.assertEqual(to_utc(VELD, DT(2025, 10, 26, 2, 0), "earlier"), DT(2025, 10, 26, 0, 0))
            self.assertEqual(to_utc(VELD, DT(2025, 10, 26, 2, 0), "later"), DT(2025, 10, 26, 1, 0))
            self.assertEqual(to_utc(VELD, DT(2025, 10, 26, 2, 59), "later"), DT(2025, 10, 26, 1, 59))
            self.assertEqual(to_utc(VELD, DT(2025, 10, 26, 1, 59), "later"), DT(2025, 10, 25, 23, 59))
            self.assertEqual(to_utc(VELD, DT(2025, 10, 26, 3, 0), "earlier"), DT(2025, 10, 26, 2, 0))

        def test_prefer_does_not_matter_when_unambiguous(self):
            for local in (DT(2025, 7, 15, 12), DT(2025, 10, 26, 1, 30), DT(2025, 10, 26, 3, 30), DT(2025, 3, 30, 3, 0)):
                self.assertEqual(to_utc(VELD, local, "earlier"), to_utc(VELD, local, "later"), local)

        def test_missing_times(self):
            for zone, local in ((VELD, DT(2025, 3, 30, 2, 30)), (VELD, DT(2025, 3, 30, 2, 0)), (VELD, DT(2025, 3, 30, 2, 59)),
                                (NORTH, DT(2025, 3, 9, 2, 30)), (TASMIN, DT(2025, 10, 5, 2, 30))):
                with self.assertRaises(ValueError, msg=local):
                    to_utc(zone, local)
                with self.assertRaises(ValueError, msg=local):
                    to_utc(zone, local, "later")

        def test_around_the_gap(self):
            self.assertEqual(to_utc(VELD, DT(2025, 3, 30, 1, 59)), DT(2025, 3, 30, 0, 59))
            self.assertEqual(to_utc(VELD, DT(2025, 3, 30, 3, 0)), DT(2025, 3, 30, 1, 0))
            self.assertEqual(to_utc(NORTH, DT(2025, 3, 9, 1, 59)), DT(2025, 3, 8, 22, 29))
            self.assertEqual(to_utc(NORTH, DT(2025, 3, 9, 3, 0)), DT(2025, 3, 8, 22, 30))

        def test_zones_without_dst_have_no_gaps(self):
            self.assertEqual(to_utc(SKERRY, DT(2025, 3, 30, 2, 30)), DT(2025, 3, 30, 2, 30))
            self.assertEqual(to_utc(QUILL, DT(2025, 10, 26, 2, 30), "later"), DT(2025, 10, 25, 13, 45))

        def test_bad_preference(self):
            for prefer in ("", "first", "EARLIER", None):
                with self.assertRaises(ValueError, msg=prefer):
                    to_utc(VELD, DT(2025, 7, 1, 12), prefer)

        def test_round_trip(self):
            for zone in ZONES.values():
                for start in (DT(2025, 3, 29, 0), DT(2025, 4, 5, 0), DT(2025, 10, 4, 0), DT(2025, 10, 25, 0), DT(2025, 11, 1, 0)):
                    for hour in range(0, 72):
                        utc = start + timedelta(hours=hour, minutes=30)
                        local = to_local(zone, utc)
                        picks = {to_utc(zone, local, "earlier"), to_utc(zone, local, "later")}
                        self.assertIn(utc, picks, (zone.name, utc))
                        self.assertTrue(all(to_local(zone, p) == local for p in picks), (zone.name, utc))


    class Convert(unittest.TestCase):
        def test_between_zones(self):
            self.assertEqual(convert(DT(2025, 7, 1, 12, 0), VELD, NORTH), DT(2025, 7, 1, 14, 30))
            self.assertEqual(convert(DT(2025, 1, 15, 12, 0), VELD, NORTH), DT(2025, 1, 15, 14, 30))
            self.assertEqual(convert(DT(2025, 3, 15, 12, 0), VELD, NORTH), DT(2025, 3, 15, 15, 30))
            self.assertEqual(convert(DT(2025, 1, 15, 12, 0), SKERRY, TASMIN), DT(2025, 1, 15, 3, 30))
            self.assertEqual(convert(DT(2025, 7, 1, 12, 0), SKERRY, TASMIN), DT(2025, 7, 1, 2, 30))
            self.assertEqual(convert(DT(2025, 7, 1, 12, 0), QUILL, SKERRY), DT(2025, 6, 30, 23, 15))

        def test_same_zone_is_identity_except_for_gaps(self):
            self.assertEqual(convert(DT(2025, 7, 1, 12, 0), VELD, VELD), DT(2025, 7, 1, 12, 0))
            self.assertEqual(convert(DT(2025, 10, 26, 2, 30), VELD, VELD, "later"), DT(2025, 10, 26, 2, 30))

        def test_preference_is_passed_on(self):
            self.assertEqual(convert(DT(2025, 10, 26, 2, 30), VELD, SKERRY, "earlier"), DT(2025, 10, 26, 0, 30))
            self.assertEqual(convert(DT(2025, 10, 26, 2, 30), VELD, SKERRY, "later"), DT(2025, 10, 26, 1, 30))

        def test_missing_source_time(self):
            with self.assertRaises(ValueError):
                convert(DT(2025, 3, 30, 2, 30), VELD, SKERRY)


    class Text(unittest.TestCase):
        def test_offset_text(self):
            table = {0: "+00:00", 60: "+01:00", 210: "+03:30", 765: "+12:45", -570: "-09:30", -30: "-00:30", -60: "-01:00", 5: "+00:05",
                     -510: "-08:30", 840: "+14:00"}
            for minutes, text in table.items():
                self.assertEqual(utc_offset_str(minutes), text, minutes)

        def test_describe(self):
            self.assertEqual(describe(VELD, DT(2025, 7, 1, 10, 0)), "2025-07-01 12:00 Veld (UTC+02:00, daylight)")
            self.assertEqual(describe(VELD, DT(2025, 1, 1, 10, 0)), "2025-01-01 11:00 Veld (UTC+01:00, standard)")
            self.assertEqual(describe(TASMIN, DT(2025, 1, 15, 12, 0)), "2025-01-15 03:30 Tasmin (UTC-08:30, daylight)")
            self.assertEqual(describe(QUILL, DT(2025, 7, 1, 12, 0)), "2025-07-02 00:45 Quill (UTC+12:45, standard)")
            self.assertEqual(describe(SKERRY, DT(2025, 7, 1, 9, 5)), "2025-07-01 09:05 Skerry (UTC+00:00, standard)")


    if __name__ == "__main__":
        unittest.main()
''')

ZONETAB = Lib(
    name="zonetab", lang="python", title="the ferry timetable's time-zone table (`zonetab/`)",
    blurb="The ferry timetable converts departure times between harbours in different time zones with zonetab, without any system zone database.",
    files={"zonetab/__init__.py": "", "zonetab/rules.py": ZT_RULES, "zonetab/zones.py": ZT_ZONES, "zonetab/convert.py": ZT_CONVERT,
           "README.md": ZT_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": ZT_VISIBLE},
    hidden_tests={"tests/test_full.py": ZT_HIDDEN},
    mutate=["zonetab/rules.py", "zonetab/zones.py", "zonetab/convert.py"], difficulty=4, tags=["timezones", "dst", "conversion"],
    probes=[
        "nth_weekday(2025, 3, 6, 2)", "nth_weekday(2025, 10, 6, -1)", "nth_weekday(2025, 4, 0, 5)", "transitions(get_zone('Veld'), 2025)",
        "transitions(get_zone('Northport'), 2025)", "transitions(get_zone('Tasmin'), 2025)", "offset_at_utc(get_zone('Veld'), datetime(2025, 3, 30, 1, 0))",
        "offset_at_utc(get_zone('Tasmin'), datetime(2025, 7, 1))", "offset_at_utc(get_zone('Tasmin'), datetime(2025, 12, 31, 23))",
        "offset_at_utc(get_zone('Northport'), datetime(2025, 11, 1, 21, 30))", "to_local(get_zone('Veld'), datetime(2025, 10, 26, 1, 0))",
        "to_utc(get_zone('Veld'), datetime(2025, 10, 26, 2, 30), 'earlier')", "to_utc(get_zone('Veld'), datetime(2025, 10, 26, 2, 30), 'later')",
        "to_utc(get_zone('Veld'), datetime(2025, 3, 30, 2, 30))", "to_utc(get_zone('Northport'), datetime(2025, 11, 2, 1, 30), 'later')",
        "convert(datetime(2025, 3, 15, 12), get_zone('Veld'), get_zone('Northport'))", "convert(datetime(2025, 1, 15, 12), get_zone('Skerry'), get_zone('Tasmin'))",
        "utc_offset_str(-30)", "describe(get_zone('Tasmin'), datetime(2025, 1, 15, 12))",
    ],
    probe_import="from datetime import datetime\nfrom zonetab.rules import *\nfrom zonetab.zones import *\nfrom zonetab.convert import *",
)

register_libs([ZONETAB], n=10)
