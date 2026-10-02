"""Port libraries about ordering: ranking with ties, dependency order, first-seen order, line diffs, grid regions."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

# ======================================================================================================================
# rank-ties: ranking with tie rules
# ======================================================================================================================

RT_SPEC = dd('''
    Ranking for a club league table. A higher score is better. Names are compared in **code point order** (a name that is
    a proper prefix of another sorts first); `names` and `scores` are parallel lists.

    * `rank_standard(scores)`: competition ranking, in input order: an entry's rank is `1 +` the number of strictly better
      scores, so ties share a rank and the next rank is skipped (`[90, 80, 80, 70]` gives `[1, 2, 2, 4]`).
    * `rank_dense(scores)`: `1 +` the number of **distinct** strictly better scores (`[90, 80, 80, 70]` gives `[1, 2, 2, 3]`).
    * `rank_mid2(scores)`: twice the average of the positions a tie group occupies, so that it is an integer: a group that fills
      positions `p..q` (1-based, positions are the standard ranks in order) gets `p + q` (`[90, 80, 80, 70]` gives `[2, 5, 5, 8]`).
    * `top_k(names, scores, k)`: the names of the `k` best entries. Order: score descending, then name ascending, then original
      index. `k` greater than the length returns everyone. `k < 0` or lists of different length is an error.
    * `table(names, scores)`: one line per entry in the same order as `top_k`: `<rank>. <name> (<score>)`, where `rank` is the
      standard rank and an entry that shares its score with another gets `=` right after the rank (`2=. bob (80)`). Different
      lengths are an error.
''')

RT_FNS = [
    Fn("rank_standard", [("scores", "list<int>")], "list<int>"),
    Fn("rank_dense", [("scores", "list<int>")], "list<int>"),
    Fn("rank_mid2", [("scores", "list<int>")], "list<int>"),
    Fn("top_k", [("names", "list<str>"), ("scores", "list<int>"), ("k", "int")], "list<str>", err=True),
    Fn("table", [("names", "list<str>"), ("scores", "list<int>")], "list<str>", err=True),
]

RT_PY = dd(r'''
def rank_standard(scores):
    return [1 + sum(1 for t in scores if t > s) for s in scores]


def rank_dense(scores):
    return [1 + len({t for t in scores if t > s}) for s in scores]


def rank_mid2(scores):
    out = []
    for s in scores:
        better = sum(1 for t in scores if t > s)
        same = sum(1 for t in scores if t == s)
        out.append((better + 1) + (better + same))
    return out


def _order(names, scores):
    if len(names) != len(scores):
        raise ValueError("length mismatch")
    return sorted(range(len(scores)), key=lambda i: (-scores[i], names[i], i))


def top_k(names, scores, k):
    if k < 0:
        raise ValueError("negative k")
    return [names[i] for i in _order(names, scores)[:k]]


def table(names, scores):
    out = []
    for i in _order(names, scores):
        better = sum(1 for t in scores if t > scores[i])
        tied = sum(1 for t in scores if t == scores[i]) > 1
        out.append("%d%s. %s (%d)" % (better + 1, "=" if tied else "", names[i], scores[i]))
    return out
''')

RT_GO = dd(r'''
package rankties

import (
	"errors"
	"fmt"
	"sort"
)

func better(scores []int64, s int64) int64 {
	var n int64
	for _, t := range scores {
		if t > s {
			n++
		}
	}
	return n
}

func RankStandard(scores []int64) []int64 {
	out := make([]int64, len(scores))
	for i, s := range scores {
		out[i] = 1 + better(scores, s)
	}
	return out
}

func RankDense(scores []int64) []int64 {
	out := make([]int64, len(scores))
	for i, s := range scores {
		seen := map[int64]bool{}
		for _, t := range scores {
			if t > s {
				seen[t] = true
			}
		}
		out[i] = 1 + int64(len(seen))
	}
	return out
}

func RankMid2(scores []int64) []int64 {
	out := make([]int64, len(scores))
	for i, s := range scores {
		b := better(scores, s)
		var same int64
		for _, t := range scores {
			if t == s {
				same++
			}
		}
		out[i] = (b + 1) + (b + same)
	}
	return out
}

func order(names []string, scores []int64) ([]int, error) {
	if len(names) != len(scores) {
		return nil, errors.New("length mismatch")
	}
	idx := make([]int, len(scores))
	for i := range idx {
		idx[i] = i
	}
	sort.SliceStable(idx, func(a, b int) bool {
		i, j := idx[a], idx[b]
		if scores[i] != scores[j] {
			return scores[i] > scores[j]
		}
		return names[i] < names[j]
	})
	return idx, nil
}

func TopK(names []string, scores []int64, k int64) ([]string, error) {
	if k < 0 {
		return nil, errors.New("negative k")
	}
	idx, err := order(names, scores)
	if err != nil {
		return nil, err
	}
	out := []string{}
	for _, i := range idx {
		if int64(len(out)) >= k {
			break
		}
		out = append(out, names[i])
	}
	return out, nil
}

func Table(names []string, scores []int64) ([]string, error) {
	idx, err := order(names, scores)
	if err != nil {
		return nil, err
	}
	out := []string{}
	for _, i := range idx {
		same := 0
		for _, t := range scores {
			if t == scores[i] {
				same++
			}
		}
		mark := ""
		if same > 1 {
			mark = "="
		}
		out = append(out, fmt.Sprintf("%d%s. %s (%d)", 1+better(scores, scores[i]), mark, names[i], scores[i]))
	}
	return out, nil
}
''')

RT_JAVA = dd(r'''
import java.util.*;

public final class RankTies {
    private RankTies() {}

    private static long better(List<Long> scores, long s) {
        long n = 0;
        for (long t : scores) if (t > s) n++;
        return n;
    }

    public static List<Long> rankStandard(List<Long> scores) {
        List<Long> out = new ArrayList<>();
        for (long s : scores) out.add(1 + better(scores, s));
        return out;
    }

    public static List<Long> rankDense(List<Long> scores) {
        List<Long> out = new ArrayList<>();
        for (long s : scores) {
            Set<Long> seen = new HashSet<>();
            for (long t : scores) if (t > s) seen.add(t);
            out.add(1L + seen.size());
        }
        return out;
    }

    public static List<Long> rankMid2(List<Long> scores) {
        List<Long> out = new ArrayList<>();
        for (long s : scores) {
            long b = better(scores, s);
            long same = 0;
            for (long t : scores) if (t == s) same++;
            out.add((b + 1) + (b + same));
        }
        return out;
    }

    // code point order, unlike String.compareTo (UTF-16 code units)
    private static int cmpPoints(String a, String b) {
        int[] x = a.codePoints().toArray();
        int[] y = b.codePoints().toArray();
        int n = Math.min(x.length, y.length);
        for (int i = 0; i < n; i++) {
            if (x[i] != y[i]) return x[i] < y[i] ? -1 : 1;
        }
        return Integer.compare(x.length, y.length);
    }

    private static Integer[] order(List<String> names, List<Long> scores) {
        if (names.size() != scores.size()) throw new IllegalArgumentException("length mismatch");
        Integer[] idx = new Integer[scores.size()];
        for (int i = 0; i < idx.length; i++) idx[i] = i;
        Arrays.sort(idx, (i, j) -> {
            int c = Long.compare(scores.get(j), scores.get(i));
            if (c != 0) return c;
            c = cmpPoints(names.get(i), names.get(j));
            return c != 0 ? c : Integer.compare(i, j);
        });
        return idx;
    }

    public static List<String> topK(List<String> names, List<Long> scores, long k) {
        if (k < 0) throw new IllegalArgumentException("negative k");
        Integer[] idx = order(names, scores);
        List<String> out = new ArrayList<>();
        for (int i = 0; i < idx.length && i < k; i++) out.add(names.get(idx[i]));
        return out;
    }

    public static List<String> table(List<String> names, List<Long> scores) {
        List<String> out = new ArrayList<>();
        for (int i : order(names, scores)) {
            long s = scores.get(i);
            int same = 0;
            for (long t : scores) if (t == s) same++;
            out.add((1 + better(scores, s)) + (same > 1 ? "=" : "") + ". " + names.get(i) + " (" + s + ")");
        }
        return out;
    }
}
''')


def rt_cases(rng):
    names_pool = ["ann", "bob", "cy", "Zed", "zed", "\u00e9mile", "emile", "\uff5eode", "\U0001F600fan", "al", "alb", "", "a b", "\u4e2d", "\U00010000"]
    out = [("rank_standard", [[90, 80, 80, 70]]), ("rank_dense", [[90, 80, 80, 70]]), ("rank_mid2", [[90, 80, 80, 70]]), ("top_k", [["a", "b", "c"], [3, 5, 5], 2]), ("table", [["ann", "bob", "cy"], [7, 5, 5]])]
    for sc in [[], [5], [5, 5], [1, 2, 3], [3, 2, 1], [2, 2, 2], [-1, 0, 0, -5], [10, 9, 9, 9, 8, 8, 7], [0, 0, 1], [100, 100, 50, 50, 50, 1]]:
        out.append(("rank_standard", [sc]))
        out.append(("rank_dense", [sc]))
        out.append(("rank_mid2", [sc]))
    for _ in range(15):
        sc = [rng.randint(-3, 6) for _ in range(rng.randint(0, 10))]
        out.append(("rank_standard", [sc]))
        out.append(("rank_dense", [sc]))
        out.append(("rank_mid2", [sc]))
    for _ in range(25):
        n = rng.randint(0, 9)
        names = [rng.choice(names_pool) for _ in range(n)]
        scores = [rng.randint(0, 4) for _ in range(n)]
        out.append(("top_k", [names, scores, rng.choice([0, 1, 2, 3, 5, 20])]))
        out.append(("table", [names, scores]))
    for names, scores in [(["\uff5e", "\U0001F600"], [1, 1]), (["\U0001F600", "\uff5e"], [1, 1]), (["b", "B", "a", "A"], [2, 2, 2, 2]), (["x", "x", "x"], [1, 1, 1]), (["", "a"], [0, 0]), (["z", "y"], [1, 2])]:
        out.append(("top_k", [names, scores, 10]))
        out.append(("table", [names, scores]))
    out += [("top_k", [["a"], [1], -1]), ("top_k", [["a", "b"], [1], 1]), ("table", [["a"], []]), ("table", [[], [1]]), ("top_k", [[], [], 3]), ("table", [[], []])]
    return out


RT = PortLib(
    slug="rank-ties",
    title="league table ranking with ties",
    blurb="A community sports league publishes standings where tied teams share a rank, and the website, the mobile app and the export job must agree on every line.",
    spec=RT_SPEC,
    fns=RT_FNS,
    impls={"python": {"rank_ties.py": RT_PY}, "go": {"rankties.go": RT_GO}, "java": {"RankTies.java": RT_JAVA}},
    cases=rt_cases,
    difficulty=2,
    traps=["tie handling", "code point order vs UTF-16 order", "stable multi-key sort"],
    tags=["sorting", "ranking"],
    pairs=[("python", "go", "full"), ("go", "java", "full"), ("java", "python", "stub"), ("python", "java", "stub")],
)
register_port(RT, __name__)

# ======================================================================================================================
# plan-order: build steps with dependencies
# ======================================================================================================================

PO_SPEC = dd('''
    A build tool plans the order of steps. A step is a string `name:dep1,dep2` (a step without dependencies is `name:` or just
    `name`). Names and dependency names match `[a-z0-9][a-z0-9_.-]*`. The same dependency may be listed twice (it counts once). It is an
    error if a step name appears twice, a name or dependency is malformed (including an empty item such as `a:b,` or `a:,b`), a
    dependency is not the name of any step, or the steps contain a dependency **cycle** (a step that depends on itself counts).

    * `build_order(steps)`: all step names, every step after its dependencies; whenever several steps are ready, the one with
      the **smallest name** (plain character order) is taken first.
    * `layers(steps)`: layer `k` holds the steps whose longest dependency chain has length `k` (layer 0 has no dependencies);
      every layer is sorted by name; there are no empty layers. No steps gives no layers.
    * `blockers(steps, name)`: the names of all steps `name` depends on, directly or indirectly, sorted; unknown `name` is an error.
    * `ready_after(steps, done)`: the steps not in `done` whose dependencies are all in `done`, sorted. `done` may repeat a name;
      a name in `done` that is not a step is an error.
''')

PO_FNS = [
    Fn("build_order", [("steps", "list<str>")], "list<str>", err=True),
    Fn("layers", [("steps", "list<str>")], "list<list<str>>", err=True),
    Fn("blockers", [("steps", "list<str>"), ("name", "str")], "list<str>", err=True),
    Fn("ready_after", [("steps", "list<str>"), ("done", "list<str>")], "list<str>", err=True),
]

PO_PY = dd(r'''
import re

_NAME = re.compile(r"[a-z0-9][a-z0-9_.-]*")


def _parse(steps):
    deps = {}
    for s in steps:
        name, sep, rest = s.partition(":")
        if not _NAME.fullmatch(name) or name in deps:
            raise ValueError("bad or duplicate step")
        ds = []
        if rest != "":
            for d in rest.split(","):
                if not _NAME.fullmatch(d):
                    raise ValueError("bad dependency")
                if d not in ds:
                    ds.append(d)
        deps[name] = ds
    for ds in deps.values():
        for d in ds:
            if d not in deps:
                raise ValueError("unknown dependency")
    return deps


def build_order(steps):
    deps = _parse(steps)
    remaining = {n: set(ds) for n, ds in deps.items()}
    out = []
    while remaining:
        ready = sorted(n for n, ds in remaining.items() if not ds)
        if not ready:
            raise ValueError("cycle")
        out.append(ready[0])
        del remaining[ready[0]]
        for ds in remaining.values():
            ds.discard(ready[0])
    return out


def layers(steps):
    deps = _parse(steps)
    order = build_order(steps)
    depth = {}
    for n in order:
        depth[n] = 1 + max((depth[d] for d in deps[n]), default=-1)
    out = []
    for n in sorted(depth):
        while len(out) <= depth[n]:
            out.append([])
        out[depth[n]].append(n)
    return out


def blockers(steps, name):
    deps = _parse(steps)
    build_order(steps)
    if name not in deps:
        raise ValueError("unknown step")
    seen, stack = set(), list(deps[name])
    while stack:
        d = stack.pop()
        if d not in seen:
            seen.add(d)
            stack.extend(deps[d])
    return sorted(seen)


def ready_after(steps, done):
    deps = _parse(steps)
    build_order(steps)
    for d in done:
        if d not in deps:
            raise ValueError("unknown step in done")
    have = set(done)
    return sorted(n for n, ds in deps.items() if n not in have and all(d in have for d in ds))
''')

PO_GO = dd(r'''
package planorder

import (
	"errors"
	"sort"
	"strings"
)

var errBad = errors.New("planorder: bad input")

func validName(s string) bool {
	if s == "" {
		return false
	}
	for i := 0; i < len(s); i++ {
		c := s[i]
		alnum := (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')
		if i == 0 && !alnum {
			return false
		}
		if !alnum && c != '_' && c != '.' && c != '-' {
			return false
		}
	}
	return true
}

type plan struct {
	names []string
	deps  map[string][]string
}

func parse(steps []string) (*plan, error) {
	p := &plan{deps: map[string][]string{}}
	for _, s := range steps {
		name, rest, _ := strings.Cut(s, ":")
		if !validName(name) {
			return nil, errBad
		}
		if _, dup := p.deps[name]; dup {
			return nil, errBad
		}
		ds := []string{}
		if rest != "" {
			for _, d := range strings.Split(rest, ",") {
				if !validName(d) {
					return nil, errBad
				}
				dupDep := false
				for _, e := range ds {
					if e == d {
						dupDep = true
					}
				}
				if !dupDep {
					ds = append(ds, d)
				}
			}
		}
		p.deps[name] = ds
		p.names = append(p.names, name)
	}
	for _, ds := range p.deps {
		for _, d := range ds {
			if _, ok := p.deps[d]; !ok {
				return nil, errBad
			}
		}
	}
	return p, nil
}

func (p *plan) order() ([]string, error) {
	remaining := map[string]map[string]bool{}
	for n, ds := range p.deps {
		set := map[string]bool{}
		for _, d := range ds {
			set[d] = true
		}
		remaining[n] = set
	}
	out := []string{}
	for len(remaining) > 0 {
		var ready []string
		for n, ds := range remaining {
			if len(ds) == 0 {
				ready = append(ready, n)
			}
		}
		if len(ready) == 0 {
			return nil, errors.New("planorder: cycle")
		}
		sort.Strings(ready)
		pick := ready[0]
		out = append(out, pick)
		delete(remaining, pick)
		for _, ds := range remaining {
			delete(ds, pick)
		}
	}
	return out, nil
}

func BuildOrder(steps []string) ([]string, error) {
	p, err := parse(steps)
	if err != nil {
		return nil, err
	}
	return p.order()
}

func Layers(steps []string) ([][]string, error) {
	p, err := parse(steps)
	if err != nil {
		return nil, err
	}
	order, err := p.order()
	if err != nil {
		return nil, err
	}
	depth := map[string]int{}
	for _, n := range order {
		d := 0
		for _, dep := range p.deps[n] {
			if depth[dep]+1 > d {
				d = depth[dep] + 1
			}
		}
		depth[n] = d
	}
	names := append([]string(nil), p.names...)
	sort.Strings(names)
	out := [][]string{}
	for _, n := range names {
		for len(out) <= depth[n] {
			out = append(out, []string{})
		}
		out[depth[n]] = append(out[depth[n]], n)
	}
	return out, nil
}

func Blockers(steps []string, name string) ([]string, error) {
	p, err := parse(steps)
	if err != nil {
		return nil, err
	}
	if _, err := p.order(); err != nil {
		return nil, err
	}
	if _, ok := p.deps[name]; !ok {
		return nil, errBad
	}
	seen := map[string]bool{}
	stack := append([]string(nil), p.deps[name]...)
	for len(stack) > 0 {
		d := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if !seen[d] {
			seen[d] = true
			stack = append(stack, p.deps[d]...)
		}
	}
	out := []string{}
	for d := range seen {
		out = append(out, d)
	}
	sort.Strings(out)
	return out, nil
}

func ReadyAfter(steps []string, done []string) ([]string, error) {
	p, err := parse(steps)
	if err != nil {
		return nil, err
	}
	if _, err := p.order(); err != nil {
		return nil, err
	}
	have := map[string]bool{}
	for _, d := range done {
		if _, ok := p.deps[d]; !ok {
			return nil, errBad
		}
		have[d] = true
	}
	out := []string{}
	for _, n := range p.names {
		if have[n] {
			continue
		}
		ok := true
		for _, d := range p.deps[n] {
			if !have[d] {
				ok = false
			}
		}
		if ok {
			out = append(out, n)
		}
	}
	sort.Strings(out)
	return out, nil
}
''')

PO_RS = dd(r'''
use std::collections::{BTreeMap, BTreeSet};

fn valid_name(s: &str) -> bool {
    let b = s.as_bytes();
    if b.is_empty() {
        return false;
    }
    b.iter().enumerate().all(|(i, &c)| {
        let alnum = c.is_ascii_lowercase() || c.is_ascii_digit();
        if i == 0 { alnum } else { alnum || c == b'_' || c == b'.' || c == b'-' }
    })
}

fn parse(steps: &[String]) -> Result<BTreeMap<String, Vec<String>>, String> {
    let mut deps: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for s in steps {
        let (name, rest) = match s.split_once(':') {
            Some((a, b)) => (a, b),
            None => (s.as_str(), ""),
        };
        if !valid_name(name) || deps.contains_key(name) {
            return Err(format!("bad or duplicate step {:?}", name));
        }
        let mut ds: Vec<String> = Vec::new();
        if !rest.is_empty() {
            for d in rest.split(',') {
                if !valid_name(d) {
                    return Err(format!("bad dependency {:?}", d));
                }
                if !ds.iter().any(|e| e == d) {
                    ds.push(d.to_string());
                }
            }
        }
        deps.insert(name.to_string(), ds);
    }
    for ds in deps.values() {
        for d in ds {
            if !deps.contains_key(d) {
                return Err(format!("unknown dependency {:?}", d));
            }
        }
    }
    Ok(deps)
}

fn order(deps: &BTreeMap<String, Vec<String>>) -> Result<Vec<String>, String> {
    let mut remaining: BTreeMap<String, BTreeSet<String>> =
        deps.iter().map(|(n, ds)| (n.clone(), ds.iter().cloned().collect())).collect();
    let mut out = Vec::new();
    while !remaining.is_empty() {
        let pick = remaining.iter().find(|(_, ds)| ds.is_empty()).map(|(n, _)| n.clone());
        let pick = pick.ok_or("cycle")?;
        remaining.remove(&pick);
        for ds in remaining.values_mut() {
            ds.remove(&pick);
        }
        out.push(pick);
    }
    Ok(out)
}

pub fn build_order(steps: &[String]) -> Result<Vec<String>, String> {
    order(&parse(steps)?)
}

pub fn layers(steps: &[String]) -> Result<Vec<Vec<String>>, String> {
    let deps = parse(steps)?;
    let ord = order(&deps)?;
    let mut depth: BTreeMap<String, usize> = BTreeMap::new();
    for n in &ord {
        let d = deps[n].iter().map(|x| depth[x] + 1).max().unwrap_or(0);
        depth.insert(n.clone(), d);
    }
    let mut out: Vec<Vec<String>> = Vec::new();
    for (n, d) in &depth {
        while out.len() <= *d {
            out.push(Vec::new());
        }
        out[*d].push(n.clone());
    }
    Ok(out)
}

pub fn blockers(steps: &[String], name: &str) -> Result<Vec<String>, String> {
    let deps = parse(steps)?;
    order(&deps)?;
    let start = deps.get(name).ok_or("unknown step")?;
    let mut seen: BTreeSet<String> = BTreeSet::new();
    let mut stack: Vec<String> = start.clone();
    while let Some(d) = stack.pop() {
        if seen.insert(d.clone()) {
            stack.extend(deps[&d].iter().cloned());
        }
    }
    Ok(seen.into_iter().collect())
}

pub fn ready_after(steps: &[String], done: &[String]) -> Result<Vec<String>, String> {
    let deps = parse(steps)?;
    order(&deps)?;
    let mut have: BTreeSet<&str> = BTreeSet::new();
    for d in done {
        if !deps.contains_key(d) {
            return Err(format!("unknown step in done {:?}", d));
        }
        have.insert(d.as_str());
    }
    Ok(deps
        .iter()
        .filter(|(n, ds)| !have.contains(n.as_str()) && ds.iter().all(|d| have.contains(d.as_str())))
        .map(|(n, _)| n.clone())
        .collect())
}
''')


def po_cases(rng):
    base = ["compile:fetch,gen", "fetch", "gen:fetch", "test:compile", "lint:fetch", "package:compile,lint,test", "docs:gen"]
    out = [("build_order", [base]), ("layers", [base]), ("blockers", [base, "package"]), ("ready_after", [base, ["fetch", "gen"]])]
    sets = [
        [], ["a"], ["a:"], ["b", "a"], ["b:a", "a"], ["c:a,b", "b:a", "a"], ["z", "y", "x"], ["x:y", "y:z", "z"], ["a:b", "b:a"], ["a:a"], ["a:b", "b:c", "c:a"], ["a", "a"], ["a:b"], ["a:b,"], ["a:,b", "b"], ["A"], ["a b"], ["_a"], ["-a"], ["a.b-c_d"],
        ["a:b,b", "b"], [":a"], ["a::b"], ["a:b:c", "b", "c"], ["1:0", "0"], ["m:a,b,c,d", "a", "b", "c", "d"], ["a", "b:a", "c:a", "d:b,c", "e:d", "f:a", "g:f,e"], ["x1", "x10", "x2", "x:x1,x10,x2"],
        base, base + ["extra:package"], base[::-1], ["a:b", "b:c", "c:d", "d"], ["alpha:beta", "beta:gamma", "gamma:", "delta:beta,gamma", "eps"], ["\u00e9"], ["a:\u00e9"],
    ]
    for st in sets:
        out.append(("build_order", [st]))
        out.append(("layers", [st]))
    for st in sets:
        names = [s.split(":")[0] for s in st] or ["a"]
        out.append(("blockers", [st, rng.choice(names + ["nope"])]))
        out.append(("ready_after", [st, rng.sample(names, min(len(names), rng.randint(0, 3)))]))
    for st, nm in [(base, "fetch"), (base, "package"), (base, "docs"), (base, "test"), (base, "nope"), (base, ""), (["a:b", "b:a"], "a")]:
        out.append(("blockers", [st, nm]))
    for st, dn in [(base, []), (base, ["fetch"]), (base, ["fetch", "fetch"]), (base, ["fetch", "gen", "lint"]), (base, ["package"]), (base, ["nope"]), (base, list(n.split(":")[0] for n in base)), (["a:b", "b:a"], [])]:
        out.append(("ready_after", [st, dn]))
    for _ in range(15):
        n = rng.randint(2, 9)
        names = [f"s{i}" for i in range(n)]
        rng.shuffle(names)
        st = []
        for i, nm in enumerate(names):
            ds = [names[j] for j in range(i) if rng.random() < 0.35]
            st.append(nm + ":" + ",".join(ds))
        rng.shuffle(st)
        out.append(("build_order", [st]))
        out.append(("layers", [st]))
        out.append(("blockers", [st, rng.choice(names)]))
        out.append(("ready_after", [st, rng.sample(names, rng.randint(0, n))]))
    return out


PO = PortLib(
    slug="plan-order",
    title="build step ordering",
    blurb="A release tool plans the order of build steps from a flat list of `name:dependencies` entries and must produce byte-identical plans on every platform.",
    spec=PO_SPEC,
    fns=PO_FNS,
    impls={"go": {"planorder.go": PO_GO}, "rust": {"src/lib.rs": PO_RS}, "python": {"plan_order.py": PO_PY}},
    cases=po_cases,
    difficulty=3,
    traps=["hash map iteration order", "deterministic tie-breaking", "cycle detection", "strict names"],
    tags=["graphs", "topological-order"],
    pairs=[("go", "rust", "full"), ("rust", "python", "full"), ("python", "go", "stub"), ("go", "python", "stub")],
)
register_port(PO, __name__)

# ======================================================================================================================
# tally-order: counting and de-duplication that keeps first-seen order
# ======================================================================================================================

TO_SPEC = dd('''
    Order matters in these small collection helpers: results follow the order in which items were **first seen** in the input
    (items are compared as exact strings).

    * `tally(xs)`: one `item=count` string per distinct item, in first-seen order (`["b", "a", "b"]` gives `["b=2", "a=1"]`).
    * `top_tally(xs, k)`: the same `item=count` strings, sorted by count descending, equal counts in first-seen order, cut to the first
      `k`. `k < 0` is an error; a `k` larger than the number of distinct items returns them all.
    * `mode_all(xs)`: every item whose count equals the highest count, in first-seen order; empty input gives an empty list.
    * `drop_dupes(xs)`: each item once, at the position of its first occurrence.
    * `repeated(xs)`: the items that occur at least twice, each listed once, ordered by the position of their **second** occurrence.
    * `last_order(xs)`: the distinct items ordered by the position of their **last** occurrence.
''')

TO_FNS = [
    Fn("tally", [("xs", "list<str>")], "list<str>"),
    Fn("top_tally", [("xs", "list<str>"), ("k", "int")], "list<str>", err=True),
    Fn("mode_all", [("xs", "list<str>")], "list<str>"),
    Fn("drop_dupes", [("xs", "list<str>")], "list<str>"),
    Fn("repeated", [("xs", "list<str>")], "list<str>"),
    Fn("last_order", [("xs", "list<str>")], "list<str>"),
]

TO_PY = dd(r'''
def _counts(xs):
    counts = {}
    for x in xs:
        counts[x] = counts.get(x, 0) + 1
    return counts


def tally(xs):
    return ["%s=%d" % (k, v) for k, v in _counts(xs).items()]


def top_tally(xs, k):
    if k < 0:
        raise ValueError("negative k")
    counts = _counts(xs)
    items = sorted(counts, key=lambda x: -counts[x])
    return ["%s=%d" % (x, counts[x]) for x in items[:k]]


def mode_all(xs):
    counts = _counts(xs)
    if not counts:
        return []
    best = max(counts.values())
    return [x for x, c in counts.items() if c == best]


def drop_dupes(xs):
    return list(_counts(xs))


def repeated(xs):
    seen, out = set(), []
    again = set()
    for x in xs:
        if x in seen and x not in again:
            again.add(x)
            out.append(x)
        seen.add(x)
    return out


def last_order(xs):
    last = {x: i for i, x in enumerate(xs)}
    return sorted(last, key=lambda x: last[x])
''')

TO_GO = dd(r'''
package tallyorder

import (
	"errors"
	"fmt"
	"sort"
)

func counts(xs []string) ([]string, map[string]int) {
	var order []string
	m := map[string]int{}
	for _, x := range xs {
		if _, ok := m[x]; !ok {
			order = append(order, x)
		}
		m[x]++
	}
	return order, m
}

func Tally(xs []string) []string {
	order, m := counts(xs)
	out := []string{}
	for _, x := range order {
		out = append(out, fmt.Sprintf("%s=%d", x, m[x]))
	}
	return out
}

func TopTally(xs []string, k int64) ([]string, error) {
	if k < 0 {
		return nil, errors.New("negative k")
	}
	order, m := counts(xs)
	sort.SliceStable(order, func(i, j int) bool { return m[order[i]] > m[order[j]] })
	out := []string{}
	for _, x := range order {
		if int64(len(out)) >= k {
			break
		}
		out = append(out, fmt.Sprintf("%s=%d", x, m[x]))
	}
	return out, nil
}

func ModeAll(xs []string) []string {
	order, m := counts(xs)
	best := 0
	for _, c := range m {
		if c > best {
			best = c
		}
	}
	out := []string{}
	for _, x := range order {
		if m[x] == best {
			out = append(out, x)
		}
	}
	return out
}

func DropDupes(xs []string) []string {
	order, _ := counts(xs)
	if order == nil {
		return []string{}
	}
	return order
}

func Repeated(xs []string) []string {
	seen := map[string]bool{}
	again := map[string]bool{}
	out := []string{}
	for _, x := range xs {
		if seen[x] && !again[x] {
			again[x] = true
			out = append(out, x)
		}
		seen[x] = true
	}
	return out
}

func LastOrder(xs []string) []string {
	last := map[string]int{}
	for i, x := range xs {
		last[x] = i
	}
	out := []string{}
	for x := range last {
		out = append(out, x)
	}
	sort.Slice(out, func(i, j int) bool { return last[out[i]] < last[out[j]] })
	return out
}
''')

TO_RS = dd(r'''
use std::collections::{HashMap, HashSet};

fn counts(xs: &[String]) -> (Vec<String>, HashMap<String, i64>) {
    let mut order: Vec<String> = Vec::new();
    let mut m: HashMap<String, i64> = HashMap::new();
    for x in xs {
        let e = m.entry(x.clone()).or_insert(0);
        if *e == 0 {
            order.push(x.clone());
        }
        *e += 1;
    }
    (order, m)
}

pub fn tally(xs: &[String]) -> Vec<String> {
    let (order, m) = counts(xs);
    order.iter().map(|x| format!("{}={}", x, m[x])).collect()
}

pub fn top_tally(xs: &[String], k: i64) -> Result<Vec<String>, String> {
    if k < 0 {
        return Err("negative k".to_string());
    }
    let (mut order, m) = counts(xs);
    order.sort_by(|a, b| m[b].cmp(&m[a]));
    Ok(order.iter().take(k as usize).map(|x| format!("{}={}", x, m[x])).collect())
}

pub fn mode_all(xs: &[String]) -> Vec<String> {
    let (order, m) = counts(xs);
    let best = m.values().copied().max().unwrap_or(0);
    order.into_iter().filter(|x| m[x] == best).collect()
}

pub fn drop_dupes(xs: &[String]) -> Vec<String> {
    counts(xs).0
}

pub fn repeated(xs: &[String]) -> Vec<String> {
    let mut seen: HashSet<&String> = HashSet::new();
    let mut again: HashSet<&String> = HashSet::new();
    let mut out = Vec::new();
    for x in xs {
        if seen.contains(x) && !again.contains(x) {
            again.insert(x);
            out.push(x.clone());
        }
        seen.insert(x);
    }
    out
}

pub fn last_order(xs: &[String]) -> Vec<String> {
    let mut last: HashMap<&String, usize> = HashMap::new();
    for (i, x) in xs.iter().enumerate() {
        last.insert(x, i);
    }
    let mut items: Vec<&String> = last.keys().copied().collect();
    items.sort_by_key(|x| last[x]);
    items.into_iter().cloned().collect()
}
''')


def to_cases(rng):
    pool = ["a", "b", "c", "d", "e", "", "\u00e9", "\U0001F600", "x y", "A", "a=1"]
    out = [("tally", [["b", "a", "b"]]), ("top_tally", [["b", "a", "b", "c", "a"], 2]), ("mode_all", [["x", "y", "x", "y", "z"]]), ("drop_dupes", [["b", "a", "b"]]), ("repeated", [["a", "b", "a", "b", "a", "c"]]), ("last_order", [["a", "b", "a", "c"]])]
    fixed = [[], ["a"], ["a", "a"], ["a", "b"], ["b", "a", "b"], ["a", "b", "a", "b"], ["x", "y", "z", "z", "y", "x"], ["", "", "a"], ["a=1", "a", "1", "a=1"], ["\U0001F600", "\u00e9", "\U0001F600"], ["A", "a", "A"], ["q"] * 5, ["a", "b", "c", "a", "b", "c", "a"]]
    for xs in fixed:
        out.append(("tally", [xs]))
        out.append(("mode_all", [xs]))
        out.append(("drop_dupes", [xs]))
        out.append(("repeated", [xs]))
        out.append(("last_order", [xs]))
        for k in [0, 1, 2, 100]:
            out.append(("top_tally", [xs, k]))
    out.append(("top_tally", [["a"], -1]))
    for _ in range(25):
        xs = [rng.choice(pool[:rng.randint(2, 11)]) for _ in range(rng.randint(0, 14))]
        out.append(("tally", [xs]))
        out.append(("mode_all", [xs]))
        out.append(("drop_dupes", [xs]))
        out.append(("repeated", [xs]))
        out.append(("last_order", [xs]))
        out.append(("top_tally", [xs, rng.randint(0, 6)]))
    return out


TO = PortLib(
    slug="tally-order",
    title="order-preserving counting helpers",
    blurb="A log-analysis script counts and de-duplicates event names but its reports must list things in the order they first appeared.",
    spec=TO_SPEC,
    fns=TO_FNS,
    impls={"python": {"tally_order.py": TO_PY}, "go": {"tallyorder.go": TO_GO}, "rust": {"src/lib.rs": TO_RS}},
    cases=to_cases,
    difficulty=2,
    traps=["hash map iteration order", "stable sort", "empty list vs nil"],
    tags=["ordering", "maps"],
    pairs=[("python", "go", "full"), ("go", "rust", "full"), ("rust", "python", "stub"), ("python", "rust", "stub")],
)
register_port(TO, __name__)

# ======================================================================================================================
# diff-lines: line diff by longest common subsequence
# ======================================================================================================================

DL_SPEC = dd('''
    A line-based diff for a changelog tool. Lines are arbitrary strings (they may be empty or start with spaces).

    * `diff(a, b)` returns an **edit script**: a list of strings, each a one-character tag, a space and the line text:
      `"= text"` (line kept), `"- text"` (line only in `a`), `"+ text"` (line only in `b`). The script is built from the
      longest-common-subsequence table `L[i][j]` = length of the longest common subsequence of `a[i:]` and `b[j:]`. Walk from
      `i = 0, j = 0`: if both lines remain and `a[i] == b[j]`, emit `=` and advance both; otherwise if `b` is used up, or `a` has
      lines left and `L[i+1][j] >= L[i][j+1]`, emit `-` for `a[i]` and advance `i`; otherwise emit `+` for `b[j]` and advance `j`.
      (So deletions win ties.)
    * `apply_script(a, script)` replays a script on `a` and returns the resulting lines. Every entry needs a tag from `=-+`
      followed by a space (otherwise error); `=` and `-` entries must equal the next unread line of `a` (else error), `+` inserts text,
      and all of `a` must be consumed (else error).
    * `distance(a, b)` is the number of `-` and `+` entries of `diff(a, b)`.
    * `shared_ends(a, b)` returns `[p, s]`: the number of equal lines at the start, and then the number of equal lines at the end of
      what is left after removing that prefix (the two never overlap).
''')

DL_FNS = [
    Fn("diff", [("a", "list<str>"), ("b", "list<str>")], "list<str>"),
    Fn("apply_script", [("a", "list<str>"), ("script", "list<str>")], "list<str>", err=True),
    Fn("distance", [("a", "list<str>"), ("b", "list<str>")], "int"),
    Fn("shared_ends", [("a", "list<str>"), ("b", "list<str>")], "list<int>"),
]

DL_PY = dd(r'''
def _table(a, b):
    n, m = len(a), len(b)
    t = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            t[i][j] = t[i + 1][j + 1] + 1 if a[i] == b[j] else max(t[i + 1][j], t[i][j + 1])
    return t


def diff(a, b):
    t = _table(a, b)
    n, m = len(a), len(b)
    i = j = 0
    out = []
    while i < n or j < m:
        if i < n and j < m and a[i] == b[j]:
            out.append("= " + a[i])
            i += 1
            j += 1
        elif j == m or (i < n and t[i + 1][j] >= t[i][j + 1]):
            out.append("- " + a[i])
            i += 1
        else:
            out.append("+ " + b[j])
            j += 1
    return out


def apply_script(a, script):
    out, i = [], 0
    for entry in script:
        if len(entry) < 2 or entry[1] != " " or entry[0] not in "=-+":
            raise ValueError("bad script entry")
        tag, text = entry[0], entry[2:]
        if tag == "+":
            out.append(text)
            continue
        if i >= len(a) or a[i] != text:
            raise ValueError("script does not match")
        i += 1
        if tag == "=":
            out.append(text)
    if i != len(a):
        raise ValueError("script leaves lines unread")
    return out


def distance(a, b):
    return sum(1 for e in diff(a, b) if e[0] != "=")


def shared_ends(a, b):
    p = 0
    while p < len(a) and p < len(b) and a[p] == b[p]:
        p += 1
    s = 0
    while s < len(a) - p and s < len(b) - p and a[len(a) - 1 - s] == b[len(b) - 1 - s]:
        s += 1
    return [p, s]
''')

DL_GO = dd(r'''
package difflines

import "errors"

func table(a, b []string) [][]int {
	n, m := len(a), len(b)
	t := make([][]int, n+1)
	for i := range t {
		t[i] = make([]int, m+1)
	}
	for i := n - 1; i >= 0; i-- {
		for j := m - 1; j >= 0; j-- {
			if a[i] == b[j] {
				t[i][j] = t[i+1][j+1] + 1
			} else if t[i+1][j] >= t[i][j+1] {
				t[i][j] = t[i+1][j]
			} else {
				t[i][j] = t[i][j+1]
			}
		}
	}
	return t
}

func Diff(a, b []string) []string {
	t := table(a, b)
	n, m := len(a), len(b)
	i, j := 0, 0
	out := []string{}
	for i < n || j < m {
		switch {
		case i < n && j < m && a[i] == b[j]:
			out = append(out, "= "+a[i])
			i++
			j++
		case j == m || (i < n && t[i+1][j] >= t[i][j+1]):
			out = append(out, "- "+a[i])
			i++
		default:
			out = append(out, "+ "+b[j])
			j++
		}
	}
	return out
}

func ApplyScript(a, script []string) ([]string, error) {
	out := []string{}
	i := 0
	for _, e := range script {
		if len(e) < 2 || e[1] != ' ' || (e[0] != '=' && e[0] != '-' && e[0] != '+') {
			return nil, errors.New("bad script entry")
		}
		tag, text := e[0], e[2:]
		if tag == '+' {
			out = append(out, text)
			continue
		}
		if i >= len(a) || a[i] != text {
			return nil, errors.New("script does not match")
		}
		i++
		if tag == '=' {
			out = append(out, text)
		}
	}
	if i != len(a) {
		return nil, errors.New("script leaves lines unread")
	}
	return out, nil
}

func Distance(a, b []string) int64 {
	var n int64
	for _, e := range Diff(a, b) {
		if e[0] != '=' {
			n++
		}
	}
	return n
}

func SharedEnds(a, b []string) []int64 {
	p := 0
	for p < len(a) && p < len(b) && a[p] == b[p] {
		p++
	}
	s := 0
	for s < len(a)-p && s < len(b)-p && a[len(a)-1-s] == b[len(b)-1-s] {
		s++
	}
	return []int64{int64(p), int64(s)}
}
''')

DL_JAVA = dd(r'''
import java.util.*;

public final class DiffLines {
    private DiffLines() {}

    private static int[][] table(List<String> a, List<String> b) {
        int n = a.size(), m = b.size();
        int[][] t = new int[n + 1][m + 1];
        for (int i = n - 1; i >= 0; i--) {
            for (int j = m - 1; j >= 0; j--) {
                t[i][j] = a.get(i).equals(b.get(j)) ? t[i + 1][j + 1] + 1 : Math.max(t[i + 1][j], t[i][j + 1]);
            }
        }
        return t;
    }

    public static List<String> diff(List<String> a, List<String> b) {
        int[][] t = table(a, b);
        int n = a.size(), m = b.size(), i = 0, j = 0;
        List<String> out = new ArrayList<>();
        while (i < n || j < m) {
            if (i < n && j < m && a.get(i).equals(b.get(j))) {
                out.add("= " + a.get(i));
                i++;
                j++;
            } else if (j == m || (i < n && t[i + 1][j] >= t[i][j + 1])) {
                out.add("- " + a.get(i));
                i++;
            } else {
                out.add("+ " + b.get(j));
                j++;
            }
        }
        return out;
    }

    public static List<String> applyScript(List<String> a, List<String> script) {
        List<String> out = new ArrayList<>();
        int i = 0;
        for (String e : script) {
            if (e.length() < 2 || e.charAt(1) != ' ' || "=-+".indexOf(e.charAt(0)) < 0) throw new IllegalArgumentException("bad script entry");
            char tag = e.charAt(0);
            String text = e.substring(2);
            if (tag == '+') {
                out.add(text);
                continue;
            }
            if (i >= a.size() || !a.get(i).equals(text)) throw new IllegalArgumentException("script does not match");
            i++;
            if (tag == '=') out.add(text);
        }
        if (i != a.size()) throw new IllegalArgumentException("script leaves lines unread");
        return out;
    }

    public static long distance(List<String> a, List<String> b) {
        long n = 0;
        for (String e : diff(a, b)) if (e.charAt(0) != '=') n++;
        return n;
    }

    public static List<Long> sharedEnds(List<String> a, List<String> b) {
        int p = 0;
        while (p < a.size() && p < b.size() && a.get(p).equals(b.get(p))) p++;
        int s = 0;
        while (s < a.size() - p && s < b.size() - p && a.get(a.size() - 1 - s).equals(b.get(b.size() - 1 - s))) s++;
        return Arrays.asList((long) p, (long) s);
    }
}
''')


def dl_cases(rng):
    pool = ["", " ", "a", "b", "c", "d", "  indented", "\u00e9", "\U0001F600", "= a", "- b", "+ c", "same", "x y"]
    out = [("diff", [["a", "b", "c"], ["a", "c", "d"]]), ("apply_script", [["a", "b"], ["= a", "- b", "+ c"]]), ("distance", [["a", "b", "c"], ["a", "c", "d"]]), ("shared_ends", [["a", "b", "z"], ["a", "q", "z"]])]
    pairs = [([], []), (["a"], []), ([], ["a"]), (["a"], ["a"]), (["a"], ["b"]), (["a", "b"], ["b", "a"]), (["a", "b", "c"], ["a", "b", "c"]), (["a", "b", "c", "d"], ["b", "c"]), (["x"], ["x", "x", "x"]), (["x", "x", "x"], ["x"]),
             (["a", "b", "c", "d", "e"], ["a", "c", "e", "g"]), (["", ""], [""]), ([""], ["", ""]), (["a", "", "b"], ["a", "b"]), (["= a"], ["+ a"]), (["a", "b", "a", "b"], ["b", "a", "b", "a"]), (["1", "2", "3", "4"], ["4", "3", "2", "1"]),
             (["\u00e9", "\U0001F600"], ["\U0001F600", "\u00e9"]), (["same", "old", "same2"], ["same", "new", "same2"]), (["a", "b"], ["a", "x", "b"])]
    for a, b in pairs:
        out.append(("diff", [a, b]))
        out.append(("distance", [a, b]))
        out.append(("shared_ends", [a, b]))
    for _ in range(25):
        a = [rng.choice(pool[:rng.randint(2, 14)]) for _ in range(rng.randint(0, 10))]
        b = list(a)
        for _ in range(rng.randint(0, 4)):
            r = rng.random()
            if r < 0.4 and b:
                b.pop(rng.randrange(len(b)))
            elif r < 0.8:
                b.insert(rng.randint(0, len(b)), rng.choice(pool))
            elif b:
                b[rng.randrange(len(b))] = rng.choice(pool)
        out.append(("diff", [a, b]))
        out.append(("distance", [a, b]))
        out.append(("shared_ends", [a, b]))
        d = _diff(a, b)
        out.append(("apply_script", [a, d]))
    for a, s in [([], []), (["a"], []), ([], ["+ x"]), (["a"], ["= a"]), (["a"], ["- a"]), (["a"], ["- b"]), (["a"], ["= b"]), (["a", "b"], ["= a"]), (["a"], ["= a", "= a"]), (["a"], ["x a"]), (["a"], ["=a"]), (["a"], ["="]), (["a"], [""]),
                 (["a"], ["+"]), ([], ["+ "]), ([""], ["- "]), ([""], ["= "]), (["a"], ["+ x", "= a", "+ y"]), (["a", "b"], ["- a", "+ x", "- b"]), (["  a"], ["=   a"]), (["a b"], ["- a b"]), (["a"], ["== a"]), (["= a"], ["= = a"]), (["a"], ["- a", "- a"])]:
        out.append(("apply_script", [a, s]))
    return out


def _diff(a, b):
    n, m = len(a), len(b)
    t = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            t[i][j] = t[i + 1][j + 1] + 1 if a[i] == b[j] else max(t[i + 1][j], t[i][j + 1])
    i = j = 0
    out = []
    while i < n or j < m:
        if i < n and j < m and a[i] == b[j]:
            out.append("= " + a[i]); i += 1; j += 1
        elif j == m or (i < n and t[i + 1][j] >= t[i][j + 1]):
            out.append("- " + a[i]); i += 1
        else:
            out.append("+ " + b[j]); j += 1
    return out


DL = PortLib(
    slug="diff-lines",
    title="line diff and edit scripts",
    blurb="A changelog tool compares two versions of a text file and stores the difference as a small edit script that other tools replay.",
    spec=DL_SPEC,
    fns=DL_FNS,
    impls={"python": {"diff_lines.py": DL_PY}, "go": {"difflines.go": DL_GO}, "java": {"DiffLines.java": DL_JAVA}},
    cases=dl_cases,
    difficulty=4,
    traps=["deterministic tie-breaking in the LCS walk", "exact tag parsing", "empty lines / nil slices"],
    tags=["diff", "dynamic-programming"],
    pairs=[("python", "go", "full"), ("go", "java", "full"), ("java", "python", "stub"), ("python", "java", "stub")],
    diff_adj={"python>java": 0},
)
register_port(DL, __name__)

# ======================================================================================================================
# grid-regions: crop plots on a character grid
# ======================================================================================================================

GR_SPEC = dd('''
    A farm map is a grid: a list of rows, every row a string of the same length **counted in Unicode code points**. Each code
    point is a crop symbol (letters, digits, emoji, ...) except the space, which is bare ground. A *region* is a maximal set of
    cells with the same crop symbol that are connected through shared edges (up, down, left, right; no diagonals). Rows are 0-based
    from the top, columns 0-based from the left. A grid with rows of different length is an error in every function that can report errors (`largest_crop` is never called with one). An empty grid has no cells.

    * `region_sizes(grid)`: the number of cells of every region, largest first (equal sizes need no further order).
    * `region_at(grid, row, col)`: the size of the region containing that cell; a cell outside the grid or a bare-ground cell is an error.
    * `largest_crop(grid)`: the crop symbol (one code point, as a string) of the largest region; among regions of the same largest
      size the one whose first cell comes first in reading order (top to bottom, left to right) wins; no crops gives *absent*.
    * `perimeter(grid, row, col)`: the number of cell edges of the region containing that cell that touch the grid border, bare ground, or a
      different crop (same errors as `region_at`).
    * `count_regions(grid, crop)`: how many regions have the symbol `crop`; `crop` must be exactly one code point and not a space (else error).
''')

GR_FNS = [
    Fn("region_sizes", [("grid", "list<str>")], "list<int>", err=True),
    Fn("region_at", [("grid", "list<str>"), ("row", "int"), ("col", "int")], "int", err=True),
    Fn("largest_crop", [("grid", "list<str>")], "opt<str>", err=False),
    Fn("perimeter", [("grid", "list<str>"), ("row", "int"), ("col", "int")], "int", err=True),
    Fn("count_regions", [("grid", "list<str>"), ("crop", "str")], "int", err=True),
]

GR_PY = dd(r'''
def _check(grid):
    if grid and any(len(r) != len(grid[0]) for r in grid):
        raise ValueError("ragged grid")


def _regions(grid):
    """[(size, crop, cells)] in reading order of each region's first cell"""
    seen = set()
    out = []
    for r in range(len(grid)):
        for c in range(len(grid[r])):
            ch = grid[r][c]
            if ch == " " or (r, c) in seen:
                continue
            cells, stack = [], [(r, c)]
            seen.add((r, c))
            while stack:
                y, x = stack.pop()
                cells.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < len(grid) and 0 <= nx < len(grid[ny]) and (ny, nx) not in seen and grid[ny][nx] == ch:
                        seen.add((ny, nx))
                        stack.append((ny, nx))
            out.append((len(cells), ch, cells))
    return out


