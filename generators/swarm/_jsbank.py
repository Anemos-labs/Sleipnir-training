"""A small bank of original JavaScript (CommonJS, node:test) libraries, the counterpart of ``_bank`` for node tasks.

Layout inside a task repository::

    src/<key>/index.js   src/<key>/SPEC.md
    test/<key>.test.js            (visible)
    .grade/test/<key>.test.js     (hidden)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from fx import merged, run

from ._bank import Bug

JS_MODS: dict[str, "JMod"] = {}

VISIBLE_HEAD = 'const test = require("node:test");\nconst assert = require("node:assert/strict");\nconst lib = require("../src/%(key)s");\n\n'
HIDDEN_HEAD = 'const test = require("node:test");\nconst assert = require("node:assert/strict");\nconst lib = require("../../src/%(key)s");\n\n'


@dataclass
class JMod:
    key: str
    title: str
    blurb: str
    spec: str
    core: str
    visible: str  # test body; the head requires the module as `lib`
    hidden: str
    bugs: list[Bug]
    names: list[str] = field(default_factory=list)

    def core_with(self, bug: Bug | None) -> str:
        if bug is None:
            return self.core
        if self.core.count(bug.old) != 1:
            raise ValueError(f"{self.key}/{bug.key}: pattern occurs {self.core.count(bug.old)} times")
        return self.core.replace(bug.old, bug.new)

    def src_files(self, bug: Bug | None = None) -> dict[str, str]:
        return {f"src/{self.key}/index.js": self.core_with(bug), f"src/{self.key}/SPEC.md": self.spec}

    def solution_files(self) -> dict[str, str]:
        return {f"src/{self.key}/index.js": self.core}

    def visible_files(self) -> dict[str, str]:
        return {f"test/{self.key}.test.js": (VISIBLE_HEAD % {"key": self.key}) + self.visible}

    def hidden_files(self) -> dict[str, str]:
        return {self.hidden_path(): (HIDDEN_HEAD % {"key": self.key}) + self.hidden}

    def hidden_path(self) -> str:
        return f".grade/test/{self.key}.test.js"


def add(m: JMod) -> JMod:
    JS_MODS[m.key] = m
    return m


def probe_script(m: JMod, probes: list[str]) -> str:
    names = ", ".join(m.names)
    return (
        'const util = require("util");\n'
        f'const {{ {names} }} = require("./src/{m.key}");\n'
        f"const PROBES = {json.dumps(probes)};\n"
        "for (const e of PROBES) {\n  let r;\n  try { r = util.inspect(eval(e), { depth: 6, breakLength: Infinity, compact: true }); }\n"
        '  catch (ex) { r = "raises " + ex.name + ": " + ex.message; }\n  console.log(JSON.stringify([e, r.slice(0, 320)]));\n}\n'
    )


def symptoms(m: JMod, bug: Bug) -> list[tuple[str, str, str]]:
    script = {"_probe.js": probe_script(m, bug.probes)}
    g = run(merged(m.src_files(None), script), "node _probe.js", timeout=30)
    b = run(merged(m.src_files(bug), script), "node _probe.js", timeout=30)
    if not g.ok or b.timed_out:
        raise RuntimeError(f"{m.key}/{bug.key}: probe run failed:\n{g.out[-500:]}\n{b.out[-500:]}")

    def parse(o):
        d = {}
        for ln in o.out.splitlines():
            try:
                e, r = json.loads(ln)
                d[e] = r
            except Exception:  # noqa: BLE001
                pass
        return d

    gd, bd = parse(g), parse(b)
    out = [(e, gd[e], bd[e]) for e in bug.probes if e in gd and e in bd and gd[e] != bd[e]]
    if not out:
        raise RuntimeError(f"{m.key}/{bug.key}: no probe distinguishes the bug")
    return out


def describe(sym, variant=0) -> str:
    e, good, bad = sym
    v = variant % 3
    if bad.startswith("raises ") and good.startswith("raises "):
        return f"`{e}` throws `{bad[7:]}` where `{good[7:]}` is expected"
    if bad.startswith("raises "):
        return (f"`{e}` throws `{bad[7:]}`, but it should return `{good}`", f"`{e}` fails with `{bad[7:]}` instead of returning `{good}`",
                f"expected `{good}` from `{e}` but it throws `{bad[7:]}`")[v]
    if good.startswith("raises "):
        return f"`{e}` returns `{bad}`, but it should throw `{good[7:]}`"
    return (f"`{e}` gives `{bad}`, but it should give `{good}`", f"`{e}` returns `{bad}` where `{good}` is expected", f"expected `{good}` from `{e}`, got `{bad}`")[v]


def run_hidden(m: JMod, bug: Bug | None, timeout: int = 60):
    return run(merged(m.src_files(bug), m.hidden_files()), f"node --test {m.hidden_path()}", timeout=timeout)


def run_visible(m: JMod, bug: Bug | None):
    return run(merged(m.src_files(bug), m.visible_files()), "node --test test/*.test.js", timeout=60)


def verify_jsbank(keys=None) -> list[str]:
    problems = []
    for k in keys or sorted(JS_MODS):
        m = JS_MODS[k]
        r = run_hidden(m, None)
        if not r.ok:
            problems.append(f"{k}: hidden fails on the correct implementation:\n{r.out[-1200:]}")
        v = run_visible(m, None)
        if not v.ok:
            problems.append(f"{k}: visible fails on the correct implementation:\n{v.out[-900:]}")
        for b in m.bugs:
            if m.core.count(b.old) != 1:
                problems.append(f"{k}/{b.key}: pattern occurs {m.core.count(b.old)} times")
                continue
            try:
                if run_hidden(m, b).ok:
                    problems.append(f"{k}/{b.key}: hidden tests do NOT catch the bug")
                symptoms(m, b)
            except Exception as e:  # noqa: BLE001
                problems.append(f"{k}/{b.key}: {e}")
    return problems
