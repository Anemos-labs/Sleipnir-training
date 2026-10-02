"""Replace conditional ladders with tables and dispatch (python)."""
from __future__ import annotations

import json
import pprint
from string import Template

from fx import Task, dd, family

from . import _kit
from ._kit import indent, prove, py_behaviour, py_structlib

structlib = _kit.load_structlib()

# ----------------------------------------------------------------------------------------------------------------
# kind A: key -> formula ladders
# ----------------------------------------------------------------------------------------------------------------
KEYED = [
    dict(key="harbour", pkg="harbour", mod="fees", fn="dock_fee", arg1="vessel_class", arg2="hours", unit="hour", what="vessel class",
         names=["dinghy", "sloop", "ketch", "trawler", "barge", "yacht", "ferry", "tug"], err="unknown vessel class: %s",
         doc="Mooring fee in cents for a vessel class and a number of hours.", topic="harbour mooring fees"),
    dict(key="kiln", pkg="pottery", mod="pricing", fn="firing_price", arg1="clay", arg2="kilos", unit="kilo", what="clay body",
         names=["stoneware", "porcelain", "earthenware", "raku", "terracotta", "bone_china", "paperclay", "crystalline"],
         err="we do not fire %s", doc="Price in cents to fire a load of a given clay body.", topic="kiln firing prices"),
    dict(key="library", pkg="lending", mod="fines", fn="late_fine", arg1="item_type", arg2="days", unit="day", what="item type",
         names=["book", "dvd", "tool", "reader", "magazine", "laptop", "boardgame", "projector"], err="no fine schedule for %s",
         doc="Fine in cents for an item that is some days late.", topic="library late fines"),
    dict(key="tram", pkg="transit", mod="tickets", fn="ticket_price", arg1="ticket", arg2="zones", unit="zone", what="ticket type",
         names=["single", "return", "day", "weekly", "student", "senior", "family", "night"], err="unknown ticket: %s",
         doc="Price in cents of a ticket valid across a number of zones.", topic="tram ticket prices"),
    dict(key="campsite", pkg="campground", mod="rates", fn="pitch_cost", arg1="pitch", arg2="nights", unit="night", what="pitch type",
         names=["tent", "caravan", "campervan", "cabin", "glamping", "group", "hammock", "wild"], err="unknown pitch type: %s",
         doc="Cost in cents of a pitch for a number of nights.", topic="campsite pitch rates"),
]


def _formula(rng, form, unit_var):
    base = rng.randrange(2, 30) * 50
    rate = rng.randrange(2, 20) * 10
    if form == "lin":
        return f"{base} + {rate} * {unit_var}"
    if form == "min":
        return f"max({base}, {rate} * {unit_var})"
    if form == "cap":
        return f"min({base * 6}, {base} + {rate} * {unit_var})"
    step = rng.choice([2, 3, 4])
    return f"{base} + {rate} * (({unit_var} + {step - 1}) // {step})"


def gen_keyed(rng, spec, k, mixed):
    names = rng.sample(spec["names"], k)
    forms = ["lin"] * k if not mixed else [rng.choice(["lin", "min", "cap", "step"]) for _ in range(k)]
    if not mixed:
        shape = rng.choice(["lin", "min", "cap", "step"])
        forms = [shape] * k
    exprs = {n: _formula(rng, f, spec["arg2"]) for n, f in zip(names, forms)}
    a1, a2 = spec["arg1"], spec["arg2"]
    lines = [f'"""{spec["topic"].capitalize()}."""', "", "", f"def {spec['fn']}({a1}, {a2}):", f'    """{spec["doc"]}"""',
             f"    if {a2} <= 0:", f'        raise ValueError("{a2} must be positive")']
    for i, n in enumerate(names):
        lines += [f'    {"if" if i == 0 else "elif"} {a1} == "{n}":', f"        cost = {exprs[n]}"]
    lines += ["    else:", f'        raise ValueError("{spec["err"]}" % {a1})', "    return cost", ""]
    start = "\n".join(lines)
    rows = "\n".join(f'    "{n}": lambda {a2}: {exprs[n]},' for n in names)
    sol = (f'"""{spec["topic"].capitalize()}."""\n\n# {a1} -> cost in cents as a function of the {a2}\n_RULES = {{\n{rows}\n}}\n\n\n'
           f'def {spec["fn"]}({a1}, {a2}):\n    """{spec["doc"]}"""\n    if {a2} <= 0:\n        raise ValueError("{a2} must be positive")\n'
           f'    rule = _RULES.get({a1})\n    if rule is None:\n        raise ValueError("{spec["err"]}" % {a1})\n    return rule({a2})\n')
    cases = []
    for i in range(30):
        who = rng.choice(names + (["zeppelin"] if i % 9 == 8 else []))
        amount = rng.choice([1, 2, 3, 4, 5, 7, 9, 12, 24, 50, 100, 0 if i % 10 == 9 else 6])
        cases.append([who, amount])
    return start, sol, cases, names


