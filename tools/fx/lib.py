"""Libraries and mutation tasks: turn one correct, well-specified library into many independent bug-fix tasks.

A ``Lib`` is authored once: a README that is the specification, a small implementation, a few visible tests, and a
larger hidden test suite that passes on the implementation. ``mutation_tasks`` then injects single-token bugs
(``fx.mutate``), keeps only the mutants that

* still build,
* are caught by the hidden suite (so the verifier can tell the fix from the bug),
* do not hang,

and writes each as a fix task whose reference solution is the original source file. The prompt describes the
symptom in one of several styles (a CI excerpt, a user-visible report from ``probes``, a vague "it drifted from the
README", ...), so tasks cut from one library are not clones of each other.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field

from . import langs, mutate
from .core import Family, Task, register
from .run import merged, run

BUILD = {
    "go": "go build ./...",
    "rust": "cargo build --offline --quiet",
    "java": "rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java' ! -path './test/*' ! -path './tests/*')",
    "c": "mkdir -p build && gcc -std=c11 -fsyntax-only -Wall $(find src -name '*.c')",
    "cpp": "mkdir -p build && g++ -std=c++17 -fsyntax-only -Wall $(find src -name '*.cpp')",
    "typescript": "rm -rf build && tsc -p .",
    "javascript": "for f in $(find src lib -name '*.js' 2>/dev/null); do node --check $f || exit 1; done",
    "php": "for f in $(find src -name '*.php'); do php -l $f >/dev/null || exit 1; done",
    "python": "python3 -m compileall -q .",
}


@dataclass
class Lib:
    name: str  # kebab-case, unique across all libraries
    lang: str
    title: str  # what a human calls it: "invoice proration"
    blurb: str  # one or two sentences of domain context used in prompts: "the billing service computes ..."
    files: dict[str, str]  # every non-test file of the CORRECT implementation (README.md is the spec)
    visible_tests: dict[str, str]  # shown to the agent; pass on the correct implementation
    hidden_tests: dict[str, str]  # the full suite; written at verification; passes on the correct implementation
    mutate: list[str]  # source paths (keys of files) that may carry a bug
    difficulty: int = 2  # 1..4: how hard the library itself is to read
    verify: str = ""
    timeout_s: int = 120
    tags: list[str] = field(default_factory=list)
    probes: list[str] = field(default_factory=list)  # python: expressions whose repr shows a difference
    probe_import: str = ""  # python: e.g. "from billing.proration import *"
    max_probe_diffs: int = 2

    def __post_init__(self):
        self.verify = self.verify or langs.VERIFY[self.lang]


def _sanitize_excerpt(out: str, hidden_paths: list[str], limit: int = 16) -> str:
    """The salient part of a failing run, with every trace of the hidden test files removed (their names, paths,
    line numbers, traceback frames), so a prompt can quote a CI failure without revealing the verifier."""
    bases = sorted({p.rsplit("/", 1)[-1] for p in hidden_paths} | set(hidden_paths), key=len, reverse=True)
    mods = {re.sub(r"\.\w+$", "", p.rsplit("/", 1)[-1]) for p in hidden_paths}
    lines: list[str] = []
    skip = False
    for line in out.splitlines():
        if skip:
            if line.startswith("    "):  # the source line and caret marks of a dropped traceback frame
                continue
            skip = False
        if any(b in line for b in bases):
            if line.lstrip().startswith(("File ", "at ", "from ")):
                skip = line.lstrip().startswith("File ")
                continue
            for b in bases:  # go/rust style "x_test.go:42: got 1 want 2" -> keep the message
                line = re.sub(r"\S*" + re.escape(b) + r":\d+(:\d+)?:?\s*", "", line)
        for m in mods:
            line = line.replace(m + ".", "")
        if re.match(r"^\s*(Ran \d+ tests?|OK\b|running \d+ tests?|test result|ok \d|# (tests|suites|pass|cancelled|skipped|todo|duration))", line):
            continue
        lines.append(line.rstrip())
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith(("FAIL: ", "ERROR: ")):
            start = i
            break
    if start is None:
        for i, ln in enumerate(lines):
            if re.search(r"--- FAIL|panicked|AssertionError|not ok|\u2716|Error:|FAIL\b|mismatch|expected", ln):
                start = i
                break
    if start is None:
        return ""
    win = []
    for ln in lines[start:]:
        if re.match(r"^\s*(-{5,}|={5,})\s*$", ln) or not ln.strip():
            continue
        if re.match(r"^(FAILED|FAIL\s*$|exit status|error: test failed)", ln):
            break
        win.append(ln[:200])
        if len(win) >= limit:
            break
    return "\n".join(win) if len(win) >= 2 else ""


def _probe_script(lib: Lib) -> str:
    return (
        "import sys, json\nsys.path.insert(0, '.')\n"
        f"{lib.probe_import}\n"
        f"PROBES = {json.dumps(lib.probes)}\n"
        "for e in PROBES:\n"
        "    try:\n        r = repr(eval(e))\n"
        "    except BaseException as ex:\n        r = 'raises ' + type(ex).__name__ + ((': ' + str(ex)) if str(ex) else '')\n"
        "    print(json.dumps([e, r[:160]]))\n"
    )


def _probe_diffs(lib: Lib, good: dict[str, str], bad: dict[str, str]) -> list[tuple[str, str, str]]:
    if lib.lang != "python" or not lib.probes:
        return []
    script = _probe_script(lib)
    g = run(merged(good, {"_probe.py": script}), "python3 _probe.py", timeout=30)
    b = run(merged(bad, {"_probe.py": script}), "python3 _probe.py", timeout=30)
    if not g.ok or b.timed_out:
        return []
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
    return [(e, gd[e], bd[e]) for e in lib.probes if e in gd and e in bd and gd[e] != bd[e]]


def _diff_line(e: str, good: str, bad: str) -> str:
    if bad.startswith("raises "):
        return f"- `{e}` raises `{bad[7:]}`, but it should return `{good}`"
    if good.startswith("raises "):
        return f"- `{e}` returns `{bad}`, but it should raise `{good[7:]}`"
    return f"- `{e}` gives `{bad}`, but it should give `{good}`"


_ENDINGS = [
    "Don't change the tests.",
    "Keep the public API as it is.",
    "Fix the cause, not the symptom.",
    "The README is the specification.",
    "Leave unrelated code alone.",
    "",
]


def _prompt(style: str, lib: Lib, m, excerpt: str, diffs, visible_fail: bool, rng: random.Random) -> str:
    end = rng.choice(_ENDINGS)
    title = lib.title
    path = m.path
    if style == "ci" and excerpt:
        return (f"The checks for {title} started failing after a recent change. {lib.blurb}\n\n"
                f"This is what the failing run reports (it is a subset of the output):\n\n```\n{excerpt}\n```\n\n"
                f"Find the root cause and fix it. {end}").strip()
    if style == "report" and diffs:
        lines = "\n".join(_diff_line(e, g, b) for e, g, b in diffs[: lib.max_probe_diffs])
        return (f"{lib.blurb} A user reports wrong results from {title}:\n\n{lines}\n\n"
                f"Track down the bug in the code and fix it. {end}").strip()
    if style == "visible" and visible_fail:
        return (f"`{lib.verify}` fails on the current checkout of {title}. Make the code correct. "
                f"There are more checks than the ones in the repository; `README.md` describes the intended behaviour. {end}").strip()
    if style == "spec":
        return (f"{lib.blurb} After a recent edit, {title} no longer behaves as `README.md` says in at least one case. "
                f"The change touched `{path}`. Compare the code with the specification, find the discrepancy and fix it. {end}").strip()
    if style == "vague":
        return (f"Something in {title} has drifted from its specification (`README.md`). I don't know which behaviour is wrong; "
                f"hidden checks cover the documented behaviour. Find and fix the defect. {end}").strip()
    if style == "terse" and diffs:
        e, g, b = diffs[0]
        return f"Bug in {title}: " + _diff_line(e, g, b)[2:] + f". Fix it. {end}".strip()
    if style == "review" and excerpt:
        sal = [ln for ln in excerpt.splitlines() if re.search(r"Error|error|expected|got|want|panick|!==|!=", ln)] or excerpt.splitlines()
        return (f"A teammate's last commit touched `{path}` and the suite for {title} has been red since. "
                f"One failure says: `{sal[-1].strip()[:160]}`. Please repair it. {end}").strip()
    return ""


_STYLES = ["ci", "report", "visible", "spec", "vague", "terse", "review"]
_STYLE_D = {"ci": 0, "report": 0, "visible": -1, "spec": 1, "vague": 1, "terse": 0, "review": 0}


def mutation_tasks(lib: Lib, rng: random.Random, n: int, max_candidates: int | None = None) -> list[Task]:
    """Up to ``n`` fix tasks from ``lib``. Raises if the library itself is not sound."""
    base_tree = merged(lib.files, lib.visible_tests, lib.hidden_tests)
    vis_tree = merged(lib.files, lib.visible_tests)
    base = run(base_tree, lib.verify, timeout=lib.timeout_s)
    if not base.ok:
        raise RuntimeError(f"lib {lib.name}: hidden+visible suite fails on the correct implementation:\n{base.out[-1500:]}")
    vbase = run(vis_tree, lib.verify, timeout=lib.timeout_s)
    # a mutant that runs far longer than the correct code is a hang: give mutants a short leash
    leash = int(max(8, min(lib.timeout_s, 8 * (base.ms / 1000.0) + 6)))
    if not vbase.ok:
        raise RuntimeError(f"lib {lib.name}: visible suite fails on the correct implementation:\n{vbase.out[-1500:]}")

    cands: list[mutate.Mutant] = []
    for path in lib.mutate:
        cands += mutate.mutants(lib.lang, path, lib.files[path], rng)
    rng.shuffle(cands)
    limit = max_candidates or (70 if lib.lang == "python" else 28)
    buildcmd = BUILD.get(lib.lang, "")
    hidden_paths = sorted(lib.hidden_tests)

    good: list[tuple[mutate.Mutant, str, bool]] = []  # (mutant, hidden output, visible_fail)
    per_op: dict[str, int] = {}
    per_line: dict[tuple, int] = {}
    tried = 0
    for m in cands:
        if len(good) >= n * 2 or tried >= limit:
            break
        if per_op.get(m.op, 0) >= max(2, n // 2 + 1) or per_line.get((m.path, m.line), 0) >= 1:
            continue
        if lib.lang == "python" and not mutate.python_compiles(m.text):
            continue
        tried += 1
        files = merged(lib.files, {m.path: m.text})
        if buildcmd and lib.lang != "python":
            b = run(merged(files, lib.visible_tests), buildcmd, timeout=max(leash, 60))
            if not b.ok:
                continue
        r = run(merged(files, lib.visible_tests, lib.hidden_tests), lib.verify, timeout=leash)
        if r.ok or r.timed_out or len(r.out.strip()) < 10:
            continue
        v = run(merged(files, lib.visible_tests), lib.verify, timeout=leash)
        if v.timed_out:
            continue
        good.append((m, r.out, not v.ok))
        per_op[m.op] = per_op.get(m.op, 0) + 1
        per_line[(m.path, m.line)] = 1

    # choose n with op diversity: round-robin over ops
    by_op: dict[str, list] = {}
    for g in good:
        by_op.setdefault(g[0].op, []).append(g)
    chosen: list = []
    ops = sorted(by_op)
    rng.shuffle(ops)
    while len(chosen) < n and any(by_op.values()):
        for op in ops:
            if by_op[op] and len(chosen) < n:
                chosen.append(by_op[op].pop(0))
    tasks: list[Task] = []
    for k, (m, out, visible_fail) in enumerate(chosen):
        files = merged(lib.files, {m.path: m.text})
        excerpt = _sanitize_excerpt(out, hidden_paths)
        diffs = _probe_diffs(lib, lib.files, files)
        styles = [s for s in _STYLES if _prompt(s, lib, m, excerpt, diffs, visible_fail, random.Random(0))]
        style = rng.choice(styles) if styles else "spec"
        prompt = _prompt(style, lib, m, excerpt, diffs, visible_fail, rng) or _prompt("spec", lib, m, excerpt, diffs, visible_fail, rng)
        d = max(1, min(5, lib.difficulty + _STYLE_D[style]))
        tasks.append(Task(
            slug=f"{k + 1:02d}-{m.op}",
            prompt=prompt,
            difficulty=d,
            start=merged(files, lib.visible_tests),
            hidden=dict(lib.hidden_tests),
            solution={m.path: lib.files[m.path]},
            verify=lib.verify,
            timeout_s=lib.timeout_s,
            tags=["mutation", "bugfix", style, *lib.tags],
            notes={"library": lib.name, "mutation": m.desc, "style": style, "visible_fails": visible_fail},
        ))
    return tasks


def register_libs(libs: list[Lib], n: int = 8, category: str = "fix") -> None:
    """Register one family per library: ``fix-<lang>-<name>``."""
    for lib in libs:
        fam = Family(name=f"fix-{lib.lang[:4]}-{lib.name}", category=category, lang=lib.lang, kind="fix", n=n,
                     summary=f"injected bugs in {lib.title} ({lib.lang})")

        def gen(rng, count, _lib=lib):
            return mutation_tasks(_lib, rng, count)

        gen.__module__ = lib.__class__.__module__
        register(fam, gen)
