"""Warehouse and stock algorithms in domain clothes (python, fix-py-3): cost layers, crate loading, bay allocation, seating."""
from fx import Lib, dd

from generators.fix._pylib3 import chain, register_libs3

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

    `replay(method, events) -> Ledger` builds a ledger from a journal. Each event is a tuple applied in order:
    `("receive", sku, qty, unit_cost)`, `("issue", sku, qty, ref)` or `("return", ref, qty)`. Any other event kind is
    a `ValueError`; errors raised by the underlying calls propagate.

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


    def replay(method, events):
        ledger = Ledger(method)
        for ev in events:
            kind = ev[0]
            if kind == "receive":
                ledger.receive(*ev[1:])
            elif kind == "issue":
                ledger.issue(*ev[1:])
            elif kind == "return":
                ledger.return_in(*ev[1:])
            else:
                raise ValueError(f"unknown event {kind!r}")
        return ledger
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

    from costlayers.ledger import Ledger, replay
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
            iss = led.issue("A", 15, "o1")
            self.assertEqual(led.return_in("o1", 3), 390)
            self.assertEqual(led.on_hand("A"), 8)
            self.assertEqual(led.value("A"), 1040)
            self.assertEqual(led.cogs(), 1260)
            self.assertEqual(iss.parts, [(10, 1000), (2, 260)])

        def test_second_return_spans_parts_and_restores_order(self):
            led = fifo()
            led.issue("A", 15, "o1")
            led.return_in("o1", 3)
            self.assertEqual(led.return_in("o1", 4), 460)
            self.assertEqual(led.on_hand("A"), 12)
            self.assertEqual(led.value("A"), 1500)
            self.assertEqual(led.cogs(), 800)
            self.assertEqual(led.issue("A", 12, "probe").parts, [(2, 200), (10, 1300)])
            led.return_in("probe", 12)
            with self.assertRaises(ValueError):
                led.return_in("o1", 9)
            self.assertEqual(led.return_in("o1", 8), 800)
            self.assertEqual(led.issue("A", 20, "all").parts, [(10, 1000), (10, 1300)])
            led.return_in("all", 20)
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
            iss = led.issue("B", 2, "x")
            self.assertEqual(led.return_in("x", 1), 101)
            self.assertEqual((led.on_hand("B"), led.value("B")), (6, 604))
            self.assertEqual(iss.parts, [(1, 100)])
            self.assertEqual(led.return_in("x", 1), 100)
            self.assertEqual((led.on_hand("B"), led.value("B")), (7, 704))
            self.assertEqual(led.cogs(), 0)

        def test_full_return_is_exact(self):
            led = self.make()
            led.issue("B", 5, "y")
            self.assertEqual(led.return_in("y", 5), 503)
            self.assertEqual((led.on_hand("B"), led.value("B")), (7, 704))


    class Replay(unittest.TestCase):
        def test_journal(self):
            led = replay("fifo", [
                ("receive", "A", 10, 100), ("receive", "A", 10, 130), ("issue", "A", 15, "o1"),
                ("return", "o1", 3), ("receive", "B", 2, 9),
            ])
            self.assertEqual((led.on_hand("A"), led.value("A")), (8, 1040))
            self.assertEqual((led.on_hand("B"), led.value("B")), (2, 18))
            self.assertEqual(led.cogs(), 1260)
            self.assertEqual(led.method, "fifo")

        def test_avg_journal(self):
            led = replay("avg", [("receive", "B", 3, 100), ("receive", "B", 4, 101), ("issue", "B", 2, "x"), ("return", "x", 1)])
            self.assertEqual((led.on_hand("B"), led.value("B")), (6, 604))

        def test_empty(self):
            self.assertEqual(replay("avg", []).skus(), [])

        def test_unknown_event(self):
            with self.assertRaises(ValueError):
                replay("fifo", [("receive", "A", 1, 1), ("scrap", "A", 1)])

        def test_errors_propagate(self):
            with self.assertRaises(ValueError):
                replay("fifo", [("receive", "A", 1, 1), ("issue", "A", 2, "o")])
            with self.assertRaises(KeyError):
                replay("fifo", [("return", "zz", 1)])
            with self.assertRaises(ValueError):
                replay("lifo", [])


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

_F = "[('receive', 'A', 10, 100), ('receive', 'A', 10, 130)]"
_B = "[('receive', 'B', 3, 100), ('receive', 'B', 4, 101)]"

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
    difficulty=3, tags=["inventory", "costing", "multi-module"],
    probes=[
        "fmt_cents(100100000)", "fmt_cents(-5)", "round_div(5, 2)",
        f"replay('fifo', {_F} + [('issue', 'A', 15, 'o1')]).cogs()",
        f"replay('fifo', {_F} + [('issue', 'A', 15, 'o1'), ('return', 'o1', 3), ('return', 'o1', 4)]).value('A')",
        f"replay('fifo', {_F} + [('issue', 'A', 12, 'o1'), ('return', 'o1', 5), ('issue', 'A', 4, 'o2')]).cogs()",
        f"replay('fifo', {_F} + [('issue', 'A', 12, 'o1'), ('return', 'o1', 5)]).issue('A', 4, 'o2').parts",
        f"replay('fifo', {_F} + [('issue', 'A', 15, 'o1')]).on_hand('A')",
        f"replay('avg', {_B} + [('issue', 'B', 2, 'x')]).cogs()",
        f"replay('avg', {_B} + [('issue', 'B', 2, 'x'), ('return', 'x', 1), ('return', 'x', 1)]).value('B')",
        f"replay('avg', {_B} + [('issue', 'B', 2, 'x'), ('return', 'x', 1)]).on_hand('B')",
        "render(replay('fifo', [('receive', 'b', 2, 50), ('receive', 'a', 1, 5)]))",
    ],
    probe_import=(
        "from costlayers.money import fmt_cents, round_div\n"
        "from costlayers.ledger import Ledger, replay\n"
        "from costlayers.report import render\n"
    ),
)


# ======================================================================================================================
# crateload: parcel manifests packed into shipping crates (multi-module)
# ======================================================================================================================

