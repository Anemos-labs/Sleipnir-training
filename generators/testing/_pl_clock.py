"""Python libraries whose behaviour depends on the clock: a TTL cache, a token-bucket limiter, a session store, a circuit breaker.

Each library comes with the reference source (it takes a ``clock`` keyword), a *legacy* variant that calls ``time.monotonic()`` directly,
the "sleepy" test suite a previous maintainer wrote (real sleeps), and a gold suite driven by a fake clock.
"""
from __future__ import annotations

from fx import dd

from ._engine import TLib

WHERE_PY = ("Put your tests in `tests/` (plain `unittest`; there is no pytest here). They are run from the repository root with "
            "`python3 -m unittest discover -s tests -t .`.")
CMD = "python3 -m unittest discover -s tests -t ."
INIT = "\n"


def legacy_source(src: str) -> str:
    """The same module before the clock became injectable: no parameter, `time.monotonic()` called inline."""
    out = src.replace(", clock=time.monotonic", "").replace("        self._clock = clock\n", "").replace("self._clock()", "time.monotonic()")
    assert out != src and "clock" not in out.replace("time.monotonic", ""), "legacy transformation left a clock behind"
    return out


def clock_para(cls: str) -> str:
    return dd(f'''
        ## Time
        `{cls}` reads the time only through the keyword argument `clock` of its constructor: a callable without arguments that returns the current time in seconds as a float.
        The default is `time.monotonic`.
    ''')


def _lib(name, pkg, cls, mod, title, blurb, readme, src, gold, sleepy, api, focus, difficulty, smoke_expr):
    smoke = dd(f'''
        import unittest

        from {pkg}.{mod} import {cls}


        class SmokeTests(unittest.TestCase):
            def test_imports(self):
                self.assertTrue({smoke_expr})
    ''')
    path = f"{pkg}/{mod}.py"
    files = {"README.md": readme + "\n" + clock_para(cls), f"{pkg}/__init__.py": INIT, path: src, "tests/__init__.py": INIT}
    legacy = legacy_source(src)
    return TLib(
        name=name, lang="python", title=title, blurb=blurb, files=files, stub={"tests/test_smoke.py": smoke}, gold={"tests/test_" + mod + ".py": gold},
        mutate=[path], cmd=CMD, where=WHERE_PY, difficulty=difficulty, timeout=30, focus=focus, strip_keep={},
        extra={"legacy": {path: legacy}, "readme_plain": readme, "sleepy": {"tests/test_" + mod + ".py": sleepy}, "api": api, "cls": cls, "pkg": pkg, "mod": mod},
    )


# ---------------------------------------------------------------------------------------------------------------------
# TTL cache
# ---------------------------------------------------------------------------------------------------------------------

CACHE_README = dd('''
    # ttlcache

    An in-process cache whose entries expire: `ttlcache.cache.TTLCache`.

    ## Construction
    `TTLCache(ttl, maxsize=128, sliding=False)`. `ttl` is the default lifetime of an entry in seconds (any positive number, otherwise `ValueError`); `maxsize` is at least 1
    (otherwise `ValueError`).

    ## Methods
    * `set(key, value, ttl=None)` stores a value. `ttl` overrides the default lifetime for this entry (it must be positive, otherwise `ValueError`).
      Storing an existing key replaces the value, restarts its lifetime and makes it the most recently used entry. Expired entries are dropped first;
      if the cache is still full, the least recently used entry (the one stored or read longest ago) is evicted to make room.
    * `get(key, default=None)` returns the value, or `default` for a missing or expired key. An entry is alive while `now < stored_at + ttl`: at exactly `ttl` seconds it is
      already expired. A successful `get` makes the entry the most recently used one; with `sliding=True` it also restarts the lifetime (with the entry's own ttl).
    * `remaining(key)` is the number of seconds an entry has left (a float), `None` for a missing or expired key.
    * `len(cache)` is the number of live entries and `key in cache` is true for live entries only.

    `remaining`, `len` and `in` never change the recency or the lifetime of an entry.
''')

CACHE_SRC = dd('''
    """A small in-process cache whose entries expire."""
    import time


    class TTLCache:
        def __init__(self, ttl, maxsize=128, sliding=False, clock=time.monotonic):
            if ttl <= 0:
                raise ValueError("ttl must be positive")
            if maxsize < 1:
                raise ValueError("maxsize must be at least 1")
            self._ttl = ttl
            self._maxsize = maxsize
            self._sliding = sliding
            self._clock = clock
            self._items = {}

        def _purge(self, now):
            dead = [k for k, e in self._items.items() if e[1] <= now]
            for k in dead:
                del self._items[k]

        def set(self, key, value, ttl=None):
            life = self._ttl if ttl is None else ttl
            if life <= 0:
                raise ValueError("ttl must be positive")
            now = self._clock()
            self._purge(now)
            if key in self._items:
                del self._items[key]
            elif len(self._items) >= self._maxsize:
                oldest = next(iter(self._items))
                del self._items[oldest]
            self._items[key] = [value, now + life, life]

        def get(self, key, default=None):
            now = self._clock()
            entry = self._items.get(key)
            if entry is None:
                return default
            if entry[1] <= now:
                del self._items[key]
                return default
            if self._sliding:
                entry[1] = now + entry[2]
            del self._items[key]
            self._items[key] = entry
            return entry[0]

        def remaining(self, key):
            entry = self._items.get(key)
            if entry is None:
                return None
            left = entry[1] - self._clock()
            if left <= 0:
                return None
            return left

        def __len__(self):
            self._purge(self._clock())
            return len(self._items)

        def __contains__(self, key):
            entry = self._items.get(key)
            return entry is not None and entry[1] > self._clock()
''')

FAKE_CLOCK = dd('''
    class Clock:
        """A clock that only moves when the test says so."""

        def __init__(self, now=1000.0):
            self.now = now

        def __call__(self):
            return self.now

        def advance(self, seconds):
            self.now += seconds
''')

