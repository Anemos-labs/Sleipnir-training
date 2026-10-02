"""Coil (c): a snake on a torus whose bites sever the body into stones, with peppers that shrink the snake and a 16-bit LCG.
Build and fix tasks; a python model cross-checks the reference engine and plays greedy games."""
from __future__ import annotations

import json

from fx import Task, dd, family

from . import _kit, _scen
from ._kit import Bug

LANG = "c"
GAME = "Coil"
DEFAULT = dict(W=10, H=8, WRAP=1, BITE=1, PEPPER=4, LEN=3)


def header(r: dict) -> str:
    return dd(f'''
        /* ---- house rules for this meadow (they are part of the specification, see README.md) ---- */
        #define W {r["W"]}
        #define H {r["H"]}
        #define WRAP {r["WRAP"]}
        #define BITE_SEVERS {r["BITE"]}
        #define PEPPER_EVERY {r["PEPPER"]}
        #define START_LEN {r["LEN"]}
        /* ------------------------------------------------------------------------------------------ */
    ''')


HEADER_H = dd(r'''
    #ifndef COIL_H
    #define COIL_H

    #include <stddef.h>

    /* Coil: a snake game on a grid. The rules and the API are described in README.md. */
    typedef struct Coil Coil;

    /* A new game; the generator is seeded with `seed`. Release with coil_free. */
    Coil *coil_new(unsigned seed);
    void coil_free(Coil *g);

    /* Writes the legal moves ("U", "D", "L", "R") separated by commas, in any order, into out ("" when there are none)
       and returns how many there are. */
    int coil_legal(const Coil *g, char *out, size_t cap);

    /* Plays a move. Returns 0 and writes the event text into event, or returns -1 (nothing changes, event is untouched)
       when the move is not legal. */
    int coil_apply(Coil *g, const char *move, char *event, size_t cap);

    /* Writes the board text (see README.md) into out. */
    void coil_render(const Coil *g, char *out, size_t cap);

    int coil_score(const Coil *g);

    /* 1 when the game has ended (crash or all cells used), else 0. */
    int coil_over(const Coil *g);

    #endif
''')

