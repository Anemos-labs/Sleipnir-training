"""Root cause from many log files: a simulated fleet, one hidden cause."""
from fx import family

from . import _logs as G


@family("debug-logs-forensics", category="debug", lang="text", kind="fix", n=28,
        summary="find the culprit host, release, component, job pair, config key or endpoint in a pile of generated logs (three log formats)")
def gen(rng, n):
    yield from G.logs_family(rng, n)
