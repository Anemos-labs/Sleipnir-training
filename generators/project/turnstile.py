"""project-turnstile: the door-access controller of an invented venue: zones with levels, caps and opening hours (weekday windows, some
crossing midnight), doors with an outer and an inner side, badges with expiry, anti-passback modes, escorts, lockdowns and idle
timeouts, with a configurable precedence of denial reasons.  Reference: Python (oracle) and Java."""
from __future__ import annotations

from fx import family

from generators.project import _kit as K

THEME = "turnstile"
TOOLS = ["turnstile", "gatewarden", "badgeline", "portcullis", "ingress", "wicketd", "doorman", "tollgate"]
ZONE_POOL = ["hall", "lab", "vault", "dock", "annex", "roof", "cellar", "atrium", "studio", "depot"]
PEOPLE = ["ana", "bo", "cy", "dee", "eli", "fay", "gus", "hal", "ivy", "jo", "kit", "lou"]
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
REASONS = ["expired", "lockdown", "passback", "level", "hours", "full"]

PLAN = [
    dict(lang="java", order=["expired", "lockdown", "passback", "level", "hours", "full"], apb="soft", escort=True, evict=0, seal=False, cross=True, exp_out=False),
    dict(lang="python", order=["lockdown", "expired", "level", "hours", "passback", "full"], apb="strict", escort=False, evict=45, seal=True, cross=False, exp_out=True),
    dict(lang="java", order=["passback", "expired", "lockdown", "hours", "level", "full"], apb="soft", escort=True, evict=60, seal=True, cross=True, exp_out=True),
    dict(lang="java", order=["level", "hours", "expired", "full", "lockdown"], apb="off", escort=True, evict=0, seal=False, cross=True, exp_out=False),
    dict(lang="python", order=["expired", "hours", "level", "passback", "lockdown", "full"], apb="strict", escort=True, evict=30, seal=False, cross=True, exp_out=False),
    dict(lang="java", order=["lockdown", "passback", "expired", "full", "level", "hours"], apb="soft", escort=False, evict=90, seal=True, cross=False, exp_out=False),
    dict(lang="java", order=["hours", "level", "full", "expired", "lockdown", "passback"], apb="strict", escort=True, evict=0, seal=True, cross=True, exp_out=True),
    dict(lang="java", order=["expired", "passback", "hours", "level", "lockdown", "full"], apb="soft", escort=False, evict=45, seal=False, cross=True, exp_out=True),
]

VOICES = [
    "We are building the access controller for a small venue: zones with clearance levels, capacities and opening hours, doors between them, badges that expire. It is driven by a script on standard input. `README.md` defines every rule, including the order in which the reasons for a denial are checked. The program is `{tool}`; write it in {Lang}: {run}. Visible examples: `python3 tests/run_examples.py`. The hidden checks run long scripts with a clock.",
    "build {tool} from README.md ({Lang}). door access simulator: zones, doors, badges, opening hours incl. weekday windows, anti-passback, lockdown. {run}. the README says exactly which check wins when several fail. examples: `python3 tests/run_examples.py`",
    "Ticket SEC-{num}: implement the `{tool}` access controller (spec: README.md).\n\nLanguage: {Lang}; the program is {run}. Output lines are compared exactly: GRANT/DENY lines with the clock stamp, TIMEOUT lines, report and stats. Please keep the clock/opening-hours code and the swipe decision separate from the command parsing.",
    "Could you write the venue access controller described in README.md? Badges swipe at doors, the controller decides GRANT or DENY and keeps track of who is where. {Lang} please; the program is {run}. `python3 tests/run_examples.py` runs a few examples; the hidden checks are long scripts, grouped by feature and scored per group.",
    "Greenfield in {Lang}: `{tool}`, a deterministic door-access simulator with a weekly clock. The README defines the script commands, the opening-hours syntax, how a swipe is judged and what every query prints. {run}. The hidden suite is grouped (setup, hours, clock, swipes, capacity, lockdown, queries, errors, sessions).",
    "README.md has the spec for `{tool}`. Please build it in {Lang} ({run}). The details that decide many checks: the precedence of denial reasons, how the clock jumps to the next weekday occurrence, windows that cross midnight, and what exactly counts as full. Visible examples: `python3 tests/run_examples.py`.",
    "short version: door access controller, spec in README.md, {Lang}, name it {tool}. {run}",
    "Please implement the access controller from README.md in {Lang}, named `{tool}`. How it is run: {run}. It reads its script from standard input and prints one line per decision; it must be exact about stamps, reasons and the order of lines.",
]


# ---------------------------------------------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------------------------------------------

