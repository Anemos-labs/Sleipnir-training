"""Barnacle (rust): a three-player trick-taking card game with house rules (rotating trump, jack bonuses, optional follow-suit),
an exact LCG Fisher-Yates shuffle and exact render text. Build and fix tasks; a python model cross-checks the reference."""
from __future__ import annotations

import json

from fx import Task, dd, family

from . import _kit, _scen
from ._kit import Bug

LANG = "rust"
GAME = "Barnacle"
PKG = "barnacle"
DEFAULT = dict(JACK=2, LAST=0, FOLLOW=True, CYCLE=True)
RANKS = "9TJQKA"
SUITS = "CDHS"


def header(r: dict) -> str:
    return dd(f'''
        // ---- house rules for this table (they are part of the specification, see README.md) ----
        pub const JACK_BONUS: u32 = {r["JACK"]};
        pub const LAST_TRICK_BONUS: u32 = {r["LAST"]};
        pub const MUST_FOLLOW: bool = {"true" if r["FOLLOW"] else "false"};
        pub const ROTATING_TRUMP: bool = {"true" if r["CYCLE"] else "false"};
        // ---------------------------------------------------------------------------------------
    ''')


BODY = dd(r'''
    const RANKS: &str = "9TJQKA";
    const SUITS: &str = "CDHS";

    /// One game of Barnacle.
    pub struct Game {
        hands: [Vec<String>; 3],
        table: Vec<(usize, String)>,
        leader: usize,
        trick: usize,
        scores: [u32; 3],
        state: u64,
        over: bool,
    }

    fn rank_of(card: &str) -> usize {
        RANKS.find(card.chars().next().unwrap()).unwrap()
    }

    fn suit_of(card: &str) -> char {
        card.chars().nth(1).unwrap()
    }

    fn sort_key(card: &str) -> (usize, usize) {
        (SUITS.find(suit_of(card)).unwrap(), rank_of(card))
    }

    impl Game {
        /// A new game: the deck is shuffled with the generator seeded by `seed` and dealt.
        pub fn new(seed: u32) -> Game {
            let mut deck: Vec<String> = Vec::new();
            for s in SUITS.chars() {
                for r in RANKS.chars() {
                    deck.push(format!("{}{}", r, s));
                }
            }
            let mut g = Game {
                hands: [Vec::new(), Vec::new(), Vec::new()],
                table: Vec::new(),
                leader: 0,
                trick: 1,
                scores: [0; 3],
                state: (seed as u64) % 2147483648,
                over: false,
            };
            for i in (1..deck.len()).rev() {
                let j = ((g.next() >> 16) % (i as u64 + 1)) as usize;
                deck.swap(i, j);
            }
            for (k, card) in deck.into_iter().enumerate() {
                g.hands[k % 3].push(card);
            }
            for h in g.hands.iter_mut() {
                h.sort_by_key(|c| sort_key(c));
            }
            g
        }

        fn next(&mut self) -> u64 {
            self.state = (self.state * 1103515245 + 12345) % 2147483648;
            self.state
        }

        fn trump(&self) -> char {
            if ROTATING_TRUMP {
                SUITS.chars().nth((self.trick - 1) % 4).unwrap()
            } else {
                'H'
            }
        }

        fn to_play(&self) -> usize {
            (self.leader + self.table.len()) % 3
        }

        /// The cards the player to move may play, as `play <card>` commands.
        pub fn legal_moves(&self) -> Vec<String> {
            if self.over {
                return Vec::new();
            }
            let hand = &self.hands[self.to_play()];
            let mut cards: Vec<&String> = hand.iter().collect();
            if MUST_FOLLOW && !self.table.is_empty() {
                let led = suit_of(&self.table[0].1);
                if hand.iter().any(|c| suit_of(c) == led) {
                    cards.retain(|c| suit_of(c) == led);
                }
            }
            cards.into_iter().map(|c| format!("play {}", c)).collect()
        }

        /// Plays a card; returns the events or an error for an illegal command.
        pub fn apply(&mut self, cmd: &str) -> Result<String, String> {
            if !self.legal_moves().iter().any(|m| m == cmd) {
                return Err(format!("illegal command: {}", cmd));
            }
            let card = cmd[5..].to_string();
            let p = self.to_play();
            let pos = self.hands[p].iter().position(|c| *c == card).unwrap();
            self.hands[p].remove(pos);
            self.table.push((p, card.clone()));
            let mut ev = vec![format!("P{} plays {}", p, card)];
            if self.table.len() == 3 {
                let trump = self.trump();
                let led = suit_of(&self.table[0].1);
                let mut winner = self.table[0].0;
                let mut best: Option<(bool, usize)> = None;
                for (who, c) in &self.table {
                    let is_trump = suit_of(c) == trump;
                    if !is_trump && suit_of(c) != led {
                        continue;
                    }
                    let key = (is_trump, rank_of(c));
                    if best.map_or(true, |b| key > b) {
                        best = Some(key);
                        winner = *who;
                    }
                }
                let jacks = self.table.iter().filter(|(_, c)| c.starts_with('J')).count() as u32;
                let mut pts = 1 + JACK_BONUS * jacks;
                if self.trick == 8 {
                    pts += LAST_TRICK_BONUS;
                }
                self.scores[winner] += pts;
                ev.push(format!("trick {} won by P{} +{}", self.trick, winner, pts));
                self.table.clear();
                self.leader = winner;
                if self.trick == 8 {
                    self.over = true;
                    let top = *self.scores.iter().max().unwrap();
                    let best: Vec<usize> = (0..3).filter(|&i| self.scores[i] == top).collect();
                    ev.push(if best.len() == 1 { format!("game over: P{} wins", best[0]) } else { "game over: draw".to_string() });
                } else {
                    self.trick += 1;
                }
            }
            Ok(ev.join("; "))
        }

        pub fn scores(&self) -> [u32; 3] {
            self.scores
        }

        pub fn is_over(&self) -> bool {
            self.over
        }

        /// The table as text.
        pub fn render(&self) -> String {
            let mut lines: Vec<String> = Vec::new();
            if self.over {
                lines.push(format!("over after {} tricks", self.trick));
            } else {
                lines.push(format!("trick {}/8 trump {} to play P{}", self.trick, self.trump(), self.to_play()));
            }
            for p in 0..3 {
                lines.push(format!("P{}: {}", p, self.hands[p].join(" ")));
            }
            if self.table.is_empty() {
                lines.push("table: -".to_string());
            } else {
                lines.push(format!("table: {}", self.table.iter().map(|(w, c)| format!("P{}={}", w, c)).collect::<Vec<_>>().join(" ")));
            }
            lines.push(format!("scores: {} {} {}", self.scores[0], self.scores[1], self.scores[2]));
            lines.join("\n")
        }
    }
''')


