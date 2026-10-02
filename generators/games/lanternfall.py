"""Lanternfall (python): a text-adventure engine with a small parser, inventory limits, dark rooms, locked exits and a
vault that banks treasures. Build and fix tasks; scenarios are walked by a state-aware command generator."""
from __future__ import annotations

import json
import types

from fx import Task, dd, family

from . import _kit, _scen
from ._kit import Bug

LANG = "python"
GAME = "Lanternfall"
DEFAULT = dict(LIMIT=0, VISIT=1, TURNS=0)


def header(r: dict) -> str:
    return dd(f'''
        # ---- house rules for this adventure (they are part of the specification, see README.md) ----
        LIMIT = {r["LIMIT"]}
        VISIT_POINTS = {r["VISIT"]}
        TURN_LIMIT = {r["TURNS"]}
        # --------------------------------------------------------------------------------------------
    ''')


BODY = dd('''
    FULL = ("north", "south", "east", "west", "up", "down")
    SHORT = {"n": "north", "s": "south", "e": "east", "w": "west", "u": "up", "d": "down"}
    ARTICLES = ("the", "a", "an")
    VERBS = {
        "go": "go", "walk": "go", "move": "go", "look": "look", "l": "look", "take": "take", "get": "take", "grab": "take",
        "drop": "drop", "inventory": "inventory", "inv": "inventory", "i": "inventory", "examine": "examine", "x": "examine",
        "inspect": "examine", "score": "score",
    }


    class Room:
        def __init__(self, rid, title, desc, dark):
            self.id = rid
            self.title = title
            self.desc = desc
            self.dark = dark
            self.exits = []  # (direction, room id, needed item id or None), in file order
            self.items = []  # item ids, in the order they lie here


    class Item:
        def __init__(self, iid, name, aliases, weight, points, text, light):
            self.id = iid
            self.name = name
            self.aliases = aliases
            self.weight = weight
            self.points = points
            self.text = text
            self.light = light


    class Game:
        def __init__(self, world):
            self.rooms = {}
            self.items = {}
            self.start = None
            self.vault = None
            for raw in world.split("\\n"):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                kind, _, rest = line.partition(" ")
                if kind == "start":
                    self.start = rest.strip()
                elif kind == "vault":
                    self.vault = rest.strip()
                elif kind == "room":
                    f = [x.strip() for x in rest.split("|")]
                    self.rooms[f[0]] = Room(f[0], f[1], f[2], len(f) > 3 and f[3] == "dark")
                elif kind == "exit":
                    p = rest.split()
                    self.rooms[p[0]].exits.append((p[1], p[2], p[3] if len(p) > 3 else None))
                elif kind == "item":
                    f = [x.strip() for x in rest.split("|")]
                    aliases = [a.strip().lower() for a in f[3].split(",") if a.strip()]
                    self.items[f[0]] = Item(f[0], f[2].lower(), aliases, int(f[4]), int(f[5]), f[6], len(f) > 7 and f[7] == "light")
                    if f[1] != "~":
                        self.rooms[f[1]].items.append(f[0])
            self.room = self.start
            self.inv = []
            self.visited = {self.start}
            self.banked = set()
            self.score_points = 0
            self.steps_taken = 0
            self.done = False

        # -- queries -------------------------------------------------------------------------------
        def score(self):
            return self.score_points

        def steps(self):
            return self.steps_taken

        def finished(self):
            return self.done

        def _lit(self):
            room = self.rooms[self.room]
            if not room.dark:
                return True
            return any(self.items[i].light for i in self.inv + room.items)

        def _weight(self):
            return sum(self.items[i].weight for i in self.inv)

        def _find(self, noun, ids):
            for i in ids:
                item = self.items[i]
                if noun == item.name or noun in item.aliases:
                    return i
            return None

        def _describe(self):
            room = self.rooms[self.room]
            if not self._lit():
                return "It is pitch dark."
            lines = [room.title, room.desc]
            if room.exits:
                lines.append("Exits: " + ", ".join(e[0] for e in room.exits))
            if room.items:
                lines.append("You see: " + ", ".join(self.items[i].name for i in room.items) + ".")
            return "\\n".join(lines)

        # -- commands ------------------------------------------------------------------------------
        def step(self, line):
            if self.done:
                return "The game is over."
            words = [w for w in line.lower().split() if w not in ARTICLES]
            if not words:
                return "I don't understand."
            verb, noun = words[0], " ".join(words[1:])
            if verb in SHORT or verb in FULL:
                if noun:
                    return "I don't understand."
                return self._go(SHORT.get(verb, verb))
            action = VERBS.get(verb)
            if action == "go":
                return self._go(SHORT.get(noun, noun))
            if action == "look":
                return self._describe()
            if action == "take":
                return self._take(noun)
            if action == "drop":
                return self._drop(noun)
            if action == "inventory":
                return self._inventory()
            if action == "examine":
                return self._examine(noun)
            if action == "score":
                return "Score: %d in %d steps." % (self.score_points, self.steps_taken)
            return "I don't understand."

        def _go(self, direction):
            if direction not in FULL:
                return "Go where?"
            room = self.rooms[self.room]
            for d, to, need in room.exits:
                if d == direction:
                    if need is not None and need not in self.inv:
                        return "The way is locked. You need the %s." % self.items[need].name
                    self.room = to
                    self.steps_taken += 1
                    if to not in self.visited:
                        self.visited.add(to)
                        self.score_points += VISIT_POINTS
                    text = self._describe()
                    if TURN_LIMIT and self.steps_taken >= TURN_LIMIT:
                        self.done = True
                        text += "\\nYou have run out of time."
                    return text
            return "You can't go that way."

        def _take(self, noun):
            if not noun:
                return "Take what?"
            if not self._lit():
                return "It is too dark to see."
            room = self.rooms[self.room]
            if noun == "all":
                if not room.items:
                    return "There is nothing to take."
                out = []
                for i in list(room.items):
                    out.append("%s: %s" % (self.items[i].name, self._pick(i)))
                return "\\n".join(out)
            if self._find(noun, self.inv) is not None:
                return "You already have the %s." % self.items[self._find(noun, self.inv)].name
            i = self._find(noun, room.items)
            if i is None:
                return "You can't see any %s here." % noun
            return self._pick(i)

        def _pick(self, i):
            if LIMIT and self._weight() + self.items[i].weight > LIMIT:
                return "You can't carry that much."
            self.rooms[self.room].items.remove(i)
            self.inv.append(i)
            return "Taken."

        def _drop(self, noun):
            if not noun:
                return "Drop what?"
            if noun == "all":
                if not self.inv:
                    return "You are carrying nothing."
                return "\\n".join("%s: %s" % (self.items[i].name, self._put(i)) for i in list(self.inv))
            i = self._find(noun, self.inv)
            if i is None:
                return "You don't have any %s." % noun
            return self._put(i)

        def _put(self, i):
            self.inv.remove(i)
            self.rooms[self.room].items.append(i)
            item = self.items[i]
            if self.room == self.vault and item.points > 0 and i not in self.banked:
                self.banked.add(i)
                self.score_points += item.points
                return "Dropped. (+%d)" % item.points
            return "Dropped."

        def _inventory(self):
            if not self.inv:
                return "You are carrying nothing."
            text = "You are carrying: " + ", ".join(self.items[i].name for i in self.inv) + "."
            if LIMIT:
                text += "\\nWeight %d/%d." % (self._weight(), LIMIT)
            return text

        def _examine(self, noun):
            if not noun:
                return "Examine what?"
            if not self._lit():
                return "It is too dark to see."
            i = self._find(noun, self.inv + self.rooms[self.room].items)
            if i is None:
                return "You can't see any %s here." % noun
            return self.items[i].text
''')