def readme(p: dict, tool: str, lang: str, by_name: dict) -> str:
    o: list[str] = []
    w = o.append
    order = p["order"]
    esc = p["escort"]
    w(f"# {tool}: a door-access controller\n")
    w("`" + tool + "` simulates the access control of a venue: **zones** joined by **doors**, **badges** that are swiped at doors, a weekly **clock**. "
      "It reads a script on standard input, one command per line, and prints the decision of every swipe and the answers to questions. Nothing is persisted.\n")
    w(f"Build and run it as {K.how_to_run(lang, tool)}. There are no arguments. Exit status 1 if any `error:` line was printed, otherwise 0. "
      "Blank lines and lines whose first non-blank character is `#` are ignored; words are separated by white space. A command that fails prints one `error:` line and changes nothing; the script goes on.\n")
    w("## 1. Model\n")
    w("* A **name** (of a zone, door or badge) is a lower-case letter followed by at most 11 lower-case letters, digits or `-`. Zones, doors and badges have separate namespaces. A **number** is `0` or 1 to 5 digits without a leading zero.")
    w("* **Zones** have a *level* (0 to 9, default 0), a *capacity* (1 to 99; default: unlimited), *opening hours* (default: always open) and a lockdown flag (initially off). The zone `outside` always exists, has no limits and cannot be declared; every badge starts there.")
    w("* A **door** joins an *outer* zone `A` (a declared zone or `outside`) to an *inner* zone `B` (a declared zone). A swipe `in` moves a badge from `A` to `B`, a swipe `out` from `B` to `A`.")
    w("* A **badge** has a level (0 to 9), optionally an expiry, a *location* (a zone name or `outside`; initially `outside`) and a *since* time (the time of its last grant or timeout; initially none).")
    w("* The **clock** counts minutes from Monday 00:00 of week 0 and starts at 0. A **stamp** is `DAY HH:MM` of the clock (`mon`..`sun`, 24-hour, zero padded), for example `tue 07:05`; the week goes on from `sun 23:59` to `mon 00:00`.")
    w("* The **occupancy** of a zone is the number of badges whose location is that zone.\n")
    w("## 2. Commands\n")
    w("Arguments of every command are checked in the order given here; the first problem is reported as `error: MESSAGE` and nothing changes. Wrong argument counts or words give the usage message of the command.\n")
    w("* `zone NAME [level N] [cap N] [hours SPEC]`: the options come in any order, each at most once (otherwise `usage: zone NAME [level N] [cap N] [hours SPEC]`). Then: `bad name 'X'`, `'outside' is reserved`, `zone 'X' exists`, then the option values left to right: "
      "`bad level 'X'`, `bad cap 'X'`, `bad hours 'X'`. Prints nothing.")
    w("* `door ID A B`: `usage: door ID A B`, `bad name 'X'`, `door 'X' exists`, `unknown zone 'X'` (first `A`, then `B`; `outside` is known), `'outside' can only be the outer side` (if `B` is `outside`), `door 'X' joins a zone to itself`. Prints nothing.")
    w("* `badge ID level N [expires in MINUTES]`: `usage: badge ID level N [expires in MINUTES]`, `bad name 'X'`, `badge 'X' exists`, `bad level 'X'`, `bad expiry 'X'` (MINUTES is a number from 1 to 99999). "
      "The expiry is the clock at the time of the command plus MINUTES. Prints nothing.")
    w("* `at DAY HH:MM`: moves the clock forward to the **next** moment that is that weekday at that time, **at or after** the current clock (the same moment means no move). `at +N` moves it forward by N minutes (N from 1 to 10080). "
      "Errors: `usage: at DAY HH:MM | at +MINUTES` (any other shape), `bad time '+N'`, `bad day 'X'`, `bad time 'X'` (`X` the clock word; `HH:MM` is `00:00` to `23:59` with two digits each). "
      + (f"After every move that changes the clock, **timeouts** happen (section 4). " if p["evict"] else "") + "Prints nothing otherwise.")
    w("* `lockdown ZONE on|off`: `usage: lockdown ZONE on|off`, `unknown zone 'X'` (`outside` is not a zone for this purpose). Sets the flag and prints `[STAMP] lockdown ZONE on` (or `off`), also if nothing changes.")
    w("* `swipe BADGE DOOR in|out" + (" [with BADGE]" if esc else "") + "`: errors `usage: swipe BADGE DOOR in|out" + (" [with BADGE]" if esc else "") + "`, `unknown badge 'X'`, `unknown door 'X'`" +
      (", `unknown badge 'X'` (the escort), `an escort must be another badge`; `with` after `out` is a usage error" if esc else "") + ". Prints the decision (section 3).")
    w("* Questions (section 5): `where BADGE`, `who ZONE`, `report`, `stats`; usage messages `usage: where BADGE`, `usage: who ZONE`, `usage: report`, `usage: stats`, and `unknown badge 'X'` / `unknown zone 'X'` (`who outside` is allowed).")
    w("* Any other first word: `unknown command 'WORD'`.\n")
    w("**Opening hours.** `SPEC` is one word of windows separated by `,`; a window is `DAYS@START-END`. `DAYS` is `*` (every day), a day, or `DAY-DAY`, a range that may wrap around the end of the week (`fri-mon` is fri, sat, sun, mon). "
      "`START` and `END` are `HH:MM`; `END` may also be `24:00` (midnight at the end of the day). `START` = `END` is not allowed. "
      + ("`END` before `START` makes the window **cross midnight**: for every listed day D it covers D from START to the end of the day and the next day from 00:00 to END (`fri@22:00-02:00` is fri 22:00 up to, not including, sat 02:00). "
         if p["cross"] else "`END` must be after `START`: windows that cross midnight do not exist in this venue, `fri@22:00-02:00` is a bad specification (write two windows instead). ")
      + "A zone is **open** at a minute if some window contains it (start included, end excluded). Anything not matching this grammar (including empty parts, upper case, one-digit hours) is `bad hours`.\n")
    w("## 3. Swipes\n")
    w("`swipe B D in` takes badge `B` through door `D` from its outer to its inner side, `out` the other way. Let `Z` be the **inner** zone of the door (for both directions). "
      + ("With `with E` the badge `E` is an **escort**: the two badges are judged together, and both move together. Only `in` swipes may have an escort. Below, \"the badges\" means the one or two badges of the swipe. " if esc else "") +
      "The swipe is judged by these rules in this order; the **first rule that applies and fails** gives the reason of a denial:\n")
    rule_text = {
        "expired": "`expired`: " + ("some" if esc else "the") + " badge has an expiry that is at or before the clock" + (" (for `in` swipes" + (", and for `out` swipes as well)" if p["exp_out"] else "; an expired badge may still leave)")) + ".",
        "lockdown": "`lockdown`: `Z` is in lockdown" + (" (for `in` and for `out` swipes: a locked zone is sealed)" if p["seal"] else " (for `in` swipes only; leaving a locked zone is always possible)") + ".",
        "passback": {"soft": "`passback`: the rule against re-using a badge for a move it already made: an `in` swipe fails if " + ("a" if esc else "the") + " badge's location is already `Z`; an `out` swipe fails if its location is already the outer zone of the door (`outside` counts). Any other location is accepted, wherever it is.",
                     "strict": "`passback`: a badge must be where the door expects it: an `in` swipe fails unless " + ("each" if esc else "the") + " badge's location is exactly the outer zone of the door (`outside` counts); an `out` swipe fails unless its location is exactly `Z`."}.get(p["apb"], ""),
        "level": "`level` (`in` only): " + ("the highest level of the badges is lower" if esc else "the badge's level is lower") + " than the level of `Z`.",
        "hours": "`hours` (`in` only): `Z` is not open at the current clock.",
        "full": "`full` (`in` only): `Z` has a capacity and its occupancy plus " + ("the number of badges of the swipe whose location is not `Z`" if esc else "1 if the badge's location is not `Z` (0 if it is)") + " is greater than it.",
    }
    for i, r in enumerate(order, 1):
        w(f"{i}. {rule_text[r]}")
    if p["apb"] == "off":
        w("\nThere is no passback rule: a badge's location is never checked, a swipe works from wherever the badge is.")
    w("\nRules marked `in` only are skipped for `out` swipes. If every rule passes, the swipe is **granted**: the location of each badge becomes the **target** (`Z` for `in`, the outer zone for `out`) and its *since* becomes the clock.\n")
    w("Output: `[STAMP] GRANT IDS DOOR DIR -> WHERE` where `IDS` is the badge id" + (" (or `ID+ESCORT`, the swiping badge first)" if esc else "") + ", `DIR` is `in` or `out`, and `WHERE` is `outside` or `ZONE (OCC/CAP)` with the occupancy **after** the move and the capacity (`-` if unlimited); "
      "or `[STAMP] DENY IDS DOOR DIR: REASON`.\n")
    if p["evict"]:
        w(f"## 4. Timeouts\n")
        w(f"A badge that stays inside too long is sent out. Right after a move of the clock (`at`) to a later time, every badge whose location is not `outside` and for which `clock - since >= {p['evict']}` is moved outside, in order of badge id (byte order); "
          "its since becomes the new clock, and a line `[STAMP] TIMEOUT ID left ZONE` (the zone it was in, the stamp of the new clock) is printed for each (by the `at` command itself, nothing else is printed for it). Timeouts do not depend on expiry. "
          "A badge that was never granted anything has no since and is outside anyway.\n")
    sec = 5 if p["evict"] else 4
    w(f"## {sec}. Questions\n")
    w("* `where B`: `B: LOCATION`, followed by ` since STAMP` if the badge has a since.")
    w("* `who Z`: `Z (OCC/CAP): ` and the ids of the badges located there in byte order separated by spaces, or `-`; `CAP` is `-` when unlimited (always for `outside`).")
    w("* `report`: one line per declared zone in the order of declaration: `NAME: OCC/CAP level L open` (or `closed`, by the opening hours at the current clock), followed by ` lockdown` if the zone is in lockdown.")
    w("* `stats`: `grants=G denies=D timeouts=T` (counts since the start: swipes granted, swipes denied, badges timed out), then one line `deny REASON COUNT` for every reason with a non-zero count, **in the order of the rules of section 3**.\n")
    w(f"## {sec + 1}. Examples\n")
    ex = [(c, r) for (c, r) in by_name.values() if c.visible]
    for c, r in ex[:3]:
        w(K.show_case(tool, c, r))
    w("The visible examples (`tests/examples.json`, run with `python3 tests/run_examples.py`) use the same format as the hidden checks.")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# venues and scripts
