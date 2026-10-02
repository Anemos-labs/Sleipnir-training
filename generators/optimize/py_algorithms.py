"""Brute-force algorithms that need a better algorithm (python): the check counts executed lines inside the package, not seconds."""
from __future__ import annotations

import math
import random
from string import Template

from fx import Task, dd, family, merged, run

from ._kit import PY_ALL, PY_CORRECT, PY_PERF, prove_opt
from ._py_lines import TEXT as LINEMETER

SHAPES = {
    "range_totals": dict(
        d=2, want="about linear", size="around {n} values and {q} ranges", unit="values", n=(2400, 3200), limit="14 * n", imports="",
        naive='''def $f($a, $b):
    """$doc"""
    out = []
    for lo, hi in $b:
        total = 0
        for i in range(lo, hi):
            total += $a[i]
        out.append(total)
    return out
''', fast='''def $f($a, $b):
    """$doc"""
    prefix = [0]
    for value in $a:
        prefix.append(prefix[-1] + value)
    return [prefix[hi] - prefix[lo] for lo, hi in $b]
''', oracle='''def oracle(a, b):
    return [sum(a[lo:hi]) for lo, hi in b]
''', gen='''def small_args(rng):
    values = [rng.randint(-9, 99) for _ in range(rng.randint(0, 25))]
    queries = []
    for _ in range(rng.randint(0, 12)):
        lo = rng.randint(0, len(values))
        queries.append((lo, rng.randint(lo, len(values))))
    return (values, queries)


def big_args(rng, n):
    values = [rng.randint(-50, 500) for _ in range(n)]
    queries = [(rng.randint(0, n // 4), rng.randint(3 * n // 4, n)) for _ in range(n // 2)]
    return (values, queries)
''', spec="`{b}` holds `(lo, hi)` index pairs with `0 <= lo <= hi <= len({a})`; the result lists `sum({a}[lo:hi])` for every pair, in order.",
        vocab=[("segment_sums", ["amounts", "ranges"], "Totals of many slices of one long list of amounts."),
               ("window_totals", ["readings", "windows"], "Total of the sensor readings inside each requested window."),
               ("cumulative_between", ["steps", "spans"], "How many steps were walked inside each span of the log.")]),
    "peak_load": dict(
        d=3, want="O(n log n)", size="around {n} bookings", unit="bookings", n=(1800, 2400), limit="40 * n", imports="import heapq\n",
        naive='''def $f($a):
    """$doc"""
    best = 0
    for start, _ in $a:
        live = 0
        for s, e in $a:
            if s <= start < e:
                live += 1
        best = max(best, live)
    return best
''', fast='''def $f($a):
    """$doc"""
    events = []
    for s, e in $a:
        events.append((s, 1))
        events.append((e, -1))
    events.sort()
    live = best = 0
    for _, delta in events:
        live += delta
        best = max(best, live)
    return best
''', oracle='''def oracle(a):
    import heapq
    ends, best = [], 0
    for s, e in sorted(a):
        while ends and ends[0] <= s:
            heapq.heappop(ends)
        heapq.heappush(ends, e)
        best = max(best, len(ends))
    return best
''', gen='''def small_args(rng):
    items = []
    for _ in range(rng.randint(0, 12)):
        s = rng.randint(0, 30)
        items.append((s, s + rng.randint(1, 10)))
    return (items,)


def big_args(rng, n):
    items = []
    for _ in range(n):
        s = rng.randint(0, 4 * n)
        items.append((s, s + rng.randint(1, 300)))
    return (items,)
''', spec="`{a}` holds `(start, end)` pairs with `start < end`; an item is active from `start` up to but excluding `end`, so an item that ends at `t` does not overlap one that starts at `t`. The result is the largest number of items active at once (0 for no items).",
        vocab=[("peak_sessions", ["sessions"], "The largest number of user sessions that were open at the same time."),
               ("busiest_moment", ["stays"], "The largest number of guests in the building at once."),
               ("max_overlap", ["shifts"], "The largest number of shifts that overlap at one instant.")]),
    "inversions": dict(
        d=4, want="O(n log n)", size="around {n} values", unit="values", n=(1500, 2000), limit="24 * n * n.bit_length()", imports="",
        naive='''def $f($a):
    """$doc"""
    total = 0
    for i in range(len($a)):
        for j in range(i + 1, len($a)):
            if $a[i] > $a[j]:
                total += 1
    return total
''', fast='''def $f($a):
    """$doc"""

    def sort(items):
        if len(items) < 2:
            return items, 0
        mid = len(items) // 2
        left, left_count = sort(items[:mid])
        right, right_count = sort(items[mid:])
        merged, i, j, cross = [], 0, 0, 0
        while i < len(left) and j < len(right):
            if left[i] <= right[j]:
                merged.append(left[i])
                i += 1
            else:
                merged.append(right[j])
                cross += len(left) - i
                j += 1
        merged.extend(left[i:])
        merged.extend(right[j:])
        return merged, left_count + right_count + cross

    return sort(list($a))[1]
''', oracle='''def oracle(a):
    import bisect
    seen, total = [], 0
    for x in reversed(a):
        total += bisect.bisect_left(seen, x)
        bisect.insort(seen, x)
    return total
''', gen='''def small_args(rng):
    return ([rng.randint(0, 20) for _ in range(rng.randint(0, 14))],)


def big_args(rng, n):
    return ([rng.randint(0, 10 * n) for _ in range(n)],)
''', spec="Counts the pairs of positions `i < j` with `{a}[i] > {a}[j]` (equal values are not inversions).",
        vocab=[("count_disorder", ["ranks"], "How far a ranking is from sorted: the number of pairs that appear in the wrong relative order."),
               ("swap_distance", ["order"], "The number of adjacent swaps a bubble sort would need for this list."),
               ("out_of_order_pairs", ["scores"], "How many pairs of results are reversed compared with ascending order.")]),
    "cheapest_cost": dict(
        d=4, want="O((V + E) log V)", size="around {n} nodes and four times as many edges", unit="nodes", n=(900, 1200), limit="90 * n", imports="import heapq\n",
        naive='''def $f($a, $b):
    """$doc"""
    dist = {$b: 0}
    done = set()
    while True:
        node = None
        for cand, d in dist.items():
            if cand not in done and (node is None or d < dist[node]):
                node = cand
        if node is None:
            break
        done.add(node)
        for nbr, w in $a.get(node, ()):
            nd = dist[node] + w
            if nd < dist.get(nbr, float("inf")):
                dist[nbr] = nd
    return dist
''', fast='''def $f($a, $b):
    """$doc"""
    dist = {$b: 0}
    heap = [(0, $b)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist[node]:
            continue
        for nbr, w in $a.get(node, ()):
            nd = d + w
            if nd < dist.get(nbr, nd + 1):
                dist[nbr] = nd
                heapq.heappush(heap, (nd, nbr))
    return dist
''', oracle='''def oracle(a, b):
    import heapq
    best = {}
    queue = [(0, b)]
    while queue:
        cost, node = heapq.heappop(queue)
        if node in best:
            continue
        best[node] = cost
        for nbr, w in a.get(node, ()):
            if nbr not in best:
                heapq.heappush(queue, (cost + w, nbr))
    return best
''', gen='''def small_args(rng):
    size = rng.randint(1, 9)
    graph = {}
    for node in range(size):
        if rng.random() < 0.85:
            graph[node] = [(rng.randrange(size), rng.randint(1, 9)) for _ in range(rng.randint(0, 3))]
    return (graph, rng.randrange(size))


def big_args(rng, n):
    graph = {}
    for node in range(n):
        out = [((node + 1) % n, rng.randint(1, 20))]
        for _ in range(3):
            out.append((rng.randrange(n), rng.randint(1, 20)))
        graph[node] = out
    return (graph, 0)
''', spec="`{a}` maps a node to a list of `(neighbour, weight)` pairs (positive integer weights; nodes without an entry have no outgoing edges). The result maps every node reachable from `{b}` to the cost of its cheapest path; `{b}` itself costs 0 and unreachable nodes are left out.",
        vocab=[("route_costs", ["roads", "origin"], "Cheapest travel cost from the depot to every town it can reach."),
               ("shortest_fares", ["links", "hub"], "Lowest fare from the hub to every airport that can be reached."),
               ("latency_map", ["network", "source"], "Smallest total latency from the source to every host that is reachable.")]),
    "connected_flags": dict(
        d=5, want="close to linear (sort the questions, then union-find)", size="around {n} nodes, a similar number of links and as many questions", unit="nodes",
        n=(500, 700), limit="200 * n", imports="",
        naive='''def $f($a, $b, $c):
    """$doc"""
    answers = []
    for x, y, upto in $c:
        adj = {}
        for u, v in $b[:upto]:
            adj.setdefault(u, []).append(v)
            adj.setdefault(v, []).append(u)
        seen = {x}
        stack = [x]
        while stack:
            cur = stack.pop()
            for nxt in adj.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        answers.append(y in seen)
    return answers
''', fast='''def $f($a, $b, $c):
    """$doc"""
    parent = list(range($a))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    order = sorted(range(len($c)), key=lambda i: $c[i][2])
    answers = [False] * len($c)
    added = 0
    for i in order:
        x, y, upto = $c[i]
        while added < upto:
            u, v = $b[added]
            parent[find(u)] = find(v)
            added += 1
        answers[i] = find(x) == find(y)
    return answers
''', oracle='''def oracle(a, b, c):
    parent = list(range(a))
    size = [1] * a

    def root(x):
        r = x
        while parent[r] != r:
            r = parent[r]
        while parent[x] != r:
            parent[x], x = r, parent[x]
        return r

    result = [None] * len(c)
    progress = 0
    for idx in sorted(range(len(c)), key=lambda k: (c[k][2], k)):
        x, y, upto = c[idx]
        while progress < upto:
            ru, rv = root(b[progress][0]), root(b[progress][1])
            if ru != rv:
                if size[ru] < size[rv]:
                    ru, rv = rv, ru
                parent[rv] = ru
                size[ru] += size[rv]
            progress += 1
        result[idx] = root(x) == root(y)
    return result
''', gen='''def small_args(rng):
    count = rng.randint(1, 10)
    links = [(rng.randrange(count), rng.randrange(count)) for _ in range(rng.randint(0, 14))]
    questions = [(rng.randrange(count), rng.randrange(count), rng.randint(0, len(links))) for _ in range(rng.randint(0, 10))]
    return (count, links, questions)


def big_args(rng, n):
    links = [(rng.randrange(n), rng.randrange(n)) for _ in range(int(n * 1.3))]
    questions = [(rng.randrange(n), rng.randrange(n), rng.randint(0, len(links))) for _ in range(n)]
    return (n, links, questions)
''', spec="`{a}` is the number of nodes (numbered from 0). `{b}` lists links `(u, v)` in the order they were installed. `{c}` lists questions `(x, y, upto)`: using only the first `upto` links, are `x` and `y` connected? The result holds one boolean per question, in question order (a node is connected to itself).",
        vocab=[("linked_by_then", ["count", "cables", "checks"], "Whether two machines could talk to each other at a given point of the cabling work."),
               ("reachable_after", ["sites", "bridges", "probes"], "Whether two islands were joined by the time a given number of bridges had been built."),
               ("joined_at_step", ["nodes", "pipes", "questions"], "Whether two junctions of the water network were connected after a given number of pipes was laid.")]),
    "longest_unique_run": dict(
        d=3, want="linear", size="around {n} items", unit="items", n=(2400, 3200), limit="24 * n", imports="",
        naive='''def $f($a):
    """$doc"""
    best = 0
    for start in range(len($a)):
        seen = set()
        for item in $a[start:]:
            if item in seen:
                break
            seen.add(item)
        best = max(best, len(seen))
    return best
''', fast='''def $f($a):
    """$doc"""
    last = {}
    start = best = 0
    for i, item in enumerate($a):
        if item in last and last[item] >= start:
            start = last[item] + 1
        last[item] = i
        best = max(best, i - start + 1)
    return best
''', oracle='''def oracle(a):
    window, left, best = {}, 0, 0
    for right, item in enumerate(a):
        if window.get(item, -1) >= left:
            left = window[item] + 1
        window[item] = right
        best = max(best, right - left + 1)
    return best
''', gen='''def small_args(rng):
    return ([rng.randint(0, 6) for _ in range(rng.randint(0, 16))],)


def big_args(rng, n):
    return ([rng.randrange(40 * n) for _ in range(n)],)
''', spec="Returns the length of the longest block of consecutive items of `{a}` in which no item occurs twice (0 for an empty list).",
        vocab=[("longest_clean_run", ["events"], "Longest stretch of the event log without the same event id twice."),
               ("max_distinct_streak", ["tags"], "Longest streak of consecutive tags that are all different."),
               ("fresh_streak", ["ids"], "Longest run of consecutive ids that never repeats one.")]),
    "longest_span_with_sum": dict(
        d=4, want="linear", size="around {n} values", unit="values", n=(2400, 3200), limit="24 * n", imports="",
        naive='''def $f($a, $b):
    """$doc"""
    best = 0
    for start in range(len($a)):
        total = 0
        for end in range(start, len($a)):
            total += $a[end]
            if total == $b:
                best = max(best, end - start + 1)
    return best
''', fast='''def $f($a, $b):
    """$doc"""
    first = {0: -1}
    total = best = 0
    for i, v in enumerate($a):
        total += v
        if total - $b in first:
            best = max(best, i - first[total - $b])
        first.setdefault(total, i)
    return best
''', oracle='''def oracle(a, b):
    seen, run, best = {0: -1}, 0, 0
    for idx, v in enumerate(a):
        run += v
        if run - b in seen:
            best = max(best, idx - seen[run - b])
        if run not in seen:
            seen[run] = idx
    return best
''', gen='''def small_args(rng):
    return ([rng.randint(-4, 9) for _ in range(rng.randint(0, 16))], rng.randint(-5, 20))


def big_args(rng, n):
    return ([rng.randint(-3, 8) for _ in range(n)], rng.randint(100, 400))
''', spec="Returns the length of the longest non-empty contiguous slice of `{a}` whose elements add up to exactly `{b}` (0 when no slice does). Values can be negative.",
        vocab=[("longest_balanced_span", ["deltas", "target"], "Longest contiguous stretch of balance changes that nets out to exactly the target."),
               ("steadiest_stretch", ["changes", "goal"], "Longest run of consecutive daily changes that adds up to the goal."),
               ("longest_exact_run", ["flows", "wanted"], "Longest block of consecutive cash flows summing to exactly the wanted amount.")]),
    "build_waves": dict(
        d=3, want="linear in tasks plus dependencies", size="around {n} tasks in a few hundred waves", unit="tasks", n=(900, 1200), limit="80 * n", imports="",
        naive='''def $f($a):
    """$doc"""
    remaining = set($a)
    done = set()
    waves = []
    while remaining:
        ready = sorted(t for t in remaining if all(p in done for p in $a[t]))
        waves.append(ready)
        done.update(ready)
        remaining.difference_update(ready)
    return waves
''', fast='''def $f($a):
    """$doc"""
    waiting = {t: len(ps) for t, ps in $a.items()}
    children = {}
    for t, ps in $a.items():
        for p in ps:
            children.setdefault(p, []).append(t)
    wave = sorted(t for t, c in waiting.items() if c == 0)
    waves = []
    while wave:
        waves.append(wave)
        nxt = []
        for t in wave:
            for c in children.get(t, ()):
                waiting[c] -= 1
                if waiting[c] == 0:
                    nxt.append(c)
        wave = sorted(nxt)
    return waves
''', oracle='''def oracle(a):
    import sys
    sys.setrecursionlimit(10000)
    level = {}

    def depth(t):
        if t not in level:
            level[t] = 1 + max((depth(p) for p in a[t]), default=-1)
        return level[t]

    groups = {}
    for t in a:
        groups.setdefault(depth(t), []).append(t)
    return [sorted(groups[k]) for k in sorted(groups)]
''', gen='''def small_args(rng):
    size = rng.randint(0, 12)
    names = ["t%d" % i for i in range(size)]
    needs = {}
    for i, name in enumerate(names):
        pool = names[:i]
        needs[name] = rng.sample(pool, rng.randint(0, min(3, len(pool))))
    items = list(needs.items())
    rng.shuffle(items)
    return (dict(items),)


def big_args(rng, n):
    width = 4
    layers = [["t%d" % (layer * width + k) for k in range(width)] for layer in range(n // width)]
    needs = {}
    for idx, layer in enumerate(layers):
        for name in layer:
            if idx == 0:
                needs[name] = []
            else:
                needs[name] = rng.sample(layers[idx - 1], rng.randint(1, 3))
    items = list(needs.items())
    rng.shuffle(items)
    return (dict(items),)
''', spec="`{a}` maps each task to the list of tasks it needs first (every task is a key; there are no cycles or repeated entries). The result is a list of waves: wave 0 holds the tasks with no prerequisites, and each later wave holds the tasks whose prerequisites all sit in earlier waves. Every wave is sorted.",
        vocab=[("plan_waves", ["needs"], "Group build steps into waves that can each run in parallel."),
               ("stage_order", ["requires"], "Split the migrations into stages: everything in a stage only depends on earlier stages."),
               ("release_stages", ["depends_on"], "Work out which services can be deployed together, stage by stage.")]),
    "longest_rising": dict(
        d=4, want="O(n log n)", size="around {n} values", unit="values", n=(2400, 3200), limit="20 * n", imports="import bisect\n",
        naive='''def $f($a):
    """$doc"""
    best = [1] * len($a)
    for i in range(len($a)):
        for j in range(i):
            if $a[j] < $a[i] and best[j] + 1 > best[i]:
                best[i] = best[j] + 1
    return max(best, default=0)
''', fast='''def $f($a):
    """$doc"""
    tails = []
    for x in $a:
        k = bisect.bisect_left(tails, x)
        if k == len(tails):
            tails.append(x)
        else:
            tails[k] = x
    return len(tails)
''', oracle='''def oracle(a):
    from bisect import bisect_left
    piles = []
    for x in a:
        pos = bisect_left(piles, x)
        piles[pos:pos + 1] = [x]
    return len(piles)
''', gen='''def small_args(rng):
    return ([rng.randint(0, 15) for _ in range(rng.randint(0, 14))],)


def big_args(rng, n):
    return ([rng.randint(0, 10 ** 6) for _ in range(n)],)
''', spec="Returns the length of the longest strictly increasing subsequence of `{a}` (not necessarily contiguous; 0 for an empty list).",
        vocab=[("longest_climb", ["heights"], "Longest chain of measurements that keeps strictly rising when you skip the dips."),
               ("best_streak_of_records", ["scores"], "How many successive personal bests are possible in this score history."),
               ("rising_chain", ["readings"], "Length of the longest strictly rising subsequence of the readings.")]),
    "next_larger": dict(
        d=3, want="linear", size="around {n} values", unit="values", n=(2400, 3200), limit="20 * n", imports="",
        naive='''def $f($a):
    """$doc"""
    out = []
    for i in range(len($a)):
        found = -1
        for j in range(i + 1, len($a)):
            if $a[j] > $a[i]:
                found = j
                break
        out.append(found)
    return out
''', fast='''def $f($a):
    """$doc"""
    out = [-1] * len($a)
    pending = []
    for i, x in enumerate($a):
        while pending and $a[pending[-1]] < x:
            out[pending.pop()] = i
        pending.append(i)
    return out
''', oracle='''def oracle(a):
    out, stack = [-1] * len(a), []
    for i in range(len(a) - 1, -1, -1):
        while stack and a[stack[-1]] <= a[i]:
            stack.pop()
        out[i] = stack[-1] if stack else -1
        stack.append(i)
    return out
''', gen='''def small_args(rng):
    return ([rng.randint(0, 9) for _ in range(rng.randint(0, 14))],)


def big_args(rng, n):
    return (sorted(rng.sample(range(10 * n), n), reverse=True),)
''', spec="For every position `i` the result holds the smallest index `j > i` with `{a}[j] > {a}[i]`, or -1 when there is none.",
        vocab=[("next_higher", ["prices"], "For each day, the next day on which the price is strictly higher."),
               ("first_bigger_after", ["loads"], "For every sample, the position of the next sample with a bigger load."),
               ("upcoming_peak", ["temps"], "For each hour, when the temperature next exceeds the current one.")]),
    "subset_sum_exists": dict(
        d=3, want="pseudo-polynomial (a table of reachable sums)", size="around {n} positive numbers and a target in the high hundreds", unit="numbers", n=(22, 24),
        limit="6 * len(args[0]) * args[1]", imports="",
        naive='''def $f($a, $b):
    """$doc"""

    def go(i, left):
        if left == 0:
            return True
        if i == len($a) or left < 0:
            return False
        return go(i + 1, left - $a[i]) or go(i + 1, left)

    return go(0, $b)
''', fast='''def $f($a, $b):
    """$doc"""
    reachable = {0}
    for x in $a:
        reachable |= {s + x for s in reachable if s + x <= $b}
    return $b in reachable
''', oracle='''def oracle(a, b):
    bits = 1
    for x in a:
        bits |= bits << x
    return bool((bits >> b) & 1)
''', gen='''def small_args(rng):
    return ([rng.randint(1, 12) for _ in range(rng.randint(0, 8))], rng.randint(0, 40))


def big_args(rng, n):
    nums = [2 * rng.randint(10, 60) for _ in range(n)]
    return (nums, sum(nums) // 2 | 1)
''', spec="`{a}` holds positive integers; the result says whether some subset of them (each used at most once, the empty subset allowed) adds up to exactly `{b}`.",
        vocab=[("can_fill_exactly", ["weights", "capacity"], "Whether some of the parcels fill the van exactly to its capacity."),
               ("exact_budget_possible", ["prices", "budget"], "Whether a selection of the items costs exactly the budget."),
               ("payable_exactly", ["parts", "total"], "Whether the invoice total can be paid with a subset of the received payments.")]),
    "prefix_counts": dict(
        d=3, want="about O((n + p) log n), or a trie", size="around {n} words and as many prefixes", unit="words", n=(2400, 3200),
        limit="10 * sum(len(w) for w in args[0]) + 20 * len(args[1])", imports="import bisect\n",
        naive='''def $f($a, $b):
    """$doc"""
    return [sum(1 for word in $a if word.startswith(p)) for p in $b]
''', fast='''def $f($a, $b):
    """$doc"""
    ordered = sorted($a)
    out = []
    for p in $b:
        lo = bisect.bisect_left(ordered, p)
        hi = bisect.bisect_right(ordered, p + "\\U0010ffff")
        out.append(hi - lo)
    return out
''', oracle='''def oracle(a, b):
    ordered = sorted(a)
    from bisect import bisect_left, bisect_right
    return [bisect_right(ordered, p + chr(0x10FFFF)) - bisect_left(ordered, p) for p in b]
''', gen='''LETTERS = "abcdefghij"


def small_args(rng):
    words = ["".join(rng.choice("abc") for _ in range(rng.randint(0, 5))) for _ in range(rng.randint(0, 14))]
    prefixes = ["".join(rng.choice("abc") for _ in range(rng.randint(0, 3))) for _ in range(rng.randint(0, 8))]
    return (words, prefixes)


def big_args(rng, n):
    words = ["".join(rng.choice(LETTERS) for _ in range(rng.randint(4, 8))) for _ in range(n)]
    prefixes = ["".join(rng.choice(LETTERS) for _ in range(rng.randint(1, 4))) for _ in range(n)]
    return (words, prefixes)
''', spec="For every prefix in `{b}` the result holds how many strings of `{a}` start with it (a string is a prefix of itself, the empty prefix matches everything; repeated strings count each time).",
        vocab=[("count_by_prefix", ["names", "prefixes"], "How many customers have a name starting with each of the typed prefixes."),
               ("autocomplete_sizes", ["words", "typed"], "How many dictionary words a search box would suggest for each typed prefix."),
               ("route_prefix_hits", ["paths", "prefixes"], "How many request paths fall under each URL prefix.")]),
    "shared_length": dict(
        d=3, want="O(len(a) * len(b))", size="two strings of around {n} characters", unit="characters", n=(54, 58), limit="10 * len(args[0]) * len(args[1])", imports="",
        naive='''def $f($a, $b):
    """$doc"""

    def go(i, j):
        if i == len($a) or j == len($b):
            return 0
        if $a[i] == $b[j]:
            return 1 + go(i + 1, j + 1)
        return max(go(i + 1, j), go(i, j + 1))

    return go(0, 0)
''', fast='''def $f($a, $b):
    """$doc"""
    prev = [0] * (len($b) + 1)
    for x in $a:
        cur = [0]
        for j, y in enumerate($b):
            cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]
''', oracle='''def oracle(a, b):
    table = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) - 1, -1, -1):
        for j in range(len(b) - 1, -1, -1):
            table[i][j] = table[i + 1][j + 1] + 1 if a[i] == b[j] else max(table[i + 1][j], table[i][j + 1])
    return table[0][0]
''', gen='''def small_args(rng):
    return ("".join(rng.choice("abc") for _ in range(rng.randint(0, 8))), "".join(rng.choice("abc") for _ in range(rng.randint(0, 8))))


def big_args(rng, n):
    return ("".join(rng.choice("abcd") for _ in range(n)), "".join(rng.choice("abcd") for _ in range(n)))
''', spec="Returns the length of the longest common subsequence of the two strings (characters in the same order, not necessarily adjacent).",
        vocab=[("common_stretch", ["left", "right"], "How much of two versions of a line survives unchanged, as a subsequence."),
               ("diff_overlap", ["old", "new"], "Size of the common core of the old and the new text in a diff."),
               ("matching_length", ["first", "second"], "Length of the longest subsequence the two sequence reads have in common.")]),
    "coin_ways": dict(
        d=3, want="O(amount * coins)", size="an amount of a few hundred and about six coin values", unit="coin values", n=(320, 400), limit="10 * len(args[1]) * (args[0] + 1)", imports="",
        naive='''def $f($a, $b):
    """$doc"""

    def go(i, left):
        if left == 0:
            return 1
        if i == len($b) or left < 0:
            return 0
        return go(i, left - $b[i]) + go(i + 1, left)

    return go(0, $a)
''', fast='''def $f($a, $b):
    """$doc"""
    ways = [1] + [0] * $a
    for coin in $b:
        for value in range(coin, $a + 1):
            ways[value] += ways[value - coin]
    return ways[$a]
''', oracle='''def oracle(a, b):
    table = [0] * (a + 1)
    table[0] = 1
    for c in b:
        for v in range(c, a + 1):
            table[v] += table[v - c]
    return table[a]
''', gen='''def small_args(rng):
    coins = sorted(rng.sample(range(1, 10), rng.randint(0, 4)))
    return (rng.randint(0, 30), coins)


def big_args(rng, n):
    coins = sorted({1} | set(rng.sample([2, 3, 5, 10, 20, 25, 50], rng.randint(4, 6))))
    return (n, coins)
''', spec="`{b}` lists distinct positive coin values (unlimited supply of each). The result is the number of different multisets of coins that add up to `{a}` (order does not matter; `{a}` of 0 has exactly one way).",
        vocab=[("count_payments", ["amount", "coins"], "How many different ways a cashier can pay out the amount in the available coins."),
               ("ways_to_change", ["total", "denoms"], "Number of ways to make change for the total."),
               ("package_mixes", ["units", "sizes"], "Number of different mixes of package sizes that add up to the ordered units.")]),
    "best_schedule": dict(
        d=5, want="O(n log n), or at the very least a quadratic dynamic programme", size="around {n} jobs", unit="jobs", n=(56, 64), limit="6 * n * n", imports="import bisect\n",
        naive='''def $f($a):
    """$doc"""
    jobs = sorted($a)

    def best(i):
        if i == len(jobs):
            return 0
        s, e, p = jobs[i]
        j = i + 1
        while j < len(jobs) and jobs[j][0] < e:
            j += 1
        return max(best(i + 1), p + best(j))

    return best(0)
''', fast='''def $f($a):
    """$doc"""
    jobs = sorted($a, key=lambda job: job[1])
    ends = [job[1] for job in jobs]
    table = [0]
    for k, (s, e, p) in enumerate(jobs):
        prior = bisect.bisect_right(ends, s, 0, k)
        table.append(max(table[-1], table[prior] + p))
    return table[-1]
''', oracle='''def oracle(a):
    jobs = sorted(a, key=lambda job: (job[1], job[0], job[2]))
    best = [0] * (len(jobs) + 1)
    for k, (s, e, p) in enumerate(jobs, 1):
        compatible = max((best[m] for m in range(k) if m == 0 or jobs[m - 1][1] <= s), default=0)
        best[k] = max(best[k - 1], compatible + p)
    return best[-1]
''', gen='''def small_args(rng):
    jobs = []
    for _ in range(rng.randint(0, 9)):
        s = rng.randint(0, 15)
        jobs.append((s, s + rng.randint(1, 6), rng.randint(1, 9)))
    return (jobs,)


def big_args(rng, n):
    jobs = []
    for _ in range(n):
        s = rng.randint(0, 2 * n)
        jobs.append((s, s + rng.randint(2, 14), rng.randint(1, 50)))
    return (jobs,)
''', spec="`{a}` holds `(start, end, profit)` jobs with `start < end` and positive profit. Two chosen jobs must not overlap, but one may start exactly when another ends. The result is the largest total profit of a valid selection (0 for no jobs).",
        vocab=[("best_booking_value", ["offers"], "Choose which booking offers to accept so that the revenue is as high as possible."),
               ("max_contract_income", ["contracts"], "The highest total income from contracts that can be worked one after the other."),
               ("most_valuable_slots", ["requests"], "Pick non-overlapping meeting-room requests with the highest total value.")]),
    "fewest_steps": dict(
        d=4, want="O(rows * cols)", size="an {n} by {n} grid with a few walls", unit="grid side", n=(7, 8), limit="80 * n * n", imports="from collections import deque\n",
        naive='''def $f($a, $b, $c):
    """$doc"""
    best = [-1]

    def walk(r, c, steps, seen):
        if best[0] != -1 and steps >= best[0]:
            return
        if (r, c) == $c:
            best[0] = steps
            return
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < len($a) and 0 <= nc < len($a[0]) and $a[nr][nc] != "#" and (nr, nc) not in seen:
                walk(nr, nc, steps + 1, seen | {(nr, nc)})

    walk($b[0], $b[1], 0, {$b})
    return best[0]
''', fast='''def $f($a, $b, $c):
    """$doc"""
    dist = {$b: 0}
    queue = deque([$b])
    while queue:
        r, c = queue.popleft()
        if (r, c) == $c:
            return dist[(r, c)]
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < len($a) and 0 <= nc < len($a[0]) and $a[nr][nc] != "#" and (nr, nc) not in dist:
                dist[(nr, nc)] = dist[(r, c)] + 1
                queue.append((nr, nc))
    return -1
''', oracle='''def oracle(a, b, c):
    frontier, seen, steps = [b], {b}, 0
    while frontier:
        if c in frontier:
            return steps
        nxt = []
        for r, col in frontier:
            for nr, nc in ((r + 1, col), (r - 1, col), (r, col + 1), (r, col - 1)):
                if 0 <= nr < len(a) and 0 <= nc < len(a[0]) and a[nr][nc] != "#" and (nr, nc) not in seen:
                    seen.add((nr, nc))
                    nxt.append((nr, nc))
        frontier = nxt
        steps += 1
    return -1
''', gen='''def _grid(rng, rows, cols, walls):
    cells = [["."] * cols for _ in range(rows)]
    for _ in range(walls):
        r, c = rng.randrange(rows), rng.randrange(cols)
        if (r, c) not in ((0, 0), (rows - 1, cols - 1)):
            cells[r][c] = "#"
    return ["".join(row) for row in cells]


def small_args(rng):
    rows, cols = rng.randint(2, 4), rng.randint(2, 4)
    return (_grid(rng, rows, cols, rng.randint(0, 6)), (0, 0), (rows - 1, cols - 1))


def big_args(rng, n):
    return (_grid(rng, n, n, n - 1), (0, 0), (n - 1, n - 1))
''', spec="`{a}` is a list of equal-length strings, `#` is a wall and `.` is open floor. `{b}` and `{c}` are `(row, column)` cells (both open). The result is the fewest moves (up, down, left, right, never onto a wall or off the grid) from `{b}` to `{c}`, or -1 when it cannot be reached.",
        vocab=[("shortest_walk", ["grid", "start", "goal"], "Fewest moves a robot needs to cross the warehouse floor."),
               ("min_moves", ["floor", "entry", "exit_cell"], "Minimum number of steps from the entrance to the exit of a floor plan."),
               ("steps_to_exit", ["maze", "begin", "target"], "Length of the shortest path through the maze.")]),
}

