"""JSDoc (javascript): every exported function documented with @param (names in order), @returns when it returns a value and @throws for what it throws; code untouched."""
from __future__ import annotations

import json
import re

from fx import Task, dd, family, merged, run

from ._kit import prove_docs

CMD = "node --test test/*.test.js && python3 checks/jsdoc.py"

MODULES = [
    dict(key="seedbank", file="src/inventory.js", summary="Stock keeping for a community seed bank.", fns=[
        dict(name="parseSku", src='''function parseSku(code) {
  const [prefix, rest] = code.split('-');
  if (!['VEG', 'HRB', 'FLW'].includes(prefix) || !/^[0-9]+$/.test(rest || '')) {
    throw new Error('bad sku: ' + code);
  }
  return [prefix, Number(rest)];
}
''', summary="Split a SKU such as `VEG-0042` into its prefix and number.", params={"code": ("string", "the SKU text")}, returns=("[string, number]", "the prefix and the number"),
             throws={"Error": "if the prefix is unknown or the number part is not made of digits"}, test="parseSku('VEG-0042')"),
        dict(name="addLot", src='''function addLot(stock, sku, qty) {
  if (qty <= 0) throw new RangeError('quantity must be positive');
  parseSku(sku);
  stock[sku] = (stock[sku] || 0) + qty;
  return stock[sku];
}
''', summary="Add packets of a SKU to the stock.", params={"stock": ("Object<string, number>", "packet counts per SKU, modified in place"), "sku": ("string", "the SKU to add to"),
                                                              "qty": ("number", "number of packets, must be positive")}, returns=("number", "the new packet count of the SKU"),
             throws={"RangeError": "if qty is not positive"}, test="addLot({}, 'VEG-1', 3)"),
        dict(name="lowStock", src='''function lowStock(stock, threshold = 5) {
  return Object.keys(stock).filter((sku) => stock[sku] < threshold).sort();
}
''', summary="List the SKUs that are running low.", params={"stock": ("Object<string, number>", "packet counts per SKU"), "threshold": ("number", "SKUs with fewer packets than this are low")},
             returns=("string[]", "the low SKUs in alphabetical order"), throws={}, test="lowStock({ 'VEG-1': 2, 'HRB-4': 9 })"),
        dict(name="totalPackets", src='''function totalPackets(stock) {
  return Object.values(stock).reduce((a, b) => a + b, 0);
}
''', summary="Count all packets in the stock.", params={"stock": ("Object<string, number>", "packet counts per SKU")}, returns=("number", "the total number of packets"), throws={},
             test="totalPackets({ 'VEG-1': 2, 'HRB-4': 9 })"),
        dict(name="formatLabel", src='''function formatLabel(sku, qty) {
  const [prefix, number] = parseSku(sku);
  return prefix + ' #' + String(number).padStart(4, '0') + ' x' + qty;
}
''', summary="Format the text printed on a packet label.", params={"sku": ("string", "the SKU of the packet"), "qty": ("number", "packets in the lot")},
             returns=("string", "the label text, for example `VEG #0042 x3`"), throws={}, test="formatLabel('VEG-42', 3)"),
    ]),
    dict(key="ferry", file="src/schedule.js", summary="Timetable helpers for the island ferry.", fns=[
        dict(name="parseTime", src='''function parseTime(text) {
  const m = /^([0-9]{1,2}):([0-9]{2})$/.exec(text);
  if (!m || Number(m[1]) > 23 || Number(m[2]) > 59) {
    throw new TypeError('expected HH:MM, got ' + text);
  }
  return Number(m[1]) * 60 + Number(m[2]);
}
''', summary="Convert `HH:MM` text to minutes after midnight.", params={"text": ("string", "a 24-hour time such as `07:45`")}, returns=("number", "minutes after midnight"),
             throws={"TypeError": "if the text is not HH:MM or is out of range"}, test="parseTime('07:45')"),
        dict(name="formatTime", src='''function formatTime(minutes) {
  const m = ((minutes % 1440) + 1440) % 1440;
  return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
}
''', summary="Convert minutes after midnight to `HH:MM`, wrapping past midnight.", params={"minutes": ("number", "minutes after midnight, may exceed one day")}, returns=("string", "the time as HH:MM"),
             throws={}, test="formatTime(1500)"),
        dict(name="nextDeparture", src='''function nextDeparture(times, now) {
  if (times.length === 0) return null;
  const sorted = [...times].sort((a, b) => a - b);
  const later = sorted.find((t) => t >= now);
  return later === undefined ? sorted[0] + 1440 : later;
}
''', summary="Find the next sailing at or after a given time.", params={"times": ("number[]", "departure times in minutes after midnight, any order"), "now": ("number", "the current time in minutes after midnight")},
             returns=("number|null", "the next departure, tomorrow's first one plus 1440 if none is left today, or null without sailings"), throws={}, test="nextDeparture([420, 600, 900], 500)"),
        dict(name="overlap", src='''function overlap(a, b) {
  return Math.max(0, Math.min(a[1], b[1]) - Math.max(a[0], b[0]));
}
''', summary="Minutes two time windows share.", params={"a": ("number[]", "first window as [start, end]"), "b": ("number[]", "second window as [start, end]")},
             returns=("number", "the shared minutes, 0 when the windows are disjoint"), throws={}, test="overlap([60, 120], [90, 200])"),
    ]),
    dict(key="tidelab", file="src/units.js", summary="Unit conversions and small statistics for the tide laboratory.", fns=[
        dict(name="toMetres", src='''function toMetres(value, unit) {
  if (unit === 'm') return value;
  if (unit === 'cm') return value / 100;
  if (unit === 'ft') return Math.round((value / 3.28084) * 10000) / 10000;
  throw new RangeError('unknown unit: ' + unit);
}
''', summary="Convert a length to metres.", params={"value": ("number", "the length"), "unit": ("string", "one of m, cm or ft")}, returns=("number", "the length in metres"),
             throws={"RangeError": "if the unit is not known"}, test="toMetres(250, 'cm')"),
        dict(name="clamp", src='''function clamp(value, low, high) {
  if (low > high) throw new RangeError('low must not exceed high');
  return Math.max(low, Math.min(high, value));
}
''', summary="Limit a value to a range.", params={"value": ("number", "the number to limit"), "low": ("number", "smallest allowed value"), "high": ("number", "largest allowed value")},
             returns=("number", "the value, or the nearest bound if it is outside"), throws={"RangeError": "if low is greater than high"}, test="clamp(5, 0, 3)"),
        dict(name="bucketize", src='''function bucketize(values, edges) {
  const counts = new Array(edges.length + 1).fill(0);
  for (const v of values) {
    let i = 0;
    while (i < edges.length && v >= edges[i]) i++;
    counts[i]++;
  }
  return counts;
}
''', summary="Count values per bucket.", params={"values": ("number[]", "the numbers to count"), "edges": ("number[]", "ascending bucket boundaries")},
             returns=("number[]", "one count per bucket, edges.length + 1 entries"), throws={}, test="bucketize([1, 5, 9, 10, 25], [5, 10])"),
        dict(name="normaliseName", src='''function normaliseName(name) {
  return name.replace(/_/g, ' ').split(/\\s+/).filter(Boolean).map((p) => p[0].toUpperCase() + p.slice(1).toLowerCase()).join(' ');
}
''', summary="Turn an identifier-like station name into a display name.", params={"name": ("string", "a name such as north_quay")}, returns=("string", "the name with spaces and capitals"),
             throws={}, test="normaliseName('north_quay')"),
    ]),
]

