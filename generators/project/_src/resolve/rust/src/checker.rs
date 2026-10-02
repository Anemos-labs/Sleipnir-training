//! `check` (validate a lock against the index and the project) and `tree` (print the locked dependency tree).
use crate::config;
use crate::files::{Index, Lock, Want};
use std::collections::BTreeSet;

pub fn fmt_feats(feats: &BTreeSet<String>) -> String {
    feats.iter().cloned().collect::<Vec<_>>().join(",")
}

pub fn check(index: &Index, wants: &[Want], lock: &Lock) -> Vec<String> {
    let mut out = Vec::new();
    for (name, cons, feats) in wants {
        let (ver, enabled) = match lock.get(name) {
            Some(x) => x,
            None => {
                out.push(format!("problem: root wants {} {} but {} is not locked", name, cons.text, name));
                continue;
            }
        };
        if !cons.allows(ver) {
            out.push(format!("problem: root wants {} {} but locked {} is {}", name, cons.text, name, ver.text));
        }
        for f in feats {
            if !enabled.contains(f) {
                out.push(format!("problem: root wants {} +{} but the lock does not enable it", name, f));
            }
        }
    }
    for (name, (ver, enabled)) in lock {
        let pi = match index.find(name, ver) {
            Some(i) => i,
            None => {
                out.push(format!("problem: {} {} is not in the index", name, ver.text));
                continue;
            }
        };
        let pkg = &index.pkgs[pi];
        for f in enabled {
            if !pkg.features.contains(f) {
                out.push(format!("problem: {} {} has no feature {}", name, ver.text, f));
            }
        }
        for need in pkg.active_needs(enabled) {
            let (dver, denabled) = match lock.get(&need.dep) {
                Some(x) => x,
                None => {
                    out.push(format!("problem: {} {} needs {} {} but {} is not locked", name, ver.text, need.dep, need.constraint.text, need.dep));
                    continue;
                }
            };
            if !need.constraint.allows(dver) {
                out.push(format!("problem: {} {} needs {} {} but locked {} is {}", name, ver.text, need.dep, need.constraint.text, need.dep, dver.text));
            }
            for f in &need.feats {
                if !denabled.contains(f) {
                    out.push(format!("problem: {} {} needs {} +{} but the lock does not enable it", name, ver.text, need.dep, f));
                }
            }
        }
        for (target, c) in &pkg.breaks {
            if let Some((tv, _)) = lock.get(target) {
                if c.allows(tv) {
                    out.push(format!("problem: {} {} breaks {} {} but locked {} is {}", name, ver.text, target, c.text, target, tv.text));
                }
            }
        }
    }
    if config::CHECK_UNUSED {
        let reach = reachable(index, wants, lock);
        for name in lock.keys() {
            if !reach.contains(name) {
                out.push(format!("problem: {} is locked but nothing needs it", name));
            }
        }
    }
    out
}

/// Names a locked package depends on (the active needs of its locked version), sorted.
fn deps_of(index: &Index, name: &str, lock: &Lock) -> Vec<String> {
    let (ver, enabled) = &lock[name];
    match index.find(name, ver) {
        None => vec![],
        Some(pi) => index.pkgs[pi].active_needs(enabled).into_iter().map(|n| n.dep).collect::<BTreeSet<_>>().into_iter().collect(),
    }
}

fn reachable(index: &Index, wants: &[Want], lock: &Lock) -> BTreeSet<String> {
    let mut seen = BTreeSet::new();
    let mut todo: Vec<String> = wants.iter().map(|w| w.0.clone()).collect();
    while let Some(n) = todo.pop() {
        if seen.contains(&n) || !lock.contains_key(&n) {
            continue;
        }
        seen.insert(n.clone());
        todo.extend(deps_of(index, &n, lock));
    }
    seen
}

fn label(name: &str, lock: &Lock) -> String {
    match lock.get(name) {
        None => format!("{} (not locked)", name),
        Some((ver, enabled)) => {
            if enabled.is_empty() {
                format!("{} {}", name, ver.text)
            } else {
                format!("{} {} [{}]", name, ver.text, fmt_feats(enabled))
            }
        }
    }
}

fn walk(index: &Index, name: &str, depth: usize, lock: &Lock, shown: &mut BTreeSet<String>, lines: &mut Vec<String>) {
    let text = label(name, lock);
    let pad = "  ".repeat(depth);
    if lock.contains_key(name) && shown.contains(name) {
        lines.push(format!("{}{} (*)", pad, text));
        return;
    }
    lines.push(format!("{}{}", pad, text));
    if !lock.contains_key(name) {
        return;
    }
    shown.insert(name.to_string());
    for d in deps_of(index, name, lock) {
        walk(index, &d, depth + 1, lock, shown, lines);
    }
}

pub fn tree(index: &Index, wants: &[Want], lock: &Lock) -> Vec<String> {
    let mut lines = vec!["root".to_string()];
    let mut shown = BTreeSet::new();
    let names: BTreeSet<&String> = wants.iter().map(|w| &w.0).collect();
    for name in names {
        walk(index, name, 1, lock, &mut shown, &mut lines);
    }
    lines
}
