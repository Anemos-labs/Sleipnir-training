"""Spindle (python): a rack-and-bag word game with an invented scoring system (letter values, length multipliers, echo and
spindle bonuses), seeded draws and a best-play search. Build, fix and bot-tournament tasks."""
from __future__ import annotations

import json
import types

from fx import Task, dd, family

from . import _kit, _scen
from ._kit import Bug

LANG = "python"
GAME = "Spindle"
CONSONANTS = "bdgklmnprst"


def make_rules(rng, variant: int) -> dict:
    cons = sorted(rng.sample(CONSONANTS, 7))
    counts = {}
    for v in "aeiou":
        counts[v] = rng.randint(4, 6)
    for c in cons:
        counts[c] = rng.randint(2, 4)
    values = {v: 1 for v in "aeiou"}
    for c in cons:
        values[c] = rng.randint(1, 4)
    mult = {3: 1, 4: 2, 5: 3, 6: 5, 7: 8}
    if variant % 3 == 1:
        mult = {3: 1, 4: 2, 5: 4, 6: 6, 7: 9}
    if variant % 3 == 2:
        mult = {3: 2, 4: 3, 5: 4, 6: 6, 7: 10}
    return dict(COUNTS=dict(sorted(counts.items())), VALUES=dict(sorted(values.items())), MULT=mult, SPINDLE=rng.choice([25, 30, 40]), ECHO=rng.choice([0, 4, 6]),
                TURNS=rng.choice([8, 10, 12]))


def make_words(rng, rules: dict, n: int = 420) -> list[str]:
    letters = sorted(rules["COUNTS"])
    vow = [c for c in letters if c in "aeiou"]
    con = [c for c in letters if c not in "aeiou"]
    pats = ["CVC", "CVCC", "CVCV", "VCV", "CCVC", "CVCVC", "CVCCV", "VCVC", "CVVC", "CVCVCV", "VCCVC", "CCVCV", "CVCCVC", "CVCVCC"]
    out = set()
    while len(out) < n:
        pat = rng.choice(pats)
        w = "".join(rng.choice(vow if ch == "V" else con) for ch in pat)
        if rng.randrange(8) == 0:  # a doubled letter somewhere, for the echo bonus
            i = rng.randrange(len(w))
            w = w[: i + 1] + w[i] + w[i + 1:]
        if 3 <= len(w) <= 7:
            out.add(w)
    return sorted(out)


def header(rules: dict) -> str:
    return (f"# ---- house rules for this table (they are part of the specification, see README.md) ----\n"
            f"COUNTS = {rules['COUNTS']!r}\nVALUES = {rules['VALUES']!r}\nMULT = {rules['MULT']!r}\nSPINDLE_BONUS = {rules['SPINDLE']}\nECHO_BONUS = {rules['ECHO']}\n"
            f"RACK_SIZE = 7\nMAX_TURNS = {rules['TURNS']}\n# --------------------------------------------------------------------------------------\n")


