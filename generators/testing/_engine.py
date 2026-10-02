"""Shared machinery for the testing families: libraries with a gold suite, mutant pools, the hidden checker spec.

A ``TLib`` is a small, correct, specified library (README = specification) with a *gold* test suite that passes on it
and kills (almost) every single-token mutant.  From one library the families make several kinds of task:

* write a suite for the module: scored by the share of hidden mutants it kills (``tests_task``),
* write a regression test for a reported bug: it must fail on the buggy copy and pass on the fixed one,
* repair a broken suite: wrong expectations, tests that pin implementation details, flaky or order dependent tests.

Everything is decided by ``_check_tests.py`` (copied to ``_verify/check.py`` as a hidden file) from ``spec.json``.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from fx import Task, mutate, run
from fx.core import rng_for
from fx.lib import BUILD
from fx.run import merged

CHECKER = (Path(__file__).with_name("_check_tests.py")).read_text(encoding="utf-8")

COMMENT = {"python": "#", "go": "//", "javascript": "//", "rust": "//", "java": "//", "typescript": "//"}
STRIP = {
    "python": ["tests/*"], "go": ["*_test.go"], "javascript": ["test/*"], "rust": ["tests/*"], "java": ["test/*"],
}


@dataclass
class TLib:
    name: str
    lang: str
    title: str  # "the ferry fare calculator"
    blurb: str  # one or two sentences of context ("The ticket office uses ...")
    files: dict[str, str]  # correct implementation + README + build files (no tests)
    stub: dict[str, str]  # visible starting tests: a smoke test that passes and checks (almost) nothing
    gold: dict[str, str]  # the reference suite: passes on `files`, kills the mutants
    mutate: list[str]  # source paths that carry mutants
    cmd: str  # command running every test of a tree (scratch copy), exit 0 = green
    where: str  # sentence: where the agent puts tests / how they are run
    difficulty: int = 2
    timeout: int = 40
    protect: list[str] = field(default_factory=list)  # globs the agent may not touch (default: the mutated sources)
    probes: list[str] = field(default_factory=list)  # python: expressions for bug-report prompts
    probe_import: str = ""
    tags: list[str] = field(default_factory=list)
    renames: dict[str, str] = field(default_factory=dict)  # python: private name -> new name (refactor variant)
    max_pool: int = 0
    focus: str = ""  # what a careful suite has to pin down (used in some prompts)
    wrong_edits: list = field(default_factory=list)  # non-python: (gold path, old snippet, new snippet) giving a wrong expectation
    internals: dict = field(default_factory=dict)  # tests that poke private names / messages; pass on `files`
    msg_swaps: dict = field(default_factory=dict)  # message text -> reworded text (refactored variant)
    strip_keep: dict = field(default_factory=dict)  # files a "fresh" scenario needs after the agent's tests are stripped
    py_groups: list = field(default_factory=list)  # python: the gold steps (to regenerate the suite with wrong expectations)
    py_imports: str = ""
    py_header: str = ""
    extra: dict = field(default_factory=dict)  # family specific material (clock: legacy sources and sleepy tests; order: test templates)

    def __post_init__(self):
        assert self.title.startswith("the "), f"{self.name}: the title must start with 'the ' (prompts rely on it)"

    @property
    def comment(self) -> str:
        return COMMENT[self.lang]

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps([self.name, self.files, self.gold, self.cmd], sort_keys=True).encode()).hexdigest()[:20]


@dataclass
class Cand:
    path: str
    line: int
    op: str
    old: str
    new_line: str
    out: str  # the failing gold output
    desc: str

    def edit(self) -> dict:
        return {"path": self.path, "line": self.line, "old": self.old, "new": self.new_line}


def line_edit(ref: str, text: str) -> tuple[int, str, str] | None:
    a, b = ref.split("\n"), text.split("\n")
    if len(a) != len(b):
        return None
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    if len(diff) != 1:
        return None
    i = diff[0]
    return i + 1, a[i], b[i]


_POOLS: dict[str, list[Cand]] = {}


def mutant_pool(lib: TLib) -> list[Cand]:
    """Mutants of the library that build and are killed by the gold suite (cached per library)."""
    key = lib.fingerprint()
    if key in _POOLS:
        return _POOLS[key]
    rng = rng_for("pool:" + lib.name)
    base = run(merged(lib.files, lib.gold), lib.cmd, timeout=max(lib.timeout, 60))
    if not base.ok:
        raise RuntimeError(f"lib {lib.name}: gold suite fails on the correct implementation:\n{base.out[-2000:]}")
    stub_base = run(merged(lib.files, lib.stub), lib.cmd, timeout=max(lib.timeout, 60))
    if not stub_base.ok:
        raise RuntimeError(f"lib {lib.name}: stub tests fail on the correct implementation:\n{stub_base.out[-2000:]}")
    leash = int(max(10, min(lib.timeout, 6 * (base.ms / 1000.0) + 8)))
    cands: list[mutate.Mutant] = []
    for p in lib.mutate:
        cands += mutate.mutants(lib.lang, p, lib.files[p], rng)
    rng.shuffle(cands)
    limit = lib.max_pool or (130 if lib.lang in ("python", "javascript") else 48)
    want = 44 if lib.lang in ("python", "javascript") else 26
    buildcmd = BUILD.get(lib.lang, "")
    out: list[Cand] = []
    per_line: set = set()
    tried = 0
    for m in cands:
        if len(out) >= want or tried >= limit:
            break
        e = line_edit(lib.files[m.path], m.text)
        if e is None or (m.path, e[0]) in per_line:
            continue
        if m.op == "delete" and not e[1].startswith((" ", "\t")):
            continue  # a deleted top-level definition is a build break, not a bug
        if lib.lang == "python" and not mutate.python_compiles(m.text):
            continue
        tried += 1
        files = merged(lib.files, {m.path: m.text})
        if buildcmd and lib.lang != "python":
            b = run(merged(files, lib.stub), buildcmd, timeout=max(leash, 60))
            if not b.ok:
                continue
        r = run(merged(files, lib.gold), lib.cmd, timeout=leash)
        if r.ok or r.timed_out or len(r.out.strip()) < 10:
            continue
        # the smoke test must not already catch it
        s = run(merged(files, lib.stub), lib.cmd, timeout=leash)
        if not s.ok:
            continue
        per_line.add((m.path, e[0]))
        out.append(Cand(m.path, e[0], m.op, e[1], e[2], r.out, m.desc))
    _POOLS[key] = out
    return out


def choose(pool: list[Cand], rng: random.Random, k: int, spacing: int = 2, exclude: set | None = None) -> list[Cand]:
    """k mutants with a spread of operators, no two on neighbouring lines of one file."""
    by_op: dict[str, list[Cand]] = {}
    for c in pool:
        if exclude and (c.path, c.line) in exclude:
            continue
        by_op.setdefault(c.op, []).append(c)
    ops = sorted(by_op)
    for op in ops:
        rng.shuffle(by_op[op])
    rng.shuffle(ops)
    chosen: list[Cand] = []
    while len(chosen) < k and any(by_op.values()):
        progressed = False
        for op in ops:
            lst = by_op[op]
            while lst:
                c = lst.pop()
                if all(not (x.path == c.path and abs(x.line - c.line) < spacing) for x in chosen):
                    chosen.append(c)
                    progressed = True
                    break
            if len(chosen) >= k:
                break
        if not progressed:
            break
    chosen.sort(key=lambda c: (c.path, c.line))
    return chosen


# ---- spec / hidden files --------------------------------------------------------------------------------------------

def hidden_files(spec: dict, extra: dict[str, str] | None = None) -> dict[str, str]:
    h = {"_verify/check.py": CHECKER, "_verify/spec.json": json.dumps(spec, sort_keys=True, indent=1) + "\n"}
    h.update(extra or {})
    return h


VERIFY = "python3 _verify/check.py"


def base_spec(lib: TLib, scenarios: list[dict], mutants: list[dict] | None = None) -> dict:
    return {
        "cmd": lib.cmd,
        "timeout": lib.timeout,
        "comment": lib.comment,
        "ref": {p: lib.files[p] for p in lib.mutate},
        "scenarios": scenarios,
        "mutants": mutants or [],
    }


def mutant_specs(chosen: list[Cand]) -> list[dict]:
    out = []
    for i, c in enumerate(chosen):
        e = c.edit()
        e["id"] = f"{i + 1:02d}"
        out.append(e)
    return out


def protect_globs(lib: TLib) -> list[str]:
    return list(lib.protect) or sorted(lib.mutate)


def sc_base(gate=True) -> dict:
    return {"name": "real code, your tests", "expect": "pass", "gate": gate, "sources": {}}


def sc_marker() -> dict:
    return {"name": "same code, shifted lines and file hash", "expect": "pass", "gate": True, "marker": True}


# ---- task builders --------------------------------------------------------------------------------------------------

def tests_task(lib: TLib, chosen: list[Cand], prompt: str, difficulty: int, slug: str, tags: list[str], notes: dict,
               start_extra: dict[str, str] | None = None) -> Task:
    spec = base_spec(lib, [sc_base(), sc_marker()], mutant_specs(chosen))
    return Task(
        slug=slug, prompt=prompt, difficulty=difficulty, kind="feature",
        start=merged(lib.files, lib.stub, start_extra or {}), hidden=hidden_files(spec), solution=dict(lib.gold),
        verify=VERIFY, pass_mode="json-score", protect_tests=False, protected=protect_globs(lib),
        timeout_s=max(150, lib.timeout * (len(chosen) + 3) + 60), tags=["write-tests", "mutation-score", *lib.tags, *tags],
        notes={"library": lib.name, "mutants": [c.desc for c in chosen], **notes},
    )


# ---- prompts for "write a test suite" -------------------------------------------------------------------------------

def _grading_sentence(rng: random.Random) -> str:
    return rng.choice([
        "To check them I run your tests against the real code and against copies with small bugs seeded in (a flipped comparison, a changed constant, a dropped statement); the score is the share of those copies your tests catch. Tests that fail on the real code count for nothing.",
        "The grader mutates the source in several small ways and counts how many mutated copies make your suite go red. A suite that is red on the genuine code scores zero.",
        "Your suite will be judged by mutation testing: broken copies of the module are produced behind your back and the more of them your tests reject, the better. It has to be green on the original, of course.",
        "I'll judge the result by seeding bugs into the module and seeing whether your tests notice; they must still pass on the untouched version.",
        "Don't worry about coverage numbers: what counts is whether the tests fail when the behaviour is wrong. Expect them to be run against deliberately broken variants of the code.",
    ])


def write_prompt(lib: TLib, rng: random.Random, k: int, style: int) -> str:
    t, b, w, f = lib.title, lib.blurb, lib.where, lib.focus
    g = _grading_sentence(rng)
    voices = [
        f"{t[0].upper() + t[1:]} has no tests at all and we are about to change it. {b} Before anybody touches it I want a proper safety net: write the test suite. README.md describes the intended behaviour; read the code too. {w}\n\n{g}",
        f"write tests for {t}. {w} {g}",
        f"I just inherited {t}. {b} The previous owner left a README and one smoke test and nothing else. Could you write the missing tests so that a regression in any documented rule gets caught? {w} {g}",
        f"Our mutation-testing job reports that the test suite of {t} is practically empty: nearly every mutant survives. Please fix that by writing real tests. {w}\n\n{g}",
        f"PR review comment on {t}: \"Needs tests before this can merge. The rules in the README are subtle, please pin them down, including the boundaries and the error cases.\" Write them. {w} {g}",
        f"README.md is the specification of {t}. Write a unit test suite that pins down every behaviour it documents, boundaries and error cases included, and nothing it does not document. {w}\n\n{g}",
        f"{b} The code is correct today but fragile. I want tests that fail when somebody gets a single comparison, constant or branch wrong. Careful, not exhaustive-for-the-sake-of-it. {w} {g}",
        f"Task: test {t}. Deliverable: test files under the usual test directory, green on the current code. {w} {g}" + (f" Areas that tend to hide bugs: {f}." if f else ""),
        f"Hi! Could you cover {t} with tests? {b} " + (f"The tricky parts are {f}. " if f else "") + f"{w} {g}",
        f"We're handing {t} to another team on Monday and they asked for tests as part of the handover. {b} The README is the contract. {w}\n\n{g}",
    ]
    return voices[style % len(voices)]


def plan_sizes(rng: random.Random, lib: TLib, per_instance: int) -> list[tuple[int, int]]:
    """(k mutants, difficulty) for the tasks cut from one library instance."""
    ks = [rng.choice([4, 5]), rng.choice([6, 7, 8]), rng.choice([9, 10, 12])]
    if per_instance <= 3:
        rng.shuffle(ks)
        ks = ks[:per_instance]
    out = []
    for k in ks:
        d = lib.difficulty - 1 + (k >= 7) + (k >= 11)
        out.append((k, max(1, min(5, d))))
    return out


def write_family(factories, rng: random.Random, n: int, per_instance: int = 3):
    """Tasks "write the missing tests": ``per_instance`` tasks per library instance, instances cycle through the factories."""
    i = 0
    inst = 0
    while i < n:
        lib = factories[inst % len(factories)](rng)
        pool = mutant_pool(lib)
        used: set = set()
        sizes = plan_sizes(rng, lib, per_instance)
        for j, (k, d) in enumerate(sizes):
            if i >= n:
                break
            chosen = choose(pool, rng, min(k, max(3, len(pool) - len(used))), exclude=used)
            if len(chosen) < 3:
                continue
            used |= {(c.path, c.line) for c in chosen}
            style = rng.randrange(10)
            prompt = write_prompt(lib, rng, len(chosen), style)
            slug = f"{i + 1:02d}-{lib.name.split('-', 1)[-1]}-{len(chosen)}m"
            yield tests_task(lib, chosen, prompt, d, slug, [], {"style": style, "k": len(chosen), "instance": inst})
            i += 1
        inst += 1
