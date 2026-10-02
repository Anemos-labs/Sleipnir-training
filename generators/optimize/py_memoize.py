"""Repeated expensive calls (python): calls to a collaborator are counted; caching and computing once is the fix."""
from __future__ import annotations

from fx import family

from ._py_shapes import shape_family

SHAPES = {
    "total_price": dict(
        d=2, args=["a", "b"], callable=True, factor=0.25, metric="Ops.reads", n=(1500, 2500), empty_args="([], PRICE)",
        prelude='''def PRICE(key):
    s = str(key)
    return len(s) * 7 + ord(s[0]) % 13
''',
        naive='''def $f($a, $b):
    """$doc"""
    total = 0
    for key, qty in $a:
        total += $b(key) * qty
    return total
''', fast='''def $f($a, $b):
    """$doc"""
    cache = {}
    total = 0
    for key, qty in $a:
        if key not in cache:
            cache[key] = $b(key)
        total += cache[key] * qty
    return total
''', oracle='''def oracle(a, b):
    return sum(b(k) * q for k, q in a)
''', small="[(rng.randrange(0, 6), rng.randrange(1, 5)) for _ in range(rng.randrange(0, 15))], PRICE",
        big="[(rng.randrange(0, 40), rng.randrange(1, 9)) for _ in range(n)], PRICE", wrap="a, Counted(b)",
        spec="`{a}` is a list of `(key, quantity)` pairs and `{b}(key)` returns the unit price of a key (an expensive lookup, always the same answer for the same key). Returns the sum of `price * quantity` over the list.",
        vocab=[("basket_total", ["lines", "price_of"], "Total of a basket, pricing each line through the catalogue service."),
               ("order_value", ["items", "unit_price"], "Value of an order using the pricing service."),
               ("invoice_sum", ["rows", "rate_for"], "Sum of an invoice, looking up the rate of every row.")]),
    "depths": dict(
        d=3, args=["a", "b"], callable=True, factor=2, metric="Ops.reads", n=(1200, 1800), empty_args="([], Parents(random.Random(0), 1))",
        prelude='''class Parents:
    def __init__(self, rng, n):
        self.p = {0: None}
        for i in range(1, n):
            self.p[i] = max(0, i - rng.randrange(1, 40))

    def __call__(self, node):
        return self.p[node]
''',
        naive='''def $f($a, $b):
    """$doc"""
    out = []
    for node in $a:
        depth = 0
        parent = $b(node)
        while parent is not None:
            depth += 1
            parent = $b(parent)
        out.append(depth)
    return out
''', fast='''def $f($a, $b):
    """$doc"""
    known = {}

    def depth(node):
        if node not in known:
            parent = $b(node)
            known[node] = 0 if parent is None else 1 + depth(parent)
        return known[node]

    return [depth(node) for node in $a]
''', oracle='''def oracle(a, b):
    known = {}

    def depth(node):
        if node not in known:
            p = b(node)
            known[node] = 0 if p is None else 1 + depth(p)
        return known[node]

    return [depth(x) for x in a]
''', small="list(range(m := rng.randrange(1, 12))), Parents(rng, m)", big="list(range(n)), Parents(rng, n)", wrap="a, Counted(b)",
        spec="`{b}(node)` returns the parent of a node (an expensive lookup) or `None` for the root. Returns, for every node in `{a}` (in order), its depth: 0 for the root, parent's depth + 1 otherwise. Node ids are the integers `0 .. n-1`.",
        vocab=[("folder_depths", ["folders", "parent_of"], "Nesting depth of folders in a document store."),
               ("reporting_levels", ["staff", "manager_of"], "How many levels below the CEO each employee sits."),
               ("thread_depths", ["comments", "reply_to"], "Reply depth of comments in a discussion.")]),
    "assembly_cost": dict(
        d=3, args=["a", "b"], callable=True, factor=2, metric="Ops.reads", n=(60, 60), empty_args="(0, Catalog(random.Random(0), 1))",
        prelude='''class Catalog:
    """Expensive parts lookup: item -> (unit_cost, [(part, qty), ...]). Parts always have a higher id than their parent."""

    def __init__(self, rng, n):
        self.rows = {}
        for i in range(n):
            if i >= n - 3:
                self.rows[i] = (rng.randrange(1, 9), [])
            else:
                parts = sorted({rng.randrange(i + 1, min(n, i + 4)) for _ in range(2)})
                self.rows[i] = (rng.randrange(1, 9), [(p, rng.randrange(1, 3)) for p in parts])

    def __call__(self, item):
        return self.rows[item]
''',
        naive='''def $f($a, $b):
    """$doc"""
    unit, parts = $b($a)
    return unit + sum(qty * $f(part, $b) for part, qty in parts)
''', fast='''def $f($a, $b):
    """$doc"""
    known = {}

    def cost(item):
        if item not in known:
            unit, parts = $b(item)
            known[item] = unit + sum(qty * cost(part) for part, qty in parts)
        return known[item]

    return cost($a)
''', oracle='''def oracle(a, b):
    known = {}

    def cost(item):
        if item not in known:
            unit, parts = b(item)
            known[item] = unit + sum(q * cost(p) for p, q in parts)
        return known[item]

    return cost(a)
''', small="0, Catalog(rng, rng.randrange(1, 10))", big="0, Catalog(rng, n)", wrap="a, Counted(b)",
        spec="`{b}(item)` is an expensive parts lookup returning `(unit_cost, parts)`, where `parts` is a list of `(part, quantity)` pairs (empty for raw materials). Returns the total cost of `{a}`: its own unit cost plus, for every part, the quantity times the total cost of that part, recursively. Sub-assemblies are shared between many parents.",
        vocab=[("assembly_cost", ["product", "parts_of"], "Total cost of building a product from its bill of materials."),
               ("kit_price", ["kit", "contents_of"], "Price of a kit including its nested sub-kits."),
               ("menu_cost", ["dish", "recipe_of"], "Cost of a dish including all its sub-recipes.")]),
    "best_items": dict(
        d=2, args=["a", "b"], callable=True, factor=1.0, metric="Ops.reads", n=(1500, 2500), empty_args="([], SCORE)",
        prelude='''def SCORE(x):
    return (x * 37) % 11 - 4
''',
        naive='''def $f($a, $b):
    """$doc"""
    keep = [item for item in $a if $b(item) > 0]
    return sorted(keep, key=lambda item: $b(item), reverse=True)
''', fast='''def $f($a, $b):
    """$doc"""
    scored = [(score, item) for item, score in ((item, $b(item)) for item in $a) if score > 0]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]
''', oracle='''def oracle(a, b):
    scored = [(b(x), x) for x in a]
    scored = [p for p in scored if p[0] > 0]
    scored.sort(key=lambda p: p[0], reverse=True)
    return [x for _, x in scored]
''', small="[rng.randrange(0, 40) for _ in range(rng.randrange(0, 15))], SCORE", big="[rng.randrange(0, 100000) for _ in range(n)], SCORE", wrap="a, Counted(b)",
        spec="`{b}(item)` is an expensive scoring function. Returns the items of `{a}` whose score is positive, best score first (items with equal scores keep their input order).",
        vocab=[("shortlist", ["candidates", "score"], "Candidates worth interviewing, best first."),
               ("ranked_offers", ["offers", "rate"], "Offers with a positive rating, best first."),
               ("worth_visiting", ["places", "appeal"], "Places with a positive appeal score, best first.")]),
    "usable_values": dict(
        d=2, args=["a", "b"], callable=True, factor=1.0, metric="Ops.reads", n=(1500, 2500), empty_args="([], FETCH)",
        prelude='''def FETCH(key):
    if key % 5 == 0:
        return None
    return {"ok": key % 3 != 0, "v": key * 2 + 1}
''',
        naive='''def $f($a, $b):
    """$doc"""
    out = []
    for key in $a:
        if $b(key) is not None and $b(key)["ok"]:
            out.append($b(key)["v"])
    return out
''', fast='''def $f($a, $b):
    """$doc"""
    out = []
    for key in $a:
        record = $b(key)
        if record is not None and record["ok"]:
            out.append(record["v"])
    return out
''', oracle='''def oracle(a, b):
    out = []
    for k in a:
        r = b(k)
        if r is not None and r["ok"]:
            out.append(r["v"])
    return out
''', small="[rng.randrange(0, 40) for _ in range(rng.randrange(0, 15))], FETCH", big="[rng.randrange(0, 100000) for _ in range(n)], FETCH", wrap="a, Counted(b)",
        spec="`{b}(key)` is an expensive fetch returning `None` (unknown key) or a dict with `ok` and `v`. Returns the `v` of every key in `{a}` whose record exists and has `ok` set, in order.",
        vocab=[("usable_readings", ["sensor_ids", "fetch"], "Values of the sensors that answered and reported healthy."),
               ("approved_totals", ["order_ids", "load"], "Totals of orders that exist and are approved."),
               ("live_prices", ["skus", "lookup"], "Prices of SKUs that exist and are active.")]),
}

