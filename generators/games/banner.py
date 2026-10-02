"""Banner (java): tactics on a small grid with an initiative order drawn from a seeded LCG, terrain costs, ranged units and
optional counter-attacks. Build, fix and AI-tournament tasks; a python model cross-checks the reference engine."""
from __future__ import annotations

import json
import textwrap

from fx import Task, dd, family

from . import _kit, _scen
from ._kit import Bug

LANG = "java"
GAME = "Banner"
DEFAULT = dict(ROUNDS=12, FOREST=2, COUNTER=True, DEFENCE=True, DICE=6)
STATS = {"K": ("knight", 10, 4, 3, 1, 5), "R": ("archer", 6, 3, 3, 2, 7), "U": ("brute", 14, 5, 2, 1, 3), "S": ("scout", 5, 2, 5, 1, 9)}  # name, hp, atk, move, range, speed


def ind(text: str, n: int = 4) -> str:
    return textwrap.indent(text, " " * n)


def header(r: dict) -> str:
    return dd(f'''
        // ---- house rules for this battlefield (they are part of the specification, see README.md) ----
        static final int MAX_ROUNDS = {r["ROUNDS"]};
        static final int FOREST_COST = {r["FOREST"]};
        static final boolean COUNTER = {"true" if r["COUNTER"] else "false"};
        static final boolean FOREST_DEFENCE = {"true" if r["DEFENCE"] else "false"};
        static final int INITIATIVE_DICE = {r["DICE"]};
        // -------------------------------------------------------------------------------------------
    ''')


ENGINE_TOP = dd(r'''
    import java.util.ArrayList;
    import java.util.Arrays;
    import java.util.Collections;
    import java.util.List;

    /** Banner: grid tactics with an initiative order. The rules are in README.md. */
    public class Banner {
''')

