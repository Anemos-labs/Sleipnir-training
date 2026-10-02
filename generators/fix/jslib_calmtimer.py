"""Debounce, throttle and batching over an injectable clock (javascript): bugs injected into a timing library."""
from fx import Lib, dd
from generators.fix._lang2 import JS_VERIFY, PACKAGE_JSON, register_libs

README = dd(r'''
    # calmtimer

    Small timing helpers that run against an injectable clock, so they can be tested without waiting. CommonJS:
    `const { FakeClock } = require('./src/clock')`, `const { debounce, throttle } = require('./src/debounce')`,
    `const { createBatcher } = require('./src/batcher')`.

    A *clock* is any object with `now()`, `setTimeout(fn, delay)` (returns an id) and `clearTimeout(id)`; the helpers
    take it as their last argument (it defaults to the real clock).

    ## `FakeClock` (`src/clock.js`)

    `new FakeClock(start = 0)`: time stands still until `advance(ms)` is called.

    * `now()` is the current time; `pending()` the number of timers that have not fired or been cleared.
    * `setTimeout(fn, delay)` schedules `fn` at `now() + max(0, delay)` and returns a numeric id. `clearTimeout(id)` removes it
      (unknown ids are ignored).
    * `advance(ms)` moves time forward by `ms` (a negative `ms` is a `RangeError`) and runs every timer that falls due on
      the way, earliest first, equal due times in the order they were scheduled. While a callback runs, `now()` is its due
      time. Timers scheduled by callbacks run in the same `advance` call if they fall due before the target time.
      Afterwards `now()` is exactly the target time.

    ## `debounce(fn, wait, opts = {}, clock)` (`src/debounce.js`)

    Returns a function `d(...args)` that delays calls to `fn`. Options: `leading` (default `false`), `trailing` (default
    `true`) and `maxWait`. `fn` must be a function (`TypeError`); `wait` a finite number `>= 0` (`RangeError`); `maxWait`, when
    given, must be `>= wait` (`RangeError`); `leading` and `trailing` both false is a `TypeError`.

    A *burst* starts with a call made while the debounced function is idle (no timer pending) and ends when its timer
    fires, or on `cancel()` / `flush()`.

    * On a call at time `t`: if it is the first of a burst, the burst starts at `t`, and with `leading` `fn(...args)` is
      called at once; otherwise (or without `leading`) and with `trailing`, the arguments are remembered as the pending
      trailing call, replacing earlier ones. Then the timer is restarted with the delay `wait`, or, when `maxWait` is set,
      `min(wait, burstStart + maxWait - t)`.
    * When the timer fires: with `trailing` and a pending trailing call, `fn` is called with the remembered arguments;
      then the debounced function is idle again. (So with `leading` and `trailing` a burst of one call calls `fn` once.)
    * `d(...)` returns the result of the latest call of `fn` (`undefined` before the first).
    * `d.cancel()` clears the timer and forgets any pending trailing call. `d.flush()` calls `fn` now with the pending
      trailing call, if there is one, clears the timer and returns the latest result. `d.pending()` is `true` while a timer is
      pending.

    ## `throttle(fn, wait, opts = {}, clock)`

    `debounce(fn, wait, { leading, trailing, maxWait: wait }, clock)` with `leading` and `trailing` both defaulting to `true`:
    at most one call per `wait` milliseconds, the first call at once and the last call of a window at its end.

    ## `createBatcher(fn, { size, wait }, clock)` (`src/batcher.js`)

    Collects items and hands them to `fn` as an array. `size` (an integer `>= 1`) and `wait` (a number `>= 0`) are validated
    (`RangeError`).

    * `add(item)`: the item joins the buffer. When it is the first item, a timer for `wait` ms starts (later items do **not**
      restart it). When the buffer reaches `size` items, it is flushed at once.
    * `flush()`: if the buffer is empty returns `false`; otherwise clears the timer, calls `fn` with the buffered items as a new array,
      empties the buffer and returns `true`. The timer firing is a `flush()`.
    * `size()` is the current number of buffered items.
''')

