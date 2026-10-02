"""Slot modules: one source file written once as a template whose functions can each be correct or carry a planted defect.

A *slot* is a block of whole lines (usually one function, sometimes a few lines inside one) that the template marks with
a line ``@@name@@``.  For each slot the author writes

* ``good``  the correct code,
* ``bad``   one or more defective variants (each tagged with a review category and a one-line explanation),
* ``old``   what the block was before the change under review ("" when the block is new code),
* ``nit``   a harmless variant of ``good`` (a style nit: odd naming, redundant parentheses, an extra comment),
* ``trap``  a variant of ``good`` that *looks* suspicious but is right.

Review tasks render a head (the repository after the change) and a base (before it) and hand the agent the head plus a
``change.patch``; debug tasks render one defective head and run a scenario to produce runtime evidence.
"""
from __future__ import annotations

import difflib
import re
import textwrap
from dataclasses import dataclass, field

from fx import dd


@dataclass
class Bad:
    text: str
    cat: str  # review category: logic security concurrency resource-leak api-misuse off-by-one validation performance error-handling
    why: str  # one sentence: what is wrong
    kw: tuple = ()  # words a good answer plausibly uses (identifiers, concepts)
    kind: str = ""  # debug taxonomy value (defaults from cat)
    obs: bool = False  # python: the module's scenario output differs from the correct one
    imports: str = ""  # replacement text of the module's "imports" slot when this variant needs different imports


@dataclass
class Slot:
    name: str
    func: str  # function (or Class.method) that contains the block
    good: str
    bad: list = field(default_factory=list)
    old: str | None = None  # None: unchanged by the change under review; "": new code; else: the previous version
    nit: str = ""
    trap: str = ""
    note: str = ""  # one bullet for the PR description when this block is part of the change
    deps: tuple = ()  # slots that must be part of the change whenever this one is


@dataclass
class Module:
    name: str
    lang: str
    path: str  # the file the template renders to
    title: str  # PR title
    intro: str  # PR description: why
    outro: str  # PR description: testing notes, remarks
    template: str
    slots: list
    ctx: dict = field(default_factory=dict)  # unchanged files of the repository (README, build files, neighbours)
    new_file: bool = False  # the file does not exist before the change
    scenario: str = ""  # python: a script that exercises the module (debug tasks)
    scenario_path: str = "scenario.py"
    blurb: str = ""  # one sentence about the project, for prompts
    difficulty: int = 2  # how hard the file is to read

    def changed(self) -> list:
        """Slots that belong to the change under review (all of them for a new file)."""
        return [s for s in self.slots if s.name != "imports" and (self.new_file or s.old is not None)]

    def slot(self, name: str) -> Slot:
        for s in self.slots:
            if s.name == name:
                return s
        raise KeyError(name)


KIND_OF_CAT = {
    "logic": "logic-error", "security": "security", "concurrency": "race-condition", "resource-leak": "resource-leak",
    "api-misuse": "api-misuse", "off-by-one": "off-by-one", "validation": "missing-validation", "performance": "performance",
    "error-handling": "error-handling",
}

_MARK = re.compile(r"^(\s*)@@(\w+)@@\s*$")


