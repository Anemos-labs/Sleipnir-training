"""Automatic *trap* variants for slot modules: a block rewritten in an equivalent way that still looks like the classic defect.

The one rewrite used is swapping the operands of a single plain comparison (``a < b`` becomes ``b > a``, ``a <= b`` becomes ``b >= a``): same behaviour, but a hasty
reader sees a flipped boundary.  It is only applied to lines with exactly one comparison between two simple operands (names, fields, indexes, numbers, ``len(x)``) and no
strings, so evaluation order and operator chaining cannot change the meaning.
"""
from __future__ import annotations

import re

from ._slots import sub

_OPERAND = r"(?:len\([\w.]+\)|[A-Za-z_]\w*(?:\.\w+|\[\w+\])*|\d[\w.]*)"
_CMP = re.compile(r"(?<![\w.\])])(" + _OPERAND + r") (<=|>=|<|>) (" + _OPERAND + r")(?![\w.(\[])")
_BEFORE = re.compile(r"(?:^|\(|,|=|!|\{|&&|\|\||\b(?:if|while|elif|and|or|return|not))\s*$")
_AFTER = re.compile(r"^\s*(?:$|\)|:|\{|;|,|\?|&&|\|\||\b(?:and|or|then)\b)")
_FLIP = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}
_ANY_CMP = re.compile(r"\s(<=|>=|<|>)\s")


def swap_comparison(text: str) -> str:
    """The block with one comparison turned around, or the text unchanged when no line qualifies."""
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        t = ln.strip()
        if not t or t.startswith(("//", "#", "*", "/*", "@", '"""')) or any(q in ln for q in "\"'`"):
            continue
        if len(_ANY_CMP.findall(ln)) != 1 or re.search(r"==|!=|=>|->|<<|>>|\bis\b|\bin\b|\bnot\b|\bas\b", ln):
            continue
        m = _CMP.search(ln)
        if not m:
            continue
        if not _BEFORE.search(ln[: m.start()]) or not _AFTER.match(ln[m.end():]):
            continue
        a, op, b = m.groups()
        lines[i] = ln[: m.start()] + f"{b} {_FLIP[op]} {a}" + ln[m.end():]
        return "\n".join(lines)
    return text


# hand-written equivalent rewrites that still look wrong at a glance: (module, slot) -> (old line(s), new line(s))
MANUAL = {
    ("py-lockers", "free"): ("free = {s: 0 for s in SIZE_RANK}", "free = dict.fromkeys(SIZE_RANK, 0)"),
    ("py-lockers", "expire"): ('expired = [c for c, p in self.parcels.items() if now - p["since"] > HOLD_SECONDS]', 'expired = [c for c, p in self.parcels.items() if p["since"] + HOLD_SECONDS < now]'),
    ("py-quayplan", "book"): ("if start < e and s < end:", "if not (e <= start or end <= s):"),
    ("py-quayplan", "safe"): ('return "\'" + cell if cell[:1] in ("=", "+", "-", "@") else cell', 'return "\'" + cell if cell.startswith(("=", "+", "-", "@")) else cell'),
    ("py-chapterfile", "slug"): ('slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")', 'slug = "-".join(re.findall(r"[a-z0-9]+", title.lower()))'),
}


def apply_traps(mods) -> None:
    for mod in mods:
        for s in mod.slots:
            if s.trap or s.name == "imports":
                continue
            manual = MANUAL.get((mod.name, s.name))
            t = sub(s.good, *manual) if manual else swap_comparison(s.good)
            if t != s.good:
                s.trap = t
