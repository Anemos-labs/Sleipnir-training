"""One environment's configuration is subtly wrong: diagnose it from the run logs."""
from fx import family

from . import _config as C


@family("debug-config-drift", category="debug", lang="python", kind="fix", n=20,
        summary="find the misspelt key, text-for-number, wrong unit, transposed port or bad secret reference in one environment's config (ini/json/toml/env)")
def gen(rng, n):
    yield from C.config_family(rng, n)
