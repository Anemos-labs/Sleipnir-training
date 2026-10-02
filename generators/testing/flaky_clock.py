"""Flaky tests: sleeping tests that must be driven by a fake clock instead."""
from fx import family

from . import _engine3 as E3
from . import _pl_clock as PC


@family("testing-clock-fake", category="testing", lang="python", kind="refactor", n=16,
        summary="a suite that sleeps through real timeouts: inject a clock into the code (or just use the existing one) and rewrite the tests so they never wait")
def gen_clock(rng, n):
    yield from E3.clock_family([PC.ttlcache, PC.ratelimit, PC.sessionstore, PC.breaker], rng, n)
