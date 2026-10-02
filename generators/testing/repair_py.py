"""Regression tests for reported bugs, and repairs of broken suites (python libraries)."""
from fx import family

from . import _engine2 as E2
from . import _pl_labels as PLL
from . import _pl_pricing as PL

PYLIBS = [PL.ferry, PLL.labelcode]


@family("testing-regress-py", category="testing", lang="python", kind="fix", n=12,
        summary="write the regression test for a reported bug: it must fail on the buggy copy and pass on the fixed one")
def gen_regress(rng, n):
    yield from E2.regress_family(PYLIBS, rng, n, per_instance=3, fix_too_every=4)


@family("testing-fixsuite-expectations-py", category="testing", lang="python", kind="fix", n=10,
        summary="a red suite whose expectations are wrong, not the code: repair the tests, keep them strong")
def gen_expect(rng, n):
    yield from E2.expect_family(PYLIBS, rng, n, per_instance=3)


@family("testing-fixsuite-internals-py", category="testing", lang="python", kind="refactor", n=8,
        summary="tests that pin private helpers and message texts: rewrite them to survive a refactor and still kill mutants")
def gen_internals(rng, n):
    yield from E2.internals_family(PYLIBS, rng, n, per_instance=2)
