"""Record pipelines: a dict-like record flows through stages that set, rename, default and drop fields (python, javascript, ruby).

The model gives the exact output for an input record (checked against the real code) and the static lineage of a field: which input
fields its final value is computed from, counting data flow, renames and the conditions guarding each assignment."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field

import fx

from . import _ir as I

FIELDS = ["qty", "unit_cents", "discount_pct", "zone", "weight_g", "nights", "tier", "deposit", "fee_cents", "tax_pct", "extra", "base_cents", "units", "rank", "load", "span"]
STAGE_NAMES = ["normalize", "enrich", "price", "discount", "surcharge", "tax", "round_off", "finalize", "clamp", "audit", "bundle", "settle"]


@dataclass
class Op:
    kind: str                 # set | rename | default | drop | if
    dst: str = ""
    src: str = ""
    expr: tuple | None = None   # IR expression over ("v", field)
    value: int = 0
    cond: tuple | None = None   # (op, field, const)
    body: list = field(default_factory=list)


@dataclass
class Stage:
    name: str
    ops: list


@dataclass
class Flow:
    lang: str
    pkg: str
    title: str
    inputs: list
    stages: list
    final: str
    noun: str


def _expr(rng, avail: list, depth: int = 0):
    r = rng.random()
    a = rng.choice(avail)
    if r < 0.30 or depth > 1:
        return I.Op(rng.choice(["+", "*"]), I.V(a), I.N(rng.randint(2, 9)))
    if r < 0.55 and len(avail) > 1:
        b = rng.choice([x for x in avail if x != a])
        return I.Op(rng.choice(["+", "min", "max", "sub", "+"]), I.V(a), I.V(b))
    if r < 0.75:
        return I.Op("//", I.Op("*", I.V(a), I.N(rng.randint(2, 9))), I.N(rng.choice([2, 4, 5, 10, 100])))
    if r < 0.88:
        return I.Op(rng.choice(["min", "max"]), I.V(a), I.N(rng.randint(10, 500)))
    return I.Op("+", I.V(a), I.Op("*", I.V(rng.choice(avail)), I.N(rng.randint(2, 5))))


def make_flow(rng: random.Random, lang: str, tier: int) -> Flow:
    dom = rng.choice(I.DOMAINS)
    n_in = {1: 3, 2: 4, 3: 5, 4: 6, 5: 7}[tier]
    n_st = {1: 2, 2: 3, 3: 5, 4: 7, 5: 9}[tier]
    inputs = rng.sample(FIELDS, n_in)
    present = list(inputs)
    stages = []
    names = rng.sample(STAGE_NAMES, n_st)
    fresh = [f for f in FIELDS if f not in inputs]
    rng.shuffle(fresh)
    for nm in names:
        ops = []
        for _ in range(rng.randint(1, 3 if tier < 4 else 4)):
            r = rng.random()
            if r < 0.5 and fresh:
                dst = fresh.pop()
                ops.append(Op("set", dst=dst, expr=_expr(rng, present)))
                present.append(dst)
            elif r < 0.62:
                dst = rng.choice(present)
                ops.append(Op("set", dst=dst, expr=_expr(rng, present)))
            elif r < 0.74 and len(present) > 2 and fresh:
                src = rng.choice(present)
                dst = fresh.pop()
                ops.append(Op("rename", src=src, dst=dst))
                present.remove(src)
                present.append(dst)
            elif r < 0.82 and fresh:
                dst = fresh.pop()
                ops.append(Op("default", dst=dst, value=rng.randint(1, 50)))
                present.append(dst)
            elif r < 0.9 and len(present) > 3:
                f = rng.choice(present)
                # never drop a field that is still needed later: keep it simple and drop only the most recently renamed-from leftovers
                ops.append(Op("drop", dst=f))
                present.remove(f)
            else:
                cf = rng.choice(present)
                body = []
                tgt = rng.choice(present)
                body.append(Op("set", dst=tgt, expr=_expr(rng, present)))
                ops.append(Op("if", cond=(rng.choice([">", "<", ">=", "<="]), cf, rng.randint(5, 80)), body=body))
        stages.append(Stage(nm, ops))
    final = "total_cents"
    # last stage computes the output total from whatever is present
    srcs = rng.sample(present, min(len(present), 3))
    expr = I.V(srcs[0])
    for s in srcs[1:]:
        expr = I.Op(rng.choice(["+", "*"]), expr, I.V(s)) if rng.random() < 0.6 else I.Op("+", expr, I.Op("*", I.V(s), I.N(rng.randint(2, 4))))
    stages[-1].ops.append(Op("set", dst=final, expr=I.Op("%", expr, I.N(100003))))
    return Flow(lang, dom.name, dom.title, inputs, stages, final, rng.choice(dom.nouns))


# ---------------------------------------------------------------------------------------------------------------- simulation
def _ev(e, rec):
    t = e[0]
    if t == "n":
        return e[1]
    if t == "v":
        return rec[e[1]]
    a, b = _ev(e[2], rec), _ev(e[3], rec)
    o = e[1]
    if o == "+":
        return a + b
    if o == "*":
        return a * b
    if o == "sub":
        return max(a - b, 0)
    if o == "min":
        return min(a, b)
    if o == "max":
        return max(a, b)
    if o == "//":
        return a // b
    if o == "%":
        return a % b
    raise ValueError(o)


def _cmp(op, a, b):
    return {">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b}[op]


def _run_ops(ops, rec):
    for op in ops:
        if op.kind == "set":
            rec[op.dst] = _ev(op.expr, rec)
        elif op.kind == "rename":
            rec[op.dst] = rec.pop(op.src)
        elif op.kind == "default":
            rec.setdefault(op.dst, op.value)
        elif op.kind == "drop":
            rec.pop(op.dst, None)
        else:
            if _cmp(op.cond[0], rec[op.cond[1]], op.cond[2]):
                _run_ops(op.body, rec)


def simulate(flow: Flow, rec: dict) -> dict:
    rec = dict(rec)
    for st in flow.stages:
        _run_ops(st.ops, rec)
    return rec


def lineage(flow: Flow, target: str) -> set:
    """input fields the final value of ``target`` is computed from (data flow plus guarding conditions)"""
    deps = {f: {f} for f in flow.inputs}

    def uni(fs, d):
        out = set()
        for f in fs:
            out |= d.get(f, set())
        return out

    def vars_of(e):
        t = e[0]
        if t == "v":
            return {e[1]}
        if t == "n":
            return set()
        return vars_of(e[2]) | vars_of(e[3])

    def run(ops, d, ctrl):
        for op in ops:
            if op.kind == "set":
                d[op.dst] = uni(vars_of(op.expr), d) | ctrl
            elif op.kind == "rename":
                d[op.dst] = set(d.pop(op.src)) | ctrl
            elif op.kind == "default":
                d[op.dst] = d.get(op.dst, set()) | ctrl
            elif op.kind == "drop":
                d.pop(op.dst, None)
            else:
                cdeps = d.get(op.cond[1], set())
                before = {k: set(v) for k, v in d.items()}
                run(op.body, d, ctrl | cdeps)
                for k in list(d):
                    if k in before and before[k] != d[k]:
                        d[k] = d[k] | before[k]
        return d

    for st in flow.stages:
        run(st.ops, deps, set())
    return deps.get(target, set())


# ---------------------------------------------------------------------------------------------------------------- rendering
def _ex(e, lang: str) -> str:
    t = e[0]
    if t == "n":
        return str(e[1])
    if t == "v":
        return {"python": f'rec["{e[1]}"]', "javascript": f"rec.{e[1]}", "ruby": f"rec[:{e[1]}]"}[lang]
    o = e[1]
    a, b = _ex(e[2], lang), _ex(e[3], lang)
    if o in ("min", "max"):
        return {"python": f"{o}({a}, {b})", "javascript": f"Math.{o}({a}, {b})", "ruby": f"[{a}, {b}].{o}"}[lang]
    if o == "sub":
        return {"python": f"max({a} - {b}, 0)", "javascript": f"Math.max({a} - {b}, 0)", "ruby": f"[{a} - {b}, 0].max"}[lang]
    if o == "//":
        return {"python": f"({a}) // {b}", "javascript": f"Math.floor(({a}) / {b})", "ruby": f"({a}) / {b}"}[lang]
    if o == "%":
        return f"({a}) % {b}"
    return f"({a} {o} {b})"


def _ops(ops, lang, ind):
    out = []
    pad = "  " * ind if lang != "python" else "    " * ind
    for op in ops:
        if op.kind == "set":
            if lang == "python":
                out.append(f'{pad}rec["{op.dst}"] = {_ex(op.expr, lang)}')
            elif lang == "javascript":
                out.append(f"{pad}rec.{op.dst} = {_ex(op.expr, lang)};")
            else:
                out.append(f"{pad}rec[:{op.dst}] = {_ex(op.expr, lang)}")
        elif op.kind == "rename":
            if lang == "python":
                out.append(f'{pad}rec["{op.dst}"] = rec.pop("{op.src}")')
            elif lang == "javascript":
                out += [f"{pad}rec.{op.dst} = rec.{op.src};", f"{pad}delete rec.{op.src};"]
            else:
                out.append(f"{pad}rec[:{op.dst}] = rec.delete(:{op.src})")
        elif op.kind == "default":
            if lang == "python":
                out.append(f'{pad}rec.setdefault("{op.dst}", {op.value})')
            elif lang == "javascript":
                out += [f"{pad}if (!('{op.dst}' in rec)) {{", f"{pad}  rec.{op.dst} = {op.value};", f"{pad}}}"]
            else:
                out.append(f"{pad}rec[:{op.dst}] ||= {op.value}")
        elif op.kind == "drop":
            if lang == "python":
                out.append(f'{pad}rec.pop("{op.dst}", None)')
            elif lang == "javascript":
                out.append(f"{pad}delete rec.{op.dst};")
            else:
                out.append(f"{pad}rec.delete(:{op.dst})")
        else:
            cf = _ex(("v", op.cond[1]), lang)
            if lang == "python":
                out.append(f"{pad}if {cf} {op.cond[0]} {op.cond[2]}:")
                out += _ops(op.body, lang, ind + 1)
            elif lang == "javascript":
                out.append(f"{pad}if ({cf} {op.cond[0]} {op.cond[2]}) {{")
                out += _ops(op.body, lang, ind + 1)
                out.append(f"{pad}}}")
            else:
                out.append(f"{pad}if {cf} {op.cond[0]} {op.cond[2]}")
                out += _ops(op.body, lang, ind + 1)
                out.append(f"{pad}end")
    return out


def render(fl: Flow) -> dict:
    lang = fl.lang
    files = {}
    if lang == "python":
        for st in fl.stages:
            files[f"{fl.pkg}/stages/{st.name}.py"] = f'"""The {st.name} stage."""\n\n\ndef apply(rec):\n    """Update the record in place and return it."""\n' + "\n".join(_ops(st.ops, lang, 1)) + "\n    return rec\n"
        files[f"{fl.pkg}/stages/__init__.py"] = ""
        imps = "\n".join(f"from .stages import {st.name}" for st in fl.stages)
        files[f"{fl.pkg}/__init__.py"] = f'"""{fl.title}: one record in, one record out."""\n{imps}\n\nPIPELINE = [{", ".join(st.name for st in fl.stages)}]\n\n\ndef run(record):\n    rec = dict(record)\n    for stage in PIPELINE:\n        rec = stage.apply(rec)\n    return rec\n'
        files["run.py"] = 'import json\nimport sys\n\nfrom ' + fl.pkg + ' import run\n\nprint(json.dumps(run(json.loads(sys.argv[1])), sort_keys=True))\n'
        cmd = "python3 run.py"
    elif lang == "javascript":
        for st in fl.stages:
            files[f"src/stages/{st.name}.js"] = f"'use strict';\n\n/** The {st.name} stage: updates the record in place and returns it. */\nfunction apply(rec) {{\n" + "\n".join(_ops(st.ops, lang, 1)) + "\n  return rec;\n}\n\nmodule.exports = { apply };\n"
        reqs = "\n".join(f"const {st.name} = require('./stages/{st.name}');" for st in fl.stages)
        files["src/index.js"] = f"'use strict';\n\n{reqs}\n\nconst PIPELINE = [{', '.join(st.name for st in fl.stages)}];\n\nfunction run(record) {{\n  let rec = {{ ...record }};\n  for (const stage of PIPELINE) {{\n    rec = stage.apply(rec);\n  }}\n  return rec;\n}}\n\nmodule.exports = {{ run, PIPELINE }};\n"
        files["run.js"] = "'use strict';\n\nconst { run } = require('./src');\n\nconst out = run(JSON.parse(process.argv[2]));\nconst sorted = Object.fromEntries(Object.entries(out).sort(([a], [b]) => (a < b ? -1 : 1)));\nconsole.log(JSON.stringify(sorted));\n"
        cmd = "node run.js"
    else:
        for st in fl.stages:
            files[f"lib/{fl.pkg}/stages/{st.name}.rb"] = f"# frozen_string_literal: true\n\nmodule {fl.pkg.capitalize()}\n  module Stages\n    # The {st.name} stage: updates the record in place and returns it.\n    module {st.name.capitalize().replace('_o', 'O')}\n      def self.apply(rec)\n" + "\n".join("    " + ln if ln else ln for ln in _ops(st.ops, lang, 3)) + "\n        rec\n      end\n    end\n  end\nend\n"
        mods = ", ".join(f"Stages::{st.name.capitalize().replace('_o', 'O')}" for st in fl.stages)
        reqs = "\n".join(f"require_relative '{fl.pkg}/stages/{st.name}'" for st in fl.stages)
        files[f"lib/{fl.pkg}.rb"] = f"# frozen_string_literal: true\n\n{reqs}\n\nmodule {fl.pkg.capitalize()}\n  PIPELINE = [{mods}].freeze\n\n  def self.run(record)\n    rec = record.dup\n    PIPELINE.each {{ |stage| rec = stage.apply(rec) }}\n    rec\n  end\nend\n"
        files["run.rb"] = f"# frozen_string_literal: true\n\nrequire 'json'\nrequire_relative 'lib/{fl.pkg}'\n\nrec = {fl.pkg.capitalize()}.run(JSON.parse(ARGV[0], symbolize_names: true))\nputs JSON.generate(rec.sort.to_h)\n"
        cmd = "ruby run.rb"
    files["README.md"] = f"# {fl.title} record pipeline\n\nEach stage in `stages/` updates a record; the order is the `PIPELINE` list. `{cmd} '<json>'` runs one record through and prints the result.\n"
    return files, cmd


def run_real(fl: Flow, files: dict, cmd: str, rec: dict) -> dict:
    res = fx.run(files, f"{cmd} '{json.dumps(rec)}' 2>&1", timeout=30)
    if not res.ok:
        raise RuntimeError(res.out[-300:])
    return json.loads(res.out.strip().splitlines()[-1])


def random_record(rng, fl: Flow) -> dict:
    return {f: rng.randint(1, 60) for f in fl.inputs}
