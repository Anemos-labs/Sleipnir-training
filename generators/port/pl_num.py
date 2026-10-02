"""Port libraries about number systems, statistics and checked arithmetic."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

# ======================================================================================================================
# bal-ternary: balanced ternary text codec
# ======================================================================================================================

BT_SPEC = dd('''
    **Balanced ternary** writes an integer with the digits `+` (one), `0` and `-` (minus one), most significant digit
    first; the digit at position `i` (from the right, starting at 0) is worth `3^i`. `+-0` is `9 - 3 + 0 = 6`, `-` is `-1`,
    `-++` is `-9 + 3 + 1 = -5`. Every integer has exactly one **canonical** text: no leading `0`, except that zero is the
    single character `0`. There is no separate minus sign.

    * `to_bt(n)` returns the canonical text of `n`.
    * `from_bt(text)` accepts canonical text only: at least one character, only `+`, `0`, `-`, no leading `0` unless the
      text is exactly `0`, and at most 34 characters. Anything else is an error.
    * `neg_bt(text)` swaps `+` and `-` (zero stays `0`); invalid input is an error.
    * `add_bt(a, b)` is the canonical text of the sum; invalid input is an error. (Test inputs have at most 32 digits.)
    * `cmp_bt(a, b)` is `-1`, `0` or `1` by numeric value; invalid input is an error.
    * `to_bt_width(n, width)` is `to_bt(n)` padded on the left with `0` to `width` characters; it is an error when the
      text is already longer than `width` or when `width < 1`.
''')

BT_FNS = [
    Fn("to_bt", [("n", "int")], "str"),
    Fn("from_bt", [("text", "str")], "int", err=True),
    Fn("neg_bt", [("text", "str")], "str", err=True),
    Fn("add_bt", [("a", "str"), ("b", "str")], "str", err=True),
    Fn("cmp_bt", [("a", "str"), ("b", "str")], "i32", err=True),
    Fn("to_bt_width", [("n", "int"), ("width", "int")], "str", err=True),
]

BT_PY = dd(r'''
def to_bt(n):
    if n == 0:
        return "0"
    out = []
    while n != 0:
        r = n % 3
        if r == 2:
            r = -1
        out.append({1: "+", 0: "0", -1: "-"}[r])
        n = (n - r) // 3
    return "".join(reversed(out))


def from_bt(text):
    if not text or len(text) > 34 or (text[0] == "0" and text != "0"):
        raise ValueError("not canonical")
    v = 0
    for c in text:
        if c not in "+0-":
            raise ValueError("bad digit")
        v = v * 3 + {"+": 1, "0": 0, "-": -1}[c]
    return v


def neg_bt(text):
    from_bt(text)
    return text.translate({ord("+"): "-", ord("-"): "+"})


def add_bt(a, b):
    return to_bt(from_bt(a) + from_bt(b))


def cmp_bt(a, b):
    x, y = from_bt(a), from_bt(b)
    return (x > y) - (x < y)


def to_bt_width(n, width):
    s = to_bt(n)
    if width < 1 or len(s) > width:
        raise ValueError("does not fit")
    return "0" * (width - len(s)) + s
''')

BT_RS = dd(r'''
pub fn to_bt(n: i64) -> String {
    if n == 0 {
        return "0".to_string();
    }
    let mut n = n;
    let mut out: Vec<char> = Vec::new();
    while n != 0 {
        let mut r = n.rem_euclid(3);
        if r == 2 {
            r = -1;
        }
        out.push(match r {
            1 => '+',
            0 => '0',
            _ => '-',
        });
        n = (n - r) / 3;
    }
    out.iter().rev().collect()
}

pub fn from_bt(text: &str) -> Result<i64, String> {
    let chars: Vec<char> = text.chars().collect();
    if chars.is_empty() || chars.len() > 34 || (chars[0] == '0' && chars.len() > 1) {
        return Err("not canonical".to_string());
    }
    let mut v: i64 = 0;
    for c in chars {
        let d = match c {
            '+' => 1,
            '0' => 0,
            '-' => -1,
            _ => return Err(format!("bad digit {:?}", c)),
        };
        v = v * 3 + d;
    }
    Ok(v)
}

pub fn neg_bt(text: &str) -> Result<String, String> {
    from_bt(text)?;
    Ok(text
        .chars()
        .map(|c| match c {
            '+' => '-',
            '-' => '+',
            o => o,
        })
        .collect())
}

pub fn add_bt(a: &str, b: &str) -> Result<String, String> {
    Ok(to_bt(from_bt(a)? + from_bt(b)?))
}

pub fn cmp_bt(a: &str, b: &str) -> Result<i32, String> {
    let (x, y) = (from_bt(a)?, from_bt(b)?);
    Ok(if x < y { -1 } else if x > y { 1 } else { 0 })
}

pub fn to_bt_width(n: i64, width: i64) -> Result<String, String> {
    let s = to_bt(n);
    if width < 1 || (s.chars().count() as i64) > width {
        return Err("does not fit".to_string());
    }
    Ok(format!("{}{}", "0".repeat((width as usize) - s.len()), s))
}
''')

BT_RB = dd(r'''
module BalTernary
  def self.to_bt(n)
    return '0' if n == 0
    out = []
    while n != 0
      r = n % 3
      r = -1 if r == 2
      out << { 1 => '+', 0 => '0', -1 => '-' }[r]
      n = (n - r) / 3
    end
    out.reverse.join
  end

  def self.from_bt(text)
    raise ArgumentError, 'not canonical' if text.empty? || text.length > 34 || (text[0] == '0' && text != '0')
    v = 0
    text.each_char do |c|
      d = { '+' => 1, '0' => 0, '-' => -1 }[c]
      raise ArgumentError, 'bad digit' if d.nil?
      v = v * 3 + d
    end
    v
  end

  def self.neg_bt(text)
    from_bt(text)
    text.tr('+-', '-+')
  end

  def self.add_bt(a, b)
    to_bt(from_bt(a) + from_bt(b))
  end

  def self.cmp_bt(a, b)
    from_bt(a) <=> from_bt(b)
  end

  def self.to_bt_width(n, width)
    s = to_bt(n)
    raise ArgumentError, 'does not fit' if width < 1 || s.length > width
    ('0' * (width - s.length)) + s
  end
end
''')


def bt_cases(rng):
    out = [("to_bt", [6]), ("to_bt", [-5]), ("to_bt", [0]), ("from_bt", ["+-0"]), ("from_bt", ["-++"]), ("neg_bt", ["+-0"]), ("add_bt", ["+-", "+"]), ("cmp_bt", ["-", "0"]),
           ("to_bt_width", [4, 5]), ("to_bt_width", [4, 1])]
    for n in [1, -1, 2, -2, 3, -3, 4, 5, 13, 14, -13, -14, 40, 41, 121, -121, 122, 1000, -1000, 9007199254740991, -9007199254740991, 8338590573969, 3 ** 33, -(3 ** 33)]:
        out.append(("to_bt", [n]))
    for _ in range(30):
        n = rng.randint(-10 ** rng.randint(1, 15), 10 ** rng.randint(1, 15))
        out.append(("to_bt", [n]))
    for s in ["0", "+", "-", "++", "+-", "-+", "--", "+0+", "-0-", "+" * 34, "-" * 34, "+" * 35, "0+", "00", "", "1", "+1", "+ ", " +", "+\n", "＋", "+-0-+-0+-", "-0+" * 11,
              "-" + "+" * 33, "+" + "-" * 33]:
        out.append(("from_bt", [s]))
    for s in ["+", "-", "0", "+-0", "-++", "", "++x", "00", "-0+-"]:
        out.append(("neg_bt", [s]))
    for _ in range(25):
        a = rng.randint(-10 ** 12, 10 ** 12)
        b = rng.randint(-10 ** 12, 10 ** 12)
        out.append(("add_bt", [_bt(a), _bt(b)]))
        out.append(("cmp_bt", [_bt(a), _bt(rng.choice([a, b]))]))
    for a, b in [("+", "-"), ("0", "0"), ("+" * 32, "+"), ("-" * 32, "-"), ("+-", "-+"), ("+", "x"), ("", "+"), ("01", "+")]:
        out.append(("add_bt", [a, b]))
        out.append(("cmp_bt", [a, b]))
    for n, w in [(0, 1), (0, 4), (1, 1), (-1, 3), (13, 3), (14, 3), (14, 4), (-5, 2), (-5, 5), (100, 0), (100, -1), (100, 10), (-9007199254740991, 34), (9007199254740991, 33)]:
        out.append(("to_bt_width", [n, w]))
    return out


def _bt(n):
    if n == 0:
        return "0"
    out = []
    while n:
        r = n % 3
        if r == 2:
            r = -1
        out.append("0+-"[r])
        n = (n - r) // 3
    return "".join(reversed(out))


BT = PortLib(
    slug="bal-ternary",
    title="balanced ternary codec",
    blurb="A teaching-lab project stores small integers as balanced ternary strings and needs the codec in more than one language.",
    spec=BT_SPEC,
    fns=BT_FNS,
    impls={"python": {"bal_ternary.py": BT_PY}, "rust": {"src/lib.rs": BT_RS}, "ruby": {"lib/bal_ternary.rb": BT_RB}},
    cases=bt_cases,
    difficulty=2,
    traps=["remainder of negative numbers", "canonical form strictness", "error idioms"],
    tags=["number-systems"],
    pairs=[("python", "rust", "full"), ("rust", "ruby", "full"), ("ruby", "python", "stub"), ("python", "ruby", "stub")],
)
register_port(BT, __name__)

# ======================================================================================================================
# stats-quarter: small integer statistics
# ======================================================================================================================

ST_SPEC = dd('''
    Statistics over lists of whole numbers (`int`). Nothing here uses floating point.

    * `mean_round(xs)` is the mean rounded to the nearest integer; an exact tie (the mean is `k + 1/2`) goes to the
      **even** neighbour (`[1, 2]` gives `2`, `[2, 3]` gives `2`, `[-1, -2]` gives `-2`). The empty list is an error.
    * `median2(xs)` is *twice* the median, so it is always an integer: the middle element times 2 for an odd count, the sum
      of the two middle elements for an even count. Empty is an error.
    * `percentile_nr(xs, p)` is the nearest-rank percentile: sort ascending, take the element at 1-based rank
      `ceil(p * n / 100)`. `p` must be in `1..100` and the list non-empty, otherwise error.
    * `mode_smallest(xs)` is the most frequent value; among equally frequent values the smallest. Empty gives *absent*.
    * `spread(xs)` is `max - min`; empty is an error.
    * `histogram(xs, lo, width, bins)` counts how many values fall into each of `bins` consecutive buckets, bucket `i`
      being `[lo + i*width, lo + (i+1)*width)`. Values below `lo` or at/after `lo + bins*width` are ignored. `width <= 0`
      or `bins <= 0` is an error.
    * `trimmed_sum(xs, k)` is the sum after discarding the `k` smallest and the `k` largest values (by value; which of
      equal values is discarded does not change the sum). `k < 0` or `2k > len(xs)` is an error; `2k == len(xs)` gives 0.
''')

ST_FNS = [
    Fn("mean_round", [("xs", "list<int>")], "int", err=True),
    Fn("median2", [("xs", "list<int>")], "int", err=True),
    Fn("percentile_nr", [("xs", "list<int>"), ("p", "int")], "int", err=True),
    Fn("mode_smallest", [("xs", "list<int>")], "opt<int>"),
    Fn("spread", [("xs", "list<int>")], "int", err=True),
    Fn("histogram", [("xs", "list<int>"), ("lo", "int"), ("width", "int"), ("bins", "int")], "list<int>", err=True),
    Fn("trimmed_sum", [("xs", "list<int>"), ("k", "int")], "int", err=True),
]

ST_PY = dd(r'''
def mean_round(xs):
    if not xs:
        raise ValueError("empty")
    n = len(xs)
    q, r = divmod(sum(xs), n)
    if 2 * r < n:
        return q
    if 2 * r > n:
        return q + 1
    return q if q % 2 == 0 else q + 1


def median2(xs):
    if not xs:
        raise ValueError("empty")
    s = sorted(xs)
    n = len(s)
    if n % 2:
        return 2 * s[n // 2]
    return s[n // 2 - 1] + s[n // 2]


def percentile_nr(xs, p):
    if not xs or p < 1 or p > 100:
        raise ValueError("bad input")
    s = sorted(xs)
    rank = (p * len(s) + 99) // 100
    return s[rank - 1]


def mode_smallest(xs):
    counts = {}
    for x in xs:
        counts[x] = counts.get(x, 0) + 1
    if not counts:
        return None
    best = max(counts.values())
    return min(k for k, v in counts.items() if v == best)


def spread(xs):
    if not xs:
        raise ValueError("empty")
    return max(xs) - min(xs)


def histogram(xs, lo, width, bins):
    if width <= 0 or bins <= 0:
        raise ValueError("bad buckets")
    out = [0] * bins
    for x in xs:
        if x < lo:
            continue
        i = (x - lo) // width
        if i < bins:
            out[i] += 1
    return out


def trimmed_sum(xs, k):
    if k < 0 or 2 * k > len(xs):
        raise ValueError("bad k")
    s = sorted(xs)
    return sum(s[k:len(s) - k])
''')

ST_GO = dd(r'''
package statsquarter

import (
	"errors"
	"sort"
)

func sortedCopy(xs []int64) []int64 {
	s := append([]int64(nil), xs...)
	sort.Slice(s, func(i, j int) bool { return s[i] < s[j] })
	return s
}

func floorDivMod(a, b int64) (int64, int64) {
	q, r := a/b, a%b
	if r != 0 && (r < 0) != (b < 0) {
		q--
		r += b
	}
	return q, r
}

func MeanRound(xs []int64) (int64, error) {
	if len(xs) == 0 {
		return 0, errors.New("empty")
	}
	var sum int64
	for _, x := range xs {
		sum += x
	}
	n := int64(len(xs))
	q, r := floorDivMod(sum, n)
	switch {
	case 2*r < n:
		return q, nil
	case 2*r > n:
		return q + 1, nil
	}
	if q%2 == 0 {
		return q, nil
	}
	return q + 1, nil
}

func Median2(xs []int64) (int64, error) {
	if len(xs) == 0 {
		return 0, errors.New("empty")
	}
	s := sortedCopy(xs)
	n := len(s)
	if n%2 == 1 {
		return 2 * s[n/2], nil
	}
	return s[n/2-1] + s[n/2], nil
}

func PercentileNr(xs []int64, p int64) (int64, error) {
	if len(xs) == 0 || p < 1 || p > 100 {
		return 0, errors.New("bad input")
	}
	s := sortedCopy(xs)
	rank := (p*int64(len(s)) + 99) / 100
	return s[rank-1], nil
}

func ModeSmallest(xs []int64) (int64, bool) {
	if len(xs) == 0 {
		return 0, false
	}
	counts := map[int64]int{}
	for _, x := range xs {
		counts[x]++
	}
	best, bestCount := int64(0), 0
	for v, c := range counts {
		if c > bestCount || (c == bestCount && v < best) {
			best, bestCount = v, c
		}
	}
	return best, true
}

func Spread(xs []int64) (int64, error) {
	if len(xs) == 0 {
		return 0, errors.New("empty")
	}
	lo, hi := xs[0], xs[0]
	for _, x := range xs {
		if x < lo {
			lo = x
		}
		if x > hi {
			hi = x
		}
	}
	return hi - lo, nil
}

func Histogram(xs []int64, lo, width, bins int64) ([]int64, error) {
	if width <= 0 || bins <= 0 {
		return nil, errors.New("bad buckets")
	}
	out := make([]int64, bins)
	for _, x := range xs {
		if x < lo {
			continue
		}
		i := (x - lo) / width
		if i < bins {
			out[i]++
		}
	}
	return out, nil
}

func TrimmedSum(xs []int64, k int64) (int64, error) {
	if k < 0 || 2*k > int64(len(xs)) {
		return 0, errors.New("bad k")
	}
	s := sortedCopy(xs)
	var sum int64
	for _, x := range s[k : int64(len(s))-k] {
		sum += x
	}
	return sum, nil
}
''')

ST_JS = dd(r'''
'use strict';

const byValue = (a, b) => a - b;

function meanRound(xs) {
  if (xs.length === 0) throw new Error('empty');
  const n = xs.length;
  const sum = xs.reduce((a, b) => a + b, 0);
  const q = Math.floor(sum / n);
  const r = sum - q * n;
  if (2 * r < n) return q;
  if (2 * r > n) return q + 1;
  return q % 2 === 0 ? q : q + 1;
}

function median2(xs) {
  if (xs.length === 0) throw new Error('empty');
  const s = [...xs].sort(byValue);
  const n = s.length;
  return n % 2 ? 2 * s[(n - 1) / 2] : s[n / 2 - 1] + s[n / 2];
}

function percentileNr(xs, p) {
  if (xs.length === 0 || p < 1 || p > 100) throw new Error('bad input');
  const s = [...xs].sort(byValue);
  const rank = Math.floor((p * s.length + 99) / 100);
  return s[rank - 1];
}

function modeSmallest(xs) {
  if (xs.length === 0) return null;
  const counts = new Map();
  for (const x of xs) counts.set(x, (counts.get(x) || 0) + 1);
  let best = null;
  let bestCount = 0;
  for (const [v, c] of counts) {
    if (c > bestCount || (c === bestCount && v < best)) {
      best = v;
      bestCount = c;
    }
  }
  return best;
}

function spread(xs) {
  if (xs.length === 0) throw new Error('empty');
  return Math.max(...xs) - Math.min(...xs);
}

function histogram(xs, lo, width, bins) {
  if (width <= 0 || bins <= 0) throw new Error('bad buckets');
  const out = new Array(bins).fill(0);
  for (const x of xs) {
    if (x < lo) continue;
    const i = Math.floor((x - lo) / width);
    if (i < bins) out[i] += 1;
  }
  return out;
}

function trimmedSum(xs, k) {
  if (k < 0 || 2 * k > xs.length) throw new Error('bad k');
  const s = [...xs].sort(byValue);
  return s.slice(k, s.length - k).reduce((a, b) => a + b, 0);
}

module.exports = { meanRound, median2, percentileNr, modeSmallest, spread, histogram, trimmedSum };
''')


def st_cases(rng):
    out = [("mean_round", [[1, 2]]), ("mean_round", [[2, 3]]), ("mean_round", [[-1, -2]]), ("median2", [[3, 1, 2]]), ("median2", [[4, 1, 3, 2]]), ("percentile_nr", [[15, 20, 35, 40, 50], 40]),
           ("mode_smallest", [[3, 1, 3, 1, 2]]), ("histogram", [[1, 5, 9, 10, -3], 0, 5, 2]), ("trimmed_sum", [[5, 1, 4, 2, 3], 1]), ("spread", [[4, -2, 9]])]
    for xs in [[1], [-1], [0], [1, 2, 3], [1, 2, 4], [2, 3, 4], [-2, -3, -4], [-1, -2, -2], [5, 5, 6], [1, 1, 1, 2], [7, 8], [-7, -8], [0, 1], [-1, 0], [1, 4], [3, 4, 4, 4], []]:
        out.append(("mean_round", [xs]))
    for _ in range(20):
        out.append(("mean_round", [[rng.randint(-50, 50) for _ in range(rng.randint(1, 9))]]))
    for xs in [[], [5], [5, 1], [1, 2, 3, 4, 5, 6], [-5, -1, -3], [10, 10], [100, -100, 0, 7]]:
        out.append(("median2", [xs]))
    for _ in range(15):
        out.append(("median2", [[rng.randint(-99, 99) for _ in range(rng.randint(1, 12))]]))
    for xs, p in [([1, 2, 3, 4], 25), ([1, 2, 3, 4], 26), ([1, 2, 3, 4], 100), ([1, 2, 3, 4], 1), ([9], 50), ([9], 1), ([3, 1, 2], 34), ([3, 1, 2], 33), ([], 50), ([1], 0), ([1], 101), ([5, 5, 5, 6], 75), ([5, 5, 5, 6], 76)]:
        out.append(("percentile_nr", [xs, p]))
    for _ in range(15):
        out.append(("percentile_nr", [[rng.randint(-20, 20) for _ in range(rng.randint(1, 15))], rng.randint(1, 100)]))
    for xs in [[], [1], [2, 2, 1, 1], [3, 3, 1, 1, 2], [-5, -5, 4, 4], [7, 8, 9], [0, 0, 0, -1]]:
        out.append(("mode_smallest", [xs]))
    for _ in range(12):
        out.append(("mode_smallest", [[rng.randint(-4, 4) for _ in range(rng.randint(0, 12))]]))
    for xs in [[], [3], [3, 3], [1, 9], [-4, 4], [10, -10, 0]]:
        out.append(("spread", [xs]))
    for xs, lo, w, b in [([], 0, 1, 1), ([0, 1, 2, 3], 0, 2, 2), ([-1, -2, -5, -6], -6, 2, 3), ([-1, 0, 1], 0, 1, 2), ([-1, -3], -4, 3, 1), ([5, 10, 15], 5, 5, 2), ([-10, -1, 0, 9, 10], -5, 5, 4), ([1], 0, 0, 1), ([1], 0, -1, 1), ([1], 0, 1, 0),
                         ([-7, -8, -9, -10], -10, 1, 4), ([-0, -1, -2], -2, 2, 2), ([100, 101], 100, 7, 3), ([-1], 0, 5, 1), ([-5, -4], -5, 10, 1)]:
        out.append(("histogram", [xs, lo, w, b]))
    for _ in range(15):
        out.append(("histogram", [[rng.randint(-30, 30) for _ in range(rng.randint(0, 14))], rng.randint(-20, 5), rng.randint(1, 9), rng.randint(1, 6)]))
    for xs, k in [([5, 1, 4, 2, 3], 0), ([5, 1, 4, 2, 3], 2), ([5, 1, 4, 2, 3], 3), ([5, 1], 1), ([], 0), ([], 1), ([2], 0), ([2], 1), ([4, 4, 4, 4], 2), ([-3, 3, 0, 9, -9], 1), ([1, 2], -1)]:
        out.append(("trimmed_sum", [xs, k]))
    return out


ST = PortLib(
    slug="stats-quarter",
    title="small-integer statistics helpers",
    blurb="A reporting job in a regional library network summarises loan counts without floating point, so the helpers work on integers only.",
    spec=ST_SPEC,
    fns=ST_FNS,
    impls={"python": {"stats_quarter.py": ST_PY}, "go": {"statsquarter.go": ST_GO}, "javascript": {"src/stats_quarter.js": ST_JS}},
    cases=st_cases,
    difficulty=3,
    traps=["round half to even", "floor division in bucketing negative values", "default sort order", "empty inputs"],
    tags=["statistics"],
    pairs=[("python", "go", "full"), ("go", "javascript", "full"), ("javascript", "python", "stub"), ("python", "javascript", "stub")],
)
register_port(ST, __name__)

# ======================================================================================================================
# limit-parse: sizes and durations with i32 limits
# ======================================================================================================================

LP_SPEC = dd('''
    Configuration values for a job runner: byte sizes and durations. Every result is a **signed 32-bit** quantity:
    anything that would exceed `2147483647` is an error, and so is any intermediate overflow in the checked helpers.

    * `parse_size(text)`: 1 to 10 ASCII digits followed by an optional unit, no spaces. Units are case-insensitive:
      none or `b` is 1, `k`/`kb`/`kib` is 1024, `m`/`mb`/`mib` is 1024^2, `g`/`gb`/`gib` is 1024^3. Only the ASCII letters `A-Z`/`a-z`
      are ever folded or accepted as unit letters (no other character, however it lowercases, is a unit). Leading zeros are fine.
      Result above `2147483647`, an unknown unit, no digits or a sign are errors.
    * `fmt_size(n)`: negative is an error; `0` is `0`; otherwise the largest unit among `G`, `M`, `K` that divides `n`
      exactly is used (`2048` is `2K`, `1073741824` is `1G`), otherwise plain digits (`1500` is `1500`).
    * `parse_dur(text)`: one or more `<digits><unit>` parts with unit `d`, `h`, `m` or `s` (lower case only), in strictly
      descending unit order, each unit at most once, each number 1 to 9 ASCII digits: `1d2h3m4s`, `90m`, `45s`. The total
      number of seconds must be at most `2147483647`. Empty text, a number without a unit, a unit without a number, repeated
      or misordered units are errors.
    * `fmt_dur(secs)`: negative is an error; `0` is `0s`; otherwise the non-zero parts from `d` down to `s`
      (`93784` is `1d2h3m4s`, `3600` is `1h`).
    * `add_checked(a, b)`, `mul_checked(a, b)` return the exact result or fail if it does not fit in a signed 32-bit integer;
      `abs_checked(a)` is `|a|` and fails for `-2147483648`.
''')

LP_FNS = [
    Fn("parse_size", [("text", "str")], "int", err=True),
    Fn("fmt_size", [("n", "i32")], "str", err=True),
    Fn("parse_dur", [("text", "str")], "int", err=True),
    Fn("fmt_dur", [("secs", "i32")], "str", err=True),
    Fn("add_checked", [("a", "i32"), ("b", "i32")], "i32", err=True),
    Fn("mul_checked", [("a", "i32"), ("b", "i32")], "i32", err=True),
    Fn("abs_checked", [("a", "i32")], "i32", err=True),
]

LP_PY = dd(r'''
import re

I32_MAX = 2147483647
_SIZE = re.compile(r"([0-9]{1,10})([A-Za-z]*)")
_UNITS = {"": 1, "b": 1, "k": 1024, "kb": 1024, "kib": 1024, "m": 1024 ** 2, "mb": 1024 ** 2, "mib": 1024 ** 2,
          "g": 1024 ** 3, "gb": 1024 ** 3, "gib": 1024 ** 3}
_DUR = re.compile(r"(?:([0-9]{1,9})d)?(?:([0-9]{1,9})h)?(?:([0-9]{1,9})m)?(?:([0-9]{1,9})s)?")


def _fit(v):
    if v < -2147483648 or v > I32_MAX:
        raise OverflowError("does not fit in 32 bits")
    return v


def parse_size(text):
    m = _SIZE.fullmatch(text)
    if not m:
        raise ValueError("bad size")
    unit = _UNITS.get(m.group(2).lower())
    if unit is None:
        raise ValueError("bad unit")
    v = int(m.group(1)) * unit
    if v > I32_MAX:
        raise OverflowError("too large")
    return v


def fmt_size(n):
    if n < 0:
        raise ValueError("negative")
    for unit, name in ((1024 ** 3, "G"), (1024 ** 2, "M"), (1024, "K")):
        if n != 0 and n % unit == 0:
            return "%d%s" % (n // unit, name)
    return str(n)


def parse_dur(text):
    m = _DUR.fullmatch(text)
    if not text or not m:
        raise ValueError("bad duration")
    total = 0
    for g, mult in zip(m.groups(), (86400, 3600, 60, 1)):
        if g is not None:
            total += int(g) * mult
    if total > I32_MAX:
        raise OverflowError("too large")
    return total


def fmt_dur(secs):
    if secs < 0:
        raise ValueError("negative")
    if secs == 0:
        return "0s"
    out = ""
    for mult, unit in ((86400, "d"), (3600, "h"), (60, "m"), (1, "s")):
        q, secs = divmod(secs, mult)
        if q:
            out += "%d%s" % (q, unit)
    return out


def add_checked(a, b):
    return _fit(a + b)


def mul_checked(a, b):
    return _fit(a * b)


def abs_checked(a):
    return _fit(abs(a))
''')

LP_GO = dd(r'''
package limitparse

import (
	"errors"
	"strconv"
	"strings"
)

const i32Max = 2147483647

var errBad = errors.New("limitparse: bad input")
var errOverflow = errors.New("limitparse: does not fit in 32 bits")

func isDigit(c byte) bool { return c >= '0' && c <= '9' }

func asciiLower(s string) string {
	b := []byte(s)
	for i, c := range b {
		if c >= 'A' && c <= 'Z' {
			b[i] = c + 32
		}
	}
	return string(b)
}

func ParseSize(text string) (int64, error) {
	i := 0
	for i < len(text) && isDigit(text[i]) {
		i++
	}
	if i < 1 || i > 10 {
		return 0, errBad
	}
	n, err := strconv.ParseInt(text[:i], 10, 64)
	if err != nil {
		return 0, errBad
	}
	var unit int64
	switch asciiLower(text[i:]) {
	case "", "b":
		unit = 1
	case "k", "kb", "kib":
		unit = 1 << 10
	case "m", "mb", "mib":
		unit = 1 << 20
	case "g", "gb", "gib":
		unit = 1 << 30
	default:
		return 0, errBad
	}
	v := n * unit
	if v > i32Max {
		return 0, errOverflow
	}
	return v, nil
}

func FmtSize(n int32) (string, error) {
	if n < 0 {
		return "", errBad
	}
	for _, u := range []struct {
		size int32
		name string
	}{{1 << 30, "G"}, {1 << 20, "M"}, {1 << 10, "K"}} {
		if n != 0 && n%u.size == 0 {
			return strconv.Itoa(int(n/u.size)) + u.name, nil
		}
	}
	return strconv.Itoa(int(n)), nil
}

func ParseDur(text string) (int64, error) {
	if text == "" {
		return 0, errBad
	}
	units := []byte{'d', 'h', 'm', 's'}
	mult := map[byte]int64{'d': 86400, 'h': 3600, 'm': 60, 's': 1}
	var total int64
	next := 0 // index of the first unit still allowed
	i := 0
	for i < len(text) {
		j := i
		for j < len(text) && isDigit(text[j]) {
			j++
		}
		if j == i || j-i > 9 || j >= len(text) {
			return 0, errBad
		}
		u := text[j]
		k := next
		for k < len(units) && units[k] != u {
			k++
		}
		if k == len(units) {
			return 0, errBad
		}
		n, _ := strconv.ParseInt(text[i:j], 10, 64)
		total += n * mult[u]
		next = k + 1
		i = j + 1
	}
	if total > i32Max {
		return 0, errOverflow
	}
	return total, nil
}

func FmtDur(secs int32) (string, error) {
	if secs < 0 {
		return "", errBad
	}
	if secs == 0 {
		return "0s", nil
	}
	var b strings.Builder
	rest := int64(secs)
	for _, p := range []struct {
		mult int64
		unit string
	}{{86400, "d"}, {3600, "h"}, {60, "m"}, {1, "s"}} {
		if q := rest / p.mult; q > 0 {
			b.WriteString(strconv.FormatInt(q, 10) + p.unit)
			rest -= q * p.mult
		}
	}
	return b.String(), nil
}

func AddChecked(a, b int32) (int32, error) {
	s := int64(a) + int64(b)
	if s > i32Max || s < -2147483648 {
		return 0, errOverflow
	}
	return int32(s), nil
}

func MulChecked(a, b int32) (int32, error) {
	p := int64(a) * int64(b)
	if p > i32Max || p < -2147483648 {
		return 0, errOverflow
	}
	return int32(p), nil
}

func AbsChecked(a int32) (int32, error) {
	if a == -2147483648 {
		return 0, errOverflow
	}
	if a < 0 {
		return -a, nil
	}
	return a, nil
}
''')

LP_JAVA = dd(r'''
public final class LimitParse {
    private LimitParse() {}

    private static final long I32_MAX = 2147483647L;

    private static boolean digit(char c) { return c >= '0' && c <= '9'; }

    private static String asciiLower(String s) {
        StringBuilder b = new StringBuilder();
        for (char c : s.toCharArray()) b.append(c >= 'A' && c <= 'Z' ? (char) (c + 32) : c);
        return b.toString();
    }

    public static long parseSize(String text) {
        int i = 0;
        while (i < text.length() && digit(text.charAt(i))) i++;
        if (i < 1 || i > 10) throw new IllegalArgumentException("bad size");
        long n = Long.parseLong(text.substring(0, i));
        long unit;
        switch (asciiLower(text.substring(i))) {
            case "": case "b": unit = 1; break;
            case "k": case "kb": case "kib": unit = 1L << 10; break;
            case "m": case "mb": case "mib": unit = 1L << 20; break;
            case "g": case "gb": case "gib": unit = 1L << 30; break;
            default: throw new IllegalArgumentException("bad unit");
        }
        long v = n * unit;
        if (v > I32_MAX) throw new ArithmeticException("too large");
        return v;
    }

    public static String fmtSize(int n) {
        if (n < 0) throw new IllegalArgumentException("negative");
        int[] sizes = {1 << 30, 1 << 20, 1 << 10};
        String[] names = {"G", "M", "K"};
        for (int k = 0; k < 3; k++) {
            if (n != 0 && n % sizes[k] == 0) return (n / sizes[k]) + names[k];
        }
        return Integer.toString(n);
    }

    public static long parseDur(String text) {
        if (text.isEmpty()) throw new IllegalArgumentException("bad duration");
        String units = "dhms";
        long[] mult = {86400, 3600, 60, 1};
        long total = 0;
        int next = 0;
        int i = 0;
        while (i < text.length()) {
            int j = i;
            while (j < text.length() && digit(text.charAt(j))) j++;
            if (j == i || j - i > 9 || j >= text.length()) throw new IllegalArgumentException("bad duration");
            int k = units.indexOf(text.charAt(j));
            if (k < next) throw new IllegalArgumentException("bad unit order");
            total += Long.parseLong(text.substring(i, j)) * mult[k];
            next = k + 1;
            i = j + 1;
        }
        if (total > I32_MAX) throw new ArithmeticException("too large");
        return total;
    }

    public static String fmtDur(int secs) {
        if (secs < 0) throw new IllegalArgumentException("negative");
        if (secs == 0) return "0s";
        long[] mult = {86400, 3600, 60, 1};
        String[] names = {"d", "h", "m", "s"};
        StringBuilder b = new StringBuilder();
        long rest = secs;
        for (int k = 0; k < 4; k++) {
            long q = rest / mult[k];
            if (q > 0) {
                b.append(q).append(names[k]);
                rest -= q * mult[k];
            }
        }
        return b.toString();
    }

    public static int addChecked(int a, int b) { return Math.addExact(a, b); }

    public static int mulChecked(int a, int b) { return Math.multiplyExact(a, b); }

    public static int absChecked(int a) {
        if (a == Integer.MIN_VALUE) throw new ArithmeticException("overflow");
        return Math.abs(a);
    }
}
''')


def lp_cases(rng):
    out = [("parse_size", ["4k"]), ("parse_size", ["512"]), ("parse_size", ["2GiB"]), ("parse_size", ["2G"]), ("fmt_size", [2048]), ("fmt_size", [1500]), ("parse_dur", ["1d2h3m4s"]), ("fmt_dur", [93784]),
           ("add_checked", [2147483647, 1]), ("mul_checked", [65536, 32768])]
    for s in ["0", "1", "1B", "1b", "4k", "4K", "4kb", "4KB", "4KiB", "4kIb", "10m", "10MiB", "1g", "1G", "2g", "2147483647", "2147483648", "2097151k", "2097152k", "2047m", "2048m", "1024m", "0g", "0000000012", "0000000000012",
              "12345678901", "99999999999", "", "k", "-1", "+1", "1 k", " 1", "1k ", "1x", "1kk", "1kbb", "1.5k", "1e3", "0x10", "1_0", "١٢", "1K", "1KIB", "1Kb", "2g1", "1ib", "1t", "1tb"]:
        out.append(("parse_size", [s]))
    for n in [0, 1, 1023, 1024, 1025, 2048, 3072, 1048576, 1048577, 2097152, 1073741824, 2147483647, 2146435072, 3 * 1048576 + 1024, 5 * 1073741824 // 5, 1536, -1, -2147483648]:
        out.append(("fmt_size", [n]))
    for s in ["1s", "0s", "59s", "60s", "1m", "1m1s", "90m", "1h", "1h30m", "24h", "1d", "1d1s", "1d2h3m4s", "30d", "24855d", "24855d3h14m7s", "24855d3h14m8s", "24856d", "99999d", "999999999s", "2147483647s", "2147483648s",
              "", "s", "1", "1x", "1S", "1D", "1s1m", "1m1h", "1h1h", "1d1d", "5m5m", "1h 1m", " 1h", "1h ", "01h", "0000000001s", "0000000000001s", "1.5h", "-1s", "+1s", "1hm", "1h2", "h1", "1d2h3m4s5", "0d0h0m0s", "0s0s"]:
        out.append(("parse_dur", [s]))
    for n in [0, 1, 59, 60, 61, 3599, 3600, 3601, 86399, 86400, 86401, 90061, 93784, 2147483647, 172800, 7200, 2147483640, -1, -2147483648]:
        out.append(("fmt_dur", [n]))
    for a, b in [(1, 2), (2147483647, 0), (2147483647, 1), (-2147483648, -1), (-2147483648, 0), (-2147483647, -1), (-2147483647, -2), (1073741824, 1073741823), (1073741824, 1073741824), (-1073741824, -1073741824), (-1073741824, -1073741825),
                 (0, 0), (5, -9)]:
        out.append(("add_checked", [a, b]))
    for a, b in [(46340, 46340), (46341, 46341), (-46341, 46341), (65536, 32768), (65536, -32768), (65536, 65536), (-65536, 32768), (-1, -2147483648), (-1, 2147483647), (0, 2147483647), (2147483647, 1), (2, 1073741823), (2, 1073741824), (2, -1073741824), (2, -1073741825),
                 (-2147483648, 1), (-2147483648, -1), (-2147483648, 0), (3, 715827883), (3, 715827882), (-3, 715827883), (-3, 715827882)]:
        out.append(("mul_checked", [a, b]))
    for a in [0, 1, -1, 2147483647, -2147483647, -2147483648, 12345, -12345]:
        out.append(("abs_checked", [a]))
    for _ in range(10):
        out.append(("add_checked", [rng.randint(-2**31, 2**31 - 1), rng.randint(-2**31, 2**31 - 1)]))
        out.append(("mul_checked", [rng.randint(-100000, 100000), rng.randint(-100000, 100000)]))
    return out


LP = PortLib(
    slug="limit-parse",
    title="size and duration limits parser",
    blurb="A job runner reads memory sizes and time limits from its configuration and must reject values that do not fit in a signed 32-bit field.",
    spec=LP_SPEC,
    fns=LP_FNS,
    impls={"python": {"limit_parse.py": LP_PY}, "go": {"limitparse.go": LP_GO}, "java": {"LimitParse.java": LP_JAVA}},
    cases=lp_cases,
    difficulty=3,
    traps=["checked 32-bit arithmetic", "strict grammar with units", "unbounded vs fixed-width integers", "error idioms"],
    tags=["checked-arithmetic", "strict-parsing"],
    pairs=[("python", "go", "full"), ("go", "java", "full"), ("java", "python", "stub"), ("python", "java", "stub")],
)
register_port(LP, __name__)
