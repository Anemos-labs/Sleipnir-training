"""Sequential awaits, unbounded fan-out, N+1 calls and duplicate loads (javascript, async). A fake backend counts calls and concurrency deterministically."""
from __future__ import annotations

import json
from string import Template

from fx import Task, family, merged, run

from ._kit import prove_opt

JS_ALL = "node --test test/*.test.js"
JS_CORRECT = "node --test test/basic.test.js test/correct.test.js"
JS_PERF = "node --test test/perf.test.js"

FAKES = '''"use strict";
// A fake backend: every call takes a few event-loop turns, and the fake records how many calls overlap.
function makeBackend(data, { ticks = 2 } = {}) {
  const stats = { calls: 0, batchCalls: 0, inflight: 0, maxInflight: 0 };
  const turn = () => new Promise((resolve) => setImmediate(resolve));
  async function enter() {
    stats.inflight++;
    stats.maxInflight = Math.max(stats.maxInflight, stats.inflight);
    for (let i = 0; i < ticks; i++) await turn();
  }
  const backend = {
    stats,
    async get(id) {
      stats.calls++;
      await enter();
      stats.inflight--;
      if (!data.has(id)) throw new Error("missing " + id);
      return data.get(id);
    },
    async getMany(ids) {
      stats.batchCalls++;
      await enter();
      stats.inflight--;
      const out = new Map();
      for (const id of ids) if (data.has(id)) out.set(id, data.get(id));
      return out;
    },
  };
  return backend;
}

module.exports = { makeBackend };
'''

SHAPES = {
    "sequential": dict(
        d=2, bar="seq",
        naive='''async function $f($a, $b) {
  const out = [];
  for (const id of $a) {
    out.push(await $b.get(id));
  }
  return out;
}
''', fast='''async function $f($a, $b) {
  return Promise.all($a.map((id) => $b.get(id)));
}
''', spec="`{b}.get(id)` returns a promise for the record of an id and rejects when the id is unknown. Returns a promise for the records of `{a}` in the same order; if any request fails, the promise rejects with that error. The requests are independent and the backend has plenty of capacity, so they should not wait for each other.",
        hint="requests are made one after the other even though they are independent",
        vocab=[("loadProfiles", ["ids", "directory"], "Load the profiles of a list of users."), ("fetchSensors", ["ids", "hub"], "Fetch the latest reading of each sensor."),
               ("resolveAuthors", ["ids", "registry"], "Resolve author records for a list of ids.")]),
    "bounded": dict(
        d=4, bar="pool",
        naive='''async function $f($a, $b) {
  return Promise.all($a.map((id) => $b.get(id)));
}
''', fast='''async function $f($a, $b) {
  const out = new Array($a.length);
  let next = 0;
  async function worker() {
    while (next < $a.length) {
      const i = next++;
      out[i] = await $b.get($a[i]);
    }
  }
  await Promise.all(Array.from({ length: Math.min(5, $a.length) }, worker));
  return out;
}
''', spec="`{b}.get(id)` returns a promise for the record of an id and rejects when the id is unknown. Returns a promise for the records of `{a}` in the same order; if any request fails, the promise rejects with that error. The backend throttles clients that have more than 5 requests in flight at once, so use up to 5 concurrent requests (at least 3 when there is enough work) but never more.",
        hint="all requests are fired at once, the backend limit of 5 concurrent requests is exceeded",
        vocab=[("downloadAll", ["urls", "mirror"], "Download many files from a throttled mirror."), ("enrichRows", ["ids", "geocoder"], "Look up every row in a rate-limited geocoding service."),
               ("syncDocuments", ["ids", "store"], "Pull documents from a store that throttles parallel requests.")]),
    "batch": dict(
        d=2, bar="batch",
        naive='''async function $f($a, $b) {
  const names = [];
  for (const id of $a) {
    try {
      names.push(await $b.get(id));
    } catch (err) {
      // unknown ids are skipped
    }
  }
  return names;
}
''', fast='''async function $f($a, $b) {
  const found = await $b.getMany($a);
  const names = [];
  for (const id of $a) {
    if (found.has(id)) names.push(found.get(id));
  }
  return names;
}
''', spec="`{b}.get(id)` answers one id (rejecting for unknown ids) and `{b}.getMany(ids)` answers a whole list in one round trip with a `Map` of the ids that exist. Returns the values of the known ids of `{a}` in order, skipping unknown ids.",
        hint="one round trip per id although a batch call exists",
        vocab=[("namesFor", ["ids", "directory"], "Names for a list of user ids."), ("titlesOf", ["ids", "catalogue"], "Titles for a list of product ids."), ("labelsFor", ["ids", "registry"], "Labels for a list of asset ids.")]),
    "dedupe": dict(
        d=3, bar="dedupe",
        naive='''async function $f($a, $b) {
  const out = [];
  for (const key of $a) {
    out.push(await $b.get(key));
  }
  return out;
}
''', fast='''async function $f($a, $b) {
  const pending = new Map();
  for (const key of $a) {
    if (!pending.has(key)) pending.set(key, $b.get(key));
  }
  return Promise.all($a.map((key) => pending.get(key)));
}
''', spec="`{b}.get(key)` returns a promise for the record of a key (rejecting for unknown keys). `{a}` contains many repeated keys. Returns the records for `{a}` in order; each distinct key must be requested only once, and requests may overlap. If a request fails the promise rejects with that error.",
        hint="the same key is requested again for every occurrence",
        vocab=[("recordsForEvents", ["keys", "backend"], "Records for a stream of events that mention the same entities repeatedly."), ("expandMentions", ["keys", "users"], "Expand user mentions found in comments."),
               ("hydrateRows", ["keys", "lookup"], "Attach lookup records to rows that share foreign keys.")]),
}

