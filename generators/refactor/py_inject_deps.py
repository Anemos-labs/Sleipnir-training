"""Replace global state and hidden collaborators (clock, ids, randomness, output) with injected dependencies (python)."""
from __future__ import annotations

import json
from string import Template

from fx import Task, dd, family

from . import _kit
from ._kit import prove, py_behaviour, py_structlib

structlib = _kit.load_structlib()

DRIVE = '''
def drive(ops, call, advance):
    results = []
    for op in ops:
        name, args = op[0], op[1:]
        if name == "advance":
            advance(args[0])
            continue
        args = [results[a["ref"]] if isinstance(a, dict) and "ref" in a else a for a in args]
        try:
            res = call(name, *args)
        except Exception as e:
            res = {"raises": type(e).__name__}
        results.append(res)
    return results


class FakeClock:
    def __init__(self, t0):
        self.now = t0

    def time(self):
        return self.now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds
'''

# ---------------------------------------------------------------------------------------------------------------
# A: street parking meters
# ---------------------------------------------------------------------------------------------------------------
PARKING_LEGACY = '''"""Street parking meters: sessions and charges."""
import time

RATES = $rates
BLOCK_MINUTES = $block
MIN_CHARGE = $min_charge

_SESSIONS = {}
_NEXT_ID = [1000]


def start_session(plate, zone):
    if zone not in RATES:
        raise ValueError("unknown zone: %s" % zone)
    for s in _SESSIONS.values():
        if s["plate"] == plate:
            raise ValueError("%s already has a session" % plate)
    sid = _NEXT_ID[0]
    _NEXT_ID[0] += 1
    _SESSIONS[sid] = {"plate": plate, "zone": zone, "start": time.time()}
    return sid


def stop_session(sid):
    s = _SESSIONS.pop(sid, None)
    if s is None:
        raise KeyError(sid)
    minutes = (time.time() - s["start"]) / 60.0
    blocks = int(minutes // BLOCK_MINUTES) + (1 if minutes % BLOCK_MINUTES else 0)
    charge = max(MIN_CHARGE, blocks * RATES[s["zone"]])
    print("receipt %d: %s zone %s %d min -> %d" % (sid, s["plate"], s["zone"], int(minutes), charge))
    return charge


def open_sessions():
    return sorted(s["plate"] for s in _SESSIONS.values())
'''

PARKING_NEW = '''"""Street parking meters: sessions and charges."""
import time

DEFAULT_RATES = $rates
BLOCK_MINUTES = $block
MIN_CHARGE = $min_charge


class MeterDesk:
    """Sessions and charges for one set of street meters."""

    def __init__(self, rates=None, clock=time.time, new_id=None, notify=print):
        self.rates = dict(DEFAULT_RATES if rates is None else rates)
        self.clock = clock
        self.new_id = new_id
        self.notify = notify
        self.sessions = {}

    def start_session(self, plate, zone):
        if zone not in self.rates:
            raise ValueError("unknown zone: %s" % zone)
        for s in self.sessions.values():
            if s["plate"] == plate:
                raise ValueError("%s already has a session" % plate)
        sid = self.new_id()
        self.sessions[sid] = {"plate": plate, "zone": zone, "start": self.clock()}
        return sid

    def stop_session(self, sid):
        s = self.sessions.pop(sid, None)
        if s is None:
            raise KeyError(sid)
        minutes = (self.clock() - s["start"]) / 60.0
        blocks = int(minutes // BLOCK_MINUTES) + (1 if minutes % BLOCK_MINUTES else 0)
        charge = max(MIN_CHARGE, blocks * self.rates[s["zone"]])
        self.notify("receipt %d: %s zone %s %d min -> %d" % (sid, s["plate"], s["zone"], int(minutes), charge))
        return charge

    def open_sessions(self):
        return sorted(s["plate"] for s in self.sessions.values())
'''


def parking_params(rng):
    zones = rng.sample(["A", "B", "C", "D", "E"], rng.choice([3, 3, 4]))
    rates = {z: rng.randrange(40, 260, 10) for z in zones}
    return {"rates": json.dumps(rates), "block": rng.choice([10, 15, 30]), "min_charge": rng.choice([60, 100, 150]), "_zones": zones, "_rates": rates}


