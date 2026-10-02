"""Hearthline (go): a tower-defence tick simulation with an exact tick order, three towers, three enemy kinds and
sell-back. Build, fix and auto-builder (AI) tasks; a python model cross-checks the reference and plays builders."""
from __future__ import annotations

import json

from fx import Task, dd, family

from . import _kit, _scen
from ._kit import Bug, tabs

LANG = "go"
GAME = "Hearthline"
PKG = "hearth"
DEFAULT = dict(LIVES=10, GOLD=20, SELL=50, FROST=False)

ENEMIES = {"imp": ("i", 4, 1, 1, 2, 1), "bat": ("b", 3, 2, 1, 3, 1), "ogre": ("o", 14, 1, 2, 6, 3)}  # letter, hp, step, every, reward, leak
TOWERS = {"arrow": ("A", 6, 2, 0), "mortar": ("M", 12, 3, 2), "frost": ("F", 9, 2, 1)}  # letter, cost, range, wait


def header(r: dict) -> str:
    return dd(f'''
        // ---- house rules for this keep (they are part of the specification, see README.md) ----
        const (
            defaultLives = {r["LIVES"]}
            defaultGold  = {r["GOLD"]}
            sellPercent  = {r["SELL"]}
            frostEnabled = {"true" if r["FROST"] else "false"}
        )
        // ----------------------------------------------------------------------------------------
    ''')


BODY = dd(r'''
    type enemyStat struct {
        letter byte
        hp     int
        step   int
        every  int
        reward int
        leak   int
    }

    var enemyStats = map[string]enemyStat{
        "imp":  {'i', 4, 1, 1, 2, 1},
        "bat":  {'b', 3, 2, 1, 3, 1},
        "ogre": {'o', 14, 1, 2, 6, 3},
    }

    type towerStat struct {
        letter byte
        cost   int
        rng    int
        wait   int
    }

    var towerStats = map[string]towerStat{
        "arrow":  {'A', 6, 2, 0},
        "mortar": {'M', 12, 3, 2},
        "frost":  {'F', 9, 2, 1},
    }

    type tower struct {
        kind string
        x, y int
        wait int
    }

    type enemy struct {
        id    int
        kind  string
        pos   int
        hp    int
        age   int
        slow  int
    }

    type wave struct {
        start    int
        kind     string
        count    int
        interval int
    }

    // Game is one game of Hearthline.
    type Game struct {
        w, h    int
        rocks   map[[2]int]bool
        path    [][2]int
        towers  []*tower
        enemies []*enemy
        waves   []wave
        nextID  int
        tick    int
        gold    int
        lives   int
        status  string
    }

    // NewGame parses a level: lines `size W H`, `spawn X Y`, `path R3 D2 ...`, `rock X Y`, `gold N`, `lives N`, `wave START KIND COUNT INTERVAL`.
    func NewGame(level string) (*Game, error) {
        g := &Game{rocks: map[[2]int]bool{}, gold: defaultGold, lives: defaultLives, status: "playing"}
        var sx, sy int
        var moves []string
        for _, line := range strings.Split(level, "\n") {
            f := strings.Fields(line)
            if len(f) == 0 {
                continue
            }
            num := func(i int) int {
                n, _ := strconv.Atoi(f[i])
                return n
            }
            switch f[0] {
            case "size":
                g.w, g.h = num(1), num(2)
            case "spawn":
                sx, sy = num(1), num(2)
            case "path":
                moves = f[1:]
            case "rock":
                g.rocks[[2]int{num(1), num(2)}] = true
            case "gold":
                g.gold = num(1)
            case "lives":
                g.lives = num(1)
            case "wave":
                g.waves = append(g.waves, wave{num(1), f[2], num(3), num(4)})
            default:
                return nil, fmt.Errorf("unknown line %q", line)
            }
        }
        x, y := sx, sy
        g.path = append(g.path, [2]int{x, y})
        for _, m := range moves {
            n, _ := strconv.Atoi(m[1:])
            for i := 0; i < n; i++ {
                switch m[0] {
                case 'U':
                    y--
                case 'D':
                    y++
                case 'L':
                    x--
                case 'R':
                    x++
                }
                g.path = append(g.path, [2]int{x, y})
            }
        }
        return g, nil
    }

    func (g *Game) onPath(x, y int) bool {
        for _, p := range g.path {
            if p[0] == x && p[1] == y {
                return true
            }
        }
        return false
    }

    func (g *Game) towerAt(x, y int) *tower {
        for _, t := range g.towers {
            if t.x == x && t.y == y {
                return t
            }
        }
        return nil
    }

    func (g *Game) pending() int {
        n := 0
        for _, w := range g.waves {
            for j := 0; j < w.count; j++ {
                if w.start+j*w.interval >= g.tick {
                    n++
                }
            }
        }
        return n
    }

    // LegalMoves lists `tick`, every affordable `build <kind> <x> <y>` on free ground and every `sell <x> <y>`.
    func (g *Game) LegalMoves() []string {
        if g.status != "playing" {
            return nil
        }
        out := []string{"tick"}
        for y := 0; y < g.h; y++ {
            for x := 0; x < g.w; x++ {
                if t := g.towerAt(x, y); t != nil {
                    out = append(out, fmt.Sprintf("sell %d %d", x, y))
                    continue
                }
                if g.rocks[[2]int{x, y}] || g.onPath(x, y) {
                    continue
                }
                for _, k := range []string{"arrow", "mortar", "frost"} {
                    if k == "frost" && !frostEnabled {
                        continue
                    }
                    if g.gold >= towerStats[k].cost {
                        out = append(out, fmt.Sprintf("build %s %d %d", k, x, y))
                    }
                }
            }
        }
        return out
    }

    // Apply runs one command and returns its event text.
    func (g *Game) Apply(cmd string) (string, error) {
        legal := false
        for _, m := range g.LegalMoves() {
            if m == cmd {
                legal = true
                break
            }
        }
        if !legal {
            return "", fmt.Errorf("illegal command %q", cmd)
        }
        f := strings.Fields(cmd)
        switch f[0] {
        case "build":
            x, _ := strconv.Atoi(f[2])
            y, _ := strconv.Atoi(f[3])
            st := towerStats[f[1]]
            g.gold -= st.cost
            g.towers = append(g.towers, &tower{kind: f[1], x: x, y: y})
            return fmt.Sprintf("built %s %d,%d -%d", f[1], x, y, st.cost), nil
        case "sell":
            x, _ := strconv.Atoi(f[1])
            y, _ := strconv.Atoi(f[2])
            t := g.towerAt(x, y)
            refund := towerStats[t.kind].cost * sellPercent / 100
            g.gold += refund
            for i, tt := range g.towers {
                if tt == t {
                    g.towers = append(g.towers[:i], g.towers[i+1:]...)
                    break
                }
            }
            return fmt.Sprintf("sold %s %d,%d +%d", t.kind, x, y, refund), nil
        }
        return g.runTick(), nil
    }

    func abs(a int) int {
        if a < 0 {
            return -a
        }
        return a
    }

    func (g *Game) cell(e *enemy) [2]int { return g.path[e.pos] }

    func (g *Game) runTick() string {
        var ev []string
        // 1. spawns
        for _, w := range g.waves {
            for j := 0; j < w.count; j++ {
                if w.start+j*w.interval == g.tick {
                    g.nextID++
                    st := enemyStats[w.kind]
                    g.enemies = append(g.enemies, &enemy{id: g.nextID, kind: w.kind, hp: st.hp})
                    ev = append(ev, fmt.Sprintf("spawn %c%d", st.letter, g.nextID))
                }
            }
        }
        // 2. towers fire, in the order they were built
        for _, t := range g.towers {
            if t.wait > 0 {
                continue
            }
            st := towerStats[t.kind]
            var target *enemy
            for _, e := range g.enemies {
                c := g.cell(e)
                if e.hp <= 0 || abs(c[0]-t.x)+abs(c[1]-t.y) > st.rng {
                    continue
                }
                if target == nil || e.pos > target.pos {
                    target = e
                }
            }
            if target == nil {
                continue
            }
            tag := fmt.Sprintf("%c(%d,%d)", st.letter, t.x, t.y)
            switch t.kind {
            case "arrow":
                target.hp -= 2
                ev = append(ev, fmt.Sprintf("%s hits %c%d 2", tag, enemyStats[target.kind].letter, target.id))
            case "frost":
                target.hp--
                target.slow = 1
                ev = append(ev, fmt.Sprintf("%s hits %c%d 1", tag, enemyStats[target.kind].letter, target.id))
            case "mortar":
                target.hp -= 3
                ev = append(ev, fmt.Sprintf("%s hits %c%d 3", tag, enemyStats[target.kind].letter, target.id))
                tc := g.cell(target)
                for _, e := range g.enemies {
                    c := g.cell(e)
                    if e != target && e.hp > 0 && abs(c[0]-tc[0])+abs(c[1]-tc[1]) <= 1 {
                        e.hp -= 2
                        ev = append(ev, fmt.Sprintf("%s splashes %c%d 2", tag, enemyStats[e.kind].letter, e.id))
                    }
                }
            }
            t.wait = st.wait
        }
        // 3. deaths
        alive := g.enemies[:0]
        for _, e := range g.enemies {
            if e.hp <= 0 {
                st := enemyStats[e.kind]
                g.gold += st.reward
                ev = append(ev, fmt.Sprintf("%c%d dies +%d", st.letter, e.id, st.reward))
            } else {
                alive = append(alive, e)
            }
        }
        g.enemies = alive
        // 4. movement
        remaining := g.enemies[:0]
        for i, e := range g.enemies {
            st := enemyStats[e.kind]
            if e.slow == 0 && e.age%st.every == 0 {
                e.pos += st.step
            }
            if e.pos >= len(g.path)-1 {
                g.lives -= st.leak
                ev = append(ev, fmt.Sprintf("%c%d leaks %d", st.letter, e.id, st.leak))
                if g.lives <= 0 {
                    g.status = "lost"
                    remaining = append(remaining, g.enemies[i+1:]...)
                    break
                }
                continue
            }
            remaining = append(remaining, e)
        }
        g.enemies = remaining
        // 5. end of tick
        if g.status == "playing" {
            for _, e := range g.enemies {
                e.age++
                if e.slow > 0 {
                    e.slow--
                }
            }
            for _, t := range g.towers {
                if t.wait > 0 {
                    t.wait--
                }
            }
        }
        g.tick++
        // 6. outcome
        if g.status == "playing" && len(g.enemies) == 0 && g.pending() == 0 {
            g.status = "won"
        }
        if len(ev) == 0 {
            return "quiet"
        }
        return strings.Join(ev, "; ")
    }

    // Gold returns the gold in the treasury.
    func (g *Game) Gold() int { return g.gold }

    // Lives returns the lives left.
    func (g *Game) Lives() int { return g.lives }

    // Status returns "playing", "won" or "lost".
    func (g *Game) Status() string { return g.status }

    // Render draws the keep.
    func (g *Game) Render() string {
        var lines []string
        for y := 0; y < g.h; y++ {
            row := make([]byte, g.w)
            for x := 0; x < g.w; x++ {
                ch := byte('.')
                if g.rocks[[2]int{x, y}] {
                    ch = '#'
                }
                for i, p := range g.path {
                    if p[0] == x && p[1] == y {
                        ch = ':'
                        if i == 0 {
                            ch = 'S'
                        } else if i == len(g.path)-1 {
                            ch = 'H'
                        }
                    }
                }
                if t := g.towerAt(x, y); t != nil {
                    ch = towerStats[t.kind].letter
                }
                for _, e := range g.enemies {
                    if c := g.cell(e); c[0] == x && c[1] == y {
                        ch = enemyStats[e.kind].letter
                        break
                    }
                }
                row[x] = ch
            }
            lines = append(lines, string(row))
        }
        status := fmt.Sprintf("tick %d gold %d lives %d foes %d next %d", g.tick, g.gold, g.lives, len(g.enemies), g.pending())
        switch g.status {
        case "won":
            status += " WON"
        case "lost":
            status += " LOST"
        }
        return strings.Join(append(lines, status), "\n")
    }
''')


