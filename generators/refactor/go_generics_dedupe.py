"""Per-type copies of the same Go helper become generic functions (type constraints stated in the prompt); the old names stay as thin wrappers."""
from __future__ import annotations

import json
import re

from fx import Task, dd, family, langs, merged, run

from . import _kit
from ._kit import clike_lib, prove, tabify

GO_VERIFY = "go test -count=1 ./... && python3 checks/structure.py"
GO_BEHAVIOUR = "go test -count=1 ./..."
GO_STRUCT = "python3 checks/structure.py"

TYPES = {"Ints": "int", "Floats": "float64", "Strings": "string"}

# op -> (go template using $S suffix and $T type, allowed type suffixes, generic text, wrapper text)
OPS = {
    "Sum": dict(types=["Ints", "Floats"], constraint="Number",
                copy='''// Sum$S adds up the values.
func Sum$S(xs []$T) $T {
    var total $T
    for _, x := range xs {
        total += x
    }
    return total
}
''', generic='''// Sum adds up the values.
func Sum[T Number](xs []T) T {
    var total T
    for _, x := range xs {
        total += x
    }
    return total
}
''', wrap="func Sum$S(xs []$T) $T { return Sum(xs) }", sig="Sum[T Number](xs []T) T"),
    "Max": dict(types=["Ints", "Floats", "Strings"], constraint="Ordered",
                copy='''// Max$S returns the largest value and false for an empty slice.
func Max$S(xs []$T) ($T, bool) {
    var best $T
    if len(xs) == 0 {
        return best, false
    }
    best = xs[0]
    for _, x := range xs[1:] {
        if x > best {
            best = x
        }
    }
    return best, true
}
''', generic='''// Max returns the largest value and false for an empty slice.
func Max[T Ordered](xs []T) (T, bool) {
    var best T
    if len(xs) == 0 {
        return best, false
    }
    best = xs[0]
    for _, x := range xs[1:] {
        if x > best {
            best = x
        }
    }
    return best, true
}
''', wrap="func Max$S(xs []$T) ($T, bool) { return Max(xs) }", sig="Max[T Ordered](xs []T) (T, bool)"),
    "Contains": dict(types=["Ints", "Strings"], constraint="comparable",
                     copy='''// Contains$S reports whether v occurs in xs.
func Contains$S(xs []$T, v $T) bool {
    for _, x := range xs {
        if x == v {
            return true
        }
    }
    return false
}
''', generic='''// Contains reports whether v occurs in xs.
func Contains[T comparable](xs []T, v T) bool {
    for _, x := range xs {
        if x == v {
            return true
        }
    }
    return false
}
''', wrap="func Contains$S(xs []$T, v $T) bool { return Contains(xs, v) }", sig="Contains[T comparable](xs []T, v T) bool"),
    "IndexOf": dict(types=["Ints", "Strings"], constraint="comparable",
                    copy='''// IndexOf$S returns the position of the first v in xs, or -1.
func IndexOf$S(xs []$T, v $T) int {
    for i, x := range xs {
        if x == v {
            return i
        }
    }
    return -1
}
''', generic='''// IndexOf returns the position of the first v in xs, or -1.
func IndexOf[T comparable](xs []T, v T) int {
    for i, x := range xs {
        if x == v {
            return i
        }
    }
    return -1
}
''', wrap="func IndexOf$S(xs []$T, v $T) int { return IndexOf(xs, v) }", sig="IndexOf[T comparable](xs []T, v T) int"),
    "Reverse": dict(types=["Ints", "Floats", "Strings"], constraint="any",
                    copy='''// Reverse$S returns a reversed copy.
func Reverse$S(xs []$T) []$T {
    out := make([]$T, len(xs))
    for i, x := range xs {
        out[len(xs)-1-i] = x
    }
    return out
}
''', generic='''// Reverse returns a reversed copy.
func Reverse[T any](xs []T) []T {
    out := make([]T, len(xs))
    for i, x := range xs {
        out[len(xs)-1-i] = x
    }
    return out
}
''', wrap="func Reverse$S(xs []$T) []$T { return Reverse(xs) }", sig="Reverse[T any](xs []T) []T"),
    "Unique": dict(types=["Ints", "Strings"], constraint="comparable",
                   copy='''// Unique$S keeps the first occurrence of every value.
func Unique$S(xs []$T) []$T {
    seen := map[$T]bool{}
    var out []$T
    for _, x := range xs {
        if !seen[x] {
            seen[x] = true
            out = append(out, x)
        }
    }
    return out
}
''', generic='''// Unique keeps the first occurrence of every value.
func Unique[T comparable](xs []T) []T {
    seen := map[T]bool{}
    var out []T
    for _, x := range xs {
        if !seen[x] {
            seen[x] = true
            out = append(out, x)
        }
    }
    return out
}
''', wrap="func Unique$S(xs []$T) []$T { return Unique(xs) }", sig="Unique[T comparable](xs []T) []T"),
    "Filter": dict(types=["Ints", "Floats", "Strings"], constraint="any",
                   copy='''// Filter$S keeps the values for which keep returns true.
func Filter$S(xs []$T, keep func($T) bool) []$T {
    var out []$T
    for _, x := range xs {
        if keep(x) {
            out = append(out, x)
        }
    }
    return out
}
''', generic='''// Filter keeps the values for which keep returns true.
func Filter[T any](xs []T, keep func(T) bool) []T {
    var out []T
    for _, x := range xs {
        if keep(x) {
            out = append(out, x)
        }
    }
    return out
}
''', wrap="func Filter$S(xs []$T, keep func($T) bool) []$T { return Filter(xs, keep) }", sig="Filter[T any](xs []T, keep func(T) bool) []T"),
}