# ----------------------------------------------------------------------------------------------------------------
# kind B: range ladders
# ----------------------------------------------------------------------------------------------------------------
RANGES = [
    dict(key="wind", pkg="weatherdesk", mod="wind", fn="wind_label", arg="speed_kmh", doc="Name for a wind speed in km/h.", topic="wind labels",
         results="words", pool=["still", "breath", "breeze", "fresh", "stiff", "gale", "storm", "squall", "howler", "tempest"], lo=0, hi=140),
    dict(key="postage", pkg="mailroom", mod="postage", fn="postage_cents", arg="weight_g", doc="Postage in cents for a letter of the given weight in grams.",
         topic="postage bands", results="numbers", pool=None, lo=0, hi=2000),
    dict(key="overtime", pkg="payroll", mod="overtime", fn="premium_percent", arg="hours", doc="Pay multiplier (percent) for the hours worked in a week.",
         topic="overtime premiums", results="numbers", pool=None, lo=0, hi=80),
    dict(key="noise", pkg="soundcheck", mod="levels", fn="noise_class", arg="decibels", doc="Noise class for a level in decibels.", topic="noise classes",
         results="words", pool=["hushed", "quiet", "calm", "moderate", "busy", "loud", "intense", "painful", "hazard"], lo=20, hi=130),
    dict(key="water", pkg="utility", mod="water", fn="litre_rate", arg="litres", doc="Price per kilolitre (cents) for a monthly consumption in litres.",
         topic="water tariffs", results="numbers", pool=None, lo=0, hi=60000),
]


def gen_range(rng, spec, k, strict):
    cuts = sorted(rng.sample(range(spec["lo"] + 5, spec["hi"], 1), k - 1))
    cuts = sorted(set(cuts))
    k = len(cuts) + 1
    if spec["results"] == "words":
        vals = rng.sample(spec["pool"], k) if len(spec["pool"]) >= k else [f"{rng.choice(spec['pool'])}{j}" for j in range(k)]
        lit = [json.dumps(v) for v in vals]
    else:
        base = rng.randrange(20, 120)
        vals = sorted(rng.sample(range(base, base + 400), k))
        lit = [str(v) for v in vals]
    op = "<" if strict else "<="
    arg = spec["arg"]
    lines = [f'"""{spec["topic"].capitalize()}."""', "", "", f"def {spec['fn']}({arg}):", f'    """{spec["doc"]}"""',
             f"    if {arg} < 0:", f'        raise ValueError("{arg} cannot be negative")']
    for i, c in enumerate(cuts):
        lines += [f"    {'if' if i == 0 else 'elif'} {arg} {op} {c}:", f"        return {lit[i]}"]
    lines += ["    else:", f"        return {lit[-1]}", ""]
    rows = "\n".join(f"    ({c}, {lit[i]})," for i, c in enumerate(cuts))
    cmp = "<" if strict else "<="
    sol = (f'"""{spec["topic"].capitalize()}."""\n\n# (upper bound of the band, result); anything above the last bound gets the default\n_BANDS = [\n{rows}\n]\n'
           f'_TOP = {lit[-1]}\n\n\ndef {spec["fn"]}({arg}):\n    """{spec["doc"]}"""\n    if {arg} < 0:\n        raise ValueError("{arg} cannot be negative")\n'
           f'    for bound, result in _BANDS:\n        if {arg} {cmp} bound:\n            return result\n    return _TOP\n')
    cases = []
    probes = []
    for c in cuts:
        probes += [c - 1, c, c + 1]
    probes += [0, spec["lo"], spec["hi"], spec["hi"] * 2, -1 if rng.random() < 2 else 0]
    rng.shuffle(probes)
    cases = [[p] for p in probes[:36]]
    return start_sol(lines, sol, cases, vals)


