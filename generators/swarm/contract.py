"""Plugins behind a shared interface contract: one worker per checkout-pricing rule, an engine that chains them."""
from __future__ import annotations

import base64
import json
import zlib
from datetime import date, timedelta

from fx import Task, dd, family, merged, run

from ._kit import GRADE_CMD, enum, pick, score_script, team

SHOPS = [
    dict(key="teashop", name="a loose-leaf tea shop", skus=[("tea-tin", 1450, 220, False), ("cup", 900, 310, True), ("kettle", 3800, 1400, True),
                                                           ("honey", 780, 450, False), ("strainer", 450, 60, False), ("scone-mix", 620, 500, False)]),
    dict(key="nursery", name="a plant nursery's web shop", skus=[("seed-pack", 260, 15, False), ("trowel", 1190, 250, False), ("pot-small", 420, 380, True),
                                                                 ("pot-large", 1350, 1900, True), ("compost", 880, 2500, False), ("gloves", 640, 120, False)]),
    dict(key="ferry", name="the ferry terminal gift counter", skus=[("postcard", 120, 8, False), ("mug", 950, 330, True), ("poncho", 1250, 180, False),
                                                                    ("snack-box", 700, 400, False), ("map", 560, 40, False), ("torch", 1590, 260, True)]),
    dict(key="bikecoop", name="a bicycle co-op's parts store", skus=[("tube", 690, 120, False), ("patch-kit", 380, 50, False), ("lock", 2490, 900, False),
                                                                     ("bell", 450, 70, False), ("light-set", 2250, 210, True), ("pump", 1890, 480, True)]),
    dict(key="stationer", name="an old-fashioned stationer's order desk", skus=[("notebook", 540, 220, False), ("ink-bottle", 890, 280, True),
                                                                              ("nib-pack", 410, 25, False), ("blotter", 230, 45, False), ("tape", 310, 90, False), ("ruler", 270, 60, False)]),
]

# --------------------------------------------------------------------------------------------------- engine + helpers
ENGINE = dd('''
    """Checkout pricing: runs every plugin in plugins/ over an order.

    This file is part of the contract; plugins import `ratio`, `subtotal` and `running_total` from it.
    """
    import importlib
    import pkgutil

    import plugins


    def ratio(n, d):
        """n / d rounded half up, for n >= 0 and d > 0 (integers only)."""
        return (2 * n + d) // (2 * d)


    def subtotal(order):
        return sum(line["qty"] * line["unit"] for line in order["lines"])


    def running_total(order, skip=()):
        """Subtotal plus every adjustment so far, ignoring adjustments whose `kind` is in `skip`."""
        return subtotal(order) + sum(a["cents"] for a in order["adjustments"] if a["kind"] not in skip)


    def load_plugins():
        mods = [importlib.import_module("plugins." + m.name) for m in pkgutil.iter_modules(plugins.__path__)]
        return sorted(mods, key=lambda m: (m.PRIORITY, m.NAME))


    def price(order):
        """order: {"lines": [...], "ctx": {...}} -> (priced order, total in cents)."""
        cur = {"lines": [dict(line) for line in order["lines"]], "adjustments": [], "ctx": dict(order.get("ctx", {}))}
        for mod in load_plugins():
            cur = mod.apply(cur)
        return cur, running_total(cur)
''')

PLUGIN_HEAD = '''"""{doc}"""
from engine import ratio, running_total

NAME = "{name}"
PRIORITY = {prio}
'''

STUB = '''"""{doc}"""

NAME = "{name}"
PRIORITY = {prio}


def apply(order):
    raise NotImplementedError("{name}: see CONTRACT.md")
'''


