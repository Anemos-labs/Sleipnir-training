"""Mutation during iteration: a session store with expiry hooks (python) and an event bus with re-entrant handlers (js)."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): sessions with a per-user limit, sweeping and revocation.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # sessionstore

    In-memory login sessions for a small web service.

    `SessionStore(ttl=1800, limit=3, on_expire=None)`

    * `create(user, now)` returns a new session id (`s1`, `s2`, ... in creation order, across all users). A user may
      hold at most `limit` sessions: creating one more evicts that user's **oldest** session (by creation).
    * `touch(sid, now)` updates the last-seen time; an unknown id is a `KeyError`. `get(sid)` returns the session or `None`.
    * `sessions_of(user)` lists the user's live session ids, oldest first (a copy; changing it changes nothing).
    * `sweep(now)` removes every session with `now - last_seen >= ttl` and returns the removed ids in creation order. For
      each session it removes it then calls `on_expire(sid)`. The hook may itself change the store (it may
      `create`, `touch` or `revoke_user`): sessions that are already gone when the sweep reaches them are skipped, and
      are not reported in the result or passed to the hook again.
    * `revoke_user(user)` removes all sessions of the user and returns how many there were (0 for an unknown user).
    * The per-user index and the session table always agree: a removed session is never listed by `sessions_of`.
''')

A_STORE = dd('''
    class Session:
        __slots__ = ("sid", "user", "created", "last_seen")

        def __init__(self, sid, user, created):
            self.sid = sid
            self.user = user
            self.created = created
            self.last_seen = created


    class SessionStore:
        def __init__(self, ttl=1800, limit=3, on_expire=None):
            self.ttl = ttl
            self.limit = limit
            self.on_expire = on_expire or (lambda sid: None)
            self._sessions = {}
            self._by_user = {}
            self._counter = 0

        def create(self, user, now):
            self._counter += 1
            sid = f"s{self._counter}"
            mine = self._by_user.setdefault(user, [])
            while len(mine) >= self.limit:
                self._drop(mine[0])
            self._sessions[sid] = Session(sid, user, now)
            mine.append(sid)
            return sid

        def touch(self, sid, now):
            self._sessions[sid].last_seen = now

        def get(self, sid):
            return self._sessions.get(sid)

        def sessions_of(self, user):
            return list(self._by_user.get(user, []))

        def _drop(self, sid):
            session = self._sessions.pop(sid)
            self._by_user[session.user].remove(sid)

        def sweep(self, now):
            expired = sorted((sid for sid, s in self._sessions.items() if now - s.last_seen >= self.ttl), key=lambda sid: int(sid[1:]))
            removed = []
            for sid in expired:
                if sid not in self._sessions:
                    continue
                self._drop(sid)
                removed.append(sid)
                self.on_expire(sid)
            return removed

        def revoke_user(self, user):
            sids = list(self._by_user.get(user, []))
            for sid in sids:
                self._drop(sid)
            return len(sids)
''')

A_VISIBLE = {
    "tests/test_store.py": dd('''
        import unittest

        from sessionstore.store import SessionStore


        class StoreTests(unittest.TestCase):
            def test_create_and_list(self):
                st = SessionStore()
                a = st.create("ann", 0)
                b = st.create("ann", 5)
                self.assertEqual((a, b), ("s1", "s2"))
                self.assertEqual(st.sessions_of("ann"), ["s1", "s2"])

            def test_limit_evicts_the_oldest(self):
                st = SessionStore(limit=2)
                for t in range(3):
                    st.create("ann", t)
                self.assertEqual(st.sessions_of("ann"), ["s2", "s3"])
                self.assertIsNone(st.get("s1"))

            def test_sweep_one(self):
                st = SessionStore(ttl=10)
                st.create("ann", 0)
                st.create("bob", 50)
                self.assertEqual(st.sweep(55), ["s1"])


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_store.py": dd('''
        import unittest

        from sessionstore.store import SessionStore


        class Basics(unittest.TestCase):
            def test_ids_run_across_users(self):
                st = SessionStore()
                self.assertEqual([st.create("a", 0), st.create("b", 0), st.create("a", 1)], ["s1", "s2", "s3"])
                self.assertEqual(st.sessions_of("a"), ["s1", "s3"])
                self.assertEqual(st.sessions_of("nobody"), [])

            def test_sessions_of_is_a_copy(self):
                st = SessionStore()
                st.create("a", 0)
                st.sessions_of("a").clear()
                self.assertEqual(st.sessions_of("a"), ["s1"])

            def test_limit_of_one(self):
                st = SessionStore(limit=1)
                st.create("a", 0)
                second = st.create("a", 1)
                self.assertEqual(st.sessions_of("a"), [second])
                self.assertIsNotNone(st.get(second))

            def test_touch(self):
                st = SessionStore(ttl=10)
                sid = st.create("a", 0)
                st.touch(sid, 8)
                self.assertEqual(st.sweep(17), [])
                self.assertEqual(st.sweep(18), [sid])
                with self.assertRaises(KeyError):
                    st.touch("zzz", 1)


        class Sweeping(unittest.TestCase):
            def test_many_expired_at_once(self):
                st = SessionStore(ttl=10, limit=20)
                ids = [st.create(f"u{i % 3}", i) for i in range(12)]
                st.create("late", 100)
                removed = st.sweep(105)
                self.assertEqual(removed, ids)
                self.assertEqual(st.sessions_of("late"), ["s13"])
                self.assertEqual(st.sessions_of("u0"), [])

            def test_removed_in_creation_order_not_text_order(self):
                st = SessionStore(ttl=1, limit=20)
                ids = [st.create("a", 0) for _ in range(11)]
                self.assertEqual(st.sweep(5), ids)

            def test_boundary(self):
                st = SessionStore(ttl=10)
                sid = st.create("a", 0)
                self.assertEqual(st.sweep(9), [])
                self.assertEqual(st.sweep(10), [sid])

            def test_hook_is_called_once_per_removed_session(self):
                seen = []
                st = SessionStore(ttl=10, on_expire=seen.append)
                st.create("a", 0)
                st.create("a", 1)
                st.create("b", 50)
                st.sweep(30)
                self.assertEqual(seen, ["s1", "s2"])

            def test_index_follows_sweeps(self):
                st = SessionStore(ttl=10, limit=2)
                st.create("a", 0)
                st.create("a", 1)
                st.sweep(30)
                self.assertEqual(st.sessions_of("a"), [])
                st.create("a", 31)
                st.create("a", 32)
                third = st.create("a", 33)
                self.assertEqual(st.sessions_of("a"), ["s4", third])

            def test_hook_that_revokes_the_users_other_sessions(self):
                holder = {}
                seen = []

                def hook(sid):
                    seen.append(sid)
                    holder["st"].revoke_user("a")

                st = SessionStore(ttl=10, on_expire=hook)
                holder["st"] = st
                st.create("a", 0)
                st.create("a", 1)
                st.create("a", 2)
                st.create("b", 3)
                removed = st.sweep(100)
                self.assertEqual(removed, ["s1", "s4"])
                self.assertEqual(seen, ["s1", "s4"])
                self.assertEqual(st.sessions_of("a"), [])
                self.assertEqual(st.sessions_of("b"), [])

            def test_hook_that_creates_sessions(self):
                holder = {}

                def hook(sid):
                    holder["st"].create("new", 100)

                st = SessionStore(ttl=10, limit=5, on_expire=hook)
                holder["st"] = st
                st.create("a", 0)
                st.create("a", 1)
                self.assertEqual(st.sweep(50), ["s1", "s2"])
                self.assertEqual(st.sessions_of("new"), ["s3", "s4"])


        class Revoking(unittest.TestCase):
            def test_revoke_everything_of_a_user(self):
                st = SessionStore(limit=10)
                for i in range(6):
                    st.create("a", i)
                st.create("b", 7)
                self.assertEqual(st.revoke_user("a"), 6)
                self.assertEqual(st.sessions_of("a"), [])
                self.assertEqual(st.sessions_of("b"), ["s7"])
                for n in range(1, 7):
                    self.assertIsNone(st.get(f"s{n}"))

            def test_revoke_unknown_user(self):
                self.assertEqual(SessionStore().revoke_user("nobody"), 0)

            def test_revoke_then_create_again(self):
                st = SessionStore(limit=2)
                st.create("a", 0)
                st.create("a", 1)
                st.revoke_user("a")
                sid = st.create("a", 2)
                self.assertEqual(st.sessions_of("a"), [sid])


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["sweep-dict"] = lambda c: (
        "The hourly session sweep crashed in production after the first time it found more than zero expired sessions:\n\n```\n"
        + "\n".join(c.bad_run("from sessionstore.store import SessionStore\nst = SessionStore(ttl=10)\nst.create('a', 0)\nst.create('b', 50)\nst.sweep(100)\n").splitlines())
        + "\n```\n\nPlease make `sweep` robust."
    )
    p["revoke-live"] = (
        "\"Log out everywhere\" leaves some sessions alive: for a user with 6 sessions only half of them are gone after "
        "`revoke_user`, and the returned count says 6. Support has been telling people to click the button twice."
    )
    p["guard"] = (
        "We added an on_expire hook that revokes the rest of a user's sessions when one of them expires (an expired session "
        "means a stale device). Since then the sweep job dies with a KeyError on users that had several expired sessions. "
        "The README says sessions that are already gone when the sweep reaches them are skipped."
    )
    p["index"] = (
        "Strange eviction crash: after a sweep removes a user's old sessions, creating a new session for the same user fails with a "
        "`KeyError` for an id that no longer exists, and `sessions_of` shows dead ids. Only users who had been swept are affected."
    )
    p["hook-and-revoke"] = (
        "We use an expiry hook that logs a user out everywhere as soon as one of their sessions expires. Two problems since: "
        "some of the user's other sessions survive the hook, and from time to time the sweep job dies with a KeyError. "
        "I can't tell if it is one bug or two; I need the hook scenario to work end to end."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "sessionstore/__init__.py": '"""Session store."""\n', "sessionstore/store.py": A_STORE}
    s = "sessionstore/store.py"
    guard = ("            if sid not in self._sessions:\n                continue\n", "")
    revoke = ("        sids = list(self._by_user.get(user, []))\n        for sid in sids:\n            self._drop(sid)\n        return len(sids)\n",
              "        sids = self._by_user.get(user, [])\n        count = len(sids)\n        for sid in sids:\n            self._drop(sid)\n        return count\n")
    bugs = [
        Bug("sweep-iterates-live-dict", 2, {s: [(
            "        expired = sorted((sid for sid, s in self._sessions.items() if now - s.last_seen >= self.ttl), key=lambda sid: int(sid[1:]))\n        removed = []\n        for sid in expired:\n            if sid not in self._sessions:\n                continue\n            self._drop(sid)\n",
            "        removed = []\n        for sid, s in self._sessions.items():\n            if now - s.last_seen < self.ttl:\n                continue\n            self._drop(sid)\n")]}, P["sweep-dict"]),
        Bug("revoke-iterates-live-list", 3, {s: [revoke]}, P["revoke-live"]),
        Bug("sweep-bypasses-the-index", 3, {s: [("            self._drop(sid)\n            removed.append(sid)\n", "            del self._sessions[sid]\n            removed.append(sid)\n")]}, P["index"]),
        Bug("sweep-without-gone-check", 4, {s: [guard]}, P["guard"]),
        Bug("revoke-live-and-no-gone-check", 5, {s: [revoke, guard]}, P["hook-and-revoke"]),
    ]
    return Base("sessionstore", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (javascript): an event bus whose handlers subscribe, unsubscribe and emit while it is dispatching.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # tinybus

    A synchronous event bus (CommonJS).

    * `bus.on(name, fn)` registers `fn` and returns a function that removes exactly that registration (registering the same
      function twice makes two registrations; removing one leaves the other).
    * `bus.once(name, fn)` is `on` for a handler that runs at most once, **even if** the handler (directly or not) emits the
      same event again, and even if it throws.
    * `bus.emit(name, payload)` calls the handlers of `name` in registration order and returns how many it called.
      * A handler registered during an emit is not called by that emit (only by later ones).
      * A handler removed before its turn in the current emit (by an earlier handler, or by itself) is not called.
      * Every handler that is due runs even if an earlier one threw; afterwards, if any threw, `emit` throws an
        `AggregateError` whose `errors` are the thrown values in order.
''')

B_BUS = dd('''
    'use strict';

    class Bus {
      constructor() {
        this.handlers = new Map(); // name -> [{ fn, active }]
      }

      on(name, fn) {
        const entry = { fn, active: true };
        if (!this.handlers.has(name)) this.handlers.set(name, []);
        this.handlers.get(name).push(entry);
        return () => this.off(name, entry);
      }

      once(name, fn) {
        const off = this.on(name, (payload) => {
          off();
          return fn(payload);
        });
        return off;
      }

      off(name, entry) {
        entry.active = false;
        const list = this.handlers.get(name);
        if (!list) return;
        const i = list.indexOf(entry);
        if (i !== -1) list.splice(i, 1);
      }

      emit(name, payload) {
        const list = this.handlers.get(name);
        if (!list) return 0;
        const snapshot = [...list];
        const errors = [];
        let called = 0;
        for (const entry of snapshot) {
          if (!entry.active) continue;
          called += 1;
          try {
            entry.fn(payload);
          } catch (e) {
            errors.push(e);
          }
        }
        if (errors.length > 0) throw new AggregateError(errors, `${errors.length} handler(s) failed for ${name}`);
        return called;
      }
    }

    module.exports = { Bus };
''')

B_VISIBLE = {
    "test/bus.test.js": dd('''
        const test = require('node:test');
        const assert = require('node:assert');
        const { Bus } = require('../src/bus');

        test('handlers run in order', () => {
          const bus = new Bus();
          const seen = [];
          bus.on('x', () => seen.push(1));
          bus.on('x', () => seen.push(2));
          assert.strictEqual(bus.emit('x'), 2);
          assert.deepStrictEqual(seen, [1, 2]);
        });

        test('off removes a handler', () => {
          const bus = new Bus();
          let n = 0;
          const off = bus.on('x', () => { n += 1; });
          bus.emit('x');
          off();
          bus.emit('x');
          assert.strictEqual(n, 1);
        });

        test('once runs once', () => {
          const bus = new Bus();
          let n = 0;
          bus.once('x', () => { n += 1; });
          bus.emit('x');
          bus.emit('x');
          assert.strictEqual(n, 1);
        });
    '''),
}

B_HIDDEN = {
    "test/hidden_bus.test.js": dd('''
        const test = require('node:test');
        const assert = require('node:assert');
        const { Bus } = require('../src/bus');

        test('a handler that removes itself does not make its neighbour skip', () => {
          const bus = new Bus();
          const seen = [];
          const offA = bus.on('x', () => { seen.push('a'); offA(); });
          bus.on('x', () => seen.push('b'));
          bus.on('x', () => seen.push('c'));
          assert.strictEqual(bus.emit('x'), 3);
          assert.deepStrictEqual(seen, ['a', 'b', 'c']);
          assert.strictEqual(bus.emit('x'), 2);
          assert.deepStrictEqual(seen, ['a', 'b', 'c', 'b', 'c']);
        });

        test('a handler added during an emit waits for the next emit', () => {
          const bus = new Bus();
          const seen = [];
          bus.on('x', () => {
            seen.push('first');
            bus.on('x', () => seen.push('late'));
          });
          assert.strictEqual(bus.emit('x'), 1);
          assert.deepStrictEqual(seen, ['first']);
          assert.strictEqual(bus.emit('x'), 2);
          assert.deepStrictEqual(seen, ['first', 'first', 'late']);
        });

        test('a handler removed before its turn is not called', () => {
          const bus = new Bus();
          const seen = [];
          let offC;
          bus.on('x', () => { seen.push('a'); offC(); });
          bus.on('x', () => seen.push('b'));
          offC = bus.on('x', () => seen.push('c'));
          assert.strictEqual(bus.emit('x'), 2);
          assert.deepStrictEqual(seen, ['a', 'b']);
        });

        test('once is once even when re-entrant', () => {
          const bus = new Bus();
          let n = 0;
          bus.once('x', () => {
            n += 1;
            if (n < 5) bus.emit('x');
          });
          bus.emit('x');
          assert.strictEqual(n, 1);
          assert.strictEqual(bus.emit('x'), 0);
        });

        test('once is removed even if it throws', () => {
          const bus = new Bus();
          let n = 0;
          bus.once('x', () => { n += 1; throw new Error('boom'); });
          assert.throws(() => bus.emit('x'), (e) => e instanceof AggregateError && e.errors.length === 1 && e.errors[0].message === 'boom');
          assert.doesNotThrow(() => bus.emit('x'));
          assert.strictEqual(n, 1);
        });

        test('every due handler runs even if one throws', () => {
          const bus = new Bus();
          const seen = [];
          bus.on('x', () => { seen.push(1); throw new Error('one'); });
          bus.on('x', () => seen.push(2));
          bus.on('x', () => { seen.push(3); throw new TypeError('three'); });
          assert.throws(() => bus.emit('x'), (e) => {
            assert.ok(e instanceof AggregateError);
            assert.deepStrictEqual(e.errors.map((x) => x.message), ['one', 'three']);
            return true;
          });
          assert.deepStrictEqual(seen, [1, 2, 3]);
        });

        test('the same function twice is two registrations', () => {
          const bus = new Bus();
          let n = 0;
          const fn = () => { n += 1; };
          const off1 = bus.on('x', fn);
          bus.on('x', fn);
          assert.strictEqual(bus.emit('x'), 2);
          off1();
          assert.strictEqual(bus.emit('x'), 1);
          off1();
          assert.strictEqual(bus.emit('x'), 1);
          assert.strictEqual(n, 4);
        });

        test('unknown names and payloads', () => {
          const bus = new Bus();
          assert.strictEqual(bus.emit('nobody'), 0);
          let got;
          bus.on('x', (p) => { got = p; });
          bus.emit('x', { a: 1 });
          assert.deepStrictEqual(got, { a: 1 });
        });
    '''),
}


def _b_prompts():
    p = {}
    p["live-list"] = (
        "Odd behaviour in the event bus: a one-shot style handler that unsubscribes itself makes the handler registered "
        "right after it miss that event, and a handler that subscribes another one during an emit sees the new handler fire "
        "immediately. Both look like the dispatch loop works on the wrong list."
    )
    p["removed-still-called"] = (
        "The plugin manager disables a plugin by calling its off() from another plugin's handler. The disabled plugin still "
        "gets that one last event (and does work it should not do). The README says a handler removed before its turn is "
        "not called."
    )
    p["once-late-off"] = (
        "A `once('retry', ...)` handler that triggers the same event again from inside runs repeatedly until the stack is "
        "exhausted (we saw a RangeError in the field). It must run once, whatever it does; the same goes for a one-shot "
        "handler that throws: it keeps getting called on later emits."
    )
    p["errors-stop"] = (
        "One failing subscriber (our metrics exporter throws when the collector is down) prevents every later subscriber from "
        "seeing the event. The contract is: all due handlers run and then the errors are reported together."
    )
    p["off-all"] = (
        "Two components register the same callback function for `tick`. When one of them unsubscribes, the other stops "
        "getting ticks too. Unsubscribing must only remove the registration it was returned for."
    )
    p["two"] = (
        "Two reports about the bus from the plugin team: unsubscribing a handler from inside another handler does not "
        "stop it for the current event, and a `once` handler that re-emits runs more than once. The unit tests we have "
        "do not cover re-entrancy. Please fix the bus."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "src/bus.js": B_BUS, "package.json": '{\n  "name": "tinybus",\n  "version": "1.0.0",\n  "private": true\n}\n'}
    b = "src/bus.js"
    active = ("      if (!entry.active) continue;\n", "")
    once = ("    const off = this.on(name, (payload) => {\n      off();\n      return fn(payload);\n    });\n",
            "    const off = this.on(name, (payload) => {\n      try {\n        return fn(payload);\n      } finally {\n        off();\n      }\n    });\n")
    once = ("    const off = this.on(name, (payload) => {\n      off();\n      return fn(payload);\n    });\n",
            "    const off = this.on(name, (payload) => {\n      const result = fn(payload);\n      off();\n      return result;\n    });\n")
    bugs = [
        Bug("dispatch-over-live-list", 3, {b: [("    const snapshot = [...list];\n", "    const snapshot = list;\n")]}, P["live-list"]),
        Bug("removed-handler-still-called", 3, {b: [active]}, P["removed-still-called"]),
        Bug("first-error-stops-dispatch", 3, {b: [("      try {\n        entry.fn(payload);\n      } catch (e) {\n        errors.push(e);\n      }\n", "      entry.fn(payload);\n")]}, P["errors-stop"]),
        Bug("off-removes-every-copy", 3, {b: [("    return () => this.off(name, entry);\n",
                                               "    return () => {\n      this.handlers.set(name, this.handlers.get(name).filter((e) => e.fn !== fn));\n    };\n")]}, P["off-all"]),
        Bug("once-removed-after-the-call", 4, {b: [once]}, P["once-late-off"]),
        Bug("removal-ignored-and-once-late", 5, {b: [active, once]}, P["two"]),
    ]
    return Base("tinybus", "javascript", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-iter-invalidate", category="fix", lang="python", kind="fix", n=11,
        summary="mutation while iterating: session sweeps and revocation (python), re-entrant event dispatch (javascript)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