def parking_ops(rng, p, n):
    cases = []
    for c in range(n):
        ops, started = [], 0
        for _ in range(rng.randrange(4, 12)):
            r = rng.random()
            if r < 0.4 or started == 0:
                ops.append(["start_session", rng.choice(["AB-%d" % rng.randrange(10, 40), "ZZ-1"]), rng.choice(p["_zones"] + (["Q"] if rng.random() < 0.08 else []))])
                started += 1
            elif r < 0.65:
                ops.append(["advance", rng.choice([30, 240, 600, 899, 900, 901, 3600, 7260])])
            elif r < 0.9:
                ops.append(["stop_session", {"ref": rng.randrange(0, len(ops) + 1) if False else _first_ref(ops, "start_session", rng)}])
            else:
                ops.append(["open_sessions"])
        ops.append(["open_sessions"])
        cases.append({"t0": 1_000_000, "ops": ops})
    return cases


def _first_ref(ops, name, rng):
    idx = [k for k, o in enumerate([o for o in ops if o[0] != "advance"]) if o[0] == name]
    return rng.choice(idx) if idx else 0


PARKING_LEGACY_HARNESS = '''
import contextlib, importlib, io
MOD = "$pkg.$mod"
''' + DRIVE + '''
def run_case(case):
    mod = importlib.reload(importlib.import_module(MOD))
    clock = FakeClock(case["t0"])
    mod.time = clock
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        results = drive(case["ops"], lambda n, *a: getattr(mod, n)(*a), clock.advance)
    return {"results": results, "notes": buf.getvalue().splitlines()}
'''

PARKING_NEW_HARNESS = '''
import importlib, itertools
MOD = "$pkg.$mod"
''' + DRIVE + '''
def run_case(case):
    mod = importlib.import_module(MOD)
    clock = FakeClock(case["t0"])
    notes, ids = [], itertools.count(1000)
    desk = mod.MeterDesk(rates=$rates, clock=clock, new_id=lambda: next(ids), notify=notes.append)
    results = drive(case["ops"], lambda n, *a: getattr(desk, n)(*a), clock.advance)
    return {"results": results, "notes": notes}
'''

# ---------------------------------------------------------------------------------------------------------------
# B: coupons with randomness
# ---------------------------------------------------------------------------------------------------------------
COUPON_LEGACY = '''"""Promo coupons: issue a code, redeem it once before it expires."""
import random
import time

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = $length
TTL_SECONDS = $ttl
PERCENT = $percent

_ISSUED = {}


def _new_code():
    return "".join(random.choice(ALPHABET) for _ in range(CODE_LENGTH))


def issue(customer, kind):
    if kind not in PERCENT:
        raise ValueError("unknown coupon kind: %s" % kind)
    code = _new_code()
    while code in _ISSUED:
        code = _new_code()
    _ISSUED[code] = {"customer": customer, "kind": kind, "expires": time.time() + TTL_SECONDS, "used": False}
    return code


def redeem(code, customer, amount_cents):
    c = _ISSUED.get(code)
    if c is None:
        raise KeyError(code)
    if c["customer"] != customer:
        raise PermissionError("coupon belongs to someone else")
    if c["used"]:
        raise ValueError("coupon already used")
    if time.time() > c["expires"]:
        raise ValueError("coupon expired")
    c["used"] = True
    off = amount_cents * PERCENT[c["kind"]] // 100
    print("redeemed %s for %s: -%d" % (code, customer, off))
    return off


def outstanding(customer):
    return sorted(code for code, c in _ISSUED.items() if c["customer"] == customer and not c["used"])
'''

