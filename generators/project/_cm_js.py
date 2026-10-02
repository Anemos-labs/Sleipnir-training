"""JavaScript codemod application (CommonJS): legacy `oldkit.js`, replacement package `kit/`, many generated modules in several call
shapes, and the migrated versions (written explicitly for each shape; the build proves they print the same thing)."""
from __future__ import annotations

import json
import random

from generators.project import _cm_common as W

FALIAS = {"fmtAmount": "money", "padRight": "rpad", "padLeft": "lpad", "parseQty": "qtyOf", "title": "nice", "cmpNames": "byName", "pick": "digIn",
          "take": "head", "groupBy": "bucket", "log": "note", "flushLog": "drainNotes", "clamp": "bound"}


def camel(s: str) -> str:
    return s


def js(v) -> str:
    return json.dumps(v, ensure_ascii=True).replace('"', "'") if isinstance(v, str) and '"' not in v and "'" not in v else json.dumps(v, ensure_ascii=True)


def lit(v) -> str:
    """A JavaScript literal (single-quoted strings) for str/int/list/dict."""
    if isinstance(v, str):
        return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(lit(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {lit(x)}" for k, x in v.items()) + "}"
    raise TypeError(v)


def oldkit_source(p: dict) -> str:
    title = ("  return s.split(/\\s+/).filter(Boolean).map((w) => w[0].toUpperCase() + w.slice(1).toLowerCase()).join(' ');" if p["title"] == "each" else
             "  const words = s.split(/\\s+/).filter(Boolean);\n  const t = words.map((w, i) => (i === 0 ? w : w.toLowerCase())).join(' ');\n  return t ? t[0].toUpperCase() + t.slice(1).toLowerCase() : '';")
    return f"""'use strict';
// oldkit: the helper module this codebase has used so far.  It is being retired: see README.md.

const LOG = [];

function fmtAmount(cents, cur = '{p['cur']}') {{
  // 12.50 EUR style text for an integer number of cents
  const sign = cents < 0 ? '-' : '';
  const abs = Math.abs(cents);
  const whole = Math.floor(abs / 100);
  const frac = String(abs % 100).padStart(2, '0');
  return `${{sign}}${{whole}}.${{frac}} ${{cur}}`;
}}

function parseQty(text) {{
  // [count, unit] for '12 kg', '3x' or '7' (unit defaults to '{p['unit']}'); null when the text is not a quantity
  const m = /^\\s*([0-9]+)\\s*([A-Za-z]*)\\s*$/.exec(text);
  if (!m) return null;
  return [parseInt(m[1], 10), m[2] || '{p['unit']}'];
}}

function padRight(s, width) {{
  // padding on the right: the text stays at the left
  return s.padEnd(width);
}}

function padLeft(s, width) {{
  // padding on the left: the text moves to the right
  return s.padStart(width);
}}

function title(s) {{
{title}
}}

function cmpNames(a, b) {{
  const x = a.toLowerCase();
  const y = b.toLowerCase();
  if (x !== y) return x < y ? -1 : 1;
  return a === b ? 0 : a < b ? -1 : 1;
}}

function pick(obj, ...keys) {{
  // nested lookup: pick(cfg, 'a', 'b') is cfg.a.b, or undefined when a key is missing
  let cur = obj;
  for (const k of keys) {{
    if (cur !== null && typeof cur === 'object' && Object.prototype.hasOwnProperty.call(cur, k)) cur = cur[k];
    else return undefined;
  }}
  return cur;
}}

function take(seq, n) {{
  return Array.from(seq).slice(0, n);
}}

function groupBy(items, keyfn) {{
  // plain object: key -> array of items (keys in order of first appearance)
  const out = {{}};
  for (const it of items) {{
    const k = keyfn(it);
    if (!Object.prototype.hasOwnProperty.call(out, k)) out[k] = [];
    out[k].push(it);
  }}
  return out;
}}

function log(level, msg, ctx = {{}}) {{
  // appends '{p['log'][0]}LEVEL{p['log'][1]} msg key=value ...' (keys sorted) to the global log and returns it
  const line = `{p['log'][0]}${{level.toUpperCase()}}{p['log'][1]} ${{msg}}` + Object.keys(ctx).sort().map((k) => ` ${{k}}=${{ctx[k]}}`).join('');
  LOG.push(line);
  return line;
}}

function flushLog() {{
  return LOG.splice(0, LOG.length);
}}

function clamp(x, lo, hi) {{
  return Math.max(lo, Math.min(hi, x));
}}

module.exports = {{ fmtAmount, parseQty, padRight, padLeft, title, cmpNames, pick, take, groupBy, log, flushLog, clamp }};
"""


POISON = """'use strict';
// oldkit has been retired: every function fails.
function gone() {
  throw new Error('oldkit has been retired; use the kit package');
}
module.exports = {
  fmtAmount: gone, parseQty: gone, padRight: gone, padLeft: gone, title: gone, cmpNames: gone,
  pick: gone, take: gone, groupBy: gone, log: gone, flushLog: gone, clamp: gone,
};
"""


def kit_files(p: dict) -> dict[str, str]:
    title = ("  return s.split(/\\s+/).filter(Boolean).map((w) => w[0].toUpperCase() + w.slice(1).toLowerCase()).join(' ');" if p["title"] == "each" else
             "  const words = s.split(/\\s+/).filter(Boolean);\n  const t = words.map((w, i) => (i === 0 ? w : w.toLowerCase())).join(' ');\n  return t ? t[0].toUpperCase() + t.slice(1).toLowerCase() : '';")
    return {
        "kit/index.js": "'use strict';\n// kit: the shared helpers of the application (money, text, quantities, data, events).\nmodule.exports = {\n  money: require('./money'),\n  text: require('./text'),\n  qty: require('./qty'),\n  data: require('./data'),\n  events: require('./events'),\n};\n",
        "kit/money.js": """'use strict';

// An amount in cents of a currency; both are required.
class Money {
  constructor(cents, cur) {
    if (cur === undefined) throw new TypeError('Money needs a currency');
    this.cents = cents;
    this.cur = cur;
  }

  text() {
    const sign = this.cents < 0 ? '-' : '';
    const abs = Math.abs(this.cents);
    const frac = String(abs % 100).padStart(2, '0');
    return `${sign}${Math.floor(abs / 100)}.${frac} ${this.cur}`;
  }
}

module.exports = { Money };
""",
        "kit/text.js": f"""'use strict';

// Pad to `width`: align 'left' keeps the text at the left (padding on the right), 'right' moves it to the right.
function pad(s, width, {{ align = 'left' }} = {{}}) {{
  if (align === 'left') return s.padEnd(width);
  if (align === 'right') return s.padStart(width);
  throw new RangeError("align must be 'left' or 'right'");
}}

function titleCase(s) {{
{title}
}}

function compare(a, b) {{
  const x = a.toLowerCase();
  const y = b.toLowerCase();
  if (x !== y) return x < y ? -1 : 1;
  return a === b ? 0 : a < b ? -1 : 1;
}}

module.exports = {{ pad, titleCase, compare }};
""",
        "kit/qty.js": f"""'use strict';

class QtyError extends Error {{}}

class Qty {{
  constructor(count, unit) {{
    this.count = count;
    this.unit = unit;
  }}

  // Qty for '12 kg', '3x' or '7' (unit defaults to '{p['unit']}'); throws QtyError otherwise.
  static parse(text) {{
    const m = /^\\s*([0-9]+)\\s*([A-Za-z]*)\\s*$/.exec(text);
    if (!m) throw new QtyError(`not a quantity: ${{JSON.stringify(text)}}`);
    return new Qty(parseInt(m[1], 10), m[2] || '{p['unit']}');
  }}

  // Like parse, but returns null instead of throwing.
  static tryParse(text) {{
    try {{
      return Qty.parse(text);
    }} catch (e) {{
      if (e instanceof QtyError) return null;
      throw e;
    }}
  }}
}}

module.exports = {{ Qty, QtyError }};
""",
        "kit/data.js": """'use strict';

// Nested lookup along an array of keys; `def` when a key is missing.
function dig(obj, path, def) {
  let cur = obj;
  for (const k of path) {
    if (cur !== null && typeof cur === 'object' && Object.prototype.hasOwnProperty.call(cur, k)) cur = cur[k];
    else return def;
  }
  return cur;
}

function first(seq, n) {
  return Array.from(seq).slice(0, n);
}

// Array of [key, items] pairs in order of first appearance of the keys.
function group(items, key) {
  const map = new Map();
  for (const it of items) {
    const k = key(it);
    if (!map.has(k)) map.set(k, []);
    map.get(k).push(it);
  }
  return Array.from(map.entries());
}

function limit(x, lo, hi) {
  return Math.max(lo, Math.min(hi, x));
}

module.exports = { dig, first, group, limit };
""",
        "kit/events.js": f"""'use strict';

class Events {{
  constructor() {{
    this.lines = [];
  }}

  // Record '{p['log'][0]}LEVEL{p['log'][1]} msg key=value ...' (keys sorted).  Returns nothing: see last().
  emit(level, msg, ctx = {{}}) {{
    this.lines.push(`{p['log'][0]}${{level.toUpperCase()}}{p['log'][1]} ${{msg}}` + Object.keys(ctx).sort().map((k) => ` ${{k}}=${{ctx[k]}}`).join(''));
  }}

  last() {{
    return this.lines[this.lines.length - 1];
  }}

  drain() {{
    return this.lines.splice(0, this.lines.length);
  }}
}}

const shared = new Events();

// The process-wide Events instance.
function defaultEvents() {{
  return shared;
}}

module.exports = {{ Events, default: defaultEvents }};
""",
    }


class Imports:
    def __init__(self, style: str, rel: str):
        self.style, self.used, self.rel = style, set(), rel

    def call(self, name: str) -> str:
        self.used.add(name)
        return {"plain": "oldkit." + name, "alias": "ok." + name, "destructure": name, "falias": FALIAS[name], "common": "common." + name}[self.style]

    def header(self) -> list[str]:
        used = sorted(self.used)
        r = self.rel
        if self.style == "plain":
            return [f"const oldkit = require('{r}oldkit');"]
        if self.style == "alias":
            return [f"const ok = require('{r}oldkit');"]
        if self.style == "destructure":
            return ["const { " + ", ".join(used) + f" }} = require('{r}oldkit');"]
        if self.style == "falias":
            return ["const { " + ", ".join(f"{n}: {FALIAS[n]}" for n in used) + f" }} = require('{r}oldkit');"]
        return ["const common = require('./common');"]


def cc(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(x[:1].upper() + x[1:] for x in parts[1:])


class Mod:
    def __init__(self, name: str, style: str, rng: random.Random, p: dict):
        self.name, self.rng, self.p = name, rng, p
        self.I = Imports(style, "../")
        self.old: list[str] = []
        self.new: list[str] = []
        self.demos: list[str] = []
        self.uses_log = False
        self.nouns = rng.sample(W.ITEMS, 6)
        self._names: set[str] = set()

    def fn(self, role: str) -> str:
        base = f"{self.name}{role[:1].upper()}{role[1:]}"
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

    def demo(self, fname: str, args: list[str]):
        for a in args:
            label = f"{fname}({a})".replace("\\", "\\\\").replace("'", "\\'")
            self.demos.append(f"out.push('{label} = ' + JSON.stringify({fname}({a})));")

    def source(self, new: bool) -> str:
        common = self.I.style == "common"
        tail = ["function demo() {", "  const out = [];"] + ["  " + d for d in self.demos]
        if self.uses_log:
            tail.append("  out.push(...kit.events.default().drain());" if (new and not common) else f"  out.push(...{self.I.call('flushLog')}());")
        tail += ["  return out;", "}", "", "module.exports = { demo };"]
        head = ["'use strict';", f"// Demo module '{self.name}' of the shop application."]
        head += ["const kit = require('../kit');"] if (new and not common) else self.I.header()
        blocks = self.new if new else self.old
        return "\n".join(head) + "\n\n" + "\n\n".join(blocks) + "\n\n" + "\n".join(tail) + "\n"


def both(m: Mod, old: str, new: str | None = None):
    m.old.append(old.strip("\n"))
    m.new.append((new if new is not None else old).strip("\n"))


def sn_line_item(m: Mod):
    rng, p, I = m.rng, m.p, m.I
    f = m.fn("line")
    w1, w2 = rng.choice([10, 12, 14]), rng.choice([8, 9, 10, 12])
    cur = rng.choice([p["cur"], p["cur"], "USD", "GBP", "CHF"])
    v = rng.choice(["plain", "default", "map"]) if cur == p["cur"] else rng.choice(["plain", "map"])
    if v == "plain":
        old = f"""
function {f}(name, qty, cents) {{
  return {I.call("padRight")}(name, {w1}) + {I.call("padLeft")}({I.call("fmtAmount")}(qty * cents, '{cur}'), {w2});
}}
"""
        new = f"""
function {f}(name, qty, cents) {{
  return kit.text.pad(name, {w1}, {{ align: 'left' }}) + kit.text.pad(new kit.money.Money(qty * cents, '{cur}').text(), {w2}, {{ align: 'right' }});
}}
"""
    elif v == "default":
        old = f"""
function {f}(name, qty, cents) {{
  const total = qty * cents;
  return {I.call("padRight")}(name, {w1}) + {I.call("padLeft")}({I.call("fmtAmount")}(total), {w2});
}}
"""
        new = f"""
function {f}(name, qty, cents) {{
  const total = qty * cents;
  return kit.text.pad(name, {w1}, {{ align: 'left' }}) + kit.text.pad(new kit.money.Money(total, '{p['cur']}').text(), {w2}, {{ align: 'right' }});
}}
"""
    else:
        old = f"""
function {f}(name, qty, cents) {{
  const cells = [name, {I.call("fmtAmount")}(qty * cents, '{cur}')];
  return cells.map((c, i) => (i === 0 ? {I.call("padRight")}(c, {w1}) : {I.call("padLeft")}(c, {w2}))).join('');
}}
"""
        new = f"""
function {f}(name, qty, cents) {{
  const cells = [name, new kit.money.Money(qty * cents, '{cur}').text()];
  return cells.map((c, i) => (i === 0 ? kit.text.pad(c, {w1}, {{ align: 'left' }}) : kit.text.pad(c, {w2}, {{ align: 'right' }}))).join('');
}}
"""
    both(m, old, new)
    it = rng.sample(m.nouns, 2)
    m.demo(f, [f"'{it[0]}', {rng.randint(1, 9)}, {rng.choice([1250, 75, 9990, 100])}", f"'{it[1]} (large)', {rng.randint(10, 60)}, {rng.choice([-75, 2, 333])}"])


def sn_header_const(m: Mod):
    rng, I = m.rng, m.I
    w1, w2 = rng.choice([10, 12]), rng.choice([8, 10])
    name = m.const("HEADER")
    f = m.fn("header")
    both(m, f"""
const {name} = {I.call("padRight")}('NAME', {w1}) + {I.call("padLeft")}('TOTAL', {w2});

function {f}() {{
  return {name} + '|';
}}
""", f"""
const {name} = kit.text.pad('NAME', {w1}, {{ align: 'left' }}) + kit.text.pad('TOTAL', {w2}, {{ align: 'right' }});

function {f}() {{
  return {name} + '|';
}}
""")
    m.demo(f, [""])


def sn_qty(m: Mod):
    rng, p, I = m.rng, m.p, m.I
    f = m.fn("qty")
    fb = rng.choice([0, -1, 1])
    fac = {u: rng.randint(2, 12) for u in rng.sample(W.UNITS, 3)}
    const = m.const("FACTORS")
    v = rng.choice(["tuple", "index", "valid", "unit"])
    if v == "tuple":
        old = f"""
const {const} = {lit(fac)};

function {f}(text) {{
  const parsed = {I.call("parseQty")}(text);
  if (parsed === null) return {fb};
  const [count, unit] = parsed;
  return count * ({const}[unit] ?? 1);
}}
"""
        new = f"""
const {const} = {lit(fac)};

function {f}(text) {{
  let q;
  try {{
    q = kit.qty.Qty.parse(text);
  }} catch (e) {{
    if (e instanceof kit.qty.QtyError) return {fb};
    throw e;
  }}
  return q.count * ({const}[q.unit] ?? 1);
}}
"""
    elif v == "index":
        old = f"""
function {f}(text) {{
  const qty = {I.call("parseQty")}(text);
  return qty ? qty[0] : {fb};
}}
"""
        new = f"""
function {f}(text) {{
  const qty = kit.qty.Qty.tryParse(text);
  return qty ? qty.count : {fb};
}}
"""
    elif v == "valid":
        old = f"""
function {f}(text) {{
  return {I.call("parseQty")}(text) !== null;
}}
"""
        new = f"""
function {f}(text) {{
  return kit.qty.Qty.tryParse(text) !== null;
}}
"""
    else:
        old = f"""
function {f}(text) {{
  const [, unit] = {I.call("parseQty")}(text) || [0, 'none'];
  return unit;
}}
"""
        new = f"""
function {f}(text) {{
  const qty = kit.qty.Qty.tryParse(text);
  return qty ? qty.unit : 'none';
}}
"""
    both(m, old, new)
    m.demo(f, [f"'{rng.randint(2, 40)} {rng.choice(list(fac))}'", f"'{rng.randint(1, 9)}x'", f"'{rng.randint(1, 30)}'", "'lots of it'", "''", f"' {rng.randint(1, 9)} L '"])


def sn_log(m: Mod):
    rng, I = m.rng, m.I
    m.uses_log = True
    f = m.fn("note")
    msg = rng.choice(["restocked", "sold out", "checked", "moved", "closed early", "inspected"])
    k = rng.randint(2, 7)
    v = rng.choice(["plain", "ret", "wrapper"])
    if v == "plain":
        old = f"""
function {f}(oid, n) {{
  {I.call("log")}('info', '{msg}', {{ order: oid, count: n }});
  return n * {k};
}}
"""
        new = f"""
function {f}(oid, n) {{
  kit.events.default().emit('info', '{msg}', {{ order: oid, count: n }});
  return n * {k};
}}
"""
    elif v == "ret":
        old = f"""
function {f}(oid, n) {{
  const line = {I.call("log")}('warn', '{msg}', {{ order: oid, left: n - {k} }});
  return line.toUpperCase();
}}
"""
        new = f"""
function {f}(oid, n) {{
  const events = kit.events.default();
  events.emit('warn', '{msg}', {{ order: oid, left: n - {k} }});
  return events.last().toUpperCase();
}}
"""
    else:
        w = m.fn("event")
        old = f"""
const {w} = (msg, ctx) => {I.call("log")}('debug', msg, ctx);

function {f}(oid, n) {{
  {w}('{msg}', {{ order: oid, n }});
  return n + {k};
}}
"""
        new = f"""
const {w} = (msg, ctx) => {{
  const events = kit.events.default();
  events.emit('debug', msg, ctx);
  return events.last();
}};

function {f}(oid, n) {{
  {w}('{msg}', {{ order: oid, n }});
  return n + {k};
}}
"""
    both(m, old, new)
    m.demo(f, [f"'A{rng.randint(10, 99)}', {rng.randint(3, 20)}", f"'B{rng.randint(10, 99)}', {rng.randint(8, 30)}"])


def sn_pick(m: Mod):
    rng, I = m.rng, m.I
    f = m.fn("rate")
    const = m.const("RATES")
    table = {"rates": {r: {k: rng.randint(1, 90) for k in rng.sample(W.KINDS, 3)} for r in rng.sample(W.REGIONS, 3)}}
    d = rng.choice([0, -1, 5])
    v = rng.choice(["args", "spread", "mixed"])
    if v == "args":
        old = f"""
const {const} = {lit(table)};

function {f}(region, kind) {{
  return {I.call("pick")}({const}, 'rates', region, kind) ?? {d};
}}
"""
        new = f"""
const {const} = {lit(table)};

function {f}(region, kind) {{
  return kit.data.dig({const}, ['rates', region, kind], {d});
}}
"""
    elif v == "spread":
        old = f"""
const {const} = {lit(table)};

function {f}(region, kind) {{
  const path = ['rates', region, kind];
  return {I.call("pick")}({const}, ...path) ?? {d};
}}
"""
        new = f"""
const {const} = {lit(table)};

function {f}(region, kind) {{
  const path = ['rates', region, kind];
  return kit.data.dig({const}, path, {d});
}}
"""
    else:
        old = f"""
const {const} = {lit(table)};

function {f}(region, kind) {{
  const byKind = {I.call("pick")}({const}, 'rates', region) ?? {{}};
  return (byKind[kind] ?? {d}) + ({I.call("pick")}({const}, 'rates', 'nowhere') ?? 0);
}}
"""
        new = f"""
const {const} = {lit(table)};

function {f}(region, kind) {{
  const byKind = kit.data.dig({const}, ['rates', region], {{}});
  return (byKind[kind] ?? {d}) + kit.data.dig({const}, ['rates', 'nowhere'], 0);
}}
"""
    both(m, old, new)
    regs = list(table["rates"])
    kinds = list(table["rates"][regs[0]])
    m.demo(f, [f"'{regs[0]}', '{kinds[0]}'", f"'{regs[1]}', '{rng.choice(W.KINDS)}'", f"'atlantis', '{kinds[0]}'"])


def sn_group(m: Mod):
    rng, I = m.rng, m.I
    f = m.fn("tally")
    kf = rng.choice(["kind", "region", "unit"])
    n = rng.randint(2, 4)
    v = rng.choice(["object", "entries", "values"])
    if v == "object":
        old = f"""
function {f}(items) {{
  const groups = {I.call("groupBy")}(items, (it) => it.{kf});
  const out = [];
  for (const key of Object.keys(groups).sort()) out.push(`${{key}}=${{groups[key].length}}`);
  return {I.call("take")}(out, {n});
}}
"""
        new = f"""
function {f}(items) {{
  const groups = Object.fromEntries(kit.data.group(items, (it) => it.{kf}));
  const out = [];
  for (const key of Object.keys(groups).sort()) out.push(`${{key}}=${{groups[key].length}}`);
  return kit.data.first(out, {n});
}}
"""
    elif v == "entries":
        old = f"""
function {f}(items) {{
  const rows = [];
  for (const [key, members] of Object.entries({I.call("groupBy")}(items, (it) => it.{kf}))) rows.push([members.length, key]);
  rows.sort((a, b) => b[0] - a[0] || (a[1] < b[1] ? 1 : a[1] > b[1] ? -1 : 0));
  return {I.call("take")}(rows, {n});
}}
"""
        new = f"""
function {f}(items) {{
  const rows = [];
  for (const [key, members] of kit.data.group(items, (it) => it.{kf})) rows.push([members.length, key]);
  rows.sort((a, b) => b[0] - a[0] || (a[1] < b[1] ? 1 : a[1] > b[1] ? -1 : 0));
  return kit.data.first(rows, {n});
}}
"""
    else:
        old = f"""
function {f}(items) {{
  const buckets = {I.call("groupBy")}(items, (it) => it.{kf});
  const sizes = {{}};
  for (const k of Object.keys(buckets).sort()) sizes[k] = buckets[k].length;
  return [Object.keys(buckets), sizes];
}}
"""
        new = f"""
function {f}(items) {{
  const buckets = Object.fromEntries(kit.data.group(items, (it) => it.{kf}));
  const sizes = {{}};
  for (const k of Object.keys(buckets).sort()) sizes[k] = buckets[k].length;
  return [Object.keys(buckets), sizes];
}}
"""
    both(m, old, new)
    rows = [{"kind": rng.choice(W.KINDS[:3]), "region": rng.choice(W.REGIONS[:3]), "unit": rng.choice(W.UNITS[:3])} for _ in range(rng.randint(5, 9))]
    m.demos.append(f"out.push('{f}(rows) = ' + JSON.stringify({f}({lit(rows)})));")


def sn_callbacks(m: Mod):
    rng, I = m.rng, m.I
    c = rng.choice(["sorted", "title", "money", "wrap", "reduce"])
    if c == "sorted":
        f = m.fn("names")
        n = rng.randint(2, 4)
        both(m, f"""
function {f}(names) {{
  return {I.call("take")}([...names].sort({I.call("cmpNames")}), {n});
}}
""", f"""
function {f}(names) {{
  return kit.data.first([...names].sort(kit.text.compare), {n});
}}
""")
        m.demo(f, [lit(rng.sample(["delta", "Alpha", "charlie", "bravo", "echo", "Bravo", "alpha"], 6))])
    elif c == "title":
        f = m.fn("labels")
        both(m, f"""
function {f}(names) {{
  return names.map({I.call("title")});
}}
""", f"""
function {f}(names) {{
  return names.map(kit.text.titleCase);
}}
""")
        m.demo(f, [lit(rng.sample(W.WORDS, 3) + ["  spaced   out  words "])])
    elif c == "money":
        f = m.fn("prices")
        both(m, f"""
function {f}(centsList) {{
  return centsList.map((c) => {I.call("fmtAmount")}(c));
}}
""", f"""
function {f}(centsList) {{
  return centsList.map((c) => new kit.money.Money(c, '{m.p['cur']}').text());
}}
""")
        m.demo(f, [lit([rng.randint(-500, 99999) for _ in range(4)])])
    elif c == "wrap":
        f = m.fn("padded")
        w = rng.choice([6, 8, 10])
        both(m, f"""
function {f}(texts) {{
  const right = (t) => {I.call("padLeft")}(t, {w});
  const left = (t) => {I.call("padRight")}(t, {w});
  return texts.map((t) => right(t) + '|' + left(t));
}}
""", f"""
function {f}(texts) {{
  const right = (t) => kit.text.pad(t, {w}, {{ align: 'right' }});
  const left = (t) => kit.text.pad(t, {w}, {{ align: 'left' }});
  return texts.map((t) => right(t) + '|' + left(t));
}}
""")
        m.demo(f, [lit(rng.sample(m.nouns, 3))])
    else:
        f = m.fn("capped")
        lo, hi = rng.choice([(0, 50), (-10, 40), (5, 100)])
        both(m, f"""
function {f}(deltas) {{
  return deltas.reduce((acc, x) => {I.call("clamp")}(acc + x, {lo}, {hi}), 0);
}}
""", f"""
function {f}(deltas) {{
  return deltas.reduce((acc, x) => kit.data.limit(acc + x, {lo}, {hi}), 0);
}}
""")
        m.demo(f, [lit([rng.randint(-30, 60) for _ in range(6)])])


def sn_label(m: Mod):
    rng, I = m.rng, m.I
    f = m.fn("label")
    w = rng.choice([14, 16, 20])
    lo, hi = rng.choice([(3, 12), (1, 8)])
    both(m, f"""
function {f}(text) {{
  const shown = {I.call("padLeft")}({I.call("title")}(text), {w});
  return `${{shown}} [${{{I.call("clamp")}(text.length, {lo}, {hi})}}]`;
}}
""", f"""
function {f}(text) {{
  const shown = kit.text.pad(kit.text.titleCase(text), {w}, {{ align: 'right' }});
  return `${{shown}} [${{kit.data.limit(text.length, {lo}, {hi})}}]`;
}}
""")
    m.demo(f, [f"'{rng.choice(W.WORDS)}'", "'x'", "'a rather long description of a thing'"])


SNIPPETS = [sn_line_item, sn_line_item, sn_header_const, sn_qty, sn_qty, sn_log, sn_log, sn_pick, sn_pick, sn_group, sn_callbacks, sn_callbacks, sn_label]


def common_old(p: dict) -> str:
    return """'use strict';
// Shared helpers: thin wrappers around oldkit that most of the application imports.
const oldkit = require('../oldkit');

module.exports = {
  fmtAmount: oldkit.fmtAmount,
  parseQty: oldkit.parseQty,
  padRight: oldkit.padRight,
  padLeft: oldkit.padLeft,
  title: oldkit.title,
  cmpNames: oldkit.cmpNames,
  pick: oldkit.pick,
  take: oldkit.take,
  groupBy: oldkit.groupBy,
  log: oldkit.log,
  flushLog: oldkit.flushLog,
  clamp: oldkit.clamp,
};
"""


def common_new(p: dict) -> str:
    return f"""'use strict';
// Shared helpers: wrappers with the historical signatures, now backed by kit.
const kit = require('../kit');

module.exports = {{
  fmtAmount: (cents, cur = '{p['cur']}') => new kit.money.Money(cents, cur).text(),
  parseQty: (text) => {{
    const q = kit.qty.Qty.tryParse(text);
    return q === null ? null : [q.count, q.unit];
  }},
  padRight: (s, width) => kit.text.pad(s, width, {{ align: 'left' }}),
  padLeft: (s, width) => kit.text.pad(s, width, {{ align: 'right' }}),
  title: (s) => kit.text.titleCase(s),
  cmpNames: (a, b) => kit.text.compare(a, b),
  pick: (obj, ...keys) => kit.data.dig(obj, keys, undefined),
  take: (seq, n) => kit.data.first(seq, n),
  groupBy: (items, keyfn) => Object.fromEntries(kit.data.group(items, keyfn)),
  log: (level, msg, ctx = {{}}) => {{
    const events = kit.events.default();
    events.emit(level, msg, ctx);
    return events.last();
  }},
  flushLog: () => kit.events.default().drain(),
  clamp: (x, lo, hi) => kit.data.limit(x, lo, hi),
}};
"""


RUN_JS = """'use strict';
// Runs the demo of one module of the application and prints its lines:  node run.js MODULE   (or: node run.js all)
const { MODULES } = require('./app');

function main(argv) {
  const names = argv.length === 1 && argv[0] === 'all' ? MODULES : argv;
  let status = 0;
  for (const name of names) {
    try {
      for (const line of require('./app/' + name).demo()) console.log(line);
    } catch (e) {
      console.log(`error: ${e.constructor.name}: ${e.message}`);
      status = 1;
    }
  }
  return status;
}

process.exitCode = main(process.argv.slice(2));
"""


def build_app(rng: random.Random, p: dict) -> dict:
    names = rng.sample(W.MODULE_NAMES, p["n_modules"])
    use_common = p["common"]
    start: dict[str, str] = {}
    solution: dict[str, str] = {}
    direct = []
    styles = ["plain", "plain", "alias", "destructure", "falias"] if p["shapes"] else ["plain", "plain", "alias"]
    for name in names:
        style = "common" if use_common and rng.random() < p["common_share"] else rng.choice(styles)
        m = Mod(name, style, rng, p)
        for fn in rng.sample(SNIPPETS, rng.randint(p["min_snip"], p["max_snip"])):
            fn(m)
        start[f"app/{name}.js"] = m.source(False)
        if style != "common":
            solution[f"app/{name}.js"] = m.source(True)
            direct.append(name)
    start["app/index.js"] = "'use strict';\n// The shop application: one demo module per workshop.\nmodule.exports = { MODULES: [" + ", ".join(f"'{n}'" for n in names) + "] };\n"
    start["oldkit.js"] = oldkit_source(p)
    start.update(kit_files(p))
    start["run.js"] = RUN_JS
    if use_common:
        start["app/common.js"] = common_old(p)
        solution["app/common.js"] = common_new(p)
    return {"start": start, "solution": solution, "modules": names, "direct": direct}
