"""fx core: the Task and Family types generators are written against, the registry, and validation.

A generator module registers one or more *families* with the ``@family`` decorator. A family is a function
``gen(rng, n) -> Iterable[Task]`` that must be deterministic given ``rng``. ``tools/build.py`` runs every family and
writes one JSONL shard per family under ``corpus/<category>/<family>.jsonl``; ``tools/admit.py`` proves the shard's
tasks sound with ``sleipnir rl tasks check`` (the verifier fails on the start state and passes with the reference
solution).

Three task modes:

* ``fixture`` (default): the agent edits a repository; the verifier command runs in a clean checkout with the hidden
  files written over it. Exit 0 is a pass.
* ``answer``: the agent's *final message* must contain every string in ``answer["contains"]`` (and, when ``verify`` is
  given, the verifier command must also pass on the final workspace). Used for questions, chat, research, recall.
* ``rubric``: not machine-verifiable by Sleipnir alone (open-ended chat, writing, advice). Carries a rubric and cheap
  deterministic ``checks`` for a model judge or the cheap scorer in ``tools/score_rubric.py``.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import textwrap
from dataclasses import dataclass, field
from typing import Callable, Iterable

SCHEMA = "sleipnir-training/1"

# category -> one line description. A category is a directory under generators/ and corpus/.
CATEGORIES: dict[str, str] = {
    "fix": "find and repair a bug in existing code (injected regressions, logic bugs, spec drift)",
    "feature": "extend an existing codebase with a described feature",
    "greenfield": "build a small program or library from a specification",
    "games": "build or repair the logic of a game (headless engine API, hidden rule tests)",
    "refactor": "restructure code while behaviour stays the same",
    "optimize": "make code faster or leaner without changing results",
    "testing": "write tests (scored against hidden mutants) or repair a broken test suite",
    "review": "review a change or a file and report the real defects",
    "debug": "diagnose a failure from logs, traces and code and state the root cause",
    "data": "SQL, ETL, CSV/JSON wrangling, reports, spreadsheets-as-code",
    "shell": "shell, text-processing pipelines, Makefiles, small CLI tools",
    "devops": "configuration, CI, packaging, containers-as-text, infrastructure descriptions",
    "port": "translate code between languages or APIs, behaviour preserved",
    "security": "find and fix vulnerabilities, harden code, with exploit tests",
    "docs": "write or repair documentation, docstrings, changelogs, with mechanical checks",
    "research": "answer questions and write reports from a local corpus of documents",
    "recall": "long-context and memory: facts spread across many files, small context windows",
    "swarm": "multi-component projects for a manager and workers",
    "robust": "honesty, injection resistance, impossible or underspecified requests, restraint",
    "chat": "conversation: questions, explanations, advice, small talk, constrained answers",
    "explain": "understand a codebase: call graphs, data flow, what-prints, where-defined, impact of a change",
    "i18n": "prompts written in other languages (the repository and the checks are the same kind as elsewhere)",
    "project": "long-horizon builds and migrations: several modules, hundreds of hidden checks, d4-d5",
}

LANGS = {
    "python", "go", "javascript", "typescript", "rust", "java", "c", "cpp", "ruby", "php", "bash", "sql",
    "text", "mixed",
}

MODES = ("fixture", "answer", "rubric")

# Defaults by difficulty 1..5
_STEPS = {1: 20, 2: 30, 3: 45, 4: 70, 5: 100}
_WALL = {1: 300, 2: 600, 3: 900, 4: 1500, 5: 2400}

# Files an agent must not edit: the visible tests of a task. Matches the usual layouts of every language we use.
TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|spec|specs|__tests__|testdata)/"
    r"|(^|/)test_[^/]*$"
    r"|_test\.[A-Za-z]+$"
    r"|\.test\.[cm]?[jt]s$"
    r"|(^|/)[^/]*Tests?\.(java|php)$"
    r"|_spec\.rb$"
)

PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,95}$")
GLOB_SPECIAL = re.compile(r"([\\*?\[\]{}])")


class FxError(Exception):
    pass


@dataclass
class Task:
    """One task instance. ``slug`` is unique inside its family; the global id is ``<family>-<slug>``."""

    prompt: str
    difficulty: int  # 1 trivial .. 5 expert; see docs/DESIGN.md
    slug: str = ""
    start: dict[str, str] = field(default_factory=dict)
    hidden: dict[str, str] = field(default_factory=dict)
    solution: dict[str, str] = field(default_factory=dict)
    verify: str = ""
    kind: str = ""  # defaults to the family's
    lang: str = ""  # defaults to the family's
    tags: list[str] = field(default_factory=list)
    protected: list[str] = field(default_factory=list)  # extra globs; hidden paths are always protected
    protect_tests: bool = True  # also protect every start file that looks like a test
    timeout_s: int = 120
    budget: dict | None = None
    team: dict | None = None  # {"mode": "swarm", "agents": 4, "roles": [...]}
    setup: list[str] = field(default_factory=list)
    context_window: int | None = None  # low values force compaction
    pass_mode: str = ""  # "" (exit0) or "json-score": the verifier prints {"score": 0..1} as its last line
    answer: dict | None = None  # {"contains": [...], "fold": bool}: mode "answer"
    gold_answer: str = ""  # a final message that satisfies `answer`; admission checks it
    rubric: list[dict] | None = None  # mode "rubric": [{"criterion": str, "weight": number}]
    checks: dict | None = None  # mode "rubric": cheap deterministic checks, see tools/score_rubric.py
    notes: dict = field(default_factory=dict)  # provenance: parameters, seed, mutation, source of facts

    def with_(self, **kw) -> "Task":
        d = dict(self.__dict__)
        d.update(kw)
        return Task(**d)


@dataclass
class Family:
    name: str
    category: str
    lang: str
    kind: str
    summary: str
    n: int
    mode: str = "fixture"
    module: str = ""
    fn: Callable | None = None


REGISTRY: dict[str, Family] = {}


def family(name: str, *, category: str, lang: str, kind: str = "fix", n: int = 8, summary: str = "", mode: str = "fixture"):
    """Register a generator function as a family. ``kind`` is one of fix|feature|refactor|greenfield for fixtures;
    other modes may use any short label (it becomes a tag)."""

    def deco(fn):
        if name in REGISTRY and REGISTRY[name].fn is not fn:
            raise FxError(f"family {name!r} is registered twice ({REGISTRY[name].module} and {fn.__module__})")
        REGISTRY[name] = Family(name=name, category=category, lang=lang, kind=kind, summary=summary or (fn.__doc__ or "").strip().split("\n")[0],
                                n=n, mode=mode, module=fn.__module__, fn=fn)
        return fn

    return deco


def register(fam: Family, fn: Callable) -> None:
    """Imperative registration (for libraries that make many families, e.g. one per library)."""
    fam.fn = fn
    fam.module = fn.__module__
    if fam.name in REGISTRY and REGISTRY[fam.name].fn is not fn:
        raise FxError(f"family {fam.name!r} is registered twice")
    REGISTRY[fam.name] = fam


def rng_for(name: str, seed: str = "sleipnir-training/1") -> random.Random:
    h = hashlib.sha256(f"{seed}\0{name}".encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def dd(s: str) -> str:
    """Dedent a triple-quoted block and drop the leading newline. Keeps one trailing newline."""
    s = textwrap.dedent(s)
    if s.startswith("\n"):
        s = s[1:]
    return s.rstrip("\n") + "\n"


def default_budget(difficulty: int, team: dict | None, context_window: int | None) -> dict:
    steps = _STEPS[difficulty]
    wall = _WALL[difficulty]
    if team and team.get("mode") == "swarm":
        steps, wall = steps * 2, wall * 2
    b = {"steps": steps, "requests": int(steps * 2.5), "wall_s": wall}
    if context_window:
        b["context_window"] = int(context_window)
    return b


def fixture_difficulty(d: int) -> str:
    return "easy" if d <= 2 else "medium" if d == 3 else "hard"


def escape_glob(p: str) -> str:
    return GLOB_SPECIAL.sub(r"\\\1", p)


def protected_globs(t: Task) -> list[str]:
    out = list(t.protected)
    if t.protect_tests:
        for p in sorted(t.start):
            if TEST_PATH_RE.search(p) and p not in t.hidden:
                out.append(escape_glob(p))
    seen, res = set(), []
    for g in out:
        if g not in seen:
            seen.add(g)
            res.append(g)
    return res


def shingles(text: str, k: int = 5) -> set[str]:
    words = re.findall(r"[a-z0-9_]+", text.lower())
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / max(1, len(a | b))


_BAD_VERIFY = re.compile(r"\b(curl|wget|pip3? install|npm (i|install)|apt(-get)?|yarn add|go get|cargo (add|install)|git clone|ssh|scp)\b")
_ABS_HOME = re.compile(r"(?<![\w.~/-])/(?:home/[A-Za-z0-9_.-]+|root|Users/[A-Za-z0-9_.-]+)(?=/)|/tmp/claude")


def validate_task(t: Task, fam: Family) -> list[str]:
    """Problems with one task, empty if it is acceptable. Generators are expected to produce zero."""
    p: list[str] = []
    mode = fam.mode
    if not (1 <= t.difficulty <= 5):
        p.append(f"difficulty {t.difficulty} not in 1..5")
    if mode not in MODES:
        p.append(f"unknown mode {mode!r}")
    if fam.category not in CATEGORIES:
        p.append(f"unknown category {fam.category!r}")
    lang = t.lang or fam.lang
    if lang not in LANGS:
        p.append(f"unknown lang {lang!r} (known: {sorted(LANGS)})")
    kind = t.kind or fam.kind
    if mode == "fixture" and kind not in ("fix", "feature", "refactor", "greenfield"):
        p.append(f"kind {kind!r}: fixtures use fix|feature|refactor|greenfield")
    minp = 60 if mode == "fixture" else 8
    if len(t.prompt.strip()) < minp:
        p.append(f"prompt shorter than {minp} characters")
    if re.search(r"\b(TODO|FIXME|XXX|lorem ipsum|placeholder)\b", t.prompt, re.I):
        p.append("prompt contains a placeholder word")
    if "{" in t.prompt and re.search(r"\{[a-z_]+\}", t.prompt):
        p.append("prompt has an unfilled {placeholder}")
    for tree_name, tree in (("start", t.start), ("hidden", t.hidden), ("solution", t.solution)):
        for path, content in tree.items():
            if not PATH_RE.match(path) or ".." in path.split("/") or path.startswith("/") or path.startswith(".git/") or "//" in path:
                p.append(f"{tree_name}: bad path {path!r}")
            if not isinstance(content, str):
                p.append(f"{tree_name}/{path}: content is not str")
                continue
            if "\x00" in content:
                p.append(f"{tree_name}/{path}: NUL byte")
            if len(content) > 400_000:
                p.append(f"{tree_name}/{path}: larger than 400 KB")
            if _ABS_HOME.search(content):
                p.append(f"{tree_name}/{path}: contains a machine-specific absolute path")
            if path.endswith(".py"):
                try:
                    compile(content, path, "exec")
                except SyntaxError as e:
                    if "fx: nocompile" not in content:
                        p.append(f"{tree_name}/{path}: python syntax error: {e}")
            if path.endswith(".json") and "fx: nojson" not in content:
                try:
                    json.loads(content)
                except Exception as e:  # noqa: BLE001
                    p.append(f"{tree_name}/{path}: invalid JSON: {e}")
    if sum(len(c) for tree in (t.start, t.hidden, t.solution) for c in tree.values()) > 4_000_000:
        p.append("task files total more than 4 MB")
    if len(t.start) + len(t.hidden) + len(t.solution) > 300:
        p.append("more than 300 files")

    if mode == "fixture":
        if not t.start:
            p.append("fixture needs start files")
        if not t.hidden:
            p.append("fixture needs hidden files (the verifier must not be visible to the agent)")
        if not t.solution:
            p.append("fixture needs a reference solution (whole files that differ from start)")
        if not t.verify.strip():
            p.append("fixture needs a verify command")
        same = [k for k, v in t.solution.items() if t.start.get(k) == v]
        if same:
            p.append(f"solution files identical to start: {same}")
        for k, v in t.hidden.items():
            for sk, sv in t.start.items():
                if sv == v and len(v) > 40:
                    p.append(f"hidden file {k} is identical to start file {sk} (leaked)")
        for k in t.hidden:
            if k in t.prompt:
                p.append(f"prompt names the hidden file {k}")
        if t.pass_mode not in ("", "json-score"):
            p.append(f"pass_mode {t.pass_mode!r}")
    if mode == "answer":
        if not t.answer or not t.answer.get("contains"):
            p.append("answer mode needs answer={'contains': [...]}")
        else:
            cs = t.answer["contains"]
            if any((not isinstance(c, str)) or not c.strip() for c in cs):
                p.append("answer.contains has an empty or non-string entry")
            fold = bool(t.answer.get("fold"))
            hay = t.prompt.lower() if fold else t.prompt
            for c in cs:
                if isinstance(c, str) and c.strip() and (c.lower() if fold else c) in hay and len(c) > 3:
                    p.append(f"answer string {c!r} appears in the prompt (trivial)")
            if not t.gold_answer:
                p.append("answer mode needs gold_answer (a message that satisfies answer)")
            else:
                g = t.gold_answer.lower() if fold else t.gold_answer
                for c in cs:
                    if isinstance(c, str) and (c.lower() if fold else c) not in g:
                        p.append(f"gold_answer lacks {c!r}")
        if t.verify and not t.hidden:
            p.append("answer mode with verify needs hidden files for the verifier")
    if mode == "rubric":
        if not t.rubric or not all(isinstance(r, dict) and r.get("criterion") for r in t.rubric):
            p.append("rubric mode needs rubric=[{'criterion': ..., 'weight': ...}]")
    if t.verify:
        if _BAD_VERIFY.search(t.verify):
            p.append("verify command uses the network or installs packages")
        if _ABS_HOME.search(t.verify):
            p.append("verify command has a machine-specific absolute path")
    if t.timeout_s < 5 or t.timeout_s > 1800:
        p.append("timeout_s outside 5..1800")
    if t.context_window is not None and not (4000 <= t.context_window <= 1_000_000):
        p.append("context_window outside 4000..1000000")
    if t.team:
        if t.team.get("mode") not in ("single", "swarm"):
            p.append("team.mode must be single or swarm")
    return p


def record_of(t: Task, fam: Family, task_id: str) -> dict:
    """The canonical on-disk record of a task (one JSONL line of a corpus shard)."""
    lang = t.lang or fam.lang
    kind = t.kind or fam.kind
    mode = fam.mode
    team = t.team or {"mode": "single"}
    budget = t.budget or default_budget(t.difficulty, team, t.context_window)
    if t.context_window and "context_window" not in budget:
        budget = {**budget, "context_window": int(t.context_window)}
    tags = sorted({fam.category, kind, lang, f"d{t.difficulty}", mode, *t.tags})
    rec = {
        "schema": SCHEMA,
        "id": task_id,
        "family": fam.name,
        "category": fam.category,
        "mode": mode,
        "kind": kind,
        "lang": lang,
        "difficulty": t.difficulty,
        "prompt": t.prompt.strip("\n") + "\n" if "\n" in t.prompt else t.prompt.strip(),
        "tags": tags,
        "team": team,
        "budget": budget,
    }
    if mode in ("fixture", "answer"):
        rec["verify"] = t.verify.strip()
        rec["timeout_s"] = t.timeout_s
        rec["protected"] = protected_globs(t)
        rec["setup"] = list(t.setup)
        rec["pass"] = t.pass_mode
        rec["files"] = {
            "start": dict(sorted(t.start.items())),
            "hidden": dict(sorted(t.hidden.items())),
            "solution": dict(sorted(t.solution.items())),
        }
    if mode == "answer":
        rec["answer"] = {"contains": list(t.answer["contains"]), "fold": bool(t.answer.get("fold"))}
        rec["gold_answer"] = t.gold_answer
    if mode == "rubric":
        rec["rubric"] = t.rubric
        rec["checks"] = t.checks or {}
        rec["files"] = {"start": dict(sorted(t.start.items()))}
    if t.notes:
        rec["notes"] = t.notes
    body = json.dumps(rec, sort_keys=True, ensure_ascii=False)
    rec["sha"] = hashlib.sha256(body.encode()).hexdigest()[:16]
    return rec


def run_family(fam: Family, n: int | None = None) -> tuple[list[dict], list[str]]:
    """Run one family, validate, and return (records, problems)."""
    assert fam.fn is not None
    rng = rng_for(fam.name)
    tasks = list(fam.fn(rng, n if n is not None else fam.n))
    problems: list[str] = []
    recs: list[dict] = []
    seen_slugs: set[str] = set()
    seen_trees: dict[str, str] = {}
    for i, t in enumerate(tasks):
        slug = t.slug or f"{i + 1:03d}"
        slug = re.sub(r"[^a-z0-9._-]+", "-", slug.lower()).strip("-")
        tid = f"{fam.name}-{slug}"
        if not ID_RE.match(tid):
            problems.append(f"{tid}: bad id")
            continue
        if slug in seen_slugs:
            problems.append(f"{tid}: duplicate slug")
            continue
        seen_slugs.add(slug)
        tp = validate_task(t, fam)
        tree_hash = hashlib.sha256(json.dumps([t.prompt, sorted(t.start.items()), sorted(t.hidden.items()), t.answer, t.verify], sort_keys=True).encode()).hexdigest()
        if tree_hash in seen_trees:
            tp.append(f"identical prompt, files and verifier to {seen_trees[tree_hash]}")
        seen_trees.setdefault(tree_hash, tid)
        problems.extend(f"{tid}: {x}" for x in tp)
        if not tp:
            recs.append(record_of(t, fam, tid))
    recs.sort(key=lambda r: r["id"])
    return recs, problems
