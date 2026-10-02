"""Skyline (java): falling blocks with tiny pieces, an exact LCG, optional wall kicks, row or column gravity and chains.
Build, fix and render-snapshot tasks; a python model cross-checks the reference engine."""
from __future__ import annotations

import json
import textwrap

from fx import Task, dd, family

from . import _kit, _scen
from ._kit import Bug

LANG = "java"
GAME = "Skyline"
DEFAULT = dict(W=6, H=10, CELLS=False, SOFT=1, DROP=2, LINE=10, KICK=False)
PIECES = "ILDX"
SHAPES = [[(0, -1), (0, 0), (0, 1)], [(-1, 0), (0, 0), (0, 1)], [(0, 0), (0, 1)], [(0, 0)]]


def ind(text: str, n: int = 4) -> str:
    return textwrap.indent(text, " " * n)


def header(r: dict) -> str:
    return dd(f'''
        // ---- house rules for this tower (they are part of the specification, see README.md) ----
        static final int W = {r["W"]};
        static final int H = {r["H"]};
        static final boolean CELL_GRAVITY = {"true" if r["CELLS"] else "false"};
        static final int SOFT = {r["SOFT"]};
        static final int DROP_PTS = {r["DROP"]};
        static final int LINE_PTS = {r["LINE"]};
        static final boolean KICK = {"true" if r["KICK"] else "false"};
        // ----------------------------------------------------------------------------------------
    ''')


ENGINE_TOP = dd(r'''
    import java.util.ArrayList;
    import java.util.Arrays;
    import java.util.List;

    /** Skyline: falling blocks. The rules are in README.md. */
    public class Skyline {
''')

ENGINE_BODY = dd(r'''
    static final String PIECES = "ILDX";
    static final int[][][] SHAPES = {
        {{0, -1}, {0, 0}, {0, 1}},
        {{-1, 0}, {0, 0}, {0, 1}},
        {{0, 0}, {0, 1}},
        {{0, 0}},
    };

    private final char[][] board = new char[H][W];
    private long state;
    private int score;
    private int lines;
    private boolean over;
    private int cur;
    private int next;
    private int[][] offs;
    private int row;
    private int col;

    public Skyline(long seed) {
        state = seed & 0xFFFFFFFFL;
        for (char[] r : board) Arrays.fill(r, '.');
        next = draw();
        spawn();
    }

    private int draw() {
        state = (state * 1664525L + 1013904223L) & 0xFFFFFFFFL;
        return (int) ((state >> 24) % 4);
    }

    private void spawn() {
        cur = next;
        next = draw();
        offs = new int[SHAPES[cur].length][];
        for (int i = 0; i < offs.length; i++) offs[i] = SHAPES[cur][i].clone();
        row = 1;
        col = W / 2;
        if (collides(offs, row, col)) over = true;
    }

    private boolean collides(int[][] o, int r0, int c0) {
        for (int[] p : o) {
            int r = r0 + p[0];
            int c = c0 + p[1];
            if (r < 0 || r >= H || c < 0 || c >= W || board[r][c] != '.') return true;
        }
        return false;
    }

    private int[][] rotate(int[][] o, boolean cw) {
        int[][] n = new int[o.length][2];
        for (int i = 0; i < o.length; i++) {
            n[i][0] = cw ? o[i][1] : -o[i][1];
            n[i][1] = cw ? -o[i][0] : o[i][0];
        }
        return n;
    }

    /** Column shift of a legal rotation, or Integer.MIN_VALUE when the rotation is not possible. */
    private int rotationShift(boolean cw) {
        int[][] n = rotate(offs, cw);
        int[] shifts = KICK ? new int[] {0, -1, 1} : new int[] {0};
        for (int s : shifts) {
            if (!collides(n, row, col + s)) return s;
        }
        return Integer.MIN_VALUE;
    }

    public List<String> legalMoves() {
        List<String> out = new ArrayList<>();
        if (over) return out;
        if (!collides(offs, row, col - 1)) out.add("left");
        if (!collides(offs, row, col + 1)) out.add("right");
        if (rotationShift(true) != Integer.MIN_VALUE) out.add("cw");
        if (rotationShift(false) != Integer.MIN_VALUE) out.add("ccw");
        out.add("down");
        out.add("drop");
        return out;
    }

    public String apply(String move) {
        if (move == null || !legalMoves().contains(move)) throw new IllegalArgumentException("illegal move: " + move);
        switch (move) {
            case "left":
                col--;
                return "moved";
            case "right":
                col++;
                return "moved";
            case "cw":
            case "ccw": {
                boolean cw = move.equals("cw");
                int s = rotationShift(cw);
                offs = rotate(offs, cw);
                col += s;
                return "rotated";
            }
            case "down":
                if (!collides(offs, row + 1, col)) {
                    row++;
                    score += SOFT;
                    return "fell";
                }
                return lock();
            default: {
                int n = 0;
                while (!collides(offs, row + 1, col)) {
                    row++;
                    n++;
                }
                score += n * DROP_PTS;
                return "dropped " + n + " +" + (n * DROP_PTS) + "; " + lock();
            }
        }
    }

    private String lock() {
        StringBuilder ev = new StringBuilder("locked " + PIECES.charAt(cur));
        for (int[] p : offs) board[row + p[0]][col + p[1]] = PIECES.charAt(cur);
        int chain = 1;
        while (true) {
            List<Integer> full = new ArrayList<>();
            for (int r = 0; r < H; r++) {
                boolean f = true;
                for (int c = 0; c < W; c++) if (board[r][c] == '.') f = false;
                if (f) full.add(r);
            }
            if (full.isEmpty()) break;
            int pts = LINE_PTS * full.size() * chain;
            score += pts;
            lines += full.size();
            ev.append("; clear ").append(full.size()).append(" x").append(chain).append(" +").append(pts);
            if (CELL_GRAVITY) {
                for (int r : full) Arrays.fill(board[r], '.');
                for (int c = 0; c < W; c++) {
                    int write = H - 1;
                    for (int r = H - 1; r >= 0; r--) {
                        if (board[r][c] != '.') {
                            char ch = board[r][c];
                            board[r][c] = '.';
                            board[write][c] = ch;
                            write--;
                        }
                    }
                }
            } else {
                int write = H - 1;
                for (int r = H - 1; r >= 0; r--) {
                    if (!full.contains(r)) {
                        if (write != r) board[write] = board[r];
                        write--;
                    }
                }
                while (write >= 0) board[write--] = emptyRow();
            }
            chain++;
        }
        spawn();
        ev.append(over ? "; game over" : "; spawn " + PIECES.charAt(cur));
        return ev.toString();
    }

    private static char[] emptyRow() {
        char[] r = new char[W];
        Arrays.fill(r, '.');
        return r;
    }

    public int score() {
        return score;
    }

    public boolean over() {
        return over;
    }

    public int lines() {
        return lines;
    }

    /** The locked letter at (r, c), or '.' for an empty cell. */
    public char cell(int r, int c) {
        return board[r][c];
    }

    /** Cells {row, col} of the falling piece (none when the game is over). */
    public int[][] activeCells() {
        if (over) return new int[0][];
        int[][] out = new int[offs.length][2];
        for (int i = 0; i < offs.length; i++) {
            out[i][0] = row + offs[i][0];
            out[i][1] = col + offs[i][1];
        }
        return out;
    }

    /** Letter of the falling piece. */
    public char activePiece() {
        return PIECES.charAt(cur);
    }

    /** Letter of the piece that comes next. */
    public char nextPiece() {
        return PIECES.charAt(next);
    }

    /** Cells {row, col} the falling piece would occupy after a hard drop (none when the game is over). */
    public int[][] ghostCells() {
        if (over) return new int[0][];
        int r = row;
        while (!collides(offs, r + 1, col)) r++;
        int[][] out = new int[offs.length][2];
        for (int i = 0; i < offs.length; i++) {
            out[i][0] = r + offs[i][0];
            out[i][1] = col + offs[i][1];
        }
        return out;
    }

''')

