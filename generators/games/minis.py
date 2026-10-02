"""Game minis (python): ten small, distinct game-rule functions (trick winner, sowing, initiative, exact shuffle, line merge,
word score, territory, dice hands, a jumping board, a run-length move log). The easy end of the games category."""
from __future__ import annotations

import types

from fx import Task, dd, family

from . import _kit

LANG = "python"

HEAD_TEST = '''import unittest

from {mod} import {names}

CASES = {cases}


class Test{cls}(unittest.TestCase):
    def test_cases(self):
        for args, want in CASES:
            with self.subTest(args=args):
                self.assertEqual({call}, want)


if __name__ == "__main__":
    unittest.main()
'''


class Mini:
    def __init__(self, slug, d, mod, fname, title, prompt_voices, readme, ref, stub, gen_args, nvis=3, nhid=40, expect_error=False):
        self.slug, self.d, self.mod, self.fname, self.title = slug, d, mod, fname, title
        self.voices, self.readme, self.ref, self.stub, self.gen_args = prompt_voices, readme, ref, stub, gen_args
        self.nvis, self.nhid = nvis, nhid


def _load(ref: str, mod: str):
    m = types.ModuleType(mod)
    exec(ref, m.__dict__)
    return m


def _safe(fn, args):
    try:
        return ("ok", fn(*args))
    except ValueError as e:
        return ("error", str(e))


# --------------------------------------------------------------------------------------------------------- 1 trick winner

TRICK_REF = dd('''
    RANKS = "9TJQKA"


    def trick_winner(plays, trump):
        """plays: [(player, card)] in the order played, card like "QH". Returns the winning player."""
        led = plays[0][1][1]
        best, winner = None, plays[0][0]
        for player, card in plays:
            is_trump = card[1] == trump
            if not is_trump and card[1] != led:
                continue
            key = (is_trump, RANKS.index(card[0]))
            if best is None or key > best:
                best, winner = key, player
        return winner
''')
TRICK_STUB = 'def trick_winner(plays, trump):\n    raise NotImplementedError\n'


def trick_args(rng):
    deck = [r + s for s in "CDHS" for r in "9TJQKA"]
    n = rng.choice([3, 3, 4])
    cards = rng.sample(deck, n)
    return ([(f"P{i}", c) for i, c in enumerate(cards)], rng.choice("CDHS")),


# --------------------------------------------------------------------------------------------------------- 2 sowing

SOW_REF = dd('''
    def sow(pits, i):
        """Tidepool sowing on 12 pits (0-5 belong to south, 6-11 to north). Returns (new pits, captured seeds)."""
        if not 0 <= i < 12:
            raise ValueError("no such pit")
        if pits[i] == 0:
            raise ValueError("empty pit")
        pits = list(pits)
        seeds, pits[i] = pits[i], 0
        pos = i
        while seeds:
            pos = (pos + 1) % 12
            if pos == i:
                continue
            pits[pos] += 1
            seeds -= 1
        captured = 0
        own = range(0, 6) if i < 6 else range(6, 12)
        if pos in own and pits[pos] == 1 and pits[11 - pos] > 0:
            captured = pits[pos] + pits[11 - pos]
            pits[pos] = pits[11 - pos] = 0
        return pits, captured
''')
SOW_STUB = 'def sow(pits, i):\n    raise NotImplementedError\n'


def sow_args(rng):
    pits = [rng.choice([0, 0, 1, 2, 3, 4, 7, 12, 15]) for _ in range(12)]
    i = rng.randrange(12) if rng.randrange(12) else 12
    if i < 12 and pits[i] == 0 and rng.randrange(5):
        pits[i] = rng.randint(1, 9)
    return (pits, i),


# --------------------------------------------------------------------------------------------------------- 3 initiative

INIT_REF = dd('''
    def initiative_order(units):
        """units: [(name, speed, roll)]. Names in acting order: highest speed+roll first, then higher speed, then name."""
        return [u[0] for u in sorted(units, key=lambda u: (-(u[1] + u[2]), -u[1], u[0]))]
''')
INIT_STUB = 'def initiative_order(units):\n    raise NotImplementedError\n'


def init_args(rng):
    names = rng.sample(["ash", "bram", "cole", "dara", "eli", "fenn", "gus", "hale", "ivo", "jun"], rng.randint(2, 7))
    return ([(n, rng.randint(1, 9), rng.randint(0, 5)) for n in names],),


