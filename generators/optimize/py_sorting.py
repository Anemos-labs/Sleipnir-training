"""Sorting where a single pass would do (python): comparison counts on tracked values."""
from __future__ import annotations

from fx import family

from ._py_shapes import shape_family

SHAPES = {
    "cheapest": dict(
        d=1, args=["a"],
        naive='''def $f($a):
    """$doc"""
    ranked = sorted($a)
    return ranked[0] if ranked else None
''', fast='''def $f($a):
    """$doc"""
    return min($a) if $a else None
''', oracle='''def oracle(a):
    return min(a) if a else None
''', small="[rng.randrange(0, 50) for _ in range(rng.randrange(0, 20))]", big="[rng.randrange(0, 10 * n) for _ in range(n)]", wrap="[T(x) for x in a]",
        spec="Returns the smallest item of `{a}`, or `None` when it is empty.",
        vocab=[("cheapest_offer", ["offers"], "The lowest offer received for a job."), ("earliest_slot", ["slots"], "The earliest free slot of a calendar."),
               ("lightest_parcel", ["parcels"], "The lightest parcel in a delivery round.")]),
    "top_k": dict(
        d=2, args=["a", "b"], empty_args="([], 3)",
        naive='''def $f($a, $b):
    """$doc"""
    return sorted($a, reverse=True)[:$b]
''', fast='''import heapq


def $f($a, $b):
    """$doc"""
    return heapq.nlargest($b, $a)
''', oracle='''def oracle(a, b):
    return sorted(a, reverse=True)[:b]
''', small="[rng.randrange(0, 40) for _ in range(rng.randrange(0, 25))], rng.randrange(0, 6)", big="[rng.randrange(0, 10 * n) for _ in range(n)], 5",
        wrap="[T(x) for x in a], b", spec="Returns the `{b}` largest items of `{a}`, largest first (equal items keep their input order); fewer if `{a}` is shorter.",
        vocab=[("best_scores", ["scores", "count"], "The best scores of the season for the leaderboard."), ("heaviest_loads", ["loads", "count"], "The heaviest loads of the day."),
               ("busiest_hours", ["hours", "count"], "The busiest hours of the week by visitor count.")]),
    "rank_of": dict(
        d=2, args=["a", "b"], empty_args="([], 5)",
        naive='''def $f($a, $b):
    """$doc"""
    ordered = sorted($a)
    place = 0
    while place < len(ordered) and ordered[place] < $b:
        place += 1
    return place
''', fast='''def $f($a, $b):
    """$doc"""
    return sum(1 for item in $a if item < $b)
''', oracle='''def oracle(a, b):
    return sum(1 for x in a if x < b)
''', small="[rng.randrange(0, 40) for _ in range(rng.randrange(0, 25))], rng.randrange(0, 45)", big="[rng.randrange(0, 10 * n) for _ in range(n)], 5 * n",
        wrap="[T(x) for x in a], T(b)", spec="Returns how many items of `{a}` are strictly smaller than `{b}`.",
        vocab=[("times_faster", ["laps", "mine"], "How many laps were faster than mine."), ("cheaper_listings", ["prices", "ours"], "How many competing prices undercut ours."),
               ("older_members", ["ages", "age"], "How many members are younger than a given age.")]),
    "is_ordered": dict(
        d=2, args=["a"],
        naive='''def $f($a):
    """$doc"""
    return $a == sorted($a)
''', fast='''def $f($a):
    """$doc"""
    for i in range(len($a) - 1):
        if $a[i + 1] < $a[i]:
            return False
    return True
''', oracle='''def oracle(a):
    return all(not (a[i + 1] < a[i]) for i in range(len(a) - 1))
''', small="sorted([rng.randrange(0, 20) for _ in range(rng.randrange(0, 12))]) if rng.random() < 0.5 else [rng.randrange(0, 20) for _ in range(rng.randrange(0, 12))]",
        big="[rng.randrange(0, 10 * n) for _ in range(n)]", wrap="[T(x) for x in a]", factor=3, n=(3000, 6000),
        spec="Returns `True` when `{a}` is in non-decreasing order, `False` otherwise (an empty or one-item list is ordered).",
        vocab=[("log_is_chronological", ["timestamps"], "Whether a log's timestamps never go backwards."), ("ranking_is_valid", ["scores"], "Whether a ranking table is sorted best to worst... non-decreasing here."),
               ("manifest_is_sorted", ["ids"], "Whether a manifest's ids are in non-decreasing order.")]),
    "latest": dict(
        d=3, args=["a"],
        naive='''def $f($a):
    """$doc"""
    ordered = sorted($a, key=lambda e: e["ts"])
    return ordered[-1]["id"] if ordered else None
''', fast='''def $f($a):
    """$doc"""
    if not $a:
        return None
    return max($a, key=lambda e: e["ts"])["id"]
''', oracle='''def oracle(a):
    return max(a, key=lambda e: e["ts"])["id"] if a else None
''', small='[{"id": "e%d" % i, "ts": t} for i, t in enumerate(rng.sample(range(100), rng.randrange(0, 15)))]',
        big='[{"id": "e%d" % i, "ts": t} for i, t in enumerate(rng.sample(range(100 * n), n))]', wrap='[{"id": e["id"], "ts": T(e["ts"])} for e in a]',
        spec="Each event is a dict with an `id` and a `ts` (timestamps are distinct). Returns the `id` of the event with the largest `ts`, or `None` for no events.",
        vocab=[("latest_backup", ["backups"], "Id of the most recent backup."), ("last_login", ["logins"], "Id of the most recent login event."),
               ("newest_revision", ["revisions"], "Id of the newest revision of a document.")]),
    "kth": dict(
        d=3, args=["a", "b"], empty_args="([1], 1)",
        naive='''def $f($a, $b):
    """$doc"""
    ordered = sorted($a)
    return ordered[-$b]
''', fast='''import heapq


def $f($a, $b):
    """$doc"""
    return heapq.nlargest($b, $a)[-1]
''', oracle='''def oracle(a, b):
    return sorted(a)[-b]
''', small="[rng.randrange(0, 40) for _ in range(rng.randrange(3, 25))], rng.randrange(1, 4)", big="[rng.randrange(0, 10 * n) for _ in range(n)], 3",
        wrap="[T(x) for x in a], b", spec="`{b}` is a small positive number not larger than the length of `{a}`; returns the `{b}`-th largest item (1 = the largest).",
        vocab=[("third_highest", ["bids", "rank"], "The k-th highest bid in an auction."), ("runner_up_time", ["times", "place"], "The time of the given place in a race (1 = slowest, counting from the end)."),
               ("nth_longest_queue", ["lengths", "rank"], "The n-th longest queue of the day.")]),
}