SAMPLES = {
    "Ints": ["[]int{3, 1, 4, 1, 5}", "[]int{}", "[]int{7}", "[]int{2, 2, 9, 2}"],
    "Floats": ["[]float64{2.5, 0.5, 4}", "[]float64{}", "[]float64{1.25, 1.25}"],
    "Strings": ["[]string{\"kiln\", \"loom\", \"kiln\"}", "[]string{}", "[]string{\"a\"}"],
}
VALUES = {"Ints": ["1", "9", "4"], "Floats": ["0.5", "4", "9"], "Strings": ["\"loom\"", "\"zz\"", "\"a\""]}
KEEPS = {"Ints": "func(x int) bool { return x > 2 }", "Floats": "func(x float64) bool { return x > 1 }", "Strings": "func(x string) bool { return len(x) > 1 }"}


def py_eval(op, suf, xs, v=None):
    if op == "Sum":
        s = sum(xs)
        return s if suf == "Ints" else float(s)
    if op == "Max":
        return (max(xs), True) if xs else (None, False)
    if op == "Contains":
        return v in xs
    if op == "IndexOf":
        return xs.index(v) if v in xs else -1
    if op == "Reverse":
        return list(reversed(xs))
    if op == "Unique":
        return list(dict.fromkeys(xs))
    if op == "Filter":
        return [x for x in xs if (x > 2 if suf == "Ints" else x > 1 if suf == "Floats" else len(x) > 1)]


def lit(suf, value):
    if suf == "Strings":
        return json.dumps(value)
    if suf == "Floats":
        return repr(float(value))
    return str(value)


def slice_lit(suf, xs):
    return f"[]{TYPES[suf]}{{" + ", ".join(lit(suf, x) for x in xs) + "}"


def go_zero(suf):
    return {"Ints": "0", "Floats": "0", "Strings": '""'}[suf]


def pyval(suf, s):
    return {"Ints": int, "Floats": float, "Strings": str}[suf](s)


DATA = {
    "Ints": [[3, 1, 4, 1, 5], [], [7], [2, 2, 9, 2]],
    "Floats": [[2.5, 0.5, 4.0], [], [1.25, 1.25]],
    "Strings": [["kiln", "loom", "kiln"], [], ["a"]],
}
NEEDLES = {"Ints": [1, 9], "Floats": [0.5, 9.0], "Strings": ["loom", "zz"]}