# --------------------------------------------------------------------------------------------------------- 4 shuffle

SHUF_REF = dd('''
    def lcg_values(seed, n):
        """The first n outputs of state = (state * 1103515245 + 12345) mod 2**31, starting from seed mod 2**31."""
        state = seed % 2**31
        out = []
        for _ in range(n):
            state = (state * 1103515245 + 12345) % 2**31
            out.append(state)
        return out


    def shuffle(items, seed):
        """A shuffled copy: Fisher-Yates from the end, j = (next >> 16) mod (i + 1)."""
        items = list(items)
        values = lcg_values(seed, max(0, len(items) - 1))
        for k, i in enumerate(range(len(items) - 1, 0, -1)):
            j = (values[k] >> 16) % (i + 1)
            items[i], items[j] = items[j], items[i]
        return items
''')
SHUF_STUB = 'def lcg_values(seed, n):\n    raise NotImplementedError\n\n\ndef shuffle(items, seed):\n    raise NotImplementedError\n'


def shuf_args(rng):
    if rng.randrange(3):
        return (list(range(rng.randint(0, 12))), rng.choice([0, 1, 7, 2**31 - 1, 2**31, 2**40 + 3, rng.randrange(10**6)])),
    return ([rng.choice("abcdefgh") for _ in range(rng.randint(2, 9))], rng.randrange(10**9)),


# --------------------------------------------------------------------------------------------------------- 5 merge line

MERGE_REF = dd('''
    def merge_line(tiles, k):
        """Slide a line of tiles (0 = empty) towards index 0 and merge groups of k equal neighbours. Returns (line, gained)."""
        nums = [t for t in tiles if t]
        out, gained, i = [], 0, 0
        while i < len(nums):
            if i + k <= len(nums) and len(set(nums[i:i + k])) == 1:
                out.append(nums[i] * k)
                gained += nums[i] * k
                i += k
            else:
                out.append(nums[i])
                i += 1
        return out + [0] * (len(tiles) - len(out)), gained
''')
MERGE_STUB = 'def merge_line(tiles, k):\n    raise NotImplementedError\n'


def merge_args(rng):
    k = rng.choice([2, 3, 3, 4])
    base = k
    n = rng.randint(3, 8)
    return ([rng.choice([0, 0, 1, 1, 1, base, base]) * (1 if rng.randrange(4) else base) for _ in range(n)], k),


# --------------------------------------------------------------------------------------------------------- 6 word score

WORD_REF = dd('''
    def word_score(word, values, mult):
        """values: letter -> points; mult: length -> multiplier. Echo: +4 for every pair of neighbouring equal letters."""
        total = sum(values[c] for c in word) * mult[len(word)]
        total += 4 * sum(1 for a, b in zip(word, word[1:]) if a == b)
        return total
''')
WORD_STUB = 'def word_score(word, values, mult):\n    raise NotImplementedError\n'


