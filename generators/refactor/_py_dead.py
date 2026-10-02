"""Small python projects for dead-code removal: clean base code, harness, cases and planted dead-code items.

Each item is a list of edits (``("replace", path, old, new)`` or ``("append", path, text)``) that plant dead code in the clean base, plus
the facts the hidden check needs (names, constants, imports, comment markers, shadowed definitions). The base code also contains things that
*look* unused but are live: decorator registries, name-based dispatch, package exports and helpers that only the tests call.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------------------------------------------------
# ledgerlite
# ---------------------------------------------------------------------------------------------------------------------
LEDGERLITE = {
    "ledgerlite/__init__.py": '''"""A tiny double-entry ledger."""
from .core import balance, post
from .exporters import export_rows
from .render import render_statement
from .util import month_key

__all__ = ["balance", "month_key", "post", "export_rows", "render_statement"]
''',
    "ledgerlite/util.py": '''"""Small helpers."""


def month_key(day):
    """'2024-03-17' -> '2024-03'."""
    return day[:7]


def cents(text):
    """'12.50' -> 1250."""
    whole, _, frac = text.partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


def money(value):
    """1250 -> '12.50'."""
    sign = "-" if value < 0 else ""
    value = abs(value)
    return "%s%d.%02d" % (sign, value // 100, value % 100)
''',
    "ledgerlite/core.py": '''"""Posting and balances."""
from .util import cents, month_key


def post(entries, day, account, amount, memo=""):
    """Append a posting (the amount is text like '12.50') and return the entry."""
    entry = {"day": day, "account": account, "cents": cents(amount), "memo": memo}
    entries.append(entry)
    return entry


def balance(entries, account=None, upto=None):
    """Sum of postings, optionally for one account and up to a day (inclusive)."""
    total = 0
    for e in entries:
        if account is not None and e["account"] != account:
            continue
        if upto is not None and e["day"] > upto:
            continue
        total += e["cents"]
    return total


def accounts(entries):
    """Sorted account names."""
    return sorted({e["account"] for e in entries})


def net_by_month(entries):
    """{'2024-03': cents}: the sum of the postings of each month."""
    out = {}
    for e in entries:
        key = month_key(e["day"])
        out[key] = out.get(key, 0) + e["cents"]
    return out
''',
    "ledgerlite/exporters.py": '''"""Export formats, registered by name."""
import json

from .util import money

FORMATS = {}


def register(name):
    """Decorator: make a function available as an export format."""
    def deco(fn):
        FORMATS[name] = fn
        return fn
    return deco


@register("csv")
def to_csv(entries):
    lines = ["day,account,amount,memo"]
    for e in entries:
        lines.append("%s,%s,%s,%s" % (e["day"], e["account"], money(e["cents"]), e["memo"]))
    return "\\n".join(lines)


@register("json")
def to_json(entries):
    return json.dumps([{"day": e["day"], "account": e["account"], "amount": money(e["cents"])} for e in entries], sort_keys=True)


def export_rows(entries, fmt="csv"):
    """Serialise the entries with a registered format."""
    return FORMATS[fmt](entries)
''',
    "ledgerlite/render.py": '''"""Statement rendering; a style is looked up by name as fmt_<style>."""
import sys

from .core import accounts, balance
from .util import money, month_key


def fmt_plain(entries):
    return "\\n".join("%s %s" % (a, money(balance(entries, a))) for a in accounts(entries))


def fmt_monthly(entries):
    months = {}
    for e in entries:
        key = month_key(e["day"])
        months[key] = months.get(key, 0) + e["cents"]
    return "\\n".join("%s %s" % (k, money(months[k])) for k in sorted(months))


def render_statement(entries, style="plain"):
    """Statement in the given style."""
    return getattr(sys.modules[__name__], "fmt_" + style)(entries)
''',
}

LEDGERLITE_HARNESS = '''from ledgerlite import balance, export_rows, month_key, post, render_statement
from ledgerlite import core, util


def run_case(case):
    entries = []
    for day, account, amount, memo in case["postings"]:
        post(entries, day, account, amount, memo)
    return {
        "balance": balance(entries),
        "per_account": {a: balance(entries, a) for a in core.accounts(entries)},
        "upto": balance(entries, upto=case["upto"]),
        "csv": export_rows(entries),
        "json": export_rows(entries, "json"),
        "plain": render_statement(entries),
        "monthly": render_statement(entries, "monthly"),
        "months": core.net_by_month(entries),
        "key": month_key(case["upto"]),
        "cents": util.cents(case["amount"]),
        "money": util.money(case["value"]),
    }
'''


def ledgerlite_cases(rng, n):
    out = []
    for _ in range(n):
        postings = []
        for _ in range(rng.randint(0, 6)):
            day = "2024-%02d-%02d" % (rng.randint(1, 6), rng.randint(1, 28))
            amount = "%s%d.%02d" % ("-" if rng.random() < 0.3 else "", rng.randint(0, 300), rng.randint(0, 99))
            postings.append([day, rng.choice(["cash", "bank", "rent", "food"]), amount.replace("-", "") if amount.startswith("-0.") else amount, rng.choice(["", "memo", "x y"])])
        out.append({"postings": postings, "upto": "2024-%02d-%02d" % (rng.randint(1, 6), rng.randint(1, 28)), "amount": "%d.%d" % (rng.randint(0, 99), rng.randint(0, 99)),
                    "value": rng.choice([0, 5, 1250, -1250, 99999, -7])})
    return out


LEDGERLITE_ITEMS = {
    "plain": dict(w=2, edits=[("append", "ledgerlite/util.py", '\n\ndef legacy_round(value, step=5):\n    """Round cents to the nearest step (the old statement format)."""\n    return int(round(value / step)) * step\n')],
                  check=dict(names=["legacy_round"])),
    "chain": dict(w=3, edits=[("append", "ledgerlite/util.py", '\n\ndef _sign(value):\n    return "-" if value < 0 else "+"\n'),
                              ("replace", "ledgerlite/core.py", "from .util import cents, month_key\n", "from .util import _sign, cents, month_key\n"),
                              ("append", "ledgerlite/core.py", '\n\ndef signed_balance(entries, account):\n    """Balance with an explicit sign, e.g. \'+12.50\'."""\n    total = balance(entries, account)\n    return _sign(total) + str(abs(total))\n')],
                  check=dict(names=["signed_balance", "_sign"], imports=[["ledgerlite/core.py", "_sign"]])),
    "imports": dict(w=1, edits=[("replace", "ledgerlite/exporters.py", "import json\n", "import csv\nimport json\nimport os\n")],
                    check=dict(imports=[["ledgerlite/exporters.py", "csv"], ["ledgerlite/exporters.py", "os"]])),
    "consts": dict(w=1, edits=[("replace", "ledgerlite/util.py", '"""Small helpers."""\n', '"""Small helpers."""\n\nDEFAULT_CURRENCY = "EUR"\nMAX_MEMO = 80\n')],
                   check=dict(consts=["DEFAULT_CURRENCY", "MAX_MEMO"])),
    "flag": dict(w=3, edits=[("replace", "ledgerlite/core.py", "\n\n\ndef post(", "\n\nLEGACY_ROUNDING = False  # old statements rounded to whole units\n\n\ndef post("),
                             ("replace", "ledgerlite/core.py", '        total += e["cents"]\n    return total\n', '        total += e["cents"]\n    if LEGACY_ROUNDING:\n        total = total // 100 * 100\n    return total\n')],
                 check=dict(consts=["LEGACY_ROUNDING"])),
    "unreachable": dict(w=1, edits=[("replace", "ledgerlite/exporters.py", "sort_keys=True)\n", 'sort_keys=True)\n    print("exported", len(entries))\n')], check=dict(generic=["unreachable"])),
    "commented": dict(w=1, edits=[("replace", "ledgerlite/core.py", "    entries.append(entry)\n",
                                   '    # entry["cents"] = int(float(amount) * 100)  # old parsing, lost cents\n    # if memo:\n    #     entry["memo"] = memo.strip()\n    entries.append(entry)\n')],
                      check=dict(markers=[["ledgerlite/core.py", "old parsing, lost cents"]])),
    "class": dict(w=2, edits=[("append", "ledgerlite/exporters.py", '\n\nclass XmlWriter:\n    """Experimental XML export (never finished)."""\n\n    def __init__(self, indent=2):\n        self.indent = indent\n\n    def write(self, entries):\n        return "".join("<e>%s</e>" % e["account"] for e in entries)\n')],
                  check=dict(names=["XmlWriter"])),
    "if_false": dict(w=1, edits=[("replace", "ledgerlite/render.py", '    """Statement in the given style."""\n', '    """Statement in the given style."""\n    if False:  # TODO remove after the 2.0 migration\n        return old_statement(entries)\n')],
                     check=dict(generic=["if_false"])),
    "dup": dict(w=3, edits=[("replace", "ledgerlite/util.py", 'def money(value):\n    """1250', 'def money(value):\n    return "%d.%02d" % (value // 100, value % 100)\n\n\ndef money(value):\n    """1250')],
                check=dict(dups=[["ledgerlite/util.py", "money"]])),
}

