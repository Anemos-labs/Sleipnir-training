"""List scans that should be hash lookups (python): operation counts on tracked values, not wall-clock time."""
from __future__ import annotations

from fx import family

from ._py_shapes import shape_family

SHAPES = {
    "dedupe": dict(
        args=["a"], what="in first-seen order without repeats",
        naive='''def $f($a):
    """$doc"""
    out = []
    for item in $a:
        if item not in out:
            out.append(item)
    return out
''', fast='''def $f($a):
    """$doc"""
    seen = set()
    out = []
    for item in $a:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
''', oracle='''def oracle(a):
    seen, out = set(), []
    for x in a:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
''', small="[rng.randrange(0, 12) for _ in range(rng.randrange(0, 30))]", big="[rng.randrange(0, n // 2) for _ in range(n)]", wrap="[T(x) for x in a]",
        spec="Returns the items of `{a}` in the order they first appear, each only once. Items are hashable and compare with `==`.",
        vocab=[("unique_plates", ["plates"], "Licence plates seen by the toll gantry, each once, in order of first sighting."),
               ("distinct_tags", ["tags"], "The tags used on a photo set, without repeats, in the order they were first used."),
               ("first_seen_sensors", ["readings"], "Sensor ids in order of first appearance in a batch of readings.")]),
    "common": dict(
        args=["a", "b"], what="the items of `a` that also occur in `b`",
        naive='''def $f($a, $b):
    """$doc"""
    return [item for item in $a if item in $b]
''', fast='''def $f($a, $b):
    """$doc"""
    wanted = set($b)
    return [item for item in $a if item in wanted]
''', oracle='''def oracle(a, b):
    s = set(b)
    return [x for x in a if x in s]
''', small="[rng.randrange(0, 15) for _ in range(rng.randrange(0, 25))], [rng.randrange(0, 15) for _ in range(rng.randrange(0, 25))]",
        big="[rng.randrange(0, n) for _ in range(n)], [rng.randrange(0, n) for _ in range(n)]", wrap="[T(x) for x in a], [T(x) for x in b]",
        spec="Returns, in the order of `{a}` (repeats included), the items of `{a}` that also occur in `{b}`.",
        vocab=[("invited_and_replied", ["invited", "replied"], "Guests on the invitation list who have replied."),
               ("stocked_items", ["wanted", "in_stock"], "Wanted items that are in stock, in the order they were asked for."),
               ("shared_followers", ["mine", "theirs"], "Accounts in my follower list that also follow them.")]),
    "difference": dict(
        args=["a", "b"], what="the items of `a` that do not occur in `b`",
        naive='''def $f($a, $b):
    """$doc"""
    out = []
    for item in $a:
        if item not in $b:
            out.append(item)
    return out
''', fast='''def $f($a, $b):
    """$doc"""
    blocked = set($b)
    return [item for item in $a if item not in blocked]
''', oracle='''def oracle(a, b):
    s = set(b)
    return [x for x in a if x not in s]
''', small="[rng.randrange(0, 15) for _ in range(rng.randrange(0, 25))], [rng.randrange(0, 15) for _ in range(rng.randrange(0, 25))]",
        big="[rng.randrange(0, n) for _ in range(n)], [rng.randrange(0, n) for _ in range(n)]", wrap="[T(x) for x in a], [T(x) for x in b]",
        spec="Returns, in the order of `{a}` (repeats included), the items of `{a}` that do not occur in `{b}`.",
        vocab=[("unsent_recipients", ["recipients", "already_sent"], "Recipients that have not been mailed yet."),
               ("missing_parts", ["required", "on_hand"], "Parts that are required but not on hand."),
               ("unreviewed_files", ["changed", "reviewed"], "Changed files nobody has reviewed yet.")]),
    "join": dict(
        args=["a", "b"], what="the name of each order's customer",
        naive='''def $f($a, $b):
    """$doc"""
    out = []
    for order in $a:
        for person in $b:
            if person["id"] == order["customer_id"]:
                out.append((order["id"], person["name"]))
                break
    return out
''', fast='''def $f($a, $b):
    """$doc"""
    names = {}
    for person in $b:
        names.setdefault(person["id"], person["name"])
    out = []
    for order in $a:
        if order["customer_id"] in names:
            out.append((order["id"], names[order["customer_id"]]))
    return out
''', oracle='''def oracle(a, b):
    names = {}
    for p in b:
        names.setdefault(p["id"], p["name"])
    return [(o["id"], names[o["customer_id"]]) for o in a if o["customer_id"] in names]
''', small='[{"id": i, "customer_id": rng.randrange(0, 8)} for i in range(rng.randrange(0, 15))], [{"id": rng.randrange(0, 8), "name": "n%d" % k} for k in range(rng.randrange(0, 10))]',
        big='[{"id": i, "customer_id": rng.randrange(0, n)} for i in range(n)], [{"id": rng.randrange(0, n), "name": "n%d" % k} for k in range(n)]',
        wrap='[{"id": o["id"], "customer_id": T(o["customer_id"])} for o in a], [{"id": p["id"] if False else T(p["id"]), "name": p["name"]} for p in b]',
        spec="Returns `(order id, customer name)` for every order in `{a}` whose `customer_id` matches the `id` of a record in `{b}`, in order of `{a}`; orders without a matching customer are left out; if several customers share an id the first one counts.",
        vocab=[("order_names", ["orders", "customers"], "Pair every order with the name of the customer who placed it."),
               ("ticket_owners", ["tickets", "staff"], "Pair every support ticket with the name of the person it is assigned to."),
               ("loan_borrowers", ["loans", "members"], "Pair every loan with the borrower's name.")]),
    "repeated": dict(
        args=["a"], what="items that occur more than once",
        naive='''def $f($a):
    """$doc"""
    out = []
    for i, item in enumerate($a):
        if $a.count(item) > 1 and item not in $a[:i]:
            out.append(item)
    return out
''', fast='''def $f($a):
    """$doc"""
    counts = {}
    for item in $a:
        counts[item] = counts.get(item, 0) + 1
    return [item for item in counts if counts[item] > 1]
''', oracle='''def oracle(a):
    counts = {}
    for x in a:
        counts[x] = counts.get(x, 0) + 1
    return [x for x in counts if counts[x] > 1]
''', small="[rng.randrange(0, 10) for _ in range(rng.randrange(0, 25))]", big="[rng.randrange(0, n) for _ in range(n)]", wrap="[T(x) for x in a]",
        spec="Returns the items that occur more than once in `{a}`, each once, in the order of their first occurrence.",
        vocab=[("duplicate_scans", ["scans"], "Barcodes that were scanned more than once."),
               ("repeat_visitors", ["visits"], "Visitors who came more than once."),
               ("clashing_names", ["names"], "Names that appear more than once in the registry.")]),
    "positions": dict(
        args=["a", "b"], what="the first position of each needle",
        naive='''def $f($a, $b):
    """$doc"""
    out = []
    for needle in $b:
        if needle in $a:
            out.append($a.index(needle))
        else:
            out.append(-1)
    return out
''', fast='''def $f($a, $b):
    """$doc"""
    first = {}
    for pos, item in enumerate($a):
        first.setdefault(item, pos)
    return [first.get(needle, -1) for needle in $b]
''', oracle='''def oracle(a, b):
    first = {}
    for i, x in enumerate(a):
        first.setdefault(x, i)
    return [first.get(x, -1) for x in b]
''', small="[rng.randrange(0, 12) for _ in range(rng.randrange(0, 20))], [rng.randrange(0, 14) for _ in range(rng.randrange(0, 12))]",
        big="[rng.randrange(0, 3 * n) for _ in range(n)], [rng.randrange(0, 3 * n) for _ in range(n)]", wrap="[T(x) for x in a], [T(x) for x in b]",
        spec="For every item of `{b}` returns the index of its first occurrence in `{a}`, or -1 when it does not occur; the result has one entry per item of `{b}`, in order.",
        vocab=[("slot_numbers", ["shelf", "requests"], "Shelf slot of every requested book (-1 when it is not on the shelf)."),
               ("column_indexes", ["header", "wanted"], "Column index of every wanted column in a CSV header."),
               ("queue_places", ["queue", "people"], "Place in the queue of every person (-1 if absent).")]),
    "group": dict(
        args=["a"], what="things grouped by owner",
        naive='''def $f($a):
    """$doc"""
    groups = []
    for owner, thing in $a:
        for group in groups:
            if group[0] == owner:
                group[1].append(thing)
                break
        else:
            groups.append((owner, [thing]))
    return groups
''', fast='''def $f($a):
    """$doc"""
    index = {}
    groups = []
    for owner, thing in $a:
        if owner not in index:
            index[owner] = []
            groups.append((owner, index[owner]))
        index[owner].append(thing)
    return groups
''', oracle='''def oracle(a):
    index, groups = {}, []
    for owner, thing in a:
        if owner not in index:
            index[owner] = []
            groups.append((owner, index[owner]))
        index[owner].append(thing)
    return groups
''', small="[(rng.randrange(0, 6), rng.randrange(0, 100)) for _ in range(rng.randrange(0, 25))]", big="[(rng.randrange(0, n // 3), k) for k in range(n)]",
        wrap="[(T(o), t) for o, t in a]",
        spec="Groups the `(owner, thing)` pairs of `{a}` by owner: returns a list of `(owner, [things...])`, owners in order of first appearance, things in input order.",
        vocab=[("group_by_author", ["posts"], "Group posts by their author."),
               ("pallets_per_dock", ["pallets"], "Group pallets by the dock they were unloaded at."),
               ("sessions_by_member", ["sessions"], "Group gym sessions by member.")]),
    "reconcile": dict(
        args=["a", "b"], what="matched, missing and extra",
        naive='''def $f($a, $b):
    """$doc"""
    matched = [x for x in $a if x in $b]
    missing = [x for x in $a if x not in $b]
    extra = []
    for y in $b:
        if y not in $a:
            extra.append(y)
    return {"matched": matched, "missing": missing, "extra": extra}
''', fast='''def $f($a, $b):
    """$doc"""
    in_b = set($b)
    in_a = set($a)
    return {
        "matched": [x for x in $a if x in in_b],
        "missing": [x for x in $a if x not in in_b],
        "extra": [y for y in $b if y not in in_a],
    }
''', oracle='''def oracle(a, b):
    sa, sb = set(a), set(b)
    return {"matched": [x for x in a if x in sb], "missing": [x for x in a if x not in sb], "extra": [y for y in b if y not in sa]}
''', small="[rng.randrange(0, 15) for _ in range(rng.randrange(0, 25))], [rng.randrange(0, 15) for _ in range(rng.randrange(0, 25))]",
        big="[rng.randrange(0, 2 * n) for _ in range(n)], [rng.randrange(0, 2 * n) for _ in range(n)]", wrap="[T(x) for x in a], [T(x) for x in b]",
        spec="Compares two lists of ids: `matched` are the ids of `{a}` that also occur in `{b}`, `missing` those of `{a}` that do not, `extra` those of `{b}` that do not occur in `{a}`; every list keeps the order (and repeats) of its source.",
        vocab=[("reconcile_payments", ["ledger", "bank"], "Reconcile the ledger's payment ids against the bank statement."),
               ("compare_inventory", ["expected", "counted"], "Compare the expected stock ids with the ids found in the stock take."),
               ("audit_accounts", ["directory", "payroll"], "Compare directory accounts with payroll ids.")]),
    "tidy": dict(
        args=["a"], what="unique values and repeated values",
        naive='''def $f($a):
    """$doc"""
    unique = []
    for item in $a:
        if item not in unique:
            unique.append(item)
    repeats = [item for item in unique if $a.count(item) > 1]
    return {"unique": unique, "repeats": repeats}
''', fast='''def $f($a):
    """$doc"""
    counts = {}
    for item in $a:
        counts[item] = counts.get(item, 0) + 1
    unique = list(counts)
    return {"unique": unique, "repeats": [item for item in unique if counts[item] > 1]}
''', oracle='''def oracle(a):
    counts = {}
    for x in a:
        counts[x] = counts.get(x, 0) + 1
    u = list(counts)
    return {"unique": u, "repeats": [x for x in u if counts[x] > 1]}
''', small="[rng.randrange(0, 10) for _ in range(rng.randrange(0, 25))]", big="[rng.randrange(0, n) for _ in range(n)]", wrap="[T(x) for x in a]",
        spec="Returns `unique` (the items of `{a}` without repeats, in order of first appearance) and `repeats` (those unique items that occur more than once).",
        vocab=[("tidy_catalogue", ["skus"], "Summarise a catalogue feed: the distinct SKUs and the ones that were listed several times."),
               ("clean_roster", ["names"], "Summarise a roster: distinct names and names entered more than once.")]),
}

