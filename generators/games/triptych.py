"""Triptych (go): a sliding-tile merge game in the 2048 family with merges of three (or two), walls, edge spawning and an
exact MINSTD generator. Build and fix tasks; a python model cross-checks the reference."""
from __future__ import annotations

import json

from fx import Task, dd, family

from . import _kit, _scen
from ._kit import Bug, tabs

LANG = "go"
GAME = "Triptych"
PKG = "triptych"
DEFAULT = dict(N=4, MERGE=3, WALLS=[], EDGE=False, TARGET=81)


def header(r: dict) -> str:
    walls = ", ".join("{%d, %d}" % (a, b) for a, b in r["WALLS"])
    return dd(f'''
        // ---- house rules for this board (they are part of the specification, see README.md) ----
        const (
            N         = {r["N"]}
            Merge     = {r["MERGE"]}
            SpawnEdge = {"true" if r["EDGE"] else "false"}
            Target    = {r["TARGET"]}
        )

        var walls = [][2]int{{{walls}}}
        // ------------------------------------------------------------------------------------------
    ''')


BODY = dd('''
    // Game is one game of Triptych.
    type Game struct {
        cells [N][N]int
        wall  [N][N]bool
        state uint64
        score int
        moves int
    }

    // NewGame starts a game: the generator is seeded, then two tiles are spawned.
    func NewGame(seed uint32) *Game {
        g := &Game{}
        for _, w := range walls {
            g.wall[w[0]][w[1]] = true
        }
        g.state = uint64(seed) % 2147483647
        if g.state == 0 {
            g.state = 1
        }
        g.spawn()
        g.spawn()
        return g
    }

    func (g *Game) next() uint64 {
        g.state = g.state * 48271 % 2147483647
        return g.state
    }

    func (g *Game) spawn() (int, int, int) {
        var empty, edge [][2]int
        for r := 0; r < N; r++ {
            for c := 0; c < N; c++ {
                if g.wall[r][c] || g.cells[r][c] != 0 {
                    continue
                }
                empty = append(empty, [2]int{r, c})
                if r == 0 || c == 0 || r == N-1 || c == N-1 {
                    edge = append(edge, [2]int{r, c})
                }
            }
        }
        pool := empty
        if SpawnEdge && len(edge) > 0 {
            pool = edge
        }
        p := pool[(g.next()>>8)%uint64(len(pool))]
        v := 1
        if (g.next()>>8)%8 == 0 {
            v = Merge
        }
        g.cells[p[0]][p[1]] = v
        return p[0], p[1], v
    }

    // lineCoords lists the cells of line i in reading order: the cell nearest to the wall the tiles move towards first.
    func lineCoords(dir string, i int) [N][2]int {
        var out [N][2]int
        for k := 0; k < N; k++ {
            switch dir {
            case "L":
                out[k] = [2]int{i, k}
            case "R":
                out[k] = [2]int{i, N - 1 - k}
            case "U":
                out[k] = [2]int{k, i}
            default:
                out[k] = [2]int{N - 1 - k, i}
            }
        }
        return out
    }

    func allEqual(v []int) bool {
        for _, x := range v {
            if x != v[0] {
                return false
            }
        }
        return true
    }

    // shift computes the board after a move in direction dir and the score gained.
    func (g *Game) shift(dir string) ([N][N]int, int) {
        nb := g.cells
        gain := 0
        for line := 0; line < N; line++ {
            coords := lineCoords(dir, line)
            i := 0
            for i < N {
                if g.wall[coords[i][0]][coords[i][1]] {
                    i++
                    continue
                }
                j := i
                for j < N && !g.wall[coords[j][0]][coords[j][1]] {
                    j++
                }
                var tiles []int
                for k := i; k < j; k++ {
                    if v := g.cells[coords[k][0]][coords[k][1]]; v != 0 {
                        tiles = append(tiles, v)
                    }
                }
                var out []int
                for t := 0; t < len(tiles); {
                    if t+Merge <= len(tiles) && allEqual(tiles[t:t+Merge]) {
                        out = append(out, tiles[t]*Merge)
                        gain += tiles[t] * Merge
                        t += Merge
                    } else {
                        out = append(out, tiles[t])
                        t++
                    }
                }
                for k := i; k < j; k++ {
                    v := 0
                    if k-i < len(out) {
                        v = out[k-i]
                    }
                    nb[coords[k][0]][coords[k][1]] = v
                }
                i = j
            }
        }
        return nb, gain
    }

    // LegalMoves returns the directions that change the board.
    func (g *Game) LegalMoves() []string {
        var out []string
        for _, d := range []string{"L", "R", "U", "D"} {
            if nb, _ := g.shift(d); nb != g.cells {
                out = append(out, d)
            }
        }
        return out
    }

    // Apply plays a move and returns the event text.
    func (g *Game) Apply(move string) (string, error) {
        legal := false
        for _, d := range g.LegalMoves() {
            if d == move {
                legal = true
            }
        }
        if !legal {
            return "", fmt.Errorf("illegal move %q", move)
        }
        nb, gain := g.shift(move)
        g.cells = nb
        g.score += gain
        g.moves++
        r, c, v := g.spawn()
        return fmt.Sprintf("+%d spawn %d,%d=%d", gain, r, c, v), nil
    }

    // Score returns the current score.
    func (g *Game) Score() int { return g.score }

    // Over reports whether no move is possible.
    func (g *Game) Over() bool { return len(g.LegalMoves()) == 0 }

    // Render draws the board.
    func (g *Game) Render() string {
        maxv := 0
        for r := 0; r < N; r++ {
            for c := 0; c < N; c++ {
                if g.cells[r][c] > maxv {
                    maxv = g.cells[r][c]
                }
            }
        }
        width := len(strconv.Itoa(maxv))
        head := fmt.Sprintf("score %d moves %d", g.score, g.moves)
        if maxv >= Target {
            head += " WIN"
        }
        if g.Over() {
            head += " OVER"
        }
        lines := []string{head}
        for r := 0; r < N; r++ {
            cells := make([]string, N)
            for c := 0; c < N; c++ {
                s := "."
                if g.wall[r][c] {
                    s = "#"
                } else if g.cells[r][c] != 0 {
                    s = strconv.Itoa(g.cells[r][c])
                }
                cells[c] = strings.Repeat(" ", width-len(s)) + s
            }
            lines = append(lines, strings.Join(cells, " "))
        }
        return strings.Join(lines, "\\n")
    }
''')


