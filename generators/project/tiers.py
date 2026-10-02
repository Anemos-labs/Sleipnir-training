"""project-tiers: a scripted tiered (log-structured) key-value store: memtable, immutable sorted runs, flushes, cascading compactions with
tombstone rules, and lookups that count the runs they probe.  Reference: Python (oracle) and Rust."""
from __future__ import annotations

from fx import family

from generators.project import _kit as K

THEME = "tiers"
TOOLS = ["tiers", "strata", "sedimentd", "layercake", "seamstore", "shelvedb", "lodestore", "cairn"]
KEYS = ["a", "b", "c", "d", "e", "f", "g", "h", "k1", "k2", "k3", "m", "n", "p", "q", "r", "s", "t", "x1", "x2", "zeta", "alpha", "beta", "mu"]
VALS = ["red", "blue", "v1", "v2", "ok", "gone", "7", "42", "x-ray", "a.b", "long_value_1"]

PLAN = [
    dict(lang="rust", mem=3, l0=3, fan=3, levels=3, merge="all", drop="deep-empty", filt=True, allcmd=True),
    dict(lang="python", mem=4, l0=2, fan=3, levels=3, merge="oldest2", drop="last", filt=True, allcmd=False),
    dict(lang="rust", mem=3, l0=2, fan=4, levels=4, merge="oldest2", drop="deep-empty", filt=False, allcmd=True),
    dict(lang="python", mem=5, l0=3, fan=3, levels=2, merge="all", drop="last", filt=False, allcmd=True),
    dict(lang="rust", mem=4, l0=3, fan=3, levels=4, merge="all", drop="last", filt=True, allcmd=False),
    dict(lang="python", mem=3, l0=4, fan=3, levels=3, merge="oldest2", drop="deep-empty", filt=True, allcmd=True),
    dict(lang="rust", mem=5, l0=2, fan=3, levels=3, merge="oldest2", drop="last", filt=False, allcmd=False),
    dict(lang="python", mem=4, l0=2, fan=4, levels=4, merge="all", drop="deep-empty", filt=True, allcmd=True),
]

VOICES = [
    "We want a tiny model of a log-structured key-value store to teach compaction with: a memtable, immutable sorted runs, levels, and compaction rules with tombstones. `README.md` specifies every rule, event line and counter. The program is `{tool}`; write it in {Lang}: {run}. Visible examples: `python3 tests/run_examples.py`. The hidden checks drive long write sequences and compare every flush and compaction line.",
    "build {tool} from README.md ({Lang}). scripted LSM-ish store: put/del/get/scan/flush/compact/dump. {run}. the cascade order (lowest level first), which runs a merge takes, and when tombstones may be dropped are all in the README. examples: `python3 tests/run_examples.py`",
    "Ticket KV-{num}: implement the `{tool}` store simulator (spec: README.md).\n\nLanguage: {Lang}; the program is {run}. Everything printed is part of the contract: flush and compaction event lines, `get` with its probe counts, `dump`, `stats`. Please keep the store logic apart from the command parsing.",
    "Could you write the store simulator described in README.md? Writes go to a memtable that flushes into level-0 runs; levels compact into the next one when they have enough runs. {Lang} please; the program is {run}. `python3 tests/run_examples.py` runs a few examples; the hidden checks are much longer sequences.",
    "Greenfield in {Lang}: `{tool}`, a deterministic simulator of a tiered key-value store. The README defines the write path, the compaction cascade, tombstone dropping, and read probing. {run}. The hidden suite is grouped (writes, compaction, tombstones, reads, manual compaction, errors, sessions) and scored per group.",
    "README.md has the spec for `{tool}`. Please build it in {Lang} ({run}). Careful with: the position of a merged run when a level merges into itself, which version wins inside a merge (newest), and probe counting with and without the key-range filter. Visible examples: `python3 tests/run_examples.py`.",
    "short version: simulated tiered kv store, spec in README.md, {Lang}, call it {tool}. {run}",
    "Please implement the key-value store simulator from README.md in {Lang}, named `{tool}`. How it is run: {run}. Commands come from standard input. It has to be exact about when a flush or compaction happens and what each one prints.",
]


