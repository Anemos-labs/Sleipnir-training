"""Python codemod application: a legacy helper module (`oldkit`) used in dozens of modules in many call shapes, a complete new API
(`kit`), and the migrated versions of every module.  Everything is synthesised from a seed; the new-style code is written
explicitly for each call shape, and the build proves that it prints exactly what the old code printed."""
from __future__ import annotations

import random

from generators.project import _cm_common as W

FALIAS = {"fmt_amount": "money", "pad_right": "rpad", "pad_left": "lpad", "parse_qty": "qty_of", "title": "nice", "sort_key": "skey", "pick": "dig_in",
          "take": "head", "group_by": "bucket", "log": "note", "flush_log": "drain_notes", "clamp": "bound"}


# ---------------------------------------------------------------------------------------------------------------
# the two APIs
# ---------------------------------------------------------------------------------------------------------------

def oldkit_source(p: dict) -> str:
    return f'''"""oldkit: the helper module this codebase has used so far.  It is being retired: see README.md."""
import re

_LOG = []
_QTY = re.compile(r"^\\s*([0-9]+)\\s*([A-Za-z]*)\\s*$")


def fmt_amount(cents, cur="{p['cur']}"):
    """12.50 EUR style text for an integer number of cents."""
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return "%s%d.%02d %s" % (sign, whole, frac, cur)


def parse_qty(text):
    """(count, unit) for texts like '12 kg', '3x' or '7' (unit defaults to '{p['unit']}'); None when the text is not a quantity."""
    m = _QTY.match(text)
    if not m:
        return None
    return int(m.group(1)), (m.group(2) or "{p['unit']}")


def pad_right(s, width):
    """Pad on the right (the text stays at the left)."""
    return s.ljust(width)


def pad_left(s, width):
    """Pad on the left (the text moves to the right)."""
    return s.rjust(width)


def title(s):
    {'return " ".join(w.capitalize() for w in s.split())' if p['title'] == 'each' else 'words = s.split()' + chr(10) + '    return " ".join(words[:1] + [w.lower() for w in words[1:]]).capitalize() if words else ""'}


def sort_key(s):
    return (s.lower(), s)


def pick(d, *keys, default=None):
    """Nested dictionary lookup: pick(cfg, "a", "b") is cfg["a"]["b"], or `default` when a key is missing."""
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def take(seq, n):
    return list(seq)[:n]


def group_by(items, keyfn):
    """dict: key -> list of items, keys in order of first appearance."""
    out = {{}}
    for it in items:
        out.setdefault(keyfn(it), []).append(it)
    return out


def log(level, msg, **ctx):
    """Append a line to the global log and return it: `{p['log'][0]}LEVEL{p['log'][1]} msg key=value ...` with the keys sorted."""
    line = "{p['log'][0]}%s{p['log'][1]} %s" % (level.upper(), msg) + "".join(" %s=%s" % (k, ctx[k]) for k in sorted(ctx))
    _LOG.append(line)
    return line


def flush_log():
    out = list(_LOG)
    del _LOG[:]
    return out


def clamp(x, lo, hi):
    return max(lo, min(hi, x))
'''


POISON = '''"""oldkit has been retired: every function fails."""


def _gone(*args, **kwargs):
    raise RuntimeError("oldkit has been retired; use the kit package")


fmt_amount = parse_qty = pad_right = pad_left = title = sort_key = pick = take = group_by = log = flush_log = clamp = _gone
'''