CRATELOAD_README = dd('''
    # crateload

    A courier packs parcels into identical shipping crates. Weights are whole **grams**, volumes whole **cm3**.

    ## `crateload.parcels`

    `Parcel(id, weight, volume, flags="")` is a frozen dataclass. `flags` is a canonical string made of the letters
    `F` (fragile), `H` (hazmat) and `U` (must stay upright), always in that order and without repeats. The properties
    `fragile`, `hazmat` and `upright` tell whether the letter is present.

    `parse_manifest(text) -> list[Parcel]` reads one parcel per line: `id,weight,volume` or `id,weight,volume,flags`
    (spaces around fields are ignored). Everything after a `#` is a comment; blank lines (and comment-only lines) are
    skipped. Flags are case-insensitive and are normalised (`"uf"` becomes `"FU"`, `"FF"` becomes `"F"`). Parcels
    keep their line order. Every problem is a `ValueError` whose message starts with `line N:` (N counts physical
    lines from 1, including skipped ones): wrong number of fields, an empty id, a duplicate id, a weight or volume
    that is not a whole number of digits, a weight or volume below 1, an unknown flag letter.

    ## `crateload.crates`

    `Crate(cap_g, cap_cm3)` holds `parcels` (in the order they were added) and reports `weight` and `volume`
    (sums). `can_take(parcel)` is true when all of these hold:

    * total weight stays `<= cap_g` and total volume stays `<= cap_cm3` (exactly full is fine);
    * a hazmat parcel never shares a crate with a different fragile parcel, and a fragile parcel never shares a
      crate with a different hazmat parcel (a parcel that is both is therefore alone with respect to every other
      fragile or hazmat parcel);
    * a crate holds at most one upright parcel.

    `add(parcel)` appends it, or raises `ValueError` when `can_take` is false.

    ## `crateload.packer`

    `pack(parcels, cap_g, cap_cm3, strategy="ffd") -> list[Crate]` creates crates on demand (crate 1 first) and
    never reorders crates. Strategies:

    * `"ff"`: first fit, parcels in the given order: a parcel goes into the first crate that can take it.
    * `"ffd"`: first fit decreasing: the same, but parcels are first sorted by weight descending, then volume
      descending, then id ascending.
    * `"bfd"`: best fit decreasing: same order as `"ffd"`; a parcel goes into the crate that can take it and
      would be left with the *least free volume* afterwards; ties go to the earliest crate.

    A new crate is opened when no crate can take the parcel. A parcel that cannot go even into an empty crate raises
    `ValueError` naming its id (before anything else is returned). An unknown strategy is a `ValueError`.

    ## `crateload.report`

    * `pct(part, whole)`: `part / whole` as a percentage rounded half up to a whole number (integers only).
    * `lower_bound(parcels, cap_g, cap_cm3)`: the fewest crates any packing could use if only weight and volume
      mattered: the larger of `ceil(total weight / cap_g)` and `ceil(total volume / cap_cm3)`; `0` for no parcels.
    * `summary(crates) -> str`: one line per crate,
      `crate 2: 3 parcels, 1450 g (73%), 820 cm3 (41%)` (`1 parcel` in the singular; the percentages are `pct` of the
      crate's capacity), then a final line `2 crates, 5 parcels` (`1 crate`, `1 parcel`, `0 crates` in the
      singular/zero case). Lines are joined with `"\\n"`, no trailing newline.
    * `loading_sheet(text, cap_g, cap_cm3, strategy="ffd") -> str`: parses the manifest, packs it and returns the
      `summary` followed by an empty line and one line per crate `crate N: id id id` listing parcel ids in the order
      they were added to the crate.
''')

CRATELOAD_PARCELS = dd('''
    """Parcels and the manifest text format."""
    from dataclasses import dataclass

    FLAG_ORDER = "FHU"


    @dataclass(frozen=True)
    class Parcel:
        id: str
        weight: int  # grams
        volume: int  # cm3
        flags: str = ""

        @property
        def fragile(self) -> bool:
            return "F" in self.flags

        @property
        def hazmat(self) -> bool:
            return "H" in self.flags

        @property
        def upright(self) -> bool:
            return "U" in self.flags


    def _canon_flags(text: str, lineno: int) -> str:
        seen = set()
        for ch in text.upper():
            if ch not in FLAG_ORDER:
                raise ValueError(f"line {lineno}: unknown flag {ch!r}")
            seen.add(ch)
        return "".join(f for f in FLAG_ORDER if f in seen)


    def parse_manifest(text: str) -> list:
        parcels = []
        ids = set()
        for lineno, raw in enumerate(text.splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            fields = [f.strip() for f in line.split(",")]
            if len(fields) not in (3, 4):
                raise ValueError(f"line {lineno}: expected 3 or 4 fields, got {len(fields)}")
            pid, w, v = fields[:3]
            if not pid:
                raise ValueError(f"line {lineno}: empty id")
            if pid in ids:
                raise ValueError(f"line {lineno}: duplicate id {pid!r}")
            if not (w.isdigit() and v.isdigit()):
                raise ValueError(f"line {lineno}: weight and volume must be whole numbers")
            weight, volume = int(w), int(v)
            if weight < 1 or volume < 1:
                raise ValueError(f"line {lineno}: weight and volume must be positive")
            flags = _canon_flags(fields[3], lineno) if len(fields) == 4 else ""
            ids.add(pid)
            parcels.append(Parcel(pid, weight, volume, flags))
        return parcels
''')

CRATELOAD_CRATES = dd('''
    """A shipping crate and its loading rules."""

    MAX_UPRIGHT = 1


    class Crate:
        def __init__(self, cap_g: int, cap_cm3: int):
            self.cap_g = cap_g
            self.cap_cm3 = cap_cm3
            self.parcels = []

        @property
        def weight(self) -> int:
            return sum(p.weight for p in self.parcels)

        @property
        def volume(self) -> int:
            return sum(p.volume for p in self.parcels)

        def can_take(self, parcel) -> bool:
            if self.weight + parcel.weight > self.cap_g:
                return False
            if self.volume + parcel.volume > self.cap_cm3:
                return False
            if parcel.hazmat and any(q.fragile for q in self.parcels):
                return False
            if parcel.fragile and any(q.hazmat for q in self.parcels):
                return False
            if parcel.upright and sum(1 for q in self.parcels if q.upright) >= MAX_UPRIGHT:
                return False
            return True

        def add(self, parcel) -> None:
            if not self.can_take(parcel):
                raise ValueError(f"parcel {parcel.id} does not fit")
            self.parcels.append(parcel)
''')

CRATELOAD_PACKER = dd('''
    """First-fit and best-fit packing of parcels into crates."""
    from .crates import Crate

    STRATEGIES = ("ff", "ffd", "bfd")


    def _ordered(parcels, strategy):
        if strategy == "ff":
            return list(parcels)
        return sorted(parcels, key=lambda p: (-p.weight, -p.volume, p.id))


    def _best_fit(crates, parcel):
        best = None
        best_left = None
        for crate in crates:
            if crate.can_take(parcel):
                left = crate.cap_cm3 - crate.volume - parcel.volume
                if best is None or left < best_left:
                    best, best_left = crate, left
        return best


    def pack(parcels, cap_g, cap_cm3, strategy="ffd"):
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy {strategy!r}")
        order = _ordered(parcels, strategy)
        for p in order:
            if not Crate(cap_g, cap_cm3).can_take(p):
                raise ValueError(f"parcel {p.id} does not fit into an empty crate")
        crates = []
        for p in order:
            if strategy == "bfd":
                target = _best_fit(crates, p)
            else:
                target = next((c for c in crates if c.can_take(p)), None)
            if target is None:
                target = Crate(cap_g, cap_cm3)
                crates.append(target)
            target.add(p)
        return crates
''')

CRATELOAD_REPORT = dd('''
    """Summaries and loading sheets."""
    from .packer import pack
    from .parcels import parse_manifest


    def pct(part: int, whole: int) -> int:
        return (200 * part + whole) // (2 * whole)


    def lower_bound(parcels, cap_g: int, cap_cm3: int) -> int:
        if not parcels:
            return 0
        total_w = sum(p.weight for p in parcels)
        total_v = sum(p.volume for p in parcels)
        return max(-(-total_w // cap_g), -(-total_v // cap_cm3))


    def _count(n: int, word: str) -> str:
        return f"{n} {word}" if n == 1 else f"{n} {word}s"


    def summary(crates) -> str:
        lines = []
        for i, c in enumerate(crates, 1):
            lines.append(
                f"crate {i}: {_count(len(c.parcels), 'parcel')}, {c.weight} g ({pct(c.weight, c.cap_g)}%), "
                f"{c.volume} cm3 ({pct(c.volume, c.cap_cm3)}%)"
            )
        total = sum(len(c.parcels) for c in crates)
        lines.append(f"{_count(len(crates), 'crate')}, {_count(total, 'parcel')}")
        return "\\n".join(lines)


    def loading_sheet(text: str, cap_g: int, cap_cm3: int, strategy: str = "ffd") -> str:
        crates = pack(parse_manifest(text), cap_g, cap_cm3, strategy)
        lines = [summary(crates), ""]
        for i, c in enumerate(crates, 1):
            lines.append(f"crate {i}: " + " ".join(p.id for p in c.parcels))
        return "\\n".join(lines)
''')

