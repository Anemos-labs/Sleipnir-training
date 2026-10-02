"""Re-export puzzles: a package facade re-exports functions from leaf modules (renames, later imports overriding earlier ones,
star imports, try/except fallbacks to a module that does not exist). Every leaf function returns ``path:name`` of its own
definition, so the answer is what the client really prints when it runs."""
from __future__ import annotations

import random

import fx

from . import _ir as I

POOL = ["parse", "render", "load", "dump", "fetch", "encode", "decode", "merge", "split", "format", "scan", "probe", "pack", "seal", "trim", "match"]


def _leaf_names(rng, k, tier):
    """leaf module names and the functions each defines (with deliberate overlaps)"""
    dom = rng.choice(I.DOMAINS)
    mods = rng.sample(dom.nouns, k)
    shared = rng.sample(POOL, {1: 2, 2: 2, 3: 3, 4: 4, 5: 4}[tier])
    defs = {}
    for m in mods:
        names = set(rng.sample(shared, rng.randint(1, min(3, len(shared)))))
        names |= set(rng.sample(POOL, rng.randint(0, 1)))
        defs[m] = sorted(names)
    return dom, mods, defs


# ---------------------------------------------------------------------------------------------------------------- python
def py_case(rng: random.Random, tier: int):
    k = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6}[tier]
    dom, mods, defs = _leaf_names(rng, k, tier)
    pkg = dom.name
    files = {}
    sub = tier >= 4 and rng.random() < 0.7
    where = {}
    for i, m in enumerate(mods):
        folder = f"{pkg}/impl" if (sub and i >= k // 2) else pkg
        where[m] = folder
        path = f"{folder}/{m}.py"
        body = [f'"""{m.capitalize()} helpers."""']
        for n in defs[m]:
            body += ["", "", f"def {n}():", f'    """{n.capitalize()} for {m}."""', f'    return "{path}:{n}"']
        files[path] = "\n".join(body) + "\n"
        if tier >= 3 and rng.random() < 0.35 and len(defs[m]) >= 2:
            files[path] = files[path].replace(f'"""{m.capitalize()} helpers."""', f'"""{m.capitalize()} helpers."""\n\n__all__ = [{", ".join(repr(n) for n in defs[m][:-1])}]')
    all_lists = {m: defs[m][:-1] for m in mods if f"__all__" in files[f"{where[m]}/{m}.py"]}

    def exported(m):
        return all_lists.get(m, defs[m])

    def rel(m, facade_dir):
        return f"{m}" if where[m] == facade_dir else f"impl.{m}"

    lines = [f'"""{dom.title}: public API."""', ""]
    if sub:
        files[f"{pkg}/impl/__init__.py"] = '"""Implementation modules."""\n'
    order = mods[:]
    rng.shuffle(order)
    kinds = ["names"]
    if tier >= 2:
        kinds += ["alias"]
    if tier >= 3:
        kinds += ["star", "names"]
    if tier >= 4:
        kinds += ["try"]
    binding: dict = {}
    first_def: dict = {}
    for m in order:
        kind = rng.choice(kinds)
        r = rel(m, pkg)
        ex = exported(m)
        if kind == "names":
            pick = rng.sample(ex, rng.randint(1, len(ex)))
            lines.append(f"from .{r} import {', '.join(pick)}")
            for n in pick:
                binding[n] = (m, n)
        elif kind == "alias" and ex:
            n = rng.choice(ex)
            other = rng.choice([x for x in POOL if x != n and x not in defs[m]])
            lines.append(f"from .{r} import {n} as {other}")
            binding[other] = (m, n)
        elif kind == "star":
            lines.append(f"from .{r} import *")
            for n in ex:
                binding[n] = (m, n)
        else:  # try / except with a module that is not there
            n = rng.choice(ex)
            ghost = rng.choice(["_fast", "_native", "_speedups"])
            if rng.random() < 0.5:
                # the ghost module exists but lacks the name
                gpath = f"{pkg}/{ghost}.py"
                files[gpath] = f'"""Optional accelerated helpers."""\n\n\ndef warmup():\n    return "{gpath}:warmup"\n'
            lines += ["try:", f"    from .{ghost} import {n}", "except ImportError:", f"    from .{r} import {n}"]
            binding[n] = (m, n)
    files[f"{pkg}/__init__.py"] = "\n".join(lines) + "\n"
    contested = [n for n in binding if sum(1 for m in mods if n in defs[m]) >= 2 or True]
    names = sorted(binding)
    contested = [n for n in names if sum(1 for mm in mods if n in defs[mm]) >= 2]
    renamed = [n for n in names if binding[n][1] != n]
    x = rng.choice(renamed) if (renamed and rng.random() < 0.5) else rng.choice(contested or names)
    m, orig = binding[x]
    path = f"{where[m]}/{m}.py"
    files["app.py"] = (f'"""Client of the {dom.title} package."""\nfrom {pkg} import {x}\n\n\ndef main():\n    print({x}())\n\n\nif __name__ == "__main__":\n    main()\n')
    files["README.md"] = f"# {dom.title}\n\nSmall helper package; `python3 app.py` shows one of its functions at work.\n"
    return files, x, f"{path}:{orig}", "python3 app.py", pkg


# ---------------------------------------------------------------------------------------------------------------- javascript
def js_case(rng: random.Random, tier: int):
    k = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6}[tier]
    dom, mods, defs = _leaf_names(rng, k, tier)
    pkg = dom.name
    files = {}
    for m in mods:
        path = f"lib/{m}.js"
        body = ["'use strict';", ""]
        for n in defs[m]:
            body += [f"/** {n.capitalize()} for {m}. */", f"function {n}() {{", f"  return '{path}:{n}';", "}", ""]
        body.append("module.exports = { " + ", ".join(defs[m]) + " };")
        files[path] = "\n".join(body) + "\n"
    order = mods[:]
    rng.shuffle(order)
    style = {1: "assign", 2: rng.choice(["assign", "spread"]), 3: rng.choice(["spread", "assign", "rename"]), 4: rng.choice(["spread", "try", "rename"]), 5: rng.choice(["spread", "try", "rename"])}[tier]
    binding: dict = {}
    lines = ["'use strict';", ""]
    if style == "assign":
        for m in order:
            lines.append(f"Object.assign(exports, require('./lib/{m}'));")
            for n in defs[m]:
                binding[n] = (m, n)
    elif style == "spread":
        for i, m in enumerate(order):
            lines.append(f"const m{i} = require('./lib/{m}');")
        lines += ["", "module.exports = {"]
        for i, m in enumerate(order):
            lines.append(f"  ...m{i},")
            for n in defs[m]:
                binding[n] = (m, n)
        lines.append("};")
    elif style == "rename":
        for m in order:
            ex = defs[m]
            n = rng.choice(ex)
            if rng.random() < 0.5:
                other = rng.choice([x for x in POOL if x != n and x not in defs[m]])
                lines.append(f"exports.{other} = require('./lib/{m}').{n};")
                binding[other] = (m, n)
            else:
                lines.append(f"Object.assign(exports, require('./lib/{m}'));")
                for nn in ex:
                    binding[nn] = (m, nn)
    else:  # try
        for m in order:
            ex = defs[m]
            n = rng.choice(ex)
            if rng.random() < 0.6:
                ghost = rng.choice(["fast", "native", "speedups"])
                if rng.random() < 0.5:
                    files[f"lib/{ghost}.js"] = f"'use strict';\n\nmodule.exports = {{ warmup: () => 'lib/{ghost}.js:warmup' }};\n"
                lines += ["try {", f"  exports.{n} = require('./lib/{ghost}').{n} || require('./lib/{m}').{n};", "} catch (err) {", f"  exports.{n} = require('./lib/{m}').{n};", "}"]
                if f"lib/{ghost}.js" in files:
                    pass
                binding[n] = (m, n)
            else:
                lines.append(f"Object.assign(exports, require('./lib/{m}'));")
                for nn in ex:
                    binding[nn] = (m, nn)
    files["index.js"] = "\n".join(lines) + "\n"
    names = sorted(binding)
    contested = [n for n in names if sum(1 for mm in mods if n in defs[mm]) >= 2]
    renamed = [n for n in names if binding[n][1] != n]
    x = rng.choice(renamed) if (renamed and rng.random() < 0.5) else rng.choice(contested or names)
    m, orig = binding[x]
    files["app.js"] = f"'use strict';\n\nconst {{ {x} }} = require('./index');\n\nconsole.log({x}());\n"
    files["package.json"] = f'{{\n  "name": "{pkg}",\n  "version": "0.4.0",\n  "main": "index.js"\n}}\n'
    files["README.md"] = f"# {dom.title}\n\nSmall helper package; `node app.js` shows one of its functions at work.\n"
    return files, x, f"lib/{m}.js:{orig}", "node app.js", pkg


