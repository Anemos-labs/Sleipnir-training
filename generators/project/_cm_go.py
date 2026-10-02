"""Go codemod application: legacy package `oldkit`, replacement package `kit`, a shared `model` package, and many generated
`package main` modules under app/ (each one a small program printing its demo), in several import and call shapes, plus the
migrated versions (written explicitly for each shape; the build proves they print the same thing)."""
from __future__ import annotations

import random

from generators.project import _cm_common as W

MODULE = "shop"
FALIAS = {}


def goq(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def golit(v) -> str:
    if isinstance(v, str):
        return goq(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    raise TypeError(v)


def title_body(p: dict) -> str:
    if p["title"] == "each":
        return """	words := strings.Fields(s)
	for i, w := range words {
		words[i] = strings.ToUpper(w[:1]) + strings.ToLower(w[1:])
	}
	return strings.Join(words, " ")"""
    return """	words := strings.Fields(s)
	for i, w := range words {
		if i > 0 {
			words[i] = strings.ToLower(w)
		}
	}
	t := strings.Join(words, " ")
	if t == "" {
		return ""
	}
	return strings.ToUpper(t[:1]) + strings.ToLower(t[1:])"""


def oldkit_source(p: dict) -> str:
    lo, hi = p["log"]
    return f'''// Package oldkit is the helper package this codebase has used so far.  It is being retired: see README.md.
package oldkit

import (
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"shop/model"
)

var logLines []string

var qtyRe = regexp.MustCompile(`^\\s*([0-9]+)\\s*([A-Za-z]*)\\s*$`)

// FmtAmount gives "12.50 {p['cur']}" style text for an integer number of cents; the currency defaults to "{p['cur']}".
func FmtAmount(cents int, cur ...string) string {{
	c := "{p['cur']}"
	if len(cur) > 0 {{
		c = cur[0]
	}}
	sign := ""
	if cents < 0 {{
		sign = "-"
		cents = -cents
	}}
	return fmt.Sprintf("%s%d.%02d %s", sign, cents/100, cents%100, c)
}}

// ParseQty reads "12 kg", "3x" or "7" (the unit defaults to "{p['unit']}"); ok is false when the text is not a quantity.
func ParseQty(text string) (count int, unit string, ok bool) {{
	m := qtyRe.FindStringSubmatch(text)
	if m == nil {{
		return 0, "", false
	}}
	n, err := strconv.Atoi(m[1])
	if err != nil {{
		return 0, "", false
	}}
	u := m[2]
	if u == "" {{
		u = "{p['unit']}"
	}}
	return n, u, true
}}

// PadRight pads on the right: the text stays at the left.
func PadRight(s string, width int) string {{
	if len(s) >= width {{
		return s
	}}
	return s + strings.Repeat(" ", width-len(s))
}}

// PadLeft pads on the left: the text moves to the right.
func PadLeft(s string, width int) string {{
	if len(s) >= width {{
		return s
	}}
	return strings.Repeat(" ", width-len(s)) + s
}}

// Title capitalises words.
func Title(s string) string {{
{title_body(p)}
}}

// CompareNames orders names case-insensitively, then by the exact text.
func CompareNames(a, b string) int {{
	x, y := strings.ToLower(a), strings.ToLower(b)
	if x != y {{
		if x < y {{
			return -1
		}}
		return 1
	}}
	return strings.Compare(a, b)
}}

// Pick looks up a nested map[string]any by keys; nil when a key is missing.
func Pick(m map[string]any, keys ...string) any {{
	var cur any = m
	for _, k := range keys {{
		next, ok := cur.(map[string]any)
		if !ok {{
			return nil
		}}
		cur, ok = next[k]
		if !ok {{
			return nil
		}}
	}}
	return cur
}}

// Take returns at most the first n strings.
func Take(xs []string, n int) []string {{
	if n > len(xs) {{
		n = len(xs)
	}}
	return append([]string(nil), xs[:n]...)
}}

// Groups is the result of GroupBy: the keys in order of first appearance and the items of each key.
type Groups struct {{
	Keys []string
	M    map[string][]model.Item
}}

// GroupBy buckets items by key.
func GroupBy(items []model.Item, key func(model.Item) string) Groups {{
	g := Groups{{M: map[string][]model.Item{{}}}}
	for _, it := range items {{
		k := key(it)
		if _, seen := g.M[k]; !seen {{
			g.Keys = append(g.Keys, k)
		}}
		g.M[k] = append(g.M[k], it)
	}}
	return g
}}

// Log appends "{lo}LEVEL{hi} msg key=value ..." (keys sorted) to the global log and returns the line; kv is key, value, key, value...
func Log(level, msg string, kv ...any) string {{
	ctx := map[string]string{{}}
	var keys []string
	for i := 0; i+1 < len(kv); i += 2 {{
		k := fmt.Sprint(kv[i])
		ctx[k] = fmt.Sprint(kv[i+1])
		keys = append(keys, k)
	}}
	sort.Strings(keys)
	line := "{lo}" + strings.ToUpper(level) + "{hi} " + msg
	for _, k := range keys {{
		line += " " + k + "=" + ctx[k]
	}}
	logLines = append(logLines, line)
	return line
}}

// FlushLog returns the global log and clears it.
func FlushLog() []string {{
	out := logLines
	logLines = nil
	return out
}}

// Clamp limits x to lo..hi.
func Clamp(x, lo, hi int) int {{
	if x < lo {{
		return lo
	}}
	if x > hi {{
		return hi
	}}
	return x
}}
'''


POISON = '''// Package oldkit has been retired: every function panics.
package oldkit

import "shop/model"

func gone() { panic("oldkit has been retired; use the kit package") }

func FmtAmount(cents int, cur ...string) string                { gone(); return "" }
func ParseQty(text string) (count int, unit string, ok bool)   { gone(); return }
func PadRight(s string, width int) string                      { gone(); return "" }
func PadLeft(s string, width int) string                       { gone(); return "" }
func Title(s string) string                                    { gone(); return "" }
func CompareNames(a, b string) int                             { gone(); return 0 }
func Pick(m map[string]any, keys ...string) any                { gone(); return nil }
func Take(xs []string, n int) []string                         { gone(); return nil }

type Groups struct {
	Keys []string
	M    map[string][]model.Item
}

func GroupBy(items []model.Item, key func(model.Item) string) Groups { gone(); return Groups{} }
func Log(level, msg string, kv ...any) string                        { gone(); return "" }
func FlushLog() []string                                             { gone(); return nil }
func Clamp(x, lo, hi int) int                                        { gone(); return 0 }
'''


def kit_files(p: dict) -> dict[str, str]:
    lo, hi = p["log"]
    return {
        "model/model.go": '''// Package model holds the record type the demos share.
package model

// Item is one record of the demo data.
type Item struct {
	Kind   string
	Region string
	Unit   string
}
''',
        "kit/money.go": '''// Package kit holds the shared helpers of the application (money, text, quantities, data, events).
package kit

import "fmt"

// Money is an amount in cents of a currency; both fields matter.
type Money struct {
	Cents int
	Cur   string
}

// Text gives "12.50 EUR" style text.
func (m Money) Text() string {
	cents, sign := m.Cents, ""
	if cents < 0 {
		sign = "-"
		cents = -cents
	}
	return fmt.Sprintf("%s%d.%02d %s", sign, cents/100, cents%100, m.Cur)
}
''',
        "kit/text.go": f'''package kit

import "strings"

// Align says where the text goes when it is padded.
type Align int

const (
	// AlignLeft keeps the text at the left (padding on the right).
	AlignLeft Align = iota
	// AlignRight moves the text to the right (padding on the left).
	AlignRight
)

// Pad pads s with spaces to width.
func Pad(s string, width int, align Align) string {{
	if len(s) >= width {{
		return s
	}}
	if align == AlignRight {{
		return strings.Repeat(" ", width-len(s)) + s
	}}
	return s + strings.Repeat(" ", width-len(s))
}}

// TitleCase capitalises words.
func TitleCase(s string) string {{
{title_body(p)}
}}

// CompareNames orders names case-insensitively, then by the exact text.
func CompareNames(a, b string) int {{
	x, y := strings.ToLower(a), strings.ToLower(b)
	if x != y {{
		if x < y {{
			return -1
		}}
		return 1
	}}
	return strings.Compare(a, b)
}}
''',
        "kit/qty.go": f'''package kit

import (
	"errors"
	"regexp"
	"strconv"
)

var qtyRe = regexp.MustCompile(`^\\s*([0-9]+)\\s*([A-Za-z]*)\\s*$`)

// ErrNotQty is returned by ParseQty for texts that are not a quantity.
var ErrNotQty = errors.New("not a quantity")

// Qty is a count with a unit.
type Qty struct {{
	Count int
	Unit  string
}}

// ParseQty reads "12 kg", "3x" or "7" (the unit defaults to "{p['unit']}").
func ParseQty(text string) (Qty, error) {{
	m := qtyRe.FindStringSubmatch(text)
	if m == nil {{
		return Qty{{}}, ErrNotQty
	}}
	n, err := strconv.Atoi(m[1])
	if err != nil {{
		return Qty{{}}, ErrNotQty
	}}
	u := m[2]
	if u == "" {{
		u = "{p['unit']}"
	}}
	return Qty{{Count: n, Unit: u}}, nil
}}
''',
        "kit/data.go": '''package kit

import "shop/model"

// Dig looks up a nested map[string]any along path; def when a key is missing.
func Dig(m map[string]any, path []string, def any) any {
	var cur any = m
	for _, k := range path {
		next, ok := cur.(map[string]any)
		if !ok {
			return def
		}
		cur, ok = next[k]
		if !ok {
			return def
		}
	}
	return cur
}

// First returns at most the first n strings.
func First(xs []string, n int) []string {
	if n > len(xs) {
		n = len(xs)
	}
	return append([]string(nil), xs[:n]...)
}

// Group is one bucket of GroupBy.
type Group struct {
	Key   string
	Items []model.Item
}

// GroupBy buckets items by key; the buckets come in order of first appearance of the keys.
func GroupBy(items []model.Item, key func(model.Item) string) []Group {
	var out []Group
	at := map[string]int{}
	for _, it := range items {
		k := key(it)
		i, seen := at[k]
		if !seen {
			i = len(out)
			at[k] = i
			out = append(out, Group{Key: k})
		}
		out[i].Items = append(out[i].Items, it)
	}
	return out
}

// Limit limits x to lo..hi.
func Limit(x, lo, hi int) int {
	if x < lo {
		return lo
	}
	if x > hi {
		return hi
	}
	return x
}
''',
        "kit/events.go": f'''package kit

import (
	"fmt"
	"sort"
	"strings"
)

// F holds the context fields of an event.
type F map[string]any

// Events collects event lines.
type Events struct {{
	lines []string
}}

// Emit records "{lo}LEVEL{hi} msg key=value ..." (keys sorted).  It returns nothing: see Last.
func (e *Events) Emit(level, msg string, ctx F) {{
	var keys []string
	for k := range ctx {{
		keys = append(keys, k)
	}}
	sort.Strings(keys)
	line := "{lo}" + strings.ToUpper(level) + "{hi} " + msg
	for _, k := range keys {{
		line += " " + k + "=" + fmt.Sprint(ctx[k])
	}}
	e.lines = append(e.lines, line)
}}

// Last is the most recent line.
func (e *Events) Last() string {{ return e.lines[len(e.lines)-1] }}

// Drain returns the lines and clears them.
func (e *Events) Drain() []string {{
	out := e.lines
	e.lines = nil
	return out
}}

var shared = &Events{{}}

// Default is the process-wide Events instance.
func Default() *Events {{ return shared }}
''',
    }


# ---------------------------------------------------------------------------------------------------------------
# modules
# ---------------------------------------------------------------------------------------------------------------

class Imports:
    """How a module refers to oldkit: plain `oldkit.X`, aliased `ok.X`, dot-imported `X`, or through `common.X`."""

    def __init__(self, style: str):
        self.style = style
        self.used = False

    def call(self, name: str) -> str:
        self.used = True
        return {"plain": "oldkit." + name, "alias": "legacy." + name, "dot": name, "common": "common." + name}[self.style]

    def line(self) -> str:
        return {"plain": '"shop/oldkit"', "alias": 'legacy "shop/oldkit"', "dot": '. "shop/oldkit"', "common": '"shop/app/common"'}[self.style]


class Mod:
    def __init__(self, name: str, style: str, rng: random.Random, p: dict):
        self.name, self.rng, self.p = name, rng, p
        self.I = Imports(style)
        self.old: list[str] = []
        self.new: list[str] = []
        self.demos: list[str] = []
        self.std: set[str] = set()
        self.model = False
        self.uses_log = False
        self.uses_kit_new = True
        self.nouns = rng.sample(W.ITEMS, 6)
        self._names: set[str] = set()

    def fn(self, role: str) -> str:
        base = f"{self.name}{role[:1].upper()}{role[1:]}"
        name, k = base, 1
        while name in self._names:
            k += 1
            name = f"{base}{k}"
        self._names.add(name)
        return name

    def const(self, role: str) -> str:
        return self.fn(role)

    def demo(self, fname: str, args: list[str]):
        self.std.add("fmt")
        for a in args:
            label = f"{fname}({a})"
            self.demos.append(f'out = append(out, fmt.Sprintf("%s = %#v", {goq(label)}, {fname}({a})))')

    def source(self, new: bool) -> str:
        common = self.I.style == "common"
        std = set(self.std) | {"fmt"}
        if self.uses_log and not (new and not common):
            pass
        tail = ["func demo() []string {", "\tvar out []string"] + ["\t" + d for d in self.demos]
        if self.uses_log:
            tail.append("\tout = append(out, kit.Default().Drain()...)" if (new and not common) else f"\tout = append(out, {self.I.call('FlushLog')}()...)")
        tail += ["\treturn out", "}", "", "func main() {", "\tfor _, line := range demo() {", "\t\tfmt.Println(line)", "\t}", "}"]
        imports = sorted(f'"{s}"' for s in std)
        local = ['"shop/kit"'] if (new and not common) else [self.I.line()]
        if self.model:
            local.append('"shop/model"')
        head = [f"// Demo module {self.name} of the shop application.", "package main", "", "import ("] + ["\t" + i for i in imports] + [""] + ["\t" + i for i in sorted(local)] + [")"]
        blocks = self.new if new else self.old
        return "\n".join(head) + "\n\n" + "\n\n".join(blocks) + "\n\n" + "\n".join(tail) + "\n"


def both(m: Mod, old: str, new: str | None = None):
    m.old.append(old.strip("\n"))
    m.new.append((new if new is not None else old).strip("\n"))


def sn_line_item(m: Mod):
    rng, p, I = m.rng, m.p, m.I
    f = m.fn("line")
    w1, w2 = rng.choice([10, 12, 14]), rng.choice([8, 9, 10, 12])
    cur = rng.choice([p["cur"], p["cur"], "USD", "GBP", "CHF"])
    v = rng.choice(["plain", "default", "parts"]) if cur == p["cur"] else rng.choice(["plain", "parts"])
    if v == "plain":
        old = f"""
func {f}(name string, qty, cents int) string {{
	return {I.call("PadRight")}(name, {w1}) + {I.call("PadLeft")}({I.call("FmtAmount")}(qty*cents, "{cur}"), {w2})
}}
"""
        new = f"""
func {f}(name string, qty, cents int) string {{
	return kit.Pad(name, {w1}, kit.AlignLeft) + kit.Pad(kit.Money{{Cents: qty * cents, Cur: "{cur}"}}.Text(), {w2}, kit.AlignRight)
}}
"""
    elif v == "default":
        old = f"""
func {f}(name string, qty, cents int) string {{
	total := qty * cents
	return {I.call("PadRight")}(name, {w1}) + {I.call("PadLeft")}({I.call("FmtAmount")}(total), {w2})
}}
"""
        new = f"""
func {f}(name string, qty, cents int) string {{
	total := qty * cents
	return kit.Pad(name, {w1}, kit.AlignLeft) + kit.Pad(kit.Money{{Cents: total, Cur: "{p['cur']}"}}.Text(), {w2}, kit.AlignRight)
}}
"""
    else:
        old = f"""
func {f}(name string, qty, cents int) string {{
	cells := []string{{name, {I.call("FmtAmount")}(qty*cents, "{cur}")}}
	pad := []func(string, int) string{{{I.call("PadRight")}, {I.call("PadLeft")}}}
	widths := []int{{{w1}, {w2}}}
	out := ""
	for i, c := range cells {{
		out += pad[i](c, widths[i])
	}}
	return out
}}
"""
        new = f"""
func {f}(name string, qty, cents int) string {{
	cells := []string{{name, kit.Money{{Cents: qty * cents, Cur: "{cur}"}}.Text()}}
	aligns := []kit.Align{{kit.AlignLeft, kit.AlignRight}}
	widths := []int{{{w1}, {w2}}}
	out := ""
	for i, c := range cells {{
		out += kit.Pad(c, widths[i], aligns[i])
	}}
	return out
}}
"""
    both(m, old, new)
    it = rng.sample(m.nouns, 2)
    m.demo(f, [f'"{it[0]}", {rng.randint(1, 9)}, {rng.choice([1250, 75, 9990, 100])}', f'"{it[1]} (large)", {rng.randint(10, 60)}, {rng.choice([-75, 2, 333])}'])


def sn_header_const(m: Mod):
    rng, I = m.rng, m.I
    w1, w2 = rng.choice([10, 12]), rng.choice([8, 10])
    name = m.const("header")
    f = m.fn("headerLine")
    both(m, f"""
var {name} = {I.call("PadRight")}("NAME", {w1}) + {I.call("PadLeft")}("TOTAL", {w2})

func {f}() string {{
	return {name} + "|"
}}
""", f"""
var {name} = kit.Pad("NAME", {w1}, kit.AlignLeft) + kit.Pad("TOTAL", {w2}, kit.AlignRight)

func {f}() string {{
	return {name} + "|"
}}
""")
    m.demo(f, [""])


def sn_qty(m: Mod):
    rng, p, I = m.rng, m.p, m.I
    f = m.fn("qty")
    fb = rng.choice([0, -1, 1])
    fac = {u: rng.randint(2, 12) for u in rng.sample(W.UNITS, 3)}
    const = m.const("factors")
    table = "map[string]int{" + ", ".join(f'"{u}": {n}' for u, n in fac.items()) + "}"
    v = rng.choice(["triple", "okonly", "unit"])
    if v == "triple":
        old = f"""
var {const} = {table}

func {f}(text string) int {{
	count, unit, ok := {I.call("ParseQty")}(text)
	if !ok {{
		return {fb}
	}}
	factor, found := {const}[unit]
	if !found {{
		factor = 1
	}}
	return count * factor
}}
"""
        new = f"""
var {const} = {table}

func {f}(text string) int {{
	q, err := kit.ParseQty(text)
	if err != nil {{
		return {fb}
	}}
	factor, found := {const}[q.Unit]
	if !found {{
		factor = 1
	}}
	return q.Count * factor
}}
"""
    elif v == "okonly":
        old = f"""
func {f}(text string) bool {{
	_, _, ok := {I.call("ParseQty")}(text)
	return ok
}}
"""
        new = f"""
func {f}(text string) bool {{
	_, err := kit.ParseQty(text)
	return err == nil
}}
"""
    else:
        old = f"""
func {f}(text string) string {{
	if _, unit, ok := {I.call("ParseQty")}(text); ok {{
		return unit
	}}
	return "none"
}}
"""
        new = f"""
func {f}(text string) string {{
	if q, err := kit.ParseQty(text); err == nil {{
		return q.Unit
	}}
	return "none"
}}
"""
    both(m, old, new)
    m.demo(f, [f'"{rng.randint(2, 40)} {rng.choice(list(fac))}"', f'"{rng.randint(1, 9)}x"', f'"{rng.randint(1, 30)}"', '"lots of it"', '""', f'" {rng.randint(1, 9)} L "'])


def sn_log(m: Mod):
    rng, I = m.rng, m.I
    m.uses_log = True
    f = m.fn("note")
    msg = rng.choice(["restocked", "sold out", "checked", "moved", "closed early", "inspected"])
    k = rng.randint(2, 7)
    v = rng.choice(["plain", "ret", "wrapper"])
    if v == "plain":
        old = f"""
func {f}(oid string, n int) int {{
	{I.call("Log")}("info", "{msg}", "order", oid, "count", n)
	return n * {k}
}}
"""
        new = f"""
func {f}(oid string, n int) int {{
	kit.Default().Emit("info", "{msg}", kit.F{{"order": oid, "count": n}})
	return n * {k}
}}
"""
    elif v == "ret":
        old = f"""
func {f}(oid string, n int) string {{
	line := {I.call("Log")}("warn", "{msg}", "order", oid, "left", n-{k})
	return strings.ToUpper(line)
}}
"""
        new = f"""
func {f}(oid string, n int) string {{
	events := kit.Default()
	events.Emit("warn", "{msg}", kit.F{{"order": oid, "left": n - {k}}})
	return strings.ToUpper(events.Last())
}}
"""
        m.std.add("strings")
    else:
        w = m.fn("event")
        old = f"""
func {w}(msg string, kv ...any) string {{
	return {I.call("Log")}("debug", msg, kv...)
}}

func {f}(oid string, n int) int {{
	{w}("{msg}", "order", oid, "n", n)
	return n + {k}
}}
"""
        new = f"""
func {w}(msg string, ctx kit.F) string {{
	events := kit.Default()
	events.Emit("debug", msg, ctx)
	return events.Last()
}}

func {f}(oid string, n int) int {{
	{w}("{msg}", kit.F{{"order": oid, "n": n}})
	return n + {k}
}}
"""
    both(m, old, new)
    m.demo(f, [f'"A{rng.randint(10, 99)}", {rng.randint(3, 20)}', f'"B{rng.randint(10, 99)}", {rng.randint(8, 30)}'])


def sn_pick(m: Mod):
    rng, I = m.rng, m.I
    f = m.fn("rate")
    const = m.const("rates")
    regs = rng.sample(W.REGIONS, 3)
    data = {r: {k: rng.randint(1, 90) for k in rng.sample(W.KINDS, 3)} for r in regs}
    table = 'map[string]any{"rates": map[string]any{' + ", ".join(
        f'"{r}": map[string]any{{' + ", ".join(f'"{k}": {n}' for k, n in kinds.items()) + "}" for r, kinds in data.items()) + "}}"
    d = rng.choice([0, -1, 5])
    v = rng.choice(["direct", "path", "mixed"])
    if v == "direct":
        old = f"""
var {const} = {table}

func {f}(region, kind string) int {{
	if n, ok := {I.call("Pick")}({const}, "rates", region, kind).(int); ok {{
		return n
	}}
	return {d}
}}
"""
        new = f"""
var {const} = {table}

func {f}(region, kind string) int {{
	if n, ok := kit.Dig({const}, []string{{"rates", region, kind}}, nil).(int); ok {{
		return n
	}}
	return {d}
}}
"""
    elif v == "path":
        old = f"""
var {const} = {table}

func {f}(region, kind string) int {{
	path := []string{{"rates", region, kind}}
	if n, ok := {I.call("Pick")}({const}, path...).(int); ok {{
		return n
	}}
	return {d}
}}
"""
        new = f"""
var {const} = {table}

func {f}(region, kind string) int {{
	path := []string{{"rates", region, kind}}
	if n, ok := kit.Dig({const}, path, nil).(int); ok {{
		return n
	}}
	return {d}
}}
"""
    else:
        old = f"""
var {const} = {table}

func {f}(region, kind string) int {{
	byKind, _ := {I.call("Pick")}({const}, "rates", region).(map[string]any)
	n, ok := byKind[kind].(int)
	if !ok {{
		n = {d}
	}}
	if extra, ok := {I.call("Pick")}({const}, "rates", "nowhere").(int); ok {{
		n += extra
	}}
	return n
}}
"""
        new = f"""
var {const} = {table}

func {f}(region, kind string) int {{
	byKind, _ := kit.Dig({const}, []string{{"rates", region}}, nil).(map[string]any)
	n, ok := byKind[kind].(int)
	if !ok {{
		n = {d}
	}}
	if extra, ok := kit.Dig({const}, []string{{"rates", "nowhere"}}, nil).(int); ok {{
		n += extra
	}}
	return n
}}
"""
    both(m, old, new)
    kinds0 = list(data[regs[0]])
    m.demo(f, [f'"{regs[0]}", "{kinds0[0]}"', f'"{regs[1]}", "{rng.choice(W.KINDS)}"', f'"atlantis", "{kinds0[0]}"'])


def sn_group(m: Mod):
    rng, I = m.rng, m.I
    f = m.fn("tally")
    kf = rng.choice(["Kind", "Region", "Unit"])
    n = rng.randint(2, 4)
    m.model = True
    v = rng.choice(["map", "keys", "count"])
    m.std.add("fmt")
    if v != "count":
        m.std.add("sort")
    if v == "map":
        old = f"""
func {f}(items []model.Item) []string {{
	groups := {I.call("GroupBy")}(items, func(it model.Item) string {{ return it.{kf} }})
	keys := append([]string(nil), groups.Keys...)
	sort.Strings(keys)
	var out []string
	for _, key := range keys {{
		out = append(out, fmt.Sprintf("%s=%d", key, len(groups.M[key])))
	}}
	return {I.call("Take")}(out, {n})
}}
"""
        new = f"""
func {f}(items []model.Item) []string {{
	sizes := map[string]int{{}}
	var keys []string
	for _, g := range kit.GroupBy(items, func(it model.Item) string {{ return it.{kf} }}) {{
		sizes[g.Key] = len(g.Items)
		keys = append(keys, g.Key)
	}}
	sort.Strings(keys)
	var out []string
	for _, key := range keys {{
		out = append(out, fmt.Sprintf("%s=%d", key, sizes[key]))
	}}
	return kit.First(out, {n})
}}
"""
    elif v == "keys":
        old = f"""
func {f}(items []model.Item) []string {{
	groups := {I.call("GroupBy")}(items, func(it model.Item) string {{ return it.{kf} }})
	var rows []string
	for _, key := range groups.Keys {{
		rows = append(rows, fmt.Sprintf("%02d:%s", len(groups.M[key]), key))
	}}
	sort.Sort(sort.Reverse(sort.StringSlice(rows)))
	return {I.call("Take")}(rows, {n})
}}
"""
        new = f"""
func {f}(items []model.Item) []string {{
	var rows []string
	for _, g := range kit.GroupBy(items, func(it model.Item) string {{ return it.{kf} }}) {{
		rows = append(rows, fmt.Sprintf("%02d:%s", len(g.Items), g.Key))
	}}
	sort.Sort(sort.Reverse(sort.StringSlice(rows)))
	return kit.First(rows, {n})
}}
"""
    else:
        old = f"""
func {f}(items []model.Item) (int, []string, int) {{
	groups := {I.call("GroupBy")}(items, func(it model.Item) string {{ return it.{kf} }})
	biggest := 0
	for _, members := range groups.M {{
		if len(members) > biggest {{
			biggest = len(members)
		}}
	}}
	return len(groups.M), groups.Keys, biggest
}}
"""
        new = f"""
func {f}(items []model.Item) (int, []string, int) {{
	groups := kit.GroupBy(items, func(it model.Item) string {{ return it.{kf} }})
	biggest := 0
	var keys []string
	for _, g := range groups {{
		keys = append(keys, g.Key)
		if len(g.Items) > biggest {{
			biggest = len(g.Items)
		}}
	}}
	return len(groups), keys, biggest
}}
"""
    both(m, old, new)
    rows = [f'{{Kind: "{rng.choice(W.KINDS[:3])}", Region: "{rng.choice(W.REGIONS[:3])}", Unit: "{rng.choice(W.UNITS[:3])}"}}' for _ in range(rng.randint(5, 9))]
    m.std.add("fmt")
    if v == "count":
        m.demos.append(f'out = append(out, fmt.Sprintf("%s = %#v", {goq(f + "(rows)")}, func() []any {{ a, b, c := {f}([]model.Item{{{", ".join(rows)}}}); return []any{{a, b, c}} }}()))')
    else:
        m.demos.append(f'out = append(out, fmt.Sprintf("%s = %#v", {goq(f + "(rows)")}, {f}([]model.Item{{{", ".join(rows)}}})))')


def sn_callbacks(m: Mod):
    rng, I = m.rng, m.I
    c = rng.choice(["sorted", "title", "money", "closure", "reduce"])
    if c == "sorted":
        f = m.fn("names")
        n = rng.randint(2, 4)
        m.std.add("sort")
        both(m, f"""
func {f}(names []string) []string {{
	sorted := append([]string(nil), names...)
	sort.Slice(sorted, func(i, j int) bool {{ return {I.call("CompareNames")}(sorted[i], sorted[j]) < 0 }})
	return {I.call("Take")}(sorted, {n})
}}
""", f"""
func {f}(names []string) []string {{
	sorted := append([]string(nil), names...)
	sort.Slice(sorted, func(i, j int) bool {{ return kit.CompareNames(sorted[i], sorted[j]) < 0 }})
	return kit.First(sorted, {n})
}}
""")
        lst = rng.sample(["delta", "Alpha", "charlie", "bravo", "echo", "Bravo", "alpha"], 6)
        m.demo(f, ["[]string{" + ", ".join(goq(x) for x in lst) + "}"])
    elif c == "title":
        f = m.fn("labels")
        h = m.fn("mapAll")
        both(m, f"""
func {h}(xs []string, fn func(string) string) []string {{
	out := make([]string, len(xs))
	for i, x := range xs {{
		out[i] = fn(x)
	}}
	return out
}}

func {f}(names []string) []string {{
	return {h}(names, {I.call("Title")})
}}
""", f"""
func {h}(xs []string, fn func(string) string) []string {{
	out := make([]string, len(xs))
	for i, x := range xs {{
		out[i] = fn(x)
	}}
	return out
}}

func {f}(names []string) []string {{
	return {h}(names, kit.TitleCase)
}}
""")
        lst = rng.sample(W.WORDS, 3) + ["  spaced   out  words "]
        m.demo(f, ["[]string{" + ", ".join(goq(x) for x in lst) + "}"])
    elif c == "money":
        f = m.fn("prices")
        both(m, f"""
func {f}(cents []int) []string {{
	out := make([]string, 0, len(cents))
	for _, c := range cents {{
		out = append(out, {I.call("FmtAmount")}(c))
	}}
	return out
}}
""", f"""
func {f}(cents []int) []string {{
	out := make([]string, 0, len(cents))
	for _, c := range cents {{
		out = append(out, kit.Money{{Cents: c, Cur: "{m.p['cur']}"}}.Text())
	}}
	return out
}}
""")
        m.demo(f, ["[]int{" + ", ".join(str(rng.randint(-500, 99999)) for _ in range(4)) + "}"])
    elif c == "closure":
        f = m.fn("padded")
        w = rng.choice([6, 8, 10])
        both(m, f"""
func {f}(texts []string) []string {{
	right := func(t string) string {{ return {I.call("PadLeft")}(t, {w}) }}
	left := func(t string) string {{ return {I.call("PadRight")}(t, {w}) }}
	var out []string
	for _, t := range texts {{
		out = append(out, right(t)+"|"+left(t))
	}}
	return out
}}
""", f"""
func {f}(texts []string) []string {{
	right := func(t string) string {{ return kit.Pad(t, {w}, kit.AlignRight) }}
	left := func(t string) string {{ return kit.Pad(t, {w}, kit.AlignLeft) }}
	var out []string
	for _, t := range texts {{
		out = append(out, right(t)+"|"+left(t))
	}}
	return out
}}
""")
        m.demo(f, ["[]string{" + ", ".join(goq(x) for x in rng.sample(m.nouns, 3)) + "}"])
    else:
        f = m.fn("capped")
        lo, hi = rng.choice([(0, 50), (-10, 40), (5, 100)])
        both(m, f"""
func {f}(deltas []int) int {{
	acc := 0
	for _, x := range deltas {{
		acc = {I.call("Clamp")}(acc+x, {lo}, {hi})
	}}
	return acc
}}
""", f"""
func {f}(deltas []int) int {{
	acc := 0
	for _, x := range deltas {{
		acc = kit.Limit(acc+x, {lo}, {hi})
	}}
	return acc
}}
""")
        m.demo(f, ["[]int{" + ", ".join(str(rng.randint(-30, 60)) for _ in range(6)) + "}"])


def sn_label(m: Mod):
    rng, I = m.rng, m.I
    f = m.fn("label")
    w = rng.choice([14, 16, 20])
    lo, hi = rng.choice([(3, 12), (1, 8)])
    m.std.add("strconv")
    both(m, f"""
func {f}(text string) string {{
	shown := {I.call("PadLeft")}({I.call("Title")}(text), {w})
	return shown + " [" + strconv.Itoa({I.call("Clamp")}(len(text), {lo}, {hi})) + "]"
}}
""", f"""
func {f}(text string) string {{
	shown := kit.Pad(kit.TitleCase(text), {w}, kit.AlignRight)
	return shown + " [" + strconv.Itoa(kit.Limit(len(text), {lo}, {hi})) + "]"
}}
""")
    m.demo(f, [f'"{rng.choice(W.WORDS)}"', '"x"', '"a rather long description of a thing"'])


SNIPPETS = [sn_line_item, sn_line_item, sn_header_const, sn_qty, sn_qty, sn_log, sn_log, sn_pick, sn_pick, sn_group, sn_callbacks, sn_callbacks, sn_label]


def common_old(p: dict) -> str:
    return '''// Package common is a layer of thin wrappers around oldkit that most of the application imports.
package common

import (
	"shop/model"
	"shop/oldkit"
)

// Groups is the result of GroupBy.
type Groups = oldkit.Groups

func FmtAmount(cents int, cur ...string) string                   { return oldkit.FmtAmount(cents, cur...) }
func ParseQty(text string) (int, string, bool)                    { return oldkit.ParseQty(text) }
func PadRight(s string, width int) string                         { return oldkit.PadRight(s, width) }
func PadLeft(s string, width int) string                          { return oldkit.PadLeft(s, width) }
func Title(s string) string                                       { return oldkit.Title(s) }
func CompareNames(a, b string) int                                { return oldkit.CompareNames(a, b) }
func Pick(m map[string]any, keys ...string) any                   { return oldkit.Pick(m, keys...) }
func Take(xs []string, n int) []string                            { return oldkit.Take(xs, n) }
func GroupBy(items []model.Item, key func(model.Item) string) Groups { return oldkit.GroupBy(items, key) }
func Log(level, msg string, kv ...any) string                     { return oldkit.Log(level, msg, kv...) }
func FlushLog() []string                                          { return oldkit.FlushLog() }
func Clamp(x, lo, hi int) int                                     { return oldkit.Clamp(x, lo, hi) }
'''


def common_new(p: dict) -> str:
    return f'''// Package common is a layer of wrappers with the historical signatures, now backed by kit.
package common

import (
	"shop/kit"
	"shop/model"
)

// Groups is the result of GroupBy: the keys in order of first appearance and the items of each key.
type Groups struct {{
	Keys []string
	M    map[string][]model.Item
}}

func FmtAmount(cents int, cur ...string) string {{
	c := "{p['cur']}"
	if len(cur) > 0 {{
		c = cur[0]
	}}
	return kit.Money{{Cents: cents, Cur: c}}.Text()
}}

func ParseQty(text string) (int, string, bool) {{
	q, err := kit.ParseQty(text)
	if err != nil {{
		return 0, "", false
	}}
	return q.Count, q.Unit, true
}}

func PadRight(s string, width int) string {{ return kit.Pad(s, width, kit.AlignLeft) }}
func PadLeft(s string, width int) string  {{ return kit.Pad(s, width, kit.AlignRight) }}
func Title(s string) string               {{ return kit.TitleCase(s) }}
func CompareNames(a, b string) int        {{ return kit.CompareNames(a, b) }}

func Pick(m map[string]any, keys ...string) any {{ return kit.Dig(m, keys, nil) }}
func Take(xs []string, n int) []string          {{ return kit.First(xs, n) }}

func GroupBy(items []model.Item, key func(model.Item) string) Groups {{
	g := Groups{{M: map[string][]model.Item{{}}}}
	for _, grp := range kit.GroupBy(items, key) {{
		g.Keys = append(g.Keys, grp.Key)
		g.M[grp.Key] = grp.Items
	}}
	return g
}}

func Log(level, msg string, kv ...any) string {{
	ctx := kit.F{{}}
	for i := 0; i+1 < len(kv); i += 2 {{
		ctx[kv[i].(string)] = kv[i+1]
	}}
	events := kit.Default()
	events.Emit(level, msg, ctx)
	return events.Last()
}}

func FlushLog() []string          {{ return kit.Default().Drain() }}
func Clamp(x, lo, hi int) int     {{ return kit.Limit(x, lo, hi) }}
'''


def build_app(rng: random.Random, p: dict) -> dict:
    names = rng.sample(W.MODULE_NAMES, p["n_modules"])
    use_common = p["common"]
    start: dict[str, str] = {}
    solution: dict[str, str] = {}
    direct = []
    styles = ["plain", "plain", "alias", "dot"] if p["shapes"] else ["plain", "plain", "alias"]
    for name in names:
        style = "common" if use_common and rng.random() < p["common_share"] else rng.choice(styles)
        m = Mod(name, style, rng, p)
        for fn in rng.sample(SNIPPETS, rng.randint(p["min_snip"], p["max_snip"])):
            fn(m)
        start[f"app/{name}/main.go"] = m.source(False)
        if style != "common":
            solution[f"app/{name}/main.go"] = m.source(True)
            direct.append(name)
    start["go.mod"] = f"module {MODULE}\n\ngo 1.21\n"
    start["oldkit/oldkit.go"] = oldkit_source(p)
    start.update(kit_files(p))
    start[".gitignore"] = "build/\n"
    if use_common:
        start["app/common/common.go"] = common_old(p)
        solution["app/common/common.go"] = common_new(p)
    return {"start": start, "solution": solution, "modules": names, "direct": direct}
