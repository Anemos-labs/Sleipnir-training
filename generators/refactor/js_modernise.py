"""Modernise legacy JavaScript (ES5 idioms to current syntax) while behaviour stays the same."""
from __future__ import annotations

import json
from string import Template

from fx import Task, dd, family, merged, run

from . import _kit
from ._kit import clike_lib, prove

NOUNS = [("order", "orderbook"), ("beehive", "apiary"), ("shelf", "library"), ("tram", "depot"), ("stall", "market"), ("pump", "waterworks"), ("loom", "mill"), ("kiln", "pottery")]

IDIOMS = {
    "var": dict(
        legacy='''function ${n}Summary(items) {
  var total = 0;
  var names = [];
  items.forEach(function (item) {
    total += item.qty;
    names.push(item.name);
  });
  return names.join(',') + ':' + total;
}
''', modern='''function ${n}Summary(items) {
  let total = 0;
  const names = [];
  items.forEach((item) => {
    total += item.qty;
    names.push(item.name);
  });
  return `${names.join(',')}:${total}`;
}
''', calls=lambda r: [["${n}Summary", [[{"name": r.choice("abcdef"), "qty": r.randrange(0, 9)} for _ in range(r.randrange(0, 5))]]] for _ in range(3)],
        checks=["var", "anon_function", "concat"], bullet=["`var` becomes `const`/`let`", "anonymous `function` callbacks become arrow functions", "string building with `+` uses template literals"]),
    "class": dict(
        legacy='''function ${N}Counter(name) {
  this.name = name;
  this.count = 0;
}

${N}Counter.prototype.add = function add(n) {
  this.count += n === undefined ? 1 : n;
  return this;
};

${N}Counter.prototype.describe = function describe() {
  return this.name + ' counted ' + this.count;
};

function ${n}CounterDemo(name, steps) {
  const c = new ${N}Counter(name);
  steps.forEach(function (s) { c.add(s); });
  return c.describe();
}
''', modern='''class ${N}Counter {
  constructor(name) {
    this.name = name;
    this.count = 0;
  }

  add(n) {
    this.count += n === undefined ? 1 : n;
    return this;
  }

  describe() {
    return `${this.name} counted ${this.count}`;
  }
}

function ${n}CounterDemo(name, steps) {
  const c = new ${N}Counter(name);
  steps.forEach((s) => { c.add(s); });
  return c.describe();
}
''', calls=lambda r: [["${n}CounterDemo", [r.choice(["bees", "tickets", "jars"]), [r.randrange(1, 5) for _ in range(r.randrange(0, 6))]]] for _ in range(3)],
        checks=["prototype", "anon_function", "concat"], bullet=["constructor functions with `.prototype` methods become `class`es", "anonymous `function` callbacks become arrow functions",
                                                                 "string building with `+` uses template literals"], exports=[]),
    "arguments": dict(
        legacy='''function ${n}Total() {
  var sum = 0;
  for (var i = 0; i < arguments.length; i++) {
    sum += arguments[i];
  }
  return sum;
}

function ${n}Longest() {
  var best = '';
  Array.prototype.slice.call(arguments).forEach(function (s) {
    if (s.length > best.length) best = s;
  });
  return best;
}
''', modern='''function ${n}Total(...values) {
  let sum = 0;
  for (const v of values) {
    sum += v;
  }
  return sum;
}

function ${n}Longest(...words) {
  let best = '';
  words.forEach((s) => {
    if (s.length > best.length) best = s;
  });
  return best;
}
''', calls=lambda r: [["${n}Total", [r.randrange(0, 9) for _ in range(r.randrange(0, 5))]] for _ in range(3)] + [["${n}Longest", [r.choice(["a", "bb", "ccc", "dd"]) for _ in range(r.randrange(0, 5))]] for _ in range(3)],
        checks=["arguments", "var", "anon_function", "index_loop", "prototype_slice"], bullet=["`arguments` becomes rest parameters", "index-based `for` loops become `for...of` or array methods", "`var` becomes `const`/`let`",
                                                                                         "anonymous `function` callbacks become arrow functions"]),
    "equality": dict(
        legacy='''function ${n}Match(a, b) {
  if (a == b) return 'same';
  if (a != null && b != null && a.length == b.length) return 'samelength';
  return 'different';
}
''', modern='''function ${n}Match(a, b) {
  if (a === b) return 'same';
  if (a !== null && b !== null && a.length === b.length) return 'samelength';
  return 'different';
}
''', calls=lambda r: [["${n}Match", [a, b]] for a, b in [("ab", "ab"), ("ab", "cd"), ("ab", "abc"), (None, "x"), ([1, 2], [3, 4]), (None, None)]],
        checks=["loose_eq"], bullet=["loose `==`/`!=` become `===`/`!==` (the inputs never mix types, apart from `null`, which the tests do not pass as `undefined`)"]),
    "includes": dict(
        legacy='''function ${n}Allowed(list, item) {
  return list.indexOf(item) !== -1;
}

function ${n}Forbidden(list, item) {
  if (list.indexOf(item) < 0) {
    return false;
  }
  return true;
}
''', modern='''function ${n}Allowed(list, item) {
  return list.includes(item);
}

function ${n}Forbidden(list, item) {
  return list.includes(item);
}
''', calls=lambda r: [["${n}Allowed", [["a", "b", "c"], r.choice(["a", "z"])]] for _ in range(3)] + [["${n}Forbidden", [["x", "y"], r.choice(["x", "q"])]] for _ in range(3)],
        checks=["indexof"], bullet=["`indexOf(...) !== -1` style membership tests use `includes`"]),
    "assign": dict(
        legacy='''function ${n}Merge(defaults, overrides) {
  return Object.assign({}, defaults, overrides, { merged: true });
}

function ${n}Keys(obj) {
  var out = [];
  Object.keys(obj).forEach(function (k) {
    out.push(k + '=' + obj[k]);
  });
  return out.sort();
}
''', modern='''function ${n}Merge(defaults, overrides) {
  return { ...defaults, ...overrides, merged: true };
}

function ${n}Keys(obj) {
  return Object.entries(obj).map(([k, v]) => `${k}=${v}`).sort();
}
''', calls=lambda r: [["${n}Merge", [{"a": 1, "b": 2}, {"b": r.randrange(5, 9), "c": 3}]] for _ in range(2)] + [["${n}Keys", [{"x": 1, "y": r.randrange(0, 9)}]], ["${n}Keys", [{}]]],
        checks=["object_assign", "anon_function", "var", "concat"], bullet=["`Object.assign({}, ...)` becomes object spread", "anonymous `function` callbacks become arrow functions", "`var` becomes `const`/`let`",
                                                                          "string building with `+` uses template literals"]),
    "defaults": dict(
        legacy='''function ${n}Label(name, options) {
  options = options || {};
  var prefix = options.prefix || '#';
  var width = options.width === undefined ? 8 : options.width;
  var text = prefix + name;
  while (text.length < width) {
    text = text + '.';
  }
  return text;
}
''', modern='''function ${n}Label(name, { prefix = '#', width = 8 } = {}) {
  let text = `${prefix}${name}`;
  while (text.length < width) {
    text = `${text}.`;
  }
  return text;
}
''', calls=lambda r: [["${n}Label", [r.choice(["ab", "north", "x7"])] + ([{"prefix": r.choice(["@", "no."]), "width": r.randrange(0, 12)}] if r.random() < 0.6 else [])] for _ in range(5)],
        checks=["options_or", "var", "concat"], bullet=["`options = options || {}` style fallbacks become default parameters (callers pass either an object or nothing)", "`var` becomes `const`/`let`",
                                                       "string building with `+` uses template literals"]),
    "literals": dict(
        legacy='''function ${n}Buckets(values) {
  var buckets = new Array();
  var index = new Object();
  for (var i = 0; i < values.length; i++) {
    var key = values[i] % 3;
    if (index[key] === undefined) {
      index[key] = buckets.length;
      buckets.push([]);
    }
    buckets[index[key]].push(values[i]);
  }
  return buckets;
}
''', modern='''function ${n}Buckets(values) {
  const buckets = [];
  const index = {};
  for (const v of values) {
    const key = v % 3;
    if (index[key] === undefined) {
      index[key] = buckets.length;
      buckets.push([]);
    }
    buckets[index[key]].push(v);
  }
  return buckets;
}
''', calls=lambda r: [["${n}Buckets", [[r.randrange(0, 30) for _ in range(r.randrange(0, 9))]]] for _ in range(4)],
        checks=["new_array", "var", "index_loop"], bullet=["`new Array()` / `new Object()` become literals", "`var` becomes `const`/`let`", "index-based `for` loops become `for...of` or array methods"]),
}

