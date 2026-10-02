"""Native bug-fix families: one correct library written for speakers of one language (README, domain blurb, comments
and test data in that language, identifiers in English), turned into many fix tasks by token mutation, with the report
written in that language.

This reuses the machinery of ``fx.lib`` (mutants that build, are caught by the hidden suite and do not hang) but
renders the prompt from the per-language phrase book in ``_phrases``; the style (CI excerpt, user report with probe
expressions, terse bug line, vague drift, ...) is picked per task, as in ``fx.lib``.
"""
from __future__ import annotations

import random
import re

from fx import Family, Task, mutate, register
from fx.lib import BUILD, _probe_diffs, _sanitize_excerpt
from fx.run import merged, run

from ._phrases import PHRASES

_STYLES = ["ci", "report", "visible", "spec", "vague", "terse", "review"]
_STYLE_D = {"ci": 0, "report": 0, "visible": -1, "spec": 1, "vague": 1, "terse": 0, "review": 0}


def _diff_line(ph: dict, e: str, good: str, bad: str) -> str:
    if bad.startswith("raises "):
        return ph["d_raises"].format(e=e, bad=bad[7:], good=good)
    if good.startswith("raises "):
        return ph["d_expect_raise"].format(e=e, bad=bad, good=good[7:])
    return ph["d_wrong"].format(e=e, bad=bad, good=good)


def _prompt(style: str, lib, code: str, m, excerpt: str, diffs, visible_fail: bool, rng: random.Random) -> str:
    ph = PHRASES[code]
    end = rng.choice(ph["end"])
    kw = dict(title=lib.title, blurb=lib.blurb, path=m.path, verify=lib.verify, end=end, excerpt=excerpt)

    def pick(key):
        return rng.choice(ph[key])

    def tidy(s: str) -> str:
        return re.sub(r"[ \t]+\n", "\n", s).strip()

    if style == "ci" and excerpt:
        return tidy(pick("ci").format(**kw))
    if style == "report" and diffs:
        lines = "\n".join("- " + _diff_line(ph, e, g, b) for e, g, b in diffs[: lib.max_probe_diffs])
        return tidy(pick("report").format(lines=lines, **kw))
    if style == "visible" and visible_fail:
        return tidy(pick("visible").format(**kw))
    if style == "spec":
        return tidy(pick("spec").format(**kw))
    if style == "vague":
        return tidy(pick("vague").format(**kw))
    if style == "terse" and diffs:
        e, g, b = diffs[0]
        return tidy(pick("terse").format(diff1=_diff_line(ph, e, g, b), **kw))
    if style == "review" and excerpt:
        sal = [ln for ln in excerpt.splitlines() if re.search(r"Error|error|expected|got|want|panick|!==|!=", ln)] or excerpt.splitlines()
        return tidy(pick("review").format(sal=sal[-1].strip()[:160], **kw))
    return ""


def native_mutation_tasks(lib, rng: random.Random, n: int, code: str) -> list[Task]:
    """Up to ``n`` fix tasks from ``lib`` with reports in language ``code``. Raises if the library is not sound."""
    base_tree = merged(lib.files, lib.visible_tests, lib.hidden_tests)
    vis_tree = merged(lib.files, lib.visible_tests)
    base = run(base_tree, lib.verify, timeout=lib.timeout_s)
    if not base.ok:
        raise RuntimeError(f"lib {lib.name}: hidden+visible suite fails on the correct implementation:\n{base.out[-1500:]}")
    vbase = run(vis_tree, lib.verify, timeout=lib.timeout_s)
    leash = int(max(8, min(lib.timeout_s, 8 * (base.ms / 1000.0) + 6)))
    if not vbase.ok:
        raise RuntimeError(f"lib {lib.name}: visible suite fails on the correct implementation:\n{vbase.out[-1500:]}")

    cands: list[mutate.Mutant] = []
    for path in lib.mutate:
        cands += mutate.mutants(lib.lang, path, lib.files[path], rng)
    rng.shuffle(cands)
    limit = 90
    buildcmd = BUILD.get(lib.lang, "")
    hidden_paths = sorted(lib.hidden_tests)

    good: list = []
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
        styles = [s for s in _STYLES if _prompt(s, lib, code, m, excerpt, diffs, visible_fail, random.Random(0))]
        style = rng.choice(styles) if styles else "spec"
        prompt = _prompt(style, lib, code, m, excerpt, diffs, visible_fail, rng) or _prompt("spec", lib, code, m, excerpt, diffs, visible_fail, rng)
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
            tags=[f"prompt-{code}", "native", "mutation", "bugfix", style, *lib.tags],
            notes={"library": lib.name, "mutation": m.desc, "style": style, "visible_fails": visible_fail, "prompt_lang": code},
        ))
    return tasks


def register_native(lib, code: str, suffix: str, n: int = 8, summary: str = "") -> None:
    """Register ``i18n-<code>-<suffix>``: bug-fix tasks from ``lib`` reported in language ``code``."""
    fam = Family(name=f"i18n-{code}-{suffix}", category="i18n", lang=lib.lang, kind="fix", n=n,
                 summary=summary or f"native: injected bugs in {lib.title}, reports in {code}")

    def gen(rng, count, _lib=lib, _code=code):
        return native_mutation_tasks(_lib, rng, count, _code)

    gen.__module__ = lib.__class__.__module__
    register(fam, gen)