PROMPTS = [
    "`{f}` in `{path}` sorts the whole input just to look at a handful of elements. On the big nightly batch that is the single hottest function. {doc} "
    "Make it do no more work than needed; the results must stay exactly what the README says.",
    "perf: `{f}` ({path}) is O(n log n) where a single pass is enough. {doc} Fix it, same results.",
    "I profiled the {f} step in `{path}` and almost all of its time goes into `sorted(...)`. We only need a tiny part of the sorted order. Rewrite it so it doesn't sort "
    "everything (the comparison count is what we watch in CI: it should be close to one comparison per element), without changing the output.",
    "Review comment: \"`{f}` sorts the entire list to take the first/last few. Use a selection instead.\" Please do that in `{path}`. {doc} Behaviour stays the same, "
    "including ties and the empty case described in the README.",
]

CFG = dict(
    pkgs=["leaderboard", "dispatch", "auctionhouse", "telemetry", "catalogue", "raceboard"], mods=["ranking", "stats", "picks", "summary"],
    prompts=PROMPTS, factor=4, metric="Ops.total()", unit="comparisons", n=(4000, 7000),
    hint="the function sorts everything although a selection or a single pass is enough",
    readme_note="Inputs can hold hundreds of thousands of items; the number of comparisons per call is monitored, so avoid sorting more than necessary.",
    tags=["sorting", "selection", "heap", "comparison-counter"])


@family("optimize-py-sorting", category="optimize", lang="python", kind="feature", n=12,
        summary="full sorts used to find a minimum, top-k, rank or ordering check: comparison counts on tracked values must stay near n")
def gen(rng, n):
    yield from shape_family(rng, n, SHAPES, CFG)
