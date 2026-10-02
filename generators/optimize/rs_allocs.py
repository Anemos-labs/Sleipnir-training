"""Allocation-heavy rust functions: a counting global allocator in the test binary, bars calibrated at generation time on the reference."""
from __future__ import annotations

import json
import re
from string import Template

from fx import Task, family, langs, merged, run

from ._kit import prove_opt

RS_ALL = "cargo test --offline --quiet"
RS_CORRECT = "cargo test --offline --quiet -- example behaviour"
RS_PERF = "cargo test --offline --quiet -- allocs"

ALLOC = '''use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;

struct Counting;

thread_local! {
    static COUNT: Cell<usize> = const { Cell::new(0) };
    static ON: Cell<bool> = const { Cell::new(false) };
}

fn bump() {
    ON.with(|on| {
        if on.get() {
            COUNT.with(|c| c.set(c.get() + 1));
        }
    });
}

unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        bump();
        System.alloc(l)
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        System.dealloc(p, l)
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        bump();
        System.realloc(p, l, n)
    }
}

#[global_allocator]
static A: Counting = Counting;

fn allocs<T>(f: impl FnOnce() -> T) -> (T, usize) {
    COUNT.with(|c| c.set(0));
    ON.with(|o| o.set(true));
    let r = f();
    ON.with(|o| o.set(false));
    (r, COUNT.with(|c| c.get()))
}

struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        self.0 >> 33
    }
    fn below(&mut self, n: u64) -> u64 {
        self.next() % n
    }
}
'''