def engine(r: dict) -> str:
    return "//! Barnacle: a three-player trick-taking game. The rules are in README.md.\n\n" + header(r) + "\n" + BODY


STUB = dd(r'''
    //! Barnacle: a three-player trick-taking game. The rules and the API are in README.md.

    /// One game of Barnacle.
    pub struct Game {}

    impl Game {
        pub fn new(seed: u32) -> Game {
            todo!()
        }

        pub fn legal_moves(&self) -> Vec<String> {
            todo!()
        }

        pub fn apply(&mut self, cmd: &str) -> Result<String, String> {
            todo!()
        }

        pub fn scores(&self) -> [u32; 3] {
            todo!()
        }

        pub fn is_over(&self) -> bool {
            todo!()
        }

        pub fn render(&self) -> String {
            todo!()
        }
    }
''')

ADAPTER = {"tests/adapter/mod.rs": dd(r'''
    // Maps scenario commands onto the engine API (the scenario runner is tests/scenarios.rs).
    use barnacle::Game;

    pub struct Adapter {
        game: Option<Game>,
    }

    impl Adapter {
        pub fn new() -> Adapter {
            Adapter { game: None }
        }

        pub fn run(&mut self, verb: &str, args: &str) -> String {
            match verb {
                // new <seed>
                "new" => {
                    self.game = Some(Game::new(args.parse().unwrap()));
                    "ok".to_string()
                }
                // do <command>: the event text, or "illegal"
                "do" => match self.game.as_mut().unwrap().apply(args) {
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
                // "<score0> <score1> <score2> <over>"
                "status" => {
                    let g = self.game.as_ref().unwrap();
                    let s = g.scores();
                    format!("{} {} {} {}", s[0], s[1], s[2], if g.is_over() { "yes" } else { "no" })
                }
                _ => panic!("unknown verb {}", verb),
            }
        }
    }
''')}