def word_args(rng):
    letters = "abdeklnorst"
    values = {c: rng.randint(1, 5) for c in letters}
    mult = {n: rng.choice([1, 2, 3]) + n // 2 for n in range(1, 9)}
    w = "".join(rng.choice(letters) for _ in range(rng.randint(1, 8)))
    if rng.randrange(3):
        i = rng.randrange(len(w))
        w = (w[: i + 1] + w[i] + w[i + 1:])[:8]
    return (w, values, mult),


# --------------------------------------------------------------------------------------------------------- 7 foam territory

FOAM_REF = dd('''
    def foam_scores(rows):
        """rows: list of strings of 'X', 'O' and '.'. Score = stones + owned empty cells (a region of '.' (4-neighbour) is owned
        by a colour when every stone touching it is that colour; regions touching both colours or no stone are nobody's)."""
        h, w = len(rows), len(rows[0])
        score = {"X": 0, "O": 0}
        seen = set()
        for y in range(h):
            for x in range(w):
                if rows[y][x] in score:
                    score[rows[y][x]] += 1
                elif (y, x) not in seen:
                    stack, region, touch = [(y, x)], [], set()
                    seen.add((y, x))
                    while stack:
                        cy, cx = stack.pop()
                        region.append((cy, cx))
                        for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                            if 0 <= ny < h and 0 <= nx < w:
                                c = rows[ny][nx]
                                if c == ".":
                                    if (ny, nx) not in seen:
                                        seen.add((ny, nx))
                                        stack.append((ny, nx))
                                else:
                                    touch.add(c)
                    if len(touch) == 1:
                        score[touch.pop()] += len(region)
        return score["X"], score["O"]
''')
FOAM_STUB = 'def foam_scores(rows):\n    raise NotImplementedError\n'


def foam_args(rng):
    w, h = rng.randint(3, 7), rng.randint(3, 7)
    dens = rng.choice([20, 35, 50])
    return (["".join(rng.choice("XO") if rng.randrange(100) < dens else "." for _ in range(w)) for _ in range(h)],),


# --------------------------------------------------------------------------------------------------------- 8 dice hands

HAND_REF = dd('''
    def hand_key(dice):
        """Comparable key of a hand of three dice: triple > run > pair > high."""
        a = sorted(dice, reverse=True)
        if a[0] == a[1] == a[2]:
            return (3, a[0])
        if a[0] - 1 == a[1] and a[1] - 1 == a[2]:
            return (2, a[0])
        if a[0] == a[1] or a[1] == a[2]:
            pair = a[1]
            kicker = a[2] if a[0] == a[1] else a[0]
            return (1, pair, kicker)
        return (0, a[0], a[1], a[2])


    def best_hand(hands):
        """Index of the best hand; the first one wins a tie."""
        best = 0
        for i, h in enumerate(hands):
            if hand_key(h) > hand_key(hands[best]):
                best = i
        return best
''')
HAND_STUB = 'def hand_key(dice):\n    raise NotImplementedError\n\n\ndef best_hand(hands):\n    raise NotImplementedError\n'


def hand_args(rng):
    if rng.randrange(2):
        return ([rng.randint(1, 6) for _ in range(3)],),
    return ([[rng.randint(1, 6) for _ in range(3)] for _ in range(rng.randint(2, 5))],),


# --------------------------------------------------------------------------------------------------------- 9 jumping board

BOARD_REF = dd('''
    def play(rolls, jumps, size=30):
        """A one-token race: start at 0 and use the rolls in order. Move forward by the roll, doubled when the previous roll was a 6.
        Past `size` the token bounces back (size - (pos - size)); then a key of `jumps` sends it to its value (one jump per roll).
        Exactly `size` wins at once. Returns (position, number of rolls used, won)."""
        pos, used, double = 0, 0, False
        for r in rolls:
            used += 1
            step = r * 2 if double else r
            double = r == 6
            pos += step
            if pos > size:
                pos = size - (pos - size)
            pos = jumps.get(pos, pos)
            if pos == size:
                return pos, used, True
        return pos, used, False
''')
BOARD_STUB = 'def play(rolls, jumps, size=30):\n    raise NotImplementedError\n'


def board_args(rng):
    size = rng.choice([30, 30, 20, 40])
    jumps = {}
    for _ in range(rng.randint(2, 6)):
        a = rng.randint(2, size - 2)
        b = rng.randint(1, size - 1)
        if a != b and a not in jumps:
            jumps[a] = b
    return ([rng.randint(1, 6) for _ in range(rng.randint(0, 40))], jumps) + ((size,) if size != 30 else ()),


# --------------------------------------------------------------------------------------------------------- 10 run-length log

LOG_REF = dd('''
    def encode(moves):
        """moves: a string of L, R, S. Runs of 2 or more get their length after the letter: 'LLLSRR' -> 'L3SR2'."""
        out, i = "", 0
        while i < len(moves):
            j = i
            while j < len(moves) and moves[j] == moves[i]:
                j += 1
            out += moves[i] + (str(j - i) if j - i > 1 else "")
            i = j
        return out


    def decode(text):
        """Inverse of encode. A letter may be followed by a count of 2..9999 without leading zeros. ValueError('bad log at <index>')
        for a letter that is not L, R or S, or (index of the first digit) for a bad count."""
        out, i = [], 0
        while i < len(text):
            c = text[i]
            if c not in "LRS":
                raise ValueError("bad log at %d" % i)
            i += 1
            start = i
            while i < len(text) and text[i].isdigit() and text[i].isascii():
                i += 1
            n = 1
            if i > start:
                digits = text[start:i]
                if digits[0] == "0" or len(digits) > 4 or int(digits) < 2:
                    raise ValueError("bad log at %d" % start)
                n = int(digits)
            out.append(c * n)
        return "".join(out)
''')
LOG_STUB = 'def encode(moves):\n    raise NotImplementedError\n\n\ndef decode(text):\n    raise NotImplementedError\n'


def log_args(rng):
    if rng.randrange(2):
        return ("".join(rng.choice("LLRRS") for _ in range(rng.randint(0, 30))),),
    return (rng.choice(["L3SR2", "", "LLR", "S", "X", "L1", "L0", "L01", "R10", "R99999", "L2L3", "2L", "SS", "R9999", "RL3S10X", "L٣"]),),


MINIS = [
    dict(slug="trick-winner", d=2, mod="trick", fname="trick_winner", ref=TRICK_REF, stub=TRICK_STUB, gen=trick_args, names="trick_winner", call="trick_winner(*args)",
         title="Who wins the trick",
         spec="""A trick in a three-or-four-player card game with ranks `9 T J Q K A` (9 lowest) and suits `C D H S`. `trick_winner(plays, trump)` takes the plays in the order they were made, as `(player, card)` pairs with a card like `"QH"` (rank, suit),
and the trump suit of this trick (one letter). The *led suit* is the suit of the first card. The winner is the player of the highest trump if any trump was played; otherwise the player of the highest card of the led suit (cards of other suits never win). Return the winning player.""",
         voices=["Write `trick_winner` in `trick.py`: given the plays of one trick and the trump suit, who takes it? The rules (our table's tide-trump variant) are in README.md.",
                 "Our Barnacle score sheet needs a function that names the winner of a trick. See README.md for the rules; the function lives in `trick.py`.",
                 "Implement `trick_winner(plays, trump)` in `trick.py` following README.md. The examples in `tests/` show the call."]),
    dict(slug="tidepool-sowing", d=3, mod="tidepool", fname="sow", ref=SOW_REF, stub=SOW_STUB, gen=sow_args, names="sow", call="sow(*args)",
         title="Sow the tidepool",
         spec="""*Tidepool* is a sowing game on 12 pits in a ring: pits 0-5 belong to the south player (left to right), pits 6-11 to the north player; the ring order is 0, 1, ..., 11, 0, ... `sow(pits, i)` plays pit `i` (a list of 12 non-negative ints is given and must not be modified):

* Raise `ValueError("no such pit")` if `i` is not in 0..11 (checked first) and `ValueError("empty pit")` if the pit holds no seeds.
* All seeds are taken out of pit `i` and dropped one by one into the following pits of the ring. The pit `i` itself is skipped when the sowing laps around.
* *Capture*: if the last seed lands in a pit on the *mover's own side* (the side of pit `i`) that was empty before this seed (so it holds exactly 1 now), and the opposite pit (`11 - j` for pit `j`) holds seeds, both pits are emptied and all those seeds (the 1 and the opposite pit's) are captured.
* Return `(new_pits, captured)`: a new list and the number of captured seeds (0 if no capture).""",
         voices=["Implement the sowing move of our Tidepool game: `sow(pits, i)` in `tidepool.py`, rules in README.md (captures and the skipped origin pit are the parts people get wrong).",
                 "Write `sow` for Tidepool. The ring, the capture rule and the error cases are described in README.md; it must not modify its argument.",
                 "`tidepool.py` needs `sow(pits, i)`: sow the seeds around the ring and report captures, as specified in README.md."]),
    dict(slug="initiative-order", d=1, mod="initiative", fname="initiative_order", ref=INIT_REF, stub=INIT_STUB, gen=init_args, names="initiative_order", call="initiative_order(*args)",
         title="Turn order",
         spec="""`initiative_order(units)` takes `(name, speed, roll)` tuples and returns the names in acting order. A unit's initiative is `speed + roll`. Higher initiative acts first; ties go to the unit with the higher `speed`; remaining ties to the name that comes first alphabetically (plain string comparison).""",
         voices=["Add `initiative_order(units)` to `initiative.py`: sort the units by initiative with the tie-breaks from README.md.",
                 "Our tactics board needs the acting order of a round. `initiative_order` in `initiative.py`, rules in README.md.",
                 "Short one: implement `initiative_order` as described in README.md."]),
    dict(slug="exact-shuffle", d=2, mod="shuffle", fname="shuffle", ref=SHUF_REF, stub=SHUF_STUB, gen=shuf_args, names="lcg_values, shuffle", call="shuffle(*args)" , title="A reproducible shuffle",
         spec="""Two functions for games that must replay exactly:

* `lcg_values(seed, n)` returns the first `n` outputs (a list) of the generator `state = (state * 1103515245 + 12345) mod 2**31`, starting from `state = seed mod 2**31`; each output is the new state. `n = 0` gives `[]`.
* `shuffle(items, seed)` returns a *new* shuffled list (the input is not modified): Fisher-Yates from the end. For `i` from `len(items) - 1` down to 1, draw `j = (next >> 16) mod (i + 1)` where `next` is the next generator output (outputs are consumed one per `i`, in order), and swap the items at `i` and `j`. Lists of length 0 or 1 consume nothing.""",
         voices=["Write `lcg_values` and `shuffle` in `shuffle.py` exactly as README.md says: our replay files depend on the shuffle being identical everywhere.",
                 "`shuffle.py` has stubs for a seeded generator and a Fisher-Yates shuffle. Implement them to match README.md bit for bit.",
                 "I need a reproducible card shuffle (spec in README.md): `lcg_values(seed, n)` and `shuffle(items, seed)`."]),
    dict(slug="merge-line", d=2, mod="merge", fname="merge_line", ref=MERGE_REF, stub=MERGE_STUB, gen=merge_args, names="merge_line", call="merge_line(*args)", title="Merge a line",
         spec="""`merge_line(tiles, k)` is one line of a sliding-tile game where `k` equal tiles merge. `tiles` is a list of ints (0 = empty); the line is pushed towards index 0. Drop the empty cells, then walk through the remaining tiles from the start: if the next `k` tiles are all equal to `v`, they become one tile `k * v` (and the walk continues after them); otherwise the tile stays. Pad with zeros back to the original length. A merged tile is never merged again. Return `(new_line, gained)` where `gained` is the sum of the tiles created by merges. The input is not modified.""",
         voices=["Implement `merge_line(tiles, k)` in `merge.py`: slide towards the start and merge groups of k equal tiles, as in README.md.",
                 "Our merge-in-threes puzzle needs its line mover as a plain function. Details in README.md; file `merge.py`.",
                 "`merge_line` in `merge.py` is a stub. README.md describes what it must return (the new line and the points)."]),
    dict(slug="word-score", d=1, mod="wordscore", fname="word_score", ref=WORD_REF, stub=WORD_STUB, gen=word_args, names="word_score", call="word_score(*args)", title="Score a word",
         spec="""`word_score(word, values, mult)`: `values` maps each letter to its points, `mult` maps a word length to a multiplier. The score is `sum of the letter values * mult[len(word)]`, plus 4 for every pair of *neighbouring equal letters* in the word (`ee` is one pair, `eee` is two, `ete` none).""",
         voices=["Write `word_score` in `wordscore.py` following README.md (letter values, a length multiplier and an echo bonus).",
                 "A tiny one: our word game's scoring formula (README.md) as a function in `wordscore.py`.",
                 "Implement `word_score(word, values, mult)`; the formula is in README.md."]),
    dict(slug="foam-territory", d=4, mod="foam", fname="foam_scores", ref=FOAM_REF, stub=FOAM_STUB, gen=foam_args, names="foam_scores", call="foam_scores(args[0])", title="Count the foam",
         spec="""*Foam* is a stone-placing game on a small rectangular board. `foam_scores(rows)` takes the board as a list of equal-length strings of `X`, `O` and `.` (empty) and returns `(x_score, o_score)`. Each stone counts 1 point for its colour. Empty cells form *regions*: maximal sets of empty cells connected through horizontal or vertical neighbours. A region is *owned* by a colour when every stone that touches the region (orthogonally adjacent to one of its cells) has that colour; an owned region gives its colour one point per cell. A region touched by both colours, or by no stone at all, is nobody's. The board's edge touches nothing.""",
         voices=["Implement `foam_scores(rows)` in `foam.py`: stones plus owned empty regions, per README.md. Regions touched by both colours count for nobody.",
                 "We need the final score of a Foam position. The rules (README.md) are about flood-filling the empty regions and checking which colours touch them.",
                 "`foam.py` needs `foam_scores`. Read README.md carefully for what counts as an owned region."]),
    dict(slug="dice-hands", d=2, mod="hands", fname="best_hand", ref=HAND_REF, stub=HAND_STUB, gen=hand_args, names="hand_key, best_hand", call=None, title="Rank three dice",
         spec="""A hand is three dice (ints 1..6, in any order). Hands are ranked: **triple** (all equal) beats **run** (three consecutive values, e.g. 4 3 5) beats **pair** (exactly two equal) beats **high** (everything else).
`hand_key(dice)` returns a tuple that compares correctly with `<` and `>`: `(3, v)` for a triple of `v`; `(2, top)` for a run with highest die `top`; `(1, pair value, kicker)` for a pair and its odd die; `(0, d1, d2, d3)` with the dice sorted from high to low for a high hand.
`best_hand(hands)` takes a list of hands and returns the *index* of the best one; the first of equal hands wins.""",
         voices=["Write the hand ranking for our three-dice game: `hand_key` and `best_hand` in `hands.py`, as described in README.md.",
                 "`hands.py`: implement `hand_key(dice)` and `best_hand(hands)` following README.md (triple, run, pair, high).",
                 "Who wins a showdown of three-dice hands? Implement `best_hand` (and the `hand_key` it relies on) per README.md."]),
    dict(slug="jumping-board", d=3, mod="board", fname="play", ref=BOARD_REF, stub=BOARD_STUB, gen=board_args, names="play", call="play(*args)", title="Race on a jumping board",
         spec="""`play(rolls, jumps, size=30)` simulates one token on a board of `size` squares. The token starts on square 0 and uses the rolls in order (one per step). For each roll:

* The token moves forward by the roll, or by *twice* the roll if the previous roll was a 6 (the doubling applies to the very next roll only; a doubled 6 still counts as a 6 for the roll after it).
* If that would pass `size` the token bounces back: new position `size - (position - size)`.
* Then, if the square is a key of `jumps` (a dict), the token moves to the value (no chained jumps: one jump per roll).
* Landing exactly on `size` (after bouncing and jumping) wins at once; the remaining rolls are ignored.
Return `(position, rolls used, won)`. With no rolls the result is `(0, 0, False)`. The inputs are not modified.""",
         voices=["Implement `play` in `board.py`: a token race with bouncing, jumps and a win on the exact last square (README.md).",
                 "Our board-game replayer needs `play(rolls, jumps, size=30)`; README.md has the bounce and jump rules and the return value.",
                 "Write the token race simulation from README.md in `board.py`. Careful with bouncing off the end and jumping after the bounce."]),
    dict(slug="run-length-log", d=2, mod="runlog", fname="decode", ref=LOG_REF, stub=LOG_STUB, gen=log_args, names="encode, decode", call=None, title="Compress a move log",
         spec="""Move logs are strings over the letters `L`, `R`, `S`. `encode(moves)` run-length encodes: every maximal run of one letter is written as the letter, followed by the run length in decimal when it is 2 or more (`"LLLSRR"` -> `"L3SR2"`). `decode(text)` is the inverse and also checks the text: a letter must be `L`, `R` or `S`, optionally followed by a count of 2 to 9999 (ASCII digits, no leading zero, not 0 or 1, at most 4 digits); adjacent runs of the same letter are fine (`"L2L3"` is five `L`).
Anything else raises `ValueError("bad log at <i>")` with `i` the 0-based index of the offending character: a bad letter, or the *first digit* of a bad count. The text is checked from left to right and the first problem is reported.""",
         voices=["Write `encode` and `decode` for our move logs in `runlog.py`; README.md has the format and the exact error message.",
                 "Run-length encoding of `L`/`R`/`S` logs (README.md) with strict decoding: `encode` and `decode` in `runlog.py`.",
                 "Implement the two functions in `runlog.py`. The decoder has to reject malformed logs with the message from README.md."]),
]


def _cases(spec: dict, rng, n: int, hidden: bool):
    mod = _load(spec["ref"], spec["mod"])
    out, seen = [], set()
    tries = 0
    while len(out) < n and tries < 2000:
        tries += 1
        args = spec["gen"](rng)
        args = args[0]
        key = repr(args)
        if key in seen:
            continue
        seen.add(key)
        out.append(args)
    return mod, out


def _test_cases(spec: dict, mod, arglist):
    cases = []
    for args in arglist:
        if spec["slug"] == "dice-hands":
            a = args[0]
            if isinstance(a[0], list):
                cases.append((("best", a), mod.best_hand(a)))
            else:
                cases.append((("key", a), mod.hand_key(a)))
        elif spec["slug"] == "run-length-log":
            a = args[0]
            if a and a[0] in "LRS" and all(c in "LRS" for c in a):
                cases.append((("enc", a), mod.encode(a)))
            r = _safe(mod.decode, (a,))
            cases.append((("dec", a), r[1] if r[0] == "ok" else ("error", r[1])))
        elif spec["slug"] == "tidepool-sowing":
            r = _safe(mod.sow, args)
            cases.append((tuple(args), r[1] if r[0] == "ok" else ("error", r[1])))
        elif spec["slug"] == "exact-shuffle":
            items, seed = args
            cases.append((("shuffle", items, seed), mod.shuffle(items, seed)))
            cases.append((("lcg", seed, len(items)), mod.lcg_values(seed, len(items))))
        else:
            fn = getattr(mod, spec["fname"])
            cases.append((tuple(args), fn(*args)))
    return cases


def _write_tests(spec: dict, cases: list, name: str) -> str:
    slug = spec["slug"]
    cls = "".join(p.title() for p in slug.split("-"))
    if slug == "dice-hands":
        body = HEAD_TEST.format(mod=spec["mod"], names=spec["names"], cases=_fmt(cases), cls=cls, call='(hand_key(args[1]) if args[0] == "key" else best_hand(args[1]))')
    elif slug == "run-length-log":
        body = HEAD_TEST.format(mod=spec["mod"], names=spec["names"], cases=_fmt(cases), cls=cls, call="run(args)")
        body = body.replace("class Test", "def run(args):\n    kind, text = args\n    if kind == 'enc':\n        return encode(text)\n    try:\n        return decode(text)\n    except ValueError as e:\n        return ('error', str(e))\n\n\nclass Test", 1)
    elif slug == "exact-shuffle":
        body = HEAD_TEST.format(mod=spec["mod"], names=spec["names"], cases=_fmt(cases), cls=cls, call="run(args)")
        body = body.replace("class Test", "def run(args):\n    if args[0] == 'lcg':\n        return lcg_values(args[1], args[2])\n    items = list(args[1])\n    out = shuffle(items, args[2])\n    assert items == list(args[1]), 'shuffle modified its argument'\n    return out\n\n\nclass Test", 1)
    elif slug == "tidepool-sowing":
        body = HEAD_TEST.format(mod=spec["mod"], names=spec["names"], cases=_fmt(cases), cls=cls, call="run(args)")
        body = body.replace("class Test", "def run(args):\n    pits = list(args[0])\n    try:\n        result = sow(pits, args[1])\n    except ValueError as e:\n        return ('error', str(e))\n    assert list(args[0]) == pits, 'sow modified its argument'\n    return result\n\n\nclass Test", 1)
    else:
        body = HEAD_TEST.format(mod=spec["mod"], names=spec["names"], cases=_fmt(cases), cls=cls, call=spec["call"])
    return body


def _fmt(cases) -> str:
    return "[\n" + "".join(f"    ({a!r}, {w!r}),\n" for a, w in cases) + "]"


@family("games-minis", category="games", lang="python", kind="greenfield", n=10,
        summary="ten small game-rule functions with exact specs: trick winner, sowing, initiative, seeded shuffle, line merge, word score, territory, dice hands, jumping board, move-log codec")
def gen(rng, n):
    for i, spec in enumerate(MINIS[:n]):
        mod, arglist = _cases(spec, rng, 3 + spec_n(spec), False)
        cases = _test_cases(spec, mod, arglist)
        vis_cases, hid_cases = cases[:3], cases[3:]
        mod_file = spec["mod"] + ".py"
        readme = f"# {spec['title']}\n\n{spec['spec']}\n\nThe module is `{mod_file}`; `python3 -m unittest discover -s tests -v` runs the examples in `tests/`.\n"
        start = {"README.md": readme, mod_file: spec["stub"], f"tests/test_{spec['mod']}.py": _write_tests(spec, vis_cases, "visible"), ".gitignore": _kit.GITIGNORE[LANG]}
        hidden = {f"tests/test_{spec['mod']}_hidden.py": _write_tests(spec, hid_cases, "hidden")}
        sol = {mod_file: spec["ref"]}
        yield Task(slug=f"{i + 1:02d}-{spec['slug']}", prompt=spec["voices"][i % 3], difficulty=spec["d"], start=start, hidden=hidden, solution=sol, verify=_kit._scen.VERIFY[LANG],
                   tags=["game-rules", "small"], notes={"mini": spec["slug"]})


def spec_n(spec: dict) -> int:
    return 40
