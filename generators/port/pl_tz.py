"""Port library: civil dates and daylight-saving rules (calendar arithmetic with floor semantics, nth-weekday rules, gaps and overlaps), Python / Go / TypeScript."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

TZ_SPEC = dd('''
    A scheduling service converts between UTC and the wall-clock time of a zone with daylight saving time (DST). Everything is in whole **minutes since 1970-01-01 00:00 UTC** (negative before) or in dates of the proleptic Gregorian calendar;
    years must be in 1900..2200 (anything outside is an error everywhere).

    * `days_from_civil(y, m, d)` is the number of days since 1970-01-01 (negative before it). An invalid date (month outside 1..12, a day that does not exist, 29 February in a non-leap year; leap years follow the 4/100/400 rule) is an error.
      `civil_from_days(n)` is the inverse and returns `[y, m, d]`; a day outside the supported years is an error.
    * `weekday(y, m, d)` is 0 for Monday up to 6 for Sunday (1970-01-01 was a Thursday, 3). `nth_weekday(y, m, nth, wd)` is the day of the month of the `nth` weekday `wd` of that month: `nth` 1..4 counts from the start, `nth = 5` means the **last** one; `wd` is 0..6;
      other `nth`, `wd` or month values are errors.
    * A **zone** is a rule name `zone` and the standard offset `std` in minutes (-720..840, else an error); an unknown rule name is an error. `"none"` never has DST. DST adds 60 minutes. For `"eu"` DST starts at 01:00 UTC on the last Sunday of March and ends at 01:00 UTC on the last Sunday of October.
      For `"us"` DST starts at 02:00 local *standard* time on the second Sunday of March (that is 02:00 minus `std` in UTC) and ends at 02:00 local *daylight* time on the first Sunday of November (02:00 minus `std + 60` in UTC).
    * `dst_window(zone, std, year)` returns `[start, end]` as minutes since the epoch (UTC) for that year (`[]` for `"none"`). `offset_at(zone, std, utc_min)` is `std + 60` when `start <= utc_min < end` for the year of the **UTC date** of `utc_min`, otherwise `std`.
    * `format_local(zone, std, utc_min)` is the local wall-clock time `YYYY-MM-DD HH:MM` (zero padded) followed directly by the offset as sign, hours and minutes: `2024-03-31 03:30+02:00`, `2024-01-15 08:00-05:00`, `2024-06-01 12:00+05:30`, `+00:00` for zero.
    * `utc_from_local(zone, std, text, later)` reads a local wall-clock time written exactly `YYYY-MM-DD HH:MM` (ASCII digits only, a valid date, hour 00..23, minute 00..59, nothing else) and returns the UTC minute. The candidate offsets are `std` and, unless the zone is `"none"`, `std + 60`; an offset `o` is *valid* when
      `offset_at(zone, std, local - o) == o` (where `local` is the wall-clock time counted as minutes). When both are valid the time occurs twice (DST ends): `later = true` picks the later instant (offset `std`), `later = false` the earlier one (offset `std + 60`). When neither is valid the time does
      not exist (DST starts) and that is an error.
''')

TZ_FNS = [
    Fn("days_from_civil", [("y", "int"), ("m", "int"), ("d", "int")], "int", err=True),
    Fn("civil_from_days", [("n", "int")], "list<int>", err=True),
    Fn("weekday", [("y", "int"), ("m", "int"), ("d", "int")], "int", err=True),
    Fn("nth_weekday", [("y", "int"), ("m", "int"), ("nth", "int"), ("wd", "int")], "int", err=True),
    Fn("dst_window", [("zone", "str"), ("std", "int"), ("year", "int")], "list<int>", err=True),
    Fn("offset_at", [("zone", "str"), ("std", "int"), ("utc_min", "int")], "int", err=True),
    Fn("format_local", [("zone", "str"), ("std", "int"), ("utc_min", "int")], "str", err=True),
    Fn("utc_from_local", [("zone", "str"), ("std", "int"), ("text", "str"), ("later", "bool")], "int", err=True),
]

TZ_PY = dd(r'''
import re

_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
_LOCAL = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2}) ([0-9]{2}):([0-9]{2})")


def _leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in(y, m):
    return _DAYS[m - 1] + (1 if m == 2 and _leap(y) else 0)


def _check_date(y, m, d):
    if not (1900 <= y <= 2200 and 1 <= m <= 12 and 1 <= d <= _days_in(y, m)):
        raise ValueError("invalid date")


def days_from_civil(y, m, d):
    _check_date(y, m, d)
    if m <= 2:
        y -= 1
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m - 3 if m > 2 else m + 9) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def civil_from_days(n):
    z = n + 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    y = yoe + era * 400 + (1 if m <= 2 else 0)
    if not 1900 <= y <= 2200:
        raise ValueError("year out of range")
    return [y, m, d]


def weekday(y, m, d):
    return (days_from_civil(y, m, d) + 3) % 7


def nth_weekday(y, m, nth, wd):
    if not (1 <= m <= 12 and 1 <= nth <= 5 and 0 <= wd <= 6):
        raise ValueError("bad argument")
    first = weekday(y, m, 1)
    day = 1 + (wd - first) % 7
    if nth <= 4:
        return day + 7 * (nth - 1)
    day += 28
    while day > _days_in(y, m):
        day -= 7
    return day


def _zone(zone, std):
    if zone not in ("eu", "us", "none") or not -720 <= std <= 840:
        raise ValueError("bad zone")


def dst_window(zone, std, year):
    _zone(zone, std)
    if not 1900 <= year <= 2200:
        raise ValueError("year out of range")
    if zone == "none":
        return []
    if zone == "eu":
        start = days_from_civil(year, 3, nth_weekday(year, 3, 5, 6)) * 1440 + 60
        end = days_from_civil(year, 10, nth_weekday(year, 10, 5, 6)) * 1440 + 60
    else:
        start = days_from_civil(year, 3, nth_weekday(year, 3, 2, 6)) * 1440 + 120 - std
        end = days_from_civil(year, 11, nth_weekday(year, 11, 1, 6)) * 1440 + 120 - (std + 60)
    return [start, end]


def offset_at(zone, std, utc_min):
    _zone(zone, std)
    year = civil_from_days(utc_min // 1440)[0]
    if zone == "none":
        return std
    start, end = dst_window(zone, std, year)
    return std + 60 if start <= utc_min < end else std


def format_local(zone, std, utc_min):
    off = offset_at(zone, std, utc_min)
    days, mins = divmod(utc_min + off, 1440)
    y, m, d = civil_from_days(days)
    a = abs(off)
    return "%04d-%02d-%02d %02d:%02d%s%02d:%02d" % (y, m, d, mins // 60, mins % 60, "+" if off >= 0 else "-", a // 60, a % 60)


def utc_from_local(zone, std, text, later):
    _zone(zone, std)
    mt = _LOCAL.fullmatch(text)
    if not mt:
        raise ValueError("bad local time")
    y, m, d, hh, mm = (int(x) for x in mt.groups())
    if hh > 23 or mm > 59:
        raise ValueError("bad local time")
    local = days_from_civil(y, m, d) * 1440 + hh * 60 + mm
    offsets = [std] if zone == "none" else [std, std + 60]
    valid = [o for o in offsets if offset_at(zone, std, local - o) == o]
    if not valid:
        raise ValueError("nonexistent local time")
    if len(valid) == 2:
        return local - (std if later else std + 60)
    return local - valid[0]
''')

TZ_GO = dd(r'''
package tzrules

import (
	"errors"
	"fmt"
)

var daysIn = [12]int64{31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31}

func floorDiv(a, b int64) int64 {
	q := a / b
	if (a%b != 0) && ((a < 0) != (b < 0)) {
		q--
	}
	return q
}

func floorMod(a, b int64) int64 { return a - floorDiv(a, b)*b }

func leap(y int64) bool { return y%4 == 0 && (y%100 != 0 || y%400 == 0) }

func daysInMonth(y, m int64) int64 {
	d := daysIn[m-1]
	if m == 2 && leap(y) {
		d++
	}
	return d
}

func checkDate(y, m, d int64) error {
	if y < 1900 || y > 2200 || m < 1 || m > 12 || d < 1 || d > daysInMonth(y, m) {
		return errors.New("invalid date")
	}
	return nil
}

func DaysFromCivil(y, m, d int64) (int64, error) {
	if err := checkDate(y, m, d); err != nil {
		return 0, err
	}
	return daysFromCivil(y, m, d), nil
}

func daysFromCivil(y, m, d int64) int64 {
	if m <= 2 {
		y--
	}
	era := floorDiv(y, 400)
	yoe := y - era*400
	var mm int64 = m + 9
	if m > 2 {
		mm = m - 3
	}
	doy := (153*mm+2)/5 + d - 1
	doe := yoe*365 + yoe/4 - yoe/100 + doy
	return era*146097 + doe - 719468
}

func civilFromDays(n int64) (int64, int64, int64, error) {
	z := n + 719468
	era := floorDiv(z, 146097)
	doe := z - era*146097
	yoe := (doe - doe/1460 + doe/36524 - doe/146096) / 365
	doy := doe - (365*yoe + yoe/4 - yoe/100)
	mp := (5*doy + 2) / 153
	d := doy - (153*mp+2)/5 + 1
	var m int64 = mp - 9
	if mp < 10 {
		m = mp + 3
	}
	y := yoe + era*400
	if m <= 2 {
		y++
	}
	if y < 1900 || y > 2200 {
		return 0, 0, 0, errors.New("year out of range")
	}
	return y, m, d, nil
}

func CivilFromDays(n int64) ([]int64, error) {
	y, m, d, err := civilFromDays(n)
	if err != nil {
		return nil, err
	}
	return []int64{y, m, d}, nil
}

func Weekday(y, m, d int64) (int64, error) {
	n, err := DaysFromCivil(y, m, d)
	if err != nil {
		return 0, err
	}
	return floorMod(n+3, 7), nil
}

func NthWeekday(y, m, nth, wd int64) (int64, error) {
	if m < 1 || m > 12 || nth < 1 || nth > 5 || wd < 0 || wd > 6 {
		return 0, errors.New("bad argument")
	}
	first, err := Weekday(y, m, 1)
	if err != nil {
		return 0, err
	}
	day := 1 + floorMod(wd-first, 7)
	if nth <= 4 {
		return day + 7*(nth-1), nil
	}
	day += 28
	for day > daysInMonth(y, m) {
		day -= 7
	}
	return day, nil
}

func checkZone(zone string, std int64) error {
	if (zone != "eu" && zone != "us" && zone != "none") || std < -720 || std > 840 {
		return errors.New("bad zone")
	}
	return nil
}

func DstWindow(zone string, std, year int64) ([]int64, error) {
	if err := checkZone(zone, std); err != nil {
		return nil, err
	}
	if year < 1900 || year > 2200 {
		return nil, errors.New("year out of range")
	}
	if zone == "none" {
		return []int64{}, nil
	}
	day := func(m, nth int64) (int64, error) {
		d, err := NthWeekday(year, m, nth, 6)
		if err != nil {
			return 0, err
		}
		return daysFromCivil(year, m, d), nil
	}
	if zone == "eu" {
		a, err := day(3, 5)
		if err != nil {
			return nil, err
		}
		b, err := day(10, 5)
		if err != nil {
			return nil, err
		}
		return []int64{a*1440 + 60, b*1440 + 60}, nil
	}
	a, err := day(3, 2)
	if err != nil {
		return nil, err
	}
	b, err := day(11, 1)
	if err != nil {
		return nil, err
	}
	return []int64{a*1440 + 120 - std, b*1440 + 120 - (std + 60)}, nil
}

func OffsetAt(zone string, std, utcMin int64) (int64, error) {
	if err := checkZone(zone, std); err != nil {
		return 0, err
	}
	year, _, _, err := civilFromDays(floorDiv(utcMin, 1440))
	if err != nil {
		return 0, err
	}
	if zone == "none" {
		return std, nil
	}
	w, err := DstWindow(zone, std, year)
	if err != nil {
		return 0, err
	}
	if w[0] <= utcMin && utcMin < w[1] {
		return std + 60, nil
	}
	return std, nil
}

func FormatLocal(zone string, std, utcMin int64) (string, error) {
	off, err := OffsetAt(zone, std, utcMin)
	if err != nil {
		return "", err
	}
	local := utcMin + off
	days := floorDiv(local, 1440)
	mins := floorMod(local, 1440)
	y, m, d, err := civilFromDays(days)
	if err != nil {
		return "", err
	}
	sign := "+"
	a := off
	if off < 0 {
		sign = "-"
		a = -off
	}
	return fmt.Sprintf("%04d-%02d-%02d %02d:%02d%s%02d:%02d", y, m, d, mins/60, mins%60, sign, a/60, a%60), nil
}

func digits(s string) (int64, bool) {
	var v int64
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return 0, false
		}
		v = v*10 + int64(s[i]-'0')
	}
	return v, true
}

func UtcFromLocal(zone string, std int64, text string, later bool) (int64, error) {
	if err := checkZone(zone, std); err != nil {
		return 0, err
	}
	bad := errors.New("bad local time")
	if len(text) != 16 || text[4] != '-' || text[7] != '-' || text[10] != ' ' || text[13] != ':' {
		return 0, bad
	}
	var parts [5]int64
	for i, span := range [5][2]int{{0, 4}, {5, 7}, {8, 10}, {11, 13}, {14, 16}} {
		v, ok := digits(text[span[0]:span[1]])
		if !ok {
			return 0, bad
		}
		parts[i] = v
	}
	if parts[3] > 23 || parts[4] > 59 {
		return 0, bad
	}
	days, err := DaysFromCivil(parts[0], parts[1], parts[2])
	if err != nil {
		return 0, err
	}
	local := days*1440 + parts[3]*60 + parts[4]
	offsets := []int64{std}
	if zone != "none" {
		offsets = append(offsets, std+60)
	}
	var valid []int64
	for _, o := range offsets {
		got, err := OffsetAt(zone, std, local-o)
		if err != nil {
			return 0, err
		}
		if got == o {
			valid = append(valid, o)
		}
	}
	if len(valid) == 0 {
		return 0, errors.New("nonexistent local time")
	}
	if len(valid) == 2 {
		if later {
			return local - std, nil
		}
		return local - (std + 60), nil
	}
	return local - valid[0], nil
}
''')

TZ_TS = dd(r'''
const DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const LOCAL = /^([0-9]{4})-([0-9]{2})-([0-9]{2}) ([0-9]{2}):([0-9]{2})$/;

function floorDiv(a: number, b: number): number {
  return Math.floor(a / b);
}

function floorMod(a: number, b: number): number {
  return a - Math.floor(a / b) * b;
}

function leap(y: number): boolean {
  return y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
}

function daysIn(y: number, m: number): number {
  return DAYS[m - 1] + (m === 2 && leap(y) ? 1 : 0);
}

function checkDate(y: number, m: number, d: number): void {
  if (!(y >= 1900 && y <= 2200 && m >= 1 && m <= 12 && d >= 1 && d <= daysIn(y, m))) throw new Error('invalid date');
}

function toDays(year: number, m: number, d: number): number {
  const y = m <= 2 ? year - 1 : year;
  const era = floorDiv(y, 400);
  const yoe = y - era * 400;
  const doy = Math.floor((153 * (m > 2 ? m - 3 : m + 9) + 2) / 5) + d - 1;
  const doe = yoe * 365 + Math.floor(yoe / 4) - Math.floor(yoe / 100) + doy;
  return era * 146097 + doe - 719468;
}

export function daysFromCivil(y: number, m: number, d: number): number {
  checkDate(y, m, d);
  return toDays(y, m, d);
}

export function civilFromDays(n: number): number[] {
  const z = n + 719468;
  const era = floorDiv(z, 146097);
  const doe = z - era * 146097;
  const yoe = Math.floor((doe - Math.floor(doe / 1460) + Math.floor(doe / 36524) - Math.floor(doe / 146096)) / 365);
  const doy = doe - (365 * yoe + Math.floor(yoe / 4) - Math.floor(yoe / 100));
  const mp = Math.floor((5 * doy + 2) / 153);
  const d = doy - Math.floor((153 * mp + 2) / 5) + 1;
  const m = mp < 10 ? mp + 3 : mp - 9;
  const y = yoe + era * 400 + (m <= 2 ? 1 : 0);
  if (y < 1900 || y > 2200) throw new Error('year out of range');
  return [y, m, d];
}

export function weekday(y: number, m: number, d: number): number {
  return floorMod(daysFromCivil(y, m, d) + 3, 7);
}

export function nthWeekday(y: number, m: number, nth: number, wd: number): number {
  if (!(m >= 1 && m <= 12 && nth >= 1 && nth <= 5 && wd >= 0 && wd <= 6)) throw new Error('bad argument');
  const first = weekday(y, m, 1);
  let day = 1 + floorMod(wd - first, 7);
  if (nth <= 4) return day + 7 * (nth - 1);
  day += 28;
  while (day > daysIn(y, m)) day -= 7;
  return day;
}

function checkZone(zone: string, std: number): void {
  if (!(zone === 'eu' || zone === 'us' || zone === 'none') || !(std >= -720 && std <= 840)) throw new Error('bad zone');
}

export function dstWindow(zone: string, std: number, year: number): number[] {
  checkZone(zone, std);
  if (!(year >= 1900 && year <= 2200)) throw new Error('year out of range');
  if (zone === 'none') return [];
  const day = (m: number, nth: number): number => toDays(year, m, nthWeekday(year, m, nth, 6));
  if (zone === 'eu') return [day(3, 5) * 1440 + 60, day(10, 5) * 1440 + 60];
  return [day(3, 2) * 1440 + 120 - std, day(11, 1) * 1440 + 120 - (std + 60)];
}

export function offsetAt(zone: string, std: number, utcMin: number): number {
  checkZone(zone, std);
  const year = civilFromDays(floorDiv(utcMin, 1440))[0];
  if (zone === 'none') return std;
  const [start, end] = dstWindow(zone, std, year);
  return utcMin >= start && utcMin < end ? std + 60 : std;
}

function pad(n: number, width: number): string {
  return String(n).padStart(width, '0');
}

export function formatLocal(zone: string, std: number, utcMin: number): string {
  const off = offsetAt(zone, std, utcMin);
  const local = utcMin + off;
  const [y, m, d] = civilFromDays(floorDiv(local, 1440));
  const mins = floorMod(local, 1440);
  const a = Math.abs(off);
  return pad(y, 4) + '-' + pad(m, 2) + '-' + pad(d, 2) + ' ' + pad(Math.floor(mins / 60), 2) + ':' + pad(mins % 60, 2) + (off >= 0 ? '+' : '-') + pad(Math.floor(a / 60), 2) + ':' + pad(a % 60, 2);
}

export function utcFromLocal(zone: string, std: number, text: string, later: boolean): number {
  checkZone(zone, std);
  const mt = LOCAL.exec(text);
  if (!mt) throw new Error('bad local time');
  const [y, m, d, hh, mm] = mt.slice(1).map((x) => parseInt(x, 10));
  if (hh > 23 || mm > 59) throw new Error('bad local time');
  const local = daysFromCivil(y, m, d) * 1440 + hh * 60 + mm;
  const offsets = zone === 'none' ? [std] : [std, std + 60];
  const valid = offsets.filter((o) => offsetAt(zone, std, local - o) === o);
  if (valid.length === 0) throw new Error('nonexistent local time');
  if (valid.length === 2) return local - (later ? std : std + 60);
  return local - valid[0];
}
''')


def tz_cases(rng):
    zones = [("eu", 60), ("eu", 0), ("eu", 120), ("us", -300), ("us", -480), ("us", -210), ("us", 0), ("none", 0), ("none", 330), ("none", -720), ("none", 840), ("eu", -720), ("us", 840)]
    out = [("days_from_civil", [1970, 1, 1]), ("civil_from_days", [0]), ("weekday", [1970, 1, 1]), ("nth_weekday", [2024, 3, 5, 6]), ("dst_window", ["eu", 60, 2024]), ("offset_at", ["eu", 60, 28344000 // 1]),
           ("format_local", ["eu", 60, 28344000 // 1]), ("utc_from_local", ["us", -300, "2024-03-10 02:30", False]), ("utc_from_local", ["us", -300, "2024-11-03 01:30", True]), ("utc_from_local", ["eu", 60, "2024-10-27 02:30", False])]
    for y, m, d in [(1970, 1, 1), (1969, 12, 31), (1900, 1, 1), (2200, 12, 31), (2000, 2, 29), (1900, 2, 28), (2100, 3, 1), (2024, 2, 29), (1999, 12, 31), (2038, 1, 19), (1960, 2, 29), (2004, 12, 31), (1900, 3, 1), (2000, 3, 1)]:
        out.append(("days_from_civil", [y, m, d]))
        out.append(("weekday", [y, m, d]))
    for y, m, d in [(1900, 2, 29), (2100, 2, 29), (2023, 2, 29), (2024, 4, 31), (2024, 0, 1), (2024, 13, 1), (2024, 1, 0), (2024, 1, 32), (1899, 12, 31), (2201, 1, 1), (-5, 1, 1), (2024, 6, 31), (2024, 9, 31), (2024, 11, 31)]:
        out.append(("days_from_civil", [y, m, d]))
        out.append(("weekday", [y, m, d]))
    for _ in range(30):
        y, m = rng.randint(1900, 2200), rng.randint(1, 12)
        d = rng.randint(1, 28)
        out.append(("days_from_civil", [y, m, d]))
        out.append(("weekday", [y, m, d]))
    for n in [0, -1, 1, 59, 365, 366, -365, -25567, -25568, -25569, 84006, 84007, 84008, 19782, 19783, 11016, -36524, 47482, 10957]:
        out.append(("civil_from_days", [n]))
    if not _NS:
        exec(TZ_PY, _NS)
    for edge in (_NS["days_from_civil"](1900, 1, 1), _NS["days_from_civil"](2200, 12, 31)):
        for delta in (-2, -1, 0, 1, 2):
            out.append(("civil_from_days", [edge + delta]))
    for _ in range(40):
        out.append(("civil_from_days", [rng.randint(-25600, 84100)]))
    for y, m in [(2024, 3), (2024, 10), (2024, 11), (2021, 2), (2000, 2), (1900, 2), (2200, 12), (1900, 1), (2023, 9)]:
        for nth in range(1, 6):
            for wd in (0, 3, 6):
                out.append(("nth_weekday", [y, m, nth, wd]))
    for args in [[2024, 3, 0, 6], [2024, 3, 6, 6], [2024, 3, 1, 7], [2024, 3, 1, -1], [2024, 0, 1, 1], [2024, 13, 1, 1], [1899, 3, 1, 1], [2201, 3, 1, 1], [2024, 3, -1, 6]]:
        out.append(("nth_weekday", args))
    for zone, std in zones:
        for year in [1900, 1970, 1999, 2000, 2007, 2024, 2038, 2100, 2200, 1899, 2201]:
            out.append(("dst_window", [zone, std, year]))
    for zone, std in [("xx", 0), ("EU", 60), ("", 0), ("eu", 841), ("eu", -721), ("us", 1000), ("none", -1000)]:
        out.append(("dst_window", [zone, std, 2024]))
        out.append(("offset_at", [zone, std, 0]))
        out.append(("format_local", [zone, std, 0]))
        out.append(("utc_from_local", [zone, std, "2024-01-01 00:00", False]))
    for zone, std in zones:
        for year in [2000, 2007, 2024, 1950, 2100]:
            window = _window(zone, std, year)
            if not window:
                continue
            for edge in window:
                for delta in (-61, -60, -2, -1, 0, 1, 2, 59, 60, 61):
                    out.append(("offset_at", [zone, std, edge + delta]))
                    out.append(("format_local", [zone, std, edge + delta]))
    for _ in range(60):
        zone, std = rng.choice(zones)
        utc = rng.randint(-2209075200 // 60, 7258118400 // 60 - 2000)
        out.append(("offset_at", [zone, std, utc]))
        out.append(("format_local", [zone, std, utc]))
    for utc in [-2209075200 // 60 - 1, -2209075200 // 60, -2209075200 // 60 + 600, 7258118400 // 60, 7258118400 // 60 - 1, 7258118400 // 60 - 90, -1, 0, 1]:
        for zone, std in [("eu", 60), ("us", -300), ("none", 330), ("none", 0), ("us", 840), ("eu", -720)]:
            out.append(("format_local", [zone, std, utc]))
            out.append(("offset_at", [zone, std, utc]))
    for zone, std in zones:
        for year in [2000, 2024, 2100, 1950]:
            window = _window(zone, std, year)
            if not window:
                continue
            for edge, off_before in ((window[0], std), (window[1], std + 60)):
                local = edge + off_before
                for delta in (-61, -60, -30, -1, 0, 1, 30, 59, 60, 61, 119, 120, 121):
                    text = _local_text(local + delta)
                    out.append(("utc_from_local", [zone, std, text, False]))
                    out.append(("utc_from_local", [zone, std, text, True]))
    for _ in range(40):
        zone, std = rng.choice(zones)
        utc = rng.randint(-2209075200 // 60 + 5000, 7258118400 // 60 - 5000)
        text = _local_text(utc + std)
        out.append(("utc_from_local", [zone, std, text, rng.random() < 0.5]))
    for text in ["2024-02-30 10:00", "2024-13-01 10:00", "2024-00-10 10:00", "2024-01-32 10:00", "2024-01-01 24:00", "2024-01-01 23:60", "2024-01-01 9:00", "2024-1-01 10:00", "2024-01-01T10:00", "2024-01-01 10:00:00", "2024-01-01 10:00 ", " 2024-01-01 10:00", "2024-01-01 10:00\n",
                 "2024/01/01 10:00", "1899-12-31 23:00", "2201-01-01 00:00", "1900-01-01 00:00", "2200-12-31 23:59", "２024-01-01 10:00", "2024-01-01 1٠:00", "", "abc", "2024-01-01", "10:00", "2024-01-01  10:00", "+024-01-01 10:00", "-024-01-01 10:00", "2023-02-29 12:00", "2000-02-29 12:00", "1900-02-29 12:00"]:
        for zone, std in [("eu", 60), ("none", 0), ("us", -300)]:
            out.append(("utc_from_local", [zone, std, text, False]))
    return out


_NS = {}


def _window(zone, std, year):
    """The DST window of the Python reference implementation, used only to choose interesting vectors."""
    if not _NS:
        exec(TZ_PY, _NS)
    return _NS["dst_window"](zone, std, year)


def _local_text(local_min):
    days, mins = divmod(local_min, 1440)
    z = days + 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    y = yoe + era * 400 + (1 if m <= 2 else 0)
    return "%04d-%02d-%02d %02d:%02d" % (y, m, d, mins // 60, mins % 60)


TZ = PortLib(
    slug="tz-rules",
    title="daylight-saving conversions",
    blurb="A scheduling service converts between UTC and wall-clock times of zones with daylight saving rules (nth-weekday transitions, skipped and repeated local times) and every client library has to agree on each minute.",
    spec=TZ_SPEC,
    fns=TZ_FNS,
    impls={"python": {"tz_rules.py": TZ_PY}, "go": {"tzrules.go": TZ_GO}, "typescript": {"src/tz_rules.ts": TZ_TS}},
    cases=tz_cases,
    difficulty=5,
    n_examples=12,
    pairs=[("python", "go", "full"), ("go", "typescript", "full"), ("typescript", "python", "stub"), ("python", "typescript", "stub")],
    traps=["floor division and modulo of negative values", "civil-from-days algorithm", "nth/last weekday rules", "gaps and overlaps in local time", "UTC year versus local year", "offset formatting for negative half-hour zones"],
    tags=["calendar", "dst", "floor-div"],
)
register_port(TZ, __name__)
