"""Port libraries about money, rounding and numeric codecs (rounding modes, remainders, checked arithmetic)."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

# ======================================================================================================================
# cents-share: co-op bill splitting
# ======================================================================================================================

SHARE_SPEC = dd('''
    All money is a whole number of **cents** (an `int`, may be negative). No floating point anywhere.

    * `round_div(n, d)` is `n / d` rounded to the nearest integer; an exact half rounds **away from zero** (`7/2` is `4`,
      `-7/2` is `-4`, `5/10` is `1`, `-5/10` is `-1`). `d == 0` is an error. The sign of `d` matters like in ordinary arithmetic.
    * `pct_of(amount, bp)` is `round_div(amount * bp, 10000)`: `bp` are basis points and may be negative.
    * `split_by_weight(total, weights)` shares `total` out in proportion to the non-negative integer `weights` by the
      **largest remainder** method, working on the magnitude of `total`: first every entry gets `floor(|total| * w / S)`
      where `S` is the sum of the weights; the cents still undistributed are handed out one each to the entries with the
      largest remainder `(|total| * w) mod S`, ties going to the **lower index**. The sign of `total` is applied at the
      end, so shares of a negative total are negative. An empty list, a negative weight or `S == 0` is an error.
    * `tier_fee(amount, tiers)`: a progressive fee. `tiers` is `[l1, r1, l2, r2, ..., rK]` (odd length): the slice of
      `amount` up to `l1` is charged at `r1` basis points, the slice from `l1` up to `l2` at `r2`, ..., and everything above
      the last limit at `rK`. Every slice's fee is rounded separately with `round_div(slice * rate, 10000)` and the fees are
      added. Limits must be positive and strictly increasing; `amount < 0` is an error; an even length is an error.
    * `fmt_money(cents)` writes `[-]W.CC` where `W` has a comma between every group of three digits: `123456` is
      `1,234.56`, `5` is `0.05`, `-100000` is `-1,000.00`, `0` is `0.00`.
    * `parse_money(text)` reads exactly what `fmt_money` can write, plus the same number without commas, plus the
      decimals may be left out (`12` and `1,200` are `1200` and `120000` cents); everything else is an error: a lone `-`
      with no digits, decimals other than exactly two, misplaced commas (`12,34`, `1,2345`, `,500`), leading zeros
      (`007`), spaces, a `+` sign. `-0.00` is `0`. More than 13 digits before the decimal point is an error.
''')

SHARE_FNS = [
    Fn("round_div", [("n", "int"), ("d", "int")], "int", err=True),
    Fn("pct_of", [("amount", "int"), ("bp", "int")], "int"),
    Fn("split_by_weight", [("total", "int"), ("weights", "list<int>")], "list<int>", err=True),
    Fn("tier_fee", [("amount", "int"), ("tiers", "list<int>")], "int", err=True),
    Fn("fmt_money", [("cents", "int")], "str"),
    Fn("parse_money", [("text", "str")], "int", err=True),
]

SHARE_PY = dd(r'''
import re

_MONEY = re.compile(r"(-?)(0|[1-9][0-9]{0,2}(?:,[0-9]{3})+|[1-9][0-9]*)(?:\.([0-9]{2}))?")


def round_div(n, d):
    if d == 0:
        raise ValueError("division by zero")
    sign = -1 if (n < 0) != (d < 0) else 1
    n, d = abs(n), abs(d)
    return sign * ((2 * n + d) // (2 * d))


def pct_of(amount, bp):
    return round_div(amount * bp, 10000)


def split_by_weight(total, weights):
    s = sum(weights)
    if not weights or s <= 0 or any(w < 0 for w in weights):
        raise ValueError("bad weights")
    mag = abs(total)
    shares = [mag * w // s for w in weights]
    rems = [mag * w % s for w in weights]
    left = mag - sum(shares)
    for i in sorted(range(len(weights)), key=lambda i: (-rems[i], i))[:left]:
        shares[i] += 1
    sign = -1 if total < 0 else 1
    return [sign * x for x in shares]


def tier_fee(amount, tiers):
    if amount < 0 or len(tiers) % 2 == 0:
        raise ValueError("bad tiers")
    limits = tiers[0:len(tiers) - 1:2]
    rates = tiers[1:len(tiers) - 1:2] + [tiers[-1]]
    prev = 0
    for lim in limits:
        if lim <= prev:
            raise ValueError("limits must be positive and increasing")
        prev = lim
    fee, prev = 0, 0
    for k, rate in enumerate(rates):
        top = amount if k == len(limits) else min(amount, limits[k])
        fee += round_div(max(0, top - prev) * rate, 10000)
        if k < len(limits):
            prev = limits[k]
    return fee


def fmt_money(cents):
    whole, frac = divmod(abs(cents), 100)
    return "%s%s.%02d" % ("-" if cents < 0 else "", format(whole, ","), frac)


def parse_money(text):
    m = _MONEY.fullmatch(text)
    if not m:
        raise ValueError("bad money text")
    digits = m.group(2).replace(",", "")
    if len(digits) > 13:
        raise ValueError("too large")
    v = int(digits) * 100 + (int(m.group(3)) if m.group(3) else 0)
    return -v if m.group(1) else v
''')

SHARE_JAVA = dd(r'''
import java.util.*;

public final class CentsShare {
    private CentsShare() {}

    public static long roundDiv(long n, long d) {
        if (d == 0) throw new IllegalArgumentException("division by zero");
        long sign = (n < 0) != (d < 0) ? -1 : 1;
        long an = Math.abs(n), ad = Math.abs(d);
        return sign * ((2 * an + ad) / (2 * ad));
    }

    public static long pctOf(long amount, long bp) {
        return roundDiv(amount * bp, 10000);
    }

    public static List<Long> splitByWeight(long total, List<Long> weights) {
        long s = 0;
        for (long w : weights) {
            if (w < 0) throw new IllegalArgumentException("bad weights");
            s += w;
        }
        if (weights.isEmpty() || s <= 0) throw new IllegalArgumentException("bad weights");
        long mag = Math.abs(total);
        int n = weights.size();
        long[] shares = new long[n];
        final long[] rems = new long[n];
        long given = 0;
        for (int i = 0; i < n; i++) {
            shares[i] = mag * weights.get(i) / s;
            rems[i] = mag * weights.get(i) % s;
            given += shares[i];
        }
        long left = mag - given;
        Integer[] order = new Integer[n];
        for (int i = 0; i < n; i++) order[i] = i;
        Arrays.sort(order, (a, b) -> rems[a] != rems[b] ? Long.compare(rems[b], rems[a]) : Integer.compare(a, b));
        for (int k = 0; k < left; k++) shares[order[k]]++;
        List<Long> out = new ArrayList<>();
        for (long x : shares) out.add(total < 0 ? -x : x);
        return out;
    }

    public static long tierFee(long amount, List<Long> tiers) {
        int n = tiers.size();
        if (amount < 0 || n % 2 == 0) throw new IllegalArgumentException("bad tiers");
        int k = n / 2;
        long[] limits = new long[k];
        long[] rates = new long[k + 1];
        long prev = 0;
        for (int i = 0; i < k; i++) {
            limits[i] = tiers.get(2 * i);
            rates[i] = tiers.get(2 * i + 1);
            if (limits[i] <= prev) throw new IllegalArgumentException("limits must be positive and increasing");
            prev = limits[i];
        }
        rates[k] = tiers.get(n - 1);
        long fee = 0;
        prev = 0;
        for (int i = 0; i <= k; i++) {
            long top = i == k ? amount : Math.min(amount, limits[i]);
            fee += roundDiv(Math.max(0, top - prev) * rates[i], 10000);
            if (i < k) prev = limits[i];
        }
        return fee;
    }

    public static String fmtMoney(long cents) {
        long mag = Math.abs(cents);
        String whole = Long.toString(mag / 100);
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < whole.length(); i++) {
            if (i > 0 && (whole.length() - i) % 3 == 0) b.append(',');
            b.append(whole.charAt(i));
        }
        long frac = mag % 100;
        return (cents < 0 ? "-" : "") + b + "." + (frac < 10 ? "0" : "") + frac;
    }

    public static long parseMoney(String text) {
        int i = 0, n = text.length();
        boolean neg = false;
        if (i < n && text.charAt(i) == '-') { neg = true; i++; }
        int ws = i;
        while (i < n && text.charAt(i) >= '0' && text.charAt(i) <= '9') i++;
        int firstLen = i - ws;
        if (firstLen == 0) throw new IllegalArgumentException("bad money text");
        StringBuilder digits = new StringBuilder(text.substring(ws, i));
        if (i < n && text.charAt(i) == ',') {
            if (firstLen > 3 || text.charAt(ws) == '0') throw new IllegalArgumentException("bad grouping");
            while (i < n && text.charAt(i) == ',') {
                if (i + 3 >= n) throw new IllegalArgumentException("bad grouping");
                for (int k = 1; k <= 3; k++) {
                    char c = text.charAt(i + k);
                    if (c < '0' || c > '9') throw new IllegalArgumentException("bad grouping");
                    digits.append(c);
                }
                i += 4;
            }
        } else if (firstLen > 1 && text.charAt(ws) == '0') {
            throw new IllegalArgumentException("leading zero");
        }
        long frac = 0;
        if (i < n && text.charAt(i) == '.') {
            if (n - i != 3) throw new IllegalArgumentException("bad decimals");
            char a = text.charAt(i + 1), b = text.charAt(i + 2);
            if (a < '0' || a > '9' || b < '0' || b > '9') throw new IllegalArgumentException("bad decimals");
            frac = (a - '0') * 10 + (b - '0');
            i = n;
        }
        if (i != n) throw new IllegalArgumentException("trailing text");
        if (digits.length() > 13) throw new IllegalArgumentException("too large");
        long v = Long.parseLong(digits.toString()) * 100 + frac;
        return neg ? -v : v;
    }
}
''')

SHARE_JS = dd(r'''
'use strict';

function roundDiv(n, d) {
  if (d === 0) throw new Error('division by zero');
  const sign = (n < 0) !== (d < 0) ? -1 : 1;
  const an = Math.abs(n);
  const ad = Math.abs(d);
  const num = 2 * an + ad;
  const den = 2 * ad;
  return sign * ((num - (num % den)) / den);
}

function pctOf(amount, bp) {
  return roundDiv(amount * bp, 10000);
}

function splitByWeight(total, weights) {
  let s = 0;
  for (const w of weights) {
    if (w < 0) throw new Error('bad weights');
    s += w;
  }
  if (weights.length === 0 || s <= 0) throw new Error('bad weights');
  const mag = Math.abs(total);
  const shares = weights.map((w) => (mag * w - ((mag * w) % s)) / s);
  const rems = weights.map((w) => (mag * w) % s);
  const left = mag - shares.reduce((a, b) => a + b, 0);
  const order = weights.map((_w, i) => i).sort((a, b) => rems[b] - rems[a] || a - b);
  for (let k = 0; k < left; k++) shares[order[k]] += 1;
  return shares.map((x) => (total < 0 ? -x : x) + 0);
}

function tierFee(amount, tiers) {
  const n = tiers.length;
  if (amount < 0 || n % 2 === 0) throw new Error('bad tiers');
  const limits = [];
  const rates = [];
  let prev = 0;
  for (let i = 0; i + 1 < n; i += 2) {
    if (tiers[i] <= prev) throw new Error('limits must be positive and increasing');
    prev = tiers[i];
    limits.push(tiers[i]);
    rates.push(tiers[i + 1]);
  }
  rates.push(tiers[n - 1]);
  let fee = 0;
  prev = 0;
  for (let k = 0; k < rates.length; k++) {
    const top = k === limits.length ? amount : Math.min(amount, limits[k]);
    fee += roundDiv(Math.max(0, top - prev) * rates[k], 10000);
    if (k < limits.length) prev = limits[k];
  }
  return fee;
}

function fmtMoney(cents) {
  const mag = Math.abs(cents);
  const whole = String((mag - (mag % 100)) / 100).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const frac = mag % 100;
  return (cents < 0 ? '-' : '') + whole + '.' + (frac < 10 ? '0' : '') + frac;
}

function parseMoney(text) {
  const m = /^(-?)(0|[1-9][0-9]{0,2}(?:,[0-9]{3})+|[1-9][0-9]*)(?:\.([0-9]{2}))?$/.exec(text);
  if (!m) throw new Error('bad money text');
  const digits = m[2].replace(/,/g, '');
  if (digits.length > 13) throw new Error('too large');
  const v = Number(digits) * 100 + (m[3] ? Number(m[3]) : 0);
  return m[1] ? -v : v;
}

module.exports = { roundDiv, pctOf, splitByWeight, tierFee, fmtMoney, parseMoney };
''')


def share_cases(rng):
    out = [
        ("round_div", [7, 2]), ("round_div", [-7, 2]), ("round_div", [5, 10]), ("round_div", [-5, 10]),
        ("split_by_weight", [100, [1, 1, 1]]), ("split_by_weight", [-100, [1, 1, 1]]),
        ("tier_fee", [1000, [500, 100, 5]]), ("fmt_money", [123456]), ("fmt_money", [-5]), ("parse_money", ["1,234.56"]),
    ]
    for n, d in [(1, 2), (-1, 2), (1, -2), (-1, -2), (3, 2), (-3, 2), (2, 4), (0, 5), (0, -5), (9, 3), (-9, 3), (10, 4), (-10, 4), (10, -4), (11, 4), (1, 3),
                 (2, 3), (-2, 3), (1000001, 2000000), (5, 0), (0, 0), (-5, 0)]:
        out.append(("round_div", [n, d]))
    for _ in range(25):
        out.append(("round_div", [rng.randint(-10**9, 10**9), rng.choice([-7, -3, -2, 1, 2, 3, 4, 6, 7, 8, 10, 100, 997])]))
    for amount, bp in [(1000, 250), (-1000, 250), (1000, -250), (1, 5000), (1, 4999), (-1, 5000), (-1, 4999), (999, 1), (0, 777), (123456789, 1234)]:
        out.append(("pct_of", [amount, bp]))
    for _ in range(12):
        out.append(("pct_of", [rng.randint(-10**8, 10**8), rng.randint(-20000, 20000)]))
    for total, w in [(100, [1, 1, 1]), (-100, [1, 1, 1]), (101, [1, 1, 1]), (1, [1, 1, 1]), (0, [3, 4]), (7, [0, 5, 0]), (10, [2, 2, 1]), (5, [1, 1, 1, 1, 1, 1, 1]),
                     (1000, [333, 333, 334]), (-7, [5, 3]), (99, [1, 2, 3, 4]), (3, [1, 0, 1]), (1, [0, 2, 2]), (10, []), (10, [0, 0]), (10, [-1, 2]), (10, [4])]:
        out.append(("split_by_weight", [total, w]))
    for _ in range(25):
        k = rng.randint(1, 7)
        out.append(("split_by_weight", [rng.randint(-100000, 100000), [rng.choice([0, 1, 2, 3, 5, 8, 13, 100, 999]) for _ in range(k)]]))
    tiers_pool = [[500, 100, 5], [100, 0, 1000, 250, 400], [10, 10000, 20, 5000, 30, 2500, 1250], [999], [1, 1, 1], [50, 333, 60, 77, 5], [100, 50, 100, 60, 7], [0, 5, 3],
                  [100, 50], [100, 50, 90, 60, 7], [5, 5, 3]]
    for tiers in tiers_pool:
        for amount in [0, 1, 99, 100, 101, 500, 501, 12345, -1]:
            out.append(("tier_fee", [amount, tiers]))
    for _ in range(10):
        out.append(("tier_fee", [rng.randint(0, 3000000), [rng.randint(1, 1000) * 100, rng.randint(0, 900), rng.randint(1001, 9000) * 100, rng.randint(0, 900), rng.randint(0, 900)]]))
    for c in [0, 5, 99, 100, 101, 999, 1000, 99999, 100000, 123456, 1000000, 100000000, -1, -5, -100000, -123456789, 9007199254740991, -9007199254740991, 123456789012]:
        out.append(("fmt_money", [c]))
    for _ in range(15):
        out.append(("fmt_money", [rng.randint(-10**11, 10**11)]))
    for s in ["0", "0.00", "-0.00", "-0", "12", "1,200", "1,234.56", "-1,234.56", "1234.56", "-1234.56", "999,999,999.99", "1,000", "100", "100.5", "100.50", "1.5", "1.", ".50", "-", "-.5",
              "12,34", "1,2345", ",500", "1,23", "007", "0,100", "00.50", "+5", "5 ", " 5", "1 000", "1,000,00", "1,000,000.00", "12345678901234", "1234567890123", "1,234,567,890,123.00", "9999999999999.99",
              "１２", "12.345", "12.3", "1e3", "", "1,000.0", "-1,000", "-,100", "--1", "0.5", "0.05", "0,5"]:
        out.append(("parse_money", [s]))
    return out


SHARE = PortLib(
    slug="cents-share",
    title="bill splitting and rounding helpers",
    blurb="A housing co-op's accounting tool splits shared bills between members, applies tiered handling fees and prints amounts in cents-exact text.",
    spec=SHARE_SPEC,
    fns=SHARE_FNS,
    impls={"python": {"cents_share.py": SHARE_PY}, "java": {"CentsShare.java": SHARE_JAVA}, "javascript": {"src/cents_share.js": SHARE_JS}},
    cases=share_cases,
    difficulty=3,
    traps=["round half away from zero (not banker's, not half-up)", "largest remainder with index tie-break", "negative totals", "strict text grammar", "integer division semantics"],
    tags=["rounding", "money"],
    pairs=[("python", "java", "full"), ("python", "javascript", "full"), ("java", "javascript", "stub"), ("javascript", "python", "stub")],
)
register_port(SHARE, __name__)