def engine(r: dict) -> str:
    return '"""Lanternfall: a text-adventure engine. The rules are in README.md."""\n\n' + header(r) + "\n\n" + BODY


STUB = dd('''
    """Lanternfall: a text-adventure engine. The rules and the API are in README.md."""


    class Game:
        def __init__(self, world):
            raise NotImplementedError

        def step(self, line):
            raise NotImplementedError

        def score(self):
            raise NotImplementedError

        def steps(self):
            raise NotImplementedError

        def finished(self):
            raise NotImplementedError
''')

ADAPTER = {"tests/adapter.py": dd('''
    """Maps scenario commands onto the engine API (the scenario runner is tests/test_scenarios.py)."""
    import lanternfall


    class Adapter:
        def __init__(self):
            self.game = None

        def run(self, verb, args):
            if verb == "new":                     # new <world text, "\\\\n" escapes expanded>
                self.game = lanternfall.Game(args.replace("\\\\n", "\\n"))
                return "ok"
            if verb == "say":                     # say <command line>: the reply text
                return self.game.step(args)
            if verb == "status":                  # "<score> <steps> <finished>"
                g = self.game
                return "%d %d %s" % (g.score(), g.steps(), "yes" if g.finished() else "no")
            raise KeyError(verb)
''')}


# ----------------------------------------------------------------------------------------------------- worlds