# ---------------------------------------------------------------------------------------------------------------------
# pantry
# ---------------------------------------------------------------------------------------------------------------------
PANTRY = {
    "pantry/__init__.py": '''"""Meal planning helpers."""
from .recipes import Recipe
from .shopping import shopping_list

__all__ = ["Recipe", "shopping_list"]
''',
    "pantry/units.py": '''"""Unit conversion."""

UNIT_GRAMS = {"g": 1, "kg": 1000, "oz": 28, "lb": 454, "cup": 240, "tbsp": 15}


def to_grams(qty, unit):
    """Convert a quantity to grams (volumes use the water-like factors in UNIT_GRAMS)."""
    if unit not in UNIT_GRAMS:
        raise ValueError("unknown unit %r" % unit)
    return round(qty * UNIT_GRAMS[unit])


def from_grams(grams, unit):
    """Inverse of to_grams, rounded to one decimal."""
    return round(grams / UNIT_GRAMS[unit], 1)
''',
    "pantry/recipes.py": '''"""Recipes."""
from .units import to_grams


class Recipe:
    """A named list of (ingredient, qty, unit, kind) rows for a number of servings."""

    def __init__(self, name, servings, rows):
        self.name = name
        self.servings = servings
        self.rows = [tuple(r) for r in rows]

    def scale(self, servings):
        """A copy of the recipe for another number of servings."""
        factor = servings / self.servings
        return Recipe(self.name, servings, [(n, round(q * factor, 2), u, k) for n, q, u, k in self.rows])

    def total_grams(self):
        return sum(to_grams(q, u) for _, q, u, _ in self.rows)

    def describe(self):
        return "%s for %d: %s" % (self.name, self.servings, ", ".join("%g %s %s" % (q, u, n) for n, q, u, _ in self.rows))
''',
    "pantry/sections.py": '''"""Shop sections; the section of an ingredient kind is looked up as section_<kind>."""


def section_dairy(name):
    return "A-dairy:" + name


def section_produce(name):
    return "B-produce:" + name


def section_dry(name):
    return "C-dry:" + name
''',
    "pantry/shopping.py": '''"""Shopping list."""
from . import sections
from .units import to_grams


def shopping_list(recipes, stock=None):
    """Merge the ingredients of several recipes minus the stock; returns sorted (section:item, grams) pairs."""
    need = {}
    for recipe in recipes:
        for name, qty, unit, kind in recipe.rows:
            key = getattr(sections, "section_" + kind)(name)
            need[key] = need.get(key, 0) + to_grams(qty, unit)
    for name, grams in (stock or {}).items():
        for key in list(need):
            if key.endswith(":" + name):
                need[key] = max(0, need[key] - grams)
    return sorted((k, g) for k, g in need.items() if g > 0)


def describe_stock(stock):
    """One line per stocked item (used by the stock report)."""
    return "\\n".join("%s: %s g" % (n, g) for n, g in sorted(stock.items()))
''',
    "pantry/cli.py": '''"""Command line entry: print the shopping list for the built-in recipe."""
import sys

from .recipes import Recipe
from .shopping import shopping_list

SAMPLE = Recipe("porridge", 2, [("oats", 80, "g", "dry"), ("milk", 1, "cup", "dairy")])


def main(argv):
    servings = int(argv[0]) if argv else 2
    return shopping_list([SAMPLE.scale(servings)])


if __name__ == "__main__":
    print(main(sys.argv[1:]))
''',
}

