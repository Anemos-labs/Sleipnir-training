"""Write the missing tests for python pricing libraries (scored by hidden mutants)."""
from fx import family

from . import _engine as E
from . import _pl_pricing as PL


@family("testing-write-py-pricing", category="testing", lang="python", kind="feature", n=9,
        summary="write a unittest suite for a fare/pricing rule book; scored by the share of seeded bugs it catches")
def gen(rng, n):
    yield from E.write_family([PL.ferry], rng, n)