CLOCK = dd(r'''
    'use strict';

    class FakeClock {
      constructor(start = 0) {
        this.time = start;
        this.timers = [];
        this.seq = 0;
      }

      now() {
        return this.time;
      }

      pending() {
        return this.timers.length;
      }

      setTimeout(fn, delay) {
        this.seq += 1;
        this.timers.push({ id: this.seq, at: this.time + Math.max(0, delay), fn });
        return this.seq;
      }

      clearTimeout(id) {
        this.timers = this.timers.filter((t) => t.id !== id);
      }

      advance(ms) {
        if (ms < 0) throw new RangeError('cannot go back in time');
        const target = this.time + ms;
        for (;;) {
          const due = this.timers.filter((t) => t.at <= target).sort((a, b) => a.at - b.at || a.id - b.id)[0];
          if (due === undefined) break;
          this.timers = this.timers.filter((t) => t !== due);
          this.time = Math.max(this.time, due.at);
          due.fn();
        }
        this.time = target;
      }
    }

    const realClock = { now: () => Date.now(), setTimeout: (fn, ms) => setTimeout(fn, ms), clearTimeout: (id) => clearTimeout(id) };

    module.exports = { FakeClock, realClock };
''')

DEBOUNCE = dd(r'''
    'use strict';

    const { realClock } = require('./clock');

    function debounce(fn, wait, opts = {}, clock = realClock) {
      if (typeof fn !== 'function') throw new TypeError('fn must be a function');
      if (typeof wait !== 'number' || !Number.isFinite(wait) || wait < 0) throw new RangeError('wait must be a number >= 0');
      const leading = opts.leading === true;
      const trailing = opts.trailing !== false;
      const maxWait = opts.maxWait;
      if (maxWait !== undefined && !(maxWait >= wait)) throw new RangeError('maxWait must be >= wait');
      if (!leading && !trailing) throw new TypeError('leading and trailing cannot both be false');

      let timer = null;
      let pendingArgs = null;
      let burstStart = 0;
      let result;

      function fire() {
        timer = null;
        if (trailing && pendingArgs !== null) {
          const args = pendingArgs;
          pendingArgs = null;
          result = fn(...args);
        }
      }

      function debounced(...args) {
        const t = clock.now();
        if (timer === null) {
          burstStart = t;
          if (leading) {
            result = fn(...args);
          } else if (trailing) {
            pendingArgs = args;
          }
        } else {
          clock.clearTimeout(timer);
          if (trailing) pendingArgs = args;
        }
        const delay = maxWait === undefined ? wait : Math.min(wait, burstStart + maxWait - t);
        timer = clock.setTimeout(fire, delay);
        return result;
      }

      debounced.cancel = () => {
        if (timer !== null) clock.clearTimeout(timer);
        timer = null;
        pendingArgs = null;
      };

      debounced.flush = () => {
        if (timer !== null) {
          clock.clearTimeout(timer);
          fire();
        }
        return result;
      };

      debounced.pending = () => timer !== null;
      return debounced;
    }

    function throttle(fn, wait, opts = {}, clock = realClock) {
      return debounce(fn, wait, { leading: opts.leading !== false, trailing: opts.trailing !== false, maxWait: wait }, clock);
    }

    module.exports = { debounce, throttle };
''')

BATCHER = dd(r'''
    'use strict';

    const { realClock } = require('./clock');

    function createBatcher(fn, opts, clock = realClock) {
      const { size, wait } = opts;
      if (!Number.isInteger(size) || size < 1) throw new RangeError('size must be an integer >= 1');
      if (typeof wait !== 'number' || !(wait >= 0)) throw new RangeError('wait must be a number >= 0');
      let buffer = [];
      let timer = null;

      function flush() {
        if (buffer.length === 0) return false;
        if (timer !== null) {
          clock.clearTimeout(timer);
          timer = null;
        }
        const items = buffer;
        buffer = [];
        fn(items.slice());
        return true;
      }

      return {
        add(item) {
          buffer.push(item);
          if (buffer.length === 1) timer = clock.setTimeout(flush, wait);
          if (buffer.length >= size) flush();
        },
        flush,
        size: () => buffer.length,
      };
    }

    module.exports = { createBatcher };
''')

VISIBLE = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { FakeClock } = require('../src/clock');
    const { debounce } = require('../src/debounce');

    test('fake clock advances', () => {
      const clock = new FakeClock();
      let fired = 0;
      clock.setTimeout(() => { fired += 1; }, 10);
      clock.advance(9);
      assert.equal(fired, 0);
      clock.advance(1);
      assert.equal(fired, 1);
    });

    test('debounce calls once after the quiet period', () => {
      const clock = new FakeClock();
      const calls = [];
      const d = debounce((x) => calls.push(x), 100, {}, clock);
      d('a');
      clock.advance(50);
      d('b');
      clock.advance(100);
      assert.deepEqual(calls, ['b']);
    });
