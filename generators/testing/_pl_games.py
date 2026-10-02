"""Python libraries about stateful rule keeping: a tabletop initiative tracker, theatre seat blocks (parametrised)."""
from __future__ import annotations

from fx import dd

from ._engine import TLib
from ._pl_pricing import WHERE_PY
from ._pygold import gold_tests


def initiative(rng) -> TLib:
    first = rng.choice(["pc", "foe"])
    second = "foe" if first == "pc" else "pc"
    tick = rng.choice(["end", "start"])
    roll_max = rng.choice([30, 40])
    name_max = rng.choice([16, 20])
    src = dd(f'''
        """Initiative tracker for the Thursday-night table, with the house rules in the README."""

        ROLL_MAX = {roll_max}
        NAME_MAX = {name_max}
        TIE_TEAM = ("{first}", "{second}")  # on a full tie the team listed first acts first
        TICK_AT = "{tick}"  # conditions count down at the "start" or the "end" of their owner's turn


        class Tracker:
            def __init__(self):
                self._c = {{}}  # lower-cased name -> combatant
                self._turn = []  # names in this round's turn order
                self._idx = 0  # position of the current combatant in _turn
                self.round = 0  # 0 until start() has been called

            @staticmethod
            def _key(name):
                return name.strip().lower()

            def add(self, name, roll, dex=0, team="pc"):
                name = name.strip()
                if not 1 <= len(name) <= NAME_MAX or "," in name:
                    raise ValueError(f"bad name: {{name!r}}")
                if isinstance(roll, bool) or not isinstance(roll, int) or not 1 <= roll <= ROLL_MAX:
                    raise ValueError(f"bad roll: {{roll!r}}")
                if team not in TIE_TEAM:
                    raise ValueError(f"bad team: {{team!r}}")
                if self._key(name) in self._c:
                    raise ValueError(f"duplicate combatant: {{name}}")
                self._c[self._key(name)] = {{"name": name, "roll": roll, "dex": dex, "team": team, "conds": {{}}}}

            def order(self):
                def key(c):
                    return (-c["roll"], -c["dex"], TIE_TEAM.index(c["team"]), c["name"].lower())

                return [c["name"] for c in sorted(self._c.values(), key=key)]

            def current(self):
                return self._turn[self._idx] if self.round else None

            def start(self):
                if not self._c:
                    raise ValueError("nobody is in the fight")
                self.round = 1
                self._turn = self.order()
                self._idx = 0
                self._begin(self._turn[0])
                return self._turn[0]

            def _tick(self, name):
                conds = self._c[self._key(name)]["conds"]
                for label in list(conds):
                    conds[label] -= 1
                    if conds[label] <= 0:
                        del conds[label]

            def _begin(self, name):
                if TICK_AT == "start":
                    self._tick(name)

            def _end(self, name):
                if TICK_AT == "end":
                    self._tick(name)

            def next_turn(self):
                if not self.round:
                    raise ValueError("the fight has not started")
                self._end(self._turn[self._idx])
                self._idx += 1
                if self._idx >= len(self._turn):
                    self.round += 1
                    self._turn = self.order()
                    self._idx = 0
                self._begin(self._turn[self._idx])
                return self._turn[self._idx], self.round

            def delay(self):
                """The current combatant waits: they move to the end of this round's order. Returns who is up now."""
                if not self.round:
                    raise ValueError("the fight has not started")
                self._turn.append(self._turn.pop(self._idx))
                self._begin(self._turn[self._idx])
                return self._turn[self._idx]

            def remove(self, name):
                key = self._key(name)
                if key not in self._c:
                    raise ValueError(f"no such combatant: {{name}}")
                real = self._c.pop(key)["name"]
                if self.round and real in self._turn:
                    pos = self._turn.index(real)
                    self._turn.pop(pos)
                    if pos < self._idx:
                        self._idx -= 1
                    if self._idx >= len(self._turn):
                        self.round += 1
                        self._turn = self.order()
                        self._idx = 0

            def add_condition(self, name, label, rounds):
                if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
                    raise ValueError(f"bad duration: {{rounds!r}}")
                if self._key(name) not in self._c:
                    raise ValueError(f"no such combatant: {{name}}")
                self._c[self._key(name)]["conds"][label] = rounds

            def conditions(self, name):
                if self._key(name) not in self._c:
                    raise ValueError(f"no such combatant: {{name}}")
                return dict(sorted(self._c[self._key(name)]["conds"].items()))
    ''')
    tick_text = ("at the **end** of its owner's turn (when `next_turn` leaves them)" if tick == "end" else "at the **start** of its owner's turn (when they come up, including in `start()` for the first combatant)")
    readme = dd(f'''
        # initiative

        Initiative tracker for the Thursday-night table. A fight is a set of combatants, each with a name, an initiative roll, a dexterity
        modifier and a team (`"pc"` or `"foe"`).

        ## `Tracker.add(name, roll, dex=0, team="pc")`
        Adds a combatant. The name is stripped; it must be 1-{name_max} characters and contain no comma. `roll` must be an `int` (not a bool) from 1 to {roll_max}.
        `team` must be `"pc"` or `"foe"`. Names are unique ignoring case. Anything else raises `ValueError`.

        ## `Tracker.order() -> list[str]`
        The names in turn order: higher `roll` first; ties go to the higher `dex`; remaining ties to the `{first}` team before the `{second}` team; then
        alphabetically ignoring case. The names keep the capitalisation they were added with.

        ## Running a fight
        * `start()` begins round 1 with the first combatant of `order()` and returns that name (`ValueError` if nobody was added).
        * `current()` is the name whose turn it is, `None` before `start()`; `round` is the round number (0 before `start()`).
        * `next_turn()` ends the current turn and returns `(name, round)` of the next one. After the last combatant a new round begins: `round`
          goes up by one and the order is worked out again (so combatants added since then take part). `ValueError` before `start()`.
        * `delay()` makes the current combatant wait: they move to the end of the current round's order and the next combatant is up; the name now up
          is returned. The delayed combatant's turn ends normally when their (late) turn is over. Their initiative is unchanged for the next round.
        * `remove(name)` takes a combatant out (`ValueError` if unknown). If it was somebody earlier in this round's order than the current
          combatant, the current combatant stays current; if it was the current combatant, the next one in the order is up; if that was
          the last of the round, a new round begins with the first combatant.

        ## Conditions
        `add_condition(name, label, rounds)` puts a condition on a combatant for `rounds` of *their own* turns (`rounds` is a positive `int`, `ValueError`
        otherwise or for an unknown name; adding a label again replaces it). A condition counts down {tick_text}; when it reaches 0 it is gone.
        `conditions(name)` returns `{{label: turns left}}` ordered by label.
    ''')
    files = {"README.md": readme, "initiative/__init__.py": "", "initiative/tracker.py": src, "tests/__init__.py": ""}
    stub = {"tests/test_smoke.py": dd('''
        import unittest

        from initiative.tracker import Tracker


        class SmokeTest(unittest.TestCase):
            def test_add_and_order(self):
                t = Tracker()
                t.add("Ayla", 12)
                self.assertEqual(t.order(), ["Ayla"])
    ''')}
    team1, team2 = first, second
    setup = [("do", "t = Tracker()"), ("do", f"t.add('Ayla', 15, dex=3, team='pc')"), ("do", "t.add('Brom', 15, dex=3, team='foe')"), ("do", "t.add('cleo', 15, dex=1)"),
             ("do", "t.add('Dax', 9, team='foe')"), ("do", "t.add('Edda', 22, team='pc')"), ("do", "t.add('ada', 15, dex=3, team='pc')")]
    steps = [
        ("order_by_roll", [("do", "t = Tracker()"), ("do", "for n, r in (('low', 3), ('high', 18), ('mid', 10)): t.add(n, r)"), ("eq", "t.order()")]),
        ("order_ties", setup + [("eq", "t.order()")]),
        ("order_team_tiebreak", [("do", "t = Tracker()"), ("do", "t.add('Zed', 12, team='pc')"), ("do", "t.add('Abe', 12, team='foe')"), ("eq", "t.order()"), ("do", "t.add('Cy', 12, team='foe')"), ("do", "t.add('Bo', 12, team='pc')"), ("eq", "t.order()")]),
        ("order_dex", [("do", "t = Tracker()"), ("do", "t.add('a', 10, dex=-1)"), ("do", "t.add('b', 10, dex=2)"), ("do", "t.add('c', 10)"), ("eq", "t.order()")]),
        ("add_validation", [("do", "t = Tracker()"), ("raises", "ValueError", "t.add('', 5)"), ("raises", "ValueError", "t.add('   ', 5)"), ("raises", "ValueError", "t.add('a,b', 5)"),
                            ("raises", "ValueError", f"t.add('x' * {name_max + 1}, 5)"), ("do", f"t.add('y' * {name_max}, 5)"), ("raises", "ValueError", "t.add('n', 0)"), ("raises", "ValueError", f"t.add('n', {roll_max + 1})"),
                            ("do", f"t.add('top', {roll_max})"), ("do", "t.add('one', 1)"), ("raises", "ValueError", "t.add('n', 5.0)"), ("raises", "ValueError", "t.add('n', True)"),
                            ("raises", "ValueError", "t.add('n', 5, team='npc')"), ("do", "t.add('Nn', 5)"),
                            ("raises", "ValueError", "t.add('nn', 6)"), ("raises", "ValueError", "t.add(' NN ', 6)"), ("eq", "t.order()")]),
        ("name_is_stripped", [("do", "t = Tracker()"), ("do", "t.add('  Wren  ', 7)"), ("eq", "t.order()")]),
        ("start_and_current", [("do", "t = Tracker()"), ("eq", "(t.round, t.current())"), ("raises", "ValueError", "t.start()"), ("raises", "ValueError", "t.next_turn()"),
                               ("do", "t.add('A', 5)"), ("do", "t.add('B', 9)"), ("eq", "t.start()"), ("eq", "(t.round, t.current())")]),
        ("next_turn_cycles", setup + [("do", "t.start()"), ("do", "seen = [t.next_turn() for _ in range(8)]"), ("eq", "seen")]),
        ("order_recomputed_each_round", [("do", "t = Tracker()"), ("do", "t.add('A', 10)"), ("do", "t.add('B', 5)"), ("do", "t.start()"), ("eq", "t.next_turn()"), ("do", "t.add('C', 20)"),
                                         ("eq", "t.order()"), ("eq", "t.next_turn()"), ("eq", "t.next_turn()"), ("eq", "t.next_turn()")]),
        ("delay_moves_to_end", [("do", "t = Tracker()"), ("do", "for n, r in (('A', 20), ('B', 15), ('C', 10)): t.add(n, r)"), ("do", "t.start()"), ("eq", "t.delay()"), ("eq", "(t.current(), t.round)"),
                                ("eq", "t.next_turn()"), ("eq", "t.next_turn()"), ("eq", "t.next_turn()"), ("eq", "t.order()")]),
        ("delay_twice", [("do", "t = Tracker()"), ("do", "for n, r in (('A', 20), ('B', 15), ('C', 10)): t.add(n, r)"), ("do", "t.start()"), ("eq", "t.delay()"), ("eq", "t.delay()"),
                         ("eq", "t.next_turn()"), ("eq", "t.next_turn()")]),
        ("delay_alone", [("do", "t = Tracker()"), ("do", "t.add('Solo', 5)"), ("do", "t.start()"), ("eq", "t.delay()"), ("eq", "t.next_turn()")]),
        ("delay_needs_a_fight", [("do", "t = Tracker()"), ("do", "t.add('A', 5)"), ("raises", "ValueError", "t.delay()")]),
        ("remove_before_current", [("do", "t = Tracker()"), ("do", "for n, r in (('A', 20), ('B', 15), ('C', 10), ('D', 5)): t.add(n, r)"), ("do", "t.start()"), ("do", "t.next_turn()"), ("do", "t.next_turn()"),
                                   ("eq", "t.current()"), ("do", "t.remove('A')"), ("eq", "(t.current(), t.round)"), ("eq", "t.next_turn()"), ("eq", "t.next_turn()")]),
        ("remove_after_current", [("do", "t = Tracker()"), ("do", "for n, r in (('A', 20), ('B', 15), ('C', 10), ('D', 5)): t.add(n, r)"), ("do", "t.start()"), ("do", "t.remove('c')"),
                                  ("eq", "t.current()"), ("eq", "t.next_turn()"), ("eq", "t.next_turn()"), ("eq", "t.next_turn()")]),
        ("remove_current", [("do", "t = Tracker()"), ("do", "for n, r in (('A', 20), ('B', 15), ('C', 10)): t.add(n, r)"), ("do", "t.start()"), ("do", "t.next_turn()"), ("do", "t.remove('B')"),
                            ("eq", "(t.current(), t.round)"), ("eq", "t.order()")]),
        ("remove_last_of_round", [("do", "t = Tracker()"), ("do", "for n, r in (('A', 20), ('B', 15), ('C', 10)): t.add(n, r)"), ("do", "t.start()"), ("do", "t.next_turn()"), ("do", "t.next_turn()"),
                                  ("do", "t.remove('C')"), ("eq", "(t.current(), t.round)")]),
        ("remove_unknown", [("do", "t = Tracker()"), ("raises", "ValueError", "t.remove('ghost')")]),
        ("condition_countdown", [("do", "t = Tracker()"), ("do", "t.add('A', 20)"), ("do", "t.add('B', 10)"), ("do", "t.add_condition('A', 'poisoned', 2)"), ("do", "t.add_condition('A', 'blessed', 1)"),
                                 ("eq", "t.conditions('A')"), ("do", "t.start()"), ("eq", "t.conditions('A')"), ("do", "t.next_turn()"), ("eq", "t.conditions('A')"), ("do", "t.next_turn()"),
                                 ("eq", "t.conditions('A')"), ("do", "t.next_turn()"), ("eq", "t.conditions('A')"), ("do", "t.next_turn()"), ("eq", "t.conditions('A')")]),
        ("condition_replace_and_errors", [("do", "t = Tracker()"), ("do", "t.add('A', 20)"), ("do", "t.add_condition('A', 'stunned', 1)"), ("do", "t.add_condition('A', 'stunned', 3)"), ("eq", "t.conditions('A')"),
                                          ("raises", "ValueError", "t.add_condition('A', 'x', 0)"), ("raises", "ValueError", "t.add_condition('A', 'x', -1)"), ("raises", "ValueError", "t.add_condition('A', 'x', 1.5)"),
                                          ("raises", "ValueError", "t.add_condition('A', 'x', True)"), ("raises", "ValueError", "t.add_condition('Nobody', 'x', 1)"), ("raises", "ValueError", "t.conditions('Nobody')"),
                                          ("do", "t.add_condition('a', 'zeal', 2)"), ("eq", "t.conditions('A')")]),
        ("condition_and_delay", [("do", "t = Tracker()"), ("do", "t.add('A', 20)"), ("do", "t.add('B', 10)"), ("do", "t.add('C', 5)"), ("do", "t.add_condition('A', 'hasted', 1)"), ("do", "t.start()"),
                                 ("do", "t.delay()"), ("eq", "t.conditions('A')"), ("do", "t.next_turn()"), ("do", "t.next_turn()"), ("eq", "t.conditions('A')"), ("do", "t.next_turn()"), ("eq", "t.conditions('A')")]),
        ("condition_removed_with_combatant", [("do", "t = Tracker()"), ("do", "t.add('A', 20)"), ("do", "t.add_condition('A', 'x', 2)"), ("do", "t.remove('A')"), ("raises", "ValueError", "t.conditions('A')"),
                                              ("do", "t.add('A', 3)"), ("eq", "t.conditions('A')")]),
    ]
    steps = [(n, [st for st in sts]) for n, sts in steps]
    imp = "from initiative.tracker import *"
    gold = gold_tests(files, imp, steps, path="tests/test_tracker.py", cls="TrackerTests")
    return TLib(
        name="py-initiative", lang="python", title="the initiative tracker", blurb="The game group's laptop tool keeps turn order, rounds and conditions of a fight.",
        files=files, stub=stub, gold=gold, mutate=["initiative/tracker.py"], cmd="python3 -m unittest discover -s tests -t .", where=WHERE_PY, difficulty=4,
        py_groups=steps, py_imports=imp, probes=[], probe_import="", renames={"_key": "_norm", "_tick": "_count_down"},
        msg_swaps={"duplicate combatant": "already in the fight", "bad name": "invalid name", "bad roll": "invalid roll", "no such combatant": "unknown combatant"},
        focus="tie-breaking, how removal and delay interact with the current turn, round changes, and when conditions count down",
    )