# ---------------------------------------------------------------------------------------------------------------

def hours_spec(rng, cross: bool) -> str:
    start = rng.choice(["06:00", "07:30", "08:00", "09:00", "10:00", "12:00", "14:00"])
    end = rng.choice(["13:00", "16:00", "17:30", "18:00", "20:00", "22:00", "24:00"])
    choices = [
        f"mon-fri@{start}-{end}", f"*@{start}-{end}", f"sat-sun@10:00-16:00,mon-fri@{start}-{end}", f"mon-thu@{start}-{end},fri@09:00-13:00", f"*@00:00-24:00",
        f"wed-mon@{start}-{end}", "sat@12:00-24:00", "mon@08:00-12:00,mon@11:00-15:00,tue-sun@08:00-09:00",
    ]
    if cross:
        choices += ["fri-sat@22:00-02:00", "*@20:00-06:00", "sun@23:30-00:30", "mon-fri@18:00-08:00,sat@08:00-12:00"]
    return rng.choice(choices)


class Venue:
    """A random venue: a tree of zones below `lobby`, plus an occasional extra door."""

    def __init__(self, rng, p, nz=5, nb=7, hours_p=0.5, cap_p=0.6, expire_p=0.25):
        self.rng, self.p = rng, p
        names = ["lobby"] + rng.sample(ZONE_POOL, nz - 1)
        self.zones = names
        depth = {"lobby": 0}
        self.lines: list[str] = []
        self.doors: list[tuple[str, str, str]] = [("d1", "outside", "lobby")]
        self.zone_lines = {}
        for i, z in enumerate(names):
            if i:
                parent = rng.choice(names[:i])
                depth[z] = depth[parent] + 1
                self.doors.append((f"d{len(self.doors) + 1}", parent, z))
            opts = []
            level = min(9, depth[z] + rng.choice([0, 0, 1, 1, 2])) if i else rng.choice([0, 0, 1])
            if level or rng.random() < 0.3:
                opts.append(f"level {level}")
            if rng.random() < cap_p:
                opts.append(f"cap {rng.choice([1, 2, 2, 3, 3, 4, 6])}")
            if rng.random() < hours_p:
                opts.append(f"hours {hours_spec(rng, p['cross'])}")
            rng.shuffle(opts)
            self.lines.append(f"zone {z} " + " ".join(opts) if opts else f"zone {z}")
        if nz > 3 and rng.random() < 0.6:
            a, b = rng.sample(names[1:], 2)
            self.doors.append((f"d{len(self.doors) + 1}", a, b))
        for d, a, b in self.doors:
            self.lines.append(f"door {d} {a} {b}")
        self.badges = rng.sample(PEOPLE, nb)
        for i, b in enumerate(self.badges):
            level = rng.choice([0, 1, 1, 2, 2, 3, 4, 5, 6, 9])
            exp = f" expires in {rng.choice([30, 60, 90, 180, 600, 2000])}" if rng.random() < expire_p else ""
            self.lines.append(f"badge {b} level {level}{exp}")
        self.where = {b: "outside" for b in self.badges}

    def plausible_swipe(self, escort_p: float) -> str:
        r = self.rng
        b = r.choice(self.badges)
        here = self.where[b]
        if r.random() < 0.2:
            d, a, z = r.choice(self.doors)
            direction = r.choice(["in", "out"])
        else:
            options = [(d, a, z, "in") for d, a, z in self.doors if a == here] + [(d, a, z, "out") for d, a, z in self.doors if z == here]
            d, a, z, direction = r.choice(options)
        escort = ""
        if direction == "in" and r.random() < escort_p:
            mates = [x for x in self.badges if x != b and self.where[x] == here]
            if mates:
                e = r.choice(mates)
                escort = f" with {e}"
                self.where[e] = z
        self.where[b] = z if direction == "in" else a
        return f"swipe {b} {d} {direction}{escort}"