ENGINE_BODY = dd(r'''
    static final String TYPES = "KRUS";
    static final int[][] STATS = {
        // hp, attack, move, range, speed
        {10, 4, 3, 1, 5},
        {6, 3, 3, 2, 7},
        {14, 5, 2, 1, 3},
        {5, 2, 5, 1, 9},
    };

    static class Unit {
        String id;
        int type;
        boolean sideA;
        int x;
        int y;
        int hp;
        int maxHp;
        int initiative;
    }

    private final char[][] terrain;
    private final int w;
    private final int h;
    private final List<Unit> units = new ArrayList<>();
    private List<Unit> order = new ArrayList<>();
    private long state;
    private int round = 1;
    private boolean moved;
    private String result = "";

    /** `text`: map rows, a line "--", then unit lines "<id> <type> <x> <y>" (ids start with A or B). */
    public Banner(String text, long seed) {
        String[] lines = text.split("\n");
        int sep = Arrays.asList(lines).indexOf("--");
        h = sep;
        w = lines[0].length();
        terrain = new char[h][];
        for (int i = 0; i < h; i++) terrain[i] = lines[i].toCharArray();
        for (int i = sep + 1; i < lines.length; i++) {
            String[] f = lines[i].trim().split(" ");
            Unit u = new Unit();
            u.id = f[0];
            u.sideA = f[0].charAt(0) == 'A';
            u.type = TYPES.indexOf(f[1].charAt(0));
            u.x = Integer.parseInt(f[2]);
            u.y = Integer.parseInt(f[3]);
            u.hp = STATS[u.type][0];
            u.maxHp = u.hp;
            units.add(u);
        }
        units.sort((a, b) -> a.id.compareTo(b.id));
        state = seed & 0x7FFFFFFFL;
        startRound(new ArrayList<>());
    }

    private int next() {
        state = (state * 1103515245L + 12345L) & 0x7FFFFFFFL;
        return (int) state;
    }

    private void startRound(List<String> ev) {
        for (Unit u : units) u.initiative = STATS[u.type][4] + ((next() >> 16) % INITIATIVE_DICE);
        order = new ArrayList<>(units);
        order.sort((a, b) -> a.initiative != b.initiative ? b.initiative - a.initiative : a.id.compareTo(b.id));
        moved = false;
        StringBuilder sb = new StringBuilder("round " + round + ":");
        for (Unit u : order) sb.append(' ').append(u.id).append('(').append(u.initiative).append(')');
        ev.add(sb.toString());
    }

    private Unit at(int x, int y) {
        for (Unit u : units) if (u.x == x && u.y == y) return u;
        return null;
    }

    private static int dist(Unit a, Unit b) {
        return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
    }

    private int stepCost(int x, int y) {
        char c = terrain[y][x];
        return c == 'f' ? FOREST_COST : 1;
    }

    /** Cheapest movement cost from the active unit to every cell (Integer.MAX_VALUE = unreachable). */
    private int[][] costs(Unit u) {
        int[][] d = new int[h][w];
        for (int[] row : d) Arrays.fill(row, Integer.MAX_VALUE);
        d[u.y][u.x] = 0;
        boolean changed = true;
        while (changed) {
            changed = false;
            for (int y = 0; y < h; y++) {
                for (int x = 0; x < w; x++) {
                    if (d[y][x] == Integer.MAX_VALUE) continue;
                    int[][] dirs = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};
                    for (int[] dd : dirs) {
                        int nx = x + dd[0];
                        int ny = y + dd[1];
                        if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
                        char c = terrain[ny][nx];
                        if (c == '#' || c == '~' || at(nx, ny) != null) continue;
                        int nd = d[y][x] + stepCost(nx, ny);
                        if (nd < d[ny][nx]) {
                            d[ny][nx] = nd;
                            changed = true;
                        }
                    }
                }
            }
        }
        return d;
    }

    public String active() {
        return result.isEmpty() ? order.get(0).id : "";
    }

    public String winner() {
        return result;
    }

    public int round() {
        return round;
    }

    public List<String> legalMoves() {
        List<String> out = new ArrayList<>();
        if (!result.isEmpty()) return out;
        Unit u = order.get(0);
        out.add("end");
        if (!moved) {
            int[][] d = costs(u);
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                    if ((x != u.x || y != u.y) && d[y][x] <= STATS[u.type][2]) out.add("move " + x + " " + y);
        }
        for (Unit t : units) {
            int dd = dist(u, t);
            if (t.sideA != u.sideA && dd >= 1 && dd <= STATS[u.type][3]) out.add("attack " + t.id);
        }
        return out;
    }

    public String apply(String command) {
        if (command == null || !legalMoves().contains(command)) throw new IllegalArgumentException("illegal command: " + command);
        List<String> ev = new ArrayList<>();
        Unit u = order.get(0);
        if (command.startsWith("move ")) {
            String[] f = command.split(" ");
            int x = Integer.parseInt(f[1]);
            int y = Integer.parseInt(f[2]);
            int cost = costs(u)[y][x];
            u.x = x;
            u.y = y;
            moved = true;
            ev.add(u.id + " moves to " + x + "," + y + " (cost " + cost + ")");
            return String.join("; ", ev);
        }
        if (command.startsWith("attack ")) {
            Unit t = null;
            for (Unit c : units) if (c.id.equals(command.substring(7))) t = c;
            int dmg = STATS[u.type][1];
            if (FOREST_DEFENCE && terrain[t.y][t.x] == 'f') dmg = Math.max(1, dmg - 1);
            t.hp -= dmg;
            ev.add(u.id + " hits " + t.id + " " + dmg + " (hp " + Math.max(t.hp, 0) + ")");
            if (t.hp <= 0) {
                units.remove(t);
                order.remove(t);
                ev.add(t.id + " dies");
            } else if (COUNTER && dist(u, t) <= STATS[t.type][3]) {
                int back = Math.max(1, STATS[t.type][1] / 2);
                u.hp -= back;
                ev.add(t.id + " counters " + u.id + " " + back + " (hp " + Math.max(u.hp, 0) + ")");
                if (u.hp <= 0) {
                    units.remove(u);
                    order.remove(u);
                    ev.add(u.id + " dies");
                }
            }
        }
        // the active unit's turn is over (end, or an attack)
        order.remove(u);
        finishTurn(ev);
        return String.join("; ", ev);
    }

    private void finishTurn(List<String> ev) {
        boolean a = false;
        boolean b = false;
        int hpA = 0;
        int hpB = 0;
        for (Unit x : units) {
            if (x.sideA) {
                a = true;
                hpA += x.hp;
            } else {
                b = true;
                hpB += x.hp;
            }
        }
        if (!a || !b) {
            result = a ? "A" : b ? "B" : "draw";
            ev.add((result.equals("draw") ? "draw" : result + " wins"));
            return;
        }
        if (order.isEmpty()) {
            round++;
            if (round > MAX_ROUNDS) {
                result = hpA > hpB ? "A" : hpB > hpA ? "B" : "draw";
                ev.add("time: " + (result.equals("draw") ? "draw" : result + " wins"));
                return;
            }
            startRound(ev);
        } else {
            moved = false;
        }
    }

    public String render() {
        StringBuilder sb = new StringBuilder();
        for (int y = 0; y < h; y++) {
            for (int x = 0; x < w; x++) {
                Unit u = at(x, y);
                if (u != null) {
                    char c = TYPES.charAt(u.type);
                    sb.append(u.sideA ? c : Character.toLowerCase(c));
                } else {
                    sb.append(terrain[y][x]);
                }
            }
            sb.append('\n');
        }
        for (Unit u : units) {
            sb.append(u.id).append(' ').append(TYPES.charAt(u.type)).append(" (").append(u.x).append(',').append(u.y).append(") hp ").append(u.hp).append('/').append(u.maxHp).append('\n');
        }
        if (!result.isEmpty()) {
            sb.append("over: ").append(result.equals("draw") ? "draw" : result + " wins");
        } else {
            sb.append("round ").append(round).append(" active ").append(order.get(0).id).append(moved ? " moved" : "").append('\n');
            sb.append("order");
            for (Unit u : order) sb.append(' ').append(u.id);
        }
        return sb.toString();
    }
''')