def engine(r: dict) -> str:
    src = ('// Package triptych is a sliding-tile merge game. The rules are in README.md.\npackage triptych\n\nimport (\n\t"fmt"\n\t"strconv"\n\t"strings"\n)\n\n'
           + header(r) + "\n" + BODY.replace("\\\\n", "\\n"))
    return tabs(src)


STUB = tabs(dd('''
    // Package triptych is a sliding-tile merge game. The rules and the API are in README.md.
    package triptych

    // Game is one game of Triptych.
    type Game struct{}

    // NewGame starts a game.
    func NewGame(seed uint32) *Game { panic("not implemented") }

    // LegalMoves returns the directions ("L", "R", "U", "D") that change the board, in any order.
    func (g *Game) LegalMoves() []string { panic("not implemented") }

    // Apply plays a move and returns the event text; it returns an error (and changes nothing) for an illegal move.
    func (g *Game) Apply(move string) (string, error) { panic("not implemented") }

    // Render draws the board.
    func (g *Game) Render() string { panic("not implemented") }

    // Score returns the current score.
    func (g *Game) Score() int { panic("not implemented") }

    // Over reports whether no move is possible.
    func (g *Game) Over() bool { panic("not implemented") }
'''))

ADAPTER = {"adapter_test.go": tabs(dd('''
    package triptych

    import (
        "sort"
        "strconv"
        "strings"
    )

    // adapter maps scenario commands onto the engine API (the scenario runner is scenarios_test.go).
    type adapter struct{ g *Game }

    func (a *adapter) run(verb, args string) string {
        switch verb {
        case "new": // new <seed>
            n, _ := strconv.ParseUint(args, 10, 32)
            a.g = NewGame(uint32(n))
            return "ok"
        case "do": // do <move>: the event text, or "illegal"
            ev, err := a.g.Apply(args)
            if err != nil {
                return "illegal"
            }
            return ev
        case "legal": // sorted legal moves joined by "," ("-" when there are none)
            m := append([]string(nil), a.g.LegalMoves()...)
            sort.Strings(m)
            if len(m) == 0 {
                return "-"
            }
            return strings.Join(m, ",")
        case "render":
            return a.g.Render()
        case "status": // "<score> <over>"
            return strconv.Itoa(a.g.Score()) + " " + strconv.FormatBool(a.g.Over())
        }
        panic("unknown verb " + verb)
    }
'''))}