BODY = dd('''
    MIN_LENGTH = 3


    def points(word):
        """Points of a word (it is not checked against any rack or dictionary)."""
        base = sum(VALUES[c] for c in word)
        total = base * MULT[len(word)]
        total += ECHO_BONUS * sum(1 for a, b in zip(word, word[1:]) if a == b)
        if len(word) == RACK_SIZE:
            total += SPINDLE_BONUS
        return total


    def formable(word, rack):
        """True if the word can be spelled with the tiles of the rack (a string or list of letters)."""
        left = list(rack)
        for c in word:
            if c not in left:
                return False
            left.remove(c)
        return True


    def best_play(rack, words):
        """(word, points) of the best word that can be played from the rack, or None."""
        best = None
        for w in words:
            if len(w) < MIN_LENGTH or not formable(w, rack):
                continue
            key = (points(w), len(w))
            if best is None or key > best[0] or (key == best[0] and w < best[1]):
                best = (key, w)
        return None if best is None else (best[1], best[0][0])


    class Game:
        def __init__(self, seed, words):
            self.state = seed & 0x7FFFFFFF
            self.words = frozenset(words)
            self.bag = [ch for ch in sorted(COUNTS) for _ in range(COUNTS[ch])]
            self.rack = []
            self.score = 0
            self.turn = 1
            self._refill()

        def _next(self):
            self.state = (self.state * 1103515245 + 12345) & 0x7FFFFFFF
            return self.state

        def _refill(self):
            while len(self.rack) < RACK_SIZE and self.bag:
                self.rack.append(self.bag.pop((self._next() >> 8) % len(self.bag)))
            self.rack.sort()

        def is_over(self):
            return self.turn > MAX_TURNS or not self.rack

        def play(self, word):
            if self.is_over():
                raise ValueError("game over")
            if len(word) < MIN_LENGTH:
                raise ValueError("too short")
            if word not in self.words:
                raise ValueError("not in dictionary")
            if not formable(word, self.rack):
                raise ValueError("not on the rack")
            for c in word:
                self.rack.remove(c)
            gained = points(word)
            self.score += gained
            self.turn += 1
            self._refill()
            return gained

        def skip(self):
            if self.is_over():
                raise ValueError("game over")
            self.rack = []
            self.turn += 1
            self._refill()

        def render(self):
            head = "turn %d/%d score %d bag %d" % (min(self.turn, MAX_TURNS), MAX_TURNS, self.score, len(self.bag))
            if self.is_over():
                head += " GAME OVER"
            return head + "\\nrack: " + " ".join(self.rack)
''')

BODY_NO_BEST = BODY.replace(BODY[BODY.index("def best_play"):BODY.index("class Game:")], "")


def engine(rules: dict, with_best: bool = True) -> str:
    return '"""Spindle: a word game with a rack and a bag. The rules are in README.md."""\n\n' + header(rules) + "\n\n" + (BODY if with_best else BODY_NO_BEST)


STUB = dd('''
    """Spindle: a word game with a rack and a bag. The rules and the API are in README.md."""


    def points(word):
        raise NotImplementedError


    def formable(word, rack):
        raise NotImplementedError


    def best_play(rack, words):
        raise NotImplementedError


    class Game:
        def __init__(self, seed, words):
            raise NotImplementedError

        def is_over(self):
            raise NotImplementedError

        def play(self, word):
            raise NotImplementedError

        def skip(self):
            raise NotImplementedError

        def render(self):
            raise NotImplementedError
''')

ADAPTER = {"tests/adapter.py": dd('''
    """Maps scenario commands onto the engine API (the scenario runner is tests/test_scenarios.py)."""
    import spindle

    with open("words.txt", encoding="utf-8") as f:
        WORDS = f.read().split()


    class Adapter:
        def __init__(self):
            self.game = None
            self.words = list(WORDS)

        def run(self, verb, args):
            if verb == "new":                     # new <seed>: the game gets its own list of the dictionary words
                self.words = list(WORDS)
                self.game = spindle.Game(int(args), self.words)
                return "ok"
            if verb == "learn":                   # learn <word>: appends to the list that was given to the game
                self.words.append(args)
                return "ok"
            if verb == "play":                    # play <word>: the points, or "error: <message>"
                try:
                    return "+%d" % self.game.play(args)
                except ValueError as e:
                    return "error: " + str(e)
            if verb == "skip":                    # skip: "ok" or "error: <message>"
                try:
                    self.game.skip()
                    return "ok"
                except ValueError as e:
                    return "error: " + str(e)
            if verb == "render":
                return self.game.render()
            if verb == "points":                  # points <word>
                return str(spindle.points(args))
            if verb == "formable":                # formable <word> <rack letters>
                word, _, rack = args.partition(" ")
                return "yes" if spindle.formable(word, rack) else "no"
            if verb == "best":                    # best <rack letters>: "<word> <points>" or "none"
                r = spindle.best_play(args, WORDS)
                return "none" if r is None else "%s %d" % r
            raise KeyError(verb)
''')}


