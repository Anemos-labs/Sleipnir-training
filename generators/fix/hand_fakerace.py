"""Concurrency bugs on a deterministic fake scheduler: check-then-act, lost updates, lock order, leaked locks (python)."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, sub, tasks_from

SCHED = dd('''
    """A deterministic cooperative scheduler: tasks are generators, every ``yield`` is a point where another task may run."""

    BLOCKED = object()
    _releases = 0  # how many times any lock was released: a blocked task can only wake up after a release


    class Deadlock(Exception):
        pass


    class Lock:
        def __init__(self, name=""):
            self.name = name
            self.held = False

        def acquire(self):
            """Generator: ``yield from lock.acquire()`` waits (yielding BLOCKED) until the lock is free, takes it, and
            yields once more (taking a lock is itself a scheduling point)."""
            while self.held:
                yield BLOCKED
            self.held = True
            yield

        def release(self):
            global _releases
            if not self.held:
                raise RuntimeError(f"release of lock {self.name!r} that is not held")
            self.held = False
            _releases += 1


    def run(tasks, schedule=()):
        """Run ``tasks`` (a list of ``(name, generator)``) to completion and return ``{name: return value}``.

        ``schedule`` is a list of task names: the n-th entry says which task takes the n-th step (a step runs the task up to
        its next ``yield``). Entries naming finished tasks are skipped. When the schedule is used up the remaining tasks
        take turns in round-robin order. ``Deadlock`` is raised when every unfinished task is blocked on a lock."""
        live = dict(tasks)
        rotation = [name for name, _ in tasks]
        order = list(schedule)
        results = {}
        stuck = {}  # task name -> value of _releases when it was last found blocked
        turn = 0
        while live:
            if order:
                name = order.pop(0)
                if name not in live:
                    continue
            else:
                names = [n for n in rotation if n in live]
                name = names[turn % len(names)]
                turn += 1
            try:
                signal = next(live[name])
            except StopIteration as stop:
                results[name] = stop.value
                del live[name]
                stuck.pop(name, None)
                continue
            if signal is BLOCKED:
                stuck[name] = _releases
            else:
                stuck.pop(name, None)
            if live and all(stuck.get(n) == _releases for n in live):
                raise Deadlock(sorted(live))
        return results
''')

# ------------------------------------------------------------------------------------------------------------------
# Base A: warehouses and a shop (sell, restock, transfer).
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # warehouse

    Stock handling of a small online shop, written as cooperative tasks for the fake scheduler in `warehouse/sched.py`
    (read its docstring: a task is a generator, every `yield` is a point where another task may run; `Lock` is a
    non-reentrant lock; `run(tasks, schedule)` takes steps in the order given). **Every operation must be correct for every
    interleaving of the tasks**, and must always release the locks it takes, on every path.

    ## `warehouse.stock`
    * `Warehouse(name, stock)`: `stock` maps sku to units; it has a `lock`.
    * `Shop(*warehouses)` with `shop.w[name]`, `shop.sold` (buyer -> units bought in total) and these operations (generators):
      * `sell(buyer, warehouse, sku, qty)`: under the warehouse's lock, if the warehouse has at least `qty` units of the
        sku, takes them and then adds `qty` to `shop.sold[buyer]` (under `shop.sold_lock`); returns `True`. If there is
        not enough stock nothing changes and it returns `False` (the lock is released). Stock never goes negative; the
        total taken from a warehouse never exceeds what it had.
      * `restock(warehouse, sku, qty)`: adds units under the warehouse's lock.
      * `transfer(src, dst, sku, qty)`: moves units between two warehouses, holding both locks, acquired in **sorted order of the
        warehouse names**, so opposite transfers can never deadlock. `False` (nothing changes) when `src` lacks the units.
        Units are never created or destroyed: stock of `src` + stock of `dst` stays the same.
''')

A_STOCK = dd('''
    from .sched import Lock


    class Warehouse:
        def __init__(self, name, stock):
            self.name = name
            self.stock = dict(stock)
            self.lock = Lock(name)


    class Shop:
        def __init__(self, *warehouses):
            self.w = {wh.name: wh for wh in warehouses}
            self.sold = {}
            self.sold_lock = Lock("sold")

        def sell(self, buyer, warehouse, sku, qty):
            wh = self.w[warehouse]
            yield from wh.lock.acquire()
            try:
                yield
                have = wh.stock.get(sku, 0)
                if have < qty:
                    return False
                yield
                wh.stock[sku] = have - qty
            finally:
                wh.lock.release()
            yield from self.sold_lock.acquire()
            try:
                yield
                total = self.sold.get(buyer, 0)
                yield
                self.sold[buyer] = total + qty
            finally:
                self.sold_lock.release()
            return True

        def restock(self, warehouse, sku, qty):
            wh = self.w[warehouse]
            yield from wh.lock.acquire()
            try:
                yield
                have = wh.stock.get(sku, 0)
                yield
                wh.stock[sku] = have + qty
            finally:
                wh.lock.release()

        def transfer(self, src, dst, sku, qty):
            first, second = sorted([src, dst])
            yield from self.w[first].lock.acquire()
            try:
                yield from self.w[second].lock.acquire()
                try:
                    yield
                    a, b = self.w[src], self.w[dst]
                    if a.stock.get(sku, 0) < qty:
                        return False
                    yield
                    a.stock[sku] -= qty
                    b.stock[sku] = b.stock.get(sku, 0) + qty
                    return True
                finally:
                    self.w[second].lock.release()
            finally:
                self.w[first].lock.release()
''')

A_VISIBLE = {
    "tests/test_stock.py": dd('''
        import unittest

        from warehouse.sched import run
        from warehouse.stock import Shop, Warehouse


        class SequentialTests(unittest.TestCase):
            def test_sell_and_restock(self):
                shop = Shop(Warehouse("north", {"cog": 5}))
                self.assertEqual(run([("a", shop.sell("ann", "north", "cog", 2))]), {"a": True})
                self.assertEqual(shop.w["north"].stock["cog"], 3)
                self.assertEqual(shop.sold, {"ann": 2})
                run([("r", shop.restock("north", "cog", 4))])
                self.assertEqual(shop.w["north"].stock["cog"], 7)

            def test_not_enough_stock(self):
                shop = Shop(Warehouse("north", {"cog": 1}))
                self.assertEqual(run([("a", shop.sell("ann", "north", "cog", 2))]), {"a": False})
                self.assertEqual(shop.w["north"].stock["cog"], 1)
                self.assertEqual(shop.sold, {})

            def test_transfer(self):
                shop = Shop(Warehouse("north", {"cog": 5}), Warehouse("south", {}))
                self.assertEqual(run([("t", shop.transfer("north", "south", "cog", 3))]), {"t": True})
                self.assertEqual((shop.w["north"].stock["cog"], shop.w["south"].stock["cog"]), (2, 3))


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_stock.py": dd('''
        import itertools
        import unittest

        from warehouse.sched import Deadlock, run
        from warehouse.stock import Shop, Warehouse


        def schedules(names, length):
            return itertools.product(names, repeat=length)


        def fresh():
            return Shop(Warehouse("north", {"cog": 3}), Warehouse("south", {"cog": 3, "nut": 5}))


        class Selling(unittest.TestCase):
            def test_two_buyers_for_the_last_units(self):
                for sched in schedules("ab", 8):
                    shop = Shop(Warehouse("north", {"cog": 3}))
                    out = run([("a", shop.sell("ann", "north", "cog", 2)), ("b", shop.sell("bob", "north", "cog", 2))], sched)
                    self.assertEqual(sorted(out.values()), [False, True], sched)
                    self.assertEqual(shop.w["north"].stock["cog"], 1, sched)
                    self.assertEqual(sum(shop.sold.values()), 2, sched)
                    self.assertFalse(shop.w["north"].lock.held, sched)

            def test_three_buyers(self):
                for sched in schedules("abc", 7):
                    shop = Shop(Warehouse("north", {"cog": 5}))
                    tasks = [(n, shop.sell(n, "north", "cog", 2)) for n in "abc"]
                    out = run(tasks, sched)
                    self.assertEqual(sorted(out.values()), [False, True, True], sched)
                    self.assertEqual(shop.w["north"].stock["cog"], 1, sched)

            def test_sold_counter_is_not_lost(self):
                for sched in schedules("ab", 10):
                    shop = Shop(Warehouse("north", {"cog": 9}), Warehouse("south", {"cog": 9}))
                    run([("a", shop.sell("kim", "north", "cog", 1)), ("b", shop.sell("kim", "south", "cog", 2))], sched)
                    self.assertEqual(shop.sold, {"kim": 3}, sched)
                    self.assertFalse(shop.sold_lock.held, sched)

            def test_a_refused_sale_releases_the_lock(self):
                for sched in schedules("ab", 6):
                    shop = Shop(Warehouse("north", {"cog": 1}))
                    out = run([("a", shop.sell("ann", "north", "cog", 5)), ("b", shop.sell("bob", "north", "cog", 1))], sched)
                    self.assertEqual(out, {"a": False, "b": True}, sched)
                    self.assertEqual(shop.w["north"].stock["cog"], 0, sched)
                    self.assertFalse(shop.w["north"].lock.held, sched)

            def test_restock_does_not_lose_units(self):
                for sched in schedules("ab", 8):
                    shop = Shop(Warehouse("north", {"cog": 1}))
                    run([("a", shop.restock("north", "cog", 2)), ("b", shop.restock("north", "cog", 4))], sched)
                    self.assertEqual(shop.w["north"].stock["cog"], 7, sched)

            def test_sale_during_restock(self):
                for sched in schedules("ab", 8):
                    shop = Shop(Warehouse("north", {"cog": 2}))
                    out = run([("a", shop.restock("north", "cog", 3)), ("b", shop.sell("bob", "north", "cog", 2))], sched)
                    self.assertTrue(out["b"], sched)
                    self.assertEqual(shop.w["north"].stock["cog"], 3, sched)

            def test_unknown_warehouse(self):
                shop = fresh()
                with self.assertRaises(KeyError):
                    run([("a", shop.sell("ann", "west", "cog", 1))])


        class Transfers(unittest.TestCase):
            def test_opposite_transfers_never_deadlock(self):
                for sched in schedules("ab", 8):
                    shop = fresh()
                    try:
                        out = run([("a", shop.transfer("north", "south", "cog", 2)), ("b", shop.transfer("south", "north", "cog", 1))], sched)
                    except Deadlock:
                        self.fail(f"deadlock with schedule {sched}")
                    self.assertEqual(out, {"a": True, "b": True}, sched)
                    self.assertEqual(shop.w["north"].stock["cog"], 2, sched)
                    self.assertEqual(shop.w["south"].stock["cog"], 4, sched)

            def test_units_are_conserved_with_sales_in_between(self):
                for sched in schedules("ab", 9):
                    shop = fresh()
                    out = run([("a", shop.transfer("north", "south", "cog", 3)), ("b", shop.sell("bob", "north", "cog", 2))], sched)
                    left = shop.w["north"].stock["cog"] + shop.w["south"].stock["cog"]
                    sold = 2 if out["b"] else 0
                    self.assertEqual(left + sold, 6, sched)
                    self.assertGreaterEqual(shop.w["north"].stock["cog"], 0, sched)
                    self.assertEqual(shop.sold.get("bob", 0), sold, sched)

            def test_a_failed_transfer_changes_nothing_and_unlocks(self):
                for sched in schedules("ab", 6):
                    shop = fresh()
                    out = run([("a", shop.transfer("north", "south", "cog", 9)), ("b", shop.sell("bob", "south", "nut", 1))], sched)
                    self.assertEqual(out, {"a": False, "b": True}, sched)
                    self.assertEqual((shop.w["north"].stock["cog"], shop.w["south"].stock["cog"]), (3, 3), sched)
                    self.assertFalse(shop.w["north"].lock.held or shop.w["south"].lock.held, sched)

            def test_three_way_cycle_of_transfers(self):
                for sched in schedules("pqr", 6):
                    shop = Shop(Warehouse("a", {"x": 1}), Warehouse("b", {"x": 1}), Warehouse("c", {"x": 1}))
                    tasks = [("p", shop.transfer("a", "b", "x", 1)), ("q", shop.transfer("b", "c", "x", 1)), ("r", shop.transfer("c", "a", "x", 1))]
                    run(tasks, sched)
                    self.assertEqual(sum(w.stock.get("x", 0) for w in shop.w.values()), 3, sched)


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["no-lock"] = (
        "We oversold: two customers each bought 2 of the last 3 cogs and the stock went to -1 in the nightly reconciliation. "
        "It only happens when the two checkouts run at the same moment, which is why nobody could reproduce it by hand. "
        "The scheduler harness in `warehouse/sched.py` lets you pick the interleaving. Fix `Shop.sell` for all interleavings."
    )
    p["leaked-lock"] = (
        "After a customer asks for more than we have (\"not enough stock\"), every later sale from the same warehouse hangs: the harness "
        "reports a deadlock. Successful sales before it were fine. Something keeps the warehouse lock after a refused sale."
    )
    p["lost-counter"] = (
        "The loyalty points use `shop.sold[buyer]`. A customer who bought from two warehouses at once (two browser tabs) ends up "
        "with the total of only one of the purchases. It is not deterministic in production, but with the fake scheduler "
        "one order of steps reproduces it every time."
    )
    p["lock-order"] = (
        "Transfers between warehouses occasionally freeze: when north->south and south->north are requested at the same time "
        "both wait for each other forever. The README says locks are taken in sorted order of the warehouse names."
    )
    p["two"] = (
        "Two production incidents in warehouse stock that I believe are separate: (1) oversold items under concurrent checkouts, "
        "(2) two opposite stock transfers hanging forever. Both depend on the interleaving. Please make `sell` and `transfer` "
        "correct for every interleaving, the visible tests cannot show it."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "warehouse/__init__.py": '"""Warehouse stock."""\n', "warehouse/sched.py": SCHED, "warehouse/stock.py": A_STOCK}
    st = "warehouse/stock.py"
    no_lock = [("        wh = self.w[warehouse]\n        yield from wh.lock.acquire()\n        try:\n            yield\n            have = wh.stock.get(sku, 0)\n            if have < qty:\n                return False\n            yield\n            wh.stock[sku] = have - qty\n        finally:\n            wh.lock.release()\n",
                "        wh = self.w[warehouse]\n        yield\n        have = wh.stock.get(sku, 0)\n        if have < qty:\n            return False\n        yield\n        wh.stock[sku] = have - qty\n")]
    leak = [("        yield from wh.lock.acquire()\n        try:\n            yield\n            have = wh.stock.get(sku, 0)\n            if have < qty:\n                return False\n            yield\n            wh.stock[sku] = have - qty\n        finally:\n            wh.lock.release()\n",
             "        yield from wh.lock.acquire()\n        yield\n        have = wh.stock.get(sku, 0)\n        if have < qty:\n            return False\n        yield\n        wh.stock[sku] = have - qty\n        wh.lock.release()\n")]
    lost = [("        yield from self.sold_lock.acquire()\n        try:\n            yield\n            total = self.sold.get(buyer, 0)\n            yield\n            self.sold[buyer] = total + qty\n        finally:\n            self.sold_lock.release()\n",
             "        yield\n        total = self.sold.get(buyer, 0)\n        yield\n        self.sold[buyer] = total + qty\n")]
    order = [("        first, second = sorted([src, dst])\n", "        first, second = src, dst\n")]
    bugs = [
        Bug("sell-without-lock", 3, {st: no_lock}, P["no-lock"]),
        Bug("refused-sale-keeps-the-lock", 3, {st: leak}, P["leaked-lock"]),
        Bug("sold-counter-unlocked", 3, {st: lost}, P["lost-counter"]),
        Bug("transfer-locks-in-argument-order", 4, {st: order}, P["lock-order"]),
        Bug("sell-unlocked-and-transfer-order", 5, {st: no_lock + order}, P["two"]),
    ]
    return Base("warehouse", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B: a job board with leases.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # jobboard

    A tiny work queue with leases, written as cooperative tasks for the fake scheduler in `jobboard/sched.py` (a task is a
    generator, every `yield` is a point where another task may run). Time is passed in explicitly as `now`. **All
    operations must be correct for every interleaving**, and must release the board's lock on every path.

    ## `jobboard.board.Board(ids, lease=30)`
    Jobs start `pending`, ordered as given. `board.jobs[id]` has `state` (`pending`, `claimed`, `done`), `owner`,
    `lease_until` and `attempts`.

    * `claim(worker, now)` (generator, under `board.lock`): gives the **first pending job** (in the original order) to `worker`:
      state `claimed`, `owner`, `lease_until = now + lease`, `attempts += 1`; returns its id, or `None` when nothing is
      pending. Two workers never get the same job.
    * `complete(worker, job_id, now)`: marks the job `done` and returns `True` only if the job is `claimed` by that worker and
      its lease has not run out (`now < lease_until`); otherwise nothing changes and it returns `False`.
    * `reap(now)`: every `claimed` job whose lease has run out (`now >= lease_until`) becomes `pending` again (no owner);
      returns the re-queued ids in the original order. `done` jobs are never touched.
''')

B_BOARD = dd('''
    from .sched import Lock


    class Job:
        def __init__(self, job_id):
            self.id = job_id
            self.state = "pending"
            self.owner = None
            self.lease_until = None
            self.attempts = 0


    class Board:
        def __init__(self, ids, lease=30):
            self.jobs = {i: Job(i) for i in ids}
            self.lease = lease
            self.lock = Lock("board")

        def claim(self, worker, now):
            yield from self.lock.acquire()
            try:
                yield
                for job in self.jobs.values():
                    if job.state == "pending":
                        yield
                        job.state = "claimed"
                        job.owner = worker
                        job.lease_until = now + self.lease
                        job.attempts += 1
                        return job.id
                return None
            finally:
                self.lock.release()

        def complete(self, worker, job_id, now):
            job = self.jobs[job_id]
            if job.state != "claimed" or job.owner != worker or now >= job.lease_until:
                return False
            job.state = "done"
            return True

        def reap(self, now):
            back = []
            for job in self.jobs.values():
                if job.state == "claimed" and now >= job.lease_until:
                    job.state = "pending"
                    job.owner = None
                    back.append(job.id)
            return back
''')

B_VISIBLE = {
    "tests/test_board.py": dd('''
        import unittest

        from jobboard.board import Board
        from jobboard.sched import run


        class BoardTests(unittest.TestCase):
            def test_claim_in_order(self):
                b = Board(["j1", "j2"])
                self.assertEqual(run([("w", b.claim("w1", 0))]), {"w": "j1"})
                self.assertEqual(run([("w", b.claim("w2", 0))]), {"w": "j2"})
                self.assertEqual(run([("w", b.claim("w3", 0))]), {"w": None})

            def test_complete(self):
                b = Board(["j1"], lease=10)
                run([("w", b.claim("w1", 0))])
                self.assertTrue(b.complete("w1", "j1", 5))
                self.assertEqual(b.jobs["j1"].state, "done")

            def test_reap(self):
                b = Board(["j1"], lease=10)
                run([("w", b.claim("w1", 0))])
                self.assertEqual(b.reap(100), ["j1"])


        if __name__ == "__main__":
            unittest.main()
    '''),
}

B_HIDDEN = {
    "tests/test_hidden_board.py": dd('''
        import itertools
        import unittest

        from jobboard.board import Board
        from jobboard.sched import run


        def schedules(names, length):
            return itertools.product(names, repeat=length)


        class Claiming(unittest.TestCase):
            def test_two_workers_never_get_the_same_job(self):
                for sched in schedules("ab", 8):
                    b = Board(["j1", "j2", "j3"])
                    out = run([("a", b.claim("wa", 0)), ("b", b.claim("wb", 0))], sched)
                    self.assertEqual(sorted(out.values()), ["j1", "j2"], sched)
                    self.assertEqual(b.jobs["j1"].attempts + b.jobs["j2"].attempts, 2, sched)
                    self.assertFalse(b.lock.held, sched)

            def test_one_job_two_workers(self):
                for sched in schedules("ab", 8):
                    b = Board(["only"])
                    out = run([("a", b.claim("wa", 0)), ("b", b.claim("wb", 0))], sched)
                    self.assertEqual(sorted(out.values(), key=str), [None, "only"], sched)
                    self.assertEqual(b.jobs["only"].attempts, 1, sched)

            def test_three_workers(self):
                for sched in schedules("abc", 7):
                    b = Board(["j1", "j2"])
                    out = run([(n, b.claim("w" + n, 5)) for n in "abc"], sched)
                    self.assertEqual(sorted(out.values(), key=str), [None, "j1", "j2"], sched)

            def test_lease_and_owner_are_recorded(self):
                b = Board(["j1"], lease=30)
                run([("a", b.claim("wa", 100))])
                job = b.jobs["j1"]
                self.assertEqual((job.state, job.owner, job.lease_until, job.attempts), ("claimed", "wa", 130, 1))

            def test_lock_is_free_after_an_empty_claim(self):
                b = Board([])
                for sched in schedules("ab", 4):
                    out = run([("a", b.claim("wa", 0)), ("b", b.claim("wb", 0))], sched)
                    self.assertEqual(out, {"a": None, "b": None})
                    self.assertFalse(b.lock.held)


        class Completing(unittest.TestCase):
            def setUp(self):
                self.b = Board(["j1", "j2"], lease=10)
                run([("a", self.b.claim("wa", 0))])
                run([("b", self.b.claim("wb", 0))])

            def test_owner_in_time(self):
                self.assertTrue(self.b.complete("wa", "j1", 9))
                self.assertEqual(self.b.jobs["j1"].state, "done")

            def test_lease_boundary(self):
                self.assertFalse(self.b.complete("wa", "j1", 10))
                self.assertEqual(self.b.jobs["j1"].state, "claimed")

            def test_wrong_worker(self):
                self.assertFalse(self.b.complete("wb", "j1", 1))
                self.assertEqual((self.b.jobs["j1"].state, self.b.jobs["j1"].owner), ("claimed", "wa"))

            def test_stale_worker_after_a_reclaim(self):
                self.assertEqual(self.b.reap(20), ["j1", "j2"])
                run([("c", self.b.claim("wc", 21))])
                self.assertEqual(self.b.jobs["j1"].owner, "wc")
                self.assertFalse(self.b.complete("wa", "j1", 22))
                self.assertEqual(self.b.jobs["j1"].state, "claimed")
                self.assertTrue(self.b.complete("wc", "j1", 22))

            def test_completing_twice_or_a_pending_job(self):
                self.assertTrue(self.b.complete("wa", "j1", 1))
                self.assertFalse(self.b.complete("wa", "j1", 2))
                self.b.reap(50)
                self.assertFalse(self.b.complete("wb", "j2", 51))


        class Reaping(unittest.TestCase):
            def test_expired_claims_go_back_in_order(self):
                b = Board(["j1", "j2", "j3"], lease=10)
                run([("a", b.claim("wa", 0))])
                run([("b", b.claim("wb", 5))])
                run([("c", b.claim("wc", 6))])
                self.assertEqual(b.reap(10), ["j1"])
                self.assertEqual(b.reap(15), ["j2"])
                self.assertEqual(b.jobs["j1"].state, "pending")
                self.assertIsNone(b.jobs["j1"].owner)
                self.assertEqual(b.jobs["j3"].state, "claimed")

            def test_done_jobs_are_never_requeued(self):
                b = Board(["j1", "j2"], lease=10)
                run([("a", b.claim("wa", 0))])
                run([("b", b.claim("wb", 0))])
                self.assertTrue(b.complete("wa", "j1", 3))
                self.assertEqual(b.reap(1000), ["j2"])
                self.assertEqual(b.jobs["j1"].state, "done")

            def test_reclaimed_job_gets_a_new_lease_and_attempt(self):
                b = Board(["j1"], lease=10)
                run([("a", b.claim("wa", 0))])
                b.reap(10)
                run([("b", b.claim("wb", 12))])
                job = b.jobs["j1"]
                self.assertEqual((job.owner, job.lease_until, job.attempts), ("wb", 22, 2))

            def test_nothing_to_reap(self):
                b = Board(["j1"], lease=10)
                self.assertEqual(b.reap(99), [])


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _b_prompts():
    p = {}
    p["claim-race"] = (
        "Two workers occasionally run the same job (attempts shows 2 although nothing failed). In the fake scheduler it happens when "
        "both workers take a step before either of them marks the job. Make `claim` correct for every interleaving."
    )
    p["owner"] = (
        "A worker that was too slow and lost its lease (the job was re-queued and picked up by another worker) can still mark "
        "the job done, which hides the other worker's progress. `complete` is supposed to accept only the current owner "
        "within the lease."
    )
    p["reap-done"] = (
        "Finished jobs come back: every job whose lease timestamp is in the past is put back into the queue by the reaper "
        "even if it was completed, so work is repeated every time the lease length passes. `reap` should only touch claimed jobs."
    )
    p["boundary"] = (
        "A lease is valid while `now < lease_until` (README). At exactly `now == lease_until` the reaper still leaves the job "
        "with its worker, so the job is picked up one tick late. `Board.reap` in `jobboard/board.py` should treat that instant as expired."
    )
    p["empty-claim"] = (
        "When the queue is empty, the first worker to ask gets `None` and from then on every other worker hangs (the harness says "
        "deadlock). Looks like the lock is not released on the empty path."
    )
    p["two"] = (
        "Two problems in the lease queue, reported separately: (1) the same job is occasionally handed to two workers, (2) a worker "
        "whose lease expired and whose job was given to someone else can still complete it. I want both fixed and the "
        "fake-scheduler tests to pass for all interleavings."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "jobboard/__init__.py": '"""Lease queue."""\n', "jobboard/sched.py": SCHED, "jobboard/board.py": B_BOARD}
    bd = "jobboard/board.py"
    claim_race = ("        yield from self.lock.acquire()\n        try:\n            yield\n            for job in self.jobs.values():\n                if job.state == \"pending\":\n                    yield\n                    job.state = \"claimed\"\n                    job.owner = worker\n                    job.lease_until = now + self.lease\n                    job.attempts += 1\n                    return job.id\n            return None\n        finally:\n            self.lock.release()\n",
                  "        yield\n        for job in self.jobs.values():\n            if job.state == \"pending\":\n                yield\n                job.state = \"claimed\"\n                job.owner = worker\n                job.lease_until = now + self.lease\n                job.attempts += 1\n                return job.id\n        return None\n")
    empty_leak = (
        "        yield from self.lock.acquire()\n        try:\n            yield\n            for job in self.jobs.values():\n                if job.state == \"pending\":\n                    yield\n                    job.state = \"claimed\"\n                    job.owner = worker\n                    job.lease_until = now + self.lease\n                    job.attempts += 1\n                    return job.id\n            return None\n        finally:\n            self.lock.release()\n",
        "        yield from self.lock.acquire()\n        yield\n        for job in self.jobs.values():\n            if job.state == \"pending\":\n                yield\n                job.state = \"claimed\"\n                job.owner = worker\n                job.lease_until = now + self.lease\n                job.attempts += 1\n                self.lock.release()\n                return job.id\n        return None\n")
    owner_bug = ("        if job.state != \"claimed\" or job.owner != worker or now >= job.lease_until:\n", "        if job.state != \"claimed\" or now >= job.lease_until:\n")
    bugs = [
        Bug("claim-without-lock", 3, {bd: [claim_race]}, P["claim-race"]),
        Bug("complete-ignores-owner", 2, {bd: [owner_bug]}, P["owner"]),
        Bug("reap-requeues-done-jobs", 2, {bd: [("            if job.state == \"claimed\" and now >= job.lease_until:\n", "            if now >= job.lease_until:\n")]}, P["reap-done"]),
        Bug("reap-boundary-exclusive", 1, {bd: [("            if job.state == \"claimed\" and now >= job.lease_until:\n", "            if job.state == \"claimed\" and now > job.lease_until:\n")]}, P["boundary"]),
        Bug("empty-claim-keeps-lock", 3, {bd: [empty_leak]}, P["empty-claim"]),
        Bug("claim-race-and-stale-owner", 5, {bd: [claim_race, owner_bug]}, P["two"]),
    ]
    return Base("jobboard", "python", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-fake-race", category="fix", lang="python", kind="fix", n=11,
        summary="deterministic concurrency bugs on a fake scheduler: unlocked check-then-act, leaked locks, lock order, leases")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
