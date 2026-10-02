"""Shared helpers for the games generators: skeletons, bug-injection tasks, prompt voices, tournament scoring."""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from fx import Task, dd, run
from fx.run import merged

from . import _scen

DATA = _scen.DATA_DIR


def go_mod(name: str) -> str:
    return f"module example.com/{name}\n\ngo 1.21\n"


def cargo_toml(name: str) -> str:
    return f'[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n'


GITIGNORE = {
    "python": "__pycache__/\n*.pyc\n",
    "javascript": "node_modules/\n",
    "go": "",
    "rust": "target/\n",
    "java": "build/\n",
    "c": "build/\n",
}


def data_files(lang: str, scripts: dict[str, str], solution: dict[str, str], adapter: dict[str, str], pkg: str = "") -> dict[str, str]:
    """{path: recorded scenario text} for each script ({file stem: script}); recorded on the reference solution.
    All scripts are recorded in one run of the reference (compiled languages are slow to start) and split afterwards."""
    stems = sorted(scripts)
    combined = "\n".join(scripts[k].rstrip("\n") for k in stems) + "\n"
    text = _scen.record(lang, solution, adapter, combined, pkg)
    blocks: list[list[str]] = []
    for line in text.split("\n"):
        if line.startswith("# scenario"):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
    out = {}
    pos = 0
    for k in stems:
        n = sum(1 for ln in scripts[k].split("\n") if ln.startswith("# scenario"))
        chunk = blocks[pos:pos + n]
        pos += n
        out[f"{DATA[lang]}/{k}.txt"] = "\n".join("\n".join(b).rstrip("\n") for b in chunk) + "\n"
    assert pos == len(blocks), "scenario count mismatch while splitting recordings"
    return out


# ---------------------------------------------------------------------------------------------------------- bugs

@dataclass
class Bug:
    """A hand-written defect: ``edits`` are (old, new) text replacements applied to ``path`` (each ``old`` must occur
    exactly once). ``symptom`` is what a user would see, in the user's words; ``title`` a short label."""

    id: str
    title: str
    symptom: str
    edits: list[tuple[str, str]]
    path: str = ""
    difficulty: int = 3
    rules: dict = field(default_factory=dict)  # instance parameters this bug needs to be observable
    detail: str = ""  # optional extra sentence for the ticket styles


def combine(*bugs: Bug, title: str = "", difficulty: int = 4) -> Bug:
    """Several independent defects at once (edits must not overlap): a harder task with a multi-part report."""
    parts = ["First", "Second", "Third", "Fourth"]
    sym = " ".join(f"{parts[i]}: {b.symptom.strip()}" for i, b in enumerate(bugs))
    rules: dict = {}
    for b in bugs:
        rules.update(b.rules)
    intro = {2: "Two separate problems.", 3: "Three separate problems.", 4: "Four separate problems."}[len(bugs)]
    return Bug(id="+".join(b.id for b in bugs), title=title or " / ".join(b.title.rstrip(".") for b in bugs), symptom=f"{intro} {sym}",
               edits=[e for b in bugs for e in b.edits], path=bugs[0].path, difficulty=min(5, max(difficulty, 2 + len(bugs))), rules=rules)


def _shift(text: str, k: int, unit: str = " ") -> str:
    """Re-indent the continuation lines (not the first line) of a multi-line edit by k units (spaces or tabs)."""
    lines = text.split("\n")
    out = [lines[0]]
    for ln in lines[1:]:
        if not ln.strip():
            out.append(ln)
        elif k >= 0:
            out.append(unit * k + ln)
        else:
            lead = len(ln) - len(ln.lstrip(unit))
            out.append(ln[min(lead, -k):])
    return "\n".join(out)


_SHIFTS = [(0, " "), (-4, " "), (-8, " "), (4, " "), (8, " "), (-12, " "), (12, " "), (-16, " "), (16, " "),
           (-1, "\t"), (1, "\t"), (-2, "\t"), (2, "\t"), (-3, "\t"), (3, "\t"), (-4, "\t"), (4, "\t")]


def apply_bug(src: str, bug: Bug) -> str:
    """Apply the edits; an edit written for a different indentation depth is re-indented until it matches exactly once."""
    out = src
    for old, new in bug.edits:
        for k, unit in _SHIFTS:
            o, n = _shift(old, k, unit), _shift(new, k, unit)
            if out.count(o) == 1:
                out = out.replace(o, n)
                break
        else:
            raise RuntimeError(f"bug {bug.id}: edit target occurs {out.count(old)} times: {old!r}")
    return out


_FAIL_RE = re.compile(r"step (\d+): > (.*)\n\s+expected: (.*)\n\s+got:\s+(.*)")


