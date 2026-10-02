//! The resolver: a depth-first search with chronological backtracking over a queue of package names.
use crate::config;
use crate::files::{Index, Need, Want};
use crate::versions::{Constraint, Version};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

#[derive(Clone, Default)]
pub struct State {
    pub chosen: BTreeMap<String, usize>,
    pub reqs: BTreeMap<String, Vec<(Constraint, String)>>,
    pub feats: BTreeMap<String, BTreeSet<String>>,
    pub queue: Vec<String>,
    pub queued: BTreeSet<String>,
    pub breaks: Vec<(String, Constraint)>,
}

pub struct Solver<'a> {
    index: &'a Index,
    wants: &'a [Want],
    oldest: bool,
    prefer: &'a BTreeMap<String, Version>,
    attempts: i64,
    pub dead: Option<String>,
}

pub enum Outcome {
    Solved(State),
    Dead,
    Limit,
}

impl<'a> Solver<'a> {
    pub fn new(index: &'a Index, wants: &'a [Want], oldest: bool, prefer: &'a BTreeMap<String, Version>) -> Solver<'a> {
        Solver { index, wants, oldest, prefer, attempts: 0, dead: None }
    }

    /// Process (owner, need) pairs first in, first out; false if a chosen package cannot accept one.
    fn apply(&self, st: &mut State, mut work: VecDeque<(usize, Need)>) -> bool {
        while let Some((owner, need)) = work.pop_front() {
            let op = &self.index.pkgs[owner];
            let who = format!("{} {}", op.name, op.version.text);
            st.reqs.entry(need.dep.clone()).or_default().push((need.constraint.clone(), who));
            let have = st.feats.entry(need.dep.clone()).or_default();
            let new: Vec<String> = need.feats.iter().filter(|f| !have.contains(*f)).cloned().collect();
            for f in &new {
                have.insert(f.clone());
            }
            if let Some(&di) = st.chosen.get(&need.dep) {
                let dp = &self.index.pkgs[di];
                if !need.constraint.allows(&dp.version) {
                    return false;
                }
                if new.iter().any(|f| !dp.features.contains(f)) {
                    return false;
                }
                for n in &dp.needs {
                    if n.gate.as_ref().map_or(false, |g| new.contains(g)) {
                        work.push_back((di, n.clone()));
                    }
                }
            } else if !st.queued.contains(&need.dep) {
                st.queued.insert(need.dep.clone());
                st.queue.push(need.dep.clone());
            }
        }
        true
    }

    fn candidates(&self, st: &State, name: &str) -> Vec<usize> {
        let cons: Vec<&Constraint> = st.reqs.get(name).map(|v| v.iter().map(|(c, _)| c).collect()).unwrap_or_default();
        let locked = self.prefer.get(name);
        let wanted_feats = st.feats.get(name);
        let mut out = Vec::new();
        for i in self.index.versions(name) {
            let p = &self.index.pkgs[i];
            if p.yanked && !locked.map_or(false, |l| *l == p.version) {
                continue;
            }
            if !cons.iter().all(|c| c.allows(&p.version)) {
                continue;
            }
            if st.breaks.iter().any(|(t, c)| t == name && c.allows(&p.version)) {
                continue;
            }
            if let Some(fs) = wanted_feats {
                if fs.iter().any(|f| !p.features.contains(f)) {
                    continue;
                }
            }
            out.push(i);
        }
        if self.oldest {
            out.reverse();
        }
        if let Some(l) = locked {
            // stable: only the locked version moves to the front
            let (mut first, rest): (Vec<usize>, Vec<usize>) = out.into_iter().partition(|&i| self.index.pkgs[i].version == *l);
            first.extend(rest);
            out = first;
        }
        out
    }

    fn choose(&self, st: &mut State, pi: usize) -> bool {
        let p = &self.index.pkgs[pi];
        st.chosen.insert(p.name.clone(), pi);
        st.feats.entry(p.name.clone()).or_default();
        for (target, c) in &p.breaks {
            if let Some(&ti) = st.chosen.get(target) {
                if c.allows(&self.index.pkgs[ti].version) {
                    return false;
                }
            }
            st.breaks.push((target.clone(), c.clone()));
        }
        let enabled = st.feats[&p.name].clone();
        let work: VecDeque<(usize, Need)> = p.active_needs(&enabled).into_iter().map(|n| (pi, n)).collect();
        self.apply(st, work)
    }

    fn solve(&mut self, st: &State) -> Result<Option<State>, ()> {
        if st.queue.is_empty() {
            return Ok(Some(st.clone()));
        }
        let name = st.queue[0].clone();
        if self.index.versions(&name).is_empty() {
            if self.dead.is_none() {
                self.dead = Some(format!("unknown package {}", name));
            }
            return Ok(None);
        }
        for pi in self.candidates(st, &name) {
            self.attempts += 1;
            if self.attempts > config::LIMIT {
                return Err(());
            }
            let mut s2 = st.clone();
            s2.queue.remove(0);
            if self.choose(&mut s2, pi) {
                if let Some(r) = self.solve(&s2)? {
                    return Ok(Some(r));
                }
            }
        }
        if self.dead.is_none() {
            let needs: Vec<String> = st.reqs.get(&name).map(|v| v.iter().map(|(c, who)| format!("{} ({})", c.text, who)).collect()).unwrap_or_default();
            self.dead = Some(format!("cannot resolve {}: needs {}", name, needs.join(", ")));
        }
        Ok(None)
    }

    pub fn run(&mut self) -> Outcome {
        let mut st = State::default();
        for (name, cons, feats) in self.wants {
            st.reqs.entry(name.clone()).or_default().push((cons.clone(), "root".to_string()));
            let e = st.feats.entry(name.clone()).or_default();
            for f in feats {
                e.insert(f.clone());
            }
            if !st.queued.contains(name) {
                st.queued.insert(name.clone());
                st.queue.push(name.clone());
            }
        }
        match self.solve(&st) {
            Ok(Some(s)) => Outcome::Solved(s),
            Ok(None) => Outcome::Dead,
            Err(()) => Outcome::Limit,
        }
    }
}