CHECK_RE = {
    "var": (r"\bvar\b", "a `var` declaration"),
    "anon_function": (r"\bfunction\s*\(", "an anonymous `function` expression"),
    "concat": (r"['\"`]\s*\+\s*[\w(\[]|[\w)\]]\s*\+\s*['\"`]", "string concatenation with `+`"),
    "prototype": (r"\.prototype\b", "`.prototype`"),
    "arguments": (r"\barguments\b", "`arguments`"),
    "prototype_slice": (r"Array\.prototype\.slice\.call", "`Array.prototype.slice.call`"),
    "index_loop": (r"\bfor\s*\(\s*(?:var|let)\s+\w+\s*=\s*0", "an index-based for loop"),
    "loose_eq": (r"(?<![=!<>])[=!]=(?!=)", "a loose equality operator"),
    "indexof": (r"\.indexOf\(", "`indexOf`"),
    "object_assign": (r"\bObject\.assign\(", "`Object.assign`"),
    "options_or": (r"=\s*\w+\s*\|\|\s*(?:\{\}|\[\]|['\"\d])", "an `x = x || fallback` default"),
    "new_array": (r"\bnew\s+(?:Array|Object)\s*\(\s*\)", "`new Array()` / `new Object()`"),
}

PROMPTS = [
    "`{path}` is ES5-era code. Bring it up to modern JavaScript without changing what it does:\n{bullets}\nExported names and behaviour stay the same.",
    "Please modernise `{path}` ({topic} helpers). Only the syntax changes; the results for all inputs must stay identical. What to update:\n{bullets}",
    "Our {topic} helpers in `{path}` predate ES6. Update them as follows and keep behaviour exactly as is:\n{bullets}",
    "lint cleanup of `{path}`:\n{bullets}\nno behaviour change, same exports.",
]

