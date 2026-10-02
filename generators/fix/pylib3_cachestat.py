"""Caches, statistics and hashing in domain clothes (python, fix-py-3): edge-cache eviction, telemetry stats, hash ring, latency histogram."""
from fx import Lib, dd

from generators.fix._pylib3 import chain, register_libs3

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# edgecache: byte-budget cache with cost-aware eviction
# ======================================================================================================================

EDGECACHE_README = dd('''
    # edgecache

    The in-memory object cache of a CDN edge node. It has a byte budget; when a new object does not fit, the least
    valuable objects are evicted. Time is a plain integer (seconds) passed in by the caller, never read from a clock.

    ## `Cache(capacity)`

    `capacity` is the byte budget (a positive integer, otherwise `ValueError`); it is kept as the attribute `capacity`.

    * `put(key, size, cost, now, ttl=None, pinned=False) -> bool`: store an object of `size` bytes whose refetch costs
      `cost`. `ValueError` for `size < 1`, `cost < 0` or a `ttl` that is not `None` and below 1. Steps:
      1. First `purge(now)`.
      2. An object bigger than `capacity` is rejected: return `False`, nothing else changes.
      3. Putting an existing key *replaces* it: the old entry's bytes count as free while making room, and the new
         entry keeps the old entry's hit count and takes the new `ttl` and `pinned` flag.
      4. If the object does not fit, entries are evicted until it does. Pinned entries and the key itself are never
         victims. Victims are taken in ascending order of `(score, last_used, key)`, where
         `score = (hits + 1) * cost * 1000 // size`.
      5. If evicting every possible victim still would not make room, return `False` and evict **nothing**
         (all-or-nothing).
      6. Otherwise evict the chosen victims (each counts as one eviction), store the entry with `last_used = now`
         and `expires = now + ttl` (no expiry when `ttl is None`) and return `True`.
    * `get(key, now) -> bool`: `purge(now)` first; a stored key is a hit (the entry's hit count goes up, its
      `last_used` becomes `now`), anything else is a miss. Returns whether it was a hit.
    * `purge(now) -> int`: remove every entry with `expires` not `None` and `now >= expires`; each counts as one
      expiration. Returns how many were removed.
    * `discard(key) -> bool`: remove an entry without counting it as an eviction; whether it was there.
    * `used`: bytes in use; `len(cache)`, `key in cache` (a membership test is not a hit and does not purge),
      `keys()` sorted list.
    * `stats() -> dict`: `{"hits", "misses", "evictions", "expirations"}` counters, and `hit_ratio_pct() -> int`:
      `100 * hits // (hits + misses)`, `0` when there were no lookups.
''')

EDGECACHE_SRC = dd('''
    """Byte-budget cache with cost-aware eviction."""


    class _Entry:
        def __init__(self, size, cost, hits, last_used, expires, pinned):
            self.size = size
            self.cost = cost
            self.hits = hits
            self.last_used = last_used
            self.expires = expires
            self.pinned = pinned

        def score(self):
            return (self.hits + 1) * self.cost * 1000 // self.size


    class Cache:
        def __init__(self, capacity):
            if capacity < 1:
                raise ValueError("capacity must be positive")
            self.capacity = capacity
            self._items = {}
            self._counts = {"hits": 0, "misses": 0, "evictions": 0, "expirations": 0}

        @property
        def used(self):
            return sum(e.size for e in self._items.values())

        def __len__(self):
            return len(self._items)

        def __contains__(self, key):
            return key in self._items

        def keys(self):
            return sorted(self._items)

        def stats(self):
            return dict(self._counts)

        def hit_ratio_pct(self):
            total = self._counts["hits"] + self._counts["misses"]
            return 100 * self._counts["hits"] // total if total else 0

        def purge(self, now):
            dead = [k for k, e in self._items.items() if e.expires is not None and now >= e.expires]
            for k in dead:
                del self._items[k]
            self._counts["expirations"] += len(dead)
            return len(dead)

        def discard(self, key):
            return self._items.pop(key, None) is not None

        def get(self, key, now):
            self.purge(now)
            entry = self._items.get(key)
            if entry is None:
                self._counts["misses"] += 1
                return False
            entry.hits += 1
            entry.last_used = now
            self._counts["hits"] += 1
            return True

        def put(self, key, size, cost, now, ttl=None, pinned=False):
            if size < 1 or cost < 0 or (ttl is not None and ttl < 1):
                raise ValueError("bad size, cost or ttl")
            self.purge(now)
            if size > self.capacity:
                return False
            old = self._items.get(key)
            need = self.used - (old.size if old else 0) + size - self.capacity
            victims = []
            if need > 0:
                pool = [(e.score(), e.last_used, k) for k, e in self._items.items() if k != key and not e.pinned]
                for _, _, k in sorted(pool):
                    victims.append(k)
                    need -= self._items[k].size
                    if need <= 0:
                        break
                if need > 0:
                    return False
            for k in victims:
                del self._items[k]
            self._counts["evictions"] += len(victims)
            hits = old.hits if old else 0
            expires = None if ttl is None else now + ttl
            self._items[key] = _Entry(size, cost, hits, now, expires, pinned)
            return True
''')

EDGECACHE_VISIBLE = dd('''
    import unittest

    from edgecache.cache import Cache


    class BasicTests(unittest.TestCase):
        def test_put_get(self):
            c = Cache(100)
            self.assertTrue(c.put("a", 40, 10, 0))
            self.assertTrue(c.get("a", 1))
            self.assertFalse(c.get("b", 1))

        def test_evicts_cheapest(self):
            c = Cache(100)
            c.put("a", 40, 10, 0)
            c.put("b", 40, 30, 0)
            c.put("c", 40, 10, 0)
            self.assertEqual(c.keys(), ["b", "c"])


    if __name__ == "__main__":
        unittest.main()
''')

