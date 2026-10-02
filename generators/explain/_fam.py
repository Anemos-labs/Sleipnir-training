"""Small helpers shared by the explain families: language and size plans, difficulty, prompt phrases, repo picking."""
from __future__ import annotations

import random

from . import _repos as RP

LANGS = RP.LANG_ORDER

TIER_DIFF = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}


def lang_plan(rng: random.Random, n: int, allowed: list | None = None) -> list:
    """n languages, balanced, in a shuffled but deterministic order"""
    pool = list(allowed or LANGS)
    out: list = []
    while len(out) < n:
        block = list(pool)
        rng.shuffle(block)
        out.extend(block)
    return out[:n]


BASE_SPREAD = (15, 25, 30, 20, 10)


def tier_plan(rng: random.Random, n: int, weights: tuple = BASE_SPREAD) -> list:
    """repository sizes 1..5 following the corpus difficulty spread (15/25/30/20/10 %). A zero in ``weights`` forbids that size
    (its share moves proportionally to the allowed ones); other values are ignored so every family lands on the same global spread.
    Remainders are drawn at random so small families do not all round the same way. Deterministic given rng."""
    allowed = [t for t, w in enumerate(weights, 1) if w > 0]
    mass = sum(BASE_SPREAD[t - 1] for t in allowed)
    exact = {t: n * BASE_SPREAD[t - 1] / mass for t in allowed}
    counts = {t: int(exact[t]) for t in allowed}
    left = n - sum(counts.values())
    pool = list(allowed)
    while left > 0:
        w = [exact[t] - counts[t] + 0.05 for t in pool]
        t = rng.choices(pool, w)[0]
        counts[t] += 1
        left -= 1
    tiers = [t for t in allowed for _ in range(counts[t])]
    rng.shuffle(tiers)
    return tiers


def clamp(d: int, lo: int = 1, hi: int = 5) -> int:
    return max(lo, min(hi, d))


def lang_name(lang: str) -> str:
    return RP.LANG_LABEL[lang]


def fn_word(lang: str) -> str:
    return RP.LANG_FNWORD[lang]


NAME_RULE = [
    "Use the identifiers exactly as they are spelled in the source files, without any module or class prefix.",
    "Spell each name the way it appears in its definition (no `module.` or `Class.` prefix).",
    "Bare names as written in the code, please (for example `some_name`, not `module.some_name`).",
    "Write the plain identifiers as they appear in the source; no qualifiers.",
]

PATH_RULE = [
    "Give repository-relative paths with forward slashes.",
    "Use paths relative to the repository root.",
    "Paths should be relative to the repo root, as the files appear in the tree.",
]

LANG_INTRO = {
    "python": ["This is a Python project.", "The repo is Python.", ""],
    "javascript": ["This is a Node.js (CommonJS) project.", "The repo is plain JavaScript.", ""],
    "go": ["This is a Go module.", "The repo is Go.", ""],
    "java": ["This is a Java project.", "The repo is Java.", ""],
    "rust": ["This is a Rust crate.", "The repo is a Rust crate.", ""],
    "ruby": ["This is a Ruby project.", "The repo is Ruby.", ""],
}


def intro(rng: random.Random, lang: str) -> str:
    return rng.choice(LANG_INTRO[lang])


def jlist(items) -> str:
    return ", ".join(f"`{x}`" for x in items)


def bracket_line(label: str, value) -> str:
    return f"{label}: [{value}]"


def pick_from(rng: random.Random, seq: list):
    return seq[rng.randrange(len(seq))]


def until(rng: random.Random, lang: str, tier: int, find, tries: int = 40, **flags):
    """Build repositories until ``find(repo)`` returns something other than None; returns (repo, found)."""
    for _ in range(tries):
        repo = RP.make_repo(rng, lang, tier, **flags)
        got = find(repo)
        if got is not None:
            return repo, got
    raise RuntimeError(f"no suitable repository (lang={lang} tier={tier} flags={flags})")


def other_idents(repo, exclude: set) -> list:
    return [repo.ident(f) for f in repo.proj.fns if f not in exclude]


def pkg_label(repo, m) -> str:
    """how to refer to the directory of a module's package in a prompt"""
    return m.pkg