def exec_engine(rules: dict):
    mod = types.ModuleType("spindle_engine")
    exec(engine(rules), mod.__dict__)
    return mod


def scripts(rng, rules: dict, words: list[str]) -> dict[str, str]:
    mod = exec_engine(rules)
    parts = []
    letters = sorted(rules["COUNTS"])
    for i, seed in enumerate((1, 2, 3, 42, 777, 123456, 2147483647, 99999999999)):
        g = mod.Game(seed, words)
        cmds = ["> new %d" % seed, "> render"]
        for _ in range(rules["TURNS"] + 2):
            if g.is_over():
                cmds += ["> play " + rng.choice(words), "> skip", "> render"]
                break
            roll = rng.randrange(100)
            best = mod.best_play(g.rack, words)
            formable = [w for w in words if mod.formable(w, g.rack)]
            if roll < 8:
                c = rng.choice(["play ab", "play zzz", "play " + "".join(rng.choice(letters) for _ in range(4)), "play", "play  " + rng.choice(words), "play " + rng.choice(words).upper()])
                cmds.append("> " + c)
                try:
                    g.play(c[5:])
                except ValueError:
                    pass
                continue
            if roll < 14:
                g.skip()
                cmds.append("> skip")
            elif formable and roll < 60 and best:
                cmds.append("> play " + best[0])
                g.play(best[0])
            elif formable:
                w = rng.choice(formable)
                cmds.append("> play " + w)
                g.play(w)
            else:
                g.skip()
                cmds.append("> skip")
            cmds.append("> render")
            cmds.append("> best " + "".join(g.rack))
        parts.append(f"# scenario game {i + 1} seed {seed}\n" + "\n".join(cmds) + "\n> render")
    for i, seed in enumerate((3, 4, 5)):
        g = mod.Game(seed, words)
        rack = g.rack
        cand = None
        for a in range(len(rack)):
            for b in range(len(rack)):
                for c in range(len(rack)):
                    if len({a, b, c}) == 3 and cand is None and "".join(rack[x] for x in (a, b, c)) not in words:
                        cand = "".join(rack[x] for x in (a, b, c))
        parts.append(f"# scenario the dictionary is copied {i + 1}\n> new {seed}\n> learn {cand}\n> play {cand}\n> render")
    pts = []
    for w in rng.sample(words, 25) + ["aaa", "eee", "baaab"][:0]:
        pts.append(f"> points {w}")
    rack = "".join(rng.choice(letters) for _ in range(7))
    ctx = ["# scenario scoring"] + pts + [f"> formable {rng.choice(words)} {rack}" for _ in range(10)] + [f"> formable {w} {w[::-1]}" for w in rng.sample(words, 6)] + [f"> formable aaaa aaa", "> formable  abc"]
    for _ in range(8):
        rack = "".join(rng.choice(letters) for _ in range(7))
        ctx.append(f"> best {rack}")
    ctx += ["> best zzzzzzz", "> best "]
    return {"hidden_games": "\n".join(parts) + "\n", "hidden_scoring": "\n".join(ctx) + "\n"}


def example_script(rules: dict, words: list[str]) -> str:
    mod = exec_engine(rules)
    g = mod.Game(5, words)
    best = mod.best_play(g.rack, words)
    return (f"# scenario first turns\n> new 5\n> render\n> best {''.join(g.rack)}\n> play {best[0]}\n> render\n> play ab\n> play qqq\n> skip\n> render\n"
            f"# scenario scoring\n> points {words[0]}\n> points {words[1]}\n> formable {words[2]} {''.join(sorted(words[2]))}\n> formable {words[2]} {words[3]}\n")


