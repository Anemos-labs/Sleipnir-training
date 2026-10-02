"""Prompt voices for the explain families: how a colleague, a reviewer, a ticket or a terse chat message asks the same question.

``frame(rng, ask, fmt, why, tag)`` wraps the family's own question (``ask``), the answer-format instruction (``fmt``) and an
optional reason for asking (``why``). The family supplies the repository-specific words; this module only supplies voice.
"""
from __future__ import annotations

import random

_Q_WORDS = {"Which", "What", "Who", "How", "Where", "Does", "Is", "Are", "List", "Tell", "Find", "Give", "Starting", "If", "For", "Using",
            "Trace", "Work", "Walk", "Count", "Name", "When", "Can", "Could", "Would", "Why", "Suppose", "Say", "Take", "Given", "After",
            "Before", "Reading", "Looking", "Among", "In", "On", "Of", "From", "With", "At", "Once", "Assume", "Run", "Considering",
            "Going", "Figure", "Check", "Identify", "Determine", "Show", "Imagine", "Pick", "Compare", "Looking", "Out", "Not",
            "This", "The", "There", "Our", "Under", "Some", "Two", "Several", "Something", "One", "Every", "Somewhere", "My", "It"}

CHAT_OPEN = ["", "", "", "Quick question: ", "Hey, ", "Hi - ", "Could you help me trace something? ", "Sorry to bother you, but ",
             "I'm new to this repo and ", "Before I touch anything: ", "Picking this up from a colleague who left. ",
             "Can you take a look at this repo? ", "Not urgent, but ", "Got a minute? ", "I've been staring at this for an hour. "]
CHAT_CLOSE = ["", "", "", " Thanks!", " Thanks in advance.", " No rush.", " Cheers.", " Thanks, that would save me a lot of reading.",
              " I'd rather not change anything, just understand it.", " Please don't edit the code, I only need the answer."]
REVIEW_OPEN = ["Reviewing PR #{n} (\"{title}\"). ", "Review comment on PR #{n}: ", "Leaving this on PR #{n} (\"{title}\") before I approve: ",
               "While reviewing \"{title}\" (#{n}) I got stuck. "]
REVIEW_TITLE = ["tidy up helpers", "rename arguments in the pricing layer", "move constants next to their users", "split a module in two",
                "drop the old code path", "cleanup after the refactor", "extract shared helper", "make reports less noisy",
                "bump defaults", "reorganise packages", "follow-up to the release branch", "remove unused imports"]
TICKET_KIND = ["Question", "Investigate", "Support", "Docs gap", "Audit"]
TERSE_END = ["", "", "", " thx", " ta", ""]


def lc_first(s: str) -> str:
    w = s.split(" ", 1)[0].strip(",:")
    return s[:1].lower() + s[1:] if w in _Q_WORDS else s


def uc_first(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def frame(rng: random.Random, ask: str, fmt: str = "", why: str = "", tag: str = "PRJ", persona: str | None = None) -> str:
    """Wrap a question. ``ask`` and ``fmt`` are complete sentences; ``why`` is a short reason sentence ("I'm about to ...")."""
    persona = persona or rng.choices(["chat", "review", "ticket", "terse", "brief"], [34, 18, 18, 12, 18])[0]
    fmt = fmt.strip()
    why = why.strip()
    if persona == "chat":
        o = rng.choice(CHAT_OPEN)
        c = rng.choice(CHAT_CLOSE)
        body = (why + " " if why else "") + ask
        if o and o.rstrip().endswith((",", "but", "and")):
            body = lc_first(body) if not why else body[:1].lower() + body[1:]
        elif not o:
            body = uc_first(body)
        elif o.rstrip().endswith((".", "?", ":", "!")) or o.rstrip().endswith("-"):
            body = uc_first(body) if not o.rstrip().endswith(":") else (lc_first(body) if not why else body)
        out = o + body
        if fmt:
            out += " " + fmt
        return (out + c).strip()
    if persona == "review":
        o = rng.choice(REVIEW_OPEN).format(n=rng.randint(120, 989), title=rng.choice(REVIEW_TITLE))
        out = o + ((why + " ") if why else "") + ask
        return (out + (" " + fmt if fmt else "")).strip()
    if persona == "ticket":
        k = rng.choice(TICKET_KIND)
        head = f"{tag}-{rng.randint(100, 999)} [{k}]"
        lines = [head, ""]
        if why:
            lines.append(why)
        lines.append(ask)
        if fmt:
            lines += ["", fmt]
        return "\n".join(lines)
    if persona == "terse":
        out = lc_first(ask) if rng.random() < 0.5 else ask
        if why and rng.random() < 0.5:
            out = lc_first(why.rstrip(".")) + ". " + out
        if fmt:
            out += " " + fmt
        return (out + rng.choice(TERSE_END)).strip()
    # brief: labelled sections
    lines = []
    if why:
        lines.append("Context: " + why)
    lines.append("Question: " + ask)
    if fmt:
        lines.append("Answer format: " + fmt)
    return "\n".join(lines)


def pick(rng: random.Random, options: list[str]) -> str:
    return options[rng.randrange(len(options))]
