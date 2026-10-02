"""Helpers for the recall families: context windows, bulky-but-plausible haystack files, small record renderers.

The fictional world generator lives in ``generators.research._world`` and is reused here."""
from __future__ import annotations

import datetime as dt
import random

from generators.research import _world as W

WINDOWS = [8000, 8000, 8000, 8000, 12000, 12000, 12000, 16000, 16000, 24000, 32000]


def tier(rng: random.Random) -> str:
    """easy tasks are small folders without context pressure; hard ones overflow the window"""
    return rng.choices(["easy", "mid", "hard"], [30, 40, 30])[0]


def window(rng: random.Random, small_bias: bool = True) -> int | None:
    """a context window in tokens, or None (the harness default) now and then"""
    if rng.random() < 0.15:
        return None
    return rng.choice(WINDOWS)


def target_chars(win: int | None, mult: float = 1.5) -> int:
    """how many characters of material make an agent overflow a window of ``win`` tokens (about 3.7 chars/token, capped
    so that the largest tasks stay around 110 KB)"""
    return min(110_000, int((win or 12000) * 3.7 * mult))


def chatter(rng: random.Random, org: W.Org, kb: float, lo: dt.date = dt.date(2031, 1, 1), hi: dt.date = dt.date(2031, 12, 28)) -> str:
    """roughly ``kb`` kilobytes of office chatter"""
    out, n = [], 0
    while n < kb * 1000:
        line = W.filler_line(rng, org, lo, hi)
        out.append(line)
        n += len(line) + 1
        if rng.random() < 0.25:
            out.append("")
    return "\n".join(out)


def note_file(rng: random.Random, org: W.Org, d: dt.date, kb: float, extra: list[str] | None = None, lo=None, hi=None) -> str:
    """a dated note by a person with chatter and, spliced in at random lines, ``extra`` lines"""
    p = rng.choice(org.people)
    lines = chatter(rng, org, kb, lo or d - dt.timedelta(days=30), hi or d + dt.timedelta(days=30)).split("\n")
    for e in extra or []:
        lines.insert(rng.randint(0, len(lines)), e)
    head = f"Note from {p.full} ({p.team}), {W.d_long(d)}\n\n"
    return head + "\n".join(lines) + "\n"


def unique_path(rng: random.Random, files: dict, folder: str, d: dt.date, ext: str = "txt") -> str:
    while True:
        name = f"{folder}/{W.d_iso(d)}-{rng.randint(100, 999)}.{ext}"
        if name not in files:
            return name


def code(rng: random.Random, n: int = 6) -> str:
    """a distinctive code such as KR-4471-M"""
    L = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    return f"{rng.choice(L)}{rng.choice(L)}-{rng.randint(1000, 9999)}-{rng.choice(L)}"
