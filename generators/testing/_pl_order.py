"""Python libraries for the order-dependence family: a plugin hub (process-wide state), a shopping cart (class-level fixtures), a note store (files).

The test file of each library is a template: ``@@slot@@`` lines are the first line of a test that needs a fixture. A *group* is an init test plus read-only
user tests; clean, every test builds its own fixture, dirty, only the init test does and the others read what it left behind.
"""
from __future__ import annotations

import re

from fx import dd

from ._engine import TLib
from ._engine3 import render_order

WHERE_PY = ("Put your tests in `tests/` (plain `unittest`; there is no pytest here). They are run from the repository root with "
            "`python3 -m unittest discover -s tests -t .`.")
CMD = "python3 -m unittest discover -s tests -t ."
INIT = "\n"


def _variants(init_clean, init_dirty, user_clean, user_dirty):
    return {"init_clean": init_clean, "init_dirty": init_dirty, "user_clean": user_clean, "user_dirty": user_dirty}


def _prepare(template: str, variants: dict) -> tuple[str, dict]:
    """Number the occurrences of ``@@g@@`` (``@@g#0@@`` is the init test of group g) and build the group table."""
    counts: dict[str, int] = {}

    def sub(m):
        g = m.group(1)
        counts[g] = counts.get(g, -1) + 1
        return f"@@{g}#{counts[g]}@@"

    numbered = re.sub(r"@@(" + "|".join(variants) + r")@@", sub, template)
    groups = {g: {"init": f"{g}#0", "slots": {f"{g}#{i}": v for i in range(counts[g] + 1)}} for g, v in variants.items()}
    return numbered, groups


def _lib(name, pkg, mod, title, blurb, readme, src, template, variants, focus, difficulty, smoke, leak):
    test_path = f"tests/test_{mod}.py"
    template, groups = _prepare(template, variants)
    gold = render_order(template, groups, set())
    return TLib(
        name=name, lang="python", title=title, blurb=blurb,
        files={"README.md": readme, f"{pkg}/__init__.py": INIT, f"{pkg}/{mod}.py": src, "tests/__init__.py": INIT},
        stub={"tests/test_smoke.py": smoke}, gold={test_path: gold}, mutate=[f"{pkg}/{mod}.py"], cmd=CMD, where=WHERE_PY, difficulty=difficulty, timeout=30, focus=focus,
        extra={"template": template, "groups": groups, "test_path": test_path, "leak": leak},
    )


# ---------------------------------------------------------------------------------------------------------------------
# plugin hub: module-level state
# ---------------------------------------------------------------------------------------------------------------------

HUB_README = dd('''
    # pluginhub

    A process-wide plugin hub: `pluginhub.hub`. It is a module with plain functions around one shared registry.

    * `register(name, fn, priority=0)` adds a plugin. `name` must be a non-empty string that is not in use (`ValueError` otherwise); `fn` is called with the event.
    * `unregister(name)` removes a plugin; an unknown name is a `KeyError`.
    * `names()` lists the plugin names in call order: higher `priority` first, equal priorities in the order of registration (a plugin that was unregistered and registered again
      counts as newly registered).
    * `run(event)` calls every plugin with the event in call order and returns the list of the return values. A plugin that raises an `Exception` is skipped (it adds nothing to
      the list) and its name is remembered until the next `run`.
    * `last_errors()` is the list of names (in call order) of the plugins that failed in the most recent `run`; `[]` before the first run.
    * `runs()` is the number of `run` calls since the last `reset()`.
    * `reset()` removes all plugins, forgets the errors and sets `runs()` back to 0.
''')

