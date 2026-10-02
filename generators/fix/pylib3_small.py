"""Small algorithmic helpers in domain clothes (python, fix-py-3): duty rota, degree-days, committee votes, swim heats, bar cutting."""
from fx import Lib, dd

from generators.fix._pylib3 import chain, register_libs3

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# rotapick: a fair duty rota with a rotating pointer
# ======================================================================================================================

ROTAPICK_README = dd('''
    # rotapick

    Picks who is on duty for a hut-warden rota. People take turns in a fixed order; somebody who is away is skipped but
    is *owed* a turn, which they get as soon as they are around again.

    ## `Roster(people)`

    `people` is a non-empty list of distinct, non-empty names (`ValueError` otherwise). The roster keeps its own copy as
    `people`, `pos`, the index of the person the pointer is on (starting at 0), and `owed`, a dict with a counter for every person (all 0).

    * `pick(unavailable=()) -> str | None`: choose who is on duty today. Names in `unavailable` that are not on the
      roster are ignored.
      1. Look at everybody in *circular order starting at `pos`*. If nobody is available return `None` and change nothing.
      2. If some available person is owed a turn (`owed > 0`), the one who is owed the most is chosen (when several are
         owed the same, the first of them in circular order). Their `owed` goes down by one. The pointer does not
         move.
      3. Otherwise walk through the circular order from `pos`: every unavailable person passed gets `owed + 1`; the first
         available person is chosen and the pointer moves to the person after them (`pos = index + 1`, wrapping around).
''')

ROTAPICK_SRC = dd('''
    """A rotating duty rota."""


    class Roster:
        def __init__(self, people):
            people = list(people)
            if not people or len(set(people)) != len(people) or any(not p for p in people):
                raise ValueError("people must be distinct and non-empty")
            self.people = people
            self.pos = 0
            self.owed = {p: 0 for p in people}

        def _circular(self):
            n = len(self.people)
            return [self.people[(self.pos + i) % n] for i in range(n)]

        def pick(self, unavailable=()):
            away = set(unavailable)
            order = self._circular()
            free = [p for p in order if p not in away]
            if not free:
                return None
            owing = [p for p in free if self.owed[p] > 0]
            if owing:
                chosen = max(owing, key=lambda p: self.owed[p])
                self.owed[chosen] -= 1
                return chosen
            chosen = None
            for p in order:
                if p in away:
                    self.owed[p] += 1
                else:
                    chosen = p
                    break
            self.pos = (self.people.index(chosen) + 1) % len(self.people)
            return chosen
''')

ROTAPICK_VISIBLE = dd('''
    import unittest

    from rotapick.rota import Roster


    class BasicTests(unittest.TestCase):
        def test_round_robin(self):
            r = Roster(["a", "b", "c"])
            self.assertEqual([r.pick() for _ in range(4)], ["a", "b", "c", "a"])


    if __name__ == "__main__":
        unittest.main()
''')

ROTAPICK_HIDDEN = dd('''
    import unittest

    from rotapick.rota import Roster


    class Construction(unittest.TestCase):
        def test_valid(self):
            r = Roster(("a", "b"))
            self.assertEqual((r.people, r.pos, r.owed), (["a", "b"], 0, {"a": 0, "b": 0}))

        def test_invalid(self):
            for people in ([], ["a", "a"], ["a", ""], [""]):
                with self.assertRaises(ValueError, msg=str(people)):
                    Roster(people)

        def test_input_is_copied(self):
            people = ["a", "b"]
            r = Roster(people)
            people.append("c")
            self.assertEqual(r.people, ["a", "b"])


    class RoundRobin(unittest.TestCase):
        def test_plain_rotation(self):
            r = Roster(["a", "b", "c", "d"])
            got = [r.pick() for _ in range(9)]
            self.assertEqual(got, ["a", "b", "c", "d", "a", "b", "c", "d", "a"])
            self.assertEqual(r.pos, 1)

        def test_single_person(self):
            r = Roster(["solo"])
            self.assertEqual([r.pick() for _ in range(3)], ["solo", "solo", "solo"])
            self.assertEqual(r.pos, 0)
            self.assertIsNone(r.pick({"solo"}))


    class Skipping(unittest.TestCase):
        def test_walkthrough(self):
            r = Roster(["a", "b", "c", "d"])
            self.assertEqual(r.pick(), "a")
            self.assertEqual(r.pick({"b"}), "c")
            self.assertEqual((r.pos, r.owed["b"]), (3, 1))
            self.assertEqual(r.pick(), "b")            # owed a turn: it comes before d
            self.assertEqual((r.pos, r.owed["b"]), (3, 0))
            self.assertEqual(r.pick(), "d")
            self.assertEqual(r.pos, 0)
            self.assertEqual(r.pick(), "a")

        def test_every_skipped_person_is_owed(self):
            r = Roster(["a", "b", "c", "d"])
            self.assertEqual(r.pick({"a", "b"}), "c")
            self.assertEqual(r.owed, {"a": 1, "b": 1, "c": 0, "d": 0})
            self.assertEqual(r.pos, 3)

        def test_owed_turn_requires_availability(self):
            r = Roster(["a", "b", "c", "d"])
            r.pick({"a", "b"})                      # c on duty; a and b owed; pos 3
            self.assertEqual(r.pick({"a"}), "b")    # a is away again: b collects its turn
            self.assertEqual(r.owed, {"a": 1, "b": 0, "c": 0, "d": 0})
            self.assertEqual(r.pos, 3)
            self.assertEqual(r.pick(), "a")
            self.assertEqual(r.owed["a"], 0)
            self.assertEqual(r.pick(), "d")

        def test_ties_in_owed_follow_the_circular_order_from_pos(self):
            r = Roster(["a", "b", "c", "d"])
            r.pick({"a", "b"})                      # pos 3, a and b owed one each
            self.assertEqual(r.pick(), "a")         # circular from d: d, a, b, c -> a is first among the owing
            self.assertEqual(r.pick(), "b")

        def test_pointer_scan_only_owes_the_people_it_passes(self):
            r = Roster(["a", "b", "c"])
            self.assertEqual(r.pick({"a"}), "b")
            self.assertEqual(r.pick({"a"}), "c")      # the scan starts at c: a is not passed this time
            self.assertEqual(r.owed["a"], 1)

        def test_collecting_an_owed_turn_leaves_the_others_owed(self):
            r = Roster(["a", "b", "c"])
            self.assertEqual(r.pick({"a", "b"}), "c")
            self.assertEqual(r.pick({"b", "c"}), "a")
            self.assertEqual(r.owed, {"a": 0, "b": 1, "c": 0})
            self.assertEqual(r.pos, 0)

        def test_most_owed_goes_first(self):
            r = Roster(["a", "b", "c", "d"])
            r.owed.update({"a": 1, "c": 3, "d": 2})
            got = [r.pick() for _ in range(6)]
            # c (3 owed) first; then c and d are both owed 2 and c comes first in circular order; then d; then a, c, d
            self.assertEqual(got, ["c", "c", "d", "a", "c", "d"])
            self.assertEqual(r.owed, {"a": 0, "b": 0, "c": 0, "d": 0})
            self.assertEqual(r.pos, 0)
            self.assertEqual(r.pick(), "a")
            self.assertEqual(r.pos, 1)

        def test_everybody_away(self):
            r = Roster(["a", "b", "c"])
            r.pick()
            before = (r.pos, dict(r.owed))
            self.assertIsNone(r.pick({"a", "b", "c"}))
            self.assertIsNone(r.pick(["a", "b", "c", "zed"]))
            self.assertEqual((r.pos, r.owed), before)

        def test_unknown_names_are_ignored(self):
            r = Roster(["a", "b"])
            self.assertEqual(r.pick({"zed", "yan"}), "a")
            self.assertEqual(r.owed, {"a": 0, "b": 0})

        def test_unavailable_may_be_any_iterable(self):
            r = Roster(["a", "b", "c"])
            self.assertEqual(r.pick(["a"]), "b")
            self.assertEqual(r.pick(iter(["c"])), "a")

        def test_pointer_wraps(self):
            r = Roster(["a", "b", "c"])
            r.pick()
            r.pick()
            self.assertEqual(r.pick(), "c")
            self.assertEqual(r.pos, 0)
            self.assertEqual(r.pick({"a"}), "b")
            self.assertEqual(r.pos, 2)
            self.assertEqual(r.owed["a"], 1)


    if __name__ == "__main__":
        unittest.main()
''')

