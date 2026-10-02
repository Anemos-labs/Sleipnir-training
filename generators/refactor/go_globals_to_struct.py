"""Package-level mutable state in Go becomes a struct with injected dependencies (constructor API stated in the prompt)."""
from __future__ import annotations

import json
import re
from string import Template

from fx import Task, dd, family, langs, merged, run

from . import _kit
from ._kit import clike_lib, prove, tabify

clike = _kit.load_clike()
GO_VERIFY = "go test -count=1 ./... && python3 checks/structure.py"
GO_BEHAVIOUR = "go test -count=1 ./..."
GO_STRUCT = "python3 checks/structure.py"

# ----------------------------------------------------------------------------------------------------------------
# GA: festival wristbands (clock + counter + store)
# ----------------------------------------------------------------------------------------------------------------
BANDS_LEGACY = '''// Package wristbands issues and checks festival wristbands.
package wristbands

import (
    "fmt"
    "time"
)

// Band is one issued wristband.
type Band struct {
    ID     int
    Name   string
    Tier   string
    Issued time.Time
    Used   int
}

var maxEntries = map[string]int{"day": 1, "weekend": 3, "crew": $crew}

var (
    issued = map[int]*Band{}
    nextID = 100
    now    = time.Now
)

// Issue creates a band for a visitor.
func Issue(name, tier string) (Band, error) {
    if _, ok := maxEntries[tier]; !ok {
        return Band{}, fmt.Errorf("unknown tier %q", tier)
    }
    b := &Band{ID: nextID, Name: name, Tier: tier, Issued: now()}
    nextID++
    issued[b.ID] = b
    return *b, nil
}

// Redeem lets a band through a gate and returns the entries it has left.
func Redeem(id int) (int, error) {
    b, ok := issued[id]
    if !ok {
        return 0, fmt.Errorf("no such band %d", id)
    }
    if now().Sub(b.Issued) > $validity*time.Hour {
        return 0, fmt.Errorf("band %d expired", id)
    }
    limit := maxEntries[b.Tier]
    if b.Used >= limit {
        return 0, fmt.Errorf("band %d is used up", id)
    }
    b.Used++
    return limit - b.Used, nil
}

// Count returns how many bands of a tier have been issued.
func Count(tier string) int {
    n := 0
    for _, b := range issued {
        if b.Tier == tier {
            n++
        }
    }
    return n
}
'''

BANDS_NEW = '''// Package wristbands issues and checks festival wristbands.
package wristbands

import (
    "fmt"
    "time"
)

// Band is one issued wristband.
type Band struct {
    ID     int
    Name   string
    Tier   string
    Issued time.Time
    Used   int
}

var maxEntries = map[string]int{"day": 1, "weekend": 3, "crew": $crew}

// Options configures a Desk. The zero value uses the wall clock and starts numbering at 100.
type Options struct {
    Clock   func() time.Time
    FirstID int
}

// Desk issues and redeems bands.
type Desk struct {
    clock  func() time.Time
    nextID int
    issued map[int]*Band
}

// NewDesk returns an empty desk.
func NewDesk(opts Options) *Desk {
    clock := opts.Clock
    if clock == nil {
        clock = time.Now
    }
    first := opts.FirstID
    if first == 0 {
        first = 100
    }
    return &Desk{clock: clock, nextID: first, issued: map[int]*Band{}}
}

// Issue creates a band for a visitor.
func (d *Desk) Issue(name, tier string) (Band, error) {
    if _, ok := maxEntries[tier]; !ok {
        return Band{}, fmt.Errorf("unknown tier %q", tier)
    }
    b := &Band{ID: d.nextID, Name: name, Tier: tier, Issued: d.clock()}
    d.nextID++
    d.issued[b.ID] = b
    return *b, nil
}

// Redeem lets a band through a gate and returns the entries it has left.
func (d *Desk) Redeem(id int) (int, error) {
    b, ok := d.issued[id]
    if !ok {
        return 0, fmt.Errorf("no such band %d", id)
    }
    if d.clock().Sub(b.Issued) > $validity*time.Hour {
        return 0, fmt.Errorf("band %d expired", id)
    }
    limit := maxEntries[b.Tier]
    if b.Used >= limit {
        return 0, fmt.Errorf("band %d is used up", id)
    }
    b.Used++
    return limit - b.Used, nil
}

// Count returns how many bands of a tier have been issued.
func (d *Desk) Count(tier string) int {
    n := 0
    for _, b := range d.issued {
        if b.Tier == tier {
            n++
        }
    }
    return n
}
'''