RENDER_PLAIN = dd(r'''
    public String render() {
        StringBuilder sb = new StringBuilder();
        char[][] view = new char[H][W];
        for (int r = 0; r < H; r++) view[r] = board[r].clone();
        for (int[] p : activeCells()) view[p[0]][p[1]] = Character.toLowerCase(PIECES.charAt(cur));
        for (int r = 0; r < H; r++) sb.append(new String(view[r])).append('\n');
        sb.append("score ").append(score).append(" lines ").append(lines);
        sb.append(over ? " GAME OVER" : " next " + PIECES.charAt(next));
        return sb.toString();
    }
''')

RENDER_STUB = dd(r'''
    public String render() {
        throw new UnsupportedOperationException("not implemented");
    }
''')

RENDER_FRAMED = dd(r'''
    public String render() {
        StringBuilder sb = new StringBuilder();
        String bar = "+" + "-".repeat(W) + "+";
        char[][] view = new char[H][W];
        for (int r = 0; r < H; r++) view[r] = board[r].clone();
        for (int[] p : activeCells()) view[p[0]][p[1]] = Character.toLowerCase(PIECES.charAt(cur));
        sb.append(bar).append('\n');
        for (int r = 0; r < H; r++) sb.append('|').append(new String(view[r])).append("|\n");
        sb.append(bar).append('\n');
        sb.append("score ").append(score).append(" lines ").append(lines);
        sb.append(over ? " GAME OVER" : " next " + PIECES.charAt(next));
        return sb.toString();
    }
''')

RENDER_GHOST = dd(r'''
    public String render() {
        StringBuilder sb = new StringBuilder();
        char[][] view = new char[H][W];
        for (int r = 0; r < H; r++) view[r] = board[r].clone();
        for (int[] p : ghostCells()) view[p[0]][p[1]] = ':';
        for (int[] p : activeCells()) view[p[0]][p[1]] = Character.toLowerCase(PIECES.charAt(cur));
        for (int r = 0; r < H; r++) sb.append(new String(view[r])).append('\n');
        sb.append("score ").append(score).append(" lines ").append(lines);
        sb.append(over ? " GAME OVER" : " next " + PIECES.charAt(next));
        return sb.toString();
    }
''')

RENDER_RULER = dd(r'''
    public String render() {
        StringBuilder sb = new StringBuilder("   ");
        for (int c = 0; c < W; c++) sb.append(c % 10);
        sb.append('\n');
        char[][] view = new char[H][W];
        for (int r = 0; r < H; r++) view[r] = board[r].clone();
        for (int[] p : activeCells()) view[p[0]][p[1]] = Character.toLowerCase(PIECES.charAt(cur));
        for (int r = 0; r < H; r++) sb.append(String.format("%2d ", r)).append(new String(view[r])).append('\n');
        sb.append("score ").append(score).append(" lines ").append(lines);
        sb.append(over ? " GAME OVER" : " next " + PIECES.charAt(next));
        return sb.toString();
    }
''')