def region_sizes(grid):
    _check(grid)
    return sorted((s for s, _, _ in _regions(grid)), reverse=True)


def _find(grid, row, col):
    _check(grid)
    if not (0 <= row < len(grid) and 0 <= col < len(grid[0])) or grid[row][col] == " ":
        raise ValueError("no crop at that cell")
    for size, ch, cells in _regions(grid):
        if (row, col) in cells:
            return size, ch, set(cells)
    raise ValueError("unreachable")


def region_at(grid, row, col):
    return _find(grid, row, col)[0]


def largest_crop(grid):
    best = None
    for size, ch, _ in _regions(grid):
        if best is None or size > best[0]:
            best = (size, ch)
    return None if best is None else best[1]


def perimeter(grid, row, col):
    _, ch, cells = _find(grid, row, col)
    n = 0
    for y, x in cells:
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (y + dy, x + dx) not in cells:
                n += 1
    return n


def count_regions(grid, crop):
    _check(grid)
    if len(crop) != 1 or crop == " ":
        raise ValueError("crop must be one non-space code point")
    return sum(1 for _, ch, _ in _regions(grid) if ch == crop)
''')

GR_RS = dd(r'''
use std::collections::HashSet;

type Grid = Vec<Vec<char>>;

fn to_grid(grid: &[String]) -> Result<Grid, String> {
    let g: Grid = grid.iter().map(|r| r.chars().collect()).collect();
    if let Some(first) = g.first() {
        if g.iter().any(|r| r.len() != first.len()) {
            return Err("ragged grid".to_string());
        }
    }
    Ok(g)
}

