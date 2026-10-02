"""API migration inside JavaScript: node-style callbacks -> promises (flow helpers and the code built on them)."""
import json

from fx import Task, dd, family

from ._portlib import run_local

VFS = dd(r'''
    'use strict';
    // In-memory virtual file system. Callback API at the top level, promise API under `.promises` (like node's fs).
    // Every operation takes a few event-loop turns (setImmediate) so that interleavings are deterministic and observable.

    const files = new Map();
    const flaky = new Map();
    const trace = [];

    function later(ticks, fn) {
      if (ticks <= 0) setImmediate(fn);
      else setImmediate(() => later(ticks - 1, fn));
    }

    function ticksFor(path) {
      return path.length % 3;
    }

    function fail(code, path) {
      const e = new Error(code + ': ' + path);
      e.code = code;
      return e;
    }

    function op(name, path, work, cb) {
      trace.push(name + ' ' + path);
      later(ticksFor(path), () => {
        let out;
        try {
          out = work();
        } catch (e) {
          return cb(e);
        }
        cb(null, out);
      });
    }

    function readWork(path) {
      if (path.endsWith('/')) throw fail('EISDIR', path);
      const left = flaky.get(path) || 0;
      if (left > 0) {
        flaky.set(path, left - 1);
        throw fail('EAGAIN', path);
      }
      if (!files.has(path)) throw fail('ENOENT', path);
      return files.get(path);
    }

    function writeWork(path, text) {
      if (path.endsWith('/')) throw fail('EISDIR', path);
      if (typeof text !== 'string') throw fail('EINVAL', path);
      files.set(path, text);
    }

    const existsWork = (path) => files.has(path);
    const listWork = (prefix) => [...files.keys()].filter((k) => k.startsWith(prefix)).sort();

    function viaPromise(name, path, work) {
      return new Promise((resolve, reject) => op(name, path, work, (err, v) => (err ? reject(err) : resolve(v))));
    }

    const promises = {
      readFile: (path) => viaPromise('read', path, () => readWork(path)),
      writeFile: (path, text) => viaPromise('write', path, () => writeWork(path, text)),
      exists: (path) => viaPromise('exists', path, () => existsWork(path)),
      list: (prefix) => viaPromise('list', prefix, () => listWork(prefix)),
    };

    function reset(initial, flakyReads) {
      files.clear();
      flaky.clear();
      trace.length = 0;
      for (const [k, v] of Object.entries(initial || {})) files.set(k, v);
      for (const [k, v] of Object.entries(flakyReads || {})) flaky.set(k, v);
    }

    module.exports = {
      readFile: (path, cb) => op('read', path, () => readWork(path), cb),
      writeFile: (path, text, cb) => op('write', path, () => writeWork(path, text), (err) => cb(err || null)),
      exists: (path, cb) => op('exists', path, () => existsWork(path), cb),
      list: (prefix, cb) => op('list', prefix, () => listWork(prefix), cb),
      promises,
      reset,
      trace,
    };
''')

FLOW_OLD = dd(r'''
    'use strict';
    // Small control-flow helpers in node callback style: every callback is called as cb(err, value).

    function series(tasks, cb) {
      const results = [];
      let i = 0;
      function next() {
        if (i === tasks.length) return cb(null, results);
        tasks[i++]((err, value) => {
          if (err) return cb(err);
          results.push(value);
          next();
        });
      }
      next();
    }

    function mapSeries(items, fn, cb) {
      series(items.map((item) => (done) => fn(item, done)), cb);
    }

    function mapLimit(items, limit, fn, cb) {
      const results = new Array(items.length);
      let started = 0;
      let finished = 0;
      let failed = false;
      if (items.length === 0) return cb(null, results);
      function launch() {
        while (!failed && started < items.length && started - finished < limit) {
          const idx = started++;
          fn(items[idx], (err, value) => {
            if (failed) return;
            if (err) {
              failed = true;
              return cb(err);
            }
            results[idx] = value;
            finished++;
            if (finished === items.length) return cb(null, results);
            launch();
          });
        }
      }
      launch();
    }

    function retry(times, fn, cb) {
      let attempt = 0;
      function go() {
        attempt++;
        fn(attempt, (err, value) => {
          if (err && attempt < times) return go();
          cb(err || null, value);
        });
      }
      go();
    }

    module.exports = { series, mapSeries, mapLimit, retry };
''')