CACHE_GOLD = dd('''
    import unittest

    from ttlcache.cache import TTLCache


''') + FAKE_CLOCK + "\n\n" + dd('''
    class TTLCacheTests(unittest.TestCase):
        def setUp(self):
            self.clock = Clock()

        def make(self, ttl=10, **kw):
            return TTLCache(ttl, clock=self.clock, **kw)

        def test_entry_lives_until_exactly_ttl(self):
            c = self.make(ttl=10)
            c.set("a", 1)
            self.clock.advance(9.5)
            self.assertEqual(c.get("a"), 1)
            self.clock.advance(0.5)
            self.assertIsNone(c.get("a"))

        def test_default_for_missing_and_expired(self):
            c = self.make()
            self.assertEqual(c.get("nope", "dflt"), "dflt")
            self.assertIsNone(c.get("nope"))
            c.set("a", 1)
            self.clock.advance(10)
            self.assertEqual(c.get("a", "dflt"), "dflt")

        def test_per_entry_ttl(self):
            c = self.make(ttl=10)
            c.set("short", 1, ttl=2)
            c.set("long", 2, ttl=30)
            self.clock.advance(5)
            self.assertIsNone(c.get("short"))
            self.assertEqual(c.get("long"), 2)
            self.clock.advance(25)
            self.assertIsNone(c.get("long"))

        def test_set_restarts_the_lifetime_and_replaces_the_value(self):
            c = self.make(ttl=10)
            c.set("a", 1)
            self.clock.advance(8)
            c.set("a", 2)
            self.clock.advance(8)
            self.assertEqual(c.get("a"), 2)
            self.clock.advance(2)
            self.assertIsNone(c.get("a"))

        def test_plain_get_does_not_extend_the_life(self):
            c = self.make(ttl=10)
            c.set("a", 1)
            self.clock.advance(6)
            self.assertEqual(c.get("a"), 1)
            self.clock.advance(4)
            self.assertIsNone(c.get("a"))

        def test_sliding_get_restarts_with_the_entrys_own_ttl(self):
            c = self.make(ttl=10, sliding=True)
            c.set("a", 1)
            c.set("b", 2, ttl=4)
            self.clock.advance(3)
            self.assertEqual(c.get("b"), 2)
            self.clock.advance(3)
            self.assertEqual(c.get("a"), 1)
            self.clock.advance(3.5)
            self.assertIsNone(c.get("b"))
            self.assertEqual(c.get("a"), 1)
            self.clock.advance(9)
            self.assertEqual(c.get("a"), 1)
            self.clock.advance(10)
            self.assertIsNone(c.get("a"))

        def test_sliding_does_not_resurrect_expired_entries(self):
            c = self.make(ttl=10, sliding=True)
            c.set("a", 1)
            self.clock.advance(10)
            self.assertIsNone(c.get("a"))
            self.assertNotIn("a", c)

        def test_remaining(self):
            c = self.make(ttl=10, sliding=True)
            self.assertIsNone(c.remaining("a"))
            c.set("a", 1)
            self.assertEqual(c.remaining("a"), 10)
            self.clock.advance(2.5)
            self.assertEqual(c.remaining("a"), 7.5)
            self.assertEqual(c.remaining("a"), 7.5)
            self.assertEqual(c.get("a"), 1)
            self.assertEqual(c.remaining("a"), 10)
            self.clock.advance(10)
            self.assertIsNone(c.remaining("a"))

        def test_len_and_contains_count_live_entries_only(self):
            c = self.make(ttl=10)
            c.set("a", 1, ttl=2)
            c.set("b", 2)
            c.set("c", 3, ttl=5)
            self.assertEqual(len(c), 3)
            self.assertIn("a", c)
            self.clock.advance(2)
            self.assertNotIn("a", c)
            self.assertIn("b", c)
            self.assertEqual(len(c), 2)
            self.clock.advance(3)
            self.assertEqual(len(c), 1)
            self.assertNotIn("c", c)
            self.clock.advance(5)
            self.assertEqual(len(c), 0)

        def test_stored_none_is_a_value(self):
            c = self.make()
            c.set("a", None)
            self.assertIn("a", c)
            self.assertEqual(c.get("a", "dflt"), None)

        def test_least_recently_used_goes_first(self):
            c = self.make(maxsize=2)
            c.set("a", 1)
            c.set("b", 2)
            c.set("c", 3)
            self.assertNotIn("a", c)
            self.assertIn("b", c)
            self.assertIn("c", c)
            self.assertEqual(len(c), 2)

        def test_get_and_set_count_as_use(self):
            c = self.make(maxsize=2)
            c.set("a", 1)
            c.set("b", 2)
            self.assertEqual(c.get("a"), 1)
            c.set("c", 3)
            self.assertNotIn("b", c)
            self.assertIn("a", c)
            c.set("a", 10)
            c.set("d", 4)
            self.assertNotIn("c", c)
            self.assertEqual(c.get("a"), 10)

        def test_replacing_a_key_never_evicts(self):
            c = self.make(maxsize=2)
            c.set("a", 1)
            c.set("b", 2)
            c.set("b", 3)
            self.assertEqual(len(c), 2)
            self.assertEqual(c.get("a"), 1)
            self.assertEqual(c.get("b"), 3)

        def test_contains_and_len_do_not_count_as_use(self):
            c = self.make(maxsize=2)
            c.set("a", 1)
            c.set("b", 2)
            self.assertIn("a", c)
            self.assertEqual(len(c), 2)
            c.remaining("a")
            c.set("c", 3)
            self.assertNotIn("a", c)
            self.assertIn("b", c)

        def test_expired_entries_are_dropped_before_live_ones_are_evicted(self):
            c = self.make(maxsize=2)
            c.set("old", 1, ttl=1)
            c.set("live", 2, ttl=100)
            self.clock.advance(5)
            self.assertEqual(c.get("live"), 2)
            c.set("new", 3)
            self.assertIn("live", c)
            self.assertIn("new", c)

        def test_validation(self):
            with self.assertRaises(ValueError):
                TTLCache(0)
            with self.assertRaises(ValueError):
                TTLCache(-1)
            with self.assertRaises(ValueError):
                TTLCache(5, maxsize=0)
            c = self.make()
            with self.assertRaises(ValueError):
                c.set("a", 1, ttl=0)
            with self.assertRaises(ValueError):
                c.set("a", 1, ttl=-3)
            self.assertNotIn("a", c)
            TTLCache(0.5, maxsize=1)
''')