def _rules():
    R = {}

    # bulk ---------------------------------------------------------------------------------------------
    def bulk_params(rng):
        return {"minq": rng.choice([3, 4, 5, 6, 10]), "pct": rng.choice([5, 8, 10, 12, 15])}

    def bulk_src(p):
        return PLUGIN_HEAD.format(doc="Bulk discount.", name="bulk", prio=10) + f'''MIN_QTY = {p["minq"]}
PCT = {p["pct"]}


def apply(order):
    out = {{**order, "adjustments": list(order["adjustments"])}}
    for line in order["lines"]:
        if line["qty"] >= MIN_QTY:
            cents = ratio(line["qty"] * line["unit"] * PCT, 100)
            if cents:
                out["adjustments"].append({{"by": NAME, "kind": "discount", "cents": -cents, "note": line["sku"]}})
    return out
'''

    def bulk_doc(p):
        return (f"Priority 10. Every line with `qty >= {p['minq']}` gets {p['pct']}% off that line (`qty * unit * {p['pct']} / 100`, "
                "rounded half up with `ratio`). One adjustment per discounted line, in line order: `kind` `\"discount\"`, negative `cents`, "
                "`note` the line's `sku`. A discount that rounds to 0 produces no adjustment.")

    R["bulk"] = (10, bulk_params, bulk_src, bulk_doc)

    # bundle -------------------------------------------------------------------------------------------
    def bundle_params(rng):
        return {"pairs": None}  # filled with skus later

    def bundle_src(p):
        return PLUGIN_HEAD.format(doc="Buy one, get one free bundles.", name="bundle", prio=15) + f'''PAIRS = {p["pairs"]!r}


def apply(order):
    left = {{}}
    units = {{}}
    for line in order["lines"]:
        left[line["sku"]] = left.get(line["sku"], 0) + line["qty"]
        units[line["sku"]] = line["unit"]
    out = {{**order, "adjustments": list(order["adjustments"])}}
    for a, b in PAIRS:
        free = min(left.get(a, 0), left.get(b, 0))
        if free <= 0:
            continue
        left[a] -= free
        left[b] -= free
        out["adjustments"].append({{"by": NAME, "kind": "discount", "cents": -free * units[b], "note": a + "+" + b}})
    return out
'''

    def bundle_doc(p):
        pairs = "; ".join(f"`{a}` + `{b}`" for a, b in p["pairs"])
        return ("Priority 15. Bundles, in this order: " + pairs + ". For a pair `A` + `B`, every unit of `B` that can be matched with a unit of `A` "
                "is free: `free = min(qty of A left, qty of B left)` (quantities are summed over the order, each sku appears on at most one line, "
                "and units used by one pair are no longer available to the next). If `free > 0`, one adjustment: `kind` `\"discount\"`, "
                "`cents = -free * unit price of B`, `note` `\"A+B\"`.")

    R["bundle"] = (15, bundle_params, bundle_src, bundle_doc)

    # member -------------------------------------------------------------------------------------------
    def member_params(rng):
        a = rng.choice([2, 3, 4, 5])
        return {"tiers": {"silver": a, "gold": a + rng.choice([2, 3, 4]), "platinum": a + rng.choice([6, 7, 9])}}

    def member_src(p):
        return PLUGIN_HEAD.format(doc="Member discount by tier.", name="member", prio=20) + f'''TIERS = {p["tiers"]!r}


def apply(order):
    tier = order["ctx"].get("member")
    pct = TIERS.get(tier)
    if not pct:
        return order
    cents = ratio(max(0, running_total(order)) * pct, 100)
    if not cents:
        return order
    return {{**order, "adjustments": order["adjustments"] + [{{"by": NAME, "kind": "discount", "cents": -cents, "note": tier}}]}}
'''

    def member_doc(p):
        t = p["tiers"]
        return (f"Priority 20. `ctx[\"member\"]` may be `\"silver\"` ({t['silver']}%), `\"gold\"` ({t['gold']}%) or `\"platinum\"` ({t['platinum']}%); "
                "anything else or no key means no discount. The discount is that percentage of `max(0, running_total(order))` at this point "
                "(so earlier discounts have already been taken off), rounded half up with `ratio`. One adjustment: `kind` `\"discount\"`, "
                "negative `cents`, `note` the tier. A discount of 0 produces no adjustment.")

    R["member"] = (20, member_params, member_src, member_doc)

    # coupon -------------------------------------------------------------------------------------------
    def coupon_params(rng):
        names = ["WELCOME", "SPRING", "HARVEST", "LANTERN", "FIRSTMATE", "BACK2WORK", "TENDOWN"]
        rng.shuffle(names)
        coupons = {}
        for nm in names[:rng.randint(3, 4)]:
            exp = None if rng.random() < 0.4 else (date(2024, 6, 1) + timedelta(days=rng.randint(0, 60))).isoformat()
            coupons[nm] = [rng.choice([300, 500, 750, 1000, 1500, 2500]), exp]
        return {"coupons": coupons}

    def coupon_src(p):
        return PLUGIN_HEAD.format(doc="Coupon codes.", name="coupon", prio=30) + f'''COUPONS = {p["coupons"]!r}


def apply(order):
    ctx = order["ctx"]
    today = ctx.get("today", "")
    cur = {{**order, "adjustments": list(order["adjustments"])}}
    seen = set()
    for code in ctx.get("coupons", []):
        if code in seen or code not in COUPONS:
            continue
        seen.add(code)
        cents, expires = COUPONS[code]
        if expires is not None and today > expires:
            continue
        amount = min(cents, max(0, running_total(cur)))
        if amount > 0:
            cur["adjustments"].append({{"by": NAME, "kind": "discount", "cents": -amount, "note": code}})
    return cur
'''

    def coupon_doc(p):
        rows = "\n".join(f"  * `{c}`: {v[0]} cents off" + (f", valid up to and including {v[1]}" if v[1] else ", never expires")
                         for c, v in p["coupons"].items())
        return ("Priority 30. `ctx[\"coupons\"]` (a list, possibly missing) holds codes the customer entered, `ctx[\"today\"]` is an ISO date string "
                "(compare as strings). Known codes:\n\n" + rows + "\n\n  Codes are processed in the order given; an unknown code, an expired code "
                "(`today` after the last valid day) or a repeat of a code already seen is ignored. A valid code takes off "
                "`min(its amount, max(0, running_total))` at that moment; one adjustment per applied code (`kind` `\"discount\"`, negative `cents`, "
                "`note` the code), none if the amount would be 0.")

    R["coupon"] = (30, coupon_params, coupon_src, coupon_doc)

    # shipping -----------------------------------------------------------------------------------------
    def ship_params(rng):
        b1 = rng.choice([250, 300, 500])
        bands = [[b1, rng.choice([350, 450, 495])], [b1 * 4, rng.choice([590, 690, 750])], [b1 * 12, rng.choice([890, 990, 1190])]]
        return {"bands": bands, "extra": rng.choice([100, 150, 200]), "free": rng.choice([4000, 5000, 6000, 7500])}

    def ship_src(p):
        return PLUGIN_HEAD.format(doc="Shipping by weight.", name="shipping", prio=40) + f'''BANDS = {p["bands"]!r}
EXTRA_PER_STARTED_500G = {p["extra"]}
FREE_OVER = {p["free"]}


def apply(order):
    grams = sum(line["qty"] * line["weight_g"] for line in order["lines"])
    if grams <= 0 or running_total(order) >= FREE_OVER:
        return order
    for upto, cents in BANDS:
        if grams <= upto:
            fee = cents
            break
    else:
        fee = BANDS[-1][1] + EXTRA_PER_STARTED_500G * -(-(grams - BANDS[-1][0]) // 500)
    return {{**order, "adjustments": order["adjustments"] + [{{"by": NAME, "kind": "shipping", "cents": fee, "note": "%d g" % grams}}]}}
'''

    def ship_doc(p):
        b = p["bands"]
        rows = ", ".join(f"up to {u} g: {c}" for u, c in b)
        return (f"Priority 40. Total weight is the sum of `qty * weight_g` over the lines. No shipping (no adjustment) when the weight is 0 or when "
                f"`running_total(order) >= {p['free']}`. Otherwise the fee in cents is, by weight: {rows}; heavier than {b[-1][0]} g: "
                f"{b[-1][1]} plus {p['extra']} for every started 500 g beyond {b[-1][0]} g. One adjustment: `kind` `\"shipping\"`, positive `cents`, "
                "`note` `\"<grams> g\"`.")

    R["shipping"] = (40, ship_params, ship_src, ship_doc)

    # fragile ------------------------------------------------------------------------------------------
    def frag_params(rng):
        return {"per": rng.choice([80, 100, 120, 150, 200]), "cap": rng.choice([300, 450, 600, 800])}

    def frag_src(p):
        return PLUGIN_HEAD.format(doc="Fragile handling fee.", name="fragile", prio=45) + f'''PER_ITEM = {p["per"]}
CAP = {p["cap"]}


def apply(order):
    n = sum(line["qty"] for line in order["lines"] if line.get("fragile"))
    fee = min(CAP, PER_ITEM * n)
    if not fee:
        return order
    return {{**order, "adjustments": order["adjustments"] + [{{"by": NAME, "kind": "fee", "cents": fee, "note": "%d fragile" % n}}]}}
'''

    def frag_doc(p):
        return (f"Priority 45. Lines with `\"fragile\": true` count their `qty`. Fee = `min({p['cap']}, {p['per']} * fragile units)`; none if it "
                "is 0. One adjustment: `kind` `\"fee\"`, positive `cents`, `note` `\"<n> fragile\"`.")

    R["fragile"] = (45, frag_params, frag_src, frag_doc)

    # tax ----------------------------------------------------------------------------------------------
    def tax_params(rng):
        regs = ["north", "coast", "inland", "isles"]
        rng.shuffle(regs)
        return {"rates": {r: rng.choice([0, 40, 60, 80, 95, 125, 150]) for r in regs[:3]}}

    def tax_src(p):
        return PLUGIN_HEAD.format(doc="Sales tax by region.", name="tax", prio=50) + f'''RATES = {p["rates"]!r}  # per mille


def apply(order):
    rate = RATES.get(order["ctx"].get("region"), 0)
    base = max(0, running_total(order, skip=("shipping",)))
    tax = ratio(base * rate, 1000)
    if not tax:
        return order
    return {{**order, "adjustments": order["adjustments"] + [{{"by": NAME, "kind": "tax", "cents": tax, "note": order["ctx"]["region"]}}]}}
'''

    def tax_doc(p):
        rows = ", ".join(f"`{r}` {v / 10:g}%" for r, v in p["rates"].items())
        return (f"Priority 50. Rates by `ctx[\"region\"]`: {rows}; any other or missing region pays 0. The base is "
                "`max(0, running_total(order, skip=(\"shipping\",)))`: everything so far except shipping. Tax is the base times the rate, "
                "rounded half up with `ratio`; none if it is 0. One adjustment: `kind` `\"tax\"`, positive `cents`, `note` the region.")

    R["tax"] = (50, tax_params, tax_src, tax_doc)

    # rounding -----------------------------------------------------------------------------------------
    def round_params(rng):
        return {"step": rng.choice([5, 10, 25, 50])}

    def round_src(p):
        return PLUGIN_HEAD.format(doc="Round the total to a cash-friendly amount.", name="rounding", prio=90) + f'''STEP = {p["step"]}


def apply(order):
    total = running_total(order)
    if total <= 0:
        return order
    delta = ratio(total, STEP) * STEP - total
    if not delta:
        return order
    return {{**order, "adjustments": order["adjustments"] + [{{"by": NAME, "kind": "rounding", "cents": delta, "note": "to %d" % STEP}}]}}
'''

    def round_doc(p):
        return (f"Priority 90, always last. If `running_total(order) > 0`, round it to the nearest multiple of {p['step']} cents (halves round "
                "up, `ratio`). The difference (positive or negative) is one adjustment: `kind` `\"rounding\"`, `note` `\"to "
                f"{p['step']}\"`; none if the difference is 0 or the total is not positive.")

    R["rounding"] = (90, round_params, round_src, round_doc)
    return R


