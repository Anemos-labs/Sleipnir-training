//! Readers for index.txt, project.txt and lock.txt.
use crate::config;
use crate::versions::{is_name, Constraint, Version};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone)]
pub struct Need {
    pub dep: String,
    pub constraint: Constraint,
    pub feats: Vec<String>,
    pub gate: Option<String>,
}

pub struct Package {
    pub name: String,
    pub version: Version,
    pub needs: Vec<Need>,
    pub breaks: Vec<(String, Constraint)>,
    pub features: Vec<String>,
    pub yanked: bool,
}

impl Package {
    pub fn active_needs(&self, enabled: &BTreeSet<String>) -> Vec<Need> {
        self.needs.iter().filter(|n| n.gate.as_ref().map_or(true, |g| enabled.contains(g))).cloned().collect()
    }
}

pub struct Index {
    pub pkgs: Vec<Package>,
    pub by_name: BTreeMap<String, Vec<usize>>, // newest version first
}

impl Index {
    pub fn versions(&self, name: &str) -> Vec<usize> {
        self.by_name.get(name).cloned().unwrap_or_default()
    }

    pub fn find(&self, name: &str, v: &Version) -> Option<usize> {
        self.by_name.get(name)?.iter().copied().find(|&i| self.pkgs[i].version == *v)
    }
}

fn err<T>(file: &str, n: usize, msg: &str) -> Result<T, String> {
    Err(format!("{}:{}: {}", file, n, msg))
}

fn words(line: &str) -> Vec<&str> {
    line.split('#').next().unwrap_or("").split_whitespace().collect()
}

fn features_of(tokens: &[&str], file: &str, n: usize) -> Result<Vec<String>, String> {
    let mut set = BTreeSet::new();
    for t in tokens {
        let ok = t.starts_with('+') && is_name(&t[1..]);
        if !ok {
            return err(file, n, &format!("bad name '{}'", t.trim_start_matches('+')));
        }
        set.insert(t[1..].to_string());
    }
    Ok(set.into_iter().collect())
}

/// needs NAME CONSTRAINT [+FEATURE...] [if FEATURE]
fn need_line(w: &[&str], n: usize) -> Result<Need, String> {
    let mut w = w.to_vec();
    let mut gate = None;
    if config::FEATURES && w.len() >= 3 && w[w.len() - 2] == "if" {
        gate = Some(w[w.len() - 1].to_string());
        w.truncate(w.len() - 2);
    }
    if w.len() < 3 || (!config::FEATURES && w.len() != 3) {
        return err("index.txt", n, "bad line");
    }
    let mut names = vec![w[1].to_string()];
    if let Some(g) = &gate {
        names.push(g.clone());
    }
    for name in names {
        if !is_name(&name) {
            return err("index.txt", n, &format!("bad name '{}'", name));
        }
    }
    let constraint = match Constraint::parse(w[2]) {
        Some(c) => c,
        None => return err("index.txt", n, &format!("bad constraint '{}'", w[2])),
    };
    let feats = features_of(&w[3..], "index.txt", n)?;
    Ok(Need { dep: w[1].to_string(), constraint, feats, gate })
}