CACHE_SLEEPY = dd('''
    import time
    import unittest

    from ttlcache.cache import TTLCache


    class SlowCacheTests(unittest.TestCase):
        def test_entry_expires(self):
            c = TTLCache(0.3)
            c.set("a", 1)
            self.assertEqual(c.get("a"), 1)
            time.sleep(0.4)
            self.assertIsNone(c.get("a"))

        def test_entry_survives_a_little_while(self):
            c = TTLCache(1.0)
            c.set("a", 1)
            time.sleep(0.5)
            self.assertEqual(c.get("a"), 1)

        def test_sliding(self):
            c = TTLCache(0.5, sliding=True)
            c.set("a", 1)
            for _ in range(3):
                time.sleep(0.3)
                self.assertEqual(c.get("a"), 1)
            time.sleep(0.6)
            self.assertIsNone(c.get("a"))

        def test_per_entry_ttl(self):
            c = TTLCache(5)
            c.set("short", 1, ttl=0.2)
            c.set("long", 2)
            time.sleep(0.3)
            self.assertIsNone(c.get("short"))
            self.assertEqual(c.get("long"), 2)

        def test_eviction(self):
            c = TTLCache(5, maxsize=2)
            c.set("a", 1)
            c.set("b", 2)
            c.set("c", 3)
            self.assertNotIn("a", c)
''')

CACHE_API = dd('''
    import unittest

    from ttlcache.cache import TTLCache


    class ClockKeyword(unittest.TestCase):
        def test_clock_keyword_drives_expiry(self):
            t = [100.0]
            c = TTLCache(5, maxsize=4, sliding=True, clock=lambda: t[0])
            c.set("a", 1)
            t[0] += 4.5
            self.assertEqual(c.get("a"), 1)
            t[0] += 4.5
            self.assertEqual(c.get("a"), 1)
            t[0] += 5
            self.assertIsNone(c.get("a"))
            self.assertEqual(len(c), 0)
''')


def ttlcache(rng) -> TLib:
    return _lib("py-ttlcache", "ttlcache", "TTLCache", "cache", "the TTL cache of the session service", "The service keeps rendered pages in a `TTLCache` so that hot pages are not rebuilt.",
                CACHE_README, CACHE_SRC, CACHE_GOLD, CACHE_SLEEPY, CACHE_API,
                "the expiry boundary, sliding expiry with per-entry lifetimes, least-recently-used eviction and what counts as a use", 3, "TTLCache(1) is not None")


# ---------------------------------------------------------------------------------------------------------------------
# token bucket
# ---------------------------------------------------------------------------------------------------------------------

BUCKET_README = dd('''
    # ratelimit

    A token-bucket rate limiter with one bucket per key: `ratelimit.bucket.RateLimiter`.

    ## Construction
    `RateLimiter(rate, burst)`. `rate` is the number of tokens added per second (any positive number, otherwise `ValueError`); `burst` is the capacity of a bucket, at least 1 (otherwise
    `ValueError`). A bucket that was never used is full.

    ## Methods
    * `allow(key, cost=1)` takes `cost` tokens from the bucket of `key` and returns `True` if it holds enough of them, otherwise it takes nothing and returns `False`.
      `cost` must be between 1 and `burst` inclusive, otherwise `ValueError` (checked before anything else happens).
    * `tokens(key)` is the current level of the bucket as a float, after refilling.
    * `retry_after(key, cost=1)` is the number of seconds until `cost` tokens are available: `0.0` if they are available now. Same check of `cost` as `allow`. It takes nothing.
    * `reset(key)` forgets the bucket of `key` (the next use finds a full bucket); unknown keys are ignored.

    Tokens flow in continuously, `rate` per second, up to `burst`, counted from the time of the last `allow` call for that key (a bucket that was only inspected keeps its old
    reference time). A clock that goes backwards never removes tokens.
''')

BUCKET_SRC = dd('''
    """Token-bucket rate limiting, one bucket per key."""
    import time


    class RateLimiter:
        def __init__(self, rate, burst, clock=time.monotonic):
            if rate <= 0:
                raise ValueError("rate must be positive")
            if burst < 1:
                raise ValueError("burst must be at least 1")
            self._rate = rate
            self._burst = burst
            self._clock = clock
            self._buckets = {}

        def _level(self, key, now):
            if key not in self._buckets:
                return float(self._burst)
            tokens, stamp = self._buckets[key]
            elapsed = max(0.0, now - stamp)
            return min(float(self._burst), tokens + elapsed * self._rate)

        def _check_cost(self, cost):
            if cost < 1 or cost > self._burst:
                raise ValueError("cost must be between 1 and burst")

        def allow(self, key, cost=1):
            self._check_cost(cost)
            now = self._clock()
            level = self._level(key, now)
            if level >= cost:
                self._buckets[key] = (level - cost, now)
                return True
            self._buckets[key] = (level, now)
            return False

        def tokens(self, key):
            return self._level(key, self._clock())

        def retry_after(self, key, cost=1):
            self._check_cost(cost)
            level = self._level(key, self._clock())
            if level >= cost:
                return 0.0
            return (cost - level) / self._rate

        def reset(self, key):
            self._buckets.pop(key, None)
''')