def readme(p: dict, tool: str, lang: str, by_name: dict) -> str:
    o: list[str] = []
    w = o.append
    last = p["levels"] - 1
    w(f"# {tool}: a tiered key-value store simulator\n")
    w(f"`{tool}` simulates a small log-structured key-value store. Writes collect in an in-memory **memtable**; when it is full it is **flushed** into an immutable sorted **run** on level 0; levels with too many runs are **compacted** into the next level. "
      "Nothing is persisted: the program reads a script on standard input, runs it and prints what each command reports, so every rule can be checked exactly.\n")
    w(f"Build and run it as {K.how_to_run(lang, tool)}. Exit status 1 if any `error:` line was printed, otherwise 0.\n")
    w("## 1. Model\n")
    w("* A **key** is 1 to 8 characters from `a-z 0-9 _`; keys compare in byte order. A **value** is 1 to 12 characters from `A-Z a-z 0-9 _ . -`. A key is either live (it has a value) or **deleted**: deleting stores a **tombstone** for the key.")
    w(f"* The **memtable** maps keys to a value or a tombstone. It is **full** when it holds at least **{p['mem']}** keys (tombstones count).")
    w(f"* A **run** is an immutable, sorted map from keys to a value or a tombstone, with a unique **id** (the run counter starts at 1 and every run ever created takes the next number, so a merged run gets a new id), a smallest key `lo` and a largest key `hi`. A run is never empty.")
    w(f"* There are **{p['levels']} levels**, `L0` to `L{last}`. A level holds a list of runs from the oldest to the newest. Every run of `Li` is newer than every run of `Li+1` (data moves down only by compaction), "
      "and *within* a level the list order, not the id, tells which run is newer.")
    w("* A key's current value is the one in the memtable if it is there; otherwise the one in the newest run containing it, searching `L0` (newest run first), then `L1`, and so on.\n")
    w("## 2. Writes, flush, compaction\n")
    w("`put KEY VALUE` and `del KEY` store the value (or a tombstone) in the memtable, replacing what the memtable had for that key. Afterwards, if the memtable is full, it is flushed (below). Neither command prints anything of its own.\n")
    w("**Flush.** The memtable's content becomes a new run (new id) appended as the newest run of `L0`; the memtable becomes empty. Prints `flush #ID (N entries)`. Then the compaction cascade runs.\n")
    limit = f"`L0` needs **{p['l0']}** runs, every other level **{p['fan']}**"
    w(f"**The cascade.** A level is *over its limit* when it has at least as many runs as its limit ({limit}). Repeat: find the **lowest-numbered** level that is over its limit and merge it (below); stop when no level is over its limit. "
      f"The last level `L{last}` is subject to the same rule and merges into itself.\n")
    if p["merge"] == "all":
        take = "all runs of the level"
    else:
        take = "the **two oldest** runs of the level (or the only run, when the level has one)"
    w(f"**Merging level `Li`.** Take {take}. Create one entry per key found in the taken runs; where several taken runs have the key, the entry of the *newer* run (later in the level's list) wins. "
      + ("Tombstones are dropped from the result if all levels deeper than `Li` are empty (`Li+1` and below)." if p["drop"] == "deep-empty" else f"Tombstones are dropped from the result only when `Li` is the last level `L{last}`.") +
      " If the result has entries, it becomes a new run (new id): its **target** is `Li+1`" + (f" (for `L{last}`, `L{last}` itself)" ) + "; for a target other than `Li` the run is appended as the newest run of the target level, "
      "and for a merge of a level into itself it takes the place of the runs it replaced, at the old end of the list (the runs that were not taken stay after it). The taken runs disappear. Prints `compact Li (M runs) -> Lj run #ID (N entries)` "
      "(`M` runs taken, `j` the target level, `N` entries of the new run), or `compact Li (M runs) -> nothing` when everything was dropped (the taken runs are gone, no run is created, no id is used).\n")
    w("**Commands about compaction.**\n")
    w("* `flush`: flushes the memtable (prints as above, then the cascade); with an empty memtable it prints `memtable is empty`. Arguments: `error: usage: flush`.")
    w("* `compact`: merges the **lowest-numbered non-empty level** (whatever its size) exactly as above, then runs the cascade; `nothing to compact` if all levels are empty. The memtable is not touched.")
    if p["allcmd"]:
        w(f"* `compact all`: takes **every run of every level** (oldest data first: deepest level first, each level from its oldest run), merges them with the newest winning, drops all tombstones, and puts the result as the only run of the last level `L{last}` (all other levels become empty). "
          f"Prints `compact all (M runs) -> L{last} run #ID (N entries)` or `compact all (M runs) -> nothing`; `nothing to compact` if there are no runs. The memtable is not touched.")
        w("* Any other argument: `error: usage: compact [all]`.")
    else:
        w("* Any argument: `error: usage: compact`.")
    w("")
    w("## 3. Reads and inspection\n")
    w("* `get KEY`: looks the key up as in section 1 and counts the runs it **probes**: " +
      ("a run is probed only if `lo <= KEY <= hi` (runs whose key range does not contain the key are skipped without a probe); every probed run counts one, whether or not it has the key. " if p["filt"] else "every run it looks at counts one, in the order of the search, whether or not it has the key (there is no key-range filter). ") +
      "The memtable costs nothing. Output: `KEY = VALUE (SOURCE, N probed)` for a live key, `KEY deleted (SOURCE, N probed)` when the first entry found is a tombstone, `KEY not found (N probed)` when no entry exists; "
      "`SOURCE` is `memtable` or `Li #ID` (level and run id of the entry found), `N` the probes up to and including that run.")
    w("* `scan LO HI`: all **live** keys `k` with `LO <= k < HI` in key order, one line `KEY = VALUE` each (newest versions; deleted keys are absent), then `N keys`. `LO >= HI` is `error: empty range`.")
    w("* `dump`: first the line `memtable: ` followed by `KEY=VALUE` (or `KEY=<del>`) items in key order separated by single spaces, or `-` when empty; then for each level one line `Li: ` followed by its runs **newest first** as `#ID[LO..HI:N]` separated by single spaces (`N` entries), or `-` when the level is empty.")
    w("* `stats`: `runs=R entries=E tombstones=T live=L next=N`: the number of runs, the total entries of all runs (not the memtable), the number of tombstone entries in runs, the number of live keys (as `scan` would see them over all keys) and the id the next run will get.")
    w("* Blank lines and lines starting with `#` are ignored. Words are separated by white space. Errors: `error: usage: put KEY VALUE`, `error: usage: del KEY`, `error: usage: get KEY`, `error: usage: scan LO HI`, `error: usage: dump`, `error: usage: stats`, "
      "`error: bad key 'X'` (checked left to right before the value), `error: bad value 'X'`, `error: unknown command 'WORD'`. Output lines of a command appear in the order things happen: flush and compaction lines first, then the command's own line.\n")
    w("## 4. Examples\n")
    ex = [(c, r) for (c, r) in by_name.values() if c.visible]
    for c, r in ex[:3]:
        w(K.show_case(tool, c, r))
    w("The visible examples (`tests/examples.json`, run with `python3 tests/run_examples.py`) use the same format as the hidden checks.")
    return "\n".join(o) + "\n"