PANTRY_HARNESS = '''from pantry import Recipe, shopping_list
from pantry import cli, sections, shopping, units


def run_case(case):
    recipes = [Recipe(n, s, rows) for n, s, rows in case["recipes"]]
    return {
        "with_stock": shopping_list(recipes, case["stock"]),
        "plain": shopping_list(recipes),
        "scaled": [r.scale(case["servings"]).describe() for r in recipes],
        "grams": [r.total_grams() for r in recipes],
        "stock": shopping.describe_stock(case["stock"]),
        "cli": cli.main([str(case["servings"])]),
        "back": units.from_grams(case["g"], case["unit"]),
        "sections": [sections.section_dairy("x"), sections.section_dry("y"), sections.section_produce("z")],
    }
'''


def pantry_cases(rng, n):
    names = {"dairy": ["milk", "butter", "cream"], "produce": ["apple", "leek", "kale"], "dry": ["oats", "rice", "flour"]}
    out = []
    for _ in range(n):
        recipes = []
        for r in range(rng.randint(0, 3)):
            rows = []
            for _ in range(rng.randint(1, 4)):
                kind = rng.choice(list(names))
                rows.append([rng.choice(names[kind]), rng.choice([0.5, 1, 2, 3, 250]), rng.choice(["g", "kg", "oz", "lb", "cup", "tbsp"] * 5 + ["pinch"]), kind])
            recipes.append(["dish%d" % r, rng.choice([1, 2, 4]), rows])
        stock = {rng.choice(sum(names.values(), [])): rng.choice([10, 100, 500]) for _ in range(rng.randint(0, 3))}
        out.append({"recipes": recipes, "stock": stock, "servings": rng.choice([1, 2, 3, 6]), "g": rng.choice([0, 100, 999, 2500]), "unit": rng.choice(["g", "kg", "oz", "cup"])})
    return out