def visible_failure(out: str):
    """(command, expected, got) of the first failing step in a harness output, or None."""
    m = _FAIL_RE.search(out)
    if not m:
        return None
    return m.group(2).strip(), m.group(3).strip(), m.group(4).strip()


def _unesc(s: str) -> str:
    return s.replace("\\n", " / ").replace("\\\\", "\\")


def fix_prompt(style: str, bug: Bug, game: str, ctx: dict, vis: tuple | None, rng: random.Random) -> str:
    """Wrap a symptom in one of several voices. ``ctx``: readme, verify, files (list of source paths), noun."""
    readme = ctx.get("readme", "README.md")
    verify = ctx.get("verify", "the tests")
    src = ", ".join(f"`{p}`" for p in ctx.get("files", []))
    sym = bug.symptom.strip()
    tail = rng.choice([
        "Don't edit the tests.", "Please keep the public API as it is.", "The rules in the README are the source of truth.",
        "Fix the cause rather than special-casing.", "", "",
    ])
    if style == "visible" and vis:
        cmd, want, got = vis
        return (f"The example scenarios of the {game} engine are failing. After `{cmd}` the engine replies `{_unesc(got)}`, but the expected reply is "
                f"`{_unesc(want)}`. The behaviour is specified in {readme}. {sym} Find the defect in the engine and fix it. "
                f"There are more scenarios than the visible ones. {tail}").strip()
    if style == "ticket":
        extra = ("\n\n" + bug.detail.strip()) if bug.detail else ""
        cover = ("the example scenarios already show a mismatch, and there are more checks than those" if vis else "they don't cover this yet")
        return (f"**{bug.title}**\n\n{sym}{extra}\n\nThe expected behaviour is whatever {readme} says. The engine lives in {src}; "
                f"`{verify}` runs the scenario checks ({cover}). {tail}").strip()
    if style == "chat":
        return f"{sym} Can you find out why in the {game} engine and fix it? {tail}".strip()
    if style == "review":
        return (f"I was play-testing the {game} engine against {readme} and something is off: {sym} I haven't looked at the code yet. "
                f"Track it down and fix it; run `{verify}` when you are done. {tail}").strip()
    if style == "terse":
        return f"{game}: {bug.title.rstrip('.')}. {sym} Fix. {tail}".strip()
    if style == "handover":
        return (f"Handing this one over. The {game} engine ({src}) has a defect that a player noticed: {sym} "
                f"I couldn't spot it by reading the rules code. The spec is {readme}. {tail}").strip()
    return f"{sym} Fix the {game} engine so it follows {readme}. {tail}".strip()


STYLES = ["visible", "ticket", "chat", "review", "terse", "handover", "plain"]


def pick_style(rng: random.Random, vis, used: list[str]) -> str:
    opts = [s for s in STYLES if (s != "visible" or vis)]
    fresh = [s for s in opts if s not in used[-3:]]
    st = rng.choice(fresh or opts)
    used.append(st)
    return st


def bug_task(*, game: str, lang: str, base_files: dict[str, str], tests: dict[str, str], hidden: dict[str, str], bug: Bug,
             ctx: dict, rng: random.Random, used: list[str], k: int, verify: str = "", tags: list[str] | None = None,
             timeout_s: int = 120, extra_notes: dict | None = None, slug_prefix: str = "") -> Task:
    """One fix task for ``bug``. ``base_files`` is the correct project (non-test files), ``tests`` the visible test
    files (they must pass on the correct project), ``hidden`` the hidden scenario files. Verifies that the bug is caught
    by the hidden suite and that the correct project passes everything."""
    verify = verify or _scen.VERIFY[lang]
    good = run(merged(base_files, tests, hidden), verify, timeout=timeout_s)
    if not good.ok:
        raise RuntimeError(f"{game}: the correct project fails its own suites:\n{good.out[-2500:]}")
    path = bug.path or ctx["files"][0]
    buggy = apply_bug(base_files[path], bug)
    files = merged(base_files, {path: buggy})
    r = run(merged(files, tests, hidden), verify, timeout=timeout_s)
    if r.ok:
        raise RuntimeError(f"{game}: bug {bug.id} is not caught by the hidden scenarios")
    v = run(merged(files, tests), verify, timeout=timeout_s)
    vis = visible_failure(v.out) if not v.ok else None
    style = pick_style(rng, vis, used)
    prompt = fix_prompt(style, bug, game, ctx, vis, rng)
    # a failing visible scenario names the exact discrepancy: a small bug that is shown that way is trivial
    difficulty = 1 if (vis and bug.difficulty == 2) else bug.difficulty
    return Task(
        slug=f"{slug_prefix}{k + 1:02d}-{bug.id}",
        prompt=prompt,
        difficulty=difficulty,
        start=merged(files, tests),
        hidden=dict(hidden),
        solution={path: base_files[path]},
        verify=verify,
        timeout_s=timeout_s,
        tags=["bugfix", "engine", style, *(tags or [])],
        notes={"game": game, "bug": bug.id, "visible_fails": not v.ok, "style": style, **(extra_notes or {})},
    )


