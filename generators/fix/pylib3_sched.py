"""Scheduling in domain clothes (python, fix-py-3): tournament pools and brackets, a film-crew planner, dock labour leveling."""
from fx import Lib, dd

from generators.fix._pylib3 import chain, register_libs3

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# cupdraw: seeding and draws for a club tournament
# ======================================================================================================================

CUPDRAW_README = dd('''
    # cupdraw

    Seeding helpers for a regional club tournament. Teams are identified by their name and a list of teams is always
    *best seed first*.

    ## Pools

    * `pool_sizes(n, pools) -> list[int]`: split `n` teams into `pools` pools as evenly as possible; the larger pools
      come first (`pool_sizes(10, 3) == [4, 3, 3]`). `ValueError` if `n < 0` or `pools < 1`.
    * `snake_pools(seeds, pools) -> list[list]`: deal the seeds out in a serpentine: the first `pools` seeds go to pools
      `0 .. pools-1`, the next `pools` seeds go to pools `pools-1 .. 0`, then forwards again, and so on. Every pool
      keeps its teams in the order they were dealt. `ValueError` if `pools < 1`.
    * `fix_clashes(pools, club_of) -> (pools, unresolved)`: teams of the same club should not meet in a pool.
      `club_of` maps a team to its club. Work on a copy: for each pool `p` in order and each position `j` in it, if
      the team there has the club of a team at an earlier position of the same pool, look for a swap partner: scan
      the pools after `p` in order and, inside each, the teams from the **last position to the first**; the first
      team `u` such that after exchanging the two teams neither pool has that clash qualifies, that is `club(u)` is
      not among the clubs of the rest of pool `p` and the club of the moved team is not among the clubs of the rest of
      `u`'s pool. Exchange them (each keeps the other's position). A team without a partner is added to
      `unresolved` (in the order met) and left where it is. Returns the new pools and the unresolved list.

    ## Knockout

    * `bracket_size(n) -> int`: the smallest power of two that is `>= n` (`ValueError` for `n < 1`; `bracket_size(1)`
      is `1`). `byes(n) -> int`: `bracket_size(n) - n`.
    * `first_round(n) -> list[(int, int | None)]`: for seeds `1..n` in a bracket of size `m = bracket_size(n)`: the
      pairs `(i, m + 1 - i)` for `i = 1 .. m // 2`; a seed above `n` does not exist and is written `None` (so the
      real seed has a bye). `first_round(1)` is `[]`.
    * `next_round(entrants) -> list[(entrant, entrant | None)]`: the draw is redone every round: with the surviving
      entrants listed best seed first, pair the best with the worst, the second best with the second worst, and so on.
      With an odd number the middle entrant is paired with `None` (a bye). Fewer than 2 entrants give `[]`.
''')

CUPDRAW_SRC = dd('''
    """Seeding and draws."""


    def pool_sizes(n, pools):
        if n < 0 or pools < 1:
            raise ValueError("need n >= 0 and pools >= 1")
        base, extra = divmod(n, pools)
        return [base + (1 if i < extra else 0) for i in range(pools)]


    def snake_pools(seeds, pools):
        if pools < 1:
            raise ValueError("pools must be at least 1")
        out = [[] for _ in range(pools)]
        for i, team in enumerate(seeds):
            row, col = divmod(i, pools)
            out[col if row % 2 == 0 else pools - 1 - col].append(team)
        return out


    def fix_clashes(pools, club_of):
        pools = [list(p) for p in pools]
        unresolved = []
        for p in range(len(pools)):
            for j in range(len(pools[p])):
                team = pools[p][j]
                if club_of[team] not in {club_of[x] for x in pools[p][:j]}:
                    continue
                done = False
                for q in range(p + 1, len(pools)):
                    for k in range(len(pools[q]) - 1, -1, -1):
                        other = pools[q][k]
                        rest_p = {club_of[x] for x in pools[p] if x != team}
                        rest_q = {club_of[x] for x in pools[q] if x != other}
                        if club_of[other] not in rest_p and club_of[team] not in rest_q:
                            pools[p][j], pools[q][k] = other, team
                            done = True
                            break
                    if done:
                        break
                if not done:
                    unresolved.append(team)
        return pools, unresolved


    def bracket_size(n):
        if n < 1:
            raise ValueError("need at least one entrant")
        size = 1
        while size < n:
            size *= 2
        return size


    def byes(n):
        return bracket_size(n) - n


    def first_round(n):
        m = bracket_size(n)
        pairs = []
        for i in range(1, m // 2 + 1):
            other = m + 1 - i
            pairs.append((i, other if other <= n else None))
        return pairs


    def next_round(entrants):
        entrants = list(entrants)
        pairs = []
        lo, hi = 0, len(entrants) - 1
        while lo < hi:
            pairs.append((entrants[lo], entrants[hi]))
            lo, hi = lo + 1, hi - 1
        if lo == hi:
            pairs.append((entrants[lo], None))
        return pairs if len(entrants) >= 2 else []
''')

CUPDRAW_VISIBLE = dd('''
    import unittest

    from cupdraw.draw import bracket_size, pool_sizes, snake_pools


    class BasicTests(unittest.TestCase):
        def test_sizes(self):
            self.assertEqual(pool_sizes(10, 3), [4, 3, 3])

        def test_snake(self):
            self.assertEqual(snake_pools(["a", "b", "c", "d"], 2), [["a", "d"], ["b", "c"]])

        def test_bracket(self):
            self.assertEqual(bracket_size(5), 8)


    if __name__ == "__main__":
        unittest.main()
''')

