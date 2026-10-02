"""Bisect tasks: a base tree plus a series of patches; the check passes on the base and fails on the final tree.

The project is a record pipeline whose steps register in ``<pkg>/steps/__init__.py``.  Every step module declares what it does
(``SPEC``) and implements it; ``check.py`` runs sample records through the pipeline and compares with a reference reading of the
specs.  A series is built by evolving the tree patch by patch: new steps, parameter tweaks, behaviour-preserving rewrites, reorders,
removals, doc edits.  One patch plants a defect (a new step, or a "tidy-up" rewrite of an existing one, that deviates from its
SPEC); the truth is found by running the check on every prefix.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import random

from fx import Task, dd, run
from fx.run import merged

from ._engine import KINDS, accepted, hidden_diag

SKINS = [
    dict(pkg="stationflow", what="weather-station readings", title="the Hilltop weather network",
         num=[("temp_c", -30, 45), ("humidity", 0, 100), ("wind_kph", 0, 120), ("pressure_hpa", 950, 1050), ("rain_mm", 0, 80)], txt=["station", "label"]),
    dict(pkg="scanflow", what="parcel scans at a warehouse gate", title="the Quarry Road warehouse",
         num=[("weight_g", 0, 30000), ("length_mm", 50, 1200), ("width_mm", 50, 800), ("height_mm", 20, 600), ("qty", 1, 40)], txt=["sku", "bin"]),
    dict(pkg="labflow", what="water-sample measurements", title="the Tarn Valley water lab",
         num=[("ph", 4, 10), ("conductivity_us", 0, 2000), ("turbidity_ntu", 0, 400), ("temp_c", 0, 40), ("chlorine_mgl", 0, 5)], txt=["sample", "site"]),
]

AUTHORS = ["Mira Okafor", "Jonas Lindqvist", "Priya Raman", "Tomasz Wieczorek", "Aoife Brennan", "Dev Patel", "Lucía Ferrer", "Sam Whitlock"]

# ---- step code ------------------------------------------------------------------------------------------------------

HEAD = '"""{doc}"""\n\nNAME = "{name}"\nSPEC = {spec}\n{consts}\n\n'


def _spec_line(spec: dict) -> str:
    return json.dumps(spec, sort_keys=False)


def _consts(op: str) -> str:
    return {
        "clamp": 'FIELD, LO, HI = SPEC["field"], SPEC["lo"], SPEC["hi"]',
        "scale": 'FIELD, FACTOR = SPEC["field"], SPEC["factor"]',
        "offset": 'FIELD, DELTA = SPEC["field"], SPEC["delta"]',
        "round": 'FIELD, DIGITS = SPEC["field"], SPEC["digits"]',
        "rename": 'SRC, DST = SPEC["src"], SPEC["dst"]',
        "default": 'FIELD, VALUE = SPEC["field"], SPEC["value"]',
        "tidy": 'FIELD = SPEC["field"]',
        "cap_len": 'FIELD, N = SPEC["field"], SPEC["n"]',
    }[op]


BODIES: dict[str, dict[str, list[str]]] = {
    "clamp": {
        "good": [
            dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if v is None:
                        return rec
                    return {**rec, FIELD: min(max(v, LO), HI)}
            '''),
            dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if v is None:
                        return rec
                    if v < LO:
                        v = LO
                    elif v > HI:
                        v = HI
                    return {**rec, FIELD: v}
            '''),
        ],
        "bad": [
            ("order of min/max swapped: every value ends up at HI", dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if v is None:
                        return rec
                    return {**rec, FIELD: max(min(v, LO), HI)}
            '''), "logic-error"),
            ("a missing or None value is not skipped, so the comparison fails with a TypeError", dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if v < LO:
                        v = LO
                    elif v > HI:
                        v = HI
                    return {**rec, FIELD: v}
            '''), "null-handling"),
        ],
    },
    "scale": {
        "good": [
            dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if v is None:
                        return rec
                    return {**rec, FIELD: v * FACTOR}
            '''),
        ],
        "bad": [
            ("the scaled value is truncated with int(), losing the fraction", dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if v is None:
                        return rec
                    return {**rec, FIELD: int(v * FACTOR)}
            '''), "rounding"),
            ("the factor is applied twice", dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if v is None:
                        return rec
                    return {**rec, FIELD: v * FACTOR * FACTOR}
            '''), "logic-error"),
        ],
    },
    "offset": {
        "good": [
            dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if v is None:
                        return rec
                    return {**rec, FIELD: v + DELTA}
            '''),
        ],
        "bad": [
            ("the offset is subtracted instead of added", dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if v is None:
                        return rec
                    return {**rec, FIELD: v - DELTA}
            '''), "logic-error"),
            ("a missing field is created as DELTA instead of being left alone", dd('''
                def apply(rec):
                    return {**rec, FIELD: (rec.get(FIELD) or 0) + DELTA}
            '''), "null-handling"),
        ],
    },
    "round": {
        "good": [
            dd('''
                from decimal import ROUND_HALF_UP, Decimal


                def apply(rec):
                    v = rec.get(FIELD)
                    if v is None:
                        return rec
                    q = Decimal(1).scaleb(-DIGITS)
                    return {**rec, FIELD: float(Decimal(str(v)).quantize(q, rounding=ROUND_HALF_UP))}
            '''),
        ],
        "bad": [
            ("the builtin round() is used: it rounds halves to even and works on the binary float, not half up on the decimal text", dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if v is None:
                        return rec
                    return {**rec, FIELD: float(round(v, DIGITS))}
            '''), "rounding"),
        ],
    },
    "rename": {
        "good": [
            dd('''
                def apply(rec):
                    if SRC not in rec:
                        return rec
                    out = {k: v for k, v in rec.items() if k != SRC}
                    out[DST] = rec[SRC]
                    return out
            '''),
        ],
        "bad": [
            ("falsy values (0, empty text) are dropped because the presence test is truthiness", dd('''
                def apply(rec):
                    if not rec.get(SRC):
                        return rec
                    out = {k: v for k, v in rec.items() if k != SRC}
                    out[DST] = rec[SRC]
                    return out
            '''), "logic-error"),
            ("the source field is copied but never removed", dd('''
                def apply(rec):
                    if SRC not in rec:
                        return rec
                    return {**rec, DST: rec[SRC]}
            '''), "logic-error"),
        ],
    },
    "default": {
        "good": [
            dd('''
                def apply(rec):
                    if rec.get(FIELD) is None:
                        return {**rec, FIELD: VALUE}
                    return rec
            '''),
        ],
        "bad": [
            ("every falsy value (0, empty text) is overwritten, not just missing or None", dd('''
                def apply(rec):
                    if not rec.get(FIELD):
                        return {**rec, FIELD: VALUE}
                    return rec
            '''), "null-handling"),
        ],
    },
    "tidy": {
        "good": [
            dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if not isinstance(v, str):
                        return rec
                    return {**rec, FIELD: v.strip().upper()}
            '''),
        ],
        "bad": [
            ("only the left side is stripped (lstrip), trailing blanks survive", dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if not isinstance(v, str):
                        return rec
                    return {**rec, FIELD: v.lstrip().upper()}
            '''), "logic-error"),
            ("non-text values are not skipped, so a number reaches .strip() and raises AttributeError", dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if v is None:
                        return rec
                    return {**rec, FIELD: v.strip().upper()}
            '''), "type-confusion"),
        ],
    },
    "cap_len": {
        "good": [
            dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if not isinstance(v, str):
                        return rec
                    return {**rec, FIELD: v[:N]}
            '''),
        ],
        "bad": [
            ("off by one: the text is cut to N - 1 characters", dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if not isinstance(v, str):
                        return rec
                    return {**rec, FIELD: v[: N - 1]}
            '''), "off-by-one"),
            ("off by one: the text is cut to N + 1 characters", dd('''
                def apply(rec):
                    v = rec.get(FIELD)
                    if not isinstance(v, str):
                        return rec
                    return {**rec, FIELD: v[: N + 1]}
            '''), "off-by-one"),
        ],
    },
}

DOCS = {
    "clamp": "Keep {field} inside [{lo}, {hi}].",
    "scale": "Multiply {field} by {factor}.",
    "offset": "Add {delta} to {field}.",
    "round": "Round {field} to {digits} decimals, halves up.",
    "rename": "Rename {src} to {dst}.",
    "default": "Fill in {field} with {value!r} when it is missing.",
    "tidy": "Trim and upper-case {field}.",
    "cap_len": "Cut {field} to at most {n} characters.",
}

SUBJECT = {
    "clamp": "add a clamp for {field}", "scale": "scale {field} by {factor}", "offset": "shift {field} by {delta}", "round": "round {field} to {digits} places",
    "rename": "rename {src} to {dst}", "default": "default {field}", "tidy": "normalise {field} text", "cap_len": "cap the length of {field}",
}


# ---- the check script (visible to the agent) ------------------------------------------------------------------------

CHECK = '''#!/usr/bin/env python3
"""Regression check: runs the sample records through the pipeline of a source tree and compares the result with the reference reading of every
registered step's SPEC.   usage: python3 check.py [TREE]    (TREE defaults to the current directory; exit status 0 = fine, 1 = mismatch)"""
import copy
import os
import sys
from decimal import ROUND_HALF_UP, Decimal