BUCKET_GOLD = dd('''
    import unittest

    from ratelimit.bucket import RateLimiter


''') + FAKE_CLOCK + "\n\n" + dd('''
    class RateLimiterTests(unittest.TestCase):
        def setUp(self):
            self.clock = Clock()

        def make(self, rate=2, burst=4):
            return RateLimiter(rate, burst, clock=self.clock)

        def test_a_new_bucket_is_full(self):
            rl = self.make(rate=1, burst=3)
            self.assertEqual(rl.tokens("k"), 3)
            self.assertTrue(rl.allow("k"))
            self.assertTrue(rl.allow("k"))
            self.assertTrue(rl.allow("k"))
            self.assertFalse(rl.allow("k"))

        def test_refill_is_continuous(self):
            rl = self.make(rate=2, burst=4)
            for _ in range(4):
                self.assertTrue(rl.allow("k"))
            self.assertFalse(rl.allow("k"))
            self.clock.advance(0.25)
            self.assertFalse(rl.allow("k"))
            self.assertEqual(rl.tokens("k"), 0.5)
            self.clock.advance(0.25)
            self.assertTrue(rl.allow("k"))
            self.assertFalse(rl.allow("k"))

        def test_the_bucket_never_overflows(self):
            rl = self.make(rate=2, burst=4)
            rl.allow("k")
            self.clock.advance(1000)
            self.assertEqual(rl.tokens("k"), 4)
            for _ in range(4):
                self.assertTrue(rl.allow("k"))
            self.assertFalse(rl.allow("k"))

        def test_a_denied_call_takes_nothing(self):
            rl = self.make(rate=1, burst=3)
            self.assertTrue(rl.allow("k", cost=2))
            self.assertFalse(rl.allow("k", cost=2))
            self.assertEqual(rl.tokens("k"), 1)
            self.assertTrue(rl.allow("k", cost=1))
            self.assertEqual(rl.tokens("k"), 0)

        def test_cost_equal_to_burst_is_allowed(self):
            rl = self.make(rate=1, burst=3)
            self.assertTrue(rl.allow("k", cost=3))
            self.assertFalse(rl.allow("k"))
            self.clock.advance(3)
            self.assertTrue(rl.allow("k", cost=3))

        def test_cost_validation(self):
            rl = self.make(rate=1, burst=3)
            for bad in (0, -1, 4):
                with self.assertRaises(ValueError):
                    rl.allow("k", cost=bad)
                with self.assertRaises(ValueError):
                    rl.retry_after("k", cost=bad)
            self.assertEqual(rl.tokens("k"), 3)

        def test_keys_are_independent(self):
            rl = self.make(rate=1, burst=2)
            self.assertTrue(rl.allow("a"))
            self.assertTrue(rl.allow("a"))
            self.assertFalse(rl.allow("a"))
            self.assertTrue(rl.allow("b"))
            self.assertEqual(rl.tokens("b"), 1)
            self.assertEqual(rl.tokens("a"), 0)

        def test_retry_after(self):
            rl = self.make(rate=2, burst=4)
            self.assertEqual(rl.retry_after("k"), 0.0)
            self.assertEqual(rl.retry_after("k", cost=4), 0.0)
            for _ in range(4):
                rl.allow("k")
            self.assertEqual(rl.retry_after("k"), 0.5)
            self.assertEqual(rl.retry_after("k", cost=3), 1.5)
            self.clock.advance(0.25)
            self.assertEqual(rl.retry_after("k"), 0.25)
            self.assertEqual(rl.tokens("k"), 0.5)
            self.clock.advance(0.25)
            self.assertEqual(rl.retry_after("k"), 0.0)

        def test_retry_after_does_not_consume(self):
            rl = self.make(rate=1, burst=2)
            rl.allow("k", cost=2)
            self.assertEqual(rl.retry_after("k", cost=2), 2.0)
            self.assertEqual(rl.retry_after("k", cost=2), 2.0)
            self.assertEqual(rl.tokens("k"), 0)

        def test_reset_refills_one_key_only(self):
            rl = self.make(rate=1, burst=2)
            rl.allow("a", cost=2)
            rl.allow("b", cost=2)
            rl.reset("a")
            rl.reset("never-seen")
            self.assertEqual(rl.tokens("a"), 2)
            self.assertEqual(rl.tokens("b"), 0)

        def test_a_clock_that_goes_backwards_removes_no_tokens(self):
            rl = self.make(rate=1, burst=4)
            rl.allow("k", cost=3)
            self.clock.advance(-50)
            self.assertEqual(rl.tokens("k"), 1)
            self.assertTrue(rl.allow("k"))
            self.assertEqual(rl.tokens("k"), 0)
            self.assertFalse(rl.allow("k"))
            self.clock.advance(1)
            self.assertEqual(rl.tokens("k"), 1)

        def test_fractional_rate(self):
            rl = self.make(rate=0.5, burst=2)
            rl.allow("k", cost=2)
            self.clock.advance(1)
            self.assertFalse(rl.allow("k"))
            self.clock.advance(1)
            self.assertTrue(rl.allow("k"))

        def test_constructor_validation(self):
            for rate, burst in ((0, 1), (-1, 1), (1, 0)):
                with self.assertRaises(ValueError):
                    RateLimiter(rate, burst)
            RateLimiter(0.001, 1)
''')