RENDER_PANEL = dd(r'''
    public String render() {
        char[][] view = new char[H][W];
        for (int r = 0; r < H; r++) view[r] = board[r].clone();
        for (int[] p : activeCells()) view[p[0]][p[1]] = Character.toLowerCase(PIECES.charAt(cur));
        String[] panel = new String[H];
        Arrays.fill(panel, "");
        panel[0] = "SCORE " + score;
        panel[1] = "LINES " + lines;
        if (over) {
            panel[3] = "GAME OVER";
        } else {
            panel[3] = "NEXT " + PIECES.charAt(next);
            int[][] shape = SHAPES[PIECES.indexOf(PIECES.charAt(next))];
            int minR = 9;
            int minC = 9;
            for (int[] p : shape) {
                minR = Math.min(minR, p[0]);
                minC = Math.min(minC, p[1]);
            }
            for (int pr = 0; pr < 2; pr++) {
                StringBuilder sb = new StringBuilder();
                for (int pc = 0; pc < 3; pc++) {
                    boolean hit = false;
                    for (int[] p : shape) if (p[0] - minR == pr && p[1] - minC == pc) hit = true;
                    sb.append(hit ? '#' : ' ');
                }
                panel[4 + pr] = sb.toString().replaceAll("\\s+$", "");
            }
        }
        StringBuilder out = new StringBuilder();
        for (int r = 0; r < H; r++) {
            out.append(new String(view[r]));
            if (!panel[r].isEmpty()) out.append("  ").append(panel[r]);
            if (r < H - 1) out.append('\n');
        }
        return out.toString();
    }
''')

RENDERS = {"plain": RENDER_PLAIN, "framed": RENDER_FRAMED, "ghost": RENDER_GHOST, "ruler": RENDER_RULER, "panel": RENDER_PANEL}


def engine(r: dict, render: str = RENDER_PLAIN) -> str:
    return ENGINE_TOP + ind(header(r)) + "\n" + ind(ENGINE_BODY) + ind(render) + "}\n"


STUB = dd(r'''
    import java.util.List;

    /** Skyline: falling blocks. The rules and the API are in README.md. */
    public class Skyline {
        public Skyline(long seed) {
            throw new UnsupportedOperationException("not implemented");
        }

        public List<String> legalMoves() {
            throw new UnsupportedOperationException("not implemented");
        }

        public String apply(String move) {
            throw new UnsupportedOperationException("not implemented");
        }

        public String render() {
            throw new UnsupportedOperationException("not implemented");
        }

        public int score() {
            throw new UnsupportedOperationException("not implemented");
        }

        public boolean over() {
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
        private Skyline game;

        String run(String verb, String args) {
            switch (verb) {
                case "new": // new <seed>
                    game = new Skyline(Long.parseLong(args));
                    return "ok";
                case "do": // do <move>: the event text, or "illegal"
                    try {
                        return game.apply(args);
                    } catch (IllegalArgumentException e) {
                        return "illegal";
                    }
                case "legal": { // sorted legal moves joined by "," ("-" when there are none)
                    List<String> moves = new ArrayList<>(game.legalMoves());
                    Collections.sort(moves);
                    return moves.isEmpty() ? "-" : String.join(",", moves);
                }
                case "render":
                    return game.render();
                case "status": // "<score> <over>"
                    return game.score() + " " + game.over();
                default:
                    throw new IllegalArgumentException("unknown verb " + verb);
            }
        }
    }
''')}


# ----------------------------------------------------------------------------------------------------- python model