def _tabs(line: str) -> str:
    n = len(line) - len(line.lstrip(" "))
    return "\t" * (n // 4) + " " * (n % 4) + line[n:]


def render(template: str, texts: dict[str, str], lang: str = "") -> tuple[str, dict[str, tuple[int, int]]]:
    """Fill the template; returns (text, {slot: (first_line, last_line)}) with 1-based inclusive lines.
    Go sources are written with 4-space indentation and converted to tabs here."""
    out: list[str] = []
    spans: dict[str, tuple[int, int]] = {}
    for line in template.split("\n"):
        m = _MARK.match(line)
        if not m:
            out.append(line)
            continue
        txt = texts.get(m.group(2), "")
        if not txt.strip():
            continue
        body = txt.rstrip("\n").split("\n")
        start = len(out) + 1
        for b in body:
            out.append(m.group(1) + b if b.strip() else "")
        spans[m.group(2)] = (start, len(out))
    if lang == "go":
        out = [_tabs(x) for x in out]
    text = "\n".join(out).rstrip("\n") + "\n"
    return text, spans


_COMMENT = {"python": "#", "go": "//", "javascript": "//", "java": "//", "rust": "//", "typescript": "//"}
_NIT_TEXT = ("TODO: tidy this up", "XXX: revisit the naming here", "FIXME: not pretty, but it works")


def auto_nit(text: str, lang: str, salt: int = 0) -> str:
    """A harmless style nit for any block: a stray TODO-style comment after the signature line ("" if there is no such line)."""
    c = _COMMENT.get(lang)
    lines = text.rstrip("\n").split("\n")
    if not c:
        return ""
    for i, ln in enumerate(lines):
        t = ln.strip()
        if t.startswith(("//", "///", "/*", "*", "#", "@")) or not t:
            continue
        if t.endswith(("{", ":")) and i + 1 < len(lines):
            indent = len(lines[i + 1]) - len(lines[i + 1].lstrip())
            note = _NIT_TEXT[(len(text) + salt) % len(_NIT_TEXT)]
            return "\n".join(lines[: i + 1] + [" " * indent + f"{c} {note}"] + lines[i + 1:]) + "\n"
        return ""
    return ""


def slot_texts(mod: Module, choice: dict, base: bool = False) -> dict[str, str]:
    """choice: slot name -> "good" | "nit" | "trap" | ("bad", index).  Missing slots are good."""
    out = {}
    for s in mod.slots:
        if base:
            out[s.name] = s.good if s.old is None else s.old
            continue
        c = choice.get(s.name, "good")
        if c == "good":
            out[s.name] = s.good
        elif c == "nit":
            out[s.name] = s.nit or auto_nit(s.good, mod.lang) or s.good
        elif c == "trap":
            out[s.name] = s.trap or s.good
        else:
            b = s.bad[c[1]]
            out[s.name] = b.text
            if b.imports:
                out["imports"] = b.imports
    return out


def unified_diff(path: str, base: str | None, head: str, n: int = 3) -> str:
    if base is None:
        a, b = [], head.split("\n")[:-1]
        body = list(difflib.unified_diff(a, b, "/dev/null", f"b/{path}", lineterm="", n=n))
        hdr = f"diff --git a/{path} b/{path}\nnew file mode 100644\n"
    else:
        a, b = base.split("\n")[:-1], head.split("\n")[:-1]
        body = list(difflib.unified_diff(a, b, f"a/{path}", f"b/{path}", lineterm="", n=n))
        hdr = f"diff --git a/{path} b/{path}\n"
    if not body:
        return ""
    return hdr + "\n".join(body) + "\n"


def description(title: str, intro: str, notes: list[str], outro: str) -> str:
    bullets = "\n".join(f"* {n}" for n in notes)
    parts = [f"# {title}", intro.strip(), bullets, outro.strip()]
    return "\n\n".join(p for p in parts if p) + "\n"


def validate_module(mod: Module) -> None:
    """Authoring checks: every marker has a slot, every variant really differs from the good text."""
    marks = set(re.findall(r"^\s*@@(\w+)@@\s*$", mod.template, re.M))
    names = [s.name for s in mod.slots]
    assert marks == set(names), (mod.name, marks ^ set(names))
    assert len(set(names)) == len(names), mod.name
    problems = []
    for s in mod.slots:
        for bi, b in enumerate(s.bad):
            if b.text == s.good:
                problems.append((s.name, "bad", bi, "== good", b.why[:40]))
            if b.cat not in KIND_OF_CAT:
                problems.append((s.name, "bad", bi, "category", b.cat))
        if s.nit and s.nit == s.good:
            problems.append((s.name, "nit == good"))
        if s.trap and s.trap == s.good:
            problems.append((s.name, "trap == good"))
        if s.old is not None and s.old != "" and s.old == s.good:
            problems.append((s.name, "old == good"))
    assert not problems, (mod.name, problems)


def sub(text: str, old: str, new: str) -> str:
    """Edit helper for authoring variants: replace a block of lines, ignoring indentation.

    The lines of ``old`` are matched against consecutive lines of ``text`` after stripping both; the matched block is
    replaced by ``new`` (dedented, then indented like the first matched line).  A one-line ``old`` that is not a whole
    line is replaced as plain text.  Raises when nothing matches, so a variant can never silently equal the original."""
    old_lines = [x.strip() for x in old.strip("\n").split("\n")]
    t = text.split("\n")
    for i in range(len(t) - len(old_lines) + 1):
        if [x.strip() for x in t[i:i + len(old_lines)]] == old_lines:
            indent = t[i][: len(t[i]) - len(t[i].lstrip())]
            body = textwrap.dedent(new.strip("\n")).split("\n") if new.strip() else []
            repl = [(indent + b) if b.strip() else "" for b in body]
            return "\n".join(t[:i] + repl + t[i + len(old_lines):])
    if len(old_lines) == 1 and old in text:
        return text.replace(old, new, 1)
    raise AssertionError(f"sub: pattern not found: {old!r}")
