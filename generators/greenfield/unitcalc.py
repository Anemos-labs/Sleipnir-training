"""Unit-aware calculator over an invented system of units: exact rational arithmetic, dimension checking, rounded output."""
from __future__ import annotations

from fractions import Fraction

from fx import family

from generators.greenfield import _kit as K

SYL = ["ba", "ke", "lo", "mi", "ra", "su", "ti", "vo", "ne", "zu", "da", "fe", "go", "hu", "pa", "ro", "sa", "wi", "yo", "ku"]
DIM_NAMES = ["reach", "span", "heft", "glow", "chill", "tone"]
LANG_PLAN = ["python", "rust", "go", "javascript", "rust", "go", "python", "javascript", "rust", "go", "javascript", "python"]


def uname(rng, used):
    while True:
        n = "".join(rng.choice(SYL) for _ in range(rng.choice([2, 2, 3])))
        if n not in used:
            used.add(n)
            return n


def params(rng, level):
    nd = 2 if level <= 2 else 3
    used = set()
    dims = rng.sample(DIM_NAMES, nd)
    units = []  # (name, num, den, dims tuple)
    bases = []
    for i in range(nd):
        n = uname(rng, used)
        v = tuple(1 if j == i else 0 for j in range(nd))
        units.append((n, 1, 1, v))
        bases.append((n, v))
        extra = rng.choice([1, 2, 2]) if level <= 2 else rng.choice([2, 2, 3])
        for _ in range(extra):
            f = rng.choice([(12, 1), (5, 1), (3, 2), (1, 4), (40, 1), (100, 1), (1, 16), (7, 1), (60, 1), (9, 4), (1, 3), (25, 2)])
            units.append((uname(rng, used), f[0], f[1], v))
    nder = 0 if level <= 2 else (1 if level == 3 else rng.choice([2, 3]))
    if level >= 5:
        nder += 2
    for _ in range(nder):
        for _ in range(50):
            a, b = rng.sample(range(nd), 2) if nd > 1 else (0, 0)
            sgn = rng.choice([1, -1, 1])
            v = [0] * nd
            v[a] += 1
            v[b] += (-1 if sgn == 1 else 1) if a != b else 1
            if rng.random() < 0.3:
                v[a] += 1
            v = tuple(v)
            if all(x == 0 for x in v) or any(u[3] == v for u in units):
                continue
            f = rng.choice([(1, 1), (2, 1), (3, 2), (5, 4), (7, 1), (1, 5), (11, 10), (9, 1)])
            units.append((uname(rng, used), f[0], f[1], v))
            break
    prefixes = {}
    if level >= 5:
        for letter, f in rng.sample([("k", (1000, 1)), ("m", (1, 1000)), ("h", (100, 1)), ("c", (1, 100)), ("d", (1, 10)), ("q", (1, 4)), ("w", (12, 1))], rng.choice([2, 3])):
            prefixes[letter] = f
        # a table unit whose name looks like prefix + another unit: the exact name must win
        letter = sorted(prefixes)[0]
        host = rng.choice(units)
        shadow = letter + host[0]
        if shadow not in used:
            used.add(shadow)
            units.append((shadow, 7, 3, host[3]))
    units.sort(key=lambda u: u[0])
    return {"level": level, "dims": dims, "units": units, "digits": rng.choice([2, 3, 4]) if level < 5 else rng.choice([3, 4]),
            "pow": level >= 3, "nd": nd, "composite": level >= 4, "prefixes": prefixes}


PY = r'''
from fractions import Fraction

ND = @ND@
UNITS = @UNITS_PY@
DIGITS = @DIGITS@
HAS_POW = @HAS_POW@
COMPOSITE = @COMPOSITE@
PREFIXES = @PREFIXES_PY@
ZERO = (0,) * ND


class CalcError(Exception):
    pass


def tokenize(s):
    toks = []
    i = 0
    dg = "0123456789"
    while i < len(s):
        c = s[i]
        if c in " \t":
            i += 1
        elif c in dg:
            j = i
            while j < len(s) and s[j] in dg:
                j += 1
            if j < len(s) and s[j] == ".":
                k = j + 1
                if k >= len(s) or s[k] not in dg:
                    raise CalcError("syntax")
                while k < len(s) and s[k] in dg:
                    k += 1
                j = k
            toks.append(("num", s[i:j]))
            i = j
        elif "a" <= c <= "z":
            j = i
            while j < len(s) and "a" <= s[j] <= "z":
                j += 1
            toks.append(("id", s[i:j]))
            i = j
        elif c in "+-*/()" or (c == "^" and HAS_POW):
            toks.append((c, c))
            i += 1
        else:
            raise CalcError("syntax")
    return toks


class Parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self):
        return self.t[self.i][0] if self.i < len(self.t) else None

    def take(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expr(self):
        left = self.term()
        while self.peek() in ("+", "-"):
            op = self.take()[0]
            left = (op, left, self.term())
        return left

    def term(self):
        left = self.unary()
        while self.peek() in ("*", "/"):
            op = self.take()[0]
            left = (op, left, self.unary())
        return left

    def unary(self):
        if self.peek() == "-":
            self.take()
            return ("neg", self.unary())
        return self.power()

    def exp(self):
        if HAS_POW and self.peek() == "^":
            self.take()
            sign = 1
            if self.peek() == "-":
                self.take()
                sign = -1
            if self.peek() != "num":
                raise CalcError("syntax")
            txt = self.take()[1]
            if len(txt) != 1:
                raise CalcError("syntax")
            return sign * int(txt)
        return None

    def power(self):
        k = self.peek()
        if k == "num":
            txt = self.take()[1]
            if "." in txt:
                a, b = txt.split(".")
                val = Fraction(int(a + b), 10 ** len(b))
            else:
                val = Fraction(int(txt))
            if self.peek() == "id":
                name = self.take()[1]
                return ("qty", val, name, self.exp())
            e = self.exp()
            return ("npow", val, e) if e is not None else ("num", val)
        if k == "id":
            name = self.take()[1]
            return ("unit", name, self.exp())
        if k == "(":
            self.take()
            inner = self.expr()
            if self.peek() != ")":
                raise CalcError("syntax")
            self.take()
            e = self.exp()
            return ("pow", inner, e) if e is not None else inner
        raise CalcError("syntax")


def parse(s):
    p = Parser(tokenize(s))
    tree = p.expr()
    if p.i != len(p.t):
        raise CalcError("syntax")
    return tree


def powq(v, e):
    r, d = v
    if e < 0:
        if r == 0:
            raise CalcError("divide by zero")
        return (Fraction(1) / r) ** (-e), tuple(x * e for x in d)
    return r ** e, tuple(x * e for x in d)


def unit(name):
    for n, num, den, dims in UNITS:
        if n == name:
            return Fraction(num, den), dims
    if len(name) > 1 and name[0] in PREFIXES:
        for n, num, den, dims in UNITS:
            if n == name[1:]:
                return Fraction(num, den) * PREFIXES[name[0]], dims
    raise CalcError("unknown unit " + name)


def target_unit(t):
    """(size, dims) of a target: one unit, or with COMPOSITE a product/quotient of units with exponents."""
    if not COMPOSITE:
        return unit(t)
    try:
        toks = tokenize(t)
        p = Parser(toks)
        items = []
        sign = 1
        while True:
            if p.peek() != "id":
                raise CalcError("target")
            name = p.take()[1]
            e = p.exp()
            items.append((sign, name, 1 if e is None else e))
            k = p.peek()
            if k == "*":
                p.take()
                sign = 1
            elif k == "/":
                p.take()
                sign = -1
            else:
                break
        if p.i != len(toks):
            raise CalcError("target")
    except CalcError:
        raise CalcError("target")
    size = Fraction(1)
    dims = ZERO
    for sign, name, e in items:
        f, d = powq(unit(name), sign * e)
        size = size * f
        dims = tuple(x + y for x, y in zip(dims, d))
    return size, dims


def ev(t):
    k = t[0]
    if k == "num":
        return t[1], ZERO
    if k == "npow":
        return powq((t[1], ZERO), t[2])
    if k == "unit":
        f, d = unit(t[1])
        return powq((f, d), t[2]) if t[2] is not None else (f, d)
    if k == "qty":
        f, d = unit(t[2])
        f, d = powq((f, d), t[3]) if t[3] is not None else (f, d)
        return t[1] * f, d
    if k == "pow":
        return powq(ev(t[1]), t[2])
    if k == "neg":
        r, d = ev(t[1])
        return -r, d
    a = ev(t[1])
    b = ev(t[2])
    if k in "+-":
        if a[1] != b[1]:
            raise CalcError("dimension")
        return (a[0] + b[0] if k == "+" else a[0] - b[0]), a[1]
    if k == "*":
        return a[0] * b[0], tuple(x + y for x, y in zip(a[1], b[1]))
    if b[0] == 0:
        raise CalcError("divide by zero")
    return a[0] / b[0], tuple(x - y for x, y in zip(a[1], b[1]))


def fmt(q):
    neg = q < 0
    q = abs(q)
    scale = 10 ** DIGITS
    scaled = (2 * q.numerator * scale + q.denominator) // (2 * q.denominator)
    ip, fp = divmod(scaled, scale)
    s = str(ip)
    if fp:
        s += "." + str(fp).rjust(DIGITS, "0").rstrip("0")
    return ("-" + s) if (neg and scaled != 0) else s


def evaluate(expr):
    return ev(parse(expr))


def calc(expr, target):
    try:
        r, d = evaluate(expr)
        if target == "-":
            if d != ZERO:
                raise CalcError("dimension")
            return fmt(r)
        f, td = target_unit(target)
        if td != d:
            raise CalcError("dimension")
        return fmt(r / f) + " " + target
    except CalcError as e:
        return "error: " + str(e)
'''

