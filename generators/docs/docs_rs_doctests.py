"""Rust doc comments with doctests: crate docs, `///` on every pub item, runnable examples with assertions, `# Errors` for fallible functions; code untouched."""
from __future__ import annotations

import json
import re

from fx import Task, dd, family, langs

from ._kit import prove_docs

CMD = "cargo test --offline --quiet && python3 checks/rsdoc.py"

MODULES = [
    dict(key="seedbank", crate="seedbank", summary="Stock keeping for a community seed bank.",
         src='''use std::collections::HashMap;

@DOC:parse_sku@
pub fn parse_sku(code: &str) -> Result<(String, u32), String> {
    let (prefix, rest) = code.split_once('-').ok_or_else(|| format!("bad sku: {}", code))?;
    if !["VEG", "HRB", "FLW"].contains(&prefix) {
        return Err(format!("bad sku: {}", code));
    }
    let n: u32 = rest.parse().map_err(|_| format!("bad sku: {}", code))?;
    Ok((prefix.to_string(), n))
}

@DOC:add_lot@
pub fn add_lot(stock: &mut HashMap<String, u32>, sku: &str, qty: u32) -> Result<u32, String> {
    if qty == 0 {
        return Err("quantity must be positive".to_string());
    }
    parse_sku(sku)?;
    let entry = stock.entry(sku.to_string()).or_insert(0);
    *entry += qty;
    Ok(*entry)
}

@DOC:low_stock@
pub fn low_stock(stock: &HashMap<String, u32>, threshold: u32) -> Vec<String> {
    let mut out: Vec<String> = stock.iter().filter(|(_, &q)| q < threshold).map(|(k, _)| k.clone()).collect();
    out.sort();
    out
}

@DOC:format_label@
pub fn format_label(sku: &str, qty: u32) -> Result<String, String> {
    let (prefix, number) = parse_sku(sku)?;
    Ok(format!("{} #{:04} x{}", prefix, number, qty))
}
''',
         docs={"parse_sku": ("Split a SKU such as `VEG-0042` into its prefix and number.", True,
                             ['assert_eq!(parse_sku("VEG-0042"), Ok(("VEG".to_string(), 42)));', 'assert!(parse_sku("XYZ-1").is_err());'], "if the prefix is unknown or the number is not a number"),
               "add_lot": ("Add packets of a SKU to the stock and return the new count.", True,
                           ['let mut stock = HashMap::new();', 'assert_eq!(add_lot(&mut stock, "VEG-1", 3), Ok(3));', 'assert_eq!(add_lot(&mut stock, "VEG-1", 2), Ok(5));', 'assert!(add_lot(&mut stock, "VEG-1", 0).is_err());'],
                           "if the quantity is zero or the SKU is malformed"),
               "low_stock": ("List, in alphabetical order, the SKUs with fewer packets than the threshold.", False,
                             ['let mut stock = HashMap::new();', 'stock.insert("VEG-1".to_string(), 2);', 'stock.insert("HRB-4".to_string(), 9);', 'assert_eq!(low_stock(&stock, 5), vec!["VEG-1".to_string()]);'], ""),
               "format_label": ("Format the text printed on a packet label.", True, ['assert_eq!(format_label("VEG-42", 3).unwrap(), "VEG #0042 x3");', 'assert!(format_label("nope", 1).is_err());'], "if the SKU is malformed")},
         uses={"parse_sku": "use seedbank::parse_sku;", "add_lot": "use seedbank::add_lot;\nuse std::collections::HashMap;", "low_stock": "use seedbank::low_stock;\nuse std::collections::HashMap;",
               "format_label": "use seedbank::format_label;"}),
    dict(key="ferry", crate="ferry", summary="Timetable helpers for the island ferry.",
         src='''@DOC:parse_time@
pub fn parse_time(text: &str) -> Option<u32> {
    let (h, m) = text.split_once(':')?;
    let (h, m): (u32, u32) = (h.parse().ok()?, m.parse().ok()?);
    if h > 23 || m > 59 {
        return None;
    }
    Some(h * 60 + m)
}

@DOC:format_time@
pub fn format_time(minutes: u32) -> String {
    let m = minutes % 1440;
    format!("{:02}:{:02}", m / 60, m % 60)
}

@DOC:next_departure@
pub fn next_departure(times: &[u32], now: u32) -> Option<u32> {
    let mut sorted = times.to_vec();
    sorted.sort_unstable();
    sorted.iter().copied().find(|&t| t >= now).or_else(|| sorted.first().map(|&t| t + 1440))
}

@DOC:overlap@
pub fn overlap(a: (u32, u32), b: (u32, u32)) -> u32 {
    let start = a.0.max(b.0);
    let end = a.1.min(b.1);
    end.saturating_sub(start)
}
''',
         docs={"parse_time": ("Convert `HH:MM` text to minutes after midnight, or `None` if it is malformed or out of range.", False,
                             ['assert_eq!(parse_time("07:45"), Some(465));', 'assert_eq!(parse_time("24:00"), None);', 'assert_eq!(parse_time("7.45"), None);'], ""),
               "format_time": ("Convert minutes after midnight to `HH:MM`, wrapping past midnight.", False, ['assert_eq!(format_time(465), "07:45");', 'assert_eq!(format_time(1500), "01:00");'], ""),
               "next_departure": ("Find the next sailing at or after `now`; tomorrow's first sailing (plus 1440 minutes) if none is left, `None` without sailings.", False,
                                  ['assert_eq!(next_departure(&[420, 600, 900], 500), Some(600));', 'assert_eq!(next_departure(&[420, 600], 700), Some(1860));', 'assert_eq!(next_departure(&[], 10), None);'], ""),
               "overlap": ("Minutes two `(start, end)` windows share; 0 if they are disjoint.", False, ['assert_eq!(overlap((60, 120), (90, 200)), 30);', 'assert_eq!(overlap((0, 10), (20, 30)), 0);'], "")},
         uses={k: f"use ferry::{k};" for k in ("parse_time", "format_time", "next_departure", "overlap")}),
    dict(key="tidelab", crate="tidelab", summary="Unit conversions and binning for the tide laboratory.",
         src='''@DOC:to_metres@
pub fn to_metres(value: f64, unit: &str) -> Result<f64, String> {
    match unit {
        "m" => Ok(value),
        "cm" => Ok(value / 100.0),
        "ft" => Ok((value / 3.28084 * 10000.0).round() / 10000.0),
        _ => Err(format!("unknown unit: {}", unit)),
    }
}

@DOC:clamp@
pub fn clamp(value: i32, low: i32, high: i32) -> i32 {
    value.max(low).min(high)
}

@DOC:bucketize@
pub fn bucketize(values: &[i32], edges: &[i32]) -> Vec<usize> {
    let mut counts = vec![0; edges.len() + 1];
    for &v in values {
        let i = edges.iter().take_while(|&&e| v >= e).count();
        counts[i] += 1;
    }
    counts
}
''',
         docs={"to_metres": ("Convert a length to metres.", True, ['assert_eq!(to_metres(250.0, "cm"), Ok(2.5));', 'assert_eq!(to_metres(2.0, "m"), Ok(2.0));', 'assert!(to_metres(1.0, "yd").is_err());'], "if the unit is not `m`, `cm` or `ft`"),
               "clamp": ("Limit a value to the closed range `[low, high]`.", False, ['assert_eq!(clamp(5, 0, 3), 3);', 'assert_eq!(clamp(-2, 0, 3), 0);', 'assert_eq!(clamp(2, 0, 3), 2);'], ""),
               "bucketize": ("Count values per bucket; the result has one more entry than there are edges, and a value equal to an edge goes to the upper bucket.", False,
                             ['assert_eq!(bucketize(&[1, 5, 9, 10, 25], &[5, 10]), vec![1, 2, 2]);', 'assert_eq!(bucketize(&[], &[1]), vec![0, 0]);'], "")},
         uses={k: f"use tidelab::{k};" for k in ("to_metres", "clamp", "bucketize")}),
]

