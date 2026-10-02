"""The script commands."""
import re

import config as C
from model import MAX_YEAR, DateError

INT_RE = re.compile(r"^[+-]?(0|[1-9][0-9]{0,5})$")
UNITS = ("days", "weeks", "months", "years")
MAX_COUNT = 50


def count_text(n, noun):
    return "%d %s%s" % (n, noun, "" if abs(n) == 1 else "s")


class Commands:
    def __init__(self, model):
        self.m = model
        self.cal = model.cal

    # -- helpers ----------------------------------------------------------------------------------------------------
    def date_only(self, toks):
        y, doy, used = self.m.parse_date(toks)
        if used != len(toks):
            raise DateError("bad date")
        return y, doy

    def spec_and_rest(self, toks):
        y, doy, used = self.m.parse_date(toks)
        return y, doy, toks[used:]

    def integer(self, tok):
        if not INT_RE.match(tok):
            raise DateError("bad number '%s'" % tok)
        return int(tok)

    def month_index(self, name):
        names = [m[0] for m in self.cal.months]
        if name not in names:
            raise DateError("unknown name '%s'" % name)
        return names.index(name)

    def weekday_index(self, name):
        if name not in self.cal.week:
            raise DateError("unknown name '%s'" % name)
        return self.cal.week.index(name)

    # -- commands ---------------------------------------------------------------------------------------------------
    def date(self, toks):
        y, doy = self.date_only(toks)
        return [self.m.show(y, doy)]

    def serial(self, toks):
        y, doy = self.date_only(toks)
        return [str(self.m.serial(y, doy))]

    def year(self, toks):
        if len(toks) != 1:
            raise DateError("usage: year YEAR")
        y = self.m.parse_year(toks[0])
        lay = self.m.layouts[self.m.is_leap(y)]
        out = ["year %d: %d days, %s" % (y, lay["length"], "leap" if self.m.is_leap(y) else "common")]
        for seg in lay["segs"]:
            out.append("  %s %d" % (self.cal.months[seg[1]][0], seg[2]) if seg[0] == "m" else "  ~ %s" % seg[1])
        return out

    def diff(self, toks):
        y1, d1, rest = self.spec_and_rest(toks)
        y2, d2 = self.date_only(rest)
        n = self.m.serial(y2, d2) - self.m.serial(y1, d1)
        return [count_text(n, "day")]

    def add(self, toks):
        y, doy, rest = self.spec_and_rest(toks)
        if len(rest) != 2:
            raise DateError("usage: add DATE N days|weeks|months|years")
        n = self.integer(rest[0])
        unit = rest[1]
        if unit not in UNITS:
            raise DateError("bad unit '%s'" % unit)
        s = self.m.serial(y, doy)
        if unit in ("days", "weeks"):
            ny, ndoy = self.m.from_serial(s + n * (len(self.cal.week) if unit == "weeks" else 1))
            return [self.m.show(ny, ndoy)]
        loc = self.m.locate(y, doy)
        if unit == "months":
            if loc[0] == "b":
                raise DateError("cannot add months to a blank day")
            total = y * len(self.cal.months) + loc[1] + n
            ny, i = total // len(self.cal.months), total % len(self.cal.months)
            return [self.place(ny, i, loc[2])]
        ny = y + n
        if not 1 <= ny <= MAX_YEAR:
            raise DateError("date out of range (year 1 to %d)" % MAX_YEAR)
        if loc[0] == "b":
            d = self.m.doy_of_blank(ny, loc[1])
            if d is None:
                raise DateError("no such day %s %d" % (loc[1], ny))
            return [self.m.show(ny, d)]
        return [self.place(ny, loc[1], loc[2])]

    def place(self, y, i, d):
        """Day d of month i in year y, with the overflow rule for days the month does not have."""
        if not 1 <= y <= MAX_YEAR:
            raise DateError("date out of range (year 1 to %d)" % MAX_YEAR)
        ln = self.m.month_len(i, y)
        if d <= ln:
            return self.m.show(y, self.m.doy_of_month_day(y, i, d))
        if C.OVERFLOW == "clamp":
            return self.m.show(y, self.m.doy_of_month_day(y, i, ln))
        if C.OVERFLOW == "spill":
            ny, ndoy = self.m.from_serial(self.m.serial(y, self.m.doy_of_month_day(y, i, 1)) + d - 1)
            return self.m.show(ny, ndoy)
        raise DateError("no such day %d %s %d" % (d, self.cal.months[i][0], y))

    def nth_in_month(self, y, i, k, wd):
        """Date (y, doy) of the k-th (or last, k == 0) month day with weekday wd in month i of year y, or None."""
        ln = self.m.month_len(i, y)
        first = self.m.doy_of_month_day(y, i, 1)
        w = len(self.cal.week)
        d1 = (wd - self.m.weekday(y, first)) % w + 1  # the first day of the month with that weekday
        if d1 > ln:
            return None
        d = d1 + (ln - d1) // w * w if k == 0 else d1 + (k - 1) * w
        return (y, first + d - 1) if d <= ln else None

    def nth(self, toks):
        if len(toks) != 5 or toks[2] != "of":
            raise DateError("usage: nth K|last WEEKDAY of MONTH YEAR")
        if toks[0] == "last":
            k = 0
        elif re.match(r"^[1-9]$", toks[0]):
            k = int(toks[0])
        else:
            raise DateError("bad number '%s'" % toks[0])
        wd = self.weekday_index(toks[1])
        i = self.month_index(toks[3])
        y = self.m.parse_year(toks[4])
        r = self.nth_in_month(y, i, k, wd)
        return [self.m.show(*r) if r else "none"]

    def next(self, toks):
        if "from" not in toks:
            raise DateError("usage: next RULE from DATE [count N]")
        k = toks.index("from")
        rule = toks[:k]
        y0, d0, rest = self.spec_and_rest(toks[k + 1:])
        count = 5
        if rest:
            if len(rest) != 2 or rest[0] != "count":
                raise DateError("usage: next RULE from DATE [count N]")
            if not re.match(r"^[1-9][0-9]{0,2}$", rest[1]) or int(rest[1]) > MAX_COUNT:
                raise DateError("bad count '%s'" % rest[1])
            count = int(rest[1])
        start = self.m.serial(y0, d0)
        out = []
        for s in self.occurrences(rule, y0, start):
            out.append(self.m.show(*self.m.from_serial(s)))
            if len(out) == count:
                break
        return out

    def occurrences(self, rule, y0, start):
        """Serial numbers of the occurrences (>= start) of a rule, in order; a generator that ends at the last year."""
        m = self.m
        if len(rule) == 3 and rule[0] == "every" and rule[2] in ("days", "weeks"):
            if not re.match(r"^[1-9][0-9]{0,2}$", rule[1]):
                raise DateError("bad number '%s'" % rule[1])
            step = int(rule[1]) * (len(self.cal.week) if rule[2] == "weeks" else 1)
            return self.every(start, step)
        if len(rule) == 2 and rule[0] == "monthly" and rule[1].isascii() and rule[1].isdigit():
            if not re.match(r"^[1-9][0-9]{0,2}$", rule[1]) or int(rule[1]) > m.max_day():
                raise DateError("day %s never occurs" % rule[1])
            return self.monthly_day(int(rule[1]), y0, start)
        if len(rule) == 3 and rule[0] == "monthly":
            if rule[1] == "last":
                k = 0
            elif re.match(r"^[1-9]$", rule[1]):
                k = int(rule[1])
            else:
                raise DateError("bad number '%s'" % rule[1])
            wd = self.weekday_index(rule[2])
            return self.monthly_weekday(k, wd, y0, start)
        if len(rule) == 3 and rule[0] == "yearly":
            if not re.match(r"^[1-9][0-9]{0,2}$", rule[1]):
                raise DateError("bad number '%s'" % rule[1])
            i = self.month_index(rule[2])
            if int(rule[1]) > m.cal.months[i][1] + (1 if m.cal.leapmonth == i else 0):
                raise DateError("day %s never occurs" % rule[1])
            return self.yearly(int(rule[1]), i, y0, start)
        if len(rule) == 2 and rule[0] == "blank":
            if rule[1] not in [x[0] for x in self.cal.inters]:
                raise DateError("unknown name '%s'" % rule[1])
            return self.blank(rule[1], y0, start)
        raise DateError("bad rule")

    def every(self, start, step):
        s = start
        while s <= self.m.max_serial:
            yield s
            s += step

    def monthly_day(self, d, y0, start):
        m = self.m
        for y in range(y0, MAX_YEAR + 1):
            for i in range(len(self.cal.months)):
                ln = m.month_len(i, y)
                if d > ln and C.SHORT_MONTH == "skip":
                    continue
                s = m.serial(y, m.doy_of_month_day(y, i, min(d, ln)))
                if s >= start:
                    yield s

    def monthly_weekday(self, k, wd, y0, start):
        for y in range(y0, MAX_YEAR + 1):
            for i in range(len(self.cal.months)):
                r = self.nth_in_month(y, i, k, wd)
                if r and self.m.serial(*r) >= start:
                    yield self.m.serial(*r)

    def yearly(self, d, i, y0, start):
        m = self.m
        for y in range(y0, MAX_YEAR + 1):
            if d <= m.month_len(i, y):
                s = m.serial(y, m.doy_of_month_day(y, i, d))
                if s >= start:
                    yield s

    def blank(self, name, y0, start):
        for y in range(y0, MAX_YEAR + 1):
            doy = self.m.doy_of_blank(y, name)
            if doy is not None and self.m.serial(y, doy) >= start:
                yield self.m.serial(y, doy)