EDGECACHE_HIDDEN = dd('''
    import unittest

    from edgecache.cache import Cache


    class Construction(unittest.TestCase):
        def test_capacity(self):
            for cap in (0, -5):
                with self.assertRaises(ValueError):
                    Cache(cap)
            self.assertEqual(Cache(1).capacity, 1)

        def test_put_validation(self):
            c = Cache(100)
            for args in ((0, 1), (-3, 1), (5, -1)):
                with self.assertRaises(ValueError):
                    c.put("k", args[0], args[1], 0)
            for ttl in (0, -2):
                with self.assertRaises(ValueError):
                    c.put("k", 5, 1, 0, ttl=ttl)
            self.assertEqual(len(c), 0)
            self.assertTrue(c.put("free", 5, 0, 0))
            self.assertTrue(c.put("ttl1", 5, 1, 0, ttl=1))


    class Eviction(unittest.TestCase):
        def test_lowest_score_goes_first(self):
            c = Cache(100)
            c.put("a", 40, 10, 0)    # 250
            c.put("b", 40, 30, 0)    # 750
            self.assertEqual(c.used, 80)
            self.assertTrue(c.put("c", 40, 10, 0))
            self.assertEqual(c.keys(), ["b", "c"])
            self.assertEqual(c.stats()["evictions"], 1)
            self.assertEqual(c.used, 80)

        def test_score_uses_size(self):
            c = Cache(100)
            c.put("big", 60, 30, 0)     # 500
            c.put("small", 30, 20, 0)   # 666
            self.assertTrue(c.put("n", 30, 1, 0))
            self.assertEqual(c.keys(), ["n", "small"])

        def test_score_is_cost_times_hits_over_size(self):
            c = Cache(100600)
            c.put("x", 100000, 100, 0)    # 100
            c.put("y", 500, 1, 0)         # 2000
            self.assertTrue(c.put("z", 500, 1, 1))
            self.assertEqual(c.keys(), ["y", "z"])

        def test_hit_count_goes_up_by_one(self):
            c = Cache(100)
            c.put("a", 40, 10, 0)
            c.get("a", 1)             # one hit: score 500
            c.put("b", 40, 20, 5)     # 500: a tie, a was used longer ago
            self.assertTrue(c.put("c", 40, 40, 6))
            self.assertEqual(c.keys(), ["b", "c"])

        def test_one_byte_short_keeps_evicting(self):
            c = Cache(100)
            c.put("a", 50, 1, 0)
            c.put("b", 50, 2, 0)
            self.assertTrue(c.put("c", 51, 100, 1))
            self.assertEqual(c.keys(), ["c"])

        def test_one_byte_short_of_room_fails(self):
            c = Cache(100)
            c.put("p", 50, 1, 0, pinned=True)
            c.put("a", 49, 1, 0)
            self.assertFalse(c.put("c", 51, 100, 1))
            self.assertEqual(c.keys(), ["a", "p"])
            self.assertTrue(c.put("d", 50, 100, 1))
            self.assertEqual(c.keys(), ["d", "p"])

        def test_victims_exactly_fill_the_gap(self):
            c = Cache(100)
            c.put("a", 50, 1, 0)
            c.put("b", 50, 2, 0)
            self.assertTrue(c.put("c", 50, 100, 1))
            self.assertEqual(c.keys(), ["b", "c"])
            self.assertEqual(c.stats()["evictions"], 1)

        def test_score_is_floored(self):
            c = Cache(1100)
            c.put("a", 7, 1, 3)        # 1000 // 7 = 142 (142.857 before flooring)
            c.put("b", 1000, 142, 5)   # exactly 142: a tie, so the older entry goes first
            self.assertTrue(c.put("c", 100, 1, 6))
            self.assertEqual(c.keys(), ["b", "c"])

        def test_hits_raise_the_score(self):
            c = Cache(100)
            c.put("a", 40, 10, 0)
            c.put("b", 40, 30, 0)
            c.get("a", 1)
            c.get("a", 2)    # a: (2 + 1) * 10 * 1000 // 40 = 750
            c.get("b", 3)    # b: (1 + 1) * 30 * 1000 // 40 = 1500
            self.assertTrue(c.put("c", 40, 10, 4))
            self.assertEqual(c.keys(), ["b", "c"])
            c = Cache(100)
            c.put("a", 40, 10, 0)
            c.put("b", 40, 20, 0)    # 500
            for t in (1, 2, 3):
                c.get("a", t)        # a: 4 * 10 * 1000 // 40 = 1000
            self.assertTrue(c.put("c", 40, 1, 4))
            self.assertEqual(c.keys(), ["a", "c"])

        def test_ties_break_on_last_used_then_key(self):
            c = Cache(100)
            c.put("x", 40, 10, 5)
            c.put("m", 40, 10, 3)
            self.assertTrue(c.put("n", 40, 10, 9))
            self.assertEqual(c.keys(), ["n", "x"])    # m is older
            c = Cache(100)
            c.put("x", 40, 10, 3)
            c.put("m", 40, 10, 3)
            self.assertTrue(c.put("n", 40, 10, 9))
            self.assertEqual(c.keys(), ["n", "x"])    # same age: the smaller key goes first
            self.assertNotIn("m", c)

        def test_get_counts_a_hit(self):
            c = Cache(100)
            c.put("a", 40, 10, 0)
            c.put("b", 40, 10, 5)
            c.get("a", 8)       # a has one hit now: score 500, b 250
            self.assertTrue(c.put("c", 40, 10, 9))
            self.assertEqual(c.keys(), ["a", "c"])

        def test_get_refreshes_last_used(self):
            c = Cache(100)
            c.put("a", 40, 10, 0)
            c.put("b", 40, 10, 1)
            c.get("a", 10)      # both have one hit now (score 500): b was used longer ago
            c.get("b", 2)
            self.assertTrue(c.put("c", 40, 10, 11))
            self.assertEqual(c.keys(), ["a", "c"])

        def test_several_victims(self):
            c = Cache(100)
            for i, cost in enumerate((5, 1, 9, 2)):
                c.put(f"k{i}", 25, cost, 0)
            self.assertTrue(c.put("big", 60, 100, 1))
            self.assertEqual(c.keys(), ["big", "k2"])
            self.assertEqual(c.stats()["evictions"], 3)
            self.assertEqual(c.used, 85)

        def test_exact_fit_needs_no_eviction(self):
            c = Cache(100)
            c.put("a", 60, 1, 0)
            self.assertTrue(c.put("b", 40, 1, 0))
            self.assertEqual(c.keys(), ["a", "b"])
            self.assertEqual(c.stats()["evictions"], 0)
            self.assertTrue(c.put("c", 1, 1, 0))
            self.assertEqual(c.stats()["evictions"], 1)

        def test_stops_as_soon_as_room_is_made(self):
            c = Cache(100)
            c.put("a", 50, 1, 0)
            c.put("b", 30, 2, 0)
            c.put("c", 20, 3, 0)
            self.assertTrue(c.put("d", 40, 5, 0))
            self.assertEqual(c.keys(), ["b", "c", "d"])    # a (score 20) frees 50 bytes, which is enough
            self.assertEqual(c.stats()["evictions"], 1)
            self.assertEqual(c.used, 90)


    class Rejections(unittest.TestCase):
        def test_too_big_changes_nothing(self):
            c = Cache(100)
            c.put("a", 50, 1, 0)
            self.assertFalse(c.put("huge", 101, 999, 0))
            self.assertEqual(c.keys(), ["a"])
            self.assertEqual(c.stats()["evictions"], 0)
            self.assertTrue(c.put("full", 100, 999, 0))
            self.assertEqual(c.keys(), ["full"])

        def test_pinned_entries_are_safe(self):
            c = Cache(100)
            c.put("p", 60, 0, 0, pinned=True)
            c.put("u", 40, 1, 0)
            self.assertFalse(c.put("x", 50, 100, 0))
            self.assertEqual(c.keys(), ["p", "u"])
            self.assertEqual(c.stats()["evictions"], 0)
            self.assertTrue(c.put("y", 40, 1, 0))
            self.assertEqual(c.keys(), ["p", "y"])

        def test_all_or_nothing(self):
            c = Cache(100)
            c.put("p", 60, 0, 0, pinned=True)
            c.put("u", 20, 1, 0)
            self.assertFalse(c.put("x", 50, 100, 0))     # u frees 20, still 10 short
            self.assertEqual(c.keys(), ["p", "u"])
            self.assertEqual(c.stats()["evictions"], 0)

        def test_failed_replacement_keeps_old_entry(self):
            c = Cache(100)
            c.put("p", 80, 0, 0, pinned=True)
            c.put("a", 10, 1, 0)
            self.assertFalse(c.put("a", 30, 1, 1))
            self.assertEqual(c.used, 90)
            self.assertTrue(c.get("a", 2))


    class Replace(unittest.TestCase):
        def test_replacing_frees_own_bytes(self):
            c = Cache(100)
            c.put("a", 60, 1, 0)
            self.assertTrue(c.put("a", 90, 1, 1))
            self.assertEqual(c.used, 90)
            self.assertEqual(c.stats()["evictions"], 0)
            self.assertTrue(c.put("a", 100, 1, 2))
            self.assertEqual(c.used, 100)

        def test_replace_keeps_the_hit_count(self):
            c = Cache(100)
            c.put("a", 40, 10, 0)
            c.get("a", 1)
            c.get("a", 2)
            c.put("a", 40, 10, 3)     # still 2 hits: score 750
            c.put("b", 40, 20, 3)     # 500
            self.assertTrue(c.put("c", 40, 30, 4))
            self.assertEqual(c.keys(), ["a", "c"])

        def test_replace_takes_the_new_pinned_flag(self):
            c = Cache(100)
            c.put("a", 40, 1, 0, pinned=True)
            c.put("b", 40, 500, 0)
            c.put("a", 40, 1, 1)      # no longer pinned
            self.assertTrue(c.put("c", 40, 5, 2))
            self.assertEqual(c.keys(), ["b", "c"])
            c = Cache(100)
            c.put("a", 40, 1, 0)
            c.put("b", 40, 500, 0)
            c.put("a", 40, 1, 1, pinned=True)
            self.assertTrue(c.put("c", 40, 5, 2))
            self.assertEqual(c.keys(), ["a", "c"])

        def test_replace_resets_expiry(self):
            c = Cache(100)
            c.put("a", 10, 1, 0, ttl=5)
            c.put("a", 10, 1, 4)
            self.assertTrue(c.get("a", 100))

        def test_replacement_never_evicts_itself(self):
            c = Cache(100)
            c.put("a", 50, 0, 0)
            c.put("b", 50, 100, 0)
            self.assertTrue(c.put("a", 70, 0, 1))
            self.assertEqual(c.keys(), ["a"])


    class Expiry(unittest.TestCase):
        def test_get_boundaries(self):
            c = Cache(100)
            c.put("a", 10, 1, 5, ttl=10)
            self.assertTrue(c.get("a", 14))
            self.assertFalse(c.get("a", 15))
            self.assertEqual(c.stats(), {"hits": 1, "misses": 1, "evictions": 0, "expirations": 1})
            self.assertEqual(len(c), 0)

        def test_no_ttl_never_expires(self):
            c = Cache(100)
            c.put("a", 10, 1, 0)
            self.assertTrue(c.get("a", 10 ** 9))

        def test_purge_counts_and_returns(self):
            c = Cache(100)
            c.put("a", 10, 1, 0, ttl=5)
            c.put("b", 10, 1, 0, ttl=7)
            c.put("c", 10, 1, 0)
            self.assertEqual(c.purge(4), 0)
            self.assertEqual(c.purge(5), 1)
            self.assertEqual(c.purge(5), 0)
            self.assertEqual(c.purge(50), 1)
            self.assertEqual(c.keys(), ["c"])
            self.assertEqual(c.stats()["expirations"], 2)
            self.assertEqual(c.stats()["evictions"], 0)

        def test_put_purges_first(self):
            c = Cache(100)
            c.put("old", 90, 1000, 0, ttl=3)
            self.assertTrue(c.put("new", 50, 1, 3))
            self.assertEqual(c.keys(), ["new"])
            self.assertEqual(c.stats()["expirations"], 1)
            self.assertEqual(c.stats()["evictions"], 0)

        def test_membership_does_not_purge(self):
            c = Cache(100)
            c.put("a", 10, 1, 0, ttl=1)
            self.assertIn("a", c)
            self.assertEqual(len(c), 1)
            self.assertEqual(c.stats()["expirations"], 0)


    class Stats(unittest.TestCase):
        def test_hit_ratio(self):
            c = Cache(100)
            self.assertEqual(c.hit_ratio_pct(), 0)
            c.put("a", 10, 1, 0)
            c.get("a", 1)
            c.get("a", 2)
            c.get("zz", 3)
            self.assertEqual(c.stats()["hits"], 2)
            self.assertEqual(c.stats()["misses"], 1)
            self.assertEqual(c.hit_ratio_pct(), 66)
            c.get("zz", 4)
            self.assertEqual(c.hit_ratio_pct(), 50)

        def test_stats_is_a_copy(self):
            c = Cache(100)
            s = c.stats()
            s["hits"] = 99
            self.assertEqual(c.stats()["hits"], 0)

        def test_discard(self):
            c = Cache(100)
            c.put("a", 10, 1, 0)
            self.assertTrue(c.discard("a"))
            self.assertFalse(c.discard("a"))
            self.assertEqual(c.stats()["evictions"], 0)
            self.assertEqual(c.used, 0)

        def test_misses_only_for_absent(self):
            c = Cache(100)
            self.assertFalse(c.get("x", 0))
            self.assertEqual(c.stats()["misses"], 1)
            self.assertEqual(c.stats()["hits"], 0)


    if __name__ == "__main__":
        unittest.main()
''')

