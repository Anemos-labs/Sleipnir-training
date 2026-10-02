"""Go doc comments and runnable examples: every exported identifier documented (go/doc), Example functions with `// Output:` for named functions."""
from __future__ import annotations

import json
import re

from fx import Task, dd, family, langs, merged, run

from ._kit import prove_docs

CMD = "go test -count=1 ./... && python3 checks/godoc.py"

# Each module: source with placeholders @DOC:<Name>@ before every exported declaration; docs per name; examples per function.
MODULES = [
    dict(key="seedbank", pkg="seedbank", summary="Package seedbank keeps the stock of a community seed bank.",
         src='''package seedbank

import (
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
)

@DOC:MaxPackets@
const MaxPackets = 500

@DOC:ErrBadSKU@
var ErrBadSKU = errors.New("seedbank: bad sku")

@DOC:Lot@
type Lot struct {
	SKU string
	Qty int
}

@DOC:Label@
func (l Lot) Label() string {
	prefix, num, err := ParseSKU(l.SKU)
	if err != nil {
		return "?"
	}
	return fmt.Sprintf("%s #%04d x%d", prefix, num, l.Qty)
}

@DOC:ParseSKU@
func ParseSKU(code string) (string, int, error) {
	prefix, rest, ok := strings.Cut(code, "-")
	if !ok || (prefix != "VEG" && prefix != "HRB" && prefix != "FLW") {
		return "", 0, ErrBadSKU
	}
	n, err := strconv.Atoi(rest)
	if err != nil || n < 0 {
		return "", 0, ErrBadSKU
	}
	return prefix, n, nil
}

@DOC:Add@
func Add(stock map[string]int, sku string, qty int) (int, error) {
	if _, _, err := ParseSKU(sku); err != nil {
		return 0, err
	}
	if qty <= 0 || stock[sku]+qty > MaxPackets {
		return 0, fmt.Errorf("seedbank: cannot add %d packets of %s", qty, sku)
	}
	stock[sku] += qty
	return stock[sku], nil
}

@DOC:LowStock@
func LowStock(stock map[string]int, threshold int) []string {
	var out []string
	for sku, qty := range stock {
		if qty < threshold {
			out = append(out, sku)
		}
	}
	sort.Strings(out)
	return out
}
''',
         docs={"seedbank": None, "MaxPackets": "MaxPackets is the most packets of one SKU the bank will hold.", "ErrBadSKU": "ErrBadSKU is returned when a SKU is not of the form PREFIX-NUMBER with a known prefix.",
               "Lot": "Lot is a number of packets of one SKU.", "Label": "Label returns the text printed on the packet label, for example \"VEG #0042 x3\".",
               "ParseSKU": "ParseSKU splits a SKU such as VEG-0042 into its prefix and number. It returns ErrBadSKU for unknown prefixes or non-numeric numbers.",
               "Add": "Add puts qty packets of sku into stock and returns the new count. It fails if the SKU is malformed, qty is not positive, or MaxPackets would be exceeded.",
               "LowStock": "LowStock returns, in alphabetical order, the SKUs whose count is below threshold."},
         examples={"ParseSKU": 'prefix, num, err := seedbank.ParseSKU("VEG-0042")\n\tfmt.Println(prefix, num, err)', "Add": 'stock := map[string]int{"VEG-1": 2}\n\tn, err := seedbank.Add(stock, "VEG-1", 3)\n\tfmt.Println(n, err)',
                   "LowStock": 'fmt.Println(seedbank.LowStock(map[string]int{"VEG-1": 2, "HRB-4": 9, "FLW-2": 4}, 5))', "Lot_Label": 'fmt.Println(seedbank.Lot{SKU: "HRB-7", Qty: 10}.Label())'}),
    dict(key="ferry", pkg="ferry", summary="Package ferry has timetable helpers for the island ferry.",
         src='''package ferry

import (
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
)

@DOC:DayMinutes@
const DayMinutes = 24 * 60

@DOC:ErrBadTime@
var ErrBadTime = errors.New("ferry: bad time")

@DOC:Window@
type Window struct {
	Start, End int
}

@DOC:Overlap@
func (w Window) Overlap(o Window) int {
	start, end := w.Start, w.End
	if o.Start > start {
		start = o.Start
	}
	if o.End < end {
		end = o.End
	}
	if end < start {
		return 0
	}
	return end - start
}

@DOC:ParseTime@
func ParseTime(s string) (int, error) {
	h, m, ok := strings.Cut(s, ":")
	if !ok {
		return 0, ErrBadTime
	}
	hours, err1 := strconv.Atoi(h)
	minutes, err2 := strconv.Atoi(m)
	if err1 != nil || err2 != nil || hours < 0 || hours > 23 || minutes < 0 || minutes > 59 {
		return 0, ErrBadTime
	}
	return hours*60 + minutes, nil
}

@DOC:FormatTime@
func FormatTime(minutes int) string {
	minutes = ((minutes % DayMinutes) + DayMinutes) % DayMinutes
	return fmt.Sprintf("%02d:%02d", minutes/60, minutes%60)
}

@DOC:NextDeparture@
func NextDeparture(times []int, now int) (int, bool) {
	if len(times) == 0 {
		return 0, false
	}
	sorted := append([]int(nil), times...)
	sort.Ints(sorted)
	for _, t := range sorted {
		if t >= now {
			return t, true
		}
	}
	return sorted[0] + DayMinutes, true
}
''',
         docs={"ferry": None, "DayMinutes": "DayMinutes is the number of minutes in a day.", "ErrBadTime": "ErrBadTime is returned for times that are not HH:MM in the 24-hour clock.",
               "Window": "Window is a span of time in minutes after midnight; End is exclusive.", "Overlap": "Overlap returns how many minutes the two windows share, or 0 if they do not touch.",
               "ParseTime": "ParseTime converts HH:MM to minutes after midnight. It returns ErrBadTime for malformed or out-of-range input.",
               "FormatTime": "FormatTime renders minutes after midnight as HH:MM, wrapping around at midnight (also for negative values).",
               "NextDeparture": "NextDeparture returns the first departure at or after now, or tomorrow's first departure (plus DayMinutes) when none is left today. The bool is false if there are no departures at all."},
         examples={"ParseTime": 'm, err := ferry.ParseTime("07:45")\n\tfmt.Println(m, err)', "FormatTime": 'fmt.Println(ferry.FormatTime(1500))', "NextDeparture": 't, ok := ferry.NextDeparture([]int{420, 600, 900}, 500)\n\tfmt.Println(t, ok)',
                   "Window_Overlap": 'fmt.Println(ferry.Window{Start: 60, End: 120}.Overlap(ferry.Window{Start: 90, End: 200}))'}),
    dict(key="tidelab", pkg="tidelab", summary="Package tidelab converts units and bins readings for the tide laboratory.",
         src='''package tidelab

import "fmt"

@DOC:FeetPerMetre@
const FeetPerMetre = 3.28084

@DOC:Reading@
type Reading struct {
	Value float64
	Unit  string
}

@DOC:Metres@
func (r Reading) Metres() (float64, error) {
	return ToMetres(r.Value, r.Unit)
}

@DOC:ToMetres@
func ToMetres(value float64, unit string) (float64, error) {
	switch unit {
	case "m":
		return value, nil
	case "cm":
		return value / 100, nil
	case "ft":
		return value / FeetPerMetre, nil
	}
	return 0, fmt.Errorf("tidelab: unknown unit %q", unit)
}

@DOC:Clamp@
func Clamp(v, lo, hi int) int {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

@DOC:Bucketize@
func Bucketize(values, edges []int) []int {
	counts := make([]int, len(edges)+1)
	for _, v := range values {
		i := 0
		for i < len(edges) && v >= edges[i] {
			i++
		}
		counts[i]++
	}
	return counts
}
''',
         docs={"tidelab": None, "FeetPerMetre": "FeetPerMetre is the number of feet in one metre.", "Reading": "Reading is a measured length together with its unit (m, cm or ft).",
               "Metres": "Metres converts the reading to metres. It returns an error for an unknown unit.", "ToMetres": "ToMetres converts value from unit (m, cm or ft) to metres and returns an error for any other unit.",
               "Clamp": "Clamp limits v to the closed range [lo, hi].", "Bucketize": "Bucketize counts values per bucket: the result has len(edges)+1 entries and a value equal to an edge falls into the upper bucket."},
         examples={"ToMetres": 'm, err := tidelab.ToMetres(250, "cm")\n\tfmt.Println(m, err)', "Clamp": 'fmt.Println(tidelab.Clamp(5, 0, 3), tidelab.Clamp(-2, 0, 3))',
                   "Bucketize": 'fmt.Println(tidelab.Bucketize([]int{1, 5, 9, 10, 25}, []int{5, 10}))', "Reading_Metres": 'm, _ := tidelab.Reading{Value: 2, Unit: "m"}.Metres()\n\tfmt.Println(m)'}),
]

