"""Lab sample labels with an invented check character: validate, parse, make and increment labels."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

PREFIXES = ["LB", "SMP", "TB", "VX", "RNA", "CRY", "QT", "PL"]
SITE_POOL2 = ["KR", "OS", "TN", "BV", "HW", "MZ", "PD", "WS", "FX", "GN", "DQ", "RC"]
SITE_POOL3 = ["KRO", "OSL", "TNB", "BVH", "HWM", "MZP", "PDW", "WSF", "FXG", "GNC", "DQR", "RCT"]
SEPS = ["-", ".", "/", "_", ""]
A32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
A36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LANG_PLAN = ["python", "c", "rust", "go", "c", "python", "rust", "go", "c", "rust", "go", "python"]


def params(rng, level, i=0):
    sitelen = rng.choice([2, 3])
    pool = SITE_POOL2 if sitelen == 2 else SITE_POOL3
    alpha = rng.choice([A32, A36])
    sites = [s for s in pool if all(c in alpha for c in s)]
    sites = rng.sample(sites, rng.randrange(3, 6))
    sep_choices = rng.sample(SEPS, 3)
    return {
        "level": level,
        "prefix": rng.choice(PREFIXES),
        "s1": sep_choices[0], "s2": sep_choices[1], "s3": sep_choices[2],
        "sites": sites, "sitelen": sitelen,
        "date_kind": (["ymd", "yo", "ymd8"] if level >= 3 else ["ymd", "ymd8"])[i % (3 if level >= 3 else 2)],
        "serial_w": rng.choice([3, 4, 5]),
        "nozero": rng.random() < 0.6,
        "weights": [rng.randrange(1, 9) for _ in range(rng.randrange(3, 7))],
        "alpha": alpha,
        "lenient": level >= 3 and rng.random() < 0.7,
        "has_parse": level >= 2, "has_make": level >= 2, "has_next": level >= 3,
    }


PY = r'''
PREFIX = "@PREFIX@"
S1 = "@S1@"
S2 = "@S2@"
S3 = "@S3@"
SITES = @SITES_PY@
SITELEN = @SITELEN@
DATE_KIND = "@DATEKIND@"
SERIAL_W = @SERIALW@
NOZERO = @NOZERO@
WEIGHTS = @WEIGHTS_PY@
ALPHA = "@ALPHA@"
LENIENT = @LENIENT@
HAS_PARSE = @HAS_PARSE@
HAS_MAKE = @HAS_MAKE@
HAS_NEXT = @HAS_NEXT@

DATELEN = {"ymd": 6, "yo": 5, "ymd8": 8}[DATE_KIND]
TOTAL = len(PREFIX) + len(S1) + SITELEN + DATELEN + len(S2) + SERIAL_W + len(S3) + 1
MAXSERIAL = 10 ** SERIAL_W - 1


def is_digits(s):
    return s != "" and all(c in "0123456789" for c in s)


def leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def mdays(y, m):
    return [31, 29 if leap(y) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]


def check_char(body):
    s = 0
    for i, c in enumerate(body):
        s += ALPHA.index(c) * WEIGHTS[i % len(WEIGHTS)]
    return ALPHA[s % len(ALPHA)]


def date_text(y, m, d):
    if DATE_KIND == "ymd":
        return "%02d%02d%02d" % (y - 2000, m, d)
    if DATE_KIND == "ymd8":
        return "%04d%02d%02d" % (y, m, d)
    n = sum(mdays(y, k) for k in range(1, m)) + d
    return "%02d%03d" % (y - 2000, n)


def date_value(t):
    """(y, m, d) for the DATE field text, or None."""
    if DATE_KIND == "ymd":
        y, m, d = 2000 + int(t[0:2]), int(t[2:4]), int(t[4:6])
    elif DATE_KIND == "ymd8":
        y, m, d = int(t[0:4]), int(t[4:6]), int(t[6:8])
        if y < 2000 or y > 2099:
            return None
    else:
        y, n = 2000 + int(t[0:2]), int(t[2:5])
        if n < 1 or n > (366 if leap(y) else 365):
            return None
        m = 1
        while n > mdays(y, m):
            n -= mdays(y, m)
            m += 1
        return (y, m, n)
    if m < 1 or m > 12 or d < 1 or d > mdays(y, m):
        return None
    return (y, m, d)


def decode(label):
    """('ok', site, (y, m, d), serial) or ('err', reason)"""
    if LENIENT:
        label = label.strip(" ").upper()
    if len(label) != TOTAL:
        return ("err", "length")
    p = len(PREFIX)
    q = p + len(S1)
    site = label[q:q + SITELEN]
    r = q + SITELEN
    date = label[r:r + DATELEN]
    s = r + DATELEN
    t = s + len(S2)
    serial = label[t:t + SERIAL_W]
    u = t + SERIAL_W
    chk = label[u + len(S3):]
    if label[:p] != PREFIX or label[p:q] != S1 or label[s:t] != S2 or label[u:u + len(S3)] != S3:
        return ("err", "format")
    if not is_digits(date) or not is_digits(serial):
        return ("err", "format")
    if site not in SITES:
        return ("err", "site")
    dv = date_value(date)
    if dv is None:
        return ("err", "date")
    if NOZERO and int(serial) == 0:
        return ("err", "serial")
    if chk != check_char(site + date + serial):
        return ("err", "check")
    return ("ok", site, dv, int(serial))


def build(site, y, m, d, serial):
    body = site + date_text(y, m, d) + ("%0*d" % (SERIAL_W, serial))
    return PREFIX + S1 + site + date_text(y, m, d) + S2 + ("%0*d" % (SERIAL_W, serial)) + S3 + check_char(body)


def label(op, text):
    if op == "validate":
        r = decode(text)
        return "valid" if r[0] == "ok" else "invalid: " + r[1]
    if HAS_PARSE and op == "parse":
        r = decode(text)
        if r[0] != "ok":
            return "invalid: " + r[1]
        y, m, d = r[2]
        return "site=%s\ndate=%04d-%02d-%02d\nserial=%d" % (r[1], y, m, d, r[3])
    if HAS_MAKE and op == "make":
        f = text.split(" ")
        if len(f) != 3 or "" in f:
            return "invalid: format"
        site, ds, ss = f
        if site not in SITES:
            return "invalid: site"
        ok = len(ds) == 10 and ds[4] == "-" and ds[7] == "-" and is_digits(ds[:4]) and is_digits(ds[5:7]) and is_digits(ds[8:])
        if not ok:
            return "invalid: date"
        y, m, d = int(ds[:4]), int(ds[5:7]), int(ds[8:])
        if y < 2000 or y > 2099 or m < 1 or m > 12 or d < 1 or d > mdays(y, m):
            return "invalid: date"
        if not is_digits(ss) or len(ss) > 9:
            return "invalid: serial"
        n = int(ss)
        if n > MAXSERIAL or (NOZERO and n == 0):
            return "invalid: serial"
        return build(site, y, m, d, n)
    if HAS_NEXT and op == "next":
        r = decode(text)
        if r[0] != "ok":
            return "invalid: " + r[1]
        if r[3] >= MAXSERIAL:
            return "invalid: overflow"
        y, m, d = r[2]
        return build(r[1], y, m, d, r[3] + 1)
    return "invalid: op"
'''

RS = r'''
const PREFIX: &str = "@PREFIX@";
const S1: &str = "@S1@";
const S2: &str = "@S2@";
const S3: &str = "@S3@";
const SITES: &[&str] = &@SITES_RS@;
const SITELEN: usize = @SITELEN@;
const DATE_KIND: &str = "@DATEKIND@";
const SERIAL_W: usize = @SERIALW@;
const NOZERO: bool = @NOZERO@;
const WEIGHTS: &[usize] = &@WEIGHTS_RS@;
const ALPHA: &str = "@ALPHA@";
const LENIENT: bool = @LENIENT@;
const HAS_PARSE: bool = @HAS_PARSE@;
const HAS_MAKE: bool = @HAS_MAKE@;
const HAS_NEXT: bool = @HAS_NEXT@;

fn datelen() -> usize {
    match DATE_KIND {
        "ymd" => 6,
        "yo" => 5,
        _ => 8,
    }
}

fn is_digits(s: &str) -> bool {
    !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())
}

fn leap(y: i64) -> bool {
    y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)
}

fn mdays(y: i64, m: i64) -> i64 {
    match m {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        _ => if leap(y) { 29 } else { 28 },
    }
}

fn check_char(body: &str) -> char {
    let alpha: Vec<char> = ALPHA.chars().collect();
    let mut s = 0usize;
    for (i, c) in body.chars().enumerate() {
        let v = alpha.iter().position(|&a| a == c).unwrap_or(0);
        s += v * WEIGHTS[i % WEIGHTS.len()];
    }
    alpha[s % alpha.len()]
}

fn date_text(y: i64, m: i64, d: i64) -> String {
    match DATE_KIND {
        "ymd" => format!("{:02}{:02}{:02}", y - 2000, m, d),
        "ymd8" => format!("{:04}{:02}{:02}", y, m, d),
        _ => {
            let mut n = d;
            for k in 1..m {
                n += mdays(y, k);
            }
            format!("{:02}{:03}", y - 2000, n)
        }
    }
}

fn num(s: &str) -> i64 {
    s.parse::<i64>().unwrap_or(0)
}

fn date_value(t: &str) -> Option<(i64, i64, i64)> {
    let (y, m, d);
    match DATE_KIND {
        "ymd" => {
            y = 2000 + num(&t[0..2]);
            m = num(&t[2..4]);
            d = num(&t[4..6]);
        }
        "ymd8" => {
            y = num(&t[0..4]);
            m = num(&t[4..6]);
            d = num(&t[6..8]);
            if y < 2000 || y > 2099 {
                return None;
            }
        }
        _ => {
            let y = 2000 + num(&t[0..2]);
            let mut n = num(&t[2..5]);
            let max_day = if leap(y) { 366 } else { 365 };
            if n < 1 || n > max_day {
                return None;
            }
            let mut m = 1;
            while n > mdays(y, m) {
                n -= mdays(y, m);
                m += 1;
            }
            return Some((y, m, n));
        }
    }
    if m < 1 || m > 12 || d < 1 || d > mdays(y, m) {
        return None;
    }
    Some((y, m, d))
}

enum Dec {
    Ok(String, (i64, i64, i64), i64),
    Err(&'static str),
}

fn decode(text: &str) -> Dec {
    let owned;
    let label: &str = if LENIENT {
        owned = text.trim_matches(' ').to_ascii_uppercase();
        &owned
    } else {
        text
    };
    let dl = datelen();
    let total = PREFIX.len() + S1.len() + SITELEN + dl + S2.len() + SERIAL_W + S3.len() + 1;
    if label.len() != total || !label.is_ascii() {
        return Dec::Err("length");
    }
    let p = PREFIX.len();
    let q = p + S1.len();
    let site = &label[q..q + SITELEN];
    let r = q + SITELEN;
    let date = &label[r..r + dl];
    let s = r + dl;
    let t = s + S2.len();
    let serial = &label[t..t + SERIAL_W];
    let u = t + SERIAL_W;
    let chk = &label[u + S3.len()..];
    if &label[..p] != PREFIX || &label[p..q] != S1 || &label[s..t] != S2 || &label[u..u + S3.len()] != S3 {
        return Dec::Err("format");
    }
    if !is_digits(date) || !is_digits(serial) {
        return Dec::Err("format");
    }
    if !SITES.contains(&site) {
        return Dec::Err("site");
    }
    let dv = match date_value(date) {
        Some(v) => v,
        None => return Dec::Err("date"),
    };
    if NOZERO && num(serial) == 0 {
        return Dec::Err("serial");
    }
    let body = format!("{}{}{}", site, date, serial);
    if chk != check_char(&body).to_string() {
        return Dec::Err("check");
    }
    Dec::Ok(site.to_string(), dv, num(serial))
}

fn build(site: &str, y: i64, m: i64, d: i64, serial: i64) -> String {
    let dt = date_text(y, m, d);
    let sr = format!("{:0w$}", serial, w = SERIAL_W);
    let body = format!("{}{}{}", site, dt, sr);
    format!("{}{}{}{}{}{}{}{}", PREFIX, S1, site, dt, S2, sr, S3, check_char(&body))
}

/// Label tool: validate, parse, make, next.
pub fn label(op: &str, text: &str) -> String {
    let max_serial = 10i64.pow(SERIAL_W as u32) - 1;
    if op == "validate" {
        return match decode(text) {
            Dec::Ok(..) => "valid".to_string(),
            Dec::Err(e) => format!("invalid: {}", e),
        };
    }
    if HAS_PARSE && op == "parse" {
        return match decode(text) {
            Dec::Ok(site, (y, m, d), n) => format!("site={}\ndate={:04}-{:02}-{:02}\nserial={}", site, y, m, d, n),
            Dec::Err(e) => format!("invalid: {}", e),
        };
    }
    if HAS_MAKE && op == "make" {
        let f: Vec<&str> = text.split(' ').collect();
        if f.len() != 3 || f.iter().any(|x| x.is_empty()) {
            return "invalid: format".to_string();
        }
        let (site, ds, ss) = (f[0], f[1], f[2]);
        if !SITES.contains(&site) {
            return "invalid: site".to_string();
        }
        let b = ds.as_bytes();
        let ok = ds.len() == 10 && b[4] == b'-' && b[7] == b'-' && is_digits(&ds[..4]) && is_digits(&ds[5..7]) && is_digits(&ds[8..]);
        if !ok {
            return "invalid: date".to_string();
        }
        let (y, m, d) = (num(&ds[..4]), num(&ds[5..7]), num(&ds[8..]));
        if y < 2000 || y > 2099 || m < 1 || m > 12 || d < 1 || d > mdays(y, m) {
            return "invalid: date".to_string();
        }
        if !is_digits(ss) || ss.len() > 9 {
            return "invalid: serial".to_string();
        }
        let n = num(ss);
        if n > max_serial || (NOZERO && n == 0) {
            return "invalid: serial".to_string();
        }
        return build(site, y, m, d, n);
    }
    if HAS_NEXT && op == "next" {
        return match decode(text) {
            Dec::Err(e) => format!("invalid: {}", e),
            Dec::Ok(site, (y, m, d), n) => {
                if n >= max_serial {
                    "invalid: overflow".to_string()
                } else {
                    build(&site, y, m, d, n + 1)
                }
            }
        };
    }
    "invalid: op".to_string()
}
'''

GO = r'''
package labelcode

import (
	"fmt"
	"strconv"
	"strings"
)

const (
	prefix    = "@PREFIX@"
	s1        = "@S1@"
	s2        = "@S2@"
	s3        = "@S3@"
	siteLen   = @SITELEN@
	dateKind  = "@DATEKIND@"
	serialW   = @SERIALW@
	noZero    = @NOZERO@
	alpha     = "@ALPHA@"
	lenient   = @LENIENT@
	hasParse  = @HAS_PARSE@
	hasMake   = @HAS_MAKE@
	hasNext   = @HAS_NEXT@
)

var sites = @SITES_GO@
var weights = @WEIGHTS_GO@

func dateLen() int {
	switch dateKind {
	case "ymd":
		return 6
	case "yo":
		return 5
	}
	return 8
}

func isDigits(s string) bool {
	if s == "" {
		return false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	return true
}

func leap(y int) bool { return y%4 == 0 && (y%100 != 0 || y%400 == 0) }

func mdays(y, m int) int {
	switch m {
	case 1, 3, 5, 7, 8, 10, 12:
		return 31
	case 4, 6, 9, 11:
		return 30
	}
	if leap(y) {
		return 29
	}
	return 28
}

func checkChar(body string) byte {
	s := 0
	for i := 0; i < len(body); i++ {
		s += strings.IndexByte(alpha, body[i]) * weights[i%len(weights)]
	}
	return alpha[s%len(alpha)]
}

func num(s string) int {
	v, _ := strconv.Atoi(s)
	return v
}

func dateText(y, m, d int) string {
	switch dateKind {
	case "ymd":
		return fmt.Sprintf("%02d%02d%02d", y-2000, m, d)
	case "ymd8":
		return fmt.Sprintf("%04d%02d%02d", y, m, d)
	}
	n := d
	for k := 1; k < m; k++ {
		n += mdays(y, k)
	}
	return fmt.Sprintf("%02d%03d", y-2000, n)
}

func dateValue(t string) (int, int, int, bool) {
	var y, m, d int
	switch dateKind {
	case "ymd":
		y, m, d = 2000+num(t[0:2]), num(t[2:4]), num(t[4:6])
	case "ymd8":
		y, m, d = num(t[0:4]), num(t[4:6]), num(t[6:8])
		if y < 2000 || y > 2099 {
			return 0, 0, 0, false
		}
	default:
		y = 2000 + num(t[0:2])
		n := num(t[2:5])
		max := 365
		if leap(y) {
			max = 366
		}
		if n < 1 || n > max {
			return 0, 0, 0, false
		}
		m = 1
		for n > mdays(y, m) {
			n -= mdays(y, m)
			m++
		}
		return y, m, n, true
	}
	if m < 1 || m > 12 || d < 1 || d > mdays(y, m) {
		return 0, 0, 0, false
	}
	return y, m, d, true
}

type decoded struct {
	err     string
	site    string
	y, m, d int
	serial  int
}

func decode(label string) decoded {
	if lenient {
		label = strings.ToUpper(strings.Trim(label, " "))
	}
	dl := dateLen()
	total := len(prefix) + len(s1) + siteLen + dl + len(s2) + serialW + len(s3) + 1
	if len(label) != total {
		return decoded{err: "length"}
	}
	p := len(prefix)
	q := p + len(s1)
	site := label[q : q+siteLen]
	r := q + siteLen
	date := label[r : r+dl]
	s := r + dl
	t := s + len(s2)
	serial := label[t : t+serialW]
	u := t + serialW
	chk := label[u+len(s3):]
	if label[:p] != prefix || label[p:q] != s1 || label[s:t] != s2 || label[u:u+len(s3)] != s3 {
		return decoded{err: "format"}
	}
	if !isDigits(date) || !isDigits(serial) {
		return decoded{err: "format"}
	}
	found := false
	for _, x := range sites {
		if x == site {
			found = true
		}
	}
	if !found {
		return decoded{err: "site"}
	}
	y, m, d, ok := dateValue(date)
	if !ok {
		return decoded{err: "date"}
	}
	if noZero && num(serial) == 0 {
		return decoded{err: "serial"}
	}
	if chk != string(checkChar(site+date+serial)) {
		return decoded{err: "check"}
	}
	return decoded{site: site, y: y, m: m, d: d, serial: num(serial)}
}

func build(site string, y, m, d, serial int) string {
	dt := dateText(y, m, d)
	sr := fmt.Sprintf("%0*d", serialW, serial)
	return prefix + s1 + site + dt + s2 + sr + s3 + string(checkChar(site+dt+sr))
}

// Label is the label tool: validate, parse, make, next.
func Label(op, text string) string {
	maxSerial := 1
	for i := 0; i < serialW; i++ {
		maxSerial *= 10
	}
	maxSerial--
	switch {
	case op == "validate":
		r := decode(text)
		if r.err != "" {
			return "invalid: " + r.err
		}
		return "valid"
	case hasParse && op == "parse":
		r := decode(text)
		if r.err != "" {
			return "invalid: " + r.err
		}
		return fmt.Sprintf("site=%s\ndate=%04d-%02d-%02d\nserial=%d", r.site, r.y, r.m, r.d, r.serial)
	case hasMake && op == "make":
		f := strings.Split(text, " ")
		if len(f) != 3 || f[0] == "" || f[1] == "" || f[2] == "" {
			return "invalid: format"
		}
		site, ds, ss := f[0], f[1], f[2]
		found := false
		for _, x := range sites {
			if x == site {
				found = true
			}
		}
		if !found {
			return "invalid: site"
		}
		ok := len(ds) == 10 && ds[4] == '-' && ds[7] == '-' && isDigits(ds[:4]) && isDigits(ds[5:7]) && isDigits(ds[8:])
		if !ok {
			return "invalid: date"
		}
		y, m, d := num(ds[:4]), num(ds[5:7]), num(ds[8:])
		if y < 2000 || y > 2099 || m < 1 || m > 12 || d < 1 || d > mdays(y, m) {
			return "invalid: date"
		}
		if !isDigits(ss) || len(ss) > 9 {
			return "invalid: serial"
		}
		n := num(ss)
		if n > maxSerial || (noZero && n == 0) {
			return "invalid: serial"
		}
		return build(site, y, m, d, n)
	case hasNext && op == "next":
		r := decode(text)
		if r.err != "" {
			return "invalid: " + r.err
		}
		if r.serial >= maxSerial {
			return "invalid: overflow"
		}
		return build(r.site, r.y, r.m, r.d, r.serial+1)
	}
	return "invalid: op"
}
'''

CC = r'''
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "labelcode.h"

#define PREFIX "@PREFIX@"
#define S1 "@S1@"
#define S2 "@S2@"
#define S3 "@S3@"
#define SITELEN @SITELEN@
#define DATE_KIND "@DATEKIND@"
#define SERIAL_W @SERIALW@
#define NOZERO @NOZERO@
#define ALPHA "@ALPHA@"
#define LENIENT @LENIENT@
#define HAS_PARSE @HAS_PARSE@
#define HAS_MAKE @HAS_MAKE@
#define HAS_NEXT @HAS_NEXT@

static const char *SITES[] = @SITES_C@;
#define NSITES ((int)(sizeof SITES / sizeof SITES[0]))
static const int WEIGHTS[] = @WEIGHTS_C@;
#define NWEIGHTS ((int)(sizeof WEIGHTS / sizeof WEIGHTS[0]))

static int date_len(void) {
    if (strcmp(DATE_KIND, "ymd") == 0) return 6;
    if (strcmp(DATE_KIND, "yo") == 0) return 5;
    return 8;
}

static int is_digits(const char *s, int n) {
    if (n <= 0) return 0;
    for (int i = 0; i < n; i++)
        if (s[i] < '0' || s[i] > '9') return 0;
    return 1;
}

static long num(const char *s, int n) {
    long v = 0;
    for (int i = 0; i < n; i++) v = v * 10 + (s[i] - '0');
    return v;
}

static int leap(int y) { return y % 4 == 0 && (y % 100 != 0 || y % 400 == 0); }

static int mdays(int y, int m) {
    static const int dm[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    if (m == 2 && leap(y)) return 29;
    return dm[m - 1];
}

static char check_char(const char *body) {
    long s = 0;
    int alen = (int)strlen(ALPHA);
    for (int i = 0; body[i]; i++) {
        const char *p = strchr(ALPHA, body[i]);
        long v = p ? (long)(p - ALPHA) : 0;
        s += v * WEIGHTS[i % NWEIGHTS];
    }
    return ALPHA[s % alen];
}

static void date_text(char *out, int y, int m, int d) {
    if (strcmp(DATE_KIND, "ymd") == 0) sprintf(out, "%02d%02d%02d", y - 2000, m, d);
    else if (strcmp(DATE_KIND, "ymd8") == 0) sprintf(out, "%04d%02d%02d", y, m, d);
    else {
        int n = d;
        for (int k = 1; k < m; k++) n += mdays(y, k);
        sprintf(out, "%02d%03d", y - 2000, n);
    }
}

static int date_value(const char *t, int *py, int *pm, int *pd) {
    int y, m, d;
    if (strcmp(DATE_KIND, "ymd") == 0) {
        y = 2000 + (int)num(t, 2);
        m = (int)num(t + 2, 2);
        d = (int)num(t + 4, 2);
    } else if (strcmp(DATE_KIND, "ymd8") == 0) {
        y = (int)num(t, 4);
        m = (int)num(t + 4, 2);
        d = (int)num(t + 6, 2);
        if (y < 2000 || y > 2099) return 0;
    } else {
        y = 2000 + (int)num(t, 2);
        int n = (int)num(t + 2, 3);
        if (n < 1 || n > (leap(y) ? 366 : 365)) return 0;
        m = 1;
        while (n > mdays(y, m)) {
            n -= mdays(y, m);
            m++;
        }
        *py = y; *pm = m; *pd = n;
        return 1;
    }
    if (m < 1 || m > 12 || d < 1 || d > mdays(y, m)) return 0;
    *py = y; *pm = m; *pd = d;
    return 1;
}

typedef struct {
    const char *err;
    char site[8];
    int y, m, d;
    long serial;
} Dec;

static Dec decode(const char *text) {
    Dec r;
    memset(&r, 0, sizeof r);
    char label[256];
    size_t n = strlen(text);
    if (n > 200) n = 200;
    memcpy(label, text, n);
    label[n] = 0;
    char *lab = label;
    if (LENIENT) {
        while (*lab == ' ') lab++;
        size_t l = strlen(lab);
        while (l > 0 && lab[l - 1] == ' ') lab[--l] = 0;
        for (size_t i = 0; lab[i]; i++) lab[i] = (char)toupper((unsigned char)lab[i]);
    }
    int dl = date_len();
    int total = (int)strlen(PREFIX) + (int)strlen(S1) + SITELEN + dl + (int)strlen(S2) + SERIAL_W + (int)strlen(S3) + 1;
    if ((int)strlen(text) > 200 || (int)strlen(lab) != total) { r.err = "length"; return r; }
    int p = (int)strlen(PREFIX), q = p + (int)strlen(S1);
    const char *site = lab + q;
    int rr = q + SITELEN;
    const char *date = lab + rr;
    int s = rr + dl, t = s + (int)strlen(S2);
    const char *serial = lab + t;
    int u = t + SERIAL_W;
    char chk = lab[u + (int)strlen(S3)];
    if (strncmp(lab, PREFIX, p) != 0 || strncmp(lab + p, S1, strlen(S1)) != 0 || strncmp(lab + s, S2, strlen(S2)) != 0 ||
        strncmp(lab + u, S3, strlen(S3)) != 0) { r.err = "format"; return r; }
    if (!is_digits(date, dl) || !is_digits(serial, SERIAL_W)) { r.err = "format"; return r; }
    int found = 0;
    for (int i = 0; i < NSITES; i++)
        if (strlen(SITES[i]) == (size_t)SITELEN && strncmp(site, SITES[i], SITELEN) == 0) found = 1;
    if (!found) { r.err = "site"; return r; }
    if (!date_value(date, &r.y, &r.m, &r.d)) { r.err = "date"; return r; }
    r.serial = num(serial, SERIAL_W);
    if (NOZERO && r.serial == 0) { r.err = "serial"; return r; }
    char body[64];
    memcpy(body, site, SITELEN);
    memcpy(body + SITELEN, date, dl);
    memcpy(body + SITELEN + dl, serial, SERIAL_W);
    body[SITELEN + dl + SERIAL_W] = 0;
    if (chk != check_char(body)) { r.err = "check"; return r; }
    memcpy(r.site, site, SITELEN);
    r.site[SITELEN] = 0;
    return r;
}

static char *dupstr(const char *s) {
    char *r = malloc(strlen(s) + 1);
    strcpy(r, s);
    return r;
}

static char *build(const char *site, int y, int m, int d, long serial) {
    char dt[16], sr[16], body[64], out[128];
    date_text(dt, y, m, d);
    sprintf(sr, "%0*ld", SERIAL_W, serial);
    sprintf(body, "%s%s%s", site, dt, sr);
    sprintf(out, "%s%s%s%s%s%s%s%c", PREFIX, S1, site, dt, S2, sr, S3, check_char(body));
    return dupstr(out);
}

static char *invalid(const char *why) {
    char out[64];
    sprintf(out, "invalid: %s", why);
    return dupstr(out);
}

char *label(const char *op, const char *text) {
    long max_serial = 1;
    for (int i = 0; i < SERIAL_W; i++) max_serial *= 10;
    max_serial--;
    if (strcmp(op, "validate") == 0) {
        Dec r = decode(text);
        return r.err ? invalid(r.err) : dupstr("valid");
    }
    if (HAS_PARSE && strcmp(op, "parse") == 0) {
        Dec r = decode(text);
        if (r.err) return invalid(r.err);
        char out[128];
        sprintf(out, "site=%s\ndate=%04d-%02d-%02d\nserial=%ld", r.site, r.y, r.m, r.d, r.serial);
        return dupstr(out);
    }
    if (HAS_MAKE && strcmp(op, "make") == 0) {
        size_t n = strlen(text);
        if (n > 100) return invalid("format");
        char buf[128];
        strcpy(buf, text);
        char *f[4];
        int nf = 0;
        char *p = buf;
        while (nf < 4) {
            f[nf++] = p;
            char *sp = strchr(p, ' ');
            if (!sp) break;
            *sp = 0;
            p = sp + 1;
        }
        if (nf != 3 || !f[0][0] || !f[1][0] || !f[2][0]) return invalid("format");
        int found = 0;
        for (int i = 0; i < NSITES; i++)
            if (strcmp(f[0], SITES[i]) == 0) found = 1;
        if (!found) return invalid("site");
        const char *ds = f[1];
        int ok = strlen(ds) == 10 && ds[4] == '-' && ds[7] == '-' && is_digits(ds, 4) && is_digits(ds + 5, 2) && is_digits(ds + 8, 2);
        if (!ok) return invalid("date");
        int y = (int)num(ds, 4), m = (int)num(ds + 5, 2), d = (int)num(ds + 8, 2);
        if (y < 2000 || y > 2099 || m < 1 || m > 12 || d < 1 || d > mdays(y, m)) return invalid("date");
        size_t sl = strlen(f[2]);
        if (!is_digits(f[2], (int)sl) || sl > 9) return invalid("serial");
        long sv = num(f[2], (int)sl);
        if (sv > max_serial || (NOZERO && sv == 0)) return invalid("serial");
        return build(f[0], y, m, d, sv);
    }
    if (HAS_NEXT && strcmp(op, "next") == 0) {
        Dec r = decode(text);
        if (r.err) return invalid(r.err);
        if (r.serial >= max_serial) return invalid("overflow");
        return build(r.site, r.y, r.m, r.d, r.serial + 1);
    }
    return invalid("op");
}
'''


def _b(lang, v):
    if lang == "python":
        return "True" if v else "False"
    if lang == "c":
        return "1" if v else "0"
    return "true" if v else "false"


def sol(lang, p):
    src = {"python": PY, "rust": RS, "go": GO, "c": CC}[lang]
    sites, w = p["sites"], p["weights"]
    return K.subst(
        src, PREFIX=p["prefix"], S1=p["s1"], S2=p["s2"], S3=p["s3"], SITELEN=p["sitelen"], DATEKIND=p["date_kind"],
        SERIALW=p["serial_w"], NOZERO=_b(lang, p["nozero"]), ALPHA=p["alpha"], LENIENT=_b(lang, p["lenient"]),
        HAS_PARSE=_b(lang, p["has_parse"]), HAS_MAKE=_b(lang, p["has_make"]), HAS_NEXT=_b(lang, p["has_next"]),
        SITES_PY="[" + ", ".join(f'"{s}"' for s in sites) + "]",
        SITES_RS="[" + ", ".join(f'"{s}"' for s in sites) + "]",
        SITES_GO="[]string{" + ", ".join(f'"{s}"' for s in sites) + "}",
        SITES_C="{" + ", ".join(f'"{s}"' for s in sites) + "}",
        WEIGHTS_PY="[" + ", ".join(map(str, w)) + "]",
        WEIGHTS_RS="[" + ", ".join(map(str, w)) + "]",
        WEIGHTS_GO="[]int{" + ", ".join(map(str, w)) + "}",
        WEIGHTS_C="{" + ", ".join(map(str, w)) + "}",
    ).lstrip("\n")


def readme(p, api, lang, examples):
    sl = p["sitelen"]
    dk = p["date_kind"]
    dl = {"ymd": 6, "yo": 5, "ymd8": 8}[dk]
    sw = p["serial_w"]
    L = ["# Sample labels", ""]
    L.append("Every tube that enters the freezer farm gets a printed label. The tool in this repository reads and writes those labels. "
             "A label is a short ASCII string made of these parts, in this order, with nothing in between:")
    L.append("")
    parts = [("prefix", f"the fixed text `{p['prefix']}`")]
    if p["s1"]:
        parts.append(("separator 1", f"the text `{p['s1']}`"))
    parts.append(("site", f"{sl} characters, one of the registered site codes: " + ", ".join(f"`{s}`" for s in p["sites"])))
    parts.append(("date", {"ymd": "6 digits `YYMMDD` (year = 2000 + YY)",
                           "yo": "5 digits `YYDDD`: two digits of year (year = 2000 + YY) and the 3-digit day of the year, `001` is 1 January",
                           "ymd8": "8 digits `YYYYMMDD` (the year must be between 2000 and 2099)"}[dk]))
    if p["s2"]:
        parts.append(("separator 2", f"the text `{p['s2']}`"))
    parts.append(("serial", f"{sw} digits, zero padded" + (" (`" + "0" * sw + "` is not a valid serial)" if p["nozero"] else "")))
    if p["s3"]:
        parts.append(("separator 3", f"the text `{p['s3']}`"))
    parts.append(("check", "1 character, the check character (below)"))
    for i, (n, d) in enumerate(parts, 1):
        L.append(f"{i}. **{n}**: {d}")
    L.append("")
    L.append("Dates are Gregorian: a year is a leap year when it is divisible by 4, except years divisible by 100 that are not divisible by 400.")
    L.append("")
    L.append("## Check character")
    L.append("")
    alpha = p["alpha"]
    L.append(f"The alphabet is `{alpha}` ({len(alpha)} symbols); the value of a symbol is its position in this string, starting at 0. "
             f"Take the *body* = site + date + serial, concatenated, without prefix or separators. Number its characters 0, 1, 2, ... "
             f"from the left; character number `i` is multiplied by the weight `W[i mod {len(p['weights'])}]` where `W = {p['weights']}`. "
             f"Sum all products; the check character is the symbol at position `sum mod {len(alpha)}` of the alphabet.")
    L.append("")
    L.append("## Validation")
    L.append("")
    if p["lenient"]:
        L.append("Inputs that are labels (for `validate`" + (", `parse`" if p["has_parse"] else "") + (", `next`" if p["has_next"] else "") +
                 ") are first *normalised*: leading and trailing spaces (only the space character) are removed and ASCII lower-case letters are turned into upper-case. "
                 "After that the label must match exactly. Results never contain the original spelling.")
        L.append("")
    L.append("A label is checked in this order and the **first** failing rule gives the reason:")
    L.append("")
    L.append("1. `length`: the total length is not exactly the length of the layout above.")
    L.append("2. `format`: the prefix or a separator is not the fixed text, or the date part or the serial part contains a character that is not an ASCII digit.")
    L.append("3. `site`: the site is not one of the registered codes.")
    L.append(f"4. `date`: the date is not a real calendar date" + (" (months 1-12, day within the month)" if dk != "yo" else " (day of the year from 1 to 365, or 366 in a leap year)") + ".")
    if p["nozero"]:
        L.append("5. `serial`: the serial is all zeros.")
    L.append(f"{6 if p['nozero'] else 5}. `check`: the check character is wrong.")
    L.append("")
    L.append("## Operations")
    L.append("")
    L.append("`label(op, text)` dispatches on `op` (an exact, lower-case word):")
    L.append("")
    L.append("* `validate`: `text` is a label. Result `valid`, or `invalid: REASON` with the reason code from the list above.")
    if p["has_parse"]:
        L.append("* `parse`: `text` is a label. For a valid label the result is three lines joined by `\\n`: `site=SITE`, `date=YYYY-MM-DD` (the calendar date, zero padded"
                 + (", converted from the day of the year" if dk == "yo" else "") + ") and `serial=N` (the serial as a number, without leading zeros). Otherwise `invalid: REASON`.")
    if p["has_make"]:
        L.append("* `make`: `text` is `SITE YYYY-MM-DD SERIAL`: exactly three non-empty fields separated by single spaces (anything else: `invalid: format`). "
                 "Then, in this order: the site must be registered (`invalid: site`); the date must be written as exactly `YYYY-MM-DD` with ASCII digits, be a real date and have a year "
                 "between 2000 and 2099 (`invalid: date`); the serial must be 1 to 9 ASCII digits (leading zeros are fine) whose value is at most "
                 f"{10 ** sw - 1}" + (" and not 0" if p["nozero"] else "") + " (`invalid: serial`). The result is the full label with the correct check character. "
                 "Input fields are taken literally: no normalisation, so a lower-case site is not registered.")
    if p["has_next"]:
        L.append("* `next`: `text` is a label. A valid label gives the label with the same site and date and the serial increased by one (check character recomputed); "
                 f"if the serial is already {10 ** sw - 1} the result is `invalid: overflow`. An invalid label gives `invalid: REASON`.")
    L.append("* any other `op` (including the operations this tool does not offer): `invalid: op`.")
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    L.append("| op | text | result |")
    L.append("|---|---|---|")
    for (op, text), out in examples:
        L.append(f"| `{op}` | `{text}` | " + "`" + out.replace("\n", " / ") + "` |")
    L.append("")
    L.append("(`/` in the last column stands for a line break in multi-line results.)")
    L.append("")
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


def make_cases(rng, p, ns):
    label = ns["label"]
    cases = []
    sites = p["sites"]

    def mk(site=None, y=None, m=None, d=None, n=None):
        site = site or rng.choice(sites)
        y = y or rng.randrange(2000, 2100)
        m = m or rng.randrange(1, 13)
        d = d or rng.randrange(1, ns["mdays"](y, m) + 1)
        n = n if n is not None else rng.randrange(1, 10 ** p["serial_w"])
        return ns["build"](site, y, m, d, n)

    def add(op, text):
        cases.append((op, text))

    good = [mk() for _ in range(6)]
    add("validate", good[0])
    add("validate", good[1][:-1] + ("0" if good[1][-1] != "0" else "1"))
    if p["has_parse"]:
        add("parse", good[2])
    else:
        add("validate", good[2])
    if p["has_make"]:
        add("make", f"{rng.choice(sites)} {rng.randrange(2000, 2100)}-0{rng.randrange(1, 10)}-1{rng.randrange(0, 9)} {rng.randrange(1, 900)}")
    nex = len(cases)
    for g in good[3:]:
        add("validate", g)
    # all-position corruptions
    base = good[0]
    for i in range(len(base)):
        ch = base[i]
        rep = "X" if ch != "X" else "Y"
        if rng.random() < 0.55:
            add("validate", base[:i] + rep + base[i + 1:])
    add("validate", "")
    add("validate", base + base[-1])
    add("validate", base[:-1])
    add("validate", " " + base)
    add("validate", base + " ")
    add("validate", base.lower())
    add("validate", " " + base.lower() + "  ")
    add("validate", base[:len(p["prefix"])].lower() + base[len(p["prefix"]):])
    add("validate", "x" * len(base))
    # replace prefix / separators
    add("validate", "ZZ" + base[2:] if not base.startswith("ZZ") else "YY" + base[2:])
    sep_positions = []
    q = len(p["prefix"])
    for s in (p["s1"],):
        if s:
            sep_positions.append(q)
        q += len(s)
    # dates
    kinds = p["date_kind"]
    s0 = sites[0]
    def raw(site, date, serial, chk=None):
        body = site + date + serial
        return p["prefix"] + p["s1"] + site + date + p["s2"] + serial + p["s3"] + (chk or ns["check_char"](body))
    sw = p["serial_w"]
    ser = "0" * (sw - 1) + "7"
    if kinds == "ymd":
        for date in ["250230", "251301", "250001", "250132", "240229", "230229", "000229", "000230", "000000", "990131", "251231", "250431"]:
            add("validate", raw(s0, date, ser))
    elif kinds == "ymd8":
        for date in ["20250230", "19991231", "21000101", "20240229", "20230229", "20000229", "21001231", "20251301", "20250001", "20251232", "20250431", "20991231"]:
            add("validate", raw(s0, date, ser))
    else:
        for date in ["24366", "23366", "25000", "25365", "25366", "00366", "00367", "99365", "24060", "23060", "25001", "00000"]:
            add("validate", raw(s0, date, ser))
    add("validate", raw(s0, "2" + "x" * (ns["DATELEN"] - 1), ser, "0"))
    add("validate", raw(s0, "2" * ns["DATELEN"], "x" * sw, "0"))
    add("validate", raw(s0, "2" * ns["DATELEN"], "0" * sw))
    add("validate", raw("QQ" if p["sitelen"] == 2 else "QQQ", "2" * ns["DATELEN"], ser))
    add("validate", raw(sites[0].lower(), "2" * ns["DATELEN"], ser, "0"))
    # serial extremes
    add("validate", mk(n=0) if not p["nozero"] else raw(s0, ns["date_text"](2025, 3, 14), "0" * sw))
    add("validate", mk(n=10 ** sw - 1))
    add("validate", mk(n=1))
    if p["has_parse"]:
        for _ in range(4):
            add("parse", mk())
        add("parse", mk(y=2024, m=2, d=29, n=5))
        add("parse", mk(y=2000, m=12, d=31, n=10 ** sw - 1))
        add("parse", mk(y=2099, m=1, d=1, n=1))
        add("parse", mk(y=2023, m=3, d=1, n=12))
        add("parse", good[0][:-1] + "!")
        add("parse", "")
        add("parse", base.lower())
    if p["has_make"]:
        for _ in range(5):
            y = rng.randrange(2000, 2100)
            m = rng.randrange(1, 13)
            d = rng.randrange(1, ns["mdays"](y, m) + 1)
            add("make", f"{rng.choice(sites)} {y:04d}-{m:02d}-{d:02d} {rng.randrange(1, 10 ** sw)}")
        s = rng.choice(sites)
        mx = 10 ** sw - 1
        for t in [f"{s} 2024-02-29 1", f"{s} 2023-02-29 1", f"{s} 2000-01-01 {mx}", f"{s} 2000-01-01 {mx + 1}", f"{s} 2099-12-31 0007",
                  f"{s} 2099-12-31 0", f"{s} 2100-01-01 5", f"{s} 1999-12-31 5", f"{s} 2025-1-05 5", f"{s} 2025-01-5 5", f"{s} 25-01-05 5",
                  f"{s} 2025/01/05 5", f"{s} 2025-13-05 5", f"{s} 2025-00-05 5", f"{s} 2025-04-31 5", f"{s} 2025-01-00 5",
                  f"{s} 2025-01-05 -5", f"{s} 2025-01-05 5x", f"{s} 2025-01-05 1234567890", f"{s} 2025-01-05 000000007", f"{s} 2025-01-05  5",
                  f"{s} 2025-01-05", f"{s}  2025-01-05 5", f"{s} 2025-01-05 5 6", f" {s} 2025-01-05 5", f"{s} 2025-01-05 5 ", f"{s.lower()} 2025-01-05 5",
                  f"QQ 2025-01-05 5", "", " ", f"{s} 2025-02-30 9", f"{s} 2025-02-30 x", f"{s} 20x5-02-03 x", f"nope 2025-02-30 x", f"{s} 2025-01-05 +5",
                  f"{s} 2025-12-31 {mx}", f"{s} 2025-12-31 1"]:
            add("make", t)
    if p["has_next"]:
        for _ in range(3):
            add("next", mk())
        add("next", mk(n=10 ** sw - 2))
        add("next", mk(n=10 ** sw - 1))
        add("next", mk(n=9))
        add("next", mk(n=10 ** (sw - 1) - 1))
        add("next", mk(y=2024, m=2, d=29, n=3))
        add("next", good[1][:-1] + "~")
        add("next", base[:-2])
        add("next", base.lower())
        add("next", " " + base + " ")
    for op in ["", "Validate", "VALIDATE", "check", "make ", " validate", "parse", "make", "next", "valid", "validate "]:
        add(op, good[0])
    if p["lenient"]:
        for _ in range(3):
            g = mk()
            add("validate", rng.choice(["  ", " ", ""]) + g.lower() + rng.choice(["  ", " ", ""]))
        add("validate", "\t" + base)
        add("validate", " " + base[:5] + " " + base[5:])
    out, seen = [], set()
    for c in cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex


def prompt(rng, p, api, lang):
    where = api.short(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    ops = ["validate"] + [o for o, f in (("parse", p["has_parse"]), ("make", p["has_make"]), ("next", p["has_next"])) if f]
    oplist = ", ".join(f"`{o}`" for o in ops)
    opts = [
        f"The biobank's freezer farm prints labels like `{p['prefix']}...` on every tube, with a home-grown check character. Write the {ln} routine `{fn}` that handles {oplist}. "
        f"README.md describes the label layout, the checksum and the exact result texts; the code goes in {where}. {K.closer(rng)}",
        f"Please implement the label tool from README.md in {ln}: one function, `{fn}`, that dispatches on an operation name ({oplist}). It lives in {where}. "
        f"Be careful with the order of the validation checks; hidden tests probe each rule.",
        f"label checksums, README.md has everything (layout, alphabet, weights, reasons). {ln}, `{fn}`, {where}. operations: {oplist}. {K.closer(rng)}",
        f"We need a small {ln} library for lab sample labels (operations {oplist}). The spec is README.md; the visible tests show the call shape only for a few labels. "
        f"Implement `{fn}` in {where}. {K.closer(rng)}",
    ]
    return rng.choice(opts).strip()


@family("greenfield-labelcode", category="greenfield", lang="mixed", kind="greenfield", n=10,
        summary="lab sample label with an invented weighted check character: validate / parse / make / next, per-instance layout and date format")
def gen(rng, n):
    levels = [1, 2, 2, 3, 3, 3, 2, 3, 1, 3]
    diff = [1, 2, 2, 3, 3, 4, 2, 4, 1, 3]
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level, i)
        api = K.Api(mod="labelcode", fn="label", args=["op", "text"],
                    arg_docs=["the operation name (`validate`" + (", `parse`" if p["has_parse"] else "") + (", `make`" if p["has_make"] else "") + (", `next`" if p["has_next"] else "") + ")",
                              "the label, or the fields of a new label, depending on the operation"],
                    ret_doc="the result text", doc="sample label check character tool")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["label"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=diff[i % len(diff)], slug=f"{i + 1:02d}-{lang}-{p['prefix'].lower()}-{p['date_kind']}",
            oracle=(None if lang == "python" else ns["label"]), tags=["checksum", "dates"],
            notes={"level": level, "date_kind": p["date_kind"], "serial_w": p["serial_w"], "lenient": p["lenient"]},
        )
