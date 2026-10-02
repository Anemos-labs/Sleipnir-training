"""Pattern matcher with an invented notation: wildcards, classes, case flag, captures, nested groups, greedy runs, back-references (exact error positions)."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

PY = r'''
S_ANY = @S_ANY@
S_LAZY = @S_LAZY@
S_GREEDY = @S_GREEDY@
S_FLAG = @S_FLAG@
S_NEG = @S_NEG@
S_OPEN = @S_OPEN@
S_CLOSE = @S_CLOSE@
S_ALT = @S_ALT@
S_REF = @S_REF@
HAS_CLASS = @CLASS@
HAS_FLAG = @FLAGS@
HAS_CAPS = @CAPS@
HAS_GROUPS = @GROUPS@
HAS_REF = @REFS@


class Err(Exception):
    pass


def lower(c):
    return chr(ord(c) + 32) if "A" <= c <= "Z" else c


def swap(c):
    if "a" <= c <= "z":
        return chr(ord(c) - 32)
    if "A" <= c <= "Z":
        return chr(ord(c) + 32)
    return c


class Parser:
    def __init__(self, pat):
        self.pat = pat
        self.n = len(pat)
        self.count = 0
        self.closed = set()

    def newcap(self):
        if not HAS_CAPS:
            return 0
        self.count += 1
        return self.count

    def alts(self, i, depth):
        """parse alternatives up to a close char (depth > 0) or the end; returns (alts, i)"""
        out = []
        while True:
            seq, i = self.seq(i, depth)
            out.append(seq)
            if depth > 0 and i < self.n and self.pat[i] == S_ALT:
                i += 1
                continue
            return out, i

    def seq(self, i, depth):
        pat, n = self.pat, self.n
        items = []
        while i < n:
            c = pat[i]
            if depth > 0 and c == S_ALT and HAS_GROUPS:
                break
            if HAS_GROUPS and c == S_CLOSE:
                if depth == 0:
                    raise Err("error: pattern at %d: group" % (i + 1))
                break
            if c == "\\":
                if i + 1 >= n:
                    raise Err("error: pattern at %d: escape" % (i + 1))
                items.append(("lit", pat[i + 1]))
                i += 2
            elif c == S_ANY:
                num = self.newcap()
                items.append(("any", num))
                if num:
                    self.closed.add(num)
                i += 1
            elif c == S_LAZY:
                num = self.newcap()
                items.append(("lazy", num))
                if num:
                    self.closed.add(num)
                i += 1
            elif HAS_REF and c == S_GREEDY:
                num = self.newcap()
                items.append(("greedy", num))
                if num:
                    self.closed.add(num)
                i += 1
            elif HAS_CLASS and c == "[":
                it, i = self.cls(i)
                items.append(it)
            elif HAS_GROUPS and c == S_OPEN:
                num = self.newcap()
                alts, j = self.alts(i + 1, depth + 1)
                if j >= n:
                    raise Err("error: pattern at %d: group" % (i + 1))
                if num:
                    self.closed.add(num)
                items.append(("grp", num, alts))
                i = j + 1
            elif HAS_REF and c == S_REF:
                if i + 1 >= n or not ("1" <= pat[i + 1] <= "9") or int(pat[i + 1]) not in self.closed:
                    raise Err("error: pattern at %d: reference" % (i + 1))
                items.append(("ref", int(pat[i + 1])))
                i += 2
            else:
                items.append(("lit", c))
                i += 1
        return items, i

    def cls(self, start):
        pat, n = self.pat, self.n
        j = start + 1
        neg = False
        if j < n and pat[j] == S_NEG:
            neg = True
            j += 1
        ranges = []
        first = True
        while True:
            if j >= n:
                raise Err("error: pattern at %d: class" % (start + 1))
            c = pat[j]
            if c == "]" and not first:
                j += 1
                break
            first = False
            lo_at = j
            if c == "\\":
                if j + 1 >= n:
                    raise Err("error: pattern at %d: class" % (start + 1))
                lo = pat[j + 1]
                j += 2
            else:
                lo = c
                j += 1
            if j + 1 < n and pat[j] == "-" and pat[j + 1] != "]":
                if pat[j + 1] == "\\":
                    if j + 2 >= n:
                        raise Err("error: pattern at %d: class" % (start + 1))
                    hi = pat[j + 2]
                    j += 3
                else:
                    hi = pat[j + 1]
                    j += 2
                if hi < lo:
                    raise Err("error: pattern at %d: range" % (lo_at + 1))
                ranges.append((lo, hi))
            else:
                ranges.append((lo, lo))
        num = self.newcap()
        if num:
            self.closed.add(num)
        return ("cls", ranges, neg, num), j


def stencil(pattern, text):
    try:
        return do_match(pattern, text)
    except Err as e:
        return str(e)


def do_match(pattern, text):
    fold = False
    body = pattern
    off = 0
    if HAS_FLAG and pattern[:1] == S_FLAG:
        fold = True
        off = 1
    p = Parser(pattern)
    p.pat = pattern
    items, i = p.alts(off, 0)
    root = items[0]
    T = text
    caps = [None] * (p.count + 1)

    def eq(a, b):
        return lower(a) == lower(b) if fold else a == b

    def inclass(ch, ranges, neg):
        hit = False
        for lo, hi in ranges:
            if lo <= ch <= hi or (fold and lo <= swap(ch) <= hi):
                hit = True
        return hit != neg

    def setcap(num, s, e):
        old = caps[num] if num else None
        if num:
            caps[num] = (s, e)
        return old

    def resume(cont, pos):
        if cont is None:
            return pos == len(T)
        if cont[0] == "seq":
            return run(cont[1], cont[2], pos, cont[3])
        g, start, nxt = cont[1], cont[2], cont[3]
        old = caps[g]
        caps[g] = (start, pos)
        if resume(nxt, pos):
            return True
        caps[g] = old
        return False

    def run(seq, idx, pos, cont):
        if idx == len(seq):
            return resume(cont, pos)
        it = seq[idx]
        k = it[0]
        if k == "lit":
            return pos < len(T) and eq(T[pos], it[1]) and run(seq, idx + 1, pos + 1, cont)
        if k == "any":
            if pos >= len(T):
                return False
            old = setcap(it[1], pos, pos + 1)
            if run(seq, idx + 1, pos + 1, cont):
                return True
            if it[1]:
                caps[it[1]] = old
            return False
        if k == "cls":
            if pos >= len(T) or not inclass(T[pos], it[1], it[2]):
                return False
            old = setcap(it[3], pos, pos + 1)
            if run(seq, idx + 1, pos + 1, cont):
                return True
            if it[3]:
                caps[it[3]] = old
            return False
        if k in ("lazy", "greedy"):
            span = range(0, len(T) - pos + 1) if k == "lazy" else range(len(T) - pos, -1, -1)
            for w in span:
                old = setcap(it[1], pos, pos + w)
                if run(seq, idx + 1, pos + w, cont):
                    return True
                if it[1]:
                    caps[it[1]] = old
            return False
        if k == "grp":
            for alt in it[2]:
                frame = ("end", it[1], pos, ("seq", seq, idx + 1, cont))
                if run(alt, 0, pos, frame):
                    return True
            return False
        if k == "ref":
            c = caps[it[1]]
            if c is None:
                return False
            s = T[c[0]:c[1]]
            w = len(s)
            if pos + w > len(T):
                return False
            for a, b in zip(s, T[pos:pos + w]):
                if not eq(a, b):
                    return False
            return run(seq, idx + 1, pos + w, cont)
        raise AssertionError(k)

    if not run(root, 0, 0, None):
        return "no"
    if not HAS_CAPS:
        return "yes"
    out = "yes"
    for c in caps[1:]:
        out += " [%s]" % ("" if c is None else T[c[0]:c[1]])
    return out
'''

JS = r'''
'use strict';
const S_ANY = @S_ANY@;
const S_LAZY = @S_LAZY@;
const S_GREEDY = @S_GREEDY@;
const S_FLAG = @S_FLAG@;
const S_NEG = @S_NEG@;
const S_OPEN = @S_OPEN@;
const S_CLOSE = @S_CLOSE@;
const S_ALT = @S_ALT@;
const S_REF = @S_REF@;
const HAS_CLASS = @CLASS@;
const HAS_FLAG = @FLAGS@;
const HAS_CAPS = @CAPS@;
const HAS_GROUPS = @GROUPS@;
const HAS_REF = @REFS@;

class Err extends Error {}

function lower(c) {
  return c >= 'A' && c <= 'Z' ? String.fromCharCode(c.charCodeAt(0) + 32) : c;
}

function swap(c) {
  if (c >= 'a' && c <= 'z') return String.fromCharCode(c.charCodeAt(0) - 32);
  if (c >= 'A' && c <= 'Z') return String.fromCharCode(c.charCodeAt(0) + 32);
  return c;
}

class Parser {
  constructor(pat) {
    this.pat = pat;
    this.n = pat.length;
    this.count = 0;
    this.closed = new Set();
  }

  newcap() {
    if (!HAS_CAPS) return 0;
    this.count += 1;
    return this.count;
  }

  alts(i, depth) {
    const out = [];
    for (;;) {
      const [seq, j] = this.seq(i, depth);
      out.push(seq);
      i = j;
      if (depth > 0 && i < this.n && this.pat[i] === S_ALT) {
        i += 1;
        continue;
      }
      return [out, i];
    }
  }

  seq(i, depth) {
    const pat = this.pat;
    const n = this.n;
    const items = [];
    while (i < n) {
      const c = pat[i];
      if (depth > 0 && c === S_ALT && HAS_GROUPS) break;
      if (HAS_GROUPS && c === S_CLOSE) {
        if (depth === 0) throw new Err('error: pattern at ' + (i + 1) + ': group');
        break;
      }
      if (c === '\\') {
        if (i + 1 >= n) throw new Err('error: pattern at ' + (i + 1) + ': escape');
        items.push({ k: 'lit', c: pat[i + 1] });
        i += 2;
      } else if (c === S_ANY) {
        const num = this.newcap();
        items.push({ k: 'any', num });
        if (num) this.closed.add(num);
        i += 1;
      } else if (c === S_LAZY) {
        const num = this.newcap();
        items.push({ k: 'lazy', num });
        if (num) this.closed.add(num);
        i += 1;
      } else if (HAS_REF && c === S_GREEDY) {
        const num = this.newcap();
        items.push({ k: 'greedy', num });
        if (num) this.closed.add(num);
        i += 1;
      } else if (HAS_CLASS && c === '[') {
        const [it, j] = this.cls(i);
        items.push(it);
        i = j;
      } else if (HAS_GROUPS && c === S_OPEN) {
        const num = this.newcap();
        const [alts, j] = this.alts(i + 1, depth + 1);
        if (j >= n) throw new Err('error: pattern at ' + (i + 1) + ': group');
        if (num) this.closed.add(num);
        items.push({ k: 'grp', num, alts });
        i = j + 1;
      } else if (HAS_REF && c === S_REF) {
        if (i + 1 >= n || !(pat[i + 1] >= '1' && pat[i + 1] <= '9') || !this.closed.has(Number(pat[i + 1]))) throw new Err('error: pattern at ' + (i + 1) + ': reference');
        items.push({ k: 'ref', n: Number(pat[i + 1]) });
        i += 2;
      } else {
        items.push({ k: 'lit', c });
        i += 1;
      }
    }
    return [items, i];
  }

  cls(start) {
    const pat = this.pat;
    const n = this.n;
    let j = start + 1;
    let neg = false;
    if (j < n && pat[j] === S_NEG) {
      neg = true;
      j += 1;
    }
    const ranges = [];
    let first = true;
    for (;;) {
      if (j >= n) throw new Err('error: pattern at ' + (start + 1) + ': class');
      const c = pat[j];
      if (c === ']' && !first) {
        j += 1;
        break;
      }
      first = false;
      const loAt = j;
      let lo;
      if (c === '\\') {
        if (j + 1 >= n) throw new Err('error: pattern at ' + (start + 1) + ': class');
        lo = pat[j + 1];
        j += 2;
      } else {
        lo = c;
        j += 1;
      }
      if (j + 1 < n && pat[j] === '-' && pat[j + 1] !== ']') {
        let hi;
        if (pat[j + 1] === '\\') {
          if (j + 2 >= n) throw new Err('error: pattern at ' + (start + 1) + ': class');
          hi = pat[j + 2];
          j += 3;
        } else {
          hi = pat[j + 1];
          j += 2;
        }
        if (hi < lo) throw new Err('error: pattern at ' + (loAt + 1) + ': range');
        ranges.push([lo, hi]);
      } else {
        ranges.push([lo, lo]);
      }
    }
    const num = this.newcap();
    if (num) this.closed.add(num);
    return [{ k: 'cls', ranges, neg, num }, j];
  }
}

function doMatch(pattern, T) {
  let fold = false;
  let off = 0;
  if (HAS_FLAG && pattern.length > 0 && pattern[0] === S_FLAG) {
    fold = true;
    off = 1;
  }
  const p = new Parser(pattern);
  const [alts] = p.alts(off, 0);
  const root = alts[0];
  const caps = new Array(p.count + 1).fill(null);

  const eq = (a, b) => (fold ? lower(a) === lower(b) : a === b);
  const inclass = (ch, ranges, neg) => {
    let hit = false;
    for (const [lo, hi] of ranges) if ((lo <= ch && ch <= hi) || (fold && lo <= swap(ch) && swap(ch) <= hi)) hit = true;
    return hit !== neg;
  };

  function resume(cont, pos) {
    if (cont === null) return pos === T.length;
    if (cont.t === 'seq') return run(cont.seq, cont.idx, pos, cont.next);
    const old = caps[cont.g];
    caps[cont.g] = [cont.start, pos];
    if (resume(cont.next, pos)) return true;
    caps[cont.g] = old;
    return false;
  }

  function run(seq, idx, pos, cont) {
    if (idx === seq.length) return resume(cont, pos);
    const it = seq[idx];
    switch (it.k) {
      case 'lit':
        return pos < T.length && eq(T[pos], it.c) && run(seq, idx + 1, pos + 1, cont);
      case 'any':
      case 'cls': {
        if (pos >= T.length) return false;
        if (it.k === 'cls' && !inclass(T[pos], it.ranges, it.neg)) return false;
        const old = it.num ? caps[it.num] : null;
        if (it.num) caps[it.num] = [pos, pos + 1];
        if (run(seq, idx + 1, pos + 1, cont)) return true;
        if (it.num) caps[it.num] = old;
        return false;
      }
      case 'lazy':
      case 'greedy': {
        const max = T.length - pos;
        for (let s = 0; s <= max; s++) {
          const w = it.k === 'lazy' ? s : max - s;
          const old = it.num ? caps[it.num] : null;
          if (it.num) caps[it.num] = [pos, pos + w];
          if (run(seq, idx + 1, pos + w, cont)) return true;
          if (it.num) caps[it.num] = old;
        }
        return false;
      }
      case 'grp':
        for (const alt of it.alts) {
          const frame = { t: 'end', g: it.num, start: pos, next: { t: 'seq', seq, idx: idx + 1, next: cont } };
          if (run(alt, 0, pos, frame)) return true;
        }
        return false;
      case 'ref': {
        const c = caps[it.n];
        if (c === null) return false;
        const s = T.slice(c[0], c[1]);
        if (pos + s.length > T.length) return false;
        for (let k = 0; k < s.length; k++) if (!eq(s[k], T[pos + k])) return false;
        return run(seq, idx + 1, pos + s.length, cont);
      }
      default:
        throw new Error('bad item');
    }
  }

  if (!run(root, 0, 0, null)) return 'no';
  if (!HAS_CAPS) return 'yes';
  let out = 'yes';
  for (let k = 1; k < caps.length; k++) out += ' [' + (caps[k] === null ? '' : T.slice(caps[k][0], caps[k][1])) + ']';
  return out;
}

function stencil(pattern, text) {
  try {
    return doMatch(pattern, text);
  } catch (e) {
    if (e instanceof Err) return e.message;
    throw e;
  }
}

module.exports = { stencil };
'''

RS = r'''
const S_ANY: u8 = @S_ANY@;
const S_LAZY: u8 = @S_LAZY@;
const S_GREEDY: u8 = @S_GREEDY@;
const S_FLAG: u8 = @S_FLAG@;
const S_NEG: u8 = @S_NEG@;
const S_OPEN: u8 = @S_OPEN@;
const S_CLOSE: u8 = @S_CLOSE@;
const S_ALT: u8 = @S_ALT@;
const S_REF: u8 = @S_REF@;
const HAS_CLASS: bool = @CLASS@;
const HAS_FLAG: bool = @FLAGS@;
const HAS_CAPS: bool = @CAPS@;
const HAS_GROUPS: bool = @GROUPS@;
const HAS_REF: bool = @REFS@;

enum Item {
    Lit(u8),
    Any(usize),
    Lazy(usize),
    Greedy(usize),
    Cls(Vec<(u8, u8)>, bool, usize),
    Grp(usize, Vec<Vec<Item>>),
    Ref(usize),
}

fn lower(c: u8) -> u8 {
    if c.is_ascii_uppercase() {
        c + 32
    } else {
        c
    }
}

fn swap(c: u8) -> u8 {
    if c.is_ascii_lowercase() {
        c - 32
    } else if c.is_ascii_uppercase() {
        c + 32
    } else {
        c
    }
}

struct Parser<'a> {
    pat: &'a [u8],
    n: usize,
    count: usize,
    closed: Vec<usize>,
}

impl<'a> Parser<'a> {
    fn newcap(&mut self) -> usize {
        if !HAS_CAPS {
            return 0;
        }
        self.count += 1;
        self.count
    }

    fn alts(&mut self, mut i: usize, depth: usize) -> Result<(Vec<Vec<Item>>, usize), String> {
        let mut out = Vec::new();
        loop {
            let (seq, j) = self.seq(i, depth)?;
            out.push(seq);
            i = j;
            if depth > 0 && i < self.n && self.pat[i] == S_ALT {
                i += 1;
                continue;
            }
            return Ok((out, i));
        }
    }

    fn seq(&mut self, mut i: usize, depth: usize) -> Result<(Vec<Item>, usize), String> {
        let n = self.n;
        let mut items: Vec<Item> = Vec::new();
        while i < n {
            let c = self.pat[i];
            if depth > 0 && c == S_ALT && HAS_GROUPS {
                break;
            }
            if HAS_GROUPS && c == S_CLOSE {
                if depth == 0 {
                    return Err(format!("error: pattern at {}: group", i + 1));
                }
                break;
            }
            if c == b'\\' {
                if i + 1 >= n {
                    return Err(format!("error: pattern at {}: escape", i + 1));
                }
                items.push(Item::Lit(self.pat[i + 1]));
                i += 2;
            } else if c == S_ANY {
                let num = self.newcap();
                items.push(Item::Any(num));
                if num > 0 {
                    self.closed.push(num);
                }
                i += 1;
            } else if c == S_LAZY {
                let num = self.newcap();
                items.push(Item::Lazy(num));
                if num > 0 {
                    self.closed.push(num);
                }
                i += 1;
            } else if HAS_REF && c == S_GREEDY {
                let num = self.newcap();
                items.push(Item::Greedy(num));
                if num > 0 {
                    self.closed.push(num);
                }
                i += 1;
            } else if HAS_CLASS && c == b'[' {
                let (it, j) = self.cls(i)?;
                items.push(it);
                i = j;
            } else if HAS_GROUPS && c == S_OPEN {
                let num = self.newcap();
                let (alts, j) = self.alts(i + 1, depth + 1)?;
                if j >= n {
                    return Err(format!("error: pattern at {}: group", i + 1));
                }
                if num > 0 {
                    self.closed.push(num);
                }
                items.push(Item::Grp(num, alts));
                i = j + 1;
            } else if HAS_REF && c == S_REF {
                let ok = i + 1 < n && self.pat[i + 1] >= b'1' && self.pat[i + 1] <= b'9' && self.closed.contains(&((self.pat[i + 1] - b'0') as usize));
                if !ok {
                    return Err(format!("error: pattern at {}: reference", i + 1));
                }
                items.push(Item::Ref((self.pat[i + 1] - b'0') as usize));
                i += 2;
            } else {
                items.push(Item::Lit(c));
                i += 1;
            }
        }
        Ok((items, i))
    }

    fn cls(&mut self, start: usize) -> Result<(Item, usize), String> {
        let n = self.n;
        let mut j = start + 1;
        let mut neg = false;
        if j < n && self.pat[j] == S_NEG {
            neg = true;
            j += 1;
        }
        let mut ranges: Vec<(u8, u8)> = Vec::new();
        let mut first = true;
        loop {
            if j >= n {
                return Err(format!("error: pattern at {}: class", start + 1));
            }
            let c = self.pat[j];
            if c == b']' && !first {
                j += 1;
                break;
            }
            first = false;
            let lo_at = j;
            let lo;
            if c == b'\\' {
                if j + 1 >= n {
                    return Err(format!("error: pattern at {}: class", start + 1));
                }
                lo = self.pat[j + 1];
                j += 2;
            } else {
                lo = c;
                j += 1;
            }
            if j + 1 < n && self.pat[j] == b'-' && self.pat[j + 1] != b']' {
                let hi;
                if self.pat[j + 1] == b'\\' {
                    if j + 2 >= n {
                        return Err(format!("error: pattern at {}: class", start + 1));
                    }
                    hi = self.pat[j + 2];
                    j += 3;
                } else {
                    hi = self.pat[j + 1];
                    j += 2;
                }
                if hi < lo {
                    return Err(format!("error: pattern at {}: range", lo_at + 1));
                }
                ranges.push((lo, hi));
            } else {
                ranges.push((lo, lo));
            }
        }
        let num = self.newcap();
        if num > 0 {
            self.closed.push(num);
        }
        Ok((Item::Cls(ranges, neg, num), j))
    }
}

enum Cont<'a> {
    Nil,
    Seq(&'a [Item], usize, &'a Cont<'a>),
    End(usize, usize, &'a Cont<'a>),
}

struct M<'t> {
    t: &'t [u8],
    fold: bool,
    caps: Vec<Option<(usize, usize)>>,
}

impl<'t> M<'t> {
    fn eq(&self, a: u8, b: u8) -> bool {
        if self.fold {
            lower(a) == lower(b)
        } else {
            a == b
        }
    }

    fn inclass(&self, ch: u8, ranges: &[(u8, u8)], neg: bool) -> bool {
        let mut hit = false;
        for &(lo, hi) in ranges {
            if (lo <= ch && ch <= hi) || (self.fold && lo <= swap(ch) && swap(ch) <= hi) {
                hit = true;
            }
        }
        hit != neg
    }

    fn resume(&mut self, cont: &Cont, pos: usize) -> bool {
        match cont {
            Cont::Nil => pos == self.t.len(),
            Cont::Seq(seq, idx, next) => self.run(seq, *idx, pos, next),
            Cont::End(g, start, next) => {
                let old = self.caps[*g];
                self.caps[*g] = Some((*start, pos));
                if self.resume(next, pos) {
                    return true;
                }
                self.caps[*g] = old;
                false
            }
        }
    }

    fn setcap(&mut self, num: usize, s: usize, e: usize) -> Option<(usize, usize)> {
        if num > 0 {
            let old = self.caps[num];
            self.caps[num] = Some((s, e));
            old
        } else {
            None
        }
    }

    fn restore(&mut self, num: usize, old: Option<(usize, usize)>) {
        if num > 0 {
            self.caps[num] = old;
        }
    }

    fn run(&mut self, seq: &[Item], idx: usize, pos: usize, cont: &Cont) -> bool {
        if idx == seq.len() {
            return self.resume(cont, pos);
        }
        let n = self.t.len();
        match &seq[idx] {
            Item::Lit(c) => pos < n && self.eq(self.t[pos], *c) && self.run(seq, idx + 1, pos + 1, cont),
            Item::Any(num) => {
                if pos >= n {
                    return false;
                }
                let old = self.setcap(*num, pos, pos + 1);
                if self.run(seq, idx + 1, pos + 1, cont) {
                    return true;
                }
                self.restore(*num, old);
                false
            }
            Item::Cls(ranges, neg, num) => {
                if pos >= n || !self.inclass(self.t[pos], ranges, *neg) {
                    return false;
                }
                let old = self.setcap(*num, pos, pos + 1);
                if self.run(seq, idx + 1, pos + 1, cont) {
                    return true;
                }
                self.restore(*num, old);
                false
            }
            Item::Lazy(num) | Item::Greedy(num) => {
                let lazy = matches!(&seq[idx], Item::Lazy(_));
                let max = n - pos;
                for s in 0..=max {
                    let w = if lazy { s } else { max - s };
                    let old = self.setcap(*num, pos, pos + w);
                    if self.run(seq, idx + 1, pos + w, cont) {
                        return true;
                    }
                    self.restore(*num, old);
                }
                false
            }
            Item::Grp(num, alts) => {
                for alt in alts {
                    let after = Cont::Seq(seq, idx + 1, cont);
                    let frame = Cont::End(*num, pos, &after);
                    if self.run(alt, 0, pos, &frame) {
                        return true;
                    }
                }
                false
            }
            Item::Ref(g) => {
                let c = match self.caps[*g] {
                    None => return false,
                    Some(c) => c,
                };
                let w = c.1 - c.0;
                if pos + w > n {
                    return false;
                }
                for k in 0..w {
                    if !self.eq(self.t[c.0 + k], self.t[pos + k]) {
                        return false;
                    }
                }
                self.run(seq, idx + 1, pos + w, cont)
            }
        }
    }
}

fn do_match(pattern: &str, text: &str) -> Result<String, String> {
    let pb = pattern.as_bytes();
    let mut fold = false;
    let mut off = 0;
    if HAS_FLAG && !pb.is_empty() && pb[0] == S_FLAG {
        fold = true;
        off = 1;
    }
    let mut p = Parser { pat: pb, n: pb.len(), count: 0, closed: Vec::new() };
    let (alts, _) = p.alts(off, 0)?;
    let root = &alts[0];
    let mut m = M { t: text.as_bytes(), fold, caps: vec![None; p.count + 1] };
    if !m.run(root, 0, 0, &Cont::Nil) {
        return Ok("no".to_string());
    }
    if !HAS_CAPS {
        return Ok("yes".to_string());
    }
    let mut out = String::from("yes");
    for c in &m.caps[1..] {
        out.push_str(" [");
        if let Some((s, e)) = c {
            out.push_str(&text[*s..*e]);
        }
        out.push(']');
    }
    Ok(out)
}

pub fn stencil(pattern: &str, text: &str) -> String {
    match do_match(pattern, text) {
        Ok(s) => s,
        Err(e) => e,
    }
}
'''

CC = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "stencil.h"

#define S_ANY @S_ANY@
#define S_LAZY @S_LAZY@
#define S_GREEDY @S_GREEDY@
#define S_FLAG @S_FLAG@
#define S_NEG @S_NEG@
#define S_OPEN @S_OPEN@
#define S_CLOSE @S_CLOSE@
#define S_ALT @S_ALT@
#define S_REF @S_REF@
#define HAS_CLASS @CLASS@
#define HAS_FLAG @FLAGS@
#define HAS_CAPS @CAPS@
#define HAS_GROUPS @GROUPS@
#define HAS_REF @REFS@

enum { LIT, ANY, LAZY, GREEDY, CLS, GRP, REF };

typedef struct Seq Seq;
typedef struct {
    int kind;
    char c;
    int num;
    int neg;
    int nr;
    unsigned char *lo, *hi;
    Seq *alts;
    int nalts;
    int ref;
} Item;
struct Seq {
    Item *items;
    int n, cap;
};

typedef struct {
    const char *pat;
    int n;
    int count;
    char *closed;
    int err_at;
    const char *err_why;
} Parser;

static int fail(Parser *p, int at, const char *why) {
    p->err_at = at + 1;
    p->err_why = why;
    return 0;
}

static int newcap(Parser *p) {
    if (!HAS_CAPS) return 0;
    return ++p->count;
}

static void push(Seq *s, Item it) {
    if (s->n == s->cap) {
        s->cap = s->cap ? s->cap * 2 : 8;
        s->items = realloc(s->items, (size_t)s->cap * sizeof(Item));
    }
    s->items[s->n++] = it;
}

static void free_seq(Seq *s) {
    for (int i = 0; i < s->n; i++) {
        Item *it = &s->items[i];
        free(it->lo);
        free(it->hi);
        for (int a = 0; a < it->nalts; a++) free_seq(&it->alts[a]);
        free(it->alts);
    }
    free(s->items);
}

static Item mk(int kind) {
    Item it;
    memset(&it, 0, sizeof it);
    it.kind = kind;
    return it;
}

static int parse_alts(Parser *p, int i, int depth, Seq **out, int *nout, int *end);

static int parse_cls(Parser *p, int start, Item *out, int *end) {
    const char *pat = p->pat;
    int n = p->n;
    int j = start + 1;
    int neg = 0;
    if (j < n && pat[j] == S_NEG) {
        neg = 1;
        j++;
    }
    unsigned char *lo = malloc((size_t)n + 1), *hi = malloc((size_t)n + 1);
    int nr = 0, first = 1;
    for (;;) {
        if (j >= n) { free(lo); free(hi); return fail(p, start, "class"); }
        char c = pat[j];
        if (c == ']' && !first) {
            j++;
            break;
        }
        first = 0;
        int lo_at = j;
        char l;
        if (c == '\\') {
            if (j + 1 >= n) { free(lo); free(hi); return fail(p, start, "class"); }
            l = pat[j + 1];
            j += 2;
        } else {
            l = c;
            j++;
        }
        if (j + 1 < n && pat[j] == '-' && pat[j + 1] != ']') {
            char h;
            if (pat[j + 1] == '\\') {
                if (j + 2 >= n) { free(lo); free(hi); return fail(p, start, "class"); }
                h = pat[j + 2];
                j += 3;
            } else {
                h = pat[j + 1];
                j += 2;
            }
            if ((unsigned char)h < (unsigned char)l) { free(lo); free(hi); return fail(p, lo_at, "range"); }
            lo[nr] = (unsigned char)l;
            hi[nr++] = (unsigned char)h;
        } else {
            lo[nr] = (unsigned char)l;
            hi[nr++] = (unsigned char)l;
        }
    }
    Item it = mk(CLS);
    it.neg = neg;
    it.nr = nr;
    it.lo = lo;
    it.hi = hi;
    it.num = newcap(p);
    if (it.num) p->closed[it.num] = 1;
    *out = it;
    *end = j;
    return 1;
}

/* parses one sequence into s; stops at an alternative separator / close char (depth > 0) or the end */
static int parse_seq(Parser *p, int i, int depth, Seq *s, int *end) {
    const char *pat = p->pat;
    int n = p->n;
    while (i < n) {
        char c = pat[i];
        if (depth > 0 && c == S_ALT && HAS_GROUPS) break;
        if (HAS_GROUPS && c == S_CLOSE) {
            if (depth == 0) return fail(p, i, "group");
            break;
        }
        if (c == '\\') {
            if (i + 1 >= n) return fail(p, i, "escape");
            Item it = mk(LIT);
            it.c = pat[i + 1];
            push(s, it);
            i += 2;
        } else if (c == S_ANY) {
            Item it = mk(ANY);
            it.num = newcap(p);
            if (it.num) p->closed[it.num] = 1;
            push(s, it);
            i++;
        } else if (c == S_LAZY) {
            Item it = mk(LAZY);
            it.num = newcap(p);
            if (it.num) p->closed[it.num] = 1;
            push(s, it);
            i++;
        } else if (HAS_REF && c == S_GREEDY) {
            Item it = mk(GREEDY);
            it.num = newcap(p);
            if (it.num) p->closed[it.num] = 1;
            push(s, it);
            i++;
        } else if (HAS_CLASS && c == '[') {
            Item it;
            int j;
            if (!parse_cls(p, i, &it, &j)) return 0;
            push(s, it);
            i = j;
        } else if (HAS_GROUPS && c == S_OPEN) {
            Item it = mk(GRP);
            it.num = newcap(p);
            int j;
            if (!parse_alts(p, i + 1, depth + 1, &it.alts, &it.nalts, &j)) return 0;
            if (j >= n) {
                for (int a = 0; a < it.nalts; a++) free_seq(&it.alts[a]);
                free(it.alts);
                return fail(p, i, "group");
            }
            if (it.num) p->closed[it.num] = 1;
            push(s, it);
            i = j + 1;
        } else if (HAS_REF && c == S_REF) {
            if (!(i + 1 < n && pat[i + 1] >= '1' && pat[i + 1] <= '9' && p->closed[pat[i + 1] - '0'])) return fail(p, i, "reference");
            Item it = mk(REF);
            it.ref = pat[i + 1] - '0';
            push(s, it);
            i += 2;
        } else {
            Item it = mk(LIT);
            it.c = c;
            push(s, it);
            i++;
        }
    }
    *end = i;
    return 1;
}

static int parse_alts(Parser *p, int i, int depth, Seq **out, int *nout, int *end) {
    Seq *alts = NULL;
    int na = 0;
    for (;;) {
        alts = realloc(alts, (size_t)(na + 1) * sizeof(Seq));
        memset(&alts[na], 0, sizeof(Seq));
        int j;
        int ok = parse_seq(p, i, depth, &alts[na], &j);
        na++;
        if (!ok) {
            for (int a = 0; a < na; a++) free_seq(&alts[a]);
            free(alts);
            return 0;
        }
        i = j;
        if (depth > 0 && i < p->n && p->pat[i] == S_ALT) {
            i++;
            continue;
        }
        *out = alts;
        *nout = na;
        *end = i;
        return 1;
    }
}

typedef struct {
    int set, s, e;
} Cap;

typedef struct Cont {
    int kind; /* 0 = resume a sequence, 1 = end of a group */
    const Seq *seq;
    int idx;
    int g, start;
    const struct Cont *next;
} Cont;

static const char *T;
static int TL;
static int FOLD;
static Cap *caps;

static char lowerc(char c) { return (c >= 'A' && c <= 'Z') ? (char)(c + 32) : c; }
static char swapc(char c) {
    if (c >= 'a' && c <= 'z') return (char)(c - 32);
    if (c >= 'A' && c <= 'Z') return (char)(c + 32);
    return c;
}
static int eqc(char a, char b) { return FOLD ? lowerc(a) == lowerc(b) : a == b; }

static int inclass(char ch, const Item *it) {
    int hit = 0;
    for (int k = 0; k < it->nr; k++) {
        unsigned char u = (unsigned char)ch, w = (unsigned char)swapc(ch);
        if ((it->lo[k] <= u && u <= it->hi[k]) || (FOLD && it->lo[k] <= w && w <= it->hi[k])) hit = 1;
    }
    return hit != it->neg;
}

static int run(const Seq *seq, int idx, int pos, const Cont *cont);

static int resume(const Cont *cont, int pos) {
    if (!cont) return pos == TL;
    if (cont->kind == 0) return run(cont->seq, cont->idx, pos, cont->next);
    Cap old = caps[cont->g];
    caps[cont->g].set = 1;
    caps[cont->g].s = cont->start;
    caps[cont->g].e = pos;
    if (resume(cont->next, pos)) return 1;
    caps[cont->g] = old;
    return 0;
}

static int run(const Seq *seq, int idx, int pos, const Cont *cont) {
    if (idx == seq->n) return resume(cont, pos);
    const Item *it = &seq->items[idx];
    switch (it->kind) {
    case LIT:
        return pos < TL && eqc(T[pos], it->c) && run(seq, idx + 1, pos + 1, cont);
    case ANY:
    case CLS: {
        if (pos >= TL) return 0;
        if (it->kind == CLS && !inclass(T[pos], it)) return 0;
        Cap old = {0, 0, 0};
        if (it->num) {
            old = caps[it->num];
            caps[it->num].set = 1;
            caps[it->num].s = pos;
            caps[it->num].e = pos + 1;
        }
        if (run(seq, idx + 1, pos + 1, cont)) return 1;
        if (it->num) caps[it->num] = old;
        return 0;
    }
    case LAZY:
    case GREEDY: {
        int max = TL - pos;
        for (int s = 0; s <= max; s++) {
            int w = it->kind == LAZY ? s : max - s;
            Cap old = {0, 0, 0};
            if (it->num) {
                old = caps[it->num];
                caps[it->num].set = 1;
                caps[it->num].s = pos;
                caps[it->num].e = pos + w;
            }
            if (run(seq, idx + 1, pos + w, cont)) return 1;
            if (it->num) caps[it->num] = old;
        }
        return 0;
    }
    case GRP:
        for (int a = 0; a < it->nalts; a++) {
            Cont after = {0, seq, idx + 1, 0, 0, cont};
            Cont frame = {1, NULL, 0, it->num, pos, &after};
            if (run(&it->alts[a], 0, pos, &frame)) return 1;
        }
        return 0;
    case REF: {
        Cap c = caps[it->ref];
        if (!c.set) return 0;
        int w = c.e - c.s;
        if (pos + w > TL) return 0;
        for (int k = 0; k < w; k++)
            if (!eqc(T[c.s + k], T[pos + k])) return 0;
        return run(seq, idx + 1, pos + w, cont);
    }
    }
    return 0;
}

char *stencil(const char *pattern, const char *text) {
    int fold = 0, off = 0;
    int n = (int)strlen(pattern);
    if (HAS_FLAG && n > 0 && pattern[0] == S_FLAG) {
        fold = 1;
        off = 1;
    }
    Parser p;
    memset(&p, 0, sizeof p);
    p.pat = pattern;
    p.n = n;
    p.closed = calloc((size_t)n + 12, 1);
    Seq *alts;
    int na, end;
    if (!parse_alts(&p, off, 0, &alts, &na, &end)) {
        char *r = malloc(80);
        sprintf(r, "error: pattern at %d: %s", p.err_at, p.err_why);
        free(p.closed);
        return r;
    }
    T = text;
    TL = (int)strlen(text);
    FOLD = fold;
    caps = calloc((size_t)p.count + 2, sizeof(Cap));
    int ok = run(&alts[0], 0, 0, NULL);
    char *res;
    if (!ok) {
        res = malloc(3);
        strcpy(res, "no");
    } else if (!HAS_CAPS) {
        res = malloc(4);
        strcpy(res, "yes");
    } else {
        size_t cap = 16 + (size_t)(p.count + 1) * (size_t)(TL + 4);
        res = malloc(cap);
        strcpy(res, "yes");
        for (int k = 1; k <= p.count; k++) {
            strcat(res, " [");
            if (caps[k].set) {
                size_t l = strlen(res);
                memcpy(res + l, T + caps[k].s, (size_t)(caps[k].e - caps[k].s));
                res[l + (size_t)(caps[k].e - caps[k].s)] = 0;
            }
            strcat(res, "]");
        }
    }
    for (int a = 0; a < na; a++) free_seq(&alts[a]);
    free(alts);
    free(caps);
    free(p.closed);
    return res;
}
'''



ANYS = ["?", "_"]
LAZYS = ["*", "%"]
GREEDYS = ["+", "#"]
FLAGS_ = ["~", "`"]
NEGS = ["!", "^"]
GROUPS_ = [("(", ")"), ("<", ">"), ("{", "}")]
ALTS = ["|", ","]
REFS_ = ["&", "$"]
THEMES = [
    ("the ferry office's notice board", "The ferry office filters its notice board with stencils."),
    ("the library's shelf labels", "The library's label printer selects labels with stencils."),
    ("the lighthouse log filter", "The lighthouse log viewer selects entries with stencils."),
    ("the seed catalogue search box", "The seed catalogue's search box understands stencils."),
    ("the kiln schedule filter", "The kiln schedule page filters rows with stencils."),
]
ALPHA = "abcABxy-./ 019_"


def params(rng, level, i):
    o, c = rng.choice(GROUPS_)
    return {
        "level": level, "any": rng.choice(ANYS), "lazy": rng.choice(LAZYS), "greedy": rng.choice(GREEDYS), "flag": rng.choice(FLAGS_), "neg": rng.choice(NEGS), "open": o, "close": c, "alt": rng.choice(ALTS), "ref": rng.choice(REFS_),
        "cls": level >= 2, "flags": level >= 2, "caps": level >= 3, "groups": level >= 4, "refs": level >= 5, "theme": THEMES[(i + rng.randrange(2)) % len(THEMES)],
    }


def sol(lang, p):
    src = {"python": PY, "javascript": JS, "rust": RS, "c": CC}[lang]

    def sym(ch):
        if lang == "c":
            return "'" + ch + "'"
        if lang == "rust":
            return "b'" + ch + "'"
        return K.lit(lang, ch)

    b = {"python": lambda v: "True" if v else "False", "javascript": lambda v: "true" if v else "false", "rust": lambda v: "true" if v else "false"}.get(lang, lambda v: "1" if v else "0")
    return K.subst(
        src, S_ANY=sym(p["any"]), S_LAZY=sym(p["lazy"]), S_GREEDY=sym(p["greedy"]), S_FLAG=sym(p["flag"]), S_NEG=sym(p["neg"]), S_OPEN=sym(p["open"]), S_CLOSE=sym(p["close"]), S_ALT=sym(p["alt"]), S_REF=sym(p["ref"]),
        CLASS=b(p["cls"]), FLAGS=b(p["flags"]), CAPS=b(p["caps"]), GROUPS=b(p["groups"]), REFS=b(p["refs"]),
    ).lstrip("\n")


def specials(p):
    s = {"\\", p["any"], p["lazy"]}
    if p["cls"]:
        s.add("[")
    if p["groups"]:
        s |= {p["open"], p["close"], p["alt"]}
    if p["refs"]:
        s |= {p["greedy"], p["ref"]}
    return s


def esc(p, ch):
    return "\\" + ch if ch in specials(p) or (p["flags"] and ch == p["flag"]) else ch


def cesc(p, ch):
    return "\\" + ch if ch in "]\\-" or ch == p["neg"] else ch


def rtext(rng, maxlen=10):
    return "".join(rng.choice(ALPHA) for _ in range(rng.randint(0, maxlen)))


def cls_for(rng, p, ch):
    r = rng.random()
    if r < 0.3:
        return "[" + cesc(p, ch) + "]"
    if r < 0.6:
        lo = chr(max(33, ord(ch) - rng.randint(0, 3)))
        hi = chr(min(126, ord(ch) + rng.randint(0, 3)))
        return "[" + cesc(p, lo) + "-" + cesc(p, hi) + "]"
    if r < 0.8:
        extra = "".join(cesc(p, rng.choice(ALPHA)) for _ in range(rng.randint(1, 3)))
        return "[" + extra + cesc(p, ch) + "]"
    other = rng.choice([c for c in ALPHA if c != ch])
    return "[" + p["neg"] + cesc(p, other) + "]"


def derive(rng, p, text, top=True):
    """a pattern that usually matches text"""
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        r = rng.random()
        if r < 0.45:
            out.append(esc(p, ch))
            i += 1
        elif r < 0.6:
            out.append(p["any"])
            i += 1
        elif r < 0.75:
            k = rng.randint(0, min(4, len(text) - i))
            out.append(p["lazy"])
            i += k
        elif p["cls"] and r < 0.87:
            out.append(cls_for(rng, p, ch))
            i += 1
        elif p["groups"] and r < 0.95 and len(text) - i >= 1:
            k = rng.randint(1, min(3, len(text) - i))
            frag = derive(rng, p, text[i:i + k], False)
            alts = [frag, esc(p, rng.choice(ALPHA)) + "".join(esc(p, rng.choice(ALPHA)) for _ in range(rng.randint(0, 2)))]
            if rng.random() < 0.3:
                alts.append("")
            rng.shuffle(alts)
            out.append(p["open"] + p["alt"].join(alts) + p["close"])
            i += k
        elif p["refs"] and r < 0.99:
            out.append(p["greedy"])
            i += rng.randint(0, min(3, len(text) - i))
        else:
            out.append(esc(p, ch))
            i += 1
    if rng.random() < 0.2:
        out.append(p["lazy"])
    s = "".join(out)
    if top and p["flags"] and rng.random() < 0.3:
        s = p["flag"] + s
    return s


def swapcase_text(rng, t):
    return "".join(c.swapcase() if rng.random() < 0.4 else c for c in t)


def mutate_text(rng, t):
    if not t:
        return rng.choice(ALPHA)
    r = rng.random()
    k = rng.randrange(len(t))
    if r < 0.4:
        return t[:k] + rng.choice(ALPHA) + t[k + 1:]
    if r < 0.7:
        return t[:k] + t[k + 1:]
    return t[:k] + rng.choice(ALPHA) + t[k:]


def make_cases(rng, p):
    cases = []
    L = p["level"]
    A, Z, Q, F, N, O, C, C_, S = p["any"], p["lazy"], p["greedy"], p["flag"], p["neg"], p["open"], p["close"], p["alt"], p["ref"]

    def add(pat, text):
        cases.append((pat, text))

    # derived pairs
    for _ in range(90):
        t = rtext(rng, rng.choice([4, 8, 12]))
        pat = derive(rng, p, t)
        add(pat, t)
        if rng.random() < 0.5:
            add(pat, mutate_text(rng, t))
        if p["flags"] and pat[:1] == F and rng.random() < 0.6:
            add(pat, swapcase_text(rng, t))
    # random pairs
    toks = [A, Z, "a", "b", "A", "x", "-", ".", " ", "\\*", "\\" + A]
    if p["cls"]:
        toks += ["[ab]", "[!a]".replace("!", N), "[a-c]", "[]a]", "[a-]", "[-a]", "[\\]x]"]
    if p["groups"]:
        toks += [O + "a" + C_ + "b" + C_ + "x" + C, O + "a" + C_ + C, O + "ab" + C_ + "b" + C, O + Z + C_ + "x" + C]
    if p["refs"]:
        toks += [Q, "&1".replace("&", S), "&2".replace("&", S)]
    for _ in range(50):
        pat = "".join(rng.choice(toks) for _ in range(rng.randint(1, 5)))
        add(pat, rtext(rng, 8))
    # basics
    for pat, t in [("", ""), ("", "a"), ("a", ""), ("a", "a"), ("a", "A"), ("a", "aa"), ("ab", "ab"), (A, "a"), (A, ""), (A, "ab"), (Z, ""), (Z, "abc"), (A + A, "ab"), (Z + Z, "ab"), ("a" + Z, "a"), ("a" + Z, "abc"), (Z + "a", "ba"),
                   (Z + "a", "ab"), ("a" + Z + "c", "abc"), ("a" + Z + "c", "ac"), ("a" + Z + "c", "abcbc"), (Z + "b" + Z, "abab"), (Z + "b" + Z, "ab"), (Z + A, "x"), (Z + A, ""), (A + Z, "xyz"), ("\\" + A, A), ("\\" + A, "a"), ("\\" + Z, Z), ("\\\\", "\\"),
                   ("\\a", "a"), ("a\\b", "ab"), ("\\" + A + "\\" + Z, A + Z), (Z + "\\" + Z, "ab" + Z), ("a.c", "abc"), ("a.c", "a.c"), ("a-c", "a-c"), (" ", " "), ("a b", "a b"), ("a" + Z + " ", "abc "), (" " + Z, "  x"),
                   ("x" * 5, "x" * 5), (Z * 3, "abc"), (A * 3 + Z, "abcde"), (Z + "." + Z, "a.b.c"), ("[", "["), ("]", "]"), ("a]", "a]"), ("-", "-"), (Z + "-", "a-"), ("a/b", "a/b"), (Z + "/" + Z, "a/b/c")]:
        add(pat, t)
    if p["flags"]:
        for pat, t in [(F, ""), (F, "a"), (F + "a", "A"), (F + "A", "a"), (F + "ab", "AB"), (F + "a" + Z, "ABC"), (F + "a" + A, "Ab"), ("a" + F, "a" + F), (F + F, F), (F + "\\" + F, F), ("\\" + F, F), (F + F + "a", F + "A"), (F + F + "a", F + "a"),
                       (F + "-", "-"), (F + "1", "1"), (F + "[a-c]", "B"), (F + "[a-c]", "d"), (F + "[A-C]", "b"), (F + "[" + N + "a]", "A"), (F + "[" + N + "a]", "b"), ("[a-c]", "B"), ("[A-C]", "b"), (F + "_", "_"), (F + "z" + Z, "Z!"), (F + "[x-z]", "{")]:
            add(pat, t)
    if p["cls"]:
        cl = [("[abc]", "a"), ("[abc]", "d"), ("[abc]", ""), ("[abc]", "ab"), ("[a-c]", "b"), ("[a-c]", "c"), ("[a-c]", "d"), ("[c-a]", "b"), ("[a-a]", "a"), ("[a-a]", "b"), ("[" + N + "abc]", "d"), ("[" + N + "abc]", "a"), ("[" + N + "]", "!"), ("[" + N + "]a]", "x]"),
              ("[]]", "]"), ("[]a]", "a"), ("[]a]", "b"), ("[" + N + "]]", "]"), ("[" + N + "]]", "x"), ("[a-]", "-"), ("[a-]", "a"), ("[a-]", "b"), ("[-a]", "-"), ("[-a]", "a"), ("[-]", "-"), ("[a-c-e]", "d"), ("[a-c-e]", "-"), ("[a-c-e]", "e"),
              ("[\\]]", "]"), ("[\\-]", "-"), ("[\\\\]", "\\"), ("[a\\-c]", "b"), ("[a\\-c]", "-"), ("[\\a]", "a"), ("[\\a-c]", "b"), ("[a-\\c]", "b"), ("[a-\\]]", "b"), ("[!-~]", "a"), ("[ -/]", "."), ("[0-9]", "5"), ("[0-9]*", "2024"), ("[" + N + "0-9]", "a"),
              ("x[a-c]" + Z, "xbyyy"), ("[a-c][a-c]", "ab"), ("[" + A + "]", A), ("[" + Z + "]", Z), ("[" + Z + "]", "a"), ("[^]", "^"), ("[x" + N + "]", N), ("[a-c]" + "[x-z]", "bz"), ("[[]", "["), ("[[a]", "a"), ("[a[]", "["),
              ("[", "a"), ("a[", "a"), ("[a", "a"), ("[]", "a"), ("[" + N, "a"), ("[" + N + "]", "a"), ("[a-", "a"), ("[a-]", "a"), ("[\\", "a"), ("[a\\", "a"), ("[a-\\", "a"), ("[b-a]x", "a"), ("x[b-a", "a"), ("x[]", "a"), ("[z-a]" + "[", "a"), ("\\[", "["), ("\\[a-c]", "[a-c]")]
        for pat, t in cl:
            add(pat, t)
    elif True:
        for pat, t in [("[abc]", "a"), ("[abc]", "[abc]"), ("[", "["), ("[a-c]", "b")]:
            add(pat, t)
    if p["caps"]:
        for pat, t in [("a" + A + "c", "abc"), (Z, "xyz"), (Z + Z, "xyz"), (Z + A + Z, "xyz"), (Z + "a" + Z, "bab"), (Z + "a" + Z, "aaa"), (A + A + A, "xyz"), (Z + "b", "abab"), ("a" + Z, "aaa"), (Z + Z + Z, ""), (Z + Z + Z, "ab"),
                       ("[a-c]" if p["cls"] else A, "b"), ("[a-c]" * 2 if p["cls"] else A + A, "bc"), ("x" + Z + "y" + Z + "z", "xAyBz"), ("x" + Z + "y" + Z + "z", "xyyyz"), ("x" + Z + "y" + Z + "z", "xyz"), (Z + "." + Z, "a.b.c"), (Z + "-" + A, "a-b-c")]:
            add(pat, t)
    if p["groups"]:
        gs = lambda *alts: O + C_.join(alts) + C  # noqa: E731
        for pat, t in [(gs("a", "b"), "a"), (gs("a", "b"), "b"), (gs("a", "b"), "c"), (gs("a", "b"), ""), (gs("a", ""), ""), (gs("a", ""), "a"), (gs("", "a"), "a"), (gs("", ""), ""), (O + C, ""), (O + C, "a"), ("a" + O + C + "b", "ab"),
                       (gs("ab", "a") + "b", "ab"), (gs("ab", "a") + "b", "abb"), (gs("a", "ab") + "b", "ab"), (gs("a", "ab") + "b", "abb"), (gs("a", "ab") + Z, "abx"), (gs("a" + Z, "b") + "c", "axxc"), (gs("a" + Z, "b") + "c", "bc"),
                       (O + gs("a", "b") + "x" + C, "ax"), (O + gs("a", "b") + gs("c", "d") + C, "bc"), (gs(gs("a", "b"), "c"), "b"), (gs(gs("a", "b"), "c"), "c"), (gs(gs("a", gs("b", "c")), "d"), "c"), (gs("a" + A, "b" + Z), "abc"), (gs("a" + A, "b" + Z), "bcd"),
                       (gs(Z, "a") + "b", "ab"), (gs(Z, "a") + "b", "xb"), (gs(A, A + A) + "z", "abz"), (gs(A, A + A) + "z", "az"), (gs("a", "b") + gs("a", "b") + gs("a", "b"), "aba"), (O + A + C, "x"), (O + Z + C, "xyz"), ("\\" + O + "a" + "\\" + C, O + "a" + C),
                       (gs("a", "b") + ("[ab]" if p["cls"] else A), "ab"), ("x" + gs("", "y") + "z", "xz"), ("x" + gs("", "y") + "z", "xyz"), ("x" + gs("", "y") + "z", "xyyz"),
                       (O, "a"), (O + "a", "a"), (O + "a" + C_, "a"), (C, "a"), ("a" + C, "a"), (O + C + C, ""), (O + O + C, ""), (gs("a", "b") + C, "a"), (O + "a" + C_ + C_ + "b" + C + O, "a"), (O + "[" + C, "["), (O + "\\", "a"), ("[" + O + "]", O), (O + "[a" + C, "a"),
                       (C_, C_), ("a" + C_ + "b", "a" + C_ + "b"), (O + "a" + C_ + "b" + C + C_ + "x", "a" + C_ + "x"), ("\\" + C_, C_)]:
            add(pat, t)
    if p["refs"]:
        for pat, t in [(O + A + C + S + "1", "aa"), (O + A + C + S + "1", "ab"), (O + Z + C + S + "1", "abab"), (O + Z + C + S + "1", ""), (O + Z + C + S + "1", "x"), (O + Z + C + S + "1" + S + "1", "abababab"), (O + "a" + C_ + "b" + C + S + "1", "bb"), (O + "a" + C_ + "b" + C + S + "1", "ab"),
                       (F + O + A + C + S + "1", "aA"), (F + O + A + C + S + "1", "ab"), (O + A + C + O + A + C + S + "2" + S + "1", "abba"), (O + A + C + O + A + C + S + "2" + S + "1", "abab"), (S + "1", "a"), (S + "0", "a"), (S + "a", "a"), (S, "a"), ("a" + S, "a"),
                       (O + S + "1" + C, ""), (O + A + S + "1" + C, "aa"), (O + A + C + S + "2", "aa"), (O + A + C + S + "9", "aa"), (O + gs_("a", "", p) + C + S + "2" + S + "1", "ba"),
                       (O + O + A + C + C + S + "1" + S + "2", "aaa"), (O + O + A + C + C + S + "1" + S + "2", "aab"), ("\\" + S + "1", S + "1"), (Q, ""), (Q, "abc"), (Q + Q, "ab"), (Q + "a", "bba"), (Q + "a", "bab"), ("a" + Q + "c", "abc"), (Q + "b" + Z, "abab"),
                       (Z + "b" + Q, "abab"), (Z + Q, "ab"), (Q + Z, "ab"), (Q + A, "x"), (Q + A, ""), (O + Q + C + S + "1", "abab"), (O + Z + C + Q + S + "1", "abab"), (Q + O + Z + C + S + "1", "aa"), ("\\" + Q, Q), (O + Q + C_ + "a" + C + "b" + S + "1", "abb"), (O + Q + "a" + C + S + "1", "baba"),
                       (O + A + C + "x" + S + "1" + "y" + S + "1", "axayb"), (O + A + C + "x" + S + "1" + "y" + S + "1", "axayb".replace("b", "a")), (S + "1" + O + A + C, "aa"), (O + A + S + "1", "aa"), (O + O + A + C + S + "2" + C, "aa"),
                       (O + O + A + C + S + "1" + C, "aa"), (O + A + C + C, "a"), (O + A + C + S + "1" + S + "1" + S + "1", "aaa"), (F + O + Z + C + S + "1", "abAB"), (F + O + "[a-c]" + C + S + "1", "bB")]:
            add(pat, t)
    # long texts
    for n in (20, 40):
        t = "ab" * (n // 2)
        add(Z + "b" + Z + "b", t)
        add("a" + Z + "b", t)
        add(Z, t)
        add(A * 5 + Z, t)
    # dedupe, examples first
    ex = []
    ex.append(("ab" + Z + "ef", "abcdef"))
    ex.append((A + "at" + Z, "cattle"))
    ex.append(("a" + A + "c", "ac"))
    if p["flags"]:
        ex.append((F + "stop" + Z, "STOPPING"))
    if p["cls"]:
        ex.append(("[a-c]" + A + "[" + N + "0-9]", "b2x"))
    if p["groups"]:
        ex.append((O + "cat" + C_ + "dog" + C + Z, "dogs"))
    if p["refs"]:
        ex.append((O + Z + C + S + "1", "abab"))
    nex = len(ex)
    out, seen = [], set()
    for c in ex + cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex


def gs_(a, b, p):
    return p["open"] + a + p["alt"] + b + p["close"]


def readme(p, api, lang, examples):
    A, Z, Q, F, N, O, C, S, R = p["any"], p["lazy"], p["greedy"], p["flag"], p["neg"], p["open"], p["close"], p["alt"], p["ref"]
    X = [f"# Stencil patterns for {p['theme'][0]}", ""]
    X.append(f"{p['theme'][1]} `stencil(pattern, text)` tests whether a whole text fits a pattern written in the house stencil notation, and reports what the wildcards matched." if p["caps"] else
             f"{p['theme'][1]} `stencil(pattern, text)` tests whether a whole text fits a pattern written in the house stencil notation.")
    X.append("")
    X.append("## Notation")
    X.append("")
    X.append("The pattern must match the **whole** text, not just a part of it. Text and pattern are ASCII. Every character of the pattern matches itself, except these:")
    X.append("")
    X.append(f"* `{A}` matches any single character.")
    X.append(f"* `{Z}` matches any run of characters, possibly empty (a *lazy* run: see *Order of attempts*).")
    X.append("* `\\` followed by any character matches that character literally (so `\\\\` matches a backslash and `\\" + Z + "` a literal `" + Z + "`). A `\\` at the very end of the pattern is an error.")
    if p["flags"]:
        X.append(f"* a `{F}` as the **first** character of the pattern switches on case-insensitive matching for the whole pattern and matches nothing itself (anywhere else it is an ordinary character).")
    if p["cls"]:
        X.append("* `[...]` is a character class matching one character. Inside: items are single characters or ranges `x-y` (both ends included, `x` must not be greater than `y` in ASCII order). "
                 f"A `{N}` right after the `[` negates the class. A `]` that is the first item (right after `[` or `[{N}`) is a literal `]`; otherwise `]` ends the class. A `-` is a range operator only between two items (a range needs a character after the `-` that is not the closing `]`), so `-` first or last is literal. "
                 "`\\` inside a class makes the next character literal (also as a range end, as in `[a-\\]]`). Other characters, including `[`, are literal. A class that never closes is an error.")
    if p["groups"]:
        X.append(f"* `{O}` starts a group and `{C}` ends it; inside, alternatives are separated by `{S}` (outside groups `{S}` is an ordinary character). A group matches the text matched by any one of its alternatives; an alternative may be empty and groups may be nested. An unmatched `{C}` or a `{O}` that is never closed is an error.")
    if p["refs"]:
        X.append(f"* `{Q}` matches any run of characters, possibly empty, like `{Z}`, but is *greedy* (longest run first).")
        X.append(f"* `{R}` followed by a digit `1` to `9` is a back-reference: it matches exactly the text that capture number N matched (see *Captures*); with case-insensitive matching the comparison ignores case. A reference to a capture that has not been *completed* earlier in the pattern (or `{R}` without a digit 1 to 9) is an error. If the referenced capture did not take part in the match, the reference fails to match.")
    X.append("")
    if p["flags"]:
        X.append(f"With the case flag, two characters are equal if they are equal after turning ASCII capitals into lower case. A class then matches a character if the class contains it **or** contains its other-case counterpart (before negation: `[{N}a]` with the flag rejects both `a` and `A`).")
        X.append("")
    X.append("## Order of attempts")
    X.append("")
    X.append("When there are several ways to match, the first one found in this order is used (this only matters for the captures below): wildcards and alternatives are tried left to right; " +
             ("a `" + Z + "` tries the shortest run first" + (f" and a `{Q}` the longest run first" if p["refs"] else "") + "; " if True else "") + ("the alternatives of a group are tried in the order written; " if p["groups"] else "") + "the choices of earlier parts are changed last.")
    X.append("")
    if p["caps"]:
        X.append("## Captures")
        X.append("")
        caps = [f"every `{A}`", f"every `{Z}`", "every class" if p["cls"] else None, f"every `{Q}`" if p["refs"] else None, "every group" if p["groups"] else None]
        X.append("The captures are " + ", ".join(c for c in caps if c) + ", numbered from 1 in the order in which they **start** in the pattern" + (" (a group is numbered before the captures inside it)" if p["groups"] else "") + ". A capture holds the text it matched" +
                 (" in the successful attempt; one that did not take part in the match (for example inside an alternative that was not used) is empty." if p["groups"] else "") + " Escaped characters and plain characters are not captures.")
        X.append("")
    X.append("## Result")
    X.append("")
    if p["caps"]:
        X.append("`no` if the text does not fit; otherwise `yes` followed by one ` [TEXT]` for every capture in order (a space, `[`, the captured text, `]`), for example `yes [b] [] [xy]`. A pattern without captures gives just `yes`.")
    else:
        X.append("`yes` if the text fits, `no` if not.")
    X.append("")
    X.append("## Errors")
    X.append("")
    X.append("A bad pattern gives `error: pattern at I: WHY` (instead of `yes`/`no`, whatever the text is). `I` is a position in the pattern counting from 1 and `WHY` one of:")
    X.append("")
    X.append("* `escape`: a `\\` at the end of the pattern (`I` is its position).")
    if p["cls"]:
        X.append("* `class`: a `[` that is never closed (`I` is the position of the `[`). A `\\` at the very end of the pattern inside a class is also reported as `class`.")
        X.append("* `range`: a range whose start is greater than its end (`I` is the position of the start of the range; if the start is written `\\x`, the position of the `\\`).")
    if p["groups"]:
        X.append(f"* `group`: an unmatched `{C}` (`I` is its position) or a `{O}` that is never closed (`I` is the position of that `{O}`).")
    if p["refs"]:
        X.append(f"* `reference`: a bad back-reference (`I` is the position of the `{R}`).")
    X.append("")
    X.append("The pattern is read once from left to right and the **first** problem found is reported. A group that is never closed is only noticed at the end of the pattern, so problems after its `" + O + "`, if any, are reported first." if p["groups"] else "The pattern is read once from left to right and the **first** problem found is reported.")
    X.append("")
    X.append(K.interface_section(api, lang))
    X.append("## Examples")
    X.append("")
    X.append("| pattern | text | result |")
    X.append("|---|---|---|")
    for (pat, t), out in examples:
        X.append(f"| `{pat}` | `{t}` | `{out}` |")
    X.append("")
    X.append(K.run_hint(lang, api.mod))
    return "\n".join(X) + "\n"


def prompt(rng, p, api, lang):
    where = api.short(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    feats = ["wildcards"] + (["classes and a case flag"] if p["cls"] else []) + (["captures"] if p["caps"] else []) + (["groups with alternatives"] if p["groups"] else []) + (["greedy runs and back-references"] if p["refs"] else [])
    fl = ", ".join(feats[:-1]) + (" and " if len(feats) > 1 else "") + feats[-1]
    opts = [
        f"For {p['theme'][0]}, patterns have their own notation. Write the matcher `{fn}(pattern, text)` in {ln}, in {where}, as README.md describes ({fl}). {K.closer(rng)}",
        f"Implement the stencil matcher from README.md in {ln} (`{fn}`, {where}). This version has {fl}; the order in which alternatives are tried is part of the spec. {K.closer(rng)}",
        f"{ln} task: a small pattern-matching engine with an invented syntax: `{fn}` in {where}. README.md lists the symbols, the result format and the pattern errors. {K.closer(rng)}",
        f"Please write `{fn}` ({ln}, {where}) from README.md: whole-text matching with {fl}, plus precise error positions for malformed patterns.",
    ]
    return rng.choice(opts).strip()


LANG_PLAN = ["c", "javascript", "rust", "python", "c", "rust", "javascript", "rust"]
LEVELS = [1, 1, 2, 2, 3, 3, 4, 5]


@family("greenfield-stencil", category="greenfield", lang="mixed", kind="greenfield", n=8,
        summary="pattern matcher with an invented notation: wildcards, classes, case flag, captures, nested groups with alternatives, greedy runs and back-references, exact error positions")
def gen(rng, n):
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = LEVELS[i % len(LEVELS)]
        p = params(rng, level, i)
        api = K.Api(mod="stencil", fn="stencil", args=["pattern", "text"], arg_docs=["the pattern", "the text to test"], ret_doc="`no`, `yes` (with captures) or an error text", doc="stencil pattern matcher")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["stencil"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=level, slug=f"{i + 1:02d}-{lang}-{ {1: 'glob', 2: 'class', 3: 'caps', 4: 'groups', 5: 'refs'}[level] }-l{level}", oracle=(None if lang == "python" else ns["stencil"]),
            tags=["pattern", "parser", "backtracking"], notes={"level": level},
        )