struct Region {
    size: usize,
    crop: char,
    cells: HashSet<(i64, i64)>,
}

fn regions(g: &Grid) -> Vec<Region> {
    let mut seen: HashSet<(i64, i64)> = HashSet::new();
    let mut out = Vec::new();
    for r in 0..g.len() as i64 {
        for c in 0..g[r as usize].len() as i64 {
            let ch = g[r as usize][c as usize];
            if ch == ' ' || seen.contains(&(r, c)) {
                continue;
            }
            let mut cells = HashSet::new();
            let mut stack = vec![(r, c)];
            seen.insert((r, c));
            while let Some((y, x)) = stack.pop() {
                cells.insert((y, x));
                for (dy, dx) in [(1, 0), (-1, 0), (0, 1), (0, -1)] {
                    let (ny, nx) = (y + dy, x + dx);
                    if ny >= 0 && (ny as usize) < g.len() && nx >= 0 && (nx as usize) < g[ny as usize].len()
                        && !seen.contains(&(ny, nx)) && g[ny as usize][nx as usize] == ch
                    {
                        seen.insert((ny, nx));
                        stack.push((ny, nx));
                    }
                }
            }
            out.push(Region { size: cells.len(), crop: ch, cells });
        }
    }
    out
}

pub fn region_sizes(grid: &[String]) -> Result<Vec<i64>, String> {
    let g = to_grid(grid)?;
    let mut sizes: Vec<i64> = regions(&g).iter().map(|r| r.size as i64).collect();
    sizes.sort_by(|a, b| b.cmp(a));
    Ok(sizes)
}