def readme(rules: dict, with_best: bool = True) -> str:
    cnt = rules["COUNTS"]
    s = []
    s.append("# Spindle\n\nA word game for one player: seven tiles on a rack, ten-ish turns, an invented scoring system. The engine is a small library (`spindle.py`): scoring helpers, a seeded `Game` and exact text for the board. "
             "The dictionary is the file `words.txt` (one lower-case word per line, 3 to 7 letters).\n")
    s.append("## Tiles\n\n| letter | " + " | ".join(cnt) + " |\n|---|" + "---|" * len(cnt) + "\n| value | " + " | ".join(str(rules["VALUES"][c]) for c in cnt) + " |\n| tiles in the bag | " + " | ".join(str(cnt[c]) for c in cnt) + " |\n\n"
             f"The bag holds {sum(cnt.values())} tiles in total, listed in a fixed order: letters in alphabetical order, each repeated as often as there are tiles of it (`aaaa...bb...`).\n")
    s.append("## Scoring a word\n\n`points(word)`:\n\n"
             f"1. `base` = the sum of the letter values.\n2. `total = base * multiplier(length)` with the multipliers " + ", ".join(f"{k} letters x{v}" for k, v in rules["MULT"].items()) + ".\n"
             f"3. Echo: for every pair of *neighbouring equal letters* in the word (`ee`, `tt`; a run of three equal letters is two pairs) add {rules['ECHO']} points" + (" (nothing, this table has no echo bonus)" if not rules["ECHO"] else "") + ".\n"
             f"4. Spindle: a word of exactly 7 letters (the whole rack) adds {rules['SPINDLE']} points.\n")
    s.append("## The game\n\n`Game(seed, words)` takes a seed and the dictionary (a list of words; the game keeps its own copy, so later changes to the caller's list have no effect on it). The generator: `state = seed mod 2^31`; `next()` sets `state = (state * 1103515245 + 12345) mod 2^31` and returns the new state. "
             "To *draw* a tile: `i = (next() >> 8) mod (tiles left in the bag)`; the tile at position `i` of the bag list is removed and goes to the rack. The rack starts empty; the game fills it to 7 tiles by drawing "
             "(one draw after the other) while the bag is not empty, then sorts the rack alphabetically. The score starts at 0 and the turn counter at 1. Nothing else uses the generator.\n\n"
             f"* `play(word)`: a turn. Checks in this order, raising `ValueError` with exactly that message and changing nothing: `game over` (the game is over); `too short` (fewer than 3 letters); `not in dictionary`; `not on the rack` "
             "(the rack cannot spell the word: every letter needs its own tile). Then the tiles of the word leave the rack (for a repeated letter one tile each), the score grows by `points(word)`, the turn counter grows by 1, "
             "the rack is refilled as above (to 7 tiles while the bag lasts, sorted) and the points are returned.\n"
             "* `skip()`: also a turn: the whole rack is thrown away (the tiles are gone, they do not go back to the bag), the turn counter grows by 1 and the rack is refilled. Raises `ValueError(\"game over\")` when the game is over. Returns nothing.\n"
             f"* The game is *over* when the turn counter is above {rules['TURNS']} or the rack is empty.\n"
             "* `is_over()` returns whether it is over.\n")
    s.append("## API (`spindle.py`)\n\n```python\nimport spindle\nspindle.points(word) -> int\nspindle.formable(word, rack) -> bool      # rack: a string or a list of letters\n" +
             ("spindle.best_play(rack, words) -> (word, points) or None\n" if with_best else "") + "g = spindle.Game(seed, words)\ng.play(word) -> int\ng.skip() -> None\ng.is_over() -> bool\ng.render() -> str\n```\n")
    if with_best:
        s.append("`best_play(rack, words)` looks through the words (an iterable) and returns the word with the most points that is at least 3 letters long and `formable` from the rack, together with its points. Ties are broken "
                 "by the longer word, then by the alphabetically smaller word. `None` if no word can be played.\n")
    s.append("### `render()`\n\nTwo lines joined by `\\n`: `turn <t>/<max> score <score> bag <tiles left>` (the turn shown is `min(turn, max)`; ` GAME OVER` is appended when the game is over) and `rack: ` followed by the rack's letters separated by single spaces "
             "(`rack: ` with nothing after it when the rack is empty). Example: `turn 3/10 score 41 bag 62` then `rack: a b d e l o r`.\n")
    s.append("## Tests\n\n`python3 -m unittest discover -s tests -v` replays the scenario files in `tests/data/` (`tests/adapter.py` shows how the API is called; the format is described at the top of `tests/test_scenarios.py`).\n")
    return "\n".join(s)