PROMPTS = [
    "`{f}` in `{path}` is slow against the real backend: {hint}. {doc} Fix it so it behaves as described in the README (results and error behaviour unchanged).",
    "perf: `{f}` ({path}) {hint}. {doc} Make it respect the README. Same results.",
    "The {noun} page loads in ten seconds for large accounts. Network traces show `{f}` ({path}): {hint}. {doc} Please fix it without changing what it resolves to.",
]


@family("optimize-js-async", category="optimize", lang="javascript", kind="feature", n=10,
        summary="sequential awaits, unbounded fan-out, N+1 backend calls and duplicate loads: a fake backend counts calls and in-flight requests deterministically")
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
        pkg = rng.choice(["profiles", "syncjob", "directory", "mirrorkit", "pagebuilder"])
        path = f"src/{pkg}.js"
        names = {"f": f, "a": argn[0], "b": argn[1]}
        wrap = lambda body: f"'use strict';\n\n{body}\nmodule.exports = {{ {f} }};\n"
        spec = sp["spec"].format(a=argn[0], b=argn[1])
        readme = f"# {pkg}\n\n## `{f}({', '.join(argn)})` (async)\n\n{doc}\n\n{spec}\n"
        files = {path: wrap(Template(sp["naive"]).substitute(names)), "README.md": readme, "package.json": json.dumps({"name": pkg, "version": "1.0.0", "private": True}, indent=2) + "\n"}
        seed = 900 + i
        bar = sp["bar"]
        if shape == "dedupe":
            gen_ids = "Array.from({ length: n }, () => 'k' + rnd(Math.max(1, Math.floor(n / 10))))"
        else:
            gen_ids = "Array.from({ length: n }, (_, i) => 'id' + i)"
        data_fn = ("function makeData(n, missingEvery) {\n  const data = new Map();\n  for (let i = 0; i < n + 5; i++) data.set('id' + i, { id: 'id' + i, v: i * 3 });\n"
                   "  for (let i = 0; i < n + 5; i++) data.set('k' + i, { id: 'k' + i, v: i * 5 });\n  return data;\n}\n")
        expected = {
            "sequential": "ids.map((id) => data.get(id))", "bounded": "ids.map((id) => data.get(id))", "batch": "ids.filter((id) => data.has(id)).map((id) => data.get(id))",
            "dedupe": "ids.map((id) => data.get(id))"}[shape]
        head = (f"'use strict';\nconst test = require('node:test');\nconst assert = require('node:assert');\nconst {{ makeRnd }} = require('./data');\nconst {{ makeBackend }} = require('./fakes');\n"
                f"const {{ {f} }} = require('../{path}');\n\n{data_fn}\n")
        has_missing = shape in ("batch",)
        correct = (head + f"test('resolves like the specification on random inputs', async () => {{\n  const rnd = makeRnd({seed});\n  for (let t = 0; t < 40; t++) {{\n"
                   "    const n = rnd(12);\n    const data = makeData(n, 0);\n"
                   f"    const ids = {gen_ids.replace('n', 'n') if shape != 'dedupe' else gen_ids};\n" +
                   ("    if (n > 2) ids.push('ghost');\n" if has_missing else "") +
                   f"    const backend = makeBackend(data);\n    const got = await {f}(ids, backend);\n    assert.deepStrictEqual(got, {expected});\n  }}\n}});\n\n"
                   f"test('an unknown id rejects with its error', async () => {{\n  const data = makeData(5, 0);\n  const backend = makeBackend(data);\n"
                   + ("  const got = await " + f + "(['id1', 'nope', 'id2'], backend);\n  assert.deepStrictEqual(got, [data.get('id1'), data.get('id2')]);\n" if has_missing else
                      "  await assert.rejects(" + f + "(['id1', 'nope', 'id2'], backend), /missing nope/);\n") + "});\n\n"
                   f"test('empty input', async () => {{\n  assert.deepStrictEqual(await {f}([], makeBackend(new Map())), []);\n}});\n")
        n_items = {"sequential": 40, "bounded": 60, "batch": 80, "dedupe": 200}[shape]
        if bar == "seq":
            check = ("  assert.ok(backend.stats.maxInflight >= 4, 'PERF: at most ' + backend.stats.maxInflight + ' request(s) in flight at once: independent requests are awaited one after the other');\n")
        elif bar == "pool":
            check = ("  assert.ok(backend.stats.maxInflight <= 5, 'PERF: ' + backend.stats.maxInflight + ' requests were in flight at once (the backend allows 5): the fan-out is not bounded');\n"
                     "  assert.ok(backend.stats.maxInflight >= 3, 'PERF: only ' + backend.stats.maxInflight + ' requests overlapped: use the allowed concurrency');\n")
        elif bar == "batch":
            check = ("  assert.ok(backend.stats.calls + backend.stats.batchCalls <= 2, 'PERF: ' + (backend.stats.calls + backend.stats.batchCalls) + ' backend calls for ' + ids.length + ' ids: use the batch call');\n")
        else:
            check = ("  const distinct = new Set(ids).size;\n  assert.ok(backend.stats.calls <= distinct, 'PERF: ' + backend.stats.calls + ' requests for ' + distinct + ' distinct keys: each key should be requested once');\n")
        perf = (head + f"test('the backend is used efficiently on a large input', async () => {{\n  const rnd = makeRnd({seed});\n  const n = {n_items};\n  const data = makeData(n, 0);\n"
                f"  const ids = {gen_ids};\n  const backend = makeBackend(data);\n  const got = await {f}(ids, backend);\n"
                f"  assert.deepStrictEqual(got, {expected});\n" + check + "});\n")
        vis = (head + f"test('resolves a few ids', async () => {{\n  const data = makeData(6, 0);\n  const ids = ['id3', 'id1', 'id4'];\n  const backend = makeBackend(data);\n"
               f"  assert.deepStrictEqual(await {f}(ids, backend), {expected});\n}});\n\n"
               f"test('rejects on an unknown id', async () => {{\n  const backend = makeBackend(makeData(3, 0));\n"
               + ("  assert.deepStrictEqual(await " + f + "(['id1', 'zzz'], backend), [makeData(3, 0).get('id1')]);\n" if has_missing else
                  "  await assert.rejects(" + f + "(['id1', 'zzz'], backend), /missing zzz/);\n") + "});\n")
        data_js = ("function mulberry32(seed) {\n  let a = seed >>> 0;\n  return function () {\n    a = (a + 0x6d2b79f5) >>> 0;\n    let t = a;\n    t = Math.imul(t ^ (t >>> 15), t | 1);\n"
                   "    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);\n    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;\n  };\n}\n\nfunction makeRnd(seed) {\n  const r = mulberry32(seed);\n  return (k) => Math.floor(r() * k);\n}\n\nmodule.exports = { mulberry32, makeRnd };\n")
        hidden = {"test/data.js": data_js, "test/fakes.js": FAKES, "test/correct.test.js": correct, "test/perf.test.js": perf}
        start = {**files, "test/basic.test.js": vis}
        solution = {path: wrap(Template(sp["fast"]).substitute(names))}
        prove_opt(f"{shape}/{f}", start, hidden, solution, JS_CORRECT, JS_PERF, JS_ALL, timeout=120)
        prompt = rng.choice(PROMPTS).format(f=f, path=path, doc=doc, hint=sp["hint"], noun=pkg)
        yield Task(slug=f"{i + 1:02d}-{shape}-{f.lower()}", prompt=prompt, difficulty=sp["d"], start=start, hidden=hidden, solution=solution, verify=JS_ALL,
                   tags=["async", "concurrency", "batching"], notes={"shape": shape})