COUPON_NEW = '''"""Promo coupons: issue a code, redeem it once before it expires."""
import random
import time

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = $length
TTL_SECONDS = $ttl
DEFAULT_PERCENT = $percent


class CouponDesk:
    """Issues and redeems coupons; randomness, time and output come from the caller."""

    def __init__(self, percent=None, rng=None, clock=time.time, notify=print):
        self.percent = dict(DEFAULT_PERCENT if percent is None else percent)
        self.rng = rng if rng is not None else random.Random()
        self.clock = clock
        self.notify = notify
        self.issued = {}

    def _new_code(self):
        return "".join(self.rng.choice(ALPHABET) for _ in range(CODE_LENGTH))

    def issue(self, customer, kind):
        if kind not in self.percent:
            raise ValueError("unknown coupon kind: %s" % kind)
        code = self._new_code()
        while code in self.issued:
            code = self._new_code()
        self.issued[code] = {"customer": customer, "kind": kind, "expires": self.clock() + TTL_SECONDS, "used": False}
        return code

    def redeem(self, code, customer, amount_cents):
        c = self.issued.get(code)
        if c is None:
            raise KeyError(code)
        if c["customer"] != customer:
            raise PermissionError("coupon belongs to someone else")
        if c["used"]:
            raise ValueError("coupon already used")
        if self.clock() > c["expires"]:
            raise ValueError("coupon expired")
        c["used"] = True
        off = amount_cents * self.percent[c["kind"]] // 100
        self.notify("redeemed %s for %s: -%d" % (code, customer, off))
        return off

    def outstanding(self, customer):
        return sorted(code for code, c in self.issued.items() if c["customer"] == customer and not c["used"])
'''


def coupon_params(rng):
    kinds = rng.sample(["welcome", "loyal", "apology", "birthday", "referral"], 3)
    pct = {k: rng.choice([5, 10, 15, 20, 25]) for k in kinds}
    return {"length": rng.choice([5, 6, 8]), "ttl": rng.choice([3600, 86400, 604800]), "percent": json.dumps(pct), "_kinds": kinds, "_pct": pct}


def coupon_ops(rng, p, n):
    cases = []
    for c in range(n):
        ops, issued = [], 0
        for _ in range(rng.randrange(4, 12)):
            r = rng.random()
            who = rng.choice(["ana", "ben", "cora"])
            if r < 0.35 or issued == 0:
                ops.append(["issue", who, rng.choice(p["_kinds"] + (["mystery"] if rng.random() < 0.08 else []))])
                issued += 1
            elif r < 0.55:
                ops.append(["advance", rng.choice([60, 3000, 90000, 700000])])
            elif r < 0.9:
                ops.append(["redeem", {"ref": _first_ref(ops, "issue", rng)}, who, rng.choice([500, 1999, 12000])])
            else:
                ops.append(["outstanding", who])
        ops += [["outstanding", "ana"], ["outstanding", "ben"]]
        cases.append({"t0": 5_000, "seed": rng.randrange(1, 10**6), "ops": ops})
    return cases


COUPON_LEGACY_HARNESS = '''
import contextlib, importlib, io, random
MOD = "$pkg.$mod"
''' + DRIVE + '''
def run_case(case):
    mod = importlib.reload(importlib.import_module(MOD))
    clock = FakeClock(case["t0"])
    mod.time = clock
    mod.random = random.Random(case["seed"])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        results = drive(case["ops"], lambda n, *a: getattr(mod, n)(*a), clock.advance)
    return {"results": results, "notes": buf.getvalue().splitlines()}
'''

COUPON_NEW_HARNESS = '''
import importlib, random
MOD = "$pkg.$mod"
''' + DRIVE + '''
def run_case(case):
    mod = importlib.import_module(MOD)
    clock = FakeClock(case["t0"])
    notes = []
    desk = mod.CouponDesk(percent=$percent, rng=random.Random(case["seed"]), clock=clock, notify=notes.append)
    results = drive(case["ops"], lambda n, *a: getattr(desk, n)(*a), clock.advance)
    return {"results": results, "notes": notes}
'''

# ---------------------------------------------------------------------------------------------------------------
# C: sensor alerts with a cooldown
# ---------------------------------------------------------------------------------------------------------------
ALERT_LEGACY = '''"""Threshold alerts for plant sensors, at most one mail per sensor per cooldown."""
import time

LIMITS = $limits
COOLDOWN = $cooldown
RECIPIENT = "$to"

OUTBOX = []
_LAST = {}


def _send(to, text):
    # stand-in for the SMTP relay
    OUTBOX.append((to, text))


def record(sensor, value):
    limit = LIMITS.get(sensor)
    if limit is None:
        raise KeyError(sensor)
    if value <= limit:
        return False
    now = time.time()
    last = _LAST.get(sensor)
    if last is not None and now - last < COOLDOWN:
        return False
    _LAST[sensor] = now
    _send(RECIPIENT, "%s high: %s" % (sensor, value))
    return True


def quiet_since(sensor):
    return _LAST.get(sensor)
'''