BANDS_CASES = '''case "issue":
    b, err := @Issue(o.S[0], o.S[1])
    out = append(out, res(b.ID, err))
case "redeem":
    left, err := @Redeem(o.N[0])
    out = append(out, res(left, err))
case "count":
    out = append(out, @Count(o.S[0]))
'''


def bands_params(rng):
    return {"crew": rng.choice([5, 10, 20]), "validity": rng.choice([24, 48, 72])}


def bands_ops(rng, p, n):
    out = []
    for _ in range(n):
        ops, issued = [], 0
        for _ in range(rng.randrange(5, 14)):
            r = rng.random()
            if r < 0.35 or issued == 0:
                ops.append({"Op": "issue", "S": [rng.choice(["Ines", "Joaquin", "Kai", "Lena"]), rng.choice(["day", "weekend", "crew", "vip" if rng.random() < 0.1 else "day"])]})
                issued += 1
            elif r < 0.5:
                ops.append({"Op": "advance", "N": [rng.choice([600, 3600, 86400, 90000, 200000])]})
            elif r < 0.85:
                ops.append({"Op": "redeem", "N": [100 + rng.randrange(0, issued + 1)]})
            else:
                ops.append({"Op": "count", "S": [rng.choice(["day", "weekend", "crew"])]})
        ops += [{"Op": "count", "S": ["day"]}, {"Op": "count", "S": ["weekend"]}]
        out.append({"Ops": ops})
    return out


BANDS_RESET_LEGACY = '''issued = map[int]*Band{}
nextID = 100
now = func() time.Time { return clockNow }'''
BANDS_RESET_NEW = '''d := NEWPKG.NewDesk(NEWPKG.Options{Clock: func() time.Time { return clockNow }})'''

# ----------------------------------------------------------------------------------------------------------------
# GB: ferry deck planner (env-driven config + stores + log)
# ----------------------------------------------------------------------------------------------------------------
DECK_LEGACY = '''// Package deckplan assigns vehicles to lanes on the car deck.
package deckplan

import (
    "fmt"
    "os"
    "strconv"
)

func envInt(name string, def int) int {
    if v, err := strconv.Atoi(os.Getenv(name)); err == nil {
        return v
    }
    return def
}

var (
    lanes      = envInt("FERRY_LANES", $lanes)
    laneLength = envInt("FERRY_LANE_METRES", $length)
    placed     = map[string][]Vehicle{}
    log        []string
)

// Vehicle is something that wants to board.
type Vehicle struct {
    Plate     string
    Metres    int
    Dangerous bool
}

// Place puts a vehicle in the first lane that can take it and returns the lane name.
func Place(v Vehicle) (string, error) {
    if v.Metres <= 0 || v.Metres > laneLength {
        return "", fmt.Errorf("%s: length %d m does not fit a lane of %d m", v.Plate, v.Metres, laneLength)
    }
    for i := 1; i <= lanes; i++ {
        lane := fmt.Sprintf("L%d", i)
        used, dangerous := 0, false
        for _, p := range placed[lane] {
            used += p.Metres
            dangerous = dangerous || p.Dangerous
        }
        if used+v.Metres > laneLength || dangerous || (v.Dangerous && len(placed[lane]) > 0) {
            continue
        }
        placed[lane] = append(placed[lane], v)
        log = append(log, fmt.Sprintf("%s -> %s", v.Plate, lane))
        return lane, nil
    }
    return "", fmt.Errorf("no space for %s", v.Plate)
}

// Remaining returns the free metres per lane, in lane order.
func Remaining() []int {
    out := make([]int, 0, lanes)
    for i := 1; i <= lanes; i++ {
        used := 0
        for _, p := range placed[fmt.Sprintf("L%d", i)] {
            used += p.Metres
        }
        out = append(out, laneLength-used)
    }
    return out
}

// Log returns the placement log so far.
func Log() []string {
    return append([]string(nil), log...)
}
'''