def kit_files(p: dict) -> dict[str, str]:
    t = p["title"]
    title_body = ('    return " ".join(w.capitalize() for w in s.split())' if t == "each" else
                  '    words = s.split()\n    return " ".join(words[:1] + [w.lower() for w in words[1:]]).capitalize() if words else ""')
    return {
        "kit/__init__.py": '"""kit: the shared helpers of the application (money, text, quantities, data, events)."""\nfrom . import data, events, money, qty, text  # noqa: F401\n',
        "kit/money.py": '''"""Money values."""


class Money:
    """An amount in cents of a currency; both are required."""

    def __init__(self, cents, cur):
        self.cents = cents
        self.cur = cur

    def text(self):
        sign = "-" if self.cents < 0 else ""
        whole, frac = divmod(abs(self.cents), 100)
        return "%s%d.%02d %s" % (sign, whole, frac, self.cur)
''',
        "kit/text.py": f'''"""Text helpers."""


def pad(s, width, *, align="left"):
    """Pad to `width`: align="left" keeps the text at the left (padding on the right), "right" moves it to the right."""
    if align == "left":
        return s.ljust(width)
    if align == "right":
        return s.rjust(width)
    raise ValueError("align must be 'left' or 'right'")


def title_case(s):
{title_body}


def sort_key(s):
    return (s.lower(), s)
''',
        "kit/qty.py": f'''"""Quantities such as '12 kg'."""
import re

_QTY = re.compile(r"^\\s*([0-9]+)\\s*([A-Za-z]*)\\s*$")


class QtyError(ValueError):
    pass


class Qty:
    def __init__(self, count, unit):
        self.count = count
        self.unit = unit

    @classmethod
    def parse(cls, text):
        """Qty for '12 kg', '3x' or '7' (unit defaults to '{p['unit']}'); raises QtyError otherwise."""
        m = _QTY.match(text)
        if not m:
            raise QtyError("not a quantity: %r" % (text,))
        return cls(int(m.group(1)), m.group(2) or "{p['unit']}")

    @classmethod
    def try_parse(cls, text):
        """Like parse, but returns None instead of raising."""
        try:
            return cls.parse(text)
        except QtyError:
            return None
''',
        "kit/data.py": '''"""Small data helpers."""


def dig(d, path, default=None):
    """Nested lookup along a tuple of keys; `default` when a key is missing."""
    cur = d
    for k in path:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def first(seq, n):
    return list(seq)[:n]


def group(items, key):
    """List of (key, [items]) pairs in order of first appearance of the keys."""
    order, buckets = [], {}
    for it in items:
        k = key(it)
        if k not in buckets:
            buckets[k] = []
            order.append(k)
        buckets[k].append(it)
    return [(k, buckets[k]) for k in order]


def limit(x, lo, hi):
    return max(lo, min(hi, x))
''',
        "kit/events.py": f'''"""Event lines."""


class Events:
    def __init__(self):
        self._lines = []

    def emit(self, level, msg, **ctx):
        """Record `{p['log'][0]}LEVEL{p['log'][1]} msg key=value ...` (keys sorted).  Returns nothing: see last()."""
        self._lines.append("{p['log'][0]}%s{p['log'][1]} %s" % (level.upper(), msg) + "".join(" %s=%s" % (k, ctx[k]) for k in sorted(ctx)))

    def last(self):
        return self._lines[-1]

    def drain(self):
        out = list(self._lines)
        del self._lines[:]
        return out


_DEFAULT = Events()


def default():
    """The process-wide Events instance."""
    return _DEFAULT
''',
    }


# ---------------------------------------------------------------------------------------------------------------
# module synthesis
# ---------------------------------------------------------------------------------------------------------------

class Imports:
    def __init__(self, style: str):
        self.style, self.used = style, set()

    def call(self, name: str) -> str:
        self.used.add(name)
        return {"plain": "oldkit." + name, "alias": "ok." + name, "from": name, "falias": FALIAS[name], "common": "common." + name}[self.style]

    def header(self) -> list[str]:
        used = sorted(self.used)
        if self.style == "plain":
            return ["import oldkit"]
        if self.style == "alias":
            return ["import oldkit as ok"]
        if self.style == "from":
            return ["from oldkit import " + ", ".join(used)]
        if self.style == "falias":
            return ["from oldkit import " + ", ".join(f"{n} as {FALIAS[n]}" for n in used)]
        return ["from app import common"]


