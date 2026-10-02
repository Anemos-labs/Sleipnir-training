"""Gloam (python): a roguelike turn engine with an energy-based speed system, doors, keys, traps and house rules.
Build, fix and save/load tasks."""
from __future__ import annotations

import json

from fx import Task, dd, family

from . import _kit, _scen
from ._kit import Bug

LANG = "python"
GAME = "Gloam"
DEFAULT = dict(HERO_HP=12, HERO_ATK=3, POTION=6, TRAP_DMG=2, SIGHT=6, COUNTER=False, REGEN=0, FIXED_SPEED=False)


def header(r: dict) -> str:
    return dd(f'''
        # ---- house rules for this dungeon (they are part of the specification, see README.md) ----
        HERO_HP = {r["HERO_HP"]}
        HERO_ATK = {r["HERO_ATK"]}
        POTION = {r["POTION"]}
        TRAP_DMG = {r["TRAP_DMG"]}
        SIGHT = {r["SIGHT"]}
        COUNTER = {r["COUNTER"]}
        REGEN = {r["REGEN"]}
        FIXED_SPEED = {r["FIXED_SPEED"]}
        # ------------------------------------------------------------------------------------------
    ''')


BODY = dd('''
    STATS = {"r": (3, 1, 100), "g": (6, 2, 60), "s": (4, 2, 150)}  # hp, attack, speed
    DIRS = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}
    ORDER = "UDLR"


    class Monster:
        def __init__(self, ident, kind, y, x):
            self.id = ident
            self.kind = kind
            self.y = y
            self.x = x
            self.hp, self.atk, speed = STATS[kind]
            self.speed = 100 if FIXED_SPEED else speed
            self.energy = 0


    class Game:
        def __init__(self, text):
            rows = text.split("\\n")
            self.h = len(rows)
            self.w = len(rows[0])
            self.grid = []
            self.monsters = []
            self.hero = [0, 0]
            for y, row in enumerate(rows):
                line = []
                for x, ch in enumerate(row):
                    if ch == "@":
                        self.hero = [y, x]
                        ch = "."
                    elif ch in STATS:
                        self.monsters.append(Monster("%s%d" % (ch, len(self.monsters) + 1), ch, y, x))
                        ch = "."
                    line.append(ch)
                self.grid.append(line)
            self.hp = HERO_HP
            self.keys = 0
            self.potions = 0
            self.tick = 0
            self.state = "playing"

        def _cell(self, y, x):
            if y < 0 or x < 0 or y >= self.h or x >= self.w:
                return "#"
            return self.grid[y][x]

        def _monster_at(self, y, x):
            for m in self.monsters:
                if m.y == y and m.x == x:
                    return m
            return None

        def legal_moves(self):
            if self.state != "playing":
                return []
            moves = []
            for name in ORDER:
                dy, dx = DIRS[name]
                cell = self._cell(self.hero[0] + dy, self.hero[1] + dx)
                if cell == "#" or (cell == "D" and self.keys == 0):
                    continue
                moves.append(name)
            moves.append("wait")
            if self.potions > 0 and self.hp < HERO_HP:
                moves.append("drink")
            return moves

        def apply(self, move):
            if move not in self.legal_moves():
                raise ValueError("illegal move: %r" % (move,))
            events = []
            if move == "wait":
                events.append("hero waits")
            elif move == "drink":
                heal = min(POTION, HERO_HP - self.hp)
                self.potions -= 1
                self.hp += heal
                events.append("hero drinks +%d" % heal)
            else:
                self._hero_step(move, events)
            if self.state == "playing":
                self._monsters_act(events)
            if self.state == "playing" and REGEN and (self.tick + 1) % REGEN == 0 and self.hp < HERO_HP:
                self.hp += 1
                events.append("hero regenerates")
            self.tick += 1
            return "; ".join(events)

        def _hero_step(self, move, events):
            dy, dx = DIRS[move]
            ty, tx = self.hero[0] + dy, self.hero[1] + dx
            cell = self._cell(ty, tx)
            mon = self._monster_at(ty, tx)
            if mon is not None:
                mon.hp -= HERO_ATK
                events.append("hero hits %s %d" % (mon.id, HERO_ATK))
                if mon.hp <= 0:
                    self.monsters.remove(mon)
                    events.append("%s dies" % mon.id)
                elif COUNTER:
                    self._hit_hero(mon, events)
                return
            if cell == "D":
                self.keys -= 1
                self.grid[ty][tx] = "."
                events.append("hero opens door")
                return
            self.hero = [ty, tx]
            events.append("hero moves")
            if cell == "k":
                self.keys += 1
                self.grid[ty][tx] = "."
                events.append("hero takes key")
            elif cell == "!":
                self.potions += 1
                self.grid[ty][tx] = "."
                events.append("hero takes potion")
            elif cell == "^" and TRAP_DMG > 0:
                self.hp -= TRAP_DMG
                events.append("spikes %d" % TRAP_DMG)
                if self.hp <= 0:
                    self.hp = 0
                    self.state = "lost"
                    events.append("hero dies")
            elif cell == ">":
                self.state = "won"
                events.append("hero reaches the stairs")

        def _hit_hero(self, mon, events):
            self.hp -= mon.atk
            events.append("%s hits hero %d" % (mon.id, mon.atk))
            if self.hp <= 0:
                self.hp = 0
                self.state = "lost"
                events.append("hero dies")

        def _monsters_act(self, events):
            for mon in list(self.monsters):
                mon.energy = min(mon.energy + mon.speed, 200)
                while mon.energy >= 100 and self.state == "playing":
                    dist = abs(mon.y - self.hero[0]) + abs(mon.x - self.hero[1])
                    if dist > SIGHT:
                        break
                    mon.energy -= 100
                    if dist == 1:
                        self._hit_hero(mon, events)
                    else:
                        best = None
                        for name in ORDER:
                            dy, dx = DIRS[name]
                            ny, nx = mon.y + dy, mon.x + dx
                            if self._cell(ny, nx) in "#D" or [ny, nx] == self.hero or self._monster_at(ny, nx):
                                continue
                            nd = abs(ny - self.hero[0]) + abs(nx - self.hero[1])
                            if nd < dist and (best is None or nd < best[0]):
                                best = (nd, ny, nx)
                        if best is not None:
                            mon.y, mon.x = best[1], best[2]
                            events.append("%s moves" % mon.id)
                if self.state != "playing":
                    break

        def render(self):
            rows = []
            for y in range(self.h):
                row = ""
                for x in range(self.w):
                    if [y, x] == self.hero:
                        row += "@"
                    else:
                        mon = self._monster_at(y, x)
                        row += mon.kind if mon else self.grid[y][x]
                rows.append(row)
            status = "HP %d/%d keys %d potions %d tick %d" % (self.hp, HERO_HP, self.keys, self.potions, self.tick)
            if self.state == "won":
                status += " WON"
            elif self.state == "lost":
                status += " LOST"
            return "\\n".join(rows + [status])

        def status(self):
            return self.state
''')


def engine(r: dict) -> str:
    return '"""Gloam: a roguelike turn engine. The rules are in README.md."""\n\n' + header(r) + "\n\n" + BODY


