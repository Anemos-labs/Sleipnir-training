"""Slidebox (javascript): a crate-pushing puzzle with ice sliding, water bridges and multi-pushes. Build, fix, level loader
and solver-tournament tasks. A python model of the rules cross-checks the reference engine and finds solvable levels."""
from __future__ import annotations

import json
import textwrap
from collections import deque

from fx import Task, dd, family

from . import _kit, _scen
from ._kit import Bug

LANG = "javascript"
GAME = "Slidebox"
DEFAULT = dict(SLIDE=False, MAX_PUSH=1, WATER=True, PUSH_COST=1, EXACT=False)


def js(v) -> str:
    return "true" if v is True else "false" if v is False else str(v)


def header(r: dict) -> str:
    return dd(f'''
        // ---- house rules for this crate yard (they are part of the specification, see README.md) ----
        const SLIDE = {js(r["SLIDE"])};
        const MAX_PUSH = {r["MAX_PUSH"]};
        const WATER = {js(r["WATER"])};
        const PUSH_COST = {r["PUSH_COST"]};
        const EXACT = {js(r["EXACT"])};
        // -----------------------------------------------------------------------------------------------
    ''')


BODY = dd(r'''
    const DIRS = { U: [-1, 0], D: [1, 0], L: [0, -1], R: [0, 1] };

    class Game {
      constructor(levelText) {
        const rows = levelText.split('\n');
        this.h = rows.length;
        this.w = rows[0].length;
        this.terrain = [];
        this.crates = new Set();
        this.player = [0, 0];
        this.moveCount = 0;
        for (let r = 0; r < this.h; r++) {
          const line = [];
          for (let c = 0; c < this.w; c++) {
            const ch = rows[r][c];
            if (ch === '@' || ch === '+') this.player = [r, c];
            if (ch === 'B' || ch === '*') this.crates.add(r * this.w + c);
            line.push(ch === '#' ? '#' : ch === '~' ? '~' : ch === '_' || ch === '+' || ch === '*' ? '_' : '.');
          }
          this.terrain.push(line);
        }
        this.padTotal = this.terrain.flat().filter((t) => t === '_').length;
      }

      _at(r, c) {
        return r < 0 || c < 0 || r >= this.h || c >= this.w ? null : this.terrain[r][c];
      }

      _key(r, c) {
        return r * this.w + c;
      }

      _covered() {
        let n = 0;
        for (const k of this.crates) {
          if (this.terrain[Math.floor(k / this.w)][k % this.w] === '_') n++;
        }
        return n;
      }

      solved() {
        const covered = this._covered();
        return covered === this.padTotal && (!EXACT || this.crates.size === this.padTotal);
      }

      moves() {
        return this.moveCount;
      }

      _plan(move) {
        const d = DIRS[move];
        const tr = this.player[0] + d[0];
        const tc = this.player[1] + d[1];
        const t = this._at(tr, tc);
        if (t === null || t === '#' || t === '~') return null;
        if (!this.crates.has(this._key(tr, tc))) return { kind: 'walk' };
        let run = 0;
        let r = tr;
        let c = tc;
        while (this.crates.has(this._key(r, c))) {
          run++;
          r += d[0];
          c += d[1];
        }
        if (run > MAX_PUSH) return null;
        const f = this._at(r, c);
        if (f === null || f === '#') return null;
        return { kind: 'push', front: [r, c] };
      }

      legalMoves() {
        if (this.solved()) return [];
        return Object.keys(DIRS).filter((m) => this._plan(m) !== null);
      }

      apply(move) {
        if (typeof move !== 'string' || !this.legalMoves().includes(move)) throw new Error('illegal move: ' + move);
        const plan = this._plan(move);
        const d = DIRS[move];
        const tr = this.player[0] + d[0];
        const tc = this.player[1] + d[1];
        let event = 'walk';
        let cost = 1;
        if (plan.kind === 'push') {
          cost = PUSH_COST;
          this.crates.delete(this._key(tr, tc));
          let [r, c] = plan.front;
          let n = 1;
          let sank = this.terrain[r][c] === '~';
          if (!sank && SLIDE) {
            for (;;) {
              const nr = r + d[0];
              const nc = c + d[1];
              const t = this._at(nr, nc);
              if (t === null || t === '#' || this.crates.has(this._key(nr, nc))) break;
              r = nr;
              c = nc;
              n++;
              if (t === '~') {
                sank = true;
                break;
              }
            }
          }
          if (sank) this.terrain[r][c] = '.';
          else this.crates.add(this._key(r, c));
          event = SLIDE ? 'slide ' + n : 'push';
          if (sank) event += ' sink';
        }
        this.player = [tr, tc];
        this.moveCount += cost;
        if (this.solved()) event += ' solved';
        return event;
      }

      render() {
        const lines = [];
        for (let r = 0; r < this.h; r++) {
          let s = '';
          for (let c = 0; c < this.w; c++) {
            const t = this.terrain[r][c];
            const crate = this.crates.has(this._key(r, c));
            const me = this.player[0] === r && this.player[1] === c;
            if (t === '#' || t === '~') s += t;
            else if (crate) s += t === '_' ? '*' : 'B';
            else if (me) s += t === '_' ? '+' : '@';
            else s += t;
          }
          lines.push(s);
        }
        lines.push('moves=' + this.moveCount + ' pads=' + this._covered() + '/' + this.padTotal + (this.solved() ? ' SOLVED' : ''));
        return lines.join('\n');
      }
    }

    module.exports = { Game };
''')

CLONE_KEY = dd(r'''

      clone() {
        const g = Object.create(Game.prototype);
        g.h = this.h;
        g.w = this.w;
        g.terrain = this.terrain.map((row) => row.slice());
        g.crates = new Set(this.crates);
        g.player = this.player.slice();
        g.moveCount = this.moveCount;
        g.padTotal = this.padTotal;
        return g;
      }

      key() {
        return this.player.join(',') + '|' + [...this.crates].sort((a, b) => a - b).join(',') + '|' + this.terrain.map((row) => row.join('')).join('/');
      }
''')


def engine(r: dict, extra: bool = False) -> str:
    body = BODY
    if extra:
        marker = "  render() {\n"
        assert body.count(marker) == 1
        body = body.replace(marker, textwrap.indent(CLONE_KEY.strip("\n"), "  ") + "\n\n" + marker, 1)
    return "'use strict';\n\n" + header(r) + "\n" + body


STUB = dd(r'''
    'use strict';

    class Game {
      constructor(levelText) {
        throw new Error('not implemented');
      }

      legalMoves() {
        throw new Error('not implemented');
      }

      apply(move) {
        throw new Error('not implemented');
      }

      render() {
        throw new Error('not implemented');
      }

      moves() {
        throw new Error('not implemented');
      }

      solved() {
        throw new Error('not implemented');
      }
    }

    module.exports = { Game };
''')