JS = r'''
'use strict';

const ND = @ND@;
const UNITS = @UNITS_JS@;
const DIGITS = @DIGITS@;
const HAS_POW = @HAS_POW@;
const COMPOSITE = @COMPOSITE@;
const PREFIXES = @PREFIXES_JS@;
const ZERO = new Array(ND).fill(0);

class CalcError extends Error {}
const fail = (m) => { throw new CalcError(m); };

function gcd(a, b) { a = a < 0n ? -a : a; b = b < 0n ? -b : b; while (b) { [a, b] = [b, a % b]; } return a; }
function mk(n, d) { if (d < 0n) { n = -n; d = -d; } const g = gcd(n, d) || 1n; return [n / g, d / g]; }
const qadd = (a, b) => mk(a[0] * b[1] + b[0] * a[1], a[1] * b[1]);
const qsub = (a, b) => mk(a[0] * b[1] - b[0] * a[1], a[1] * b[1]);
const qmul = (a, b) => mk(a[0] * b[0], a[1] * b[1]);
const qdiv = (a, b) => mk(a[0] * b[1], a[1] * b[0]);

function tokenize(s) {
  const toks = [];
  let i = 0;
  const dg = (c) => c !== undefined && c >= '0' && c <= '9';
  while (i < s.length) {
    const c = s[i];
    if (c === ' ' || c === '\t') { i++; }
    else if (dg(c)) {
      let j = i;
      while (dg(s[j])) j++;
      if (s[j] === '.') {
        let k = j + 1;
        if (!dg(s[k])) fail('syntax');
        while (dg(s[k])) k++;
        j = k;
      }
      toks.push(['num', s.slice(i, j)]);
      i = j;
    } else if (c >= 'a' && c <= 'z') {
      let j = i;
      while (s[j] !== undefined && s[j] >= 'a' && s[j] <= 'z') j++;
      toks.push(['id', s.slice(i, j)]);
      i = j;
    } else if ('+-*/()'.includes(c) || (c === '^' && HAS_POW)) { toks.push([c, c]); i++; }
    else fail('syntax');
  }
  return toks;
}

function parse(s) {
  const t = tokenize(s);
  let i = 0;
  const peek = () => (i < t.length ? t[i][0] : null);
  const take = () => t[i++];
  function exp() {
    if (HAS_POW && peek() === '^') {
      take();
      let sign = 1;
      if (peek() === '-') { take(); sign = -1; }
      if (peek() !== 'num') fail('syntax');
      const txt = take()[1];
      if (txt.length !== 1) fail('syntax');
      return sign * Number(txt);
    }
    return null;
  }
  function power() {
    const k = peek();
    if (k === 'num') {
      const txt = take()[1];
      let val;
      if (txt.includes('.')) { const [a, b] = txt.split('.'); val = mk(BigInt(a + b), 10n ** BigInt(b.length)); }
      else val = [BigInt(txt), 1n];
      if (peek() === 'id') { const name = take()[1]; return ['qty', val, name, exp()]; }
      const e = exp();
      return e !== null ? ['npow', val, e] : ['num', val];
    }
    if (k === 'id') { const name = take()[1]; return ['unit', name, exp()]; }
    if (k === '(') {
      take();
      const inner = expr();
      if (peek() !== ')') fail('syntax');
      take();
      const e = exp();
      return e !== null ? ['pow', inner, e] : inner;
    }
    return fail('syntax');
  }
  function unary() {
    if (peek() === '-') { take(); return ['neg', unary()]; }
    return power();
  }
  function term() {
    let left = unary();
    while (peek() === '*' || peek() === '/') { const op = take()[0]; left = [op, left, unary()]; }
    return left;
  }
  function expr() {
    let left = term();
    while (peek() === '+' || peek() === '-') { const op = take()[0]; left = [op, left, term()]; }
    return left;
  }
  const tree = expr();
  if (i !== t.length) fail('syntax');
  return tree;
}

function powq(v, e) {
  let [r, d] = v;
  const nd = d.map((x) => x * e);
  let base = r;
  if (e < 0) {
    if (r[0] === 0n) fail('divide by zero');
    base = mk(r[1], r[0]);
    e = -e;
  }
  let out = [1n, 1n];
  for (let k = 0; k < e; k++) out = qmul(out, base);
  return [out, nd];
}

function unit(name) {
  for (const [n, num, den, dims] of UNITS) if (n === name) return [mk(BigInt(num), BigInt(den)), dims];
  if (name.length > 1 && Object.prototype.hasOwnProperty.call(PREFIXES, name[0])) {
    for (const [n, num, den, dims] of UNITS) {
      if (n === name.slice(1)) {
        const [pn, pd] = PREFIXES[name[0]];
        return [mk(BigInt(num) * BigInt(pn), BigInt(den) * BigInt(pd)), dims];
      }
    }
  }
  return fail('unknown unit ' + name);
}

function targetUnit(t) {
  if (!COMPOSITE) return unit(t);
  let toks;
  try { toks = tokenize(t); } catch (e) { if (e instanceof CalcError) fail('target'); throw e; }
  let i = 0;
  const items = [];
  let sign = 1;
  for (;;) {
    if (!(i < toks.length && toks[i][0] === 'id')) fail('target');
    const name = toks[i++][1];
    let e = 1;
    if (i < toks.length && toks[i][0] === '^') {
      i++;
      let sg = 1;
      if (i < toks.length && toks[i][0] === '-') { i++; sg = -1; }
      if (!(i < toks.length && toks[i][0] === 'num' && toks[i][1].length === 1)) fail('target');
      e = sg * Number(toks[i++][1]);
    }
    items.push([sign, name, e]);
    if (i < toks.length && toks[i][0] === '*') { i++; sign = 1; }
    else if (i < toks.length && toks[i][0] === '/') { i++; sign = -1; }
    else break;
  }
  if (i !== toks.length) fail('target');
  let size = [1n, 1n];
  let dims = ZERO;
  for (const [sg, name, e] of items) {
    const [f, d] = powq(unit(name), sg * e);
    size = qmul(size, f);
    dims = dims.map((x, k) => x + d[k]);
  }
  return [size, dims];
}

const sameDims = (a, b) => a.every((x, i) => x === b[i]);

function ev(t) {
  const k = t[0];
  if (k === 'num') return [t[1], ZERO];
  if (k === 'npow') return powq([t[1], ZERO], t[2]);
  if (k === 'unit') { const u = unit(t[1]); return t[2] !== null ? powq(u, t[2]) : u; }
  if (k === 'qty') {
    let u = unit(t[2]);
    if (t[3] !== null) u = powq(u, t[3]);
    return [qmul(t[1], u[0]), u[1]];
  }
  if (k === 'pow') return powq(ev(t[1]), t[2]);
  if (k === 'neg') { const a = ev(t[1]); return [[-a[0][0], a[0][1]], a[1]]; }
  const a = ev(t[1]);
  const b = ev(t[2]);
  if (k === '+' || k === '-') {
    if (!sameDims(a[1], b[1])) fail('dimension');
    return [k === '+' ? qadd(a[0], b[0]) : qsub(a[0], b[0]), a[1]];
  }
  if (k === '*') return [qmul(a[0], b[0]), a[1].map((x, i) => x + b[1][i])];
  if (b[0][0] === 0n) fail('divide by zero');
  return [qdiv(a[0], b[0]), a[1].map((x, i) => x - b[1][i])];
}

function fmt(q) {
  const neg = q[0] < 0n;
  const n = neg ? -q[0] : q[0];
  const d = q[1];
  const scale = 10n ** BigInt(DIGITS);
  const scaled = (2n * n * scale + d) / (2n * d);
  const ip = scaled / scale;
  const fp = scaled % scale;
  let s = ip.toString();
  if (fp !== 0n) s += '.' + fp.toString().padStart(DIGITS, '0').replace(/0+$/, '');
  return neg && scaled !== 0n ? '-' + s : s;
}

function calc(expr, target) {
  try {
    const [r, d] = ev(parse(expr));
    if (target === '-') {
      if (!sameDims(d, ZERO)) fail('dimension');
      return fmt(r);
    }
    const [f, td] = targetUnit(target);
    if (!sameDims(td, d)) fail('dimension');
    return fmt(qdiv(r, f)) + ' ' + target;
  } catch (e) {
    if (e instanceof CalcError) return 'error: ' + e.message;
    throw e;
  }
}

module.exports = { calc };
'''