def test_for(pkg, mod, ops_types, wrappers_only=False):
    """Go test file: old per-type names and the new generic names must agree with values computed in python."""
    lines = [f"package {pkg}_test", "", "import (", '\t"reflect"', '\t"testing"', "", f'\t"example.com/{mod}/{pkg}"', ")", "", "func eq(t *testing.T, name string, got, want any) {", "\tt.Helper()",
             "\tif !reflect.DeepEqual(got, want) && !(reflect.ValueOf(got).Kind() == reflect.Slice && reflect.ValueOf(want).Kind() == reflect.Slice && reflect.ValueOf(got).Len() == 0 && reflect.ValueOf(want).Len() == 0) {",
             '\t\tt.Errorf("%s: got %v, want %v", name, got, want)', "\t}", "}", "", "func TestPerTypeNamesStillWork(t *testing.T) {"]
    gen_lines = ["", "func TestGenericFunctions(t *testing.T) {"]
    for op, sufs in ops_types.items():
        for suf in sufs:
            for xs in DATA[suf]:
                T = TYPES[suf]
                args = slice_lit(suf, xs)
                if op in ("Contains", "IndexOf"):
                    for v in NEEDLES[suf]:
                        want = py_eval(op, suf, xs, v)
                        old = f"{pkg}.{op}{suf}({args}, {lit(suf, v)})"
                        new = f"{pkg}.{op}({args}, {lit(suf, v)})"
                        lines.append(f'\teq(t, "{op}{suf}", {old}, {want if not isinstance(want, bool) else str(want).lower()})')
                        gen_lines.append(f'\teq(t, "{op}", {new}, {want if not isinstance(want, bool) else str(want).lower()})')
                elif op == "Max":
                    want = py_eval(op, suf, xs)
                    zero = go_zero(suf)
                    val = lit(suf, want[0]) if want[1] else zero
                    for prefix, name, store in ((f"{pkg}.{op}{suf}", f"{op}{suf}", lines), (f"{pkg}.{op}", op, gen_lines)):
                        store.append(f"\t{{\n\t\tgot, ok := {prefix}({args})\n\t\teq(t, \"{name}\", []any{{got, ok}}, []any{{{T}({val}), {str(want[1]).lower()}}})\n\t}}")
                elif op == "Filter":
                    want = py_eval(op, suf, xs)
                    w = slice_lit(suf, want) if want else f"[]{T}(nil)"
                    lines.append(f'\teq(t, "{op}{suf}", {pkg}.{op}{suf}({args}, {KEEPS[suf]}), {w})')
                    gen_lines.append(f'\teq(t, "{op}", {pkg}.{op}({args}, {KEEPS[suf]}), {w})')
                elif op in ("Reverse", "Unique"):
                    want = py_eval(op, suf, xs)
                    w = slice_lit(suf, want) if want else f"[]{T}(nil)"
                    lines.append(f'\teq(t, "{op}{suf}", {pkg}.{op}{suf}({args}), {w})')
                    gen_lines.append(f'\teq(t, "{op}", {pkg}.{op}({args}), {w})')
                else:  # Sum
                    want = py_eval(op, suf, xs)
                    lines.append(f'\teq(t, "{op}{suf}", {pkg}.{op}{suf}({args}), {T}({lit(suf, want)}))')
                    gen_lines.append(f'\teq(t, "{op}", {pkg}.{op}({args}), {T}({lit(suf, want)}))')
    lines.append("}")
    gen_lines.append("}")
    return "\n".join(lines + ([] if wrappers_only else gen_lines)) + "\n"


PROMPTS = [
    "`{pkg}/{file}` has the same helper written once per element type ({names}...). That is {n} functions that differ only in the type. Replace the copies with generic functions "
    "(Go {go_ver}+): {sigs}. The constraint types `Number` (`~int | ~int64 | ~float64`) and `Ordered` (`Number | ~string`) are for you to declare. The per-type names are used by other packages, so keep them "
    "as thin wrappers around the generic versions. Behaviour must not change.",
    "dedupe `{pkg}/{file}` with generics: {sigs}. Keep the existing per-type functions ({names}...) as one-line wrappers since callers import them. Declare the `Number` and `Ordered` constraints yourself. "
    "No copy-pasted function bodies should remain.",
    "We have {n} near-identical per-type functions in `{pkg}` (e.g. {names}). Go has generics now: write `{gen_names}` as generic functions with these signatures: {sigs} (you declare the `Number` / `Ordered` "
    "constraints), and reduce the old per-type functions to wrappers so existing imports keep working.",
]


@family("refactor-go-generics-dedupe", category="refactor", lang="go", kind="refactor", n=8,
        summary="per-type copies of slice helpers become generic functions with stated signatures; the old per-type names stay as wrappers")
