"""The calendar model: year layout, day serial numbers, weekdays, date text."""
import bisect
import re

import config as C

MAX_YEAR = 9999
NUM_RE = re.compile(r"^(0|[1-9][0-9]{0,5})$")


class DateError(Exception):
    pass


class Model:
    def __init__(self, cal):
        self.cal = cal
        self.layouts = {False: self._layout(False), True: self._layout(True)}
        self.year_start = [0, 1]  # serial of the first day of year y
        self.mdays_before = [0, 0]  # month days (weekday bearing) before year y
        for y in range(1, MAX_YEAR + 1):
            lay = self.layouts[self.is_leap(y)]
            self.year_start.append(self.year_start[-1] + lay["length"])
            self.mdays_before.append(self.mdays_before[-1] + lay["mdays"])
        self.max_serial = self.year_start[MAX_YEAR + 1] - 1

    # -- layout -----------------------------------------------------------------------------------------------------
    def is_leap(self, y):
        a, b, c = self.cal.leap or (None, None, None)
        if a is None or y % a != 0:
            return False
        if b is None or y % b != 0:
            return True
        return c is not None and y % c == 0

    def _layout(self, leap):
        """Segments of a year in order: ('m', index, length) or ('b', name)."""
        cal = self.cal
        segs = []

        def inter_after(k):
            for name, anchor, leap_only in cal.inters:
                if anchor == k and (leap or not leap_only):
                    segs.append(("b", name))

        for i, (name, ln) in enumerate(cal.months):
            segs.append(("m", i, ln + (1 if leap and cal.leapmonth == i else 0)))
            inter_after(i)
        inter_after(len(cal.months))
        length = sum(s[2] if s[0] == "m" else 1 for s in segs)
        mdays = sum(s[2] for s in segs if s[0] == "m")
        return {"segs": segs, "length": length, "mdays": mdays}

    def month_len(self, i, y):
        return self.cal.months[i][1] + (1 if self.cal.leapmonth == i and self.is_leap(y) else 0)

    def max_day(self):
        return max(ln for _, ln in self.cal.months) + (1 if self.cal.leapmonth is not None else 0)

    # -- days -------------------------------------------------------------------------------------------------------
    def locate(self, y, doy):
        """(kind, ...) of day number doy (1-based) of year y: ('m', month index, day) or ('b', name)."""
        left = doy
        for seg in self.layouts[self.is_leap(y)]["segs"]:
            if seg[0] == "m":
                if left <= seg[2]:
                    return ("m", seg[1], left)
                left -= seg[2]
            else:
                if left == 1:
                    return ("b", seg[1])
                left -= 1
        raise DateError("internal")

    def doy_of_month_day(self, y, i, d):
        n = 0
        for seg in self.layouts[self.is_leap(y)]["segs"]:
            if seg[0] == "m":
                if seg[1] == i:
                    return n + d
                n += seg[2]
            else:
                n += 1
        raise DateError("internal")

    def doy_of_blank(self, y, name):
        """Day number of a blank day in year y, or None if that year has no such day."""
        n = 0
        for seg in self.layouts[self.is_leap(y)]["segs"]:
            if seg[0] == "m":
                n += seg[2]
            else:
                n += 1
                if seg[1] == name:
                    return n
        return None

    def serial(self, y, doy):
        return self.year_start[y] + doy - 1

    def from_serial(self, s):
        if s < 1 or s > self.max_serial:
            raise DateError("date out of range (year 1 to %d)" % MAX_YEAR)
        y = bisect.bisect_right(self.year_start, s, 1, MAX_YEAR + 1) - 1
        return y, s - self.year_start[y] + 1

    def weekday(self, y, doy):
        """Weekday index of a month day, None for a blank day."""
        loc = self.locate(y, doy)
        if loc[0] == "b":
            return None
        before = 0
        for seg in self.layouts[self.is_leap(y)]["segs"]:
            if seg[0] == "m":
                if seg[1] == loc[1]:
                    break
                before += seg[2]
        return (self.cal.epoch + self.mdays_before[y] + before + loc[2] - 1) % len(self.cal.week)

    # -- text -------------------------------------------------------------------------------------------------------
    def show(self, y, doy):
        loc = self.locate(y, doy)
        total = self.layouts[self.is_leap(y)]["length"]
        if loc[0] == "b":
            return "%s %d [%d/%d]" % (loc[1], y, doy, total)
        wd = self.cal.week[self.weekday(y, doy)]
        return "%s %d %s %d [%d/%d]" % (wd, loc[2], self.cal.months[loc[1]][0], y, doy, total)

    def parse_year(self, tok):
        if not NUM_RE.match(tok):
            raise DateError("bad date")
        y = int(tok)
        if not 1 <= y <= MAX_YEAR:
            raise DateError("year %d out of range (1..%d)" % (y, MAX_YEAR))
        return y

    def parse_date(self, toks):
        """Parse a date from the front of toks: ('D MONTH Y' or 'NAME Y'). Returns (y, doy, number of tokens used)."""
        if not toks:
            raise DateError("bad date")
        names = [m[0] for m in self.cal.months]
        if toks[0].isascii() and toks[0].isdigit():
            if len(toks) < 3 or not NUM_RE.match(toks[0]):
                raise DateError("bad date")
            if toks[1] not in names:
                raise DateError("unknown name '%s'" % toks[1])
            y = self.parse_year(toks[2])
            i, d = names.index(toks[1]), int(toks[0])
            ln = self.month_len(i, y)
            if not 1 <= d <= ln:
                raise DateError("day %d out of range for %s %d (1..%d)" % (d, toks[1], y, ln))
            return y, self.doy_of_month_day(y, i, d), 3
        if len(toks) < 2:
            raise DateError("bad date")
        inter = [x[0] for x in self.cal.inters]
        if toks[0] not in inter:
            raise DateError("unknown name '%s'" % toks[0])
        y = self.parse_year(toks[1])
        doy = self.doy_of_blank(y, toks[0])
        if doy is None:
            raise DateError("no such day %s %d" % (toks[0], y))
        return y, doy, 2
