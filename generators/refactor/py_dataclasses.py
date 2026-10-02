"""Dict and tuple records become dataclasses (python); the new field names are stated in the prompt."""
from __future__ import annotations

import json
from string import Template

from fx import Task, dd, family

from . import _kit
from ._kit import prove, py_behaviour, py_structlib

structlib = _kit.load_structlib()

# ----------------------------------------------------------------------------------------------------------------
# D1: character sheets (dicts, nested items)
# ----------------------------------------------------------------------------------------------------------------
SHEET_LEGACY = '''"""Character sheets for the campaign tracker."""

MAX_LOAD = $max_load


def take_damage(sheet, amount):
    if amount < 0:
        raise ValueError("damage cannot be negative")
    sheet["hp"] = max(0, sheet["hp"] - amount)
    if sheet["hp"] == 0 and "down" not in sheet["conditions"]:
        sheet["conditions"].append("down")
    return sheet["hp"]


def heal(sheet, amount):
    if amount < 0:
        raise ValueError("healing cannot be negative")
    if "dead" in sheet["conditions"]:
        raise ValueError("cannot heal the dead")
    sheet["hp"] = min(sheet["max_hp"], sheet["hp"] + amount)
    if sheet["hp"] > 0 and "down" in sheet["conditions"]:
        sheet["conditions"].remove("down")
    return sheet["hp"]


def carried_weight(sheet):
    return sum(item["weight"] * item.get("count", 1) for item in sheet["inventory"])


def add_item(sheet, item):
    if carried_weight(sheet) + item["weight"] * item.get("count", 1) > MAX_LOAD:
        raise ValueError("%s is too heavy to carry" % item["name"])
    for have in sheet["inventory"]:
        if have["name"] == item["name"]:
            have["count"] = have.get("count", 1) + item.get("count", 1)
            return have["count"]
    sheet["inventory"].append(dict(item))
    return item.get("count", 1)


def status_line(sheet):
    flags = ",".join(sorted(sheet["conditions"])) or "ok"
    return "%s %d/%d AC%d [%s]" % (sheet["name"], sheet["hp"], sheet["max_hp"], sheet["ac"], flags)
'''

SHEET_NEW = '''"""Character sheets for the campaign tracker."""
from dataclasses import dataclass, field

MAX_LOAD = $max_load


@dataclass
class Item:
    name: str
    weight: int
    count: int = 1


@dataclass
class Sheet:
    name: str
    hp: int
    max_hp: int
    ac: int
    inventory: list = field(default_factory=list)
    conditions: list = field(default_factory=list)


def take_damage(sheet, amount):
    if amount < 0:
        raise ValueError("damage cannot be negative")
    sheet.hp = max(0, sheet.hp - amount)
    if sheet.hp == 0 and "down" not in sheet.conditions:
        sheet.conditions.append("down")
    return sheet.hp


def heal(sheet, amount):
    if amount < 0:
        raise ValueError("healing cannot be negative")
    if "dead" in sheet.conditions:
        raise ValueError("cannot heal the dead")
    sheet.hp = min(sheet.max_hp, sheet.hp + amount)
    if sheet.hp > 0 and "down" in sheet.conditions:
        sheet.conditions.remove("down")
    return sheet.hp


def carried_weight(sheet):
    return sum(item.weight * item.count for item in sheet.inventory)


def add_item(sheet, item):
    if carried_weight(sheet) + item.weight * item.count > MAX_LOAD:
        raise ValueError("%s is too heavy to carry" % item.name)
    for have in sheet.inventory:
        if have.name == item.name:
            have.count += item.count
            return have.count
    sheet.inventory.append(Item(item.name, item.weight, item.count))
    return item.count


def status_line(sheet):
    flags = ",".join(sorted(sheet.conditions)) or "ok"
    return "%s %d/%d AC%d [%s]" % (sheet.name, sheet.hp, sheet.max_hp, sheet.ac, flags)
'''