def engine(r: dict) -> str:
    src = ('// Package hearth is a tower-defence tick simulation. The rules are in README.md.\npackage hearth\n\nimport (\n\t"fmt"\n\t"strconv"\n\t"strings"\n)\n\n'
           + header(r) + "\n" + BODY)
    return tabs(src)


STUB = tabs(dd(r'''
    // Package hearth is a tower-defence tick simulation. The rules and the API are in README.md.
    package hearth

    // Game is one game of Hearthline.
    type Game struct{}

    // NewGame parses a level.
    func NewGame(level string) (*Game, error) { panic("not implemented") }

    // LegalMoves lists the legal commands, in any order; empty when the game is over.
    func (g *Game) LegalMoves() []string { panic("not implemented") }

    // Apply runs one command and returns its event text; it returns an error (and changes nothing) for an illegal command.
    func (g *Game) Apply(cmd string) (string, error) { panic("not implemented") }

    // Render draws the keep.
    func (g *Game) Render() string { panic("not implemented") }

    // Gold returns the gold in the treasury.
    func (g *Game) Gold() int { panic("not implemented") }

    // Lives returns the lives left.
    func (g *Game) Lives() int { panic("not implemented") }

    // Status returns "playing", "won" or "lost".
    func (g *Game) Status() string { panic("not implemented") }
'''))

