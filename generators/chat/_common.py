"""Shared helpers for the chat generators: people, voices (how a person writes), answer-task plumbing.

Nothing here registers a family. Prompts are assembled from *prose* pieces (which may be roughed up with typos and
chatty asides) and *verbatim* blocks (data, code, tables) which are never touched.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from fx import Task

FIRST = [
    "Amara", "Tomas", "Priya", "Ingrid", "Kofi", "Mei", "Rashid", "Sofia", "Dmitri", "Yuki", "Olu", "Hana", "Mateo", "Leila",
    "Bram", "Noor", "Ines", "Jun", "Farah", "Callum", "Zainab", "Anselm", "Thandi", "Lars", "Marisol", "Emre", "Siobhan",
    "Kwame", "Ravi", "Elif", "Nikolai", "Chiara", "Tariq", "Wren", "Pilar", "Anika", "Joaquin", "Freya", "Daniyar", "Imani",
    "Soren", "Lucia", "Hugo", "Keiko", "Abebe", "Nadia", "Oskar", "Paloma", "Idris", "Greta", "Malik", "Aoife", "Viktor",
    "Salma", "Dario", "Ebony", "Henrik", "Lin", "Odalys", "Pavel", "Rosalind", "Tobias", "Uma", "Wendell", "Xiomara",
    "Yara", "Zev", "Bianca", "Cormac", "Delphine", "Enzo", "Fatima", "Gideon", "Helga", "Isidro", "Jamila", "Konrad",
    "Livia", "Murat", "Nia", "Orla", "Percival", "Qadir", "Rhea", "Stellan", "Teodora", "Ulrich", "Vera", "Winston",
]
LAST = [
    "Okafor", "Lindqvist", "Marchetti", "Haddad", "Takahashi", "Brennan", "Castellano", "Nowak", "Abdi", "Fernandes",
    "Kowalczyk", "Mbeki", "Petrov", "Sandoval", "Thorsen", "Vasquez", "Whitlock", "Yilmaz", "Zielinski", "Adeyemi",
    "Bergstrom", "Carvalho", "Dlamini", "Eriksen", "Fofana", "Guerrero", "Hoang", "Iyer", "Jovanovic", "Kaplan",
    "Laurent", "Moretti", "Nakamura", "Oyelaran", "Pereira", "Quinlan", "Rahimi", "Svensson", "Tanaka", "Uddin",
]
REGISTERS = ("terse", "chatty", "formal", "hurried", "rambling")

_MISSPELL = {
    "definitely": "definately", "tomorrow": "tommorow", "receive": "recieve", "separate": "seperate", "weird": "wierd",
    "until": "untill", "because": "becuase", "their": "thier", "friend": "freind", "occurred": "occured",
    "necessary": "neccessary", "believe": "belive", "calendar": "calender", "beginning": "begining", "probably": "probly",
    "really": "realy", "schedule": "shedule", "address": "adress", "restaurant": "resturant", "maintenance": "maintainance",
    "which": "wich", "through": "thru", "something": "somthing", "different": "diffrent", "usually": "usualy",
    "business": "buisness", "actually": "actualy", "experience": "experiance", "thought": "thougt", "should": "shoud",
    "would": "woud", "people": "poeple", "quickly": "quicky", "answer": "anwser", "enough": "enuf", "tonight": "tonite",
    "everything": "everthing", "second": "secnod", "minutes": "minuets", "accidentally": "accidently", "apparently": "apparantly",
    "whether": "wether", "sure": "shure", "whole": "wole", "again": "agian", "might": "migth", "friday": "firday",
}
_CONTRACT = {"don't": "dont", "can't": "cant", "it's": "its", "I'm": "im", "I've": "ive", "isn't": "isnt", "doesn't": "doesnt",
             "didn't": "didnt", "won't": "wont", "that's": "thats", "I'll": "ill", "I'd": "id", "you're": "youre"}

OPENERS = {
    "terse": ["", "", "", "quick one:", "question:", "hey,"],
    "chatty": ["Hi there!", "Hey!", "Hello :)", "Good morning!", "Hi,", "Hey, hope your day's going ok.", "Evening!", "Hiya,"],
    "formal": ["Hello,", "Good afternoon,", "Hello, and thank you for your help.", "Dear assistant,", "Hello there,", "Greetings,"],
    "hurried": ["hey", "ok so", "hi quick q", "yo", "hey sorry in a rush,", "ok", ""],
    "rambling": ["Hi!! Ok so,", "Hey, so this is going to sound silly but", "Hello, bear with me,", "Morning. So,", "Hi, long story short (it is not short):",
                 "Right, so"],
}
CLOSERS = {
    "terse": ["", "", "", "thx", "ta", "cheers"],
    "chatty": ["Thanks so much!", "Thank you!", "Cheers, appreciate it.", "You're a star, thanks.", "Thanks in advance :)", "Much appreciated!"],
    "formal": ["Thank you in advance for your help.", "Many thanks.", "Kind regards.", "I appreciate your assistance.", "Thank you for your time."],
    "hurried": ["thx", "pls", "thanks!!", "", "need it soon", "tia"],
    "rambling": ["Sorry for the wall of text, and thanks!", "Anyway, thanks for bearing with me.", "That's everything, thanks a ton.",
                 "I realise that was a lot. Thank you!", "OK that is all, thank you."],
}
TANGENTS = [
    "(my cat just walked across the keyboard, so ignore any odd characters)",
    "Also the printer is jammed again, but that is a different problem.",
    "I have had far too much coffee for a weekday.",
    "(it has been raining sideways here all day, so I am stuck inside anyway)",
    "Sorry if this is a bit scattered, I am answering between meetings.",
    "My sister says I am overthinking it, which is probably true.",
    "I am typing this on my phone on a train, forgive the typos.",
    "Not that it matters, but the neighbour is mowing the lawn at the worst possible moment.",
    "I tried asking the group chat and got three different opinions and a meme.",
    "We had a long argument about this over dinner and nobody wanted to be the referee.",
    "(yes, I know I should have written it down at the time)",
    "I have been staring at this for a while and my eyes have gone funny.",
    "The kettle is on, so I have got a few minutes.",
    "Honestly I would rather be doing literally anything else right now.",
    "My brother in law swears he did this in his head in ten seconds.",
    "I promise I did try it myself first.",
    "It is one of those evenings where the wifi keeps dropping, so apologies if I vanish.",
    "(small print: I am not very good at maths, so please be gentle)",
]


def pick_names(rng, k: int) -> list[str]:
    return rng.sample(FIRST, k)


def full_names(rng, k: int) -> list[str]:
    firsts = rng.sample(FIRST, k)
    return [f"{f} {rng.choice(LAST)}" for f in firsts]


def _safe_token(tok: str) -> bool:
    return bool(re.fullmatch(r"[a-z]{6,}", tok))


def roughen(rng, text: str, level: float) -> str:
    """Typos and sloppiness in prose. Never touches digits, capitalised words, backticked or quoted text."""
    if level <= 0:
        return text
    parts = re.split(r"(`[^`]*`|\"[^\"]*\"|\S*\d\S*)", text)
    out = []
    for part in parts:
        if not part or part.startswith("`") or part.startswith('"') or re.search(r"\d", part):
            out.append(part)
            continue
        toks = re.split(r"(\s+)", part)
        for i, tok in enumerate(toks):
            core = tok.strip(".,;:!?()")
            low = core.lower()
            if low in _MISSPELL and rng.random() < 0.55 * level and core == low:
                toks[i] = tok.replace(core, _MISSPELL[low])
            elif _safe_token(core) and rng.random() < 0.05 * level:
                j = rng.randrange(1, len(core) - 2)
                swapped = core[:j] + core[j + 1] + core[j] + core[j + 2:]
                toks[i] = tok.replace(core, swapped)
        out.append("".join(toks))
    return "".join(out)


def sloppy(rng, text: str, level: float = 1.0) -> str:
    """Lowercase, dropped apostrophes, dropped final full stops (the 'typing fast' look)."""
    text = re.sub(r"\bI\b(?!')", "i", text)
    for k, v in _CONTRACT.items():
        if rng.random() < 0.7 * level:
            text = text.replace(k, v)
    text = re.sub(r"(?m)^([A-Z])(?=[a-z ])", lambda m: m.group(1).lower() if rng.random() < 0.8 else m.group(1), text)
    if rng.random() < 0.6:
        text = re.sub(r"\.(\s*)$", r"\1", text)
    return text


def register_for(rng, d: int | None = None) -> str:
    w = [3, 3, 2, 3, 2]
    return rng.choices(REGISTERS, weights=w)[0]


def prose(rng, text: str, reg: str) -> str:
    """Apply a register's roughness to one prose segment."""
    if reg == "hurried":
        return sloppy(rng, roughen(rng, text, 1.2), 1.0)
    if reg == "rambling":
        return roughen(rng, text, 0.6)
    if reg == "chatty":
        return roughen(rng, text, 0.35)
    if reg == "terse":
        return sloppy(rng, text, 0.5) if rng.random() < 0.5 else text
    return text


