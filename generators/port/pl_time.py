"""Port libraries about clocks, calendars and schedules (floor division, negative values, calendar arithmetic)."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

# ======================================================================================================================
# ferry-slots: minutes since the start of a service day, negative values belong to earlier days
# ======================================================================================================================

FERRY_SPEC = dd('''
    Times are whole **minutes since 00:00 of service day 0**. A time may be negative (before day 0) or reach beyond 1439
    (later days). Day numbers use *floor* semantics: minute `-1` is 23:59 of day `-1`, not day `0`.

    * **Clock text.** `HH:MM` (24 hour, two digits each) for a time on day 0; `HH:MM+N` for day `N >= 1` and `HH:MM-N`
      for day `-N`. `N` has no leading zeros. Examples: `0` is `00:00`, `1439` is `23:59`, `1440` is `00:00+1`,
      `-30` is `23:30-1`, `-1441` is `23:59-2`.
    * **Parsing** accepts exactly that grammar and nothing else: hours `00`..`23`, minutes `00`..`59`, an optional suffix
      `+N`/`-N` with `N` from 1 to 6 ASCII digits and no leading zero (`+0`, `-0`, `+01` are invalid). Only ASCII digits are
      digits. The whole string must match: no spaces, no trailing newline.
    * A **timetable** is `first` (the first departure) and a positive `interval` in minutes; departures happen at
      `first + k * interval` for every integer `k >= 0`. An interval of zero or less is an error.
    * `slot_index` is `floor((t - first) / interval)`, which is negative before the first departure.
    * `next_departure` is the earliest departure at or after `now`; before the first departure that is `first`.
    * `wait_minutes` is `next_departure - now`.
    * `align_down(t, step)` is the largest multiple of `step` that is `<= t` (floor, also for negative `t`); `step <= 0` is an error.
    * `split_clock(t)` returns `[day, hour, minute]` with floor semantics: `split_clock(-30)` is `[-1, 23, 30]`.
''')

FERRY_FNS = [
    Fn("fmt_clock", [("minutes", "int")], "str"),
    Fn("parse_clock", [("text", "str")], "int", err=True),
    Fn("split_clock", [("minutes", "int")], "list<int>"),
    Fn("slot_index", [("first", "int"), ("interval", "int"), ("t", "int")], "int", err=True),
    Fn("next_departure", [("first", "int"), ("interval", "int"), ("now", "int")], "int", err=True),
    Fn("wait_minutes", [("first", "int"), ("interval", "int"), ("now", "int")], "int", err=True),
    Fn("align_down", [("t", "int"), ("step", "int")], "int", err=True),
]

FERRY_PY = dd(r'''
import re

_CLOCK = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])(?:([+-])([1-9][0-9]{0,5}))?")


def fmt_clock(minutes):
    day, rem = divmod(minutes, 1440)
    out = "%02d:%02d" % (rem // 60, rem % 60)
    if day > 0:
        out += "+%d" % day
    elif day < 0:
        out += "-%d" % -day
    return out


def parse_clock(text):
    m = _CLOCK.fullmatch(text)
    if not m:
        raise ValueError("bad clock text: %r" % text)
    total = int(m.group(1)) * 60 + int(m.group(2))
    if m.group(3):
        n = int(m.group(4))
        total += 1440 * (n if m.group(3) == "+" else -n)
    return total


def split_clock(minutes):
    day, rem = divmod(minutes, 1440)
    return [day, rem // 60, rem % 60]


def slot_index(first, interval, t):
    if interval <= 0:
        raise ValueError("interval must be positive")
    return (t - first) // interval


def next_departure(first, interval, now):
    if interval <= 0:
        raise ValueError("interval must be positive")
    if now <= first:
        return first
    return first + -((first - now) // interval) * interval


def wait_minutes(first, interval, now):
    return next_departure(first, interval, now) - now


def align_down(t, step):
    if step <= 0:
        raise ValueError("step must be positive")
    return t - t % step
''')

FERRY_GO = dd(r'''
package ferryslots

import (
	"errors"
	"fmt"
)

func floorDivMod(a, b int64) (int64, int64) {
	q, r := a/b, a%b
	if r != 0 && (r < 0) != (b < 0) {
		q--
		r += b
	}
	return q, r
}

func isDigit(c byte) bool { return c >= '0' && c <= '9' }

// FmtClock renders minutes since 00:00 of day 0 as HH:MM with an optional day suffix.
func FmtClock(minutes int64) string {
	day, rem := floorDivMod(minutes, 1440)
	s := fmt.Sprintf("%02d:%02d", rem/60, rem%60)
	if day > 0 {
		s += fmt.Sprintf("+%d", day)
	} else if day < 0 {
		s += fmt.Sprintf("-%d", -day)
	}
	return s
}

// ParseClock is the strict inverse of FmtClock.
func ParseClock(text string) (int64, error) {
	bad := errors.New("bad clock text")
	n := len(text)
	if n != 5 && !(n >= 7 && n <= 12) {
		return 0, bad
	}
	if !isDigit(text[0]) || !isDigit(text[1]) || text[2] != ':' || !isDigit(text[3]) || !isDigit(text[4]) {
		return 0, bad
	}
	hh := int64(text[0]-'0')*10 + int64(text[1]-'0')
	mm := int64(text[3]-'0')*10 + int64(text[4]-'0')
	if hh > 23 || mm > 59 {
		return 0, bad
	}
	total := hh*60 + mm
	if n > 5 {
		sign := text[5]
		if sign != '+' && sign != '-' {
			return 0, bad
		}
		digits := text[6:]
		if len(digits) < 1 || len(digits) > 6 || digits[0] == '0' {
			return 0, bad
		}
		var d int64
		for i := 0; i < len(digits); i++ {
			if !isDigit(digits[i]) {
				return 0, bad
			}
			d = d*10 + int64(digits[i]-'0')
		}
		if sign == '-' {
			d = -d
		}
		total += 1440 * d
	}
	return total, nil
}

func SplitClock(minutes int64) []int64 {
	day, rem := floorDivMod(minutes, 1440)
	return []int64{day, rem / 60, rem % 60}
}

func SlotIndex(first, interval, t int64) (int64, error) {
	if interval <= 0 {
		return 0, errors.New("interval must be positive")
	}
	q, _ := floorDivMod(t-first, interval)
	return q, nil
}

func NextDeparture(first, interval, now int64) (int64, error) {
	if interval <= 0 {
		return 0, errors.New("interval must be positive")
	}
	if now <= first {
		return first, nil
	}
	k := (now - first + interval - 1) / interval
	return first + k*interval, nil
}

func WaitMinutes(first, interval, now int64) (int64, error) {
	d, err := NextDeparture(first, interval, now)
	if err != nil {
		return 0, err
	}
	return d - now, nil
}

func AlignDown(t, step int64) (int64, error) {
	if step <= 0 {
		return 0, errors.New("step must be positive")
	}
	_, r := floorDivMod(t, step)
	return t - r, nil
}
''')

FERRY_RS = dd(r'''
fn floor_div_mod(a: i64, b: i64) -> (i64, i64) {
    (a.div_euclid(b), a.rem_euclid(b))
}

/// Renders minutes since 00:00 of day 0 as HH:MM with an optional day suffix.
pub fn fmt_clock(minutes: i64) -> String {
    let (day, rem) = floor_div_mod(minutes, 1440);
    let mut s = format!("{:02}:{:02}", rem / 60, rem % 60);
    if day > 0 {
        s.push_str(&format!("+{}", day));
    } else if day < 0 {
        s.push_str(&format!("-{}", -day));
    }
    s
}

pub fn parse_clock(text: &str) -> Result<i64, String> {
    let b = text.as_bytes();
    let bad = || format!("bad clock text: {:?}", text);
    let n = b.len();
    if n != 5 && !(7..=12).contains(&n) {
        return Err(bad());
    }
    let dig = |i: usize| -> Option<i64> { if b[i].is_ascii_digit() { Some((b[i] - b'0') as i64) } else { None } };
    let (h1, h2, m1, m2) = match (dig(0), dig(1), dig(3), dig(4)) {
        (Some(a), Some(b), Some(c), Some(d)) => (a, b, c, d),
        _ => return Err(bad()),
    };
    if b[2] != b':' {
        return Err(bad());
    }
    let (hh, mm) = (h1 * 10 + h2, m1 * 10 + m2);
    if hh > 23 || mm > 59 {
        return Err(bad());
    }
    let mut total = hh * 60 + mm;
    if n > 5 {
        let sign = b[5];
        if sign != b'+' && sign != b'-' {
            return Err(bad());
        }
        let digits = &b[6..];
        if digits.is_empty() || digits.len() > 6 || digits[0] == b'0' || !digits.iter().all(|c| c.is_ascii_digit()) {
            return Err(bad());
        }
        let mut d: i64 = 0;
        for c in digits {
            d = d * 10 + (c - b'0') as i64;
        }
        total += 1440 * if sign == b'-' { -d } else { d };
    }
    Ok(total)
}

pub fn split_clock(minutes: i64) -> Vec<i64> {
    let (day, rem) = floor_div_mod(minutes, 1440);
    vec![day, rem / 60, rem % 60]
}

pub fn slot_index(first: i64, interval: i64, t: i64) -> Result<i64, String> {
    if interval <= 0 {
        return Err("interval must be positive".to_string());
    }
    Ok((t - first).div_euclid(interval))
}

pub fn next_departure(first: i64, interval: i64, now: i64) -> Result<i64, String> {
    if interval <= 0 {
        return Err("interval must be positive".to_string());
    }
    if now <= first {
        return Ok(first);
    }
    let k = (now - first + interval - 1) / interval;
    Ok(first + k * interval)
}

pub fn wait_minutes(first: i64, interval: i64, now: i64) -> Result<i64, String> {
    next_departure(first, interval, now).map(|d| d - now)
}

pub fn align_down(t: i64, step: i64) -> Result<i64, String> {
    if step <= 0 {
        return Err("step must be positive".to_string());
    }
    Ok(t - t.rem_euclid(step))
}
''')


def ferry_cases(rng):
    out = [
        ("fmt_clock", [0]), ("fmt_clock", [1439]), ("fmt_clock", [1440]), ("fmt_clock", [-30]), ("fmt_clock", [-1441]),
        ("parse_clock", ["23:30-1"]), ("next_departure", [360, 20, 400]), ("align_down", [-7, 5]),
    ]
    for t in [-1, -60, -1440, -1439, 59, 60, 2879, 2880, 1000000, -1000000, 86399, -86401]:
        out.append(("fmt_clock", [t]))
        out.append(("split_clock", [t]))
    for _ in range(25):
        t = rng.randint(-30000, 30000)
        out.append(("fmt_clock", [t]))
        out.append(("split_clock", [t]))
        out.append(("parse_clock", [_fmt(t)]))
    for s in ["00:00", "23:59", "09:05+3", "09:05-3", "12:00+999999", "12:00-999999", "00:00+1", "24:00", "23:60", "9:05", "09:5", "09:05+0", "09:05-0",
              "09:05+01", "09:05+", "09:05-", "09:05+1000000", "09:05 ", " 09:05", "09:05\n", "09-05", "09:05*2", "", "ab:cd", "０９:０５",
              "09:05+٣", "٠٩:05", "09:05+1+2", "+1", "09:05--1", "2:30", "12:0", "99:99", "00:00-1", "00:00-0"]:
        out.append(("parse_clock", [s]))
    for _ in range(30):
        first = rng.randint(-500, 1500)
        interval = rng.choice([1, 3, 7, 15, 20, 45, 60, 90, 1440])
        now = first + rng.randint(-2000, 4000)
        out.append(("next_departure", [first, interval, now]))
        out.append(("wait_minutes", [first, interval, now]))
        out.append(("slot_index", [first, interval, now]))
    for first, interval, now in [(360, 20, 360), (360, 20, 361), (360, 20, 379), (360, 20, 380), (360, 20, 0), (-60, 30, -61), (-60, 30, -60), (0, 1, 5), (10, 10, -10)]:
        out.append(("next_departure", [first, interval, now]))
        out.append(("slot_index", [first, interval, now]))
    for first, interval in [(0, 0), (5, -3)]:
        out.append(("next_departure", [first, interval, 10]))
        out.append(("slot_index", [first, interval, 10]))
        out.append(("wait_minutes", [first, interval, 10]))
    for t, step in [(-7, 5), (7, 5), (-10, 5), (0, 5), (-1, 1440), (1439, 1440), (-1441, 1440), (123456, 1), (-123457, 60), (5, 0), (5, -2)]:
        out.append(("align_down", [t, step]))
    for _ in range(12):
        out.append(("align_down", [rng.randint(-5000, 5000), rng.choice([2, 3, 7, 10, 60, 1000])]))
    return out


def _fmt(t):
    day, rem = divmod(t, 1440)
    s = "%02d:%02d" % (rem // 60, rem % 60)
    return s + ("+%d" % day if day > 0 else "-%d" % -day if day < 0 else "")


FERRY = PortLib(
    slug="ferry-slots",
    title="ferry timetable clock arithmetic",
    blurb="The harbour authority's timetable service counts minutes from the start of a service day and has to behave for times before day 0 as well.",
    spec=FERRY_SPEC,
    fns=FERRY_FNS,
    impls={"python": {"ferry_slots.py": FERRY_PY}, "go": {"ferryslots.go": FERRY_GO}, "rust": {"src/lib.rs": FERRY_RS}},
    cases=ferry_cases,
    difficulty=2,
    traps=["floor division and modulo of negative integers", "strict text grammar (ASCII digits, trailing newline)", "error idioms"],
    tags=["floor-div", "strict-parsing"],
    pairs=[("python", "go", "full"), ("python", "rust", "full"), ("go", "rust", "stub"), ("rust", "python", "stub")],
)
register_port(FERRY, __name__)