HUB_SRC = dd('''
    """A process-wide plugin hub."""

    _plugins = []
    _seq = 0
    _runs = 0
    _errors = []


    def reset():
        global _seq, _runs
        del _plugins[:]
        del _errors[:]
        _seq = 0
        _runs = 0


    def register(name, fn, priority=0):
        global _seq
        if not isinstance(name, str) or not name:
            raise ValueError("plugin name must be a non-empty string")
        if any(p[0] == name for p in _plugins):
            raise ValueError("duplicate plugin: " + name)
        _seq += 1
        _plugins.append((name, fn, priority, _seq))


    def unregister(name):
        for i, p in enumerate(_plugins):
            if p[0] == name:
                del _plugins[i]
                return
        raise KeyError(name)


    def _ordered():
        return sorted(_plugins, key=lambda p: (-p[2], p[3]))


    def names():
        return [p[0] for p in _ordered()]


    def run(event):
        global _runs
        _runs += 1
        del _errors[:]
        results = []
        for name, fn, _priority, _order in _ordered():
            try:
                results.append(fn(event))
            except Exception:
                _errors.append(name)
        return results


    def last_errors():
        return list(_errors)


    def runs():
        return _runs
''')

HUB_TEMPLATE = dd('''
    import unittest

    from pluginhub import hub


    def say(label):
        return lambda event: "%s:%s" % (label, event)


    def boom(event):
        raise RuntimeError("boom")


    def standard():
        hub.reset()
        hub.register("audit", say("audit"), priority=9)
        hub.register("sms", say("sms"), priority=5)
        hub.register("mail", say("mail"), priority=5)
        hub.register("log", say("log"))


    def with_a_failure():
        hub.reset()
        hub.register("good", say("good"), priority=1)
        hub.register("bad", boom, priority=5)
        hub.register("good2", say("good2"), priority=1)
        hub.run("e")


    def churned():
        hub.reset()
        hub.register("a", say("a"), priority=2)
        hub.register("b", say("b"), priority=2)
        hub.register("c", say("c"), priority=2)
        hub.unregister("a")
        hub.register("a", say("a"), priority=2)


    class HubTests(unittest.TestCase):
        def test_01_names_follow_priority_then_registration(self):
            @@std@@
            self.assertEqual(hub.names(), ["audit", "sms", "mail", "log"])

        def test_02_run_returns_results_in_call_order(self):
            @@std@@
            self.assertEqual(hub.run("x"), ["audit:x", "sms:x", "mail:x", "log:x"])

        def test_03_the_event_reaches_every_plugin(self):
            @@std@@
            seen = hub.run({"id": 7})
            self.assertEqual(len(seen), 4)
            self.assertEqual(seen[0], "audit:{'id': 7}")
            self.assertEqual(seen[3], "log:{'id': 7}")

        def test_10_a_failing_plugin_is_listed_among_the_names(self):
            @@fail@@
            self.assertEqual(hub.names(), ["bad", "good", "good2"])

        def test_11_the_failure_is_remembered(self):
            @@fail@@
            self.assertEqual(hub.last_errors(), ["bad"])

        def test_12_the_run_is_counted(self):
            @@fail@@
            self.assertEqual(hub.runs(), 1)

        def test_20_a_plugin_registered_again_goes_last_among_equals(self):
            @@churn@@
            self.assertEqual(hub.names(), ["b", "c", "a"])

        def test_21_run_follows_the_names(self):
            @@churn@@
            self.assertEqual(hub.run(1), ["b:1", "c:1", "a:1"])

        def test_50_names_must_be_unique_non_empty_strings(self):
            hub.reset()
            hub.register("one", say("one"))
            for bad in ("one", "", None, 5):
                with self.assertRaises(ValueError):
                    hub.register(bad, say("x"))
            self.assertEqual(hub.names(), ["one"])

        def test_51_unregister(self):
            hub.reset()
            hub.register("one", say("one"))
            hub.register("two", say("two"))
            hub.unregister("one")
            self.assertEqual(hub.names(), ["two"])
            with self.assertRaises(KeyError):
                hub.unregister("one")
            with self.assertRaises(KeyError):
                hub.unregister("never")

        def test_52_negative_priorities_come_last(self):
            hub.reset()
            hub.register("late", say("late"), priority=-1)
            hub.register("plain", say("plain"))
            hub.register("early", say("early"), priority=3)
            self.assertEqual(hub.names(), ["early", "plain", "late"])
            self.assertEqual(hub.run("q"), ["early:q", "plain:q", "late:q"])

        def test_53_failures_are_isolated_and_forgotten(self):
            hub.reset()
            hub.register("good", say("good"), priority=1)
            hub.register("bad", boom, priority=5)
            hub.register("worse", boom, priority=3)
            self.assertEqual(hub.last_errors(), [])
            self.assertEqual(hub.run("e"), ["good:e"])
            self.assertEqual(hub.last_errors(), ["bad", "worse"])
            hub.unregister("bad")
            hub.unregister("worse")
            self.assertEqual(hub.run("e"), ["good:e"])
            self.assertEqual(hub.last_errors(), [])

        def test_54_runs_are_counted_until_reset(self):
            hub.reset()
            self.assertEqual(hub.runs(), 0)
            self.assertEqual(hub.run("x"), [])
            hub.run("y")
            self.assertEqual(hub.runs(), 2)
            hub.reset()
            self.assertEqual(hub.runs(), 0)

        def test_55_reset_forgets_everything(self):
            hub.reset()
            hub.register("bad", boom)
            hub.run("x")
            hub.reset()
            self.assertEqual(hub.names(), [])
            self.assertEqual(hub.last_errors(), [])
            hub.register("bad", say("again"))
            self.assertEqual(hub.run("x"), ["again:x"])

        def test_56_an_exception_class_hierarchy_is_respected(self):
            hub.reset()

            def wrong(event):
                raise ValueError("no")

            def fine(event):
                return "fine"

            hub.register("wrong", wrong)
            hub.register("fine", fine)
            self.assertEqual(hub.run(None), ["fine"])
            self.assertEqual(hub.last_errors(), ["wrong"])
''')