GO = r'''
package unitcalc

import (
	"math/big"
	"strconv"
	"strings"
)

const (
	nd        = @ND@
	digits    = @DIGITS@
	hasPow    = @HAS_POW@
	composite = @COMPOSITE@
)

var prefixes = @PREFIXES_GO@

type unitDef struct {
	name     string
	num, den int64
	dims     [nd]int
}

var units = @UNITS_GO@

type calcErr struct{ msg string }

func fail(m string) { panic(calcErr{m}) }

type value struct {
	r    *big.Rat
	dims [nd]int
}

type tok struct{ kind, text string }

func isDig(c byte) bool { return c >= '0' && c <= '9' }

func tokenize(s string) []tok {
	var out []tok
	i := 0
	for i < len(s) {
		c := s[i]
		switch {
		case c == ' ' || c == '\t':
			i++
		case isDig(c):
			j := i
			for j < len(s) && isDig(s[j]) {
				j++
			}
			if j < len(s) && s[j] == '.' {
				k := j + 1
				if k >= len(s) || !isDig(s[k]) {
					fail("syntax")
				}
				for k < len(s) && isDig(s[k]) {
					k++
				}
				j = k
			}
			out = append(out, tok{"num", s[i:j]})
			i = j
		case c >= 'a' && c <= 'z':
			j := i
			for j < len(s) && s[j] >= 'a' && s[j] <= 'z' {
				j++
			}
			out = append(out, tok{"id", s[i:j]})
			i = j
		case strings.IndexByte("+-*/()", c) >= 0 || (c == '^' && hasPow):
			out = append(out, tok{string(c), string(c)})
			i++
		default:
			fail("syntax")
		}
	}
	return out
}

type node struct {
	kind string // num npow unit qty pow neg + - * /
	val  *big.Rat
	name string
	exp  *int
	a, b *node
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
	t := p.t[p.i]
	p.i++
	return t
}

func (p *parser) exp() *int {
	if hasPow && p.peek() == "^" {
		p.take()
		sign := 1
		if p.peek() == "-" {
			p.take()
			sign = -1
		}
		if p.peek() != "num" {
			fail("syntax")
		}
		txt := p.take().text
		if len(txt) != 1 {
			fail("syntax")
		}
		v, _ := strconv.Atoi(txt)
		v *= sign
		return &v
	}
	return nil
}

func parseNum(txt string) *big.Rat {
	r := new(big.Rat)
	if i := strings.IndexByte(txt, '.'); i >= 0 {
		frac := txt[i+1:]
		n, _ := new(big.Int).SetString(txt[:i]+frac, 10)
		d := new(big.Int).Exp(big.NewInt(10), big.NewInt(int64(len(frac))), nil)
		return r.SetFrac(n, d)
	}
	n, _ := new(big.Int).SetString(txt, 10)
	return r.SetInt(n)
}

func (p *parser) power() *node {
	switch p.peek() {
	case "num":
		val := parseNum(p.take().text)
		if p.peek() == "id" {
			name := p.take().text
			return &node{kind: "qty", val: val, name: name, exp: p.exp()}
		}
		if e := p.exp(); e != nil {
			return &node{kind: "npow", val: val, exp: e}
		}
		return &node{kind: "num", val: val}
	case "id":
		name := p.take().text
		return &node{kind: "unit", name: name, exp: p.exp()}
	case "(":
		p.take()
		inner := p.expr()
		if p.peek() != ")" {
			fail("syntax")
		}
		p.take()
		if e := p.exp(); e != nil {
			return &node{kind: "pow", a: inner, exp: e}
		}
		return inner
	}
	fail("syntax")
	return nil
}

func (p *parser) unary() *node {
	if p.peek() == "-" {
		p.take()
		return &node{kind: "neg", a: p.unary()}
	}
	return p.power()
}

func (p *parser) term() *node {
	left := p.unary()
	for p.peek() == "*" || p.peek() == "/" {
		op := p.take().kind
		left = &node{kind: op, a: left, b: p.unary()}
	}
	return left
}

func (p *parser) expr() *node {
	left := p.term()
	for p.peek() == "+" || p.peek() == "-" {
		op := p.take().kind
		left = &node{kind: op, a: left, b: p.term()}
	}
	return left
}

func powq(v value, e int) value {
	out := value{r: new(big.Rat).SetInt64(1)}
	base := new(big.Rat).Set(v.r)
	n := e
	if e < 0 {
		if v.r.Sign() == 0 {
			fail("divide by zero")
		}
		base.Inv(base)
		n = -e
	}
	for k := 0; k < n; k++ {
		out.r.Mul(out.r, base)
	}
	for i := range v.dims {
		out.dims[i] = v.dims[i] * e
	}
	return out
}

func lookup(name string) value {
	for _, u := range units {
		if u.name == name {
			return value{r: big.NewRat(u.num, u.den), dims: u.dims}
		}
	}
	if len(name) > 1 {
		if pf, ok := prefixes[name[0]]; ok {
			for _, u := range units {
				if u.name == name[1:] {
					return value{r: new(big.Rat).Mul(big.NewRat(u.num, u.den), big.NewRat(pf[0], pf[1])), dims: u.dims}
				}
			}
		}
	}
	fail("unknown unit " + name)
	return value{}
}

func targetUnit(t string) value {
	if !composite {
		return lookup(t)
	}
	var toks []tok
	func() {
		defer func() {
			if r := recover(); r != nil {
				if _, ok := r.(calcErr); ok {
					fail("target")
				}
				panic(r)
			}
		}()
		toks = tokenize(t)
	}()
	type item struct {
		sign int
		name string
		e    int
	}
	var items []item
	i, sign := 0, 1
	for {
		if !(i < len(toks) && toks[i].kind == "id") {
			fail("target")
		}
		name := toks[i].text
		i++
		e := 1
		if i < len(toks) && toks[i].kind == "^" {
			i++
			sg := 1
			if i < len(toks) && toks[i].kind == "-" {
				i++
				sg = -1
			}
			if !(i < len(toks) && toks[i].kind == "num" && len(toks[i].text) == 1) {
				fail("target")
			}
			v, _ := strconv.Atoi(toks[i].text)
			e = sg * v
			i++
		}
		items = append(items, item{sign, name, e})
		if i < len(toks) && toks[i].kind == "*" {
			i++
			sign = 1
		} else if i < len(toks) && toks[i].kind == "/" {
			i++
			sign = -1
		} else {
			break
		}
	}
	if i != len(toks) {
		fail("target")
	}
	size := value{r: new(big.Rat).SetInt64(1)}
	for _, it := range items {
		f := powq(lookup(it.name), it.sign*it.e)
		size.r.Mul(size.r, f.r)
		for k := range size.dims {
			size.dims[k] += f.dims[k]
		}
	}
	return size
}

func ev(t *node) value {
	switch t.kind {
	case "num":
		return value{r: t.val}
	case "npow":
		return powq(value{r: t.val}, *t.exp)
	case "unit":
		u := lookup(t.name)
		if t.exp != nil {
			return powq(u, *t.exp)
		}
		return u
	case "qty":
		u := lookup(t.name)
		if t.exp != nil {
			u = powq(u, *t.exp)
		}
		return value{r: new(big.Rat).Mul(t.val, u.r), dims: u.dims}
	case "pow":
		return powq(ev(t.a), *t.exp)
	case "neg":
		a := ev(t.a)
		return value{r: new(big.Rat).Neg(a.r), dims: a.dims}
	}
	a := ev(t.a)
	b := ev(t.b)
	switch t.kind {
	case "+", "-":
		if a.dims != b.dims {
			fail("dimension")
		}
		if t.kind == "+" {
			return value{r: new(big.Rat).Add(a.r, b.r), dims: a.dims}
		}
		return value{r: new(big.Rat).Sub(a.r, b.r), dims: a.dims}
	case "*":
		out := value{r: new(big.Rat).Mul(a.r, b.r)}
		for i := range out.dims {
			out.dims[i] = a.dims[i] + b.dims[i]
		}
		return out
	}
	if b.r.Sign() == 0 {
		fail("divide by zero")
	}
	out := value{r: new(big.Rat).Quo(a.r, b.r)}
	for i := range out.dims {
		out.dims[i] = a.dims[i] - b.dims[i]
	}
	return out
}

func format(q *big.Rat) string {
	neg := q.Sign() < 0
	n := new(big.Int).Abs(q.Num())
	d := q.Denom()
	scale := new(big.Int).Exp(big.NewInt(10), big.NewInt(digits), nil)
	scaled := new(big.Int).Mul(n, scale)
	scaled.Mul(scaled, big.NewInt(2))
	scaled.Add(scaled, d)
	scaled.Div(scaled, new(big.Int).Mul(d, big.NewInt(2)))
	ip, fp := new(big.Int).DivMod(scaled, scale, new(big.Int))
	s := ip.String()
	if fp.Sign() != 0 {
		f := fp.String()
		f = strings.Repeat("0", digits-len(f)) + f
		s += "." + strings.TrimRight(f, "0")
	}
	if neg && scaled.Sign() != 0 {
		return "-" + s
	}
	return s
}

// Calc evaluates expr and renders it in the target unit ("-" for a plain number).
func Calc(expr, target string) (out string) {
	defer func() {
		if r := recover(); r != nil {
			if e, ok := r.(calcErr); ok {
				out = "error: " + e.msg
				return
			}
			panic(r)
		}
	}()
	p := &parser{t: tokenize(expr)}
	tree := p.expr()
	if p.i != len(p.t) {
		fail("syntax")
	}
	v := ev(tree)
	var zero [nd]int
	if target == "-" {
		if v.dims != zero {
			fail("dimension")
		}
		return format(v.r)
	}
	u := targetUnit(target)
	if u.dims != v.dims {
		fail("dimension")
	}
	return format(new(big.Rat).Quo(v.r, u.r)) + " " + target
}
'''