DECK_NEW = '''// Package deckplan assigns vehicles to lanes on the car deck.
package deckplan

import "fmt"

// Vehicle is something that wants to board.
type Vehicle struct {
    Plate     string
    Metres    int
    Dangerous bool
}

// Config describes the car deck.
type Config struct {
    Lanes      int
    LaneLength int
}

// Planner assigns vehicles to the lanes of one deck.
type Planner struct {
    cfg    Config
    placed map[string][]Vehicle
    log    []string
}

// NewPlanner returns an empty planner for the given deck.
func NewPlanner(cfg Config) *Planner {
    return &Planner{cfg: cfg, placed: map[string][]Vehicle{}}
}

// Place puts a vehicle in the first lane that can take it and returns the lane name.
func (p *Planner) Place(v Vehicle) (string, error) {
    if v.Metres <= 0 || v.Metres > p.cfg.LaneLength {
        return "", fmt.Errorf("%s: length %d m does not fit a lane of %d m", v.Plate, v.Metres, p.cfg.LaneLength)
    }
    for i := 1; i <= p.cfg.Lanes; i++ {
        lane := fmt.Sprintf("L%d", i)
        used, dangerous := 0, false
        for _, q := range p.placed[lane] {
            used += q.Metres
            dangerous = dangerous || q.Dangerous
        }
        if used+v.Metres > p.cfg.LaneLength || dangerous || (v.Dangerous && len(p.placed[lane]) > 0) {
            continue
        }
        p.placed[lane] = append(p.placed[lane], v)
        p.log = append(p.log, fmt.Sprintf("%s -> %s", v.Plate, lane))
        return lane, nil
    }
    return "", fmt.Errorf("no space for %s", v.Plate)
}

// Remaining returns the free metres per lane, in lane order.
func (p *Planner) Remaining() []int {
    out := make([]int, 0, p.cfg.Lanes)
    for i := 1; i <= p.cfg.Lanes; i++ {
        used := 0
        for _, q := range p.placed[fmt.Sprintf("L%d", i)] {
            used += q.Metres
        }
        out = append(out, p.cfg.LaneLength-used)
    }
    return out
}

// Log returns the placement log so far.
func (p *Planner) Log() []string {
    return append([]string(nil), p.log...)
}
'''

DECK_CASES = '''case "place":
    lane, err := @Place(NEWPKGVehicle{Plate: o.S[0], Metres: o.N[0], Dangerous: o.N[1] == 1})
    out = append(out, res(lane, err))
case "remaining":
    out = append(out, @Remaining())
case "log":
    out = append(out, @Log())
'''


def deck_params(rng):
    return {"lanes": rng.choice([2, 3, 4]), "length": rng.choice([12, 16, 20])}


def deck_ops(rng, p, n):
    out = []
    for _ in range(n):
        ops = []
        for k in range(rng.randrange(4, 12)):
            r = rng.random()
            if r < 0.7:
                ops.append({"Op": "place", "S": [f"PL-{rng.randrange(100, 999)}"], "N": [rng.choice([2, 4, 5, 8, 12, p["length"], p["length"] + 3, 0]), 1 if rng.random() < 0.15 else 0]})
            elif r < 0.85:
                ops.append({"Op": "remaining"})
            else:
                ops.append({"Op": "log"})
        ops += [{"Op": "remaining"}, {"Op": "log"}]
        out.append({"Ops": ops})
    return out


