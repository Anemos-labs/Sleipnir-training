"""Full reviews of python changes with planted defects."""
from fx import family

from . import _engine as E
from ._mods_py1 import MODULES as PY1

PY = PY1


@family("review-py-full", category="review", lang="python", kind="feature", n=9,
        summary="review a python PR (PR.md + change.patch) and report the planted defects; scored by recall minus false positives")
def gen(rng, n):
    yield from E.review_family(PY, rng, n, "full")
