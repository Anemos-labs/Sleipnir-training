"""Cinder (rust): a grid-ball brick breaker with hit points, explosive and steel bricks, speed-ups, and shrinking paddles.
Build, fix and replay-log tasks; a python model cross-checks the reference engine and plays tracking games."""
from __future__ import annotations

import json
import textwrap
from collections import deque

from fx import Task, dd, family

from . import _kit, _scen
from ._kit import Bug

LANG = "rust"
GAME = "Cinder"
PKG = "cinder"
DEFAULT = dict(W=11, H=12, PW=4, SHRINK=0, LIVES=3, STEP=6, ENGLISH=True, ALT=True)


def header(r: dict) -> str:
    return dd(f'''
        // ---- house rules for this court (they are part of the specification, see README.md) ----
        pub const W: usize = {r["W"]};
        pub const H: usize = {r["H"]};
        pub const PADDLE: usize = {r["PW"]};
        pub const SHRINK: usize = {r["SHRINK"]};
        pub const LIVES: u32 = {r["LIVES"]};
        pub const SPEED_STEP: usize = {r["STEP"]};
        pub const ENGLISH: bool = {"true" if r["ENGLISH"] else "false"};
        pub const ALT_SERVE: bool = {"true" if r["ALT"] else "false"};
        // -----------------------------------------------------------------------------------------
    ''')


BODY = dd(r'''
    use std::collections::VecDeque;

    #[derive(Clone, Copy, PartialEq, Debug)]
    enum State {
        Playing,
        Won,
        Lost,
    }

    /// One game of Cinder.
    pub struct Game {
        grid: [[u8; W]; H],
        orig: [[u8; W]; H],
        px: usize,
        pw: usize,
        bx: i32,
        by: i32,
        vx: i32,
        vy: i32,
        score: u32,
        lives: u32,
        destroyed: usize,
        state: State,
    }

    impl Game {
        /// `level` has `H` rows (joined by '\n') of `W` characters; the last row is the paddle row and is ignored.
        pub fn new(level: &str) -> Game {
            let mut grid = [[b'.'; W]; H];
            let mut orig = [[0u8; W]; H];
            for (y, row) in level.split('\n').enumerate().take(H - 1) {
                for (x, ch) in row.bytes().enumerate().take(W) {
                    grid[y][x] = ch;
                    orig[y][x] = match ch {
                        b'1' => 1,
                        b'2' => 2,
                        b'3' => 3,
                        b'X' => 1,
                        _ => 0,
                    };
                }
            }
            let mut g = Game {
                grid,
                orig,
                px: (W - PADDLE) / 2,
                pw: PADDLE,
                bx: 0,
                by: 0,
                vx: 1,
                vy: -1,
                score: 0,
                lives: LIVES,
                destroyed: 0,
                state: State::Playing,
            };
            g.serve();
            g
        }

        fn serve(&mut self) {
            self.bx = (self.px + self.pw / 2) as i32;
            self.by = (H - 2) as i32;
            self.vx = if !ALT_SERVE || self.lives % 2 == 1 { 1 } else { -1 };
            self.vy = -1;
        }

        fn speed(&self) -> usize {
            1 + (self.destroyed / SPEED_STEP).min(2)
        }

        fn solid(&self, x: i32, y: i32) -> bool {
            self.grid[y as usize][x as usize] != b'.'
        }

        fn remaining(&self) -> usize {
            self.grid.iter().flatten().filter(|&&c| (b'1'..=b'3').contains(&c) || c == b'X').count()
        }

        /// The legal commands: `L`, `R`, `S` (empty when the game is over).
        pub fn legal_moves(&self) -> Vec<String> {
            let mut out = Vec::new();
            if self.state != State::Playing {
                return out;
            }
            if self.px > 0 {
                out.push("L".to_string());
            }
            if self.px + self.pw < W {
                out.push("R".to_string());
            }
            out.push("S".to_string());
            out
        }

        /// Plays one tick; returns the events or an error for an illegal command.
        pub fn step(&mut self, cmd: &str) -> Result<String, String> {
            if !self.legal_moves().iter().any(|m| m == cmd) {
                return Err(format!("illegal command: {}", cmd));
            }
            let mut ev: Vec<String> = Vec::new();
            match cmd {
                "L" => self.px -= 1,
                "R" => self.px += 1,
                _ => {}
            }
            for _ in 0..self.speed() {
                if !self.ball_step(&mut ev) {
                    break;
                }
            }
            if self.state == State::Playing {
                if self.remaining() == 0 {
                    self.state = State::Won;
                } else if self.lives == 0 {
                    self.state = State::Lost;
                }
            }
            Ok(if ev.is_empty() { "idle".to_string() } else { ev.join("; ") })
        }

        fn ball_step(&mut self, ev: &mut Vec<String>) -> bool {
            let nx = self.bx + self.vx;
            if nx < 0 || nx >= W as i32 {
                self.vx = -self.vx;
                ev.push("wall".to_string());
            } else if self.solid(nx, self.by) {
                self.hit(nx as usize, self.by as usize, ev);
                self.vx = -self.vx;
            } else {
                self.bx = nx;
            }
            let ny = self.by + self.vy;
            if ny < 0 {
                self.vy = -self.vy;
                ev.push("ceiling".to_string());
            } else if ny == (H - 1) as i32 {
                let x = self.bx as usize;
                if x >= self.px && x < self.px + self.pw {
                    self.vy = -self.vy;
                    if ENGLISH {
                        if x == self.px {
                            self.vx = -1;
                        } else if x == self.px + self.pw - 1 {
                            self.vx = 1;
                        }
                    }
                    ev.push("paddle".to_string());
                } else {
                    self.lives -= 1;
                    ev.push("lost".to_string());
                    if self.lives == 0 {
                        self.state = State::Lost;
                    } else {
                        self.pw = (self.pw.saturating_sub(SHRINK)).max(2);
                        self.serve();
                    }
                    return false;
                }
            } else if self.solid(self.bx, ny) {
                self.hit(self.bx as usize, ny as usize, ev);
                self.vy = -self.vy;
            } else {
                self.by = ny;
            }
            true
        }

        fn hit(&mut self, x: usize, y: usize, ev: &mut Vec<String>) {
            let mut queue = VecDeque::new();
            queue.push_back((x, y, true));
            while let Some((cx, cy, direct)) = queue.pop_front() {
                match self.grid[cy][cx] {
                    b'#' => {
                        if direct {
                            ev.push(format!("clang {},{}", cx, cy));
                        }
                    }
                    b'.' => {}
                    b'X' => {
                        self.grid[cy][cx] = b'.';
                        self.destroyed += 1;
                        self.score += 10;
                        ev.push(format!("boom {},{}", cx, cy));
                        for (dx, dy) in [(0i32, -1i32), (0, 1), (-1, 0), (1, 0)] {
                            let nx = cx as i32 + dx;
                            let ny = cy as i32 + dy;
                            if nx >= 0 && ny >= 0 && (nx as usize) < W && (ny as usize) < H {
                                queue.push_back((nx as usize, ny as usize, false));
                            }
                        }
                    }
                    d => {
                        if d > b'1' {
                            self.grid[cy][cx] = d - 1;
                            ev.push(format!("hit {},{}", cx, cy));
                        } else {
                            self.grid[cy][cx] = b'.';
                            self.destroyed += 1;
                            self.score += 10 * self.orig[cy][cx] as u32;
                            ev.push(format!("break {},{}", cx, cy));
                        }
                    }
                }
            }
        }

        pub fn score(&self) -> u32 {
            self.score
        }

        pub fn status(&self) -> &'static str {
            match self.state {
                State::Playing => "playing",
                State::Won => "won",
                State::Lost => "lost",
            }
        }

        /// The court as text.
        pub fn render(&self) -> String {
            let mut lines: Vec<String> = Vec::new();
            for y in 0..H {
                let mut row = String::new();
                for x in 0..W {
                    let ch = if y == H - 1 {
                        if x >= self.px && x < self.px + self.pw { '=' } else { '.' }
                    } else if self.state != State::Lost && self.bx == x as i32 && self.by == y as i32 {
                        'o'
                    } else {
                        self.grid[y][x] as char
                    };
                    row.push(ch);
                }
                lines.push(row);
            }
            let mut status = format!("score {} lives {} speed {}", self.score, self.lives, self.speed());
            match self.state {
                State::Won => status.push_str(" WON"),
                State::Lost => status.push_str(" LOST"),
                State::Playing => {}
            }
            lines.push(status);
            lines.join("\n")
        }
    }
''')