def _variants(rng, n: int):
    return [make_rules(rng, i) for i in range(n)]


@family("games-spindle-build", category="games", lang="python", kind="greenfield", n=6,
        summary="build the Spindle word game: invented scoring (multipliers, echo, spindle), seeded bag draws, best-play search")
def gen_build(rng, n):
    used: list[str] = []
    for i, rules in enumerate(_variants(rng, n)):
        words = make_words(rng, rules)
        sol = {"spindle.py": engine(rules), "words.txt": "\n".join(words) + "\n", ".gitignore": _kit.GITIGNORE[LANG]}
        hidden = _kit.data_files(LANG, scripts(rng, rules, words), sol, ADAPTER)
        vis = _kit.data_files(LANG, {"examples": example_script(rules, words)}, sol, ADAPTER)
        start = {"README.md": readme(rules), "spindle.py": STUB, "words.txt": sol["words.txt"], ".gitignore": sol[".gitignore"], **_scen.check_files(LANG, ADAPTER), **vis}
        d = 2 + (rules["ECHO"] > 0) + (rules["TURNS"] != 10)
        prompt = _kit.green_prompt(rng, game=GAME, blurb="a one-player word game with a rack, a bag and an invented scoring system", file="spindle.py", verify=_scen.VERIFY[LANG], used=used)
        yield Task(slug=f"{i + 1:02d}-echo{rules['ECHO']}-spindle{rules['SPINDLE']}-t{rules['TURNS']}", prompt=prompt, difficulty=min(d, 4), start=start, hidden=hidden,
                   solution={"spindle.py": sol["spindle.py"]}, verify=_scen.VERIFY[LANG], tags=["word-game", "scoring", "rng", "scenarios"], notes={"rules": rules})