class Model:
    def __init__(self, seed: int, r: dict):
        self.r = r
        self.W, self.H = r["W"], r["H"]
        self.board = [["."] * self.W for _ in range(self.H)]
        self.state = seed & 0xFFFFFFFF
        self.score = self.lines = 0
        self.over = False
        self.next = self.draw()
        self.spawn()

    def draw(self):
        self.state = (self.state * 1664525 + 1013904223) & 0xFFFFFFFF
        return (self.state >> 24) % 4

    def spawn(self):
        self.cur, self.next = self.next, self.draw()
        self.offs = [tuple(p) for p in SHAPES[self.cur]]
        self.row, self.col = 1, self.W // 2
        if self.collides(self.offs, self.row, self.col):
            self.over = True

    def collides(self, o, r0, c0):
        for pr, pc in o:
            r, c = r0 + pr, c0 + pc
            if r < 0 or r >= self.H or c < 0 or c >= self.W or self.board[r][c] != ".":
                return True
        return False

    @staticmethod
    def rot(o, cw):
        return [((pc if cw else -pc), (-pr if cw else pr)) for pr, pc in o]

    def shift(self, cw):
        n = self.rot(self.offs, cw)
        for s in ([0, -1, 1] if self.r["KICK"] else [0]):
            if not self.collides(n, self.row, self.col + s):
                return s
        return None

    def legal(self):
        if self.over:
            return []
        out = []
        if not self.collides(self.offs, self.row, self.col - 1):
            out.append("left")
        if not self.collides(self.offs, self.row, self.col + 1):
            out.append("right")
        if self.shift(True) is not None:
            out.append("cw")
        if self.shift(False) is not None:
            out.append("ccw")
        return out + ["down", "drop"]

    def apply(self, mv):
        if mv == "left":
            self.col -= 1
            return "moved"
        if mv == "right":
            self.col += 1
            return "moved"
        if mv in ("cw", "ccw"):
            s = self.shift(mv == "cw")
            self.offs = self.rot(self.offs, mv == "cw")
            self.col += s
            return "rotated"
        if mv == "down":
            if not self.collides(self.offs, self.row + 1, self.col):
                self.row += 1
                self.score += self.r["SOFT"]
                return "fell"
            return self.lock()
        n = 0
        while not self.collides(self.offs, self.row + 1, self.col):
            self.row += 1
            n += 1
        self.score += n * self.r["DROP"]
        return "dropped %d +%d; %s" % (n, n * self.r["DROP"], self.lock())

    def lock(self):
        W, H = self.W, self.H
        ev = "locked " + PIECES[self.cur]
        for pr, pc in self.offs:
            self.board[self.row + pr][self.col + pc] = PIECES[self.cur]
        chain = 1
        while True:
            full = [r for r in range(H) if all(ch != "." for ch in self.board[r])]
            if not full:
                break
            pts = self.r["LINE"] * len(full) * chain
            self.score += pts
            self.lines += len(full)
            ev += "; clear %d x%d +%d" % (len(full), chain, pts)
            if self.r["CELLS"]:
                for r in full:
                    self.board[r] = ["."] * W
                for c in range(W):
                    col = [self.board[r][c] for r in range(H) if self.board[r][c] != "."]
                    for r in range(H):
                        self.board[r][c] = "." if r < H - len(col) else col[r - (H - len(col))]
            else:
                kept = [row for r, row in enumerate(self.board) if r not in full]
                self.board = [["."] * W for _ in full] + kept
            chain += 1
        self.spawn()
        return ev + ("; game over" if self.over else "; spawn " + PIECES[self.cur])

    def view(self):
        v = [row[:] for row in self.board]
        return v

    def active(self):
        return [] if self.over else [(self.row + pr, self.col + pc) for pr, pc in self.offs]

    def ghost(self):
        if self.over:
            return []
        r = self.row
        while not self.collides(self.offs, r + 1, self.col):
            r += 1
        return [(r + pr, self.col + pc) for pr, pc in self.offs]

    def render(self, style: str = "plain"):
        W, H = self.W, self.H
        v = self.view()
        if style == "ghost":
            for r, c in self.ghost():
                v[r][c] = ":"
        for r, c in self.active():
            v[r][c] = PIECES[self.cur].lower()
        foot = "score %d lines %d" % (self.score, self.lines) + (" GAME OVER" if self.over else " next " + PIECES[self.next])
        rows = ["".join(row) for row in v]
        if style in ("plain", "ghost"):
            return "\\n".join(rows + [foot])
        if style == "framed":
            bar = "+" + "-" * W + "+"
            return "\\n".join([bar] + ["|" + r + "|" for r in rows] + [bar, foot])
        if style == "ruler":
            return "\\n".join(["   " + "".join(str(c % 10) for c in range(W))] + ["%2d " % i + r for i, r in enumerate(rows)] + [foot])
        panel = [""] * H
        panel[0], panel[1] = "SCORE %d" % self.score, "LINES %d" % self.lines
        if self.over:
            panel[3] = "GAME OVER"
        else:
            panel[3] = "NEXT " + PIECES[self.next]
            shape = SHAPES[self.next]
            mr, mc = min(p[0] for p in shape), min(p[1] for p in shape)
            for pr in range(2):
                panel[4 + pr] = "".join("#" if any(p[0] - mr == pr and p[1] - mc == pc for p in shape) else " " for pc in range(3)).rstrip()
        return "\\n".join(r + ("  " + panel[i] if panel[i] else "") for i, r in enumerate(rows))


def crosscheck(text: str, r: dict, style: str = "plain") -> None:
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
                got = f"{m.score} {'true' if m.over else 'false'}"
                assert got == want, f"status disagree {got!r} vs {want!r}"
            elif verb == "render":
                assert m.render(style) == want, f"render disagree:\n{m.render(style)}\n{want}"
            cmd = None


# ----------------------------------------------------------------------------------------------------- README

def piece_table() -> str:
    rows = ["| letter | cells as (row, column) offsets from the piece's origin |", "|---|---|"]
    for ch, sh in zip(PIECES, SHAPES):
        rows.append(f"| `{ch}` | " + ", ".join(f"({a},{b})" for a, b in sh) + " |")
    return "\n".join(rows)


