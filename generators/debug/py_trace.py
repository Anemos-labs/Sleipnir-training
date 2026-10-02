"""Diagnose python failures (tracebacks and wrong output) from a reproduction script and its log."""
from fx import family

from generators.review._mods_py1 import MODULES as PY1
from generators.review._mods_py2 import MODULES as PY2
from generators.review._mods_py3 import MODULES as PY3
from generators.review._mods_py4 import MODULES as PY4

from . import _engine as E

PY = PY1 + PY2 + PY3 + PY4


@family("debug-trace-py", category="debug", lang="python", kind="fix", n=50,
        summary="diagnosis.json for a crash or wrong output of a python scenario; the traceback often points away from the culprit")
def gen(rng, n):
    yield from E.trace_family(PY, rng, n)


@family("debug-fix-py", category="debug", lang="python", kind="fix", n=15,
        summary="diagnose a python failure from the log, then repair the module: diagnosis fields and the repaired scenario output are both scored")
def gen_fix(rng, n):
    yield from E.trace_family(PY, rng, n, tag="fix", fix_too=True)
