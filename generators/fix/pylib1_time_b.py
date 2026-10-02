"""Python libraries, theme time/money/scheduling (batch time-b): ship-log durations, recurring-event expansion."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# shiplog: duration parsing/formatting with nautical units, watches and bells
# ======================================================================================================================

SL_README = dd('''
    # shiplog

    Duration helpers for a ship's logbook tool. A duration is a whole number of seconds (an `int`, may be negative).

    ## `parse_span(text) -> int` (`shiplog/units.py`)

    Reads text such as `"2d 4h 5m"`. A term is a number immediately followed by a unit; number and unit are not
    separated by a space. Units (case-sensitive):

    | unit | seconds |
    |------|---------|
    | `w`  | 604800  |
    | `d`  | 86400   |
    | `wt` (a watch) | 14400 |
    | `h`  | 3600    |
    | `bl` (a bell)  | 1800  |
    | `m`  | 60      |
    | `s`  | 1       |

    * Terms are separated by any mix of spaces and commas (or nothing at all: `"1h30m"`), in any order. Surrounding
      whitespace is ignored.
    * Each unit may appear at most once.
    * A number is digits with an optional decimal part (`1.5h`). The value of the term must be a whole number of
      seconds: `0.5m` is `30` but `0.25s` is an error.
    * A leading `-` (whitespace after it is allowed) negates the whole duration.
    * Empty text, unknown or upper-case units, a missing unit or number, or anything else left over is a
      `ValueError`.

    ## `format_span(seconds, max_parts=2) -> str` (`shiplog/fmt.py`)

    Formats with the units `w d h m s` only. Zero is `"0s"`; a negative duration is the format of its magnitude with
    a leading `-`. Parts are separated by one space.

    The first unit is the largest one that fits into the magnitude. The output is limited to a window of
    `max_parts` units starting there (the window stops at seconds): everything smaller than the last unit of the
    window is rounded **half up** into it, and the rounding may carry into larger units, even beyond the window's
    first unit (`86399` is `"1d"`, `604799` is `"1w"`). Units whose count is zero are left out (`3605` with
    `max_parts=3` is `"1h 5s"`). `max_parts < 1` is a `ValueError`.

    ## Watches and bells (`shiplog/watch.py`)

    The ship's day is split into watches (minutes since midnight, end exclusive): `middle` 00:00-04:00, `morning`
    04:00-08:00, `forenoon` 08:00-12:00, `afternoon` 12:00-16:00, `first dog` 16:00-18:00, `last dog` 18:00-20:00,
    `first` 20:00-24:00.

    * `watch_at(minute)` is the name of the watch. A minute outside `0..1439` is a `ValueError`.
    * `bells_at(minute)`: bells are struck on every half hour. The number of bells is the number of half hours
      elapsed since the start of the watch that is *ending or running* at that minute: the half hour at which a
      watch ends counts as the last bell of that watch. Midnight (minute `0`) therefore ends the `first` watch (8
      bells), `04:00` ends the middle watch (8 bells), `16:30` is 1 bell, `18:00` ends the first dog watch (4
      bells), `20:00` ends the last dog watch (4 bells). Every other minute has `0` bells. A minute outside
      `0..1439` is a `ValueError`.
''')

SL_UNITS = dd('''
    import re

    UNITS = {"w": 604800, "d": 86400, "wt": 14400, "h": 3600, "bl": 1800, "m": 60, "s": 1}

    _TERM = re.compile(r"(\\d+)(?:\\.(\\d+))?(wt|w|d|h|bl|m|s)")
    _SEP = re.compile(r"[\\s,]*")


    def parse_span(text):
        s = text.strip()
        sign = 1
        if s.startswith("-"):
            sign = -1
            s = s[1:].lstrip()
        if not s:
            raise ValueError("empty duration")
        pos = 0
        seen = set()
        total = 0
        while pos < len(s):
            m = _TERM.match(s, pos)
            if not m:
                raise ValueError(f"cannot read a duration at {s[pos:]!r}")
            whole, frac, unit = m.group(1), m.group(2) or "", m.group(3)
            if unit in seen:
                raise ValueError(f"unit {unit!r} given twice")
            seen.add(unit)
            scaled = int(whole + frac) * UNITS[unit]
            if scaled % 10 ** len(frac):
                raise ValueError(f"{m.group(0)!r} is not a whole number of seconds")
            total += scaled // 10 ** len(frac)
            pos = _SEP.match(s, m.end()).end()
        return sign * total
''')

SL_FMT = dd('''
    FORMAT_UNITS = [("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]


    def format_span(seconds, max_parts=2):
        if max_parts < 1:
            raise ValueError("max_parts must be at least 1")
        if seconds == 0:
            return "0s"
        sign = "-" if seconds < 0 else ""
        secs = abs(seconds)
        first = next(i for i, (_, size) in enumerate(FORMAT_UNITS) if secs >= size)
        last = min(first + max_parts - 1, len(FORMAT_UNITS) - 1)
        q = FORMAT_UNITS[last][1]
        secs = (secs + q // 2) // q * q
        parts = []
        for name, size in FORMAT_UNITS:
            if size < q:
                break
            count, secs = divmod(secs, size)
            if count:
                parts.append(str(count) + name)
        return sign + " ".join(parts)
''')

SL_WATCH = dd('''
    WATCHES = [
        ("middle", 0, 240),
        ("morning", 240, 480),
        ("forenoon", 480, 720),
        ("afternoon", 720, 960),
        ("first dog", 960, 1080),
        ("last dog", 1080, 1200),
        ("first", 1200, 1440),
    ]


    def _check(minute):
        if not 0 <= minute < 1440:
            raise ValueError(f"minute out of range: {minute!r}")


    def watch_at(minute):
        _check(minute)
        for name, start, end in WATCHES:
            if start <= minute < end:
                return name


    def bells_at(minute):
        _check(minute)
        if minute % 30:
            return 0
        t = minute if minute else 1440
        for _, start, end in WATCHES:
            if start < t <= end:
                return (t - start) // 30
''')

SL_VISIBLE = dd('''
    import unittest

    from shiplog.fmt import format_span
    from shiplog.units import parse_span
    from shiplog.watch import bells_at, watch_at


    class BasicTests(unittest.TestCase):
        def test_parse_simple(self):
            self.assertEqual(parse_span("1h 30m"), 5400)

        def test_format_simple(self):
            self.assertEqual(format_span(3661), "1h 1m")

        def test_watch(self):
            self.assertEqual(watch_at(9 * 60), "forenoon")

        def test_bells(self):
            self.assertEqual(bells_at(12 * 60 + 30), 1)


    if __name__ == "__main__":
        unittest.main()
''')

SL_HIDDEN = dd('''
    import unittest

    from shiplog.fmt import format_span
    from shiplog.units import parse_span
    from shiplog.watch import bells_at, watch_at


    class Parse(unittest.TestCase):
        def test_single_units(self):
            table = {"1w": 604800, "1d": 86400, "1wt": 14400, "1h": 3600, "1bl": 1800, "1m": 60, "1s": 1, "0s": 0,
                     "90m": 5400, "12wt": 172800, "3bl": 5400}
            for text, secs in table.items():
                self.assertEqual(parse_span(text), secs, text)

        def test_combinations_and_separators(self):
            for text in ("1h 30m", "1h30m", "1h,30m", "1h, 30m", "30m 1h", "  1h   30m  ", "1h ,  , 30m", "30m1h"):
                self.assertEqual(parse_span(text), 5400, text)
            self.assertEqual(parse_span("2d 4h 5m 6s"), 187506)
            self.assertEqual(parse_span("1wt 2bl"), 18000)
            self.assertEqual(parse_span("1w1wt"), 604800 + 14400)
            self.assertEqual(parse_span("1h 60m"), 7200)

        def test_negative(self):
            self.assertEqual(parse_span("-1h"), -3600)
            self.assertEqual(parse_span("- 1h30m"), -5400)
            self.assertEqual(parse_span("  -45s "), -45)
            self.assertEqual(parse_span("-0s"), 0)

        def test_decimals(self):
            table = {"1.5h": 5400, "0.5m": 30, "2.5d": 216000, "0.75bl": 1350, "1.25wt": 18000, "0.125w": 75600,
                     "1.50h": 5400, "0.5h 0.5m": 1830, "10.0s": 10, "0.3m": 18}
            for text, secs in table.items():
                self.assertEqual(parse_span(text), secs, text)

        def test_fractions_of_a_second_are_errors(self):
            for text in ("0.25s", "1.5s", "0.1s", "1.0001m", "0.001w", "0.01m"):
                with self.assertRaises(ValueError, msg=text):
                    parse_span(text)

        def test_duplicate_units(self):
            for text in ("1h 1h", "1h30m5m", "2wt,3wt", "1w 2d 1w"):
                with self.assertRaises(ValueError, msg=text):
                    parse_span(text)

        def test_garbage(self):
            for text in ("", "   ", "-", "h", "1", "1x", "1H", "1 h", "1.h", ".5h", "1,5h", "1h+2m", "+1h", "1h 2",
                         "1.5.5h", "1e3s", ",1h", "1h--2m", "1b", "1ms", "abc", "1h and 2m", "--1h"):
                with self.assertRaises(ValueError, msg=text):
                    parse_span(text)

        def test_watch_is_not_a_week(self):
            self.assertEqual(parse_span("2wt"), 28800)
            self.assertEqual(parse_span("2w"), 1209600)


    class Format(unittest.TestCase):
        def test_small_values(self):
            table = {0: "0s", 1: "1s", 59: "59s", 60: "1m", 61: "1m 1s", 3599: "59m 59s", 3600: "1h", 3601: "1h",
                     3661: "1h 1m", 3689: "1h 1m", 3690: "1h 2m", 86400: "1d", 7200: "2h"}
            for secs, text in table.items():
                self.assertEqual(format_span(secs), text, secs)

        def test_carry_into_larger_units(self):
            self.assertEqual(format_span(86399), "1d")
            self.assertEqual(format_span(604799), "1w")
            self.assertEqual(format_span(7199), "2h")
            self.assertEqual(format_span(7170), "2h")
            self.assertEqual(format_span(7169), "1h 59m")
            self.assertEqual(format_span(3599), "59m 59s")
            self.assertEqual(format_span(119), "1m 59s")
            self.assertEqual(format_span(119, 1), "2m")
            self.assertEqual(format_span(90061), "1d 1h")
            self.assertEqual(format_span(172799), "2d")

        def test_max_parts(self):
            self.assertEqual(format_span(5400, 1), "2h")
            self.assertEqual(format_span(5399, 1), "1h")
            self.assertEqual(format_span(89, 1), "1m")
            self.assertEqual(format_span(90, 1), "2m")
            self.assertEqual(format_span(29, 1), "29s")
            self.assertEqual(format_span(90061, 3), "1d 1h 1m")
            self.assertEqual(format_span(90061, 4), "1d 1h 1m 1s")
            self.assertEqual(format_span(90061, 5), "1d 1h 1m 1s")
            self.assertEqual(format_span(90061, 9), "1d 1h 1m 1s")
            self.assertEqual(format_span(694861, 5), "1w 1d 1h 1m 1s")
            self.assertEqual(format_span(694861, 2), "1w 1d")
            self.assertEqual(format_span(694861, 1), "1w")
            self.assertEqual(format_span(302400, 1), "4d")
            self.assertEqual(format_span(302399, 1), "3d")
            self.assertEqual(format_span(907200, 1), "2w")
            self.assertEqual(format_span(907199, 1), "1w")

        def test_zero_parts_are_left_out(self):
            self.assertEqual(format_span(3605, 5), "1h 5s")
            self.assertEqual(format_span(3605, 3), "1h 5s")
            self.assertEqual(format_span(3605, 2), "1h")
            self.assertEqual(format_span(86460, 3), "1d 1m")
            self.assertEqual(format_span(604800 + 5, 5), "1w 5s")

        def test_many_weeks(self):
            self.assertEqual(format_span(6048000), "10w")
            self.assertEqual(format_span(6048000 + 86400 * 3), "10w 3d")

        def test_negative(self):
            self.assertEqual(format_span(-90), "-1m 30s")
            self.assertEqual(format_span(-3600), "-1h")
            self.assertEqual(format_span(-1), "-1s")
            self.assertEqual(format_span(-86399), "-1d")

        def test_bad_max_parts(self):
            for n in (0, -1):
                with self.assertRaises(ValueError):
                    format_span(100, n)

        def test_round_trip(self):
            values = list(range(0, 400, 7)) + [3599, 3600, 3601, 86399, 86400, 90061, 604799, 604800, 694861, 6048000 + 17]
            for v in values:
                self.assertEqual(parse_span(format_span(v, 5)), v, v)
                self.assertEqual(parse_span(format_span(-v, 5)), -v, -v)


    class Watches(unittest.TestCase):
        def test_watch_names(self):
            table = {0: "middle", 239: "middle", 240: "morning", 479: "morning", 480: "forenoon", 719: "forenoon",
                     720: "afternoon", 959: "afternoon", 960: "first dog", 1079: "first dog", 1080: "last dog",
                     1199: "last dog", 1200: "first", 1439: "first"}
            for minute, name in table.items():
                self.assertEqual(watch_at(minute), name, minute)

        def test_bells(self):
            table = {30: 1, 60: 2, 90: 3, 120: 4, 150: 5, 180: 6, 210: 7, 240: 8, 270: 1, 480: 8, 510: 1, 720: 8,
                     750: 1, 960: 8, 990: 1, 1020: 2, 1050: 3, 1080: 4, 1110: 1, 1140: 2, 1170: 3, 1200: 4,
                     1230: 1, 1260: 2, 1410: 7, 0: 8}
            for minute, bells in table.items():
                self.assertEqual(bells_at(minute), bells, minute)

        def test_no_bells_between_half_hours(self):
            for minute in (1, 29, 31, 59, 61, 239, 241, 1199, 1439):
                self.assertEqual(bells_at(minute), 0, minute)

        def test_every_half_hour_has_bells(self):
            for minute in range(0, 1440, 30):
                self.assertTrue(1 <= bells_at(minute) <= 8, minute)

        def test_range(self):
            for minute in (-1, 1440, 5000):
                with self.assertRaises(ValueError):
                    watch_at(minute)
                with self.assertRaises(ValueError):
                    bells_at(minute)


    if __name__ == "__main__":
        unittest.main()
''')

SHIPLOG = Lib(
    name="shiplog", lang="python", title="the logbook duration helpers (`shiplog/`)",
    blurb="A ship's logbook tool reads and prints watch durations, spans of time and bell counts with shiplog.",
    files={"shiplog/__init__.py": "", "shiplog/units.py": SL_UNITS, "shiplog/fmt.py": SL_FMT,
           "shiplog/watch.py": SL_WATCH, "README.md": SL_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": SL_VISIBLE},
    hidden_tests={"tests/test_full.py": SL_HIDDEN},
    mutate=["shiplog/units.py", "shiplog/fmt.py", "shiplog/watch.py"], difficulty=3, tags=["duration", "formatting", "parsing"],
    probes=[
        "parse_span('1wt 2bl')", "parse_span('1.5h')", "parse_span('0.25s')", "parse_span('1h 1h')", "parse_span('- 1h30m')",
        "parse_span('2wt')", "format_span(3690)", "format_span(86399)", "format_span(604799)", "format_span(90061, 3)",
        "format_span(3605, 3)", "format_span(-90)", "format_span(5400, 1)", "watch_at(719)", "watch_at(720)",
        "bells_at(0)", "bells_at(240)", "bells_at(1080)", "bells_at(1200)", "bells_at(1230)",
    ],
    probe_import="from shiplog.units import *\nfrom shiplog.fmt import *\nfrom shiplog.watch import *",
)

# ======================================================================================================================
# recur: expansion of a small recurrence-rule language into dates
# ======================================================================================================================

RC_README = dd('''
    # recur

    Expands recurrence rules for a club's event calendar. Dates are `datetime.date`.

    ## `expand(rule, start, until) -> list[date]` (`recur/expand.py`)

    All dates the rule yields from `start` (included) to `until` (included), ascending, no duplicates. `until <
    start` gives `[]` (the rule is parsed first, so a bad rule is an error even then). A range of more than 3660 days (`(until - start).days > 3660`) is a `ValueError`.

    ## Rule language (`recur/rules.py`)

    Rules are case-insensitive. Leading and trailing whitespace is ignored.

        rule   := frequency [" on " selector] [" except " date ("," date)*]
        frequency := "daily" | "weekly" | "monthly" | "every N days" | "every N weeks" | "every N months"

    `N` is a whole number of at least 1 and the unit is always plural (`every 1 weeks`, not `every 1 week`). `daily`
    is `every 1 days`, `weekly` is `every 1 weeks`, `monthly` is `every 1 months`. Dates in the `except` list are
    ISO `YYYY-MM-DD` separated by commas (spaces allowed); those dates are removed from the result. Any syntax error
    is a `ValueError`.

    * **days** (`daily`, `every N days`): `start`, `start + N days`, `start + 2N days`, ... A selector is an error.
    * **weeks**: weeks are counted from the Monday of the week that holds `start`; the rule applies to every `N`-th
      week (that week, then `N` weeks later, ...). The selector is a comma-separated list of weekdays
      (`mon,tue,wed,thu,fri,sat,sun`, duplicates fine); without a selector it is the weekday of `start`. Dates before
      `start` are never produced, even when they belong to the first week.
    * **months**: the rule applies to the month of `start`, then every `N`-th month after it. The selector is one of
      `day D` (the D-th day, `1 <= D <= 31`; months that are too short are skipped), `last day`, or
      `<ordinal> <weekday>` with ordinal `1st`, `2nd`, `3rd`, `4th`, `5th` or `last` (for example `2nd tue`,
      `last fri`; a month without a 5th such weekday is skipped). Without a selector it is `day D` with `D` the day
      of the month of `start`. Dates before `start` or after `until` are not produced.

    `nth_weekday(year, month, weekday, n)` (`recur/expand.py`) returns that date (`weekday` 0 = Monday) for `n` in
    `1..5` or `-1` (the last one), or `None` when the month has no such date; any other `n` is a `ValueError`.
''')

RC_RULES = dd('''
    import re
    from collections import namedtuple
    from datetime import date

    WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    ORDINALS = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "last": -1}

    Rule = namedtuple("Rule", "unit step selector exceptions")

    _FREQ = re.compile(r"^(?:(daily|weekly|monthly)|every (\\d+) (days|weeks|months))$")
    _DAY = re.compile(r"^day (\\d{1,2})$")
    _NTH = re.compile(r"^(1st|2nd|3rd|4th|5th|last) (mon|tue|wed|thu|fri|sat|sun)$")


    def _frequency(text):
        m = _FREQ.match(text)
        if not m:
            raise ValueError(f"bad frequency {text!r}")
        if m.group(1):
            return {"daily": "days", "weekly": "weeks", "monthly": "months"}[m.group(1)], 1
        step = int(m.group(2))
        if step < 1:
            raise ValueError("step must be at least 1")
        return m.group(3), step


    def _selector(unit, text):
        if text is None:
            return None
        if unit == "days":
            raise ValueError("a daily rule takes no selector")
        if unit == "weeks":
            names = [n.strip() for n in text.split(",")]
            if any(n not in WEEKDAYS for n in names):
                raise ValueError(f"bad weekday list {text!r}")
            return tuple(sorted({WEEKDAYS.index(n) for n in names}))
        if text == "last day":
            return ("dom", -1)
        m = _DAY.match(text)
        if m:
            day = int(m.group(1))
            if not 1 <= day <= 31:
                raise ValueError(f"bad day of month {day!r}")
            return ("dom", day)
        m = _NTH.match(text)
        if m:
            return ("nth", ORDINALS[m.group(1)], WEEKDAYS.index(m.group(2)))
        raise ValueError(f"bad monthly selector {text!r}")


    def parse_rule(text):
        body = text.strip().lower()
        exceptions = ()
        if " except " in body:
            body, _, tail = body.partition(" except ")
            exceptions = tuple(sorted({date.fromisoformat(x.strip()) for x in tail.split(",")}))
        selector = None
        if " on " in body:
            body, _, selector = body.partition(" on ")
            selector = selector.strip()
        unit, step = _frequency(body.strip())
        return Rule(unit, step, _selector(unit, selector), exceptions)
''')

RC_EXPAND = dd('''
    import calendar
    from datetime import date, timedelta

    from .rules import parse_rule

    MAX_RANGE_DAYS = 3660


    def nth_weekday(year, month, weekday, n):
        if n == 0 or n < -1 or n > 5:
            raise ValueError(f"bad ordinal {n!r}")
        last_day = calendar.monthrange(year, month)[1]
        if n > 0:
            first = 1 + (weekday - date(year, month, 1).weekday()) % 7
            day = first + 7 * (n - 1)
            return date(year, month, day) if day <= last_day else None
        last = date(year, month, last_day)
        return last - timedelta(days=(last.weekday() - weekday) % 7)


    def _every_n_days(rule, start, until):
        out = []
        d = start
        while d <= until:
            out.append(d)
            d += timedelta(days=rule.step)
        return out


    def _every_n_weeks(rule, start, until):
        weekdays = rule.selector or (start.weekday(),)
        monday = start - timedelta(days=start.weekday())
        out = []
        while monday <= until:
            for wd in weekdays:
                d = monday + timedelta(days=wd)
                if start <= d <= until:
                    out.append(d)
            monday += timedelta(weeks=rule.step)
        return out


    def _pick(selector, year, month):
        if selector[0] == "dom":
            last_day = calendar.monthrange(year, month)[1]
            if selector[1] == -1:
                return date(year, month, last_day)
            return date(year, month, selector[1]) if selector[1] <= last_day else None
        return nth_weekday(year, month, selector[2], selector[1])


    def _every_n_months(rule, start, until):
        selector = rule.selector or ("dom", start.day)
        index = start.year * 12 + start.month - 1
        stop = until.year * 12 + until.month - 1
        out = []
        while index <= stop:
            year, month0 = divmod(index, 12)
            d = _pick(selector, year, month0 + 1)
            if d is not None and start <= d <= until:
                out.append(d)
            index += rule.step
        return out


    def expand(rule, start, until):
        parsed = parse_rule(rule)
        if until < start:
            return []
        if (until - start).days > MAX_RANGE_DAYS:
            raise ValueError("range too long")
        run = {"days": _every_n_days, "weeks": _every_n_weeks, "months": _every_n_months}[parsed.unit]
        skip = set(parsed.exceptions)
        return sorted({d for d in run(parsed, start, until) if d not in skip})
''')

RC_VISIBLE = dd('''
    import unittest
    from datetime import date

    from recur.expand import expand, nth_weekday


    class BasicTests(unittest.TestCase):
        def test_daily(self):
            got = expand("daily", date(2025, 3, 3), date(2025, 3, 5))
            self.assertEqual(got, [date(2025, 3, 3), date(2025, 3, 4), date(2025, 3, 5)])

        def test_weekly_default_weekday(self):
            got = expand("weekly", date(2025, 3, 3), date(2025, 3, 17))
            self.assertEqual(got, [date(2025, 3, 3), date(2025, 3, 10), date(2025, 3, 17)])

        def test_nth_weekday(self):
            self.assertEqual(nth_weekday(2025, 3, 1, 2), date(2025, 3, 11))


    if __name__ == "__main__":
        unittest.main()
''')

RC_HIDDEN = dd('''
    import unittest
    from datetime import date, timedelta

    from recur.expand import expand, nth_weekday

    D = date


    class Days(unittest.TestCase):
        def test_daily(self):
            self.assertEqual(expand("daily", D(2025, 3, 3), D(2025, 3, 6)), [D(2025, 3, d) for d in (3, 4, 5, 6)])

        def test_every_n_days(self):
            self.assertEqual(expand("every 3 days", D(2025, 3, 3), D(2025, 3, 12)), [D(2025, 3, d) for d in (3, 6, 9, 12)])
            self.assertEqual(expand("every 3 days", D(2025, 3, 3), D(2025, 3, 11)), [D(2025, 3, d) for d in (3, 6, 9)])
            self.assertEqual(expand("every 10 days", D(2025, 2, 20), D(2025, 3, 25)),
                             [D(2025, 2, 20), D(2025, 3, 2), D(2025, 3, 12), D(2025, 3, 22)])

        def test_range_edges(self):
            self.assertEqual(expand("daily", D(2025, 3, 3), D(2025, 3, 3)), [D(2025, 3, 3)])
            self.assertEqual(expand("daily", D(2025, 3, 4), D(2025, 3, 3)), [])
            self.assertEqual(expand("every 5 days", D(2025, 3, 3), D(2025, 3, 7)), [D(2025, 3, 3)])

        def test_exceptions(self):
            self.assertEqual(expand("every 2 days except 2025-03-05", D(2025, 3, 3), D(2025, 3, 9)),
                             [D(2025, 3, 3), D(2025, 3, 7), D(2025, 3, 9)])
            self.assertEqual(expand("daily except 2025-03-03, 2025-03-05", D(2025, 3, 3), D(2025, 3, 6)),
                             [D(2025, 3, 4), D(2025, 3, 6)])
            self.assertEqual(expand("daily except 2025-04-01", D(2025, 3, 3), D(2025, 3, 4)), [D(2025, 3, 3), D(2025, 3, 4)])

        def test_selector_not_allowed(self):
            with self.assertRaises(ValueError):
                expand("daily on mon", D(2025, 3, 3), D(2025, 3, 9))
            with self.assertRaises(ValueError):
                expand("every 2 days on mon", D(2025, 3, 3), D(2025, 3, 9))


    class Weeks(unittest.TestCase):
        def test_default_weekday(self):
            self.assertEqual(expand("weekly", D(2025, 3, 3), D(2025, 3, 24)), [D(2025, 3, d) for d in (3, 10, 17, 24)])
            self.assertEqual(expand("weekly", D(2025, 3, 5), D(2025, 3, 25)), [D(2025, 3, d) for d in (5, 12, 19)])
            self.assertEqual(expand("weekly", D(2025, 3, 9), D(2025, 3, 23)), [D(2025, 3, d) for d in (9, 16, 23)])

        def test_weekday_list(self):
            self.assertEqual(expand("weekly on mon,thu", D(2025, 3, 3), D(2025, 3, 14)), [D(2025, 3, d) for d in (3, 6, 10, 13)])
            self.assertEqual(expand("weekly on thu,mon", D(2025, 3, 3), D(2025, 3, 14)), [D(2025, 3, d) for d in (3, 6, 10, 13)])
            self.assertEqual(expand("weekly on sun,mon", D(2025, 3, 3), D(2025, 3, 17)), [D(2025, 3, d) for d in (3, 9, 10, 16, 17)])
            self.assertEqual(expand("weekly on mon,mon", D(2025, 3, 3), D(2025, 3, 11)), [D(2025, 3, 3), D(2025, 3, 10)])

        def test_nothing_before_start(self):
            self.assertEqual(expand("weekly on mon,thu", D(2025, 3, 4), D(2025, 3, 13)), [D(2025, 3, d) for d in (6, 10, 13)])
            self.assertEqual(expand("weekly on sun", D(2025, 3, 3), D(2025, 3, 3)), [])
            self.assertEqual(expand("weekly on mon", D(2025, 3, 3), D(2025, 3, 3)), [D(2025, 3, 3)])

        def test_until_cuts_the_week(self):
            self.assertEqual(expand("weekly on mon,fri", D(2025, 3, 3), D(2025, 3, 6)), [D(2025, 3, 3)])
            self.assertEqual(expand("weekly on mon,fri", D(2025, 3, 3), D(2025, 3, 7)), [D(2025, 3, 3), D(2025, 3, 7)])

        def test_every_n_weeks(self):
            self.assertEqual(expand("every 2 weeks on tue,fri", D(2025, 3, 7), D(2025, 4, 5)),
                             [D(2025, 3, 7), D(2025, 3, 18), D(2025, 3, 21), D(2025, 4, 1), D(2025, 4, 4)])
            self.assertEqual(expand("every 3 weeks", D(2025, 3, 5), D(2025, 5, 14)),
                             [D(2025, 3, 5), D(2025, 3, 26), D(2025, 4, 16), D(2025, 5, 7)])

        def test_weeks_start_on_monday(self):
            # start on a Sunday: its week began on Monday 3 March; the next applicable week is two weeks later
            self.assertEqual(expand("every 2 weeks on sun,mon", D(2025, 3, 9), D(2025, 3, 31)),
                             [D(2025, 3, 9), D(2025, 3, 17), D(2025, 3, 23), D(2025, 3, 31)])

        def test_exceptions_and_case(self):
            self.assertEqual(expand("WEEKLY ON Mon,THU except 2025-03-06", D(2025, 3, 3), D(2025, 3, 14)),
                             [D(2025, 3, d) for d in (3, 10, 13)])
            self.assertEqual(expand("  weekly  ", D(2025, 3, 3), D(2025, 3, 10)), [D(2025, 3, 3), D(2025, 3, 10)])

        def test_step_one_is_fine(self):
            self.assertEqual(expand("every 1 days", D(2025, 3, 3), D(2025, 3, 4)), [D(2025, 3, 3), D(2025, 3, 4)])
            self.assertEqual(expand("every 1 weeks", D(2025, 3, 3), D(2025, 3, 10)), [D(2025, 3, 3), D(2025, 3, 10)])
            self.assertEqual(expand("every 1 months", D(2025, 3, 3), D(2025, 4, 3)), [D(2025, 3, 3), D(2025, 4, 3)])

        def test_bad_selectors(self):
            for rule in ("weekly on funday", "weekly on mon,funday", "weekly on funday,mon", "weekly on 2nd tue", "weekly on day 3", "weekly on", "weekly on mon,", "weekly on mon tue"):
                with self.assertRaises(ValueError, msg=rule):
                    expand(rule, D(2025, 3, 3), D(2025, 3, 9))


    class Months(unittest.TestCase):
        def test_default_day_of_month(self):
            self.assertEqual(expand("monthly", D(2025, 1, 15), D(2025, 4, 30)), [D(2025, m, 15) for m in (1, 2, 3, 4)])
            self.assertEqual(expand("monthly", D(2025, 1, 31), D(2025, 6, 30)), [D(2025, 1, 31), D(2025, 3, 31), D(2025, 5, 31)])
            self.assertEqual(expand("monthly", D(2025, 1, 15), D(2025, 4, 14)), [D(2025, m, 15) for m in (1, 2, 3)])
            self.assertEqual(expand("monthly", D(2025, 11, 20), D(2026, 2, 20)),
                             [D(2025, 11, 20), D(2025, 12, 20), D(2026, 1, 20), D(2026, 2, 20)])

        def test_day_selector(self):
            self.assertEqual(expand("monthly on day 1", D(2025, 3, 2), D(2025, 6, 30)), [D(2025, m, 1) for m in (4, 5, 6)])
            self.assertEqual(expand("monthly on day 30", D(2025, 1, 1), D(2025, 4, 30)), [D(2025, 1, 30), D(2025, 3, 30), D(2025, 4, 30)])
            self.assertEqual(expand("monthly on day 29", D(2024, 1, 1), D(2024, 3, 31)), [D(2024, m, 29) for m in (1, 2, 3)])
            self.assertEqual(expand("monthly on day 29", D(2025, 1, 1), D(2025, 3, 31)), [D(2025, 1, 29), D(2025, 3, 29)])

        def test_every_n_months(self):
            self.assertEqual(expand("every 2 months on day 31", D(2025, 1, 1), D(2025, 12, 31)),
                             [D(2025, 1, 31), D(2025, 3, 31), D(2025, 5, 31), D(2025, 7, 31)])
            self.assertEqual(expand("every 3 months", D(2025, 2, 10), D(2026, 3, 1)),
                             [D(2025, 2, 10), D(2025, 5, 10), D(2025, 8, 10), D(2025, 11, 10), D(2026, 2, 10)])
            self.assertEqual(expand("every 12 months", D(2024, 2, 29), D(2029, 3, 1)), [D(2024, 2, 29), D(2028, 2, 29)])

        def test_last_day(self):
            self.assertEqual(expand("monthly on last day", D(2025, 1, 1), D(2025, 4, 30)),
                             [D(2025, 1, 31), D(2025, 2, 28), D(2025, 3, 31), D(2025, 4, 30)])
            self.assertEqual(expand("monthly on last day", D(2024, 1, 1), D(2024, 3, 31)),
                             [D(2024, 1, 31), D(2024, 2, 29), D(2024, 3, 31)])
            self.assertEqual(expand("monthly on last day", D(2025, 1, 31), D(2025, 1, 31)), [D(2025, 1, 31)])

        def test_nth_weekday_selector(self):
            self.assertEqual(expand("monthly on 2nd tue", D(2025, 3, 1), D(2025, 5, 31)), [D(2025, 3, 11), D(2025, 4, 8), D(2025, 5, 13)])
            self.assertEqual(expand("monthly on 1st mon", D(2025, 3, 1), D(2025, 5, 31)), [D(2025, 3, 3), D(2025, 4, 7), D(2025, 5, 5)])
            self.assertEqual(expand("monthly on 3rd sat", D(2025, 3, 1), D(2025, 4, 30)), [D(2025, 3, 15), D(2025, 4, 19)])
            self.assertEqual(expand("monthly on 4th thu", D(2025, 11, 1), D(2025, 12, 31)), [D(2025, 11, 27), D(2025, 12, 25)])
            self.assertEqual(expand("monthly on 1st sat", D(2025, 3, 1), D(2025, 3, 31)), [D(2025, 3, 1)])

        def test_last_weekday(self):
            self.assertEqual(expand("monthly on last fri", D(2025, 3, 1), D(2025, 5, 31)), [D(2025, 3, 28), D(2025, 4, 25), D(2025, 5, 30)])
            self.assertEqual(expand("monthly on last mon", D(2025, 3, 1), D(2025, 3, 31)), [D(2025, 3, 31)])
            self.assertEqual(expand("monthly on last sun", D(2025, 2, 1), D(2025, 3, 31)), [D(2025, 2, 23), D(2025, 3, 30)])

        def test_fifth_weekday_skips_months(self):
            self.assertEqual(expand("monthly on 5th fri", D(2025, 1, 1), D(2025, 12, 31)),
                             [D(2025, 1, 31), D(2025, 5, 30), D(2025, 8, 29), D(2025, 10, 31)])

        def test_start_inside_the_month(self):
            self.assertEqual(expand("monthly on 2nd tue", D(2025, 3, 12), D(2025, 4, 30)), [D(2025, 4, 8)])
            self.assertEqual(expand("monthly on 2nd tue", D(2025, 3, 11), D(2025, 4, 30)), [D(2025, 3, 11), D(2025, 4, 8)])
            self.assertEqual(expand("monthly on 2nd tue", D(2025, 3, 1), D(2025, 4, 7)), [D(2025, 3, 11)])
            self.assertEqual(expand("monthly on 2nd tue", D(2025, 3, 1), D(2025, 4, 8)), [D(2025, 3, 11), D(2025, 4, 8)])

        def test_year_boundary(self):
            self.assertEqual(expand("every 2 months on last day", D(2025, 9, 1), D(2026, 3, 31)),
                             [D(2025, 9, 30), D(2025, 11, 30), D(2026, 1, 31), D(2026, 3, 31)])

        def test_exceptions(self):
            self.assertEqual(expand("monthly on last fri except 2025-04-25", D(2025, 3, 1), D(2025, 5, 31)), [D(2025, 3, 28), D(2025, 5, 30)])

        def test_bad_selectors(self):
            for rule in ("monthly on mon", "monthly on day 0", "monthly on day 32", "monthly on 6th fri", "monthly on 0th fri",
                         "monthly on tue 2nd", "monthly on day", "monthly on last", "monthly on 15th", "monthly on mon,tue",
                         "monthly on 2nd funday"):
                with self.assertRaises(ValueError, msg=rule):
                    expand(rule, D(2025, 3, 1), D(2025, 4, 30))


    class Grammar(unittest.TestCase):
        def test_bad_frequency(self):
            for rule in ("", "hourly", "every day", "every 2 day", "every 0 days", "every 0 weeks", "every 2 weeks2", "every -1 days",
                         "every 2", "every days", "daily daily", "yearly", "every 1.5 weeks", "daily except", "monthly on"):
                with self.assertRaises(ValueError, msg=rule):
                    expand(rule, D(2025, 3, 1), D(2025, 3, 5))

        def test_bad_exception_dates(self):
            for rule in ("daily except 2025-13-01", "daily except tomorrow", "daily except 2025-03-04,", "daily except 2025-02-30"):
                with self.assertRaises(ValueError, msg=rule):
                    expand(rule, D(2025, 3, 1), D(2025, 3, 5))

        def test_range_limit(self):
            with self.assertRaises(ValueError):
                expand("daily", D(2025, 1, 1), D(2036, 1, 4))
            self.assertEqual(len(expand("monthly", D(2025, 1, 1), D(2035, 1, 1))), 121)

        def test_range_limit_is_inclusive_of_3660_days(self):
            start = D(2025, 1, 1)
            self.assertEqual(len(expand("every 100 days", start, start + timedelta(days=3660))), 37)
            with self.assertRaises(ValueError):
                expand("every 100 days", start, start + timedelta(days=3661))

        def test_nothing_checked_when_until_is_before_start(self):
            self.assertEqual(expand("daily", D(2025, 3, 5), D(2020, 1, 1)), [])
            with self.assertRaises(ValueError):
                expand("nonsense", D(2025, 3, 5), D(2020, 1, 1))


    class NthWeekday(unittest.TestCase):
        def test_values(self):
            self.assertEqual(nth_weekday(2025, 3, 1, 2), D(2025, 3, 11))
            self.assertEqual(nth_weekday(2025, 3, 0, 1), D(2025, 3, 3))
            self.assertEqual(nth_weekday(2025, 3, 5, 1), D(2025, 3, 1))
            self.assertEqual(nth_weekday(2025, 3, 5, 5), D(2025, 3, 29))
            self.assertEqual(nth_weekday(2025, 3, 6, 5), D(2025, 3, 30))
            self.assertEqual(nth_weekday(2025, 3, 0, 5), D(2025, 3, 31))
            self.assertEqual(nth_weekday(2025, 4, 0, 5), None)
            self.assertEqual(nth_weekday(2025, 2, 4, 4), D(2025, 2, 28))
            self.assertEqual(nth_weekday(2025, 2, 4, 5), None)
            self.assertEqual(nth_weekday(2024, 2, 3, 5), D(2024, 2, 29))

        def test_last(self):
            self.assertEqual(nth_weekday(2025, 3, 0, -1), D(2025, 3, 31))
            self.assertEqual(nth_weekday(2025, 3, 6, -1), D(2025, 3, 30))
            self.assertEqual(nth_weekday(2025, 3, 4, -1), D(2025, 3, 28))
            self.assertEqual(nth_weekday(2025, 3, 1, -1), D(2025, 3, 25))
            self.assertEqual(nth_weekday(2025, 2, 4, -1), D(2025, 2, 28))
            self.assertEqual(nth_weekday(2024, 2, 3, -1), D(2024, 2, 29))
            self.assertEqual(nth_weekday(2025, 6, 6, -1), D(2025, 6, 29))

        def test_bad_ordinal(self):
            for n in (0, 6, -2, 10):
                with self.assertRaises(ValueError):
                    nth_weekday(2025, 3, 1, n)


    if __name__ == "__main__":
        unittest.main()
''')

RECUR = Lib(
    name="recurrules", lang="python", title="the recurrence-rule expander (`recur/`)",
    blurb="The club calendar generates its event dates from short text rules with the recur package.",
    files={"recur/__init__.py": "", "recur/rules.py": RC_RULES, "recur/expand.py": RC_EXPAND,
           "README.md": RC_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": RC_VISIBLE},
    hidden_tests={"tests/test_full.py": RC_HIDDEN},
    mutate=["recur/rules.py", "recur/expand.py"], difficulty=4, tags=["recurrence", "calendar", "parsing"],
    probes=[
        "expand('weekly on mon,thu', date(2025, 3, 4), date(2025, 3, 13))",
        "expand('every 2 weeks on tue,fri', date(2025, 3, 7), date(2025, 4, 5))",
        "expand('every 2 weeks on sun,mon', date(2025, 3, 9), date(2025, 3, 31))",
        "expand('monthly', date(2025, 1, 31), date(2025, 6, 30))",
        "expand('monthly on last day', date(2025, 1, 1), date(2025, 3, 31))",
        "expand('monthly on 2nd tue', date(2025, 3, 12), date(2025, 4, 30))",
        "expand('monthly on 5th fri', date(2025, 1, 1), date(2025, 6, 30))",
        "expand('monthly on last fri except 2025-04-25', date(2025, 3, 1), date(2025, 5, 31))",
        "expand('every 3 days', date(2025, 3, 3), date(2025, 3, 12))",
        "expand('daily except 2025-03-03, 2025-03-05', date(2025, 3, 3), date(2025, 3, 6))",
        "nth_weekday(2025, 3, 6, -1)", "nth_weekday(2025, 4, 0, 5)", "expand('every 0 days', date(2025, 3, 1), date(2025, 3, 5))",
    ],
    probe_import="from datetime import date\nfrom recur.expand import *\nfrom recur.rules import *",
)

register_libs([SHIPLOG, RECUR], n=10)