# shapes: arg = Rust parameter list text, call args come from `gen` (Rust code returning a tuple named `input`)
SHAPES = {
    "format_loop": dict(
        d=1, res="String", doc="Joins the {noun} into one comma separated line.", sig="items: &[String]",
        naive='''pub fn $f(items: &[String]) -> String {
    let mut out = String::new();
    for (i, item) in items.iter().enumerate() {
        if i > 0 {
            out = format!("{},{}", out, item);
        } else {
            out = item.clone();
        }
    }
    out
}
''', fast='''pub fn $f(items: &[String]) -> String {
    let total: usize = items.iter().map(|s| s.len() + 1).sum();
    let mut out = String::with_capacity(total);
    for (i, item) in items.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        out.push_str(item);
    }
    out
}
''', gen='''fn small_input(r: &mut Rng) -> Vec<String> {
    let n = r.below(8) as usize;
    (0..n).map(|_| format!("it{}", r.below(1000))).collect()
}
fn big_input(r: &mut Rng) -> Vec<String> {
    (0..200).map(|_| format!("it{}", r.below(1000))).collect()
}
''', arg_ty="Vec<String>", call="$f(&input)", samples=['vec!["a".to_string(), "b".to_string()]', 'Vec::<String>::new()', 'vec!["solo".to_string()]'],
        vocab=[("join_tags", "tags", "tagging"), ("csv_line", "cells", "export"), ("route_string", "stops", "routes")]),
    "capacity": dict(
        d=1, res="Vec<u32>", doc="Returns the first n {noun} values.", sig="n: usize",
        naive='''pub fn $f(n: usize) -> Vec<u32> {
    let mut out = Vec::new();
    for i in 0..n as u32 {
        out.push(i * i % 97);
    }
    out
}
''', fast='''pub fn $f(n: usize) -> Vec<u32> {
    let mut out = Vec::with_capacity(n);
    for i in 0..n as u32 {
        out.push(i * i % 97);
    }
    out
}
''', gen='''fn small_input(r: &mut Rng) -> usize {
    r.below(30) as usize
}
fn big_input(_r: &mut Rng) -> usize {
    4000
}
''', arg_ty="usize", call="$f(*input)", sample_call="$f({0})", samples=["5", "0", "12"], vocab=[("offsets", "offset", "offsets"), ("weights", "weight", "weights")]),
    "clone_rows": dict(
        d=2, res="u32", doc="Adds up all {noun} cells.", sig="rows: &Vec<Vec<u32>>",
        naive='''pub fn $f(rows: &Vec<Vec<u32>>) -> u32 {
    let mut total = 0;
    for row in rows.clone() {
        for cell in row.clone() {
            total += cell;
        }
    }
    total
}
''', fast='''pub fn $f(rows: &Vec<Vec<u32>>) -> u32 {
    rows.iter().flatten().sum()
}
''', gen='''fn small_input(r: &mut Rng) -> Vec<Vec<u32>> {
    (0..r.below(5)).map(|_| (0..r.below(5)).map(|_| r.below(100) as u32).collect()).collect()
}
fn big_input(r: &mut Rng) -> Vec<Vec<u32>> {
    (0..100).map(|_| (0..20).map(|_| r.below(100) as u32).collect()).collect()
}
''', arg_ty="Vec<Vec<u32>>", call="$f(&input)", samples=["vec![vec![1, 2], vec![3]]", "vec![]", "vec![vec![]]"],
        vocab=[("grid_total", "grid", "grids"), ("sheet_sum", "spreadsheet", "sheets")]),
    "collect_chain": dict(
        d=2, res="usize", doc="Counts the {noun} whose square is even.", sig="values: &[u32]",
        naive='''pub fn $f(values: &[u32]) -> usize {
    let squares: Vec<u64> = values.iter().map(|&v| v as u64 * v as u64).collect();
    let evens: Vec<&u64> = squares.iter().filter(|s| **s % 2 == 0).collect();
    evens.len()
}
''', fast='''pub fn $f(values: &[u32]) -> usize {
    values.iter().filter(|&&v| (v as u64 * v as u64) % 2 == 0).count()
}
''', gen='''fn small_input(r: &mut Rng) -> Vec<u32> {
    (0..r.below(20)).map(|_| r.below(1000) as u32).collect()
}
fn big_input(r: &mut Rng) -> Vec<u32> {
    (0..5000).map(|_| r.below(100000) as u32).collect()
}
''', arg_ty="Vec<u32>", call="$f(&input)", samples=["vec![1, 2, 3, 4]", "vec![]", "vec![7]"], vocab=[("count_even_squares", "readings", "readings"), ("even_square_tally", "samples", "samples")]),
    "eq_ignore_case": dict(
        d=1, res="bool", doc="Compares two {noun} ignoring ASCII case.", sig="a: &str, b: &str",
        naive='''pub fn $f(a: &str, b: &str) -> bool {
    a.to_lowercase() == b.to_lowercase()
}
''', fast='''pub fn $f(a: &str, b: &str) -> bool {
    a.eq_ignore_ascii_case(b)
}
''', gen='''fn small_input(r: &mut Rng) -> (String, String) {
    let words = ["Harbour", "HARBOUR", "harbour", "Kiln", "kiln", "KILN", "Tide", "tide"];
    (words[r.below(8) as usize].to_string(), words[r.below(8) as usize].to_string())
}
fn big_input(_r: &mut Rng) -> (String, String) {
    ("HARBOUR-MASTER-OFFICE".to_string(), "harbour-master-office".to_string())
}
''', arg_ty="(String, String)", call="$f(&input.0, &input.1)", samples=['("Kiln".to_string(), "kiln".to_string())', '("a".to_string(), "b".to_string())'], sample_call="$f(&{0}.0, &{0}.1)",
        vocab=[("same_name", "names", "names"), ("same_command", "commands", "cli")]),
    "split_nth": dict(
        d=1, res="usize", doc="Returns the length of the third column of a {noun} line (0 when there is none).", sig="line: &str",
        naive='''pub fn $f(line: &str) -> usize {
    let parts: Vec<&str> = line.split(',').collect();
    if parts.len() > 2 {
        parts[2].len()
    } else {
        0
    }
}
''', fast='''pub fn $f(line: &str) -> usize {
    line.split(',').nth(2).map_or(0, |s| s.len())
}
''', gen='''fn small_input(r: &mut Rng) -> String {
    let n = r.below(6);
    (0..n).map(|i| format!("c{}{}", i, r.below(10))).collect::<Vec<_>>().join(",")
}
fn big_input(_r: &mut Rng) -> String {
    "alpha,beta,gamma,delta,epsilon,zeta,eta,theta".to_string()
}
''', arg_ty="String", call="$f(&input)", samples=['"a,bb,ccc,d".to_string()', '"a,b".to_string()', '"".to_string()'],
        vocab=[("third_field_len", "CSV", "csvtools"), ("sku_column_len", "inventory", "stockfeed")]),
    "key_to_string": dict(
        d=2, res="u32", doc="Sums the stock of the given {noun}.", sig="stock: &HashMap<String, u32>, keys: &[String]",
        naive='''use std::collections::HashMap;

pub fn $f(stock: &HashMap<String, u32>, keys: &[String]) -> u32 {
    let mut total = 0;
    for key in keys {
        total += stock.get(&key.to_string()).copied().unwrap_or(0);
    }
    total
}
''', fast='''use std::collections::HashMap;

pub fn $f(stock: &HashMap<String, u32>, keys: &[String]) -> u32 {
    keys.iter().map(|key| stock.get(key).copied().unwrap_or(0)).sum()
}
''', gen='''use std::collections::HashMap;

fn small_input(r: &mut Rng) -> (HashMap<String, u32>, Vec<String>) {
    let stock: HashMap<String, u32> = (0..r.below(8)).map(|i| (format!("k{}", i), r.below(50) as u32)).collect();
    let keys = (0..r.below(10)).map(|_| format!("k{}", r.below(10))).collect();
    (stock, keys)
}
fn big_input(r: &mut Rng) -> (HashMap<String, u32>, Vec<String>) {
    let stock: HashMap<String, u32> = (0..50).map(|i| (format!("k{}", i), r.below(50) as u32)).collect();
    let keys = (0..300).map(|_| format!("k{}", r.below(60))).collect();
    (stock, keys)
}
''', arg_ty="(HashMap<String, u32>, Vec<String>)", call="$f(&input.0, &input.1)", sample_call="$f(&{0}.0, &{0}.1)",
        samples=['([("a".to_string(), 3), ("b".to_string(), 4)].into_iter().collect::<std::collections::HashMap<String, u32>>(), vec!["a".to_string(), "z".to_string(), "b".to_string()])'],
        vocab=[("total_stock", "SKUs", "warehouse"), ("sum_quotas", "accounts", "quotas")], test_use="use std::collections::HashMap;"),
    "hashmap_cap": dict(
        d=2, res="usize", doc="Returns how many distinct {noun} there are.", sig="items: &[u32]",
        naive='''use std::collections::HashMap;

pub fn $f(items: &[u32]) -> usize {
    let mut seen: HashMap<u32, u32> = HashMap::new();
    for &i in items {
        *seen.entry(i).or_insert(0) += 1;
    }
    seen.len()
}
''', fast='''use std::collections::HashMap;

pub fn $f(items: &[u32]) -> usize {
    let mut seen: HashMap<u32, u32> = HashMap::with_capacity(items.len());
    for &i in items {
        *seen.entry(i).or_insert(0) += 1;
    }
    seen.len()
}
''', gen='''fn small_input(r: &mut Rng) -> Vec<u32> {
    (0..r.below(20)).map(|_| r.below(10) as u32).collect()
}
fn big_input(r: &mut Rng) -> Vec<u32> {
    (0..4000).map(|i| (i as u64 * 2654435761 % 4000) as u32 + r.below(2) as u32).collect()
}
''', arg_ty="Vec<u32>", call="$f(&input)", samples=["vec![1, 2, 2, 3]", "vec![]", "vec![5, 5, 5]"], vocab=[("distinct_visitors", "visitors", "visitors"), ("distinct_codes", "codes", "codes")]),
    "join_ints": dict(
        d=2, res="String", doc="Formats the {noun} as a comma separated list.", sig="vals: &[i64]",
        naive='''pub fn $f(vals: &[i64]) -> String {
    let parts: Vec<String> = vals.iter().map(|v| v.to_string()).collect();
    parts.join(",")
}
''', fast='''use std::fmt::Write;

pub fn $f(vals: &[i64]) -> String {
    let mut out = String::with_capacity(vals.len() * 7);
    for (i, v) in vals.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        write!(out, "{}", v).unwrap();
    }
    out
}
''', gen='''fn small_input(r: &mut Rng) -> Vec<i64> {
    (0..r.below(10)).map(|_| r.below(200000) as i64 - 1000).collect()
}
fn big_input(r: &mut Rng) -> Vec<i64> {
    (0..300).map(|_| r.below(200000) as i64 - 1000).collect()
}
''', arg_ty="Vec<i64>", call="$f(&input)", samples=["vec![1, -2, 300]", "vec![]", "vec![7]"], vocab=[("format_readings", "readings", "readings"), ("id_list", "ids", "idlist")]),
}

