"""JavaScript functions with quadratic behaviour (list scans, object spread, concat in reduce, insertion by splice).
The hidden perf test runs the function on a large generated input in a child process with a generous timeout: the slow version needs minutes."""
from __future__ import annotations

import json
from string import Template

from fx import Task, family, merged, run

from ._kit import prove_opt

JS_ALL = "node --test test/*.test.js"
JS_CORRECT = "node --test test/basic.test.js test/correct.test.js"
JS_PERF = "node --test test/perf.test.js"

SHAPES = {
    "dedupe": dict(
        d=1, args=1, big="[Array.from({ length: n }, () => 'id-' + rnd(Math.floor(n / 2)))]", small="[Array.from({ length: rnd(25) }, () => 'k' + rnd(8))]", n=250000,
        naive='''function $f($a) {
  const out = [];
  for (const item of $a) {
    if (!out.includes(item)) out.push(item);
  }
  return out;
}
''', fast='''function $f($a) {
  return [...new Set($a)];
}
''', oracle='''function oracle(a) {
  const seen = new Set();
  const out = [];
  for (const x of a) {
    if (!seen.has(x)) { seen.add(x); out.push(x); }
  }
  return out;
}''', spec="Returns the items of `{a}` in order of first appearance, without repeats. Items are strings.",
        vocab=[("uniquePlates", ["plates"], "Licence plates seen at the gate, each once."), ("distinctTags", ["tags"], "The tags used in a photo set, each once, in order of first use."),
               ("firstSeenHosts", ["hosts"], "Host names in order of first appearance in a log.")]),
    "intersect": dict(
        d=2, args=2, big="[Array.from({ length: n }, () => 'u' + rnd(n)), Array.from({ length: n }, () => 'u' + rnd(n))]", n=160000,
        small="[Array.from({ length: rnd(15) }, () => 'u' + rnd(10)), Array.from({ length: rnd(15) }, () => 'u' + rnd(10))]",
        naive='''function $f($a, $b) {
  return $a.filter((item) => $b.includes(item));
}
''', fast='''function $f($a, $b) {
  const lookupSet = new Set($b);
  return $a.filter((item) => lookupSet.has(item));
}
''', oracle='''function oracle(a, b) {
  const s = new Set(b);
  return a.filter((x) => s.has(x));
}''', spec="Returns, in the order of `{a}` (repeats included), the items of `{a}` that also occur in `{b}`. Items are strings.",
        vocab=[("repliedGuests", ["invited", "replied"], "Invited guests who have replied."), ("sharedFollowers", ["mine", "theirs"], "Accounts that follow both of us."),
               ("stockedItems", ["wanted", "inStock"], "Wanted items that are in stock.")]),
    "difference": dict(
        d=2, args=2, big="[Array.from({ length: n }, () => 'u' + rnd(n)), Array.from({ length: n }, () => 'u' + rnd(n))]", n=160000,
        small="[Array.from({ length: rnd(15) }, () => 'u' + rnd(10)), Array.from({ length: rnd(15) }, () => 'u' + rnd(10))]",
        naive='''function $f($a, $b) {
  const out = [];
  for (const item of $a) {
    if (!$b.includes(item)) out.push(item);
  }
  return out;
}
''', fast='''function $f($a, $b) {
  const blockedSet = new Set($b);
  const out = [];
  for (const item of $a) {
    if (!blockedSet.has(item)) out.push(item);
  }
  return out;
}
''', oracle='''function oracle(a, b) {
  const s = new Set(b);
  return a.filter((x) => !s.has(x));
}''', spec="Returns, in the order of `{a}` (repeats included), the items of `{a}` that do not occur in `{b}`. Items are strings.",
        vocab=[("unsentRecipients", ["recipients", "alreadySent"], "Recipients that have not been mailed yet."), ("missingParts", ["required", "onHand"], "Parts that are required but not on hand."),
               ("unreviewedFiles", ["changed", "reviewed"], "Changed files that nobody has reviewed.")]),
    "join": dict(
        d=3, args=2, n=160000,
        big="[Array.from({ length: n }, (_, i) => ({ id: i, customerId: 'c' + rnd(n) })), Array.from({ length: n }, (_, i) => ({ id: 'c' + rnd(n), name: 'n' + i }))]",
        small="[Array.from({ length: rnd(12) }, (_, i) => ({ id: i, customerId: 'c' + rnd(8) })), Array.from({ length: rnd(10) }, (_, i) => ({ id: 'c' + rnd(8), name: 'n' + i }))]",
        naive='''function $f($a, $b) {
  const out = [];
  for (const order of $a) {
    const owner = $b.find((c) => c.id === order.customerId);
    if (owner) out.push([order.id, owner.name]);
  }
  return out;
}
''', fast='''function $f($a, $b) {
  const names = new Map();
  for (const c of $b) {
    if (!names.has(c.id)) names.set(c.id, c.name);
  }
  const out = [];
  for (const order of $a) {
    if (names.has(order.customerId)) out.push([order.id, names.get(order.customerId)]);
  }
  return out;
}
''', oracle='''function oracle(a, b) {
  const names = new Map();
  for (const c of b) if (!names.has(c.id)) names.set(c.id, c.name);
  return a.filter((o) => names.has(o.customerId)).map((o) => [o.id, names.get(o.customerId)]);
}''', spec="`{a}` holds `{{ id, customerId }}` records and `{b}` holds `{{ id, name }}` records. Returns `[id, name]` for every record of `{a}` whose `customerId` equals the `id` of a record in `{b}` (the first such record if several), in the order of `{a}`; records without a match are left out.",
        vocab=[("orderNames", ["orders", "customers"], "Pair every order with the name of its customer."), ("ticketOwners", ["tickets", "staff"], "Pair every ticket with the assigned person's name."),
               ("loanBorrowers", ["loans", "members"], "Pair every loan with the borrower's name.")]),
    "dupes": dict(
        d=2, args=1, big="[Array.from({ length: n }, () => 'e' + rnd(n))]", small="[Array.from({ length: rnd(25) }, () => 'e' + rnd(10))]", n=150000,
        naive='''function $f($a) {
  return $a.filter((item, i) => $a.indexOf(item) !== i);
}
''', fast='''function $f($a) {
  const seen = new Set();
  const out = [];
  for (const item of $a) {
    if (seen.has(item)) out.push(item);
    else seen.add(item);
  }
  return out;
}
''', oracle='''function oracle(a) {
  const seen = new Set();
  const out = [];
  for (const x of a) { if (seen.has(x)) out.push(x); else seen.add(x); }
  return out;
}''', spec="Returns the entries of `{a}` that already appeared earlier in the list (every repeat, in order of appearance). Items are strings.",
        vocab=[("repeatScans", ["scans"], "Barcode scans that repeat an earlier scan."), ("doubleBookings", ["slots"], "Slot ids that were booked more than once (every repeat)."),
               ("echoedEvents", ["events"], "Events that are repeats of earlier events.")]),
    "spread": dict(
        d=3, args=1, n=30000, big="[Array.from({ length: n }, (_, i) => ({ id: 'k' + i, value: rnd(1000) }))]", small="[Array.from({ length: rnd(10) }, (_, i) => ({ id: 'k' + rnd(6), value: rnd(100) }))]",
        naive='''function $f($a) {
  return $a.reduce((acc, item) => ({ ...acc, [item.id]: item.value }), {});
}
''', fast='''function $f($a) {
  const out = {};
  for (const item of $a) {
    out[item.id] = item.value;
  }
  return out;
}
''', oracle='''function oracle(a) {
  const out = {};
  for (const it of a) out[it.id] = it.value;
  return out;
}''', spec="`{a}` holds `{{ id, value }}` records. Returns an object mapping every `id` to its `value` (the last record wins when an id repeats).",
        vocab=[("indexById", ["records"], "Index records by id."), ("priceTable", ["rows"], "Build a lookup table from price rows."), ("settingsMap", ["entries"], "Turn a list of setting entries into an object.")]),
    "concat": dict(
        d=2, args=1, n=150000, big="[Array.from({ length: n }, () => ({ tags: [rnd(50), rnd(50), rnd(50)] }))]", small="[Array.from({ length: rnd(8) }, () => ({ tags: Array.from({ length: rnd(4) }, () => rnd(9)) }))]",
        naive='''function $f($a) {
  return $a.reduce((acc, item) => acc.concat(item.tags), []);
}
''', fast='''function $f($a) {
  const out = [];
  for (const item of $a) {
    for (const tag of item.tags) out.push(tag);
  }
  return out;
}
''', oracle='''function oracle(a) {
  const out = [];
  for (const it of a) out.push(...it.tags);
  return out;
}''', spec="Each record of `{a}` has a `tags` array. Returns all tags of all records as one flat array, in order.",
        vocab=[("allTags", ["photos"], "All tags of a photo set as one list."), ("flattenRoles", ["users"], "All roles of all users in one array."), ("collectLabels", ["items"], "All labels of all items.")]),
    "insertion": dict(
        d=3, args=1, n=200000, big="[Array.from({ length: n }, () => rnd(1000000))]", small="[Array.from({ length: rnd(20) }, () => rnd(30))]",
        naive='''function $f($a) {
  const out = [];
  for (const value of $a) {
    let at = out.findIndex((x) => x > value);
    if (at === -1) at = out.length;
    out.splice(at, 0, value);
  }
  return out;
}
''', fast='''function $f($a) {
  return [...$a].sort((x, y) => x - y);
}
''', oracle='''function oracle(a) {
  return [...a].sort((x, y) => x - y);
}''', spec="Returns the numbers of `{a}` in ascending order (`{a}` itself is not modified).",
        vocab=[("rankedScores", ["scores"], "Scores in ascending order."), ("sortedLatencies", ["samples"], "Latency samples in ascending order."), ("orderedPrices", ["prices"], "Prices in ascending order.")]),
}