HUB_STUB = dd('''
    import unittest

    from pluginhub import hub


    class SmokeTests(unittest.TestCase):
        def test_empty_hub(self):
            hub.reset()
            self.assertEqual(hub.names(), [])
''')


def pluginhub(rng) -> TLib:
    variants = {
        "std": _variants("standard()", "standard()", "standard()", ""),
        "fail": _variants("with_a_failure()", "with_a_failure()", "with_a_failure()", ""),
        "churn": _variants("churned()", "churned()", "churned()", ""),
    }
    return _lib("py-pluginhub", "pluginhub", "hub", "the plugin hub of the notification daemon", "The daemon loads its plugins into one process-wide hub and dispatches every event through it.",
                HUB_README, HUB_SRC, HUB_TEMPLATE, variants, "call order, re-registration, failure isolation and the run counter", 3, HUB_STUB, "global-state")


# ---------------------------------------------------------------------------------------------------------------------
# shopping cart: class-level fixtures
# ---------------------------------------------------------------------------------------------------------------------

CART_README = dd('''
    # cartkit

    A shopping cart with one coupon, tax and shipping: `cartkit.cart.Cart`. Money is an `int` number of cents.

    ## Construction
    `Cart(tax_percent=0)`; a negative `tax_percent` is a `ValueError`.

    ## Lines
    * `add(sku, qty, unit)` adds `qty` units at `unit` cents each. `qty` must be at least 1 and `unit` not negative (`ValueError`). Adding a sku that is already in the cart increases
      its quantity, but only at the same unit price; another price is a `ValueError`.
    * `remove(sku, qty=None)` removes `qty` units (all of them when `qty` is `None` or equal to the quantity in the cart; the line disappears). Removing more than the cart holds, or
      zero or fewer, is a `ValueError`; an unknown sku is a `KeyError`.
    * `lines()` lists `(sku, qty, unit)` tuples sorted by sku.

    ## Money
    * `subtotal()` is the sum of `qty * unit`.
    * `apply_coupon(code)` applies one coupon per cart (a second one is a `ValueError`, whatever its code). `SAVE10` takes 10% off the subtotal (the discount is rounded down).
      `FIVER` takes a flat 500 off but needs a subtotal of at least 2500 at the moment it is applied; the discount never exceeds the subtotal. Unknown codes and coupons that cannot
      be applied are a `ValueError` and change nothing.
    * `discount()` is the discount in cents (0 without a coupon), `net` below means subtotal minus discount.
    * `shipping()` is 0 for an empty cart and for a net of 5000 or more, otherwise 495.
    * `tax()` is `tax_percent` percent of the net, rounded half up.
    * `total()` is net + tax + shipping.
''')

