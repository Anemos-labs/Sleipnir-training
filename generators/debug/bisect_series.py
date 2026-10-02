"""Find the first bad patch of a series (a base tree, N patches, a check script)."""
from fx import family

from . import _bisect as B


@family("debug-bisect-patches", category="debug", lang="python", kind="fix", n=24,
        summary="bisect a patch series for the first patch that makes check.py fail; the culprit is a new step or a 'tidy-up' of an existing one")
def gen(rng, n):
    yield from B.bisect_family(rng, n)
