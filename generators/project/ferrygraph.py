"""project-ferrygraph: journey planning on a small invented timetable network (rides, walks, change times, discounts) where the best journey is
defined by an ordered list of criteria and a total tie-break.  Reference: Python (oracle) and Java."""
from __future__ import annotations

import itertools

from fx import family

from generators.project import _kit as K

THEME = "ferrygraph"
TOOLS = ["ferrygraph", "tidetable", "quaywise", "moorings", "wharfwise", "ferrylink", "berthplan", "crossings"]
STOPS = ["Quay", "Mill", "Pier", "Lock", "Weir", "Ness", "Holm", "Cove", "Sound", "Strand", "Ferry", "Shoal", "Reach", "Spit"]
CRIT = [["arrive", "rides", "fare", "walk"], ["arrive", "fare", "rides", "walk"], ["rides", "arrive", "fare", "walk"], ["arrive", "walk", "rides", "fare"],
        ["fare", "arrive", "rides", "walk"], ["arrive", "rides", "walk", "fare"], ["walk", "arrive", "rides", "fare"], ["arrive", "fare", "walk", "rides"]]

PLAN = [
    dict(lang="java", crit=0, max_rides=3, cap=450, window=30, disc=60, change=3, nowalk=True, avoid=True, ns=8, nr=4),
    dict(lang="python", crit=1, max_rides=3, cap=400, window=25, disc=50, change=4, nowalk=False, avoid=True, ns=7, nr=4),
    dict(lang="java", crit=2, max_rides=2, cap=500, window=40, disc=80, change=2, nowalk=True, avoid=False, ns=9, nr=5),
    dict(lang="python", crit=3, max_rides=4, cap=350, window=20, disc=40, change=5, nowalk=True, avoid=True, ns=8, nr=5),
    dict(lang="java", crit=4, max_rides=3, cap=600, window=35, disc=100, change=3, nowalk=False, avoid=False, ns=7, nr=4),
    dict(lang="python", crit=5, max_rides=3, cap=380, window=45, disc=70, change=4, nowalk=True, avoid=True, ns=9, nr=5),
    dict(lang="java", crit=6, max_rides=4, cap=420, window=30, disc=30, change=2, nowalk=False, avoid=True, ns=8, nr=4),
    dict(lang="python", crit=7, max_rides=2, cap=480, window=30, disc=90, change=5, nowalk=True, avoid=False, ns=8, nr=5),
]

VOICES = [
    "We run a small ferry-and-footpath network and want a journey planner for it. The timetable is a plain text file (`network.txt`), queries come on standard input. `README.md` defines the journey model, what counts as the *best* journey (an ordered list of criteria and a total tie-break, so the answer is unique) and every output line. The tool is `{tool}`; write it in {Lang}: {run}. Visible examples: `python3 tests/run_examples.py`.",
    "build {tool} per README.md in {Lang}. timetable in network.txt, queries on stdin: route / departures / reach. {run}. the best-journey rule is a lexicographic order over (criteria..., legs) and it is spelled out - follow it literally. examples: `python3 tests/run_examples.py`",
    "Ticket FRY-{num}: journey planner `{tool}` (spec: README.md).\n\nLanguage: {Lang}; the program is {run}. Output must match byte for byte, including the fare computation (transfer discount inside a time window, daily cap) and the change-time rule. Please separate the network reader, the search and the command layer.",
    "Could you implement the planner described in README.md? It reads `network.txt` from the current directory and answers `route`, `departures` and `reach` queries from standard input. {Lang} please; the program is {run}. The visible examples (`python3 tests/run_examples.py`) are small; the hidden checks use many different networks and every error message.",
    "Greenfield in {Lang}: `{tool}`, a timetable-based planner. Everything is in README.md: the file grammar with line-numbered errors, the rules for boarding, changing and walking, the optimisation order and the output layout. {run}. Hidden checks are grouped (routes, options, departures, reach, errors, sessions).",
    "README.md has the spec for `{tool}`. Please write it in {Lang} ({run}). The part people get wrong: a change time applies only after arriving by vehicle, never after walking; a stop may not be visited twice; the destination ends the journey; and ties are broken by the leg sequence itself. `python3 tests/run_examples.py` for the visible examples.",
    "short version: ferry timetable planner, spec in README.md, {Lang}, name it {tool}. {run}",
    "Please implement the journey planner from README.md in {Lang}. Name: `{tool}`. How it is run: {run}. It must work for any network file that follows the grammar, not just the examples; the hidden checks use other networks, other query options and bad input.",
]


