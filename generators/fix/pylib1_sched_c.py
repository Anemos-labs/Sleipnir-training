"""Python libraries, theme time/money/scheduling (batch sched-c): night-warden rota for alpine huts."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# hutwarden: greedy night rota with weights, away ranges, soft requests, a rest rule, and swap checking
# ======================================================================================================================

HW_README = dd('''
    # hutwarden

    The night rota of the wardens of an alpine club's huts. A night is a `datetime.date` (the night that starts on that
    date). A **rota** is a list of `(night, warden)` pairs in date order; `warden` is a name, or `None` when nobody covers
    the night.

    `people` maps warden names to dicts, **in order of club seniority** (the order of the dict matters, see below). A
    person dict has two optional keys: `away`, a list of closed `(first, last)` date ranges in which the warden is not
    available, and `off`, a collection of nights the warden would rather not work.

    ## Rules (`hutwarden/rules.py`)

    * `night_weight(day, holidays=())`: how hard a night is. A night in `holidays` weighs 3; otherwise a Friday or Saturday
      night weighs 2 and any other night 1.
    * `is_away(person, day)`: `True` when `day` is inside one of the `away` ranges of the person dict (both ends included).
    * `rest_problem(worked, day)`: `worked` is the set of nights a warden works. After three nights in a row a warden
      needs two nights off. The function returns `"fourth night in a row"` when the three nights before `day` are all in
      `worked`; otherwise `"rest after three nights"` when the second, third and fourth nights before `day` are in `worked`
      but the night just before is not; otherwise `None`.

    ## Building a rota (`hutwarden/assign.py`)

    * `build_rota(people, start, end, holidays=(), load=None)`: the rota for the nights from `start` to `end`, both
      included (`[]` when `start` is after `end`). The nights are filled one after the other in date order. For each night:
      1. the candidates are the wardens who are not away that night and for whom `rest_problem` is `None`, given the nights
         they were already given in this rota;
      2. if some candidates do not have the night in their `off` collection, only those remain;
      3. the warden is the remaining candidate with the **lowest load**, a warden's load being the sum of the
         `night_weight` of the nights given to the warden so far in this rota, plus `load.get(name, 0)` (`load` is a dict
         of loads carried over from an earlier season, or `None`);
         a tie goes to the warden whose last night was **earliest** (a warden without a night yet counts as earlier than
         all others), and a tie that remains to the warden who comes first in `people`.

      A night without any candidate is `(night, None)`.
    * `loads(rota, holidays=())`: a dict from warden name to the sum of the `night_weight` of the nights in `rota` the
      warden works (uncovered nights count for nobody; wardens without a night are not in the dict).
    * `spread(rota, names, holidays=())`: the highest load minus the lowest load among `names`, a name without a night
      having load 0; `0` when `names` is empty.

    ## Checking (`hutwarden/check.py`)

    * `check_rota(rota, people)`: the list of rule violations as strings, nights in date order (the rota may be given in
      any order) and, within one night, in the order below:
      * an uncovered night gives `"2025-07-10 uncovered"` (the date in ISO form);
      * a warden who is not in `people` gives `"2025-07-10 Eve: unknown warden"`, and nothing else is checked for that
        night;
      * a warden who is away gives `"2025-07-10 Ada: away"`;
      * a `rest_problem` of the warden's nights in the rota gives `"2025-07-10 Ada: fourth night in a row"` or
        `"2025-07-10 Ada: rest after three nights"` (all of the nights of the warden in the rota are the `worked` set).

      A rota without violations gives `[]`.
    * `swap(rota, people, day_a, day_b)`: a new rota (the old one is not changed) in which the two nights exchange their
      wardens. It raises `ValueError` when one of the nights is not in the rota or is uncovered, when the same warden works
      both nights, and when the exchange gives a violation (as worded by `check_rota`) that the old rota did not have.
      Violations that were already there do not stop a swap.
''')

HW_RULES = dd('''
    from datetime import timedelta


    def night_weight(day, holidays=()):
        if day in holidays:
            return 3
        return 2 if day.weekday() in (4, 5) else 1


    def is_away(person, day):
        return any(first <= day <= last for first, last in person.get("away", ()))


    def rest_problem(worked, day):
        def was(n):
            return day - timedelta(days=n) in worked

        if was(1) and was(2) and was(3):
            return "fourth night in a row"
        if was(2) and was(3) and was(4) and not was(1):
            return "rest after three nights"
        return None
''')

HW_ASSIGN = dd('''
    from datetime import timedelta

    from .rules import is_away, night_weight, rest_problem


    def build_rota(people, start, end, holidays=(), load=None):
        names = list(people)
        load = {name: (load or {}).get(name, 0) for name in names}
        worked = {name: set() for name in names}
        last = {name: None for name in names}
        rota = []
        day = start
        while day <= end:
            free = [n for n in names if not is_away(people[n], day) and rest_problem(worked[n], day) is None]
            happy = [n for n in free if day not in people[n].get("off", ())]
            pool = happy or free
            if pool:
                pick = min(pool, key=lambda n: (load[n], -1 if last[n] is None else last[n].toordinal(), names.index(n)))
                load[pick] += night_weight(day, holidays)
                worked[pick].add(day)
                last[pick] = day
                rota.append((day, pick))
            else:
                rota.append((day, None))
            day += timedelta(days=1)
        return rota


    def loads(rota, holidays=()):
        total = {}
        for day, name in rota:
            if name is not None:
                total[name] = total.get(name, 0) + night_weight(day, holidays)
        return total


    def spread(rota, names, holidays=()):
        total = loads(rota, holidays)
        values = [total.get(name, 0) for name in names]
        return max(values) - min(values) if values else 0
''')

HW_CHECK = dd('''
    from .rules import is_away, rest_problem


    def check_rota(rota, people):
        worked = {}
        for day, name in rota:
            if name is not None:
                worked.setdefault(name, set()).add(day)
        problems = []
        for day, name in sorted(rota, key=lambda item: item[0]):
            stamp = day.isoformat()
            if name is None:
                problems.append(stamp + " uncovered")
            elif name not in people:
                problems.append(stamp + " " + name + ": unknown warden")
            else:
                if is_away(people[name], day):
                    problems.append(stamp + " " + name + ": away")
                reason = rest_problem(worked[name], day)
                if reason:
                    problems.append(stamp + " " + name + ": " + reason)
        return problems


    def swap(rota, people, day_a, day_b):
        names = dict(rota)
        if day_a not in names or day_b not in names or names[day_a] is None or names[day_b] is None:
            raise ValueError("both nights need a warden")
        if names[day_a] == names[day_b]:
            raise ValueError("the same warden works both nights")
        names[day_a], names[day_b] = names[day_b], names[day_a]
        new = [(day, names[day]) for day, _ in rota]
        if set(check_rota(new, people)) - set(check_rota(rota, people)):
            raise ValueError("the swap breaks a rule")
        return new
''')

HW_VISIBLE = dd('''
    import unittest
    from datetime import date

    from hutwarden.assign import build_rota
    from hutwarden.rules import night_weight


    class BasicTests(unittest.TestCase):
        def test_weights(self):
            self.assertEqual([night_weight(date(2025, 7, d)) for d in range(7, 14)], [1, 1, 1, 1, 2, 2, 1])

        def test_three_wardens_take_turns(self):
            people = {"Ada": {}, "Bo": {}, "Cy": {}}
            rota = build_rota(people, date(2025, 7, 7), date(2025, 7, 9))
            self.assertEqual([name for _, name in rota], ["Ada", "Bo", "Cy"])


    if __name__ == "__main__":
        unittest.main()
''')

HW_HIDDEN = dd('''
    import unittest
    from datetime import date

    from hutwarden.assign import build_rota, loads, spread
    from hutwarden.check import check_rota, swap
    from hutwarden.rules import is_away, night_weight, rest_problem

    D = date


    def july(day):
        return D(2025, 7, day)


    def names(rota):
        return [name for _, name in rota]


    class Rules(unittest.TestCase):
        def test_weights_of_the_week(self):
            self.assertEqual([night_weight(july(d)) for d in range(7, 14)], [1, 1, 1, 1, 2, 2, 1])

        def test_holidays_weigh_three(self):
            self.assertEqual(night_weight(july(11), {july(11)}), 3)
            self.assertEqual(night_weight(july(9), {july(9)}), 3)
            self.assertEqual(night_weight(july(13), [july(13)]), 3)
            self.assertEqual(night_weight(july(10), {july(9)}), 1)
            self.assertEqual(night_weight(july(12), (july(9),)), 2)

        def test_away_ranges_are_closed(self):
            person = {"away": [(july(8), july(10)), (july(20), july(20))]}
            self.assertEqual([is_away(person, july(d)) for d in (7, 8, 9, 10, 11, 19, 20, 21)],
                             [False, True, True, True, False, False, True, False])

        def test_no_away_key(self):
            self.assertFalse(is_away({}, july(8)))
            self.assertFalse(is_away({"off": {july(8)}}, july(8)))

        def test_rest_problems(self):
            worked = {july(7), july(8), july(9)}
            table = {10: "fourth night in a row", 11: "rest after three nights", 12: None, 13: None, 9: None, 8: None}
            for day, want in table.items():
                self.assertEqual(rest_problem(worked, july(day)), want, day)
            self.assertIsNone(rest_problem(set(), july(10)))
            self.assertIsNone(rest_problem({july(8), july(9)}, july(10)))
            self.assertIsNone(rest_problem({july(7), july(9)}, july(10)))
            self.assertIsNone(rest_problem({july(7), july(8), july(10)}, july(11)))

        def test_fourth_night_wins_over_rest(self):
            self.assertEqual(rest_problem({july(6), july(7), july(8), july(9)}, july(10)), "fourth night in a row")
            self.assertEqual(rest_problem({july(6), july(7), july(8), july(9)}, july(11)), "rest after three nights")


    class Building(unittest.TestCase):
        PEOPLE = {"Ada": {}, "Bo": {}, "Cy": {}}

        def test_three_wardens_take_turns(self):
            rota = build_rota(self.PEOPLE, july(7), july(15))
            self.assertEqual(names(rota), ["Ada", "Bo", "Cy"] * 3)
            self.assertEqual([day for day, _ in rota], [july(d) for d in range(7, 16)])
            self.assertEqual(loads(rota), {"Ada": 3, "Bo": 4, "Cy": 4})
            self.assertEqual(spread(rota, list(self.PEOPLE)), 1)

        def test_away_and_requests(self):
            people = {"Ada": {"away": [(july(8), july(10))]}, "Bo": {"off": {july(11)}}, "Cy": {}}
            rota = build_rota(people, july(7), july(16))
            self.assertEqual(names(rota), ["Ada", "Bo", "Cy", "Bo", "Ada", "Cy", "Bo", "Ada", "Cy", "Bo"])
            self.assertEqual(loads(rota), {"Ada": 4, "Bo": 4, "Cy": 4})

        def test_nobody_available_leaves_a_gap(self):
            people = {"Ada": {}, "Bo": {"away": [(july(7), july(13))]}}
            rota = build_rota(people, july(7), july(16))
            self.assertEqual(names(rota), ["Ada", "Ada", "Ada", None, None, "Ada", "Ada", "Bo", "Bo", "Bo"])
            self.assertEqual(check_rota(rota, people), ["2025-07-10 uncovered", "2025-07-11 uncovered"])

        def test_streak_and_rest_in_the_builder(self):
            people = {"Ada": {}, "Bo": {}}
            rota = build_rota(people, july(7), july(16), load={"Bo": 100})
            self.assertEqual(names(rota), ["Ada", "Ada", "Ada", "Bo", "Bo", "Ada", "Ada", "Ada", "Bo", "Bo"])
            self.assertEqual(loads(rota), {"Ada": 7, "Bo": 5})
            self.assertEqual(check_rota(rota, people), [])

        def test_carried_load(self):
            rota = build_rota(self.PEOPLE, july(7), july(12), load={"Cy": 5})
            self.assertEqual(names(rota), ["Ada", "Bo", "Ada", "Bo", "Ada", "Bo"])
            rota = build_rota(self.PEOPLE, july(7), july(9), load={"Ada": 1, "Bo": 1})
            self.assertEqual(names(rota), ["Cy", "Ada", "Bo"])
            rota = build_rota(self.PEOPLE, july(7), july(8), load={"Zed": 9})
            self.assertEqual(names(rota), ["Ada", "Bo"])

        def test_holidays_weigh_on_the_load(self):
            holiday = {july(8)}
            rota = build_rota(self.PEOPLE, july(7), july(12), holidays=holiday)
            self.assertEqual(names(rota), ["Ada", "Bo", "Cy", "Ada", "Cy", "Ada"])
            self.assertEqual(loads(rota, holiday), {"Ada": 4, "Bo": 3, "Cy": 3})
            self.assertEqual(loads(rota), {"Ada": 4, "Bo": 1, "Cy": 3})

        def test_everybody_asking_for_a_night_off_still_works(self):
            people = {"Ada": {"off": {july(7)}}, "Bo": {"off": {july(7)}}}
            self.assertEqual(names(build_rota(people, july(7), july(8))), ["Ada", "Bo"])

        def test_away_beats_a_request(self):
            people = {"Ada": {"away": [(july(7), july(7))], "off": {july(7)}}, "Bo": {"off": {july(7)}}}
            self.assertEqual(build_rota(people, july(7), july(7)), [(july(7), "Bo")])

        def test_a_request_beats_the_load(self):
            people = {"Ada": {"off": {july(8)}}, "Bo": {}}
            self.assertEqual(names(build_rota(people, july(7), july(9), load={"Bo": 50})), ["Ada", "Bo", "Ada"])

        def test_seniority_breaks_the_last_tie(self):
            people = {"Zoe": {}, "Abe": {}}
            self.assertEqual(names(build_rota(people, july(7), july(8))), ["Zoe", "Abe"])

        def test_edges(self):
            self.assertEqual(build_rota({}, july(7), july(8)), [(july(7), None), (july(8), None)])
            self.assertEqual(build_rota(self.PEOPLE, july(8), july(7)), [])
            self.assertEqual(build_rota(self.PEOPLE, july(7), july(7)), [(july(7), "Ada")])


    class Loads(unittest.TestCase):
        ROTA = [(july(10), "Ada"), (july(11), "Bo"), (july(12), None), (july(13), "Ada")]

        def test_loads(self):
            self.assertEqual(loads(self.ROTA), {"Ada": 2, "Bo": 2})
            self.assertEqual(loads(self.ROTA, {july(13)}), {"Ada": 4, "Bo": 2})
            self.assertEqual(loads([]), {})

        def test_spread(self):
            self.assertEqual(spread(self.ROTA, ["Ada", "Bo"]), 0)
            self.assertEqual(spread(self.ROTA, ["Ada", "Bo"], {july(13)}), 2)
            self.assertEqual(spread(self.ROTA, ["Ada", "Bo", "Cy"]), 2)
            self.assertEqual(spread(self.ROTA, []), 0)
            self.assertEqual(spread(self.ROTA, ["Cy"]), 0)


    class Checking(unittest.TestCase):
        def test_every_kind_of_violation(self):
            rota = [(july(10), "Ada"), (july(7), "Ada"), (july(8), "Ada"), (july(9), "Ada"), (july(11), "Ada"), (july(12), None),
                    (july(13), "Eve"), (july(14), "Bo")]
            people = {"Ada": {"away": [(july(11), july(11))]}, "Bo": {"away": [(july(14), july(20))]}}
            self.assertEqual(check_rota(rota, people), [
                "2025-07-10 Ada: fourth night in a row",
                "2025-07-11 Ada: away",
                "2025-07-11 Ada: fourth night in a row",
                "2025-07-12 uncovered",
                "2025-07-13 Eve: unknown warden",
                "2025-07-14 Bo: away"])

        def test_rest_after_three_nights(self):
            rota = [(july(7), "Ada"), (july(8), "Ada"), (july(9), "Ada"), (july(10), "Bo"), (july(11), "Ada"), (july(12), "Ada")]
            self.assertEqual(check_rota(rota, {"Ada": {}, "Bo": {}}), ["2025-07-11 Ada: rest after three nights"])

        def test_a_clean_rota(self):
            rota = [(july(7), "Ada"), (july(8), "Ada"), (july(9), "Ada"), (july(12), "Ada")]
            self.assertEqual(check_rota(rota, {"Ada": {}}), [])
            self.assertEqual(check_rota([], {}), [])

        def test_unknown_warden_is_not_checked_further(self):
            rota = [(july(7), "Eve"), (july(8), "Eve"), (july(9), "Eve"), (july(10), "Eve")]
            self.assertEqual(check_rota(rota, {}), ["2025-07-%02d Eve: unknown warden" % d for d in range(7, 11)])


    class Swapping(unittest.TestCase):
        PEOPLE = {"Ada": {"away": [(july(12), july(13))]}, "Bo": {}, "Cy": {}}
        ROTA = [(july(10), "Ada"), (july(11), "Bo"), (july(12), "Cy"), (july(13), "Bo"), (july(14), "Ada"), (july(15), None)]

        def test_the_rota_is_clean(self):
            self.assertEqual(check_rota(self.ROTA[:5], self.PEOPLE), [])

        def test_a_good_swap(self):
            new = swap(self.ROTA, self.PEOPLE, july(10), july(11))
            self.assertEqual(new, [(july(10), "Bo"), (july(11), "Ada"), (july(12), "Cy"), (july(13), "Bo"), (july(14), "Ada"), (july(15), None)])
            self.assertEqual(self.ROTA[0], (july(10), "Ada"))
            self.assertEqual(swap(self.ROTA, self.PEOPLE, july(13), july(12))[2:4], [(july(12), "Bo"), (july(13), "Cy")])

        def test_the_order_of_the_rota_is_kept(self):
            shuffled = [self.ROTA[2], self.ROTA[0], self.ROTA[1]]
            new = swap(shuffled, self.PEOPLE, july(10), july(11))
            self.assertEqual(new, [(july(12), "Cy"), (july(10), "Bo"), (july(11), "Ada")])

        def test_away_blocks_a_swap(self):
            with self.assertRaises(ValueError):
                swap(self.ROTA, self.PEOPLE, july(10), july(12))

        def test_bad_nights(self):
            for a, b in ((10, 14), (11, 13), (10, 10), (10, 20), (20, 10), (10, 15), (15, 11)):
                with self.assertRaises(ValueError, msg=(a, b)):
                    swap(self.ROTA, self.PEOPLE, july(a), july(b))

        def test_a_swap_may_not_break_the_streak_rules(self):
            people = {"Ada": {}, "Bo": {}, "Cy": {}}
            four = [(july(7), "Ada"), (july(8), "Ada"), (july(9), "Bo"), (july(10), "Ada"), (july(11), "Cy"), (july(12), "Cy"), (july(13), "Ada")]
            with self.assertRaises(ValueError):
                swap(four, people, july(9), july(13))
            rest = [(july(7), "Ada"), (july(8), "Ada"), (july(9), "Bo"), (july(10), "Cy"), (july(11), "Ada"), (july(12), "Cy"), (july(13), "Ada")]
            with self.assertRaises(ValueError):
                swap(rest, people, july(9), july(13))
            self.assertEqual(names(swap(rest, people, july(9), july(10))), ["Ada", "Ada", "Cy", "Bo", "Ada", "Cy", "Ada"])

        def test_old_violations_do_not_block(self):
            people = {"Ada": {"away": [(july(7), july(7))]}, "Bo": {}}
            rota = [(july(7), "Ada"), (july(8), "Bo"), (july(9), "Ada"), (july(10), "Bo")]
            self.assertEqual(check_rota(rota, people), ["2025-07-07 Ada: away"])
            self.assertEqual(names(swap(rota, people, july(8), july(9))), ["Ada", "Ada", "Bo", "Bo"])
            self.assertEqual(names(swap(rota, people, july(7), july(8))), ["Bo", "Ada", "Ada", "Bo"])


    if __name__ == "__main__":
        unittest.main()
''')

HUTWARDEN = Lib(
    name="hutwarden", lang="python", title="the hut warden rota planner (`hutwarden/`)",
    blurb="The alpine club staffs its mountain huts night by night, with fair loads and rest rules, using hutwarden.",
    files={"hutwarden/__init__.py": "", "hutwarden/rules.py": HW_RULES, "hutwarden/assign.py": HW_ASSIGN,
           "hutwarden/check.py": HW_CHECK, "README.md": HW_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": HW_VISIBLE},
    hidden_tests={"tests/test_full.py": HW_HIDDEN},
    mutate=["hutwarden/rules.py", "hutwarden/assign.py", "hutwarden/check.py"], difficulty=4,
    tags=["rota", "fairness", "constraints", "swaps"],
    probes=[
        "[night_weight(date(2025, 7, d)) for d in range(7, 14)]", "night_weight(date(2025, 7, 9), {date(2025, 7, 9)})",
        "is_away({'away': [(date(2025, 7, 8), date(2025, 7, 10))]}, date(2025, 7, 10))",
        "is_away({'away': [(date(2025, 7, 8), date(2025, 7, 10))]}, date(2025, 7, 8))",
        "rest_problem({date(2025, 7, 7), date(2025, 7, 8), date(2025, 7, 9)}, date(2025, 7, 10))",
        "rest_problem({date(2025, 7, 7), date(2025, 7, 8), date(2025, 7, 9)}, date(2025, 7, 11))",
        "rest_problem({date(2025, 7, 7), date(2025, 7, 8), date(2025, 7, 9)}, date(2025, 7, 12))",
        "[n for d, n in build_rota({'Ada': {}, 'Bo': {}, 'Cy': {}}, date(2025, 7, 7), date(2025, 7, 15))]",
        "[n for d, n in build_rota({'Ada': {'away': [(date(2025, 7, 8), date(2025, 7, 10))]}, 'Bo': {'off': {date(2025, 7, 11)}}, 'Cy': {}}, date(2025, 7, 7), date(2025, 7, 16))]",
        "[n for d, n in build_rota({'Ada': {}, 'Bo': {'away': [(date(2025, 7, 7), date(2025, 7, 13))]}}, date(2025, 7, 7), date(2025, 7, 16))]",
        "[n for d, n in build_rota({'Ada': {}, 'Bo': {}}, date(2025, 7, 7), date(2025, 7, 16), load={'Bo': 100})]",
        "[n for d, n in build_rota({'Ada': {}, 'Bo': {}, 'Cy': {}}, date(2025, 7, 7), date(2025, 7, 12), holidays={date(2025, 7, 8)})]",
        "[n for d, n in build_rota({'Ada': {}, 'Bo': {}, 'Cy': {}}, date(2025, 7, 7), date(2025, 7, 12), load={'Cy': 5})]",
        "loads(build_rota({'Ada': {}, 'Bo': {}, 'Cy': {}}, date(2025, 7, 7), date(2025, 7, 15)))",
        "spread([(date(2025, 7, 10), 'Ada'), (date(2025, 7, 11), 'Bo'), (date(2025, 7, 12), None)], ['Ada', 'Bo', 'Cy'])",
        "check_rota([(date(2025, 7, d), 'Ada') for d in (7, 8, 9, 10, 11)], {'Ada': {}})",
        "check_rota([(date(2025, 7, 7), 'Ada'), (date(2025, 7, 8), None), (date(2025, 7, 9), 'Eve')], {'Ada': {'away': [(date(2025, 7, 7), date(2025, 7, 7))]}})",
        "swap([(date(2025, 7, 10), 'Ada'), (date(2025, 7, 11), 'Bo')], {'Ada': {}, 'Bo': {'away': [(date(2025, 7, 10), date(2025, 7, 10))]}}, date(2025, 7, 10), date(2025, 7, 11))",
        "swap([(date(2025, 7, 10), 'Ada'), (date(2025, 7, 11), 'Bo')], {'Ada': {}, 'Bo': {}}, date(2025, 7, 10), date(2025, 7, 11))",
        "swap([(date(2025, 7, 10), 'Ada'), (date(2025, 7, 11), 'Ada')], {'Ada': {}}, date(2025, 7, 10), date(2025, 7, 11))",
    ],
    probe_import="from datetime import date\nfrom hutwarden.rules import *\nfrom hutwarden.assign import *\nfrom hutwarden.check import *",
)

register_libs([HUTWARDEN], n=10)
