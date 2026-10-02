//! tiers: a scripted tiered key-value store (memtable, runs, compaction).
mod config;
mod store;

use std::io::{Read, Write};
use store::{Lookup, Store};

fn is_key(s: &str) -> bool {
    !s.is_empty() && s.len() <= 8 && s.bytes().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'_')
}

fn is_value(s: &str) -> bool {
    !s.is_empty() && s.len() <= 12 && s.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'.' || c == b'-')
}

fn key_arg(tok: &str) -> Result<&str, String> {
    if is_key(tok) {
        Ok(tok)
    } else {
        Err(format!("bad key '{}'", tok))
    }
}

fn run(st: &mut Store, cmd: &str, args: &[&str]) -> Result<Vec<String>, String> {
    let mut out: Vec<String> = Vec::new();
    match cmd {
        "put" => {
            if args.len() != 2 {
                return Err("usage: put KEY VALUE".to_string());
            }
            key_arg(args[0])?;
            if !is_value(args[1]) {
                return Err(format!("bad value '{}'", args[1]));
            }
            st.write(args[0], Some(args[1].to_string()));
        }
        "del" => {
            if args.len() != 1 {
                return Err("usage: del KEY".to_string());
            }
            st.write(key_arg(args[0])?, None);
        }
        "get" => {
            if args.len() != 1 {
                return Err("usage: get KEY".to_string());
            }
            let key = key_arg(args[0])?;
            out.push(match st.lookup(key) {
                Lookup::Live(v, src, p) => format!("{} = {} ({}, {} probed)", key, v, src, p),
                Lookup::Deleted(src, p) => format!("{} deleted ({}, {} probed)", key, src, p),
                Lookup::Missing(p) => format!("{} not found ({} probed)", key, p),
            });
        }
        "scan" => {
            if args.len() != 2 {
                return Err("usage: scan LO HI".to_string());
            }
            let (lo, hi) = (key_arg(args[0])?, key_arg(args[1])?);
            if lo >= hi {
                return Err("empty range".to_string());
            }
            let mut n = 0;
            for (k, v) in st.view() {
                if lo <= k.as_str() && k.as_str() < hi {
                    out.push(format!("{} = {}", k, v));
                    n += 1;
                }
            }
            out.push(format!("{} keys", n));
        }
        "flush" => {
            if !args.is_empty() {
                return Err("usage: flush".to_string());
            }
            if !st.flush() {
                out.push("memtable is empty".to_string());
            }
        }
        "compact" => {
            if args == ["all"] && config::HAS_ALL {
                if !st.compact_all() {
                    out.push("nothing to compact".to_string());
                }
            } else if args.is_empty() {
                if !st.compact() {
                    out.push("nothing to compact".to_string());
                }
            } else {
                return Err(format!("usage: compact{}", if config::HAS_ALL { " [all]" } else { "" }));
            }
        }
        "dump" => {
            if !args.is_empty() {
                return Err("usage: dump".to_string());
            }
            let mem: Vec<String> = st.mem.iter().map(|(k, v)| format!("{}={}", k, v.clone().unwrap_or_else(|| "<del>".to_string()))).collect();
            out.push(format!("memtable: {}", if mem.is_empty() { "-".to_string() } else { mem.join(" ") }));
            for (i, level) in st.levels.iter().enumerate() {
                let runs: Vec<String> = level.iter().rev().map(|r| format!("#{}[{}..{}:{}]", r.id, r.lo, r.hi, r.entries.len())).collect();
                out.push(format!("L{}: {}", i, if runs.is_empty() { "-".to_string() } else { runs.join(" ") }));
            }
        }
        "stats" => {
            if !args.is_empty() {
                return Err("usage: stats".to_string());
            }
            let (runs, entries, tombs, live) = st.stats();
            out.push(format!("runs={} entries={} tombstones={} live={} next={}", runs, entries, tombs, live, st.next_id));
        }
        _ => return Err(format!("unknown command '{}'", cmd)),
    }
    Ok(out)
}

fn main() {
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input).ok();
    let mut st = Store::new();
    let mut out: Vec<String> = Vec::new();
    let mut errors = 0;
    for raw in input.split('\n') {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let words: Vec<&str> = line.split_whitespace().collect();
        let res = run(&mut st, words[0], &words[1..]);
        // lines produced while the command ran (flush/compaction events) come first, then the command's own output
        out.append(&mut st.lines);
        match res {
            Ok(mut lines) => out.append(&mut lines),
            Err(e) => {
                out.push(format!("error: {}", e));
                errors += 1;
            }
        }
    }
    let stdout = std::io::stdout();
    let mut w = stdout.lock();
    for l in &out {
        writeln!(w, "{}", l).ok();
    }
    w.flush().ok();
    std::process::exit(if errors > 0 { 1 } else { 0 });
}