PROMPTS = [
    "`{f}` in `{path}` is fast on small inputs and unusable on real ones: the nightly job with a few hundred thousand entries has been running for hours. {doc} "
    "Find the cause and fix it without changing what is returned (order included).",
    "perf: `{f}` ({path}) is quadratic. {doc} Make it linear. Same output, same order.",
    "I need `{f}` in `{path}` to scale: right now doubling the input quadruples the run time, and our import has 100k+ rows. {doc} Keep the results exactly as the README says. "
    "(CI runs it on a large input with a time limit that only a linear algorithm meets.)",
    "Could you speed up `{f}` ({path})? It does too much work per item. {doc} Don't change the signature or the output.",
]

DATA = '''// deterministic test data
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function makeRnd(seed) {
  const r = mulberry32(seed);
  return (k) => Math.floor(r() * k);
}

module.exports = { mulberry32, makeRnd };
'''


def _clone_js():
    return ("function clone(args) {\n  return args.map((x) => (Array.isArray(x) ? x.map((y) => (typeof y === 'object' && y !== null ? JSON.parse(JSON.stringify(y)) : y)) : x));\n}\n")


@family("optimize-js-scale", category="optimize", lang="javascript", kind="feature", n=10,
        summary="quadratic javascript (includes/indexOf/find in loops, object spread and concat in reduce, splice insertion): large input in a child process with a generous timeout")
