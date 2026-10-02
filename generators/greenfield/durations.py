"""Durations in an invented time system: parse compound texts, format canonically, evaluate sums and differences."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

SYSTEMS = [
    ("the harbour watch roster", [("t", 1), ("k", 12), ("w", 144), ("q", 864)]),
    ("the lighthouse log", [("s", 1), ("m", 60), ("h", 3600), ("d", 86400)]),
    ("the ferry timetable", [("p", 1), ("l", 20), ("r", 400)]),
    ("the tide-clock", [("a", 1), ("b", 6), ("c", 36), ("e", 432), ("f", 2592)]),
    ("the kettle timer", [("n", 1), ("g", 45), ("z", 900)]),
    ("the library fines desk", [("u", 1), ("v", 7), ("y", 28), ("x", 364)]),
]
LANG_PLAN = ["c", "go", "ruby", "java", "c", "go", "java", "ruby", "python", "c"]


def params(rng, level, i):
    name, units = SYSTEMS[(i + rng.randrange(2)) % len(SYSTEMS)]
    return {"level": level, "sys": name, "units": units, "format": level >= 2, "calc": level >= 3, "digits": rng.choice([4, 5, 6])}


PY = r'''
UNITS = @UNITS_PY@
HAS_FORMAT = @FORMAT@
HAS_CALC = @CALC@
DIGITS = @DIGITS@
DG = "0123456789"


def size_of(c):
    for u, s in UNITS:
        if u == c:
            return s
    return None


def parse(text):
    """(value, None) or (None, error text)"""
    if text == "":
        return None, "error: empty"
    i = 0
    total = 0
    prev = None
    while i < len(text):
        j = i
        while j < len(text) and text[j] in DG:
            j += 1
        if j == i or j - i > DIGITS:
            return None, "error: number"
        if j >= len(text):
            return None, "error: unit"
        s = size_of(text[j])
        if s is None:
            return None, "error: unit"
        if prev is not None and s >= prev:
            return None, "error: repeat" if s == prev else "error: order"
        total += int(text[i:j]) * s
        prev = s
        i = j + 1
    return total, None


def fmt(n):
    if n == 0:
        return "0" + UNITS[0][0]
    out = ""
    for u, s in reversed(UNITS):
        if n >= s:
            out += "%d%s" % (n // s, u)
            n %= s
    return out


def dur(op, text):
    if op == "parse":
        v, e = parse(text)
        return e if e else str(v)
    if HAS_FORMAT and op == "format":
        if not (1 <= len(text) <= 15 and all(c in DG for c in text) and (text == "0" or text[0] != "0")):
            return "error: number"
        return fmt(int(text))
    if HAS_CALC and op == "calc":
        total = 0
        parts = []
        cur = ""
        ops = []
        for c in text:
            if c in "+-":
                parts.append(cur)
                ops.append(c)
                cur = ""
            else:
                cur += c
        parts.append(cur)
        for k, part in enumerate(parts):
            t = part.strip(" ")
            v, e = parse(t)
            if e:
                return e
            total += v if k == 0 or ops[k - 1] == "+" else -v
        if total < 0:
            return "error: negative"
        return fmt(total)
    return "error: op"
'''

RB = r'''
module Durations
  UNITS = @UNITS_RB@
  HAS_FORMAT = @FORMAT@
  HAS_CALC = @CALC@
  DIGITS = @DIGITS@
  DG = '0123456789'

  def self.size_of(c)
    UNITS.each { |u, s| return s if u == c }
    nil
  end

  def self.parse(text)
    return [nil, 'error: empty'] if text.empty?
    i = 0
    total = 0
    prev = nil
    while i < text.length
      j = i
      j += 1 while j < text.length && DG.include?(text[j])
      return [nil, 'error: number'] if j == i || j - i > DIGITS
      return [nil, 'error: unit'] if j >= text.length
      s = size_of(text[j])
      return [nil, 'error: unit'] if s.nil?
      return [nil, s == prev ? 'error: repeat' : 'error: order'] if !prev.nil? && s >= prev
      total += text[i...j].to_i * s
      prev = s
      i = j + 1
    end
    [total, nil]
  end

  def self.fmt(n)
    return '0' + UNITS[0][0] if n == 0
    out = +''
    UNITS.reverse_each do |u, s|
      if n >= s
        out << "#{n / s}#{u}"
        n %= s
      end
    end
    out
  end

  def self.dur(op, text)
    if op == 'parse'
      v, e = parse(text)
      return e || v.to_s
    end
    if HAS_FORMAT && op == 'format'
      ok = text.length >= 1 && text.length <= 15 && text.each_char.all? { |c| DG.include?(c) } && (text == '0' || text[0] != '0')
      return 'error: number' unless ok
      return fmt(text.to_i)
    end
    if HAS_CALC && op == 'calc'
      parts = []
      ops = []
      cur = +''
      text.each_char do |c|
        if c == '+' || c == '-'
          parts << cur
          ops << c
          cur = +''
        else
          cur << c
        end
      end
      parts << cur
      total = 0
      parts.each_with_index do |part, k|
        v, e = parse(part.gsub(/\A +| +\z/, ''))
        return e if e
        total += (k == 0 || ops[k - 1] == '+') ? v : -v
      end
      return 'error: negative' if total < 0
      return fmt(total)
    end
    'error: op'
  end
end
'''

GO = r'''
package durations

import (
	"fmt"
	"strconv"
	"strings"
)

const (
	hasFormat = @FORMAT@
	hasCalc   = @CALC@
	digitsMax = @DIGITS@
)

type unit struct {
	name byte
	size int64
}

var units = @UNITS_GO@

func sizeOf(c byte) (int64, bool) {
	for _, u := range units {
		if u.name == c {
			return u.size, true
		}
	}
	return 0, false
}

func isDig(c byte) bool { return c >= '0' && c <= '9' }

func parse(text string) (int64, string) {
	if text == "" {
		return 0, "error: empty"
	}
	i := 0
	var total, prev int64
	for i < len(text) {
		j := i
		for j < len(text) && isDig(text[j]) {
			j++
		}
		if j == i || j-i > digitsMax {
			return 0, "error: number"
		}
		if j >= len(text) {
			return 0, "error: unit"
		}
		s, ok := sizeOf(text[j])
		if !ok {
			return 0, "error: unit"
		}
		if prev != 0 && s >= prev {
			if s == prev {
				return 0, "error: repeat"
			}
			return 0, "error: order"
		}
		n, _ := strconv.ParseInt(text[i:j], 10, 64)
		total += n * s
		prev = s
		i = j + 1
	}
	return total, ""
}

func format(n int64) string {
	if n == 0 {
		return "0" + string(units[0].name)
	}
	var sb strings.Builder
	for k := len(units) - 1; k >= 0; k-- {
		u := units[k]
		if n >= u.size {
			sb.WriteString(fmt.Sprintf("%d%c", n/u.size, u.name))
			n %= u.size
		}
	}
	return sb.String()
}

// Dur parses, formats or evaluates durations.
func Dur(op, text string) string {
	switch {
	case op == "parse":
		v, e := parse(text)
		if e != "" {
			return e
		}
		return strconv.FormatInt(v, 10)
	case hasFormat && op == "format":
		ok := len(text) >= 1 && len(text) <= 15 && (text == "0" || text[0] != '0')
		for i := 0; i < len(text); i++ {
			if !isDig(text[i]) {
				ok = false
			}
		}
		if !ok {
			return "error: number"
		}
		n, _ := strconv.ParseInt(text, 10, 64)
		return format(n)
	case hasCalc && op == "calc":
		var parts []string
		var ops []byte
		cur := ""
		for i := 0; i < len(text); i++ {
			if text[i] == '+' || text[i] == '-' {
				parts = append(parts, cur)
				ops = append(ops, text[i])
				cur = ""
			} else {
				cur += string(text[i])
			}
		}
		parts = append(parts, cur)
		var total int64
		for k, part := range parts {
			v, e := parse(strings.Trim(part, " "))
			if e != "" {
				return e
			}
			if k == 0 || ops[k-1] == '+' {
				total += v
			} else {
				total -= v
			}
		}
		if total < 0 {
			return "error: negative"
		}
		return format(total)
	}
	return "error: op"
}
'''

JV = r'''
import java.util.ArrayList;
import java.util.List;

public class Durations {
    static final boolean HAS_FORMAT = @FORMAT@;
    static final boolean HAS_CALC = @CALC@;
    static final int DIGITS = @DIGITS@;
    static final Object[][] UNITS = @UNITS_JAVA@;

    static long sizeOf(char c) {
        for (Object[] u : UNITS) if ((Character) u[0] == c) return (Long) u[1];
        return -1;
    }

    static boolean dig(char c) { return c >= '0' && c <= '9'; }

    // returns {value, error}
    static Object[] parse(String text) {
        if (text.isEmpty()) return new Object[] { null, "error: empty" };
        int i = 0;
        long total = 0, prev = -1;
        while (i < text.length()) {
            int j = i;
            while (j < text.length() && dig(text.charAt(j))) j++;
            if (j == i || j - i > DIGITS) return new Object[] { null, "error: number" };
            if (j >= text.length()) return new Object[] { null, "error: unit" };
            long s = sizeOf(text.charAt(j));
            if (s < 0) return new Object[] { null, "error: unit" };
            if (prev >= 0 && s >= prev) return new Object[] { null, s == prev ? "error: repeat" : "error: order" };
            total += Long.parseLong(text.substring(i, j)) * s;
            prev = s;
            i = j + 1;
        }
        return new Object[] { total, null };
    }

    static String fmt(long n) {
        if (n == 0) return "0" + UNITS[0][0];
        StringBuilder sb = new StringBuilder();
        for (int k = UNITS.length - 1; k >= 0; k--) {
            long s = (Long) UNITS[k][1];
            if (n >= s) {
                sb.append(n / s).append((Character) UNITS[k][0]);
                n %= s;
            }
        }
        return sb.toString();
    }

    static String trimSpaces(String s) {
        int a = 0, b = s.length();
        while (a < b && s.charAt(a) == ' ') a++;
        while (b > a && s.charAt(b - 1) == ' ') b--;
        return s.substring(a, b);
    }

    public static String dur(String op, String text) {
        if (op.equals("parse")) {
            Object[] r = parse(text);
            return r[1] != null ? (String) r[1] : String.valueOf((Long) r[0]);
        }
        if (HAS_FORMAT && op.equals("format")) {
            boolean ok = text.length() >= 1 && text.length() <= 15 && (text.equals("0") || text.charAt(0) != '0');
            for (char c : text.toCharArray()) if (!dig(c)) ok = false;
            if (!ok) return "error: number";
            return fmt(Long.parseLong(text));
        }
        if (HAS_CALC && op.equals("calc")) {
            List<String> parts = new ArrayList<>();
            List<Character> ops = new ArrayList<>();
            StringBuilder cur = new StringBuilder();
            for (char c : text.toCharArray()) {
                if (c == '+' || c == '-') {
                    parts.add(cur.toString());
                    ops.add(c);
                    cur = new StringBuilder();
                } else cur.append(c);
            }
            parts.add(cur.toString());
            long total = 0;
            for (int k = 0; k < parts.size(); k++) {
                Object[] r = parse(trimSpaces(parts.get(k)));
                if (r[1] != null) return (String) r[1];
                long v = (Long) r[0];
                total += (k == 0 || ops.get(k - 1) == '+') ? v : -v;
            }
            if (total < 0) return "error: negative";
            return fmt(total);
        }
        return "error: op";
    }
}
'''

CC = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "durations.h"

#define HAS_FORMAT @FORMAT@
#define HAS_CALC @CALC@
#define DIGITS @DIGITS@

typedef struct { char name; long long size; } Unit;
static const Unit UNITS[] = @UNITS_C@;
#define NU ((int)(sizeof UNITS / sizeof UNITS[0]))

static char *dupstr(const char *s) {
    char *r = malloc(strlen(s) + 1);
    strcpy(r, s);
    return r;
}

static int dig(char c) { return c >= '0' && c <= '9'; }

static long long size_of(char c) {
    for (int i = 0; i < NU; i++) if (UNITS[i].name == c) return UNITS[i].size;
    return -1;
}

/* returns 0 and the value, or a pointer to the error text via err */
static const char *parse(const char *text, long long *out) {
    if (!*text) return "error: empty";
    size_t n = strlen(text), i = 0;
    long long total = 0, prev = -1;
    while (i < n) {
        size_t j = i;
        while (j < n && dig(text[j])) j++;
        if (j == i || j - i > DIGITS) return "error: number";
        if (j >= n) return "error: unit";
        long long s = size_of(text[j]);
        if (s < 0) return "error: unit";
        if (prev >= 0 && s >= prev) return s == prev ? "error: repeat" : "error: order";
        long long v = 0;
        for (size_t k = i; k < j; k++) v = v * 10 + (text[k] - '0');
        total += v * s;
        prev = s;
        i = j + 1;
    }
    *out = total;
    return NULL;
}

static char *fmt(long long n) {
    char buf[256];
    if (n == 0) { sprintf(buf, "0%c", UNITS[0].name); return dupstr(buf); }
    buf[0] = 0;
    for (int k = NU - 1; k >= 0; k--) {
        if (n >= UNITS[k].size) {
            sprintf(buf + strlen(buf), "%lld%c", n / UNITS[k].size, UNITS[k].name);
            n %= UNITS[k].size;
        }
    }
    return dupstr(buf);
}

char *dur(const char *op, const char *text) {
    if (strcmp(op, "parse") == 0) {
        long long v;
        const char *e = parse(text, &v);
        if (e) return dupstr(e);
        char buf[64];
        sprintf(buf, "%lld", v);
        return dupstr(buf);
    }
    if (HAS_FORMAT && strcmp(op, "format") == 0) {
        size_t n = strlen(text);
        int ok = n >= 1 && n <= 15 && (strcmp(text, "0") == 0 || text[0] != '0');
        for (size_t i = 0; i < n; i++) if (!dig(text[i])) ok = 0;
        if (!ok) return dupstr("error: number");
        return fmt(atoll(text));
    }
    if (HAS_CALC && strcmp(op, "calc") == 0) {
        size_t n = strlen(text);
        char *copy = dupstr(text);
        long long total = 0;
        size_t start = 0;
        char pending = '+';
        int first = 1;
        for (size_t i = 0; i <= n; i++) {
            if (i == n || copy[i] == '+' || copy[i] == '-') {
                char saved = copy[i];
                copy[i] = 0;
                char *part = copy + start;
                while (*part == ' ') part++;
                size_t pl = strlen(part);
                while (pl > 0 && part[pl - 1] == ' ') part[--pl] = 0;
                long long v;
                const char *e = parse(part, &v);
                if (e) { free(copy); return dupstr(e); }
                if (first || pending == '+') total += v; else total -= v;
                first = 0;
                pending = saved;
                start = i + 1;
            }
        }
        free(copy);
        if (total < 0) return dupstr("error: negative");
        return fmt(total);
    }
    return dupstr("error: op");
}
'''


def sol(lang, p):
    u = p["units"]
    src = {"python": PY, "ruby": RB, "go": GO, "java": JV, "c": CC}[lang]
    b = lambda v: ("True" if v else "False") if lang == "python" else ("1" if v else "0") if lang == "c" else ("true" if v else "false")  # noqa: E731
    return K.subst(
        src, FORMAT=b(p["format"]), CALC=b(p["calc"]), DIGITS=p["digits"],
        UNITS_PY="[" + ", ".join(f'("{n}", {s})' for n, s in u) + "]", UNITS_RB="[" + ", ".join(f"['{n}', {s}]" for n, s in u) + "]",
        UNITS_GO="[]unit{" + ", ".join(f"{{'{n}', {s}}}" for n, s in u) + "}", UNITS_JAVA="{" + ", ".join(f"{{'{n}', {s}L}}" for n, s in u) + "}",
        UNITS_C="{" + ", ".join(f"{{'{n}', {s}LL}}" for n, s in u) + "}",
    ).lstrip("\n")


def readme(p, api, lang, examples):
    u = p["units"]
    ex = "".join(f"3{n}" for n, _ in reversed(u[:2])) if len(u) >= 2 else f"3{u[0][0]}"
    L = [f"# Durations for {p['sys']}", ""]
    L.append(f"{p['sys'].capitalize()} counts time in its own units. `dur(op, text)` reads and writes durations in that system. A duration is a whole number of the smallest unit (`{u[0][0]}`).")
    L.append("")
    L.append("| unit | size |")
    L.append("|---|---|")
    for n, s in u:
        L.append(f"| `{n}` | {s} ({'the base unit' if s == 1 else f'{s} x `{u[0][0]}`'}) |")
    L.append("")
    L.append("## Compound texts")
    L.append("")
    L.append(f"A compound text is one or more *parts* written one after the other, each part being a count (one to {p['digits']} ASCII digits, leading zeros allowed) immediately followed by a unit letter from the table: `{ex}`. "
             "Units must be written from the **largest to the smallest**, each at most once. No blanks, no signs, nothing else. The value is the sum of `count x size`.")
    L.append("")
    L.append("## Operations")
    L.append("")
    L.append("**`parse`**: `text` is a compound text; the result is its value as a decimal number. Errors are reported in this way, scanning from the left and stopping at the first problem:")
    L.append("")
    L.append("* `error: empty`: the text is empty;")
    L.append(f"* `error: number`: where a count must start there is no digit (or a non-digit, or a sign), or the count has more than {p['digits']} digits;")
    L.append("* `error: unit`: the count is not followed by a unit letter of the table (end of text included);")
    L.append("* `error: repeat`: a unit that is the same as the previous part's; `error: order`: a unit larger than the previous part's.")
    L.append("")
    if p["format"]:
        L.append("**`format`**: `text` is a non-negative whole number in decimal (1 to 15 ASCII digits, no leading zeros except the number `0` itself, otherwise `error: number`). The result is its *canonical compound text*: go through the units from largest to smallest and, for every unit whose size does not exceed what is left, "
                 f"write `count` and the letter (count = what is left divided by the size, rounded down), then keep the remainder. Zero parts are left out. The number 0 is written `0{u[0][0]}`.")
        L.append("")
    if p["calc"]:
        L.append("**`calc`**: `text` is a sum of compound texts joined by `+` and `-`, for example `" + f"2{u[1][0]}5{u[0][0]} + 3{u[0][0]} - 1{u[0][0]}" + "`. Blanks (spaces only) are allowed around each compound text and around the operators. There is no leading sign: the first term is a compound text. "
                 "Every term is parsed exactly as in `parse` (blanks stripped first); the first error, from left to right, is the result. If the total is negative the result is `error: negative`; otherwise it is the total in canonical compound form (as in `format`). "
                 "Note that an empty term (`1" + u[0][0] + " + `, `+ 1" + u[0][0] + "`, `1" + u[0][0] + "++1" + u[0][0] + "`) is `error: empty`.")
        L.append("")
    L.append("Any other `op` gives `error: op`.")
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    L.append("| op | text | result |")
    L.append("|---|---|---|")
    for (op, t), out in examples:
        L.append(f"| `{op}` | `{t}` | `{out}` |")
    L.append("")
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


def make_cases(rng, p, ns):
    u = p["units"]
    names = [n for n, _ in u]
    dur = ns["dur"]
    cases = []

    def add(op, t):
        cases.append((op, t))

    def comp(maxparts=None):
        k = rng.randrange(1, min(len(u), maxparts or len(u)) + 1)
        chosen = sorted(rng.sample(range(len(u)), k), reverse=True)
        return "".join(f"{rng.randrange(0, 40) if rng.random() < 0.8 else rng.randrange(0, 999)}{names[i]}" for i in chosen)

    add("parse", comp())
    add("parse", comp())
    if p["format"]:
        add("format", str(rng.randrange(1, 5000)))
    else:
        add("parse", f"{rng.randrange(1, 9)}{names[0]}")
    nex = len(cases)
    for _ in range(12):
        add("parse", comp())
    d = p["digits"]
    for t in [f"0{names[0]}", f"1{names[0]}", f"00{names[0]}", "9" * d + names[0], "9" * (d + 1) + names[0], "0" * d + names[-1], "0" * (d + 1) + names[-1], "".join(f"1{n}" for n in reversed(names)), "".join(f"0{n}" for n in reversed(names)),
              "".join(f"{p['digits']}{n}" for n in reversed(names)), f"1{names[-1]}1{names[0]}", f"1{names[-1]}0{names[0]}", f"0{names[-1]}1{names[0]}"]:
        add("parse", t)
    for t in ["", "5", "x", "5x", "5 " + names[0], " 5" + names[0], "5" + names[0] + " ", names[0], names[0] + "5", "-5" + names[0], "+5" + names[0], "5.5" + names[0], "5" + names[0].upper(), "5" + names[0] + "5", "5" + names[0] + "x", "5" + names[0] + "5x",
              f"1{names[0]}1{names[0]}", f"1{names[-1]}1{names[-1]}", f"1{names[0]}1{names[-1]}", f"1{names[0]}1{names[1]}", f"2{names[1]}1{names[-1]}", f"1{names[-1]}2{names[-1]}1{names[0]}", f"1{names[-1]}1{names[0]}1{names[-1]}", f"1{names[-1]}x", f"x1{names[-1]}",
              f"1{names[-1]}1", f"1{names[-1]}1{names[0]}1", f"1{names[-1]}1{names[0]}z", "٣" if False else "3", "1" + names[0] + "\n", "\t1" + names[0]]:
        add("parse", t)
    if len(u) >= 3:
        add("parse", f"1{names[2]}1{names[1]}1{names[0]}")
        add("parse", f"1{names[1]}1{names[2]}")
        add("parse", f"1{names[2]}1{names[0]}")
    if p["format"]:
        for n in [0, 1, 2, 7, 11, 12, 13, 23, 24, 59, 60, 61, 100, 143, 144, 145, 863, 864, 865, 1000, 3599, 3600, 3601, 86399, 86400, 86401, 123456, 999999, 1000000, 123456789, 99999999999, 999999999999999]:
            add("format", str(n))
        for s_, _ in u:
            for _, sz in u:
                add("format", str(sz))
                add("format", str(sz - 1))
                break
        for sz in [s for _, s in u]:
            add("format", str(sz * 2))
            add("format", str(sz * 3 - 1))
            add("format", str(sz * 7 + 1))
        for t in ["", "-1", "+1", "01", "00", "1.5", "1e3", " 1", "1 ", "abc", "1000000000000000", "9999999999999999", "0x10", "1_000", "١"] :
            if all(ord(c) < 128 for c in t):
                add("format", t)
        for _ in range(8):
            add("format", str(rng.randrange(0, 10 ** rng.randrange(1, 9))))
        for _ in range(8):
            c = comp()
            v = dur("parse", c)
            if not v.startswith("error"):
                add("format", v)
    if p["calc"]:
        a, b, c = names[0], names[1], names[-1]
        for t in [f"1{b}", f"1{b} + 1{a}", f"1{b} - 1{a}", f"1{a} - 1{a}", f"1{a} - 2{a}", f"1{b} - 1{b}1{a}", f"2{b} - 1{b} - 1{b}", f"2{b} - 1{b} - 1{b} - 1{a}", f"1{a}+1{a}+1{a}", f"1{a} + 1{a} - 1{a} + 1{a}", f"  1{b}  +  1{a}  ", f"1{b}+1{a}", f"1{b} +1{a}", f"1{b}+ 1{a}",
                  f"{c.join(['9', ''])}" if False else f"3{c} + 1{a}", f"1{c} - 1{a}", f"1{c} - 1{b}", f"1{c}1{a} + 1{c}1{a}", f"0{a} + 0{a}", f"0{a} - 0{a}", f"1{b} - 1{b}", f"5{b}3{a} + 7{b}9{a} - 2{b}", f"999{a} + 999{a}"]:
            add("calc", t)
        for t in ["", " ", "+", "-", f"+1{a}", f"-1{a}", f"1{a} +", f"1{a} -", f"1{a} + + 1{a}", f"1{a}++1{a}", f"1{a} - - 1{a}", f"1{a} + x", f"1{a} + 1", f"1{a} + 1x", f"1{a} 1{a}", f"1{a} + 1{a} 1{a}", f"1{a} * 2", f"(1{a})", f"1{a}\t+ 1{a}",
                  f"1{b}1{c}", f"1{a}1{b}", f"1{b}1{b}", f"1{a} + 1{b}1{c}", f"x + 1{a}", f"1{a} + x + 1{a}", f"1{b}1{c} + x", f"1 {a}", f"1{a} + 1 {a}", f"{'9' * (d + 1)}{a}", f"1{a} + {'9' * (d + 1)}{a}", f"{'9' * (d + 1)}{a} + x"]:
            add("calc", t)
        for _ in range(10):
            terms = [comp() for _ in range(rng.randrange(2, 5))]
            expr = terms[0]
            for tt in terms[1:]:
                expr += rng.choice([" + ", " - ", "+", "-", " +", "- "]) + tt
            add("calc", expr)
    for op in ["", "Parse", "PARSE", "parse ", "calc" if not p["calc"] else "calculate", "format" if not p["format"] else "fmt", "p"]:
        add(op, f"1{names[0]}")
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
    ops = ["`parse`"] + (["`format`"] if p["format"] else []) + (["`calc`"] if p["calc"] else [])
    ol = ", ".join(ops)
    opts = [
        f"{p['sys'].capitalize()} has its own units of time. Please write `{fn}(op, text)` in {ln} ({where}) to {'parse and print' if p['format'] else 'parse'} durations ({ol}). README.md has the unit table, the grammar and the error texts. {K.closer(rng)}",
        f"Small utility, {ln}: implement `{fn}` in {where} as specified in README.md (operations {ol}). Pay attention to which error is reported first.",
        f"duration helper for {p['sys']} ({ln}, `{fn}`, {where}). see README.md for the units and the operations ({ol}). {K.closer(rng)}",
        f"Could you build the duration tool from README.md? {ln}, entry point `{fn}` in {where}. Operations: {ol}. Hidden checks include zero-padded counts, over-long counts and out-of-order units.",
    ]
    return rng.choice(opts).strip()


@family("greenfield-durations", category="greenfield", lang="mixed", kind="greenfield", n=10,
        summary="durations in an invented unit system: parse with ordered errors, canonical formatting, sums and differences")
def gen(rng, n):
    levels = [1, 1, 1, 2, 2, 2, 3, 3, 1, 3]
    diffs = [1, 1, 1, 2, 2, 2, 3, 3, 1, 3]
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level, i)
        api = K.Api(mod="durations", fn="dur", args=["op", "text"], arg_docs=["the operation: `parse`" + (", `format`" if p["format"] else "") + (", `calc`" if p["calc"] else ""), "the duration text, the number, or the expression, depending on the operation"],
                    ret_doc="the result text", doc="durations in an invented time system")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["dur"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=diffs[i % len(diffs)], slug=f"{i + 1:02d}-{lang}-{''.join(n for n, _ in p['units'])}-l{level}", oracle=(None if lang == "python" else ns["dur"]),
            tags=["parser", "units"], notes={"level": level, "units": p["units"], "digits": p["digits"]},
        )
