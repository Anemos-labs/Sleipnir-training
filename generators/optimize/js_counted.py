"""JavaScript functions that read or call an expensive collaborator too often: element reads are counted with a Proxy, calls with a wrapper.
The counters carry a budget, so the slow start is cut off quickly."""
from __future__ import annotations

import json
from string import Template

from fx import Task, family, merged, run

from ._kit import prove_opt
from .js_scale import DATA, _clone_js

JS_ALL = "node --test test/*.test.js"
JS_CORRECT = "node --test test/basic.test.js test/correct.test.js"
JS_PERF = "node --test test/perf.test.js"

COUNTING = '''"use strict";
// Counters with a budget: reads of array elements (through a Proxy) and calls of wrapped functions.
class BudgetExceeded extends Error {}

const Ops = { reads: 0, budget: null };

function tick() {
  Ops.reads++;
  if (Ops.budget !== null && Ops.reads > Ops.budget) throw new BudgetExceeded("budget exceeded");
}

const isIndex = (p) => typeof p === "string" && p.length > 0 && p.charCodeAt(0) >= 48 && p.charCodeAt(0) <= 57;

function counted(arr) {
  return new Proxy(arr, {
    get(t, p, r) { if (isIndex(p)) tick(); return Reflect.get(t, p, r); },
    set(t, p, v, r) { if (isIndex(p)) tick(); return Reflect.set(t, p, v, r); },
    has(t, p) { if (isIndex(p)) tick(); return Reflect.has(t, p); },
    deleteProperty(t, p) { if (isIndex(p)) tick(); return Reflect.deleteProperty(t, p); },
  });
}

function countedFn(fn) {
  return (...args) => { tick(); return fn(...args); };
}

module.exports = { BudgetExceeded, Ops, counted, countedFn };
'''