def clock_step(rng) -> str:
    r = rng.random()
    if r < 0.55:
        return f"at +{rng.choice([1, 5, 10, 15, 20, 30, 40, 45, 59, 60, 61, 90, 120, 240, 600, 1440])}"
    return f"at {rng.choice(DAYS)} {rng.randint(0, 23):02d}:{rng.choice([0, 0, 15, 30, 45, 59]):02d}"


def session(rng, p, steps, nz=5, nb=7, **vkw) -> list[str]:
    v = Venue(rng, p, nz=nz, nb=nb, **vkw)
    lines = list(v.lines)
    lines.append(f"at {rng.choice(DAYS)} {rng.randint(6, 20):02d}:{rng.choice([0, 30]):02d}")
    esc_p = 0.25 if p["escort"] else 0.0
    for _ in range(steps):
        r = rng.random()
        if r < 0.62:
            lines.append(v.plausible_swipe(esc_p))
        elif r < 0.78:
            lines.append(clock_step(rng))
        elif r < 0.83:
            lines.append(f"lockdown {rng.choice(v.zones)} {rng.choice(['on', 'on', 'off'])}")
        elif r < 0.88:
            lines.append(f"where {rng.choice(v.badges)}")
        elif r < 0.92:
            lines.append(f"who {rng.choice(v.zones + ['outside'])}")
        elif r < 0.96:
            lines.append("report")
        else:
            lines.append("stats")
    lines += ["report", "stats"] + [f"where {b}" for b in v.badges[:3]]
    return lines


def features_of(out: str) -> set[str]:
    f = set()
    for ln in out.splitlines():
        if "DENY" in ln:
            f.add("deny-" + ln.rsplit(": ", 1)[1])
        elif "GRANT" in ln:
            f.add("grant-group" if "+" in ln.split(" ")[3] else "grant")
            f.add("grant-out" if " out -> " in ln else "grant-in")
        elif "TIMEOUT" in ln:
            f.add("timeout")
        elif ln.startswith("error:"):
            f.add("error")
        elif "lockdown" in ln:
            f.add("lockdown")
    return f


