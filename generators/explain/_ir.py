"""A small language-neutral program model used to generate the repositories of the explain families.

A ``Project`` is a set of modules holding functions whose bodies are written in a tiny integer IR (literals, parameters,
module constants, arithmetic, calls, branches, loops, printing, and optionally raise/try). The IR can be *interpreted* here
(ground truth for "what does it print", coverage, call stacks) and *rendered* into python, javascript, go, java, rust and
ruby by ``_render``. Because the program is generated from the model, every structural fact (who calls whom, who imports
whom, what is public) is known by construction.

Values are non-negative integers far below 2**48 (the interpreter asserts it), so every language computes identical results:
``//`` and ``%`` only see non-negative operands, subtraction is the saturating ``sub`` (``max(a - b, 0)``), and nothing overflows a 64-bit integer or a JavaScript double.

Expressions:  ("n", v) ("v", name) ("k", CONST) ("op", o, a, b) ("call", fid, [args])      o in + * // % min max sub
Conditions:   ("cmp", o, a, b)  ("and", c1, c2)  ("or", c1, c2)                              o in < <= > >= == !=
Statements:   ("let", var, e) ("set", var, e) ("if", cond, then, else) ("for", var, lo, hi, body) ("emit", tpl, [e..])
              ("ret", e) ("raise", exc, tpl, [e..]) ("try", body, [(exc, handler)], final) ("do", call_expr)
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

LIM = 10007
PBOUND = 20000     # nominal bound tag carried by generated values (the interpreter itself asserts every value stays below BIG)
BIG = 2**48

LANGS6 = ["python", "javascript", "go", "java", "rust", "ruby"]
EXC_LANGS = {"python", "javascript", "java", "ruby"}


# ------------------------------------------------------------------------------------------------------------ IR helpers
def N(v):
    return ("n", v)


def V(x):
    return ("v", x)


def K(x):
    return ("k", x)


def Op(o, a, b):
    return ("op", o, a, b)


def Call(fid, *args):
    return ("call", fid, list(args))


def Cmp(o, a, b):
    return ("cmp", o, a, b)


class Raised(Exception):
    def __init__(self, exc, msg):
        super().__init__(f"{exc}: {msg}")
        self.exc, self.msg = exc, msg


@dataclass
class Fn:
    fid: str
    mod: str
    name: str            # snake_case, e.g. "berth_fee"
    params: list
    body: list
    public: bool = True
    doc: str = ""
    kind: str = "fn"     # fn | main (boilerplate that parses argv and calls run)
    ret_bound: int = LIM


@dataclass
class Mod:
    key: str             # "core.berths" or "berths"
    pkg: str             # "core" or ""
    base: str            # "berths"
    layer: str           # util | core | svc | cli | errors
    rank: int
    consts: list = field(default_factory=list)   # [(NAME, value)]
    fids: list = field(default_factory=list)
    decoys: list = field(default_factory=list)   # module keys imported but never used
    all_list: bool = False                       # python: defines __all__ (listing a subset of the public names)
    lazy: list = field(default_factory=list)     # module keys imported inside a function body instead of at the top (cycle breakers)
    all_names: list = field(default_factory=list)  # python: function ids listed in __all__
    doc: str = ""


@dataclass
class Case:
    name: str
    fid: str
    args: list
    expect: str           # "ok" | "raises"
    value: int = 0
    lines: list = field(default_factory=list)
    exc: str = ""


@dataclass
class Project:
    lang: str
    name: str
    title: str
    tag: str
    blurb: str
    mods: dict
    fns: dict
    excs: list            # [(name, base)] base is "" for the root
    cases: list
    tier: int
    layered: bool
    run_fid: str = "cli.run"
    main_fid: str = "cli.main"
    unit: str = "units"
    seed_info: dict = field(default_factory=dict)

    # ---------------------------------------------------------------- static structure
    def mod_of(self, fid: str) -> Mod:
        return self.mods[self.fns[fid].mod]

    def order(self) -> list:
        """function ids in definition order (module rank, then position)"""
        out = []
        for m in sorted(self.mods.values(), key=lambda m: m.rank):
            out.extend(m.fids)
        return out

    def exprs_of(self, body):
        """yield every expression node in a statement list (pre-order)"""
        for st in body:
            t = st[0]
            if t in ("let", "set"):
                yield from _walk(st[2])
            elif t == "ret" or t == "do":
                yield from _walk(st[1])
            elif t == "emit":
                for e in st[2]:
                    yield from _walk(e)
            elif t == "raise":
                for e in st[3]:
                    yield from _walk(e)
            elif t == "if":
                yield from _walk_cond(st[1])
                yield from self.exprs_of(st[2])
                yield from self.exprs_of(st[3])
            elif t == "for":
                yield from _walk(st[2])
                yield from _walk(st[3])
                yield from self.exprs_of(st[4])
            elif t == "try":
                yield from self.exprs_of(st[1])
                for _, h in st[2]:
                    yield from self.exprs_of(h)
                yield from self.exprs_of(st[3])

    def calls_in(self, fid: str) -> list:
        """callee fids in textual order (with repeats)"""
        f = self.fns[fid]
        if f.kind == "main":
            return [self.run_fid]
        return [e[1] for e in self.exprs_of(f.body) if e[0] == "call"]

    def callees(self, fid: str) -> list:
        out = []
        for c in self.calls_in(fid):
            if c not in out:
                out.append(c)
        return out

    def callers_map(self) -> dict:
        m = {fid: [] for fid in self.fns}
        for fid in self.fns:
            for c in self.callees(fid):
                m[c].append(fid)
        return m

    def reach(self, fid: str, forward: bool = True) -> list:
        """transitive callees (forward) or callers, excluding fid itself, sorted"""
        edges = {f: self.callees(f) for f in self.fns} if forward else self.callers_map()
        seen, stack = set(), [fid]
        while stack:
            x = stack.pop()
            for y in edges[x]:
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        seen.discard(fid)
        return sorted(seen)

    def uses_exc(self, fid: str) -> set:
        f = self.fns[fid]
        out = set()
        for st in _stmts(f.body):
            if st[0] == "raise":
                out.add(st[1])
            if st[0] == "try":
                for e, _ in st[2]:
                    out.add(e)
        return out

    def exc_mod(self) -> str:
        return "errors" if "errors" in self.mods else ("util.errors" if "util.errors" in self.mods else "")

    def used_imports(self, mkey: str) -> dict:
        """module key -> list of symbols (function ids or exception names) this module uses from that module"""
        m = self.mods[mkey]
        out: dict = {}
        for fid in m.fids:
            for c in self.callees(fid):
                cm = self.fns[c].mod
                if cm != mkey:
                    out.setdefault(cm, [])
                    if c not in out[cm]:
                        out[cm].append(c)
            for e in sorted(self.uses_exc(fid)):
                out.setdefault(self.exc_mod(), [])
                if e not in out[self.exc_mod()]:
                    out[self.exc_mod()].append(e)
        return out

    def import_edges(self) -> dict:
        """module key -> sorted list of module keys it imports (used or not)"""
        out = {}
        for k, m in self.mods.items():
            s = set(self.used_imports(k)) | set(m.decoys)
            out[k] = sorted(s)
        return out

    def exports(self, mkey: str) -> list:
        """public function ids of a module that are part of its public surface"""
        m = self.mods[mkey]
        return [f for f in m.fids if self.fns[f].public and self.fns[f].kind == "fn"]

    # ---------------------------------------------------------------- interpretation
    def run(self, fid: str, args: list, trace: "Trace | None" = None, over: dict | None = None, cover: dict | None = None):
        """execute fid; returns the value; trace (if given) collects output, coverage and call stacks.
        ``over`` replaces function bodies (fid -> body), ``cover`` replaces module constants ((module, NAME) -> value)"""
        tr = trace if trace is not None else Trace()
        return _Interp(self, tr, over or {}, cover or {}).call(fid, list(args))

    def case_passes(self, c: "Case", over: dict | None = None, cover: dict | None = None) -> bool:
        """would the generated test for this case still pass with the given changes?"""
        tr = Trace()
        try:
            v = self.run(c.fid, c.args, tr, over, cover)
        except Raised as r:
            return c.expect == "raises" and self.exc_is(r.exc, c.exc)
        if c.expect == "raises":
            return False
        if v != c.value:
            return False
        if c.lines and tr.out != c.lines:
            return False
        return True

    def exc_is(self, exc: str, base: str) -> bool:
        parent = dict(self.excs)
        while exc:
            if exc == base:
                return True
            exc = parent.get(exc, "")
        return False

    def escapes(self, fid: str, memo: dict | None = None) -> set:
        """exception classes that can propagate out of ``fid`` if every branch may be taken (hierarchy-aware catch clauses)"""
        memo = memo if memo is not None else {}
        if fid in memo:
            return memo[fid]
        memo[fid] = set()
        f = self.fns[fid]
        if f.kind == "main":
            memo[fid] = self.escapes(self.run_fid, memo)
            return memo[fid]

        def block(body) -> set:
            out: set = set()
            for st in body:
                t = st[0]
                if t == "raise":
                    out.add(st[1])
                for e in _stmt_exprs(st):
                    for x in _walk(e):
                        if x[0] == "call":
                            out |= self.escapes(x[1], memo)
                if t == "if":
                    out |= block(st[2]) | block(st[3])
                elif t == "for":
                    out |= block(st[4])
                elif t == "try":
                    inner = block(st[1])
                    caught = {e for e in inner if any(self.exc_is(e, h) for h, _ in st[2])}
                    out |= inner - caught
                    for _, h in st[2]:
                        out |= block(h)
                    out |= block(st[3])
            return out

        res = block(f.body)
        memo[fid] = res
        return res

    def raisers(self) -> dict:
        """exception class -> function ids that contain a raise of it"""
        out: dict = {}
        for fid, f in self.fns.items():
            for st in _stmts(f.body):
                if st[0] == "raise":
                    out.setdefault(st[1], []).append(fid)
        return out

    def case_name_set(self) -> set:
        return {c.name for c in self.cases}


@dataclass
class Trace:
    out: list = field(default_factory=list)          # emitted lines
    emit_stacks: list = field(default_factory=list)  # stack (fids, outermost first) at every emit
    executed: list = field(default_factory=list)     # fids in first-execution order
    calls: list = field(default_factory=list)        # (caller, callee) runtime edges in order
    raised_in: str = ""                              # function whose raise statement fired last
    steps: int = 0


def _stmt_exprs(st):
    t = st[0]
    if t in ("let", "set"):
        return [st[2]]
    if t in ("ret", "do"):
        return [st[1]]
    if t == "emit":
        return list(st[2])
    if t == "raise":
        return list(st[3])
    if t == "if":
        return _cond_exprs(st[1])
    if t == "for":
        return [st[2], st[3]]
    return []


def _cond_exprs(c):
    if c[0] == "cmp":
        return [c[2], c[3]]
    return _cond_exprs(c[1]) + _cond_exprs(c[2])


def _walk(e):
    yield e
    if e[0] == "op":
        yield from _walk(e[2])
        yield from _walk(e[3])
    elif e[0] == "call":
        for a in e[2]:
            yield from _walk(a)


def _walk_cond(c):
    if c[0] == "cmp":
        yield from _walk(c[2])
        yield from _walk(c[3])
    else:
        yield from _walk_cond(c[1])
        yield from _walk_cond(c[2])


def _stmts(body):
    for st in body:
        yield st
        if st[0] == "if":
            yield from _stmts(st[2])
            yield from _stmts(st[3])
        elif st[0] == "for":
            yield from _stmts(st[4])
        elif st[0] == "try":
            yield from _stmts(st[1])
            for _, h in st[2]:
                yield from _stmts(h)
            yield from _stmts(st[3])


class _Return(Exception):
    def __init__(self, v):
        self.v = v


class _Interp:
    def __init__(self, proj, trace, over, cover=None):
        self.p, self.t, self.over = proj, trace, over
        self.cover = cover or {}
        self.stack: list = []

    def call(self, fid, args):
        f = self.p.fns[fid]
        if self.stack:
            self.t.calls.append((self.stack[-1], fid))
        if fid not in self.t.executed:
            self.t.executed.append(fid)
        env = dict(zip(f.params, args))
        consts = dict(self.p.mods[f.mod].consts)
        for (mk, nm), val in self.cover.items():
            if mk == f.mod and nm in consts:
                consts[nm] = val
        self.stack.append(fid)
        if len(self.stack) > 60:
            raise RuntimeError("call depth")
        try:
            if f.kind == "main":
                r = self.call(self.p.run_fid, args)
                self.t.out.append(str(r))
                return r
            body = self.over.get(fid, f.body)
            try:
                self.block(body, env, consts)
            except _Return as r:
                return r.v
            raise RuntimeError(f"{fid} fell off the end")
        finally:
            self.stack.pop()

    def ev(self, e, env, consts):
        t = e[0]
        if t == "n":
            return e[1]
        if t == "v":
            return env[e[1]]
        if t == "k":
            return consts[e[1]]
        if t == "op":
            a, b = self.ev(e[2], env, consts), self.ev(e[3], env, consts)
            o = e[1]
            self.t.steps += 1
            if o == "+":
                r = a + b
            elif o == "*":
                r = a * b
            elif o == "sub":
                r = max(a - b, 0)
            elif o == "min":
                r = min(a, b)
            elif o == "max":
                r = max(a, b)
            elif o == "//":
                assert b > 0 and a >= 0
                r = a // b
            elif o == "%":
                assert b > 0 and a >= 0
                r = a % b
            else:
                raise ValueError(o)
            assert 0 <= r < BIG, (o, a, b)
            return r
        if t == "call":
            return self.call(e[1], [self.ev(a, env, consts) for a in e[2]])
        raise ValueError(t)

    def cond(self, c, env, consts):
        t = c[0]
        if t == "cmp":
            a, b = self.ev(c[2], env, consts), self.ev(c[3], env, consts)
            return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b, "==": a == b, "!=": a != b}[c[1]]
        if t == "and":
            return self.cond(c[1], env, consts) and self.cond(c[2], env, consts)
        return self.cond(c[1], env, consts) or self.cond(c[2], env, consts)

    def block(self, body, env, consts):
        for st in body:
            t = st[0]
            if t in ("let", "set"):
                env[st[1]] = self.ev(st[2], env, consts)
            elif t == "do":
                self.ev(st[1], env, consts)
            elif t == "if":
                self.block(st[2] if self.cond(st[1], env, consts) else st[3], env, consts)
            elif t == "for":
                lo, hi = self.ev(st[2], env, consts), self.ev(st[3], env, consts)
                for i in range(lo, hi):
                    env[st[1]] = i
                    self.block(st[4], env, consts)
                env.pop(st[1], None)
            elif t == "emit":
                vals = [self.ev(e, env, consts) for e in st[2]]
                self.t.out.append(fmt_tpl(st[1], vals))
                self.t.emit_stacks.append(list(self.stack))
            elif t == "ret":
                raise _Return(self.ev(st[1], env, consts))
            elif t == "raise":
                vals = [self.ev(e, env, consts) for e in st[3]]
                self.t.raised_in = self.stack[-1]
                raise Raised(st[1], fmt_tpl(st[2], vals))
            elif t == "try":
                try:
                    try:
                        self.block(st[1], env, consts)
                    except Raised as r:
                        for exc, handler in st[2]:
                            if self.p.exc_is(r.exc, exc):
                                self.block(handler, env, consts)
                                break
                        else:
                            raise
                finally:
                    self.block(st[3], env, consts)
            else:
                raise ValueError(t)


def fmt_tpl(tpl: str, vals: list) -> str:
    parts = tpl.split("{}")
    assert len(parts) == len(vals) + 1, (tpl, vals)
    out = parts[0]
    for v, p in zip(vals, parts[1:]):
        out += str(v) + p
    return out


# ------------------------------------------------------------------------------------------------------------ domains
@dataclass
class Domain:
    key: str
    name: str
    title: str
    tag: str
    blurb: str
    nouns: list
    unit: str


def _d(key, name, title, tag, blurb, nouns, unit):
    return Domain(key, name, title, tag, blurb, nouns.split(), unit)


DOMAINS = [
    _d("harbor", "harbormaster", "Harbormaster", "HBR", "prices berth stays, plans dock use and prints the daily harbour report",
       "berth tide hull mooring fuel crew pilot cargo manifest quay wharf dues slip anchor buoy draft keel lock gangway tender dockage", "metres"),
    _d("seeds", "seedshelf", "Seedshelf", "SDS", "tracks packets in a community seed library: lending, germination checks and the yearly stocktake",
       "seed packet tray label batch germ plot bed sprout cutting bulb tuber loan donor catalogue jar shelf bin tag sowing", "packets"),
    _d("kiln", "kilnbook", "Kilnbook", "KLN", "schedules kiln firings for a pottery co-op and works out shelf loads and energy shares",
       "kiln firing glaze clay shelf cone ramp soak bisque pot batch cooling vent damper element cycle load slab", "kilns"),
    _d("apiary", "hivelog", "Hivelog", "HVL", "keeps beehive inspection records and estimates honey yield per apiary",
       "hive frame super queen colony brood honey nectar swarm comb varroa feeder apiary inspection yield smoker", "frames"),
    _d("beacon", "beaconkeep", "Beaconkeep", "BCN", "computes watch rosters, lamp oil use and fog-horn schedules for a chain of lighthouses",
       "lamp lens beacon watch shift oil wick fog horn tower keeper beam sector range flash gale", "hours"),
    _d("huts", "hutline", "Hutline", "HUT", "handles bookings, meals and wood stocks for a network of mountain huts",
       "hut bunk meal night guest warden trail stove wood ridge pass stamp pack group blanket season", "nights"),
    _d("tram", "tramyard", "Tramyard", "TRM", "plans depot bays, driver shifts and fare zones for a small tram operator",
       "tram depot bay track shift driver fare stop route line pantograph siding wash roster service coupling", "stops"),
    _d("cheese", "cavelog", "Cavelog", "CVL", "records wheels ageing in a cheese cave and computes turning schedules and rind losses",
       "wheel rind brine cave rack batch curd turn cut humidity aging crate label mold press", "wheels"),
    _d("observatory", "starbook", "Starbook", "STB", "plans telescope sessions and exposure budgets for a university observatory",
       "scope dome slot target exposure filter frame seeing flat dark mount session plate field magnitude", "frames"),
    _d("glass", "glasswright", "Glasswright", "GLS", "costs glassworks melts, furnace schedules and annealing runs",
       "melt gather blow annealer batch cullet mould piece lehr furnace crucible gob rod pontil lot", "pieces"),
    _d("bells", "bellcast", "Bellcast", "BLC", "models bell pours: metal mixes, mould sizes, tuning checks and delivery slots",
       "bell mould pour tin copper tuning tone strike yoke clapper pit crown lathe", "kilos"),
    _d("orchard", "orchardly", "Orchardly", "ORC", "grades fruit crates, plans picking rounds and prices cider pressings",
       "tree row crate grade apple pick press cider bin yield blossom frost graft ladder sorter", "crates"),
    _d("post", "sortline", "Sortline", "SRT", "routes parcels through a regional sorting depot and prints the van manifests",
       "parcel bag route chute scan label belt depot van stamp postcode manifest tray", "parcels"),
    _d("mill", "millrace", "Millrace", "MLR", "predicts grain throughput for a tide mill from pond levels and gate openings",
       "mill wheel gate sluice grain sack stone flour pond tide hopper cog shaft", "sacks"),
    _d("theatre", "stringsmith", "Stringsmith", "STR", "books performances, seats and rigging for a travelling puppet theatre",
       "puppet stage act cue curtain seat show ticket rehearsal prop rig scene lamp", "seats"),
    _d("rope", "ropewalk", "Ropewalk", "RPW", "estimates fibre needs, twist counts and pricing for a traditional ropewalk",
       "strand fibre lay twist rope hank bobbin reel walk tar mark fathom coil", "fathoms"),
    _d("bikes", "cyclecoop", "Cyclecoop", "CYC", "balances bikes between docks of a cooperative bike-share and settles deposits",
       "bike dock rack lock ride deposit station rebalance tyre pump trip rider bell", "bikes"),
    _d("clock", "tickwright", "Tickwright", "TKW", "schedules winding rounds and servicing for a collection of tower clocks",
       "dial weight escapement chime bell hour swing pendulum winding gear spring service", "hours"),
]

UTIL_MODS = ["rounding", "spans", "units", "calendar", "counts", "scales", "bands", "steps", "ranges", "buckets", "limits", "ratios"]
SVC_MODS = ["booking", "billing", "planning", "reports", "audit", "intake", "dispatch", "ledger", "forecast", "scheduling", "settlement", "quotes", "review"]
UTIL_VERBS = ["clamp", "scale", "bucket", "round", "pad", "smooth", "fold", "spread", "cap", "tier", "snap", "trim", "wrap", "blend", "shave"]
CORE_SUFFIX = ["rate", "fee", "limit", "factor", "bonus", "penalty", "quota", "levy", "share", "weight", "score", "margin", "offset", "ceiling", "floor", "step"]
SVC_VERBS = ["plan", "settle", "quote", "audit", "assemble", "reconcile", "schedule", "summarise", "rank", "dispatch", "compile", "tally", "price", "stage", "check"]
CONST_STEMS = ["BASE", "STEP", "CAP", "FLOOR", "BLOCK", "SPAN", "TIER", "UNIT", "LIMIT", "SLOPE", "SHIFT", "BAND", "RATIO", "LEVY"]
PARAMS = ["length", "nights", "tons", "crew", "draft", "hours", "units", "count", "width", "level", "size", "load", "span", "lots",
          "batch", "days", "weight", "score", "rank", "depth", "height", "stock", "queue", "slots", "pairs", "turns", "rounds"]
VARS = ["base", "extra", "total", "part", "rate", "step", "margin", "gap", "share", "tier", "tally", "carry", "bonus", "shift",
        "delta", "cost", "surplus", "slack", "offset", "adj", "fee", "mix", "left", "right", "core", "rest", "load2"]
VARS = [v for v in VARS if v not in ("load2",)]

SUFFIX_DOC = {
    "rate": "Per-unit rate for a {n}", "fee": "Fee owed for a {n}", "limit": "Upper limit on a {n}", "factor": "Scaling factor applied to a {n}",
    "bonus": "Bonus granted for a {n}", "penalty": "Penalty charged against a {n}", "quota": "Quota allowed for a {n}",
    "levy": "Levy raised on a {n}", "share": "Share assigned to a {n}", "weight": "Weight given to a {n}", "score": "Score of a {n}",
    "margin": "Safety margin around a {n}", "offset": "Offset applied to a {n}", "ceiling": "Ceiling for a {n}", "floor": "Floor for a {n}",
    "step": "Step size for a {n}",
}
VERB_DOC = {
    "clamp": "Clamp the {n} value into its allowed range", "scale": "Scale a {n} value by the standard ratio", "bucket": "Put a {n} value into its band",
    "round": "Round a {n} value to the nearest block", "pad": "Pad a {n} value with the fixed allowance", "smooth": "Smooth a {n} value against the running level",
    "fold": "Fold a {n} value back into range", "spread": "Spread a {n} value over the standard span", "cap": "Cap a {n} value at the ceiling",
    "tier": "Price a {n} value by tier", "snap": "Snap a {n} value to the grid", "trim": "Trim a {n} value by the standard margin",
    "wrap": "Wrap a {n} value around the cycle", "blend": "Blend a {n} value with the reference level", "shave": "Shave the excess off a {n} value",
    "plan": "Plan the {n} step", "settle": "Settle the {n} account", "quote": "Quote a price for the {n}", "audit": "Audit the {n} figures",
    "assemble": "Assemble the {n} summary", "reconcile": "Reconcile the {n} totals", "schedule": "Schedule the {n} work", "summarise": "Summarise the {n} figures",
    "rank": "Rank the {n} candidates", "dispatch": "Dispatch the {n} request", "compile": "Compile the {n} sheet", "tally": "Tally the {n} counts",
    "price": "Price the {n} request", "stage": "Stage the {n} batch", "check": "Check the {n} totals",
}


def plural(w: str) -> str:
    if w.endswith("y") and w[-2:-1] not in "aeiou":
        return w[:-1] + "ies"
    if w.endswith(("s", "x", "ch", "sh")):
        return w + "es" if not w.endswith("s") else w + "es"
    return w + "s"


@dataclass
class Spec:
    lang: str
    tier: int = 2
    exc: bool = False
    dead: int = 0                 # functions intentionally unreachable from main
    dup: int = 0                  # helper names defined in two modules
    cycle: bool = False           # add a module import cycle (not for go)
    decoys: bool = True
    tests: bool = True
    domain: int = -1
    layered: bool | None = None
    emit_deep: bool = False       # allow emits below the service layer
    big: bool = False             # tier 5 only: use the largest size plan


TIER_PLAN = {
    1: dict(util=1, core=1, svc=1, per=(3, 4), cli=(3, 3)),
    2: dict(util=2, core=2, svc=2, per=(3, 4), cli=(3, 4)),
    3: dict(util=3, core=3, svc=3, per=(3, 5), cli=(4, 5)),
    4: dict(util=4, core=5, svc=4, per=(4, 6), cli=(5, 7)),
    5: dict(util=5, core=7, svc=6, per=(4, 7), cli=(6, 9)),
    6: dict(util=6, core=10, svc=8, per=(4, 7), cli=(8, 11)),   # "big": only for tier-5 questions that deserve a really large repository
}


class Builder:
    def __init__(self, rng: random.Random, spec: Spec):
        self.rng, self.spec = rng, spec
        self.fns: dict = {}
        self.mods: dict = {}
        self.names: set = set()
        self.callers: dict = {}
        self.counter = 0
        self.dead_pos: set = set()
        self.dup_left = spec.dup
        self.dead_set = set()

    # ---- naming
    def fresh_name(self, make, tries=60):
        for _ in range(tries):
            n = make()
            if n not in self.names:
                self.names.add(n)
                return n
        raise RuntimeError("could not find a fresh name")

    def build(self) -> Project:
        rng, spec = self.rng, self.spec
        plan = TIER_PLAN[6 if (spec.big and spec.tier >= 5) else spec.tier]
        dom = DOMAINS[spec.domain % len(DOMAINS)] if spec.domain >= 0 else rng.choice(DOMAINS)
        layered = spec.layered if spec.layered is not None else spec.tier >= 3
        nouns = list(dom.nouns)
        rng.shuffle(nouns)
        util_names = rng.sample(UTIL_MODS, plan["util"])
        core_cands = [plural(n) for n in nouns]
        core_names = core_cands[: plan["core"]]
        svc_names = rng.sample(SVC_MODS, plan["svc"])
        taken = set(util_names + core_names + svc_names)
        assert len(taken) == len(util_names) + len(core_names) + len(svc_names)
        rank = 0
        mods = []
        if spec.exc:
            mods.append(("errors", "util" if layered else "", "errors", "errors"))
        for layer, names in (("util", util_names), ("core", core_names), ("svc", svc_names)):
            for nm in names:
                pkg = ({"util": "util", "core": "core", "svc": "services"}[layer]) if layered else ""
                mods.append((f"{pkg}.{nm}" if pkg else nm, pkg, nm, layer))
        mods.append(("cli", "", "cli", "cli"))
        for key, pkg, base, layer in mods:
            m = Mod(key=key, pkg=pkg, base=base, layer=layer, rank=rank)
            if layer == "errors":
                m.key = f"{pkg}.errors" if pkg else "errors"
            rank += 1
            self.mods[m.key] = m
        # constants
        for m in self.mods.values():
            if m.layer in ("errors", "cli"):
                continue
            stems = rng.sample(CONST_STEMS, rng.randint(2, 3))
            noun = rng.choice(nouns).upper()
            for s in stems:
                nm = f"{noun}_{s}" if rng.random() < 0.5 else s
                if any(nm == c for c, _ in m.consts):
                    continue
                m.consts.append((nm, rng.choice([2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 16, 20, 24, 25, 30, 32, 40, 50, 60, 64, 75, 90, 100, 120, 150, 200, 250, 365])))
        # exceptions
        excs = []
        if spec.exc:
            root = f"{dom.title}Error"
            excs.append((root, ""))
            for stem in rng.sample(["Limit", "Quota", "Window", "Shortage", "Closed", "Invalid", "Overload", "Capacity", "Stale"], rng.randint(2, 4)):
                excs.append((f"{stem}Error", root))
            if len(excs) >= 4 and rng.random() < 0.6:
                excs.append((f"Hard{excs[1][0]}", excs[1][0]))
        self.excs = excs
        # functions, layer by layer
        counts = {}
        for layer in ("util", "core", "svc"):
            for m in [m for m in self.mods.values() if m.layer == layer]:
                lo, hi = plan["per"]
                counts[m.key] = rng.randint(lo, hi)
        total = sum(counts.values())
        if spec.dead:
            self.dead_pos = set(rng.sample(range(3, total), min(spec.dead, total - 3)))
        for layer in ("util", "core", "svc"):
            for m in [m for m in self.mods.values() if m.layer == layer]:
                for _ in range(counts[m.key]):
                    self.add_function(m, dom, nouns, layer)
        cli = self.mods["cli"]
        self.add_cli(cli, dom)
        self.connect_orphans()
        for m in self.mods.values():
            usedk = set()
            for fid in m.fids:
                for st in _stmts(self.fns[fid].body):
                    for e in _stmt_exprs(st):
                        for x in _walk(e):
                            if x[0] == "k":
                                usedk.add(x[1])
            m.consts = [(k, v) for k, v in m.consts if k in usedk]
        proj = Project(lang=spec.lang, name=dom.name, title=dom.title, tag=dom.tag, blurb=dom.blurb, mods=self.mods, fns=self.fns,
                       excs=excs, cases=[], tier=spec.tier, layered=layered, unit=dom.unit)
        if spec.cycle:
            self.add_cycle(proj)
        proj.seed_info["dead"] = sorted(self.dead_set)
        if spec.decoys:
            self.add_decoys(proj)
        for m in self.mods.values():
            m.all_list = spec.lang == "python" and m.layer in ("core", "util", "svc") and rng.random() < 0.35
            if m.all_list:
                ex = [f for f in m.fids if proj.fns[f].public and proj.fns[f].kind == "fn"]
                if len(ex) < 2:
                    m.all_list = False
                else:
                    drop = rng.sample(ex, rng.randint(1, max(1, len(ex) // 3)))
                    m.all_names = [f for f in ex if f not in drop]
        for m in self.mods.values():
            m.doc = f"{m.base.capitalize()} helpers for {dom.title}."
        if spec.tests:
            make_cases(rng, proj, spec.lang)
        return proj

    # ---- functions
    def add_function(self, m: Mod, dom: Domain, nouns: list, layer: str):
        rng = self.rng
        if layer == "util":
            verb, noun = rng.choice(UTIL_VERBS), rng.choice(nouns + [dom.unit.rstrip("s")])
            name = self.fresh_name(lambda: f"{rng.choice(UTIL_VERBS)}_{rng.choice(nouns)}")
            verb = name.split("_")[0]
            noun = name.split("_", 1)[1]
            doc = VERB_DOC[verb].format(n=noun)
        elif layer == "core":
            name = self.fresh_name(lambda: f"{rng.choice(nouns)}_{rng.choice(CORE_SUFFIX)}")
            noun, suf = name.split("_", 1)
            doc = SUFFIX_DOC[suf].format(n=noun)
        else:
            name = self.fresh_name(lambda: f"{rng.choice(SVC_VERBS)}_{rng.choice(nouns)}")
            verb, noun = name.split("_", 1)
            doc = VERB_DOC[verb].format(n=noun)
        if self.dup_left and layer in ("util", "core") and rng.random() < 0.6:
            twins = [f for f in self.fns.values() if self.mods[f.mod].layer == layer and f.mod != m.key and f.kind == "fn"
                     and f.public and not any(g.name == f.name and g.mod == m.key for g in self.fns.values())
                     and sum(1 for g in self.fns.values() if g.name == f.name) == 1]
            if twins:
                t = rng.choice(twins)
                name, doc = t.name, t.doc
                self.dup_left -= 1
        fid = f"{m.key}.{name}"
        nparams = rng.choice([1, 1, 2, 2, 2, 3])
        params = rng.sample(PARAMS, nparams)
        public = rng.random() < 0.8 or layer == "svc"
        if self.dup_left is not None and name in {f.name for f in self.fns.values()}:
            public = True
        fn = Fn(fid=fid, mod=m.key, name=name, params=params, body=[], public=public, doc=doc + ".")
        self.fns[fid] = fn
        self.counter += 1
        if self.counter in self.dead_pos:
            self.dead_set.add(fid)
        m.fids.append(fid)
        self.fill(fn, m, layer, dom)
        return fn

    def candidates(self, fn: Fn, layer: str) -> list:
        """functions this one may call: strictly earlier in definition order, lower-or-equal layer"""
        order_ok = []
        m = self.mods[fn.mod]
        for fid, f in self.fns.items():
            if fid == fn.fid:
                break
            fm = self.mods[f.mod]
            if fm.layer == "errors":
                continue
            if layer == "util" and fm.layer != "util":
                continue
            if layer == "core" and fm.layer not in ("util", "core"):
                continue
            if f.kind != "fn":
                continue
            if f.mod != fn.mod and not f.public:
                continue
            order_ok.append(fid)
        return [c for c in order_ok if c not in self.dead_set or fn.fid in self.dead_set]

    def pick_callees(self, fn: Fn, layer: str, k: int) -> list:
        cands = self.candidates(fn, layer)
        rng = self.rng
        out = []
        for _ in range(k):
            pool = [c for c in cands if c not in out]
            if not pool:
                break
            w = []
            fm = self.mods[fn.mod]
            for c in pool:
                f = self.fns[c]
                base = 4 if not self.callers.get(c) else 1
                cm = self.mods[f.mod]
                # prefer the next layer down over util everywhere
                if layer == "svc" and cm.layer == "core":
                    base *= 3
                if layer == "core" and cm.layer == "util":
                    base *= 2
                if f.mod == fn.mod:
                    base *= 1.5
                w.append(base)
            c = rng.choices(pool, w)[0]
            out.append(c)
            self.callers.setdefault(c, []).append(fn.fid)
        return out

    def arg_expr(self, vals: list, consts: dict, rng):
        e, b = rng.choice(vals)
        r = rng.random()
        if r < 0.5:
            return e
        if r < 0.7:
            return Op("+", e, N(rng.randint(1, 9)))
        if r < 0.85:
            return Op("*", e, N(rng.randint(2, 4)))
        return Op("sub", e, N(rng.randint(1, 5)))

    def finish(self, e, consts, rng, vb=None):
        """keep a return expression compact with % or min"""
        r = rng.random()
        if r < 0.6:
            return Op("%", e, N(rng.choice([97, 251, 509, 1009, 4001, 9973])))
        if r < 0.85:
            return Op("min", e, N(rng.choice([480, 999, 2500, 4800, 9000])))
        return e

    def fill(self, fn: Fn, m: Mod, layer: str, dom: Domain):
        rng = self.rng
        consts = dict(m.consts)
        kn = [c for c, _ in m.consts]
        ps = fn.params
        vals = [(V(p), PBOUND) for p in ps]
        vname = lambda used: rng.choice([v for v in VARS if v not in used])  # noqa: E731
        used = set(ps)
        body: list = []

        def newvar():
            v = vname(used)
            used.add(v)
            return v

        def kexpr():
            return K(rng.choice(kn)) if kn and rng.random() < 0.7 else N(rng.randint(2, 12))

        shape_pool = {
            "util": ["tier", "clamp", "pipeline", "tier", "clamp"],
            "core": ["pipeline", "branch", "loop", "guard", "early", "nested", "tier", "pipeline", "branch"],
            "svc": ["pipeline", "branch", "loop", "report", "nested", "report", "early", "guard"],
        }[layer]
        if self.spec.exc and layer == "core" and rng.random() < 0.35:
            shape = "check"
        elif self.spec.exc and layer == "svc" and rng.random() < 0.35:
            shape = "guarded"
        else:
            shape = rng.choice(shape_pool)
        need = {"tier": 0, "clamp": 0, "pipeline": rng.randint(1, 3 if layer != "util" else 1), "branch": 2, "loop": 1, "guard": rng.randint(1, 2),
                "early": 1, "nested": 2, "report": rng.randint(2, 3), "check": rng.randint(1, 2), "guarded": 1}[shape]
        if layer == "util":
            need = min(need, 1)
        callees = self.pick_callees(fn, layer, need)
        # when a shape needs callees that do not exist, degrade to a leaf shape
        if len(callees) < need or (need > 0 and not callees):
            for c in callees:
                self.callers[c].remove(fn.fid)
            callees = []
            shape = rng.choice(["tier", "clamp"])
        p0 = ps[0]
        p1 = ps[1] if len(ps) > 1 else ps[0]

        def call_expr(c, extra=None):
            cf = self.fns[c]
            pool = list(vals) + (extra or [])
            args = [self.arg_expr(pool, consts, rng) for _ in cf.params]
            return Call(c, *args)

        def combine(parts: list):
            """sum of weighted parts, then fit"""
            e = None
            for i, (pe, _) in enumerate(parts):
                t = pe
                if rng.random() < 0.5:
                    t = Op("*", pe, kexpr() if rng.random() < 0.5 else N(rng.randint(2, 6)))
                e = t if e is None else Op("+", e, t)
            return e

        if shape == "tier":
            k1, k2, k3, k4 = rng.sample([3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40], 4)
            lo = min(k1, k3)
            hi = max(k1, k3) + 10
            body = [("if", Cmp("<=", V(p0), N(lo)), [("ret", Op("*", V(p0), N(k2)))], []),
                    ("if", Cmp("<=", V(p0), N(hi)), [("ret", Op("+", Op("*", N(lo), N(k2)), Op("*", Op("sub", V(p0), N(lo)), N(k4))))], []),
                    ("ret", Op("min", Op("+", Op("*", N(lo), N(k2)), Op("*", Op("sub", V(p0), N(lo)), N(k4 + 2))), K(kn[0]) if kn and consts[kn[0]] > 20 else N(rng.choice([480, 900, 2500]))))]
            if rng.random() < 0.4 and len(ps) > 1:
                body = [body[0], body[1], ("ret", Op("%", Op("+", Op("*", V(p0), N(k4 + 2)), V(p1)), N(rng.choice([997, 1009, 4001]))))]
        elif shape == "clamp":
            lo, hi = sorted(rng.sample([2, 5, 8, 10, 15, 20, 30, 50, 80, 100], 2))
            ex = Op("//", Op("*", V(p0), kexpr()), N(rng.choice([2, 3, 4, 5, 8, 10])))
            if len(ps) > 1 and rng.random() < 0.6:
                ex = Op("+", ex, V(p1))
            body = [("ret", Op("min", Op("max", ex, N(lo)), N(hi * rng.choice([1, 10, 20]))))]
        elif shape == "pipeline":
            lines = []
            for c in callees:
                v = newvar()
                lines.append(("let", v, call_expr(c)))
                vals.append((V(v), PBOUND))
            parts = [(V(p0), 0)] + [(x, 0) for x, _ in vals[len(ps):]]
            if rng.random() < 0.5 and len(ps) > 1:
                parts.append((V(p1), 0))
            if not callees:
                parts = [(V(p0), 0), (kexpr(), 0)]
            body = lines + [("ret", self.finish(combine(parts), consts, rng))]
        elif shape == "branch":
            v = newvar()
            c1, c2 = callees
            thr = rng.randint(3, 40)
            cond = Cmp(rng.choice(["<", ">", "<=", ">="]), V(p0), N(thr))
            if len(ps) > 1 and rng.random() < 0.3:
                cond = ("and", cond, Cmp(rng.choice([">", "!=", "<"]), V(p1), N(rng.randint(1, 20))))
            body = [("let", v, N(0)), ("if", cond, [("set", v, call_expr(c1))], [("set", v, call_expr(c2))]),
                    ("ret", self.finish(Op("+", V(v), Op("*", V(p0), kexpr())), consts, rng))]
        elif shape == "loop":
            v, i = newvar(), "i"
            c = callees[0]
            hi = Op("+", Op("%", V(p0), N(rng.choice([3, 4, 5]))), N(1))
            cf = self.fns[c]
            largs = [self.arg_expr(vals, consts, rng) for _ in cf.params]
            largs[0] = Op("+", V(i), largs[0]) if rng.random() < 0.5 else V(i)
            body = [("let", v, N(0)), ("for", i, N(0), hi, [("set", v, Op("+", V(v), Call(c, *largs)))]),
                    ("ret", self.finish(Op("+", V(v), kexpr()), consts, rng))]
        elif shape == "guard":
            lines = []
            for c in callees:
                v = newvar()
                lines.append(("let", v, call_expr(c)))
                vals.append((V(v), PBOUND))
            body = [("if", Cmp("==", V(p0), N(rng.choice([0, 1]))), [("ret", N(rng.randint(0, 9)))], [])] + lines + [
                ("ret", self.finish(combine([(x, 0) for x, _ in vals[len(ps):]] + [(V(p0), 0)]), consts, rng))]
        elif shape == "early":
            c = callees[0]
            thr = rng.randint(4, 50)
            body = [("if", Cmp(">", V(p0), N(thr)), [("ret", self.finish(Op("+", call_expr(c), N(rng.randint(1, 9))), consts, rng))], []),
                    ("ret", self.finish(Op("+", Op("*", V(p0), kexpr()), V(p1)), consts, rng))]
        elif shape == "nested":
            c1, c2 = callees
            inner = call_expr(c2)
            f1 = self.fns[c1]
            args = [inner] + [self.arg_expr(vals, consts, rng) for _ in f1.params[1:]]
            if not f1.params:
                args = []
            body = [("ret", self.finish(Op("+", Call(c1, *args), kexpr()), consts, rng))]
        elif shape == "report":
            lines = []
            vs = []
            for c in callees:
                v = newvar()
                lines.append(("let", v, call_expr(c)))
                vals.append((V(v), PBOUND))
                vs.append(v)
            tot = newvar()
            parts = [(V(v), 0) for v in vs] + [(V(p0), 0)]
            lines.append(("let", tot, self.finish(combine(parts), consts, rng)))
            tpl = f"{fn.name.replace('_', ' ')}: {p0}={{}} {vs[0] if len(vs) == 1 else vs[0]}={{}} total={{}}"
            lines.append(("emit", tpl, [V(p0), V(vs[0]), V(tot)]))
            body = lines + [("ret", V(tot))]
        elif shape == "check":
            c = callees[0]
            exc = rng.choice([e for e, b in self.excs if b])
            lim = rng.randint(300, 4000)
            v = newvar()
            body = [("if", Cmp(">", V(p0), N(lim)), [("raise", exc, f"{fn.name.replace('_', ' ')}: {p0} {{}} is over {lim}", [V(p0)])], []),
                    ("let", v, call_expr(c)),
                    ("ret", self.finish(Op("+", V(v), Op("*", V(p1), kexpr())), consts, rng))]
        elif shape == "guarded":
            c = callees[0]
            excs = [e for e, b in self.excs]
            exc = rng.choice(excs[1:] if len(excs) > 1 else excs)
            v = newvar()
            fallback = rng.randint(0, 40)
            handler = [("set", v, N(fallback))]
            if layer == "svc" and rng.random() < 0.5:
                handler.append(("emit", f"{fn.name.replace('_', ' ')}: fallback {{}}", [V(p0)]))
            fin = []
            body = [("let", v, N(0)), ("try", [("set", v, call_expr(c))], [(exc, handler)], fin),
                    ("ret", self.finish(Op("+", V(v), Op("*", V(p0), kexpr())), consts, rng))]
        fn.body = body
        fn.ret_bound = PBOUND
        self.use_all_params(fn)

    def use_all_params(self, fn: Fn):
        rng = self.rng
        seen = set()
        for st in _stmts(fn.body):
            for e in _stmt_exprs(st):
                for x in _walk(e):
                    if x[0] == "v":
                        seen.add(x[1])
        for p in fn.params:
            if p not in seen:
                for i in range(len(fn.body) - 1, -1, -1):
                    if fn.body[i][0] == "ret":
                        fn.body[i] = ("ret", Op("%", Op("+", fn.body[i][1], V(p)), N(rng.choice([997, 1009, 4001, 9973]))))
                        break

    def add_cli(self, m: Mod, dom: Domain):
        rng = self.rng
        plan = TIER_PLAN[self.spec.tier]
        run = Fn(fid="cli.run", mod="cli", name="run", params=["count", "days"], body=[], public=True,
                 doc=f"Run the {dom.title} report for a batch size and a number of days.")
        self.fns[run.fid] = run
        m.fids.append(run.fid)
        lo, hi = plan["cli"]
        k = rng.randint(lo, hi)
        cands = [fid for fid, f in self.fns.items() if self.mods[f.mod].layer in ("svc", "core") and f.public and f.kind == "fn" and fid not in self.dead_set]
        svc = [c for c in cands if self.mods[self.fns[c].mod].layer == "svc"]
        # make sure every service function nobody calls yet gets called from run
        unc = [c for c in svc if not self.callers.get(c)]
        chosen = []
        for c in unc:
            if c not in chosen:
                chosen.append(c)
        pool = [c for c in cands if c not in chosen]
        rng.shuffle(pool)
        while len(chosen) < k and pool:
            chosen.append(pool.pop())
        chosen = chosen[: max(k, min(len(unc), 14))]
        for c in chosen:
            self.callers.setdefault(c, []).append(run.fid)
        consts = {}
        lines = []
        vals = [(V("count"), PBOUND), (V("days"), PBOUND)]
        vs = []
        for j, c in enumerate(chosen):
            cf = self.fns[c]
            args = [self.arg_expr(vals, consts, rng) for _ in cf.params]
            v = f"r{j + 1}"
            lines.append(("let", v, Call(c, *args)))
            vals.append((V(v), PBOUND))
            vs.append(v)
            if j % 3 == 2 or j == len(chosen) - 1:
                lines.append(("emit", f"batch {j // 3 + 1}: {{}} {{}}", [V(v), V(vs[max(0, len(vs) - 2)])]))
        tot = None
        for v in vs:
            tot = V(v) if tot is None else Op("+", tot, V(v))
        lines.append(("let", "total", Op("%", tot, N(LIM))))
        lines.append(("emit", f"{dom.name} total {{}} for {{}} days", [V("total"), V("days")]))
        lines.append(("ret", V("total")))
        run.body = lines
        main = Fn(fid="cli.main", mod="cli", name="main", params=["count", "days"], body=[], public=True, doc="Command line entry point.", kind="main")
        self.fns[main.fid] = main
        m.fids.append(main.fid)

    def connect_orphans(self):
        """every function that is not meant to be dead gets at least one caller"""
        rng = self.rng
        order = list(self.fns)
        called = {c for fid in self.fns for c in self.static_callees(fid)}
        for f in reversed(order):
            fn = self.fns[f]
            if fn.kind != "fn" or f in called or f in self.dead_set or f == "cli.run":
                continue
            fm = self.mods[fn.mod]
            pos = order.index(f)
            cands = []
            for g in order[pos + 1:]:
                gf = self.fns[g]
                gm = self.mods[gf.mod]
                if gf.kind != "fn" or g in self.dead_set or gm.layer == "errors":
                    continue
                if gm.layer == "util" and fm.layer != "util":
                    continue
                if gm.layer == "core" and fm.layer not in ("util", "core"):
                    continue
                if gf.mod != fn.mod and not fn.public:
                    continue
                cands.append(g)
            if not cands:
                if not fn.public:
                    fn.public = True
                cands = ["cli.run"]
            g = rng.choice(cands) if "cli.run" not in cands or len(cands) == 1 else rng.choice([c for c in cands if c != "cli.run"] or cands)
            self.attach_call(g, f)
            called.add(f)

    def static_callees(self, fid):
        f = self.fns[fid]
        out = []
        for st in _stmts(f.body):
            for e in _stmt_exprs(st):
                for x in _walk(e):
                    if x[0] == "call":
                        out.append(x[1])
        return out

    def attach_call(self, g: str, f: str):
        """make function g call function f: bind the result in a new variable and add it into the final expression"""
        rng = self.rng
        gf, ff = self.fns[g], self.fns[f]
        used = set(gf.params) | {st[1] for st in _stmts(gf.body) if st[0] in ("let", "set")}
        v = rng.choice([x for x in VARS if x not in used])
        args = [V(rng.choice(gf.params)) if rng.random() < 0.7 else N(rng.randint(1, 30)) for _ in ff.params]
        call = Call(f, *args)
        if g == "cli.run":
            idx = next(i for i, st in enumerate(gf.body) if st[0] == "let" and st[1] == "total")
            st = gf.body[idx]
            tot = st[2][2]  # ("op", "%", tot, N(LIM))
            gf.body.insert(idx, ("let", v, call))
            gf.body[idx + 1] = ("let", "total", Op("%", Op("+", tot, V(v)), N(LIM)))
            return
        for i in range(len(gf.body) - 1, -1, -1):
            if gf.body[i][0] == "ret":
                old = gf.body[i][1]
                gf.body.insert(i, ("let", v, call))
                gf.body[i + 1] = ("ret", Op("%", Op("+", old, V(v)), N(rng.choice([997, 1009, 4001, 9973]))))
                return
        raise RuntimeError("no ret to extend")

    def add_cycle(self, proj: Project):
        """a module import cycle that is still acyclic at function level: a new function in a low module calls up into a higher one"""
        rng = self.rng
        want = rng.choice([2, 2, 3, 3, 4])
        mods = [m.key for m in sorted(proj.mods.values(), key=lambda m: m.rank) if m.layer in ("util", "core", "svc")]
        for _ in range(60):
            x = rng.choice(mods)
            path = [x]
            while len(path) < want:
                nxt = [k for k in proj.used_imports(path[-1]) if proj.mods[k].layer in ("util", "core", "svc") and k not in path]
                if not nxt:
                    break
                path.append(rng.choice(sorted(nxt)))
            if len(path) < 2:
                continue
            z = path[-1]
            tgt = [f for f in proj.exports(x)]
            if not tgt:
                continue
            h = rng.choice(tgt)
            mz = proj.mods[z]
            noun = rng.choice(["sync", "refresh", "recheck", "reload", "resync"])
            name = self.fresh_name(lambda: f"{noun}_{rng.choice(proj.mods[z].base.split('_'))}_{rng.choice(['view', 'copy', 'state', 'cache', 'index'])}")
            fid = f"{z}.{name}"
            hf = self.fns[h]
            p0 = rng.choice(PARAMS)
            body = [("ret", Op("%", Op("+", Call(h, *[Op("+", V(p0), N(1 + i)) for i in range(len(hf.params))]), N(rng.randint(1, 9))), N(rng.choice([997, 1009, 4001]))))]
            fn = Fn(fid=fid, mod=z, name=name, params=[p0], body=body, public=True, doc=f"Re-read {proj.mods[x].base} values from inside {mz.base}.")
            self.fns[fid] = fn
            mz.fids.append(fid)
            mz.lazy.append(x)
            # run calls it, so the function is live and the cycle is real
            run = self.fns["cli.run"]
            self.attach_call("cli.run", fid)
            proj.seed_info["cycle"] = {"path": path, "back_fn": fid, "target": h}
            return
        raise RuntimeError("no cycle")

    def add_decoys(self, proj: Project):
        """unused imports of other modules (realistic noise); never create an import cycle"""
        rng = self.rng
        mods = [m for m in proj.mods.values() if m.layer in ("core", "svc", "util")]
        if proj.lang == "go" or proj.lang == "rust":
            return
        for m in mods:
            if rng.random() < 0.3:
                lower = [x for x in proj.mods.values() if x.rank < m.rank and x.layer in ("util", "core") and x.key != m.key]
                used = set(proj.used_imports(m.key))
                lower = [x for x in lower if x.key not in used and not (m.layer == "util" and x.layer != "util")]
                if proj.lang == "java":
                    lower = [x for x in lower if x.pkg != m.pkg]
                if lower:
                    m.decoys.append(rng.choice(lower).key)


# ------------------------------------------------------------------------------------------------------------ tests
CASE_WORDS = ["basic", "small", "typical", "large", "boundary", "mid_range", "busy", "quiet", "edge", "bulk", "single", "weekday", "peak", "offseason"]


def make_cases(rng: random.Random, proj: Project, lang: str):
    """unit-test cases (function, args, expected) computed by running the interpreter"""
    names: set = set()
    seen_args: dict = {}
    for m in sorted(proj.mods.values(), key=lambda m: m.rank):
        if m.layer in ("errors", "cli"):
            continue
        fids = [f for f in m.fids if proj.fns[f].public and proj.fns[f].kind == "fn"]
        rng.shuffle(fids)
        want = rng.randint(1, min(3, len(fids))) if fids else 0
        got = 0
        for fid in fids:
            if got >= want:
                break
            f = proj.fns[fid]
            tr = Trace()
            args = [rng.randint(1, 60) for _ in f.params]
            try:
                val = proj.run(fid, args, tr)
            except Raised as r:
                if lang in EXC_LANGS:
                    cname = _case_name(rng, f.name, names)
                    proj.cases.append(Case(name=cname, fid=fid, args=args, expect="raises", exc=r.exc))
                    got += 1
                continue
            if tr.out and lang != "python":
                continue
            cname = _case_name(rng, f.name, names)
            proj.cases.append(Case(name=cname, fid=fid, args=args, expect="ok", value=val, lines=list(tr.out)))
            seen_args.setdefault(fid, []).append(args)
            got += 1
    # one end-to-end test of the entry (python captures stdout; other languages do not test run)
    if lang == "python":
        for _ in range(40):
            tr = Trace()
            args = [rng.randint(2, 9), rng.randint(2, 9)]
            try:
                val = proj.run(proj.run_fid, args, tr)
            except Raised:
                continue
            proj.cases.append(Case(name="run_prints_report", fid=proj.run_fid, args=args, expect="ok", value=val, lines=list(tr.out)))
            break
    proj.seed_info["test_args"] = seen_args


def _case_name(rng, fname, names):
    for _ in range(40):
        n = f"{fname}_{rng.choice(CASE_WORDS)}"
        if n not in names:
            names.add(n)
            return n
    n = f"{fname}_case{len(names)}"
    names.add(n)
    return n


def make_project(rng: random.Random, spec: Spec) -> Project:
    for attempt in range(30):
        try:
            b = Builder(rng, spec)
            return b.build()
        except (AssertionError, RuntimeError):
            continue
    raise RuntimeError("could not build a project")