RULES = _rules()


def random_order(rng, shop, regions, tiers, codes, bundles):
    skus = list(shop["skus"])
    rng.shuffle(skus)
    lines = []
    forced = []
    if bundles and rng.random() < 0.6:
        a, b = rng.choice(bundles)
        forced = [a, b]
    chosen = [s for s in skus if s[0] in forced] + [s for s in skus if s[0] not in forced][: rng.randint(1, 3)]
    seen = set()
    for sku, unit, grams, frag in chosen:
        if sku in seen:
            continue
        seen.add(sku)
        lines.append({"sku": sku, "qty": rng.choice([1, 1, 2, 3, 4, 5, 6, 8, 11]), "unit": unit + rng.choice([0, 0, 10, -10]), "weight_g": grams + rng.choice([0, 5]),
                      "fragile": frag})
    ctx = {"today": (date(2024, 6, 1) + timedelta(days=rng.randint(0, 80))).isoformat()}
    if regions and rng.random() < 0.85:
        ctx["region"] = rng.choice(regions + ["elsewhere"])
    if tiers and rng.random() < 0.6:
        ctx["member"] = rng.choice(tiers + ["bronze"])
    if codes and rng.random() < 0.7:
        pool = list(codes) + ["NOSUCHCODE"]
        ctx["coupons"] = [rng.choice(pool) for _ in range(rng.randint(1, 3))]
    return {"lines": lines, "ctx": ctx}