def readme(p: dict, tool: str, lang: str, by_name: dict) -> str:
    o: list[str] = []
    w = o.append
    crit = CRIT[p["crit"]]
    w(f"# {tool}: a journey planner for a ferry and footpath network\n")
    w(f"`{tool}` reads a timetable from `network.txt` in the current directory and answers queries given on standard input. "
      "The model is small and exact: rides on scheduled trips, walks along footpaths, change times, a fare with a transfer discount, and a precisely defined *best* journey.\n")
    w(f"Build and run it as {K.how_to_run(lang, tool)}. The program reads the network, then the whole of standard input, runs the queries line by line and exits. "
      "Exit status 1 if any `error:` line was printed, otherwise 0.\n")
    w("## 1. network.txt\n")
    w("Lines are split into words at white space; `#` starts a comment; lines without words are skipped (they count for line numbers, which start at 1). Directives:\n")
    w("* `stop NAME`: a stop. Names are a letter followed by letters, digits and `_`; they must be unique among stops.")
    w("* `walk A B MIN`: a footpath between two declared stops, in both directions, `MIN` minutes (1 to 240). A later `walk` for the same pair replaces the earlier one.")
    w(f"* `change STOP MIN`: the time (0 to 240 minutes) needed to change vehicles at `STOP`. Stops without a `change` line use {p['change']} minutes.")
    w("* `route ID fare F`: a route (a line) with the fare `F` (0 to 99999) for one ride on it. Route ids are names, unique among routes.")
    w("* `trip ID HH:MM STOP 0 STOP OFFSET STOP OFFSET ...`: a scheduled trip of a declared route. `HH:MM` is the departure from the first stop (`HH` 00 to 47: the service day may run past midnight; times never wrap), "
      "followed by at least two `STOP OFFSET` pairs: the stops in order with the minutes after the departure at which the vehicle is there (arrival and departure are the same minute). "
      "The first offset must be `0` and the offsets must strictly increase (0 to 600), and a stop may appear only once in a trip. A route may have any number of trips.")
    w("\nA problem prints `error: network.txt:LINE: MESSAGE` (or `error: cannot read network.txt`) and the program stops with status 1 without reading any query. The first problem in file order wins; messages: "
      "`unknown directive 'WORD'`, `bad line` (wrong word count, or `fare` missing), `bad name 'X'`, `duplicate name 'X'`, `unknown stop 'X'`, `unknown route 'X'`, `bad number 'X'` (not a number without leading zero, or out of its range), "
      "`bad time 'X'`, `offsets must increase`, `repeated stop 'X'`. Within a line, items are checked from left to right; for `trip`: word count, route, time, then every stop and offset pair in order (stop name, offset number, increase rule, repeated stop).\n")
    w("## 2. Journeys\n")
    w("A **journey** is a list of **legs** from the origin to the destination, starting at the query time `T0`:\n")
    w("* a **ride** leg boards a trip at a stop at the trip's time there and alights at a *later* stop of the same trip at the trip's time there (the vehicle passes the stops in between);")
    w("* a **walk** leg goes along a footpath from the stop where the traveller is to a neighbouring stop and takes the footpath's minutes.\n")
    w("**Ready time.** A traveller *leaves* a stop at the time of arrival there. To board a trip at a stop, the trip's time at that stop must be at least the stop's **ready time**: `T0` at the origin; for a stop reached by a ride, the alighting time plus the `change` time of that stop; "
      "for a stop reached by walking, the arrival time (no change time after a walk). Boarding is not possible at the last stop of a trip.\n")
    w("**Rules.** A journey may not visit a stop twice (the origin, every alighting stop and every walk destination count as visited; stops a vehicle merely passes do not). The journey ends the moment it arrives at the destination (it may not go on and come back). "
      "Two walk legs may not follow each other. At most " + str(p["max_rides"]) + " rides" + (" (a query may lower this limit with `rides N`)" if True else "") + ". The destination may be reached by a ride or by a walk. A journey of only a walk is allowed.\n")
    w("**Fare.** Each ride costs the fare of its route, except that a ride after the first one costs `max(0, fare - " + str(p["disc"]) + ")` when it boards at most " + str(p["window"]) + " minutes after the alighting time of the previous *ride* (walking in between does not matter). "
      "The fare of the journey is the sum, but at most " + str(p["cap"]) + ".\n")
    names = {"arrive": "arrival time", "rides": "number of rides", "fare": "fare", "walk": "total walking minutes"}
    w("**The best journey.** Among all journeys that follow the rules, the best is the one that is smallest by these values compared in this order: " + ", then ".join(f"`{c}` ({names[c]})" for c in crit) +
      ". Remaining ties are broken by comparing the journeys' **leg lists** element by element (a shorter list that is a prefix is smaller): a leg is the tuple `(0, route id, trip departure minutes, boarding stop, alighting stop)` for a ride and `(1, from stop, to stop)` for a walk; "
      "tuples compare element by element, text by byte order, numbers numerically. So the answer is unique for every network.\n")
    w("## 3. Queries\n")
    w("Blank lines and lines starting with `#` are ignored. A query line is a command and its words (separated by white space). Unknown command: `error: unknown command 'WORD'`. Errors in a query print one `error: ...` line and the script goes on. "
      "A stop word that is not a declared stop is `error: unknown stop 'X'`; a time is `HH:MM` as above (`error: bad time 'X'`); checks run left to right.\n")
    opts = ["`rides N` (N one digit; the limit is the smaller of N and " + str(p["max_rides"]) + ")"]
    if p["nowalk"]:
        opts.append("`nowalk` (no walk legs at all)")
    if p["avoid"]:
        opts.append("`avoid STOP` (repeatable): the journey may not alight at or walk to that stop, nor may it start... see below")
    u = "route FROM TO at HH:MM [rides N]" + (" [nowalk]" if p["nowalk"] else "") + (" [avoid STOP]..." if p["avoid"] else "")
    w(f"### `route FROM TO at HH:MM [options]`\n")
    w(f"Options (in any order, each at most as often as it makes sense): `rides N` (`N` one digit, `bad number 'X'` otherwise; the limit is the smaller of `N` and {p['max_rides']})" +
      (", `nowalk` (no walk legs)" if p["nowalk"] else "") +
      (", `avoid STOP` (repeatable; the journey may not alight at, or walk to, that stop; vehicles may still pass it; `STOP` is checked as a stop; the origin and destination may be avoided stops without effect on their own role)" if p["avoid"] else "") +
      ". Any other word is `error: bad option 'WORD'`. Too few words or `at` missing: `error: " + u + "`" + (" (also for an `avoid` without a stop)" if p["avoid"] else "") +
      ". `FROM` and `TO` equal: `error: origin and destination are the same` (checked after all other checks).\n")
    w("Output for the best journey (`HH:MM` as in the input):\n")
    w("```\njourney FROM -> TO: arrive HH:MM, N ride(s), M walk, fare F\n  HH:MM ride ROUTE A -> B (arrive HH:MM)\n  HH:MM walk A -> B (K min)\n```")
    w("with one indented line per leg in order. `ride` lines start with the boarding time; `walk` lines with the time the traveller leaves (the arrival time at `A`). `N ride(s)` is `1 ride`, `0 rides`, `2 rides`; `M` is the total walking minutes (always the word `walk` after the number). "
      f"If there is no journey: `no journey FROM -> TO`.\n")
    w("### `departures STOP at HH:MM [count N]`\n")
    w("Lists the next departures from `STOP`: for every trip that is at `STOP` at a time not before `HH:MM` and does not end there, a line `HH:MM ROUTE to LAST` (the trip's time at `STOP`, its route, its last stop), "
      "ordered by (time, route id, trip departure minutes, last stop), the first `N` (default 5; `N` is 1 or 2 digits, nonzero, else `error: bad number 'X'`). None: `no departures from STOP`. "
      "Usage: `error: usage: departures STOP at HH:MM [count N]` (any other shape).\n")
    w("### `reach STOP at HH:MM within MINUTES [rides N]`\n")
    w("For every other stop, take its best journey from `STOP` starting at `HH:MM` (same rules, rides limit as above, no `nowalk`/`avoid`); list the stops whose arrival is at most `MINUTES` minutes after the start (`MINUTES` is 0 to 9999: `error: bad number 'X'`), ordered by arrival time, then by name, "
      "as `STOP arrive HH:MM, N ride(s)`. None: `nothing reachable from STOP`. Usage: `error: usage: reach STOP at HH:MM within MINUTES [rides N]`. Other option words: `error: bad option 'WORD'`.\n")
    w("## 4. Examples\n")
    ex = [(c, r) for (c, r) in by_name.values() if c.visible]
    for c, r in ex[:3]:
        w(K.show_case(tool, c, r))
    w("The visible examples (`tests/examples.json`, run with `python3 tests/run_examples.py`) use the same format as the hidden checks: a `network.txt`, a query script, the expected output.")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------------------------------------------