def make_cases(p: dict, tool: str, rng) -> list[K.Case]:
    cases: list[K.Case] = []
    cnt: dict[str, int] = {}

    def add(group, lines, visible=False):
        cnt[group] = cnt.get(group, 0) + 1
        cases.append(K.Case(name=f"{group}-{cnt[group]:02d}", group=group, stdin="\n".join(lines) + "\n", visible=visible))

    keys = KEYS[: rng.randint(10, 16)]

    def k():
        return rng.choice(keys)

    def put():
        return f"put {k()} {rng.choice(VALS)}"

    def writes(n, dels=0.0):
        return [put() if rng.random() >= dels else f"del {k()}" for _ in range(n)]

    for i in range(3):
        add("writes", writes(rng.randint(8, 14)) + ["dump", "stats"] + [f"get {k()}" for _ in range(3)], visible=(i == 0))
    for i in range(4):
        lines = writes(rng.randint(30, 45), dels=0.2)
        for j in range(6):
            lines.insert(rng.randint(5, len(lines)), "dump")
        lines += ["stats", "dump"]
        add("compaction", lines, visible=(i == 0 and False))
    for i in range(4):
        lines = writes(rng.randint(8, 12))
        lines += [f"del {k()}" for _ in range(rng.randint(4, 7))]
        lines += [f"get {k()}" for _ in range(5)]
        lines += writes(rng.randint(10, 20), dels=0.4) + ["dump", "stats", f"scan {sorted(keys)[0]} {sorted(keys)[-1]}", "flush", "dump"]
        lines += [f"get {k()}" for _ in range(4)]
        if p["allcmd"]:
            lines += ["compact all", "dump", "stats", "scan a zzzzzzzz"]
        add("tombstones", lines)
    for i in range(4):
        lines = writes(rng.randint(25, 40), dels=0.1)
        lines += [f"get {k()}" for _ in range(8)] + [f"get {rng.choice(['nope', 'a0', 'zz', 'zzzzzz'])}" for _ in range(2)]
        for _ in range(3):
            lo, hi = sorted(rng.sample(sorted(set(keys)), 2))
            lines.append(f"scan {lo} {hi}")
        lines.append("dump")
        add("reads", lines, visible=False)
    for i in range(3):
        lines = ["compact", "flush", "stats", "dump"]
        lines += writes(rng.randint(4, 8)) + ["flush", "compact", "dump", "compact", "dump", "flush"]
        lines += writes(rng.randint(15, 25), dels=0.15) + ["compact", "compact", "dump", "stats"]
        if p["allcmd"]:
            lines += ["compact all", "compact all", "dump"]
        add("manual", lines)
    # everything deleted
    lines = [f"put {x} v" for x in keys[:p["mem"] * 2]] + [f"del {x}" for x in keys[:p["mem"] * 2]] + ["dump", "stats", "compact", "compact", "dump", "stats", "scan a zzzzzzzz"]
    if p["allcmd"]:
        lines += ["compact all", "dump", "stats"]
    add("tombstones", lines)
    # errors
    for i in range(2):
        e = ["frob", "put", "put a", "put a b c", "put A b", "put toolongkey1 v", "put a bad!", "put a toolongvalue123", "del", "del a b", "del BAD", "get", "get a b", "get Bad", "scan", "scan a", "scan b a", "scan a a",
             "scan a BAD", "flush now", "flush", "compact all", "compact some", "compact", "dump x", "stats x", "# comment", "", "put a 1", "get a", "flush", "flush"]
        rng.shuffle(e)
        add("errors", e)
    # sessions
    for i in range(10):
        lines = []
        for _ in range(rng.randint(40, 70)):
            r = rng.random()
            if r < 0.5:
                lines.append(put())
            elif r < 0.62:
                lines.append(f"del {k()}")
            elif r < 0.78:
                lines.append(f"get {k()}")
            elif r < 0.83:
                lo, hi = sorted(rng.sample(sorted(set(keys)), 2))
                lines.append(f"scan {lo} {hi}")
            elif r < 0.88:
                lines.append("flush")
            elif r < 0.92:
                lines.append("compact")
            elif r < 0.94 and p["allcmd"]:
                lines.append("compact all")
            elif r < 0.97:
                lines.append("dump")
            else:
                lines.append("stats")
        add("sessions", lines)
    return cases