# ----------------------------------------------------------------------------------------------------- python model

class Model:
    def __init__(self, seed: int, r: dict):
        self.r = r
        n = r["N"]
        self.cells = [[0] * n for _ in range(n)]
        self.wall = {tuple(w) for w in r["WALLS"]}
        self.state = seed % 2147483647 or 1
        self.score = 0
        self.moves = 0
        self.spawn()
        self.spawn()

    def next(self):
        self.state = self.state * 48271 % 2147483647
        return self.state

    def spawn(self):
        n = self.r["N"]
        empty = [(y, x) for y in range(n) for x in range(n) if (y, x) not in self.wall and self.cells[y][x] == 0]
        edge = [(y, x) for (y, x) in empty if y in (0, n - 1) or x in (0, n - 1)]
        pool = edge if (self.r["EDGE"] and edge) else empty
        y, x = pool[(self.next() >> 8) % len(pool)]
        v = self.r["MERGE"] if (self.next() >> 8) % 8 == 0 else 1
        self.cells[y][x] = v
        return y, x, v

    def shift(self, d):
        n, m = self.r["N"], self.r["MERGE"]
        nb = [row[:] for row in self.cells]
        gain = 0
        for i in range(n):
            coords = [(i, k) if d == "L" else (i, n - 1 - k) if d == "R" else (k, i) if d == "U" else (n - 1 - k, i) for k in range(n)]
            seg = []
            for c in coords + [None]:
                if c is None or c in self.wall:
                    if seg:
                        tiles = [self.cells[y][x] for y, x in seg if self.cells[y][x]]
                        out, t = [], 0
                        while t < len(tiles):
                            if t + m <= len(tiles) and len(set(tiles[t:t + m])) == 1:
                                out.append(tiles[t] * m)
                                gain += tiles[t] * m
                                t += m
                            else:
                                out.append(tiles[t])
                                t += 1
                        for k, (y, x) in enumerate(seg):
                            nb[y][x] = out[k] if k < len(out) else 0
                    seg = []
                else:
                    seg.append(c)
        return nb, gain

    def legal(self):
        return [d for d in "LRUD" if self.shift(d)[0] != self.cells]

    def apply(self, d):
        nb, gain = self.shift(d)
        self.cells = nb
        self.score += gain
        self.moves += 1
        y, x, v = self.spawn()
        return "+%d spawn %d,%d=%d" % (gain, y, x, v)

    def render(self):
        n = self.r["N"]
        maxv = max(max(row) for row in self.cells)
        width = len(str(maxv))
        head = "score %d moves %d" % (self.score, self.moves)
        if maxv >= self.r["TARGET"]:
            head += " WIN"
        if not self.legal():
            head += " OVER"
        lines = [head]
        for y in range(n):
            lines.append(" ".join(("#" if (y, x) in self.wall else str(self.cells[y][x]) if self.cells[y][x] else ".").rjust(width) for x in range(n)))
        return "\\n".join(lines)


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
                m = Model(int(args), r)
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
                got = f"{m.score} {'true' if not m.legal() else 'false'}"
                assert got == want, f"status disagree {got!r} vs {want!r}"
            elif verb == "render":
                assert m.render() == want, f"render disagree:\n{m.render()}\n{want}"
            cmd = None


# ----------------------------------------------------------------------------------------------------- README