RS = r'''
const ND: usize = @ND@;
const DIGITS: u32 = @DIGITS@;
const HAS_POW: bool = @HAS_POW@;
const COMPOSITE: bool = @COMPOSITE@;
const PREFIXES: &[(char, i128, i128)] = &@PREFIXES_RS@;
const UNITS: &[(&str, i128, i128, [i32; ND])] = &@UNITS_RS@;

type Dims = [i32; ND];

#[derive(Clone, Copy)]
struct Q {
    n: i128,
    d: i128,
}

fn gcd(a: i128, b: i128) -> i128 {
    let (mut a, mut b) = (a.abs(), b.abs());
    while b != 0 {
        let t = a % b;
        a = b;
        b = t;
    }
    a
}

fn q(n: i128, d: i128) -> Q {
    let g = gcd(n, d).max(1);
    let s = if d < 0 { -1 } else { 1 };
    Q { n: s * n / g, d: s * d / g }
}

impl Q {
    fn add(self, o: Q) -> Q { q(self.n * o.d + o.n * self.d, self.d * o.d) }
    fn sub(self, o: Q) -> Q { q(self.n * o.d - o.n * self.d, self.d * o.d) }
    fn mul(self, o: Q) -> Q { q(self.n * o.n, self.d * o.d) }
    fn div(self, o: Q) -> Q { q(self.n * o.d, self.d * o.n) }
}

#[derive(Clone)]
enum Tok {
    Num(String),
    Id(String),
    Sym(char),
}

enum Node {
    Num(Q),
    NPow(Q, i32),
    Unit(String, Option<i32>),
    Qty(Q, String, Option<i32>),
    Pow(Box<Node>, i32),
    Neg(Box<Node>),
    Bin(char, Box<Node>, Box<Node>),
}

type R<T> = Result<T, String>;

fn syntax<T>() -> R<T> {
    Err("syntax".to_string())
}

fn tokenize(s: &str) -> R<Vec<Tok>> {
    let b: Vec<char> = s.chars().collect();
    let mut out = Vec::new();
    let mut i = 0;
    let dg = |c: char| c.is_ascii_digit();
    while i < b.len() {
        let c = b[i];
        if c == ' ' || c == '\t' {
            i += 1;
        } else if dg(c) {
            let mut j = i;
            while j < b.len() && dg(b[j]) {
                j += 1;
            }
            if j < b.len() && b[j] == '.' {
                let mut k = j + 1;
                if k >= b.len() || !dg(b[k]) {
                    return syntax();
                }
                while k < b.len() && dg(b[k]) {
                    k += 1;
                }
                j = k;
            }
            out.push(Tok::Num(b[i..j].iter().collect()));
            i = j;
        } else if c.is_ascii_lowercase() {
            let mut j = i;
            while j < b.len() && b[j].is_ascii_lowercase() {
                j += 1;
            }
            out.push(Tok::Id(b[i..j].iter().collect()));
            i = j;
        } else if "+-*/()".contains(c) || (c == '^' && HAS_POW) {
            out.push(Tok::Sym(c));
            i += 1;
        } else {
            return syntax();
        }
    }
    Ok(out)
}

struct Parser {
    t: Vec<Tok>,
    i: usize,
}

impl Parser {
    fn peek_sym(&self, c: char) -> bool {
        matches!(self.t.get(self.i), Some(Tok::Sym(x)) if *x == c)
    }
    fn exp(&mut self) -> R<Option<i32>> {
        if HAS_POW && self.peek_sym('^') {
            self.i += 1;
            let mut sign = 1;
            if self.peek_sym('-') {
                self.i += 1;
                sign = -1;
            }
            match self.t.get(self.i).cloned() {
                Some(Tok::Num(txt)) => {
                    self.i += 1;
                    if txt.len() != 1 {
                        return syntax();
                    }
                    Ok(Some(sign * txt.parse::<i32>().unwrap()))
                }
                _ => syntax(),
            }
        } else {
            Ok(None)
        }
    }
    fn power(&mut self) -> R<Node> {
        match self.t.get(self.i).cloned() {
            Some(Tok::Num(txt)) => {
                self.i += 1;
                let val = parse_num(&txt);
                if let Some(Tok::Id(name)) = self.t.get(self.i).cloned() {
                    self.i += 1;
                    let e = self.exp()?;
                    return Ok(Node::Qty(val, name, e));
                }
                match self.exp()? {
                    Some(e) => Ok(Node::NPow(val, e)),
                    None => Ok(Node::Num(val)),
                }
            }
            Some(Tok::Id(name)) => {
                self.i += 1;
                let e = self.exp()?;
                Ok(Node::Unit(name, e))
            }
            Some(Tok::Sym('(')) => {
                self.i += 1;
                let inner = self.expr()?;
                if !self.peek_sym(')') {
                    return syntax();
                }
                self.i += 1;
                match self.exp()? {
                    Some(e) => Ok(Node::Pow(Box::new(inner), e)),
                    None => Ok(inner),
                }
            }
            _ => syntax(),
        }
    }
    fn unary(&mut self) -> R<Node> {
        if self.peek_sym('-') {
            self.i += 1;
            return Ok(Node::Neg(Box::new(self.unary()?)));
        }
        self.power()
    }
    fn term(&mut self) -> R<Node> {
        let mut left = self.unary()?;
        while self.peek_sym('*') || self.peek_sym('/') {
            let op = if self.peek_sym('*') { '*' } else { '/' };
            self.i += 1;
            let right = self.unary()?;
            left = Node::Bin(op, Box::new(left), Box::new(right));
        }
        Ok(left)
    }
    fn expr(&mut self) -> R<Node> {
        let mut left = self.term()?;
        while self.peek_sym('+') || self.peek_sym('-') {
            let op = if self.peek_sym('+') { '+' } else { '-' };
            self.i += 1;
            let right = self.term()?;
            left = Node::Bin(op, Box::new(left), Box::new(right));
        }
        Ok(left)
    }
}

fn parse_num(txt: &str) -> Q {
    match txt.find('.') {
        Some(i) => {
            let frac = &txt[i + 1..];
            let n: i128 = format!("{}{}", &txt[..i], frac).parse().unwrap();
            q(n, 10i128.pow(frac.len() as u32))
        }
        None => q(txt.parse().unwrap(), 1),
    }
}

fn powq(v: (Q, Dims), e: i32) -> R<(Q, Dims)> {
    let (r, d) = v;
    let mut base = r;
    let mut n = e;
    if e < 0 {
        if r.n == 0 {
            return Err("divide by zero".to_string());
        }
        base = q(r.d, r.n);
        n = -e;
    }
    let mut out = q(1, 1);
    for _ in 0..n {
        out = out.mul(base);
    }
    let mut nd = d;
    for x in nd.iter_mut() {
        *x *= e;
    }
    Ok((out, nd))
}

fn unit(name: &str) -> R<(Q, Dims)> {
    for (n, num, den, dims) in UNITS.iter() {
        if *n == name {
            return Ok((q(*num, *den), *dims));
        }
    }
    let first = name.chars().next();
    if name.len() > 1 {
        if let Some((_, pn, pd)) = PREFIXES.iter().find(|(c, _, _)| Some(*c) == first) {
            for (n, num, den, dims) in UNITS.iter() {
                if *n == &name[1..] {
                    return Ok((q(*num, *den).mul(q(*pn, *pd)), *dims));
                }
            }
        }
    }
    Err(format!("unknown unit {}", name))
}

fn target_unit(t: &str) -> R<(Q, Dims)> {
    if !COMPOSITE {
        return unit(t);
    }
    let bad = || Err::<(Q, Dims), String>("target".to_string());
    let toks = match tokenize(t) {
        Ok(v) => v,
        Err(_) => return bad(),
    };
    let mut items: Vec<(i32, String, i32)> = Vec::new();
    let (mut i, mut sign) = (0usize, 1i32);
    loop {
        let name = match toks.get(i) {
            Some(Tok::Id(n)) => n.clone(),
            _ => return bad(),
        };
        i += 1;
        let mut e = 1;
        if let Some(Tok::Sym('^')) = toks.get(i) {
            i += 1;
            let mut sg = 1;
            if let Some(Tok::Sym('-')) = toks.get(i) {
                i += 1;
                sg = -1;
            }
            match toks.get(i) {
                Some(Tok::Num(txt)) if txt.len() == 1 => {
                    e = sg * txt.parse::<i32>().unwrap();
                    i += 1;
                }
                _ => return bad(),
            }
        }
        items.push((sign, name, e));
        match toks.get(i) {
            Some(Tok::Sym('*')) => {
                i += 1;
                sign = 1;
            }
            Some(Tok::Sym('/')) => {
                i += 1;
                sign = -1;
            }
            _ => break,
        }
    }
    if i != toks.len() {
        return bad();
    }
    let mut size = q(1, 1);
    let mut dims: Dims = [0; ND];
    for (sg, name, e) in items {
        let (f, d) = powq(unit(&name)?, sg * e)?;
        size = size.mul(f);
        for k in 0..ND {
            dims[k] += d[k];
        }
    }
    Ok((size, dims))
}

fn ev(t: &Node) -> R<(Q, Dims)> {
    let zero: Dims = [0; ND];
    match t {
        Node::Num(v) => Ok((*v, zero)),
        Node::NPow(v, e) => powq((*v, zero), *e),
        Node::Unit(name, e) => {
            let u = unit(name)?;
            match e {
                Some(e) => powq(u, *e),
                None => Ok(u),
            }
        }
        Node::Qty(v, name, e) => {
            let mut u = unit(name)?;
            if let Some(e) = e {
                u = powq(u, *e)?;
            }
            Ok((v.mul(u.0), u.1))
        }
        Node::Pow(inner, e) => powq(ev(inner)?, *e),
        Node::Neg(inner) => {
            let a = ev(inner)?;
            Ok((q(-a.0.n, a.0.d), a.1))
        }
        Node::Bin(op, l, r) => {
            let a = ev(l)?;
            let b = ev(r)?;
            match op {
                '+' | '-' => {
                    if a.1 != b.1 {
                        return Err("dimension".to_string());
                    }
                    Ok((if *op == '+' { a.0.add(b.0) } else { a.0.sub(b.0) }, a.1))
                }
                '*' => {
                    let mut d = a.1;
                    for i in 0..ND {
                        d[i] += b.1[i];
                    }
                    Ok((a.0.mul(b.0), d))
                }
                _ => {
                    if b.0.n == 0 {
                        return Err("divide by zero".to_string());
                    }
                    let mut d = a.1;
                    for i in 0..ND {
                        d[i] -= b.1[i];
                    }
                    Ok((a.0.div(b.0), d))
                }
            }
        }
    }
}

fn fmt(v: Q) -> String {
    let neg = v.n < 0;
    let n = v.n.abs();
    let scale = 10i128.pow(DIGITS);
    let scaled = (2 * n * scale + v.d) / (2 * v.d);
    let (ip, fp) = (scaled / scale, scaled % scale);
    let mut s = ip.to_string();
    if fp != 0 {
        let f = format!("{:0w$}", fp, w = DIGITS as usize);
        s.push('.');
        s.push_str(f.trim_end_matches('0'));
    }
    if neg && scaled != 0 {
        format!("-{}", s)
    } else {
        s
    }
}

fn run(expr: &str, target: &str) -> R<String> {
    let toks = tokenize(expr)?;
    let mut p = Parser { t: toks, i: 0 };
    let tree = p.expr()?;
    if p.i != p.t.len() {
        return syntax();
    }
    let (r, d) = ev(&tree)?;
    let zero: Dims = [0; ND];
    if target == "-" {
        if d != zero {
            return Err("dimension".to_string());
        }
        return Ok(fmt(r));
    }
    let (f, td) = target_unit(target)?;
    if td != d {
        return Err("dimension".to_string());
    }
    Ok(format!("{} {}", fmt(r.div(f)), target))
}

/// Evaluates `expr` and renders it in the target unit (`-` for a plain number).
pub fn calc(expr: &str, target: &str) -> String {
    match run(expr, target) {
        Ok(s) => s,
        Err(e) => format!("error: {}", e),
    }
}
'''