DECK_RESET_LEGACY = '''lanes = $lanes
laneLength = $length
placed = map[string][]Vehicle{}
log = nil'''
DECK_RESET_NEW = '''d := NEWPKG.NewPlanner(NEWPKG.Config{Lanes: $lanes, LaneLength: $length})'''

# ----------------------------------------------------------------------------------------------------------------
# GC: badge scanner (clock + writer + last-seen)
# ----------------------------------------------------------------------------------------------------------------
BADGE_LEGACY = '''// Package badges decides whether a badge swipe opens a door.
package badges

import (
    "fmt"
    "io"
    "os"
    "time"
)

const cooldown = $cooldown * time.Second

var access = map[string][]string{
$access_rows
}

var (
    lastSeen           = map[string]time.Time{}
    out      io.Writer = os.Stdout
    now                = time.Now
)

func allowed(badge, door string) bool {
    for _, d := range access[badge] {
        if d == door {
            return true
        }
    }
    return false
}

// Scan records a swipe and reports whether the door opens.
func Scan(badge, door string) bool {
    key := badge + "@" + door
    if !allowed(badge, door) {
        fmt.Fprintf(out, "denied %s\\n", key)
        return false
    }
    t := now()
    if prev, seen := lastSeen[key]; seen && t.Sub(prev) < cooldown {
        fmt.Fprintf(out, "ignored repeat %s\\n", key)
        return false
    }
    lastSeen[key] = t
    fmt.Fprintf(out, "opened %s\\n", key)
    return true
}

// Seen reports whether the badge has opened the door before.
func Seen(badge, door string) bool {
    _, ok := lastSeen[badge+"@"+door]
    return ok
}
'''

BADGE_NEW = '''// Package badges decides whether a badge swipe opens a door.
package badges

import (
    "fmt"
    "io"
    "io/ioutil"
    "time"
)

const cooldown = $cooldown * time.Second

var access = map[string][]string{
$access_rows
}

// Options configures a Scanner. A nil Clock means time.Now, a nil Log discards the messages.
type Options struct {
    Clock func() time.Time
    Log   io.Writer
}

// Scanner decides whether swipes open doors.
type Scanner struct {
    clock    func() time.Time
    log      io.Writer
    lastSeen map[string]time.Time
}

// NewScanner returns a scanner with no history.
func NewScanner(opts Options) *Scanner {
    s := &Scanner{clock: opts.Clock, log: opts.Log, lastSeen: map[string]time.Time{}}
    if s.clock == nil {
        s.clock = time.Now
    }
    if s.log == nil {
        s.log = ioutil.Discard
    }
    return s
}

func allowed(badge, door string) bool {
    for _, d := range access[badge] {
        if d == door {
            return true
        }
    }
    return false
}

// Scan records a swipe and reports whether the door opens.
func (s *Scanner) Scan(badge, door string) bool {
    key := badge + "@" + door
    if !allowed(badge, door) {
        fmt.Fprintf(s.log, "denied %s\\n", key)
        return false
    }
    t := s.clock()
    if prev, seen := s.lastSeen[key]; seen && t.Sub(prev) < cooldown {
        fmt.Fprintf(s.log, "ignored repeat %s\\n", key)
        return false
    }
    s.lastSeen[key] = t
    fmt.Fprintf(s.log, "opened %s\\n", key)
    return true
}

// Seen reports whether the badge has opened the door before.
func (s *Scanner) Seen(badge, door string) bool {
    _, ok := s.lastSeen[badge+"@"+door]
    return ok
}
'''

BADGE_CASES = '''case "scan":
    out = append(out, @Scan(o.S[0], o.S[1]))
case "seen":
    out = append(out, @Seen(o.S[0], o.S[1]))
'''


