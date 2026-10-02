"""Diagnose python failures (tracebacks and wrong output) from a reproduction script and its log."""
from fx import family

from generators.review._mods_py1 import MODULES as PY1

from . import _engine as E


@family("debug-trace-py", category="debug", lang="python", kind="fix", n=10,
        summary="diagnosis.json for a crash or wrong output of a python scenario; the traceback often points away from the culprit")
def gen(rng, n):
    yield from E.trace_family(PY1, rng, n)
