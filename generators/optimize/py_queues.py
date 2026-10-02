"""Front-of-list operations (python): pop(0), repeated slicing, `in` + remove loops; element moves are counted."""
from __future__ import annotations

from fx import family

from ._py_shapes import shape_family

SHAPES = {
    "drain": dict(
        d=1, args=["a"], factor=4, metric="Ops.reads", n=(4000, 8000),
        naive='''def $f($a):
    """$doc"""
    done = []
    while $a:
        job = $a.pop(0)
        done.append(job * 2 + 1)
    return done
''', fast='''def $f($a):
    """$doc"""
    return [job * 2 + 1 for job in $a]
''', oracle='''def oracle(a):
    return [j * 2 + 1 for j in a]
''', small="[rng.randrange(0, 50) for _ in range(rng.randrange(0, 20))]", big="[rng.randrange(0, 1000) for _ in range(n)]", wrap="ShiftList(a)",
        spec="Handles every job of `{a}` in order and returns the list of results (`job * 2 + 1` for each job). The caller does not use `{a}` afterwards.",
        vocab=[("process_jobs", ["queue"], "Work through the pending job queue."), ("drain_events", ["events"], "Handle all queued events."),
               ("settle_payments", ["batch"], "Settle every payment of a batch in arrival order.")]),
    "merge": dict(
        d=3, args=["a", "b"], factor=4, metric="Ops.reads", n=(3000, 6000),
        naive='''def $f($a, $b):
    """$doc"""
    out = []
    while $a and $b:
        if $a[0] <= $b[0]:
            out.append($a.pop(0))
        else:
            out.append($b.pop(0))
    out.extend($a)
    out.extend($b)
    return out
''', fast='''def $f($a, $b):
    """$doc"""
    out = []
    i = j = 0
    while i < len($a) and j < len($b):
        if $a[i] <= $b[j]:
            out.append($a[i])
            i += 1
        else:
            out.append($b[j])
            j += 1
    out.extend($a[i:])
    out.extend($b[j:])
    return out
''', oracle='''def oracle(a, b):
    out = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            out.append(a[i]); i += 1
        else:
            out.append(b[j]); j += 1
    return out + a[i:] + b[j:]
''', small="sorted(rng.randrange(0, 30) for _ in range(rng.randrange(0, 12))), sorted(rng.randrange(0, 30) for _ in range(rng.randrange(0, 12)))",
        big="sorted(rng.randrange(0, 10 * n) for _ in range(n)), sorted(rng.randrange(0, 10 * n) for _ in range(n))", wrap="ShiftList(a), ShiftList(b)",
        spec="Both lists are sorted. Returns the merged sorted list; on equal items the one from `{a}` comes first. The caller does not use the arguments afterwards.",
        vocab=[("merge_schedules", ["morning", "evening"], "Merge two sorted timetables."), ("combine_ledgers", ["left", "right"], "Merge two ledgers sorted by amount."),
               ("merge_logs", ["first", "second"], "Merge two sorted event logs.")]),
    "batches": dict(
        d=2, args=["a", "b"], factor=4, metric="Ops.reads", n=(4000, 8000), empty_args="([], 3)",
        naive='''def $f($a, $b):
    """$doc"""
    out = []
    rest = $a
    while rest:
        out.append(rest[:$b])
        rest = rest[$b:]
    return out
''', fast='''def $f($a, $b):
    """$doc"""
    return [$a[i:i + $b] for i in range(0, len($a), $b)]
''', oracle='''def oracle(a, b):
    return [a[i:i + b] for i in range(0, len(a), b)]
''', small="[rng.randrange(0, 50) for _ in range(rng.randrange(0, 25))], rng.randrange(1, 6)", big="[rng.randrange(0, 1000) for _ in range(n)], 8", wrap="ShiftList(a), b",
        spec="`{b}` is at least 1. Returns consecutive chunks of `{a}`, each of `{b}` items except possibly the last; empty list for an empty input.",
        vocab=[("split_into_pages", ["rows", "size"], "Split rows into pages for the export."), ("chunk_uploads", ["files", "per_request"], "Group files into upload requests."),
               ("shift_groups", ["staff", "team_size"], "Group staff into teams of a given size.")]),
    "remove_all": dict(
        d=2, args=["a", "b"], factor=4, metric="Ops.reads", n=(3000, 6000), empty_args="([], 1)",
        naive='''def $f($a, $b):
    """$doc"""
    while $b in $a:
        $a.remove($b)
    return $a
''', fast='''def $f($a, $b):
    """$doc"""
    return [item for item in $a if item != $b]
''', oracle='''def oracle(a, b):
    return [x for x in a if x != b]
''', small="[rng.randrange(0, 6) for _ in range(rng.randrange(0, 20))], rng.randrange(0, 6)", big="[rng.randrange(0, 4) for _ in range(n)], 1", wrap="ShiftList(a), b",
        spec="Returns the items of `{a}` that are not equal to `{b}`, in their original order.",
        vocab=[("without_cancelled", ["bookings", "cancelled"], "Bookings without the cancelled marker."), ("drop_sentinel", ["samples", "sentinel"], "Samples without the sentinel value."),
               ("strip_blank_slots", ["slots", "blank"], "Calendar slots without blank entries.")]),
}

PROMPTS = [
    "`{f}` in `{path}` is quadratic: it takes items off the front of a Python list (or re-slices the rest each round), and every such step shifts or copies the remaining "
    "elements. With tens of thousands of entries the job crawls. {doc} Fix it so the work is linear. Results as documented in the README.",
    "perf: `{f}` ({path}) uses `pop(0)` / repeated slicing / remove-in-a-loop on a list. {doc} Make it O(n). Same output. The CI counts element moves.",
    "Profiling shows `{f}` ({path}) spending its time shifting list elements around. {doc} Please restructure it (indices, a deque, a comprehension...) so the number of element moves "
    "stays linear in the input size, without changing the result.",
]

CFG = dict(
    pkgs=["jobrunner", "scheduler", "ledgerio", "pagedexport", "rosterkit"], mods=["queue", "batch", "merge", "work"],
    prompts=PROMPTS, factor=4, metric="Ops.reads", unit="element moves", n=(4000, 8000),
    hint="elements are shifted or copied again and again (front pops, repeated slicing, membership + remove loops)",
    readme_note="Inputs are plain lists with tens of thousands of entries; the number of element moves a call causes must grow linearly with the length.",
    tags=["lists", "deque", "quadratic", "move-counter"])


@family("optimize-py-queues", category="optimize", lang="python", kind="feature", n=10,
        summary="pop(0), repeated slicing and remove loops on lists: element moves are counted with an instrumented list and must stay linear")
def gen(rng, n):
    yield from shape_family(rng, n, SHAPES, CFG)