HARNESS = '''const m = require('../{path}');
const CASES = {cases};
function outcome(c) {{
  try {{
    return {{ value: m[c[0]](...c[1]) }};
  }} catch (e) {{
    return {{ error: e.name }};
  }}
}}
'''


@family("refactor-js-modernise", category="refactor", lang="javascript", kind="refactor", n=10,
        summary="ES5 idioms (var, prototypes, arguments, concatenation, loose equality, Object.assign, ...) become modern syntax, same behaviour")
def gen(rng, n):
    for i in range(n):
        noun, place = NOUNS[i % len(NOUNS)]
        keys = rng.sample(list(IDIOMS), rng.choice([2, 3, 3, 4, 5, 6, 7]) if i % 4 else rng.choice([2, 3]))
        keys.sort(key=list(IDIOMS).index)
        N = noun.capitalize()
        path = f"src/{noun}utils.js"

        def build(kind):
            blocks = [Template(IDIOMS[x][kind]).safe_substitute(n=noun, N=N) for x in keys]
            names = []
            for b in blocks:
                for ln in b.splitlines():
                    if ln.startswith("function "):
                        names.append(ln.split("(")[0].split()[1])
            return "'use strict';\n\n" + "\n".join(blocks) + "\nmodule.exports = { " + ", ".join(dict.fromkeys(names)) + " };\n"
        legacy, modern = build("legacy"), build("modern")
        calls = []
        for x in keys:
            for c in IDIOMS[x]["calls"](rng):
                calls.append([c[0].replace("${n}", noun), c[1]])
        files = {path: legacy, "package.json": json.dumps({"name": noun + "utils", "version": "1.0.0", "private": True}, indent=2) + "\n"}
        harness_js = HARNESS.format(path=path, cases=json.dumps(calls))
        gold_script = harness_js + "console.log(JSON.stringify(CASES.map(outcome)));\n"
        gold_script = gold_script.replace("../src/", "./src/")
        r = run(merged(files, {"_golden.js": gold_script}), "node _golden.js", timeout=60)
        if not r.ok:
            raise RuntimeError("golden failed:\n" + r.out[-1500:])
        want = json.loads(r.out.strip().splitlines()[-1])
        hid = ("'use strict';\nconst test = require('node:test');\nconst assert = require('node:assert');\n" + harness_js
               + f"const WANT = {json.dumps(want)};\n\ntest('every recorded call gives the same outcome', () => {{\n  for (let i = 0; i < CASES.length; i++) {{\n"
                 "    assert.deepStrictEqual(JSON.parse(JSON.stringify(outcome(CASES[i]))), WANT[i], 'case ' + i + ': ' + JSON.stringify(CASES[i]));\n  }\n});\n")
        pick = list(range(0, len(calls), max(1, len(calls) // 4)))[:4]
        vis = ("'use strict';\nconst test = require('node:test');\nconst assert = require('node:assert');\n" + HARNESS.format(path=path, cases=json.dumps([calls[j] for j in pick]))
               + f"const WANT = {json.dumps([want[j] for j in pick])};\n\ntest('examples', () => {{\n  for (let i = 0; i < CASES.length; i++) {{\n"
                 "    assert.deepStrictEqual(JSON.parse(JSON.stringify(outcome(CASES[i]))), WANT[i]);\n  }\n});\n")
        checks = sorted({c for x in keys for c in IDIOMS[x]["checks"]})
        struct = dd(f'''
        import re

        import clike as C

        FILES = C.files([".js"], dirs=["src"])
        CHECKS = {json.dumps({c: CHECK_RE[c] for c in checks})}
        problems = []
        text = "\\n".join(C.clean(C.read(f), "javascript") for f in FILES)
        for key, (pat, what) in CHECKS.items():
            for m in re.finditer(pat, text):
                line = text.count("\\n", 0, m.start()) + 1
                problems.append("line %d: %s" % (line, what))
        C.report(problems[:12])
        ''')
        hidden = {"test/recorded.test.js": hid, "checks/structure.py": struct, **clike_lib()}
        start = {**files, "test/examples.test.js": vis}
        sol = {path: modern}
        prove(noun, start, hidden, sol, _kit.JS_BEHAVIOUR_CMD, _kit.JS_STRUCT_CMD, _kit.JS_FULL_CMD)
        seen, bullets = set(), []
        for x in keys:
            for b in IDIOMS[x]["bullet"]:
                if b not in seen:
                    seen.add(b)
                    bullets.append("- " + b)
        prompt = rng.choice(PROMPTS).format(path=path, topic=place, bullets="\n".join(bullets))
        d = 1 if len(bullets) <= 3 else 2 if len(bullets) <= 5 else 3 if len(bullets) <= 7 else 4
        yield Task(slug=f"{i + 1:02d}-{noun}-{len(keys)}blocks", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=sol, verify=_kit.JS_FULL_CMD,
                   tags=["modernise", "es6", "template-literals", "classes"], notes={"idioms": keys})
