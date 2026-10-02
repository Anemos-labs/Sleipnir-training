"""Performance regressions diagnosed from a before/after call-count profile."""
from fx import family

from . import _perf as P
from . import _perf2 as P2


@family("debug-perf-profile", category="debug", lang="python", kind="fix", n=23,
        summary="the results are unchanged but the workload got slower: find the regression from before/after call-count profiles (N+1 queries, repeated compiles, rescans)")
def gen(rng, n):
    yield from P.perf_family(P.PERF + P2.PERF2, rng, n)