def badge_params(rng):
    badges = rng.sample(["B-17", "B-22", "B-31", "B-40", "B-58"], 3)
    doors = ["lab", "store", "roof", "server"]
    access = {b: rng.sample(doors, rng.randrange(1, 4)) for b in badges}
    rows = "\n".join(f'    "{b}": {{{", ".join(json.dumps(d) for d in ds)}}},' for b, ds in access.items())
    return {"cooldown": rng.choice([5, 10, 30, 60]), "access_rows": rows, "_badges": badges, "_doors": doors}


def badge_ops(rng, p, n):
    out = []
    for _ in range(n):
        ops = []
        for _ in range(rng.randrange(5, 14)):
            r = rng.random()
            b, d = rng.choice(p["_badges"] + ["B-99"]), rng.choice(p["_doors"])
            if r < 0.55:
                ops.append({"Op": "scan", "S": [b, d]})
            elif r < 0.8:
                ops.append({"Op": "advance", "N": [rng.choice([1, 4, 5, 9, 10, 29, 30, 59, 60, 120])]})
            else:
                ops.append({"Op": "seen", "S": [b, d]})
        out.append({"Ops": ops})
    return out


BADGE_RESET_LEGACY = '''lastSeen = map[string]time.Time{}
logBuf.Reset()
out = &logBuf
now = func() time.Time { return clockNow }'''
BADGE_RESET_NEW = '''d := NEWPKG.NewScanner(NEWPKG.Options{Clock: func() time.Time { return clockNow }, Log: &logBuf})'''

DOMAINS = [
    dict(key="bands", mod="festival", pkg="wristbands", file="bands.go", legacy=BANDS_LEGACY, new=BANDS_NEW, params=bands_params, ops=bands_ops, cases=BANDS_CASES,
         reset_legacy=BANDS_RESET_LEGACY, reset_new=BANDS_RESET_NEW, ctor="NewDesk(opts Options) *Desk", types="`Options{Clock func() time.Time; FirstID int}` (zero values: wall clock, first id 100)",
         methods="`Issue`, `Redeem` and `Count`", topic="wristband desk", legacy_names=["issued", "nextID", "now"], extra_out=False,
         api_cap="`Options` has a `Clock func() time.Time` (the thing `now` is today) and a `FirstID int` (the number `nextID` starts at; zero means 100)"),
    dict(key="deck", mod="ferryops", pkg="deckplan", file="plan.go", legacy=DECK_LEGACY, new=DECK_NEW, params=deck_params, ops=deck_ops, cases=DECK_CASES,
         reset_legacy=DECK_RESET_LEGACY, reset_new=DECK_RESET_NEW, ctor="NewPlanner(cfg Config) *Planner", types="`Config{Lanes int; LaneLength int}`",
         methods="`Place`, `Remaining` and `Log`", topic="car deck planner", legacy_names=["lanes", "laneLength", "placed", "log"], extra_out=False,
         api_cap="`Config` carries `Lanes` and `LaneLength` (what the `FERRY_LANES` and `FERRY_LANE_METRES` environment variables control today); the package must not read the environment itself any more"),
    dict(key="badges", mod="doorcontrol", pkg="badges", file="scan.go", legacy=BADGE_LEGACY, new=BADGE_NEW, params=badge_params, ops=badge_ops, cases=BADGE_CASES,
         reset_legacy=BADGE_RESET_LEGACY, reset_new=BADGE_RESET_NEW, ctor="NewScanner(opts Options) *Scanner", types="`Options{Clock func() time.Time; Log io.Writer}` (nil Clock: wall clock, nil Log: discard)",
         methods="`Scan` and `Seen`", topic="door controller", legacy_names=["lastSeen", "out", "now"], extra_out=True,
         api_cap="`Options` has a `Clock func() time.Time` and a `Log io.Writer` that receives the lines now written to `os.Stdout`"),
]