class Mod:
    """One generated module: old and new source assembled from snippets."""

    def __init__(self, name: str, style: str, rng: random.Random, p: dict):
        self.name, self.rng, self.p = name, rng, p
        self.I = Imports(style)
        self.old: list[str] = []  # code blocks, old style
        self.new: list[str] = []  # code blocks, new style (same when the module goes through common)
        self.demos: list[str] = []
        self.uses_log = False
        self.uses_functools = False
        self.nouns = rng.sample(W.ITEMS, 6)
        self._names: set[str] = set()

    def fn(self, role: str) -> str:
        base = f"{self.name}_{role}"
        name, k = base, 1
        while name in self._names:
            k += 1
            name = f"{base}{k}"
        self._names.add(name)
        return name

    def const(self, role: str) -> str:
        base = f"{self.name.upper()}_{role}"
        name, k = base, 1
        while name in self._names:
            k += 1
            name = f"{base}{k}"
        self._names.add(name)
        return name

    def demo(self, label_fn: str, args: list[str]):
        for a in args:
            self.demos.append(f"out.append(\"{label_fn}({a.replace(chr(34), chr(39))}) = %r\" % ({label_fn}({a}),))")

    def source(self, new: bool) -> str:
        common = self.I.style == "common"
        tail = ["def demo():", "    out = []"] + ["    " + d for d in self.demos]
        if self.uses_log:
            tail.append("    out.extend(kit.events.default().drain())" if (new and not common) else f"    out.extend({self.I.call('flush_log')}())")
        tail.append("    return out")
        head = ['"""Demo module "%s" of the shop application."""' % self.name]
        if self.uses_functools:
            head.append("import functools")
        head += ["import kit"] if (new and not common) else self.I.header()
        blocks = self.new if new else self.old
        return "\n".join(head) + "\n\n\n" + "\n\n\n".join(blocks) + "\n\n\n" + "\n".join(tail) + "\n"


def both(m: Mod, old: str, new: str | None = None):
    m.old.append(old.strip("\n"))
    m.new.append((new if new is not None else old).strip("\n"))


# -- snippets -----------------------------------------------------------------------------------------------------

def sn_line_item(m: Mod):
    rng, p, I = m.rng, m.p, m.I
    f = m.fn("line")
    w1, w2 = rng.choice([10, 12, 14]), rng.choice([8, 9, 10, 12])
    cur = rng.choice([p["cur"], p["cur"], "USD", "GBP", "CHF"])
    v = rng.choice(["plain", "default", "kw"]) if cur == p["cur"] else rng.choice(["plain", "kw"])
    if v == "plain":
        old = f'''
def {f}(name, qty, cents):
    return {I.call("pad_right")}(name, {w1}) + {I.call("pad_left")}({I.call("fmt_amount")}(qty * cents, "{cur}"), {w2})
'''
        new = f'''
def {f}(name, qty, cents):
    return kit.text.pad(name, {w1}, align="left") + kit.text.pad(kit.money.Money(qty * cents, "{cur}").text(), {w2}, align="right")
'''
    elif v == "default":
        old = f'''
def {f}(name, qty, cents):
    total = qty * cents
    return {I.call("pad_right")}(name, {w1}) + {I.call("pad_left")}({I.call("fmt_amount")}(total), {w2})
'''
        new = f'''
def {f}(name, qty, cents):
    total = qty * cents
    return kit.text.pad(name, {w1}, align="left") + kit.text.pad(kit.money.Money(total, "{p['cur']}").text(), {w2}, align="right")
'''
    else:
        old = f'''
def {f}(name, qty, cents):
    amount = {I.call("fmt_amount")}(cents=qty * cents, cur="{cur}")
    return {I.call("pad_right")}(s=name, width={w1}) + {I.call("pad_left")}(amount, width={w2})
'''
        new = f'''
def {f}(name, qty, cents):
    amount = kit.money.Money(cents=qty * cents, cur="{cur}").text()
    return kit.text.pad(s=name, width={w1}, align="left") + kit.text.pad(amount, width={w2}, align="right")
'''
    both(m, old, new)
    it = rng.sample(m.nouns, 2)
    m.demo(f, [f'"{it[0]}", {rng.randint(1, 9)}, {rng.choice([1250, 75, 9990, 100])}', f'"{it[1]} (large)", {rng.randint(10, 60)}, {rng.choice([-75, 2, 333])}'])


