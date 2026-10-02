//! Command line: lock, upgrade, tree, check.
mod checker;
mod config;
mod files;
mod solver;
mod versions;

use files::{read_index, read_lock, read_project, Index, Lock, Want};
use solver::{Outcome, Solver};
use std::collections::BTreeMap;
use versions::Version;

fn read(path: &str) -> Option<String> {
    std::fs::read_to_string(path).ok()
}

fn fail(msg: &str) -> i32 {
    println!("error: {}", msg);
    1
}

#[derive(PartialEq)]
enum LockMode {
    None,
    Optional,
    Required,
}

fn load(mode: LockMode) -> Result<(Index, Vec<Want>, Option<Lock>), String> {
    let text = read("index.txt").ok_or("cannot read index.txt")?;
    let index = read_index(&text)?;
    let text = read("project.txt").ok_or("cannot read project.txt")?;
    let wants = read_project(&text)?;
    let mut lock = None;
    if mode != LockMode::None {
        match read("lock.txt") {
            None => {
                if mode == LockMode::Required {
                    return Err("cannot read lock.txt".to_string());
                }
            }
            Some(t) => lock = Some(read_lock(&t)?),
        }
    }
    Ok((index, wants, lock))
}

fn resolve(index: &Index, wants: &[Want], oldest: bool, prefer: &BTreeMap<String, Version>) -> i32 {
    let mut s = Solver::new(index, wants, oldest, prefer);
    let st = match s.run() {
        Outcome::Limit => return fail("search limit reached"),
        Outcome::Dead => return fail(&s.dead.clone().unwrap_or_default()),
        Outcome::Solved(st) => st,
    };
    let mut lines = Vec::new();
    for (name, &pi) in &st.chosen {
        let p = &index.pkgs[pi];
        let feats = st.feats.get(name).cloned().unwrap_or_default();
        let mut l = format!("{} {}", name, p.version.text);
        if !feats.is_empty() {
            l.push(' ');
            l.push_str(&checker::fmt_feats(&feats));
        }
        lines.push(l);
    }
    let body: String = lines.iter().map(|l| format!("{}\n", l)).collect();
    let _ = std::fs::write("lock.txt", body);
    for l in &lines {
        println!("{}", l);
    }
    println!("locked {} packages", lines.len());
    0
}

fn cmd_lock(args: &[String]) -> Result<i32, String> {
    let (mut oldest, mut fresh) = (false, false);
    for a in args {
        if a == "--oldest" && config::OLDEST_OPT {
            oldest = true;
        } else if a == "--fresh" && config::STICKY {
            fresh = true;
        } else if a.starts_with('-') {
            return Ok(fail(&format!("unknown option '{}'", a)));
        } else {
            return Ok(fail(&format!("usage: {} lock [OPTION...]", config::TOOL)));
        }
    }
    let mode = if config::STICKY && !fresh { LockMode::Optional } else { LockMode::None };
    let (index, wants, lock) = load(mode)?;
    let mut prefer = BTreeMap::new();
    if let Some(l) = lock {
        for (n, (v, _)) in l {
            prefer.insert(n, v);
        }
    }
    Ok(resolve(&index, &wants, oldest, &prefer))
}

fn cmd_upgrade(args: &[String]) -> Result<i32, String> {
    if args.is_empty() {
        return Ok(fail(&format!("usage: {} upgrade NAME...", config::TOOL)));
    }
    let (index, wants, lock) = load(LockMode::Required)?;
    let lock = lock.unwrap();
    for n in args {
        if !lock.contains_key(n) {
            return Ok(fail(&format!("{} is not locked", n)));
        }
    }
    let mut prefer = BTreeMap::new();
    for (n, (v, _)) in lock {
        if !args.contains(&n) {
            prefer.insert(n, v);
        }
    }
    Ok(resolve(&index, &wants, false, &prefer))
}

fn cmd_tree(args: &[String]) -> Result<i32, String> {
    if !args.is_empty() {
        return Ok(fail(&format!("usage: {} tree", config::TOOL)));
    }
    let (index, wants, lock) = load(LockMode::Required)?;
    for l in checker::tree(&index, &wants, &lock.unwrap()) {
        println!("{}", l);
    }
    Ok(0)
}

fn cmd_check(args: &[String]) -> Result<i32, String> {
    if !args.is_empty() {
        return Ok(fail(&format!("usage: {} check", config::TOOL)));
    }
    let (index, wants, lock) = load(LockMode::Required)?;
    let lock = lock.unwrap();
    let problems = checker::check(&index, &wants, &lock);
    for p in &problems {
        println!("{}", p);
    }
    if !problems.is_empty() {
        println!("FAILED: {} problems", problems.len());
        return Ok(1);
    }
    println!("ok: {} packages", lock.len());
    Ok(0)
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let code = if args.is_empty() {
        fail(&format!("usage: {} COMMAND [ARGS]", config::TOOL))
    } else {
        let rest = &args[1..];
        let result = match args[0].as_str() {
            "lock" => cmd_lock(rest),
            "tree" => cmd_tree(rest),
            "check" => cmd_check(rest),
            "upgrade" if config::STICKY => cmd_upgrade(rest),
            other => Ok(fail(&format!("unknown command '{}'", other))),
        };
        match result {
            Ok(c) => c,
            Err(e) => fail(&e),
        }
    };
    std::process::exit(code);
}