STUB = dd('''
    """Gloam: a roguelike turn engine. The rules and the API are in README.md."""


    class Game:
        def __init__(self, text):
            raise NotImplementedError

        def legal_moves(self):
            raise NotImplementedError

        def apply(self, move):
            raise NotImplementedError

        def render(self):
            raise NotImplementedError

        def status(self):
            raise NotImplementedError
''')

ADAPTER = {"tests/adapter.py": dd('''
    """Maps scenario commands onto the engine API (the scenario runner is tests/test_scenarios.py)."""
    import gloam


    class Adapter:
        def __init__(self):
            self.game = None

        def run(self, verb, args):
            if verb == "new":                     # new <map rows joined by |>
                self.game = gloam.Game(args.replace("|", "\\n"))
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
            if verb == "status":
                return self.game.status()
            raise KeyError(verb)
''')}


# ----------------------------------------------------------------------------------------------------- maps

HAND_MAPS = [
    "##########\n#@.k.D..>#\n##########",
    "###########\n#@..r.....#\n#...#.g...#\n#.!.#..s.>#\n#..^......#\n###########",
    "#########\n#@....g.#\n#.###.#.#\n#.#!..#.#\n#.#.###.#\n#...^..>#\n#########",
    "##########\n#@.s....>#\n#.r.g....#\n#..^.^...#\n##########",
    "#########\n#k.D....#\n#.#D###.#\n#@#.!#>.#\n#...r...#\n#########",
]


def random_map(rng, w: int, h: int) -> str:
    g = [["#"] * w for _ in range(h)]
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            g[y][x] = "#" if rng.randrange(100) < 14 else "."
    cells = [(y, x) for y in range(1, h - 1) for x in range(1, w - 1) if g[y][x] == "."]
    rng.shuffle(cells)
    need = 1 + rng.randint(2, 4) + 6
    if len(cells) < need:
        return random_map(rng, w, h)
    y, x = cells.pop()
    g[y][x] = "@"
    for _ in range(rng.randint(2, 4)):
        y, x = cells.pop()
        g[y][x] = rng.choice("rrgs")
    for ch in ["k", "D", ">", "!", "!", "^", "^"][: rng.randint(4, 7)]:
        y, x = cells.pop()
        g[y][x] = ch
    return "\n".join("".join(row) for row in g)


def scripts(rng, r: dict) -> dict[str, str]:
    parts = []
    for i, mp in enumerate(HAND_MAPS):
        row = mp.replace("\n", "|")
        parts.append(f"# scenario hand map {i + 1}\n> new {row}\n> legal\n> render\n~ rand 160 {rng.randrange(1, 900)} every=3 emit=render,legal,status junk=X|u|UU|0|Wait|drink up\n"
                     f"> new {row}\n~ rand 260 {rng.randrange(1, 900)} every=5 emit=render,status")
    rnd = []
    for i in range(6):
        mp = random_map(rng, rng.choice([9, 10, 11]), rng.choice([7, 8]))
        row = mp.replace("\n", "|")
        rnd.append(f"# scenario random map {i + 1}\n> new {row}\n~ rand 300 {rng.randrange(1, 900)} every=4 emit=render,legal,status junk=X|drink")
    edge = dd('''
        # scenario illegal moves
        > new ##########|#@.k.D..>#|##########
        > do X
        > do u
        > do drink
        > do U
        > do L
        > do D
        > do R
        > do R
        > do R
        > do R
        > do R
        > do R
        > do R
        > render
        > do R
        > do R
        > do R
        > do R
        > render
        > status
        > do R
        > legal
    ''')
    banked = []
    for kind in "rgs":
        row = f"##############|#@...........{kind}#|##############"
        banked.append(f"# scenario waiting then approaching {kind}\n> new {row}\n" + "\n".join(["> do wait"] * 14) + "\n> render\n" + "\n".join(["> do R"] * 10) + "\n> render\n> status")
        banked.append(f"# scenario two {kind} wake together\n> new ##############|#@..........{kind}.{kind}#|##############\n" + "\n".join(["> do wait"] * 9) + "\n" + "\n".join(["> do R"] * 9) + "\n> render\n> status")
    ambush = []
    for i, mp in enumerate(["#######|#.r.g.#|#.s@r.#|#.g.s.#|#######", "#####|#rgs#|#r@g#|#sg.#|#####", "########|#s.r..g#|#..@...#|#g...rs#|########"]):
        ambush.append(f"# scenario ambush {i + 1}\n> new {mp}\n> render\n" + "\n".join(["> do wait", "> legal"] * 9) + "\n> render\n> status")
        ambush.append(f"# scenario ambush fight {i + 1}\n> new {mp}\n~ rand 60 {rng.randrange(1, 900)} every=2 emit=render,status")
    return {"hidden_maps": "\n".join(parts) + "\n", "hidden_random": "\n".join(rnd) + "\n", "hidden_edge": edge, "hidden_banked": "\n".join(banked) + "\n",
            "hidden_ambush": "\n".join(ambush) + "\n"}


def example_script() -> str:
    return dd('''
        # scenario a corridor
        > new ##########|#@.k.D..>#|##########
        > render
        > legal
        > do R
        > do R
        > do R
        > render
        > do R
        > do R
        > render
        # scenario a rat
        > new #######|#@..r.#|#######
        > do R
        > do R
        > render
        > do R
        > do R
        > render
        > status
    ''')