@family("project-tiers", category="project", lang="rust", kind="greenfield", n=8,
        summary="a tiered key-value store simulator: memtable flushes, cascading compactions (merge selection, tombstone dropping, in-place merges), probe-counting reads")
def gen(rng, n):
    for i in range(n):
        plan = dict(PLAN[i])
        tool = TOOLS[i]
        lang = plan.pop("lang")
        p = dict(plan)
        cfg = dict(MEM_LIMIT=p["mem"], L0_LIMIT=p["l0"], FANOUT=p["fan"], LEVELS=p["levels"], MERGE=p["merge"], DROP=p["drop"], RANGE_FILTER=p["filt"], HAS_ALL=p["allcmd"])
        cases = make_cases(p, tool, rng)
        py_sol = K.merged(K.load_src(THEME, "python", tool), K.render_config("python", cfg))
        sol = py_sol if lang == "python" else K.merged(K.load_src(THEME, lang, tool), K.render_config(lang, cfg))
        prompt = VOICES[i % len(VOICES)].format(tool=tool, Lang=K.LANG_NAME[lang], run=K.how_to_run(lang, tool), num=9100 + i * 19)
        nfeat = sum([p["merge"] == "oldest2", p["drop"] == "deep-empty", p["filt"], p["allcmd"], p["levels"] >= 4])
        yield K.project_task(
            theme=THEME, tool=tool, lang=lang, cases=cases, solution=sol, py_solution=py_sol,
            readme=lambda by_name, p=p, tool=tool, lang=lang: readme(p, tool, lang, by_name),
            prompt=prompt, difficulty=3 if nfeat <= 1 else (4 if nfeat <= 3 else 5), slug=f"{i + 1:02d}-{tool}-{p['merge']}-{lang}",
            notes={k_: p[k_] for k_ in ("mem", "l0", "fan", "levels", "merge", "drop", "filt", "allcmd")}, tags=["storage", "simulation"],
        )