fn find(grid: &[String], row: i64, col: i64) -> Result<Region, String> {
    let g = to_grid(grid)?;
    if row < 0 || row as usize >= g.len() || col < 0 || col as usize >= g[0].len() || g[row as usize][col as usize] == ' ' {
        return Err("no crop at that cell".to_string());
    }
    regions(&g).into_iter().find(|r| r.cells.contains(&(row, col))).ok_or_else(|| "unreachable".to_string())
}

pub fn region_at(grid: &[String], row: i64, col: i64) -> Result<i64, String> {
    Ok(find(grid, row, col)?.size as i64)
}

pub fn largest_crop(grid: &[String]) -> Option<String> {
    let g = to_grid(grid).ok()?;
    let mut best: Option<(usize, char)> = None;
    for r in regions(&g) {
        if best.map_or(true, |(s, _)| r.size > s) {
            best = Some((r.size, r.crop));
        }
    }
    best.map(|(_, c)| c.to_string())
}

pub fn perimeter(grid: &[String], row: i64, col: i64) -> Result<i64, String> {
    let region = find(grid, row, col)?;
    let mut n = 0;
    for &(y, x) in &region.cells {
        for (dy, dx) in [(1, 0), (-1, 0), (0, 1), (0, -1)] {
            if !region.cells.contains(&(y + dy, x + dx)) {
                n += 1;
            }
        }
    }
    Ok(n)
}