PROMPTS = [
    "`{f}` in `{path}` calls an expensive collaborator far more often than necessary: the same answer is requested again and again, and the job that uses it has become "
    "unaffordable. {doc} Make it call the collaborator no more often than needed; results must not change. The README says what is expensive.",
    "perf: `{f}` ({path}) recomputes things it already knows. {doc} Cache or compute once. Output identical. We count the collaborator calls in CI.",
    "Our bill for the lookup service doubled after the last release and the trace says `{f}` ({path}) is the caller that asks the same question over and over. "
    "Please fix it so each distinct question is asked once per call. Behaviour must stay exactly the same. {doc}",
    "Could you make `{f}` in `{path}` cheaper? It works but it hits the (expensive) collaborator repeatedly, in some cases exponentially often. Don't change what it returns.",
]

CFG = dict(
    pkgs=["pricing", "orgchart", "routing", "shortlist", "sensorhub", "billing"], mods=["calc", "service", "report", "engine"],
    prompts=PROMPTS, factor=2, metric="Ops.reads", unit="calls to the collaborator", n=(1500, 2500),
    hint="the collaborator is called repeatedly for the same arguments",
    readme_note="The callable argument stands for an expensive service (a database round trip or a remote lookup): the number of calls per request is what costs money, so make each distinct question at most once.",
    tags=["memoisation", "caching", "call-counter"])


@family("optimize-py-memoize", category="optimize", lang="python", kind="feature", n=12,
        summary="redundant calls to an expensive collaborator (repeated lookups, overlapping recursion, calls repeated per item): calls are counted with a budget")
def gen(rng, n):
    yield from shape_family(rng, n, SHAPES, CFG)
