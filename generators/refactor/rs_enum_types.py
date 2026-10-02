"""Stringly-typed rust becomes enums and exhaustive matches."""
from __future__ import annotations

import json
import re

from fx import Task, dd, family, langs, merged, run

from . import _kit
from ._kit import clike_lib, prove, tabify

RS_VERIFY = "cargo test --offline --quiet && python3 checks/structure.py"
RS_BEHAVIOUR = "cargo test --offline --quiet"
RS_STRUCT = "python3 checks/structure.py"

DOMAINS = [
    dict(key="parcel", crate="parcelpost", ty="Zone", pool=[("domestic", "Domestic post"), ("eu", "European Union"), ("world", "Rest of world"), ("remote", "Remote islands"),
                                                              ("freight", "Freight lane"), ("express", "Express air"), ("pickup", "Customer pickup")],
         f_rate="rate", f_label="label", f_flag="customs_needed", flag_doc="whether customs paperwork is needed", qty="kg", err="unknown zone", quote="quote",
         formula="base + per * qty", topic="parcel pricing", what="zone", base=(250, 900), per=(20, 160)),
    dict(key="soil", crate="allotment", ty="Soil", pool=[("sand", "Sandy"), ("clay", "Heavy clay"), ("loam", "Loam"), ("peat", "Peat"), ("chalk", "Chalky"), ("silt", "Silty")],
         f_rate="water_litres", f_label="describe", f_flag="needs_lime", flag_doc="whether the bed needs liming", qty="sqm", err="unknown soil", quote="water_for",
         formula="base + per * qty / 10", topic="allotment watering", what="soil type", base=(30, 120), per=(5, 40)),
    dict(key="tier", crate="boxoffice", ty="Tier", pool=[("floor", "Standing floor"), ("balcony", "Balcony"), ("circle", "Dress circle"), ("stalls", "Stalls"), ("box", "Private box"),
                                                         ("gallery", "Gallery"), ("lounge", "Lounge table")],
         f_rate="price", f_label="name", f_flag="has_lounge", flag_doc="whether the ticket includes lounge access", qty="seats", err="unknown tier", quote="price_for",
         formula="base * qty + per * (qty / 4)", topic="box office pricing", what="seating tier", base=(1500, 9000), per=(100, 900)),
]


def camel(s):
    return "".join(p.capitalize() for p in re.split(r"[_\-]", s))


def _variants(rng, dom, k):
    picks = rng.sample(dom["pool"], k)
    out = []
    for name, label in picks:
        out.append({"name": name, "label": label, "base": rng.randrange(dom["base"][0], dom["base"][1], 5), "per": rng.randrange(dom["per"][0], dom["per"][1], 5),
                    "flag": rng.random() < 0.4, "var": camel(name)})
    if not any(v["flag"] for v in out):
        out[0]["flag"] = True
    return out


def _arms(vs, fn, indent="        "):
    return "\n".join(f"{indent}{fn(v)}" for v in vs)


def legacy_src(dom, vs):
    q, err = dom["qty"], dom["err"]
    f = dom["formula"]
    return dd(f'''
    //! {dom["topic"].capitalize()}.

    /// Display name of a {dom["what"]}.
    pub fn {dom["f_label"]}({dom["what"].split()[0]}: &str) -> Result<&'static str, String> {{
        match {dom["what"].split()[0]} {{
    {_arms(vs, lambda v: f'"{v["name"]}" => Ok("{v["label"]}"),')}
            _ => Err(format!("{err}: {{}}", {dom["what"].split()[0]})),
        }}
    }}

    /// {dom["flag_doc"].capitalize()}.
    pub fn {dom["f_flag"]}({dom["what"].split()[0]}: &str) -> Result<bool, String> {{
        match {dom["what"].split()[0]} {{
    {_arms(vs, lambda v: f'"{v["name"]}" => Ok({"true" if v["flag"] else "false"}),')}
            _ => Err(format!("{err}: {{}}", {dom["what"].split()[0]})),
        }}
    }}

    /// Price or amount for a {dom["what"]} and a quantity ({q}).
    pub fn {dom["f_rate"]}({dom["what"].split()[0]}: &str, {q}: u32) -> Result<u32, String> {{
        let base = match {dom["what"].split()[0]} {{
    {_arms(vs, lambda v: f'"{v["name"]}" => {v["base"]},')}
            _ => return Err(format!("{err}: {{}}", {dom["what"].split()[0]})),
        }};
        let per = match {dom["what"].split()[0]} {{
    {_arms(vs, lambda v: f'"{v["name"]}" => {v["per"]},')}
            _ => return Err(format!("{err}: {{}}", {dom["what"].split()[0]})),
        }};
        let qty = {q};
        Ok({f})
    }}
    ''')


