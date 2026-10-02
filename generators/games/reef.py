"""Reef Salvage (python): a press-your-luck dice game for two divers, with an exact LCG, house-rule variants,
bug-fix tasks on the engine, an undo feature and a seeded bot tournament."""
from __future__ import annotations

from fx import Task, dd, family

from . import _kit, _scen
from ._kit import Bug

LANG = "python"
GAME = "Reef Salvage"

DEFAULT = dict(DICE=6, MIN_SHOAL=2, MIN_CHAIN=3, CHAIN_MULT=2, SWEEP=25, FINE=0, STING=0, ROUNDS=8, SUDDEN=0)


def header(r: dict) -> str:
    return dd(f'''
        # ---- house rules for this table (they are part of the specification, see README.md) ----
        DICE = {r["DICE"]}
        MIN_SHOAL = {r["MIN_SHOAL"]}
        MIN_CHAIN = {r["MIN_CHAIN"]}
        CHAIN_MULT = {r["CHAIN_MULT"]}
        SWEEP = {r["SWEEP"]}
        FINE = {r["FINE"]}
        STING = {r["STING"]}
        ROUNDS = {r["ROUNDS"]}
        SUDDEN = {r["SUDDEN"]}
        # ----------------------------------------------------------------------------------------
    ''')


BODY = dd('''
    MASK = 0x7FFFFFFF


    class Rng:
        """The table's only source of randomness: a linear congruential generator."""

        def __init__(self, seed):
            self.state = seed & MASK

        def next(self):
            self.state = (self.state * 1103515245 + 12345) & MASK
            return self.state

        def die(self):
            return 1 + (self.next() >> 16) % 6


    class Game:
        def __init__(self, seed):
            self.rng = Rng(seed)
            self.totals = [0, 0]
            self.round = 1
            self.turn = 0
            self.over = False
            self._new_turn()

        def _new_turn(self):
            self.turn_score = 0
            self.dice_left = DICE
            self.pool = []
            self.phase = "roll"

        def _claims(self):
            out = []
            for face in range(1, 7):
                if self.pool.count(face) >= MIN_SHOAL:
                    out.append("shoal %d" % face)
            for a in range(1, 7):
                for b in range(a + MIN_CHAIN - 1, 7):
                    if all(f in self.pool for f in range(a, b + 1)):
                        out.append("chain %d-%d" % (a, b))
            return out

        def legal_moves(self):
            if self.over:
                return []
            if self.phase == "roll":
                return ["roll"]
            if self.phase == "choice":
                return ["bank", "roll"]
            return sorted(self._claims())

        def apply(self, move):
            if move not in self.legal_moves():
                raise ValueError("illegal move: %r" % (move,))
            if move == "roll":
                return self._roll()
            if move == "bank":
                return self._bank()
            return self._claim(move)

        def _roll(self):
            self.pool = sorted(self.rng.die() for _ in range(self.dice_left))
            event = "rolled " + " ".join(str(d) for d in self.pool)
            stung = STING > 0 and self.pool.count(1) >= STING
            if stung or not self._claims():
                event += " sting" if stung else " wreck"
                self.turn_score = 0
                if FINE:
                    self.totals[self.turn] = max(0, self.totals[self.turn] - FINE)
                self._end_turn()
            else:
                self.phase = "claim"
            return event

        def _claim(self, move):
            kind, arg = move.split(" ")
            if kind == "shoal":
                face = int(arg)
                count = self.pool.count(face)
                points = face * count * count
                taken = count
            else:
                a, b = (int(x) for x in arg.split("-"))
                points = CHAIN_MULT * sum(range(a, b + 1))
                taken = b - a + 1
            self.turn_score += points
            self.dice_left -= taken
            self.pool = []
            event = "claimed %s +%d" % (move, points)
            if self.dice_left == 0:
                self.turn_score += SWEEP
                self.dice_left = DICE
                event += " sweep +%d" % SWEEP
            self.phase = "choice"
            return event

        def _bank(self):
            banked = self.turn_score
            self.totals[self.turn] += banked
            event = "banked %d" % banked
            if SUDDEN and self.totals[self.turn] >= SUDDEN:
                self.over = True
                event += " sudden"
            else:
                self._end_turn()
            return event

        def _end_turn(self):
            if self.turn == 1:
                self.round += 1
                if self.round > ROUNDS:
                    self.over = True
            self.turn = 1 - self.turn
            self._new_turn()

        def render(self):
            t0, t1 = self.totals
            if self.over:
                winner = "P0" if t0 > t1 else "P1" if t1 > t0 else "draw"
                return "REEF over\\ntotals P0=%d P1=%d\\nwinner %s" % (t0, t1, winner)
            pool = " ".join(str(d) for d in self.pool) or "-"
            return ("REEF round %d/%d P%d to move\\ntotals P0=%d P1=%d\\nturn=%d dice=%d pool=%s\\nphase=%s"
                    % (self.round, ROUNDS, self.turn, t0, t1, self.turn_score, self.dice_left, pool, self.phase))

        def score(self, player):
            return self.totals[player]

        def is_over(self):
            return self.over
''')


def engine(r: dict) -> str:
    return '"""Reef Salvage: a dice game for two divers. The rules are in README.md."""\n\n' + header(r) + "\n\n" + BODY


STUB = dd('''
    """Reef Salvage: a dice game for two divers. The rules and the API are in README.md."""


    class Game:
        def __init__(self, seed):
            raise NotImplementedError

        def legal_moves(self):
            raise NotImplementedError

        def apply(self, move):
            raise NotImplementedError

        def render(self):
            raise NotImplementedError

        def score(self, player):
            raise NotImplementedError

        def is_over(self):
            raise NotImplementedError
''')

ADAPTER = {"tests/adapter.py": dd('''
    """Maps scenario commands onto the engine API (the scenario runner is tests/test_scenarios.py)."""
    import reef


    class Adapter:
        def __init__(self):
            self.game = None

        def run(self, verb, args):
            if verb == "new":                     # new <seed>
                self.game = reef.Game(int(args))
                return "ok"
            if verb == "do":                      # do <move>: the event text, or "illegal"
                try:
                    return self.game.apply(args)
                except ValueError:
                    return "illegal"
            if verb == "legal":                   # sorted legal moves joined by "," ("-" when there are none)
                return ",".join(sorted(self.game.legal_moves())) or "-"
            if verb == "render":
                return self.game.render()
            if verb == "scores":                  # both totals, "P0 P1"
                return "%d %d" % (self.game.score(0), self.game.score(1))
            if verb == "over":
                return "yes" if self.game.is_over() else "no"
            raise KeyError(verb)
''')}

EXAMPLES = dd('''
    # scenario opening
    > new 1
    > render
    > do bank
    > legal
    > do roll
    > legal
    > render
    # scenario a short game
    > new 7
    ~ rand 14 3 emit=render,legal,scores
''')