def readme(r: dict) -> str:
    s = []
    s.append("# Gloam\n\nA tiny roguelike engine: one hero, a few monsters, doors, keys, potions, spikes and stairs. The engine is headless: a `Game` built from a map text, its legal moves "
             "and exact text for every reply. Time is discrete: the hero acts, then every monster gets its turn.\n")
    s.append("## Map\n\nThe map is a list of rows of equal length joined by `\\n`, surrounded by walls (cells outside the grid count as walls). Row 0 is the top. Characters:\n\n"
             "| char | meaning |\n|---|---|\n| `#` | wall |\n| `.` | floor |\n| `@` | the hero (on floor) |\n| `r` `g` `s` | a rat, goblin or spider (on floor) |\n"
             "| `k` | a key (on floor) |\n| `!` | a potion (on floor) |\n| `D` | a locked door |\n| `>` | the stairs: reaching them wins |\n" + ("| `^` | spikes |\n" if r["TRAP_DMG"] else "| `^` | spikes (harmless in this dungeon) |\n"))
    s.append(f"## State\n\nThe hero has `hp` (starts at {r['HERO_HP']}, never above {r['HERO_HP']}), attack {r['HERO_ATK']}, a number of `keys` and of `potions` (both start at 0) and the dungeon has a `tick` counter starting at 0. "
             "Monsters are numbered `1, 2, 3...` in reading order of the map (row by row, left to right) and named by their letter and number: `r1`, `g2`, `s3`. A monster never changes its name, "
             "and the numbers of dead monsters are not reused.\n")
    spd = "all monsters have speed 100" if r["FIXED_SPEED"] else "`r` 100, `g` 60, `s` 150"
    s.append("| monster | hp | attack | speed |\n|---|---|---|---|\n| `r` rat | 3 | 1 | " + ("100" if r["FIXED_SPEED"] else "100") + " |\n| `g` goblin | 6 | 2 | " + ("100" if r["FIXED_SPEED"] else "60") + " |\n| `s` spider | 4 | 2 | " + ("100" if r["FIXED_SPEED"] else "150") + " |\n")
    s.append("## The hero's action\n\nA move is one of `U` `D` `L` `R` (the cell above, below, left, right of the hero), `wait`, `drink` (exact strings). `legal_moves()` lists the legal ones; a direction is legal unless "
             "the target cell is a wall or a locked door while the hero has no key; `wait` is always legal; `drink` is legal when the hero has a potion and `hp` is below the maximum. When the game "
             "is over (`won` or `lost`) there are no legal moves. Resolving a move, in order of the first rule that applies:\n")
    rules = [
        "A monster stands on the target cell: the hero *attacks* it. The monster loses " + str(r["HERO_ATK"]) + " hp; event `hero hits <id> " + str(r["HERO_ATK"]) + "`. At 0 hp or less it dies and is removed: event `<id> dies`." +
        (f" If it survives it immediately hits back (this is not its turn: no energy is spent): event `<id> hits hero <attack>`, the hero loses that much hp (see *death* below)." if r["COUNTER"] else ""),
        "The target is a locked door (the hero has a key): the key is used up, the door becomes floor `.`, the hero stays where he is. Event `hero opens door`.",
        "Otherwise the hero moves to the target cell. Event `hero moves`. Then, depending on the cell: `k` is picked up (`keys` +1, the cell becomes `.`, event `hero takes key`); `!` is picked up (`potions` +1, "
        "cell becomes `.`, event `hero takes potion`); " + (f"`^` costs {r['TRAP_DMG']} hp (event `spikes {r['TRAP_DMG']}`, see *death*); " if r["TRAP_DMG"] else "`^` does nothing; ") +
        "`>` ends the game: the state becomes `won`, event `hero reaches the stairs`.",
    ]
    s.append("\n".join(f"{i + 1}. {t}" for i, t in enumerate(rules)) + "\n")
    s.append(f"* `wait`: event `hero waits`.\n* `drink`: the hero heals `min({r['POTION']}, max_hp - hp)`, one potion is used; event `hero drinks +<healed>`.\n")
    s.append("*Death*: whenever the hero's `hp` drops to 0 or below (by spikes or a monster hit) it is set to 0, the state becomes `lost` and the event `hero dies` follows the event that caused it; the rest of "
             "that tick (including all later monsters) is skipped.\n")
    s.append("## The monsters' turn\n\nIf after the hero's action the game is still running, the monsters act, **in order of their numbers** (the number of a monster is part of its name, so `g2` acts before `r5`). Each monster in turn "
             "does the following.\n")
    mon = [
        "Its `energy` first increases by its speed, but never above 200 (`energy = min(energy + speed, 200)`). Energy starts at 0.",
        f"While `energy >= 100` (and the hero is alive) the monster looks at the Manhattan distance `d` between itself and the hero. If `d` is more than {r['SIGHT']} (out of sight) the monster does nothing and *keeps* its energy: the loop ends. "
        "Otherwise it spends 100 energy and acts once, so a monster can act twice in one tick (speed 150, or a banked 200) or skip a tick (speed 60). The action:",
        "  * if `d` is 1 (orthogonally adjacent) it hits the hero: event `<id> hits hero <attack>`; the hero loses that much hp (*death* above).",
        "  * otherwise it steps towards the hero. Candidate cells are the four neighbours in the order `U D L R` that are not walls, not locked doors, not the hero's "
        "cell and not occupied by another monster, and whose Manhattan distance to the hero is *strictly smaller* than `d`. The candidate with the smallest distance wins, the first one in the order "
        "`U D L R` on ties. Event `<id> moves`. If there is no candidate the monster stays and nothing is reported (the energy is spent all the same).",
    ]
    s.append("\n".join(f"{'' if t.startswith('  ') else str(sum(1 for q in mon[:mon.index(t) + 1] if not q.startswith('  '))) + '. '}{t}" for t in mon) + "\n")
    s.append("## End of the tick\n\n" + (f"If the game is still running and `(tick + 1)` is a multiple of {r['REGEN']} and the hero has less than the maximum hp, the hero regains 1 hp (event `hero regenerates`). " if r["REGEN"] else "") +
             "Then `tick` increases by one (for every legal move, also for the move that won or lost the game). `apply` returns all events of the move in the order they happened, joined by `; `.\n")
    s.append("## API (`gloam.py`)\n\n```python\nimport gloam\ng = gloam.Game(map_text)   # rows joined by \"\\n\"\ng.legal_moves()            # list of move strings (any order); [] when the game is over\n"
             "g.apply(move)              # plays a legal move and returns the events text; ValueError otherwise, state unchanged\ng.render()                 # the map and a status line (below)\n"
             "g.status()                 # 'playing', 'won' or 'lost'\n```\n")
    s.append("### `render()`\n\nThe map rows as they are now (hero `@`, monsters by their letter, doors, keys, potions, spikes and stairs as long as they exist), then a status line, joined by `\\n`, no trailing newline: "
             "`HP <hp>/<max> keys <keys> potions <potions> tick <tick>` followed by ` WON` or ` LOST` when the game is over. Example:\n\n```\n#######\n#.@.r.#\n#######\nHP 12/12 keys 0 potions 0 tick 1\n```\n")
    s.append("## Tests\n\n`python3 -m unittest discover -s tests -v` replays the scenario files in `tests/data/` (`tests/adapter.py` shows how the API is called; the format is described at the top of `tests/test_scenarios.py`).\n")
    return "\n".join(s)


def project(r: dict) -> dict[str, str]:
    return {"gloam.py": engine(r), ".gitignore": _kit.GITIGNORE[LANG]}


def _variants(n: int) -> list[dict]:
    plan = [
        dict(),
        dict(COUNTER=True),
        dict(FIXED_SPEED=True, TRAP_DMG=0, SIGHT=8),
        dict(REGEN=3, HERO_HP=10, HERO_ATK=2),
        dict(COUNTER=True, REGEN=4, SIGHT=4, POTION=4, TRAP_DMG=3),
        dict(FIXED_SPEED=True, COUNTER=True, REGEN=2, HERO_ATK=4, SIGHT=5),
        dict(HERO_HP=8, HERO_ATK=3, POTION=8, SIGHT=10, TRAP_DMG=1, REGEN=5),
    ]
    return [{**DEFAULT, **o} for o in plan[:n]]


@family("games-gloam-build", category="games", lang="python", kind="greenfield", n=7,
        summary="build the Gloam roguelike turn engine (energy speeds, chase rules, doors and keys, counter-attacks, regeneration)")