TREE = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
sys.path.insert(0, TREE)
sys.dont_write_bytecode = True

SAMPLES = __SAMPLES__


def half_up(v, digits):
    return float(Decimal(str(v)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def reference(spec, rec):
    op = spec["op"]
    rec = dict(rec)
    if op == "rename":
        if spec["src"] in rec:
            rec[spec["dst"]] = rec.pop(spec["src"])
        return rec
    f = spec.get("field")
    v = rec.get(f)
    if op == "default":
        if v is None:
            rec[f] = spec["value"]
        return rec
    if v is None:
        return rec
    if op == "clamp":
        rec[f] = min(max(v, spec["lo"]), spec["hi"])
    elif op == "scale":
        rec[f] = v * spec["factor"]
    elif op == "offset":
        rec[f] = v + spec["delta"]
    elif op == "round":
        rec[f] = half_up(v, spec["digits"])
    elif op == "tidy":
        if isinstance(v, str):
            rec[f] = v.strip().upper()
    elif op == "cap_len":
        if isinstance(v, str):
            rec[f] = v[: spec["n"]]
    return rec


def main():
    from __PKG__.steps import ORDER

    bad = 0
    for i, original in enumerate(SAMPLES):
        want = copy.deepcopy(original)
        for step in ORDER:
            want = reference(step.SPEC, want)
        try:
            from __PKG__ import pipeline

            got = pipeline.run([copy.deepcopy(original)])[0]
        except Exception as exc:  # noqa: BLE001
            print(f"record {i}: the pipeline raised {type(exc).__name__}: {exc}")
            bad += 1
            continue
        if got != want:
            for k in sorted(set(got) | set(want)):
                if got.get(k, "<missing>") != want.get(k, "<missing>"):
                    print(f"record {i}: field {k!r}: expected {want.get(k, '<missing>')!r}, got {got.get(k, '<missing>')!r}")
            bad += 1
    print("FAIL: %d of %d sample records differ" % (bad, len(SAMPLES)) if bad else "ok: %d sample records" % len(SAMPLES))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
'''

TRY_SH = '''#!/usr/bin/env bash
# usage: ./try.sh N    build work/ = base/ + the first N patches (in file name order) and run check.py on it
set -e
n=${1:?usage: ./try.sh N}
rm -rf work
cp -r base work
i=0
for p in $(ls patches/*.patch | sort); do
  i=$((i + 1))
  [ "$i" -gt "$n" ] && break
  (cd work && patch -p1 -s < "../$p") || { echo "patch $p does not apply"; exit 2; }
done
python3 check.py work
'''


class Series:
    def __init__(self, rng: random.Random, skin: dict):
        self.rng, self.skin = rng, skin
        self.pkg = skin["pkg"]
        self.steps: dict[str, dict] = {}  # module name -> {"op", "spec", "code", "doc", "style"}
        self.order: list[str] = []
        self.counter = 0

    # -- tree rendering
    def render(self, extra_readme: str = "") -> dict[str, str]:
        t = {
            f"{self.pkg}/__init__.py": f'"""{self.skin["what"].capitalize()} pipeline."""\n',
            f"{self.pkg}/pipeline.py": dd('''
                """The record pipeline: every registered step is applied to every record, in order."""
                from copy import deepcopy

                from .steps import ORDER


                def run(records):
                    out = []
                    for rec in records:
                        rec = deepcopy(rec)
                        for step in ORDER:
                            rec = step.apply(rec)
                        out.append(rec)
                    return out
            '''),
            "README.md": dd(f'''
                # {self.pkg}

                Processing pipeline for {self.skin["what"]} of {self.skin["title"]}. Each step lives in `{self.pkg}/steps/` and is
                registered in `{self.pkg}/steps/__init__.py`; the steps run in the order of `ORDER`.

                A step module has a `SPEC` (a small dict that says what it does) and an `apply(record)` function that returns the new record.
            ''') + extra_readme,
        }
        imports = "".join(f"from . import {m}\n" for m in sorted(self.steps))
        order = "".join(f"    {m},\n" for m in self.order)
        t[f"{self.pkg}/steps/__init__.py"] = f'"""Registered steps, in the order they run."""\n{imports}\nORDER = [\n{order}]\n'
        for m, st in self.steps.items():
            t[f"{self.pkg}/steps/{m}.py"] = st["code"]
        return t

    # -- step construction
    def new_step(self, op: str, bug: bool = False, style: int = 0, bad_index: int = 0) -> str:
        sk, rng = self.skin, self.rng
        nums, txts = sk["num"], sk["txt"]
        fld, lo, hi = rng.choice(nums)
        spec: dict
        if op == "clamp":
            a = lo + (hi - lo) * rng.choice([0.0, 0.05, 0.1])
            b = hi - (hi - lo) * rng.choice([0.0, 0.05, 0.1])
            a, b = (round(a, 1), round(b, 1)) if isinstance(lo, float) or lo % 1 else (round(a), round(b))
            spec = {"op": op, "field": fld, "lo": a, "hi": b}
        elif op == "scale":
            spec = {"op": op, "field": fld, "factor": rng.choice([0.1, 0.25, 0.5, 1.1, 1.8, 2, 3.6, 0.9, 1.609])}
        elif op == "offset":
            spec = {"op": op, "field": fld, "delta": rng.choice([-5, -2.5, 1, 2.5, 10, 0.5, -0.25])}
        elif op == "round":
            spec = {"op": op, "field": fld, "digits": rng.choice([0, 1, 2])}
        elif op == "rename":
            spec = {"op": op, "src": fld, "dst": rng.choice([fld + "_raw", "raw_" + fld, fld + "_v1"])}
        elif op == "default":
            spec = {"op": op, "field": fld, "value": rng.choice([0, 1, hi, lo])}
        elif op == "tidy":
            spec = {"op": op, "field": rng.choice(txts)}
        else:
            spec = {"op": op, "field": rng.choice(txts), "n": rng.choice([4, 5, 6, 8])}
        key = spec.get("field") or spec.get("src")
        mod = f"s_{op}_{key}"
        while mod in self.steps:
            self.counter += 1
            mod = f"s_{op}_{key}{self.counter}"
        name = mod[2:].replace("_", "-")
        code = self._code(mod, op, spec, bug, style, bad_index)
        self.steps[mod] = {"op": op, "spec": spec, "doc": DOCS[op].format(**spec), "style": style, "bug": bug}
        self.steps[mod]["code"] = code
        return mod

    def _code(self, mod: str, op: str, spec: dict, bug: bool, style: int, bad_index: int = 0) -> str:
        name = mod[2:].replace("_", "-")
        head = HEAD.format(doc=DOCS[op].format(**spec), name=name, spec=_spec_line(spec), consts=_consts(op))
        if bug:
            body = BODIES[op]["bad"][bad_index % len(BODIES[op]["bad"])][1]
        else:
            goods = BODIES[op]["good"]
            body = goods[style % len(goods)]
        if body.startswith("from "):  # a step with its own imports: keep them at the top
            imp, rest = body.split("\n\n\n", 1)
            return f'"""{DOCS[op].format(**spec)}"""\n{imp}\n\nNAME = "{name}"\nSPEC = {_spec_line(spec)}\n{_consts(op)}\n\n\n{rest}'
        return head + body

    def bug_info(self, op: str, bad_index: int = 0) -> tuple[str, str]:
        b = BODIES[op]["bad"][bad_index % len(BODIES[op]["bad"])]
        return b[0], b[2]


def sample_records(rng: random.Random, series: "Series", n: int = 14) -> list[dict]:
    sk = series.skin
    nums = [(f, lo, hi) for f, lo, hi in sk["num"]]
    vals_by_field = {}
    bounds: dict[str, list] = {f: [] for f, _, _ in nums}
    for st in series.steps.values():
        sp = st["spec"]
        if sp["op"] == "clamp":
            bounds[sp["field"]] += [sp["lo"], sp["hi"], sp["lo"] - 1, sp["hi"] + 1]
    recs: list[dict] = []
    base_vals = [0, 0.5, 1.5, 2.5, 2.675, 0.125, -0.5, -3, 7, 12.34, 100, 1e-3, 33.75, 0.05, 18.0]
    for i in range(n):
        r: dict = {}
        for f, lo, hi in nums:
            roll = rng.random()
            if roll < 0.08:
                continue
            if roll < 0.14:
                r[f] = None
                continue
            pool = base_vals + bounds[f] + [lo, hi, (lo + hi) / 2]
            r[f] = rng.choice(pool)
        for j, f in enumerate(sk["txt"]):
            roll = rng.random()
            if roll < 0.08:
                continue
            r[f] = rng.choice(["  alpha ", "Beta", "gamma  ", "", " delta", "épsilon ", "zeta-12345", "eta", "θ-north", "  ", "kappa 9", "lambda.long.name"])
        recs.append(r)
    # make sure each step's trigger values exist somewhere
    for st in series.steps.values():
        sp = st["spec"]
        f = sp.get("field") or sp.get("src")
        extra: dict = {}
        if sp["op"] in ("rename", "default", "scale", "offset", "round", "clamp"):
            for v in (0, 2.5, 2.675, 1.5, sp.get("lo"), sp.get("hi"), 0.0):
                if v is not None:
                    r = {g: rng.choice([1, 2.25, 40]) for g, _, _ in nums}
                    r[f] = v
                    for g in sk["txt"]:
                        r[g] = "x"
                    recs.append(r)
        elif sp["op"] in ("tidy", "cap_len"):
            for v in ("  trail  ", "abcdefghij", "Mixed Case ", "", 17):
                r = {g: 1 for g, _, _ in nums}
                r[f] = v
                recs.append(r)
    rng.shuffle(recs)
    return recs[:48]


def _patch_text(old: dict[str, str], new: dict[str, str], subject: str, idx: int, total: int, rng: random.Random) -> str:
    chunks = []
    for path in sorted(set(old) | set(new)):
        a, b = old.get(path), new.get(path)
        if a == b:
            continue
        if a is None:
            body = list(difflib.unified_diff([], b.splitlines(True), "/dev/null", f"b/{path}", n=3))
            hdr = f"diff --git a/{path} b/{path}\nnew file mode 100644\n"
        elif b is None:
            body = list(difflib.unified_diff(a.splitlines(True), [], f"a/{path}", "/dev/null", n=3))
            hdr = f"diff --git a/{path} b/{path}\ndeleted file mode 100644\n"
        else:
            body = list(difflib.unified_diff(a.splitlines(True), b.splitlines(True), f"a/{path}", f"b/{path}", n=3))
            hdr = f"diff --git a/{path} b/{path}\n"
        chunks.append(hdr + "".join(x if x.endswith("\n") else x + "\n" for x in body))
    day = 3 + idx // 2
    author = AUTHORS[(idx * 5 + total) % len(AUTHORS)]
    head = (f"From: {author} <{author.split()[0].lower()}@example.org>\nDate: {['Mon', 'Tue', 'Wed', 'Thu', 'Fri'][idx % 5]}, {day % 28 + 1} "
            f"{['Jan', 'Feb', 'Mar', 'Apr'][idx * 7 // max(1, total) % 4]} 2025 {9 + idx % 8:02d}:{(idx * 13) % 60:02d}:00 +0000\n"
            f"Subject: [PATCH {idx:04d}/{total:04d}] {subject}\n\n---\n")
    return head + "".join(chunks)


def _slug(m: str) -> str:
    return m[2:].replace("_", "-")


def _apply_patch_kind(S: Series, rng: random.Random, kind: str, i: int, ctx: dict) -> str | None:
    """Mutate S according to `kind`; returns the subject line, or None when the kind is not possible right now."""
    ops = list(BODIES)
    if kind == "culprit":
        if ctx["mode"] == "refactor":
            cands = [m for m in S.order if not S.steps[m]["bug"]]
            m = rng.choice(cands)
            st = S.steps[m]
            bi = rng.randrange(len(BODIES[st["op"]]["bad"]))
            st["code"] = S._code(m, st["op"], st["spec"], True, 0, bi)
            st["bug"] = True
            why, k = S.bug_info(st["op"], bi)
            ctx["culprit"] = dict(module=m, file=f"{S.pkg}/steps/{m}.py", why=why, kind=k, op=st["op"])
            return f"tidy up {_slug(m)}: simplify the implementation"
        op = rng.choice(ops)
        bi = rng.randrange(len(BODIES[op]["bad"]))
        m = S.new_step(op, bug=True, bad_index=bi)
        S.order.insert(rng.randint(0, len(S.order)), m)
        why, k = S.bug_info(op, bi)
        ctx["culprit"] = dict(module=m, file=f"{S.pkg}/steps/{m}.py", why=why, kind=k, op=op)
        return f"{S.pkg}: {SUBJECT[op].format(**S.steps[m]['spec'])}"
    if kind == "disable":
        m = ctx["culprit"]["module"]
        S.order.remove(m)
        ctx["position"] = None
        return f"temporarily take {_slug(m)} out of the pipeline while we look at the sample failures"
    if kind == "enable":
        m = ctx["culprit"]["module"]
        S.order.insert(rng.randint(0, len(S.order)), m)
        return f"put {_slug(m)} back into the pipeline"
    if kind == "add":
        op = rng.choice(ops)
        m = S.new_step(op)
        S.order.insert(rng.randint(0, len(S.order)), m)
        return f"{S.pkg}: {SUBJECT[op].format(**S.steps[m]['spec'])}"
    protected = {ctx["culprit"]["module"]} if ctx.get("culprit") else set()
    if kind == "retune":
        cands = [m for m in S.order if S.steps[m]["op"] in ("clamp", "scale", "offset", "round", "cap_len", "default") and not S.steps[m]["bug"]]
        if not cands:
            return None
        m = rng.choice(cands)
        st = S.steps[m]
        spec = dict(st["spec"])
        key = {"clamp": "hi", "scale": "factor", "offset": "delta", "round": "digits", "cap_len": "n", "default": "value"}[st["op"]]
        old = spec[key]
        spec[key] = {"clamp": lambda v: v - 1, "scale": lambda v: round(v * 1.25, 4), "offset": lambda v: v + 0.5, "round": lambda v: (v + 1) % 3,
                     "cap_len": lambda v: v + 1, "default": lambda v: (v or 0) + 1}[st["op"]](old)
        st["spec"] = spec
        st["code"] = S._code(m, st["op"], spec, False, st["style"])
        return f"retune {_slug(m)}: {key} {old} -> {spec[key]}"
    if kind == "restyle":
        cands = [m for m in S.order if len(BODIES[S.steps[m]["op"]]["good"]) > 1 and not S.steps[m]["bug"]]
        if not cands:
            return None
        m = rng.choice(cands)
        st = S.steps[m]
        st["style"] += 1
        st["code"] = S._code(m, st["op"], st["spec"], False, st["style"])
        return f"refactor {_slug(m)} (no functional change)"
    if kind == "reorder":
        if len(S.order) < 3:
            return None
        a, b = rng.sample(range(len(S.order)), 2)
        S.order[a], S.order[b] = S.order[b], S.order[a]
        return f"{S.pkg}: run {_slug(S.order[a])} before {_slug(S.order[b])}"
    if kind == "drop":
        cands = [m for m in S.order if m not in protected and not S.steps[m]["bug"]]
        if len(S.order) < 4 or len(cands) < 3:
            return None
        m = rng.choice(cands)
        S.order.remove(m)
        del S.steps[m]
        return f"drop the {_slug(m)} step"
    if kind == "docs":
        text = rng.choice(["Describe the step registry.", "Fix a typo in the step list.", "Explain how to add a step.", "Mention the check script.", "Add a note on step order."])
        S.readme_extra += f"\n{text} (revision {i}).\n"
        return "README: " + text[:-1].lower()
    return None


def build_series(rng: random.Random, skin: dict, n_patches: int, culprit_pos: float, mode: str, nonmono: bool):
    import copy

    S = Series(rng, skin)
    S.readme_extra = ""
    ops = list(BODIES)
    for _ in range(2):
        S.order.append(S.new_step(rng.choice(ops)))
    base = S.render()
    trees, patches = [base], []
    culprit_idx = max(2, min(n_patches - 4 if nonmono else n_patches - 2, int(n_patches * culprit_pos)))
    forced: dict[int, str] = {culprit_idx: "culprit"}
    off_idx = on_idx = None
    if nonmono:
        off_idx = culprit_idx + rng.randint(1, max(1, (n_patches - culprit_idx) // 3))
        on_idx = off_idx + rng.randint(2, max(2, (n_patches - off_idx) // 2))
        if on_idx >= n_patches:
            return None
        forced[off_idx], forced[on_idx] = "disable", "enable"
    ctx: dict = {"mode": mode}
    weights = [("add", 40), ("retune", 14), ("restyle", 12), ("reorder", 10), ("drop", 8), ("docs", 16)]
    for i in range(1, n_patches + 1):
        prev = trees[-1]
        done = False
        for attempt in range(30):
            snap = (copy.deepcopy(S.steps), list(S.order), S.readme_extra, S.counter, copy.deepcopy(ctx))
            kind = forced.get(i) or rng.choices([w[0] for w in weights], [w[1] for w in weights])[0]
            subject = _apply_patch_kind(S, rng, kind, i, ctx)
            tree = S.render(S.readme_extra) if subject else None
            if subject is None or tree == prev:
                S.steps, S.order, S.readme_extra, S.counter, ctx = snap[0], snap[1], snap[2], snap[3], snap[4]
                if forced.get(i):
                    return None
                continue
            done = True
            break
        if not done:
            return None
        fname = f"{i:04d}-{''.join(c if c.isalnum() else '-' for c in subject.lower())}"
        fname = "-".join(x for x in fname.split("-") if x)[:60].rstrip("-") + ".patch"
        patches.append((fname, _patch_text(prev, tree, subject, i, n_patches, rng)))
        trees.append(tree)
    return base, patches, trees, culprit_idx, ctx["culprit"], (off_idx, on_idx), S


def check_text(series: "Series", samples: list[dict]) -> str:
    return CHECK.replace("__SAMPLES__", _pyrepr(samples)).replace("__PKG__", series.pkg)


def _pyrepr(samples: list[dict]) -> str:
    lines = ["["]
    for r in samples:
        lines.append("    " + repr(r) + ",")
    lines.append("]")
    return "\n".join(lines)


def outcome(tree: dict[str, str], check: str) -> tuple[bool, str]:
    r = run(merged(tree, {"check.py": check}), "python3 check.py .", timeout=60)
    return r.ok, r.out


BISECT_VOICES = [
    "Release engineering here. Last week's merge brought {n} patches into the development tree (they are in `patches/`, in the order they were applied on top of `base/`). `check.py` passes on `base/` and fails on the tree with everything applied. I need the *first* patch after which it fails. {tools} {schema}",
    "git history for this component was squashed into a patch series before it reached us, so there is no `git bisect`. The tree in `base/` is good, the tree after all {n} patches is bad (`check.py` says so). Find the patch that introduced the problem. {tools} {schema}",
    "which patch broke the check? {n} patches in patches/, base is fine, final tree is not. {tools} {schema}",
    "QA noticed that sample records come out wrong in the current development build of {title}. The build is `base/` plus the {n} patches in `patches/`, applied in file-name order. Track the regression down to the patch that causes it. {tools} {schema}",
    "A teammate asked me to find out where our nightly went red. The nightly runs `check.py` on the tree built from `base/` and the {n} patches under `patches/`. {tools} {schema}",
]


def bisect_task(rng: random.Random, i: int, n_patches: int, culprit_pos: float, mode: str, nonmono: bool, skin: dict) -> Task | None:
    built = build_series(rng, skin, n_patches, culprit_pos, mode, nonmono)
    if built is None:
        return None
    base, patches, trees, cidx, cinfo, (off, on), S = built
    samples = sample_records(rng, S)
    check = check_text(S, samples)
    res = [outcome(t, check) for t in trees]
    ok = [r[0] for r in res]
    if not ok[0] or not all(ok[:cidx]) or ok[cidx] or ok[-1]:
        return None
    if nonmono:
        if not all(ok[off:on]) or ok[on]:
            return None
    elif any(ok[cidx:]):
        return None
    # the patches must really apply, and give the trees we think they give
    start = {"check.py": check, "try.sh": TRY_SH}
    for path, text in base.items():
        start["base/" + path] = text
    for name, text in patches:
        start["patches/" + name] = text
    final_hash = hashlib.md5("".join(f"{p}{hashlib.md5(t.encode()).hexdigest()}" for p, t in sorted(trees[-1].items())).encode()).hexdigest()
    probe = ("bash try.sh %d > /dev/null; echo applied; find work -type f ! -name '*.pyc' ! -path '*__pycache__*' | sort | sed 's#^work/##' | "
             "while read f; do echo \"$f $(md5sum < work/$f | cut -d' ' -f1)\"; done" % len(patches))
    r = run(start, probe, timeout=120)
    got = {}
    for line in r.out.splitlines():
        if " " in line and not line.startswith("applied"):
            f, h = line.rsplit(" ", 1)
            got[f] = h
    want = {p: hashlib.md5(t.encode()).hexdigest() for p, t in trees[-1].items()}
    if got != want:
        raise RuntimeError(f"bisect series does not apply cleanly:\n{r.out[-800:]}")
    pname = patches[cidx - 1][0]
    why = cinfo["why"]
    ntext = f"{n_patches}"
    tools = rng.choice(["`./try.sh N` builds `work/` from `base/` plus the first N patches and runs the check on it.", "There is a helper, `./try.sh N`, that applies the first N patches to a copy of `base/` and runs `check.py` on the result.",
                        "Patches are plain `patch -p1` files. `./try.sh N` is a small helper that applies the first N of them to a fresh copy of `base/` and runs the check.", ""])
    schema = ("Write `answer.json`: an object with exactly these keys: `patch` (the file name of the first bad patch, or just its number), `file` (the path inside the tree "
              "of the file that contains the defect), `kind` (one of " + ", ".join(KINDS) + ") and `explanation` (one or two sentences: what is wrong with the code).")
    if nonmono:
        schema += " The check is green again for a stretch in the middle of the series; I want the first patch that makes it fail."
    prompt = rng.choice(BISECT_VOICES).format(n=ntext, tools=tools, title=skin["title"], schema=schema).replace("  ", " ")
    kws = [cinfo["op"].replace("_", " "), cinfo["module"][2:].replace("_", "-"), "spec", "instead", "should"]
    spec = {"answer_file": "answer.json", "fields": {
        "patch": {"type": "number", "accept": [cidx]},
        "file": {"type": "path", "accept": [cinfo["file"]]},
        "kind": {"type": "enum", "allowed": KINDS, "accept": accepted(cinfo["kind"])},
        "explanation": {"type": "text", "min_len": 20, "any": kws + [cinfo["module"], cinfo["op"]]},
    }}
    gold = {"patch": pname, "file": cinfo["file"], "kind": cinfo["kind"], "explanation": f"The step does not follow its SPEC: {why}."}
    d = 1 if n_patches <= 10 else 2 if n_patches <= 16 else 3 if n_patches <= 28 else 4 if n_patches <= 44 else 5
    d = min(5, d + (1 if (mode == "refactor" and n_patches > 10) else 0) + (1 if nonmono and d < 5 else 0))
    return Task(
        slug=f"{i:02d}-{S.pkg}-{n_patches}p-{mode}{'-nonmono' if nonmono else ''}", prompt=prompt, difficulty=d, kind="fix", lang="python", start=start,
        hidden=hidden_diag(spec), solution={"answer.json": json.dumps(gold, indent=1) + "\n"}, verify="python3 _verify/check.py", pass_mode="json-score",
        protected=sorted(start), timeout_s=60, tags=["bisect", "patch-series", mode, *( ["non-monotone"] if nonmono else [])],
        notes={"patches": n_patches, "culprit": cidx, "mode": mode, "nonmonotone": nonmono, "defect": why, "skin": skin["pkg"]},
    )


def bisect_family(rng: random.Random, n: int, sizes=(8, 12, 16, 20, 24, 32, 44, 60)):
    i = 0
    guard = 0
    while i < n and guard < n * 12:
        guard += 1
        size = sizes[i % len(sizes)]
        skin = SKINS[(i + guard // 20) % len(SKINS)]
        mode = rng.choice(["add", "refactor", "add"])
        nonmono = size >= 24 and rng.random() < 0.4
        t = bisect_task(rng, i + 1, size, rng.choice([0.25, 0.4, 0.55, 0.7, 0.85]), mode, nonmono, skin)
        if t is not None:
            i += 1
            yield t
