"""Re-reading expensive sequences (python): element reads are counted on a lazily loaded series."""
from __future__ import annotations

from fx import family

from ._py_shapes import shape_family

SHAPES = {
    "moving_average": dict(
        d=2, args=["a", "b"], empty_args="([], 3)",
        naive='''def $f($a, $b):
    """$doc"""
    out = []
    for start in range(len($a) - $b + 1):
        out.append(sum($a[start:start + $b]) // $b)
    return out
''', fast='''def $f($a, $b):
    """$doc"""
    data = list($a)
    out = []
    total = sum(data[:$b])
    for start in range(len(data) - $b + 1):
        if start:
            total += data[start + $b - 1] - data[start - 1]
        out.append(total // $b)
    return out
''', oracle='''def oracle(a, b):
    a = list(a)
    return [sum(a[i:i + b]) // b for i in range(len(a) - b + 1)]
''', small="Seq([rng.randrange(0, 100) for _ in range(rng.randrange(0, 20))]), rng.randrange(1, 6)", big="Seq([rng.randrange(0, 1000) for _ in range(n)]), 50",
        wrap="a, b", spec="`{b}` is the window length (at least 1). Returns, for every window of `{b}` consecutive readings (left to right), the integer mean `sum // {b}`; empty when there are fewer than `{b}` readings.",
        vocab=[("smoothed_levels", ["readings", "window"], "Smooth a river-level series with a moving average."), ("rolling_load", ["samples", "span"], "Rolling mean of server load samples."),
               ("step_trend", ["counts", "days"], "Rolling mean of daily step counts.")]),
    "window_max": dict(
        d=3, args=["a", "b"], empty_args="([], 3)",
        naive='''def $f($a, $b):
    """$doc"""
    return [max($a[i:i + $b]) for i in range(len($a) - $b + 1)]
''', fast='''def $f($a, $b):
    """$doc"""
    data = list($a)
    return [max(data[i:i + $b]) for i in range(len(data) - $b + 1)]
''', oracle='''def oracle(a, b):
    a = list(a)
    return [max(a[i:i + b]) for i in range(len(a) - b + 1)]
''', small="Seq([rng.randrange(0, 100) for _ in range(rng.randrange(0, 20))]), rng.randrange(1, 6)", big="Seq([rng.randrange(0, 1000) for _ in range(n)]), 40",
        wrap="a, b", spec="`{b}` is the window length (at least 1). Returns the maximum of every window of `{b}` consecutive readings, left to right; empty when there are fewer than `{b}` readings.",
        vocab=[("peak_per_window", ["readings", "window"], "Highest reading in each sliding window."), ("worst_latency", ["latencies", "span"], "Worst latency within each sliding window."),
               ("max_temperature", ["temps", "hours"], "Highest temperature in each sliding block of hours.")]),
    "range_sums": dict(
        d=2, args=["a", "b"], empty_args="([], [])",
        naive='''def $f($a, $b):
    """$doc"""
    return [sum($a[lo:hi]) for lo, hi in $b]
''', fast='''def $f($a, $b):
    """$doc"""
    prefix = [0]
    for value in $a:
        prefix.append(prefix[-1] + value)
    return [prefix[hi] - prefix[lo] for lo, hi in $b]
''', oracle='''def oracle(a, b):
    a = list(a)
    return [sum(a[lo:hi]) for lo, hi in b]
''', small="Seq(xs := [rng.randrange(0, 50) for _ in range(rng.randrange(1, 25))]), [(min(lo, len(xs)), min(len(xs), lo + rng.randrange(0, 8))) for lo in [rng.randrange(0, 10) for _ in range(rng.randrange(0, 6))]]",
        big="Seq([rng.randrange(0, 1000) for _ in range(n)]), [(lo, lo + rng.randrange(0, n // 4)) for lo in [rng.randrange(0, n // 2) for _ in range(n // 10)]]",
        wrap="a, b", spec="`{b}` is a list of `(lo, hi)` index pairs with `0 <= lo <= hi <= len({a})`. Returns `sum({a}[lo:hi])` for every pair, in order.",
        vocab=[("usage_between", ["usage", "ranges"], "Energy used between pairs of meter readings."), ("sales_in_ranges", ["daily_sales", "ranges"], "Total sales for each requested day range."),
               ("rain_totals", ["rain_mm", "periods"], "Rainfall totals for each requested period.")]),
    "cumulative": dict(
        d=2, args=["a"],
        naive='''def $f($a):
    """$doc"""
    return [sum($a[:i + 1]) for i in range(len($a))]
''', fast='''def $f($a):
    """$doc"""
    out = []
    total = 0
    for value in $a:
        total += value
        out.append(total)
    return out
''', oracle='''def oracle(a):
    a = list(a)
    return [sum(a[:i + 1]) for i in range(len(a))]
''', small="Seq([rng.randrange(0, 50) for _ in range(rng.randrange(0, 25))])", big="Seq([rng.randrange(0, 1000) for _ in range(n)])", wrap="a",
        spec="Returns the running total of `{a}`: entry `i` is the sum of the first `i + 1` readings.",
        vocab=[("running_balance", ["movements"], "Running balance after every ledger movement."), ("distance_so_far", ["legs"], "Distance covered after every leg of a trip."),
               ("cumulative_rainfall", ["rain_mm"], "Cumulative rainfall after each day.")]),
    "count_over": dict(
        d=3, args=["a", "b"], empty_args="([], [])",
        naive='''def $f($a, $b):
    """$doc"""
    return [sum(1 for value in $a if value > limit) for limit in $b]
''', fast='''import bisect


def $f($a, $b):
    """$doc"""
    ordered = sorted($a)
    return [len(ordered) - bisect.bisect_right(ordered, limit) for limit in $b]
''', oracle='''def oracle(a, b):
    a = list(a)
    return [sum(1 for v in a if v > t) for t in b]
''', small="Seq([rng.randrange(0, 30) for _ in range(rng.randrange(0, 25))]), [rng.randrange(0, 32) for _ in range(rng.randrange(0, 6))]",
        big="Seq([rng.randrange(0, 1000) for _ in range(n)]), [rng.randrange(0, 1000) for _ in range(40)]", wrap="a, b",
        spec="`{b}` is a list of thresholds. For each threshold returns how many readings in `{a}` are strictly greater than it, in order.",
        vocab=[("exceedances", ["readings", "limits"], "How many readings exceed each alarm limit."), ("orders_above", ["order_values", "thresholds"], "How many orders are worth more than each threshold."),
               ("pages_slower_than", ["load_ms", "budgets"], "How many page loads were slower than each budget.")]),
}