DOC_TEST = '''package PKG_test

import (
	"go/doc"
	"go/parser"
	"go/token"
	"os"
	"strings"
	"testing"
)

func TestDocComments(t *testing.T) {
	fset := token.NewFileSet()
	pkgs, err := parser.ParseDir(fset, ".", func(fi os.FileInfo) bool { return !strings.HasSuffix(fi.Name(), "_test.go") }, parser.ParseComments)
	if err != nil {
		t.Fatal(err)
	}
	for _, p := range pkgs {
		d := doc.New(p, "./", 0)
		if !strings.HasPrefix(d.Doc, "Package "+d.Name+" ") {
			t.Errorf("the package comment must start with \\"Package %s \\"", d.Name)
		}
		check := func(kind, name, text string) {
			if strings.TrimSpace(text) == "" {
				t.Errorf("%s %s has no doc comment", kind, name)
			} else if !strings.HasPrefix(text, name+" ") {
				t.Errorf("the doc comment of %s %s must start with its name", kind, name)
			}
		}
		for _, v := range d.Consts {
			check("const", v.Names[0], v.Doc)
		}
		for _, v := range d.Vars {
			check("var", v.Names[0], v.Doc)
		}
		for _, f := range d.Funcs {
			check("func", f.Name, f.Doc)
		}
		for _, ty := range d.Types {
			check("type", ty.Name, ty.Doc)
			for _, v := range ty.Consts {
				check("const", v.Names[0], v.Doc)
			}
			for _, v := range ty.Vars {
				check("var", v.Names[0], v.Doc)
			}
			for _, f := range ty.Funcs {
				check("func", f.Name, f.Doc)
			}
			for _, m := range ty.Methods {
				check("method", m.Name, m.Doc)
			}
		}
	}
}
'''