ADAPTER = {"test/adapter.js": dd(r'''
    // Maps scenario commands onto the engine API (the scenario runner is test/scenarios.test.js).
    'use strict';
    const { Game } = require('../src/slidebox');

    class Adapter {
      constructor() {
        this.game = null;
      }

      run(verb, args) {
        switch (verb) {
          case 'new': // new <level rows joined by |>
            this.game = new Game(args.split('|').join('\n'));
            return 'ok';
          case 'do': // do <move>: the event text, or "illegal"
            try {
              return this.game.apply(args);
            } catch (e) {
              return 'illegal';
            }
          case 'legal': { // sorted legal moves joined by "," ("-" when there are none)
            const moves = this.game.legalMoves().slice().sort();
            return moves.length ? moves.join(',') : '-';
          }
          case 'render':
            return this.game.render();
          case 'status': // "<moves> <solved>"
            return this.game.moves() + ' ' + this.game.solved();
          default:
            throw new Error('unknown verb ' + verb);
        }
      }
    }

    module.exports = { Adapter };
''')}


# ----------------------------------------------------------------------------------------------------- python model

class Model:
    """Independent re-implementation of the rules, used to find solvable levels and to cross-check the reference."""

    def __init__(self, level: str, r: dict):
        self.r = r
        rows = level.split("\n")
        self.h, self.w = len(rows), len(rows[0])
        self.terrain = {}
        self.crates = set()
        self.player = None
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch in "@+":
                    self.player = (y, x)
                if ch in "B*":
                    self.crates.add((y, x))
                self.terrain[(y, x)] = "#" if ch == "#" else "~" if ch == "~" else "_" if ch in "_+*" else "."
        self.pads = sum(1 for t in self.terrain.values() if t == "_")
        self.moves = 0

    def clone(self):
        m = Model.__new__(Model)
        m.r, m.h, m.w = self.r, self.h, self.w
        m.terrain, m.crates, m.player, m.pads, m.moves = dict(self.terrain), set(self.crates), self.player, self.pads, self.moves
        return m

    def solved(self):
        cov = sum(1 for c in self.crates if self.terrain[c] == "_")
        return cov == self.pads and (not self.r["EXACT"] or len(self.crates) == self.pads)

    D = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}

    def plan(self, mv):
        dy, dx = self.D[mv]
        t = (self.player[0] + dy, self.player[1] + dx)
        tt = self.terrain.get(t)
        if tt in (None, "#", "~"):
            return None
        if t not in self.crates:
            return ("walk", None)
        run, p = 0, t
        while p in self.crates:
            run += 1
            p = (p[0] + dy, p[1] + dx)
        if run > self.r["MAX_PUSH"]:
            return None
        if self.terrain.get(p) in (None, "#"):
            return None
        return ("push", p)

    def legal(self):
        if self.solved():
            return []
        return [m for m in "UDLR" if self.plan(m)]

    def apply(self, mv):
        pl = self.plan(mv)
        dy, dx = self.D[mv]
        t = (self.player[0] + dy, self.player[1] + dx)
        ev, cost = "walk", 1
        if pl[0] == "push":
            cost = self.r["PUSH_COST"]
            self.crates.discard(t)
            p, n = pl[1], 1
            sank = self.terrain[p] == "~"
            if not sank and self.r["SLIDE"]:
                while True:
                    q = (p[0] + dy, p[1] + dx)
                    tq = self.terrain.get(q)
                    if tq in (None, "#") or q in self.crates:
                        break
                    p, n = q, n + 1
                    if tq == "~":
                        sank = True
                        break
            if sank:
                self.terrain[p] = "."
            else:
                self.crates.add(p)
            ev = ("slide %d" % n) if self.r["SLIDE"] else "push"
            if sank:
                ev += " sink"
        self.player = t
        self.moves += cost
        if self.solved():
            ev += " solved"
        return ev

    def key(self):
        return (self.player, tuple(sorted(self.crates)), tuple(sorted(p for p, t in self.terrain.items() if t == "~")))


def solve(level: str, r: dict, cap: int = 60000):
    """Shortest move string, or None (unsolvable or beyond ``cap`` states)."""
    start = Model(level, r)
    if start.solved():
        return ""
    seen = {start.key()}
    q = deque([(start, "")])
    while q and len(seen) < cap:
        m, path = q.popleft()
        for mv in m.legal():
            n = m.clone()
            n.apply(mv)
            k = n.key()
            if k in seen:
                continue
            if n.solved():
                return path + mv
            seen.add(k)
            q.append((n, path + mv))
    return None


def random_level(rng, r: dict, w: int, h: int, crates: int, extra: int = 0, water: int = 0, wall_pct: int = 14) -> str:
    g = [["#"] * w for _ in range(h)]
    cells = [(y, x) for y in range(1, h - 1) for x in range(1, w - 1)]
    for y, x in cells:
        g[y][x] = "#" if rng.randrange(100) < wall_pct else "."
    free = [c for c in cells if g[c[0]][c[1]] == "."]
    rng.shuffle(free)
    need = 1 + crates + extra + crates + water
    if len(free) < need:
        return ""
    py, px = free.pop()
    for _ in range(crates):
        y, x = free.pop()
        g[y][x] = "_"
    for _ in range(crates + extra):
        y, x = free.pop()
        g[y][x] = "B"
    for _ in range(water):
        y, x = free.pop()
        g[y][x] = "~"
    g[py][px] = "@"
    out = ["".join(row) for row in g]
    # a crate that starts on a pad would be fine, but keep levels honest: player and crates never share a cell (by construction)
    return "\n".join(out)


def make_levels(rng, r: dict, count: int, sizes, tries: int = 4000) -> list[tuple[str, str]]:
    """[(level, shortest solution)] of solvable levels with a solution of at least 6 moves."""
    out = []
    t = 0
    while len(out) < count and t < tries:
        t += 1
        w, h = sizes[rng.randrange(len(sizes))]
        crates = rng.choice([1, 2, 2, 3])
        extra = 1 if (r["EXACT"] and r["WATER"]) else 0
        water = rng.choice([1, 2, 3]) if r["WATER"] else 0
        if r["EXACT"] and not r["WATER"]:
            extra = 0
        lv = random_level(rng, r, w, h, crates, extra, water)
        if not lv:
            continue
        sol = solve(lv, r, cap=40000)
        if sol and len(sol) >= 6:
            out.append((lv, sol))
    if len(out) < count:
        raise RuntimeError(f"slidebox: only {len(out)} solvable levels for {r}")
    return out