def _b(lang, v):
    return "True" if (lang == "python" and v) else "False" if lang == "python" else ("true" if v else "false")


def sol(lang, p):
    units = p["units"]
    src = {"python": PY, "javascript": JS, "go": GO, "rust": RS}[lang]
    py = "[" + ", ".join(f'("{n}", {a}, {b}, {tuple(d)!r})' for n, a, b, d in units) + "]"
    js = "[" + ", ".join(f'["{n}", {a}, {b}, {list(d)!r}]' for n, a, b, d in units) + "]"
    go = "[]unitDef{" + ", ".join(f'{{"{n}", {a}, {b}, [nd]int{{{", ".join(map(str, d))}}}}}' for n, a, b, d in units) + "}"
    rs = "[" + ", ".join(f'("{n}", {a}, {b}, [{", ".join(map(str, d))}])' for n, a, b, d in units) + "]"
    pf = p["prefixes"]
    pf_py = "{" + ", ".join(f'"{k}": Fraction({a}, {b})' for k, (a, b) in pf.items()) + "}"
    pf_js = "{" + ", ".join(f'{k}: [{a}, {b}]' for k, (a, b) in pf.items()) + "}"
    pf_go = "map[byte][2]int64{" + ", ".join(f"'{k}': {{{a}, {b}}}" for k, (a, b) in pf.items()) + "}"
    pf_rs = "[" + ", ".join(f"('{k}', {a}, {b})" for k, (a, b) in pf.items()) + "]"
    return K.subst(src, ND=p["nd"], DIGITS=p["digits"], HAS_POW=_b(lang, p["pow"]), COMPOSITE=_b(lang, p["composite"]),
                   UNITS_PY=py, UNITS_JS=js, UNITS_GO=go, UNITS_RS=rs, PREFIXES_PY=pf_py, PREFIXES_JS=pf_js, PREFIXES_GO=pf_go,
                   PREFIXES_RS=pf_rs).lstrip("\n")


