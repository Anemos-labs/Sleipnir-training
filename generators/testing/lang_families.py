"""Testing families for Go, JavaScript and Rust libraries: write the suite, write the regression test, repair wrong expectations."""
from fx import family

from . import _engine as E
from . import _engine2 as E2
from . import _gl_go1 as GL
from . import _jl_js1 as JL
from . import _rl_rust1 as RL

GOLIBS = [GL.meter, GL.bells]
JSLIBS = [JL.recipe, JL.cronlite]
RSLIBS = [RL.fuel, RL.railfare]


# ---- write the missing tests ----------------------------------------------------------------------------------------

@family("testing-write-go-rules", category="testing", lang="go", kind="feature", n=12,
        summary="write the missing Go tests for a metering / schedule rule package; scored by the share of seeded bugs caught")
def gen_write_go(rng, n):
    yield from E.write_family(GOLIBS, rng, n)


@family("testing-write-js-rules", category="testing", lang="javascript", kind="feature", n=12,
        summary="write node:test suites for a recipe scaler and a cron-expression parser; scored by seeded bugs caught")
def gen_write_js(rng, n):
    yield from E.write_family(JSLIBS, rng, n)


@family("testing-write-rs-rules", category="testing", lang="rust", kind="feature", n=10,
        summary="write Rust integration tests for a fuel-log parser and a rail fare table; scored by seeded bugs caught")
def gen_write_rs(rng, n):
    yield from E.write_family(RSLIBS, rng, n)


# ---- regression tests -----------------------------------------------------------------------------------------------

@family("testing-regress-go", category="testing", lang="go", kind="fix", n=8,
        summary="write the Go regression test for a reported bug: red on the buggy copy, green on the fixed one")
def gen_regress_go(rng, n):
    yield from E2.regress_family(GOLIBS, rng, n, per_instance=2, fix_too_every=4)


@family("testing-regress-js", category="testing", lang="javascript", kind="fix", n=8,
        summary="write the node:test regression test for a reported bug: red on the buggy copy, green on the fixed one")
def gen_regress_js(rng, n):
    yield from E2.regress_family(JSLIBS, rng, n, per_instance=2, fix_too_every=4)


@family("testing-regress-rs", category="testing", lang="rust", kind="fix", n=8,
        summary="write the Rust regression test for a reported bug: red on the buggy copy, green on the fixed one")
def gen_regress_rs(rng, n):
    yield from E2.regress_family(RSLIBS, rng, n, per_instance=2, fix_too_every=4)


# ---- wrong expectations ---------------------------------------------------------------------------------------------

@family("testing-fixsuite-expectations-go", category="testing", lang="go", kind="fix", n=6,
        summary="a red Go suite whose expectations are wrong, not the code: repair the tests and keep them strong")
def gen_expect_go(rng, n):
    yield from E2.expect_family(GOLIBS, rng, n, per_instance=3)


@family("testing-fixsuite-expectations-js", category="testing", lang="javascript", kind="fix", n=6,
        summary="a red node:test suite whose expectations are wrong, not the code: repair the tests and keep them strong")
def gen_expect_js(rng, n):
    yield from E2.expect_family(JSLIBS, rng, n, per_instance=3)


@family("testing-fixsuite-expectations-rs", category="testing", lang="rust", kind="fix", n=6,
        summary="a red cargo test suite whose expectations are wrong, not the code: repair the tests and keep them strong")
def gen_expect_rs(rng, n):
    yield from E2.expect_family(RSLIBS, rng, n, per_instance=3)