def gen_build(rng, n):
    used: list[str] = []
    for i, r in enumerate(_variants(n)):
        sol = project(r)
        hidden = _kit.data_files(LANG, scripts(rng, r), sol, ADAPTER)
        vis = _kit.data_files(LANG, {"examples": example_script()}, sol, ADAPTER)
        start = {"README.md": readme(r), "gloam.py": STUB, ".gitignore": _kit.GITIGNORE[LANG], **_scen.check_files(LANG, ADAPTER), **vis}
        extras = r["COUNTER"] + (r["REGEN"] > 0) + (not r["FIXED_SPEED"])
        d = min(5, 2 + extras + (r["SIGHT"] != 6 and r["TRAP_DMG"] != 2))
        prompt = _kit.green_prompt(rng, game=GAME, blurb="a small roguelike engine where the hero and the monsters take turns on an energy system", file="gloam.py",
                                   verify=_scen.VERIFY[LANG], used=used)
        feats = ["energy" if not r["FIXED_SPEED"] else "fixed", "counter" if r["COUNTER"] else "", "regen" if r["REGEN"] else ""]
        yield Task(slug=f"{i + 1:02d}-" + "-".join(f for f in feats if f), prompt=prompt, difficulty=d, start=start, hidden=hidden, solution={"gloam.py": sol["gloam.py"]},
                   verify=_scen.VERIFY[LANG], tags=["roguelike", "turn-order", "scenarios"], notes={"rules": r})


BUGS = [
    Bug("monster-order", "Monsters act in the wrong order",
        "When two monsters are next to the hero in the same tick the hits are reported in a different order than the monster numbers: the higher-numbered monster hits first. It matters when the hero has little hp left: who gets the killing blow changes.",
        [("for mon in list(self.monsters):", "for mon in reversed(list(self.monsters)):")], difficulty=3),
    Bug("energy-cap", "Idle monsters bank too much energy",
        "A monster that waited far away for a long time gets several attacks in a row the moment the hero comes close, instead of at most two actions in a tick.",
        [("mon.energy = min(mon.energy + mon.speed, 200)", "mon.energy = mon.energy + mon.speed")], difficulty=3),
    Bug("hero-dies-continue", "Monsters keep hitting after the hero is dead",
        "After the hero's hp reaches zero the report still lists further hits from other monsters in the same tick; the hero is dead, so the rest of the tick should be skipped.",
        [('while mon.energy >= 100 and self.state == "playing":', "while mon.energy >= 100:"), ('if self.state != "playing":\n                break', "if False:\n                break")], difficulty=3),
    Bug("sight-chebyshev", "Monsters notice the hero from too far away",
        "Monsters start chasing from farther away than the sight range in the README when the hero is diagonal to them: the range seems to be measured as a square instead of as steps along the corridors.",
        [("if dist > SIGHT:", "if max(abs(mon.y - self.hero[0]), abs(mon.x - self.hero[1])) > SIGHT:")], difficulty=3),
    Bug("tie-break", "Chasing monsters take the wrong route around obstacles",
        "When a monster can approach the hero by two equally good steps it picks a different one than the README's U D L R order says (it seems to prefer the horizontal step).",
        [('ORDER = "UDLR"', 'ORDER = "LRUD"')], difficulty=3),
    Bug("trap-damage", "Spikes do the wrong damage",
        "Walking onto spikes hurts less than it should: the hp lost is one less than the dungeon's spike damage.",
        [("self.hp -= TRAP_DMG", "self.hp -= TRAP_DMG - 1")], difficulty=2, rules=dict(TRAP_DMG=3)),
    Bug("potion-overheal", "Potions can heal above the maximum",
        "Drinking a potion when almost at full hp pushes the hero above the maximum (e.g. 14/12) and the status line shows it.",
        [("heal = min(POTION, HERO_HP - self.hp)", "heal = POTION")], difficulty=2),
    Bug("door-key", "Doors don't use up the key",
        "Opening a door does not consume the key: I can open every door in the level with a single key.",
        [('self.keys -= 1\n            self.grid[ty][tx] = "."\n            events.append("hero opens door")', 'self.grid[ty][tx] = "."\n            events.append("hero opens door")')], difficulty=2),
    Bug("counter-energy", "Counter-attacks cost the monster its turn",
        "With counter-attacks on, a monster that hits back after being hit then does not get to act in the monster phase, as if it had spent its energy.",
        [("elif COUNTER:\n                self._hit_hero(mon, events)", "elif COUNTER:\n                mon.energy = 0\n                self._hit_hero(mon, events)")], difficulty=3, rules=dict(COUNTER=True)),
    Bug("tick-on-win", "The tick counter stops when the game ends",
        "The tick counter in the status line shows one less than the number of actions when the game has ended (won or lost): the final action isn't counted.",
        [('self.tick += 1\n        return "; ".join(events)', 'if self.state == "playing":\n            self.tick += 1\n        return "; ".join(events)')], difficulty=2),
    Bug("regen-timing", "Regeneration happens one tick early",
        "Hit point regeneration kicks in on the wrong tick: with regeneration every 3 ticks the hero is healed after 2 actions rather than 3.",
        [("(self.tick + 1) % REGEN == 0", "self.tick % REGEN == 0")], difficulty=3, rules=dict(REGEN=3)),
    Bug("monster-door", "Monsters walk through doors",
        "Monsters get to the other side of locked doors: they open them by walking through (the door disappears from the map).",
        [('if self._cell(ny, nx) in "#D" or', 'if self._cell(ny, nx) in "#" or')], difficulty=3, rules=dict(SIGHT=10)),
    Bug("dead-id", "Monster names change after a death",
        "After a monster dies the others are renumbered in the report: `g3` becomes `g2`. Names should never change.",
        [("self.monsters.remove(mon)\n", 'self.monsters.remove(mon)\n                for k, other in enumerate(self.monsters):\n                    other.id = "%s%d" % (other.kind, k + 1)\n')], difficulty=3),
]

# a no-op first edit of some bugs above is only there to keep the target readable; strip identity edits
BUGS = [Bug(b.id, b.title, b.symptom, [e for e in b.edits if e[0] != e[1]], b.path, b.difficulty, b.rules, b.detail) for b in BUGS]
_B = {b.id: b for b in BUGS}
BUGS_ALL = BUGS + [
    _kit.combine(_B["trap-damage"], _B["potion-overheal"], difficulty=3),
    _kit.combine(_B["monster-order"], _B["tick-on-win"], _B["door-key"], difficulty=4),
    _kit.combine(_B["energy-cap"], _B["tie-break"], _B["hero-dies-continue"], difficulty=5),
]


@family("games-gloam-fix", category="games", lang="python", kind="fix", n=15,
        summary="hand-injected defects in the Gloam engine (turn order, energy, chase rules, doors, death handling, render)")
def gen_fix(rng, n):
    used: list[str] = []
    cache = {}
    for k, bug in enumerate(BUGS_ALL[:n]):
        r = {**DEFAULT, **bug.rules}
        key = json.dumps(r, sort_keys=True)
        if key not in cache:
            sol = project(r)
            cache[key] = (sol, _kit.data_files(LANG, scripts(rng, r), sol, ADAPTER), _kit.data_files(LANG, {"examples": example_script()}, sol, ADAPTER), readme(r))
        sol, hidden, vis, rd = cache[key]
        base = {**sol, "README.md": rd}
        tests = {**_scen.check_files(LANG, ADAPTER), **vis}
        ctx = {"files": ["gloam.py"], "verify": _scen.VERIFY[LANG]}
        yield _kit.bug_task(game=GAME, lang=LANG, base_files=base, tests=tests, hidden=hidden, bug=bug, ctx=ctx, rng=rng, used=used, k=k,
                            tags=["roguelike", "turn-order"], extra_notes={"rules": r})


# ----------------------------------------------------------------------------------------------------- features

def _indent_blocks(blocks: list[str]) -> str:
    return "".join("    " + line + "\n" for b in blocks for line in b.split("\n") if line)