ALERT_NEW = '''"""Threshold alerts for plant sensors, at most one mail per sensor per cooldown."""
import time

DEFAULT_LIMITS = $limits
COOLDOWN = $cooldown
RECIPIENT = "$to"


class AlertDesk:
    """Decides when a reading deserves a mail; the clock and the mail relay are injected."""

    def __init__(self, limits=None, clock=time.time, send=None):
        self.limits = dict(DEFAULT_LIMITS if limits is None else limits)
        self.clock = clock
        self.send = send
        self.last = {}

    def record(self, sensor, value):
        limit = self.limits.get(sensor)
        if limit is None:
            raise KeyError(sensor)
        if value <= limit:
            return False
        now = self.clock()
        last = self.last.get(sensor)
        if last is not None and now - last < COOLDOWN:
            return False
        self.last[sensor] = now
        self.send(RECIPIENT, "%s high: %s" % (sensor, value))
        return True

    def quiet_since(self, sensor):
        return self.last.get(sensor)
'''


def alert_params(rng):
    sensors = rng.sample(["temp", "vibration", "humidity", "pressure", "flow", "ph"], 3)
    limits = {s: rng.choice([5.5, 30.0, 80.0, 101.5, 7.25]) for s in sensors}
    return {"limits": json.dumps(limits), "cooldown": rng.choice([300, 600, 1800]), "to": rng.choice(["ops@plant.example", "oncall@mill.example"]),
            "_sensors": sensors, "_limits": limits}


def alert_ops(rng, p, n):
    cases = []
    for c in range(n):
        ops = []
        for _ in range(rng.randrange(5, 14)):
            s = rng.choice(p["_sensors"] + (["ghost"] if rng.random() < 0.06 else []))
            r = rng.random()
            if r < 0.55:
                lim = p["_limits"].get(s, 10)
                ops.append(["record", s, round(lim + rng.choice([-3, -0.5, 0, 0.5, 2, 9]), 2)])
            elif r < 0.85:
                ops.append(["advance", rng.choice([10, 200, 299, 300, 599, 600, 1799, 2000])])
            else:
                ops.append(["quiet_since", s])
        cases.append({"t0": 100, "ops": ops})
    return cases


ALERT_LEGACY_HARNESS = '''
import importlib
MOD = "$pkg.$mod"
''' + DRIVE + '''
def run_case(case):
    mod = importlib.reload(importlib.import_module(MOD))
    clock = FakeClock(case["t0"])
    mod.time = clock
    results = drive(case["ops"], lambda n, *a: getattr(mod, n)(*a), clock.advance)
    return {"results": results, "notes": [list(m) for m in mod.OUTBOX]}
'''

ALERT_NEW_HARNESS = '''
import importlib
MOD = "$pkg.$mod"
''' + DRIVE + '''
def run_case(case):
    mod = importlib.import_module(MOD)
    clock = FakeClock(case["t0"])
    outbox = []
    desk = mod.AlertDesk(limits=$limits, clock=clock, send=lambda to, text: outbox.append([to, text]))
    results = drive(case["ops"], lambda n, *a: getattr(desk, n)(*a), clock.advance)
    return {"results": results, "notes": outbox}
'''

# ---------------------------------------------------------------------------------------------------------------
# D: library holds
# ---------------------------------------------------------------------------------------------------------------
HOLDS_LEGACY = '''"""Hold queues for popular library books."""
from datetime import date

HOLD_DAYS = $days
MAX_HOLDS = $max_holds

OUTBOX = []
_QUEUES = {}


def _mail(member, text):
    OUTBOX.append((member, text))


def _today():
    return date.today().toordinal()


def place_hold(member, book):
    queue = _QUEUES.setdefault(book, [])
    if any(m == member for m, _ in queue):
        raise ValueError("%s already waits for %s" % (member, book))
    if sum(1 for q in _QUEUES.values() for m, _ in q if m == member) >= MAX_HOLDS:
        raise ValueError("%s has too many holds" % member)
    queue.append((member, _today()))
    return len(queue)


def return_book(book):
    queue = _QUEUES.get(book, [])
    today = _today()
    while queue:
        member, since = queue.pop(0)
        if today - since > HOLD_DAYS:
            _mail(member, "your hold on %s expired" % book)
            continue
        _mail(member, "%s is ready for you for %d days" % (book, HOLD_DAYS))
        return member
    return None


def waiting(book):
    return [m for m, _ in _QUEUES.get(book, [])]
'''

