"""Derived i18n tasks: take an existing corpus task and give it a new prompt written in another language.

The repository, hidden files, reference solution, verifier, protected globs, budget, team, answer expectation and gold
answer are copied unchanged from the source record (read from ``corpus/<category>/<family>.jsonl`` by id); only the
prompt is new. Because the checks stay identical, the facts a checker needs (identifiers, file names, formats, numbers,
``answer.contains`` strings) must survive in the new prompt: ``§N`` / ``¶N`` tokens in a prompt template are replaced by
the N-th backtick span / fenced block of the *source* prompt, so code expressions are copied verbatim, never retyped.

Source shards are located lazily (one shard per source family) so a build does not read the whole corpus.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fx import Task

ROOT = Path(__file__).resolve().parents[2]
_SHARDS: dict[str, dict[str, dict]] = {}
_NAMES: list[tuple[str, Path]] | None = None


def _shard_names() -> list[tuple[str, Path]]:
    global _NAMES
    if _NAMES is None:
        _NAMES = sorted(
            ((p.stem, p) for p in (ROOT / "corpus").glob("*/*.jsonl") if p.parent.name != "i18n"),
            key=lambda x: -len(x[0]),
        )
    return _NAMES


def source(src_id: str) -> dict:
    """The record with this id; the id's family is the longest shard name that is a prefix of it."""
    for name, path in _shard_names():
        if src_id.startswith(name + "-"):
            if name not in _SHARDS:
                recs = {}
                for line in path.read_text(encoding="utf-8").split("\n"):  # not splitlines(): see build._line
                    if line.strip():
                        r = json.loads(line)
                        recs[r["id"]] = r
                _SHARDS[name] = recs
            if src_id in _SHARDS[name]:
                return _SHARDS[name][src_id]
    raise KeyError(f"i18n: source task {src_id!r} not found in corpus/")


_SPAN = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.S)


def spans(prompt: str) -> list[str]:
    return _SPAN.findall(_BLOCK.sub("", prompt))


def blocks(prompt: str) -> list[str]:
    return _BLOCK.findall(prompt)


def _fill(template: str, src_prompt: str) -> str:
    sp, bl = spans(src_prompt), blocks(src_prompt)

    def s(m):
        return sp[int(m.group(1))]

    def b(m):
        return bl[int(m.group(1))].rstrip("\n")

    out = re.sub(r"§(\d+)", s, template)
    out = re.sub(r"¶(\d+)", b, out)
    def seg(m):  # ⟦start|end⟧: the stretch of the source prompt from `start` up to (not including) `end`
        a = src_prompt.index(m.group(1))
        return src_prompt[a : src_prompt.index(m.group(2), a)].rstrip("\n")

    out = re.sub(r"⟦([^|⟧]+)\|([^⟧]+)⟧", seg, out)
    if "¤oneof" in out:  # the closed vocabulary of a diagnosis/review key, e.g. "(one of logic-error, off-by-one, ...)"
        m = re.search(r"\(one of ([^)]+)\)", src_prompt)
        out = out.replace("¤oneof", m.group(1))
    return out


def derive(src_id: str, prompt: str, slug: str, code: str, *, style: str = "", difficulty: int | None = None, tags: tuple = ()) -> Task:
    """Build the derived task. ``code`` is the prompt language code (fr, ja, ...); ``prompt`` may use §N / ¶N tokens."""
    r = source(src_id)
    files = r.get("files", {})
    budget = dict(r["budget"])
    notes = {"source": r["id"], "source_category": r["category"], "source_family": r["family"], "source_sha": r["sha"], "prompt_lang": code}
    if style:
        notes["style"] = style
    team = r.get("team")
    if team and team.get("mode") == "single":
        team = None
    return Task(
        prompt=_fill(prompt, r["prompt"]),
        difficulty=difficulty or r["difficulty"],
        slug=slug,
        start=dict(files.get("start", {})),
        hidden=dict(files.get("hidden", {})),
        solution=dict(files.get("solution", {})),
        verify=r.get("verify", ""),
        kind=r["kind"],
        lang=r["lang"],
        tags=[f"prompt-{code}", f"src-{r['category']}", "derived", *tags],
        protected=list(r.get("protected", [])),
        protect_tests=False,
        timeout_s=r.get("timeout_s", 120),
        budget=budget,
        team=team,
        setup=list(r.get("setup", [])),
        context_window=budget.get("context_window"),
        pass_mode=r.get("pass", ""),
        answer=dict(r["answer"]) if r.get("answer") else None,
        gold_answer=r.get("gold_answer", ""),
        notes=notes,
    )


def take(items: list, n: int) -> list:
    """Honour --scale: the first n items."""
    return items[: max(1, n)]