BODY = dd(r'''
    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>

    #include "coil.h"

    #define MAXLEN (W * H)

    static const int DR[4] = {-1, 1, 0, 0};
    static const int DC[4] = {0, 0, -1, 1};
    static const char LETTERS[5] = "UDLR";

    struct Coil {
        int sr[MAXLEN + 1];
        int sc[MAXLEN + 1];
        int len;
        int dir;
        char stone[H][W];
        int fr;
        int fc;
        int fkind;
        int foods;
        unsigned state;
        int score;
        int tick;
        int status; /* 0 playing, 1 crashed, 2 won */
    };

    static int next_random(Coil *g) {
        g->state = (g->state * 25173u + 13849u) & 0xFFFFu;
        return (int)g->state;
    }

    static void spawn_food(Coil *g) {
        char occupied[H][W];
        int empty = 0;
        memset(occupied, 0, sizeof occupied);
        for (int i = 0; i < g->len; i++) occupied[g->sr[i]][g->sc[i]] = 1;
        for (int r = 0; r < H; r++)
            for (int c = 0; c < W; c++)
                if (!occupied[r][c] && !g->stone[r][c]) empty++;
        if (empty == 0) {
            g->status = 2;
            g->fr = -1;
            g->fc = -1;
            return;
        }
        int k = next_random(g) % empty;
        for (int r = 0; r < H; r++) {
            for (int c = 0; c < W; c++) {
                if (!occupied[r][c] && !g->stone[r][c]) {
                    if (k == 0) {
                        g->fr = r;
                        g->fc = c;
                    }
                    k--;
                }
            }
        }
        g->foods++;
        g->fkind = (PEPPER_EVERY > 0 && g->foods % PEPPER_EVERY == 0) ? 1 : 0;
    }

    Coil *coil_new(unsigned seed) {
        Coil *g = calloc(1, sizeof(Coil));
        if (!g) return NULL;
        g->state = seed & 0xFFFFu;
        g->len = START_LEN;
        for (int i = 0; i < START_LEN; i++) {
            g->sr[i] = H / 2;
            g->sc[i] = W / 2 - i;
        }
        g->dir = 3;
        spawn_food(g);
        return g;
    }

    void coil_free(Coil *g) {
        free(g);
    }

    static int dir_index(const char *move) {
        if (!move || move[0] == 0 || move[1] != 0) return -1;
        for (int d = 0; d < 4; d++)
            if (LETTERS[d] == move[0]) return d;
        return -1;
    }

    static int opposite(int d) {
        return d ^ 1;
    }

    int coil_legal(const Coil *g, char *out, size_t cap) {
        int n = 0;
        size_t used = 0;
        if (cap > 0) out[0] = 0;
        if (g->status != 0) return 0;
        for (int d = 0; d < 4; d++) {
            if (d == opposite(g->dir)) continue;
            if (used + 2 >= cap) break;
            if (n > 0) out[used++] = ',';
            out[used++] = LETTERS[d];
            out[used] = 0;
            n++;
        }
        return n;
    }

    int coil_apply(Coil *g, const char *move, char *event, size_t cap) {
        int d = dir_index(move);
        if (d < 0 || g->status != 0 || d == opposite(g->dir)) return -1;
        int nr = g->sr[0] + DR[d];
        int nc = g->sc[0] + DC[d];
        char ev[256];
        ev[0] = 0;
        g->tick++;
        if (WRAP) {
            nr = (nr + H) % H;
            nc = (nc + W) % W;
        } else if (nr < 0 || nr >= H || nc < 0 || nc >= W) {
            g->status = 1;
            snprintf(event, cap, "crash wall");
            return 0;
        }
        if (g->stone[nr][nc]) {
            g->status = 1;
            snprintf(event, cap, "crash stone");
            return 0;
        }
        int hit = -1;
        for (int i = 1; i < g->len; i++) {
            if (g->sr[i] == nr && g->sc[i] == nc) {
                hit = i;
                break;
            }
        }
        if (hit == g->len - 1) hit = -1; /* the tail moves away first */
        g->dir = d;
        if (hit >= 1) {
            if (!BITE_SEVERS) {
                g->status = 1;
                snprintf(event, cap, "crash body");
                return 0;
            }
            int cut = g->len - 1 - hit;
            for (int i = hit + 1; i < g->len; i++) g->stone[g->sr[i]][g->sc[i]] = 1;
            for (int i = hit; i > 0; i--) {
                g->sr[i] = g->sr[i - 1];
                g->sc[i] = g->sc[i - 1];
            }
            g->sr[0] = nr;
            g->sc[0] = nc;
            g->len = hit + 1;
            g->score = g->score >= cut ? g->score - cut : 0;
            snprintf(event, cap, "bite %d", cut);
            return 0;
        }
        int eats = (nr == g->fr && nc == g->fc);
        int apple = eats && g->fkind == 0;
        for (int i = g->len; i > 0; i--) {
            g->sr[i] = g->sr[i - 1];
            g->sc[i] = g->sc[i - 1];
        }
        g->sr[0] = nr;
        g->sc[0] = nc;
        if (apple) {
            g->len++;
            g->score += 1;
            snprintf(ev, sizeof ev, "ate apple +1");
        } else if (eats) {
            int before = g->len;
            g->len = g->len > 4 ? g->len - 2 : 2;
            g->score += 3;
            snprintf(ev, sizeof ev, "ate pepper +3 shrink %d", before - g->len);
        } else {
            snprintf(event, cap, "move");
            return 0;
        }
        spawn_food(g);
        if (g->status == 2) {
            snprintf(event, cap, "%s; won", ev);
        } else {
            snprintf(event, cap, "%s; food %d,%d %s", ev, g->fr, g->fc, g->fkind ? "pepper" : "apple");
        }
        return 0;
    }

    void coil_render(const Coil *g, char *out, size_t cap) {
        size_t n = 0;
        for (int r = 0; r < H; r++) {
            for (int c = 0; c < W; c++) {
                char ch = '.';
                if (g->stone[r][c]) ch = '#';
                if (r == g->fr && c == g->fc) ch = g->fkind ? '!' : '*';
                for (int i = g->len - 1; i >= 0; i--)
                    if (g->sr[i] == r && g->sc[i] == c) ch = i == 0 ? '@' : 'o';
                if (n + 2 < cap) out[n++] = ch;
            }
            if (n + 2 < cap) out[n++] = '\n';
        }
        out[n] = 0;
        snprintf(out + n, cap - n, "score %d len %d tick %d%s", g->score, g->len, g->tick, g->status == 1 ? " GAME OVER" : g->status == 2 ? " WON" : "");
    }

    int coil_score(const Coil *g) {
        return g->score;
    }

    int coil_over(const Coil *g) {
        return g->status != 0;
    }
''')


