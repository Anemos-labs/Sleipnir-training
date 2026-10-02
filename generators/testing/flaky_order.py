"""Flaky tests: suites that only pass in file order because tests leak state into each other."""
from fx import family

from . import _engine3 as E3
from . import _pl_order as PO


@family("testing-order-independence", category="testing", lang="python", kind="fix", n=17,
        summary="a suite that is green in file order but red when shuffled or run one test at a time: make the tests independent without weakening them")
def gen_order(rng, n):
    yield from E3.order_family([PO.pluginhub, PO.cartkit, PO.notestore], rng, n)