SHEET_SPEC = {
    "classes": {"Item": ["name", "weight", "count"], "Sheet": ["name", "hp", "max_hp", "ac", "inventory", "conditions"]},
    "frozen": [],
    "prompt_api": ("`Item(name: str, weight: int, count: int = 1)` and `Sheet(name: str, hp: int, max_hp: int, ac: int, inventory: list[Item] = [], "
                   "conditions: list[str] = [])` (use `field(default_factory=list)` for the lists)"),
    "keys": ["hp", "max_hp", "conditions", "inventory", "weight", "count", "name", "ac"],
    "int_index": False,
    "mutable": True,
}


def sheet_params(rng):
    return {"max_load": rng.choice([30, 40, 60])}


def sheet_cases(rng, p, n):
    out = []
    items = [("rope", 5), ("lantern", 3), ("shield", 12), ("rations", 1), ("anvil", 45), ("potion", 1)]
    for i in range(n):
        mhp = rng.randrange(8, 40)
        sheet = {"name": rng.choice(["Brix", "Orla", "Yoru", "Pell"]), "hp": rng.randrange(0, mhp + 1), "max_hp": mhp, "ac": rng.randrange(8, 20),
                 "inventory": [{"name": n, "weight": w, **({"count": rng.randrange(1, 4)} if rng.random() < 0.5 else {})}
                               for n, w in rng.sample(items, rng.randrange(0, 3))],
                 "conditions": [c for c in ["poisoned", "dead", "prone"] if rng.random() < 0.15]}
        ops = []
        for _ in range(rng.randrange(3, 8)):
            r = rng.random()
            if r < 0.3:
                ops.append(["take_damage", rng.choice([-1, 0, 3, 12, 50])])
            elif r < 0.55:
                ops.append(["heal", rng.choice([-2, 0, 4, 20])])
            elif r < 0.85:
                n, w = rng.choice(items)
                it = {"name": n, "weight": w}
                if rng.random() < 0.4:
                    it["count"] = rng.randrange(1, 5)
                ops.append(["add_item", it])
            else:
                ops.append(["carried_weight"])
        ops += [["status_line"], ["carried_weight"]]
        out.append({"sheet": sheet, "ops": ops})
    return out


SHEET_LEGACY_H = '''
import importlib
MOD = "$pkg.$mod"

def _plain(sheet):
    return {"name": sheet["name"], "hp": sheet["hp"], "max_hp": sheet["max_hp"], "ac": sheet["ac"], "conditions": list(sheet["conditions"]),
            "inventory": [{"name": i["name"], "weight": i["weight"], "count": i.get("count", 1)} for i in sheet["inventory"]]}

def run_case(case):
    mod = importlib.import_module(MOD)
    sheet = json.loads(json.dumps(case["sheet"]))
    results = []
    for op in case["ops"]:
        try:
            if op[0] == "add_item":
                res = mod.add_item(sheet, dict(op[1]))
            else:
                res = getattr(mod, op[0])(sheet, *op[1:]) if op[0] in ("take_damage", "heal") else getattr(mod, op[0])(sheet)
        except Exception as e:
            res = {"raises": type(e).__name__}
        results.append(res)
    return {"results": results, "sheet": _plain(sheet)}
'''

SHEET_NEW_H = '''
import dataclasses, importlib
MOD = "$pkg.$mod"

def run_case(case):
    mod = importlib.import_module(MOD)
    c = case["sheet"]
    sheet = mod.Sheet(name=c["name"], hp=c["hp"], max_hp=c["max_hp"], ac=c["ac"], conditions=list(c["conditions"]),
                      inventory=[mod.Item(name=i["name"], weight=i["weight"], count=i.get("count", 1)) for i in c["inventory"]])
    results = []
    for op in case["ops"]:
        try:
            if op[0] == "add_item":
                i = op[1]
                res = mod.add_item(sheet, mod.Item(name=i["name"], weight=i["weight"], count=i.get("count", 1)))
            else:
                res = getattr(mod, op[0])(sheet, *op[1:]) if op[0] in ("take_damage", "heal") else getattr(mod, op[0])(sheet)
        except Exception as e:
            res = {"raises": type(e).__name__}
        results.append(res)
    return {"results": results, "sheet": dataclasses.asdict(sheet)}
'''

