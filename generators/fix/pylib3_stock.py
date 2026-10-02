"""Warehouse and stock algorithms in domain clothes (python, fix-py-3): cost layers, crate loading, bay allocation, seating."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# costlayers: FIFO / moving-average inventory costing with returns (multi-module)
# ======================================================================================================================

COSTLAYERS_README = dd('''
    # costlayers

    Inventory costing for a small wholesaler. Quantities are positive integers, costs are integer **cents per unit**.
    Two costing methods are supported: `"fifo"` (the oldest cost layer is consumed first) and `"avg"` (one moving
    average per SKU). Everything is integer arithmetic; division always rounds *half up*.

    ## `costlayers.money`

    * `round_div(n, d) -> int`: `n / d` rounded half up. `ValueError` if `d <= 0` or `n < 0`.
    * `fmt_cents(cents) -> str`: `"1,234.50"` style. Always two decimals, `,` between groups of three digits in the
      whole part, a leading `-` for negative amounts (`fmt_cents(-5) == "-0.05"`).

    ## `costlayers.layers`

    ### `CostQueue` (FIFO layers of one SKU)
    * `push(qty, unit_cost)` adds a layer at the back. If the back layer has the same unit cost the quantity is added
      to it instead (layers never get merged any other way). `qty <= 0` or `unit_cost < 0` is a `ValueError`
      (a unit cost of `0` is fine: free goods).
    * `push_front(qty, unit_cost)` does the same at the front (merging into the front layer when costs are equal).
    * `on_hand` is the total quantity, `value` the total cost in cents, `layers()` a list of `(qty, unit_cost)` from
      the oldest to the newest layer.
    * `take(qty)` draws `qty` units from the oldest layers and returns the *parts* it drew, oldest first, as
      `(part_qty, part_cost)` where `part_cost` is the total cost in cents of that part. A layer that is only partly
      used keeps its remainder (and stays the oldest). `qty <= 0` or `qty > on_hand` is a `ValueError` and leaves
      the queue unchanged.
    * `put_back(parts)` undoes a `take`: the parts (given oldest first, as `take` returned them) go back to the front
      of the queue, so that giving back *all* parts of one `take` restores the queue exactly.

    ### `AvgPool` (moving average of one SKU)
    * `push(qty, unit_cost)` adds stock (same validation as `CostQueue.push`). `on_hand` and `value` as above.
    * `take(qty)` charges `round_div(value * qty, on_hand)` cents (rounded once, over the whole quantity, not per
      unit) and returns a single part `[(qty, cost)]`. The pool loses that quantity and that cost. Errors as in
      `CostQueue.take`.
    * `put_back(parts)` adds each part's quantity and cost back to the pool.

    ## `costlayers.ledger`

    `Ledger(method="fifo")` (`ValueError` for any other method than `"fifo"` and `"avg"`).

    * `receive(sku, qty, unit_cost)`: stock arrives.
    * `issue(sku, qty, ref) -> Issue`: stock leaves under a unique reference string. `ValueError` if `ref` was used
      before by any earlier *successful* issue; `KeyError` if the SKU never received anything; `ValueError` for
      insufficient stock (nothing is recorded then, the reference stays free). An `Issue` has `ref`, `sku`, `qty`,
      `cost` (total cents) and `parts` (what is still outstanding, i.e. not yet returned, same format as `take`).
    * `return_in(ref, qty) -> int`: the customer sends back `qty` units of an earlier issue; returns the cost in
      cents credited back. Units come back *last drawn part first*; a part that is only partly returned keeps its
      remainder. The credit for `used` units out of a part `(q, c)` is `round_div(c * used, q)` and the remainder
      keeps `c` minus that credit. The returned parts go back into the SKU's pool with `put_back`. Unknown `ref` is a
      `KeyError`; `qty <= 0` or more than what is still outstanding on that issue is a `ValueError`.
    * `on_hand(sku)`, `value(sku)` (both `0` for an unknown SKU), `skus()` (sorted list of every SKU ever received).
    * `cogs()`: total cost in cents of everything issued minus what was returned (the sum of the outstanding parts
      of all issues).

    ## `costlayers.report`

    * `valuation(ledger) -> list[(sku, qty, value)]` sorted by SKU, only SKUs with stock on hand.
    * `render(ledger) -> str`: `"(no stock)"` when the valuation is empty, otherwise a table of lines joined by
      `"\\n"` (no trailing newline): a header, one line per row, and a `TOTAL` line. Columns are separated by two
      spaces: the label column is left-justified and as wide as the longest SKU but at least 5 (the width of
      `TOTAL`); the quantity column is right-aligned in width 6; the value column is `fmt_cents` right-aligned in
      width 12. The header labels are `SKU`, `QTY`, `VALUE`.
''')

COSTLAYERS_MONEY = dd('''
    """Integer money helpers (cents)."""


    def round_div(n: int, d: int) -> int:
        """n / d rounded half up (n >= 0, d > 0)."""
        if d <= 0:
            raise ValueError("divisor must be positive")
        if n < 0:
            raise ValueError("numerator must not be negative")
        return (2 * n + d) // (2 * d)


    def fmt_cents(cents: int) -> str:
        sign = "-" if cents < 0 else ""
        whole, frac = divmod(abs(cents), 100)
        groups = []
        while whole >= 1000:
            whole, rest = divmod(whole, 1000)
            groups.append(f"{rest:03d}")
        groups.append(str(whole))
        return f"{sign}{','.join(reversed(groups))}.{frac:02d}"
''')

COSTLAYERS_LAYERS = dd('''
    """Cost layers of one SKU: a FIFO queue and a moving-average pool."""
    from .money import round_div


    def _check(qty: int, unit_cost: int) -> None:
        if qty <= 0:
            raise ValueError("quantity must be positive")
        if unit_cost < 0:
            raise ValueError("unit cost must not be negative")


    class CostQueue:
        def __init__(self):
            self._layers = []  # [qty, unit_cost], oldest first

        def push(self, qty, unit_cost):
            _check(qty, unit_cost)
            if self._layers and self._layers[-1][1] == unit_cost:
                self._layers[-1][0] += qty
            else:
                self._layers.append([qty, unit_cost])

        def push_front(self, qty, unit_cost):
            _check(qty, unit_cost)
            if self._layers and self._layers[0][1] == unit_cost:
                self._layers[0][0] += qty
            else:
                self._layers.insert(0, [qty, unit_cost])

        @property
        def on_hand(self):
            return sum(q for q, _ in self._layers)

        @property
        def value(self):
            return sum(q * c for q, c in self._layers)

        def layers(self):
            return [(q, c) for q, c in self._layers]

        def take(self, qty):
            if qty <= 0:
                raise ValueError("quantity must be positive")
            if qty > self.on_hand:
                raise ValueError("insufficient stock")
            parts = []
            need = qty
            while need:
                q, c = self._layers[0]
                used = min(q, need)
                parts.append((used, used * c))
                if used == q:
                    self._layers.pop(0)
                else:
                    self._layers[0][0] -= used
                need -= used
            return parts

        def put_back(self, parts):
            for qty, cost in reversed(parts):
                self.push_front(qty, cost // qty)


    class AvgPool:
        def __init__(self):
            self.on_hand = 0
            self.value = 0

        def push(self, qty, unit_cost):
            _check(qty, unit_cost)
            self.on_hand += qty
            self.value += qty * unit_cost

        def take(self, qty):
            if qty <= 0:
                raise ValueError("quantity must be positive")
            if qty > self.on_hand:
                raise ValueError("insufficient stock")
            cost = round_div(self.value * qty, self.on_hand)
            self.on_hand -= qty
            self.value -= cost
            return [(qty, cost)]

        def put_back(self, parts):
            for qty, cost in parts:
                self.on_hand += qty
                self.value += cost
''')

COSTLAYERS_LEDGER = dd('''
    """A stock ledger: receipts, issues and customer returns for many SKUs."""
    from .layers import AvgPool, CostQueue
    from .money import round_div


    class Issue:
        def __init__(self, ref, sku, parts):
            self.ref = ref
            self.sku = sku
            self.parts = list(parts)
            self.qty = sum(q for q, _ in parts)
            self.cost = sum(c for _, c in parts)

        def outstanding(self):
            return sum(q for q, _ in self.parts)


    class Ledger:
        def __init__(self, method="fifo"):
            if method not in ("fifo", "avg"):
                raise ValueError(f"unknown costing method {method!r}")
            self.method = method
            self._pools = {}
            self._issues = {}

        def receive(self, sku, qty, unit_cost):
            pool = self._pools.get(sku)
            if pool is None:
                pool = CostQueue() if self.method == "fifo" else AvgPool()
                self._pools[sku] = pool
            pool.push(qty, unit_cost)

        def issue(self, sku, qty, ref):
            if ref in self._issues:
                raise ValueError(f"reference {ref!r} already used")
            if sku not in self._pools:
                raise KeyError(sku)
            parts = self._pools[sku].take(qty)
            issue = Issue(ref, sku, parts)
            self._issues[ref] = issue
            return issue

        def return_in(self, ref, qty):
            issue = self._issues[ref]
            if qty <= 0 or qty > issue.outstanding():
                raise ValueError("bad return quantity")
            restored = []
            need = qty
            while need:
                q, c = issue.parts[-1]
                used = min(q, need)
                credit = round_div(c * used, q)
                restored.append((used, credit))
                if used == q:
                    issue.parts.pop()
                else:
                    issue.parts[-1] = (q - used, c - credit)
                need -= used
            restored.reverse()
            self._pools[issue.sku].put_back(restored)
            return sum(c for _, c in restored)

        def on_hand(self, sku):
            pool = self._pools.get(sku)
            return pool.on_hand if pool else 0

        def value(self, sku):
            pool = self._pools.get(sku)
            return pool.value if pool else 0

        def skus(self):
            return sorted(self._pools)

        def cogs(self):
            return sum(c for issue in self._issues.values() for _, c in issue.parts)
''')

COSTLAYERS_REPORT = dd('''
    """Valuation report over a ledger."""
    from .money import fmt_cents


    def valuation(ledger):
        rows = []
        for sku in ledger.skus():
            qty = ledger.on_hand(sku)
            if qty > 0:
                rows.append((sku, qty, ledger.value(sku)))
        return rows


    def render(ledger):
        rows = valuation(ledger)
        if not rows:
            return "(no stock)"
        width = max(5, max(len(sku) for sku, _, _ in rows))
        lines = [f"{'SKU'.ljust(width)}  {'QTY':>6}  {'VALUE':>12}"]
        for sku, qty, value in rows:
            lines.append(f"{sku.ljust(width)}  {qty:>6}  {fmt_cents(value):>12}")
        total_qty = sum(qty for _, qty, _ in rows)
        total_value = sum(value for _, _, value in rows)
        lines.append(f"{'TOTAL'.ljust(width)}  {total_qty:>6}  {fmt_cents(total_value):>12}")
        return "\\n".join(lines)
''')

COSTLAYERS_VISIBLE = dd('''
    import unittest

    from costlayers.ledger import Ledger
    from costlayers.money import fmt_cents, round_div


    class BasicTests(unittest.TestCase):
        def test_round_div(self):
            self.assertEqual(round_div(10, 4), 3)

        def test_fmt(self):
            self.assertEqual(fmt_cents(123456), "1,234.56")

        def test_fifo_issue(self):
            led = Ledger("fifo")
            led.receive("bolt", 10, 100)
            led.receive("bolt", 10, 130)
            issue = led.issue("bolt", 15, "o1")
            self.assertEqual(issue.cost, 1650)


    if __name__ == "__main__":
        unittest.main()
''')

COSTLAYERS_HIDDEN_MONEY = dd('''
    import unittest

    from costlayers.money import fmt_cents, round_div


    class RoundDiv(unittest.TestCase):
        def test_values(self):
            self.assertEqual(round_div(5, 2), 3)
            self.assertEqual(round_div(4, 3), 1)
            self.assertEqual(round_div(5, 3), 2)
            self.assertEqual(round_div(0, 5), 0)
            self.assertEqual(round_div(1, 2), 1)
            self.assertEqual(round_div(1, 3), 0)
            self.assertEqual(round_div(7, 7), 1)
            self.assertEqual(round_div(1000, 1), 1000)
            self.assertEqual(round_div(99, 100), 1)
            self.assertEqual(round_div(49, 100), 0)
            self.assertEqual(round_div(50, 100), 1)

        def test_errors(self):
            with self.assertRaises(ValueError):
                round_div(1, 0)
            with self.assertRaises(ValueError):
                round_div(1, -3)
            with self.assertRaises(ValueError):
                round_div(-1, 3)


    class FmtCents(unittest.TestCase):
        def test_small(self):
            self.assertEqual(fmt_cents(0), "0.00")
            self.assertEqual(fmt_cents(5), "0.05")
            self.assertEqual(fmt_cents(50), "0.50")
            self.assertEqual(fmt_cents(123), "1.23")
            self.assertEqual(fmt_cents(99999), "999.99")

        def test_groups(self):
            self.assertEqual(fmt_cents(100000), "1,000.00")
            self.assertEqual(fmt_cents(123456789), "1,234,567.89")
            self.assertEqual(fmt_cents(100100000), "1,001,000.00")
            self.assertEqual(fmt_cents(100000000), "1,000,000.00")
            self.assertEqual(fmt_cents(100500), "1,005.00")

        def test_negative(self):
            self.assertEqual(fmt_cents(-5), "-0.05")
            self.assertEqual(fmt_cents(-150000), "-1,500.00")
            self.assertEqual(fmt_cents(-99), "-0.99")


    if __name__ == "__main__":
        unittest.main()
''')

COSTLAYERS_HIDDEN_LAYERS = dd('''
    import unittest

    from costlayers.layers import AvgPool, CostQueue


    class QueuePush(unittest.TestCase):
        def test_merge_equal_back_only(self):
            q = CostQueue()
            q.push(5, 100)
            q.push(3, 120)
            q.push(2, 120)
            self.assertEqual(q.layers(), [(5, 100), (5, 120)])
            q.push(1, 100)
            self.assertEqual(q.layers(), [(5, 100), (5, 120), (1, 100)])
            self.assertEqual(q.on_hand, 11)
            self.assertEqual(q.value, 500 + 600 + 100)

        def test_merge_single_layer(self):
            q = CostQueue()
            q.push(2, 50)
            q.push(3, 50)
            self.assertEqual(q.layers(), [(5, 50)])

        def test_empty(self):
            q = CostQueue()
            self.assertEqual(q.on_hand, 0)
            self.assertEqual(q.value, 0)
            self.assertEqual(q.layers(), [])

        def test_validation(self):
            q = CostQueue()
            for args in ((0, 10), (-1, 10), (1, -1)):
                with self.assertRaises(ValueError):
                    q.push(*args)
                with self.assertRaises(ValueError):
                    q.push_front(*args)
            q.push(1, 0)
            self.assertEqual(q.layers(), [(1, 0)])
            q.push_front(2, 0)
            self.assertEqual(q.layers(), [(3, 0)])

        def test_push_front(self):
            q = CostQueue()
            q.push(3, 120)
            q.push_front(2, 100)
            self.assertEqual(q.layers(), [(2, 100), (3, 120)])
            q.push_front(1, 100)
            self.assertEqual(q.layers(), [(3, 100), (3, 120)])
            q.push_front(4, 90)
            self.assertEqual(q.layers(), [(4, 90), (3, 100), (3, 120)])

        def test_push_front_ignores_back_layer(self):
            q = CostQueue()
            q.push(1, 50)
            q.push(1, 60)
            q.push_front(1, 60)
            self.assertEqual(q.layers(), [(1, 60), (1, 50), (1, 60)])


    class QueueTake(unittest.TestCase):
        def setUp(self):
            self.q = CostQueue()
            self.q.push(5, 100)
            self.q.push(5, 120)

        def test_take_across_layers(self):
            self.assertEqual(self.q.take(7), [(5, 500), (2, 240)])
            self.assertEqual(self.q.layers(), [(3, 120)])
            self.assertEqual(self.q.take(3), [(3, 360)])
            self.assertEqual(self.q.layers(), [])
            self.assertEqual(self.q.on_hand, 0)

        def test_partial_layer(self):
            self.assertEqual(self.q.take(2), [(2, 200)])
            self.assertEqual(self.q.layers(), [(3, 100), (5, 120)])

        def test_exact_layer_boundary(self):
            self.assertEqual(self.q.take(5), [(5, 500)])
            self.assertEqual(self.q.layers(), [(5, 120)])
            self.assertEqual(self.q.take(1), [(1, 120)])

        def test_everything(self):
            self.assertEqual(self.q.take(10), [(5, 500), (5, 600)])
            self.assertEqual(self.q.value, 0)

        def test_errors_leave_queue_alone(self):
            for n in (0, -2, 11):
                with self.assertRaises(ValueError):
                    self.q.take(n)
            self.assertEqual(self.q.layers(), [(5, 100), (5, 120)])

        def test_put_back_restores(self):
            parts = self.q.take(7)
            self.q.put_back(parts)
            self.assertEqual(self.q.layers(), [(5, 100), (5, 120)])
            self.assertTrue(all(isinstance(c, int) for _, c in self.q.layers()))

        def test_put_back_partial_parts_go_to_front(self):
            parts = self.q.take(7)
            self.q.put_back(parts[1:])
            self.assertEqual(self.q.layers(), [(5, 120)])
            self.q.put_back(parts[:1])
            self.assertEqual(self.q.layers(), [(5, 100), (5, 120)])

        def test_put_back_order(self):
            q = CostQueue()
            q.push(1, 10)
            q.push(1, 20)
            q.push(1, 30)
            parts = q.take(3)
            q.put_back(parts)
            self.assertEqual(q.layers(), [(1, 10), (1, 20), (1, 30)])
            self.assertEqual(q.take(1), [(1, 10)])


    class AvgPoolTests(unittest.TestCase):
        def test_exact(self):
            p = AvgPool()
            p.push(10, 100)
            p.push(10, 130)
            self.assertEqual((p.on_hand, p.value), (20, 2300))
            self.assertEqual(p.take(5), [(5, 575)])
            self.assertEqual((p.on_hand, p.value), (15, 1725))
            self.assertEqual(p.take(3), [(3, 345)])

        def test_rounds_once_over_whole_quantity(self):
            p = AvgPool()
            p.push(3, 100)
            p.push(4, 101)
            self.assertEqual(p.take(2), [(2, 201)])
            self.assertEqual((p.on_hand, p.value), (5, 503))
            self.assertEqual(p.take(5), [(5, 503)])
            self.assertEqual((p.on_hand, p.value), (0, 0))

        def test_half_up(self):
            p = AvgPool()
            p.push(2, 5)
            p.push(1, 6)
            self.assertEqual(p.take(1), [(1, 5)])
            self.assertEqual(p.take(1), [(1, 6)])
            self.assertEqual(p.take(1), [(1, 5)])

        def test_errors(self):
            p = AvgPool()
            p.push(2, 5)
            for n in (0, -1, 3):
                with self.assertRaises(ValueError):
                    p.take(n)
            self.assertEqual((p.on_hand, p.value), (2, 10))
            with self.assertRaises(ValueError):
                p.push(0, 5)
            with self.assertRaises(ValueError):
                p.push(1, -5)
            p.push(1, 0)
            self.assertEqual((p.on_hand, p.value), (3, 10))

        def test_put_back(self):
            p = AvgPool()
            p.push(3, 10)
            parts = p.take(2)
            self.assertEqual((p.on_hand, p.value), (1, 10))
            p.put_back(parts)
            self.assertEqual((p.on_hand, p.value), (3, 30))
            p.put_back([(2, 7), (1, 1)])
            self.assertEqual((p.on_hand, p.value), (6, 38))


    if __name__ == "__main__":
        unittest.main()
''')

COSTLAYERS_HIDDEN_LEDGER = dd('''
    import unittest

    from costlayers.ledger import Ledger
    from costlayers.report import render, valuation


    def fifo():
        led = Ledger("fifo")
        led.receive("A", 10, 100)
        led.receive("A", 10, 130)
        return led


    class Construction(unittest.TestCase):
        def test_methods(self):
            self.assertEqual(Ledger().method, "fifo")
            self.assertEqual(Ledger("avg").method, "avg")
            with self.assertRaises(ValueError):
                Ledger("lifo")


    class FifoLedger(unittest.TestCase):
        def test_issue_parts_and_cost(self):
            led = fifo()
            iss = led.issue("A", 15, "o1")
            self.assertEqual((iss.ref, iss.sku, iss.qty, iss.cost), ("o1", "A", 15, 1650))
            self.assertEqual(iss.parts, [(10, 1000), (5, 650)])
            self.assertEqual(led.on_hand("A"), 5)
            self.assertEqual(led.value("A"), 650)
            self.assertEqual(led.cogs(), 1650)

        def test_return_last_part_first(self):
            led = fifo()
            led.issue("A", 15, "o1")
            self.assertEqual(led.return_in("o1", 3), 390)
            self.assertEqual(led.on_hand("A"), 8)
            self.assertEqual(led.value("A"), 1040)
            self.assertEqual(led.cogs(), 1260)
            self.assertEqual(led._issues["o1"].parts, [(10, 1000), (2, 260)])

        def test_second_return_spans_parts_and_restores_order(self):
            led = fifo()
            led.issue("A", 15, "o1")
            led.return_in("o1", 3)
            self.assertEqual(led.return_in("o1", 4), 460)
            self.assertEqual(led.on_hand("A"), 12)
            self.assertEqual(led.value("A"), 1500)
            self.assertEqual(led.cogs(), 800)
            self.assertEqual(led._pools["A"].layers(), [(2, 100), (10, 130)])
            with self.assertRaises(ValueError):
                led.return_in("o1", 9)
            self.assertEqual(led.return_in("o1", 8), 800)
            self.assertEqual(led._pools["A"].layers(), [(10, 100), (10, 130)])
            self.assertEqual(led.cogs(), 0)
            with self.assertRaises(ValueError):
                led.return_in("o1", 1)

        def test_returned_units_are_sold_first(self):
            led = fifo()
            led.issue("A", 12, "o1")
            led.return_in("o1", 5)
            nxt = led.issue("A", 4, "o2")
            self.assertEqual(nxt.parts, [(3, 300), (1, 130)])

        def test_errors(self):
            led = fifo()
            led.issue("A", 4, "o1")
            with self.assertRaises(ValueError):
                led.issue("A", 1, "o1")
            with self.assertRaises(KeyError):
                led.issue("B", 1, "o2")
            with self.assertRaises(ValueError):
                led.issue("A", 17, "o3")
            led.issue("A", 16, "o3")  # a failed issue does not burn its reference
            with self.assertRaises(ValueError):
                led.issue("A", 1, "o4")
            self.assertEqual(led.on_hand("A"), 0)
            with self.assertRaises(KeyError):
                led.return_in("nope", 1)
            for n in (0, -1, 5):
                with self.assertRaises(ValueError):
                    led.return_in("o1", n)
            self.assertEqual(led.return_in("o1", 4), 400)

        def test_unknown_sku_queries(self):
            led = Ledger()
            self.assertEqual(led.on_hand("zzz"), 0)
            self.assertEqual(led.value("zzz"), 0)
            self.assertEqual(led.cogs(), 0)
            self.assertEqual(led.skus(), [])

        def test_skus_sorted(self):
            led = Ledger()
            led.receive("m", 1, 1)
            led.receive("b", 1, 1)
            led.receive("x", 1, 1)
            self.assertEqual(led.skus(), ["b", "m", "x"])

        def test_skus_are_independent(self):
            led = fifo()
            led.receive("B", 5, 7)
            iss = led.issue("B", 2, "b1")
            self.assertEqual(iss.cost, 14)
            self.assertEqual(led.on_hand("A"), 20)
            led.return_in("b1", 1)
            self.assertEqual(led.on_hand("B"), 4)
            self.assertEqual(led.value("B"), 28)
            self.assertEqual(led.value("A"), 2300)


    class AvgLedger(unittest.TestCase):
        def make(self):
            led = Ledger("avg")
            led.receive("B", 3, 100)
            led.receive("B", 4, 101)
            return led

        def test_issue(self):
            led = self.make()
            iss = led.issue("B", 2, "x")
            self.assertEqual(iss.cost, 201)
            self.assertEqual(iss.parts, [(2, 201)])
            self.assertEqual(led.on_hand("B"), 5)
            self.assertEqual(led.value("B"), 503)

        def test_return_rounds_each_step(self):
            led = self.make()
            led.issue("B", 2, "x")
            self.assertEqual(led.return_in("x", 1), 101)
            self.assertEqual((led.on_hand("B"), led.value("B")), (6, 604))
            self.assertEqual(led._issues["x"].parts, [(1, 100)])
            self.assertEqual(led.return_in("x", 1), 100)
            self.assertEqual((led.on_hand("B"), led.value("B")), (7, 704))
            self.assertEqual(led.cogs(), 0)

        def test_full_return_is_exact(self):
            led = self.make()
            led.issue("B", 5, "y")
            self.assertEqual(led.return_in("y", 5), 503)
            self.assertEqual((led.on_hand("B"), led.value("B")), (7, 704))


    class Report(unittest.TestCase):
        def test_valuation(self):
            led = Ledger()
            led.receive("b", 2, 50)
            led.receive("a", 1, 5)
            led.receive("c", 1, 7)
            led.issue("c", 1, "r")
            self.assertEqual(valuation(led), [("a", 1, 5), ("b", 2, 100)])

        def test_render_empty(self):
            self.assertEqual(render(Ledger()), "(no stock)")
            led = Ledger()
            led.receive("a", 1, 5)
            led.issue("a", 1, "r")
            self.assertEqual(render(led), "(no stock)")

        def test_render_table(self):
            led = Ledger()
            led.receive("b", 2, 50)
            led.receive("a", 1, 5)
            expected = "\\n".join([
                "SKU       QTY         VALUE",
                "a           1          0.05",
                "b           2          1.00",
                "TOTAL       3          1.05",
            ])
            self.assertEqual(render(led), expected)

        def test_render_wide_sku_and_groups(self):
            led = Ledger()
            led.receive("hex-bolt-m8", 1200, 150)
            led.receive("nut", 3, 1)
            expected = "\\n".join([
                "SKU             QTY         VALUE",
                "hex-bolt-m8    1200      1,800.00",
                "nut               3          0.03",
                "TOTAL          1203      1,800.03",
            ])
            self.assertEqual(render(led), expected)


    if __name__ == "__main__":
        unittest.main()
''')

COSTLAYERS = Lib(
    name="costlayers", lang="python", title="the costlayers inventory costing package",
    blurb="The wholesaler's back office uses the costlayers package to value stock and cost of goods sold with FIFO or moving-average costing.",
    files={
        "costlayers/__init__.py": "", "costlayers/money.py": COSTLAYERS_MONEY, "costlayers/layers.py": COSTLAYERS_LAYERS,
        "costlayers/ledger.py": COSTLAYERS_LEDGER, "costlayers/report.py": COSTLAYERS_REPORT,
        "README.md": COSTLAYERS_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": COSTLAYERS_VISIBLE},
    hidden_tests={
        "tests/test_money.py": COSTLAYERS_HIDDEN_MONEY, "tests/test_layers.py": COSTLAYERS_HIDDEN_LAYERS,
        "tests/test_ledger.py": COSTLAYERS_HIDDEN_LEDGER,
    },
    mutate=["costlayers/money.py", "costlayers/layers.py", "costlayers/ledger.py", "costlayers/report.py"],
    difficulty=4, tags=["inventory", "costing", "multi-module"],
    probes=[
        "fmt_cents(100100000)", "fmt_cents(-5)", "round_div(5, 2)",
        "_fifo_issue_cost()", "_fifo_return()", "_avg_return()", "_avg_issue()", "_after_return_next_issue()",
        "_queue_after_partial_take()", "_render_small()",
    ],
    probe_import=(
        "from costlayers.money import fmt_cents, round_div\n"
        "from costlayers.ledger import Ledger\n"
        "from costlayers.report import render\n"
        "def _led(m='fifo'):\n"
        "    led = Ledger(m)\n"
        "    led.receive('A', 10, 100)\n"
        "    led.receive('A', 10, 130)\n"
        "    return led\n"
        "def _fifo_issue_cost():\n"
        "    return _led().issue('A', 15, 'o1').parts\n"
        "def _fifo_return():\n"
        "    led = _led(); led.issue('A', 15, 'o1')\n"
        "    return [led.return_in('o1', 3), led.return_in('o1', 4), led.value('A'), led.cogs()]\n"
        "def _avg_issue():\n"
        "    led = Ledger('avg'); led.receive('B', 3, 100); led.receive('B', 4, 101)\n"
        "    return led.issue('B', 2, 'x').cost, led.value('B')\n"
        "def _avg_return():\n"
        "    led = Ledger('avg'); led.receive('B', 3, 100); led.receive('B', 4, 101)\n"
        "    led.issue('B', 2, 'x')\n"
        "    return [led.return_in('x', 1), led.return_in('x', 1), led.value('B')]\n"
        "def _after_return_next_issue():\n"
        "    led = _led(); led.issue('A', 12, 'o1'); led.return_in('o1', 5)\n"
        "    return led.issue('A', 4, 'o2').parts\n"
        "def _queue_after_partial_take():\n"
        "    led = _led(); led.issue('A', 7, 'o1'); return led._pools['A'].layers()\n"
        "def _render_small():\n"
        "    led = Ledger(); led.receive('b', 2, 50); led.receive('a', 1, 5); return render(led)\n"
    ),
)

LIBS = [COSTLAYERS]
register_libs(LIBS, n=10)
