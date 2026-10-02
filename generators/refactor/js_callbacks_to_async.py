"""Callbacks to promises / async-await (javascript): nested node-style callbacks become flat async code."""
from __future__ import annotations

import json

from fx import Task, dd, family, merged, run

from . import _kit, _js_flows as F
from ._kit import clike_lib, prove

CB_PATTERN = r"\(\s*(?:err|error|e)\s*(?:,[^)]*)?\)\s*=>|\b(?:err|error)\s*=>|function\s*\w*\s*\(\s*(?:err|error)\b"


def _select(rng, flow):
    chosen, bound = [], set()
    for s in flow.steps:
        if s.needs and s.needs not in bound:
            continue
        if s.opt < 1.0 and rng.random() >= s.opt:
            continue
        chosen.append(s)
        if s.kind == "call" and s.res:
            bound.add(s.res)
        inner = s.inner
        if inner is not None and inner.res:
            bound.add(inner.res)
    return chosen


def _count_cb(text):
    import importlib.util
    spec = importlib.util.spec_from_file_location("fx_clike", _kit.ASSETS / "clike.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return len(__import__("re").findall(CB_PATTERN, m.clean(text, "javascript")))


def _golden(start_files, flow, cases):
    script = dd(f'''
    const {{ makeServices }} = require('./test/helpers');
    const mod = require('./{flow.file}');
    const CASES = {json.dumps(cases)};
    (async () => {{
      const out = [];
      for (const c of CASES) {{
        const {{ svc, log }} = makeServices(c.state);
        const res = await new Promise((resolve) => {{
          mod.{flow.name}(c.input, svc, (err, value) => resolve(err ? {{ error: err.message, calls: log.slice() }} : {{ value, calls: log.slice() }}));
        }});
        out.push(JSON.parse(JSON.stringify(res)));
      }}
      console.log(JSON.stringify(out));
    }})();
    ''')
    r = run(merged(start_files, {"_golden.js": script}), "node _golden.js", timeout=60)
    if not r.ok:
        raise RuntimeError("golden run failed:\n" + r.out[-2000:])
    return json.loads(r.out.strip().splitlines()[-1])


def _runner(flow):
    return dd(f'''
    function run(input, state) {{
      const {{ svc, log }} = makeServices(state);
      return {flow.name}(input, svc).then(
        (value) => ({{ value, calls: log.slice() }}),
        (err) => ({{ error: err.message, calls: log.slice() }}),
      );
    }}

    function runWithCallback(input, state) {{
      const {{ svc, log }} = makeServices(state);
      return new Promise((resolve) => {{
        {flow.name}(input, svc, (err, value) => resolve(err ? {{ error: err.message, calls: log.slice() }} : {{ value, calls: log.slice() }}));
      }});
    }}

    const plain = (x) => JSON.parse(JSON.stringify(x));
    ''')


def _test_head(flow):
    return dd(f'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert');
    const {{ makeServices }} = require('./helpers');
    const {{ {flow.name} }} = require('../{flow.file}');
    ''')


PROMPTS_REPLACE = [
    "`{name}` in `{file}` is a pyramid of nested node-style callbacks. Rewrite it with promises (async/await preferred) so it returns a promise and takes "
    "no callback: it resolves with the value the callback used to receive, and rejects with the same `Error` (same message) it used to pass. The `svc` "
    "collaborators keep their callback signatures (`svc.x.y(args..., cb)`), so you will need a small wrapper or `util.promisify` for them. "
    "The services must still be called in the same order with the same arguments, and no err-first callbacks should be left in the module.",
    "Please modernise the {noun} code: `{name}` ({file}) uses callbacks everywhere. Make it `async` / promise based. Same results, same error messages, same "
    "calls to the services in the same order. The services themselves are not part of this change: they still call back node-style. The visible tests were "
    "already updated for the promise API.",
    "callbacks -> async/await in `{file}`. `{name}(input, svc)` should return a promise with the old result or reject with the old error. keep the service "
    "call order, don't touch the service interface, leave no callback pyramid behind",
]
PROMPTS_BOTH = [
    "`{name}` in `{file}` is written as nested callbacks. Convert the implementation to async/await, but existing callers still call it as "
    "`{name}(input, svc, cb)`, so keep that working: when the last argument is a function, call it node-style `(err, value)`; when it is omitted, return a "
    "promise. Same results, same `Error` messages, same order of service calls. The `svc` collaborators keep their callback signatures. No err-first "
    "callback pyramids should remain in the implementation.",
    "Move the {noun} code in `{file}` to async/await without breaking the callers that still pass a callback: `{name}(input, svc, cb)` must keep calling `cb(err, value)`, "
    "and `{name}(input, svc)` (no callback) should return a promise. Behaviour, error messages and the order of calls to `svc` stay identical.",
]


@family("refactor-js-callbacks-to-async", category="refactor", lang="javascript", kind="refactor", n=12,
        summary="nested node-style callbacks become promise/async code (promise-only or dual callback+promise API)")
def gen(rng, n):
    flows = list(F.FLOWS) * 4
    rng.shuffle(flows)
    for i in range(n):
        flow = flows[i]
        dual = rng.random() < 0.4
        steps = _select(rng, flow)
        calls_n = sum(1 for s in steps if s.kind in ("call", "when"))
        if calls_n < 4:
            steps = list(flow.steps)  # fall back to the full flow
            steps = [s for s in steps if not s.needs or any(t.res == s.needs for t in steps if t.kind == "call")]
        start_js = f"'use strict';\n\n{F.emit_callbacks(flow, steps)}\n\nmodule.exports = {{ {flow.name} }};\n"
        sol_js = f"'use strict';\n\n{F.emit_async(flow, steps, dual)}\n\nmodule.exports = {{ {flow.name} }};\n"
        cases = flow.cases(rng, 26)
        helpers = F.helpers_js(flow)
        pkg = json.dumps({"name": flow.key + "-service", "version": "1.0.0", "private": True, "main": flow.file}, indent=2) + "\n"
        files = {flow.file: start_js, "test/helpers.js": helpers, "package.json": pkg}
        want = _golden(files, flow, cases)
        ok = [j for j, w in enumerate(want) if "value" in w][:2]
        bad = [j for j, w in enumerate(want) if "error" in w][:1]
        head = _test_head(flow)
        runner = _runner(flow)
        vis = head + "\n" + runner + "\n"
        for t, j in enumerate(ok + bad):
            vis += (f"test('example {t + 1}', async () => {{\n  const input = {json.dumps(cases[j]['input'])};\n  const state = {json.dumps(cases[j]['state'])};\n"
                    f"  assert.deepStrictEqual(plain(await run(input, state)), {json.dumps(want[j])});\n}});\n\n")
        if dual:
            j = ok[0]
            vis += (f"test('callback style still works', async () => {{\n  const input = {json.dumps(cases[j]['input'])};\n  const state = {json.dumps(cases[j]['state'])};\n"
                    f"  assert.deepStrictEqual(plain(await runWithCallback(input, state)), {json.dumps(want[j])});\n}});\n\n")
        hid = head + "\n" + runner + dd(f'''
        const CASES = {json.dumps(cases)};
        const WANT = {json.dumps(want)};

        test('every recorded case gives the same outcome', async () => {{
          for (let i = 0; i < CASES.length; i++) {{
            const got = plain(await run(CASES[i].input, JSON.parse(JSON.stringify(CASES[i].state))));
            assert.deepStrictEqual(got, WANT[i], 'case ' + i + ': ' + JSON.stringify(CASES[i].input));
          }}
        }});
        ''')
        if dual:
            hid += dd('''
            test('callback style gives the same outcome', async () => {
              for (let i = 0; i < CASES.length; i++) {
                const got = plain(await runWithCallback(CASES[i].input, JSON.parse(JSON.stringify(CASES[i].state))));
                assert.deepStrictEqual(got, WANT[i], 'callback case ' + i);
              }
            });

            test('without a callback a promise is returned', () => {
              const { svc } = makeServices(JSON.parse(JSON.stringify(CASES[0].state)));
              const result = ''' + flow.name + '''(CASES[0].input, svc);
              assert.ok(result && typeof result.then === 'function');
              return result.catch(() => {});
            });
            ''')
        s_count, a_count = _count_cb(start_js), _count_cb(sol_js)
        allowed = a_count + 1
        if s_count < allowed + 1:
            raise RuntimeError(f"{flow.key}: start has {s_count} callbacks, allowed {allowed}")
        struct = dd(f'''
        import clike as C

        FILES = C.files([".js"], dirs=["src"])
        PATTERN = {json.dumps(CB_PATTERN)}
        ALLOWED = {allowed}
        problems = []
        n = C.count(FILES, PATTERN, "javascript")
        if n > ALLOWED:
            problems.append("%d node-style (err, ...) callbacks are still in the source (at most %d expected, e.g. one promisify helper)" % (n, ALLOWED))
        w = C.count(FILES, r"\\bawait\\b|\\.then\\(", "javascript")
        if w < {max(3, calls_n - 2)}:
            problems.append("expected promise based code (await / then), found %d uses" % w)
        C.report(problems)
        ''')
        hidden = {"test/recorded.test.js": hid, "checks/structure.py": struct, **clike_lib()}
        start = {**files, "test/example.test.js": vis}
        solution = {flow.file: sol_js}
        prove(f"{flow.key}", start, hidden, solution, _kit.JS_BEHAVIOUR_CMD, _kit.JS_STRUCT_CMD, _kit.JS_FULL_CMD, behaviour_on_start=False)
        prompt = rng.choice(PROMPTS_BOTH if dual else PROMPTS_REPLACE).format(name=flow.name, file=flow.file, noun=flow.noun)
        d = 3 if calls_n <= 5 else 4
        if not dual and calls_n <= 5 and flow.key != "orders":
            d = 2
        yield Task(slug=f"{i + 1:02d}-{flow.key}-{'dual' if dual else 'promise'}", prompt=prompt, difficulty=d, start=start, hidden=hidden,
                   solution=solution, verify=_kit.JS_FULL_CMD, tags=["callbacks", "promises", "async-await"],
                   notes={"flow": flow.key, "dual": dual, "calls": calls_n})
