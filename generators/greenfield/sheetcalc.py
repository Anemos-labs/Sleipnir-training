"""A small spreadsheet engine: cell references, ranges, aggregate functions, lazy IF, error values and cycle detection."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

FN_NAMES = {
    "SUM": ["SUM", "TOTAL", "ADDUP"], "MIN": ["MIN", "LOWEST", "SMALLEST"], "MAX": ["MAX", "HIGHEST", "LARGEST"],
    "AVG": ["AVG", "MEAN", "AVERAGE"], "COUNT": ["COUNT", "TALLY", "NUMBERS"], "ABS": ["ABS", "MAGNITUDE", "ABSOLUTE"],
    "IF": ["IF", "WHEN", "PICK"], "CLAMP": ["CLAMP", "LIMIT", "BOUND"], "SNAP": ["SNAP", "ROUNDTO", "NEAREST"],
}
AGG = ["SUM", "MIN", "MAX", "AVG", "COUNT"]
LANG_PLAN = ["javascript", "go", "java", "python", "javascript", "go", "java", "javascript", "go", "java", "python", "go"]


def params(rng, level, i):
    avail = []
    if level >= 4:
        avail += ["SUM", "MIN", "MAX", "AVG", "COUNT", "ABS"]
    if level >= 5:
        avail += ["IF", "CLAMP", "SNAP"]
    names = {}
    used = set()
    for c in avail:
        nm = rng.choice(FN_NAMES[c]) if rng.random() < 0.6 else c
        if nm in used:
            nm = c
        used.add(nm)
        names[c] = nm
    return {"level": level, "names": names, "div": ["trunc", "floor", "exact"][(i + rng.randrange(3)) % 3], "order": rng.choice(["row", "col"]),
            "funcs": level >= 4, "cmp": level >= 5}


PY = r'''
LIMIT = 9999999
DIVMODE = "@DIV@"
ORDER = "@ORDER@"
HAS_FUNCS = @FUNCS@
HAS_CMP = @CMP@
FN = @FN_PY@
AGG = [FN[k] for k in ("SUM", "MIN", "MAX", "AVG", "COUNT") if k in FN]
CANON = {v: k for k, v in FN.items()}
DIG = "0123456789"
ALPHA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
CMPOPS = ("=", "<>", "<", "<=", ">", ">=")


class Err(Exception):
    def __init__(self, code):
        self.code = code


def valid_cell(t):
    return len(t) >= 2 and t[0] in "ABCDEFGHIJ" and all(c in DIG for c in t[1:]) and t[1] != "0" and len(t) <= 3


def tokenize(s):
    toks = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in " \t":
            i += 1
        elif c in DIG:
            j = i
            while j < n and s[j] in DIG:
                j += 1
            toks.append(("int", s[i:j]))
            i = j
        elif c in ALPHA:
            j = i
            while j < n and s[j] in ALPHA:
                j += 1
            k = j
            while k < n and s[k] in DIG:
                k += 1
            toks.append(("ref" if k > j else "name", s[i:k]))
            i = k
        elif HAS_CMP and s[i:i + 2] in ("<>", "<=", ">="):
            toks.append((s[i:i + 2], s[i:i + 2]))
            i += 2
        elif c in "+-*/%(),:" or (HAS_CMP and c in "=<>"):
            toks.append((c, c))
            i += 1
        else:
            raise Err("#SYN")
    return toks


class Parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self):
        return self.t[self.i][0] if self.i < len(self.t) else None

    def take(self):
        if self.i >= len(self.t):
            raise Err("#SYN")
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expect(self, k):
        if self.peek() != k:
            raise Err("#SYN")
        self.i += 1

    def expr(self):
        left = self.add()
        if self.peek() in CMPOPS:
            op = self.take()[0]
            return ("bin", op, left, self.add())
        return left

    def add(self):
        left = self.mul()
        while self.peek() in ("+", "-"):
            op = self.take()[0]
            left = ("bin", op, left, self.mul())
        return left

    def mul(self):
        left = self.unary()
        while self.peek() in ("*", "/", "%"):
            op = self.take()[0]
            left = ("bin", op, left, self.unary())
        return left

    def unary(self):
        if self.peek() == "-":
            self.take()
            return ("neg", self.unary())
        return self.atom()

    def atom(self):
        k, v = self.take()
        if k == "int":
            return ("int", v)
        if k == "ref":
            if self.peek() == ":":
                self.take()
                k2, v2 = self.take()
                if k2 != "ref":
                    raise Err("#SYN")
                return ("range", v, v2)
            return ("ref", v)
        if k == "name":
            if not HAS_FUNCS:
                raise Err("#SYN")
            self.expect("(")
            args = []
            if self.peek() != ")":
                args.append(self.expr())
                while self.peek() == ",":
                    self.take()
                    args.append(self.expr())
            self.expect(")")
            return ("call", v, args)
        if k == "(":
            e = self.expr()
            self.expect(")")
            return e
        raise Err("#SYN")


def validate(n, ok=False):
    k = n[0]
    if k == "range":
        if not ok:
            raise Err("#SYN")
    elif k == "neg":
        validate(n[1])
    elif k == "bin":
        validate(n[2])
        validate(n[3])
    elif k == "call":
        agg = n[1] in AGG
        for a in n[2]:
            validate(a, agg)


def parse_formula(text):
    p = Parser(tokenize(text))
    tree = p.expr()
    if p.i != len(p.t):
        raise Err("#SYN")
    validate(tree)
    return tree


def fdiv(a, b):
    return a // b


def tdiv(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def divide(a, b):
    if b == 0:
        raise Err("#DIV")
    if DIVMODE == "exact":
        if a % b != 0:
            raise Err("#DIV")
        return a // b
    return fdiv(a, b) if DIVMODE == "floor" else tdiv(a, b)


def modulo(a, b):
    if b == 0:
        raise Err("#DIV")
    if DIVMODE == "floor":
        return a % b
    return a - b * tdiv(a, b)


def bound(v):
    if abs(v) > LIMIT:
        raise Err("#NUM")
    return v


class Sheet:
    def __init__(self, defs):
        self.defs = defs
        self.memo = {}
        self.busy = set()

    def cell(self, name):
        if name not in self.defs:
            return 0
        if name in self.memo:
            v = self.memo[name]
        elif name in self.busy:
            raise Err("#CYC")
        else:
            self.busy.add(name)
            try:
                v = self.ev(parse_formula(self.defs[name]))
            except Err as e:
                v = e.code
            self.busy.discard(name)
            self.memo[name] = v
        if isinstance(v, str):
            raise Err(v)
        return v

    def ref(self, tok):
        if not valid_cell(tok):
            raise Err("#REF")
        return self.cell(tok)

    def rng(self, a, b):
        if not valid_cell(a) or not valid_cell(b):
            raise Err("#REF")
        c1, c2 = sorted((a[0], b[0]))
        r1, r2 = sorted((int(a[1:]), int(b[1:])))
        vals = []
        for r in range(r1, r2 + 1):
            for c in range(ord(c1), ord(c2) + 1):
                nm = chr(c) + str(r)
                if nm in self.defs:
                    vals.append(self.cell(nm))
        return vals

    def ev(self, n):
        k = n[0]
        if k == "int":
            return bound(int(n[1])) if len(n[1]) <= 9 else bound(LIMIT + 1)
        if k == "ref":
            return self.ref(n[1])
        if k == "neg":
            return -self.ev(n[1])
        if k == "bin":
            a = self.ev(n[2])
            b = self.ev(n[3])
            op = n[1]
            if op == "+":
                return bound(a + b)
            if op == "-":
                return bound(a - b)
            if op == "*":
                return bound(a * b)
            if op == "/":
                return divide(a, b)
            if op == "%":
                return modulo(a, b)
            return int({"=": a == b, "<>": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op])
        return self.call(n[1], n[2])

    def call(self, name, args):
        if name not in CANON:
            raise Err("#NAME")
        f = CANON[name]
        if f in ("SUM", "MIN", "MAX", "AVG", "COUNT"):
            if not args:
                raise Err("#ARG")
            vals = []
            for a in args:
                if a[0] == "range":
                    vals.extend(self.rng(a[1], a[2]))
                else:
                    vals.append(self.ev(a))
            if f == "SUM":
                return bound(sum(vals))
            if f == "COUNT":
                return len(vals)
            if not vals:
                raise Err("#NUM")
            if f == "MIN":
                return min(vals)
            if f == "MAX":
                return max(vals)
            return divide(sum(vals), len(vals))
        if f == "ABS":
            if len(args) != 1:
                raise Err("#ARG")
            return abs(self.ev(args[0]))
        if f == "IF":
            if len(args) != 3:
                raise Err("#ARG")
            return self.ev(args[1]) if self.ev(args[0]) != 0 else self.ev(args[2])
        if f == "CLAMP":
            if len(args) != 3:
                raise Err("#ARG")
            x = self.ev(args[0])
            lo = self.ev(args[1])
            hi = self.ev(args[2])
            if lo > hi:
                raise Err("#ARG")
            return min(max(x, lo), hi)
        if f == "SNAP":
            if len(args) != 2:
                raise Err("#ARG")
            x = self.ev(args[0])
            m = self.ev(args[1])
            if m <= 0:
                raise Err("#ARG")
            return bound((2 * x + m) // (2 * m) * m)
        raise Err("#NAME")


def sheet(source):
    defs = {}
    for no, raw in enumerate(source.split("\n"), 1):
        line = raw.strip(" \t")
        if line == "" or line[0] == "#":
            continue
        i = line.find("=")
        if i < 0:
            return "error: line %d" % no
        name = line[:i].strip(" \t")
        if not valid_cell(name):
            return "error: line %d" % no
        defs[name] = line[i + 1:].strip(" \t")
    sh = Sheet(defs)
    if ORDER == "row":
        names = sorted(defs, key=lambda c: (int(c[1:]), c[0]))
    else:
        names = sorted(defs, key=lambda c: (c[0], int(c[1:])))
    out = []
    for nm in names:
        try:
            v = str(sh.cell(nm))
        except Err as e:
            v = e.code
        out.append("%s = %s" % (nm, v))
    return "\n".join(out)
'''

JS = r'''
'use strict';

const LIMIT = 9999999;
const DIVMODE = '@DIV@';
const ORDER = '@ORDER@';
const HAS_FUNCS = @FUNCS@;
const HAS_CMP = @CMP@;
const FN = @FN_JS@;
const AGG = ['SUM', 'MIN', 'MAX', 'AVG', 'COUNT'].filter((k) => k in FN).map((k) => FN[k]);
const CANON = {};
for (const k of Object.keys(FN)) CANON[FN[k]] = k;
const DIG = '0123456789';
const ALPHA = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';
const CMPOPS = ['=', '<>', '<', '<=', '>', '>='];

class Err extends Error {
  constructor(code) { super(code); this.code = code; }
}

function validCell(t) {
  if (t.length < 2 || t.length > 3 || 'ABCDEFGHIJ'.indexOf(t[0]) < 0 || t[1] === '0') return false;
  for (let i = 1; i < t.length; i++) if (DIG.indexOf(t[i]) < 0) return false;
  return true;
}

function tokenize(s) {
  const toks = [];
  let i = 0;
  const n = s.length;
  while (i < n) {
    const c = s[i];
    if (c === ' ' || c === '\t') { i++; }
    else if (DIG.includes(c)) {
      let j = i;
      while (j < n && DIG.includes(s[j])) j++;
      toks.push(['int', s.slice(i, j)]);
      i = j;
    } else if (ALPHA.includes(c)) {
      let j = i;
      while (j < n && ALPHA.includes(s[j])) j++;
      let k = j;
      while (k < n && DIG.includes(s[k])) k++;
      toks.push([k > j ? 'ref' : 'name', s.slice(i, k)]);
      i = k;
    } else if (HAS_CMP && ['<>', '<=', '>='].includes(s.slice(i, i + 2))) {
      toks.push([s.slice(i, i + 2), s.slice(i, i + 2)]);
      i += 2;
    } else if ('+-*/%(),:'.includes(c) || (HAS_CMP && '=<>'.includes(c))) {
      toks.push([c, c]);
      i++;
    } else throw new Err('#SYN');
  }
  return toks;
}

function parseFormula(text) {
  const t = tokenize(text);
  let i = 0;
  const peek = () => (i < t.length ? t[i][0] : null);
  const take = () => { if (i >= t.length) throw new Err('#SYN'); return t[i++]; };
  const expect = (k) => { if (peek() !== k) throw new Err('#SYN'); i++; };
  function expr() {
    const left = add();
    if (CMPOPS.includes(peek())) { const op = take()[0]; return ['bin', op, left, add()]; }
    return left;
  }
  function add() {
    let left = mul();
    while (peek() === '+' || peek() === '-') { const op = take()[0]; left = ['bin', op, left, mul()]; }
    return left;
  }
  function mul() {
    let left = unary();
    while (peek() === '*' || peek() === '/' || peek() === '%') { const op = take()[0]; left = ['bin', op, left, unary()]; }
    return left;
  }
  function unary() {
    if (peek() === '-') { take(); return ['neg', unary()]; }
    return atom();
  }
  function atom() {
    const [k, v] = take();
    if (k === 'int') return ['int', v];
    if (k === 'ref') {
      if (peek() === ':') {
        take();
        const [k2, v2] = take();
        if (k2 !== 'ref') throw new Err('#SYN');
        return ['range', v, v2];
      }
      return ['ref', v];
    }
    if (k === 'name') {
      if (!HAS_FUNCS) throw new Err('#SYN');
      expect('(');
      const args = [];
      if (peek() !== ')') {
        args.push(expr());
        while (peek() === ',') { take(); args.push(expr()); }
      }
      expect(')');
      return ['call', v, args];
    }
    if (k === '(') { const e = expr(); expect(')'); return e; }
    throw new Err('#SYN');
  }
  function validate(n, ok) {
    if (n[0] === 'range') { if (!ok) throw new Err('#SYN'); }
    else if (n[0] === 'neg') validate(n[1], false);
    else if (n[0] === 'bin') { validate(n[2], false); validate(n[3], false); }
    else if (n[0] === 'call') { const agg = AGG.includes(n[1]); for (const a of n[2]) validate(a, agg); }
  }
  const tree = expr();
  if (i !== t.length) throw new Err('#SYN');
  validate(tree, false);
  return tree;
}

function fdiv(a, b) {
  let q = Math.trunc(a / b);
  if (a % b !== 0 && (a < 0) !== (b < 0)) q--;
  return q;
}

function divide(a, b) {
  if (b === 0) throw new Err('#DIV');
  if (DIVMODE === 'exact') {
    if (a % b !== 0) throw new Err('#DIV');
    return a / b;
  }
  return DIVMODE === 'floor' ? fdiv(a, b) : Math.trunc(a / b);
}

function modulo(a, b) {
  if (b === 0) throw new Err('#DIV');
  if (DIVMODE === 'floor') return a - b * fdiv(a, b);
  return a - b * Math.trunc(a / b);
}

function bound(v) {
  if (Math.abs(v) > LIMIT) throw new Err('#NUM');
  return v;
}

function sheet(source) {
  const defs = new Map();
  const lines = source.split('\n');
  for (let no = 1; no <= lines.length; no++) {
    const line = lines[no - 1].replace(/^[ \t]+|[ \t]+$/g, '');
    if (line === '' || line[0] === '#') continue;
    const i = line.indexOf('=');
    if (i < 0) return `error: line ${no}`;
    const name = line.slice(0, i).replace(/^[ \t]+|[ \t]+$/g, '');
    if (!validCell(name)) return `error: line ${no}`;
    defs.set(name, line.slice(i + 1).replace(/^[ \t]+|[ \t]+$/g, ''));
  }
  const memo = new Map();
  const busy = new Set();

  function cell(name) {
    if (!defs.has(name)) return 0;
    let v;
    if (memo.has(name)) v = memo.get(name);
    else if (busy.has(name)) throw new Err('#CYC');
    else {
      busy.add(name);
      try { v = ev(parseFormula(defs.get(name))); }
      catch (e) { if (e instanceof Err) v = e.code; else throw e; }
      busy.delete(name);
      memo.set(name, v);
    }
    if (typeof v === 'string') throw new Err(v);
    return v;
  }
  function ref(tok) {
    if (!validCell(tok)) throw new Err('#REF');
    return cell(tok);
  }
  function range(a, b) {
    if (!validCell(a) || !validCell(b)) throw new Err('#REF');
    const cs = [a[0], b[0]].sort();
    const rs = [parseInt(a.slice(1), 10), parseInt(b.slice(1), 10)].sort((x, y) => x - y);
    const vals = [];
    for (let r = rs[0]; r <= rs[1]; r++) {
      for (let c = cs[0].charCodeAt(0); c <= cs[1].charCodeAt(0); c++) {
        const nm = String.fromCharCode(c) + r;
        if (defs.has(nm)) vals.push(cell(nm));
      }
    }
    return vals;
  }
  function ev(n) {
    const k = n[0];
    if (k === 'int') return n[1].length <= 9 ? bound(parseInt(n[1], 10)) : bound(LIMIT + 1);
    if (k === 'ref') return ref(n[1]);
    if (k === 'neg') return -ev(n[1]);
    if (k === 'bin') {
      const a = ev(n[2]);
      const b = ev(n[3]);
      switch (n[1]) {
        case '+': return bound(a + b);
        case '-': return bound(a - b);
        case '*': return bound(a * b);
        case '/': return divide(a, b);
        case '%': return modulo(a, b);
        case '=': return a === b ? 1 : 0;
        case '<>': return a !== b ? 1 : 0;
        case '<': return a < b ? 1 : 0;
        case '<=': return a <= b ? 1 : 0;
        case '>': return a > b ? 1 : 0;
        default: return a >= b ? 1 : 0;
      }
    }
    return call(n[1], n[2]);
  }
  function call(name, args) {
    if (!(name in CANON)) throw new Err('#NAME');
    const f = CANON[name];
    if (['SUM', 'MIN', 'MAX', 'AVG', 'COUNT'].includes(f)) {
      if (args.length === 0) throw new Err('#ARG');
      let vals = [];
      for (const a of args) {
        if (a[0] === 'range') vals = vals.concat(range(a[1], a[2]));
        else vals.push(ev(a));
      }
      if (f === 'SUM') return bound(vals.reduce((x, y) => x + y, 0));
      if (f === 'COUNT') return vals.length;
      if (vals.length === 0) throw new Err('#NUM');
      if (f === 'MIN') return Math.min(...vals);
      if (f === 'MAX') return Math.max(...vals);
      return divide(vals.reduce((x, y) => x + y, 0), vals.length);
    }
    if (f === 'ABS') {
      if (args.length !== 1) throw new Err('#ARG');
      return Math.abs(ev(args[0]));
    }
    if (f === 'IF') {
      if (args.length !== 3) throw new Err('#ARG');
      return ev(args[0]) !== 0 ? ev(args[1]) : ev(args[2]);
    }
    if (f === 'CLAMP') {
      if (args.length !== 3) throw new Err('#ARG');
      const x = ev(args[0]);
      const lo = ev(args[1]);
      const hi = ev(args[2]);
      if (lo > hi) throw new Err('#ARG');
      return Math.min(Math.max(x, lo), hi);
    }
    if (f === 'SNAP') {
      if (args.length !== 2) throw new Err('#ARG');
      const x = ev(args[0]);
      const m = ev(args[1]);
      if (m <= 0) throw new Err('#ARG');
      return bound(fdiv(2 * x + m, 2 * m) * m);
    }
    throw new Err('#NAME');
  }

  const names = [...defs.keys()];
  const colOf = (c) => c[0];
  const rowOf = (c) => parseInt(c.slice(1), 10);
  if (ORDER === 'row') names.sort((a, b) => rowOf(a) - rowOf(b) || (colOf(a) < colOf(b) ? -1 : 1));
  else names.sort((a, b) => (colOf(a) === colOf(b) ? rowOf(a) - rowOf(b) : colOf(a) < colOf(b) ? -1 : 1));
  const out = [];
  for (const nm of names) {
    let v;
    try { v = String(cell(nm)); }
    catch (e) { if (e instanceof Err) v = e.code; else throw e; }
    out.push(`${nm} = ${v}`);
  }
  return out.join('\n');
}

module.exports = { sheet };
'''

GO = r'''
package sheetcalc

import (
	"fmt"
	"sort"
	"strconv"
	"strings"
)

const (
	limit    = 9999999
	divMode  = "@DIV@"
	order    = "@ORDER@"
	hasFuncs = @FUNCS@
	hasCmp   = @CMP@
)

var fn = @FN_GO@

const dig = "0123456789"
const alpha = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

type errCode struct{ code string }

func raise(c string) { panic(errCode{c}) }

func canon(name string) (string, bool) {
	for k, v := range fn {
		if v == name {
			return k, true
		}
	}
	return "", false
}

func isAgg(name string) bool {
	if c, ok := canon(name); ok {
		switch c {
		case "SUM", "MIN", "MAX", "AVG", "COUNT":
			return true
		}
	}
	return false
}

func validCell(t string) bool {
	if len(t) < 2 || len(t) > 3 || !strings.ContainsRune("ABCDEFGHIJ", rune(t[0])) || t[1] == '0' {
		return false
	}
	for i := 1; i < len(t); i++ {
		if !strings.ContainsRune(dig, rune(t[i])) {
			return false
		}
	}
	return true
}

type tok struct{ kind, text string }

func tokenize(s string) []tok {
	var out []tok
	i, n := 0, len(s)
	for i < n {
		c := s[i]
		switch {
		case c == ' ' || c == '\t':
			i++
		case strings.IndexByte(dig, c) >= 0:
			j := i
			for j < n && strings.IndexByte(dig, s[j]) >= 0 {
				j++
			}
			out = append(out, tok{"int", s[i:j]})
			i = j
		case strings.IndexByte(alpha, c) >= 0:
			j := i
			for j < n && strings.IndexByte(alpha, s[j]) >= 0 {
				j++
			}
			k := j
			for k < n && strings.IndexByte(dig, s[k]) >= 0 {
				k++
			}
			kind := "name"
			if k > j {
				kind = "ref"
			}
			out = append(out, tok{kind, s[i:k]})
			i = k
		case hasCmp && i+1 < n && (s[i:i+2] == "<>" || s[i:i+2] == "<=" || s[i:i+2] == ">="):
			out = append(out, tok{s[i : i+2], s[i : i+2]})
			i += 2
		case strings.IndexByte("+-*/%(),:", c) >= 0 || (hasCmp && strings.IndexByte("=<>", c) >= 0):
			out = append(out, tok{string(c), string(c)})
			i++
		default:
			raise("#SYN")
		}
	}
	return out
}

type node struct {
	kind string // int ref range neg bin call
	text string
	op   string
	a, b *node
	args []*node
	t2   string
}

type parser struct {
	t []tok
	i int
}

func (p *parser) peek() string {
	if p.i < len(p.t) {
		return p.t[p.i].kind
	}
	return ""
}

func (p *parser) take() tok {
	if p.i >= len(p.t) {
		raise("#SYN")
	}
	t := p.t[p.i]
	p.i++
	return t
}

func (p *parser) expect(k string) {
	if p.peek() != k {
		raise("#SYN")
	}
	p.i++
}

func isCmp(k string) bool {
	return k == "=" || k == "<>" || k == "<" || k == "<=" || k == ">" || k == ">="
}

func (p *parser) expr() *node {
	left := p.add()
	if isCmp(p.peek()) {
		op := p.take().kind
		return &node{kind: "bin", op: op, a: left, b: p.add()}
	}
	return left
}

func (p *parser) add() *node {
	left := p.mul()
	for p.peek() == "+" || p.peek() == "-" {
		op := p.take().kind
		left = &node{kind: "bin", op: op, a: left, b: p.mul()}
	}
	return left
}

func (p *parser) mul() *node {
	left := p.unary()
	for p.peek() == "*" || p.peek() == "/" || p.peek() == "%" {
		op := p.take().kind
		left = &node{kind: "bin", op: op, a: left, b: p.unary()}
	}
	return left
}

func (p *parser) unary() *node {
	if p.peek() == "-" {
		p.take()
		return &node{kind: "neg", a: p.unary()}
	}
	return p.atom()
}

func (p *parser) atom() *node {
	t := p.take()
	switch t.kind {
	case "int":
		return &node{kind: "int", text: t.text}
	case "ref":
		if p.peek() == ":" {
			p.take()
			t2 := p.take()
			if t2.kind != "ref" {
				raise("#SYN")
			}
			return &node{kind: "range", text: t.text, t2: t2.text}
		}
		return &node{kind: "ref", text: t.text}
	case "name":
		if !hasFuncs {
			raise("#SYN")
		}
		p.expect("(")
		var args []*node
		if p.peek() != ")" {
			args = append(args, p.expr())
			for p.peek() == "," {
				p.take()
				args = append(args, p.expr())
			}
		}
		p.expect(")")
		return &node{kind: "call", text: t.text, args: args}
	case "(":
		e := p.expr()
		p.expect(")")
		return e
	}
	raise("#SYN")
	return nil
}

func validate(n *node, ok bool) {
	switch n.kind {
	case "range":
		if !ok {
			raise("#SYN")
		}
	case "neg":
		validate(n.a, false)
	case "bin":
		validate(n.a, false)
		validate(n.b, false)
	case "call":
		agg := isAgg(n.text)
		for _, a := range n.args {
			validate(a, agg)
		}
	}
}

func parseFormula(text string) *node {
	p := &parser{t: tokenize(text)}
	tree := p.expr()
	if p.i != len(p.t) {
		raise("#SYN")
	}
	validate(tree, false)
	return tree
}

func fdiv(a, b int64) int64 {
	q := a / b
	if a%b != 0 && ((a < 0) != (b < 0)) {
		q--
	}
	return q
}

func divide(a, b int64) int64 {
	if b == 0 {
		raise("#DIV")
	}
	if divMode == "exact" {
		if a%b != 0 {
			raise("#DIV")
		}
		return a / b
	}
	if divMode == "floor" {
		return fdiv(a, b)
	}
	return a / b
}

func modulo(a, b int64) int64 {
	if b == 0 {
		raise("#DIV")
	}
	if divMode == "floor" {
		return a - b*fdiv(a, b)
	}
	return a - b*(a/b)
}

func bound(v int64) int64 {
	if v > limit || v < -limit {
		raise("#NUM")
	}
	return v
}

type result struct {
	v   int64
	err string
}

type engine struct {
	defs map[string]string
	memo map[string]result
	busy map[string]bool
}

func (e *engine) cell(name string) int64 {
	if _, ok := e.defs[name]; !ok {
		return 0
	}
	r, done := e.memo[name]
	if !done {
		if e.busy[name] {
			raise("#CYC")
		}
		e.busy[name] = true
		r = e.eval(name)
		delete(e.busy, name)
		e.memo[name] = r
	}
	if r.err != "" {
		raise(r.err)
	}
	return r.v
}

func (e *engine) eval(name string) (res result) {
	defer func() {
		if r := recover(); r != nil {
			if ec, ok := r.(errCode); ok {
				res = result{err: ec.code}
				return
			}
			panic(r)
		}
	}()
	return result{v: e.ev(parseFormula(e.defs[name]))}
}

func (e *engine) ref(tok string) int64 {
	if !validCell(tok) {
		raise("#REF")
	}
	return e.cell(tok)
}

func (e *engine) rng(a, b string) []int64 {
	if !validCell(a) || !validCell(b) {
		raise("#REF")
	}
	c1, c2 := a[0], b[0]
	if c1 > c2 {
		c1, c2 = c2, c1
	}
	r1, _ := strconv.Atoi(a[1:])
	r2, _ := strconv.Atoi(b[1:])
	if r1 > r2 {
		r1, r2 = r2, r1
	}
	var vals []int64
	for r := r1; r <= r2; r++ {
		for c := c1; c <= c2; c++ {
			nm := string(rune(c)) + strconv.Itoa(r)
			if _, ok := e.defs[nm]; ok {
				vals = append(vals, e.cell(nm))
			}
		}
	}
	return vals
}

func b2i(b bool) int64 {
	if b {
		return 1
	}
	return 0
}

func sum(v []int64) int64 {
	var s int64
	for _, x := range v {
		s += x
	}
	return s
}

func (e *engine) ev(n *node) int64 {
	switch n.kind {
	case "int":
		if len(n.text) <= 9 {
			v, _ := strconv.ParseInt(n.text, 10, 64)
			return bound(v)
		}
		return bound(limit + 1)
	case "ref":
		return e.ref(n.text)
	case "neg":
		return -e.ev(n.a)
	case "bin":
		a := e.ev(n.a)
		b := e.ev(n.b)
		switch n.op {
		case "+":
			return bound(a + b)
		case "-":
			return bound(a - b)
		case "*":
			return bound(a * b)
		case "/":
			return divide(a, b)
		case "%":
			return modulo(a, b)
		case "=":
			return b2i(a == b)
		case "<>":
			return b2i(a != b)
		case "<":
			return b2i(a < b)
		case "<=":
			return b2i(a <= b)
		case ">":
			return b2i(a > b)
		}
		return b2i(a >= b)
	}
	return e.call(n.text, n.args)
}

func (e *engine) call(name string, args []*node) int64 {
	f, ok := canon(name)
	if !ok {
		raise("#NAME")
	}
	switch f {
	case "SUM", "MIN", "MAX", "AVG", "COUNT":
		if len(args) == 0 {
			raise("#ARG")
		}
		var vals []int64
		for _, a := range args {
			if a.kind == "range" {
				vals = append(vals, e.rng(a.text, a.t2)...)
			} else {
				vals = append(vals, e.ev(a))
			}
		}
		if f == "SUM" {
			return bound(sum(vals))
		}
		if f == "COUNT" {
			return int64(len(vals))
		}
		if len(vals) == 0 {
			raise("#NUM")
		}
		if f == "MIN" || f == "MAX" {
			best := vals[0]
			for _, v := range vals {
				if (f == "MIN" && v < best) || (f == "MAX" && v > best) {
					best = v
				}
			}
			return best
		}
		return divide(sum(vals), int64(len(vals)))
	case "ABS":
		if len(args) != 1 {
			raise("#ARG")
		}
		v := e.ev(args[0])
		if v < 0 {
			v = -v
		}
		return v
	case "IF":
		if len(args) != 3 {
			raise("#ARG")
		}
		if e.ev(args[0]) != 0 {
			return e.ev(args[1])
		}
		return e.ev(args[2])
	case "CLAMP":
		if len(args) != 3 {
			raise("#ARG")
		}
		x := e.ev(args[0])
		lo := e.ev(args[1])
		hi := e.ev(args[2])
		if lo > hi {
			raise("#ARG")
		}
		if x < lo {
			x = lo
		}
		if x > hi {
			x = hi
		}
		return x
	case "SNAP":
		if len(args) != 2 {
			raise("#ARG")
		}
		x := e.ev(args[0])
		m := e.ev(args[1])
		if m <= 0 {
			raise("#ARG")
		}
		return bound(fdiv(2*x+m, 2*m) * m)
	}
	raise("#NAME")
	return 0
}

func trimBlank(s string) string { return strings.Trim(s, " \t") }

// Sheet evaluates a spreadsheet source text.
func Sheet(source string) string {
	defs := map[string]string{}
	for i, raw := range strings.Split(source, "\n") {
		no := i + 1
		line := trimBlank(raw)
		if line == "" || line[0] == '#' {
			continue
		}
		k := strings.IndexByte(line, '=')
		if k < 0 {
			return fmt.Sprintf("error: line %d", no)
		}
		name := trimBlank(line[:k])
		if !validCell(name) {
			return fmt.Sprintf("error: line %d", no)
		}
		defs[name] = trimBlank(line[k+1:])
	}
	e := &engine{defs: defs, memo: map[string]result{}, busy: map[string]bool{}}
	var names []string
	for k := range defs {
		names = append(names, k)
	}
	rowOf := func(c string) int { v, _ := strconv.Atoi(c[1:]); return v }
	sort.Slice(names, func(i, j int) bool {
		a, b := names[i], names[j]
		if order == "row" {
			if rowOf(a) != rowOf(b) {
				return rowOf(a) < rowOf(b)
			}
			return a[0] < b[0]
		}
		if a[0] != b[0] {
			return a[0] < b[0]
		}
		return rowOf(a) < rowOf(b)
	})
	var out []string
	for _, nm := range names {
		var v string
		func() {
			defer func() {
				if r := recover(); r != nil {
					if ec, ok := r.(errCode); ok {
						v = ec.code
						return
					}
					panic(r)
				}
			}()
			v = strconv.FormatInt(e.cell(nm), 10)
		}()
		out = append(out, nm+" = "+v)
	}
	return strings.Join(out, "\n")
}
'''

JV = r'''
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class Sheetcalc {
    static final long LIMIT = 9999999L;
    static final String DIVMODE = "@DIV@";
    static final String ORDER = "@ORDER@";
    static final boolean HAS_FUNCS = @FUNCS@;
    static final boolean HAS_CMP = @CMP@;
    static final String[][] FN = @FN_JAVA@;
    static final String DIG = "0123456789";
    static final String ALPHA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";

    static class Err extends RuntimeException {
        final String code;
        Err(String code) { super(code, null, false, false); this.code = code; }
    }

    static String canon(String name) {
        for (String[] kv : FN) if (kv[1].equals(name)) return kv[0];
        return null;
    }

    static boolean isAgg(String name) {
        String c = canon(name);
        return c != null && (c.equals("SUM") || c.equals("MIN") || c.equals("MAX") || c.equals("AVG") || c.equals("COUNT"));
    }

    static boolean validCell(String t) {
        if (t.length() < 2 || t.length() > 3 || "ABCDEFGHIJ".indexOf(t.charAt(0)) < 0 || t.charAt(1) == '0') return false;
        for (int i = 1; i < t.length(); i++) if (DIG.indexOf(t.charAt(i)) < 0) return false;
        return true;
    }

    static String[][] tokenize(String s) {
        List<String[]> toks = new ArrayList<>();
        int i = 0, n = s.length();
        while (i < n) {
            char c = s.charAt(i);
            if (c == ' ' || c == '\t') { i++; }
            else if (DIG.indexOf(c) >= 0) {
                int j = i;
                while (j < n && DIG.indexOf(s.charAt(j)) >= 0) j++;
                toks.add(new String[] { "int", s.substring(i, j) });
                i = j;
            } else if (ALPHA.indexOf(c) >= 0) {
                int j = i;
                while (j < n && ALPHA.indexOf(s.charAt(j)) >= 0) j++;
                int k = j;
                while (k < n && DIG.indexOf(s.charAt(k)) >= 0) k++;
                toks.add(new String[] { k > j ? "ref" : "name", s.substring(i, k) });
                i = k;
            } else if (HAS_CMP && i + 1 < n && (s.startsWith("<>", i) || s.startsWith("<=", i) || s.startsWith(">=", i))) {
                toks.add(new String[] { s.substring(i, i + 2), s.substring(i, i + 2) });
                i += 2;
            } else if ("+-*/%(),:".indexOf(c) >= 0 || (HAS_CMP && "=<>".indexOf(c) >= 0)) {
                toks.add(new String[] { String.valueOf(c), String.valueOf(c) });
                i++;
            } else throw new Err("#SYN");
        }
        return toks.toArray(new String[0][]);
    }

    static class Node {
        String kind, text, op, t2;
        Node a, b;
        List<Node> args = new ArrayList<>();
        Node(String kind) { this.kind = kind; }
    }

    static class Parser {
        String[][] t;
        int i = 0;
        Parser(String[][] t) { this.t = t; }
        String peek() { return i < t.length ? t[i][0] : ""; }
        String[] take() { if (i >= t.length) throw new Err("#SYN"); return t[i++]; }
        void expect(String k) { if (!peek().equals(k)) throw new Err("#SYN"); i++; }
        boolean isCmp(String k) { return Arrays.asList("=", "<>", "<", "<=", ">", ">=").contains(k); }
        Node bin(String op, Node a, Node b) { Node n = new Node("bin"); n.op = op; n.a = a; n.b = b; return n; }
        Node expr() {
            Node left = add();
            if (isCmp(peek())) { String op = take()[0]; return bin(op, left, add()); }
            return left;
        }
        Node add() {
            Node left = mul();
            while (peek().equals("+") || peek().equals("-")) { String op = take()[0]; left = bin(op, left, mul()); }
            return left;
        }
        Node mul() {
            Node left = unary();
            while (peek().equals("*") || peek().equals("/") || peek().equals("%")) { String op = take()[0]; left = bin(op, left, unary()); }
            return left;
        }
        Node unary() {
            if (peek().equals("-")) { take(); Node n = new Node("neg"); n.a = unary(); return n; }
            return atom();
        }
        Node atom() {
            String[] tk = take();
            String k = tk[0], v = tk[1];
            if (k.equals("int")) { Node n = new Node("int"); n.text = v; return n; }
            if (k.equals("ref")) {
                if (peek().equals(":")) {
                    take();
                    String[] t2 = take();
                    if (!t2[0].equals("ref")) throw new Err("#SYN");
                    Node n = new Node("range"); n.text = v; n.t2 = t2[1]; return n;
                }
                Node n = new Node("ref"); n.text = v; return n;
            }
            if (k.equals("name")) {
                if (!HAS_FUNCS) throw new Err("#SYN");
                expect("(");
                Node n = new Node("call"); n.text = v;
                if (!peek().equals(")")) {
                    n.args.add(expr());
                    while (peek().equals(",")) { take(); n.args.add(expr()); }
                }
                expect(")");
                return n;
            }
            if (k.equals("(")) { Node e = expr(); expect(")"); return e; }
            throw new Err("#SYN");
        }
    }

    static void validate(Node n, boolean ok) {
        switch (n.kind) {
            case "range": if (!ok) throw new Err("#SYN"); break;
            case "neg": validate(n.a, false); break;
            case "bin": validate(n.a, false); validate(n.b, false); break;
            case "call": { boolean agg = isAgg(n.text); for (Node a : n.args) validate(a, agg); break; }
            default: break;
        }
    }

    static Node parseFormula(String text) {
        Parser p = new Parser(tokenize(text));
        Node tree = p.expr();
        if (p.i != p.t.length) throw new Err("#SYN");
        validate(tree, false);
        return tree;
    }

    static long fdiv(long a, long b) {
        long q = a / b;
        if (a % b != 0 && ((a < 0) != (b < 0))) q--;
        return q;
    }

    static long divide(long a, long b) {
        if (b == 0) throw new Err("#DIV");
        if (DIVMODE.equals("exact")) {
            if (a % b != 0) throw new Err("#DIV");
            return a / b;
        }
        return DIVMODE.equals("floor") ? fdiv(a, b) : a / b;
    }

    static long modulo(long a, long b) {
        if (b == 0) throw new Err("#DIV");
        if (DIVMODE.equals("floor")) return a - b * fdiv(a, b);
        return a - b * (a / b);
    }

    static long bound(long v) {
        if (Math.abs(v) > LIMIT) throw new Err("#NUM");
        return v;
    }

    static Map<String, String> defs;
    static Map<String, Object> memo;
    static Set<String> busy;

    static long cell(String name) {
        if (!defs.containsKey(name)) return 0;
        Object v;
        if (memo.containsKey(name)) v = memo.get(name);
        else if (busy.contains(name)) throw new Err("#CYC");
        else {
            busy.add(name);
            try { v = ev(parseFormula(defs.get(name))); }
            catch (Err e) { v = e.code; }
            busy.remove(name);
            memo.put(name, v);
        }
        if (v instanceof String) throw new Err((String) v);
        return (Long) v;
    }

    static long ref(String tok) {
        if (!validCell(tok)) throw new Err("#REF");
        return cell(tok);
    }

    static List<Long> range(String a, String b) {
        if (!validCell(a) || !validCell(b)) throw new Err("#REF");
        char c1 = a.charAt(0), c2 = b.charAt(0);
        if (c1 > c2) { char t = c1; c1 = c2; c2 = t; }
        int r1 = Integer.parseInt(a.substring(1)), r2 = Integer.parseInt(b.substring(1));
        if (r1 > r2) { int t = r1; r1 = r2; r2 = t; }
        List<Long> vals = new ArrayList<>();
        for (int r = r1; r <= r2; r++)
            for (char c = c1; c <= c2; c++) {
                String nm = "" + c + r;
                if (defs.containsKey(nm)) vals.add(cell(nm));
            }
        return vals;
    }

    static long ev(Node n) {
        switch (n.kind) {
            case "int": return n.text.length() <= 9 ? bound(Long.parseLong(n.text)) : bound(LIMIT + 1);
            case "ref": return ref(n.text);
            case "neg": return -ev(n.a);
            case "bin": {
                long a = ev(n.a);
                long b = ev(n.b);
                switch (n.op) {
                    case "+": return bound(a + b);
                    case "-": return bound(a - b);
                    case "*": return bound(a * b);
                    case "/": return divide(a, b);
                    case "%": return modulo(a, b);
                    case "=": return a == b ? 1 : 0;
                    case "<>": return a != b ? 1 : 0;
                    case "<": return a < b ? 1 : 0;
                    case "<=": return a <= b ? 1 : 0;
                    case ">": return a > b ? 1 : 0;
                    default: return a >= b ? 1 : 0;
                }
            }
            default: return call(n.text, n.args);
        }
    }

    static long sum(List<Long> v) { long s = 0; for (long x : v) s += x; return s; }

    static long call(String name, List<Node> args) {
        String f = canon(name);
        if (f == null) throw new Err("#NAME");
        switch (f) {
            case "SUM": case "MIN": case "MAX": case "AVG": case "COUNT": {
                if (args.isEmpty()) throw new Err("#ARG");
                List<Long> vals = new ArrayList<>();
                for (Node a : args) {
                    if (a.kind.equals("range")) vals.addAll(range(a.text, a.t2));
                    else vals.add(ev(a));
                }
                if (f.equals("SUM")) return bound(sum(vals));
                if (f.equals("COUNT")) return vals.size();
                if (vals.isEmpty()) throw new Err("#NUM");
                if (f.equals("MIN")) return Collections.min(vals);
                if (f.equals("MAX")) return Collections.max(vals);
                return divide(sum(vals), vals.size());
            }
            case "ABS":
                if (args.size() != 1) throw new Err("#ARG");
                return Math.abs(ev(args.get(0)));
            case "IF":
                if (args.size() != 3) throw new Err("#ARG");
                return ev(args.get(0)) != 0 ? ev(args.get(1)) : ev(args.get(2));
            case "CLAMP": {
                if (args.size() != 3) throw new Err("#ARG");
                long x = ev(args.get(0));
                long lo = ev(args.get(1));
                long hi = ev(args.get(2));
                if (lo > hi) throw new Err("#ARG");
                return Math.min(Math.max(x, lo), hi);
            }
            case "SNAP": {
                if (args.size() != 2) throw new Err("#ARG");
                long x = ev(args.get(0));
                long m = ev(args.get(1));
                if (m <= 0) throw new Err("#ARG");
                return bound(fdiv(2 * x + m, 2 * m) * m);
            }
            default: throw new Err("#NAME");
        }
    }

    static String blanks(String s) {
        int a = 0, b = s.length();
        while (a < b && (s.charAt(a) == ' ' || s.charAt(a) == '\t')) a++;
        while (b > a && (s.charAt(b - 1) == ' ' || s.charAt(b - 1) == '\t')) b--;
        return s.substring(a, b);
    }

    public static String sheet(String source) {
        defs = new HashMap<>();
        memo = new HashMap<>();
        busy = new HashSet<>();
        String[] lines = source.split("\n", -1);
        for (int i = 0; i < lines.length; i++) {
            String line = blanks(lines[i]);
            if (line.isEmpty() || line.charAt(0) == '#') continue;
            int k = line.indexOf('=');
            if (k < 0) return "error: line " + (i + 1);
            String name = blanks(line.substring(0, k));
            if (!validCell(name)) return "error: line " + (i + 1);
            defs.put(name, blanks(line.substring(k + 1)));
        }
        List<String> names = new ArrayList<>(defs.keySet());
        Collections.sort(names, (a, b) -> {
            int ra = Integer.parseInt(a.substring(1)), rb = Integer.parseInt(b.substring(1));
            if (ORDER.equals("row")) return ra != rb ? Integer.compare(ra, rb) : Character.compare(a.charAt(0), b.charAt(0));
            return a.charAt(0) != b.charAt(0) ? Character.compare(a.charAt(0), b.charAt(0)) : Integer.compare(ra, rb);
        });
        StringBuilder out = new StringBuilder();
        for (String nm : names) {
            String v;
            try { v = Long.toString(cell(nm)); }
            catch (Err e) { v = e.code; }
            if (out.length() > 0) out.append("\n");
            out.append(nm).append(" = ").append(v);
        }
        return out.toString();
    }
}
'''


def _b(lang, v):
    if lang == "python":
        return "True" if v else "False"
    return "true" if v else "false"


def sol(lang, p):
    fn = p["names"]
    fp = "{" + ", ".join(f'"{k}": "{v}"' for k, v in fn.items()) + "}"
    fj = "{" + ", ".join(f'"{k}": "{v}"' for k, v in fn.items()) + "}"
    fg = "map[string]string{" + ", ".join(f'"{k}": "{v}"' for k, v in fn.items()) + "}"
    fjv = "{" + ", ".join(f'{{"{k}", "{v}"}}' for k, v in fn.items()) + "}"
    if not fn:
        fjv = "{}"
    src = {"python": PY, "javascript": JS, "go": GO, "java": JV}[lang]
    return K.subst(src, DIV=p["div"], ORDER=p["order"], FUNCS=_b(lang, p["funcs"]), CMP=_b(lang, p["cmp"]),
                   FN_PY=fp, FN_JS=fj, FN_GO=fg, FN_JAVA=fjv).lstrip("\n")


# ---------------------------------------------------------------------------------------------------------------

def readme(p, api, lang, examples):
    names = p["names"]
    L = ["# Sheet engine", ""]
    L.append("A tiny spreadsheet engine for the planning tool of a harbour office. `sheet(source)` takes the text of a sheet (one cell per line), "
             "evaluates every cell and returns the values as text. Numbers are integers; there are no decimals, strings or dates.")
    L.append("")
    L.append("## Sheet text")
    L.append("")
    L.append("Lines are separated by `\\n`; line numbers count from 1. Leading and trailing blanks (spaces, tabs) of a line are ignored; a line that is then empty, "
             "or starts with `#`, is skipped. Every other line is `CELL = FORMULA`: the text before the **first** `=` (blanks trimmed) must be a valid cell name, "
             "the text after it (blanks trimmed, possibly empty) is the formula. A later line for the same cell replaces the earlier one.")
    L.append("")
    L.append("A **cell name** is a column letter `A` to `J` followed by a row number `1` to `99` written without a leading zero (`A1`, `J99`, `C10`). "
             "If a line is not of the form `CELL = FORMULA` (no `=`, or an invalid cell name) the whole result is `error: line N` for the first such line (`N` is its line number) "
             "and nothing else is evaluated.")
    L.append("")
    L.append("## Formulas")
    L.append("")
    L.append("Tokens (blanks between tokens are ignored): " +
             "**integers** (ASCII digits); **references** (a run of ASCII letters followed by one or more digits, e.g. `B7`, `K12`, `a1`); " +
             ("**function names** (a run of ASCII letters followed by `(`); " if p["funcs"] else "") +
             "the operators `+ - * / %`" + (" `= <> < <= > >=`" if p["cmp"] else "") + ", parentheses" + (", `,` and `:`" if p["funcs"] else ", and `:`") + ". Anything else is a syntax error.")
    L.append("")
    grammar = ["```"]
    if p["cmp"]:
        grammar.append("formula := sum [ ('=' | '<>' | '<' | '<=' | '>' | '>=') sum ]      (at most one comparison, not chained)")
    else:
        grammar.append("formula := sum")
    grammar += ["sum     := product { ('+' | '-') product }",
                "product := unary { ('*' | '/' | '%') unary }",
                "unary   := '-' unary | atom"]
    if p["funcs"]:
        grammar += ["atom    := INTEGER | REF | RANGE | NAME '(' [ formula { ',' formula } ] ')' | '(' formula ')'", "RANGE   := REF ':' REF"]
    else:
        grammar += ["atom    := INTEGER | REF | '(' formula ')'"]
    grammar.append("```")
    L += grammar
    L.append("")
    L.append("The whole formula must be consumed. Any violation is a **syntax error**, and the value of that cell is `#SYN` (the rest of the sheet is unaffected)."
             + (" Without functions in this engine, a function name is a syntax error too." if not p["funcs"] else "")
             + " " + ("A range `REF:REF` may appear only as a direct argument of " + ", ".join(f"`{names[c]}`" for c in AGG if c in names) + "; anywhere else it is a syntax error "
                      "(this includes arguments of any other function, even an unknown one)." if p["funcs"] else "A `REF:REF` range is not available here; the `:` token makes the formula a syntax error."))
    L.append("")
    L.append("## Values and errors")
    L.append("")
    L.append("Every value is an integer whose absolute value is **at most 9999999**; an integer literal, or a result of `+`, `-`, `*`"
             + (", the aggregate sum and `SNAP`" if p["funcs"] else "") + " that is larger in absolute value, is the error `#NUM` (unary minus never leaves the range). "
             "An integer literal with more than nine digits is also `#NUM`.")
    L.append("")
    L.append("* A **reference** whose text is not a valid cell name (`K1`, `A0`, `A100`, `a1`, `A01`) is `#REF`. A reference to a valid cell that has no line is `0`.")
    L.append("* **Errors propagate**: if an operand (or a function argument) evaluates to an error, the whole operation has that error. Operands are evaluated left to right and "
             "evaluation stops at the first error, so the leftmost failing operand decides which error is reported.")
    divtext = {"trunc": "`/` truncates towards zero and `%` is the matching remainder (it has the sign of the dividend: `-7 / 2 = -3`, `-7 % 2 = -1`)",
               "floor": "`/` rounds towards minus infinity and `%` is the matching remainder (it has the sign of the divisor: `-7 / 2 = -4`, `-7 % 2 = 1`)",
               "exact": "`/` is only allowed when the division is exact; a non-zero remainder gives `#DIV` (`6 / 3 = 2`, `7 / 2` is `#DIV`); `%` is the remainder with the sign of the dividend (`-7 % 2 = -1`)"}[p["div"]]
    L.append(f"* **Division**: {divtext}. Dividing by 0 (with `/` or `%`) is `#DIV`.")
    if p["cmp"]:
        L.append("* A comparison gives `1` when it holds and `0` when it does not.")
    L.append("* **Cycles**: the value of a cell is `#CYC` when computing it needs the value of that same cell, directly or through other cells, following only the references that are actually evaluated "
             "(" + ("an argument of " + f"`{names['IF']}`" + " that is not chosen is not evaluated" if "IF" in names else "every reference in the formula is evaluated") + "). "
             "A cell that merely reads a `#CYC` cell gets `#CYC` through normal error propagation. A self-reference is a cycle.")
    L.append("")
    if p["funcs"]:
        L.append("## Functions")
        L.append("")
        L.append("Function names are upper-case and matched exactly; a name that is not in the table is `#NAME` (when the call is evaluated). A wrong number of arguments is `#ARG`, "
                 "detected **before** any argument is evaluated. Arguments are evaluated left to right.")
        L.append("")
        L.append("| function | meaning |")
        L.append("|---|---|")
        agg_txt = {
            "SUM": "sum of all values (0 if there are no values)",
            "MIN": "smallest value (`#NUM` if there are no values)",
            "MAX": "largest value (`#NUM` if there are no values)",
            "AVG": "sum of the values divided by their number, using the division rule above (`#NUM` if there are no values)",
            "COUNT": "how many values there are",
        }
        for c in AGG:
            L.append(f"| `{names[c]}(a, b, ...)` | {agg_txt[c]} |")
        L.append("")
        L.append("The aggregate functions take **one or more** arguments (no argument: `#ARG`). Each argument is a formula or a range. A formula argument contributes one value. "
                 "A range `X1:Y2` covers the rectangle of cells between the two corners, whichever corner comes first (`B3:A1` is the same as `A1:B3`); it contributes the value of every cell **that has a line**, "
                 "in row order (row by row, columns A to J within a row); cells without a line contribute nothing. If a covered cell has an error value the aggregate fails with that error "
                 "(the first one in that order). A corner that is not a valid cell name makes the range `#REF` (it is checked when the range is evaluated). `#NUM` for an oversized sum is checked on the final sum only.")
        L.append("")
        one = []
        one.append(f"| `{names['ABS']}(x)` | absolute value |")
        if "IF" in names:
            one.append(f"| `{names['IF']}(c, a, b)` | `a` if `c` is not 0, otherwise `b`; only `c` and the chosen branch are evaluated |")
            one.append(f"| `{names['CLAMP']}(x, lo, hi)` | `x` limited to the range `lo..hi` (all three are evaluated first; `lo > hi` is `#ARG`) |")
            one.append(f"| `{names['SNAP']}(x, m)` | `x` rounded to the nearest multiple of `m`, halfway cases towards plus infinity (`m <= 0` is `#ARG`; both arguments are evaluated first) |")
        L.append("| function | meaning |")
        L.append("|---|---|")
        L += one
        L.append("")
    L.append("## Result")
    L.append("")
    L.append("One line `CELL = VALUE` for every cell that has a line (even when its formula is empty or erroneous), in " +
             ("row order: by row number, then by column letter (`A1`, `B1`, `A2`, ...)" if p["order"] == "row" else
              "column order: by column letter, then by row number (`A1`, `A2`, `B1`, ...)") +
             ". `VALUE` is the decimal integer (a leading `-` for negatives, no `+`) or the error text (`#SYN`, `#REF`, `#DIV`, `#NUM`, `#CYC`" +
             (", `#NAME`, `#ARG`" if p["funcs"] else "") + "). Lines are joined with `\\n`, no trailing newline; a sheet without cells gives the empty text. An empty formula is `#SYN`.")
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    for (src,), out in examples:
        L.append("Sheet:")
        L.append("")
        L.append(K.fence(src))
        L.append("Result:")
        L.append("")
        L.append(K.fence(out) if out else "(empty)\n")
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


def make_cases(rng, p, ns):
    names = p["names"]
    sheet = ns["sheet"]
    cases = []
    funcs = p["funcs"]
    N = lambda c: names[c]  # noqa: E731

    def add(*lines, blank=None):
        cases.append(("\n".join(lines),))

    cols = "ABCDEFGHIJ"

    def rname():
        return f"{rng.choice(cols[:5])}{rng.randrange(1, 7)}"

    def rexpr(refs, depth):
        r = rng.random()
        if depth == 0 or r < 0.25:
            if refs and rng.random() < 0.6:
                return rng.choice(refs)
            return str(rng.randrange(0, 60))
        if r < 0.55:
            op = rng.choice("+-*")
            return f"{rexpr(refs, depth - 1)} {op} {rexpr(refs, depth - 1)}"
        if r < 0.65:
            return f"({rexpr(refs, depth - 1)}) {rng.choice('+-*/%')} {rexpr(refs, depth - 1)}"
        if r < 0.72:
            return f"-{rexpr(refs, depth - 1)}"
        if funcs and r < 0.9:
            c = rng.choice([x for x in ("SUM", "MIN", "MAX", "AVG", "COUNT", "ABS") if x in names])
            if c == "ABS":
                return f"{N(c)}({rexpr(refs, depth - 1)})"
            if refs and rng.random() < 0.6:
                a, b = rng.choice(refs), rng.choice(refs)
                return f"{N(c)}({a}:{b}, {rexpr(refs, depth - 1)})" if rng.random() < 0.4 else f"{N(c)}({a}:{b})"
            return f"{N(c)}({rexpr(refs, depth - 1)}, {rexpr(refs, depth - 1)})"
        if p["cmp"] and r < 0.96:
            return f"{N('IF')}({rexpr(refs, depth - 1)} {rng.choice(['<', '>', '=', '<>', '<=', '>='])} {rexpr(refs, depth - 1)}, {rexpr(refs, depth - 1)}, {rexpr(refs, depth - 1)})"
        return f"({rexpr(refs, depth - 1)})"

    def rsheet(n, cyc=False, noisy=True):
        pool = []
        cells = []
        used = set()
        while len(cells) < n:
            c = rname()
            if c not in used:
                used.add(c)
                cells.append(c)
        lines = []
        for k, c in enumerate(cells):
            if k < 2 or rng.random() < 0.3:
                f = str(rng.randrange(0, 100))
            else:
                f = rexpr(pool, rng.choice([1, 2, 2, 3]))
            sp = rng.choice(["", " "]) if noisy else " "
            lines.append(f"{c}{sp}={sp}{f}" if noisy else f"{c} = {f}")
            pool.append(c)
        if cyc:
            a, b = rng.sample(cells, 2)
            lines.append(f"{a} = {b} + 1")
        rng.shuffle(lines)
        return lines

    # examples
    add("A1 = 12", "A2 = 30", "B1 = A1 + A2 * 2")
    if funcs:
        add("A1 = 4", "A2 = 9", "A3 = 2", f"B1 = {N('SUM')}(A1:A3)", f"B2 = {N('MAX')}(A1:A3) - {N('MIN')}(A1:A3)")
    else:
        add("A1 = 7", "B1 = A1 * (A2 + 3)", "# A2 is empty", "C1 = B1 / 4")
    add("A1 = 2", "A2 = A1 + B1", "B1 = A2")
    nex = len(cases)
    for _ in range(10):
        add(*rsheet(rng.randrange(4, 10)))
    for _ in range(4):
        add(*rsheet(rng.randrange(5, 12), cyc=True))
    for _ in range(3):
        add(*rsheet(rng.randrange(10, 18), noisy=False))
    # arithmetic details
    for f in ["7 / 2", "-7 / 2", "7 / -2", "-7 / -2", "7 % 2", "-7 % 2", "7 % -2", "-7 % -2", "6 / 3", "-6 / 3", "6 % 3", "0 / 5", "0 % 5", "5 / 0", "5 % 0", "0 / 0",
              "2 + 3 * 4", "(2 + 3) * 4", "10 - 4 - 3", "100 / 5 / 4", "-2 * -3", "- - 4", "-(3 - 5)", "2 * (3 + (4 - 1)) % 5", "1 - -1", "8 / 2 * 3", "9 % 4 * 2", "-3 % 5", "3 % -5", "-1 / 2", "1 / -2",
              "9999999", "10000000", "9999999 + 1", "-9999999 - 1", "3162 * 3162", "3163 * 3163", "-3163 * 3163", "99999999999", "0", "007", "-0", "5000000 + 5000000", "5000000 * 2 - 10000000"]:
        add(f"A1 = {f}")
    # many small cell formats
    add("A1=1", "  A2  =  2  ", "\tA3\t=\t3\t", "B1= A1+A2+A3", "B2 =A1*A2*A3")
    add("A1 = 1", "A1 = 2", "B1 = A1")
    add("A1 = 5", "A1 =", "B1 = A1")
    add("A1 =", "B1 = 3")
    add("# comment", "", "A1 = 3", "   # indented comment", "B2 = A1")
    add("A1 = 1 = 2" if p["cmp"] else "A1 = 1 ( 2")
    add("")
    add("# only comments", "  ", "\t")
    add("J99 = 1", "A1 = J99 + 1", "J1 = A1", "A99 = 7")
    add("B2 = 1", "A3 = 2", "C1 = 3", "A1 = 4")
    add("B2 = 1", "A3 = 2", "C1 = 3", "A1 = 4", "A2 = 5", "B1 = 6")
    # sheet-level errors
    for bad in ["K1 = 1", "A0 = 1", "A100 = 1", "a1 = 1", "A01 = 1", "A = 1", "1A = 1", "AA1 = 1", "A1", "= 5", "A1 5", "A-1 = 2", "A1: = 2", " = ", "A1 : B1 = 1", "A1B1 = 3", "#A1 = 2"]:
        add("A1 = 1", bad, "B1 = 2") if not bad.startswith("#") else add("A1 = 1", bad)
    add("bogus", "A1 = 1")
    add("A1 = 1", "", "# c", "oops")
    # references
    for f in ["K1", "A0", "A100", "a1", "A01", "B", "AA1", "J99", "Z9", "A1", "B2 + 1", "C3 * 2", "1 + K1", "K1 + 1 / 0", "1 / 0 + K1", "ZZ", "A1B", "12A", "A1 A2", "A1 +", "+ A1", "(A1", "A1)", "()", "1 2", "A1 2", "A1 * * 2", "1 +* 2", "$A1", "A$1", "A1.5", "1.5", "A1;", "A1 & A2", "A1 | 1", "!1", "~1", "1_0"]:
        add("A1 = 3", f"B1 = {f}")
    # cycles
    add("A1 = A1")
    add("A1 = A1 + 1")
    add("A1 = B1", "B1 = A1")
    add("A1 = B1", "B1 = C1", "C1 = A1", "D1 = C1 + 1", "E1 = 5", "F1 = E1 + D1")
    add("A1 = 1", "B1 = A1 + C1", "C1 = B1 + 1", "D1 = A1 + 1")
    add("A1 = B1 + 1", "B1 = 2", "C1 = A1 * B1")
    add("A1 = 1 / 0", "B1 = A1", "C1 = B1")
    add("A1 = B1 / 0", "B1 = A1")
    add("A1 = B1 + C1", "B1 = 1 / 0", "C1 = C1")
    add("A1 = B1 + C1", "B1 = C1", "C1 = K1")
    add("A1 = 1 / 0 + B1", "B1 = A1")
    add("A1 = B1 + 1 / 0", "B1 = A1")
    add("A1 = 99999999999 + B1", "B1 = A1")
    add("A1 = K1 + B1", "B1 = A1")
    add("A1 = B1 + K1", "B1 = A1")
    add("A1 = -B1", "B1 = -A1")
    add("A1 = (B1)", "B1 = (A1)")
    add("A1 = 1", "A2 = A1 + A3", "A3 = A2 + A1", "A4 = A1 + A1")
    if funcs:
        # aggregates
        S, MI, MA, AV, CO, AB = N("SUM"), N("MIN"), N("MAX"), N("AVG"), N("COUNT"), N("ABS")
        add("A1 = 3", "A3 = 5", "B1 = 7", "C1 = 1", f"D1 = {S}(A1:A3)", f"D2 = {CO}(A1:C3)", f"D3 = {MI}(A1:C3)", f"D4 = {MA}(A1:C3)", f"D5 = {AV}(A1:C3)")
        add("A1 = 3", "A2 = 4", f"B1 = {S}(A2:A1)", f"B2 = {S}(A1:A1)", f"B3 = {S}(A1:B2)", f"B4 = {S}(B2:A1)", f"B5 = {CO}(B1:B5)")
        add(f"A1 = {S}(B1:B3)", f"A2 = {CO}(B1:B3)", f"A3 = {MI}(B1:B3)", f"A4 = {MA}(B1:B3)", f"A5 = {AV}(B1:B3)", f"A6 = {S}(5)", f"A7 = {MI}(3, 4, 1, 9)", f"A8 = {AV}(1, 2)", f"A9 = {AV}(7)")
        add(f"A1 = {S}()", f"A2 = {MI}()", f"A3 = {CO}()", f"A4 = {AV}()", f"A5 = {MA}()")
        add("A1 = 5", f"B1 = {S}(A1, A1:A2, A1)", f"B2 = {CO}(A1, A1:A2, A1)", f"B3 = {S}(1, 2, 3, 4)", f"B4 = {CO}(1, 2, 3, 4)")
        add("A1 = 1 / 0", "A2 = 5", f"B1 = {S}(A1:A2)", f"B2 = {CO}(A2:A3)", f"B3 = {S}(A2:A3, A1)", f"B4 = {MI}(A2, A1)")
        add(f"A1 = {S}(A1:A3)", "A2 = 1", "A3 = 2", f"B1 = {S}(A2:A3)")
        add(f"A1 = {S}(B1:B2)", "B1 = 4", f"B2 = {S}(A1:A1)")
        add("A1 = 7", f"B1 = {S}(A1:K1)", f"B2 = {S}(K1:A1)", f"B3 = {S}(A1:A100)", f"B4 = {S}(a1:A2)", f"B5 = {S}(A1:)", f"B6 = {S}(:A1)", f"B7 = {S}(A1:A2:A3)", f"B8 = {S}(A1:5)")
        add("A1 = 7", f"B1 = A1:A2", f"B2 = {S}(A1:A2) + A1:A2", f"B3 = ({S}(A1:A2))", f"B4 = {S}((A1:A2))", f"B5 = -A1:A2", f"B6 = {AB}(A1:A2)", f"B7 = FOO(A1:A2)", f"B8 = {S}(A1:A2,)")
        add("A1 = 7", f"B1 = FOO(1)", f"B2 = {S.lower()}(1)", f"B3 = {S}(1", f"B4 = {S} (1)", f"B5 = {S}(1))", f"B6 = {S}", f"B7 = {S}()()", f"B8 = FOO(1) / 0", f"B9 = 1 / 0 + FOO(1)")
        add(f"A1 = {AB}(-5)", f"A2 = {AB}(0)", f"A3 = {AB}(7)", f"A4 = {AB}()", f"A5 = {AB}(1, 2)", f"A6 = {AB}(1 / 0)", f"A7 = {AB}(-9999999)", f"A8 = {AB}(3 - 10)")
        add(f"A1 = {S}(9999999, 1)", f"A2 = {S}(9999999, -1)", f"A3 = {S}(5000000, 5000000, -5000000)", f"A4 = {AV}(9999999, 9999999)", f"A5 = {S}(99999999999)", f"A6 = {CO}(99999999999)")
        add("A1 = 1", "A2 = 2", "A3 = 3", f"B1 = {AV}(A1:A3)", f"B2 = {AV}(A1:A2)", f"B3 = {AV}(1, 2)", f"B4 = {AV}(-1, -2)", f"B5 = {AV}(-1, -2, -2)", f"B6 = {AV}(5, 5)", f"B7 = {AV}(0, 0, 1)", f"B8 = {AV}(-7, 2)")
        add("A1 = 4", "B2 = A1:B1", "C1 = 3", f"D1 = {S}(A1:C2)")
        add("A1 = 4", f"B1 = {S}(A1, K1)", f"B2 = {S}(K1, 1 / 0)", f"B3 = {S}(1 / 0, K1)", f"B4 = {S}(A1:A2, K1)", f"B5 = {CO}(K1:A1, 1 / 0)")
        add(*[f"A{i} = {i * 3 % 7}" for i in range(1, 15)], f"B1 = {S}(A1:A14)", f"B2 = {MA}(A1:A14)", f"B3 = {MI}(A1:A14)", f"B4 = {AV}(A1:A14)", f"B5 = {CO}(A1:A14)")
    if p["cmp"]:
        IF, CL, SN = N("IF"), N("CLAMP"), N("SNAP")
        add("A1 = 1 < 2", "A2 = 2 < 1", "A3 = 2 = 2", "A4 = 2 <> 2", "A5 = 3 >= 3", "A6 = 3 <= 2", "A7 = -1 > -2", "A8 = 2 + 2 = 4", "A9 = 1 + 1 < 1 + 2")
        add("A1 = 1 < 2 < 3", "A2 = 1 = 1 = 1", "A3 = (1 < 2) < 3", "A4 = 1 < (2 < 3)", "A5 = 1 <", "A6 = < 1", "A7 = 1 == 1", "A8 = 1 => 1", "A9 = 1 >< 1", "B1 = 1 <> <> 1")
        add("A1 = 1 / 0 = 1", "A2 = K1 < 1", "A3 = 1 < K1", "A4 = 1 / 0 < K1", "A5 = K1 < 1 / 0")
        add(f"A1 = {IF}(1, 10, 20)", f"A2 = {IF}(0, 10, 20)", f"A3 = {IF}(-1, 10, 20)", f"A4 = {IF}(2 > 1, 10, 20)", f"A5 = {IF}(2 < 1, 10, 20)", f"A6 = {IF}(1, 10)", f"A7 = {IF}(1, 10, 20, 30)", f"A8 = {IF}()")
        add(f"A1 = {IF}(1, 5, 1 / 0)", f"A2 = {IF}(0, 1 / 0, 6)", f"A3 = {IF}(1, 1 / 0, 5)", f"A4 = {IF}(0, 5, 1 / 0)", f"A5 = {IF}(1 / 0, 1, 2)", f"A6 = {IF}(1, K1, 2)", f"A7 = {IF}(0, K1, 2)", f"A8 = {IF}(0, FOO(1), 2)", f"A9 = {IF}(1, FOO(1), 2)")
        add(f"A1 = {IF}(1, 5, B1)", "B1 = A1", f"C1 = {IF}(0, 5, C1)", f"D1 = {IF}(1, D1, 5)", f"E1 = {IF}(F1, 1, 2)", f"F1 = {IF}(E1, 1, 2)")
        add(f"A1 = {IF}(B1, A2, A3)", "B1 = 1", "A2 = 10", f"A3 = {IF}(1, A1, 0)", f"C1 = {IF}(B1, 5, C1)", f"C2 = C1 + 1")
        add(f"A1 = {IF}(B1, 1, C1)", "B1 = 1", "C1 = D1", "D1 = C1", f"E1 = {IF}(B1 - 1, C1, 3)", f"F1 = {IF}(B1 - 1, 3, C1)")
        add(f"A1 = {IF}(0, A1, 3)", f"A2 = {IF}(1, 3, A2)", f"A3 = {IF}(1, A3, 3)", "A4 = A1 + A2", f"A5 = {IF}(A4 > 5, A5, 0)", f"A6 = {IF}(A4 < 5, A6, 0)")
        add(f"A1 = {CL}(5, 1, 10)", f"A2 = {CL}(-5, 1, 10)", f"A3 = {CL}(50, 1, 10)", f"A4 = {CL}(5, 5, 5)", f"A5 = {CL}(5, 10, 1)", f"A6 = {CL}(1 / 0, 10, 1)", f"A7 = {CL}(5, 10, 1 / 0)",
            f"A8 = {CL}(5, 1)", f"A9 = {CL}(5, K1, 1 / 0)", f"B1 = {CL}(-9999999, -9999999, 9999999)")
        add(f"A1 = {SN}(14, 5)", f"A2 = {SN}(15, 5)", f"A3 = {SN}(12, 5)", f"A4 = {SN}(-12, 5)", f"A5 = {SN}(-13, 5)", f"A6 = {SN}(-15, 5)", f"A7 = {SN}(7, 1)", f"A8 = {SN}(7, 2)", f"A9 = {SN}(6, 4)",
            f"B1 = {SN}(5, 0)", f"B2 = {SN}(5, -2)", f"B3 = {SN}(5)", f"B4 = {SN}(1 / 0, 0)", f"B5 = {SN}(5, 1 / 0)", f"B6 = {SN}(9999999, 10)", f"B7 = {SN}(-9999999, 10)", f"B8 = {SN}(0, 3)", f"B9 = {SN}(1, 3)", f"C1 = {SN}(2, 3)", f"C2 = {SN}(-1, 3)", f"C3 = {SN}(-2, 3)")
        add("A1 = 7", f"B1 = {IF}(A1 > 5, {SN}(A1, 4), {CL}(A1, 0, 3))", f"B2 = {IF}(A1 > 9, {SN}(A1, 4), {CL}(A1, 0, 3))", f"B3 = {S}({IF}(1, A1, 0), {IF}(0, 1, A1:A1))")
        add("A1 = 3", f"B1 = {IF}(1, A1:A2, 0)", f"B2 = {IF}(A1:A2, 1, 0)", f"B3 = {CL}(A1:A2, 0, 1)")
        for _ in range(6):
            add(*rsheet(rng.randrange(8, 16), cyc=rng.random() < 0.5))
    for _ in range(5):
        add(*rsheet(rng.randrange(12, 24), cyc=rng.random() < 0.4, noisy=False))
    # long dependency chain
    add("A1 = 1", *[f"A{i} = A{i - 1} + 1" for i in range(2, 40)])
    add("A1 = A2", *[f"A{i} = A{i + 1}" for i in range(2, 30)], "A30 = A1")
    out, seen = [], set()
    for c in cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex


def prompt(rng, p, api, lang):
    where = api.where(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    feats = ["references", "cycle detection"]
    if p["funcs"]:
        feats.append("ranges and aggregate functions")
    if p["cmp"]:
        feats.append("comparisons and a lazy conditional")
    ft = ", ".join(feats)
    opts = [
        f"The harbour office wants a small spreadsheet engine. Implement `{fn}` in {ln} ({where}) so that it evaluates a sheet text and prints the value of each cell. Everything - cell syntax, operators, error codes, ordering and the division rule - is in README.md. Needed: {ft}. {K.closer(rng)}",
        f"Task: build the sheet evaluator from README.md ({ln}, `{fn}`, {where}). It has to handle {ft}. The README is the contract; pay attention to which error wins when several operands fail and to what counts as a cycle.",
        f"spreadsheet-in-a-function, {ln}. one entry point `{fn}` in {where}. spec: README.md. features this time: {ft}. error values like #CYC and #DIV have exact semantics there. {K.closer(rng)}",
        f"I need `{fn}` ({ln}): input is a sheet (`A1 = ...` lines), output is `CELL = VALUE` lines. README.md describes the whole language, including {ft}. File: {where}. Hidden checks cover odd corners such as reversed ranges and empty cells, so follow the spec literally.",
    ]
    return rng.choice(opts).strip()


@family("greenfield-sheetcalc", category="greenfield", lang="mixed", kind="greenfield", n=10,
        summary="spreadsheet engine: integer formulas, refs, ranges, aggregates, lazy IF, error propagation, cycle detection; division rule and function names vary")
def gen(rng, n):
    levels = [3, 3, 4, 4, 4, 5, 5, 5, 3, 4]
    diffs = [3, 3, 4, 4, 4, 5, 5, 5, 3, 4]
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level, i)
        api = K.Api(mod="sheetcalc", fn="sheet", args=["source"], arg_docs=["the sheet text"], ret_doc="the evaluated sheet as text", doc="spreadsheet engine")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["sheet"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=diffs[i % len(diffs)], slug=f"{i + 1:02d}-{lang}-{p['div']}-{p['order']}-l{level}",
            oracle=(None if lang == "python" else ns["sheet"]), tags=["parser", "evaluator", "cycles"],
            notes={"level": level, "div": p["div"], "order": p["order"]},
        )
