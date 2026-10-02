"""Python "legacy function" domains for the extract-function family.

A domain is a module header, an entry function built from *stages* (inlined in the start, extracted in the
reference solution) and a generator of behaviour cases. Stages marked optional can be dropped, so every instance is a
different function; numeric rules and tables are drawn from the rng.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from string import Template
from typing import Callable


@dataclass
class Stage:
    name: str
    title: str
    ins: tuple
    outs: tuple
    body: str
    doc: str
    optional: bool = True


@dataclass
class Domain:
    key: str
    package: str
    module: str  # file stem
    entry: str
    sig: str  # parameter list text
    doc: str
    topic: str  # words for prompts
    header: Callable  # rng -> (text, ctx)
    params: Callable  # rng -> dict
    stages: list
    epilogue: object  # str, or callable(selected stage names) -> str
    cases: Callable  # (rng, ctx, n) -> list of [args...]
    harness_call: str  # expression using `a` (the args list) e.g. "entry(*a)"
    imports: str = ""

    @property
    def path(self):
        return f"{self.package}/{self.module}.py"


def _pick(rng, xs, k):
    return rng.sample(list(xs), k)


# ---------------------------------------------------------------------------------------------------------------
# ferry fare quotes
# ---------------------------------------------------------------------------------------------------------------
PORTS = ["NB", "HV", "SK", "OR", "TL", "WM", "GR", "PI", "ES", "LK"]
COUPON_WORDS = ["SEA", "DECK", "GULL", "TIDE", "ANCHOR", "BUOY", "KELP", "HARBOR"]


def ferry_header(rng):
    ports = _pick(rng, PORTS, 5)
    routes = {}
    for i in range(4):
        routes[f"{ports[i]}-{ports[i + 1]}"] = rng.randrange(1200, 4200, 50)
    vehicles = {"bike": rng.randrange(200, 500, 50), "car": rng.randrange(2400, 3600, 100), "van": rng.randrange(4200, 6200, 100)}
    coupons = {}
    for w in _pick(rng, COUPON_WORDS, 3):
        if rng.random() < 0.6:
            pct = rng.choice([5, 10, 15, 20])
            coupons[f"{w}{pct}"] = ("pct", pct)
        else:
            coupons[f"{w}OFF"] = ("flat", rng.randrange(200, 900, 50))
    lines = ["ROUTES = {"] + [f'    "{k}": {v},' for k, v in routes.items()] + ["}", "",
             "VEHICLE_FEES = {"] + [f'    "{k}": {v},' for k, v in vehicles.items()] + ["}", "",
             "COUPONS = {"] + [f'    "{k}": ("{v[0]}", {v[1]}),' for k, v in coupons.items()] + ["}"]
    return "\n".join(lines) + "\n", {"routes": list(routes), "vehicles": list(vehicles), "coupons": list(coupons)}


def ferry_params(rng, ctx):
    months = sorted(rng.sample(range(1, 13), 3))
    return {"max_pax": rng.randrange(6, 13), "child_age": rng.choice([12, 14, 16]), "child_pct": rng.choice([40, 50, 60]),
            "senior_age": rng.choice([60, 65, 67]), "senior_pct": rng.choice([70, 75, 80]),
            "peak_months": ", ".join(map(str, months)), "peak_pct": rng.choice([8, 10, 12, 15]),
            "group_min": rng.choice([4, 5, 6]), "group_pct": rng.choice([5, 8, 10])}


FERRY_STAGES = [
    Stage("check_booking", "booking checks", ("booking",), ("passengers", "route"), '''
passengers = booking.get("passengers") or []
if not passengers:
    raise ValueError("a booking needs at least one passenger")
if len(passengers) > $max_pax:
    raise ValueError("too many passengers")
route = booking.get("route")
if route not in ROUTES:
    raise ValueError("unknown route: %s" % route)
''', "Return the passenger list and route of a booking, or raise ValueError if the booking is unusable.", optional=False),
    Stage("base_fares", "per-passenger fares", ("passengers", "route"), ("total", "notes"), '''
total = 0
notes = []
for p in passengers:
    kind = p.get("kind", "adult")
    if kind == "child" or p.get("age", 99) < $child_age:
        fare = ROUTES[route] * $child_pct // 100
    elif kind == "senior" or p.get("age", 0) >= $senior_age:
        fare = ROUTES[route] * $senior_pct // 100
    else:
        fare = ROUTES[route]
    total += fare
notes.append("passengers: %d" % len(passengers))
''', "Sum the per-passenger fares (child and senior fares are a percentage of the adult fare).", optional=False),
    Stage("vehicle_fee", "vehicle fee", ("booking", "total", "notes"), ("total",), '''
vehicle = booking.get("vehicle")
if vehicle:
    fee = VEHICLE_FEES.get(vehicle)
    if fee is None:
        raise ValueError("unknown vehicle: %s" % vehicle)
    total += fee
    notes.append("vehicle %s: +%d" % (vehicle, fee))
''', "Add the fee for the vehicle that travels with the booking, if any."),
    Stage("peak_surcharge", "peak-season surcharge", ("booking", "total", "notes"), ("total",), '''
month = int(booking["date"][5:7])
if month in ($peak_months):
    surcharge = total * $peak_pct // 100
    total += surcharge
    notes.append("peak season: +%d" % surcharge)
''', "Apply the peak-season surcharge for sailings in the peak months."),
    Stage("group_discount", "group discount", ("passengers", "total", "notes"), ("total",), '''
if len(passengers) >= $group_min:
    discount = total * $group_pct // 100
    total -= discount
    notes.append("group discount: -%d" % discount)
''', "Give the group discount to large parties."),
    Stage("apply_coupon", "coupon handling", ("booking", "total", "notes"), ("total",), '''
code = (booking.get("coupon") or "").upper()
if code in COUPONS:
    kind, amount = COUPONS[code]
    off = total * amount // 100 if kind == "pct" else amount
    off = min(off, total)
    total -= off
    notes.append("coupon %s: -%d" % (code, off))
elif code:
    raise ValueError("unknown coupon: %s" % code)
''', "Apply a coupon code (percentage or flat amount, never below zero)."),
    Stage("round_total", "rounding of the total", ("total", "notes"), ("total",), '''
rounded = (total + 2) // 5 * 5
if rounded != total:
    notes.append("rounded to 5: %+d" % (rounded - total))
total = rounded
''', "Round the total to the nearest 5 cents."),
]


def ferry_cases(rng, ctx, n):
    out = []
    for i in range(n):
        pax = []
        for _ in range(rng.randrange(1, 8)):
            if rng.random() < 0.2:
                pax.append({"kind": rng.choice(["child", "senior", "adult"])})
            else:
                pax.append({"age": rng.randrange(2, 85)})
        b = {"route": rng.choice(ctx["routes"]), "date": "2026-%02d-%02d" % (rng.randrange(1, 13), rng.randrange(1, 29)),
             "passengers": pax}
        if rng.random() < 0.5:
            b["vehicle"] = rng.choice(ctx["vehicles"])
        if rng.random() < 0.4:
            b["coupon"] = rng.choice(ctx["coupons"]).lower() if rng.random() < 0.5 else rng.choice(ctx["coupons"])
        r = rng.random()
        if i % 11 == 10:
            b["route"] = "XX-YY"
        elif i % 13 == 12:
            b["passengers"] = []
        elif i % 7 == 6:
            b["vehicle"] = "hovercraft"
        elif i % 9 == 8:
            b["coupon"] = "BOGUS"
        elif r < 0.1:
            b["passengers"] = pax * 4
        out.append([b])
    return out


FERRY = Domain(
    key="ferry", package="ferry", module="quote", entry="quote_fare", sig="booking",
    doc="Price a ferry booking and explain the price line by line.", topic="ferry fare quoting",
    header=ferry_header, params=ferry_params, stages=FERRY_STAGES,
    epilogue='return {"route": route, "passengers": len(passengers), "total_cents": total, "notes": notes}',
    cases=ferry_cases, harness_call="quote_fare(*a)")


# ---------------------------------------------------------------------------------------------------------------
# lab sample intake (list pipeline)
# ---------------------------------------------------------------------------------------------------------------
SAMPLE_KINDS = ["serum", "plasma", "swab", "tissue", "urine", "csf", "biopsy", "saliva", "stool", "buffy"]


def intake_header(rng):
    kinds = _pick(rng, SAMPLE_KINDS, 5)
    life = {k: rng.randrange(2, 15) for k in kinds}
    units = {k: rng.choice(["F1", "F2", "F3"]) for k in kinds}
    lines = ["SHELF_LIFE_DAYS = {"] + [f'    "{k}": {v},' for k, v in life.items()] + ["}", "",
             "UNIT_FOR_KIND = {"] + [f'    "{k}": "{v}",' for k, v in units.items()] + ["}", "",
             f"UNIT_CAPACITY = {{\"F1\": {rng.randrange(2, 5)}, \"F2\": {rng.randrange(2, 5)}, \"F3\": {rng.randrange(3, 6)}}}", ""]
    return "\n".join(lines), {"kinds": kinds}


def intake_params(rng, ctx):
    return {"rush_kind": rng.choice(ctx["kinds"]), "rush_bump": rng.choice([2, 3, 5]), "batch_cap": rng.randrange(5, 9)}


INTAKE_STAGES = [
    Stage("parse_lines", "parsing of the raw lines", ("raw_lines", "today"), ("rows", "rejected"), '''
rows = []
rejected = []
for number, line in enumerate(raw_lines, 1):
    parts = [p.strip() for p in line.split(";")]
    if len(parts) != 4:
        rejected.append("line %d: expected 4 fields" % number)
        continue
    sample_id, kind, received, priority = parts
    if kind not in SHELF_LIFE_DAYS:
        rejected.append("line %d: unknown kind %s" % (number, kind))
        continue
    try:
        age = today - int(received)
        prio = int(priority)
    except ValueError:
        rejected.append("line %d: bad number" % number)
        continue
    rows.append({"id": sample_id, "kind": kind, "age": age, "priority": prio})
''', "Split the raw lines into sample records; lines that cannot be read go to the rejected list.", optional=False),
    Stage("drop_repeats", "duplicate removal", ("rows", "rejected"), ("rows",), '''
seen = set()
unique = []
for row in rows:
    if row["id"] in seen:
        rejected.append("%s: duplicate id" % row["id"])
        continue
    seen.add(row["id"])
    unique.append(row)
rows = unique
''', "Keep only the first record of each sample id."),
    Stage("drop_expired", "expiry check", ("rows", "rejected"), ("rows",), '''
fresh = []
for row in rows:
    if row["age"] > SHELF_LIFE_DAYS[row["kind"]]:
        rejected.append("%s: expired (%d days)" % (row["id"], row["age"]))
    else:
        fresh.append(row)
rows = fresh
''', "Reject samples older than the shelf life of their kind."),
    Stage("bump_rush", "rush priority bump", ("rows",), (), '''
for row in rows:
    if row["kind"] == "$rush_kind" and row["age"] <= 1:
        row["priority"] += $rush_bump
''', "Bump the priority of fresh samples of the rush kind."),
    Stage("order_batch", "batch ordering", ("rows",), ("rows",), '''
rows = sorted(rows, key=lambda r: (-r["priority"], r["age"], r["id"]))
''', "Order by priority (high first), then freshest first, then id."),
    Stage("cap_batch", "batch size cap", ("rows", "rejected"), ("rows",), '''
if len(rows) > $batch_cap:
    for row in rows[$batch_cap:]:
        rejected.append("%s: deferred to next batch" % row["id"])
    rows = rows[:$batch_cap]
''', "Process at most one batch; the rest is deferred."),
    Stage("assign_units", "fridge unit assignment", ("rows", "rejected"), ("rows",), '''
load = {}
placed = []
for row in rows:
    unit = UNIT_FOR_KIND[row["kind"]]
    if load.get(unit, 0) >= UNIT_CAPACITY[unit]:
        rejected.append("%s: unit %s is full" % (row["id"], unit))
        continue
    load[unit] = load.get(unit, 0) + 1
    row["unit"] = unit
    placed.append(row)
rows = placed
''', "Give every sample the fridge unit for its kind; full units turn samples away.", optional=False),
]


def intake_cases(rng, ctx, n):
    out = []
    for i in range(n):
        lines = []
        for k in range(rng.randrange(3, 14)):
            r = rng.random()
            sid = "S%03d" % rng.randrange(1, 40)
            kind = rng.choice(ctx["kinds"])
            if r < 0.05:
                lines.append("%s;%s;12" % (sid, kind))
            elif r < 0.1:
                lines.append("%s;mystery;%d;1" % (sid, 100 - rng.randrange(0, 4)))
            elif r < 0.15:
                lines.append("%s;%s;abc;1" % (sid, kind))
            else:
                lines.append("%s;%s;%d;%d" % (sid, kind, 100 - rng.randrange(0, 18), rng.randrange(0, 6)))
        out.append([lines, 100])
    return out


INTAKE = Domain(
    key="intake", package="labflow", module="intake", entry="plan_intake", sig="raw_lines, today",
    doc="Turn raw intake lines into the list of samples to shelve and the list of rejects.", topic="lab sample intake",
    header=intake_header, params=intake_params, stages=INTAKE_STAGES,
    epilogue='''labels = ["%s|%s|%s|p%d" % (r["id"], r["kind"], r["unit"], r["priority"]) for r in rows]
return {"labels": labels, "rejected": rejected}''',
    cases=intake_cases, harness_call="plan_intake(*a)")


# ---------------------------------------------------------------------------------------------------------------
# initiative order for a tabletop game
# ---------------------------------------------------------------------------------------------------------------
NAMES = ["Brix", "Orla", "Tamsin", "Yoru", "Kestrel", "Mab", "Dunstan", "Ilse", "Corvin", "Pell", "Nadia", "Rook", "Sable", "Vex"]


def initiative_header(rng):
    return ("SIDE_RANK = {\"players\": 0, \"allies\": 1, \"foes\": 2}\n", {"names": NAMES})


def initiative_params(rng, ctx):
    return {"haste_bonus": rng.choice([3, 4, 5]), "slow_penalty": rng.choice([2, 3, 4]), "surprise_bonus": rng.choice([5, 8, 10]),
            "max_acts": rng.randrange(6, 10)}


INITIATIVE_STAGES = [
    Stage("base_scores", "base initiative scores", ("combatants",), ("entries",), '''
entries = []
for c in combatants:
    modifier = (c["dex"] - 10) // 2
    entries.append({"name": c["name"], "score": c["roll"] + modifier, "dex": c["dex"], "side": c["side"],
                    "conditions": list(c.get("conditions", []))})
''', "Initiative score is the d20 roll plus the dexterity modifier.", optional=False),
    Stage("apply_conditions", "condition handling", ("entries",), ("entries", "skipped"), '''
skipped = []
active = []
for e in entries:
    if "stunned" in e["conditions"]:
        skipped.append(e["name"])
        continue
    if "hasted" in e["conditions"]:
        e["score"] += $haste_bonus
    if "slowed" in e["conditions"]:
        e["score"] -= $slow_penalty
    active.append(e)
entries = active
''', "Stunned combatants lose the round; haste and slow shift the score.", optional=False),
    Stage("surprise_bonus", "surprise-round bonus", ("entries", "round_no"), ("entries",), '''
if round_no == 1:
    for e in entries:
        if e["side"] == "players" and "ambush" in e["conditions"]:
            e["score"] += $surprise_bonus
''', "Ambushing players act earlier in the first round."),
    Stage("split_delayed", "delayed turns", ("entries",), ("entries", "delayed"), '''
delayed = [e for e in entries if "delaying" in e["conditions"]]
entries = [e for e in entries if "delaying" not in e["conditions"]]
''', "Combatants who are delaying go after everyone else."),
    Stage("sort_entries", "tie-break sorting", ("entries",), ("entries",), '''
entries = sorted(entries, key=lambda e: (-e["score"], -e["dex"], SIDE_RANK[e["side"]], e["name"]))
''', "Highest score first; ties go to higher dexterity, then players before allies before foes, then name.", optional=False),
    Stage("limit_actions", "action limit", ("entries", "skipped"), ("entries",), '''
if len(entries) > $max_acts:
    for e in entries[$max_acts:]:
        skipped.append(e["name"])
    entries = entries[:$max_acts]
''', "Only the first few combatants act; the rest are listed as skipped."),
]


def initiative_cases(rng, ctx, n):
    out = []
    conds = ["hasted", "slowed", "stunned", "ambush", "delaying"]
    for i in range(n):
        cs = []
        for name in rng.sample(NAMES, rng.randrange(2, 9)):
            cs.append({"name": name, "dex": rng.randrange(6, 20), "roll": rng.randrange(1, 21),
                       "side": rng.choice(["players", "allies", "foes"]),
                       "conditions": [c for c in conds if rng.random() < 0.15]})
        if i % 9 == 8:
            cs[0]["side"] = "neutral"
        out.append([cs, rng.choice([1, 1, 2, 3])])
    return out


INITIATIVE = Domain(
    key="initiative", package="tabletop", module="initiative", entry="turn_order", sig="combatants, round_no",
    doc="Work out who acts, and in which order, in a round of combat.", topic="tabletop initiative",
    header=initiative_header, params=initiative_params, stages=INITIATIVE_STAGES,
    epilogue=lambda names: ('''order = [e["name"] for e in entries] + [e["name"] for e in delayed]
return {"order": order, "skipped": skipped}''' if "split_delayed" in names else '''order = [e["name"] for e in entries]
return {"order": order, "skipped": skipped}'''),
    cases=initiative_cases, harness_call="turn_order(*a)")


# ---------------------------------------------------------------------------------------------------------------
# podcast chapter lists
# ---------------------------------------------------------------------------------------------------------------
TITLES = ["intro", "sponsor read", "listener mail", "the long story", "interview", "news roundup", "ad break", "quick fire",
          "outro", "behind the scenes", "bloopers", "next week", "main topic", "recap"]


def chapters_header(rng):
    return "", {}


def chapters_params(rng, ctx):
    return {"min_len": rng.choice([20, 30, 45, 60]), "skew": rng.choice([1, 2, 5])}


CHAPTER_STAGES = [
    Stage("parse_chapters", "chapter line parsing", ("lines",), ("chapters",), '''
chapters = []
for line in lines:
    stamp, _, title = line.strip().partition(" ")
    pieces = stamp.split(":")
    if len(pieces) != 2 or not all(p.isdigit() for p in pieces):
        raise ValueError("bad timestamp: %r" % stamp)
    start = int(pieces[0]) * 60 + int(pieces[1])
    chapters.append({"start": start, "title": title.strip() or "untitled"})
''', "Read `MM:SS title` lines into chapter records.", optional=False),
    Stage("sort_chapters", "chapter sorting", ("chapters",), ("chapters",), '''
chapters = sorted(chapters, key=lambda c: c["start"])
''', "Make sure chapters are in playing order."),
    Stage("ensure_intro", "intro chapter", ("chapters",), ("chapters",), '''
if not chapters or chapters[0]["start"] > 0:
    chapters.insert(0, {"start": 0, "title": "intro"})
''', "Every episode starts with a chapter at 00:00."),
    Stage("drop_past_end", "past-the-end filter", ("chapters", "total_seconds"), ("chapters",), '''
chapters = [c for c in chapters if c["start"] < total_seconds]
''', "Chapters that start after the end of the audio are dropped."),
    Stage("merge_short", "short chapter merging", ("chapters", "total_seconds"), ("chapters",), '''
merged = []
for i, c in enumerate(chapters):
    end = chapters[i + 1]["start"] if i + 1 < len(chapters) else total_seconds
    if merged and end - c["start"] < $min_len:
        continue
    merged.append(c)
chapters = merged
''', "A chapter shorter than the minimum length is absorbed by the previous one."),
    Stage("unique_titles", "title de-duplication", ("chapters",), (), '''
count = {}
for c in chapters:
    key = c["title"].lower()
    count[key] = count.get(key, 0) + 1
    if count[key] > 1:
        c["title"] = "%s (%d)" % (c["title"], count[key])
''', "Repeated titles get a (2), (3) ... suffix."),
    Stage("capitalise_titles", "title capitalisation", ("chapters",), (), '''
for c in chapters:
    c["title"] = c["title"][:1].upper() + c["title"][1:]
''', "Titles start with a capital letter."),
]


def chapters_cases(rng, ctx, n):
    out = []
    for i in range(n):
        lines = []
        t = rng.choice([0, 0, 0, 15])
        for _ in range(rng.randrange(2, 10)):
            title = rng.choice(TITLES) if rng.random() > 0.1 else ""
            lines.append("%02d:%02d %s" % (t // 60, t % 60, title))
            t += rng.randrange(5, 400)
        if rng.random() < 0.3:
            rng.shuffle(lines)
        if i % 10 == 9:
            lines.append("12-30 broken")
        out.append([lines, rng.randrange(600, 2400)])
    return out


CHAPTERS = Domain(
    key="chapters", package="podcast", module="chapters", entry="render_chapters", sig="lines, total_seconds",
    doc="Turn chapter lines into the list shown in the player.", topic="podcast chapter",
    header=chapters_header, params=chapters_params, stages=CHAPTER_STAGES,
    epilogue='''shown = []
for i, c in enumerate(chapters):
    end = chapters[i + 1]["start"] if i + 1 < len(chapters) else total_seconds
    shown.append("%02d:%02d %s [%ds]" % (c["start"] // 60, c["start"] % 60, c["title"], end - c["start"]))
return shown''',
    cases=chapters_cases, harness_call="render_chapters(*a)")


# ---------------------------------------------------------------------------------------------------------------
# stamp duty for an invented jurisdiction
# ---------------------------------------------------------------------------------------------------------------
def duty_header(rng):
    top = rng.randrange(250, 400, 25) * 1000
    bands = [(rng.randrange(80, 140, 10) * 1000, 0), (top // 2, rng.choice([150, 200, 250])), (top, rng.choice([400, 450, 500])),
             (None, rng.choice([700, 800, 900]))]
    lines = ["# (upper limit of the band in whole dollars, rate in basis points)", "BANDS = ["]
    for lim, bp in bands:
        lines.append(f"    ({lim}, {bp})," if lim else f"    (None, {bp}),")
    lines.append("]")
    return "\n".join(lines) + "\n", {"top": top}


def duty_params(rng, ctx):
    return {"ftb_limit": rng.randrange(300, 500, 25) * 1000, "ftb_cut": rng.choice([50, 75, 100]), "nonres_bp": rng.choice([150, 200, 300]),
            "heritage_pct": rng.choice([10, 15, 20]), "floor": rng.choice([50, 100, 250]), "cap": rng.randrange(40, 70, 5) * 1000}


DUTY_STAGES = [
    Stage("check_deal", "deal validation", ("deal",), ("price",), '''
price = deal.get("price")
if not isinstance(price, int) or price <= 0:
    raise ValueError("price must be a positive whole number of dollars")
if deal.get("kind") not in ("house", "flat", "land"):
    raise ValueError("unknown property kind")
''', "Return the price of a deal, or raise ValueError when the deal is malformed.", optional=False),
    Stage("banded_duty", "banded base duty", ("price",), ("total", "notes"), '''
total = 0
notes = []
lower = 0
for upper, bp in BANDS:
    top = price if upper is None else min(price, upper)
    if top > lower:
        part = (top - lower) * bp // 10000
        total += part
        notes.append("band %d-%d at %d bp: %d" % (lower, top, bp, part))
    if upper is None or price <= upper:
        break
    lower = upper
''', "Duty is charged band by band; each band has its own rate in basis points.", optional=False),
    Stage("land_uplift", "land uplift", ("deal", "total", "notes"), ("total",), '''
if deal["kind"] == "land":
    extra = total // 4
    total += extra
    notes.append("land uplift: +%d" % extra)
''', "Bare land pays a 25% uplift."),
    Stage("nonresident_surcharge", "non-resident surcharge", ("deal", "price", "total", "notes"), ("total",), '''
buyer = deal.get("buyer", {})
if not buyer.get("resident", True):
    extra = price * $nonres_bp // 10000
    total += extra
    notes.append("non-resident surcharge: +%d" % extra)
''', "Non-resident buyers pay a surcharge on the whole price."),
    Stage("first_time_relief", "first-time buyer relief", ("deal", "price", "total", "notes"), ("total",), '''
buyer = deal.get("buyer", {})
if buyer.get("first_time") and deal["kind"] != "land" and price <= $ftb_limit:
    cut = total * $ftb_cut // 100
    total -= cut
    notes.append("first-time buyer relief: -%d" % cut)
''', "First-time buyers of homes up to the limit get part of the duty back."),
    Stage("heritage_rebate", "heritage rebate", ("deal", "total", "notes"), ("total",), '''
if deal.get("heritage"):
    rebate = total * $heritage_pct // 100
    total -= rebate
    notes.append("heritage rebate: -%d" % rebate)
''', "Listed heritage properties get a rebate."),
    Stage("apply_bounds", "floor and cap", ("total", "notes"), ("total",), '''
if 0 < total < $floor:
    notes.append("minimum duty applied")
    total = $floor
if total > $cap:
    notes.append("duty capped")
    total = $cap
''', "A minimum duty applies to any non-zero bill and a cap to the largest ones."),
]


def duty_cases(rng, ctx, n):
    out = []
    for i in range(n):
        d = {"price": rng.choice([rng.randrange(20, 120) * 1000, rng.randrange(120, 500) * 1000, rng.randrange(500, 2000) * 1000]),
             "kind": rng.choice(["house", "flat", "land"]),
             "buyer": {"first_time": rng.random() < 0.4, "resident": rng.random() < 0.7}}
        if rng.random() < 0.2:
            d["heritage"] = True
        if i % 12 == 11:
            d["price"] = -5
        elif i % 9 == 8:
            d["kind"] = "castle"
        elif i % 14 == 13:
            d["price"] = 1250.5
        out.append([d])
    return out


DUTY = Domain(
    key="duty", package="registry", module="duty", entry="stamp_duty", sig="deal",
    doc="Compute the transfer duty for a property deal and list how it was built up.", topic="stamp duty",
    header=duty_header, params=duty_params, stages=DUTY_STAGES,
    epilogue='return {"duty": total, "price": price, "notes": notes}',
    cases=duty_cases, harness_call="stamp_duty(*a)")


DOMAINS = [FERRY, INTAKE, INITIATIVE, CHAPTERS, DUTY]