# ----------------------------------------------------------------------------------------------------------------
# D2: dock bookings (dicts)
# ----------------------------------------------------------------------------------------------------------------
DOCK_LEGACY = '''"""Berth allocation and fees for the marina office."""

TIDE_MARGIN = $margin
RATES = $rates
POWER_PER_HOUR = $power


def keel_ok(booking, depth_m):
    return depth_m - booking["draft_m"] >= TIDE_MARGIN


def berth_fee(booking):
    hours = booking["hours"]
    if hours <= 0:
        raise ValueError("hours must be positive")
    base = RATES[booking["kind"]] * hours
    if booking.get("shore_power"):
        base += POWER_PER_HOUR * hours
    return base


def assign_berth(booking, berths):
    for berth in sorted(berths, key=lambda b: (b["max_len_m"], b["id"])):
        if berth["free"] and berth["max_len_m"] >= booking["length_m"] and keel_ok(booking, berth["depth_m"]):
            berth["free"] = False
            return berth["id"]
    return None


def free_berths(berths):
    return sorted(b["id"] for b in berths if b["free"])


def describe(booking):
    power = " +power" if booking.get("shore_power") else ""
    return "%s (%s, %.1fm x %.1fm, %dh%s)" % (booking["vessel"], booking["kind"], booking["length_m"], booking["draft_m"], booking["hours"], power)
'''

DOCK_NEW = '''"""Berth allocation and fees for the marina office."""
from dataclasses import dataclass

TIDE_MARGIN = $margin
RATES = $rates
POWER_PER_HOUR = $power


@dataclass
class Booking:
    vessel: str
    kind: str
    length_m: float
    draft_m: float
    hours: int
    shore_power: bool = False


@dataclass
class Berth:
    id: str
    max_len_m: float
    depth_m: float
    free: bool = True


def keel_ok(booking, depth_m):
    return depth_m - booking.draft_m >= TIDE_MARGIN


def berth_fee(booking):
    if booking.hours <= 0:
        raise ValueError("hours must be positive")
    base = RATES[booking.kind] * booking.hours
    if booking.shore_power:
        base += POWER_PER_HOUR * booking.hours
    return base


def assign_berth(booking, berths):
    for berth in sorted(berths, key=lambda b: (b.max_len_m, b.id)):
        if berth.free and berth.max_len_m >= booking.length_m and keel_ok(booking, berth.depth_m):
            berth.free = False
            return berth.id
    return None


def free_berths(berths):
    return sorted(b.id for b in berths if b.free)


def describe(booking):
    power = " +power" if booking.shore_power else ""
    return "%s (%s, %.1fm x %.1fm, %dh%s)" % (booking.vessel, booking.kind, booking.length_m, booking.draft_m, booking.hours, power)
'''

DOCK_SPEC = {
    "classes": {"Booking": ["vessel", "kind", "length_m", "draft_m", "hours", "shore_power"], "Berth": ["id", "max_len_m", "depth_m", "free"]},
    "frozen": [],
    "prompt_api": ("`Booking(vessel: str, kind: str, length_m: float, draft_m: float, hours: int, shore_power: bool = False)` and "
                   "`Berth(id: str, max_len_m: float, depth_m: float, free: bool = True)`"),
    "keys": ["vessel", "kind", "length_m", "draft_m", "hours", "shore_power", "id", "max_len_m", "depth_m", "free"],
    "int_index": False,
    "mutable": True,
}


def dock_params(rng):
    kinds = rng.sample(["dinghy", "sloop", "ketch", "catamaran", "barge"], 3)
    return {"margin": rng.choice([0.3, 0.5, 0.8]), "rates": json.dumps({k: rng.randrange(150, 1200, 10) for k in kinds}),
            "power": rng.choice([80, 120, 200]), "_kinds": kinds}