FLOW_NEW = dd(r'''
    'use strict';
    // Small control-flow helpers on promises.

    async function series(tasks) {
      const results = [];
      for (const task of tasks) results.push(await task());
      return results;
    }

    async function mapSeries(items, fn) {
      return series(items.map((item) => () => fn(item)));
    }

    function mapLimit(items, limit, fn) {
      return new Promise((resolve, reject) => {
        const results = new Array(items.length);
        let started = 0;
        let finished = 0;
        let failed = false;
        if (items.length === 0) return resolve(results);
        function launch() {
          while (!failed && started < items.length && started - finished < limit) {
            const idx = started++;
            Promise.resolve(fn(items[idx])).then(
              (value) => {
                if (failed) return;
                results[idx] = value;
                finished++;
                if (finished === items.length) resolve(results);
                else launch();
              },
              (err) => {
                if (failed) return;
                failed = true;
                reject(err);
              }
            );
          }
        }
        launch();
      });
    }

    async function retry(times, fn) {
      let lastErr;
      for (let attempt = 1; attempt <= times; attempt++) {
        try {
          return await fn(attempt);
        } catch (err) {
          lastErr = err;
        }
      }
      throw lastErr;
    }

    module.exports = { series, mapSeries, mapLimit, retry };
''')

# ---- application functions: (callback version, promise version, doc, cases)

APP = {}


def app_fn(name, doc, old, new, cases):
    APP[name] = dict(name=name, doc=doc, old=dd(old), new=dd(new), cases=cases)


app_fn("loadJson", "`loadJson(path)` resolves with the parsed JSON of the file. A missing file rejects with the file system's error (`code` `ENOENT`); text that is not valid JSON rejects with an `Error` whose `code` is `'EJSON'` and whose message is `bad json: <path>`.", r'''
    function loadJson(path, cb) {
      vfs.readFile(path, (err, text) => {
        if (err) return cb(err);
        let data;
        try {
          data = JSON.parse(text);
        } catch (e) {
          const bad = new Error('bad json: ' + path);
          bad.code = 'EJSON';
          return cb(bad);
        }
        cb(null, data);
      });
    }
''', r'''
    async function loadJson(path) {
      const text = await vfs.promises.readFile(path);
      try {
        return JSON.parse(text);
      } catch (e) {
        const bad = new Error('bad json: ' + path);
        bad.code = 'EJSON';
        throw bad;
      }
    }
''', [("app.loadJson('cfg.json')", {"cfg.json": '{"a": [1, 2], "b": null}'}, {}), ("app.loadJson('broken.json')", {"broken.json": '{oops'}, {}), ("app.loadJson('absent.json')", {}, {})])

app_fn("copyFile", "`copyFile(src, dst)` reads `src` and then writes the same text to `dst`; it resolves with `undefined`. Errors (for instance a missing source) reject with the file system's error and nothing is written.", r'''
    function copyFile(src, dst, cb) {
      vfs.readFile(src, (err, text) => {
        if (err) return cb(err);
        vfs.writeFile(dst, text, cb);
      });
    }
''', r'''
    async function copyFile(src, dst) {
      const text = await vfs.promises.readFile(src);
      await vfs.promises.writeFile(dst, text);
    }
''', [("app.copyFile('a.txt', 'b.txt')", {"a.txt": "alpha"}, {}), ("app.copyFile('nope.txt', 'b.txt')", {}, {}), ("app.copyFile('a.txt', 'out/')", {"a.txt": "alpha"}, {})])