DRIVER_COMMON = '''
type op struct {
    Op string
    S  []string
    N  []int
}

type scenario struct {
    Ops []op
}

func res(v any, err error) any {
    if err != nil {
        return map[string]any{"err": err.Error()}
    }
    return v
}

func normG(v any) any {
    switch x := v.(type) {
    case []any:
        if len(x) == 0 {
            return nil
        }
        for i := range x {
            x[i] = normG(x[i])
        }
        return x
    case map[string]any:
        for k := range x {
            x[k] = normG(x[k])
        }
        return x
    }
    return v
}

func outcomesG() []any {
    var scs []scenario
    if err := json.Unmarshal([]byte(casesJSON), &scs); err != nil {
        panic(err)
    }
    var all []any
    for _, sc := range scs {
        b, _ := json.Marshal(runCase(sc))
        var v any
        _ = json.Unmarshal(b, &v)
        all = append(all, normG(v))
    }
    return all
}
'''


def _driver(dom, params, legacy: bool, cases, want=None, golden=False, label="") -> str:
    subs = {k: v for k, v in params.items() if not k.startswith("_")}
    pkg = dom["pkg"]
    cj = json.dumps(cases)
    body = dom["cases"]
    body = body.replace("@", "" if legacy else "d.")
    body = body.replace("NEWPKG.", "" if legacy else f"{pkg}.").replace("NEWPKG", "" if legacy else f"{pkg}.")
    reset = Template(dom["reset_legacy"] if legacy else dom["reset_new"]).substitute(subs).replace("NEWPKG", pkg)
    extra_imports = ["bytes"] if dom["extra_out"] else []
    imports = ["encoding/hex", "encoding/json", "fmt"] if golden else ["encoding/json", "reflect"]
    imports += ["testing", "time"] + extra_imports
    imps = "".join(f'    "{x}"\n' for x in sorted(set(imports)))
    pkg_line = f"package {pkg}" if legacy else f"package {pkg}_test"
    head = f"{pkg_line}\n\nimport (\n{imps}"
    if not legacy:
        head += f'\n    "example.com/{dom["mod"]}/{pkg}"\n'
    head += ")\n\n"
    head += f"const casesJSON = `{cj}`\n"
    head += "\nvar clockNow time.Time\n"
    if dom["extra_out"]:
        head += "\nvar logBuf bytes.Buffer\n"
    run = ["func runCase(sc scenario) []any {", "    clockNow = time.Unix(1_700_000_000, 0)"]
    if dom["extra_out"] and not legacy:
        run.append("    logBuf.Reset()")
    run += ["    " + ln for ln in reset.splitlines()]
    run += ["    var out []any", "    for _, o := range sc.Ops {", "        switch o.Op {",
            '        case "advance":', "            clockNow = clockNow.Add(time.Duration(o.N[0]) * time.Second)"]
    run += ["        " + ln for ln in body.rstrip("\n").splitlines()]
    run += ["        }", "    }"]
    if dom["extra_out"]:
        run += ['    out = append(out, logBuf.String())']
    run += ["    return out", "}", ""]
    text = head + DRIVER_COMMON.replace("outcomesG", "outcomes").replace("normG", "norm")
    text += "\n" + "\n".join(run)
    if golden:
        text += dd('''
        func TestGolden(t *testing.T) {
            b, _ := json.Marshal(outcomes())
            fmt.Println("GOLDEN:" + hex.EncodeToString(b))
        }
        ''')
    else:
        text += dd(f'''
        const wantJSON = `{json.dumps(want)}`

        func TestRecordedScenarios(t *testing.T) {{
            var want []any
            if err := json.Unmarshal([]byte(wantJSON), &want); err != nil {{
                t.Fatal(err)
            }}
            got := outcomes()
            if len(got) != len(want) {{
                t.Fatalf("got %d scenarios, want %d", len(got), len(want))
            }}
            for i := range want {{
                w := norm(want[i])
                if !reflect.DeepEqual(got[i], w) {{
                    t.Errorf("scenario %d:\\n got  %v\\n want %v", i, got[i], w)
                }}
            }}
        }}
        ''')
    if "NEWPKGVehicle" in text:
        text = text.replace("NEWPKGVehicle", "Vehicle" if legacy else f"{pkg}.Vehicle")
    return tabify(text)