def readme(r: dict) -> str:
    n, m = r["N"], r["MERGE"]
    pre = {2: "pair", 3: "triple"}[m]
    def line(vals, d):
        mm = Model(1, {**r, "WALLS": []})
        mm.cells = [[0] * n for _ in range(n)]
        for i, v in enumerate(vals):
            mm.cells[0][i] = v
        nb, g = mm.shift(d)
        return nb[0], g
    ex_in = ([1, 1, 1, 1, m] if m == 3 else [2, 2, 2, 2, 4])[:max(4, min(n, 5))]
    ex_in = (ex_in + [0] * n)[:n]
    exL, gL = line(ex_in, "L")
    exR, gR = line(ex_in, "R")
    fmt = lambda v: " ".join(str(x) if x else "." for x in v)
    s = []
    s.append(f"# Triptych\n\nA sliding-tile merge game on a {n}x{n} board in the 2048 family, except that tiles merge in {pre}s of {m}. The engine is headless: a `Game`, its legal moves "
             f"and exact text for every reply.\n")
    s.append("## The board\n")
    wl = ""
    if r["WALLS"]:
        wl = " Walls (never entered by tiles, drawn `#`) stand at (row, column): " + ", ".join(f"({a},{b})" for a, b in r["WALLS"]) + "."
    s.append(f"The board has {n} rows and {n} columns, numbered from 0, row 0 at the top.{wl} Every other cell is empty or holds a tile with a positive value; tile values are powers of {m} "
             f"(1, {m}, {m * m}, ...).\n")
    s.append("## Moves\n")
    s.append("A move is one of the strings `L`, `R`, `U`, `D` (slide left, right, up, down; upper case only). A move is *legal* exactly when it changes the board; a move that would change nothing is "
             "illegal (and so is every other string). A legal move does, in this order: slide and merge (below), add the merge points to the score, count the move, spawn one tile.\n")
    s.append("### Sliding and merging\n")
    seg = "every row for `L`/`R` and every column for `U`/`D` is a *line*" + (", and the walls cut each line into *segments* (maximal runs of cells without a wall); segments are processed independently, tiles never cross a wall." if r["WALLS"] else ".")
    s.append(f"Lines move independently: {seg} Take a segment and read its tiles (skipping the empty cells) starting from the end nearest to the side the tiles move towards (the left end for `L`, the right "
             f"end for `R`, the top for `U`, the bottom for `D`). Walk through that list from its start: if the next {m} tiles are all equal to some value `v`, they merge into one tile of value "
             f"`{m}*v` and the walk continues after them; otherwise the tile stays as it is and the walk continues with the next one. The resulting tiles are packed against the same end of the segment, in the same order, "
             f"and the rest of the segment is empty. A tile created by a merge is never merged again in the same move. The score gains the value of every tile created by a merge.\n")
    s.append(f"Example on a line of {n} cells: `{fmt(ex_in)}` moved left becomes `{fmt(exL)}` (score +{gL}); moved right it becomes `{fmt(exR)}` (score +{gR}).\n")
    s.append("### Spawning\n")
    s.append(f"The generator is MINSTD: `state = state * 48271 mod 2147483647`, and `next()` returns the new state. `NewGame(seed)` starts with `state = seed mod 2147483647`, or `1` if that is 0.\n\n"
             f"A spawn first lists the candidate cells in row-major order (row 0 first, left to right): the cells that are empty and not walls" +
             (" — but if at least one of them lies on the border of the board (row 0, row %d, column 0 or column %d), only the candidates on the border are kept." % (n - 1, n - 1) if r["EDGE"] else ".") +
             f" Then `i = (next() >> 8) mod (number of candidates)` picks the i-th candidate (0-based), and a second call decides the value: `1` normally, `{m}` when `(next() >> 8) mod 8 == 0`. "
             f"The position is drawn before the value; nothing else ever calls `next()`. A new game spawns twice (two tiles) before the first move; every legal move spawns once, after the slide.\n")
    ck = []
    st = 1
    for _ in range(4):
        st = st * 48271 % 2147483647
        ck.append(st)
    s.append(f"Check: with seed 1 the first four values of `next()` are {', '.join(map(str, ck))}.\n")
    s.append("## Rules of the game\n")
    s.append(f"The game is *over* when no move is legal. The first line of the board text carries ` WIN` when the largest tile is at least {r['TARGET']} and ` OVER` when the game is over (play simply continues after a win).\n")
    s.append("## API (package `triptych`)\n")
    s.append("```go\n"
             "g := triptych.NewGame(seed uint32)\n"
             "g.LegalMoves() []string          // the legal moves, in any order; empty when the game is over\n"
             "g.Apply(move string) (string, error) // plays a legal move and returns the event; an error, and no change, otherwise\n"
             "g.Render() string                // the board text (below)\n"
             "g.Score() int\n"
             "g.Over() bool\n```\n")
    s.append("### Event returned by `Apply`\n\n`+<points> spawn <row>,<col>=<value>`: the score gained by the move and the tile that spawned, for example `+9 spawn 2,0=1` (rows and columns from 0).\n")
    s.append("### `Render()`\n")
    mm = Model(1, {**r, "TARGET": 10 ** 9})
    mm.cells = [[0] * n for _ in range(n)]
    sample = [(0, 1, m), (0, 3, 1), (1, 0, m ** 4), (1, 2, m ** 2), (2, 2, 1), (3, 0, m)]
    for y, x, v in sample:
        if (y, x) not in mm.wall:
            mm.cells[y][x] = v
    mm.score, mm.moves = 90, 21
    s.append("The first line is `score <score> moves <moves>` followed by ` WIN` and/or ` OVER` when they apply (in that order). Then one line per row, no trailing newline at the end of the text. "
             "Every cell is written as its value (`.` for an empty cell, `#` for a wall), right-aligned to the width `w` = the number of digits of the largest tile on the board (at least 1), and the cells of a row are joined by "
             "a single space. Example (a board whose largest tile is %d):\n\n```\n%s\n```\n" % (m ** 4, mm.render().replace("\\n", "\n")))
    s.append("## Tests\n\n`go test ./...` replays the scenario files in `testdata/` (`adapter_test.go` shows how the API is called; the format is described at the top of `scenarios_test.go`).\n")
    return "\n".join(s)


