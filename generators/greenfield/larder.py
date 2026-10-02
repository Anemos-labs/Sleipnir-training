"""larder: a pantry-stock CLI that keeps its state in a file between runs (units, lots with expiry, shopping needs, exit codes)."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

PLACES = ["the lighthouse pantry", "a ferry galley store", "the Hollin allotment shed", "the library tea room", "a harbour kitchen", "the lamp-keepers' cupboard"]
ITEMS = ["flour", "sugar", "salt", "oats", "rice", "milk", "oil", "vinegar", "honey", "lentils", "eggs", "tea", "barley", "stock", "jam", "tin-beans", "dried-kelp", "cocoa"]
LANG_PLAN = ["bash", "python", "go", "rust", "bash", "go", "bash", "rust", "python", "bash"]


def params(rng, level, i):
    return {"level": level, "place": rng.choice(PLACES), "lots": level >= 3, "needs": level >= 4, "name_max": rng.choice([12, 16, 20]), "qty_digits": rng.choice([4, 5, 6])}


PY = r'''
import os
import sys

LOTS = @LOTS@
NEEDS = @NEEDS@
NAME_MAX = @NAME_MAX@
QTY_DIGITS = @QTY_DIGITS@
DG = "0123456789"
NAMECH = "abcdefghijklmnopqrstuvwxyz0123456789-"
UNITS = {"": ("pcs", 1), "pcs": ("pcs", 1), "g": ("g", 1), "kg": ("g", 1000), "ml": ("ml", 1), "cl": ("ml", 10), "dl": ("ml", 100), "l": ("ml", 1000)}


class Exit(Exception):
    def __init__(self, code):
        self.code = code


def die(code):
    raise Exit(code)


def valid_name(s):
    return 1 <= len(s) <= NAME_MAX and all(c in NAMECH for c in s)


def parse_qty(s):
    i = 0
    while i < len(s) and s[i] in DG:
        i += 1
    if i == 0 or i > QTY_DIGITS or s[i:] not in UNITS:
        die(2)
    cls, mult = UNITS[s[i:]]
    n = int(s[:i]) * mult
    if n < 1:
        die(2)
    return n, cls


def leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def valid_date(s):
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return False
    parts = s[:4] + s[5:7] + s[8:]
    if not all(c in DG for c in parts):
        return False
    y, m, d = int(s[:4]), int(s[5:7]), int(s[8:])
    if y < 2000 or y > 2099 or m < 1 or m > 12:
        return False
    dim = [31, 29 if leap(y) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return 1 <= d <= dim


def load(path):
    st = {"seq": 0, "lots": [], "needs": {}}
    if not os.path.exists(path):
        return st
    for line in open(path).read().split("\n"):
        w = line.split(" ")
        if w[0] == "seq":
            st["seq"] = int(w[1])
        elif w[0] == "lot":
            st["lots"].append({"name": w[1], "cls": w[2], "qty": int(w[3]), "exp": w[4], "seq": int(w[5])})
        elif w[0] == "need":
            st["needs"][w[1]] = (w[2], int(w[3]))
    return st


def save(path, st):
    lines = ["seq %d" % st["seq"]]
    for l in st["lots"]:
        lines.append("lot %s %s %d %s %d" % (l["name"], l["cls"], l["qty"], l["exp"], l["seq"]))
    for n, (c, q) in sorted(st["needs"].items()):
        lines.append("need %s %s %d" % (n, c, q))
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def totals(st):
    t = {}
    for l in st["lots"]:
        c, q = t.get(l["name"], (l["cls"], 0))
        t[l["name"]] = (c, q + l["qty"])
    return t


def lot_order(l):
    return (0 if l["exp"] != "-" else 1, l["exp"] if l["exp"] != "-" else "", l["seq"])


def main(argv):
    if len(argv) < 3 or argv[0] != "--db" or argv[1] == "":
        die(2)
    path, cmd, args = argv[1], argv[2], argv[3:]
    out = []
    if cmd == "add":
        if len(args) not in (2, 4):
            die(2)
        if not valid_name(args[0]):
            die(2)
        qty, cls = parse_qty(args[1])
        exp = "-"
        if len(args) == 4:
            if not LOTS or args[2] != "--exp" or not valid_date(args[3]):
                die(2)
            exp = args[3]
        st = load(path)
        have = totals(st).get(args[0])
        if have and have[0] != cls:
            die(4)
        st["seq"] += 1
        st["lots"].append({"name": args[0], "cls": cls, "qty": qty, "exp": exp, "seq": st["seq"]})
        save(path, st)
        out.append("added %s %d %s" % (args[0], qty, cls))
    elif cmd == "use":
        if len(args) != 2 or not valid_name(args[0]):
            die(2)
        qty, cls = parse_qty(args[1])
        st = load(path)
        have = totals(st).get(args[0])
        if not have:
            die(3)
        if have[0] != cls:
            die(4)
        if have[1] < qty:
            die(3)
        mine = sorted([l for l in st["lots"] if l["name"] == args[0]], key=lot_order)
        left = qty
        for l in mine:
            take = min(left, l["qty"])
            l["qty"] -= take
            left -= take
        st["lots"] = [l for l in st["lots"] if l["qty"] > 0]
        save(path, st)
        out.append("used %s %d %s" % (args[0], qty, cls))
        out.append("left %d %s" % (have[1] - qty, cls))
    elif cmd == "list":
        if args:
            die(2)
        st = load(path)
        t = totals(st)
        for n in sorted(t):
            line = "%s %d %s" % (n, t[n][1], t[n][0])
            if LOTS:
                line += " lots=%d" % sum(1 for l in st["lots"] if l["name"] == n)
            out.append(line)
    elif LOTS and cmd == "expire":
        if len(args) != 2 or args[0] != "--today" or not valid_date(args[1]):
            die(2)
        st = load(path)
        gone = [l for l in st["lots"] if l["exp"] != "-" and l["exp"] < args[1]]
        gone.sort(key=lambda l: (l["name"], l["exp"], l["seq"]))
        for l in gone:
            out.append("expired %s %d %s %s" % (l["name"], l["qty"], l["cls"], l["exp"]))
        st["lots"] = [l for l in st["lots"] if not (l["exp"] != "-" and l["exp"] < args[1])]
        save(path, st)
        out.append("removed %d" % len(gone))
    elif NEEDS and cmd == "need":
        if len(args) != 2 or not valid_name(args[0]):
            die(2)
        qty, cls = parse_qty(args[1])
        st = load(path)
        c0, q0 = st["needs"].get(args[0], (cls, 0))
        if c0 != cls:
            die(4)
        st["needs"][args[0]] = (cls, q0 + qty)
        save(path, st)
        out.append("need %s %d %s" % (args[0], q0 + qty, cls))
    elif NEEDS and cmd == "shopping":
        if args:
            die(2)
        st = load(path)
        t = totals(st)
        for n in sorted(st["needs"]):
            c, q = st["needs"][n]
            stock = t[n][1] if n in t and t[n][0] == c else 0
            if q > stock:
                out.append("%s %d %s" % (n, q - stock, c))
        if not out:
            out.append("nothing to buy")
    else:
        die(2)
    if out:
        sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exit as e:
        sys.exit(e.code)
'''

GO = r'''
package main

import (
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
)

const (
	hasLots   = @LOTS@
	hasNeeds  = @NEEDS@
	nameMax   = @NAME_MAX@
	qtyDigits = @QTY_DIGITS@
	dg        = "0123456789"
	nameCh    = "abcdefghijklmnopqrstuvwxyz0123456789-"
)

type unit struct {
	cls  string
	mult int64
}

var units = map[string]unit{"": {"pcs", 1}, "pcs": {"pcs", 1}, "g": {"g", 1}, "kg": {"g", 1000}, "ml": {"ml", 1}, "cl": {"ml", 10}, "dl": {"ml", 100}, "l": {"ml", 1000}}

type lot struct {
	name, cls, exp string
	qty            int64
	seq            int
}

type need struct {
	cls string
	qty int64
}

type state struct {
	seq   int
	lots  []lot
	needs map[string]need
}

func die(code int) { os.Exit(code) }

func validName(s string) bool {
	if len(s) < 1 || len(s) > nameMax {
		return false
	}
	for i := 0; i < len(s); i++ {
		if !strings.ContainsRune(nameCh, rune(s[i])) {
			return false
		}
	}
	return true
}

func parseQty(s string) (int64, string) {
	i := 0
	for i < len(s) && strings.ContainsRune(dg, rune(s[i])) {
		i++
	}
	u, ok := units[s[i:]]
	if i == 0 || i > qtyDigits || !ok {
		die(2)
	}
	n, _ := strconv.ParseInt(s[:i], 10, 64)
	n *= u.mult
	if n < 1 {
		die(2)
	}
	return n, u.cls
}

func leap(y int) bool { return y%4 == 0 && (y%100 != 0 || y%400 == 0) }

func validDate(s string) bool {
	if len(s) != 10 || s[4] != '-' || s[7] != '-' {
		return false
	}
	for _, p := range []string{s[:4], s[5:7], s[8:]} {
		for i := 0; i < len(p); i++ {
			if p[i] < '0' || p[i] > '9' {
				return false
			}
		}
	}
	y, _ := strconv.Atoi(s[:4])
	m, _ := strconv.Atoi(s[5:7])
	d, _ := strconv.Atoi(s[8:])
	if y < 2000 || y > 2099 || m < 1 || m > 12 {
		return false
	}
	dim := []int{31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31}[m-1]
	if m == 2 && leap(y) {
		dim = 29
	}
	return d >= 1 && d <= dim
}

func load(path string) *state {
	st := &state{needs: map[string]need{}}
	data, err := os.ReadFile(path)
	if err != nil {
		return st
	}
	for _, line := range strings.Split(string(data), "\n") {
		w := strings.Split(line, " ")
		switch w[0] {
		case "seq":
			st.seq, _ = strconv.Atoi(w[1])
		case "lot":
			q, _ := strconv.ParseInt(w[3], 10, 64)
			s, _ := strconv.Atoi(w[5])
			st.lots = append(st.lots, lot{name: w[1], cls: w[2], qty: q, exp: w[4], seq: s})
		case "need":
			q, _ := strconv.ParseInt(w[3], 10, 64)
			st.needs[w[1]] = need{w[2], q}
		}
	}
	return st
}

func save(path string, st *state) {
	lines := []string{fmt.Sprintf("seq %d", st.seq)}
	for _, l := range st.lots {
		lines = append(lines, fmt.Sprintf("lot %s %s %d %s %d", l.name, l.cls, l.qty, l.exp, l.seq))
	}
	var names []string
	for n := range st.needs {
		names = append(names, n)
	}
	sort.Strings(names)
	for _, n := range names {
		lines = append(lines, fmt.Sprintf("need %s %s %d", n, st.needs[n].cls, st.needs[n].qty))
	}
	os.WriteFile(path, []byte(strings.Join(lines, "\n")+"\n"), 0o644)
}

type total struct {
	cls string
	qty int64
}

func totals(st *state) map[string]total {
	t := map[string]total{}
	for _, l := range st.lots {
		x, ok := t[l.name]
		if !ok {
			x = total{cls: l.cls}
		}
		x.qty += l.qty
		t[l.name] = x
	}
	return t
}

func lotLess(a, b lot) bool {
	an, bn := a.exp == "-", b.exp == "-"
	if an != bn {
		return !an
	}
	if a.exp != b.exp {
		return a.exp < b.exp
	}
	return a.seq < b.seq
}

func sortedKeys(t map[string]total) []string {
	var ks []string
	for k := range t {
		ks = append(ks, k)
	}
	sort.Strings(ks)
	return ks
}

func main() {
	argv := os.Args[1:]
	if len(argv) < 3 || argv[0] != "--db" || argv[1] == "" {
		die(2)
	}
	path, cmd, args := argv[1], argv[2], argv[3:]
	var out []string
	switch {
	case cmd == "add":
		if len(args) != 2 && len(args) != 4 {
			die(2)
		}
		if !validName(args[0]) {
			die(2)
		}
		qty, cls := parseQty(args[1])
		exp := "-"
		if len(args) == 4 {
			if !hasLots || args[2] != "--exp" || !validDate(args[3]) {
				die(2)
			}
			exp = args[3]
		}
		st := load(path)
		if h, ok := totals(st)[args[0]]; ok && h.cls != cls {
			die(4)
		}
		st.seq++
		st.lots = append(st.lots, lot{name: args[0], cls: cls, qty: qty, exp: exp, seq: st.seq})
		save(path, st)
		out = append(out, fmt.Sprintf("added %s %d %s", args[0], qty, cls))
	case cmd == "use":
		if len(args) != 2 || !validName(args[0]) {
			die(2)
		}
		qty, cls := parseQty(args[1])
		st := load(path)
		h, ok := totals(st)[args[0]]
		if !ok {
			die(3)
		}
		if h.cls != cls {
			die(4)
		}
		if h.qty < qty {
			die(3)
		}
		var idx []int
		for i, l := range st.lots {
			if l.name == args[0] {
				idx = append(idx, i)
			}
		}
		sort.Slice(idx, func(a, b int) bool { return lotLess(st.lots[idx[a]], st.lots[idx[b]]) })
		left := qty
		for _, i := range idx {
			take := left
			if st.lots[i].qty < take {
				take = st.lots[i].qty
			}
			st.lots[i].qty -= take
			left -= take
		}
		var keep []lot
		for _, l := range st.lots {
			if l.qty > 0 {
				keep = append(keep, l)
			}
		}
		st.lots = keep
		save(path, st)
		out = append(out, fmt.Sprintf("used %s %d %s", args[0], qty, cls), fmt.Sprintf("left %d %s", h.qty-qty, cls))
	case cmd == "list":
		if len(args) != 0 {
			die(2)
		}
		st := load(path)
		t := totals(st)
		for _, n := range sortedKeys(t) {
			line := fmt.Sprintf("%s %d %s", n, t[n].qty, t[n].cls)
			if hasLots {
				c := 0
				for _, l := range st.lots {
					if l.name == n {
						c++
					}
				}
				line += fmt.Sprintf(" lots=%d", c)
			}
			out = append(out, line)
		}
	case hasLots && cmd == "expire":
		if len(args) != 2 || args[0] != "--today" || !validDate(args[1]) {
			die(2)
		}
		st := load(path)
		var gone, keep []lot
		for _, l := range st.lots {
			if l.exp != "-" && l.exp < args[1] {
				gone = append(gone, l)
			} else {
				keep = append(keep, l)
			}
		}
		sort.Slice(gone, func(a, b int) bool {
			x, y := gone[a], gone[b]
			if x.name != y.name {
				return x.name < y.name
			}
			if x.exp != y.exp {
				return x.exp < y.exp
			}
			return x.seq < y.seq
		})
		for _, l := range gone {
			out = append(out, fmt.Sprintf("expired %s %d %s %s", l.name, l.qty, l.cls, l.exp))
		}
		st.lots = keep
		save(path, st)
		out = append(out, fmt.Sprintf("removed %d", len(gone)))
	case hasNeeds && cmd == "need":
		if len(args) != 2 || !validName(args[0]) {
			die(2)
		}
		qty, cls := parseQty(args[1])
		st := load(path)
		cur, ok := st.needs[args[0]]
		if !ok {
			cur = need{cls, 0}
		}
		if cur.cls != cls {
			die(4)
		}
		st.needs[args[0]] = need{cls, cur.qty + qty}
		save(path, st)
		out = append(out, fmt.Sprintf("need %s %d %s", args[0], cur.qty+qty, cls))
	case hasNeeds && cmd == "shopping":
		if len(args) != 0 {
			die(2)
		}
		st := load(path)
		t := totals(st)
		var names []string
		for n := range st.needs {
			names = append(names, n)
		}
		sort.Strings(names)
		for _, n := range names {
			nd := st.needs[n]
			var stock int64
			if x, ok := t[n]; ok && x.cls == nd.cls {
				stock = x.qty
			}
			if nd.qty > stock {
				out = append(out, fmt.Sprintf("%s %d %s", n, nd.qty-stock, nd.cls))
			}
		}
		if len(out) == 0 {
			out = append(out, "nothing to buy")
		}
	default:
		die(2)
	}
	if len(out) > 0 {
		fmt.Print(strings.Join(out, "\n") + "\n")
	}
}
'''

RS = r'''
use std::collections::BTreeMap;
use std::fs;
use std::process::exit;

const HAS_LOTS: bool = @LOTS@;
const HAS_NEEDS: bool = @NEEDS@;
const NAME_MAX: usize = @NAME_MAX@;
const QTY_DIGITS: usize = @QTY_DIGITS@;
const NAMECH: &str = "abcdefghijklmnopqrstuvwxyz0123456789-";

#[derive(Clone)]
struct Lot {
    name: String,
    cls: String,
    qty: i64,
    exp: String,
    seq: i64,
}

struct State {
    seq: i64,
    lots: Vec<Lot>,
    needs: BTreeMap<String, (String, i64)>,
}

fn die(code: i32) -> ! {
    exit(code)
}

fn valid_name(s: &str) -> bool {
    !s.is_empty() && s.len() <= NAME_MAX && s.chars().all(|c| NAMECH.contains(c))
}

fn unit(s: &str) -> Option<(&'static str, i64)> {
    match s {
        "" | "pcs" => Some(("pcs", 1)),
        "g" => Some(("g", 1)),
        "kg" => Some(("g", 1000)),
        "ml" => Some(("ml", 1)),
        "cl" => Some(("ml", 10)),
        "dl" => Some(("ml", 100)),
        "l" => Some(("ml", 1000)),
        _ => None,
    }
}

fn parse_qty(s: &str) -> (i64, &'static str) {
    let i = s.bytes().take_while(|b| b.is_ascii_digit()).count();
    let u = unit(&s[i..]);
    if i == 0 || i > QTY_DIGITS || u.is_none() {
        die(2);
    }
    let (cls, mult) = u.unwrap();
    let n: i64 = s[..i].parse::<i64>().unwrap() * mult;
    if n < 1 {
        die(2);
    }
    (n, cls)
}

fn leap(y: i32) -> bool {
    y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)
}

fn valid_date(s: &str) -> bool {
    let b = s.as_bytes();
    if s.len() != 10 || b[4] != b'-' || b[7] != b'-' {
        return false;
    }
    for (i, c) in b.iter().enumerate() {
        if i != 4 && i != 7 && !c.is_ascii_digit() {
            return false;
        }
    }
    let y: i32 = s[..4].parse().unwrap();
    let m: usize = s[5..7].parse().unwrap();
    let d: i32 = s[8..].parse().unwrap();
    if y < 2000 || y > 2099 || m < 1 || m > 12 {
        return false;
    }
    let mut dim = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1];
    if m == 2 && leap(y) {
        dim = 29;
    }
    d >= 1 && d <= dim
}

fn load(path: &str) -> State {
    let mut st = State { seq: 0, lots: Vec::new(), needs: BTreeMap::new() };
    if let Ok(data) = fs::read_to_string(path) {
        for line in data.split('\n') {
            let w: Vec<&str> = line.split(' ').collect();
            match w[0] {
                "seq" => st.seq = w[1].parse().unwrap_or(0),
                "lot" => st.lots.push(Lot { name: w[1].to_string(), cls: w[2].to_string(), qty: w[3].parse().unwrap_or(0), exp: w[4].to_string(), seq: w[5].parse().unwrap_or(0) }),
                "need" => {
                    st.needs.insert(w[1].to_string(), (w[2].to_string(), w[3].parse().unwrap_or(0)));
                }
                _ => {}
            }
        }
    }
    st
}

fn save(path: &str, st: &State) {
    let mut lines = vec![format!("seq {}", st.seq)];
    for l in &st.lots {
        lines.push(format!("lot {} {} {} {} {}", l.name, l.cls, l.qty, l.exp, l.seq));
    }
    for (n, (c, q)) in &st.needs {
        lines.push(format!("need {} {} {}", n, c, q));
    }
    let _ = fs::write(path, lines.join("\n") + "\n");
}

fn totals(st: &State) -> BTreeMap<String, (String, i64)> {
    let mut t: BTreeMap<String, (String, i64)> = BTreeMap::new();
    for l in &st.lots {
        let e = t.entry(l.name.clone()).or_insert((l.cls.clone(), 0));
        e.1 += l.qty;
    }
    t
}

fn lot_key(l: &Lot) -> (u8, String, i64) {
    if l.exp != "-" { (0, l.exp.clone(), l.seq) } else { (1, String::new(), l.seq) }
}

fn main() {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    if argv.len() < 3 || argv[0] != "--db" || argv[1].is_empty() {
        die(2);
    }
    let path = argv[1].as_str();
    let cmd = argv[2].as_str();
    let args: Vec<&str> = argv[3..].iter().map(|s| s.as_str()).collect();
    let mut out: Vec<String> = Vec::new();
    if cmd == "add" {
        if args.len() != 2 && args.len() != 4 {
            die(2);
        }
        if !valid_name(args[0]) {
            die(2);
        }
        let (qty, cls) = parse_qty(args[1]);
        let mut exp = "-".to_string();
        if args.len() == 4 {
            if !HAS_LOTS || args[2] != "--exp" || !valid_date(args[3]) {
                die(2);
            }
            exp = args[3].to_string();
        }
        let mut st = load(path);
        if let Some(h) = totals(&st).get(args[0]) {
            if h.0 != cls {
                die(4);
            }
        }
        st.seq += 1;
        let seq = st.seq;
        st.lots.push(Lot { name: args[0].to_string(), cls: cls.to_string(), qty, exp, seq });
        save(path, &st);
        out.push(format!("added {} {} {}", args[0], qty, cls));
    } else if cmd == "use" {
        if args.len() != 2 || !valid_name(args[0]) {
            die(2);
        }
        let (qty, cls) = parse_qty(args[1]);
        let mut st = load(path);
        let h = match totals(&st).get(args[0]) {
            Some(h) => h.clone(),
            None => die(3),
        };
        if h.0 != cls {
            die(4);
        }
        if h.1 < qty {
            die(3);
        }
        let mut idx: Vec<usize> = (0..st.lots.len()).filter(|i| st.lots[*i].name == args[0]).collect();
        idx.sort_by_key(|i| lot_key(&st.lots[*i]));
        let mut left = qty;
        for i in idx {
            let take = left.min(st.lots[i].qty);
            st.lots[i].qty -= take;
            left -= take;
        }
        st.lots.retain(|l| l.qty > 0);
        save(path, &st);
        out.push(format!("used {} {} {}", args[0], qty, cls));
        out.push(format!("left {} {}", h.1 - qty, cls));
    } else if cmd == "list" {
        if !args.is_empty() {
            die(2);
        }
        let st = load(path);
        for (n, (c, q)) in totals(&st) {
            let mut line = format!("{} {} {}", n, q, c);
            if HAS_LOTS {
                line += &format!(" lots={}", st.lots.iter().filter(|l| l.name == n).count());
            }
            out.push(line);
        }
    } else if HAS_LOTS && cmd == "expire" {
        if args.len() != 2 || args[0] != "--today" || !valid_date(args[1]) {
            die(2);
        }
        let mut st = load(path);
        let today = args[1];
        let mut gone: Vec<Lot> = st.lots.iter().filter(|l| l.exp != "-" && l.exp.as_str() < today).cloned().collect();
        gone.sort_by(|a, b| (a.name.clone(), a.exp.clone(), a.seq).cmp(&(b.name.clone(), b.exp.clone(), b.seq)));
        for l in &gone {
            out.push(format!("expired {} {} {} {}", l.name, l.qty, l.cls, l.exp));
        }
        st.lots.retain(|l| !(l.exp != "-" && l.exp.as_str() < today));
        save(path, &st);
        out.push(format!("removed {}", gone.len()));
    } else if HAS_NEEDS && cmd == "need" {
        if args.len() != 2 || !valid_name(args[0]) {
            die(2);
        }
        let (qty, cls) = parse_qty(args[1]);
        let mut st = load(path);
        let cur = st.needs.get(args[0]).cloned().unwrap_or((cls.to_string(), 0));
        if cur.0 != cls {
            die(4);
        }
        st.needs.insert(args[0].to_string(), (cls.to_string(), cur.1 + qty));
        save(path, &st);
        out.push(format!("need {} {} {}", args[0], cur.1 + qty, cls));
    } else if HAS_NEEDS && cmd == "shopping" {
        if !args.is_empty() {
            die(2);
        }
        let st = load(path);
        let t = totals(&st);
        for (n, (c, q)) in &st.needs {
            let stock = match t.get(n) {
                Some(x) if x.0 == *c => x.1,
                _ => 0,
            };
            if *q > stock {
                out.push(format!("{} {} {}", n, q - stock, c));
            }
        }
        if out.is_empty() {
            out.push("nothing to buy".to_string());
        }
    } else {
        die(2);
    }
    if !out.is_empty() {
        println!("{}", out.join("\n"));
    }
}
'''

SH = r'''
#!/usr/bin/env bash
# larder: pantry stock with a state file
HAS_LOTS=@LOTS_SH@
HAS_NEEDS=@NEEDS_SH@
if [ $# -lt 3 ] || [ "$1" != "--db" ] || [ -z "$2" ]; then exit 2; fi
DB=$2
shift 2
TMP="$DB.tmp.$$"
trap 'rm -f "$TMP"' EXIT
touch_db=0
if [ -f "$DB" ]; then SRC=$DB; else SRC=/dev/null; fi
ARGS=("$@")
# join arguments with a unit separator so that awk can split them back
JOINED=$(printf '%s\037' "$@")
awk -v HAS_LOTS="$HAS_LOTS" -v HAS_NEEDS="$HAS_NEEDS" -v NAME_MAX=@NAME_MAX@ -v QTY_DIGITS=@QTY_DIGITS@ -v OUTF="$TMP" -v ARGJ="$JOINED" '
function isdig(s,   i, n) { n = length(s); if (n == 0) return 0; for (i = 1; i <= n; i++) if (index("0123456789", substr(s, i, 1)) == 0) return 0; return 1 }
function die(c) { rc = c; exit c }
function validname(s,   i) {
  if (length(s) < 1 || length(s) > NAME_MAX) return 0
  for (i = 1; i <= length(s); i++) if (index("abcdefghijklmnopqrstuvwxyz0123456789-", substr(s, i, 1)) == 0) return 0
  return 1
}
function parseqty(s,   i, suf, n) {
  i = 0
  while (i < length(s) && index("0123456789", substr(s, i + 1, 1)) > 0) i++
  suf = substr(s, i + 1)
  if (i == 0 || i > QTY_DIGITS) die(2)
  if (suf == "" || suf == "pcs") { QCLS = "pcs"; mult = 1 }
  else if (suf == "g") { QCLS = "g"; mult = 1 }
  else if (suf == "kg") { QCLS = "g"; mult = 1000 }
  else if (suf == "ml") { QCLS = "ml"; mult = 1 }
  else if (suf == "cl") { QCLS = "ml"; mult = 10 }
  else if (suf == "dl") { QCLS = "ml"; mult = 100 }
  else if (suf == "l") { QCLS = "ml"; mult = 1000 }
  else die(2)
  n = substr(s, 1, i) * mult
  if (n < 1) die(2)
  return n
}
function leap(y) { return (y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)) }
function validdate(s,   y, m, d, dim, parts, i) {
  if (length(s) != 10 || substr(s, 5, 1) != "-" || substr(s, 8, 1) != "-") return 0
  if (!isdig(substr(s, 1, 4)) || !isdig(substr(s, 6, 2)) || !isdig(substr(s, 9, 2))) return 0
  y = substr(s, 1, 4) + 0; m = substr(s, 6, 2) + 0; d = substr(s, 9, 2) + 0
  if (y < 2000 || y > 2099 || m < 1 || m > 12) return 0
  split("31 28 31 30 31 30 31 31 30 31 30 31", parts, " ")
  dim = parts[m] + 0
  if (m == 2 && leap(y)) dim = 29
  return (d >= 1 && d <= dim)
}
function totalsof(   i) {
  delete TQ; delete TC; delete TL
  for (i = 1; i <= nl; i++) {
    if (!(LN[i] in TQ)) { TQ[LN[i]] = 0; TC[LN[i]] = LC[i]; TL[LN[i]] = 0 }
    TQ[LN[i]] += LQ[i]; TL[LN[i]]++
  }
}
# does lot a sort before lot b?
function lotless(a, b,   an, bn) {
  an = (LE[a] == "-"); bn = (LE[b] == "-")
  if (an != bn) return !an
  if (LE[a] != LE[b]) return LE[a] < LE[b]
  return LS[a] + 0 < LS[b] + 0
}
function emit(s) { OUT[++no] = s }
BEGIN {
  nl = 0; nn = 0; seq = 0; no = 0
  while ((getline line < "'"$SRC"'") > 0) {
    n = split(line, w, " ")
    if (w[1] == "seq") seq = w[2] + 0
    else if (w[1] == "lot") { nl++; LN[nl] = w[2]; LC[nl] = w[3]; LQ[nl] = w[4] + 0; LE[nl] = w[5]; LS[nl] = w[6] + 0 }
    else if (w[1] == "need") { NN[w[2]] = w[2]; NC[w[2]] = w[3]; NQ[w[2]] = w[4] + 0 }
  }
  na = split(ARGJ, A, "\037"); na--   # trailing separator gives one empty element
  cmd = A[1]
  mutated = 0
  if (cmd == "add") {
    if (na != 3 && na != 5) die(2)
    if (!validname(A[2])) die(2)
    qty = parseqty(A[3]); cls = QCLS
    expd = "-"
    if (na == 5) {
      if (!HAS_LOTS || A[4] != "--exp" || !validdate(A[5])) die(2)
      expd = A[5]
    }
    totalsof()
    if ((A[2] in TQ) && TC[A[2]] != cls) die(4)
    seq++; nl++; LN[nl] = A[2]; LC[nl] = cls; LQ[nl] = qty; LE[nl] = expd; LS[nl] = seq
    mutated = 1
    emit("added " A[2] " " qty " " cls)
  } else if (cmd == "use") {
    if (na != 3 || !validname(A[2])) die(2)
    qty = parseqty(A[3]); cls = QCLS
    totalsof()
    if (!(A[2] in TQ)) die(3)
    if (TC[A[2]] != cls) die(4)
    if (TQ[A[2]] < qty) die(3)
    left = qty
    while (left > 0) {
      best = 0
      for (i = 1; i <= nl; i++) {
        if (LN[i] != A[2] || LQ[i] <= 0) continue
        if (best == 0 || lotless(i, best)) best = i
      }
      take = (left < LQ[best]) ? left : LQ[best]
      LQ[best] -= take; left -= take
    }
    mutated = 1
    emit("used " A[2] " " qty " " cls)
    emit("left " (TQ[A[2]] - qty) " " cls)
  } else if (cmd == "list") {
    if (na != 1) die(2)
    totalsof()
    k = 0
    for (nm in TQ) NAMES[++k] = nm
    for (i = 2; i <= k; i++) { v = NAMES[i]; j = i - 1; while (j >= 1 && NAMES[j] > v) { NAMES[j + 1] = NAMES[j]; j-- } NAMES[j + 1] = v }
    for (i = 1; i <= k; i++) {
      nm = NAMES[i]
      line = nm " " TQ[nm] " " TC[nm]
      if (HAS_LOTS == 1) line = line " lots=" TL[nm]
      emit(line)
    }
  } else if (HAS_LOTS == 1 && cmd == "expire") {
    if (na != 3 || A[2] != "--today" || !validdate(A[3])) die(2)
    today = A[3]
    g = 0
    for (i = 1; i <= nl; i++) if (LE[i] != "-" && LE[i] < today) GONE[++g] = i
    # order gone lots by (name, exp, seq)
    for (a = 2; a <= g; a++) {
      v = GONE[a]; b = a - 1
      while (b >= 1 && ((LN[GONE[b]] "") > (LN[v] "") || ((LN[GONE[b]] "") == (LN[v] "") && ((LE[GONE[b]] "") > (LE[v] "") || ((LE[GONE[b]] "") == (LE[v] "") && LS[GONE[b]] + 0 > LS[v] + 0))))) { GONE[b + 1] = GONE[b]; b-- }
      GONE[b + 1] = v
    }
    for (a = 1; a <= g; a++) { i = GONE[a]; emit("expired " LN[i] " " LQ[i] " " LC[i] " " LE[i]); LQ[i] = 0 }
    mutated = 1
    emit("removed " g)
  } else if (HAS_NEEDS == 1 && cmd == "need") {
    if (na != 3 || !validname(A[2])) die(2)
    qty = parseqty(A[3]); cls = QCLS
    if ((A[2] in NC) && NC[A[2]] != cls) die(4)
    NN[A[2]] = A[2]; NC[A[2]] = cls; NQ[A[2]] += qty
    mutated = 1
    emit("need " A[2] " " NQ[A[2]] " " cls)
  } else if (HAS_NEEDS == 1 && cmd == "shopping") {
    if (na != 1) die(2)
    totalsof()
    k = 0
    for (nm in NN) NAMES[++k] = nm
    for (i = 2; i <= k; i++) { v = NAMES[i]; j = i - 1; while (j >= 1 && NAMES[j] > v) { NAMES[j + 1] = NAMES[j]; j-- } NAMES[j + 1] = v }
    for (i = 1; i <= k; i++) {
      nm = NAMES[i]
      stock = ((nm in TQ) && TC[nm] == NC[nm]) ? TQ[nm] : 0
      if (NQ[nm] > stock) emit(nm " " (NQ[nm] - stock) " " NC[nm])
    }
    if (no == 0) emit("nothing to buy")
  } else die(2)
  # write the new state
  if (mutated) {
    print "seq " seq > OUTF
    for (i = 1; i <= nl; i++) if (LQ[i] > 0) print "lot " LN[i] " " LC[i] " " LQ[i] " " LE[i] " " LS[i] > OUTF
    k = 0
    for (nm in NN) NAMES2[++k] = nm
    for (i = 2; i <= k; i++) { v = NAMES2[i]; j = i - 1; while (j >= 1 && NAMES2[j] > v) { NAMES2[j + 1] = NAMES2[j]; j-- } NAMES2[j + 1] = v }
    for (i = 1; i <= k; i++) print "need " NAMES2[i] " " NC[NAMES2[i]] " " NQ[NAMES2[i]] > OUTF
    close(OUTF)
  }
  for (i = 1; i <= no; i++) print OUT[i]
  exit 0
}'
rc=$?
if [ $rc -eq 0 ] && [ -f "$TMP" ]; then mv "$TMP" "$DB"; fi
exit $rc
'''

SOURCES = {"python": PY, "go": GO, "rust": RS, "bash": SH}


def _b(lang, v):
    if lang == "python":
        return "True" if v else "False"
    if lang == "bash":
        return "1" if v else "0"
    return "true" if v else "false"


def sol(lang, p):
    return K.subst(SOURCES[lang], LOTS=_b(lang, p["lots"]), NEEDS=_b(lang, p["needs"]), LOTS_SH=_b("bash", p["lots"]), NEEDS_SH=_b("bash", p["needs"]),
                   NAME_MAX=p["name_max"], QTY_DIGITS=p["qty_digits"]).lstrip("\n")


# ---------------------------------------------------------------------------------------------------------------

def readme(p, spec, lang, examples):
    L = [f"# larder: stock-keeping for {p['place']}", ""]
    L.append(f"`larder` keeps track of what is in the store of {p['place']}. It is a command-line tool that remembers its data **between runs in a state file**: every invocation starts with `--db PATH`, "
             "the path of the state file. The format of that file is entirely up to you; a file that does not exist yet means an empty store. Commands that fail must leave the state untouched.")
    L.append("")
    L.append("```")
    L.append("larder --db PATH COMMAND [ARGUMENTS...]")
    L.append("```")
    L.append("")
    L.append("`--db PATH` must be the first two arguments (and `PATH` must not be empty) and a command must follow; otherwise the exit status is 2. Results go to standard output; error messages go to standard error (their text is not checked).")
    L.append("")
    L.append("## Names, quantities, units")
    L.append("")
    L.append(f"* An **item name** is 1 to {p['name_max']} characters from `a-z`, `0-9` and `-`.")
    L.append(f"* A **quantity** is one to {p['qty_digits']} ASCII digits immediately followed by an optional unit suffix: nothing or `pcs` (pieces), `g`, `kg` (1000 g), `ml`, `cl` (10 ml), `dl` (100 ml), `l` (1000 ml). "
             "Leading zeros are fine (`007g` is 7 g). Quantities are converted to the *base unit* of their class: `g`, `ml` or `pcs`; the converted amount must be at least 1 (so `0g` is invalid). "
             "Anything else (a sign, a decimal point, an unknown suffix, no digits, upper case) is invalid.")
    L.append("* Every item belongs to a **unit class** (`g`, `ml` or `pcs`), fixed by the first quantity added to it. Mixing classes for the same item is an error (exit status 4, see below).")
    if p["lots"]:
        L.append("* A **date** is `YYYY-MM-DD` with ASCII digits, a real calendar date (leap years follow the Gregorian rule), year 2000 to 2099.")
    L.append("")
    L.append("## Commands")
    L.append("")
    L.append("Syntax or value problems in the arguments (wrong number of arguments, invalid name, quantity" + (" or date" if p["lots"] else "") + ", unknown command, unknown option) are exit status 2 and are detected **before** the store is looked at.")
    L.append("")
    if p["lots"]:
        L.append("**`add NAME QTY [--exp DATE]`**: puts a new *lot* of the item in the store. The optional expiry date is only valid in this exact form (`--exp` followed by the date). "
                 "If the item exists with a different unit class: exit 4. Prints `added NAME AMOUNT UNIT` with the amount converted to the base unit (`added flour 2000 g`).")
    else:
        L.append("**`add NAME QTY`**: adds the quantity to the item. If the item exists with a different unit class: exit 4. Prints `added NAME AMOUNT UNIT` with the amount converted to the base unit (`added flour 2000 g` for `2kg`).")
    L.append("")
    if p["lots"]:
        L.append("**`use NAME QTY`**: takes the quantity out of the store. Check order after the argument checks: the item does not exist (nothing in stock): exit 3; the unit class differs: exit 4; the total in stock is smaller than the quantity: exit 3. "
                 "Otherwise the amount is taken from the item's lots, **earliest expiry date first, lots without an expiry date last, ties in the order the lots were added**, emptying a lot completely before the next one is touched. "
                 "Empty lots disappear. Prints two lines: `used NAME AMOUNT UNIT` and `left TOTAL UNIT` (total remaining; 0 if nothing is left, in which case the item is forgotten, including its unit class).")
    else:
        L.append("**`use NAME QTY`**: takes the quantity out of the store. Check order after the argument checks: the item does not exist (nothing in stock): exit 3; the unit class differs: exit 4; less in stock than requested: exit 3. "
                 "Prints two lines: `used NAME AMOUNT UNIT` and `left TOTAL UNIT` (0 if nothing is left, in which case the item is forgotten, including its unit class).")
    L.append("")
    L.append("**`list`** (no arguments): one line per item in stock, sorted by name in ascending byte order: `NAME TOTAL UNIT`" + (" followed by ` lots=K` (the number of lots)" if p["lots"] else "") + ". Nothing is printed for an empty store.")
    L.append("")
    if p["lots"]:
        L.append("**`expire --today DATE`**: removes every lot whose expiry date is **before** `DATE` (a lot expiring on `DATE` is still good; lots without a date never expire). Prints `expired NAME AMOUNT UNIT EXPIRY` for each removed lot "
                 "sorted by name, then expiry date, then the order the lots were added, and finally `removed K`.")
        L.append("")
    if p["needs"]:
        L.append("**`need NAME QTY`**: records that the item has to be bought; repeated needs of an item add up. The unit class of a need is fixed by its first quantity (a different class: exit 4). Prints `need NAME TOTAL_NEED UNIT`. Needs are independent of the stock.")
        L.append("")
        L.append("**`shopping`** (no arguments): for every item with a need, sorted by name, if the need is larger than the stock of that item *in the same unit class* (stock in another class counts as 0; no stock counts as 0), prints `NAME MISSING UNIT` (the difference). "
                 "If nothing is missing the single line `nothing to buy` is printed. The needs list is never cleared.")
        L.append("")
    L.append("## Exit statuses")
    L.append("")
    L.append("0 success; 2 usage or value error; 3 item not found or not enough in stock; 4 unit class mismatch. With a non-zero status nothing is printed to standard output and the state is not changed.")
    L.append("")
    L.append("## Where")
    L.append("")
    L.append(f"The program lives in {spec.how(lang)}.")
    L.append("")
    L.append("## Example session")
    L.append("")
    L.append("```")
    for c, out in examples:
        L.append("$ larder " + " ".join(a for a in c.args).replace("@STATE@", "store.db"))
        for ln in out.rstrip("\n").split("\n"):
            if ln:
                L.append(ln)
        L.append(f"[exit {c.code}]")
    L.append("```")
    L.append("")
    L.append(K.run_hint("bash"))
    return "\n".join(L) + "\n"


def make_cases(rng, p):
    cases = []
    lots, needs = p["lots"], p["needs"]
    items = rng.sample(ITEMS, 7)
    S = "@STATE@"

    def c(*args, fresh=False):
        cases.append(K.CliCase(["--db", S, *args], "", fresh=fresh))

    def qty(cls=None):
        cls = cls or rng.choice(["g", "g", "ml", "pcs"])
        n = rng.randrange(1, 900)
        if cls == "g":
            return rng.choice([f"{n}g", f"{rng.randrange(1, 9)}kg", f"{n}g"])
        if cls == "ml":
            return rng.choice([f"{n}ml", f"{rng.randrange(1, 9)}l", f"{rng.randrange(1, 90)}cl", f"{rng.randrange(1, 20)}dl"])
        return rng.choice([str(rng.randrange(1, 30)), f"{rng.randrange(1, 30)}pcs"])

    def date(lo=2024, hi=2026):
        y = rng.randrange(lo, hi + 1)
        m = rng.randrange(1, 13)
        d = rng.randrange(1, 29)
        return f"{y}-{m:02d}-{d:02d}"

    def session(n_ops, first=True):
        its = rng.sample(items, 3)
        cls = {it: rng.choice(["g", "ml", "pcs"]) for it in its}
        for k in range(n_ops):
            it = rng.choice(its)
            r = rng.random()
            f = first and k == 0
            if r < 0.4:
                args = ["add", it, qty(cls[it])]
                if lots and rng.random() < 0.6:
                    args += ["--exp", date()]
                c(*args, fresh=f)
            elif r < 0.65:
                c("use", it, qty(cls[it]), fresh=f)
            elif r < 0.78:
                c("list", fresh=f)
            elif lots and r < 0.88:
                c("expire", "--today", date(), fresh=f)
            elif needs and r < 0.94:
                c("need", it, qty(cls[it]), fresh=f)
            elif needs:
                c("shopping", fresh=f)
            else:
                c("list", fresh=f)

    # examples: a short session
    a, b = items[0], items[1]
    c("add", a, "2kg", *(["--exp", "2025-06-30"] if lots else []), fresh=True)
    c("add", a, "500g", *(["--exp", "2025-05-01"] if lots else []))
    c("use", a, "600g")
    c("list")
    nex = len(cases)
    for _ in range(4):
        session(rng.randrange(5, 9))
    session(rng.randrange(10, 14))
    # basic ones
    it = items[2]
    c("list", fresh=True)
    c("use", it, "1g", fresh=True)
    c("add", it, "1g", fresh=True)
    c("list")
    c("use", it, "1g")
    c("list")
    c("use", it, "1g")
    c("add", it, "1kg", fresh=True)
    c("add", it, "1kg")
    c("list")
    c("use", it, "1500g")
    c("list")
    c("use", it, "501g")
    c("use", it, "500g")
    c("list")
    c("add", it, "500g")
    c("add", it, "2l")
    c("use", it, "3")
    c("list")
    # units
    for q in ("1kg", "1l", "1cl", "1pcs", "007g", "0g", "00", "12G", "1 g", "1.5kg", "-1g", "kg", "", "1gg", "999999g", "9999999g", "99999", "100000"):
        c("add", items[3], q, fresh=True)
    c("add", items[3], "2dl", fresh=True)
    c("list")
    # names
    for nm in ("A", "my-item", "-", "a_b", "a b", "x" * p["name_max"], "x" * (p["name_max"] + 1), "", "UPPER"):
        c("add", nm, "5g", fresh=True)
    c("add", "12345", "5g", fresh=True)
    c("add", "100", "5g")
    c("add", "99", "5g")
    c("list")
    # arguments
    for args in (["add"], ["add", "x"], ["add", "x", "1g", "extra"], ["use"], ["use", "x", "1g", "extra"], ["list", "extra"], ["frobnicate"], [""], ["ADD", "x", "1g"], ["add", "x", "--exp", "2025-01-01"]):
        c(*args, fresh=True)
    cases.append(K.CliCase([], "", fresh=True))
    cases.append(K.CliCase(["list"], "", fresh=True))
    cases.append(K.CliCase(["--db"], "", fresh=True))
    cases.append(K.CliCase(["--db", S], "", fresh=True))
    cases.append(K.CliCase(["--db", "", "list"], "", fresh=True))
    cases.append(K.CliCase(["--dbx", S, "list"], "", fresh=True))
    cases.append(K.CliCase([S, "--db", "list"], "", fresh=True))
    cases.append(K.CliCase(["--db", S, "list", "--db", S], "", fresh=True))
    # unit mismatch
    c("add", "oil", "1l", fresh=True)
    c("add", "oil", "500g")
    c("add", "oil", "3")
    c("use", "oil", "1g")
    c("use", "oil", "1")
    c("use", "oil", "1l")
    c("list")
    c("add", "oil", "1l", fresh=True)
    c("use", "oil", "2l")
    c("use", "oil", "1001ml")
    c("use", "oil", "1000ml")
    c("add", "oil", "5", fresh=True)
    c("use", "oil", "5")
    c("add", "oil", "1g")
    c("list")
    if lots:
        a = items[4]
        c("add", a, "100g", "--exp", "2025-03-01", fresh=True)
        c("add", a, "100g", "--exp", "2025-02-01")
        c("add", a, "100g")
        c("add", a, "100g", "--exp", "2025-02-01")
        c("add", a, "100g", "--exp", "2024-12-31")
        c("list")
        c("use", a, "250g")
        c("list")
        c("expire", "--today", "2025-02-01")
        c("expire", "--today", "2025-02-02")
        c("list")
        c("use", a, "50g")
        c("expire", "--today", "2099-12-31")
        c("list")
        for d in ("2025-02-29", "2024-02-29", "2000-02-29", "2100-02-28", "1999-12-31", "2025-13-01", "2025-04-31", "2025-1-01", "2025/01/01", "2025-01-00", "2099-12-31", ""):
            c("add", "salt", "1g", "--exp", d, fresh=True)
        c("list")
        for d in ("2025-02-29", "bad", ""):
            c("expire", "--today", d, fresh=True)
        for args in (["expire"], ["expire", "2025-01-01"], ["expire", "--today"], ["expire", "--now", "2025-01-01"], ["expire", "--today", "2025-01-01", "x"], ["add", "x", "1g", "--expires", "2025-01-01"], ["add", "x", "1g", "-e", "2025-01-01"], ["add", "x", "1g", "--exp", "2025-01-01", "extra"]):
            c(*args, fresh=True)
        # ordering of consumption
        c("add", "tea", "3", "--exp", "2025-05-01", fresh=True)
        c("add", "tea", "3", "--exp", "2025-04-01")
        c("add", "tea", "3")
        c("add", "tea", "3", "--exp", "2025-04-01")
        c("add", "tea", "3", "--exp", "2026-01-01")
        c("use", "tea", "7")
        c("list")
        c("use", "tea", "3")
        c("expire", "--today", "2025-04-02")
        c("list")
        c("use", "tea", "100")
        c("use", "tea", "5")
        c("list")
        c("add", "jam", "1kg", "--exp", "2025-01-01", fresh=True)
        c("add", "tea", "1", "--exp", "2025-01-01")
        c("add", "jam", "1kg", "--exp", "2025-01-01")
        c("add", "tea", "1", "--exp", "2024-01-01")
        c("expire", "--today", "2025-01-01")
        c("expire", "--today", "2025-01-02")
        c("list")
    if needs:
        c("shopping", fresh=True)
        c("need", "flour", "1kg")
        c("shopping")
        c("add", "flour", "400g")
        c("shopping")
        c("add", "flour", "600g")
        c("shopping")
        c("add", "flour", "1g")
        c("shopping")
        c("need", "flour", "1kg")
        c("shopping")
        c("need", "flour", "2l")
        c("need", "eggs", "6")
        c("need", "eggs", "6pcs")
        c("add", "eggs", "5")
        c("shopping")
        c("add", "eggs", "1")
        c("shopping")
        c("use", "flour", "2000g")
        c("shopping")
        c("add", "milk", "1l", fresh=True)
        c("need", "milk", "1500ml")
        c("shopping")
        c("add", "milk", "1l")
        c("shopping")
        c("need", "milk", "3")
        c("need", "milk", "1500g")
        c("shopping")
        c("need", "x", "5g", fresh=True)
        c("add", "x", "5")
        c("shopping")
        c("list")
        c("use", "x", "5")
        c("need", "zebra", "1", fresh=True)
        c("need", "apple", "1")
        c("need", "mango", "1")
        c("shopping")
        for args in (["need"], ["need", "x"], ["need", "x", "0g"], ["need", "X", "1g"], ["need", "x", "1g", "extra"], ["shopping", "x"]):
            c(*args, fresh=True)
    else:
        c("expire", "--today", "2025-01-01", fresh=True)
        c("need", "x", "1g", fresh=True)
        c("shopping", fresh=True)
        c("add", "x", "1g", "--exp", "2025-01-01", fresh=True)
        c("list")
    out, seen = [], set()
    for k_ in cases:
        out.append(k_)
    # drop exact duplicates only for fresh single-step cases (keep sequences intact)
    return out, nex


def prompt(rng, p, spec, lang):
    ln = K.LANG_NAME[lang]
    where = spec.short(lang)
    feats = ["`add`, `use` and `list`"] + (["lots with expiry dates (`expire`)"] if p["lots"] else []) + (["a shopping list (`need`, `shopping`)"] if p["needs"] else [])
    ft = ", ".join(feats)
    opts = [
        f"{p['place'].capitalize()} wants a command-line stock keeper called `larder`, written in {ln} (entry point {where}). It must remember its data in a file between runs. README.md has the full command reference: {ft}, units, exit statuses. {K.closer(rng)}",
        f"Please implement the `larder` CLI from README.md in {ln}. State lives in the file given by `--db`; the format is yours. Commands: {ft}. Entry point {where}. Exit codes and the order of the error checks matter.",
        f"need `larder` ({ln}, entry point {where}): pantry tracking with persistence across invocations. spec in README.md. {ft}. {K.closer(rng)}",
        f"Greenfield task: write the stateful `larder` tool ({ln}; {where}) described in README.md. The hidden checks run command sequences against a fresh state file and compare stdout and exit status after each command.",
    ]
    return rng.choice(opts).strip()


@family("greenfield-larder", category="greenfield", lang="mixed", kind="greenfield", n=10,
        summary="pantry stock CLI with a state file between invocations: unit conversion, lots with expiry consumed earliest-first, shopping needs, exit-code contract")
def gen(rng, n):
    levels = [2, 2, 3, 3, 3, 4, 4, 3, 2, 4]
    diffs = [2, 2, 3, 3, 3, 4, 4, 4, 2, 5]
    spec = K.CliSpec("larder")
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level, i)
        sols = {lang: sol(lang, p), "python": sol("python", p)}
        cases, nex = make_cases(rng, p)
        pt = K.merged(spec.skeleton("python"), spec.stub("python"), {spec.path("python"): sols["python"]})
        res = K.record_cli(spec, "python", pt, cases[:nex])
        ex = []
        for cs, o in zip(cases[:nex], res):
            cs.code = o[1]
            ex.append((cs, o[0]))
        rd = readme(p, spec, lang, ex)
        yield K.cli_task(
            spec=spec, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, spec, lang),
            difficulty=diffs[i % len(diffs)], slug=f"{i + 1:02d}-{lang}-l{level}-{p['place'].split()[-1].lower()}",
            tags=["cli", "state", "exit-codes"], notes={"level": level, "lots": p["lots"], "needs": p["needs"]},
        )
