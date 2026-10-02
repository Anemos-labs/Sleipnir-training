"""Forge (javascript): an idle crafting economy with an exact production chain, caps and quadratic upgrade costs.
Build, fix and feature tasks (achievements, rebirth, buy queue); a python model cross-checks the reference."""
from __future__ import annotations

import json

from fx import Task, dd, family

from . import _kit, _scen
from ._kit import Bug

LANG = "javascript"
GAME = "Forge"
DEFAULT = dict(START=60, CAP=500, PRICE=3, ORE_PER=2, COAL_PER=1)
BUILDINGS = ["miner", "stoker", "smelter", "market"]
COST = {"miner": (10, 5), "stoker": (12, 6), "smelter": (30, 15), "market": (40, 20)}


def header(r: dict) -> str:
    return dd(f'''
        // ---- house rules for this forge (they are part of the specification, see README.md) ----
        const START_COINS = {r["START"]};
        const CAP = {r["CAP"]};
        const PRICE = {r["PRICE"]};
        const ORE_PER_INGOT = {r["ORE_PER"]};
        const COAL_PER_INGOT = {r["COAL_PER"]};
        // -----------------------------------------------------------------------------------------
    ''')


BODY = dd(r'''
    const BASE = { miner: 10, stoker: 12, smelter: 30, market: 40 };
    const STEP = { miner: 5, stoker: 6, smelter: 15, market: 20 };
    const NAMES = ['miner', 'stoker', 'smelter', 'market'];

    class Forge {
      constructor() {
        this.coins = START_COINS;
        this.ore = 0;
        this.coal = 0;
        this.ingots = 0;
        this.level = { miner: 0, stoker: 0, smelter: 0, market: 0 };
        this.ticks = 0;
      }

      cost(name) {
        const l = this.level[name];
        return BASE[name] + STEP[name] * l * l;
      }

      legalMoves() {
        const out = ['tick', 'mine', 'sell'];
        for (const n of NAMES) if (this.coins >= this.cost(n)) out.push('buy ' + n);
        return out;
      }

      _step() {
        this.ore = Math.min(CAP, this.ore + this.level.miner);
        this.coal = Math.min(CAP, this.coal + this.level.stoker);
        const runs = Math.min(this.level.smelter, Math.floor(this.ore / ORE_PER_INGOT), Math.floor(this.coal / COAL_PER_INGOT));
        this.ore -= runs * ORE_PER_INGOT;
        this.coal -= runs * COAL_PER_INGOT;
        this.ingots = Math.min(CAP, this.ingots + runs);
        const sold = Math.min(this.level.market, this.ingots);
        this.ingots -= sold;
        this.coins += sold * PRICE;
        this.ticks += 1;
      }

      apply(command) {
        const m = /^tick(?: ([1-9][0-9]{0,3}))?$/.exec(command);
        if (m) {
          const n = m[1] === undefined ? 1 : parseInt(m[1], 10);
          if (n > 1000) throw new Error('illegal command: ' + command);
          for (let i = 0; i < n; i++) this._step();
          return 'ticked ' + n;
        }
        if (command === 'mine') {
          this.ore = Math.min(CAP, this.ore + 1);
          return 'mined';
        }
        if (command === 'sell') {
          const n = this.ingots;
          this.coins += n * PRICE;
          this.ingots = 0;
          return 'sold ' + n + ' for ' + n * PRICE;
        }
        const b = /^buy (miner|stoker|smelter|market)$/.exec(command);
        if (b && this.coins >= this.cost(b[1])) {
          const price = this.cost(b[1]);
          this.coins -= price;
          this.level[b[1]] += 1;
          return 'bought ' + b[1] + ' level ' + this.level[b[1]] + ' -' + price;
        }
        throw new Error('illegal command: ' + command);
      }

      render() {
        return [
          'tick ' + this.ticks,
          'coins ' + this.coins + ' ore ' + this.ore + ' coal ' + this.coal + ' ingots ' + this.ingots,
          'levels ' + NAMES.map((n) => n + ' ' + this.level[n]).join(' '),
          'cost ' + NAMES.map((n) => n + ' ' + this.cost(n)).join(' '),
        ].join('\n');
      }
    }

    module.exports = { Forge };
''')


def engine(r: dict) -> str:
    return "'use strict';\n\n" + header(r) + "\n" + BODY


STUB = dd(r'''
    'use strict';

    class Forge {
      constructor() {
        throw new Error('not implemented');
      }

      legalMoves() {
        throw new Error('not implemented');
      }

      apply(command) {
        throw new Error('not implemented');
      }

      render() {
        throw new Error('not implemented');
      }
    }

    module.exports = { Forge };
''')