def crosscheck(text: str, r: dict) -> None:
    """Replay a recorded scenario file on the python model: events, legal moves and renders must agree."""
    model = None
    cmd = None
    for line in text.split("\n"):
        if line.startswith("> "):
            cmd = line[2:]
        elif line.startswith("= ") and cmd is not None:
            want = line[2:]
            verb, _, args = cmd.partition(" ")
            if verb == "new":
                model = Model(args.replace("|", "\n"), r)
            elif verb == "do":
                if args in model.legal():
                    got = model.apply(args)
                    assert got == want, f"model/engine disagree on {cmd}: {got!r} vs {want!r}"
                else:
                    assert want == "illegal", f"model says illegal for {cmd}, engine says {want!r}"
            elif verb == "legal":
                got = ",".join(sorted(model.legal())) or "-"
                assert got == want, f"legal disagree: {got!r} vs {want!r}"
            elif verb == "status":
                got = f"{model.moves} {'true' if model.solved() else 'false'}"
                assert got == want, f"status disagree: {got!r} vs {want!r}"
            elif verb == "render":
                rows = []
                for y in range(model.h):
                    s = ""
                    for x in range(model.w):
                        t, c, me = model.terrain[(y, x)], (y, x) in model.crates, model.player == (y, x)
                        s += t if t in "#~" else ("*" if t == "_" else "B") if c else ("+" if t == "_" else "@") if me else t
                    rows.append(s)
                cov = sum(1 for c in model.crates if model.terrain[c] == "_")
                rows.append(f"moves={model.moves} pads={cov}/{model.pads}" + (" SOLVED" if model.solved() else ""))
                got = "\\n".join(rows)
                assert got == want, f"render disagree:\n{got}\n{want}"
            cmd = None


# ----------------------------------------------------------------------------------------------------- README

def readme(r: dict, example: tuple[str, str, str] | None = None) -> str:
    s = []
    s.append("# Slidebox\n\nA crate yard seen from above. You are the `@`; push crates onto the pads (`_`). The engine is headless: a `Game` built from a level text, "
             "a list of legal moves and exact text for every reply.\n")
    chars = ["| char | meaning |", "|---|---|", "| `#` | wall |", "| `.` | floor |", "| `_` | pad (a target cell) |", "| `@` / `+` | the player on floor / on a pad |",
             "| `B` / `*` | a crate on floor / on a pad |"]
    if r["WATER"]:
        chars.append("| `~` | water: the player can never enter it; a crate that enters it sinks and *fills* it |")
    s.append("## Levels\n\nA level is a list of rows of equal length joined by `\\n` (the engine receives a string without a trailing newline):\n\n" + "\n".join(chars) +
             "\n\nA level has exactly one player and at least one pad. Cells outside the grid count as walls. Row 0 is the top row; `U` moves to row-1, `D` to row+1, `L` to column-1 and `R` to column+1.\n")
    s.append("## Moves\n\nA move is one of the strings `U`, `D`, `L`, `R` (upper case, nothing else is accepted). Let `t` be the cell next to the player in the move's direction.\n")
    rules = []
    rules.append("1. If `t` is a wall or outside the grid" + (" or water" if r["WATER"] else "") + ", the move is illegal.")
    rules.append("2. If `t` holds no crate, the player walks onto `t`. Event `walk`.")
    mp = r["MAX_PUSH"]
    if mp == 1:
        push = "3. If `t` holds a crate the player *pushes* it: the crate moves one cell further in the same direction, which must be free of walls and other crates (and inside the grid), otherwise the move is illegal."
    else:
        push = (f"3. If `t` holds a crate the player *pushes*. Let the *run* be the crates standing in an unbroken line from `t` in the move's direction. If the run has more than {mp} crate"
                f"{'s' if mp > 1 else ''}, the move is illegal. Otherwise let `f` be the cell right after the run: if `f` is a wall or outside the grid the move is illegal; if not, every crate of the run "
                f"moves one cell (in effect the first crate of the run leaves its cell and a crate appears on `f`).")
    if r["WATER"]:
        push += " A crate that is pushed onto a water cell is gone: the water cell becomes plain floor (`.`)" + (" and the crate leaves the level (it sinks)." if r["SLIDE"] else " (the crate that reaches the water sinks; the others in the run just move one cell)." if r["MAX_PUSH"] > 1 else " (the crate sinks).")
    rules.append(push)
    if r["SLIDE"]:
        rules.append("4. *Ice*: a pushed crate does not stop after one cell. It keeps sliding in the same direction while the next cell is free: not a wall, not outside the grid, not another crate"
                     + (" (water is free: sliding into water sinks the crate and the slide ends there)." if r["WATER"] else ".") +
                     " The player ends on `t`. The event is `slide <n>` where `n >= 1` is the number of cells the crate travelled" + (" (the cell of the sinking counts)." if r["WATER"] else "."))
        rules.append("5. A pushed crate that does not sink is placed on the cell where it stopped.")
    else:
        rules.append("4. After a push the player stands on `t`. Event `push`.")
    rules.append(f"{len(rules) + 1}. Cost: a walk adds 1 to the move counter, a {'slide' if r['SLIDE'] else 'push'} adds {r['PUSH_COST']}. Illegal moves change nothing and cost nothing.")
    if r["WATER"]:
        rules.append(f"{len(rules) + 1}. When a crate sank, the event gets the suffix ` sink` (`push sink`" + (", `slide 3 sink`" if r["SLIDE"] else "") + ").")
    rules.append(f"{len(rules) + 1}. The level is *solved* when every pad holds a crate" + (" and there is no crate off the pads (a crate that is not on a pad prevents the solution; surplus crates must sink)" if r["EXACT"] else " (extra crates elsewhere do not matter)") +
                 ". The event of a move that solves the level gets the suffix ` solved`. In a solved level there are no legal moves.")
    s.append("\n".join(rules) + "\n")
    s.append("## API (`src/slidebox.js`, CommonJS)\n")
    s.append("```js\nconst { Game } = require('./src/slidebox');\n"
             "const g = new Game(levelText);   // rows joined by \"\\n\"\n"
             "g.legalMoves()    // array of the legal move strings (any order); [] when solved\n"
             "g.apply('R')      // plays a legal move and returns the event text; throws an Error otherwise (state unchanged)\n"
             "g.render()        // the board text (below)\n"
             "g.moves()         // the move counter\n"
             "g.solved()        // boolean\n```\n")
    s.append("### `render()`\n\nThe rows of the level as they are now, using the characters of the table above (a crate on a pad is `*`, the player on a pad `+`; a filled water cell is `.`), followed by one "
             "status line, joined by `\\n` with no trailing newline: `moves=<counter> pads=<pads holding a crate>/<pads in the level>`, with ` SOLVED` appended when the level is solved. For example:\n")
    if example:
        lv, mv, out = example
        s.append(f"```\nlevel   {lv.replace(chr(10), '|')}\nmoves   {mv}\n```\n\n```\n{out}\n```\n")
    s.append("## Tests\n\n`node --test test/*.test.js` replays the scenario files in `test/data/` (`test/adapter.js` shows how the API is called; the format is described at the top of "
             "`test/scenarios.test.js`).\n")
    return "\n".join(s)