SHAPES = {
    "rangeSums": dict(
        d=2, factor=3, n=(3000, 5000),
        prelude="",
        small="(() => { const s = Array.from({ length: 1 + rnd(20) }, () => rnd(50)); const q = Array.from({ length: rnd(6) }, () => { const lo = rnd(s.length + 1); return [lo, lo + rnd(s.length - lo + 1)]; }); return [s, q]; })()",
        big="(() => { const s = Array.from({ length: n }, () => rnd(1000)); const q = Array.from({ length: Math.floor(n / 10) }, () => { const lo = rnd(Math.floor(n / 2)); return [lo, lo + rnd(Math.floor(n / 4))]; }); return [s, q]; })()",
        wrap="[counted(a), b]", empty="[[], []]",
        naive='''function $f($a, $b) {
  return $b.map(([lo, hi]) => {
    let sum = 0;
    for (let i = lo; i < hi; i++) sum += $a[i];
    return sum;
  });
}
''', fast='''function $f($a, $b) {
  const prefix = [0];
  for (let i = 0; i < $a.length; i++) prefix.push(prefix[i] + $a[i]);
  return $b.map(([lo, hi]) => prefix[hi] - prefix[lo]);
}
''', oracle='''function oracle(a, b) {
  const arr = Array.from(a);
  return b.map(([lo, hi]) => arr.slice(lo, hi).reduce((x, y) => x + y, 0));
}''', spec="`{b}` is a list of `[lo, hi]` index pairs (`0 <= lo <= hi <= {a}.length`). Returns the sum of `{a}[lo..hi)` for every pair, in order. `{a}` is a lazily loaded series: every element access is a disk read, so read each element only a few times per call.",
        vocab=[("usageBetween", ["usage", "ranges"], "Energy used between pairs of meter readings."), ("salesInRanges", ["dailySales", "ranges"], "Total sales for each requested day range."),
               ("rainTotals", ["rainMm", "periods"], "Rainfall totals for each requested period.")]),
    "windowMeans": dict(
        d=2, factor=3, n=(3000, 5000), prelude="",
        small="[Array.from({ length: rnd(20) }, () => rnd(100)), 1 + rnd(5)]", big="[Array.from({ length: n }, () => rnd(1000)), 50]", wrap="[counted(a), b]", empty="[[], 3]",
        naive='''function $f($a, $b) {
  const out = [];
  for (let start = 0; start + $b <= $a.length; start++) {
    const window = $a.slice(start, start + $b);
    out.push(Math.floor(window.reduce((x, y) => x + y, 0) / $b));
  }
  return out;
}
''', fast='''function $f($a, $b) {
  const data = Array.from($a);
  const out = [];
  let total = 0;
  for (let i = 0; i < data.length; i++) {
    total += data[i];
    if (i >= $b) total -= data[i - $b];
    if (i >= $b - 1) out.push(Math.floor(total / $b));
  }
  return out;
}
''', oracle='''function oracle(a, b) {
  const arr = Array.from(a);
  const out = [];
  for (let i = 0; i + b <= arr.length; i++) out.push(Math.floor(arr.slice(i, i + b).reduce((x, y) => x + y, 0) / b));
  return out;
}''', spec="`{b}` is the window length (at least 1). Returns the integer mean (`Math.floor(sum / {b})`) of every window of `{b}` consecutive readings, left to right; empty when there are fewer than `{b}` readings. `{a}` is a lazily loaded series: every element access is a disk read.",
        vocab=[("smoothedLevels", ["readings", "window"], "Smooth a river level series with a moving average."), ("rollingLoad", ["samples", "span"], "Rolling mean of server load samples."),
               ("stepTrend", ["counts", "days"], "Rolling mean of daily step counts.")]),
    "totalPrice": dict(
        d=2, factor=0.25, n=(1500, 2500), prelude="const PRICE = (k) => String(k).length * 7 + (String(k).charCodeAt(0) % 13);",
        small="[Array.from({ length: rnd(15) }, () => [rnd(6), 1 + rnd(4)]), PRICE]", big="[Array.from({ length: n }, () => [rnd(40), 1 + rnd(8)]), PRICE]", wrap="[a, countedFn(b)]", empty="[[], PRICE]",
        naive='''function $f($a, $b) {
  let total = 0;
  for (const [key, qty] of $a) {
    total += $b(key) * qty;
  }
  return total;
}
''', fast='''function $f($a, $b) {
  const cache = new Map();
  let total = 0;
  for (const [key, qty] of $a) {
    if (!cache.has(key)) cache.set(key, $b(key));
    total += cache.get(key) * qty;
  }
  return total;
}
''', oracle='''function oracle(a, b) {
  return a.reduce((t, [k, q]) => t + b(k) * q, 0);
}''', spec="`{a}` is a list of `[key, quantity]` pairs and `{b}(key)` returns a unit price (an expensive lookup that always answers the same for the same key). Returns the sum of price times quantity.",
        vocab=[("basketTotal", ["lines", "priceOf"], "Total of a basket, pricing each line through the catalogue service."), ("orderValue", ["items", "unitPrice"], "Value of an order."),
               ("invoiceSum", ["rows", "rateFor"], "Sum of an invoice using the rate service.")]),
    "depths": dict(
        d=3, factor=2, n=(1200, 1800),
        prelude="const parents = (rnd, n) => { const p = [null]; for (let i = 1; i < n; i++) p.push(Math.max(0, i - 1 - rnd(39))); return (node) => p[node]; };",
        small="(() => { const n = 1 + rnd(12); return [Array.from({ length: n }, (_, i) => i), parents(rnd, n)]; })()", big="[Array.from({ length: n }, (_, i) => i), parents(rnd, n)]",
        wrap="[a, countedFn(b)]", empty="[[], parents(() => 0, 1)]",
        naive='''function $f($a, $b) {
  return $a.map((node) => {
    let depth = 0;
    for (let p = $b(node); p !== null; p = $b(p)) depth++;
    return depth;
  });
}
''', fast='''function $f($a, $b) {
  const known = new Map();
  const depthOf = (node) => {
    if (!known.has(node)) {
      const p = $b(node);
      known.set(node, p === null ? 0 : depthOf(p) + 1);
    }
    return known.get(node);
  };
  return $a.map(depthOf);
}
''', oracle='''function oracle(a, b) {
  const known = new Map();
  const d = (n) => { if (!known.has(n)) { const p = b(n); known.set(n, p === null ? 0 : d(p) + 1); } return known.get(n); };
  return a.map(d);
}''', spec="`{b}(node)` returns the parent of a node (an expensive lookup) or `null` for the root. Returns the depth of each node of `{a}` (root 0). Nodes are the integers `0..n-1`.",
        vocab=[("folderDepths", ["folders", "parentOf"], "Nesting depth of folders in a document store."), ("reportingLevels", ["staff", "managerOf"], "Levels below the CEO for each employee."),
               ("threadDepths", ["comments", "replyTo"], "Reply depth of comments in a discussion.")]),
    "drain": dict(
        d=1, factor=4, n=(3000, 6000), prelude="",
        small="[Array.from({ length: rnd(20) }, () => rnd(50))]", big="[Array.from({ length: n }, () => rnd(1000))]", wrap="[counted(a)]", empty="[[]]",
        naive='''function $f($a) {
  const done = [];
  while ($a.length > 0) {
    const job = $a.shift();
    done.push(job * 2 + 1);
  }
  return done;
}
''', fast='''function $f($a) {
  const done = [];
  for (const job of $a) {
    done.push(job * 2 + 1);
  }
  return done;
}
''', oracle='''function oracle(a) {
  return Array.from(a, (j) => j * 2 + 1);
}''', spec="Handles every job of `{a}` in order and returns the results (`job * 2 + 1`). The caller does not use `{a}` afterwards.",
        vocab=[("processJobs", ["queue"], "Work through the pending job queue."), ("drainEvents", ["events"], "Handle all queued events."), ("settlePayments", ["batch"], "Settle a batch of payments in arrival order.")]),
    "usable": dict(
        d=2, factor=1.0, n=(1500, 2500), prelude="const FETCH = (k) => (k % 5 === 0 ? null : { ok: k % 3 !== 0, v: k * 2 + 1 });",
        small="[Array.from({ length: rnd(15) }, () => rnd(40)), FETCH]", big="[Array.from({ length: n }, () => rnd(100000)), FETCH]", wrap="[a, countedFn(b)]", empty="[[], FETCH]",
        naive='''function $f($a, $b) {
  const out = [];
  for (const key of $a) {
    if ($b(key) !== null && $b(key).ok) out.push($b(key).v);
  }
  return out;
}
''', fast='''function $f($a, $b) {
  const out = [];
  for (const key of $a) {
    const record = $b(key);
    if (record !== null && record.ok) out.push(record.v);
  }
  return out;
}
''', oracle='''function oracle(a, b) {
  const out = [];
  for (const k of a) { const r = b(k); if (r !== null && r.ok) out.push(r.v); }
  return out;
}''', spec="`{b}(key)` is an expensive fetch returning `null` or `{{ ok, v }}`. Returns the `v` of every key of `{a}` whose record exists and has `ok` set, in order.",
        vocab=[("usableReadings", ["sensorIds", "fetch"], "Values of the sensors that answered and are healthy."), ("approvedTotals", ["orderIds", "load"], "Totals of approved orders."),
               ("livePrices", ["skus", "lookup"], "Prices of active SKUs.")]),
    "ranked": dict(
        d=3, factor=1.0, n=(1500, 2500), prelude="const SCORE = (x) => ((x * 37) % 11) - 4;",
        small="[Array.from({ length: rnd(15) }, () => rnd(40)), SCORE]", big="[Array.from({ length: n }, () => rnd(100000)), SCORE]", wrap="[a, countedFn(b)]", empty="[[], SCORE]",
        naive='''function $f($a, $b) {
  return $a.filter((item) => $b(item) > 0).sort((x, y) => $b(y) - $b(x));
}
''', fast='''function $f($a, $b) {
  const scored = [];
  for (const item of $a) {
    const s = $b(item);
    if (s > 0) scored.push([s, item]);
  }
  scored.sort((x, y) => y[0] - x[0]);
  return scored.map((p) => p[1]);
}
''', oracle='''function oracle(a, b) {
  const scored = a.map((x) => [b(x), x]).filter((p) => p[0] > 0);
  scored.sort((x, y) => y[0] - x[0]);
  return scored.map((p) => p[1]);
}''', spec="`{b}(item)` is an expensive scoring function. Returns the items of `{a}` with a positive score, best first (equal scores keep their input order).",
        vocab=[("shortlist", ["candidates", "score"], "Candidates worth interviewing, best first."), ("rankedOffers", ["offers", "rate"], "Offers with a positive rating, best first."),
               ("worthVisiting", ["places", "appeal"], "Places with a positive appeal score, best first.")]),
    "route": dict(
        d=4, factor=2, n=(144, 144), prelude="const COST = (i, j) => ((i * 7 + j * 13) % 10) + 1;",
        small="[1 + rnd(5), COST]", big="[12, COST]", wrap="[a, countedFn(b)]", empty="[1, COST]",
        naive='''function $f($a, $b) {
  const best = (i, j) => {
    const here = $b(i, j);
    if (i === $a - 1 && j === $a - 1) return here;
    const options = [];
    if (i + 1 < $a) options.push(best(i + 1, j));
    if (j + 1 < $a) options.push(best(i, j + 1));
    return here + Math.min(...options);
  };
  return best(0, 0);
}
''', fast='''function $f($a, $b) {
  const known = new Map();
  const best = (i, j) => {
    const key = i * $a + j;
    if (known.has(key)) return known.get(key);
    const here = $b(i, j);
    let result = here;
    if (!(i === $a - 1 && j === $a - 1)) {
      const options = [];
      if (i + 1 < $a) options.push(best(i + 1, j));
      if (j + 1 < $a) options.push(best(i, j + 1));
      result = here + Math.min(...options);
    }
    known.set(key, result);
    return result;
  };
  return best(0, 0);
}
''', oracle='''function oracle(a, b) {
  const best = Array.from({ length: a }, () => new Array(a).fill(0));
  for (let i = a - 1; i >= 0; i--) {
    for (let j = a - 1; j >= 0; j--) {
      const here = b(i, j);
      if (i === a - 1 && j === a - 1) { best[i][j] = here; continue; }
      const opts = [];
      if (i + 1 < a) opts.push(best[i + 1][j]);
      if (j + 1 < a) opts.push(best[i][j + 1]);
      best[i][j] = here + Math.min(...opts);
    }
  }
  return best[0][0];
}''', spec="The grid has `{a} x {a}` cells (`{a}` at least 1); `{b}(row, col)` is the expensive cost of stepping on a cell. Returns the cheapest total cost of a walk from the top-left to the bottom-right cell moving only down or right, counting both ends.",
        vocab=[("cheapestCrossing", ["size", "costAt"], "Cheapest crossing of a field of tiles."), ("leastEffortTrail", ["side", "effort"], "Least-effort route over a square hillside map."),
               ("cheapestCabling", ["width", "costOfCell"], "Cheapest cable run across a floor plan.")]),
}