HOLDS_NEW = '''"""Hold queues for popular library books."""
from datetime import date

HOLD_DAYS = $days
MAX_HOLDS = $max_holds


def system_today():
    return date.today().toordinal()


class HoldDesk:
    """Hold queues; the calendar and the mailer are injected."""

    def __init__(self, today=system_today, mail=None):
        self.today = today
        self.mail = mail
        self.queues = {}

    def place_hold(self, member, book):
        queue = self.queues.setdefault(book, [])
        if any(m == member for m, _ in queue):
            raise ValueError("%s already waits for %s" % (member, book))
        if sum(1 for q in self.queues.values() for m, _ in q if m == member) >= MAX_HOLDS:
            raise ValueError("%s has too many holds" % member)
        queue.append((member, self.today()))
        return len(queue)

    def return_book(self, book):
        queue = self.queues.get(book, [])
        today = self.today()
        while queue:
            member, since = queue.pop(0)
            if today - since > HOLD_DAYS:
                self.mail(member, "your hold on %s expired" % book)
                continue
            self.mail(member, "%s is ready for you for %d days" % (book, HOLD_DAYS))
            return member
        return None

    def waiting(self, book):
        return [m for m, _ in self.queues.get(book, [])]
'''


def holds_params(rng):
    return {"days": rng.choice([3, 5, 7, 10]), "max_holds": rng.choice([2, 3, 4])}


def holds_ops(rng, p, n):
    cases = []
    books = ["Dune Atlas", "Tide Almanac", "Moss Field Guide", "Kiln Manual"]
    for c in range(n):
        ops = []
        for _ in range(rng.randrange(6, 16)):
            r = rng.random()
            if r < 0.45:
                ops.append(["place_hold", rng.choice(["ila", "joss", "kit", "lou", "max"]), rng.choice(books)])
            elif r < 0.65:
                ops.append(["advance", rng.choice([1, 2, 4, 6, 9, 15])])
            elif r < 0.9:
                ops.append(["return_book", rng.choice(books)])
            else:
                ops.append(["waiting", rng.choice(books)])
        ops += [["waiting", b] for b in books[:2]]
        cases.append({"t0": 739000, "ops": ops})
    return cases


HOLDS_LEGACY_HARNESS = '''
import datetime, importlib
MOD = "$pkg.$mod"
''' + DRIVE + '''
class FakeDate:
    clock = None

    @classmethod
    def today(cls):
        return datetime.date.fromordinal(int(cls.clock.now))


def run_case(case):
    mod = importlib.reload(importlib.import_module(MOD))
    clock = FakeClock(case["t0"])
    FakeDate.clock = clock
    mod.date = FakeDate
    results = drive(case["ops"], lambda n, *a: getattr(mod, n)(*a), clock.advance)
    return {"results": results, "notes": [list(m) for m in mod.OUTBOX]}
'''

HOLDS_NEW_HARNESS = '''
import importlib
MOD = "$pkg.$mod"
''' + DRIVE + '''
def run_case(case):
    mod = importlib.import_module(MOD)
    clock = FakeClock(case["t0"])
    outbox = []
    desk = mod.HoldDesk(today=lambda: int(clock.now), mail=lambda member, text: outbox.append([member, text]))
    results = drive(case["ops"], lambda n, *a: getattr(desk, n)(*a), clock.advance)
    return {"results": results, "notes": outbox}
'''