def sn_header_const(m: Mod):
    rng, I = m.rng, m.I
    w1, w2 = rng.choice([10, 12]), rng.choice([8, 10])
    name = m.const("HEADER")
    f = m.fn("header")
    both(m, f'''
{name} = {I.call("pad_right")}("NAME", {w1}) + {I.call("pad_left")}("TOTAL", {w2})


def {f}():
    return {name} + "|"
''', f'''
{name} = kit.text.pad("NAME", {w1}, align="left") + kit.text.pad("TOTAL", {w2}, align="right")


def {f}():
    return {name} + "|"
''')
    m.demo(f, [""])


def sn_qty(m: Mod):
    rng, p, I = m.rng, m.p, m.I
    f = m.fn("qty")
    fb = rng.choice([0, -1, 1])
    fac = {u: rng.randint(2, 12) for u in rng.sample(W.UNITS, 3)}
    const = m.const("FACTORS")
    v = rng.choice(["tuple", "index", "valid", "unit"])
    if v == "tuple":
        old = f'''
{const} = {fac!r}


def {f}(text):
    parsed = {I.call("parse_qty")}(text)
    if parsed is None:
        return {fb}
    count, unit = parsed
    return count * {const}.get(unit, 1)
'''
        new = f'''
{const} = {fac!r}


def {f}(text):
    try:
        q = kit.qty.Qty.parse(text)
    except kit.qty.QtyError:
        return {fb}
    return q.count * {const}.get(q.unit, 1)
'''
    elif v == "index":
        old = f'''
def {f}(text):
    qty = {I.call("parse_qty")}(text)
    return qty[0] if qty else {fb}
'''
        new = f'''
def {f}(text):
    qty = kit.qty.Qty.try_parse(text)
    return qty.count if qty else {fb}
'''
    elif v == "valid":
        old = f'''
def {f}(text):
    return {I.call("parse_qty")}(text) is not None
'''
        new = f'''
def {f}(text):
    return kit.qty.Qty.try_parse(text) is not None
'''
    else:
        old = f'''
def {f}(text):
    _, unit = {I.call("parse_qty")}(text) or (0, "none")
    return unit
'''
        new = f'''
def {f}(text):
    qty = kit.qty.Qty.try_parse(text)
    return qty.unit if qty else "none"
'''
    both(m, old, new)
    m.demo(f, [f'"{rng.randint(2, 40)} {rng.choice(list(fac))}"', f'"{rng.randint(1, 9)}x"', f'"{rng.randint(1, 30)}"', '"lots of it"', '""', f'" {rng.randint(1, 9)} L "'])


def sn_log(m: Mod):
    rng, I = m.rng, m.I
    m.uses_log = True
    f = m.fn("note")
    msg = rng.choice(["restocked", "sold out", "checked", "moved", "closed early", "inspected"])
    k = rng.randint(2, 7)
    v = rng.choice(["plain", "ret", "wrapper"])
    if v == "plain":
        old = f'''
def {f}(oid, n):
    {I.call("log")}("info", "{msg}", order=oid, count=n)
    return n * {k}
'''
        new = f'''
def {f}(oid, n):
    kit.events.default().emit("info", "{msg}", order=oid, count=n)
    return n * {k}
'''
    elif v == "ret":
        old = f'''
def {f}(oid, n):
    line = {I.call("log")}("warn", "{msg}", order=oid, left=n - {k})
    return line.upper()
'''
        new = f'''
def {f}(oid, n):
    events = kit.events.default()
    events.emit("warn", "{msg}", order=oid, left=n - {k})
    return events.last().upper()
'''
    else:
        w = "_" + m.fn("event")
        old = f'''
def {w}(msg, **ctx):
    return {I.call("log")}("debug", msg, **ctx)


def {f}(oid, n):
    {w}("{msg}", order=oid, n=n)
    return n + {k}
'''
        new = f'''
def {w}(msg, **ctx):
    events = kit.events.default()
    events.emit("debug", msg, **ctx)
    return events.last()


def {f}(oid, n):
    {w}("{msg}", order=oid, n=n)
    return n + {k}
'''
    both(m, old, new)
    m.demo(f, [f'"A{rng.randint(10, 99)}", {rng.randint(3, 20)}', f'"B{rng.randint(10, 99)}", {rng.randint(8, 30)}'])