def dock_cases(rng, p, n):
    out = []
    for i in range(n):
        berths = [{"id": "B%d" % k, "max_len_m": rng.choice([6.0, 8.5, 10.0, 12.5, 16.0]), "depth_m": rng.choice([1.5, 2.2, 3.0, 4.5]), "free": rng.random() < 0.8}
                  for k in range(rng.randrange(2, 6))]
        ops = []
        for _ in range(rng.randrange(2, 6)):
            b = {"vessel": rng.choice(["Wren", "Petrel", "Skua", "Merlin"]), "kind": rng.choice(p["_kinds"]), "length_m": rng.choice([5.5, 7.0, 9.5, 11.0, 15.0]),
                 "draft_m": rng.choice([0.6, 1.0, 1.8, 2.5]), "hours": rng.choice([0, 2, 6, 24, 72])}
            if rng.random() < 0.4:
                b["shore_power"] = True
            ops.append(b)
        out.append({"berths": berths, "bookings": ops})
    return out


DOCK_LEGACY_H = '''
import importlib
MOD = "$pkg.$mod"

def run_case(case):
    mod = importlib.import_module(MOD)
    berths = json.loads(json.dumps(case["berths"]))
    results = []
    for b in case["bookings"]:
        booking = dict(b)
        row = {}
        for name, fn in (("fee", lambda: mod.berth_fee(booking)), ("berth", lambda: mod.assign_berth(booking, berths)), ("text", lambda: mod.describe(booking))):
            try:
                row[name] = fn()
            except Exception as e:
                row[name] = {"raises": type(e).__name__}
        results.append(row)
    return {"results": results, "free": mod.free_berths(berths), "berths": [[x["id"], x["free"]] for x in berths]}
'''

DOCK_NEW_H = '''
import importlib
MOD = "$pkg.$mod"

def run_case(case):
    mod = importlib.import_module(MOD)
    berths = [mod.Berth(id=x["id"], max_len_m=x["max_len_m"], depth_m=x["depth_m"], free=x["free"]) for x in case["berths"]]
    results = []
    for b in case["bookings"]:
        booking = mod.Booking(vessel=b["vessel"], kind=b["kind"], length_m=b["length_m"], draft_m=b["draft_m"], hours=b["hours"], shore_power=b.get("shore_power", False))
        row = {}
        for name, fn in (("fee", lambda: mod.berth_fee(booking)), ("berth", lambda: mod.assign_berth(booking, berths)), ("text", lambda: mod.describe(booking))):
            try:
                row[name] = fn()
            except Exception as e:
                row[name] = {"raises": type(e).__name__}
        results.append(row)
    return {"results": results, "free": mod.free_berths(berths), "berths": [[x.id, x.free] for x in berths]}
'''

# ----------------------------------------------------------------------------------------------------------------
# T1: lab samples (tuples)
# ----------------------------------------------------------------------------------------------------------------
SAMPLE_LEGACY = '''"""Sample handling rules for the intake bench. A sample is (sample_id, kind, received_day, temp_c, volume_ml)."""

MAX_AGE_DAYS = $max_age
SHORT = 3


def is_stale(sample, today):
    return today - sample[2] > MAX_AGE_DAYS.get(sample[1], 7)


def label(sample):
    return "%s/%s/%d" % (sample[0], sample[1][:SHORT].upper(), sample[2])


def aliquot(sample, parts):
    if parts < 1:
        raise ValueError("parts must be at least 1")
    each = round(sample[4] / parts, 3)
    return [(sample[0] + "-" + chr(ord("a") + i), sample[1], sample[2], sample[3], each) for i in range(parts)]


def warm(samples, limit):
    return [s[0] for s in samples if s[3] > limit]


def total_volume(samples, kind=None):
    return round(sum(s[4] for s in samples if kind is None or s[1] == kind), 3)


def chill(sample, to_temp):
    return (sample[0], sample[1], sample[2], min(sample[3], to_temp), sample[4])
'''