CART_SRC = dd('''
    """A shopping cart with one coupon, tax and shipping. Money is an int number of cents."""

    SHIPPING = 495
    FREE_SHIPPING_OVER = 5000
    FIVER_MINIMUM = 2500


    class Cart:
        def __init__(self, tax_percent=0):
            if tax_percent < 0:
                raise ValueError("tax must not be negative")
            self._tax = tax_percent
            self._lines = {}
            self._coupon = None

        def add(self, sku, qty, unit):
            if qty < 1 or unit < 0:
                raise ValueError("bad quantity or price")
            line = self._lines.get(sku)
            if line is None:
                self._lines[sku] = [qty, unit]
            elif line[1] != unit:
                raise ValueError("price mismatch for " + sku)
            else:
                line[0] += qty

        def remove(self, sku, qty=None):
            line = self._lines[sku]
            if qty is None or qty == line[0]:
                del self._lines[sku]
            elif 0 < qty < line[0]:
                line[0] -= qty
            else:
                raise ValueError("cannot remove %s of %d" % (qty, line[0]))

        def lines(self):
            return [(sku, line[0], line[1]) for sku, line in sorted(self._lines.items())]

        def subtotal(self):
            return sum(q * u for q, u in self._lines.values())

        def apply_coupon(self, code):
            if self._coupon is not None:
                raise ValueError("a coupon is already applied")
            if code == "SAVE10":
                self._coupon = code
            elif code == "FIVER":
                if self.subtotal() < FIVER_MINIMUM:
                    raise ValueError("FIVER needs a subtotal of at least 2500")
                self._coupon = code
            else:
                raise ValueError("unknown coupon: " + str(code))

        def discount(self):
            if self._coupon == "SAVE10":
                return self.subtotal() * 10 // 100
            if self._coupon == "FIVER":
                return min(500, self.subtotal())
            return 0

        def _net(self):
            return self.subtotal() - self.discount()

        def shipping(self):
            if not self._lines:
                return 0
            return 0 if self._net() >= FREE_SHIPPING_OVER else SHIPPING

        def tax(self):
            return (self._net() * self._tax * 2 + 100) // 200

        def total(self):
            return self._net() + self.tax() + self.shipping()
''')