def prior_adjustments(rng, order):
    adj = []
    for _ in range(rng.choice([0, 0, 1, 2])):
        kind = rng.choice(["discount", "fee", "shipping", "discount"])
        cents = rng.randint(50, 900)
        adj.append({"by": "earlier", "kind": kind, "cents": cents if kind != "discount" else -cents, "note": "x"})
    return {**order, "adjustments": adj}


EXPECT_SCRIPT = '''import base64, copy, json, sys, zlib
sys.path.insert(0, ".")
import engine

data = json.load(open("_orders.json"))
out = {"units": {}, "e2e": []}
mods = {m.NAME: m for m in engine.load_plugins()}
for name, orders in data["units"].items():
    out["units"][name] = [mods[name].apply(copy.deepcopy(o)) for o in orders]
for o in data["e2e"]:
    priced, total = engine.price(copy.deepcopy(o))
    out["e2e"].append({"adjustments": priced["adjustments"], "total": total})
print(base64.b64encode(zlib.compress(json.dumps(out, sort_keys=True).encode(), 9)).decode())
'''

PLUGIN_TEST = '''import copy
import json
import os
import sys

sys.path.insert(0, os.getcwd())
import engine

CASES = json.loads(%(cases)r)


def check_unit(name):
    mod = {m.NAME: m for m in engine.load_plugins()}[name]
    for order, want in zip(CASES["units"][name]["orders"], CASES["units"][name]["want"]):
        before = copy.deepcopy(order)
        got = mod.apply(order)
        assert order == before, "apply() mutated its argument for %%r" %% (before,)
        assert got == want, "plugin %%s: order %%r\\n  got  %%r\\n  want %%r" %% (name, before, got, want)


def check_integration():
    for order, want in zip(CASES["e2e"]["orders"], CASES["e2e"]["want"]):
        priced, total = engine.price(copy.deepcopy(order))
        assert priced["adjustments"] == want["adjustments"], "order %%r\\n  got  %%r\\n  want %%r" %% (order, priced["adjustments"], want["adjustments"])
        assert total == want["total"], "order %%r: total %%r, want %%r" %% (order, total, want["total"])


if __name__ == "__main__":
    name = sys.argv[1]
    try:
        check_integration() if name == "integration" else check_unit(name)
    except Exception as e:  # noqa: BLE001
        print("FAILED:", type(e).__name__, e, file=sys.stderr)
        sys.exit(1)
'''