def sn_pick(m: Mod):
    rng, I = m.rng, m.I
    f = m.fn("rate")
    const = m.const("RATES")
    table = {"rates": {r: {k: rng.randint(1, 90) for k in rng.sample(W.KINDS, 3)} for r in rng.sample(W.REGIONS, 3)}}
    d = rng.choice([0, -1, 5])
    v = rng.choice(["args", "star", "mixed"])
    if v == "args":
        old = f'''
{const} = {table!r}


def {f}(region, kind):
    return {I.call("pick")}({const}, "rates", region, kind, default={d})
'''
        new = f'''
{const} = {table!r}


def {f}(region, kind):
    return kit.data.dig({const}, ("rates", region, kind), default={d})
'''
    elif v == "star":
        old = f'''
{const} = {table!r}


def {f}(region, kind):
    path = ("rates", region, kind)
    return {I.call("pick")}({const}, *path, default={d})
'''
        new = f'''
{const} = {table!r}


def {f}(region, kind):
    path = ("rates", region, kind)
    return kit.data.dig({const}, path, default={d})
'''
    else:
        old = f'''
{const} = {table!r}


def {f}(region, kind):
    by_kind = {I.call("pick")}({const}, "rates", region, default={{}})
    return by_kind.get(kind, {d}) + {I.call("pick")}({const}, "rates", "nowhere", default=0)
'''
        new = f'''
{const} = {table!r}


def {f}(region, kind):
    by_kind = kit.data.dig({const}, ("rates", region), default={{}})
    return by_kind.get(kind, {d}) + kit.data.dig({const}, ("rates", "nowhere"), default=0)
'''
    both(m, old, new)
    regs = list(table["rates"])
    kinds = list(table["rates"][regs[0]])
    m.demo(f, [f'"{regs[0]}", "{kinds[0]}"', f'"{regs[1]}", "{rng.choice(W.KINDS)}"', f'"atlantis", "{kinds[0]}"'])


def sn_group(m: Mod):
    rng, I = m.rng, m.I
    f = m.fn("tally")
    kf = rng.choice(["kind", "region", "unit"])
    n = rng.randint(2, 4)
    v = rng.choice(["dict", "items", "comp"])
    if v == "dict":
        old = f'''
def {f}(items):
    groups = {I.call("group_by")}(items, lambda it: it["{kf}"])
    out = []
    for key in sorted(groups):
        out.append("%s=%d" % (key, len(groups[key])))
    return {I.call("take")}(out, {n})
'''
        new = f'''
def {f}(items):
    groups = dict(kit.data.group(items, key=lambda it: it["{kf}"]))
    out = []
    for key in sorted(groups):
        out.append("%s=%d" % (key, len(groups[key])))
    return kit.data.first(out, {n})
'''
    elif v == "items":
        old = f'''
def {f}(items):
    rows = []
    for key, members in {I.call("group_by")}(items, lambda it: it["{kf}"]).items():
        rows.append((len(members), key))
    return {I.call("take")}(sorted(rows, reverse=True), {n})
'''
        new = f'''
def {f}(items):
    rows = []
    for key, members in kit.data.group(items, key=lambda it: it["{kf}"]):
        rows.append((len(members), key))
    return kit.data.first(sorted(rows, reverse=True), {n})
'''
    else:
        old = f'''
def {f}(items):
    buckets = {I.call("group_by")}(items, lambda it: it["{kf}"])
    first_seen = list(buckets)
    return first_seen, {{k: len(v) for k, v in sorted(buckets.items())}}
'''
        new = f'''
def {f}(items):
    buckets = dict(kit.data.group(items, key=lambda it: it["{kf}"]))
    first_seen = list(buckets)
    return first_seen, {{k: len(v) for k, v in sorted(buckets.items())}}
'''
    both(m, old, new)
    rows = [{"kind": rng.choice(W.KINDS[:3]), "region": rng.choice(W.REGIONS[:3]), "unit": rng.choice(W.UNITS[:3])} for _ in range(rng.randint(5, 9))]
    m.demos.append(f"out.append(\"{f}(rows) = %r\" % ({f}({rows!r}),))")