app_fn("copyAll", "`copyAll(names, srcDir, dstDir, limit)` copies `srcDir/<name>` to `dstDir/<name>` for every name, running at most `limit` copies at the same time (copies start in the order of `names`; use `flow.mapLimit`). It resolves with the number of files copied; the first failure rejects with that error and no further copy is started.", r'''
    function copyAll(names, srcDir, dstDir, limit, cb) {
      flow.mapLimit(names, limit, (name, done) => copyFile(srcDir + '/' + name, dstDir + '/' + name, done), (err, results) => {
        if (err) return cb(err);
        cb(null, results.length);
      });
    }
''', r'''
    async function copyAll(names, srcDir, dstDir, limit) {
      const results = await flow.mapLimit(names, limit, (name) => copyFile(srcDir + '/' + name, dstDir + '/' + name));
      return results.length;
    }
''', [("app.copyAll(['a', 'b', 'c', 'd'], 'in', 'out', 2)", {"in/a": "1", "in/b": "22", "in/c": "333", "in/d": "4444"}, {}), ("app.copyAll(['a', 'zz', 'c'], 'in', 'out', 1)", {"in/a": "1", "in/c": "3"}, {}),
      ("app.copyAll([], 'in', 'out', 3)", {}, {}), ("app.copyAll(['a', 'b'], 'in', 'out', 9)", {"in/a": "x", "in/b": "y"}, {})])

app_fn("manifest", "`manifest(prefix)` lists the files whose path starts with `prefix` and resolves with an object mapping each path (without the prefix), in sorted order, to the length of its text. The files are read one after another, in name order.", r'''
    function manifest(prefix, cb) {
      vfs.list(prefix, (err, names) => {
        if (err) return cb(err);
        flow.mapSeries(names, (name, done) => vfs.readFile(name, (e, text) => done(e, e ? null : [name.slice(prefix.length), text.length])), (e2, pairs) => {
          if (e2) return cb(e2);
          const out = {};
          for (const [n, len] of pairs) out[n] = len;
          cb(null, out);
        });
      });
    }
''', r'''
    async function manifest(prefix) {
      const names = await vfs.promises.list(prefix);
      const pairs = await flow.mapSeries(names, async (name) => [name.slice(prefix.length), (await vfs.promises.readFile(name)).length]);
      const out = {};
      for (const [n, len] of pairs) out[n] = len;
      return out;
    }
''', [("app.manifest('docs/')", {"docs/b.md": "bb", "docs/a.md": "a", "other/x": "xxx"}, {}), ("app.manifest('none/')", {"docs/a.md": "a"}, {}), ("app.manifest('')", {"z": "zzzz", "y": ""}, {})])

app_fn("readFirst", "`readFirst(paths)` checks the paths in order, one at a time, with `exists`, and resolves with the text of the first one that exists (reading only that file); it resolves with `null` when none exists.", r'''
    function readFirst(paths, cb) {
      let i = 0;
      function next() {
        if (i === paths.length) return cb(null, null);
        const p = paths[i++];
        vfs.exists(p, (err, yes) => {
          if (err) return cb(err);
          if (!yes) return next();
          vfs.readFile(p, cb);
        });
      }
      next();
    }
''', r'''
    async function readFirst(paths) {
      for (const p of paths) {
        if (await vfs.promises.exists(p)) return vfs.promises.readFile(p);
      }
      return null;
    }
''', [("app.readFirst(['a', 'b', 'c'])", {"b": "bee", "c": "sea"}, {}), ("app.readFirst(['a'])", {}, {}), ("app.readFirst([])", {"a": "x"}, {}), ("app.readFirst(['dir/', 'a'])", {"a": "x"}, {})])

app_fn("safeRead", "`safeRead(path, fallback)` resolves with the file's text, or with `fallback` when the file does not exist (`ENOENT`); every other error (for example `EISDIR`) rejects.", r'''
    function safeRead(path, fallback, cb) {
      vfs.readFile(path, (err, text) => {
        if (err && err.code === 'ENOENT') return cb(null, fallback);
        cb(err || null, text);
      });
    }
''', r'''
    async function safeRead(path, fallback) {
      try {
        return await vfs.promises.readFile(path);
      } catch (err) {
        if (err.code === 'ENOENT') return fallback;
        throw err;
      }
    }
''', [("app.safeRead('a', 'dflt')", {"a": "here"}, {}), ("app.safeRead('b', 'dflt')", {}, {}), ("app.safeRead('dir/', 'dflt')", {}, {})])

