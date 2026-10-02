"""Recipe scaling: exact rational amounts, unit ladders with promotion and demotion, kitchen fractions, minimum steps."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

KITCHENS = ["the lighthouse canteen", "the Hollin allotment society", "a ferry galley", "the library tea room", "the quay bakery", "the lamp-keepers' mess", "a harbour pie stall"]
VOL_NAMES = [["pinch", "dash", "spoon", "scoop", "jar"], ["nip", "tot", "gill", "mug", "pail"], ["dab", "dram", "ladle", "cup", "tub"], ["wisp", "drop", "sip", "bowl", "crock"]]
WT_NAMES = [["gr", "oz", "lb"], ["scrap", "bit", "block"], ["ct", "dr", "stone"], ["mite", "grain", "bar"]]
INGREDIENTS = ["flour", "salt", "sugar", "butter", "oats", "milk", "dried kelp", "smoked fish", "egg", "apple", "onion", "barley", "yeast", "cream cheese", "honey", "black pepper",
               "sea salt", "lemon juice", "river water", "pickled beet", "rye flour", "cinnamon", "stock", "mustard seed"]
LANG_PLAN = ["ruby", "javascript", "c", "rust", "ruby", "javascript", "c", "rust", "javascript", "ruby", "c", "rust"]


def params(rng, level, i):
    k = rng.choice(KITCHENS)
    vols = rng.choice(VOL_NAMES)
    wts = rng.choice(WT_NAMES)
    # ratios between neighbouring units
    vr = [1]
    for _ in range(len(vols) - 1):
        vr.append(vr[-1] * rng.choice([2, 3, 4, 6]))
    wr = [1]
    for _ in range(len(wts) - 1):
        wr.append(wr[-1] * rng.choice([4, 8, 12, 16]))
    nvol = len(vols) if level >= 3 else 3
    return {
        "level": level, "kitchen": k, "vol": list(zip(vols[:nvol], vr[:nvol])) if level >= 2 else [], "wt": list(zip(wts, wr)) if level >= 3 else [],
        "has_vol": level >= 2, "m": rng.choice([2, 3, 4, 8]) if level >= 2 else 1, "decimals": level >= 3, "mixed": level >= 2,
    }


PY = r'''
VOL = @VOL_PY@
WT = @WT_PY@
M = @M@
HAS_DEC = @DEC@
HAS_FRAC = @FRAC@
DG = "0123456789"


def digits(s, lo=1, hi=4):
    return lo <= len(s) <= hi and all(c in DG for c in s)


def gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def parse_amount(toks):
    """(num, den, tokens used) or None"""
    t = toks[0]
    if digits(t):
        if HAS_FRAC and len(toks) > 1 and "/" in toks[1]:
            p, _, q = toks[1].partition("/")
            if digits(p) and digits(q) and int(q) > 0:
                return int(t) * int(q) + int(p), int(q), 2
            return None
        return int(t), 1, 1
    if HAS_FRAC and "/" in t:
        p, _, q = t.partition("/")
        if digits(p) and digits(q) and int(q) > 0:
            return int(p), int(q), 1
        return None
    if HAS_DEC and "." in t:
        a, _, b = t.partition(".")
        if digits(a) and digits(b, 1, 3):
            return int(a + b), 10 ** len(b), 1
    return None


def find_unit(name):
    for ladder in (VOL, WT):
        for i, (n, sz) in enumerate(ladder):
            if n == name:
                return ladder, i
    return None


def fmt(k, m):
    whole, rem = divmod(k, m)
    if rem == 0:
        return str(whole)
    g = gcd(rem, m)
    frac = "%d/%d" % (rem // g, m // g)
    return frac if whole == 0 else "%d %s" % (whole, frac)


def scale(recipe, servings):
    if servings.count(":") != 1:
        return "error: servings"
    a, b = servings.split(":")
    if not (digits(a, 1, 3) and digits(b, 1, 3)) or int(a) == 0 or int(b) == 0:
        return "error: servings"
    f, t = int(a), int(b)
    out = []
    for no, raw in enumerate(recipe.split("\n"), 1):
        line = raw.strip(" \t")
        if line == "" or line[0] == "#":
            out.append(raw)
            continue
        toks = line.split()
        am = parse_amount(toks)
        if am is None:
            return "error: line %d" % no
        num, den, used = am
        rest = toks[used:]
        unit = None
        if rest and find_unit(rest[0]):
            unit = rest[0]
            rest = rest[1:]
        if not rest:
            return "error: line %d" % no
        name = " ".join(rest)
        num, den = num * t, den * f
        g = gcd(num, den) or 1
        num, den = num // g, den // g
        if unit is None:
            m = 1
            amt = (num, den)
            shown_unit = ""
        else:
            ladder, i = find_unit(unit)
            size0 = ladder[i][1]
            # exact amount in the smallest unit of the ladder
            base_n, base_d = num * size0, den
            chosen = 0
            for j, (n2, sz) in enumerate(ladder):
                if base_n >= sz * base_d:
                    chosen = j
            amt = (base_n, base_d * ladder[chosen][1])
            m = M if ladder is VOL else 1
            shown_unit = " " + ladder[chosen][0]
        n, d = amt
        if n == 0:
            out.append("0%s %s" % (shown_unit, name))
            continue
        k = (2 * n * m + d) // (2 * d)
        if k == 0:
            k = 1
        out.append("%s%s %s" % (fmt(k, m), shown_unit, name))
    return "\n".join(out)
'''

RB = r'''
module Recipescale
  VOL = @VOL_RB@
  WT = @WT_RB@
  M = @M@
  HAS_DEC = @DEC@
  HAS_FRAC = @FRAC@
  DG = '0123456789'

  def self.digits?(s, lo = 1, hi = 4)
    s.length >= lo && s.length <= hi && s.each_char.all? { |c| DG.include?(c) }
  end

  def self.gcd(a, b)
    a, b = b, a % b while b != 0
    a
  end

  def self.parse_amount(toks)
    t = toks[0]
    if digits?(t)
      if HAS_FRAC && toks.length > 1 && toks[1].include?('/')
        p, q = toks[1].split('/', 2)
        return [t.to_i * q.to_i + p.to_i, q.to_i, 2] if digits?(p) && digits?(q) && q.to_i > 0
        return nil
      end
      return [t.to_i, 1, 1]
    end
    if HAS_FRAC && t.include?('/')
      p, q = t.split('/', 2)
      return [p.to_i, q.to_i, 1] if digits?(p) && digits?(q) && q.to_i > 0
      return nil
    end
    if HAS_DEC && t.include?('.')
      a, b = t.split('.', 2)
      return [(a + b).to_i, 10**b.length, 1] if digits?(a) && digits?(b, 1, 3)
    end
    nil
  end

  def self.find_unit(name)
    [VOL, WT].each do |ladder|
      ladder.each_with_index { |(n, _), i| return [ladder, i] if n == name }
    end
    nil
  end

  def self.fmt(k, m)
    whole, rem = k.divmod(m)
    return whole.to_s if rem == 0
    g = gcd(rem, m)
    frac = "#{rem / g}/#{m / g}"
    whole == 0 ? frac : "#{whole} #{frac}"
  end

  def self.scale(recipe, servings)
    return 'error: servings' unless servings.count(':') == 1
    a, b = servings.split(':', -1)
    return 'error: servings' unless digits?(a, 1, 3) && digits?(b, 1, 3) && a.to_i != 0 && b.to_i != 0
    f = a.to_i
    t = b.to_i
    out = []
    recipe.split("\n", -1).each_with_index do |raw, idx|
      no = idx + 1
      line = raw.sub(/\A[ \t]+/, '').sub(/[ \t]+\z/, '')
      if line.empty? || line[0] == '#'
        out << raw
        next
      end
      toks = line.split
      am = parse_amount(toks)
      return "error: line #{no}" if am.nil?
      num, den, used = am
      rest = toks[used..]
      unit = nil
      if !rest.empty? && find_unit(rest[0])
        unit = rest[0]
        rest = rest[1..]
      end
      return "error: line #{no}" if rest.empty?
      name = rest.join(' ')
      num *= t
      den *= f
      g = gcd(num, den)
      g = 1 if g == 0
      num /= g
      den /= g
      if unit.nil?
        m = 1
        n = num
        d = den
        shown = ''
      else
        ladder, i = find_unit(unit)
        size0 = ladder[i][1]
        base_n = num * size0
        base_d = den
        chosen = 0
        ladder.each_with_index { |(_, sz), j| chosen = j if base_n >= sz * base_d }
        n = base_n
        d = base_d * ladder[chosen][1]
        m = ladder.equal?(VOL) ? M : 1
        shown = ' ' + ladder[chosen][0]
      end
      if n == 0
        out << "0#{shown} #{name}"
        next
      end
      k = (2 * n * m + d) / (2 * d)
      k = 1 if k == 0
      out << "#{fmt(k, m)}#{shown} #{name}"
    end
    out.join("\n")
  end
end
'''

JS = r'''
'use strict';

const VOL = @VOL_JS@;
const WT = @WT_JS@;
const M = @M@;
const HAS_DEC = @DEC@;
const HAS_FRAC = @FRAC@;
const DG = '0123456789';

function digits(s, lo = 1, hi = 4) {
  return s.length >= lo && s.length <= hi && [...s].every((c) => DG.includes(c));
}

function gcd(a, b) {
  while (b) { [a, b] = [b, a % b]; }
  return a;
}

function parseAmount(toks) {
  const t = toks[0];
  if (digits(t)) {
    if (HAS_FRAC && toks.length > 1 && toks[1].includes('/')) {
      const [p, q] = toks[1].split('/');
      if (toks[1].split('/').length === 2 && digits(p) && digits(q) && parseInt(q, 10) > 0) return [parseInt(t, 10) * parseInt(q, 10) + parseInt(p, 10), parseInt(q, 10), 2];
      return null;
    }
    return [parseInt(t, 10), 1, 1];
  }
  if (HAS_FRAC && t.includes('/')) {
    const parts = t.split('/');
    if (parts.length === 2 && digits(parts[0]) && digits(parts[1]) && parseInt(parts[1], 10) > 0) return [parseInt(parts[0], 10), parseInt(parts[1], 10), 1];
    return null;
  }
  if (HAS_DEC && t.includes('.')) {
    const parts = t.split('.');
    if (parts.length === 2 && digits(parts[0]) && digits(parts[1], 1, 3)) return [parseInt(parts[0] + parts[1], 10), 10 ** parts[1].length, 1];
  }
  return null;
}

function findUnit(name) {
  for (const ladder of [VOL, WT]) {
    for (let i = 0; i < ladder.length; i++) if (ladder[i][0] === name) return [ladder, i];
  }
  return null;
}

function fmt(k, m) {
  const whole = Math.floor(k / m);
  const rem = k % m;
  if (rem === 0) return String(whole);
  const g = gcd(rem, m);
  const frac = `${rem / g}/${m / g}`;
  return whole === 0 ? frac : `${whole} ${frac}`;
}

function scale(recipe, servings) {
  if (servings.split(':').length !== 2) return 'error: servings';
  const [a, b] = servings.split(':');
  if (!(digits(a, 1, 3) && digits(b, 1, 3)) || parseInt(a, 10) === 0 || parseInt(b, 10) === 0) return 'error: servings';
  const f = parseInt(a, 10);
  const t = parseInt(b, 10);
  const out = [];
  const lines = recipe.split('\n');
  for (let idx = 0; idx < lines.length; idx++) {
    const raw = lines[idx];
    const line = raw.replace(/^[ \t]+|[ \t]+$/g, '');
    if (line === '' || line[0] === '#') { out.push(raw); continue; }
    const toks = line.split(/[ \t\r\n\v\f]+/).filter((x) => x.length > 0);
    const am = parseAmount(toks);
    if (am === null) return `error: line ${idx + 1}`;
    let [num, den, used] = am;
    let rest = toks.slice(used);
    let unit = null;
    if (rest.length > 0 && findUnit(rest[0])) { unit = rest[0]; rest = rest.slice(1); }
    if (rest.length === 0) return `error: line ${idx + 1}`;
    const name = rest.join(' ');
    num *= t;
    den *= f;
    const g = gcd(num, den) || 1;
    num /= g;
    den /= g;
    let n, d, m, shown;
    if (unit === null) {
      m = 1; n = num; d = den; shown = '';
    } else {
      const [ladder, i] = findUnit(unit);
      const size0 = ladder[i][1];
      const baseN = num * size0;
      const baseD = den;
      let chosen = 0;
      ladder.forEach(([, sz], j) => { if (baseN >= sz * baseD) chosen = j; });
      n = baseN;
      d = baseD * ladder[chosen][1];
      m = ladder === VOL ? M : 1;
      shown = ' ' + ladder[chosen][0];
    }
    if (n === 0) { out.push(`0${shown} ${name}`); continue; }
    let k = Math.floor((2 * n * m + d) / (2 * d));
    if (k === 0) k = 1;
    out.push(`${fmt(k, m)}${shown} ${name}`);
  }
  return out.join('\n');
}

module.exports = { scale };
'''

RS = r'''
const VOL: &[(&str, i64)] = &@VOL_RS@;
const WT: &[(&str, i64)] = &@WT_RS@;
const M: i64 = @M@;
const HAS_DEC: bool = @DEC@;
const HAS_FRAC: bool = @FRAC@;

fn digits(s: &str, lo: usize, hi: usize) -> bool {
    s.len() >= lo && s.len() <= hi && s.bytes().all(|c| c.is_ascii_digit())
}

fn gcd(a: i64, b: i64) -> i64 {
    let (mut a, mut b) = (a, b);
    while b != 0 {
        let t = a % b;
        a = b;
        b = t;
    }
    a
}

fn num(s: &str) -> i64 {
    s.parse::<i64>().unwrap_or(0)
}

fn parse_amount(toks: &[&str]) -> Option<(i64, i64, usize)> {
    let t = toks[0];
    if digits(t, 1, 4) {
        if HAS_FRAC && toks.len() > 1 && toks[1].contains('/') {
            let parts: Vec<&str> = toks[1].split('/').collect();
            if parts.len() == 2 && digits(parts[0], 1, 4) && digits(parts[1], 1, 4) && num(parts[1]) > 0 {
                return Some((num(t) * num(parts[1]) + num(parts[0]), num(parts[1]), 2));
            }
            return None;
        }
        return Some((num(t), 1, 1));
    }
    if HAS_FRAC && t.contains('/') {
        let parts: Vec<&str> = t.split('/').collect();
        if parts.len() == 2 && digits(parts[0], 1, 4) && digits(parts[1], 1, 4) && num(parts[1]) > 0 {
            return Some((num(parts[0]), num(parts[1]), 1));
        }
        return None;
    }
    if HAS_DEC && t.contains('.') {
        let parts: Vec<&str> = t.split('.').collect();
        if parts.len() == 2 && digits(parts[0], 1, 4) && digits(parts[1], 1, 3) {
            return Some((num(&format!("{}{}", parts[0], parts[1])), 10i64.pow(parts[1].len() as u32), 1));
        }
    }
    None
}

fn find_unit(name: &str) -> Option<(&'static [(&'static str, i64)], bool, usize)> {
    for (i, (n, _)) in VOL.iter().enumerate() {
        if *n == name {
            return Some((VOL, true, i));
        }
    }
    for (i, (n, _)) in WT.iter().enumerate() {
        if *n == name {
            return Some((WT, false, i));
        }
    }
    None
}

fn fmt(k: i64, m: i64) -> String {
    let whole = k / m;
    let rem = k % m;
    if rem == 0 {
        return whole.to_string();
    }
    let g = gcd(rem, m);
    let frac = format!("{}/{}", rem / g, m / g);
    if whole == 0 { frac } else { format!("{} {}", whole, frac) }
}

/// Scales a recipe from one number of servings to another.
pub fn scale(recipe: &str, servings: &str) -> String {
    if servings.matches(':').count() != 1 {
        return "error: servings".to_string();
    }
    let sv: Vec<&str> = servings.split(':').collect();
    if !(digits(sv[0], 1, 3) && digits(sv[1], 1, 3)) || num(sv[0]) == 0 || num(sv[1]) == 0 {
        return "error: servings".to_string();
    }
    let (f, t) = (num(sv[0]), num(sv[1]));
    let mut out: Vec<String> = Vec::new();
    for (idx, raw) in recipe.split('\n').enumerate() {
        let line = raw.trim_matches(|c| c == ' ' || c == '\t');
        if line.is_empty() || line.starts_with('#') {
            out.push(raw.to_string());
            continue;
        }
        let toks: Vec<&str> = line.split_whitespace().collect();
        let (mut n0, mut d0, used) = match parse_amount(&toks) {
            Some(a) => a,
            None => return format!("error: line {}", idx + 1),
        };
        let mut rest: &[&str] = &toks[used..];
        let mut unit: Option<&str> = None;
        if !rest.is_empty() && find_unit(rest[0]).is_some() {
            unit = Some(rest[0]);
            rest = &rest[1..];
        }
        if rest.is_empty() {
            return format!("error: line {}", idx + 1);
        }
        let name = rest.join(" ");
        n0 *= t;
        d0 *= f;
        let g = gcd(n0, d0);
        let g = if g == 0 { 1 } else { g };
        n0 /= g;
        d0 /= g;
        let (n, d, m, shown): (i64, i64, i64, String);
        match unit {
            None => {
                n = n0;
                d = d0;
                m = 1;
                shown = String::new();
            }
            Some(u) => {
                let (ladder, is_vol, i) = find_unit(u).unwrap();
                let size0 = ladder[i].1;
                let base_n = n0 * size0;
                let base_d = d0;
                let mut chosen = 0;
                for (j, (_, sz)) in ladder.iter().enumerate() {
                    if base_n >= sz * base_d {
                        chosen = j;
                    }
                }
                n = base_n;
                d = base_d * ladder[chosen].1;
                m = if is_vol { M } else { 1 };
                shown = format!(" {}", ladder[chosen].0);
            }
        }
        if n == 0 {
            out.push(format!("0{} {}", shown, name));
            continue;
        }
        let mut k = (2 * n * m + d) / (2 * d);
        if k == 0 {
            k = 1;
        }
        out.push(format!("{}{} {}", fmt(k, m), shown, name));
    }
    out.join("\n")
}
'''

CC = r'''
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "recipescale.h"

typedef struct { const char *name; long size; } Unit;
static const Unit VOL[] = @VOL_C@;
static const Unit WT[] = @WT_C@;
#define NVOL ((int)(sizeof VOL / sizeof VOL[0]))
#define NWT ((int)(sizeof WT / sizeof WT[0]))
#define M @M@
#define HAS_DEC @DEC@
#define HAS_FRAC @FRAC@

static int digits(const char *s, size_t n, size_t lo, size_t hi) {
    if (n < lo || n > hi) return 0;
    for (size_t i = 0; i < n; i++) if (s[i] < '0' || s[i] > '9') return 0;
    return 1;
}

static long numv(const char *s, size_t n) {
    long v = 0;
    for (size_t i = 0; i < n; i++) v = v * 10 + (s[i] - '0');
    return v;
}

static long gcdl(long a, long b) {
    while (b) { long t = a % b; a = b; b = t; }
    return a;
}

static char *dupstr(const char *s) {
    char *r = malloc(strlen(s) + 1);
    strcpy(r, s);
    return r;
}

/* a/b with exactly one slash: sets num, den */
static int split_frac(const char *t, long *p, long *q) {
    const char *sl = strchr(t, '/');
    if (!sl || strchr(sl + 1, '/')) return 0;
    size_t lp = (size_t)(sl - t), lq = strlen(sl + 1);
    if (!digits(t, lp, 1, 4) || !digits(sl + 1, lq, 1, 4)) return 0;
    *p = numv(t, lp);
    *q = numv(sl + 1, lq);
    return *q > 0;
}

static int parse_amount(char **toks, int nt, long *num, long *den, int *used) {
    char *t = toks[0];
    long p, q;
    if (digits(t, strlen(t), 1, 4)) {
        if (HAS_FRAC && nt > 1 && strchr(toks[1], '/')) {
            if (split_frac(toks[1], &p, &q)) {
                *num = numv(t, strlen(t)) * q + p; *den = q; *used = 2;
                return 1;
            }
            return 0;
        }
        *num = numv(t, strlen(t)); *den = 1; *used = 1;
        return 1;
    }
    if (HAS_FRAC && strchr(t, '/')) {
        if (split_frac(t, &p, &q)) { *num = p; *den = q; *used = 1; return 1; }
        return 0;
    }
    if (HAS_DEC && strchr(t, '.')) {
        char *dot = strchr(t, '.');
        if (strchr(dot + 1, '.')) return 0;
        size_t la = (size_t)(dot - t), lb = strlen(dot + 1);
        if (digits(t, la, 1, 4) && digits(dot + 1, lb, 1, 3)) {
            long d = 1;
            for (size_t i = 0; i < lb; i++) d *= 10;
            *num = numv(t, la) * d + numv(dot + 1, lb);
            *den = d; *used = 1;
            return 1;
        }
    }
    return 0;
}

static const Unit *find_unit(const char *name, const Unit **ladder, int *n, int *idx, int *is_vol) {
    for (int i = 0; i < NVOL; i++) if (strcmp(VOL[i].name, name) == 0) { *ladder = VOL; *n = NVOL; *idx = i; *is_vol = 1; return &VOL[i]; }
    for (int i = 0; i < NWT; i++) if (strcmp(WT[i].name, name) == 0) { *ladder = WT; *n = NWT; *idx = i; *is_vol = 0; return &WT[i]; }
    return NULL;
}

static void fmt(char *out, long k, long m) {
    long whole = k / m, rem = k % m;
    if (rem == 0) { sprintf(out, "%ld", whole); return; }
    long g = gcdl(rem, m);
    if (whole == 0) sprintf(out, "%ld/%ld", rem / g, m / g);
    else sprintf(out, "%ld %ld/%ld", whole, rem / g, m / g);
}

static char *fail_line(int no) {
    char b[48];
    sprintf(b, "error: line %d", no);
    return dupstr(b);
}

char *scale(const char *recipe, const char *servings) {
    size_t sl = strlen(servings);
    const char *colon = strchr(servings, ':');
    if (!colon || strchr(colon + 1, ':')) return dupstr("error: servings");
    size_t la = (size_t)(colon - servings), lb = sl - la - 1;
    if (!digits(servings, la, 1, 3) || !digits(colon + 1, lb, 1, 3)) return dupstr("error: servings");
    long f = numv(servings, la), t = numv(colon + 1, lb);
    if (f == 0 || t == 0) return dupstr("error: servings");
    size_t cap = strlen(recipe) * 4 + 256, len = 0;
    char *out = malloc(cap);
    out[0] = 0;
    char *copy = dupstr(recipe);
    char *cur = copy;
    int no = 0;
    int first = 1;
    while (1) {
        char *nl = strchr(cur, '\n');
        if (nl) *nl = 0;
        no++;
        char *raw = cur;
        char line[1024];
        strncpy(line, raw, 1023);
        line[1023] = 0;
        char piece[512];
        const char *a = line;
        while (*a == ' ' || *a == '\t') a++;
        size_t ll = strlen(a);
        while (ll > 0 && (a[ll - 1] == ' ' || a[ll - 1] == '\t')) ll--;
        if (ll == 0 || a[0] == '#') {
            snprintf(piece, sizeof piece, "%s", raw);
        } else {
            char work[1024];
            memcpy(work, a, ll);
            work[ll] = 0;
            char *toks[64];
            int nt = 0;
            char *p = work;
            while (*p) {
                while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\v' || *p == '\f') *p++ = 0;
                if (!*p) break;
                toks[nt++] = p;
                while (*p && !(*p == ' ' || *p == '\t' || *p == '\r' || *p == '\v' || *p == '\f')) p++;
            }
            long num, den;
            int used;
            if (!parse_amount(toks, nt, &num, &den, &used)) { free(out); free(copy); return fail_line(no); }
            int ri = used;
            const Unit *ladder = NULL;
            int ln = 0, ui = 0, is_vol = 0;
            const Unit *u = NULL;
            if (ri < nt) u = find_unit(toks[ri], &ladder, &ln, &ui, &is_vol);
            if (u) ri++;
            if (ri >= nt) { free(out); free(copy); return fail_line(no); }
            char name[700];
            name[0] = 0;
            for (int k = ri; k < nt; k++) { if (k > ri) strcat(name, " "); strcat(name, toks[k]); }
            num *= t;
            den *= f;
            long g = gcdl(num, den);
            if (g == 0) g = 1;
            num /= g;
            den /= g;
            long n, d, m;
            char shown[64];
            shown[0] = 0;
            if (!u) {
                n = num; d = den; m = 1;
            } else {
                long size0 = ladder[ui].size;
                long base_n = num * size0, base_d = den;
                int chosen = 0;
                for (int j = 0; j < ln; j++) if (base_n >= ladder[j].size * base_d) chosen = j;
                n = base_n;
                d = base_d * ladder[chosen].size;
                m = is_vol ? M : 1;
                sprintf(shown, " %s", ladder[chosen].name);
            }
            if (n == 0) {
                snprintf(piece, sizeof piece, "0%s %s", shown, name);
            } else {
                long k = (2 * n * m + d) / (2 * d);
                if (k == 0) k = 1;
                char amt[64];
                fmt(amt, k, m);
                snprintf(piece, sizeof piece, "%s%s %s", amt, shown, name);
            }
        }
        size_t pl = strlen(piece);
        if (len + pl + 2 > cap) { cap = (len + pl + 2) * 2; out = realloc(out, cap); }
        if (!first) out[len++] = '\n';
        memcpy(out + len, piece, pl);
        len += pl;
        out[len] = 0;
        first = 0;
        if (!nl) break;
        cur = nl + 1;
    }
    free(copy);
    return out;
}
'''


def _b(lang, v):
    if lang == "python":
        return "True" if v else "False"
    if lang == "c":
        return "1" if v else "0"
    return "true" if v else "false"


def sol(lang, p):
    src = {"python": PY, "ruby": RB, "javascript": JS, "rust": RS, "c": CC}[lang]
    vol, wt = p["vol"], p["wt"]
    pair = lambda l, f: "[" + ", ".join(f(n, s) for n, s in l) + "]"  # noqa: E731
    return K.subst(
        src, M=p["m"], DEC=_b(lang, p["decimals"]), FRAC=_b(lang, p["mixed"]),
        VOL_PY=pair(vol, lambda n, s: f'("{n}", {s})'), WT_PY=pair(wt, lambda n, s: f'("{n}", {s})'),
        VOL_RB=pair(vol, lambda n, s: f'["{n}", {s}]'), WT_RB=pair(wt, lambda n, s: f'["{n}", {s}]'),
        VOL_JS=pair(vol, lambda n, s: f'["{n}", {s}]'), WT_JS=pair(wt, lambda n, s: f'["{n}", {s}]'),
        VOL_RS=pair(vol, lambda n, s: f'("{n}", {s})'), WT_RS=pair(wt, lambda n, s: f'("{n}", {s})'),
        VOL_C="{" + ", ".join(f'{{"{n}", {s}}}' for n, s in vol) + "}",
        WT_C="{" + (", ".join(f'{{"{n}", {s}}}' for n, s in wt) if wt else '{"", 0}') + "}",
    ).lstrip("\n")


def sol_c_fix(p):
    return sol("c", p)


# ---------------------------------------------------------------------------------------------------------------

def readme(p, api, lang, examples):
    m = p["m"]
    L = [f"# Recipe scaler for {p['kitchen']}", ""]
    L.append(f"The cooks at {p['kitchen']} keep recipes as plain text and scale them for the number of guests. `scale(recipe, servings)` rewrites every ingredient line for a new number of servings, "
             "using exact arithmetic and the house rules for rounding. This document is the whole specification.")
    L.append("")
    L.append("## Input")
    L.append("")
    L.append("`servings` is `FROM:TO`: two positive integers of one to three ASCII digits each (no sign, no blanks, exactly one colon, neither number zero). Anything else gives the result `error: servings`. "
             "The scale factor is `TO / FROM`, an exact fraction.")
    L.append("")
    L.append("`recipe` is text with lines separated by `\\n` (line numbers count from 1). A line that is empty after removing leading and trailing blanks (spaces, tabs), or whose first non-blank character is `#`, is a *note*: "
             "it is copied to the output exactly as it is (blanks included). Every other line is an *ingredient line*: whitespace-separated words, `AMOUNT [UNIT] NAME...`:")
    L.append("")
    am = ["an integer: one to four ASCII digits"]
    if p["mixed"]:
        am.append("a fraction `P/Q`: `P` and `Q` each one to four digits, `Q` greater than 0 (`P` may be 0)")
        am.append("a mixed number: an integer *word* followed by a fraction word, for example `1 1/2` (two words). If the word right after an integer contains a `/`, it must be a valid fraction (otherwise the line is an error)")
    if p["decimals"]:
        am.append("a decimal: digits, a point, one to three digits (`0.75`, `12.5`)")
    L.append("* **AMOUNT** is one of the following (nothing else is an amount: no signs, no `.5` or `5.`):")
    for a_ in am:
        L.append(f"    * {a_}")
    ladders = [("volume", p["vol"])]
    if p["has_vol"]:
        L.append("* **UNIT** is optional: if the word after the amount is one of the unit names below it is the unit, otherwise the line has no unit (and that word starts the name). Unit names are case-sensitive.")
    else:
        L.append("* There are no units in this kitchen: everything after the amount is the name.")
    L.append("* **NAME** is all remaining words, joined with single spaces on output; it must contain at least one word.")
    L.append("")
    L.append("A line whose amount is invalid or whose name would be empty makes the whole result `error: line N` (the first such line; nothing else is output).")
    L.append("")
    if p["has_vol"]:
        L.append("## Units")
        L.append("")
        L.append("Units come in *ladders*; within a ladder, each unit has a size in terms of the smallest unit of the ladder:")
        L.append("")
        L.append("| ladder | unit | size |")
        L.append("|---|---|---|")
        for n, s in p["vol"]:
            L.append(f"| volume | `{n}` | {s} |")
        for n, s in p["wt"]:
            L.append(f"| weight | `{n}` | {s} |")
        L.append("")
    L.append("## Scaling and rounding")
    L.append("")
    L.append("For an ingredient line, multiply the amount by the scale factor (exactly), then:")
    L.append("")
    if p["has_vol"]:
        L.append("1. **Choose the unit.** Without a unit, keep it that way. With a unit, express the exact value in the smallest unit of its ladder and choose the **largest unit of the ladder in which the value is at least 1** "
                 "(if the value is smaller than 1 even in the smallest unit, the smallest unit is used). The choice is made on the exact value, *before* rounding, and is never revised afterwards. Units never move between ladders.")
        L.append(f"2. **Round** the amount in the chosen unit to the nearest multiple of `1/{m}` for the volume ladder" + (" and to the nearest whole number for the weight ladder" if p["wt"] else "") + ", and for amounts without a unit to the nearest whole number; exact halves round **up**. "
                 "A value that is exactly 0 stays 0 and prints as `0`; any other value is never shown as less than one rounding step (so a tiny positive amount prints as `1/" + str(m) + "` or `1`).")
    else:
        L.append("1. **Round** the amount to the nearest whole number; exact halves round **up**. A value that is exactly 0 stays `0`; any other value is never shown as less than `1`.")
    L.append("")
    L.append("**Writing an amount** that is `k` rounding steps of `1/s` (`s` is " + (f"{m} for the volume ladder and 1 otherwise" if p["has_vol"] else "1") + "): the whole part is `k div s` and the remainder `k mod s` is a fraction `r/s` reduced to lowest terms "
             "(`2/4` is written `1/2`). Write the whole part if the fraction is zero, the fraction alone if the whole part is zero, otherwise the whole part, a blank and the fraction (`1 1/2`).")
    L.append("")
    L.append("Each ingredient line becomes `AMOUNT UNIT NAME` (or `AMOUNT NAME` when there is no unit), words separated by single blanks; lines are joined with `\\n`, with no trailing newline added (a recipe that ends with `\\n` produces a result that ends with `\\n` because its final empty line is a note).")
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    for (rec, sv), out in examples:
        L.append(f"Servings `{sv}`. Recipe:")
        L.append("")
        L.append(K.fence(rec))
        L.append("Result:")
        L.append("")
        L.append(K.fence(out))
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


def make_cases(rng, p, ns):
    vol, wt = p["vol"], p["wt"]
    m = p["m"]
    cases = []

    def add(rec, sv):
        cases.append((rec, sv))

    def amount():
        r = rng.random()
        if r < 0.45 or not p["mixed"]:
            return str(rng.randrange(1, 40))
        if r < 0.65:
            return f"{rng.randrange(1, 5)} {rng.randrange(1, 4)}/{rng.choice([2, 3, 4, 8])}"
        if r < 0.85:
            return f"{rng.randrange(1, 7)}/{rng.choice([2, 3, 4, 6, 8])}"
        if p["decimals"]:
            return f"{rng.randrange(0, 9)}.{rng.randrange(1, 10)}{rng.choice(['', '5', '25'])}"
        return str(rng.randrange(1, 12))

    def line(kind=None):
        k = kind or rng.choice(["vol", "vol", "wt", "cnt"] if wt else (["vol", "cnt"] if p["has_vol"] else ["cnt"]))
        ing = rng.choice(INGREDIENTS)
        if k == "vol" and p["has_vol"]:
            return f"{amount()} {rng.choice(vol)[0]} {ing}"
        if k == "wt" and wt:
            return f"{amount()} {rng.choice(wt)[0]} {ing}"
        return f"{amount()} {ing}"

    def recipe(n=None, notes=False):
        lines = []
        if notes:
            lines.append("# soup for the quay")
        for _ in range(n or rng.randrange(2, 7)):
            lines.append(line())
            if notes and rng.random() < 0.3:
                lines.append(rng.choice(["", "   ", "# note"]))
        return "\n".join(lines) + rng.choice(["", "\n"])

    def sv():
        a, b = rng.randrange(1, 13), rng.randrange(1, 25)
        return f"{a}:{b}"

    add(recipe(3), "4:6")
    add(recipe(4), "2:5")
    add(recipe(3, notes=True), "6:3")
    nex = len(cases)
    for _ in range(14):
        add(recipe(), sv())
    for _ in range(4):
        add(recipe(rng.randrange(6, 12), notes=True), sv())
    s0 = vol[0][0] if vol else "pinch"
    s1 = vol[1][0] if vol else "dash"
    s2 = vol[2][0] if vol else "spoon"
    # scale factors on a fixed small recipe
    base = f"1 {s0} salt\n3 {s1} flour\n2 egg\n"
    for s in ("1:1", "2:1", "1:2", "1:3", "3:1", "3:2", "2:3", "4:5", "5:4", "7:3", "1:100", "100:1", "10:1", "999:1", "1:999", "12:7"):
        add(base, s)
    # servings errors
    for bad in ("", ":", "1", "1:", ":1", "0:4", "4:0", "0:0", "1:2:3", "a:b", "-1:2", "1:-2", "+1:2", "1.5:2", "1 :2", " 1:2", "1:2 ", "1000:1", "1:1000", "01:2", "001:2", "1:002", "1,2"):
        add(base, bad)
    add("", "2:3")
    add("\n", "2:3")
    add("# nothing", "2:3")
    add("   \n\t\n", "2:3")
    add("2 egg", "1:1")
    add("2 egg\n", "1:1")
    add("\n\n2 egg\n\n", "1:2")
    # zero / minimum steps
    add("0 egg\n0 " + s0 + " salt\n1 egg\n1 " + s0 + " salt", "4:1")
    add("1 egg\n2 egg\n3 egg\n5 egg\n7 egg", "8:1")
    add("1 egg\n2 egg\n3 egg\n5 egg\n7 egg", "2:1")
    add("1 egg\n3 egg\n5 egg", "2:3")
    add("1 egg\n3 egg\n5 egg\n1 apple", "4:1")
    add("1 egg\n1 apple", "3:2")
    if p["has_vol"]:
        # ladder choice at boundaries
        for i, (n, s) in enumerate(vol):
            ratio = vol[i + 1][1] // s if i + 1 < len(vol) else None
            add(f"1 {n} sand", "1:1")
            add(f"1 {n} sand", "5:1")
            add(f"1 {n} sand", "1:5")
            add(f"1 {n} sand", "1:7")
            add(f"2 {n} sand", "3:2")
            if ratio:
                add(f"{ratio - 1} {n} sand", "1:1")
                add(f"{ratio} {n} sand", "1:1")
                add(f"{ratio + 1} {n} sand", "1:1")
                add(f"1 {n} sand", f"1:{ratio}")
                add(f"1 {n} sand", f"{ratio}:1" if ratio < 1000 else "1:1")
                add(f"1 {n} sand", f"1:{ratio + 1}")
                add(f"{ratio * ratio} {n} sand" if ratio * ratio < 10000 else f"9 {n} sand", "1:1")
        add(f"3 {s1} a b c", "1:1")
        add(f"3 {s1}   spaced    out   name  ", "1:2")
        add(f"\t3\t{s1}\tflour\t", "2:2")
        add(f"3 {s1}", "1:1")
        add(f"3 {s1} ", "1:1")
        add(f"3", "1:1")
        add(f"{s0}", "1:1")
        add(f"{s0} flour", "1:1")
        add(f"3 {s0.upper()} flour", "1:1")
        add(f"3 {s0}s flour", "1:1")
        add(f"3 egg {s0}", "1:2")
        add(f"3 {s0} {s1} flour", "2:1")
        add(f"3 {s0} {s0}", "2:1")
        # fraction rounding to 1/m
        for num_ in range(1, 4 * m + 1, 1):
            add(f"{num_}/{4 * m} {s2} oil", "1:1")
        add(f"1 {s2} oil", "1:" + str(m * 2))
        add(f"1 {s2} oil", "1:" + str(m * 2 + 1))
        add(f"3 {s2} oil", "1:" + str(m * 2))
        add(f"1/{m * 2} {s2} oil", "1:1")
        add(f"1/{m * 4} {s2} oil", "1:1")
        add(f"1/{m * 4} {s2} oil", "3:1")
        add(f"1/{m * 4} {s2} oil", "1:3")
    if p["mixed"]:
        for a in ("1/2", "3/4", "1 1/2", "2 3/4", "1/3", "2/3", "5/2", "0/5", "0 1/2", "1 0/3", "7/7", "1 7/7", "10/4", "1/1", "3/8", "12/1"):
            add(f"{a} egg" if not p["has_vol"] else f"{a} {s1} oil", "1:1")
            add(f"{a} egg" if not p["has_vol"] else f"{a} {s1} oil", "3:2")
        for bad in ("1/0 egg", "1/ egg", "/2 egg", "1//2 egg", "1/2/3 egg", "1 /2 egg", "1/ 2 egg", "a/2 egg", "1/b egg", "1 1/0 egg", "1 1/ egg", "1 x/2 egg", "-1/2 egg", "1/-2 egg", "12345/2 egg", "1/12345 egg", "1 1/2/3 egg", "1.5/2 egg", "1/2.5 egg", "1/2"):
            add(bad, "1:1")
            add("2 egg\n" + bad, "1:1")
    else:
        for bad in ("1/2 egg", "1.5 egg", "1/2"):
            add(bad, "1:1")
    if p["decimals"]:
        for a in ("0.5", "0.25", "0.125", "0.75", "1.5", "12.5", "0.001", "0.0", "0.00", "00.5", "3.14", "99.999", "0.333", "10.10", "7.0", "1.25"):
            add(f"{a} {s1} oil", "1:1")
            add(f"{a} {s1} oil", "5:3")
            add(f"{a} egg", "1:1")
            add(f"{a} egg", "2:1")
        for bad in (".5 egg", "5. egg", "1.2.3 egg", "1.2345 egg", "1,5 egg", "1.5.5 egg", "1. 5 egg", "12345.5 egg", "1.e5 egg", "..5 egg", "-1.5 egg", "1.5/2 egg"):
            add(bad, "1:1")
        for n_, s_ in wt:
            add(f"1 {n_} salt", "1:1")
            add(f"1 {n_} salt", "7:3")
            add(f"{s_} {n_} salt", "1:1")
        if len(wt) >= 2:
            ratio = wt[1][1]
            add(f"{ratio - 1} {wt[0][0]} salt", "1:1")
            add(f"{ratio} {wt[0][0]} salt", "1:1")
            add(f"1 {wt[1][0]} salt", f"1:{ratio}")
            add(f"1 {wt[1][0]} salt", f"1:{ratio * 2}")
            add(f"1 {wt[1][0]} salt", f"1:{ratio * 2 + 1}")
            add(f"3 {wt[1][0]} salt", f"1:{ratio * 3}")
            add(f"1/2 {wt[0][0]} salt", "1:1")
            add(f"1 1/2 {wt[1][0]} salt", "1:1")
    else:
        for bad in ("0.5 egg", "1.5 egg", "1.5 " + s0 + " egg" if p["has_vol"] else "1.5 egg"):
            add(bad, "1:1")
    # bad lines
    add("2 egg\nbogus line\n3 egg", "1:1")
    add("2 egg\n3\n", "1:1")
    add("x\n3", "1:1")
    add("# c\n\n  3  \n", "1:1")
    add("2 egg\n# 3\n  # indented\n3 egg", "2:1")
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
    k = p["kitchen"]
    opts = [
        f"{k.capitalize()} needs a recipe scaler: `{fn}(recipe, servings)` in {ln}, in {where}. The README spells out the units, the kitchen fractions, how amounts are written and which line is reported on a mistake. {K.closer(rng)}",
        f"Please implement the recipe scaling routine from README.md ({ln}, `{fn}`, {where}). Exact fractions only - no floating point. Hidden checks look at rounding of halves, tiny amounts and unit changes.",
        f"scale recipes for {k}. {ln}. function `{fn}`, file {where}. read README.md: unit ladders, 'largest unit with at least 1', rounding up on halves, minimum step. {K.closer(rng)}",
        f"Task: write `{fn}` ({ln}) as specified in README.md. It takes a recipe text and a `FROM:TO` servings string and returns the rewritten recipe. Put the code in {where}.",
    ]
    return rng.choice(opts).strip()


@family("greenfield-recipescale", category="greenfield", lang="mixed", kind="greenfield", n=12,
        summary="recipe scaler: exact fractions, unit ladders with promotion/demotion on the exact value, kitchen-fraction rounding, minimum step, line errors")
def gen(rng, n):
    levels = [1, 2, 2, 3, 3, 1, 2, 3, 3, 2, 3, 1]
    diffs = [1, 2, 2, 3, 4, 1, 2, 3, 3, 2, 4, 1]
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level, i)
        api = K.Api(mod="recipescale", fn="scale", args=["recipe", "servings"], arg_docs=["the recipe text", "`FROM:TO`, the old and the new number of servings"],
                    ret_doc="the rewritten recipe, or an `error: ...` text", doc="recipe scaler")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["scale"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=diffs[i % len(diffs)], slug=f"{i + 1:02d}-{lang}-m{p['m']}-l{level}", oracle=(None if lang == "python" else ns["scale"]),
            tags=["parser", "fractions", "formatting"], notes={"level": level, "m": p["m"]},
        )