PROMPTS = [
    "`{f}` in `src/lib.rs` is on the hot path of the {noun} service and the allocator shows up at the top of every profile. {doc} Cut its allocations without changing what it returns; "
    "the behaviour tests stay as they are.",
    "perf: `{f}` allocates far more than it should. {doc} Make it allocation-light (CI counts allocations with a counting allocator). Same results.",
    "heaptrack says `{f}` (src/lib.rs) churns through short-lived heap allocations. {doc} Rewrite it so it allocates (almost) nothing beyond the result. Keep the signature and the output.",
    "Please reduce the heap allocations of `{f}`. {doc} A test in CI counts allocations per call, and the behaviour must remain identical.",
]


def _lib(shape_src, f, doc, extra_imports=""):
    return f"//! Small helpers on a hot path.\n\n{shape_src}"


def _spec(sp, crate, f, naive_fn):
    naive_ref = naive_fn.replace(f"pub fn {f}(", "fn reference(")
    gen = sp["gen"]
    use_lines = {ln for text in (naive_ref, gen, sp.get("test_use", "")) for ln in text.splitlines() if ln.startswith("use ")}
    naive_ref = "\n".join(ln for ln in naive_ref.splitlines() if not ln.startswith("use "))
    gen = "\n".join(ln for ln in gen.splitlines() if not ln.startswith("use "))
    uses = "\n".join(sorted(use_lines))
    call = sp["call"].replace("$f", f)
    ref_call = call.replace(f, "reference")
    res = sp["res"]
    return (f"use {crate}::*;\n{uses}\n\n{ALLOC}\n{naive_ref}\n{gen}\n"
            f"fn call_it(input: &{sp['arg_ty']}) -> {res} {{ {call} }}\n"
            f"fn ref_it(input: &{sp['arg_ty']}) -> {res} {{ {ref_call} }}\n")