app_fn("fetchConfig", "`fetchConfig(path, attempts)` loads the JSON file with `loadJson`, trying up to `attempts` times (use `flow.retry`; any failure is retried, including a missing file); it resolves with the first success and rejects with the last error.", r'''
    function fetchConfig(path, attempts, cb) {
      flow.retry(attempts, (n, done) => loadJson(path, done), cb);
    }
''', r'''
    function fetchConfig(path, attempts) {
      return flow.retry(attempts, () => loadJson(path));
    }
''', [("app.fetchConfig('c.json', 3)", {"c.json": '{"ok": true}'}, {"c.json": 2}), ("app.fetchConfig('c.json', 2)", {"c.json": '{"ok": true}'}, {"c.json": 2}), ("app.fetchConfig('missing.json', 2)", {}, {}), ("app.fetchConfig('c.json', 1)", {"c.json": "[]"}, {})])

app_fn("mirror", "`mirror(names, srcDir, dstDir)` copies the files one at a time in the order of `names` (use `flow.mapSeries`) and resolves with the list of destination paths; a failure rejects at once and the remaining names are not touched.", r'''
    function mirror(names, srcDir, dstDir, cb) {
      flow.mapSeries(names, (name, done) => copyFile(srcDir + '/' + name, dstDir + '/' + name, (err) => done(err, dstDir + '/' + name)), cb);
    }
''', r'''
    function mirror(names, srcDir, dstDir) {
      return flow.mapSeries(names, async (name) => {
        await copyFile(srcDir + '/' + name, dstDir + '/' + name);
        return dstDir + '/' + name;
      });
    }
''', [("app.mirror(['x', 'y'], 'src', 'dst')", {"src/x": "1", "src/y": "2"}, {}), ("app.mirror(['x', 'q', 'y'], 'src', 'dst')", {"src/x": "1", "src/y": "2"}, {}), ("app.mirror([], 'src', 'dst')", {}, {})])

APP_DEPS = {"copyAll": ["copyFile"], "mirror": ["copyFile"], "fetchConfig": ["loadJson"]}
APP_ORDER = ["loadJson", "copyFile", "copyAll", "manifest", "readFirst", "safeRead", "fetchConfig", "mirror"]

FLOW_CASES = [
    ("flow.series([() => Promise.resolve(1), async () => 2, async () => 3])", {}, {}),
    ("flow.series([async () => { log.push('a'); return 1; }, async () => { throw new Error('boom'); }, async () => { log.push('never'); }])", {}, {}),
    ("flow.series([])", {}, {}),
    ("flow.mapSeries([3, 1, 2], async (x) => { log.push('s' + x); await tick(x); log.push('e' + x); return x * 10; })", {}, {}),
    ("flow.mapLimit([1, 2, 3, 4, 5], 2, async (x) => { log.push('s' + x); await tick((x % 3) + 1); log.push('e' + x); return x; })", {}, {}),
    ("flow.mapLimit([], 3, async (x) => x)", {}, {}),
    ("flow.mapLimit([1, 2, 3], 2, async (x) => { log.push('s' + x); if (x === 2) throw new Error('bad2'); await tick(3); return x; })", {}, {}),
    ("flow.mapLimit([1, 2, 3], 1, async (x) => { log.push('s' + x); await tick(2 - (x % 2)); log.push('e' + x); return -x; })", {}, {}),
    ("flow.mapLimit([4, 3], 5, async (x) => { log.push('s' + x); await tick(x); log.push('e' + x); return x; })", {}, {}),
    ("flow.retry(3, async (n) => { log.push('try' + n); if (n < 3) throw new Error('e' + n); return 'ok' + n; })", {}, {}),
    ("flow.retry(2, async (n) => { log.push('try' + n); throw new Error('e' + n); })", {}, {}),
    ("flow.retry(1, async (n) => n)", {}, {}),
]