def project(r: dict) -> dict[str, str]:
    return {"game.go": engine(r), "go.mod": _kit.go_mod(PKG), ".gitignore": ""}


def scripts(rng, r: dict) -> dict[str, str]:
    games = "\n".join(f"# scenario game {s}\n> new {s}\n~ rand 900 {s * 17 + 3} every=8 emit=render,legal,status junk=X|l|LL|0|u|down" for s in (1, 2, 3, 77, 4242, 4294967295, 2147483647, 2147483646))
    edge = dd('''
        # scenario seeds
        > new 0
        > render
        > new 1
        > render
        > new 2147483647
        > render
        > new 2147483648
        > render
        > new 4294967295
        > render
        # scenario illegal
        > new 5
        > legal
        > do X
        > do l
        > do LL
        > do
        > render
        > status
        # scenario games are independent
        > new 9
        ~ rand 30 4 every=30 emit=render
        > new 9
        ~ rand 30 4 every=30 emit=render
    ''')
    return {"hidden_games": games + "\n", "hidden_edge": edge}


def example_script() -> str:
    return dd('''
        # scenario opening
        > new 1
        > render
        > legal
        > do L
        > render
        # scenario a few moves
        > new 12
        ~ rand 12 3 emit=render,legal,status
    ''')


def _variants(n: int) -> list[dict]:
    plan = [
        dict(),
        dict(MERGE=2, TARGET=64),
        dict(N=5, WALLS=[[2, 2]], TARGET=81),
        dict(MERGE=2, EDGE=True, TARGET=32),
        dict(N=5, MERGE=2, WALLS=[[1, 3], [3, 1]], EDGE=True, TARGET=64),
        dict(N=4, WALLS=[[0, 2], [2, 1]], EDGE=True, TARGET=27),
        dict(N=5, MERGE=3, WALLS=[[0, 0], [2, 2], [4, 4]], TARGET=81),
    ]
    return [{**DEFAULT, **o} for o in plan[:n]]