''')

HIDDEN = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { FakeClock } = require('../src/clock');
    const { debounce, throttle } = require('../src/debounce');
    const { createBatcher } = require('../src/batcher');

    // a recorder: calls are logged as [clock time, ...args]
    function rec(clock) {
      const log = [];
      const fn = (...args) => {
        log.push([clock.now(), ...args]);
        return args.join('+');
      };
      return { log, fn };
    }

    test('FakeClock: time and ordering', () => {
      const c = new FakeClock(1000);
      assert.equal(c.now(), 1000);
      const seen = [];
      c.setTimeout(() => seen.push(['b', c.now()]), 20);
      c.setTimeout(() => seen.push(['a', c.now()]), 10);
      c.setTimeout(() => seen.push(['c', c.now()]), 20);
      assert.equal(c.pending(), 3);
      c.advance(9);
      assert.deepEqual(seen, []);
      assert.equal(c.now(), 1009);
      c.advance(1);
      assert.deepEqual(seen, [['a', 1010]]);
      c.advance(50);
      assert.deepEqual(seen, [['a', 1010], ['b', 1020], ['c', 1020]]);
      assert.equal(c.now(), 1060);
      assert.equal(c.pending(), 0);
    });

    test('FakeClock: nested timers and zero or negative delays', () => {
      const c = new FakeClock();
      const seen = [];
      c.setTimeout(() => {
        seen.push(['outer', c.now()]);
        c.setTimeout(() => seen.push(['inner', c.now()]), 5);
        c.setTimeout(() => seen.push(['late', c.now()]), 500);
      }, 10);
      c.advance(100);
      assert.deepEqual(seen, [['outer', 10], ['inner', 15]]);
      assert.equal(c.pending(), 1);
      c.setTimeout(() => seen.push(['zero', c.now()]), 0);
      c.setTimeout(() => seen.push(['neg', c.now()]), -50);
      c.advance(0);
      assert.deepEqual(seen.slice(2), [['zero', 100], ['neg', 100]]);
    });

    test('FakeClock: clearTimeout and ids', () => {
      const c = new FakeClock();
      let n = 0;
      const a = c.setTimeout(() => { n += 1; }, 10);
      const b = c.setTimeout(() => { n += 10; }, 10);
      assert.equal(typeof a, 'number');
      assert.notEqual(a, b);
      c.clearTimeout(a);
      c.clearTimeout(12345);
      assert.equal(c.pending(), 1);
      c.advance(10);
      assert.equal(n, 10);
      c.clearTimeout(b);
      assert.equal(c.pending(), 0);
    });

    test('FakeClock: advance rules', () => {
      const c = new FakeClock();
      assert.throws(() => c.advance(-1), RangeError);
      c.advance(0);
      assert.equal(c.now(), 0);
      let hit = 0;
      c.setTimeout(() => { hit += 1; }, 7);
      c.advance(6);
      assert.equal(hit, 0);
      c.advance(1);
      assert.equal(hit, 1);
      c.advance(1000);
      assert.equal(hit, 1);
    });

    test('debounce: trailing call with the last arguments', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const d = debounce(fn, 100, {}, clock);
      d('a', 1);
      clock.advance(50);
      d('b', 2);
      clock.advance(99);
      assert.deepEqual(log, []);
      clock.advance(1);
      assert.deepEqual(log, [[150, 'b', 2]]);
      clock.advance(1000);
      assert.equal(log.length, 1);
    });

    test('debounce: every call restarts the wait', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const d = debounce(fn, 100, {}, clock);
      for (let i = 0; i < 5; i++) {
        d(i);
        clock.advance(99);
      }
      assert.deepEqual(log, []);
      clock.advance(1);
      assert.deepEqual(log, [[496, 4]]);
    });

    test('debounce: a new burst after the timer fired', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const d = debounce(fn, 10, {}, clock);
      d('x');
      clock.advance(10);
      d('y');
      clock.advance(10);
      assert.deepEqual(log, [[10, 'x'], [20, 'y']]);
    });

    test('debounce: leading only', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const d = debounce(fn, 100, { leading: true, trailing: false }, clock);
      d('a');
      assert.deepEqual(log, [[0, 'a']]);
      clock.advance(50);
      d('b');
      clock.advance(99);
      d('c');
      clock.advance(99);
      assert.deepEqual(log, [[0, 'a']]);
      clock.advance(1);
      d('d');
      assert.deepEqual(log, [[0, 'a'], [249, 'd']]);
    });

    test('debounce: leading and trailing', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const d = debounce(fn, 100, { leading: true }, clock);
      d('a');
      clock.advance(10);
      d('b');
      clock.advance(10);
      d('c');
      assert.deepEqual(log, [[0, 'a']]);
      clock.advance(100);
      assert.deepEqual(log, [[0, 'a'], [120, 'c']]);
    });

    test('debounce: a lone call with leading and trailing runs once', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const d = debounce(fn, 100, { leading: true, trailing: true }, clock);
      d('only');
      clock.advance(500);
      assert.deepEqual(log, [[0, 'only']]);
      d('again');
      assert.deepEqual(log, [[0, 'only'], [500, 'again']]);
    });

    test('debounce: return values', () => {
      const clock = new FakeClock();
      const { fn } = rec(clock);
      const d = debounce(fn, 100, { leading: true }, clock);
      assert.equal(d('a', 'b'), 'a+b');
      assert.equal(d('c'), 'a+b');
      clock.advance(100);
      assert.equal(d('x'), 'x');
      const t = debounce(fn, 100, {}, clock);
      assert.equal(t('q'), undefined);
      clock.advance(100);
      assert.equal(t('r'), 'q');
    });

    test('debounce: maxWait caps the delay', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const d = debounce(fn, 100, { maxWait: 250 }, clock);
      for (let t = 0; t <= 200; t += 50) {
        if (t > 0) clock.advance(50);
        d(t);
      }
      assert.deepEqual(log, []);
      clock.advance(49);
      assert.deepEqual(log, []);
      clock.advance(1);
      assert.deepEqual(log, [[250, 200]]);
      assert.equal(d.pending(), false);
    });

    test('debounce: after a maxWait firing the next call starts a fresh burst', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const d = debounce(fn, 100, { maxWait: 150 }, clock);
      for (let t = 0; t <= 400; t += 40) {
        if (t > 0) clock.advance(40);
        d(t);
      }
      clock.advance(100);
      // bursts: calls at 0..120 -> fires at 150 (last call 120); calls 160..280 -> burst start 160, fires at 310 (call 280);
      // calls 320..400 -> burst start 320, fires at 470 (last call 400)
      assert.deepEqual(log, [[150, 120], [310, 280], [470, 400]]);
    });

    test('debounce: maxWait delay never goes negative and equal wait works', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const d = debounce(fn, 100, { maxWait: 100 }, clock);
      d('a');
      clock.advance(60);
      d('b');
      clock.advance(40);
      assert.deepEqual(log, [[100, 'b']]);
    });

    test('debounce: cancel', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const d = debounce(fn, 100, {}, clock);
      d('a');
      assert.equal(d.pending(), true);
      d.cancel();
      assert.equal(d.pending(), false);
      assert.equal(clock.pending(), 0);
      clock.advance(1000);
      assert.deepEqual(log, []);
      d('b');
      clock.advance(100);
      assert.deepEqual(log, [[1100, 'b']]);
      d.cancel();
      d.cancel();
    });

    test('debounce: cancel forgets the pending trailing call of a leading burst', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const d = debounce(fn, 100, { leading: true }, clock);
      d('a');
      d('b');
      d.cancel();
      clock.advance(500);
      assert.deepEqual(log, [[0, 'a']]);
      d('c');
      assert.deepEqual(log, [[0, 'a'], [500, 'c']]);
    });

    test('debounce: flush', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const d = debounce(fn, 100, {}, clock);
      assert.equal(d.flush(), undefined);
      d('a');
      clock.advance(30);
      assert.equal(d.flush(), 'a');
      assert.deepEqual(log, [[30, 'a']]);
      assert.equal(d.pending(), false);
      assert.equal(clock.pending(), 0);
      clock.advance(1000);
      assert.equal(log.length, 1);
      assert.equal(d.flush(), 'a');
      assert.equal(log.length, 1);
    });

    test('debounce: flush without a pending trailing call', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const d = debounce(fn, 100, { leading: true }, clock);
      d('a');
      assert.equal(d.flush(), 'a');
      assert.deepEqual(log, [[0, 'a']]);
      assert.equal(d.pending(), false);
      d('b');
      assert.deepEqual(log, [[0, 'a'], [0, 'b']]);
      const lo = debounce(fn, 100, { leading: true, trailing: false }, clock);
      lo('z');
      d.cancel();
      assert.equal(lo.flush(), 'z');
      assert.equal(log.filter((e) => e[1] === 'z').length, 1);
    });

    test('debounce: pending reflects the timer', () => {
      const clock = new FakeClock();
      const d = debounce(() => 1, 100, {}, clock);
      assert.equal(d.pending(), false);
      d();
      assert.equal(d.pending(), true);
      clock.advance(99);
      assert.equal(d.pending(), true);
      clock.advance(1);
      assert.equal(d.pending(), false);
    });

    test('debounce: zero wait', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const d = debounce(fn, 0, {}, clock);
      d('a');
      d('b');
      assert.deepEqual(log, []);
      clock.advance(0);
      assert.deepEqual(log, [[0, 'b']]);
    });

    test('debounce: validation', () => {
      const clock = new FakeClock();
      assert.throws(() => debounce('x', 10, {}, clock), TypeError);
      assert.throws(() => debounce(() => 1, -1, {}, clock), RangeError);
      assert.throws(() => debounce(() => 1, NaN, {}, clock), RangeError);
      assert.throws(() => debounce(() => 1, Infinity, {}, clock), RangeError);
      assert.throws(() => debounce(() => 1, '10', {}, clock), RangeError);
      assert.throws(() => debounce(() => 1, 100, { maxWait: 99 }, clock), RangeError);
      assert.throws(() => debounce(() => 1, 100, { leading: false, trailing: false }, clock), TypeError);
      assert.doesNotThrow(() => debounce(() => 1, 100, { maxWait: 100 }, clock));
      assert.doesNotThrow(() => debounce(() => 1, 0, {}, clock));
      assert.doesNotThrow(() => debounce(() => 1, 100, { leading: true, trailing: false }, clock));
    });

    test('throttle: leading and trailing by default', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const t = throttle(fn, 100, {}, clock);
      t('a');
      clock.advance(30);
      t('b');
      clock.advance(30);
      t('c');
      assert.deepEqual(log, [[0, 'a']]);
      clock.advance(40);
      assert.deepEqual(log, [[0, 'a'], [100, 'c']]);
      clock.advance(20);
      t('d');
      clock.advance(10);
      t('e');
      assert.deepEqual(log, [[0, 'a'], [100, 'c'], [120, 'd']]);
      clock.advance(100);
      assert.deepEqual(log, [[0, 'a'], [100, 'c'], [120, 'd'], [220, 'e']]);
    });

    test('throttle: a steady stream', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const t = throttle(fn, 100, {}, clock);
      for (let at = 0; at <= 300; at += 10) {
        if (at > 0) clock.advance(10);
        t(at);
      }
      assert.deepEqual(log, [[0, 0], [100, 90], [100, 100], [200, 190], [200, 200], [300, 290], [300, 300]]);
      clock.advance(100);
      assert.equal(log.length, 7);
    });

    test('throttle: without leading the first call waits', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const t = throttle(fn, 100, { leading: false }, clock);
      t('a');
      clock.advance(30);
      t('b');
      assert.deepEqual(log, []);
      clock.advance(70);
      assert.deepEqual(log, [[100, 'b']]);
    });

    test('throttle: without trailing the last call of a window is dropped', () => {
      const clock = new FakeClock();
      const { log, fn } = rec(clock);
      const t = throttle(fn, 100, { trailing: false }, clock);
      t('a');
      clock.advance(40);
      t('b');
      clock.advance(60);
      assert.deepEqual(log, [[0, 'a']]);
      t('c');
      assert.deepEqual(log, [[0, 'a'], [100, 'c']]);
      clock.advance(100);
      assert.equal(log.length, 2);
    });

    test('throttle: validation and a single call', () => {
      const clock = new FakeClock();
      assert.throws(() => throttle(() => 1, 100, { leading: false, trailing: false }, clock), TypeError);
      assert.throws(() => throttle(() => 1, -5, {}, clock), RangeError);
      const { log, fn } = rec(clock);
      const t = throttle(fn, 100, {}, clock);
      t('solo');
      clock.advance(1000);
      assert.deepEqual(log, [[0, 'solo']]);
    });

    test('batcher: flushes at size', () => {
      const clock = new FakeClock();
      const batches = [];
      const b = createBatcher((items) => batches.push([clock.now(), items]), { size: 3, wait: 100 }, clock);
      b.add('a');
      clock.advance(10);
      b.add('b');
      assert.equal(b.size(), 2);
      clock.advance(10);
      b.add('c');
      assert.deepEqual(batches, [[20, ['a', 'b', 'c']]]);
      assert.equal(b.size(), 0);
      assert.equal(clock.pending(), 0);
      clock.advance(500);
      assert.equal(batches.length, 1);
    });

    test('batcher: flushes wait ms after the first item', () => {
      const clock = new FakeClock();
      const batches = [];
      const b = createBatcher((items) => batches.push([clock.now(), items]), { size: 10, wait: 100 }, clock);
      b.add(1);
      clock.advance(60);
      b.add(2);
      clock.advance(39);
      assert.deepEqual(batches, []);
      clock.advance(1);
      assert.deepEqual(batches, [[100, [1, 2]]]);
      clock.advance(1000);
      b.add(3);
      clock.advance(100);
      assert.deepEqual(batches, [[100, [1, 2]], [1200, [3]]]);
    });

    test('batcher: manual flush', () => {
      const clock = new FakeClock();
      const batches = [];
      const b = createBatcher((items) => batches.push(items), { size: 5, wait: 100 }, clock);
      assert.equal(b.flush(), false);
      b.add('x');
      assert.equal(b.flush(), true);
      assert.deepEqual(batches, [['x']]);
      assert.equal(clock.pending(), 0);
      assert.equal(b.flush(), false);
      b.add('y');
      clock.advance(100);
      assert.deepEqual(batches, [['x'], ['y']]);
    });

    test('batcher: size one and zero wait', () => {
      const clock = new FakeClock();
      const batches = [];
      const one = createBatcher((items) => batches.push(items), { size: 1, wait: 100 }, clock);
      one.add('a');
      one.add('b');
      assert.deepEqual(batches, [['a'], ['b']]);
      const zero = createBatcher((items) => batches.push(items), { size: 5, wait: 0 }, clock);
      zero.add('z');
      assert.equal(zero.size(), 1);
      clock.advance(0);
      assert.deepEqual(batches[2], ['z']);
    });

    test('batcher: every flush hands over a fresh array', () => {
      const clock = new FakeClock();
      let got;
      const b = createBatcher((items) => { got = items; items.push('tampered'); }, { size: 2, wait: 100 }, clock);
      b.add(1);
      b.add(2);
      assert.deepEqual(got, [1, 2, 'tampered']);
      b.add(3);
      b.flush();
      assert.deepEqual(got, [3, 'tampered']);
      assert.equal(b.size(), 0);
    });

    test('batcher: validation', () => {
      const clock = new FakeClock();
      assert.throws(() => createBatcher(() => 1, { size: 0, wait: 10 }, clock), RangeError);
      assert.throws(() => createBatcher(() => 1, { size: 1.5, wait: 10 }, clock), RangeError);
      assert.throws(() => createBatcher(() => 1, { size: 2, wait: -1 }, clock), RangeError);
      assert.throws(() => createBatcher(() => 1, { size: 2, wait: '5' }, clock), RangeError);
      assert.doesNotThrow(() => createBatcher(() => 1, { size: 1, wait: 0 }, clock));
    });
''')

LIB = Lib(
    name="calmtimer", lang="javascript", title="the calmtimer helpers",
    blurb="The editor's autosave and search-as-you-type code use calmtimer to debounce, throttle and batch events against a fake clock in tests.",
    files={"package.json": PACKAGE_JSON % "calmtimer", "src/clock.js": CLOCK, "src/debounce.js": DEBOUNCE, "src/batcher.js": BATCHER,
           "README.md": README, ".gitignore": "node_modules/\n"},
    visible_tests={"test/basic.test.js": VISIBLE},
    hidden_tests={"test/full.test.js": HIDDEN},
    mutate=["src/debounce.js", "src/clock.js", "src/batcher.js"], difficulty=4, tags=["timers", "debounce", "throttle"],
    verify=JS_VERIFY,
)

register_libs([LIB], n=8)