BUGS = [
    Bug("echo-triples", "Echo counts letters, not pairs",
        "The echo bonus is too high for words with three equal letters in a row, and it also fires for equal letters that are not next to each other.",
        [("total += ECHO_BONUS * sum(1 for a, b in zip(word, word[1:]) if a == b)", "total += ECHO_BONUS * sum(word.count(c) - 1 for c in set(word))")], difficulty=2, rules=dict(ECHO=4)),
    Bug("spindle-length", "The spindle bonus needs the wrong length",
        "The bonus for using the whole rack is given for six-letter words as well as seven-letter ones.",
        [("if len(word) == RACK_SIZE:", "if len(word) >= RACK_SIZE - 1:")], difficulty=1),
    Bug("formable-duplicates", "A single tile is used twice",
        "The engine accepts words that need a letter twice when the rack only has one tile of it.",
        [("left = list(rack)\n        for c in word:\n            if c not in left:\n                return False\n            left.remove(c)\n        return True", "return all(c in rack for c in word)")], difficulty=2),
    Bug("tie-break", "Best-play ties go to the wrong word",
        "When two words are worth the same `best_play` returns the alphabetically larger one (or the shorter one); the README says longer first, then alphabetical.",
        [("(key == best[0] and w < best[1])", "(key == best[0] and w > best[1])")], difficulty=2),
    Bug("rack-unsorted", "The rack is not kept in alphabetical order",
        "After tiles are drawn the rack shows them in the order they came out of the bag instead of alphabetically, so the same rack can be displayed in different orders.",
        [("self.rack.sort()", "pass")], difficulty=1),
    Bug("rng-bits", "Draws use the wrong bits",
        "For a given seed the racks do not match the README's draws: the position of the drawn tile uses different bits of the state.",
        [("self.bag.pop((self._next() >> 8) % len(self.bag))", "self.bag.pop((self._next() >> 4) % len(self.bag))")], difficulty=3),
    Bug("skip-returns-tiles", "Skipping puts the rack back into the bag",
        "After a skip the bag size in the status text doesn't go down by the new rack: thrown-away tiles seem to return to the bag.",
        [("def skip(self):\n            if self.is_over():\n                raise ValueError(\"game over\")\n            self.rack = []", "def skip(self):\n            if self.is_over():\n                raise ValueError(\"game over\")\n            self.bag.extend(self.rack)\n            self.rack = []")], difficulty=3),
    Bug("error-order", "Error messages come in the wrong order",
        "A short word that is also not in the dictionary gets `not in dictionary` where the README says `too short` is checked first.",
        [("if len(word) < MIN_LENGTH:\n                raise ValueError(\"too short\")\n            if word not in self.words:\n                raise ValueError(\"not in dictionary\")", "if word not in self.words:\n                raise ValueError(\"not in dictionary\")\n            if len(word) < MIN_LENGTH:\n                raise ValueError(\"too short\")")], difficulty=2),
    Bug("turn-display", "The turn counter can exceed the maximum",
        "On the final board the turn shows e.g. 11/10; the README says the shown turn is capped at the maximum.",
        [("min(self.turn, MAX_TURNS)", "self.turn")], difficulty=1),
    Bug("last-turn", "The game lasts one turn too long",
        "A game of N turns lets me play N+1 words.",
        [("return self.turn > MAX_TURNS or not self.rack", "return self.turn > MAX_TURNS + 1 or not self.rack")], difficulty=2),
    Bug("mult-length", "Multipliers are looked up one length off",
        "Words are scored with the multiplier of the next shorter length, so a 5-letter word gets the 4-letter multiplier.",
        [("total = base * MULT[len(word)]", "total = base * MULT[max(3, len(word) - 1)]")], difficulty=2),
    Bug("dictionary-copy", "Changing the dictionary list changes the game",
        "If the caller changes the word list after creating a game (appending a word, for instance) the game accepts it too.",
        [("self.words = frozenset(words)", "self.words = words")], difficulty=3),
]

_B = {b.id: b for b in BUGS}
BUGS_ALL = BUGS + [
    _kit.combine(_B["spindle-length"], _B["turn-display"], difficulty=2),
    _kit.combine(_B["tie-break"], _B["mult-length"], _B["error-order"], difficulty=4),
]


@family("games-spindle-fix", category="games", lang="python", kind="fix", n=13,
        summary="hand-injected defects in the Spindle engine (echo and spindle bonuses, multiset check, ties, draw order, error order)")
def gen_fix(rng, n):
    used: list[str] = []
    cache = {}
    for k, bug in enumerate(BUGS_ALL[:n]):
        key = json.dumps(bug.rules, sort_keys=True)
        if key not in cache:
            rr = random_rules = make_rules(rng, len(cache))
            rr.update({kk: vv for kk, vv in bug.rules.items()})
            words = make_words(rng, rr)
            sol = {"spindle.py": engine(rr), "words.txt": "\n".join(words) + "\n", ".gitignore": _kit.GITIGNORE[LANG]}
            cache[key] = (sol, _kit.data_files(LANG, scripts(rng, rr, words), sol, ADAPTER), _kit.data_files(LANG, {"examples": example_script(rr, words)}, sol, ADAPTER), readme(rr))
        sol, hidden, vis, rd = cache[key]
        base = {**sol, "README.md": rd}
        tests = {**_scen.check_files(LANG, ADAPTER), **vis}
        ctx = {"files": ["spindle.py"], "verify": _scen.VERIFY[LANG]}
        yield _kit.bug_task(game=GAME, lang=LANG, base_files=base, tests=tests, hidden=hidden, bug=bug, ctx=ctx, rng=rng, used=used, k=k,
                            tags=["word-game", "scoring"], extra_notes={"rules": json.loads(json.dumps({k2: v2 for k2, v2 in bug.rules.items()}))})