pub fn count_regions(grid: &[String], crop: &str) -> Result<i64, String> {
    let g = to_grid(grid)?;
    let cs: Vec<char> = crop.chars().collect();
    if cs.len() != 1 || cs[0] == ' ' {
        return Err("crop must be one non-space code point".to_string());
    }
    Ok(regions(&g).iter().filter(|r| r.crop == cs[0]).count() as i64)
}
''')

GR_JS = dd(r'''
'use strict';

function toGrid(grid) {
  const g = grid.map((r) => Array.from(r));
  if (g.length && g.some((r) => r.length !== g[0].length)) throw new Error('ragged grid');
  return g;
}

function regions(g) {
  const seen = new Set();
  const key = (y, x) => y * 100003 + x;
  const out = [];
  for (let r = 0; r < g.length; r++) {
    for (let c = 0; c < g[r].length; c++) {
      const ch = g[r][c];
      if (ch === ' ' || seen.has(key(r, c))) continue;
      const cells = new Set();
      const stack = [[r, c]];
      seen.add(key(r, c));
      while (stack.length) {
        const [y, x] = stack.pop();
        cells.add(key(y, x));
        for (const [dy, dx] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
          const ny = y + dy;
          const nx = x + dx;
          if (ny >= 0 && ny < g.length && nx >= 0 && nx < g[ny].length && !seen.has(key(ny, nx)) && g[ny][nx] === ch) {
            seen.add(key(ny, nx));
            stack.push([ny, nx]);
          }
        }
      }
      out.push({ size: cells.size, crop: ch, cells, key });
    }
  }
  return out;
}