def engine(r: dict, with_suggest: str = "") -> str:
    return ENGINE_TOP + ind(header(r)) + "\n" + ind(ENGINE_BODY) + (ind(with_suggest) if with_suggest else "") + "}\n"


STUB = dd(r'''
    import java.util.List;

    /** Banner: grid tactics with an initiative order. The rules and the API are in README.md. */
    public class Banner {
        public Banner(String text, long seed) {
            throw new UnsupportedOperationException("not implemented");
        }

        public List<String> legalMoves() {
            throw new UnsupportedOperationException("not implemented");
        }

        public String apply(String command) {
            throw new UnsupportedOperationException("not implemented");
        }

        public String render() {
            throw new UnsupportedOperationException("not implemented");
        }

        public String active() {
            throw new UnsupportedOperationException("not implemented");
        }

        public String winner() {
            throw new UnsupportedOperationException("not implemented");
        }

        public int round() {
            throw new UnsupportedOperationException("not implemented");
        }
    }
''')

ADAPTER = {"test/Adapter.java": dd(r'''
    import java.util.ArrayList;
    import java.util.Collections;
    import java.util.List;

    /** Maps scenario commands onto the engine API (the scenario runner is TestMain.java). */
    public class Adapter {
        private Banner game;

        String run(String verb, String args) {
            switch (verb) {
                case "new": { // new <seed> <battlefield lines joined by |>
                    int sp = args.indexOf(' ');
                    game = new Banner(args.substring(sp + 1).replace('|', '\n'), Long.parseLong(args.substring(0, sp)));
                    return "ok";
                }
                case "do": // do <command>: the event text, or "illegal"
                    try {
                        return game.apply(args);
                    } catch (IllegalArgumentException e) {
                        return "illegal";
                    }
                case "legal": { // sorted legal commands joined by "," ("-" when there are none)
                    List<String> moves = new ArrayList<>(game.legalMoves());
                    Collections.sort(moves);
                    return moves.isEmpty() ? "-" : String.join(",", moves);
                }
                case "render":
                    return game.render();
                case "status": // "<round> <active or -> <winner or ->"
                    return game.round() + " " + (game.active().isEmpty() ? "-" : game.active()) + " " + (game.winner().isEmpty() ? "-" : game.winner());
                default:
                    throw new IllegalArgumentException("unknown verb " + verb);
            }
        }
    }
''')}


# ----------------------------------------------------------------------------------------------------- python model