BUCKET_SLEEPY = dd('''
    import time
    import unittest

    from ratelimit.bucket import RateLimiter


    class SlowLimiterTests(unittest.TestCase):
        def test_burst_then_deny(self):
            rl = RateLimiter(1, 3)
            self.assertTrue(all(rl.allow("k") for _ in range(3)))
            self.assertFalse(rl.allow("k"))

        def test_refills_over_time(self):
            rl = RateLimiter(5, 1)
            self.assertTrue(rl.allow("k"))
            self.assertFalse(rl.allow("k"))
            time.sleep(0.25)
            self.assertTrue(rl.allow("k"))

        def test_does_not_refill_too_fast(self):
            rl = RateLimiter(1, 1)
            rl.allow("k")
            time.sleep(0.2)
            self.assertFalse(rl.allow("k"))

        def test_retry_after_is_reasonable(self):
            rl = RateLimiter(2, 1)
            rl.allow("k")
            self.assertTrue(0.3 < rl.retry_after("k") <= 0.5)

        def test_keys_are_independent(self):
            rl = RateLimiter(1, 1)
            rl.allow("a")
            self.assertTrue(rl.allow("b"))
''')

BUCKET_API = dd('''
    import unittest

    from ratelimit.bucket import RateLimiter


    class ClockKeyword(unittest.TestCase):
        def test_clock_keyword_drives_the_refill(self):
            t = [50.0]
            rl = RateLimiter(2, 2, clock=lambda: t[0])
            self.assertTrue(rl.allow("k", cost=2))
            self.assertFalse(rl.allow("k"))
            t[0] += 0.5
            self.assertTrue(rl.allow("k"))
            self.assertFalse(rl.allow("k"))
            self.assertEqual(rl.retry_after("k"), 0.5)
''')


def ratelimit(rng) -> TLib:
    return _lib("py-ratelimit", "ratelimit", "RateLimiter", "bucket", "the API gateway's token-bucket limiter", "The gateway throttles every client key with a `RateLimiter` before calling the backend.",
                BUCKET_README, BUCKET_SRC, BUCKET_GOLD, BUCKET_SLEEPY, BUCKET_API,
                "the refill arithmetic, the cap at the burst size, what a denied call costs, cost validation and a clock that jumps back", 3, "RateLimiter(1, 1) is not None")


# ---------------------------------------------------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------------------------------------------------

SESSION_README = dd('''
    # sessions

    An in-memory session store with an idle timeout and an absolute lifetime: `sessions.store.SessionStore`.

    ## Construction
    `SessionStore(idle_timeout, max_lifetime)`, both in seconds and positive; the idle timeout must not be longer than the lifetime. Violations are a `ValueError`.

    ## Rules
    A session is created at some time `t0`; it is alive at time `t` as long as **both** `t - last_seen < idle_timeout` and `t - t0 < max_lifetime`. At exactly the limit it is already dead.
    A dead session is gone for good: nothing brings it back.

    ## Methods
    * `create(user)` returns a new token: `"s1"`, `"s2"`, ... in the order of creation (the counter never goes back, even after revocations).
    * `touch(token)` is a sign of activity: for a live session it sets `last_seen` to now and returns `True`; otherwise `False`.
    * `user(token)` is the user name of a live session or `None`. It is not activity.
    * `expires_in(token)` is the number of seconds until the session dies (whichever limit comes first, a float), `None` if it is not alive. Not activity.
    * `revoke(token)` ends a session: `True` if the token belonged to a stored session (even one that has expired meanwhile but was not looked at), `False` otherwise.
    * `revoke_user(user)` ends every session of that user and returns how many of them were still alive.
    * `active_count()` is the number of live sessions.
''')

SESSION_SRC = dd('''
    """An in-memory session store with idle and absolute timeouts."""
    import time


    class SessionStore:
        def __init__(self, idle_timeout, max_lifetime, clock=time.monotonic):
            if idle_timeout <= 0 or max_lifetime <= 0:
                raise ValueError("timeouts must be positive")
            if idle_timeout > max_lifetime:
                raise ValueError("idle timeout longer than the lifetime")
            self._idle = idle_timeout
            self._life = max_lifetime
            self._clock = clock
            self._sessions = {}
            self._counter = 0

        def create(self, user):
            self._counter += 1
            token = "s%d" % self._counter
            now = self._clock()
            self._sessions[token] = [user, now, now]
            return token

        def _alive(self, token, now):
            s = self._sessions.get(token)
            if s is None:
                return False
            if now - s[2] >= self._idle or now - s[1] >= self._life:
                del self._sessions[token]
                return False
            return True

        def touch(self, token):
            now = self._clock()
            if not self._alive(token, now):
                return False
            self._sessions[token][2] = now
            return True

        def user(self, token):
            if not self._alive(token, self._clock()):
                return None
            return self._sessions[token][0]

        def expires_in(self, token):
            now = self._clock()
            if not self._alive(token, now):
                return None
            s = self._sessions[token]
            return min(s[2] + self._idle, s[1] + self._life) - now

        def revoke(self, token):
            return self._sessions.pop(token, None) is not None

        def revoke_user(self, user):
            now = self._clock()
            n = 0
            for token in list(self._sessions):
                if self._sessions[token][0] != user:
                    continue
                if self._alive(token, now):
                    del self._sessions[token]
                    n += 1
            return n

        def active_count(self):
            now = self._clock()
            return sum(1 for token in list(self._sessions) if self._alive(token, now))
''')