CRATELOAD_VISIBLE = dd('''
    import unittest

    from crateload.packer import pack
    from crateload.parcels import Parcel, parse_manifest


    class BasicTests(unittest.TestCase):
        def test_parse(self):
            ps = parse_manifest("a,100,200\\nb, 50, 60, f\\n")
            self.assertEqual(ps, [Parcel("a", 100, 200, ""), Parcel("b", 50, 60, "F")])

        def test_pack_two(self):
            ps = [Parcel("a", 600, 100), Parcel("b", 600, 100)]
            self.assertEqual(len(pack(ps, 1000, 1000)), 2)


    if __name__ == "__main__":
        unittest.main()
''')

CRATELOAD_HIDDEN_PARCELS = dd('''
    import unittest

    from crateload.parcels import Parcel, parse_manifest


    class ParcelProps(unittest.TestCase):
        def test_flags(self):
            p = Parcel("x", 1, 1, "FU")
            self.assertTrue(p.fragile)
            self.assertTrue(p.upright)
            self.assertFalse(p.hazmat)
            q = Parcel("y", 1, 1, "H")
            self.assertTrue(q.hazmat)
            self.assertFalse(q.fragile or q.upright)
            self.assertEqual(Parcel("z", 1, 1).flags, "")

        def test_frozen_and_hashable(self):
            p = Parcel("x", 1, 2, "F")
            with self.assertRaises(Exception):
                p.weight = 5
            self.assertEqual(len({p, Parcel("x", 1, 2, "F")}), 1)


    class Manifest(unittest.TestCase):
        def test_basic_and_order(self):
            text = "p2,500,900\\np1, 20 , 30 ,H\\n"
            self.assertEqual(parse_manifest(text), [Parcel("p2", 500, 900, ""), Parcel("p1", 20, 30, "H")])

        def test_comments_and_blanks(self):
            text = "# header\\n\\n  \\na,1,2  # trailing\\n   # indented comment\\nb,3,4,u\\n"
            self.assertEqual(parse_manifest(text), [Parcel("a", 1, 2), Parcel("b", 3, 4, "U")])

        def test_empty(self):
            self.assertEqual(parse_manifest(""), [])
            self.assertEqual(parse_manifest("# nothing\\n"), [])

        def test_flags_normalised(self):
            got = parse_manifest("a,1,1,uf\\nb,1,1,FFF\\nc,1,1,hFu\\nd,1,1,\\ne,1,1,h")
            self.assertEqual([p.flags for p in got], ["FU", "F", "FHU", "", "H"])

        def test_errors_carry_line_numbers(self):
            cases = [
                ("a,1", 1), ("a,1,2,F,extra", 1), (",1,2", 1), ("a,x,2", 1), ("a,1,2.5", 1), ("a,-1,2", 1),
                ("a,0,2", 1), ("a,1,0", 1), ("a,1,2,Q", 1), ("a,1,2,FX", 1),
            ]
            for text, line in cases:
                with self.assertRaises(ValueError, msg=text) as cm:
                    parse_manifest(text)
                self.assertTrue(str(cm.exception).startswith(f"line {line}:"), (text, str(cm.exception)))

        def test_line_numbers_count_skipped_lines(self):
            with self.assertRaises(ValueError) as cm:
                parse_manifest("# c\\n\\na,1,2\\n\\nb,1\\n")
            self.assertTrue(str(cm.exception).startswith("line 5:"))

        def test_duplicate_id(self):
            with self.assertRaises(ValueError) as cm:
                parse_manifest("a,1,2\\nb,1,2\\na,3,4")
            self.assertTrue(str(cm.exception).startswith("line 3:"))

        def test_big_numbers(self):
            self.assertEqual(parse_manifest("a,1000000,250000"), [Parcel("a", 1000000, 250000)])


    if __name__ == "__main__":
        unittest.main()
''')

CRATELOAD_HIDDEN_CRATES = dd('''
    import unittest

    from crateload.crates import Crate
    from crateload.parcels import Parcel


    def P(i, w=100, v=100, f=""):
        return Parcel(i, w, v, f)


    class CrateRules(unittest.TestCase):
        def test_empty(self):
            c = Crate(1000, 500)
            self.assertEqual((c.weight, c.volume, c.parcels), (0, 0, []))

        def test_weight_limit_inclusive(self):
            c = Crate(1000, 10000)
            c.add(P("a", 600))
            self.assertTrue(c.can_take(P("b", 400)))
            self.assertFalse(c.can_take(P("b", 401)))
            c.add(P("b", 400))
            self.assertEqual(c.weight, 1000)
            self.assertFalse(c.can_take(P("c", 1)))

        def test_volume_limit_inclusive(self):
            c = Crate(10000, 1000)
            c.add(P("a", 1, 700))
            self.assertTrue(c.can_take(P("b", 1, 300)))
            self.assertFalse(c.can_take(P("b", 1, 301)))
            c.add(P("b", 1, 300))
            self.assertEqual(c.volume, 1000)

        def test_single_parcel_may_fill_crate(self):
            self.assertTrue(Crate(1000, 500).can_take(P("a", 1000, 500)))
            self.assertFalse(Crate(1000, 500).can_take(P("a", 1001, 500)))
            self.assertFalse(Crate(1000, 500).can_take(P("a", 1000, 501)))

        def test_hazmat_vs_fragile(self):
            c = Crate(10000, 10000)
            c.add(P("f", f="F"))
            self.assertFalse(c.can_take(P("h", f="H")))
            self.assertTrue(c.can_take(P("g", f="F")))
            self.assertTrue(c.can_take(P("n")))
            d = Crate(10000, 10000)
            d.add(P("h", f="H"))
            self.assertFalse(d.can_take(P("f", f="F")))
            self.assertTrue(d.can_take(P("h2", f="H")))
            self.assertTrue(d.can_take(P("n")))

        def test_both_flags(self):
            both = P("fh", f="FH")
            c = Crate(10000, 10000)
            c.add(both)
            self.assertFalse(c.can_take(P("f", f="F")))
            self.assertFalse(c.can_take(P("h", f="H")))
            self.assertTrue(c.can_take(P("plain")))
            d = Crate(10000, 10000)
            d.add(P("f", f="F"))
            self.assertFalse(d.can_take(both))
            e = Crate(10000, 10000)
            e.add(P("h", f="H"))
            self.assertFalse(e.can_take(both))

        def test_one_upright(self):
            c = Crate(10000, 10000)
            c.add(P("u1", f="U"))
            self.assertFalse(c.can_take(P("u2", f="U")))
            self.assertTrue(c.can_take(P("n")))
            self.assertTrue(c.can_take(P("f", f="F")))
            c.add(P("n"))
            self.assertFalse(c.can_take(P("u3", f="FU")))

        def test_add_raises_and_keeps_order(self):
            c = Crate(300, 300)
            for i in "bca":
                c.add(P(i))
            self.assertEqual([p.id for p in c.parcels], ["b", "c", "a"])
            with self.assertRaises(ValueError):
                c.add(P("d"))
            self.assertEqual(len(c.parcels), 3)


    if __name__ == "__main__":
        unittest.main()
''')