def contract_md(shop, kinds, params, order_example):
    lines = [f"# Pricing plugin contract", "",
             f"Checkout for {shop['name']} prices an order by running every plugin in `plugins/` over it, lowest `PRIORITY` first "
             "(ties by `NAME`). Each plugin is a module with `NAME`, `PRIORITY` and `apply(order) -> order`. `engine.py` is finished and "
             "must not change; the plugin files in `plugins/` are stubs that only carry their `NAME` and `PRIORITY`.", "",
             "## The order", "",
             "```python",
             json.dumps(order_example, indent=2, sort_keys=True),
             "```", "",
             "* `lines`: dicts with `sku`, `qty`, `unit` (cents), `weight_g` (grams per unit) and `fragile`. Each sku appears at most once.",
             "* `ctx`: customer and day information (`today`, and sometimes `region`, `member`, `coupons`).",
             "* `adjustments`: starts empty. Plugins append dicts `{\"by\": NAME, \"kind\": ..., \"cents\": int, \"note\": str}`; negative cents "
             "reduce the price. `kind` is one of `discount`, `fee`, `shipping`, `tax`, `rounding`.",
             "", "## Rules every plugin follows", "",
             "* `apply` never mutates its argument. It returns the order unchanged (the same object is fine) or a new dict whose `adjustments` "
             "list is a new list holding the old adjustments followed by the plugin's new ones.",
             "* All amounts are integer cents. Use `engine.ratio(n, d)` (round half up) for every percentage; do all the multiplying "
             "before the single division, as the rules below say.",
             "* Only look at `order` (including adjustments made by lower-priority plugins); no module-level state.",
             "* `engine.running_total(order, skip=())` is the subtotal plus the adjustments so far, optionally ignoring some kinds.",
             "", "## Plugins", ""]
    for kd in kinds:
        prio = RULES[kd][0]
        lines += [f"### `{kd}` (`plugins/{kd}.py`)", "", RULES[kd][3](params[kd]), ""]
    lines += ["Pricing an order is `engine.price(order)`, which returns the priced order and the total in cents."]
    return "\n".join(lines) + "\n"


