"""Write the missing tests for python rule libraries (scored by hidden mutants)."""
from fx import family

from . import _engine as E
from . import _pl_labels as PLL
from . import _pl_pricing as PL


@family("testing-write-py-pricing", category="testing", lang="python", kind="feature", n=9,
        summary="write a unittest suite for a fare/pricing rule book; scored by the share of seeded bugs it catches")
def gen(rng, n):
    yield from E.write_family([PL.ferry], rng, n)


@family("testing-write-py-codes", category="testing", lang="python", kind="feature", n=9,
        summary="write a unittest suite for an identifier codec with a check character; scored by seeded bugs caught")
def gen_codes(rng, n):
    yield from E.write_family([PLL.labelcode], rng, n)