def make_cases(p: dict, tool: str, rng, py_solution) -> list[K.Case]:
    cases: list[K.Case] = []
    cnt: dict[str, int] = {}
    runner = K.oracle_runner(tool, py_solution)

    def add(group, lines, visible=False):
        cnt[group] = cnt.get(group, 0) + 1
        cases.append(K.Case(name=f"{group}-{cnt[group]:02d}", group=group, stdin="\n".join(lines) + "\n", visible=visible))

    esc = p["escort"]
    wanted = {"deny-" + r for r in p["order"]} | {"grant", "grant-in", "grant-out", "lockdown", "error"}
    if esc:
        wanted.add("grant-group")
    if p["evict"]:
        wanted.add("timeout")

    # ---- sessions on random venues, chosen so that every reason and feature shows up (several times)
    pool = [session(rng, p, rng.randint(25, 70), nz=rng.randint(4, 6), nb=rng.randint(5, 9)) for _ in range(70)]
    pool_cases = [K.Case(name=f"pool-{i}", group="sessions", stdin="\n".join(ln) + "\n") for i, ln in enumerate(pool)]
    recs = runner(pool_cases)
    feats = [features_of(r.stdout) for r in recs]
    counts = {f: sum(f in fs for fs in feats) for f in sorted(wanted)}
    missing = [f for f, n in counts.items() if n < 3 and f != "error"]
    if missing:
        raise K.BuildError(f"turnstile: the sessions do not cover {missing}")
    chosen: list[int] = []
    covered: dict[str, int] = {}
    while len(chosen) < 14:
        best, best_gain = None, -1.0
        for i, fs in enumerate(feats):
            if i in chosen:
                continue
            gain = sum(1.0 / (1 + covered.get(f, 0)) for f in sorted(fs) if f in wanted) + len(fs) * 0.01
            if gain > best_gain:
                best, best_gain = i, gain
        chosen.append(best)
        for f in feats[best]:
            covered[f] = covered.get(f, 0) + 1
    for i in chosen:
        add("sessions", pool[i])

    # ---- swipes: small scripted scenarios (the first ones are the README examples)
    E = p["evict"]
    add("swipes", ["zone lobby", "zone lab level 2 cap 1 hours mon-fri@09:00-17:00", "door d1 outside lobby", "door d2 lobby lab", "badge ana level 3", "badge bo level 1", "badge cy level 2",
                   "at mon 08:30", "swipe ana d1 in", "swipe ana d2 in", "at mon 09:00", "swipe ana d2 in", "swipe bo d1 in", "swipe bo d2 in", "swipe cy d1 in", "swipe cy d2 in", "who lab", "stats"], visible=True)
    if E:
        add("swipes", ["zone lobby", "zone hall", "door d1 outside lobby", "door d2 lobby hall", "badge ana level 0", "badge bo level 0", "at tue 09:00", "swipe ana d1 in", "swipe bo d1 in", f"at +{E - 10}",
                       "swipe bo d2 in", f"at +10", "where ana", "where bo", f"at +{E}", "who hall", "stats"], visible=True)
    else:
        add("swipes", ["zone lobby", "zone hall level 1", "door d1 outside lobby", "door d2 lobby hall", "badge ana level 1", "at sat 12:00", "swipe ana d1 in", "lockdown hall on", "swipe ana d2 in", "lockdown hall off",
                       "swipe ana d2 in", "lockdown lobby on", "swipe ana d2 out", "swipe ana d1 out", "swipe ana d1 in", "report"], visible=True)
    if esc:
        add("swipes", ["zone lobby", "zone vault level 4 cap 2", "door d1 outside lobby", "door d2 lobby vault", "badge ana level 5", "badge bo level 1", "badge cy level 1", "at wed 10:00", "swipe ana d1 in",
                       "swipe bo d1 in", "swipe cy d1 in", "swipe bo d2 in", "swipe bo d2 in with ana", "swipe cy d2 in with ana", "swipe cy d2 in with bo", "who vault", "stats"], visible=True)
    else:
        add("swipes", ["zone lobby", "zone den level 1 cap 2", "door d1 outside lobby", "door d2 lobby den", "badge ana level 1", "badge bo level 1", "badge cy level 1", "badge dee level 0", "at wed 10:00",
                       "swipe ana d1 in", "swipe bo d1 in", "swipe cy d1 in", "swipe dee d1 in", "swipe ana d2 in", "swipe dee d2 in", "swipe bo d2 in", "swipe cy d2 in", "swipe ana d2 out", "swipe cy d2 in", "who den", "stats"], visible=True)
    for i in range(3):
        add("swipes", session(rng, p, rng.randint(15, 30), nz=3, nb=4, hours_p=0.3, expire_p=0.0))

    # ---- hours: scripted scenarios around window edges
    zone_hours = ["mon-fri@08:00-18:00", "sat-sun@10:00-16:00,mon-fri@07:30-19:00", "*@00:00-24:00", "wed-mon@08:00-12:00", "mon@08:00-12:00,mon@11:00-15:00", "sat@12:00-24:00"]
    base = ["zone lobby", "zone room level 1 cap 3 hours {h}", "door d1 outside lobby", "door d2 lobby room", "badge ana level 5", "badge bo level 5"]
    probes = [("mon 07:59", "mon 08:00"), ("mon 17:59", "mon 18:00"), ("fri 18:00", "sat 10:00"), ("sat 15:59", "sat 16:00"), ("sun 23:59", "mon 00:00")]
    for h in zone_hours:
        lines = [b.format(h=h) for b in base] + ["swipe ana d1 in"]
        lines.append(f"at {rng.choice(DAYS)} 00:00")
        for _ in range(7):
            lines.append(f"at {rng.choice(DAYS)} {rng.randint(0, 23):02d}:{rng.choice([0, 0, 30, 59]):02d}")
            lines += ["swipe ana d2 in", "report", "swipe ana d2 out"]
        add("hours", lines, visible=False)
    edge = [b.format(h="mon-fri@08:00-18:00,sat@10:00-14:00") for b in base] + ["swipe ana d1 in", "swipe bo d1 in"]
    for a, b in probes:
        edge += [f"at {a}", "swipe ana d2 in", "report", "swipe ana d2 out", f"at {b}", "swipe bo d2 in", "report", "swipe bo d2 out"]
    add("hours", edge)
    cross = [b.format(h="fri-sat@22:00-02:00,sun@23:30-00:30") for b in base] + ["swipe ana d1 in", "swipe bo d1 in"]
    for a in ["thu 23:59", "fri 21:59", "fri 22:00", "sat 01:59", "sat 02:00", "sat 21:59", "sat 23:59", "sun 00:00", "sun 23:30", "mon 00:29", "mon 00:30"]:
        cross += [f"at {a}", "report", "swipe ana d2 in", "swipe ana d2 out"]
    add("hours", cross)
    specs = ["mon@08:00", "mon@8:00-9:00", "mon@08:00-08:00", "mon@09:00-08:00", "xyz@08:00-09:00", "mon-@08:00-09:00", "@08:00-09:00", "mon@08:00-25:00", "mon@08:00-24:00", "mon@24:00-24:30",
             "mon@08:60-09:00", ",mon@08:00-09:00", "mon@08:00-09:00,", "mon@08:00-09:00,tue", "mon-tue-wed@08:00-09:00", "MON@08:00-09:00", "mon@08:00-09:00@x", "*@23:00-01:00", "sun-mon@00:00-24:00",
             "mon@08:00-09:00,tue@08:00-09:00", "mon@08:00-", "mon@-09:00", "mon@0800-0900", "fri-mon@22:00-23:00", "fri@22:00-24:00", "*@00:00-00:01", "mon@00:00-24:00"]
    rng.shuffle(specs)
    for chunk in (specs[:14], specs[14:]):
        lines = ["zone base"]
        for i, s in enumerate(chunk):
            lines.append(f"zone z{i} hours {s}")
        lines += ["door d1 outside base", "report"]
        add("hours", lines)

    # ---- clock
    pre = ["zone lobby hours mon-fri@09:00-17:00", "door d1 outside lobby", "badge ana level 1", "badge bo level 1"]
    add("clock", pre + ["at +0", "at +10081", "at +10080", "at +abc", "at +-5", "at +007", "at +", "at tue 25:00", "at xyz 10:00", "at mon", "at", "at mon 10:00 extra", "at mon 9:00", "at mon 09:60", "at Mon 10:00",
                        "at 10:00", "at tue 24:00", "at tue 10:0", "at +1.5", "at +1 +2", "report", "at +10", "report"])
    add("clock", pre + ["swipe ana d1 in", "at mon 10:00", "swipe ana d1 in", "swipe bo d1 in", "at mon 10:00", "report", "at sun 23:59", "at mon 00:00", "report", "at mon 00:00", "at tue 00:00", "swipe ana d1 in",
                        "swipe bo d1 out", "where ana", "where bo", "at +1440", "at +1", "swipe ana d1 out", "at wed 13:15", "at wed 13:14", "at wed 13:15", "report", "at fri 17:00", "report", "at fri 16:59", "report",
                        "at +10080", "report", "at mon 08:59", "report", "at +1", "report"])
    if p["evict"]:
        e = p["evict"]
        lines = ["zone lobby", "zone hall level 1", "door d1 outside lobby", "door d2 lobby hall", "badge ana level 2", "badge bo level 2", "badge cy level 2", "at mon 08:00", "swipe ana d1 in", "swipe ana d2 in",
                 f"at +{e - 1}", "where ana", f"at +1", "where ana", "who outside", "swipe bo d1 in", f"at +{e - 5}", "swipe cy d1 in", "swipe bo d1 in", f"at +{e - 5}", "who lobby", f"at +5", "who lobby", "stats",
                 f"at +{e * 3}", "swipe ana d1 in", "swipe ana d2 in", "swipe bo d1 in", "swipe cy d1 in", "at +1", "at +1", f"at +{e}", "where ana", "where cy", "report", "stats", "at +0", "at +1", "stats"]
        add("clock", lines)
        lines = ["zone a", "zone b level 1 cap 1", "door d1 outside a", "door d2 a b"] + [f"badge u{i} level 3" for i in range(1, 6)] + ["at tue 12:00"]
        for i in range(1, 6):
            lines += [f"swipe u{i} d1 in", f"at +{e // 3 + i}"]
        lines += ["swipe u1 d2 in", f"at +{e // 2}", "swipe u2 d2 in", "who a", "who b", f"at +{e}", "who a", "who b", "swipe u2 d2 in", "stats"]
        add("clock", lines)

    # ---- passback / locations: chains of doors
    chain = ["zone a", "zone b level 1", "zone c level 1", "door d1 outside a", "door d2 a b", "door d3 b c", "door d4 a c", "badge ana level 3", "badge bo level 3", "at mon 09:00"]
    seqs = [
        ["swipe ana d1 in", "swipe ana d1 in", "swipe ana d2 in", "swipe ana d3 in", "swipe ana d3 in", "swipe ana d3 out", "swipe ana d3 out", "swipe ana d2 out", "swipe ana d1 out", "swipe ana d1 out", "where ana"],
        ["swipe bo d3 in", "swipe bo d2 in", "swipe bo d1 in", "swipe bo d3 out", "swipe bo d2 out", "swipe bo d4 in", "swipe bo d4 out", "swipe bo d4 in", "swipe bo d2 out", "swipe bo d2 in", "where bo", "who a", "who b", "who c"],
        ["swipe ana d1 in", "swipe bo d1 in", "swipe ana d4 in", "swipe bo d2 in", "swipe bo d3 in", "swipe ana d3 out", "swipe bo d3 out", "swipe ana d4 out", "who outside", "who a", "who c", "stats"],
        ["swipe ana d4 in", "swipe ana d4 out", "swipe ana d2 out", "swipe ana d1 out", "swipe ana d1 in", "swipe ana d2 out", "swipe ana d3 out", "swipe ana d3 in", "swipe ana d2 in", "where ana", "stats"],
    ]
    for s in seqs:
        add("passback", chain + s)

    # ---- capacity, escorts, levels
    capb = ["zone lobby", "zone vip level 4 cap 2", "zone den level 1 cap 3", "door d1 outside lobby", "door d2 lobby vip", "door d3 lobby den", "badge ana level 5", "badge bo level 4", "badge cy level 1",
            "badge dee level 0", "badge eli level 1", "at wed 10:00"]
    for who in ["ana", "bo", "cy", "dee", "eli"]:
        capb.append(f"swipe {who} d1 in")
    s1 = capb + ["swipe ana d2 in", "swipe bo d2 in", "swipe cy d2 in", "swipe cy d3 in", "swipe dee d3 in", "swipe eli d3 in", "swipe ana d2 out", "swipe cy d2 in", "swipe eli d3 out", "swipe dee d3 in", "report", "stats"]
    add("capacity", s1, visible=False)
    if esc:
        s2 = capb + ["swipe cy d2 in with ana", "swipe dee d3 in with cy", "swipe eli d2 in with dee", "swipe bo d2 in with eli", "swipe bo d2 in", "swipe eli d3 in with dee", "swipe dee d3 in with eli",
                     "swipe cy d3 in with dee", "swipe ana d2 out", "swipe cy d2 out", "swipe bo d2 in with ana", "who vip", "who den", "who lobby", "stats"]
        s3 = capb + ["swipe ana d3 in", "swipe bo d3 in", "swipe cy d3 in with ana", "swipe cy d3 in with bo", "swipe dee d3 in with eli", "swipe eli d3 in with dee", "swipe ana d3 out", "swipe eli d3 in with dee",
                     "swipe dee d3 in with bo", "swipe ana d2 in with ana", "swipe ana d2 in with nobody", "swipe ana d2 out with bo", "swipe ana d2 in with", "who den", "who vip", "stats"]
        add("capacity", s2)
        add("capacity", s3, visible=False)
    else:
        add("capacity", capb + ["swipe cy d2 in with ana", "swipe ana d2 in with bo", "swipe ana d2 in", "swipe ana d2 out with bo", "who vip", "stats"])
    for i in range(2):
        add("capacity", session(rng, p, rng.randint(30, 50), nz=4, nb=8, cap_p=1.0, hours_p=0.1, expire_p=0.0))

    # ---- lockdown
    lk = ["zone lobby", "zone hall level 1", "zone lab level 2", "door d1 outside lobby", "door d2 lobby hall", "door d3 hall lab", "badge ana level 3", "badge bo level 3", "badge cy level 1", "at fri 09:00",
          "swipe ana d1 in", "swipe ana d2 in", "swipe ana d3 in", "swipe bo d1 in", "swipe bo d2 in", "lockdown lab on", "swipe ana d3 out", "swipe bo d3 in", "swipe ana d3 in", "report", "lockdown lab off",
          "swipe ana d3 out", "swipe bo d3 in", "lockdown hall on", "swipe bo d2 out", "swipe cy d1 in", "swipe cy d2 in", "swipe ana d2 in", "lockdown hall on", "lockdown hall off", "lockdown nowhere on",
          "lockdown outside on", "lockdown hall", "lockdown hall maybe", "lockdown lab on", "who lab", "who hall", "stats"]
    add("lockdown", lk)
    for i in range(2):
        lines = session(rng, p, 45, nz=5, nb=6)
        lines = [ln for ln in lines if not ln.startswith("lockdown")]
        zs = [ln.split()[1] for ln in lines if ln.startswith("zone")]
        for k in range(6):
            lines.insert(rng.randint(10 + len(zs), len(lines)), f"lockdown {rng.choice(zs)} {rng.choice(['on', 'off'])}")
        add("lockdown", lines)

    # ---- expiry
    ex = ["zone lobby", "zone hall level 1", "door d1 outside lobby", "door d2 lobby hall", "badge ana level 2 expires in 60", "badge bo level 2 expires in 120", "badge cy level 2", "at mon 09:00",
          "swipe ana d1 in", "swipe bo d1 in", "swipe cy d1 in", "at +59", "swipe ana d2 in", "at +1", "swipe ana d2 in", "swipe ana d1 out", "swipe bo d2 in", "swipe cy d2 in", "at +60", "swipe bo d2 out",
          "swipe bo d1 out", "swipe bo d1 in", "swipe cy d2 out", "where ana", "where bo", "stats"]
    if esc:
        ex += ["badge dee level 0", "swipe dee d1 in with ana", "swipe cy d1 in with bo", "swipe dee d1 in with cy", "swipe cy d2 in with dee", "stats"]
    add("expiry", ex)
    add("expiry", ["zone a", "door d1 outside a", "badge x level 0 expires in 1", "badge y level 0 expires in 99999", "badge z level 0 expires in 100000", "badge w level 0 expires in 0", "badge v level 0 expires in 05",
                   "badge u level 0 expires 5", "badge t level 0 expires in", "badge s level 0 expire in 5", "badge r level 0 expires in 5 6", "swipe x d1 in", "at +1", "swipe x d1 in", "swipe y d1 in", "at +10080", "swipe y d1 in",
                   "swipe x d1 out", "swipe y d1 out", "stats"])

    # ---- queries
    q = ["zone lobby", "zone hall level 1 cap 2", "zone lab level 2 hours mon-fri@09:00-17:00", "zone vault level 9 cap 1", "door d1 outside lobby", "door d2 lobby hall", "door d3 hall lab", "door d4 hall vault",
         "badge ana level 9", "badge bo level 2", "badge cy level 1", "report", "who lobby", "who outside", "who nowhere", "where ana", "where nobody", "at tue 10:00", "report", "swipe ana d1 in", "swipe bo d1 in",
         "swipe cy d1 in", "swipe ana d2 in", "swipe bo d2 in", "swipe cy d2 in", "swipe ana d3 in", "swipe ana d4 in", "swipe bo d3 in", "where ana", "where bo", "where cy", "who lobby", "who hall", "who lab",
         "who vault", "who outside", "report", "at sat 10:00", "report", "lockdown hall on", "report", "stats"]
    add("queries", q)
    add("queries", ["zone lobby", "door d1 outside lobby", "badge ana level 1", "stats now", "report now", "where", "where a b", "who", "who a b", "frob", "lockdown", "at", "swipe", "zone", "door", "badge",
                    "stats", "who outside", "who lobby", "who nowhere", "where nobody", "where ana", "report"])

    # ---- definitions and errors
    pre = ["zone lobby", "zone hall level 1", "door d1 outside lobby", "badge ana level 1"]
    zone_errs = ["zone lobby", "zone outside", "zone Bad", "zone 9lives", "zone averyveryverylongname", "zone a12345678901", "zone x level", "zone x level 10", "zone x level 01", "zone x level -1", "zone x cap 0",
                 "zone x cap 100", "zone x cap 99 level 9", "zone x2 cap 1 cap 2", "zone x3 colour red", "zone x4 level 1 hours", "zone x5 hours bad level 2", "zone x6 level 2 hours bad", "zone x7 cap two level 3", "zone",
                 "zone y level 3 cap 2 hours *@08:00-09:00", "zone y", "zone z1-2", "zone -z", "report"]
    door_errs = ["door d1 outside lobby", "door d2 lobby x", "door d3 lobby", "door D4 outside lobby", "door d5 nowhere lobby", "door d6 outside nowhere", "door d7 lobby outside", "door d8 lobby lobby",
                 "door d9 outside outside", "door d10 outside hall", "door d11 hall lobby", "door d12 outside lobby extra", "door", "door d13 nowhere nowhere", "door d14 hall hall", "door d15 outside hall", "who hall"]
    badge_errs = ["badge ana level 2", "badge Bo level 1", "badge bo", "badge bo lvl 1", "badge bo level", "badge bo level 10", "badge bo level x", "badge bo level 3 expires in 0", "badge bo level 3 expires in 2x",
                  "badge bo level 3 expires", "badge bo level 3 expires in 5", "badge bo level 4", "badge cy level 3 expires in 99999", "badge dee level 9 expires in 100000", "badge 1x level 1", "badge", "badge eli level 0 expires in 5 6",
                  "where bo", "where cy", "where eli"]
    for lines in (zone_errs, door_errs, badge_errs):
        add("setup", pre + lines)
    add("setup", ["zone lobby level 2 cap 5 hours mon-fri@09:00-17:00", "zone hall cap 2 hours *@00:00-24:00 level 1", "zone vault hours sat@08:00-09:00 cap 1", "door a outside lobby", "door b lobby hall", "door c lobby vault",
                  "badge ana level 9", "badge bo level 0 expires in 10", "report", "who lobby", "who hall", "who vault", "where ana", "where bo", "stats"])
    swipe_errs = ["zone lobby", "zone hall level 2", "door d1 outside lobby", "door d2 lobby hall", "badge ana level 5", "badge bo level 0", "swipe", "swipe ana", "swipe ana d1", "swipe ana d1 sideways", "swipe ana d1 IN", "swipe nobody d1 in",
                  "swipe ana nodoor in", "swipe ana d1 in extra", "swipe ana d1 in with", "swipe ana d1 in with bo", "swipe ana d1 out with bo", "swipe ana d1 in to bo", "swipe ana d1 in with ana", "swipe ana d1 in with nobody",
                  "swipe nobody nodoor in", "swipe ana nodoor in with nobody", "swipe ana d1 in with bo extra", "swipe ana d2 in", "swipe ana d1 in", "swipe ana d2 in", "stats", "unknown cmd", "ZONE lobby", "swipe  ana   d2\tout", "  # c", "#swipe", "stats",
                  "frob", "swipe ana d2 out"]
    add("errors", swipe_errs, visible=False)
    add("errors", ["", "# nothing", "report", "stats", "who outside", "at mon 00:00", "at sun 23:59", "stats", "where x", "lockdown x on"])
    return cases


