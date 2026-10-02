"""A bank of small, original Python libraries ("modules") shared by the swarm and robust generators.

A ``Mod`` is a correct, specified library (SPEC.md is the specification), a few visible tests, a thorough hidden test
module and a list of hand-written ``Bug`` variants (an exact text replacement in the implementation). A task picks a
module, applies a bug and describes the symptom; ``symptoms`` runs probe expressions on the good and the buggy
tree so prompts can quote real wrong results. ``build_module_tests`` confirms (and caches) that the hidden tests pass
on the good tree and fail on the buggy one.

Layout of a module inside a task repository::

    src/<key>/__init__.py   src/<key>/core.py   src/<key>/SPEC.md
    tests/test_<key>.py     (visible)
    .grade/tests/test_<key>.py (hidden)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from fx import dd, merged, run

HIDDEN_PRELUDE = "import os, sys, unittest\nsys.path.insert(0, os.path.join(os.getcwd(), 'src'))\n\n"
VISIBLE_PRELUDE = ("import os, sys, unittest\n"
                   "sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))\n\n")
MAIN = "\n\nif __name__ == '__main__':\n    unittest.main()\n"


@dataclass
class Bug:
    key: str
    old: str  # exact text in core.py (must occur exactly once)
    new: str
    probes: list[str]  # expressions evaluated after `from <key> import *`; at least one differs when the bug is present
    where: str = ""  # which function holds the defect (used by hints and review tasks)
    note: str = ""  # one line for notes/provenance


@dataclass
class Mod:
    key: str
    title: str
    blurb: str  # a complete sentence naming the subject
    spec: str
    core: str
    visible: str  # test body (without prelude)
    hidden: str
    bugs: list[Bug]
    names: list[str] = field(default_factory=list)  # public functions, in spec order

    def init_py(self) -> str:
        return f'"""{self.title}."""\nfrom .core import *  # noqa: F401,F403\n'

    def core_with(self, bug: Bug | None) -> str:
        if bug is None:
            return self.core
        if self.core.count(bug.old) != 1:
            raise ValueError(f"{self.key}/{bug.key}: pattern occurs {self.core.count(bug.old)} times")
        return self.core.replace(bug.old, bug.new)

    def src_files(self, bug: Bug | None = None) -> dict[str, str]:
        return {
            f"src/{self.key}/__init__.py": self.init_py(),
            f"src/{self.key}/core.py": self.core_with(bug),
            f"src/{self.key}/SPEC.md": self.spec,
        }

    def solution_files(self) -> dict[str, str]:
        return {f"src/{self.key}/core.py": self.core}

    def visible_files(self) -> dict[str, str]:
        return {f"tests/test_{self.key}.py": VISIBLE_PRELUDE + self.visible + MAIN}

    def hidden_files(self) -> dict[str, str]:
        return {f".grade/tests/test_{self.key}.py": HIDDEN_PRELUDE + self.hidden + MAIN}

    def hidden_path(self) -> str:
        return f".grade/tests/test_{self.key}.py"

    def bug(self, key: str) -> Bug:
        for b in self.bugs:
            if b.key == key:
                return b
        raise KeyError(key)


MODS: dict[str, Mod] = {}


def add(m: Mod) -> Mod:
    if m.key in MODS:
        raise ValueError(f"duplicate module {m.key}")
    MODS[m.key] = m
    return m


def _probe_script(m: Mod, probes: list[str]) -> str:
    return (
        "import sys, json\nsys.path.insert(0, 'src')\n"
        f"from {m.key} import *\n"
        f"PROBES = {json.dumps(probes)}\n"
        "for e in PROBES:\n"
        "    try:\n        r = repr(eval(e))\n"
        "    except BaseException as ex:\n        r = 'raises ' + type(ex).__name__ + ((': ' + str(ex)) if str(ex) else '')\n"
        "    print(json.dumps([e, r[:200]]))\n"
    )


def symptoms(m: Mod, bug: Bug) -> list[tuple[str, str, str]]:
    """(expression, good repr, buggy repr) for every probe whose result differs."""
    script = {"_probe.py": _probe_script(m, bug.probes)}
    g = run(merged(m.src_files(None), script), "python3 _probe.py", timeout=30)
    b = run(merged(m.src_files(bug), script), "python3 _probe.py", timeout=30)
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


def describe(sym: tuple[str, str, str]) -> str:
    e, good, bad = sym
    if bad.startswith("raises "):
        return f"`{e}` raises `{bad[7:]}`, but it should return `{good}`"
    if good.startswith("raises "):
        return f"`{e}` returns `{bad}`, but it should raise `{good[7:]}`"
    return f"`{e}` gives `{bad}`, but it should give `{good}`"


def run_hidden(m: Mod, bug: Bug | None, extra: dict[str, str] | None = None):
    files = merged(m.src_files(bug), m.hidden_files(), extra or {})
    return run(files, f"python3 {m.hidden_path()}", timeout=60)


def run_visible(m: Mod, bug: Bug | None):
    files = merged(m.src_files(bug), m.visible_files())
    return run(files, "python3 -m unittest discover -s tests", timeout=60)


def verify_bank(keys: list[str] | None = None) -> list[str]:
    """Development check: hidden tests pass on the good tree, fail on every bug; visible pass on the good tree."""
    problems = []
    for k in keys or sorted(MODS):
        m = MODS[k]
        r = run_hidden(m, None)
        if not r.ok:
            problems.append(f"{k}: hidden fails on the correct implementation:\n{r.out[-900:]}")
        v = run_visible(m, None)
        if not v.ok:
            problems.append(f"{k}: visible fails on the correct implementation:\n{v.out[-900:]}")
        for b in m.bugs:
            try:
                if m.core.count(b.old) != 1:
                    problems.append(f"{k}/{b.key}: pattern occurs {m.core.count(b.old)} times")
                    continue
                rb = run_hidden(m, b)
                if rb.ok:
                    problems.append(f"{k}/{b.key}: hidden tests do NOT catch the bug")
                symptoms(m, b)
            except Exception as e:  # noqa: BLE001
                problems.append(f"{k}/{b.key}: {e}")
    return problems