def chat(rng, intro: str, ask: str = "", data: str | None = None, reg: str | None = None, *, data_after_ask: bool = False,
         tangent: bool | None = None, allow_open: bool = True) -> str:
    """Assemble a chat message: opener, intro, verbatim data block, ask, closer. ``data`` is never altered.

    ``ask`` carries format instructions and is only lightly roughened (typos never touch digits or quoted text)."""
    reg = reg or register_for(rng)
    pieces: list[str] = []
    op = rng.choice(OPENERS[reg]) if allow_open else ""
    body = []
    if op:
        body.append(op)
    if intro:
        body.append(prose(rng, intro, reg))
    use_tangent = tangent if tangent is not None else (reg in ("chatty", "rambling") and rng.random() < 0.65)
    if use_tangent:
        t = rng.choice(TANGENTS)
        if reg == "hurried":
            t = sloppy(rng, t)
        body.append(t)
    head = " ".join(body).strip()
    ask_p = prose(rng, ask, reg) if ask else ""
    if reg == "hurried" and ask_p:
        ask_p = ask_p  # already sloppy
    cl = rng.choice(CLOSERS[reg])
    if data is not None:
        if data_after_ask:
            pieces = [head, ask_p, data.rstrip("\n"), cl]
        else:
            pieces = [head, data.rstrip("\n"), ask_p, cl]
    else:
        pieces = [" ".join(x for x in (head, ask_p, cl) if x)]
    msg = "\n\n".join(p for p in pieces if p)
    return msg