PANTRY_ITEMS = {
    "plain": dict(w=2, edits=[("append", "pantry/units.py", '\n\ndef oz_to_grams_old(oz):\n    """Old conversion kept for the legacy importer."""\n    return int(oz * 28.35)\n')],
                  check=dict(names=["oz_to_grams_old"])),
    "chain": dict(w=3, edits=[("append", "pantry/units.py", "\n\ndef _tbsp_count(cups):\n    return cups * 16\n"),
                              ("replace", "pantry/recipes.py", "from .units import to_grams\n", "from .units import _tbsp_count, to_grams\n"),
                              ("append", "pantry/recipes.py", '\n\ndef legacy_cups(recipe):\n    """Cups of liquid in a recipe, the old way."""\n    return sum(_tbsp_count(q) for _, q, u, _ in recipe.rows if u == "cup")\n')],
                  check=dict(names=["legacy_cups", "_tbsp_count"], imports=[["pantry/recipes.py", "_tbsp_count"]])),
    "imports": dict(w=1, edits=[("replace", "pantry/shopping.py", "from . import sections\n", "import itertools\nimport re\n\nfrom . import sections\n"),
                                ("replace", "pantry/recipes.py", '"""Recipes."""\n', '"""Recipes."""\nfrom collections import OrderedDict\n')],
                    check=dict(imports=[["pantry/shopping.py", "itertools"], ["pantry/shopping.py", "re"], ["pantry/recipes.py", "OrderedDict"]])),
    "consts": dict(w=1, edits=[("replace", "pantry/units.py", '"""Unit conversion."""\n', '"""Unit conversion."""\n\nDEFAULT_UNIT = "g"\n'), ("append", "pantry/recipes.py", "\n\nMAX_SERVINGS = 24\n")],
                   check=dict(consts=["DEFAULT_UNIT", "MAX_SERVINGS"])),
    "flag": dict(w=3, edits=[("replace", "pantry/recipes.py", 'class Recipe:\n    """A named list', 'LEGACY_SCALING = False\n\n\nclass Recipe:\n    """A named list'),
                             ("replace", "pantry/recipes.py", "        factor = servings / self.servings\n", "        factor = servings / self.servings\n        if LEGACY_SCALING:\n            factor = int(factor)\n")],
                 check=dict(consts=["LEGACY_SCALING"])),
    "unreachable": dict(w=1, edits=[("replace", "pantry/units.py", "    return round(grams / UNIT_GRAMS[unit], 1)\n", '    return round(grams / UNIT_GRAMS[unit], 1)\n    print("converted", grams)\n')], check=dict(generic=["unreachable"])),
    "commented": dict(w=1, edits=[("replace", "pantry/shopping.py", '            key = getattr(sections, "section_" + kind)(name)\n',
                                   '            # key = kind + ":" + name  # old matching by prefix\n            # if kind == "dairy":\n            #     key = "A-" + key\n            key = getattr(sections, "section_" + kind)(name)\n')],
                      check=dict(markers=[["pantry/shopping.py", "old matching by prefix"]])),
    "class": dict(w=2, edits=[("append", "pantry/recipes.py", '\n\nclass RecipeBook:\n    """Collection of recipes (replaced by plain lists)."""\n\n    def __init__(self):\n        self.items = {}\n\n    def add(self, recipe):\n        self.items[recipe.name] = recipe\n')],
                  check=dict(names=["RecipeBook"])),
    "method": dict(w=2, edits=[("replace", "pantry/recipes.py", "    def total_grams(self):\n", "    def _normalise_name(self, name):\n        return name.strip().lower()\n\n    def total_grams(self):\n")],
                   check=dict(names=["_normalise_name"])),
    "if_false": dict(w=1, edits=[("replace", "pantry/shopping.py", "    return sorted((k, g) for k, g in need.items() if g > 0)\n", "    if False:  # debugging\n        print(need)\n    return sorted((k, g) for k, g in need.items() if g > 0)\n")],
                     check=dict(generic=["if_false"])),
    "dup": dict(w=3, edits=[("replace", "pantry/units.py", 'def to_grams(qty, unit):\n    """Convert a quantity', 'def to_grams(qty, unit):\n    return qty * UNIT_GRAMS[unit]\n\n\ndef to_grams(qty, unit):\n    """Convert a quantity')],
                check=dict(dups=[["pantry/units.py", "to_grams"]])),
}