def engine(r: dict) -> str:
    inc, rest = BODY.split('#include "coil.h"\n', 1)
    return inc + '#include "coil.h"\n\n' + header(r) + rest


STUB = dd(r'''
    #include <stdlib.h>
    #include <string.h>

    #include "coil.h"

    /* Coil: implement the API of coil.h as described in README.md. */

    Coil *coil_new(unsigned seed) {
        (void)seed;
        return NULL;
    }

    void coil_free(Coil *g) {
        (void)g;
    }

    int coil_legal(const Coil *g, char *out, size_t cap) {
        (void)g;
        if (cap > 0) out[0] = 0;
        return 0;
    }

    int coil_apply(Coil *g, const char *move, char *event, size_t cap) {
        (void)g;
        (void)move;
        (void)event;
        (void)cap;
        return -1;
    }

    void coil_render(const Coil *g, char *out, size_t cap) {
        (void)g;
        if (cap > 0) out[0] = 0;
    }

    int coil_score(const Coil *g) {
        (void)g;
        return 0;
    }

    int coil_over(const Coil *g) {
        (void)g;
        return 1;
    }
''')

ADAPTER = {"tests/adapter.c": dd(r'''
    /* Maps scenario commands onto the engine API (the scenario runner is tests/test_main.c). */
    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>

    #include "adapter.h"
    #include "coil.h"

    static Coil *game;

    void adapter_reset(void) {
        if (game) coil_free(game);
        game = NULL;
    }

    void adapter_run(const char *verb, const char *args, char *out, size_t cap) {
        if (strcmp(verb, "new") == 0) { /* new <seed> */
            adapter_reset();
            game = coil_new((unsigned)strtoul(args, NULL, 10));
            snprintf(out, cap, "ok");
        } else if (strcmp(verb, "do") == 0) { /* do <move>: the event text, or "illegal" */
            char ev[512];
            if (coil_apply(game, args, ev, sizeof ev) == 0) snprintf(out, cap, "%s", ev);
            else snprintf(out, cap, "illegal");
        } else if (strcmp(verb, "legal") == 0) { /* sorted legal moves joined by "," ("-" when there are none) */
            char buf[64];
            size_t n = 0;
            coil_legal(game, buf, sizeof buf);
            out[0] = 0;
            for (const char *p = "DLRU"; *p; p++) {
                if (strchr(buf, *p)) {
                    if (n > 0) out[n++] = ',';
                    out[n++] = *p;
                    out[n] = 0;
                }
            }
            if (n == 0) snprintf(out, cap, "-");
        } else if (strcmp(verb, "render") == 0) {
            coil_render(game, out, cap);
        } else if (strcmp(verb, "status") == 0) { /* "<score> <over>" */
            snprintf(out, cap, "%d %s", coil_score(game), coil_over(game) ? "yes" : "no");
        } else {
            snprintf(out, cap, "unknown verb %s", verb);
        }
    }
''')}


# ----------------------------------------------------------------------------------------------------- python model