def readme(r: dict, style: str = "plain", render_only: bool = False) -> str:
    W, H = r["W"], r["H"]
    s = []
    s.append("# Skyline\n\nA falling-blocks engine with tiny pieces. The engine is headless: a `Skyline` object, its legal moves and exact text for every reply. "
             "Everything is deterministic: pieces come from a generator that is specified exactly.\n")
    s.append(f"## Board and pieces\n\nThe board has {H} rows (row 0 at the top) and {W} columns (column 0 at the left). A cell is empty (`.`) or holds a locked block, remembered by the letter of the piece it came from.\n\n"
             f"Pieces are four small shapes:\n\n{piece_table()}\n\nA piece is a list of offsets; the falling piece also has an *origin* cell `(row, col)` on the board, so the piece covers `(row + dr, col + dc)` for every offset. "
             f"The offsets of the *current orientation* change when the piece rotates: a clockwise turn maps every offset `(dr, dc)` to `(dc, -dr)`, a counter-clockwise turn maps it to `(-dc, dr)` (the origin stays where it is).\n")
    s.append("### Randomness\n\n`state` is an unsigned 32-bit integer. `Skyline(seed)` starts with `state = seed mod 2^32`. A *draw* sets `state = (state * 1664525 + 1013904223) mod 2^32` and "
             "returns `(state >> 24) mod 4`, the index into the letters `ILDX`. The game draws once at the start (that piece will be the first falling piece) and draws once more immediately to choose the next piece "
             "(it is *next*); afterwards every spawn takes `next` and then draws a new `next`. Nothing else draws.\n")
    s.append(f"### Spawning\n\nA piece spawns in its base orientation with origin `(1, {W // 2})` (row 1, column `W / 2` rounded down). If any of its cells is outside the board or on a locked block the game is over "
             "(the piece does not exist on the board, there are no legal moves and the game never changes again).\n")
    kick = (f" If the rotated piece does not fit, the rotation is retried with the origin moved one column left (`col - 1`) and then one column right (`col + 1`); the first position that fits is used and the origin moves with it. If none fits the rotation is illegal."
            if r["KICK"] else " A rotation is legal only if the rotated piece fits with the origin where it is (there are no wall kicks).")
    s.append("## Moves\n\nMoves are exact strings: `left`, `right`, `cw`, `ccw`, `down`, `drop` (nothing else is accepted). `legalMoves()` lists the legal ones:\n\n"
             "* `left`, `right`: legal when the piece fits one column to the left or right. Event `moved`.\n"
             f"* `cw`, `ccw`: rotate the piece.{kick} Event `rotated`.\n"
             f"* `down`: always legal while the game runs. If the piece fits one row lower it moves there, the score gains {r['SOFT']} point{'s' if r['SOFT'] != 1 else ''} and the event is `fell`. Otherwise the piece *locks* (below).\n"
             f"* `drop`: always legal. The piece falls as far as it can, `n` rows (possibly 0); the score gains `n * {r['DROP']}` and the piece locks. Event `dropped <n> +<points>; ` followed by the lock event.\n")
    grav = ("Every column is compacted downwards: the blocks of a column fall to the bottom of the board, keeping their order and their letters, until there are no gaps in the column (this also closes holes that existed before). "
            if r["CELLS"] else "The remaining rows move down to fill the gaps and empty rows appear at the top; the rows keep their order. ")
    s.append("## Locking, clearing, scoring\n\n"
             "When the piece locks its cells become locked blocks with the piece's letter. Then rows are cleared in *rounds*, `chain` starting at 1:\n\n"
             f"1. Collect the full rows (no empty cell). If there are none, stop.\n2. With `k` full rows the score gains `{r['LINE']} * k * chain` points, `lines` grows by `k`. Remove the full rows (their cells become empty). {grav}\n"
             "3. `chain` grows by 1 and the next round starts.\n\n"
             "(" + ("With column gravity a new full row can appear after the compaction, which is why chains exist." if r["CELLS"] else "With row gravity compacting never makes a new full row, so a lock clears at most one round.") + ")\n\n"
             "Finally the next piece spawns. The lock event is `locked <letter>`, then for every round `; clear <k> x<chain> +<points>`, then `; spawn <letter of the new piece>` or `; game over`. "
             "Example: `locked L; clear 1 x1 +10; spawn I`.\n")
    s.append("## API (`Skyline.java`, default package)\n\n```java\nSkyline g = new Skyline(long seed);\nList<String> g.legalMoves();   // legal moves in any order; empty when the game is over\n"
             "String g.apply(String move);   // plays a legal move and returns the event; throws IllegalArgumentException (state unchanged) otherwise\n"
             "String g.render();             // the board text (below)\nint g.score();\nboolean g.over();\n```\n")
    if render_only:
        s.append("The engine already has everything except `render()`; these read-only accessors are there for it: `int lines()`, `char cell(int row, int col)` (locked letter or `.`), `int[][] activeCells()` "
                 "(`{row, col}` pairs of the falling piece, none when the game is over), `char activePiece()`, `char nextPiece()`, `int[][] ghostCells()` (where a hard drop would put the piece, none when the game is over).\n")
    s.append(render_section(r, style))
    s.append("## Tests\n\n`" + _scen.VERIFY[LANG] + "` replays the scenario files in `test/data/` (`test/Adapter.java` shows how the API is called; the format is described at the top of `test/TestMain.java`).\n")
    return "\n".join(s)


def render_section(r: dict, style: str) -> str:
    W, H = r["W"], r["H"]
    m = Model(5, r)
    m.apply("drop")
    sample = {k: m.render(k) for k in RENDERS}
    common = ("The footer line is `score <score> lines <lines>` followed by ` next <letter>` while the game runs or ` GAME OVER` when it is over. In the picture the falling piece is drawn with the *lower-case* letter "
              "of its piece (locked blocks keep their upper-case letters, empty cells are `.`); when the game is over there is no falling piece. Lines are joined by `\\n`, there is no trailing newline.")
    if style == "plain":
        return f"### `render()`\n\n{H} board lines of {W} characters, then the footer. {common}\n\n```\n{sample['plain']}\n```\n"
    if style == "framed":
        return (f"### `render()`\n\nThe board is framed: a line `+` + {W} dashes + `+`, then each board row between `|` characters, then the same frame line, then the footer. {common}\n\n```\n{sample['framed']}\n```\n")
    if style == "ghost":
        return (f"### `render()`\n\n{H} board lines of {W} characters, then the footer. Besides the falling piece the board shows its *ghost*: the cells that a hard drop would fill are drawn `:` — except where the "
                f"falling piece itself currently is (the lower-case letter wins) — and only on cells that are empty. {common}\n\n```\n{sample['ghost']}\n```\n")
    if style == "ruler":
        return (f"### `render()`\n\nA ruler line first: three spaces, then the column numbers modulo 10 (`0123...`). Each board row is prefixed with its row number right-aligned to width 2 and one space (`' 0 '`, `'12 '`). Then the footer. "
                f"{common}\n\n```\n{sample['ruler']}\n```\n")
    return (f"### `render()`\n\nNo footer line. The {H} board lines (each {W} characters, falling piece in lower case as above) get a side panel appended after two spaces, only on the lines that have panel text "
            f"(lines without panel text end after the board): line 0 `SCORE <score>`, line 1 `LINES <lines>`, line 3 `NEXT <letter>` (or `GAME OVER` instead while the game is over), and while the game runs lines 4 and 5 draw the shape of "
            f"the next piece with `#` and spaces on a 2-row, 3-column grid (rows and columns are taken from the minimum offset of the shape; trailing spaces of a panel line are removed, a line that becomes empty is left empty and gets no "
            f"two-space prefix). Lines are joined by `\\n`, no trailing newline.\n\n```\n{sample['panel']}\n```\n")