CART_TEMPLATE = dd('''
    import unittest

    from cartkit.cart import Cart


    def basket():
        cart = Cart(tax_percent=20)
        cart.add("pen", 3, 120)
        cart.add("ink", 1, 899)
        cart.add("pad", 2, 450)
        return cart


    def promo():
        cart = basket()
        cart.apply_coupon("SAVE10")
        return cart


    def big():
        cart = Cart()
        cart.add("desk", 1, 45000)
        cart.add("lamp", 2, 2500)
        cart.apply_coupon("FIVER")
        return cart


    class CartTests(unittest.TestCase):
        def test_01_subtotal(self):
            @@basket@@
            self.assertEqual(cart.subtotal(), 2159)

        def test_02_lines_are_sorted_by_sku(self):
            @@basket@@
            self.assertEqual(cart.lines(), [("ink", 1, 899), ("pad", 2, 450), ("pen", 3, 120)])

        def test_03_total_with_tax_and_shipping(self):
            @@basket@@
            self.assertEqual(cart.tax(), 432)
            self.assertEqual(cart.shipping(), 495)
            self.assertEqual(cart.total(), 3086)

        def test_10_percent_coupon_rounds_down(self):
            @@promo@@
            self.assertEqual(cart.discount(), 215)

        def test_11_total_after_the_coupon(self):
            @@promo@@
            self.assertEqual(cart.tax(), 389)
            self.assertEqual(cart.total(), 2828)

        def test_12_a_second_coupon_is_refused_and_changes_nothing(self):
            @@promo@@
            with self.assertRaises(ValueError):
                cart.apply_coupon("FIVER")
            self.assertEqual(cart.discount(), 215)
            self.assertEqual(cart.total(), 2828)

        def test_20_big_orders_ship_free(self):
            @@big@@
            self.assertEqual(cart.shipping(), 0)

        def test_21_flat_coupon(self):
            @@big@@
            self.assertEqual(cart.discount(), 500)
            self.assertEqual(cart.subtotal(), 50000)

        def test_22_total_of_a_big_order(self):
            @@big@@
            self.assertEqual(cart.total(), 49500)

        def test_50_adding_merges_lines_at_the_same_price(self):
            cart = Cart()
            cart.add("pen", 2, 100)
            cart.add("pen", 3, 100)
            self.assertEqual(cart.lines(), [("pen", 5, 100)])
            with self.assertRaises(ValueError):
                cart.add("pen", 1, 101)
            self.assertEqual(cart.lines(), [("pen", 5, 100)])

        def test_51_bad_lines_are_refused(self):
            cart = Cart()
            for qty, unit in ((0, 100), (-1, 100), (1, -1)):
                with self.assertRaises(ValueError):
                    cart.add("x", qty, unit)
            self.assertEqual(cart.lines(), [])
            cart.add("free", 1, 0)
            self.assertEqual(cart.subtotal(), 0)

        def test_52_remove(self):
            cart = Cart()
            cart.add("a", 5, 10)
            cart.add("b", 1, 7)
            cart.remove("a", 2)
            self.assertEqual(cart.lines(), [("a", 3, 10), ("b", 1, 7)])
            cart.remove("a", 3)
            self.assertEqual(cart.lines(), [("b", 1, 7)])
            cart.remove("b")
            self.assertEqual(cart.lines(), [])
            cart.add("c", 4, 5)
            for bad in (5, 0, -1):
                with self.assertRaises(ValueError):
                    cart.remove("c", bad)
            with self.assertRaises(KeyError):
                cart.remove("nope")
            self.assertEqual(cart.lines(), [("c", 4, 5)])
            cart.remove("c")
            self.assertEqual(cart.subtotal(), 0)

        def test_53_the_fiver_needs_2500(self):
            cart = Cart()
            cart.add("x", 1, 2499)
            with self.assertRaises(ValueError):
                cart.apply_coupon("FIVER")
            self.assertEqual(cart.discount(), 0)
            cart.add("y", 1, 1)
            cart.apply_coupon("FIVER")
            self.assertEqual(cart.discount(), 500)

        def test_54_other_coupon_codes(self):
            cart = Cart()
            cart.add("x", 1, 999)
            for bad in ("save10", "NOPE", "", None):
                with self.assertRaises(ValueError):
                    cart.apply_coupon(bad)
            cart.apply_coupon("SAVE10")
            self.assertEqual(cart.discount(), 99)

        def test_55_the_fiver_never_exceeds_the_subtotal(self):
            cart = Cart()
            cart.add("x", 1, 2500)
            cart.apply_coupon("FIVER")
            cart.remove("x")
            cart.add("y", 1, 300)
            self.assertEqual(cart.discount(), 300)
            self.assertEqual(cart.total(), 0 + 0 + 495)

        def test_56_an_empty_cart_costs_nothing(self):
            cart = Cart(tax_percent=20)
            self.assertEqual((cart.subtotal(), cart.discount(), cart.shipping(), cart.tax(), cart.total()), (0, 0, 0, 0, 0))

        def test_57_free_shipping_is_decided_after_the_discount(self):
            cart = Cart()
            cart.add("a", 1, 5000)
            self.assertEqual(cart.shipping(), 0)
            cart = Cart()
            cart.add("a", 1, 4999)
            self.assertEqual(cart.shipping(), 495)
            cart = Cart()
            cart.add("a", 1, 5200)
            cart.apply_coupon("SAVE10")
            self.assertEqual(cart.shipping(), 495)
            self.assertEqual(cart.total(), 5200 - 520 + 495)

        def test_58_tax_rounds_half_up(self):
            cart = Cart(tax_percent=10)
            cart.add("a", 1, 1005)
            self.assertEqual(cart.tax(), 101)
            cart = Cart(tax_percent=10)
            cart.add("a", 1, 1004)
            self.assertEqual(cart.tax(), 100)
            cart = Cart(tax_percent=10)
            cart.add("a", 1, 1006)
            self.assertEqual(cart.tax(), 101)
            cart = Cart()
            cart.add("a", 1, 1005)
            self.assertEqual(cart.tax(), 0)
            with self.assertRaises(ValueError):
                Cart(tax_percent=-1)

        def test_59_tax_is_charged_on_the_net(self):
            cart = Cart(tax_percent=25)
            cart.add("a", 1, 6000)
            cart.apply_coupon("SAVE10")
            self.assertEqual(cart.tax(), 1350)
            self.assertEqual(cart.total(), 5400 + 1350)
''')

