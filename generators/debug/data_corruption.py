"""Data corruption forensics: find the pipeline stage that damages the data from the dumps after each stage."""
from fx import family

from . import _pipes as P


@family("debug-stage-dumps", category="debug", lang="python", kind="fix", n=24,
        summary="the output of every pipeline stage is saved; find the stage and function that corrupts amounts, times, order or identity")
def gen(rng, n):
    yield from P.pipe_family(P.PIPES, rng, n)