def start_sol(lines, sol, cases, vals):
    return "\n".join(lines), sol, cases, vals


# ----------------------------------------------------------------------------------------------------------------
# kind C: event dispatch ladders with multi-line bodies
# ----------------------------------------------------------------------------------------------------------------
EVENTS = [
    dict(key="greenhouse", pkg="greenhouse", mod="controller", fn="react", doc="Update the controller state for one sensor event; returns the actions to take.",
         topic="greenhouse controller", noun="sensor event", init='{"vents": 0, "heater": False, "fan_minutes": 0, "water_l": 0, "lamps": 0}',
         snippets={
             "temp_high": ('''if event["celsius"] > $a:
    state["vents"] = min(100, state["vents"] + $b)
    actions.append("open vents to %d%%" % state["vents"])
else:
    actions.append("temperature ok")''', lambda r: dict(a=r.randrange(24, 34), b=r.choice([10, 15, 25]))),
             "temp_low": ('''if event["celsius"] < $a:
    state["heater"] = True
    actions.append("heater on")
elif state["heater"]:
    state["heater"] = False
    actions.append("heater off")''', lambda r: dict(a=r.randrange(8, 16))),
             "humidity_high": ('''excess = event["percent"] - $a
if excess > 0:
    state["fan_minutes"] += excess // $b + 1
    actions.append("run fan for %d minutes" % (excess // $b + 1))''', lambda r: dict(a=r.randrange(60, 85), b=r.choice([2, 3, 5]))),
             "soil_dry": ('''if event["moisture"] < $a:
    litres = ($a - event["moisture"]) * $b
    state["water_l"] += litres
    actions.append("water %d litres" % litres)
    if state["water_l"] > $c:
        actions.append("tank low")''', lambda r: dict(a=r.randrange(20, 40), b=r.choice([2, 3]), c=r.randrange(60, 200, 20))),
             "light_low": ('''if event["lux"] < $a and state["lamps"] < $b:
    state["lamps"] += 1
    actions.append("switch on lamp %d" % state["lamps"])
elif event["lux"] > $c and state["lamps"] > 0:
    state["lamps"] -= 1
    actions.append("switch off a lamp")''', lambda r: dict(a=r.randrange(2000, 6000, 500), b=r.choice([2, 3, 4]), c=r.randrange(9000, 15000, 1000))),
             "door_open": ('''if event["minutes"] >= $a:
    actions.append("close door and alert")
    state["vents"] = 0
else:
    actions.append("door open %d min" % event["minutes"])''', lambda r: dict(a=r.randrange(5, 20, 5))),
             "power_cut": ('''state["heater"] = False
state["lamps"] = 0
actions.append("switch to battery")
if event.get("hours", 0) > $a:
    actions.append("call the grower")''', lambda r: dict(a=r.randrange(1, 6))),
         },
         case=lambda r, kinds: ({"vents": r.choice([0, 40, 90]), "heater": r.random() < 0.5, "fan_minutes": 0, "water_l": r.choice([0, 100]), "lamps": r.choice([0, 1, 3])},
                                lambda kind: {"kind": kind, "celsius": r.randrange(2, 40), "percent": r.randrange(30, 100), "moisture": r.randrange(5, 60),
                                              "lux": r.randrange(500, 20000), "minutes": r.randrange(1, 30), "hours": r.randrange(0, 9)})),
    dict(key="triage", pkg="helpdesk", mod="triage", fn="route_ticket", doc="Place a ticket in the right queue and return the follow-up actions.",
         topic="ticket triage", noun="ticket type", init='{"queues": {}, "escalated": 0, "refund_total": 0}',
         snippets={
             "refund": ('''amount = event["amount"]
if amount > $a:
    state["escalated"] += 1
    actions.append("escalate refund of %d" % amount)
else:
    state["refund_total"] += amount
    actions.append("auto-approve refund of %d" % amount)''', lambda r: dict(a=r.randrange(50, 400, 25))),
             "outage": ('''state["escalated"] += 1
state["queues"]["ops"] = state["queues"].get("ops", 0) + 1
actions.append("page on-call")
if event.get("customers", 0) > $a:
    actions.append("post status update")''', lambda r: dict(a=r.randrange(10, 200, 10))),
             "bug": ('''queue = "bugs-hi" if event.get("severity", 1) >= $a else "bugs"
state["queues"][queue] = state["queues"].get(queue, 0) + 1
actions.append("file in %s" % queue)''', lambda r: dict(a=r.choice([2, 3, 4]))),
             "feature": ('''state["queues"]["ideas"] = state["queues"].get("ideas", 0) + 1
votes = event.get("votes", 0)
if votes >= $a:
    actions.append("send to product review")
else:
    actions.append("thank the customer")''', lambda r: dict(a=r.randrange(3, 12))),
             "abuse": ('''state["queues"]["trust"] = state["queues"].get("trust", 0) + 1
actions.append("lock account")
if event.get("repeat"):
    actions.append("ban for %d days" % $a)''', lambda r: dict(a=r.choice([7, 14, 30]))),
             "billing": ('''if event.get("disputed"):
    state["queues"]["billing-disputes"] = state["queues"].get("billing-disputes", 0) + 1
    actions.append("freeze invoice")
else:
    state["queues"]["billing"] = state["queues"].get("billing", 0) + 1
    actions.append("send invoice copy")''', lambda r: dict()),
             "question": ('''state["queues"]["support"] = state["queues"].get("support", 0) + 1
if len(event.get("text", "")) > $a:
    actions.append("assign senior agent")
else:
    actions.append("send canned answer")''', lambda r: dict(a=r.randrange(60, 200, 20))),
         },
         case=lambda r, kinds: ({"queues": {}, "escalated": r.choice([0, 2]), "refund_total": r.choice([0, 120])},
                                lambda kind: {"kind": kind, "amount": r.randrange(5, 500), "customers": r.randrange(0, 300), "severity": r.randrange(1, 5),
                                              "votes": r.randrange(0, 15), "repeat": r.random() < 0.4, "disputed": r.random() < 0.5,
                                              "text": "x" * r.randrange(0, 260)})),
    dict(key="drone", pkg="dronepost", mod="tracking", fn="apply_update", doc="Apply a tracking update to a parcel record and return the notifications to send.",
         topic="drone delivery tracking", noun="tracking update", init='{"status": "created", "attempts": 0, "history": []}',
         snippets={
             "picked_up": ('''state["status"] = "in_flight"
actions.append("notify sender: picked up")
if event.get("battery", 100) < $a:
    actions.append("swap battery at next hub")''', lambda r: dict(a=r.randrange(15, 40, 5))),
             "delayed": ('''minutes = event.get("minutes", 0)
if minutes > $a:
    state["status"] = "late"
    actions.append("apologise and offer credit")
else:
    actions.append("send new eta")''', lambda r: dict(a=r.randrange(20, 90, 10))),
             "failed": ('''state["attempts"] += 1
if state["attempts"] >= $a:
    state["status"] = "returning"
    actions.append("return to sender")
else:
    state["status"] = "retry"
    actions.append("schedule attempt %d" % (state["attempts"] + 1))''', lambda r: dict(a=r.choice([2, 3, 4]))),
             "delivered": ('''state["status"] = "delivered"
actions.append("send photo proof")
if event.get("signed"):
    actions.append("close ticket")''', lambda r: dict()),
             "rescheduled": ('''day = event.get("day", 0)
if day > $a:
    actions.append("reject: too far out")
else:
    state["status"] = "scheduled"
    actions.append("confirm day %d" % day)''', lambda r: dict(a=r.randrange(3, 10))),
             "returned": ('''state["status"] = "returned"
actions.append("refund shipping")
if state["attempts"] == 0:
    actions.append("flag address error")''', lambda r: dict()),
             "lost": ('''state["status"] = "lost"
actions.append("open insurance claim")
if event.get("value", 0) > $a:
    actions.append("assign adjuster")''', lambda r: dict(a=r.randrange(100, 800, 50))),
         },
         case=lambda r, kinds: ({"status": r.choice(["created", "in_flight", "retry"]), "attempts": r.choice([0, 1, 2, 3]), "history": []},
                                lambda kind: {"kind": kind, "battery": r.randrange(5, 100), "minutes": r.randrange(1, 120), "day": r.randrange(1, 14),
                                              "signed": r.random() < 0.5, "value": r.randrange(20, 1000)})),
]


