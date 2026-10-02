"""Regex alternatives for the many ways a person writes a date, a time or an amount. Used by the file checkers ('re:' patterns)."""
from __future__ import annotations

import re
from datetime import date

from . import _common as C


def date_re(d: date, year: bool = False) -> str:
    mon = C.MONTHS[d.month - 1]
    m3 = mon[:3]
    suf = r"(?:st|nd|rd|th)?"
    alts = [rf"(?<!\d)0?{d.day}{suf}(?:\s+of)?\s+(?:{mon}|{m3}\.?)\b", rf"\b(?:{mon}|{m3}\.?)\s+0?{d.day}{suf}(?!\d)", d.isoformat()]
    return "re:(?:" + "|".join(alts) + ")"


def time_re(minutes: int) -> str:
    h, m = divmod(minutes % 1440, 60)
    h12 = h % 12 or 12
    suf = "am" if h < 12 else "pm"
    alts = [rf"(?<![\d:.]){h:02d}[:.]{m:02d}(?!\d)", rf"(?<![\d:.]){h}[:.]{m:02d}(?!\d)" if h < 10 else ""]
    alts.append(rf"(?<![\d:.]){h12}[:.]{m:02d}\s*(?:{suf}|{suf[0]}\.m\.)")
    if m == 0:
        alts.append(rf"(?<![\d:.]){h12}\s*(?:{suf}|{suf[0]}\.m\.)")
    return "re:(?:" + "|".join(a for a in alts if a) + ")"


def money_re(cents: int, sym: str = r"[$£€]?") -> str:
    d, c = divmod(cents, 100)
    ds = f"{d}" if d < 1000 else f"(?:{d}|{d // 1000},{d % 1000:03d})"
    if c == 0:
        return f"re:(?<![\\d.,]){sym}{ds}(?:\\.00)?(?![\\d])"
    return f"re:(?<![\\d.,]){sym}{ds}\\.{c:02d}(?!\\d)"


def num_re(n) -> str:
    return rf"re:(?<![\d.,]){re.escape(str(n))}(?![\d])"


def word_re(w: str) -> str:
    return rf"re:(?<![A-Za-z0-9]){re.escape(w)}(?![A-Za-z0-9])"
