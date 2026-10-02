//! Versions and constraints.
use crate::config;

pub fn is_name(s: &str) -> bool {
    let b = s.as_bytes();
    !b.is_empty() && b[0].is_ascii_lowercase() && b.iter().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == b'-')
}

fn parse_num(s: &str) -> Option<u64> {
    if s.is_empty() || s.len() > 6 || !s.bytes().all(|c| c.is_ascii_digit()) || (s.len() > 1 && s.starts_with('0')) {
        return None;
    }
    s.parse().ok()
}

/// A tag is letters followed by digits.
fn is_tag(s: &str) -> bool {
    let letters = s.bytes().take_while(|c| c.is_ascii_lowercase()).count();
    letters > 0 && s.bytes().skip(letters).all(|c| c.is_ascii_digit())
}

#[derive(Clone, Debug)]
pub struct Version {
    pub text: String,
    pub nums: (u64, u64, u64),
    pub tag: Option<String>,
}

/// Total order of versions: the numbers, then "no tag" above any tag, then the tag text.
pub type Key = ((u64, u64, u64), u8, String);

impl Version {
    /// `N.N.N` or `N.N.N-tag`.
    pub fn parse(text: &str) -> Option<Version> {
        let (num_part, tag) = match text.split_once('-') {
            Some((a, t)) => (a, Some(t)),
            None => (text, None),
        };
        if let Some(t) = tag {
            if !config::TAGS || !is_tag(t) {
                return None;
            }
        }
        let parts: Vec<&str> = num_part.split('.').collect();
        if parts.len() != 3 {
            return None;
        }
        let n: Vec<u64> = parts.iter().filter_map(|p| parse_num(p)).collect();
        if n.len() != 3 {
            return None;
        }
        Some(Version { text: text.to_string(), nums: (n[0], n[1], n[2]), tag: tag.map(|t| t.to_string()) })
    }

    pub fn key(&self) -> Key {
        (self.nums, if self.tag.is_none() { 1 } else { 0 }, self.tag.clone().unwrap_or_default())
    }
}

impl PartialEq for Version {
    fn eq(&self, other: &Version) -> bool {
        self.key() == other.key()
    }
}

/// `1`, `1.2`, `1.2.3`, `1.2.3-rc1`: missing numbers are 0; a tag needs all three numbers.
fn parse_partial(text: &str) -> Option<Version> {
    let (num_part, tag) = match text.split_once('-') {
        Some((a, t)) => (a, Some(t)),
        None => (text, None),
    };
    let parts: Vec<&str> = num_part.split('.').collect();
    if parts.is_empty() || parts.len() > 3 {
        return None;
    }
    let mut n = Vec::new();
    for p in &parts {
        n.push(parse_num(p)?);
    }
    if tag.is_some() && (parts.len() != 3 || !config::TAGS) {
        return None;
    }
    if let Some(t) = tag {
        if !is_tag(t) {
            return None;
        }
    }
    while n.len() < 3 {
        n.push(0);
    }
    let mut full = format!("{}.{}.{}", n[0], n[1], n[2]);
    if let Some(t) = tag {
        full = format!("{}-{}", full, t);
    }
    Version::parse(&full)
}

fn upper_bound(op: &str, v: &Version) -> (u64, u64, u64) {
    let (maj, min, pat) = v.nums;
    if op == "~" {
        return (maj, min + 1, 0);
    }
    if maj > 0 || !config::CARET_ZERO {
        return (maj + 1, 0, 0);
    }
    if min > 0 {
        return (0, min + 1, 0);
    }
    (0, 0, pat + 1)
}

#[derive(Clone, Debug)]
pub struct Constraint {
    pub text: String,
    clauses: Vec<(String, Option<Version>)>,
}

impl Constraint {
    pub fn parse(text: &str) -> Option<Constraint> {
        let mut clauses = Vec::new();
        for part in text.split(',') {
            clauses.push(parse_clause(part)?);
        }
        Some(Constraint { text: text.to_string(), clauses })
    }

    pub fn allows(&self, ver: &Version) -> bool {
        let k = ver.key();
        for (op, v) in &self.clauses {
            let v = match v {
                Some(v) => v,
                None => continue,
            };
            let vk = v.key();
            let ok = match op.as_str() {
                ">=" => k >= vk,
                ">" => k > vk,
                "<=" => k <= vk,
                "<" => k < vk,
                "=" => k == vk,
                "!=" => k != vk,
                _ => k >= vk && ver.nums < upper_bound(op, v),
            };
            if !ok {
                return false;
            }
        }
        true
    }
}

fn parse_clause(part: &str) -> Option<(String, Option<Version>)> {
    if part == "*" {
        return if config::OPS.contains(&"*") { Some(("*".to_string(), None)) } else { None };
    }
    for op in [">=", "<=", "!=", ">", "<", "=", "^", "~"] {
        if let Some(rest) = part.strip_prefix(op) {
            let v = parse_partial(rest)?;
            if !config::OPS.contains(&op) {
                return None;
            }
            return Some((op.to_string(), Some(v)));
        }
    }
    Some(("=".to_string(), Some(parse_partial(part)?)))
}