# ---------------------------------------------------------------------------------------------------------------- rust
def rs_case(rng: random.Random, tier: int):
    k = {1: 2, 2: 3, 3: 4, 4: 4, 5: 5}[tier]
    dom, mods, defs = _leaf_names(rng, k, tier)
    pkg = dom.name
    files = {"Cargo.toml": f'[package]\nname = "{pkg}"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n'}
    for m in mods:
        path = f"src/{m}.rs"
        body = [f"//! {m.capitalize()} helpers.", ""]
        for n in defs[m]:
            body += [f"/// {n.capitalize()} for {m}.", f"pub fn {n}() -> &'static str {{", f'    "{path}:{n}"', "}", ""]
        files[path] = "\n".join(body)
    order = mods[:]
    rng.shuffle(order)
    lines = [f"//! {dom.title}: public API.", ""]
    for m in sorted(mods):
        lines.append(f"mod {m};")
    lines.append("")
    explicit: set = set()
    aliases: set = set()
    globs: dict = {}
    for m in order:
        ex = defs[m]
        kind = rng.choice(["glob", "names", "alias"] if tier >= 3 else ["names"])
        if kind == "glob":
            lines.append(f"pub use crate::{m}::*;")
            for n in ex:
                globs.setdefault(n, []).append(m)
        elif kind == "names":
            pick = [n for n in rng.sample(ex, rng.randint(1, len(ex))) if n not in explicit]
            if not pick:
                continue
            lines.append(f"pub use crate::{m}::{pick[0]};" if len(pick) == 1 else f"pub use crate::{m}::{{{', '.join(pick)}}};")
            explicit.update(pick)
        else:
            n = rng.choice(ex)
            other = rng.choice([x for x in POOL if x != n and x not in defs[m] and x not in explicit])
            lines.append(f"pub use crate::{m}::{n} as {other};")
            explicit.add(other)
            aliases.add(other)
    files["src/lib.rs"] = "\n".join(lines) + "\n"
    ok = sorted(explicit | {n for n, ms in globs.items() if len(ms) == 1})
    if not ok:
        return None
    contested = [n for n in ok if sum(1 for mm in mods if n in defs[mm]) >= 2]
    x = rng.choice(sorted(aliases)) if (aliases and rng.random() < 0.5) else rng.choice(contested or ok)
    files["src/main.rs"] = f"fn main() {{\n    println!(\"{{}}\", {pkg}::{x}());\n}}\n"
    files["README.md"] = f"# {dom.title}\n\nSmall helper crate; `cargo run` shows one of its functions at work.\n"
    return files, x, None, "cargo run --quiet", pkg


CASES = {"python": py_case, "javascript": js_case, "rust": rs_case}
RUN = {"python": "python3 app.py", "javascript": "node app.js", "rust": "cargo run --quiet --offline"}


def build(rng, lang: str, tier: int):
    """(files, symbol, 'path:name' really printed by the client, run command)"""
    for _ in range(30):
        got = CASES[lang](rng, tier)
        if not got:
            continue
        files, x, expect, cmd, pkg = got
        res = fx.run(files, RUN[lang] + " 2>/dev/null", timeout=120)
        out = [ln for ln in res.out.strip().split("\n") if ln]
        if not res.ok or not out or ":" not in out[-1]:
            continue
        truth = out[-1].strip()
        if expect is not None and truth != expect:
            raise AssertionError(f"model {expect} != run {truth}")
        return files, x, truth, cmd
    raise RuntimeError("reexport: nothing valid")
