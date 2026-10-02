"""Port libraries about fixed-width integers and bit manipulation (wrap-around, shifts, unsigned order)."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

# ======================================================================================================================
# shelf-hash: rendezvous placement with 32-bit hashes
# ======================================================================================================================

SH_SPEC = dd('''
    Rendezvous ("highest score wins") placement of keys on nodes, using unsigned **32-bit** arithmetic that wraps
    around (all products are taken modulo 2^32, shifts are logical).

    * `fnv32(text)`: the FNV-1a hash of the **UTF-8 bytes** of `text`: start with `h = 2166136261`; for every byte `b`:
      `h = h XOR b`, then `h = (h * 16777619) mod 2^32`.
    * `mix32(x)`: the finaliser `h = x; h ^= h >> 15; h = h * 0x2C1B3C6D; h ^= h >> 12; h = h * 0x297A2D39; h ^= h >> 15`
      (products mod 2^32).
    * `score(key, node)` is `mix32(fnv32(key) XOR mix32(fnv32(node)))`; scores are compared as **unsigned** numbers.
    * `place(key, nodes)` is the node with the highest score; on equal scores the node that comes **first in the
      list** wins. An empty list gives *absent*.
    * `place_n(key, nodes, n)` is the `n` best nodes in order of descending score, equal scores in list order. Every
      list position counts once, so a node listed twice may appear twice. `n < 0` is an error; `n` larger than the list
      returns the whole list ordered.
    * `bucket(key, buckets)` is `fnv32(key) mod buckets`; `buckets` must be between 1 and 4294967295 (else error).
''')

SH_FNS = [
    Fn("fnv32", [("text", "str")], "u32"),
    Fn("mix32", [("x", "u32")], "u32"),
    Fn("score", [("key", "str"), ("node", "str")], "u32"),
    Fn("place", [("key", "str"), ("nodes", "list<str>")], "opt<str>"),
    Fn("place_n", [("key", "str"), ("nodes", "list<str>"), ("n", "int")], "list<str>", err=True),
    Fn("bucket", [("key", "str"), ("buckets", "int")], "int", err=True),
]

SH_PY = dd(r'''
M32 = 0xFFFFFFFF


def fnv32(text):
    h = 2166136261
    for b in text.encode("utf-8"):
        h = ((h ^ b) * 16777619) & M32
    return h


def mix32(x):
    h = x & M32
    h ^= h >> 15
    h = (h * 0x2C1B3C6D) & M32
    h ^= h >> 12
    h = (h * 0x297A2D39) & M32
    h ^= h >> 15
    return h


def score(key, node):
    return mix32(fnv32(key) ^ mix32(fnv32(node)))


def place(key, nodes):
    best, best_score = None, -1
    for node in nodes:
        s = score(key, node)
        if s > best_score:
            best, best_score = node, s
    return best


def place_n(key, nodes, n):
    if n < 0:
        raise ValueError("n must not be negative")
    scores = [score(key, node) for node in nodes]
    order = sorted(range(len(nodes)), key=lambda i: (-scores[i], i))
    return [nodes[i] for i in order[:n]]


def bucket(key, buckets):
    if buckets < 1 or buckets > M32:
        raise ValueError("bad bucket count")
    return fnv32(key) % buckets
''')

SH_JS = dd(r'''
'use strict';

function fnv32(text) {
  let h = 2166136261;
  for (const b of Buffer.from(text, 'utf8')) {
    h = Math.imul(h ^ b, 16777619) >>> 0;
  }
  return h;
}

function mix32(x) {
  let h = x >>> 0;
  h = (h ^ (h >>> 15)) >>> 0;
  h = Math.imul(h, 0x2c1b3c6d) >>> 0;
  h = (h ^ (h >>> 12)) >>> 0;
  h = Math.imul(h, 0x297a2d39) >>> 0;
  h = (h ^ (h >>> 15)) >>> 0;
  return h;
}

function score(key, node) {
  return mix32((fnv32(key) ^ mix32(fnv32(node))) >>> 0);
}

function place(key, nodes) {
  let best = null;
  let bestScore = -1;
  for (const node of nodes) {
    const s = score(key, node);
    if (s > bestScore) {
      best = node;
      bestScore = s;
    }
  }
  return best;
}

function placeN(key, nodes, n) {
  if (n < 0) throw new Error('n must not be negative');
  const scored = nodes.map((node, i) => ({ node, i, s: score(key, node) }));
  scored.sort((a, b) => (a.s === b.s ? a.i - b.i : b.s - a.s));
  return scored.slice(0, n).map((e) => e.node);
}

function bucket(key, buckets) {
  if (buckets < 1 || buckets > 4294967295) throw new Error('bad bucket count');
  return fnv32(key) % buckets;
}

module.exports = { fnv32, mix32, score, place, placeN, bucket };
''')

SH_JAVA = dd(r'''
import java.nio.charset.StandardCharsets;
import java.util.*;

public final class ShelfHash {
    private ShelfHash() {}

    public static long fnv32(String text) {
        int h = (int) 2166136261L;
        for (byte b : text.getBytes(StandardCharsets.UTF_8)) {
            h ^= (b & 0xFF);
            h *= 16777619;
        }
        return h & 0xFFFFFFFFL;
    }

    public static long mix32(long x) {
        int h = (int) x;
        h ^= h >>> 15;
        h *= 0x2C1B3C6D;
        h ^= h >>> 12;
        h *= 0x297A2D39;
        h ^= h >>> 15;
        return h & 0xFFFFFFFFL;
    }

    public static long score(String key, String node) {
        return mix32((fnv32(key) ^ mix32(fnv32(node))) & 0xFFFFFFFFL);
    }

    public static String place(String key, List<String> nodes) {
        String best = null;
        long bestScore = -1;
        for (String node : nodes) {
            long s = score(key, node);
            if (s > bestScore) {
                best = node;
                bestScore = s;
            }
        }
        return best;
    }

    public static List<String> placeN(String key, List<String> nodes, long n) {
        if (n < 0) throw new IllegalArgumentException("n must not be negative");
        final long[] scores = new long[nodes.size()];
        Integer[] order = new Integer[nodes.size()];
        for (int i = 0; i < scores.length; i++) {
            scores[i] = score(key, nodes.get(i));
            order[i] = i;
        }
        Arrays.sort(order, (a, b) -> scores[a] != scores[b] ? Long.compare(scores[b], scores[a]) : Integer.compare(a, b));
        List<String> out = new ArrayList<>();
        for (int i = 0; i < order.length && i < n; i++) out.add(nodes.get(order[i]));
        return out;
    }

    public static long bucket(String key, long buckets) {
        if (buckets < 1 || buckets > 4294967295L) throw new IllegalArgumentException("bad bucket count");
        return fnv32(key) % buckets;
    }
}
''')


def sh_cases(rng):
    words = ["alpha", "beta", "gamma", "delta", "eps", "zeta", "été", "中文", "node-\U0001F600", "", "n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8"]
    out = [("fnv32", ["a"]), ("fnv32", [""]), ("mix32", [1]), ("score", ["k", "n"]), ("place", ["key", ["a", "b", "c"]]), ("place_n", ["key", ["a", "b", "c"], 2]), ("bucket", ["key", 10])]
    for t in ["", "a", "b", "foobar", "hello world", "é", "中文", "\U0001F600", "á", "\x00", "\x7f\x80", "The quick brown fox jumps over the lazy dog", "ÿĀ", "￿", "k" * 100]:
        out.append(("fnv32", [t]))
    for x in [0, 1, 2, 0xFF, 0x8000, 0x7FFFFFFF, 0x80000000, 0x80000001, 0xFFFFFFFF, 0xDEADBEEF, 0x12345678, 0xCAFEBABE]:
        out.append(("mix32", [x]))
    for _ in range(10):
        out.append(("mix32", [rng.randint(0, 2**32 - 1)]))
    for _ in range(14):
        out.append(("score", [rng.choice(words), rng.choice(words)]))
    nodes_sets = [[], ["a"], ["a", "b"], ["n1", "n2", "n3", "n4", "n5"], ["x", "x", "x"], ["a", "b", "a"], ["été", "中文", "node-\U0001F600", ""], ["n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8"]]
    keys = ["user:1", "user:2", "user:3", "", "k", "é", "session-\U0001F600", "a" * 40, "order/1001", "order/1002"]
    for ns in nodes_sets:
        for k in rng.sample(keys, 4):
            out.append(("place", [k, ns]))
    for ns in nodes_sets:
        for k in rng.sample(keys, 2):
            for n in [0, 1, 2, 3, 100]:
                out.append(("place_n", [k, ns, n]))
    out.append(("place_n", ["k", ["a", "b"], -1]))
    for _ in range(15):
        out.append(("bucket", [rng.choice(keys) + str(rng.randint(0, 999)), rng.choice([1, 2, 3, 7, 10, 64, 100, 1000, 65537, 2**31 - 1, 2**31, 2**32 - 1])]))
    for b in [0, -1, 2**32, 2**32 + 5]:
        out.append(("bucket", ["key", b]))
    return out


SH = PortLib(
    slug="shelf-hash",
    title="rendezvous hashing on 32-bit hashes",
    blurb="A warehouse-routing service decides which sorting node handles a parcel key; the decision has to be identical in every service, whatever it is written in.",
    spec=SH_SPEC,
    fns=SH_FNS,
    impls={"python": {"shelf_hash.py": SH_PY}, "javascript": {"src/shelf_hash.js": SH_JS}, "java": {"ShelfHash.java": SH_JAVA}},
    cases=sh_cases,
    difficulty=3,
    traps=["u32 wrap-around multiplication", "unsigned comparison", "UTF-8 bytes", "stable ordering of ties"],
    tags=["hashing", "u32"],
    pairs=[("python", "javascript", "full"), ("javascript", "java", "full"), ("java", "python", "stub"), ("python", "java", "stub")],
)
register_port(SH, __name__)

# ======================================================================================================================
# pack-stamp: bit-packed timestamps
# ======================================================================================================================

PS_SPEC = dd('''
    A telemetry format stores a timestamp and five flag bits in one **unsigned 32-bit word**. From the most significant
    bit down: `year - 2000` (7 bits, so years 2000..2127), `month` (4 bits, 1..12), `day` (5 bits), `hour` (5 bits, 0..23),
    `minute` (6 bits, 0..59), `flags` (5 bits, 0..31). So `word = (year-2000)<<25 | month<<21 | day<<16 | hour<<11 | minute<<5 | flags`;
    years from 2064 on set the top bit of the word.

    The calendar of this format has **no leap years**: months have 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 days and
    every year has 365 days.

    * `pack(year, month, day, hour, minute, flags)` builds the word; any field out of range (including a day that does not
      exist in that month) is an error.
    * `unpack(word)` returns `[year, month, day, hour, minute, flags]` (year is the full year); a word whose fields are not a valid
      date and time (month 0 or above 12, day 0 or too large for the month, hour above 23, minute above 59) is an error.
    * `add_minutes(word, delta)` moves the timestamp by `delta` minutes (negative goes back), keeping the flags. The word must be
      valid; a result before 2000-01-01 00:00 or after 2127-12-31 23:59 is an error.
    * `compare(a, b)` orders two valid words chronologically, ignoring flags: `-1`, `0` or `1`. Either word invalid is an error.
    * `has_flag(word, bit)` tells whether flag bit `bit` (0 is the least significant bit of the word, up to 4) is set;
      `set_flag(word, bit, on)` returns the word with that bit set or cleared and everything else untouched (the date fields are not
      validated by these two). A `bit` outside 0..4 is an error.
''')

PS_FNS = [
    Fn("pack", [("year", "int"), ("month", "int"), ("day", "int"), ("hour", "int"), ("minute", "int"), ("flags", "int")], "u32", err=True),
    Fn("unpack", [("word", "u32")], "list<int>", err=True),
    Fn("add_minutes", [("word", "u32"), ("delta", "int")], "u32", err=True),
    Fn("compare", [("a", "u32"), ("b", "u32")], "i32", err=True),
    Fn("has_flag", [("word", "u32"), ("bit", "int")], "bool", err=True),
    Fn("set_flag", [("word", "u32"), ("bit", "int"), ("on", "bool")], "u32", err=True),
]

PS_PY = dd(r'''
_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _valid(year, month, day, hour, minute, flags):
    return (2000 <= year <= 2127 and 1 <= month <= 12 and 1 <= day <= _DAYS[month - 1]
            and 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= flags <= 31)


def pack(year, month, day, hour, minute, flags):
    if not _valid(year, month, day, hour, minute, flags):
        raise ValueError("field out of range")
    return ((year - 2000) << 25) | (month << 21) | (day << 16) | (hour << 11) | (minute << 5) | flags


def unpack(word):
    f = [2000 + (word >> 25), (word >> 21) & 15, (word >> 16) & 31, (word >> 11) & 31, (word >> 5) & 63, word & 31]
    if f[1] < 1 or f[1] > 12 or not _valid(*f):
        raise ValueError("invalid word")
    return f


def _minutes(f):
    doy = sum(_DAYS[:f[1] - 1]) + f[2] - 1
    return (((f[0] - 2000) * 365 + doy) * 24 + f[3]) * 60 + f[4]


def add_minutes(word, delta):
    f = unpack(word)
    total = _minutes(f) + delta
    if total < 0:
        raise ValueError("before the epoch")
    days, rem = divmod(total, 1440)
    year_off, doy = divmod(days, 365)
    if year_off > 127:
        raise ValueError("after the last year")
    month = 1
    while doy >= _DAYS[month - 1]:
        doy -= _DAYS[month - 1]
        month += 1
    return pack(2000 + year_off, month, doy + 1, rem // 60, rem % 60, f[5])


def compare(a, b):
    x, y = unpack(a)[:5], unpack(b)[:5]
    return (x > y) - (x < y)


def has_flag(word, bit):
    if bit < 0 or bit > 4:
        raise ValueError("bad bit")
    return (word >> bit) & 1 == 1


def set_flag(word, bit, on):
    if bit < 0 or bit > 4:
        raise ValueError("bad bit")
    return (word | (1 << bit)) if on else (word & ~(1 << bit) & 0xFFFFFFFF)
''')

PS_GO = dd(r'''
package packstamp

import "errors"

var days = [12]int64{31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31}

var errBad = errors.New("packstamp: bad input")

func valid(year, month, day, hour, minute, flags int64) bool {
	return year >= 2000 && year <= 2127 && month >= 1 && month <= 12 && day >= 1 && day <= days[month-1] &&
		hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59 && flags >= 0 && flags <= 31
}

func Pack(year, month, day, hour, minute, flags int64) (uint32, error) {
	if !valid(year, month, day, hour, minute, flags) {
		return 0, errBad
	}
	return uint32(year-2000)<<25 | uint32(month)<<21 | uint32(day)<<16 | uint32(hour)<<11 | uint32(minute)<<5 | uint32(flags), nil
}

func fields(word uint32) ([6]int64, error) {
	f := [6]int64{2000 + int64(word>>25), int64(word>>21) & 15, int64(word>>16) & 31, int64(word>>11) & 31, int64(word>>5) & 63, int64(word) & 31}
	if f[1] < 1 || f[1] > 12 || !valid(f[0], f[1], f[2], f[3], f[4], f[5]) {
		return f, errBad
	}
	return f, nil
}

func Unpack(word uint32) ([]int64, error) {
	f, err := fields(word)
	if err != nil {
		return nil, err
	}
	return f[:], nil
}

func AddMinutes(word uint32, delta int64) (uint32, error) {
	f, err := fields(word)
	if err != nil {
		return 0, err
	}
	var doy int64
	for m := int64(0); m < f[1]-1; m++ {
		doy += days[m]
	}
	doy += f[2] - 1
	total := (((f[0]-2000)*365+doy)*24+f[3])*60 + f[4] + delta
	if total < 0 {
		return 0, errBad
	}
	d, rem := total/1440, total%1440
	yearOff, doy2 := d/365, d%365
	if yearOff > 127 {
		return 0, errBad
	}
	month := int64(1)
	for doy2 >= days[month-1] {
		doy2 -= days[month-1]
		month++
	}
	return Pack(2000+yearOff, month, doy2+1, rem/60, rem%60, f[5])
}

func Compare(a, b uint32) (int32, error) {
	x, err := fields(a)
	if err != nil {
		return 0, err
	}
	y, err := fields(b)
	if err != nil {
		return 0, err
	}
	for i := 0; i < 5; i++ {
		if x[i] != y[i] {
			if x[i] < y[i] {
				return -1, nil
			}
			return 1, nil
		}
	}
	return 0, nil
}

func HasFlag(word uint32, bit int64) (bool, error) {
	if bit < 0 || bit > 4 {
		return false, errBad
	}
	return (word>>uint(bit))&1 == 1, nil
}

func SetFlag(word uint32, bit int64, on bool) (uint32, error) {
	if bit < 0 || bit > 4 {
		return 0, errBad
	}
	if on {
		return word | 1<<uint(bit), nil
	}
	return word &^ (1 << uint(bit)), nil
}
''')

PS_JAVA = dd(r'''
import java.util.*;

public final class PackStamp {
    private PackStamp() {}

    private static final int[] DAYS = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};

    private static boolean valid(long year, long month, long day, long hour, long minute, long flags) {
        return year >= 2000 && year <= 2127 && month >= 1 && month <= 12 && day >= 1 && day <= DAYS[(int) month - 1]
            && hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59 && flags >= 0 && flags <= 31;
    }

    public static long pack(long year, long month, long day, long hour, long minute, long flags) {
        if (!valid(year, month, day, hour, minute, flags)) throw new IllegalArgumentException("field out of range");
        return ((year - 2000) << 25 | month << 21 | day << 16 | hour << 11 | minute << 5 | flags) & 0xFFFFFFFFL;
    }

    private static long[] fields(long word) {
        long[] f = {2000 + (word >>> 25), (word >>> 21) & 15, (word >>> 16) & 31, (word >>> 11) & 31, (word >>> 5) & 63, word & 31};
        if (f[1] < 1 || f[1] > 12 || !valid(f[0], f[1], f[2], f[3], f[4], f[5])) throw new IllegalArgumentException("invalid word");
        return f;
    }

    public static List<Long> unpack(long word) {
        long[] f = fields(word);
        List<Long> out = new ArrayList<>();
        for (long x : f) out.add(x);
        return out;
    }

    public static long addMinutes(long word, long delta) {
        long[] f = fields(word);
        long doy = f[2] - 1;
        for (int m = 0; m < f[1] - 1; m++) doy += DAYS[m];
        long total = (((f[0] - 2000) * 365 + doy) * 24 + f[3]) * 60 + f[4] + delta;
        if (total < 0) throw new IllegalArgumentException("before the epoch");
        long days = total / 1440, rem = total % 1440;
        long yearOff = days / 365, d = days % 365;
        if (yearOff > 127) throw new IllegalArgumentException("after the last year");
        int month = 1;
        while (d >= DAYS[month - 1]) {
            d -= DAYS[month - 1];
            month++;
        }
        return pack(2000 + yearOff, month, d + 1, rem / 60, rem % 60, f[5]);
    }

    public static int compare(long a, long b) {
        long[] x = fields(a), y = fields(b);
        for (int i = 0; i < 5; i++) {
            if (x[i] != y[i]) return x[i] < y[i] ? -1 : 1;
        }
        return 0;
    }

    public static boolean hasFlag(long word, long bit) {
        if (bit < 0 || bit > 4) throw new IllegalArgumentException("bad bit");
        return ((word >>> bit) & 1L) == 1L;
    }

    public static long setFlag(long word, long bit, boolean on) {
        if (bit < 0 || bit > 4) throw new IllegalArgumentException("bad bit");
        long mask = 1L << bit;
        return (on ? (word | mask) : (word & ~mask)) & 0xFFFFFFFFL;
    }
}
''')


def _ps_pack(y, mo, d, h, mi, f):
    return ((y - 2000) << 25) | (mo << 21) | (d << 16) | (h << 11) | (mi << 5) | f


def ps_cases(rng):
    out = [("pack", [2024, 5, 17, 13, 45, 3]), ("unpack", [_ps_pack(2024, 5, 17, 13, 45, 3)]), ("add_minutes", [_ps_pack(2024, 12, 31, 23, 59, 0), 1]), ("compare", [_ps_pack(2024, 1, 1, 0, 0, 31), _ps_pack(2024, 1, 1, 0, 0, 0)]),
           ("has_flag", [_ps_pack(2024, 5, 17, 13, 45, 4), 2]), ("set_flag", [_ps_pack(2070, 5, 17, 13, 45, 0), 4, True])]
    for args in [(2000, 1, 1, 0, 0, 0), (2127, 12, 31, 23, 59, 31), (2063, 12, 31, 23, 59, 0), (2064, 1, 1, 0, 0, 0), (2100, 2, 28, 12, 0, 1), (2100, 2, 29, 12, 0, 1), (2024, 4, 30, 0, 0, 0), (2024, 4, 31, 0, 0, 0), (2024, 6, 31, 0, 0, 0),
                 (1999, 12, 31, 23, 59, 0), (2128, 1, 1, 0, 0, 0), (2024, 0, 1, 0, 0, 0), (2024, 13, 1, 0, 0, 0), (2024, 1, 0, 0, 0, 0), (2024, 1, 1, 24, 0, 0), (2024, 1, 1, 0, 60, 0), (2024, 1, 1, 0, 0, 32), (2024, 1, 1, 0, 0, -1),
                 (2024, 1, 1, -1, 0, 0), (2024, 1, 1, 0, -1, 0), (2100, 7, 31, 23, 59, 31), (2090, 11, 30, 18, 30, 17)]:
        out.append(("pack", list(args)))
    for _ in range(25):
        y = rng.randint(2000, 2127)
        mo = rng.randint(1, 12)
        d = rng.randint(1, [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo - 1])
        w = _ps_pack(y, mo, d, rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 31))
        out.append(("pack", [y, mo, d, w >> 11 & 31, w >> 5 & 63, w & 31]))
        out.append(("unpack", [w]))
        out.append(("add_minutes", [w, rng.choice([0, 1, -1, 59, 60, 1439, 1440, -1440, 525600, -525600, 100000, -100000, 123456789 % 5000000, -(123456789 % 5000000)])]))
        w2 = _ps_pack(rng.randint(2000, 2127), rng.randint(1, 12), rng.randint(1, 28), rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 31))
        out.append(("compare", [w, w2]))
        out.append(("compare", [w, w ^ rng.randint(0, 31)]))
    for w in [0, 1, 0xFFFFFFFF, 0x80000000, _ps_pack(2024, 0, 1, 0, 0, 0) | 0, (2024 - 2000) << 25 | 13 << 21 | 1 << 16, _ps_pack(2024, 2, 1, 0, 0, 0) | (30 << 16), _ps_pack(2024, 5, 17, 13, 45, 3) | (31 << 11), _ps_pack(2024, 5, 17, 13, 45, 3) | (63 << 5), 2000 + 0, _ps_pack(2000, 1, 1, 0, 0, 0)]:
        out.append(("unpack", [w]))
        out.append(("add_minutes", [w, 5]))
        out.append(("compare", [w, _ps_pack(2024, 1, 1, 0, 0, 0)]))
    s = _ps_pack(2000, 1, 1, 0, 0, 7)
    e = _ps_pack(2127, 12, 31, 23, 59, 9)
    for w, dlt in [(s, -1), (s, 0), (s, 1), (s, 525600 * 128 - 1), (s, 525600 * 128), (e, 1), (e, 0), (e, -1), (e, -525600 * 128 + 1), (e, -525600 * 128), (e, -525600 * 128 - 1), (_ps_pack(2024, 2, 28, 23, 59, 0), 1), (_ps_pack(2024, 3, 1, 0, 0, 0), -1),
                   (_ps_pack(2024, 12, 31, 23, 59, 5), 1), (_ps_pack(2024, 1, 1, 0, 0, 5), -1), (_ps_pack(2063, 12, 31, 23, 59, 0), 1), (_ps_pack(2064, 1, 1, 0, 0, 0), -1), (_ps_pack(2100, 6, 15, 12, 30, 2), 2**33), (_ps_pack(2100, 6, 15, 12, 30, 2), -(2**33))]:
        out.append(("add_minutes", [w, dlt]))
    for w in [0, _ps_pack(2070, 1, 1, 0, 0, 0), _ps_pack(2024, 5, 17, 13, 45, 0b10110), 0xFFFFFFFF, 0x80000000, 0x80000010]:
        for bit in [0, 1, 4, 5, -1, 31]:
            out.append(("has_flag", [w, bit]))
            out.append(("set_flag", [w, bit, True]))
            out.append(("set_flag", [w, bit, False]))
    return out


PS = PortLib(
    slug="pack-stamp",
    title="bit-packed telemetry timestamps",
    blurb="A telemetry gateway squeezes a timestamp and five status flags into one 32-bit word, and several services (in different languages) read and write that word.",
    spec=PS_SPEC,
    fns=PS_FNS,
    impls={"go": {"packstamp.go": PS_GO}, "java": {"PackStamp.java": PS_JAVA}, "python": {"pack_stamp.py": PS_PY}},
    cases=ps_cases,
    difficulty=4,
    traps=["top bit of a u32 (signed int in Java/JS)", "shifts", "floor vs truncating division on negative minutes", "custom calendar"],
    tags=["bit-packing", "u32", "calendar"],
    pairs=[("go", "java", "full"), ("java", "python", "full"), ("python", "go", "stub"), ("go", "python", "stub")],
)
register_port(PS, __name__)

# ======================================================================================================================
# drift-sum: checksums and a tiny PRNG
# ======================================================================================================================

DS_SPEC = dd('''
    Checksums and a pseudo-random shuffle for a sensor firmware's test bench. All 32-bit arithmetic is **unsigned and wraps**.
    Byte strings travel as **hex text**: an even number of ASCII hex digits, upper or lower case, nothing else (no spaces, no
    `0x`); anything else is an error.

    * `crc16x(payload)`: payload is hex text. `crc = 0xFFFF`; for every byte: `crc ^= byte << 8`, then 8 times: if the top bit
      (`0x8000`) of `crc` is set `crc = ((crc << 1) XOR 0x8BB7) AND 0xFFFF`, else `crc = (crc << 1) AND 0xFFFF`. The result is
      `crc XOR 0x0001`. (The empty payload gives `0xFFFE`.)
    * `fletch(text)`: over the **UTF-8 bytes** of `text`: `a = 7`, `b = 3`; for each byte `a = (a + byte) mod 251`,
      `b = (b + a) mod 251`; result `b * 256 + a`.
    * `xorshift(seed, steps)`: the xorshift32 generator `x ^= x << 13; x ^= x >> 17; x ^= x << 5` applied `steps` times
      to `seed`. A zero seed or negative `steps` is an error. `steps = 0` returns the seed.
    * `shuffle(n, seed)`: `n` in `0..1000` and a non-zero seed, else error. Start from `[0, 1, ..., n-1]`; for `i` from `n-1`
      down to `1`: advance the generator one step (`x = next(x)`, the first step is taken from `seed`), `j = x mod (i + 1)`, swap
      the entries at `i` and `j`. Returns the list.
    * `rotl32(x, k)` rotates the 32 bits of `x` left by `k mod 32` (floor modulo, so a negative `k` rotates right).
    * `popcount(x)` is the number of set bits.
''')

DS_FNS = [
    Fn("crc16x", [("payload", "str")], "u32", err=True),
    Fn("fletch", [("text", "str")], "u32"),
    Fn("xorshift", [("seed", "u32"), ("steps", "int")], "u32", err=True),
    Fn("shuffle", [("n", "int"), ("seed", "u32")], "list<int>", err=True),
    Fn("rotl32", [("x", "u32"), ("k", "int")], "u32"),
    Fn("popcount", [("x", "u32")], "int"),
]

DS_PY = dd(r'''
M32 = 0xFFFFFFFF
_HEX = "0123456789abcdefABCDEF"


def _bytes(payload):
    if len(payload) % 2 or any(c not in _HEX for c in payload):
        raise ValueError("bad hex")
    return [int(payload[i:i + 2], 16) for i in range(0, len(payload), 2)]


def crc16x(payload):
    crc = 0xFFFF
    for byte in _bytes(payload):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x8BB7) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc ^ 0x0001


def fletch(text):
    a, b = 7, 3
    for byte in text.encode("utf-8"):
        a = (a + byte) % 251
        b = (b + a) % 251
    return b * 256 + a


def _next(x):
    x ^= (x << 13) & M32
    x ^= x >> 17
    x ^= (x << 5) & M32
    return x


def xorshift(seed, steps):
    if seed == 0 or steps < 0:
        raise ValueError("bad seed or steps")
    x = seed
    for _ in range(steps):
        x = _next(x)
    return x


def shuffle(n, seed):
    if n < 0 or n > 1000 or seed == 0:
        raise ValueError("bad arguments")
    arr = list(range(n))
    x = seed
    for i in range(n - 1, 0, -1):
        x = _next(x)
        j = x % (i + 1)
        arr[i], arr[j] = arr[j], arr[i]
    return arr


def rotl32(x, k):
    k %= 32
    return ((x << k) | (x >> (32 - k))) & M32 if k else x


def popcount(x):
    return bin(x).count("1")
''')

DS_RS = dd(r'''
fn hex_bytes(payload: &str) -> Result<Vec<u8>, String> {
    let b = payload.as_bytes();
    if b.len() % 2 != 0 || !b.iter().all(|c| c.is_ascii_hexdigit()) {
        return Err("bad hex".to_string());
    }
    Ok((0..b.len() / 2).map(|i| u8::from_str_radix(&payload[2 * i..2 * i + 2], 16).unwrap()).collect())
}

pub fn crc16x(payload: &str) -> Result<u32, String> {
    let mut crc: u32 = 0xFFFF;
    for byte in hex_bytes(payload)? {
        crc ^= (byte as u32) << 8;
        for _ in 0..8 {
            crc = if crc & 0x8000 != 0 { ((crc << 1) ^ 0x8BB7) & 0xFFFF } else { (crc << 1) & 0xFFFF };
        }
    }
    Ok(crc ^ 1)
}

pub fn fletch(text: &str) -> u32 {
    let (mut a, mut b) = (7u32, 3u32);
    for byte in text.bytes() {
        a = (a + byte as u32) % 251;
        b = (b + a) % 251;
    }
    b * 256 + a
}

fn next(mut x: u32) -> u32 {
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    x
}

pub fn xorshift(seed: u32, steps: i64) -> Result<u32, String> {
    if seed == 0 || steps < 0 {
        return Err("bad seed or steps".to_string());
    }
    let mut x = seed;
    for _ in 0..steps {
        x = next(x);
    }
    Ok(x)
}

pub fn shuffle(n: i64, seed: u32) -> Result<Vec<i64>, String> {
    if !(0..=1000).contains(&n) || seed == 0 {
        return Err("bad arguments".to_string());
    }
    let mut arr: Vec<i64> = (0..n).collect();
    let mut x = seed;
    let mut i = n - 1;
    while i >= 1 {
        x = next(x);
        let j = (x as i64) % (i + 1);
        arr.swap(i as usize, j as usize);
        i -= 1;
    }
    Ok(arr)
}

pub fn rotl32(x: u32, k: i64) -> u32 {
    x.rotate_left(k.rem_euclid(32) as u32)
}

pub fn popcount(x: u32) -> i64 {
    x.count_ones() as i64
}
''')

DS_JAVA = dd(r'''
import java.nio.charset.StandardCharsets;
import java.util.*;

public final class DriftSum {
    private DriftSum() {}

    private static int[] hex(String payload) {
        if (payload.length() % 2 != 0) throw new IllegalArgumentException("bad hex");
        int[] out = new int[payload.length() / 2];
        for (int i = 0; i < payload.length(); i++) {
            char c = payload.charAt(i);
            boolean ok = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
            if (!ok) throw new IllegalArgumentException("bad hex");
        }
        for (int i = 0; i < out.length; i++) out[i] = Integer.parseInt(payload.substring(2 * i, 2 * i + 2), 16);
        return out;
    }

    public static long crc16x(String payload) {
        int crc = 0xFFFF;
        for (int b : hex(payload)) {
            crc ^= b << 8;
            for (int k = 0; k < 8; k++) {
                crc = (crc & 0x8000) != 0 ? ((crc << 1) ^ 0x8BB7) & 0xFFFF : (crc << 1) & 0xFFFF;
            }
        }
        return crc ^ 1;
    }

    public static long fletch(String text) {
        int a = 7, b = 3;
        for (byte x : text.getBytes(StandardCharsets.UTF_8)) {
            a = (a + (x & 0xFF)) % 251;
            b = (b + a) % 251;
        }
        return b * 256 + a;
    }

    private static int next(int x) {
        x ^= x << 13;
        x ^= x >>> 17;
        x ^= x << 5;
        return x;
    }

    public static long xorshift(long seed, long steps) {
        if (seed == 0 || steps < 0) throw new IllegalArgumentException("bad seed or steps");
        int x = (int) seed;
        for (long i = 0; i < steps; i++) x = next(x);
        return x & 0xFFFFFFFFL;
    }

    public static List<Long> shuffle(long n, long seed) {
        if (n < 0 || n > 1000 || seed == 0) throw new IllegalArgumentException("bad arguments");
        long[] arr = new long[(int) n];
        for (int i = 0; i < n; i++) arr[i] = i;
        int x = (int) seed;
        for (int i = (int) n - 1; i >= 1; i--) {
            x = next(x);
            int j = (int) ((x & 0xFFFFFFFFL) % (i + 1));
            long t = arr[i];
            arr[i] = arr[j];
            arr[j] = t;
        }
        List<Long> out = new ArrayList<>();
        for (long v : arr) out.add(v);
        return out;
    }

    public static long rotl32(long x, long k) {
        int r = (int) Math.floorMod(k, 32L);
        return Integer.rotateLeft((int) x, r) & 0xFFFFFFFFL;
    }

    public static long popcount(long x) {
        return Long.bitCount(x & 0xFFFFFFFFL);
    }
}
''')


def ds_cases(rng):
    out = [("crc16x", ["313233343536373839"]), ("crc16x", [""]), ("fletch", ["abc"]), ("xorshift", [1, 1]), ("xorshift", [2463534242, 3]), ("shuffle", [5, 12345]), ("rotl32", [0x80000001, 1]), ("popcount", [0xFFFFFFFF])]
    for h in ["", "00", "ff", "FF", "aBcD", "0123456789abcdef", "7e7d7f", "deadBEEF", "00" * 40, "a", "abc", "zz", "12 34", "0x12", "12\n", "１２", "gg", "1234567", "-1"]:
        out.append(("crc16x", [h]))
    for _ in range(12):
        out.append(("crc16x", ["".join(rng.choice("0123456789abcdefABCDEF") for _ in range(2 * rng.randint(1, 30)))]))
    for t in ["", "a", "abc", "hello", "é", "中文", "\U0001F600", "x" * 300, "The quick brown fox", "\x00\x01"]:
        out.append(("fletch", [t]))
    for seed in [1, 2, 0xFFFFFFFF, 0x80000000, 2463534242, 123456789, 0xDEADBEEF]:
        for steps in [0, 1, 2, 5, 50]:
            out.append(("xorshift", [seed, steps]))
    out += [("xorshift", [0, 3]), ("xorshift", [5, -1]), ("xorshift", [0, 0]), ("xorshift", [7, 100000])]
    for n, seed in [(0, 1), (1, 1), (2, 1), (5, 12345), (10, 2463534242), (10, 0xFFFFFFFF), (52, 777), (100, 0x80000000), (1000, 99), (1001, 5), (-1, 5), (5, 0), (0, 0)]:
        out.append(("shuffle", [n, seed]))
    for _ in range(5):
        out.append(("shuffle", [rng.randint(2, 60), rng.randint(1, 2**32 - 1)]))
    for x in [0, 1, 0x80000000, 0xFFFFFFFF, 0x12345678, 0xF0000001]:
        for k in [0, 1, 4, 16, 31, 32, 33, 64, -1, -4, -31, -32, -33, 1000, -1000]:
            out.append(("rotl32", [x, k]))
    for x in [0, 1, 2, 3, 0xFF, 0x80000000, 0xFFFFFFFF, 0x55555555, 0xAAAAAAAA, 0x12345678]:
        out.append(("popcount", [x]))
    return out


DS = PortLib(
    slug="drift-sum",
    title="checksums and a seeded shuffle",
    blurb="A sensor firmware team keeps a test bench that checks frames with a custom CRC, a small additive checksum, and a deterministic shuffle for replaying captures.",
    spec=DS_SPEC,
    fns=DS_FNS,
    impls={"rust": {"src/lib.rs": DS_RS}, "python": {"drift_sum.py": DS_PY}, "java": {"DriftSum.java": DS_JAVA}},
    cases=ds_cases,
    difficulty=3,
    traps=["u32 shifts that must not widen", "unsigned modulo", "strict hex parsing (bytes.fromhex accepts spaces)", "floor modulo for rotations"],
    tags=["checksum", "u32", "prng"],
    pairs=[("rust", "python", "full"), ("python", "java", "full"), ("java", "rust", "stub"), ("rust", "java", "stub")],
)
register_port(DS, __name__)

# ======================================================================================================================
# morton-cells: Z-order cell ids on a 65536 x 65536 grid
# ======================================================================================================================

MC_SPEC = dd('''
    A map service addresses the cells of a 65536 x 65536 grid (`x`, `y` in `0..65535`) by a 32-bit **Z-order id**:
    bit `i` of `x` becomes bit `2i` of the id and bit `i` of `y` becomes bit `2i+1`. So cell `(1, 0)` is id 1, `(0, 1)` is
    id 2, `(1, 1)` is id 3 and `(65535, 65535)` is `4294967295`. Ids are unsigned 32-bit numbers.

    * `cell_id(x, y)` builds the id; a coordinate outside `0..65535` is an error.
    * `cell_xy(id)` returns `[x, y]`.
    * `parent(id, level)` is the id of the enclosing block `level` levels up: `id` shifted right by `2*level` bits. `level` is
      `0..16` (anything else is an error); at level 16 the result is always 0.
    * `neighbors(id)` lists the ids of the (up to) 8 cells around the cell, leaving out cells outside the grid, in ascending order of id.
    * `common_level(a, b)` is the smallest `level` in `0..16` at which `parent(a, level) == parent(b, level)`.
    * `distance_cells(a, b)` is the Chebyshev distance between the two cells: `max(|dx|, |dy|)`.
''')

MC_FNS = [
    Fn("cell_id", [("x", "int"), ("y", "int")], "u32", err=True),
    Fn("cell_xy", [("id", "u32")], "list<int>"),
    Fn("parent", [("id", "u32"), ("level", "int")], "u32", err=True),
    Fn("neighbors", [("id", "u32")], "list<u32>"),
    Fn("common_level", [("a", "u32"), ("b", "u32")], "int"),
    Fn("distance_cells", [("a", "u32"), ("b", "u32")], "int"),
]

MC_PY = dd(r'''
def _spread(v):
    r = 0
    for i in range(16):
        r |= ((v >> i) & 1) << (2 * i)
    return r


def _compact(v):
    r = 0
    for i in range(16):
        r |= ((v >> (2 * i)) & 1) << i
    return r


def cell_id(x, y):
    if not (0 <= x <= 65535 and 0 <= y <= 65535):
        raise ValueError("coordinate out of range")
    return _spread(x) | (_spread(y) << 1)


def cell_xy(id):
    return [_compact(id), _compact(id >> 1)]


def parent(id, level):
    if level < 0 or level > 16:
        raise ValueError("bad level")
    return id >> (2 * level)


def neighbors(id):
    x, y = cell_xy(id)
    out = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if (dx or dy) and 0 <= x + dx <= 65535 and 0 <= y + dy <= 65535:
                out.append(cell_id(x + dx, y + dy))
    return sorted(out)


def common_level(a, b):
    for level in range(17):
        if parent(a, level) == parent(b, level):
            return level
    return 16


def distance_cells(a, b):
    ax, ay = cell_xy(a)
    bx, by = cell_xy(b)
    return max(abs(ax - bx), abs(ay - by))
''')

MC_GO = dd(r'''
package mortoncells

import "errors"

func spread(v uint32) uint32 {
	var r uint32
	for i := uint(0); i < 16; i++ {
		r |= ((v >> i) & 1) << (2 * i)
	}
	return r
}

func compact(v uint32) uint32 {
	var r uint32
	for i := uint(0); i < 16; i++ {
		r |= ((v >> (2 * i)) & 1) << i
	}
	return r
}

func CellId(x, y int64) (uint32, error) {
	if x < 0 || x > 65535 || y < 0 || y > 65535 {
		return 0, errors.New("coordinate out of range")
	}
	return spread(uint32(x)) | spread(uint32(y))<<1, nil
}

func CellXy(id uint32) []int64 {
	return []int64{int64(compact(id)), int64(compact(id >> 1))}
}

func Parent(id uint32, level int64) (uint32, error) {
	if level < 0 || level > 16 {
		return 0, errors.New("bad level")
	}
	return id >> uint(2*level), nil
}

func Neighbors(id uint32) []uint32 {
	xy := CellXy(id)
	x, y := xy[0], xy[1]
	out := []uint32{}
	for dx := int64(-1); dx <= 1; dx++ {
		for dy := int64(-1); dy <= 1; dy++ {
			if (dx != 0 || dy != 0) && x+dx >= 0 && x+dx <= 65535 && y+dy >= 0 && y+dy <= 65535 {
				c, _ := CellId(x+dx, y+dy)
				out = append(out, c)
			}
		}
	}
	for i := 1; i < len(out); i++ {
		for j := i; j > 0 && out[j-1] > out[j]; j-- {
			out[j-1], out[j] = out[j], out[j-1]
		}
	}
	return out
}

func CommonLevel(a, b uint32) int64 {
	for level := int64(0); level <= 16; level++ {
		pa, _ := Parent(a, level)
		pb, _ := Parent(b, level)
		if pa == pb {
			return level
		}
	}
	return 16
}

func abs(v int64) int64 {
	if v < 0 {
		return -v
	}
	return v
}

func DistanceCells(a, b uint32) int64 {
	p, q := CellXy(a), CellXy(b)
	dx, dy := abs(p[0]-q[0]), abs(p[1]-q[1])
	if dx > dy {
		return dx
	}
	return dy
}
''')

MC_JS = dd(r'''
'use strict';

function spread(v) {
  let r = 0;
  for (let i = 0; i < 16; i++) {
    r = (r | (((v >>> i) & 1) << (2 * i))) >>> 0;
  }
  return r;
}

function compact(v) {
  let r = 0;
  for (let i = 0; i < 16; i++) {
    r |= ((v >>> (2 * i)) & 1) << i;
  }
  return r >>> 0;
}

function cellId(x, y) {
  if (x < 0 || x > 65535 || y < 0 || y > 65535) throw new Error('coordinate out of range');
  return (spread(x) | (spread(y) << 1)) >>> 0;
}

function cellXy(id) {
  return [compact(id), compact(id >>> 1)];
}

function parent(id, level) {
  if (level < 0 || level > 16) throw new Error('bad level');
  return level === 16 ? 0 : id >>> (2 * level);
}

function neighbors(id) {
  const [x, y] = cellXy(id);
  const out = [];
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      if ((dx || dy) && x + dx >= 0 && x + dx <= 65535 && y + dy >= 0 && y + dy <= 65535) out.push(cellId(x + dx, y + dy));
    }
  }
  return out.sort((a, b) => a - b);
}

function commonLevel(a, b) {
  for (let level = 0; level <= 16; level++) {
    if (parent(a, level) === parent(b, level)) return level;
  }
  return 16;
}

function distanceCells(a, b) {
  const [ax, ay] = cellXy(a);
  const [bx, by] = cellXy(b);
  return Math.max(Math.abs(ax - bx), Math.abs(ay - by));
}

module.exports = { cellId, cellXy, parent, neighbors, commonLevel, distanceCells };
''')


def _mc_id(x, y):
    r = 0
    for i in range(16):
        r |= ((x >> i) & 1) << (2 * i) | ((y >> i) & 1) << (2 * i + 1)
    return r


def mc_cases(rng):
    out = [("cell_id", [1, 0]), ("cell_id", [0, 1]), ("cell_id", [65535, 65535]), ("cell_xy", [3]), ("parent", [0xFFFFFFFF, 1]), ("neighbors", [_mc_id(5, 5)]), ("common_level", [_mc_id(0, 0), _mc_id(3, 3)]), ("distance_cells", [_mc_id(0, 0), _mc_id(3, 5)])]
    pts = [(0, 0), (1, 0), (0, 1), (1, 1), (2, 3), (65535, 0), (0, 65535), (65535, 65535), (32768, 32768), (32767, 32767), (12345, 54321), (255, 256), (65534, 65535), (1, 65535), (43690, 21845)]
    for x, y in pts:
        out.append(("cell_id", [x, y]))
        out.append(("neighbors", [_mc_id(x, y)]))
        for lvl in [0, 1, 7, 15, 16]:
            out.append(("parent", [_mc_id(x, y), lvl]))
    for x, y in [(-1, 0), (0, -1), (65536, 0), (0, 65536), (70000, 70000), (-5, -5)]:
        out.append(("cell_id", [x, y]))
    for lvl in [-1, 17, 100]:
        out.append(("parent", [5, lvl]))
    for cid in [0, 1, 2, 3, 0x80000000, 0xFFFFFFFF, 0xAAAAAAAA, 0x55555555, 0x12345678]:
        out.append(("cell_xy", [cid]))
        out.append(("neighbors", [cid]))
        out.append(("parent", [cid, 16]))
        out.append(("parent", [cid, 15]))
    for _ in range(25):
        a = (rng.randint(0, 65535), rng.randint(0, 65535))
        b = rng.choice([(min(65535, max(0, a[0] + rng.randint(-5, 5))), min(65535, max(0, a[1] + rng.randint(-5, 5)))), (rng.randint(0, 65535), rng.randint(0, 65535))])
        out.append(("common_level", [_mc_id(*a), _mc_id(*b)]))
        out.append(("distance_cells", [_mc_id(*a), _mc_id(*b)]))
        out.append(("cell_xy", [_mc_id(*a)]))
        out.append(("cell_id", list(a)))
    out.append(("common_level", [0, 0xFFFFFFFF]))
    out.append(("common_level", [7, 7]))
    out.append(("common_level", [0x80000000, 0]))
    out.append(("distance_cells", [0, 0xFFFFFFFF]))
    return out


MC = PortLib(
    slug="morton-cells",
    title="Z-order cell ids for a map grid",
    blurb="A map tile service addresses grid cells by interleaving the bits of their coordinates into a single 32-bit id.",
    spec=MC_SPEC,
    fns=MC_FNS,
    impls={"go": {"mortoncells.go": MC_GO}, "javascript": {"src/morton_cells.js": MC_JS}, "python": {"morton_cells.py": MC_PY}},
    cases=mc_cases,
    difficulty=3,
    traps=["32-bit signed shifts in JavaScript", "shift by the full width", "unsigned ids with the top bit set"],
    tags=["bit-twiddling", "u32"],
    pairs=[("go", "javascript", "full"), ("javascript", "python", "full"), ("python", "go", "stub"), ("go", "python", "stub")],
)
register_port(MC, __name__)

# ======================================================================================================================
# fix-lerp: integer colour maths
# ======================================================================================================================

FL_SPEC = dd('''
    Integer-only colour helpers for a lighting-cue controller. Channels are `u8` (0..255). A colour is a packed `u32`
    `0xRRGGBB`; the top byte must be zero (a colour with any bit above bit 23 is an error everywhere it is accepted).

    * `lerp_u8(a, b, t)` interpolates with an integer weight `t` in `0..256` (otherwise error):
      `(a * (256 - t) + b * t + 128) >> 8`. So `t = 0` is `a` and `t = 256` is `b`.
    * `blend_rgb(a, b, t)` applies `lerp_u8` to each channel of two packed colours.
    * `fade(a, b, steps)`: `steps >= 2` (else error); entry `i` (from `0` to `steps-1`) is
      `a + round_div((b - a) * i, steps - 1)`, where `round_div` rounds to the nearest integer and an exact half goes **away
      from zero** (`round_div(-3, 2) = -2`, `round_div(3, 2) = 2`). A fade can go downwards.
    * `scale_rgb(rgb, pct)`: `pct` in `0..400` (else error); every channel becomes `min(255, (c * pct + 50) / 100)` with integer
      (floor) division.
    * `gamma_u8(v)` is `(2*v*v + 255) / 510` (floor division): the nearest integer to `v*v/255`.
    * `luma(rgb)` is `(299*r + 587*g + 114*b + 500) / 1000` (floor division).
''')

FL_FNS = [
    Fn("lerp_u8", [("a", "u8"), ("b", "u8"), ("t", "int")], "u8", err=True),
    Fn("blend_rgb", [("a", "u32"), ("b", "u32"), ("t", "int")], "u32", err=True),
    Fn("fade", [("a", "u8"), ("b", "u8"), ("steps", "int")], "list<int>", err=True),
    Fn("scale_rgb", [("rgb", "u32"), ("pct", "int")], "u32", err=True),
    Fn("gamma_u8", [("v", "u8")], "u8"),
    Fn("luma", [("rgb", "u32")], "u8", err=True),
]

FL_PY = dd(r'''
def lerp_u8(a, b, t):
    if t < 0 or t > 256:
        raise ValueError("weight out of range")
    return (a * (256 - t) + b * t + 128) >> 8


def _split(rgb):
    if rgb >> 24:
        raise ValueError("not a 24-bit colour")
    return (rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255


def _join(r, g, b):
    return (r << 16) | (g << 8) | b


def blend_rgb(a, b, t):
    ca, cb = _split(a), _split(b)
    return _join(*[lerp_u8(x, y, t) for x, y in zip(ca, cb)])


def _round_div(n, d):
    sign = -1 if (n < 0) != (d < 0) else 1
    return sign * ((2 * abs(n) + abs(d)) // (2 * abs(d)))


def fade(a, b, steps):
    if steps < 2:
        raise ValueError("need at least two steps")
    return [a + _round_div((b - a) * i, steps - 1) for i in range(steps)]


def scale_rgb(rgb, pct):
    c = _split(rgb)
    if pct < 0 or pct > 400:
        raise ValueError("percentage out of range")
    return _join(*[min(255, (x * pct + 50) // 100) for x in c])


def gamma_u8(v):
    return (2 * v * v + 255) // 510


def luma(rgb):
    r, g, b = _split(rgb)
    return (299 * r + 587 * g + 114 * b + 500) // 1000
''')

FL_RS = dd(r'''
pub fn lerp_u8(a: u8, b: u8, t: i64) -> Result<u8, String> {
    if !(0..=256).contains(&t) {
        return Err("weight out of range".to_string());
    }
    Ok(((a as i64 * (256 - t) + b as i64 * t + 128) >> 8) as u8)
}

fn split(rgb: u32) -> Result<[u8; 3], String> {
    if rgb >> 24 != 0 {
        return Err("not a 24-bit colour".to_string());
    }
    Ok([(rgb >> 16) as u8, (rgb >> 8) as u8, rgb as u8])
}

fn join(c: [u8; 3]) -> u32 {
    ((c[0] as u32) << 16) | ((c[1] as u32) << 8) | c[2] as u32
}

pub fn blend_rgb(a: u32, b: u32, t: i64) -> Result<u32, String> {
    let (ca, cb) = (split(a)?, split(b)?);
    let mut out = [0u8; 3];
    for i in 0..3 {
        out[i] = lerp_u8(ca[i], cb[i], t)?;
    }
    Ok(join(out))
}

fn round_div(n: i64, d: i64) -> i64 {
    let sign = if (n < 0) != (d < 0) { -1 } else { 1 };
    sign * ((2 * n.abs() + d.abs()) / (2 * d.abs()))
}

pub fn fade(a: u8, b: u8, steps: i64) -> Result<Vec<i64>, String> {
    if steps < 2 {
        return Err("need at least two steps".to_string());
    }
    Ok((0..steps).map(|i| a as i64 + round_div((b as i64 - a as i64) * i, steps - 1)).collect())
}

pub fn scale_rgb(rgb: u32, pct: i64) -> Result<u32, String> {
    let c = split(rgb)?;
    if !(0..=400).contains(&pct) {
        return Err("percentage out of range".to_string());
    }
    let mut out = [0u8; 3];
    for i in 0..3 {
        out[i] = std::cmp::min(255, (c[i] as i64 * pct + 50) / 100) as u8;
    }
    Ok(join(out))
}

pub fn gamma_u8(v: u8) -> u8 {
    ((2 * (v as u32) * (v as u32) + 255) / 510) as u8
}

pub fn luma(rgb: u32) -> Result<u8, String> {
    let [r, g, b] = split(rgb)?;
    Ok(((299 * r as u32 + 587 * g as u32 + 114 * b as u32 + 500) / 1000) as u8)
}
''')

FL_PHP = dd(r'''
<?php
final class FixLerp
{
    public static function lerpU8(int $a, int $b, int $t): int
    {
        if ($t < 0 || $t > 256) throw new InvalidArgumentException('weight out of range');
        return ($a * (256 - $t) + $b * $t + 128) >> 8;
    }

    private static function split(int $rgb): array
    {
        if ($rgb >> 24 !== 0) throw new InvalidArgumentException('not a 24-bit colour');
        return [($rgb >> 16) & 255, ($rgb >> 8) & 255, $rgb & 255];
    }

    private static function join(array $c): int
    {
        return ($c[0] << 16) | ($c[1] << 8) | $c[2];
    }

    public static function blendRgb(int $a, int $b, int $t): int
    {
        $ca = self::split($a);
        $cb = self::split($b);
        $out = [];
        for ($i = 0; $i < 3; $i++) $out[] = self::lerpU8($ca[$i], $cb[$i], $t);
        return self::join($out);
    }

    private static function roundDiv(int $n, int $d): int
    {
        $sign = (($n < 0) !== ($d < 0)) ? -1 : 1;
        return $sign * intdiv(2 * abs($n) + abs($d), 2 * abs($d));
    }

    public static function fade(int $a, int $b, int $steps): array
    {
        if ($steps < 2) throw new InvalidArgumentException('need at least two steps');
        $out = [];
        for ($i = 0; $i < $steps; $i++) $out[] = $a + self::roundDiv(($b - $a) * $i, $steps - 1);
        return $out;
    }

    public static function scaleRgb(int $rgb, int $pct): int
    {
        $c = self::split($rgb);
        if ($pct < 0 || $pct > 400) throw new InvalidArgumentException('percentage out of range');
        return self::join(array_map(fn($x) => min(255, intdiv($x * $pct + 50, 100)), $c));
    }

    public static function gammaU8(int $v): int
    {
        return intdiv(2 * $v * $v + 255, 510);
    }

    public static function luma(int $rgb): int
    {
        [$r, $g, $b] = self::split($rgb);
        return intdiv(299 * $r + 587 * $g + 114 * $b + 500, 1000);
    }
}
''')


def fl_cases(rng):
    out = [("lerp_u8", [0, 255, 128]), ("blend_rgb", [0xFF0000, 0x0000FF, 128]), ("fade", [0, 10, 5]), ("fade", [10, 0, 4]), ("scale_rgb", [0x808080, 150]), ("gamma_u8", [128]), ("luma", [0xFF8000])]
    for a, b, t in [(0, 255, 0), (0, 255, 256), (0, 255, 128), (0, 255, 1), (255, 0, 128), (255, 0, 1), (10, 20, 64), (200, 100, 200), (255, 255, 77), (0, 0, 200), (1, 2, 128), (1, 2, 127), (254, 255, 128), (0, 255, -1), (0, 255, 257), (0, 1, 255)]:
        out.append(("lerp_u8", [a, b, t]))
    for _ in range(15):
        out.append(("lerp_u8", [rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 256)]))
    for a, b, t in [(0xFF0000, 0x0000FF, 128), (0, 0xFFFFFF, 64), (0x123456, 0xFEDCBA, 200), (0xFFFFFF, 0, 255), (0x808080, 0x808080, 100), (0x1000000, 0, 5), (0, 0x1000000, 5), (0xFF000000, 0, 5), (0x010203, 0x0A0B0C, 256), (0x010203, 0x0A0B0C, 0), (0x010203, 0x0A0B0C, 300), (0xFFFFFF, 0xFFFFFF, 0)]:
        out.append(("blend_rgb", [a, b, t]))
    for _ in range(10):
        out.append(("blend_rgb", [rng.randint(0, 0xFFFFFF), rng.randint(0, 0xFFFFFF), rng.randint(0, 256)]))
    for a, b, s in [(0, 10, 2), (0, 10, 3), (0, 10, 5), (10, 0, 5), (255, 0, 4), (0, 255, 4), (5, 5, 3), (0, 1, 4), (1, 0, 4), (0, 255, 256), (200, 100, 7), (100, 200, 7), (0, 7, 4), (7, 0, 4), (0, 3, 3), (3, 0, 3), (0, 10, 1), (0, 10, 0), (0, 10, -3), (255, 0, 2), (0, 5, 11), (5, 0, 11)]:
        out.append(("fade", [a, b, s]))
    for _ in range(12):
        out.append(("fade", [rng.randint(0, 255), rng.randint(0, 255), rng.randint(2, 20)]))
    for rgb, p in [(0x808080, 100), (0x808080, 150), (0x808080, 0), (0x808080, 400), (0xFFFFFF, 400), (0x010101, 50), (0x010101, 49), (0x030303, 50), (0x102030, 250), (0x10FF30, 101), (0x1000000, 100), (0x102030, -1), (0x102030, 401), (0xFE0000, 101), (0xC8C8C8, 128), (0xC8C8C8, 127)]:
        out.append(("scale_rgb", [rgb, p]))
    for _ in range(10):
        out.append(("scale_rgb", [rng.randint(0, 0xFFFFFF), rng.randint(0, 400)]))
    for v in [0, 1, 2, 3, 10, 64, 127, 128, 129, 200, 254, 255] + [rng.randint(0, 255) for _ in range(8)]:
        out.append(("gamma_u8", [v]))
    for rgb in [0, 0xFFFFFF, 0xFF0000, 0x00FF00, 0x0000FF, 0x808080, 0x123456, 0xFFFFFE, 0x010101, 0xFF8000, 0x1000000, 0xFFFFFFFF] + [rng.randint(0, 0xFFFFFF) for _ in range(10)]:
        out.append(("luma", [rgb]))
    return out


FL = PortLib(
    slug="fix-lerp",
    title="integer colour interpolation",
    blurb="A stage-lighting controller fades and blends RGB cues with integer maths only, so every console in the rig computes the same channel values.",
    spec=FL_SPEC,
    fns=FL_FNS,
    impls={"python": {"fix_lerp.py": FL_PY}, "rust": {"src/lib.rs": FL_RS}, "php": {"src/FixLerp.php": FL_PHP}},
    cases=fl_cases,
    difficulty=3,
    traps=["u8 arithmetic overflow (panic in Rust debug, wrap in C-like languages)", "rounding half away from zero for negative deltas", "packed colour validation"],
    tags=["fixed-point", "u8"],
    pairs=[("python", "rust", "full"), ("rust", "php", "full"), ("php", "python", "stub"), ("python", "php", "stub")],
)
register_port(FL, __name__)