CHECK = r'''import json
import re

import clike as C

ORIGINAL = __ORIGINAL__
PATH = __PATH__
problems = []
src = C.read(PATH)
if re.sub(r"\s+", "", C.clean(src, "javascript")) != re.sub(r"\s+", "", C.clean(ORIGINAL, "javascript")):
    problems.append("the code changed: only comments may be added")
cleaned = C.clean(src, "javascript")
for m in re.finditer(r"^function\s+(\w+)\s*\(([^)]*)\)\s*\{", cleaned, re.M):
    name = m.group(1)
    params = [p.split("=")[0].strip() for p in m.group(2).split(",") if p.strip()]
    end = C.match_brace(cleaned, m.end() - 1)
    body = cleaned[m.end():end]
    before = src[:m.start()].rstrip()
    if not before.endswith("*/"):
        problems.append(name + ": no JSDoc block")
        continue
    block = before[before.rindex("/**"):] if "/**" in before else ""
    if not block:
        problems.append(name + ": the comment above is not a JSDoc block")
        continue
    lines = [re.sub(r"^\s*\*\s?", "", ln) for ln in block.strip("/*").split("\n")]
    text = "\n".join(lines)
    summary = next((ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("@")), "")
    if not summary:
        problems.append(name + ": no summary line")
    documented = re.findall(r"@param\s+\{([^}]+)\}\s+(\[?[\w.]+\]?)(?:\s*-)?\s+(\S.*)", text)
    names = [re.sub(r"[\[\]]|=.*", "", d[1]) for d in documented]
    if names != params:
        problems.append("%s: @param names %s do not match the parameters %s (same order)" % (name, names, params))
    for d in documented:
        if len(re.findall(r"\w+", d[2])) < 2:
            problems.append("%s: the description of @param %s is too short" % (name, d[1]))
    returns_value = bool(re.search(r"\breturn\s+[^;\s]", body))
    has_returns = bool(re.search(r"@returns?\s+\{[^}]+\}\s+\S", text))
    if returns_value != has_returns:
        problems.append(name + ": @returns must be present exactly when the function returns a value")
    thrown = set(re.findall(r"throw\s+new\s+(\w+)\(", body))
    documented_throws = set(re.findall(r"@throws\s+\{(\w+)\}\s+\S", text))
    if thrown != documented_throws:
        problems.append("%s: @throws lists %s but the function throws %s" % (name, sorted(documented_throws), sorted(thrown)))
modules = set(re.findall(r"^function\s+(\w+)", cleaned, re.M))
if not modules:
    problems.append("no functions found")
head = src.lstrip()
if not head.startswith("/**") and not head.startswith("/*") and not head.startswith("//"):
    problems.append("the file needs a header comment describing the module")
C.report(problems)
'''