ADAPTER = {"test/adapter.js": dd(r'''
    // Maps scenario commands onto the engine API (the scenario runner is test/scenarios.test.js).
    'use strict';
    const { Forge } = require('../src/forge');

    class Adapter {
      constructor() {
        this.game = null;
      }

      run(verb, args) {
        switch (verb) {
          case 'new':
            this.game = new Forge();
            return 'ok';
          case 'do': // do <command>: the reply text, or "illegal"
            try {
              return this.game.apply(args);
            } catch (e) {
              return 'illegal';
            }
          case 'legal': { // sorted legal commands joined by "," ("tick" is repeated so that random play lets time pass)
            const moves = this.game.legalMoves().slice().sort();
            return moves.concat(['tick', 'tick', 'tick', 'tick', 'tick', 'tick']).join(',');
          }
          case 'render':
            return this.game.render();
          default:
            throw new Error('unknown verb ' + verb);
        }
      }
    }

    module.exports = { Adapter };
''')}


class Model:
    def __init__(self, r: dict):
        self.r = r
        self.coins = r["START"]
        self.ore = self.coal = self.ingots = self.ticks = 0
        self.level = {b: 0 for b in BUILDINGS}

    def cost(self, b):
        return COST[b][0] + COST[b][1] * self.level[b] ** 2

    def legal(self):
        return ["tick", "mine", "sell"] + [f"buy {b}" for b in BUILDINGS if self.coins >= self.cost(b)]

    def step(self):
        r = self.r
        self.ore = min(r["CAP"], self.ore + self.level["miner"])
        self.coal = min(r["CAP"], self.coal + self.level["stoker"])
        runs = min(self.level["smelter"], self.ore // r["ORE_PER"], self.coal // r["COAL_PER"])
        self.ore -= runs * r["ORE_PER"]
        self.coal -= runs * r["COAL_PER"]
        self.ingots = min(r["CAP"], self.ingots + runs)
        sold = min(self.level["market"], self.ingots)
        self.ingots -= sold
        self.coins += sold * r["PRICE"]
        self.ticks += 1

    def apply(self, c):
        import re
        m = re.fullmatch(r"tick(?: ([1-9][0-9]{0,3}))?", c)
        if m:
            n = int(m.group(1) or 1)
            if n > 1000:
                return None
            for _ in range(n):
                self.step()
            return f"ticked {n}"
        if c == "mine":
            self.ore = min(self.r["CAP"], self.ore + 1)
            return "mined"
        if c == "sell":
            n = self.ingots
            self.coins += n * self.r["PRICE"]
            self.ingots = 0
            return f"sold {n} for {n * self.r['PRICE']}"
        m = re.fullmatch(r"buy (miner|stoker|smelter|market)", c)
        if m and self.coins >= self.cost(m.group(1)):
            p = self.cost(m.group(1))
            self.coins -= p
            self.level[m.group(1)] += 1
            return f"bought {m.group(1)} level {self.level[m.group(1)]} -{p}"
        return None

    def render(self):
        return "\\n".join([f"tick {self.ticks}", f"coins {self.coins} ore {self.ore} coal {self.coal} ingots {self.ingots}",
                          "levels " + " ".join(f"{b} {self.level[b]}" for b in BUILDINGS), "cost " + " ".join(f"{b} {self.cost(b)}" for b in BUILDINGS)])


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
                m = Model(r)
            elif verb == "do":
                got = m.apply(args)
                assert (got if got is not None else "illegal") == want, f"model/engine disagree on {cmd}: {got!r} vs {want!r}"
            elif verb == "legal":
                got = ",".join(sorted(m.legal()) + ["tick"] * 6)
                assert got == want, f"legal disagree: {got!r} vs {want!r}"
            elif verb == "render":
                assert m.render() == want, f"render disagree:\n{m.render()}\n{want}"
            cmd = None


def policy(rng, r: dict, steps: int, thrift: int) -> list[str]:
    """Buys buildings in a rough order of usefulness when affordable, otherwise waits for a few ticks."""
    m = Model(r)
    out = []
    order = ["miner", "stoker", "smelter", "market", "miner", "stoker", "smelter", "market"]
    for _ in range(steps):
        legal = m.legal()
        pick = None
        want = sorted(BUILDINGS, key=lambda b: (m.level[b], order.index(b)))
        for b in want:
            if f"buy {b}" in legal and rng.randrange(100) >= thrift:
                pick = f"buy {b}"
                break
        if pick is None:
            pick = rng.choice(["tick", "tick 3", "tick 10", "tick 1", "mine", "tick 25", "tick 100", "sell", "sell", "tick 10", "tick 7"])
        m.apply(pick)
        out.append(pick)
    return out


def scripts(rng, r: dict) -> dict[str, str]:
    parts = []
    for i in range(5):
        cmds = policy(rng, r, 90, thrift=[0, 20, 50, 10, 70][i])
        parts.append(f"# scenario policy {i + 1}\n> new\n> render\n" + "\n".join(f"> do {c}" + ("\n> render" if k % 6 == 5 else "") for k, c in enumerate(cmds)) + "\n> render")
    parts.append("# scenario random\n> new\n~ rand 300 41 every=6 emit=render junk=tick 0|tick 1001|tick -1|tick 05|buy|buy farm|Mine|tick  2|tick 1000")
    for kind, n_mine in (("coal limited", 30), ("coal limited again", 12)):
        parts.append(f"# scenario {kind}\n> new\n> do buy stoker\n> do buy smelter\n" + "\n".join(["> do mine"] * n_mine) + "\n> render\n" + "\n".join(["> do tick 3", "> render"] * 6) + "\n> do sell\n> render")
    parts.append("# scenario caps\n> new\n" + "\n".join(["> do mine"] * 3 + ["> do buy miner"] + ["> do tick 400"] * 3 + ["> render", "> do tick 1000", "> render", "> do tick 1001", "> do tick 0", "> do tick 07", "> do tick", "> do tick 999", "> render"]))
    parts.append("# scenario a rich forge\n> new\n" + "\n".join(["> do buy miner", "> do buy stoker", "> do tick 30", "> do buy smelter", "> do tick 40", "> do buy market", "> do tick 300", "> render"]
                                                           + ["> do buy miner"] * 6 + ["> do tick 300", "> render"] + ["> do buy market"] * 6 + ["> do tick 1000", "> render", "> do tick 1000", "> render"]))
    return {"hidden_games": "\n".join(parts) + "\n"}


def example_script() -> str:
    return dd('''
        # scenario first steps
        > new
        > render
        > legal
        > do mine
        > do buy miner
        > do tick 4
        > render
        > do buy stoker
        > do tick
        > do buy farm
        > do sell
        > render
    ''')


def readme(r: dict) -> str:
    s = []
    s.append("# Forge\n\nAn idle forge: miners dig ore, stokers make coal, smelters turn them into ingots, the market sells ingots for coins, coins buy better buildings. The engine is headless: a `Forge` object, commands as strings, exact text for every reply. "
             "Everything is integer arithmetic.\n")
    s.append(f"## State\n\nResources are integers: `coins`, `ore`, `coal`, `ingots`; the first start at 0 and `coins` starts at {r['START']}. `ore`, `coal` and `ingots` can never exceed the *cap* {r['CAP']}: whenever one of them would go above it, it is cut back to the cap "
             "(extra units are lost). `coins` have no cap. There are four buildings, each with a *level* starting at 0: `miner`, `stoker`, `smelter`, `market`. The forge counts `ticks` (0 at the start).\n\n"
             "The cost of the next level of a building with current level `L` is `base + step * L * L`:\n\n| building | base | step |\n|---|---|---|\n| `miner` | 10 | 5 |\n| `stoker` | 12 | 6 |\n| `smelter` | 30 | 15 |\n| `market` | 40 | 20 |\n")
    s.append(f"## One tick\n\nIn this order:\n\n1. `ore` grows by the miner level (then cut to the cap).\n2. `coal` grows by the stoker level (then cut to the cap).\n"
             f"3. The smelters work: `runs = min(smelter level, floor(ore / {r['ORE_PER']}), floor(coal / {r['COAL_PER']}))`; `ore` goes down by `{r['ORE_PER']} * runs`, `coal` by `{r['COAL_PER']} * runs`, `ingots` grows by `runs` (then cut to the cap).\n"
             f"4. The market sells: `sold = min(market level, ingots)`; `ingots` goes down by `sold` and `coins` grows by `sold * {r['PRICE']}`.\n5. `ticks` grows by 1.\n")
    s.append("## Commands\n\nCommands are exact strings:\n\n* `tick` or `tick <n>` with `n` a decimal integer from 1 to 1000 written without sign or leading zeros (`tick 7`, `tick 250`): run that many ticks (`tick` is `tick 1`). Reply `ticked <n>`.\n"
             "* `mine`: `ore` grows by 1 (cut to the cap). No tick passes. Reply `mined`.\n"
             f"* `sell`: sell every ingot by hand: `coins` grows by `ingots * {r['PRICE']}`, `ingots` becomes 0. No tick passes. Reply `sold <n> for <coins gained>` (also when `n` is 0).\n"
             "* `buy <building>`: legal when `coins` are at least the cost of the building's next level. The cost is paid and the level grows. Reply `bought <building> level <new level> -<cost paid>`.\n\n"
             "Anything else (other numbers, other words, other spacing or case, buying something unaffordable) is illegal: the engine throws and nothing changes. `legalMoves()` returns `tick`, `mine`, `sell` and a `buy` command for every affordable building (in the order of the table above).\n")
    s.append("## API (`src/forge.js`, CommonJS)\n\n```js\nconst { Forge } = require('./src/forge');\nconst f = new Forge();\nf.legalMoves()    // array of command strings: 'tick', 'mine', 'buy miner', ...\nf.apply(command)  // runs a legal command and returns the reply text; throws an Error otherwise (state unchanged)\nf.render()        // the status text (below)\n```\n")
    m = Model(r)
    for c in ("buy miner", "tick 6", "buy stoker", "tick 3"):
        m.apply(c)
    s.append("### `render()`\n\nFour lines joined by `\\n` (no trailing newline): `tick <ticks>`; `coins <coins> ore <ore> coal <coal> ingots <ingots>`; `levels miner <l> stoker <l> smelter <l> market <l>`; `cost miner <c> stoker <c> smelter <c> market <c>` (the cost of the next level of each building). Example "
             "(after `buy miner`, `tick 6`, `buy stoker`, `tick 3`):\n\n```\n" + m.render().replace("\\n", "\n") + "\n```\n")
    s.append("## Tests\n\n`node --test test/*.test.js` replays the scenario files in `test/data/` (`test/adapter.js` shows how the API is called; the format is described at the top of `test/scenarios.test.js`).\n")
    return "\n".join(s)


def project(r: dict) -> dict[str, str]:
    return {"src/forge.js": engine(r), ".gitignore": _kit.GITIGNORE[LANG]}


def _variants(n: int) -> list[dict]:
    plan = [dict(), dict(PRICE=4, CAP=200, START=70), dict(ORE_PER=3, COAL_PER=2, START=80), dict(CAP=60, PRICE=2, START=55), dict(ORE_PER=3, PRICE=5, CAP=1000, START=65), dict(CAP=120, COAL_PER=3, ORE_PER=2, PRICE=6, START=75)]
    return [{**DEFAULT, **o} for o in plan[:n]]


@family("games-forge-build", category="games", lang="javascript", kind="greenfield", n=6,
        summary="build the Forge idle-economy engine: production chain with caps, quadratic upgrade costs, strict command grammar")
def gen_build(rng, n):
    used: list[str] = []
    for i, r in enumerate(_variants(n)):
        sol = project(r)
        hidden = _kit.data_files(LANG, scripts(rng, r), sol, ADAPTER)
        for t in hidden.values():
            crosscheck(t, r)
        vis = _kit.data_files(LANG, {"examples": example_script()}, sol, ADAPTER)
        crosscheck(next(iter(vis.values())), r)
        start = {"README.md": readme(r), "src/forge.js": STUB, ".gitignore": _kit.GITIGNORE[LANG], **_scen.check_files(LANG, ADAPTER), **vis}
        d = 2 + (r["ORE_PER"] != 2 or r["COAL_PER"] != 1) + (r["CAP"] <= 200)
        prompt = _kit.green_prompt(rng, game=GAME, blurb="an idle crafting economy (mine, smelt, sell, upgrade) with storage caps", file="src/forge.js", verify=_scen.VERIFY[LANG], used=used)
        yield Task(slug=f"{i + 1:02d}-cap{r['CAP']}-price{r['PRICE']}-{r['ORE_PER']}ore{r['COAL_PER']}coal", prompt=prompt, difficulty=min(d, 4), start=start, hidden=hidden,
                   solution={"src/forge.js": sol["src/forge.js"]}, verify=_scen.VERIFY[LANG], tags=["idle", "economy", "scenarios"], notes={"rules": r})


BUGS = [
    Bug("cap-ore", "Ore can exceed the storage cap",
        "After a long wait the ore shown is way above the storage cap; coal and ingots respect it but ore doesn't.",
        [("this.ore = Math.min(CAP, this.ore + this.level.miner);", "this.ore = this.ore + this.level.miner;")], difficulty=2, rules=dict(CAP=60)),
    Bug("cost-formula", "Upgrades get expensive too slowly",
        "The second and later levels of a building cost less than the README's formula says; the price list in the status text looks linear.",
        [("return BASE[name] + STEP[name] * l * l;", "return BASE[name] + STEP[name] * l;")], difficulty=1),
    Bug("smelter-runs", "Smelters use too much coal",
        "Smelting stalls: with enough ore and coal for several runs only one smelter run seems to happen, and the coal use looks wrong.",
        [("const runs = Math.min(this.level.smelter, Math.floor(this.ore / ORE_PER_INGOT), Math.floor(this.coal / COAL_PER_INGOT));", "const runs = Math.min(this.level.smelter, Math.floor(this.ore / ORE_PER_INGOT), Math.floor(this.coal / (COAL_PER_INGOT + 1)));")], difficulty=3, rules=dict(COAL_PER=1)),
    Bug("price-multiplier", "Ingots sell for the wrong price",
        "The market pays a different price per ingot than the README: I get less coins than sold ingots times the price.",
        [("this.coins += sold * PRICE;", "this.coins += sold * (PRICE - 1);")], difficulty=1),
    Bug("buy-boundary", "Can't buy when coins equal the cost",
        "I have exactly the coins needed for the next level and the buy is refused (and `buy` isn't in the legal moves); with one more coin it works.",
        [("for (const n of NAMES) if (this.coins >= this.cost(n)) out.push('buy ' + n);", "for (const n of NAMES) if (this.coins > this.cost(n)) out.push('buy ' + n);"),
         ("if (b && this.coins >= this.cost(b[1])) {", "if (b && this.coins > this.cost(b[1])) {")], difficulty=2, rules=dict(START=10)),
    Bug("phase-order", "Ingots are sold before they are made",
        "Ingots made in a tick are only sold one tick later; the market seems to run before the smelters.",
        [("const sold = Math.min(this.level.market, this.ingots);\n    this.ingots -= sold;\n    this.coins += sold * PRICE;", "const sold = Math.min(this.level.market, this.ingots - runs);\n    this.ingots -= sold;\n    this.coins += sold * PRICE;")], difficulty=3),
    Bug("tick-count", "`tick n` runs n-1 ticks",
        "`tick 10` only runs nine ticks (the tick counter and the production both fall one short), and a plain `tick` does nothing at all.",
        [("for (let i = 0; i < n; i++) this._step();", "for (let i = 1; i < n; i++) this._step();")], difficulty=2),
    Bug("grammar-zero", "`tick 05` is accepted",
        "Commands like `tick 05` and `tick 0` are accepted; the README says counts have no leading zeros and start at 1.",
        [("/^tick(?: ([1-9][0-9]{0,3}))?$/", "/^tick(?: ([0-9]{1,4}))?$/")], difficulty=2),
    Bug("tick-limit", "`tick 1000` is refused",
        "The largest allowed tick count is refused: `tick 1000` is illegal while `tick 999` works.",
        [("if (n > 1000) throw", "if (n >= 1000) throw")], difficulty=2),
    Bug("mine-cap", "Manual mining ignores the cap",
        "Mining by hand at the storage cap pushes the ore above the cap.",
        [("this.ore = Math.min(CAP, this.ore + 1);\n      return 'mined';", "this.ore = this.ore + 1;\n      return 'mined';")], difficulty=2, rules=dict(CAP=60)),
    Bug("reply-level", "The buy reply shows the old level",
        "The reply of a purchase reports the level the building had before the purchase.",
        [("this.level[b[1]] += 1;\n      return 'bought ' + b[1] + ' level ' + this.level[b[1]] + ' -' + price;", "this.level[b[1]] += 1;\n      return 'bought ' + b[1] + ' level ' + (this.level[b[1]] - 1) + ' -' + price;")], difficulty=1),
    Bug("sell-keeps", "Selling by hand doesn't empty the warehouse",
        "After `sell` the coins go up but the ingots are still there, so selling again pays for the same ingots twice.",
        [("this.coins += n * PRICE;\n      this.ingots = 0;", "this.coins += n * PRICE;")], difficulty=2),
    Bug("ingot-cap", "Smelting stops when ingots hit the cap",
        "Once the ingots reach the storage cap the smelters stop consuming ore and coal, instead of wasting the excess ingots.",
        [("this.ore -= runs * ORE_PER_INGOT;\n    this.coal -= runs * COAL_PER_INGOT;\n    this.ingots = Math.min(CAP, this.ingots + runs);", "this.ore -= runs * ORE_PER_INGOT;\n    this.coal -= runs * COAL_PER_INGOT;\n    this.ingots = Math.min(CAP, this.ingots + runs);\n    if (this.ingots >= CAP) { this.ore += runs * ORE_PER_INGOT; this.coal += runs * COAL_PER_INGOT; }")], difficulty=3, rules=dict(CAP=40, PRICE=1)),
]

_B = {b.id: b for b in BUGS}
BUGS_ALL = BUGS + [
    _kit.combine(_B["cost-formula"], _B["price-multiplier"], difficulty=2),
    _kit.combine(_B["buy-boundary"], _B["reply-level"], _B["grammar-zero"], difficulty=3),
]


@family("games-forge-fix", category="games", lang="javascript", kind="fix", n=14,
        summary="hand-injected defects in the Forge engine (caps, cost formula, smelting, selling, command grammar)")
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
        ctx = {"files": ["src/forge.js"], "verify": _scen.VERIFY[LANG]}
        yield _kit.bug_task(game=GAME, lang=LANG, base_files=base, tests=tests, hidden=hidden, bug=bug, ctx=ctx, rng=rng, used=used, k=k,
                            tags=["idle", "economy"], extra_notes={"rules": r})


# ----------------------------------------------------------------------------------------------------- features

ACH_EDITS = [
    ("this.ticks = 0;\n  }", "this.ticks = 0;\n    this.produced = 0;\n    this.done = [];\n    this.pending = [];\n  }"),
    ("this.ingots = Math.min(CAP, this.ingots + runs);", "this.ingots = Math.min(CAP, this.ingots + runs);\n    this.produced += runs;"),
    ("this.ticks += 1;\n  }", "this.ticks += 1;\n    this._check();\n  }"),
    ("  apply(command) {\n", "  _check() {\n    const checks = [\n      ['first-ingot', () => this.produced >= 1],\n      ['rich', () => this.coins >= 100],\n      ['hoarder', () => this.ore === CAP || this.coal === CAP || this.ingots === CAP],\n      ['tycoon', () => NAMES.every((n) => this.level[n] >= 3)],\n    ];\n    for (const [name, ok] of checks) {\n      if (!this.done.includes(name) && ok()) {\n        this.done.push(name);\n        this.pending.push(name + '@' + this.ticks);\n      }\n    }\n  }\n\n  achievements() {\n    return this.done.slice();\n  }\n\n  apply(command) {\n    const reply = this._apply(command);\n    if (command.startsWith('buy ')) this._check();\n    return reply + this.pending.splice(0).map((s) => '; achieved ' + s).join('');\n  }\n\n  _apply(command) {\n"),
    ("'levels ' + NAMES.map((n) => n + ' ' + this.level[n]).join(' '),\n          'cost ' + NAMES.map((n) => n + ' ' + this.cost(n)).join(' '),\n        ]", "'levels ' + NAMES.map((n) => n + ' ' + this.level[n]).join(' '),\n          'cost ' + NAMES.map((n) => n + ' ' + this.cost(n)).join(' '),\n          'achieved ' + (this.done.length ? this.done.join(' ') : 'none'),\n        ]"),
]

REBIRTH_AT = 250
REBIRTH_EDITS = [
    ("this.ticks = 0;\n  }", "this.ticks = 0;\n    this.mult = 1;\n    this.earned = 0;\n  }"),
    ("this.ore = Math.min(CAP, this.ore + this.level.miner);", "this.ore = Math.min(CAP, this.ore + this.level.miner * this.mult);"),
    ("this.coal = Math.min(CAP, this.coal + this.level.stoker);", "this.coal = Math.min(CAP, this.coal + this.level.stoker * this.mult);"),
    ("this.coins += sold * PRICE;\n    this.ticks += 1;", "this.coins += sold * PRICE;\n    this.earned += sold * PRICE;\n    this.ticks += 1;"),
    ("this.coins += n * PRICE;\n          this.ingots = 0;", "this.coins += n * PRICE;\n          this.earned += n * PRICE;\n          this.ingots = 0;"),
    ("for (const n of NAMES) if (this.coins >= this.cost(n)) out.push('buy ' + n);", "for (const n of NAMES) if (this.coins >= this.cost(n)) out.push('buy ' + n);\n    if (this.earned >= " + str(REBIRTH_AT) + ") out.push('rebirth');"),
    ("if (command === 'mine') {", "if (command === 'rebirth' && this.earned >= " + str(REBIRTH_AT) + ") {\n          this.coins = START_COINS;\n          this.ore = 0;\n          this.coal = 0;\n          this.ingots = 0;\n          this.level = { miner: 0, stoker: 0, smelter: 0, market: 0 };\n          this.earned = 0;\n          this.mult += 1;\n          return 'reborn x' + this.mult;\n        }\n        if (command === 'mine') {"),
    ("'cost ' + NAMES.map((n) => n + ' ' + this.cost(n)).join(' '),\n        ]", "'cost ' + NAMES.map((n) => n + ' ' + this.cost(n)).join(' '),\n          'multiplier ' + this.mult,\n        ]"),
]

QUEUE_EDITS = [
    ("this.ticks = 0;\n  }", "this.ticks = 0;\n    this.queue = [];\n    this.auto = [];\n  }"),
    ("_step() {\n", "_step() {\n    while (this.queue.length > 0 && this.coins >= this.cost(this.queue[0])) {\n      const name = this.queue.shift();\n      this.coins -= this.cost(name);\n      this.level[name] += 1;\n      this.auto.push('auto ' + name + ' level ' + this.level[name]);\n    }\n"),
    ("for (let i = 0; i < n; i++) this._step();\n          return 'ticked ' + n;", "for (let i = 0; i < n; i++) this._step();\n          return 'ticked ' + n + this.auto.splice(0).map((s) => '; ' + s).join('');"),
    ("for (const n of NAMES) if (this.coins >= this.cost(n)) out.push('buy ' + n);", "for (const n of NAMES) if (this.coins >= this.cost(n)) out.push('buy ' + n);\n    if (this.queue.length < 5) for (const n of NAMES) out.push('queue ' + n);"),
    ("if (command === 'mine') {", "const q = /^queue (miner|stoker|smelter|market)$/.exec(command);\n        if (q && this.queue.length < 5) {\n          this.queue.push(q[1]);\n          return 'queued ' + q[1] + ' (' + this.queue.length + ')';\n        }\n        if (command === 'mine') {"),
    ("'cost ' + NAMES.map((n) => n + ' ' + this.cost(n)).join(' '),\n        ]", "'cost ' + NAMES.map((n) => n + ' ' + this.cost(n)).join(' '),\n          'queue ' + (this.queue.length ? this.queue.join(' ') : 'empty'),\n        ]"),
]

FORGE_FEATURES = [
    dict(key="achievements", d=3, rules=dict(CAP=60), edits=ACH_EDITS,
         ask="Add achievements to the Forge engine: a few named milestones that unlock once, are announced in the reply of the command that unlocked them, are listed on the status text and are available through `achievements()`. The exact list, the order of the checks and the formats are in the new README.md section.",
         readme="""## Feature to add: achievements

There are four achievements, checked in this order after every tick (each of the ticks of a `tick n`, after its own step) and after every successful `buy` — not after `mine`, `sell` or `queue`: `first-ingot` (the smelters have made at least one ingot so far, in total), `rich` (`coins >= 100`), `hoarder` (at least one of `ore`, `coal`, `ingots` is exactly at the cap) and `tycoon` (all four buildings have level 3 or more).
An achievement unlocks once; unlocking appends `; achieved <name>@<tick>` to the reply of the command, where `<tick>` is the value of `ticks` at that moment (after the tick that unlocked it), in the order the achievements unlocked. `achievements()` returns the unlocked names in unlock order (an array). `render()` gets a fifth line `achieved <names separated by spaces>`, or `achieved none`."""),
    dict(key="rebirth", d=4, rules=dict(CAP=200), edits=REBIRTH_EDITS,
         ask="Add a prestige mechanic to the Forge engine: after earning enough coins you can `rebirth`, which resets the forge but makes miners and stokers more productive for good. The README.md section has the rules; keep everything else as it is.",
         readme=f"""## Feature to add: rebirth

The forge now tracks `earned`: the total coins that came from sales (ingots sold by the market in a tick, and by `sell`) since the last rebirth, and a `multiplier` that starts at 1. The multiplier multiplies what miners and stokers produce per tick (`ore += miner level * multiplier`, `coal += stoker level * multiplier`, then cut to the cap).
New command `rebirth`, legal exactly when `earned >= {REBIRTH_AT}`: `coins` go back to the starting amount, `ore`, `coal` and `ingots` to 0, all buildings to level 0, `earned` to 0, `multiplier` grows by 1, `ticks` is not touched. Reply `reborn x<new multiplier>`. `legalMoves()` lists `rebirth` (after the `buy` commands) when it is legal. `render()` gets a fifth line `multiplier <multiplier>`."""),
    dict(key="queue", d=4, rules={}, edits=QUEUE_EDITS,
         ask="Add a shopping queue to the Forge engine: `queue <building>` puts a purchase in line and the forge buys it by itself as soon as it can afford it. The README.md section describes the order of things inside a tick and the new text formats.",
         readme="""## Feature to add: buy queue

The forge has a *queue* of building names (at most 5). New command `queue <building>` (`miner`, `stoker`, `smelter` or `market`), legal while the queue has fewer than 5 entries: it appends the building. Reply `queued <building> (<queue length>)`. `legalMoves()` lists a `queue <building>` for each of the four buildings (in table order, after the `buy` commands) while the queue is not full.
At the very start of every tick (before step 1 of *One tick*), the forge buys from the head of the queue: while the queue is not empty and `coins` are at least the cost of the first entry, that entry is removed, its cost is paid and its level grows. Each such purchase is reported by the reply of the `tick` command: `ticked <n>` followed by `; auto <building> level <new level>` for every automatic purchase of those ticks, in the order they happened. `render()` gets a fifth line: `queue ` and the queued names separated by spaces, or `queue empty`."""),
]


def forge_feature_adapter(key: str) -> dict[str, str]:
    a = ADAPTER["test/adapter.js"]
    if key == "achievements":
        target = "      default:\n"
        assert a.count(target) == 1
        block = "      case 'achievements': { // the unlocked names joined by \",\" (\"-\" when none)\n        const done = this.game.achievements();\n        return done.length ? done.join(',') : '-';\n      }\n"
        a = a.replace(target, block + target)
    return {"test/adapter.js": a}


def forge_feature_scripts(rng, key: str, r: dict) -> dict[str, str]:
    base = scripts(rng, r)
    extra = []
    for i in range(3):
        cmds = policy(rng, r, 110, thrift=[0, 15, 40][i])
        out = [f"# scenario {key} policy {i + 1}", "> new"]
        for k, c in enumerate(cmds):
            out.append(f"> do {c}")
            if key == "rebirth" and k % 23 == 22:
                out += ["> do rebirth", "> render"]
            if key == "queue" and k % 5 == 3:
                out.append("> do queue " + rng.choice(BUILDINGS))
            if k % 9 == 8:
                out.append("> render")
        out += ["> render"] + (["> achievements"] if key == "achievements" else [])
        extra.append("\n".join(out))
    if key == "achievements":
        extra.append("# scenario milestones\n> new\n" + "\n".join(["> do mine", "> do buy miner", "> do buy stoker", "> do buy smelter", "> do tick 30", "> achievements", "> do tick 200", "> do buy market", "> do tick 500", "> achievements", "> render", "> do tick 1000", "> achievements", "> render"]))
        extra.append("# scenario no check after mine and sell\n> new\n" + "\n".join(["> do buy miner", "> do buy stoker", "> do buy smelter"] + ["> do mine"] * 70 + ["> achievements", "> do sell", "> achievements", "> do tick", "> achievements", "> render"]))
    if key == "rebirth":
        extra.append("# scenario rebirth\n> new\n" + "\n".join(["> do rebirth", "> do buy miner", "> do buy stoker", "> do buy smelter", "> do tick 100", "> do sell", "> do buy market", "> do tick 300", "> render", "> legal", "> do rebirth", "> render", "> do buy miner", "> do tick 50", "> render", "> do rebirth", "> do tick 400", "> do buy smelter", "> do buy market", "> do tick 600", "> do sell", "> render", "> do rebirth", "> render"]))
    if key == "queue":
        extra.append("# scenario queue\n> new\n" + "\n".join(["> do queue miner", "> do queue stoker", "> do queue smelter", "> do queue market", "> do queue miner", "> do queue miner", "> render", "> do tick", "> render", "> do tick 5", "> do tick 40", "> render", "> do buy miner", "> do queue stoker", "> do tick 100", "> render", "> legal"]))
    return {**base, f"hidden_{key}": "\n".join(extra) + "\n"}


def forge_feature_vis(key: str) -> str:
    return {
        "achievements": "# scenario achievements\n> new\n> do buy miner\n> do buy stoker\n> do buy smelter\n> do tick 12\n> achievements\n> render\n",
        "rebirth": "# scenario rebirth\n> new\n> do rebirth\n> render\n",
        "queue": "# scenario queue\n> new\n> do queue miner\n> do queue stoker\n> render\n> do tick 3\n> render\n",
    }[key]


@family("games-forge-feature", category="games", lang="javascript", kind="feature", n=3,
        summary="add achievements, a rebirth (prestige) mechanic or an automatic buy queue to the Forge engine")
def gen_feature(rng, n):
    for i, v in enumerate(FORGE_FEATURES[:n]):
        key = v["key"]
        r = {**DEFAULT, **v["rules"]}
        base = project(r)
        src = _kit.apply_bug(base["src/forge.js"], Bug("feature", "", "", v["edits"]))
        sol = {"src/forge.js": src, ".gitignore": base[".gitignore"]}
        adapter = forge_feature_adapter(key)
        hidden = _kit.data_files(LANG, forge_feature_scripts(rng, key, r), sol, adapter)
        vis = _kit.data_files(LANG, {"examples": example_script(), "feature": forge_feature_vis(key)}, sol, adapter)
        start = {"README.md": readme(r).replace("## Tests\n", v["readme"].rstrip("\n") + "\n\n## Tests\n"), "src/forge.js": base["src/forge.js"], ".gitignore": base[".gitignore"], **_scen.check_files(LANG, adapter), **vis}
        yield Task(slug=f"{i + 1:02d}-{key}", prompt=v["ask"] + (" Existing behaviour must stay exactly the same." if i % 2 == 0 else ""), difficulty=v["d"], start=start, hidden=hidden, solution={"src/forge.js": src},
                   verify=_scen.VERIFY[LANG], tags=["idle", "economy", "feature"], notes={"feature": key, "rules": r})