def _adapter_with(blocks: list[str], new_block: str | None = None) -> dict[str, str]:
    a = ADAPTER["tests/adapter.py"]
    target = "        raise KeyError(verb)\n"
    assert a.count(target) == 1
    if new_block is not None:
        old = '        if verb == "new":                     # new <map rows joined by |>\n            self.game = gloam.Game(args.replace("|", "\\n"))\n            return "ok"\n'
        assert a.count(old) == 1, "adapter new block"
        a = a.replace(old, new_block)
    return {"tests/adapter.py": a.replace(target, _indent_blocks(blocks) + target)}


def _enc(text: str) -> str:
    return text.replace("\n", "\\n")


def _unenc(text: str) -> str:
    return text.replace("\\n", "\n")


def _ck(body: str) -> int:
    return sum(ord(c) * (i + 1) for i, c in enumerate(body)) % 65521


SAVE_V1 = '''
    def save(self):
        lines = [
            "GLOAM-SAVE 1",
            "tick %d state %s" % (self.tick, self.state),
            "hero %d %d hp %d keys %d potions %d" % (self.hero[0], self.hero[1], self.hp, self.keys, self.potions),
            "grid",
        ]
        lines += ["".join(row) for row in self.grid]
        lines.append("end")
        for m in self.monsters:
            lines.append("monster %s %s %d %d hp %d energy %d" % (m.id, m.kind, m.y, m.x, m.hp, m.energy))
        return "\\n".join(lines)

    @classmethod
    def load(cls, text):
        lines = text.split("\\n")
        try:
            if lines[0] != "GLOAM-SAVE 1":
                raise ValueError
            t = lines[1].split(" ")
            if len(t) != 4 or t[0] != "tick" or t[2] != "state" or t[3] not in ("playing", "won", "lost"):
                raise ValueError
            h = lines[2].split(" ")
            if len(h) != 9 or [h[0], h[3], h[5], h[7]] != ["hero", "hp", "keys", "potions"]:
                raise ValueError
            if lines[3] != "grid":
                raise ValueError
            end = lines.index("end")
            grid = [list(r) for r in lines[4:end]]
            if not grid or any(len(r) != len(grid[0]) for r in grid):
                raise ValueError
            game = cls.__new__(cls)
            game.h, game.w = len(grid), len(grid[0])
            game.grid = grid
            game.tick = int(t[1])
            game.state = t[3]
            game.hero = [int(h[1]), int(h[2])]
            game.hp, game.keys, game.potions = int(h[4]), int(h[6]), int(h[8])
            game.monsters = []
            for line in lines[end + 1:]:
                f = line.split(" ")
                if len(f) != 9 or f[0] != "monster" or f[2] not in STATS or [f[5], f[7]] != ["hp", "energy"]:
                    raise ValueError
                mon = Monster(f[1], f[2], int(f[3]), int(f[4]))
                mon.hp, mon.energy = int(f[6]), int(f[8])
                game.monsters.append(mon)
            return game
        except (ValueError, IndexError):
            raise ValueError("bad save")
'''

SAVE_V2 = '''
    def save(self):
        lines = [
            "tick %d state %s" % (self.tick, self.state),
            "hero %d %d hp %d keys %d potions %d" % (self.hero[0], self.hero[1], self.hp, self.keys, self.potions),
            "grid",
        ]
        lines += ["".join(row) for row in self.grid]
        lines.append("end")
        for m in self.monsters:
            lines.append("monster %s %s %d %d hp %d energy %d" % (m.id, m.kind, m.y, m.x, m.hp, m.energy))
        body = "\\n".join(lines)
        return "GLOAM-SAVE 2 %d\\n%s" % (_checksum(body), body)

    @classmethod
    def load(cls, text):
        head, _, body = text.partition("\\n")
        parts = head.split(" ")
        if len(parts) != 3 or parts[0] != "GLOAM-SAVE" or parts[1] != "2" or not parts[2].isdigit():
            raise ValueError("bad header")
        if int(parts[2]) != _checksum(body):
            raise ValueError("checksum mismatch")
        lines = body.split("\\n")
        if "end" not in lines:
            raise ValueError("missing end")
        end = lines.index("end")
        grid = [list(r) for r in lines[3:end]]
        if not grid or any(len(r) != len(grid[0]) for r in grid):
            raise ValueError("ragged grid")
        game = cls.__new__(cls)
        t, h = lines[0].split(" "), lines[1].split(" ")
        game.h, game.w = len(grid), len(grid[0])
        game.grid = grid
        game.tick = int(t[1])
        game.state = t[3]
        game.hero = [int(h[1]), int(h[2])]
        game.hp, game.keys, game.potions = int(h[4]), int(h[6]), int(h[8])
        if not (0 <= game.hero[0] < game.h and 0 <= game.hero[1] < game.w) or grid[game.hero[0]][game.hero[1]] == "#":
            raise ValueError("bad hero position")
        game.monsters = []
        for line in lines[end + 1:]:
            f = line.split(" ")
            if f[2] not in STATS:
                raise ValueError("unknown monster kind '%s'" % f[2])
            mon = Monster(f[1], f[2], int(f[3]), int(f[4]))
            mon.hp, mon.energy = int(f[6]), int(f[8])
            game.monsters.append(mon)
        return game
'''

CHECKSUM_FN = '''

def _checksum(body):
    return sum(ord(c) * (i + 1) for i, c in enumerate(body)) % 65521
'''

SAVE_ADAPT = ['''
    if verb == "save":                    # save: the save text
        return self.game.save()
    if verb == "load":                    # load <save text, "\\\\n" escapes expanded>: "ok" or "error: <message>"
        try:
            self.game = gloam.Game.load(args.replace("\\\\n", "\\n"))
            return "ok"
        except ValueError as e:
            return "error: " + str(e)
    if verb == "reload":                  # save the game and load the text into a new game: "same" or "different"
        text = self.game.save()
        self.game = gloam.Game.load(text)
        return "same" if self.game.save() == text else "different"
''']


