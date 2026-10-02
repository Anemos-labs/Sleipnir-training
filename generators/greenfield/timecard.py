"""Shift-sheet CLI: shift-line validation, breaks and rounding, weekly overtime, daily limits, holidays and pay (invented payroll rules)."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

PY = r'''
import sys

CMD_CHECK = "@C_CHECK@"
CMD_TOTAL = "@C_TOTAL@"
CMD_WEEKS = "@C_WEEKS@"
CMD_PAY = "@C_PAY@"
HAS_WEEKS = @WEEKS@
HAS_PAY = @PAY@
HAS_AUTO = @AUTO@
HAS_DAILY = @DAILY@
TFMT = "@TFMT@"
ROUND = @ROUND@
RMODE = "@RMODE@"
AUTO_AFTER = @AUTO_AFTER@
AUTO_MIN = @AUTO_MIN@
MAXSHIFT = @MAXSHIFT@
WSTART = @WSTART@
THRESH = @THRESH@
MULT_NUM = @MULT_NUM@
MULT_DEN = @MULT_DEN@
DAILY = @DAILY_MIN@
NMAX = @NMAX@

LOW = "abcdefghijklmnopqrstuvwxyz"
DG = "0123456789"
MDAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


class Usage(Exception):
    pass


class Bad(Exception):
    pass


def leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_from_civil(y, m, d):
    """days since 2000-01-01"""
    n = 0
    for yy in range(2000, y):
        n += 366 if leap(yy) else 365
    for mm in range(1, m):
        n += MDAYS[mm - 1] + (1 if mm == 2 and leap(y) else 0)
    return n + d - 1


def civil_from_days(n):
    y = 2000
    while True:
        ylen = 366 if leap(y) else 365
        if n < ylen:
            break
        n -= ylen
        y += 1
    m = 1
    while True:
        ml = MDAYS[m - 1] + (1 if m == 2 and leap(y) else 0)
        if n < ml:
            break
        n -= ml
        m += 1
    return y, m, n + 1


def parse_date(s):
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return None
    if not all(c in DG for c in s[:4] + s[5:7] + s[8:]):
        return None
    y, m, d = int(s[:4]), int(s[5:7]), int(s[8:])
    if not (2000 <= y <= 2099 and 1 <= m <= 12):
        return None
    if not (1 <= d <= MDAYS[m - 1] + (1 if m == 2 and leap(y) else 0)):
        return None
    return days_from_civil(y, m, d)


def parse_time(s):
    if len(s) != 5 or s[2] != ":" or not all(c in DG for c in s[:2] + s[3:]):
        return None
    h, m = int(s[:2]), int(s[3:])
    if h > 23 or m > 59:
        return None
    return h * 60 + m


def good_name(s):
    return 1 <= len(s) <= NMAX and s[0] in LOW and all(c in LOW + DG + "_" for c in s)


def rnd(n):
    if ROUND <= 1:
        return n
    if RMODE == "nearest":
        return (2 * n + ROUND) // (2 * ROUND) * ROUND
    if RMODE == "up":
        return (n + ROUND - 1) // ROUND * ROUND
    return n // ROUND * ROUND


def parse_line(line):
    f = line.split(" ")
    if len(f) not in (4, 5):
        return "fields"
    name, date, tin, tout = f[:4]
    if not good_name(name):
        return "name"
    day = parse_date(date)
    if day is None:
        return "date"
    a, b = parse_time(tin), parse_time(tout)
    if a is None or b is None:
        return "time"
    brk = None
    if len(f) == 5:
        s = f[4]
        if not (1 <= len(s) <= 3 and all(c in DG for c in s) and (len(s) == 1 or s[0] != "0") and int(s) <= 180):
            return "break"
        brk = int(s)
    if a == b:
        return "times"
    gross = b - a if b > a else b + 1440 - a
    if gross > MAXSHIFT:
        return "long"
    if brk is not None and brk >= gross:
        return "breaklen"
    if brk is not None:
        ded = brk
    elif HAS_AUTO and gross > AUTO_AFTER:
        ded = AUTO_MIN
    else:
        ded = 0
    return (name, day, rnd(gross - ded))


def fmt(n):
    if TFMT == "hm":
        return "%d:%02d" % (n // 60, n % 60)
    h = (n * 200 + 60) // 120
    return "%d.%02d" % (h // 100, h % 100)


def money(c):
    return "%d.%02d" % (c // 100, c % 100)


def week_start(day):
    wd = (day + 5) % 7
    return day - (wd - WSTART) % 7


def date_text(day):
    y, m, d = civil_from_days(day)
    return "%04d-%02d-%02d" % (y, m, d)


def split(rows, holidays):
    """(name, weekstart) -> [regular, overtime]"""
    days = {}
    for name, day, mins in rows:
        days[(name, day)] = days.get((name, day), 0) + mins
    weeks = {}
    for (name, day), tot in days.items():
        ws = week_start(day)
        w = weeks.setdefault((name, ws), [0, 0, 0])  # candidate regular, overtime, holiday
        if day in holidays:
            w[2] += tot
        else:
            reg = min(tot, DAILY) if HAS_DAILY else tot
            w[0] += reg
            w[1] += tot - reg
    out = {}
    for k, (cand, ot, hol) in weeks.items():
        reg = min(cand, THRESH * 60)
        out[k] = [reg, ot + (cand - reg) + hol]
    return out


def run(argv, text):
    try:
        return do_run(argv, text)
    except Usage:
        return "", 2


def do_run(argv, text):
    if not argv:
        raise Usage()
    cmd = argv[0]
    rates = {}
    holidays = set()
    if cmd in (CMD_CHECK, CMD_TOTAL) or (HAS_WEEKS and cmd == CMD_WEEKS):
        if len(argv) != 1:
            raise Usage()
    elif HAS_PAY and cmd == CMD_PAY:
        i = 1
        while i < len(argv):
            if i + 1 >= len(argv):
                raise Usage()
            opt, val = argv[i], argv[i + 1]
            if opt == "--rate":
                nm, eq, cents = val.partition("=")
                if not eq or not good_name(nm) or nm in rates:
                    raise Usage()
                if not (1 <= len(cents) <= 6 and all(c in DG for c in cents) and cents[0] != "0"):
                    raise Usage()
                rates[nm] = int(cents)
            elif opt == "--holiday":
                d = parse_date(val)
                if d is None:
                    raise Usage()
                holidays.add(d)
            else:
                raise Usage()
            i += 2
    else:
        raise Usage()
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    rows = []
    for n, line in enumerate(lines, 1):
        r = parse_line(line)
        if isinstance(r, str):
            return "error: line %d: %s\n" % (n, r), 1
        rows.append(r)
    if cmd == CMD_CHECK:
        return "ok %d shifts\n" % len(rows), 0
    if cmd == CMD_TOTAL:
        tot = {}
        for name, day, mins in rows:
            tot[name] = tot.get(name, 0) + mins
        return "".join("%s %s\n" % (n, fmt(tot[n])) for n in sorted(tot)), 0
    ws = split(rows, holidays)
    if cmd == CMD_WEEKS:
        return "".join("%s %s %s %s\n" % (n, date_text(w), fmt(v[0]), fmt(v[1])) for (n, w), v in sorted(ws.items())), 0
    names = sorted({n for n, _ in ws})
    for n in names:
        if n not in rates:
            return "error: rate %s\n" % n, 1
    out = []
    total = 0
    for n in names:
        cents = 0
        for (nn, w), (reg, ot) in ws.items():
            if nn == n:
                numer = (reg * MULT_DEN + ot * MULT_NUM) * rates[n]
                denom = 60 * MULT_DEN
                cents += (2 * numer + denom) // (2 * denom)
        total += cents
        out.append("%s %s\n" % (n, money(cents)))
    if names:
        out.append("TOTAL %s\n" % money(total))
    return "".join(out), 0


def main():
    out, code = run(sys.argv[1:], sys.stdin.read())
    if code == 2:
        sys.stderr.write("usage: timecard COMMAND [OPTIONS]\n")
    sys.stdout.write(out)
    return code


if __name__ == "__main__":
    sys.exit(main())
'''

GO = r'''
package main

import (
	"fmt"
	"io"
	"os"
	"sort"
	"strconv"
	"strings"
)

const (
	cmdCheck  = "@C_CHECK@"
	cmdTotal  = "@C_TOTAL@"
	cmdWeeks  = "@C_WEEKS@"
	cmdPay    = "@C_PAY@"
	hasWeeks  = @WEEKS@
	hasPay    = @PAY@
	hasAuto   = @AUTO@
	hasDaily  = @DAILY@
	tfmt      = "@TFMT@"
	roundTo   = @ROUND@
	rmode     = "@RMODE@"
	autoAfter = @AUTO_AFTER@
	autoMin   = @AUTO_MIN@
	maxShift  = @MAXSHIFT@
	wstart    = @WSTART@
	thresh    = @THRESH@
	multNum   = @MULT_NUM@
	multDen   = @MULT_DEN@
	dailyMin  = @DAILY_MIN@
	nmax      = @NMAX@
)

var mdays = []int{31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31}

type row struct {
	name string
	day  int
	mins int
}

func isDig(c byte) bool { return c >= '0' && c <= '9' }

func allDig(s string) bool {
	for i := 0; i < len(s); i++ {
		if !isDig(s[i]) {
			return false
		}
	}
	return true
}

func leap(y int) bool { return y%4 == 0 && (y%100 != 0 || y%400 == 0) }

func monthLen(y, m int) int {
	if m == 2 && leap(y) {
		return 29
	}
	return mdays[m-1]
}

func daysFromCivil(y, m, d int) int {
	n := 0
	for yy := 2000; yy < y; yy++ {
		if leap(yy) {
			n += 366
		} else {
			n += 365
		}
	}
	for mm := 1; mm < m; mm++ {
		n += monthLen(y, mm)
	}
	return n + d - 1
}

func civilFromDays(n int) (int, int, int) {
	y := 2000
	for {
		yl := 365
		if leap(y) {
			yl = 366
		}
		if n < yl {
			break
		}
		n -= yl
		y++
	}
	m := 1
	for n >= monthLen(y, m) {
		n -= monthLen(y, m)
		m++
	}
	return y, m, n + 1
}

func parseDate(s string) (int, bool) {
	if len(s) != 10 || s[4] != '-' || s[7] != '-' || !allDig(s[:4]) || !allDig(s[5:7]) || !allDig(s[8:]) {
		return 0, false
	}
	y, _ := strconv.Atoi(s[:4])
	m, _ := strconv.Atoi(s[5:7])
	d, _ := strconv.Atoi(s[8:])
	if y < 2000 || y > 2099 || m < 1 || m > 12 || d < 1 || d > monthLen(y, m) {
		return 0, false
	}
	return daysFromCivil(y, m, d), true
}

func parseTime(s string) (int, bool) {
	if len(s) != 5 || s[2] != ':' || !allDig(s[:2]) || !allDig(s[3:]) {
		return 0, false
	}
	h, _ := strconv.Atoi(s[:2])
	m, _ := strconv.Atoi(s[3:])
	if h > 23 || m > 59 {
		return 0, false
	}
	return h*60 + m, true
}

func goodName(s string) bool {
	if len(s) < 1 || len(s) > nmax || !(s[0] >= 'a' && s[0] <= 'z') {
		return false
	}
	for i := 0; i < len(s); i++ {
		c := s[i]
		if !(c >= 'a' && c <= 'z') && !isDig(c) && c != '_' {
			return false
		}
	}
	return true
}

func rnd(n int) int {
	if roundTo <= 1 {
		return n
	}
	switch rmode {
	case "nearest":
		return (2*n + roundTo) / (2 * roundTo) * roundTo
	case "up":
		return (n + roundTo - 1) / roundTo * roundTo
	}
	return n / roundTo * roundTo
}

func parseLine(line string) (row, string) {
	f := strings.Split(line, " ")
	if len(f) != 4 && len(f) != 5 {
		return row{}, "fields"
	}
	if !goodName(f[0]) {
		return row{}, "name"
	}
	day, ok := parseDate(f[1])
	if !ok {
		return row{}, "date"
	}
	a, ok1 := parseTime(f[2])
	b, ok2 := parseTime(f[3])
	if !ok1 || !ok2 {
		return row{}, "time"
	}
	brk := -1
	if len(f) == 5 {
		s := f[4]
		if !(len(s) >= 1 && len(s) <= 3 && allDig(s) && (len(s) == 1 || s[0] != '0')) {
			return row{}, "break"
		}
		brk, _ = strconv.Atoi(s)
		if brk > 180 {
			return row{}, "break"
		}
	}
	if a == b {
		return row{}, "times"
	}
	gross := b - a
	if b < a {
		gross = b + 1440 - a
	}
	if gross > maxShift {
		return row{}, "long"
	}
	if brk >= 0 && brk >= gross {
		return row{}, "breaklen"
	}
	ded := 0
	if brk >= 0 {
		ded = brk
	} else if hasAuto && gross > autoAfter {
		ded = autoMin
	}
	return row{f[0], day, rnd(gross - ded)}, ""
}

func fmtT(n int) string {
	if tfmt == "hm" {
		return fmt.Sprintf("%d:%02d", n/60, n%60)
	}
	h := (n*200 + 60) / 120
	return fmt.Sprintf("%d.%02d", h/100, h%100)
}

func money(c int) string { return fmt.Sprintf("%d.%02d", c/100, c%100) }

func weekStart(day int) int {
	wd := (day + 5) % 7
	return day - ((wd-wstart)%7+7)%7
}

func dateText(day int) string {
	y, m, d := civilFromDays(day)
	return fmt.Sprintf("%04d-%02d-%02d", y, m, d)
}

type wkey struct {
	name string
	ws   int
}

func split(rows []row, hol map[int]bool) map[wkey][2]int {
	type dk struct {
		name string
		day  int
	}
	days := map[dk]int{}
	for _, r := range rows {
		days[dk{r.name, r.day}] += r.mins
	}
	weeks := map[wkey]*[3]int{}
	for k, tot := range days {
		wk := wkey{k.name, weekStart(k.day)}
		w := weeks[wk]
		if w == nil {
			w = &[3]int{}
			weeks[wk] = w
		}
		if hol[k.day] {
			w[2] += tot
		} else {
			reg := tot
			if hasDaily && dailyMin < tot {
				reg = dailyMin
			}
			w[0] += reg
			w[1] += tot - reg
		}
	}
	out := map[wkey][2]int{}
	for k, w := range weeks {
		reg := w[0]
		if thresh*60 < reg {
			reg = thresh * 60
		}
		out[k] = [2]int{reg, w[1] + (w[0] - reg) + w[2]}
	}
	return out
}

func sortedKeys(m map[wkey][2]int) []wkey {
	ks := make([]wkey, 0, len(m))
	for k := range m {
		ks = append(ks, k)
	}
	sort.Slice(ks, func(a, b int) bool {
		if ks[a].name != ks[b].name {
			return ks[a].name < ks[b].name
		}
		return ks[a].ws < ks[b].ws
	})
	return ks
}

func usage() int {
	fmt.Fprintln(os.Stderr, "usage: timecard COMMAND [OPTIONS]")
	return 2
}

func run(args []string) int {
	if len(args) == 0 {
		return usage()
	}
	cmd := args[0]
	rates := map[string]int{}
	hol := map[int]bool{}
	if cmd == cmdCheck || cmd == cmdTotal || (hasWeeks && cmd == cmdWeeks) {
		if len(args) != 1 {
			return usage()
		}
	} else if hasPay && cmd == cmdPay {
		for i := 1; i < len(args); i += 2 {
			if i+1 >= len(args) {
				return usage()
			}
			opt, val := args[i], args[i+1]
			if opt == "--rate" {
				eq := strings.IndexByte(val, '=')
				if eq < 0 {
					return usage()
				}
				nm, cents := val[:eq], val[eq+1:]
				if _, dup := rates[nm]; !goodName(nm) || dup {
					return usage()
				}
				if !(len(cents) >= 1 && len(cents) <= 6 && allDig(cents) && cents[0] != '0') {
					return usage()
				}
				rates[nm], _ = strconv.Atoi(cents)
			} else if opt == "--holiday" {
				d, ok := parseDate(val)
				if !ok {
					return usage()
				}
				hol[d] = true
			} else {
				return usage()
			}
		}
	} else {
		return usage()
	}
	data, _ := io.ReadAll(os.Stdin)
	lines := strings.Split(string(data), "\n")
	if len(lines) > 0 && lines[len(lines)-1] == "" {
		lines = lines[:len(lines)-1]
	}
	var rows []row
	for n, line := range lines {
		r, why := parseLine(line)
		if why != "" {
			fmt.Printf("error: line %d: %s\n", n+1, why)
			return 1
		}
		rows = append(rows, r)
	}
	switch cmd {
	case cmdCheck:
		fmt.Printf("ok %d shifts\n", len(rows))
		return 0
	case cmdTotal:
		tot := map[string]int{}
		for _, r := range rows {
			tot[r.name] += r.mins
		}
		names := make([]string, 0, len(tot))
		for n := range tot {
			names = append(names, n)
		}
		sort.Strings(names)
		for _, n := range names {
			fmt.Printf("%s %s\n", n, fmtT(tot[n]))
		}
		return 0
	}
	ws := split(rows, hol)
	keys := sortedKeys(ws)
	if hasWeeks && cmd == cmdWeeks {
		for _, k := range keys {
			v := ws[k]
			fmt.Printf("%s %s %s %s\n", k.name, dateText(k.ws), fmtT(v[0]), fmtT(v[1]))
		}
		return 0
	}
	var names []string
	seen := map[string]bool{}
	for _, k := range keys {
		if !seen[k.name] {
			seen[k.name] = true
			names = append(names, k.name)
		}
	}
	for _, n := range names {
		if _, ok := rates[n]; !ok {
			fmt.Printf("error: rate %s\n", n)
			return 1
		}
	}
	total := 0
	for _, n := range names {
		cents := 0
		for _, k := range keys {
			if k.name == n {
				v := ws[k]
				numer := (v[0]*multDen + v[1]*multNum) * rates[n]
				denom := 60 * multDen
				cents += (2*numer + denom) / (2 * denom)
			}
		}
		total += cents
		fmt.Printf("%s %s\n", n, money(cents))
	}
	if len(names) > 0 {
		fmt.Printf("TOTAL %s\n", money(total))
	}
	return 0
}

func main() {
	os.Exit(run(os.Args[1:]))
}
'''

SH = r'''
#!/usr/bin/env bash
# timecard: shift logs to totals, weekly splits and pay
exec awk -v C_CHECK=@C_CHECK@ -v C_TOTAL=@C_TOTAL@ -v C_WEEKS=@C_WEEKS@ -v C_PAY=@C_PAY@ \
  -v HAS_WEEKS=@WEEKS_SH@ -v HAS_PAY=@PAY_SH@ -v HAS_AUTO=@AUTO_SH@ -v HAS_DAILY=@DAILY_SH@ -v TFMT=@TFMT@ -v ROUND=@ROUND@ -v RMODE=@RMODE@ \
  -v AUTO_AFTER=@AUTO_AFTER@ -v AUTO_MIN=@AUTO_MIN@ -v MAXSHIFT=@MAXSHIFT@ -v WSTART=@WSTART@ -v THRESH=@THRESH@ \
  -v MULT_NUM=@MULT_NUM@ -v MULT_DEN=@MULT_DEN@ -v DAILY=@DAILY_MIN@ -v NMAX=@NMAX@ '
function leap(y) { return (y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)) }
function mlen(y, m) { if (m == 2 && leap(y)) return 29; return MD[m] }
function dfc(y, m, d,   n, yy, mm) {
  n = 0
  for (yy = 2000; yy < y; yy++) n += leap(yy) ? 366 : 365
  for (mm = 1; mm < m; mm++) n += mlen(y, mm)
  return n + d - 1
}
function cfd(n,   y, m, yl) {
  y = 2000
  while (1) {
    yl = leap(y) ? 366 : 365
    if (n < yl) break
    n -= yl; y++
  }
  m = 1
  while (n >= mlen(y, m)) { n -= mlen(y, m); m++ }
  return sprintf("%04d-%02d-%02d", y, m, n + 1)
}
function pdate(s,   y, m, d) {
  if (s !~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]$/) return -1
  y = substr(s, 1, 4) + 0; m = substr(s, 6, 2) + 0; d = substr(s, 9, 2) + 0
  if (y < 2000 || y > 2099 || m < 1 || m > 12 || d < 1 || d > mlen(y, m)) return -1
  return dfc(y, m, d)
}
function ptime(s,   h, m) {
  if (s !~ /^[0-9][0-9]:[0-9][0-9]$/) return -1
  h = substr(s, 1, 2) + 0; m = substr(s, 4, 2) + 0
  if (h > 23 || m > 59) return -1
  return h * 60 + m
}
function goodname(s) { return (length(s) >= 1 && length(s) <= NMAX && s ~ /^[a-z][a-z0-9_]*$/) }
function rnd(n) {
  if (ROUND <= 1) return n
  if (RMODE == "nearest") return int((2 * n + ROUND) / (2 * ROUND)) * ROUND
  if (RMODE == "up") return int((n + ROUND - 1) / ROUND) * ROUND
  return int(n / ROUND) * ROUND
}
function fmt(n,   h) {
  if (TFMT == "hm") return sprintf("%d:%02d", int(n / 60), n % 60)
  h = int((n * 200 + 60) / 120)
  return sprintf("%d.%02d", int(h / 100), h % 100)
}
function money(c) { return sprintf("%d.%02d", int(c / 100), c % 100) }
function wstartof(day,   wd, d) {
  wd = (day + 5) % 7
  d = (wd - WSTART) % 7
  if (d < 0) d += 7
  return day - d
}
function pline(line,   f, nf, a, b, s, brk, gross, ded, day) {
  nf = split(line, f, "[ ]")
  if (nf != 4 && nf != 5) return "fields"
  if (!goodname(f[1])) return "name"
  day = pdate(f[2])
  if (day < 0) return "date"
  a = ptime(f[3]); b = ptime(f[4])
  if (a < 0 || b < 0) return "time"
  brk = -1
  if (nf == 5) {
    s = f[5]
    if (s !~ /^([0-9]|[1-9][0-9]|[1-9][0-9][0-9])$/) return "break"
    brk = s + 0
    if (brk > 180) return "break"
  }
  if (a == b) return "times"
  gross = (b > a) ? b - a : b + 1440 - a
  if (gross > MAXSHIFT) return "long"
  if (brk >= 0 && brk >= gross) return "breaklen"
  if (brk >= 0) ded = brk
  else if (HAS_AUTO && gross > AUTO_AFTER) ded = AUTO_MIN
  else ded = 0
  R_NAME = f[1]; R_DAY = day; R_MINS = rnd(gross - ded)
  return ""
}
BEGIN {
  split("31 28 31 30 31 30 31 31 30 31 30 31", MD, " ")
  SORT = "LC_ALL=C sort"
  nargs = ARGC - 1
  CMD = ARGV[1]
  usage = 0
  if (nargs == 0) usage = 1
  else if (CMD == C_CHECK || CMD == C_TOTAL || (HAS_WEEKS && CMD == C_WEEKS)) { if (nargs != 1) usage = 1 }
  else if (HAS_PAY && CMD == C_PAY) {
    for (i = 2; i <= nargs && !usage; i += 2) {
      if (i + 1 > nargs) { usage = 1; break }
      opt = ARGV[i]; val = ARGV[i + 1]
      if (opt == "--rate") {
        eq = index(val, "=")
        if (eq == 0) { usage = 1; break }
        nm = substr(val, 1, eq - 1); cents = substr(val, eq + 1)
        if (!goodname(nm) || (nm in rate)) { usage = 1; break }
        if (cents !~ /^[1-9][0-9]?[0-9]?[0-9]?[0-9]?[0-9]?$/) { usage = 1; break }
        rate[nm] = cents + 0
      } else if (opt == "--holiday") {
        d = pdate(val)
        if (d < 0) { usage = 1; break }
        hol[d] = 1
      } else { usage = 1; break }
    }
  } else usage = 1
  if (usage) exit 2
  ARGC = 1
  nrows = 0
}
{
  why = pline($0)
  if (why != "") {
    printf "error: line %d: %s\n", NR, why
    fail = 1
    exit 1
  }
  nrows++
  tot[R_NAME] += R_MINS
  dayt[R_NAME SUBSEP R_DAY] += R_MINS
}
END {
  if (usage) exit 2
  if (fail) exit 1
  if (CMD == C_CHECK) { printf "ok %d shifts\n", nrows; exit 0 }
  if (CMD == C_TOTAL) {
    for (n in tot) print n " " fmt(tot[n]) | SORT
    close(SORT)
    exit 0
  }
  for (k in dayt) {
    split(k, kk, SUBSEP)
    name = kk[1]; day = kk[2] + 0
    wk = name SUBSEP wstartof(day)
    if (day in hol) hl[wk] += dayt[k]
    else {
      reg = dayt[k]
      if (HAS_DAILY && DAILY < reg) reg = DAILY
      cand[wk] += reg
      ot[wk] += dayt[k] - reg
    }
    seen[wk] = 1
  }
  for (wk in seen) {
    r = cand[wk] + 0
    if (THRESH * 60 < r) r = THRESH * 60
    regm[wk] = r
    otm[wk] = ot[wk] + (cand[wk] - r) + hl[wk]
  }
  if (CMD == C_WEEKS) {
    for (wk in seen) {
      split(wk, kk, SUBSEP)
      print kk[1] " " cfd(kk[2] + 0) " " fmt(regm[wk]) " " fmt(otm[wk]) | SORT
    }
    close(SORT)
    exit 0
  }
  nn = 0
  for (wk in seen) { split(wk, kk, SUBSEP); if (!(kk[1] in isn)) { isn[kk[1]] = 1; nn++ } }
  miss = ""
  for (n in isn) if (!(n in rate) && (miss == "" || n < miss)) miss = n
  if (miss != "") { printf "error: rate %s\n", miss; fail = 1; exit 1 }
  total = 0
  for (n in isn) {
    cents = 0
    for (wk in seen) {
      split(wk, kk, SUBSEP)
      if (kk[1] == n) {
        numer = (regm[wk] * MULT_DEN + otm[wk] * MULT_NUM) * rate[n]
        denom = 60 * MULT_DEN
        cents += int((2 * numer + denom) / (2 * denom))
      }
    }
    total += cents
    print n " " money(cents) | SORT
  }
  close(SORT)
  if (nn > 0) printf "TOTAL %s\n", money(total)
  exit 0
}' "$@"
'''

CC = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CMD_CHECK "@C_CHECK@"
#define CMD_TOTAL "@C_TOTAL@"
#define CMD_WEEKS "@C_WEEKS@"
#define CMD_PAY "@C_PAY@"
#define HAS_WEEKS @WEEKS_SH@
#define HAS_PAY @PAY_SH@
#define HAS_AUTO @AUTO_SH@
#define HAS_DAILY @DAILY_SH@
#define TFMT_HM @TFMT_HM@
#define ROUND @ROUND@
#define RMODE_NEAREST @RM_NEAREST@
#define RMODE_UP @RM_UP@
#define AUTO_AFTER @AUTO_AFTER@
#define AUTO_MIN @AUTO_MIN@
#define MAXSHIFT @MAXSHIFT@
#define WSTART @WSTART@
#define THRESH @THRESH@
#define MULT_NUM @MULT_NUM@
#define MULT_DEN @MULT_DEN@
#define DAILY @DAILY_MIN@
#define NMAX @NMAX@

static const int MDAYS[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};

typedef struct { char name[24]; int day; long mins; } Row;
typedef struct { char name[24]; int key; long a, b, c; } Agg; /* key: day or week start */

static int leap(int y) { return y % 4 == 0 && (y % 100 != 0 || y % 400 == 0); }
static int mlen(int y, int m) { return (m == 2 && leap(y)) ? 29 : MDAYS[m - 1]; }

static int dfc(int y, int m, int d) {
    int n = 0;
    for (int yy = 2000; yy < y; yy++) n += leap(yy) ? 366 : 365;
    for (int mm = 1; mm < m; mm++) n += mlen(y, mm);
    return n + d - 1;
}

static void cfd(int n, char *out) {
    int y = 2000;
    for (;;) {
        int yl = leap(y) ? 366 : 365;
        if (n < yl) break;
        n -= yl;
        y++;
    }
    int m = 1;
    while (n >= mlen(y, m)) { n -= mlen(y, m); m++; }
    sprintf(out, "%04d-%02d-%02d", y, m, n + 1);
}

static int all_dig(const char *s, int n) {
    for (int i = 0; i < n; i++)
        if (s[i] < '0' || s[i] > '9') return 0;
    return 1;
}

static int num(const char *s, int n) {
    int v = 0;
    for (int i = 0; i < n; i++) v = v * 10 + (s[i] - '0');
    return v;
}

static int pdate(const char *s) {
    if (strlen(s) != 10 || s[4] != '-' || s[7] != '-' || !all_dig(s, 4) || !all_dig(s + 5, 2) || !all_dig(s + 8, 2)) return -1;
    int y = num(s, 4), m = num(s + 5, 2), d = num(s + 8, 2);
    if (y < 2000 || y > 2099 || m < 1 || m > 12 || d < 1 || d > mlen(y, m)) return -1;
    return dfc(y, m, d);
}

static int ptime(const char *s) {
    if (strlen(s) != 5 || s[2] != ':' || !all_dig(s, 2) || !all_dig(s + 3, 2)) return -1;
    int h = num(s, 2), m = num(s + 3, 2);
    if (h > 23 || m > 59) return -1;
    return h * 60 + m;
}

static int good_name(const char *s) {
    size_t n = strlen(s);
    if (n < 1 || n > NMAX || !(s[0] >= 'a' && s[0] <= 'z')) return 0;
    for (size_t i = 0; i < n; i++) {
        char c = s[i];
        if (!(c >= 'a' && c <= 'z') && !(c >= '0' && c <= '9') && c != '_') return 0;
    }
    return 1;
}

static long rnd(long n) {
    if (ROUND <= 1) return n;
    if (RMODE_NEAREST) return (2 * n + ROUND) / (2 * ROUND) * ROUND;
    if (RMODE_UP) return (n + ROUND - 1) / ROUND * ROUND;
    return n / ROUND * ROUND;
}

static void fmt_t(long n, char *out) {
    if (TFMT_HM) {
        sprintf(out, "%ld:%02ld", n / 60, n % 60);
    } else {
        long h = (n * 200 + 60) / 120;
        sprintf(out, "%ld.%02ld", h / 100, h % 100);
    }
}

static void money(long c, char *out) { sprintf(out, "%ld.%02ld", c / 100, c % 100); }

static int week_start(int day) {
    int wd = (day + 5) % 7;
    int d = ((wd - WSTART) % 7 + 7) % 7;
    return day - d;
}

/* returns NULL when the line is fine, else the reason; fills r */
static const char *pline(char *line, Row *r) {
    char *f[8];
    int nf = 0;
    char *p = line;
    for (;;) {
        char *e = strchr(p, ' ');
        if (nf < 8) f[nf] = p;
        nf++;
        if (!e) break;
        *e = 0;
        p = e + 1;
    }
    if (nf != 4 && nf != 5) return "fields";
    if (!good_name(f[0])) return "name";
    int day = pdate(f[1]);
    if (day < 0) return "date";
    int a = ptime(f[2]), b = ptime(f[3]);
    if (a < 0 || b < 0) return "time";
    int brk = -1;
    if (nf == 5) {
        size_t n = strlen(f[4]);
        if (!(n >= 1 && n <= 3 && all_dig(f[4], (int)n) && (n == 1 || f[4][0] != '0'))) return "break";
        brk = num(f[4], (int)n);
        if (brk > 180) return "break";
    }
    if (a == b) return "times";
    int gross = b > a ? b - a : b + 1440 - a;
    if (gross > MAXSHIFT) return "long";
    if (brk >= 0 && brk >= gross) return "breaklen";
    int ded = 0;
    if (brk >= 0) ded = brk;
    else if (HAS_AUTO && gross > AUTO_AFTER) ded = AUTO_MIN;
    strcpy(r->name, f[0]);
    r->day = day;
    r->mins = rnd(gross - ded);
    return NULL;
}

static int usage(void) {
    fprintf(stderr, "usage: timecard COMMAND [OPTIONS]\n");
    return 2;
}

static Agg *find_agg(Agg **arr, int *n, int *cap, const char *name, int key) {
    for (int i = 0; i < *n; i++)
        if (strcmp((*arr)[i].name, name) == 0 && (*arr)[i].key == key) return &(*arr)[i];
    if (*n == *cap) {
        *cap = *cap ? *cap * 2 : 16;
        *arr = realloc(*arr, (size_t)*cap * sizeof(Agg));
    }
    Agg *g = &(*arr)[(*n)++];
    memset(g, 0, sizeof *g);
    strcpy(g->name, name);
    g->key = key;
    return g;
}

static int cmp_agg(const void *x, const void *y) {
    const Agg *a = x, *b = y;
    int c = strcmp(a->name, b->name);
    if (c) return c;
    return a->key < b->key ? -1 : a->key > b->key;
}

int main(int argc, char **argv) {
    if (argc < 2) return usage();
    const char *cmd = argv[1];
    char rate_name[64][24];
    long rate_cents[64];
    int nrates = 0;
    int hol[64];
    int nhol = 0;
    int is_pay = 0;
    if (strcmp(cmd, CMD_CHECK) == 0 || strcmp(cmd, CMD_TOTAL) == 0 || (HAS_WEEKS && strcmp(cmd, CMD_WEEKS) == 0)) {
        if (argc != 2) return usage();
    } else if (HAS_PAY && strcmp(cmd, CMD_PAY) == 0) {
        is_pay = 1;
        for (int i = 2; i < argc; i += 2) {
            if (i + 1 >= argc) return usage();
            const char *opt = argv[i], *val = argv[i + 1];
            if (strcmp(opt, "--rate") == 0) {
                const char *eq = strchr(val, '=');
                if (!eq || eq - val > 23) return usage();
                char nm[24];
                memcpy(nm, val, (size_t)(eq - val));
                nm[eq - val] = 0;
                const char *cents = eq + 1;
                size_t cl = strlen(cents);
                if (!good_name(nm)) return usage();
                for (int j = 0; j < nrates; j++)
                    if (strcmp(rate_name[j], nm) == 0) return usage();
                if (!(cl >= 1 && cl <= 6 && all_dig(cents, (int)cl) && cents[0] != '0')) return usage();
                if (nrates >= 64) return usage();
                strcpy(rate_name[nrates], nm);
                rate_cents[nrates++] = num(cents, (int)cl);
            } else if (strcmp(opt, "--holiday") == 0) {
                int d = pdate(val);
                if (d < 0 || nhol >= 64) return usage();
                hol[nhol++] = d;
            } else {
                return usage();
            }
        }
    } else {
        return usage();
    }
    size_t cap = 4096, len = 0;
    char *buf = malloc(cap);
    size_t got;
    while ((got = fread(buf + len, 1, cap - len, stdin)) > 0) {
        len += got;
        if (len == cap) {
            cap *= 2;
            buf = realloc(buf, cap);
        }
    }
    buf[len] = 0;
    Row *rows = NULL;
    int nrows = 0, caprows = 0;
    size_t pos = 0;
    int lineno = 0;
    while (pos < len) {
        char *e = memchr(buf + pos, '\n', len - pos);
        size_t ll = e ? (size_t)(e - (buf + pos)) : len - pos;
        char *line = malloc(ll + 1);
        memcpy(line, buf + pos, ll);
        line[ll] = 0;
        pos += ll + (e ? 1 : 0);
        lineno++;
        if (nrows == caprows) {
            caprows = caprows ? caprows * 2 : 64;
            rows = realloc(rows, (size_t)caprows * sizeof(Row));
        }
        const char *why = pline(line, &rows[nrows]);
        free(line);
        if (why) {
            printf("error: line %d: %s\n", lineno, why);
            return 1;
        }
        nrows++;
    }
    char tb[64], tb2[64];
    if (strcmp(cmd, CMD_CHECK) == 0) {
        printf("ok %d shifts\n", nrows);
        return 0;
    }
    if (strcmp(cmd, CMD_TOTAL) == 0) {
        Agg *tot = NULL;
        int nt = 0, ct = 0;
        for (int i = 0; i < nrows; i++) find_agg(&tot, &nt, &ct, rows[i].name, 0)->a += rows[i].mins;
        if (nt) qsort(tot, (size_t)nt, sizeof(Agg), cmp_agg);
        for (int i = 0; i < nt; i++) {
            fmt_t(tot[i].a, tb);
            printf("%s %s\n", tot[i].name, tb);
        }
        return 0;
    }
    Agg *days = NULL;
    int nd = 0, cd = 0;
    for (int i = 0; i < nrows; i++) find_agg(&days, &nd, &cd, rows[i].name, rows[i].day)->a += rows[i].mins;
    Agg *wk = NULL;
    int nw = 0, cw = 0;
    for (int i = 0; i < nd; i++) {
        Agg *w = find_agg(&wk, &nw, &cw, days[i].name, week_start(days[i].key));
        int is_hol = 0;
        for (int h = 0; h < nhol; h++)
            if (hol[h] == days[i].key) is_hol = 1;
        long tot = days[i].a;
        if (is_hol) {
            w->c += tot;
        } else {
            long reg = tot;
            if (HAS_DAILY && DAILY < reg) reg = DAILY;
            w->a += reg;
            w->b += tot - reg;
        }
    }
    long regm[512], otm[512];
    for (int i = 0; i < nw; i++) {
        long r = wk[i].a;
        if (THRESH * 60 < r) r = THRESH * 60;
        regm[i] = r;
        otm[i] = wk[i].b + (wk[i].a - r) + wk[i].c;
    }
    /* sort weeks together with their results */
    int order[512];
    for (int i = 0; i < nw; i++) order[i] = i;
    for (int i = 1; i < nw; i++) {
        int v = order[i], j = i - 1;
        while (j >= 0 && cmp_agg(&wk[order[j]], &wk[v]) > 0) { order[j + 1] = order[j]; j--; }
        order[j + 1] = v;
    }
    if (HAS_WEEKS && strcmp(cmd, CMD_WEEKS) == 0) {
        for (int k = 0; k < nw; k++) {
            int i = order[k];
            char ds[16];
            cfd(wk[i].key, ds);
            fmt_t(regm[i], tb);
            fmt_t(otm[i], tb2);
            printf("%s %s %s %s\n", wk[i].name, ds, tb, tb2);
        }
        return 0;
    }
    (void)is_pay;
    /* employees in name order */
    char names[256][24];
    int nn = 0;
    for (int k = 0; k < nw; k++) {
        int i = order[k];
        if (nn == 0 || strcmp(names[nn - 1], wk[i].name) != 0) strcpy(names[nn++], wk[i].name);
    }
    for (int k = 0; k < nn; k++) {
        int found = 0;
        for (int j = 0; j < nrates; j++)
            if (strcmp(rate_name[j], names[k]) == 0) found = 1;
        if (!found) {
            printf("error: rate %s\n", names[k]);
            return 1;
        }
    }
    long total = 0;
    for (int k = 0; k < nn; k++) {
        long rate = 0, cents = 0;
        for (int j = 0; j < nrates; j++)
            if (strcmp(rate_name[j], names[k]) == 0) rate = rate_cents[j];
        for (int i = 0; i < nw; i++) {
            if (strcmp(wk[i].name, names[k]) != 0) continue;
            long numer = (regm[i] * MULT_DEN + otm[i] * MULT_NUM) * rate;
            long denom = 60L * MULT_DEN;
            cents += (2 * numer + denom) / (2 * denom);
        }
        total += cents;
        money(cents, tb);
        printf("%s %s\n", names[k], tb);
    }
    if (nn > 0) {
        money(total, tb);
        printf("TOTAL %s\n", tb);
    }
    return 0;
}
'''



import datetime

NAMES = ["ana", "bo", "cy", "dee", "eli", "fay", "gus", "hal", "ivy", "joe", "kit", "lou"]
THEMES = ["the Quillfeather ferry crew", "the lighthouse keepers", "the bakery rota", "the orchard pickers", "the tide-clock workshop", "the harbour cleaners"]
WEEK_BASES = ["2024-02-26", "2023-12-28", "2024-03-01", "2023-12-31", "2024-02-28", "2099-12-26", "2000-01-01", "2024-07-08", "2021-02-25", "2023-02-27"]
RATES = [1500, 2000, 1850, 999, 12345, 1, 777, 2250]
WS_NAME = {0: "Monday", 5: "Saturday", 6: "Sunday"}


def params(rng, level, i):
    pick = lambda xs: rng.choice(xs)  # noqa: E731
    return {
        "level": level,
        "c": {"check": pick(["check", "verify", "audit"]), "total": pick(["total", "sum", "hours"]), "weeks": pick(["weeks", "weekly", "byweek"]), "pay": pick(["pay", "gross", "wages"])},
        "weeks": level >= 3, "pay": level >= 4, "auto": level >= 2, "daily": level >= 4, "tfmt": pick(["hm", "dec"]),
        "round": 1 if level < 2 else pick([5, 6, 15]), "rmode": pick(["nearest", "up", "down"]) if level >= 2 else "nearest",
        "auto_after": pick([300, 360, 420]), "auto_min": pick([15, 30, 45]), "maxshift": pick([720, 840, 960]), "wstart": pick([0, 5, 6]), "thresh": pick([38, 40, 44]), "mult": pick([(3, 2), (5, 4), (2, 1)]),
        "daily_h": pick([8, 9, 10]), "nmax": pick([8, 12]), "theme": THEMES[(i + rng.randrange(2)) % len(THEMES)],
    }


def sol(lang, p):
    src = {"python": PY, "go": GO, "bash": SH, "c": CC}[lang]
    b = {"python": lambda v: "True" if v else "False", "go": lambda v: "true" if v else "false"}.get(lang, lambda v: "1" if v else "0")
    return K.subst(
        src, C_CHECK=p["c"]["check"], C_TOTAL=p["c"]["total"], C_WEEKS=p["c"]["weeks"], C_PAY=p["c"]["pay"], WEEKS=b(p["weeks"]), PAY=b(p["pay"]), AUTO=b(p["auto"]), DAILY=b(p["daily"]),
        WEEKS_SH="1" if p["weeks"] else "0", PAY_SH="1" if p["pay"] else "0", AUTO_SH="1" if p["auto"] else "0", DAILY_SH="1" if p["daily"] else "0",
        TFMT=p["tfmt"], TFMT_HM="1" if p["tfmt"] == "hm" else "0", ROUND=p["round"], RMODE=p["rmode"], RM_NEAREST="1" if p["rmode"] == "nearest" else "0", RM_UP="1" if p["rmode"] == "up" else "0",
        AUTO_AFTER=p["auto_after"], AUTO_MIN=p["auto_min"], MAXSHIFT=p["maxshift"], WSTART=p["wstart"], THRESH=p["thresh"], MULT_NUM=p["mult"][0], MULT_DEN=p["mult"][1], DAILY_MIN=p["daily_h"] * 60, NMAX=p["nmax"],
    ).lstrip("\n")


def hm(m):
    return "%02d:%02d" % (m // 60, m % 60)


def shift(name, date, start, length, brk=None):
    """a shift line: start minute of day, length in minutes (may cross midnight)"""
    tin, tout = start % 1440, (start + length) % 1440
    return f"{name} {date} {hm(tin)} {hm(tout)}" + ("" if brk is None else f" {brk}")


def add_days(date, n):
    return (datetime.date.fromisoformat(date) + datetime.timedelta(days=n)).isoformat()


def log_text(rng, lines, final_newline=None):
    ls = list(lines)
    rng.shuffle(ls)
    fn = rng.random() < 0.7 if final_newline is None else final_newline
    return "\n".join(ls) + ("\n" if fn and ls else "")


def rand_shift(rng, p, name, date):
    mx = p["maxshift"]
    length = rng.choice([240, 300, 360, 420, 450, 480, 510, 540, 600, rng.randrange(20, mx + 1), rng.randrange(20, 400)])
    length = min(length, mx)
    start = rng.choice([360, 420, 480, 540, 600, 1260, 1320, rng.randrange(0, 1440)])
    brk = None
    if rng.random() < 0.45:
        brk = rng.choice([0, 15, 30, 45, 60, rng.randrange(0, 61)])
        if brk >= length:
            brk = None
    return shift(name, date, start, length, brk)


def rand_log(rng, p, nemp=None, days=None):
    nemp = nemp or rng.randint(1, 4)
    emps = rng.sample(NAMES, nemp)
    base = rng.choice(WEEK_BASES)
    lines = []
    for e in emps:
        for _ in range(rng.randint(1, 8)):
            lines.append(rand_shift(rng, p, e, add_days(base, rng.randrange(0, days or 16))))
    return lines, emps, base


def cmd_args(rng, p, emps, lines, which=None):
    c = p["c"]
    opts = ["check", "total"] + (["weeks"] if p["weeks"] else []) + (["pay"] if p["pay"] else [])
    which = which or rng.choice(opts)
    if which != "pay":
        return [c[which]]
    args = [c["pay"]]
    for e in emps:
        if rng.random() < 0.93:
            args += ["--rate", f"{e}={rng.choice(RATES)}"]
    dates = [ln.split(" ")[1] for ln in lines]
    for _ in range(rng.choice([0, 0, 1, 2])):
        if dates:
            args += ["--holiday", rng.choice(dates)]
    return args


def make_cases(rng, p):
    cases = []
    c = p["c"]
    L = p["level"]

    def add(args, stdin):
        cases.append(K.CliCase(list(args), stdin))

    # random logs
    for _ in range(70 if L >= 3 else 50):
        lines, emps, base = rand_log(rng, p)
        add(cmd_args(rng, p, emps, lines), log_text(rng, lines))
    for _ in range(10):
        lines, emps, base = rand_log(rng, p, nemp=rng.randint(2, 4), days=9)
        for which in ([None] if not p["pay"] else [None, "pay"]):
            add(cmd_args(rng, p, emps, lines, which), log_text(rng, lines))
    # edge shifts
    mx = p["maxshift"]
    d0 = "2024-03-04"
    base_edges = [shift("ana", d0, 480, mx), shift("bo", d0, 480, mx - 1), shift("cy", d0, 1200, 480), shift("dee", d0, 0, 1), shift("eli", d0, 1439, 2), shift("fay", d0, 480, 60, 0), shift("gus", d0, 480, 61, 60), shift("hal", d0, 480, 61, 59)]
    for ln in base_edges:
        add([c["total"]], ln + "\n")
    add([c["total"]], "\n".join(base_edges) + "\n")
    add([c["check"]], "\n".join(base_edges))
    for ln in [shift("ana", d0, 480, mx + 1), shift("ana", d0, 480, 600, 600), shift("ana", d0, 480, 600, 601), shift("ana", d0, 480, 600, 599), shift("ana", d0, 480, 600, 180), shift("ana", d0, 480, 600, 181), shift("ana", d0, 480, 600, 0), shift("ana", d0, 480, 30, 29)]:
        add([c["total"]], ln + "\n")
    # automatic break edges and rounding
    if p["auto"]:
        a = p["auto_after"]
        for ln in [shift("ana", d0, 480, a), shift("ana", d0, 480, a + 1), shift("ana", d0, 480, a + 1, 0), shift("ana", d0, 480, a + 1, 5), shift("ana", d0, 480, a - 1), shift("ana", d0, 480, a + 90)]:
            add([c["total"]], ln + "\n")
        for k in range(1, 31):
            add([c["total"]], shift("ana", d0, 480, 100 + k, 0) + "\n" + shift("bo", d0, 480, 200 + k, 7) + "\n")
    # time and date syntax
    errs = ["ana", "ana 2024-03-04 08:00", "ana 2024-03-04 08:00 16:00 30 x", "ana  2024-03-04 08:00 16:00", "ana 2024-03-04 08:00 16:00 ", " ana 2024-03-04 08:00 16:00", "ana\t2024-03-04 08:00 16:00", "", " ",
            "Ana 2024-03-04 08:00 16:00", "1ana 2024-03-04 08:00 16:00", "a-b 2024-03-04 08:00 16:00", "_a 2024-03-04 08:00 16:00", "a" * p["nmax"] + " 2024-03-04 08:00 16:00", "a" * (p["nmax"] + 1) + " 2024-03-04 08:00 16:00",
            "ana 2024-3-4 08:00 16:00", "ana 2024/03/04 08:00 16:00", "ana 20240304 08:00 16:00", "ana 2024-03-04T 08:00 16:00", "ana 2024-13-01 08:00 16:00", "ana 2024-00-10 08:00 16:00", "ana 2024-04-31 08:00 16:00", "ana 2024-02-30 08:00 16:00",
            "ana 2024-02-29 08:00 16:00", "ana 2023-02-29 08:00 16:00", "ana 2100-02-28 08:00 16:00", "ana 2099-12-31 08:00 16:00", "ana 2000-02-29 08:00 16:00", "ana 1999-12-31 08:00 16:00", "ana 2100-01-01 08:00 16:00", "ana 2024-03-00 08:00 16:00",
            "ana 2024-03-04 8:00 16:00", "ana 2024-03-04 08:0 16:00", "ana 2024-03-04 24:00 16:00", "ana 2024-03-04 08:60 16:00", "ana 2024-03-04 08:00 16:60", "ana 2024-03-04 08.00 16:00", "ana 2024-03-04 0800 1600", "ana 2024-03-04 aa:bb 16:00",
            "ana 2024-03-04 08:00 08:00", "ana 2024-03-04 23:59 00:00", "ana 2024-03-04 00:00 23:59", "ana 2024-03-04 08:00 16:00 -5", "ana 2024-03-04 08:00 16:00 05", "ana 2024-03-04 08:00 16:00 1.5", "ana 2024-03-04 08:00 16:00 1000", "ana 2024-03-04 08:00 16:00 x",
            "ana 2024-03-04 08:00 16:00 180", "ana 2024-03-04 08:00 16:00 181", "ana 2024-03-04 08:00 16:00 00", "ana 2024-03-04 08:00 16:00 0", "ana 2024-03-04 08:00 16:00 +5", "ana 2024-03-04 16:00 08:00"]
    for e in errs:
        add([c["total"]], e + "\n")
        if rng.random() < 0.35:
            add([c["check"]], "bo 2024-03-04 08:00 12:00\n" + e + "\ncy 2024-03-04 08:00 12:00\n")
    add([c["check"]], "")
    add([c["total"]], "")
    add([c["check"]], "\n")
    add([c["total"]], "\n\n")
    add([c["check"]], "ana 2024-03-04 08:00 16:00\n\n")
    add([c["total"]], "ana 2024-03-04 08:00 16:00\n\nbo 2024-03-04 08:00 16:00\n")
    add([c["total"]], "ana 2024-03-04 08:00 16:00\nbad\nalso bad\n")
    add([c["total"]], "bad name 2024-03-04 08:00 16:00\nana 2024-02-30 08:00 16:00\n")
    add([c["check"]], "ana 2024-03-04 08:00 16:00\nbo 2024-03-04 08:00 16:00 30\n" * 3)
    # usage
    uses = [[], ["bogus"], [c["check"], "x"], [c["total"], "--x"], [c["total"].upper()], [c["check"].capitalize()], ["-h"], [""], [c["check"], ""], [c["total"], c["total"]], ["--rate"], [c["weeks"], "x"]]
    if not p["weeks"]:
        uses.append([c["weeks"]])
    if not p["pay"]:
        uses.append([c["pay"]])
        uses.append([c["pay"], "--rate", "ana=1500"])
    for u in uses:
        add(u, "ana 2024-03-04 08:00 16:00\n")
    if p["weeks"]:
        add([c["weeks"]], "")
    tot = lambda n, d, ms: [shift(n, add_days(d, k), 480, m, 0) for k, m in enumerate(ms)]  # noqa: E731
    # weeks
    if p["weeks"]:
        T = p["thresh"] * 60
        for wd in range(7):
            d = add_days("2024-03-04", wd)
            even = T // 5
            ms = [even] * 5
            ms[0] += T - sum(ms)
            for delta in (-30, 0, 30):
                ms2 = list(ms)
                ms2[1] += delta
                if max(ms2) <= p["maxshift"]:
                    add([c["weeks"]], log_text(rng, tot("ana", d, ms2)))
        add([c["weeks"]], log_text(rng, tot("ana", "2024-03-04", [480, 480, 480, 480, 480, 120, 60]) + tot("bo", "2024-03-06", [600, 600, 600, 600, 600])))
        add([c["weeks"]], log_text(rng, tot("ana", "2023-12-28", [480] * 10) + tot("ana", "2024-02-26", [300] * 6)))
        add([c["weeks"]], log_text(rng, [shift("ana", "2024-02-29", 1320, 480, 0), shift("ana", "2024-03-01", 480, 60, 0)]))
        add([c["weeks"]], log_text(rng, [shift("ana", "2099-12-31", 1320, 480, 0), shift("ana", "2099-12-28", 480, 60, 0)]))
        add([c["weeks"]], log_text(rng, [shift("ana", "2000-01-01", 480, 60, 0), shift("ana", "2000-01-02", 480, 60, 0), shift("ana", "2000-01-03", 480, 60, 0)]))
    # daily and pay
    if p["daily"]:
        D = p["daily_h"] * 60
        for delta in (-30, 0, 30, 120):
            add([c["weeks"]], log_text(rng, tot("ana", "2024-03-04", [D + delta, 60]) if D + delta <= p["maxshift"] else tot("ana", "2024-03-04", [D, 60])))
        add([c["weeks"]], log_text(rng, [shift("ana", "2024-03-04", 480, 300, 0), shift("ana", "2024-03-04", 1020, 300, 0), shift("ana", "2024-03-05", 480, 120, 0)]))
    if p["pay"]:
        base = [shift("ana", "2024-03-04", 480, 540, 30), shift("ana", "2024-03-05", 480, 540, 30), shift("bo", "2024-03-04", 480, 300, 0), shift("cy", "2024-03-10", 480, 600, 0)]
        txt = log_text(rng, base)
        pay = c["pay"]
        add([pay, "--rate", "ana=1500", "--rate", "bo=2000", "--rate", "cy=999"], txt)
        add([pay, "--rate", "ana=1500", "--rate", "bo=2000"], txt)
        add([pay, "--rate", "ana=1500", "--rate", "bo=2000", "--rate", "cy=999", "--rate", "zed=5"], txt)
        add([pay, "--rate", "bo=2000", "--rate", "cy=999"], txt)
        add([pay], txt)
        add([pay], "")
        add([pay, "--rate", "ana=1"], "")
        add([pay, "--rate", "ana=1500", "--rate", "bo=2000", "--rate", "cy=999", "--holiday", "2024-03-05"], txt)
        add([pay, "--rate", "ana=1500", "--rate", "bo=2000", "--rate", "cy=999", "--holiday", "2024-03-10", "--holiday", "2024-03-10"], txt)
        add([pay, "--rate", "ana=1500", "--rate", "bo=2000", "--rate", "cy=999", "--holiday", "2024-03-04", "--holiday", "2024-03-05"], txt)
        add([pay, "--holiday", "2024-03-05", "--rate", "ana=1500", "--rate", "bo=2000", "--rate", "cy=999"], txt)
        for r in ("ana=1", "ana=999999", "ana=7777"):
            add([pay, "--rate", r, "--rate", "bo=1", "--rate", "cy=1"], txt)
        for bad in (["--rate"], ["--rate", "ana"], ["--rate", "ana="], ["--rate", "=5"], ["--rate", "Ana=5"], ["--rate", "ana=0"], ["--rate", "ana=05"], ["--rate", "ana=1234567"], ["--rate", "ana=5x"], ["--rate", "ana=-5"], ["--rate", "ana=1.5"],
                    ["--rate", "ana=5", "--rate", "ana=6"], ["--rate", "ana=5", "--bogus", "1"], ["--holiday"], ["--holiday", "2024-02-30"], ["--holiday", "x"], ["--holiday", "2024-3-5"], ["--rate", "ana=5", "stray"], ["stray"], ["--rate", "ana=5", "--holiday"],
                    ["--rate", "ana=5=6"], ["--RATE", "ana=5"], ["-rate", "ana=5"], ["--rate", "a" * (p["nmax"] + 1) + "=5"]):
            add([pay] + bad, txt)
        for k in range(8):
            lines, emps, base2 = rand_log(rng, p, nemp=3, days=14)
            args = [pay]
            for e in emps:
                args += ["--rate", f"{e}={rng.choice(RATES)}"]
            for _ in range(rng.randint(0, 3)):
                args += ["--holiday", add_days(base2, rng.randrange(0, 14))]
            add(args, log_text(rng, lines))
    # dedupe, examples first
    ex = []
    ex.append(K.CliCase([c["total"]], "ana 2024-03-04 08:00 12:30\nbo 2024-03-04 22:00 06:00 30\nana 2024-03-05 09:00 11:00 0\n"))
    ex.append(K.CliCase([c["check"]], "ana 2024-03-04 08:00 12:30\nbo 2024-03-04 22:00 25:00\n"))
    if p["auto"]:
        ex.append(K.CliCase([c["total"]], f"cy 2024-03-04 08:00 {hm(480 + p['auto_after'] + 20)}\ncy 2024-03-05 08:00 {hm(480 + p['auto_after'] + 20)} 5\n"))
    if p["weeks"]:
        ex.append(K.CliCase([c["weeks"]], "".join(shift("ana", add_days("2024-03-04", k), 480, 600, 0) + "\n" for k in range(5))))
    if p["pay"]:
        ex.append(K.CliCase([c["pay"], "--rate", "ana=1500", "--holiday", "2024-03-06"], "".join(shift("ana", add_days("2024-03-04", k), 480, 300, 0) + "\n" for k in range(4))))
    nex = len(ex)
    out, seen = [], set()
    for cs in ex + cases:
        if cs.key() not in seen:
            seen.add(cs.key())
            out.append(cs)
    return out, nex


def readme(p, spec, lang, examples):
    c = p["c"]
    X = [f"# timecard: shift sheets for {p['theme']}", ""]
    X.append("`timecard` reads shift lines on **standard input** and prints totals" + (", weekly regular/overtime splits" if p["weeks"] else "") + (" and pay" if p["pay"] else "") + f" for {p['theme']}. "
             "Results go to standard output. A usage mistake prints nothing on standard output (a message on standard error is allowed and not checked) and exits with status 2; a problem in the data prints one `error:` line on standard output and exits with status 1; otherwise the status is 0.")
    X.append("")
    X.append("## Shift lines")
    X.append("")
    X.append("Each line has **four or five fields separated by single spaces**:")
    X.append("")
    X.append("    NAME DATE IN OUT [BREAK]")
    X.append("")
    X.append(f"* `NAME`: 1 to {p['nmax']} characters: a lower-case ASCII letter followed by lower-case letters, digits or `_`.")
    X.append("* `DATE`: `YYYY-MM-DD` written exactly so, a real date from 2000-01-01 to 2099-12-31 (usual leap-year rule: divisible by 4, except centuries that are not divisible by 400). It is the day the shift **starts**.")
    X.append("* `IN`, `OUT`: `HH:MM`, 24-hour clock, `00:00` to `23:59`, two digits each. A shift whose `OUT` is earlier than `IN` ends after midnight on the next day; `OUT` equal to `IN` is not allowed.")
    X.append("* `BREAK`: optional, a whole number of minutes from `0` to `180` written without sign, leading zeros or fractions (`0` itself is fine).")
    X.append("")
    X.append(f"The **gross** length of a shift is `OUT - IN` in minutes (plus 24 hours when it ends after midnight). A shift may be at most **{p['maxshift']} minutes** long, and an explicit `BREAK` must be shorter than the gross length. "
             "Lines end with `\\n`; one final line without `\\n` is fine. Empty input has no lines; an empty line in the middle is an error like any other bad line.")
    X.append("")
    X.append("A bad line is reported as `error: line N: WHY` (`N` counts from 1; only the **first** bad line is reported, nothing else is printed, status 1). `WHY` is the first of these that applies:")
    X.append("")
    X.append("1. `fields`: not four or five fields.")
    X.append("2. `name`, then `date`, then `time` (for `IN` or `OUT`), then `break` (a `BREAK` field that is not a valid number, or is above 180).")
    X.append("3. `times`: `IN` equals `OUT`.")
    X.append("4. `long`: the gross length is above the maximum.")
    X.append("5. `breaklen`: an explicit `BREAK` is not shorter than the gross length.")
    X.append("")
    X.append("## Worked time")
    X.append("")
    X.append("The **worked** minutes of a shift are the gross length minus its break" + (f". If the line has no `BREAK` field and the gross length is **more than {p['auto_after']} minutes**, an automatic break of {p['auto_min']} minutes is taken instead (an explicit break, even `0`, always replaces the automatic one)." if p["auto"] else " (no `BREAK` field means no break)."))
    if p["round"] > 1:
        rn = {"nearest": f"to the nearest multiple of {p['round']} minutes, halves going up", "up": f"up to the next multiple of {p['round']} minutes (a multiple stays as it is)", "down": f"down to a multiple of {p['round']} minutes"}[p["rmode"]]
        X.append(f"The worked minutes of each shift are then rounded {rn}. Everything below works on these rounded minutes.")
    X.append("")
    X.append("Durations are written " + ("as `H:MM`: hours (any number of digits, no leading zeros) and exactly two digits of minutes (`0:00`, `7:05`, `112:30`)." if p["tfmt"] == "hm" else
             "as decimal hours with two decimals, rounding halves up in hundredths of an hour (`0.00`, `7.08` for 7 h 5 min, `1.33` for 80 min): the value is `round(minutes * 100 / 60)` written as `H.CC`."))
    X.append("")
    X.append("## Commands")
    X.append("")
    X.append(f"* `timecard {c['check']}`: validates the input and prints `ok N shifts` (`N` is the number of lines; `0` for empty input).")
    X.append(f"* `timecard {c['total']}`: one line per person, in ascending byte order of the name: `NAME TIME`, the sum of the worked minutes of all their shifts. No output for empty input.")
    if p["weeks"]:
        ws = WS_NAME[p["wstart"]]
        X.append(f"* `timecard {c['weeks']}`: one line per person and week, ordered by name and then week: `NAME WEEKSTART REGULAR OVERTIME`. Weeks start on **{ws}**; `WEEKSTART` is the date (`YYYY-MM-DD`) of that {ws}. A shift belongs to the week that contains its `DATE` (the day it starts). "
                 f"Per person and week, the worked minutes are added up; up to **{p['thresh']} hours** ({p['thresh'] * 60} minutes) are regular, the rest is overtime." + (" The daily rule below applies first." if p["daily"] else "") + " Weeks without shifts are not listed.")
    if p["daily"]:
        X.append("")
        X.append(f"**Daily rule.** Worked minutes are also added up per person and per start `DATE`: up to **{p['daily_h']} hours** ({p['daily_h'] * 60} minutes) of a day count as candidate regular time, the rest of that day is overtime. "
                 f"The week's regular time is then the candidate regular minutes of its days, but at most {p['thresh'] * 60}; any candidate minutes above that are overtime too. So overtime = (minutes above the daily limit) + (candidate minutes above the weekly limit) + (holiday minutes, see below).")
    if p["pay"]:
        X.append("")
        X.append(f"* `timecard {c['pay']} [--rate NAME=CENTS]... [--holiday DATE]...`: gross pay per person. The options may come in any order and be repeated. `--rate NAME=CENTS` gives the hourly rate of a person in cents (`CENTS` is 1 to 6 digits, no leading zero; a person may be given only once). "
                 "`--holiday DATE` names a day (a valid `DATE`; naming a day twice is fine): all minutes of shifts that **start** on a holiday are overtime, they do not count toward the daily or weekly limits, and the daily limit does not apply to them.")
        n, d = p["mult"]
        X.append("")
        X.append(f"Per person and week the pay in cents is `round((regular + overtime * {n} / {d}) * RATE / 60)` with the minutes as whole numbers, computed in exact integer arithmetic, halves rounded up. The person's pay is the sum over their weeks (the weeks use the same split as `{c['weeks']}`, including the daily rule and the holidays). "
                 "Output: one line `NAME AMOUNT` per person in ascending name order, amount in dollars as `D.CC` (`0.00`, `1234.50`), followed by `TOTAL AMOUNT` (the sum), unless there is nobody. "
                 "A person with shifts but no `--rate` is reported as `error: rate NAME` (the first such name in ascending order; status 1, nothing else printed). Rates for people without shifts are ignored.")
    X.append("")
    X.append("## Usage errors")
    X.append("")
    cmds = [c["check"], c["total"]] + ([c["weeks"]] if p["weeks"] else []) + ([c["pay"]] if p["pay"] else [])
    X.append("Any other command line is a usage error (status 2, nothing on standard output, standard input not read): no arguments, an unknown command (commands are lower-case and case-sensitive: " + ", ".join(f"`{x}`" for x in cmds) + ")" +
             f", any argument after `{c['check']}`, `{c['total']}`" + (f" or `{c['weeks']}`" if p["weeks"] else "") + (", an unknown option, an option without its value, a malformed `--rate` or `--holiday` value, a repeated name in `--rate`, a stray argument." if p["pay"] else "."))
    X.append("Usage errors win over data errors.")
    X.append("")
    X.append("## Where")
    X.append("")
    X.append(f"The program lives in {spec.how(lang)}.")
    X.append("")
    X.append("## Examples")
    X.append("")
    for cs, out in examples:
        X.append("```")
        X.append(f"$ timecard {' '.join(cs.args)} <<'EOF'")
        X.append(cs.stdin.rstrip("\n"))
        X.append("EOF")
        X.append(out.rstrip("\n"))
        X.append("```")
        X.append("")
    X.append(K.run_hint("bash"))
    return "\n".join(X) + "\n"


def prompt(rng, p, spec, lang):
    where = spec.short(lang)
    ln = K.LANG_NAME[lang]
    feats = ["totals"] + (["rounding and automatic breaks"] if p["auto"] else []) + (["weekly overtime"] if p["weeks"] else []) + (["daily limits, holidays and pay"] if p["pay"] else [])
    fl = ", ".join(feats[:-1]) + (" and " if len(feats) > 1 else "") + feats[-1]
    opts = [
        f"Write `timecard` in {ln} ({where}): a command-line tool that reads shift lines on stdin and prints {fl} for {p['theme']}. The exact format, rounding and error rules are in README.md. {K.closer(rng)}",
        f"Build the shift-sheet tool described in README.md ({ln}, {where}). It covers {fl}. Exit statuses matter: 0 ok, 1 data error, 2 usage error. {K.closer(rng)}",
        f"{ln} CLI task: implement `timecard` ({where}) following README.md. Features: {fl}. Hidden checks include date edge cases and malformed lines.",
        f"Please implement the time-card CLI in {ln} in {where}; the spec (input format, worked-time rules, commands) is README.md. {K.closer(rng)}",
    ]
    return rng.choice(opts).strip()


LANG_PLAN = ["bash", "c", "python", "bash", "go", "c", "bash", "go"]
LEVELS = [1, 1, 1, 2, 2, 2, 3, 4]


@family("greenfield-timecard", category="greenfield", lang="mixed", kind="greenfield", n=8,
        summary="shift-sheet CLI: strict shift-line validation, break/rounding rules, weekly overtime, daily limits, holidays and pay in exact integer arithmetic")
def gen(rng, n):
    spec = K.CliSpec("timecard")
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = LEVELS[i % len(LEVELS)]
        p = params(rng, level, i)
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        sols = {lang: sol(lang, p), "python": py_src}
        cases, nex = make_cases(rng, p)
        ex = [(cs, ns["run"](cs.args, cs.stdin)[0]) for cs in cases[:nex]]
        rd = readme(p, spec, lang, ex)

        def oracle(cs):
            return ns["run"](cs.args, cs.stdin)

        yield K.cli_task(
            spec=spec, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, spec, lang), difficulty=level,
            slug=f"{i + 1:02d}-{lang}-{p['tfmt']}-l{level}", oracle=oracle, tags=["cli", "dates", "payroll"],
            notes={"level": level, "tfmt": p["tfmt"], "round": p["round"], "rmode": p["rmode"], "wstart": p["wstart"]},
        )