PKGS = ["routeplan", "datajobs", "gridwork", "opsmath", "batchcalc", "sched", "nightly", "ledgerlab"]
MODS = ["core", "algos", "compute", "queries", "analysis"]

PROMPTS = [
    "`{f}` in `{path}` gives the right answers, but its work explodes with the input: the nightly job feeds it {size} and never finishes. {doc} Rewrite it with a better algorithm "
    "({want} is what we are after). The signature and the results must stay exactly the same. There is no stopwatch in the check: it counts the Python lines executed inside the "
    "`{pkg}` package on a large input, with a budget that leaves a sensible solution plenty of room, so only a real improvement in complexity will get under it.",
    "perf: `{f}` ({path}). {doc} It is hopeless for {size}. Keep the contract in the README but change the algorithm (target: {want}). "
    "The grader counts executed lines in `{pkg}/` instead of seconds, so shaving a constant factor will not be enough.",
    "Could you speed up `{f}` in `{path}`? {doc} Profiling says the algorithm itself is the problem: it is the brute-force version and with {size} it needs orders of magnitude more "
    "steps than a good solution. Same inputs, same outputs, same signature. Target complexity: {want}. The check counts how many lines of `{pkg}` get executed on a big input and "
    "compares that with a budget.",
]


def test_text(sp, f, nargs, which, seed, n, pkg, mod, limit):
    names = ["a", "b", "c"][:nargs]
    header = (f"import copy\nimport importlib\nimport os\nimport random\nimport unittest\n\nfrom linemeter import BudgetExceeded, LineMeter\nfrom {pkg}.{mod} import {f}\n\n\n"
              f"{sp['oracle']}\n\n{sp['gen']}\n\n")
    if which == "correct":
        return header + dd(f'''
        class CorrectnessTests(unittest.TestCase):
            def test_matches_the_reference_on_random_inputs(self):
                rng = random.Random({seed})
                for _ in range(150):
                    args = small_args(rng)
                    self.assertEqual({f}(*copy.deepcopy(args)), oracle(*copy.deepcopy(args)), args)

            def test_inputs_are_not_modified(self):
                rng = random.Random({seed + 1})
                for _ in range(40):
                    args = small_args(rng)
                    before = copy.deepcopy(args)
                    {f}(*args)
                    self.assertEqual(args, before)
        ''')
    return header + dd(f'''
    PACKAGE_DIR = os.path.dirname(os.path.abspath(importlib.import_module("{pkg}").__file__))
    LIMIT = {limit}


    class PerformanceTests(unittest.TestCase):
        def test_executed_lines_stay_within_budget(self):
            rng = random.Random({seed})
            n = {n}
            args = big_args(rng, n)
            expected = oracle(*copy.deepcopy(args))
            meter = LineMeter(PACKAGE_DIR, budget=2 * LIMIT)
            try:
                with meter:
                    got = {f}(*copy.deepcopy(args))
            except BudgetExceeded:
                self.fail("PERF: still running after %d executed lines of {pkg} code (budget %d) on an input of size %d: the algorithm does far too much work" % (meter.lines, LIMIT, n))
            self.assertEqual(got, expected)
            self.assertLessEqual(meter.lines, LIMIT, "PERF: %d executed lines of {pkg} code on an input of size %d (budget %d): the algorithm does too much work" % (meter.lines, n, LIMIT))
    ''')


