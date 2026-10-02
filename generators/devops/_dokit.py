"""Shared machinery for the `devops` category: configuration files as the artefact, semantic validators as the judge.

Every task ships a hidden ``tests/check.py`` (a validator that interprets the configuration with real semantics, written
per family), the support library ``tests/dolib.py`` (reports, a ruby-backed YAML reader, small parsers) and whatever hidden
data the validator needs (rule sets, scenarios). The family README lists the rules the validator implements, so the task
is fair. ``finish`` runs the generation-time guards: the start state fails, the reference passes, every ``wrong`` variant
(a plausible bad fix) fails.
"""
from __future__ import annotations

from fx import Task, merged, run

from generators.devops import _yamlw

DOLIB = r'''
import json
import os
import re
import subprocess
import sys


class Report:
    def __init__(self):
        self.problems = []

    def check(self, cond, msg):
        if not cond:
            self.problems.append(msg)
        return bool(cond)

    def finish(self):
        if self.problems:
            print(f"FAIL: {len(self.problems)} problem(s)")
            for p in self.problems[:14]:
                print("  - " + p)
            if len(self.problems) > 14:
                print(f"  ... and {len(self.problems) - 14} more")
            sys.exit(1)
        print("ok")


def die(msg):
    print("FAIL: " + msg)
    sys.exit(1)


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        die(f"cannot read {path}: {e.strerror}")


def yaml_docs(path):
    """Parse a YAML file (all documents) with ruby's Psych. YAML 1.1 rules apply: `on`/`yes` are booleans and a
    boolean key becomes the string "true". Raises ValueError with the parser message on a syntax error."""
    here = os.path.dirname(os.path.abspath(__file__))
    p = subprocess.run(["ruby", os.path.join(here, "yaml2json.rb"), path], capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        try:
            msg = json.loads(p.stdout)["__error__"]
        except Exception:
            msg = p.stderr.strip()[:200]
        raise ValueError(msg)
    return json.loads(p.stdout)


def yaml_one(path):
    try:
        docs = yaml_docs(path)
    except ValueError as e:
        die(f"{path} is not valid YAML: {e}")
    if len(docs) != 1 or not isinstance(docs[0], dict):
        die(f"{path} must contain exactly one YAML mapping")
    return docs[0]


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]
'''


def devops_task(slug: str, d: int, prompt: str, start: dict, solution: dict, check: str, hidden: dict | None = None, *, lang: str = "text",
                kind: str = "fix", tags: list | None = None, notes: dict | None = None, verify: str = "python3 tests/check.py", **kw) -> Task:
    h = {"tests/check.py": check, "tests/dolib.py": DOLIB, "tests/yaml2json.rb": _yamlw.RUBY}
    h.update(hidden or {})
    return Task(slug=slug, prompt=prompt, difficulty=d, start=start, hidden=h, solution=solution, verify=verify, kind=kind, lang=lang,
                tags=["config", *(tags or [])], notes=notes or {}, **kw)


def finish(t: Task, wrong: list[dict] | tuple = ()) -> Task:
    """Generation-time guards for a devops task."""
    res = run(merged(t.start, t.hidden), t.verify, timeout=120, cache=False)
    if res.ok:
        raise RuntimeError(f"{t.slug}: the start state already passes the validator")
    res = run(merged(t.start, t.hidden, t.solution), t.verify, timeout=120, cache=False)
    if not res.ok:
        raise RuntimeError(f"{t.slug}: the reference solution fails its validator:\n{res.out[-1500:]}")
    for i, w in enumerate(wrong):
        res = run(merged(t.start, t.hidden, t.solution, w), t.verify, timeout=120, cache=False)
        if res.ok:
            raise RuntimeError(f"{t.slug}: validator accepted wrong variant #{i}")
    return t


# ----------------------------------------------------------------------------------------------------------------
# policy-driven repair families: model -> defect injection -> emitted configuration

import copy
import json
import random

STYLES = ("list", "para", "terse")


def fix_prompt(rng: random.Random, target: str, subject: str, texts: list[str], doc: str, vague: bool, vague_variants: list[str], tail: str = "") -> str:
    """Compose a bug-report style prompt. ``target`` is the file(s) to fix, ``doc`` the rules document."""
    if vague:
        return rng.choice(vague_variants)
    pol = f"`{doc}` lists the rules that the configuration is checked against"
    style = rng.choice(STYLES)
    if style == "list":
        return f"Problems with the {subject} (`{target}`):\n" + "\n".join(f"- {t}" for t in texts) + f"\n\nPlease fix them. {pol}.{tail}"
    if style == "para":
        return f"Reports about `{target}`: " + "; ".join(texts) + f". Can you sort it out? {pol}.{tail}"
    return f"{target}: " + "; ".join(texts) + f". Please fix it ({pol[0].lower() + pol[1:]}).{tail}"


def fix_tasks(rng: random.Random, n: int, *, prefix: str, plan: list, build, render, defects: dict, docs, hidden, check: str, prompt, wrong, tags: list,
              lang: str = "text") -> list[Task]:
    """Generic repair-task factory.

    plan      list of dicts ``{"keys": [defect, ...], "vague": bool, "d": difficulty or None}``
    build     (rng, i) -> (model, ctx)
    render    (model, ctx) -> {path: text}
    defects   key -> (fn(model, ctx, rng) -> info dict, [phrasings with {placeholders} filled from info])
    docs      (model, ctx) -> extra start files (rules document, README)
    hidden    (model, ctx) -> extra hidden files (rules.json ...)
    prompt    (rng, ctx, texts, vague) -> prompt text
    wrong     (model, ctx) -> list of {path: text} (plausible bad "fixes" the validator must reject)
    """
    out = []
    for i, item in enumerate(plan[:n]):
        keys = item["keys"]
        model, ctx = build(rng, i)
        good = render(model, ctx)
        bad_model = copy.deepcopy(model)
        applied, post = [], []
        for k in keys:
            info = defects[k][0](bad_model, ctx, rng) or {}
            if "_post" in info:
                post.append(info.pop("_post"))
            applied.append((k, info, info.pop("_phr", None)))
        bad = render(bad_model, ctx)
        for p in post:
            bad = p(bad)
        texts = [rng.choice(defects[k][1] if allowed is None else [defects[k][1][j] for j in allowed]).format(**{"a": "", "b": "", "c": "", **info}) for k, info, allowed in applied]
        d = item.get("d") or {1: 2, 2: 3, 3: 4, 4: 4, 5: 5}[min(len(keys), 5)]
        keys = [k for k, _, _ in applied]
        start = dict(bad)
        start.update(docs(model, ctx))
        sol = {k: v for k, v in good.items() if bad.get(k) != v}
        t = devops_task(f"{i + 1:02d}-" + "-".join(keys[:2]), d, prompt(rng, ctx, texts, item.get("vague", False)), start, sol, check, hidden(model, ctx), lang=lang,
                        kind="fix", tags=tags, notes={"defects": keys})
        ws = [{**good, **w} for w in wrong(model, ctx)]
        out.append(finish(t, wrong=[{k: v for k, v in w.items() if good.get(k) != v or True} for w in ws]))
    return out