function regionSizes(grid) {
  return regions(toGrid(grid)).map((r) => r.size).sort((a, b) => b - a);
}

function find(grid, row, col) {
  const g = toGrid(grid);
  if (row < 0 || row >= g.length || col < 0 || col >= g[0].length || g[row][col] === ' ') throw new Error('no crop at that cell');
  const k = row * 100003 + col;
  return regions(g).find((r) => r.cells.has(k));
}

function regionAt(grid, row, col) {
  return find(grid, row, col).size;
}

function largestCrop(grid) {
  let best = null;
  for (const r of regions(toGrid(grid))) {
    if (best === null || r.size > best.size) best = r;
  }
  return best === null ? null : best.crop;
}

function perimeter(grid, row, col) {
  const region = find(grid, row, col);
  let n = 0;
  for (const k of region.cells) {
    const y = Math.round((k - (k % 100003)) / 100003);
    const x = k - y * 100003;
    for (const [dy, dx] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      if (!region.cells.has(region.key(y + dy, x + dx))) n++;
    }
  }
  return n;
}

function countRegions(grid, crop) {
  const g = toGrid(grid);
  const cs = Array.from(crop);
  if (cs.length !== 1 || cs[0] === ' ') throw new Error('crop must be one non-space code point');
  return regions(g).filter((r) => r.crop === cs[0]).length;
}