def calib_text(sp, f, seed, n, pkg, mod):
    return (f"import importlib, os, random\nfrom linemeter import LineMeter\nfrom {pkg}.{mod} import {f}\n\n{sp['gen']}\n\n"
            f"root = os.path.dirname(os.path.abspath(importlib.import_module('{pkg}').__file__))\nargs = big_args(random.Random({seed}), {n})\n"
            f"m = LineMeter(root)\nwith m:\n    {f}(*args)\nprint('LINES', m.lines)\n")


@family("optimize-py-algorithms", category="optimize", lang="python", kind="feature", n=20,
        summary="brute-force algorithms (range sums, sweeps, union-find, Dijkstra, LIS, DP) that need a better algorithm: a budget on executed lines, not seconds")
def gen(rng, n):
    keys = list(SHAPES)
    rng.shuffle(keys)
    extra = [k for k in keys if SHAPES[k]["d"] >= 4]
    rng.shuffle(extra)
    order = keys + extra
    used = set()
    for i in range(n):
        shape = order[i % len(order)]
        sp = SHAPES[shape]
        vocab = [v for v in sp["vocab"] if (shape, v[0]) not in used] or sp["vocab"]
        f, argn, doc = rng.choice(vocab)
        used.add((shape, f))
        pkg, mod = rng.choice(PKGS), rng.choice(MODS)
        names = {"f": f, "doc": doc, "a": argn[0], "b": argn[1] if len(argn) > 1 else "", "c": argn[2] if len(argn) > 2 else ""}
        naive = Template(sp["naive"]).substitute(names)
        fast = Template(sp["fast"]).substitute(names)
        helper = dd('''
        def describe(count, noun):
            """Pluralised count for log lines."""
            return "%d %s%s" % (count, noun, "" if count == 1 else "s")
        ''')
        head = f'"""{pkg}: calculations used by the nightly batch jobs."""\n'
        start_src = head + "\n\n" + naive + "\n\n" + helper
        sol_src = head + sp["imports"] + "\n\n" + fast + "\n\n" + helper
        spec = sp["spec"].format(a=names["a"], b=names["b"], c=names["c"])
        readme = dd(f'''
        # {pkg}

        ## `{mod}.{f}({", ".join(argn)})`

        {doc}

        {spec}

        The batch job calls it with large inputs, so the amount of work has to grow slowly with their size. The function must not modify its arguments.
        ''')
        files = {f"{pkg}/{mod}.py": start_src, f"{pkg}/__init__.py": "", "README.md": readme}
        ns = {}
        exec(sp["oracle"], ns)
        exec(sp["gen"], ns)
        r = random.Random(100 + i)
        ex = []
        while len(ex) < 3:
            args = ns["small_args"](r)
            if len(ex) == 0 or any(a for a in args):
                ex.append((args, ns["oracle"](*args)))
        vis = [f"import unittest\n\nfrom {pkg}.{mod} import {f}\n\n\nclass BasicTests(unittest.TestCase):\n"]
        for k, (args, want) in enumerate(ex):
            vis.append(f"    def test_example_{k + 1}(self):\n        self.assertEqual({f}({', '.join(repr(a) for a in args)}), {want!r})\n")
        vis.append("\nif __name__ == '__main__':\n    unittest.main()\n")
        seed = 2000 + i
        lo, hi = sp["n"]
        size = rng.choice(sorted({lo, (lo + hi) // 2, hi}))
        big = ns["big_args"](random.Random(seed), size)
        limit = int(eval(sp["limit"], {"n": size, "args": big, "len": len, "sum": sum}))
        corr = test_text(sp, f, len(argn), "correct", seed, size, pkg, mod, limit)
        perf = test_text(sp, f, len(argn), "perf", seed, size, pkg, mod, limit)
        hidden = {"tests/linemeter.py": LINEMETER, "tests/test_correct_lines.py": corr, "tests/test_perf_lines.py": perf}
        start = {**files, "tests/test_basic.py": "".join(vis)}
        solution = {f"{pkg}/{mod}.py": sol_src}
        # calibration: the reference must use at most a third of the budget
        r = run(merged(start, hidden, solution, {"calib.py": calib_text(sp, f, seed, size, pkg, mod)}), "python3 -c \"import sys; sys.path.insert(0, 'tests'); exec(open('calib.py').read())\"", timeout=180)
        if "LINES" not in r.out:
            raise RuntimeError(f"{shape}/{f}: calibration failed:\n{r.out[-1500:]}")
        used_lines = int(r.out.split("LINES")[1].split()[0])
        if used_lines * 3 > limit:
            raise RuntimeError(f"{shape}/{f}: reference uses {used_lines} lines, budget {limit} leaves less than 3x headroom")
        prove_opt(f"{shape}/{f}", start, hidden, solution, PY_CORRECT, PY_PERF, PY_ALL, timeout=240)
        sizetxt = sp["size"].format(n=f"{size:,}", q=f"{size // 2:,}")
        prompt = rng.choice(PROMPTS).format(f=f, path=f"{pkg}/{mod}.py", doc=doc, size=sizetxt, want=sp["want"], pkg=pkg)
        yield Task(slug=f"{i + 1:02d}-{shape}-{f}", prompt=prompt, difficulty=sp["d"], start=start, hidden=hidden, solution=solution, verify=PY_ALL, timeout_s=300,
                   tags=["algorithms", "complexity", "line-budget"], notes={"shape": shape, "n": size, "limit": limit, "reference_lines": used_lines})