def sn_callbacks(m: Mod):
    rng, I = m.rng, m.I
    c = rng.choice(["sorted", "title", "money", "partial", "reduce"])
    if c == "sorted":
        f = m.fn("names")
        n = rng.randint(2, 4)
        both(m, f'''
def {f}(names):
    return {I.call("take")}(sorted(names, key={I.call("sort_key")}), {n})
''', f'''
def {f}(names):
    return kit.data.first(sorted(names, key=kit.text.sort_key), {n})
''')
        m.demo(f, [repr(rng.sample(["delta", "Alpha", "charlie", "bravo", "echo", "Bravo", "alpha"], 6))])
    elif c == "title":
        f = m.fn("labels")
        both(m, f'''
def {f}(names):
    return list(map({I.call("title")}, names))
''', f'''
def {f}(names):
    return list(map(kit.text.title_case, names))
''')
        m.demo(f, [repr(rng.sample(W.WORDS, 3) + ["  spaced   out  words "])])
    elif c == "money":
        f = m.fn("prices")
        both(m, f'''
def {f}(cents_list):
    return list(map({I.call("fmt_amount")}, cents_list))
''', f'''
def {f}(cents_list):
    return [kit.money.Money(c, "{m.p['cur']}").text() for c in cents_list]
''')
        m.demo(f, [repr([rng.randint(-500, 99999) for _ in range(4)])])
    elif c == "partial":
        f = m.fn("padded")
        w = rng.choice([6, 8, 10])
        m.uses_functools = True
        both(m, f'''
def {f}(texts):
    right = functools.partial({I.call("pad_left")}, width={w})
    left = functools.partial({I.call("pad_right")}, width={w})
    return [right(t) + "|" + left(t) for t in texts]
''', f'''
def {f}(texts):
    right = functools.partial(kit.text.pad, width={w}, align="right")
    left = functools.partial(kit.text.pad, width={w}, align="left")
    return [right(t) + "|" + left(t) for t in texts]
''')
        m.demo(f, [repr(rng.sample(m.nouns, 3))])
    else:
        f = m.fn("capped")
        lo, hi = rng.choice([(0, 50), (-10, 40), (5, 100)])
        m.uses_functools = True
        both(m, f'''
def {f}(deltas):
    return functools.reduce(lambda acc, x: {I.call("clamp")}(acc + x, {lo}, {hi}), deltas, 0)
''', f'''
def {f}(deltas):
    return functools.reduce(lambda acc, x: kit.data.limit(acc + x, {lo}, {hi}), deltas, 0)
''')
        m.demo(f, [repr([rng.randint(-30, 60) for _ in range(6)])])


def sn_label(m: Mod):
    rng, I = m.rng, m.I
    f = m.fn("label")
    w = rng.choice([14, 16, 20])
    lo, hi = rng.choice([(3, 12), (1, 8)])
    both(m, f'''
def {f}(text):
    shown = {I.call("pad_left")}({I.call("title")}(text), {w})
    return shown + " [" + str({I.call("clamp")}(len(text), {lo}, {hi})) + "]"
''', f'''
def {f}(text):
    shown = kit.text.pad(kit.text.title_case(text), {w}, align="right")
    return shown + " [" + str(kit.data.limit(len(text), {lo}, {hi})) + "]"
''')
    m.demo(f, [f'"{rng.choice(W.WORDS)}"', '"x"', '"a rather long description of a thing"'])