ADAPTER = {"adapter_test.go": tabs(dd(r'''
    package hearth

    import (
        "sort"
        "strconv"
        "strings"
    )

    // adapter maps scenario commands onto the engine API (the scenario runner is scenarios_test.go).
    type adapter struct{ g *Game }

    func (a *adapter) run(verb, args string) string {
        switch verb {
        case "new": // new <level lines joined by |>
            g, err := NewGame(strings.ReplaceAll(args, "|", "\n"))
            if err != nil {
                return "error: " + err.Error()
            }
            a.g = g
            return "ok"
        case "do": // do <command>: the event text, or "illegal"
            ev, err := a.g.Apply(args)
            if err != nil {
                return "illegal"
            }
            return ev
        case "legal": // sorted legal commands joined by "," ("-" when none); `tick` is repeated so that random play lets time pass
            m := append([]string(nil), a.g.LegalMoves()...)
            sort.Strings(m)
            if len(m) == 0 {
                return "-"
            }
            for i := 0; i < 6; i++ {
                m = append(m, "tick")
            }
            return strings.Join(m, ",")
        case "render":
            return a.g.Render()
        case "status": // "<status> <gold> <lives>"
            return a.g.Status() + " " + strconv.Itoa(a.g.Gold()) + " " + strconv.Itoa(a.g.Lives())
        }
        panic("unknown verb " + verb)
    }
'''))}


# ----------------------------------------------------------------------------------------------------- python model

class Model:
    def __init__(self, level: str, r: dict):
        self.r = r
        self.rocks, self.waves = set(), []
        self.gold, self.lives = r["GOLD"], r["LIVES"]
        sx = sy = 0
        moves = []
        self.w = self.h = 0
        for line in level.split("\n"):
            f = line.split()
            if not f:
                continue
            if f[0] == "size":
                self.w, self.h = int(f[1]), int(f[2])
            elif f[0] == "spawn":
                sx, sy = int(f[1]), int(f[2])
            elif f[0] == "path":
                moves = f[1:]
            elif f[0] == "rock":
                self.rocks.add((int(f[1]), int(f[2])))
            elif f[0] == "gold":
                self.gold = int(f[1])
            elif f[0] == "lives":
                self.lives = int(f[1])
            elif f[0] == "wave":
                self.waves.append((int(f[1]), f[2], int(f[3]), int(f[4])))
        self.path = [(sx, sy)]
        x, y = sx, sy
        for m in moves:
            for _ in range(int(m[1:])):
                dx, dy = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}[m[0]]
                x, y = x + dx, y + dy
                self.path.append((x, y))
        self.towers = []  # [kind, x, y, wait]
        self.enemies = []  # dicts
        self.next_id = 0
        self.tick = 0
        self.status = "playing"

    def pending(self):
        return sum(1 for (s, k, c, i) in self.waves for j in range(c) if s + j * i >= self.tick)

    def tower_at(self, x, y):
        return next((t for t in self.towers if t[1] == x and t[2] == y), None)

    def legal(self):
        if self.status != "playing":
            return []
        out = ["tick"]
        for y in range(self.h):
            for x in range(self.w):
                if self.tower_at(x, y):
                    out.append("sell %d %d" % (x, y))
                    continue
                if (x, y) in self.rocks or (x, y) in self.path:
                    continue
                for k in ("arrow", "mortar", "frost"):
                    if k == "frost" and not self.r["FROST"]:
                        continue
                    if self.gold >= TOWERS[k][1]:
                        out.append("build %s %d %d" % (k, x, y))
        return out

    def apply(self, cmd):
        f = cmd.split()
        if f[0] == "build":
            x, y = int(f[2]), int(f[3])
            self.gold -= TOWERS[f[1]][1]
            self.towers.append([f[1], x, y, 0])
            return "built %s %d,%d -%d" % (f[1], x, y, TOWERS[f[1]][1])
        if f[0] == "sell":
            x, y = int(f[1]), int(f[2])
            t = self.tower_at(x, y)
            refund = TOWERS[t[0]][1] * self.r["SELL"] // 100
            self.gold += refund
            self.towers.remove(t)
            return "sold %s %d,%d +%d" % (t[0], x, y, refund)
        return self.run_tick()

    def run_tick(self):
        ev = []
        for (s, k, c, i) in self.waves:
            for j in range(c):
                if s + j * i == self.tick:
                    self.next_id += 1
                    self.enemies.append(dict(id=self.next_id, kind=k, pos=0, hp=ENEMIES[k][1], age=0, slow=0))
                    ev.append("spawn %s%d" % (ENEMIES[k][0], self.next_id))
        for t in self.towers:
            if t[3] > 0:
                continue
            letter, cost, rng_, wait = TOWERS[t[0]]
            target = None
            for e in self.enemies:
                c = self.path[e["pos"]]
                if e["hp"] <= 0 or abs(c[0] - t[1]) + abs(c[1] - t[2]) > rng_:
                    continue
                if target is None or e["pos"] > target["pos"]:
                    target = e
            if target is None:
                continue
            tag = "%s(%d,%d)" % (letter, t[1], t[2])
            tl = ENEMIES[target["kind"]][0]
            if t[0] == "arrow":
                target["hp"] -= 2
                ev.append("%s hits %s%d 2" % (tag, tl, target["id"]))
            elif t[0] == "frost":
                target["hp"] -= 1
                target["slow"] = 1
                ev.append("%s hits %s%d 1" % (tag, tl, target["id"]))
            else:
                target["hp"] -= 3
                ev.append("%s hits %s%d 3" % (tag, tl, target["id"]))
                tc = self.path[target["pos"]]
                for e in self.enemies:
                    c = self.path[e["pos"]]
                    if e is not target and e["hp"] > 0 and abs(c[0] - tc[0]) + abs(c[1] - tc[1]) <= 1:
                        e["hp"] -= 2
                        ev.append("%s splashes %s%d 2" % (tag, ENEMIES[e["kind"]][0], e["id"]))
            t[3] = wait
        alive = []
        for e in self.enemies:
            if e["hp"] <= 0:
                st = ENEMIES[e["kind"]]
                self.gold += st[4]
                ev.append("%s%d dies +%d" % (st[0], e["id"], st[4]))
            else:
                alive.append(e)
        self.enemies = alive
        remaining = []
        for idx, e in enumerate(self.enemies):
            st = ENEMIES[e["kind"]]
            if e["slow"] == 0 and e["age"] % st[3] == 0:
                e["pos"] += st[2]
            if e["pos"] >= len(self.path) - 1:
                self.lives -= st[5]
                ev.append("%s%d leaks %d" % (st[0], e["id"], st[5]))
                if self.lives <= 0:
                    self.status = "lost"
                    remaining += self.enemies[idx + 1:]
                    break
                continue
            remaining.append(e)
        self.enemies = remaining
        if self.status == "playing":
            for e in self.enemies:
                e["age"] += 1
                if e["slow"] > 0:
                    e["slow"] -= 1
            for t in self.towers:
                if t[3] > 0:
                    t[3] -= 1
        self.tick += 1
        if self.status == "playing" and not self.enemies and self.pending() == 0:
            self.status = "won"
        return "; ".join(ev) if ev else "quiet"

    def render(self):
        rows = []
        for y in range(self.h):
            row = ""
            for x in range(self.w):
                ch = "#" if (x, y) in self.rocks else "."
                for i, p in enumerate(self.path):
                    if p == (x, y):
                        ch = "S" if i == 0 else "H" if i == len(self.path) - 1 else ":"
                t = self.tower_at(x, y)
                if t:
                    ch = TOWERS[t[0]][0]
                for e in self.enemies:
                    if self.path[e["pos"]] == (x, y):
                        ch = ENEMIES[e["kind"]][0]
                        break
                row += ch
            rows.append(row)
        status = "tick %d gold %d lives %d foes %d next %d" % (self.tick, self.gold, self.lives, len(self.enemies), self.pending())
        if self.status == "won":
            status += " WON"
        elif self.status == "lost":
            status += " LOST"
        return "\\n".join(rows + [status])


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
                m = Model(args.replace("|", "\n"), r)
            elif verb == "do":
                if args in m.legal():
                    got = m.apply(args)
                    assert got == want, f"model/engine disagree on {cmd}: {got!r} vs {want!r}"
                else:
                    assert want == "illegal", f"model says illegal for {cmd}, engine says {want!r}"
            elif verb == "legal":
                lst = sorted(m.legal())
                got = ",".join(lst + ["tick"] * 6) if lst else "-"
                assert got == want, f"legal disagree: {got[:200]!r} vs {want[:200]!r}"
            elif verb == "status":
                got = f"{m.status} {m.gold} {m.lives}"
                assert got == want, f"status disagree {got!r} vs {want!r}"
            elif verb == "render":
                assert m.render() == want, f"render disagree:\n{m.render()}\n{want}"
            cmd = None