class Model:
    def __init__(self, seed: int, r: dict):
        self.r = r
        deck = [rk + s for s in SUITS for rk in RANKS]
        self.state = seed % 2147483648
        for i in range(len(deck) - 1, 0, -1):
            self.state = (self.state * 1103515245 + 12345) % 2147483648
            j = (self.state >> 16) % (i + 1)
            deck[i], deck[j] = deck[j], deck[i]
        self.hands = [sorted(deck[k::3], key=lambda c: (SUITS.index(c[1]), RANKS.index(c[0]))) for k in range(3)]
        self.table, self.leader, self.trick, self.scores, self.over = [], 0, 1, [0, 0, 0], False

    def trump(self):
        return SUITS[(self.trick - 1) % 4] if self.r["CYCLE"] else "H"

    def to_play(self):
        return (self.leader + len(self.table)) % 3

    def legal(self):
        if self.over:
            return []
        hand = self.hands[self.to_play()]
        cards = list(hand)
        if self.r["FOLLOW"] and self.table:
            led = self.table[0][1][1]
            if any(c[1] == led for c in hand):
                cards = [c for c in hand if c[1] == led]
        return ["play " + c for c in cards]

    def apply(self, cmd):
        card = cmd[5:]
        p = self.to_play()
        self.hands[p].remove(card)
        self.table.append((p, card))
        ev = ["P%d plays %s" % (p, card)]
        if len(self.table) == 3:
            trump, led = self.trump(), self.table[0][1][1]
            best, winner = None, self.table[0][0]
            for who, c in self.table:
                is_t = c[1] == trump
                if not is_t and c[1] != led:
                    continue
                key = (is_t, RANKS.index(c[0]))
                if best is None or key > best:
                    best, winner = key, who
            jacks = sum(1 for _, c in self.table if c[0] == "J")
            pts = 1 + self.r["JACK"] * jacks + (self.r["LAST"] if self.trick == 8 else 0)
            self.scores[winner] += pts
            ev.append("trick %d won by P%d +%d" % (self.trick, winner, pts))
            self.table = []
            self.leader = winner
            if self.trick == 8:
                self.over = True
                top = max(self.scores)
                w = [i for i in range(3) if self.scores[i] == top]
                ev.append("game over: P%d wins" % w[0] if len(w) == 1 else "game over: draw")
            else:
                self.trick += 1
        return "; ".join(ev)

    def render(self):
        lines = ["over after %d tricks" % self.trick if self.over else "trick %d/8 trump %s to play P%d" % (self.trick, self.trump(), self.to_play())]
        lines += ["P%d: %s" % (p, " ".join(self.hands[p])) for p in range(3)]
        lines.append("table: -" if not self.table else "table: " + " ".join("P%d=%s" % (w, c) for w, c in self.table))
        lines.append("scores: %d %d %d" % tuple(self.scores))
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
                got = "%d %d %d %s" % (*m.scores, "yes" if m.over else "no")
                assert got == want, f"status disagree {got!r} vs {want!r}"
            elif verb == "render":
                assert m.render() == want, f"render disagree:\n{m.render()}\n{want}"
            cmd = None