CUPDRAW_HIDDEN = dd('''
    import unittest

    from cupdraw.draw import bracket_size, byes, first_round, fix_clashes, next_round, pool_sizes, snake_pools


    class Sizes(unittest.TestCase):
        def test_pool_sizes(self):
            self.assertEqual(pool_sizes(10, 3), [4, 3, 3])
            self.assertEqual(pool_sizes(9, 3), [3, 3, 3])
            self.assertEqual(pool_sizes(11, 3), [4, 4, 3])
            self.assertEqual(pool_sizes(2, 4), [1, 1, 0, 0])
            self.assertEqual(pool_sizes(0, 3), [0, 0, 0])
            self.assertEqual(pool_sizes(7, 1), [7])
            self.assertEqual(pool_sizes(13, 5), [3, 3, 3, 2, 2])

        def test_pool_sizes_errors(self):
            for args in ((-1, 3), (5, 0), (5, -2)):
                with self.assertRaises(ValueError):
                    pool_sizes(*args)

        def test_bracket_size(self):
            table = {1: 1, 2: 2, 3: 4, 4: 4, 5: 8, 8: 8, 9: 16, 16: 16, 17: 32, 100: 128}
            for n, want in table.items():
                self.assertEqual(bracket_size(n), want, n)
                self.assertEqual(byes(n), want - n, n)
            for n in (0, -3):
                with self.assertRaises(ValueError):
                    bracket_size(n)
                with self.assertRaises(ValueError):
                    byes(n)


    class Snake(unittest.TestCase):
        def test_even(self):
            seeds = list("ABCDEFGH")
            self.assertEqual(snake_pools(seeds, 2), [["A", "D", "E", "H"], ["B", "C", "F", "G"]])
            self.assertEqual(snake_pools(seeds, 4), [["A", "H"], ["B", "G"], ["C", "F"], ["D", "E"]])

        def test_uneven(self):
            self.assertEqual(snake_pools(list("ABCDEFG"), 3), [["A", "F", "G"], ["B", "E"], ["C", "D"]])
            self.assertEqual(snake_pools(list("ABCDEFGH"), 3), [["A", "F", "G"], ["B", "E", "H"], ["C", "D"]])
            self.assertEqual(snake_pools(list("ABCDEFGHI"), 3), [["A", "F", "G"], ["B", "E", "H"], ["C", "D", "I"]])
            self.assertEqual(snake_pools(list("ABCDEFGHIJ"), 3), [["A", "F", "G"], ["B", "E", "H"], ["C", "D", "I", "J"]])

        def test_edges(self):
            self.assertEqual(snake_pools([], 3), [[], [], []])
            self.assertEqual(snake_pools(["A"], 3), [["A"], [], []])
            self.assertEqual(snake_pools(["A", "B", "C"], 1), [["A", "B", "C"]])
            self.assertEqual(snake_pools(["A", "B"], 5), [["A"], ["B"], [], [], []])
            with self.assertRaises(ValueError):
                snake_pools(["A"], 0)

        def test_sizes_agree_with_pool_sizes(self):
            for n in range(0, 20):
                for pools in range(1, 6):
                    got = [len(p) for p in snake_pools(list(range(n)), pools)]
                    self.assertEqual(sorted(got, reverse=True), pool_sizes(n, pools))


    class Clashes(unittest.TestCase):
        def test_simple_swap(self):
            clubs = {"A": "x", "B": "y", "C": "z", "D": "w", "E": "z", "F": "x"}
            pools = snake_pools(list("ABCDEF"), 3)
            self.assertEqual(pools, [["A", "F"], ["B", "E"], ["C", "D"]])
            fixed, unresolved = fix_clashes(pools, clubs)
            self.assertEqual(fixed, [["A", "E"], ["B", "F"], ["C", "D"]])
            self.assertEqual(unresolved, [])
            self.assertEqual(pools, [["A", "F"], ["B", "E"], ["C", "D"]])    # the input is not modified

        def test_partner_is_searched_from_the_last_position(self):
            clubs = {"A": "x", "B": "x", "C": "p", "D": "q", "E": "r"}
            fixed, unresolved = fix_clashes([["A", "B"], ["C", "D", "E"]], clubs)
            self.assertEqual(fixed, [["A", "E"], ["C", "D", "B"]])
            self.assertEqual(unresolved, [])

        def test_partner_pool_must_not_have_the_clashing_club(self):
            # pools 1 holds a team of club x, so nobody from there can take B's place; pool 2 is clean
            clubs = {"A": "x", "B": "x", "C": "y", "D": "z", "E": "x", "G": "w"}
            fixed, unresolved = fix_clashes([["A", "B"], ["C", "D", "E"], ["G"]], clubs)
            self.assertEqual(fixed, [["A", "G"], ["C", "D", "E"], ["B"]])
            self.assertEqual(unresolved, [])

        def test_partner_must_not_clash_with_the_rest_of_the_pool(self):
            # C (club y) would sit next to D (club y) in pool 0
            clubs = {"A": "x", "B": "x", "D": "y", "C": "y"}
            fixed, unresolved = fix_clashes([["A", "B", "D"], ["C"]], clubs)
            self.assertEqual(fixed, [["A", "B", "D"], ["C"]])
            self.assertEqual(unresolved, ["B"])

        def test_destination_pool_clash_blocks_the_swap(self):
            clubs = {"A": "x", "B": "x", "C": "x", "D": "y"}
            fixed, unresolved = fix_clashes([["A", "B"], ["C", "D"]], clubs)
            self.assertEqual(fixed, [["A", "B"], ["C", "D"]])
            self.assertEqual(unresolved, ["B"])

        def test_later_pools_in_order(self):
            clubs = {"A": "x", "B": "x", "C": "y", "D": "z"}
            fixed, unresolved = fix_clashes([["A", "B"], ["C"], ["D"]], clubs)
            self.assertEqual(fixed, [["A", "C"], ["B"], ["D"]])

        def test_unresolved(self):
            clubs = {"A": "x", "B": "x", "C": "x", "D": "x"}
            fixed, unresolved = fix_clashes([["A", "B"], ["C", "D"]], clubs)
            self.assertEqual(fixed, [["A", "B"], ["C", "D"]])
            self.assertEqual(unresolved, ["B", "D"])

        def test_no_clash_no_change(self):
            clubs = {"A": "x", "B": "y", "C": "x", "D": "y"}
            pools = [["A", "B"], ["C", "D"]]
            fixed, unresolved = fix_clashes(pools, clubs)
            self.assertEqual((fixed, unresolved), (pools, []))
            self.assertIsNot(fixed, pools)
            self.assertIsNot(fixed[0], pools[0])

        def test_earlier_pools_are_never_touched_after_their_turn(self):
            clubs = {"A": "x", "B": "y", "C": "x", "D": "y", "E": "z", "F": "z"}
            fixed, unresolved = fix_clashes([["A", "B"], ["C", "D"], ["E", "F"]], clubs)
            self.assertEqual(fixed, [["A", "B"], ["C", "D"], ["E", "F"]])
            self.assertEqual(unresolved, ["F"])


    class Knockout(unittest.TestCase):
        def test_first_round(self):
            self.assertEqual(first_round(8), [(1, 8), (2, 7), (3, 6), (4, 5)])
            self.assertEqual(first_round(5), [(1, None), (2, None), (3, None), (4, 5)])
            self.assertEqual(first_round(6), [(1, None), (2, None), (3, 6), (4, 5)])
            self.assertEqual(first_round(2), [(1, 2)])
            self.assertEqual(first_round(3), [(1, None), (2, 3)])
            self.assertEqual(first_round(1), [])
            self.assertEqual(first_round(9)[0], (1, None))
            self.assertEqual(len(first_round(9)), 8)
            self.assertEqual(first_round(9)[-1], (8, 9))

        def test_first_round_errors(self):
            with self.assertRaises(ValueError):
                first_round(0)

        def test_next_round(self):
            self.assertEqual(next_round(["a", "b", "c", "d"]), [("a", "d"), ("b", "c")])
            self.assertEqual(next_round(["a", "b", "c", "d", "e"]), [("a", "e"), ("b", "d"), ("c", None)])
            self.assertEqual(next_round(["a", "b"]), [("a", "b")])
            self.assertEqual(next_round(["a", "b", "c"]), [("a", "c"), ("b", None)])
            self.assertEqual(next_round(list(range(1, 7))), [(1, 6), (2, 5), (3, 4)])
            self.assertEqual(next_round(["a"]), [])
            self.assertEqual(next_round([]), [])
            self.assertEqual(next_round(("x", "y")), [("x", "y")])


    if __name__ == "__main__":
        unittest.main()
''')