SESSION_GOLD = dd('''
    import unittest

    from sessions.store import SessionStore


''') + FAKE_CLOCK + "\n\n" + dd('''
    class SessionStoreTests(unittest.TestCase):
        def setUp(self):
            self.clock = Clock()

        def make(self, idle=30, life=100):
            return SessionStore(idle, life, clock=self.clock)

        def test_tokens_count_up(self):
            s = self.make()
            self.assertEqual(s.create("ann"), "s1")
            self.assertEqual(s.create("bob"), "s2")
            s.revoke("s2")
            self.assertEqual(s.create("cy"), "s3")

        def test_idle_timeout_is_exclusive(self):
            s = self.make(idle=30, life=100)
            t = s.create("ann")
            self.clock.advance(29.5)
            self.assertTrue(s.touch(t))
            self.clock.advance(30)
            self.assertFalse(s.touch(t))
            self.assertIsNone(s.user(t))

        def test_touch_pushes_the_idle_deadline(self):
            s = self.make(idle=30, life=100)
            t = s.create("ann")
            for _ in range(3):
                self.clock.advance(20)
                self.assertTrue(s.touch(t))
            self.assertEqual(s.user(t), "ann")
            self.assertEqual(s.expires_in(t), 30)

        def test_absolute_lifetime_wins_over_activity(self):
            s = self.make(idle=30, life=100)
            t = s.create("ann")
            for _ in range(4):
                self.clock.advance(24)
                self.assertTrue(s.touch(t))
            self.assertEqual(s.expires_in(t), 4)
            self.clock.advance(4)
            self.assertFalse(s.touch(t))

        def test_lifetime_boundary(self):
            s = self.make(idle=100, life=100)
            t = s.create("ann")
            self.clock.advance(99.5)
            self.assertEqual(s.user(t), "ann")
            self.clock.advance(0.5)
            self.assertIsNone(s.user(t))

        def test_a_dead_session_does_not_come_back(self):
            s = self.make(idle=10, life=100)
            t = s.create("ann")
            self.clock.advance(10)
            self.assertFalse(s.touch(t))
            self.clock.advance(-5)
            self.assertFalse(s.touch(t))
            self.assertEqual(s.active_count(), 0)

        def test_user_and_expires_in_are_not_activity(self):
            s = self.make(idle=30, life=100)
            t = s.create("ann")
            self.clock.advance(20)
            self.assertEqual(s.user(t), "ann")
            self.assertEqual(s.expires_in(t), 10)
            self.clock.advance(10)
            self.assertIsNone(s.user(t))

        def test_expires_in_is_the_nearer_deadline(self):
            s = self.make(idle=30, life=100)
            t = s.create("ann")
            self.assertEqual(s.expires_in(t), 30)
            self.clock.advance(10)
            self.assertEqual(s.expires_in(t), 20)
            s.touch(t)
            self.assertEqual(s.expires_in(t), 30)
            for _ in range(3):
                self.clock.advance(25)
                s.touch(t)
            self.assertEqual(s.expires_in(t), 15)
            self.clock.advance(10)
            s.touch(t)
            self.assertEqual(s.expires_in(t), 5)
            self.assertIsNone(s.expires_in("nope"))

        def test_unknown_tokens(self):
            s = self.make()
            self.assertFalse(s.touch("s9"))
            self.assertIsNone(s.user("s9"))
            self.assertFalse(s.revoke("s9"))

        def test_revoke(self):
            s = self.make()
            t = s.create("ann")
            self.assertTrue(s.revoke(t))
            self.assertFalse(s.revoke(t))
            self.assertFalse(s.touch(t))

        def test_revoke_of_an_expired_but_unseen_session(self):
            s = self.make(idle=10, life=100)
            t = s.create("ann")
            self.clock.advance(50)
            self.assertTrue(s.revoke(t))

        def test_revoke_user_counts_live_sessions(self):
            s = self.make(idle=10, life=100)
            a1 = s.create("ann")
            a2 = s.create("ann")
            b1 = s.create("bob")
            self.clock.advance(6)
            s.touch(a2)
            s.touch(b1)
            self.clock.advance(6)
            self.assertEqual(s.revoke_user("ann"), 1)
            self.assertFalse(s.touch(a2))
            self.assertEqual(s.revoke_user("ann"), 0)
            self.assertTrue(s.touch(b1))
            self.assertFalse(s.touch(a1))

        def test_active_count(self):
            s = self.make(idle=10, life=15)
            a = s.create("ann")
            self.clock.advance(5)
            s.create("bob")
            self.assertEqual(s.active_count(), 2)
            self.clock.advance(5)
            self.assertEqual(s.active_count(), 1)
            s.touch(s.create("cy"))
            self.clock.advance(9)
            self.assertEqual(s.active_count(), 1)
            self.assertFalse(s.touch(a))

        def test_constructor_validation(self):
            for idle, life in ((0, 10), (10, 0), (-1, 10), (20, 10)):
                with self.assertRaises(ValueError):
                    SessionStore(idle, life)
            SessionStore(10, 10)
''')

SESSION_SLEEPY = dd('''
    import time
    import unittest

    from sessions.store import SessionStore


    class SlowSessionTests(unittest.TestCase):
        def test_idle_timeout(self):
            s = SessionStore(0.3, 5)
            t = s.create("ann")
            time.sleep(0.2)
            self.assertTrue(s.touch(t))
            time.sleep(0.4)
            self.assertFalse(s.touch(t))

        def test_lifetime(self):
            s = SessionStore(0.3, 0.6)
            t = s.create("ann")
            for _ in range(5):
                time.sleep(0.15)
                s.touch(t)
            self.assertIsNone(s.user(t))

        def test_user(self):
            s = SessionStore(5, 10)
            t = s.create("ann")
            self.assertEqual(s.user(t), "ann")

        def test_revoke_user(self):
            s = SessionStore(5, 10)
            s.create("ann")
            s.create("ann")
            s.create("bob")
            self.assertEqual(s.revoke_user("ann"), 2)
            self.assertEqual(s.active_count(), 1)

        def test_expires_in(self):
            s = SessionStore(5, 10)
            t = s.create("ann")
            time.sleep(0.2)
            self.assertTrue(4.5 < s.expires_in(t) < 5)
''')

SESSION_API = dd('''
    import unittest

    from sessions.store import SessionStore


    class ClockKeyword(unittest.TestCase):
        def test_clock_keyword_drives_the_timeouts(self):
            t = [10.0]
            s = SessionStore(30, 100, clock=lambda: t[0])
            tok = s.create("ann")
            t[0] += 29
            self.assertTrue(s.touch(tok))
            t[0] += 30
            self.assertFalse(s.touch(tok))
            self.assertEqual(s.active_count(), 0)
''')


