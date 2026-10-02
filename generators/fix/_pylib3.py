"""Shared registration helper for the pylib3_* modules (fix-py-3).

``register_libs3`` behaves like ``fx.register_libs`` for python libraries, but cleans CI excerpts: a traceback shows the
source line of every frame, and a line such as ``raise ValueError(f"line {lineno}: ...")`` would trip the framework's
"unfilled {placeholder}" prompt check and make the whole family fail. Those echoed source lines are dropped from the
quoted traceback (the traceback stays readable: the ``File ... line N, in func`` line and the exception remain).
"""
import re

from fx import Family
from fx.core import register
from fx.lib import mutation_tasks

_PH = re.compile(r"\{[a-z_]+\}")


def clean_prompt(prompt: str) -> str:
    out: list[str] = []
    for ln in prompt.split("\n"):
        if ln.startswith("    ") and _PH.search(ln) and out and out[-1].lstrip().startswith("File "):
            continue
        out.append(ln)
    return "\n".join(out)


def register_libs3(libs, n: int = 10, category: str = "fix") -> None:
    for lib in libs:
        fam = Family(name=f"fix-py-{lib.name}", category=category, lang="python", kind="fix", n=n,
                     summary=f"injected bugs in {lib.title} (python)")

        def gen(rng, count, _lib=lib):
            return [t.with_(prompt=clean_prompt(t.prompt)) for t in mutation_tasks(_lib, rng, count)]

        gen.__module__ = "generators.fix.pylib3"
        register(fam, gen)


def chain(ctor: str, calls: list[str]) -> str:
    """A probe expression that drives one stateful object through a list of calls and returns every result:
    ``chain("BayMap(16)", ["alloc(3)", "free_blocks()"])`` -> ``(lambda o: [o.alloc(3), o.free_blocks()])(BayMap(16))``.
    Only the public API shows up in the prompt, no private helper functions."""
    items = ", ".join(f"o.{c}" for c in calls)
    return f"(lambda o: [{items}])({ctor})"