SAMPLE_NEW = '''"""Sample handling rules for the intake bench."""
from dataclasses import dataclass, replace

MAX_AGE_DAYS = $max_age
SHORT = 3


@dataclass(frozen=True)
class Sample:
    sample_id: str
    kind: str
    received_day: int
    temp_c: float
    volume_ml: float


def is_stale(sample, today):
    return today - sample.received_day > MAX_AGE_DAYS.get(sample.kind, 7)


def label(sample):
    return "%s/%s/%d" % (sample.sample_id, sample.kind[:SHORT].upper(), sample.received_day)


def aliquot(sample, parts):
    if parts < 1:
        raise ValueError("parts must be at least 1")
    each = round(sample.volume_ml / parts, 3)
    return [replace(sample, sample_id=sample.sample_id + "-" + chr(ord("a") + i), volume_ml=each) for i in range(parts)]


def warm(samples, limit):
    return [s.sample_id for s in samples if s.temp_c > limit]


def total_volume(samples, kind=None):
    return round(sum(s.volume_ml for s in samples if kind is None or s.kind == kind), 3)


def chill(sample, to_temp):
    return replace(sample, temp_c=min(sample.temp_c, to_temp))
'''

SAMPLE_SPEC = {
    "classes": {"Sample": ["sample_id", "kind", "received_day", "temp_c", "volume_ml"]},
    "frozen": ["Sample"],
    "prompt_api": "a frozen `Sample(sample_id: str, kind: str, received_day: int, temp_c: float, volume_ml: float)`",
    "keys": [],
    "int_index": True,
    "mutable": False,
}


def sample_params(rng):
    kinds = rng.sample(["serum", "plasma", "swab", "tissue", "urine", "saliva"], 3)
    return {"max_age": json.dumps({k: rng.choice([2, 3, 5, 7, 14]) for k in kinds}), "_kinds": kinds}


def sample_cases(rng, p, n):
    out = []
    for i in range(n):
        samples = [["S%02d" % k, rng.choice(p["_kinds"] + ["swab"]), rng.randrange(80, 100), rng.choice([-20.0, 4.0, 8.5, 21.0, 37.0]),
                    rng.choice([0.5, 1.0, 2.5, 10.0, 4.3])] for k in range(rng.randrange(2, 6))]
        out.append({"samples": samples, "today": rng.randrange(95, 110), "parts": rng.choice([0, 1, 2, 3, 4]), "limit": rng.choice([4.0, 10.0, 30.0]),
                    "to_temp": rng.choice([-80.0, 4.0]), "kind": rng.choice([None] + p["_kinds"])})
    return out


SAMPLE_LEGACY_H = '''
import importlib
MOD = "$pkg.$mod"
FIELDS = ["sample_id", "kind", "received_day", "temp_c", "volume_ml"]

def _d(t):
    return dict(zip(FIELDS, t))

def run_case(case):
    mod = importlib.import_module(MOD)
    samples = [tuple(s) for s in case["samples"]]
    out = {"stale": [mod.is_stale(s, case["today"]) for s in samples], "labels": [mod.label(s) for s in samples],
           "warm": mod.warm(samples, case["limit"]), "total": mod.total_volume(samples, case["kind"]),
           "chilled": [_d(mod.chill(s, case["to_temp"])) for s in samples]}
    try:
        out["aliquots"] = [_d(a) for a in mod.aliquot(samples[0], case["parts"])]
    except ValueError as e:
        out["aliquots"] = {"raises": "ValueError"}
    return out
'''

SAMPLE_NEW_H = '''
import dataclasses, importlib
MOD = "$pkg.$mod"

def run_case(case):
    mod = importlib.import_module(MOD)
    samples = [mod.Sample(*s) for s in case["samples"]]
    d = dataclasses.asdict
    out = {"stale": [mod.is_stale(s, case["today"]) for s in samples], "labels": [mod.label(s) for s in samples],
           "warm": mod.warm(samples, case["limit"]), "total": mod.total_volume(samples, case["kind"]),
           "chilled": [d(mod.chill(s, case["to_temp"])) for s in samples]}
    try:
        out["aliquots"] = [d(a) for a in mod.aliquot(samples[0], case["parts"])]
    except ValueError as e:
        out["aliquots"] = {"raises": "ValueError"}
    return out
'''

