"""Port libraries with more involved semantics: a deterministic dice generator (u32 wraparound, rejection sampling; C source) and shelf packing of rectangles (tie-breaking rules)."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

# ======================================================================================================================
# dice-lcg: replayable dice for a tabletop server (C -> Rust / Python)
# ======================================================================================================================

DL_SPEC = dd('''
    A tabletop server must replay games exactly, so its dice come from a deterministic generator over 32-bit unsigned integers. **All arithmetic is modulo 2^32.**

    * `step(state)` is the next state: `state * 747796405 + 2891336453`.
    * `output(state)` scrambles a state into a value: `word = ((state >> ((state >> 28) + 4)) ^ state) * 277803737`, then `(word >> 22) ^ word`. (The shift amount is 4..19.)
    * The **stream** of a `seed`: the state starts as `seed`; every **draw** first replaces the state by `step(state)` and then yields `output(state)` of the new state.
      `draw(seed, index)` is the value of draw number `index` (0-based) of the stream (`index <= 100000` in the vectors).
    * **Bounded values.** To get a value in `0..sides-1` without modulo bias, compute `threshold = (2^32 - sides) mod sides` (that is `((-sides) mod 2^32) mod sides`), then keep drawing until a drawn value is `>= threshold`
      (rejected draws are consumed) and use that value `mod sides`. With `sides = 1` nothing is ever rejected and the value is 0.
    * `roll(seed, nth, sides)` is the `nth` (0-based) die of a run of dice with `sides` faces that are all rolled from one stream: each die is `1 +` a bounded value, and each die continues the same stream where
      the previous one stopped (including the draws it rejected). `sides == 0` is an error. `sides` may be as large as 2^32 - 1; the vectors keep `nth <= 2000`.
    * `sum_dice(seed, expr)` evaluates dice notation `NdS`, `dS` (one die), optionally followed by `+M` or `-M`, for example `3d6+2`, `d20`, `2d10-1`: roll `N` dice of `S` faces from one stream (as in `roll`), add them up and add or subtract `M`.
      The notation is strict: lower-case `d`, ASCII digits, no spaces, no leading zeros, no `+0`; `N` is 1..100, `S` is 2..1000, `M` is 1..10000; anything else is an error. The result is a signed 32-bit integer.
    * `shuffle(seed, n)` is a Fisher-Yates shuffle of `0..n-1` driven by one stream: start with the list `0, 1, ..., n-1`; for `i` from `n-1` down to 1, take `j` as a bounded value with `sides = i + 1` and swap the entries at `i` and `j`.
      The result is the final list as decimal numbers separated by commas (`""` for `n = 0`). `n > 500` is an error.
''')

DL_FNS = [
    Fn("step", [("state", "u32")], "u32"),
    Fn("output", [("state", "u32")], "u32"),
    Fn("draw", [("seed", "u32"), ("index", "u32")], "u32"),
    Fn("roll", [("seed", "u32"), ("nth", "u32"), ("sides", "u32")], "u32", err=True),
    Fn("sum_dice", [("seed", "u32"), ("expr", "str")], "i32", err=True),
    Fn("shuffle", [("seed", "u32"), ("n", "u32")], "str", err=True),
]

DL_H = dd('''
    #ifndef DICE_LCG_H
    #define DICE_LCG_H

    #include <stddef.h>
    #include <stdint.h>

    /* Functions that can fail return 0 on success and a non-zero value on error; results go through `out`.
       Text results are NUL-terminated and must fit in `cap` bytes (including the NUL), otherwise the call fails. */
    uint32_t dice_lcg_step(uint32_t state);
    uint32_t dice_lcg_output(uint32_t state);
    uint32_t dice_lcg_draw(uint32_t seed, uint32_t index);
    int dice_lcg_roll(uint32_t seed, uint32_t nth, uint32_t sides, uint32_t *out);
    int dice_lcg_sum_dice(uint32_t seed, const char *expr, int32_t *out);
    int dice_lcg_shuffle(uint32_t seed, uint32_t n, char *out, size_t cap);

    #endif
''')

DL_C = dd(r'''
#include "dice_lcg.h"

#include <stdio.h>
#include <string.h>

uint32_t dice_lcg_step(uint32_t state) {
    return state * 747796405u + 2891336453u;
}

uint32_t dice_lcg_output(uint32_t state) {
    uint32_t word = ((state >> ((state >> 28) + 4)) ^ state) * 277803737u;
    return (word >> 22) ^ word;
}

uint32_t dice_lcg_draw(uint32_t seed, uint32_t index) {
    uint32_t s = seed, v = 0;
    for (uint32_t i = 0; i <= index; i++) {
        s = dice_lcg_step(s);
        v = dice_lcg_output(s);
        if (i == UINT32_MAX) break;
    }
    return v;
}

static uint32_t bounded(uint32_t *s, uint32_t sides) {
    uint32_t threshold = (0u - sides) % sides;
    for (;;) {
        *s = dice_lcg_step(*s);
        uint32_t v = dice_lcg_output(*s);
        if (v >= threshold) return v % sides;
    }
}

int dice_lcg_roll(uint32_t seed, uint32_t nth, uint32_t sides, uint32_t *out) {
    if (sides == 0) return -1;
    uint32_t s = seed, r = 0;
    for (uint32_t i = 0; i <= nth; i++) {
        r = bounded(&s, sides);
        if (i == UINT32_MAX) break;
    }
    *out = r + 1;
    return 0;
}

/* a number of 1 to maxdigits ASCII digits without a leading zero */
static int read_number(const char **p, int maxdigits, int *value) {
    const char *q = *p;
    int n = 0, v = 0;
    if (*q < '1' || *q > '9') return -1;
    while (*q >= '0' && *q <= '9') {
        v = v * 10 + (*q - '0');
        q++;
        if (++n > maxdigits) return -1;
    }
    *p = q;
    *value = v;
    return 0;
}

int dice_lcg_sum_dice(uint32_t seed, const char *expr, int32_t *out) {
    const char *p = expr;
    int count = 1, sides = 0, modifier = 0;
    if (*p != 'd') {
        if (read_number(&p, 3, &count)) return -1;
        if (*p != 'd') return -1;
    }
    p++;
    if (read_number(&p, 4, &sides)) return -1;
    if (*p == '+' || *p == '-') {
        char sign = *p++;
        if (read_number(&p, 5, &modifier)) return -1;
        if (modifier > 10000) return -1;
        if (sign == '-') modifier = -modifier;
    }
    if (*p != '\0') return -1;
    if (count < 1 || count > 100 || sides < 2 || sides > 1000) return -1;
    uint32_t s = seed;
    int32_t total = 0;
    for (int i = 0; i < count; i++) total += (int32_t)bounded(&s, (uint32_t)sides) + 1;
    *out = total + modifier;
    return 0;
}

int dice_lcg_shuffle(uint32_t seed, uint32_t n, char *out, size_t cap) {
    int a[500];
    if (n > 500) return -1;
    for (uint32_t i = 0; i < n; i++) a[i] = (int)i;
    uint32_t s = seed;
    for (uint32_t i = n; i-- > 1;) {
        uint32_t j = bounded(&s, i + 1);
        int t = a[i];
        a[i] = a[j];
        a[j] = t;
    }
    size_t pos = 0;
    if (cap == 0) return -1;
    out[0] = '\0';
    for (uint32_t i = 0; i < n; i++) {
        char tmp[16];
        int len = snprintf(tmp, sizeof tmp, i ? ",%d" : "%d", a[i]);
        if (pos + (size_t)len + 1 > cap) return -1;
        memcpy(out + pos, tmp, (size_t)len + 1);
        pos += (size_t)len;
    }
    return 0;
}
''')

DL_PY = dd(r'''
import re

_M = 0xFFFFFFFF
_DICE = re.compile(r"([1-9][0-9]{0,2})?d([1-9][0-9]{0,3})(?:([+-])([1-9][0-9]{0,4}))?")


def step(state):
    return (state * 747796405 + 2891336453) & _M


def output(state):
    word = (((state >> ((state >> 28) + 4)) ^ state) * 277803737) & _M
    return ((word >> 22) ^ word) & _M


def draw(seed, index):
    s, v = seed, 0
    for _ in range(index + 1):
        s = step(s)
        v = output(s)
    return v


def _bounded(s, sides):
    threshold = ((1 << 32) - sides) % sides
    while True:
        s = step(s)
        v = output(s)
        if v >= threshold:
            return s, v % sides


def roll(seed, nth, sides):
    if sides == 0:
        raise ValueError("sides must be positive")
    s, r = seed, 0
    for _ in range(nth + 1):
        s, r = _bounded(s, sides)
    return r + 1


def sum_dice(seed, expr):
    m = _DICE.fullmatch(expr)
    if not m:
        raise ValueError("bad dice notation")
    count = int(m.group(1)) if m.group(1) else 1
    sides = int(m.group(2))
    if not (1 <= count <= 100 and 2 <= sides <= 1000):
        raise ValueError("count or sides out of range")
    modifier = 0
    if m.group(3):
        modifier = int(m.group(4))
        if modifier > 10000:
            raise ValueError("modifier out of range")
        if m.group(3) == "-":
            modifier = -modifier
    s, total = seed, 0
    for _ in range(count):
        s, r = _bounded(s, sides)
        total += r + 1
    return total + modifier


def shuffle(seed, n):
    if n > 500:
        raise ValueError("too many items")
    a = list(range(n))
    s = seed
    for i in range(n - 1, 0, -1):
        s, j = _bounded(s, i + 1)
        a[i], a[j] = a[j], a[i]
    return ",".join(str(x) for x in a)
''')

DL_RS = dd(r'''
pub fn step(state: u32) -> u32 {
    state.wrapping_mul(747796405).wrapping_add(2891336453)
}

pub fn output(state: u32) -> u32 {
    let word = ((state >> ((state >> 28) + 4)) ^ state).wrapping_mul(277803737);
    (word >> 22) ^ word
}

pub fn draw(seed: u32, index: u32) -> u32 {
    let mut s = seed;
    let mut v = 0;
    for _ in 0..=(index as u64) {
        s = step(s);
        v = output(s);
    }
    v
}

fn bounded(s: &mut u32, sides: u32) -> u32 {
    let threshold = sides.wrapping_neg() % sides;
    loop {
        *s = step(*s);
        let v = output(*s);
        if v >= threshold {
            return v % sides;
        }
    }
}

pub fn roll(seed: u32, nth: u32, sides: u32) -> Result<u32, String> {
    if sides == 0 {
        return Err("sides must be positive".to_string());
    }
    let mut s = seed;
    let mut r = 0;
    for _ in 0..=(nth as u64) {
        r = bounded(&mut s, sides);
    }
    Ok(r + 1)
}

fn number(b: &[u8], pos: &mut usize, max_digits: usize) -> Option<i32> {
    let start = *pos;
    if start >= b.len() || !(b'1'..=b'9').contains(&b[start]) {
        return None;
    }
    let mut v: i32 = 0;
    let mut n = 0;
    while *pos < b.len() && b[*pos].is_ascii_digit() {
        v = v * 10 + (b[*pos] - b'0') as i32;
        *pos += 1;
        n += 1;
        if n > max_digits {
            return None;
        }
    }
    Some(v)
}

pub fn sum_dice(seed: u32, expr: &str) -> Result<i32, String> {
    let bad = || format!("bad dice notation: {:?}", expr);
    let b = expr.as_bytes();
    let mut pos = 0;
    let mut count = 1;
    if b.first() != Some(&b'd') {
        count = number(b, &mut pos, 3).ok_or_else(bad)?;
        if b.get(pos) != Some(&b'd') {
            return Err(bad());
        }
    }
    pos += 1;
    let sides = number(b, &mut pos, 4).ok_or_else(bad)?;
    let mut modifier = 0;
    if let Some(&c) = b.get(pos) {
        if c == b'+' || c == b'-' {
            pos += 1;
            modifier = number(b, &mut pos, 5).ok_or_else(bad)?;
            if modifier > 10000 {
                return Err(bad());
            }
            if c == b'-' {
                modifier = -modifier;
            }
        }
    }
    if pos != b.len() || !(1..=100).contains(&count) || !(2..=1000).contains(&sides) {
        return Err(bad());
    }
    let mut s = seed;
    let mut total: i32 = 0;
    for _ in 0..count {
        total += bounded(&mut s, sides as u32) as i32 + 1;
    }
    Ok(total + modifier)
}

pub fn shuffle(seed: u32, n: u32) -> Result<String, String> {
    if n > 500 {
        return Err("too many items".to_string());
    }
    let mut a: Vec<u32> = (0..n).collect();
    let mut s = seed;
    let mut i = n as usize;
    while i > 1 {
        i -= 1;
        let j = bounded(&mut s, (i + 1) as u32) as usize;
        a.swap(i, j);
    }
    Ok(a.iter().map(|x| x.to_string()).collect::<Vec<_>>().join(","))
}
''')


def dl_cases(rng):
    seeds = [0, 1, 42, 2**31, 2**32 - 1, 123456789, 0xDEADBEEF, 7, 99991]
    out = [("step", [0]), ("output", [1]), ("draw", [42, 0]), ("roll", [42, 0, 6]), ("sum_dice", [7, "3d6+2"]), ("shuffle", [42, 5]), ("draw", [0, 1]), ("roll", [1, 3, 20]), ("sum_dice", [1, "d20"]), ("shuffle", [7, 10])]
    for st in [0, 1, 0xFFFFFFFF, 0x10000000, 0x7FFFFFFF, 0x80000000, 0xF0000000, 0xFFFFFFF0, 12345]:
        out.append(("step", [st]))
        out.append(("output", [st]))
    for _ in range(20):
        st = rng.getrandbits(32)
        out.append(("step", [st]))
        out.append(("output", [st]))
    for seed in seeds:
        for index in [0, 1, 2, 10, 255, 1000]:
            out.append(("draw", [seed, index]))
    for _ in range(6):
        out.append(("draw", [rng.getrandbits(32), rng.randint(0, 100000)]))
    for sides in [1, 2, 3, 6, 7, 20, 100, 1000, 65535, 2**31 - 1, 2**31, 2**31 + 1, 3 * 2**30, 2**32 - 2, 2**32 - 1, 0]:
        for seed in seeds[:4]:
            out.append(("roll", [seed, rng.randint(0, 60), sides]))
    for _ in range(30):
        out.append(("roll", [rng.getrandbits(32), rng.randint(0, 2000), rng.choice([2, 4, 6, 8, 10, 12, 20, 100, 360, 1000003, 2**31 + 12345, 4000000000])]))
    out += [("roll", [5, 0, 1]), ("roll", [5, 1999, 6]), ("roll", [2**32 - 1, 2000, 2**31 + 1])]
    for expr in ["3d6", "d20", "1d20", "3d6+2", "2d10-1", "100d1000+10000", "100d1000-10000", "d2", "d1000", "1d2+1", "d6-9999", "10d10", "4d6-3", "d6+1", "50d20+1234",
                 "0d6", "101d6", "3d1", "3d1001", "3d6+0", "3d6-0", "3d6+10001", "03d6", "3d06", "3d6+02", "3D6", "3d6 ", " 3d6", "3d6+", "3d6-", "3d", "d", "3", "", "dd6", "3dd6", "3d6+2+1", "3d6*2", "-3d6", "+3d6",
                 "1000d6", "3d10000", "3d6+100000", "3d6\n", "\uff13d6", "3d\u0666", "3d6+\u0661", "d6d6", "3d6-1x"]:
        out.append(("sum_dice", [rng.choice(seeds), expr]))
    for _ in range(25):
        n = rng.randint(1, 30)
        s = rng.choice([2, 4, 6, 8, 10, 12, 20, 100])
        m = rng.choice(["", "", "+%d" % rng.randint(1, 20), "-%d" % rng.randint(1, 20)])
        out.append(("sum_dice", [rng.getrandbits(32), ("%dd%d%s" % (n, s, m)) if n > 1 or rng.random() < 0.5 else "d%d%s" % (s, m)]))
    for n in [0, 1, 2, 3, 5, 8, 10, 52, 100, 255, 499, 500, 501, 1000, 4294967295]:
        out.append(("shuffle", [rng.choice(seeds), n]))
    for _ in range(15):
        out.append(("shuffle", [rng.getrandbits(32), rng.randint(0, 60)]))
    return out


DL = PortLib(
    slug="dice-lcg",
    title="deterministic dice generator",
    blurb="A tabletop server replays games from a seed, so its dice, dice notation and shuffles come from a hand-rolled 32-bit generator that every client implementation has to reproduce exactly.",
    spec=DL_SPEC,
    fns=DL_FNS,
    impls={"c": {"src/dice_lcg.c": DL_C, "include/dice_lcg.h": DL_H}, "python": {"dice_lcg.py": DL_PY}, "rust": {"src/lib.rs": DL_RS}},
    cases=dl_cases,
    difficulty=4,
    n_examples=10,
    pairs=[("c", "rust", "full"), ("c", "python", "full"), ("rust", "python", "stub"), ("python", "rust", "stub")],
    traps=["unsigned 32-bit wraparound", "variable shift amounts", "rejection sampling consumes draws", "strict notation parsing", "Python unbounded integers"],
    tags=["u32", "prng", "c-source"],
)
register_port(DL, __name__)

# ======================================================================================================================
# shelf-pack: placing rectangles on a sheet with shelves (Python <-> Rust)
# ======================================================================================================================

SP_SPEC = dd('''
    A print shop places rectangular stickers on a sheet of fixed `width` and unlimited height by **shelf packing**. Items are placed one at a time in input order. All numbers are integers >= 1; `items` is a flat list
    `[w0, h0, w1, h1, ...]` of widths and heights, so its length must be even. A negative or zero width, a zero or negative dimension or an odd number of entries is an error.

    * A **shelf** is a horizontal row of the sheet. It has a `y` offset (the sum of the heights of the shelves below it), a fixed `height` (the height of the first item placed on it, never grown later) and a `used` width.
    * An item has two **orientations**: normal `(w, h)` and, when rotation is allowed and `w != h`, rotated `(h, w)`; the rotated one is listed second.
    * To place an item, look at every existing shelf in creation order and every orientation `(ow, oh)` that fits: `used + ow <= width` and `oh <= shelf.height`. Among the candidates choose the one with the smallest
      `shelf.height - oh`, then the smallest remaining width `width - used - ow`, then the earliest shelf, then the normal orientation.
    * When there is no candidate, open a new shelf at the top (at `y` = total height of all shelves so far) for the orientation with `ow <= width` and the smaller `oh` (on a tie the normal one). When neither orientation fits the sheet width the
      item is **rejected** and no shelf is opened.
    * A placed item sits at `x = shelf.used` (before adding it) and the shelf's `y`; afterwards `shelf.used += ow`.

    Functions (all take the same `width`, `items`, `rotate`):

    * `place` returns three numbers per item, in input order: `x, y, r` where `r` is 1 for the rotated orientation; a rejected item is `-1, -1, 0`.
    * `sheet_height` is the total height of all shelves. `shelf_count` is the number of shelves.
    * `rejected` returns the 0-based indices of the rejected items.
    * `waste_pm` is `floor(1000 * (width * sheet_height - placed_area) / (width * sheet_height))` where `placed_area` is the sum of the areas of the placed items; 0 when there are no shelves.
''')

SP_FNS = [
    Fn("place", [("width", "int"), ("items", "list<int>"), ("rotate", "bool")], "list<int>", err=True),
    Fn("sheet_height", [("width", "int"), ("items", "list<int>"), ("rotate", "bool")], "int", err=True),
    Fn("shelf_count", [("width", "int"), ("items", "list<int>"), ("rotate", "bool")], "int", err=True),
    Fn("rejected", [("width", "int"), ("items", "list<int>"), ("rotate", "bool")], "list<int>", err=True),
    Fn("waste_pm", [("width", "int"), ("items", "list<int>"), ("rotate", "bool")], "int", err=True),
]

SP_PY = dd(r'''
def _pack(width, items, rotate):
    if width < 1 or len(items) % 2 != 0 or any(v < 1 for v in items):
        raise ValueError("bad input")
    shelves = []  # [y, height, used]
    placed = []
    top = 0
    for k in range(0, len(items), 2):
        w, h = items[k], items[k + 1]
        orients = [(w, h, 0)]
        if rotate and w != h:
            orients.append((h, w, 1))
        best = None
        for si, shelf in enumerate(shelves):
            for ow, oh, r in orients:
                if shelf[2] + ow <= width and oh <= shelf[1]:
                    key = (shelf[1] - oh, width - shelf[2] - ow, si, r)
                    if best is None or key < best[0]:
                        best = (key, si, ow, oh, r)
        if best is not None:
            _, si, ow, oh, r = best
            placed.append((shelves[si][2], shelves[si][0], r, ow * oh))
            shelves[si][2] += ow
            continue
        fits = [o for o in orients if o[0] <= width]
        if not fits:
            placed.append((-1, -1, 0, 0))
            continue
        ow, oh, r = min(fits, key=lambda o: (o[1], o[2]))
        shelves.append([top, oh, ow])
        placed.append((0, top, r, ow * oh))
        top += oh
    return shelves, placed, top


def place(width, items, rotate):
    _, placed, _ = _pack(width, items, rotate)
    out = []
    for x, y, r, _ in placed:
        out += [x, y, r]
    return out


def sheet_height(width, items, rotate):
    return _pack(width, items, rotate)[2]


def shelf_count(width, items, rotate):
    return len(_pack(width, items, rotate)[0])


def rejected(width, items, rotate):
    _, placed, _ = _pack(width, items, rotate)
    return [i for i, p in enumerate(placed) if p[0] < 0]


def waste_pm(width, items, rotate):
    _, placed, top = _pack(width, items, rotate)
    if top == 0:
        return 0
    area = width * top
    used = sum(p[3] for p in placed)
    return 1000 * (area - used) // area
''')

SP_RS = dd(r'''
struct Shelf {
    y: i64,
    height: i64,
    used: i64,
}

struct Packed {
    shelves: usize,
    placed: Vec<(i64, i64, i64, i64)>,
    top: i64,
}

fn pack(width: i64, items: &[i64], rotate: bool) -> Result<Packed, String> {
    if width < 1 || items.len() % 2 != 0 || items.iter().any(|&v| v < 1) {
        return Err("bad input".to_string());
    }
    let mut shelves: Vec<Shelf> = Vec::new();
    let mut placed = Vec::new();
    let mut top = 0i64;
    for pair in items.chunks(2) {
        let (w, h) = (pair[0], pair[1]);
        let mut orients = vec![(w, h, 0i64)];
        if rotate && w != h {
            orients.push((h, w, 1));
        }
        let mut best: Option<((i64, i64, usize, i64), usize, i64, i64, i64)> = None;
        for (si, shelf) in shelves.iter().enumerate() {
            for &(ow, oh, r) in &orients {
                if shelf.used + ow <= width && oh <= shelf.height {
                    let key = (shelf.height - oh, width - shelf.used - ow, si, r);
                    if best.as_ref().map_or(true, |b| key < b.0) {
                        best = Some((key, si, ow, oh, r));
                    }
                }
            }
        }
        if let Some((_, si, ow, oh, r)) = best {
            placed.push((shelves[si].used, shelves[si].y, r, ow * oh));
            shelves[si].used += ow;
            continue;
        }
        let mut choice: Option<(i64, i64, i64)> = None;
        for &(ow, oh, r) in &orients {
            if ow <= width && choice.map_or(true, |c| oh < c.1) {
                choice = Some((ow, oh, r));
            }
        }
        match choice {
            None => placed.push((-1, -1, 0, 0)),
            Some((ow, oh, r)) => {
                shelves.push(Shelf { y: top, height: oh, used: ow });
                placed.push((0, top, r, ow * oh));
                top += oh;
            }
        }
    }
    Ok(Packed { shelves: shelves.len(), placed, top })
}

pub fn place(width: i64, items: &[i64], rotate: bool) -> Result<Vec<i64>, String> {
    let p = pack(width, items, rotate)?;
    let mut out = Vec::new();
    for (x, y, r, _) in p.placed {
        out.extend_from_slice(&[x, y, r]);
    }
    Ok(out)
}

pub fn sheet_height(width: i64, items: &[i64], rotate: bool) -> Result<i64, String> {
    Ok(pack(width, items, rotate)?.top)
}

pub fn shelf_count(width: i64, items: &[i64], rotate: bool) -> Result<i64, String> {
    Ok(pack(width, items, rotate)?.shelves as i64)
}

pub fn rejected(width: i64, items: &[i64], rotate: bool) -> Result<Vec<i64>, String> {
    let p = pack(width, items, rotate)?;
    Ok(p.placed.iter().enumerate().filter(|(_, e)| e.0 < 0).map(|(i, _)| i as i64).collect())
}

pub fn waste_pm(width: i64, items: &[i64], rotate: bool) -> Result<i64, String> {
    let p = pack(width, items, rotate)?;
    if p.top == 0 {
        return Ok(0);
    }
    let area = width * p.top;
    let used: i64 = p.placed.iter().map(|e| e.3).sum();
    Ok(1000 * (area - used) / area)
}
''')


def sp_cases(rng):
    out = [
        ("place", [10, [4, 3, 4, 2, 3, 3], False]), ("place", [10, [4, 3, 3, 4], True]), ("sheet_height", [10, [4, 3, 4, 2, 3, 3], False]), ("shelf_count", [10, [6, 2, 5, 2, 5, 2], False]),
        ("rejected", [5, [6, 2, 2, 7, 5, 5], True]), ("waste_pm", [10, [5, 5, 5, 5], False]), ("place", [8, [], True]), ("waste_pm", [8, [], False]),
    ]
    fixed = [
        (10, [4, 3, 4, 2, 3, 3]), (10, [4, 3, 3, 4]), (10, [6, 2, 5, 2, 5, 2]), (5, [6, 2, 2, 7, 5, 5]), (10, [5, 5, 5, 5]), (7, [3, 5, 4, 5, 3, 2, 4, 2]), (6, [2, 6, 6, 2, 3, 3, 3, 3]), (1, [1, 1, 1, 1, 2, 1]),
        (9, [4, 4, 4, 4, 1, 4, 4, 1, 4, 1]), (12, [5, 4, 5, 3, 2, 4, 2, 3, 12, 1, 1, 12, 7, 7]), (4, [4, 1, 1, 4, 2, 2, 2, 2, 2, 2]),
    ]
    for width, items in fixed:
        for rot in (False, True):
            for fn in ["place", "sheet_height", "shelf_count", "rejected", "waste_pm"]:
                out.append((fn, [width, items, rot]))
    for _ in range(40):
        width = rng.randint(3, 40)
        n = rng.randint(0, 14)
        hi = max(2, width + 3)
        items = []
        for _ in range(n):
            items += [rng.randint(1, hi), rng.randint(1, 12)]
        rot = rng.random() < 0.5
        for fn in ["place", "sheet_height", "waste_pm", "rejected", "shelf_count"]:
            if fn in ("place", "waste_pm") or rng.random() < 0.4:
                out.append((fn, [width, items, rot]))
    for width, items in [(0, [1, 1]), (-3, [1, 1]), (5, [1]), (5, [1, 2, 3]), (5, [0, 2]), (5, [2, 0]), (5, [-1, 2]), (5, [2, -2]), (5, [3, 3, 0, 1])]:
        for fn in ["place", "sheet_height", "shelf_count", "rejected", "waste_pm"]:
            out.append((fn, [width, items, rng.random() < 0.5]))
    return out


SP = PortLib(
    slug="shelf-pack",
    title="sticker sheet shelf packing",
    blurb="A print shop lays rectangular stickers out on a sheet in rows (shelves) with optional rotation, and its tie-breaking rules have to be reproduced exactly so that old orders reprint identically.",
    spec=SP_SPEC,
    fns=SP_FNS,
    impls={"python": {"shelf_pack.py": SP_PY}, "rust": {"src/lib.rs": SP_RS}},
    cases=sp_cases,
    difficulty=4,
    n_examples=10,
    pairs=[("python", "rust", "full"), ("rust", "python", "full"), ("python", "rust", "stub"), ("rust", "python", "stub")],
    traps=["multi-key tie-breaking (tuple comparison)", "floor division", "rejected items open no shelf", "fixed shelf heights"],
    tags=["packing", "tie-breaking"],
)
register_port(SP, __name__)