HIDDEN_TEST = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert');
    const vfs = require('../vfs');
    const flow = require('../flow');
    const app = require('../app');

    const CASES = %s;

    function tick(n) {
      return new Promise((resolve) => {
        const go = (k) => (k <= 0 ? resolve() : setImmediate(() => go(k - 1)));
        go(n);
      });
    }

    async function runCase(c) {
      vfs.reset(c.files, c.flaky);
      const log = [];
      let out;
      try {
        const value = await eval(c.expr);
        out = { ok: value === undefined ? null : value };
      } catch (e) {
        out = { err: e.code || e.message };
      }
      return JSON.parse(JSON.stringify({ out, trace: vfs.trace.slice(), log }));
    }

    test('behaviour', async () => {
      const bad = [];
      for (const c of CASES) {
        const got = await runCase(c);
        try {
          assert.deepStrictEqual(got, c.want);
        } catch (e) {
          bad.push(c.expr + ' -> ' + JSON.stringify(got) + ', want ' + JSON.stringify(c.want));
        }
      }
      assert.strictEqual(bad.length, 0, bad.length + ' cases differ:\n  ' + bad.slice(0, 5).join('\n  '));
    });

    test('promise-returning', async () => {
      vfs.reset({ a: '1' });
      assert.ok(flow.series([]) instanceof Promise, 'flow.series must return a promise');
      assert.ok(flow.retry(1, async () => 1) instanceof Promise, 'flow.retry must return a promise');
      await tick(5);
    });
''')

DRIVER = dd(r'''
    'use strict';
    const fs = require('fs');
    const vfs = require('./vfs');
    const flow = require('./flow');
    const app = require('./app');

    function tick(n) {
      return new Promise((resolve) => {
        const go = (k) => (k <= 0 ? resolve() : setImmediate(() => go(k - 1)));
        go(n);
      });
    }

    async function runCase(c) {
      vfs.reset(c.files, c.flaky);
      const log = [];
      let out;
      try {
        const value = await eval(c.expr);
        out = { ok: value === undefined ? null : value };
      } catch (e) {
        out = { err: e.code || e.message };
      }
      return JSON.parse(JSON.stringify({ out, trace: vfs.trace.slice(), log }));
    }

    (async () => {
      const cases = JSON.parse(fs.readFileSync('cases_in.json', 'utf8'));
      const out = [];
      for (const c of cases) out.push({ expr: c.expr, files: c.files, flaky: c.flaky, want: await runCase(c) });
      console.log(JSON.stringify(out));
    })();
