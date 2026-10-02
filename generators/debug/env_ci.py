"""Tests pass locally and fail in CI: find the hidden dependency on the environment."""
from fx import family

from . import _env as V


@family("debug-works-on-my-machine", category="debug", lang="python", kind="fix", n=16,
        summary="a test fails only in CI: default encoding, time zone, hash seed, case-insensitive paths, Python version, CRLF, an exported variable or the working directory")
def gen(rng, n):
    yield from V.env_family(rng, n)