def gen_events(rng, spec, k, common):
    kinds = rng.sample(list(spec["snippets"]), k)
    bodies = {}
    for kind in kinds:
        tpl, mk = spec["snippets"][kind]
        bodies[kind] = Template(tpl).substitute(mk(rng))
    fn, noun = spec["fn"], spec["noun"]
    post = 'state["last"] = event["kind"]' if common else ""
    lines = [f'"""{spec["topic"].capitalize()}."""', "", "", f"def {fn}(state, event):", f'    """{spec["doc"]}"""', "    kind = event[\"kind\"]", "    actions = []"]
    for i, kind in enumerate(kinds):
        lines.append(f'    {"if" if i == 0 else "elif"} kind == "{kind}":')
        lines += [("        " + ln) if ln else ln for ln in bodies[kind].splitlines()]
    lines += ["    else:", f'        raise ValueError("unknown {noun}: %s" % kind)']
    if post:
        lines.append("    " + post)
    lines += ["    return actions", ""]
    start = "\n".join(lines)
    out = [f'"""{spec["topic"].capitalize()}."""', ""]
    for kind in kinds:
        out += ["", f"def _{kind}(state, event):", f'    """Handle the {kind.replace("_", " ")} case."""', "    actions = []"]
        out += [("    " + ln) if ln else ln for ln in bodies[kind].splitlines()] + ["    return actions", ""]
    out += ["", "_HANDLERS = {"] + [f'    "{kind}": _{kind},' for kind in kinds] + ["}", "", "",
            f"def {fn}(state, event):", f'    """{spec["doc"]}"""', '    handler = _HANDLERS.get(event["kind"])', "    if handler is None:",
            f'        raise ValueError("unknown {noun}: %s" % event["kind"])', "    actions = handler(state, event)"]
    if post:
        out.append("    " + post)
    out += ["    return actions", ""]
    sol = "\n".join(out)
    cases = []
    for i in range(32):
        st, mk = spec["case"](rng, kinds)
        kind = rng.choice(kinds + (["mystery"] if i % 11 == 10 else []))
        cases.append([st, mk(kind)])
    return start, sol, cases, kinds