def hhmm(t):
    return "%02d:%02d" % (t // 60, t % 60)


def make_network(rng, p):
    stops = rng.sample(STOPS, p["ns"])
    lines = ["# timetable of the sound", ""]
    for s in stops:
        lines.append(f"stop {s}")
    lines.append("")
    edges = set()
    for _ in range(rng.randint(3, 5)):
        a, b = rng.sample(stops, 2)
        if (a, b) not in edges and (b, a) not in edges:
            edges.add((a, b))
            lines.append(f"walk {a} {b} {rng.choice([2, 3, 4, 5, 6, 8, 10, 12])}")
    for s in rng.sample(stops, 3):
        lines.append(f"change {s} {rng.choice([0, 1, 3, 4, 6, 8])}")
    lines.append("")
    for r in range(1, p["nr"] + 1):
        rid = f"R{r}"
        lines.append(f"route {rid} fare {rng.choice([80, 100, 120, 150, 200, 250])}")
        seq = rng.sample(stops, rng.randint(3, 5))
        base = rng.choice([360, 375, 390, 400])
        for t in range(rng.randint(2, 4)):
            offs, cur = [], 0
            for _ in seq:
                offs.append(cur)
                cur += rng.randint(5, 22)
            dep = base + t * rng.choice([20, 30, 45, 60]) + rng.randint(0, 9)
            order = seq if rng.random() < 0.75 else list(reversed(seq))
            lines.append(f"trip {rid} {hhmm(dep)} " + " ".join(f"{s} {o}" for s, o in zip(order, offs)))
        lines.append("")
    return stops, "\n".join(lines) + "\n"


def make_cases(p: dict, tool: str, rng, oracle) -> list[K.Case]:
    cases: list[K.Case] = []
    cnt: dict[str, int] = {}
    stops, net = make_network(rng, p)

    def add(group, lines, visible=False, files=None):
        cnt[group] = cnt.get(group, 0) + 1
        cases.append(K.Case(name=f"{group}-{cnt[group]:02d}", group=group, stdin="\n".join(lines) + "\n", files=files if files is not None else {"network.txt": net}, visible=visible))

    def route_q(extra=""):
        a, b = rng.sample(stops, 2)
        return f"route {a} {b} at {hhmm(rng.randint(355, 520))}{extra}"

    # candidate route queries, chosen by what the oracle answers
    pool = []
    for k in range(60):
        extra = ""
        r = rng.random()
        if r < 0.15:
            extra = f" rides {rng.randint(0, 3)}"
        elif r < 0.30 and p["nowalk"]:
            extra = " nowalk"
        elif r < 0.45 and p["avoid"]:
            extra = " avoid " + rng.choice(stops)
        pool.append(K.Case(name=f"q{k}", group="q", stdin=route_q(extra) + "\n", files={"network.txt": net}))
    outs = oracle(pool)
    multi, single, none = [], [], []
    for c, r in zip(pool, outs):
        legs = r.stdout.count("\n  ")
        if r.stdout.startswith("error"):
            continue
        if r.stdout.startswith("no journey"):
            none.append(c.stdin.strip())
        elif legs >= 2:
            multi.append(c.stdin.strip())
        else:
            single.append(c.stdin.strip())
    pick = multi[:14] + single[:4] + none[:3]
    rng.shuffle(pick)
    for i in range(0, len(pick), 3):
        add("route", pick[i:i + 3], visible=(i == 0))
    # option queries: the same trip with and without options
    for k in range(4):
        a, b = rng.sample(stops, 2)
        t = hhmm(rng.randint(360, 480))
        lines = [f"route {a} {b} at {t}", f"route {a} {b} at {t} rides 1", f"route {a} {b} at {t} rides 0", f"route {a} {b} at {t} rides 9"]
        if p["nowalk"]:
            lines.append(f"route {a} {b} at {t} nowalk")
        if p["avoid"]:
            mid = rng.choice([s for s in stops if s not in (a, b)])
            lines += [f"route {a} {b} at {t} avoid {mid}", f"route {a} {b} at {t} avoid {mid} avoid {a}"]
        add("options", lines)
    # departures
    for k in range(3):
        lines = []
        for _ in range(5):
            lines.append(f"departures {rng.choice(stops)} at {hhmm(rng.randint(350, 560))}" + rng.choice(["", "", " count 2", " count 20"]))
        add("departures", lines, visible=(k == 0 and False))
    # reach
    for k in range(3):
        lines = []
        for _ in range(3):
            lines.append(f"reach {rng.choice(stops)} at {hhmm(rng.randint(355, 480))} within {rng.choice([0, 20, 45, 90, 300])}" + rng.choice(["", "", " rides 1", " rides 2"]))
        add("reach", lines)
    # query errors
    s0, s1 = stops[0], stops[1]
    errs = ["frob", "route", f"route {s0}", f"route {s0} {s1}", f"route {s0} {s1} at", f"route {s0} {s1} at 25:00", f"route {s0} {s1} at 08:60", f"route {s0} {s1} at 8:00", f"route {s0} {s1} at 48:00",
            f"route {s0} Nowhere at 08:00", f"route Nowhere {s1} at 08:00", f"route {s0} {s0} at 08:00", f"route {s0} {s1} at 08:00 bogus", f"route {s0} {s1} at 08:00 rides", f"route {s0} {s1} at 08:00 rides x",
            f"route {s0} {s1} to 08:00", f"route {s0} {s1} at 08:00 nowalk", f"route {s0} {s1} at 08:00 avoid", f"route {s0} {s1} at 08:00 avoid Nowhere",
            f"departures", f"departures {s0}", f"departures {s0} at 08:00 count", f"departures {s0} at 08:00 count 0", f"departures {s0} at 08:00 count 5 6", f"departures {s0} at 08:00 limit 5",
            f"reach {s0} at 08:00", f"reach {s0} at 08:00 within x", f"reach {s0} at 08:00 within 30 nowalk", f"reach {s0} at 08:00 within 30 rides", f"reach {s0} at 08:00 within 10000",
            f"# comment", "", f"route {s0} {s1} at 08:00 rides 2 rides 1"]
    for k in range(2):
        e = list(errs)
        rng.shuffle(e)
        add("errors", e)
    # network file errors
    good = net.split("\n")
    s0, s1 = stops[0], stops[1]
    first_trip = next(i for i, x in enumerate(good) if x.startswith("trip"))
    first_route = next(i for i, x in enumerate(good) if x.startswith("route"))
    muts = [
        ("unknown directive", lambda ls: ls.insert(2, "frob 1")),
        ("duplicate stop", lambda ls: ls.insert(3, f"stop {s0}")),
        ("bad stop name", lambda ls: ls.insert(3, "stop 9bad")),
        ("stop extra word", lambda ls: ls.insert(3, "stop Zed extra")),
        ("walk unknown stop", lambda ls: ls.insert(3, f"walk {s0} Nowhere 3")),
        ("walk zero", lambda ls: ls.append(f"walk {s0} {s1} 0")),
        ("walk big", lambda ls: ls.append(f"walk {s0} {s1} 241")),
        ("walk short", lambda ls: ls.append(f"walk {s0} {s1}")),
        ("change leading zero", lambda ls: ls.append(f"change {s0} 05")),
        ("route no fare word", lambda ls: ls.insert(first_route, "route RX cost 100")),
        ("duplicate route", lambda ls: ls.insert(first_route + 1, "route R1 fare 5")),
        ("trip unknown route", lambda ls: ls.insert(first_trip, f"trip RZ 08:00 {s0} 0 {s1} 5")),
        ("trip bad time", lambda ls: ls.insert(first_trip, f"trip R1 8:00 {s0} 0 {s1} 5")),
        ("trip time 48", lambda ls: ls.insert(first_trip, f"trip R1 48:00 {s0} 0 {s1} 5")),
        ("trip one stop", lambda ls: ls.insert(first_trip, f"trip R1 08:00 {s0} 0")),
        ("trip first offset", lambda ls: ls.insert(first_trip, f"trip R1 08:00 {s0} 3 {s1} 9")),
        ("trip flat offsets", lambda ls: ls.insert(first_trip, f"trip R1 08:00 {s0} 0 {s1} 0")),
        ("trip decreasing", lambda ls: ls.insert(first_trip, f"trip R1 08:00 {s0} 0 {s1} 9 {stops[2]} 4")),
        ("trip repeated stop", lambda ls: ls.insert(first_trip, f"trip R1 08:00 {s0} 0 {s1} 9 {s0} 14")),
        ("trip unknown stop", lambda ls: ls.insert(first_trip, f"trip R1 08:00 {s0} 0 Nowhere 9")),
        ("trip odd words", lambda ls: ls.insert(first_trip, f"trip R1 08:00 {s0} 0 {s1}")),
        ("trip big offset", lambda ls: ls.insert(first_trip, f"trip R1 08:00 {s0} 0 {s1} 601")),
    ]
    rng.shuffle(muts)
    for name, edit in muts[:14]:
        ls = list(good)
        edit(ls)
        add("network", [f"route {s0} {s1} at 08:00"], files={"network.txt": "\n".join(ls)})
    add("network", [f"route {s0} {s1} at 08:00"], files={})
    # sessions
    for k in range(6):
        lines = []
        for _ in range(rng.randint(6, 10)):
            r = rng.random()
            if r < 0.6:
                a, b = rng.sample(stops, 2)
                extra = rng.choice(["", "", " rides 2"] + ([" nowalk"] if p["nowalk"] else []) + ([" avoid " + rng.choice(stops)] if p["avoid"] else []))
                lines.append(f"route {a} {b} at {hhmm(rng.randint(355, 600))}{extra}")
            elif r < 0.8:
                lines.append(f"departures {rng.choice(stops)} at {hhmm(rng.randint(350, 560))} count {rng.randint(1, 6)}")
            else:
                lines.append(f"reach {rng.choice(stops)} at {hhmm(rng.randint(355, 480))} within {rng.choice([30, 60, 120])}")
        add("sessions", lines)
    return cases


@family("project-ferrygraph", category="project", lang="java", kind="greenfield", n=8,
        summary="a timetable journey planner: change times, walks, transfer discounts, and a uniquely defined best journey by ordered criteria and leg tie-break")
def gen(rng, n):
    for i in range(n):
        plan = dict(PLAN[i])
        tool = TOOLS[i]
        lang = plan.pop("lang")
        p = dict(plan)
        cfg = dict(CRITERIA=CRIT[p["crit"]], MAX_RIDES=p["max_rides"], FARE_CAP=p["cap"], TRANSFER_WINDOW=p["window"], TRANSFER_DISCOUNT=p["disc"], CHANGE_DEFAULT=p["change"],
                   HAS_NOWALK=p["nowalk"], HAS_AVOID=p["avoid"])
        py_sol = K.merged(K.load_src(THEME, "python", tool), K.render_config("python", cfg))
        cases = make_cases(p, tool, rng, K.oracle_runner(tool, py_sol))
        sol = py_sol if lang == "python" else K.merged(K.load_src(THEME, lang, tool), K.render_config(lang, cfg))
        prompt = VOICES[i % len(VOICES)].format(tool=tool, Lang=K.LANG_NAME[lang], run=K.how_to_run(lang, tool), num=8100 + i * 17)
        nfeat = sum([p["nowalk"], p["avoid"], p["crit"] in (2, 4, 6), p["max_rides"] >= 4])
        yield K.project_task(
            theme=THEME, tool=tool, lang=lang, cases=cases, solution=sol, py_solution=py_sol,
            readme=lambda by_name, p=p, tool=tool, lang=lang: readme(p, tool, lang, by_name),
            prompt=prompt, difficulty=3 if nfeat == 0 else (4 if nfeat <= 2 else 5), slug=f"{i + 1:02d}-{tool}-{CRIT[p['crit']][0]}-{lang}",
            notes={"criteria": CRIT[p["crit"]], "max_rides": p["max_rides"], "cap": p["cap"], "window": p["window"], "discount": p["disc"], "change": p["change"]},
            tags=["routing", "timetable"],
        )