def save_scripts(rng, r: dict, sol: dict, adapter: dict, v: str) -> dict[str, str]:
    play = []
    maps = HAND_MAPS[1:4] + [random_map(rng, 10, 8)]
    for i, mp in enumerate(maps):
        row = mp.replace("\n", "|")
        sd = rng.randrange(1, 900)
        play.append(f"# scenario save and resume {i + 1}\n> new {row}\n~ rand 25 {sd} emit=render\n> save\n> reload\n> render\n~ rand 60 {sd + 1} every=5 emit=render,status\n> save\n> reload\n"
                    f"~ rand 80 {sd + 2} every=9 emit=render,status")
    play.append("# scenario save of a fresh game\n> new " + HAND_MAPS[0].replace("\n", "|") + "\n> save\n> reload\n> save\n> do R\n> save")
    recorded = list(_kit.data_files(LANG, {"s1": "\n".join(play) + "\n"}, sol, adapter).values())[0]
    lines = recorded.split("\n")
    saves = [_unenc(lines[i + 1][2:]) for i, ln in enumerate(lines) if ln == "> save" and lines[i + 1].startswith("= GLOAM")]
    good = saves[2]
    variants = [good, saves[0], saves[-1]]
    gl = good.split("\n")
    if v == "v1":
        bad = [
            "", "nonsense", "GLOAM-SAVE 2\n" + "\n".join(gl[1:]), "\n".join(gl[:5]),
            "\n".join(gl[:1] + ["tick x state playing"] + gl[2:]), "\n".join(gl[:2] + ["hero 1 1 hp 3 keys 0"] + gl[3:]),
            "\n".join(gl[:3] + ["grid "] + gl[4:]), good.replace("\nend", "\nstop"), good + "\nmonster q1 q 1 1 hp 3 energy 0",
            good + "\nmonster r1 r 1 1 hp x energy 0", "\n".join(gl[:4] + [gl[4], gl[5][:-1]] + gl[6:]),
        ]
    else:
        body = "\n".join(gl[1:])
        bl = body.split("\n")

        def with_ck(b: str) -> str:
            return f"GLOAM-SAVE 2 {_ck(b)}\n{b}"
        end_i = bl.index("end")
        bad = [
            "", "nonsense", f"GLOAM-SAVE 1 {_ck(body)}\n{body}", "GLOAM-SAVE 2\n" + body, "GLOAM-SAVE 2 x1\n" + body,
            good.replace("GLOAM-SAVE 2 ", "GLOAM-SAVE 2 9", 1), good[:-1] + ("0" if good[-1] != "0" else "1"),
            with_ck("\n".join(bl[:end_i] + bl[end_i + 1:])), with_ck(body.replace("\nend", "\nstop")),
            with_ck("\n".join(bl[:4] + [bl[4][:-1]] + bl[5:])), with_ck(body + "\nmonster q1 q 1 1 hp 3 energy 0"),
            with_ck("\n".join([bl[0], "hero 99 99 hp 3 keys 0 potions 0"] + bl[2:])), with_ck("\n".join([bl[0], "hero 0 0 hp 3 keys 0 potions 0"] + bl[2:])),
        ]
    cases = [f"> load {_enc(b)}\n> render\n> new {HAND_MAPS[0].replace(chr(10), '|')}" for b in variants + bad]
    script = "# scenario loading\n> new " + HAND_MAPS[0].replace("\n", "|") + "\n" + "\n".join(cases) + "\n"
    return {"hidden_play": "\n".join(play) + "\n", "hidden_load": script}


# -- throwing daggers ------------------------------------------------------------------------------------

THROW_EDITS = [
    ("self.potions = 0\n        self.tick = 0", "self.potions = 0\n        self.daggers = 0\n        self.tick = 0"),
    ('        if self.potions > 0 and self.hp < HERO_HP:\n            moves.append("drink")',
     '        if self.potions > 0 and self.hp < HERO_HP:\n            moves.append("drink")\n        if self.daggers > 0:\n            moves.extend("throw " + d for d in ORDER)'),
    ('        elif move == "drink":', '        elif move.startswith("throw "):\n            self._throw(move[6], events)\n        elif move == "drink":'),
    ('        elif cell == "!":\n            self.potions += 1\n            self.grid[ty][tx] = "."\n            events.append("hero takes potion")',
     '        elif cell == "!":\n            self.potions += 1\n            self.grid[ty][tx] = "."\n            events.append("hero takes potion")\n        elif cell == "/":\n            self.daggers += 1\n            self.grid[ty][tx] = "."\n            events.append("hero takes dagger")'),
    ('status = "HP %d/%d keys %d potions %d tick %d" % (self.hp, HERO_HP, self.keys, self.potions, self.tick)',
     'status = "HP %d/%d keys %d potions %d daggers %d tick %d" % (self.hp, HERO_HP, self.keys, self.potions, self.daggers, self.tick)'),
]
THROW_APPEND = '''
    def _throw(self, direction, events):
        dy, dx = DIRS[direction]
        self.daggers -= 1
        events.append("hero throws %s" % direction)
        y, x = self.hero
        for _ in range(4):
            y, x = y + dy, x + dx
            if self._cell(y, x) in "#D":
                break
            mon = self._monster_at(y, x)
            if mon is not None:
                mon.hp -= 2
                events.append("hero hits %s 2" % mon.id)
                if mon.hp <= 0:
                    self.monsters.remove(mon)
                    events.append("%s dies" % mon.id)
                return
        events.append("dagger is lost")
'''

# -- several levels ----------------------------------------------------------------------------------------

LEVELS_EDITS = [
    ('    def __init__(self, text):\n        rows = text.split("\\n")\n        self.h = len(rows)\n        self.w = len(rows[0])\n        self.grid = []\n        self.monsters = []\n        self.hero = [0, 0]\n',
     '    def __init__(self, text):\n        self.maps = text.split("\\n---\\n")\n        self.level = 0\n        self.hp = HERO_HP\n        self.keys = 0\n        self.potions = 0\n        self.tick = 0\n        self.state = "playing"\n        self._enter(0)\n\n    def _enter(self, index):\n        self.level = index\n        rows = self.maps[index].split("\\n")\n        self.h = len(rows)\n        self.w = len(rows[0])\n        self.grid = []\n        self.monsters = []\n        self.hero = [0, 0]\n'),
    ('            self.grid.append(line)\n        self.hp = HERO_HP\n        self.keys = 0\n        self.potions = 0\n        self.tick = 0\n        self.state = "playing"\n', '            self.grid.append(line)\n'),
    ('        elif cell == ">":\n            self.state = "won"\n            events.append("hero reaches the stairs")',
     '        elif cell == ">":\n            if self.level + 1 < len(self.maps):\n                self._enter(self.level + 1)\n                self.keys = 0\n                events.append("hero descends to level %d" % (self.level + 1))\n            else:\n                self.state = "won"\n                events.append("hero reaches the stairs")'),
    ('status = "HP %d/%d keys %d potions %d tick %d" % (self.hp, HERO_HP, self.keys, self.potions, self.tick)',
     'status = "HP %d/%d keys %d potions %d level %d/%d tick %d" % (self.hp, HERO_HP, self.keys, self.potions, self.level + 1, len(self.maps), self.tick)'),
]

# -- bats ----------------------------------------------------------------------------------------------------

BAT_EDITS = [
    ('STATS = {"r": (3, 1, 100), "g": (6, 2, 60), "s": (4, 2, 150)}  # hp, attack, speed', 'STATS = {"r": (3, 1, 100), "g": (6, 2, 60), "s": (4, 2, 150), "b": (2, 1, 100)}  # hp, attack, speed'),
    ('    def __init__(self, text):\n        rows = text.split("\\n")', '    def __init__(self, text, seed=0):\n        self.rng = seed & 0x7FFFFFFF\n        rows = text.split("\\n")'),
    ('                dist = abs(mon.y - self.hero[0]) + abs(mon.x - self.hero[1])\n                if dist > SIGHT:\n                    break\n                mon.energy -= 100\n                if dist == 1:\n                    self._hit_hero(mon, events)\n                else:',
     '                dist = abs(mon.y - self.hero[0]) + abs(mon.x - self.hero[1])\n                if dist > SIGHT and mon.kind != "b":\n                    break\n                mon.energy -= 100\n                if dist == 1:\n                    self._hit_hero(mon, events)\n                elif mon.kind == "b":\n                    self._flutter(mon, events)\n                else:'),
]
BAT_APPEND = '''
    def _next(self):
        self.rng = (self.rng * 1103515245 + 12345) & 0x7FFFFFFF
        return self.rng

    def _flutter(self, mon, events):
        pick = (self._next() >> 16) % 5
        if pick == 4:
            return
        dy, dx = DIRS[ORDER[pick]]
        ny, nx = mon.y + dy, mon.x + dx
        if self._cell(ny, nx) in "#D" or [ny, nx] == self.hero or self._monster_at(ny, nx):
            return
        mon.y, mon.x = ny, nx
        events.append("%s flutters" % mon.id)
'''