''')


def _app_text(fns, which):
    head = "'use strict';\nconst vfs = require('./vfs');\nconst flow = require('./flow');\n\n"
    body = "\n".join(APP[f]["old" if which == "old" else "new"] for f in fns)
    return head + body + "\nmodule.exports = { " + ", ".join(fns) + " };\n"


@family("port-callbacks-to-promises", category="port", lang="javascript", kind="refactor", n=8,
        summary="convert node-style callback helpers and the code built on them to promises (ordering and concurrency preserved)")
def gen_js(rng, n):
    sizes = [2, 3, 3, 4, 5, 6, 7, 8]
    prompts = [
        "The repo's control-flow helpers (`flow.js`) and everything in `app.js` use node-style callbacks. Convert them to promises: the helpers keep their names but take and return promises (README.md has the exact contract), and the app functions drop their callback parameter and return promises too. `vfs.js` already has a promise API under `vfs.promises`; don't touch it.",
        "callbacks -> promises please. flow.js and app.js. new contract is in README.md (what the helpers accept, what they resolve/reject with, concurrency and ordering). keep the same order of file operations, tests check the trace",
        "Ticket: drop the callback style from our small async toolkit. Acceptance: `flow.*` and `app.*` return promises, no function takes a callback, behaviour (results, errors, and the order in which `vfs` operations are issued) is unchanged. Contract in README.md; `vfs.js` is not part of this change.",
        "We are moving this service to async code. Rewrite `flow.js` and `app.js` so that they work with promises instead of `(err, value)` callbacks; the README describes how each helper must behave, including how many things may run at once. The virtual file system in `vfs.js` already offers promises.",
    ]
    for i in range(n):
        k = sizes[i % len(sizes)]
        chosen = set(rng.sample(APP_ORDER, k))
        for f in list(chosen):
            chosen.update(APP_DEPS.get(f, []))
        fns = [f for f in APP_ORDER if f in chosen]
        cases = [(e, files, flaky) for e, files, flaky in FLOW_CASES]
        for f in fns:
            cases += APP[f]["cases"]
        case_objs = [{"expr": e, "files": files, "flaky": flaky} for e, files, flaky in cases]
        base_files = {"vfs.js": VFS}
        start_files = {"flow.js": FLOW_OLD, "app.js": _app_text(fns, "old"), **base_files}
        new_files = {"flow.js": FLOW_NEW, "app.js": _app_text(fns, "new")}
        code, out = run_local({**new_files, **base_files, "driver.js": DRIVER, "cases_in.json": json.dumps(case_objs)}, ["node", "driver.js"], timeout=120)
        if code != 0:
            raise RuntimeError("reference migration fails:\n" + out[-1500:])
        expected = json.loads(out.strip().splitlines()[-1])
        full = [dict(c, want=c["want"]) for c in expected]
        hidden = HIDDEN_TEST % json.dumps(full, ensure_ascii=True)
        vis_cases = [full[0], full[3], full[4], full[9]] + [c for c in full if c["expr"].startswith("app.")][:3]
        visible = HIDDEN_TEST % json.dumps(vis_cases, ensure_ascii=True)
        visible = visible.replace("test('promise-returning'", "test('promise-returning-visible'")
        flow_doc = dd('''
            ## `flow.js`

            All helpers take promise-returning functions and return a promise.

            * `series(tasks)`: `tasks` are functions with no arguments that return a promise (or a value). They run one at a time, in order; the result is the array of their results. The first rejection rejects the whole call and later tasks are not started.
            * `mapSeries(items, fn)`: like `series` with `fn(item)` for each item; resolves with the array of results.
            * `mapLimit(items, limit, fn)`: calls `fn(item)` for every item with at most `limit` calls in flight at any time. Calls start in the order of `items` and a new one starts as soon as a slot frees up; results are in the order of `items`. The first rejection rejects the whole call and no further call is started (calls already running are left alone). An empty `items` resolves with `[]`.
            * `retry(times, fn)`: calls `fn(attempt)` (attempts are numbered from 1) up to `times` times until it succeeds; resolves with that result, or rejects with the **last** error.
        ''')
        app_doc = "## `app.js`\n\nExported functions (all return promises):\n\n" + "\n".join("* " + APP[f]["doc"] for f in fns) + "\n"
        readme = ("# asset toolkit\n\nA small async toolkit over an in-memory virtual file system (`vfs.js`, which has a callback API and, under `vfs.promises`, a promise API with the same "
                  "operations: `readFile`, `writeFile`, `exists`, `list`). `flow.js` holds control-flow helpers and `app.js` the application functions.\n\n"
                  "Tests: `node --test test/*.test.js`. Operations are deterministic: every `vfs` call takes a few event-loop turns, and `vfs.trace` records the order in which "
                  "operations were issued.\n\n" + flow_doc + "\n" + app_doc)
        d = 2 + (k >= 3) + (k >= 5) + (k >= 7)
        yield Task(
            slug=f"{i + 1:02d}-{len(fns)}-functions",
            prompt=rng.choice(prompts),
            difficulty=max(2, min(5, d)),
            lang="javascript",
            kind="refactor",
            start={**start_files, "README.md": readme, "test/visible.test.js": visible},
            hidden={"test/behaviour.test.js": hidden},
            solution=new_files,
            verify="node --test test/*.test.js",
            protected=["vfs.js", "README.md"],
            tags=["api-migration", "callbacks-to-promises", "javascript"],
            notes={"app_functions": fns},
        )
