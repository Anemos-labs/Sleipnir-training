"""Review families that change what is asked: security-only passes, merge verdicts (including clean changes), small diffs."""
from fx import family

from . import _engine as E
from .fam_full import GO, JAVA, JS, PY, RS

ALL = PY + GO + JS + JAVA + RS


@family("review-security", category="review", lang="mixed", kind="feature", n=18,
        summary="security-only review: only security defects count, functional bugs in the same change are out of scope")
def gen_sec(rng, n):
    yield from E.review_family(ALL, rng, n, "security", profile=[2, 3, 3, 4, 4, 5, 3, 2, 4])


@family("review-verdict", category="review", lang="mixed", kind="feature", n=22,
        summary="is it safe to merge? a verdict plus findings; about a third of the changes are clean and must be approved")
def gen_verdict(rng, n):
    yield from E.review_family(ALL, rng, n, "verdict", profile=[1, 2, 2, 3, 3, 3, 4, 4, 5, 2, 3])


@family("review-small-diff", category="review", lang="mixed", kind="feature", n=12,
        summary="review of a tiny change (one or two functions) with one planted defect")
def gen_small(rng, n):
    yield from E.review_family(ALL, rng, n, "full", profile=[1, 1, 1, 2], tag="small")