# ----------------------------------------------------------------------------------------------------- bot tournament

ARENA = dd('''
    """Local arena for Spindle bots.

        python3 arena.py [--games N]

    Plays N games (seeds 1..N) with your `bot.choose` and prints the totals next to the opponent baseline's.
    """
    import argparse

    import baseline
    import bot
    import spindle

    with open("words.txt", encoding="utf-8") as f:
        WORDS = f.read().split()


    def play_game(choose, seed):
        """One game; `choose(rack, words)` returns a word to play or None to skip. A word that the engine rejects
        counts as a skip (and costs the turn)."""
        game = spindle.Game(seed, WORDS)
        while not game.is_over():
            word = None
            try:
                word = choose("".join(game.rack), frozenset(WORDS))
            except Exception:  # noqa: BLE001 - a crashing bot skips
                word = None
            try:
                if word is None:
                    game.skip()
                else:
                    game.play(word)
            except ValueError:
                game.skip()
        return game.score


    def total(choose, seeds):
        return sum(play_game(choose, s) for s in seeds)


    if __name__ == "__main__":
        ap = argparse.ArgumentParser()
        ap.add_argument("--games", type=int, default=20)
        args = ap.parse_args()
        seeds = range(1, args.games + 1)
        print("bot total %d, baseline total %d over %d games" % (total(bot.choose, seeds), total(baseline.choose, seeds), args.games))
''')

BASELINE_LONGEST = dd('''
    """The opponent: it plays the longest word that fits the rack (ties: the alphabetically first), or skips."""
    import spindle


    def choose(rack, words):
        best = None
        for w in sorted(words):
            if len(w) >= 3 and spindle.formable(w, rack) and (best is None or len(w) > len(best)):
                best = w
        return best
''')

BASELINE_FIRST = dd('''
    """The opponent: it plays the alphabetically first word that fits the rack, or skips."""
    import spindle


    def choose(rack, words):
        for w in sorted(words):
            if len(w) >= 3 and spindle.formable(w, rack):
                return w
        return None
''')

BOT_STUB = dd('''
    """Your Spindle player. `choose(rack, words)` gets the rack as a string of letters and the dictionary as a frozenset and
    returns the word to play, or None to skip the turn."""


    def choose(rack, words):
        return None
''')

GOLD_BOT = dd('''
    """Greedy: play the most valuable word the rack allows."""
    import spindle


    def choose(rack, words):
        best = None
        for w in sorted(words):
            if len(w) >= 3 and spindle.formable(w, rack):
                p = spindle.points(w)
                if best is None or p > best[0]:
                    best = (p, w)
        return None if best is None else best[1]
''')

SCORE_PY = dd('''
    import json
    import sys

    sys.path.insert(0, ".")
    import arena  # noqa: E402
    import bot  # noqa: E402
    import spindle  # noqa: E402

    SEEDS = range(5000, 5000 + 24)
    FLOOR, GOAL = @@FLOOR@@, @@GOAL@@


    def reference(rack, words):
        best = None
        for w in sorted(words):
            if len(w) >= 3 and spindle.formable(w, rack):
                p = spindle.points(w)
                if best is None or p > best[0]:
                    best = (p, w)
        return None if best is None else best[1]


    mine = arena.total(bot.choose, SEEDS)
    ref = arena.total(reference, SEEDS)
    ratio = mine / ref
    print("bot %d, greedy reference %d over %d games: ratio %.3f (full score from %.2f)" % (mine, ref, len(SEEDS), ratio, GOAL))
    print(json.dumps({"score": round(max(0.0, min(1.0, (ratio - FLOOR) / (GOAL - FLOOR))), 4)}))
''')