FEATURES = [
    dict(key="save-text", d=3, ask="Add saving and loading to the Gloam engine: `Game.save()` returns a text and `Game.load(text)` rebuilds the game from it. The exact text format and the behaviour on bad input are in "
                              "the new README section; the point is that a loaded game continues exactly like the original."),
    dict(key="save-checked", d=4, ask="Players share Gloam save files and sometimes mangle them. Implement `Game.save()` and `Game.load(text)` as specified in README.md: a checksum in the header, and a distinct "
                                "error message for every kind of damage, because the launcher shows the message to the player."),
    dict(key="daggers", d=3, ask="New item for the Gloam dungeon: daggers (`/` on the map) that the hero can throw along a line. README.md has the new section with the exact rules for picking them up, the `throw` "
                           "moves, their events and the changed status line. Don't change anything else."),
    dict(key="levels", d=4, ask="Gloam should support a dungeon of several levels: the map text may contain several maps separated by `---` lines, and the stairs of a level lead to the next one. The details (what "
                          "carries over, the events, the status line) are in the new README section."),
    dict(key="bats", d=4, ask="Add bats to Gloam. They flutter around at random, and the randomness has to be exactly reproducible: README.md specifies the generator and the way the engine draws from it. "
                        "A new optional `seed` argument of `Game` starts the generator."),
]


def feature_readme_section(key: str) -> str:
    if key == "save-text":
        return dd('''
            ## Feature to add: saving and loading

            `g.save()` returns the complete state as text and `Game.load(text)` (a class method) returns a new game that continues exactly like the saved one. The text is, with lines joined by `\\n`
            and no trailing newline:

            ```
            GLOAM-SAVE 1
            tick <tick> state <playing|won|lost>
            hero <row> <col> hp <hp> keys <keys> potions <potions>
            grid
            <the current map rows: terrain only, without the hero and the monsters; floor under them is `.`>
            end
            monster <id> <kind> <row> <col> hp <hp> energy <energy>      (one line per living monster, in order of the numbers)
            ```

            For example a fresh game on a 3x5 map with one rat starts with `GLOAM-SAVE 1`, `tick 0 state playing`, `hero 1 1 hp 12 keys 0 potions 0`, `grid`, the three rows, `end`, `monster r1 r 1 3 hp 3 energy 0`.
            `load` raises `ValueError("bad save")` when the text is not in exactly this format (wrong header, missing or malformed line, a monster kind that does not exist, rows of different lengths, text that is not
            numbers where numbers belong, no `end` line). `load(g.save()).save() == g.save()` for every game, and the loaded game plays on identically. The scenario adapter knows `save`, `load <text>` and `reload`.
        ''')
    if key == "save-checked":
        return dd('''
            ## Feature to add: saving and loading with a checksum

            `g.save()` returns the state as text and `Game.load(text)` (a class method) returns a new game that continues exactly like the saved one. The text, with lines joined by `\\n` and no trailing newline, is a
            header line followed by the *body*:

            ```
            GLOAM-SAVE 2 <checksum>
            tick <tick> state <playing|won|lost>
            hero <row> <col> hp <hp> keys <keys> potions <potions>
            grid
            <the current map rows: terrain only, without the hero and the monsters; floor under them is `.`>
            end
            monster <id> <kind> <row> <col> hp <hp> energy <energy>      (one line per living monster, in order of the numbers)
            ```

            The body is everything after the first `\\n` (the lines `tick ...` to the last monster line, joined by `\\n`). `checksum = (sum of ord(c) * (i + 1) for every character c at index i of the body) mod 65521`.
            `load` raises `ValueError` with exactly one of these messages, checking in this order and reporting the first problem: `bad header` (the first line is not `GLOAM-SAVE 2 <digits>` with exactly those three
            space-separated parts); `checksum mismatch`; `missing end` (no line equal to `end`); `ragged grid` (no map rows, or rows of different lengths); `bad hero position` (outside the grid, or on a `#`);
            `unknown monster kind 'x'` (a monster line whose kind is not `r`, `g` or `s`, `x` being the kind as written). Beyond that the text of a body with a valid checksum is trusted: the engine's own saves
            are always well formed. `load(g.save()).save() == g.save()` for every game and the loaded game plays on identically. The scenario adapter knows `save`, `load <text>` and `reload`.
        ''')
    if key == "daggers":
        return dd('''
            ## Feature to add: daggers

            * The map character `/` is a dagger lying on the floor. The hero keeps a count `daggers` (starts at 0). Stepping onto it picks it up (`daggers` +1, the cell becomes `.`), after `hero moves`: event `hero takes dagger`.
            * New moves `throw U`, `throw D`, `throw L`, `throw R` (exact strings), legal exactly when `daggers > 0`, in addition to the existing ones. A throw uses up one dagger and is the hero's action for the tick:
              event `hero throws <dir>` (dir is the letter). The dagger flies up to 4 cells in the direction, starting at the cell next to the hero. It stops at the first wall or locked door (it never passes them). It hits the first
              monster it meets: that monster loses 2 hp, event `hero hits <id> 2`, and `<id> dies` follows when it reaches 0 hp or less. A monster hit by a dagger does not counter-attack. If the dagger meets nothing within range
              the event `dagger is lost` follows. After the throw the monsters act as usual.
            * The status line of `render()` gets the dagger count between potions and tick: `HP 12/12 keys 0 potions 0 daggers 1 tick 3`.
        ''')
    if key == "levels":
        return dd('''
            ## Feature to add: several levels

            * The text given to `Game` may hold several maps separated by a line that is exactly `---` (that is, the maps are joined by `\\n---\\n`). A text without `---` is a single-level dungeon exactly as before.
            * The game starts on the first map. When the hero steps on `>` of a level that is not the last, he *descends*: the next map is loaded (hero on its `@`, its monsters numbered `1, 2, 3...` again, with fresh energy), the
              hero keeps his `hp` and `potions` but loses his `keys`, `tick` just goes on. Event `hero descends to level <n>` where `n` is the number of the new level (counted from 1), after `hero moves`; the monsters of
              the new level then get their turn as usual, in the same tick. On the last level `>` still wins the game (`hero reaches the stairs`).
            * The status line of `render()` gets the level between potions and tick: `HP 12/12 keys 0 potions 0 level 2/3 tick 14` (also for a single level: `level 1/1`).
        ''')
    return dd('''
        ## Feature to add: bats

        * `Game(text, seed=0)` takes an optional `seed`. The engine keeps a generator with `state = seed mod 2^31` and `next()` sets `state = (state * 1103515245 + 12345) mod 2^31` and returns the new state.
        * The map character `b` is a bat (hp 2, attack 1, speed 100), numbered like the other monsters (`b3`). Bats ignore the sight limit: they act (and spend energy) every time they have energy for it. A bat that is
          orthogonally adjacent to the hero hits it like any monster. Otherwise it *flutters*: it draws `p = (next() >> 16) mod 5`; if `p` is 0..3 it tries to step to the neighbour `U D L R` with index `p` (it moves if that cell is
          not a wall, not a locked door, not the hero's cell and not occupied by another monster, event `<id> flutters`; otherwise it stays and nothing is reported); if `p` is 4 it stays. Exactly one number is drawn per flutter
          and the generator is used for nothing else.
    ''')