GLOBAL_CHECK = r'''
import re

import clike as C

FILES = C.files([".go"], dirs=[__PKGDIR__])
problems = []

VAR_RE = re.compile(r"^var\s+(\w+)([^=\n]*)(?:=\s*(.*))?$", re.M)
BLOCK_RE = re.compile(r"^var \(\n(.*?)^\)", re.M | re.S)


def top_level_vars(text):
    found = []
    for m in VAR_RE.finditer(text):
        found.append((m.group(1), m.group(2), (m.group(3) or "").strip(), m.group(0)))
    for blk in BLOCK_RE.finditer(text):
        for line in blk.group(1).splitlines():
            m = re.match(r"^[ \t]+(\w+)([^=\n]*)(?:=\s*(.*))?$", line)
            if m and m.group(1) != "_":
                found.append((m.group(1), m.group(2), (m.group(3) or "").strip(), line))
    return found


texts = {f: C.clean(C.read(f), "go") for f in FILES}
decls = {f: top_level_vars(t) for f, t in texts.items()}
dropped = {d[3] for v in decls.values() for d in v}
code = "\n".join(ln for t in texts.values() for ln in t.splitlines() if ln not in dropped)
for f in FILES:
    for name, typ, init, _line in decls[f]:
        if init.startswith(("errors.New", "fmt.Errorf")) or "regexp.MustCompile" in init:
            continue
        literal = re.match(r"^[\w\.\[\]\*]+\{", init) is not None
        mutated = re.search(r"\b" + name + r"\b(\[[^\]]*\])*\s*(=[^=]|\+=|-=|\+\+|--)", code) or re.search(
            r"(delete|append)\(\s*" + name + r"\b", code) or re.search(r"\b" + name + r"\.(Store|Add|Set|Lock|Write|Reset)\(", code)
        if not literal or mutated:
            problems.append("%s: package-level variable %s is shared mutable or hidden state" % (f, name))

for pat, what in __FORBIDDEN__:
    if re.search(pat, code):
        problems.append("direct use of " + what + " in the package code")

for kind, name in __TYPES__:
    if not re.search(r"\btype\s+" + name + r"\s+(struct|interface)", code):
        problems.append("expected a type called " + name)
for name in __METHODS__:
    if not re.search(r"func\s*\(\w+\s+\*?\w+\)\s*" + name + r"\(", code):
        problems.append("expected a method called " + name)
C.report(problems)
'''


def go_golden(files, pkg, text):
    r = run(merged(files, {f"{pkg}/golden_test.go": text}), f"go test -count=1 -run TestGolden -v ./{pkg}/", timeout=120)
    m = re.search(r"GOLDEN:([0-9a-f]+)", r.out)
    if not r.ok or not m:
        raise RuntimeError("go golden run failed:\n" + r.out[-2500:])
    return json.loads(bytes.fromhex(m.group(1)).decode())


PROMPTS = [
    "`{pkg}/{file}` ({topic}) keeps its state in package-level variables ({legacy_names}) and so cannot be used twice in one process, which is why its tests "
    "poke at unexported variables. Turn it into a type with a constructor: `{ctor}` offering {methods} as methods with the same behaviour as the "
    "functions of the same name. {api_cap}. No package-level variable may remain except constant-like lookup tables and sentinel errors, and the package code must not "
    "{forbidden_text}. The visible test shows how the new API is driven.",
    "Make the {topic} package instantiable. Right now it uses globals ({legacy_names}); refactor to a struct created by `{ctor}` with {methods}. {api_cap}. "
    "Behaviour must be identical, but there must be no mutable package-level state left and nothing may {forbidden_text}.",
    "globals to struct in `{pkg}/{file}`: `{ctor}`, methods {methods}. {api_cap}. no mutable package-level vars (lookup tables ok), must not {forbidden_text}. same behaviour as the functions",
]


