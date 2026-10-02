"""Reader for calendar.txt."""
import re

import config as C

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
NUM_RE = re.compile(r"^(0|[1-9][0-9]{0,5})$")
RESERVED = {"from", "count", "of", "last", "after", "end", "days", "weeks", "months", "years", "every", "monthly", "yearly", "blank"}


class CalendarError(Exception):
    pass


class Calendar:
    def __init__(self):
        self.week = []
        self.months = []  # [name, length]
        self.inters = []  # [name, anchor, leap_only]; anchor = index of the month it follows, len(months) = end of year
        self.leap = None  # (a, b, c) with None for absent parts
        self.leapmonth = None  # month index
        self.epoch = None  # weekday index
        self.leapday = None  # name


def fail(n, msg):
    raise CalendarError("calendar.txt:%d: %s" % (n, msg))


def number(tok, n, lo, hi):
    if not NUM_RE.match(tok):
        fail(n, "bad number '%s'" % tok)
    v = int(tok)
    if v < lo or v > hi:
        fail(n, "number '%s' out of range" % tok)
    return v


def read_calendar(text):
    cal = Calendar()
    seen_names = set()
    epoch_name = None
    epoch_line = 0
    pending_anchors = []  # (inter index, month name, line) resolved after all months are known

    def claim(name, n):
        if not NAME_RE.match(name) or name in RESERVED:
            fail(n, "bad name '%s'" % name)
        if name in seen_names:
            fail(n, "duplicate name '%s'" % name)
        seen_names.add(name)

    for n, raw in enumerate(text.split("\n"), 1):
        w = raw.split("#", 1)[0].split()
        if not w:
            continue
        d = w[0]
        if d == "week":
            if not 2 <= len(w) - 1 <= 9:
                fail(n, "bad line")
            for name in w[1:]:
                if not NAME_RE.match(name) or name in RESERVED:
                    fail(n, "bad name '%s'" % name)
            if len(set(w[1:])) != len(w) - 1:
                fail(n, "duplicate name '%s'" % next(x for x in w[1:] if w[1:].count(x) > 1))
            if cal.week:
                fail(n, "duplicate 'week'")
            cal.week = w[1:]
        elif d == "month":
            if len(w) != 3:
                fail(n, "bad line")
            claim(w[1], n)
            cal.months.append([w[1], number(w[2], n, 1, C.MAX_MONTH)])
        elif d == "blank" or (d == "leapday" and C.LEAP_STYLE == "day"):
            if len(w) != 4 or w[2] != "after":
                fail(n, "bad line")
            claim(w[1], n)
            if d == "leapday":
                if cal.leapday is not None:
                    fail(n, "duplicate 'leapday'")
                if cal.leap is None:
                    fail(n, "no leap rule for 'leapday'")
                cal.leapday = w[1]
            cal.inters.append([w[1], w[3], d == "leapday"])
            pending_anchors.append((len(cal.inters) - 1, w[3], n))
        elif d == "leapmonth" and C.LEAP_STYLE == "month":
            if len(w) != 2:
                fail(n, "bad line")
            if cal.leapmonth is not None:
                fail(n, "duplicate 'leapmonth'")
            if cal.leap is None:
                fail(n, "no leap rule for 'leapmonth'")
            names = [m[0] for m in cal.months]
            if w[1] not in names:
                fail(n, "unknown month '%s'" % w[1])
            cal.leapmonth = names.index(w[1])
        elif d == "leap":
            if not 1 <= len(w) - 1 <= C.LEAP_PARTS:
                fail(n, "bad line")
            if cal.leap is not None:
                fail(n, "duplicate 'leap'")
            vals = [number(t, n, 2, 9999) for t in w[1:]]
            cal.leap = tuple(vals + [None] * (3 - len(vals)))
        elif d == "epoch":
            if len(w) != 2:
                fail(n, "bad line")
            if epoch_name is not None:
                fail(n, "duplicate 'epoch'")
            epoch_name, epoch_line = w[1], n
        else:
            fail(n, "unknown directive '%s'" % d)
    names = [m[0] for m in cal.months]
    for idx, anchor, n in pending_anchors:
        if anchor == "end":
            cal.inters[idx][1] = len(names)
        elif anchor in names:
            cal.inters[idx][1] = names.index(anchor)
        else:
            fail(n, "unknown month '%s'" % anchor)
    if not cal.week:
        raise CalendarError("calendar.txt: missing 'week'")
    if not cal.months:
        raise CalendarError("calendar.txt: missing 'month'")
    if epoch_name is None:
        raise CalendarError("calendar.txt: missing 'epoch'")
    if epoch_name not in cal.week:
        fail(epoch_line, "unknown weekday '%s'" % epoch_name)
    cal.epoch = cal.week.index(epoch_name)
    return cal