# ---------------------------------------------------------------------------------------------------------------

def dims_text(p, d):
    parts = []
    for name, e in zip(p["dims"], d):
        if e == 1:
            parts.append(name)
        elif e != 0:
            parts.append(f"{name}^{e}")
    return " * ".join(parts) if parts else "(plain number)"


def readme(p, api, lang, examples):
    L = ["# Unit calculator", ""]
    L.append("The surveyors of an invented archipelago measure everything in their own units. This library evaluates arithmetic on *quantities* "
             "written in those units, checks that the dimensions fit, and prints the answer in the unit the caller asks for. All arithmetic is "
             "**exact** (rational numbers): the numbers in the test-suite keep every numerator and denominator below 10^15 at every step, so 128-bit or "
             "arbitrary precision integers are enough; floating point is not good enough.")
    L.append("")
    L.append("## Units and dimensions")
    L.append("")
    L.append(f"There are {p['nd']} base kinds of measure: " + ", ".join(f"`{d}`" for d in p["dims"]) + ". "
             "The *dimension* of a quantity is the list of exponents of the base kinds; a plain number has all exponents 0. "
             "Every unit has a fixed dimension and a size expressed as an exact fraction of the *base unit* of its dimension. The table is the whole unit system:")
    L.append("")
    L.append("| unit | dimension | size |")
    L.append("|---|---|---|")
    for n, a, b, d in p["units"]:
        L.append(f"| `{n}` | {dims_text(p, d)} | {a if b == 1 else f'{a}/{b}'} |")
    L.append("")
    u0 = p["units"][0][0]
    L.append("A *magnitude* is stored as an exact fraction of the base units: `3 " + u0 + "` has magnitude `3 x (size of " + u0 + ")`.")
    L.append("")
    if p["prefixes"]:
        L.append("**Prefixes.** A unit name may carry a one-letter prefix: " + ", ".join(f"`{k}` (x{a if b == 1 else f'{a}/{b}'})" for k, (a, b) in sorted(p["prefixes"].items())) +
                 ". To look a name up: if the whole name is in the table, that unit is meant (even when it also looks like a prefix plus another unit); "
                 "otherwise, if the name has at least two letters, its first letter is one of the prefixes and the rest is in the table, the unit is the table unit with its size multiplied by the prefix factor "
                 "(same dimension); otherwise the name is unknown, and `NAME` in `unknown unit NAME` is the whole name as written. Prefixes never combine with each other.")
        L.append("")
    L.append("## Expressions")
    L.append("")
    L.append("Tokens: numbers, unit names, the operators `+ - * /`" + (" `^`" if p["pow"] else "") + ", and parentheses. Spaces and tabs between tokens are ignored "
             "(and may be left out wherever the tokens stay distinguishable: `3" + p["units"][0][0] + "` is the same as `3 " + p["units"][0][0] + "`). Any other character is a syntax error. "
             "A **number** is one or more ASCII digits, optionally followed by `.` and one or more digits (`.5`, `5.` and `1.2.3` are not numbers). "
             "A **unit name** is a maximal run of lower-case ASCII letters `a`-`z`; names are matched case-sensitively against the table.")
    L.append("")
    L.append("Grammar (`|` separates alternatives, `[ ]` is optional):")
    L.append("")
    pw = " ['^' EXP]" if p["pow"] else ""
    L.append("```")
    L.append("expr    := term { ('+' | '-') term }")
    L.append("term    := unary { ('*' | '/') unary }")
    L.append("unary   := '-' unary | power")
    if p["pow"]:
        L.append("power   := NUMBER UNIT ['^' EXP]       quantity: the number times the unit raised to EXP")
        L.append("         | NUMBER ['^' EXP]            plain number (to the power EXP)")
        L.append("         | UNIT ['^' EXP]              one of that unit")
        L.append("         | '(' expr ')' ['^' EXP]")
        L.append("EXP     := ['-'] DIGIT                 a single digit 0-9, so exponents run from -9 to 9")
    else:
        L.append("power   := NUMBER UNIT                 quantity: the number times the unit")
        L.append("         | NUMBER")
        L.append("         | UNIT                         one of that unit")
        L.append("         | '(' expr ')'")
    L.append("```")
    L.append("")
    L.append("Binary operators associate to the left; `*` and `/` bind tighter than `+` and `-`; unary minus applies to the whole `power` after it"
             + (" (so `-2^2` is `-4`)" if p["pow"] else "") + ". There is no implicit multiplication other than `NUMBER UNIT`: `3 (ell)`, `2 3` and `ell ell` are syntax errors. "
             + ("In `3 ell^2` the exponent belongs to the unit only (3 times `ell` squared); `(3 ell)^2` squares the quantity. Powers do not chain: `2^3^2` is a syntax error. " if p["pow"] else "")
             + "The whole text must be consumed by one `expr`; an empty expression is a syntax error.")
    L.append("")
    L.append("## Meaning")
    L.append("")
    L.append("* A number has dimension 0. A unit name alone, or `NUMBER UNIT`, has the unit's dimension and the magnitude described above.")
    if p["pow"]:
        L.append("* Raising to the power `e` raises the magnitude to `e` and multiplies every dimension exponent by `e`; `x^0` is the plain number 1 (even for `0^0`); a negative exponent "
                 "takes the reciprocal first and fails with `divide by zero` when the base magnitude is 0.")
    L.append("* `+` and `-` need both operands to have the **same dimension**, otherwise the evaluation fails with `dimension`; the result has that dimension.")
    L.append("* `*` multiplies magnitudes and adds the dimensions; `/` divides magnitudes and subtracts the dimensions; dividing by a magnitude of 0 fails with `divide by zero` "
             "(even when the dividend is 0).")
    L.append("* Unary minus negates the magnitude.")
    L.append("")
    L.append("## Result text")
    L.append("")
    L.append("`calc(expr, target)` first parses the *whole* expression: any syntax problem gives `error: syntax`, whatever else is wrong with it. "
             "If the expression parses, it is evaluated; operands are evaluated from left to right and the operator is applied only after both operands succeeded, "
             "so the first failure in that order is the one reported: `error: unknown unit NAME` (a unit name that is not in the table), `error: dimension` or `error: divide by zero`. "
             "Only when the expression evaluates, the target is examined:")
    L.append("")
    L.append("* `target` is `-`: the value must be a plain number (all dimensions 0) or the result is `error: dimension`; the output is the number.")
    if p["composite"]:
        L.append("* otherwise `target` is a *unit expression*: `UNIT ['^' EXP] { ('*' | '/') UNIT ['^' EXP] }`, written with the same tokens as above (spaces and tabs are ignored; no numbers other than exponents, no parentheses, "
                 "no unary minus). Text that does not fit this shape (empty, a number, upper-case letters, a missing or doubled operator, a bad exponent, ...) gives `error: target`. "
                 "A valid target is then resolved from left to right: a unit that is not in the table gives `error: unknown unit NAME`. Its size is the product of the unit sizes raised to their exponents "
                 "(a unit after `/` counts with the negated exponent) and its dimension is combined the same way. If the dimension differs from the value's dimension the result is `error: dimension`; "
                 "otherwise the output is `NUMBER TARGET` where the number is `magnitude / size` and `TARGET` is the target text **exactly as it was given**, spaces included.")
    else:
        L.append("* otherwise `target` is a unit name: if it is not in the table the result is `error: unknown unit NAME`; if its dimension differs from the value's dimension the result is "
                 "`error: dimension`; otherwise the output is `NUMBER NAME` where the number is `magnitude / (size of NAME)`.")
    L.append("")
    L.append(f"**Number format**: round to {p['digits']} digits after the decimal point, with halves rounded **away from zero** (computed exactly, on the exact fraction), "
             "write the digits without grouping, strip trailing zeros from the fractional part and drop the point when nothing is left. "
             "A value that rounds to zero is written `0`, never `-0`. Examples with 2 digits: `1/3` is `0.33`, `5/2` is `2.5`, `-0.005` is `-0.01`, `-0.004` is `0`, `1200` is `1200`.")
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    L.append("| expr | target | result |")
    L.append("|---|---|---|")
    for (e, t), out in examples:
        L.append(f"| `{e}` | `{t}` | `{out}` |")
    L.append("")
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