def _tests(sp, crate, f, naive_fn, limit, seed, measure=False):
    head = _spec(sp, crate, f, naive_fn)
    behaviour = (f"\n#[test]\nfn behaviour_matches_reference() {{\n    let mut r = Rng({seed});\n    for _ in 0..300 {{\n        let input = small_input(&mut r);\n"
                 "        assert_eq!(call_it(&input), ref_it(&input), \"input {:?}\", input);\n    }\n}\n")
    if measure:
        perf = (f"\n#[test]\nfn allocs_measure() {{\n    let mut r = Rng({seed});\n    let input = big_input(&mut r);\n    let (_, n) = allocs(|| call_it(&input));\n    println!(\"MEASURE|{{}}\", n);\n}}\n")
    else:
        perf = (f"\n#[test]\nfn allocs_stay_low() {{\n    let mut r = Rng({seed});\n    let input = big_input(&mut r);\n    let (got, n) = allocs(|| call_it(&input));\n"
                f"    assert!(n <= {limit}, \"PERF: {{}} allocations per call (limit {limit}): the function allocates much more than it needs to\", n);\n"
                "    assert_eq!(got, ref_it(&input));\n}\n")
    return head + behaviour + perf


def _measure(files, crate, sp, f, naive_fn, seed):
    t = _tests(sp, crate, f, naive_fn, 0, seed, measure=True)
    r = run(merged(files, {"tests/measure.rs": t}), "cargo test --offline --quiet --test measure -- --nocapture", timeout=240)
    m = re.search(r"MEASURE\|(\d+)", r.out)
    if not r.ok or not m:
        raise RuntimeError("measure failed:\n" + r.out[-2500:])
    return int(m.group(1))


