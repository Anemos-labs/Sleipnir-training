"""Allocation-heavy Go functions: the bar is testing.AllocsPerRun, calibrated at generation time against the reference solution."""
from __future__ import annotations

import json
import re
from string import Template

from fx import Task, family, langs, merged, run

from ._kit import prove_opt

GO_ALL = "go test -count=1 ./..."
GO_CORRECT = "go test -count=1 -run 'Test(Example|Behaviour)' ./..."
GO_PERF = "go test -count=1 -run TestAllocs ./..."


def tabify(text: str) -> str:
    out = []
    for ln in text.split("\n"):
        n = len(ln) - len(ln.lstrip(" "))
        out.append("\t" * (n // 4) + ln.lstrip(" "))
    return "\n".join(out)


# every shape: Go snippets over $F; `arg` the Go type of the input struct fields; `gen` builds a random input
SHAPES = {
    "regex": dict(
        d=2, samples=['"ORD-123456"', '"nope"', '"v1.2.3"'], res="bool", fields="S string", doc="Reports whether {noun} is well formed.",
        naive_imports=["regexp"], fast_imports=["regexp"],
        naive='''func $F(s string) bool {
    return regexp.MustCompile(`$PAT`).MatchString(s)
}
''', fast='''var re$F = regexp.MustCompile(`$PAT`)

func $F(s string) bool {
    return re$F.MatchString(s)
}
''', call="$F(in.S)", ref_call="reference(in.S)",
        gen='''func genInput(rng *rand.Rand, big bool) input {
    if big || rng.Intn(3) == 0 {
        return input{S: $VALID}
    }
    junk := "ORD-0123456789abcdefXYZ.v- "
    b := make([]byte, rng.Intn(12))
    for i := range b {
        b[i] = junk[rng.Intn(len(junk))]
    }
    return input{S: string(b)}
}
''', vocab=[dict(f="IsOrderID", noun="an order id", pat="^ORD-[0-9]{6}$", valid='fmt.Sprintf("ORD-%06d", rng.Intn(1000000))', pkg="orders"),
            dict(f="IsVersion", noun="a version string", pat=r"^v[0-9]+\.[0-9]+\.[0-9]+$", valid='fmt.Sprintf("v%d.%d.%d", rng.Intn(20), rng.Intn(20), rng.Intn(200))', pkg="releases"),
            dict(f="IsPlate", noun="a licence plate", pat="^[A-Z]{2}[0-9]{4}-[a-z]$", valid='fmt.Sprintf("%c%c%04d-%c", 65+rng.Intn(26), 65+rng.Intn(26), rng.Intn(10000), 97+rng.Intn(26))', pkg="plates")]),
    "submatch": dict(
        d=3, samples=['"kiln=12"', '"x"', '"a=b"'], res="Pair", fields="S string", decl="type Pair struct {\n    Name  string\n    Count int\n    OK    bool\n}\n", doc="Parses a `{noun}` entry such as `name=12` into its parts.",
        naive_imports=["regexp", "strconv"], fast_imports=["regexp", "strconv"],
        naive='''func $F(s string) Pair {
    m := regexp.MustCompile(`^([a-z]+)=([0-9]+)$`).FindStringSubmatch(s)
    if m == nil {
        return Pair{}
    }
    n, _ := strconv.Atoi(m[2])
    return Pair{Name: m[1], Count: n, OK: true}
}
''', fast='''var re$F = regexp.MustCompile(`^([a-z]+)=([0-9]+)$`)

func $F(s string) Pair {
    m := re$F.FindStringSubmatch(s)
    if m == nil {
        return Pair{}
    }
    n, _ := strconv.Atoi(m[2])
    return Pair{Name: m[1], Count: n, OK: true}
}
''', call="$F(in.S)", ref_call="reference(in.S)",
        gen='''func genInput(rng *rand.Rand, big bool) input {
    if big || rng.Intn(2) == 0 {
        return input{S: fmt.Sprintf("%s=%d", []string{"kiln", "loom", "vat", "press"}[rng.Intn(4)], rng.Intn(5000))}
    }
    return input{S: []string{"", "x", "a=", "=3", "A=3", "a=b", "a=1=2"}[rng.Intn(7)]}
}
''', vocab=[dict(f="ParseSetting", noun="machine setting", pkg="settings"), dict(f="ParseQuota", noun="quota", pkg="quotas")]),
    "concat": dict(
        d=1, samples=['[]string{"a", "b", "c"}', '[]string{}', '[]string{"solo"}'], res="string", fields="Items []string", doc="Joins the {noun} into one comma separated line.",
        naive_imports=[], fast_imports=["strings"],
        naive='''func $F(items []string) string {
    out := ""
    for i, item := range items {
        if i > 0 {
            out += ","
        }
        out += item
    }
    return out
}
''', fast='''func $F(items []string) string {
    var b strings.Builder
    for i, item := range items {
        if i > 0 {
            b.WriteByte(',')
        }
        b.WriteString(item)
    }
    return b.String()
}
''', call="$F(in.Items)", ref_call="reference(in.Items)",
        gen='''func genInput(rng *rand.Rand, big bool) input {
    n := rng.Intn(8)
    if big {
        n = 200
    }
    items := make([]string, n)
    for i := range items {
        items[i] = fmt.Sprintf("it%d", rng.Intn(1000))
    }
    return input{Items: items}
}
''', vocab=[dict(f="JoinTags", noun="tags", pkg="tagging"), dict(f="CSVLine", noun="cells", pkg="export"), dict(f="RouteString", noun="stops", pkg="routes")]),
    "prealloc": dict(
        d=1, samples=['5', '0', '12'], res="[]int", fields="N int", doc="Returns the first n {noun} values.",
        naive_imports=[], fast_imports=[],
        naive='''func $F(n int) []int {
    var out []int
    for i := 0; i < n; i++ {
        out = append(out, i*i%97)
    }
    return out
}
''', fast='''func $F(n int) []int {
    out := make([]int, 0, n)
    for i := 0; i < n; i++ {
        out = append(out, i*i%97)
    }
    return out
}
''', call="$F(in.N)", ref_call="reference(in.N)",
        gen='''func genInput(rng *rand.Rand, big bool) input {
    if big {
        return input{N: 4000}
    }
    return input{N: rng.Intn(30)}
}
''', vocab=[dict(f="Offsets", noun="offset", pkg="offsets"), dict(f="Weights", noun="weight", pkg="weights")]),
    "equalfold": dict(
        d=1, samples=['"Kiln", "kiln"', '"a", "b"', '"HARBOUR", "harbour"'], res="bool", fields="A string\n    B string", doc="Compares two {noun} ignoring case.",
        naive_imports=["strings"], fast_imports=["strings"],
        naive='''func $F(a, b string) bool {
    return strings.ToLower(a) == strings.ToLower(b)
}
''', fast='''func $F(a, b string) bool {
    return strings.EqualFold(a, b)
}
''', call="$F(in.A, in.B)", ref_call="reference(in.A, in.B)",
        gen='''func genInput(rng *rand.Rand, big bool) input {
    words := []string{"Harbour", "HARBOUR", "harbour", "Kiln", "kiln", "KILN", "Tide", "tide"}
    a := words[rng.Intn(len(words))]
    b := words[rng.Intn(len(words))]
    if big {
        return input{A: "HARBOUR-MASTER-OFFICE", B: "harbour-master-office"}
    }
    return input{A: a, B: b}
}
''', vocab=[dict(f="SameName", noun="names", pkg="names"), dict(f="SameCommand", noun="commands", pkg="cli")]),
    "cut": dict(
        d=1, samples=['"https://example.org/a/b"', '"nohost"', '"http://x"'], res="string", fields="URL string", doc="Returns the host part of a {noun} such as `https://host/path`.",
        naive_imports=["strings"], fast_imports=["strings"],
        naive='''func $F(url string) string {
    parts := strings.Split(url, "/")
    if len(parts) < 3 {
        return ""
    }
    return parts[2]
}
''', fast='''func $F(url string) string {
    _, rest, ok := strings.Cut(url, "//")
    if !ok {
        return ""
    }
    host, _, _ := strings.Cut(rest, "/")
    return host
}
''', call="$F(in.URL)", ref_call="reference(in.URL)",
        gen='''func genInput(rng *rand.Rand, big bool) input {
    hosts := []string{"example.org", "a.b.c", "localhost:8080", "x"}
    if big || rng.Intn(4) != 0 {
        return input{URL: "https://" + hosts[rng.Intn(len(hosts))] + "/some/long/path?q=1"}
    }
    return input{URL: []string{"", "nohost", "http:/x", "ftp://"}[rng.Intn(4)]}
}
''', vocab=[dict(f="HostOf", noun="link", pkg="links"), dict(f="SourceHost", noun="feed URL", pkg="feeds")]),
    "itoa_join": dict(
        d=2, samples=['[]int{1, -2, 300}', '[]int{}', '[]int{7}'], res="string", fields="Vals []int", doc="Formats the {noun} as a comma separated list.",
        naive_imports=["fmt", "strings"], fast_imports=["strconv"],
        naive='''func $F(vals []int) string {
    parts := []string{}
    for _, v := range vals {
        parts = append(parts, fmt.Sprintf("%d", v))
    }
    return strings.Join(parts, ",")
}
''', fast='''func $F(vals []int) string {
    buf := make([]byte, 0, 8*len(vals))
    for i, v := range vals {
        if i > 0 {
            buf = append(buf, ',')
        }
        buf = strconv.AppendInt(buf, int64(v), 10)
    }
    return string(buf)
}
''', call="$F(in.Vals)", ref_call="reference(in.Vals)",
        gen='''func genInput(rng *rand.Rand, big bool) input {
    n := rng.Intn(10)
    if big {
        n = 300
    }
    vals := make([]int, n)
    for i := range vals {
        vals[i] = rng.Intn(200000) - 1000
    }
    return input{Vals: vals}
}
''', vocab=[dict(f="FormatReadings", noun="readings", pkg="readings"), dict(f="IDList", noun="ids", pkg="idlist")]),
    "boxing": dict(
        d=2, samples=['[]int{1, 2, 3}', '[]int{}', '[]int{1000, 2000}'], res="int", fields="Vals []int", doc="Adds up the {noun}.",
        naive_imports=[], fast_imports=[],
        naive='''func $F(vals []int) int {
    var boxed []interface{}
    for _, v := range vals {
        boxed = append(boxed, v)
    }
    sum := 0
    for _, b := range boxed {
        sum += b.(int)
    }
    return sum
}
''', fast='''func $F(vals []int) int {
    sum := 0
    for _, v := range vals {
        sum += v
    }
    return sum
}
''', call="$F(in.Vals)", ref_call="reference(in.Vals)",
        gen='''func genInput(rng *rand.Rand, big bool) input {
    n := rng.Intn(20)
    if big {
        n = 500
    }
    vals := make([]int, n)
    for i := range vals {
        vals[i] = 1000 + rng.Intn(100000)
    }
    return input{Vals: vals}
}
''', vocab=[dict(f="TotalWeight", noun="weights", pkg="weighing"), dict(f="SumInvoice", noun="line amounts", pkg="invoicing")]),
    "bytes": dict(
        d=2, samples=['[]byte("abcabab")', '[]byte("")', '[]byte("aab")'], res="int", fields="B []byte", doc="Counts the occurrences of `ab` in a {noun}.",
        naive_imports=["strings"], fast_imports=["bytes"],
        naive='''func $F(b []byte) int {
    return strings.Count(string(b), "ab")
}
''', fast='''func $F(b []byte) int {
    return bytes.Count(b, []byte("ab"))
}
''', call="$F(in.B)", ref_call="reference(in.B)",
        gen='''func genInput(rng *rand.Rand, big bool) input {
    n := rng.Intn(40)
    if big {
        n = 4096
    }
    b := make([]byte, n)
    for i := range b {
        b[i] = "abc"[rng.Intn(3)]
    }
    return input{B: b}
}
''', vocab=[dict(f="CountMarkers", noun="packet payload", pkg="packets"), dict(f="CountPairs", noun="byte stream", pkg="streams")]),
    "lines": dict(
        d=2, samples=['"ok\\nERR x\\nok"', '""', '"ERR\\nERR\\n"'], res="int", fields="Text string", doc="Counts the lines of a {noun} that contain `ERR`.",
        naive_imports=["strings"], fast_imports=["strings"],
        naive='''func $F(text string) int {
    n := 0
    for _, line := range strings.Split(text, "\\n") {
        if strings.Contains(line, "ERR") {
            n++
        }
    }
    return n
}
''', fast='''func $F(text string) int {
    n := 0
    for len(text) > 0 {
        line := text
        if i := strings.IndexByte(text, '\\n'); i >= 0 {
            line, text = text[:i], text[i+1:]
        } else {
            text = ""
        }
        if strings.Contains(line, "ERR") {
            n++
        }
    }
    return n
}
''', call="$F(in.Text)", ref_call="reference(in.Text)",
        gen='''func genInput(rng *rand.Rand, big bool) input {
    n := rng.Intn(8)
    if big {
        n = 300
    }
    var b strings.Builder
    for i := 0; i < n; i++ {
        if rng.Intn(4) == 0 {
            b.WriteString("ERR disk full")
        } else {
            b.WriteString("ok line")
        }
        if i < n-1 || rng.Intn(2) == 0 {
            b.WriteByte('\\n')
        }
    }
    return input{Text: b.String()}
}
''', vocab=[dict(f="CountErrorLines", noun="log", pkg="logscan"), dict(f="FaultyRows", noun="report", pkg="reports")], test_imports=["strings"]),
}

PROMPTS = [
    "`{f}` in `{pkg}/{file}` sits on a hot path (called millions of times per hour) and the profiler says most of the time goes into allocation and garbage collection. "
    "{doc} Reduce its allocations without changing what it returns; the behaviour tests stay the same.",
    "perf: `{f}` ({pkg}/{file}) allocates far more than it needs to. {doc} Make it allocation-light (CI checks `testing.AllocsPerRun` for a typical call). Same results.",
    "pprof for the {noun} service points at `{f}` in `{pkg}/{file}`: tons of short-lived garbage per call. {doc} Rewrite it so it allocates (almost) nothing beyond its result. "
    "Do not change the signature or the output.",
    "Can you cut the allocations of `{f}` (`{pkg}/{file}`)? {doc} Behaviour has to remain identical; a benchmark in CI watches allocs/op.",
]


def _imports(names):
    names = sorted(set(names))
    if not names:
        return ""
    if len(names) == 1:
        return f'import "{names[0]}"\n\n'
    return "import (\n" + "".join(f'    "{n}"\n' for n in names) + ")\n\n"


def _pkg_source(pkg, doc, src, imports, decl=""):
    return tabify(f"// Package {pkg}: {doc}\npackage {pkg}\n\n{_imports(imports)}{decl}\n{src}")


def _resq(sp, pkg):
    res = sp["res"]
    return res if res in ("bool", "int", "string", "[]int") else f"{pkg}.{res}"


def _shared(sp, v, pkg, f, naive_src, naive_imports):
    imports = ["fmt", "math/rand", "reflect", f"example.com/{pkg}mod/{pkg}"] + sp.get("test_imports", []) + list(naive_imports)
    imp_txt = "import (\n" + "".join(f'    "{x}"\n' for x in sorted(set(imports))) + ")\n"
    ref = naive_src.replace(f"func {f}(", "func reference(")
    if sp["res"] == "Pair":
        ref = ref.replace("Pair", f"{pkg}.Pair")
    gen = Template(sp["gen"]).safe_substitute(VALID=v.get("valid", ""))
    call = sp["call"].replace("$F", f"{pkg}.{f}")
    resq = _resq(sp, pkg)
    text = (f"package {pkg}_test\n\n{imp_txt}\nvar _ = fmt.Sprint\n\ntype input struct {{\n    {sp['fields']}\n}}\n\n{ref}\n{gen}\n"
            f"func callIt(in input) {resq} {{ return {call} }}\nfunc refIt(in input) {resq} {{ return {sp['ref_call']} }}\n\n"
            "func same(a, b any) bool {\n    va, vb := reflect.ValueOf(a), reflect.ValueOf(b)\n"
            "    if va.Kind() == reflect.Slice && vb.Kind() == reflect.Slice && va.Len() == 0 && vb.Len() == 0 {\n        return true\n    }\n"
            "    return reflect.DeepEqual(a, b)\n}\n")
    return tabify(text)


def _behaviour(sp, pkg, seed):
    return tabify(f"package {pkg}_test\n\nimport (\n    \"math/rand\"\n    \"testing\"\n)\n\nfunc TestBehaviourMatchesReference(t *testing.T) {{\n"
                  f"    rng := rand.New(rand.NewSource({seed}))\n    for i := 0; i < 400; i++ {{\n        in := genInput(rng, false)\n"
                  "        got, want := callIt(in), refIt(in)\n        if !same(got, want) {\n            t.Fatalf(\"input %+v: got %v, want %v\", in, got, want)\n        }\n    }\n}\n")


def _alloc(sp, pkg, seed, limit, measure=False):
    resq = _resq(sp, pkg)
    check = ("    fmt.Printf(\"MEASURE|%.0f\\n\", got)\n" if measure else
             f"    if got > {limit} {{\n        t.Errorf(\"PERF: %.0f allocations per call (limit {limit}): the function allocates much more than it needs to\", got)\n    }}\n")
    extra = f'    "example.com/{pkg}mod/{pkg}"\n' if resq.startswith(pkg + ".") else ""
    return tabify(f"package {pkg}_test\n\nimport (\n    \"fmt\"\n    \"math/rand\"\n    \"testing\"\n{extra})\n\nvar sink {resq}\nvar _ = fmt.Sprint\n\n"
                  f"func TestAllocs(t *testing.T) {{\n    in := genInput(rand.New(rand.NewSource({seed})), true)\n"
                  "    got := testing.AllocsPerRun(30, func() { sink = callIt(in) })\n" + check
                  + "    if !same(callIt(in), refIt(in)) {\n        t.Fatal(\"result differs from the reference\")\n    }\n}\n")


def _measure(files, pkg, sp, v, f, naive_src, naive_imports, seed):
    extra = {f"{pkg}/shared_test.go": _shared(sp, v, pkg, f, naive_src, naive_imports), f"{pkg}/measure_test.go": _alloc(sp, pkg, seed, 0, True)}
    r = run(merged(files, extra), f"go test -count=1 -run TestAllocs -v ./{pkg}/", timeout=120)
    m = re.search(r"MEASURE\|(\d+)", r.out)
    if not r.ok or not m:
        raise RuntimeError("measure failed:\n" + r.out[-2000:])
    return int(m.group(1))


def _expected_literals(files, pkg, f, samples):
    lines = "\n".join(f'    fmt.Printf("RESULT|%d|%#v\\n", {i}, {pkg}.{f}({a}))' for i, a in enumerate(samples))
    text = tabify(f"package {pkg}_test\n\nimport (\n    \"fmt\"\n    \"testing\"\n\n    \"example.com/{pkg}mod/{pkg}\"\n)\n\nfunc TestPrintResults(t *testing.T) {{\n{lines}\n}}\n")
    r = run(merged(files, {f"{pkg}/print_test.go": text}), f"go test -count=1 -run TestPrintResults -v ./{pkg}/", timeout=120)
    got = {}
    for ln in r.out.splitlines():
        m = re.match(r"RESULT\|(\d+)\|(.*)$", ln)
        if m:
            got[int(m.group(1))] = m.group(2)
    if not r.ok or len(got) != len(samples):
        raise RuntimeError("expected-literal run failed:\n" + r.out[-2000:])
    return [got[i] for i in range(len(samples))]


def _visible(sp, pkg, f, files):
    samples = sp["samples"]
    lits = _expected_literals(files, pkg, f, samples)
    resq = _resq(sp, pkg)
    body = ""
    for k, (a, lit) in enumerate(zip(samples, lits)):
        body += (f"func TestExample{k + 1}(t *testing.T) {{\n    got := {pkg}.{f}({a})\n    var want {resq} = {lit}\n"
                 "    if !reflect.DeepEqual(got, want) && !(reflect.ValueOf(got).Kind() == reflect.Slice && reflect.ValueOf(got).Len() == 0 && reflect.ValueOf(want).Len() == 0) {\n"
                 "        t.Errorf(\"got %v, want %v\", got, want)\n    }\n}\n\n")
    return tabify(f"package {pkg}_test\n\nimport (\n    \"reflect\"\n    \"testing\"\n\n    \"example.com/{pkg}mod/{pkg}\"\n)\n\n{body}")


@family("optimize-go-allocs", category="optimize", lang="go", kind="feature", n=14,
        summary="allocation-heavy go functions (regexp compiled per call, += concatenation, no preallocation, boxing, conversions): AllocsPerRun bar calibrated on the reference")
def gen(rng, n):
    order = list(SHAPES) * 2
    rng.shuffle(order)
    used = set()
    for i in range(n):
        shape = order[i]
        sp = SHAPES[shape]
        vs = [v for v in sp["vocab"] if (shape, v["f"]) not in used] or sp["vocab"]
        v = rng.choice(vs)
        used.add((shape, v["f"]))
        f, pkg = v["f"], v["pkg"]
        file = "ops.go"
        subs = {"F": f, "PAT": v.get("pat", "")}
        naive_body = tabify(Template(sp["naive"]).safe_substitute(subs))
        fast_body = Template(sp["fast"]).safe_substitute(subs)
        doc = sp["doc"].format(noun=v.get("noun", "values"))
        decl = sp.get("decl", "")
        start_src = _pkg_source(pkg, "small helpers on a hot path.", Template(sp["naive"]).safe_substitute(subs), sp["naive_imports"], decl)
        sol_src = _pkg_source(pkg, "small helpers on a hot path.", fast_body, sp["fast_imports"], decl)
        seed = 50 + i
        base_files = {"go.mod": langs.go_mod(pkg + "mod"), f"{pkg}/{file}": start_src}
        sol_files = {"go.mod": langs.go_mod(pkg + "mod"), f"{pkg}/{file}": sol_src}
        a_naive = _measure(base_files, pkg, sp, v, f, naive_body, sp["naive_imports"], seed)
        a_fast = _measure(sol_files, pkg, sp, v, f, naive_body, sp["naive_imports"], seed)
        limit = a_fast if a_fast == 0 else a_fast + max(1, a_fast // 2)
        if a_naive < 3 * limit + 1:
            raise RuntimeError(f"{shape}/{f}: naive allocs {a_naive} too close to limit {limit} (fast {a_fast})")
        vis = _visible(sp, pkg, f, base_files)
        hidden = {f"{pkg}/shared_test.go": _shared(sp, v, pkg, f, naive_body, sp["naive_imports"]), f"{pkg}/behaviour_test.go": _behaviour(sp, pkg, seed),
                  f"{pkg}/alloc_test.go": _alloc(sp, pkg, seed, limit)}
        readme = f"# {pkg}\n\n## `{f}`\n\n{doc}\n\nIt is called for every request of the {v.get('noun', 'value')} service, so it must not allocate more than necessary.\n"
        start = {**base_files, f"{pkg}/example_test.go": vis, "README.md": readme}
        solution = {f"{pkg}/{file}": sol_src}
        prove_opt(f"{shape}/{f}", start, hidden, solution, GO_CORRECT, GO_PERF, GO_ALL, timeout=180)
        prompt = rng.choice(PROMPTS).format(f=f, pkg=pkg, file=file, doc=doc, noun=v.get("noun", "service").replace(" ", "-"))
        yield Task(slug=f"{i + 1:02d}-{shape}-{f.lower()}", prompt=prompt, difficulty=sp["d"], start=start, hidden=hidden, solution=solution, verify=GO_ALL,
                   tags=["allocations", "allocs-per-run", "gc"], notes={"shape": shape, "naive_allocs": a_naive, "fast_allocs": a_fast, "limit": limit})