def make_cases(rng, p, ns):
    track = {"m": 0}
    orig_ev = ns["ev"]

    def tracked(t):
        r = orig_ev(t)
        q = r[0]
        track["m"] = max(track["m"], abs(q.numerator), q.denominator)
        return r

    ns["ev"] = tracked

    def small(expr):
        track["m"] = 0
        try:
            ns["evaluate"](expr)
        except Exception:
            pass
        return track["m"] <= 10 ** 15

    units = p["units"]
    nd = p["nd"]
    zero = (0,) * nd
    by_dims = {}
    for n, a, b, d in units:
        by_dims.setdefault(tuple(d), []).append(n)
    avail = list(by_dims)
    calc = ns["calc"]
    cases = []

    def num(maxv=60):
        r = rng.random()
        if r < 0.5:
            return str(rng.randrange(1, maxv))
        if r < 0.85:
            return f"{rng.randrange(1, 30)}.{rng.randrange(1, 100):02d}"
        return f"{rng.randrange(1, 9)}.{rng.randrange(1, 10)}"

    def leaf(dims, allow_pow=True):
        if dims == zero:
            return num()
        us = by_dims.get(dims)
        if us:
            u = rng.choice(us)
            if p["prefixes"] and rng.random() < 0.3:
                u = rng.choice(sorted(p["prefixes"])) + u
            return f"{num()} {u}"
        return f"{num()} {rng.choice(by_dims[rng.choice(avail)])}"

    def splits(dims):
        out = []
        for a in avail + [zero]:
            for b in avail + [zero]:
                if tuple(x + y for x, y in zip(a, b)) == dims:
                    out.append((a, b))
        return out

    def qsplits(dims):
        out = []
        for a in avail + [zero]:
            for b in avail + [zero]:
                if b != zero and tuple(x - y for x, y in zip(a, b)) == dims:
                    out.append((a, b))
        return out

    def wrap(s):
        return f"({s})" if any(c in s for c in "+-") and not s.startswith("(") else s

    def wrapd(s):
        return f"({s})" if any(c in s for c in "+-*/") and not (s.startswith("(") and s.endswith(")") and s.count("(") == 1) else s

    def gen(dims, depth):
        r = rng.random()
        if depth == 0 or r < 0.3:
            return leaf(dims)
        if r < 0.55:
            return f"{gen(dims, depth - 1)} {rng.choice('+-')} {gen(dims, depth - 1)}"
        if r < 0.75:
            sp = splits(dims)
            if sp:
                a, b = rng.choice(sp)
                return f"{wrap(gen(a, depth - 1))} * {wrap(gen(b, depth - 1))}"
        if r < 0.9:
            sp = qsplits(dims)
            if sp:
                a, b = rng.choice(sp)
                return f"{wrap(gen(a, depth - 1))} / {wrapd(gen(b, depth - 1))}"
        if r < 0.95:
            return f"-{wrap(gen(dims, depth - 1))}"
        return f"({gen(dims, depth - 1)})"

    def compose(d):
        found = []
        for a in avail:
            for e1 in (1, 2, -1, 3):
                for ua in by_dims[a][:2]:
                    rem = tuple(x - e1 * y for x, y in zip(d, a))
                    if all(x == 0 for x in rem):
                        found.append(f"{ua}^{e1}" if e1 != 1 else ua)
                    for b in avail:
                        for e2 in (1, -1, 2):
                            if tuple(x * 1 for x in rem) == tuple(e2 * y for y in b):
                                ub = by_dims[b][0]
                                t2 = f"{ub}^{abs(e2)}" if abs(e2) != 1 else ub
                                t1 = f"{ua}^{e1}" if e1 != 1 else ua
                                found.append(f"{t1} * {t2}" if e2 > 0 else f"{t1} / {t2}")
        found = [f for f in found if f]
        return rng.choice(found) if found else None

    def target_for(expr):
        try:
            r, d = ns["evaluate"](expr)
        except Exception:
            return "-"
        d = tuple(d)
        if d == zero:
            return rng.choice(["-", "-", "-"])
        us = by_dims.get(d)
        if p["composite"] and (not us or rng.random() < 0.55):
            t = compose(d)
            if t:
                if p["pow"] and "^-" not in t and rng.random() < 0.2:
                    t = t.replace(" * ", "*").replace(" / ", "/")
                return t
        return rng.choice(us) if us else "-"

    def add(expr, target=None):
        cases.append((expr, target if target is not None else target_for(expr)))

    lv = p["level"]
    depth = 1 if lv <= 2 else 2 if lv <= 4 else 3
    # examples: three expressions that evaluate without error
    d0 = rng.choice(avail)
    add(f"{num()} {rng.choice(by_dims[d0])} + {num()} {rng.choice(by_dims[d0])}")
    tries = 0
    while len(cases) < 3 and tries < 200:
        tries += 1
        e = gen(rng.choice(avail), 1 if len(cases) == 1 else depth)
        t = target_for(e)
        if not calc(e, t).startswith("error") and (e, t) not in cases:
            cases.append((e, t))
    nex = len(cases)
    # more generated
    for _ in range(14):
        add(gen(rng.choice(avail), depth))
    for _ in range(6):
        add(gen(rng.choice(avail), depth + 1))
    # same dims, different units, rounding
    for dims, us in by_dims.items():
        if len(us) >= 2:
            a, b = rng.sample(us, 2)
            add(f"1 {a}", b)
            add(f"{num()} {a} - {num()} {b}", rng.choice(us))
            add(f"{num()} {a}", b)
    one = units[0][0]
    # rounding
    base = units[0]
    b0 = [u for u in units if tuple(u[3]) == tuple(units[0][3])]
    for expr in ["1/3", "2/3", "5/2", "1/8", "7/8", "1/16", "3/16"]:
        a, b = expr.split("/")
        add(f"{a} / {b}", "-")
    dg = p["digits"]
    for frac in ["4", "5", "6", "49", "51", "5000", "4999", "9", "95"]:
        for ip in ["0", "12", "7"]:
            add(f"{ip}.{'0' * dg}{frac}" if frac not in ("9", "95") else f"{ip}.{'9' * dg}{frac}", "-")
            add(f"-{ip}.{'3' * dg}{frac}", "-")
    for expr in ["0.005", "0.004", "0.0049", "0.0051", "0.001", "0.0005", "1.005", "2.675", "123.456", "1000", "0", "0.00", "10.10"]:
        add(expr, "-")
        add("-" + expr, "-")
    add("-0.0004", "-")
    add("0 * 5", "-")
    add(f"{p['units'][0][0]} - {p['units'][0][0]}", p["units"][0][0])
    add(f"-{p['units'][0][0]} + {p['units'][0][0]}", p["units"][0][0])
    # unary minus & precedence
    u0 = units[0][0]
    for e in [f"2 * 3 + 4", f"2 + 3 * 4", f"(2 + 3) * 4", f"10 - 4 - 3", f"100 / 5 / 4", f"2 * -3", f"- - 2", f"-(2 + 1)", f"8 / 2 * 4", f"1 - -1", f"-2 * -2",
              f"{u0} * 3 / {u0}", f"3 {u0} / 2 {u0}", f"(1)", f"((2))", f"2*3", f"2   *\t3", f"3{u0}", f"3.5{u0}", f"{u0}", f"{u0}{u0}" ]:
        add(e)
    if p["pow"]:
        for e in ["2^3", "2^-2", "-2^2", "(-2)^2", "2^0", "0^0", "0^2", "10^1", "1.5^2", "(1 + 1)^3", f"{u0}^2", f"3 {u0}^2", f"(3 {u0})^2", f"2 {u0}^-1", f"{u0}^0",
                  f"(2 {u0} + 3 {u0})^2", f"{u0}^2 / {u0}", f"{u0}^3 / {u0}^2", f"2 {u0}^3 * 3 {u0}^-2", "2 ^ 3", "2^ -1", f"- {u0} ^ 2", f"1 / {u0}^2", f"{u0}^9", f"2^9", "0^-1", f"(0 {u0})^-1", "(2)^2^2",
                  "2^3^2", "2^12", "2^--1", "2^", "^2", f"{u0}^x", "2^1.5", "2^+1", "(1 + 1)^-3"]:
            add(e)
    else:
        for e in ["2^3", f"{u0}^2", "2 ^ 3"]:
            add(e)
    # errors
    for e in ["", "   ", "+", "3 +", "* 3", "(3", "3)", "()", "3 ell )", "3..2", ".5", "5.", "1.2.3", "2 3", "3 (4)", "3 (" + u0 + ")", "(3) 4", "$", "3 # 4", "3 % 2", "3,5", "1e5", "3 - - ", "3 * * 2",
              "3 / ", f"{u0.upper()}", f"3 {u0.capitalize()}", "3 ell2", "3 2ell", "a b", f"{u0} 3", f"3 {u0} 2", "--", "-", "(-)", "1 +* 2", "((1)", "1 (2)", "3 4 5", "3 .5", "3 . 5", "3\n+4", "0x10", "1_000"]:
        try:
            add(e)
        except Exception:
            pass
    add("3 zzz", "-")
    add(f"3 zzz + 1 {u0}", u0)
    add(f"1 {u0} + 3 zzz", u0)
    add(f"1 / 0", "-")
    add(f"1 {u0} / 0", "-")
    add(f"0 / 0", "-")
    add(f"1 / (2 - 2)", "-")
    add(f"3 qqq / 0", "-")
    add(f"1 / 0 + 3 qqq", "-")
    add(f"1 + 3 qqq", "-")
    add(f"1 {u0} + 1", u0)
    add(f"1 {u0} + 1", "-")
    # dimension mismatches between different dims
    ds = list(by_dims)
    if len(ds) >= 2:
        a, b = ds[0], ds[1]
        ua, ub = by_dims[a][0], by_dims[b][0]
        add(f"1 {ua} + 1 {ub}", ua)
        add(f"1 {ua} - 1 {ub}", ub)
        add(f"1 {ua} * 1 {ub}", ua)
        add(f"1 {ua} / 1 {ub}", "-")
        add(f"(1 {ua} + 1 {ub}) / 0", "-")
        add(f"1 / 0 + (1 {ua} + 1 {ub})", "-")
        add(f"1 {ua} + 1 {ub} + 3 zzz", ua)
        add(f"1 {ua} + 3 zzz + 1 {ub}", ua)
        add(f"1 {ua}", ub)
        add(f"1 {ua} / 1 {ua}", ua)
        add(f"1 {ua} / 1 {ua}", "-")
        add(f"2 {ua} / 4 {ua}", "-")
    # target errors
    add(f"1 {u0}", "nosuch")
    add(f"1 {u0}", u0.upper())
    if p["composite"]:
        for t in ["", "1", "2 " + u0, u0 + "^", u0 + "^x", u0 + "^12", u0 + "^1.5", u0 + " " + u0, u0 + "*", "*" + u0, u0 + "//" + u0, u0 + "/", "/" + u0, "-" + u0, "(" + u0 + ")",
                  u0 + "^-", u0 + " ^ 2", u0 + "^+1", "nosuch/" + u0, u0 + "*nosuch", "nosuch*", u0 + "^2^2", "-", u0 + "-" + u0, u0 + "+" + u0, u0 + "^2 / " + u0 + "^2 / " + u0]:
            add(f"1 {u0}", t)
        add(f"1 {u0} / 1 {u0}", u0 + "/" + u0)
        add(f"2 {u0}", u0 + "^1")
        add(f"2 {u0}", u0 + "^0")
        add(f"3", u0 + "^0")
        add(f"3", u0 + "/" + u0)
        add(f"3", u0 + " * " + u0 + "^-1")
        add(f"3 {u0}", "  " + u0 + "  ")
        add(f"3 {u0}", u0 + "\t")
    add(f"1 zzz", "nosuch")
    add(f"1 {u0} +", "nosuch")
    add("5", u0)
    add("5", "nosuch")
    add(f"1 {u0}", "-")
    if p["prefixes"]:
        for letter, (a, b) in sorted(p["prefixes"].items()):
            for n, ua, ub, d in units[:6]:
                if (letter + n) in {u[0] for u in units}:
                    add(f"1 {letter}{n}", n)
                    add(f"3 {letter}{n}^2" if p["pow"] else f"3 {letter}{n}", n if not p["pow"] else "-")
                    continue
                add(f"1 {letter}{n}", n)
                add(f"{num()} {letter}{n} + {num()} {n}", n)
                add(f"1 {n}", letter + n)
                add(f"({num()} {letter}{n})^2" if p["pow"] else f"{num()} {letter}{n}", "-")
        add("1 zzz", "-")
        add("1 kzzz", "-")
        for letter in sorted(p["prefixes"]):
            add(f"1 {letter}", "-")
            add(f"1 {letter}{letter}{units[0][0]}", units[0][0])
            add(f"1 {letter}{letter}", "-")
        add(f"1 x{units[0][0]}", "-")
        add(f"1 {units[0][0]}x", "-")
        add(f"1 K{units[0][0]}", "-")
    # derived: every unit to every other with equal dims, and zero
    for n, a, b, d in units:
        add(f"{num()} {n}", n)
        add(f"0 {n}", n)
        add(f"-{num()} {n}", n)
    out, seen = [], set()
    for k, c in enumerate(cases):
        if c not in seen and (k < nex or small(c[0])):
            seen.add(c)
            out.append(c)
    ns["ev"] = orig_ev
    return out, nex


