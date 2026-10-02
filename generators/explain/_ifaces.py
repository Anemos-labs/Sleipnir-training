"""Interfaces/traits/protocols and the types that satisfy them, in go, rust, java and python.

Truth by construction: go uses structural method sets (value vs pointer receivers, exact signatures, struct embedding),
rust uses explicit ``impl`` blocks with supertraits and one blanket impl, java is nominal (extends/implements, transitively),
python runs ``isinstance`` against ``Protocol`` (structural, names only) and ABC (nominal + ``register``) classes.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

import fx

from . import _ir as I

# (name, params, ret)
METHOD_POOL = [("fee", [], "int"), ("weight", [], "int"), ("label", [], "string"), ("capacity", [], "int"), ("valid", [], "bool"),
               ("scale", ["int"], "int"), ("describe", [], "string"), ("reset", [], "bool"), ("rank", [], "int"), ("code", [], "string")]
IFACE_NAMES = ["Billable", "Weighable", "Labelled", "Sized", "Checkable", "Scalable", "Describer", "Resettable", "Ranked", "Coded"]
TYPE_PREFIX = ["Heavy", "Light", "Night", "Day", "Guest", "Fixed", "Quick", "Grand", "Mini", "Lone", "Open", "Sealed", "Long", "Short", "Early", "Late"]


@dataclass
class Meth:
    name: str
    params: list
    ret: str
    ptr: bool = False


@dataclass
class Iface:
    name: str
    methods: list                       # [Meth]
    embeds: list = field(default_factory=list)


@dataclass
class Typ:
    name: str
    methods: list = field(default_factory=list)       # own methods [Meth]
    embeds: list = field(default_factory=list)        # go: embedded struct types; java/python: parent class
    declares: list = field(default_factory=list)      # java implements / rust impl / python bases
    registered: list = field(default_factory=list)    # python ABC.register


@dataclass
class Model:
    lang: str
    ifaces: list
    types: list
    pkg: str
    noun: str
    style: str = ""       # python: "protocol" | "abc"


def _sig_variant(rng, m: Meth) -> Meth:
    """a near miss: same name, different return type or parameters"""
    alt = {"int": "string", "string": "int", "bool": "int"}[m.ret]
    if m.params and rng.random() < 0.5:
        return Meth(m.name, [], m.ret, m.ptr)
    return Meth(m.name, m.params, alt, m.ptr)


def make_model(rng: random.Random, lang: str, tier: int) -> Model:
    dom = rng.choice(I.DOMAINS)
    noun = rng.choice(dom.nouns).capitalize()
    n_if = {1: 2, 2: 2, 3: 3, 4: 4, 5: 5}[tier]
    n_ty = {1: 4, 2: 5, 3: 7, 4: 9, 5: 12}[tier]
    pool = rng.sample(METHOD_POOL, min(len(METHOD_POOL), n_if + 3))
    inames = rng.sample(IFACE_NAMES, n_if)
    ifaces = []
    for k, nm in enumerate(inames):
        ms = rng.sample(pool, rng.randint(1, 2))
        ifaces.append(Iface(nm, [Meth(*m) for m in ms]))
    # embedding / extension of interfaces
    if tier >= 3 and len(ifaces) >= 3:
        ifaces[-1].embeds = [ifaces[0].name]
    if tier >= 4 and len(ifaces) >= 4:
        ifaces[-2].embeds = [ifaces[1].name]
    prefixes = rng.sample(TYPE_PREFIX, n_ty)
    types = []
    for p in prefixes:
        t = Typ(f"{p}{noun}")
        chosen = rng.sample(ifaces, rng.randint(0, min(3, len(ifaces))))
        want = {}
        for i in chosen:
            for m in _all_methods(ifaces, i):
                want[(m.name)] = m
        for m in want.values():
            ptr = lang == "go" and rng.random() < 0.35
            t.methods.append(Meth(m.name, list(m.params), m.ret, ptr))
        # near misses and strays
        if rng.random() < 0.45:
            m = rng.choice(pool)
            if all(x.name != m[0] for x in t.methods):
                t.methods.append(_sig_variant(rng, Meth(*m)))
        if rng.random() < 0.4:
            m = rng.choice(pool)
            if all(x.name != m[0] for x in t.methods):
                t.methods.append(Meth(*m, ptr=(lang == "go" and rng.random() < 0.3)))
        types.append(t)
    mdl = Model(lang, ifaces, types, dom.name, noun)
    if lang == "go" and tier >= 4:
        # one struct embeds another and gets its value methods promoted
        a, b = rng.sample(types, 2)
        if not b.embeds and a.methods:
            b.embeds = [a.name]
    if lang == "java":
        # nominal: declared interfaces (only some of the structurally matching ones), plus inheritance between classes
        for t in types:
            for i in ifaces:
                if _satisfies_structurally(mdl, t, i) and rng.random() < 0.55:
                    t.declares.append(i.name)
        if tier >= 3:
            a, b = rng.sample(types, 2)
            b.embeds = [a.name]
            # an override may not change the signature of an inherited method: drop such methods from the child
            inherited = {}
            for anc in _chain(types, b):
                for m in anc.methods:
                    inherited.setdefault(m.name, m)
            b.methods = [m for m in b.methods if m.name not in inherited or (inherited[m.name].params == m.params and inherited[m.name].ret == m.ret)]
        # every declared interface must be fully implemented: add the missing methods
        for t in types:
            have = {m.name for m in t.methods}
            for iname in list(t.declares):
                for m in _all_methods(ifaces, _find(ifaces, iname)):
                    if m.name not in have and not _inherits(types, t, m.name, m):
                        t.methods.append(Meth(m.name, list(m.params), m.ret))
                        have.add(m.name)
    if lang == "rust":
        # explicit impls; a supertrait must be implemented too
        for t in types:
            for i in ifaces:
                if rng.random() < 0.4:
                    t.declares.append(i.name)
        for t in types:
            for iname in list(t.declares):
                for e in _find(ifaces, iname).embeds:
                    if e not in t.declares:
                        t.declares.append(e)
    if lang == "python":
        mdl.style = rng.choice(["protocol", "abc"])
        if mdl.style == "abc":
            for t in types:
                for i in ifaces:
                    if rng.random() < 0.35:
                        t.declares.append(i.name)
                    elif rng.random() < 0.1:
                        t.registered.append(i.name)
            for t in types:
                # a base that is already an ancestor of another declared base would break the MRO
                t.declares = [d for d in t.declares if not any(d in _ancestors_iface(mdl, o) for o in t.declares if o != d)]
                have = {m.name for m in t.methods}
                for iname in t.declares:
                    for m in _all_methods(ifaces, _find(ifaces, iname)):
                        if m.name not in have:
                            t.methods.append(Meth(m.name, list(m.params), m.ret))
                            have.add(m.name)
    return mdl


def _find(ifaces, name):
    return next(i for i in ifaces if i.name == name)


def _all_methods(ifaces, i: Iface) -> list:
    out = list(i.methods)
    for e in i.embeds:
        out += _all_methods(ifaces, _find(ifaces, e))
    return out


def _chain(types, t: Typ) -> list:
    out = []
    for e in t.embeds:
        p = next(x for x in types if x.name == e)
        out.append(p)
        out += _chain(types, p)
    return out


def _inherits(types, t: Typ, mname: str, req: "Meth | None" = None) -> bool:
    for p in _chain(types, t):
        for m in p.methods:
            if m.name == mname and (req is None or (m.params == req.params and m.ret == req.ret)):
                return True
    return False


def resolve_methods(mdl: Model, t: Typ) -> dict:
    """go selector resolution: own methods shadow promoted ones; name -> Meth (with its receiver kind)"""
    out = {m.name: m for m in t.methods}
    for e in t.embeds:
        p = next(x for x in mdl.types if x.name == e)
        for name, m in resolve_methods(mdl, p).items():
            out.setdefault(name, m)
    return out


def method_set(mdl: Model, t: Typ, pointer: bool = False) -> list:
    """go method set of T (value) or *T (pointer)"""
    return [m for m in resolve_methods(mdl, t).values() if pointer or not m.ptr]


def _satisfies_structurally(mdl: Model, t: Typ, i: Iface, pointer: bool = False) -> bool:
    ms = method_set(mdl, t, pointer)
    for req in _all_methods(mdl.ifaces, i):
        if not any(m.name == req.name and m.params == req.params and m.ret == req.ret for m in ms):
            return False
    return True


def implementers(mdl: Model, iname: str, pointer: bool = False) -> list:
    i = _find(mdl.ifaces, iname)
    if mdl.lang == "go":
        return sorted(t.name for t in mdl.types if _satisfies_structurally(mdl, t, i, pointer))
    if mdl.lang == "java":
        out = []
        for t in mdl.types:
            if _java_is(mdl, t, iname):
                out.append(t.name)
        return sorted(out)
    if mdl.lang == "rust":
        return sorted(t.name for t in mdl.types if iname in t.declares)
    raise ValueError(mdl.lang)


def _java_is(mdl: Model, t: Typ, iname: str) -> bool:
    for d in t.declares:
        if d == iname or iname in _ancestors_iface(mdl, d):
            return True
    for e in t.embeds:
        p = next(x for x in mdl.types if x.name == e)
        if _java_is(mdl, p, iname):
            return True
    return False


def _ancestors_iface(mdl: Model, name: str) -> list:
    out = []
    for e in _find(mdl.ifaces, name).embeds:
        out.append(e)
        out += _ancestors_iface(mdl, e)
    return out


# ---------------------------------------------------------------------------------------------------------------- renderers
GO_T = {"int": "int", "string": "string", "bool": "bool"}
RUST_T = {"int": "i64", "string": "String", "bool": "bool"}
JAVA_T = {"int": "int", "string": "String", "bool": "boolean"}
PY_T = {"int": "int", "string": "str", "bool": "bool"}


def _zero(ret: str, lang: str, k: int) -> str:
    if ret == "int":
        return str(k)
    if ret == "bool":
        return {"go": "true", "rust": "true", "java": "true", "python": "True"}[lang]
    return {"go": f'"v{k}"', "rust": f'"v{k}".to_string()', "java": f'"v{k}"', "python": f'"v{k}"'}[lang]


def render(mdl: Model) -> dict:
    return {"go": _go, "rust": _rust, "java": _java, "python": _py}[mdl.lang](mdl)


def _go(mdl: Model) -> dict:
    pkg = mdl.pkg
    files = {"go.mod": f"module example.com/{pkg}\n\ngo 1.21\n"}
    lines = [f"// Package {pkg} models {mdl.noun.lower()} capabilities.", f"package {pkg}", ""]
    for i in mdl.ifaces:
        lines.append(f"// {i.name} is implemented by anything that offers the listed capabilities.")
        lines.append(f"type {i.name} interface {{")
        for e in i.embeds:
            lines.append(f"\t{e}")
        for m in i.methods:
            ps = ", ".join(f"x {GO_T[p]}" for p in m.params)
            lines.append(f"\t{m.name.capitalize()}({ps}) {GO_T[m.ret]}")
        lines.append("}")
        lines.append("")
    files[f"{pkg}/ifaces.go"] = "\n".join(lines)
    lines = [f"package {pkg}", ""]
    k = 3
    for t in mdl.types:
        lines.append(f"// {t.name} is one kind of {mdl.noun.lower()}.")
        lines.append(f"type {t.name} struct {{")
        for e in t.embeds:
            lines.append(f"\t{e}")
        lines.append("\tID int")
        lines.append("}")
        lines.append("")
        for m in t.methods:
            recv = f"(t *{t.name})" if m.ptr else f"(t {t.name})"
            ps = ", ".join(f"x {GO_T[p]}" for p in m.params)
            k += 2
            lines.append(f"func {recv} {m.name.capitalize()}({ps}) {GO_T[m.ret]} {{")
            lines.append(f"\treturn {_zero(m.ret, 'go', k)}" if not m.params or m.ret != "int" else f"\treturn x + {k}")
            lines.append("}")
            lines.append("")
    files[f"{pkg}/types.go"] = "\n".join(lines)
    files["README.md"] = f"# {pkg}\n\nCapability interfaces and the {mdl.noun.lower()} types of the {pkg} model.\n"
    return files


def _rust(mdl: Model) -> dict:
    pkg = mdl.pkg
    files = {"Cargo.toml": f'[package]\nname = "{pkg}"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n', "src/lib.rs": "pub mod traits;\npub mod types;\n"}
    lines = ["//! Capability traits."]
    for i in mdl.ifaces:
        sup = f": {' + '.join(i.embeds)}" if i.embeds else ""
        lines += ["", f"/// {i.name}: implemented by the types that offer these capabilities.", f"pub trait {i.name}{sup} {{"]
        for m in i.methods:
            ps = "".join(f", x: {RUST_T[p]}" for p in m.params)
            lines.append(f"    fn {m.name}(&self{ps}) -> {RUST_T[m.ret]};")
        lines.append("}")
    files["src/traits.rs"] = "\n".join(lines) + "\n"
    lines = ["//! The types.", "", "use crate::traits::*;"]
    k = 3
    for t in mdl.types:
        lines += ["", f"/// {t.name} is one kind of {mdl.noun.lower()}.", "pub struct " + t.name + " {", "    pub id: i64,", "}"]
        for iname in t.declares:
            i = _find(mdl.ifaces, iname)
            lines += ["", f"impl {iname} for {t.name} {{"]
            for m in i.methods:
                ps = "".join(f", x: {RUST_T[p]}" for p in m.params)
                k += 2
                body = f"x + {k}" if m.params and m.ret == "int" else _zero(m.ret, "rust", k)
                lines.append(f"    fn {m.name}(&self{ps}) -> {RUST_T[m.ret]} {{")
                lines.append(f"        {body}")
                lines.append("    }")
            lines.append("}")
        own = [m for m in t.methods]
        if own:
            lines += ["", f"impl {t.name} {{"]
            for m in own:
                ps = "".join(f", x: {RUST_T[p]}" for p in m.params)
                k += 2
                body = f"x + {k}" if m.params and m.ret == "int" else _zero(m.ret, "rust", k)
                lines.append(f"    pub fn {m.name}(&self{ps}) -> {RUST_T[m.ret]} {{")
                lines.append(f"        {body}")
                lines.append("    }")
            lines.append("}")
    files["src/types.rs"] = "\n".join(lines) + "\n"
    files["README.md"] = f"# {pkg}\n\nCapability traits and the {mdl.noun.lower()} types of the {pkg} model.\n"
    return files


def _java(mdl: Model) -> dict:
    pkg = mdl.pkg
    files = {}
    for i in mdl.ifaces:
        lines = [f"package {pkg};", "", f"/** {i.name}: implemented by the classes that offer these capabilities. */",
                 f"public interface {i.name}" + (f" extends {', '.join(i.embeds)}" if i.embeds else "") + " {"]
        for m in i.methods:
            ps = ", ".join(f"{JAVA_T[p]} x" for p in m.params)
            lines.append(f"    {JAVA_T[m.ret]} {m.name}({ps});")
        lines.append("}")
        files[f"src/{pkg}/{i.name}.java"] = "\n".join(lines) + "\n"
    k = 3
    for t in mdl.types:
        head = f"public class {t.name}"
        if t.embeds:
            head += f" extends {t.embeds[0]}"
        if t.declares:
            head += f" implements {', '.join(t.declares)}"
        lines = [f"package {pkg};", "", f"/** One kind of {mdl.noun.lower()}. */", head + " {"]
        for m in t.methods:
            ps = ", ".join(f"{JAVA_T[p]} x" for p in m.params)
            k += 2
            body = f"x + {k}" if m.params and m.ret == "int" else _zero(m.ret, "java", k)
            lines += ["", f"    public {JAVA_T[m.ret]} {m.name}({ps}) {{", f"        return {body};", "    }"]
        lines.append("}")
        files[f"src/{pkg}/{t.name}.java"] = "\n".join(lines) + "\n"
    files[f"src/{pkg}/Main.java"] = f"package {pkg};\n\npublic class Main {{\n    public static void main(String[] args) {{\n        System.out.println(\"{mdl.noun} model loaded\");\n    }}\n}}\n"
    files["README.md"] = f"# {pkg}\n\nCapability interfaces and the {mdl.noun.lower()} classes of the {pkg} model.\n"
    return files


def _py(mdl: Model) -> dict:
    pkg = mdl.pkg
    files = {f"{pkg}/__init__.py": ""}
    lines = ['"""Capability interfaces."""', ""]
    if mdl.style == "protocol":
        lines += ["from typing import Protocol, runtime_checkable", ""]
    else:
        lines += ["from abc import ABC, abstractmethod", ""]
    for i in mdl.ifaces:
        lines += ["", ""]
        if mdl.style == "protocol":
            lines.append("@runtime_checkable")
            bases = ", ".join(i.embeds + ["Protocol"])
            lines.append(f"class {i.name}({bases}):")
        else:
            bases = ", ".join(i.embeds + ["ABC"])
            lines.append(f"class {i.name}({bases}):")
        lines.append(f'    """{i.name}: implemented by the classes that offer these capabilities."""')
        for m in i.methods:
            ps = "".join(f", x: {PY_T[p]}" for p in m.params)
            if mdl.style == "abc":
                lines += ["", "    @abstractmethod"]
            else:
                lines.append("")
            lines.append(f"    def {m.name}(self{ps}) -> {PY_T[m.ret]}:")
            lines.append("        ...")
    files[f"{pkg}/ifaces.py"] = "\n".join(lines) + "\n"
    lines = ['"""The concrete types."""', "", "from .ifaces import " + ", ".join(i.name for i in mdl.ifaces)]
    k = 3
    for t in mdl.types:
        bases = list(t.embeds) + (list(t.declares) if mdl.style == "abc" else [])
        lines += ["", "", f"class {t.name}" + (f"({', '.join(bases)})" if bases else "") + ":", f'    """One kind of {mdl.noun.lower()}."""']
        if not t.methods:
            lines.append("    pass")
        for m in t.methods:
            ps = "".join(f", x: {PY_T[p]}" for p in m.params)
            k += 2
            body = f"x + {k}" if m.params and m.ret == "int" else _zero(m.ret, "python", k)
            lines += ["", f"    def {m.name}(self{ps}) -> {PY_T[m.ret]}:", f"        return {body}"]
    if mdl.style == "abc":
        reg = [(i, t) for t in mdl.types for i in t.registered]
        for i, t in [(r, t) for t in mdl.types for r in t.registered]:
            lines += ["", f"{i}.register({t.name})"]
    files[f"{pkg}/types.py"] = "\n".join(lines) + "\n"
    files["README.md"] = f"# {pkg}\n\nCapability interfaces and the {mdl.noun.lower()} types of the {pkg} model.\n"
    return files


def python_implementers(mdl: Model, files: dict, iname: str) -> list:
    """truth for python: ask the interpreter"""
    ts = ", ".join(t.name for t in mdl.types)
    probe = (f"from {mdl.pkg}.types import {ts}\nfrom {mdl.pkg}.ifaces import {iname}\n"
             f"names = [{', '.join(repr(t.name) for t in mdl.types)}]\nclasses = [{ts}]\n"
             f"print(sorted(n for n, c in zip(names, classes) if isinstance(c(), {iname})))\n")
    res = fx.run({**files, "_probe.py": probe}, "python3 _probe.py", timeout=30)
    if not res.ok:
        raise RuntimeError(res.out)
    return eval(res.out.strip().splitlines()[-1])