def new_src(dom, vs):
    q, err, ty = dom["qty"], dom["err"], dom["ty"]
    arg = dom["what"].split()[0]
    return dd(f'''
    //! {dom["topic"].capitalize()}.

    /// The {dom["what"]}s we know about.
    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum {ty} {{
    {_arms(vs, lambda v: v["var"] + ",", "    ")}
    }}

    impl {ty} {{
        /// Parse the lower-case name used in orders; `None` for anything unknown.
        pub fn parse(s: &str) -> Option<{ty}> {{
            match s {{
    {_arms(vs, lambda v: f'"{v["name"]}" => Some({ty}::{v["var"]}),', "            ")}
                _ => None,
            }}
        }}
    }}

    /// Display name of a {dom["what"]}.
    pub fn {dom["f_label"]}({arg}: {ty}) -> &'static str {{
        match {arg} {{
    {_arms(vs, lambda v: f'{ty}::{v["var"]} => "{v["label"]}",')}
        }}
    }}

    /// {dom["flag_doc"].capitalize()}.
    pub fn {dom["f_flag"]}({arg}: {ty}) -> bool {{
        match {arg} {{
    {_arms(vs, lambda v: f'{ty}::{v["var"]} => {"true" if v["flag"] else "false"},')}
        }}
    }}

    /// Price or amount for a {dom["what"]} and a quantity ({q}).
    pub fn {dom["f_rate"]}({arg}: {ty}, {q}: u32) -> u32 {{
        let (base, per) = match {arg} {{
    {_arms(vs, lambda v: f'{ty}::{v["var"]} => ({v["base"]}, {v["per"]}),')}
        }};
        let qty = {q};
        {dom["formula"]}
    }}

    /// The string-facing entry point used by order forms.
    pub fn {dom["quote"]}({arg}: &str, {q}: u32) -> Result<u32, String> {{
        let parsed = {ty}::parse({arg}).ok_or_else(|| format!("{err}: {{}}", {arg}))?;
        Ok({dom["f_rate"]}(parsed, {q}))
    }}
    ''')


def _harness_rs(dom, vs, cases, legacy, want=None, golden=False):
    arg = dom["what"].split()[0]
    ty, err, q = dom["ty"], dom["err"], dom["qty"]
    names = [v["name"] for v in vs]
    rows = ", ".join(f'("{n}", {u})' for n, u in cases)
    if legacy:
        lab, flag, rate = f"{dom['f_label']}(z)", f"{dom['f_flag']}(z)", f"{dom['f_rate']}(z, q)"
    else:
        lab = f'{ty}::parse(z).map({dom["f_label"]}).ok_or_else(|| format!("{err}: {{}}", z))'
        flag = f'{ty}::parse(z).map({dom["f_flag"]}).ok_or_else(|| format!("{err}: {{}}", z))'
        rate = f"{dom['quote']}(z, q)"
    head = (f"use {dom['crate']}::*;\n\nconst CASES: &[(&str, u32)] = &[{rows}];\n\n"
            f"fn outcome(i: usize) -> String {{\n    let (z, q) = CASES[i];\n    format!(\"{{:?}}|{{:?}}|{{:?}}\", {lab}, {flag}, {rate})\n}}\n")
    if golden:
        return head + "\n#[test]\nfn golden() {\n    for i in 0..CASES.len() {\n        println!(\"GOLDEN|{}|{}\", i, outcome(i));\n    }\n}\n"
    wl = ",\n".join("    " + json.dumps(w) for w in want)
    return head + f"\nconst WANT: &[&str] = &[\n{wl},\n];\n\n#[test]\nfn recorded_outcomes() {{\n    for i in 0..CASES.len() {{\n        assert_eq!(outcome(i), WANT[i], \"case {{}}\", i);\n    }}\n}}\n"


def rs_golden(files, dom, vs, cases):
    t = _harness_rs(dom, vs, cases, True, golden=True)
    r = run(merged(files, {"tests/golden.rs": t}), "cargo test --offline --quiet --test golden -- --nocapture", timeout=180)
    lines = [ln for ln in r.out.splitlines() if ln.startswith("GOLDEN|")]
    if not r.ok or len(lines) != len(cases):
        raise RuntimeError("rust golden run failed:\n" + r.out[-2500:])
    return [ln.split("|", 2)[2] for ln in lines]


