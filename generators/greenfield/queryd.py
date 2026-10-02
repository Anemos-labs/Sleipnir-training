"""Query engine over delimited text tables: invented keywords, typed null/number/text comparisons, conditions, expressions, grouping and aggregates, ordered errors."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

PY = r'''
SEP = @SEP@
OUTSEP = @OUTSEP@
K_SELECT = @K_SELECT@
K_WHERE = @K_WHERE@
K_GROUP = @K_GROUP@
K_HAVING = @K_HAVING@
K_ORDER = @K_ORDER@
K_LIMIT = @K_LIMIT@
K_ASC = @K_ASC@
K_DESC = @K_DESC@
K_HAS = @K_HAS@
K_STARTS = @K_STARTS@
K_ENDS = @K_ENDS@
HAS_LOGIC = @LOGIC@
HAS_EXPR = @EXPR@
HAS_AGG = @AGG@
LIM = 10 ** 15
LOW = "abcdefghijklmnopqrstuvwxyz"
DG = "0123456789"
AGGS = ("count", "sum", "min", "max", "avg")
FUNCS = ("len", "upper", "lower", "abs", "num")


class Err(Exception):
    pass


def keywords():
    ks = {K_SELECT, "as"}
    if True:
        ks |= {K_WHERE, K_LIMIT, K_ORDER, K_ASC, K_DESC}
    if HAS_LOGIC:
        ks |= {"and", "or", "not", K_HAS, K_STARTS, K_ENDS}
    if HAS_EXPR:
        ks |= {"is", "null", "in"}
    if HAS_AGG:
        ks |= {K_GROUP, K_HAVING}
    return ks


def goodname(s):
    return s != "" and s[0] in LOW and all(c in LOW + DG + "_" for c in s)


def int_text(s):
    if s.startswith("-"):
        body = s[1:]
        if body == "0":
            return False
    else:
        body = s
    return 1 <= len(body) <= 9 and all(c in DG for c in body) and (len(body) == 1 or body[0] != "0")


def parse_table(data):
    ls = data.split("\n")
    if ls and ls[-1] == "":
        ls.pop()
    if not ls:
        raise Err("error: table line 1: header")
    names = ls[0].split(SEP)
    ks = keywords()
    if not all(goodname(n) and n not in ks for n in names) or len(set(names)) != len(names):
        raise Err("error: table line 1: header")
    rows = []
    for i, line in enumerate(ls[1:], 2):
        if line == "":
            raise Err("error: table line %d: blank" % i)
        cells = line.split(SEP)
        if len(cells) != len(names):
            raise Err("error: table line %d: columns" % i)
        rows.append({n: (None if c == "" else int(c) if int_text(c) else c) for n, c in zip(names, cells)})
    return names, rows


def lex(q):
    toks = []
    i, n = 0, len(q)
    while i < n:
        c = q[i]
        if c in " \t\n":
            i += 1
        elif c in LOW:
            j = i
            while j < n and q[j] in LOW + DG + "_":
                j += 1
            toks.append(("name", q[i:j]))
            i = j
        elif c in DG:
            j = i
            while j < n and q[j] in DG:
                j += 1
            t = q[i:j]
            if len(t) > 9 or (len(t) > 1 and t[0] == "0"):
                raise Err("error: query: syntax")
            toks.append(("num", t))
            i = j
        elif c == "'":
            j = i + 1
            buf = []
            while True:
                if j >= n or q[j] == "\n":
                    raise Err("error: query: syntax")
                if q[j] == "'":
                    if j + 1 < n and q[j + 1] == "'":
                        buf.append("'")
                        j += 2
                        continue
                    break
                buf.append(q[j])
                j += 1
            toks.append(("str", "".join(buf)))
            i = j + 1
        elif q[i:i + 2] in ("!=", "<=", ">="):
            toks.append(("sym", q[i:i + 2]))
            i += 2
        elif c in ",()*+-/=<>":
            toks.append(("sym", c))
            i += 1
        else:
            raise Err("error: query: syntax")
    toks.append(("eof", ""))
    return toks


class P:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self):
        return self.t[self.i]

    def at(self, kind, text=None):
        k, s = self.t[self.i]
        return k == kind and (text is None or s == text)

    def sym(self, s):
        return self.at("sym", s)

    def kw(self, s):
        return self.at("name", s)

    def take(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def need(self, kind, text=None):
        if not self.at(kind, text):
            raise Err("error: query: syntax")
        return self.take()

    # expressions
    def expr(self):
        left = self.term()
        while HAS_EXPR and (self.sym("+") or self.sym("-")):
            op = self.take()[1]
            left = ("bin", op, left, self.term())
        return left

    def term(self):
        left = self.unary()
        while HAS_EXPR and (self.sym("*") or self.sym("/")):
            op = self.take()[1]
            left = ("bin", op, left, self.unary())
        return left

    def unary(self):
        if HAS_EXPR and self.sym("-"):
            self.take()
            return ("neg", self.unary())
        return self.atom()

    def atom(self):
        k, s = self.peek()
        if k == "num":
            self.take()
            return ("lit", int(s))
        if k == "str":
            self.take()
            return ("lit", s)
        if k == "sym" and s == "(" and HAS_EXPR:
            self.take()
            e = self.expr()
            self.need("sym", ")")
            return e
        if k == "name":
            if s in keywords():
                raise Err("error: query: syntax")
            self.take()
            if HAS_EXPR and self.sym("("):
                self.take()
                args = []
                if self.sym("*"):
                    self.take()
                    args = ["*"]
                elif not self.sym(")"):
                    args.append(self.expr())
                    while self.sym(","):
                        self.take()
                        args.append(self.expr())
                self.need("sym", ")")
                if s in AGGS and HAS_AGG:
                    ok = (s == "count" and len(args) == 1) or (s != "count" and len(args) == 1 and args[0] != "*")
                    if not ok:
                        raise Err("error: query: syntax")
                    return ("agg", s, args[0])
                if args == ["*"]:
                    raise Err("error: query: syntax")
                return ("call", s, args)
            return ("col", s)
        raise Err("error: query: syntax")

    # conditions
    def cond(self):
        left = self.andc()
        while HAS_LOGIC and self.kw("or"):
            self.take()
            left = ("or", left, self.andc())
        return left

    def andc(self):
        left = self.notc()
        while HAS_LOGIC and self.kw("and"):
            self.take()
            left = ("and", left, self.notc())
        return left

    def notc(self):
        if HAS_LOGIC and self.kw("not"):
            self.take()
            return ("not", self.notc())
        if HAS_LOGIC and self.sym("("):
            save = self.i
            try:
                self.take()
                c = self.cond()
                self.need("sym", ")")
                return c
            except Err:
                self.i = save
        return self.pred()

    def pred(self):
        left = self.expr()
        k, s = self.peek()
        if k == "sym" and s in ("=", "!=", "<", "<=", ">", ">="):
            self.take()
            return ("cmp", s, left, self.expr())
        if HAS_LOGIC and k == "name" and s in (K_HAS, K_STARTS, K_ENDS):
            self.take()
            return ("txt", s, left, self.expr())
        if HAS_EXPR and k == "name" and s == "is":
            self.take()
            neg = False
            if self.kw("not"):
                self.take()
                neg = True
            self.need("name", "null")
            return ("isnull", neg, left)
        if HAS_EXPR and k == "name" and s == "in":
            self.take()
            self.need("sym", "(")
            items = [self.expr()]
            while self.sym(","):
                self.take()
                items.append(self.expr())
            self.need("sym", ")")
            return ("in", left, items)
        raise Err("error: query: syntax")

    def query(self):
        self.need("name", K_SELECT)
        items = []
        if self.sym("*"):
            self.take()
            items = [("star",)]
        else:
            while True:
                e = self.expr()
                alias = None
                if self.kw("as"):
                    self.take()
                    k, s = self.peek()
                    if k != "name" or s in keywords():
                        raise Err("error: query: syntax")
                    alias = self.take()[1]
                items.append(("item", e, alias))
                if self.sym(","):
                    self.take()
                    continue
                break
        where = group = having = None
        order = []
        limit = None
        if self.kw(K_WHERE):
            self.take()
            where = self.cond()
        if HAS_AGG and self.kw(K_GROUP):
            self.take()
            group = []
            while True:
                k, s = self.peek()
                if k != "name" or s in keywords():
                    raise Err("error: query: syntax")
                group.append(self.take()[1])
                if self.sym(","):
                    self.take()
                    continue
                break
            if self.kw(K_HAVING):
                self.take()
                having = self.cond()
        if self.kw(K_ORDER):
            self.take()
            while True:
                e = self.expr()
                desc = False
                if self.kw(K_DESC):
                    self.take()
                    desc = True
                elif self.kw(K_ASC):
                    self.take()
                order.append((e, desc))
                if self.sym(","):
                    self.take()
                    continue
                break
        if self.kw(K_LIMIT):
            self.take()
            k, s = self.peek()
            if k != "num":
                raise Err("error: query: syntax")
            limit = int(self.take()[1])
        if not self.at("eof"):
            raise Err("error: query: syntax")
        return {"items": items, "where": where, "group": group, "having": having, "order": order, "limit": limit}


def walk(e):
    """children in textual order"""
    k = e[0]
    if k in ("bin",):
        return [e[2], e[3]]
    if k == "neg":
        return [e[1]]
    if k == "call":
        return list(e[2])
    if k == "agg":
        return [] if e[2] == "*" else [e[2]]
    if k in ("cmp", "txt"):
        return [e[2], e[3]]
    if k == "isnull":
        return [e[2]]
    if k == "in":
        return [e[1]] + list(e[2])
    if k in ("and", "or"):
        return [e[1], e[2]]
    if k == "not":
        return [e[1]]
    return []


def contains_agg(e):
    return e[0] == "agg" or any(contains_agg(c) for c in walk(e))


def check(e, cols, aliases, aggq, group, in_agg, in_where):
    k = e[0]
    if k == "col":
        name = e[1]
        if aliases is not None and name in aliases:
            return
        if name not in cols:
            raise Err("error: query: unknown column " + name)
        if aggq and not in_agg and name not in (group or []):
            raise Err("error: query: not grouped " + name)
        return
    if k == "call":
        if e[1] not in FUNCS:
            raise Err("error: query: unknown function " + e[1])
    if k == "agg":
        if in_where:
            raise Err("error: query: aggregate in where")
        if in_agg:
            raise Err("error: query: nested aggregate")
        for c in walk(e):
            check(c, cols, aliases, aggq, group, True, in_where)
        return
    for c in walk(e):
        check(c, cols, aliases, aggq, group, in_agg, in_where)


def tostr(v):
    return str(v) if isinstance(v, int) else v


def cap(v):
    return None if abs(v) > LIM else v


def calc(op, a, b):
    if not (isinstance(a, int) and isinstance(b, int)):
        return None
    if op == "+":
        return cap(a + b)
    if op == "-":
        return cap(a - b)
    if op == "*":
        return cap(a * b)
    if b == 0:
        return None
    return cap(a // b)


def cmpvals(op, a, b):
    if a is None or b is None:
        return False
    if isinstance(a, int) and isinstance(b, int):
        x, y = a, b
    elif isinstance(a, str) and isinstance(b, str):
        x, y = a, b
    else:
        return op == "!="
    return {"=": x == y, "!=": x != y, "<": x < y, "<=": x <= y, ">": x > y, ">=": x >= y}[op]


def func(name, args):
    a = args[0] if args else None
    if len(args) != 1:
        return None
    if a is None:
        return None
    if name == "len":
        return len(tostr(a))
    if name == "upper":
        return "".join(c.upper() if "a" <= c <= "z" else c for c in tostr(a))
    if name == "lower":
        return "".join(c.lower() if "A" <= c <= "Z" else c for c in tostr(a))
    if name == "abs":
        return abs(a) if isinstance(a, int) else None
    if name == "num":
        if isinstance(a, int):
            return a
        return int(a) if int_text(a) else None
    return None


def aggregate(name, arg, rows, ev):
    if arg == "*":
        return len(rows)
    vals = [ev(arg, r) for r in rows]
    if name == "count":
        return sum(1 for v in vals if v is not None)
    nums = [v for v in vals if isinstance(v, int)]
    if not nums:
        return None
    if name == "sum":
        return cap(sum(nums))
    if name == "min":
        return min(nums)
    if name == "max":
        return max(nums)
    s, c = sum(nums), len(nums)
    return (2 * s + c) // (2 * c)


def query(data, q):
    try:
        return do_query(data, q)
    except Err as e:
        return str(e)


def do_query(data, q):
    cols, rows = parse_table(data)
    ast = P(lex(q)).query()
    items = []
    for it in ast["items"]:
        if it[0] == "star":
            items += [("item", ("col", c), None) for c in cols]
        else:
            items.append(it)
    aggq = ast["group"] is not None or any(contains_agg(it[1]) for it in items) or (ast["having"] is not None) or any(contains_agg(o[0]) for o in ast["order"])
    group = ast["group"]
    # static checks in clause order
    for it in ast["items"]:
        if it[0] == "star":
            if aggq:
                for c in cols:
                    if c not in (group or []):
                        raise Err("error: query: not grouped " + c)
        else:
            check(it[1], cols, None, aggq, group, False, False)
    if ast["where"] is not None:
        check(ast["where"], cols, None, False, None, False, True)
    for g in group or []:
        if g not in cols:
            raise Err("error: query: unknown column " + g)
    if ast["having"] is not None:
        check(ast["having"], cols, None, aggq, group, False, False)
    aliases = {it[2] for it in items if it[2]}
    for o in ast["order"]:
        check(o[0], cols, aliases, aggq, group, False, False)

    def ev(e, ctx):
        """ctx: dict row for plain rows, or (rows, rep) for groups"""
        k = e[0]
        if k == "lit":
            return e[1]
        if k == "col":
            r = ctx[1] if isinstance(ctx, tuple) else ctx
            return r[e[1]]
        if k == "neg":
            v = ev(e[1], ctx)
            return cap(-v) if isinstance(v, int) else None
        if k == "bin":
            return calc(e[1], ev(e[2], ctx), ev(e[3], ctx))
        if k == "call":
            return func(e[1], [ev(a, ctx) for a in e[2]])
        if k == "agg":
            return aggregate(e[1], e[2], ctx[0], lambda x, r: ev(x, r))
        if k == "cmp":
            return cmpvals(e[1], ev(e[2], ctx), ev(e[3], ctx))
        if k == "txt":
            a, b = ev(e[2], ctx), ev(e[3], ctx)
            if a is None or b is None:
                return False
            a, b = tostr(a), tostr(b)
            return b in a if e[1] == K_HAS else a.startswith(b) if e[1] == K_STARTS else a.endswith(b)
        if k == "isnull":
            return (ev(e[2], ctx) is None) != e[1]
        if k == "in":
            a = ev(e[1], ctx)
            return any(cmpvals("=", a, ev(x, ctx)) for x in e[2])
        if k == "and":
            return ev(e[1], ctx) and ev(e[2], ctx)
        if k == "or":
            return ev(e[1], ctx) or ev(e[2], ctx)
        if k == "not":
            return not ev(e[1], ctx)
        raise AssertionError(k)

    if ast["where"] is not None:
        rows = [r for r in rows if ev(ast["where"], r)]
    if aggq:
        if group:
            order_keys, buckets = [], {}
            for r in rows:
                key = tuple(r[g] for g in group)
                if key not in buckets:
                    buckets[key] = []
                    order_keys.append(key)
                buckets[key].append(r)
            ctxs = [(buckets[k], buckets[k][0]) for k in order_keys]
        else:
            ctxs = [(rows, rows[0] if rows else {c: None for c in cols})]
        if ast["having"] is not None:
            ctxs = [c for c in ctxs if ev(ast["having"], c)]
    else:
        ctxs = rows
    labels = []
    for n, it in enumerate(items, 1):
        labels.append(it[2] or (it[1][1] if it[1][0] == "col" else "col%d" % n))
    out = []
    for c in ctxs:
        vals = [ev(it[1], c) for it in items]
        alias_vals = {it[2]: v for it, v in zip(items, vals) if it[2]}

        def ev_o(e, c=c, alias_vals=alias_vals):
            if e[0] == "col" and e[1] in alias_vals:
                return alias_vals[e[1]]
            return ev(e, c)

        keys = [ev_o(o[0]) for o in ast["order"]]
        out.append((vals, keys))

    def rank(v):
        return 0 if isinstance(v, int) else 1 if isinstance(v, str) else 2

    import functools

    def cmpkey(x, y):
        for (a, b), o in zip(zip(x[1], y[1]), ast["order"]):
            ra, rb = rank(a), rank(b)
            if ra != rb:
                c = -1 if ra < rb else 1
            elif ra == 2 or a == b:
                c = 0
            else:
                c = -1 if a < b else 1
            if o[1]:
                c = -c
            if c:
                return c
        return 0

    if ast["order"]:
        out.sort(key=functools.cmp_to_key(cmpkey))
    if ast["limit"] is not None:
        out = out[:ast["limit"]]
    lines = [OUTSEP.join(labels)]
    for vals, _ in out:
        lines.append(OUTSEP.join("" if v is None else tostr(v) for v in vals))
    return "\n".join(lines)
'''

JS = r'''
'use strict';
const SEP = @SEP@;
const OUTSEP = @OUTSEP@;
const K_SELECT = @K_SELECT@;
const K_WHERE = @K_WHERE@;
const K_GROUP = @K_GROUP@;
const K_HAVING = @K_HAVING@;
const K_ORDER = @K_ORDER@;
const K_LIMIT = @K_LIMIT@;
const K_ASC = @K_ASC@;
const K_DESC = @K_DESC@;
const K_HAS = @K_HAS@;
const K_STARTS = @K_STARTS@;
const K_ENDS = @K_ENDS@;
const HAS_LOGIC = @LOGIC@;
const HAS_EXPR = @EXPR@;
const HAS_AGG = @AGG@;
const LIM = 1000000000000000n;
const LOW = 'abcdefghijklmnopqrstuvwxyz';
const DG = '0123456789';
const AGGS = ['count', 'sum', 'min', 'max', 'avg'];
const FUNCS = ['len', 'upper', 'lower', 'abs', 'num'];

class Err extends Error {}

function keywords() {
  const ks = new Set([K_SELECT, 'as', K_WHERE, K_LIMIT, K_ORDER, K_ASC, K_DESC]);
  if (HAS_LOGIC) for (const k of ['and', 'or', 'not', K_HAS, K_STARTS, K_ENDS]) ks.add(k);
  if (HAS_EXPR) for (const k of ['is', 'null', 'in']) ks.add(k);
  if (HAS_AGG) {
    ks.add(K_GROUP);
    ks.add(K_HAVING);
  }
  return ks;
}

function goodName(s) {
  if (s === '' || !LOW.includes(s[0])) return false;
  for (const c of s) if (!(LOW + DG + '_').includes(c)) return false;
  return true;
}

function allDig(s) {
  for (const c of s) if (!DG.includes(c)) return false;
  return true;
}

function intText(s) {
  let body = s;
  if (s.startsWith('-')) {
    body = s.slice(1);
    if (body === '0') return false;
  }
  return body.length >= 1 && body.length <= 9 && allDig(body) && (body.length === 1 || body[0] !== '0');
}

function isNum(v) {
  return typeof v === 'bigint';
}

function parseTable(data) {
  const ls = data.split('\n');
  if (ls.length > 0 && ls[ls.length - 1] === '') ls.pop();
  if (ls.length === 0) throw new Err('error: table line 1: header');
  const names = ls[0].split(SEP);
  const ks = keywords();
  if (!names.every((n) => goodName(n) && !ks.has(n)) || new Set(names).size !== names.length) throw new Err('error: table line 1: header');
  const rows = [];
  for (let i = 1; i < ls.length; i++) {
    const line = ls[i];
    if (line === '') throw new Err('error: table line ' + (i + 1) + ': blank');
    const cells = line.split(SEP);
    if (cells.length !== names.length) throw new Err('error: table line ' + (i + 1) + ': columns');
    const row = new Map();
    names.forEach((n, j) => row.set(n, cells[j] === '' ? null : intText(cells[j]) ? BigInt(cells[j]) : cells[j]));
    rows.push(row);
  }
  return [names, rows];
}

function lex(q) {
  const toks = [];
  let i = 0;
  const n = q.length;
  while (i < n) {
    const c = q[i];
    if (c === ' ' || c === '\t' || c === '\n') i++;
    else if (LOW.includes(c)) {
      let j = i;
      while (j < n && (LOW + DG + '_').includes(q[j])) j++;
      toks.push(['name', q.slice(i, j)]);
      i = j;
    } else if (DG.includes(c)) {
      let j = i;
      while (j < n && DG.includes(q[j])) j++;
      const t = q.slice(i, j);
      if (t.length > 9 || (t.length > 1 && t[0] === '0')) throw new Err('error: query: syntax');
      toks.push(['num', t]);
      i = j;
    } else if (c === "'") {
      let j = i + 1;
      let buf = '';
      for (;;) {
        if (j >= n || q[j] === '\n') throw new Err('error: query: syntax');
        if (q[j] === "'") {
          if (j + 1 < n && q[j + 1] === "'") {
            buf += "'";
            j += 2;
            continue;
          }
          break;
        }
        buf += q[j];
        j++;
      }
      toks.push(['str', buf]);
      i = j + 1;
    } else if (['!=', '<=', '>='].includes(q.slice(i, i + 2))) {
      toks.push(['sym', q.slice(i, i + 2)]);
      i += 2;
    } else if (',()*+-/=<>'.includes(c)) {
      toks.push(['sym', c]);
      i++;
    } else throw new Err('error: query: syntax');
  }
  toks.push(['eof', '']);
  return toks;
}

const KS = keywords();

class P {
  constructor(toks) {
    this.t = toks;
    this.i = 0;
  }

  peek() {
    return this.t[this.i];
  }

  at(kind, text) {
    const [k, s] = this.t[this.i];
    return k === kind && (text === undefined || s === text);
  }

  sym(s) {
    return this.at('sym', s);
  }

  kw(s) {
    return this.at('name', s);
  }

  take() {
    return this.t[this.i++];
  }

  need(kind, text) {
    if (!this.at(kind, text)) throw new Err('error: query: syntax');
    return this.take();
  }

  expr() {
    let left = this.term();
    while (HAS_EXPR && (this.sym('+') || this.sym('-'))) {
      const op = this.take()[1];
      left = ['bin', op, left, this.term()];
    }
    return left;
  }

  term() {
    let left = this.unary();
    while (HAS_EXPR && (this.sym('*') || this.sym('/'))) {
      const op = this.take()[1];
      left = ['bin', op, left, this.unary()];
    }
    return left;
  }

  unary() {
    if (HAS_EXPR && this.sym('-')) {
      this.take();
      return ['neg', this.unary()];
    }
    return this.atom();
  }

  atom() {
    const [k, s] = this.peek();
    if (k === 'num') {
      this.take();
      return ['lit', BigInt(s)];
    }
    if (k === 'str') {
      this.take();
      return ['lit', s];
    }
    if (k === 'sym' && s === '(' && HAS_EXPR) {
      this.take();
      const e = this.expr();
      this.need('sym', ')');
      return e;
    }
    if (k === 'name') {
      if (KS.has(s)) throw new Err('error: query: syntax');
      this.take();
      if (HAS_EXPR && this.sym('(')) {
        this.take();
        let args = [];
        if (this.sym('*')) {
          this.take();
          args = ['*'];
        } else if (!this.sym(')')) {
          args.push(this.expr());
          while (this.sym(',')) {
            this.take();
            args.push(this.expr());
          }
        }
        this.need('sym', ')');
        if (AGGS.includes(s) && HAS_AGG) {
          const ok = (s === 'count' && args.length === 1) || (s !== 'count' && args.length === 1 && args[0] !== '*');
          if (!ok) throw new Err('error: query: syntax');
          return ['agg', s, args[0]];
        }
        if (args.length === 1 && args[0] === '*') throw new Err('error: query: syntax');
        return ['call', s, args];
      }
      return ['col', s];
    }
    throw new Err('error: query: syntax');
  }

  cond() {
    let left = this.andc();
    while (HAS_LOGIC && this.kw('or')) {
      this.take();
      left = ['or', left, this.andc()];
    }
    return left;
  }

  andc() {
    let left = this.notc();
    while (HAS_LOGIC && this.kw('and')) {
      this.take();
      left = ['and', left, this.notc()];
    }
    return left;
  }

  notc() {
    if (HAS_LOGIC && this.kw('not')) {
      this.take();
      return ['not', this.notc()];
    }
    if (HAS_LOGIC && this.sym('(')) {
      const save = this.i;
      try {
        this.take();
        const c = this.cond();
        this.need('sym', ')');
        return c;
      } catch (e) {
        if (!(e instanceof Err)) throw e;
        this.i = save;
      }
    }
    return this.pred();
  }

  pred() {
    const left = this.expr();
    const [k, s] = this.peek();
    if (k === 'sym' && ['=', '!=', '<', '<=', '>', '>='].includes(s)) {
      this.take();
      return ['cmp', s, left, this.expr()];
    }
    if (HAS_LOGIC && k === 'name' && (s === K_HAS || s === K_STARTS || s === K_ENDS)) {
      this.take();
      return ['txt', s, left, this.expr()];
    }
    if (HAS_EXPR && k === 'name' && s === 'is') {
      this.take();
      let neg = false;
      if (this.kw('not')) {
        this.take();
        neg = true;
      }
      this.need('name', 'null');
      return ['isnull', neg, left];
    }
    if (HAS_EXPR && k === 'name' && s === 'in') {
      this.take();
      this.need('sym', '(');
      const items = [this.expr()];
      while (this.sym(',')) {
        this.take();
        items.push(this.expr());
      }
      this.need('sym', ')');
      return ['in', left, items];
    }
    throw new Err('error: query: syntax');
  }

  query() {
    this.need('name', K_SELECT);
    let items = [];
    if (this.sym('*')) {
      this.take();
      items = [['star']];
    } else {
      for (;;) {
        const e = this.expr();
        let alias = null;
        if (this.kw('as')) {
          this.take();
          const [k, s] = this.peek();
          if (k !== 'name' || KS.has(s)) throw new Err('error: query: syntax');
          alias = this.take()[1];
        }
        items.push(['item', e, alias]);
        if (this.sym(',')) {
          this.take();
          continue;
        }
        break;
      }
    }
    let where = null;
    let group = null;
    let having = null;
    const order = [];
    let limit = null;
    if (this.kw(K_WHERE)) {
      this.take();
      where = this.cond();
    }
    if (HAS_AGG && this.kw(K_GROUP)) {
      this.take();
      group = [];
      for (;;) {
        const [k, s] = this.peek();
        if (k !== 'name' || KS.has(s)) throw new Err('error: query: syntax');
        group.push(this.take()[1]);
        if (this.sym(',')) {
          this.take();
          continue;
        }
        break;
      }
      if (this.kw(K_HAVING)) {
        this.take();
        having = this.cond();
      }
    }
    if (this.kw(K_ORDER)) {
      this.take();
      for (;;) {
        const e = this.expr();
        let desc = false;
        if (this.kw(K_DESC)) {
          this.take();
          desc = true;
        } else if (this.kw(K_ASC)) this.take();
        order.push([e, desc]);
        if (this.sym(',')) {
          this.take();
          continue;
        }
        break;
      }
    }
    if (this.kw(K_LIMIT)) {
      this.take();
      const [k] = this.peek();
      if (k !== 'num') throw new Err('error: query: syntax');
      limit = Number(this.take()[1]);
    }
    if (!this.at('eof')) throw new Err('error: query: syntax');
    return { items, where, group, having, order, limit };
  }
}

function walk(e) {
  switch (e[0]) {
    case 'bin': return [e[2], e[3]];
    case 'neg': return [e[1]];
    case 'call': return e[2];
    case 'agg': return e[2] === '*' ? [] : [e[2]];
    case 'cmp':
    case 'txt': return [e[2], e[3]];
    case 'isnull': return [e[2]];
    case 'in': return [e[1]].concat(e[2]);
    case 'and':
    case 'or': return [e[1], e[2]];
    case 'not': return [e[1]];
    default: return [];
  }
}

function containsAgg(e) {
  return e[0] === 'agg' || walk(e).some(containsAgg);
}

function check(e, cols, aliases, aggq, group, inAgg, inWhere) {
  const k = e[0];
  if (k === 'col') {
    const name = e[1];
    if (aliases !== null && aliases.has(name)) return;
    if (!cols.includes(name)) throw new Err('error: query: unknown column ' + name);
    if (aggq && !inAgg && !(group || []).includes(name)) throw new Err('error: query: not grouped ' + name);
    return;
  }
  if (k === 'call' && !FUNCS.includes(e[1])) throw new Err('error: query: unknown function ' + e[1]);
  if (k === 'agg') {
    if (inWhere) throw new Err('error: query: aggregate in where');
    if (inAgg) throw new Err('error: query: nested aggregate');
    for (const c of walk(e)) check(c, cols, aliases, aggq, group, true, inWhere);
    return;
  }
  for (const c of walk(e)) check(c, cols, aliases, aggq, group, inAgg, inWhere);
}

const tostr = (v) => (isNum(v) ? v.toString() : v);
const cap = (v) => (v > LIM || v < -LIM ? null : v);

function calc(op, a, b) {
  if (!isNum(a) || !isNum(b)) return null;
  if (op === '+') return cap(a + b);
  if (op === '-') return cap(a - b);
  if (op === '*') return cap(a * b);
  if (b === 0n) return null;
  let q = a / b;
  if ((a % b !== 0n) && ((a < 0n) !== (b < 0n))) q -= 1n;
  return cap(q);
}

function cmpvals(op, a, b) {
  if (a === null || b === null) return false;
  let x;
  let y;
  if (isNum(a) && isNum(b)) {
    x = a;
    y = b;
  } else if (typeof a === 'string' && typeof b === 'string') {
    x = a;
    y = b;
  } else return op === '!=';
  switch (op) {
    case '=': return x === y;
    case '!=': return x !== y;
    case '<': return x < y;
    case '<=': return x <= y;
    case '>': return x > y;
    default: return x >= y;
  }
}

function func(name, args) {
  if (args.length !== 1) return null;
  const a = args[0];
  if (a === null) return null;
  if (name === 'len') return BigInt(tostr(a).length);
  if (name === 'upper') return tostr(a).replace(/[a-z]/g, (c) => c.toUpperCase());
  if (name === 'lower') return tostr(a).replace(/[A-Z]/g, (c) => c.toLowerCase());
  if (name === 'abs') return isNum(a) ? (a < 0n ? -a : a) : null;
  if (name === 'num') {
    if (isNum(a)) return a;
    return intText(a) ? BigInt(a) : null;
  }
  return null;
}

function aggregate(name, arg, rows, ev) {
  if (arg === '*') return BigInt(rows.length);
  const vals = rows.map((r) => ev(arg, r));
  if (name === 'count') return BigInt(vals.filter((v) => v !== null).length);
  const nums = vals.filter(isNum);
  if (nums.length === 0) return null;
  if (name === 'sum') return cap(nums.reduce((a, b) => a + b, 0n));
  if (name === 'min') return nums.reduce((a, b) => (b < a ? b : a));
  if (name === 'max') return nums.reduce((a, b) => (b > a ? b : a));
  const s = nums.reduce((a, b) => a + b, 0n);
  const c = BigInt(nums.length);
  const num = 2n * s + c;
  const den = 2n * c;
  let q = num / den;
  if (num % den !== 0n && num < 0n) q -= 1n;
  return q;
}

function rank(v) {
  return isNum(v) ? 0 : typeof v === 'string' ? 1 : 2;
}

function doQuery(data, q) {
  const [cols, allRows] = parseTable(data);
  let rows = allRows;
  const ast = new P(lex(q)).query();
  let items = [];
  for (const it of ast.items) {
    if (it[0] === 'star') items = items.concat(cols.map((c) => ['item', ['col', c], null]));
    else items.push(it);
  }
  const group = ast.group;
  const aggq = group !== null || items.some((it) => containsAgg(it[1])) || ast.having !== null || ast.order.some((o) => containsAgg(o[0]));
  for (const it of ast.items) {
    if (it[0] === 'star') {
      if (aggq) for (const c of cols) if (!(group || []).includes(c)) throw new Err('error: query: not grouped ' + c);
    } else check(it[1], cols, null, aggq, group, false, false);
  }
  if (ast.where !== null) check(ast.where, cols, null, false, null, false, true);
  for (const g of group || []) if (!cols.includes(g)) throw new Err('error: query: unknown column ' + g);
  if (ast.having !== null) check(ast.having, cols, null, aggq, group, false, false);
  const aliases = new Set(items.filter((it) => it[2]).map((it) => it[2]));
  for (const o of ast.order) check(o[0], cols, aliases, aggq, group, false, false);

  function ev(e, ctx) {
    switch (e[0]) {
      case 'lit': return e[1];
      case 'col': return (ctx instanceof Map ? ctx : ctx.rep).get(e[1]);
      case 'neg': {
        const v = ev(e[1], ctx);
        return isNum(v) ? cap(-v) : null;
      }
      case 'bin': return calc(e[1], ev(e[2], ctx), ev(e[3], ctx));
      case 'call': return func(e[1], e[2].map((a) => ev(a, ctx)));
      case 'agg': return aggregate(e[1], e[2], ctx.rows, (x, r) => ev(x, r));
      case 'cmp': return cmpvals(e[1], ev(e[2], ctx), ev(e[3], ctx));
      case 'txt': {
        let a = ev(e[2], ctx);
        let b = ev(e[3], ctx);
        if (a === null || b === null) return false;
        a = tostr(a);
        b = tostr(b);
        return e[1] === K_HAS ? a.includes(b) : e[1] === K_STARTS ? a.startsWith(b) : a.endsWith(b);
      }
      case 'isnull': return (ev(e[2], ctx) === null) !== e[1];
      case 'in': {
        const a = ev(e[1], ctx);
        return e[2].some((x) => cmpvals('=', a, ev(x, ctx)));
      }
      case 'and': return ev(e[1], ctx) && ev(e[2], ctx);
      case 'or': return ev(e[1], ctx) || ev(e[2], ctx);
      case 'not': return !ev(e[1], ctx);
      default: throw new Error('bad node');
    }
  }

  if (ast.where !== null) rows = rows.filter((r) => ev(ast.where, r));
  let ctxs;
  if (aggq) {
    if (group && group.length > 0) {
      const keys = [];
      const buckets = new Map();
      for (const r of rows) {
        const key = JSON.stringify(group.map((g) => { const v = r.get(g); return v === null ? ['n'] : isNum(v) ? ['i', v.toString()] : ['s', v]; }));
        if (!buckets.has(key)) {
          buckets.set(key, []);
          keys.push(key);
        }
        buckets.get(key).push(r);
      }
      ctxs = keys.map((k) => ({ rows: buckets.get(k), rep: buckets.get(k)[0] }));
    } else {
      const empty = new Map(cols.map((c) => [c, null]));
      ctxs = [{ rows, rep: rows.length ? rows[0] : empty }];
    }
    if (ast.having !== null) ctxs = ctxs.filter((c) => ev(ast.having, c));
  } else ctxs = rows;
  const labels = items.map((it, n) => it[2] || (it[1][0] === 'col' ? it[1][1] : 'col' + (n + 1)));
  let out = [];
  for (const c of ctxs) {
    const vals = items.map((it) => ev(it[1], c));
    const aliasVals = new Map();
    items.forEach((it, i) => {
      if (it[2]) aliasVals.set(it[2], vals[i]);
    });
    const keys = ast.order.map((o) => (o[0][0] === 'col' && aliasVals.has(o[0][1]) ? aliasVals.get(o[0][1]) : ev(o[0], c)));
    out.push([vals, keys]);
  }
  const cmpkey = (x, y) => {
    for (let i = 0; i < ast.order.length; i++) {
      const a = x[1][i];
      const b = y[1][i];
      const ra = rank(a);
      const rb = rank(b);
      let c;
      if (ra !== rb) c = ra < rb ? -1 : 1;
      else if (ra === 2 || a === b) c = 0;
      else c = a < b ? -1 : 1;
      if (ast.order[i][1]) c = -c;
      if (c) return c;
    }
    return 0;
  };
  if (ast.order.length > 0) out = out.map((x, i) => [x, i]).sort((p, q2) => cmpkey(p[0], q2[0]) || p[1] - q2[1]).map((p) => p[0]);
  if (ast.limit !== null) out = out.slice(0, ast.limit);
  const lines = [labels.join(OUTSEP)];
  for (const [vals] of out) lines.push(vals.map((v) => (v === null ? '' : tostr(v))).join(OUTSEP));
  return lines.join('\n');
}

function query(data, q) {
  try {
    return doQuery(data, q);
  } catch (e) {
    if (e instanceof Err) return e.message;
    throw e;
  }
}

module.exports = { query };
'''

JV = r'''
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class Queryd {
    static final String SEP = @SEP@;
    static final String OUTSEP = @OUTSEP@;
    static final String K_SELECT = @K_SELECT@;
    static final String K_WHERE = @K_WHERE@;
    static final String K_GROUP = @K_GROUP@;
    static final String K_HAVING = @K_HAVING@;
    static final String K_ORDER = @K_ORDER@;
    static final String K_LIMIT = @K_LIMIT@;
    static final String K_ASC = @K_ASC@;
    static final String K_DESC = @K_DESC@;
    static final String K_HAS = @K_HAS@;
    static final String K_STARTS = @K_STARTS@;
    static final String K_ENDS = @K_ENDS@;
    static final boolean HAS_LOGIC = @LOGIC@;
    static final boolean HAS_EXPR = @EXPR@;
    static final boolean HAS_AGG = @AGG@;
    static final long LIM = 1000000000000000L;
    static final String LOW = "abcdefghijklmnopqrstuvwxyz";
    static final String DG = "0123456789";
    static final List<String> AGGS = Arrays.asList("count", "sum", "min", "max", "avg");
    static final List<String> FUNCS = Arrays.asList("len", "upper", "lower", "abs", "num");

    static class Err extends RuntimeException {
        Err(String m) { super(m); }
    }

    static Err syntax() {
        return new Err("error: query: syntax");
    }

    static class Node {
        String k;
        String op;
        Object lit; // Long or String
        Node a, b;
        boolean flag;
        boolean star;
        List<Node> args = new ArrayList<>();
    }

    static class Item {
        boolean isStar;
        Node e;
        String alias;
    }

    static class Ast {
        List<Item> items = new ArrayList<>();
        Node where, having;
        List<String> group;
        List<Node> orderE = new ArrayList<>();
        List<Boolean> orderDesc = new ArrayList<>();
        long limit = -1;
    }

    static final Set<String> KS = keywords();

    static Set<String> keywords() {
        Set<String> ks = new HashSet<>(Arrays.asList(K_SELECT, "as", K_WHERE, K_LIMIT, K_ORDER, K_ASC, K_DESC));
        if (HAS_LOGIC) ks.addAll(Arrays.asList("and", "or", "not", K_HAS, K_STARTS, K_ENDS));
        if (HAS_EXPR) ks.addAll(Arrays.asList("is", "null", "in"));
        if (HAS_AGG) ks.addAll(Arrays.asList(K_GROUP, K_HAVING));
        return ks;
    }

    static boolean goodName(String s) {
        if (s.isEmpty() || LOW.indexOf(s.charAt(0)) < 0) return false;
        for (int i = 0; i < s.length(); i++) if ((LOW + DG + "_").indexOf(s.charAt(i)) < 0) return false;
        return true;
    }

    static boolean allDig(String s) {
        for (int i = 0; i < s.length(); i++) if (DG.indexOf(s.charAt(i)) < 0) return false;
        return true;
    }

    static boolean intText(String s) {
        String body = s;
        if (s.startsWith("-")) {
            body = s.substring(1);
            if (body.equals("0")) return false;
        }
        return body.length() >= 1 && body.length() <= 9 && allDig(body) && (body.length() == 1 || body.charAt(0) != '0');
    }

    static Object cell(String c) {
        if (c.isEmpty()) return null;
        return intText(c) ? (Object) Long.valueOf(Long.parseLong(c)) : c;
    }

    static List<String> cols;
    static List<Map<String, Object>> allRows;

    static void parseTable(String data) {
        List<String> ls = new ArrayList<>(Arrays.asList(data.split("\n", -1)));
        if (!ls.isEmpty() && ls.get(ls.size() - 1).isEmpty()) ls.remove(ls.size() - 1);
        if (ls.isEmpty()) throw new Err("error: table line 1: header");
        List<String> names = Arrays.asList(ls.get(0).split(java.util.regex.Pattern.quote(SEP), -1));
        boolean ok = new HashSet<>(names).size() == names.size();
        for (String n : names) if (!goodName(n) || KS.contains(n)) ok = false;
        if (!ok) throw new Err("error: table line 1: header");
        cols = names;
        allRows = new ArrayList<>();
        for (int i = 1; i < ls.size(); i++) {
            String line = ls.get(i);
            if (line.isEmpty()) throw new Err("error: table line " + (i + 1) + ": blank");
            String[] cells = line.split(java.util.regex.Pattern.quote(SEP), -1);
            if (cells.length != names.size()) throw new Err("error: table line " + (i + 1) + ": columns");
            Map<String, Object> row = new LinkedHashMap<>();
            for (int j = 0; j < cells.length; j++) row.put(names.get(j), cell(cells[j]));
            allRows.add(row);
        }
    }

    static List<String[]> lex(String q) {
        List<String[]> toks = new ArrayList<>();
        int i = 0, n = q.length();
        while (i < n) {
            char c = q.charAt(i);
            if (c == ' ' || c == '\t' || c == '\n') i++;
            else if (LOW.indexOf(c) >= 0) {
                int j = i;
                while (j < n && (LOW + DG + "_").indexOf(q.charAt(j)) >= 0) j++;
                toks.add(new String[] { "name", q.substring(i, j) });
                i = j;
            } else if (DG.indexOf(c) >= 0) {
                int j = i;
                while (j < n && DG.indexOf(q.charAt(j)) >= 0) j++;
                String t = q.substring(i, j);
                if (t.length() > 9 || (t.length() > 1 && t.charAt(0) == '0')) throw syntax();
                toks.add(new String[] { "num", t });
                i = j;
            } else if (c == '\'') {
                int j = i + 1;
                StringBuilder buf = new StringBuilder();
                for (;;) {
                    if (j >= n || q.charAt(j) == '\n') throw syntax();
                    if (q.charAt(j) == '\'') {
                        if (j + 1 < n && q.charAt(j + 1) == '\'') {
                            buf.append('\'');
                            j += 2;
                            continue;
                        }
                        break;
                    }
                    buf.append(q.charAt(j));
                    j++;
                }
                toks.add(new String[] { "str", buf.toString() });
                i = j + 1;
            } else if (i + 1 < n && (q.startsWith("!=", i) || q.startsWith("<=", i) || q.startsWith(">=", i))) {
                toks.add(new String[] { "sym", q.substring(i, i + 2) });
                i += 2;
            } else if (",()*+-/=<>".indexOf(c) >= 0) {
                toks.add(new String[] { "sym", String.valueOf(c) });
                i++;
            } else throw syntax();
        }
        toks.add(new String[] { "eof", "" });
        return toks;
    }

    static class P {
        List<String[]> t;
        int i = 0;

        P(List<String[]> t) { this.t = t; }

        String[] peek() { return t.get(i); }

        boolean at(String kind, String text) {
            String[] x = t.get(i);
            return x[0].equals(kind) && (text == null || x[1].equals(text));
        }

        boolean sym(String s) { return at("sym", s); }

        boolean kw(String s) { return at("name", s); }

        String[] take() { return t.get(i++); }

        String[] need(String kind, String text) {
            if (!at(kind, text)) throw syntax();
            return take();
        }

        Node bin(String op, Node l, Node r) {
            Node n = new Node();
            n.k = "bin";
            n.op = op;
            n.a = l;
            n.b = r;
            return n;
        }

        Node expr() {
            Node left = term();
            while (HAS_EXPR && (sym("+") || sym("-"))) {
                String op = take()[1];
                left = bin(op, left, term());
            }
            return left;
        }

        Node term() {
            Node left = unary();
            while (HAS_EXPR && (sym("*") || sym("/"))) {
                String op = take()[1];
                left = bin(op, left, unary());
            }
            return left;
        }

        Node unary() {
            if (HAS_EXPR && sym("-")) {
                take();
                Node n = new Node();
                n.k = "neg";
                n.a = unary();
                return n;
            }
            return atom();
        }

        Node atom() {
            String[] tk = peek();
            String k = tk[0], s = tk[1];
            if (k.equals("num")) {
                take();
                Node n = new Node();
                n.k = "lit";
                n.lit = Long.valueOf(Long.parseLong(s));
                return n;
            }
            if (k.equals("str")) {
                take();
                Node n = new Node();
                n.k = "lit";
                n.lit = s;
                return n;
            }
            if (k.equals("sym") && s.equals("(") && HAS_EXPR) {
                take();
                Node e = expr();
                need("sym", ")");
                return e;
            }
            if (k.equals("name")) {
                if (KS.contains(s)) throw syntax();
                take();
                if (HAS_EXPR && sym("(")) {
                    take();
                    List<Node> args = new ArrayList<>();
                    boolean star = false;
                    if (sym("*")) {
                        take();
                        star = true;
                    } else if (!sym(")")) {
                        args.add(expr());
                        while (sym(",")) {
                            take();
                            args.add(expr());
                        }
                    }
                    need("sym", ")");
                    Node n = new Node();
                    n.op = s;
                    if (AGGS.contains(s) && HAS_AGG) {
                        boolean ok = star ? s.equals("count") : args.size() == 1;
                        if (!ok) throw syntax();
                        n.k = "agg";
                        n.star = star;
                        if (!star) n.a = args.get(0);
                        return n;
                    }
                    if (star) throw syntax();
                    n.k = "call";
                    n.args = args;
                    return n;
                }
                Node n = new Node();
                n.k = "col";
                n.op = s;
                return n;
            }
            throw syntax();
        }

        Node logic(String kind, Node l, Node r) {
            Node n = new Node();
            n.k = kind;
            n.a = l;
            n.b = r;
            return n;
        }

        Node cond() {
            Node left = andc();
            while (HAS_LOGIC && kw("or")) {
                take();
                left = logic("or", left, andc());
            }
            return left;
        }

        Node andc() {
            Node left = notc();
            while (HAS_LOGIC && kw("and")) {
                take();
                left = logic("and", left, notc());
            }
            return left;
        }

        Node notc() {
            if (HAS_LOGIC && kw("not")) {
                take();
                return logic("not", notc(), null);
            }
            if (HAS_LOGIC && sym("(")) {
                int save = i;
                try {
                    take();
                    Node c = cond();
                    need("sym", ")");
                    return c;
                } catch (Err e) {
                    i = save;
                }
            }
            return pred();
        }

        Node pred() {
            Node left = expr();
            String[] tk = peek();
            String k = tk[0], s = tk[1];
            if (k.equals("sym") && Arrays.asList("=", "!=", "<", "<=", ">", ">=").contains(s)) {
                take();
                Node n = logic("cmp", left, expr());
                n.op = s;
                return n;
            }
            if (HAS_LOGIC && k.equals("name") && (s.equals(K_HAS) || s.equals(K_STARTS) || s.equals(K_ENDS))) {
                take();
                Node n = logic("txt", left, expr());
                n.op = s;
                return n;
            }
            if (HAS_EXPR && k.equals("name") && s.equals("is")) {
                take();
                boolean neg = false;
                if (kw("not")) {
                    take();
                    neg = true;
                }
                need("name", "null");
                Node n = logic("isnull", left, null);
                n.flag = neg;
                return n;
            }
            if (HAS_EXPR && k.equals("name") && s.equals("in")) {
                take();
                need("sym", "(");
                Node n = logic("in", left, null);
                n.args.add(expr());
                while (sym(",")) {
                    take();
                    n.args.add(expr());
                }
                need("sym", ")");
                return n;
            }
            throw syntax();
        }

        Ast query() {
            need("name", K_SELECT);
            Ast ast = new Ast();
            if (sym("*")) {
                take();
                Item it = new Item();
                it.isStar = true;
                ast.items.add(it);
            } else {
                for (;;) {
                    Item it = new Item();
                    it.e = expr();
                    if (kw("as")) {
                        take();
                        String[] tk = peek();
                        if (!tk[0].equals("name") || KS.contains(tk[1])) throw syntax();
                        it.alias = take()[1];
                    }
                    ast.items.add(it);
                    if (sym(",")) {
                        take();
                        continue;
                    }
                    break;
                }
            }
            if (kw(K_WHERE)) {
                take();
                ast.where = cond();
            }
            if (HAS_AGG && kw(K_GROUP)) {
                take();
                ast.group = new ArrayList<>();
                for (;;) {
                    String[] tk = peek();
                    if (!tk[0].equals("name") || KS.contains(tk[1])) throw syntax();
                    ast.group.add(take()[1]);
                    if (sym(",")) {
                        take();
                        continue;
                    }
                    break;
                }
                if (kw(K_HAVING)) {
                    take();
                    ast.having = cond();
                }
            }
            if (kw(K_ORDER)) {
                take();
                for (;;) {
                    Node e = expr();
                    boolean desc = false;
                    if (kw(K_DESC)) {
                        take();
                        desc = true;
                    } else if (kw(K_ASC)) take();
                    ast.orderE.add(e);
                    ast.orderDesc.add(desc);
                    if (sym(",")) {
                        take();
                        continue;
                    }
                    break;
                }
            }
            if (kw(K_LIMIT)) {
                take();
                if (!peek()[0].equals("num")) throw syntax();
                ast.limit = Long.parseLong(take()[1]);
            }
            if (!at("eof", null)) throw syntax();
            return ast;
        }
    }

    static List<Node> walk(Node e) {
        List<Node> out = new ArrayList<>();
        switch (e.k) {
            case "bin":
            case "cmp":
            case "txt":
            case "and":
            case "or":
                out.add(e.a);
                out.add(e.b);
                break;
            case "neg":
            case "not":
            case "isnull":
                out.add(e.a);
                break;
            case "call":
                out.addAll(e.args);
                break;
            case "agg":
                if (!e.star) out.add(e.a);
                break;
            case "in":
                out.add(e.a);
                out.addAll(e.args);
                break;
            default:
                break;
        }
        return out;
    }

    static boolean containsAgg(Node e) {
        if (e.k.equals("agg")) return true;
        for (Node c : walk(e)) if (containsAgg(c)) return true;
        return false;
    }

    static void check(Node e, Set<String> aliases, boolean aggq, List<String> group, boolean inAgg, boolean inWhere) {
        String k = e.k;
        if (k.equals("col")) {
            String name = e.op;
            if (aliases != null && aliases.contains(name)) return;
            if (!cols.contains(name)) throw new Err("error: query: unknown column " + name);
            if (aggq && !inAgg && !(group != null && group.contains(name))) throw new Err("error: query: not grouped " + name);
            return;
        }
        if (k.equals("call") && !FUNCS.contains(e.op)) throw new Err("error: query: unknown function " + e.op);
        if (k.equals("agg")) {
            if (inWhere) throw new Err("error: query: aggregate in where");
            if (inAgg) throw new Err("error: query: nested aggregate");
            for (Node c : walk(e)) check(c, aliases, aggq, group, true, inWhere);
            return;
        }
        for (Node c : walk(e)) check(c, aliases, aggq, group, inAgg, inWhere);
    }

    static String tostr(Object v) {
        return v instanceof Long ? Long.toString((Long) v) : (String) v;
    }

    static Long cap(long v) {
        return Math.abs(v) > LIM ? null : Long.valueOf(v);
    }

    static Object calc(String op, Object a, Object b) {
        if (!(a instanceof Long) || !(b instanceof Long)) return null;
        long x = (Long) a, y = (Long) b;
        switch (op) {
            case "+": return cap(x + y);
            case "-": return cap(x - y);
            case "*":
                try {
                    return cap(Math.multiplyExact(x, y));
                } catch (ArithmeticException ex) {
                    return null;
                }
            default:
                if (y == 0) return null;
                return cap(Math.floorDiv(x, y));
        }
    }

    static boolean cmpvals(String op, Object a, Object b) {
        if (a == null || b == null) return false;
        int c;
        if (a instanceof Long && b instanceof Long) c = Long.compare((Long) a, (Long) b);
        else if (a instanceof String && b instanceof String) c = ((String) a).compareTo((String) b);
        else return op.equals("!=");
        switch (op) {
            case "=": return c == 0;
            case "!=": return c != 0;
            case "<": return c < 0;
            case "<=": return c <= 0;
            case ">": return c > 0;
            default: return c >= 0;
        }
    }

    static Object func(String name, List<Object> args) {
        if (args.size() != 1) return null;
        Object a = args.get(0);
        if (a == null) return null;
        String s = tostr(a);
        switch (name) {
            case "len": return Long.valueOf(s.length());
            case "upper": {
                StringBuilder sb = new StringBuilder();
                for (char c : s.toCharArray()) sb.append(c >= 'a' && c <= 'z' ? (char) (c - 32) : c);
                return sb.toString();
            }
            case "lower": {
                StringBuilder sb = new StringBuilder();
                for (char c : s.toCharArray()) sb.append(c >= 'A' && c <= 'Z' ? (char) (c + 32) : c);
                return sb.toString();
            }
            case "abs": return a instanceof Long ? (Object) Long.valueOf(Math.abs((Long) a)) : null;
            case "num":
                if (a instanceof Long) return a;
                return intText(s) ? (Object) Long.valueOf(Long.parseLong(s)) : null;
            default: return null;
        }
    }

    static class Ctx {
        Map<String, Object> row;
        List<Map<String, Object>> rows;
        Map<String, Object> rep;
    }

    static Object ev(Node e, Ctx ctx) {
        switch (e.k) {
            case "lit": return e.lit;
            case "col": return (ctx.row != null ? ctx.row : ctx.rep).get(e.op);
            case "neg": {
                Object v = ev(e.a, ctx);
                return v instanceof Long ? (Object) cap(-(Long) v) : null;
            }
            case "bin": return calc(e.op, ev(e.a, ctx), ev(e.b, ctx));
            case "call": {
                List<Object> vs = new ArrayList<>();
                for (Node a : e.args) vs.add(ev(a, ctx));
                return func(e.op, vs);
            }
            case "agg": return aggregate(e, ctx.rows);
            case "cmp": return cmpvals(e.op, ev(e.a, ctx), ev(e.b, ctx));
            case "txt": {
                Object a = ev(e.a, ctx), b = ev(e.b, ctx);
                if (a == null || b == null) return false;
                String x = tostr(a), y = tostr(b);
                return e.op.equals(K_HAS) ? x.contains(y) : e.op.equals(K_STARTS) ? x.startsWith(y) : x.endsWith(y);
            }
            case "isnull": return (ev(e.a, ctx) == null) != e.flag;
            case "in": {
                Object a = ev(e.a, ctx);
                for (Node x : e.args) if (cmpvals("=", a, ev(x, ctx))) return true;
                return false;
            }
            case "and": return (Boolean) ev(e.a, ctx) && (Boolean) ev(e.b, ctx);
            case "or": return (Boolean) ev(e.a, ctx) || (Boolean) ev(e.b, ctx);
            case "not": return !(Boolean) ev(e.a, ctx);
            default: throw new IllegalStateException(e.k);
        }
    }

    static Object aggregate(Node e, List<Map<String, Object>> rows) {
        if (e.star) return Long.valueOf(rows.size());
        List<Object> vals = new ArrayList<>();
        for (Map<String, Object> r : rows) {
            Ctx c = new Ctx();
            c.row = r;
            vals.add(ev(e.a, c));
        }
        if (e.op.equals("count")) {
            long n = 0;
            for (Object v : vals) if (v != null) n++;
            return Long.valueOf(n);
        }
        List<Long> nums = new ArrayList<>();
        for (Object v : vals) if (v instanceof Long) nums.add((Long) v);
        if (nums.isEmpty()) return null;
        long sum = 0, mn = nums.get(0), mx = nums.get(0);
        for (long v : nums) {
            sum += v;
            mn = Math.min(mn, v);
            mx = Math.max(mx, v);
        }
        switch (e.op) {
            case "sum": return cap(sum);
            case "min": return Long.valueOf(mn);
            case "max": return Long.valueOf(mx);
            default: return Long.valueOf(Math.floorDiv(2 * sum + nums.size(), 2L * nums.size()));
        }
    }

    static int rank(Object v) {
        return v instanceof Long ? 0 : v instanceof String ? 1 : 2;
    }

    static int cmpOrder(Object a, Object b) {
        int ra = rank(a), rb = rank(b);
        if (ra != rb) return ra < rb ? -1 : 1;
        if (ra == 2) return 0;
        if (ra == 0) return Long.compare((Long) a, (Long) b);
        int c = ((String) a).compareTo((String) b);
        return c < 0 ? -1 : c > 0 ? 1 : 0;
    }

    static String doQuery(String data, String q) {
        parseTable(data);
        List<Map<String, Object>> rows = allRows;
        Ast ast = new P(lex(q)).query();
        List<Item> items = new ArrayList<>();
        for (Item it : ast.items) {
            if (it.isStar) {
                for (String c : cols) {
                    Item x = new Item();
                    Node n = new Node();
                    n.k = "col";
                    n.op = c;
                    x.e = n;
                    items.add(x);
                }
            } else items.add(it);
        }
        List<String> group = ast.group;
        boolean aggq = group != null || ast.having != null;
        for (Item it : items) if (containsAgg(it.e)) aggq = true;
        for (Node o : ast.orderE) if (containsAgg(o)) aggq = true;
        for (Item it : ast.items) {
            if (it.isStar) {
                if (aggq) for (String c : cols) if (!(group != null && group.contains(c))) throw new Err("error: query: not grouped " + c);
            } else check(it.e, null, aggq, group, false, false);
        }
        if (ast.where != null) check(ast.where, null, false, null, false, true);
        if (group != null) for (String g : group) if (!cols.contains(g)) throw new Err("error: query: unknown column " + g);
        if (ast.having != null) check(ast.having, null, aggq, group, false, false);
        Set<String> aliases = new HashSet<>();
        for (Item it : items) if (it.alias != null) aliases.add(it.alias);
        for (Node o : ast.orderE) check(o, aliases, aggq, group, false, false);

        if (ast.where != null) {
            List<Map<String, Object>> kept = new ArrayList<>();
            for (Map<String, Object> r : rows) {
                Ctx c = new Ctx();
                c.row = r;
                if ((Boolean) ev(ast.where, c)) kept.add(r);
            }
            rows = kept;
        }
        List<Ctx> ctxs = new ArrayList<>();
        if (aggq) {
            if (group != null && !group.isEmpty()) {
                Map<String, List<Map<String, Object>>> buckets = new LinkedHashMap<>();
                for (Map<String, Object> r : rows) {
                    StringBuilder key = new StringBuilder();
                    for (String g : group) {
                        Object v = r.get(g);
                        key.append(v == null ? "n" : v instanceof Long ? "i" + v : "s" + v).append('\u0001');
                    }
                    buckets.computeIfAbsent(key.toString(), x -> new ArrayList<>()).add(r);
                }
                for (List<Map<String, Object>> b : buckets.values()) {
                    Ctx c = new Ctx();
                    c.rows = b;
                    c.rep = b.get(0);
                    ctxs.add(c);
                }
            } else {
                Ctx c = new Ctx();
                c.rows = rows;
                if (!rows.isEmpty()) c.rep = rows.get(0);
                else {
                    c.rep = new LinkedHashMap<>();
                    for (String n : cols) c.rep.put(n, null);
                }
                ctxs.add(c);
            }
            if (ast.having != null) {
                List<Ctx> kept = new ArrayList<>();
                for (Ctx c : ctxs) if ((Boolean) ev(ast.having, c)) kept.add(c);
                ctxs = kept;
            }
        } else {
            for (Map<String, Object> r : rows) {
                Ctx c = new Ctx();
                c.row = r;
                ctxs.add(c);
            }
        }
        List<String> labels = new ArrayList<>();
        for (int n = 0; n < items.size(); n++) {
            Item it = items.get(n);
            labels.add(it.alias != null ? it.alias : it.e.k.equals("col") ? it.e.op : "col" + (n + 1));
        }
        List<Object[]> out = new ArrayList<>(); // {vals, keys}
        for (Ctx c : ctxs) {
            Object[] vals = new Object[items.size()];
            Map<String, Object> aliasVals = new LinkedHashMap<>();
            for (int i = 0; i < vals.length; i++) {
                vals[i] = ev(items.get(i).e, c);
                if (items.get(i).alias != null) aliasVals.put(items.get(i).alias, vals[i]);
            }
            Object[] keys = new Object[ast.orderE.size()];
            for (int i = 0; i < keys.length; i++) {
                Node o = ast.orderE.get(i);
                keys[i] = o.k.equals("col") && aliasVals.containsKey(o.op) ? aliasVals.get(o.op) : ev(o, c);
            }
            out.add(new Object[] { vals, keys });
        }
        if (!ast.orderE.isEmpty()) {
            Collections.sort(out, (x, y) -> {
                Object[] kx = (Object[]) x[1], ky = (Object[]) y[1];
                for (int i = 0; i < kx.length; i++) {
                    int c = cmpOrder(kx[i], ky[i]);
                    if (ast.orderDesc.get(i)) c = -c;
                    if (c != 0) return c;
                }
                return 0;
            });
        }
        if (ast.limit >= 0 && out.size() > ast.limit) out = out.subList(0, (int) ast.limit);
        StringBuilder sb = new StringBuilder(String.join(OUTSEP, labels));
        for (Object[] row : out) {
            Object[] vals = (Object[]) row[0];
            sb.append('\n');
            for (int i = 0; i < vals.length; i++) {
                if (i > 0) sb.append(OUTSEP);
                if (vals[i] != null) sb.append(tostr(vals[i]));
            }
        }
        return sb.toString();
    }

    public static String query(String data, String q) {
        try {
            return doQuery(data, q);
        } catch (Err e) {
            return e.getMessage();
        }
    }
}
'''

GO = r'''
package queryd

import (
	"sort"
	"strconv"
	"strings"
)

const (
	sepC     = @SEP@
	outSep   = @OUTSEP@
	kSelect  = @K_SELECT@
	kWhere   = @K_WHERE@
	kGroup   = @K_GROUP@
	kHaving  = @K_HAVING@
	kOrder   = @K_ORDER@
	kLimit   = @K_LIMIT@
	kAsc     = @K_ASC@
	kDesc    = @K_DESC@
	kHas     = @K_HAS@
	kStarts  = @K_STARTS@
	kEnds    = @K_ENDS@
	hasLogic = @LOGIC@
	hasExpr  = @EXPR@
	hasAgg   = @AGG@
	lim      = int64(1000000000000000)
)

type qErr struct{ msg string }

func fail(m string) { panic(qErr{m}) }

func syntax() { fail("error: query: syntax") }

type val struct {
	kind int // 0 null, 1 number, 2 text
	n    int64
	s    string
}

var null = val{}

func num(n int64) val  { return val{kind: 1, n: n} }
func txt(s string) val { return val{kind: 2, s: s} }

func tostr(v val) string {
	if v.kind == 1 {
		return strconv.FormatInt(v.n, 10)
	}
	return v.s
}

var keywordSet = func() map[string]bool {
	ks := map[string]bool{kSelect: true, "as": true, kWhere: true, kLimit: true, kOrder: true, kAsc: true, kDesc: true}
	if hasLogic {
		for _, k := range []string{"and", "or", "not", kHas, kStarts, kEnds} {
			ks[k] = true
		}
	}
	if hasExpr {
		for _, k := range []string{"is", "null", "in"} {
			ks[k] = true
		}
	}
	if hasAgg {
		ks[kGroup] = true
		ks[kHaving] = true
	}
	return ks
}()

func isLow(c byte) bool { return c >= 'a' && c <= 'z' }
func isDig(c byte) bool { return c >= '0' && c <= '9' }

func goodName(s string) bool {
	if s == "" || !isLow(s[0]) {
		return false
	}
	for i := 0; i < len(s); i++ {
		if !isLow(s[i]) && !isDig(s[i]) && s[i] != '_' {
			return false
		}
	}
	return true
}

func allDig(s string) bool {
	for i := 0; i < len(s); i++ {
		if !isDig(s[i]) {
			return false
		}
	}
	return true
}

func intText(s string) bool {
	body := s
	if strings.HasPrefix(s, "-") {
		body = s[1:]
		if body == "0" {
			return false
		}
	}
	return len(body) >= 1 && len(body) <= 9 && allDig(body) && (len(body) == 1 || body[0] != '0')
}

type row map[string]val

func cellVal(c string) val {
	if c == "" {
		return null
	}
	if intText(c) {
		n, _ := strconv.ParseInt(c, 10, 64)
		return num(n)
	}
	return txt(c)
}

func parseTable(data string) ([]string, []row) {
	ls := strings.Split(data, "\n")
	if len(ls) > 0 && ls[len(ls)-1] == "" {
		ls = ls[:len(ls)-1]
	}
	if len(ls) == 0 {
		fail("error: table line 1: header")
	}
	names := strings.Split(ls[0], sepC)
	seen := map[string]bool{}
	for _, n := range names {
		if !goodName(n) || keywordSet[n] || seen[n] {
			fail("error: table line 1: header")
		}
		seen[n] = true
	}
	var rows []row
	for i := 1; i < len(ls); i++ {
		if ls[i] == "" {
			fail("error: table line " + strconv.Itoa(i+1) + ": blank")
		}
		cells := strings.Split(ls[i], sepC)
		if len(cells) != len(names) {
			fail("error: table line " + strconv.Itoa(i+1) + ": columns")
		}
		r := row{}
		for j, n := range names {
			r[n] = cellVal(cells[j])
		}
		rows = append(rows, r)
	}
	return names, rows
}

type tok struct{ kind, text string }

func lex(q string) []tok {
	var toks []tok
	i, n := 0, len(q)
	for i < n {
		c := q[i]
		switch {
		case c == ' ' || c == '\t' || c == '\n':
			i++
		case isLow(c):
			j := i
			for j < n && (isLow(q[j]) || isDig(q[j]) || q[j] == '_') {
				j++
			}
			toks = append(toks, tok{"name", q[i:j]})
			i = j
		case isDig(c):
			j := i
			for j < n && isDig(q[j]) {
				j++
			}
			t := q[i:j]
			if len(t) > 9 || (len(t) > 1 && t[0] == '0') {
				syntax()
			}
			toks = append(toks, tok{"num", t})
			i = j
		case c == '\'':
			j := i + 1
			var buf strings.Builder
			for {
				if j >= n || q[j] == '\n' {
					syntax()
				}
				if q[j] == '\'' {
					if j+1 < n && q[j+1] == '\'' {
						buf.WriteByte('\'')
						j += 2
						continue
					}
					break
				}
				buf.WriteByte(q[j])
				j++
			}
			toks = append(toks, tok{"str", buf.String()})
			i = j + 1
		case i+1 < n && (q[i:i+2] == "!=" || q[i:i+2] == "<=" || q[i:i+2] == ">="):
			toks = append(toks, tok{"sym", q[i : i+2]})
			i += 2
		case strings.IndexByte(",()*+-/=<>", c) >= 0:
			toks = append(toks, tok{"sym", string(c)})
			i++
		default:
			syntax()
		}
	}
	toks = append(toks, tok{"eof", ""})
	return toks
}

type node struct {
	k    string
	op   string
	lit  val
	a, b *node
	flag bool
	star bool
	args []*node
}

type item struct {
	isStar bool
	e      *node
	alias  string
}

type ast struct {
	items     []item
	where     *node
	having    *node
	group     []string
	hasGroup  bool
	orderE    []*node
	orderDesc []bool
	limit     int64
}

type parser struct {
	t []tok
	i int
}

func (p *parser) peek() tok { return p.t[p.i] }
func (p *parser) at(kind, text string) bool {
	x := p.t[p.i]
	return x.kind == kind && (text == "" || x.text == text)
}
func (p *parser) sym(s string) bool { return p.at("sym", s) }
func (p *parser) kw(s string) bool  { return p.at("name", s) }
func (p *parser) take() tok {
	x := p.t[p.i]
	p.i++
	return x
}
func (p *parser) need(kind, text string) tok {
	if !p.at(kind, text) {
		syntax()
	}
	return p.take()
}

func (p *parser) expr() *node {
	left := p.term()
	for hasExpr && (p.sym("+") || p.sym("-")) {
		op := p.take().text
		left = &node{k: "bin", op: op, a: left, b: p.term()}
	}
	return left
}

func (p *parser) term() *node {
	left := p.unary()
	for hasExpr && (p.sym("*") || p.sym("/")) {
		op := p.take().text
		left = &node{k: "bin", op: op, a: left, b: p.unary()}
	}
	return left
}

func (p *parser) unary() *node {
	if hasExpr && p.sym("-") {
		p.take()
		return &node{k: "neg", a: p.unary()}
	}
	return p.atom()
}

func isAgg(s string) bool {
	return s == "count" || s == "sum" || s == "min" || s == "max" || s == "avg"
}

func (p *parser) atom() *node {
	t := p.peek()
	switch {
	case t.kind == "num":
		p.take()
		n, _ := strconv.ParseInt(t.text, 10, 64)
		return &node{k: "lit", lit: num(n)}
	case t.kind == "str":
		p.take()
		return &node{k: "lit", lit: txt(t.text)}
	case t.kind == "sym" && t.text == "(" && hasExpr:
		p.take()
		e := p.expr()
		p.need("sym", ")")
		return e
	case t.kind == "name":
		if keywordSet[t.text] {
			syntax()
		}
		p.take()
		if hasExpr && p.sym("(") {
			p.take()
			var args []*node
			star := false
			if p.sym("*") {
				p.take()
				star = true
			} else if !p.sym(")") {
				args = append(args, p.expr())
				for p.sym(",") {
					p.take()
					args = append(args, p.expr())
				}
			}
			p.need("sym", ")")
			if isAgg(t.text) && hasAgg {
				ok := len(args) == 1
				if star {
					ok = t.text == "count"
				}
				if !ok {
					syntax()
				}
				n := &node{k: "agg", op: t.text, star: star}
				if !star {
					n.a = args[0]
				}
				return n
			}
			if star {
				syntax()
			}
			return &node{k: "call", op: t.text, args: args}
		}
		return &node{k: "col", op: t.text}
	}
	syntax()
	return nil
}

func (p *parser) cond() *node {
	left := p.andc()
	for hasLogic && p.kw("or") {
		p.take()
		left = &node{k: "or", a: left, b: p.andc()}
	}
	return left
}

func (p *parser) andc() *node {
	left := p.notc()
	for hasLogic && p.kw("and") {
		p.take()
		left = &node{k: "and", a: left, b: p.notc()}
	}
	return left
}

func (p *parser) tryParen() (res *node) {
	save := p.i
	defer func() {
		if r := recover(); r != nil {
			if _, ok := r.(qErr); ok {
				p.i = save
				res = nil
				return
			}
			panic(r)
		}
	}()
	p.take()
	c := p.cond()
	p.need("sym", ")")
	return c
}

func (p *parser) notc() *node {
	if hasLogic && p.kw("not") {
		p.take()
		return &node{k: "not", a: p.notc()}
	}
	if hasLogic && p.sym("(") {
		if c := p.tryParen(); c != nil {
			return c
		}
	}
	return p.pred()
}

func (p *parser) pred() *node {
	left := p.expr()
	t := p.peek()
	if t.kind == "sym" && (t.text == "=" || t.text == "!=" || t.text == "<" || t.text == "<=" || t.text == ">" || t.text == ">=") {
		p.take()
		return &node{k: "cmp", op: t.text, a: left, b: p.expr()}
	}
	if hasLogic && t.kind == "name" && (t.text == kHas || t.text == kStarts || t.text == kEnds) {
		p.take()
		return &node{k: "txt", op: t.text, a: left, b: p.expr()}
	}
	if hasExpr && t.kind == "name" && t.text == "is" {
		p.take()
		neg := false
		if p.kw("not") {
			p.take()
			neg = true
		}
		p.need("name", "null")
		return &node{k: "isnull", a: left, flag: neg}
	}
	if hasExpr && t.kind == "name" && t.text == "in" {
		p.take()
		p.need("sym", "(")
		n := &node{k: "in", a: left}
		n.args = append(n.args, p.expr())
		for p.sym(",") {
			p.take()
			n.args = append(n.args, p.expr())
		}
		p.need("sym", ")")
		return n
	}
	syntax()
	return nil
}

func (p *parser) query() *ast {
	p.need("name", kSelect)
	a := &ast{limit: -1}
	if p.sym("*") {
		p.take()
		a.items = append(a.items, item{isStar: true})
	} else {
		for {
			it := item{e: p.expr()}
			if p.kw("as") {
				p.take()
				t := p.peek()
				if t.kind != "name" || keywordSet[t.text] {
					syntax()
				}
				it.alias = p.take().text
			}
			a.items = append(a.items, it)
			if p.sym(",") {
				p.take()
				continue
			}
			break
		}
	}
	if p.kw(kWhere) {
		p.take()
		a.where = p.cond()
	}
	if hasAgg && p.kw(kGroup) {
		p.take()
		a.hasGroup = true
		for {
			t := p.peek()
			if t.kind != "name" || keywordSet[t.text] {
				syntax()
			}
			a.group = append(a.group, p.take().text)
			if p.sym(",") {
				p.take()
				continue
			}
			break
		}
		if p.kw(kHaving) {
			p.take()
			a.having = p.cond()
		}
	}
	if p.kw(kOrder) {
		p.take()
		for {
			e := p.expr()
			desc := false
			if p.kw(kDesc) {
				p.take()
				desc = true
			} else if p.kw(kAsc) {
				p.take()
			}
			a.orderE = append(a.orderE, e)
			a.orderDesc = append(a.orderDesc, desc)
			if p.sym(",") {
				p.take()
				continue
			}
			break
		}
	}
	if p.kw(kLimit) {
		p.take()
		if p.peek().kind != "num" {
			syntax()
		}
		a.limit, _ = strconv.ParseInt(p.take().text, 10, 64)
	}
	if !p.at("eof", "") {
		syntax()
	}
	return a
}

func walk(e *node) []*node {
	switch e.k {
	case "bin", "cmp", "txt", "and", "or":
		return []*node{e.a, e.b}
	case "neg", "not", "isnull":
		return []*node{e.a}
	case "call":
		return e.args
	case "agg":
		if e.star {
			return nil
		}
		return []*node{e.a}
	case "in":
		return append([]*node{e.a}, e.args...)
	}
	return nil
}

func containsAgg(e *node) bool {
	if e.k == "agg" {
		return true
	}
	for _, c := range walk(e) {
		if containsAgg(c) {
			return true
		}
	}
	return false
}

func has(xs []string, x string) bool {
	for _, y := range xs {
		if y == x {
			return true
		}
	}
	return false
}

func isFunc(s string) bool {
	return s == "len" || s == "upper" || s == "lower" || s == "abs" || s == "num"
}

func check(e *node, cols []string, aliases map[string]bool, aggq bool, group []string, inAgg, inWhere bool) {
	switch e.k {
	case "col":
		if aliases != nil && aliases[e.op] {
			return
		}
		if !has(cols, e.op) {
			fail("error: query: unknown column " + e.op)
		}
		if aggq && !inAgg && !has(group, e.op) {
			fail("error: query: not grouped " + e.op)
		}
		return
	case "call":
		if !isFunc(e.op) {
			fail("error: query: unknown function " + e.op)
		}
	case "agg":
		if inWhere {
			fail("error: query: aggregate in where")
		}
		if inAgg {
			fail("error: query: nested aggregate")
		}
		for _, c := range walk(e) {
			check(c, cols, aliases, aggq, group, true, inWhere)
		}
		return
	}
	for _, c := range walk(e) {
		check(c, cols, aliases, aggq, group, inAgg, inWhere)
	}
}

func capv(v int64) val {
	if v > lim || v < -lim {
		return null
	}
	return num(v)
}

func floorDiv(a, b int64) int64 {
	q := a / b
	if a%b != 0 && (a < 0) != (b < 0) {
		q--
	}
	return q
}

func calc(op string, a, b val) val {
	if a.kind != 1 || b.kind != 1 {
		return null
	}
	x, y := a.n, b.n
	switch op {
	case "+":
		return capv(x + y)
	case "-":
		return capv(x - y)
	case "*":
		if x == 0 || y == 0 {
			return num(0)
		}
		ax, ay := x, y
		if ax < 0 {
			ax = -ax
		}
		if ay < 0 {
			ay = -ay
		}
		if ay > lim/ax {
			return null
		}
		return capv(x * y)
	}
	if y == 0 {
		return null
	}
	return capv(floorDiv(x, y))
}

func cmpvals(op string, a, b val) bool {
	if a.kind == 0 || b.kind == 0 {
		return false
	}
	var c int
	if a.kind == 1 && b.kind == 1 {
		switch {
		case a.n < b.n:
			c = -1
		case a.n > b.n:
			c = 1
		}
	} else if a.kind == 2 && b.kind == 2 {
		c = strings.Compare(a.s, b.s)
	} else {
		return op == "!="
	}
	switch op {
	case "=":
		return c == 0
	case "!=":
		return c != 0
	case "<":
		return c < 0
	case "<=":
		return c <= 0
	case ">":
		return c > 0
	}
	return c >= 0
}

func funcCall(name string, args []val) val {
	if len(args) != 1 || args[0].kind == 0 {
		return null
	}
	a := args[0]
	s := tostr(a)
	switch name {
	case "len":
		return num(int64(len(s)))
	case "upper":
		b := []byte(s)
		for i, c := range b {
			if c >= 'a' && c <= 'z' {
				b[i] = c - 32
			}
		}
		return txt(string(b))
	case "lower":
		b := []byte(s)
		for i, c := range b {
			if c >= 'A' && c <= 'Z' {
				b[i] = c + 32
			}
		}
		return txt(string(b))
	case "abs":
		if a.kind == 1 {
			if a.n < 0 {
				return num(-a.n)
			}
			return a
		}
		return null
	case "num":
		if a.kind == 1 {
			return a
		}
		if intText(s) {
			n, _ := strconv.ParseInt(s, 10, 64)
			return num(n)
		}
	}
	return null
}

type ctx struct {
	row  row
	rows []row
	rep  row
	grp  bool
}

func ev(e *node, c *ctx) val {
	switch e.k {
	case "lit":
		return e.lit
	case "col":
		if c.grp {
			return c.rep[e.op]
		}
		return c.row[e.op]
	case "neg":
		v := ev(e.a, c)
		if v.kind == 1 {
			return capv(-v.n)
		}
		return null
	case "bin":
		return calc(e.op, ev(e.a, c), ev(e.b, c))
	case "call":
		vs := make([]val, 0, len(e.args))
		for _, a := range e.args {
			vs = append(vs, ev(a, c))
		}
		return funcCall(e.op, vs)
	case "agg":
		return aggregate(e, c.rows)
	}
	return boolVal(evb(e, c))
}

// booleans are carried as numbers only inside evb; conditions never reach ev as values
func boolVal(b bool) val {
	if b {
		return num(1)
	}
	return num(0)
}

func evb(e *node, c *ctx) bool {
	switch e.k {
	case "cmp":
		return cmpvals(e.op, ev(e.a, c), ev(e.b, c))
	case "txt":
		a, b := ev(e.a, c), ev(e.b, c)
		if a.kind == 0 || b.kind == 0 {
			return false
		}
		x, y := tostr(a), tostr(b)
		switch e.op {
		case kHas:
			return strings.Contains(x, y)
		case kStarts:
			return strings.HasPrefix(x, y)
		}
		return strings.HasSuffix(x, y)
	case "isnull":
		return (ev(e.a, c).kind == 0) != e.flag
	case "in":
		a := ev(e.a, c)
		for _, x := range e.args {
			if cmpvals("=", a, ev(x, c)) {
				return true
			}
		}
		return false
	case "and":
		return evb(e.a, c) && evb(e.b, c)
	case "or":
		return evb(e.a, c) || evb(e.b, c)
	case "not":
		return !evb(e.a, c)
	}
	panic("bad condition " + e.k)
}

func aggregate(e *node, rows []row) val {
	if e.star {
		return num(int64(len(rows)))
	}
	var vals []val
	for _, r := range rows {
		vals = append(vals, ev(e.a, &ctx{row: r}))
	}
	if e.op == "count" {
		n := int64(0)
		for _, v := range vals {
			if v.kind != 0 {
				n++
			}
		}
		return num(n)
	}
	var nums []int64
	for _, v := range vals {
		if v.kind == 1 {
			nums = append(nums, v.n)
		}
	}
	if len(nums) == 0 {
		return null
	}
	sum, mn, mx := int64(0), nums[0], nums[0]
	for _, v := range nums {
		sum += v
		if v < mn {
			mn = v
		}
		if v > mx {
			mx = v
		}
	}
	switch e.op {
	case "sum":
		return capv(sum)
	case "min":
		return num(mn)
	case "max":
		return num(mx)
	}
	return num(floorDiv(2*sum+int64(len(nums)), 2*int64(len(nums))))
}

func rank(v val) int {
	switch v.kind {
	case 1:
		return 0
	case 2:
		return 1
	}
	return 2
}

func cmpOrder(a, b val) int {
	ra, rb := rank(a), rank(b)
	if ra != rb {
		if ra < rb {
			return -1
		}
		return 1
	}
	switch ra {
	case 2:
		return 0
	case 0:
		switch {
		case a.n < b.n:
			return -1
		case a.n > b.n:
			return 1
		}
		return 0
	}
	return strings.Compare(a.s, b.s)
}

func doQuery(data, q string) string {
	cols, rows := parseTable(data)
	a := newParser(q).query()
	var items []item
	for _, it := range a.items {
		if it.isStar {
			for _, c := range cols {
				items = append(items, item{e: &node{k: "col", op: c}})
			}
		} else {
			items = append(items, it)
		}
	}
	group := a.group
	aggq := a.hasGroup || a.having != nil
	for _, it := range items {
		if containsAgg(it.e) {
			aggq = true
		}
	}
	for _, o := range a.orderE {
		if containsAgg(o) {
			aggq = true
		}
	}
	for _, it := range a.items {
		if it.isStar {
			if aggq {
				for _, c := range cols {
					if !has(group, c) {
						fail("error: query: not grouped " + c)
					}
				}
			}
		} else {
			check(it.e, cols, nil, aggq, group, false, false)
		}
	}
	if a.where != nil {
		check(a.where, cols, nil, false, nil, false, true)
	}
	for _, g := range group {
		if !has(cols, g) {
			fail("error: query: unknown column " + g)
		}
	}
	if a.having != nil {
		check(a.having, cols, nil, aggq, group, false, false)
	}
	aliases := map[string]bool{}
	for _, it := range items {
		if it.alias != "" {
			aliases[it.alias] = true
		}
	}
	for _, o := range a.orderE {
		check(o, cols, aliases, aggq, group, false, false)
	}
	if a.where != nil {
		var kept []row
		for _, r := range rows {
			if evb(a.where, &ctx{row: r}) {
				kept = append(kept, r)
			}
		}
		rows = kept
	}
	var ctxs []*ctx
	if aggq {
		if len(group) > 0 {
			var keys []string
			buckets := map[string][]row{}
			for _, r := range rows {
				var kb strings.Builder
				for _, g := range group {
					v := r[g]
					switch v.kind {
					case 0:
						kb.WriteString("n")
					case 1:
						kb.WriteString("i" + strconv.FormatInt(v.n, 10))
					default:
						kb.WriteString("s" + v.s)
					}
					kb.WriteByte(1)
				}
				k := kb.String()
				if _, ok := buckets[k]; !ok {
					keys = append(keys, k)
				}
				buckets[k] = append(buckets[k], r)
			}
			for _, k := range keys {
				ctxs = append(ctxs, &ctx{rows: buckets[k], rep: buckets[k][0], grp: true})
			}
		} else {
			rep := row{}
			if len(rows) > 0 {
				rep = rows[0]
			} else {
				for _, c := range cols {
					rep[c] = null
				}
			}
			ctxs = []*ctx{{rows: rows, rep: rep, grp: true}}
		}
		if a.having != nil {
			var kept []*ctx
			for _, c := range ctxs {
				if evb(a.having, c) {
					kept = append(kept, c)
				}
			}
			ctxs = kept
		}
	} else {
		for _, r := range rows {
			ctxs = append(ctxs, &ctx{row: r})
		}
	}
	labels := make([]string, len(items))
	for n, it := range items {
		switch {
		case it.alias != "":
			labels[n] = it.alias
		case it.e.k == "col":
			labels[n] = it.e.op
		default:
			labels[n] = "col" + strconv.Itoa(n+1)
		}
	}
	type outRow struct {
		vals []val
		keys []val
	}
	var out []outRow
	for _, c := range ctxs {
		vals := make([]val, len(items))
		aliasVals := map[string]val{}
		for i, it := range items {
			vals[i] = ev(it.e, c)
			if it.alias != "" {
				aliasVals[it.alias] = vals[i]
			}
		}
		keys := make([]val, len(a.orderE))
		for i, o := range a.orderE {
			if v, ok := aliasVals[o.op]; ok && o.k == "col" {
				keys[i] = v
			} else {
				keys[i] = ev(o, c)
			}
		}
		out = append(out, outRow{vals, keys})
	}
	if len(a.orderE) > 0 {
		sort.SliceStable(out, func(x, y int) bool {
			for i := range a.orderE {
				c := cmpOrder(out[x].keys[i], out[y].keys[i])
				if a.orderDesc[i] {
					c = -c
				}
				if c != 0 {
					return c < 0
				}
			}
			return false
		})
	}
	if a.limit >= 0 && int64(len(out)) > a.limit {
		out = out[:a.limit]
	}
	lines := []string{strings.Join(labels, outSep)}
	for _, r := range out {
		cells := make([]string, len(r.vals))
		for i, v := range r.vals {
			if v.kind != 0 {
				cells[i] = tostr(v)
			}
		}
		lines = append(lines, strings.Join(cells, outSep))
	}
	return strings.Join(lines, "\n")
}

func newParser(q string) *parser { return &parser{t: lex(q)} }

// Query runs a query over a table and returns the result text.
func Query(data, q string) (res string) {
	defer func() {
		if r := recover(); r != nil {
			if e, ok := r.(qErr); ok {
				res = e.msg
				return
			}
			panic(r)
		}
	}()
	return doQuery(data, q)
}
'''



COLS = ["city", "qty", "name", "price", "tag", "stock", "size", "code", "kind", "owner", "note", "day", "dock", "crew"]
WORDS = ["Oslo", "bergen", "Tromso", "ann", "Bob", "cy", "dee", "net", "rope", "lamp", "salt tin", "a b", "x", "ZZ", "mixed Case", "007", "-0", "1.5", "12a", " 5", "5 ", "0x1", "+3", "it's", "a=b", "q?", "e-mail", "(x)"]
KW_CHOICES = {"select": ["show", "pick", "get"], "where": ["where", "when", "if"], "group": ["per", "bucket", "grouped"], "having": ["having", "keeping", "only"], "order": ["sort", "order", "rank"],
              "limit": ["limit", "top", "first"], "asc": ["asc", "up", "fwd"], "desc": ["desc", "down", "rev"], "has": ["has", "contains", "holds"], "starts": ["starts", "begins", "leads"], "ends": ["ends", "finishes", "trails"]}
THEMES = [("the tide-table spreadsheet", "The harbour office keeps its tide-table spreadsheet as plain delimited text."), ("the seed catalogue sheet", "The seed library exports its catalogue as plain delimited text."),
          ("the crew roster", "The ferry crew roster is a plain delimited table."), ("the lamp-oil ledger", "The lighthouse keeps a ledger of lamp oil as a delimited table.")]


def params(rng, level, i):
    kw = {k: rng.choice(v) for k, v in KW_CHOICES.items()}
    return {
        "level": level, "sep": rng.choice([",", ";", "|"]), "outsep": rng.choice([" | ", "\t", ";"]), "kw": kw, "logic": level >= 2, "expr": level >= 3, "agg": level >= 4, "theme": THEMES[(i + rng.randrange(2)) % len(THEMES)],
    }


def sol(lang, p):
    src = {"python": PY, "javascript": JS, "java": JV, "go": GO}[lang]
    L = lambda s: K.lit(lang, s)  # noqa: E731
    b = (lambda v: "True" if v else "False") if lang == "python" else (lambda v: "true" if v else "false")  # noqa: E731
    kw = p["kw"]
    return K.subst(
        src, SEP=L(p["sep"]), OUTSEP=L(p["outsep"]), K_SELECT=L(kw["select"]), K_WHERE=L(kw["where"]), K_GROUP=L(kw["group"]), K_HAVING=L(kw["having"]), K_ORDER=L(kw["order"]), K_LIMIT=L(kw["limit"]),
        K_ASC=L(kw["asc"]), K_DESC=L(kw["desc"]), K_HAS=L(kw["has"]), K_STARTS=L(kw["starts"]), K_ENDS=L(kw["ends"]), LOGIC=b(p["logic"]), EXPR=b(p["expr"]), AGG=b(p["agg"]),
    ).lstrip("\n")


def make_table(rng, p, ncols, nrows, nulls=0.12):
    cols = rng.sample(COLS, ncols)
    kinds = [rng.choice(["int", "int", "text", "mixed"]) for _ in cols]
    if "int" not in kinds:
        kinds[0] = "int"
    rows = []
    for _ in range(nrows):
        r = []
        for k in kinds:
            if rng.random() < nulls:
                r.append("")
            elif k == "int" or (k == "mixed" and rng.random() < 0.6):
                r.append(str(rng.choice([0, 1, 2, 3, 5, 7, 10, 25, -1, -4, 100, 999999999, -999999999, rng.randrange(-50, 500)])))
            else:
                r.append(rng.choice([w for w in WORDS if p["sep"] not in w]))
        rows.append(r)
    return cols, kinds, rows


def table_text(p, cols, rows, final_nl=True):
    return "\n".join([p["sep"].join(cols)] + [p["sep"].join(r) for r in rows]) + ("\n" if final_nl else "")


def sq(s):
    return "'" + s.replace("'", "''") + "'"


def lit_for(rng, rows, ci, kind):
    vals = [r[ci] for r in rows if r[ci] != ""]
    if vals and rng.random() < 0.8:
        v = rng.choice(vals)
        if v.lstrip("-").isdigit() and not (len(v.lstrip("-")) > 1 and v.lstrip("-")[0] == "0") and v != "-0" and len(v.lstrip("-")) <= 9 and rng.random() < 0.9:
            return str(abs(int(v))) if int(v) >= 0 else None
        return sq(v)
    return rng.choice(["0", "1", "5", "10", sq("a"), sq("Oslo"), "100"])


def gen_query(rng, p, cols, kinds, rows):
    kw = p["kw"]
    ints = [c for c, k in zip(cols, kinds) if k in ("int", "mixed")] or cols
    L = p["level"]

    def colref():
        return rng.choice(cols)

    def intcol():
        return rng.choice(ints)

    def literal(ci=None):
        ci = rng.randrange(len(cols)) if ci is None else ci
        v = lit_for(rng, rows, ci, kinds[ci])
        return v if v is not None else "0"

    def expr(depth=0):
        r = rng.random()
        if not p["expr"] or depth >= 2 or r < 0.45:
            return rng.choice([colref(), intcol(), str(rng.choice([0, 1, 2, 3, 10])), sq(rng.choice(["a", "x"]))]) if rng.random() < 0.9 else colref()
        if r < 0.7:
            return "(" + expr(depth + 1) + " " + rng.choice("+-*/") + " " + expr(depth + 1) + ")" if rng.random() < 0.5 else expr(depth + 1) + " " + rng.choice("+-*/") + " " + expr(depth + 1)
        if r < 0.78:
            return "-" + expr(depth + 1)
        return rng.choice(["len", "upper", "lower", "abs", "num"]) + "(" + expr(depth + 1) + ")"

    def pred():
        r = rng.random()
        c = colref()
        ci = cols.index(c)
        if r < 0.55 or not p["logic"]:
            lhs = expr() if p["expr"] and rng.random() < 0.5 else c
            return f"{lhs} {rng.choice(['=', '!=', '<', '<=', '>', '>='])} {literal(ci) if lhs == c else rng.choice(['0', '1', '5', sq('a')])}"
        if r < 0.7:
            return f"{c} {rng.choice([kw['has'], kw['starts'], kw['ends']])} {sq(rng.choice(['a', 'O', 'e', 'Oslo', 'x', '0', '']))}"
        if p["expr"] and r < 0.82:
            return f"{c} is {rng.choice(['', 'not '])}null"
        if p["expr"] and r < 0.92:
            return f"{c} in ({', '.join(literal(ci) for _ in range(rng.randint(1, 3)))})"
        return f"{c} = {literal(ci)}"

    def cond(depth=0):
        if not p["logic"] or depth >= 2 or rng.random() < 0.45:
            return pred()
        r = rng.random()
        if r < 0.35:
            return cond(depth + 1) + " and " + cond(depth + 1)
        if r < 0.7:
            return cond(depth + 1) + " or " + cond(depth + 1)
        if r < 0.85:
            return "not " + pred()
        return "(" + cond(depth + 1) + ")"

    if L >= 4 and rng.random() < 0.75:
        gcols = rng.sample(cols, rng.randint(1, min(2, len(cols))))
        aggs = []
        for _ in range(rng.randint(1, 3)):
            f = rng.choice(["count", "sum", "min", "max", "avg"])
            aggs.append("count(*)" if f == "count" and rng.random() < 0.5 else f"{f}({rng.choice(['qty', intcol(), colref()] if rng.random() < 0.3 else [intcol()])})")
        items = [rng.choice(gcols) if rng.random() < 0.8 else "-" ] if False else list(gcols)
        sel = ", ".join(items + [a + (f" as {rng.choice(['t', 'n', 'v'])}{k}" if rng.random() < 0.3 else "") for k, a in enumerate(aggs)])
        q = f"{kw['select']} {sel}"
        if rng.random() < 0.5:
            q += f" {kw['where']} {cond()}"
        q += f" {kw['group']} {', '.join(gcols)}"
        if rng.random() < 0.4:
            q += f" {kw['having']} {rng.choice(aggs)} {rng.choice(['>', '>=', '<', '=', '!='])} {rng.choice(['0', '1', '2', '10'])}"
        if rng.random() < 0.6:
            q += f" {kw['order']} {rng.choice(aggs + gcols)} {rng.choice(['', kw['desc'], kw['asc']])}".rstrip()
        if rng.random() < 0.3:
            q += f" {kw['limit']} {rng.randint(0, 4)}"
        return q
    if L >= 4 and rng.random() < 0.12:
        f = rng.choice(["count(*)", "sum(" + intcol() + ")", "avg(" + intcol() + ")", "max(" + intcol() + ")", "min(" + colref() + ")"])
        q = f"{kw['select']} {f}, count({colref()})"
        if rng.random() < 0.5:
            q += f" {kw['where']} {cond()}"
        return q
    if rng.random() < 0.15:
        sel = "*"
    else:
        n = rng.randint(1, 3)
        parts = []
        for k in range(n):
            e = expr() if p["expr"] and rng.random() < 0.5 else colref()
            if rng.random() < 0.25:
                e += f" as {rng.choice(['a', 'b', 'c', 'x1', 'out_' + str(k)])}"
            parts.append(e)
        sel = ", ".join(parts)
    q = f"{kw['select']} {sel}"
    if rng.random() < 0.7:
        q += f" {kw['where']} {cond()}"
    if rng.random() < 0.5:
        keys = []
        for _ in range(rng.randint(1, 2)):
            e = expr() if p["expr"] and rng.random() < 0.3 else colref()
            keys.append(e + rng.choice(["", " " + kw["desc"], " " + kw["asc"]]))
        q += f" {kw['order']} " + ", ".join(keys)
    if rng.random() < 0.3:
        q += f" {kw['limit']} {rng.randint(0, 6)}"
    return q


def make_cases(rng, p, ns):
    cases = []
    kw = p["kw"]
    L = p["level"]

    def add(t, q):
        cases.append((t, q))

    tables = []
    for _ in range(4):
        cols, kinds, rows = make_table(rng, p, rng.randint(2, 5), rng.randint(4, 12))
        tables.append((cols, kinds, rows))
    for cols, kinds, rows in tables:
        t = table_text(p, cols, rows, rng.random() < 0.7)
        for _ in range(26 if L >= 3 else 20):
            add(t, gen_query(rng, p, cols, kinds, rows))
    # fixed table for hand-written queries
    sp = p["sep"]
    rows = [["Oslo", "5", "Ann", "10"], ["Bergen", "", "Bob", "-4"], ["Oslo", "7", "Cy", "0"], ["Tromso", "10", "Dee", "25"], ["bergen", "3", "ann", ""], ["Oslo", "007", "Eli", "999999999"], ["Tromso", "-2", "", "1"]]
    cols = ["city", "qty", "name", "price"]
    base = table_text(p, cols, rows)
    S, W, Gp, H, O, Lm, A_, D = kw["select"], kw["where"], kw["group"], kw["having"], kw["order"], kw["limit"], kw["asc"], kw["desc"]
    qs = [f"{S} *", f"{S} city", f"{S} city, name", f"{S} name, city", f"{S} qty as q, qty as q", f"{S} city as c, name as c", f"{S} *  {W} qty > 5", f"{S} *\n{W}\tqty = 5", f"{S} name {W} qty < 5", f"{S} name {W} qty <= 5", f"{S} name {W} qty >= 7", f"{S} name {W} qty != 5",
          f"{S} name {W} city = 'Oslo'", f"{S} name {W} city = 'oslo'", f"{S} name {W} city != 'Oslo'", f"{S} name {W} city < 'Oslo'", f"{S} name {W} city > 'Oslo'", f"{S} name {W} qty = 'Oslo'", f"{S} name {W} qty != 'Oslo'", f"{S} name {W} qty < 'Oslo'", f"{S} name {W} city = 5", f"{S} name {W} city != 5",
          f"{S} name {W} 5 < qty", f"{S} name {W} qty = qty", f"{S} name {W} qty < price", f"{S} name {W} name = ''", f"{S} name {W} qty = 7", f"{S} name {W} qty = 007", f"{S} name {W} qty = 0", f"{S} name {W} price = 0", f"{S} qty {O} qty", f"{S} qty {O} qty {D}", f"{S} qty {O} qty {A_}", f"{S} city, qty {O} city, qty {D}",
          f"{S} city, qty {O} city {D}, qty", f"{S} name {O} price", f"{S} name {O} price {D}", f"{S} name {O} name", f"{S} name {O} name {D}", f"{S} name, city {O} city", f"{S} name {Lm} 0", f"{S} name {Lm} 1", f"{S} name {Lm} 3", f"{S} name {Lm} 100", f"{S} name {O} name {Lm} 2", f"{S} name {W} qty > 0 {O} name {D} {Lm} 3",
          f"{S} name {W} qty > 0 {Lm} 2 {O} name", f"{S} {S}", f"{S}", f"{S} ,", f"{S} name,", f"{S} name city", f"{S} name as", f"{S} name as {W}", f"{S} name as 5", f"{S} bogus", f"{S} name {W} bogus = 1", f"{S} name {O} bogus", f"{S} *, name", f"{S} 5", f"{S} 'x'", f"{S} 12345678901", f"{S} 007", f"{S} name {W} qty >", f"{S} name {W} > 5",
          f"{S} name {W} qty 5", f"{S} name {W} 5", f"{S} name {W} name", f"{S} name {Lm} x", f"{S} name {Lm} -1", f"{S} name {Lm} 1.5", f"{S} name {Lm} 1 2", f"{S} name {Lm}", f"{S} name {W} city = 'Oslo", f"{S} name {W} city = \"Oslo\"", f"{S} name {W} city = 'it''s'", f"{S} name {W} city = ''''", f"{S} name ;", f"{S} name # c", f"{S} name !", f"{S} name {W} qty ! 5",
          f"{S.upper()} name", f"{S} NAME", f"{S} Name", f"{S} name {W.upper()} qty = 5", f"  {S}   name  ", f"\n{S}\n name\n{W}\nqty = 5\n", "", " ", "name", f"{S} name {W} qty = 5 {W} qty = 6", f"{S} name {O} name {W} qty = 5", f"{S} name {Lm} 2 {Lm} 3", f"{S} name {O}", f"{S} name {O} name,", f"{S} name {O} {D}", f"{S} name {O} name {D} {A_}", f"{S} name {O} name {A_} {D}",
          f"{S} name {O} name {A_}", f"{S} name {W} qty > 5 {O} qty"]
    if p["logic"]:
        qs += [f"{S} name {W} qty > 4 and city = 'Oslo'", f"{S} name {W} qty > 6 or city = 'Bergen'", f"{S} name {W} not qty > 5", f"{S} name {W} not not qty > 5", f"{S} name {W} not (qty > 5)", f"{S} name {W} (qty > 5)", f"{S} name {W} ((qty > 5))", f"{S} name {W} qty > 4 and qty < 8 or city = 'Tromso'",
               f"{S} name {W} city = 'Tromso' or qty > 4 and qty < 8", f"{S} name {W} (city = 'Tromso' or qty > 4) and qty < 8", f"{S} name {W} not city = 'Oslo' and qty > 0", f"{S} name {W} not (city = 'Oslo' and qty > 0)", f"{S} name {W} city {kw['has']} 'o'", f"{S} name {W} city {kw['has']} ''", f"{S} name {W} city {kw['starts']} 'O'",
               f"{S} name {W} city {kw['starts']} 'o'", f"{S} name {W} city {kw['ends']} 'o'", f"{S} name {W} city {kw['ends']} 'en'", f"{S} name {W} qty {kw['has']} 0", f"{S} name {W} qty {kw['starts']} 0", f"{S} name {W} price {kw['ends']} 9", f"{S} name {W} name {kw['has']} city", f"{S} name {W} qty {kw['has']} price", f"{S} name {W} city {kw['has']}",
               f"{S} name {W} city {kw['has']} 'o' and", f"{S} name {W} and qty > 1", f"{S} name {W} qty > 1 and and qty < 5", f"{S} name {W} (qty > 1", f"{S} name {W} qty > 1)", f"{S} name {W} ()", f"{S} name {W} (qty > 5) > 1", f"{S} name {W} not", f"{S} name {W} qty > 5 or", f"{S} name {W} AND qty > 5", f"{S} name {W} qty > 5 And qty < 9",
               f"{S} name {W} city = 'Oslo' and name = ''", f"{S} name {W} (city = 'Oslo') or (city = 'Bergen')", f"{S} name {W} not (not (qty > 5))", f"{S} name {W} not not not qty > 5", f"{S} name {W} not qty = 5 or qty = 5"]
    else:
        qs += [f"{S} name {W} qty > 4 and city = 'Oslo'", f"{S} name {W} not qty > 5", f"{S} name {W} (qty > 5)", f"{S} name {W} city {kw['has']} 'o'", f"{S} name {W} qty is null", f"{S} name {W} qty in (5)"]
    if p["expr"]:
        qs += [f"{S} qty + 1", f"{S} qty - 1 as m", f"{S} qty * 2", f"{S} qty / 2", f"{S} qty / 0", f"{S} 0 / qty", f"{S} price / 3", f"{S} -price / 3", f"{S} price / -3", f"{S} -price", f"{S} - price", f"{S} --price", f"{S} -(price)", f"{S} 7 / 2, -7 / 2, 7 / -2, -7 / -2", f"{S} 1 + 2 * 3, (1 + 2) * 3, 10 - 2 - 3, 100 / 10 / 5, 2 * 3 / 4",
                f"{S} price * price", f"{S} price * price * price", f"{S} price + price + price", f"{S} price * qty", f"{S} qty + name", f"{S} name + 1", f"{S} city * 2", f"{S} 999999999 * 999999999", f"{S} 999999999 * 999999999 * 999999999", f"{S} 999999999 * 1000000", f"{S} 999999999 * 1000001", f"{S} 1000000 * 1000000 * 1000", f"{S} 1000000 * 1000000 * 1001",
                f"{S} 1000000 * 1000000 * 1000 + 1", f"{S} 1000000 * 1000000 * 1000 - 1", f"{S} -999999999 * 999999999 * 1000000", f"{S} 999999999 * 999999999 / 999999999", f"{S} len(name)", f"{S} len(qty)", f"{S} len(price)", f"{S} len(city) + len(name)", f"{S} upper(name)", f"{S} lower(city)", f"{S} upper(qty)", f"{S} lower(price) as p", f"{S} abs(price)",
                f"{S} abs(name)", f"{S} abs(-5), abs(0), abs(5)", f"{S} num(qty)", f"{S} num(city)", f"{S} num('12'), num('-12'), num('007'), num('1.5'), num(''), num(' 5'), num('-0'), num('1234567890'), num('123456789')", f"{S} len(), upper(), abs(1, 2)", f"{S} len(qty, price)", f"{S} len", f"{S} bogus(qty)", f"{S} len(bogus)", f"{S} len(bogus(qty))",
                f"{S} len(1", f"{S} len 1)", f"{S} len(*)", f"{S} (qty)", f"{S} ((qty + 1)) * 2", f"{S} (qty +) * 2", f"{S} qty +", f"{S} qty * * 2", f"{S} qty {W} qty is null", f"{S} qty {W} qty is not null", f"{S} qty {W} qty is", f"{S} qty {W} qty is not", f"{S} qty {W} qty is null null", f"{S} qty {W} qty is nil", f"{S} qty {W} (qty + 1) is null", f"{S} qty {W} qty / 0 is null",
                f"{S} name {W} city in ('Oslo', 'Bergen')", f"{S} name {W} city in ('Oslo')", f"{S} name {W} city in ()", f"{S} name {W} city in", f"{S} name {W} qty in (5, 7, 'x')", f"{S} name {W} qty in (5 7)", f"{S} name {W} qty in (5,)", f"{S} name {W} qty in (qty)", f"{S} name {W} qty in (price)", f"{S} name {W} city in (name)", f"{S} name {W} name in ('')", f"{S} name {W} qty + 1 in (6, 8)",
                f"{S} name {W} qty * 2 > price", f"{S} name {W} price / 2 >= 0", f"{S} name {W} len(name) = 3", f"{S} name {W} upper(city) = 'OSLO'", f"{S} name {W} lower(city) = lower('BERGEN')", f"{S} name {W} abs(price) > 5", f"{S} name {W} -qty < 0", f"{S} name {W} not qty is null", f"{S} name {O} qty * 2 {D}", f"{S} name, qty * 2 as dbl {O} dbl {D}", f"{S} name, qty * 2 as dbl {O} dbl", f"{S} name, price as qty {O} qty",
                f"{S} name as city {O} city", f"{S} name, price as p {O} p {D}, name", f"{S} name, upper(name) as u {O} u", f"{S} name {O} len(name), name", f"{S} name {O} len(name) {D}, name {D}", f"{S} name, qty / 2 as h {W} h > 1 {O} h", f"{S} qty as p, price as q {O} p, q {D}", f"{S} 1 as a {O} a", f"{S} 'x' as a, 5 as b, '' as c", f"{S} 'it''s'", f"{S} '' as e", f"{S} name {W} city = 'Oslo' {O} price {D} {Lm} 2"]
    else:
        qs += [f"{S} qty + 1", f"{S} len(name)", f"{S} name {W} qty is null", f"{S} name {W} qty in (5)", f"{S} (qty)", f"{S} -qty", f"{S} qty * 2", f"{S} name {W} qty + 1 > 5", f"{S} name {W} len(name) = 3"]
    if p["agg"]:
        qs += [f"{S} count(*)", f"{S} count(qty)", f"{S} count(name), count(city), count(price)", f"{S} sum(qty)", f"{S} sum(price)", f"{S} min(qty), max(qty)", f"{S} min(price), max(price)", f"{S} avg(qty)", f"{S} avg(price)", f"{S} min(name)", f"{S} max(city)", f"{S} sum(name)", f"{S} avg(name)", f"{S} sum(qty * 2)", f"{S} sum(qty) + 1", f"{S} sum(qty) / count(*)",
               f"{S} count(*) {W} qty > 100", f"{S} sum(qty) {W} qty > 100", f"{S} min(qty), max(qty), avg(qty), count(qty), count(*) {W} qty > 100", f"{S} count(*) {W} name = 'nobody'", f"{S} count(*) as n, sum(qty) as s", f"{S} count(*) {W} qty > 4", f"{S} count(*) {W} count(*) > 1", f"{S} city {Gp} city", f"{S} city, count(*) {Gp} city", f"{S} city, count(*) as n {Gp} city {O} n {D}",
               f"{S} city, count(*) as n {Gp} city {O} n {D}, city", f"{S} city, count(*) as n {Gp} city {O} n, city {D}", f"{S} city, sum(qty), avg(qty), min(price), max(price) {Gp} city", f"{S} city, sum(price) {Gp} city {O} city", f"{S} city, count(*) {Gp} city {H} count(*) > 1", f"{S} city, count(*) {Gp} city {H} count(*) >= 3", f"{S} city, count(*) {Gp} city {H} sum(qty) > 10",
               f"{S} city, count(*) {Gp} city {H} avg(price) > 0", f"{S} city, count(*) {Gp} city {H} city = 'Oslo'", f"{S} city, count(*) {Gp} city {H} count(*) > 1 and sum(qty) > 0", f"{S} city {Gp} city {H} count(*) > 1", f"{S} {Gp} city", f"{S} city {Gp}", f"{S} city {Gp} city,", f"{S} city {Gp} bogus", f"{S} city {Gp} 5", f"{S} city {Gp} {W} qty > 1", f"{S} city {W} qty > 1 {Gp} city",
               f"{S} city {Gp} city {H}", f"{S} city {H} count(*) > 1", f"{S} city, qty {Gp} city", f"{S} qty {Gp} city", f"{S} * {Gp} city", f"{S} * {Gp} city, qty, name, price", f"{S} name {Gp} name", f"{S} name, count(*) {Gp} name {O} name", f"{S} city, name, count(*) {Gp} city, name", f"{S} city, name, count(*) {Gp} name, city {O} city, name", f"{S} price, count(*) {Gp} price {O} price {D}",
               f"{S} qty, count(*) {Gp} qty", f"{S} count(count(*))", f"{S} sum(sum(qty))", f"{S} sum(count(*))", f"{S} count()", f"{S} sum()", f"{S} sum(*)", f"{S} count(*, qty)", f"{S} count(qty, price)", f"{S} min(*)", f"{S} sum(qty", f"{S} avg", f"{S} count", f"{S} city, count(*) {Gp} city {O} count(*)", f"{S} city, count(*) {Gp} city {O} count(*) {D}, city", f"{S} city {Gp} city {O} sum(qty)", f"{S} city {Gp} city {O} qty",
               f"{S} city {Gp} city {O} bogus", f"{S} city, sum(qty) as total {Gp} city {O} total {D}", f"{S} city, sum(qty) as total {Gp} city {H} total > 3", f"{S} city, count(*) {Gp} city {Lm} 2", f"{S} city, count(*) {Gp} city {O} city {Lm} 1", f"{S} city, avg(qty) {Gp} city {O} avg(qty)", f"{S} city, avg(price) as a {Gp} city {O} a {D}", f"{S} count(*) {O} count(*)", f"{S} count(*) {Lm} 0",
               f"{S} city, sum(qty) + count(*) as z {Gp} city", f"{S} city, upper(city) {Gp} city", f"{S} len(city), count(*) {Gp} city", f"{S} city, sum(len(name)) {Gp} city", f"{S} city, max(len(name)) {Gp} city", f"{S} city, sum(qty) {Gp} city {H} sum(qty) is null", f"{S} city, sum(qty) {Gp} city {H} not sum(qty) is null", f"{S} city, count(*) {Gp} city {H} count(qty) = 0", f"{S} count(*) {W} sum(qty) > 1", f"{S} city {Gp} qty"]
    else:
        qs += [f"{S} count(*)", f"{S} sum(qty)", f"{S} city {Gp} city", f"{S} {Gp}", f"{S} count(*) {Gp} city"]
    for q in qs:
        add(base, q)
    # tiny / empty tables
    head = sp.join(cols)
    for t in [head, head + "\n", head + "\n\n", head + "\n" + sp.join(["a", "1", "b", "2"]) + "\n\n", head + "\n" + sp.join(["a", "1", "b"]), head + "\n" + sp.join(["a", "1", "b", "2", "3"]), "", "\n", "\n\n", sp.join(["a"]), sp.join(["a"]) + "\nx\n", sp.join(["a"]) + "\n1\n\n3", sp.join(["a", "a"]) + "\n1" + sp + "2", sp.join(["A", "b"]) + "\n1" + sp + "2",
              sp.join(["a", "1b"]) + "\n1" + sp + "2", sp.join(["a", ""]) + "\n1" + sp + "2", sp.join(["a", "b c"]) + "\n1" + sp + "2", sp.join([kw["select"], "b"]) + "\n1" + sp + "2", sp.join(["a", "as"]) + "\n1" + sp + "2", sp.join(["a", kw["where"]]) + "\n1" + sp + "2", sp.join(["a", kw["limit"]]) + "\n1" + sp + "2", sp.join(["a", "and"]) + "\n1" + sp + "2",
              sp.join(["a", "null"]) + "\n1" + sp + "2", sp.join(["a", "is"]) + "\n1" + sp + "2", sp.join(["a", "in"]) + "\n1" + sp + "2", sp.join(["a", kw["has"]]) + "\n1" + sp + "2", sp.join(["a", kw["group"]]) + "\n1" + sp + "2", sp.join(["a", kw["having"]]) + "\n1" + sp + "2", sp.join(["a", "count"]) + "\n1" + sp + "2", sp.join(["a", "len"]) + "\n1" + sp + "2", sp.join(["a", "b"]) + "\n" + sp.join(["1", "2"]) + "\n" + sp.join(["3", "4"]) + "\r\n"]:
        add(t, f"{S} *")
        add(t, f"{S} a")
        if p["agg"]:
            add(t, f"{S} count(*), sum(a)")
    # number cell formats
    nums = ["0", "-0", "00", "01", "-1", "-01", "1", "123456789", "1234567890", "-123456789", "-1234567890", "+1", "1.0", "1e3", " 1", "1 ", "0x10", "٣"[:0] + "9"]
    t = sp.join(["v"]) + "\n" + "\n".join(nums) + "\n"
    for q in [f"{S} v", f"{S} v {W} v = 0", f"{S} v {W} v = '0'", f"{S} v {O} v", f"{S} v {W} v > 5", f"{S} v {W} v < 'a'", f"{S} v {W} v {kw['has']} '1'" if p["logic"] else f"{S} v {W} v != 0"]:
        add(t, q)
        if p["expr"]:
            add(t, f"{S} v + 1, len(v), upper(v), abs(v), num(v)")
        if p["agg"]:
            add(t, f"{S} count(*), count(v), sum(v), min(v), max(v), avg(v)")
    if p["agg"]:
        t2 = sp.join(["k", "v"]) + "\n" + "\n".join([sp.join(r) for r in [["a", "1"], ["a", "2"], ["b", "-3"], ["b", "-4"], ["c", ""], ["", "5"], ["", "6"], ["a", "x"], ["c", "7"], ["d", "-1"], ["d", "-2"]]]) + "\n"
        for q in [f"{S} k, avg(v) {Gp} k", f"{S} k, sum(v), min(v), max(v), count(v), count(*) {Gp} k", f"{S} k, count(*) {Gp} k {O} k", f"{S} k, count(*) {Gp} k {O} k {D}", f"{S} k, avg(v) as m {Gp} k {O} m", f"{S} avg(v), sum(v)", f"{S} k, avg(v) {Gp} k {H} avg(v) < 0", f"{S} k, avg(v) {Gp} k {H} avg(v) is null"]:
            add(t2, q)
    # examples first
    ex = []
    ex.append((table_text(p, ["city", "qty", "name"], [["Oslo", "5", "Ann"], ["Bergen", "", "Bob"], ["Oslo", "7", "Cy"]]), f"{S} name, city {W} qty > 5"))
    ex.append((table_text(p, ["city", "qty", "name"], [["Oslo", "5", "Ann"], ["Bergen", "", "Bob"], ["Oslo", "7", "Cy"]]), f"{S} *  {O} qty {D}"))
    if p["logic"]:
        ex.append((table_text(p, ["city", "qty", "name"], [["Oslo", "5", "Ann"], ["Bergen", "", "Bob"], ["Oslo", "7", "Cy"]]), f"{S} name {W} not (city = 'Oslo' and qty > 5) or name {kw['starts']} 'B'"))
    if p["expr"]:
        ex.append((table_text(p, ["city", "qty", "name"], [["Oslo", "5", "Ann"], ["Bergen", "", "Bob"], ["Oslo", "7", "Cy"]]), f"{S} upper(name) as n, qty * 2, qty {kw['limit'] if False else ''}".rstrip() + f" {W} qty is not null"))
    if p["agg"]:
        ex.append((table_text(p, ["city", "qty", "name"], [["Oslo", "5", "Ann"], ["Bergen", "", "Bob"], ["Oslo", "7", "Cy"]]), f"{S} city, count(*), avg(qty) {Gp} city {O} city"))
    nex = len(ex)
    out, seen = [], set()
    for c in ex + cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex


def readme(p, api, lang, examples):
    kw = p["kw"]
    sep = p["sep"]
    osep = {" | ": "` | ` (a space, a vertical bar, a space)", "\t": "a single tab character", ";": "a semicolon"}[p["outsep"]]
    X = [f"# Table queries for {p['theme'][0]}", ""]
    X.append(f"{p['theme'][1]} `query(data, q)` runs a small query written in the house query language over such a table and returns the result as text.")
    X.append("")
    X.append("## The table")
    X.append("")
    X.append(f"`data` is text made of lines separated by `\\n` (one final `\\n` is allowed). The first line is the header: column names separated by `{sep}`. Every further line is a row with the same number of cells, also separated by `{sep}`. A cell is never quoted: it is the text between two separators (a cell cannot contain `{sep}`).")
    X.append("")
    X.append("* A column name is a lower-case ASCII letter followed by lower-case letters, digits or `_`; names are unique; a name may not be one of the query keywords (" + ", ".join(f"`{k}`" for k in sorted(KEYWORD_LIST(p))) + ").")
    X.append("* An **empty cell is null**. A cell that is a whole number is a **number**: an optional `-`, then 1 to 9 digits without leading zeros (so `0`, `-12` and `999999999` are numbers; `007`, `-0`, `+3`, `1.5`, ` 5` and `5 ` are not). Every other cell is **text**, exactly as written.")
    X.append("")
    X.append("A table problem is reported as `error: table line N: WHY` (`N` counts lines from 1, the header being line 1), for the first line that has one: `header` (no lines at all, an invalid or repeated or keyword column name), `blank` (an empty line before the end: an empty line is never a row), `columns` (a row with the wrong number of cells).")
    X.append("")
    X.append("## The query language")
    X.append("")
    clauses = [f"`{kw['select']}` *items*"]
    X.append("A query is one line of text (spaces, tabs and newlines may separate tokens freely):")
    X.append("")
    X.append("```")
    X.append(f"{kw['select']} ITEMS [{kw['where']} COND]" + (f" [{kw['group']} NAME, ... [{kw['having']} COND]]" if p["agg"] else "") + f" [{kw['order']} KEY [{kw['asc']}|{kw['desc']}], ...] [{kw['limit']} N]")
    X.append("```")
    X.append("")
    X.append("The clauses appear in this order, each at most once. Keywords are lower-case and are whole words; they cannot be used as column names or aliases.")
    X.append("")
    X.append("**Tokens.** Names (`[a-z][a-z0-9_]*`), whole numbers (digits only, at most 9 digits, no leading zeros unless the number is `0`), text literals in single quotes (`'abc'`; a quote inside is written twice: `'it''s'`; a literal may not contain a newline) and the symbols `, ( ) * " + ("+ - / " if p["expr"] else "") + "= != < <= > >=`. Anything else, such as upper-case letters, `\"`, `;` or a lone `!`, is a syntax error.")
    X.append("")
    X.append(f"**Items.** `*` selects every column in table order. Otherwise a comma-separated list of items, each " + ("an expression" if p["expr"] else "a column name, a number or a text literal") + f", optionally followed by `as NAME` giving it a label. The result header has one label per item: the `as` name, else the column name if the item is just a column, else `colN` where `N` is the item's position counted from 1 (after `*` is expanded).")
    X.append("")
    if p["expr"]:
        X.append("**Expressions** are built from column names, number literals, text literals, `( )`, unary `-`, the operators `*` `/` (binding tighter) and `+` `-`, left to right, and function calls `len(x)`, `upper(x)`, `lower(x)`, `abs(x)`, `num(x)`" + (", plus the aggregates below" if p["agg"] else "") + ". A function name that is not in this list is `error: query: unknown function NAME`.")
        X.append("")
        X.append("Values are *numbers*, *text* or *null*. Arithmetic needs numbers on both sides (a number, never text or null) and gives null otherwise. It is exact on whole numbers: `+ - *` give the exact result, `/` rounds **down** (towards minus infinity: `-7 / 2` is `-4`) and `/ 0` gives null; **any result whose absolute value is above 10^15 (1000000000000000) is null** instead. Unary `-` of a number is its negative, of anything else null.")
        X.append("")
        X.append("* `len(x)`: the number of characters of `x` (a number counts as its decimal text); null for null. `upper(x)`, `lower(x)`: ASCII letters changed to upper or lower case (a number is turned into its decimal text first); null for null. `abs(x)`: the absolute value of a number, null for anything else. `num(x)`: a number stays itself, a text that is a whole number (in the sense of the table cells) becomes that number, anything else is null. A function called with the wrong number of arguments gives null.")
        X.append("")
    X.append("**Conditions** (after `" + kw["where"] + "`" + (f" and `{kw['having']}`" if p["agg"] else "") + ") are " + ("built from comparisons " if p["logic"] else "a single comparison ") + "`A op B` with `op` one of `=`, `!=`, `<`, `<=`, `>`, `>=`, where `A` and `B` are " + ("expressions" if p["expr"] else "column names, numbers or text literals") + ". "
             "A comparison with null on either side is **false** (even `!=`). Two numbers compare numerically, two texts compare bytewise (ASCII order, `'Z'` before `'a'`); a number against a text is false for every operator except `!=`, which is true.")
    if p["logic"]:
        X.append("")
        X.append(f"Conditions combine with `not` (strongest), `and`, `or` (weakest), and parentheses `( )`; `and`/`or` associate to the left. Further tests: `A {kw['has']} B` (A contains B), `A {kw['starts']} B`, `A {kw['ends']} B`: both sides are turned into text first (numbers into decimal text); false if either is null; case-sensitive.")
    if p["expr"]:
        X.append(f"`A is null` and `A is not null` test for null. `A in (E1, E2, ...)` is true if `A = Ei` (the comparison above) holds for some `Ei`.")
    if p["logic"]:
        X.append("A parenthesis at the start of a condition is first tried as a parenthesised condition; if that does not parse, it is read as the start of a comparison. Conditions are two-valued: `not` of a false comparison is true.")
    X.append("")
    X.append(f"**Rows.** `{kw['where']}` keeps the rows whose condition is true. `{kw['order']}` sorts by the keys (expressions" + (", or the label of an item given with `as`" if True else "") + f") from left to right, each ascending (default, or `{kw['asc']}`) or descending (`{kw['desc']}`); numbers sort before text and null sorts after everything when ascending (so first when descending); texts compare bytewise; the sort is **stable**. "
             f"`{kw['limit']} N` keeps the first N rows after sorting (`N` a number literal).")
    if p["agg"]:
        X.append("")
        X.append("**Aggregates.** `count(*)` counts rows, `count(x)` counts the rows where `x` is not null; `sum(x)`, `min(x)`, `max(x)`, `avg(x)` use only the rows where `x` is a *number* (text and null are ignored) and give null when there is none. `sum` is exact but null if its absolute value is above 10^15; `avg` is the average **rounded to a whole number, halves going up** (exactly: `floor((2*sum + n) / (2*n))`). An aggregate may not be nested inside another aggregate or used in a `" + kw["where"] + "` condition.")
        X.append("")
        X.append(f"A query is an *aggregate query* if it has a `{kw['group']}` clause or uses an aggregate anywhere (items, `{kw['having']}`, `{kw['order']}`). Rows are first filtered by `{kw['where']}`; with `{kw['group']} a, b` the remaining rows are grouped by the values of those columns (null is a value of its own, groups appear in order of their first row), without it all rows form one group (even if there are none: then `count` is 0 and the other aggregates are null, and the result has exactly one row). "
                 f"The result has one row per group. In an aggregate query a column may only be used inside an aggregate or if it is named in `{kw['group']}`; `{kw['having']}` keeps the groups whose condition is true; `*` stands for all columns, which must all be grouped.")
    X.append("")
    X.append("## Result and errors")
    X.append("")
    X.append(f"The result is the header line followed by one line per row, joined by `\\n` without a trailing newline. In each line the cells are joined by {osep}: numbers in decimal, text as is, null as nothing. A query with no matching rows gives just the header line.")
    X.append("")
    X.append("Problems are reported instead of a result, the first applying in this order:")
    X.append("")
    X.append("1. the table problems above;")
    X.append("2. `error: query: syntax`: the query does not follow the grammar (including bad tokens, a missing or extra part, a keyword used as a name, a trailing token, or a call such as `sum(*)`);")
    names = ["`error: query: unknown column NAME`", "`error: query: unknown function NAME`"] + (["`error: query: not grouped NAME`", "`error: query: nested aggregate`", "`error: query: aggregate in where`"] if p["agg"] else [])
    X.append("3. then the clauses are checked in the order they are written (items, " + kw["where"] + (f", {kw['group']} names, {kw['having']}" if p["agg"] else "") + f", {kw['order']}; inside a clause the expressions are walked from left to right, a function or aggregate call being examined before its arguments), reporting the first of " + ", ".join(names) + ". A name used in `" + kw["order"] + "` that is the label of an item given with `as` is that item, not a column.")
    X.append("")
    X.append(K.interface_section(api, lang))
    X.append("## Examples")
    X.append("")
    for k, ((t, q), out) in enumerate(examples):
        X.append(f"**Example {k + 1}** (query `{q}`)")
        X.append("")
        X.append("```")
        X.append("table:")
        X += ["  " + ln.replace("\t", "<TAB>") for ln in t.rstrip("\n").split("\n")]
        X.append("result:")
        X += ["  " + ln.replace("\t", "<TAB>") for ln in out.split("\n")]
        X.append("```")
        X.append("")
    if p["outsep"] == "\t":
        X.append("(`<TAB>` stands for a tab character in the examples above.)")
        X.append("")
    X.append(K.run_hint(lang, api.mod))
    return "\n".join(X) + "\n"


def KEYWORD_LIST(p):
    kw = p["kw"]
    ks = {kw["select"], "as", kw["where"], kw["limit"], kw["order"], kw["asc"], kw["desc"]}
    if p["logic"]:
        ks |= {"and", "or", "not", kw["has"], kw["starts"], kw["ends"]}
    if p["expr"]:
        ks |= {"is", "null", "in"}
    if p["agg"]:
        ks |= {kw["group"], kw["having"]}
    return ks


def prompt(rng, p, api, lang):
    where = api.short(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    feats = ["projection, filtering, sorting and limits"] + (["boolean conditions and text tests"] if p["logic"] else []) + (["expressions, functions and null handling"] if p["expr"] else []) + (["grouping, aggregates and having"] if p["agg"] else [])
    fl = "; ".join(feats)
    opts = [
        f"{p['theme'][0].capitalize()} needs a tiny query engine. Write `{fn}(data, q)` in {ln}, in {where}, as README.md describes: {fl}. {K.closer(rng)}",
        f"Implement the query language from README.md in {ln} (`{fn}`, {where}). This version covers {fl}; the error order and the null/number/text comparison rules are part of the spec. {K.closer(rng)}",
        f"{ln} task: a small SQL-ish query evaluator with an invented syntax. `{fn}` in {where}; README.md defines the table format, the grammar, the semantics and the errors. Features: {fl}.",
        f"Please build `{fn}` ({ln}, {where}) from README.md. It runs queries over delimited text tables ({fl}). Hidden checks include malformed queries and awkward cell values.",
    ]
    return rng.choice(opts).strip()


LANG_PLAN = ["javascript", "java", "go", "python", "javascript", "java", "go", "java"]
LEVELS = [1, 1, 2, 2, 3, 3, 4, 4]


@family("greenfield-queryd", category="greenfield", lang="mixed", kind="greenfield", n=8,
        summary="query engine over delimited text tables: invented keywords, typed null/number/text comparisons, boolean conditions, expressions with floor division and a 10^15 cap, grouping and aggregates, ordered error reporting")
def gen(rng, n):
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = LEVELS[i % len(LEVELS)]
        p = params(rng, level, i)
        api = K.Api(mod="queryd", fn="query", args=["data", "q"], arg_docs=["the table text (header line, then rows)", "the query text"], ret_doc="the result table as text, or an error text", doc="query engine over delimited text tables")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["query"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=level, slug=f"{i + 1:02d}-{lang}-{ {',': 'comma', ';': 'semi', '|': 'pipe'}[p['sep']] }-l{level}", oracle=(None if lang == "python" else ns["query"]),
            tags=["query", "parser", "interpreter"], notes={"level": level, "sep": p["sep"]},
        )