pub fn read_index(text: &str) -> Result<Index, String> {
    let mut all: Vec<Package> = Vec::new();
    for (i, line) in text.split('\n').enumerate() {
        let n = i + 1;
        let w = words(line);
        if w.is_empty() {
            continue;
        }
        let d = w[0];
        if d == "pkg" {
            if w.len() != 3 {
                return err("index.txt", n, "bad line");
            }
            if !is_name(w[1]) {
                return err("index.txt", n, &format!("bad name '{}'", w[1]));
            }
            let ver = match Version::parse(w[2]) {
                Some(v) => v,
                None => return err("index.txt", n, &format!("bad version '{}'", w[2])),
            };
            if all.iter().any(|p| p.name == w[1] && p.version == ver) {
                return err("index.txt", n, &format!("duplicate package {} {}", w[1], w[2]));
            }
            all.push(Package { name: w[1].to_string(), version: ver, needs: vec![], breaks: vec![], features: vec![], yanked: false });
            continue;
        }
        let mut known = vec!["needs", "yanked"];
        if config::BREAKS {
            known.push("breaks");
        }
        if config::FEATURES {
            known.push("feature");
        }
        if !known.contains(&d) {
            return err("index.txt", n, &format!("unknown directive '{}'", d));
        }
        let cur = match all.last_mut() {
            Some(c) => c,
            None => return err("index.txt", n, &format!("'{}' outside a package block", d)),
        };
        match d {
            "yanked" => {
                if w.len() != 1 {
                    return err("index.txt", n, "bad line");
                }
                cur.yanked = true;
            }
            "feature" => {
                if w.len() != 2 {
                    return err("index.txt", n, "bad line");
                }
                if !is_name(w[1]) {
                    return err("index.txt", n, &format!("bad name '{}'", w[1]));
                }
                if cur.features.iter().any(|f| f == w[1]) {
                    return err("index.txt", n, &format!("duplicate feature '{}'", w[1]));
                }
                cur.features.push(w[1].to_string());
            }
            "breaks" => {
                if w.len() != 3 {
                    return err("index.txt", n, "bad line");
                }
                if !is_name(w[1]) {
                    return err("index.txt", n, &format!("bad name '{}'", w[1]));
                }
                match Constraint::parse(w[2]) {
                    Some(c) => cur.breaks.push((w[1].to_string(), c)),
                    None => return err("index.txt", n, &format!("bad constraint '{}'", w[2])),
                }
            }
            _ => {
                let need = need_line(&w, n)?;
                if let Some(g) = &need.gate {
                    if !cur.features.contains(g) {
                        return err("index.txt", n, &format!("undeclared feature '{}'", g));
                    }
                }
                cur.needs.push(need);
            }
        }
    }
    let mut by_name: BTreeMap<String, Vec<usize>> = BTreeMap::new();
    for (i, p) in all.iter().enumerate() {
        by_name.entry(p.name.clone()).or_default().push(i);
    }
    for list in by_name.values_mut() {
        list.sort_by(|a, b| all[*b].version.key().cmp(&all[*a].version.key()));
    }
    Ok(Index { pkgs: all, by_name })
}

pub type Want = (String, Constraint, Vec<String>);

pub fn read_project(text: &str) -> Result<Vec<Want>, String> {
    let mut wants = Vec::new();
    for (i, line) in text.split('\n').enumerate() {
        let n = i + 1;
        let w = words(line);
        if w.is_empty() {
            continue;
        }
        if w[0] != "want" {
            return err("project.txt", n, &format!("unknown directive '{}'", w[0]));
        }
        if w.len() < 3 || (!config::FEATURES && w.len() != 3) {
            return err("project.txt", n, "bad line");
        }
        if !is_name(w[1]) {
            return err("project.txt", n, &format!("bad name '{}'", w[1]));
        }
        let c = match Constraint::parse(w[2]) {
            Some(c) => c,
            None => return err("project.txt", n, &format!("bad constraint '{}'", w[2])),
        };
        wants.push((w[1].to_string(), c, features_of(&w[3..], "project.txt", n)?));
    }
    Ok(wants)
}

pub type Lock = BTreeMap<String, (Version, BTreeSet<String>)>;

pub fn read_lock(text: &str) -> Result<Lock, String> {
    let mut out = Lock::new();
    for (i, line) in text.split('\n').enumerate() {
        let n = i + 1;
        let w = words(line);
        if w.is_empty() {
            continue;
        }
        if (w.len() != 2 && w.len() != 3) || (w.len() == 3 && !config::FEATURES) {
            return err("lock.txt", n, "bad line");
        }
        if !is_name(w[0]) {
            return err("lock.txt", n, &format!("bad name '{}'", w[0]));
        }
        let ver = match Version::parse(w[1]) {
            Some(v) => v,
            None => return err("lock.txt", n, &format!("bad version '{}'", w[1])),
        };
        let plus: Vec<String> = if w.len() == 3 { w[2].split(',').map(|f| format!("+{}", f)).collect() } else { vec![] };
        let refs: Vec<&str> = plus.iter().map(|s| s.as_str()).collect();
        let feats = features_of(&refs, "lock.txt", n)?;
        if out.contains_key(w[0]) {
            return err("lock.txt", n, &format!("duplicate package '{}'", w[0]));
        }
        out.insert(w[0].to_string(), (ver, feats.into_iter().collect()));
    }
    Ok(out)
}