BOT_VARIANTS = [dict(opp="first", floor=0.0, goal=0.97, d=2), dict(opp="longest", floor=0.3, goal=0.97, d=3), dict(opp="first", floor=0.2, goal=0.99, d=3), dict(opp="longest", floor=0.4, goal=0.99, d=3)]


def bot_readme(rules: dict, v: dict) -> str:
    return readme(rules, with_best=False).replace("## Tests\n", dd(f'''
        ## Your task: a player

        `bot.py` defines `choose(rack, words)`: `rack` is the current rack as a string of letters (sorted), `words` the dictionary as a `frozenset`; return the word to play, or `None` to skip the turn. `arena.py` plays whole games with the real
        engine: a word the engine rejects counts as a skip (and costs the turn), and a bot that raises an exception skips too. `python3 arena.py --games 20` prints your total over seeds 1..20 next to the opponent's
        (`baseline.py`: {"the longest word that fits the rack" if v["opp"] == "longest" else "the alphabetically first word that fits the rack"}).

        ## Scoring

        The check plays 24 games (other seeds) and compares your total score with the total of a reference player that always plays the highest-scoring word available (you do not get to see it; it is not the baseline). `ratio` is your total divided by the reference total.
        The score is `clamp((ratio - {v["floor"]}) / ({v["goal"]} - {v["floor"]}), 0, 1)`: 1.0 needs a ratio of at least {v["goal"]}.

        ## Tests
    '''), 1)


@family("games-spindle-bot", category="games", lang="python", kind="greenfield", n=4,
        summary="write a Spindle player that scores close to a greedy reference over seeded games (json-score)")
def gen_bot(rng, n):
    for i, v in enumerate(BOT_VARIANTS[:n]):
        rules = make_rules(rng, i)
        words = make_words(rng, rules)
        files = {"spindle.py": engine(rules, with_best=False), "words.txt": "\n".join(words) + "\n", "arena.py": ARENA, "baseline.py": BASELINE_LONGEST if v["opp"] == "longest" else BASELINE_FIRST,
                 ".gitignore": _kit.GITIGNORE[LANG]}
        start = {**files, "bot.py": BOT_STUB, "README.md": bot_readme(rules, v)}
        hidden = {".check/score.py": SCORE_PY.replace("@@FLOOR@@", repr(v["floor"])).replace("@@GOAL@@", repr(v["goal"]))}
        s0, s1, out = _kit.check_scores(start=start, hidden=hidden, solution={"bot.py": GOLD_BOT}, verify="python3 .check/score.py", name=f"spindle-bot-{i}")
        voices = [
            "Write the player for our Spindle table in `bot.py`: given the rack and the dictionary it must pick a word. README.md explains how it is scored (a ratio against a greedy reference over a set of seeded games); `arena.py` lets you try it.",
            "`bot.py` never plays anything, so every game scores zero. Make it play well: README.md describes the scoring rules of Spindle and how the bot is graded.",
            "I want a Spindle bot that gets close to the best a greedy player can do. The scoring system is unusual (see README.md), so don't assume the longest word is the best one. Implement `choose` in `bot.py`.",
            "Implement `choose(rack, words)` in `bot.py` for Spindle. The grading compares your total over a batch of games with a reference total; README.md has the details and `python3 arena.py` runs a local match against the baseline.",
        ]
        yield Task(slug=f"{i + 1:02d}-vs-{v['opp']}", prompt=voices[i % len(voices)], difficulty=v["d"], start=start, hidden=hidden, solution={"bot.py": GOLD_BOT},
                   verify="python3 .check/score.py", pass_mode="json-score", protected=["spindle.py", "arena.py", "baseline.py", "words.txt"],
                   tags=["bot", "word-game", "tournament"], notes={"rules": rules, "opponent": v["opp"], "gold": out.strip().splitlines()[-2], "stub_score": s0})