def gen(rng, n):
    for i in range(n):
        k = rng.choice([2, 3, 4, 5, 6])
        ops = rng.sample(list(OPS), k)
        ops.sort(key=list(OPS).index)
        chosen = {}
        for op in ops:
            avail = OPS[op]["types"]
            chosen[op] = sorted(rng.sample(avail, rng.randrange(2, len(avail) + 1)) if len(avail) > 2 else list(avail), key=["Ints", "Floats", "Strings"].index)
        pkg = rng.choice(["slicekit", "listutil", "seqtools", "batchlib", "rowtools"])
        mod = pkg + "mod"
        file = "helpers.go"
        rel = f"{pkg}/{file}"
        start_parts, sol_parts, wrappers = [], [], []
        for op, sufs in chosen.items():
            for suf in sufs:
                start_parts.append(OPS[op]["copy"].replace("$S", suf).replace("$T", TYPES[suf]))
            sol_parts.append(OPS[op]["generic"])
            for suf in sufs:
                wrappers.append(OPS[op]["wrap"].replace("$S", suf).replace("$T", TYPES[suf]))
        needs_number = "Sum" in chosen
        needs_ordered = "Max" in chosen
        constraints = ""
        if needs_number or needs_ordered:
            constraints += "// Number is any numeric type.\ntype Number interface {\n    ~int | ~int64 | ~float64\n}\n\n"
        if needs_ordered:
            constraints += "// Ordered is any type that supports < and >.\ntype Ordered interface {\n    Number | ~string\n}\n\n"
        head = f"// Package {pkg} holds small slice helpers.\npackage {pkg}\n\n"
        start_src = tabify(head + "\n".join(start_parts))
        sol_src = tabify(head + constraints + "\n".join(sol_parts) + "\n" + "\n".join(wrappers) + "\n")
        base = {"go.mod": langs.go_mod(mod), rel: start_src}
        vis_ops = {op: sufs[:1] for op, sufs in list(chosen.items())[:2]}
        vis = tabify(test_for(pkg, mod, vis_ops, wrappers_only=True))
        vis = vis.replace("func eq(", "func exEq(").replace("eq(t,", "exEq(t,").replace("TestPerTypeNamesStillWork", "TestExamples")
        hid = tabify(test_for(pkg, mod, chosen))
        gen_names = ", ".join(f"`{op}`" for op in chosen)
        sigs = "; ".join(f"`{OPS[op]['sig']}`" for op in chosen)
        names = ", ".join(f"`{op}{chosen[op][0]}`" for op in list(chosen)[:3])
        n_funcs = sum(len(v) for v in chosen.values())
        struct = dd(f'''
        import re

        import clike as C

        FILES = C.files([".go"], dirs=[{json.dumps(pkg)}])
        GENERIC = {json.dumps(list(chosen))}
        OLD = {json.dumps([op + s for op, sufs in chosen.items() for s in sufs])}
        problems = []
        fns = C.all_functions(FILES, "go")
        text = "\\n".join(C.clean(C.read(f), "go") for f in FILES)
        for g in GENERIC:
            if not re.search(r"func\\s+" + g + r"\\s*\\[", text):
                problems.append("missing the generic function " + g)
        for o in OLD:
            if not re.search(r"func\\s+" + o + r"\\s*\\(", text):
                problems.append("the per-type function " + o + " must stay available")
        dup = C.duplicate_functions(FILES, "go", min_tokens=70)
        if dup:
            problems.append("copy-pasted function bodies remain: %s" % dup)
        big = [f for f in fns if f.loc > 14]
        if big:
            problems.append("per-type function bodies are still long: %s" % big)
        C.report(problems)
        ''')
        hidden = {f"{pkg}/behaviour_test.go": hid, "checks/structure.py": struct, **clike_lib()}
        start = {**base, f"{pkg}/example_test.go": vis}
        solution = {rel: sol_src}
        # the hidden test also calls the new generic names, so it cannot compile on the start; the old-names part must pass there
        old_only = {f"{pkg}/behaviour_test.go": tabify(test_for(pkg, mod, chosen, wrappers_only=True))}
        r0 = run(merged(start, old_only), GO_BEHAVIOUR, timeout=120)
        if not r0.ok:
            raise RuntimeError(f"generics-{i}: the old-names test fails on the start:\n{r0.out[-1500:]}")
        prove(f"generics-{i}", start, hidden, solution, GO_BEHAVIOUR, GO_STRUCT, GO_VERIFY, behaviour_on_start=False)
        prompt = rng.choice(PROMPTS).format(pkg=pkg, file=file, names=names, n=n_funcs, sigs=sigs, gen_names=gen_names, go_ver="1.18")
        d = 2 if k <= 3 else 3 if k <= 5 else 4
        yield Task(slug=f"{i + 1:02d}-{k}ops-{n_funcs}copies", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution, verify=GO_VERIFY,
                   tags=["generics", "deduplication", "type-parameters"], notes={"ops": chosen})