def engine(r: dict) -> str:
    return "//! Cinder: a grid-ball brick breaker. The rules are in README.md.\n\n" + header(r) + "\n" + BODY


STUB = dd(r'''
    //! Cinder: a grid-ball brick breaker. The rules and the API are in README.md.

    /// One game of Cinder.
    pub struct Game {}

    impl Game {
        pub fn new(level: &str) -> Game {
            todo!()
        }

        pub fn legal_moves(&self) -> Vec<String> {
            todo!()
        }

        pub fn step(&mut self, cmd: &str) -> Result<String, String> {
            todo!()
        }

        pub fn score(&self) -> u32 {
            todo!()
        }

        pub fn status(&self) -> &'static str {
            todo!()
        }

        pub fn render(&self) -> String {
            todo!()
        }
    }
''')

ADAPTER = {"tests/adapter/mod.rs": dd(r'''
    // Maps scenario commands onto the engine API (the scenario runner is tests/scenarios.rs).
    use cinder::Game;

    pub struct Adapter {
        game: Option<Game>,
    }

    impl Adapter {
        pub fn new() -> Adapter {
            Adapter { game: None }
        }

        pub fn run(&mut self, verb: &str, args: &str) -> String {
            match verb {
                // new <level rows joined by |>
                "new" => {
                    self.game = Some(Game::new(&args.replace('|', "\n")));
                    "ok".to_string()
                }
                // do <command>: the event text, or "illegal"
                "do" => match self.game.as_mut().unwrap().step(args) {
                    Ok(ev) => ev,
                    Err(_) => "illegal".to_string(),
                },
                // sorted legal commands joined by "," ("-" when there are none)
                "legal" => {
                    let mut m = self.game.as_ref().unwrap().legal_moves();
                    m.sort();
                    if m.is_empty() {
                        "-".to_string()
                    } else {
                        m.join(",")
                    }
                }
                "render" => self.game.as_ref().unwrap().render(),
                // "<score> <status>"
                "status" => {
                    let g = self.game.as_ref().unwrap();
                    format!("{} {}", g.score(), g.status())
                }
                _ => panic!("unknown verb {}", verb),
            }
        }
    }
''')}


# ----------------------------------------------------------------------------------------------------- python model