def hidden_scripts(r: dict) -> dict[str, str]:
    games = "\n".join(f"# scenario game seed {s}\n> new {s}\n~ rand 700 {s * 31 + 5} every=9 emit=render,legal,scores,over" for s in (2, 11, 23, 4242, 90001, 7))
    edge = dd('''
        # scenario illegal moves change nothing
        > new 5
        > do bank
        > do claim
        > do roll roll
        > do ROLL
        > do  roll
        > do shoal 3
        > render
        > do roll
        > do roll
        > do bank
        > do shoal 0
        > do shoal 7
        > do chain 1-1
        > do chain 3-1
        > do chain
        > do
        > render
        > legal
        # scenario seeds
        > new 0
        > do roll
        > render
        > new 2147483647
        > do roll
        > render
        > new 2147483648
        > do roll
        > render
        > new 99999999999
        > do roll
        > render
        # scenario games are independent
        > new 3
        ~ rand 40 8 every=40 emit=render,scores
        > new 3
        ~ rand 40 8 every=40 emit=render,scores
        > new 4
        > render
        > scores
        # scenario junk between moves
        > new 12
        ~ rand 300 77 every=6 emit=render,scores junk=bank|shoal 7|chain 1-2|Roll| roll|claim|shoal 1|chain 1-3|chain 2-6
        # scenario after the end
        > new 13
        ~ rand 2000 5 emit=over
        > legal
        > do roll
        > do bank
        > render
        > scores
    ''')
    return {"hidden_games": games + "\n", "hidden_edge": edge}


def project(r: dict) -> dict[str, str]:
    return {"reef.py": engine(r), ".gitignore": _kit.GITIGNORE[LANG]}


# ----------------------------------------------------------------------------------------------------- README

def lcg_prefix(seed: int, k: int) -> list[int]:
    st, out = seed & 0x7FFFFFFF, []
    for _ in range(k):
        st = (st * 1103515245 + 12345) & 0x7FFFFFFF
        out.append(st)
    return out


def readme(r: dict, note: str = "") -> str:
    ex = lcg_prefix(1, 4)
    dice1 = [1 + (v >> 16) % 6 for v in lcg_prefix(1, r["DICE"])]
    first_roll = " ".join(str(d) for d in sorted(dice1))
    s = []
    s.append(f"# Reef Salvage\n\nTwo divers, **P0** and **P1**, pick through a wreck. On a turn a diver rolls {r['DICE']} dice, claims one set of "
             f"dice from every roll, and decides whether to roll the rest again or to *bank* the points of the turn. A roll that offers nothing to claim "
             f"is a *wreck* and loses the whole turn. The engine is headless: a `Game` object, a list of legal moves, and exact text for every reply.\n")
    if note:
        s.append(note.strip() + "\n")
    s.append("## Randomness\n")
    s.append(f"All randomness comes from one linear congruential generator, so games are reproducible.\n\n"
             f"* `Game(seed)` starts with `state = seed mod 2^31` (`seed` is a non-negative integer, possibly larger than 2^31).\n"
             f"* `next()` sets `state = (state * 1103515245 + 12345) mod 2^31` and returns the new `state`.\n"
             f"* A die is `1 + (next() >> 16) % 6`.\n"
             f"* A roll draws its dice one after the other, in that order, then sorts them ascending. Nothing else ever calls `next()`.\n\n"
             f"Check: with seed 1 the first four values of `next()` are {', '.join(map(str, ex))}, so the first roll of a game with seed 1 is `rolled {first_roll}`.\n")
    s.append("## A turn\n")
    s.append(f"The turn starts with `dice = {r['DICE']}` dice available, `turn = 0` points, and the diver must `roll`.\n\n"
             f"* **`roll`**: roll all available dice (see Randomness). The result is the *pool*. If the pool offers at least one claim the phase becomes `claim`.\n"
             f"  Otherwise it is a wreck: the turn score is lost and the turn passes to the other diver.")
    if r["STING"]:
        s.append(f"  In addition, if the pool contains {r['STING']} or more dice showing 1 (urchins) the diver is *stung*: this ends the turn exactly like a wreck, "
                 f"even if the pool offers claims (the stinging check comes first).")
    if r["FINE"]:
        s.append(f"  A wreck{' or a sting' if r['STING'] else ''} also costs the diver a fine of {r['FINE']} points taken from their total, which never drops below 0.")
    s.append("\n* **claims** (phase `claim`: the only legal moves are the claims the pool offers; exactly one must be played):\n"
             f"  * `shoal F` where `F` is a face (1..6) showing at least {r['MIN_SHOAL']} times in the pool: claims *every* die showing `F`. "
             f"Points: `F * c * c` where `c` is the number of dice claimed.\n"
             f"  * `chain A-B` where `A < B`, the chain has at least {r['MIN_CHAIN']} faces (`B - A + 1 >= {r['MIN_CHAIN']}`) and every face from `A` to `B` is in the pool: "
             f"claims one die of each of those faces. Points: `{r['CHAIN_MULT']} * (A + (A+1) + ... + B)`.\n"
             f"  Every qualifying `shoal` and every qualifying `chain A-B` (all sub-ranges, not only the longest) is a legal move.\n"
             f"  The claimed dice leave the game for this turn (`dice` goes down by that many); the unclaimed dice of the pool are put back and "
             f"will be rolled again. The points are added to the turn score and the phase becomes `choice`.\n"
             f"  If `dice` is now 0 the claim is a *sweep*: the turn score gets a bonus of {r['SWEEP']} points and `dice` goes back to {r['DICE']}.\n"
             f"* **choice** (phase `choice`): legal moves are `bank` and `roll`.\n"
             f"  * `roll` rolls the available dice again (a new pool, the same rules).\n"
             f"  * `bank` adds the turn score to the diver's total; the turn passes to the other diver.\n")
    s.append("## Rounds and the end of the game\n")
    end = (f"A round is a turn of P0 followed by a turn of P1; P0 always starts. The game has {r['ROUNDS']} rounds and is over when P1's turn of round "
           f"{r['ROUNDS']} ends (banked or wrecked). The higher total wins; equal totals are a draw.")
    if r["SUDDEN"]:
        end += (f" Sudden death: as soon as a diver *banks* and their total is {r['SUDDEN']} or more, the game ends at once (even in the middle of a round) "
                f"and the totals decide as usual.")
    s.append(end + " When the game is over there are no legal moves.\n")
    s.append("## API (`reef.py`)\n")
    s.append("```python\nimport reef\n"
             "g = reef.Game(seed)        # new game\n"
             "g.legal_moves()            # list of move strings (any order); [] when the game is over\n"
             "g.apply(move)              # play a legal move, return the event text (below); ValueError otherwise, state unchanged\n"
             "g.render()                 # the board text (below)\n"
             "g.score(player)            # total of diver 0 or 1\n"
             "g.is_over()                # bool\n```\n")
    s.append("Moves are exactly these strings and nothing else is accepted (no extra spaces, no other case): `roll`, `bank`, `shoal 4`, `chain 2-5`.\n")
    s.append("### Events returned by `apply`\n")
    ev = ("* `roll`: `rolled ` followed by the sorted dice separated by single spaces, for example `rolled 1 3 3 6`; when the roll is a wreck the text "
          "ends with ` wreck`")
    ev += (", when it is a sting with ` sting`" if r["STING"] else "")
    ev += ".\n* a claim: `claimed <move> +<points>`, for example `claimed shoal 3 +18`; a sweep adds ` sweep +<bonus>` (also when the bonus is 0).\n"
    ev += "* `bank`: `banked <turn score>`" + ("; when it ends the game by sudden death the text ends with ` sudden`" if r["SUDDEN"] else "") + ".\n"
    s.append(ev)
    s.append("### `render()`\n")
    s.append("While the game is running (four lines, no trailing newline):\n\n```\nREEF round 3/%d P1 to move\ntotals P0=45 P1=62\nturn=18 dice=4 pool=1 3 3 6\nphase=claim\n```\n\n"
             "`round` is the current round, `P1 to move` the diver whose turn it is, `turn` the turn score, `dice` the dice available, `pool` the sorted pool "
             "(`-` when empty: outside the `claim` phase the pool is empty) and `phase` one of `roll`, `claim`, `choice`. When the game is over:\n\n"
             "```\nREEF over\ntotals P0=145 P1=162\nwinner P1\n```\n\n(`winner` is `P0`, `P1` or `draw`.)\n" % r["ROUNDS"])
    s.append("## Tests\n\n`python3 -m unittest discover -s tests -v` replays the scenario files in `tests/data/` (`tests/adapter.py` shows how the API is called; "
             "the format is described at the top of `tests/test_scenarios.py`).\n")
    return "\n".join(s)