@family("games-triptych-build", category="games", lang="go", kind="greenfield", n=7,
        summary="build the Triptych merge-in-threes sliding game with walls, edge spawning and an exact MINSTD generator")
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
        d = 2 + (r["MERGE"] == 3) + bool(r["WALLS"]) + r["EDGE"]
        d = min(5, max(2, d))
        blurb = f"a {r['N']}x{r['N']} sliding-tile game where tiles merge in {'threes' if r['MERGE'] == 3 else 'pairs'}" + (", with walls on the board" if r["WALLS"] else "")
        prompt = _kit.green_prompt(rng, game=GAME, blurb=blurb, file="game.go", verify=_scen.VERIFY[LANG], used=used)
        slug = f"{i + 1:02d}-n{r['N']}m{r['MERGE']}" + ("-walls" if r["WALLS"] else "") + ("-edge" if r["EDGE"] else "")
        yield Task(slug=slug, prompt=prompt, difficulty=d, start=start, hidden=hidden, solution={"game.go": sol["game.go"]}, verify=_scen.VERIFY[LANG],
                   tags=["tiles", "rng", "scenarios"], notes={"rules": r})


BUGS = [
    Bug("last-triple", "The last group of a line never merges",
        "A line that ends in a full group of equal tiles does not merge that last group: with merges of three, `1 1 1` slid left stays `1 1 1`, while `1 1 1 1` merges the first three. Merges only seem to happen when there is a spare tile after the group.",
        [("if t+Merge <= len(tiles) && allEqual(tiles[t:t+Merge]) {", "if t+Merge < len(tiles) && allEqual(tiles[t:t+Merge]) {")], difficulty=2),
    Bug("score-base", "Score counts the wrong value",
        "The score after a merge is too low: it goes up by the value of the tiles that merged, not by the value of the tile that the merge produces.",
        [("gain += tiles[t] * Merge", "gain += tiles[t]")], difficulty=1),
    Bug("spawn-rate", "Big tiles spawn far too often",
        "Way too many of the bigger spawn tiles appear: roughly one in four new tiles instead of one in eight.",
        [("if (g.next()>>8)%8 == 0 {", "if (g.next()>>8)%4 == 0 {")], difficulty=2),
    Bug("spawn-order", "Spawns use the random numbers in the wrong order",
        "New tiles end up in different places than the README's reference runs say for the same seed, although the values look right. The two random draws of a spawn seem to be used in the other order.",
        [("p := pool[(g.next()>>8)%uint64(len(pool))]\n    v := 1\n    if (g.next()>>8)%8 == 0 {\n        v = Merge\n    }",
          "r2 := g.next() >> 8\n    v := 1\n    if r2%8 == 0 {\n        v = Merge\n    }\n    p := pool[(g.next()>>8)%uint64(len(pool))]")], difficulty=3),
    Bug("noop-move", "Moves that change nothing are accepted",
        "Pressing a direction in which nothing can move still counts as a move and spawns a new tile. It should be refused like any other illegal move.",
        [("if nb, _ := g.shift(d); nb != g.cells {", "if _, _ = g.shift(d); true {")], difficulty=2),
    Bug("down-as-up", "Down moves the tiles up",
        "Pressing down slides the tiles to the top of the board, exactly like pressing up. Left and right are fine.",
        [("default:\n            out[k] = [2]int{N - 1 - k, i}", "default:\n            out[k] = [2]int{k, i}")], difficulty=1),
    Bug("walls-ignored", "Tiles slide through walls",
        "On boards with walls, tiles slide right over the wall cells and merge with tiles on the other side of a wall (and sometimes a tile seems to vanish into a wall). Each side of a wall should behave like a separate line.",
        [("for j < N && !g.wall[coords[j][0]][coords[j][1]] {", "for j < N {")], difficulty=3, rules=dict(N=5, WALLS=[[2, 2]])),
    Bug("seed-zero", "Seed 0 produces a stuck game",
        "Games started with seed 0 (and the seed 2147483647) are broken: the same cell fills up every time and the random sequence never changes.",
        [("if g.state == 0 {\n        g.state = 1\n    }\n    g.spawn()\n    g.spawn()", "g.spawn()\n    g.spawn()")], difficulty=3),
    Bug("edge-spawn", "Edge spawning is not restricted to the border",
        "On the table with edge spawning tiles still appear in the middle of the board even though border cells are free.",
        [("if SpawnEdge && len(edge) > 0 {", "if SpawnEdge && len(edge) > 4 {")], difficulty=3, rules=dict(EDGE=True, MERGE=2, TARGET=32)),
    Bug("width-per-row", "The board text is aligned per row",
        "When the board holds a wide number the columns don't line up: only the row that contains the big tile gets wide cells, the other rows stay narrow.",
        [("width := len(strconv.Itoa(maxv))", "width := 1"),
         ("lines := []string{head}\n    for r := 0; r < N; r++ {\n        cells := make([]string, N)",
          "lines := []string{head}\n    for r := 0; r < N; r++ {\n        width = 1\n        for c := 0; c < N; c++ {\n            if l := len(strconv.Itoa(g.cells[r][c])); l > width {\n                width = l\n            }\n        }\n        cells := make([]string, N)")],
        difficulty=3, rules=dict(MERGE=2, TARGET=64)),
    Bug("over-early", "Game over is declared one move too early",
        "When only a single direction is still possible the board already says OVER, although that move works and the game could go on.",
        [("func (g *Game) Over() bool { return len(g.LegalMoves()) == 0 }", "func (g *Game) Over() bool { return len(g.LegalMoves()) <= 1 }")], difficulty=2),
    Bug("column-major", "Spawn candidates are listed column by column",
        "With the same seed the new tiles land in different cells than expected; the cell picked by the random number looks transposed.",
        [("for r := 0; r < N; r++ {\n        for c := 0; c < N; c++ {\n            if g.wall[r][c] || g.cells[r][c] != 0 {", "for c := 0; c < N; c++ {\n        for r := 0; r < N; r++ {\n            if g.wall[r][c] || g.cells[r][c] != 0 {")],
        difficulty=3),
    Bug("no-merge-score-reset", "Moves are counted twice",
        "The move counter in the status line runs twice as fast as the number of moves played: after 5 moves it says 10.",
        [("g.moves++\n    r, c, v := g.spawn()", "g.moves += 2\n    r, c, v := g.spawn()")], difficulty=1),
]