def block(text: str) -> str:
    """A verbatim code block for pasted data."""
    return "```\n" + text.rstrip("\n") + "\n```"


# ----- number and text formatting -------------------------------------------------------------------------------

def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    c = abs(cents)
    return f"{sign}{c // 100}.{c % 100:02d}"


def money_c(cents: int, sym: str = "$") -> str:
    sign = "-" if cents < 0 else ""
    c = abs(cents)
    return f"{sign}{sym}{c // 100:,}.{c % 100:02d}"


def hhmm(minutes: int) -> str:
    minutes %= 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def dur(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60:02d}m"


def round_half_up(x: Fraction | Decimal | int, places: int = 0) -> int | Decimal:
    q = Decimal(1).scaleb(-places)
    d = Decimal(x.numerator) / Decimal(x.denominator) if isinstance(x, Fraction) else Decimal(x)
    return d.quantize(q, rounding=ROUND_HALF_UP)


def cents_half_up(x: Fraction) -> int:
    """Round a Fraction number of cents half-up (positive values)."""
    n, d = x.numerator, x.denominator
    return (2 * n + d) // (2 * d)


def iso(d: date) -> str:
    return d.isoformat()


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
          "December"]


def wd(d: date) -> str:
    return WEEKDAYS[d.weekday()]


def pretty_date(d: date, rng=None) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def table(rows: list[list], header: list[str] | None = None, sep: str = " | ") -> str:
    """Plain-text aligned table (verbatim paste)."""
    allrows = ([header] if header else []) + [[str(c) for c in r] for r in rows]
    widths = [max(len(str(r[i])) for r in allrows) for i in range(len(allrows[0]))]
    lines = []
    for ri, r in enumerate(allrows):
        lines.append(sep.join(str(c).ljust(widths[i]) for i, c in enumerate(r)).rstrip())
        if header and ri == 0:
            lines.append(sep.join("-" * widths[i] for i in range(len(widths))))
    return "\n".join(lines)


def md_table(rows: list[list], header: list[str]) -> str:
    allrows = [header] + [[str(c) for c in r] for r in rows]
    widths = [max(len(str(r[i])) for r in allrows) for i in range(len(header))]
    out = []
    for ri, r in enumerate(allrows):
        out.append("| " + " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)) + " |")
        if ri == 0:
            out.append("|" + "|".join("-" * (widths[i] + 2) for i in range(len(header))) + "|")
    return "\n".join(out)


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


# ----- task plumbing -------------------------------------------------------------------------------------------

def answer_task(slug: str, prompt: str, difficulty: int, contains: list[str], gold: str, *, start: dict | None = None,
                fold: bool = False, tags=(), notes: dict | None = None, **kw) -> Task:
    """An answer-mode task. ``start`` defaults to a placeholder file (taskgen needs a non-empty start tree)."""
    return Task(
        slug=slug, prompt=prompt, difficulty=difficulty, start=start if start is not None else {".gitkeep": ""},
        answer={"contains": list(contains), "fold": fold}, gold_answer=gold, tags=list(tags), notes=notes or {}, **kw)


def uniq_in_prompt_ok(prompt: str, contains: list[str], fold: bool = False) -> bool:
    hay = prompt.lower() if fold else prompt
    for c in contains:
        cc = c.lower() if fold else c
        if len(c) > 3 and cc in hay:
            return False
    return True


def pick_d(rng, weights: dict[int, int]) -> int:
    ds = sorted(weights)
    return rng.choices(ds, weights=[weights[d] for d in ds])[0]


def d_cycle(i: int, n: int, plan: list[int]) -> int:
    """Deterministic difficulty plan: plan is cycled over instances."""
    return plan[i % len(plan)]


def month_add(d: date, k: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 + k, 12)
    m += 1
    import calendar
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date | None:
    """The n-th (1-based) given weekday (0=Mon) of a month, or None if the month has fewer."""
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    d += timedelta(weeks=n - 1)
    return d if d.month == month else None
