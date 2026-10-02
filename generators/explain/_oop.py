"""Small class hierarchies rendered in python, javascript, java and ruby. The answer (which method bodies run, in which order, and
what is returned) is obtained by actually running the generated program.

Every method logs ``Class.method`` on entry and returns the sum of its parts: constants, the parent implementation (``super``)
and virtual calls on ``self`` to a method with a higher index, so everything terminates.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

import fx

from . import _ir as I

PREFIXES = ["Heavy", "Light", "Night", "Day", "Guest", "Fixed", "Quick", "Grand", "Mini", "Lone", "Open", "Sealed", "Long", "Short", "Early", "Late"]
METHOD_SETS = [["price", "surcharge", "tax", "rounding"], ["label", "prefix", "suffix", "width"], ["capacity", "reserve", "buffer", "margin"],
               ["score", "bonus", "penalty", "cap"], ["rate", "base", "extra", "floor"], ["load", "tare", "pad", "limit"]]
MODS = ["Audited", "Metered", "Cached", "Tracked", "Capped", "Rounded"]


@dataclass
class Cls:
    name: str
    base: str = ""                 # single parent ("" for the root)
    bases: list = field(default_factory=list)   # python: several parents
    mixins: list = field(default_factory=list)  # ruby: [(module name, "include" | "prepend")]
    methods: dict = field(default_factory=dict)  # name -> ops
    is_module: bool = False
    module: str = ""               # file group


@dataclass
class Hier:
    lang: str
    classes: list
    mro_note: str
    method_names: list
    entry_cls: str
    entry_method: str
    pkg: str
    domain_noun: str


def _ops(rng: random.Random, mnames: list, idx: int, has_super: bool, allow_self: bool = True) -> list:
    """one to three steps: constants, at most one super call and at most one virtual self call (keeps traces short)"""
    can_self = allow_self and idx + 1 < len(mnames)
    ops: list = []
    k = rng.randint(1, 3)
    kinds = ["add"]
    if has_super:
        kinds += ["super", "super"]
    if can_self:
        kinds += ["self"]
    chosen = [rng.choice(kinds) for _ in range(k)]
    seen_super = seen_self = False
    for c in chosen:
        if c == "super":
            if seen_super:
                c = "add"
            seen_super = True
        elif c == "self":
            if seen_self:
                c = "add"
            seen_self = True
        if c == "add":
            ops.append(("add", rng.choice([1, 2, 3, 5, 7, 10, 20])))
        elif c == "super":
            ops.append(("super",))
        else:
            ops.append(("self", mnames[rng.randint(idx + 1, len(mnames) - 1)]))
    if has_super and not seen_super and rng.random() < 0.7:
        ops.insert(rng.randint(0, len(ops)), ("super",))
    return ops


def make_hier(rng: random.Random, lang: str, tier: int) -> Hier:
    dom = rng.choice(I.DOMAINS)
    noun = rng.choice(dom.nouns)
    root_name = noun.capitalize()
    mnames = list(rng.choice(METHOD_SETS))
    prefixes = rng.sample(PREFIXES, 8)
    names = [f"{p}{root_name}" for p in prefixes]
    root = Cls(root_name)
    for i, m in enumerate(mnames):
        root.methods[m] = _ops(rng, mnames, i, False)
        if not root.methods[m] or all(o[0] != "add" for o in root.methods[m]):
            root.methods[m].append(("add", rng.choice([1, 2, 5])))
    classes = [root]
    n_sub = {1: 1, 2: 2, 3: 3, 4: 5, 5: 7}[tier]
    structure = "chain" if tier <= 2 else rng.choice(["tree", "chain", "tree"])
    diamond = lang == "python" and tier >= 4 and rng.random() < 0.8
    modules = []
    if lang == "ruby" and tier >= 3:
        for mn in rng.sample(MODS, 1 if tier == 3 else 2):
            md = Cls(f"{mn}", is_module=True)
            for m in rng.sample(mnames[:-1] if len(mnames) > 2 else mnames, rng.randint(1, 2)):
                md.methods[m] = _ops(rng, mnames, mnames.index(m), True)
            modules.append(md)
    pool = [root]
    for i in range(n_sub):
        nm = names[i]
        if diamond and i == 2:
            b1, b2 = classes[1], classes[2]
            c = Cls(nm, bases=[b1.name, b2.name])
        else:
            parent = pool[-1] if structure == "chain" else rng.choice(pool)
            if diamond and i in (0, 1):
                parent = root
            c = Cls(nm, base=parent.name, bases=[parent.name])
        for j, m in enumerate(mnames):
            if rng.random() < (0.55 if tier >= 3 else 0.7):
                c.methods[m] = _ops(rng, mnames, j, True)
        if not c.methods:
            j = rng.randrange(len(mnames))
            c.methods[mnames[j]] = _ops(rng, mnames, j, True)
        classes.append(c)
        pool.append(c)
    for md in modules:
        target = rng.choice([c for c in classes[1:]])
        target.mixins.append((md.name, "prepend" if (tier >= 4 and rng.random() < 0.5) else "include"))
    classes = classes + modules
    leaves = [c for c in classes if not c.is_module and not any(c.name in o.bases for o in classes if not o.is_module)]
    entry = rng.choice(leaves)
    # entry method: a low index method so that self-calls matter
    entry_m = mnames[rng.randint(0, max(0, len(mnames) - 2))]
    return Hier(lang=lang, classes=classes, mro_note="", method_names=mnames, entry_cls=entry.name, entry_method=entry_m, pkg=dom.name, domain_noun=noun)


# ---------------------------------------------------------------------------------------------------------------- renderers
def _group(h: Hier) -> list:
    """split the classes into files: root + module files first"""
    cls = [c for c in h.classes if not c.is_module]
    mods = [c for c in h.classes if c.is_module]
    return [cls[:1], cls[1:3], cls[3:]] + [mods] if mods else [cls[:1], cls[1:3], cls[3:]]


def render(h: Hier) -> dict:
    return {"python": _py, "javascript": _js, "java": _java, "ruby": _rb}[h.lang](h)


def _body_py(c: Cls, m: str, ops: list, ind: str = "        ") -> list:
    out = [f"{ind}log(\"{c.name}.{m}\")", f"{ind}total = 0"]
    for o in ops:
        if o[0] == "add":
            out.append(f"{ind}total += {o[1]}")
        elif o[0] == "super":
            out.append(f"{ind}total += super().{m}()")
        else:
            out.append(f"{ind}total += self.{o[1]}()")
    out.append(f"{ind}return total")
    return out


def _py(h: Hier) -> dict:
    p = h.pkg
    files = {f"{p}/__init__.py": "", f"{p}/log.py": 'CALLS = []\n\n\ndef log(entry):\n    """Record that a method body started running."""\n    CALLS.append(entry)\n'}
    groups = [g for g in _group(h) if g]
    modnames = ["base", "kinds", "extras"][: len(groups)]
    where = {}
    for gi, g in enumerate(groups):
        for c in g:
            where[c.name] = modnames[gi]
    for gi, g in enumerate(groups):
        lines = [f'"""{modnames[gi].capitalize()} classes of the {h.domain_noun} model."""', "", "from .log import log"]
        imps = {}
        for c in g:
            for b in c.bases:
                if where[b] != modnames[gi]:
                    imps.setdefault(where[b], set()).add(b)
        for mn, names in sorted(imps.items()):
            lines.append(f"from .{mn} import {', '.join(sorted(names))}")
        for c in g:
            lines += ["", ""]
            bases = ", ".join(c.bases)
            lines.append(f"class {c.name}({bases}):" if bases else f"class {c.name}:")
            first = True
            for m, ops in c.methods.items():
                if not first:
                    lines.append("")
                first = False
                lines.append(f"    def {m}(self):")
                lines += _body_py(c, m, ops)
        files[f"{p}/{modnames[gi]}.py"] = "\n".join(lines) + "\n"
    entry = h.entry_cls
    files[f"{p}/__main__.py"] = (f"from .log import CALLS\nfrom .{where[entry]} import {entry}\n\n\ndef main():\n    obj = {entry}()\n    value = obj.{h.entry_method}()\n"
                                 f"    for entry in CALLS:\n        print(entry)\n    print(value)\n\n\nmain()\n")
    files["README.md"] = f"# {h.domain_noun.capitalize()} model\n\nA small class hierarchy; `python3 -m {p}` builds one object, calls one method and prints which method bodies ran, then the result.\n"
    return files


def _body_js(c: Cls, m: str, ops: list, ind: str = "    ") -> list:
    out = [f"{ind}log('{c.name}.{m}');", f"{ind}let total = 0;"]
    for o in ops:
        if o[0] == "add":
            out.append(f"{ind}total += {o[1]};")
        elif o[0] == "super":
            out.append(f"{ind}total += super.{m}();")
        else:
            out.append(f"{ind}total += this.{o[1]}();")
    out.append(f"{ind}return total;")
    return out


def _js(h: Hier) -> dict:
    files = {"src/log.js": "'use strict';\n\nconst CALLS = [];\n\n/** Record that a method body started running. */\nfunction log(entry) {\n  CALLS.push(entry);\n}\n\nmodule.exports = { CALLS, log };\n"}
    groups = [g for g in _group(h) if g]
    modnames = ["base", "kinds", "extras"][: len(groups)]
    where = {c.name: modnames[gi] for gi, g in enumerate(groups) for c in g}
    for gi, g in enumerate(groups):
        lines = ["'use strict';", "", "const { log } = require('./log');"]
        imps = {}
        for c in g:
            if c.base and where[c.base] != modnames[gi]:
                imps.setdefault(where[c.base], set()).add(c.base)
        for mn, names in sorted(imps.items()):
            lines.append(f"const {{ {', '.join(sorted(names))} }} = require('./{mn}');")
        for c in g:
            lines.append("")
            lines.append(f"class {c.name}" + (f" extends {c.base}" if c.base else "") + " {")
            first = True
            for m, ops in c.methods.items():
                if not first:
                    lines.append("")
                first = False
                lines.append(f"  {m}() {{")
                lines += _body_js(c, m, ops)
                lines.append("  }")
            lines.append("}")
        lines += ["", "module.exports = { " + ", ".join(c.name for c in g) + " };"]
        files[f"src/{modnames[gi]}.js"] = "\n".join(lines) + "\n"
    e = h.entry_cls
    files["src/main.js"] = (f"'use strict';\n\nconst {{ CALLS }} = require('./log');\nconst {{ {e} }} = require('./{where[e]}');\n\nconst obj = new {e}();\nconst value = obj.{h.entry_method}();\n"
                            f"for (const entry of CALLS) {{\n  console.log(entry);\n}}\nconsole.log(value);\n")
    files["package.json"] = f'{{\n  "name": "{h.pkg}",\n  "version": "1.0.0",\n  "scripts": {{ "start": "node src/main.js" }}\n}}\n'
    files["README.md"] = f"# {h.domain_noun.capitalize()} model\n\nA small class hierarchy; `node src/main.js` builds one object, calls one method and prints which method bodies ran, then the result.\n"
    return files


def _java(h: Hier) -> dict:
    p = h.pkg
    files = {f"src/{p}/Log.java": f"package {p};\n\nimport java.util.ArrayList;\nimport java.util.List;\n\n/** Records which method bodies ran. */\npublic final class Log {{\n    public static final List<String> CALLS = new ArrayList<>();\n\n    private Log() {{\n    }}\n\n    public static void add(String entry) {{\n        CALLS.add(entry);\n    }}\n}}\n"}
    for c in h.classes:
        if c.is_module:
            continue
        lines = [f"package {p};", "", f"public class {c.name}" + (f" extends {c.base}" if c.base else "") + " {"]
        first = True
        for m, ops in c.methods.items():
            if not first:
                lines.append("")
            first = False
            if c.base:
                lines.append("    @Override")
            lines.append(f"    public int {m}() {{")
            lines.append(f'        Log.add("{c.name}.{m}");')
            lines.append("        int total = 0;")
            for o in ops:
                if o[0] == "add":
                    lines.append(f"        total += {o[1]};")
                elif o[0] == "super":
                    lines.append(f"        total += super.{m}();")
                else:
                    lines.append(f"        total += {o[1]}();")
            lines.append("        return total;")
            lines.append("    }")
        lines.append("}")
        files[f"src/{p}/{c.name}.java"] = "\n".join(lines) + "\n"
    files[f"src/{p}/Main.java"] = (f"package {p};\n\npublic class Main {{\n    public static void main(String[] args) {{\n        {h.entry_cls} obj = new {h.entry_cls}();\n        int value = obj.{h.entry_method}();\n"
                                   f"        for (String entry : Log.CALLS) {{\n            System.out.println(entry);\n        }}\n        System.out.println(value);\n    }}\n}}\n")
    files["README.md"] = f"# {h.domain_noun.capitalize()} model\n\nA small class hierarchy; `{p}.Main` builds one object, calls one method and prints which method bodies ran, then the result.\n"
    return files


def _rb(h: Hier) -> dict:
    p = h.pkg
    root = p.capitalize()
    files = {f"lib/{p}/log.rb": f"# frozen_string_literal: true\n\nmodule {root}\n  module Log\n    CALLS = []\n\n    def self.add(entry)\n      CALLS << entry\n    end\n  end\nend\n"}
    groups = [g for g in _group(h) if g]
    modnames = ["base", "kinds", "extras", "mixins"][: len(groups)]
    where = {c.name: modnames[gi] for gi, g in enumerate(groups) for c in g}
    for gi, g in enumerate(groups):
        lines = ["# frozen_string_literal: true", "", "require_relative 'log'"]
        deps = set()
        for c in g:
            if c.base and where[c.base] != modnames[gi]:
                deps.add(where[c.base])
            for mn, _ in c.mixins:
                if where[mn] != modnames[gi]:
                    deps.add(where[mn])
        for d in sorted(deps):
            lines.append(f"require_relative '{d}'")
        lines += ["", f"module {root}"]
        for c in g:
            lines.append("")
            if c.is_module:
                lines.append(f"  module {c.name}")
            else:
                lines.append(f"  class {c.name}" + (f" < {c.base}" if c.base else ""))
                for mn, kind in c.mixins:
                    lines.append(f"    {kind} {mn}")
                if c.mixins and c.methods:
                    lines.append("")
            first = True
            for m, ops in c.methods.items():
                if not first:
                    lines.append("")
                first = False
                lines.append(f"    def {m}")
                lines.append(f"      Log.add('{c.name}.{m}')")
                lines.append("      total = 0")
                for o in ops:
                    if o[0] == "add":
                        lines.append(f"      total += {o[1]}")
                    elif o[0] == "super":
                        lines.append("      total += super")
                    else:
                        lines.append(f"      total += {o[1]}")
                lines.append("      total")
                lines.append("    end")
            lines.append("  end")
        lines.append("end")
        files[f"lib/{p}/{modnames[gi]}.rb"] = "\n".join(lines) + "\n"
    reqs = "\n".join(f"require_relative '../lib/{p}/{m}'" for m in modnames)
    files[f"bin/{p}"] = f"#!/usr/bin/env ruby\n# frozen_string_literal: true\n\n{reqs}\n\nobj = {root}::{h.entry_cls}.new\nvalue = obj.{h.entry_method}\n{root}::Log::CALLS.each {{ |entry| puts entry }}\nputs value\n"
    files["README.md"] = f"# {h.domain_noun.capitalize()} model\n\nA small class hierarchy; `ruby bin/{p}` builds one object, calls one method and prints which method bodies ran, then the result.\n"
    return files


RUN = {"python": lambda h: f"python3 -m {h.pkg}", "javascript": lambda h: "node src/main.js",
       "java": lambda h: f"mkdir -p build && javac -d build $(find . -name '*.java') 2>&1 && java -cp build {h.pkg}.Main", "ruby": lambda h: f"ruby bin/{h.pkg}"}


def run_hier(h: Hier, files: dict):
    """(calls, value) from really running the program"""
    res = fx.run(files, RUN[h.lang](h) + " 2>/dev/null", timeout=90)
    lines = [ln for ln in res.out.strip().split("\n") if ln and "JAVA_TOOL_OPTIONS" not in ln]
    if not res.ok or len(lines) < 2:
        raise RuntimeError(f"oop program failed: {res.out[-300:]}")
    return lines[:-1], int(lines[-1])


def cmd_for(h: Hier) -> str:
    return {"python": f"python3 -m {h.pkg}", "javascript": "node src/main.js", "java": f"java -cp build {h.pkg}.Main", "ruby": f"ruby bin/{h.pkg}"}[h.lang]


def ancestors(h: Hier, name: str) -> list:
    """python C3 linearisation (computed here, then cross-checked by importing the generated code)"""
    byname = {c.name: c for c in h.classes}

    def lin(n):
        c = byname[n]
        parents = [b for b in c.bases]
        seqs = [lin(b) for b in parents] + [parents[:]]
        out = [n]
        seqs = [s[:] for s in seqs if s]
        while seqs:
            for s in seqs:
                cand = s[0]
                if not any(cand in t[1:] for t in seqs):
                    break
            else:
                raise RuntimeError("no C3")
            out.append(cand)
            seqs = [[x for x in t if x != cand] for t in seqs]
            seqs = [t for t in seqs if t]
        return out

    return lin(name)


def mro_of(h: Hier, files: dict, name: str) -> list:
    """class linearisation obtained from the running interpreter, restricted to this project's classes and modules"""
    names = {c.name for c in h.classes}
    if h.lang == "python":
        mods = ["base", "kinds", "extras"]
        where = None
        for mn in mods:
            if f"{h.pkg}/{mn}.py" in files and f"class {name}" in files[f"{h.pkg}/{mn}.py"]:
                where = mn
        res = fx.run(files, f'python3 -c "from {h.pkg}.{where} import {name}; print([c.__name__ for c in {name}.__mro__])"', timeout=30)
        out = eval(res.out.strip().splitlines()[-1])
        return [x for x in out if x in names]
    if h.lang == "ruby":
        root = h.pkg.capitalize()
        reqs = "; ".join(f"require_relative 'lib/{h.pkg}/{m}'" for m in ["base", "kinds", "extras", "mixins"] if f"lib/{h.pkg}/{m}.rb" in files)
        res = fx.run(files, f"ruby -e \"{reqs}; puts {root}::{name}.ancestors.map(&:name).join(',')\"", timeout=30)
        out = res.out.strip().splitlines()[-1].split(",")
        return [x.split("::")[-1] for x in out if x.startswith(root + "::") and x.split("::")[-1] in names]
    raise ValueError(h.lang)