# ----------------------------------------------------------------------------------------------------- families

def _variants(rng, n: int) -> list[dict]:
    seen, out = set(), []
    # a few hand-picked flavours first, then random combinations
    plan = [
        dict(),
        dict(MIN_SHOAL=3, SWEEP=40),
        dict(STING=3, DICE=7),
        dict(FINE=5, MIN_CHAIN=4, ROUNDS=6),
        dict(SUDDEN=150, CHAIN_MULT=3, DICE=5),
    ]
    while len(out) < n:
        if len(out) < len(plan):
            o = plan[len(out)]
        else:
            o = dict(DICE=rng.choice([5, 6, 7]), MIN_SHOAL=rng.choice([2, 3]), MIN_CHAIN=rng.choice([3, 4]), CHAIN_MULT=rng.choice([2, 3]),
                     SWEEP=rng.choice([0, 20, 40]), FINE=rng.choice([0, 5, 10]), STING=rng.choice([0, 3, 4]), ROUNDS=rng.choice([4, 6, 8]),
                     SUDDEN=rng.choice([0, 120, 200]))
        r = {**DEFAULT, **o}
        key = tuple(sorted(r.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _extras(r: dict) -> int:
    return (r["STING"] > 0) + (r["FINE"] > 0) + (r["SUDDEN"] > 0) + (r["MIN_SHOAL"] == 3 and r["MIN_CHAIN"] == 4)


def _blurb(r: dict) -> str:
    return f"a two-diver press-your-luck dice game with {r['DICE']} dice and an exact random number generator"


@family("games-reef-build", category="games", lang="python", kind="greenfield", n=10,
        summary="build the Reef Salvage dice engine from a README with house-rule variants and an exact LCG")
def gen_build(rng, n):
    used: list[str] = []
    for i, r in enumerate(_variants(rng, n)):
        sol = project(r)
        scripts = hidden_scripts(r)
        hidden = _kit.data_files(LANG, scripts, sol, ADAPTER)
        vis = _kit.data_files(LANG, {"examples": EXAMPLES}, sol, ADAPTER)
        start = {"README.md": readme(r), "reef.py": STUB, ".gitignore": _kit.GITIGNORE[LANG], **_scen.check_files(LANG, ADAPTER), **vis}
        d = min(4, 2 + _extras(r)) if r["ROUNDS"] != 4 else 2
        if r["STING"] and r["FINE"] and r["SUDDEN"]:
            d = 5
        prompt = _kit.green_prompt(rng, game=GAME, blurb=_blurb(r), file="reef.py", verify=_scen.VERIFY[LANG], used=used)
        slug = f"{i + 1:02d}-d{r['DICE']}-s{r['MIN_SHOAL']}c{r['MIN_CHAIN']}" + ("-sting" if r["STING"] else "") + ("-fine" if r["FINE"] else "") + ("-sudden" if r["SUDDEN"] else "")
        yield Task(slug=slug, prompt=prompt, difficulty=d, start=start, hidden=hidden, solution={"reef.py": sol["reef.py"]},
                   verify=_scen.VERIFY[LANG], tags=["dice", "rng", "scenarios"], notes={"rules": r})


BUGS = [
    Bug("chain-off-by-one", "Chains are worth too little",
        "Chains score less than the README says: the highest face of the chain is not counted. Every chain I claim is short by that face times the chain multiplier.",
        [("points = CHAIN_MULT * sum(range(a, b + 1))", "points = CHAIN_MULT * sum(range(a, b))")], difficulty=1),
    Bug("shoal-linear", "Big shoals are scored like small ones",
        "A shoal of several dice scores far less than I expect: three fives gives 15 instead of 75, and four of a kind is barely better than a pair.",
        [("points = face * count * count", "points = face * count")], difficulty=1),
    Bug("shoal-min", "A pair is not accepted as a shoal",
        "I rolled exactly as many matching dice as the shoal minimum and the game did not offer the shoal, though it offered it once I had one more matching die.",
        [("if self.pool.count(face) >= MIN_SHOAL:", "if self.pool.count(face) > MIN_SHOAL:")], difficulty=2),
    Bug("chain-min", "Shortest chains are never offered",
        "A chain with the minimum allowed number of faces is never offered as a move, only longer ones are. For example a pool with 2 3 4 should offer the chain 2-4 when three faces are enough.",
        [("for b in range(a + MIN_CHAIN - 1, 7):", "for b in range(a + MIN_CHAIN, 7):")], difficulty=2, rules=dict(MIN_CHAIN=3)),
    Bug("sweep-forgotten", "Sweep bonus is announced but never paid",
        "When I claim my last dice the event says `sweep +N` and I get my full set of dice back, but the points are not in my turn score: banking right after a sweep gives me only what I claimed.",
        [("            self.turn_score += SWEEP\n", "")], difficulty=2, rules=dict(SWEEP=25)),
    Bug("round-counter", "Games end after half the rounds",
        "Games are over much too early: the round counter on the board goes up after the first diver's turn rather than after both have played, so a game of N rounds lasts about N turns in total.",
        [("        if self.turn == 1:\n            self.round += 1", "        if self.turn == 0:\n            self.round += 1")], difficulty=2),
    Bug("rng-low-bits", "Dice don't match the published sequence",
        "The dice are wrong compared with the sequences the README promises for a given seed: with seed 1 the very first roll is not what the README says. Fixed seeds also give suspiciously regular rolls.",
        [("return 1 + (self.next() >> 16) % 6", "return 1 + self.next() % 6")], difficulty=2),
    Bug("fine-negative", "Totals can go negative",
        "After a wreck near the start of a game the fine drives my total below zero, even though the rules say a total never drops below 0.",
        [("self.totals[self.turn] = max(0, self.totals[self.turn] - FINE)", "self.totals[self.turn] = self.totals[self.turn] - FINE")], difficulty=2, rules=dict(FINE=10)),
    Bug("sting-threshold", "Urchins sting one die too late",
        "The urchin rule is off by one: with the sting limit set to N, I can roll exactly N ones and nothing happens; it only hurts me with N+1.",
        [("self.pool.count(1) >= STING", "self.pool.count(1) > STING")], difficulty=3, rules=dict(STING=3)),
    Bug("shared-totals", "A second game starts with the first game's points",
        "Starting a new Game in the same process shows the totals of the previous game: the scores only look right for the first game of a run. Everything else about the new game, including the dice, is fine.",
        [("class Game:\n    def __init__(self, seed):\n        self.rng = Rng(seed)\n        self.totals = [0, 0]\n",
          "class Game:\n    totals = [0, 0]\n\n    def __init__(self, seed):\n        self.rng = Rng(seed)\n")], difficulty=3),
    Bug("pool-unsorted", "The pool is listed in roll order",
        "The pool is not shown sorted: `rolled` events and the board list the dice in the order they were drawn, so the same dice can be written in different orders.",
        [("self.pool = sorted(self.rng.die() for _ in range(self.dice_left))", "self.pool = [self.rng.die() for _ in range(self.dice_left)]")], difficulty=2),
    Bug("bank-at-start", "You can bank before rolling",
        "At the start of a turn the game lets a diver `bank` with nothing in hand, which just skips the turn for free. It should be a mandatory roll.",
        [('        if self.phase == "roll":\n            return ["roll"]', '        if self.phase == "roll":\n            return ["bank", "roll"]')], difficulty=2),
    Bug("moves-after-end", "Moves are still offered after the game is over",
        "Once the game is over the engine still lists legal moves and lets me keep rolling; the board says the game is over but `legal_moves()` isn't empty.",
        [("        if self.over:\n            return []\n", "")], difficulty=3),
    Bug("sudden-boundary", "Sudden death needs one point too many",
        "In the sudden-death rule a diver who banks exactly the target total does not end the game; they have to pass it by at least one point.",
        [("self.totals[self.turn] >= SUDDEN", "self.totals[self.turn] > SUDDEN")], difficulty=3, rules=dict(SUDDEN=60)),
]


@family("games-reef-fix", category="games", lang="python", kind="fix", n=18,
        summary="hand-injected defects in the Reef Salvage engine (scoring, rules, rounds, RNG, shared state), some several at once")
def gen_fix(rng, n):
    used: list[str] = []
    cache = {}
    bugs = BUGS_ALL[:n]
    for k, bug in enumerate(bugs):
        r = {**DEFAULT, **bug.rules}
        key = tuple(sorted(r.items()))
        if key not in cache:
            sol = project(r)
            cache[key] = (sol, _kit.data_files(LANG, hidden_scripts(r), sol, ADAPTER), _kit.data_files(LANG, {"examples": EXAMPLES}, sol, ADAPTER))
        sol, hidden, vis = cache[key]
        base = {**sol, "README.md": readme(r)}
        tests = {**_scen.check_files(LANG, ADAPTER), **vis}
        ctx = {"files": ["reef.py"], "verify": _scen.VERIFY[LANG]}
        yield _kit.bug_task(game=GAME, lang=LANG, base_files=base, tests=tests, hidden=hidden, bug=bug, ctx=ctx, rng=rng, used=used, k=k,
                            tags=["dice", "rng"], extra_notes={"rules": r})


# ----------------------------------------------------------------------------------------------------- combined defects

_B = {b.id: b for b in BUGS}
COMBOS = [
    _kit.combine(_B["chain-min"], _B["sweep-forgotten"], difficulty=4),
    _kit.combine(_B["round-counter"], _B["shoal-linear"], _B["pool-unsorted"], difficulty=4),
    _kit.combine(_B["fine-negative"], _B["sting-threshold"], difficulty=4),
    _kit.combine(_B["shared-totals"], _B["moves-after-end"], _B["sudden-boundary"], _B["bank-at-start"], difficulty=5),
]
BUGS_ALL = BUGS + COMBOS


# ----------------------------------------------------------------------------------------------------- feature: undo, redo, replay

_SNAP = '''
    def _snapshot(self):
        return (self.rng.state, list(self.totals), self.round, self.turn, self.over, self.turn_score, self.dice_left, list(self.pool), self.phase)

    def _restore(self, snap):
        state, totals, self.round, self.turn, self.over, self.turn_score, self.dice_left, pool, self.phase = snap
        self.rng.state = state
        self.totals = list(totals)
        self.pool = list(pool)
'''

_PUSH_EDIT = ('            raise ValueError("illegal move: %r" % (move,))\n',
              '            raise ValueError("illegal move: %r" % (move,))\n        self._undo.append((move, self._snapshot()))\n')
_INIT_EDIT = ("        self.over = False\n        self._new_turn()\n", "        self.over = False\n        self._undo = []\n        self._new_turn()\n")


def _edit(src: str, *pairs: tuple[str, str]) -> str:
    for old, new in pairs:
        if src.count(old) != 1:
            raise RuntimeError(f"edit target occurs {src.count(old)} times: {old!r}")
        src = src.replace(old, new)
    return src


def _adapter(*verbs: str) -> dict[str, str]:
    a = ADAPTER["tests/adapter.py"]
    blocks = {
        "undo": '''            if verb == "undo":                    # undo: "undone <move>" or "error: <message>"
                try:
                    return "undone " + self.game.undo()
                except ValueError as e:
                    return "error: " + str(e)
''',
        "redo": '''            if verb == "redo":                    # redo: the event text or "error: <message>"
                try:
                    return self.game.redo()
                except ValueError as e:
                    return "error: " + str(e)
''',
        "history": '''            if verb == "history":                 # the applied moves joined by ";" ("-" when none)
                return ";".join(self.game.history()) or "-"
''',
        "replay": '''            if verb == "replay":                  # replay <seed> <moves joined by ";">
                seed, _, rest = args.partition(" ")
                try:
                    self.game = reef.replay(int(seed), rest.split(";") if rest else [])
                    return "ok"
                except ValueError as e:
                    return "error: " + str(e)
''',
    }
    add = "".join(blocks[v] for v in verbs)
    add = "".join(line[4:] + "\n" for line in add.split("\n") if line)
    target = "        raise KeyError(verb)\n"
    assert a.count(target) == 1
    return {"tests/adapter.py": a.replace(target, add + target)}


def _times(verb: str, k: int) -> str:
    return "\n".join([f"> {verb}"] * k)


def _walk(seed: int, n: int, undos: int, tail: str = "") -> str:
    return f"> new {seed}\n~ rand {n} {seed * 7 + 1} emit=render\n{_times('undo', undos)}\n> render\n{tail}"


def undo_variants(r: dict) -> list[dict]:
    snap_methods = _SNAP
    v = []
    # 1. unlimited undo
    v.append(dict(
        key="undo-all", d=3, verbs=("undo",),
        title="Take-backs",
        ask=("Players at our table keep asking for a take-back button. Add `Game.undo()` to the engine as specified in the new section of README.md. "
             "The tricky part is the dice: after a take-back the same move has to produce the same dice again."),
        readme=("A diver who misclicks wants the move back. `g.undo()` takes back the most recently applied move and returns that move (the string). "
                "Calling it repeatedly walks back one move at a time, all the way to the start of the game, across turns and rounds, and even past the end "
                "of a finished game. The whole game state returns to exactly what it was *before* the move: totals, round, whose turn, turn score, dice "
                "available, pool, phase, whether the game is over, and the random generator, so that applying the same move again gives the identical "
                "event text and dice. Moves that were rejected as illegal are not part of the history. With nothing to take back, `undo()` raises "
                "`ValueError(\"nothing to undo\")`."),
        edits=[_INIT_EDIT, _PUSH_EDIT],
        append=snap_methods + '''
    def undo(self):
        if not self._undo:
            raise ValueError("nothing to undo")
        move, snap = self._undo.pop()
        self._restore(snap)
        return move
''',
        vis="# scenario take back a roll\n> new 3\n> do roll\n> render\n> undo\n> render\n> do roll\n> undo\n> undo\n",
        hid=lambda: {
            "hidden_undo": "\n".join([
                "# scenario walk back through a whole game", _walk(2, 60, 70), "> new 2\n~ rand 700 15 emit=over\n" + _times("undo", 3) + "\n> render\n> over\n> legal",
                "# scenario undo then replay gives the same dice", "> new 41\n> do roll\n> do roll\n> undo\n> do roll\n> render\n> undo\n> undo\n> undo\n> do roll\n> render",
                "# scenario undo restores wreck and claims", _walk(9, 30, 5, "~ rand 5 3 emit=render\n" + _times("undo", 9) + "\n> render"),
                "# scenario illegal moves are not in the history", "> new 8\n> do bank\n> undo\n> do roll\n> do bank\n> do roll\n> undo\n> undo\n> undo\n> render",
                "# scenario undo after an undo of the final move", "> new 6\n~ rand 900 2 emit=over\n> undo\n> legal\n> render\n> over\n> undo\n> render",
            ]) + "\n"}))
    # 2. undo within the turn
    v.append(dict(
        key="undo-turn", d=3, verbs=("undo",),
        title="Take-backs within a turn",
        ask=("Add a take-back to the Reef engine, but a fair one: a diver may only take back moves of their *current* turn. The exact rules are in the new "
             "section of README.md; the engine is `reef.py`."),
        readme=("`g.undo()` takes back the most recently applied move of the *current turn* and returns that move (the string). Repeated calls walk back "
                "to the start of the turn but no further: as soon as a turn ends (a `bank`, a wreck, a sting, or the end of the game) the history is cleared, "
                "so a move that ended a turn can never be taken back. The whole game state returns to exactly what it was before the move, including the "
                "random generator (applying the same move again gives the identical event text and dice). Rejected moves are not part of the history. With "
                "nothing to take back `undo()` raises `ValueError(\"nothing to undo\")`."),
        edits=[_INIT_EDIT, _PUSH_EDIT, ("        self.turn_score = 0\n        self.dice_left = DICE\n        self.pool = []\n        self.phase = \"roll\"\n",
                                        "        self.turn_score = 0\n        self.dice_left = DICE\n        self.pool = []\n        self.phase = \"roll\"\n        self._undo = []\n")],
        append=snap_methods + '''
    def undo(self):
        if not self._undo:
            raise ValueError("nothing to undo")
        move, snap = self._undo.pop()
        self._restore(snap)
        return move
''',
        vis="# scenario take back inside a turn\n> new 3\n> do roll\n> undo\n> undo\n> do roll\n> render\n",
        hid=lambda: {
            "hidden_undo": "\n".join([
                "# scenario walk back inside a turn", "> new 2\n> do roll\n> legal\n> undo\n> render\n> undo\n> do roll\n> render",
                "# scenario history clears when the turn ends", "> new 5\n~ rand 400 9 every=1 emit=render\n" + _times("undo", 3) + "\n> render",
                "# scenario many games", *[f"> new {s}\n~ rand 120 {s + 3} emit=render\n{_times('undo', 6)}\n> render\n> legal" for s in (1, 4, 17, 30, 31)],
                "# scenario bank cannot be undone", "> new 7\n> do roll\n> legal\n~ rand 6 2 emit=render\n> do bank\n> undo\n> render",
                "# scenario rejected moves", "> new 8\n> do bank\n> undo\n> do roll\n> do bank\n> undo\n> undo\n> undo\n",
                "# scenario end of game", "> new 6\n~ rand 900 2 emit=over\n> undo\n> render\n> legal",
            ]) + "\n"}))
    # 3. undo and redo
    v.append(dict(
        key="undo-redo", d=4, verbs=("undo", "redo"),
        title="Undo and redo",
        ask=("We want an undo/redo pair on the Reef engine, like in an editor: `undo()` walks back, `redo()` walks forward again, and any new move forgets the "
             "forward history. README.md has a section with every detail (return values, error texts, what exactly is restored)."),
        readme=("`g.undo()` and `g.redo()` work like undo/redo in an editor.\n\n"
                "* `undo()` takes back the most recently applied move (back to the start of the game, across turns, even past the end of a finished game) and "
                "returns that move (the string). The complete state returns to what it was before the move, including the random generator.\n"
                "* `redo()` plays again the move most recently taken back, exactly as if it were applied with `apply`, and returns its event text. Because "
                "the generator was restored, the event text is the one the move originally produced.\n"
                "* Any *successful* `apply` clears the redo history; a rejected move does not touch undo or redo history.\n"
                "* With nothing to take back `undo()` raises `ValueError(\"nothing to undo\")`; with nothing to replay `redo()` raises `ValueError(\"nothing to redo\")`."),
        edits=[_INIT_EDIT.__class__(("        self.over = False\n        self._new_turn()\n", "        self.over = False\n        self._undo = []\n        self._redo = []\n        self._new_turn()\n")),
               ("    def apply(self, move):\n", "    def apply(self, move):\n        event = self._apply(move)\n        self._redo = []\n        return event\n\n    def _apply(self, move):\n"), _PUSH_EDIT],
        append=snap_methods + '''
    def undo(self):
        if not self._undo:
            raise ValueError("nothing to undo")
        move, snap = self._undo.pop()
        self._restore(snap)
        self._redo.append(move)
        return move

    def redo(self):
        if not self._redo:
            raise ValueError("nothing to redo")
        return self._apply(self._redo.pop())
''',
        vis="# scenario undo and redo\n> new 3\n> do roll\n> render\n> undo\n> redo\n> render\n> redo\n> undo\n> undo\n",
        hid=lambda: {
            "hidden_undo": "\n".join([
                "# scenario redo gives the same event", "> new 41\n> do roll\n> undo\n> redo\n> undo\n> do roll\n> redo\n> render",
                "# scenario a new move clears redo", "> new 5\n~ rand 8 3 emit=render\n" + _times("undo", 4) + "\n> redo\n> do roll\n> redo\n> render\n> legal",
                "# scenario walk back and forward", "> new 2\n~ rand 60 4 emit=render\n" + _times("undo", 30) + "\n" + _times("redo", 31) + "\n> render\n" + _times("undo", 80) + "\n> render\n" + _times("redo", 80) + "\n> render",
                "# scenario rejected moves keep redo", "> new 8\n> do roll\n> undo\n> do bank\n> do shoal 9\n> redo\n> render",
                "# scenario past the end of the game", "> new 6\n~ rand 900 2 emit=over\n> undo\n> undo\n> render\n> redo\n> render\n> redo\n> over\n> undo\n> redo",
                "# scenario many games", *[f"> new {s}\n~ rand 90 {s + 3} emit=render\n{_times('undo', 25)}\n{_times('redo', 10)}\n> render\n> legal\n~ rand 10 {s} emit=render\n> redo" for s in (1, 4, 17)],
            ]) + "\n"}))
    # 4. tokens
    v.append(dict(
        key="undo-tokens", d=4, verbs=("undo",),
        title="Take-backs with a budget",
        ask=("Implement the 'undo tokens' house rule in the Reef engine: take-backs inside the current turn, paid for with two tokens per diver per game, and a fifth "
             "line on the board that shows the tokens. All of it is described in the new section of README.md."),
        readme=("Each diver starts the game with 2 *undo tokens*. `g.undo()` takes back the most recently applied move of the *current turn* (a turn's history ends "
                "when the turn ends: after a `bank`, a wreck, a sting or the end of the game nothing can be taken back) and returns that move (the string). The "
                "whole state returns to what it was before the move, including the random generator. A successful `undo()` costs the diver whose turn it is one token; "
                "tokens are never refunded. Errors (state unchanged), checked in this order: with nothing to take back `ValueError(\"nothing to undo\")`; with no token "
                "left `ValueError(\"no undo tokens left\")`.\n\n"
                "`render()` gets a fifth line, in the running and in the finished state alike: `undos P0=2 P1=2` (the tokens left; no trailing newline)."),
        edits=[("        self.over = False\n        self._new_turn()\n", "        self.over = False\n        self._undo = []\n        self._tokens = [2, 2]\n        self._new_turn()\n"),
               _PUSH_EDIT, ("        self.turn_score = 0\n        self.dice_left = DICE\n        self.pool = []\n        self.phase = \"roll\"\n",
                            "        self.turn_score = 0\n        self.dice_left = DICE\n        self.pool = []\n        self.phase = \"roll\"\n        self._undo = []\n"),
               ("    def render(self):\n", "    def render(self):\n        return self._render() + \"\\nundos P0=%d P1=%d\" % tuple(self._tokens)\n\n    def _render(self):\n")],
        append=snap_methods + '''
    def undo(self):
        if not self._undo:
            raise ValueError("nothing to undo")
        if self._tokens[self.turn] == 0:
            raise ValueError("no undo tokens left")
        who = self.turn
        move, snap = self._undo.pop()
        self._restore(snap)
        self._tokens[who] -= 1
        return move
''',
        vis="# scenario tokens\n> new 3\n> do roll\n> render\n> undo\n> render\n> undo\n> do roll\n> undo\n> undo\n> render\n",
        hid=lambda: {
            "hidden_undo": "\n".join([
                "# scenario spend both tokens", "> new 2\n> do roll\n> legal\n> undo\n> do roll\n> undo\n> do roll\n> undo\n> render\n> do roll\n> render",
                "# scenario tokens per diver", "> new 5\n~ rand 400 9 every=1 emit=render\n" + _times("undo", 4) + "\n> render",
                "# scenario many games", *[f"> new {s}\n~ rand 150 {s + 3} every=15 emit=render\n{_times('undo', 6)}\n> render\n> legal" for s in (1, 4, 17, 30, 31, 63)],
                "# scenario precedence of errors", "> new 7\n> undo\n> do roll\n> undo\n> do roll\n> undo\n> do roll\n> undo\n> do roll\n> undo\n> render",
                "# scenario end of game", "> new 6\n~ rand 900 2 emit=over\n> undo\n> render\n> scores",
            ]) + "\n"}))
    # 5. history and replay
    v.append(dict(
        key="history-replay", d=3, verbs=("history", "replay"),
        title="Move history and replay",
        ask=("The tournament organisers want to store games as `(seed, moves)` and replay them. Add `Game.history()` and a module-level `reef.replay(seed, moves)` to the "
             "engine, as described in README.md (including the exact error text for a bad move)."),
        readme=("Games can be stored as a seed plus the list of moves that were applied.\n\n"
                "* `g.history()` returns a new list with every move successfully applied so far, in order (including the move that ended the game). Rejected moves are not recorded.\n"
                "* `reef.replay(seed, moves)` creates `Game(seed)`, applies `moves` in order and returns the game. If a move is illegal at its turn it raises "
                "`ValueError(\"illegal move at index %d: %s\" % (i, move))` where `i` is the 0-based index of the offending move and `move` is the string as given; a "
                "wrong move therefore reports the *first* bad index. The replayed game's `history()` equals `moves`."),
        edits=[("        self.over = False\n        self._new_turn()\n", "        self.over = False\n        self._log = []\n        self._new_turn()\n"),
               ('            raise ValueError("illegal move: %r" % (move,))\n', '            raise ValueError("illegal move: %r" % (move,))\n        self._log.append(move)\n')],
        append='''
    def history(self):
        return list(self._log)


def replay(seed, moves):
    game = Game(seed)
    for i, move in enumerate(moves):
        try:
            game.apply(move)
        except ValueError:
            raise ValueError("illegal move at index %d: %s" % (i, move))
    return game
''',
        vis="# scenario history\n> new 3\n> do roll\n> do bank\n> history\n> replay 3 roll\n> render\n> replay 3 roll;bank;roll\n",
        hid=lambda: {
            "hidden_replay": "\n".join([
                "# scenario history follows the moves", "> new 4\n> history\n~ rand 25 6 emit=history\n> do bank\n> do roll\n> history",
                "# scenario replay reproduces a game", "> new 12\n~ rand 700 5 emit=render\n> history\n> render\n",
                "# scenario replay errors", "> new 1\n> replay 3 roll;bank\n> replay 3 roll;roll\n> replay 3 bank\n> replay 5 roll;shoal 9\n> render\n> replay 3 \n> history\n> replay 3 roll;do roll",
                "# scenario replay of a finished game", "> new 6\n~ rand 900 2 emit=over\n> history\n> render\n> replay 6 roll;roll\n> over",
            ]) + "\n"}))
    return v


def _replay_scripts(seed_games: list[int], r: dict) -> None:
    return None


@family("games-reef-undo", category="games", lang="python", kind="feature", n=5,
        summary="add take-backs, undo/redo, undo tokens or move history and replay to the Reef Salvage engine")
def gen_undo(rng, n):
    used: list[str] = []
    rule_sets = [{}, dict(STING=3), dict(FINE=5, DICE=5), dict(MIN_SHOAL=3, SWEEP=40), dict(SUDDEN=150, ROUNDS=6)]
    for i, var in enumerate(undo_variants({**DEFAULT})[:n]):
        r = {**DEFAULT, **rule_sets[i % len(rule_sets)]}
        var = undo_variants(r)[i]
        base_src = engine(r)
        edited = _edit(base_src, *var["edits"]) + var["append"]
        adapter = _adapter(*var["verbs"])
        sol = {"reef.py": edited, ".gitignore": _kit.GITIGNORE[LANG]}
        hid_scripts = {**hidden_scripts(r)}
        hid_scripts.update(var["hid"]())
        hidden = _kit.data_files(LANG, hid_scripts, sol, adapter)
        vis = _kit.data_files(LANG, {"examples": EXAMPLES, "feature": var["vis"]}, sol, adapter)
        section = f"\n## Feature to add: {var['title'].lower()}\n\n{var['readme']}\n"
        verbs_doc = {
            "undo": "`undo` replies `undone <move>` or `error: <message>`",
            "redo": "`redo` replies with the event text or `error: <message>`",
            "history": "`history` replies with the moves joined by `;` (`-` when empty)",
            "replay": "`replay <seed> <moves joined by ;>` replaces the game and replies `ok` or `error: <message>`",
        }
        section += "\nThe scenario adapter (`tests/adapter.py`) already knows the new commands: " + "; ".join(verbs_doc[x] for x in var["verbs"]) + ".\n"
        start = {"README.md": readme(r).replace("## Tests\n", section.lstrip("\n") + "\n## Tests\n"), "reef.py": project(r)["reef.py"], ".gitignore": _kit.GITIGNORE[LANG],
                 **_scen.check_files(LANG, adapter), **vis}
        prompt = var["ask"]
        if i % 2:
            prompt += " Keep everything the engine already does exactly as it is."
        yield Task(slug=f"{i + 1:02d}-{var['key']}", prompt=prompt, difficulty=var["d"], start=start, hidden=hidden,
                   solution={"reef.py": edited}, verify=_scen.VERIFY[LANG], tags=["undo", "state", "rng"], notes={"rules": r, "variant": var["key"]})


# ----------------------------------------------------------------------------------------------------- bot tournament

ARENA = dd('''
    """Local arena for Reef Salvage bots.

        python3 arena.py [--games N] [--first-seed S]

    Plays `bot.choose` against `baseline.choose` on the real engine. Every seed is played twice, once with the bot as P0 and once as P1.
    """
    import argparse
    import random

    import baseline
    import bot
    import reef

    MAX_MOVES = 2000  # a game that lasts longer than this is a forfeit of the diver to move


    def view(game):
        """What a policy gets to see: a plain dict (a fresh copy on every call)."""
        return {
            "me": game.turn,
            "phase": game.phase,
            "legal": sorted(game.legal_moves()),
            "pool": list(game.pool),
            "dice": game.dice_left,
            "turn": game.turn_score,
            "totals": list(game.totals),
            "round": game.round,
            "rounds": reef.ROUNDS,
        }


    def play(policies, seed):
        """Play one game; policies[0] is P0 and policies[1] is P1. Python's global `random` is seeded with `seed` first.
        Returns (totals, forfeit): `forfeit` is the diver (0 or 1) whose policy raised, returned an illegal move or ran
        past MAX_MOVES, otherwise None. A forfeit loses the game."""
        random.seed(seed)
        game = reef.Game(seed)
        for _ in range(MAX_MOVES):
            if game.is_over():
                return list(game.totals), None
            who = game.turn
            try:
                game.apply(policies[who](view(game)))
            except Exception:  # noqa: BLE001 - a crashing bot forfeits
                return list(game.totals), who
        return list(game.totals), game.turn


    def result_for(seat, totals, forfeit):
        """1 for a win of `seat`, 0.5 for a draw, 0 for a loss."""
        if forfeit is not None:
            return 0.0 if forfeit == seat else 1.0
        mine, theirs = totals[seat], totals[1 - seat]
        return 1.0 if mine > theirs else 0.5 if mine == theirs else 0.0


    def win_rate(bot_choose, opponent_choose, seeds):
        points = 0.0
        for seed in seeds:
            totals, forfeit = play([bot_choose, opponent_choose], seed)
            points += result_for(0, totals, forfeit)
            totals, forfeit = play([opponent_choose, bot_choose], seed)
            points += result_for(1, totals, forfeit)
        return points / (2 * len(seeds))


    if __name__ == "__main__":
        ap = argparse.ArgumentParser()
        ap.add_argument("--games", type=int, default=100, help="number of seeds (each is played twice)")
        ap.add_argument("--first-seed", type=int, default=1)
        args = ap.parse_args()
        seeds = range(args.first_seed, args.first_seed + args.games)
        print("win rate of bot.py against baseline.py: %.3f over %d games" % (win_rate(bot.choose, baseline.choose, seeds), 2 * args.games))
''')

OPPONENTS = {
    "gambler45": ("The *gambler* claims the highest-scoring set and banks only once the turn score is 45 or more.",
                  '''
    def choose(view):
        legal = view["legal"]
        if view["phase"] == "claim":
            return max(legal, key=lambda move: (points(move, view["pool"]), move))
        if view["phase"] == "choice":
            return "bank" if view["turn"] >= 45 else "roll"
        return "roll"
'''),
    "banker": ("The *banker* claims the highest-scoring set and banks at the first opportunity (right after its first claim of every turn).",
               '''
    def choose(view):
        legal = view["legal"]
        if view["phase"] == "claim":
            return max(legal, key=lambda move: (points(move, view["pool"]), move))
        if view["phase"] == "choice":
            return "bank"
        return "roll"
'''),
    "random": ("The *drifter* picks a uniformly random legal move (`random.choice(view[\"legal\"])`; the arena seeds `random`, so games are reproducible).",
               '''
    def choose(view):
        return random.choice(view["legal"])
'''),
}


def baseline_source(r: dict, key: str) -> str:
    helper = dd(f'''
        """The opponent your bot is measured against."""
        import random

        CHAIN_MULT = {r["CHAIN_MULT"]}


        def points(move, pool):
            """Points of a claim (`shoal F` / `chain A-B`) from the given pool."""
            kind, arg = move.split(" ")
            if kind == "shoal":
                face = int(arg)
                count = pool.count(face)
                return face * count * count
            a, b = (int(x) for x in arg.split("-"))
            return CHAIN_MULT * sum(range(a, b + 1))

    ''')
    return helper + "\n" + dd(OPPONENTS[key][1])


GOLD_BOT = dd('''
    """A reasonable Reef Salvage policy: take the claim that is worth the most per die spent and bank earlier when few dice are left."""
    import reef


    def points(move, pool):
        kind, arg = move.split(" ")
        if kind == "shoal":
            face = int(arg)
            count = pool.count(face)
            return face * count * count, count
        a, b = (int(x) for x in arg.split("-"))
        return reef.CHAIN_MULT * sum(range(a, b + 1)), b - a + 1


    def choose(view):
        legal = view["legal"]
        if view["phase"] == "claim":
            def value(move):
                pts, used = points(move, view["pool"])
                return (pts - 4 * used, move)
            return max(legal, key=value)
        if view["phase"] == "choice":
            return "bank" if view["turn"] >= 8 + 6 * view["dice"] else "roll"
        return "roll"
''')

BOT_STUB = dd('''
    """Your Reef Salvage policy. `choose(view)` is called for every decision of your diver and must return one of `view["legal"]`."""


    def choose(view):
        return view["legal"][-1]
''')

SCORE_PY = dd('''
    import json
    import sys

    sys.path.insert(0, ".")
    import arena  # noqa: E402
    import baseline  # noqa: E402
    import bot  # noqa: E402

    SEEDS = range(70001, 70001 + 250)
    FLOOR, GOAL = 0.5, @@GOAL@@

    rate = arena.win_rate(bot.choose, baseline.choose, SEEDS)
    print("games %d, win rate %.3f (goal %.2f)" % (2 * len(SEEDS), rate, GOAL))
    print(json.dumps({"score": round(max(0.0, min(1.0, (rate - FLOOR) / (GOAL - FLOOR))), 4)}))
''')

BOT_VARIANTS = [
    dict(rules={}, opp="gambler45", goal=0.70, d=2),
    dict(rules=dict(STING=3, DICE=7), opp="random", goal=0.80, d=2),
    dict(rules={}, opp="banker", goal=0.64, d=3),
    dict(rules=dict(FINE=10, MIN_SHOAL=3), opp="gambler45", goal=0.68, d=3),
    dict(rules=dict(SUDDEN=150, DICE=5, CHAIN_MULT=3), opp="gambler45", goal=0.64, d=3),
    dict(rules=dict(MIN_SHOAL=3, MIN_CHAIN=4, SWEEP=40, ROUNDS=6), opp="random", goal=0.70, d=2),
]


def bot_readme(r: dict, opp: str, goal: float) -> str:
    return readme(r).replace("## Tests\n", dd(f'''
        ## Your task: a bot

        `bot.py` has to define `choose(view)`, called for every decision of your diver. `view` is a dict:

        | key | meaning |
        |---|---|
        | `me` | your seat, 0 or 1 |
        | `phase` | `roll`, `claim` or `choice` |
        | `legal` | the sorted legal moves (what `legal_moves()` returns) |
        | `pool` | the sorted dice of the current roll (empty outside `claim`) |
        | `dice` | dice available this turn |
        | `turn` | the turn score so far |
        | `totals` | `[P0 total, P1 total]` |
        | `round`, `rounds` | the current round and the number of rounds |

        `choose` returns one of the strings in `view["legal"]`. A bot that raises an exception, returns anything else or takes more than {2000} moves in one game
        forfeits that game (it counts as a loss).

        `arena.py` is the referee. `python3 arena.py --games 100` plays your bot against the opponent (`baseline.py`) on the real engine; every seed is played twice, once
        on each seat, and a win counts 1, a draw 0.5. The arena seeds Python's `random` with the game seed before every game, so a bot that uses `random` is
        still reproducible. Do not edit `reef.py`, `arena.py` or `baseline.py`.

        Opponent: {OPPONENTS[opp][0]} Its code is `baseline.py`.

        ## Scoring

        The check plays 500 games (250 fresh seeds, both seats) against the opponent. With `rate` your win rate the score is
        `clamp((rate - 0.5) / ({goal:.2f} - 0.5), 0, 1)`: 0 when you only match a coin flip, 1.0 from a win rate of {goal:.2f} on.

        ## Tests
    '''), 1)


@family("games-reef-bot", category="games", lang="python", kind="greenfield", n=6,
        summary="write a Reef Salvage bot that beats a baseline opponent in a seeded tournament (json-score)")
def gen_bot(rng, n):
    used: list[str] = []
    for i, v in enumerate(BOT_VARIANTS[:n]):
        r = {**DEFAULT, **v["rules"]}
        eng = engine(r)
        files = {"reef.py": eng, "arena.py": ARENA, "baseline.py": baseline_source(r, v["opp"]), ".gitignore": _kit.GITIGNORE[LANG]}
        start = {**files, "bot.py": BOT_STUB, "README.md": bot_readme(r, v["opp"], v["goal"])}
        hidden = {".check/score.py": SCORE_PY.replace("@@GOAL@@", repr(v["goal"]))}
        voices = [
            "I'd like a bot for our Reef Salvage table that can hold its own against the house opponent. The rules, the `view` dict your policy receives and the way the tournament is scored are in README.md; write `choose` in `bot.py`.",
            "Write the policy for a Reef Salvage player in `bot.py`. It will be scored by a seeded tournament against `baseline.py`: see README.md for the interface and for how the win rate becomes a score. A higher win rate is better, and the full score is reachable with a sensible strategy.",
            "Our Reef Salvage house opponent is too easy to be fun. Before we replace it, I want a bot that reliably beats it. Everything you need (rules, the view, scoring) is in README.md, `arena.py` lets you test locally. Put your policy in `bot.py`.",
            "`bot.py` plays Reef Salvage badly: it always takes the last legal move, which means it keeps rolling and never banks. Replace it with a real strategy (claims, when to bank) so that it wins clearly against the opponent in `baseline.py`. README.md explains the tournament.",
        ]
        prompt = voices[i % len(voices)]
        s0, s1, out = _kit.check_scores(start=start, hidden=hidden, solution={"bot.py": GOLD_BOT}, verify="python3 .check/score.py", name=f"reef-bot-{i}")
        v["_note"] = out.strip().splitlines()[-2]
        yield Task(slug=f"{i + 1:02d}-vs-{v['opp']}", prompt=prompt, difficulty=v["d"], start=start, hidden=hidden, solution={"bot.py": GOLD_BOT},
                   verify="python3 .check/score.py", pass_mode="json-score", protected=["reef.py", "arena.py", "baseline.py"],
                   tags=["bot", "tournament", "strategy"], notes={"rules": r, "opponent": v["opp"], "goal": v["goal"], "gold": v["_note"], "stub_score": s0})
