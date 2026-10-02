"""Plugin dependency resolver: manifests with version constraints, conflicts, ordering hints; deterministic backtracking and load order."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

NAMES = ["core", "render", "audio", "net", "ui", "theme", "cache", "log", "auth", "store", "sync", "plot", "export", "search", "i18n", "crypto", "zip", "mail", "cron", "scene"]
HOSTS = ["the Quillfeather game engine", "the Saltmarsh dashboard", "a lighthouse control panel", "the Hollin kiosk shell", "the tide-clock firmware", "a ferry booking portal"]
LANG_PLAN = ["java", "rust", "go", "python", "java", "rust", "go", "java", "rust", "go"]


def vtxt(v):
    return ".".join(map(str, v))


def params(rng, level, i):
    return {"level": level, "host": rng.choice(HOSTS), "conflicts": level >= 4, "after": level >= 5, "reqcons": level >= 5,
            "ops": [">=", "<", "=", "*"] if level <= 3 else [">=", "<", "=", "*", "^", "~", ">", "<="]}


PY = r'''
HAS_CONFLICTS = @CONFLICTS@
HAS_AFTER = @AFTER@
HAS_REQCONS = @REQCONS@
OPS = @OPS_PY@
DG = "0123456789"
LOW = "abcdefghijklmnopqrstuvwxyz"


def digits(s, lo, hi):
    return lo <= len(s) <= hi and all(c in DG for c in s)


def valid_name(s):
    return 1 <= len(s) <= 16 and s[0] in LOW and all(c in LOW + DG + "-" for c in s)


def parse_version(s):
    parts = s.split(".")
    if len(parts) != 3:
        return None
    out = []
    for p in parts:
        if not digits(p, 1, 4) or (len(p) > 1 and p[0] == "0"):
            return None
        out.append(int(p))
    return tuple(out)


def parse_cons(s):
    if s == "*" and "*" in OPS:
        return ("*", None)
    for op in (">=", "<=", "=", ">", "<", "^", "~"):
        if s.startswith(op) and op in OPS:
            v = parse_version(s[len(op):])
            return (op, v) if v else None
    return None


def sat(v, c):
    op, w = c
    if op == "*":
        return True
    if op == "=":
        return v == w
    if op == ">=":
        return v >= w
    if op == ">":
        return v > w
    if op == "<=":
        return v <= w
    if op == "<":
        return v < w
    if op == "^":
        return v[0] == w[0] and v >= w
    return v[0] == w[0] and v[1] == w[1] and v >= w


def parse_registry(text):
    reg = {}
    cur = None
    for no, raw in enumerate(text.split("\n"), 1):
        w = raw.split("#", 1)[0].split()
        if not w:
            continue
        k = w[0]
        def err(m):
            return "error: line %d: %s" % (no, m)
        if k == "plugin":
            if len(w) != 3:
                return None, err("bad directive")
            if not valid_name(w[1]):
                return None, err("bad name")
            v = parse_version(w[2])
            if v is None:
                return None, err("bad version")
            if v in reg.get(w[1], {}):
                return None, err("duplicate plugin")
            reg.setdefault(w[1], {})[v] = {"requires": [], "conflicts": [], "after": []}
            cur = reg[w[1]][v]
        elif k in ("requires", "conflicts", "after") and (k == "requires" or (k == "conflicts" and HAS_CONFLICTS) or (k == "after" and HAS_AFTER)):
            if cur is None:
                return None, err("outside plugin")
            if k == "after":
                if len(w) != 2:
                    return None, err("bad directive")
                if not valid_name(w[1]):
                    return None, err("bad name")
                cur["after"].append(w[1])
                continue
            if len(w) not in (2, 3):
                return None, err("bad directive")
            if not valid_name(w[1]):
                return None, err("bad name")
            c = parse_cons(w[2]) if len(w) == 3 else ("*", None) if "*" in OPS else None
            if c is None:
                return None, err("bad constraint")
            cur[k].append((w[1], c))
        else:
            return None, err("unknown directive")
    return reg, None


def solve(reg, chosen, queue):
    if not queue:
        return chosen
    (name, cons), rest = queue[0], queue[1:]
    if name in chosen:
        return solve(reg, chosen, rest) if sat(chosen[name], cons) else None
    cands = sorted((v for v in reg.get(name, {}) if sat(v, cons)), reverse=True)
    for v in cands:
        meta = reg[name][v]
        bad = False
        for other, c in meta["conflicts"]:
            if other in chosen and sat(chosen[other], c):
                bad = True
        for other, ver in chosen.items():
            for n2, c in reg[other][ver]["conflicts"]:
                if n2 == name and sat(v, c):
                    bad = True
        if bad:
            continue
        nc = dict(chosen)
        nc[name] = v
        res = solve(reg, nc, rest + list(meta["requires"]))
        if res is not None:
            return res
    return None


def plan(manifests, request):
    reg, err = parse_registry(manifests)
    if err:
        return err
    queue = []
    for tok in request.split():
        name, _, cs = tok.partition("@")
        if not valid_name(name) or ("@" in tok and not HAS_REQCONS):
            return "error: bad request " + tok
        c = ("*", None)
        if "@" in tok:
            c = parse_cons(cs)
            if c is None:
                return "error: bad request " + tok
        if name not in reg:
            return "error: unknown plugin " + name
        queue.append((name, c))
    chosen = solve(reg, {}, queue)
    if chosen is None:
        return "error: no solution"
    # load order
    before = {n: set() for n in chosen}
    for n, v in chosen.items():
        for r, _ in reg[n][v]["requires"]:
            before[n].add(r)
        for a in reg[n][v]["after"]:
            if a in chosen:
                before[n].add(a)
    done = []
    remaining = set(chosen)
    while remaining:
        ready = sorted(n for n in remaining if all(b in done for b in before[n]))
        if not ready:
            return "error: cycle"
        done.append(ready[0])
        remaining.discard(ready[0])
    return "\n".join("load %s %s" % (n, ".".join(map(str, chosen[n]))) for n in done)
'''

GO = r'''
package plugins

import (
	"fmt"
	"sort"
	"strconv"
	"strings"
)

const (
	hasConflicts = @CONFLICTS@
	hasAfter     = @AFTER@
	hasReqCons   = @REQCONS@
)

var ops = @OPS_GO@

type version [3]int

func less(a, b version) bool {
	for i := 0; i < 3; i++ {
		if a[i] != b[i] {
			return a[i] < b[i]
		}
	}
	return false
}

func ge(a, b version) bool { return !less(a, b) }

type cons struct {
	op string
	v  version
}

type dep struct {
	name string
	c    cons
}

type meta struct {
	requires, conflicts []dep
	after               []string
}

type registry map[string]map[version]*meta

func hasOp(op string) bool {
	for _, o := range ops {
		if o == op {
			return true
		}
	}
	return false
}

func digits(s string, lo, hi int) bool {
	if len(s) < lo || len(s) > hi {
		return false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	return true
}

func validName(s string) bool {
	if len(s) < 1 || len(s) > 16 || s[0] < 'a' || s[0] > 'z' {
		return false
	}
	for i := 0; i < len(s); i++ {
		c := s[i]
		if !((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-') {
			return false
		}
	}
	return true
}

func parseVersion(s string) (version, bool) {
	parts := strings.Split(s, ".")
	var v version
	if len(parts) != 3 {
		return v, false
	}
	for i, p := range parts {
		if !digits(p, 1, 4) || (len(p) > 1 && p[0] == '0') {
			return v, false
		}
		v[i], _ = strconv.Atoi(p)
	}
	return v, true
}

func parseCons(s string) (cons, bool) {
	if s == "*" && hasOp("*") {
		return cons{op: "*"}, true
	}
	for _, op := range []string{">=", "<=", "=", ">", "<", "^", "~"} {
		if strings.HasPrefix(s, op) && hasOp(op) {
			v, ok := parseVersion(s[len(op):])
			if !ok {
				return cons{}, false
			}
			return cons{op, v}, true
		}
	}
	return cons{}, false
}

func sat(v version, c cons) bool {
	w := c.v
	switch c.op {
	case "*":
		return true
	case "=":
		return v == w
	case ">=":
		return ge(v, w)
	case ">":
		return less(w, v)
	case "<=":
		return !less(w, v)
	case "<":
		return less(v, w)
	case "^":
		return v[0] == w[0] && ge(v, w)
	}
	return v[0] == w[0] && v[1] == w[1] && ge(v, w)
}

func parseRegistry(text string) (registry, string) {
	reg := registry{}
	var cur *meta
	for i, raw := range strings.Split(text, "\n") {
		no := i + 1
		if h := strings.IndexByte(raw, '#'); h >= 0 {
			raw = raw[:h]
		}
		w := strings.Fields(raw)
		if len(w) == 0 {
			continue
		}
		err := func(m string) string { return fmt.Sprintf("error: line %d: %s", no, m) }
		k := w[0]
		switch {
		case k == "plugin":
			if len(w) != 3 {
				return nil, err("bad directive")
			}
			if !validName(w[1]) {
				return nil, err("bad name")
			}
			v, ok := parseVersion(w[2])
			if !ok {
				return nil, err("bad version")
			}
			if _, dup := reg[w[1]][v]; dup {
				return nil, err("duplicate plugin")
			}
			if reg[w[1]] == nil {
				reg[w[1]] = map[version]*meta{}
			}
			cur = &meta{}
			reg[w[1]][v] = cur
		case k == "requires" || (k == "conflicts" && hasConflicts) || (k == "after" && hasAfter):
			if cur == nil {
				return nil, err("outside plugin")
			}
			if k == "after" {
				if len(w) != 2 {
					return nil, err("bad directive")
				}
				if !validName(w[1]) {
					return nil, err("bad name")
				}
				cur.after = append(cur.after, w[1])
				continue
			}
			if len(w) != 2 && len(w) != 3 {
				return nil, err("bad directive")
			}
			if !validName(w[1]) {
				return nil, err("bad name")
			}
			var c cons
			if len(w) == 3 {
				var ok bool
				c, ok = parseCons(w[2])
				if !ok {
					return nil, err("bad constraint")
				}
			} else if hasOp("*") {
				c = cons{op: "*"}
			} else {
				return nil, err("bad constraint")
			}
			if k == "requires" {
				cur.requires = append(cur.requires, dep{w[1], c})
			} else {
				cur.conflicts = append(cur.conflicts, dep{w[1], c})
			}
		default:
			return nil, err("unknown directive")
		}
	}
	return reg, ""
}

func solve(reg registry, chosen map[string]version, queue []dep) map[string]version {
	if len(queue) == 0 {
		return chosen
	}
	head, rest := queue[0], queue[1:]
	if v, ok := chosen[head.name]; ok {
		if sat(v, head.c) {
			return solve(reg, chosen, rest)
		}
		return nil
	}
	var cands []version
	for v := range reg[head.name] {
		if sat(v, head.c) {
			cands = append(cands, v)
		}
	}
	sort.Slice(cands, func(i, j int) bool { return less(cands[j], cands[i]) })
	for _, v := range cands {
		m := reg[head.name][v]
		bad := false
		for _, d := range m.conflicts {
			if ov, ok := chosen[d.name]; ok && sat(ov, d.c) {
				bad = true
			}
		}
		for other, ov := range chosen {
			for _, d := range reg[other][ov].conflicts {
				if d.name == head.name && sat(v, d.c) {
					bad = true
				}
			}
		}
		if bad {
			continue
		}
		nc := map[string]version{}
		for k2, v2 := range chosen {
			nc[k2] = v2
		}
		nc[head.name] = v
		nq := append(append([]dep{}, rest...), m.requires...)
		if res := solve(reg, nc, nq); res != nil {
			return res
		}
	}
	return nil
}

// Plan resolves a request against the manifests and prints the load order.
func Plan(manifests, request string) string {
	reg, errText := parseRegistry(manifests)
	if errText != "" {
		return errText
	}
	var queue []dep
	for _, tok := range strings.Fields(request) {
		name, cs, has := strings.Cut(tok, "@")
		if !validName(name) || (has && !hasReqCons) {
			return "error: bad request " + tok
		}
		c := cons{op: "*"}
		if has {
			var ok bool
			c, ok = parseCons(cs)
			if !ok {
				return "error: bad request " + tok
			}
		}
		if _, ok := reg[name]; !ok {
			return "error: unknown plugin " + name
		}
		queue = append(queue, dep{name, c})
	}
	chosen := solve(reg, map[string]version{}, queue)
	if chosen == nil {
		return "error: no solution"
	}
	before := map[string]map[string]bool{}
	for n, v := range chosen {
		before[n] = map[string]bool{}
		for _, d := range reg[n][v].requires {
			before[n][d.name] = true
		}
		for _, a := range reg[n][v].after {
			if _, ok := chosen[a]; ok {
				before[n][a] = true
			}
		}
	}
	done := map[string]bool{}
	var order []string
	for len(order) < len(chosen) {
		var ready []string
		for n := range chosen {
			if done[n] {
				continue
			}
			ok := true
			for b := range before[n] {
				if !done[b] {
					ok = false
				}
			}
			if ok {
				ready = append(ready, n)
			}
		}
		if len(ready) == 0 {
			return "error: cycle"
		}
		sort.Strings(ready)
		done[ready[0]] = true
		order = append(order, ready[0])
	}
	var out []string
	for _, n := range order {
		v := chosen[n]
		out = append(out, fmt.Sprintf("load %s %d.%d.%d", n, v[0], v[1], v[2]))
	}
	return strings.Join(out, "\n")
}
'''

RS = r'''
use std::collections::{BTreeMap, BTreeSet};

const HAS_CONFLICTS: bool = @CONFLICTS@;
const HAS_AFTER: bool = @AFTER@;
const HAS_REQCONS: bool = @REQCONS@;
const OPS: &[&str] = &@OPS_RS@;

type Version = (i64, i64, i64);

#[derive(Clone, Debug)]
struct Cons {
    op: String,
    v: Version,
}

#[derive(Clone, Debug)]
struct Dep {
    name: String,
    c: Cons,
}

#[derive(Default, Clone)]
struct Meta {
    requires: Vec<Dep>,
    conflicts: Vec<Dep>,
    after: Vec<String>,
}

type Registry = BTreeMap<String, BTreeMap<Version, Meta>>;

fn has_op(op: &str) -> bool {
    OPS.contains(&op)
}

fn digits(s: &str, lo: usize, hi: usize) -> bool {
    s.len() >= lo && s.len() <= hi && s.bytes().all(|c| c.is_ascii_digit())
}

fn valid_name(s: &str) -> bool {
    let b = s.as_bytes();
    !b.is_empty() && b.len() <= 16 && b[0].is_ascii_lowercase() && b.iter().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == b'-')
}

fn parse_version(s: &str) -> Option<Version> {
    let parts: Vec<&str> = s.split('.').collect();
    if parts.len() != 3 {
        return None;
    }
    let mut out = [0i64; 3];
    for (i, p) in parts.iter().enumerate() {
        if !digits(p, 1, 4) || (p.len() > 1 && p.starts_with('0')) {
            return None;
        }
        out[i] = p.parse().unwrap();
    }
    Some((out[0], out[1], out[2]))
}

fn parse_cons(s: &str) -> Option<Cons> {
    if s == "*" && has_op("*") {
        return Some(Cons { op: "*".to_string(), v: (0, 0, 0) });
    }
    for op in [">=", "<=", "=", ">", "<", "^", "~"] {
        if s.starts_with(op) && has_op(op) {
            return parse_version(&s[op.len()..]).map(|v| Cons { op: op.to_string(), v });
        }
    }
    None
}

fn sat(v: Version, c: &Cons) -> bool {
    let w = c.v;
    match c.op.as_str() {
        "*" => true,
        "=" => v == w,
        ">=" => v >= w,
        ">" => v > w,
        "<=" => v <= w,
        "<" => v < w,
        "^" => v.0 == w.0 && v >= w,
        _ => v.0 == w.0 && v.1 == w.1 && v >= w,
    }
}

fn parse_registry(text: &str) -> Result<Registry, String> {
    let mut reg: Registry = BTreeMap::new();
    let mut cur: Option<(String, Version)> = None;
    for (i, raw) in text.split('\n').enumerate() {
        let no = i + 1;
        let line = raw.split('#').next().unwrap_or("");
        let w: Vec<&str> = line.split_whitespace().collect();
        if w.is_empty() {
            continue;
        }
        let err = |m: &str| format!("error: line {}: {}", no, m);
        let k = w[0];
        if k == "plugin" {
            if w.len() != 3 {
                return Err(err("bad directive"));
            }
            if !valid_name(w[1]) {
                return Err(err("bad name"));
            }
            let v = parse_version(w[2]).ok_or_else(|| err("bad version"))?;
            let e = reg.entry(w[1].to_string()).or_default();
            if e.contains_key(&v) {
                return Err(err("duplicate plugin"));
            }
            e.insert(v, Meta::default());
            cur = Some((w[1].to_string(), v));
        } else if k == "requires" || (k == "conflicts" && HAS_CONFLICTS) || (k == "after" && HAS_AFTER) {
            let (cn, cv) = match &cur {
                Some(c) => c.clone(),
                None => return Err(err("outside plugin")),
            };
            if k == "after" {
                if w.len() != 2 {
                    return Err(err("bad directive"));
                }
                if !valid_name(w[1]) {
                    return Err(err("bad name"));
                }
                reg.get_mut(&cn).unwrap().get_mut(&cv).unwrap().after.push(w[1].to_string());
                continue;
            }
            if w.len() != 2 && w.len() != 3 {
                return Err(err("bad directive"));
            }
            if !valid_name(w[1]) {
                return Err(err("bad name"));
            }
            let c = if w.len() == 3 {
                parse_cons(w[2]).ok_or_else(|| err("bad constraint"))?
            } else if has_op("*") {
                Cons { op: "*".to_string(), v: (0, 0, 0) }
            } else {
                return Err(err("bad constraint"));
            };
            let m = reg.get_mut(&cn).unwrap().get_mut(&cv).unwrap();
            let d = Dep { name: w[1].to_string(), c };
            if k == "requires" {
                m.requires.push(d);
            } else {
                m.conflicts.push(d);
            }
        } else {
            return Err(err("unknown directive"));
        }
    }
    Ok(reg)
}

fn solve(reg: &Registry, chosen: &BTreeMap<String, Version>, queue: &[Dep]) -> Option<BTreeMap<String, Version>> {
    if queue.is_empty() {
        return Some(chosen.clone());
    }
    let head = &queue[0];
    let rest = &queue[1..];
    if let Some(v) = chosen.get(&head.name) {
        return if sat(*v, &head.c) { solve(reg, chosen, rest) } else { None };
    }
    let mut cands: Vec<Version> = match reg.get(&head.name) {
        Some(m) => m.keys().cloned().filter(|v| sat(*v, &head.c)).collect(),
        None => Vec::new(),
    };
    cands.sort();
    cands.reverse();
    for v in cands {
        let m = &reg[&head.name][&v];
        let mut bad = false;
        for d in &m.conflicts {
            if let Some(ov) = chosen.get(&d.name) {
                if sat(*ov, &d.c) {
                    bad = true;
                }
            }
        }
        for (other, ov) in chosen {
            for d in &reg[other][ov].conflicts {
                if d.name == head.name && sat(v, &d.c) {
                    bad = true;
                }
            }
        }
        if bad {
            continue;
        }
        let mut nc = chosen.clone();
        nc.insert(head.name.clone(), v);
        let mut nq: Vec<Dep> = rest.to_vec();
        nq.extend(m.requires.iter().cloned());
        if let Some(r) = solve(reg, &nc, &nq) {
            return Some(r);
        }
    }
    None
}

/// Resolves a request against the manifests and renders the load plan.
pub fn plan(manifests: &str, request: &str) -> String {
    let reg = match parse_registry(manifests) {
        Ok(r) => r,
        Err(e) => return e,
    };
    let mut queue: Vec<Dep> = Vec::new();
    for tok in request.split_whitespace() {
        let (name, cs, has) = match tok.find('@') {
            Some(i) => (&tok[..i], &tok[i + 1..], true),
            None => (tok, "", false),
        };
        if !valid_name(name) || (has && !HAS_REQCONS) {
            return format!("error: bad request {}", tok);
        }
        let mut c = Cons { op: "*".to_string(), v: (0, 0, 0) };
        if has {
            match parse_cons(cs) {
                Some(x) => c = x,
                None => return format!("error: bad request {}", tok),
            }
        }
        if !reg.contains_key(name) {
            return format!("error: unknown plugin {}", name);
        }
        queue.push(Dep { name: name.to_string(), c });
    }
    let chosen = match solve(&reg, &BTreeMap::new(), &queue) {
        Some(c) => c,
        None => return "error: no solution".to_string(),
    };
    let mut before: BTreeMap<&String, BTreeSet<String>> = BTreeMap::new();
    for (n, v) in &chosen {
        let mut set = BTreeSet::new();
        for d in &reg[n][v].requires {
            set.insert(d.name.clone());
        }
        for a in &reg[n][v].after {
            if chosen.contains_key(a) {
                set.insert(a.clone());
            }
        }
        before.insert(n, set);
    }
    let mut done: Vec<String> = Vec::new();
    while done.len() < chosen.len() {
        let next = chosen.keys().filter(|n| !done.contains(*n)).find(|n| before[*n].iter().all(|b| done.contains(b)));
        match next {
            Some(n) => done.push(n.clone()),
            None => return "error: cycle".to_string(),
        }
    }
    done.iter().map(|n| format!("load {} {}.{}.{}", n, chosen[n].0, chosen[n].1, chosen[n].2)).collect::<Vec<_>>().join("\n")
}
'''

JV = r'''
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

public class Plugins {
    static final boolean HAS_CONFLICTS = @CONFLICTS@;
    static final boolean HAS_AFTER = @AFTER@;
    static final boolean HAS_REQCONS = @REQCONS@;
    static final List<String> OPS = Arrays.asList(@OPS_JAVA@);

    static class Cons {
        String op;
        int[] v;
        Cons(String op, int[] v) { this.op = op; this.v = v; }
    }

    static class Dep {
        String name;
        Cons c;
        Dep(String name, Cons c) { this.name = name; this.c = c; }
    }

    static class Meta {
        List<Dep> requires = new ArrayList<>(), conflicts = new ArrayList<>();
        List<String> after = new ArrayList<>();
    }

    static int cmp(int[] a, int[] b) {
        for (int i = 0; i < 3; i++) if (a[i] != b[i]) return Integer.compare(a[i], b[i]);
        return 0;
    }

    static String key(int[] v) { return v[0] + "." + v[1] + "." + v[2]; }

    static boolean digits(String s, int lo, int hi) {
        if (s.length() < lo || s.length() > hi) return false;
        for (char c : s.toCharArray()) if (c < '0' || c > '9') return false;
        return true;
    }

    static boolean validName(String s) {
        if (s.isEmpty() || s.length() > 16 || s.charAt(0) < 'a' || s.charAt(0) > 'z') return false;
        for (char c : s.toCharArray()) if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-')) return false;
        return true;
    }

    static int[] parseVersion(String s) {
        String[] parts = s.split("\\.", -1);
        if (parts.length != 3) return null;
        int[] out = new int[3];
        for (int i = 0; i < 3; i++) {
            if (!digits(parts[i], 1, 4) || (parts[i].length() > 1 && parts[i].charAt(0) == '0')) return null;
            out[i] = Integer.parseInt(parts[i]);
        }
        return out;
    }

    static Cons parseCons(String s) {
        if (s.equals("*") && OPS.contains("*")) return new Cons("*", null);
        for (String op : new String[] { ">=", "<=", "=", ">", "<", "^", "~" }) {
            if (s.startsWith(op) && OPS.contains(op)) {
                int[] v = parseVersion(s.substring(op.length()));
                return v == null ? null : new Cons(op, v);
            }
        }
        return null;
    }

    static boolean sat(int[] v, Cons c) {
        int[] w = c.v;
        switch (c.op) {
            case "*": return true;
            case "=": return cmp(v, w) == 0;
            case ">=": return cmp(v, w) >= 0;
            case ">": return cmp(v, w) > 0;
            case "<=": return cmp(v, w) <= 0;
            case "<": return cmp(v, w) < 0;
            case "^": return v[0] == w[0] && cmp(v, w) >= 0;
            default: return v[0] == w[0] && v[1] == w[1] && cmp(v, w) >= 0;
        }
    }

    // name -> (version key -> [version, meta])
    static Map<String, TreeMap<String, Object[]>> reg;

    static String parseRegistry(String text) {
        reg = new HashMap<>();
        Meta cur = null;
        String[] lines = text.split("\n", -1);
        for (int i = 0; i < lines.length; i++) {
            int no = i + 1;
            String raw = lines[i];
            int h = raw.indexOf('#');
            if (h >= 0) raw = raw.substring(0, h);
            String t = raw.trim();
            if (t.isEmpty()) continue;
            String[] w = t.split("\\s+");
            String pre = "error: line " + no + ": ";
            String k = w[0];
            if (k.equals("plugin")) {
                if (w.length != 3) return pre + "bad directive";
                if (!validName(w[1])) return pre + "bad name";
                int[] v = parseVersion(w[2]);
                if (v == null) return pre + "bad version";
                TreeMap<String, Object[]> vs = reg.computeIfAbsent(w[1], x -> new TreeMap<>());
                if (vs.containsKey(key(v))) return pre + "duplicate plugin";
                cur = new Meta();
                vs.put(key(v), new Object[] { v, cur });
            } else if (k.equals("requires") || (k.equals("conflicts") && HAS_CONFLICTS) || (k.equals("after") && HAS_AFTER)) {
                if (cur == null) return pre + "outside plugin";
                if (k.equals("after")) {
                    if (w.length != 2) return pre + "bad directive";
                    if (!validName(w[1])) return pre + "bad name";
                    cur.after.add(w[1]);
                    continue;
                }
                if (w.length != 2 && w.length != 3) return pre + "bad directive";
                if (!validName(w[1])) return pre + "bad name";
                Cons c;
                if (w.length == 3) {
                    c = parseCons(w[2]);
                    if (c == null) return pre + "bad constraint";
                } else if (OPS.contains("*")) c = new Cons("*", null);
                else return pre + "bad constraint";
                (k.equals("requires") ? cur.requires : cur.conflicts).add(new Dep(w[1], c));
            } else return pre + "unknown directive";
        }
        return null;
    }

    static Meta meta(String name, int[] v) { return (Meta) reg.get(name).get(key(v))[1]; }

    static Map<String, int[]> solve(Map<String, int[]> chosen, List<Dep> queue, int from) {
        if (from >= queue.size()) return chosen;
        Dep head = queue.get(from);
        if (chosen.containsKey(head.name)) return sat(chosen.get(head.name), head.c) ? solve(chosen, queue, from + 1) : null;
        List<int[]> cands = new ArrayList<>();
        if (reg.containsKey(head.name)) for (Object[] e : reg.get(head.name).values()) if (sat((int[]) e[0], head.c)) cands.add((int[]) e[0]);
        Collections.sort(cands, (a, b) -> cmp(b, a));
        for (int[] v : cands) {
            Meta m = meta(head.name, v);
            boolean bad = false;
            for (Dep d : m.conflicts) if (chosen.containsKey(d.name) && sat(chosen.get(d.name), d.c)) bad = true;
            for (Map.Entry<String, int[]> e : chosen.entrySet())
                for (Dep d : meta(e.getKey(), e.getValue()).conflicts) if (d.name.equals(head.name) && sat(v, d.c)) bad = true;
            if (bad) continue;
            Map<String, int[]> nc = new HashMap<>(chosen);
            nc.put(head.name, v);
            List<Dep> nq = new ArrayList<>(queue.subList(from + 1, queue.size()));
            nq.addAll(m.requires);
            Map<String, int[]> res = solve(nc, nq, 0);
            if (res != null) return res;
        }
        return null;
    }

    public static String plan(String manifests, String request) {
        String err = parseRegistry(manifests);
        if (err != null) return err;
        List<Dep> queue = new ArrayList<>();
        String rq = request.trim();
        if (!rq.isEmpty()) {
            for (String tok : rq.split("\\s+")) {
                int at = tok.indexOf('@');
                String name = at >= 0 ? tok.substring(0, at) : tok;
                if (!validName(name) || (at >= 0 && !HAS_REQCONS)) return "error: bad request " + tok;
                Cons c = new Cons("*", null);
                if (at >= 0) {
                    c = parseCons(tok.substring(at + 1));
                    if (c == null) return "error: bad request " + tok;
                }
                if (!reg.containsKey(name)) return "error: unknown plugin " + name;
                queue.add(new Dep(name, c));
            }
        }
        Map<String, int[]> chosen = solve(new HashMap<>(), queue, 0);
        if (chosen == null) return "error: no solution";
        Map<String, Set<String>> before = new HashMap<>();
        for (Map.Entry<String, int[]> e : chosen.entrySet()) {
            Set<String> set = new HashSet<>();
            Meta m = meta(e.getKey(), e.getValue());
            for (Dep d : m.requires) set.add(d.name);
            for (String a : m.after) if (chosen.containsKey(a)) set.add(a);
            before.put(e.getKey(), set);
        }
        List<String> done = new ArrayList<>();
        while (done.size() < chosen.size()) {
            List<String> ready = new ArrayList<>();
            for (String n : chosen.keySet()) {
                if (done.contains(n)) continue;
                boolean ok = true;
                for (String b : before.get(n)) if (!done.contains(b)) ok = false;
                if (ok) ready.add(n);
            }
            if (ready.isEmpty()) return "error: cycle";
            Collections.sort(ready);
            done.add(ready.get(0));
        }
        StringBuilder out = new StringBuilder();
        for (String n : done) {
            if (out.length() > 0) out.append("\n");
            out.append("load ").append(n).append(" ").append(key(chosen.get(n)));
        }
        return out.toString();
    }
}
'''

SOURCES = {"python": PY, "go": GO, "rust": RS, "java": JV}


def _b(lang, v):
    if lang == "python":
        return "True" if v else "False"
    return "true" if v else "false"


def sol(lang, p):
    ops = p["ops"]
    return K.subst(SOURCES[lang], CONFLICTS=_b(lang, p["conflicts"]), AFTER=_b(lang, p["after"]), REQCONS=_b(lang, p["reqcons"]),
                   OPS_PY="[" + ", ".join(f'"{o}"' for o in ops) + "]", OPS_GO="[]string{" + ", ".join(f'"{o}"' for o in ops) + "}",
                   OPS_RS="[" + ", ".join(f'"{o}"' for o in ops) + "]", OPS_JAVA=", ".join(f'"{o}"' for o in ops)).lstrip("\n")


# ---------------------------------------------------------------------------------------------------------------

def readme(p, api, lang, examples):
    L = [f"# Plugin planner for {p['host']}", ""]
    L.append(f"{p['host'].capitalize()} loads its plugins in a fixed order. `plan(manifests, request)` reads the manifests of all available plugin versions, chooses one version of every plugin that is needed, "
             "and prints the order in which to load them. The choice rules are deterministic and spelled out here.")
    L.append("")
    L.append("## Manifests")
    L.append("")
    L.append("Lines are separated by `\\n` (numbered from 1). From a `#` to the end of a line is a comment. Words are separated by blanks (spaces, tabs); lines without words are ignored. A `plugin` line starts a block; the other directives belong to the *most recent* `plugin` line (indentation does not matter).")
    L.append("")
    L.append("* `plugin NAME VERSION`: declares one version of a plugin. The same plugin can be declared several times with different versions.")
    L.append("* `requires NAME [CONSTRAINT]`: this version needs another plugin, in a version that satisfies the constraint (default `*`, any version)." if "*" in p["ops"] else
             "* `requires NAME CONSTRAINT`: this version needs another plugin, in a version that satisfies the constraint (the constraint is mandatory).")
    if p["conflicts"]:
        L.append("* `conflicts NAME [CONSTRAINT]`: this version cannot be loaded together with a version of `NAME` that satisfies the constraint (default `*`).")
    if p["after"]:
        L.append("* `after NAME`: if `NAME` is loaded at all, it must be loaded before this plugin (it does **not** require it).")
    L.append("")
    L.append("A **name** is 1 to 16 characters: a lower-case ASCII letter, then lower-case letters, digits or `-`. A **version** is `MAJOR.MINOR.PATCH`: three numbers of 1 to 4 ASCII digits without leading zeros (`0` itself is fine), compared number by number. "
             "A **constraint** is one of: " + ", ".join(f"`{o}VERSION`" if o != "*" else "`*`" for o in p["ops"]) + " with no blank inside. Meaning, for a version `v` and the constraint's version `w`: "
             "`=` equal; `>=`, `>`, `<=`, `<` as usual" + ("; `^w`: same MAJOR as `w` and `v >= w`; `~w`: same MAJOR and MINOR as `w` and `v >= w`" if "^" in p["ops"] else "") + "; `*` any version.")
    L.append("")
    missing = [d for d, have in (("conflicts", p["conflicts"]), ("after", p["after"])) if not have]
    note = ""
    if missing:
        note = " (" + " and ".join(f"`{d}`" for d in missing) + (" do" if len(missing) > 1 else " does") + " not exist in this version, so they are unknown directives)"
    L.append("Problems in the manifests give `error: line N: REASON` for the first offending line: `unknown directive` (the first word is not one of the directives above" + note + "), "
             "`outside plugin` (a directive before the first `plugin` line), `bad directive` (wrong number of words), `bad name`, `bad version`, `bad constraint`, `duplicate plugin` (same name and version declared twice). "
             "On one line the checks run in the order: unknown directive, outside plugin, number of words, name, version/constraint, duplicate.")
    L.append("")
    L.append("## Request")
    L.append("")
    L.append("`request` lists the wanted plugins, separated by blanks: " + ("each word is `NAME` or `NAME@CONSTRAINT` (for example `render@>=2.0.0`)." if p["reqcons"] else "each word is a plain `NAME` (no `@`)."))
    L.append("The words are checked from left to right; the first problem is the result: `error: bad request WORD` (invalid name" + (" or constraint" if p["reqcons"] else ", or an `@`") + "), `error: unknown plugin NAME` (no manifest declares that name). "
             "An empty request has an empty plan: the result is the empty text.")
    L.append("")
    L.append("## Choosing versions")
    L.append("")
    L.append("The planner keeps a list of *chosen* versions (at most one per plugin) and a *queue* of pending needs `(name, constraint)`, initially the request in order. It works on the queue from the front:")
    L.append("")
    L.append("1. If the front need names a plugin that is already chosen: it is fine if the chosen version satisfies the constraint; otherwise this branch **fails**. Either way the need leaves the queue.")
    L.append("2. Otherwise the *candidates* are the declared versions that satisfy the constraint, from the **highest version to the lowest** (a plugin with no declared version has none). For each candidate in that order:")
    if p["conflicts"]:
        L.append("   * skip it if one of its own `conflicts` matches an already chosen plugin, or if an already chosen plugin has a `conflicts` entry that names this plugin and matches the candidate's version;")
    L.append("   * otherwise choose it, remove the need from the queue, **append** the candidate's `requires` needs (in manifest order) to the **end** of the queue and continue; "
             "if the continuation eventually fails, undo this choice and try the next candidate (plain chronological backtracking).")
    L.append("3. If no candidate works the branch fails. The queue being empty means success. The first success found is the answer. If every possibility fails the result is `error: no solution`.")
    L.append("")
    L.append("## Load order")
    L.append("")
    L.append("Among the chosen versions, each plugin has to come after every plugin it `requires`" + (" and after every *chosen* plugin named by one of its `after` lines" if p["after"] else "") + ". "
             "Produce the order by repeatedly emitting, among the plugins whose predecessors have all been emitted, the one with the **smallest name** (byte order). If at some point no plugin is ready (the requirements form a cycle, a plugin requiring itself included), the result is `error: cycle`.")
    L.append("")
    L.append("The result is one line `load NAME VERSION` per chosen plugin in load order, joined by `\\n` without a trailing newline.")
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    for (m, r), out in examples:
        L.append("Manifests:")
        L.append("")
        L.append(K.fence(m))
        L.append(f"Request: `{r}`")
        L.append("")
        L.append("Result:")
        L.append("")
        L.append(K.fence(out) if out else "(empty)\n")
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


def make_cases(rng, p, ns):
    ops = p["ops"]
    plan = ns["plan"]
    cases = []

    def cons_for(v):
        op = rng.choice(ops)
        if op == "*":
            return "*"
        return f"{op}{vtxt(v)}"

    def random_registry(nplug=None, with_cycles=False):
        n = nplug or rng.randrange(4, 9)
        names = rng.sample(NAMES, n)
        lines = []
        vers = {}
        for idx, nm in enumerate(names):
            vs = sorted({(rng.randrange(0, 3), rng.randrange(0, 4), rng.randrange(0, 4)) for _ in range(rng.randrange(1, 4))})
            vers[nm] = vs
        for idx, nm in enumerate(names):
            for v in vers[nm]:
                lines.append(f"plugin {nm} {vtxt(v)}")
                lower = names[:idx] if not with_cycles else names
                for _ in range(rng.randrange(0, 3)):
                    if not lower:
                        break
                    dep = rng.choice(lower)
                    if dep == nm and not with_cycles:
                        continue
                    target = rng.choice(vers[dep])
                    lines.append(f"  requires {dep}" + (f" {cons_for(target)}" if rng.random() < 0.8 or "*" not in ops else ""))
                if p["conflicts"] and rng.random() < 0.3 and idx > 0:
                    other = rng.choice(names[:idx])
                    lines.append(f"  conflicts {other} {cons_for(rng.choice(vers[other]))}")
                if p["after"] and rng.random() < 0.3 and n > 1:
                    lines.append(f"  after {rng.choice(names)}")
        return "\n".join(lines) + "\n", names, vers

    def req(names, vers, k=None):
        k = k or rng.randrange(1, 4)
        toks = []
        for nm in rng.sample(names, min(k, len(names))):
            if p["reqcons"] and rng.random() < 0.4:
                toks.append(f"{nm}@{cons_for(rng.choice(vers[nm]))}")
            else:
                toks.append(nm)
        return " ".join(toks)

    def add(m, r):
        cases.append((m, r))

    add("plugin core 1.0.0\nplugin core 1.2.0\nplugin ui 2.0.0\n  requires core >=1.1.0\n", "ui")
    m, names, vers = random_registry(5)
    add(m, req(names, vers, 2))
    m, names, vers = random_registry(6)
    add(m, req(names, vers, 2))
    nex = len(cases)
    for _ in range(12):
        m, names, vers = random_registry()
        add(m, req(names, vers))
    for _ in range(4):
        m, names, vers = random_registry(rng.randrange(7, 11))
        add(m, req(names, vers, 3))
    if p["level"] >= 5:
        for _ in range(4):
            m, names, vers = random_registry(rng.randrange(3, 6), with_cycles=True)
            add(m, req(names, vers, 2))
    # fixed scenarios
    add("plugin a 1.0.0\n", "")
    add("plugin a 1.0.0\n", "  ")
    add("", "")
    add("", "a")
    add("# nothing\n", "a")
    add("plugin a 1.0.0\n", "a")
    add("plugin a 1.0.0\n", "a a a")
    add("plugin a 1.0.0\nplugin a 2.0.0\nplugin a 1.5.0\n", "a")
    add("plugin a 1.0.0\nplugin a 2.0.0\nplugin a 1.5.0\n", "a b")
    add("plugin a 1.0.0\nplugin a 10.0.0\nplugin a 9.9.9\n", "a")
    add("plugin a 1.10.0\nplugin a 1.9.0\n", "a")
    add("plugin a 0.0.1\nplugin a 0.0.10\nplugin a 0.0.2\n", "a")
    add("plugin a 1.0.0\nplugin b 1.0.0\n  requires a\n", "b")
    add("plugin a 1.0.0\nplugin b 1.0.0\n  requires a\n", "b a")
    add("plugin a 1.0.0\nplugin b 1.0.0\n  requires a\n", "a b")
    add("plugin b 1.0.0\n  requires a\nplugin a 1.0.0\n", "b")
    add("plugin b 1.0.0\n  requires a\n", "b")
    add("plugin b 1.0.0\n  requires a\nplugin b 0.9.0\n", "b")
    add("plugin b 1.0.0\n  requires a\nplugin b 0.9.0\n  requires c\nplugin c 1.0.0\n", "b")
    add("plugin b 1.0.0\n  requires a\nplugin b 0.9.0\n  requires c\nplugin c 1.0.0\n", "b@<1.0.0" if p["reqcons"] else "b")
    # constraint semantics
    for c in ops:
        if c == "*":
            continue
        for base in ("1.2.3", "0.0.0", "2.0.0", "1.2.0"):
            add(f"plugin x 0.9.9\nplugin x 1.0.0\nplugin x 1.2.2\nplugin x 1.2.3\nplugin x 1.2.4\nplugin x 1.3.0\nplugin x 2.0.0\nplugin x 2.0.1\nplugin y 1.0.0\n  requires x {c}{base}\n", "y")
    add("plugin x 1.0.0\nplugin y 1.0.0\n  requires x\n", "y")
    add("plugin x 1.0.0\nplugin y 1.0.0\n  requires x *\n", "y")
    # backtracking
    add("plugin a 2.0.0\n  requires c >=2.0.0\nplugin a 1.0.0\n  requires c <2.0.0\nplugin c 1.5.0\nplugin b 1.0.0\n  requires c <2.0.0\n", "a b")
    add("plugin a 2.0.0\n  requires c >=2.0.0\nplugin a 1.0.0\n  requires c <2.0.0\nplugin c 1.5.0\nplugin c 2.5.0\nplugin b 1.0.0\n  requires c <2.0.0\n", "a b")
    add("plugin a 2.0.0\n  requires c >=2.0.0\nplugin a 1.0.0\n  requires c <2.0.0\nplugin c 1.5.0\nplugin c 2.5.0\nplugin b 1.0.0\n  requires c <2.0.0\n", "b a")
    add("plugin a 3.0.0\n  requires z\nplugin a 2.0.0\n  requires y\nplugin a 1.0.0\nplugin y 1.0.0\n", "a")
    add("plugin a 3.0.0\n  requires z\nplugin a 2.0.0\n  requires y\nplugin a 1.0.0\n", "a")
    add("plugin a 3.0.0\n  requires z\nplugin a 2.0.0\n  requires y\nplugin a 1.0.0\n", "a@>1.0.0" if p["reqcons"] else "a")
    add("plugin a 1.0.0\n  requires b >=2.0.0\nplugin b 1.0.0\n", "a")
    add("plugin a 1.0.0\n  requires b >=2.0.0\nplugin b 2.0.0\n  requires a >=2.0.0\n", "a")
    add("plugin a 1.0.0\n  requires b\nplugin b 2.0.0\n  requires a >=2.0.0\n", "a")
    add("plugin a 2.0.0\n  requires b\nplugin a 1.0.0\nplugin b 1.0.0\n  requires a <2.0.0\nplugin b 2.0.0\n  requires a >=2.0.0\n", "a")
    add("plugin a 2.0.0\n  requires b\nplugin a 1.0.0\nplugin b 1.0.0\n  requires a <2.0.0\nplugin b 2.0.0\n  requires a >=2.0.0\n", "b")
    add("plugin a 2.0.0\n  requires b >=2.0.0\nplugin b 2.0.0\n  requires c\nplugin b 1.0.0\nplugin c 1.0.0\n  requires a <2.0.0\nplugin a 1.0.0\n", "a")
    # deep chain and diamond
    chain = "".join(f"plugin p{i} 1.0.0\n  requires p{i + 1}\n" for i in range(8)) + "plugin p8 1.0.0\n"
    add(chain, "p0")
    add(chain, "p8 p0")
    diamond = "plugin top 1.0.0\n  requires l\n  requires r\nplugin l 1.0.0\n  requires base >=1.0.0\nplugin r 1.0.0\n  requires base <2.0.0\nplugin base 1.5.0\nplugin base 2.5.0\n"
    add(diamond, "top")
    add(diamond, "base top")
    add(diamond.replace("plugin base 1.5.0\n", ""), "top")
    # order ties
    add("plugin zed 1.0.0\nplugin alpha 1.0.0\nplugin mid 1.0.0\n  requires zed\n", "mid alpha")
    add("plugin zed 1.0.0\nplugin alpha 1.0.0\nplugin mid 1.0.0\n  requires zed\nplugin top 1.0.0\n  requires alpha\n  requires mid\n", "top")
    add("plugin b 1.0.0\nplugin a 1.0.0\n  requires b\nplugin c 1.0.0\n", "c a")
    add("plugin ab 1.0.0\nplugin a 1.0.0\nplugin a-b 1.0.0\nplugin a1 1.0.0\n", "ab a a-b a1")
    # cycles via requires
    add("plugin a 1.0.0\n  requires b\nplugin b 1.0.0\n  requires a\n", "a")
    add("plugin a 1.0.0\n  requires a\n", "a")
    add("plugin a 1.0.0\n  requires b\nplugin b 1.0.0\n  requires c\nplugin c 1.0.0\n  requires a\nplugin d 1.0.0\n", "d a")
    if p["conflicts"]:
        add("plugin a 1.0.0\n  conflicts b\nplugin b 1.0.0\n", "a b")
        add("plugin a 1.0.0\n  conflicts b\nplugin b 1.0.0\n", "b a")
        add("plugin a 1.0.0\n  conflicts b\nplugin b 1.0.0\n", "a")
        add("plugin a 1.0.0\n  conflicts b >=2.0.0\nplugin b 1.0.0\nplugin b 2.0.0\n", "a b")
        add("plugin a 1.0.0\n  conflicts b >=2.0.0\nplugin b 1.0.0\nplugin b 2.0.0\n", "b a")
        add("plugin a 1.0.0\n  conflicts b >=2.0.0\nplugin b 2.0.0\n", "b a")
        add("plugin a 1.0.0\n  conflicts b >=2.0.0\nplugin b 2.0.0\n", "a b")
        add("plugin a 2.0.0\n  conflicts c\nplugin a 1.0.0\nplugin b 1.0.0\n  requires c\nplugin c 1.0.0\n", "a b")
        add("plugin a 2.0.0\n  conflicts c\nplugin a 1.0.0\nplugin b 1.0.0\n  requires c\nplugin c 1.0.0\n", "b a")
        add("plugin a 2.0.0\n  requires c\n  conflicts c\nplugin a 1.0.0\nplugin c 1.0.0\n", "a")
        add("plugin a 1.0.0\n  conflicts a\n", "a")
        add("plugin a 1.0.0\n  conflicts a\nplugin a 0.5.0\n", "a")
        add("plugin a 2.0.0\n  requires d\nplugin a 1.0.0\n  requires e\nplugin d 1.0.0\n  conflicts e\nplugin e 1.0.0\nplugin f 1.0.0\n  requires e\n", "f a")
        add("plugin a 2.0.0\n  requires d\nplugin a 1.0.0\n  requires e\nplugin d 1.0.0\n  conflicts e\nplugin e 1.0.0\nplugin f 1.0.0\n  requires e\n", "a f")
        add("plugin a 1.0.0\n  conflicts b <2.0.0\nplugin b 1.0.0\nplugin b 2.0.0\nplugin c 1.0.0\n  requires b <2.0.0\n", "c a")
        add("plugin a 1.0.0\n  conflicts b <2.0.0\nplugin b 1.0.0\nplugin b 2.0.0\nplugin c 1.0.0\n  requires b <2.0.0\n", "a c")
        add("plugin a 1.0.0\n  conflicts zzz\n", "a")
        add("plugin a 1.0.0\n  conflicts\n", "a")
        add("plugin a 1.0.0\n  conflicts b c d\n", "a")
        add("plugin a 1.0.0\n  conflicts b >=x\n", "a")
    else:
        add("plugin a 1.0.0\n  conflicts b\nplugin b 1.0.0\n", "a")
    if p["after"]:
        add("plugin a 1.0.0\n  after b\nplugin b 1.0.0\n", "a b")
        add("plugin a 1.0.0\n  after b\nplugin b 1.0.0\n", "a")
        add("plugin a 1.0.0\n  after b\nplugin b 1.0.0\n", "b a")
        add("plugin a 1.0.0\n  after b\nplugin b 1.0.0\n  after a\n", "a b")
        add("plugin a 1.0.0\n  after a\n", "a")
        add("plugin a 1.0.0\n  after zzz\n", "a")
        add("plugin a 1.0.0\n  after b\nplugin b 1.0.0\n  requires c\nplugin c 1.0.0\n", "a b")
        add("plugin m 1.0.0\n  after z\n  after y\nplugin z 1.0.0\nplugin y 1.0.0\nplugin x 1.0.0\n", "m z y x")
        add("plugin a 1.0.0\n  after\n", "a")
        add("plugin a 1.0.0\n  after b c\n", "a")
        add("plugin a 1.0.0\n  after B\n", "a")
        add("plugin a 1.0.0\n  after b\nplugin a 2.0.0\n  after c\nplugin b 1.0.0\nplugin c 1.0.0\n", "a b c")
        add("plugin a 1.0.0\n  after b\nplugin a 2.0.0\n  after c\nplugin b 1.0.0\nplugin c 1.0.0\n", "a@<2.0.0 b c")
    else:
        add("plugin a 1.0.0\n  after b\nplugin b 1.0.0\n", "a")
    # request errors
    for r in ("a@", "@", "@>=1.0.0", "A", "1a", "a b@", "a@>=1", "a@>=1.0", "a@>=1.0.0.0", "a@x", "a@>=01.0.0", "a@*", "a@^1.0.0", "a@~1.0.0", "a@=1.0.0", "a@>1.0.0", "a@<=1.0.0", "a@<1.0.0", "a@>=1.0.0@x", "a @>=1.0.0", "zzz", "a zzz", "zzz a", "zzz A", "a-", "a_b", "a b!", "a\tb", "a\nb"):
        add("plugin a 1.0.0\nplugin b 1.0.0\n", r)
    add("plugin a 1.0.0\n", "a@>=1.0.0 zzz")
    add("plugin a 1.0.0\n", "a@>=2.0.0")
    add("plugin a 1.0.0\n", "a@>=2.0.0 zzz")
    add("plugin a 1.0.0\n", "a a@>=2.0.0")
    # manifest errors
    for m in ("plugin", "plugin a", "plugin a 1.0.0 extra", "plugin A 1.0.0", "plugin 1a 1.0.0", "plugin a 1.0", "plugin a 1.0.0.0", "plugin a 01.0.0", "plugin a 1.0.x", "plugin a v1.0.0", "plugin a 1.0.00",
              "plugin a 10000.0.0", "plugin a 1.0.0\nplugin a 1.0.0", "plugin a 1.0.0\nplugin b 1.0.0\nplugin a 1.0.0", "requires b\nplugin a 1.0.0", "bogus a 1.0.0", "Plugin a 1.0.0", "plugin a 1.0.0\nbogus",
              "plugin a 1.0.0\n  requires", "plugin a 1.0.0\n  requires b c d", "plugin a 1.0.0\n  requires B", "plugin a 1.0.0\n  requires b >=1", "plugin a 1.0.0\n  requires b ?1.0.0", "plugin a 1.0.0\n  requires b >= 1.0.0",
              "plugin a 1.0.0\n  requires b =1.0.0\n  requires c =x", "plugin a 1.0.0\n  requires 9b", "plugin a 1.0.0 # comment\n  # comment only\n\n  requires b # why\nplugin b 2.0.0", "\n\n  plugin a 1.0.0", "plugin a 1.0.0\n\tplugin b 1.0.0",
              "plugin a 1.0.0\n  requires b *", "plugin " + "x" * 17 + " 1.0.0", "plugin " + "x" * 16 + " 1.0.0", "plugin a-b 1.0.0", "plugin a--b 1.0.0", "plugin -a 1.0.0", "plugin a- 1.0.0"):
        add(m + "\n" if not m.endswith("\n") else m, "a")
    add("plugin a 1.0.0\nplugin a 0.1.0\nrequires x\n", "a")
    add("frobnicate\nplugin a 1.0.0\n", "a")
    add("plugin a 1.0.0\n  frobnicate\n", "a")
    add("plugin a 1.0.0\n  requires b >=1.0.0 extra\nplugin b 1.0.0\n", "a")
    if p["level"] >= 5:
        add("plugin a 1.0.0\n  requires b ^1.2.3\nplugin b 1.2.2\nplugin b 1.2.3\nplugin b 1.9.0\nplugin b 2.0.0\n", "a")
        add("plugin a 1.0.0\n  requires b ~1.2.3\nplugin b 1.2.2\nplugin b 1.2.3\nplugin b 1.2.9\nplugin b 1.3.0\n", "a")
        add("plugin a 1.0.0\n  requires b ^0.2.3\nplugin b 0.2.3\nplugin b 0.9.0\nplugin b 1.0.0\n", "a")
        add("plugin a 1.0.0\n  requires b ~0.0.3\nplugin b 0.0.3\nplugin b 0.0.9\nplugin b 0.1.0\n", "a")
    out, seen = [], set()
    for c in cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex


def prompt(rng, p, api, lang):
    where = api.where(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    feats = ["version constraints", "highest-version-first backtracking"] + (["conflicts"] if p["conflicts"] else []) + (["`after` ordering hints and cycle detection"] if p["after"] else [])
    ft = ", ".join(feats)
    opts = [
        f"{p['host'].capitalize()} needs a plugin planner: `{fn}(manifests, request)` in {ln} ({where}) chooses plugin versions and returns the load order. README.md fixes the search procedure exactly ({ft}), so any correct solution gives the same answers. {K.closer(rng)}",
        f"Please implement the plugin resolver from README.md in {ln}: `{fn}` in {where}. It must pick the same versions as the reference procedure, including when it has to backtrack, and report errors with the exact texts. Features: {ft}.",
        f"dependency resolver task ({ln}). function `{fn}`, file {where}. spec: README.md - {ft}. the order of the queue and of the candidates is part of the spec. {K.closer(rng)}",
        f"Task: write the load planner for {p['host']}. {ln}, `{fn}(manifests, request)`, {where}. See README.md for manifests, constraints, the choosing procedure and the load order.",
    ]
    return rng.choice(opts).strip()


@family("greenfield-plugins", category="greenfield", lang="mixed", kind="greenfield", n=10,
        summary="plugin planner: manifest parsing, version constraints, deterministic chronological backtracking, conflicts, ordering hints, cycle detection")
def gen(rng, n):
    levels = [3, 3, 4, 4, 4, 5, 5, 5, 3, 4]
    diffs = [3, 3, 4, 4, 4, 5, 5, 5, 3, 4]
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level, i)
        api = K.Api(mod="plugins", fn="plan", args=["manifests", "request"], arg_docs=["the manifests text", "the wanted plugins, separated by blanks"],
                    ret_doc="the load plan, or an `error: ...` text", doc="plugin dependency planner")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["plan"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=diffs[i % len(diffs)], slug=f"{i + 1:02d}-{lang}-l{level}", oracle=(None if lang == "python" else ns["plan"]),
            tags=["resolver", "backtracking", "parser"], notes={"level": level, "conflicts": p["conflicts"], "after": p["after"]},
        )