def gen(rng, n):
    order = list(SHAPES) * 3
    rng.shuffle(order)
    used = set()
    for i in range(n):
        shape = order[i]
        sp = SHAPES[shape]
        vocab = [v for v in sp["vocab"] if (shape, v[0]) not in used] or sp["vocab"]
        f, argn, doc = rng.choice(vocab)
        used.add((shape, f))
        pkg = rng.choice(["feedtools", "ledgerkit", "importer", "roster", "gatehouse", "reportlib"])
        mod = rng.choice(["scan", "batch", "lookup", "reports"])
        path = f"src/{pkg}.js"
        names = {"f": f, "a": argn[0], "b": argn[1] if len(argn) > 1 else ""}
        naive = Template(sp["naive"]).substitute(names)
        fast = Template(sp["fast"]).substitute(names)
        wrap = lambda body: f"'use strict';\n\n{body}\nmodule.exports = {{ {f} }};\n"
        start_src = wrap(naive)
        sol_src = wrap(fast)
        spec = sp["spec"].format(a=argn[0], b=argn[1] if len(argn) > 1 else "")
        readme = f"# {pkg}\n\n## `{f}({', '.join(argn)})`\n\n{doc}\n\n{spec}\n\nInputs can hold hundreds of thousands of entries, so the work must grow about linearly with their size.\n"
        files = {path: start_src, "README.md": readme, "package.json": json.dumps({"name": pkg, "version": "1.0.0", "private": True}, indent=2) + "\n"}
        seed = 300 + i
        nargs = sp["args"]
        argsig = ", ".join("abc"[:nargs])
        small_fn = f"function smallArgs(rnd) {{\n  return {sp['small']};\n}}\n"
        big_fn = f"function bigArgs(rnd, n) {{\n  return {sp['big']};\n}}\n"
        oracle_js = sp["oracle"].replace("a", "a", 1)
        helpers = _clone_js()
        correct = (f"'use strict';\nconst test = require('node:test');\nconst assert = require('node:assert');\nconst {{ makeRnd }} = require('./data');\nconst {{ {f} }} = require('../{path}');\n\n"
                   f"{oracle_js}\n\n{helpers}\n{small_fn}\n"
                   f"test('matches the reference on random inputs', () => {{\n  const rnd = makeRnd({seed});\n  for (let i = 0; i < 150; i++) {{\n    const args = smallArgs(rnd);\n"
                   f"    assert.deepStrictEqual({f}(...clone(args)), oracle(...clone(args)), JSON.stringify(args));\n  }}\n}});\n\n"
                   f"test('empty inputs', () => {{\n  const args = {json.dumps([[]] * nargs)};\n  assert.deepStrictEqual({f}(...clone(args)), oracle(...clone(args)));\n}});\n")
        perf = (f"'use strict';\nconst test = require('node:test');\nconst assert = require('node:assert');\nconst path = require('node:path');\nconst {{ spawnSync }} = require('node:child_process');\n"
                f"const {{ makeRnd }} = require('./data');\n\n{oracle_js}\n\n{big_fn}\n"
                f"test('a large input is handled in reasonable time', () => {{\n  const n = {sp['n']};\n  const child = spawnSync(process.execPath, [path.join(__dirname, 'child.js')], {{ encoding: 'utf8', timeout: 8000, killSignal: 'SIGKILL', maxBuffer: 256 * 1024 * 1024 }});\n"
                "  if (child.error || child.signal) {\n    assert.fail('PERF: no answer within 8 seconds for ' + n + ' items: the function does far too much work per item');\n  }\n"
                "  assert.strictEqual(child.status, 0, child.stderr);\n  const got = JSON.parse(child.stdout);\n"
                f"  const want = oracle(...bigArgs(makeRnd({seed}), n));\n  assert.deepStrictEqual(got, JSON.parse(JSON.stringify(want)));\n}});\n")
        child = (f"'use strict';\nconst {{ makeRnd }} = require('./data');\nconst {{ {f} }} = require('../{path}');\n\n{big_fn}\nconst n = {sp['n']};\n"
                 f"const result = {f}(...bigArgs(makeRnd({seed}), n));\nprocess.stdout.write(JSON.stringify(result));\n")
        # visible tests with literal expectations (computed with node from the oracle)
        probe = (f"{oracle_js}\n{small_fn}\nconst {{ makeRnd }} = require('./test/data');\nconst rnd = makeRnd({700 + i});\nconst out = [];\n"
                 "for (let k = 0; k < 3; k++) { const a = smallArgs(rnd); out.push([a, oracle(...JSON.parse(JSON.stringify(a)))]); }\nconsole.log(JSON.stringify(out));\n")
        r = run(merged(files, {"test/data.js": DATA, "_probe.js": probe}), "node _probe.js", timeout=60)
        if not r.ok:
            raise RuntimeError("probe failed:\n" + r.out[-1500:])
        examples = json.loads(r.out.strip().splitlines()[-1])
        vis = f"'use strict';\nconst test = require('node:test');\nconst assert = require('node:assert');\nconst {{ {f} }} = require('../{path}');\n\n"
        for k, (args, want) in enumerate(examples):
            vis += f"test('example {k + 1}', () => {{\n  assert.deepStrictEqual({f}(...{json.dumps(args)}), {json.dumps(want)});\n}});\n\n"
        hidden = {"test/data.js": DATA, "test/correct.test.js": correct, "test/perf.test.js": perf, "test/child.js": child}
        start = {**files, "test/basic.test.js": vis}
        solution = {path: sol_src}
        prove_opt(f"{shape}/{f}", start, hidden, solution, JS_CORRECT, JS_PERF, JS_ALL, timeout=120, start_perf_timeout_ok=False)
        prompt = rng.choice(PROMPTS).format(f=f, path=path, doc=doc)
        yield Task(slug=f"{i + 1:02d}-{shape}-{f.lower()}", prompt=prompt, difficulty=sp["d"], start=start, hidden=hidden, solution=solution, verify=JS_ALL,
                   tags=["complexity", "quadratic", "timeout-bar"], notes={"shape": shape, "n": sp["n"]})