def _struct(path, entry_fns, bound):
    return dd(f'''
    import ast
    import unittest

    import structlib as S

    BOUND = {bound}
    ENTRY_PATH = "{path}"
    ENTRY_FUNCTIONS = {json.dumps(entry_fns)}


    class StructureTests(unittest.TestCase):
        def test_entry_points_remain(self):
            names = {{n.name for n in S.parse(ENTRY_PATH).body if isinstance(n, ast.FunctionDef)}}
            self.assertFalse(set(ENTRY_FUNCTIONS) - names)

        def test_no_conditional_ladders(self):
            bad = []
            for rel in S.py_files("."):
                src = S.read(rel)
                for q, fn in S.functions(ast.parse(src)):
                    n = S.branch_nodes(fn)
                    if n > BOUND:
                        bad.append("%s:%s has %d conditional branches (limit %d)" % (rel, q, n, BOUND))
            self.assertFalse(bad, "ladders remain:\\n" + S.format_problems(bad))
    ''')


PROMPTS_A = [
    "`{fn}` in `{path}` is a {k}-branch if/elif ladder on the {what} where every branch is a one-line formula. A new {what} gets added about once a month "
    "and each time it is another elif. Turn it into a table (or other lookup) so that a new {what} is one new entry. The function must keep its "
    "signature, results, and the errors (type and message) for a non-positive {arg2} or an unknown {what}. No function in the project should "
    "contain more than {bound} conditional branches (`if`/`elif`/ternary/`match` case) afterwards.",
    "Replace the if/elif chain in `{fn}` ({path}) with a data-driven lookup. same results, same ValueErrors. max {bound} conditionals per function afterwards.",
    "I need `{fn}` to stop being a ladder. It has {k} `elif`s, one per {what}, and nobody remembers which formula belongs to whom. Please restructure `{path}` "
    "around a mapping from {what} to rule, keeping behaviour identical (including unknown values and bad {arg2}). Functions in the project shouldn't have "
    "more than {bound} conditional branches when you are done.",
]
PROMPTS_B = [
    "`{fn}` in `{path}` looks the value up with a ladder of {n} comparisons. Change it to a table of band limits and results that is searched, so that "
    "changing a band means editing data rather than code. Boundaries must behave exactly as today (the value on a limit belongs to the same band as before), "
    "and negative input must still raise `ValueError`. After the change no function should have more than {bound} conditional branches.",
    "refactor `{fn}` ({path}): the if/elif chain on `{arg}` becomes a sorted table + lookup (bisect or loop, your call). Identical results at every boundary, "
    "same ValueError for negatives, at most {bound} conditionals per function.",
    "The bands in `{path}` are hard-coded as an {n}-way if/elif ladder, which is what produced the last off-by-one when someone inserted a band. Put the "
    "bands in a table and look the result up; behaviour must not change anywhere (watch the exact boundary values).  Keep each function to {bound} "
    "conditional branches or fewer.",
]
PROMPTS_C = [
    "`{fn}` in `{path}` dispatches on the {noun} with an if/elif ladder whose branches are 4 to 8 lines each. Move each branch into its own handler "
    "function and dispatch through a mapping (or small classes), keeping `{fn}` as the single public entry point with the same behaviour, including the error "
    "for an unknown kind. No function in the project should have more than {bound} conditional branches afterwards (the handlers' own `if`s count, so keep "
    "them small).",
    "split the ladder in `{fn}` ({path}) into one handler per {noun}, dispatch via dict. same actions, same state changes, same error for unknown kinds. "
    "at most {bound} conditionals in any function.",
    "Adding a {noun} to `{fn}` means editing a {n}-line ladder, and merges keep colliding in `{path}`. Make each kind a self-contained handler registered "
    "in a lookup table so new kinds can be added without touching the others. The public function and everything it does must stay as it is. Don't let "
    "any function exceed {bound} conditional branches.",
]