# ----------------------------------------------------------------------------------------------------------------
# T2: recipe ingredients (tuples)
# ----------------------------------------------------------------------------------------------------------------
RECIPE_LEGACY = '''"""Scaling and shopping lists for the canteen kitchen. An ingredient is (name, qty, unit, optional)."""
import math

STEP_G = $step
ALLERGENS = $allergens


def scale(ingredients, factor):
    if factor <= 0:
        raise ValueError("factor must be positive")
    out = []
    for ing in ingredients:
        qty = ing[1] * factor
        if ing[2] == "g":
            qty = round(qty / STEP_G) * STEP_G
        elif ing[2] == "pcs":
            qty = math.ceil(qty)
        else:
            qty = round(qty, 2)
        out.append((ing[0], qty, ing[2], ing[3]))
    return out


def shopping_list(ingredients, pantry, include_optional=False):
    need = []
    for ing in ingredients:
        if ing[3] and not include_optional:
            continue
        missing = ing[1] - pantry.get(ing[0], 0)
        if missing > 0:
            need.append((ing[0], missing, ing[2]))
    return sorted(need)


def allergens_in(ingredients):
    found = set()
    for ing in ingredients:
        found.update(ALLERGENS.get(ing[0], ()))
    return sorted(found)


def render(ingredients):
    return ["%s: %s %s%s" % (ing[0], ing[1], ing[2], " (optional)" if ing[3] else "") for ing in ingredients]
'''

RECIPE_NEW = '''"""Scaling and shopping lists for the canteen kitchen."""
import math
from dataclasses import dataclass

STEP_G = $step
ALLERGENS = $allergens


@dataclass(frozen=True)
class Ingredient:
    name: str
    qty: float
    unit: str
    optional: bool = False


def scale(ingredients, factor):
    if factor <= 0:
        raise ValueError("factor must be positive")
    out = []
    for ing in ingredients:
        qty = ing.qty * factor
        if ing.unit == "g":
            qty = round(qty / STEP_G) * STEP_G
        elif ing.unit == "pcs":
            qty = math.ceil(qty)
        else:
            qty = round(qty, 2)
        out.append(Ingredient(ing.name, qty, ing.unit, ing.optional))
    return out


def shopping_list(ingredients, pantry, include_optional=False):
    need = []
    for ing in ingredients:
        if ing.optional and not include_optional:
            continue
        missing = ing.qty - pantry.get(ing.name, 0)
        if missing > 0:
            need.append((ing.name, missing, ing.unit))
    return sorted(need)


def allergens_in(ingredients):
    found = set()
    for ing in ingredients:
        found.update(ALLERGENS.get(ing.name, ()))
    return sorted(found)


def render(ingredients):
    return ["%s: %s %s%s" % (ing.name, ing.qty, ing.unit, " (optional)" if ing.optional else "") for ing in ingredients]
'''

RECIPE_SPEC = {
    "classes": {"Ingredient": ["name", "qty", "unit", "optional"]},
    "frozen": ["Ingredient"],
    "prompt_api": ("a frozen `Ingredient(name: str, qty: float, unit: str, optional: bool = False)`; `scale` returns a list of `Ingredient`, and "
                   "`shopping_list` keeps returning plain `(name, missing, unit)` tuples"),
    "keys": [],
    "int_index": True,
    "mutable": False,
}


def recipe_params(rng):
    names = ["flour", "butter", "egg", "milk", "peanut", "sesame", "rye", "oat"]
    al = {n: rng.sample(["gluten", "dairy", "egg", "nuts", "sesame"], rng.randrange(1, 3)) for n in rng.sample(names, 5)}
    return {"step": rng.choice([5, 10, 25]), "allergens": json.dumps({k: sorted(v) for k, v in al.items()}), "_names": names}


def recipe_cases(rng, p, n):
    out = []
    for i in range(n):
        ings = [[nm, rng.choice([2, 3, 150, 250.5, 480, 0.75]), rng.choice(["g", "pcs", "l"]), rng.random() < 0.25] for nm in rng.sample(p["_names"], rng.randrange(2, 6))]
        out.append({"ingredients": ings, "factor": rng.choice([0, 0.5, 1, 1.5, 2.25, 3, 10]),
                    "pantry": {nm: rng.choice([0, 1, 100, 400]) for nm in p["_names"][:4]}, "optional": rng.random() < 0.5})
    return out