def sessionstore(rng) -> TLib:
    return _lib("py-sessions", "sessions", "SessionStore", "store", "the web app's session store", "The login service hands out session tokens from a `SessionStore` with an idle timeout and a hard lifetime.",
                SESSION_README, SESSION_SRC, SESSION_GOLD, SESSION_SLEEPY, SESSION_API,
                "exclusive deadlines, activity versus mere lookups, which of the two limits wins, and sessions that die unnoticed", 4, "SessionStore(1, 2) is not None")


# ---------------------------------------------------------------------------------------------------------------------
# circuit breaker
# ---------------------------------------------------------------------------------------------------------------------

BREAKER_README = dd('''
    # breaker

    A circuit breaker for calls to a flaky backend: `breaker.core.CircuitBreaker`.

    ## Construction
    `CircuitBreaker(failure_threshold=3, cooldown=30, success_threshold=1)`. The thresholds are integers of at least 1, `cooldown` (seconds) is positive; otherwise `ValueError`.

    ## States
    * `closed`: calls are allowed. Every `record_failure()` counts; a `record_success()` resets the count to zero (only *consecutive* failures matter). When the count reaches
      `failure_threshold` the breaker trips to `open`.
    * `open`: `allow()` is `False`. Once `cooldown` seconds have passed since the trip (at exactly `cooldown` it is already over) the breaker is `half-open`.
      Results reported while it is open (late replies) are ignored; in particular they do not extend the cooldown.
    * `half-open`: one probe at a time. `allow()` returns `True` for the first caller and `False` for everybody else until that probe's result has been recorded.
      A `record_success()` counts toward `success_threshold`; when it is reached the breaker is `closed` again with a clean failure count (and the next probe, if the threshold is
      higher than 1, is allowed right after each success). Any `record_failure()` trips it back to `open` with a fresh cooldown.

    ## Inspection
    `state` is one of `"closed"`, `"open"`, `"half-open"` (the property takes the elapsed time into account). `retry_in()` is the number of seconds an open breaker still has to wait (a float),
    `0.0` in any other state.
''')

BREAKER_SRC = dd('''
    """A circuit breaker."""
    import time

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


    class CircuitBreaker:
        def __init__(self, failure_threshold=3, cooldown=30, success_threshold=1, clock=time.monotonic):
            if failure_threshold < 1 or success_threshold < 1:
                raise ValueError("thresholds must be at least 1")
            if cooldown <= 0:
                raise ValueError("cooldown must be positive")
            self._fail_limit = failure_threshold
            self._cooldown = cooldown
            self._succ_limit = success_threshold
            self._clock = clock
            self._state = CLOSED
            self._failures = 0
            self._successes = 0
            self._opened_at = 0.0
            self._probing = False

        def _refresh(self):
            if self._state == OPEN and self._clock() - self._opened_at >= self._cooldown:
                self._state = HALF_OPEN
                self._successes = 0
                self._probing = False

        def _trip(self):
            self._state = OPEN
            self._opened_at = self._clock()
            self._failures = 0
            self._probing = False

        @property
        def state(self):
            self._refresh()
            return self._state

        def allow(self):
            self._refresh()
            if self._state == CLOSED:
                return True
            if self._state == OPEN:
                return False
            if self._probing:
                return False
            self._probing = True
            return True

        def record_success(self):
            self._refresh()
            if self._state == CLOSED:
                self._failures = 0
            elif self._state == HALF_OPEN:
                self._probing = False
                self._successes += 1
                if self._successes >= self._succ_limit:
                    self._state = CLOSED
                    self._failures = 0

        def record_failure(self):
            self._refresh()
            if self._state == CLOSED:
                self._failures += 1
                if self._failures >= self._fail_limit:
                    self._trip()
            elif self._state == HALF_OPEN:
                self._trip()

        def retry_in(self):
            self._refresh()
            if self._state != OPEN:
                return 0.0
            return self._opened_at + self._cooldown - self._clock()
''')