# ---------------------------------------------------------------------------------------------------------------------
# signals
# ---------------------------------------------------------------------------------------------------------------------
SIGNALS = {
    "signals/__init__.py": '''"""Sensor event processing."""
from .events import Event, parse_event
from .handlers import Pipeline
from .sinks import make_sink
from .stats import summarize

__all__ = ["Event", "Pipeline", "make_sink", "parse_event", "summarize"]
''',
    "signals/events.py": '''"""Event parsing."""


class Event:
    """A named measurement at a timestamp (seconds)."""

    def __init__(self, name, value, ts):
        self.name = name
        self.value = value
        self.ts = ts

    def as_tuple(self):
        return (self.name, self.value, self.ts)


def parse_event(line):
    """'temp=21.5@100' -> Event('temp', 21.5, 100)."""
    body, _, ts = line.partition("@")
    name, _, value = body.partition("=")
    if not name or not value or not ts:
        raise ValueError("bad event line: %r" % line)
    return Event(name, float(value), int(ts))
''',
    "signals/handlers.py": '''"""Event handlers: the pipeline calls on_<event name> when such a method exists."""


class Pipeline:
    def __init__(self):
        self.log = []
        self.peak = {}

    def handle(self, event):
        method = getattr(self, "on_" + event.name, self.on_other)
        method(event)

    def on_temp(self, event):
        self.log.append("temp %.1f" % event.value)
        self.peak["temp"] = max(self.peak.get("temp", event.value), event.value)

    def on_door(self, event):
        self.log.append("door %s" % ("open" if event.value else "closed"))

    def on_other(self, event):
        self.log.append("other %s" % event.name)
''',
    "signals/stats.py": '''"""Statistics."""


def rolling_mean(values, window):
    """Mean of each full window."""
    out = []
    for i in range(len(values) - window + 1):
        out.append(round(sum(values[i:i + window]) / window, 3))
    return out


def summarize(events):
    """Count, mean and last value per event name."""
    out = {}
    for e in events:
        c, total, _ = out.get(e.name, (0, 0.0, 0.0))
        out[e.name] = (c + 1, total + e.value, e.value)
    return {n: {"count": c, "mean": round(t / c, 3), "last": last} for n, (c, t, last) in sorted(out.items())}
''',
    "signals/sinks.py": '''"""Where processed events go; sinks register themselves by name."""

SINKS = {}


def sink(name):
    """Class decorator: make a sink available under a name."""
    def deco(cls):
        SINKS[name] = cls
        return cls
    return deco


@sink("memory")
class MemorySink:
    def __init__(self):
        self.items = []

    def write(self, event):
        self.items.append(event.as_tuple())


@sink("count")
class CountSink:
    def __init__(self):
        self.n = 0

    def write(self, event):
        self.n += 1


def make_sink(name):
    return SINKS[name]()
''',
}