# ----------------------------------------------------------------------------------------------------- scenarios

def level_scripts(rng, r: dict, n_solved: int = 3, n_random: int = 4) -> dict[str, str]:
    solved = make_levels(rng, r, n_solved, [(6, 5), (7, 5), (7, 6)])
    parts = []
    for i, (lv, sol) in enumerate(solved):
        row = lv.replace("\n", "|")
        moves = "\n".join(f"> do {m}" for m in sol)
        parts.append(f"# scenario solve level {i + 1}\n> new {row}\n> render\n{moves}\n> render\n> legal\n> status\n> do U\n> do R")
        # a detour first: bump into things, then solve from the start again
        parts.append(f"# scenario junk then solve {i + 1}\n> new {row}\n> do X\n> do u\n> do UD\n{moves}\n> status")
    rnd = []
    pool = [lv for lv, _ in solved]
    for i in range(n_random):
        w, h = [(6, 5), (7, 6), (8, 6), (6, 6)][i % 4]
        lv = ""
        while not lv:
            lv = random_level(rng, r, w, h, rng.choice([1, 2, 3]), 1 if r["EXACT"] else 0, rng.choice([1, 2, 3]) if r["WATER"] else 0)
        pool.append(lv)
        row = lv.replace("\n", "|")
        rnd.append(f"# scenario random walk {i + 1}\n> new {row}\n~ rand 260 {rng.randrange(1, 900)} every=7 emit=render,legal,status junk=X|u|UU|0")
    for i, lv in enumerate(pool[:3]):
        row = lv.replace("\n", "|")
        rnd.append(f"# scenario walk the solved levels {i + 1}\n> new {row}\n~ rand 400 {rng.randrange(1, 900)} every=11 emit=render,status")
    hand = []
    for i, lv in enumerate(HAND_LEVELS):
        if not r["WATER"]:
            lv = lv.replace("~", ".")
        row = lv.replace("\n", "|")
        hand.append(f"# scenario hand level {i + 1}\n> new {row}\n> legal\n> render\n~ rand 120 {rng.randrange(1, 900)} every=4 emit=render,legal,status\n"
                    f"> new {row}\n~ rand 160 {rng.randrange(1, 900)} every=5 emit=render,legal junk=X|u|UU")
    return {"hidden_solutions": "\n".join(parts) + "\n", "hidden_walks": "\n".join(rnd) + "\n", "hidden_hand": "\n".join(hand) + "\n"}


HAND_LEVELS = [
    "#########\n#@BBB__.#\n#########",
    "#########\n#_@BB~._#\n#########",
    "#########\n#..B..B.#\n#@..B...#\n#.._.._.#\n#########",
    "#####\n#_.._#\n#B..B#\n#.@.~#\n#B.._#\n#####",
    "########\n#@B.B.~#\n#.B_B._#\n#..B..##\n########",
]


def example_scripts() -> str:
    return dd('''
        # scenario a push
        > new #####|#@B_#|#####
        > render
        > legal
        > do R
        > render
        > legal
        # scenario bumping
        > new #####|#@B_#|#####
        > do L
        > do U
        > do X
        > status
    ''')


def _variants(rng, n: int) -> list[dict]:
    plan = [
        dict(),
        dict(SLIDE=True),
        dict(MAX_PUSH=2, WATER=False),
        dict(SLIDE=True, WATER=False, PUSH_COST=2),
        dict(MAX_PUSH=3, PUSH_COST=2),
        dict(EXACT=True),
        dict(SLIDE=True, EXACT=True, PUSH_COST=2),
        dict(MAX_PUSH=2, EXACT=True, PUSH_COST=3),
    ]
    out = []
    for o in plan[:n]:
        out.append({**DEFAULT, **o})
    return out


def _difficulty(r: dict) -> int:
    return min(5, 2 + (r["SLIDE"]) + (r["MAX_PUSH"] > 1) + (r["EXACT"] and r["WATER"]) + (r["PUSH_COST"] > 1 and r["WATER"] and r["SLIDE"]))


def project(r: dict, extra: bool = False) -> dict[str, str]:
    return {"src/slidebox.js": engine(r, extra), ".gitignore": _kit.GITIGNORE[LANG]}


def _readme_example(r: dict, sol: dict[str, str]) -> tuple[str, str, str]:
    lv = "#######\n#@B~_.#\n#######" if r["WATER"] else "#######\n#@B_..#\n#######"
    script = f"# scenario ex\n> new {lv.replace(chr(10), '|')}\n> do R\n> do R\n> render\n"
    text = _scen.record(LANG, sol, ADAPTER, script)
    got = [ln[2:] for ln in text.split("\n") if ln.startswith("= ")]
    return lv, f"R (event `{got[1]}`), R (event `{got[2]}`)", got[3].replace("\\n", "\n")


@family("games-slidebox-build", category="games", lang="javascript", kind="greenfield", n=8,
        summary="build the Slidebox crate-pushing engine: ice sliding, water bridges, multi-pushes, move costs (rule variants)")
def gen_build(rng, n):
    used: list[str] = []
    for i, r in enumerate(_variants(rng, n)):
        sol = project(r)
        scripts = level_scripts(rng, r)
        hidden = _kit.data_files(LANG, scripts, sol, ADAPTER)
        for text in hidden.values():
            crosscheck(text, r)
        vis = _kit.data_files(LANG, {"examples": example_scripts()}, sol, ADAPTER)
        crosscheck(next(iter(vis.values())), r)
        start = {"README.md": readme(r, _readme_example(r, sol)), "src/slidebox.js": STUB, ".gitignore": _kit.GITIGNORE[LANG], **_scen.check_files(LANG, ADAPTER), **vis}
        feats = [k for k, v in (("slide", r["SLIDE"]), ("push%d" % r["MAX_PUSH"], r["MAX_PUSH"] > 1), ("water", r["WATER"]), ("exact", r["EXACT"]), ("cost%d" % r["PUSH_COST"], r["PUSH_COST"] > 1)) if v]
        blurb = "a crate-pushing puzzle" + (" on ice" if r["SLIDE"] else "") + (" with water to bridge" if r["WATER"] else "")
        prompt = _kit.green_prompt(rng, game=GAME, blurb=blurb, file="src/slidebox.js", verify=_scen.VERIFY[LANG], used=used)
        yield Task(slug=f"{i + 1:02d}-" + "-".join(feats or ["plain"]), prompt=prompt, difficulty=_difficulty(r), start=start, hidden=hidden,
                   solution={"src/slidebox.js": sol["src/slidebox.js"]}, verify=_scen.VERIFY[LANG], tags=["puzzle", "grid", "scenarios"], notes={"rules": r})