@family("refactor-go-globals-to-struct", category="refactor", lang="go", kind="refactor", n=10,
        summary="package-level mutable state and hidden clock/env/stdout dependencies become a struct with a stated constructor API")
def gen(rng, n):
    order = list(DOMAINS) * 4
    rng.shuffle(order)
    for i in range(n):
        dom = order[i]
        params = dom["params"](rng)
        subs = {k: v for k, v in params.items() if not k.startswith("_")}
        pkg, rel = dom["pkg"], f"{dom['pkg']}/{dom['file']}"
        legacy = tabify(Template(dom["legacy"]).substitute(subs))
        new = tabify(Template(dom["new"]).substitute(subs))
        cases = dom["ops"](rng, params, 18)
        base = {"go.mod": langs.go_mod(dom["mod"]), rel: legacy}
        gold = _driver(dom, params, True, cases, golden=True)
        want = go_golden(base, pkg, gold)
        vis = _driver(dom, params, False, cases[:3], want[:3]).replace("TestRecordedScenarios", "TestExampleScenarios")
        # avoid clashing identifiers between the visible and the hidden test files
        vis = re.sub(r"\b(op|scenario|res|norm|outcomes|runCase|casesJSON|wantJSON|clockNow|logBuf)\b", lambda m: m.group(1) + "Ex", vis)
        vis = vis.replace('"encoding/json"', '"encoding/json"')
        hid = _driver(dom, params, False, cases, want)
        forbidden = []
        if "now" in dom["legacy_names"]:
            forbidden.append((r"time\.Now\(\)", "time.Now()"))
        if "out" in dom["legacy_names"]:
            forbidden.append((r"os\.Stdout", "os.Stdout"))
        if dom["key"] == "deck":
            forbidden.append((r"os\.Getenv", "os.Getenv"))
        forbidden_text = " or ".join({"time.Now()": "call `time.Now()`", "os.Stdout": "write to `os.Stdout`", "os.Getenv": "read the environment"}[w] for _, w in forbidden)
        ctor_name = dom["ctor"].split("(")[0]
        type_name = dom["ctor"].split("*")[-1]
        methods = re.findall(r"`(\w+)`", dom["methods"])
        struct = GLOBAL_CHECK.replace("__PKGDIR__", json.dumps(pkg)).replace("__FORBIDDEN__", repr(forbidden)).replace(
            "__TYPES__", repr([("type", type_name)])).replace("__METHODS__", repr(methods)).strip("\n") + "\n"
        hidden = {f"{pkg}/behaviour_test.go": hid, "checks/structure.py": struct, **clike_lib()}
        start = {**base, f"{pkg}/example_test.go": vis}
        solution = {rel: new}
        prove(dom["key"], start, hidden, solution, GO_BEHAVIOUR, GO_STRUCT, GO_VERIFY, behaviour_on_start=False)
        prompt = rng.choice(PROMPTS).format(pkg=pkg, file=dom["file"], topic=dom["topic"], legacy_names=", ".join(f"`{x}`" for x in dom["legacy_names"]),
                                            ctor=dom["ctor"], methods=dom["methods"], api_cap=dom["api_cap"], forbidden_text=forbidden_text)
        d = 3 if dom["key"] != "deck" else 4
        yield Task(slug=f"{i + 1:02d}-{dom['key']}", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution, verify=GO_VERIFY,
                   tags=["globals", "dependency-injection", "constructor"], notes={"domain": dom["key"]})