EDGECACHE = Lib(
    name="edgecache", lang="python", title="the edgecache object cache (`edgecache/cache.py`)",
    blurb="The CDN edge node keeps hot objects in edgecache and relies on its cost-aware eviction to stay within the memory budget.",
    files={"edgecache/__init__.py": "", "edgecache/cache.py": EDGECACHE_SRC, "README.md": EDGECACHE_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": EDGECACHE_VISIBLE},
    hidden_tests={"tests/test_full.py": EDGECACHE_HIDDEN},
    mutate=["edgecache/cache.py"], difficulty=3, tags=["cache", "eviction"],
    probes=[
        chain("Cache(100)", ["put('a', 40, 10, 0)", "put('b', 40, 30, 0)", "put('c', 40, 10, 0)", "keys()", "stats()"]),
        chain("Cache(100)", ["put('p', 60, 0, 0, pinned=True)", "put('u', 20, 1, 0)", "put('x', 50, 100, 0)", "keys()"]),
        chain("Cache(100)", ["put('a', 60, 1, 0)", "put('a', 90, 1, 1)", "used", "keys()"]),
        chain("Cache(100)", ["put('a', 10, 1, 5, ttl=10)", "get('a', 14)", "get('a', 15)", "stats()"]),
        chain("Cache(100)", ["put('x', 40, 10, 5)", "put('m', 40, 10, 3)", "put('n', 40, 10, 9)", "keys()"]),
        chain("Cache(100)", ["put('a', 40, 10, 0)", "put('b', 40, 30, 0)", "get('a', 1)", "get('a', 2)", "get('b', 3)", "put('c', 40, 10, 4)", "keys()"]),
        chain("Cache(100)", ["put('a', 10, 1, 0)", "get('a', 1)", "get('a', 2)", "get('zz', 3)", "hit_ratio_pct()"]),
        chain("Cache(100)", ["put('old', 90, 1000, 0, ttl=3)", "put('new', 50, 1, 3)", "keys()", "stats()"]),
    ],
    probe_import="from edgecache.cache import Cache\n",
)

# ======================================================================================================================
# gardenstats: exact running statistics for sensor streams (multi-module)
# ======================================================================================================================

GARDENSTATS_README = dd('''
    # gardenstats

    Statistics for greenhouse sensor streams. Readings are integers (for example millidegrees) and all results are
    exact `fractions.Fraction` values, so nothing depends on float rounding.

    ## `gardenstats.running`

    `RunningStats()` accumulates a stream in constant space (Welford's method).

    * `push(x)`: add a reading.
    * `n`, `min`, `max`: count and extremes (`min` and `max` are `None` while empty).
    * `mean`: the exact mean as a `Fraction`; `ValueError` when empty.
    * `variance(sample=True)`: the exact variance. The sample variance divides by `n - 1` and needs `n >= 2`; the
      population variance (`sample=False`) divides by `n` and needs `n >= 1`. Otherwise `ValueError`.
    * `merge(other) -> RunningStats`: a *new* object that describes both streams together (neither input changes).
      With `delta = other.mean - self.mean` the combined mean is `self.mean + delta * other.n / n` and the combined
      sum of squared deviations is `M2_self + M2_other + delta**2 * self.n * other.n / n`. Merging with an empty
      object gives a copy of the other one; two empty objects give an empty one.

    ## `gardenstats.window`

    `Window(size)` keeps the last `size` readings (`ValueError` if `size < 1`).

    * `push(x)`; `len(w)`; `values()`: the kept readings, oldest first.
    * `mean()`: `Fraction`. `median()`: the middle reading of the sorted values, or for an even count the mean of the
      two middle ones, as a `Fraction`.
    * `percentile(p)`: the *nearest-rank* percentile: sort the values and take the one at 1-based rank
      `max(1, ceil(p * n / 100))`. `p` is an integer from 0 to 100, otherwise `ValueError`.
    * `trimmed_mean(k)`: sort, drop the `k` smallest and `k` largest readings and average the rest (`Fraction`);
      `ValueError` if `k < 0` or `2 * k >= len(w)`.

    All of `mean`, `median`, `percentile` and `trimmed_mean` raise `ValueError` on an empty window.

    ## `gardenstats.summary`

    * `fmt_fraction(value, places=2) -> str`: the number with exactly `places` decimals (no decimal point when
      `places == 0`), rounded half **away from zero**; a result that rounds to zero never gets a minus sign.
    * `describe(values) -> dict`: for a non-empty list of integers: `n`, `min`, `max`, `mean` (a `Fraction`),
      `median` (`Fraction`), `p90` (nearest rank as in `Window`) and `variance` (sample variance, or `None` for a
      single value). `ValueError` for an empty list.
    * `report(values, places=2) -> str`: the `describe` numbers as lines `name: value` in the order `n`, `min`, `max`,
      `mean`, `median`, `p90`, `variance`, formatted with `fmt_fraction` (`n`, `min`, `max`, `p90` print as plain
      integers when they are integers; a missing variance prints as `n/a`). Lines are joined with `"\\\\n"`.
''')

GARDENSTATS_RUNNING = dd('''
    """Welford running statistics, exact."""
    from fractions import Fraction


    class RunningStats:
        def __init__(self):
            self.n = 0
            self.min = None
            self.max = None
            self._mean = Fraction(0)
            self._m2 = Fraction(0)

        def push(self, x):
            self.n += 1
            delta = x - self._mean
            self._mean += Fraction(delta, self.n)
            self._m2 += delta * (x - self._mean)
            self.min = x if self.min is None or x < self.min else self.min
            self.max = x if self.max is None or x > self.max else self.max

        @property
        def mean(self):
            if self.n == 0:
                raise ValueError("no readings")
            return self._mean

        def variance(self, sample=True):
            need = 2 if sample else 1
            if self.n < need:
                raise ValueError("not enough readings")
            return self._m2 / (self.n - 1 if sample else self.n)

        def merge(self, other):
            out = RunningStats()
            if self.n == 0 or other.n == 0:
                src = other if self.n == 0 else self
                out.n, out.min, out.max = src.n, src.min, src.max
                out._mean, out._m2 = src._mean, src._m2
                return out
            out.n = self.n + other.n
            delta = other._mean - self._mean
            out._mean = self._mean + delta * other.n / out.n
            out._m2 = self._m2 + other._m2 + delta * delta * self.n * other.n / out.n
            out.min = min(self.min, other.min)
            out.max = max(self.max, other.max)
            return out
''')

GARDENSTATS_WINDOW = dd('''
    """A sliding window over the most recent readings."""
    from collections import deque
    from fractions import Fraction


    class Window:
        def __init__(self, size):
            if size < 1:
                raise ValueError("window size must be at least 1")
            self._items = deque(maxlen=size)

        def __len__(self):
            return len(self._items)

        def push(self, x):
            self._items.append(x)

        def values(self):
            return list(self._items)

        def _need(self):
            if not self._items:
                raise ValueError("empty window")
            return sorted(self._items)

        def mean(self):
            self._need()
            return Fraction(sum(self._items), len(self._items))

        def median(self):
            xs = self._need()
            mid = len(xs) // 2
            if len(xs) % 2:
                return Fraction(xs[mid])
            return Fraction(xs[mid - 1] + xs[mid], 2)

        def percentile(self, p):
            if not isinstance(p, int) or p < 0 or p > 100:
                raise ValueError("p must be an integer from 0 to 100")
            xs = self._need()
            rank = max(1, -(-p * len(xs) // 100))
            return xs[rank - 1]

        def trimmed_mean(self, k):
            xs = self._need()
            if k < 0 or 2 * k >= len(xs):
                raise ValueError("cannot trim that much")
            kept = xs[k:len(xs) - k]
            return Fraction(sum(kept), len(kept))
''')

GARDENSTATS_SUMMARY = dd('''
    """Descriptions and text reports."""
    from fractions import Fraction

    from .running import RunningStats
    from .window import Window


    def fmt_fraction(value, places=2):
        scale = 10 ** places
        scaled = abs(value) * scale
        whole = int(scaled)
        if scaled - whole >= Fraction(1, 2):
            whole += 1
        sign = "-" if value < 0 and whole else ""
        if places == 0:
            return f"{sign}{whole}"
        return f"{sign}{whole // scale}.{whole % scale:0{places}d}"


    def describe(values):
        if not values:
            raise ValueError("no values")
        stats = RunningStats()
        win = Window(len(values))
        for v in values:
            stats.push(v)
            win.push(v)
        return {
            "n": stats.n,
            "min": stats.min,
            "max": stats.max,
            "mean": stats.mean,
            "median": win.median(),
            "p90": win.percentile(90),
            "variance": stats.variance() if stats.n > 1 else None,
        }


    def _show(value, places):
        if isinstance(value, int):
            return str(value)
        return fmt_fraction(value, places)


    def report(values, places=2):
        d = describe(values)
        lines = []
        for name in ("n", "min", "max", "mean", "median", "p90", "variance"):
            v = d[name]
            lines.append(f"{name}: " + ("n/a" if v is None else _show(v, places)))
        return "\\\\n".join(lines)
''')

GARDENSTATS_VISIBLE = dd('''
    import unittest
    from fractions import Fraction

    from gardenstats.running import RunningStats
    from gardenstats.window import Window


    class BasicTests(unittest.TestCase):
        def test_mean(self):
            s = RunningStats()
            for x in (2, 4, 6):
                s.push(x)
            self.assertEqual(s.mean, 4)

        def test_median(self):
            w = Window(5)
            for x in (5, 1, 3):
                w.push(x)
            self.assertEqual(w.median(), Fraction(3))


    if __name__ == "__main__":
        unittest.main()
''')

GARDENSTATS_HIDDEN_RUNNING = dd('''
    import unittest
    from fractions import Fraction as F

    from gardenstats.running import RunningStats


    def feed(xs):
        s = RunningStats()
        for x in xs:
            s.push(x)
        return s


    DATA = [2, 4, 4, 4, 5, 5, 7, 9]


    class Running(unittest.TestCase):
        def test_empty(self):
            s = RunningStats()
            self.assertEqual((s.n, s.min, s.max), (0, None, None))
            with self.assertRaises(ValueError):
                s.mean
            with self.assertRaises(ValueError):
                s.variance()
            with self.assertRaises(ValueError):
                s.variance(sample=False)

        def test_basic(self):
            s = feed(DATA)
            self.assertEqual((s.n, s.min, s.max), (8, 2, 9))
            self.assertEqual(s.mean, 5)
            self.assertEqual(s.variance(sample=False), 4)
            self.assertEqual(s.variance(), F(32, 7))
            self.assertIsInstance(s.mean, F)

        def test_single_reading(self):
            s = feed([7])
            self.assertEqual(s.mean, 7)
            self.assertEqual(s.variance(sample=False), 0)
            with self.assertRaises(ValueError):
                s.variance()

        def test_two_readings(self):
            s = feed([1, 2])
            self.assertEqual(s.mean, F(3, 2))
            self.assertEqual(s.variance(), F(1, 2))
            self.assertEqual(s.variance(sample=False), F(1, 4))

        def test_negative_and_fractional_means(self):
            s = feed([-3, 0, 1])
            self.assertEqual(s.mean, F(-2, 3))
            self.assertEqual(s.variance(sample=False), F(26, 9))
            self.assertEqual((s.min, s.max), (-3, 1))

        def test_min_max_tracking_order(self):
            s = feed([5, 9, 1, 7])
            self.assertEqual((s.min, s.max), (1, 9))
            s = feed([1, 9, 5, 7])
            self.assertEqual((s.min, s.max), (1, 9))
            s = feed([-5])
            self.assertEqual((s.min, s.max), (-5, -5))

        def test_matches_direct_formula(self):
            xs = [13, -4, 27, 8, 8, 0, 91, -33, 5, 6, 1]
            s = feed(xs)
            mean = F(sum(xs), len(xs))
            ss = sum((x - mean) ** 2 for x in xs)
            self.assertEqual(s.mean, mean)
            self.assertEqual(s.variance(), ss / (len(xs) - 1))
            self.assertEqual(s.variance(sample=False), ss / len(xs))


    class Merge(unittest.TestCase):
        def test_merge_equals_concatenation(self):
            a, b = [1, 2, 3, 10], [7, 7, 20, -5, 4]
            m = feed(a).merge(feed(b))
            whole = feed(a + b)
            self.assertEqual(m.n, 9)
            self.assertEqual(m.mean, whole.mean)
            self.assertEqual(m.variance(), whole.variance())
            self.assertEqual(m.variance(sample=False), whole.variance(sample=False))
            self.assertEqual((m.min, m.max), (-5, 20))

        def test_merge_is_symmetric_and_pure(self):
            a, b = feed([1, 2, 3]), feed([10, 20])
            ab, ba = a.merge(b), b.merge(a)
            self.assertEqual((ab.mean, ab.variance()), (ba.mean, ba.variance()))
            self.assertEqual((a.n, a.mean), (3, 2))
            self.assertEqual((b.n, b.mean), (2, 15))
            self.assertIsNot(ab, a)

        def test_merge_with_empty(self):
            a = feed([4, 8, 9])
            for m in (a.merge(RunningStats()), RunningStats().merge(a)):
                self.assertEqual((m.n, m.min, m.max), (3, 4, 9))
                self.assertEqual(m.mean, F(7))
                self.assertEqual(m.variance(), a.variance())
                self.assertIsNot(m, a)
            m = RunningStats().merge(RunningStats())
            self.assertEqual((m.n, m.min, m.max), (0, None, None))

        def test_merged_object_keeps_growing(self):
            m = feed([1, 2]).merge(feed([3, 4]))
            m.push(5)
            whole = feed([1, 2, 3, 4, 5])
            self.assertEqual(m.mean, whole.mean)
            self.assertEqual(m.variance(), whole.variance())

        def test_merge_disjoint_ranges(self):
            for a, b in (([1, 2], [5, 6]), ([5, 6], [1, 2])):
                m = feed(a).merge(feed(b))
                self.assertEqual((m.min, m.max), (1, 6))
            m = feed([-9, -8]).merge(feed([-3]))
            self.assertEqual((m.min, m.max), (-9, -3))

        def test_unequal_sizes(self):
            m = feed([0]).merge(feed([6, 6, 6]))
            self.assertEqual(m.mean, F(9, 2))
            self.assertEqual(m.variance(sample=False), F(27, 4))
            m = feed([6, 6, 6]).merge(feed([0]))
            self.assertEqual(m.variance(sample=False), F(27, 4))


    if __name__ == "__main__":
        unittest.main()
''')

GARDENSTATS_HIDDEN_WINDOW = dd('''
    import unittest
    from fractions import Fraction as F

    from gardenstats.window import Window


    def win(size, xs):
        w = Window(size)
        for x in xs:
            w.push(x)
        return w


    class Basics(unittest.TestCase):
        def test_size_validation(self):
            for size in (0, -1):
                with self.assertRaises(ValueError):
                    Window(size)
            Window(1)

        def test_sliding(self):
            w = win(3, [1, 2, 3, 4, 5])
            self.assertEqual(w.values(), [3, 4, 5])
            self.assertEqual(len(w), 3)
            w = win(3, [1, 2])
            self.assertEqual(w.values(), [1, 2])
            self.assertEqual(len(w), 2)
            self.assertEqual(win(1, [4, 9]).values(), [9])

        def test_values_is_a_copy(self):
            w = win(3, [1, 2, 3])
            w.values().append(99)
            self.assertEqual(w.values(), [1, 2, 3])

        def test_empty_errors(self):
            w = Window(3)
            for call in (w.mean, w.median, lambda: w.percentile(50), lambda: w.trimmed_mean(0)):
                with self.assertRaises(ValueError):
                    call()


    class Centre(unittest.TestCase):
        def test_mean(self):
            self.assertEqual(win(4, [1, 2, 3, 5]).mean(), F(11, 4))
            self.assertEqual(win(2, [1, 2, 3, 6]).mean(), F(9, 2))
            self.assertIsInstance(win(2, [2, 2]).mean(), F)

        def test_median_odd_and_even(self):
            self.assertEqual(win(5, [9, 1, 5]).median(), 5)
            self.assertEqual(win(5, [9, 1, 5, 7, 3]).median(), 5)
            self.assertEqual(win(4, [10, 1, 4, 7]).median(), F(11, 2))
            self.assertEqual(win(4, [1, 2]).median(), F(3, 2))
            self.assertEqual(win(3, [4]).median(), 4)
            self.assertEqual(win(4, [-3, -4]).median(), F(-7, 2))

        def test_median_uses_sorted_values(self):
            self.assertEqual(win(6, [100, 1, 50, 2, 60, 3]).median(), F(53, 2))

        def test_trimmed_mean(self):
            w = win(6, [1, 100, 5, 7, 6, 3])
            self.assertEqual(w.trimmed_mean(0), F(122, 6))
            self.assertEqual(w.trimmed_mean(1), F(21, 4))
            self.assertEqual(w.trimmed_mean(2), F(11, 2))
            for k in (3, 4, -1):
                with self.assertRaises(ValueError):
                    w.trimmed_mean(k)
            self.assertEqual(win(3, [1, 50, 9]).trimmed_mean(1), 9)
            with self.assertRaises(ValueError):
                win(3, [1, 2]).trimmed_mean(1)


    class Percentile(unittest.TestCase):
        def test_nearest_rank(self):
            w = win(10, [15, 20, 35, 40, 50])
            self.assertEqual(w.percentile(0), 15)
            self.assertEqual(w.percentile(1), 15)
            self.assertEqual(w.percentile(20), 15)
            self.assertEqual(w.percentile(21), 20)
            self.assertEqual(w.percentile(30), 20)
            self.assertEqual(w.percentile(40), 20)
            self.assertEqual(w.percentile(41), 35)
            self.assertEqual(w.percentile(50), 35)
            self.assertEqual(w.percentile(60), 35)
            self.assertEqual(w.percentile(61), 40)
            self.assertEqual(w.percentile(80), 40)
            self.assertEqual(w.percentile(81), 50)
            self.assertEqual(w.percentile(100), 50)

        def test_unsorted_input_and_window(self):
            w = win(4, [99, 50, 10, 30, 20, 40])
            self.assertEqual(w.values(), [10, 30, 20, 40])
            self.assertEqual(w.percentile(25), 10)
            self.assertEqual(w.percentile(26), 20)
            self.assertEqual(w.percentile(100), 40)
            self.assertEqual(w.percentile(90), 40)

        def test_large_window(self):
            w = win(200, range(101))
            self.assertEqual(w.percentile(100), 100)
            self.assertEqual(w.percentile(50), 50)
            self.assertEqual(w.percentile(99), 99)
            self.assertEqual(w.percentile(1), 1)

        def test_single_value(self):
            w = win(3, [7])
            for p in (0, 1, 50, 100):
                self.assertEqual(w.percentile(p), 7)

        def test_validation(self):
            w = win(3, [1, 2, 3])
            for p in (-1, 101, 50.5, "50"):
                with self.assertRaises(ValueError):
                    w.percentile(p)


    if __name__ == "__main__":
        unittest.main()
''')

GARDENSTATS_HIDDEN_SUMMARY = dd('''
    import unittest
    from fractions import Fraction as F

    from gardenstats.summary import describe, fmt_fraction, report


    class Fmt(unittest.TestCase):
        def test_rounding_half_away_from_zero(self):
            self.assertEqual(fmt_fraction(F(7, 3)), "2.33")
            self.assertEqual(fmt_fraction(F(5, 3)), "1.67")
            self.assertEqual(fmt_fraction(F(1, 8), 2), "0.13")
            self.assertEqual(fmt_fraction(F(-1, 8), 2), "-0.13")
            self.assertEqual(fmt_fraction(F(5, 2), 0), "3")
            self.assertEqual(fmt_fraction(F(-5, 2), 0), "-3")
            self.assertEqual(fmt_fraction(F(7, 2), 0), "4")
            self.assertEqual(fmt_fraction(F(1, 2), 0), "1")
            self.assertEqual(fmt_fraction(F(2, 5), 0), "0")
            self.assertEqual(fmt_fraction(F(1, 200), 2), "0.01")
            self.assertEqual(fmt_fraction(F(1, 201), 2), "0.00")

        def test_no_negative_zero(self):
            self.assertEqual(fmt_fraction(F(-1, 300), 2), "0.00")
            self.assertEqual(fmt_fraction(F(-2, 5), 0), "0")
            self.assertEqual(fmt_fraction(0), "0.00")
            self.assertEqual(fmt_fraction(F(-1, 100), 2), "-0.01")

        def test_places(self):
            self.assertEqual(fmt_fraction(F(1, 3), 4), "0.3333")
            self.assertEqual(fmt_fraction(F(2, 3), 1), "0.7")
            self.assertEqual(fmt_fraction(F(5), 3), "5.000")
            self.assertEqual(fmt_fraction(7), "7.00")
            self.assertEqual(fmt_fraction(F(1, 20), 3), "0.050")
            self.assertEqual(fmt_fraction(F(1234567, 1000), 2), "1234.57")
            self.assertEqual(fmt_fraction(F(-1234567, 1000), 1), "-1234.6")
            self.assertEqual(fmt_fraction(F(999, 1000), 2), "1.00")
            self.assertEqual(fmt_fraction(F(1, 1000), 3), "0.001")


    class Describe(unittest.TestCase):
        def test_values(self):
            d = describe([2, 4, 4, 4, 5, 5, 7, 9])
            self.assertEqual(d["n"], 8)
            self.assertEqual((d["min"], d["max"]), (2, 9))
            self.assertEqual(d["mean"], 5)
            self.assertEqual(d["median"], F(9, 2))
            self.assertEqual(d["p90"], 9)
            self.assertEqual(d["variance"], F(32, 7))

        def test_order_independent(self):
            a = describe([9, 2, 5, 4, 7, 5, 4, 4])
            self.assertEqual(a, describe([2, 4, 4, 4, 5, 5, 7, 9]))

        def test_single_value(self):
            d = describe([42])
            self.assertEqual((d["n"], d["min"], d["max"], d["mean"], d["median"], d["p90"]), (1, 42, 42, 42, 42, 42))
            self.assertIsNone(d["variance"])

        def test_p90_of_a_hundred(self):
            d = describe(list(range(1, 101)))
            self.assertEqual(d["p90"], 90)

        def test_p90_nearest_rank(self):
            self.assertEqual(describe(list(range(1, 11)))["p90"], 9)
            self.assertEqual(describe(list(range(1, 12)))["p90"], 10)

        def test_empty(self):
            with self.assertRaises(ValueError):
                describe([])


    class Report(unittest.TestCase):
        def test_report(self):
            expected = "\\\\n".join([
                "n: 8", "min: 2", "max: 9", "mean: 5.00", "median: 4.50", "p90: 9", "variance: 4.57",
            ])
            self.assertEqual(report([2, 4, 4, 4, 5, 5, 7, 9]), expected)

        def test_places_and_single(self):
            self.assertEqual(report([3, 4], places=0).split("\\\\n")[3:], ["mean: 4", "median: 4", "p90: 4", "variance: 1"])
            self.assertEqual(report([3, 4], places=3).split("\\\\n")[3:], ["mean: 3.500", "median: 3.500", "p90: 4", "variance: 0.500"])
            self.assertEqual(report([42]), "\\\\n".join(["n: 1", "min: 42", "max: 42", "mean: 42.00", "median: 42.00", "p90: 42", "variance: n/a"]))

        def test_negative_numbers(self):
            lines = report([-3, 0, 1]).split("\\\\n")
            self.assertEqual(lines[1:3], ["min: -3", "max: 1"])
            self.assertEqual(lines[3], "mean: -0.67")
            self.assertEqual(lines[4], "median: 0.00")

        def test_empty(self):
            with self.assertRaises(ValueError):
                report([])


    if __name__ == "__main__":
        unittest.main()
''')

GARDENSTATS = Lib(
    name="gardenstats", lang="python", title="the gardenstats sensor statistics package",
    blurb="The greenhouse monitor uses gardenstats to summarise temperature and humidity readings without float rounding surprises.",
    files={
        "gardenstats/__init__.py": "", "gardenstats/running.py": GARDENSTATS_RUNNING, "gardenstats/window.py": GARDENSTATS_WINDOW,
        "gardenstats/summary.py": GARDENSTATS_SUMMARY, "README.md": GARDENSTATS_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": GARDENSTATS_VISIBLE},
    hidden_tests={
        "tests/test_running.py": GARDENSTATS_HIDDEN_RUNNING, "tests/test_window.py": GARDENSTATS_HIDDEN_WINDOW,
        "tests/test_summary.py": GARDENSTATS_HIDDEN_SUMMARY,
    },
    mutate=["gardenstats/running.py", "gardenstats/window.py", "gardenstats/summary.py"],
    difficulty=3, tags=["statistics", "streaming", "multi-module"],
    probes=[
        "feed([2, 4, 4, 4, 5, 5, 7, 9]).variance()", "feed([2, 4, 4, 4, 5, 5, 7, 9]).variance(sample=False)",
        "feed([-3, 0, 1]).mean", "(feed([0]).merge(feed([6, 6, 6]))).variance(sample=False)",
        "(feed([1, 2, 3, 10]).merge(feed([7, 7, 20, -5, 4]))).mean",
        "(feed([1, 2, 3, 10]).merge(feed([7, 7, 20, -5, 4]))).variance()",
        "win(10, [15, 20, 35, 40, 50]).percentile(21)", "win(10, [15, 20, 35, 40, 50]).percentile(40)",
        "win(4, [10, 1, 4, 7]).median()", "win(6, [1, 100, 5, 7, 6, 3]).trimmed_mean(1)",
        "win(3, [1, 2, 3, 4, 5]).values()",
        "fmt_fraction(Fraction(-5, 2), 0)", "fmt_fraction(Fraction(-1, 300))", "fmt_fraction(Fraction(1, 8))",
        "report([2, 4, 4, 4, 5, 5, 7, 9])", "report([42])",
    ],
    probe_import=(
        "from fractions import Fraction\n"
        "from gardenstats.running import RunningStats\nfrom gardenstats.window import Window\n"
        "from gardenstats.summary import fmt_fraction, report, describe\n"
        "def feed(xs):\n    s = RunningStats()\n    [s.push(x) for x in xs]\n    return s\n"
        "def win(n, xs):\n    w = Window(n)\n    [w.push(x) for x in xs]\n    return w\n"
    ),
)


# ======================================================================================================================
# keyring: consistent hashing with weights, replicas and ownership shares
# ======================================================================================================================

KEYRING_README = dd('''
    # keyring

    A consistent-hash ring that a cache cluster uses to decide which node owns a key.

    ## `hash32(text) -> int`

    32-bit FNV-1a over the UTF-8 bytes of `text`: start with `h = 2166136261`; for every byte `h ^= byte` and then
    `h = (h * 16777619) mod 2**32`. (`hash32("") == 2166136261`, `hash32("a") == 3826002220`,
    `hash32("foobar") == 3214735720`.)

    ## `Ring(vnodes=8, hash_fn=hash32)`

    `vnodes` is the number of points per unit of weight (`ValueError` if below 1); `hash_fn` maps a string to an
    integer position in `[0, 2**32)` and is used for points and for keys alike.

    * `add(node, weight=1)`: put a node on the ring. It gets `vnodes * weight` points, point `i` (counting from 0) at
      position `hash_fn(f"{node}#{i}")`. `ValueError` if `weight < 1` or the node is already on the ring.
    * `remove(node)`: take it off together with all its points; `KeyError` if it is not on the ring.
    * `nodes()`: sorted list of the nodes on the ring.
    * `lookup(key) -> str`: the owner of `key`: the node of the first point whose position is **greater than or
      equal to** `hash_fn(key)`, wrapping around to the lowest point when there is none. If two points have the same
      position, the one whose node name sorts first wins. `ValueError` on an empty ring.
    * `replicas(key, n) -> list[str]`: the first `n` *distinct* nodes met when walking the ring clockwise from the
      point that `lookup` would use (that point's node comes first). `ValueError` if `n < 1` or `n` is more than the
      number of nodes on the ring.
    * `shares() -> dict[node, Fraction]`: the fraction of the key space `[0, 2**32)` each node owns, as exact
      `Fraction`s that add up to 1 (empty dict for an empty ring). A point owns the arc from the previous point
      (exclusive) up to its own position (inclusive); the first point's arc starts after the last point, wrapping
      around the end of the space. Equal positions: only the first point (in `lookup` order) gets the arc, the others
      own nothing.
    * `moved(keys, other) -> list[str]`: the keys (in the given order) whose owner on this ring differs from their
      owner on the ring `other`.
''')

KEYRING_SRC = dd('''
    """Consistent hashing."""
    import bisect
    from fractions import Fraction

    SPACE = 1 << 32


    def hash32(text):
        h = 2166136261
        for byte in text.encode("utf-8"):
            h ^= byte
            h = (h * 16777619) % SPACE
        return h


    class Ring:
        def __init__(self, vnodes=8, hash_fn=hash32):
            if vnodes < 1:
                raise ValueError("vnodes must be at least 1")
            self.vnodes = vnodes
            self._hash = hash_fn
            self._weights = {}
            self._points = []

        def add(self, node, weight=1):
            if weight < 1:
                raise ValueError("weight must be at least 1")
            if node in self._weights:
                raise ValueError(f"{node!r} is already on the ring")
            self._weights[node] = weight
            for i in range(self.vnodes * weight):
                bisect.insort(self._points, (self._hash(f"{node}#{i}"), node))

        def remove(self, node):
            if node not in self._weights:
                raise KeyError(node)
            del self._weights[node]
            self._points = [pt for pt in self._points if pt[1] != node]

        def nodes(self):
            return sorted(self._weights)

        def _start(self, key):
            if not self._points:
                raise ValueError("the ring is empty")
            i = bisect.bisect_left(self._points, (self._hash(key), ""))
            return i % len(self._points)

        def lookup(self, key):
            return self._points[self._start(key)][1]

        def replicas(self, key, n):
            if n < 1 or n > len(self._weights):
                raise ValueError("n must be between 1 and the number of nodes")
            start = self._start(key)
            found = []
            for step in range(len(self._points)):
                node = self._points[(start + step) % len(self._points)][1]
                if node not in found:
                    found.append(node)
                    if len(found) == n:
                        break
            return found

        def shares(self):
            if not self._points:
                return {}
            owned = {node: 0 for node in self._weights}
            prev = self._points[-1][0] - SPACE
            for pos, node in self._points:
                owned[node] += pos - prev
                prev = pos
            return {node: Fraction(v, SPACE) for node, v in owned.items()}

        def moved(self, keys, other):
            return [k for k in keys if self.lookup(k) != other.lookup(k)]
''')

KEYRING_VISIBLE = dd('''
    import unittest

    from keyring.ring import Ring, hash32


    class BasicTests(unittest.TestCase):
        def test_hash_vector(self):
            self.assertEqual(hash32(""), 2166136261)

        def test_lookup_with_one_node(self):
            r = Ring()
            r.add("only")
            self.assertEqual(r.lookup("anything"), "only")


    if __name__ == "__main__":
        unittest.main()
''')

KEYRING_HIDDEN = dd('''
    import unittest
    from fractions import Fraction as F

    from keyring.ring import SPACE, Ring, hash32

    TABLE = {
        "A#0": 10, "A#1": 60, "B#0": 30, "B#1": 90, "C#0": 50, "C#1": 70,
        "k1": 5, "k2": 10, "k3": 11, "k4": 31, "k5": 60, "k6": 61, "k7": 71, "k8": 91, "k9": SPACE - 1,
    }


    def table_ring(vnodes=2, nodes="ABC"):
        r = Ring(vnodes=vnodes, hash_fn=lambda s: TABLE[s])
        for n in nodes:
            r.add(n)
        return r


    class Hash(unittest.TestCase):
        def test_vectors(self):
            self.assertEqual(hash32(""), 2166136261)
            self.assertEqual(hash32("a"), 3826002220)
            self.assertEqual(hash32("foobar"), 3214735720)

        def test_range_and_unicode(self):
            for text in ("x", "hello world", "\\u00e9\\u4e2d", "k" * 500):
                self.assertTrue(0 <= hash32(text) < SPACE)
            self.assertNotEqual(hash32("\\u00e9"), hash32("e"))
            self.assertEqual(hash32("\\u00e9"), hash32(b"\\xc3\\xa9".decode("utf-8")))


    class Construction(unittest.TestCase):
        def test_validation(self):
            with self.assertRaises(ValueError):
                Ring(vnodes=0)
            r = Ring()
            r.add("a")
            with self.assertRaises(ValueError):
                r.add("a")
            with self.assertRaises(ValueError):
                r.add("b", weight=0)
            with self.assertRaises(KeyError):
                r.remove("zzz")
            self.assertEqual(r.nodes(), ["a"])

        def test_default_vnodes(self):
            seen = []
            r = Ring(hash_fn=lambda s: seen.append(s) or 0)
            r.add("a")
            self.assertEqual(sorted(seen), sorted(f"a#{i}" for i in range(8)))
            del seen[:]
            r.add("b", weight=3)
            self.assertEqual(sorted(seen), sorted(f"b#{i}" for i in range(24)))

        def test_nodes_sorted_and_remove(self):
            r = Ring()
            for n in ("m", "c", "x"):
                r.add(n)
            self.assertEqual(r.nodes(), ["c", "m", "x"])
            r.remove("m")
            self.assertEqual(r.nodes(), ["c", "x"])
            r.add("m")
            self.assertEqual(r.nodes(), ["c", "m", "x"])

        def test_empty_ring(self):
            r = Ring()
            with self.assertRaises(ValueError):
                r.lookup("k")
            with self.assertRaises(ValueError):
                r.replicas("k", 1)
            self.assertEqual(r.shares(), {})
            self.assertEqual(r.nodes(), [])


    class Lookup(unittest.TestCase):
        def test_table(self):
            r = table_ring()
            got = {k: r.lookup(k) for k in ("k1", "k2", "k3", "k4", "k5", "k6", "k7", "k8", "k9")}
            self.assertEqual(got, {
                "k1": "A", "k2": "A", "k3": "B", "k4": "C", "k5": "A", "k6": "C", "k7": "B", "k8": "A", "k9": "A",
            })

        def test_remove_moves_only_its_keys(self):
            r = table_ring()
            r.remove("B")
            self.assertEqual(r.nodes(), ["A", "C"])
            self.assertEqual(r.lookup("k3"), "C")
            self.assertEqual(r.lookup("k7"), "A")
            self.assertEqual(r.lookup("k4"), "C")
            self.assertEqual(r.lookup("k6"), "C")
            self.assertEqual(r.lookup("k1"), "A")

        def test_weight_multiplies_points(self):
            t = dict(TABLE)
            t.update({"D#0": 20, "D#1": 40, "D#2": 80, "D#3": 85})
            r = Ring(vnodes=2, hash_fn=lambda s: t[s])
            for n in "ABC":
                r.add(n)
            r.add("D", weight=2)
            self.assertEqual(r.lookup("k3"), "D")     # 11 -> D#0 at 20 (it was B at 30)
            t["k7"] = 81
            self.assertEqual(r.lookup("k7"), "D")     # D#3 at 85
            t["k7"] = 86
            self.assertEqual(r.lookup("k7"), "B")     # B#1 at 90
            t["k7"] = 41
            self.assertEqual(r.lookup("k7"), "C")     # C#0 at 50

        def test_equal_positions_prefer_the_smaller_name(self):
            t = {"A#0": 10, "B#0": 10, "k": 4, "j": 10, "z": 11}
            for order in ("AB", "BA"):
                r = Ring(vnodes=1, hash_fn=lambda s: t[s])
                for n in order:
                    r.add(n)
                self.assertEqual(r.lookup("k"), "A")
                self.assertEqual(r.lookup("j"), "A")
                self.assertEqual(r.lookup("z"), "A")

        def test_real_hash_is_consistent(self):
            keys = [f"user:{i}" for i in range(300)]
            r = Ring(vnodes=16)
            for n in ("n1", "n2", "n3"):
                r.add(n)
            before = {k: r.lookup(k) for k in keys}
            self.assertEqual(set(before.values()), {"n1", "n2", "n3"})
            r.add("n4")
            after = {k: r.lookup(k) for k in keys}
            moved = [k for k in keys if before[k] != after[k]]
            self.assertTrue(moved)
            self.assertTrue(all(after[k] == "n4" for k in moved))
            r.remove("n4")
            self.assertEqual({k: r.lookup(k) for k in keys}, before)
            r.remove("n2")
            final = {k: r.lookup(k) for k in keys}
            for k in keys:
                if before[k] != "n2":
                    self.assertEqual(final[k], before[k])
                else:
                    self.assertIn(final[k], ("n1", "n3"))


    class Replicas(unittest.TestCase):
        def test_walk(self):
            r = table_ring()
            self.assertEqual(r.replicas("k3", 3), ["B", "C", "A"])
            self.assertEqual(r.replicas("k3", 1), ["B"])
            self.assertEqual(r.replicas("k7", 2), ["B", "A"])
            self.assertEqual(r.replicas("k4", 3), ["C", "A", "B"])
            self.assertEqual(r.replicas("k8", 3), ["A", "B", "C"])
            self.assertEqual(r.replicas("k9", 2), ["A", "B"])
            self.assertEqual(r.replicas("k2", 2), ["A", "B"])

        def test_first_replica_is_the_owner(self):
            r = Ring(vnodes=8)
            for n in ("a", "b", "c", "d"):
                r.add(n)
            for i in range(60):
                k = f"key{i}"
                reps = r.replicas(k, 3)
                self.assertEqual(reps[0], r.lookup(k))
                self.assertEqual(len(set(reps)), 3)
                self.assertEqual(r.replicas(k, 4)[:3], reps)

        def test_errors(self):
            r = table_ring()
            for n in (0, -1, 4):
                with self.assertRaises(ValueError):
                    r.replicas("k3", n)
            r.remove("C")
            with self.assertRaises(ValueError):
                r.replicas("k3", 3)
            self.assertEqual(r.replicas("k3", 2), ["B", "A"])


    class Shares(unittest.TestCase):
        def test_table_shares(self):
            r = table_ring()
            s = r.shares()
            self.assertEqual(s, {"A": F(SPACE - 70, SPACE), "B": F(40, SPACE), "C": F(30, SPACE)})
            self.assertEqual(sum(s.values()), 1)

        def test_after_remove(self):
            r = table_ring()
            r.remove("B")
            self.assertEqual(r.shares(), {"A": F(SPACE - 50, SPACE), "C": F(50, SPACE)})

        def test_equal_positions_give_zero_to_the_second(self):
            t = {"A#0": 10, "B#0": 10, "C#0": 20}
            r = Ring(vnodes=1, hash_fn=lambda s: t[s])
            for n in "ABC":
                r.add(n)
            self.assertEqual(r.shares(), {"A": F(SPACE - 10, SPACE), "B": F(0), "C": F(10, SPACE)})

        def test_single_node_owns_everything(self):
            r = Ring(vnodes=3)
            r.add("solo")
            self.assertEqual(r.shares(), {"solo": F(1)})

        def test_real_hash_sums_to_one(self):
            r = Ring(vnodes=32)
            for n, w in (("x", 1), ("y", 2), ("z", 1)):
                r.add(n, w)
            s = r.shares()
            self.assertEqual(sum(s.values()), 1)
            self.assertEqual(sorted(s), ["x", "y", "z"])
            self.assertTrue(all(v > 0 for v in s.values()))


    class Moved(unittest.TestCase):
        def test_moved(self):
            a = table_ring()
            b = table_ring()
            b.remove("B")
            self.assertEqual(a.moved(["k1", "k3", "k5", "k7", "k4"], b), ["k3", "k7"])
            self.assertEqual(a.moved(["k7", "k3"], b), ["k7", "k3"])
            self.assertEqual(a.moved([], b), [])
            self.assertEqual(a.moved(["k1", "k2"], a), [])


    if __name__ == "__main__":
        unittest.main()
''')

KEYRING = Lib(
    name="keyring", lang="python", title="the keyring consistent-hash ring (`keyring/ring.py`)",
    blurb="The cache cluster uses keyring to decide which node owns a key and which nodes hold its replicas.",
    files={"keyring/__init__.py": "", "keyring/ring.py": KEYRING_SRC, "README.md": KEYRING_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": KEYRING_VISIBLE},
    hidden_tests={"tests/test_full.py": KEYRING_HIDDEN},
    mutate=["keyring/ring.py"], difficulty=2, tags=["hashing", "cluster"],
    probes=[
        "hash32('a')", "hash32('foobar')",
        chain("Ring(vnodes=4)", ["add('a')", "add('b')", "add('c', 2)", "lookup('user:1')", "lookup('user:2')", "lookup('user:3')", "lookup('user:4')", "lookup('user:5')"]),
        chain("Ring(vnodes=4)", ["add('a')", "add('b')", "add('c')", "replicas('user:3', 2)", "replicas('user:9', 3)"]),
        chain("Ring(vnodes=2)", ["add('a')", "add('b')", "shares()"]),
        chain("Ring(vnodes=2)", ["add('a')", "add('b')", "remove('a')", "nodes()", "lookup('user:7')"]),
    ],
    probe_import="from keyring.ring import Ring, hash32\n",
)

# ======================================================================================================================
# latbuckets: exponential latency histogram
# ======================================================================================================================

LATBUCKETS_README = dd('''
    # latbuckets

    Latency histograms with exponential bucket boundaries, as used by a service's metrics endpoint. Values are
    non-negative integers (microseconds).

    ## `exp_bounds(first, factor, count) -> list[int]`

    `count` boundaries `first, first*factor, first*factor**2, ...`. `ValueError` if `first < 1`, `factor < 2` or
    `count < 1`.

    ## `Histogram(bounds)`

    `bounds` must be a non-empty, strictly increasing list of integers, otherwise `ValueError`. With `k` bounds there
    are `k + 1` buckets: bucket `0` holds values below `bounds[0]`, bucket `i` holds `bounds[i-1] <= v < bounds[i]`,
    and the last bucket (the overflow bucket) holds `v >= bounds[-1]`.

    * `counts`: list of the `k + 1` bucket counts; `total`: the number of recorded values.
    * `bucket_of(v) -> int`: the bucket index for a value (`ValueError` for a negative value).
    * `add(v, n=1)`: record `n` occurrences of `v`. `ValueError` if `n < 1` or `v` is negative.
    * `percentile(p) -> int | float`: nearest-rank percentile resolved to a bucket: take rank
      `max(1, ceil(p * total / 100))`, find the bucket in which the cumulative count first reaches that rank and
      return that bucket's **upper bound** (`bounds[i]`); for the overflow bucket return `float("inf")`. `p` is an
      integer from 0 to 100 (`ValueError` otherwise) and the histogram must not be empty (`ValueError`).
    * `merge(other) -> Histogram`: a new histogram with the counts of both added; `ValueError` unless both have the
      same bounds. Neither input changes.
    * `render(width=20) -> str`: one line per bucket, joined with `"\\n"`: the label right-aligned to width 10, a
      space, the bar left-aligned in `width` columns, a space and the count. Labels: `<B0` for bucket 0 (B0 is
      `bounds[0]`), `lo-hi` for a middle bucket where `hi` is its upper bound minus one (`bounds[i]-1`), `>=Bk` for the
      overflow bucket. The bar has `ceil(count * width / max_count)` `#` characters, none for an empty bucket
      (`max_count` is the largest bucket count; when everything is empty there are no bars). The lines carry no
      trailing spaces.
''')

LATBUCKETS_SRC = dd('''
    """Exponential latency histogram."""
    import bisect


    def exp_bounds(first, factor, count):
        if first < 1 or factor < 2 or count < 1:
            raise ValueError("first >= 1, factor >= 2 and count >= 1 are required")
        out = []
        b = first
        for _ in range(count):
            out.append(b)
            b *= factor
        return out


    class Histogram:
        def __init__(self, bounds):
            bounds = list(bounds)
            if not bounds or any(b <= a for a, b in zip(bounds, bounds[1:])):
                raise ValueError("bounds must be non-empty and strictly increasing")
            self.bounds = bounds
            self.counts = [0] * (len(bounds) + 1)
            self.total = 0

        def bucket_of(self, v):
            if v < 0:
                raise ValueError("negative value")
            return bisect.bisect_right(self.bounds, v)

        def add(self, v, n=1):
            if n < 1:
                raise ValueError("n must be at least 1")
            self.counts[self.bucket_of(v)] += n
            self.total += n

        def percentile(self, p):
            if not isinstance(p, int) or p < 0 or p > 100:
                raise ValueError("p must be an integer from 0 to 100")
            if self.total == 0:
                raise ValueError("empty histogram")
            rank = max(1, -(-p * self.total // 100))
            seen = 0
            for i, c in enumerate(self.counts):
                seen += c
                if seen >= rank:
                    return self.bounds[i] if i < len(self.bounds) else float("inf")

        def merge(self, other):
            if self.bounds != other.bounds:
                raise ValueError("different bounds")
            out = Histogram(self.bounds)
            out.counts = [a + b for a, b in zip(self.counts, other.counts)]
            out.total = self.total + other.total
            return out

        def _label(self, i):
            if i == 0:
                return f"<{self.bounds[0]}"
            if i == len(self.bounds):
                return f">={self.bounds[-1]}"
            return f"{self.bounds[i - 1]}-{self.bounds[i] - 1}"

        def render(self, width=20):
            top = max(self.counts)
            lines = []
            for i, c in enumerate(self.counts):
                bar = "#" * (-(-c * width // top) if top else 0)
                lines.append(f"{self._label(i):>10} {bar:<{width}} {c}")
            return "\\n".join(lines)
''')

LATBUCKETS_VISIBLE = dd('''
    import unittest

    from latbuckets.hist import Histogram, exp_bounds


    class BasicTests(unittest.TestCase):
        def test_bounds(self):
            self.assertEqual(exp_bounds(10, 2, 4), [10, 20, 40, 80])

        def test_add(self):
            h = Histogram([10, 20])
            h.add(5)
            h.add(15)
            self.assertEqual(h.counts, [1, 1, 0])


    if __name__ == "__main__":
        unittest.main()
''')

LATBUCKETS_HIDDEN = dd('''
    import unittest

    from latbuckets.hist import Histogram, exp_bounds


    class Bounds(unittest.TestCase):
        def test_values(self):
            self.assertEqual(exp_bounds(1, 2, 5), [1, 2, 4, 8, 16])
            self.assertEqual(exp_bounds(100, 10, 3), [100, 1000, 10000])
            self.assertEqual(exp_bounds(5, 3, 1), [5])
            self.assertEqual(exp_bounds(7, 2, 2), [7, 14])

        def test_errors(self):
            for args in ((0, 2, 3), (-1, 2, 3), (5, 1, 3), (5, 0, 3), (5, 2, 0), (5, 2, -1)):
                with self.assertRaises(ValueError):
                    exp_bounds(*args)


    class Construction(unittest.TestCase):
        def test_bounds_validation(self):
            for bad in ([], [5, 5], [10, 5], [1, 2, 2, 3], (3, 2)):
                with self.assertRaises(ValueError):
                    Histogram(bad)
            h = Histogram((1, 2, 3))
            self.assertEqual(h.bounds, [1, 2, 3])
            self.assertEqual(h.counts, [0, 0, 0, 0])
            self.assertEqual(h.total, 0)
            Histogram([0])

        def test_bounds_are_copied(self):
            src = [10, 20]
            h = Histogram(src)
            src.append(30)
            self.assertEqual(h.bounds, [10, 20])
            self.assertEqual(len(h.counts), 3)


    class Bucketing(unittest.TestCase):
        def test_bucket_of(self):
            h = Histogram([10, 20, 40])
            got = [h.bucket_of(v) for v in (0, 9, 10, 11, 19, 20, 39, 40, 41, 10 ** 9)]
            self.assertEqual(got, [0, 0, 1, 1, 1, 2, 2, 3, 3, 3])

        def test_negative(self):
            h = Histogram([10])
            with self.assertRaises(ValueError):
                h.bucket_of(-1)
            with self.assertRaises(ValueError):
                h.add(-5)
            self.assertEqual(h.total, 0)

        def test_add_counts(self):
            h = Histogram([10, 20, 40])
            h.add(5)
            h.add(10, n=3)
            h.add(25, 2)
            h.add(100)
            self.assertEqual(h.counts, [1, 3, 2, 1])
            self.assertEqual(h.total, 7)
            for n in (0, -1):
                with self.assertRaises(ValueError):
                    h.add(5, n)
            self.assertEqual(h.total, 7)

        def test_zero_bound(self):
            h = Histogram([0, 5])
            h.add(0)
            h.add(3)
            self.assertEqual(h.counts, [0, 2, 0])


    class Percentiles(unittest.TestCase):
        def hist(self):
            h = Histogram([10, 20, 40, 80])
            for v, n in ((5, 4), (15, 3), (30, 2), (70, 1)):
                h.add(v, n)
            return h   # counts [4, 3, 2, 1, 0], total 10

        def test_ranks(self):
            h = self.hist()
            self.assertEqual(h.percentile(0), 10)
            self.assertEqual(h.percentile(10), 10)
            self.assertEqual(h.percentile(40), 10)
            self.assertEqual(h.percentile(41), 20)
            self.assertEqual(h.percentile(70), 20)
            self.assertEqual(h.percentile(71), 40)
            self.assertEqual(h.percentile(90), 40)
            self.assertEqual(h.percentile(91), 80)
            self.assertEqual(h.percentile(100), 80)

        def test_overflow_is_infinite(self):
            h = self.hist()
            h.add(500)
            self.assertEqual(h.total, 11)
            self.assertEqual(h.percentile(90), 80)
            self.assertEqual(h.percentile(100), float("inf"))
            h2 = Histogram([10])
            h2.add(10)
            self.assertEqual(h2.percentile(1), float("inf"))

        def test_large_totals(self):
            h = Histogram([10])
            h.add(1, 100)
            h.add(50)
            self.assertEqual(h.percentile(100), float("inf"))
            self.assertEqual(h.percentile(99), 10)

        def test_total_matters(self):
            h = Histogram([10, 20])
            h.add(5, 99)
            h.add(15)
            self.assertEqual(h.percentile(99), 10)
            self.assertEqual(h.percentile(100), 20)

        def test_single_value(self):
            h = Histogram([10, 20])
            h.add(12)
            for p in (0, 1, 50, 100):
                self.assertEqual(h.percentile(p), 20)

        def test_errors(self):
            h = self.hist()
            for p in (-1, 101, 50.5, "50"):
                with self.assertRaises(ValueError):
                    h.percentile(p)
            with self.assertRaises(ValueError):
                Histogram([10]).percentile(50)


    class Merge(unittest.TestCase):
        def test_merge(self):
            a, b = Histogram([10, 20]), Histogram([10, 20])
            a.add(5, 2)
            a.add(15)
            b.add(15, 3)
            b.add(99)
            m = a.merge(b)
            self.assertEqual(m.counts, [2, 4, 1])
            self.assertEqual(m.total, 7)
            self.assertEqual(a.counts, [2, 1, 0])
            self.assertEqual(b.counts, [0, 3, 1])
            self.assertEqual((a.total, b.total), (3, 4))
            self.assertIsNot(m, a)
            m.add(1)
            self.assertEqual(a.counts[0], 2)

        def test_merge_mismatch(self):
            with self.assertRaises(ValueError):
                Histogram([10, 20]).merge(Histogram([10, 30]))
            with self.assertRaises(ValueError):
                Histogram([10, 20]).merge(Histogram([10, 20, 40]))


    class Render(unittest.TestCase):
        def test_render(self):
            h = Histogram([10, 20, 40])
            for v, n in ((5, 4), (15, 1), (30, 2)):
                h.add(v, n)
            expected = "\\n".join([
                "       <10 ################ 4",
                "     10-19 ####             1",
                "     20-39 ########         2",
                "      >=40                  0",
            ])
            self.assertEqual(h.render(16), expected)

        def test_bar_rounds_up(self):
            h = Histogram([10])
            h.add(1, 100)
            h.add(50, 1)
            lines = h.render(20).split("\\n")
            self.assertEqual(lines[0], "       <10 " + "#" * 20 + " 100")
            self.assertEqual(lines[1], "      >=10 " + "#" + " " * 19 + " 1")

        def test_empty_histogram(self):
            h = Histogram([10, 20])
            self.assertEqual(h.render(4), "\\n".join(["       <10      0", "     10-19      0", "      >=20      0"]))

        def test_default_width_and_long_labels(self):
            h = Histogram([1000, 20000, 300000])
            h.add(5)
            lines = h.render().split("\\n")
            self.assertEqual(lines[0], "     <1000 " + "#" * 20 + " 1")
            self.assertEqual(lines[1], "1000-19999 " + " " * 20 + " 0")
            self.assertEqual(lines[2], "20000-299999 " + " " * 20 + " 0")
            self.assertEqual(lines[3], "  >=300000 " + " " * 20 + " 0")
            self.assertEqual(len(lines), 4)


    if __name__ == "__main__":
        unittest.main()
''')

LATBUCKETS = Lib(
    name="latbuckets", lang="python", title="the latbuckets latency histogram (`latbuckets/hist.py`)",
    blurb="The metrics endpoint of the API gateway uses latbuckets to turn request latencies into histograms and percentiles.",
    files={"latbuckets/__init__.py": "", "latbuckets/hist.py": LATBUCKETS_SRC, "README.md": LATBUCKETS_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": LATBUCKETS_VISIBLE},
    hidden_tests={"tests/test_full.py": LATBUCKETS_HIDDEN},
    mutate=["latbuckets/hist.py"], difficulty=2, tags=["histogram", "metrics"],
    probes=[
        "exp_bounds(100, 10, 3)",
        chain("Histogram([10, 20, 40])", ["bucket_of(9)", "bucket_of(10)", "bucket_of(39)", "bucket_of(40)"]),
        chain("Histogram([10, 20, 40, 80])", ["add(5, 4)", "add(15, 3)", "add(30, 2)", "add(70, 1)", "percentile(41)", "percentile(91)", "percentile(100)"]),
        chain("Histogram([10, 20])", ["add(5, 99)", "add(15)", "percentile(99)", "percentile(100)"]),
        chain("Histogram([10])", ["add(1, 100)", "add(50, 1)", "render(10)"]),
        chain("Histogram([10, 20, 40])", ["add(5, 4)", "add(15)", "add(30, 2)", "render(16)"]),
        chain("Histogram([10, 20])", ["add(5, 2)", "merge(Histogram([10, 20]))", "counts"]),
    ],
    probe_import="from latbuckets.hist import Histogram, exp_bounds\n",
)

LIBS = [EDGECACHE, GARDENSTATS, KEYRING, LATBUCKETS]
register_libs3(LIBS, n=10)