PROMPTS = [
    "`src/lib.rs` ({topic}) passes the {what} around as a `&str` and every function matches on string literals, repeating the list of {what}s and the \"{err}\" error three times. "
    "Replace that with a proper enum: `pub enum {ty} {{ {variants} }}` (derive `Debug, Clone, Copy, PartialEq, Eq`) with `{ty}::parse(&str) -> Option<{ty}>`, and give "
    "`{f_label}`, `{f_flag}` and `{f_rate}` an `{ty}` instead of a `&str` (no more `Result`: they cannot fail now; `{f_label}` returns `&'static str`, `{f_flag}` a `bool`, `{f_rate}` a `u32`). "
    "Add `pub fn {quote}(&str, u32) -> Result<u32, String>` as the string-facing entry point: it parses, fails with `\"{err}: <input>\"` for unknown names and otherwise returns what "
    "`{f_rate}` returns. Numbers and labels must not change. The only string matching left should be `{ty}::parse`.",
    "Make `{f_rate}`, `{f_label}` and `{f_flag}` in `src/lib.rs` type-safe: introduce `pub enum {ty}` with the variants {variants} (derive Debug, Clone, Copy, PartialEq, Eq) and "
    "`{ty}::parse(&str) -> Option<{ty}>`; the three functions take the enum and return plain `&'static str` / `bool` / `u32`; a new `{quote}(&str, u32) -> Result<u32, String>` "
    "parses the name (error text `{err}: <input>`) and calls `{f_rate}`. Same results as today for every known {what}; `{ty}::parse` is the only place that still compares strings.",
    "stringly typed {what}s in the {topic} crate. introduce `{ty}` enum ({variants}), `{ty}::parse(&str) -> Option<{ty}>`, make `{f_label}(…) -> &'static str`, `{f_flag}(…) -> bool`, "
    "`{f_rate}(…, u32) -> u32` take it, add `{quote}(&str, u32) -> Result<u32, String>` (error `{err}: <input>`). same numbers. no other string matching.",
]


@family("refactor-rs-enum-types", category="refactor", lang="rust", kind="refactor", n=9,
        summary="stringly-typed rust (match on &str in several functions) becomes an enum with parse + exhaustive matches; new API stated")
def gen(rng, n):
    order = list(DOMAINS) * 3
    rng.shuffle(order)
    for i in range(n):
        dom = order[i]
        k = rng.choice([3, 4, 5, 6])
        vs = _variants(rng, dom, k)
        crate = dom["crate"]
        cargo = langs.cargo_toml(crate)
        legacy = legacy_src(dom, vs)
        base = {"Cargo.toml": cargo, "src/lib.rs": legacy}
        cases = []
        for j in range(24):
            nm = rng.choice([v["name"] for v in vs] + (["nowhere"] if j % 8 == 7 else []))
            cases.append((nm, rng.choice([0, 1, 2, 5, 10, 37, 100])))
        want = rs_golden(base, dom, vs, cases)
        vis_idx = [j for j, w in enumerate(want) if "Err" not in w][:3] + [j for j, w in enumerate(want) if "Err" in w][:1]
        vis = _harness_rs(dom, vs, [cases[j] for j in vis_idx], False, [want[j] for j in vis_idx])
        hid = _harness_rs(dom, vs, cases, False, want)
        bound = k + 2
        variants_txt = ", ".join(f"`{v['var']}`" for v in vs)
        struct = dd(f'''
        import re

        import clike as C

        FILES = C.files([".rs"], dirs=["src"])
        problems = []
        text = "\\n".join(C.clean(C.read(f), "rust") for f in FILES)
        arms = len(re.findall(r'^\\s*"[^"\\n]*"\\s*(?:\\|\\s*"[^"\\n]*"\\s*)*=>', text, re.M))
        if arms > {bound}:
            problems.append("%d string-literal match arms remain (at most {bound}: only {dom['ty']}::parse should match on strings)" % arms)
        if re.search(r'==\\s*"', text):
            problems.append("comparison with a string literal found")
        m = re.search(r"\\benum\\s+{dom['ty']}\\s*\\{{([^}}]*)\\}}", text)
        if not m:
            problems.append("missing enum {dom['ty']}")
        else:
            for v in {json.dumps([v['var'] for v in vs])}:
                if not re.search(r"\\b" + v + r"\\b", m.group(1)):
                    problems.append("enum {dom['ty']} lacks the variant " + v)
        C.report(problems)
        ''')
        start = {**base, "tests/example.rs": vis}
        hidden = {"tests/behaviour.rs": hid, "checks/structure.py": struct, **clike_lib()}
        sol = {"src/lib.rs": new_src(dom, vs)}
        prove(dom["key"], start, hidden, sol, RS_BEHAVIOUR, RS_STRUCT, RS_VERIFY, behaviour_on_start=False, timeout=240)
        prompt = rng.choice(PROMPTS).format(topic=dom["topic"], what=dom["what"], err=dom["err"], ty=dom["ty"], variants=variants_txt, f_label=dom["f_label"], f_flag=dom["f_flag"],
                                            f_rate=dom["f_rate"], quote=dom["quote"])
        d = 2 if k <= 4 else 3
        yield Task(slug=f"{i + 1:02d}-{dom['key']}-{k}", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=sol, verify=RS_VERIFY, timeout_s=240,
                   tags=["enum", "stringly-typed", "exhaustive-match"], notes={"domain": dom["key"], "variants": [v["name"] for v in vs]})