# ---------------------------------------------------------------------------------------------------------- tournaments

def clamp_score_expr() -> str:
    return "max(0.0, min(1.0, (rate - FLOOR) / (GOAL - FLOOR)))"


def vary(rng: random.Random, options: list):
    return options[rng.randrange(len(options))]


# ---------------------------------------------------------------------------------------------------------- greenfield prompts

def green_prompt(rng: random.Random, *, game: str, blurb: str, file: str, verify: str, used: list[str], extra: str = "",
                 api_word: str = "API") -> str:
    """A request to build ``game`` from its README. Voices differ; the facts do not."""
    extra = (" " + extra.strip()) if extra.strip() else ""
    voices = {
        "brief": (f"Please implement the headless engine for {game}, {blurb}. `README.md` has the complete rules and the exact {api_word}; "
                  f"the stub in `{file}` has the signatures. `{verify}` replays recorded scenarios against your engine: the ones in the repo are "
                  f"examples, the real check uses many more, so follow every sentence of the README (event texts and render layout are compared "
                  f"character by character).{extra}"),
        "dev": (f"I'm putting together {game}, {blurb}. The rules are written up in `README.md` but there is no code yet, only a stub in "
                f"`{file}`. Could you write the engine? Other tools parse the replies and the render output, so they have to match the README "
                f"exactly.{extra} I run `{verify}` to check.") ,
        "ticket": (f"Task: build the {game} engine.\n\nContext: {blurb}.\nDeliverable: `{file}` implementing the {api_word} in `README.md`.\n"
                   f"Acceptance: `{verify}` passes. It compares every reply with the documented text, so no improvising on wording or layout. "
                   f"The scenarios in the repo are samples of what is checked.{extra}"),
        "terse": f"{game} engine: rules and {api_word} in README.md, stub in `{file}`. Make `{verify}` pass (the visible scenarios are only samples).{extra}",
        "teacher": (f"I'm using {game} ({blurb}) as a worked example of a deterministic simulation. Write the engine in `{file}` so that it follows "
                    f"`README.md` to the letter, including the random number generator, which is specified exactly. A scenario runner "
                    f"(`{verify}`) is the judge.{extra}"),
        "qa": (f"We need a reference implementation of {game} that other ports can be diffed against. The specification is `README.md` "
               f"({blurb}); it is meant to be complete, so don't invent behaviour that it doesn't describe. Fill in `{file}`. "
               f"Run `{verify}` to compare with the recorded examples; more hidden scenarios cover the rest of the rules.{extra}"),
    }
    keys = [k for k in voices if k not in used[-3:]] or list(voices)
    k = keys[rng.randrange(len(keys))]
    used.append(k)
    return voices[k]


def last_score(out: str) -> float | None:
    import json as _json
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        return float(_json.loads(lines[-1])["score"])
    except Exception:  # noqa: BLE001
        return None


def check_scores(*, start: dict[str, str], hidden: dict[str, str], solution: dict[str, str], verify: str, name: str,
                 timeout_s: int = 120, max_start: float = 0.999) -> tuple[float, float, str]:
    """For json-score tasks: the reference solution must score 1.0, the untouched start strictly less. Returns
    (start score, solution score, solution output tail)."""
    a = run(merged(start, hidden), verify, timeout=timeout_s)
    b = run(merged(start, hidden, solution), verify, timeout=timeout_s)
    sa, sb = last_score(a.out), last_score(b.out)
    if sb is None or sb < 0.999999:
        raise RuntimeError(f"{name}: the reference solution scores {sb}:\n{b.out[-1500:]}")
    if sa is not None and sa > max_start:
        raise RuntimeError(f"{name}: the untouched start already scores {sa}:\n{a.out[-800:]}")
    return (sa if sa is not None else 0.0), sb, b.out


def tabs(src: str, width: int = 4) -> str:
    """Convert leading groups of ``width`` spaces to tabs (so Go/C sources can be written with spaces in generators)."""
    import re as _re
    out = []
    for line in src.split("\n"):
        m = _re.match(r"^( +)", line)
        if m and len(m.group(1)) >= width:
            n = len(m.group(1)) // width
            line = "\t" * n + " " * (len(m.group(1)) - n * width) + line[len(m.group(1)):]
        out.append(line)
    return "\n".join(out)


def edit_once(src: str, *pairs: tuple[str, str]) -> str:
    """Apply (old, new) replacements; every ``old`` must occur exactly once."""
    for old, new in pairs:
        if src.count(old) != 1:
            raise RuntimeError(f"edit target occurs {src.count(old)} times: {old!r}")
        src = src.replace(old, new)
    return src