CHECK = r'''import glob
import re

import clike as C

ORIGINAL = __ORIGINAL__
FUNCS = __FUNCS__
FALLIBLE = __FALLIBLE__
problems = []
src = C.read("src/lib.rs")
if re.sub(r"\s+", "", C.clean(src, "rust")) != re.sub(r"\s+", "", C.clean(ORIGINAL, "rust")):
    problems.append("the code changed: only comments may be added")
lines = src.split("\n")
if not any(ln.startswith("//!") for ln in lines):
    problems.append("the crate needs `//!` documentation at the top of src/lib.rs")
for name in FUNCS:
    idx = next((i for i, ln in enumerate(lines) if re.match(r"\s*pub fn " + name + r"\b", ln)), None)
    if idx is None:
        problems.append(name + ": not found")
        continue
    doc = []
    j = idx - 1
    while j >= 0 and lines[j].lstrip().startswith("///"):
        doc.insert(0, lines[j].lstrip()[3:])
        j -= 1
    text = "\n".join(doc)
    if not text.strip():
        problems.append(name + ": no `///` documentation")
        continue
    blocks = re.findall(r"```[a-z]*\n(.*?)```", text, re.S)
    if not any("assert" in b for b in blocks):
        problems.append(name + ": the documentation needs an example in a code block that asserts something")
    if name in FALLIBLE and not re.search(r"^\s?# Errors", text, re.M):
        problems.append(name + ": functions returning Result need an `# Errors` section")
C.report(problems)
'''