CUPDRAW = Lib(
    name="cupdraw", lang="python", title="the cupdraw tournament helpers (`cupdraw/draw.py`)",
    blurb="The club league's website uses cupdraw to deal teams into pools and to build the knockout draw.",
    files={"cupdraw/__init__.py": "", "cupdraw/draw.py": CUPDRAW_SRC, "README.md": CUPDRAW_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": CUPDRAW_VISIBLE},
    hidden_tests={"tests/test_full.py": CUPDRAW_HIDDEN},
    mutate=["cupdraw/draw.py"], difficulty=2, tags=["tournament", "seeding"],
    probes=[
        "pool_sizes(11, 3)", "pool_sizes(2, 4)", "bracket_size(9)", "byes(5)",
        "snake_pools(list('ABCDEFGH'), 3)", "snake_pools(list('ABCDEFGHIJ'), 3)",
        "first_round(5)", "first_round(9)[-1]", "first_round(3)",
        "next_round(['a', 'b', 'c', 'd', 'e'])", "next_round(['a', 'b'])",
        "fix_clashes([['A', 'F'], ['B', 'E'], ['C', 'D']], {'A': 'x', 'B': 'y', 'C': 'z', 'D': 'w', 'E': 'z', 'F': 'x'})",
        "fix_clashes([['A', 'B'], ['C', 'D', 'E']], {'A': 'x', 'B': 'x', 'C': 'p', 'D': 'q', 'E': 'r'})",
        "fix_clashes([['A', 'B'], ['C', 'D']], {'A': 'x', 'B': 'x', 'C': 'x', 'D': 'x'})",
    ],
    probe_import="from cupdraw.draw import pool_sizes, snake_pools, fix_clashes, bracket_size, byes, first_round, next_round\n",
)

# ======================================================================================================================
# crewplan: job scheduling with dependencies for a film crew (multi-module)
# ======================================================================================================================

CREWPLAN_README = dd('''
    # crewplan

    Planning the shoot of a short film: jobs have a duration (whole days) and may depend on other jobs.

    ## `crewplan.jobs`

    `Job(name, duration, deps)` is a frozen dataclass; `deps` is a tuple of job names.

    `parse_jobs(text) -> list[Job]`: one job per line, `name duration` or `name duration after dep1,dep2` (the
    dependencies are comma separated without spaces). Names consist of lower-case letters, digits and `-`; the
    duration is a whole number of at least 1. Everything after `#` is a comment and blank lines are skipped. Jobs
    keep the order of the lines. Problems are a `ValueError` starting with `line N:` (N counts physical lines from 1):
    a wrong number of words (a line must have 2 words, or 4 when the third is `after`), a bad name, a bad duration,
    a duplicate job name, an empty dependency list or a dependency that is not a valid name. Dependencies on unknown
    jobs are not detected by the parser.

    ## `crewplan.analysis`

    All functions take a list of `Job`s.

    * `topo_order(jobs) -> list[str]`: job names such that every job follows its dependencies. Among the jobs that are
      ready, the one with the smallest name always goes first. `ValueError("unknown job: X")`-style errors: a job that
      depends on an unknown job raises `ValueError` whose message is `"<job> depends on unknown job <dep>"` (the
      first such job in list order and its first unknown dependency in the order given). A dependency cycle raises
      `ValueError` with the message `"cycle among: "` followed by the sorted names that could not be ordered
      (jobs on a cycle and jobs that depend on one), joined by `", "`.
    * `earliest(jobs) -> dict`: `name -> (start, finish)` with unlimited workers: a job starts when its last
      dependency finishes (day 0 if it has none) and runs `duration` days.
    * `makespan(jobs) -> int`: the largest finish (`0` for no jobs).
    * `latest(jobs) -> dict`: `name -> (late_start, late_finish)`: the latest times that do not delay the makespan:
      a job's `late_finish` is the smallest `late_start` of the jobs that depend on it (the makespan if nothing
      depends on it) and `late_start = late_finish - duration`.
    * `slack(jobs) -> dict`: `late_start - start` per job. `critical_jobs(jobs) -> list[str]`: the jobs with zero
      slack, ordered by earliest start and then by name.

    ## `crewplan.schedule`

    * `priority(jobs) -> dict`: the length of the longest chain of durations that starts with the job and follows
      its dependents (`duration` plus the largest priority among its dependents, or just `duration`).
    * `list_schedule(jobs, workers) -> list[(name, worker, start, finish)]` for `workers >= 1` (`ValueError`
      otherwise) workers numbered from 0. Time advances from day 0. At every time `t` that is day 0 or the finish time
      of some running job: the jobs that are ready (every dependency has finished, `finish <= t`) and not yet started
      are sorted by descending `priority`, then by name; the workers that are idle at `t` are taken in ascending
      number; the best ready job gets the first idle worker, the next job the next idle worker, until one of the two
      runs out. A started job runs `duration` days without interruption. The result is sorted by `(start, worker)`.
      Errors of `topo_order` (unknown jobs, cycles) are raised before scheduling.
    * `finish_time(schedule) -> int`: the largest finish (`0` when empty).
    * `gantt(schedule, workers) -> str`: one line per worker `w<number> | ` followed by that worker's entries
      `name@start-finish` separated by single spaces in start order, or `-` for a worker without any job; lines are
      joined with `"\\n"`.
''')

CREWPLAN_JOBS = dd('''
    """Jobs and their text format."""
    import re
    from dataclasses import dataclass

    _NAME = re.compile(r"^[a-z0-9-]+$")


    @dataclass(frozen=True)
    class Job:
        name: str
        duration: int
        deps: tuple = ()


    def parse_jobs(text):
        jobs, seen = [], set()
        for lineno, raw in enumerate(text.splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            words = line.split()
            if len(words) not in (2, 4) or (len(words) == 4 and words[2] != "after"):
                raise ValueError(f"line {lineno}: expected 'name duration' or 'name duration after a,b'")
            name = words[0]
            if not _NAME.match(name):
                raise ValueError(f"line {lineno}: bad job name {name!r}")
            if name in seen:
                raise ValueError(f"line {lineno}: duplicate job {name!r}")
            if not words[1].isdigit() or int(words[1]) < 1:
                raise ValueError(f"line {lineno}: duration must be a whole number of at least 1")
            deps = ()
            if len(words) == 4:
                deps = tuple(words[3].split(","))
                if not all(_NAME.match(d) for d in deps):
                    raise ValueError(f"line {lineno}: bad dependency list {words[3]!r}")
            seen.add(name)
            jobs.append(Job(name, int(words[1]), deps))
        return jobs
''')

CREWPLAN_ANALYSIS = dd('''
    """Critical-path analysis with unlimited workers."""
    import heapq


    def topo_order(jobs):
        names = {j.name for j in jobs}
        for job in jobs:
            for dep in job.deps:
                if dep not in names:
                    raise ValueError(f"{job.name} depends on unknown job {dep}")
        waiting = {j.name: len(set(j.deps)) for j in jobs}
        dependents = {j.name: [] for j in jobs}
        for job in jobs:
            for dep in set(job.deps):
                dependents[dep].append(job.name)
        heap = [n for n, k in waiting.items() if k == 0]
        heapq.heapify(heap)
        order = []
        while heap:
            name = heapq.heappop(heap)
            order.append(name)
            for nxt in dependents[name]:
                waiting[nxt] -= 1
                if waiting[nxt] == 0:
                    heapq.heappush(heap, nxt)
        if len(order) < len(jobs):
            stuck = sorted(names - set(order))
            raise ValueError("cycle among: " + ", ".join(stuck))
        return order


    def earliest(jobs):
        by_name = {j.name: j for j in jobs}
        times = {}
        for name in topo_order(jobs):
            job = by_name[name]
            start = max((times[d][1] for d in job.deps), default=0)
            times[name] = (start, start + job.duration)
        return times


    def makespan(jobs):
        return max((finish for _, finish in earliest(jobs).values()), default=0)


    def latest(jobs):
        by_name = {j.name: j for j in jobs}
        end = makespan(jobs)
        late = {}
        for name in reversed(topo_order(jobs)):
            finish = min((late[j.name][0] for j in jobs if name in j.deps), default=end)
            late[name] = (finish - by_name[name].duration, finish)
        return late


    def slack(jobs):
        early, late = earliest(jobs), latest(jobs)
        return {name: late[name][0] - early[name][0] for name in early}


    def critical_jobs(jobs):
        early, spare = earliest(jobs), slack(jobs)
        return sorted((n for n, s in spare.items() if s == 0), key=lambda n: (early[n][0], n))
''')

CREWPLAN_SCHEDULE = dd('''
    """List scheduling on a fixed number of workers."""
    from .analysis import topo_order


    def priority(jobs):
        by_name = {j.name: j for j in jobs}
        prio = {}
        for name in reversed(topo_order(jobs)):
            tail = max((prio[j.name] for j in jobs if name in j.deps), default=0)
            prio[name] = by_name[name].duration + tail
        return prio


    def list_schedule(jobs, workers):
        if workers < 1:
            raise ValueError("need at least one worker")
        topo_order(jobs)
        prio = priority(jobs)
        by_name = {j.name: j for j in jobs}
        finished = {}
        busy_until = [0] * workers
        plan = []
        t = 0
        while len(plan) < len(jobs):
            ready = sorted(
                (n for n in by_name if n not in finished and all(d in finished and finished[d] <= t for d in by_name[n].deps)),
                key=lambda n: (-prio[n], n),
            )
            idle = [w for w in range(workers) if busy_until[w] <= t]
            for name, w in zip(ready, idle):
                finished[name] = t + by_name[name].duration
                busy_until[w] = finished[name]
                plan.append((name, w, t, finished[name]))
            if len(plan) < len(jobs):
                t = min(f for f in finished.values() if f > t)
        return sorted(plan, key=lambda e: (e[2], e[1]))


    def finish_time(schedule):
        return max((e[3] for e in schedule), default=0)


    def gantt(schedule, workers):
        lines = []
        for w in range(workers):
            mine = sorted((e for e in schedule if e[1] == w), key=lambda e: e[2])
            body = " ".join(f"{name}@{start}-{finish}" for name, _, start, finish in mine) or "-"
            lines.append(f"w{w} | {body}")
        return "\\n".join(lines)
''')

CREWPLAN_VISIBLE = dd('''
    import unittest

    from crewplan.analysis import makespan, topo_order
    from crewplan.jobs import parse_jobs

    TEXT = """
    script 3
    sets 4 after script
    props 2 after script
    shoot 5 after sets,props
    """


    class BasicTests(unittest.TestCase):
        def test_order(self):
            self.assertEqual(topo_order(parse_jobs(TEXT)), ["script", "props", "sets", "shoot"])

        def test_makespan(self):
            self.assertEqual(makespan(parse_jobs(TEXT)), 12)


    if __name__ == "__main__":
        unittest.main()
''')

CREWPLAN_HIDDEN_JOBS = dd('''
    import unittest

    from crewplan.jobs import Job, parse_jobs


    class Parse(unittest.TestCase):
        def test_forms(self):
            text = "a 3\\nb 2 after a\\nc 4 after a,b\\n"
            self.assertEqual(parse_jobs(text), [Job("a", 3, ()), Job("b", 2, ("a",)), Job("c", 4, ("a", "b"))])

        def test_comments_blank_lines_and_order(self):
            text = "# plan\\n\\n  z-9   1  # last alphabetically, first listed\\nb 2 after z-9   # note\\n"
            self.assertEqual(parse_jobs(text), [Job("z-9", 1), Job("b", 2, ("z-9",))])

        def test_empty(self):
            self.assertEqual(parse_jobs(""), [])
            self.assertEqual(parse_jobs("# nothing\\n\\n"), [])

        def test_job_defaults(self):
            self.assertEqual(Job("a", 1).deps, ())
            with self.assertRaises(Exception):
                Job("a", 1).duration = 2

        def test_dependencies_on_unknown_jobs_are_not_checked_here(self):
            self.assertEqual(parse_jobs("a 1 after ghost"), [Job("a", 1, ("ghost",))])
            self.assertEqual(parse_jobs("a 1 after a"), [Job("a", 1, ("a",))])
            self.assertEqual(parse_jobs("a 1 after b\\nb 1"), [Job("a", 1, ("b",)), Job("b", 1, ())])

        def test_errors_with_line_numbers(self):
            bad = [
                "a", "a 1 2", "a 1 after", "a 1 before b", "a 1 after b c", "A 1", "a_b 1", "a 0", "a -1", "a x", "a 1.5",
                "a 1 after b,,c", "a 1 after ,b", "a 1 after B", "a 1 after b,", "a 2 after a,B", " 5",
            ]
            for text in bad:
                with self.assertRaises(ValueError, msg=text) as cm:
                    parse_jobs("# first\\nok 1\\n" + text)
                self.assertTrue(str(cm.exception).startswith("line 3:"), (text, str(cm.exception)))

        def test_duplicate(self):
            with self.assertRaises(ValueError) as cm:
                parse_jobs("a 1\\nb 1\\n\\na 2")
            self.assertTrue(str(cm.exception).startswith("line 4:"))


    if __name__ == "__main__":
        unittest.main()
''')

CREWPLAN_HIDDEN_ANALYSIS = dd('''
    import unittest

    from crewplan.analysis import critical_jobs, earliest, latest, makespan, slack, topo_order
    from crewplan.jobs import Job, parse_jobs

    DEMO = parse_jobs("""
    a 3
    b 2 after a
    c 4 after a
    d 1 after b,c
    e 5
    """)


    class Order(unittest.TestCase):
        def test_ties_go_to_the_smallest_name(self):
            self.assertEqual(topo_order(DEMO), ["a", "b", "c", "d", "e"])
            jobs = [Job("m", 1), Job("b", 1), Job("z", 1), Job("a", 1, ("z",))]
            self.assertEqual(topo_order(jobs), ["b", "m", "z", "a"])

        def test_dependencies_first(self):
            jobs = [Job("x", 1, ("y",)), Job("y", 1, ("z",)), Job("z", 1)]
            self.assertEqual(topo_order(jobs), ["z", "y", "x"])

        def test_duplicate_deps_count_once(self):
            jobs = [Job("a", 1), Job("b", 1, ("a", "a"))]
            self.assertEqual(topo_order(jobs), ["a", "b"])

        def test_empty(self):
            self.assertEqual(topo_order([]), [])
            self.assertEqual(earliest([]), {})
            self.assertEqual(makespan([]), 0)
            self.assertEqual(latest([]), {})
            self.assertEqual(critical_jobs([]), [])

        def test_unknown_dependency(self):
            jobs = [Job("a", 1), Job("b", 1, ("a", "nope", "zzz")), Job("c", 1, ("ghost",))]
            with self.assertRaises(ValueError) as cm:
                topo_order(jobs)
            self.assertEqual(str(cm.exception), "b depends on unknown job nope")

        def test_cycle(self):
            jobs = [Job("a", 1), Job("b", 1, ("c",)), Job("c", 1, ("b",)), Job("d", 1, ("c",))]
            with self.assertRaises(ValueError) as cm:
                topo_order(jobs)
            self.assertEqual(str(cm.exception), "cycle among: b, c, d")
            with self.assertRaises(ValueError) as cm:
                topo_order([Job("x", 1, ("x",))])
            self.assertEqual(str(cm.exception), "cycle among: x")


    class Times(unittest.TestCase):
        def test_earliest(self):
            self.assertEqual(earliest(DEMO), {"a": (0, 3), "b": (3, 5), "c": (3, 7), "d": (7, 8), "e": (0, 5)})
            self.assertEqual(makespan(DEMO), 8)

        def test_latest(self):
            self.assertEqual(latest(DEMO), {"a": (0, 3), "b": (5, 7), "c": (3, 7), "d": (7, 8), "e": (3, 8)})

        def test_slack_and_critical(self):
            self.assertEqual(slack(DEMO), {"a": 0, "b": 2, "c": 0, "d": 0, "e": 3})
            self.assertEqual(critical_jobs(DEMO), ["a", "c", "d"])

        def test_chain(self):
            jobs = [Job("c", 2, ("b",)), Job("b", 3, ("a",)), Job("a", 1)]
            self.assertEqual(earliest(jobs), {"a": (0, 1), "b": (1, 4), "c": (4, 6)})
            self.assertEqual(critical_jobs(jobs), ["a", "b", "c"])
            self.assertEqual(makespan(jobs), 6)

        def test_parallel_independent_jobs(self):
            jobs = [Job("x", 4), Job("y", 4), Job("z", 2)]
            self.assertEqual(makespan(jobs), 4)
            self.assertEqual(slack(jobs), {"x": 0, "y": 0, "z": 2})
            self.assertEqual(critical_jobs(jobs), ["x", "y"])
            self.assertEqual(latest(jobs)["z"], (2, 4))

        def test_late_finish_is_the_minimum_over_dependents(self):
            jobs = [Job("a", 1), Job("b", 5, ("a",)), Job("c", 1, ("a",)), Job("d", 1, ("c",))]
            self.assertEqual(latest(jobs)["a"], (0, 1))
            self.assertEqual(latest(jobs)["c"], (4, 5))
            self.assertEqual(latest(jobs)["d"], (5, 6))
            self.assertEqual(slack(jobs), {"a": 0, "b": 0, "c": 3, "d": 3})

        def test_critical_ordering(self):
            jobs = [Job("b", 2), Job("a", 2), Job("c", 2, ("a", "b"))]
            self.assertEqual(critical_jobs(jobs), ["a", "b", "c"])

        def test_input_order_does_not_matter(self):
            self.assertEqual(earliest(DEMO[::-1]), earliest(DEMO))
            self.assertEqual(latest(DEMO[::-1]), latest(DEMO))
            self.assertEqual(topo_order(DEMO[::-1]), topo_order(DEMO))


    if __name__ == "__main__":
        unittest.main()
''')

CREWPLAN_HIDDEN_SCHEDULE = dd('''
    import unittest

    from crewplan.analysis import topo_order
    from crewplan.jobs import Job, parse_jobs
    from crewplan.schedule import finish_time, gantt, list_schedule, priority

    DEMO = parse_jobs("""
    a 3
    b 2 after a
    c 4 after a
    d 1 after b,c
    e 5
    """)


    class Priority(unittest.TestCase):
        def test_values(self):
            self.assertEqual(priority(DEMO), {"a": 8, "b": 3, "c": 5, "d": 1, "e": 5})
            self.assertEqual(priority([]), {})
            self.assertEqual(priority([Job("x", 7)]), {"x": 7})


    class Schedule(unittest.TestCase):
        def test_two_workers(self):
            got = list_schedule(DEMO, 2)
            self.assertEqual(got, [("a", 0, 0, 3), ("e", 1, 0, 5), ("c", 0, 3, 7), ("b", 1, 5, 7), ("d", 0, 7, 8)])
            self.assertEqual(finish_time(got), 8)

        def test_one_worker(self):
            got = list_schedule(DEMO, 1)
            self.assertEqual(got, [("a", 0, 0, 3), ("c", 0, 3, 7), ("e", 0, 7, 12), ("b", 0, 12, 14), ("d", 0, 14, 15)])
            self.assertEqual(finish_time(got), 15)

        def test_three_workers(self):
            got = list_schedule(DEMO, 3)
            self.assertEqual(got, [("a", 0, 0, 3), ("e", 1, 0, 5), ("c", 0, 3, 7), ("b", 2, 3, 5), ("d", 0, 7, 8)])

        def test_many_workers_match_unlimited(self):
            got = list_schedule(DEMO, 10)
            self.assertEqual(finish_time(got), 8)
            self.assertEqual([e[1] for e in got if e[2] == 0], [0, 1])

        def test_priority_then_name_decides_who_goes_first(self):
            jobs = [Job("z", 2), Job("m", 2), Job("a", 1), Job("long", 6)]
            got = list_schedule(jobs, 2)
            self.assertEqual(got, [("long", 0, 0, 6), ("m", 1, 0, 2), ("z", 1, 2, 4), ("a", 1, 4, 5)])

        def test_job_waits_for_its_slowest_dependency(self):
            jobs = [Job("p", 2), Job("q", 6), Job("r", 1, ("p", "q"))]
            got = list_schedule(jobs, 3)
            self.assertEqual(got, [("q", 0, 0, 6), ("p", 1, 0, 2), ("r", 0, 6, 7)])

        def test_dependency_finishing_exactly_at_t_counts(self):
            jobs = [Job("a", 3), Job("b", 1, ("a",))]
            self.assertEqual(list_schedule(jobs, 1), [("a", 0, 0, 3), ("b", 0, 3, 4)])

        def test_idle_gap_is_skipped(self):
            jobs = [Job("a", 5), Job("b", 1), Job("c", 1, ("b",)), Job("d", 3, ("a",))]
            got = list_schedule(jobs, 2)
            self.assertEqual(got, [("a", 0, 0, 5), ("b", 1, 0, 1), ("c", 1, 1, 2), ("d", 0, 5, 8)])

        def test_empty_and_errors(self):
            self.assertEqual(list_schedule([], 2), [])
            self.assertEqual(finish_time([]), 0)
            with self.assertRaises(ValueError):
                list_schedule(DEMO, 0)
            with self.assertRaises(ValueError):
                list_schedule(DEMO, -1)
            with self.assertRaises(ValueError) as cm:
                list_schedule([Job("a", 1, ("b",)), Job("b", 1, ("a",))], 2)
            self.assertEqual(str(cm.exception), "cycle among: a, b")
            with self.assertRaises(ValueError) as cm:
                list_schedule([Job("a", 1, ("zz",))], 2)
            self.assertEqual(str(cm.exception), "a depends on unknown job zz")

        def test_no_overlaps_and_dependencies_respected(self):
            jobs = parse_jobs("""
            a 2
            b 3
            c 1 after a
            d 4 after a,b
            e 2 after c
            f 1 after d,e
            g 3
            """)
            for workers in (1, 2, 3, 4):
                plan = list_schedule(jobs, workers)
                self.assertEqual(sorted(e[0] for e in plan), sorted(j.name for j in jobs))
                by_name = {e[0]: e for e in plan}
                for job in jobs:
                    name, w, start, finish = by_name[job.name]
                    self.assertEqual(finish - start, job.duration)
                    self.assertTrue(0 <= w < workers)
                    for dep in job.deps:
                        self.assertLessEqual(by_name[dep][3], start)
                for w in range(workers):
                    mine = sorted((e for e in plan if e[1] == w), key=lambda e: e[2])
                    for first, second in zip(mine, mine[1:]):
                        self.assertLessEqual(first[3], second[2])
            self.assertEqual(finish_time(list_schedule(jobs, 4)), 8)


    class Gantt(unittest.TestCase):
        def test_gantt(self):
            got = gantt(list_schedule(DEMO, 2), 2)
            self.assertEqual(got, "w0 | a@0-3 c@3-7 d@7-8\\nw1 | e@0-5 b@5-7")

        def test_idle_worker(self):
            got = gantt(list_schedule([Job("only", 2)], 3), 3)
            self.assertEqual(got, "w0 | only@0-2\\nw1 | -\\nw2 | -")

        def test_entries_in_start_order(self):
            sched = [("late", 0, 5, 6), ("early", 0, 0, 5)]
            self.assertEqual(gantt(sched, 1), "w0 | early@0-5 late@5-6")

        def test_empty(self):
            self.assertEqual(gantt([], 2), "w0 | -\\nw1 | -")


    if __name__ == "__main__":
        unittest.main()
''')

_CP = "'a 3\\nb 2 after a\\nc 4 after a\\nd 1 after b,c\\ne 5'"

CREWPLAN = Lib(
    name="crewplan", lang="python", title="the crewplan shoot scheduler",
    blurb="The production office uses crewplan to find the critical path of a shoot and to roster crew members onto jobs.",
    files={
        "crewplan/__init__.py": "", "crewplan/jobs.py": CREWPLAN_JOBS, "crewplan/analysis.py": CREWPLAN_ANALYSIS,
        "crewplan/schedule.py": CREWPLAN_SCHEDULE, "README.md": CREWPLAN_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": CREWPLAN_VISIBLE},
    hidden_tests={
        "tests/test_jobs.py": CREWPLAN_HIDDEN_JOBS, "tests/test_analysis.py": CREWPLAN_HIDDEN_ANALYSIS,
        "tests/test_schedule.py": CREWPLAN_HIDDEN_SCHEDULE,
    },
    mutate=["crewplan/jobs.py", "crewplan/analysis.py", "crewplan/schedule.py"],
    difficulty=4, tags=["scheduling", "critical-path", "multi-module"],
    probes=[
        f"parse_jobs({_CP})[2]", "parse_jobs('a 0')", "parse_jobs('a 1\\nb 1 after a,,c')",
        f"topo_order(parse_jobs({_CP}))", f"earliest(parse_jobs({_CP}))", f"latest(parse_jobs({_CP}))",
        f"slack(parse_jobs({_CP}))", f"critical_jobs(parse_jobs({_CP}))",
        "topo_order([Job('a', 1), Job('b', 1, ('c',)), Job('c', 1, ('b',)), Job('d', 1, ('c',))])",
        f"priority(parse_jobs({_CP}))",
        f"list_schedule(parse_jobs({_CP}), 2)", f"list_schedule(parse_jobs({_CP}), 1)", f"list_schedule(parse_jobs({_CP}), 3)",
        f"gantt(list_schedule(parse_jobs({_CP}), 2), 2)",
        "list_schedule([Job('z', 2), Job('m', 2), Job('a', 1), Job('long', 6)], 2)",
        "list_schedule([Job('p', 2), Job('q', 6), Job('r', 1, ('p', 'q'))], 3)",
        "finish_time(list_schedule([Job('a', 5), Job('b', 1), Job('c', 1, ('b',)), Job('d', 3, ('a',))], 2))",
    ],
    probe_import=(
        "from crewplan.jobs import Job, parse_jobs\nfrom crewplan.analysis import topo_order, earliest, latest, slack, critical_jobs, makespan\n"
        "from crewplan.schedule import priority, list_schedule, finish_time, gantt\n"
    ),
)

# ======================================================================================================================
# docklevel: leveling dock labour demand
# ======================================================================================================================

DOCKLEVEL_README = dd('''
    # docklevel

    Leveling the labour demand of a dock: every task needs some workers on each of its days, and may be started on any
    day inside a window. The planner shifts tasks to avoid peaks. Days are whole numbers from 0.

    ## `Task(name, duration, demand, earliest, latest)`

    A frozen dataclass: the task occupies the `duration` consecutive days `start .. start + duration - 1` and needs
    `demand` workers on each of them; `start` must lie in `earliest .. latest` (both inclusive).

    ## `level(tasks, capacity) -> dict`

    Returns `{name: start}`. Validation first: `ValueError` for a `duration` or `demand` below 1, `earliest` below 0,
    `latest < earliest`, a duplicate name or `capacity < 1`. The tasks are then placed one at a time in the order of
    `(latest - earliest, earliest, name)` ascending (least flexible first). For a task every start day in its window
    is tried in ascending order and gets the *peak* it would create: the largest current load on any of its days plus
    its demand. The start with the smallest peak is chosen; on a tie the earlier start wins. If the chosen peak is
    above `capacity` the whole call raises `ValueError` (the message names the task). Otherwise the task's demand is
    added to the load of each of its days.

    ## `profile(tasks, plan) -> list[int]`

    The load of every day from day 0 up to the last busy day (inclusive) for the given plan; an empty plan gives `[]`.
    Days without work show `0`.

    ## `peak(tasks, plan) -> int` and `utilisation(tasks, plan, capacity) -> int`

    `peak` is the largest value of the profile (`0` for an empty plan). `utilisation` is the total worker-days
    (the sum of the profile) as a percentage of `capacity * len(profile)`, rounded half up to a whole number
    (`0` for an empty plan).
''')

DOCKLEVEL_SRC = dd('''
    """Greedy resource leveling."""
    from dataclasses import dataclass


    @dataclass(frozen=True)
    class Task:
        name: str
        duration: int
        demand: int
        earliest: int
        latest: int


    def _validate(tasks, capacity):
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        seen = set()
        for t in tasks:
            if t.duration < 1 or t.demand < 1 or t.earliest < 0 or t.latest < t.earliest:
                raise ValueError(f"bad task {t.name!r}")
            if t.name in seen:
                raise ValueError(f"duplicate task {t.name!r}")
            seen.add(t.name)


    def level(tasks, capacity):
        _validate(tasks, capacity)
        load = {}
        plan = {}
        for t in sorted(tasks, key=lambda t: (t.latest - t.earliest, t.earliest, t.name)):
            best_peak, best_start = None, None
            for start in range(t.earliest, t.latest + 1):
                peak = max(load.get(d, 0) for d in range(start, start + t.duration)) + t.demand
                if best_peak is None or peak < best_peak:
                    best_peak, best_start = peak, start
            if best_peak > capacity:
                raise ValueError(f"cannot place {t.name} within capacity {capacity}")
            for d in range(best_start, best_start + t.duration):
                load[d] = load.get(d, 0) + t.demand
            plan[t.name] = best_start
        return plan


    def profile(tasks, plan):
        load = {}
        for t in tasks:
            if t.name in plan:
                for d in range(plan[t.name], plan[t.name] + t.duration):
                    load[d] = load.get(d, 0) + t.demand
        if not load:
            return []
        return [load.get(d, 0) for d in range(max(load) + 1)]


    def peak(tasks, plan):
        return max(profile(tasks, plan), default=0)


    def utilisation(tasks, plan, capacity):
        days = profile(tasks, plan)
        if not days:
            return 0
        return (200 * sum(days) + capacity * len(days)) // (2 * capacity * len(days))
''')

DOCKLEVEL_VISIBLE = dd('''
    import unittest

    from docklevel.level import Task, level, peak


    class BasicTests(unittest.TestCase):
        def test_single_task(self):
            tasks = [Task("unload", 2, 3, 1, 1)]
            self.assertEqual(level(tasks, 5), {"unload": 1})
            self.assertEqual(peak(tasks, {"unload": 1}), 3)


    if __name__ == "__main__":
        unittest.main()
''')

DOCKLEVEL_HIDDEN = dd('''
    import unittest

    from docklevel.level import Task, level, peak, profile, utilisation


    def T(name, duration, demand, earliest, latest):
        return Task(name, duration, demand, earliest, latest)


    class Placement(unittest.TestCase):
        def test_flexible_tasks_dodge_the_fixed_one(self):
            tasks = [T("T3", 1, 3, 0, 4), T("T2", 2, 3, 0, 3), T("T1", 2, 4, 0, 0)]
            plan = level(tasks, 6)
            self.assertEqual(plan, {"T1": 0, "T2": 2, "T3": 4})
            self.assertEqual(profile(tasks, plan), [4, 4, 3, 3, 3])
            self.assertEqual(peak(tasks, plan), 4)

        def test_capacity_is_enforced(self):
            tasks = [T("T1", 2, 4, 0, 0), T("T2", 2, 3, 0, 3), T("T3", 1, 3, 0, 3)]
            with self.assertRaises(ValueError) as cm:
                level(tasks, 5)
            self.assertIn("T3", str(cm.exception))
            plan = level(tasks, 6)
            self.assertEqual(plan, {"T1": 0, "T2": 2, "T3": 2})
            self.assertEqual(peak(tasks, plan), 6)

        def test_exact_capacity_is_fine(self):
            tasks = [T("a", 1, 5, 0, 0), T("b", 1, 5, 1, 1)]
            self.assertEqual(level(tasks, 5), {"a": 0, "b": 1})
            with self.assertRaises(ValueError):
                level(tasks, 4)

        def test_tie_goes_to_the_earlier_start(self):
            self.assertEqual(level([T("a", 1, 2, 3, 9)], 5), {"a": 3})
            self.assertEqual(level([T("a", 2, 1, 0, 5)], 5), {"a": 0})

        def test_least_flexible_first(self):
            tasks = [T("loose", 1, 2, 0, 5), T("tight", 1, 2, 0, 0)]
            plan = level(tasks, 3)
            self.assertEqual(plan, {"tight": 0, "loose": 1})

        def test_order_ties_use_earliest_then_name(self):
            tasks = [T("b", 1, 2, 1, 2), T("a", 1, 2, 1, 2), T("c", 1, 2, 0, 1)]
            plan = level(tasks, 2)
            # flexibility is 1 for all: c (earliest 0) first -> day 0; then a -> day 1 (day 0 is taken), then b -> day 2
            self.assertEqual(plan, {"c": 0, "a": 1, "b": 2})

        def test_peak_is_computed_over_the_whole_span(self):
            tasks = [T("base", 1, 4, 2, 2), T("long", 3, 2, 0, 1)]
            plan = level(tasks, 8)
            # long at 0 covers days 0-2 (day 2 has load 4 -> peak 6); at 1 covers 1-3 (peak 6): tie -> earlier
            self.assertEqual(plan["long"], 0)
            tasks = [T("base", 1, 4, 3, 3), T("long", 3, 2, 0, 1)]
            plan = level(tasks, 8)
            self.assertEqual(plan["long"], 0)
            tasks = [T("base", 1, 4, 1, 1), T("long", 3, 2, 0, 2)]
            plan = level(tasks, 8)
            self.assertEqual(plan["long"], 2)

        def test_window_edges(self):
            plan = level([T("a", 1, 1, 4, 4), T("b", 3, 1, 2, 6)], 3)
            self.assertEqual(plan, {"a": 4, "b": 5})
            blocker = T("blocker", 5, 3, 0, 0)
            self.assertEqual(level([blocker, T("x", 1, 2, 0, 5)], 4)["x"], 5)       # the last allowed day counts
            with self.assertRaises(ValueError):
                level([blocker, T("x", 1, 2, 0, 4)], 4)
            self.assertEqual(level([blocker, T("x", 1, 1, 0, 4)], 4)["x"], 0)       # peak 4 is exactly the capacity

        def test_no_tasks(self):
            self.assertEqual(level([], 3), {})

        def test_validation(self):
            bad = [T("a", 0, 1, 0, 0), T("a", 1, 0, 0, 0), T("a", 1, 1, -1, 0), T("a", 1, 1, 3, 2)]
            for t in bad:
                with self.assertRaises(ValueError):
                    level([t], 5)
            with self.assertRaises(ValueError):
                level([T("a", 1, 1, 0, 0), T("a", 1, 1, 1, 1)], 5)
            with self.assertRaises(ValueError):
                level([T("a", 1, 1, 0, 0)], 0)
            level([T("a", 1, 1, 0, 0)], 1)

        def test_validation_happens_before_placement(self):
            with self.assertRaises(ValueError):
                level([T("a", 1, 1, 0, 0), T("b", 0, 1, 0, 0)], 5)


    class Reports(unittest.TestCase):
        def test_profile(self):
            tasks = [T("a", 2, 3, 0, 0), T("b", 1, 2, 4, 4)]
            plan = {"a": 0, "b": 4}
            self.assertEqual(profile(tasks, plan), [3, 3, 0, 0, 2])
            self.assertEqual(peak(tasks, plan), 3)
            self.assertEqual(profile(tasks, {}), [])
            self.assertEqual(profile([], {}), [])
            self.assertEqual(peak(tasks, {}), 0)

        def test_profile_sums_overlaps_and_starts_at_zero(self):
            tasks = [T("a", 3, 2, 0, 5), T("b", 2, 1, 0, 5)]
            self.assertEqual(profile(tasks, {"a": 2, "b": 3}), [0, 0, 2, 3, 3])
            self.assertEqual(profile(tasks, {"a": 2}), [0, 0, 2, 2, 2])

        def test_utilisation(self):
            tasks = [T("a", 2, 3, 0, 0), T("b", 1, 2, 4, 4)]
            plan = {"a": 0, "b": 4}
            # worker-days 3 + 3 + 2 = 8 over 5 days at capacity 4: 8 / 20 = 40 %
            self.assertEqual(utilisation(tasks, plan, 4), 40)
            self.assertEqual(utilisation(tasks, plan, 3), 53)       # 8 / 15 = 53.33
            self.assertEqual(utilisation(tasks, plan, 5), 32)       # 8 / 25
            self.assertEqual(utilisation(tasks, {}, 4), 0)
            one = [T("a", 1, 1, 0, 0)]
            self.assertEqual(utilisation(one, {"a": 0}, 2), 50)
            self.assertEqual(utilisation(one, {"a": 0}, 3), 33)
            self.assertEqual(utilisation([T("a", 1, 1, 0, 0)], {"a": 0}, 8), 13)   # 12.5 rounds up
            self.assertEqual(utilisation([T("a", 1, 1, 0, 0)], {"a": 0}, 200), 1)  # 0.5 rounds up
            self.assertEqual(utilisation([T("a", 1, 1, 0, 0)], {"a": 0}, 201), 0)


    if __name__ == "__main__":
        unittest.main()
''')

DOCKLEVEL = Lib(
    name="docklevel", lang="python", title="the docklevel labour leveling package (`docklevel/level.py`)",
    blurb="The dock's shift planner uses docklevel to move flexible unloading jobs around so that the labour demand stays under the crew size.",
    files={"docklevel/__init__.py": "", "docklevel/level.py": DOCKLEVEL_SRC, "README.md": DOCKLEVEL_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": DOCKLEVEL_VISIBLE},
    hidden_tests={"tests/test_full.py": DOCKLEVEL_HIDDEN},
    mutate=["docklevel/level.py"], difficulty=3, tags=["leveling", "resources"],
    probes=[
        "level([Task('T3', 1, 3, 0, 4), Task('T2', 2, 3, 0, 3), Task('T1', 2, 4, 0, 0)], 6)",
        "level([Task('loose', 1, 2, 0, 5), Task('tight', 1, 2, 0, 0)], 3)",
        "level([Task('b', 1, 2, 1, 2), Task('a', 1, 2, 1, 2), Task('c', 1, 2, 0, 1)], 2)",
        "level([Task('blocker', 5, 3, 0, 0), Task('x', 1, 2, 0, 6)], 4)",
        "level([Task('a', 2, 1, 0, 5)], 5)",
        "level([Task('a', 1, 5, 0, 0), Task('b', 1, 5, 1, 1)], 5)",
        "profile([Task('a', 3, 2, 0, 5), Task('b', 2, 1, 0, 5)], {'a': 2, 'b': 3})",
        "peak([Task('a', 2, 3, 0, 0), Task('b', 1, 2, 4, 4)], {'a': 0, 'b': 4})",
        "utilisation([Task('a', 2, 3, 0, 0), Task('b', 1, 2, 4, 4)], {'a': 0, 'b': 4}, 3)",
        "utilisation([Task('a', 1, 1, 0, 0)], {'a': 0}, 8)",
        "level([Task('a', 1, 1, 0, 0), Task('b', 0, 1, 0, 0)], 5)",
    ],
    probe_import="from docklevel.level import Task, level, profile, peak, utilisation\n",
)

LIBS = [CUPDRAW, CREWPLAN, DOCKLEVEL]
register_libs3(LIBS, n=10)