def _fix_edits(b: Bug) -> Bug:
    return Bug(b.id, b.title, b.symptom, [(tabs(o), tabs(n)) for o, n in b.edits], b.path, b.difficulty, b.rules, b.detail)


BUGS = [_fix_edits(b) for b in BUGS]
_B = {b.id: b for b in BUGS}
BUGS_ALL = BUGS + [
    _kit.combine(_B["score-base"], _B["over-early"], difficulty=3),
    _kit.combine(_B["last-triple"], _B["spawn-rate"], _B["noop-move"], difficulty=4),
    _kit.combine(_B["walls-ignored"], _B["down-as-up"], difficulty=4),
]


@family("games-triptych-fix", category="games", lang="go", kind="fix", n=15,
        summary="hand-injected defects in the Triptych engine (merging, justification, walls, spawn order, seeds, render)")
def gen_fix(rng, n):
    used: list[str] = []
    cache = {}
    for k, bug in enumerate(BUGS_ALL[:n]):
        r = {**DEFAULT, **bug.rules}
        key = json.dumps(r, sort_keys=True)
        if key not in cache:
            sol = project(r)
            hidden = _kit.data_files(LANG, scripts(rng, r), sol, ADAPTER, PKG)
            vis = _kit.data_files(LANG, {"examples": example_script()}, sol, ADAPTER, PKG)
            cache[key] = (sol, hidden, vis, readme(r))
        sol, hidden, vis, rd = cache[key]
        base = {**sol, "README.md": rd}
        tests = {**_scen.check_files(LANG, ADAPTER, PKG), **vis}
        ctx = {"files": ["game.go"], "verify": _scen.VERIFY[LANG]}
        yield _kit.bug_task(game=GAME, lang=LANG, base_files=base, tests=tests, hidden=hidden, bug=bug, ctx=ctx, rng=rng, used=used, k=k,
                            tags=["tiles", "rng"], extra_notes={"rules": r})