CRATELOAD_HIDDEN_PACKER = dd('''
    import unittest

    from crateload.packer import pack
    from crateload.parcels import Parcel
    from crateload.report import loading_sheet, lower_bound, pct, summary


    def P(i, w, v, f=""):
        return Parcel(i, w, v, f)


    PARCELS = [P("A", 600, 300), P("B", 500, 600), P("C", 400, 200), P("D", 300, 500), P("E", 200, 100)]


    def ids(crates):
        return [[p.id for p in c.parcels] for c in crates]


    class Strategies(unittest.TestCase):
        def test_ffd(self):
            self.assertEqual(ids(pack(PARCELS, 1000, 1000, "ffd")), [["A", "C"], ["B", "E"], ["D"]])

        def test_default_is_ffd(self):
            self.assertEqual(ids(pack(PARCELS[::-1], 1000, 1000)), [["A", "C"], ["B", "E"], ["D"]])

        def test_ff_keeps_input_order(self):
            self.assertEqual(ids(pack(PARCELS[::-1], 1000, 1000, "ff")), [["E", "D", "C"], ["B"], ["A"]])
            self.assertEqual(ids(pack(PARCELS, 1000, 1000, "ff")), [["A", "C"], ["B", "E"], ["D"]])

        def test_bfd(self):
            self.assertEqual(ids(pack(PARCELS, 1000, 1000, "bfd")), [["A", "D"], ["B", "C"], ["E"]])

        def test_bfd_tie_goes_to_earliest_crate(self):
            ps = [P("a", 900, 500), P("b", 800, 500), P("c", 100, 100)]
            # c fits both crates and leaves 400 free volume in either: the earlier crate wins
            self.assertEqual(ids(pack(ps, 1000, 1000, "bfd")), [["a", "c"], ["b"]])

        def test_ffd_sort_ties(self):
            ps = [P("z", 500, 100), P("y", 500, 300), P("x", 500, 300), P("w", 400, 900)]
            got = pack(ps, 600, 1000, "ffd")
            self.assertEqual(ids(got), [["x"], ["y"], ["z"], ["w"]])

        def test_ffd_sort_weight_first(self):
            ps = [P("light", 100, 900), P("heavy", 200, 100)]
            got = pack(ps, 250, 1000, "ffd")
            self.assertEqual(ids(got), [["heavy"], ["light"]])
            self.assertEqual(ids(pack(ps, 250, 1000, "bfd")), [["heavy"], ["light"]])

        def test_empty_input(self):
            for s in ("ff", "ffd", "bfd"):
                self.assertEqual(pack([], 100, 100, s), [])

        def test_input_not_modified(self):
            ps = list(PARCELS[::-1])
            pack(ps, 1000, 1000, "ffd")
            self.assertEqual([p.id for p in ps], ["E", "D", "C", "B", "A"])

        def test_exactly_full_crates(self):
            ps = [P("a", 500, 500), P("b", 500, 500), P("c", 500, 500)]
            self.assertEqual(ids(pack(ps, 1000, 1000)), [["a", "b"], ["c"]])

        def test_rules_apply_when_packing(self):
            ps = [P("f1", 100, 100, "F"), P("h1", 100, 100, "H"), P("n1", 100, 100), P("u1", 100, 100, "U"), P("u2", 100, 100, "U")]
            got = pack(ps, 1000, 1000, "ff")
            self.assertEqual(ids(got), [["f1", "n1", "u1"], ["h1", "u2"]])

        def test_errors(self):
            with self.assertRaises(ValueError):
                pack(PARCELS, 1000, 1000, "random")
            with self.assertRaises(ValueError) as cm:
                pack([P("ok", 1, 1), P("huge", 2000, 1)], 1000, 1000)
            self.assertIn("huge", str(cm.exception))
            with self.assertRaises(ValueError) as cm:
                pack([P("ok", 1, 1), P("wide", 1, 1001)], 1000, 1000, "ff")
            self.assertIn("wide", str(cm.exception))


    class Report(unittest.TestCase):
        def test_pct(self):
            self.assertEqual(pct(1, 2), 50)
            self.assertEqual(pct(1, 3), 33)
            self.assertEqual(pct(2, 3), 67)
            self.assertEqual(pct(1, 8), 13)  # 12.5 rounds up
            self.assertEqual(pct(0, 7), 0)
            self.assertEqual(pct(7, 7), 100)
            self.assertEqual(pct(1, 200), 1)  # 0.5 rounds up
            self.assertEqual(pct(1, 201), 0)

        def test_lower_bound(self):
            self.assertEqual(lower_bound([], 100, 100), 0)
            self.assertEqual(lower_bound(PARCELS, 1000, 1000), 2)  # weight 2000/1000, volume 1700/1000
            self.assertEqual(lower_bound(PARCELS, 5000, 600), 3)  # volume 1700 / 600
            self.assertEqual(lower_bound([P("a", 1, 1)], 100, 100), 1)
            self.assertEqual(lower_bound([P("a", 101, 1)], 100, 100), 2)
            self.assertEqual(lower_bound([P("a", 100, 1), P("b", 100, 1)], 100, 100), 2)
            self.assertEqual(lower_bound([P("a", 1, 100), P("b", 1, 100), P("c", 1, 1)], 100, 100), 3)

        def test_summary(self):
            got = summary(pack(PARCELS, 1000, 1000, "ffd"))
            expected = "\\n".join([
                "crate 1: 2 parcels, 1000 g (100%), 500 cm3 (50%)",
                "crate 2: 2 parcels, 700 g (70%), 700 cm3 (70%)",
                "crate 3: 1 parcel, 300 g (30%), 500 cm3 (50%)",
                "3 crates, 5 parcels",
            ])
            self.assertEqual(got, expected)

        def test_summary_singular_and_empty(self):
            self.assertEqual(summary(pack([P("a", 1, 1)], 3, 8)), "crate 1: 1 parcel, 1 g (33%), 1 cm3 (13%)\\n1 crate, 1 parcel")
            self.assertEqual(summary([]), "0 crates, 0 parcels")

        def test_loading_sheet(self):
            text = "# run 7\\nC,400,200\\nA,600,300\\nB,500,600\\n"
            got = loading_sheet(text, 1000, 1000)
            expected = "\\n".join([
                "crate 1: 2 parcels, 1000 g (100%), 500 cm3 (50%)",
                "crate 2: 1 parcel, 500 g (50%), 600 cm3 (60%)",
                "2 crates, 3 parcels",
                "",
                "crate 1: A C",
                "crate 2: B",
            ])
            self.assertEqual(got, expected)
            self.assertTrue(loading_sheet(text, 1000, 1000, "ff").endswith("crate 1: C A\\ncrate 2: B"))

        def test_loading_sheet_errors(self):
            with self.assertRaises(ValueError):
                loading_sheet("a,1", 100, 100)
            with self.assertRaises(ValueError):
                loading_sheet("a,1,1", 100, 100, "nope")


    if __name__ == "__main__":
        unittest.main()
''')

_CM = "'a,600,300\\nb,500,600,F\\nc,400,200,H\\nd,300,500\\ne,200,100,U\\nf,150,150,U'"