def compose(mod, documented):
    text = mod["src"]

    def rep(m):
        name = m.group(1)
        if not documented:
            return ""
        summary, fallible, body, errors = mod["docs"][name]
        lines = [summary, ""]
        if fallible:
            lines += ["# Errors", "", f"Returns an error {errors}.", ""]
        lines += ["# Examples", "", "```"] + mod["uses"][name].split("\n") + body + ["```"]
        return "".join(f"/// {ln}\n" if ln else "///\n" for ln in lines)
    text = re.sub(r"@DOC:(\w+)@\n", rep, text)
    if documented:
        text = f"//! {mod['summary']}\n\n" + text
    return text


PROMPTS = [
    "`src/lib.rs` has no documentation. Add crate-level docs (`//!`), and a `///` doc comment for every public function with a summary line and an `# Examples` section containing a runnable "
    "doctest that asserts the behaviour (use the crate name, e.g. `use {crate_}::...;`). Functions that return `Result` also need an `# Errors` section. The code must not change and `cargo test` (which runs "
    "doctests) has to pass.",
    "rustdoc for the `{crate_}` crate: `//!` crate docs, `///` on every `pub fn` with an `# Examples` doctest that asserts something real, and `# Errors` for the fallible ones. Only comments change; the doctests must pass.",
    "docs.rs would show nothing useful for `{crate_}`. Please write the documentation: crate docs, a doc comment on each public function, doctests that call them with `assert_eq!` / `assert!`, and `# Errors` sections "
    "where a function returns `Err`. No code changes, and everything has to pass under `cargo test --offline`.",
]


@family("docs-rs-doctests", category="docs", lang="rust", kind="feature", n=4,
        summary="rustdoc: crate docs, /// on every pub fn with asserting doctests and # Errors sections; code unchanged, doctests run by cargo test")
def gen(rng, n):
    mods = list(MODULES) + [rng.choice(MODULES)]
    rng.shuffle(mods)
    for i in range(n):
        mod = mods[i]
        crate = mod["crate"]
        original = compose(mod, False)
        solved = compose(mod, True)
        names = list(mod["docs"])
        fallible = [k for k, v in mod["docs"].items() if v[1]]
        vis = (f"use {crate}::*;\n\n#[test]\nfn smoke() {{\n    let _ = {names[0]} as usize;\n}}\n") if False else f"use {crate}::*;\n\n#[test]\nfn the_crate_builds() {{\n    let f = {names[-1]};\n    let _ = &f;\n}}\n"
        cargo = langs.cargo_toml(crate)
        base = {"Cargo.toml": cargo, "src/lib.rs": original, "tests/smoke.rs": vis}
        from generators.refactor import _kit as rk
        check = CHECK.replace("__ORIGINAL__", repr(original)).replace("__FUNCS__", repr(names)).replace("__FALLIBLE__", repr(fallible))
        hidden = {"checks/rsdoc.py": check, **rk.clike_lib()}
        solution = {"src/lib.rs": solved}
        prove_docs(f"{mod['key']}-{i}", base, hidden, solution, CMD, "cargo test --offline --quiet", timeout=300)
        yield Task(slug=f"{i + 1:02d}-{mod['key']}-{len(names)}fn", prompt=rng.choice(PROMPTS).format(crate_=crate), difficulty=2 if len(names) <= 3 else 3, start=base, hidden=hidden,
                   solution=solution, verify=CMD, timeout_s=300, tags=["rustdoc", "doctest", "documentation"], notes={"module": mod["key"], "functions": names})