@family("refactor-py-table-driven", category="refactor", lang="python", kind="refactor", n=12,
        summary="replace if/elif ladders (keyed formulas, value bands, multi-line event handlers) with tables and dispatch")
def gen(rng, n):
    plan = ["A"] * 5 + ["B"] * 5 + ["C"] * 5
    rng.shuffle(plan)
    pools = {"A": list(KEYED) * 2, "B": list(RANGES) * 2, "C": list(EVENTS) * 2}
    for p in pools.values():
        rng.shuffle(p)
    for i in range(n):
        kind = plan[i]
        spec = pools[kind].pop()
        if kind == "A":
            k = rng.choice([4, 5, 6, 7, 8])
            mixed = rng.random() < 0.5
            start_src, sol_src, cases, names = gen_keyed(rng, spec, k, mixed)
            fns = [spec["fn"]]
            d = 1 if (k <= 4 and not mixed) else 2 if not mixed else 3
            prompt = rng.choice(PROMPTS_A)
            tags = ["conditional-ladder", "lookup-table"]
            nn = k
        elif kind == "B":
            k = rng.choice([4, 5, 6, 8, 9])
            strict = rng.random() < 0.5
            start_src, sol_src, cases, _ = gen_range(rng, spec, k, strict)
            fns = [spec["fn"]]
            nn = start_src.count("elif") + 1
            d = 2 if nn <= 6 else 3
            prompt = rng.choice(PROMPTS_B)
            tags = ["conditional-ladder", "range-table"]
        else:
            k = rng.choice([4, 5, 6, 7])
            common = rng.random() < 0.5
            start_src, sol_src, cases, names = gen_events(rng, spec, k, common)
            fns = [spec["fn"]]
            d = 3 if k <= 5 else 4
            prompt = rng.choice(PROMPTS_C)
            tags = ["conditional-ladder", "dispatch", "handlers"]
            nn = len(start_src.splitlines())
        path = f"{spec['pkg']}/{spec['mod']}.py"
        files = {path: start_src, f"{spec['pkg']}/__init__.py": ""}
        # behaviour harness
        if kind == "A":
            harness = f"from {spec['pkg']}.{spec['mod']} import {spec['fn']}\n\ndef run_case(a):\n    return {spec['fn']}(*a)\n"
        elif kind == "B":
            harness = f"from {spec['pkg']}.{spec['mod']} import {spec['fn']}\n\ndef run_case(a):\n    return {spec['fn']}(*a)\n"
        else:
            harness = (f"from {spec['pkg']}.{spec['mod']} import {spec['fn']}\n\ndef run_case(a):\n    state, event = a\n"
                       f"    actions = {spec['fn']}(state, event)\n    return {{'actions': actions, 'state': state}}\n")
        want = _kit.py_golden(files, harness, cases)
        beh = py_behaviour(files, harness, cases, "recorded")
        ok_idx = [j for j, w in enumerate(want) if not (isinstance(w, dict) and "raises" in w)][:3]
        bad_idx = [j for j, w in enumerate(want) if isinstance(w, dict) and "raises" in w][:1]
        vis = ["import json", "import unittest", "", harness.rstrip("\n"), "", "def norm(x):", "    return json.loads(json.dumps(x))", "", "",
               f"class {spec['mod'].title()}Tests(unittest.TestCase):"]
        for t, j in enumerate(ok_idx):
            vis += [f"    def test_example_{t + 1}(self):", f"        case = json.loads({json.dumps(json.dumps(cases[j]))})",
                    f"        self.assertEqual(norm(run_case(case)), json.loads({json.dumps(json.dumps(want[j]))}))", ""]
        for j in bad_idx:
            vis += ["    def test_rejects_bad_input(self):", f"        case = json.loads({json.dumps(json.dumps(cases[j]))})",
                    f"        with self.assertRaises({want[j]['raises']}):", "            run_case(case)", ""]
        vis += ["", "if __name__ == '__main__':", "    unittest.main()", ""]
        start = {**files, f"tests/test_{spec['mod']}.py": "\n".join(vis)}
        # bound from the reference solution
        import ast
        sol_tree = ast.parse(sol_src)
        sol_bound = max(structlib.branch_nodes(f) for _, f in structlib.functions(sol_tree))
        start_bound = max(structlib.branch_nodes(f) for _, f in structlib.functions(ast.parse(start_src)))
        bound = max(3, sol_bound + 1)
        if start_bound <= bound + 1:
            raise RuntimeError(f"{spec['key']}: start ladder only has {start_bound} branches, bound {bound}")
        hidden = {"tests/test_more_behaviour.py": beh, "tests/test_zz_structure.py": _struct(path, fns, bound), **py_structlib()}
        solution = {path: sol_src}
        prove(f"{spec['key']}-{kind}", start, hidden, solution, _kit.PY_BEHAVIOUR_CMD, _kit.PY_STRUCT_CMD, "python3 -m unittest discover -s tests")
        prompt = prompt.format(fn=spec["fn"], path=path, k=k, what=spec.get("what", ""), arg1=spec.get("arg1", ""), arg2=spec.get("arg2", ""),
                               arg=spec.get("arg", ""), noun=spec.get("noun", ""), bound=bound, n=nn)
        yield Task(slug=f"{i + 1:02d}-{spec['key']}-{kind.lower()}", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution,
                   verify="python3 -m unittest discover -s tests -v", tags=tags, notes={"kind": kind, "branches": k, "bound": bound})
