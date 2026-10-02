"""Small port libraries (difficulty 1): bin labels, rounding modes, ticket codes, flag sets. Each has one or two traps (bijective numbering, floor versus truncating division, safe integers, 8-bit masks)."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

# ======================================================================================================================
# bin-labels: warehouse bin labels with spreadsheet-style aisle names
# ======================================================================================================================

BL_SPEC = dd('''
    Warehouse bins are labelled `<AISLE>-<SHELF>-<LEVEL>`, for example `C-07-3`.

    * **Aisle names** count like spreadsheet columns (bijective base 26: there is no zero digit): index 0 is `A`, 25 is `Z`, 26 is `AA`,
      27 is `AB`, 51 is `AZ`, 52 is `BA`, 701 is `ZZ`, 702 is `AAA`. Only capital ASCII letters, at most four of them (the last index is 475253, `ZZZZ`).
    * A **shelf** is an integer from 1 to 9999 written with at least two digits (`07`, `10`, `123`, `9999`); a **level** is a single digit from 1 to 9.
    * `aisle_name(n)` is the name of index `n`; `n` outside 0..475253 is an error. `aisle_index(name)` is the inverse; an empty name, more than four letters or any character outside `A`..`Z` is an error.
    * `fmt_bin(aisle, shelf, level)` is the label for an aisle index, a shelf and a level; anything out of range is an error.
    * `parse_bin(text)` returns `[aisle index, shelf, level]` and accepts exactly the text `fmt_bin` produces: no spaces or signs, ASCII digits only, the shelf with exactly the canonical padding
      (`7` and `007` are invalid, `07` and `100` are fine, `00` is invalid), a single level digit 1..9. Everything else is an error.
    * Walking order inside a warehouse with `shelves` shelves per aisle: levels 1 to 9 first, then the next shelf (level back to 1), after shelf `shelves` the next aisle starts at shelf 1, level 1.
      `bin_number(text, shelves)` is the 0-based position in that order, `((aisle * shelves) + (shelf - 1)) * 9 + (level - 1)`.
      `next_bin(text, shelves)` is the label of the following position. `shelves` outside 1..9999, an invalid label, a shelf larger than `shelves`, or a next aisle beyond `ZZZZ` is an error.
''')

BL_FNS = [
    Fn("aisle_name", [("n", "int")], "str", err=True),
    Fn("aisle_index", [("name", "str")], "int", err=True),
    Fn("fmt_bin", [("aisle", "int"), ("shelf", "int"), ("level", "int")], "str", err=True),
    Fn("parse_bin", [("text", "str")], "list<int>", err=True),
    Fn("bin_number", [("text", "str"), ("shelves", "int")], "int", err=True),
    Fn("next_bin", [("text", "str"), ("shelves", "int")], "str", err=True),
]

BL_PY = dd(r'''
import re

_MAX_AISLE = 475253
_BIN = re.compile(r"([A-Z]{1,4})-([0-9]{2,4})-([1-9])")


def aisle_name(n):
    if n < 0 or n > _MAX_AISLE:
        raise ValueError("aisle out of range")
    out = ""
    v = n + 1
    while v > 0:
        v, r = divmod(v - 1, 26)
        out = chr(65 + r) + out
    return out


def aisle_index(name):
    if not re.fullmatch(r"[A-Z]{1,4}", name):
        raise ValueError("bad aisle name")
    n = 0
    for ch in name:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def fmt_bin(aisle, shelf, level):
    name = aisle_name(aisle)
    if not (1 <= shelf <= 9999 and 1 <= level <= 9):
        raise ValueError("shelf or level out of range")
    return "%s-%02d-%d" % (name, shelf, level)


def parse_bin(text):
    m = _BIN.fullmatch(text)
    if not m:
        raise ValueError("bad bin label")
    s = m.group(2)
    if len(s) > 2 and s[0] == "0":
        raise ValueError("bad shelf padding")
    shelf = int(s)
    if shelf < 1:
        raise ValueError("shelf out of range")
    return [aisle_index(m.group(1)), shelf, int(m.group(3))]


def _checked(text, shelves):
    if not (1 <= shelves <= 9999):
        raise ValueError("bad shelves")
    aisle, shelf, level = parse_bin(text)
    if shelf > shelves:
        raise ValueError("shelf beyond the aisle")
    return aisle, shelf, level


def bin_number(text, shelves):
    aisle, shelf, level = _checked(text, shelves)
    return (aisle * shelves + (shelf - 1)) * 9 + (level - 1)


def next_bin(text, shelves):
    aisle, shelf, level = _checked(text, shelves)
    if level < 9:
        level += 1
    elif shelf < shelves:
        shelf, level = shelf + 1, 1
    else:
        aisle, shelf, level = aisle + 1, 1, 1
    return fmt_bin(aisle, shelf, level)
''')

BL_GO = dd(r'''
package binlabels

import (
	"errors"
	"fmt"
	"strings"
)

const maxAisle = 475253

func AisleName(n int64) (string, error) {
	if n < 0 || n > maxAisle {
		return "", errors.New("aisle out of range")
	}
	var buf []byte
	v := n + 1
	for v > 0 {
		r := (v - 1) % 26
		buf = append([]byte{byte('A' + r)}, buf...)
		v = (v - 1) / 26
	}
	return string(buf), nil
}

func AisleIndex(name string) (int64, error) {
	if len(name) < 1 || len(name) > 4 {
		return 0, errors.New("bad aisle name")
	}
	var n int64
	for i := 0; i < len(name); i++ {
		c := name[i]
		if c < 'A' || c > 'Z' {
			return 0, errors.New("bad aisle name")
		}
		n = n*26 + int64(c-'A'+1)
	}
	return n - 1, nil
}

func FmtBin(aisle, shelf, level int64) (string, error) {
	name, err := AisleName(aisle)
	if err != nil {
		return "", err
	}
	if shelf < 1 || shelf > 9999 || level < 1 || level > 9 {
		return "", errors.New("shelf or level out of range")
	}
	return fmt.Sprintf("%s-%02d-%d", name, shelf, level), nil
}

func ParseBin(text string) ([]int64, error) {
	bad := errors.New("bad bin label")
	parts := strings.Split(text, "-")
	if len(parts) != 3 {
		return nil, bad
	}
	aisle, err := AisleIndex(parts[0])
	if err != nil {
		return nil, bad
	}
	s := parts[1]
	if len(s) < 2 || len(s) > 4 || (len(s) > 2 && s[0] == '0') {
		return nil, bad
	}
	var shelf int64
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return nil, bad
		}
		shelf = shelf*10 + int64(s[i]-'0')
	}
	if shelf < 1 {
		return nil, bad
	}
	l := parts[2]
	if len(l) != 1 || l[0] < '1' || l[0] > '9' {
		return nil, bad
	}
	return []int64{aisle, shelf, int64(l[0] - '0')}, nil
}

func checked(text string, shelves int64) (int64, int64, int64, error) {
	if shelves < 1 || shelves > 9999 {
		return 0, 0, 0, errors.New("bad shelves")
	}
	p, err := ParseBin(text)
	if err != nil {
		return 0, 0, 0, err
	}
	if p[1] > shelves {
		return 0, 0, 0, errors.New("shelf beyond the aisle")
	}
	return p[0], p[1], p[2], nil
}

func BinNumber(text string, shelves int64) (int64, error) {
	aisle, shelf, level, err := checked(text, shelves)
	if err != nil {
		return 0, err
	}
	return (aisle*shelves+(shelf-1))*9 + (level - 1), nil
}

func NextBin(text string, shelves int64) (string, error) {
	aisle, shelf, level, err := checked(text, shelves)
	if err != nil {
		return "", err
	}
	if level < 9 {
		level++
	} else if shelf < shelves {
		shelf, level = shelf+1, 1
	} else {
		aisle, shelf, level = aisle+1, 1, 1
	}
	return FmtBin(aisle, shelf, level)
}
''')


def bl_cases(rng):
    out = [
        ("aisle_name", [0]), ("aisle_name", [25]), ("aisle_name", [26]), ("aisle_name", [701]), ("aisle_name", [702]),
        ("fmt_bin", [2, 7, 3]), ("parse_bin", ["C-07-3"]), ("next_bin", ["C-07-9", 12]), ("bin_number", ["B-02-4", 10]), ("aisle_index", ["AZ"]),
    ]
    for n in [27, 51, 52, 675, 676, 18277, 18278, 475252, 475253, 12345, 100000, -1, 475254, 10**9]:
        out.append(("aisle_name", [n]))
    for _ in range(20):
        out.append(("aisle_name", [rng.randint(0, 475253)]))
    names = ["A", "Z", "AA", "AZ", "BA", "ZZ", "AAA", "ZZZ", "AAAA", "ZZZZ", "ABCD", "", "AAAAA", "a", "Aa", "A1", "A ", " A", "A\n", "\u00c4", "\u0391", "A-B", "\uff21", "AB\u00c4"]
    for s in names:
        out.append(("aisle_index", [s]))
    for _ in range(15):
        n = rng.randint(0, 475253)
        out.append(("aisle_index", [_name(n)]))
    for aisle, shelf, level in [(0, 1, 1), (0, 9999, 9), (3, 10, 5), (26, 100, 2), (475253, 1, 1), (-1, 1, 1), (475254, 1, 1), (0, 0, 1), (0, 10000, 1), (0, 1, 0), (0, 1, 10), (5, -3, 4), (1, 5, -1)]:
        out.append(("fmt_bin", [aisle, shelf, level]))
    for _ in range(15):
        out.append(("fmt_bin", [rng.randint(0, 3000), rng.randint(1, 9999), rng.randint(1, 9)]))
    texts = ["A-01-1", "ZZZZ-9999-9", "C-07-3", "C-7-3", "C-007-3", "C-0007-3", "C-00-3", "C-0100-3", "C-100-3", "C-10000-3", "C-07-0", "C-07-10", "C-07", "C-07-3-1", "c-07-3", "C-07-3 ", " C-07-3",
             "C-07-3\n", "C--07-3", "C-+7-3", "C-0\u0667-3", "C-07-\u0663", "-07-3", "C-07-", "AAAAA-01-1", "C\u201307\u20133", "C-\uff10\uff17-3", "C-ab-3", "", "---"]
    for t in texts:
        out.append(("parse_bin", [t]))
    for _ in range(12):
        out.append(("parse_bin", [_fmt(rng.randint(0, 800), rng.randint(1, 9999), rng.randint(1, 9))]))
    for t, sh in [("A-01-1", 5), ("A-01-9", 5), ("A-05-9", 5), ("A-05-8", 5), ("B-01-1", 5), ("ZZZZ-05-9", 5), ("ZZZZ-05-8", 5), ("A-06-1", 5), ("A-01-1", 0), ("A-01-1", 10000), ("A-01-1", 1),
                  ("A-01-9", 1), ("bad", 5), ("Z-99-9", 99), ("Z-99-9", 100), ("AZ-100-9", 100), ("A-9999-9", 9999), ("A-07-9", 12)]:
        out.append(("next_bin", [t, sh]))
        out.append(("bin_number", [t, sh]))
    for _ in range(25):
        sh = rng.choice([1, 2, 5, 12, 40, 100, 9999])
        t = _fmt(rng.randint(0, 600), rng.randint(1, sh), rng.randint(1, 9))
        out.append(("next_bin", [t, sh]))
        out.append(("bin_number", [t, sh]))
    return out


def _name(n):
    s, v = "", n + 1
    while v > 0:
        v, r = divmod(v - 1, 26)
        s = chr(65 + r) + s
    return s


def _fmt(aisle, shelf, level):
    return "%s-%02d-%d" % (_name(aisle), shelf, level)


BL = PortLib(
    slug="bin-labels",
    title="warehouse bin labels",
    blurb="A warehouse system labels bins like C-07-3 with spreadsheet-style aisle names and has to count, parse and step through them exactly.",
    spec=BL_SPEC,
    fns=BL_FNS,
    impls={"python": {"bin_labels.py": BL_PY}, "go": {"binlabels.go": BL_GO}},
    cases=bl_cases,
    difficulty=1,
    n_examples=10,
    pairs=[("python", "go", "full"), ("go", "python", "full"), ("python", "go", "stub"), ("go", "python", "stub")],
    traps=["bijective base-26 (no zero digit)", "strict ASCII-only digit parsing", "canonical padding"],
    tags=["strict-parsing", "bijective-numbering"],
)
register_port(BL, __name__)

# ======================================================================================================================
# div-modes: integer division with eight rounding rules
# ======================================================================================================================

DM_SPEC = dd('''
    Quantities and money are divided by integers in many places and every call site has its own rounding rule. A `mode` is one of eight words:

    | mode | result |
    |---|---|
    | `floor` | toward minus infinity |
    | `ceil` | toward plus infinity |
    | `trunc` | toward zero |
    | `away` | away from zero |
    | `half-up` | nearest integer, an exact tie goes toward plus infinity |
    | `half-down` | nearest integer, an exact tie goes toward minus infinity |
    | `half-even` | nearest integer, an exact tie goes to the even neighbour |
    | `half-away` | nearest integer, an exact tie goes away from zero |

    * `div_round(n, d, mode)` is the exact quotient `n / d` rounded by `mode`. The divisor may be negative (`7 / -2` is `-3.5`). A zero divisor or an unknown mode (checked even when the division is exact) is an error.
      Examples: `(7, 2, half-even)` is 4, `(5, 2, half-even)` is 2, `(-7, 2, half-up)` is -3, `(-7, 2, half-away)` is -4, `(7, -2, floor)` is -4, `(-7, -2, ceil)` is 4.
    * `mul_div(a, b, c, mode)` is `a * b / c` rounded by `mode`, with the product computed exactly (the vectors keep `|a|` and `|b|` below 2^31, so it fits 64 bits). Same errors as `div_round`.
    * `split_even(total, parts)` splits `total` into `parts` integers that add up to `total` and differ by at most one: every entry is `floor(total / parts)` and the first `total - parts * floor(total / parts)` entries are one larger
      (`(10, 3)` gives `[4, 3, 3]`, `(-7, 3)` gives `[-2, -2, -3]`). `parts < 1` is an error.
    * `clamp_div(n, d, lo, hi, mode)` is `div_round(n, d, mode)` limited to `lo..hi`; `lo > hi` is an error (as well as the `div_round` errors).
    * `bucket(n, width)` is `floor(n / width)`, the index of the bucket of that width that contains `n` (negative `n` goes to negative buckets); `width < 1` is an error.
''')

DM_FNS = [
    Fn("div_round", [("n", "int"), ("d", "int"), ("mode", "str")], "int", err=True),
    Fn("mul_div", [("a", "int"), ("b", "int"), ("c", "int"), ("mode", "str")], "int", err=True),
    Fn("split_even", [("total", "int"), ("parts", "int")], "list<int>", err=True),
    Fn("clamp_div", [("n", "int"), ("d", "int"), ("lo", "int"), ("hi", "int"), ("mode", "str")], "int", err=True),
    Fn("bucket", [("n", "int"), ("width", "int")], "int", err=True),
]

DM_PY = dd(r'''
_MODES = ("floor", "ceil", "trunc", "away", "half-up", "half-down", "half-even", "half-away")


def div_round(n, d, mode):
    if mode not in _MODES:
        raise ValueError("unknown mode")
    if d == 0:
        raise ValueError("division by zero")
    if d < 0:
        n, d = -n, -d
    q, r = divmod(n, d)
    if r == 0:
        return q
    if mode == "floor":
        return q
    if mode == "ceil":
        return q + 1
    if mode == "trunc":
        return q if n >= 0 else q + 1
    if mode == "away":
        return q + 1 if n >= 0 else q
    twice = 2 * r
    if twice < d:
        return q
    if twice > d:
        return q + 1
    if mode == "half-up":
        return q + 1
    if mode == "half-down":
        return q
    if mode == "half-even":
        return q if q % 2 == 0 else q + 1
    return q + 1 if n >= 0 else q


def mul_div(a, b, c, mode):
    return div_round(a * b, c, mode)


def split_even(total, parts):
    if parts < 1:
        raise ValueError("parts must be positive")
    base, extra = divmod(total, parts)
    return [base + 1 if i < extra else base for i in range(parts)]


def clamp_div(n, d, lo, hi, mode):
    if lo > hi:
        raise ValueError("lo > hi")
    return max(lo, min(hi, div_round(n, d, mode)))


def bucket(n, width):
    if width < 1:
        raise ValueError("width must be positive")
    return n // width
''')

DM_JAVA = dd(r'''
import java.util.*;

public final class DivModes {
    private DivModes() {}

    private static final List<String> MODES = Arrays.asList("floor", "ceil", "trunc", "away", "half-up", "half-down", "half-even", "half-away");

    public static long divRound(long n, long d, String mode) {
        if (!MODES.contains(mode)) throw new IllegalArgumentException("unknown mode");
        if (d == 0) throw new IllegalArgumentException("division by zero");
        if (d < 0) {
            n = -n;
            d = -d;
        }
        long q = Math.floorDiv(n, d);
        long r = Math.floorMod(n, d);
        if (r == 0) return q;
        switch (mode) {
            case "floor": return q;
            case "ceil": return q + 1;
            case "trunc": return n >= 0 ? q : q + 1;
            case "away": return n >= 0 ? q + 1 : q;
            default: break;
        }
        long twice = 2 * r;
        if (twice < d) return q;
        if (twice > d) return q + 1;
        switch (mode) {
            case "half-up": return q + 1;
            case "half-down": return q;
            case "half-even": return q % 2 == 0 ? q : q + 1;
            default: return n >= 0 ? q + 1 : q;
        }
    }

    public static long mulDiv(long a, long b, long c, String mode) {
        return divRound(Math.multiplyExact(a, b), c, mode);
    }

    public static List<Long> splitEven(long total, long parts) {
        if (parts < 1) throw new IllegalArgumentException("parts must be positive");
        long base = Math.floorDiv(total, parts);
        long extra = Math.floorMod(total, parts);
        List<Long> out = new ArrayList<>();
        for (long i = 0; i < parts; i++) out.add(i < extra ? base + 1 : base);
        return out;
    }

    public static long clampDiv(long n, long d, long lo, long hi, String mode) {
        if (lo > hi) throw new IllegalArgumentException("lo > hi");
        return Math.max(lo, Math.min(hi, divRound(n, d, mode)));
    }

    public static long bucket(long n, long width) {
        if (width < 1) throw new IllegalArgumentException("width must be positive");
        return Math.floorDiv(n, width);
    }
}
''')

MODES = ["floor", "ceil", "trunc", "away", "half-up", "half-down", "half-even", "half-away"]


def dm_cases(rng):
    out = [("div_round", [7, 2, "half-even"]), ("div_round", [5, 2, "half-even"]), ("div_round", [-7, 2, "half-up"]), ("div_round", [-7, 2, "half-away"]), ("div_round", [7, -2, "floor"]),
           ("div_round", [-7, -2, "ceil"]), ("split_even", [10, 3]), ("split_even", [-7, 3]), ("bucket", [-1, 10]), ("clamp_div", [100, 7, 0, 10, "half-up"])]
    for mode in MODES:
        for n, d in [(7, 2), (-7, 2), (7, -2), (-7, -2), (5, 2), (-5, 2), (6, 4), (-6, 4), (1, 3), (-1, 3), (2, 3), (-2, 3), (0, 5), (9, 3), (-9, 3), (3, 6), (-3, 6), (1, 2), (-1, 2), (1, -2), (13, 4), (-13, 4)]:
            out.append(("div_round", [n, d, mode]))
        for _ in range(8):
            out.append(("div_round", [rng.randint(-10**6, 10**6), rng.choice([-1000, -17, -4, -3, -2, -1, 1, 2, 3, 4, 7, 10, 100, 12345]), mode]))
    out += [("div_round", [5, 0, "floor"]), ("div_round", [0, 0, "half-up"]), ("div_round", [5, 2, "round"]), ("div_round", [4, 2, "Floor"]), ("div_round", [4, 2, ""]), ("div_round", [4, 2, "half_up"]),
            ("div_round", [10, 5, "nope"]), ("div_round", [10, 0, "nope"]), ("div_round", [2**53 - 1, 2, "half-even"]), ("div_round", [-(2**53 - 1), 2, "half-even"]), ("div_round", [2**53 - 1, 3, "ceil"])]
    while sum(1 for c in out if c[0] == "mul_div") < 30:
        a = rng.randint(-2**31 + 1, 2**31 - 1)
        b = rng.randint(-2**31 + 1, 2**31 - 1)
        c = rng.choice([-1000003, -7, -1, 1, 2, 3, 10, 360, 86400, 1000003, 999999937])
        if abs(a * b) // abs(c) >= 2**52:
            continue
        out.append(("mul_div", [a, b, c, rng.choice(MODES)]))
    for a, b, c, mode in [(2**31 - 1, 2**31 - 1, 1000003, "half-even"), (-(2**31 - 1), 2**31 - 1, 999999937, "floor"), (5, 5, 0, "floor"), (5, 5, 2, "bad"), (125, 3, 100, "half-up"), (125, 3, 100, "half-even"), (-125, 3, 100, "half-away")]:
        out.append(("mul_div", [a, b, c, mode]))
    for total, parts in [(10, 3), (-7, 3), (0, 4), (7, 1), (3, 5), (-3, 5), (-1, 4), (100, 7), (-100, 7), (12, 12), (2**40, 7), (-(2**40), 9), (5, 0), (5, -2), (0, 0)]:
        out.append(("split_even", [total, parts]))
    for _ in range(12):
        out.append(("split_even", [rng.randint(-1000, 1000), rng.randint(1, 20)]))
    for n, d, lo, hi, mode in [(100, 7, 0, 10, "half-up"), (100, 7, 0, 20, "half-up"), (-100, 7, -5, 5, "floor"), (-100, 7, 0, 5, "ceil"), (5, 1, 7, 3, "floor"), (5, 0, 0, 9, "floor"), (5, 2, 0, 9, "x"), (1000, 3, 5, 5, "trunc")]:
        out.append(("clamp_div", [n, d, lo, hi, mode]))
    for _ in range(10):
        out.append(("clamp_div", [rng.randint(-5000, 5000), rng.choice([-9, -2, 3, 7, 25]), rng.randint(-50, 0), rng.randint(0, 50), rng.choice(MODES)]))
    for n, w in [(-1, 10), (0, 10), (9, 10), (10, 10), (-10, 10), (-11, 10), (123456789, 1000), (-123456789, 1000), (5, 1), (5, 0), (5, -3), (2**53 - 1, 2)]:
        out.append(("bucket", [n, w]))
    return out


DM = PortLib(
    slug="div-modes",
    title="integer division with rounding modes",
    blurb="A billing library divides amounts and quantities in many places and each caller needs a specific rounding rule, negative numbers included.",
    spec=DM_SPEC,
    fns=DM_FNS,
    impls={"python": {"div_modes.py": DM_PY}, "java": {"DivModes.java": DM_JAVA}},
    cases=dm_cases,
    difficulty=1,
    n_examples=10,
    pairs=[("python", "java", "full"), ("java", "python", "full"), ("python", "java", "stub"), ("java", "python", "stub")],
    traps=["floor division and modulo of negative operands", "exact ties", "negative divisors", "mode validity checked before the exactness shortcut"],
    tags=["rounding", "floor-div"],
)
register_port(DM, __name__)

# ======================================================================================================================
# ticket-codes: base-28 ticket codes with a check symbol
# ======================================================================================================================

TC_SPEC = dd('''
    Event tickets carry a short code. The code alphabet has **28 symbols** (look-alike characters are left out) in this order:
    `3 4 6 7 8 9 A B C D E F G H J K L M N P Q R T U V W X Y`, so `3` is digit 0, `4` is digit 1, ..., `Y` is digit 27.

    * A ticket number is an integer `0 <= n < 28^6` (481890304). `encode_ticket(n)` writes it with exactly six symbols, most significant first, padded on the left with `3`
      (`0` is `333333`, `27` is `33333Y`, `28` is `333343`). A number outside the range is an error.
    * `decode_ticket(code)` is the inverse. The code must have exactly six symbols; the ASCII letters `a`..`z` are accepted as their capitals and no other case or Unicode folding is applied;
      any other character (or another length) is an error.
    * `check_symbol(n)` is the symbol with digit value `(1*d1 + 2*d2 + 3*d3 + 4*d4 + 5*d5 + 6*d6) mod 28`, where `d1` is the most significant of the six digits of `n` (same range error as `encode_ticket`).
      `with_check(n)` is `encode_ticket(n)` followed by `check_symbol(n)` (seven symbols).
    * `verify_ticket(code)` is true when `code` is seven symbols (letters in either case, as in `decode_ticket`) whose last symbol is the check symbol of the number in the first six. Malformed text is simply false, never an error.
    * `next_ticket(code, step)` is the six-symbol code of `decode_ticket(code) + step`, wrapping around modulo 28^6 (`step` may be negative or as large as 2^40). An invalid code is an error.
''')

TC_FNS = [
    Fn("encode_ticket", [("n", "int")], "str", err=True),
    Fn("decode_ticket", [("code", "str")], "int", err=True),
    Fn("check_symbol", [("n", "int")], "str", err=True),
    Fn("with_check", [("n", "int")], "str", err=True),
    Fn("verify_ticket", [("code", "str")], "bool"),
    Fn("next_ticket", [("code", "str"), ("step", "int")], "str", err=True),
]

TC_PY = dd(r'''
_ALPHABET = "346789ABCDEFGHJKLMNPQRTUVWXY"
_SPAN = 28 ** 6


def _norm(code):
    return "".join(chr(ord(c) - 32) if "a" <= c <= "z" else c for c in code)


def _digits(code, length):
    code = _norm(code)
    if len(code) != length:
        raise ValueError("wrong length")
    out = []
    for c in code:
        i = _ALPHABET.find(c)
        if i < 0:
            raise ValueError("bad symbol")
        out.append(i)
    return out


def _digits_of(n):
    if n < 0 or n >= _SPAN:
        raise ValueError("ticket number out of range")
    out = []
    for _ in range(6):
        n, r = divmod(n, 28)
        out.append(r)
    return out[::-1]


def encode_ticket(n):
    return "".join(_ALPHABET[d] for d in _digits_of(n))


def decode_ticket(code):
    n = 0
    for d in _digits(code, 6):
        n = n * 28 + d
    return n


def check_symbol(n):
    ds = _digits_of(n)
    return _ALPHABET[sum((i + 1) * d for i, d in enumerate(ds)) % 28]


def with_check(n):
    return encode_ticket(n) + check_symbol(n)


def verify_ticket(code):
    try:
        ds = _digits(code, 7)
    except ValueError:
        return False
    n = 0
    for d in ds[:6]:
        n = n * 28 + d
    return _ALPHABET[sum((i + 1) * d for i, d in enumerate(ds[:6])) % 28] == _ALPHABET[ds[6]]


def next_ticket(code, step):
    return encode_ticket((decode_ticket(code) + step) % _SPAN)
''')

TC_JS = dd(r'''
'use strict';

const ALPHABET = '346789ABCDEFGHJKLMNPQRTUVWXY';
const SPAN = 28 ** 6;

function norm(code) {
  let out = '';
  for (const c of code) out += c >= 'a' && c <= 'z' ? String.fromCharCode(c.charCodeAt(0) - 32) : c;
  return out;
}

function digits(code, length) {
  const text = norm(code);
  if (Array.from(text).length !== length) throw new Error('wrong length');
  const out = [];
  for (const c of text) {
    const i = ALPHABET.indexOf(c);
    if (i < 0) throw new Error('bad symbol');
    out.push(i);
  }
  return out;
}

function digitsOf(n) {
  if (!Number.isSafeInteger(n) || n < 0 || n >= SPAN) throw new Error('ticket number out of range');
  const out = [];
  let v = n;
  for (let i = 0; i < 6; i++) {
    out.push(v % 28);
    v = Math.floor(v / 28);
  }
  return out.reverse();
}

function weighted(ds) {
  let s = 0;
  for (let i = 0; i < 6; i++) s += (i + 1) * ds[i];
  return s % 28;
}

function encodeTicket(n) {
  return digitsOf(n).map((d) => ALPHABET[d]).join('');
}

function decodeTicket(code) {
  let n = 0;
  for (const d of digits(code, 6)) n = n * 28 + d;
  return n;
}

function checkSymbol(n) {
  return ALPHABET[weighted(digitsOf(n))];
}

function withCheck(n) {
  return encodeTicket(n) + checkSymbol(n);
}

function verifyTicket(code) {
  let ds;
  try {
    ds = digits(code, 7);
  } catch (e) {
    return false;
  }
  return weighted(ds.slice(0, 6)) === ds[6];
}

function nextTicket(code, step) {
  const v = decodeTicket(code) + step;
  return encodeTicket(((v % SPAN) + SPAN) % SPAN);
}

module.exports = { encodeTicket, decodeTicket, checkSymbol, withCheck, verifyTicket, nextTicket };
''')

TC_ALPHA = "346789ABCDEFGHJKLMNPQRTUVWXY"


def tc_cases(rng):
    span = 28 ** 6
    out = [("encode_ticket", [0]), ("encode_ticket", [27]), ("encode_ticket", [28]), ("decode_ticket", ["33333Y"]), ("check_symbol", [12345]), ("with_check", [0]), ("verify_ticket", ["3333330"]), ("next_ticket", ["333333", -1])]
    for n in [1, 783, 784, 21951, 21952, 614655, 1000000, span - 1, span, -1, 2**40, span + 5]:
        out.append(("encode_ticket", [n]))
        out.append(("check_symbol", [n]))
        out.append(("with_check", [n]))
    for _ in range(20):
        n = rng.randint(0, span - 1)
        out.append(("encode_ticket", [n]))
        out.append(("check_symbol", [n]))
        out.append(("with_check", [n]))
        out.append(("decode_ticket", [_enc(n)]))
        out.append(("verify_ticket", [_enc(n) + TC_ALPHA[_chk(n)]]))
        out.append(("verify_ticket", [(_enc(n) + TC_ALPHA[(_chk(n) + rng.randint(1, 27)) % 28])]))
        out.append(("verify_ticket", [(_enc(n) + TC_ALPHA[_chk(n)]).lower()]))
    for s in ["333333", "33333Y", "YYYYYY", "yyyyyy", "abcdef", "ABCDEF", "a3a3a3", "33333", "3333333", "", "333 33", "33333I", "33333O", "33333S", "33333Z", "333330", "33333\u0131", "33333\u017f", "\uff23\uff23\uff23\uff23\uff23\uff23",
              "33333\n", " 33333", "3333\u00e9", "\U0001f600\U0001f600\U0001f600", "\u212a33333", "kkkkkk", "KKKKKK", "ll3333", "uuuuuu"]:
        out.append(("decode_ticket", [s]))
        out.append(("verify_ticket", [s]))
        out.append(("next_ticket", [s, 1]))
    for s in ["3333330", "33333Y8", "3333333", "333333", "33333333", "", "333333\u00e9", "3333 33", "yyyyyyy", "YYYYYYY", "\U0001f600333333", "4333339"]:
        out.append(("verify_ticket", [s]))
    for code, step in [("333333", 1), ("333333", -1), ("YYYYYY", 1), ("YYYYYY", -1), ("33333Y", 1), ("abcdef", 0), ("hhhhhh", 2**40), ("hhhhhh", -(2**40)), ("333333", span), ("333333", -span), ("333333", 2 * span + 3),
                       ("bad", 1), ("333333", 0), ("4Y4Y4Y", -987654321)]:
        out.append(("next_ticket", [code, step]))
    for _ in range(15):
        out.append(("next_ticket", [_enc(rng.randint(0, span - 1)), rng.randint(-2**40, 2**40)]))
    return out


def _enc(n):
    return "".join(TC_ALPHA[(n // 28 ** i) % 28] for i in range(5, -1, -1))


def _chk(n):
    ds = [(n // 28 ** i) % 28 for i in range(5, -1, -1)]
    return sum((i + 1) * d for i, d in enumerate(ds)) % 28


TC = PortLib(
    slug="ticket-codes",
    title="base-28 ticket codes",
    blurb="A ticketing service prints six-symbol codes in a 28-symbol alphabet with a weighted check symbol, and steps through them modulo the code space.",
    spec=TC_SPEC,
    fns=TC_FNS,
    impls={"javascript": {"src/ticket_codes.js": TC_JS}, "python": {"ticket_codes.py": TC_PY}},
    cases=tc_cases,
    difficulty=1,
    n_examples=10,
    pairs=[("python", "javascript", "full"), ("javascript", "python", "full"), ("python", "javascript", "stub"), ("javascript", "python", "stub")],
    traps=["negative modulo in JavaScript", "UTF-16 length versus code points", "ASCII-only case folding"],
    tags=["base-n", "safe-integers"],
)
register_port(TC, __name__)

# ======================================================================================================================
# flag-sets: 8-bit access masks (typescript <-> javascript)
# ======================================================================================================================

FS_SPEC = dd('''
    Access rights are an 8-bit mask. The flag letters, from the lowest bit: `R`=1, `W`=2, `X`=4, `D`=8, `S`=16, `A`=32, `L`=64, `V`=128. This is also the canonical order of letters in text.

    * `flags_from(text)` reads a set of letters: each of the eight capital letters at most once, in any order; `""` is 0. Any other character or a repeated letter is an error.
    * `flags_to(mask)` writes the letters of the set bits in canonical order (`""` for 0).
    * `grant(mask, other)` sets the bits of `other`, `revoke(mask, other)` clears them, `toggle(mask, other)` flips them. Results stay within 8 bits.
    * `rotl8(mask, k)` rotates the 8 bits left by `k` positions; `k` may be any integer, a negative `k` rotates right, and only `k mod 8` matters (`rotl8(0x81, 1)` is `0x03`, `rotl8(0x81, -1)` is `0xC0`).
    * `popcount(mask)` is the number of set bits.
    * `implied(mask)` adds the rights that others imply, repeatedly until nothing changes: `A` implies `R W X D S`, `D` implies `W`, `W` implies `R`, `X` implies `R`, `L` implies `V`.
    * `can(mask, need)` is true when every bit of `need` is in `implied(mask)` (`need = 0` is always true).
''')

FS_FNS = [
    Fn("flags_from", [("text", "str")], "u8", err=True),
    Fn("flags_to", [("mask", "u8")], "str"),
    Fn("grant", [("mask", "u8"), ("other", "u8")], "u8"),
    Fn("revoke", [("mask", "u8"), ("other", "u8")], "u8"),
    Fn("toggle", [("mask", "u8"), ("other", "u8")], "u8"),
    Fn("rotl8", [("mask", "u8"), ("k", "int")], "u8"),
    Fn("popcount", [("mask", "u8")], "int"),
    Fn("implied", [("mask", "u8")], "u8"),
    Fn("can", [("mask", "u8"), ("need", "u8")], "bool"),
]

FS_PY = dd(r'''
_LETTERS = "RWXDSALV"
_IMPLY = [(32, 1 | 2 | 4 | 8 | 16), (8, 2), (2, 1), (4, 1), (64, 128)]


def flags_from(text):
    mask = 0
    for ch in text:
        i = _LETTERS.find(ch)
        if i < 0:
            raise ValueError("unknown flag letter")
        if mask & (1 << i):
            raise ValueError("duplicate flag")
        mask |= 1 << i
    return mask


def flags_to(mask):
    return "".join(ch for i, ch in enumerate(_LETTERS) if mask & (1 << i))


def grant(mask, other):
    return (mask | other) & 0xFF


def revoke(mask, other):
    return mask & ~other & 0xFF


def toggle(mask, other):
    return (mask ^ other) & 0xFF


def rotl8(mask, k):
    k %= 8
    return ((mask << k) | (mask >> (8 - k))) & 0xFF


def popcount(mask):
    return bin(mask & 0xFF).count("1")


def implied(mask):
    while True:
        new = mask
        for have, add in _IMPLY:
            if mask & have:
                new |= add
        if new == mask:
            return mask
        mask = new


def can(mask, need):
    return (implied(mask) & need) == need
''')

FS_TS = dd(r'''
const LETTERS = 'RWXDSALV';
const IMPLY: Array<[number, number]> = [[32, 1 | 2 | 4 | 8 | 16], [8, 2], [2, 1], [4, 1], [64, 128]];

export function flagsFrom(text: string): number {
  let mask = 0;
  for (const ch of text) {
    const i = LETTERS.indexOf(ch);
    if (i < 0) throw new Error('unknown flag letter');
    if (mask & (1 << i)) throw new Error('duplicate flag');
    mask |= 1 << i;
  }
  return mask;
}

export function flagsTo(mask: number): string {
  let out = '';
  for (let i = 0; i < 8; i++) {
    if (mask & (1 << i)) out += LETTERS[i];
  }
  return out;
}

export function grant(mask: number, other: number): number {
  return (mask | other) & 0xff;
}

export function revoke(mask: number, other: number): number {
  return mask & ~other & 0xff;
}

export function toggle(mask: number, other: number): number {
  return (mask ^ other) & 0xff;
}

export function rotl8(mask: number, k: number): number {
  const s = ((k % 8) + 8) % 8;
  return ((mask << s) | (mask >> (8 - s))) & 0xff;
}

export function popcount(mask: number): number {
  let n = 0;
  for (let i = 0; i < 8; i++) {
    if (mask & (1 << i)) n++;
  }
  return n;
}

export function implied(mask: number): number {
  let cur = mask;
  for (;;) {
    let next = cur;
    for (const [have, add] of IMPLY) {
      if (cur & have) next |= add;
    }
    if (next === cur) return cur;
    cur = next;
  }
}

export function can(mask: number, need: number): boolean {
  return (implied(mask) & need) === need;
}
''')

FS_JS = dd(r'''
'use strict';

const LETTERS = 'RWXDSALV';
const IMPLY = [[32, 1 | 2 | 4 | 8 | 16], [8, 2], [2, 1], [4, 1], [64, 128]];

function flagsFrom(text) {
  let mask = 0;
  for (const ch of text) {
    const i = LETTERS.indexOf(ch);
    if (i < 0) throw new Error('unknown flag letter');
    if (mask & (1 << i)) throw new Error('duplicate flag');
    mask |= 1 << i;
  }
  return mask;
}

function flagsTo(mask) {
  let out = '';
  for (let i = 0; i < 8; i++) {
    if (mask & (1 << i)) out += LETTERS[i];
  }
  return out;
}

function grant(mask, other) {
  return (mask | other) & 0xff;
}

function revoke(mask, other) {
  return mask & ~other & 0xff;
}

function toggle(mask, other) {
  return (mask ^ other) & 0xff;
}

function rotl8(mask, k) {
  const s = ((k % 8) + 8) % 8;
  return ((mask << s) | (mask >> (8 - s))) & 0xff;
}

function popcount(mask) {
  let n = 0;
  for (let i = 0; i < 8; i++) {
    if (mask & (1 << i)) n++;
  }
  return n;
}

function implied(mask) {
  let cur = mask;
  for (;;) {
    let next = cur;
    for (const [have, add] of IMPLY) {
      if (cur & have) next |= add;
    }
    if (next === cur) return cur;
    cur = next;
  }
}

function can(mask, need) {
  return (implied(mask) & need) === need;
}

module.exports = { flagsFrom, flagsTo, grant, revoke, toggle, rotl8, popcount, implied, can };
''')


def fs_cases(rng):
    out = [("flags_from", ["RWX"]), ("flags_to", [7]), ("grant", [1, 2]), ("revoke", [255, 1]), ("toggle", [5, 7]), ("rotl8", [0x81, 1]), ("rotl8", [0x81, -1]), ("popcount", [0xFF]), ("implied", [32]), ("can", [8, 1])]
    for s in ["", "R", "RWXDSALV", "VLASDXWR", "WR", "RR", "r", "RW ", " R", "R\n", "Q", "RWQ", "A\u00c0", "\u0420", "R,W", "RWRW", "\U0001f600", "LV", "DS"]:
        out.append(("flags_from", [s]))
    for m in [0, 1, 2, 4, 8, 16, 32, 64, 128, 255, 129, 170, 85, 37]:
        out.append(("flags_to", [m]))
        out.append(("popcount", [m]))
        out.append(("implied", [m]))
    for _ in range(25):
        a, b = rng.randint(0, 255), rng.randint(0, 255)
        out.append(("grant", [a, b]))
        out.append(("revoke", [a, b]))
        out.append(("toggle", [a, b]))
        out.append(("can", [a, b]))
        out.append(("rotl8", [a, rng.choice([-1000001, -17, -9, -8, -3, -1, 0, 1, 3, 7, 8, 9, 16, 1000003, 2**40 + 3, -(2**40) - 5])]))
        out.append(("popcount", [a]))
        out.append(("implied", [a]))
        out.append(("flags_to", [a]))
    for a in [0, 255, 128, 1]:
        for k in range(-9, 10):
            out.append(("rotl8", [a, k]))
    for m, need in [(0, 0), (255, 0), (0, 1), (32, 31), (32, 63), (8, 3), (8, 7), (4, 3), (64, 128), (128, 64), (2, 1), (1, 2), (33, 16)]:
        out.append(("can", [m, need]))
    for _ in range(10):
        s = "".join(rng.sample("RWXDSALV", rng.randint(0, 8)))
        out.append(("flags_from", [s]))
    return out


FS = PortLib(
    slug="flag-sets",
    title="access flag sets",
    blurb="An access-control helper keeps rights in an 8-bit mask with named letters, implications between rights and bit rotation for its hashing.",
    spec=FS_SPEC,
    fns=FS_FNS,
    impls={"python": {"flag_sets.py": FS_PY}, "typescript": {"src/flag_sets.ts": FS_TS}, "javascript": {"src/flag_sets.js": FS_JS}},
    cases=fs_cases,
    difficulty=1,
    n_examples=10,
    pairs=[("typescript", "javascript", "full"), ("javascript", "typescript", "full"), ("typescript", "javascript", "stub"), ("javascript", "typescript", "stub")],
    traps=["bitwise NOT yields a negative number in JavaScript", "shift counts and rotation modulo 8 for negative k", "type annotations (strict tsc)"],
    tags=["bitmask", "ts-js"],
)
register_port(FS, __name__)