CRATELOAD = Lib(
    name="crateload", lang="python", title="the crateload parcel packing package",
    blurb="The courier's dispatch tool uses crateload to read a day's parcel manifest and decide how many crates to load.",
    files={
        "crateload/__init__.py": "", "crateload/parcels.py": CRATELOAD_PARCELS, "crateload/crates.py": CRATELOAD_CRATES,
        "crateload/packer.py": CRATELOAD_PACKER, "crateload/report.py": CRATELOAD_REPORT,
        "README.md": CRATELOAD_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": CRATELOAD_VISIBLE},
    hidden_tests={
        "tests/test_parcels.py": CRATELOAD_HIDDEN_PARCELS, "tests/test_crates.py": CRATELOAD_HIDDEN_CRATES,
        "tests/test_packer.py": CRATELOAD_HIDDEN_PACKER,
    },
    mutate=["crateload/parcels.py", "crateload/crates.py", "crateload/packer.py", "crateload/report.py"],
    difficulty=3, tags=["packing", "logistics", "multi-module"],
    probes=[
        "parse_manifest('a,1,2,uf\\nb,3,4')", "parse_manifest('# c\\n\\nb,1')",
        f"[[p.id for p in c.parcels] for c in pack(parse_manifest({_CM}), 1000, 1000, 'bfd')]",
        f"[[p.id for p in c.parcels] for c in pack(parse_manifest({_CM}), 1000, 1000, 'ffd')]",
        f"[[p.id for p in c.parcels] for c in pack(parse_manifest({_CM}), 1000, 1000, 'ff')]",
        f"summary(pack(parse_manifest({_CM}), 1000, 1000))",
        "pct(1, 8)", "pct(1, 200)",
        f"lower_bound(parse_manifest({_CM}), 1000, 700)",
        f"loading_sheet({_CM}, 1000, 1000, 'bfd')",
    ],
    probe_import="from crateload.parcels import parse_manifest\nfrom crateload.packer import pack\nfrom crateload.report import pct, lower_bound, summary, loading_sheet\n",
)


# ======================================================================================================================
# buddybay: power-of-two bay allocation in a cold-storage row
# ======================================================================================================================

BUDDYBAY_README = dd('''
    # buddybay

    A cold-storage warehouse has one long row of `total` identical bays, numbered from 0. Pallets are stored in
    blocks of adjacent bays allocated with the *buddy system*: block sizes are powers of two, and every block of size
    `s` starts at an offset that is a multiple of `s`.

    ## `BayMap(total, min_block=1)`

    `total` and `min_block` must both be powers of two (1, 2, 4, ...) and `min_block <= total`, otherwise
    `ValueError`. The row starts as one free block `(0, total)`.

    * `block_size(n) -> int`: the size a request for `n` bays gets: the smallest power of two that is `>= n` and
      `>= min_block`. `ValueError` if `n < 1` or `n > total`.
    * `alloc(n) -> int | None`: allocate a block for `n` bays (validated like `block_size`) and return its offset, or
      `None` when no free block is big enough. The allocator uses the **smallest free block size that is large
      enough**, and among free blocks of that size the **lowest offset**. A larger block is split in halves until it
      has the wanted size; the lower half is kept for splitting further and the upper half becomes free.
    * `free(offset) -> int`: release the block that was allocated at `offset` and return its size. `KeyError` if no
      allocated block starts there (including a block that was already freed). The freed block is merged with its
      buddy (the block at `offset ^ size`) whenever that buddy is entirely free *and of the same size*, and the merge
      repeats with the merged block, up to the full row.
    * `size_of(offset) -> int`: size of an allocated block (`KeyError` if there is none).
    * `free_blocks() -> list[(offset, size)]`: every free block, sorted by offset.
    * `used_bays()`, `free_bays()`: the number of bays in allocated (rounded-up) blocks and in free blocks.
    * `largest_free()`: size of the biggest free block, `0` if there is none.
    * `fragmentation() -> int`: how much of the free space is not in the largest free block, as a percentage rounded
      *down*: `100 * (free_bays - largest_free) // free_bays`; `0` when nothing is free.
    * `render() -> str`: one character per `min_block` bays: `.` for free space; an allocated block of `u` such units
      is drawn `#` if `u == 1`, `[]` if `u == 2`, and `[` + `=` * (u - 2) + `]` otherwise.
''')

BUDDYBAY_SRC = dd('''
    """Buddy-system bay allocator."""
    import bisect


    def _is_pow2(n: int) -> bool:
        return n > 0 and n & (n - 1) == 0


    class BayMap:
        def __init__(self, total: int, min_block: int = 1):
            if not (_is_pow2(total) and _is_pow2(min_block)) or min_block > total:
                raise ValueError("total and min_block must be powers of two with min_block <= total")
            self.total = total
            self.min_block = min_block
            self._free = {total: [0]}  # block size -> sorted offsets
            self._used = {}  # offset -> block size

        def block_size(self, n: int) -> int:
            if n < 1 or n > self.total:
                raise ValueError("request must be between 1 and the row length")
            size = self.min_block
            while size < n:
                size *= 2
            return size

        def _insert(self, size: int, offset: int) -> None:
            bisect.insort(self._free.setdefault(size, []), offset)

        def alloc(self, n: int):
            want = self.block_size(n)
            size = want
            while size <= self.total and not self._free.get(size):
                size *= 2
            if size > self.total:
                return None
            offset = self._free[size].pop(0)
            while size > want:
                size //= 2
                self._insert(size, offset + size)
            self._used[offset] = want
            return offset

        def free(self, offset: int) -> int:
            if offset not in self._used:
                raise KeyError(offset)
            size = self._used.pop(offset)
            freed = size
            while size < self.total:
                buddy = offset ^ size
                peers = self._free.get(size, [])
                if buddy not in peers:
                    break
                peers.remove(buddy)
                offset = min(offset, buddy)
                size *= 2
            self._insert(size, offset)
            return freed

        def size_of(self, offset: int) -> int:
            return self._used[offset]

        def free_blocks(self) -> list:
            return sorted((off, size) for size, offs in self._free.items() for off in offs)

        def used_bays(self) -> int:
            return sum(self._used.values())

        def free_bays(self) -> int:
            return self.total - self.used_bays()

        def largest_free(self) -> int:
            return max((size for size, offs in self._free.items() if offs), default=0)

        def fragmentation(self) -> int:
            free = self.free_bays()
            if free == 0:
                return 0
            return 100 * (free - self.largest_free()) // free

        def render(self) -> str:
            cells = ["."] * (self.total // self.min_block)
            for offset, size in self._used.items():
                units = size // self.min_block
                first = offset // self.min_block
                if units == 1:
                    cells[first] = "#"
                else:
                    cells[first] = "["
                    cells[first + units - 1] = "]"
                    for i in range(first + 1, first + units - 1):
                        cells[i] = "="
            return "".join(cells)
''')

BUDDYBAY_VISIBLE = dd('''
    import unittest

    from buddybay.bays import BayMap


    class BasicTests(unittest.TestCase):
        def test_first_alloc_is_at_zero(self):
            m = BayMap(16)
            self.assertEqual(m.alloc(4), 0)
            self.assertEqual(m.free_blocks(), [(4, 4), (8, 8)])

        def test_rounding(self):
            self.assertEqual(BayMap(16).block_size(5), 8)


    if __name__ == "__main__":
        unittest.main()
''')

BUDDYBAY_HIDDEN = dd('''
    import random
    import unittest

    from buddybay.bays import BayMap


    class Construction(unittest.TestCase):
        def test_valid(self):
            m = BayMap(16, 2)
            self.assertEqual(m.free_blocks(), [(0, 16)])
            self.assertEqual((m.total, m.min_block), (16, 2))
            BayMap(1)
            BayMap(8, 8)

        def test_invalid(self):
            for args in ((0,), (3,), (12, 2), (16, 3), (16, 0), (4, 8), (-4,), (16, -2)):
                with self.assertRaises(ValueError, msg=str(args)):
                    BayMap(*args)


    class BlockSize(unittest.TestCase):
        def test_sizes(self):
            m = BayMap(16, 2)
            got = [m.block_size(n) for n in (1, 2, 3, 4, 5, 8, 9, 16)]
            self.assertEqual(got, [2, 2, 4, 4, 8, 8, 16, 16])
            m1 = BayMap(16)
            self.assertEqual([m1.block_size(n) for n in (1, 2, 3, 7, 8)], [1, 2, 4, 8, 8])

        def test_errors(self):
            m = BayMap(16, 2)
            for n in (0, -1, 17):
                with self.assertRaises(ValueError):
                    m.block_size(n)
                with self.assertRaises(ValueError):
                    m.alloc(n)


    class AllocFree(unittest.TestCase):
        def test_walkthrough(self):
            m = BayMap(16, 2)
            self.assertEqual(m.alloc(3), 0)
            self.assertEqual(m.free_blocks(), [(4, 4), (8, 8)])
            self.assertEqual(m.size_of(0), 4)
            self.assertEqual(m.alloc(2), 4)
            self.assertEqual(m.free_blocks(), [(6, 2), (8, 8)])
            self.assertEqual(m.alloc(8), 8)
            self.assertEqual(m.free_blocks(), [(6, 2)])
            self.assertIsNone(m.alloc(4))
            self.assertIsNone(m.alloc(3))
            self.assertEqual(m.alloc(1), 6)
            self.assertEqual(m.free_blocks(), [])
            self.assertIsNone(m.alloc(1))
            self.assertEqual(m.free(4), 2)
            self.assertEqual(m.free_blocks(), [(4, 2)])
            self.assertEqual(m.free(6), 2)
            self.assertEqual(m.free_blocks(), [(4, 4)])
            self.assertEqual(m.free(0), 4)
            self.assertEqual(m.free_blocks(), [(0, 8)])
            self.assertEqual(m.free(8), 8)
            self.assertEqual(m.free_blocks(), [(0, 16)])

        def test_smallest_sufficient_block_is_used(self):
            m = BayMap(16)
            a = m.alloc(4)   # 0..4
            b = m.alloc(4)   # 4..8
            c = m.alloc(2)   # 8..10, free: 10..12, 12..16
            self.assertEqual((a, b, c), (0, 4, 8))
            self.assertEqual(m.free_blocks(), [(10, 2), (12, 4)])
            m.free(a)
            self.assertEqual(m.free_blocks(), [(0, 4), (10, 2), (12, 4)])
            self.assertEqual(m.alloc(2), 10)  # the size-2 block, not the size-4 ones
            self.assertEqual(m.alloc(3), 0)   # size 4: lowest offset
            self.assertEqual(m.alloc(4), 12)

        def test_lowest_offset_among_equal_blocks(self):
            m = BayMap(16)
            offs = [m.alloc(4) for _ in range(4)]
            self.assertEqual(offs, [0, 4, 8, 12])
            m.free(12)
            m.free(4)
            self.assertEqual(m.free_blocks(), [(4, 4), (12, 4)])
            self.assertEqual(m.alloc(1), 4)
            self.assertEqual(m.free_blocks(), [(5, 1), (6, 2), (12, 4)])

        def test_buddy_must_be_free_and_same_size(self):
            m = BayMap(8)
            a = m.alloc(2)  # 0
            b = m.alloc(1)  # 2
            c = m.alloc(1)  # 3
            self.assertEqual((a, b, c), (0, 2, 3))
            self.assertEqual(m.free_blocks(), [(4, 4)])
            m.free(a)
            self.assertEqual(m.free_blocks(), [(0, 2), (4, 4)])  # buddy (2..4) is only partly free
            m.free(c)
            self.assertEqual(m.free_blocks(), [(0, 2), (3, 1), (4, 4)])  # buddy of 3 is 2: still allocated
            m.free(b)
            self.assertEqual(m.free_blocks(), [(0, 8)])

        def test_merge_cascades_to_full_row(self):
            m = BayMap(8)
            offs = [m.alloc(1) for _ in range(8)]
            self.assertEqual(offs, list(range(8)))
            for off in (0, 2, 4, 6, 1, 3, 5, 7):
                m.free(off)
            self.assertEqual(m.free_blocks(), [(0, 8)])

        def test_whole_row(self):
            m = BayMap(8)
            self.assertEqual(m.alloc(8), 0)
            self.assertIsNone(m.alloc(1))
            self.assertEqual(m.free(0), 8)
            self.assertEqual(m.free_blocks(), [(0, 8)])

        def test_errors(self):
            m = BayMap(8)
            off = m.alloc(2)
            for bad in (1, 3, 7, 99, -1):
                with self.assertRaises(KeyError):
                    m.free(bad)
            with self.assertRaises(KeyError):
                m.size_of(5)
            m.free(off)
            with self.assertRaises(KeyError):
                m.free(off)

        def test_random_workload_invariants(self):
            rng = random.Random(7)
            m = BayMap(64, 2)
            live = {}
            for step in range(400):
                if live and rng.random() < 0.45:
                    off = rng.choice(sorted(live))
                    self.assertEqual(m.free(off), live.pop(off))
                else:
                    n = rng.choice([1, 2, 3, 4, 6, 8, 12])
                    off = m.alloc(n)
                    if off is not None:
                        size = m.block_size(n)
                        self.assertEqual(off % size, 0)
                        live[off] = size
                blocks = sorted([(o, s) for o, s in live.items()] + m.free_blocks())
                pos = 0
                for o, s in blocks:
                    self.assertEqual(o, pos)
                    self.assertEqual(o % s, 0)
                    pos += s
                self.assertEqual(pos, 64)
                self.assertEqual(m.used_bays(), sum(live.values()))
            for off in sorted(live):
                m.free(off)
            self.assertEqual(m.free_blocks(), [(0, 64)])


    class Stats(unittest.TestCase):
        def test_counts(self):
            m = BayMap(16, 2)
            self.assertEqual((m.used_bays(), m.free_bays(), m.largest_free()), (0, 16, 16))
            m.alloc(3)
            m.alloc(2)
            self.assertEqual((m.used_bays(), m.free_bays(), m.largest_free()), (6, 10, 8))
            m.alloc(8)
            self.assertEqual((m.used_bays(), m.free_bays(), m.largest_free()), (14, 2, 2))
            m.alloc(2)
            self.assertEqual((m.used_bays(), m.free_bays(), m.largest_free()), (16, 0, 0))

        def test_fragmentation(self):
            m = BayMap(16)
            self.assertEqual(m.fragmentation(), 0)
            for _ in range(8):
                m.alloc(2)
            for off in (2, 6, 10):
                m.free(off)
            self.assertEqual(m.free_blocks(), [(2, 2), (6, 2), (10, 2)])
            self.assertEqual(m.fragmentation(), 66)  # 100 * (6 - 2) // 6
            m.free(14)
            self.assertEqual(m.free_blocks(), [(2, 2), (6, 2), (10, 2), (14, 2)])
            self.assertEqual(m.fragmentation(), 75)
            m = BayMap(8)
            m.alloc(8)
            self.assertEqual(m.fragmentation(), 0)  # nothing free

        def test_fragmentation_single_free_block(self):
            m = BayMap(8)
            m.alloc(2)
            self.assertEqual(m.free_blocks(), [(2, 2), (4, 4)])
            self.assertEqual(m.fragmentation(), 33)
            m.alloc(2)
            self.assertEqual(m.fragmentation(), 0)


    class Render(unittest.TestCase):
        def test_render(self):
            m = BayMap(16, 2)
            self.assertEqual(m.render(), "........")
            m.alloc(3)
            self.assertEqual(m.render(), "[]......")
            m.alloc(2)
            self.assertEqual(m.render(), "[]#.....")
            m.alloc(8)
            self.assertEqual(m.render(), "[]#.[==]")
            m.alloc(1)
            self.assertEqual(m.render(), "[]##[==]")

        def test_render_unit_one(self):
            m = BayMap(8)
            m.alloc(1)
            m.alloc(2)
            m.alloc(4)
            self.assertEqual(m.render(), "#.[]" + "[==]")
            m.free(0)
            self.assertEqual(m.render(), "..[][==]")


    if __name__ == "__main__":
        unittest.main()
''')

BUDDYBAY = Lib(
    name="buddybay", lang="python", title="the buddybay allocator (`buddybay/bays.py`)",
    blurb="The cold-storage warehouse system uses buddybay to hand out blocks of adjacent bays to incoming pallets.",
    files={"buddybay/__init__.py": "", "buddybay/bays.py": BUDDYBAY_SRC, "README.md": BUDDYBAY_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": BUDDYBAY_VISIBLE},
    hidden_tests={"tests/test_full.py": BUDDYBAY_HIDDEN},
    mutate=["buddybay/bays.py"], difficulty=2, tags=["allocator", "buddy-system"],
    probes=[
        "BayMap(16, 2).block_size(5)", "BayMap(16).block_size(9)",
        chain("BayMap(16, 2)", ["alloc(3)", "alloc(2)", "alloc(8)", "alloc(4)", "free(4)", "free(0)", "free_blocks()"]),
        chain("BayMap(16, 2)", ["alloc(3)", "alloc(2)", "free(0)", "alloc(1)", "free_blocks()"]),
        chain("BayMap(16)", ["alloc(4)", "alloc(4)", "alloc(2)", "free(0)", "alloc(2)", "alloc(3)", "free_blocks()"]),
        chain("BayMap(16)", ["alloc(2)", "alloc(2)", "alloc(2)", "alloc(2)", "free(2)", "free(6)", "free_blocks()", "fragmentation()"]),
        chain("BayMap(16, 2)", ["alloc(1)", "alloc(2)", "alloc(4)", "render()", "used_bays()", "largest_free()"]),
        chain("BayMap(8)", ["alloc(8)", "alloc(1)", "free(0)", "free_blocks()"]),
    ],
    probe_import="from buddybay.bays import BayMap\n",
)


# ======================================================================================================================
# seatblock: seating groups in a theatre hall
# ======================================================================================================================

SEATBLOCK_README = dd('''
    # seatblock

    Seat selection for group bookings in a small theatre. A hall is a list of rows; each row is a string with one
    character per seat: `.` free, `*` taken, `#` not a seat (a pillar, a wheelchair bay, a broken seat). Rows may
    have different lengths. Rows are numbered from 0 (the front) and seats from 0 (the left).

    ## `Hall(rows)`

    `ValueError` if a row contains any other character. `Hall.rows` is a list of lists of characters (mutable).

    * `ideal_row`: the preferred row, `(number_of_rows - 1) // 2`.
    * `free_seats() -> int`: number of `.` seats.
    * `candidates(k) -> list[(row, start)]`: every place where `k` free seats sit next to each other in one row, in
      row order and then left to right. `ValueError` if `k < 1`.
    * `best_block(k) -> (row, start) | None`: the best candidate, or `None` if there is none. Candidates are
      compared by this key, smallest wins:
      1. *orphans*: look at the free seats directly left of the block and directly right of it. A side whose run of
         free seats is **exactly one** seat long would leave a single unsellable seat behind and counts as one
         orphan (so the number of orphans is 0, 1 or 2; a run of two or more, or no free seat, is fine);
      2. the distance of the row from `ideal_row`;
      3. how far the block is from the middle of its row: `abs(2 * start + k - len(row))`;
      4. the row number, then 5. the start seat.
    * `book(k) -> list[(row, seat)] | None`: marks the seats of `best_block(k)` as `*` and returns them left to right;
      `None` (and nothing changes) if there is no block.
    * `book_groups(sizes, largest_first=False) -> list`: books every group with `book` and returns the results in the
      order of `sizes` (a group that cannot be seated gives `None` and does not stop the others). With
      `largest_first=True` the groups are *booked* from the largest to the smallest (equal sizes keep their order),
      but the results are still reported in the order of `sizes`.
    * `cancel(seats)`: frees seats given as `(row, seat)` pairs. Every pair must currently be `*`; otherwise
      `ValueError` is raised and *no* seat is changed (an unknown row or seat number counts as an error too).
    * `render() -> str`: the rows as strings joined by `"\\n"`.
''')

SEATBLOCK_SRC = dd('''
    """Seat selection for group bookings."""

    VALID = ".*#"


    class Hall:
        def __init__(self, rows):
            for row in rows:
                if any(ch not in VALID for ch in row):
                    raise ValueError(f"bad seat character in {row!r}")
            self.rows = [list(row) for row in rows]

        @property
        def ideal_row(self) -> int:
            return (len(self.rows) - 1) // 2

        def free_seats(self) -> int:
            return sum(row.count(".") for row in self.rows)

        @staticmethod
        def _run(row, col, step) -> int:
            n = 0
            col += step
            while 0 <= col < len(row) and row[col] == ".":
                n += 1
                col += step
            return n

        def candidates(self, k: int) -> list:
            if k < 1:
                raise ValueError("group size must be at least 1")
            found = []
            for r, row in enumerate(self.rows):
                for start in range(len(row) - k + 1):
                    if all(ch == "." for ch in row[start:start + k]):
                        found.append((r, start))
            return found

        def _key(self, r: int, start: int, k: int):
            row = self.rows[r]
            left = self._run(row, start, -1)
            right = self._run(row, start + k - 1, 1)
            orphans = (left == 1) + (right == 1)
            return (orphans, abs(r - self.ideal_row), abs(2 * start + k - len(row)), r, start)

        def best_block(self, k: int):
            found = self.candidates(k)
            if not found:
                return None
            return min(found, key=lambda c: self._key(c[0], c[1], k))

        def book(self, k: int):
            spot = self.best_block(k)
            if spot is None:
                return None
            r, start = spot
            for col in range(start, start + k):
                self.rows[r][col] = "*"
            return [(r, col) for col in range(start, start + k)]

        def book_groups(self, sizes, largest_first: bool = False) -> list:
            order = list(range(len(sizes)))
            if largest_first:
                order.sort(key=lambda i: (-sizes[i], i))
            results = [None] * len(sizes)
            for i in order:
                results[i] = self.book(sizes[i])
            return results

        def cancel(self, seats) -> None:
            for r, col in seats:
                if not (0 <= r < len(self.rows) and 0 <= col < len(self.rows[r])) or self.rows[r][col] != "*":
                    raise ValueError(f"seat {(r, col)} is not booked")
            for r, col in seats:
                self.rows[r][col] = "."

        def render(self) -> str:
            return "\\n".join("".join(row) for row in self.rows)
''')

SEATBLOCK_VISIBLE = dd('''
    import unittest

    from seatblock.hall import Hall


    class BasicTests(unittest.TestCase):
        def test_book_centre(self):
            h = Hall(["......"] * 3)
            self.assertEqual(h.book(2), [(1, 2), (1, 3)])

        def test_bad_row(self):
            with self.assertRaises(ValueError):
                Hall(["..?"])


    if __name__ == "__main__":
        unittest.main()
''')

SEATBLOCK_HIDDEN = dd('''
    import unittest

    from seatblock.hall import Hall


    class Basics(unittest.TestCase):
        def test_construction(self):
            h = Hall([".*#", ".."])
            self.assertEqual(h.rows, [[".", "*", "#"], [".", "."]])
            self.assertEqual(h.free_seats(), 3)
            self.assertEqual(Hall([]).free_seats(), 0)
            for bad in ("..X", ". .", ".o", "x"):
                with self.assertRaises(ValueError):
                    Hall([bad])

        def test_ideal_row(self):
            got = [Hall(["."] * n).ideal_row for n in (1, 2, 3, 4, 5, 6)]
            self.assertEqual(got, [0, 0, 1, 1, 2, 2])

        def test_candidates(self):
            h = Hall(["..*..", "#...."])
            self.assertEqual(h.candidates(2), [(0, 0), (0, 3), (1, 1), (1, 2), (1, 3)])
            self.assertEqual(h.candidates(1), [(0, 0), (0, 1), (0, 3), (0, 4), (1, 1), (1, 2), (1, 3), (1, 4)])
            self.assertEqual(h.candidates(4), [(1, 1)])
            self.assertEqual(h.candidates(5), [])
            self.assertEqual(h.candidates(9), [])
            with self.assertRaises(ValueError):
                h.candidates(0)
            with self.assertRaises(ValueError):
                h.candidates(-1)


    class Choice(unittest.TestCase):
        def test_middle_of_middle_row(self):
            h = Hall(["......"] * 3)
            self.assertEqual(h.best_block(2), (1, 2))
            self.assertEqual(h.book(2), [(1, 2), (1, 3)])
            self.assertEqual(h.render(), "......\\n..**..\\n......")

        def test_sequence(self):
            h = Hall(["......"] * 3)
            self.assertEqual(h.book(2), [(1, 2), (1, 3)])
            self.assertEqual(h.book(2), [(1, 0), (1, 1)])
            self.assertEqual(h.book(2), [(1, 4), (1, 5)])
            self.assertEqual(h.book(2), [(0, 2), (0, 3)])
            self.assertEqual(h.book(2), [(2, 2), (2, 3)])
            self.assertEqual(h.free_seats(), 18 - 10)

        def test_odd_group_in_odd_row(self):
            h = Hall(["....."])
            self.assertEqual(h.book(1), [(0, 2)])
            self.assertEqual(h.render(), "..*..")

        def test_orphan_rule_beats_centre(self):
            h = Hall(["*......"])
            # starts 2 and 3 are the most central but would leave a lone seat on the left / right
            self.assertEqual(h.best_block(3), (0, 1))
            h2 = Hall(["......*"])
            self.assertEqual(h2.best_block(3), (0, 3))

        def test_exact_gap_has_no_orphans(self):
            h = Hall([".*...*."])
            self.assertEqual(h.best_block(3), (0, 2))  # a free run of exactly 3, both neighbours taken
            h = Hall(["*....*"])
            # k=3 -> starts 1 and 2 each leave one orphan; the centre rule decides, then the lower start
            self.assertEqual(h.best_block(3), (0, 1))
            h = Hall(["*.....*", "*.....*"])
            self.assertEqual(h.best_block(3), (0, 1))

        def test_orphan_counts_only_runs_of_exactly_one(self):
            h = Hall(["*.....*"])
            # k=2: start 1 (right run 3, no orphan), 2 (left run 1), 3 (right run 1), 4 (left run 3, no orphan)
            self.assertEqual(h.best_block(2), (0, 1))
            h = Hall(["*....*"])
            # k=2: start 1: right run 2 -> fine; start 2: both runs 1 -> two orphans; start 3: left run 2 -> fine
            self.assertEqual(h.best_block(2), (0, 1))

        def test_row_distance_beats_row_centre(self):
            h = Hall(["......", "*.....", "......", "......", "......"])
            self.assertEqual(h.ideal_row, 2)
            self.assertEqual(h.best_block(2), (2, 2))
            h = Hall(["......", "......", "******", "......", "......"])
            self.assertEqual(h.best_block(2), (1, 2))  # rows 1 and 3 are equally far: the lower row number wins

        def test_orphans_beat_row_distance(self):
            h = Hall(["....", "...", "...."])
            self.assertEqual(h.ideal_row, 1)
            # the ideal row only offers blocks that leave a lone seat, the front row does not
            self.assertEqual(h.best_block(2), (0, 0))

        def test_pillars_block(self):
            h = Hall([".#.."])
            self.assertEqual(h.candidates(2), [(0, 2)])
            self.assertEqual(h.book(2), [(0, 2), (0, 3)])
            self.assertIsNone(h.book(2))

        def test_none_when_full_or_too_big(self):
            h = Hall(["**", ".#."])
            self.assertIsNone(h.best_block(2))
            self.assertIsNone(h.book(2))
            self.assertEqual(h.render(), "**\\n.#.")
            self.assertIsNone(h.book(7))

        def test_rows_of_different_length(self):
            h = Hall(["..", "........"])
            self.assertEqual(h.book(2), [(0, 0), (0, 1)])
            self.assertEqual(h.book(2), [(1, 3), (1, 4)])

        def test_centre_uses_each_rows_own_length(self):
            h = Hall(["*......*", "*...*"])
            self.assertEqual(h.ideal_row, 0)
            self.assertEqual(h.best_block(1), (0, 3))


    class Groups(unittest.TestCase):
        def test_in_given_order(self):
            h = Hall(["....", "....", "...."])
            got = h.book_groups([3, 4, 2])
            self.assertEqual(got[0], [(1, 0), (1, 1), (1, 2)])
            self.assertEqual(got[1], [(0, 0), (0, 1), (0, 2), (0, 3)])
            self.assertEqual(got[2], [(2, 0), (2, 1)])

        def test_failed_group_does_not_stop_others(self):
            h = Hall(["...", "..."])
            got = h.book_groups([4, 2, 3, 1])
            self.assertIsNone(got[0])
            self.assertEqual(got[1], [(0, 0), (0, 1)])
            self.assertEqual(got[2], [(1, 0), (1, 1), (1, 2)])
            self.assertEqual(got[3], [(0, 2)])

        def test_largest_first_reports_in_input_order(self):
            plain = Hall(["....", "..."]).book_groups([2, 4, 3])
            big = Hall(["....", "..."]).book_groups([2, 4, 3], largest_first=True)
            self.assertEqual(plain, [[(0, 0), (0, 1)], None, [(1, 0), (1, 1), (1, 2)]])
            self.assertEqual(big, [None, [(0, 0), (0, 1), (0, 2), (0, 3)], [(1, 0), (1, 1), (1, 2)]])

        def test_equal_sizes_keep_order(self):
            h = Hall(["....", "...."])
            got = h.book_groups([2, 3, 2], largest_first=True)
            # the 3 goes first, then the first 2, then the second 2
            self.assertEqual(got[1], [(0, 0), (0, 1), (0, 2)])
            self.assertEqual(got[0], [(1, 0), (1, 1)])
            self.assertEqual(got[2], [(1, 2), (1, 3)])

        def test_empty(self):
            self.assertEqual(Hall(["..."]).book_groups([]), [])


    class Cancel(unittest.TestCase):
        def test_cancel(self):
            h = Hall(["...."])
            seats = h.book(3)
            h.cancel(seats[:2])
            self.assertEqual(h.render(), "..*.")
            h.cancel(seats[2:])
            self.assertEqual(h.render(), "....")

        def test_cancel_is_all_or_nothing(self):
            h = Hall(["..*#", "**.."])
            for bad in ([(0, 2), (0, 0)], [(0, 2), (0, 3)], [(0, 2), (5, 0)], [(0, 2), (2, 0)], [(0, 2), (0, 9)], [(0, 2), (1, 4)], [(0, 2), (1, 2)], [(0, 2), (-1, 0)], [(0, 2), (0, -1)]):
                with self.assertRaises(ValueError):
                    h.cancel(bad)
                self.assertEqual(h.render(), "..*#\\n**..")
            h.cancel([(0, 2), (1, 0)])
            self.assertEqual(h.render(), "..." + "#" + "\\n" + ".*..")


    if __name__ == "__main__":
        unittest.main()
''')

SEATBLOCK = Lib(
    name="seatblock", lang="python", title="the seatblock group-seating package (`seatblock/hall.py`)",
    blurb="The theatre's box-office system uses seatblock to choose seats for group bookings.",
    files={"seatblock/__init__.py": "", "seatblock/hall.py": SEATBLOCK_SRC, "README.md": SEATBLOCK_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": SEATBLOCK_VISIBLE},
    hidden_tests={"tests/test_full.py": SEATBLOCK_HIDDEN},
    mutate=["seatblock/hall.py"], difficulty=1, tags=["booking", "heuristic"],
    probes=[
        "Hall(['......'] * 3).best_block(2)", "Hall(['*......']).best_block(3)", "Hall(['*....*']).best_block(2)",
        "Hall(['......', '......', '******', '......', '......']).best_block(2)",
        "Hall(['..', '........']).best_block(2)", "Hall(['.#..']).candidates(2)",
        chain("Hall(['....', '....'])", ["book_groups([1, 4, 2])", "render()"]),
        chain("Hall(['....', '....'])", ["book_groups([1, 4, 2], largest_first=True)"]),
        chain("Hall(['....'])", ["book(3)", "cancel([(0, 0), (0, 1)])", "render()"]),
    ],
    probe_import="from seatblock.hall import Hall\n",
)

LIBS = [COSTLAYERS, CRATELOAD, BUDDYBAY, SEATBLOCK]
register_libs3(LIBS, n=10)