class Model:
    def __init__(self, seed: int, r: dict):
        self.r = r
        W, H = r["W"], r["H"]
        self.stone = set()
        self.state = seed & 0xFFFF
        self.body = [(H // 2, W // 2 - i) for i in range(r["LEN"])]
        self.dir = "R"
        self.score = self.tick = 0
        self.foods = 0
        self.status = 0
        self.food = None
        self.kind = 0
        self.spawn()

    def nxt(self):
        self.state = (self.state * 25173 + 13849) & 0xFFFF
        return self.state

    def spawn(self):
        W, H = self.r["W"], self.r["H"]
        free = [(y, x) for y in range(H) for x in range(W) if (y, x) not in self.body and (y, x) not in self.stone]
        if not free:
            self.status = 2
            self.food = None
            return
        self.food = free[self.nxt() % len(free)]
        self.foods += 1
        self.kind = 1 if (self.r["PEPPER"] > 0 and self.foods % self.r["PEPPER"] == 0) else 0

    OPP = {"U": "D", "D": "U", "L": "R", "R": "L"}
    VEC = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}

    def legal(self):
        return [] if self.status else [m for m in "UDLR" if m != self.OPP[self.dir]]

    def apply(self, mv):
        W, H = self.r["W"], self.r["H"]
        dy, dx = self.VEC[mv]
        ny, nx = self.body[0][0] + dy, self.body[0][1] + dx
        self.tick += 1
        if self.r["WRAP"]:
            ny, nx = ny % H, nx % W
        elif not (0 <= ny < H and 0 <= nx < W):
            self.status = 1
            return "crash wall"
        if (ny, nx) in self.stone:
            self.status = 1
            return "crash stone"
        hit = next((i for i in range(1, len(self.body)) if self.body[i] == (ny, nx)), -1)
        if hit == len(self.body) - 1:
            hit = -1
        self.dir = mv
        if hit >= 1:
            if not self.r["BITE"]:
                self.status = 1
                return "crash body"
            cut = len(self.body) - 1 - hit
            for c in self.body[hit + 1:]:
                self.stone.add(c)
            self.body = [(ny, nx)] + self.body[:hit]
            self.score = self.score - cut if self.score >= cut else 0
            return "bite %d" % cut
        eats = (ny, nx) == self.food
        apple = eats and self.kind == 0
        self.body = [(ny, nx)] + (self.body if apple else self.body[:-1])
        if apple:
            self.score += 1
            ev = "ate apple +1"
        elif eats:
            before = len(self.body)
            if len(self.body) > 4:
                self.body = self.body[:-2]
            else:
                self.body = self.body[:2]
            self.score += 3
            ev = "ate pepper +3 shrink %d" % (before - len(self.body))
        else:
            return "move"
        self.spawn()
        if self.status == 2:
            return ev + "; won"
        return "%s; food %d,%d %s" % (ev, self.food[0], self.food[1], "pepper" if self.kind else "apple")

    def render(self):
        W, H = self.r["W"], self.r["H"]
        rows = []
        for y in range(H):
            row = ""
            for x in range(W):
                ch = "#" if (y, x) in self.stone else "."
                if (y, x) == self.food:
                    ch = "!" if self.kind else "*"
                if (y, x) in self.body:
                    ch = "@" if self.body[0] == (y, x) else "o"
                row += ch
            rows.append(row)
        return "\\n".join(rows + ["score %d len %d tick %d%s" % (self.score, len(self.body), self.tick, " GAME OVER" if self.status == 1 else " WON" if self.status == 2 else "")])


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
                got = f"{m.score} {'yes' if m.status else 'no'}"
                assert got == want, f"status disagree {got!r} vs {want!r}"
            elif verb == "render":
                assert m.render() == want, f"render disagree:\n{m.render()}\n{want}"
            cmd = None


def greedy_moves(rng, seed: int, r: dict, ticks: int, careless: int) -> list[str]:
    """A snake that walks to the food (shortest wrapped path), sometimes carelessly into its own body."""
    W, H = r["W"], r["H"]
    m = Model(seed, r)
    out = []
    for _ in range(ticks):
        if m.status:
            break
        legal = m.legal()
        scored = []
        for mv in legal:
            dy, dx = m.VEC[mv]
            ny, nx = m.body[0][0] + dy, m.body[0][1] + dx
            if r["WRAP"]:
                ny, nx = ny % H, nx % W
            if not (0 <= ny < H and 0 <= nx < W):
                scored.append((10_000, rng.random(), mv))
                continue
            bad = ((ny, nx) in m.stone) * 1000 + ((ny, nx) in m.body[1:-1]) * (1 if rng.randrange(100) < careless else 500)
            fy, fx = m.food if m.food else (0, 0)
            ddy, ddx = abs(ny - fy), abs(nx - fx)
            if r["WRAP"]:
                ddy, ddx = min(ddy, H - ddy), min(ddx, W - ddx)
            scored.append((bad + ddy + ddx, rng.random(), mv))
        mv = min(scored)[2]
        m.apply(mv)
        out.append(mv)
    return out


def bite_sequences(rng, r: dict, count: int = 3) -> list[tuple[int, list[str]]]:
    """Random games (python model) that end a prefix with a bite that costs more than the whole score."""
    out = []
    for sd in range(1, 4000):
        m = Model(sd, r)
        moves = []
        for _ in range(120):
            if m.status:
                break
            legal = m.legal()
            mv = rng.choice(legal)
            before = m.score
            ev = m.apply(mv)
            moves.append(mv)
            if ev.startswith("bite"):
                if int(ev.split()[1]) > before:
                    out.append((sd, moves + [rng.choice(m.legal()) for _ in range(0)]))
                break
        if len(out) >= count:
            break
    return out


def scripts(rng, r: dict) -> dict[str, str]:
    parts = []
    if r["BITE"]:
        for i, (sd, mv) in enumerate(bite_sequences(rng, r)):
            parts.append(f"# scenario early bite {i + 1}\n> new {sd}\n" + "\n".join(f"> do {m}" for m in mv) + "\n> render\n> status\n> legal")
    for i, sd in enumerate((1, 2, 3, 4, 5, 65535, 65536, 4294967295)):
        mv = greedy_moves(rng, sd, r, 260, careless=[0, 30, 60][i % 3])
        parts.append(f"# scenario greedy {i + 1} seed {sd}\n> new {sd}\n> render\n" + "\n".join(f"> do {m}" + ("\n> render" if k % 13 == 12 else "") for k, m in enumerate(mv)) + "\n> render\n> status\n> legal")
    for i, sd in enumerate((7, 8, 9, 10)):
        parts.append(f"# scenario random {i + 1}\n> new {sd}\n~ rand 400 {sd * 3} every=7 emit=render,legal,status junk=X|u|UU|0|Up|")
    parts.append("# scenario reverse and walls\n> new 3\n> do L\n> legal\n> do U\n> do D\n> do R\n> do R\n> do R\n> do R\n> do R\n> do R\n> render\n> do R\n> do R\n> do R\n> do R\n> render\n> status\n> legal")
    return {"hidden_games": "\n".join(parts) + "\n"}


def example_script() -> str:
    return dd('''
        # scenario opening
        > new 1
        > render
        > legal
        > do L
        > do U
        > do R
        > render
        # scenario a few moves
        > new 9
        ~ rand 15 3 emit=render,status
    ''')


def readme(r: dict) -> str:
    W, H = r["W"], r["H"]
    s = []
    s.append("# Coil\n\nA snake game on a grid with a twist: a snake that bites itself is not dead, it is *severed*. The engine is a small C library: an opaque `Coil` object, a list of legal moves and exact text for every reply.\n")
    s.append(f"## The meadow\n\nThe grid has {H} rows and {W} columns, `(row, col)` from the top left, row-major. " + (
        "The meadow is a *torus*: stepping off one edge brings the head in on the opposite edge." if r["WRAP"] else "The edges are walls: stepping off the grid is a crash.") +
        f" Cells can hold: empty ground, a segment of the snake (segment 0 is the *head*), a *stone* (permanent), and the one piece of *food* (an apple or a pepper).\n")
    s.append(f"## Start\n\nThe snake has {r['LEN']} segments in a row: segment `i` is at row `{H // 2}`, column `{W // 2} - i` (so the head is at column {W // 2} and the body extends to the left). Its direction is `R`. "
             "Score 0, tick 0. Then the first food is placed (below).\n")
    s.append("## Randomness and food\n\nA 16-bit generator: `state = (state * 25173 + 13849) mod 65536`; `coil_new(seed)` starts with `state = seed mod 65536` (seed is an `unsigned`); a call to `next()` updates the state and returns the new state.\n\n"
             "To place food: list the cells that hold no snake segment and no stone in row-major order. If there are none the game is *won* (no food). Otherwise `k = next() mod (number of free cells)` picks the `k`-th free cell (0-based) "
             f"and the food counter grows by one (the first food is number 1). Food number `n` is a *pepper* " + (f"when `n` is a multiple of {r['PEPPER']}" if r["PEPPER"] else "never (there are no peppers on this meadow)") + ", an *apple* otherwise. `next()` is called only when food is placed.\n")
    bite = ("*Bite*: the head enters a segment `s[i]` of its own body (`i >= 1`, not the tail, see above). The snake is severed: the segments *behind* the bitten one (`s[i+1]` to the tail, `cut` of them, at least 1) turn into stones "
            "on the cells they occupied, the head takes the bitten cell, and the snake continues as the new head followed by the old `s[0] ... s[i-1]` (its new length is `i + 1`). The score drops by `cut` but not below 0. Event `bite <cut>`. "
            "Nothing is eaten and no food is placed (even if the food would be somewhere on that path it is not affected)."
            if r["BITE"] else "*Bite*: the head enters a segment of its own body (`i >= 1`, not the tail, see above): crash, event `crash body`.")
    s.append("## Moves\n\nA move is one of the strings `U`, `D`, `L`, `R` (up = row-1, down = row+1, left = col-1, right = col+1; upper case, exactly one character). The reverse of the current direction is illegal, and so is every move "
             "once the game is over. Legal moves: the other three directions. A legal move is processed as follows; the tick counter grows by 1 for every legal move (also for a fatal one). Let `t` be the cell the head steps to"
             + (" (with wrap-around)." if r["WRAP"] else " (outside the grid: crash, event `crash wall`; the snake stays).") + "\n")
    rules = [
        "A stone on `t`: crash, event `crash stone`; the snake does not move and the game is over.",
        "*Tail rule*: the tail segment leaves its cell during a move, so stepping onto the cell of the current *tail* is an ordinary move (not a bite) — the snake follows its own tail.",
        bite,
        "Otherwise the head moves to `t` and every segment follows (the old tail cell is freed); the direction becomes the move. If `t` holds the food it is eaten: "
        "an *apple* is eaten: the snake keeps its tail cell (length +1), score +1, event `ate apple +1`. "
        + ("A *pepper*: the snake moves normally and then loses segments from the tail: if its length is above 4 it drops by exactly 2, otherwise it becomes 2; score +3, event `ate pepper +3 shrink <n>` where `n` is the number of segments lost beyond the normal move. " if r["PEPPER"] else "")
        + "After eating, new food is placed and `; food <row>,<col> <apple|pepper>` is appended to the event; if no free cell is left the snake has won instead and `; won` is appended (the game is over). If nothing is eaten the event is `move`.",
    ]
    s.append("\n".join(f"{i + 1}. {t}" for i, t in enumerate(rules)) + "\n")
    s.append("## API (`include/coil.h`)\n\nThe header is given; keep the signatures. Implement them in `src/coil.c`.\n\n```c\nCoil *coil_new(unsigned seed);\nvoid coil_free(Coil *g);\nint coil_legal(const Coil *g, char *out, size_t cap);  /* \"U,L\" style list, any order; returns the count */\n"
             "int coil_apply(Coil *g, const char *move, char *event, size_t cap);  /* 0 and the event text, or -1 if illegal */\nvoid coil_render(const Coil *g, char *out, size_t cap);\nint coil_score(const Coil *g);\nint coil_over(const Coil *g);  /* 1 after a crash or a win */\n```\n")
    m = Model(1, r)
    m.apply("U")
    s.append(f"### `coil_render`\n\nThe grid, one line per row (`{W}` characters), then a status line, joined by `\\n` with no trailing newline: `.` empty, `#` stone, `*` apple, `!` pepper, `@` head, `o` other segments (the snake is drawn over food and stones never share a cell with it); "
             "the status line is `score <score> len <length> tick <tick>` followed by ` GAME OVER` after a crash or ` WON` after a win. Example after the first move `U` of a game with seed 1:\n\n```\n" + m.render().replace("\\n", "\n") + "\n```\n")
    s.append("## Tests\n\n`" + _scen.VERIFY[LANG] + "` builds the engine with the scenario runner and replays the scenario files in `tests/data/` (`tests/adapter.c` shows how the API is called; the format is described at the top of `tests/test_main.c`).\n")
    return "\n".join(s)


def project(r: dict) -> dict[str, str]:
    return {"src/coil.c": engine(r), "include/coil.h": HEADER_H, ".gitignore": _kit.GITIGNORE[LANG]}


def _variants(n: int) -> list[dict]:
    plan = [
        dict(),
        dict(W=9, H=9, WRAP=0, BITE=0, PEPPER=3),
        dict(W=12, H=7, BITE=1, PEPPER=0, LEN=4),
        dict(W=8, H=8, WRAP=0, BITE=1, PEPPER=5),
        dict(W=11, H=9, WRAP=1, BITE=0, PEPPER=0, LEN=5),
        dict(W=7, H=7, WRAP=1, BITE=1, PEPPER=2, LEN=3),
    ]
    return [{**DEFAULT, **o} for o in plan[:n]]


@family("games-coil-build", category="games", lang="c", kind="greenfield", n=6,
        summary="build the Coil severing-snake library in C: torus or walls, bites that turn the tail into stones, peppers, 16-bit LCG food")
def gen_build(rng, n):
    used: list[str] = []
    for i, r in enumerate(_variants(n)):
        sol = project(r)
        hidden = _kit.data_files(LANG, scripts(rng, r), sol, ADAPTER)
        for t in hidden.values():
            crosscheck(t, r)
        vis = _kit.data_files(LANG, {"examples": example_script()}, sol, ADAPTER)
        crosscheck(next(iter(vis.values())), r)
        start = {"README.md": readme(r), "src/coil.c": STUB, "include/coil.h": HEADER_H, ".gitignore": _kit.GITIGNORE[LANG], **_scen.check_files(LANG, ADAPTER), **vis}
        d = 2 + r["BITE"] + (r["PEPPER"] > 0) + (not r["WRAP"] and r["BITE"] == 0 and False)
        d = min(5, d + 1)
        prompt = _kit.green_prompt(rng, game=GAME, blurb=f"a snake on a {r['W']}x{r['H']} " + ("torus" if r["WRAP"] else "walled grid") + (", whose bites sever its body into stones" if r["BITE"] else ""),
                                   file="src/coil.c", verify=_scen.VERIFY[LANG], used=used, api_word="C API")
        yield Task(slug=f"{i + 1:02d}-{r['W']}x{r['H']}" + ("-torus" if r["WRAP"] else "-walls") + ("-sever" if r["BITE"] else "-crash") + (f"-pepper{r['PEPPER']}" if r["PEPPER"] else ""),
                   prompt=prompt, difficulty=d, start=start, hidden=hidden, solution={"src/coil.c": sol["src/coil.c"]}, verify=_scen.VERIFY[LANG],
                   tags=["snake", "rng", "scenarios"], notes={"rules": r})


BUGS = [
    Bug("tail-rule", "The snake can't follow its own tail",
        "A snake that goes round in a tight loop dies (or gets severed) when its head steps onto the cell its tail is just leaving, although the tail moves away on the same tick.",
        [("if (hit == g->len - 1) hit = -1; /* the tail moves away first */", "")], difficulty=3),
    Bug("reverse-legal", "The snake can turn back on itself",
        "Pressing the opposite direction is accepted: the head moves back into the neck and the snake dies or gets cut right away.",
        [("if (d == opposite(g->dir)) continue;", "")], difficulty=2),
    Bug("wrap-negative", "Wrapping off the top or left edge goes wrong",
        "Walking off the top or left edge of the meadow either crashes the program or puts the head in a nonsense cell; right and bottom are fine.",
        [("nr = (nr + H) % H;\n            nc = (nc + W) % W;", "nr = nr % H;\n            nc = nc % W;")], difficulty=3, rules=dict(WRAP=1)),
    Bug("food-cells", "Food can appear on the snake",
        "Food sometimes spawns on a cell that the snake occupies, and then the pickup is impossible until the snake moves on.",
        [("if (!occupied[r][c] && !g->stone[r][c]) empty++;", "if (!g->stone[r][c]) empty++;")], difficulty=3),
    Bug("pepper-shrink", "Peppers shrink the snake to nothing",
        "A pepper can leave the snake with a single segment; the README says its length never goes below 2.",
        [("g->len = g->len > 4 ? g->len - 2 : 2;", "g->len = g->len > 2 ? g->len - 2 : 1;")], difficulty=2, rules=dict(PEPPER=2)),
    Bug("bite-floor", "Bites can make the score negative",
        "After a bite the score can go below zero (shown as e.g. -2): it should stop at 0.",
        [("g->score = g->score >= cut ? g->score - cut : 0;", "g->score = g->score - cut;")], difficulty=2, rules=dict(BITE=1)),
    Bug("rng-mask", "The generator uses the wrong width",
        "With big seeds (more than 65535) the food ends up in different places than the README says; small seeds behave.",
        [("g->state = seed & 0xFFFFu;", "g->state = seed;")], difficulty=3),
    Bug("pepper-schedule", "Peppers come one food too early",
        "Peppers show up on the wrong food: the first pepper appears after one fewer apple than the README says.",
        [("g->fkind = (PEPPER_EVERY > 0 && g->foods % PEPPER_EVERY == 0) ? 1 : 0;", "g->fkind = (PEPPER_EVERY > 0 && (g->foods + 1) % PEPPER_EVERY == 0) ? 1 : 0;")], difficulty=3, rules=dict(PEPPER=3)),
    Bug("bite-count", "A bite cuts one segment too many",
        "After a bite there is one stone more than the README says: the bitten segment itself also turns to stone.",
        [("int cut = g->len - 1 - hit;\n            for (int i = hit + 1; i < g->len; i++)", "int cut = g->len - hit;\n            for (int i = hit; i < g->len; i++)")], difficulty=3, rules=dict(BITE=1)),
    Bug("render-pepper", "Peppers look like apples",
        "In the board text a pepper is drawn as an apple (`*`) so I can't tell what the next food is; the status of the game is otherwise right.",
        [("g->fkind ? '!' : '*'", "'*'")], difficulty=1, rules=dict(PEPPER=3)),
    Bug("wall-crash", "Hitting a wall doesn't end the game",
        "On the walled meadow the crash is reported (`crash wall`) but the game goes on afterwards: legal moves are still offered and the snake can keep playing.",
        [('g->status = 1;\n            snprintf(event, cap, "crash wall");', 'snprintf(event, cap, "crash wall");')], difficulty=2, rules=dict(WRAP=0, W=9, H=9, BITE=0, PEPPER=3)),
]
_B = {b.id: b for b in BUGS}
BUGS_ALL = BUGS + [
    _kit.combine(_B["reverse-legal"], _B["bite-floor"], difficulty=3),
    _kit.combine(_B["pepper-schedule"], _B["rng-mask"], difficulty=4),
]


@family("games-coil-fix", category="games", lang="c", kind="fix", n=12,
        summary="hand-injected defects in the Coil engine (tail rule, wrapping, food placement, peppers, bites, RNG width)")
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
        ctx = {"files": ["src/coil.c"], "verify": _scen.VERIFY[LANG]}
        yield _kit.bug_task(game=GAME, lang=LANG, base_files=base, tests=tests, hidden=hidden, bug=bug, ctx=ctx, rng=rng, used=used, k=k,
                            tags=["snake", "rng"], extra_notes={"rules": r})