DOMAINS = [
    dict(key="parking", pkg="meters", mod="desk", cls="MeterDesk", legacy=PARKING_LEGACY, new=PARKING_NEW, params=parking_params, ops=parking_ops,
         lh=PARKING_LEGACY_HARNESS, nh=PARKING_NEW_HARNESS, forbid=["time.time", "print"], topic="street parking meters",
         ctor="MeterDesk(rates, clock, new_id, notify)",
         api=("`rates` is the zone -> price dict that is currently the `RATES` constant, `clock()` returns the current time in seconds, `new_id()` returns the next "
              "session id (it used to count up from 1000), and `notify(text)` receives each receipt line that is printed today"),
         methods="`start_session`, `stop_session` and `open_sessions`", ctor_args=["rates", "clock", "new_id", "notify"],
         params_for_harness=lambda p: {"rates": json.dumps(p["_rates"])}),
    dict(key="coupons", pkg="promo", mod="coupons", cls="CouponDesk", legacy=COUPON_LEGACY, new=COUPON_NEW, params=coupon_params, ops=coupon_ops,
         lh=COUPON_LEGACY_HARNESS, nh=COUPON_NEW_HARNESS, forbid=["time.time", "random.choice", "random.random", "print"], topic="promo coupons",
         ctor="CouponDesk(percent, rng, clock, notify)",
         api=("`percent` is the kind -> discount percentage dict (today `PERCENT`), `rng` is a `random.Random`-like object whose `choice` picks the code characters, "
              "`clock()` returns the time in seconds, and `notify(text)` receives the line that is printed on redemption"),
         methods="`issue`, `redeem` and `outstanding`", ctor_args=["percent", "rng", "clock", "notify"],
         params_for_harness=lambda p: {"percent": json.dumps(p["_pct"])}),
    dict(key="alerts", pkg="plantwatch", mod="alerts", cls="AlertDesk", legacy=ALERT_LEGACY, new=ALERT_NEW, params=alert_params, ops=alert_ops,
         lh=ALERT_LEGACY_HARNESS, nh=ALERT_NEW_HARNESS, forbid=["time.time"], topic="sensor alerts",
         ctor="AlertDesk(limits, clock, send)",
         api=("`limits` is the sensor -> limit dict (today `LIMITS`), `clock()` returns the time in seconds and `send(to, text)` replaces the private `_send` "
              "that fills `OUTBOX`"),
         methods="`record` and `quiet_since`", ctor_args=["limits", "clock", "send"],
         params_for_harness=lambda p: {"limits": json.dumps(p["_limits"])}),
    dict(key="holds", pkg="holdshelf", mod="holds", cls="HoldDesk", legacy=HOLDS_LEGACY, new=HOLDS_NEW, params=holds_params, ops=holds_ops,
         lh=HOLDS_LEGACY_HARNESS, nh=HOLDS_NEW_HARNESS, forbid=["date.today"], topic="library holds",
         ctor="HoldDesk(today, mail)",
         api=("`today()` returns the current day number (what `date.today().toordinal()` gives today) and `mail(member, text)` replaces the private `_mail` "
              "that fills `OUTBOX`"),
         methods="`place_hold`, `return_book` and `waiting`", ctor_args=["today", "mail"], params_for_harness=lambda p: {}),
]

PROMPTS = [
    "`{pkg}/{mod}.py` ({topic}) works through module-level state and calls `time`/`random`/`print` directly, so the tests that exist today have to monkeypatch "
    "module internals and cannot run two desks side by side. Turn it into a class `{ctor}` with {methods} as methods (same names, same behaviour as the module "
    "functions they replace). Where the arguments are concerned: {api}. Everything it needs must come in through the constructor: no module-level mutable state, "
    "no `global`, and no direct calls to {forbidden} inside the class. The visible tests show how it will be driven.",
    "Make the {topic} code testable. Right now `{pkg}/{mod}.py` keeps its state in module globals and reaches for the clock and output itself. Refactor into "
    "`{ctor}` offering {methods}. {api_cap}. The behaviour has to stay identical, including the exact text that was passed to the output hook, but nothing "
    "may be global or hidden any more (no `global`, no mutable module-level containers, no direct {forbidden}).",
    "dependency injection for `{pkg}/{mod}.py`: class `{ctor}`, methods {methods}. {api_cap}. no module-level state, no `global`, no direct {forbidden} in the class. "
    "same behaviour as before",
]


def _fmt(names):
    return ", ".join(f"`{n}`" for n in names)


@family("refactor-py-inject-deps", category="refactor", lang="python", kind="refactor", n=12,
        summary="replace module globals and hard-wired clock/random/output with a class taking injected collaborators (constructor API stated)")
