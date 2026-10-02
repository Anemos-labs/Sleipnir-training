"""Go functions that call an injected collaborator far too often (rescans, N+1 calls, repeated lookups, front-to-back recomputation).
The collaborators are counted in the hidden tests; counts have a wide margin and runaway naive code is cut off by a budget."""
from __future__ import annotations

import json
import re
from string import Template

from fx import Task, family, langs, merged, run

from ._kit import prove_opt

GO_ALL = "go test -count=1 ./..."
GO_CORRECT = "go test -count=1 -run 'Test(Example|Behaviour)' ./..."
GO_PERF = "go test -count=1 -run TestCost ./..."


def tabify(text):
    out = []
    for ln in text.split("\n"):
        n = len(ln) - len(ln.lstrip(" "))
        out.append("\t" * (n // 4) + ln.lstrip(" "))
    return "\n".join(out)


def imports_block(names):
    names = sorted(set(names))
    if not names:
        return ""
    if len(names) == 1:
        return f'import "{names[0]}"\n\n'
    return "import (\n" + "".join(f'    "{n}"\n' for n in names) + ")\n\n"


# each shape: types (package declarations), naive/fast ($Fn ...), fake (test code implementing the collaborator, with counters), gen, call, metric, limit
SHAPES = {
    "rescan": dict(
        d=2, res="[]int",
        types='''// $Rec is one stored row.
type $Rec struct {
    ID     string
    Amount int
}

// $Store gives access to every stored row. Each call to All reads the whole table from disk.
type $Store interface {
    All() []$Rec
}
''', naive='''func $Fn(s $Store, ids []string) []int {
    out := make([]int, 0, len(ids))
    for _, id := range ids {
        amount := 0
        for _, r := range s.All() {
            if r.ID == id {
                amount = r.Amount
                break
            }
        }
        out = append(out, amount)
    }
    return out
}
''', fast='''func $Fn(s $Store, ids []string) []int {
    byID := map[string]int{}
    for _, r := range s.All() {
        if _, seen := byID[r.ID]; !seen {
            byID[r.ID] = r.Amount
        }
    }
    out := make([]int, 0, len(ids))
    for _, id := range ids {
        out = append(out, byID[id])
    }
    return out
}
''', fake='''type fakeStore struct {
    recs  []PKG.$Rec
    reads int
    calls int
}

func (f *fakeStore) All() []PKG.$Rec {
    f.calls++
    f.reads += len(f.recs)
    return f.recs
}

type input struct {
    f   *fakeStore
    ids []string
}

func genInput(rng *rand.Rand, big bool) input {
    n, m := rng.Intn(10), rng.Intn(10)
    if big {
        n, m = 600, 600
    }
    recs := make([]PKG.$Rec, n)
    for i := range recs {
        recs[i] = PKG.$Rec{ID: fmt.Sprintf("r%d", rng.Intn(n+3)), Amount: rng.Intn(1000)}
    }
    ids := make([]string, m)
    for i := range ids {
        ids[i] = fmt.Sprintf("r%d", rng.Intn(n+5))
    }
    return input{f: &fakeStore{recs: recs}, ids: ids}
}
''', call="PKG.$Fn(in.f, in.ids)", ref_call="reference(&fakeStore{recs: in.f.recs}, in.ids)", metric="in.f.reads", limit="3 * len(in.f.recs) + 3", unit="rows read",
        hint="the whole table is re-read for every id; read it once and index it", vocab=[
            dict(Fn="AmountsFor", Rec="Row", Store="Table", pkg="ledgerdb", noun="ledger"), dict(Fn="PricesFor", Rec="Product", Store="Catalog", pkg="shopdata", noun="catalogue"),
            dict(Fn="BalancesOf", Rec="Account", Store="Accounts", pkg="bankdata", noun="accounts")]),
    "many": dict(
        d=2, res="[]string",
        types='''// $Store resolves ids to names. GetMany answers a whole batch in a single round trip.
type $Store interface {
    Get(id string) (string, bool)
    GetMany(ids []string) map[string]string
}
''', naive='''func $Fn(s $Store, ids []string) []string {
    var out []string
    for _, id := range ids {
        if name, ok := s.Get(id); ok {
            out = append(out, name)
        }
    }
    return out
}
''', fast='''func $Fn(s $Store, ids []string) []string {
    found := s.GetMany(ids)
    var out []string
    for _, id := range ids {
        if name, ok := found[id]; ok {
            out = append(out, name)
        }
    }
    return out
}
''', fake='''type fakeStore struct {
    names map[string]string
    calls int
}

func (f *fakeStore) Get(id string) (string, bool) {
    f.calls++
    v, ok := f.names[id]
    return v, ok
}

func (f *fakeStore) GetMany(ids []string) map[string]string {
    f.calls++
    out := map[string]string{}
    for _, id := range ids {
        if v, ok := f.names[id]; ok {
            out[id] = v
        }
    }
    return out
}

type input struct {
    f   *fakeStore
    ids []string
}

func genInput(rng *rand.Rand, big bool) input {
    n, m := rng.Intn(8), rng.Intn(10)
    if big {
        n, m = 400, 400
    }
    names := map[string]string{}
    for i := 0; i < n; i++ {
        names[fmt.Sprintf("u%d", i)] = fmt.Sprintf("name%d", rng.Intn(100))
    }
    ids := make([]string, m)
    for i := range ids {
        ids[i] = fmt.Sprintf("u%d", rng.Intn(n+4))
    }
    return input{f: &fakeStore{names: names}, ids: ids}
}
''', call="PKG.$Fn(in.f, in.ids)", ref_call="reference(&fakeStore{names: in.f.names}, in.ids)", metric="in.f.calls", limit="2", unit="calls to the store",
        hint="one call per id instead of one batched call", vocab=[
            dict(Fn="AuthorNames", Store="Directory", pkg="authors", noun="author directory"), dict(Fn="OwnerNames", Store="Registry", pkg="owners", noun="owner registry"),
            dict(Fn="StaffNames", Store="HR", pkg="staff", noun="staff system")]),
    "memo": dict(
        d=2, res="int",
        types='''// $Line is one line of an order.
type $Line struct {
    SKU string
    Qty int
}

// $Pricer looks up unit prices; every call is a round trip to the pricing service.
type $Pricer interface {
    Price(sku string) int
}
''', naive='''func $Fn(p $Pricer, lines []$Line) int {
    total := 0
    for _, l := range lines {
        total += p.Price(l.SKU) * l.Qty
    }
    return total
}
''', fast='''func $Fn(p $Pricer, lines []$Line) int {
    cache := map[string]int{}
    total := 0
    for _, l := range lines {
        price, ok := cache[l.SKU]
        if !ok {
            price = p.Price(l.SKU)
            cache[l.SKU] = price
        }
        total += price * l.Qty
    }
    return total
}
''', fake='''type fakePricer struct {
    calls int
}

func (f *fakePricer) Price(sku string) int {
    f.calls++
    return len(sku)*7 + int(sku[len(sku)-1])%13
}

type input struct {
    f     *fakePricer
    lines []PKG.$Line
}

func genInput(rng *rand.Rand, big bool) input {
    n := rng.Intn(12)
    if big {
        n = 2000
    }
    lines := make([]PKG.$Line, n)
    for i := range lines {
        lines[i] = PKG.$Line{SKU: fmt.Sprintf("sku-%d", rng.Intn(30)), Qty: 1 + rng.Intn(5)}
    }
    return input{f: &fakePricer{}, lines: lines}
}
''', call="PKG.$Fn(in.f, in.lines)", ref_call="reference(&fakePricer{}, in.lines)", metric="in.f.calls", limit="40", unit="price lookups",
        hint="the same SKU is priced again and again", vocab=[
            dict(Fn="OrderTotal", Line="OrderLine", Pricer="Pricing", pkg="orders", noun="order"), dict(Fn="BasketValue", Line="BasketItem", Pricer="RateCard", pkg="baskets", noun="basket")]),
    "less": dict(
        d=3, res="int",
        types='''// $Item is something with a price.
type $Item struct {
    ID    int
    Price int
}
''', naive='''func $Fn(items []$Item, less func(a, b $Item) bool) int {
    if len(items) == 0 {
        return -1
    }
    cp := append([]$Item(nil), items...)
    sort.SliceStable(cp, func(i, j int) bool { return less(cp[i], cp[j]) })
    return cp[0].ID
}
''', fast='''func $Fn(items []$Item, less func(a, b $Item) bool) int {
    if len(items) == 0 {
        return -1
    }
    best := items[0]
    for _, it := range items[1:] {
        if less(it, best) {
            best = it
        }
    }
    return best.ID
}
''', fake='''type fakeLess struct {
    calls int
}

type input struct {
    f     *fakeLess
    items []PKG.$Item
}

func (f *fakeLess) less(a, b PKG.$Item) bool {
    f.calls++
    return a.Price < b.Price
}

func genInput(rng *rand.Rand, big bool) input {
    n := rng.Intn(15)
    if big {
        n = 3000
    }
    items := make([]PKG.$Item, n)
    for i := range items {
        items[i] = PKG.$Item{ID: i, Price: rng.Intn(100000)}
    }
    return input{f: &fakeLess{}, items: items}
}
''', call="PKG.$Fn(in.items, in.f.less)", ref_call="reference(in.items, func(a, b PKG.$Item) bool { return a.Price < b.Price })", metric="in.f.calls", limit="2 * len(in.items)",
        unit="comparisons", hint="the whole list is sorted just to find the cheapest item (equal prices: the earlier item wins)",
        imports_naive=["sort"], vocab=[dict(Fn="CheapestID", Item="Offer", pkg="offers", noun="offers"), dict(Fn="LightestID", Item="Parcel", pkg="parcels", noun="parcels")]),
    "flush": dict(
        d=2, res="[]string",
        types='''// $Sink is a buffered writer to a remote log. Flush forces everything written so far over the network.
type $Sink interface {
    Write(line string)
    Flush() error
}
''', naive='''func $Fn(s $Sink, lines []string) error {
    for _, line := range lines {
        s.Write(line)
        if err := s.Flush(); err != nil {
            return err
        }
    }
    return nil
}
''', fast='''func $Fn(s $Sink, lines []string) error {
    for _, line := range lines {
        s.Write(line)
    }
    return s.Flush()
}
''', fake='''type fakeSink struct {
    lines   []string
    flushes int
}

func (f *fakeSink) Write(line string) { f.lines = append(f.lines, line) }
func (f *fakeSink) Flush() error      { f.flushes++; return nil }

type input struct {
    f     *fakeSink
    lines []string
}

func genInput(rng *rand.Rand, big bool) input {
    n := rng.Intn(10)
    if big {
        n = 500
    }
    lines := make([]string, n)
    for i := range lines {
        lines[i] = fmt.Sprintf("event-%d", rng.Intn(1000))
    }
    return input{f: &fakeSink{}, lines: lines}
}
''', call="in.run()", ref_call="in.refRun()", metric="in.f.flushes", limit="1", unit="flushes", hint="the sink is flushed after every single line",
        special="flush", vocab=[dict(Fn="ShipLogs", Sink="LogSink", pkg="logship", noun="log shipper"), dict(Fn="PublishEvents", Sink="Outbox", pkg="eventbus", noun="event publisher")]),
    "ranges": dict(
        d=3, res="[]int",
        types='''// $Series is a long run of readings stored on disk; every call to At is a disk read.
type $Series interface {
    Len() int
    At(i int) int
}
''', naive='''func $Fn(s $Series, queries [][2]int) []int {
    out := make([]int, 0, len(queries))
    for _, q := range queries {
        sum := 0
        for i := q[0]; i < q[1]; i++ {
            sum += s.At(i)
        }
        out = append(out, sum)
    }
    return out
}
''', fast='''func $Fn(s $Series, queries [][2]int) []int {
    prefix := make([]int, s.Len()+1)
    for i := 0; i < s.Len(); i++ {
        prefix[i+1] = prefix[i] + s.At(i)
    }
    out := make([]int, 0, len(queries))
    for _, q := range queries {
        out = append(out, prefix[q[1]]-prefix[q[0]])
    }
    return out
}
''', fake='''type fakeSeries struct {
    data  []int
    reads int
}

func (f *fakeSeries) Len() int { return len(f.data) }
func (f *fakeSeries) At(i int) int {
    f.reads++
    return f.data[i]
}

type input struct {
    f *fakeSeries
    q [][2]int
}

func genInput(rng *rand.Rand, big bool) input {
    n, k := 1+rng.Intn(20), rng.Intn(6)
    if big {
        n, k = 2000, 60
    }
    data := make([]int, n)
    for i := range data {
        data[i] = rng.Intn(1000)
    }
    q := make([][2]int, k)
    for i := range q {
        lo := rng.Intn(n)
        hi := lo + rng.Intn(n-lo+1)
        q[i] = [2]int{lo, hi}
    }
    return input{f: &fakeSeries{data: data}, q: q}
}
''', call="PKG.$Fn(in.f, in.q)", ref_call="reference(&fakeSeries{data: in.f.data}, in.q)", metric="in.f.reads", limit="3 * len(in.f.data)", unit="disk reads",
        hint="every query re-reads its whole range", vocab=[dict(Fn="RangeTotals", Series="Readings", pkg="meters", noun="meter"), dict(Fn="SalesBetween", Series="DailySales", pkg="salesdb", noun="sales")]),
    "depth": dict(
        d=3, res="[]int",
        types='''// $Parents answers the tree question: the parent of a node (ok is false for the root). Every call is a database round trip.
type $Parents func(node int) (parent int, ok bool)
''', naive='''func $Fn(parent $Parents, nodes []int) []int {
    out := make([]int, 0, len(nodes))
    for _, n := range nodes {
        depth := 0
        for cur := n; ; depth++ {
            p, ok := parent(cur)
            if !ok {
                break
            }
            cur = p
        }
        out = append(out, depth)
    }
    return out
}
''', fast='''func $Fn(parent $Parents, nodes []int) []int {
    known := map[int]int{}
    var depthOf func(n int) int
    depthOf = func(n int) int {
        if d, ok := known[n]; ok {
            return d
        }
        d := 0
        if p, ok := parent(n); ok {
            d = depthOf(p) + 1
        }
        known[n] = d
        return d
    }
    out := make([]int, 0, len(nodes))
    for _, n := range nodes {
        out = append(out, depthOf(n))
    }
    return out
}
''', fake='''type fakeTree struct {
    p     []int
    calls int
}

func (f *fakeTree) parent(n int) (int, bool) {
    f.calls++
    if n == 0 {
        return 0, false
    }
    return f.p[n], true
}

type input struct {
    f     *fakeTree
    nodes []int
}

func genInput(rng *rand.Rand, big bool) input {
    n := 1 + rng.Intn(12)
    if big {
        n = 1500
    }
    p := make([]int, n)
    for i := 1; i < n; i++ {
        lo := i - 30
        if lo < 0 {
            lo = 0
        }
        p[i] = lo + rng.Intn(i-lo)
    }
    nodes := make([]int, n)
    for i := range nodes {
        nodes[i] = i
    }
    return input{f: &fakeTree{p: p}, nodes: nodes}
}
''', call="PKG.$Fn(in.f.parent, in.nodes)", ref_call="reference((&fakeTree{p: in.f.p}).parent, in.nodes)", metric="in.f.calls", limit="2 * len(in.nodes)",
        unit="parent lookups", hint="depths are recomputed from scratch for every node", vocab=[dict(Fn="Depths", Parents="ParentOf", pkg="orgtree", noun="org chart"),
                                                                                               dict(Fn="NestingLevels", Parents="FolderParent", pkg="folders", noun="folder tree")]),
}

PROMPTS = [
    "`{f}` in `{pkg}/ops.go` talks to {thing} far more often than it needs to, and the service that calls it in a loop has become the slowest part of our nightly run. {doc} "
    "Change it so the number of calls no longer grows with the amount of data in the way it does now. Results (and their order) must stay exactly as they are.",
    "perf: `{f}` ({pkg}/ops.go) {hint}. {doc} Fix it; same output. CI counts the {unit}.",
    "The {noun} export times out for big accounts. Tracing it down leads to `{f}` in `{pkg}/ops.go`: {hint}. Please fix that without altering the behaviour or the signature.",
    "Please make `{f}` (`{pkg}/ops.go`) cheaper: {hint}. {doc} The hidden checks count the {unit} for a large input, so a small constant-factor improvement will not be enough.",
]


def _shared(sp, v, pkg, f, naive_body, naive_imports):
    subs = {**v, "Fn": f, "PKG": pkg}
    fake = Template(sp["fake"]).safe_substitute(subs).replace("PKG", pkg)
    ref = Template(naive_body).safe_substitute(subs).replace(f"func {f}(", "func reference(")
    # the reference lives in the test package: qualify package types
    for t in ("Rec", "Item", "Line", "Store", "Pricer", "Sink", "Series", "Parents"):
        if t in v:
            ref = re.sub(r"(?<![\w.])" + re.escape(v[t]) + r"\b", f"{pkg}.{v[t]}", ref)
    imps = ["fmt", "math/rand", "reflect", f"example.com/{pkg}mod/{pkg}"] + list(naive_imports)
    imp_txt = "import (\n" + "".join(f'    "{x}"\n' for x in sorted(set(imps))) + ")\n"
    call = Template(sp["call"]).safe_substitute(subs).replace("PKG", pkg)
    ref_call = Template(sp["ref_call"]).safe_substitute(subs).replace("PKG", pkg)
    resq = sp["res"]
    extra = ""
    if sp.get("special") == "flush":
        extra = (f"\nfunc (in input) run() error {{ return {pkg}.{f}(in.f, in.lines) }}\nfunc (in input) refRun() error {{ return reference(&fakeSink{{}}, in.lines) }}\n")
        text = (f"package {pkg}_test\n\n{imp_txt}\nvar _ = fmt.Sprint\nvar _ = reflect.DeepEqual\nvar _ = rand.Intn\n\n{ref}\n{fake}{extra}\n"
                "func callIt(in input) []string {\n    if err := in.run(); err != nil {\n        return []string{\"error: \" + err.Error()}\n    }\n    return in.f.lines\n}\n\n"
                "func refIt(in input) []string {\n    other := &fakeSink{}\n    if err := reference(other, in.lines); err != nil {\n        return []string{\"error: \" + err.Error()}\n    }\n    return other.lines\n}\n")
    else:
        text = (f"package {pkg}_test\n\n{imp_txt}\nvar _ = fmt.Sprint\nvar _ = reflect.DeepEqual\n\n{ref}\n{fake}{extra}\n"
                f"func callIt(in input) {resq} {{ return {call} }}\nfunc refIt(in input) {resq} {{ return {ref_call} }}\n")
    text += ("\nfunc same(a, b any) bool {\n    va, vb := reflect.ValueOf(a), reflect.ValueOf(b)\n"
             "    if va.Kind() == reflect.Slice && vb.Kind() == reflect.Slice && va.Len() == 0 && vb.Len() == 0 {\n        return true\n    }\n    return reflect.DeepEqual(a, b)\n}\n")
    return tabify(text)


def _behaviour(pkg, seed):
    return tabify(f"package {pkg}_test\n\nimport (\n    \"math/rand\"\n    \"testing\"\n)\n\nfunc TestBehaviourMatchesReference(t *testing.T) {{\n"
                  f"    rng := rand.New(rand.NewSource({seed}))\n    for i := 0; i < 300; i++ {{\n        in := genInput(rng, false)\n"
                  "        want := refIt(in)\n        got := callIt(in)\n        if !same(got, want) {\n            t.Fatalf(\"got %v, want %v\", got, want)\n        }\n    }\n}\n")


def _cost(sp, pkg, seed, measure=False):
    limit = sp["limit"]
    if measure:
        check = f"    fmt.Printf(\"MEASURE|%d|%d\\n\", {sp['metric']}, {limit})\n"
    else:
        check = (f"    if got, limit := {sp['metric']}, {limit}; got > limit {{\n        t.Errorf(\"PERF: %d {sp['unit']} for a large input (limit %d): {sp['hint']}\", got, limit)\n    }}\n")
    return tabify(f"package {pkg}_test\n\nimport (\n    \"fmt\"\n    \"math/rand\"\n    \"testing\"\n)\n\nvar _ = fmt.Sprint\n\nfunc TestCost(t *testing.T) {{\n"
                  f"    in := genInput(rand.New(rand.NewSource({seed})), true)\n    got := callIt(in)\n    _ = got\n{check}" + "    if !same(callIt(genInput(rand.New(rand.NewSource(" + str(seed) + ")), true)), refIt(genInput(rand.New(rand.NewSource(" + str(seed) + ")), true))) {\n"
                  "        t.Fatal(\"result differs from the reference\")\n    }\n}\n")


def _measure(files, pkg, sp, v, f, naive_body, naive_imports, seed):
    extra = {f"{pkg}/shared_test.go": _shared(sp, v, pkg, f, naive_body, naive_imports), f"{pkg}/measure_test.go": _cost(sp, pkg, seed, True)}
    r = run(merged(files, extra), f"go test -count=1 -run TestCost -v ./{pkg}/", timeout=150)
    m = re.search(r"MEASURE\|(\d+)\|(\d+)", r.out)
    if not r.ok or not m:
        raise RuntimeError("measure failed:\n" + r.out[-2000:])
    return int(m.group(1)), int(m.group(2))


def _visible(sp, v, pkg, f, files, seed):
    """A small deterministic example, with expected values taken from the slow implementation."""
    base = _shared(sp, v, pkg, f, "", [])  # placeholder to keep the signature; replaced below
    return None


@family("optimize-go-complexity", category="optimize", lang="go", kind="feature", n=14,
        summary="go functions that rescan, re-fetch or recompute through an injected collaborator: counted calls/reads/flushes with a wide margin")
def gen(rng, n):
    order = list(SHAPES) * 3
    rng.shuffle(order)
    used = set()
    for i in range(n):
        shape = order[i]
        sp = SHAPES[shape]
        vs = [v for v in sp["vocab"] if (shape, v["Fn"]) not in used] or sp["vocab"]
        v = rng.choice(vs)
        used.add((shape, v["Fn"]))
        f, pkg = v["Fn"], v["pkg"]
        subs = {**v, "Fn": f}
        types = Template(sp["types"]).substitute(subs)
        naive_body = Template(sp["naive"]).substitute(subs)
        fast_body = Template(sp["fast"]).substitute(subs)
        naive_imports = sp.get("imports_naive", [])
        head = f"// Package {pkg} computes reports for the {v['noun']} service.\npackage {pkg}\n\n"
        ops_naive = tabify(head + imports_block(naive_imports) + naive_body)
        ops_fast = tabify(head + fast_body)
        types_src = tabify(f"package {pkg}\n\n{types}")
        files_naive = {"go.mod": langs.go_mod(pkg + "mod"), f"{pkg}/types.go": types_src, f"{pkg}/ops.go": ops_naive}
        files_fast = {"go.mod": langs.go_mod(pkg + "mod"), f"{pkg}/types.go": types_src, f"{pkg}/ops.go": ops_fast}
        seed = 90 + i
        got_naive, limit = _measure(files_naive, pkg, sp, v, f, naive_body, naive_imports, seed)
        got_fast, _ = _measure(files_fast, pkg, sp, v, f, naive_body, naive_imports, seed)
        if got_fast > limit or got_naive < 4 * max(1, limit):
            raise RuntimeError(f"{shape}/{f}: naive {got_naive}, fast {got_fast}, limit {limit}")
        # visible example: a tiny external test that uses the package API with a local fake
        vis = _visible_test(shape, sp, v, pkg, f)
        hidden = {f"{pkg}/shared_test.go": _shared(sp, v, pkg, f, naive_body, naive_imports), f"{pkg}/behaviour_test.go": _behaviour(pkg, seed), f"{pkg}/cost_test.go": _cost(sp, pkg, seed)}
        readme = (f"# {pkg}\n\nReports for the {v['noun']} service.\n\n## `{f}`\n\n{sp['hint'].capitalize()} is the problem; `types.go` documents the collaborator and what each of its calls costs.\n")
        start = {**files_naive, f"{pkg}/example_test.go": vis, "README.md": readme}
        solution = {f"{pkg}/ops.go": ops_fast}
        prove_opt(f"{shape}/{f}", start, hidden, solution, GO_CORRECT, GO_PERF, GO_ALL, timeout=180)
        doc = {"rescan": "It returns the amount stored for each id (0 for unknown ids; the first row wins).", "many": "It returns the names of the ids that exist, in order.",
               "memo": "It returns the total value of the lines.", "less": "It returns the id of the cheapest item, or -1 for no items.",
               "flush": "It writes every line to the sink, in order.", "ranges": "It returns the sum of the readings in each half-open index range.",
               "depth": "It returns the depth of each node (the root has depth 0)."}[shape]
        thing = {"rescan": "the database", "many": "the directory service", "memo": "the pricing service", "less": "the comparison callback", "flush": "the remote log",
                 "ranges": "the disk", "depth": "the tree database"}[shape]
        prompt = rng.choice(PROMPTS).format(f=f, pkg=pkg, thing=thing, doc=doc, hint=sp["hint"], unit=sp["unit"], noun=v["noun"])
        yield Task(slug=f"{i + 1:02d}-{shape}-{f.lower()}", prompt=prompt, difficulty=sp["d"], start=start, hidden=hidden, solution=solution, verify=GO_ALL,
                   tags=["complexity", "collaborator-counter", "go"], notes={"shape": shape, "naive": got_naive, "fast": got_fast, "limit": limit})


def _visible_test(shape, sp, v, pkg, f):
    """Example tests with their own tiny fakes (distinct identifiers, so they never clash with the hidden helpers)."""
    from collections import defaultdict
    v = defaultdict(str, v)
    simple = {
        "rescan": (f'type exStore struct{{ recs []{pkg}.{v["Rec"]} }}\nfunc (s exStore) All() []{pkg}.{v["Rec"]} {{ return s.recs }}\n',
                   f'    s := exStore{{recs: []{pkg}.{v["Rec"]}{{{{ID: "a", Amount: 5}}, {{ID: "b", Amount: 7}}, {{ID: "a", Amount: 9}}}}}}\n    got := {pkg}.{f}(s, []string{{"b", "a", "zz"}})\n    want := []int{{7, 5, 0}}\n'),
        "many": (f'type exStore struct{{ m map[string]string }}\nfunc (s exStore) Get(id string) (string, bool) {{ v, ok := s.m[id]; return v, ok }}\n'
                 'func (s exStore) GetMany(ids []string) map[string]string {\n    out := map[string]string{}\n    for _, id := range ids {\n        if v, ok := s.m[id]; ok {\n            out[id] = v\n        }\n    }\n    return out\n}\n',
                 f'    s := exStore{{m: map[string]string{{"u1": "Ann", "u2": "Bo"}}}}\n    got := {pkg}.{f}(s, []string{{"u2", "u9", "u1"}})\n    want := []string{{"Bo", "Ann"}}\n'),
        "memo": (f'type exPricer struct{{}}\nfunc (exPricer) Price(sku string) int {{ return len(sku) }}\n',
                 f'    got := {pkg}.{f}(exPricer{{}}, []{pkg}.{v["Line"]}{{{{SKU: "ab", Qty: 2}}, {{SKU: "abc", Qty: 1}}, {{SKU: "ab", Qty: 3}}}})\n    want := 13\n'),
        "less": ("", f'    got := {pkg}.{f}([]{pkg}.{v["Item"]}{{{{ID: 1, Price: 9}}, {{ID: 2, Price: 4}}, {{ID: 3, Price: 4}}}}, func(a, b {pkg}.{v["Item"]}) bool {{ return a.Price < b.Price }})\n    want := 2\n'),
        "flush": (f'type exSink struct{{ lines []string }}\nfunc (s *exSink) Write(l string) {{ s.lines = append(s.lines, l) }}\nfunc (s *exSink) Flush() error {{ return nil }}\n',
                  f'    s := &exSink{{}}\n    if err := {pkg}.{f}(s, []string{{"a", "b"}}); err != nil {{\n        t.Fatal(err)\n    }}\n    got := s.lines\n    want := []string{{"a", "b"}}\n'),
        "ranges": ('type exSeries []int\nfunc (s exSeries) Len() int { return len(s) }\nfunc (s exSeries) At(i int) int { return s[i] }\n',
                   f'    got := {pkg}.{f}(exSeries{{1, 2, 3, 4}}, [][2]int{{{{0, 2}}, {{1, 4}}, {{2, 2}}}})\n    want := []int{{3, 9, 0}}\n'),
        "depth": ("", f'    parents := []int{{0, 0, 1, 1, 3}}\n    got := {pkg}.{f}(func(n int) (int, bool) {{ return parents[n], n != 0 }}, []int{{0, 2, 4}})\n    want := []int{{0, 2, 3}}\n'),
    }[shape]
    decl, body = simple
    return tabify(f"package {pkg}_test\n\nimport (\n    \"reflect\"\n    \"testing\"\n\n    \"example.com/{pkg}mod/{pkg}\"\n)\n\n{decl}\nfunc TestExample(t *testing.T) {{\n{body}"
                  "    if !reflect.DeepEqual(got, want) {\n        t.Errorf(\"got %v, want %v\", got, want)\n    }\n}\n")