SIGNALS_HARNESS = '''from signals import make_sink, parse_event, summarize, Pipeline
from signals import stats


def run_case(case):
    events = [parse_event(line) for line in case["lines"]]
    pipe = Pipeline()
    sinks = [make_sink("memory"), make_sink("count")]
    for e in events:
        pipe.handle(e)
        for s in sinks:
            s.write(e)
    return {
        "log": pipe.log,
        "peak": pipe.peak,
        "memory": sinks[0].items,
        "count": sinks[1].n,
        "summary": summarize(events),
        "rolling": stats.rolling_mean([e.value for e in events], case["window"]),
        "tuples": [e.as_tuple() for e in events],
    }
'''


def signals_cases(rng, n):
    out = []
    for _ in range(n):
        lines = []
        for _ in range(rng.randint(0, 7)):
            name = rng.choice(["temp", "temp", "door", "humidity", "light"])
            value = rng.choice([0, 1]) if name == "door" else round(rng.uniform(-5, 40), 1)
            lines.append("%s=%s@%d" % (name, value, rng.randint(0, 5000)))
        if rng.random() < 0.1:
            lines.append("broken line")
        out.append({"lines": lines, "window": rng.choice([1, 2, 3])})
    return out


SIGNALS_ITEMS = {
    "plain": dict(w=2, edits=[("append", "signals/stats.py", '\n\ndef median(values):\n    """Median of a list (unused since the dashboard was dropped)."""\n    ordered = sorted(values)\n    mid = len(ordered) // 2\n    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2\n')],
                  check=dict(names=["median"])),
    "chain": dict(w=3, edits=[("append", "signals/stats.py", "\n\ndef _clip(value, lo, hi):\n    return max(lo, min(hi, value))\n"),
                              ("append", "signals/stats.py", '\n\ndef normalise(values, lo=0.0, hi=100.0):\n    """Clip values into a range (left over from the old dashboard)."""\n    return [_clip(v, lo, hi) for v in values]\n')],
                  check=dict(names=["normalise", "_clip"])),
    "imports": dict(w=1, edits=[("replace", "signals/stats.py", '"""Statistics."""\n', '"""Statistics."""\nimport math\nfrom collections import defaultdict\n'),
                                ("replace", "signals/handlers.py", 'when such a method exists."""\n', 'when such a method exists."""\nimport time\n')],
                    check=dict(imports=[["signals/stats.py", "math"], ["signals/stats.py", "defaultdict"], ["signals/handlers.py", "time"]])),
    "consts": dict(w=1, edits=[("replace", "signals/events.py", '"""Event parsing."""\n', '"""Event parsing."""\n\nMAX_VALUE = 1e6\nUNITS = {"temp": "C", "door": ""}\n')],
                   check=dict(consts=["MAX_VALUE", "UNITS"])),
    "flag": dict(w=3, edits=[("replace", "signals/handlers.py", "class Pipeline:\n", "VERBOSE_LOG = False\n\n\nclass Pipeline:\n"),
                             ("replace", "signals/handlers.py", '        self.log.append("temp %.1f" % event.value)\n', '        self.log.append("temp %.1f" % event.value)\n        if VERBOSE_LOG:\n            self.log.append("temp-raw %r" % event.value)\n')],
                 check=dict(consts=["VERBOSE_LOG"])),
    "unreachable": dict(w=1, edits=[("replace", "signals/stats.py", "    return out\n\n\ndef summarize", "    return out\n    out.clear()\n\n\ndef summarize")], check=dict(generic=["unreachable"])),
    "commented": dict(w=1, edits=[("replace", "signals/handlers.py", '        method = getattr(self, "on_" + event.name, self.on_other)\n',
                                   '        # if event.name in self.muted:  # muted sensors were dropped in v2\n        #     return\n        method = getattr(self, "on_" + event.name, self.on_other)\n')],
                      check=dict(markers=[["signals/handlers.py", "muted sensors were dropped"]])),
    "class": dict(w=2, edits=[("append", "signals/sinks.py", '\n\nclass FileSink:\n    """Writes events to a file (the feature was cut)."""\n\n    def __init__(self, path):\n        self.path = path\n\n    def write(self, event):\n        with open(self.path, "a") as f:\n            f.write("%s\\n" % (event.as_tuple(),))\n')],
                  check=dict(names=["FileSink"])),
    "method": dict(w=2, edits=[("replace", "signals/handlers.py", "    def on_door(self, event):\n", "    def _reset(self):\n        self.log = []\n        self.peak = {}\n\n    def on_door(self, event):\n")],
                   check=dict(names=["_reset"])),
    "if_false": dict(w=1, edits=[("replace", "signals/stats.py", "    out = {}\n    for e in events:\n", "    out = {}\n    if False:\n        return {}\n    for e in events:\n")],
                     check=dict(generic=["if_false"])),
    "dup": dict(w=3, edits=[("replace", "signals/stats.py", 'def rolling_mean(values, window):\n    """Mean of each full window."""', 'def rolling_mean(values, window):\n    return [sum(values[i:i + window]) / window for i in range(len(values) - window + 1)]\n\n\ndef rolling_mean(values, window):\n    """Mean of each full window."""')],
                check=dict(dups=[["signals/stats.py", "rolling_mean"]])),
}

SKELETONS = {
    "ledgerlite": dict(pkg="ledgerlite", files=LEDGERLITE, harness=LEDGERLITE_HARNESS, cases=ledgerlite_cases, items=LEDGERLITE_ITEMS, topic="bookkeeping"),
    "pantry": dict(pkg="pantry", files=PANTRY, harness=PANTRY_HARNESS, cases=pantry_cases, items=PANTRY_ITEMS, topic="meal planning"),
    "signals": dict(pkg="signals", files=SIGNALS, harness=SIGNALS_HARNESS, cases=signals_cases, items=SIGNALS_ITEMS, topic="sensor events"),
}