def seatmap(rng) -> TLib:
    """Seat blocks in a small theatre."""
    rows = rng.choice([6, 8])
    cols = rng.choice([10, 12])
    aisle = rng.choice([4, 5, 6])
    wheel_rows = rng.choice([(1, 2), (1,), (2,)])
    ws = ", ".join(str(r) for r in wheel_rows)
    maxp = min(rng.choice([6, 8]), max(aisle, cols - aisle))
    src = dd(f'''
        """Seat allocation for the Bellwether Playhouse: find a block of adjacent seats in one row."""

        ROWS = {rows}  # rows A.. (A is the front row)
        COLS = {cols}  # seats 1..COLS per row
        AISLE_AFTER = {aisle}  # a gangway between seat {aisle} and seat {aisle + 1} in every row
        WHEELCHAIR_ROWS = ({ws},)  # rows (1 = A) whose seats may be removed for wheelchair spaces
        MAX_PARTY = {maxp}


        class SeatMapError(ValueError):
            """Bad request for seats."""


        def seat_name(row, col):
            """Row letter and seat number: row 1, seat 7 is "A7"."""
            return f"{{chr(ord('A') + row - 1)}}{{col}}"


        def parse_seat(text):
            """"A7" -> (1, 7). SeatMapError if the seat does not exist."""
            t = text.strip().upper()
            if len(t) < 2 or not t[0].isalpha() or not t[1:].isdigit():
                raise SeatMapError(f"bad seat: {{text!r}}")
            row, col = ord(t[0]) - ord("A") + 1, int(t[1:])
            if not 1 <= row <= ROWS or not 1 <= col <= COLS:
                raise SeatMapError(f"no such seat: {{text!r}}")
            return row, col


        def adjacent(a, b):
            """True if the two (row, col) seats are in the same row, next to each other and not separated by the gangway."""
            if a[0] != b[0] or abs(a[1] - b[1]) != 1:
                return False
            return min(a[1], b[1]) != AISLE_AFTER


        def free_blocks(taken, row):
            """Maximal runs of free seats in a row, as (first col, last col) pairs; `taken` is a set of seat names. The gangway splits runs."""
            runs, start = [], None
            for col in range(1, COLS + 1):
                free = seat_name(row, col) not in taken
                if free and start is None:
                    start = col
                if start is not None and (not free or col == AISLE_AFTER or col == COLS):
                    end = col if free else col - 1
                    if end >= start:
                        runs.append((start, end))
                    start = None
            return runs


        def find_block(taken, party, wheelchairs=0):
            """The best block for a party: `party` adjacent seats (1..MAX_PARTY) in one row. Preference: the row nearest the front, and in it
            the block whose centre is closest to the middle of the row (ties: the lower seat numbers). Parties with wheelchairs
            (0..party) need the seats in WHEELCHAIR_ROWS only and sit at the first `wheelchairs` seats of the block. Returns the list of seat
            names, or None if there is no room."""
            if not 1 <= party <= MAX_PARTY or not 0 <= wheelchairs <= party:
                raise SeatMapError("bad party")
            rows = WHEELCHAIR_ROWS if wheelchairs else range(1, ROWS + 1)
            middle = (COLS + 1) / 2
            for row in rows:
                best = None
                for first, last in free_blocks(taken, row):
                    for start in range(first, last - party + 2):
                        centre = start + (party - 1) / 2
                        key = (abs(centre - middle), start)
                        if best is None or key < best[0]:
                            best = (key, start)
                if best:
                    return [seat_name(row, best[1] + i) for i in range(party)]
            return None
    ''')
    readme = dd(f'''
        # playhouse

        Seat allocation for the Bellwether Playhouse: {ROWS_WORD[rows]} rows (`A` is the front row) of {cols} seats, with a gangway between seat {aisle} and seat {aisle + 1} in every row.

        ## `seat_name(row, col) -> str` / `parse_seat(text) -> (row, col)`
        `seat_name(1, 7)` is `"A7"`. `parse_seat` accepts a letter and a number in any case, ignoring surrounding blanks (`" b12 "` is `(2, 12)`);
        anything that is not a letter followed by digits is a `SeatMapError`, and so is a seat outside rows A..{chr(ord('A') + rows - 1)} or numbers 1..{cols}.

        ## `adjacent(a, b) -> bool`
        True when two `(row, col)` seats are in the same row, next to each other, and not on the two sides of the gangway.

        ## `free_blocks(taken, row) -> list[(first, last)]`
        The maximal runs of free seats in a row (`taken` is a set of seat names such as `"A7"`), in seat order. The gangway always ends a run.

        ## `find_block(taken, party, wheelchairs=0) -> list[str] | None`
        Finds seats for a party of `party` people (1..{maxp}; `SeatMapError` otherwise, also when `wheelchairs` is not between 0 and `party`). The seats are adjacent
        (see `adjacent`) and in one row. Choice: the front-most row that has room; in that row the block whose centre is closest to the middle of the row
        (the middle is seat {(cols + 1) / 2:g}); equal distance goes to the block with the lower seat numbers. A party with `wheelchairs > 0` can only sit in rows
        {" or ".join(str(r) for r in wheel_rows)} (row 1 is `A`), and the wheelchair spaces are the first `wheelchairs` seats of the block. The result is the list of seat names
        from the lowest seat number up; `None` if there is no room.
    ''')
    files = {"README.md": readme, "playhouse/__init__.py": "", "playhouse/seats.py": src, "tests/__init__.py": ""}
    stub = {"tests/test_smoke.py": dd('''
        import unittest

        from playhouse.seats import seat_name


        class SmokeTest(unittest.TestCase):
            def test_name(self):
                self.assertEqual(seat_name(1, 1), "A1")
    ''')}
    mid = (cols + 1) / 2
    a = aisle
    steps = [
        ("names", [("eq", "seat_name(1, 7)"), ("eq", "seat_name(3, 12)"), ("eq", f"seat_name({rows}, {cols})")]),
        ("parse_ok", [("eq", "parse_seat('A1')"), ("eq", "parse_seat(' b12 ')" if cols >= 12 else "parse_seat(' b10 ')"), ("eq", f"parse_seat('{chr(ord('a') + rows - 1)}{cols}')"), ("eq", "parse_seat('c07')")]),
        ("parse_errors", [("raises", "SeatMapError", "parse_seat('')"), ("raises", "SeatMapError", "parse_seat('A')"), ("raises", "SeatMapError", "parse_seat('7')"), ("raises", "SeatMapError", "parse_seat('AA7')"),
                          ("raises", "SeatMapError", "parse_seat('A0')"), ("raises", "SeatMapError", f"parse_seat('A{cols + 1}')"), ("raises", "SeatMapError", f"parse_seat('{chr(ord('A') + rows)}1')"),
                          ("raises", "SeatMapError", "parse_seat('A-1')"), ("raises", "SeatMapError", "parse_seat('A1b')"), ("raises", "SeatMapError", "parse_seat('1A')")]),
        ("adjacent_rules", [("eq", "adjacent((1, 3), (1, 4))"), ("eq", "adjacent((1, 4), (1, 3))"), ("eq", f"adjacent((1, {a}), (1, {a + 1}))"), ("eq", f"adjacent((1, {a + 1}), (1, {a}))"),
                            ("eq", f"adjacent((1, {a - 1}), (1, {a}))"), ("eq", f"adjacent((1, {a + 1}), (1, {a + 2}))"), ("eq", "adjacent((1, 3), (2, 3))"), ("eq", "adjacent((1, 3), (1, 5))"), ("eq", "adjacent((1, 3), (1, 3))")]),
        ("free_blocks_empty_row", [("eq", "free_blocks(set(), 1)")]),
        ("free_blocks_with_taken", [("eq", "free_blocks({'A3'}, 1)"), ("eq", f"free_blocks({{'A1', 'A{cols}'}}, 1)"), ("eq", f"free_blocks({{'A{a}'}}, 1)"), ("eq", f"free_blocks({{'A{a + 1}'}}, 1)"),
                                    ("eq", f"free_blocks({{f'B{{c}}' for c in range(1, {cols + 1})}}, 2)"), ("eq", "free_blocks({'A3'}, 2)"), ("eq", f"free_blocks({{f'A{{c}}' for c in range(1, {a + 1})}}, 1)"),
                                    ("eq", f"free_blocks({{f'A{{c}}' for c in range({a + 1}, {cols + 1})}}, 1)")]),
        ("free_blocks_single_seats", [("eq", f"free_blocks({{f'A{{c}}' for c in range(1, {cols + 1}) if c % 2 == 0}}, 1)")]),
        ("find_block_front_middle", [("eq", "find_block(set(), 1)"), ("eq", "find_block(set(), 2)"), ("eq", "find_block(set(), 3)"), ("eq", f"find_block(set(), {maxp})"), ("eq", "find_block(set(), 4)")]),
        ("find_block_next_to_taken", [("eq", f"find_block({{'A{int(mid)}'}}, 2)"), ("eq", f"find_block({{'A{int(mid)}', 'A{int(mid) + 1}'}}, 2)"), ("eq", f"find_block({{f'A{{c}}' for c in range(1, {cols + 1})}}, 2)"),
                                      ("eq", f"find_block({{f'A{{c}}' for c in range(1, {cols + 1})}} | {{f'B{{c}}' for c in range(1, {cols + 1})}}, 3)")]),
        ("find_block_gangway", [("eq", f"find_block({{f'A{{c}}' for c in range(1, {cols + 1}) if c not in ({a - 1}, {a}, {a + 1}, {a + 2})}}, 4)"), ("eq", f"find_block({{f'A{{c}}' for c in range(1, {cols + 1}) if c not in ({a - 1}, {a}, {a + 1}, {a + 2})}}, 2)"),
                                ("eq", f"find_block({{f'A{{c}}' for c in range(1, {cols + 1}) if c not in ({a - 1}, {a}, {a + 1}, {a + 2})}}, 1)")]),
        ("find_block_tie_goes_low", [("eq", f"find_block({{f'A{{c}}' for c in range(1, {cols + 1}) if c not in (3, 4, {cols - 3}, {cols - 2})}}, 2)")]),
        ("find_block_none", [("eq", f"find_block({{f'{{r}}{{c}}' for r in 'ABCDEFGH'[:{rows}] for c in range(1, {cols + 1})}}, 1)"),
                             ("eq", f"find_block({{f'A{{c}}' for c in range(1, {cols + 1}) if c % 2}} , 2) is not None"), ("eq", f"find_block({{f'{{r}}{{c}}' for r in 'ABCDEFGH'[:{rows}] for c in range(1, {cols + 1}) if c % 3}}, 2)")]),
        ("find_block_party_limits", [("raises", "SeatMapError", "find_block(set(), 0)"), ("raises", "SeatMapError", f"find_block(set(), {maxp + 1})"), ("eq", f"len(find_block(set(), {maxp}))"),
                                     ("raises", "SeatMapError", "find_block(set(), 2, 3)"), ("raises", "SeatMapError", "find_block(set(), 2, -1)"), ("eq", "find_block(set(), 2, 2)")]),
        ("find_block_wheelchairs", [("eq", "find_block(set(), 3, 1)"), ("eq", "find_block(set(), 2, 2)"),
                                    ("eq", f"find_block({{f'A{{c}}' for c in range(1, {cols + 1})}}, 2, 1)"),
                                    ("eq", f"find_block({{f'{{chr(64 + r)}}{{c}}' for r in {wheel_rows!r} for c in range(1, {cols + 1})}}, 2, 1)"),
                                    ("eq", f"find_block({{'A{int(mid)}'}}, 2, 1)")]),
    ]
    imp = "from playhouse.seats import *"
    gold = gold_tests(files, imp, steps, path="tests/test_seats.py", cls="SeatTests")
    return TLib(
        name="py-playhouse", lang="python", title="the Playhouse seat allocator", blurb="The box office finds seats for parties with `playhouse`.",
        files=files, stub=stub, gold=gold, mutate=["playhouse/seats.py"], cmd="python3 -m unittest discover -s tests -t .", where=WHERE_PY, difficulty=4,
        py_groups=steps, py_imports=imp, focus="the gangway, centring rules and tie-breaks, wheelchair rows, and the party limits",
    )


ROWS_WORD = {6: "six", 8: "eight"}