def jsdoc(f):
    lines = ["/**", f" * {f['summary']}", " *"]
    for n, (t, d) in f["params"].items():
        lines.append(f" * @param {{{t}}} {n} - {d}")
    if f["returns"]:
        lines.append(f" * @returns {{{f['returns'][0]}}} {f['returns'][1][0].upper() + f['returns'][1][1:]}")
    for t, d in f["throws"].items():
        lines.append(f" * @throws {{{t}}} {d[0].upper() + d[1:]}")
    lines.append(" */")
    return "\n".join(lines) + "\n"


def module_text(mod, funcs, documented):
    head = f"/** {mod['summary']} */\n" if documented else ""
    out = head + "'use strict';\n\n"
    for f in funcs:
        out += (jsdoc(f) if documented else "") + f["src"] + "\n"
    out += "module.exports = { " + ", ".join(f["name"] for f in funcs) + " };\n"
    return out


PROMPTS = [
    "None of the functions in `{path}` have documentation. Add JSDoc blocks: a one-line summary, one `@param` tag per parameter in signature order (type in curly braces, name, description), "
    "an `@returns` tag (type in braces, description) for functions that return a value, and an `@throws` tag (error class in braces, description) for each error type the function throws itself. "
    "Also give the file a header comment. The doc checker compares the tags with the code, so they must be accurate. Code must stay exactly as it is.",
    "docs: JSDoc for everything in `{path}`. Tags have to match what the code does: all params (in order, with a type and a description), `@returns` only when there is a returned value, `@throws` for the "
    "errors thrown in the function body. Add a short file header comment too. No code changes.",
]


@family("docs-js-jsdoc", category="docs", lang="javascript", kind="feature", n=4,
        summary="JSDoc blocks whose @param/@returns/@throws tags must match the code (checked mechanically); code unchanged")
def gen(rng, n):
    mods = list(MODULES) + [rng.choice(MODULES)]
    rng.shuffle(mods)
    for i in range(n):
        mod = mods[i]
        funcs = list(mod["fns"])
        if i == 3:
            funcs = funcs[:3] if len(funcs) > 3 else funcs
        path = mod["file"]
        original = module_text(mod, funcs, False)
        solved = module_text(mod, funcs, True)
        ns_script = f"const m = require('./{path}');\nconsole.log(JSON.stringify([{', '.join('m.' + f['test'] for f in funcs)}]));\n"
        files = {path: original, "package.json": json.dumps({"name": mod["key"], "private": True}) + "\n"}
        r = run(merged(files, {"_probe.js": ns_script}), "node _probe.js", timeout=60)
        if not r.ok:
            raise RuntimeError("probe failed:\n" + r.out[-1000:])
        vals = json.loads(r.out.strip().splitlines()[-1])
        vis = ("'use strict';\nconst test = require('node:test');\nconst assert = require('node:assert');\n" + f"const m = require('../{path}');\n\n"
               + "".join(f"test('{f['name']}', () => {{\n  assert.deepStrictEqual(m.{f['test']}, {json.dumps(v)});\n}});\n\n" for f, v in zip(funcs[:3], vals)))
        from generators.refactor import _kit as rk
        start = {**files, "test/behaviour.test.js": vis}
        check = CHECK.replace("__ORIGINAL__", repr(original)).replace("__PATH__", repr(path))
        hidden = {"checks/jsdoc.py": check, **rk.clike_lib()}
        solution = {path: solved}
        prove_docs(f"{mod['key']}-{i}", start, hidden, solution, CMD, "node --test test/*.test.js")
        yield Task(slug=f"{i + 1:02d}-{mod['key']}-{len(funcs)}fn", prompt=rng.choice(PROMPTS).format(path=path), difficulty=2 if len(funcs) <= 3 else 3, start=start, hidden=hidden, solution=solution, verify=CMD,
                   tags=["jsdoc", "tags", "documentation"], notes={"module": mod["key"], "functions": [f["name"] for f in funcs]})