CART_STUB = dd('''
    import unittest

    from cartkit.cart import Cart


    class SmokeTests(unittest.TestCase):
        def test_empty_cart(self):
            self.assertEqual(Cart().subtotal(), 0)
''')


def cartkit(rng) -> TLib:
    variants = {
        "basket": _variants("cart = basket()", "cart = type(self).basket = basket()", "cart = basket()", "cart = type(self).basket"),
        "promo": _variants("cart = promo()", "cart = type(self).promo = promo()", "cart = promo()", "cart = type(self).promo"),
        "big": _variants("cart = big()", "cart = type(self).big = big()", "cart = big()", "cart = type(self).big"),
    }
    return _lib("py-cartkit", "cartkit", "cart", "the shop's shopping cart", "The checkout page builds a `Cart` for every visitor and prices it with the coupon, tax and shipping rules.",
                CART_README, CART_SRC, CART_TEMPLATE, variants, "line merging and removal, the two coupons, the order of discount, shipping and tax, and rounding", 3, CART_STUB, "shared-fixture")


# ---------------------------------------------------------------------------------------------------------------------
# note store: files
# ---------------------------------------------------------------------------------------------------------------------

NOTES_README = dd('''
    # notestore

    A small note store that keeps its notes in a JSON file: `notestore.store.NoteStore`.

    ## Construction
    `NoteStore(path)` opens the file at `path`; a missing file is an empty store, an unreadable (invalid JSON) one is a `ValueError`. The `path` attribute returns the path.
    Every change is written to the file at once, so a second `NoteStore(path)` sees it.

    ## Methods
    * `add(title, body="", tags=())` stores a note and returns its id, an int: 1, 2, 3, ... Ids are never reused, not even after `delete` and not after reopening the file.
      The title is stripped and must not be empty afterwards (`ValueError`). Tags are stripped and lower-cased, blank ones dropped, duplicates removed, and kept sorted.
    * `get(note_id)` returns `{"title": ..., "body": ..., "tags": [...]}`; changing the returned dict or list does not change the store. Unknown id: `KeyError`.
    * `delete(note_id)` removes the note (unknown id: `KeyError`).
    * `search(term)` returns the ids (ascending) of the notes whose title or body contains the term, ignoring case, or that carry the term as a tag (exact match, ignoring case).
      The term is stripped first; an empty term finds nothing.
    * `titles()` lists the titles ordered by id.
    * `tag_counts()` maps every tag in use to the number of notes carrying it.
''')