RECIPE_LEGACY_H = '''
import importlib
MOD = "$pkg.$mod"
FIELDS = ["name", "qty", "unit", "optional"]

def _d(t):
    return dict(zip(FIELDS, t))

def run_case(case):
    mod = importlib.import_module(MOD)
    ings = [tuple(i) for i in case["ingredients"]]
    try:
        scaled = [_d(x) for x in mod.scale(ings, case["factor"])]
    except ValueError:
        scaled = {"raises": "ValueError"}
    return {"scaled": scaled, "shopping": [list(x) for x in mod.shopping_list(ings, case["pantry"], case["optional"])],
            "allergens": mod.allergens_in(ings), "rendered": mod.render(ings)}
'''

RECIPE_NEW_H = '''
import dataclasses, importlib
MOD = "$pkg.$mod"

def run_case(case):
    mod = importlib.import_module(MOD)
    ings = [mod.Ingredient(*i) for i in case["ingredients"]]
    try:
        scaled = [dataclasses.asdict(x) for x in mod.scale(ings, case["factor"])]
    except ValueError:
        scaled = {"raises": "ValueError"}
    return {"scaled": scaled, "shopping": [list(x) for x in mod.shopping_list(ings, case["pantry"], case["optional"])],
            "allergens": mod.allergens_in(ings), "rendered": mod.render(ings)}
'''

DOMAINS = [
    dict(key="sheets", pkg="campaign", mod="sheets", legacy=SHEET_LEGACY, new=SHEET_NEW, spec=SHEET_SPEC, params=sheet_params, cases=sheet_cases,
         lh=SHEET_LEGACY_H, nh=SHEET_NEW_H, topic="character sheet", record="character sheet"),
    dict(key="dock", pkg="marina", mod="berths", legacy=DOCK_LEGACY, new=DOCK_NEW, spec=DOCK_SPEC, params=dock_params, cases=dock_cases,
         lh=DOCK_LEGACY_H, nh=DOCK_NEW_H, topic="berth office", record="booking and berth"),
    dict(key="samples", pkg="intake", mod="samples", legacy=SAMPLE_LEGACY, new=SAMPLE_NEW, spec=SAMPLE_SPEC, params=sample_params, cases=sample_cases,
         lh=SAMPLE_LEGACY_H, nh=SAMPLE_NEW_H, topic="sample bench", record="sample tuple"),
    dict(key="recipes", pkg="canteen", mod="recipes", legacy=RECIPE_LEGACY, new=RECIPE_NEW, spec=RECIPE_SPEC, params=recipe_params, cases=recipe_cases,
         lh=RECIPE_LEGACY_H, nh=RECIPE_NEW_H, topic="canteen recipe", record="ingredient tuple"),
]

PROMPTS = [
    "In `{path}` the {record}s are passed around as {legacy_kind} and every function reaches into them with {access}. Replace them with dataclasses: {api}. "
    "Functions keep their names and behaviour but take and return the new types instead (the visible tests show the calls). No function should index "
    "a {record} with {access2} any more.",
    "The {topic} code ({path}) is a pile of {legacy_kind}; I keep getting {access} wrong. Introduce proper types: {api}. Update every function in the module "
    "accordingly, keep the logic exactly as it is, and stop using {access2} to read fields.",
    "replace the {legacy_kind} in `{path}` with dataclasses ({api}). same functions, same results, attribute access instead of {access2}.",
]


@family("refactor-py-dataclasses", category="refactor", lang="python", kind="refactor", n=10,
        summary="dict and tuple records become (frozen) dataclasses with the stated fields; callers and functions switch to attribute access")