BREAKER_GOLD = dd('''
    import unittest

    from breaker.core import CircuitBreaker


''') + FAKE_CLOCK + "\n\n" + dd('''
    class CircuitBreakerTests(unittest.TestCase):
        def setUp(self):
            self.clock = Clock()

        def make(self, **kw):
            return CircuitBreaker(clock=self.clock, **kw)

        def trip(self, cb, n=3):
            for _ in range(n):
                self.assertTrue(cb.allow())
                cb.record_failure()

        def test_starts_closed_and_allows(self):
            cb = self.make()
            self.assertEqual(cb.state, "closed")
            self.assertTrue(cb.allow())
            self.assertEqual(cb.retry_in(), 0.0)

        def test_trips_after_the_threshold(self):
            cb = self.make(failure_threshold=3)
            cb.record_failure()
            cb.record_failure()
            self.assertEqual(cb.state, "closed")
            cb.record_failure()
            self.assertEqual(cb.state, "open")
            self.assertFalse(cb.allow())

        def test_success_resets_the_failure_count(self):
            cb = self.make(failure_threshold=3)
            cb.record_failure()
            cb.record_failure()
            cb.record_success()
            cb.record_failure()
            cb.record_failure()
            self.assertEqual(cb.state, "closed")
            cb.record_failure()
            self.assertEqual(cb.state, "open")

        def test_cooldown_is_exact(self):
            cb = self.make(failure_threshold=1, cooldown=30)
            cb.record_failure()
            self.assertEqual(cb.retry_in(), 30)
            self.clock.advance(29.5)
            self.assertEqual(cb.state, "open")
            self.assertFalse(cb.allow())
            self.assertEqual(cb.retry_in(), 0.5)
            self.clock.advance(0.5)
            self.assertEqual(cb.state, "half-open")
            self.assertEqual(cb.retry_in(), 0.0)

        def test_half_open_lets_one_probe_through(self):
            cb = self.make(failure_threshold=1, cooldown=10)
            cb.record_failure()
            self.clock.advance(10)
            self.assertTrue(cb.allow())
            self.assertFalse(cb.allow())
            self.assertFalse(cb.allow())
            self.assertEqual(cb.state, "half-open")

        def test_a_successful_probe_closes_the_breaker(self):
            cb = self.make(failure_threshold=2, cooldown=10)
            self.trip(cb, 2)
            self.clock.advance(10)
            self.assertTrue(cb.allow())
            cb.record_success()
            self.assertEqual(cb.state, "closed")
            self.assertTrue(cb.allow())
            self.assertTrue(cb.allow())
            cb.record_failure()
            self.assertEqual(cb.state, "closed")

        def test_a_failed_probe_reopens_with_a_fresh_cooldown(self):
            cb = self.make(failure_threshold=1, cooldown=10)
            cb.record_failure()
            self.clock.advance(12)
            self.assertTrue(cb.allow())
            cb.record_failure()
            self.assertEqual(cb.state, "open")
            self.assertEqual(cb.retry_in(), 10)
            self.clock.advance(9)
            self.assertFalse(cb.allow())
            self.clock.advance(1)
            self.assertTrue(cb.allow())

        def test_several_successes_may_be_required(self):
            cb = self.make(failure_threshold=1, cooldown=10, success_threshold=2)
            cb.record_failure()
            self.clock.advance(10)
            self.assertTrue(cb.allow())
            cb.record_success()
            self.assertEqual(cb.state, "half-open")
            self.assertTrue(cb.allow())
            self.assertFalse(cb.allow())
            cb.record_success()
            self.assertEqual(cb.state, "closed")

        def test_the_success_count_restarts_in_every_half_open_phase(self):
            cb = self.make(failure_threshold=1, cooldown=10, success_threshold=2)
            cb.record_failure()
            self.clock.advance(10)
            cb.allow()
            cb.record_success()
            cb.allow()
            cb.record_failure()
            self.assertEqual(cb.state, "open")
            self.clock.advance(10)
            cb.allow()
            cb.record_success()
            self.assertEqual(cb.state, "half-open")

        def test_failures_before_the_trip_do_not_leak_into_the_next_closed_phase(self):
            cb = self.make(failure_threshold=2, cooldown=10)
            self.trip(cb, 2)
            self.clock.advance(10)
            cb.allow()
            cb.record_success()
            cb.record_failure()
            self.assertEqual(cb.state, "closed")
            cb.record_failure()
            self.assertEqual(cb.state, "open")

        def test_results_while_open_are_ignored(self):
            cb = self.make(failure_threshold=1, cooldown=10)
            cb.record_failure()
            self.clock.advance(6)
            cb.record_failure()
            cb.record_success()
            self.assertEqual(cb.state, "open")
            self.assertEqual(cb.retry_in(), 4)
            self.clock.advance(4)
            self.assertEqual(cb.state, "half-open")

        def test_an_unanswered_probe_blocks_until_a_result(self):
            cb = self.make(failure_threshold=1, cooldown=10)
            cb.record_failure()
            self.clock.advance(10)
            self.assertTrue(cb.allow())
            self.clock.advance(1000)
            self.assertFalse(cb.allow())
            cb.record_success()
            self.assertTrue(cb.allow())

        def test_constructor_validation(self):
            for kw in ({"failure_threshold": 0}, {"success_threshold": 0}, {"cooldown": 0}, {"cooldown": -5}):
                with self.assertRaises(ValueError):
                    CircuitBreaker(**kw)
            CircuitBreaker(1, 0.5, 1)
''')

BREAKER_SLEEPY = dd('''
    import time
    import unittest

    from breaker.core import CircuitBreaker


    class SlowBreakerTests(unittest.TestCase):
        def test_opens_and_recovers(self):
            cb = CircuitBreaker(failure_threshold=2, cooldown=0.3)
            cb.record_failure()
            cb.record_failure()
            self.assertEqual(cb.state, "open")
            self.assertFalse(cb.allow())
            time.sleep(0.4)
            self.assertEqual(cb.state, "half-open")
            self.assertTrue(cb.allow())
            cb.record_success()
            self.assertEqual(cb.state, "closed")

        def test_failed_probe_reopens(self):
            cb = CircuitBreaker(failure_threshold=1, cooldown=0.2)
            cb.record_failure()
            time.sleep(0.3)
            self.assertTrue(cb.allow())
            cb.record_failure()
            self.assertEqual(cb.state, "open")

        def test_stays_open_during_the_cooldown(self):
            cb = CircuitBreaker(failure_threshold=1, cooldown=5)
            cb.record_failure()
            time.sleep(0.2)
            self.assertFalse(cb.allow())

        def test_only_one_probe(self):
            cb = CircuitBreaker(failure_threshold=1, cooldown=0.2)
            cb.record_failure()
            time.sleep(0.3)
            self.assertTrue(cb.allow())
            self.assertFalse(cb.allow())
''')

BREAKER_API = dd('''
    import unittest

    from breaker.core import CircuitBreaker


    class ClockKeyword(unittest.TestCase):
        def test_clock_keyword_drives_the_cooldown(self):
            t = [0.0]
            cb = CircuitBreaker(failure_threshold=1, cooldown=10, clock=lambda: t[0])
            cb.record_failure()
            t[0] += 9.5
            self.assertEqual(cb.state, "open")
            t[0] += 0.5
            self.assertEqual(cb.state, "half-open")
            self.assertTrue(cb.allow())
''')


def breaker(rng) -> TLib:
    return _lib("py-breaker", "breaker", "CircuitBreaker", "core", "the circuit breaker in front of the payment backend", "The checkout service wraps every call to the payment provider in a `CircuitBreaker`.",
                BREAKER_README, BREAKER_SRC, BREAKER_GOLD, BREAKER_SLEEPY, BREAKER_API,
                "consecutive-failure counting, the exact end of the cooldown, one probe at a time, and what late results do", 4, "CircuitBreaker() is not None")