PROMPTS = [
    "`{f}` in `{path}` reads the same readings over and over: the series behind `readings` is lazily loaded from disk, so every element access is expensive, and for a month of data "
    "the function takes ages. {doc} Rework it so each element is read only a small number of times per call. Results stay exactly as documented.",
    "perf: `{f}` ({path}) re-reads input elements for every window/query. The input is a lazy series (indexing = disk read). {doc} Cut the number of reads to roughly linear in the "
    "length of the series. Same output.",
    "We moved the {f} input to a lazily loaded series and now the batch crawls: each element access is a disk read and `{f}` ({path}) touches every element many times. "
    "Please fix the access pattern (copy once, prefix sums, a sliding window, whatever fits) without changing the results. The CI harness counts reads.",
    "Could you speed up `{f}` in `{path}`? {doc} Right now it slices the series again for every output item. The series is expensive to read, so aim for about one read per element.",
]

CFG = dict(
    pkgs=["meterbank", "stormwatch", "ledgerlab", "tidegauge", "pulselog", "gridwatch"], mods=["series", "windows", "queries", "stats"],
    prompts=PROMPTS, factor=3, metric="Ops.reads", unit="element reads", n=(3000, 5000),
    hint="elements of the series are read over and over instead of a bounded number of times",
    readme_note="The first argument is a lazily loaded series (supports `len`, indexing, slicing and iteration); every element access is expensive, so a call should read each element only a small number of times.",
    tags=["sliding-window", "prefix-sums", "access-counter"])


@family("optimize-py-windows", category="optimize", lang="python", kind="feature", n=8,
        summary="windows, prefix sums and threshold counts over an expensive lazily read series: counted element reads must stay linear")
def gen(rng, n):
    yield from shape_family(rng, n, SHAPES, CFG)
