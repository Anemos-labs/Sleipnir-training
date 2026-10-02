"""Retry logic that applies things twice, forgets state or retries what it should not: webhooks (python), batch sending (js)."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): webhook dispatcher with idempotency keys and exponential backoff.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # hooks

    Webhook delivery for an event bus. `hooks.dispatcher.Dispatcher(transport, sleep, max_attempts=4, base_delay=1.0,
    max_delay=8.0)`; `sleep(seconds)` is injected (tests record it instead of waiting).

    `deliver(event)` (an event is `{"id", "url", "payload"}`) calls `transport.send(url, payload, key)`:

    * **Idempotency**: a timeout may happen *after* the receiver processed the request, so every attempt for one event uses the
      **same** key (`key_for(event_id)`); different events have different keys. The receiver ignores keys it has seen.
    * `TransportError` (timeouts, 5xx) is retried, at most `max_attempts` tries in total. After the n-th failed try the dispatcher
      sleeps `min(max_delay, base_delay * 2**(n-1))` seconds, except after the last try: then it raises `GaveUp(attempts)` at
      once, without sleeping.
    * `Permanent` (4xx) is never retried: it propagates after the first try and nothing is slept.
    * An event that was delivered is remembered: delivering the same event id again does not call the transport and returns the
      same `Result`. An event that **failed** (`GaveUp` or `Permanent`) is not remembered: delivering it again tries again.
    * `deliver` returns `Result(attempts=<number of tries it took>)`.
''')

A_DISPATCHER = dd('''
    class TransportError(Exception):
        """Timeout, connection reset or a 5xx answer: worth another try."""


    class Permanent(Exception):
        """A 4xx answer: retrying cannot help."""


    class GaveUp(Exception):
        def __init__(self, attempts):
            super().__init__(f"gave up after {attempts} attempts")
            self.attempts = attempts


    class Result:
        def __init__(self, attempts):
            self.attempts = attempts

        def __repr__(self):
            return f"Result(attempts={self.attempts})"


    class Dispatcher:
        def __init__(self, transport, sleep, max_attempts=4, base_delay=1.0, max_delay=8.0):
            self.transport = transport
            self.sleep = sleep
            self.max_attempts = max_attempts
            self.base_delay = base_delay
            self.max_delay = max_delay
            self._done = {}

        @staticmethod
        def key_for(event_id):
            return f"evt-{event_id}"

        def deliver(self, event):
            event_id = event["id"]
            if event_id in self._done:
                return self._done[event_id]
            key = self.key_for(event_id)
            for attempt in range(1, self.max_attempts + 1):
                try:
                    self.transport.send(event["url"], event["payload"], key)
                except Permanent:
                    raise
                except TransportError:
                    if attempt == self.max_attempts:
                        raise GaveUp(attempt) from None
                    self.sleep(min(self.max_delay, self.base_delay * 2 ** (attempt - 1)))
                    continue
                result = Result(attempt)
                self._done[event_id] = result
                return result
''')

A_FAKES = dd('''
    from .dispatcher import Permanent, TransportError


    class ScriptedTransport:
        """A receiver whose behaviour is scripted: one outcome per call.

        ok             the receiver processes the request and answers
        timeout-after  the receiver processes the request, but the answer is lost (TransportError)
        timeout        the request never arrives (TransportError)
        500            the receiver fails without processing (TransportError)
        400            the receiver refuses the request (Permanent)
        """

        def __init__(self, script):
            self.script = list(script)
            self.calls = []  # (url, key) of every call
            self.applied = {}  # key -> payload, each key is applied at most once

        def send(self, url, payload, key):
            self.calls.append((url, key))
            outcome = self.script.pop(0) if self.script else "ok"
            if outcome in ("ok", "timeout-after"):
                self.applied.setdefault(key, payload)
            if outcome == "timeout-after" or outcome == "timeout" or outcome == "500":
                raise TransportError(outcome)
            if outcome == "400":
                raise Permanent(outcome)
''')

A_VISIBLE = {
    "tests/test_dispatcher.py": dd('''
        import unittest

        from hooks.dispatcher import Dispatcher
        from hooks.fakes import ScriptedTransport


        def event(i="1"):
            return {"id": i, "url": "https://example.test/hook", "payload": {"n": i}}


        class DispatcherTests(unittest.TestCase):
            def test_plain_delivery(self):
                t = ScriptedTransport([])
                d = Dispatcher(t, sleep=lambda s: None)
                self.assertEqual(d.deliver(event()).attempts, 1)
                self.assertEqual(len(t.calls), 1)

            def test_retry_after_a_5xx(self):
                t = ScriptedTransport(["500", "ok"])
                waits = []
                d = Dispatcher(t, sleep=waits.append)
                self.assertEqual(d.deliver(event()).attempts, 2)
                self.assertEqual(waits, [1.0])


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_dispatcher.py": dd('''
        import unittest

        from hooks.dispatcher import Dispatcher, GaveUp, Permanent
        from hooks.fakes import ScriptedTransport


        def event(i="1", url="https://example.test/hook"):
            return {"id": i, "url": url, "payload": {"n": i}}


        def make(script, **kw):
            waits = []
            t = ScriptedTransport(script)
            return Dispatcher(t, sleep=waits.append, **kw), t, waits


        class Idempotency(unittest.TestCase):
            def test_a_lost_answer_does_not_deliver_twice(self):
                d, t, waits = make(["timeout-after", "ok"])
                self.assertEqual(d.deliver(event("a")).attempts, 2)
                self.assertEqual(len(t.calls), 2)
                self.assertEqual(len(set(key for _, key in t.calls)), 1)
                self.assertEqual(len(t.applied), 1)

            def test_the_same_key_is_used_by_every_attempt(self):
                d, t, _ = make(["500", "timeout", "timeout-after", "ok"], max_attempts=5)
                d.deliver(event("x"))
                self.assertEqual({key for _, key in t.calls}, {d.key_for("x")})
                self.assertEqual(len(t.applied), 1)

            def test_different_events_have_different_keys(self):
                d, t, _ = make([])
                d.deliver(event("a"))
                d.deliver(event("b"))
                self.assertEqual(len({key for _, key in t.calls}), 2)
                self.assertEqual(len(t.applied), 2)


        class Backoff(unittest.TestCase):
            def test_doubling_delays(self):
                d, t, waits = make(["500", "500", "500", "ok"], max_attempts=5)
                self.assertEqual(d.deliver(event()).attempts, 4)
                self.assertEqual(waits, [1.0, 2.0, 4.0])

            def test_delay_is_capped(self):
                d, t, waits = make(["500"] * 5 + ["ok"], max_attempts=6, base_delay=1.0, max_delay=4.0)
                d.deliver(event())
                self.assertEqual(waits, [1.0, 2.0, 4.0, 4.0, 4.0])

            def test_custom_base(self):
                d, t, waits = make(["500", "500", "ok"], base_delay=0.5)
                d.deliver(event())
                self.assertEqual(waits, [0.5, 1.0])

            def test_no_sleep_after_the_last_failure(self):
                d, t, waits = make(["500"] * 4)
                with self.assertRaises(GaveUp) as cm:
                    d.deliver(event())
                self.assertEqual(cm.exception.attempts, 4)
                self.assertEqual(len(t.calls), 4)
                self.assertEqual(waits, [1.0, 2.0, 4.0])

            def test_single_attempt(self):
                d, t, waits = make(["500", "ok"], max_attempts=1)
                with self.assertRaises(GaveUp) as cm:
                    d.deliver(event())
                self.assertEqual((cm.exception.attempts, len(t.calls), waits), (1, 1, []))


        class Permanence(unittest.TestCase):
            def test_a_4xx_is_not_retried(self):
                d, t, waits = make(["400", "ok"])
                with self.assertRaises(Permanent):
                    d.deliver(event())
                self.assertEqual((len(t.calls), waits), (1, []))

            def test_a_4xx_after_a_5xx_stops_there(self):
                d, t, waits = make(["500", "400", "ok"])
                with self.assertRaises(Permanent):
                    d.deliver(event())
                self.assertEqual((len(t.calls), waits), (2, [1.0]))


        class Memory(unittest.TestCase):
            def test_a_delivered_event_is_not_sent_again(self):
                d, t, waits = make(["500", "ok"])
                first = d.deliver(event("e"))
                again = d.deliver(event("e"))
                self.assertIs(first, again)
                self.assertEqual(len(t.calls), 2)

            def test_a_failed_event_is_tried_again_on_redelivery(self):
                d, t, waits = make(["500"] * 4 + ["ok"])
                with self.assertRaises(GaveUp):
                    d.deliver(event("e"))
                self.assertEqual(d.deliver(event("e")).attempts, 1)
                self.assertEqual(len(t.calls), 5)
                self.assertEqual(len(t.applied), 1)

            def test_a_permanently_refused_event_is_tried_again_too(self):
                d, t, waits = make(["400", "ok"])
                with self.assertRaises(Permanent):
                    d.deliver(event("e"))
                self.assertEqual(d.deliver(event("e")).attempts, 1)


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["new-key"] = (
        "Customers of the webhook feature report that they received the same order event twice. Their logs show two requests "
        "with *different* idempotency keys, one of which had timed out on our side after their server had already "
        "processed it. Retries must reuse the key of the event."
    )
    p["permanent"] = lambda c: (
        "A customer's endpoint answers 410 Gone and we keep hammering it: with a 400-class answer the dispatcher still retries "
        "and sleeps. For `[\"400\", \"ok\"]` the transport saw "
        + c.probe("from hooks.dispatcher import Dispatcher, Permanent\nfrom hooks.fakes import ScriptedTransport\n"
                  "t = ScriptedTransport(['400', 'ok'])\ntry:\n    Dispatcher(t, sleep=lambda s: None).deliver({'id': '1', 'url': 'u', 'payload': {}})\n"
                  "except Permanent:\n    pass\nprint(len(t.calls))\n")[1]
        + " calls; the README says a 4xx is never retried."
    )
    p["last-sleep"] = (
        "When an endpoint is down the delivery worker holds its slot for 8 more seconds after the last failed try before reporting "
        "that it gave up (it sleeps and then raises). The final failure must be reported at once; waiting is for retries only."
    )
    p["no-cap"] = (
        "Exponential backoff has no ceiling: with `max_attempts=8` the worker sleeps 64 seconds before the last try although `max_delay` "
        "is 8. Please apply the cap."
    )
    p["done-early"] = (
        "Lost events: when a customer's endpoint was down for the whole retry budget, the event was reported as failed (GaveUp), and "
        "when our queue redelivered it later (as designed) the dispatcher answered immediately with an empty success and never "
        "sent it. Only events that were actually delivered may be remembered."
    )
    p["two"] = (
        "Two webhook complaints that may or may not be related: (1) duplicate deliveries after timeouts, (2) events lost for good after "
        "an outage because the redelivery from the queue is swallowed. The visible tests pass. Please fix everything that is "
        "wrong in the dispatcher."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "hooks/__init__.py": '"""Webhook delivery."""\n', "hooks/dispatcher.py": A_DISPATCHER, "hooks/fakes.py": A_FAKES}
    d = "hooks/dispatcher.py"
    newkey = ('                self.transport.send(event["url"], event["payload"], key)\n', '                self.transport.send(event["url"], event["payload"], f"{key}-{attempt}")\n')
    early = ("        key = self.key_for(event_id)\n", "        key = self.key_for(event_id)\n        self._done[event_id] = Result(0)\n")
    bugs = [
        Bug("retry-with-a-new-key", 3, {d: [newkey]}, P["new-key"]),
        Bug("permanent-errors-retried", 2, {d: [("            except Permanent:\n                raise\n            except TransportError:\n", "            except (TransportError, Permanent):\n")]}, P["permanent"]),
        Bug("sleeps-after-the-last-try", 1, {d: [("                if attempt == self.max_attempts:\n                    raise GaveUp(attempt) from None\n                self.sleep(min(self.max_delay, self.base_delay * 2 ** (attempt - 1)))\n",
                                                  "                self.sleep(min(self.max_delay, self.base_delay * 2 ** (attempt - 1)))\n                if attempt == self.max_attempts:\n                    raise GaveUp(attempt) from None\n")]}, P["last-sleep"]),
        Bug("backoff-without-cap", 1, {d: [("self.sleep(min(self.max_delay, self.base_delay * 2 ** (attempt - 1)))", "self.sleep(self.base_delay * 2 ** (attempt - 1))")]}, P["no-cap"]),
        Bug("event-remembered-before-delivery", 3, {d: [early]}, P["done-early"]),
        Bug("new-key-and-early-memory", 5, {d: [newkey, early]}, P["two"]),
    ]
    return Base("hooks", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (javascript): sending a batch with per-item retries.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # batchsend

    Sends a batch of items one by one through a flaky `send(item)` function (CommonJS).

    `sendAll(items, send, { attempts = 3 })` returns `{ sent, calls }`:

    * Items are sent in order. Each item has **its own** budget of `attempts` tries; a `TransientError` thrown by `send` uses one up
      and the same item is tried again. When an item succeeds, the next one starts with a fresh budget.
    * An item that was sent is **never sent again**, whatever happens to later items.
    * Items with the same `id` as an earlier item of the batch are skipped (sent once; the first occurrence wins).
    * Any error that is not a `TransientError` is not retried: it propagates at once.
    * When an item uses up its attempts, `sendAll` throws a `GaveUp` with `sent` (how many items had been sent), `failedAt` (index
      of the item in `items`) and `cause` (the last `TransientError`); later items are not attempted.
    * `sent` counts the items sent; `calls` counts every call of `send`.
''')

B_BATCH = dd('''
    'use strict';

    class TransientError extends Error {}

    class GaveUp extends Error {
      constructor(sent, failedAt, cause) {
        super(`gave up on item ${failedAt} after ${sent} sent`);
        this.sent = sent;
        this.failedAt = failedAt;
        this.cause = cause;
      }
    }

    function sendAll(items, send, { attempts = 3 } = {}) {
      const seen = new Set();
      let sent = 0;
      let calls = 0;
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (seen.has(item.id)) continue;
        for (let attempt = 1; attempt <= attempts; attempt++) {
          calls += 1;
          try {
            send(item);
            break;
          } catch (e) {
            if (!(e instanceof TransientError)) throw e;
            if (attempt === attempts) throw new GaveUp(sent, i, e);
          }
        }
        seen.add(item.id);
        sent += 1;
      }
      return { sent, calls };
    }

    module.exports = { sendAll, TransientError, GaveUp };
''')

B_RESTART = dd('''
    'use strict';

    class TransientError extends Error {}

    class GaveUp extends Error {
      constructor(sent, failedAt, cause) {
        super(`gave up on item ${failedAt} after ${sent} sent`);
        this.sent = sent;
        this.failedAt = failedAt;
        this.cause = cause;
      }
    }

    function sendAll(items, send, { attempts = 3 } = {}) {
      let calls = 0;
      for (let attempt = 1; attempt <= attempts; attempt++) {
        const seen = new Set();
        let sent = 0;
        let failedAt = -1;
        let failure = null;
        for (let i = 0; i < items.length; i++) {
          const item = items[i];
          if (seen.has(item.id)) continue;
          calls += 1;
          try {
            send(item);
          } catch (e) {
            if (!(e instanceof TransientError)) throw e;
            failedAt = i;
            failure = e;
            break;
          }
          seen.add(item.id);
          sent += 1;
        }
        if (failure === null) return { sent, calls };
        if (attempt === attempts) throw new GaveUp(sent, failedAt, failure);
      }
      return { sent: 0, calls };
    }

    module.exports = { sendAll, TransientError, GaveUp };
''')

B_VISIBLE = {
    "test/batch.test.js": dd('''
        const test = require('node:test');
        const assert = require('node:assert');
        const { sendAll, TransientError } = require('../src/batch');

        test('sends everything in order', () => {
          const log = [];
          const r = sendAll([{ id: 'a' }, { id: 'b' }], (it) => log.push(it.id));
          assert.deepStrictEqual(log, ['a', 'b']);
          assert.deepStrictEqual(r, { sent: 2, calls: 2 });
        });

        test('retries a transient failure', () => {
          let n = 0;
          const r = sendAll([{ id: 'a' }], () => {
            n += 1;
            if (n < 2) throw new TransientError('flaky');
          });
          assert.deepStrictEqual(r, { sent: 1, calls: 2 });
        });
    '''),
}

B_HIDDEN = {
    "test/hidden_batch.test.js": dd('''
        const test = require('node:test');
        const assert = require('node:assert');
        const { sendAll, TransientError, GaveUp } = require('../src/batch');

        // failures: { id: number of calls that fail before the item goes through }
        function flaky(failures) {
          const left = { ...failures };
          const log = [];
          const send = (item) => {
            if (left[item.id] > 0) {
              left[item.id] -= 1;
              throw new TransientError(`flaky ${item.id}`);
            }
            log.push(item.id);
          };
          return { send, log };
        }
        const ids = (...xs) => xs.map((id) => ({ id }));

        test('items before a failing item are not sent again', () => {
          const { send, log } = flaky({ c: 2 });
          const r = sendAll(ids('a', 'b', 'c', 'd'), send);
          assert.deepStrictEqual(log, ['a', 'b', 'c', 'd']);
          assert.deepStrictEqual(r, { sent: 4, calls: 6 });
        });

        test('every item has its own budget', () => {
          const { send, log } = flaky({ a: 2, b: 2, c: 2 });
          const r = sendAll(ids('a', 'b', 'c'), send, { attempts: 3 });
          assert.deepStrictEqual(log, ['a', 'b', 'c']);
          assert.deepStrictEqual(r, { sent: 3, calls: 9 });
        });

        test('giving up reports how far it got', () => {
          const { send, log } = flaky({ c: 99 });
          let err;
          try {
            sendAll(ids('a', 'b', 'c', 'd'), send, { attempts: 3 });
          } catch (e) {
            err = e;
          }
          assert.ok(err instanceof GaveUp);
          assert.strictEqual(err.sent, 2);
          assert.strictEqual(err.failedAt, 2);
          assert.ok(err.cause instanceof TransientError);
          assert.strictEqual(err.cause.message, 'flaky c');
          assert.deepStrictEqual(log, ['a', 'b']);
        });

        test('the failing item is tried exactly `attempts` times', () => {
          let calls = 0;
          assert.throws(() => sendAll(ids('x'), () => { calls += 1; throw new TransientError('no'); }, { attempts: 4 }), GaveUp);
          assert.strictEqual(calls, 4);
          calls = 0;
          assert.throws(() => sendAll(ids('x'), () => { calls += 1; throw new TransientError('no'); }, { attempts: 1 }), GaveUp);
          assert.strictEqual(calls, 1);
        });

        test('other errors are not retried', () => {
          let calls = 0;
          const send = () => { calls += 1; throw new TypeError('bad item'); };
          assert.throws(() => sendAll(ids('a', 'b'), send), TypeError);
          assert.strictEqual(calls, 1);
        });

        test('a later non-transient error does not repeat earlier items', () => {
          const log = [];
          const send = (item) => {
            if (item.id === 'b') throw new RangeError('boom');
            log.push(item.id);
          };
          assert.throws(() => sendAll(ids('a', 'b', 'c'), send), RangeError);
          assert.deepStrictEqual(log, ['a']);
        });

        test('duplicate ids are sent once, first occurrence wins', () => {
          const { send, log } = flaky({});
          const items = [{ id: 'a', v: 1 }, { id: 'b', v: 1 }, { id: 'a', v: 2 }, { id: 'c', v: 1 }, { id: 'b', v: 3 }];
          const sentItems = [];
          const r = sendAll(items, (it) => { send(it); sentItems.push(it.v); });
          assert.deepStrictEqual(log, ['a', 'b', 'c']);
          assert.deepStrictEqual(sentItems, [1, 1, 1]);
          assert.deepStrictEqual(r, { sent: 3, calls: 3 });
        });

        test('empty batch and a failing duplicate', () => {
          assert.deepStrictEqual(sendAll([], () => { throw new Error('never'); }), { sent: 0, calls: 0 });
          const { send, log } = flaky({ a: 1 });
          const r = sendAll(ids('a', 'a', 'b'), send);
          assert.deepStrictEqual(log, ['a', 'b']);
          assert.deepStrictEqual(r, { sent: 2, calls: 3 });
        });
    '''),
}


def _b_prompts():
    p = {}
    p["restart"] = (
        "Customers received the first rows of an export several times: when row 40 of a 100 row batch hits a transient error the sender "
        "starts over from row 1, so rows 1-39 are delivered again (and again, if row 40 keeps failing). Only the failing row "
        "should be retried. Please fix `sendAll`."
    )
    p["budget"] = (
        "A batch of ten rows fails halfway although every single row would have gone through after one retry: the retry budget "
        "seems to be shared by the whole batch instead of being per row (`attempts` is documented per item)."
    )
    p["permanent"] = (
        "A malformed row throws a `TypeError` in `send` and instead of failing fast the batch sender calls it three more times "
        "and wraps the failure as `GaveUp`, hiding the real problem. Only `TransientError` should be retried."
    )
    p["gave-up-count"] = (
        "The `GaveUp` error always says `sent: 0`, so the support tool tells people that nothing was delivered when most of the batch had "
        "been. The count of rows sent before the failing one must be reported."
    )
    p["dupes"] = (
        "The same row id appearing twice in an upload is delivered twice. The README says repeated ids are sent once and the first "
        "occurrence wins."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "src/batch.js": B_BATCH, "package.json": '{\n  "name": "batchsend",\n  "version": "1.0.0",\n  "private": true\n}\n'}
    b = "src/batch.js"
    budget = [("  let calls = 0;\n", "  let calls = 0;\n  let failures = 0;\n"),
              ("        if (attempt === attempts) throw new GaveUp(sent, i, e);\n", "        failures += 1;\n        if (failures >= attempts) throw new GaveUp(sent, i, e);\n")]
    bugs = [
        Bug("failure-restarts-the-batch", 3, {b: B_RESTART}, P["restart"]),
        Bug("attempt-budget-shared", 3, {b: budget}, P["budget"]),
        Bug("any-error-is-retried", 1, {b: [("        if (!(e instanceof TransientError)) throw e;\n", "")]}, P["permanent"]),
        Bug("giving-up-reports-zero-sent", 2, {b: [("throw new GaveUp(sent, i, e)", "throw new GaveUp(0, i, e)")]}, P["gave-up-count"]),
        Bug("duplicates-are-resent", 2, {b: [("    if (seen.has(item.id)) continue;\n", "")]}, P["dupes"]),
    ]
    return Base("batchsend", "javascript", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-retry-twice", category="fix", lang="python", kind="fix", n=11,
        summary="retry logic: changing idempotency keys, premature memory, wrong backoff, resending sent items (python webhooks, js batch sender)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