def _visible(sp, crate, f, files):
    samples = sp["samples"]
    call = sp.get("sample_call", "$f(&{0})")
    lines = []
    for i, s in enumerate(samples):
        expr = call.replace("$f", f).replace("{0}", f"s{i}")
        lines.append(f"    let s{i} = {s};\n    println!(\"RESULT|{i}|{{:?}}\", {expr});")
    text = f"use {crate}::*;\n{sp.get('test_use', '')}\n\n#[test]\nfn print_results() {{\n" + "\n".join(lines) + "\n}\n"
    r = run(merged(files, {"tests/print.rs": text}), "cargo test --offline --quiet --test print -- --nocapture", timeout=240)
    got = {}
    for ln in r.out.splitlines():
        m = re.match(r"RESULT\|(\d+)\|(.*)$", ln)
        if m:
            got[int(m.group(1))] = m.group(2)
    if not r.ok or len(got) != len(samples):
        raise RuntimeError("visible run failed:\n" + r.out[-2500:])
    body = f"use {crate}::*;\n{sp.get('test_use', '')}\n\n"
    for i, s in enumerate(samples):
        lit = got[i]
        if sp["res"].startswith("Vec"):
            lit = "vec!" + lit
        expr = call.replace("$f", f).replace("{0}", f"s{i}")
        body += f"#[test]\nfn example_{i + 1}() {{\n    let s{i} = {s};\n    assert_eq!({expr}, {lit});\n}}\n\n"
    return body


@family("optimize-rs-allocs", category="optimize", lang="rust", kind="feature", n=12,
        summary="allocation-heavy rust (format! in loops, no capacity, clones, intermediate collects, to_string lookups): a counting global allocator with a bar calibrated on the reference")
def gen(rng, n):
    order = list(SHAPES) * 2
    rng.shuffle(order)
    used = set()
    for i in range(n):
        shape = order[i]
        sp = SHAPES[shape]
        vs = [v for v in sp["vocab"] if (shape, v[0]) not in used] or sp["vocab"]
        f, noun, pkg = rng.choice(vs)
        used.add((shape, f))
        crate = pkg + "lib"
        naive = Template(sp["naive"]).substitute(f=f)
        fast = Template(sp["fast"]).substitute(f=f)
        doc = sp["doc"].format(noun=noun)
        start_lib = _lib(naive, f, doc)
        sol_lib = _lib(fast, f, doc)
        cargo = langs.cargo_toml(crate)
        base = {"Cargo.toml": cargo, "src/lib.rs": start_lib}
        sol_files = {"Cargo.toml": cargo, "src/lib.rs": sol_lib}
        seed = 40 + i
        a_naive = _measure(base, crate, sp, f, naive, seed)
        a_fast = _measure(sol_files, crate, sp, f, naive, seed)
        limit = a_fast if a_fast == 0 else a_fast + max(1, a_fast // 2)
        if a_naive < 3 * limit + 1:
            raise RuntimeError(f"{shape}/{f}: naive allocs {a_naive} too close to limit {limit} (fast {a_fast})")
        vis = _visible(sp, crate, f, base)
        hidden = {"tests/spec.rs": _tests(sp, crate, f, naive, limit, seed)}
        readme = f"# {crate}\n\n## `{f}`\n\n{doc}\n\nIt is called for every request of the {noun} service, so it must not allocate more than necessary.\n"
        start = {**base, "tests/example.rs": vis, "README.md": readme}
        solution = {"src/lib.rs": sol_lib}
        prove_opt(f"{shape}/{f}", start, hidden, solution, RS_CORRECT, RS_PERF, RS_ALL, timeout=300)
        prompt = rng.choice(PROMPTS).format(f=f, doc=doc, noun=noun)
        yield Task(slug=f"{i + 1:02d}-{shape}-{f}", prompt=prompt, difficulty=sp["d"], start=start, hidden=hidden, solution=solution, verify=RS_ALL, timeout_s=300,
                   tags=["allocations", "counting-allocator", "rust"], notes={"shape": shape, "naive_allocs": a_naive, "fast_allocs": a_fast, "limit": limit})