PROMPTS = [
    "`{f}` in `{path}` is far too slow once the input grows: with a few thousand items the job that calls it takes minutes where it used to take seconds. "
    "Find out why and fix it without changing what it returns (order and repeats included). The README describes the contract.",
    "perf bug: `{f}` ({path}) scales quadratically. {doc} Make it linear-ish. Same results, same order.",
    "Our nightly batch job calls `{f}` in `{path}` with tens of thousands of items and has started missing its window. Profiling points at this function. "
    "Speed it up substantially; its behaviour (including the order of the result) must stay exactly as documented in the README. I have a counting harness "
    "that compares the number of comparisons and hash operations against the input size, so a constant-factor tweak will not be enough.",
    "Could you look at `{f}`? It works, but every element is checked against a whole list, so doubling the input quadruples the time. {doc} "
    "Please restructure it so the work grows roughly linearly. Don't change the results.",
    "`{path}` -> `{f}`. Complexity problem (list scans inside a loop). Keep the output identical, make the cost O(n) in expectation. Hash-based lookups are fine because the "
    "items are hashable.",
]


CFG = dict(
    pkgs=["ledgerkit", "opsdesk", "inventory", "tracking", "roster", "feedtools", "batchjobs", "gatehouse"], mods=["scan", "compare", "lookup", "batch", "reports"],
    prompts=PROMPTS, factor=30, metric="Ops.total()", unit="comparisons and hash calls", n=(1000, 1800),
    hint="the function scans lists instead of using hash lookups",
    readme_note="The items are hashable and compare with `==`; the lists can hold tens of thousands of entries, so the cost of a call has to grow about linearly with their size.",
    tags=["complexity", "hash-lookup", "operation-counter"])
for _k, _d in {"dedupe": 1, "common": 1, "difference": 1, "join": 2, "repeated": 2, "positions": 2, "group": 2, "reconcile": 3, "tidy": 3}.items():
    SHAPES[_k]["d"] = _d
for _k in ("reconcile", "tidy", "repeated"):
    SHAPES[_k]["n"] = (800, 1100)


@family("optimize-py-membership", category="optimize", lang="python", kind="feature", n=14,
        summary="list scans inside loops (dedupe, join, group, reconcile, positions): operation counts on tracked values must grow linearly")
def gen(rng, n):
    yield from shape_family(rng, n, SHAPES, CFG)