def project(r: dict, style: str = "plain") -> dict[str, str]:
    return {"src/Skyline.java": engine(r, RENDERS[style]), ".gitignore": _kit.GITIGNORE[LANG]}


def policy_moves(rng, seed: int, r: dict, pieces: int, blunder: int = 10) -> list[str]:
    """Moves of a greedy stacker (the python model plays it): for every piece the placement that clears lines and avoids
    holes, with an occasional random blunder. Random play almost never completes a row; this does."""
    import copy

    m = Model(seed, r)
    out: list[str] = []
    for _ in range(pieces):
        if m.over:
            break
        best = None
        for rot in range(4):
            for target in range(-1, m.W + 1):
                c = copy.deepcopy(m)
                seq: list[str] = []
                ok = True
                for _r in range(rot):
                    if "cw" not in c.legal():
                        ok = False
                        break
                    c.apply("cw")
                    seq.append("cw")
                if not ok:
                    continue
                while c.col != target and ok:
                    mv = "left" if c.col > target else "right"
                    if mv not in c.legal():
                        ok = False
                        break
                    c.apply(mv)
                    seq.append(mv)
                if not ok:
                    continue
                before = c.lines
                c.apply("drop")
                seq.append("drop")
                holes = 0
                height = 0
                for col in range(c.W):
                    seen = False
                    for row in range(c.H):
                        if c.board[row][col] != ".":
                            if not seen:
                                height += c.H - row
                            seen = True
                        elif seen:
                            holes += 1
                score = (c.lines - before) * 50 - holes * 8 - height
                if best is None or score > best[0]:
                    best = (score, seq)
        if best is None or rng.randrange(100) < blunder:
            seq = [rng.choice([mv for mv in m.legal() if mv != "drop"] or ["drop"]) for _ in range(rng.randrange(1, 4))] + ["drop"]
        else:
            seq = best[1]
        for mv in seq:
            if m.over:
                break
            if mv in m.legal():
                m.apply(mv)
                out.append(mv)
    return out


def scripts(rng, r: dict) -> dict[str, str]:
    stack = []
    for i, sd in enumerate((21, 22, 23)):
        mv = policy_moves(rng, sd, r, 70, blunder=[0, 6, 14][i])
        stack.append(f"# scenario stacker {i + 1}\n> new {sd}\n" + "\n".join(f"> do {m}" + ("\n> render" if k % 7 == 6 else "") for k, m in enumerate(mv)) + "\n> render\n> status\n> legal")
    games = "\n".join(f"# scenario game {s}\n> new {s}\n~ rand 700 {s * 13 + 1} every=9 emit=render,legal,status junk=Left|up|rotate|drop |cw cw|0" for s in (1, 2, 3, 4242, 4294967295, 99999999999, 7))
    plan = []
    for i, s in enumerate((11, 12, 13)):
        plan.append(f"# scenario stacking {i + 1}\n> new {s}\n" + "\n".join(["> do drop", "> render"] * 14) + "\n> status\n> legal")
        plan.append(f"# scenario sideways {i + 1}\n> new {s}\n" + "\n".join(["> do left"] * 4 + ["> do cw", "> do right", "> do right", "> do ccw", "> render", "> do cw", "> do cw", "> do cw", "> render", "> do down", "> do down", "> render"]))
    edge = dd('''
        # scenario illegal moves
        > new 5
        > do Left
        > do up
        > do
        > do cw cw
        > do hold
        > legal
        > render
        > status
        # scenario seeds
        > new 0
        > render
        > new 4294967296
        > render
        > new 4294967295
        > render
        # scenario games are independent
        > new 9
        ~ rand 30 4 every=30 emit=render
        > new 9
        ~ rand 30 4 every=30 emit=render
    ''')
    return {"hidden_games": games + "\n", "hidden_plans": "\n".join(plan) + "\n", "hidden_edge": edge, "hidden_stackers": "\n".join(stack) + "\n"}


def example_script() -> str:
    return dd('''
        # scenario opening
        > new 1
        > render
        > legal
        > do left
        > do cw
        > render
        > do drop
        > render
        # scenario a few moves
        > new 12
        ~ rand 14 3 emit=render,status
    ''')


def _variants(n: int) -> list[dict]:
    plan = [
        dict(),
        dict(W=7, CELLS=True, SOFT=0, DROP=1),
        dict(H=9, KICK=True),
        dict(W=8, H=11, CELLS=True, KICK=True, LINE=15),
        dict(W=5, H=9, CELLS=True, LINE=20),
        dict(W=6, H=12, KICK=True, SOFT=2, DROP=3, LINE=15),
    ]
    return [{**DEFAULT, **o} for o in plan[:n]]


