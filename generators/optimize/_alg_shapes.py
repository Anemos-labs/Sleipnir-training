"""Shapes for optimize-py-algorithms: slow implementations with invented, domain-specific rules (berths, fares, ledgers, build graphs, alert logs, shared capacity), each with a better algorithm."""

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
    "berth_peak": dict(
        d=3, want="O(n log n)", size="around {n} vessel visits", unit="visits", n=(1800, 2400), limit="40 * n", imports="",
        naive='''def $f($a):
    """$doc"""
    buffers = {"S": 1, "M": 2, "L": 4}
    best = 0
    for arrive, _, _ in $a:
        busy = 0
        for start, depart, size in $a:
            if start <= arrive < depart + buffers[size]:
                busy += 1
        best = max(best, busy)
    return best
''', fast='''def $f($a):
    """$doc"""
    buffers = {"S": 1, "M": 2, "L": 4}
    events = []
    for arrive, depart, size in $a:
        events.append((arrive, 1))
        events.append((depart + buffers[size], -1))
    events.sort()
    busy = best = 0
    for _, delta in events:
        busy += delta
        best = max(best, busy)
    return best
''', oracle='''def oracle(a):
    import heapq
    buffers = {"S": 1, "M": 2, "L": 4}
    free_at, best = [], 0
    for arrive, depart, size in sorted(a):
        while free_at and free_at[0] <= arrive:
            heapq.heappop(free_at)
        heapq.heappush(free_at, depart + buffers[size])
        best = max(best, len(free_at))
    return best
''', gen='''def small_args(rng):
    visits = []
    for _ in range(rng.randint(0, 10)):
        arrive = rng.randint(0, 30)
        visits.append((arrive, arrive + rng.randint(1, 8), rng.choice("SML")))
    return (visits,)


def big_args(rng, n):
    visits = []
    for _ in range(n):
        arrive = rng.randint(0, 4 * n)
        visits.append((arrive, arrive + rng.randint(1, 200), rng.choice("SML")))
    return (visits,)
''', spec="`{a}` holds `(arrive, depart, size)` vessel visits with `arrive < depart` and a size class `S`, `M` or `L`. A vessel keeps its berth from `arrive` until `depart` plus a turnaround time of 1, 2 or 4 time units (for S, M and L); the berth is free again at that instant, so a visit that arrives exactly then can take it. The result is the largest number of berths in use at the same time (0 for no visits).",
        vocab=[("berths_needed", ["visits"], "How many berths the harbour must have ready for a day of vessel visits."),
               ("peak_dock_usage", ["calls"], "The busiest moment of the day at the quay, as a number of occupied berths."),
               ("bays_required", ["arrivals"], "How many unloading bays a depot needs for its truck arrivals, turnaround included.")]),
    "fare_capping": dict(
        d=3, want="linear", size="around {n} trips", unit="trips", n=(2400, 3200), limit="20 * n", imports="",
        naive='''def $f($a, $b):
    """$doc"""
    charges = []
    for i, (rider, day, fare) in enumerate($a):
        paid = 0
        for j in range(i):
            other, other_day, _ = $a[j]
            if other == rider and other_day == day:
                paid += charges[j]
        charges.append(min(fare, $b - paid))
    return charges
''', fast='''def $f($a, $b):
    """$doc"""
    paid = {}
    charges = []
    for rider, day, fare in $a:
        so_far = paid.get((rider, day), 0)
        charge = min(fare, $b - so_far)
        paid[(rider, day)] = so_far + charge
        charges.append(charge)
    return charges
''', oracle='''def oracle(a, b):
    paid, out = {}, []
    for rider, day, fare in a:
        key = (rider, day)
        charge = min(fare, b - paid.get(key, 0))
        paid[key] = paid.get(key, 0) + charge
        out.append(charge)
    return out
''', gen='''def small_args(rng):
    trips = [(rng.randint(0, 3), rng.randint(0, 2), rng.randint(1, 9)) for _ in range(rng.randint(0, 14))]
    return (trips, rng.randint(3, 20))


def big_args(rng, n):
    trips = [(rng.randint(0, 39), rng.randint(0, 4), rng.randint(1, 9)) for _ in range(n)]
    return (trips, 25)
''', spec="`{a}` lists trips `(rider, day, fare)` in chronological order. A rider is never charged more than `{b}` in one day: a trip costs its fare until the rider's charges of that day reach the cap, then only what is left under the cap (possibly 0). The result lists the amount charged for every trip, in the same order.",
        vocab=[("daily_charges", ["trips", "cap"], "What each tap-in actually costs on a transit card with a daily cap."),
               ("capped_fares", ["rides", "daily_limit"], "Fares charged to bike-share members with a per-day spending limit."),
               ("metered_costs", ["sessions", "ceiling"], "Costs of parking sessions where a day never costs more than the ceiling.")]),
    "balance_as_of": dict(
        d=3, want="O((n + q) log n)", size="around {n} ledger entries and half as many balance questions", unit="entries", n=(2400, 3200), limit="14 * (n + len(args[1]))", imports="import bisect\n",
        naive='''def $f($a, $b):
    """$doc"""
    out = []
    for account, moment in $b:
        total = 0
        for ts, owner, delta in $a:
            if owner == account and ts <= moment:
                total += delta
        out.append(total)
    return out
''', fast='''def $f($a, $b):
    """$doc"""
    times, sums = {}, {}
    for ts, owner, delta in $a:
        times.setdefault(owner, []).append(ts)
        running = sums.setdefault(owner, [0])
        running.append(running[-1] + delta)
    out = []
    for account, moment in $b:
        k = bisect.bisect_right(times.get(account, []), moment)
        out.append(sums.get(account, [0])[k])
    return out
''', oracle='''def oracle(a, b):
    from bisect import bisect_right
    by = {}
    for ts, owner, delta in a:
        by.setdefault(owner, []).append((ts, delta))
    prefix = {}
    for owner, rows in by.items():
        acc, stamps, totals = 0, [], [0]
        for ts, delta in rows:
            acc += delta
            stamps.append(ts)
            totals.append(acc)
        prefix[owner] = (stamps, totals)
    out = []
    for account, moment in b:
        stamps, totals = prefix.get(account, ([], [0]))
        out.append(totals[bisect_right(stamps, moment)])
    return out
''', gen='''def small_args(rng):
    ledger = sorted((rng.randint(0, 20), rng.randint(0, 3), rng.randint(-9, 9)) for _ in range(rng.randint(0, 14)))
    queries = [(rng.randint(0, 4), rng.randint(0, 22)) for _ in range(rng.randint(0, 8))]
    return (ledger, queries)


def big_args(rng, n):
    ledger = sorted((rng.randint(0, 10 * n), rng.randint(0, 59), rng.randint(-500, 900)) for _ in range(n))
    queries = [(rng.randint(0, 60), rng.randint(0, 10 * n)) for _ in range(n // 2)]
    return (ledger, queries)
''', spec="`{a}` lists ledger entries `(timestamp, account, delta)` ordered by timestamp. `{b}` lists questions `(account, moment)`. For each question the result holds the sum of the deltas of that account's entries with `timestamp <= moment` (0 when there are none, also for accounts that do not appear in the ledger).",
        vocab=[("balances_as_of", ["ledger", "questions"], "Account balances at the moments an auditor asks about."),
               ("stock_levels_at", ["movements", "checks"], "Warehouse stock of a SKU at given points in time."),
               ("meter_totals_until", ["readings", "queries"], "Cumulative consumption of a meter up to a given time.")]),
    "nearest_depot": dict(
        d=3, want="O((n + q) log n)", size="around {n} depots and as many customers", unit="depots", n=(1500, 2000), limit="16 * (n + len(args[1]))", imports="import bisect\n",
        naive='''def $f($a, $b):
    """$doc"""
    out = []
    for spot in $b:
        best = None
        for depot in $a:
            if best is None or abs(depot - spot) < abs(best - spot) or (abs(depot - spot) == abs(best - spot) and depot < best):
                best = depot
        out.append(best)
    return out
''', fast='''def $f($a, $b):
    """$doc"""
    ordered = sorted($a)
    out = []
    for spot in $b:
        k = bisect.bisect_left(ordered, spot)
        candidates = ordered[max(0, k - 1):k + 1]
        out.append(min(candidates, key=lambda depot: (abs(depot - spot), depot)) if candidates else None)
    return out
''', oracle='''def oracle(a, b):
    from bisect import bisect_left
    pts = sorted(set(a))
    out = []
    for spot in b:
        if not pts:
            out.append(None)
            continue
        k = bisect_left(pts, spot)
        left = pts[k - 1] if k > 0 else None
        right = pts[k] if k < len(pts) else None
        if left is None:
            out.append(right)
        elif right is None:
            out.append(left)
        else:
            out.append(left if spot - left <= right - spot else right)
    return out
''', gen='''def small_args(rng):
    depots = [rng.randint(0, 30) for _ in range(rng.randint(0, 6))]
    spots = [rng.randint(-3, 33) for _ in range(rng.randint(0, 8))]
    return (depots, spots)


def big_args(rng, n):
    depots = [rng.randint(0, 20 * n) for _ in range(n)]
    spots = [rng.randint(-50, 20 * n + 50) for _ in range(n)]
    return (depots, spots)
''', spec="`{a}` holds positions of depots along a straight road (integers, repeats possible, possibly empty); `{b}` holds positions of customers. For every customer the result holds the position of the closest depot; when two depots are equally close the one with the smaller position wins; `None` when there are no depots.",
        vocab=[("closest_depots", ["depots", "customers"], "The depot that serves each customer along a highway."),
               ("nearest_chargers", ["stations", "drivers"], "The charging station nearest to each driver on a motorway."),
               ("assign_clinics", ["clinics", "villages"], "The clinic each village on a valley road should use.")]),
    "critical_path": dict(
        d=3, want="linear in tasks plus dependencies", size="a project of around {n} tasks in about 20 stages", unit="tasks", n=(60, 60), limit="50 * n", imports="",
        naive='''def $f($a, $b):
    """$doc"""

    def finish(task):
        hours, needs = $a[task]
        return hours + max((finish(dep) for dep in needs), default=0)

    return finish($b)
''', fast='''def $f($a, $b):
    """$doc"""
    known = {}

    def finish(task):
        if task not in known:
            hours, needs = $a[task]
            known[task] = hours + max((finish(dep) for dep in needs), default=0)
        return known[task]

    return finish($b)
''', oracle='''def oracle(a, b):
    import sys
    sys.setrecursionlimit(10000)
    memo = {}

    def go(t):
        if t not in memo:
            h, ds = a[t]
            memo[t] = h + (max(go(d) for d in ds) if ds else 0)
        return memo[t]

    return go(b)
''', gen='''def _project(rng, n):
    stages = max(1, n // 3)
    names = ["t%d" % i for i in range(n)]
    tasks = {}
    for i, name in enumerate(names):
        stage = i // 3
        prev = [names[j] for j in range((stage - 1) * 3, stage * 3)] if stage > 0 else []
        deps = rng.sample(prev, min(len(prev), rng.randint(1, 3))) if prev else []
        tasks[name] = (rng.randint(1, 9), deps)
    return tasks, names[-1]


def small_args(rng):
    return _project(rng, rng.randint(1, 12))


def big_args(rng, n):
    return _project(rng, n)
''', spec="`{a}` maps every task to `(hours, needs)`: how long it takes and the tasks that must be finished before it can start (a task can start as soon as all of them are done; there are no cycles). The result is the time at which `{b}` is finished when work starts at time 0, with unlimited people.",
        vocab=[("project_finish", ["plan", "target"], "The earliest finish time of a construction task given its prerequisites."),
               ("release_eta", ["stages", "release"], "When the release is ready if every step starts as soon as its inputs exist."),
               ("pipeline_latency", ["jobs", "output"], "End-to-end latency of a data job that waits for its upstream jobs.")]),
    "rerun_set": dict(
        d=4, want="linear in the size of the affected part", size="around {n} modules in a deep import chain and a dozen change sets", unit="modules", n=(300, 400), limit="400 * n", imports="",
        naive='''def $f($a, $b):
    """$doc"""
    results = []
    for changed in $b:
        dirty = set(changed)
        grew = True
        while grew:
            grew = False
            for module, deps in $a.items():
                if module not in dirty and any(dep in dirty for dep in deps):
                    dirty.add(module)
                    grew = True
        results.append(sorted(dirty))
    return results
''', fast='''def $f($a, $b):
    """$doc"""
    importers = {}
    for module, deps in $a.items():
        for dep in deps:
            importers.setdefault(dep, []).append(module)
    results = []
    for changed in $b:
        dirty = set(changed)
        stack = list(dirty)
        while stack:
            current = stack.pop()
            for user in importers.get(current, ()):
                if user not in dirty:
                    dirty.add(user)
                    stack.append(user)
        results.append(sorted(dirty))
    return results
''', oracle='''def oracle(a, b):
    users = {}
    for module, deps in a.items():
        for dep in deps:
            users.setdefault(dep, set()).add(module)
    out = []
    for changed in b:
        seen = set(changed)
        frontier = list(seen)
        while frontier:
            nxt = []
            for m in frontier:
                for u in users.get(m, ()):
                    if u not in seen:
                        seen.add(u)
                        nxt.append(u)
            frontier = nxt
        out.append(sorted(seen))
    return out
''', gen='''def _imports(rng, n):
    names = ["m%03d" % i for i in range(n)]
    graph = {}
    for i, name in enumerate(names):
        lower = names[max(0, i - 4):i]
        graph[name] = rng.sample(lower, min(len(lower), rng.randint(1, 2))) if lower else []
    items = list(graph.items())
    rng.shuffle(items)
    return dict(items), names


def small_args(rng):
    graph, names = _imports(rng, rng.randint(1, 12))
    sets = [rng.sample(names, rng.randint(0, min(3, len(names)))) for _ in range(rng.randint(0, 5))]
    return (graph, sets)


def big_args(rng, n):
    graph, names = _imports(rng, n)
    sets = [rng.sample(names[: n // 3], 2) for _ in range(12)]
    return (graph, sets)
''', spec="`{a}` maps every module to the list of modules it imports (imports only point at other keys, and there are no cycles). `{b}` lists change sets (lists of module names). For each change set the result holds, sorted, the changed modules plus every module that imports one of them directly or indirectly: exactly the modules that have to be rebuilt.",
        vocab=[("modules_to_rebuild", ["imports", "change_sets"], "Which modules a build must redo for each commit's changed files."),
               ("suites_to_rerun", ["uses", "edits"], "Which test suites to rerun after each batch of edits to shared libraries."),
               ("affected_services", ["calls", "deploys"], "Which services are affected by each deployment of an upstream service.")]),
    "escalation_matches": dict(
        d=4, want="linear", size="around {n} alert events from twenty hosts", unit="events", n=(2400, 3200), limit="20 * n", imports="from collections import deque\n",
        naive='''def $f($a, $b):
    """$doc"""
    total = 0
    for i, (host, kind, ts) in enumerate($a):
        if kind != "crit":
            continue
        for j in range(i):
            other_host, other_kind, other_ts = $a[j]
            if other_host == host and other_kind == "warn" and ts - other_ts <= $b:
                total += 1
    return total
''', fast='''def $f($a, $b):
    """$doc"""
    recent = {}
    total = 0
    for host, kind, ts in $a:
        live = recent.setdefault(host, deque())
        while live and ts - live[0] > $b:
            live.popleft()
        if kind == "warn":
            live.append(ts)
        elif kind == "crit":
            total += len(live)
    return total
''', oracle='''def oracle(a, b):
    from collections import deque as dq
    live, total = {}, 0
    for host, kind, ts in a:
        q = live.setdefault(host, dq())
        while q and q[0] < ts - b:
            q.popleft()
        if kind == "warn":
            q.append(ts)
        elif kind == "crit":
            total += len(q)
    return total
''', gen='''def small_args(rng):
    events, ts = [], 0
    for _ in range(rng.randint(0, 14)):
        ts += rng.randint(0, 3)
        events.append(("h%d" % rng.randint(0, 2), rng.choice(["warn", "crit", "info"]), ts))
    return (events, rng.randint(0, 8))


def big_args(rng, n):
    events, ts = [], 0
    for _ in range(n):
        ts += rng.randint(0, 2)
        events.append(("h%d" % rng.randint(0, 19), rng.choice(["warn", "crit", "info"]), ts))
    return (events, 10 * n)
''', spec="`{a}` lists alert events `(host, kind, timestamp)` in chronological order; the kind is `warn`, `crit` or `info`. A `warn` escalates to a later `crit` when both are on the same host, the `warn` comes earlier in the list and the `crit` follows within `{b}` time units (`crit.timestamp - warn.timestamp <= {b}`). The result is the number of such (warn, crit) pairs; one warn can escalate to several crits and the other way round.",
        vocab=[("escalation_pairs", ["events", "window"], "How many warnings were followed by a critical alert on the same host in time."),
               ("followups_counted", ["log", "within"], "Number of warning-then-failure pairs in a service log."),
               ("alarm_chains", ["alerts", "horizon"], "How often a sensor warning turned into a critical alarm on the same machine.")]),
    "overlap_report": dict(
        d=4, want="O((w + i) log w)", size="around {n} maintenance windows and as many incidents", unit="windows", n=(1800, 2400), limit="16 * (n + len(args[1]))", imports="import bisect\n",
        naive='''def $f($a, $b):
    """$doc"""
    out = []
    for begin, end in $b:
        count = 0
        for start, stop in $a:
            if start < end and stop > begin:
                count += 1
        out.append(count)
    return out
''', fast='''def $f($a, $b):
    """$doc"""
    starts = sorted(start for start, _ in $a)
    stops = sorted(stop for _, stop in $a)
    out = []
    for begin, end in $b:
        started_before_end = bisect.bisect_left(starts, end)
        stopped_before_begin = bisect.bisect_right(stops, begin)
        out.append(started_before_end - stopped_before_begin)
    return out
''', oracle='''def oracle(a, b):
    from bisect import bisect_left, bisect_right
    s = sorted(x[0] for x in a)
    e = sorted(x[1] for x in a)
    return [bisect_left(s, hi) - bisect_right(e, lo) for lo, hi in b]
''', gen='''def small_args(rng):
    def span():
        start = rng.randint(0, 30)
        return (start, start + rng.randint(1, 8))
    return ([span() for _ in range(rng.randint(0, 10))], [span() for _ in range(rng.randint(0, 8))])


def big_args(rng, n):
    def span(width):
        start = rng.randint(0, 20 * n)
        return (start, start + rng.randint(1, width))
    return ([span(300) for _ in range(n)], [span(300) for _ in range(n)])
''', spec="`{a}` holds `(start, stop)` windows and `{b}` holds `(begin, end)` incidents, all with start < stop (half-open: the stop instant is not part of the window). For each incident the result holds the number of windows that overlap it, i.e. `start < end` and `stop > begin`.",
        vocab=[("windows_hit", ["windows", "incidents"], "How many maintenance windows overlapped each reported incident."),
               ("overlapping_bookings", ["bookings", "requests"], "How many existing bookings clash with each new room request."),
               ("conflicts_per_request", ["leases", "requests"], "How many existing leases clash with each requested lease period.")]),
    "fair_share": dict(
        d=4, want="O(n log capacity)", size="around {n} requests and a capacity in the hundreds of thousands", unit="requests", n=(300, 400), limit="150 * n", imports="",
        naive='''def $f($a, $b):
    """$doc"""
    if sum($b) <= $a:
        return list($b)
    level = 0
    while sum(min(d, level + 1) for d in $b) <= $a:
        level += 1
    shares = [min(d, level) for d in $b]
    left = $a - sum(shares)
    for i, d in enumerate($b):
        if left > 0 and d > level:
            shares[i] += 1
            left -= 1
    return shares
''', fast='''def $f($a, $b):
    """$doc"""
    if sum($b) <= $a:
        return list($b)
    lo, hi = 0, max($b)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if sum(min(d, mid) for d in $b) <= $a:
            lo = mid
        else:
            hi = mid - 1
    shares = [min(d, lo) for d in $b]
    left = $a - sum(shares)
    for i, d in enumerate($b):
        if left > 0 and d > lo:
            shares[i] += 1
            left -= 1
    return shares
''', oracle='''def oracle(a, b):
    if sum(b) <= a:
        return list(b)
    order = sorted(b)
    remaining, level = a, 0
    for k, d in enumerate(order):
        share = remaining // (len(order) - k)
        if d <= share:
            remaining -= d
        else:
            level = share
            break
    out = [min(d, level) for d in b]
    left = a - sum(out)
    for i, d in enumerate(b):
        if left > 0 and d > level:
            out[i] += 1
            left -= 1
    return out
''', gen='''def small_args(rng):
    demands = [rng.randint(0, 12) for _ in range(rng.randint(0, 7))]
    return (rng.randint(0, 40), demands)


def big_args(rng, n):
    demands = [rng.randint(1, 4000) for _ in range(n)]
    return (sum(demands) // 2, demands)
''', spec="`{a}` is the capacity (a non-negative integer) and `{b}` lists what each requester asks for. When everything fits, everyone gets what they ask for. Otherwise every requester gets `min(demand, level)`, where `level` is the largest integer for which these shares still add up to at most the capacity; the units that are still left over (fewer than the number of requesters asking for more than `level`) are handed out one each to requesters whose demand exceeds `level`, in list order. The result lists the share of every requester in input order.",
        vocab=[("bandwidth_shares", ["capacity", "requests"], "How a link's capacity is split among flows so that no one gets more than they ask for and the rest is shared evenly."),
               ("seat_allotment", ["seats", "applications"], "How many seats each school gets when applications exceed the seats available."),
               ("grant_split", ["budget", "claims"], "How a grant budget is divided among claims as evenly as the claims allow.")]),
    "slowest_in_window": dict(
        d=5, want="O(n log n)", size="around {n} requests", unit="requests", n=(2000, 2600), limit="100 * n", imports="import heapq\n",
        naive='''def $f($a, $b):
    """$doc"""
    out = []
    for i, (ts, _) in enumerate($a):
        window = [latency for stamp, latency in $a[:i + 1] if stamp > ts - $b]
        out.append(sum(sorted(window, reverse=True)[:3]))
    return out
''', fast='''def $f($a, $b):
    """$doc"""
    heap = []
    start = 0
    out = []
    for i, (ts, latency) in enumerate($a):
        heapq.heappush(heap, (-latency, i))
        while $a[start][0] <= ts - $b:
            start += 1
        total, kept = 0, []
        while heap and len(kept) < 3:
            negative, j = heapq.heappop(heap)
            if j < start:
                continue
            kept.append((negative, j))
            total -= negative
        for item in kept:
            heapq.heappush(heap, item)
        out.append(total)
    return out
''', oracle='''def oracle(a, b):
    out, lo = [], 0
    for i, (ts, _) in enumerate(a):
        while a[lo][0] <= ts - b:
            lo += 1
        out.append(sum(sorted((lat for _, lat in a[lo:i + 1]), reverse=True)[:3]))
    return out
''', gen='''def small_args(rng):
    ts, reqs = 0, []
    for _ in range(rng.randint(0, 14)):
        ts += rng.randint(0, 4)
        reqs.append((ts, rng.randint(1, 50)))
    return (reqs, rng.randint(1, 12))


def big_args(rng, n):
    ts, reqs = 0, []
    for _ in range(n):
        ts += rng.randint(0, 2)
        reqs.append((ts, rng.randint(1, 5000)))
    return (reqs, 120)
''', spec="`{a}` lists requests `(timestamp, latency)` ordered by timestamp. For every request the result holds the sum of the three largest latencies among the requests of the trailing window that ends with it: those with `timestamp > this_timestamp - {b}`, this request included (fewer than three requests: the sum of what is there).",
        vocab=[("slowest_three_sum", ["requests", "span"], "A load-balancer health score: the three slowest responses within the trailing window, summed."),
               ("worst_latency_score", ["calls", "horizon"], "For every API call, how bad the three worst calls of the last couple of minutes were."),
               ("peak_delay_total", ["jobs", "width"], "Sum of the three longest queue delays within the last window of arrivals.")]),
}