def scripts(rng, r: dict) -> dict[str, str]:
    parts = []
    for i, sd in enumerate((1, 2, 3, 4, 5, 6, 7, 2147483647, 4294967295, 12345)):
        parts.append(f"# scenario game seed {sd}\n> new {sd}\n> render\n~ rand 60 {sd * 7 + 1} every=2 emit=render,legal,status junk=play ZZ|play|play 9C |Play 9C|play 9c|pass|play AH AH")
    parts.append("# scenario follow suit probing\n> new 9\n> legal\n> do play XX\n> render\n> status")
    return {"hidden_games": "\n".join(parts) + "\n"}


def example_script() -> str:
    return dd('''
        # scenario a deal
        > new 1
        > render
        > legal
        # scenario one trick
        > new 5
        > legal
        ~ rand 3 2 emit=render,status
        # scenario a whole game
        > new 8
        ~ rand 40 3 emit=status
    ''')


def readme(r: dict) -> str:
    s = []
    s.append("# Barnacle\n\nA trick-taking card game for three players with a rotating trump suit. The engine is headless: a `Game` created from a seed, a list of legal commands and exact text for every reply.\n")
    s.append("## Deck and deal\n\n24 cards: ranks `9 T J Q K A` (in this order, `9` lowest) in the suits `C D H S`. A card is written rank then suit: `9C`, `TD`, `AS`. The deck starts in this order: all clubs from `9` to `A`, then diamonds, hearts, spades "
             "(`9C TC JC QC KC AC 9D ... AS`).\n\n"
             "Randomness: `state = seed mod 2^31`; `next()` sets `state = (state * 1103515245 + 12345) mod 2^31` and returns the new state. The deck is shuffled by Fisher-Yates from the end: for `i` from 23 down to 1: `j = (next() >> 16) mod (i + 1)`, swap the cards at positions `i` and `j`. "
             "Then the card at position `k` goes to player `k mod 3` (three players `P0`, `P1`, `P2`; 8 cards each). A hand is kept sorted by suit (`C D H S`) and, inside a suit, by rank ascending. Nothing else uses the generator.\n")
    trump = ("The trump suit changes with the trick number: trick 1 `C`, trick 2 `D`, trick 3 `H`, trick 4 `S`, trick 5 `C` again, and so on (`SUITS[(trick - 1) mod 4]`)." if r["CYCLE"]
             else "The trump suit is always hearts (`H`).")
    follow = ("A player must *follow suit*: if the hand holds at least one card of the led suit (the suit of the first card of the trick) only those cards may be played; otherwise any card." if r["FOLLOW"]
              else "There is no obligation to follow suit: any card of the hand may be played at any time.")
    s.append(f"## Play\n\nThere are 8 tricks, numbered from 1. `P0` leads trick 1; the winner of a trick leads the next one. In a trick the players play one card each, in turn order starting with the leader (`P0 P1 P2` wrap around). {follow} {trump}\n\n"
             "Commands are exact strings `play <card>` (for example `play QH`). `legal_moves()` lists the `play` commands the player to move may use (in any order; empty when the game is over). Anything else is illegal.\n")
    s.append(f"### Winning a trick\n\nWhen the third card is played the trick is decided at once. If any card of the trick has the trump suit of this trick, the highest trump wins; otherwise the highest card *of the led suit* wins (cards of other suits never win). "
             f"The winner scores `1 + {r['JACK']} * (number of jacks in the trick)`" + (f" and, for the 8th trick, another {r['LAST']}" if r["LAST"] else "") + ". After trick 8 the game is over: the player with the most points wins; if two or three players share the top score the game is a draw.\n")
    s.append("### Events returned by `apply`\n\n`P<p> plays <card>`; when the card completes a trick `; trick <n> won by P<w> +<points>` follows; after trick 8 `; game over: P<w> wins` or `; game over: draw` is appended too.\n")
    s.append("## API (crate `barnacle`, `src/lib.rs`)\n\n```rust\nuse barnacle::Game;\nlet mut g = Game::new(seed);        // seed: u32\ng.legal_moves() -> Vec<String>\ng.apply(cmd: &str) -> Result<String, String>   // Ok(events), or Err(message) and no change for an illegal command\n"
             "g.scores() -> [u32; 3]\ng.is_over() -> bool\ng.render() -> String\n```\n")
    s.append("### `render()`\n\nLines joined by `\\n` (no trailing newline): `trick <n>/8 trump <suit> to play P<k>` (after the last trick: `over after 8 tricks`); one line per player `P<p>: <cards separated by single spaces, sorted>` (`P<p>: ` with nothing after it when the hand is empty); "
             "`table: ` followed by the cards of the trick in play as `P<p>=<card>` separated by spaces, or `table: -` when the table is empty; `scores: <s0> <s1> <s2>`. Example at the start of a game with seed 1:\n\n```\n" + Model(1, r).render().replace("\\n", "\n") + "\n```\n")
    s.append("## Tests\n\n`cargo test --offline --quiet` replays the scenario files in `tests/data/` (`tests/adapter/mod.rs` shows how the API is called; the format is described at the top of `tests/scenarios.rs`).\n")
    return "\n".join(s)