ROTAPICK = Lib(
    name="rotapick", lang="python", title="the rotapick duty rota (`rotapick/rota.py`)",
    blurb="The hut wardens' scheduling script uses rotapick to decide who is on duty each day while keeping the rota fair when people are away.",
    files={"rotapick/__init__.py": "", "rotapick/rota.py": ROTAPICK_SRC, "README.md": ROTAPICK_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": ROTAPICK_VISIBLE},
    hidden_tests={"tests/test_full.py": ROTAPICK_HIDDEN},
    mutate=["rotapick/rota.py"], difficulty=1, tags=["roster", "fairness"],
    probes=[
        chain("Roster(['a', 'b', 'c', 'd'])", ["pick()", "pick({'b'})", "pick()", "pick()", "pos", "owed"]),
        chain("Roster(['a', 'b', 'c', 'd'])", ["pick({'a', 'b'})", "owed", "pos"]),
        chain("Roster(['a', 'b', 'c', 'd'])", ["pick({'a', 'b'})", "pick({'a'})", "owed", "pick()", "pick()"]),
        chain("Roster(['a', 'b', 'c', 'd'])", ["pick({'a', 'b'})", "pick()", "pick()"]),
        "(lambda r: (r.owed.update({'a': 1, 'c': 3, 'd': 2}), r.pick(), r.owed)[1:])(Roster(['a', 'b', 'c', 'd']))",
        chain("Roster(['a', 'b', 'c'])", ["pick()", "pick()", "pick()", "pos", "pick({'a'})", "pos", "owed"]),
        chain("Roster(['a', 'b'])", ["pick({'a', 'b'})", "pos", "owed"]),
        "Roster(['a', 'a'])",
    ],
    probe_import="from rotapick.rota import Roster\n",
)

# ======================================================================================================================
# degreedays: growing-degree-day tracking
# ======================================================================================================================

DEGREEDAYS_README = dd('''
    # degreedays

    Growing-degree-day bookkeeping for a market garden: plants move through stages once enough warmth has accumulated.
    Temperatures are in degrees Celsius (integers or `Fraction`s); results are exact `fractions.Fraction`s.

    * `daily_gdd(tmin, tmax, base=10, cap=30) -> Fraction`: the warmth of one day. Each of the two temperatures is first
      clamped into `[base, cap]` (a value below `base` counts as `base`, one above `cap` as `cap`); the day's value is
      the mean of the two clamped temperatures minus `base`. `ValueError` if `tmin > tmax` or `cap <= base`.
    * `accumulate(days, base=10, cap=30) -> list[Fraction]`: `days` is a list of `(tmin, tmax)`; the result holds the
      running total after each day.
    * `stage_of(total, stages) -> str | None`: `stages` is a list of `(name, threshold)` with strictly increasing
      thresholds (`ValueError` for an empty list or thresholds that do not strictly increase). The stage is the name of
      the last entry whose threshold is `<= total`, or `None` when the total is below the first threshold.
    * `days_to_reach(total, target, per_day) -> int`: how many more days at `per_day` degree-days a day are needed to get
      from `total` to at least `target`: `0` if `total >= target`, otherwise the smallest whole number of days.
      `ValueError` if `per_day <= 0`.
''')

DEGREEDAYS_SRC = dd('''
    """Growing degree days."""
    from fractions import Fraction


    def daily_gdd(tmin, tmax, base=10, cap=30):
        if tmin > tmax or cap <= base:
            raise ValueError("need tmin <= tmax and cap > base")
        lo = min(max(tmin, base), cap)
        hi = min(max(tmax, base), cap)
        return Fraction(lo + hi, 2) - base


    def accumulate(days, base=10, cap=30):
        total = Fraction(0)
        out = []
        for tmin, tmax in days:
            total += daily_gdd(tmin, tmax, base, cap)
            out.append(total)
        return out


    def stage_of(total, stages):
        if not stages or any(b[1] <= a[1] for a, b in zip(stages, stages[1:])):
            raise ValueError("stages need strictly increasing thresholds")
        current = None
        for name, threshold in stages:
            if total >= threshold:
                current = name
        return current


    def days_to_reach(total, target, per_day):
        if per_day <= 0:
            raise ValueError("per_day must be positive")
        if total >= target:
            return 0
        return -(-(Fraction(target) - total) // Fraction(per_day))
''')

DEGREEDAYS_VISIBLE = dd('''
    import unittest
    from fractions import Fraction as F

    from degreedays.gdd import daily_gdd


    class BasicTests(unittest.TestCase):
        def test_simple_day(self):
            self.assertEqual(daily_gdd(12, 20), F(6))


    if __name__ == "__main__":
        unittest.main()
''')

DEGREEDAYS_HIDDEN = dd('''
    import unittest
    from fractions import Fraction as F

    from degreedays.gdd import accumulate, daily_gdd, days_to_reach, stage_of


    class Daily(unittest.TestCase):
        def test_clamping(self):
            self.assertEqual(daily_gdd(4, 18), 4)           # 4 counts as 10: (10 + 18) / 2 - 10
            self.assertEqual(daily_gdd(12, 36), 11)         # 36 counts as 30: (12 + 30) / 2 - 10
            self.assertEqual(daily_gdd(0, 5), 0)
            self.assertEqual(daily_gdd(22, 22), 12)
            self.assertEqual(daily_gdd(50, 60), 20)
            self.assertEqual(daily_gdd(10, 10), 0)
            self.assertEqual(daily_gdd(30, 30), 20)
            self.assertEqual(daily_gdd(-5, 40), 10)

        def test_fractions(self):
            self.assertEqual(daily_gdd(11, 14), F(5, 2))
            self.assertEqual(daily_gdd(F(21, 2), F(25, 2)), F(3, 2))
            self.assertIsInstance(daily_gdd(12, 20), F)

        def test_custom_base_and_cap(self):
            self.assertEqual(daily_gdd(10, 20, base=5, cap=25), 10)
            self.assertEqual(daily_gdd(0, 40, base=5, cap=25), 10)
            self.assertEqual(daily_gdd(8, 9, base=8, cap=9), F(1, 2))
            self.assertEqual(daily_gdd(14, 16, 12, 14), 2)

        def test_errors(self):
            with self.assertRaises(ValueError):
                daily_gdd(20, 10)
            with self.assertRaises(ValueError):
                daily_gdd(10, 20, base=20, cap=20)
            with self.assertRaises(ValueError):
                daily_gdd(10, 20, base=20, cap=15)
            daily_gdd(15, 15)


    class Accumulate(unittest.TestCase):
        def test_running_totals(self):
            self.assertEqual(accumulate([(4, 18), (12, 36), (0, 5)]), [4, 15, 15])
            self.assertEqual(accumulate([]), [])
            self.assertEqual(accumulate([(11, 14)] * 3), [F(5, 2), F(5), F(15, 2)])

        def test_parameters(self):
            self.assertEqual(accumulate([(10, 20), (0, 40)], base=5, cap=25), [10, 20])

        def test_errors_propagate(self):
            with self.assertRaises(ValueError):
                accumulate([(10, 20), (20, 10)])


    class Stages(unittest.TestCase):
        STAGES = [("emerge", 50), ("flower", 300), ("fruit", 800)]

        def test_lookup(self):
            self.assertIsNone(stage_of(0, self.STAGES))
            self.assertIsNone(stage_of(F(99, 2), self.STAGES))
            self.assertEqual(stage_of(50, self.STAGES), "emerge")
            self.assertEqual(stage_of(299, self.STAGES), "emerge")
            self.assertEqual(stage_of(300, self.STAGES), "flower")
            self.assertEqual(stage_of(799, self.STAGES), "flower")
            self.assertEqual(stage_of(800, self.STAGES), "fruit")
            self.assertEqual(stage_of(5000, self.STAGES), "fruit")

        def test_single_stage(self):
            self.assertEqual(stage_of(5, [("only", 5)]), "only")
            self.assertIsNone(stage_of(4, [("only", 5)]))

        def test_thresholds_may_be_zero_or_negative(self):
            self.assertEqual(stage_of(0, [("seed", 0), ("leaf", 10)]), "seed")
            self.assertEqual(stage_of(-1, [("cold", -5), ("seed", 0)]), "cold")

        def test_bad_stages(self):
            for stages in ([], [("a", 5), ("b", 5)], [("a", 5), ("b", 3)], [("a", 1), ("b", 2), ("c", 2)], [("a", 1), ("b", 5), ("c", 4)]):
                with self.assertRaises(ValueError, msg=str(stages)):
                    stage_of(10, stages)


    class Forecast(unittest.TestCase):
        def test_days(self):
            self.assertEqual(days_to_reach(0, 100, 30), 4)
            self.assertEqual(days_to_reach(0, 90, 30), 3)
            self.assertEqual(days_to_reach(70, 100, 30), 1)
            self.assertEqual(days_to_reach(70, 100, 31), 1)
            self.assertEqual(days_to_reach(70, 101, 30), 2)
            self.assertEqual(days_to_reach(F(5, 2), 10, F(5, 2)), 3)
            self.assertEqual(days_to_reach(0, 1, 100), 1)
            self.assertEqual(days_to_reach(10, 100, F(1, 3)), 270)

        def test_already_there(self):
            self.assertEqual(days_to_reach(100, 100, 5), 0)
            self.assertEqual(days_to_reach(150, 100, 5), 0)
            self.assertEqual(days_to_reach(0, 0, 5), 0)

        def test_errors(self):
            for per_day in (0, -1, F(-1, 2)):
                with self.assertRaises(ValueError):
                    days_to_reach(0, 10, per_day)
            with self.assertRaises(ValueError):
                days_to_reach(100, 10, 0)


    if __name__ == "__main__":
        unittest.main()
''')

DEGREEDAYS = Lib(
    name="degreedays", lang="python", title="the degreedays tracker (`degreedays/gdd.py`)",
    blurb="The market garden's planner uses degreedays to follow crop development from daily minimum and maximum temperatures.",
    files={"degreedays/__init__.py": "", "degreedays/gdd.py": DEGREEDAYS_SRC, "README.md": DEGREEDAYS_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": DEGREEDAYS_VISIBLE},
    hidden_tests={"tests/test_full.py": DEGREEDAYS_HIDDEN},
    mutate=["degreedays/gdd.py"], difficulty=1, tags=["agriculture", "thresholds"],
    probes=[
        "daily_gdd(4, 18)", "daily_gdd(12, 36)", "daily_gdd(50, 60)", "daily_gdd(11, 14)", "daily_gdd(10, 20, base=5, cap=25)",
        "accumulate([(4, 18), (12, 36), (0, 5)])", "accumulate([(11, 14)] * 3)",
        "stage_of(299, [('emerge', 50), ('flower', 300), ('fruit', 800)])", "stage_of(300, [('emerge', 50), ('flower', 300), ('fruit', 800)])",
        "stage_of(49, [('emerge', 50), ('flower', 300)])", "stage_of(10, [('a', 5), ('b', 5)])",
        "days_to_reach(0, 100, 30)", "days_to_reach(70, 100, 30)", "days_to_reach(100, 100, 5)", "days_to_reach(0, 10, 0)",
    ],
    probe_import="from fractions import Fraction\nfrom degreedays.gdd import daily_gdd, accumulate, stage_of, days_to_reach\n",
)

# ======================================================================================================================
# quorumcheck: committee quorum and voting rules
# ======================================================================================================================

QUORUMCHECK_README = dd('''
    # quorumcheck

    Committee rules for a village hall association: how many members must be present, and when does a motion pass?

    ## `quorum(members, rule="majority") -> int`

    The number of members that must take part: `"majority"` is `members // 2 + 1`, `"third"` is one third rounded up,
    `"two-thirds"` is two thirds rounded up and `"all"` is every member. `ValueError` for `members < 1` or any other rule.

    ## `decide(yes, no, abstain, members, quorum_rule="majority", pass_rule="simple") -> str`

    `ValueError` if a count is negative, `yes + no + abstain > members`, `members < 1`, or a rule name is unknown (the
    names are checked before anything else). Everyone who voted yes, no or abstained is *present*. The outcome is:

    * `"no quorum"` when fewer members are present than `quorum(members, quorum_rule)`; otherwise by the pass rule:
    * `"simple"`: `"passed"` if `yes > no`, `"failed"` if `yes < no`, `"tied"` if they are equal (abstentions are ignored);
    * `"absolute"`: `"passed"` if `yes` is more than half of **all** members (`yes > members // 2`), else `"failed"`;
    * `"two-thirds"`: `"passed"` if `yes > 0` and `yes` is at least two thirds of the yes and no votes together
      (`3 * yes >= 2 * (yes + no)`), else `"failed"`;
    * `"unanimous"`: `"passed"` if `yes > 0` and `no == 0`, else `"failed"`.
''')

QUORUMCHECK_SRC = dd('''
    """Quorum and voting rules."""

    PASS_RULES = ("simple", "absolute", "two-thirds", "unanimous")


    def quorum(members, rule="majority"):
        if members < 1:
            raise ValueError("members must be at least 1")
        if rule == "majority":
            return members // 2 + 1
        if rule == "third":
            return -(-members // 3)
        if rule == "two-thirds":
            return -(-2 * members // 3)
        if rule == "all":
            return members
        raise ValueError(f"unknown quorum rule {rule!r}")


    def decide(yes, no, abstain, members, quorum_rule="majority", pass_rule="simple"):
        needed = quorum(members, quorum_rule)
        if pass_rule not in PASS_RULES:
            raise ValueError(f"unknown pass rule {pass_rule!r}")
        if min(yes, no, abstain) < 0 or yes + no + abstain > members:
            raise ValueError("impossible vote counts")
        if yes + no + abstain < needed:
            return "no quorum"
        if pass_rule == "simple":
            if yes == no:
                return "tied"
            return "passed" if yes > no else "failed"
        if pass_rule == "absolute":
            return "passed" if yes > members // 2 else "failed"
        if pass_rule == "two-thirds":
            return "passed" if yes > 0 and 3 * yes >= 2 * (yes + no) else "failed"
        return "passed" if yes > 0 and no == 0 else "failed"
''')

QUORUMCHECK_VISIBLE = dd('''
    import unittest

    from quorumcheck.rules import decide, quorum


    class BasicTests(unittest.TestCase):
        def test_quorum(self):
            self.assertEqual(quorum(9), 5)

        def test_simple_vote(self):
            self.assertEqual(decide(4, 1, 0, 9), "passed")


    if __name__ == "__main__":
        unittest.main()
''')

QUORUMCHECK_HIDDEN = dd('''
    import unittest

    from quorumcheck.rules import decide, quorum


    class Quorum(unittest.TestCase):
        def test_majority(self):
            self.assertEqual([quorum(n) for n in (1, 2, 3, 4, 5, 10, 11)], [1, 2, 2, 3, 3, 6, 6])
            self.assertEqual(quorum(7, "majority"), 4)

        def test_third(self):
            self.assertEqual([quorum(n, "third") for n in (1, 2, 3, 4, 6, 7, 9, 10)], [1, 1, 1, 2, 2, 3, 3, 4])

        def test_two_thirds(self):
            self.assertEqual([quorum(n, "two-thirds") for n in (1, 2, 3, 4, 5, 6, 9, 10)], [1, 2, 2, 3, 4, 4, 6, 7])

        def test_all(self):
            self.assertEqual([quorum(n, "all") for n in (1, 5, 12)], [1, 5, 12])

        def test_errors(self):
            for args in ((0,), (-3,), (5, "half"), (5, ""), (5, "Majority")):
                with self.assertRaises(ValueError, msg=str(args)):
                    quorum(*args)


    class Simple(unittest.TestCase):
        def test_outcomes(self):
            self.assertEqual(decide(3, 1, 1, 9), "passed")
            self.assertEqual(decide(1, 3, 1, 9), "failed")
            self.assertEqual(decide(2, 2, 1, 9), "tied")
            self.assertEqual(decide(0, 0, 5, 9), "tied")
            self.assertEqual(decide(5, 0, 0, 9), "passed")
            self.assertEqual(decide(0, 5, 0, 9), "failed")

        def test_abstentions_do_not_count_against(self):
            self.assertEqual(decide(2, 1, 6, 9), "passed")

        def test_quorum_first(self):
            self.assertEqual(decide(3, 1, 0, 9), "no quorum")       # 4 present, 5 needed
            self.assertEqual(decide(3, 1, 1, 9), "passed")
            self.assertEqual(decide(0, 0, 0, 9), "no quorum")
            self.assertEqual(decide(0, 0, 0, 1, "third"), "no quorum")
            self.assertEqual(decide(1, 0, 0, 1), "passed")

        def test_other_quorum_rules(self):
            self.assertEqual(decide(2, 0, 0, 9, "third"), "no quorum")
            self.assertEqual(decide(3, 0, 0, 9, "third"), "passed")
            self.assertEqual(decide(5, 0, 0, 9, "two-thirds"), "no quorum")
            self.assertEqual(decide(6, 0, 0, 9, "two-thirds"), "passed")
            self.assertEqual(decide(8, 0, 0, 9, "all"), "no quorum")
            self.assertEqual(decide(9, 0, 0, 9, "all"), "passed")
            self.assertEqual(decide(5, 0, 0, 10, "majority"), "no quorum")
            self.assertEqual(decide(6, 0, 0, 10, "majority"), "passed")


    class Absolute(unittest.TestCase):
        def test_more_than_half_of_all_members(self):
            self.assertEqual(decide(5, 0, 0, 9, pass_rule="absolute"), "passed")
            self.assertEqual(decide(4, 0, 1, 9, pass_rule="absolute"), "failed")
            self.assertEqual(decide(5, 4, 0, 9, pass_rule="absolute"), "passed")
            self.assertEqual(decide(5, 0, 0, 8, "third", "absolute"), "passed")
            self.assertEqual(decide(4, 0, 0, 8, "third", "absolute"), "failed")
            self.assertEqual(decide(1, 0, 0, 1, pass_rule="absolute"), "passed")
            self.assertEqual(decide(1, 1, 0, 2, pass_rule="absolute"), "failed")


    class TwoThirds(unittest.TestCase):
        def test_threshold(self):
            self.assertEqual(decide(6, 3, 0, 9, pass_rule="two-thirds"), "passed")      # exactly two thirds
            self.assertEqual(decide(5, 3, 0, 9, pass_rule="two-thirds"), "failed")
            self.assertEqual(decide(4, 2, 3, 9, pass_rule="two-thirds"), "passed")      # abstentions are ignored
            self.assertEqual(decide(7, 1, 1, 9, pass_rule="two-thirds"), "passed")
            self.assertEqual(decide(2, 1, 6, 9, pass_rule="two-thirds"), "passed")
            self.assertEqual(decide(2, 2, 5, 9, pass_rule="two-thirds"), "failed")

        def test_needs_a_yes(self):
            self.assertEqual(decide(0, 0, 5, 9, pass_rule="two-thirds"), "failed")
            self.assertEqual(decide(0, 0, 9, 9, pass_rule="two-thirds"), "failed")
            self.assertEqual(decide(1, 0, 4, 9, pass_rule="two-thirds"), "passed")


    class Unanimous(unittest.TestCase):
        def test_rules(self):
            self.assertEqual(decide(5, 0, 2, 9, pass_rule="unanimous"), "passed")
            self.assertEqual(decide(5, 1, 0, 9, pass_rule="unanimous"), "failed")
            self.assertEqual(decide(0, 0, 9, 9, pass_rule="unanimous"), "failed")
            self.assertEqual(decide(9, 0, 0, 9, pass_rule="unanimous"), "passed")
            self.assertEqual(decide(1, 0, 4, 9, pass_rule="unanimous"), "passed")


    class Validation(unittest.TestCase):
        def test_bad_counts(self):
            for args in ((-1, 0, 0, 9), (0, -1, 0, 9), (0, 0, -1, 9), (5, 4, 1, 9), (10, 0, 0, 9), (0, 0, 0, 0), (1, 0, 0, -2)):
                with self.assertRaises(ValueError, msg=str(args)):
                    decide(*args)
            decide(5, 3, 1, 9)

        def test_bad_rules(self):
            with self.assertRaises(ValueError):
                decide(5, 0, 0, 9, "half")
            with self.assertRaises(ValueError):
                decide(5, 0, 0, 9, pass_rule="plurality")
            with self.assertRaises(ValueError):
                decide(0, 0, 0, 9, pass_rule="plurality")       # rules are checked before the quorum
            with self.assertRaises(ValueError):
                decide(1, 0, 0, 9, quorum_rule="half")


    if __name__ == "__main__":
        unittest.main()
''')

QUORUMCHECK = Lib(
    name="quorumcheck", lang="python", title="the quorumcheck voting rules (`quorumcheck/rules.py`)",
    blurb="The village hall association's minutes tool uses quorumcheck to say whether a meeting was valid and whether a motion carried.",
    files={"quorumcheck/__init__.py": "", "quorumcheck/rules.py": QUORUMCHECK_SRC, "README.md": QUORUMCHECK_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": QUORUMCHECK_VISIBLE},
    hidden_tests={"tests/test_full.py": QUORUMCHECK_HIDDEN},
    mutate=["quorumcheck/rules.py"], difficulty=1, tags=["voting", "rules"],
    probes=[
        "[quorum(n) for n in (1, 2, 3, 4, 5, 10)]", "[quorum(n, 'third') for n in (1, 3, 4, 7, 10)]",
        "[quorum(n, 'two-thirds') for n in (1, 3, 4, 5, 10)]", "quorum(5, 'all')",
        "decide(3, 1, 0, 9)", "decide(3, 1, 1, 9)", "decide(2, 2, 1, 9)", "decide(1, 3, 1, 9)",
        "decide(5, 0, 0, 9, pass_rule='absolute')", "decide(4, 0, 1, 9, pass_rule='absolute')",
        "decide(6, 3, 0, 9, pass_rule='two-thirds')", "decide(5, 3, 0, 9, pass_rule='two-thirds')",
        "decide(0, 0, 5, 9, pass_rule='two-thirds')", "decide(5, 0, 2, 9, pass_rule='unanimous')", "decide(5, 1, 0, 9, pass_rule='unanimous')",
        "decide(3, 0, 0, 9, 'third')", "decide(6, 0, 0, 9, 'two-thirds')",
    ],
    probe_import="from quorumcheck.rules import quorum, decide\n",
)

# ======================================================================================================================
# heatlanes: heats and lanes for a swimming meet
# ======================================================================================================================

LANEDRAW_README = dd('''
    # heatlanes

    The draw for a swimming meet: swimmers are split into heats by their entry times and given lanes, the fastest in the
    middle.

    ## `lane_order(lanes) -> list[int]`

    The order in which lanes are handed out, best lane first. Lanes are numbered from 1. The first lane is `(lanes + 1) // 2`;
    then the lanes alternate one step above and one step below it, then two steps, and so on, skipping lanes that do not
    exist: `lane_order(8) == [4, 5, 3, 6, 2, 7, 1, 8]`, `lane_order(6) == [3, 4, 2, 5, 1, 6]`,
    `lane_order(5) == [3, 4, 2, 5, 1]`. `ValueError` for `lanes < 1`.

    ## `fmt_time(ms) -> str`

    A time in milliseconds as swimmers read it: rounded half up to hundredths of a second, `M:SS.hh` from one minute on
    (`62500` is `"1:02.50"`) and `S.hh` below one minute (`5000` is `"5.00"`, `59995` rounds up to `"1:00.00"`); `None` (no
    entry time) is `"NT"`. `ValueError` for a negative time.

    ## `build_heats(entries, lanes=8, min_heat=3) -> list[list[(lane, name, ms)]]`

    `entries` is a list of `(name, ms)` where `ms` is the entry time in milliseconds or `None` for a swimmer without a time.
    `ValueError` for duplicate names, `lanes < 1` or `min_heat` outside `1..lanes`.

    1. Rank the swimmers fastest first: those with a time by `(ms, name)`, then those without a time by name (a swimmer
       without a time counts as slower than everybody).
    2. With `n` swimmers there are `ceil(n / lanes)` heats. The heats are filled from the fast end: every heat except the
       slowest has exactly `lanes` swimmers, the slowest heat gets the rest. If that rest is smaller than `min_heat` (and
       there is more than one heat) the slowest heat is topped up to `min_heat` with the slowest swimmers of the next heat.
    3. The result lists the heats in swimming order: **the slowest heat first**, the fastest heat last. Inside a heat the
       fastest swimmer gets the first lane of `lane_order(lanes)`, the next the second lane, and so on; each heat is
       sorted by lane.
    No entries give `[]`.

    ## `format_heats(heats) -> str`

    For every heat (numbered from 1) a line `Heat N` followed by one line `  lane L: name (time)` per swimmer, with the time
    written by `fmt_time`; all lines joined with `"\\n"`. No heats give an empty string.
''')

LANEDRAW_SRC = dd('''
    """Heats and lanes."""


    def lane_order(lanes):
        if lanes < 1:
            raise ValueError("a pool needs at least one lane")
        start = (lanes + 1) // 2
        order = [start]
        step = 1
        while len(order) < lanes:
            for lane in (start + step, start - step):
                if 1 <= lane <= lanes:
                    order.append(lane)
            step += 1
        return order


    def fmt_time(ms):
        if ms is None:
            return "NT"
        if ms < 0:
            raise ValueError("negative time")
        centis = (ms + 5) // 10
        minutes, rest = divmod(centis, 6000)
        seconds, hundredths = divmod(rest, 100)
        if minutes:
            return f"{minutes}:{seconds:02d}.{hundredths:02d}"
        return f"{seconds}.{hundredths:02d}"


    def build_heats(entries, lanes=8, min_heat=3):
        if lanes < 1 or not 1 <= min_heat <= lanes:
            raise ValueError("bad lane settings")
        names = [name for name, _ in entries]
        if len(set(names)) != len(names):
            raise ValueError("duplicate swimmer")
        timed = sorted((e for e in entries if e[1] is not None), key=lambda e: (e[1], e[0]))
        untimed = sorted((e for e in entries if e[1] is None), key=lambda e: e[0])
        ranked = timed + untimed
        n = len(ranked)
        if n == 0:
            return []
        count = -(-n // lanes)
        sizes = [n - lanes * (count - 1)] + [lanes] * (count - 1)
        if count > 1 and sizes[0] < min_heat:
            shift = min_heat - sizes[0]
            sizes[0] += shift
            sizes[1] -= shift
        order = lane_order(lanes)
        heats = []
        end = n
        for size in sizes:
            group = ranked[end - size:end]
            end -= size
            heats.append(sorted((order[i], name, ms) for i, (name, ms) in enumerate(group)))
        return heats


    def format_heats(heats):
        lines = []
        for number, heat in enumerate(heats, 1):
            lines.append(f"Heat {number}")
            for lane, name, ms in heat:
                lines.append(f"  lane {lane}: {name} ({fmt_time(ms)})")
        return "\\n".join(lines)
''')

LANEDRAW_VISIBLE = dd('''
    import unittest

    from heatlanes.draw import fmt_time, lane_order


    class BasicTests(unittest.TestCase):
        def test_lanes(self):
            self.assertEqual(lane_order(8), [4, 5, 3, 6, 2, 7, 1, 8])

        def test_time(self):
            self.assertEqual(fmt_time(62500), "1:02.50")


    if __name__ == "__main__":
        unittest.main()
''')

LANEDRAW_HIDDEN = dd('''
    import unittest

    from heatlanes.draw import build_heats, fmt_time, format_heats, lane_order

    TEN = [(chr(ord("A") + i), 50000 + 1000 * i) for i in range(10)]      # A is the fastest


    class Lanes(unittest.TestCase):
        def test_orders(self):
            table = {
                1: [1], 2: [1, 2], 3: [2, 3, 1], 4: [2, 3, 1, 4], 5: [3, 4, 2, 5, 1], 6: [3, 4, 2, 5, 1, 6],
                7: [4, 5, 3, 6, 2, 7, 1], 8: [4, 5, 3, 6, 2, 7, 1, 8], 10: [5, 6, 4, 7, 3, 8, 2, 9, 1, 10],
            }
            for lanes, want in table.items():
                self.assertEqual(lane_order(lanes), want, lanes)

        def test_errors(self):
            for lanes in (0, -2):
                with self.assertRaises(ValueError):
                    lane_order(lanes)


    class Times(unittest.TestCase):
        def test_formats(self):
            table = {
                62500: "1:02.50", 5000: "5.00", 0: "0.00", 59990: "59.99", 3599990: "59:59.99", 60000: "1:00.00",
                9995: "10.00", 9994: "9.99", 62504: "1:02.50", 62505: "1:02.51", 600000: "10:00.00", 61000: "1:01.00",
                7: "0.01", 4: "0.00", 59995: "1:00.00", 3600000: "60:00.00",
            }
            for ms, want in table.items():
                self.assertEqual(fmt_time(ms), want, ms)

        def test_no_time_and_errors(self):
            self.assertEqual(fmt_time(None), "NT")
            with self.assertRaises(ValueError):
                fmt_time(-1)


    class Heats(unittest.TestCase):
        def names(self, heats):
            return [[name for _, name, _ in heat] for heat in heats]

        def test_topping_up_the_slowest_heat(self):
            heats = build_heats(TEN, lanes=4, min_heat=3)
            self.assertEqual(self.names(heats), [["J", "H", "I"], ["G", "E", "F"], ["C", "A", "B", "D"]])
            self.assertEqual([[lane for lane, _, _ in heat] for heat in heats], [[1, 2, 3], [1, 2, 3], [1, 2, 3, 4]])
            self.assertEqual(heats[2][1], (2, "A", 50000))

        def test_no_top_up_needed(self):
            heats = build_heats(TEN, lanes=4, min_heat=2)
            self.assertEqual(self.names(heats), [["I", "J"], ["G", "E", "F", "H"], ["C", "A", "B", "D"]])
            self.assertEqual([len(h) for h in heats], [2, 4, 4])

        def test_full_heats_and_a_remainder_of_one(self):
            entries = [(f"s{i}", 60000 + i) for i in range(9)]
            heats = build_heats(entries, lanes=4, min_heat=1)
            self.assertEqual([len(h) for h in heats], [1, 4, 4])
            self.assertEqual(heats[0], [(2, "s8", 60008)])
            self.assertEqual({name for _, name, _ in heats[2]}, {"s0", "s1", "s2", "s3"})

        def test_exact_multiple(self):
            heats = build_heats(TEN[:8], lanes=4, min_heat=3)
            self.assertEqual([len(h) for h in heats], [4, 4])
            self.assertEqual({name for _, name, _ in heats[1]}, set("ABCD"))
            self.assertEqual({name for _, name, _ in heats[0]}, set("EFGH"))

        def test_single_heat(self):
            heats = build_heats([("P", 50000), ("Q", 51000)], lanes=8, min_heat=3)
            self.assertEqual(heats, [[(4, "P", 50000), (5, "Q", 51000)]])
            self.assertEqual(build_heats([("Solo", 1)]), [[(4, "Solo", 1)]])
            self.assertEqual(build_heats([]), [])

        def test_swimmers_without_a_time_are_slowest(self):
            heats = build_heats([("Y", None), ("P", 50000), ("X", None), ("Q", 51000)], lanes=8, min_heat=3)
            self.assertEqual(heats, [[(3, "X", None), (4, "P", 50000), (5, "Q", 51000), (6, "Y", None)]])
            mixed = build_heats([("n1", None), ("n2", None), ("t1", 1), ("t2", 2), ("t3", 3), ("t4", 4)], lanes=3, min_heat=1)
            self.assertEqual(self.names(mixed), [["n2", "t4", "n1"], ["t3", "t1", "t2"]])

        def test_default_settings(self):
            entries = [(f"s{i:02d}", 60000 + i) for i in range(17)]
            heats = build_heats(entries)
            self.assertEqual([len(h) for h in heats], [3, 6, 8])
            self.assertEqual([lane for lane, _, _ in heats[2]], [1, 2, 3, 4, 5, 6, 7, 8])
            self.assertEqual(heats[2][3][1], "s00")           # the fastest swimmer has lane 4 of 8

        def test_one_lane_pool(self):
            heats = build_heats([("a", 3), ("b", 1), ("c", 2)], lanes=1, min_heat=1)
            self.assertEqual(heats, [[(1, "a", 3)], [(1, "c", 2)], [(1, "b", 1)]])

        def test_equal_times_are_ordered_by_name(self):
            heats = build_heats([("Bo", 50000), ("Al", 50000), ("Cy", 50000)], lanes=8)
            self.assertEqual(heats, [[(3, "Cy", 50000), (4, "Al", 50000), (5, "Bo", 50000)]])

        def test_every_swimmer_appears_once(self):
            for n in range(0, 30):
                entries = [(f"s{i}", 50000 + 37 * i) for i in range(n)]
                heats = build_heats(entries, lanes=6, min_heat=3)
                flat = [name for heat in heats for _, name, _ in heat]
                self.assertEqual(sorted(flat), sorted(name for name, _ in entries))
                for heat in heats:
                    lanes_used = [lane for lane, _, _ in heat]
                    self.assertEqual(lanes_used, sorted(set(lanes_used)))
                    self.assertTrue(all(1 <= lane <= 6 for lane in lanes_used))
                if len(heats) > 1:
                    self.assertGreaterEqual(len(heats[0]), 3)
                    self.assertTrue(all(len(h) == 6 for h in heats[2:]))

        def test_fastest_heat_is_last_and_fastest_swimmer_has_the_middle_lane(self):
            heats = build_heats(TEN, lanes=4, min_heat=1)
            self.assertEqual(heats[-1][1][1:], ("A", 50000))
            self.assertEqual(max(ms for _, _, ms in heats[-1]), 53000)
            self.assertEqual(min(ms for _, _, ms in heats[0]), 58000)

        def test_errors(self):
            with self.assertRaises(ValueError):
                build_heats([("A", 1), ("A", 2)])
            for lanes, min_heat in ((0, 1), (4, 0), (4, 5), (-1, 1)):
                with self.assertRaises(ValueError, msg=(lanes, min_heat)):
                    build_heats(TEN, lanes=lanes, min_heat=min_heat)
            build_heats(TEN, lanes=4, min_heat=4)


    class Formatting(unittest.TestCase):
        def test_format(self):
            heats = build_heats([("Ann", 62500), ("Bea", 59990), ("Cat", None)], lanes=4, min_heat=1)
            self.assertEqual(format_heats(heats), "Heat 1\\n  lane 1: Cat (NT)\\n  lane 2: Bea (59.99)\\n  lane 3: Ann (1:02.50)")
            self.assertEqual(format_heats([]), "")

        def test_two_heats(self):
            text = format_heats(build_heats(TEN, lanes=4, min_heat=3))
            lines = text.split("\\n")
            self.assertEqual(lines[0], "Heat 1")
            self.assertEqual(lines[1], "  lane 1: J (59.00)")
            self.assertIn("Heat 3", lines)
            self.assertEqual(lines[-1], "  lane 4: D (53.00)")
            self.assertEqual(len(lines), 3 + 10)


    if __name__ == "__main__":
        unittest.main()
''')

LANEDRAW = Lib(
    name="heatlanes", lang="python", title="the heatlanes heat builder (`heatlanes/draw.py`)",
    blurb="The swimming club's meet manager uses heatlanes to split entries into heats, assign lanes and print the start lists.",
    files={"heatlanes/__init__.py": "", "heatlanes/draw.py": LANEDRAW_SRC, "README.md": LANEDRAW_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": LANEDRAW_VISIBLE},
    hidden_tests={"tests/test_full.py": LANEDRAW_HIDDEN},
    mutate=["heatlanes/draw.py"], difficulty=2, tags=["sport", "seeding"],
    probes=[
        "lane_order(8)", "lane_order(5)", "lane_order(6)", "lane_order(7)",
        "[fmt_time(m) for m in (62500, 5000, 59990, 59995, 9995, 62505, 3599990)]", "fmt_time(None)",
        "build_heats([('A', 50000), ('B', 51000), ('C', 52000), ('D', 53000), ('E', 54000), ('F', 55000), ('G', 56000), ('H', 57000), ('I', 58000), ('J', 59000)], lanes=4, min_heat=3)",
        "build_heats([('A', 50000), ('B', 51000), ('C', 52000), ('D', 53000), ('E', 54000), ('F', 55000), ('G', 56000), ('H', 57000), ('I', 58000), ('J', 59000)], lanes=4, min_heat=2)",
        "build_heats([('Y', None), ('P', 50000), ('X', None), ('Q', 51000)])",
        "build_heats([('Bo', 50000), ('Al', 50000), ('Cy', 50000)])",
        "build_heats([('Solo', 1)])", "build_heats([('A', 1), ('A', 2)])",
        "format_heats(build_heats([('Ann', 62500), ('Bea', 59990), ('Cat', None)], lanes=4, min_heat=1))",
    ],
    probe_import="from heatlanes.draw import lane_order, fmt_time, build_heats, format_heats\n",
)

# ======================================================================================================================
# barcut: cutting pieces from stock bars
# ======================================================================================================================

BARCUT_README = dd('''
    # barcut

    A joinery shop cuts required lengths (whole millimetres) from stock bars of one length. The saw blade removes `kerf`
    millimetres at every cut.

    ## `plan_cuts(pieces, stock_len, kerf=0) -> list[(list[int], int)]`

    `pieces` is a list of required lengths. `ValueError` for `stock_len < 1`, `kerf < 0`, a piece shorter than 1 or longer than
    `stock_len`. First fit decreasing: the pieces are handled from the longest to the shortest (equal lengths in their input
    order) and each goes onto the first bar that still has room for it; if there is none a new bar is started. A bar holding
    pieces `p1 .. pk` uses `p1 + ... + pk + kerf * (k - 1)` millimetres (the kerf is lost between two pieces; the end of the
    last piece needs no kerf), which may not exceed `stock_len`. The result lists the bars in the order they were started,
    each as `(pieces in the order they were placed, leftover)` with `leftover = stock_len - used`. No pieces give `[]`.

    ## `waste_pct(bars, stock_len) -> int`

    The share of the bought material that is not in a piece (offcuts and kerf together): with `total = len(bars) *
    stock_len` and `waste = total - sum of all piece lengths`, `100 * waste / total` rounded half up to a whole number;
    `0` when there are no bars.

    ## `cut_list(bars) -> str`

    One line per bar, `Bar N: 120 + 80 + 30 (left 4)` (the pieces in placement order joined by ` + `, `N` counting from 1),
    lines joined with `"\\n"`; no bars give an empty string.
''')

BARCUT_SRC = dd('''
    """Cutting stock with kerf."""


    def plan_cuts(pieces, stock_len, kerf=0):
        if stock_len < 1 or kerf < 0:
            raise ValueError("stock_len must be at least 1 and kerf must not be negative")
        if any(p < 1 or p > stock_len for p in pieces):
            raise ValueError("every piece must fit on a bar")
        bars = []
        for i in sorted(range(len(pieces)), key=lambda i: (-pieces[i], i)):
            piece = pieces[i]
            for bar in bars:
                need = piece + (kerf if bar[0] else 0)
                if bar[1] + need <= stock_len:
                    bar[0].append(piece)
                    bar[1] += need
                    break
            else:
                bars.append([[piece], piece])
        return [(cuts, stock_len - used) for cuts, used in bars]


    def waste_pct(bars, stock_len):
        total = len(bars) * stock_len
        if total == 0:
            return 0
        waste = total - sum(sum(cuts) for cuts, _ in bars)
        return (200 * waste + total) // (2 * total)


    def cut_list(bars):
        lines = []
        for number, (cuts, left) in enumerate(bars, 1):
            lines.append(f"Bar {number}: " + " + ".join(str(c) for c in cuts) + f" (left {left})")
        return "\\n".join(lines)
''')

BARCUT_VISIBLE = dd('''
    import unittest

    from barcut.cuts import plan_cuts


    class BasicTests(unittest.TestCase):
        def test_two_bars(self):
            self.assertEqual(plan_cuts([150, 100, 90], 240), [([150, 90], 0), ([100], 140)])


    if __name__ == "__main__":
        unittest.main()
''')

BARCUT_HIDDEN = dd('''
    import unittest

    from barcut.cuts import cut_list, plan_cuts, waste_pct


    class Planning(unittest.TestCase):
        def test_walkthrough_with_kerf(self):
            got = plan_cuts([120, 80, 70, 40, 30, 120], 240, kerf=3)
            self.assertEqual(got, [([120, 80, 30], 4), ([120, 70, 40], 4)])

        def test_no_kerf(self):
            self.assertEqual(plan_cuts([120, 120], 240), [([120, 120], 0)])
            self.assertEqual(plan_cuts([100, 100, 100], 240), [([100, 100], 40), ([100], 140)])

        def test_exact_fit_with_kerf(self):
            self.assertEqual(plan_cuts([49, 49], 100, kerf=2), [([49, 49], 0)])
            self.assertEqual(plan_cuts([50, 49], 100, kerf=2), [([50], 50), ([49], 51)])
            self.assertEqual(plan_cuts([50, 48], 100, kerf=2), [([50, 48], 0)])

        def test_tiny_pieces_and_bars(self):
            self.assertEqual(plan_cuts([1], 1), [([1], 0)])
            self.assertEqual(plan_cuts([1, 1], 1), [([1], 0), ([1], 0)])
            self.assertEqual(plan_cuts([1, 1], 2), [([1, 1], 0)])
            self.assertEqual(plan_cuts([1, 1], 2, kerf=1), [([1], 1), ([1], 1)])

        def test_a_piece_the_size_of_the_bar(self):
            self.assertEqual(plan_cuts([240, 1], 240, kerf=3), [([240], 0), ([1], 239)])
            self.assertEqual(plan_cuts([240], 240, kerf=3), [([240], 0)])

        def test_longest_first_and_stable(self):
            got = plan_cuts([30, 60, 30, 60], 100)
            self.assertEqual(got, [([60, 30], 10), ([60, 30], 10)])
            self.assertEqual(plan_cuts([10, 10, 10], 25), [([10, 10], 5), ([10], 15)])

        def test_several_bars(self):
            got = plan_cuts([100, 150, 70, 60], 200)
            self.assertEqual(got, [([150], 50), ([100, 70], 30), ([60], 140)])

        def test_later_pieces_fill_earlier_bars(self):
            got = plan_cuts([90, 90, 90, 10, 10, 10], 100)
            self.assertEqual(got, [([90, 10], 0), ([90, 10], 0), ([90, 10], 0)])

        def test_no_pieces(self):
            self.assertEqual(plan_cuts([], 100), [])

        def test_input_is_not_modified(self):
            pieces = [30, 90, 60]
            plan_cuts(pieces, 100)
            self.assertEqual(pieces, [30, 90, 60])

        def test_errors(self):
            for args in (([0], 100), ([-5], 100), ([101], 100), ([10], 0), ([10], -1)):
                with self.assertRaises(ValueError, msg=str(args)):
                    plan_cuts(*args)
            with self.assertRaises(ValueError):
                plan_cuts([10], 100, kerf=-1)
            plan_cuts([100], 100)

        def test_leftover_accounts_for_the_kerf(self):
            got = plan_cuts([30, 30, 30], 100, kerf=5)
            self.assertEqual(got, [([30, 30, 30], 100 - 90 - 10)])
            got = plan_cuts([30, 30, 30, 30], 100, kerf=5)
            self.assertEqual(got, [([30, 30, 30], 0), ([30], 70)])


    class Waste(unittest.TestCase):
        def test_percentages(self):
            bars = plan_cuts([120, 80, 70, 40, 30, 120], 240, kerf=3)
            self.assertEqual(waste_pct(bars, 240), 4)             # 20 of 480
            self.assertEqual(waste_pct([([100], 0)], 100), 0)
            self.assertEqual(waste_pct([([50], 50)], 100), 50)
            self.assertEqual(waste_pct([], 100), 0)
            self.assertEqual(waste_pct([([1], 7)], 8), 88)         # 87.5 rounds up
            self.assertEqual(waste_pct([([3], 5)], 8), 63)         # 62.5 rounds up
            self.assertEqual(waste_pct([([5], 3)], 8), 38)         # 37.5 rounds up
            self.assertEqual(waste_pct([([1], 99)], 100), 99)
            self.assertEqual(waste_pct([([40, 40], 20), ([10], 90)], 100), 55)
            self.assertEqual(waste_pct([([1], 3)], 4), 75)


    class Listing(unittest.TestCase):
        def test_cut_list(self):
            bars = plan_cuts([120, 80, 70, 40, 30, 120], 240, kerf=3)
            self.assertEqual(cut_list(bars), "Bar 1: 120 + 80 + 30 (left 4)\\nBar 2: 120 + 70 + 40 (left 4)")
            self.assertEqual(cut_list([([100], 140)]), "Bar 1: 100 (left 140)")
            self.assertEqual(cut_list([]), "")


    if __name__ == "__main__":
        unittest.main()
''')

BARCUT = Lib(
    name="barcut", lang="python", title="the barcut cutting planner (`barcut/cuts.py`)",
    blurb="The joinery's workshop tool uses barcut to plan which pieces to saw from which stock bar and how much material is wasted.",
    files={"barcut/__init__.py": "", "barcut/cuts.py": BARCUT_SRC, "README.md": BARCUT_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": BARCUT_VISIBLE},
    hidden_tests={"tests/test_full.py": BARCUT_HIDDEN},
    mutate=["barcut/cuts.py"], difficulty=2, tags=["cutting-stock", "packing"],
    probes=[
        "plan_cuts([120, 80, 70, 40, 30, 120], 240, kerf=3)", "plan_cuts([100, 100, 100], 240)",
        "plan_cuts([49, 49], 100, kerf=2)", "plan_cuts([50, 49], 100, kerf=2)", "plan_cuts([30, 60, 30, 60], 100)",
        "plan_cuts([90, 90, 90, 10, 10, 10], 100)", "plan_cuts([30, 30, 30, 30], 100, kerf=5)", "plan_cuts([101], 100)",
        "waste_pct(plan_cuts([120, 80, 70, 40, 30, 120], 240, kerf=3), 240)", "waste_pct([([1], 7)], 8)", "waste_pct([([5], 3)], 8)",
        "cut_list(plan_cuts([120, 80, 70, 40, 30, 120], 240, kerf=3))",
    ],
    probe_import="from barcut.cuts import plan_cuts, waste_pct, cut_list\n",
)

LIBS = [ROTAPICK, DEGREEDAYS, QUORUMCHECK, LANEDRAW, BARCUT]
register_libs3(LIBS, n=10)