NOTES_SRC = dd('''
    """A small note store backed by a JSON file."""
    import json
    import os


    class NoteStore:
        def __init__(self, path):
            self._path = path
            self._notes = {}
            self._next = 1
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    try:
                        data = json.load(fh)
                    except ValueError:
                        raise ValueError("corrupt note file: " + path)
                self._notes = {int(k): v for k, v in data["notes"].items()}
                self._next = data["next"]

        @property
        def path(self):
            return self._path

        def _save(self):
            data = {"next": self._next, "notes": {str(k): v for k, v in self._notes.items()}}
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, sort_keys=True)
            os.replace(tmp, self._path)

        def add(self, title, body="", tags=()):
            title = title.strip()
            if not title:
                raise ValueError("title must not be empty")
            clean = sorted({t.strip().lower() for t in tags if t.strip()})
            note_id = self._next
            self._next += 1
            self._notes[note_id] = {"title": title, "body": body, "tags": clean}
            self._save()
            return note_id

        def get(self, note_id):
            note = self._notes[note_id]
            return {"title": note["title"], "body": note["body"], "tags": list(note["tags"])}

        def delete(self, note_id):
            del self._notes[note_id]
            self._save()

        def search(self, term):
            needle = term.strip().lower()
            if not needle:
                return []
            hits = []
            for note_id in sorted(self._notes):
                note = self._notes[note_id]
                if needle in note["title"].lower() or needle in note["body"].lower() or needle in note["tags"]:
                    hits.append(note_id)
            return hits

        def titles(self):
            return [self._notes[i]["title"] for i in sorted(self._notes)]

        def tag_counts(self):
            counts = {}
            for note in self._notes.values():
                for tag in note["tags"]:
                    counts[tag] = counts.get(tag, 0) + 1
            return counts
''')

