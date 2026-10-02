"""Shared helpers for the security families.

A scenario is a dict describing one defensive task: a vulnerable (but functional) start repository, a fixed reference
solution, hidden tests that check *both* the functionality (legitimate inputs, including odd-looking ones) and the
vulnerability (inert exploit payloads fed to pure functions or in-process objects), plus the facts needed to write a prompt.

    dict(slug, d, lang, product, func, cwe, finding, start, solution, hidden, verify="", tags=[], visible=None, extra="")

Hidden tests accept any *rejection style* (an exception, an error value, an empty result): they check outcomes (nothing outside
the sandbox was read or written, nothing was injected), not which exception was used.
"""
from __future__ import annotations

import random

from fx import Task, langs

PY_PRELUDE = '''import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)


def attempt(fn, *args, **kw):
    """Call fn; return its result, or None when it refused (raised)."""
    try:
        return fn(*args, **kw)
    except Exception:  # noqa: BLE001
        return None


def tmpdir():
    d = tempfile.mkdtemp(prefix="sec-")
    return os.path.realpath(d)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(data, bytes) else "w") as fh:
        fh.write(data)


def read(path):
    with open(path, "rb") as fh:
        return fh.read()
'''

def patched(text: str, *pairs: tuple[str, str]) -> str:
    """The reference solution of a file: `text` with every (old, new) pair applied (each `old` must occur)."""
    for old, new in pairs:
        if old not in text:
            raise ValueError(f"patch target not found: {old[:60]!r}")
        text = text.replace(old, new)
    return text


def readme(title: str, body: str) -> str:
    return f"# {title}\n\n{body.strip()}\n"


VOICES = [
    lambda s: (f"A penetration test of {s['product']} reported a vulnerability: {s['finding']} Fix it in the code so the whole class of problem is gone (not just the payload from the report) "
               f"and keep everything legitimate working. README.md describes the intended behaviour."),
    lambda s: (f"Review comment on `{s['func']}`: {s['finding']} Please fix this properly and keep the existing functionality, including unusual but valid inputs. "
               f"Nobody should be able to work around the fix with a variant of the payload."),
    lambda s: (f"Our static analysis flagged `{s['func']}` ({s['cwe']}): {s['finding']} Harden the code. Existing behaviour for legitimate callers has to stay exactly as documented in README.md; "
               f"there are tests for both the normal use and for hostile input."),
    lambda s: f"{s['func']} is unsafe: {s['finding']} fix it without breaking normal use, README.md says what normal is.",
    lambda s: (f"Security ticket for {s['product']} ({s['cwe']}). Problem: {s['finding']} Acceptance: hostile input can no longer do this, every documented behaviour still works, and the fix "
               f"is in the code (not in the tests). Don't weaken the visible tests."),
    lambda s: (f"We had an incident review for {s['product']}. Root cause: {s['finding']} Close the hole in `{s['func']}` and anything that shares the flaw in this repository; "
               f"normal users must notice nothing."),
]


def emit(rng: random.Random, scenarios: list[dict], tags: list[str] | None = None):
    """Yield one Task per scenario."""
    for i, s in enumerate(scenarios):
        voice = VOICES[(i + rng.randrange(len(VOICES))) % len(VOICES)]
        prompt = voice(s) + (" " + s["extra"] if s.get("extra") else "")
        lang = s.get("lang", "python")
        start = dict(s["start"])
        if s.get("visible"):
            start.update(s["visible"])
        yield Task(
            slug=f"{i + 1:02d}-{s['slug']}",
            prompt=prompt,
            difficulty=s["d"],
            lang=lang,
            kind="fix",
            start=start,
            hidden=dict(s["hidden"]),
            solution=dict(s["solution"]),
            verify=s.get("verify") or {"javascript": "node --test test/*.test.js"}.get(lang) or langs.VERIFY[lang],
            timeout_s=s.get("timeout_s", 120),
            protected=list(s.get("protected", [])),
            tags=["security", s["cwe"].lower().replace(" ", "-"), *(tags or []), *s.get("tags", [])],
            notes={"cwe": s["cwe"], "scenario": s["slug"]},
        )