module.exports = { regionSizes, regionAt, largestCrop, perimeter, countRegions };
''')


def gr_cases(rng):
    syms = ["a", "b", "c", "\U0001F33D", "\U0001F955", "\u00e9", " ", " ", "1"]
    grids = [
        [], [""], ["a"], [" "], ["aa", "aa"], ["ab", "ba"], ["aab", "abb", "ccb"], ["a a", " a ", "a a"], ["\U0001F33D\U0001F33D\U0001F955", "\U0001F955\U0001F33D\U0001F955"], ["abc", "ab", "abc"], ["a", "aa"], ["   ", "   "],
        ["aaaa", "abba", "abba", "aaaa"], ["ab", "cd"], ["abab", "baba", "abab"], ["\u00e9\u00e9a", "a\u00e9a", "aaa"], ["zzzzzzzz"] , ["z", "z", "z", "z", "z"], ["a b", "a b", "aab"],
    ]
    out = [("region_sizes", [["aab", "abb", "ccb"]]), ("region_at", [["aab", "abb", "ccb"], 0, 0]), ("largest_crop", [["aab", "abb", "ccb"]]), ("perimeter", [["aab", "abb", "ccb"], 0, 2]), ("count_regions", [["aab", "abb", "ccb"], "b"])]
    for g in grids:
        out.append(("region_sizes", [g]))
        if len({len(r) for r in g}) <= 1:
            out.append(("largest_crop", [g]))
        for sym in ["a", "b", "\U0001F33D", " ", "ab", "", "\u00e9"]:
            if rng.random() < 0.5:
                out.append(("count_regions", [g, sym]))
        for _ in range(3):
            if g and g[0] is not None:
                r = rng.randint(-1, len(g))
                c = rng.randint(-1, len(g[0]) // 1 + 1)
                out.append(("region_at", [g, r, c]))
                out.append(("perimeter", [g, r, c]))
    big = [
        ["aaaaaaaaaaaaaaaaaaaa"] * 20,
        ["ab" * 10, "ba" * 10] * 5,
        ["a" * 30] + ["a" + " " * 28 + "a" for _ in range(28)] + ["a" * 30],
    ]
    for g in big:
        out.append(("region_sizes", [g]))
        out.append(("largest_crop", [g]))
        out.append(("region_at", [g, 0, 0]))
        out.append(("perimeter", [g, 1, 1]))
    for _ in range(25):
        h, w = rng.randint(1, 6), rng.randint(1, 6)
        g = ["".join(rng.choice(syms[:rng.randint(2, 9)]) for _ in range(w)) for _ in range(h)]
        out.append(("region_sizes", [g]))
        out.append(("largest_crop", [g]))
        out.append(("count_regions", [g, rng.choice(["a", "b", "c", "\U0001F33D"])]))
        r, c = rng.randint(0, h - 1), rng.randint(0, w - 1)
        out.append(("region_at", [g, r, c]))
        out.append(("perimeter", [g, r, c]))
    return out


GR = PortLib(
    slug="grid-regions",
    title="crop regions on a farm map grid",
    blurb="A farm-planning tool reads a character map of a field (one symbol per plot) and reports connected plots of the same crop, their sizes and fence lengths.",
    spec=GR_SPEC,
    fns=GR_FNS,
    impls={"rust": {"src/lib.rs": GR_RS}, "python": {"grid_regions.py": GR_PY}, "javascript": {"src/grid_regions.js": GR_JS}},
    cases=gr_cases,
    difficulty=3,
    traps=["indexing text by code point (emoji crops)", "iterative flood fill on a 30x30 grid", "reading-order tie break"],
    tags=["grids", "flood-fill", "unicode"],
    pairs=[("rust", "python", "full"), ("python", "javascript", "full"), ("javascript", "rust", "stub"), ("rust", "javascript", "stub")],
)
register_port(GR, __name__)