BUGS = [
    Bug("push-into-wall", "Crates can be pushed through walls",
        "I can push a crate straight into a wall: the crate vanishes into the wall tile and the level becomes unsolvable. Pushes should simply be refused when the crate's way is blocked.",
        [("if (f === null || f === '#') return null;", "if (f === null) return null;")], difficulty=1),
    Bug("player-into-water", "The player can walk into water",
        "The player can step onto a water tile and keeps walking over it as if it were floor; only crates are supposed to be able to enter water.",
        [("if (t === null || t === '#' || t === '~') return null;", "if (t === null || t === '#') return null;")], difficulty=1, rules=dict(WATER=True)),
    Bug("move-cost", "Pushes are counted as ordinary steps",
        "The move counter in the status line is wrong after pushes: a push is supposed to cost more than a plain step in this yard but the counter treats them the same.",
        [("cost = PUSH_COST;", "cost = 1;")], difficulty=2, rules=dict(PUSH_COST=2)),
    Bug("push-limit", "Longer rows of crates can be pushed than allowed",
        "I managed to push a row of crates that is longer than the yard's limit. The check on how many crates may be pushed at once lets one crate too many through.",
        [("if (run > MAX_PUSH) return null;", "if (run > MAX_PUSH + 1) return null;")], difficulty=2, rules=dict(MAX_PUSH=2, WATER=False)),
    Bug("water-not-filled", "Water that swallowed a crate is still water",
        "After a crate sinks the water tile is still there: the crate is gone but nobody can ever walk over that tile, so levels that need the bridge can't be finished.",
        [("if (sank) this.terrain[r][c] = '.';", "if (sank) this.terrain[r][c] = '~';")], difficulty=2),
    Bug("slide-stops-early", "Crates on ice stop one cell too soon",
        "On the ice yard a crate that is pushed seems to stop one cell before the obstacle in some cases, and never slides at all when the free run is just two cells. The `slide N` counts are lower than they should be.",
        [("if (t === null || t === '#' || this.crates.has(this._key(nr, nc))) break;", "if (t === null || t === '#' || this.crates.has(this._key(nr, nc)) || this._at(nr + d[0], nc + d[1]) === '#') break;")],
        difficulty=3, rules=dict(SLIDE=True, WATER=False)),
    Bug("slide-through-crate", "Sliding crates pass through other crates",
        "A crate sliding on ice sometimes ends up stacked on a cell that already has another crate, so one of the crates disappears from the board and the pad count looks wrong.",
        [("if (t === null || t === '#' || this.crates.has(this._key(nr, nc))) break;", "if (t === null || t === '#') break;")], difficulty=3, rules=dict(SLIDE=True, WATER=False)),
    Bug("exact-solved", "Levels are declared solved with stray crates around",
        "In the strict yard a level is announced as SOLVED while a crate is still standing off the pads. The rules say surplus crates must be sunk first.",
        [("return covered === this.padTotal && (!EXACT || this.crates.size === this.padTotal);", "return covered === this.padTotal;")], difficulty=3, rules=dict(EXACT=True)),
    Bug("moves-after-solved", "Moves are still offered once the level is solved",
        "When the level is solved the engine still lists legal moves and happily lets me keep walking, which messes up the move count I report for the level.",
        [("if (this.solved()) return [];\n    return Object.keys(DIRS)", "return Object.keys(DIRS)")], difficulty=2),
    Bug("run-shift", "Pushing a row of crates loses a crate",
        "When I push two crates in a row they don't both move: afterwards there is only one crate where there were two, and the pad counter drops.",
        [("this.crates.delete(this._key(tr, tc));", "for (let q = 0; this.crates.has(this._key(tr + q * d[0], tc + q * d[1])); q++) this.crates.delete(this._key(tr + q * d[0], tc + q * d[1]));")],
        difficulty=3, rules=dict(MAX_PUSH=2, WATER=False)),
    Bug("pad-render", "Crates on pads look like plain crates",
        "In the board text a crate standing on a pad is drawn as a normal crate `B`, so I can't tell from the picture which pads are covered (the pads counter in the status line is right).",
        [("else if (crate) s += t === '_' ? '*' : 'B';", "else if (crate) s += 'B';")], difficulty=1),
    Bug("counter-illegal", "Failed moves are counted",
        "Walking into a wall increments the move counter even though nothing happens. (The move is correctly refused; the counter just moves anyway.)",
        [("if (typeof move !== 'string' || !this.legalMoves().includes(move)) throw new Error('illegal move: ' + move);",
          "this.moveCount++;\n    if (typeof move !== 'string' || !this.legalMoves().includes(move)) throw new Error('illegal move: ' + move);")], difficulty=2),
]


def _fix_edit_indent(b: Bug) -> Bug:
    """The BODY is indented by two spaces inside the class; edits above are written at the file's real indentation."""
    return b


@family("games-slidebox-fix", category="games", lang="javascript", kind="fix", n=12,
        summary="hand-injected defects in the Slidebox engine (pushing, sliding, water, costs, solved detection, render)")
def gen_fix(rng, n):
    used: list[str] = []
    cache = {}
    for k, bug in enumerate(BUGS[:n]):
        r = {**DEFAULT, **bug.rules}
        key = json.dumps(r, sort_keys=True)
        if key not in cache:
            sol = project(r)
            scripts = level_scripts(rng, r)
            hidden = _kit.data_files(LANG, scripts, sol, ADAPTER)
            vis = _kit.data_files(LANG, {"examples": example_scripts()}, sol, ADAPTER)
            cache[key] = (sol, hidden, vis, readme(r, _readme_example(r, sol)))
        sol, hidden, vis, rd = cache[key]
        base = {**sol, "README.md": rd}
        tests = {**_scen.check_files(LANG, ADAPTER), **vis}
        ctx = {"files": ["src/slidebox.js"], "verify": _scen.VERIFY[LANG]}
        yield _kit.bug_task(game=GAME, lang=LANG, base_files=base, tests=tests, hidden=hidden, bug=bug, ctx=ctx, rng=rng, used=used, k=k,
                            tags=["puzzle", "grid"], extra_notes={"rules": r})


# ----------------------------------------------------------------------------------------------------- feature: level files

LEVEL_COMMON = dd(r'''
    'use strict';
    const { Game } = require('./slidebox');

    class LevelError extends Error {}

    const VALID = '#._@+B*~';

    function count(s, set) {
      let n = 0;
      for (const ch of s) if (set.includes(ch)) n++;
      return n;
    }

    function validate(rows) {
      if (rows.length === 0) throw new LevelError('level is empty');
      const w = rows[0].length;
      for (let r = 0; r < rows.length; r++) {
        if (rows[r].length !== w) throw new LevelError(`row ${r + 1} has ${rows[r].length} columns, expected ${w}`);
      }
      for (let r = 0; r < rows.length; r++) {
        for (let c = 0; c < w; c++) {
          if (!VALID.includes(rows[r][c])) throw new LevelError(`unknown character '${rows[r][c]}' at row ${r + 1}, column ${c + 1}`);
        }
      }
      const all = rows.join('');
      const players = count(all, '@+');
      if (players === 0) throw new LevelError('no player');
      if (players > 1) throw new LevelError('more than one player');
      const pads = count(all, '_+*');
      if (pads === 0) throw new LevelError('no pads');
      const crates = count(all, 'B*');
      if (crates < pads) throw new LevelError(`not enough crates: ${crates} crates for ${pads} pads`);
    }

    function splitLines(text) {
      return text.split(/\r?\n/);
    }

    function trimBlankEnds(lines) {
      let a = 0;
      let b = lines.length;
      while (a < b && lines[a].trim() === '') a++;
      while (b > a && lines[b - 1].trim() === '') b--;
      return lines.slice(a, b);
    }
''')