@family("games-skyline-build", category="games", lang="java", kind="greenfield", n=6,
        summary="build the Skyline falling-blocks engine: tiny pieces, exact LCG, wall kicks, row or column gravity and chains")
def gen_build(rng, n):
    used: list[str] = []
    for i, r in enumerate(_variants(n)):
        sol = project(r)
        hidden = _kit.data_files(LANG, scripts(rng, r), sol, ADAPTER)
        for t in hidden.values():
            crosscheck(t, r)
        vis = _kit.data_files(LANG, {"examples": example_script()}, sol, ADAPTER)
        crosscheck(next(iter(vis.values())), r)
        start = {"README.md": readme(r), "src/Skyline.java": STUB, ".gitignore": _kit.GITIGNORE[LANG], **_scen.check_files(LANG, ADAPTER), **vis}
        d = min(5, 2 + r["CELLS"] * 2 + r["KICK"] + (r["H"] != 10 and r["W"] != 6))
        blurb = f"a {r['W']}-wide falling-blocks game with tiny pieces" + (", column gravity and chain reactions" if r["CELLS"] else "")
        prompt = _kit.green_prompt(rng, game=GAME, blurb=blurb, file="src/Skyline.java", verify=_scen.VERIFY[LANG], used=used)
        slug = f"{i + 1:02d}-w{r['W']}h{r['H']}" + ("-cells" if r["CELLS"] else "-rows") + ("-kick" if r["KICK"] else "")
        yield Task(slug=slug, prompt=prompt, difficulty=d, start=start, hidden=hidden, solution={"src/Skyline.java": sol["src/Skyline.java"]},
                   verify=_scen.VERIFY[LANG], tags=["falling-blocks", "rng", "scenarios"], notes={"rules": r})


BUGS = [
    Bug("rotation-direction", "Clockwise rotates counter-clockwise",
        "The rotate keys are swapped: `cw` turns a piece counter-clockwise and `ccw` clockwise. The L piece makes it obvious.",
        [("n[i][0] = cw ? o[i][1] : -o[i][1];\n            n[i][1] = cw ? -o[i][0] : o[i][0];", "n[i][0] = cw ? -o[i][1] : o[i][1];\n            n[i][1] = cw ? o[i][0] : -o[i][0];")], difficulty=1),
    Bug("spawn-column", "Pieces spawn one column off",
        "New pieces appear one column to the left of where the README says; the effect is easiest to see on a board with an even width.",
        [("col = W / 2;", "col = (W - 1) / 2;")], difficulty=2, rules=dict(W=6)),
    Bug("bottom-row", "The bottom row never clears",
        "A completely filled bottom row just sits there and is never cleared, while rows higher up clear fine.",
        [("for (int r = 0; r < H; r++) {\n                boolean f = true;", "for (int r = 0; r < H - 1; r++) {\n                boolean f = true;")], difficulty=2),
    Bug("chain-counter", "Chain bonuses are never applied",
        "On the column-gravity table a clear that triggers another clear scores as if it was an ordinary clear: the `x2` bonus never shows up in the points.",
        [("            chain++;\n        }\n        spawn();", "        }\n        spawn();")], difficulty=3, rules=dict(CELLS=True)),
    Bug("drop-distance", "Hard drops are paid one row too much",
        "Hard drop points are off: dropping from a spot where the piece can fall `n` rows pays for `n + 1`, even when it is already resting on the stack.",
        [("score += n * DROP_PTS;\n                return \"dropped \" + n + \" +\" + (n * DROP_PTS) + \"; \" + lock();", "score += (n + 1) * DROP_PTS;\n                return \"dropped \" + n + \" +\" + ((n + 1) * DROP_PTS) + \"; \" + lock();")], difficulty=2, rules=dict(DROP=2)),
    Bug("kick-order", "Wall kicks prefer the right",
        "When a rotation needs a wall kick the piece is moved to the right even when moving it to the left would also work; the README says left is tried first.",
        [("int[] shifts = KICK ? new int[] {0, -1, 1} : new int[] {0};", "int[] shifts = KICK ? new int[] {0, 1, -1} : new int[] {0};")], difficulty=3, rules=dict(KICK=True)),
    Bug("gravity-up", "Blocks float to the top after a column clear",
        "On the column-gravity table, after a row clear the blocks of the columns are pushed to the top of the board instead of falling down.",
        [("int write = H - 1;\n                    for (int r = H - 1; r >= 0; r--) {\n                        if (board[r][c] != '.') {\n                            char ch = board[r][c];\n                            board[r][c] = '.';\n                            board[write][c] = ch;\n                            write--;\n                        }\n                    }",
          "int write = 0;\n                    for (int r = 0; r < H; r++) {\n                        if (board[r][c] != '.') {\n                            char ch = board[r][c];\n                            board[r][c] = '.';\n                            board[write][c] = ch;\n                            write++;\n                        }\n                    }")], difficulty=3, rules=dict(CELLS=True)),
    Bug("rng-shift", "The piece sequence is not the documented one",
        "With a given seed the sequence of pieces differs from the README: the draw seems to use different bits of the generator state.",
        [("return (int) ((state >> 24) % 4);", "return (int) ((state >> 16) % 4);")], difficulty=2),
    Bug("extra-draw", "The piece sequence is shifted by one",
        "From the very first piece on, the sequence of pieces does not match the README for a given seed: every piece looks like the one that should have come after it.",
        [("next = draw();\n        spawn();\n    }", "draw();\n        next = draw();\n        spawn();\n    }")], difficulty=3),
    Bug("rotate-into-wall", "Pieces can rotate into walls and blocks",
        "Rotating next to a wall or the stack sometimes pushes part of the piece outside the board or over locked blocks, and then the game crashes or the piece overlaps.",
        [("if (rotationShift(true) != Integer.MIN_VALUE) out.add(\"cw\");\n        if (rotationShift(false) != Integer.MIN_VALUE) out.add(\"ccw\");", "out.add(\"cw\");\n        out.add(\"ccw\");")], difficulty=3),
    Bug("soft-drop-lock", "Soft drops score when they lock",
        "The `down` key scores a soft-drop point even when the piece could not move and locked instead.",
        [("                return lock();\n            default: {", "                score += SOFT;\n                return lock();\n            default: {")], difficulty=2, rules=dict(SOFT=1)),
    Bug("lines-count", "The lines counter counts clear rounds",
        "The `lines` figure in the footer is wrong after multi-row clears: it counts a double clear as a single line.",
        [("lines += full.size();", "lines += 1;")], difficulty=2),
    Bug("game-over-spawn", "Game over is detected one piece late",
        "The tower can overflow and a new piece still spawns on top of locked blocks; the game only ends when the next piece fails to spawn.",
        [("if (collides(offs, row, col)) over = true;", "if (collides(offs, row + 1, col)) over = true;")], difficulty=3),
]