ADJ = ["mossy", "narrow", "echoing", "dusty", "sunken", "windy", "silver", "forgotten", "crooked", "frozen", "amber", "quiet"]
NOUN = ["cellar", "hall", "gallery", "chapel", "vault", "kitchen", "tower", "stair", "cavern", "library", "garden", "attic"]
OPP = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up"}
THINGS = [("brass lantern", "lamp, lantern", 2, 0, "A battered brass lantern with a warm glow.", True),
          ("iron key", "key", 1, 0, "A heavy key with a ring-shaped bow.", False),
          ("silver cup", "cup, chalice", 2, 12, "A small cup, tarnished but valuable.", False),
          ("jade frog", "frog", 1, 8, "A frog carved from jade.", False),
          ("old map", "map, chart", 0, 5, "A map of a place that no longer exists.", False),
          ("bronze gong", "gong", 5, 15, "A gong that is far too heavy to be convenient.", False),
          ("rope coil", "rope", 3, 0, "Thirty feet of good rope.", False),
          ("glass bead", "bead", 0, 4, "A bead that catches the light.", False),
          ("wooden spoon", "spoon", 1, 0, "A spoon, chewed at one end.", False),
          ("golden egg", "egg", 2, 20, "An egg of solid gold.", False)]


def make_world(rng, n_rooms: int, locks: int = 1, darks: int = 1, items: int = 7) -> str:
    ids = [f"r{i}" for i in range(n_rooms)]
    names = []
    while len(names) < n_rooms:
        nm = f"{rng.choice(ADJ).title()} {rng.choice(NOUN).title()}"
        if nm not in names:
            names.append(nm)
    used_dirs = {i: set() for i in ids}
    edges = []
    for k in range(1, n_rooms):
        for _ in range(50):
            frm = ids[rng.randrange(0, k)]
            d = rng.choice(list(OPP))
            if d not in used_dirs[frm] and OPP[d] not in used_dirs[ids[k]]:
                used_dirs[frm].add(d)
                used_dirs[ids[k]].add(OPP[d])
                edges.append((frm, d, ids[k]))
                break
        else:
            raise RuntimeError("world: no free direction")
    # a few extra links
    for _ in range(max(1, n_rooms // 4)):
        a, b = rng.sample(ids, 2)
        d = rng.choice(list(OPP))
        if d not in used_dirs[a] and OPP[d] not in used_dirs[b] and not any((x == a and z == b) or (x == b and z == a) for x, _, z in edges):
            used_dirs[a].add(d)
            used_dirs[b].add(OPP[d])
            edges.append((a, d, b))
    dark_rooms = set(rng.sample(ids[2:], min(darks, n_rooms - 2))) if darks else set()
    things = list(THINGS)
    chosen = [things[0], things[1]] + rng.sample(things[2:], items - 2)
    placed = {}
    for t in chosen:
        placed[t[0]] = rng.choice([i for i in ids[:max(3, n_rooms // 2)] if i not in dark_rooms] or ids[:1])
    lines = ["# generated world", f"start {ids[0]}", f"vault {ids[0]}"]
    for i, nm in zip(ids, names):
        desc = rng.choice(["Cold air drifts through here.", "The walls are damp and smooth.", "Someone lived here once.", "A faint smell of smoke hangs in the air.", "Your steps echo."])
        lines.append(f"room {i} | {nm} | {desc}" + (" | dark" if i in dark_rooms else ""))
    locked_edges = set(rng.sample(range(len(edges)), min(locks, len(edges)))) if locks else set()
    for idx, (a, d, b) in enumerate(edges):
        need = " k1" if idx in locked_edges and idx > 0 else ""
        lines.append(f"exit {a} {d} {b}{need}")
        lines.append(f"exit {b} {OPP[d]} {a}")
    for n, (name, aliases, weight, points, text, light) in enumerate(chosen):
        iid = "k1" if name == "iron key" else "lamp" if light else f"t{n}"
        lines.append(f"item {iid} | {placed[name]} | {name} | {aliases} | {weight} | {points} | {text}" + (" | light" if light else ""))
    return "\n".join(lines) + "\n"


def exec_engine(r: dict):
    mod = types.ModuleType("lf_engine")
    exec(engine(r), mod.__dict__)
    return mod


def walk(rng, world: str, r: dict, n: int) -> list[str]:
    """A state-aware command generator: mostly sensible commands, some garbage and some wrong nouns."""
    mod = exec_engine(r)
    g = mod.Game(world)
    cmds = []
    for _ in range(n):
        room = g.rooms[g.room]
        roll = rng.randrange(100)
        item_words = []
        for i in g.inv + room.items:
            it = g.items[i]
            item_words += [it.name] + it.aliases
        if roll < 35 and room.exits:
            d = rng.choice(room.exits)[0]
            cmd = rng.choice([d, "go " + d, d[0], "go " + d[0], "walk " + d, "move " + d[0]])
        elif roll < 55 and room.items:
            it = g.items[rng.choice(room.items)]
            cmd = rng.choice(["take " + it.name, "get the " + rng.choice([it.name] + it.aliases), "grab " + rng.choice(it.aliases or [it.name]), "take all", "take  " + it.name.upper(), "take a " + it.name, "take an " + rng.choice(it.aliases or [it.name])])
        elif roll < 70 and g.inv:
            it = g.items[rng.choice(g.inv)]
            cmd = rng.choice(["drop " + it.name, "drop the " + rng.choice([it.name] + it.aliases), "drop all", "drop a " + it.name, "drop an " + (it.aliases or [it.name])[0]])
        elif roll < 78:
            cmd = rng.choice(["look", "l", "inventory", "i", "inv", "score"])
        elif roll < 84 and item_words:
            cmd = rng.choice(["examine ", "x ", "inspect "]) + rng.choice(item_words)
        elif roll < 88:
            cmd = rng.choice(["go", "go sideways", "take", "drop", "examine", "xyzzy", "", "   ", "north east", "n n", "take sword", "drop sword", "examine ghost", "dance", "take the", "up up"])
        elif roll < 92:
            cmd = "go " + rng.choice(["north", "south", "east", "west", "up", "down"])
        else:
            cmd = rng.choice(["take all", "drop all", "look", "score"])
        cmds.append(cmd)
        g.step(cmd)
    return cmds


def _enc(text: str) -> str:
    return text.replace("\n", "\\n")


def scripts(rng, r: dict) -> dict[str, str]:
    parts = []
    for i in range(5):
        world = make_world(rng, rng.choice([6, 8, 9, 10]), locks=rng.choice([0, 1, 2]), darks=rng.choice([0, 1, 2]), items=rng.choice([6, 7, 8]))
        cmds = walk(rng, world, r, 130)
        parts.append(f"# scenario world {i + 1}\n> new {_enc(world)}\n" + "\n".join(f"> say {c}" for c in cmds) + "\n> status")
    parts.append("# scenario darkness\n> new " + _enc(TINY) + "\n" + "\n".join("> say " + c for c in [
        "down", "look", "take coin", "examine coin", "inventory", "up", "take lamp", "down", "look", "drop the lamp", "look", "take all", "examine lamp", "up", "down", "look", "take coin",
        "drop all", "take lantern", "up", "look", "score"]) + "\n> status")
    parts.append("# scenario locked door\n> new " + _enc(LOCKED) + "\n" + "\n".join("> say " + c for c in [
        "east", "e", "take key", "go east", "look", "take all", "drop idol", "drop all", "take idol", "west", "west", "drop key", "drop idol", "score", "east", "take key", "east", "inventory", "x key", "x idol", "x vase", "score"]) + "\n> status")
    parts.append("# scenario twin coins\n> new " + _enc(TWINS) + "\n" + "\n".join("> say " + c for c in [
        "look", "examine coin", "take coin", "look", "examine coin", "take coin", "take dime", "inventory", "examine coin", "drop coin", "look", "examine coin", "drop penny", "drop coin", "drop coin",
        "take all", "drop all", "take all", "score"]) + "\n> status")
    return {"hidden_walks": "\n".join(parts) + "\n"}


TINY = (
    "start hall\nvault hall\nroom hall | Great Hall | A long table runs down the middle. | \nroom cellar | Damp Cellar | It smells of apples. | dark\n"
    "exit hall down cellar\nexit cellar up hall\nitem lamp | hall | brass lantern | lamp, lantern | 2 | 0 | A battered brass lantern. | light\n"
    "item coin | cellar | gold coin | coin | 1 | 10 | A shiny coin.\n"
)


LOCKED = (
    "start a\nvault a\nroom a | Porch | A creaky porch. | \nroom b | Parlour | Dust sheets everywhere. | \nexit a east b k1\nexit b west a\n"
    "item k1 | a | iron key | key | 1 | 0 | A heavy key.\nitem idol | b | stone idol | idol, statue | 4 | 9 | It stares back.\nitem vase | b | blue vase | vase | 2 | 3 | A chipped vase.\n"
)


TWINS = (
    "start a\nvault a\nroom a | Yard | Weeds everywhere. | \n"
    "item c1 | a | copper coin | coin, penny | 1 | 1 | Worn copper.\nitem c2 | a | silver coin | coin, dime | 1 | 5 | Shiny silver.\n"
)


def example_script() -> str:
    return ("# scenario a tiny cave\n> new " + _enc(TINY) + "\n> say look\n> say take the lamp\n> say down\n> say take coin\n> say inventory\n> say up\n> say drop coin\n> say score\n> say dance\n> status\n")


def readme(r: dict) -> str:
    s = []
    s.append("# Lanternfall\n\nA small text-adventure engine: rooms, exits, items, a tiny parser. The engine is headless: a `Game` built from a world text, and `step(line)` which returns the exact reply text.\n")
    s.append("## World file\n\nThe world is text, one record per line; empty lines and lines starting with `#` are ignored; fields are separated by `|` and trimmed of surrounding spaces:\n\n"
             "```\nstart <room id>\nvault <room id>\nroom <id> | <title> | <description> [| dark]\nexit <room id> <direction> <target room id> [<item id>]\nitem <id> | <room id or ~> | <name> | <aliases, comma separated> | <weight> | <points> | <examine text> [| light]\n```\n\n"
             "* Directions are `north south east west up down`. Exits are one-way: a world lists the way back separately. The order of the `exit` lines of a room is the order the exits are shown in.\n"
             "* An exit with a fourth word is *locked*: it can only be used while the item with that id is in the inventory (the item is not consumed).\n"
             "* An item lies in the room named by its second field (`~` = nowhere yet). Names and aliases are matched case-insensitively (store them in lower case). `light` items light up dark rooms.\n"
             "* `weight` and `points` are integers. Items lie in a room in the order of the `item` lines, and an item that is dropped is appended to the room's list.\n"
             "* All `room` lines come before the `exit` and `item` lines that mention them; ids are unique.\n")
    lim = (f"The hero can carry at most {r['LIMIT']} weight units in total." if r["LIMIT"] else "There is no limit to what the hero can carry.")
    s.append(f"## The game\n\nThe hero starts in the `start` room with empty hands; that room counts as visited. {lim} `steps` counts the successful moves (`go` through an exit); `score` starts at 0. "
             f"The first time the hero enters a room (the start room doesn't count) the score gains {r['VISIT']} point{'s' if r['VISIT'] != 1 else ''}"
             + ("" if r["VISIT"] else " (that is: nothing)") + ".\n")
    s.append("### Reading a command\n\n`step(line)` takes a line and returns the reply text (no trailing newline, lines joined by `\\n`). The line is lower-cased and split at whitespace; the words `the`, `a` and `an` are dropped. "
             "The first remaining word is the verb, the other words joined by single spaces are the *noun phrase* (possibly empty). Nothing left: `I don't understand.`\n\n"
             "| words | meaning |\n|---|---|\n| `go`, `walk`, `move` | go in the direction named by the noun phrase |\n| `look`, `l` | describe the room |\n| `take`, `get`, `grab` | pick something up |\n"
             "| `drop` | put something down |\n| `inventory`, `inv`, `i` | list what is carried |\n| `examine`, `x`, `inspect` | read an item's examine text |\n| `score` | `Score: <score> in <steps> steps.` |\n"
             "| a direction (`north`...) or its first letter (`n e s w u d`) as the verb, alone | same as `go <direction>` |\n\n"
             "A direction word as the verb followed by more words, and any other verb, reply `I don't understand.` In a `go` command the noun phrase may be a direction word or its one-letter form.\n")
    s.append("### Replies\n\n"
             "* **Describing a room** (also after moving into it): if the room is dark and no `light` item is in the inventory or lying in the room, the reply is `It is pitch dark.` Otherwise the lines `<title>`, `<description>`, "
             "`Exits: <directions in file order, joined by \", \">` (only if the room has exits) and `You see: <item names joined by \", \">.` (only if items lie here, in the room's order).\n"
             "* **go**: a noun phrase that is not a direction: `Go where?`; no exit that way: `You can't go that way.`; a locked exit without its item: `The way is locked. You need the <item name>.` Otherwise the hero moves, "
             "`steps` grows, a first visit scores, and the reply is the description of the new room." +
             (f" When `steps` reaches {r['TURNS']} the reply gets an extra last line `You have run out of time.` and the game is over: every later command (whatever it is) replies `The game is over.` and changes nothing." if r["TURNS"] else "") + "\n"
             "* **take**: no noun phrase: `Take what?`; dark room (as above): `It is too dark to see.`; `take all` in a room without items: `There is nothing to take.`, otherwise it tries every item of the room in the room's order and "
             "replies one line per item, `<item name>: <result>`; an item the hero already carries (matched by name or alias): `You already have the <item name>.`; no matching item in the room: `You can't see any <noun phrase> here.`; "
             "otherwise the item is taken: `Taken.`" +
             (f" — unless the carried weight plus the item's weight would exceed {r['LIMIT']}: then `You can't carry that much.` and nothing moves." if r["LIMIT"] else "") + "\n"
             "* **drop**: no noun phrase: `Drop what?`; `drop all` with empty hands: `You are carrying nothing.`, otherwise one line per carried item in carrying order, `<item name>: <result>`; an item that is not carried: "
             "`You don't have any <noun phrase>.`; otherwise the item is put in the room (appended to the room's items): `Dropped.` If the room is the `vault`, the item has more than 0 points and it was never dropped in the vault before, "
             "the score gains the item's points and the reply is `Dropped. (+<points>)`.\n"
             "* **inventory**: empty hands: `You are carrying nothing.`, otherwise `You are carrying: <names in carrying order, joined by \", \">.`" +
             (f" followed by a second line `Weight <carried>/{r['LIMIT']}.`" if r["LIMIT"] else "") + "\n"
             "* **examine**: no noun phrase: `Examine what?`; dark room: `It is too dark to see.`; an item that is carried or lies in the room (carried items first, then the room's, first match wins): its examine text; otherwise "
             "`You can't see any <noun phrase> here.`\n\n"
             "An item *matches* a noun phrase when the phrase equals its name or one of its aliases (all lower case). If several items match, the first in the order that is being searched wins.\n")
    s.append("## API (`lanternfall.py`)\n\n```python\nimport lanternfall\ng = lanternfall.Game(world_text)\ng.step(line)     # the reply text\ng.score()        # int\ng.steps()        # int, successful moves\ng.finished()     # bool, True once the turn limit ended the game\n```\n")
    s.append("## Tests\n\n`python3 -m unittest discover -s tests -v` replays the scenario files in `tests/data/` (`tests/adapter.py` shows how the API is called; in a scenario command `\\n` stands for a newline in the world text; "
             "the format is described at the top of `tests/test_scenarios.py`).\n")
    return "\n".join(s)


def project(r: dict) -> dict[str, str]:
    return {"lanternfall.py": engine(r), ".gitignore": _kit.GITIGNORE[LANG]}


def _variants(n: int) -> list[dict]:
    plan = [dict(), dict(LIMIT=5), dict(VISIT=0, TURNS=12), dict(LIMIT=4, VISIT=2), dict(LIMIT=6, TURNS=20, VISIT=3), dict(TURNS=8), dict(LIMIT=3, VISIT=1, TURNS=30)]
    return [{**DEFAULT, **o} for o in plan[:n]]


@family("games-lanternfall-build", category="games", lang="python", kind="greenfield", n=7,
        summary="build the Lanternfall text-adventure engine: world file parser, command parser, dark rooms, locks, carry limit, vault scoring")
def gen_build(rng, n):
    used: list[str] = []
    for i, r in enumerate(_variants(n)):
        sol = project(r)
        hidden = _kit.data_files(LANG, scripts(rng, r), sol, ADAPTER)
        vis = _kit.data_files(LANG, {"examples": example_script()}, sol, ADAPTER)
        start = {"README.md": readme(r), "lanternfall.py": STUB, ".gitignore": _kit.GITIGNORE[LANG], **_scen.check_files(LANG, ADAPTER), **vis}
        d = 2 + (r["LIMIT"] > 0) + (r["TURNS"] > 0) + (r["VISIT"] > 1)
        prompt = _kit.green_prompt(rng, game=GAME, blurb="a text adventure with a tiny command parser, inventory weight limits and dark rooms", file="lanternfall.py",
                                   verify=_scen.VERIFY[LANG], used=used)
        yield Task(slug=f"{i + 1:02d}-limit{r['LIMIT']}-visit{r['VISIT']}-turns{r['TURNS']}", prompt=prompt, difficulty=min(d, 5), start=start, hidden=hidden,
                   solution={"lanternfall.py": sol["lanternfall.py"]}, verify=_scen.VERIFY[LANG], tags=["text-adventure", "parser", "scenarios"], notes={"rules": r})


BUGS = [
    Bug("articles", "Articles confuse the parser",
        "`take the lamp` works but `take a lamp` says there is no `a lamp` here; the words a/an/the should all be ignored, wherever they appear.",
        [('ARTICLES = ("the", "a", "an")', 'ARTICLES = ("the",)')], difficulty=1),
    Bug("alias-case", "Names with capitals are not found",
        "`TAKE LAMP` is understood but `take Brass Lantern` isn't: capital letters in the item name make the engine say there is nothing like that here.",
        [("words = [w for w in line.lower().split() if w not in ARTICLES]", "words = [w for w in line.split() if w.lower() not in ARTICLES]")], difficulty=2),
    Bug("first-visit", "Rooms score every time you walk in",
        "Walking back and forth between two rooms keeps adding the first-visit points: you can farm the score by pacing.",
        [("if to not in self.visited:\n                    self.visited.add(to)\n                    self.score_points += VISIT_POINTS", "self.visited.add(to)\n                self.score_points += VISIT_POINTS")], difficulty=2, rules=dict(VISIT=2)),
    Bug("vault-farming", "Treasures can be banked repeatedly",
        "Dropping the same treasure in the vault again and again scores its points every time; it should only count the first time.",
        [("if self.room == self.vault and item.points > 0 and i not in self.banked:", "if self.room == self.vault and item.points > 0:")], difficulty=2),
    Bug("limit-boundary", "The carry limit is one unit too strict",
        "The hero can't pick something up although the total would be exactly the limit. Being exactly at the limit should be fine.",
        [("if LIMIT and self._weight() + self.items[i].weight > LIMIT:", "if LIMIT and self._weight() + self.items[i].weight >= LIMIT:")], difficulty=2, rules=dict(LIMIT=5)),
    Bug("dark-light-room", "A lantern on the floor doesn't light the room",
        "If the lantern is lying in a dark room the room is still pitch dark; it only works while carried.",
        [("return any(self.items[i].light for i in self.inv + room.items)", "return any(self.items[i].light for i in self.inv)")], difficulty=3),
    Bug("locked-message", "The locked-door message names the wrong thing",
        "The locked door message names the item that is needed using its id (e.g. `k1`) rather than its name.",
        [('return "The way is locked. You need the %s." % self.items[need].name', 'return "The way is locked. You need the %s." % need')], difficulty=1),
    Bug("take-all-order", "`take all` picks things up in the wrong order",
        "`take all` handles the items in reverse order, so the lines of the reply and the inventory order are back to front compared with the room listing.",
        [("for i in list(room.items):\n                out.append", "for i in reversed(list(room.items)):\n                out.append")], difficulty=2),
    Bug("drop-appends", "Dropped items go to the front of the room list",
        "Items I drop show up first in the `You see:` list instead of last.",
        [("self.rooms[self.room].items.append(i)", "self.rooms[self.room].items.insert(0, i)")], difficulty=2),
    Bug("exit-order", "Exits are listed alphabetically",
        "The `Exits:` line is sorted alphabetically but the world file order is what the README promises.",
        [('lines.append("Exits: " + ", ".join(e[0] for e in room.exits))', 'lines.append("Exits: " + ", ".join(sorted(e[0] for e in room.exits)))')], difficulty=2),
    Bug("turn-limit", "The game doesn't end after the last allowed step",
        "The time limit is applied one step late: on the last allowed step the game goes on and the `run out of time` line comes with the next move.",
        [("if TURN_LIMIT and self.steps_taken >= TURN_LIMIT:", "if TURN_LIMIT and self.steps_taken > TURN_LIMIT:")], difficulty=3, rules=dict(TURNS=12)),
    Bug("go-abbrev", "Single-letter directions don't work after `go`",
        "`n` works on its own but `go n` says `Go where?`.",
        [("return self._go(SHORT.get(noun, noun))", "return self._go(noun)")], difficulty=2),
    Bug("examine-order", "Examining prefers the floor to the hands",
        "When the hero carries an item with the same name as one on the floor, `examine` shows the one on the floor; carried items should win.",
        [("i = self._find(noun, self.inv + self.rooms[self.room].items)", "i = self._find(noun, self.rooms[self.room].items + self.inv)")], difficulty=3),
    Bug("already-have", "Picking up what you already carry",
        "Asking to `take` something that is already in the inventory says there is no such thing here instead of telling me I already have it.",
        [('        if self._find(noun, self.inv) is not None:\n            return "You already have the %s." % self.items[self._find(noun, self.inv)].name\n', "")], difficulty=2),
    Bug("weight-line", "The weight line shows the limit twice",
        "With a carry limit, the inventory's second line shows the wrong weight: it prints the limit where the carried weight should be.",
        [('text += "\\nWeight %d/%d." % (self._weight(), LIMIT)', 'text += "\\nWeight %d/%d." % (LIMIT, LIMIT)')], difficulty=1, rules=dict(LIMIT=5)),
]

_B = {b.id: b for b in BUGS}
BUGS_ALL = BUGS + [
    _kit.combine(_B["locked-message"], _B["exit-order"], difficulty=3),
    _kit.combine(_B["first-visit"], _B["vault-farming"], _B["limit-boundary"], difficulty=4, title="Scoring and limits"),
]


@family("games-lanternfall-fix", category="games", lang="python", kind="fix", n=16,
        summary="hand-injected defects in the Lanternfall engine (parser, scoring, limits, darkness, locks, listing order)")
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
        ctx = {"files": ["lanternfall.py"], "verify": _scen.VERIFY[LANG]}
        yield _kit.bug_task(game=GAME, lang=LANG, base_files=base, tests=tests, hidden=hidden, bug=bug, ctx=ctx, rng=rng, used=used, k=k,
                            tags=["text-adventure", "parser"], extra_notes={"rules": r})