class Model:
    def __init__(self, level: str, r: dict):
        self.r = r
        W, H = r["W"], r["H"]
        self.grid = [["."] * W for _ in range(H)]
        self.orig = [[0] * W for _ in range(H)]
        for y, row in enumerate(level.split("\n")[: H - 1]):
            for x, ch in enumerate(row[:W]):
                self.grid[y][x] = ch
                self.orig[y][x] = {"1": 1, "2": 2, "3": 3, "X": 1}.get(ch, 0)
        self.pw = r["PW"]
        self.px = (W - self.pw) // 2
        self.score, self.lives, self.destroyed, self.state = 0, r["LIVES"], 0, "playing"
        self.serve()

    def serve(self):
        self.bx, self.by = self.px + self.pw // 2, self.r["H"] - 2
        self.vx = 1 if (not self.r["ALT"] or self.lives % 2 == 1) else -1
        self.vy = -1

    def speed(self):
        return 1 + min(self.destroyed // self.r["STEP"], 2)

    def remaining(self):
        return sum(1 for row in self.grid for c in row if c in "123X")

    def legal(self):
        if self.state != "playing":
            return []
        out = []
        if self.px > 0:
            out.append("L")
        if self.px + self.pw < self.r["W"]:
            out.append("R")
        return out + ["S"]

    def step(self, cmd):
        ev = []
        if cmd == "L":
            self.px -= 1
        elif cmd == "R":
            self.px += 1
        for _ in range(self.speed()):
            if not self.ball(ev):
                break
        if self.state == "playing":
            if self.remaining() == 0:
                self.state = "won"
            elif self.lives == 0:
                self.state = "lost"
        return "; ".join(ev) if ev else "idle"

    def solid(self, x, y):
        return self.grid[y][x] != "."

    def ball(self, ev):
        W, H = self.r["W"], self.r["H"]
        nx = self.bx + self.vx
        if nx < 0 or nx >= W:
            self.vx = -self.vx
            ev.append("wall")
        elif self.solid(nx, self.by):
            self.hit(nx, self.by, ev)
            self.vx = -self.vx
        else:
            self.bx = nx
        ny = self.by + self.vy
        if ny < 0:
            self.vy = -self.vy
            ev.append("ceiling")
        elif ny == H - 1:
            if self.px <= self.bx < self.px + self.pw:
                self.vy = -self.vy
                if self.r["ENGLISH"]:
                    if self.bx == self.px:
                        self.vx = -1
                    elif self.bx == self.px + self.pw - 1:
                        self.vx = 1
                ev.append("paddle")
            else:
                self.lives -= 1
                ev.append("lost")
                if self.lives == 0:
                    self.state = "lost"
                else:
                    self.pw = max(2, self.pw - self.r["SHRINK"]) if self.pw >= self.r["SHRINK"] else 2
                    self.serve()
                return False
        elif self.solid(self.bx, ny):
            self.hit(self.bx, ny, ev)
            self.vy = -self.vy
        else:
            self.by = ny
        return True

    def hit(self, x, y, ev):
        W, H = self.r["W"], self.r["H"]
        q = deque([(x, y, True)])
        while q:
            cx, cy, direct = q.popleft()
            c = self.grid[cy][cx]
            if c == "#":
                if direct:
                    ev.append("clang %d,%d" % (cx, cy))
            elif c == ".":
                pass
            elif c == "X":
                self.grid[cy][cx] = "."
                self.destroyed += 1
                self.score += 10
                ev.append("boom %d,%d" % (cx, cy))
                for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < W and 0 <= ny < H:
                        q.append((nx, ny, False))
            else:
                if int(c) > 1:
                    self.grid[cy][cx] = str(int(c) - 1)
                    ev.append("hit %d,%d" % (cx, cy))
                else:
                    self.grid[cy][cx] = "."
                    self.destroyed += 1
                    self.score += 10 * self.orig[cy][cx]
                    ev.append("break %d,%d" % (cx, cy))

    def render(self):
        W, H = self.r["W"], self.r["H"]
        lines = []
        for y in range(H):
            row = ""
            for x in range(W):
                if y == H - 1:
                    row += "=" if self.px <= x < self.px + self.pw else "."
                elif self.state != "lost" and (self.bx, self.by) == (x, y):
                    row += "o"
                else:
                    row += self.grid[y][x]
            lines.append(row)
        status = "score %d lives %d speed %d" % (self.score, self.lives, self.speed())
        if self.state == "won":
            status += " WON"
        elif self.state == "lost":
            status += " LOST"
        return "\\n".join(lines + [status])


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
                    got = m.step(args)
                    assert got == want, f"model/engine disagree on {cmd}: {got!r} vs {want!r}"
                else:
                    assert want == "illegal", f"model says illegal for {cmd}, engine says {want!r}"
            elif verb == "legal":
                got = ",".join(sorted(m.legal())) or "-"
                assert got == want, f"legal disagree: {got!r} vs {want!r}"
            elif verb == "status":
                got = f"{m.score} {m.state}"
                assert got == want, f"status disagree {got!r} vs {want!r}"
            elif verb == "render":
                assert m.render() == want, f"render disagree:\n{m.render()}\n{want}"
            cmd = None


def make_level(rng, r: dict, rows: int = 4, steel: bool = True, boom: bool = True) -> str:
    W, H = r["W"], r["H"]
    grid = [["."] * W for _ in range(H)]
    for y in range(1, 1 + rows):
        for x in range(W):
            roll = rng.randrange(100)
            if roll < 10:
                continue
            grid[y][x] = "1" if roll < 45 else "2" if roll < 75 else "3" if roll < 88 else ("X" if boom else "1") if roll < 96 else ("#" if steel else "2")
    return "\n".join("".join(row) for row in grid)


def tracking_moves(rng, level: str, r: dict, ticks: int, noise: int) -> list[str]:
    """Moves of a paddle that follows the ball (with some noise): plays the model and records the commands."""
    m = Model(level, r)
    out = []
    for _ in range(ticks):
        if m.state != "playing":
            break
        target = m.bx - m.pw // 2
        if rng.randrange(100) < noise:
            mv = rng.choice(m.legal())
        elif m.px < target and "R" in m.legal():
            mv = "R"
        elif m.px > target and "L" in m.legal():
            mv = "L"
        else:
            mv = "S"
        m.step(mv)
        out.append(mv)
    return out


def scripts(rng, r: dict) -> dict[str, str]:
    W, H = r["W"], r["H"]
    parts = []
    for i in range(4):
        lv = make_level(rng, r, rows=rng.choice([3, 4, 5]), steel=(i % 2 == 1), boom=(i != 0))
        row = lv.replace("\n", "|")
        mv = tracking_moves(rng, lv, r, 1500, noise=[4, 10, 2, 18][i])
        parts.append(f"# scenario tracking {i + 1}\n> new {row}\n> render\n" + "\n".join(f"> do {m}" + ("\n> render" if k % 29 == 28 else "") for k, m in enumerate(mv)) + "\n> render\n> status\n> legal")
        parts.append(f"# scenario random paddle {i + 1}\n> new {row}\n~ rand 700 {rng.randrange(1, 900)} every=11 emit=render,status junk=Left|X|0|LR| L")
    # a hand-made explosion chain and a steel wall
    chain = ["." * W] * H
    chain = [list(r_) for r_ in chain]
    for x in range(1, W - 1):
        chain[2][x] = "X"
    chain[3][W // 2] = "3"
    chain[1][W // 2] = "#"
    lv = "\n".join("".join(row) for row in chain)
    mv = tracking_moves(rng, lv, r, 800, noise=3)
    parts.append("# scenario explosion chain\n> new " + lv.replace("\n", "|") + "\n" + "\n".join(f"> do {m}" + ("\n> render" if k % 17 == 16 else "") for k, m in enumerate(mv)) + "\n> render\n> status")
    for i in range(6):
        grid = [["."] * W for _ in range(H)]
        cells = [(y, x) for y in range(1, 4) for x in range(W)]
        rng.shuffle(cells)
        y, x = cells.pop()
        grid[y][x] = "X"
        for _ in range(rng.choice([1, 2])):
            y, x = cells.pop()
            grid[y][x] = "1"
        lv = "\n".join("".join(row) for row in grid)
        mv = tracking_moves(rng, lv, r, 1200, noise=5)
        parts.append(f"# scenario few bricks {i + 1}\n> new " + lv.replace("\n", "|") + "\n" + "\n".join(f"> do {m}" + ("\n> render" if k % 23 == 22 else "") for k, m in enumerate(mv)) + "\n> render\n> status\n> legal")
    parts.append(f"# scenario edges\n> new {make_level(rng, r).replace(chr(10), '|')}\n" + "\n".join(["> do L"] * (W // 2 + 2) + ["> render"] + ["> do R"] * (W + 2) + ["> render", "> legal", "> do S", "> do x", "> do", "> status"]))
    return {"hidden_games": "\n".join(parts) + "\n"}


def example_script(rng, r: dict) -> str:
    lv = make_level(rng, r, rows=3, steel=True, boom=True)
    row = lv.replace("\n", "|")
    return f"# scenario first ticks\n> new {row}\n> render\n> do S\n> do S\n> do R\n> render\n> do S\n> legal\n> status\n# scenario random\n> new {row}\n~ rand 25 3 emit=render,status\n"


# ----------------------------------------------------------------------------------------------------- README

def readme(r: dict) -> str:
    W, H, PW = r["W"], r["H"], r["PW"]
    s = []
    s.append("# Cinder\n\nA brick breaker on a grid. The ball moves one cell at a time along both axes, bricks have hit points, some bricks explode, some cannot be broken, and the paddle can shrink. The engine is headless: "
             "a `Game` built from a level text, a list of legal commands and exact text for every reply.\n")
    s.append(f"## The court\n\nThe court is {W} columns wide and {H} rows high; `(x, y)` is column `x` (0 at the left), row `y` (0 at the top). Row {H - 1} is the *paddle row*; rows 0..{H - 2} hold bricks and the ball.\n\n"
             f"A level is {H} rows of {W} characters joined by `\\n` (the engine receives the text without a trailing newline; row {H - 1} is ignored: it is always the paddle row). Characters:\n\n"
             "| char | meaning |\n|---|---|\n| `.` | empty |\n| `1` `2` `3` | a brick with that many hit points left |\n| `X` | an explosive brick (1 hit point) |\n| `#` | a steel brick: never breaks |\n")
    s.append(f"## State at the start\n\nThe paddle is {PW} cells wide with its left end at column `px = (W - PW) / 2` (integer division = {(W - PW) // 2}); the ball is at `(px + PW / 2, {H - 2})` (integer division) and moves up and to the right: "
             f"velocity `(vx, vy) = (+1, -1)` (`vy = -1` is up). You have {r['LIVES']} lives, score 0 and no brick has been destroyed yet. Bricks destroyed so far are counted (an `X` that explodes counts as one destroyed brick, "
             "bricks destroyed by an explosion count too).\n")
    s.append("## Commands\n\nA command is `L` (paddle one column left), `R` (one column right) or `S` (stay). `L` is legal only if `px > 0`, `R` only if `px + paddle_width < " + str(W) + "`, `S` always; when the game is over there are no legal commands. "
             "One command is one *tick*:\n\n"
             "1. the paddle moves;\n"
             f"2. the ball makes `speed` *sub-steps*, where `speed = 1 + min(destroyed / {r['STEP']}, 2)` (integer division, `destroyed` as it is at the start of the tick); the sub-steps stop early if the ball is lost;\n"
             "3. the game is *won* if no brick with hit points (`1`, `2`, `3`, `X`) is left, *lost* if no lives are left.\n")
    ang = (" If the ball hits the paddle on its left end cell (`x == px`) `vx` becomes -1, on its right end cell (`x == px + width - 1`) `vx` becomes +1; elsewhere `vx` is unchanged." if r["ENGLISH"]
           else " The paddle does not change `vx`.")
    serve = (f"The new ball is served exactly like the first one except for `vx`: it is `+1` when the number of lives left is odd and `-1` when it is even." if r["ALT"] else "The new ball is served exactly like the first one (`vx = +1`).")
    shrink = (f" The paddle becomes `{r['SHRINK']}` cell{'s' if r['SHRINK'] != 1 else ''} narrower, but never narrower than 2, and keeps its left end `px`." if r["SHRINK"] else " The paddle keeps its width.")
    s.append("### One sub-step of the ball\n\nThe ball is at `(bx, by)` with velocity `(vx, vy)`. The two axes are resolved one after the other, X first, with the position updated in between.\n\n"
             "**X axis.** Let `nx = bx + vx`. If `nx` is outside `0..W-1`: `vx = -vx`, the ball stays, event `wall`. Else if `(nx, by)` holds a brick (any character except `.`): the brick is *hit* (below), `vx = -vx`, "
             "the ball stays. Else `bx = nx`.\n\n"
             f"**Y axis.** Let `ny = by + vy` (with the updated `bx`). If `ny < 0`: `vy = -vy`, the ball stays, event `ceiling`. Else if `ny` is the paddle row ({H - 1}): if the paddle covers column `bx` (`px <= bx < px + width`) the ball bounces: `vy = -vy`, "
             f"the ball stays, event `paddle`.{ang} Otherwise the ball is *lost*: one life is gone, event `lost`; if no life is left the game is lost at once, else{shrink} {serve} The rest of the tick's sub-steps are skipped. "
             "Else if `(bx, ny)` holds a brick: it is *hit*, `vy = -vy`, the ball stays. Else `by = ny`.\n")
    s.append("### Hitting a brick\n\nHits are processed through a FIFO queue that starts with the cell that was hit (marked *direct*). Take the first entry:\n\n"
             "* `.` (already gone): nothing.\n"
             "* `#`: nothing happens, but a *direct* hit reports `clang <x>,<y>` (a steel brick caught in an explosion is ignored silently).\n"
             "* `1`, `2`, `3`: the number goes down by one. If it is still positive: event `hit <x>,<y>`. If it reaches 0 the cell becomes `.`, `destroyed` grows, the score gains `10 * (the brick's hit points in the level)` and the event is `break <x>,<y>`.\n"
             "* `X`: the cell becomes `.`, `destroyed` grows, the score gains 10, event `boom <x>,<y>`, and the four neighbouring cells (inside the court) are appended to the queue (not direct) in the order up, down, left, right.\n\n"
             "A tick's events are listed in the order they happened, joined by `; `; a tick without any event is reported as `idle`.\n")
    s.append("## API (crate `cinder`, `src/lib.rs`)\n\n```rust\nuse cinder::Game;\nlet mut g = Game::new(level);          // level: &str, rows joined by '\\n'\ng.legal_moves() -> Vec<String>          // legal commands in any order; empty when the game is over\n"
             "g.step(cmd: &str) -> Result<String, String>   // Ok(events) for a legal command; Err(message), no change, otherwise\ng.score() -> u32\ng.status() -> &'static str             // \"playing\", \"won\" or \"lost\"\ng.render() -> String\n```\n")
    s.append(f"### `render()`\n\n{H} court lines of {W} characters, then a status line, joined by `\\n` (no trailing newline). In the court lines the paddle row shows `=` on the paddle's cells and `.` elsewhere; in the other rows the ball `o` "
             "is drawn over its cell (it is not drawn when the game is lost; when the game is won it stays where it is), every other cell shows its brick character. The status line is `score <score> lives <lives> speed <speed>` followed by "
             "` WON` or ` LOST` when the game is over. Example:\n")
    m = Model(("." * W + "\n") * 2 + "11" + "." * (W - 2) + "\n" + ("." * W + "\n") * (H - 4) + "." * W, r)
    m.step("R")
    s.append(f"```\n{m.render().replace(chr(92) + 'n', chr(10))}\n```\n")
    s.append("## Tests\n\n`cargo test --offline --quiet` replays the scenario files in `tests/data/` (`tests/adapter/mod.rs` shows how the API is called; the format is described at the top of `tests/scenarios.rs`).\n")
    return "\n".join(s)


def project(r: dict) -> dict[str, str]:
    return {"src/lib.rs": engine(r), "Cargo.toml": _kit.cargo_toml(PKG), ".gitignore": _kit.GITIGNORE[LANG]}


def _variants(n: int) -> list[dict]:
    plan = [
        dict(),
        dict(W=13, PW=5, SHRINK=1, STEP=4),
        dict(W=9, H=10, PW=3, SHRINK=1, LIVES=2, STEP=5, ENGLISH=False),
        dict(H=14, LIVES=4, STEP=3, ALT=False),
        dict(W=15, PW=6, SHRINK=2, STEP=8, ENGLISH=False, ALT=False),
    ]
    return [{**DEFAULT, **o} for o in plan[:n]]


@family("games-cinder-build", category="games", lang="rust", kind="greenfield", n=5,
        summary="build the Cinder grid-ball brick breaker: axis-by-axis ball physics, explosions via a queue, speed-ups, shrinking paddle")
def gen_build(rng, n):
    used: list[str] = []
    for i, r in enumerate(_variants(n)):
        sol = project(r)
        hidden = _kit.data_files(LANG, scripts(rng, r), sol, ADAPTER)
        for t in hidden.values():
            crosscheck(t, r)
        vis = _kit.data_files(LANG, {"examples": example_script(rng, r)}, sol, ADAPTER)
        crosscheck(next(iter(vis.values())), r)
        start = {"README.md": readme(r), "src/lib.rs": STUB, "Cargo.toml": sol["Cargo.toml"], ".gitignore": sol[".gitignore"], **_scen.check_files(LANG, ADAPTER), **vis}
        d = min(5, 3 + (r["SHRINK"] > 0) + (not r["ENGLISH"] and False) + (r["STEP"] <= 4))
        d = max(3, d)
        prompt = _kit.green_prompt(rng, game=GAME, blurb=f"a {r['W']}x{r['H']} brick breaker with explosive and steel bricks and an integer grid ball", file="src/lib.rs", verify=_scen.VERIFY[LANG], used=used)
        yield Task(slug=f"{i + 1:02d}-{r['W']}x{r['H']}-pw{r['PW']}" + ("-shrink" if r["SHRINK"] else ""), prompt=prompt, difficulty=d, start=start, hidden=hidden,
                   solution={"src/lib.rs": sol["src/lib.rs"]}, verify=_scen.VERIFY[LANG], timeout_s=300, tags=["breakout", "physics", "scenarios"], notes={"rules": r})


BUGS = [
    Bug("speed-step", "The ball speeds up too late",
        "The ball speeds up later than the rules say: after exactly the number of bricks that should trigger speed 2 it is still at speed 1, and speed 3 comes late too.",
        [("1 + (self.destroyed / SPEED_STEP).min(2)", "1 + (self.destroyed / (SPEED_STEP + 1)).min(2)")], difficulty=2),
    Bug("brick-points", "Strong bricks give the same points as weak ones",
        "Breaking a three-hit brick scores only 10, like a one-hit brick; the points should depend on the hit points the brick started with.",
        [("self.score += 10 * self.orig[cy][cx] as u32;", "self.score += 10;")], difficulty=1),
    Bug("explosion-order", "Explosions spread in the wrong order",
        "When explosive bricks sit next to each other the `boom` events of a chain come out in a different order than the README describes (up, down, left, right).",
        [("for (dx, dy) in [(0i32, -1i32), (0, 1), (-1, 0), (1, 0)] {", "for (dx, dy) in [(-1i32, 0i32), (1, 0), (0, -1), (0, 1)] {")], difficulty=3),
    Bug("english-edge", "The paddle steers the ball from too far in",
        "The ball changes direction when it lands on the second cell from the end of the paddle too, not only on the ends.",
        [("if x == self.px {\n                            self.vx = -1;\n                        } else if x == self.px + self.pw - 1 {", "if x <= self.px + 1 {\n                            self.vx = -1;\n                        } else if x + 2 >= self.px + self.pw {")], difficulty=3, rules=dict(ENGLISH=True, PW=5)),
    Bug("serve-parity", "Re-serves go the wrong way",
        "After losing a ball the next one is served in the wrong horizontal direction: it goes left when the README says right and vice versa.",
        [("self.vx = if !ALT_SERVE || self.lives % 2 == 1 { 1 } else { -1 };", "self.vx = if !ALT_SERVE || self.lives % 2 == 0 { 1 } else { -1 };")], difficulty=2, rules=dict(ALT=True)),
    Bug("paddle-bound", "The paddle can leave the court",
        "Keep pressing right and the paddle slides partly out of the court on the right, and `R` is still offered as legal.",
        [("if self.px + self.pw < W {", "if self.px + self.pw <= W {")], difficulty=2),
    Bug("won-explosives", "A court with only explosives left counts as cleared",
        "The game says WON while explosive bricks are still on the court; it only looks at the numbered bricks.",
        [("(b'1'..=b'3').contains(&c) || c == b'X'", "(b'1'..=b'3').contains(&c)")], difficulty=2),
    Bug("steel-breaks", "Steel bricks can be destroyed by the ball",
        "A steel brick disappears after being hit, and there is a `clang` event but the brick is gone afterwards.",
        [("b'#' => {\n                        if direct {\n                            ev.push(format!(\"clang {},{}\", cx, cy));\n                        }\n                    }", "b'#' => {\n                        if direct {\n                            ev.push(format!(\"clang {},{}\", cx, cy));\n                            self.grid[cy][cx] = b'.';\n                        }\n                    }")], difficulty=2),
    Bug("ceiling-row", "The ball bounces off the first brick row early",
        "The ball bounces off the ceiling one row too early: it never gets to row 0.",
        [("if ny < 0 {\n                self.vy = -self.vy;\n                ev.push(\"ceiling\".to_string());", "if ny <= 0 {\n                self.vy = -self.vy;\n                ev.push(\"ceiling\".to_string());")], difficulty=2),
    Bug("axis-order", "Corner hits behave differently",
        "When the ball hits a brick diagonally (a brick at the corner but neither neighbour solid) it passes straight through instead of... well, in the README the two axes are resolved one after the other, so such a hit can't happen; but shots into inner corners between two bricks bounce back the wrong way.",
        [("} else if self.solid(self.bx, ny) {\n                self.hit(self.bx as usize, ny as usize, ev);\n                self.vy = -self.vy;", "} else if self.solid(self.bx, ny) {\n                self.hit(self.bx as usize, ny as usize, ev);\n                self.vy = -self.vy;\n                self.vx = -self.vx;")], difficulty=3),
    Bug("shrink-floor", "The paddle shrinks below two cells",
        "After a few lost balls the paddle gets narrower than 2 cells (down to a single cell) although the rules say it never goes below 2.",
        [("self.pw = (self.pw.saturating_sub(SHRINK)).max(2);", "self.pw = (self.pw.saturating_sub(SHRINK)).max(1);")], difficulty=2, rules=dict(SHRINK=2, PW=4, LIVES=4)),
    Bug("lives-check", "The paddle shrinks after the last ball",
        "After the last ball is lost the paddle on the final board is narrower than it was when the ball was lost: it shrinks once more even though the game is over.",
        [("if self.lives == 0 {\n                        self.state = State::Lost;\n                    } else {", "if self.lives == 0 && self.destroyed > 1000 {\n                        self.state = State::Lost;\n                    } else {")], difficulty=3, rules=dict(SHRINK=1, LIVES=2)),
    Bug("destroyed-chain", "Bricks destroyed by explosions do not speed the ball up",
        "Explosion chains don't count towards the speed-up: the ball is slower than the README says after big explosions.",
        [("b'X' => {\n                        self.grid[cy][cx] = b'.';\n                        self.destroyed += 1;", "b'X' => {\n                        self.grid[cy][cx] = b'.';\n                        if direct {\n                            self.destroyed += 1;\n                        }")], difficulty=3),
]


def _fix_edits(b: Bug) -> Bug:
    return b


_B = {b.id: b for b in BUGS}
BUGS_ALL = BUGS + [
    _kit.combine(_B["brick-points"], _B["paddle-bound"], difficulty=3),
    _kit.combine(_B["explosion-order"], _B["destroyed-chain"], _B["won-explosives"], difficulty=4),
]


@family("games-cinder-fix", category="games", lang="rust", kind="fix", n=12,
        summary="hand-injected defects in the Cinder engine (physics axes, explosions, speed-ups, paddle rules, lives)")
def gen_fix(rng, n):
    used: list[str] = []
    cache = {}
    for k, bug in enumerate(BUGS_ALL[:n]):
        r = {**DEFAULT, **bug.rules}
        key = json.dumps(r, sort_keys=True)
        if key not in cache:
            sol = project(r)
            cache[key] = (sol, _kit.data_files(LANG, scripts(rng, r), sol, ADAPTER), _kit.data_files(LANG, {"examples": example_script(rng, r)}, sol, ADAPTER), readme(r))
        sol, hidden, vis, rd = cache[key]
        base = {**sol, "README.md": rd}
        tests = {**_scen.check_files(LANG, ADAPTER), **vis}
        ctx = {"files": ["src/lib.rs"], "verify": _scen.VERIFY[LANG]}
        yield _kit.bug_task(game=GAME, lang=LANG, base_files=base, tests=tests, hidden=hidden, bug=bug, ctx=ctx, rng=rng, used=used, k=k,
                            tags=["breakout", "physics"], timeout_s=300, extra_notes={"rules": r})


# ----------------------------------------------------------------------------------------------------- bot tournament

BOT_STUB = dd(r'''
    use crate::Game;

    /// The command to play now: "L", "R" or "S" (it is only called while the game is running).
    pub fn choose(game: &Game) -> &'static str {
        let _ = game;
        "S"
    }
''')

BOT_GOLD = dd(r'''
    use crate::{Game, H, W};

    /// Where will the ball come down? Let a clone play on until the ball is falling (the paddle stays put), then follow
    /// the falling diagonal with its wall bounces (bricks are above, so they can be ignored) and move the paddle there.
    pub fn choose(game: &Game) -> &'static str {
        let legal = game.legal_moves();
        let (px, pw) = game.paddle();
        let mut sim = game.clone();
        for _ in 0..80 {
            if sim.ball().3 > 0 || sim.step("S").is_err() {
                break;
            }
        }
        let (bx, by, vx, vy) = sim.ball();
        let mut x = bx;
        let mut dx = vx;
        if vy > 0 {
            for _ in 0..=((H as i32) - 2 - by) {
                let nx = x + dx;
                if nx < 0 || nx >= W as i32 {
                    dx = -dx;
                } else {
                    x = nx;
                }
            }
        }
        let target = x - (pw as i32) / 2;
        if (px as i32) < target && legal.iter().any(|m| m == "R") {
            "R"
        } else if (px as i32) > target && legal.iter().any(|m| m == "L") {
            "L"
        } else {
            "S"
        }
    }
''')

BOT_EXTRA = dd(r'''

        /// The ball as (x, y, vx, vy).
        pub fn ball(&self) -> (i32, i32, i32, i32) {
            (self.bx, self.by, self.vx, self.vy)
        }

        /// The paddle as (left column, width).
        pub fn paddle(&self) -> (usize, usize) {
            (self.px, self.pw)
        }

        /// Number of bricks that still have hit points (1, 2, 3 or X).
        pub fn bricks_left(&self) -> usize {
            self.remaining()
        }
''')

ARENA_RS = dd(r'''
    // Local arena: plays `cinder::bot::choose` on the sample levels and prints the fraction of bricks cleared.
    use cinder::{bot, Game};

    const LEVELS: [&str; @@N@@] = [
    @@LEVELS@@
    ];

    fn main() {
        let mut sum = 0.0;
        for (i, level) in LEVELS.iter().enumerate() {
            let mut g = Game::new(level);
            let total = g.bricks_left() as f64;
            for _ in 0..2500 {
                if g.status() != "playing" {
                    break;
                }
                let cmd = bot::choose(&g);
                if g.step(cmd).is_err() {
                    break; // an illegal command ends the game
                }
            }
            let cleared = (total - g.bricks_left() as f64) / total;
            println!("level {}: cleared {:.0}% ({}, score {})", i + 1, cleared * 100.0, g.status(), g.score());
            sum += cleared;
        }
        println!("average cleared {:.3}", sum / LEVELS.len() as f64);
    }
''')

SCORE_RS = dd(r'''
    use cinder::{bot, Game};

    const LEVELS: [&str; @@N@@] = [
    @@LEVELS@@
    ];
    const FLOOR: f64 = @@FLOOR@@;
    const GOAL: f64 = @@GOAL@@;

    fn main() {
        let mut sum = 0.0;
        for level in LEVELS.iter() {
            let mut g = Game::new(level);
            let total = g.bricks_left() as f64;
            for _ in 0..2500 {
                if g.status() != "playing" {
                    break;
                }
                let cmd = bot::choose(&g);
                if g.step(cmd).is_err() {
                    break;
                }
            }
            sum += (total - g.bricks_left() as f64) / total;
        }
        let avg = sum / LEVELS.len() as f64;
        let score = ((avg - FLOOR) / (GOAL - FLOOR)).max(0.0).min(1.0);
        println!("average cleared {:.3} over {} levels (full score from {:.2})", avg, LEVELS.len(), GOAL);
        println!("{{\"score\": {:.4}}}", score);
    }
''')

CINDER_BOT_VARIANTS = [
    dict(rules={}, floor=0.3, goal=0.6, d=3),
    dict(rules=dict(H=14, LIVES=4, STEP=3, ALT=False), floor=0.2, goal=0.8, d=3),
    dict(rules=dict(W=13, PW=5, SHRINK=0, STEP=5), floor=0.3, goal=0.48, d=3),
    dict(rules=dict(W=9, H=10, PW=4, SHRINK=0, STEP=6, ENGLISH=False), floor=0.35, goal=0.72, d=4),
]


def _rust_levels(levels: list[str]) -> str:
    return ",\n".join('    "' + lv.replace("\n", "\\n") + '"' for lv in levels) + ","


def bot_readme(r: dict, v: dict) -> str:
    return readme(r).replace("## Tests\n", dd(f'''
        ## Your task: a paddle controller

        `src/bot.rs` must define `pub fn choose(game: &Game) -> &'static str`, called before every tick while the game is running; it returns `"L"`, `"R"` or `"S"` (a command that is not legal ends the game). Besides the API above the engine has
        read-only helpers (the engine, `src/lib.rs`, is given and must not be edited): `game.clone()` (an independent copy: step the copy to look ahead), `game.ball() -> (x, y, vx, vy)`, `game.paddle() -> (left column, width)` and
        `game.bricks_left()` (bricks that still have hit points).

        `cargo run --offline --quiet --bin arena` plays your controller on a few sample levels and prints the fraction of bricks cleared. The check plays 8 other levels, at most 2500 ticks each (a level ends when the game is won or lost), and
        takes the average fraction of the bricks cleared (`1 - bricks left / bricks at the start`). The score is `clamp((average - {v["floor"]}) / ({v["goal"]} - {v["floor"]}), 0, 1)`; 1.0 needs an average of at least {v["goal"]}.

        ## Tests
    '''), 1)


@family("games-cinder-bot", category="games", lang="rust", kind="greenfield", n=4,
        summary="write a Cinder paddle controller (rust) scored by the bricks it clears on hidden levels (json-score)")
def gen_bot(rng, n):
    for i, v in enumerate(CINDER_BOT_VARIANTS[:n]):
        r = {**DEFAULT, **v["rules"]}
        sol = project(r)
        lib = sol["src/lib.rs"].replace("/// One game of Cinder.\npub struct Game {", "/// One game of Cinder.\n#[derive(Clone)]\npub struct Game {", 1)
        assert "#[derive(Clone)]\npub struct Game" in lib
        lib = lib.replace("use std::collections::VecDeque;\n", "use std::collections::VecDeque;\n\npub mod bot;\n", 1)
        marker = "    pub fn score(&self) -> u32 {"
        assert lib.count(marker) == 1
        lib = lib.replace(marker, textwrap.indent(BOT_EXTRA.strip("\n"), "    ") + "\n\n" + marker, 1)
        samples = [make_level(rng, r, rows=rng.choice([3, 4]), steel=(k % 2 == 1), boom=(k != 0)) for k in range(3)]
        graded = [make_level(rng, r, rows=rng.choice([3, 4, 5]), steel=(k % 2 == 1), boom=(k != 0)) for k in range(8)]
        files = {"src/lib.rs": lib, "src/bot.rs": BOT_STUB, "Cargo.toml": sol["Cargo.toml"], ".gitignore": sol[".gitignore"], "README.md": bot_readme(r, v),
                 "src/bin/arena.rs": ARENA_RS.replace("@@N@@", str(len(samples))).replace("@@LEVELS@@", _rust_levels(samples))}
        hidden = {"src/bin/score.rs": SCORE_RS.replace("@@N@@", str(len(graded))).replace("@@LEVELS@@", _rust_levels(graded)).replace("@@FLOOR@@", repr(float(v["floor"]))).replace("@@GOAL@@", repr(float(v["goal"])))}
        s0, s1, out = _kit.check_scores(start=files, hidden=hidden, solution={"src/bot.rs": BOT_GOLD}, verify="cargo run --offline --quiet --bin score", name=f"cinder-bot-{i}", timeout_s=300)
        voices = [
            "Write a paddle controller for Cinder in `src/bot.rs`: `choose` returns `L`, `R` or `S` each tick. README.md describes the game, the extra read-only helpers and how the share of bricks cleared on hidden levels is graded; `cargo run --offline --bin arena` shows how you do on samples.",
            "The Cinder bot just stays put, which clears a lot less than it could. Make `choose` in `src/bot.rs` actually return the ball: a clone of the game lets you simulate ahead. The grading is in README.md.",
            "I need a Cinder autoplayer. Mind the physics (README.md has the exact rules, including the ball speed-ups) because the naive 'follow the ball' idea performs badly. Implement `choose` in `src/bot.rs`.",
            "Implement the controller in `src/bot.rs` for this Cinder court. The score is the average fraction of bricks cleared over eight levels you don't see (details in README.md); `cargo run --offline --quiet --bin arena` plays three samples.",
        ]
        yield Task(slug=f"{i + 1:02d}-{r['W']}x{r['H']}-pw{r['PW']}", prompt=voices[i % len(voices)], difficulty=v["d"], start=files, hidden=hidden, solution={"src/bot.rs": BOT_GOLD},
                   verify="cargo run --offline --quiet --bin score", pass_mode="json-score", protected=["src/lib.rs", "src/bin/arena.rs"], timeout_s=300,
                   tags=["bot", "physics", "tournament"], notes={"rules": r, "gold": out.strip().splitlines()[-2], "stub_score": s0})


# ----------------------------------------------------------------------------------------------------- feature: command log and replay

REPLAY_EDITS = [
    ("    state: State,\n}", "    state: State,\n    level: String,\n    hist: Vec<u8>,\n}"),
    ("state: State::Playing,\n            };", "state: State::Playing,\n                level: level.to_string(),\n                hist: Vec::new(),\n            };"),
    ("let mut ev: Vec<String> = Vec::new();\n            match cmd {", "self.hist.push(cmd.as_bytes()[0]);\n            let mut ev: Vec<String> = Vec::new();\n            match cmd {"),
]

LOG_PLAIN = '''
    /// The accepted commands so far, one character each.
    pub fn log(&self) -> String {
        String::from_utf8(self.hist.clone()).unwrap()
    }

    /// A game on `level` after playing `log` (see README.md).
    pub fn replay(level: &str, log: &str) -> Result<Game, String> {
        let mut g = Game::new(level);
        for (i, c) in log.chars().enumerate() {
            g.step(&c.to_string()).map_err(|_| format!("bad command at tick {}", i))?;
        }
        Ok(g)
    }
'''

LOG_RLE = '''
    /// The accepted commands so far, run-length encoded.
    pub fn log(&self) -> String {
        let mut out = String::new();
        let mut i = 0;
        while i < self.hist.len() {
            let c = self.hist[i];
            let mut j = i;
            while j < self.hist.len() && self.hist[j] == c {
                j += 1;
            }
            out.push(c as char);
            if j - i > 1 {
                out.push_str(&(j - i).to_string());
            }
            i = j;
        }
        out
    }

    /// A game on `level` after playing the run-length encoded `log` (see README.md).
    pub fn replay(level: &str, log: &str) -> Result<Game, String> {
        let bytes = log.as_bytes();
        let mut cmds: Vec<u8> = Vec::new();
        let mut i = 0;
        while i < bytes.len() {
            let c = bytes[i];
            if c != b'L' && c != b'R' && c != b'S' {
                return Err(format!("bad log at {}", i));
            }
            i += 1;
            let start = i;
            while i < bytes.len() && bytes[i].is_ascii_digit() {
                i += 1;
            }
            let mut n = 1usize;
            if i > start {
                let digits = &log[start..i];
                if digits.starts_with('0') || digits.len() > 4 {
                    return Err(format!("bad log at {}", start));
                }
                n = digits.parse().unwrap();
                if n < 2 {
                    return Err(format!("bad log at {}", start));
                }
            }
            for _ in 0..n {
                cmds.push(c);
            }
        }
        let mut g = Game::new(level);
        for (k, c) in cmds.iter().enumerate() {
            g.step(&(*c as char).to_string()).map_err(|_| format!("illegal command at tick {}", k))?;
        }
        Ok(g)
    }
'''

LOG_FOOTER = '''
    /// The accepted commands so far followed by `|score:lives`.
    pub fn log(&self) -> String {
        format!("{}|{}:{}", String::from_utf8(self.hist.clone()).unwrap(), self.score, self.lives)
    }

    /// A game on `level` after playing `log` (see README.md).
    pub fn replay(level: &str, log: &str) -> Result<Game, String> {
        let (cmds, footer) = log.split_once('|').ok_or_else(|| "bad log".to_string())?;
        let (score, lives) = footer.split_once(':').ok_or_else(|| "bad log".to_string())?;
        let digits = |s: &str| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit());
        if !digits(score) || !digits(lives) {
            return Err("bad log".to_string());
        }
        let mut g = Game::new(level);
        for (i, c) in cmds.chars().enumerate() {
            g.step(&c.to_string()).map_err(|_| format!("bad command at tick {}", i))?;
        }
        if g.score.to_string() != score || g.lives.to_string() != lives {
            return Err("state mismatch".to_string());
        }
        Ok(g)
    }
'''

LOG_REWIND = LOG_PLAIN + '''
    /// Takes back the last `ticks` ticks.
    pub fn rewind(&mut self, ticks: usize) -> Result<(), String> {
        if ticks > self.hist.len() {
            return Err("cannot rewind past the start".to_string());
        }
        let keep = self.hist.len() - ticks;
        let log: String = self.hist[..keep].iter().map(|&b| b as char).collect();
        let level = self.level.clone();
        *self = Game::replay(&level, &log)?;
        Ok(())
    }
'''


def rle(moves: list[str]) -> str:
    out, i = "", 0
    while i < len(moves):
        j = i
        while j < len(moves) and moves[j] == moves[i]:
            j += 1
        out += moves[i] + (str(j - i) if j - i > 1 else "")
        i = j
    return out


def replay_adapter(variant: str) -> dict[str, str]:
    arms = {
        "plain": ("log", "replay"), "rle": ("log", "replay"), "footer": ("log", "replay"), "rewind": ("log", "replay", "rewind"),
    }[variant]
    text = dd(r'''
        // Maps scenario commands onto the engine API (the scenario runner is tests/scenarios.rs).
        use cinder::Game;

        pub struct Adapter {
            game: Option<Game>,
            level: String,
        }

        impl Adapter {
            pub fn new() -> Adapter {
                Adapter { game: None, level: String::new() }
            }

            pub fn run(&mut self, verb: &str, args: &str) -> String {
                match verb {
                    // new <level rows joined by |>
                    "new" => {
                        self.level = args.replace('|', "\n");
                        self.game = Some(Game::new(&self.level));
                        "ok".to_string()
                    }
                    // do <command>: the event text, or "illegal"
                    "do" => match self.game.as_mut().unwrap().step(args) {
                        Ok(ev) => ev,
                        Err(_) => "illegal".to_string(),
                    },
                    // sorted legal commands joined by "," ("-" when there are none)
                    "legal" => {
                        let mut m = self.game.as_ref().unwrap().legal_moves();
                        m.sort();
                        if m.is_empty() {
                            "-".to_string()
                        } else {
                            m.join(",")
                        }
                    }
                    "render" => self.game.as_ref().unwrap().render(),
                    // "<score> <status>"
                    "status" => {
                        let g = self.game.as_ref().unwrap();
                        format!("{} {}", g.score(), g.status())
                    }
                    // log: the command log of the game so far
                    "log" => self.game.as_ref().unwrap().log(),
                    // replay <log>: replace the game by the replayed one on the same level: "ok" or "error: <message>"
                    "replay" => match Game::replay(&self.level, args) {
                        Ok(g) => {
                            self.game = Some(g);
                            "ok".to_string()
                        }
                        Err(e) => format!("error: {}", e),
                    },
                    // reload: replay the current log into a new game: "same" or "different"
                    "reload" => {
                        let before = self.game.as_ref().unwrap().render();
                        let log = self.game.as_ref().unwrap().log();
                        match Game::replay(&self.level, &log) {
                            Ok(g) => {
                                let same = g.render() == before && g.log() == log;
                                self.game = Some(g);
                                if same { "same".to_string() } else { "different".to_string() }
                            }
                            Err(e) => format!("error: {}", e),
                        }
                    }
@@REWIND@@                    _ => panic!("unknown verb {}", verb),
                }
            }
        }
    ''')
    rewind = '''                    // rewind <n>: take back the last n ticks: "ok" or "error: <message>"
                    "rewind" => match self.game.as_mut().unwrap().rewind(args.parse().unwrap()) {
                        Ok(()) => "ok".to_string(),
                        Err(e) => format!("error: {}", e),
                    },
'''
    return {"tests/adapter/mod.rs": text.replace("@@REWIND@@", rewind if variant == "rewind" else "")}


def _log_for(variant: str, moves: list[str], r: dict, level: str) -> str:
    if variant == "rle":
        return rle(moves)
    if variant == "footer":
        m = Model(level, r)
        for x in moves:
            m.step(x)
        return "".join(moves) + f"|{m.score}:{m.lives}"
    return "".join(moves)


def replay_scripts(rng, variant: str, r: dict) -> dict[str, str]:
    parts = []
    for i in range(4):
        lv = make_level(rng, r, rows=rng.choice([3, 4]), steel=(i % 2 == 1), boom=True)
        row = lv.replace("\n", "|")
        mv = tracking_moves(rng, lv, r, 140 + 60 * i, noise=[2, 10, 4, 25][i])
        lines = [f"# scenario log and replay {i + 1}", f"> new {row}"] + [f"> do {m}" for m in mv[: len(mv) // 2]] + ["> log", "> reload", "> render"] + [f"> do {m}" for m in mv[len(mv) // 2:]] + ["> log", "> reload", "> status", "> render"]
        parts.append("\n".join(lines))
        full = _log_for(variant, mv, r, lv)
        lines = [f"# scenario replay a stored game {i + 1}", f"> new {row}", f"> replay {full}", "> render", "> log", "> status", "> legal"]
        if variant == "rewind":
            lines = [f"# scenario rewind {i + 1}", f"> new {row}"] + [f"> do {m}" for m in mv[:90]] + ["> rewind 0", "> log", "> rewind 7", "> render", "> log", "> do S", "> log", "> rewind 30", "> render", "> rewind 100000", "> rewind 59", "> render", "> rewind 1", "> log", "> status"]
        parts.append("\n".join(lines))
    lv = make_level(rng, r, rows=3, steel=False, boom=True)
    row = lv.replace("\n", "|")
    mv = tracking_moves(rng, lv, r, 60, noise=3)
    good = _log_for(variant, mv, r, lv)
    bad: list[str] = ["", "X", "L R", "l", "LLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLL"]
    if variant == "plain":
        bad += [good + "X", good[:20] + "Q" + good[20:], "S" * 40]
    elif variant == "rle":
        bad += [good + "X", "L1", "L0", "L01", "S2R", "R" + "9" * 5, "L2S3R10X", "2L", "LL" + "9999", "S0R", "R3" + "L"]
    elif variant == "footer":
        bad += [good + "X", good.split("|")[0], good.replace("|", ":"), good.split("|")[0] + "|1:2", good.split("|")[0] + "|x:y", good.split("|")[0] + "|", good + "|1:1", "LLL|0:" + str(r["LIVES"]), good.split("|")[0][:-1] + "|" + good.split("|")[1]]
    else:
        bad += [good + "X", "S" * 40]
    cases = [f"# scenario bad logs\n> new {row}"]
    for b in [good] + bad:
        cases += [f"> replay {b}", "> render"]
    parts.append("\n".join(cases))
    return {"hidden_replay": "\n".join(parts) + "\n"}


REPLAY_VARIANTS = [
    dict(key="plain", d=3, ask="Add a command log and a replay to the Cinder engine: `Game::log()` gives every accepted command as one character, `Game::replay(level, log)` rebuilds a game from a level and a log. README.md has the exact format and the error texts.",
         text=LOG_PLAIN),
    dict(key="rle", d=4, ask="Cinder games should be storable as short strings, so the log is run-length encoded. Implement `Game::log()` and `Game::replay(level, log)` as specified in the new README.md section, including what counts as a malformed log and the exact error texts.",
         text=LOG_RLE),
    dict(key="footer", d=4, ask="Store Cinder games as `<commands>|<score>:<lives>` so that a replay can check itself. Add `Game::log()` and `Game::replay(level, log)` following the new README.md section; every failure has its own exact message.",
         text=LOG_FOOTER),
    dict(key="rewind", d=4, ask="Add an undo-by-ticks to Cinder: `Game::rewind(n)` takes back the last n ticks (by replaying the log from the start). It needs a command log and `Game::replay(level, log)`; all of it is specified in the new README.md section.",
         text=LOG_REWIND),
]


def replay_readme(key: str) -> str:
    base = ("`Game::log()` returns the *command log*: the accepted commands of this game so far (`L`, `R`, `S`, in order; rejected commands are not logged) and `Game::replay(level, log)` returns a new game on `level` after playing the commands of `log` one tick at a time "
            "(`level` is the same kind of text that `Game::new` takes). The scenario adapter has the commands `log`, `replay <log>` (on the level of the last `new`) and `reload`.\n\n")
    if key == "plain":
        return ("## Feature to add: command log and replay\n\n" + base + "The log is the commands as characters with nothing between them (`LLSR`); a fresh game has the empty log. `replay` plays each character as a command: the first one that the engine does not accept (any other character, or "
                "a command that is illegal at that moment, e.g. any command after the game is over) makes it return `Err(\"bad command at tick <i>\")` with `i` the 0-based position of that character. `replay(level, \"\")` is a fresh game; "
                "the replayed game's `log()` equals the log it was built from.\n")
    if key == "rle":
        return ("## Feature to add: run-length encoded command log\n\n" + base + "The log is run-length encoded: every maximal run of the same command is written as the command letter, followed by the run length in decimal if it is 2 or more "
                "(`L3SR2`: three `L`, one `S`, two `R`). A fresh game has the empty log. `replay` accepts exactly these strings: a letter `L`, `R` or `S`, optionally followed by a count of 2 to 9999 written without leading zeros or sign; "
                "adjacent runs of the same letter are fine (`L2L3` means five `L`). Anything else returns `Err(\"bad log at <i>\")` where `i` is the 0-based byte index of the offending character (a letter that is not `L`, `R` or `S`; "
                "or the *first digit* of a bad count: `0`, `1`, a count starting with 0, or more than 4 digits). The whole text is checked this way first; only then are the commands played, and the first command that is illegal "
                "when it is played returns `Err(\"illegal command at tick <i>\")` with `i` the 0-based index of that command in the expanded sequence.\n")
    if key == "footer":
        return ("## Feature to add: self-checking command log\n\n" + base + "The log is the commands as characters, then `|`, then the score and the lives left, separated by `:`: for example `LLSR|30:3`. `replay` checks the text in this order and returns `Err` with exactly the given message: "
                "no `|` or a footer that is not `<digits>:<digits>` (both numbers non-empty, digits only; only the first `|` splits the text): `bad log`; a command that is not accepted when it is played: `bad command at tick <i>` (0-based); "
                "finally, if the replayed game's score or lives differ from the footer: `state mismatch`.\n")
    return ("## Feature to add: rewind\n\n" + base + "The log is the commands as characters with nothing between them (`LLSR`); `replay` returns `Err(\"bad command at tick <i>\")` (`i` the 0-based position) for the first command that is not accepted. "
            "`Game::rewind(&mut self, ticks: usize) -> Result<(), String>` takes back the last `ticks` accepted ticks: afterwards the game is exactly what a replay of the log without those last commands would give (the log is shorter by `ticks`, "
            "the ball, the paddle, bricks, lives and score are as they were then). `rewind(0)` changes nothing. If `ticks` is more than the number of ticks played the result is `Err(\"cannot rewind past the start\")` and nothing changes.\n")


@family("games-cinder-replay", category="games", lang="rust", kind="feature", n=4,
        summary="add a command log with replay (plain, run-length encoded, self-checking) or rewind-by-replay to the Cinder engine")
def gen_replay(rng, n):
    for i, v in enumerate(REPLAY_VARIANTS[:n]):
        key = v["key"]
        r = {**DEFAULT, **(dict(SHRINK=1) if key == "rewind" else {})}
        base = project(r)
        src = _kit.apply_bug(base["src/lib.rs"], Bug("replay", "", "", REPLAY_EDITS))
        assert src.rstrip().endswith("}")
        body = src.rstrip("\n")
        body = body[: body.rindex("}")] + v["text"].lstrip("\n").replace("\n    ", "\n    ") .join(["", ""]) if False else body
        lib = body[: body.rindex("}")].rstrip("\n") + "\n" + v["text"].rstrip("\n") + "\n}\n"
        adapter = replay_adapter(key)
        sol = {"src/lib.rs": lib, "Cargo.toml": base["Cargo.toml"], ".gitignore": base[".gitignore"]}
        hid_scripts = {**scripts(rng, r), **replay_scripts(rng, key, r)}
        hidden = _kit.data_files(LANG, hid_scripts, sol, adapter)
        lv = make_level(rng, r, rows=3, steel=True, boom=True)
        ex = (f"# scenario log\n> new {lv.replace(chr(10), '|')}\n> do S\n> do R\n> do R\n> do S\n> log\n> reload\n> render\n> replay " + _log_for(key, ["S", "R", "R", "S", "L"], r, lv) + "\n> render\n> replay Q\n")
        vis = _kit.data_files(LANG, {"examples": example_script(rng, r), "feature": ex}, sol, adapter)
        start = {"README.md": readme(r).replace("## Tests\n", replay_readme(key) + "\n## Tests\n"), "src/lib.rs": base["src/lib.rs"], "Cargo.toml": base["Cargo.toml"], ".gitignore": base[".gitignore"],
                 **_scen.check_files(LANG, adapter), **vis}
        yield Task(slug=f"{i + 1:02d}-{key}", prompt=v["ask"] + (" Keep the existing behaviour exactly as it is." if i % 2 else ""), difficulty=v["d"], start=start, hidden=hidden, solution={"src/lib.rs": lib},
                   verify=_scen.VERIFY[LANG], timeout_s=300, tags=["breakout", "replay", "feature"], notes={"feature": key, "rules": r})