_B = {b.id: b for b in BUGS}
BUGS_ALL = BUGS + [
    _kit.combine(_B["lines-count"], _B["soft-drop-lock"], difficulty=3),
    _kit.combine(_B["bottom-row"], _B["chain-counter"], difficulty=4, title="Scoring and clearing"),
    _kit.combine(_B["spawn-column"], _B["rotation-direction"], _B["rng-shift"], difficulty=4),
]


@family("games-skyline-fix", category="games", lang="java", kind="fix", n=16,
        summary="hand-injected defects in the Skyline engine (rotation, spawn, clearing, chains, gravity, kicks, RNG, scoring)")
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
        ctx = {"files": ["src/Skyline.java"], "verify": _scen.VERIFY[LANG]}
        yield _kit.bug_task(game=GAME, lang=LANG, base_files=base, tests=tests, hidden=hidden, bug=bug, ctx=ctx, rng=rng, used=used, k=k,
                            tags=["falling-blocks", "rng"], extra_notes={"rules": r})


# ----------------------------------------------------------------------------------------------------- snapshot renderer

SNAP_STYLES = [("plain", 1), ("framed", 2), ("ghost", 3), ("ruler", 2), ("panel", 4)]


@family("games-skyline-snapshot", category="games", lang="java", kind="feature", n=5,
        summary="implement Skyline's text renderer (framed, ghost piece, ruler, side panel) against exact snapshot strings")
def gen_snapshot(rng, n):
    for i, (style, d) in enumerate(SNAP_STYLES[:n]):
        r = {**DEFAULT, **dict(W=[6, 7, 6, 8, 7][i], H=[10, 9, 10, 11, 10][i])}
        full = project(r, style)
        engine_no_render = {"src/Skyline.java": engine(r, RENDER_STUB), ".gitignore": _kit.GITIGNORE[LANG]}
        sc = {"hidden_snap": "\n".join(f"# scenario render {s}\n> new {s}\n~ rand 200 {s + 5} every=2 emit=render,status" for s in (3, 4, 77, 1234, 98765, 5)) + "\n"
              + "# scenario a wide stack\n> new 8\n" + "\n".join(["> do drop", "> render"] * 18) + "\n"}
        hidden = _kit.data_files(LANG, sc, full, ADAPTER)
        for t in hidden.values():
            crosscheck(t, r, style)
        ex = "# scenario opening\n> new 1\n> render\n> do left\n> do cw\n> render\n> do drop\n> render\n# scenario a short game\n> new 12\n~ rand 12 3 emit=render\n"
        vis = _kit.data_files(LANG, {"examples": ex}, full, ADAPTER)
        crosscheck(next(iter(vis.values())), r, style)
        start = {"README.md": readme(r, style, render_only=True), **engine_no_render, **_scen.check_files(LANG, ADAPTER), **vis}
        asks = {
            "plain": "The Skyline engine is finished except for `render()`, which still throws. Write it so the board text matches the README exactly: board lines, the falling piece in lower case, and the footer.",
            "framed": "Skyline's terminal front end wants the board in a frame. Implement `render()` in `src/Skyline.java` as described in README.md; the engine has accessors for everything you need.",
            "ghost": "Players of our Skyline table want a ghost piece. Implement `render()` (README.md describes it, including how the ghost cells interact with the falling piece) in the Skyline engine, which is otherwise complete.",
            "ruler": "Implement Skyline's `render()` with the ruler line and the row numbers the README describes. The rest of the engine is done and tested; only `render()` is missing.",
            "panel": "Skyline needs a text renderer with a side panel that shows the score, the lines and a small drawing of the next piece. README.md has the exact layout, and the engine already has accessors for what you need to read.",
        }
        yield Task(slug=f"{i + 1:02d}-{style}", prompt=asks[style], difficulty=d, start=start, hidden=hidden, solution={"src/Skyline.java": full["src/Skyline.java"]},
                   verify=_scen.VERIFY[LANG], tags=["renderer", "snapshot", "falling-blocks"], notes={"rules": r, "style": style})