def _feature_scripts(key: str, rng, r: dict, sol: dict, adapter: dict) -> dict[str, str]:
    if key in ("save-text", "save-checked"):
        return save_scripts(rng, r, sol, adapter, "v1" if key == "save-text" else "v2")
    if key == "daggers":
        maps = ["###########|#@./..r.g.#|###########", "#########|#@/.../.#|#.#.#.#.#|#r..s..g#|#########", "########|#/.@.r.#|#.#.#.##|#.g..D.#|#..!/.>#|########",
                "#######|#@/s//g#|#######"]
        lines = []
        for i, mp in enumerate(maps):
            lines.append(f"# scenario daggers {i + 1}\n> new {mp}\n> legal\n~ rand 200 {rng.randrange(1, 900)} every=3 emit=render,legal,status\n> new {mp}\n~ rand 200 {rng.randrange(1, 900)} every=7 emit=render,status junk=throw X|throw|throw u")
        lines.append("# scenario aimed throws\n> new ##########|#@/..r.g..#|##########\n> do R\n> do throw R\n> do throw R\n> render\n> do R\n> do R\n> do throw R\n> render\n> do throw L\n> status")
        return {"hidden_daggers": "\n".join(lines) + "\n", **scripts(rng, r)}
    if key == "levels":
        lv = ["#######|#@..k.>#|#######", "#########|#@.r.D..#|#...!.#.#|#.g.#.>.#|#########", "#####|#@r>#|#####"]
        lines = []
        for i in range(3):
            text = "|---|".join(lv[: i + 1])
            lines.append(f"# scenario levels {i + 1}\n> new {text}\n> render\n~ rand 400 {rng.randrange(1, 900)} every=6 emit=render,legal,status junk=X|drink")
        lines.append("# scenario descending\n> new " + "|---|".join(lv) + "\n" + "\n".join(["> do R"] * 6) + "\n> render\n" + "\n".join(["> do R"] * 4) + "\n> render\n> status")
        return {"hidden_levels": "\n".join(lines) + "\n", **scripts(rng, r)}
    lines = []
    bat_maps = ["#########|#@.....b.#|#.......##|#.b.....##|#########", "######|#@.b.#|#.b..#|######", "###########|#b...@...b#|#.........#|###########"]
    for i, mp in enumerate(bat_maps):
        for seed in (0, 1, 7, 2147483648 + 5):
            lines.append(f"# scenario bats {i + 1} seed {seed}\n> new {seed} {mp}\n~ rand 80 {rng.randrange(1, 900)} every=4 emit=render,status")
    lines.append("# scenario waiting bats\n> new 3 ###########|#@........b#|#.........##|###########\n" + "\n".join(["> do wait"] * 25) + "\n> render")
    return {"hidden_bats": "\n".join(lines) + "\n", **{k: _seeded(v) for k, v in scripts(rng, r).items()}}


def _seeded(script: str) -> str:
    """The bats adapter takes `new <seed> <rows>`: give the older scenarios seed 0."""
    return "\n".join("> new 0 " + ln[6:] if ln.startswith("> new ") else ln for ln in script.split("\n"))


def _feature_engine(key: str, r: dict) -> str:
    base = engine(r)
    if key == "save-text":
        return base + SAVE_V1
    if key == "save-checked":
        return _kit.edit_once(base, ("\n\nclass Game:", CHECKSUM_FN + "\n\nclass Game:")) + SAVE_V2
    if key == "daggers":
        return _kit.edit_once(base, *THROW_EDITS) + THROW_APPEND
    if key == "levels":
        return _kit.edit_once(base, *LEVELS_EDITS)
    return _kit.edit_once(base, *BAT_EDITS) + BAT_APPEND


def _feature_adapter(key: str) -> dict[str, str]:
    if key in ("save-text", "save-checked"):
        return _adapter_with(SAVE_ADAPT)
    if key == "bats":
        new = ('        if verb == "new":                     # new <seed> <map rows joined by |>\n'
               '            seed, _, rows = args.partition(" ")\n'
               '            self.game = gloam.Game(rows.replace("|", "\\n"), int(seed))\n'
               '            return "ok"\n')
        return _adapter_with([], new)
    return _adapter_with([])


def _feature_vis(key: str) -> str:
    return {
        "save-text": "# scenario save\n> new #####|#@.r#|#####\n> save\n> do R\n> save\n> reload\n> render\n> load nonsense\n",
        "save-checked": "# scenario save\n> new #####|#@.r#|#####\n> save\n> do R\n> reload\n> render\n> load nonsense\n> load GLOAM-SAVE 2 5\\nx\n",
        "daggers": "# scenario dagger\n> new #######|#@/.r.#|#######\n> do R\n> render\n> legal\n> do throw R\n> render\n",
        "levels": "# scenario stairs\n> new #####|#@.>#|#####|---|#####|#@r>#|#####\n> do R\n> do R\n> render\n> do R\n> render\n",
        "bats": "# scenario a bat\n> new 1 #######|#@..b.#|#######\n> do wait\n> do wait\n> render\n",
    }[key]


@family("games-gloam-feature", category="games", lang="python", kind="feature", n=5,
        summary="add save/load (plain and checksummed), throwable daggers, multi-level dungeons or seeded bats to the Gloam engine")
def gen_feature(rng, n):
    for i, v in enumerate(FEATURES[:n]):
        key = v["key"]
        r = {**DEFAULT}
        base = project(r)
        sol_eng = _feature_engine(key, r)
        sol = {"gloam.py": sol_eng, ".gitignore": _kit.GITIGNORE[LANG]}
        adapter = _feature_adapter(key)
        hid_scripts = _feature_scripts(key, rng, r, sol, adapter)
        hidden = _kit.data_files(LANG, hid_scripts, sol, adapter)
        ex = _seeded(example_script()) if key == "bats" else example_script()
        vis = _kit.data_files(LANG, {"examples": ex, "feature": _feature_vis(key)}, sol, adapter)
        rd = readme(r).replace("## Tests\n", feature_readme_section(key) + "\n## Tests\n")
        start = {"README.md": rd, "gloam.py": base["gloam.py"], ".gitignore": _kit.GITIGNORE[LANG], **_scen.check_files(LANG, adapter), **vis}
        prompt = v["ask"] + ("" if i % 2 == 0 else " Existing behaviour must not change.")
        yield Task(slug=f"{i + 1:02d}-{key}", prompt=prompt, difficulty=v["d"], start=start, hidden=hidden, solution={"gloam.py": sol_eng},
                   verify=_scen.VERIFY[LANG], tags=["roguelike", "feature"], notes={"feature": key, "rules": r})
