"""Copy-pasted python handler skeletons for the de-duplication family.

A skeleton has a start template (rendered once per variant: same shape, different constants, sometimes an extra block),
a reference solution builder (one generic function, a table, thin public wrappers) and a behaviour-case generator.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from string import Template
from typing import Callable


@dataclass
class Skeleton:
    key: str
    package: str
    module: str
    topic: str
    unit: str  # what a handler is called in prompts ("booking handler")
    header: str
    tpl: str
    variant: Callable  # (rng, taken_names) -> dict
    extras: Callable  # variant -> {placeholder: block}
    solution: Callable  # (skeleton, variants) -> module text
    cases: Callable  # (rng, variants, n) -> list of case dicts
    harness: str
    names: list
    fn_prefix: str

    @property
    def path(self):
        return f"{self.package}/{self.module}.py"


def render(sk: Skeleton, v: dict) -> str:
    extras = sk.extras(v)
    out = []
    for line in sk.tpl.splitlines():
        m = re.fullmatch(r"(\s*)\$(x_\w+)", line)
        if m:
            blk = extras.get(m.group(2))
            if blk:
                out += [m.group(1) + ln for ln in Template(blk).substitute(v).splitlines()]
            continue
        out.append(Template(line).substitute(v))
    return "\n".join(out) + "\n"


def start_module(sk: Skeleton, variants: list) -> str:
    return sk.header + "\n\n" + "\n\n".join(render(sk, v).rstrip("\n") + "\n" for v in variants)


# ---------------------------------------------------------------------------------------------------------------
# makerspace credit ledger: bill_<machine>(ledger, member, minutes)
# ---------------------------------------------------------------------------------------------------------------
MACHINES = ["laser", "cnc", "printer3d", "kiln", "vinyl", "lathe", "sewing", "soldering"]


def bill_variant(rng, taken):
    name = rng.choice([m for m in MACHINES if m not in taken])
    return {"name": name, "fn": "bill_" + name, "rate": rng.choice([15, 20, 25, 40, 60, 90]), "min_fee": rng.choice([100, 150, 300, 500]),
            "limit": rng.choice([None, None, 120, 240]), "cap": rng.choice([None, None, 2500, 4000]),
            "doc": f"Charge a member for time on the {name} machine."}


def bill_extras(v):
    e = {}
    if v["limit"] is not None:
        e["x_limit"] = 'if minutes > $limit:\n    raise ValueError("$name sessions are limited to $limit minutes")'
    if v["cap"] is not None:
        e["x_cap"] = "if fee > $cap:\n    fee = $cap"
    return e


BILL_TPL = '''def $fn(ledger, member, minutes):
    """$doc"""
    account = ledger["members"].get(member)
    if account is None:
        raise KeyError(member)
    if minutes <= 0:
        raise ValueError("minutes must be positive")
    $x_limit
    fee = minutes * $rate
    if fee < $min_fee:
        fee = $min_fee
    $x_cap
    if account["credit"] < fee:
        raise InsufficientCredit(member, fee)
    account["credit"] -= fee
    ledger["journal"].append((member, "$name", minutes, -fee))
    return fee'''


def bill_solution(sk, variants):
    rows = "\n".join(f'    "{v["name"]}": ({v["rate"]}, {v["min_fee"]}, {v["limit"]}, {v["cap"]}),' for v in variants)
    wrappers = "\n\n".join(f'def {v["fn"]}(ledger, member, minutes):\n    """{v["doc"]}"""\n    return _bill("{v["name"]}", ledger, member, minutes)'
                           for v in variants)
    return sk.header + f'''

# machine -> (rate per minute, minimum fee, longest session in minutes or None, fee cap or None)
_MACHINES = {{
{rows}
}}


def _bill(machine, ledger, member, minutes):
    rate, min_fee, limit, cap = _MACHINES[machine]
    account = ledger["members"].get(member)
    if account is None:
        raise KeyError(member)
    if minutes <= 0:
        raise ValueError("minutes must be positive")
    if limit is not None and minutes > limit:
        raise ValueError("%s sessions are limited to %d minutes" % (machine, limit))
    fee = max(minutes * rate, min_fee)
    if cap is not None:
        fee = min(fee, cap)
    if account["credit"] < fee:
        raise InsufficientCredit(member, fee)
    account["credit"] -= fee
    ledger["journal"].append((member, machine, minutes, -fee))
    return fee


{wrappers}
'''


def bill_cases(rng, variants, n):
    out = []
    for i in range(n):
        v = rng.choice(variants)
        members = {m: {"credit": rng.choice([50, 400, 1500, 6000, 20000])} for m in rng.sample(["ada", "bo", "cy", "dee", "eli"], 3)}
        member = rng.choice(list(members) + (["zed"] if i % 8 == 7 else []))
        minutes = rng.choice([1, 5, 30, 59, 90, 119, 120, 121, 200, 241, 400, 0 if i % 9 == 8 else 15])
        out.append({"fn": v["fn"], "state": {"members": members, "journal": []}, "args": [member, minutes]})
    return out


BILL = Skeleton(
    key="makerspace", package="makerspace", module="billing", topic="makerspace billing", unit="machine billing function",
    header='''"""Time-on-machine billing for the makerspace credit ledger."""


class InsufficientCredit(Exception):
    def __init__(self, member, needed):
        super().__init__("%s needs %d more credit" % (member, needed))
        self.member = member
        self.needed = needed
''',
    tpl=BILL_TPL, variant=bill_variant, extras=bill_extras, solution=bill_solution, cases=bill_cases,
    harness='''import importlib

def run_case(case):
    mod = importlib.import_module("makerspace.billing")
    state = case["state"]
    res = getattr(mod, case["fn"])(state, *case["args"])
    return {"result": res, "state": state}
''', names=MACHINES, fn_prefix="bill_")


# ---------------------------------------------------------------------------------------------------------------
# community garden activity feed: format_<kind>(event)
# ---------------------------------------------------------------------------------------------------------------
FEED_KINDS = [("watering", "watered", "watered the beds", "~"), ("planting", "planted", "planted something", "S"),
              ("harvest", "picked", "went harvesting", "H"), ("compost", "turned", "turned the compost", "C"),
              ("tool", "borrowed", "borrowed a tool", "T"), ("weeding", "weeded", "weeded the plots", "W"),
              ("bee", "inspected", "checked the hives", "B")]


def feed_variant(rng, taken):
    pool = [k for k in FEED_KINDS if k[0] not in taken]
    kind, verb, none, icon = rng.choice(pool)
    return {"name": kind, "fn": "format_" + kind, "verb": verb, "verb_none": none, "icon": icon,
            "actor_key": rng.choice(["who", "member", "gardener"]), "target_key": rng.choice(["what", "plot", "item", "bed"]),
            "count": rng.random() < 0.3, "doc": f"Render a {kind} event for the activity feed."}


def feed_extras(v):
    return {"x_count": 'if event.get("count", 1) > 1:\n    text += " (x%d)" % event["count"]'} if v["count"] else {}


FEED_TPL = '''def $fn(event):
    """$doc"""
    actor = event.get("$actor_key") or "someone"
    target = event.get("$target_key")
    if target is None:
        text = "%s $verb_none" % actor
    else:
        text = "%s $verb %s" % (actor, target)
    $x_count
    minutes = event.get("at", 0) // 60 % 1440
    stamp = "%02d:%02d" % (minutes // 60, minutes % 60)
    if event.get("urgent"):
        text = text.upper()
    return "[%s] $icon %s" % (stamp, text)'''


def feed_solution(sk, variants):
    rows = "\n".join(f'    "{v["name"]}": ("{v["actor_key"]}", "{v["target_key"]}", "{v["verb"]}", "{v["verb_none"]}", "{v["icon"]}", {v["count"]}),' for v in variants)
    wrappers = "\n\n".join(f'def {v["fn"]}(event):\n    """{v["doc"]}"""\n    return _format("{v["name"]}", event)' for v in variants)
    return sk.header + f'''

# kind -> (actor key, target key, verb, text without a target, icon, show a repeat count)
_KINDS = {{
{rows}
}}


def _format(kind, event):
    actor_key, target_key, verb, verb_none, icon, show_count = _KINDS[kind]
    actor = event.get(actor_key) or "someone"
    target = event.get(target_key)
    if target is None:
        text = "%s %s" % (actor, verb_none)
    else:
        text = "%s %s %s" % (actor, verb, target)
    if show_count and event.get("count", 1) > 1:
        text += " (x%d)" % event["count"]
    minutes = event.get("at", 0) // 60 % 1440
    stamp = "%02d:%02d" % (minutes // 60, minutes % 60)
    if event.get("urgent"):
        text = text.upper()
    return "[%s] %s %s" % (stamp, icon, text)


{wrappers}
'''


def feed_cases(rng, variants, n):
    out = []
    for i in range(n):
        v = rng.choice(variants)
        ev = {"at": rng.randrange(0, 200000)}
        if rng.random() < 0.7:
            ev[v["actor_key"]] = rng.choice(["Mina", "Osei", "Pia", "Quentin", "Rhea"])
        if rng.random() < 0.7:
            ev[v["target_key"]] = rng.choice(["tomatoes", "bed 4", "the shed key", "plot 12", "roses"])
        if rng.random() < 0.3:
            ev["count"] = rng.choice([1, 2, 5])
        if rng.random() < 0.2:
            ev["urgent"] = True
        out.append({"fn": v["fn"], "args": [ev]})
    return out


FEED = Skeleton(
    key="garden", package="gardenfeed", module="events", topic="garden activity feed", unit="event formatter",
    header='"""Text lines for the community garden activity feed."""\n',
    tpl=FEED_TPL, variant=feed_variant, extras=feed_extras, solution=feed_solution, cases=feed_cases,
    harness='''import importlib

def run_case(case):
    mod = importlib.import_module("gardenfeed.events")
    return getattr(mod, case["fn"])(*case["args"])
''', names=[k[0] for k in FEED_KINDS], fn_prefix="format_")


# ---------------------------------------------------------------------------------------------------------------
# seed bank stock movements: <verb>(stock, sku, qty, note="")
# ---------------------------------------------------------------------------------------------------------------
MOVES = [("receive", 1, "Add seed lots that arrived at the bank."), ("sow", -1, "Take seed out for sowing."),
         ("discard", -1, "Write off seed that failed germination."), ("donate", -1, "Give seed to another bank."),
         ("return_lot", 1, "Put back seed that was not used."), ("sample", -1, "Take a germination sample.")]


def stock_variant(rng, taken):
    name, sign, doc = rng.choice([m for m in MOVES if m[0] not in taken])
    return {"name": name, "fn": name, "sign": sign, "floor": 0, "note": rng.random() < 0.35 and sign < 0,
            "stamp": rng.random() < 0.3 and sign > 0, "doc": doc, "kind": name}


def stock_extras(v):
    e = {}
    if v["note"]:
        e["x_note"] = 'if not note:\n    raise ValueError("a note is required")'
    if v["stamp"]:
        e["x_stamp"] = 'item["last_move"] = len(stock["moves"])'
    return e


STOCK_TPL = '''def $fn(stock, sku, qty, note=""):
    """$doc"""
    if qty <= 0:
        raise ValueError("quantity must be positive")
    item = stock["items"].get(sku)
    if item is None:
        raise KeyError(sku)
    $x_note
    delta = $sign * qty
    if item["on_hand"] + delta < $floor:
        raise ValueError("not enough stock for %s" % sku)
    item["on_hand"] += delta
    stock["moves"].append({"sku": sku, "kind": "$kind", "qty": delta, "note": note})
    $x_stamp
    return item["on_hand"]'''


def stock_solution(sk, variants):
    rows = "\n".join(f'    "{v["name"]}": ({v["sign"]}, {v["floor"]}, {v["note"]}, {v["stamp"]}),' for v in variants)
    wrappers = "\n\n".join(f'def {v["fn"]}(stock, sku, qty, note=""):\n    """{v["doc"]}"""\n    return _move("{v["name"]}", stock, sku, qty, note)'
                           for v in variants)
    return sk.header + f'''

# kind -> (sign, lowest allowed on-hand, note required, remember the move number)
_MOVES = {{
{rows}
}}


def _move(kind, stock, sku, qty, note):
    sign, floor, need_note, stamp = _MOVES[kind]
    if qty <= 0:
        raise ValueError("quantity must be positive")
    item = stock["items"].get(sku)
    if item is None:
        raise KeyError(sku)
    if need_note and not note:
        raise ValueError("a note is required")
    delta = sign * qty
    if item["on_hand"] + delta < floor:
        raise ValueError("not enough stock for %s" % sku)
    item["on_hand"] += delta
    stock["moves"].append({{"sku": sku, "kind": kind, "qty": delta, "note": note}})
    if stamp:
        item["last_move"] = len(stock["moves"])
    return item["on_hand"]


{wrappers}
'''


def stock_cases(rng, variants, n):
    out = []
    for i in range(n):
        v = rng.choice(variants)
        items = {s: {"on_hand": rng.choice([0, 3, 10, 50])} for s in rng.sample(["bean-01", "kale-07", "oat-22", "leek-03"], 3)}
        sku = rng.choice(list(items) + (["nope-00"] if i % 9 == 8 else []))
        out.append({"fn": v["fn"], "state": {"items": items, "moves": []},
                    "args": [sku, rng.choice([1, 2, 7, 12, 60, 0 if i % 10 == 9 else 4])] + ([rng.choice(["", "lab test", "mouldy"])] if rng.random() < 0.6 else [])})
    return out


STOCK = Skeleton(
    key="seedbank", package="seedbank", module="moves", topic="seed bank stock", unit="stock movement function",
    header='"""Stock movements for the seed bank inventory."""\n',
    tpl=STOCK_TPL, variant=stock_variant, extras=stock_extras, solution=stock_solution, cases=stock_cases,
    harness='''import importlib

def run_case(case):
    mod = importlib.import_module("seedbank.moves")
    state = case["state"]
    res = getattr(mod, case["fn"])(state, *case["args"])
    return {"result": res, "state": state}
''', names=[m[0] for m in MOVES], fn_prefix="")


# ---------------------------------------------------------------------------------------------------------------
# courier quotes: quote_<courier>(parcel)
# ---------------------------------------------------------------------------------------------------------------
COURIERS = ["pelican", "arrowhead", "northwind", "dovetail", "brisk", "lantern", "hopscotch", "tern"]


def courier_variant(rng, taken):
    name = rng.choice([c for c in COURIERS if c not in taken])
    return {"name": name, "fn": "quote_" + name, "max_g": rng.choice([5000, 10000, 20000, 30000]), "base": rng.choice([390, 450, 520, 610, 780]),
            "step_g": rng.choice([500, 1000, 2000]), "step_price": rng.choice([80, 120, 150, 210]), "zone_fee": rng.choice([100, 150, 250]),
            "sig_fee": rng.choice([0, 120, 200]), "fuel": rng.choice([0, 0, 4, 7]), "fragile": rng.choice([0, 0, 350, 500]),
            "label": name.title(), "doc": f"Quote a parcel with {name.title()}."}


def courier_extras(v):
    e = {}
    if v["fuel"]:
        e["x_fuel"] = "price = price * (100 + $fuel) // 100"
    if v["fragile"]:
        e["x_fragile"] = 'if parcel.get("fragile"):\n    price += $fragile'
    return e


COURIER_TPL = '''def $fn(parcel):
    """$doc"""
    weight = parcel["weight_g"]
    if weight <= 0 or weight > $max_g:
        raise ValueError("$label cannot carry %d g" % weight)
    price = $base
    if weight > $step_g:
        price += (weight - $step_g + $step_g - 1) // $step_g * $step_price
    if parcel.get("zone", 1) > 1:
        price += $zone_fee * (parcel["zone"] - 1)
    if parcel.get("signature"):
        price += $sig_fee
    $x_fragile
    $x_fuel
    return {"carrier": "$label", "cents": price}'''


def courier_solution(sk, variants):
    rows = "\n".join(f'    "{v["name"]}": ("{v["label"]}", {v["max_g"]}, {v["base"]}, {v["step_g"]}, {v["step_price"]}, {v["zone_fee"]}, {v["sig_fee"]}, {v["fragile"]}, {v["fuel"]}),'
                     for v in variants)
    wrappers = "\n\n".join(f'def {v["fn"]}(parcel):\n    """{v["doc"]}"""\n    return _quote("{v["name"]}", parcel)' for v in variants)
    return sk.header + f'''

# courier -> (label, heaviest parcel in g, base price, weight step in g, price per step, zone fee, signature fee, fragile fee, fuel %)
_RATES = {{
{rows}
}}


def _quote(courier, parcel):
    label, max_g, base, step_g, step_price, zone_fee, sig_fee, fragile, fuel = _RATES[courier]
    weight = parcel["weight_g"]
    if weight <= 0 or weight > max_g:
        raise ValueError("%s cannot carry %d g" % (label, weight))
    price = base
    if weight > step_g:
        price += (weight - step_g + step_g - 1) // step_g * step_price
    if parcel.get("zone", 1) > 1:
        price += zone_fee * (parcel["zone"] - 1)
    if parcel.get("signature"):
        price += sig_fee
    if fragile and parcel.get("fragile"):
        price += fragile
    if fuel:
        price = price * (100 + fuel) // 100
    return {{"carrier": label, "cents": price}}


{wrappers}
'''


def courier_cases(rng, variants, n):
    out = []
    for i in range(n):
        v = rng.choice(variants)
        p = {"weight_g": rng.choice([1, 400, 500, 501, 999, 1000, 1001, 2500, 4999, 9000, 15000, 31000, 0 if i % 9 == 8 else 750])}
        if rng.random() < 0.5:
            p["zone"] = rng.choice([1, 2, 3, 4])
        if rng.random() < 0.3:
            p["signature"] = True
        if rng.random() < 0.3:
            p["fragile"] = True
        out.append({"fn": v["fn"], "args": [p]})
    return out


COURIER = Skeleton(
    key="courier", package="parcelpost", module="quotes", topic="courier quote", unit="courier quote function",
    header='"""Price quotes for the carriers the shop ships with."""\n',
    tpl=COURIER_TPL, variant=courier_variant, extras=courier_extras, solution=courier_solution, cases=courier_cases,
    harness='''import importlib

def run_case(case):
    mod = importlib.import_module("parcelpost.quotes")
    return getattr(mod, case["fn"])(*case["args"])
''', names=COURIERS, fn_prefix="quote_")


# ---------------------------------------------------------------------------------------------------------------
# retry runners: run_<policy>(job, attempt_fn, sleep)
# ---------------------------------------------------------------------------------------------------------------
POLICIES = [("flaky_api", "ConnectionError"), ("slow_disk", "TimeoutError"), ("lock_wait", "BlockingIOError"), ("mailer", "OSError"),
            ("sync_peer", "ConnectionResetError"), ("cache_fill", "LookupError")]


def policy_variant(rng, taken):
    name, exc = rng.choice([p for p in POLICIES if p[0] not in taken])
    return {"name": name, "fn": "run_" + name, "exc": exc, "tries": rng.choice([3, 4, 5, 6]), "base_delay": rng.choice([1, 2, 5, 10]),
            "factor": rng.choice([2, 3]), "max_delay": rng.choice([20, 60, 120]), "log": rng.random() < 0.4,
            "doc": f"Run a {name.replace('_', ' ')} job, retrying transient failures."}


def policy_extras(v):
    return {"x_log": 'job.setdefault("history", []).append(attempt)'} if v["log"] else {}


POLICY_TPL = '''def $fn(job, attempt_fn, sleep):
    """$doc"""
    delay = $base_delay
    for attempt in range(1, $tries + 1):
        $x_log
        try:
            return attempt_fn(job, attempt)
        except $exc:
            if attempt == $tries:
                raise
            sleep(delay)
            delay = min(delay * $factor, $max_delay)'''


def policy_solution(sk, variants):
    rows = "\n".join(f'    "{v["name"]}": ({v["exc"]}, {v["tries"]}, {v["base_delay"]}, {v["factor"]}, {v["max_delay"]}, {v["log"]}),' for v in variants)
    wrappers = "\n\n".join(f'def {v["fn"]}(job, attempt_fn, sleep):\n    """{v["doc"]}"""\n    return _run("{v["name"]}", job, attempt_fn, sleep)'
                           for v in variants)
    return sk.header + f'''

# policy -> (retryable error, attempts, first delay, growth factor, longest delay, record attempts on the job)
_POLICIES = {{
{rows}
}}


def _run(policy, job, attempt_fn, sleep):
    exc, tries, delay, factor, max_delay, log = _POLICIES[policy]
    for attempt in range(1, tries + 1):
        if log:
            job.setdefault("history", []).append(attempt)
        try:
            return attempt_fn(job, attempt)
        except exc:
            if attempt == tries:
                raise
            sleep(delay)
            delay = min(delay * factor, max_delay)


{wrappers}
'''


def policy_cases(rng, variants, n):
    out = []
    for i in range(n):
        v = rng.choice(variants)
        out.append({"fn": v["fn"], "exc": v["exc"], "fail_times": rng.choice([0, 1, 2, 3, 4, 5, 8]), "other_error": i % 8 == 7})
    return out


POLICY = Skeleton(
    key="retry", package="resilient", module="runners", topic="retry runner", unit="retry runner",
    header='"""Retry runners for the integration jobs."""\n',
    tpl=POLICY_TPL, variant=policy_variant, extras=policy_extras, solution=policy_solution, cases=policy_cases,
    harness='''import builtins
import importlib

def run_case(case):
    mod = importlib.import_module("resilient.runners")
    exc = getattr(builtins, case["exc"])
    sleeps = []
    job = {"id": 1}
    def attempt_fn(j, attempt):
        if case["other_error"] and attempt == 2:
            raise KeyError("boom")
        if attempt <= case["fail_times"]:
            raise exc("try %d" % attempt)
        return "done after %d" % attempt
    res = getattr(mod, case["fn"])(job, attempt_fn, sleeps.append)
    return {"result": res, "sleeps": sleeps, "job": job}
''', names=[p[0] for p in POLICIES], fn_prefix="run_")


SKELETONS = [BILL, FEED, STOCK, COURIER, POLICY]