@family("swarm-plugin-contract", category="swarm", lang="python", kind="feature", n=12,
        summary="k checkout-pricing plugins behind a documented contract (one worker each) plus an engine integration check")
def plugin_contract(rng, n):
    kinds_all = ["bulk", "bundle", "member", "coupon", "shipping", "fragile", "tax", "rounding"]
    counts = [3, 4, 4, 5, 5, 5, 6, 6, 4, 7, 6, 3]
    for i in range(n):
        shop = SHOPS[i % len(SHOPS)]
        k = counts[i % len(counts)]
        # rounding and tax tend to be present: they interact with everything before them
        pool = [x for x in kinds_all]
        rng.shuffle(pool)
        kinds = pool[:k]
        if k >= 5 and "tax" not in kinds:
            kinds[-1] = "tax"
        if "rounding" not in kinds and k >= 6:
            kinds[0] = "rounding"
        kinds = sorted(set(kinds), key=lambda x: RULES[x][0])
        params = {kd: RULES[kd][1](rng) for kd in kinds}
        names = [s[0] for s in shop["skus"]]
        if "bundle" in kinds:
            a, b = rng.sample(names, 2)
            pairs = [[a, b]]
            if rng.random() < 0.5:
                c, d = rng.sample(names, 2)
                if (c, d) != (a, b):
                    pairs.append([c, d])
            params["bundle"]["pairs"] = [tuple(p) for p in pairs]
        bundles = params.get("bundle", {}).get("pairs", [])
        tiers = list(params["member"]["tiers"]) if "member" in params else []
        codes = list(params["coupon"]["coupons"]) if "coupon" in params else []
        regions = list(params["tax"]["rates"]) if "tax" in params else []
        sources = {kd: RULES[kd][2](params[kd]) for kd in kinds}
        solution = {f"plugins/{kd}.py": sources[kd] for kd in kinds}
        start = {
            "CONTRACT.md": contract_md(shop, kinds, params, {
                "lines": [{"sku": shop["skus"][0][0], "qty": 2, "unit": shop["skus"][0][1], "weight_g": shop["skus"][0][2], "fragile": shop["skus"][0][3]}],
                "ctx": {"today": "2024-07-01", "region": "coast"}, "adjustments": []}),
            "engine.py": ENGINE,
            "plugins/__init__.py": "",
            "README.md": dd(f'''
                # Checkout pricing for {shop["name"]}

                `engine.price(order)` runs every module in `plugins/` and returns the priced order and its total.
                The interface and the rule of every plugin are in `CONTRACT.md`. Try your work with `python3 try_order.py`.
            '''),
            "try_order.py": dd('''
                """Prices one sample order with whatever plugins exist."""
                import json

                import engine

                ORDER = {
                    "lines": [{"sku": "demo", "qty": 3, "unit": 1000, "weight_g": 400, "fragile": False}],
                    "ctx": {"today": "2024-07-01"},
                }

                priced, total = engine.price(ORDER)
                print(json.dumps(priced["adjustments"], indent=2))
                print("total:", total)
            '''),
        }
        for kd in kinds:
            start[f"plugins/{kd}.py"] = STUB.format(doc=f"{kd} plugin (see CONTRACT.md).", name=kd, prio=RULES[kd][0])
        # expected outputs from the reference tree
        data = {"units": {}, "e2e": []}
        for kd in kinds:
            data["units"][kd] = [prior_adjustments(rng, random_order(rng, shop, regions, tiers, codes, bundles)) for _ in range(40)]
        data["e2e"] = [random_order(rng, shop, regions, tiers, codes, bundles) for _ in range(30)]
        tree = merged(start, solution, {"_orders.json": json.dumps(data), "_expect.py": EXPECT_SCRIPT})
        res = run(tree, "python3 _expect.py", timeout=60)
        if not res.ok:
            raise RuntimeError("reference run failed:\n" + res.out[-1500:])
        exp = json.loads(zlib.decompress(base64.b64decode(res.out.strip().splitlines()[-1])))
        cases = {"units": {kd: {"orders": data["units"][kd], "want": exp["units"][kd]} for kd in kinds},
                 "e2e": {"orders": data["e2e"], "want": exp["e2e"]}}
        # each rule must matter somewhere in the cases (otherwise the unit test is vacuous)
        for kd in kinds:
            if not any(w != o for w, o in zip(exp["units"][kd], data["units"][kd])):
                raise RuntimeError(f"rule {kd} never changes an order in its unit cases")
        hidden = {".grade/plugin_cases.py": PLUGIN_TEST % {"cases": json.dumps(cases, sort_keys=True)}}
        units = [{"name": f"plugin {kd}", "cmd": ["python3", ".grade/plugin_cases.py", kd], "weight": 1} for kd in kinds]
        units.append({"name": "integration", "cmd": ["python3", ".grade/plugin_cases.py", "integration"], "weight": max(1, len(kinds) // 3)})
        hidden[".grade/score.py"] = score_script(units)
        voices = [
            f"We're launching an online counter for {shop['name']} and pricing is a chain of plugins behind the contract in CONTRACT.md. "
            f"Every plugin file in plugins/ is a stub. Implement them all; they should work together through engine.price.",
            f"Pricing rules for {shop['name']} are specified one by one in CONTRACT.md, each as its own plugin module. I'd like every rule "
            f"implemented to the letter (rounding included) and the whole chain checked on a pile of orders.",
            f"Implement the {len(kinds)} pricing plugins in plugins/ ({', '.join(kinds)}) as described in CONTRACT.md. engine.py is finished, don't edit it.",
            f"The checkout rules for {shop['name']} changed hands and the code never got written. CONTRACT.md has the full specification. "
            f"Get all the plugins in, and make sure they compose: order of application matters.",
        ]
        d = 3 if len(kinds) <= 4 else 4 if len(kinds) <= 6 else 5
        yield Task(
            slug=f"{i + 1:02d}-{shop['key']}-k{len(kinds)}",
            prompt=voices[i % len(voices)], difficulty=d,
            start=start, hidden=hidden, solution=solution, protected=["engine.py", "CONTRACT.md"],
            verify=GRADE_CMD, pass_mode="json-score",
            team=team(rng, min(len(kinds), 6)),
            tags=["plugins", "interface-contract", "integration"],
            notes={"shop": shop["key"], "rules": kinds, "params": json.loads(json.dumps(params))},
        )