@family("project-turnstile", category="project", lang="java", kind="greenfield", n=8,
        summary="a door-access controller: zones with levels, caps and weekday opening hours (some crossing midnight), anti-passback modes, escorts, lockdown, idle timeouts, configurable denial precedence")
def gen(rng, n):
    for i in range(n):
        plan = dict(PLAN[i])
        tool = TOOLS[i]
        lang = plan.pop("lang")
        p = dict(plan)
        cfg = dict(ORDER=p["order"], APB=p["apb"], ESCORT=p["escort"], EVICT=p["evict"], SEAL=p["seal"], CROSS=p["cross"], EXP_OUT=p["exp_out"])
        py_sol = K.merged(K.load_src(THEME, "python", tool), K.render_config("python", cfg))
        sol = py_sol if lang == "python" else K.merged(K.load_src(THEME, lang, tool), K.render_config(lang, cfg))
        cases = make_cases(p, tool, rng, py_sol)
        prompt = VOICES[i % len(VOICES)].format(tool=tool, Lang=K.LANG_NAME[lang], run=K.how_to_run(lang, tool), num=5200 + i * 31)
        nfeat = sum([p["escort"], p["apb"] != "off", p["evict"] > 0, p["seal"], p["cross"]])
        yield K.project_task(
            theme=THEME, tool=tool, lang=lang, cases=cases, solution=sol, py_solution=py_sol,
            readme=lambda by_name, p=p, tool=tool, lang=lang: readme(p, tool, lang, by_name),
            prompt=prompt, difficulty=3 if nfeat <= 2 else (5 if nfeat == 5 else 4), slug=f"{i + 1:02d}-{tool}-{p['apb']}-{lang}",
            notes={"order": ">".join(p["order"]), **{k_: p[k_] for k_ in ("apb", "escort", "evict", "seal", "cross", "exp_out")}}, tags=["access-control", "simulation"],
        )