def gen(rng, n):
    order = list(DOMAINS) * 3
    rng.shuffle(order)
    for i in range(n):
        dom = order[i]
        p = dom["params"](rng)
        subs = {k: v for k, v in p.items() if not k.startswith("_")}
        legacy = Template(dom["legacy"]).substitute(subs)
        new = Template(dom["new"]).substitute(subs)
        pkg, mod = dom["pkg"], dom["mod"]
        path = f"{pkg}/{mod}.py"
        files = {path: legacy, f"{pkg}/__init__.py": ""}
        cases = dom["ops"](rng, p, 24)
        sub2 = {"pkg": pkg, "mod": mod, **dom["params_for_harness"](p)}
        lh = Template(dom["lh"]).substitute(sub2)
        nh = Template(dom["nh"]).substitute(sub2)
        beh = py_behaviour(files, lh, cases, "recorded", test_harness=nh)
        want = _kit.py_golden(files, lh, cases)
        vis_idx = [j for j, w in enumerate(want) if len(w["notes"]) >= 1][:3] or [0, 1]
        vis = ["import json", "import unittest", "", nh.strip("\n"), "", "def norm(x):", "    return json.loads(json.dumps(x))", "", "",
               f"class {dom['cls']}Tests(unittest.TestCase):"]
        for t, j in enumerate(vis_idx):
            vis += [f"    def test_scenario_{t + 1}(self):", f"        case = json.loads({json.dumps(json.dumps(cases[j]))})",
                    f"        self.assertEqual(norm(run_case(case)), json.loads({json.dumps(json.dumps(want[j]))}))", ""]
        vis += ["", "if __name__ == '__main__':", "    unittest.main()", ""]
        start = {**files, f"tests/test_{mod}.py": "\n".join(vis)}
        solution = {path: new}
        forbidden = dom["forbid"]
        struct = dd(f'''
        import ast
        import unittest

        import structlib as S

        PATH = "{path}"
        CLASS = "{dom['cls']}"
        CTOR_ARGS = {json.dumps(dom['ctor_args'])}
        FORBIDDEN = {json.dumps(forbidden)}


        class StructureTests(unittest.TestCase):
            def setUp(self):
                self.tree = S.parse(PATH)

            def test_class_exists_with_injected_constructor(self):
                classes = {{c.name: c for c in S.classes(self.tree)}}
                self.assertIn(CLASS, classes)
                init = [n for n in classes[CLASS].body if isinstance(n, ast.FunctionDef) and n.name == "__init__"]
                self.assertTrue(init, "%s needs an __init__" % CLASS)
                args = [a.arg for a in init[0].args.args + init[0].args.kwonlyargs]
                missing = [a for a in CTOR_ARGS if a not in args]
                self.assertFalse(missing, "constructor lacks parameters: %s" % missing)

            def test_no_hidden_global_state(self):
                problems = S.global_state_problems(self.tree)
                self.assertFalse(problems, S.format_problems(problems))

            def test_no_hard_wired_collaborators(self):
                bad = []
                for q, fn in S.functions(self.tree):
                    if not q.startswith(CLASS + "."):
                        continue
                    for call in S.dotted_calls(fn):
                        if call in FORBIDDEN or (call.split(".")[-1] == "print" and "print" in FORBIDDEN and call == "print"):
                            bad.append("%s calls %s directly" % (q, call))
                self.assertFalse(bad, S.format_problems(bad))
        ''')
        hidden = {"tests/test_more_behaviour.py": beh, "tests/test_zz_structure.py": struct, **py_structlib()}
        prove(dom["key"], start, hidden, solution, _kit.PY_BEHAVIOUR_CMD, _kit.PY_STRUCT_CMD, "python3 -m unittest discover -s tests", behaviour_on_start=False)
        api = dom["api"]
        prompt = rng.choice(PROMPTS).format(pkg=pkg, mod=mod, topic=dom["topic"], ctor=dom["ctor"], methods=dom["methods"], api=api,
                                            api_cap=api[0].upper() + api[1:], forbidden=_fmt(forbidden))
        d = 3 if dom["key"] in ("alerts", "parking") else 4
        yield Task(slug=f"{i + 1:02d}-{dom['key']}", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution,
                   verify="python3 -m unittest discover -s tests -v", tags=["dependency-injection", "global-state", "testability"],
                   notes={"domain": dom["key"]})