def project(r: dict) -> dict[str, str]:
    return {"src/lib.rs": engine(r), "Cargo.toml": _kit.cargo_toml(PKG), ".gitignore": _kit.GITIGNORE[LANG]}


def _variants(n: int) -> list[dict]:
    plan = [dict(), dict(CYCLE=False, JACK=3), dict(FOLLOW=False, LAST=3), dict(JACK=3, LAST=2, CYCLE=False), dict(FOLLOW=False, CYCLE=False, JACK=1), dict(LAST=5, JACK=0)]
    return [{**DEFAULT, **o} for o in plan[:n]]


@family("games-barnacle-build", category="games", lang="rust", kind="greenfield", n=6,
        summary="build the Barnacle three-player trick-taking game: exact LCG shuffle, rotating or fixed trump, jack and last-trick bonuses")
def gen_build(rng, n):
    used: list[str] = []
    for i, r in enumerate(_variants(n)):
        sol = project(r)
        hidden = _kit.data_files(LANG, scripts(rng, r), sol, ADAPTER)
        for t in hidden.values():
            crosscheck(t, r)
        vis = _kit.data_files(LANG, {"examples": example_script()}, sol, ADAPTER)
        crosscheck(next(iter(vis.values())), r)
        start = {"README.md": readme(r), "src/lib.rs": STUB, "Cargo.toml": sol["Cargo.toml"], ".gitignore": sol[".gitignore"], **_scen.check_files(LANG, ADAPTER), **vis}
        d = 2 + r["CYCLE"] + r["FOLLOW"] + (r["LAST"] > 0)
        prompt = _kit.green_prompt(rng, game=GAME, blurb="a three-player trick-taking card game with house rules and an exactly specified shuffle", file="src/lib.rs", verify=_scen.VERIFY[LANG], used=used)
        yield Task(slug=f"{i + 1:02d}-" + ("cycle" if r["CYCLE"] else "fixed") + ("-follow" if r["FOLLOW"] else "-free") + f"-j{r['JACK']}l{r['LAST']}", prompt=prompt, difficulty=min(d, 4), start=start, hidden=hidden,
                   solution={"src/lib.rs": sol["src/lib.rs"]}, verify=_scen.VERIFY[LANG], timeout_s=300, tags=["cards", "rng", "scenarios"], notes={"rules": r})