NOTES_TEMPLATE = dd('''
    import os
    import shutil
    import tempfile
    import unittest

    from notestore.store import NoteStore

    SCRATCH = os.path.join("tests", "_scratch", "notes.json")
    SCRATCH2 = os.path.join("tests", "_scratch", "after_delete.json")


    def tmp_path(test):
        d = tempfile.mkdtemp()
        test.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return os.path.join(d, "notes.json")


    def seeded(test, path=None):
        if path is None:
            path = tmp_path(test)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.exists(path):
                os.remove(path)
        store = NoteStore(path)
        store.add("Buy milk", "two litres", ["Errands", "home"])
        store.add("Call Ann", "about the roof", ["phone", "home"])
        store.add("Roof quote", "ask Ann for the number", ["home"])
        return store


    def after_delete(test, path=None):
        store = seeded(test, path)
        store.delete(2)
        return store


    class NoteTests(unittest.TestCase):
        def test_01_titles_in_id_order(self):
            @@disk@@
            self.assertEqual(store.titles(), ["Buy milk", "Call Ann", "Roof quote"])

        def test_02_search_looks_at_title_body_and_tags(self):
            @@disk@@
            self.assertEqual(store.search("ann"), [2, 3])
            self.assertEqual(store.search("ROOF"), [2, 3])
            self.assertEqual(store.search("home"), [1, 2, 3])
            self.assertEqual(store.search("errands"), [1])

        def test_03_tag_counts(self):
            @@disk@@
            self.assertEqual(store.tag_counts(), {"errands": 1, "home": 3, "phone": 1})

        def test_10_deleted_notes_are_gone(self):
            @@gone@@
            self.assertEqual(store.titles(), ["Buy milk", "Roof quote"])
            self.assertEqual(store.search("ann"), [3])
            with self.assertRaises(KeyError):
                store.get(2)

        def test_11_tag_counts_after_a_delete(self):
            @@gone@@
            self.assertEqual(store.tag_counts(), {"errands": 1, "home": 2})

        def test_12_ids_are_never_reused(self):
            @@gone@@
            self.assertEqual(store.add("Fresh"), 4)

        def test_50_add_and_get(self):
            store = NoteStore(tmp_path(self))
            self.assertEqual(store.add("  Plan  ", "details", ["B", " a ", "b", "", "  "]), 1)
            self.assertEqual(store.get(1), {"title": "Plan", "body": "details", "tags": ["a", "b"]})
            self.assertEqual(store.add("Second"), 2)
            self.assertEqual(store.get(2), {"title": "Second", "body": "", "tags": []})

        def test_51_titles_must_not_be_blank(self):
            store = NoteStore(tmp_path(self))
            for bad in ("", "   "):
                with self.assertRaises(ValueError):
                    store.add(bad)
            self.assertEqual(store.titles(), [])
            self.assertEqual(store.add("ok"), 1)

        def test_52_get_returns_copies(self):
            store = NoteStore(tmp_path(self))
            store.add("t", "b", ["x"])
            note = store.get(1)
            note["title"] = "changed"
            note["tags"].append("y")
            self.assertEqual(store.get(1), {"title": "t", "body": "b", "tags": ["x"]})
            with self.assertRaises(KeyError):
                store.get(9)

        def test_53_changes_reach_the_file(self):
            path = tmp_path(self)
            store = NoteStore(path)
            store.add("one", "", ["a"])
            store.add("two")
            store.delete(1)
            again = NoteStore(path)
            self.assertEqual(again.titles(), ["two"])
            self.assertEqual(again.get(2)["title"], "two")
            self.assertEqual(store.path, path)
            self.assertFalse(os.path.exists(path + ".tmp"))

        def test_54_ids_survive_a_reopen_and_a_delete(self):
            path = tmp_path(self)
            store = NoteStore(path)
            store.add("one")
            store.add("two")
            store.delete(2)
            self.assertEqual(NoteStore(path).add("three"), 3)

        def test_55_delete_unknown(self):
            store = NoteStore(tmp_path(self))
            store.add("one")
            with self.assertRaises(KeyError):
                store.delete(5)
            store.delete(1)
            with self.assertRaises(KeyError):
                store.delete(1)

        def test_56_search_rules(self):
            store = NoteStore(tmp_path(self))
            store.add("Alpha", "beta gamma", ["delta"])
            store.add("beta", "", [])
            self.assertEqual(store.search("  BETA "), [1, 2])
            self.assertEqual(store.search("delta"), [1])
            self.assertEqual(store.search("delt"), [])
            self.assertEqual(store.search("gamma"), [1])
            self.assertEqual(store.search(""), [])
            self.assertEqual(store.search("   "), [])
            self.assertEqual(store.search("zzz"), [])

        def test_57_a_corrupt_file_is_refused(self):
            path = tmp_path(self)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{not json")
            with self.assertRaises(ValueError):
                NoteStore(path)

        def test_58_a_missing_file_is_an_empty_store(self):
            path = tmp_path(self)
            store = NoteStore(path)
            self.assertEqual(store.titles(), [])
            self.assertEqual(store.tag_counts(), {})
            self.assertFalse(os.path.exists(path))
''')

NOTES_STUB = dd('''
    import os
    import tempfile
    import unittest

    from notestore.store import NoteStore


    class SmokeTests(unittest.TestCase):
        def test_empty_store(self):
            with tempfile.TemporaryDirectory() as d:
                self.assertEqual(NoteStore(os.path.join(d, "n.json")).titles(), [])
''')


def notestore(rng) -> TLib:
    variants = {
        "disk": _variants("store = seeded(self)", "store = seeded(self, SCRATCH)", "store = seeded(self)", "store = NoteStore(SCRATCH)"),
        "gone": _variants("store = after_delete(self)", "store = after_delete(self, SCRATCH2)", "store = after_delete(self)", "store = NoteStore(SCRATCH2)"),
    }
    return _lib("py-notestore", "notestore", "store", "the note store of the desktop app", "The desktop app keeps its notes in a JSON file managed by `NoteStore`.",
                NOTES_README, NOTES_SRC, NOTES_TEMPLATE, variants, "normalisation of titles and tags, search rules, persistence and id allocation", 3, NOTES_STUB, "shared-files")