def prompt(rng, p, api, lang):
    where = api.where(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    units = ", ".join(f"`{u[0]}`" for u in p["units"][:3])
    opts = [
        f"I need a unit-aware calculator in {ln}: expressions such as `3 {p['units'][0][0]} + 2 {p['units'][0][0]}`, with the archipelago's own units ({units}, ...). README.md defines the units, the grammar, the error texts and the output rounding. Implement `{fn}` in {where}. {K.closer(rng)}",
        f"Please build the quantity calculator described in README.md ({ln}). Entry point `{fn}`, file {where}. The fiddly parts are the exact rational arithmetic, which error wins when there are several, and the rounding rule for the result.",
        f"Surveyors keep mixing up their units, so we want `{fn}` ({ln}) to evaluate quantity expressions and refuse dimension mismatches. Write it in {where}; the spec in README.md is complete (units table, grammar, errors, number format). {K.closer(rng)}",
        f"Task ({ln}): parse and evaluate unit expressions as specified in README.md, converting the result into a requested unit. The function is `{fn}` in {where}. Don't use floats; the hidden checks include fractions like 1/3 and halves that must round away from zero.",
    ]
    return rng.choice(opts).strip()


@family("greenfield-unitcalc", category="greenfield", lang="mixed", kind="greenfield", n=12,
        summary="unit-aware calculator over an invented unit table: exact rationals, dimension checks, precedence, rounding, error priority")
def gen(rng, n):
    levels = [2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 3, 4]
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level)
        api = K.Api(mod="unitcalc", fn="calc", args=["expr", "target"],
                    arg_docs=["the expression text", "the unit to express the result in, or `-` for a plain number"],
                    ret_doc="the formatted result, or an `error: ...` text", doc="unit-aware calculator")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["calc"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=level, slug=f"{i + 1:02d}-{lang}-{p['units'][0][0]}-{p['nd']}d", oracle=(None if lang == "python" else ns["calc"]),
            tags=["parser", "rational", "units"], notes={"level": level, "nd": p["nd"], "digits": p["digits"], "units": len(p["units"])},
        )
