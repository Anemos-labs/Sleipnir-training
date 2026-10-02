//! The tiered store: a memtable, levels of immutable sorted runs, flushes and compactions.
use crate::config;
use std::collections::BTreeMap;

/// A stored value: `None` is a tombstone (a deleted key).
pub type Entries = BTreeMap<String, Option<String>>;

pub struct Run {
    pub id: u32,
    pub entries: Entries,
    pub lo: String,
    pub hi: String,
}

impl Run {
    fn new(id: u32, entries: Entries) -> Run {
        let lo = entries.keys().next().unwrap().clone();
        let hi = entries.keys().next_back().unwrap().clone();
        Run { id, entries, lo, hi }
    }
}

pub struct Store {
    pub mem: Entries,
    pub levels: Vec<Vec<Run>>, // each level lists its runs oldest first
    pub next_id: u32,
    pub lines: Vec<String>,
}

pub enum Lookup {
    Live(String, String, usize),
    Deleted(String, usize),
    Missing(usize),
}

impl Store {
    pub fn new() -> Store {
        let mut levels = Vec::new();
        for _ in 0..config::LEVELS {
            levels.push(Vec::new());
        }
        Store { mem: Entries::new(), levels, next_id: 1, lines: Vec::new() }
    }

    fn say(&mut self, s: String) {
        self.lines.push(s);
    }

    pub fn write(&mut self, key: &str, value: Option<String>) {
        self.mem.insert(key.to_string(), value);
        if self.mem.len() as i64 >= config::MEM_LIMIT {
            self.flush();
        }
    }

    pub fn flush(&mut self) -> bool {
        if self.mem.is_empty() {
            return false;
        }
        let entries = std::mem::take(&mut self.mem);
        let run = Run::new(self.next_id, entries);
        self.next_id += 1;
        let line = format!("flush #{} ({} entries)", run.id, run.entries.len());
        self.levels[0].push(run);
        self.say(line);
        self.cascade();
        true
    }

    fn limit(i: usize) -> usize {
        (if i == 0 { config::L0_LIMIT } else { config::FANOUT }) as usize
    }

    fn merge_level(&mut self, i: usize) {
        let k = if config::MERGE == "all" { self.levels[i].len() } else { self.levels[i].len().min(2) };
        let rest = self.levels[i].split_off(k);
        let take = std::mem::replace(&mut self.levels[i], Vec::new());
        let last = self.levels.len() - 1;
        let target = (i + 1).min(last);
        let drop = if config::DROP == "deep-empty" { self.levels[i + 1..].iter().all(|l| l.is_empty()) } else { i == last };
        let mut merged = Entries::new();
        for run in &take {
            for (key, v) in &run.entries {
                merged.insert(key.clone(), v.clone());
            }
        }
        if drop {
            merged.retain(|_, v| v.is_some());
        }
        let new = if merged.is_empty() {
            None
        } else {
            let r = Run::new(self.next_id, merged);
            self.next_id += 1;
            Some(r)
        };
        let line = match &new {
            Some(r) => format!("compact L{} ({} runs) -> L{} run #{} ({} entries)", i, take.len(), target, r.id, r.entries.len()),
            None => format!("compact L{} ({} runs) -> nothing", i, take.len()),
        };
        if target == i {
            let mut level = Vec::new();
            if let Some(r) = new {
                level.push(r);
            }
            level.extend(rest);
            self.levels[i] = level;
        } else {
            self.levels[i] = rest;
            if let Some(r) = new {
                self.levels[target].push(r);
            }
        }
        self.say(line);
    }

    fn cascade(&mut self) {
        loop {
            let mut hit = None;
            for i in 0..self.levels.len() {
                if self.levels[i].len() >= Store::limit(i) {
                    hit = Some(i);
                    break;
                }
            }
            match hit {
                Some(i) => self.merge_level(i),
                None => return,
            }
        }
    }

    pub fn compact(&mut self) -> bool {
        for i in 0..self.levels.len() {
            if !self.levels[i].is_empty() {
                self.merge_level(i);
                self.cascade();
                return true;
            }
        }
        false
    }

    pub fn compact_all(&mut self) -> bool {
        let mut runs: Vec<Run> = Vec::new();
        for level in self.levels.iter_mut().rev() {
            runs.append(level);
        }
        if runs.is_empty() {
            return false;
        }
        let mut merged = Entries::new();
        for run in &runs {
            for (key, v) in &run.entries {
                merged.insert(key.clone(), v.clone());
            }
        }
        merged.retain(|_, v| v.is_some());
        let last = self.levels.len() - 1;
        if merged.is_empty() {
            self.say(format!("compact all ({} runs) -> nothing", runs.len()));
        } else {
            let r = Run::new(self.next_id, merged);
            self.next_id += 1;
            self.say(format!("compact all ({} runs) -> L{} run #{} ({} entries)", runs.len(), last, r.id, r.entries.len()));
            self.levels[last].push(r);
        }
        true
    }

    pub fn lookup(&self, key: &str) -> Lookup {
        if let Some(v) = self.mem.get(key) {
            return match v {
                Some(s) => Lookup::Live(s.clone(), "memtable".to_string(), 0),
                None => Lookup::Deleted("memtable".to_string(), 0),
            };
        }
        let mut probed = 0;
        for (i, level) in self.levels.iter().enumerate() {
            for run in level.iter().rev() {
                if config::RANGE_FILTER && !(run.lo.as_str() <= key && key <= run.hi.as_str()) {
                    continue;
                }
                probed += 1;
                if let Some(v) = run.entries.get(key) {
                    let src = format!("L{} #{}", i, run.id);
                    return match v {
                        Some(s) => Lookup::Live(s.clone(), src, probed),
                        None => Lookup::Deleted(src, probed),
                    };
                }
            }
        }
        Lookup::Missing(probed)
    }

    /// All live keys with their values (newest version wins).
    pub fn view(&self) -> BTreeMap<String, String> {
        let mut seen: Entries = Entries::new();
        for (k, v) in &self.mem {
            seen.insert(k.clone(), v.clone());
        }
        for level in &self.levels {
            for run in level.iter().rev() {
                for (k, v) in &run.entries {
                    seen.entry(k.clone()).or_insert_with(|| v.clone());
                }
            }
        }
        seen.into_iter().filter_map(|(k, v)| v.map(|s| (k, s))).collect()
    }

    pub fn stats(&self) -> (usize, usize, usize, usize) {
        let runs: usize = self.levels.iter().map(|l| l.len()).sum();
        let entries: usize = self.levels.iter().flatten().map(|r| r.entries.len()).sum();
        let tombs: usize = self.levels.iter().flatten().map(|r| r.entries.values().filter(|v| v.is_none()).count()).sum();
        (runs, entries, tombs, self.view().len())
    }
}
