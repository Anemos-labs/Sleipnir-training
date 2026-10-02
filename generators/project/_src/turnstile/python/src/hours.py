"""Opening hours: windows such as `mon-fri@08:00-18:00,sat@10:00-14:00` and the test whether a minute of the week lies in them."""
import re

import config as C

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
CLOCK = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")


def clock(text, allow_24=False):
    """Minutes since midnight of `HH:MM`, or None; `24:00` is accepted only for the end of a window."""
    if allow_24 and text == "24:00":
        return 1440
    m = CLOCK.match(text)
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def parse_days(text):
    """The set of weekday numbers (0 = mon) of `*`, `DAY` or `DAY-DAY` (a range may wrap around the end of the week), or None."""
    if text == "*":
        return set(range(7))
    parts = text.split("-")
    if len(parts) == 1 and parts[0] in DAYS:
        return {DAYS.index(parts[0])}
    if len(parts) == 2 and parts[0] in DAYS and parts[1] in DAYS:
        a, b = DAYS.index(parts[0]), DAYS.index(parts[1])
        out = {a}
        while a != b:
            a = (a + 1) % 7
            out.add(a)
        return out
    return None


def parse(spec):
    """A list of windows (days, start, end, crossing), or None when the specification is bad."""
    windows = []
    for part in spec.split(","):
        if part.count("@") != 1:
            return None
        days_text, span = part.split("@")
        days = parse_days(days_text)
        if days is None or span.count("-") != 1:
            return None
        a, b = span.split("-")
        start, end = clock(a), clock(b, allow_24=True)
        if start is None or end is None or start == end:
            return None
        if end < start and not C.CROSS:
            return None
        windows.append((days, start, end, end < start))
    return windows


def is_open(windows, t):
    """Whether minute `t` (since Monday 00:00 of week 0) is inside one of the windows; no windows at all means always open."""
    if windows is None:
        return True
    day, tod = (t // 1440) % 7, t % 1440
    for days, start, end, crossing in windows:
        if not crossing:
            if day in days and start <= tod < end:
                return True
        elif (day in days and tod >= start) or ((day - 1) % 7 in days and tod < end):
            return True
    return False