PY_CHECK = r'''import glob
import re
import sys

import clike as C

ORIGINAL = __ORIGINAL__
REQUIRED = __REQUIRED__
PKG = __PKG__


def squash(text):
    return re.sub(r"\s+", "", C.clean(text, "go"))


problems = []
src = "".join(C.read(f) for f in sorted(glob.glob(PKG + "/*.go")) if not f.endswith("_test.go"))
if squash(src) != squash(ORIGINAL):
    problems.append("the code changed: only comments may be added")
tests = "".join(open(f, encoding="utf-8").read() for f in sorted(glob.glob(PKG + "/*_test.go")))
clean = C.clean(tests, "go")
found = {}
for m in re.finditer(r"func (Example\w*)\(\) \{", clean):
    end = C.match_brace(clean, clean.index("{", m.start()))
    body = tests[m.end():end]
    found[m.group(1)] = "// Output:" in body or "// output:" in body
for name in REQUIRED:
    names = [n for n in found if n == "Example" + name or n.startswith("Example" + name + "_")]
    if not names:
        problems.append("missing an Example function for " + name)
    elif not any(found[n] for n in names):
        problems.append("the example for " + name + " has no // Output: comment")
C.report(problems)
'''


def compose(mod, documented: bool):
    text = mod["src"]
    summary = mod["summary"]
    def rep(m):
        name = m.group(1)
        doc = mod["docs"][name]
        return f"// {doc}\n" if documented and doc else ""
    text = re.sub(r"@DOC:(\w+)@\n", rep, text)
    if documented:
        text = f"// {summary}\n" + text
    return text


def example_source(mod, bodies, outputs):
    imports = ['"fmt"', f'"example.com/{mod["pkg"]}mod/{mod["pkg"]}"']
    out = f"package {mod['pkg']}_test\n\nimport (\n\t" + "\n\t".join(imports) + "\n)\n\n"
    for name, body in bodies.items():
        lines = outputs[name]
        out += f"func Example{name}() {{\n\t{body}\n\t// Output:\n" + "".join(f"\t// {ln}\n" if ln else "\t//\n" for ln in lines) + "}\n\n"
    return out