PROMPTS = [
    "`{f}` in `{path}` {hint} and the job that calls it has become unaffordable. {doc} Make it do no more work against the collaborator than necessary; the results must not change. "
    "The README says what is expensive.",
    "perf: `{f}` ({path}) {hint}. {doc} Fix it, same output. CI counts the expensive operations with a budget.",
    "Our bill for the lookup service doubled after the last release and the trace says `{f}` ({path}) is the caller that {hint}. {doc} Please fix it; behaviour must stay exactly the same.",
    "Could you make `{f}` in `{path}` cheaper? {doc} It works, but it {hint}. Don't change the signature or what it returns.",
]
HINTS = {
    "rangeSums": "re-reads the same stretch of the series for every query", "windowMeans": "re-reads every window's elements for each window",
    "totalPrice": "asks the pricing service the same question again and again", "depths": "walks the tree to the root again for every node",
    "drain": "shifts the whole queue on every step", "usable": "calls the fetch function several times for the same key", "ranked": "scores the same item over and over while sorting",
    "route": "recomputes the same sub-routes exponentially often",
}


@family("optimize-js-counted", category="optimize", lang="javascript", kind="feature", n=12,
        summary="javascript reading an expensive series or calling an expensive collaborator too often: Proxy-counted reads and counted calls, with a budget")
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
        pkg = rng.choice(["meterbank", "pricing", "orgchart", "stormwatch", "joblab", "routing"])
        path = f"src/{pkg}.js"
        names = {"f": f, "a": argn[0], "b": argn[1] if len(argn) > 1 else ""}
        naive = Template(sp["naive"]).substitute(names)
        fast = Template(sp["fast"]).substitute(names)
        wrap = lambda body: f"'use strict';\n\n{body}\nmodule.exports = {{ {f} }};\n"
        spec = sp["spec"].format(a=argn[0], b=argn[1] if len(argn) > 1 else "")
        readme = f"# {pkg}\n\n## `{f}({', '.join(argn)})`\n\n{doc}\n\n{spec}\n"
        files = {path: wrap(naive), "README.md": readme, "package.json": json.dumps({"name": pkg, "version": "1.0.0", "private": True}, indent=2) + "\n"}
        seed = 500 + i
        lo, hi = sp["n"]
        n_items = rng.choice([lo, hi])
        factor = sp["factor"]
        nargs = len(argn)
        argsig = ", ".join("ab"[:nargs])
        prelude = sp["prelude"]
        head = (f"'use strict';\nconst test = require('node:test');\nconst assert = require('node:assert');\nconst {{ makeRnd }} = require('./data');\n"
                f"const {{ BudgetExceeded, Ops, counted, countedFn }} = require('./counting');\nconst {{ {f} }} = require('../{path}');\n\n{prelude}\n\n{sp['oracle']}\n\n{_clone_js()}\n")
        small_fn = f"function smallArgs(rnd) {{\n  return {sp['small']};\n}}\n"
        big_fn = f"function bigArgs(rnd, n) {{\n  return {sp['big']};\n}}\n"
        wrap_fn = f"function wrapArgs({argsig}) {{\n  return {sp['wrap']};\n}}\n"
        correct = (head + small_fn + wrap_fn + "\n"
                   f"test('matches the reference on random inputs', () => {{\n  const rnd = makeRnd({seed});\n  for (let i = 0; i < 120; i++) {{\n    const args = smallArgs(rnd);\n"
                   f"    assert.deepStrictEqual({f}(...clone(args)), oracle(...clone(args)));\n  }}\n}});\n\n"
                   f"test('works with instrumented inputs', () => {{\n  const rnd = makeRnd({seed + 1});\n  for (let i = 0; i < 40; i++) {{\n    const args = smallArgs(rnd);\n"
                   f"    assert.deepStrictEqual({f}(...wrapArgs(...clone(args))), oracle(...clone(args)));\n  }}\n}});\n\n"
                   f"test('empty inputs', () => {{\n  const args = {sp['empty']};\n  assert.deepStrictEqual({f}(...clone(args)), oracle(...clone(args)));\n}});\n")
        limit_expr = f"{factor} * n"
        perf = (head + big_fn + wrap_fn + "\n"
                f"test('the number of expensive operations stays proportional to the input', () => {{\n  const n = {n_items};\n  const args = bigArgs(makeRnd({seed}), n);\n  const limit = {limit_expr};\n"
                "  Ops.reads = 0;\n  Ops.budget = limit * 20;\n  let got;\n  try {\n"
                f"    got = {f}(...wrapArgs(...clone(args)));\n"
                "  } catch (e) {\n    if (e instanceof BudgetExceeded) assert.fail('PERF: gave up after ' + Ops.budget + ' expensive operations for ' + n + ' items (limit ' + limit + '): ' + " + json.dumps(HINTS[shape]) + ");\n    throw e;\n"
                "  } finally {\n    Ops.budget = null;\n  }\n  const ops = Ops.reads;\n"
                f"  assert.deepStrictEqual(got, oracle(...clone(args)));\n  assert.ok(ops <= limit, 'PERF: ' + ops + ' expensive operations for ' + n + ' items (limit ' + limit + '): ' + {json.dumps(HINTS[shape])});\n}});\n")
        vis = (f"'use strict';\nconst test = require('node:test');\nconst assert = require('node:assert');\nconst {{ makeRnd }} = require('./data');\nconst {{ {f} }} = require('../{path}');\n\n{prelude}\n\n{sp['oracle']}\n\n{_clone_js()}\n{small_fn}\n"
               f"test('small examples agree with the specification', () => {{\n  const rnd = makeRnd({7 + i});\n  for (let i = 0; i < 6; i++) {{\n    const args = smallArgs(rnd);\n    assert.deepStrictEqual({f}(...clone(args)), oracle(...clone(args)));\n  }}\n}});\n")
        hidden = {"test/data.js": DATA, "test/counting.js": COUNTING, "test/correct.test.js": correct, "test/perf.test.js": perf}
        start = {**files, "test/basic.test.js": vis}
        solution = {path: wrap(fast)}
        prove_opt(f"{shape}/{f}", start, hidden, solution, JS_CORRECT, JS_PERF, JS_ALL, timeout=120)
        prompt = rng.choice(PROMPTS).format(f=f, path=path, doc=doc, hint=HINTS[shape])
        yield Task(slug=f"{i + 1:02d}-{shape.lower()}-{f.lower()}", prompt=prompt, difficulty=sp["d"], start=start, hidden=hidden, solution=solution, verify=JS_ALL,
                   tags=["complexity", "proxy-counter", "memoisation"], notes={"shape": shape, "n": n_items, "factor": factor})
