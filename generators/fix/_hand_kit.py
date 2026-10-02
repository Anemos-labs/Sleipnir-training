"""Helpers shared by the hand-authored fix families (``generators/fix/hand_*.py``).

A *base* is one small, correct, specified project (source files, a README, visible tests, a thorough hidden suite).
A *bug* is a hand-designed defect expressed as textual patches against the correct files (never a token mutation: each
patch is written by the author, may touch several files and may combine causes), together with the way it is reported
(the prompt). ``tasks_from`` turns bases and bugs into fixture tasks whose reference solution is exactly the correct
version of the files the bug touched, and *checks while generating* that

* the hidden suite passes on the correct project and on the reference solution,
* the hidden suite fails on every buggy start,
* the buggy start still builds (a syntax error is not a bug),
* an optional "reported" visible test fails on the bug and passes on the fix.

Prompts may be plain strings or callables ``f(ctx)``; ``ctx.probe(script)`` runs a small program in the correct and in
the buggy checkout and returns both outputs, so numbers quoted in a bug report are real, not hand-computed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from fx import Task, langs, merged, run

_PH = re.compile(r"\{\{(\w+)\}\}")


def sub(text: str, **kw) -> str:
    """Replace ``{{name}}`` placeholders (the only template syntax used inside project sources)."""

    def r(m):
        k = m.group(1)
        if k not in kw:
            raise KeyError(f"unknown placeholder {{{{{k}}}}}")
        return str(kw[k])

    return _PH.sub(r, text)


def subtree(tree: dict[str, str], **kw) -> dict[str, str]:
    return {sub(p, **kw): sub(t, **kw) for p, t in tree.items()}


def patch_text(text: str, pairs: list[tuple[str, str]], where: str = "") -> str:
    for old, new in pairs:
        n = text.count(old)
        if n != 1:
            raise ValueError(f"patch target occurs {n} times in {where}: {old[:80]!r}")
        if old == new:
            raise ValueError(f"patch is a no-op in {where}: {old[:80]!r}")
        text = text.replace(old, new)
    return text


@dataclass
class Bug:
    id: str
    d: int
    patches: dict[str, list[tuple[str, str]]]
    prompt: object  # str | Callable[[Ctx], str]
    reported: dict[str, str] = field(default_factory=dict)  # extra visible test files that fail on the bug
    tags: list[str] = field(default_factory=list)
    lang: str = ""
    timeout_s: int = 0


@dataclass
class Base:
    name: str
    lang: str
    good: dict[str, str]  # non-test files of the correct project
    visible: dict[str, str]  # visible tests (pass on the correct project)
    hidden: dict[str, str]  # hidden suite (passes on the correct project, fails on every bug)
    bugs: list[Bug]
    verify: str = ""
    notes: dict = field(default_factory=dict)
    extra_hidden_ok: bool = False


class Ctx:
    """What a prompt function can ask: outputs of a probe program on the correct and on the buggy tree."""

    def __init__(self, base: Base, bug: Bug, good_tree: dict[str, str], bad_tree: dict[str, str]):
        self.base, self.bug = base, bug
        self.good_tree, self.bad_tree = good_tree, bad_tree

    def probe(self, script: str, cmd: str = "", name: str = "") -> tuple[str, str]:
        lang = self.bug.lang or self.base.lang
        name = name or {"python": "_probe.py", "javascript": "_probe.js", "ruby": "_probe.rb", "bash": "_probe.sh"}.get(lang, "_probe.txt")
        cmd = cmd or {"python": "python3 _probe.py", "javascript": "node _probe.js", "ruby": "ruby -Ilib _probe.rb", "bash": "bash _probe.sh"}[lang]
        g = run(merged(self.good_tree, {name: script}), cmd, timeout=40)
        b = run(merged(self.bad_tree, {name: script}), cmd, timeout=40)
        if not g.ok:
            raise RuntimeError(f"probe fails on the correct tree of {self.base.name}:\n{g.out[-1500:]}")
        return g.out.strip(), b.out.strip()

    def bad_run(self, script: str, cmd: str = "", name: str = "") -> str:
        """Output (stdout+stderr, success or not) of a probe on the buggy tree only: e.g. a real traceback."""
        lang = self.bug.lang or self.base.lang
        name = name or {"python": "_probe.py", "javascript": "_probe.js", "ruby": "_probe.rb", "bash": "_probe.sh"}.get(lang, "_probe.txt")
        cmd = cmd or {"python": "python3 _probe.py", "javascript": "node _probe.js", "ruby": "ruby -Ilib _probe.rb", "bash": "bash _probe.sh"}[lang]
        return run(merged(self.bad_tree, {name: script}), cmd, timeout=40).out.strip()


# `node --test test/` does not work on node 22 (a directory argument is run as a module); use a glob.
KIT_VERIFY = {"javascript": "node --test test/*.test.js"}

_COMPILE_ERR = re.compile(r"SyntaxError|IndentationError|error\[E\d+\]|cannot find symbol|undefined: |syntax error|declared and not used|"
                          r"imported and not used|expected .*, found|error: cannot|error: expected|mismatched types|unresolved")


def tasks_from(bases: list[Base], picks: list[tuple[int, int]] | None = None, check: bool = True) -> list[Task]:
    """One fixture task per (base index, bug index) pick (default: every bug of every base, in order)."""
    out: list[Task] = []
    problems: list[str] = []
    if picks is None:
        picks = [(i, j) for i, b in enumerate(bases) for j in range(len(b.bugs))]
    for k, (bi, bj) in enumerate(picks):
        base = bases[bi]
        bug = base.bugs[bj]
        lang = bug.lang or base.lang
        verify = base.verify or KIT_VERIFY.get(lang) or langs.VERIFY[lang]
        good_tree = dict(base.good)
        bad_tree = dict(base.good)
        for path, pairs in bug.patches.items():
            if path not in base.good:
                raise ValueError(f"{base.name}/{bug.id}: patch for unknown file {path}")
            bad_tree[path] = patch_text(base.good[path], pairs, f"{base.name}/{bug.id}:{path}")
        ctx = Ctx(base, bug, good_tree, bad_tree)
        prompt = bug.prompt(ctx) if callable(bug.prompt) else bug.prompt
        start = merged(bad_tree, base.visible, bug.reported)
        hidden = dict(base.hidden)
        solution = {p: base.good[p] for p in bug.patches}
        t = Task(
            slug=f"{k + 1:02d}-{bug.id}",
            prompt=prompt,
            difficulty=bug.d,
            start=start,
            hidden=hidden,
            solution=solution,
            verify=verify,
            lang=lang,
            tags=["handmade", "bugfix", *bug.tags],
            timeout_s=bug.timeout_s or 120,
            notes={"base": base.name, "bug": bug.id, **base.notes},
        )
        out.append(t)
        if not check:
            continue
        tag = f"{base.name}/{bug.id}"
        timeout = 60
        sol_tree = merged(start, solution)
        r_sol = run(merged(sol_tree, hidden), verify, timeout=timeout)
        if not r_sol.ok:
            problems.append(f"{tag}: hidden+visible fail on the reference solution:\n{r_sol.out[-1200:]}")
            continue
        r_bad = run(merged(start, hidden), verify, timeout=timeout)
        if r_bad.ok:
            problems.append(f"{tag}: hidden suite PASSES on the buggy start (bug not caught)")
        elif r_bad.timed_out:
            problems.append(f"{tag}: buggy start hangs")
        elif _COMPILE_ERR.search(r_bad.out) and not re.search(r"FAIL|panicked|AssertionError|assert|not ok|Error:", r_bad.out.replace("SyntaxError", "")):
            problems.append(f"{tag}: buggy start fails to build:\n{r_bad.out[-800:]}")
        if bug.reported:
            r_rep = run(merged(bad_tree, base.visible, bug.reported), verify, timeout=timeout)
            if r_rep.ok:
                problems.append(f"{tag}: the reported visible test passes on the bug")
        if r_sol.ms > 20000 or r_bad.ms > 20000:
            problems.append(f"{tag}: slow verify ({r_sol.ms} ms / {r_bad.ms} ms)")
    if problems:
        raise RuntimeError("\n---\n".join(problems))
    return out


def mix(items: list, picks: list[int]) -> list:
    return [items[i] for i in picks]