SNIPPETS = [sn_line_item, sn_line_item, sn_header_const, sn_qty, sn_qty, sn_log, sn_log, sn_pick, sn_pick, sn_group, sn_callbacks, sn_callbacks, sn_label]


# ---------------------------------------------------------------------------------------------------------------
# the application
# ---------------------------------------------------------------------------------------------------------------

def common_old(p: dict) -> str:
    return '''"""Shared helpers: thin wrappers around oldkit that most of the application imports."""
import oldkit

fmt_amount = oldkit.fmt_amount
parse_qty = oldkit.parse_qty
pad_right = oldkit.pad_right
pad_left = oldkit.pad_left
title = oldkit.title
sort_key = oldkit.sort_key
pick = oldkit.pick
take = oldkit.take
group_by = oldkit.group_by
log = oldkit.log
flush_log = oldkit.flush_log
clamp = oldkit.clamp
'''


def common_new(p: dict) -> str:
    return f'''"""Shared helpers: wrappers with the historical signatures, now backed by kit."""
import kit


def fmt_amount(cents, cur="{p['cur']}"):
    return kit.money.Money(cents, cur).text()


def parse_qty(text):
    q = kit.qty.Qty.try_parse(text)
    return None if q is None else (q.count, q.unit)


def pad_right(s, width):
    return kit.text.pad(s, width, align="left")


def pad_left(s, width):
    return kit.text.pad(s, width, align="right")


def title(s):
    return kit.text.title_case(s)


def sort_key(s):
    return kit.text.sort_key(s)


def pick(d, *keys, default=None):
    return kit.data.dig(d, keys, default=default)


def take(seq, n):
    return kit.data.first(seq, n)


def group_by(items, keyfn):
    return dict(kit.data.group(items, key=keyfn))


def log(level, msg, **ctx):
    events = kit.events.default()
    events.emit(level, msg, **ctx)
    return events.last()


def flush_log():
    return kit.events.default().drain()


def clamp(x, lo, hi):
    return kit.data.limit(x, lo, hi)
'''


RUN_PY = '''"""Runs the demo of one module of the application and prints its lines:  python3 run.py MODULE   (or: python3 run.py all)."""
import importlib
import sys

from app import MODULES


def main(argv):
    names = MODULES if argv == ["all"] else argv
    status = 0
    for name in names:
        try:
            for line in importlib.import_module("app." + name).demo():
                print(line)
        except Exception as e:  # noqa: BLE001
            print("error: %s: %s" % (type(e).__name__, e))
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''


def build_app(rng: random.Random, p: dict) -> dict:
    """-> {"start": files, "solution": changed files, "modules": [names], "common": bool}"""
    names = rng.sample(W.MODULE_NAMES, p["n_modules"])
    use_common = p["common"]
    direct = []
    start: dict[str, str] = {}
    solution: dict[str, str] = {}
    styles = ["plain", "plain", "alias", "from", "falias"] if p["shapes"] else ["plain", "plain", "alias"]
    for name in names:
        style = "common" if use_common and rng.random() < p["common_share"] else rng.choice(styles)
        m = Mod(name, style, rng, p)
        kinds = rng.sample(SNIPPETS, rng.randint(p["min_snip"], p["max_snip"]))
        for fn in kinds:
            fn(m)
        old_src, new_src = m.source(False), m.source(True)
        start[f"app/{name}.py"] = old_src
        if style != "common":
            solution[f"app/{name}.py"] = new_src
            direct.append(name)
    start["app/__init__.py"] = '"""The shop application: one demo module per workshop."""\nMODULES = (' + ", ".join(f'"{n}"' for n in names) + ",)\n"
    start["oldkit.py"] = oldkit_source(p)
    start.update(kit_files(p))
    start["run.py"] = RUN_PY
    if use_common:
        start["app/common.py"] = common_old(p)
        solution["app/common.py"] = common_new(p)
    return {"start": start, "solution": solution, "modules": names, "direct": direct}