LEVEL_V = {
    "plain": dd(r'''

        function parseLevel(text) {
          const rows = trimBlankEnds(splitLines(text));
          validate(rows);
          return rows.join('\n');
        }

        function loadLevel(text) {
          return new Game(parseLevel(text));
        }

        module.exports = { LevelError, parseLevel, loadLevel };
    '''),
    "headers": dd(r'''

        function parseLevel(text) {
          const lines = splitLines(text).filter((l) => !l.startsWith(';'));
          let i = 0;
          while (i < lines.length && lines[i].trim() === '') i++;
          const meta = { title: '', par: null };
          if (i < lines.length && lines[i].includes(':')) {
            const seen = new Set();
            while (i < lines.length && lines[i].trim() !== '') {
              const line = lines[i];
              const k = line.indexOf(':');
              if (k < 0) throw new LevelError(`bad header line '${line}'`);
              const key = line.slice(0, k).trim();
              const value = line.slice(k + 1).trim();
              if (key !== 'title' && key !== 'par') throw new LevelError(`unknown header '${key}'`);
              if (seen.has(key)) throw new LevelError(`duplicate header '${key}'`);
              seen.add(key);
              if (key === 'par') {
                if (!/^[1-9][0-9]*$/.test(value)) throw new LevelError('par must be a positive integer');
                meta.par = parseInt(value, 10);
              } else {
                meta.title = value;
              }
              i++;
            }
          }
          const rows = trimBlankEnds(lines.slice(i));
          validate(rows);
          return { title: meta.title, par: meta.par, level: rows.join('\n') };
        }

        function loadLevel(text) {
          return new Game(parseLevel(text).level);
        }

        module.exports = { LevelError, parseLevel, loadLevel };
    '''),
    "pack": dd(r'''

        function parsePack(text) {
          const levels = [];
          let cur = null;
          for (const line of splitLines(text)) {
            if (line.startsWith('==')) {
              cur = { title: line.slice(2).trim(), rows: [] };
              levels.push(cur);
            } else if (cur) {
              cur.rows.push(line);
            } else if (line.trim() !== '') {
              throw new LevelError('text before the first level');
            }
          }
          if (levels.length === 0) throw new LevelError('pack is empty');
          return levels.map((lv, k) => {
            const rows = trimBlankEnds(lv.rows);
            try {
              validate(rows);
            } catch (e) {
              throw new LevelError(`level ${k + 1}: ${e.message}`);
            }
            return { title: lv.title, level: rows.join('\n') };
          });
        }

        module.exports = { LevelError, parsePack };
    '''),
    "rle": dd(r'''

        function expandRow(row, number) {
          let out = '';
          let i = 0;
          while (i < row.length) {
            const ch = row[i];
            if (ch >= '0' && ch <= '9') {
              let j = i;
              while (j < row.length && row[j] >= '0' && row[j] <= '9') j++;
              const digits = row.slice(i, j);
              if (digits.length > 2 || j >= row.length || parseInt(digits, 10) === 0) throw new LevelError(`bad run-length at row ${number}`);
              out += row[j].repeat(parseInt(digits, 10));
              i = j + 1;
            } else {
              out += ch;
              i++;
            }
          }
          return out;
        }

        function parseLevel(text) {
          const rows = trimBlankEnds(splitLines(text)).map((row, k) => expandRow(row, k + 1));
          validate(rows);
          return rows.join('\n');
        }

        function loadLevel(text) {
          return new Game(parseLevel(text));
        }

        module.exports = { LevelError, parseLevel, loadLevel };
    '''),
}

LOADER_ADAPT = {
    "plain": '''
          case 'load': // load <file text, "\\n" and "\\r" escapes expanded>: "ok" or "error: <message>"
            try {
              this.game = loadLevel(unescape(args));
              return 'ok';
            } catch (e) {
              if (e instanceof LevelError) return 'error: ' + e.message;
              throw e;
            }''',
    "headers": '''
          case 'load': // load <file text, "\\n" and "\\r" escapes expanded>: "ok title=<title> par=<par or ->" or "error: <message>"
            try {
              const parsed = parseLevel(unescape(args));
              this.game = new Game(parsed.level);
              return 'ok title=' + parsed.title + ' par=' + (parsed.par === null ? '-' : parsed.par);
            } catch (e) {
              if (e instanceof LevelError) return 'error: ' + e.message;
              throw e;
            }''',
    "pack": '''
          case 'pack': // pack <file text>: "ok <n> <title>=<level rows joined by |>;..." or "error: <message>"
            try {
              const levels = parsePack(unescape(args));
              return 'ok ' + levels.length + ' ' + levels.map((l) => l.title + '=' + l.level.split('\\n').join('|')).join(';');
            } catch (e) {
              if (e instanceof LevelError) return 'error: ' + e.message;
              throw e;
            }''',
    "rle": '''
          case 'load': // load <file text, "\\n" and "\\r" escapes expanded>: "ok" or "error: <message>"
            try {
              this.game = loadLevel(unescape(args));
              return 'ok';
            } catch (e) {
              if (e instanceof LevelError) return 'error: ' + e.message;
              throw e;
            }''',
}
LOADER_REQ = {"plain": "const { LevelError, loadLevel } = require('../src/level');", "headers": "const { LevelError, parseLevel } = require('../src/level');",
              "pack": "const { LevelError, parsePack } = require('../src/level');", "rle": "const { LevelError, loadLevel } = require('../src/level');"}


def loader_adapter(variant: str) -> dict[str, str]:
    a = ADAPTER["test/adapter.js"]
    a = a.replace("const { Game } = require('../src/slidebox');", "const { Game } = require('../src/slidebox');\n" + LOADER_REQ[variant] +
                  "\n\nconst unescape = (s) => s.split('\\\\n').join('\\n').split('\\\\r').join('\\r');")
    target = "      default:\n"
    assert a.count(target) == 1
    block = "\n".join(line[4:] for line in LOADER_ADAPT[variant].lstrip("\n").split("\n"))
    return {"test/adapter.js": a.replace(target, block + "\n" + target)}