def gen(rng, n):
    order = list(DOMAINS) * 3
    rng.shuffle(order)
    for i in range(n):
        dom = order[i]
        p = dom["params"](rng)
        subs = {k: v for k, v in p.items() if not k.startswith("_")}
        pkg, mod = dom["pkg"], dom["mod"]
        path = f"{pkg}/{mod}.py"
        legacy = Template(dom["legacy"]).substitute(subs)
        new = Template(dom["new"]).substitute(subs)
        files = {path: legacy, f"{pkg}/__init__.py": ""}
        cases = dom["cases"](rng, p, 22)
        sub2 = {"pkg": pkg, "mod": mod}
        lh = "import json\n" + Template(dom["lh"]).substitute(sub2)
        nh = "import json\n" + Template(dom["nh"]).substitute(sub2)
        beh = py_behaviour(files, lh, cases, "recorded", test_harness=nh)
        want = _kit.py_golden(files, lh, cases)
        vis = ["import json", "import unittest", "", nh.replace("import json\n", "", 1).strip("\n"), "", "def norm(x):", "    return json.loads(json.dumps(x))", "", "",
               "class RecordTests(unittest.TestCase):"]
        for t, j in enumerate([0, 1, 2]):
            vis += [f"    def test_example_{t + 1}(self):", f"        case = json.loads({json.dumps(json.dumps(cases[j]))})",
                    f"        self.assertEqual(norm(run_case(case)), json.loads({json.dumps(json.dumps(want[j]))}))", ""]
        vis += ["", "if __name__ == '__main__':", "    unittest.main()", ""]
        start = {**files, f"tests/test_{mod}.py": "\n".join(vis)}
        spec = dom["spec"]
        struct = dd(f'''
        import ast
        import unittest

        import structlib as S

        PATH = "{path}"
        CLASSES = {json.dumps(spec['classes'])}
        FROZEN = {json.dumps(spec['frozen'])}
        KEYS = {json.dumps(spec['keys'])}
        INT_INDEX = {spec['int_index']!r}


        def is_dataclass(cls):
            for d in cls.decorator_list:
                target = d.func if isinstance(d, ast.Call) else d
                name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
                if name == "dataclass":
                    frozen = isinstance(d, ast.Call) and any(k.arg == "frozen" and getattr(k.value, "value", False) is True for k in d.keywords)
                    return True, frozen
            return False, False


        class StructureTests(unittest.TestCase):
            def setUp(self):
                self.tree = S.parse(PATH)

            def test_dataclasses_exist_with_the_stated_fields(self):
                classes = {{c.name: c for c in S.classes(self.tree)}}
                for name, fields in CLASSES.items():
                    self.assertIn(name, classes, "missing class %s" % name)
                    ok, frozen = is_dataclass(classes[name])
                    self.assertTrue(ok, "%s must be a dataclass" % name)
                    if name in FROZEN:
                        self.assertTrue(frozen, "%s must be frozen" % name)
                    got = [n.target.id for n in classes[name].body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)]
                    self.assertEqual(got, fields, "fields of %s" % name)

            def test_no_string_keys_or_positional_indexes_left(self):
                bad = []
                for q, fn in S.functions(self.tree):
                    for n in ast.walk(fn):
                        if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant):
                            v = n.slice.value
                            if isinstance(v, str) and v in KEYS:
                                bad.append("%s indexes with the key %r (line %d)" % (q, v, n.lineno))
                            if INT_INDEX and isinstance(v, int) and not isinstance(v, bool):
                                bad.append("%s indexes with the position %d (line %d)" % (q, v, n.lineno))
                self.assertFalse(bad, S.format_problems(bad))
        ''')
        hidden = {"tests/test_more_behaviour.py": beh, "tests/test_zz_structure.py": struct, **py_structlib()}
        solution = {path: new}
        prove(dom["key"], start, hidden, solution, _kit.PY_BEHAVIOUR_CMD, _kit.PY_STRUCT_CMD, "python3 -m unittest discover -s tests", behaviour_on_start=False)
        tup = spec["int_index"]
        prompt = rng.choice(PROMPTS).format(
            path=path, record=dom["record"], topic=dom["topic"], api=spec["prompt_api"],
            legacy_kind="positional tuples" if tup else "plain dicts", access="magic index numbers" if tup else "string keys",
            access2="`[0]`, `[1]`, ..." if tup else "`[\"key\"]`")
        d = 2 if dom["key"] in ("dock", "samples") and rng.random() < 0.5 else 3 if dom["key"] != "sheets" else 4
        yield Task(slug=f"{i + 1:02d}-{dom['key']}", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution,
                   verify="python3 -m unittest discover -s tests -v", tags=["dataclasses", "typed-records"], notes={"domain": dom["key"]})