BUGS = [
    Bug("shuffle-bound", "The first card never moves",
        "The shuffle leaves the first card of the deck (the 9 of clubs) where it was; it can never end up anywhere else, so it always goes to the first player.",
        [("for i in (1..deck.len()).rev() {", "for i in (2..deck.len()).rev() {")], difficulty=3),
    Bug("shuffle-mod", "Shuffle indices are drawn from the wrong range",
        "The deals don't match the README's reference shuffle for a given seed: the swap partner of a card is drawn from a range one card too small.",
        [("let j = ((g.next() >> 16) % (i as u64 + 1)) as usize;", "let j = ((g.next() >> 16) % (i as u64)) as usize;")], difficulty=3),
    Bug("rank-order", "Aces count low",
        "The ace loses to every other card of its suit, and in the hands it is sorted before the nine.",
        [('const RANKS: &str = "9TJQKA";', 'const RANKS: &str = "A9TJQK";')], difficulty=1),
    Bug("follow-suit", "A player can ignore the led suit",
        "Players are allowed to play any card even when they hold a card of the suit that was led, on a table where following suit is compulsory.",
        [("if MUST_FOLLOW && !self.table.is_empty() {", "if false && !self.table.is_empty() {")], difficulty=2, rules=dict(FOLLOW=True)),
    Bug("trump-cycle", "The trump suit is one trick behind",
        "The rotating trump is off by one: trick 1 already uses diamonds (or hearts, in the last quarter), shifted by one from the order in the README.",
        [("SUITS.chars().nth((self.trick - 1) % 4).unwrap()", "SUITS.chars().nth(self.trick % 4).unwrap()")], difficulty=2, rules=dict(CYCLE=True)),
    Bug("trump-ignored", "Trumps don't beat the led suit",
        "A trump card played on a trick does not win it if somebody played a higher card of the led suit.",
        [("let key = (is_trump, rank_of(c));", "let key = (false, rank_of(c));")], difficulty=3),
    Bug("jack-count", "Jack bonus only counts once",
        "A trick with two jacks gives the winner the bonus for one jack only.",
        [("let mut pts = 1 + JACK_BONUS * jacks;", "let mut pts = 1 + JACK_BONUS * jacks.min(1);")], difficulty=2, rules=dict(JACK=3)),
    Bug("last-trick", "The last-trick bonus is paid for the wrong trick",
        "The bonus for the final trick is paid on the seventh trick, not the eighth.",
        [("if self.trick == 8 {\n                    pts += LAST_TRICK_BONUS;", "if self.trick == 7 {\n                    pts += LAST_TRICK_BONUS;")], difficulty=2, rules=dict(LAST=3)),
    Bug("deal-order", "Cards are dealt in blocks",
        "The hands are blocks of eight consecutive cards of the shuffled deck instead of one card to each player in turn, so the hands don't match the README's reference deal.",
        [("g.hands[k % 3].push(card);", "g.hands[k / 8].push(card);")], difficulty=2),
    Bug("leader-reset", "The winner doesn't lead the next trick",
        "After a trick the player who won it doesn't necessarily lead the next one: the lead seems to go back to the first player.",
        [("self.leader = winner;", "self.leader = 0;")], difficulty=2),
    Bug("draw-detection", "Ties for the top are not draws",
        "When two players end with the same top score the game says the first of them wins instead of declaring a draw.",
        [('ev.push(if best.len() == 1 { format!("game over: P{} wins", best[0]) } else { "game over: draw".to_string() });', 'ev.push(format!("game over: P{} wins", best[0]));')], difficulty=2),
    Bug("table-render", "The table line shows the wrong player",
        "In the board text the cards on the table are labelled with the player who is to move next instead of the player who played each card.",
        [('self.table.iter().map(|(w, c)| format!("P{}={}", w, c))', 'self.table.iter().map(|(_, c)| format!("P{}={}", (self.leader + 1) % 3, c))')], difficulty=2),
]

_B = {b.id: b for b in BUGS}
BUGS_ALL = BUGS + [
    _kit.combine(_B["rank-order"], _B["jack-count"], difficulty=3),
    _kit.combine(_B["shuffle-mod"], _B["leader-reset"], _B["trump-ignored"], difficulty=4),
]


@family("games-barnacle-fix", category="games", lang="rust", kind="fix", n=14,
        summary="hand-injected defects in the Barnacle engine (shuffle, deal, follow-suit, rotating trump, bonuses, trick winner)")
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
        ctx = {"files": ["src/lib.rs"], "verify": _scen.VERIFY[LANG]}
        yield _kit.bug_task(game=GAME, lang=LANG, base_files=base, tests=tests, hidden=hidden, bug=bug, ctx=ctx, rng=rng, used=used, k=k,
                            tags=["cards", "rng"], timeout_s=300, extra_notes={"rules": r})