# ----------------------------------------------------------------------------------------------------- levels and policies

def make_level(rng, w: int, h: int, segs: int, nwaves: int, r: dict, rocks: int = 6) -> str:
    """A random self-avoiding path of `segs` straight segments from the left edge, rocks off the path, some waves."""
    for _ in range(500):
        x, y = 0, rng.randrange(h)
        cells = [(x, y)]
        moves = []
        ok = True
        d = "R"
        for k in range(segs):
            if k % 2 == 0:
                d = "R" if k == 0 else rng.choice("RR" + ("L" if False else ""))
            else:
                d = rng.choice("UD")
            n = rng.randint(2, max(2, (w - 2) // 2)) if d in "RL" else rng.randint(1, max(1, h - 2))
            for _s in range(n):
                dx, dy = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}[d]
                x, y = x + dx, y + dy
                if not (0 <= x < w and 0 <= y < h) or (x, y) in cells:
                    ok = False
                    break
                cells.append((x, y))
            else:
                moves.append(f"{d}{n}")
                continue
            break
        if ok and len(cells) >= 8:
            break
    else:
        raise RuntimeError("hearth: no path")
    free = [(a, b) for a in range(w) for b in range(h) if (a, b) not in cells]
    rng.shuffle(free)
    lines = [f"size {w} {h}", f"spawn {cells[0][0]} {cells[0][1]}", "path " + " ".join(moves)]
    lines += [f"rock {a} {b}" for a, b in free[:rocks]]
    if rng.randrange(2):
        lines.append(f"gold {rng.choice([14, 26, 40])}")
    if rng.randrange(3) == 0:
        lines.append(f"lives {rng.choice([3, 5, 12])}")
    t = 0
    kinds = ["imp", "bat", "ogre"]
    for k in range(nwaves):
        kind = kinds[min(len(kinds) - 1, rng.randrange(0, 3))]
        lines.append(f"wave {t} {kind} {rng.randint(2, 6)} {rng.randint(1, 3)}")
        t += rng.randint(6, 14)
    return "\n".join(lines)


def builder_commands(rng, level: str, r: dict, ticks: int, skill: int) -> list[str]:
    """A simple builder: buys towers next to the path whenever it can, ticks otherwise; the python model plays it."""
    m = Model(level, r)
    cmds = []
    near = []
    for y in range(m.h):
        for x in range(m.w):
            if (x, y) in m.rocks or (x, y) in m.path:
                continue
            d = min(abs(x - px) + abs(y - py) for px, py in m.path)
            if d <= 2:
                near.append((d, rng.random(), x, y))
    near.sort()
    for _ in range(ticks):
        if m.status != "playing":
            break
        legal = m.legal()
        pick = None
        if rng.randrange(100) < skill:
            builds = [c for c in legal if c.startswith("build")]
            sells = [c for c in legal if c.startswith("sell")]
            cands = [(d, x, y) for d, _, x, y in near if not m.tower_at(x, y)]
            if builds and cands:
                kind = rng.choice(["arrow", "arrow", "mortar"] + (["frost"] if r["FROST"] else []))
                for d, x, y in cands:
                    c = f"build {kind} {x} {y}"
                    if c in legal:
                        pick = c
                        break
            if pick is None and sells and rng.randrange(8) == 0:
                pick = rng.choice(sells)
        if pick is None:
            pick = "tick"
        m.apply(pick)
        cmds.append(pick)
    return cmds


def scripts(rng, r: dict) -> dict[str, str]:
    parts = []
    for i in range(5):
        lv = make_level(rng, rng.choice([9, 10, 12]), rng.choice([6, 7, 8]), rng.choice([3, 4, 5]), rng.choice([2, 3, 4]), r)
        row = lv.replace("\n", "|")
        cmds = builder_commands(rng, lv, r, 260, skill=[60, 35, 20, 50, 10][i])
        parts.append(f"# scenario builder {i + 1}\n> new {row}\n> render\n" + "\n".join(f"> do {c}" + ("\n> render" if k % 9 == 8 else "") for k, c in enumerate(cmds)) + "\n> render\n> status")
        parts.append(f"# scenario random {i + 1}\n> new {row}\n~ rand 250 {rng.randrange(1, 900)} every=10 emit=render,status junk=tick now|build arrow 0 0|build tower 1 1|sell|build mortar -1 2|")
    lv = "size 8 5\nspawn 0 2\npath R7\nrock 3 1\ngold 40\nlives 4\nwave 0 imp 3 1\nwave 4 bat 3 1\nwave 9 ogre 2 3"
    parts.append("# scenario a straight lane\n> new " + lv.replace("\n", "|") + "\n" + "\n".join(["> do build arrow 3 2" if False else "> do build arrow 2 1", "> do build arrow 4 3", "> do build mortar 5 1", "> do sell 2 1", "> do build arrow 2 1"] + ["> do tick"] * 40) + "\n> render\n> status")
    return {"hidden_games": "\n".join(parts) + "\n"}


EXAMPLE_LEVEL = "size 8 5\nspawn 0 2\npath R7\nrock 3 1\ngold 30\nlives 3\nwave 0 imp 2 2\nwave 6 ogre 1 1"


def example_script() -> str:
    lv = EXAMPLE_LEVEL.replace("\n", "|")
    return (f"# scenario a short lane\n> new {lv}\n> render\n> legal\n> do build arrow 2 1\n> do tick\n> do tick\n> do tick\n> render\n> do sell 2 1\n> do build mortar 2 3\n"
            + "\n".join(["> do tick"] * 6) + "\n> render\n> status\n")


def readme(r: dict) -> str:
    s = []
    s.append("# Hearthline\n\nA tower-defence simulation in discrete ticks. Enemies walk a fixed path to your hearth, towers shoot them on the way. The engine is headless: a `Game` built from a level text, a list of legal commands and exact text for every reply. "
             "The order of everything inside a tick is part of the rules.\n")
    s.append("## Level text\n\nOne record per line, fields separated by spaces (blank lines are ignored):\n\n```\nsize <W> <H>                      the keep is W columns by H rows, (x, y) = (column, row), (0,0) top left\nspawn <x> <y>                    the first cell of the path\n"
             "path <D><n> <D><n> ...           from the spawn cell: n steps in direction U D L R, for each token\nrock <x> <y>                     an unbuildable cell (any number of lines)\ngold <n>                         starting gold (optional)\nlives <n>                        starting lives (optional)\n"
             "wave <start> <kind> <count> <interval>   `count` enemies of `kind`, the first at tick `start`, then one every `interval` ticks\n```\n\n"
             f"The path cells are numbered `0, 1, 2, ...` from the spawn cell; the last one is the *hearth*. Cells that are neither rocks nor path cells are *ground*. Without `gold`/`lives` lines the game starts with {r['GOLD']} gold and {r['LIVES']} lives. "
             "There may be several `wave` lines; enemies get numbers `1, 2, 3, ...` in order of spawning (ties: wave line order).\n")
    s.append("## Enemies and towers\n\n| enemy | name letter | hp | cells per move | moves every | gold reward | lives lost when it reaches the hearth |\n|---|---|---|---|---|---|---|\n"
             "| `imp` | `i` | 4 | 1 | tick | 2 | 1 |\n| `bat` | `b` | 3 | 2 | tick | 3 | 1 |\n| `ogre` | `o` | 14 | 1 | 2nd tick | 6 | 3 |\n\n"
             "An enemy's *name* is its letter and its number (`i1`, `o7`). It has an *age*: 0 on the tick it spawns, +1 at the end of every tick (while the game runs). It moves on the ticks where `age mod every == 0` (`every` is 1 for imps and bats, 2 for ogres).\n\n"
             "| tower | letter | cost | range (Manhattan) | damage | waits after a shot |\n|---|---|---|---|---|---|\n| `arrow` | `A` | 6 | 2 | 2 | 0 ticks (fires every tick) |\n| `mortar` | `M` | 12 | 3 | 3, and 2 to every other enemy within Manhattan distance 1 of the target | 2 ticks (fires every third tick) |\n" +
             (f"| `frost` | `F` | 9 | 2 | 1, and the target is *slowed* for one tick | 1 tick (fires every other tick) |\n" if r["FROST"] else "") + "\n" +
             ("Frost towers exist in this keep. " if r["FROST"] else "There are no frost towers in this keep (`build frost ...` is not a legal command). ") +
             "A tower's *wait* is 0 when it is built.\n")
    s.append("## Commands\n\nCommands are exact strings. `LegalMoves()` lists the legal ones; once the game is won or lost there are none.\n\n"
             f"* `build <kind> <x> <y>`: legal when the cell is ground with no tower, `kind` exists, and gold is at least its cost. Gold goes down by the cost; the tower is appended to the list of towers (build order). Event `built <kind> <x>,<y> -<cost>`.\n"
             f"* `sell <x> <y>`: legal when a tower stands there. It is removed and gold goes up by `cost * {r['SELL']} / 100` (integer division). Event `sold <kind> <x>,<y> +<refund>`.\n"
             "* `tick`: always legal. Runs one tick, below.\n\n"
             "`build` and `sell` do not advance time.\n")
    s.append("### One tick\n\nIn this order (the tick counter `tick` is 0 at the start of the game):\n\n"
             "1. **Spawns.** Every wave (in file order), for `j = 0 .. count-1`: if `start + j * interval` equals the current `tick`, a new enemy appears on path cell 0 with full hp. Event `spawn <name>`.\n"
             "2. **Towers fire**, in build order. A tower whose wait is above 0 does nothing. Otherwise its *target* is, among the enemies with `hp > 0` whose cell is within the tower's range, the one furthest along the path (largest path number); a tie "
             "(same cell) goes to the lower enemy number. No target: nothing happens and the wait stays 0. A shot deals its damage at once (events: `<T>(<x>,<y>) hits <name> <damage>`, and for mortar splash `<T>(<x>,<y>) splashes <name> 2` "
             "for each other enemy with `hp > 0` within Manhattan distance 1 of the target's cell, in enemy number order, after the `hits` event); then the tower's wait is set to its *waits after a shot* value. "
             "An enemy whose hp is already 0 or less from an earlier shot of this tick can no longer be targeted or splashed.\n"
             "3. **Deaths**, in enemy number order: every enemy with `hp <= 0` is removed, the gold gains its reward; event `<name> dies +<reward>`.\n"
             "4. **Movement**, in enemy number order. " + ("An enemy that is *slowed* does not move this tick. " if r["FROST"] else "") + "Otherwise, if `age mod every == 0`, its path number grows by its cells-per-move. An enemy whose path number reaches the last cell (or goes beyond it) *leaks*: it is removed, lives go down by its leak value, "
             "event `<name> leaks <n>`. When lives are 0 or less the game is *lost* at once: processing stops (the enemies not yet processed stay where they are, nothing else of the tick happens except the tick counter).\n"
             "5. **End of tick** (only while the game is still running): every enemy's age grows by 1" + (" and a positive slow value goes down by 1" if r["FROST"] else "") + "; every tower's wait goes down by 1 if it is above 0.\n"
             "6. `tick` grows by 1. If the game is still running and there are no enemies left and no enemy is still to spawn (no `start + j * interval >= tick`), the game is *won*.\n\n"
             "The `tick` command's reply is all events of the tick joined by `; `, or `quiet` if there were none.\n")
    s.append("## API (package `hearth`)\n\n```go\ng, err := hearth.NewGame(levelText)   // levelText: the lines above joined by \"\\n\"\ng.LegalMoves() []string               // legal commands, any order\ng.Apply(cmd string) (string, error)   // event text; an error and no change for an illegal command\n"
             "g.Render() string\ng.Gold() int\ng.Lives() int\ng.Status() string                   // \"playing\", \"won\" or \"lost\"\n```\n")
    ex = Model(EXAMPLE_LEVEL, r)
    ex.apply("build arrow 2 1")
    ex.apply("tick")
    ex.apply("tick")
    s.append("### `Render()`\n\nOne line per row (`W` characters): `.` ground, `#` rock, `S` spawn cell, `:` path, `H` hearth, a tower's letter (`A`, `M`" + (", `F`" if r["FROST"] else "") + "), and on a path cell the *lower-case letter* of the enemy standing there (if several, the lowest number). Enemies are drawn "
             "over the path markers; there are never towers on the path. Then the status line `tick <tick> gold <gold> lives <lives> foes <enemies alive> next <enemies still to spawn>`, followed by ` WON` or ` LOST` when the game is over. "
             "Lines are joined by `\\n`, no trailing newline. Example (level `" + EXAMPLE_LEVEL.replace("\n", " / ") + "`, after `build arrow 2 1`, `tick`, `tick`):\n\n```\n" + ex.render().replace("\\n", "\n") + "\n```\n")
    s.append("## Tests\n\n`go test ./...` replays the scenario files in `testdata/` (`adapter_test.go` shows how the API is called; levels are given with `|` instead of newlines; the format is described at the top of `scenarios_test.go`).\n")
    return "\n".join(s)


def project(r: dict) -> dict[str, str]:
    return {"game.go": engine(r), "go.mod": _kit.go_mod(PKG), ".gitignore": ""}


def _variants(n: int) -> list[dict]:
    plan = [dict(), dict(FROST=True), dict(SELL=75, GOLD=30), dict(LIVES=5, FROST=True, SELL=25), dict(GOLD=16, LIVES=8), dict(FROST=True, SELL=60, GOLD=26, LIVES=6)]
    return [{**DEFAULT, **o} for o in plan[:n]]


@family("games-hearth-build", category="games", lang="go", kind="greenfield", n=6,
        summary="build the Hearthline tower-defence simulation: exact tick order, targeting, splash, slow, sell-back, level parser")
def gen_build(rng, n):
    used: list[str] = []
    for i, r in enumerate(_variants(n)):
        sol = project(r)
        hidden = _kit.data_files(LANG, scripts(rng, r), sol, ADAPTER, PKG)
        for t in hidden.values():
            crosscheck(t, r)
        vis = _kit.data_files(LANG, {"examples": example_script()}, sol, ADAPTER, PKG)
        crosscheck(next(iter(vis.values())), r)
        start = {"README.md": readme(r), "game.go": STUB, "go.mod": sol["go.mod"], **_scen.check_files(LANG, ADAPTER, PKG), **vis}
        d = 4 + r["FROST"] - (r["SELL"] == 50 and not r["FROST"])
        prompt = _kit.green_prompt(rng, game=GAME, blurb="a tower-defence simulation where every tick has a fixed order of spawning, shooting, dying and moving", file="game.go",
                                   verify=_scen.VERIFY[LANG], used=used)
        yield Task(slug=f"{i + 1:02d}-" + ("frost" if r["FROST"] else "nofrost") + f"-sell{r['SELL']}-gold{r['GOLD']}", prompt=prompt, difficulty=max(3, min(5, d)), start=start, hidden=hidden,
                   solution={"game.go": sol["game.go"]}, verify=_scen.VERIFY[LANG], timeout_s=240, tags=["tower-defence", "tick-order", "scenarios"], notes={"rules": r})


BUGS = [
    Bug("fire-order", "Towers fire in the wrong order",
        "When two towers can shoot the same enemy in the same tick, the hits are listed (and resolved) in a different order than the order the towers were built in: the newest tower seems to shoot first.",
        [("for _, t := range g.towers {\n        if t.wait > 0 {\n            continue\n        }\n        st := towerStats[t.kind]", "for ti := len(g.towers) - 1; ti >= 0; ti-- {\n        t := g.towers[ti]\n        if t.wait > 0 {\n            continue\n        }\n        st := towerStats[t.kind]")], difficulty=3),
    Bug("target-first", "Towers shoot the enemy at the back",
        "Towers pick the enemy that has gone the least far along the path instead of the one closest to the hearth, so strong enemies in front get through while the tail gets shot.",
        [("if target == nil || e.pos > target.pos {", "if target == nil || e.pos < target.pos {")], difficulty=2),
    Bug("splash-radius", "Mortar splash reaches too far",
        "Mortar splash also hits enemies two cells away from the target (diagonals count as one step), which is more than the README's distance.",
        [("if e != target && e.hp > 0 && abs(c[0]-tc[0])+abs(c[1]-tc[1]) <= 1 {", "if e != target && e.hp > 0 && abs(c[0]-tc[0]) <= 1 && abs(c[1]-tc[1]) <= 1 {")], difficulty=3),
    Bug("overkill-targets", "Dead enemies keep being shot at",
        "Several towers waste shots on an enemy that an earlier tower has already killed in the same tick: the replay shows hits on an enemy right after another hit that should have finished it.",
        [("if e.hp <= 0 || abs(c[0]-t.x)+abs(c[1]-t.y) > st.rng {", "if abs(c[0]-t.x)+abs(c[1]-t.y) > st.rng {")], difficulty=3),
    Bug("cooldown-order", "Mortars fire every other tick",
        "Mortars fire more often than the README says: they fire every second tick instead of every third.",
        [("t.wait = st.wait", "t.wait = st.wait - 1\n            if t.wait < 0 {\n                t.wait = 0\n            }")], difficulty=3),
    Bug("ogre-leak", "Ogres cost one life like everyone else",
        "An ogre that gets through takes only one life, the same as an imp; it should be a lot more painful.",
        [("g.lives -= st.leak", "g.lives -= 1")], difficulty=2),
    Bug("sell-refund", "Selling refunds too much",
        "Selling a tower gives back more than the sell-back percentage: the refund looks rounded up.",
        [("refund := towerStats[t.kind].cost * sellPercent / 100", "refund := (towerStats[t.kind].cost*sellPercent + 99) / 100")], difficulty=2, rules=dict(SELL=25)),
    Bug("bat-overshoot", "Bats stop at the hearth's neighbour",
        "Bats (two cells per move) never leak when they start their move one cell before the hearth: they sit there.",
        [("if e.pos >= len(g.path)-1 {", "if e.pos == len(g.path)-1 {")], difficulty=3),
    Bug("movement-before-death", "Enemies killed this tick still take their step",
        "A killed enemy shows up as `leaks` on the same tick it was shot dead: the deaths seem to be processed after the movement instead of before it.",
        [("// 3. deaths\n    alive := g.enemies[:0]\n    for _, e := range g.enemies {\n        if e.hp <= 0 {", "// 3. deaths\n    alive := g.enemies[:0]\n    for _, e := range g.enemies {\n        if e.hp <= 0 && e.pos+1 < len(g.path)-1 {")], difficulty=4),
    Bug("pending-win", "The game is won too early",
        "The game is declared won while enemies from the last wave are still to appear; it only looks at the enemies that are on the board.",
        [("if g.status == \"playing\" && len(g.enemies) == 0 && g.pending() == 0 {", "if g.status == \"playing\" && len(g.enemies) == 0 {")], difficulty=2),
    Bug("spawn-interval", "Spawns come at the wrong spacing",
        "Within a wave the enemies spawn one tick later than they should after the first one, i.e. the interval is off by one.",
        [("if w.start+j*w.interval == g.tick {", "if w.start+j*(w.interval+1) == g.tick {")], difficulty=3),
    Bug("build-on-path", "Towers can be built on the path",
        "I managed to build a tower on a path cell, which makes the path cell show a tower instead of the road.",
        [("if g.rocks[[2]int{x, y}] || g.onPath(x, y) {", "if g.rocks[[2]int{x, y}] {")], difficulty=2),
    Bug("lives-zero", "You survive with zero lives",
        "With lives at exactly 0 the game goes on; the loss is only declared when the lives go negative.",
        [("if g.lives <= 0 {", "if g.lives < 0 {")], difficulty=2),
    Bug("slow-stays", "Frozen enemies stay frozen",
        "Frost makes enemies stop for as long as the tower keeps being able to shoot them, even when the tower is waiting: the slow effect is not wearing off after one tick.",
        [("if e.slow > 0 {\n                    e.slow--\n                }", "")], difficulty=3, rules=dict(FROST=True)),
]


def _fix_edits(b: Bug) -> Bug:
    return Bug(b.id, b.title, b.symptom, [(tabs(o), tabs(n)) for o, n in b.edits], b.path, b.difficulty, b.rules, b.detail)


BUGS = [_fix_edits(b) for b in BUGS]
_B = {b.id: b for b in BUGS}
BUGS_ALL = BUGS + [
    _kit.combine(_B["ogre-leak"], _B["lives-zero"], difficulty=3),
    _kit.combine(_B["target-first"], _B["sell-refund"], _B["pending-win"], difficulty=4),
]


@family("games-hearth-fix", category="games", lang="go", kind="fix", n=14,
        summary="hand-injected defects in the Hearthline engine (tick order, targeting, splash, cooldowns, leaks, selling, win detection)")
def gen_fix(rng, n):
    used: list[str] = []
    cache = {}
    for k, bug in enumerate(BUGS_ALL[:n]):
        r = {**DEFAULT, **bug.rules}
        key = json.dumps(r, sort_keys=True)
        if key not in cache:
            sol = project(r)
            cache[key] = (sol, _kit.data_files(LANG, scripts(rng, r), sol, ADAPTER, PKG), _kit.data_files(LANG, {"examples": example_script()}, sol, ADAPTER, PKG), readme(r))
        sol, hidden, vis, rd = cache[key]
        base = {**sol, "README.md": rd}
        tests = {**_scen.check_files(LANG, ADAPTER, PKG), **vis}
        ctx = {"files": ["game.go"], "verify": _scen.VERIFY[LANG]}
        yield _kit.bug_task(game=GAME, lang=LANG, base_files=base, tests=tests, hidden=hidden, bug=bug, ctx=ctx, rng=rng, used=used, k=k,
                            tags=["tower-defence", "tick-order"], timeout_s=240, extra_notes={"rules": r})


# ----------------------------------------------------------------------------------------------------- AI tournament

def hard_level(rng, w: int, h: int, segs: int, r: dict, waves: int = 5) -> str:
    lv = [ln for ln in make_level(rng, w, h, segs, 1, r).split("\n") if not ln.startswith(("wave", "lives", "gold"))]
    lv.append(f"gold {rng.choice([24, 30, 36])}")
    lv.append(f"lives {rng.choice([4, 5, 6])}")
    t = 0
    for k in range(waves):
        kind = ["imp", "bat", "ogre", "imp", "ogre"][k % 5]
        count = rng.randint(4, 8) if kind != "ogre" else rng.randint(2, 4)
        lv.append(f"wave {t} {kind} {count} {rng.choice([1, 2])}")
        t += rng.randint(8, 16)
    return "\n".join(lv)


AI_EXTRA = tabs(dd(r'''

    // Width returns the number of columns of the keep.
    func (g *Game) Width() int { return g.w }

    // Height returns the number of rows of the keep.
    func (g *Game) Height() int { return g.h }

    // Path returns a copy of the path cells (x, y) from the spawn cell (index 0) to the hearth (the last one).
    func (g *Game) Path() [][2]int { return append([][2]int(nil), g.path...) }

    // Tick returns the number of ticks run so far.
    func (g *Game) Tick() int { return g.tick }

    // TowerCount returns how many towers of the given kind ("arrow", "mortar", "frost") stand now.
    func (g *Game) TowerCount(kind string) int {
        n := 0
        for _, t := range g.towers {
            if t.kind == kind {
                n++
            }
        }
        return n
    }

    // Clone returns an independent copy of the game: commands applied to the copy do not affect the original.
    func (g *Game) Clone() *Game {
        c := *g
        c.towers = make([]*tower, len(g.towers))
        for i, t := range g.towers {
            tt := *t
            c.towers[i] = &tt
        }
        c.enemies = make([]*enemy, len(g.enemies))
        for i, e := range g.enemies {
            ee := *e
            c.enemies[i] = &ee
        }
        return &c
    }
'''))

AI_STUB = tabs(dd('''
    package hearth

    // Plan returns the command to run now (it may be "tick"); it is called again after every command while the game is running.
    // A command that is not in g.LegalMoves() loses the level on the spot.
    func Plan(g *Game) string {
        return "tick"
    }
'''))

AI_GOLD = tabs(dd('''
    package hearth

    import (
        "strconv"
        "strings"
    )

    // Plan builds where a tower covers the most of the path for its price (arrows first), and otherwise lets time pass.
    func Plan(g *Game) string {
        best, bestV := "tick", 0.0
        path := g.Path()
        for _, c := range g.LegalMoves() {
            f := strings.Fields(c)
            if f[0] != "build" || f[1] == "frost" {
                continue
            }
            x, _ := strconv.Atoi(f[2])
            y, _ := strconv.Atoi(f[3])
            rng, cost := 2, 6.0
            if f[1] == "mortar" {
                rng, cost = 3, 12.0
            }
            cov := 0
            for i := 1; i < len(path)-1; i++ {
                dx, dy := path[i][0]-x, path[i][1]-y
                if dx < 0 {
                    dx = -dx
                }
                if dy < 0 {
                    dy = -dy
                }
                if dx+dy <= rng {
                    cov++
                }
            }
            v := float64(cov) / cost
            if f[1] == "arrow" {
                v += 0.05
            }
            if f[1] == "mortar" && g.TowerCount("arrow") < 3 {
                v -= 1
            }
            if v > bestV {
                best, bestV = c, v
            }
        }
        return best
    }
'''))

AI_ARENA = tabs(dd('''
    // Command arena runs hearth.Plan on the sample levels: go run ./cmd/arena
    package main

    import (
        "fmt"

        "example.com/hearth"
    )

    var levels = []string{
    @@LEVELS@@
    }

    func main() {
        won := 0
        for i, level := range levels {
            g, err := hearth.NewGame(level)
            if err != nil {
                panic(err)
            }
            for g.Status() == "playing" && g.Tick() < 2000 {
                cmd := hearth.Plan(g)
                if _, err := g.Apply(cmd); err != nil {
                    fmt.Printf("level %d: illegal command %q: lost\\n", i+1, cmd)
                    break
                }
            }
            fmt.Printf("level %d: %s after %d ticks (gold %d, lives %d)\\n", i+1, g.Status(), g.Tick(), g.Gold(), g.Lives())
            if g.Status() == "won" {
                won++
            }
        }
        fmt.Printf("won %d of %d\\n", won, len(levels))
    }
'''))

AI_SCORE = tabs(dd('''
    package main

    import (
        "encoding/json"
        "fmt"

        "example.com/hearth"
    )

    var levels = []string{
    @@LEVELS@@
    }

    const floor, goal = 0.4, 0.9

    func main() {
        won := 0
        for _, level := range levels {
            g, err := hearth.NewGame(level)
            if err != nil {
                panic(err)
            }
            for g.Status() == "playing" && g.Tick() < 2000 {
                if _, err := g.Apply(hearth.Plan(g)); err != nil {
                    break
                }
            }
            if g.Status() == "won" {
                won++
            }
        }
        rate := float64(won) / float64(len(levels))
        score := (rate - floor) / (goal - floor)
        if score < 0 {
            score = 0
        }
        if score > 1 {
            score = 1
        }
        fmt.Printf("won %d of %d levels (full score from %.0f%%)\\n", won, len(levels), goal*100)
        out, _ := json.Marshal(map[string]float64{"score": float64(int(score*10000)) / 10000})
        fmt.Println(string(out))
    }
'''))


def _go_levels(levels: list[str]) -> str:
    return "\n".join("\t\"" + lv.replace("\n", "\\n") + "\"," for lv in levels)


AI_VARIANTS = [dict(rules={}, d=3), dict(rules=dict(FROST=True, SELL=75), d=3), dict(rules=dict(SELL=25, LIVES=6), d=4), dict(rules=dict(FROST=True, SELL=60, GOLD=26), d=4)]


def ai_readme(r: dict) -> str:
    return readme(r).replace("## Tests\n", dd('''
        ## Your task: the builder

        `ai.go` must define `Plan(g *Game) string`: the command to run now. The check calls it again after every command while the game is running, so `tick` is a valid answer (and the usual one once you cannot or do not want to build). A command that is
        not in `g.LegalMoves()` loses the level on the spot. The engine (`game.go`, given, do not edit) has a few read-only helpers: `g.Width()`, `g.Height()`, `g.Path()` (the path cells from the spawn to the hearth), `g.Tick()`, `g.TowerCount(kind)`,
        and `g.Clone()`, an independent copy of the game that you may play forward to look ahead; `Gold()`, `Lives()` and `Status()` as above.

        `go run ./cmd/arena` plays `Plan` on three sample levels. The check plays 12 other levels (little gold, few lives, waves of imps, bats and ogres; each level is given up after 2000 ticks) and counts the levels that end `won`. The score is
        `clamp((levels won / 12 - 0.4) / (0.9 - 0.4), 0, 1)`: 1.0 needs at least 11 of the 12 levels.

        ## Tests
    '''), 1)


@family("games-hearth-ai", category="games", lang="go", kind="greenfield", n=4,
        summary="write the auto-builder AI of a Hearthline keep (go); the fraction of generated levels it wins is the score (json-score)")
def gen_ai(rng, n):
    for i, v in enumerate(AI_VARIANTS[:n]):
        r = {**DEFAULT, **v["rules"]}
        sol = project(r)
        samples = [hard_level(rng, rng.choice([9, 10]), rng.choice([6, 7]), rng.choice([3, 4]), r, waves=4) for _ in range(3)]
        graded = [hard_level(rng, rng.choice([9, 10, 12]), rng.choice([6, 7, 8]), rng.choice([3, 4, 5]), r) for _ in range(12)]
        files = {"game.go": sol["game.go"] + "\n" + AI_EXTRA, "go.mod": sol["go.mod"], "ai.go": AI_STUB, "README.md": ai_readme(r),
                 "cmd/arena/main.go": AI_ARENA.replace("@@LEVELS@@", _go_levels(samples))}
        hidden = {"cmd/score/main.go": AI_SCORE.replace("@@LEVELS@@", _go_levels(graded))}
        s0, s1, out = _kit.check_scores(start=files, hidden=hidden, solution={"ai.go": AI_GOLD}, verify="go run ./cmd/score", name=f"hearth-ai-{i}", timeout_s=240)
        voices = [
            "Our Hearthline keep needs an auto-builder: `Plan` in `ai.go` returns the next command (build, sell or tick). README.md explains the helpers the engine offers and how the share of generated levels it wins is graded; `go run ./cmd/arena` shows three samples.",
            "`Plan` in `ai.go` never builds anything, so the keep falls to the first ogre. Write a builder that wins most of the levels the check generates (README.md has the details and the scoring). Gold is tight, so where you build matters.",
            "I want an AI that defends a Hearthline keep on its own: pick sensible tower positions (the path, the ranges and the prices are all in README.md), and tick when there is nothing worth buying. It is judged on how many of 12 hidden levels it wins.",
            "Implement the defender for Hearthline in `ai.go`. Mind that every tick has a fixed order (README.md) and that gold is scarce. `g.Clone()` lets you test a command before committing to it.",
        ]
        yield Task(slug=f"{i + 1:02d}-" + ("frost" if r["FROST"] else "nofrost") + f"-sell{r['SELL']}", prompt=voices[i % len(voices)], difficulty=v["d"], start=files, hidden=hidden,
                   solution={"ai.go": AI_GOLD}, verify="go run ./cmd/score", pass_mode="json-score", protected=["game.go", "cmd/arena/main.go"], timeout_s=240,
                   tags=["bot", "tower-defence", "tournament", "ai"], notes={"rules": r, "gold": out.strip().splitlines()[-2], "stub_score": s0})
