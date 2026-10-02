"""Stale caches and invalidation: a TTL price cache (python) and a memoised permission resolver (javascript)."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): a price service with a TTL cache in front of a store, on a fake clock.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # pricing

    A price lookup service for a shop with per-region prices (cents). Reads go through a small TTL cache.

    * `Store` is the source of truth: `get(sku, region)` (counts every call in `store.reads`), `set`, `bulk_set`,
      `rename(old, new)` (moves every region of a sku), `regions(sku)`.
    * `TTLCache(clock, ttl)`: an entry is valid for strictly less than `ttl` seconds: at age exactly `ttl` it is
      expired. `FakeClock.advance(seconds)` is how tests move time.
    * `PriceService(store, clock, ttl=60)`:
      * `price(sku, region)`: the price in cents or `None` for an unknown sku. Results are cached **per
        (sku, region)**, and a `None` is cached too, so repeated lookups of a missing sku read the store once.
      * `set_price(sku, region, cents)` and `import_prices({(sku, region): cents})` write to the store and make the
        change visible to the next `price` call at once (only the affected entries are dropped).
      * `rename_sku(old, new)`: after it, `price(new, r)` is the old price in every region `r` that `old` had and
        `price(old, r)` is `None`, immediately, whatever was cached before (including a cached `None` for `new`).
      * `prices_for(sku)`: `{region: cents}` for the regions the store has for that sku, read through `price`.
''')

A_CLOCK = dd('''
    class FakeClock:
        def __init__(self, start=1000.0):
            self.now = start

        def time(self):
            return self.now

        def advance(self, seconds):
            self.now += seconds
''')

A_STORE = dd('''
    class Store:
        """Source of truth: cents per (sku, region). Counts reads so tests can tell a cache hit from a read."""

        def __init__(self, rows=None):
            self._rows = dict(rows or {})
            self.reads = 0

        def get(self, sku, region):
            self.reads += 1
            return self._rows.get((sku, region))

        def set(self, sku, region, cents):
            self._rows[(sku, region)] = cents

        def bulk_set(self, rows):
            self._rows.update(rows)

        def regions(self, sku):
            return sorted(r for (s, r) in self._rows if s == sku)

        def rename(self, old, new):
            for region in self.regions(old):
                self._rows[(new, region)] = self._rows.pop((old, region))
''')

A_CACHE = dd('''
    class TTLCache:
        def __init__(self, clock, ttl):
            self.clock = clock
            self.ttl = ttl
            self._data = {}

        def get(self, key, default=None):
            hit = self._data.get(key)
            if hit is None:
                return default
            stored_at, value = hit
            if self.clock.time() - stored_at >= self.ttl:
                del self._data[key]
                return default
            return value

        def put(self, key, value):
            self._data[key] = (self.clock.time(), value)

        def drop(self, key):
            self._data.pop(key, None)
''')

A_SERVICE = dd('''
    from .cache import TTLCache

    _MISS = object()


    class PriceService:
        def __init__(self, store, clock, ttl=60):
            self.store = store
            self.cache = TTLCache(clock, ttl)

        @staticmethod
        def _key(sku, region):
            return (sku, region)

        def price(self, sku, region):
            key = self._key(sku, region)
            value = self.cache.get(key, _MISS)
            if value is not _MISS:
                return value
            value = self.store.get(sku, region)
            self.cache.put(key, value)
            return value

        def set_price(self, sku, region, cents):
            self.store.set(sku, region, cents)
            self.cache.drop(self._key(sku, region))

        def import_prices(self, rows):
            self.store.bulk_set(rows)
            for sku, region in rows:
                self.cache.drop(self._key(sku, region))

        def rename_sku(self, old, new):
            regions = self.store.regions(old)
            self.store.rename(old, new)
            for region in regions:
                self.cache.drop(self._key(old, region))
                self.cache.drop(self._key(new, region))

        def prices_for(self, sku):
            return {r: self.price(sku, r) for r in self.store.regions(sku)}
''')

A_VISIBLE = {
    "tests/test_service.py": dd('''
        import unittest

        from pricing.cache import TTLCache
        from pricing.clock import FakeClock
        from pricing.service import PriceService
        from pricing.store import Store


        class ServiceTests(unittest.TestCase):
            def setUp(self):
                self.clock = FakeClock()
                self.store = Store({("tea", "eu"): 450, ("tea", "us"): 399})
                self.svc = PriceService(self.store, self.clock, ttl=60)

            def test_reads_through_and_caches(self):
                self.assertEqual(self.svc.price("tea", "eu"), 450)
                self.assertEqual(self.svc.price("tea", "eu"), 450)
                self.assertEqual(self.store.reads, 1)

            def test_expires_after_ttl(self):
                self.svc.price("tea", "eu")
                self.clock.advance(120)
                self.svc.price("tea", "eu")
                self.assertEqual(self.store.reads, 2)

            def test_cache_drop(self):
                c = TTLCache(self.clock, 10)
                c.put("k", 1)
                c.drop("k")
                self.assertIsNone(c.get("k"))


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_service.py": dd('''
        import unittest

        from pricing.clock import FakeClock
        from pricing.service import PriceService
        from pricing.store import Store


        def make(rows=None, ttl=60):
            clock = FakeClock()
            store = Store(rows if rows is not None else {("tea", "eu"): 450, ("tea", "us"): 399, ("mug", "eu"): 1200})
            return PriceService(store, clock, ttl=ttl), store, clock


        class ReadThrough(unittest.TestCase):
            def test_regions_are_separate_entries(self):
                svc, store, _ = make()
                self.assertEqual(svc.price("tea", "eu"), 450)
                self.assertEqual(svc.price("tea", "us"), 399)
                self.assertEqual(svc.price("tea", "eu"), 450)
                self.assertEqual(svc.price("tea", "us"), 399)
                self.assertEqual(store.reads, 2)

            def test_ttl_boundary(self):
                svc, store, clock = make(ttl=60)
                svc.price("tea", "eu")
                clock.advance(59.5)
                svc.price("tea", "eu")
                self.assertEqual(store.reads, 1)
                clock.advance(0.5)  # age is exactly ttl: expired
                svc.price("tea", "eu")
                self.assertEqual(store.reads, 2)

            def test_expiry_sees_a_direct_store_change(self):
                svc, store, clock = make()
                self.assertEqual(svc.price("mug", "eu"), 1200)
                store.set("mug", "eu", 1300)
                self.assertEqual(svc.price("mug", "eu"), 1200)
                clock.advance(61)
                self.assertEqual(svc.price("mug", "eu"), 1300)

            def test_missing_prices_are_cached_too(self):
                svc, store, clock = make()
                for _ in range(4):
                    self.assertIsNone(svc.price("ghost", "eu"))
                self.assertEqual(store.reads, 1)
                clock.advance(60)
                self.assertIsNone(svc.price("ghost", "eu"))
                self.assertEqual(store.reads, 2)

            def test_zero_price_is_a_value_not_a_miss(self):
                svc, store, _ = make({("freebie", "eu"): 0})
                self.assertEqual(svc.price("freebie", "eu"), 0)
                self.assertEqual(svc.price("freebie", "eu"), 0)
                self.assertEqual(store.reads, 1)


        class Writes(unittest.TestCase):
            def test_set_price_is_visible_at_once(self):
                svc, store, _ = make()
                self.assertEqual(svc.price("tea", "eu"), 450)
                svc.set_price("tea", "eu", 480)
                self.assertEqual(svc.price("tea", "eu"), 480)

            def test_set_price_replaces_a_cached_miss(self):
                svc, store, _ = make()
                self.assertIsNone(svc.price("cake", "eu"))
                svc.set_price("cake", "eu", 250)
                self.assertEqual(svc.price("cake", "eu"), 250)

            def test_set_price_only_drops_its_own_entry(self):
                svc, store, _ = make()
                svc.price("tea", "eu")
                svc.price("tea", "us")
                reads = store.reads
                svc.set_price("tea", "eu", 500)
                self.assertEqual(svc.price("tea", "us"), 399)
                self.assertEqual(store.reads, reads)
                self.assertEqual(svc.price("tea", "eu"), 500)
                self.assertEqual(store.reads, reads + 1)

            def test_import_prices_is_visible_at_once(self):
                svc, store, _ = make()
                svc.price("tea", "eu")
                svc.price("mug", "eu")
                self.assertIsNone(svc.price("pot", "eu"))
                svc.import_prices({("tea", "eu"): 460, ("pot", "eu"): 2200})
                self.assertEqual(svc.price("tea", "eu"), 460)
                self.assertEqual(svc.price("pot", "eu"), 2200)
                self.assertEqual(svc.price("mug", "eu"), 1200)


        class Renames(unittest.TestCase):
            def test_rename_moves_prices(self):
                svc, store, _ = make()
                self.assertEqual(svc.price("tea", "eu"), 450)
                self.assertEqual(svc.price("tea", "us"), 399)
                svc.rename_sku("tea", "chai")
                self.assertEqual(svc.price("chai", "eu"), 450)
                self.assertEqual(svc.price("chai", "us"), 399)
                self.assertIsNone(svc.price("tea", "eu"))
                self.assertIsNone(svc.price("tea", "us"))

            def test_rename_beats_a_cached_miss_for_the_new_name(self):
                svc, store, _ = make()
                self.assertIsNone(svc.price("chai", "eu"))
                self.assertIsNone(svc.price("chai", "us"))
                svc.rename_sku("tea", "chai")
                self.assertEqual(svc.price("chai", "eu"), 450)
                self.assertEqual(svc.price("chai", "us"), 399)

            def test_rename_when_nothing_was_cached(self):
                svc, store, _ = make()
                svc.rename_sku("mug", "cup")
                self.assertEqual(svc.price("cup", "eu"), 1200)

            def test_prices_for(self):
                svc, store, _ = make()
                self.assertEqual(svc.prices_for("tea"), {"eu": 450, "us": 399})
                self.assertEqual(svc.prices_for("nothing"), {})
                reads = store.reads
                svc.prices_for("tea")
                self.assertEqual(store.reads, reads)


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["region-key"] = (
        "Bug bash item: customers in the US shop sometimes see the EU price. It seems to depend on who looked at the product "
        "first after a deploy. The price rows in the store are right (we checked), so I suspect the lookup layer."
    )
    p["ttl-edge"] = (
        "Our contract with the price feed says an entry may be served for *less than* `ttl` seconds and must be re-read at "
        "exactly `ttl`. The cache keeps serving it for one more tick. Not a big deal in production, but the new SLA "
        "check on the replay harness fails. `pricing/cache.py`."
    )
    p["negative"] = lambda c: (
        "Load test result: lookups for unknown SKUs (typos, discontinued products) hammer the store, about one read per request "
        "even though the README says misses are cached. Reads for 4 lookups of a missing sku: "
        + c.probe("from pricing.service import PriceService\nfrom pricing.store import Store\nfrom pricing.clock import FakeClock\n"
                  "st = Store({})\nsv = PriceService(st, FakeClock())\nfor _ in range(4):\n    sv.price('ghost', 'eu')\nprint(st.reads)\n")[1]
        + ", expected 1."
    )
    p["import-stale"] = (
        "After the nightly CSV import the storefront keeps showing yesterday's prices for up to a minute, but prices edited "
        "one by one through the admin screen show up immediately. Both paths are supposed to be visible at once."
    )
    p["rename-new"] = (
        "ticket SHOP-731: we renamed `tea` to `chai`. Search results for `chai` were looked up before the rename (the product page "
        "had been linked from a newsletter), and now `chai` shows \"no price\" for a minute even though the rename went "
        "through. `tea` is correctly gone. I'd expect the cache to be cleaned for both names."
    )
    p["two-paths"] = (
        "Prices look stale after bulk changes and after SKU renames, and the TTL of 60 seconds is the obvious suspect, so someone "
        "lowered it to 5 in staging. That helped a bit but did not fix it: the stale value now lives for 5 seconds. "
        "Don't touch the TTL; find out why changes do not show up at once."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "pricing/__init__.py": '"""Price lookup."""\n', "pricing/clock.py": A_CLOCK, "pricing/store.py": A_STORE,
            "pricing/cache.py": A_CACHE, "pricing/service.py": A_SERVICE}
    sv, ca = "pricing/service.py", "pricing/cache.py"
    imp = ("        self.store.bulk_set(rows)\n        for sku, region in rows:\n            self.cache.drop(self._key(sku, region))\n",
           "        self.store.bulk_set(rows)\n")
    ren = ("            self.cache.drop(self._key(old, region))\n            self.cache.drop(self._key(new, region))\n",
           "            self.cache.drop(self._key(old, region))\n")
    bugs = [
        Bug("key-omits-region", 2, {sv: [("        return (sku, region)\n", "        return sku\n")]}, P["region-key"]),
        Bug("ttl-boundary-inclusive", 2, {ca: [("        if self.clock.time() - stored_at >= self.ttl:", "        if self.clock.time() - stored_at > self.ttl:")]}, P["ttl-edge"]),
        Bug("misses-not-cached", 2, {sv: [("        value = self.cache.get(key, _MISS)\n        if value is not _MISS:\n            return value\n",
                                           "        value = self.cache.get(key)\n        if value is not None:\n            return value\n")]}, P["negative"]),
        Bug("import-skips-invalidation", 3, {sv: [imp]}, P["import-stale"]),
        Bug("rename-keeps-new-key", 4, {sv: [ren]}, P["rename-new"]),
        Bug("import-and-rename-stale", 5, {sv: [imp, ren]}, P["two-paths"]),
    ]
    return Base("pricing", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (javascript): memoised effective permissions over users, groups and nested groups.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # permcache

    Effective permissions for an admin console. `Directory` holds users and groups and emits change events;
    `Resolver` memoises `permissions(userId, tenant)` and must never serve an answer that a change has made wrong,
    while keeping entries of unaffected users cached.

    * A user has `roles` and belongs to `groups`. A group has `roles` and an optional `parent` group.
    * A role is `name` (all tenants) or `name@tenant` (only that tenant). `ROLE_PERMS` maps a role name to
      permissions; unknown roles grant nothing.
    * The permissions of a user in a tenant are those of the user's own roles plus the roles of every group the user is
      in **and of every ancestor of those groups**, filtered by tenant. An unknown user has no permissions.
    * `resolver.permissions(userId, tenant = 'default')` returns a fresh `Set` (changing it never affects later calls)
      and `resolver.computes` counts how often a result was computed rather than served from the cache.
    * Changes: a user event (`addUser`, `removeUser`, `setUserRoles`, `joinGroup`, `leaveGroup`) invalidates that user
      (all tenants). A group event (`addGroup`, `setGroupRoles`, `moveGroup`) invalidates the members of that group
      **and of all groups below it**. Nobody else is recomputed.
''')

B_ROLES = dd('''
    'use strict';

    const ROLE_PERMS = {
      viewer: ['read'],
      editor: ['read', 'write'],
      admin: ['read', 'write', 'delete', 'admin'],
      billing: ['invoice.read', 'invoice.write'],
    };

    module.exports = { ROLE_PERMS };
''')

B_DIRECTORY = dd('''
    'use strict';

    class Directory {
      constructor() {
        this.users = new Map(); // id -> { roles: Set, groups: Set }
        this.groups = new Map(); // name -> { roles: Set, parent: string | null }
        this.listeners = [];
      }

      onChange(fn) {
        this.listeners.push(fn);
      }

      emit(ev) {
        for (const fn of this.listeners) fn(ev);
      }

      addUser(id, { roles = [], groups = [] } = {}) {
        this.users.set(id, { roles: new Set(roles), groups: new Set(groups) });
        this.emit({ type: 'user', id });
      }

      removeUser(id) {
        this.users.delete(id);
        this.emit({ type: 'user', id });
      }

      setUserRoles(id, roles) {
        this.users.get(id).roles = new Set(roles);
        this.emit({ type: 'user', id });
      }

      joinGroup(id, group) {
        this.users.get(id).groups.add(group);
        this.emit({ type: 'user', id });
      }

      leaveGroup(id, group) {
        this.users.get(id).groups.delete(group);
        this.emit({ type: 'user', id });
      }

      addGroup(name, { roles = [], parent = null } = {}) {
        this.groups.set(name, { roles: new Set(roles), parent });
        this.emit({ type: 'group', name });
      }

      setGroupRoles(name, roles) {
        this.groups.get(name).roles = new Set(roles);
        this.emit({ type: 'group', name });
      }

      moveGroup(name, parent) {
        this.groups.get(name).parent = parent;
        this.emit({ type: 'group', name });
      }

      // the group and every group below it
      subtree(name) {
        const out = new Set([name]);
        let grew = true;
        while (grew) {
          grew = false;
          for (const [g, info] of this.groups) {
            if (info.parent !== null && out.has(info.parent) && !out.has(g)) {
              out.add(g);
              grew = true;
            }
          }
        }
        return out;
      }

      // the group and its ancestors, nearest first (cycles are cut)
      ancestry(name) {
        const out = [];
        const seen = new Set();
        let g = name;
        while (g && this.groups.has(g) && !seen.has(g)) {
          seen.add(g);
          out.push(g);
          g = this.groups.get(g).parent;
        }
        return out;
      }
    }

    module.exports = { Directory };
''')

B_RESOLVER = dd('''
    'use strict';
    const { ROLE_PERMS } = require('./roles');

    class Resolver {
      constructor(directory) {
        this.dir = directory;
        this.cache = new Map(); // userId -> Map(tenant -> Set)
        this.computes = 0;
        directory.onChange((ev) => this.invalidate(ev));
      }

      permissions(userId, tenant = 'default') {
        let byTenant = this.cache.get(userId);
        if (!byTenant) {
          byTenant = new Map();
          this.cache.set(userId, byTenant);
        }
        if (!byTenant.has(tenant)) byTenant.set(tenant, this.compute(userId, tenant));
        return new Set(byTenant.get(tenant));
      }

      compute(userId, tenant) {
        this.computes += 1;
        const perms = new Set();
        const user = this.dir.users.get(userId);
        if (!user) return perms;
        const roles = [...user.roles];
        for (const g of user.groups) {
          for (const anc of this.dir.ancestry(g)) roles.push(...this.dir.groups.get(anc).roles);
        }
        for (const role of roles) {
          const [name, scope] = role.split('@');
          if (scope !== undefined && scope !== tenant) continue;
          for (const p of ROLE_PERMS[name] || []) perms.add(p);
        }
        return perms;
      }

      invalidate(ev) {
        if (ev.type === 'user') {
          this.cache.delete(ev.id);
          return;
        }
        const groups = this.dir.subtree(ev.name);
        for (const [id, user] of this.dir.users) {
          for (const g of user.groups) {
            if (groups.has(g)) {
              this.cache.delete(id);
              break;
            }
          }
        }
      }
    }

    module.exports = { Resolver };
''')

B_VISIBLE = {
    "test/resolver.test.js": dd('''
        const test = require('node:test');
        const assert = require('node:assert');
        const { Directory } = require('../src/directory');
        const { Resolver } = require('../src/resolver');

        test('roles and group roles add up', () => {
          const d = new Directory();
          d.addGroup('eng', { roles: ['editor'] });
          d.addUser('ann', { roles: ['viewer'], groups: ['eng'] });
          const r = new Resolver(d);
          assert.deepStrictEqual([...r.permissions('ann')].sort(), ['read', 'write']);
        });

        test('answers are cached', () => {
          const d = new Directory();
          d.addUser('ann', { roles: ['admin'] });
          const r = new Resolver(d);
          r.permissions('ann');
          r.permissions('ann');
          assert.strictEqual(r.computes, 1);
        });

        test('a role change shows up', () => {
          const d = new Directory();
          d.addUser('ann', { roles: ['viewer'] });
          const r = new Resolver(d);
          assert.ok(!r.permissions('ann').has('write'));
          d.setUserRoles('ann', ['editor']);
          assert.ok(r.permissions('ann').has('write'));
        });
    '''),
}

B_HIDDEN = {
    "test/hidden_resolver.test.js": dd('''
        const test = require('node:test');
        const assert = require('node:assert');
        const { Directory } = require('../src/directory');
        const { Resolver } = require('../src/resolver');

        function setup() {
          const d = new Directory();
          d.addGroup('eng', { roles: ['editor'] });
          d.addGroup('backend', { roles: ['viewer'], parent: 'eng' });
          d.addGroup('ops', { roles: ['admin'] });
          d.addUser('ann', { roles: ['viewer'], groups: ['backend'] });
          d.addUser('bob', { roles: ['billing@acme'], groups: ['ops'] });
          d.addUser('cy', { roles: [], groups: [] });
          return { d, r: new Resolver(d) };
        }
        const sorted = (s) => [...s].sort();

        test('permissions follow roles, groups and ancestors', () => {
          const { r } = setup();
          assert.deepStrictEqual(sorted(r.permissions('ann')), ['read', 'write']);
          assert.deepStrictEqual(sorted(r.permissions('cy')), []);
          assert.deepStrictEqual(sorted(r.permissions('nobody')), []);
        });

        test('roles scoped to a tenant only count there, whichever tenant is asked first', () => {
          for (const order of [['acme', 'globex'], ['globex', 'acme']]) {
            const { r } = setup();
            const got = {};
            for (const t of order) got[t] = sorted(r.permissions('bob', t));
            assert.deepStrictEqual(got.acme, ['admin', 'delete', 'invoice.read', 'invoice.write', 'read', 'write']);
            assert.deepStrictEqual(got.globex, ['admin', 'delete', 'read', 'write']);
          }
        });

        test('unknown roles grant nothing', () => {
          const { d, r } = setup();
          d.setUserRoles('cy', ['wizard', 'viewer']);
          assert.deepStrictEqual(sorted(r.permissions('cy')), ['read']);
        });

        test('answers are cached per user and tenant', () => {
          const { r } = setup();
          r.permissions('ann');
          r.permissions('ann');
          r.permissions('ann', 'acme');
          r.permissions('ann', 'acme');
          assert.strictEqual(r.computes, 2);
        });

        test('the returned set is a copy', () => {
          const { r } = setup();
          const s = r.permissions('ann');
          s.add('hack');
          s.delete('read');
          assert.deepStrictEqual(sorted(r.permissions('ann')), ['read', 'write']);
        });

        test('user changes are visible at once', () => {
          const { d, r } = setup();
          r.permissions('cy');
          d.setUserRoles('cy', ['admin']);
          assert.ok(r.permissions('cy').has('delete'));
          d.joinGroup('cy', 'ops');
          d.setUserRoles('cy', []);
          assert.ok(r.permissions('cy').has('admin'));
          d.leaveGroup('cy', 'ops');
          assert.deepStrictEqual(sorted(r.permissions('cy')), []);
        });

        test('a removed user loses everything, and a new user with the same id starts clean', () => {
          const { d, r } = setup();
          assert.ok(r.permissions('bob').has('admin'));
          d.removeUser('bob');
          assert.deepStrictEqual(sorted(r.permissions('bob')), []);
          d.addUser('bob', { roles: ['viewer'] });
          assert.deepStrictEqual(sorted(r.permissions('bob')), ['read']);
        });

        test('a group role change reaches its members and nobody else is recomputed', () => {
          const { d, r } = setup();
          r.permissions('ann');
          r.permissions('bob');
          r.permissions('cy');
          const before = r.computes;
          d.setGroupRoles('ops', ['viewer']);
          assert.deepStrictEqual(sorted(r.permissions('bob', 'globex')), ['read']);
          r.permissions('ann');
          r.permissions('cy');
          assert.strictEqual(r.computes, before + 1);
        });

        test('a change to a parent group reaches members of its child groups', () => {
          const { d, r } = setup();
          assert.deepStrictEqual(sorted(r.permissions('ann')), ['read', 'write']);
          d.setGroupRoles('eng', ['admin']);
          assert.deepStrictEqual(sorted(r.permissions('ann')), ['admin', 'delete', 'read', 'write']);
        });

        test('moving a group changes what its members inherit', () => {
          const { d, r } = setup();
          assert.deepStrictEqual(sorted(r.permissions('ann')), ['read', 'write']);
          d.moveGroup('backend', 'ops');
          assert.deepStrictEqual(sorted(r.permissions('ann')), ['admin', 'delete', 'read', 'write']);
          d.moveGroup('backend', null);
          assert.deepStrictEqual(sorted(r.permissions('ann')), ['read']);
        });

        test('moving a group with sub-groups reaches the members of the sub-groups', () => {
          const { d, r } = setup();
          d.addGroup('infra', { roles: [], parent: 'backend' });
          d.addUser('dee', { roles: [], groups: ['infra'] });
          assert.deepStrictEqual(sorted(r.permissions('dee')), ['read', 'write']);
          d.moveGroup('backend', 'ops');
          assert.deepStrictEqual(sorted(r.permissions('dee')), ['admin', 'delete', 'read', 'write']);
        });
    '''),
}


def _b_prompts():
    p = {}
    p["tenant-leak"] = (
        "Security-adjacent: a user who is a billing clerk for Acme only shows billing powers in the Globex console as well, but "
        "only if the Acme console was opened first in that process. The role is written `billing@acme`. Something in the "
        "resolver's memoisation does not know about tenants."
    )
    p["group-ignored"] = (
        "We revoked the `admin` role of the ops group an hour ago and the people in it can still do admin things until the "
        "service restarts. Changing a person's own roles takes effect at once. Changes to group roles seem to be "
        "ignored by the resolver."
    )
    p["descendants"] = (
        "Changing the roles of the `eng` group updates the people directly in `eng` but not the ones in its sub-groups "
        "(`backend`, `infra`): they keep their old permissions until restart. The README says everyone below the group "
        "is refreshed."
    )
    p["removed-user"] = (
        "Offboarding bug: when an account is deleted and the same id is re-created later for a new hire (we recycle ids), "
        "the new hire briefly has the permissions of the previous holder. A restart cures it. Only happens if the previous "
        "holder had been resolved before they were removed."
    )
    p["internal-set"] = (
        "The settings page adds a synthetic `preview` permission to the set it gets back from `permissions()` to render a "
        "demo. Afterwards every later call for that user contains `preview`. The caller owns the set it receives; "
        "the resolver should hand out a fresh one each time."
    )
    p["move-and-descendants"] = (
        "Re-organising teams: moving `backend` under the `ops` department does not change what its members can do, and "
        "when the department's own roles change the people in its sub-teams are not refreshed either. Direct members are "
        "fine. We need both fixed; restarting the service is the only thing that helps today."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "src/roles.js": B_ROLES, "src/directory.js": B_DIRECTORY, "src/resolver.js": B_RESOLVER,
            "package.json": '{\n  "name": "permcache",\n  "version": "1.0.0",\n  "private": true\n}\n'}
    rs, di = "src/resolver.js", "src/directory.js"
    sub_bug = ("    const groups = this.dir.subtree(ev.name);\n", "    const groups = new Set([ev.name]);\n")
    mv_bug = ("    this.groups.get(name).parent = parent;\n    this.emit({ type: 'group', name });\n", "    this.groups.get(name).parent = parent;\n")
    bugs = [
        Bug("tenant-not-in-key", 3, {rs: [("    if (!byTenant.has(tenant)) byTenant.set(tenant, this.compute(userId, tenant));\n    return new Set(byTenant.get(tenant));\n",
                                          "    if (!byTenant.has('*')) byTenant.set('*', this.compute(userId, tenant));\n    return new Set(byTenant.get('*'));\n")]}, P["tenant-leak"]),
        Bug("returns-cached-set", 2, {rs: [("    return new Set(byTenant.get(tenant));\n", "    return byTenant.get(tenant);\n")]}, P["internal-set"]),
        Bug("group-events-ignored", 3, {rs: [("    const groups = this.dir.subtree(ev.name);\n    for (const [id, user] of this.dir.users) {\n      for (const g of user.groups) {\n        if (groups.has(g)) {\n          this.cache.delete(id);\n          break;\n        }\n      }\n    }\n", "")]}, P["group-ignored"]),
        Bug("removed-user-kept", 3, {rs: [("    if (ev.type === 'user') {\n      this.cache.delete(ev.id);\n      return;\n    }\n",
                                          "    if (ev.type === 'user') {\n      if (this.dir.users.has(ev.id)) this.cache.delete(ev.id);\n      return;\n    }\n")]}, P["removed-user"]),
        Bug("only-direct-members", 4, {rs: [sub_bug]}, P["descendants"]),
        Bug("move-silent-and-direct-only", 5, {rs: [sub_bug], di: [mv_bug]}, P["move-and-descendants"]),
    ]
    return Base("permcache", "javascript", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-stale-cache", category="fix", lang="python", kind="fix", n=12,
        summary="stale caches and missed invalidation: a TTL price cache (python) and a memoised permission resolver (javascript)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
