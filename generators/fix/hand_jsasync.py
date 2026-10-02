"""Async control flow in javascript on fake timers: concurrency limits, retries, timeouts, debounce and throttle."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

TIMERS = dd(r'''
    'use strict';

    // A manual clock: nothing runs until `tick` is called, so tests are deterministic.
    class FakeTimers {
      constructor() {
        this.t = 0;
        this.queue = [];
        this.nextId = 1;
      }

      now() {
        return this.t;
      }

      setTimeout(fn, ms) {
        const id = this.nextId++;
        this.queue.push({ id, at: this.t + ms, fn });
        return id;
      }

      clearTimeout(id) {
        this.queue = this.queue.filter((x) => x.id !== id);
      }

      pending() {
        return this.queue.length;
      }

      tick(ms) {
        const end = this.t + ms;
        for (;;) {
          const due = this.queue.filter((x) => x.at <= end).sort((a, b) => a.at - b.at || a.id - b.id)[0];
          if (!due) break;
          this.queue = this.queue.filter((x) => x !== due);
          this.t = due.at;
          due.fn();
        }
        this.t = end;
      }
    }

    module.exports = { FakeTimers };
''')

PKG = '{\n  "name": "%s",\n  "version": "1.0.0",\n  "private": true\n}\n'

# ------------------------------------------------------------------------------------------------------------------
# Base A: promise helpers.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # asyncflow

    Promise helpers of a job runner (CommonJS). `src/timers.js` has a `FakeTimers` clock for tests.

    * `forEachSeries(items, fn)`: awaits `fn(item, index)` for each item **one after the other**; the returned promise resolves after the
      last one finished and rejects with the first failure (later items are not started).
    * `mapLimit(items, limit, fn)`: runs `fn(item, index)` for every item with **at most `limit` calls in flight**, starting the next item as soon as a
      slot frees up; resolves to the results **in input order**. After the first failure no new call is started; calls already in
      flight are awaited, then the promise rejects with the **first** error that happened.
    * `retry(fn, { attempts = 3, delay = 100, sleep })`: calls `fn(attemptNumber)` (the number starts at 1); if it throws or rejects it is tried again
      after `await sleep(delay * 2 ** (attempt - 1))`, but never after the last attempt, whose error is thrown. A return value ends it.
    * `withTimeout(promise, ms, timers)`: settles like `promise`, or rejects with `TimeoutError` after `ms` on `timers`. Whichever happens first, no
      timer is left pending afterwards (`timers.pending()` is 0).
''')

A_ASYNC = dd(r'''
    'use strict';

    class TimeoutError extends Error {}

    async function forEachSeries(items, fn) {
      for (let i = 0; i < items.length; i++) await fn(items[i], i);
    }

    async function mapLimit(items, limit, fn) {
      const results = new Array(items.length);
      let next = 0;
      let failed = false;
      let firstError;
      async function worker() {
        while (!failed && next < items.length) {
          const i = next++;
          try {
            results[i] = await fn(items[i], i);
          } catch (e) {
            if (!failed) {
              failed = true;
              firstError = e;
            }
            return;
          }
        }
      }
      const workers = [];
      for (let w = 0; w < Math.min(limit, items.length); w++) workers.push(worker());
      await Promise.all(workers);
      if (failed) throw firstError;
      return results;
    }

    async function retry(fn, { attempts = 3, delay = 100, sleep } = {}) {
      let lastError;
      for (let attempt = 1; attempt <= attempts; attempt++) {
        try {
          return await fn(attempt);
        } catch (e) {
          lastError = e;
          if (attempt < attempts) await sleep(delay * 2 ** (attempt - 1));
        }
      }
      throw lastError;
    }

    function withTimeout(promise, ms, timers) {
      return new Promise((resolve, reject) => {
        const id = timers.setTimeout(() => reject(new TimeoutError(`timed out after ${ms} ms`)), ms);
        promise.then(
          (v) => {
            timers.clearTimeout(id);
            resolve(v);
          },
          (e) => {
            timers.clearTimeout(id);
            reject(e);
          },
        );
      });
    }

    module.exports = { forEachSeries, mapLimit, retry, withTimeout, TimeoutError };
''')

A_VISIBLE = {
    "test/async.test.js": dd(r'''
        const test = require('node:test');
        const assert = require('node:assert');
        const { forEachSeries, mapLimit, retry } = require('../src/async');

        test('mapLimit returns the results', async () => {
          assert.deepStrictEqual(await mapLimit([1, 2, 3], 2, async (x) => x * 2), [2, 4, 6]);
        });

        test('forEachSeries visits everything', async () => {
          const seen = [];
          await forEachSeries(['a', 'b'], async (x) => { seen.push(x); });
          assert.deepStrictEqual(seen, ['a', 'b']);
        });

        test('retry returns the value of the first success', async () => {
          const r = await retry(async (n) => (n < 2 ? Promise.reject(new Error('no')) : 'ok'), { sleep: async () => {} });
          assert.strictEqual(r, 'ok');
        });
    '''),
}

A_HIDDEN = {
    "test/hidden_async.test.js": dd(r'''
        const test = require('node:test');
        const assert = require('node:assert');
        const { forEachSeries, mapLimit, retry, withTimeout, TimeoutError } = require('../src/async');
        const { FakeTimers } = require('../src/timers');

        const flush = () => new Promise((resolve) => setImmediate(resolve));
        function deferred() {
          let resolve;
          let reject;
          const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
          return { promise, resolve, reject };
        }

        test('mapLimit keeps at most `limit` calls in flight and starts the next as soon as a slot frees', async () => {
          const gates = [0, 1, 2, 3].map(() => deferred());
          const started = [];
          let active = 0;
          let maxActive = 0;
          const p = mapLimit([10, 20, 30, 40], 2, async (x, i) => {
            started.push(i);
            active += 1;
            maxActive = Math.max(maxActive, active);
            await gates[i].promise;
            active -= 1;
            return x * 2;
          });
          await flush();
          assert.deepStrictEqual(started, [0, 1]);
          gates[1].resolve();
          await flush();
          assert.deepStrictEqual(started, [0, 1, 2]);
          gates[2].resolve();
          await flush();
          assert.deepStrictEqual(started, [0, 1, 2, 3]);
          gates[3].resolve();
          gates[0].resolve();
          assert.deepStrictEqual(await p, [20, 40, 60, 80]);
          assert.strictEqual(maxActive, 2);
        });

        test('mapLimit results are in input order whatever the completion order', async () => {
          const gates = [0, 1, 2].map(() => deferred());
          const p = mapLimit(['a', 'b', 'c'], 3, async (x, i) => { await gates[i].promise; return x + x; });
          gates[2].resolve();
          gates[0].resolve();
          gates[1].resolve();
          assert.deepStrictEqual(await p, ['aa', 'bb', 'cc']);
        });

        test('mapLimit edge cases', async () => {
          assert.deepStrictEqual(await mapLimit([], 3, async () => 1), []);
          assert.deepStrictEqual(await mapLimit([1, 2], 10, async (x) => x), [1, 2]);
          const order = [];
          await mapLimit([1, 2, 3], 1, async (x) => { order.push(`s${x}`); await flush(); order.push(`e${x}`); });
          assert.deepStrictEqual(order, ['s1', 'e1', 's2', 'e2', 's3', 'e3']);
        });

        test('after a failure nothing new starts, in-flight calls finish, the first error is thrown', async () => {
          const gates = [0, 1, 2, 3, 4].map(() => deferred());
          const started = [];
          const p = mapLimit([0, 1, 2, 3, 4], 2, async (x, i) => { started.push(i); await gates[i].promise; return x; });
          const outcome = p.then(() => 'resolved', (e) => e.message);
          await flush();
          gates[1].reject(new Error('boom'));
          await flush();
          assert.deepStrictEqual(started, [0, 1]);
          gates[0].resolve();
          assert.strictEqual(await outcome, 'boom');
          assert.deepStrictEqual(started, [0, 1]);
        });

        test('with two failures the first one in time is reported', async () => {
          const gates = [deferred(), deferred(), deferred()];
          const p = mapLimit([0, 1, 2], 3, async (x, i) => { await gates[i].promise; return x; });
          const outcome = p.then(() => 'resolved', (e) => e.message);
          await flush();
          gates[2].reject(new Error('first'));
          gates[0].reject(new Error('second'));
          gates[1].resolve();
          assert.strictEqual(await outcome, 'first');
        });

        test('the promise waits for the in-flight call before rejecting', async () => {
          const gates = [deferred(), deferred()];
          let settled = false;
          const p = mapLimit([0, 1], 2, async (x, i) => { await gates[i].promise; return x; });
          p.then(() => { settled = true; }, () => { settled = true; });
          await flush();
          gates[1].reject(new Error('x'));
          await flush();
          assert.strictEqual(settled, false);
          gates[0].resolve();
          await assert.rejects(p, /x/);
        });

        test('forEachSeries runs one at a time and resolves after the last', async () => {
          const gates = [deferred(), deferred(), deferred()];
          const log = [];
          let done = false;
          const p = forEachSeries([0, 1, 2], async (x) => { log.push(`start${x}`); await gates[x].promise; log.push(`end${x}`); }).then(() => { done = true; });
          await flush();
          assert.deepStrictEqual(log, ['start0']);
          gates[0].resolve();
          await flush();
          assert.deepStrictEqual(log, ['start0', 'end0', 'start1']);
          gates[1].resolve();
          gates[2].resolve();
          await flush();
          assert.strictEqual(done, true);
          await p;
          assert.deepStrictEqual(log, ['start0', 'end0', 'start1', 'end1', 'start2', 'end2']);
        });

        test('forEachSeries stops at the first failure', async () => {
          const seen = [];
          await assert.rejects(forEachSeries([1, 2, 3], async (x) => { seen.push(x); if (x === 2) throw new Error('stop'); }), /stop/);
          assert.deepStrictEqual(seen, [1, 2]);
        });

        test('retry waits with doubling delays and passes the attempt number', async () => {
          const sleeps = [];
          const attempts = [];
          const r = await retry(async (n) => { attempts.push(n); if (n < 3) throw new Error(`fail ${n}`); return 'done'; }, { attempts: 5, delay: 100, sleep: async (ms) => { sleeps.push(ms); } });
          assert.strictEqual(r, 'done');
          assert.deepStrictEqual(attempts, [1, 2, 3]);
          assert.deepStrictEqual(sleeps, [100, 200]);
        });

        test('retry throws the last error and does not sleep after the last attempt', async () => {
          const sleeps = [];
          await assert.rejects(retry(async (n) => { throw new Error(`fail ${n}`); }, { attempts: 3, delay: 10, sleep: async (ms) => { sleeps.push(ms); } }), /fail 3/);
          assert.deepStrictEqual(sleeps, [10, 20]);
        });

        test('retry also retries synchronous throws and rejected promises', async () => {
          let n = 0;
          const r = await retry((a) => { n += 1; if (a === 1) throw new Error('sync'); if (a === 2) return Promise.reject(new Error('async')); return 'third'; }, { sleep: async () => {} });
          assert.strictEqual(r, 'third');
          assert.strictEqual(n, 3);
        });

        test('retry with a single attempt', async () => {
          await assert.rejects(retry(async () => { throw new Error('once'); }, { attempts: 1, sleep: async () => { throw new Error('must not sleep'); } }), /once/);
        });

        test('withTimeout resolves and leaves no timer behind', async () => {
          const timers = new FakeTimers();
          const d = deferred();
          const p = withTimeout(d.promise, 100, timers);
          assert.strictEqual(timers.pending(), 1);
          d.resolve('v');
          assert.strictEqual(await p, 'v');
          assert.strictEqual(timers.pending(), 0);
        });

        test('withTimeout passes rejections through and leaves no timer behind', async () => {
          const timers = new FakeTimers();
          const d = deferred();
          const p = withTimeout(d.promise, 100, timers);
          d.reject(new Error('nope'));
          await assert.rejects(p, /nope/);
          assert.strictEqual(timers.pending(), 0);
        });

        test('withTimeout rejects with TimeoutError at the deadline', async () => {
          const timers = new FakeTimers();
          const d = deferred();
          const p = withTimeout(d.promise, 100, timers);
          const outcome = p.then(() => 'resolved', (e) => e);
          timers.tick(99);
          await flush();
          assert.strictEqual(timers.pending(), 1);
          timers.tick(1);
          const err = await outcome;
          assert.ok(err instanceof TimeoutError);
          assert.match(err.message, /100 ms/);
          d.resolve('late');
        });
    '''),
}


def _a_prompts():
    p = {}
    p["foreach"] = (
        "The nightly migration runs its steps with `forEachSeries` but they overlap: step 2 starts before step 1 finished (the "
        "second one needs the first one's table), and the function returns before the last step is done so the script exits early. "
        "It is supposed to await each step."
    )
    p["order"] = (
        "`mapLimit` returns results in the order the jobs finished rather than the order of the input, so reports are shuffled whenever "
        "one request is slower than the next. Results must line up with the input items."
    )
    p["unlimited"] = (
        "We configured `mapLimit` with a concurrency of 5 to be kind to the API but the provider's dashboard shows all 200 requests in flight at once."
    )
    p["timer-leak"] = (
        "Our test run hangs for a minute after the last test: `withTimeout` leaves its timer behind when the wrapped promise "
        "resolves in time, and the pending timers keep the process alive. After the promise settles no timer should remain."
    )
    p["retry-no-await"] = (
        "`retry` never retries our async uploads: the first rejected promise goes straight to the caller (as an unhandled rejection "
        "from inside) and the backoff sleeps never happen. Functions that throw synchronously are retried fine."
    )
    p["keeps-starting"] = (
        "When one item of a `mapLimit` batch fails, the remaining items still get processed (we saw 40 more API calls after the first "
        "error) and only then does the error come out. After a failure no new call should start, only those already in flight are awaited."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "src/async.js": A_ASYNC, "src/timers.js": TIMERS, "package.json": PKG % "asyncflow"}
    a = "src/async.js"
    bugs = [
        Bug("series-does-not-wait", 3, {a: [("  for (let i = 0; i < items.length; i++) await fn(items[i], i);\n", "  items.forEach(async (item, i) => {\n    await fn(item, i);\n  });\n")]}, P["foreach"]),
        Bug("results-in-completion-order", 3, {a: [("  const results = new Array(items.length);\n", "  const results = [];\n"), ("        results[i] = await fn(items[i], i);\n", "        results.push(await fn(items[i], i));\n")]}, P["order"]),
        Bug("limit-not-applied", 2, {a: [("  for (let w = 0; w < Math.min(limit, items.length); w++) workers.push(worker());\n", "  for (let w = 0; w < items.length; w++) workers.push(worker());\n")]}, P["unlimited"]),
        Bug("timeout-timer-left-pending", 3, {a: [("      (v) => {\n        timers.clearTimeout(id);\n        resolve(v);\n      },\n", "      (v) => {\n        resolve(v);\n      },\n")]}, P["timer-leak"]),
        Bug("retry-forgets-to-await", 3, {a: [("      return await fn(attempt);\n", "      return fn(attempt);\n")]}, P["retry-no-await"]),
        Bug("new-calls-start-after-a-failure", 4, {a: [("    while (!failed && next < items.length) {\n", "    while (next < items.length) {\n")]}, P["keeps-starting"]),
    ]
    return Base("asyncflow", "javascript", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B: debounce and throttle.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # ratelimits

    `debounce` and `throttle` for UI events (CommonJS) on an injected timer object (`src/timers.js` has a `FakeTimers` clock: `now()`,
    `setTimeout`, `clearTimeout`, `tick(ms)`, `pending()`).

    * `debounce(fn, ms, timers)`: every call restarts a `ms` countdown; when it runs out `fn` is called **once with the arguments of the last call**.
      `.cancel()` drops the pending call (and its timer); `.flush()` runs the pending call now, if there is one.
    * `throttle(fn, ms, timers)`: the first call runs at once. After every execution there is a window of `ms`; calls inside the window are coalesced
      into **one trailing call with the arguments of the last of them**, executed when the window ends (and that execution opens the next window).
      A call after the window has passed runs at once. So executions are never closer than `ms`, and a steady stream of calls is executed every
      `ms`. `.cancel()` drops the pending trailing call (and its timer).
''')

B_LIMITS = dd(r'''
    'use strict';

    function debounce(fn, ms, timers) {
      let id = null;
      let lastArgs;
      const debounced = (...args) => {
        lastArgs = args;
        if (id !== null) timers.clearTimeout(id);
        id = timers.setTimeout(() => {
          id = null;
          fn(...lastArgs);
        }, ms);
      };
      debounced.cancel = () => {
        if (id !== null) {
          timers.clearTimeout(id);
          id = null;
        }
      };
      debounced.flush = () => {
        if (id !== null) {
          timers.clearTimeout(id);
          id = null;
          fn(...lastArgs);
        }
      };
      return debounced;
    }

    function throttle(fn, ms, timers) {
      let lastRun = -Infinity;
      let id = null;
      let pending;
      const run = (args) => {
        lastRun = timers.now();
        fn(...args);
      };
      const throttled = (...args) => {
        const remaining = lastRun + ms - timers.now();
        if (remaining <= 0) {
          if (id !== null) {
            timers.clearTimeout(id);
            id = null;
          }
          run(args);
        } else {
          pending = args;
          if (id === null) {
            id = timers.setTimeout(() => {
              id = null;
              run(pending);
            }, remaining);
          }
        }
      };
      throttled.cancel = () => {
        if (id !== null) {
          timers.clearTimeout(id);
          id = null;
        }
      };
      return throttled;
    }

    module.exports = { debounce, throttle };
''')

B_VISIBLE = {
    "test/limits.test.js": dd(r'''
        const test = require('node:test');
        const assert = require('node:assert');
        const { debounce, throttle } = require('../src/limits');
        const { FakeTimers } = require('../src/timers');

        test('debounce fires once after the quiet period', () => {
          const timers = new FakeTimers();
          const calls = [];
          const d = debounce((x) => calls.push(x), 50, timers);
          d(1);
          timers.tick(60);
          assert.deepStrictEqual(calls, [1]);
        });

        test('throttle runs the first call at once', () => {
          const timers = new FakeTimers();
          const calls = [];
          const t = throttle((x) => calls.push(x), 100, timers);
          t('a');
          assert.deepStrictEqual(calls, ['a']);
        });
    '''),
}

B_HIDDEN = {
    "test/hidden_limits.test.js": dd(r'''
        const test = require('node:test');
        const assert = require('node:assert');
        const { debounce, throttle } = require('../src/limits');
        const { FakeTimers } = require('../src/timers');

        test('debounce restarts the countdown on every call and uses the last arguments', () => {
          const timers = new FakeTimers();
          const calls = [];
          const d = debounce((...a) => calls.push(a), 50, timers);
          d(1, 'a');
          timers.tick(10);
          d(2, 'b');
          timers.tick(10);
          d(3, 'c');
          timers.tick(49);
          assert.deepStrictEqual(calls, []);
          timers.tick(1);
          assert.deepStrictEqual(calls, [[3, 'c']]);
          assert.strictEqual(timers.pending(), 0);
        });

        test('debounce can fire again after a quiet period, with fresh arguments', () => {
          const timers = new FakeTimers();
          const calls = [];
          const d = debounce((x) => calls.push(x), 20, timers);
          d('first');
          timers.tick(20);
          d('second');
          d('third');
          timers.tick(20);
          assert.deepStrictEqual(calls, ['first', 'third']);
        });

        test('debounce cancel and flush', () => {
          const timers = new FakeTimers();
          const calls = [];
          const d = debounce((x) => calls.push(x), 30, timers);
          d('x');
          d.cancel();
          assert.strictEqual(timers.pending(), 0);
          timers.tick(100);
          assert.deepStrictEqual(calls, []);
          d('y');
          d('z');
          d.flush();
          assert.deepStrictEqual(calls, ['z']);
          assert.strictEqual(timers.pending(), 0);
          timers.tick(100);
          assert.deepStrictEqual(calls, ['z']);
          d.flush();
          assert.deepStrictEqual(calls, ['z']);
        });

        test('throttle: leading call, one trailing call with the last arguments', () => {
          const timers = new FakeTimers();
          const log = [];
          const t = throttle((x) => log.push([timers.now(), x]), 100, timers);
          t('a');
          timers.tick(10);
          t('b');
          timers.tick(10);
          t('c');
          assert.deepStrictEqual(log, [[0, 'a']]);
          timers.tick(79);
          assert.deepStrictEqual(log, [[0, 'a']]);
          timers.tick(1);
          assert.deepStrictEqual(log, [[0, 'a'], [100, 'c']]);
          assert.strictEqual(timers.pending(), 0);
        });

        test('throttle: a single call inside the window still gets its trailing execution', () => {
          const timers = new FakeTimers();
          const log = [];
          const t = throttle((x) => log.push([timers.now(), x]), 100, timers);
          t(1);
          timers.tick(30);
          t(2);
          timers.tick(100);
          assert.deepStrictEqual(log, [[0, 1], [100, 2]]);
        });

        test('throttle: the window opens after each execution, including the trailing one', () => {
          const timers = new FakeTimers();
          const log = [];
          const t = throttle((x) => log.push([timers.now(), x]), 100, timers);
          t('a');
          timers.tick(50);
          t('b');
          timers.tick(50);
          assert.deepStrictEqual(log, [[0, 'a'], [100, 'b']]);
          timers.tick(10);
          t('c');
          timers.tick(89);
          assert.deepStrictEqual(log, [[0, 'a'], [100, 'b']]);
          timers.tick(1);
          assert.deepStrictEqual(log, [[0, 'a'], [100, 'b'], [200, 'c']]);
        });

        test('throttle: a call after a quiet window runs at once', () => {
          const timers = new FakeTimers();
          const log = [];
          const t = throttle((x) => log.push([timers.now(), x]), 100, timers);
          t('a');
          timers.tick(250);
          t('b');
          assert.deepStrictEqual(log, [[0, 'a'], [250, 'b']]);
          assert.strictEqual(timers.pending(), 0);
        });

        test('throttle: a steady stream is executed about every `ms` and never more often', () => {
          const timers = new FakeTimers();
          const log = [];
          const t = throttle((x) => log.push([timers.now(), x]), 100, timers);
          for (let i = 0; i < 14; i++) {
            t(i);
            timers.tick(30);
          }
          timers.tick(200);
          const times = log.map(([at]) => at);
          for (let i = 1; i < times.length; i++) assert.ok(times[i] - times[i - 1] >= 100, `executions at ${times}`);
          assert.ok(times.length >= 4, `only ${times.length} executions: ${times}`);
          assert.strictEqual(log[log.length - 1][1], 13);
          assert.strictEqual(times[0], 0);
        });

        test('throttle cancel drops the trailing call', () => {
          const timers = new FakeTimers();
          const log = [];
          const t = throttle((x) => log.push(x), 100, timers);
          t('a');
          t('b');
          t.cancel();
          assert.strictEqual(timers.pending(), 0);
          timers.tick(300);
          assert.deepStrictEqual(log, ['a']);
        });
    '''),
}


def _b_prompts():
    p = {}
    p["no-restart"] = (
        "The search box fires one request per keystroke burst *segment* instead of one per pause: typing `hello` quickly sends several "
        "requests, each with a partial text. A debounce should restart its countdown on every call."
    )
    p["first-args"] = (
        "Our debounced autosave saves the text as it was when the user *started* typing, not the final text: the call that goes through "
        "has the arguments of the first call in the burst."
    )
    p["cancel-leak"] = (
        "Cancelling a debounced handler (when the component unmounts) does not stop it: the callback still fires 300 ms later and touches a "
        "destroyed component. `cancel` must drop the timer."
    )
    p["no-trailing"] = (
        "A throttled scroll handler drops the final position: if the user stops scrolling inside the throttle window, the last event is never "
        "delivered, so the sticky header ends in the wrong place. The last call of a burst must be delivered when the window ends."
    )
    p["window-from-call"] = (
        "With a throttled mouse-move handler (100 ms) and a steady stream of events every 30 ms, the handler runs only once at the very start "
        "and then rarely: the window seems to be measured from the last *call* rather than from the last execution, so it keeps "
        "being pushed out. During a stream it should run about every 100 ms."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "src/limits.js": B_LIMITS, "src/timers.js": TIMERS, "package.json": PKG % "ratelimits"}
    m = "src/limits.js"
    bugs = [
        Bug("debounce-never-restarts", 2, {m: [("    if (id !== null) timers.clearTimeout(id);\n    id = timers.setTimeout(() => {\n      id = null;\n      fn(...lastArgs);\n    }, ms);\n",
                                                "    if (id !== null) return;\n    id = timers.setTimeout(() => {\n      id = null;\n      fn(...lastArgs);\n    }, ms);\n")]}, P["no-restart"]),
        Bug("debounce-keeps-the-first-arguments", 2, {m: [("  const debounced = (...args) => {\n    lastArgs = args;\n", "  const debounced = (...args) => {\n    if (id === null) lastArgs = args;\n")]}, P["first-args"]),
        Bug("debounce-cancel-keeps-the-timer", 2, {m: [("  debounced.cancel = () => {\n    if (id !== null) {\n      timers.clearTimeout(id);\n      id = null;\n    }\n  };\n",
                                                        "  debounced.cancel = () => {\n    id = null;\n  };\n")]}, P["cancel-leak"]),
        Bug("throttle-without-trailing-call", 3, {m: [("      pending = args;\n      if (id === null) {\n        id = timers.setTimeout(() => {\n          id = null;\n          run(pending);\n        }, remaining);\n      }\n", "")]}, P["no-trailing"]),
        Bug("throttle-window-from-last-call", 4, {m: [("  const run = (args) => {\n    lastRun = timers.now();\n    fn(...args);\n  };\n", "  const run = (args) => {\n    fn(...args);\n  };\n"),
                                                  ("    const remaining = lastRun + ms - timers.now();\n", "    const remaining = lastRun + ms - timers.now();\n    lastRun = timers.now();\n")]}, P["window-from-call"]),
    ]
    return Base("ratelimits", "javascript", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-js-async", category="fix", lang="javascript", kind="fix", n=11,
        summary="async control flow on fake timers: concurrency limits, retries, timeouts, debounce and throttle (javascript)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