class Model:
    def __init__(self, text: str, seed: int, r: dict):
        self.r = r
        lines = text.split("\n")
        sep = lines.index("--")
        self.terrain = [list(x) for x in lines[:sep]]
        self.h, self.w = sep, len(lines[0])
        self.units = []
        for ln in lines[sep + 1:]:
            f = ln.split()
            t = STATS[f[1]]
            self.units.append(dict(id=f[0], a=f[0][0] == "A", t=f[1], x=int(f[2]), y=int(f[3]), hp=t[1], max=t[1], ini=0))
        self.units.sort(key=lambda u: u["id"])
        self.state = seed & 0x7FFFFFFF
        self.round, self.moved, self.result = 1, False, ""
        self.order = []
        self.start_round([])

    def nxt(self):
        self.state = (self.state * 1103515245 + 12345) & 0x7FFFFFFF
        return self.state

    def start_round(self, ev):
        for u in self.units:
            u["ini"] = STATS[u["t"]][5] + (self.nxt() >> 16) % self.r["DICE"]
        self.order = sorted(self.units, key=lambda u: (-u["ini"], u["id"]))
        self.moved = False
        ev.append("round %d: %s" % (self.round, " ".join("%s(%d)" % (u["id"], u["ini"]) for u in self.order)))

    def at(self, x, y):
        return next((u for u in self.units if u["x"] == x and u["y"] == y), None)

    def costs(self, u):
        INF = 10 ** 9
        d = [[INF] * self.w for _ in range(self.h)]
        d[u["y"]][u["x"]] = 0
        changed = True
        while changed:
            changed = False
            for y in range(self.h):
                for x in range(self.w):
                    if d[y][x] == INF:
                        continue
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = x + dx, y + dy
                        if not (0 <= nx < self.w and 0 <= ny < self.h):
                            continue
                        c = self.terrain[ny][nx]
                        if c in "#~" or self.at(nx, ny):
                            continue
                        nd = d[y][x] + (self.r["FOREST"] if c == "f" else 1)
                        if nd < d[ny][nx]:
                            d[ny][nx] = nd
                            changed = True
        return d

    def legal(self):
        if self.result:
            return []
        u = self.order[0]
        out = ["end"]
        if not self.moved:
            d = self.costs(u)
            for y in range(self.h):
                for x in range(self.w):
                    if (x, y) != (u["x"], u["y"]) and d[y][x] <= STATS[u["t"]][3]:
                        out.append("move %d %d" % (x, y))
        for t in self.units:
            dd = abs(u["x"] - t["x"]) + abs(u["y"] - t["y"])
            if t["a"] != u["a"] and 1 <= dd <= STATS[u["t"]][4]:
                out.append("attack " + t["id"])
        return out

    def apply(self, cmd):
        ev = []
        u = self.order[0]
        if cmd.startswith("move "):
            _, x, y = cmd.split()
            x, y = int(x), int(y)
            cost = self.costs(u)[y][x]
            u["x"], u["y"] = x, y
            self.moved = True
            return "%s moves to %d,%d (cost %d)" % (u["id"], x, y, cost)
        if cmd.startswith("attack "):
            t = next(c for c in self.units if c["id"] == cmd[7:])
            dmg = STATS[u["t"]][2]
            if self.r["DEFENCE"] and self.terrain[t["y"]][t["x"]] == "f":
                dmg = max(1, dmg - 1)
            t["hp"] -= dmg
            ev.append("%s hits %s %d (hp %d)" % (u["id"], t["id"], dmg, max(t["hp"], 0)))
            if t["hp"] <= 0:
                self.units.remove(t)
                if t in self.order:
                    self.order.remove(t)
                ev.append("%s dies" % t["id"])
            elif self.r["COUNTER"] and abs(u["x"] - t["x"]) + abs(u["y"] - t["y"]) <= STATS[t["t"]][4]:
                back = max(1, STATS[t["t"]][2] // 2)
                u["hp"] -= back
                ev.append("%s counters %s %d (hp %d)" % (t["id"], u["id"], back, max(u["hp"], 0)))
                if u["hp"] <= 0:
                    self.units.remove(u)
                    if u in self.order:
                        self.order.remove(u)
                    ev.append("%s dies" % u["id"])
        if u in self.order:
            self.order.remove(u)
        self.finish(ev)
        return "; ".join(ev)

    def finish(self, ev):
        a = [u for u in self.units if u["a"]]
        b = [u for u in self.units if not u["a"]]
        if not a or not b:
            self.result = "A" if a else "B" if b else "draw"
            ev.append("draw" if self.result == "draw" else self.result + " wins")
            return
        if not self.order:
            self.round += 1
            if self.round > self.r["ROUNDS"]:
                ha, hb = sum(u["hp"] for u in a), sum(u["hp"] for u in b)
                self.result = "A" if ha > hb else "B" if hb > ha else "draw"
                ev.append("time: " + ("draw" if self.result == "draw" else self.result + " wins"))
                return
            self.start_round(ev)
        else:
            self.moved = False

    def render(self):
        rows = []
        for y in range(self.h):
            row = ""
            for x in range(self.w):
                u = self.at(x, y)
                row += (u["t"] if u["a"] else u["t"].lower()) if u else self.terrain[y][x]
            rows.append(row)
        for u in self.units:
            rows.append("%s %s (%d,%d) hp %d/%d" % (u["id"], u["t"], u["x"], u["y"], u["hp"], u["max"]))
        if self.result:
            rows.append("over: " + ("draw" if self.result == "draw" else self.result + " wins"))
        else:
            rows.append("round %d active %s%s" % (self.round, self.order[0]["id"], " moved" if self.moved else ""))
            rows.append("order " + " ".join(u["id"] for u in self.order))
        return "\\n".join(rows)


def crosscheck(text: str, r: dict) -> None:
    m = None
    cmd = None
    for line in text.split("\n"):
        if line.startswith("> "):
            cmd = line[2:]
        elif line.startswith("= ") and cmd is not None:
            want = line[2:]
            verb, _, args = cmd.partition(" ")
            if verb == "new":
                seed, _, rows = args.partition(" ")
                m = Model(rows.replace("|", "\n"), int(seed), r)
            elif verb == "do":
                if args in m.legal():
                    got = m.apply(args)
                    assert got == want, f"model/engine disagree on {cmd}: {got!r} vs {want!r}"
                else:
                    assert want == "illegal", f"model says illegal for {cmd}, engine says {want!r}"
            elif verb == "legal":
                got = ",".join(sorted(m.legal())) or "-"
                assert got == want, f"legal disagree: {got!r} vs {want!r}"
            elif verb == "status":
                got = f"{m.round} {m.order[0]['id'] if not m.result else '-'} {m.result or '-'}"
                assert got == want, f"status disagree {got!r} vs {want!r}"
            elif verb == "render":
                assert m.render() == want, f"render disagree:\n{m.render()}\n{want}"
            cmd = None


def make_battle(rng, w: int, h: int, per_side: int, forests: int = 4, walls: int = 3, water: int = 2) -> str:
    g = [["."] * w for _ in range(h)]
    cells = [(x, y) for x in range(w) for y in range(h)]
    rng.shuffle(cells)
    for ch, n in (("f", forests), ("#", walls), ("~", water)):
        for _ in range(n):
            x, y = cells.pop()
            g[y][x] = ch
    left = [(x, y) for (x, y) in cells if x < w // 2 and g[y][x] == "."]
    right = [(x, y) for (x, y) in cells if x >= w - w // 2 and g[y][x] == "."]
    lines = ["".join(row) for row in g] + ["--"]
    for side, pool in (("A", left), ("B", right)):
        for i in range(per_side):
            x, y = pool.pop(rng.randrange(len(pool)))
            lines.append(f"{side}{i + 1} {rng.choice('KKRUS')} {x} {y}")
    return "\n".join(lines)


def scripts(rng, r: dict) -> dict[str, str]:
    parts = []
    for i in range(6):
        battle = make_battle(rng, rng.choice([7, 8, 9]), rng.choice([5, 6]), rng.choice([2, 3, 4]))
        row = battle.replace("\n", "|")
        seed = rng.randrange(1, 100000)
        parts.append(f"# scenario battle {i + 1}\n> new {seed} {row}\n> render\n> legal\n~ rand 420 {rng.randrange(1, 900)} every=5 emit=render,status junk=end now|move 99 99|attack ZZ|move 1|attack|move -1 0")
    edge = dd('''
        # scenario a duel on open ground
        > new 7 ......|......|......|--|A1 K 0 1|B1 K 5 1
        > render
        > do move 3 1
        > do move 3 2
        > do attack B1
        > do end
        > render
        > status
        # scenario ranged, forest and water
        > new 3 .f.~..|.f.~..|......|--|A1 R 0 0|A2 S 0 2|B1 U 4 0|B2 R 5 2
        > render
        > legal
        > do end
        > do end
        > do end
        > do end
        > render
        > status
    ''')
    return {"hidden_battles": "\n".join(parts) + "\n", "hidden_edge": edge}


def example_script() -> str:
    return dd('''
        # scenario a duel
        > new 5 ......|......|......|--|A1 K 0 1|B1 K 5 1
        > render
        > legal
        > do move 2 1
        > render
        > do end
        > render
        # scenario a few commands
        > new 11 ...f...|..#....|.......|--|A1 R 0 0|A2 U 0 2|B1 S 6 0|B2 K 6 2
        > render
        ~ rand 20 4 emit=render,status
    ''')


def readme(r: dict) -> str:
    s = []
    s.append("# Banner\n\nA small turn-based tactics game on a grid: two sides (`A` and `B`), four unit types, terrain with movement costs, and a turn order that is drawn at the start of every round from a seeded generator. "
             "The engine is headless: a `Banner` object, a list of legal commands and exact text for every reply.\n")
    s.append("## Battlefield text\n\n`new Banner(text, seed)`: `text` is the map rows (equal length, joined by `\\n`), then a line `--`, then one line per unit: `<id> <type> <x> <y>` with `x` the column and `y` the row (0, 0 at the top left); "
             "the id starts with `A` or `B` (`A1`, `A2`, `B1`), the type is one letter. Terrain: `.` plain, `f` forest, `#` wall, `~` water. Walls and water can never be entered. Units start on plain or forest cells.\n\n"
             "| type | name | hp | attack | move | range | speed |\n|---|---|---|---|---|---|---|\n| `K` | knight | 10 | 4 | 3 | 1 | 5 |\n| `R` | archer | 6 | 3 | 3 | 2 | 7 |\n| `U` | brute | 14 | 5 | 2 | 1 | 3 |\n| `S` | scout | 5 | 2 | 5 | 1 | 9 |\n\n"
             "All distances are Manhattan (`|dx| + |dy|`). Units are kept in order of their ids as text (`A1 < A2 < B1`).\n")
    s.append(f"## Rounds and initiative\n\nThe game has rounds numbered from 1. *Initiative*: at the start of every round each living unit, in id order, draws `d = (next() >> 16) mod {r['DICE']}` and gets `initiative = speed + d`. The round's *order* sorts the living units by "
             "initiative descending, ties by id ascending. The generator is `state = seed mod 2^31`, `next()` sets `state = (state * 1103515245 + 12345) mod 2^31` and returns the new state; it is used only for initiative draws. "
             "Round 1 starts when the game is created (its draws happen then). Units act one at a time in that order; a unit that died before its turn is skipped (removed from the order). The event of a round start is `round <n>: <id>(<initiative>) ...` listing the order.\n")
    s.append("## A unit's turn\n\nThe *active* unit is the first of the order. Commands (exact strings): `end`; `move <x> <y>`; `attack <id>`. `LegalMoves()` lists the legal ones; when the game is over there are none.\n\n"
             f"* `end`: always legal. The unit's turn ends.\n"
             f"* `move <x> <y>`: legal only if the unit has not moved yet this turn and the target cell is not its own cell and can be reached with a total cost of at most its *move* value. Moving enters one orthogonally adjacent cell at a time; entering a plain cell costs 1, a forest cell {r['FOREST']}; "
             "walls, water and cells occupied by any unit (of either side) cannot be entered or passed through. The cost used is the cheapest one. Event `<id> moves to <x>,<y> (cost <c>)`. The turn goes on (the unit may still attack or end).\n"
             "* `attack <id>`: legal when the target is a living unit of the other side at a distance from 1 to the attacker's *range*. A unit may move before attacking, and an attack ends the turn (a unit cannot move after attacking, simply because its turn is over). "
             f"Damage is the attacker's attack" + (", reduced by 1 (but never below 1) when the target stands on a forest cell" if r["DEFENCE"] else "") + f". Event `<id> hits <target> <damage> (hp <remaining>)` where the remaining hp is shown as 0 if it dropped below 0. At 0 hp or less the target dies "
             "(it is removed from the field and from the order), event `<target> dies`." + (" If it survives and the attacker is within the target's own range (distance from 1 to the target's range), the target *counters* at once: damage `max(1, target attack / 2)` (integer division, no terrain effect, no further counter), "
                                                                                                    "event `<target> counters <id> <damage> (hp <remaining>)`, and the attacker dies if that kills it (`<id> dies`)." if r["COUNTER"] else " There are no counter-attacks on this battlefield.") + "\n\n"
             "After a turn ends the next unit of the order becomes active (and has not moved). Events of one command are joined by `; `.\n")
    s.append(f"## End of the game\n\nAfter every turn (before anything else) the game checks the units: if one side has no units the other side *wins* (event `A wins` / `B wins`; if both sides are empty at once, event `draw`). "
             f"Otherwise, when the order is empty a new round starts: the round number grows by 1 and if it is now above {r['ROUNDS']} the game ends on time: the side with more total remaining hp wins (event `time: A wins`, `time: B wins`, or `time: draw` for equal hp); else the new round starts with its initiative draws (event `round <n>: ...`). "
             "When the game is over `winner()` returns `A`, `B` or `draw`, `active()` returns an empty string.\n")
    s.append("## API (`Banner.java`, default package)\n\n```java\nBanner g = new Banner(String text, long seed);\nList<String> g.legalMoves();   // any order; empty when over\nString g.apply(String command); // events text; throws IllegalArgumentException (nothing changes) for an illegal command\n"
             "String g.render();\nString g.active();   // id of the active unit, \"\" when over\nString g.winner();   // \"\" while running, else \"A\", \"B\" or \"draw\"\nint g.round();\n```\n")
    m = Model("......\n......\n......\n--\nA1 K 0 1\nB1 K 5 1", 5, r)
    m.apply("move 2 1")
    s.append("### `render()`\n\nThe map (units drawn over the terrain: the type letter, upper case for side A and lower case for side B), then one line per living unit in id order `<id> <type letter> (<x>,<y>) hp <hp>/<max hp>`, then "
             "`round <n> active <id>` (followed by ` moved` if the active unit has already moved this turn) and `order <ids still to act this round, active unit first>`; when the game is over those two lines are replaced by one line "
             "`over: A wins`, `over: B wins` or `over: draw`. Lines are joined by `\\n`, no trailing newline. Example after `new Banner(\"......|......|......|--|A1 K 0 1|B1 K 5 1\", 5)` and `move 2 1` (if A1 happened to be active):\n\n```\n" + m.render().replace("\\n", "\n") + "\n```\n")
    s.append("## Tests\n\n`" + _scen.VERIFY[LANG] + "` replays the scenario files in `test/data/` (`test/Adapter.java` shows how the API is called; battlefields are written with `|` instead of newlines; the format is described at the top of `test/TestMain.java`).\n")
    return "\n".join(s)


def project(r: dict) -> dict[str, str]:
    return {"src/Banner.java": engine(r), ".gitignore": _kit.GITIGNORE[LANG]}


def _variants(n: int) -> list[dict]:
    plan = [dict(), dict(COUNTER=False), dict(DEFENCE=False, FOREST=3), dict(ROUNDS=6, DICE=4), dict(FOREST=3, DICE=8, ROUNDS=8), dict(COUNTER=False, DEFENCE=False, ROUNDS=5)]
    return [{**DEFAULT, **o} for o in plan[:n]]


@family("games-banner-build", category="games", lang="java", kind="greenfield", n=6,
        summary="build the Banner grid-tactics engine: seeded initiative order, terrain costs, ranged attacks, counters, time limit")
def gen_build(rng, n):
    used: list[str] = []
    for i, r in enumerate(_variants(n)):
        sol = project(r)
        hidden = _kit.data_files(LANG, scripts(rng, r), sol, ADAPTER)
        for t in hidden.values():
            crosscheck(t, r)
        vis = _kit.data_files(LANG, {"examples": example_script()}, sol, ADAPTER)
        crosscheck(next(iter(vis.values())), r)
        start = {"README.md": readme(r), "src/Banner.java": STUB, ".gitignore": _kit.GITIGNORE[LANG], **_scen.check_files(LANG, ADAPTER), **vis}
        d = 3 + r["COUNTER"] + (r["FOREST"] != 2) - (not r["DEFENCE"])
        prompt = _kit.green_prompt(rng, game=GAME, blurb="a small grid-tactics game with a seeded initiative order and terrain movement costs", file="src/Banner.java", verify=_scen.VERIFY[LANG], used=used)
        yield Task(slug=f"{i + 1:02d}-" + ("counter" if r["COUNTER"] else "nocounter") + ("-defence" if r["DEFENCE"] else "") + f"-f{r['FOREST']}-r{r['ROUNDS']}", prompt=prompt,
                   difficulty=max(3, min(5, d)), start=start, hidden=hidden, solution={"src/Banner.java": sol["src/Banner.java"]}, verify=_scen.VERIFY[LANG], timeout_s=240,
                   tags=["tactics", "initiative", "rng", "scenarios"], notes={"rules": r})


BUGS = [
    Bug("initiative-tie", "Ties in initiative are broken the wrong way",
        "When two units have the same initiative the one with the larger id acts first; the README says the smaller id goes first.",
        [("order.sort((a, b) -> a.initiative != b.initiative ? b.initiative - a.initiative : a.id.compareTo(b.id));", "order.sort((a, b) -> a.initiative != b.initiative ? b.initiative - a.initiative : b.id.compareTo(a.id));")], difficulty=2),
    Bug("dice-bits", "Initiative rolls don't follow the generator spec",
        "For a given seed the initiative values differ from the README's generator; the draw seems to use different bits of the state.",
        [("((next() >> 16) % INITIATIVE_DICE)", "((next() >> 8) % INITIATIVE_DICE)")], difficulty=3),
    Bug("forest-cost", "Forests cost the same as plain ground",
        "Units walk through forests as if they were plain: a 3-move scout reaches cells that cost more than its move points.",
        [("return c == 'f' ? FOREST_COST : 1;", "return 1;")], difficulty=2),
    Bug("pass-through", "Units can walk through other units",
        "A unit can move through cells occupied by other units (even enemies) as long as it doesn't end on one.",
        [("if (c == '#' || c == '~' || at(nx, ny) != null) continue;", "if (c == '#' || c == '~') continue;")], difficulty=3),
    Bug("range-adjacent", "Archers can shoot adjacent targets only",
        "Archers can attack at distance 2 but not at distance 1, although range 2 should include the neighbouring cells.",
        [("if (t.sideA != u.sideA && dd >= 1 && dd <= STATS[u.type][3]) out.add(\"attack \" + t.id);", "if (t.sideA != u.sideA && dd >= STATS[u.type][3] && dd <= STATS[u.type][3]) out.add(\"attack \" + t.id);")], difficulty=3),
    Bug("forest-defence", "The forest protects the attacker instead of the defender",
        "Units standing in a forest take full damage, while units that attack from a forest do less damage than their attack value: the forest bonus is applied to the wrong unit.",
        [("if (FOREST_DEFENCE && terrain[t.y][t.x] == 'f') dmg = Math.max(1, dmg - 1);", "if (FOREST_DEFENCE && terrain[u.y][u.x] == 'f') dmg = Math.max(1, dmg - 1);")], difficulty=2, rules=dict(DEFENCE=True)),
    Bug("counter-damage", "Counter-attacks hit as hard as attacks",
        "Counter-attacks do full damage; they should deal half the defender's attack (at least 1).",
        [("int back = Math.max(1, STATS[t.type][1] / 2);", "int back = STATS[t.type][1];")], difficulty=2, rules=dict(COUNTER=True)),
    Bug("counter-range", "Everyone can counter at any distance",
        "Archers' targets that only have range 1 counter-attack even when the archer shoots from two cells away.",
        [("} else if (COUNTER && dist(u, t) <= STATS[t.type][3]) {", "} else if (COUNTER) {")], difficulty=3, rules=dict(COUNTER=True)),
    Bug("move-twice", "Units can move more than once per turn",
        "After moving, the unit is offered more `move` commands in the same turn; it should only be able to attack or end.",
        [("            moved = true;\n            ev.add(u.id + \" moves to \"", "            ev.add(u.id + \" moves to \"")], difficulty=2),
    Bug("dead-in-order", "Dead units still get a turn",
        "A unit that has been killed earlier in the round still shows up as the active unit later in the same round.",
        [("units.remove(t);\n                order.remove(t);\n                ev.add(t.id + \" dies\");", "units.remove(t);\n                ev.add(t.id + \" dies\");")], difficulty=3),
    Bug("time-limit", "The battle lasts one round too long",
        "Games on a time limit last one round longer than the README says: the last allowed round is followed by one more.",
        [("if (round > MAX_ROUNDS) {", "if (round > MAX_ROUNDS + 1) {")], difficulty=2),
    Bug("time-winner", "The winner on time is decided by unit count",
        "When the battle ends on time the side with more units wins, but the README says total remaining hp decides.",
        [("result = hpA > hpB ? \"A\" : hpB > hpA ? \"B\" : \"draw\";", "result = a && b ? (countA(units) > countB(units) ? \"A\" : countB(units) > countA(units) ? \"B\" : \"draw\") : \"draw\";")], difficulty=3),
    Bug("hp-display", "Negative hp is shown after overkill",
        "A unit killed by a big hit is reported with a negative remaining hp, e.g. `(hp -3)`; it should show 0.",
        [("ev.add(u.id + \" hits \" + t.id + \" \" + dmg + \" (hp \" + Math.max(t.hp, 0) + \")\");", "ev.add(u.id + \" hits \" + t.id + \" \" + dmg + \" (hp \" + t.hp + \")\");")], difficulty=1),
    Bug("moved-flag", "The `moved` flag leaks into the next unit's turn",
        "After a unit that moved ends its turn, the next unit is shown as `moved` and cannot move.",
        [("        } else {\n            moved = false;\n        }\n    }\n\n    public String render() {", "        }\n    }\n\n    public String render() {")], difficulty=3),
]
BUGS[11] = Bug("hp-display", BUGS[11].title, BUGS[11].symptom, BUGS[11].edits, difficulty=1)
_helpers = '''
    private static int countA(List<Unit> us) {
        int n = 0;
        for (Unit x : us) if (x.sideA) n++;
        return n;
    }

    private static int countB(List<Unit> us) {
        return us.size() - countA(us);
    }
'''
BUGS = [b if b.id != "time-winner" else Bug(b.id, b.title, b.symptom, [("private int next() {", _helpers.strip("\n").replace("\n    ", "\n") + "\n\nprivate int next() {")] + b.edits, b.path, b.difficulty, b.rules, b.detail) for b in BUGS]
_B = {b.id: b for b in BUGS}
BUGS_ALL = BUGS + [
    _kit.combine(_B["hp-display"], _B["time-limit"], difficulty=3),
    _kit.combine(_B["initiative-tie"], _B["forest-cost"], _B["counter-damage"], difficulty=4),
]


@family("games-banner-fix", category="games", lang="java", kind="fix", n=15,
        summary="hand-injected defects in the Banner engine (initiative, movement, ranges, counters, order bookkeeping, time limit)")
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
        ctx = {"files": ["src/Banner.java"], "verify": _scen.VERIFY[LANG]}
        yield _kit.bug_task(game=GAME, lang=LANG, base_files=base, tests=tests, hidden=hidden, bug=bug, ctx=ctx, rng=rng, used=used, k=k,
                            tags=["tactics", "initiative"], timeout_s=240, extra_notes={"rules": r})
