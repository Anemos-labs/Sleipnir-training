"""Diagnose wrong output of javascript, go, rust and java programs from a reproduction script and its log."""
from fx import family

from generators.review._mods_go1 import MODULES as GO1
from generators.review._mods_java1 import MODULES as JAVA1
from generators.review._mods_js1 import MODULES as JS1
from generators.review._mods_rs1 import MODULES as RS1

from . import _scn_go as SGO
from . import _scn_java as SJAVA
from . import _scn_js as SJS
from . import _scn_rs as SRS
from . import _xtrace as X

JS = [m for m in JS1 if m.name in SJS.SCENARIOS]
GO = [m for m in GO1 if m.name in SGO.SCENARIOS]
RS = [m for m in RS1 if m.name in SRS.SCENARIOS]
JAVA = [m for m in JAVA1 if m.name in SJAVA.SCENARIOS]


@family("debug-trace-js", category="debug", lang="javascript", kind="fix", n=8,
        summary="diagnosis.json for the wrong output of a javascript reproduction script (rounding, coercion, aliasing, time zones, async)")
def gen_js(rng, n):
    yield from X.x_trace_family(JS, SJS.SCENARIOS, rng, n)


@family("debug-trace-go", category="debug", lang="go", kind="fix", n=8,
        summary="diagnosis.json for the wrong output of a go reproduction program (expiry edges, path cleaning, retries, contexts, deadlocks)")
def gen_go(rng, n):
    yield from X.x_trace_family(GO, SGO.SCENARIOS, rng, n)


@family("debug-trace-rs", category="debug", lang="rust", kind="fix", n=8,
        summary="diagnosis.json for the wrong output or panics of a rust example program (parsing limits, overflow, ordering, rounding)")
def gen_rs(rng, n):
    yield from X.x_trace_family(RS, SRS.SCENARIOS, rng, n)


@family("debug-trace-java", category="debug", lang="java", kind="fix", n=5,
        summary="diagnosis.json for the wrong output of a java reproduction program (boundaries, overflow, lost units, escaping state)")
def gen_java(rng, n):
    yield from X.x_trace_family(JAVA, SJAVA.SCENARIOS, rng, n)