def run_examples(base, mod, bodies):
    pkg = mod["pkg"]
    body = "".join(f'\tfmt.Println("==={n}===")\n\t{{\n\t{b}\n\t}}\n' for n, b in bodies.items())
    scratch = f"package {pkg}_test\n\nimport (\n\t\"fmt\"\n\t\"testing\"\n\n\t\"example.com/{pkg}mod/{pkg}\"\n)\n\nvar _ = {pkg}.{'MaxPackets' if mod['key'] == 'seedbank' else 'DayMinutes' if mod['key'] == 'ferry' else 'FeetPerMetre'}\n\nfunc TestScratch(t *testing.T) {{\n{body}}}\n"
    r = run(merged(base, {f"{pkg}/scratch_test.go": scratch}), f"go test -count=1 -run TestScratch -v ./{pkg}/", timeout=120)
    if not r.ok:
        raise RuntimeError("examples failed to run:\n" + r.out[-1500:])
    outs, cur = {}, None
    for ln in r.out.splitlines():
        m = re.match(r"^===(\w+)===$", ln)
        if m:
            cur = m.group(1)
            outs[cur] = []
        elif cur and not ln.startswith(("--- ", "=== ", "PASS", "ok ", "FAIL")):
            outs[cur].append(ln)
    return outs


PROMPTS = [
    "The `{pkg}` package has no documentation at all, and `go doc` shows bare signatures. Add a package comment (`// Package {pkg} ...`), a doc comment for every exported constant, variable, type, function and method, "
    "each starting with the name of the thing it documents, and runnable examples (`ExampleXxx` functions with an `// Output:` comment, in an `example_test.go` file) for {req}. "
    "Only comments and the new example file may change; the examples have to pass.",
    "godoc cleanup for `{pkg}`: package comment, doc comments for everything exported (starting with the identifier's name), and examples with `// Output:` for {req}. Don't touch the code itself.",
    "Reviewer: \"`go doc {pkg}` is empty and nobody knows how to call `{first}`.\" Please document the package: a `Package {pkg}` comment, a comment on each exported identifier (the golint convention: starts with the name), "
    "and testable examples for {req}. Behaviour stays unchanged.",
]


@family("docs-go-godoc", category="docs", lang="go", kind="feature", n=6,
        summary="go doc comments for every exported identifier (checked with go/doc) plus runnable Example functions with // Output:")
def gen(rng, n):
    mods = list(MODULES) * 2
    rng.shuffle(mods)
    for i in range(n):
        mod = mods[i]
        pkg = mod["pkg"]
        original = compose(mod, False)
        documented = compose(mod, True)
        rel = f"{pkg}/{pkg}.go"
        base = {"go.mod": langs.go_mod(pkg + "mod"), rel: original}
        names = list(mod["examples"])
        k = rng.choice([2, 3, 3, 4])
        chosen = rng.sample(names, min(k, len(names)))
        chosen.sort(key=names.index)
        bodies = {n_: mod["examples"][n_] for n_ in chosen}
        solved = {rel: documented}
        outs = run_examples(solved if False else {"go.mod": base["go.mod"], rel: documented}, mod, bodies)
        ex_src = example_source(mod, bodies, outs)
        req_funcs = [c for c in chosen]
        req_text = ", ".join(f"`{c.replace('_', '.')}`" for c in req_funcs[:-1]) + (" and " if len(req_funcs) > 1 else "") + f"`{req_funcs[-1].replace('_', '.')}`"
        vis = (f"package {pkg}_test\n\nimport (\n\t\"testing\"\n\n\t\"example.com/{pkg}mod/{pkg}\"\n)\n\nfunc TestBuilds(t *testing.T) {{\n\t_ = {pkg}.{'MaxPackets' if mod['key'] == 'seedbank' else 'DayMinutes' if mod['key'] == 'ferry' else 'FeetPerMetre'}\n}}\n")
        start = {**base, f"{pkg}/smoke_test.go": vis}
        from fx import Task  # noqa
        check = PY_CHECK.replace("__ORIGINAL__", repr(original)).replace("__REQUIRED__", repr(req_funcs)).replace("__PKG__", repr(pkg))
        from generators.refactor import _kit as rk
        hidden = {f"{pkg}/doccheck_test.go": DOC_TEST.replace("PKG", pkg), "checks/godoc.py": check, **rk.clike_lib()}
        solution = {rel: documented, f"{pkg}/example_test.go": ex_src}
        prove_docs(f"{mod['key']}-{i}", start, hidden, solution, CMD, "go test -count=1 ./...")
        prompt = rng.choice(PROMPTS).format(pkg=pkg, req=req_text, first=chosen[0].replace("_", "."))
        yield Task(slug=f"{i + 1:02d}-{mod['key']}-{len(chosen)}examples", prompt=prompt, difficulty=2 if len(chosen) <= 2 else 3, start=start, hidden=hidden, solution=solution, verify=CMD,
                   tags=["godoc", "examples", "doc-comments"], notes={"module": mod["key"], "examples": chosen})