def loader_readme(variant: str) -> str:
    common_err = dd('''
        Validation (after the format-specific parsing) is done on the final rows, in this order; the first failure is reported:

        1. no rows at all: `level is empty`
        2. rows of different lengths: `row R has C columns, expected W` (R: the first row whose length differs from the first row's, counted from 1; C its length; W the length of row 1)
        3. a character that is not one of `# . _ @ + B * ~`: `unknown character 'X' at row R, column C` (the first one in reading order, rows and columns counted from 1)
        4. `no player` (no `@` or `+`), `more than one player` (together more than one)
        5. `no pads` (no `_`, `+` or `*`)
        6. fewer crates than pads (`B` and `*` count as crates; `*` and `+` count on pads too): `not enough crates: C crates for P pads`
    ''')
    lines = ("**Files** are text; lines end with `\\n` or `\\r\\n`. `parseLevel`/`loadLevel` live in a new module `src/level.js`, which also exports `LevelError`, "
             "a subclass of `Error`; every validation failure is thrown as a `LevelError` whose `message` is the text given below. (The engine itself, `src/slidebox.js`, stays as it is.)")
    if variant == "plain":
        body = dd('''
            `loadLevel(text)` turns the text of a level file into a `Game`; `parseLevel(text)` returns the normalised level string (rows joined by `\\n`).

            * The file is one level: its rows, one per line. Blank lines (empty or only spaces and tabs) at the start and at the end of the file are ignored; a blank line between rows is a row of
              length 0. Rows are taken exactly as written (a trailing space is a character like any other, and an unknown one).
        ''')
    elif variant == "headers":
        body = dd('''
            `parseLevel(text)` returns `{ title, par, level }` (the level is the rows joined by `\\n`); `loadLevel(text)` returns a `Game` built from it.

            * Lines starting with `;` are comments: they are removed before anything else.
            * The file has an optional header followed by the rows. There is a header exactly when the first non-blank line (after removing comments) contains a `:`. The header lasts until the first
              blank line; every header line is `key: value` (split at the first colon, key and value trimmed). A header line without a colon is `bad header line '<the line as written>'`.
            * Known keys: `title` (any text, default `''`) and `par` (default `null`; it must match `[1-9][0-9]*` or the error is `par must be a positive integer`, and it is returned as a number).
              An unknown key is `unknown header 'key'`; a repeated key is `duplicate header 'key'`. Header errors are reported in reading order, before any level validation.
            * After the header (and its blank line) come the rows; blank lines at the start and the end are ignored.
        ''')
    elif variant == "pack":
        body = dd('''
            A *pack* file holds several levels. `parsePack(text)` returns an array of `{ title, level }` (level: the rows joined by `\\n`); there is no `loadLevel` in this module.

            * A line that starts with `==` begins a new level; the rest of the line, trimmed, is its title (possibly empty). Every other line belongs to the level that began last; blank lines at the
              start and the end of a level's lines are ignored.
            * Text before the first `==` line must be blank: otherwise `text before the first level` (reported as soon as that line is met, before anything else). A file with no `==` line at all
              (and only blank lines) is `pack is empty`.
            * Levels are validated in order with the rules below; the error of the first invalid level is prefixed with its number: `level 2: no player`.
        ''')
    else:
        body = dd('''
            `loadLevel(text)` turns the text of a level file into a `Game`; `parseLevel(text)` returns the normalised level string (rows joined by `\\n`).

            * The file is one level, one row per line; blank lines (empty or only spaces and tabs) at the start and the end are ignored.
            * Rows may be *run-length encoded*: a run of one or two digits immediately followed by any non-digit character stands for that character repeated that many times: `3#.2B` is `###.BB`.
              All other characters stand for themselves. Digits that are not followed by a character (at the end of the row), a count of `0`, or a run of three or more digits is the error
              `bad run-length at row R` (R counted from 1 over the rows that remain after the blank lines were dropped). Every row is expanded first (top to bottom, the first bad row is reported)
              and only then are the expanded rows validated.
        ''')
    return f"## Feature to add: level files\n\n{lines}\n\n{body}\n{common_err}\n"


def _lv(rng) -> str:
    return HAND_LEVELS[rng.randrange(len(HAND_LEVELS))]


def _crlf(t: str) -> str:
    return t.replace("\n", "\r\n")


def _enc(text: str) -> str:
    return text.replace("\r", "\\r").replace("\n", "\\n")


def loader_cases(rng, variant: str) -> list[str]:
    """Raw file texts exercising the format; most are valid, many fail validation in different ways."""
    base = [HAND_LEVELS[0], HAND_LEVELS[2], HAND_LEVELS[3], HAND_LEVELS[4], "#####\n#@B_#\n#####", "#######\n#..~..#\n#@B_B_#\n#######"]
    cases: list[str] = []

    def mut(level: str) -> list[str]:
        rows = level.split("\n")
        out = [level, "\n\n" + level + "\n\n\n", "  \n" + level + "\n \t \n", _crlf(level), _crlf(level) + "\r\n", level + "\n  x", level.replace("\n", "\n\n", 1)]
        r = rng.randrange(1, len(rows) - 1)
        ragged = rows[:]
        ragged[r] = ragged[r][:-1]
        out.append("\n".join(ragged))
        ragged2 = rows[:]
        ragged2[-1] = ragged2[-1] + "#"
        out.append("\n".join(ragged2))
        for ch in ("x", "1", "-", " ", "b"):
            rr = rng.randrange(1, len(rows) - 1)
            cc = rng.randrange(1, len(rows[0]) - 1)
            m = rows[:]
            m[rr] = m[rr][:cc] + ch + m[rr][cc + 1:]
            out.append("\n".join(m))
        text = level.replace("@", ".", 1)
        out.append(text)
        out.append(level.replace("_", "@", 1) if "_" in level else level)
        out.append(level.replace("_", ".").replace("*", "B"))
        out.append(level.replace("B", ".", 1))
        out.append(level.replace("B", ".").replace("*", "."))
        # precedence: ragged + unknown, unknown + no player, no player + no pads, two players + too few crates
        m = rows[:]
        m[1] = m[1][:-1]
        m[-2] = m[-2][:1] + "x" + m[-2][2:]
        out.append("\n".join(m))
        out.append(level.replace("@", "?", 1).replace("B", "!", 1))
        out.append(level.replace("@", ".").replace("_", "."))
        out.append(level.replace("B", ".", 1).replace(".", "@", 1))
        return out

    for lv in base:
        cases += mut(lv)
    cases.append("")
    cases.append("\n\n  \n")
    cases.append("\n".join(["#"]))

    if variant == "plain":
        pass
    elif variant == "headers":
        out = []
        for lv in base[:4]:
            out += [
                f"title: Cellar 3\npar: 14\n\n{lv}",
                f"; made by hand\ntitle:   Spaced out   \n\n; second comment\n{lv}\n; end",
                f"par: 7\n\n{lv}",
                f"title: only a title\n{lv}",
                f"par: 0\n\n{lv}",
                f"par: 07\n\n{lv}",
                f"par: -3\n\n{lv}",
                f"par: 4x\n\n{lv}",
                f"title: A\ntitle: B\n\n{lv}",
                f"author: me\n\n{lv}",
                f"title: A\nnot a header\n\n{lv}",
                f"\n\ntitle: t:colon:inside\npar: 5\n\n\n{lv}",
                f"{lv}",
                f"title: x\r\npar: 3\r\n\r\n{_crlf(lv)}",
                f"title: x\n\n{lv.replace('@', '.', 1)}",
                f"par: oops\nauthor: x\n\n{lv}",
                f"author: x\nauthor: y\npar: 0\n\n{lv}",
                f";only a comment\n{lv}",
                f"{lv.split(chr(10))[0]}\n;{lv.split(chr(10))[1]}\n" + "\n".join(lv.split("\n")[1:]),
            ]
        cases = out + cases[:12]
    elif variant == "pack":
        out = []
        a, b, c = base[0], base[4], base[3]
        out += [
            f"== One\n{a}\n== Two\n{b}\n== Three\n{c}\n",
            f"== Only\n{a}",
            f"\n\n== \n{a}\n==    Spaces   \n\n{b}\n\n",
            f"title\n== One\n{a}",
            f"  \n\n== One\n{a}\n",
            f"== One\n{a}\n== Two\n{b.replace('@', '.')}\n",
            f"== One\n{a.replace('B', '.')}\n== Two\n{b.replace('@', '.')}\n",
            f"== One\n{a}\n==\n{b}\n== Three\n",
            f"== One\n\n== Two\n{b}",
            "",
            "\n\n  \n",
            "just text",
            f"== One\r\n{_crlf(a)}\r\n== Two\r\n{_crlf(b)}",
            f"==A\n{a}\n==B\n{b}\n==C\n{c.replace('#', '#x', 1)}",
            f"== One\n{a}\n== Two\n{b}\n== Three\n{c[:-2]}",
            f"= not a separator\n== One\n{a}",
            f"== One\n{a}\n== Two\n{a.replace('_', '.')}",
            f"== One\n{a}\n=== Three equals\n{b}",
        ]
        for lv in base:
            out += [f"== X\n{lv}", f"== X\n{lv.replace('@', '.', 1)}\n== Y\n{lv}"]
        cases = out
    else:  # rle
        def comp(level: str) -> str:
            rows = []
            for row in level.split("\n"):
                s, i = "", 0
                while i < len(row):
                    j = i
                    while j < len(row) and row[j] == row[i]:
                        j += 1
                    n = j - i
                    s += (str(min(n, 99)) + row[i]) if n >= 3 else row[i] * n
                    i = j
                rows.append(s)
            return "\n".join(rows)
        out = []
        for lv in base:
            out += [comp(lv), comp(lv) + "\n\n", "\n" + comp(lv), _crlf(comp(lv)), lv]
        out += ["3#\n#@B_#\n3#", "#@2B3_#", "2#\n#@B_#", "5#\n5#\n5#", "0#\n#@B_#", "123#\n#@B_#", "5#\n#@B_#\n5", "#@B_#4", "9#\n#@B_9", "5#\n#@B_#\n#2x@#", "5#\n#@B_#\n#10.#",
                "99.", "5#\n#@B_#\n#3 .#", "5#\n#@B_#\n5#" + "\n" + "7#", "5#\n#@B_#\n5#\n\n5#"]
        cases = out
    # drop duplicates, keep order, cap
    seen, uniq = set(), []
    for c in cases:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    rng.shuffle(uniq)
    return uniq[:70]


def loader_scripts(rng, variant: str) -> dict[str, str]:
    verb = "pack" if variant == "pack" else "load"
    cases = loader_cases(rng, variant)
    lines = ["# scenario files"]
    for c in cases:
        lines.append(f"> {verb} {_enc(c)}")
        if variant != "pack":
            lines.append("> render")
            lines.append("> new #####|#@B_#|#####")  # a failed load must leave a known game in place: reset it for the next case
    return {"hidden_levels": "\n".join(lines) + "\n"}


LOADER_VARIANTS = [
    dict(key="plain", d=3, ask="Our level editor saves plain text files and the engine has no way to read them. Please add a level loader (a new `src/level.js`) as specified in the new README section: "
                           "exact error messages included, because the editor shows them to the author."),
    dict(key="headers", d=4, ask="I want to ship levels as files with a small header (title, par) and `;` comments. The format and every error message are written down in README.md, in the section "
                            "about level files. Implement it in a new `src/level.js`; the engine itself should not need to change."),
    dict(key="pack", d=3, ask="Level packs: one text file with many levels, each introduced by a `==` line with a title. Add `parsePack` in `src/level.js` as described in README.md. The error messages are "
                           "compared literally by the pack-building tool."),
    dict(key="rle", d=3, ask="Write the level loader for Slidebox files (new module `src/level.js`). Files are compressed with run-length digits, so the loader has to expand them before it validates "
                          "anything; README.md has the details and the exact error messages."),
]


@family("games-slidebox-loader", category="games", lang="javascript", kind="feature", n=4,
        summary="add a level-file loader with exact validation messages (plain, headers and comments, packs, run-length rows) to the Slidebox engine")
def gen_loader(rng, n):
    for i, v in enumerate(LOADER_VARIANTS[:n]):
        r = {**DEFAULT}
        sol = project(r)
        adapter = loader_adapter(v["key"])
        level_js = LEVEL_COMMON + LEVEL_V[v["key"]]
        full_sol = {**sol, "src/level.js": level_js}
        scripts = loader_scripts(rng, v["key"])
        hidden = _kit.data_files(LANG, {**scripts, **level_scripts(rng, r, 2, 2)}, full_sol, adapter)
        vis_script = dd('''
            # scenario load and play
            > new #####|#@B_#|#####
            > render
        ''') + ("> load #####\\n#@B_#\\n#####\n> render\n> do R\n> load #####\\n#@B_##\\n#####\n> load\n" if v["key"] != "pack" else "> pack == A\\n#####\\n#@B_#\\n#####\n> pack\n")
        vis = _kit.data_files(LANG, {"examples": example_scripts(), "loader": vis_script}, full_sol, adapter)
        start = {"README.md": readme(r, _readme_example(r, sol)).replace("## Tests\n", loader_readme(v["key"]) + "\n## Tests\n"), **sol,
                 **_scen.check_files(LANG, adapter), **vis}
        yield Task(slug=f"{i + 1:02d}-{v['key']}", prompt=v["ask"], difficulty=v["d"], start=start, hidden=hidden, solution={"src/level.js": level_js},
                   verify=_scen.VERIFY[LANG], tags=["parser", "validation", "feature"], notes={"variant": v["key"]})
