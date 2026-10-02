"""File-sync planner: mirror / newer / two-way sync with a base listing, globs, size limit, move detection, conflict preferences and directory ordering (invented rules)."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

PY = r'''
SAME = @SAME@
MODES = @MODES@
HAS_IGNORE = @IGNORE@
HAS_MAXSIZE = @MAXSIZE@
HAS_MOVE = @MOVE@
HAS_PREFER = @PREFER@
HAS_DIRS = @DIRS@
V_COPY = @V_COPY@
V_DELETE = @V_DELETE@
V_SKIP = @V_SKIP@
V_CONFLICT = @V_CONFLICT@
V_MOVE = @V_MOVE@
V_MKDIR = @V_MKDIR@
V_RMDIR = @V_RMDIR@
TO_RIGHT = @TO_RIGHT@
TO_LEFT = @TO_LEFT@
INSYNC = @INSYNC@

LOW = "abcdefghijklmnopqrstuvwxyz"
DIG = "0123456789"
PATH_CHARS = LOW + LOW.upper() + DIG + "._/-"


class Err(Exception):
    pass


def split_lines(text):
    if text == "":
        return []
    ls = text.split("\n")
    if ls[-1] == "":
        ls.pop()
    return ls


def num_ok(s, maxlen):
    return 1 <= len(s) <= maxlen and all(c in DIG for c in s) and (len(s) == 1 or s[0] != "0")


def path_ok(p):
    if not (1 <= len(p) <= 60) or not all(c in PATH_CHARS for c in p):
        return False
    if p[0] == "/" or p[-1] == "/":
        return False
    segs = p.split("/")
    return all(s != "" and s != "." and s != ".." for s in segs)


def parse_listing(label, lines):
    out = {}
    for n, line in enumerate(lines, 1):
        parts = line.split(" ")
        bad = None
        if len(parts) != 4:
            bad = "fields"
        else:
            path, size, mt, ident = parts
            if not path_ok(path):
                bad = "path"
            elif not num_ok(size, 9):
                bad = "size"
            elif not num_ok(mt, 10):
                bad = "mtime"
            elif not (1 <= len(ident) <= 8 and all(c in LOW + DIG for c in ident)):
                bad = "id"
            elif path in out:
                bad = "duplicate"
        if bad:
            raise Err("error: %s line %d: %s" % (label, n, bad))
        out[path] = (int(size), int(mt), ident)
    return out


def parse_rules(text):
    lines = split_lines(text)
    r = {"mode": "mirror", "prune": False, "ignore": [], "maxsize": None, "prefer": None}
    seen = set()
    base = []
    for i, line in enumerate(lines):
        if line == "--":
            base = lines[i + 1:]
            break
        parts = line.split(" ")
        w, args = parts[0], parts[1:]
        known = ["mode", "prune"] + (["ignore"] if HAS_IGNORE else []) + (["maxsize"] if HAS_MAXSIZE else []) + (["prefer"] if HAS_PREFER else [])
        fail = lambda m: Err("error: rules line %d: %s" % (i + 1, m))  # noqa: E731
        if w not in known:
            raise fail("unknown")
        if w != "ignore" and w in seen:
            raise fail("duplicate")
        seen.add(w)
        if w == "mode":
            if len(args) != 1 or args[0] not in MODES:
                raise fail("argument")
            r["mode"] = args[0]
        elif w == "prune":
            if args:
                raise fail("argument")
            r["prune"] = True
        elif w == "ignore":
            if len(args) != 1 or args[0] == "":
                raise fail("argument")
            r["ignore"].append(args[0])
        elif w == "maxsize":
            if len(args) != 1 or not num_ok(args[0], 9):
                raise fail("argument")
            r["maxsize"] = int(args[0])
        elif w == "prefer":
            if len(args) != 1 or args[0] not in ("left", "right", "newer"):
                raise fail("argument")
            r["prefer"] = args[0]
    return r, base


def gmatch(pat, s):
    def go(i, j):
        if i == len(pat):
            return j == len(s)
        if pat.startswith("**", i):
            for k in range(j, len(s) + 1):
                if go(i + 2, k):
                    return True
            return False
        c = pat[i]
        if c == "*":
            k = j
            while True:
                if go(i + 1, k):
                    return True
                if k < len(s) and s[k] != "/":
                    k += 1
                else:
                    return False
        if c == "?":
            return j < len(s) and s[j] != "/" and go(i + 1, j + 1)
        return j < len(s) and s[j] == c and go(i + 1, j + 1)
    return go(0, 0)


def same(a, b):
    if SAME == "id":
        return a[2] == b[2]
    if SAME == "sizeid":
        return a[0] == b[0] and a[2] == b[2]
    return a[0] == b[0] and a[1] == b[1]


def equiv(a, b):
    if a is None or b is None:
        return a is None and b is None
    return same(a, b)


def ancestors(p):
    segs = p.split("/")
    return ["/".join(segs[:k]) for k in range(1, len(segs))]


def plan(left, right, rules):
    try:
        return do_plan(left, right, rules)
    except Err as e:
        return str(e)


def do_plan(left, right, rules):
    r, base_lines = parse_rules(rules)
    L = parse_listing("left", split_lines(left))
    R = parse_listing("right", split_lines(right))
    B = parse_listing("base", base_lines)
    ig = r["ignore"]
    live = lambda p: not any(gmatch(g, p) for g in ig)  # noqa: E731
    Lf = {p: e for p, e in L.items() if live(p)}
    Rf = {p: e for p, e in R.items() if live(p)}
    Bf = {p: e for p, e in B.items() if live(p)}
    mx = r["maxsize"]
    lines = []  # (kind, dir or None, path, path2 or None)

    def transfer(side_entry, to, p):
        if mx is not None and side_entry[0] > mx:
            lines.append(("skip", None, p, None))
        else:
            lines.append(("copy", to, p, None))

    if r["mode"] in ("mirror", "newer"):
        for p in sorted(set(Lf) | set(Rf)):
            l, rr = Lf.get(p), Rf.get(p)
            if l is not None and rr is None:
                transfer(l, TO_RIGHT, p)
            elif rr is not None and l is None:
                if r["prune"]:
                    lines.append(("delete", TO_RIGHT, p, None))
            elif not same(l, rr):
                if r["mode"] == "newer" and not l[1] > rr[1]:
                    lines.append(("skip", None, p, None))
                else:
                    transfer(l, TO_RIGHT, p)
    else:
        for p in sorted(set(Lf) | set(Rf) | set(Bf)):
            l, rr, b = Lf.get(p), Rf.get(p), Bf.get(p)
            if equiv(l, rr):
                continue
            lch, rch = not equiv(l, b), not equiv(rr, b)
            src = None
            if lch and not rch:
                src = "l"
            elif rch and not lch:
                src = "r"
            else:
                pf = r["prefer"]
                if pf == "left":
                    src = "l"
                elif pf == "right":
                    src = "r"
                elif pf == "newer":
                    if l is not None and rr is not None:
                        src = "l" if l[1] > rr[1] else "r" if rr[1] > l[1] else None
                    else:
                        src = "l" if l is not None else "r"
                if src is None:
                    lines.append(("conflict", None, p, None))
                    continue
            ent, to = (l, TO_RIGHT) if src == "l" else (rr, TO_LEFT)
            if ent is None:
                lines.append(("delete", to, p, None))
            else:
                transfer(ent, to, p)
        if HAS_MOVE:
            for to in (TO_RIGHT, TO_LEFT):
                src_map = Lf if to == TO_RIGHT else Rf
                dels, adds = {}, {}
                for ln in lines:
                    if ln[1] != to:
                        continue
                    if ln[0] == "delete":
                        e = Bf[ln[2]]
                        dels.setdefault((e[2], e[0]), []).append(ln[2])
                    elif ln[0] == "copy":
                        e = src_map[ln[2]]
                        adds.setdefault((e[2], e[0]), []).append(ln[2])
                drop = set()
                new = []
                for k in dels:
                    if len(dels[k]) == 1 and len(adds.get(k, [])) == 1:
                        drop.add(("delete", to, dels[k][0], None))
                        drop.add(("copy", to, adds[k][0], None))
                        new.append(("move", to, dels[k][0], adds[k][0]))
                lines = [ln for ln in lines if ln not in drop] + new
    rank = lambda d: 1 if d == TO_LEFT else 0  # noqa: E731
    key = lambda ln: (ln[3] if ln[0] == "move" else ln[2], rank(ln[1]))  # noqa: E731
    if not HAS_DIRS:
        lines.sort(key=key)
    else:
        sidefile = lambda d: L if d == TO_LEFT else R  # noqa: E731
        writes, removes = [], []
        for kind, d, p, q in lines:
            if kind == "copy":
                writes.append((d, p))
            elif kind == "delete":
                removes.append((d, p))
            elif kind == "move":
                removes.append((d, p))
                writes.append((d, q))
        mk, rm = [], []
        made = set()
        for d, p in writes:
            have = set()
            for f in sidefile(d):
                have.update(ancestors(f))
            for a in ancestors(p):
                if a not in have and (d, a) not in made:
                    made.add((d, a))
                    mk.append(("mkdir", d, a, None))
        gone = set()
        for d in (TO_RIGHT, TO_LEFT):
            final = set(sidefile(d))
            for dd, p in removes:
                if dd == d:
                    final.discard(p)
            for dd, p in writes:
                if dd == d:
                    final.add(p)
            fdirs = set()
            for f in final:
                fdirs.update(ancestors(f))
            for dd, p in removes:
                if dd == d:
                    for a in ancestors(p):
                        if a not in fdirs and (d, a) not in gone:
                            gone.add((d, a))
                            rm.append(("rmdir", d, a, None))
        main = sorted([ln for ln in lines if ln[0] != "delete"], key=key)
        dels = sorted([ln for ln in lines if ln[0] == "delete"], key=key)
        mk.sort(key=key)
        rm.sort(key=lambda ln: (ln[2], -rank(ln[1])), reverse=True)
        lines = mk + main + dels + rm
    return render_lines(lines, r["mode"] == "twoway")


def render_lines(lines, two):
    if not lines:
        return INSYNC
    out = []
    names = {"copy": V_COPY, "delete": V_DELETE, "skip": V_SKIP, "conflict": V_CONFLICT, "move": V_MOVE, "mkdir": V_MKDIR, "rmdir": V_RMDIR}
    for kind, d, p, q in lines:
        parts = [names[kind]]
        if two and kind not in ("skip", "conflict"):
            parts.append(d)
        parts.append(p)
        if q is not None:
            parts.append(q)
        out.append(" ".join(parts))
    return "\n".join(out)
'''

GO = r'''
package syncplan

import (
	"sort"
	"strconv"
	"strings"
)

const (
	same_      = @SAME@
	hasIgnore  = @IGNORE@
	hasMaxsize = @MAXSIZE@
	hasMove    = @MOVE@
	hasPrefer  = @PREFER@
	hasDirs    = @DIRS@
	vCopy      = @V_COPY@
	vDelete    = @V_DELETE@
	vSkip      = @V_SKIP@
	vConflict  = @V_CONFLICT@
	vMove      = @V_MOVE@
	vMkdir     = @V_MKDIR@
	vRmdir     = @V_RMDIR@
	toRight    = @TO_RIGHT@
	toLeft     = @TO_LEFT@
	inSync     = @INSYNC@
)

var modes = []string@MODES@

type entry struct {
	size, mtime int64
	id          string
}

type planErr struct{ msg string }

type rules struct {
	mode    string
	prune   bool
	ignore  []string
	maxsize int64
	hasMax  bool
	prefer  string
}

type line struct {
	kind, dir, p, q string
}

func fail(m string) { panic(planErr{m}) }

func splitLines(text string) []string {
	if text == "" {
		return nil
	}
	ls := strings.Split(text, "\n")
	if ls[len(ls)-1] == "" {
		ls = ls[:len(ls)-1]
	}
	return ls
}

func numOK(s string, maxlen int) bool {
	if len(s) < 1 || len(s) > maxlen {
		return false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	return len(s) == 1 || s[0] != '0'
}

func pathOK(p string) bool {
	if len(p) < 1 || len(p) > 60 {
		return false
	}
	for i := 0; i < len(p); i++ {
		c := p[i]
		if !(c >= 'a' && c <= 'z') && !(c >= 'A' && c <= 'Z') && !(c >= '0' && c <= '9') && c != '.' && c != '_' && c != '/' && c != '-' {
			return false
		}
	}
	if p[0] == '/' || p[len(p)-1] == '/' {
		return false
	}
	for _, s := range strings.Split(p, "/") {
		if s == "" || s == "." || s == ".." {
			return false
		}
	}
	return true
}

func idOK(s string) bool {
	if len(s) < 1 || len(s) > 8 {
		return false
	}
	for i := 0; i < len(s); i++ {
		if !(s[i] >= 'a' && s[i] <= 'z') && !(s[i] >= '0' && s[i] <= '9') {
			return false
		}
	}
	return true
}

func parseListing(label string, lines []string) map[string]entry {
	out := map[string]entry{}
	for n, ln := range lines {
		parts := strings.Split(ln, " ")
		bad := ""
		if len(parts) != 4 {
			bad = "fields"
		} else if !pathOK(parts[0]) {
			bad = "path"
		} else if !numOK(parts[1], 9) {
			bad = "size"
		} else if !numOK(parts[2], 10) {
			bad = "mtime"
		} else if !idOK(parts[3]) {
			bad = "id"
		} else if _, dup := out[parts[0]]; dup {
			bad = "duplicate"
		}
		if bad != "" {
			fail("error: " + label + " line " + strconv.Itoa(n+1) + ": " + bad)
		}
		sz, _ := strconv.ParseInt(parts[1], 10, 64)
		mt, _ := strconv.ParseInt(parts[2], 10, 64)
		out[parts[0]] = entry{sz, mt, parts[3]}
	}
	return out
}

func parseRules(text string) (rules, []string) {
	ls := splitLines(text)
	r := rules{mode: "mirror"}
	seen := map[string]bool{}
	var base []string
	for i, ln := range ls {
		if ln == "--" {
			base = ls[i+1:]
			break
		}
		parts := strings.Split(ln, " ")
		w, args := parts[0], parts[1:]
		bad := func(m string) { fail("error: rules line " + strconv.Itoa(i+1) + ": " + m) }
		known := w == "mode" || w == "prune" || (hasIgnore && w == "ignore") || (hasMaxsize && w == "maxsize") || (hasPrefer && w == "prefer")
		if !known {
			bad("unknown")
		}
		if w != "ignore" && seen[w] {
			bad("duplicate")
		}
		seen[w] = true
		switch w {
		case "mode":
			ok := false
			if len(args) == 1 {
				for _, m := range modes {
					if m == args[0] {
						ok = true
					}
				}
			}
			if !ok {
				bad("argument")
			}
			r.mode = args[0]
		case "prune":
			if len(args) != 0 {
				bad("argument")
			}
			r.prune = true
		case "ignore":
			if len(args) != 1 || args[0] == "" {
				bad("argument")
			}
			r.ignore = append(r.ignore, args[0])
		case "maxsize":
			if len(args) != 1 || !numOK(args[0], 9) {
				bad("argument")
			}
			r.maxsize, _ = strconv.ParseInt(args[0], 10, 64)
			r.hasMax = true
		case "prefer":
			if len(args) != 1 || (args[0] != "left" && args[0] != "right" && args[0] != "newer") {
				bad("argument")
			}
			r.prefer = args[0]
		}
	}
	return r, base
}

func gmatch(pat, s string) bool {
	var gof func(i, j int) bool
	gof = func(i, j int) bool {
		if i == len(pat) {
			return j == len(s)
		}
		if strings.HasPrefix(pat[i:], "**") {
			for k := j; k <= len(s); k++ {
				if gof(i+2, k) {
					return true
				}
			}
			return false
		}
		c := pat[i]
		if c == '*' {
			k := j
			for {
				if gof(i+1, k) {
					return true
				}
				if k < len(s) && s[k] != '/' {
					k++
				} else {
					return false
				}
			}
		}
		if c == '?' {
			return j < len(s) && s[j] != '/' && gof(i+1, j+1)
		}
		return j < len(s) && s[j] == c && gof(i+1, j+1)
	}
	return gof(0, 0)
}

func same(a, b entry) bool {
	switch same_ {
	case "id":
		return a.id == b.id
	case "sizeid":
		return a.size == b.size && a.id == b.id
	}
	return a.size == b.size && a.mtime == b.mtime
}

func equiv(a, b *entry) bool {
	if a == nil || b == nil {
		return a == nil && b == nil
	}
	return same(*a, *b)
}

func ancestors(p string) []string {
	segs := strings.Split(p, "/")
	var out []string
	for k := 1; k < len(segs); k++ {
		out = append(out, strings.Join(segs[:k], "/"))
	}
	return out
}

func get(m map[string]entry, p string) *entry {
	if e, ok := m[p]; ok {
		return &e
	}
	return nil
}

func sortedKeys(ms ...map[string]entry) []string {
	set := map[string]bool{}
	for _, m := range ms {
		for k := range m {
			set[k] = true
		}
	}
	out := make([]string, 0, len(set))
	for k := range set {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func rank(d string) int {
	if d == toLeft {
		return 1
	}
	return 0
}

func sortKey(ln line) string {
	if ln.kind == "move" {
		return ln.q
	}
	return ln.p
}

func sortLines(ls []line) {
	sort.SliceStable(ls, func(a, b int) bool {
		ka, kb := sortKey(ls[a]), sortKey(ls[b])
		if ka != kb {
			return ka < kb
		}
		return rank(ls[a].dir) < rank(ls[b].dir)
	})
}

func doPlan(left, right, rulesText string) string {
	r, baseLines := parseRules(rulesText)
	L := parseListing("left", splitLines(left))
	R := parseListing("right", splitLines(right))
	B := parseListing("base", baseLines)
	live := func(p string) bool {
		for _, g := range r.ignore {
			if gmatch(g, p) {
				return false
			}
		}
		return true
	}
	filt := func(m map[string]entry) map[string]entry {
		o := map[string]entry{}
		for p, e := range m {
			if live(p) {
				o[p] = e
			}
		}
		return o
	}
	Lf, Rf, Bf := filt(L), filt(R), filt(B)
	var lines []line
	transfer := func(e entry, to, p string) {
		if r.hasMax && e.size > r.maxsize {
			lines = append(lines, line{"skip", "", p, ""})
		} else {
			lines = append(lines, line{"copy", to, p, ""})
		}
	}
	if r.mode == "mirror" || r.mode == "newer" {
		for _, p := range sortedKeys(Lf, Rf) {
			l, rr := get(Lf, p), get(Rf, p)
			if l != nil && rr == nil {
				transfer(*l, toRight, p)
			} else if rr != nil && l == nil {
				if r.prune {
					lines = append(lines, line{"delete", toRight, p, ""})
				}
			} else if !same(*l, *rr) {
				if r.mode == "newer" && !(l.mtime > rr.mtime) {
					lines = append(lines, line{"skip", "", p, ""})
				} else {
					transfer(*l, toRight, p)
				}
			}
		}
	} else {
		for _, p := range sortedKeys(Lf, Rf, Bf) {
			l, rr, b := get(Lf, p), get(Rf, p), get(Bf, p)
			if equiv(l, rr) {
				continue
			}
			lch, rch := !equiv(l, b), !equiv(rr, b)
			src := ""
			if lch && !rch {
				src = "l"
			} else if rch && !lch {
				src = "r"
			} else {
				switch r.prefer {
				case "left":
					src = "l"
				case "right":
					src = "r"
				case "newer":
					if l != nil && rr != nil {
						if l.mtime > rr.mtime {
							src = "l"
						} else if rr.mtime > l.mtime {
							src = "r"
						}
					} else if l != nil {
						src = "l"
					} else {
						src = "r"
					}
				}
				if src == "" {
					lines = append(lines, line{"conflict", "", p, ""})
					continue
				}
			}
			ent, to := l, toRight
			if src == "r" {
				ent, to = rr, toLeft
			}
			if ent == nil {
				lines = append(lines, line{"delete", to, p, ""})
			} else {
				transfer(*ent, to, p)
			}
		}
		if hasMove {
			for _, to := range []string{toRight, toLeft} {
				srcMap := Lf
				if to == toLeft {
					srcMap = Rf
				}
				type key struct {
					id   string
					size int64
				}
				dels, adds := map[key][]string{}, map[key][]string{}
				for _, ln := range lines {
					if ln.dir != to {
						continue
					}
					if ln.kind == "delete" {
						e := Bf[ln.p]
						dels[key{e.id, e.size}] = append(dels[key{e.id, e.size}], ln.p)
					} else if ln.kind == "copy" {
						e := srcMap[ln.p]
						adds[key{e.id, e.size}] = append(adds[key{e.id, e.size}], ln.p)
					}
				}
				drop := map[line]bool{}
				var added []line
				for k, d := range dels {
					if len(d) == 1 && len(adds[k]) == 1 {
						drop[line{"delete", to, d[0], ""}] = true
						drop[line{"copy", to, adds[k][0], ""}] = true
						added = append(added, line{"move", to, d[0], adds[k][0]})
					}
				}
				var kept []line
				for _, ln := range lines {
					if !drop[ln] {
						kept = append(kept, ln)
					}
				}
				lines = append(kept, added...)
			}
		}
	}
	if !hasDirs {
		sortLines(lines)
	} else {
		sideFile := func(d string) map[string]entry {
			if d == toLeft {
				return L
			}
			return R
		}
		type dp struct{ d, p string }
		var writes, removes []dp
		for _, ln := range lines {
			switch ln.kind {
			case "copy":
				writes = append(writes, dp{ln.dir, ln.p})
			case "delete":
				removes = append(removes, dp{ln.dir, ln.p})
			case "move":
				removes = append(removes, dp{ln.dir, ln.p})
				writes = append(writes, dp{ln.dir, ln.q})
			}
		}
		var mk, rm []line
		made := map[dp]bool{}
		for _, w := range writes {
			have := map[string]bool{}
			for f := range sideFile(w.d) {
				for _, a := range ancestors(f) {
					have[a] = true
				}
			}
			for _, a := range ancestors(w.p) {
				if !have[a] && !made[dp{w.d, a}] {
					made[dp{w.d, a}] = true
					mk = append(mk, line{"mkdir", w.d, a, ""})
				}
			}
		}
		gone := map[dp]bool{}
		for _, d := range []string{toRight, toLeft} {
			final := map[string]bool{}
			for f := range sideFile(d) {
				final[f] = true
			}
			for _, x := range removes {
				if x.d == d {
					delete(final, x.p)
				}
			}
			for _, x := range writes {
				if x.d == d {
					final[x.p] = true
				}
			}
			fdirs := map[string]bool{}
			for f := range final {
				for _, a := range ancestors(f) {
					fdirs[a] = true
				}
			}
			for _, x := range removes {
				if x.d == d {
					for _, a := range ancestors(x.p) {
						if !fdirs[a] && !gone[dp{d, a}] {
							gone[dp{d, a}] = true
							rm = append(rm, line{"rmdir", d, a, ""})
						}
					}
				}
			}
		}
		var mainL, dels []line
		for _, ln := range lines {
			if ln.kind == "delete" {
				dels = append(dels, ln)
			} else {
				mainL = append(mainL, ln)
			}
		}
		sortLines(mainL)
		sortLines(dels)
		sortLines(mk)
		sort.SliceStable(rm, func(a, b int) bool {
			if rm[a].p != rm[b].p {
				return rm[a].p > rm[b].p
			}
			return rank(rm[a].dir) < rank(rm[b].dir)
		})
		lines = append(append(append(mk, mainL...), dels...), rm...)
	}
	return renderLines(lines, r.mode == "twoway")
}

func renderLines(lines []line, two bool) string {
	if len(lines) == 0 {
		return inSync
	}
	names := map[string]string{"copy": vCopy, "delete": vDelete, "skip": vSkip, "conflict": vConflict, "move": vMove, "mkdir": vMkdir, "rmdir": vRmdir}
	out := make([]string, 0, len(lines))
	for _, ln := range lines {
		parts := []string{names[ln.kind]}
		if two && ln.kind != "skip" && ln.kind != "conflict" {
			parts = append(parts, ln.dir)
		}
		parts = append(parts, ln.p)
		if ln.q != "" {
			parts = append(parts, ln.q)
		}
		out = append(out, strings.Join(parts, " "))
	}
	return strings.Join(out, "\n")
}

// Plan computes the sync plan.
func Plan(left, right, rulesText string) (res string) {
	defer func() {
		if r := recover(); r != nil {
			if e, ok := r.(planErr); ok {
				res = e.msg
				return
			}
			panic(r)
		}
	}()
	return doPlan(left, right, rulesText)
}
'''

RS = r'''
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

const SAME: &str = @SAME@;
const MODES: &[&str] = &@MODES@;
const HAS_IGNORE: bool = @IGNORE@;
const HAS_MAXSIZE: bool = @MAXSIZE@;
const HAS_MOVE: bool = @MOVE@;
const HAS_PREFER: bool = @PREFER@;
const HAS_DIRS: bool = @DIRS@;
const V_COPY: &str = @V_COPY@;
const V_DELETE: &str = @V_DELETE@;
const V_SKIP: &str = @V_SKIP@;
const V_CONFLICT: &str = @V_CONFLICT@;
const V_MOVE: &str = @V_MOVE@;
const V_MKDIR: &str = @V_MKDIR@;
const V_RMDIR: &str = @V_RMDIR@;
const TO_RIGHT: &str = @TO_RIGHT@;
const TO_LEFT: &str = @TO_LEFT@;
const INSYNC: &str = @INSYNC@;

#[derive(Clone)]
struct Entry {
    size: i64,
    mtime: i64,
    id: String,
}

type Map = BTreeMap<String, Entry>;

struct Rules {
    mode: String,
    prune: bool,
    ignore: Vec<String>,
    maxsize: Option<i64>,
    prefer: Option<String>,
}

#[derive(Clone, PartialEq, Eq)]
struct Line {
    kind: &'static str,
    dir: String,
    p: String,
    q: String,
}

fn mk(kind: &'static str, dir: &str, p: &str, q: &str) -> Line {
    Line { kind, dir: dir.to_string(), p: p.to_string(), q: q.to_string() }
}

fn split_lines(text: &str) -> Vec<String> {
    if text.is_empty() {
        return Vec::new();
    }
    let mut ls: Vec<String> = text.split('\n').map(|s| s.to_string()).collect();
    if ls.last().map(|s| s.is_empty()).unwrap_or(false) {
        ls.pop();
    }
    ls
}

fn num_ok(s: &str, maxlen: usize) -> bool {
    if s.is_empty() || s.len() > maxlen || !s.bytes().all(|c| c.is_ascii_digit()) {
        return false;
    }
    s.len() == 1 || !s.starts_with('0')
}

fn path_ok(p: &str) -> bool {
    if p.is_empty() || p.len() > 60 {
        return false;
    }
    if !p.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'.' || c == b'_' || c == b'/' || c == b'-') {
        return false;
    }
    if p.starts_with('/') || p.ends_with('/') {
        return false;
    }
    p.split('/').all(|s| !s.is_empty() && s != "." && s != "..")
}

fn id_ok(s: &str) -> bool {
    !s.is_empty() && s.len() <= 8 && s.bytes().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
}

fn parse_listing(label: &str, lines: &[String]) -> Result<Map, String> {
    let mut out = Map::new();
    for (n, line) in lines.iter().enumerate() {
        let parts: Vec<&str> = line.split(' ').collect();
        let bad = if parts.len() != 4 {
            Some("fields")
        } else if !path_ok(parts[0]) {
            Some("path")
        } else if !num_ok(parts[1], 9) {
            Some("size")
        } else if !num_ok(parts[2], 10) {
            Some("mtime")
        } else if !id_ok(parts[3]) {
            Some("id")
        } else if out.contains_key(parts[0]) {
            Some("duplicate")
        } else {
            None
        };
        if let Some(b) = bad {
            return Err(format!("error: {} line {}: {}", label, n + 1, b));
        }
        out.insert(parts[0].to_string(), Entry { size: parts[1].parse().unwrap(), mtime: parts[2].parse().unwrap(), id: parts[3].to_string() });
    }
    Ok(out)
}

fn parse_rules(text: &str) -> Result<(Rules, Vec<String>), String> {
    let ls = split_lines(text);
    let mut r = Rules { mode: "mirror".to_string(), prune: false, ignore: Vec::new(), maxsize: None, prefer: None };
    let mut seen: HashSet<String> = HashSet::new();
    let mut base: Vec<String> = Vec::new();
    for (i, line) in ls.iter().enumerate() {
        if line == "--" {
            base = ls[i + 1..].to_vec();
            break;
        }
        let parts: Vec<&str> = line.split(' ').collect();
        let w = parts[0];
        let args = &parts[1..];
        let bad = |m: &str| format!("error: rules line {}: {}", i + 1, m);
        let known = w == "mode" || w == "prune" || (HAS_IGNORE && w == "ignore") || (HAS_MAXSIZE && w == "maxsize") || (HAS_PREFER && w == "prefer");
        if !known {
            return Err(bad("unknown"));
        }
        if w != "ignore" && seen.contains(w) {
            return Err(bad("duplicate"));
        }
        seen.insert(w.to_string());
        match w {
            "mode" => {
                if args.len() != 1 || !MODES.contains(&args[0]) {
                    return Err(bad("argument"));
                }
                r.mode = args[0].to_string();
            }
            "prune" => {
                if !args.is_empty() {
                    return Err(bad("argument"));
                }
                r.prune = true;
            }
            "ignore" => {
                if args.len() != 1 || args[0].is_empty() {
                    return Err(bad("argument"));
                }
                r.ignore.push(args[0].to_string());
            }
            "maxsize" => {
                if args.len() != 1 || !num_ok(args[0], 9) {
                    return Err(bad("argument"));
                }
                r.maxsize = Some(args[0].parse().unwrap());
            }
            "prefer" => {
                if args.len() != 1 || !(args[0] == "left" || args[0] == "right" || args[0] == "newer") {
                    return Err(bad("argument"));
                }
                r.prefer = Some(args[0].to_string());
            }
            _ => {}
        }
    }
    Ok((r, base))
}

fn gmatch(pat: &[u8], s: &[u8], i: usize, j: usize) -> bool {
    if i == pat.len() {
        return j == s.len();
    }
    if pat[i..].starts_with(b"**") {
        for k in j..=s.len() {
            if gmatch(pat, s, i + 2, k) {
                return true;
            }
        }
        return false;
    }
    let c = pat[i];
    if c == b'*' {
        let mut k = j;
        loop {
            if gmatch(pat, s, i + 1, k) {
                return true;
            }
            if k < s.len() && s[k] != b'/' {
                k += 1;
            } else {
                return false;
            }
        }
    }
    if c == b'?' {
        return j < s.len() && s[j] != b'/' && gmatch(pat, s, i + 1, j + 1);
    }
    j < s.len() && s[j] == c && gmatch(pat, s, i + 1, j + 1)
}

fn same(a: &Entry, b: &Entry) -> bool {
    match SAME {
        "id" => a.id == b.id,
        "sizeid" => a.size == b.size && a.id == b.id,
        _ => a.size == b.size && a.mtime == b.mtime,
    }
}

fn equiv(a: Option<&Entry>, b: Option<&Entry>) -> bool {
    match (a, b) {
        (None, None) => true,
        (Some(x), Some(y)) => same(x, y),
        _ => false,
    }
}

fn ancestors(p: &str) -> Vec<String> {
    let segs: Vec<&str> = p.split('/').collect();
    (1..segs.len()).map(|k| segs[..k].join("/")).collect()
}

fn side_file<'a>(d: &str, l: &'a Map, r: &'a Map) -> &'a Map {
    if d == TO_LEFT {
        l
    } else {
        r
    }
}

fn rank(d: &str) -> u8 {
    if d == TO_LEFT {
        1
    } else {
        0
    }
}

fn sort_key(l: &Line) -> &str {
    if l.kind == "move" {
        &l.q
    } else {
        &l.p
    }
}

fn sort_lines(ls: &mut Vec<Line>) {
    ls.sort_by(|a, b| sort_key(a).cmp(sort_key(b)).then(rank(&a.dir).cmp(&rank(&b.dir))));
}

fn filt(m: &Map, ignore: &[String]) -> Map {
    m.iter().filter(|(p, _)| !ignore.iter().any(|g| gmatch(g.as_bytes(), p.as_bytes(), 0, 0))).map(|(p, e)| (p.clone(), e.clone())).collect()
}

fn do_plan(left: &str, right: &str, rules_text: &str) -> Result<String, String> {
    let (r, base_lines) = parse_rules(rules_text)?;
    let l_all = parse_listing("left", &split_lines(left))?;
    let r_all = parse_listing("right", &split_lines(right))?;
    let b_all = parse_listing("base", &base_lines)?;
    let lf = filt(&l_all, &r.ignore);
    let rf = filt(&r_all, &r.ignore);
    let bf = filt(&b_all, &r.ignore);
    let mut lines: Vec<Line> = Vec::new();
    let transfer = |lines: &mut Vec<Line>, e: &Entry, to: &str, p: &str| {
        if let Some(mx) = r.maxsize {
            if e.size > mx {
                lines.push(mk("skip", "", p, ""));
                return;
            }
        }
        lines.push(mk("copy", to, p, ""));
    };
    if r.mode == "mirror" || r.mode == "newer" {
        let keys: BTreeSet<&String> = lf.keys().chain(rf.keys()).collect();
        for p in keys {
            match (lf.get(p), rf.get(p)) {
                (Some(l), None) => transfer(&mut lines, l, TO_RIGHT, p),
                (None, Some(_)) => {
                    if r.prune {
                        lines.push(mk("delete", TO_RIGHT, p, ""));
                    }
                }
                (Some(l), Some(rr)) => {
                    if !same(l, rr) {
                        if r.mode == "newer" && !(l.mtime > rr.mtime) {
                            lines.push(mk("skip", "", p, ""));
                        } else {
                            transfer(&mut lines, l, TO_RIGHT, p);
                        }
                    }
                }
                (None, None) => {}
            }
        }
    } else {
        let keys: BTreeSet<&String> = lf.keys().chain(rf.keys()).chain(bf.keys()).collect();
        for p in keys {
            let (l, rr, b) = (lf.get(p), rf.get(p), bf.get(p));
            if equiv(l, rr) {
                continue;
            }
            let lch = !equiv(l, b);
            let rch = !equiv(rr, b);
            let mut src: Option<char> = None;
            if lch && !rch {
                src = Some('l');
            } else if rch && !lch {
                src = Some('r');
            } else {
                match r.prefer.as_deref() {
                    Some("left") => src = Some('l'),
                    Some("right") => src = Some('r'),
                    Some("newer") => {
                        if let (Some(x), Some(y)) = (l, rr) {
                            src = if x.mtime > y.mtime {
                                Some('l')
                            } else if y.mtime > x.mtime {
                                Some('r')
                            } else {
                                None
                            };
                        } else {
                            src = Some(if l.is_some() { 'l' } else { 'r' });
                        }
                    }
                    _ => {}
                }
                if src.is_none() {
                    lines.push(mk("conflict", "", p, ""));
                    continue;
                }
            }
            let (ent, to) = if src == Some('l') { (l, TO_RIGHT) } else { (rr, TO_LEFT) };
            match ent {
                None => lines.push(mk("delete", to, p, "")),
                Some(e) => transfer(&mut lines, e, to, p),
            }
        }
        if HAS_MOVE {
            for to in [TO_RIGHT, TO_LEFT] {
                let src_map = if to == TO_RIGHT { &lf } else { &rf };
                let mut dels: HashMap<(String, i64), Vec<String>> = HashMap::new();
                let mut adds: HashMap<(String, i64), Vec<String>> = HashMap::new();
                for ln in &lines {
                    if ln.dir != to {
                        continue;
                    }
                    if ln.kind == "delete" {
                        let e = &bf[&ln.p];
                        dels.entry((e.id.clone(), e.size)).or_default().push(ln.p.clone());
                    } else if ln.kind == "copy" {
                        let e = &src_map[&ln.p];
                        adds.entry((e.id.clone(), e.size)).or_default().push(ln.p.clone());
                    }
                }
                let mut drop: Vec<Line> = Vec::new();
                let mut added: Vec<Line> = Vec::new();
                for (k, d) in &dels {
                    if d.len() == 1 {
                        if let Some(a) = adds.get(k) {
                            if a.len() == 1 {
                                drop.push(mk("delete", to, &d[0], ""));
                                drop.push(mk("copy", to, &a[0], ""));
                                added.push(mk("move", to, &d[0], &a[0]));
                            }
                        }
                    }
                }
                lines.retain(|ln| !drop.contains(ln));
                lines.extend(added);
            }
        }
    }
    if !HAS_DIRS {
        sort_lines(&mut lines);
    } else {
        let mut writes: Vec<(String, String)> = Vec::new();
        let mut removes: Vec<(String, String)> = Vec::new();
        for ln in &lines {
            match ln.kind {
                "copy" => writes.push((ln.dir.clone(), ln.p.clone())),
                "delete" => removes.push((ln.dir.clone(), ln.p.clone())),
                "move" => {
                    removes.push((ln.dir.clone(), ln.p.clone()));
                    writes.push((ln.dir.clone(), ln.q.clone()));
                }
                _ => {}
            }
        }
        let mut mkl: Vec<Line> = Vec::new();
        let mut rml: Vec<Line> = Vec::new();
        let mut made: HashSet<(String, String)> = HashSet::new();
        for (d, p) in &writes {
            let mut have: HashSet<String> = HashSet::new();
            for f in side_file(d, &l_all, &r_all).keys() {
                have.extend(ancestors(f));
            }
            for a in ancestors(p) {
                if !have.contains(&a) && made.insert((d.clone(), a.clone())) {
                    mkl.push(mk("mkdir", d, &a, ""));
                }
            }
        }
        let mut gone: HashSet<(String, String)> = HashSet::new();
        for d in [TO_RIGHT, TO_LEFT] {
            let mut fin: HashSet<String> = side_file(d, &l_all, &r_all).keys().cloned().collect();
            for (dd, p) in &removes {
                if dd.as_str() == d {
                    fin.remove(p);
                }
            }
            for (dd, p) in &writes {
                if dd.as_str() == d {
                    fin.insert(p.clone());
                }
            }
            let mut fdirs: HashSet<String> = HashSet::new();
            for f in &fin {
                fdirs.extend(ancestors(f));
            }
            for (dd, p) in &removes {
                if dd.as_str() == d {
                    for a in ancestors(p) {
                        if !fdirs.contains(&a) && gone.insert((d.to_string(), a.clone())) {
                            rml.push(mk("rmdir", d, &a, ""));
                        }
                    }
                }
            }
        }
        let mut main_l: Vec<Line> = lines.iter().filter(|l| l.kind != "delete").cloned().collect();
        let mut dels: Vec<Line> = lines.iter().filter(|l| l.kind == "delete").cloned().collect();
        sort_lines(&mut main_l);
        sort_lines(&mut dels);
        sort_lines(&mut mkl);
        rml.sort_by(|a, b| b.p.cmp(&a.p).then(rank(&a.dir).cmp(&rank(&b.dir))));
        lines = Vec::new();
        lines.extend(mkl);
        lines.extend(main_l);
        lines.extend(dels);
        lines.extend(rml);
    }
    Ok(render_lines(&lines, r.mode == "twoway"))
}

fn render_lines(lines: &[Line], two: bool) -> String {
    if lines.is_empty() {
        return INSYNC.to_string();
    }
    let mut out: Vec<String> = Vec::new();
    for ln in lines {
        let name = match ln.kind {
            "copy" => V_COPY,
            "delete" => V_DELETE,
            "skip" => V_SKIP,
            "conflict" => V_CONFLICT,
            "move" => V_MOVE,
            "mkdir" => V_MKDIR,
            _ => V_RMDIR,
        };
        let mut parts: Vec<&str> = vec![name];
        if two && ln.kind != "skip" && ln.kind != "conflict" {
            parts.push(&ln.dir);
        }
        parts.push(&ln.p);
        if !ln.q.is_empty() {
            parts.push(&ln.q);
        }
        out.push(parts.join(" "));
    }
    out.join("\n")
}

pub fn plan(left: &str, right: &str, rules: &str) -> String {
    match do_plan(left, right, rules) {
        Ok(s) => s,
        Err(e) => e,
    }
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
import java.util.TreeSet;

public class Syncplan {
    static final String SAME = @SAME@;
    static final String[] MODES = @MODES@;
    static final boolean HAS_IGNORE = @IGNORE@;
    static final boolean HAS_MAXSIZE = @MAXSIZE@;
    static final boolean HAS_MOVE = @MOVE@;
    static final boolean HAS_PREFER = @PREFER@;
    static final boolean HAS_DIRS = @DIRS@;
    static final String V_COPY = @V_COPY@;
    static final String V_DELETE = @V_DELETE@;
    static final String V_SKIP = @V_SKIP@;
    static final String V_CONFLICT = @V_CONFLICT@;
    static final String V_MOVE = @V_MOVE@;
    static final String V_MKDIR = @V_MKDIR@;
    static final String V_RMDIR = @V_RMDIR@;
    static final String TO_RIGHT = @TO_RIGHT@;
    static final String TO_LEFT = @TO_LEFT@;
    static final String INSYNC = @INSYNC@;

    static class Err extends RuntimeException {
        Err(String m) { super(m); }
    }

    static class Entry {
        long size, mtime;
        String id;
        Entry(long s, long m, String i) { size = s; mtime = m; id = i; }
    }

    static class Rules {
        String mode = "mirror";
        boolean prune;
        List<String> ignore = new ArrayList<>();
        long maxsize = -1;
        String prefer = null;
    }

    static class Line {
        String kind, dir, p, q;
        Line(String k, String d, String p, String q) { kind = k; dir = d; this.p = p; this.q = q; }
        String key() { return kind.equals("move") ? q : p; }
        int rank() { return TO_LEFT.equals(dir) ? 1 : 0; }
        boolean same(Line o) { return kind.equals(o.kind) && java.util.Objects.equals(dir, o.dir) && p.equals(o.p) && java.util.Objects.equals(q, o.q); }
    }

    static List<String> splitLines(String text) {
        List<String> out = new ArrayList<>();
        if (text.isEmpty()) return out;
        List<String> ls = new ArrayList<>(Arrays.asList(text.split("\n", -1)));
        if (ls.get(ls.size() - 1).isEmpty()) ls.remove(ls.size() - 1);
        return ls;
    }

    static boolean numOk(String s, int maxlen) {
        if (s.length() < 1 || s.length() > maxlen) return false;
        for (int i = 0; i < s.length(); i++) if (s.charAt(i) < '0' || s.charAt(i) > '9') return false;
        return s.length() == 1 || s.charAt(0) != '0';
    }

    static boolean pathOk(String p) {
        if (p.length() < 1 || p.length() > 60) return false;
        for (int i = 0; i < p.length(); i++) {
            char c = p.charAt(i);
            if (!(c >= 'a' && c <= 'z') && !(c >= 'A' && c <= 'Z') && !(c >= '0' && c <= '9') && c != '.' && c != '_' && c != '/' && c != '-') return false;
        }
        if (p.charAt(0) == '/' || p.charAt(p.length() - 1) == '/') return false;
        for (String s : p.split("/", -1)) if (s.isEmpty() || s.equals(".") || s.equals("..")) return false;
        return true;
    }

    static boolean idOk(String s) {
        if (s.length() < 1 || s.length() > 8) return false;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (!(c >= 'a' && c <= 'z') && !(c >= '0' && c <= '9')) return false;
        }
        return true;
    }

    static Map<String, Entry> parseListing(String label, List<String> lines) {
        Map<String, Entry> out = new HashMap<>();
        for (int n = 0; n < lines.size(); n++) {
            String[] parts = lines.get(n).split(" ", -1);
            String bad = null;
            if (parts.length != 4) bad = "fields";
            else if (!pathOk(parts[0])) bad = "path";
            else if (!numOk(parts[1], 9)) bad = "size";
            else if (!numOk(parts[2], 10)) bad = "mtime";
            else if (!idOk(parts[3])) bad = "id";
            else if (out.containsKey(parts[0])) bad = "duplicate";
            if (bad != null) throw new Err("error: " + label + " line " + (n + 1) + ": " + bad);
            out.put(parts[0], new Entry(Long.parseLong(parts[1]), Long.parseLong(parts[2]), parts[3]));
        }
        return out;
    }

    static Err ruleErr(int i, String m) {
        return new Err("error: rules line " + (i + 1) + ": " + m);
    }

    static List<String> baseLines = new ArrayList<>();

    static Rules parseRules(String text) {
        List<String> ls = splitLines(text);
        Rules r = new Rules();
        Set<String> seen = new HashSet<>();
        baseLines = new ArrayList<>();
        for (int i = 0; i < ls.size(); i++) {
            String ln = ls.get(i);
            if (ln.equals("--")) {
                baseLines = new ArrayList<>(ls.subList(i + 1, ls.size()));
                break;
            }
            String[] parts = ln.split(" ", -1);
            String w = parts[0];
            String[] args = Arrays.copyOfRange(parts, 1, parts.length);
            boolean known = w.equals("mode") || w.equals("prune") || (HAS_IGNORE && w.equals("ignore")) || (HAS_MAXSIZE && w.equals("maxsize")) || (HAS_PREFER && w.equals("prefer"));
            if (!known) throw ruleErr(i, "unknown");
            if (!w.equals("ignore") && seen.contains(w)) throw ruleErr(i, "duplicate");
            seen.add(w);
            switch (w) {
                case "mode": {
                    boolean ok = false;
                    if (args.length == 1) for (String m : MODES) if (m.equals(args[0])) ok = true;
                    if (!ok) throw ruleErr(i, "argument");
                    r.mode = args[0];
                    break;
                }
                case "prune":
                    if (args.length != 0) throw ruleErr(i, "argument");
                    r.prune = true;
                    break;
                case "ignore":
                    if (args.length != 1 || args[0].isEmpty()) throw ruleErr(i, "argument");
                    r.ignore.add(args[0]);
                    break;
                case "maxsize":
                    if (args.length != 1 || !numOk(args[0], 9)) throw ruleErr(i, "argument");
                    r.maxsize = Long.parseLong(args[0]);
                    break;
                case "prefer":
                    if (args.length != 1 || !(args[0].equals("left") || args[0].equals("right") || args[0].equals("newer"))) throw ruleErr(i, "argument");
                    r.prefer = args[0];
                    break;
                default:
                    break;
            }
        }
        return r;
    }

    static boolean gmatch(String pat, String s, int i, int j) {
        if (i == pat.length()) return j == s.length();
        if (pat.startsWith("**", i)) {
            for (int k = j; k <= s.length(); k++) if (gmatch(pat, s, i + 2, k)) return true;
            return false;
        }
        char c = pat.charAt(i);
        if (c == '*') {
            int k = j;
            while (true) {
                if (gmatch(pat, s, i + 1, k)) return true;
                if (k < s.length() && s.charAt(k) != '/') k++;
                else return false;
            }
        }
        if (c == '?') return j < s.length() && s.charAt(j) != '/' && gmatch(pat, s, i + 1, j + 1);
        return j < s.length() && s.charAt(j) == c && gmatch(pat, s, i + 1, j + 1);
    }

    static boolean same(Entry a, Entry b) {
        if (SAME.equals("id")) return a.id.equals(b.id);
        if (SAME.equals("sizeid")) return a.size == b.size && a.id.equals(b.id);
        return a.size == b.size && a.mtime == b.mtime;
    }

    static boolean equiv(Entry a, Entry b) {
        if (a == null || b == null) return a == null && b == null;
        return same(a, b);
    }

    static List<String> ancestors(String p) {
        String[] segs = p.split("/", -1);
        List<String> out = new ArrayList<>();
        for (int k = 1; k < segs.length; k++) out.add(String.join("/", Arrays.asList(segs).subList(0, k)));
        return out;
    }

    static List<String> sortedKeys(List<Map<String, Entry>> ms) {
        TreeSet<String> set = new TreeSet<>();
        for (Map<String, Entry> m : ms) set.addAll(m.keySet());
        return new ArrayList<>(set);
    }

    static Map<String, Entry> filt(Map<String, Entry> m, Rules r) {
        Map<String, Entry> o = new HashMap<>();
        for (Map.Entry<String, Entry> e : m.entrySet()) {
            boolean live = true;
            for (String g : r.ignore) if (gmatch(g, e.getKey(), 0, 0)) live = false;
            if (live) o.put(e.getKey(), e.getValue());
        }
        return o;
    }

    static void sortLines(List<Line> ls) {
        Collections.sort(ls, (a, b) -> {
            int c = a.key().compareTo(b.key());
            return c != 0 ? c : Integer.compare(a.rank(), b.rank());
        });
    }

    static void transfer(List<Line> lines, Rules r, Entry e, String to, String p) {
        if (r.maxsize >= 0 && e.size > r.maxsize) lines.add(new Line("skip", null, p, null));
        else lines.add(new Line("copy", to, p, null));
    }

    static String doPlan(String left, String right, String rulesText) {
        Rules r = parseRules(rulesText);
        Map<String, Entry> L = parseListing("left", splitLines(left));
        Map<String, Entry> R = parseListing("right", splitLines(right));
        Map<String, Entry> B = parseListing("base", baseLines);
        Map<String, Entry> Lf = filt(L, r), Rf = filt(R, r), Bf = filt(B, r);
        List<Line> lines = new ArrayList<>();
        if (r.mode.equals("mirror") || r.mode.equals("newer")) {
            for (String p : sortedKeys(Arrays.asList(Lf, Rf))) {
                Entry l = Lf.get(p), rr = Rf.get(p);
                if (l != null && rr == null) transfer(lines, r, l, TO_RIGHT, p);
                else if (rr != null && l == null) {
                    if (r.prune) lines.add(new Line("delete", TO_RIGHT, p, null));
                } else if (!same(l, rr)) {
                    if (r.mode.equals("newer") && !(l.mtime > rr.mtime)) lines.add(new Line("skip", null, p, null));
                    else transfer(lines, r, l, TO_RIGHT, p);
                }
            }
        } else {
            for (String p : sortedKeys(Arrays.asList(Lf, Rf, Bf))) {
                Entry l = Lf.get(p), rr = Rf.get(p), b = Bf.get(p);
                if (equiv(l, rr)) continue;
                boolean lch = !equiv(l, b), rch = !equiv(rr, b);
                String src = null;
                if (lch && !rch) src = "l";
                else if (rch && !lch) src = "r";
                else {
                    String pf = r.prefer;
                    if ("left".equals(pf)) src = "l";
                    else if ("right".equals(pf)) src = "r";
                    else if ("newer".equals(pf)) {
                        if (l != null && rr != null) src = l.mtime > rr.mtime ? "l" : rr.mtime > l.mtime ? "r" : null;
                        else src = l != null ? "l" : "r";
                    }
                    if (src == null) {
                        lines.add(new Line("conflict", null, p, null));
                        continue;
                    }
                }
                Entry ent = src.equals("l") ? l : rr;
                String to = src.equals("l") ? TO_RIGHT : TO_LEFT;
                if (ent == null) lines.add(new Line("delete", to, p, null));
                else transfer(lines, r, ent, to, p);
            }
            if (HAS_MOVE) {
                for (String to : new String[] { TO_RIGHT, TO_LEFT }) {
                    Map<String, Entry> srcMap = to.equals(TO_RIGHT) ? Lf : Rf;
                    Map<String, List<String>> dels = new HashMap<>(), adds = new HashMap<>();
                    for (Line ln : lines) {
                        if (!to.equals(ln.dir)) continue;
                        if (ln.kind.equals("delete")) {
                            Entry e = Bf.get(ln.p);
                            dels.computeIfAbsent(e.id + "\u0001" + e.size, k -> new ArrayList<>()).add(ln.p);
                        } else if (ln.kind.equals("copy")) {
                            Entry e = srcMap.get(ln.p);
                            adds.computeIfAbsent(e.id + "\u0001" + e.size, k -> new ArrayList<>()).add(ln.p);
                        }
                    }
                    List<Line> drop = new ArrayList<>(), added = new ArrayList<>();
                    for (Map.Entry<String, List<String>> d : dels.entrySet()) {
                        List<String> a = adds.get(d.getKey());
                        if (d.getValue().size() == 1 && a != null && a.size() == 1) {
                            drop.add(new Line("delete", to, d.getValue().get(0), null));
                            drop.add(new Line("copy", to, a.get(0), null));
                            added.add(new Line("move", to, d.getValue().get(0), a.get(0)));
                        }
                    }
                    List<Line> kept = new ArrayList<>();
                    for (Line ln : lines) {
                        boolean dropIt = false;
                        for (Line dd : drop) if (dd.same(ln)) dropIt = true;
                        if (!dropIt) kept.add(ln);
                    }
                    kept.addAll(added);
                    lines = kept;
                }
            }
        }
        if (!HAS_DIRS) {
            sortLines(lines);
        } else {
            List<String[]> writes = new ArrayList<>(), removes = new ArrayList<>();
            for (Line ln : lines) {
                if (ln.kind.equals("copy")) writes.add(new String[] { ln.dir, ln.p });
                else if (ln.kind.equals("delete")) removes.add(new String[] { ln.dir, ln.p });
                else if (ln.kind.equals("move")) {
                    removes.add(new String[] { ln.dir, ln.p });
                    writes.add(new String[] { ln.dir, ln.q });
                }
            }
            List<Line> mk = new ArrayList<>(), rm = new ArrayList<>();
            Set<String> made = new HashSet<>();
            for (String[] w : writes) {
                Set<String> have = new HashSet<>();
                for (String f : (w[0].equals(TO_LEFT) ? L : R).keySet()) have.addAll(ancestors(f));
                for (String a : ancestors(w[1])) {
                    if (!have.contains(a) && made.add(w[0] + "\u0001" + a)) mk.add(new Line("mkdir", w[0], a, null));
                }
            }
            Set<String> gone = new HashSet<>();
            for (String d : new String[] { TO_RIGHT, TO_LEFT }) {
                Set<String> fin = new HashSet<>((d.equals(TO_LEFT) ? L : R).keySet());
                for (String[] x : removes) if (x[0].equals(d)) fin.remove(x[1]);
                for (String[] x : writes) if (x[0].equals(d)) fin.add(x[1]);
                Set<String> fdirs = new HashSet<>();
                for (String f : fin) fdirs.addAll(ancestors(f));
                for (String[] x : removes) {
                    if (!x[0].equals(d)) continue;
                    for (String a : ancestors(x[1])) {
                        if (!fdirs.contains(a) && gone.add(d + "\u0001" + a)) rm.add(new Line("rmdir", d, a, null));
                    }
                }
            }
            List<Line> mainL = new ArrayList<>(), dels = new ArrayList<>();
            for (Line ln : lines) (ln.kind.equals("delete") ? dels : mainL).add(ln);
            sortLines(mainL);
            sortLines(dels);
            sortLines(mk);
            Collections.sort(rm, (a, b) -> {
                int c = b.p.compareTo(a.p);
                return c != 0 ? c : Integer.compare(a.rank(), b.rank());
            });
            lines = new ArrayList<>(mk);
            lines.addAll(mainL);
            lines.addAll(dels);
            lines.addAll(rm);
        }
        return renderLines(lines, r.mode.equals("twoway"));
    }

    static String renderLines(List<Line> lines, boolean two) {
        if (lines.isEmpty()) return INSYNC;
        StringBuilder sb = new StringBuilder();
        for (Line ln : lines) {
            String name = ln.kind.equals("copy") ? V_COPY : ln.kind.equals("delete") ? V_DELETE : ln.kind.equals("skip") ? V_SKIP : ln.kind.equals("conflict") ? V_CONFLICT : ln.kind.equals("move") ? V_MOVE : ln.kind.equals("mkdir") ? V_MKDIR : V_RMDIR;
            if (sb.length() > 0) sb.append('\n');
            sb.append(name);
            if (two && !ln.kind.equals("skip") && !ln.kind.equals("conflict")) sb.append(' ').append(ln.dir);
            sb.append(' ').append(ln.p);
            if (ln.q != null) sb.append(' ').append(ln.q);
        }
        return sb.toString();
    }

    public static String plan(String left, String right, String rules) {
        try {
            return doPlan(left, right, rules);
        } catch (Err e) {
            return e.getMessage();
        }
    }
}
'''



GLOBS = ["*.tmp", "**/*.bak", "build/**", "docs/*", "?.log", "**.log", "src/**/*.o", "tmp/*", "*/cache", "a/**/c/*", "*"]
SIDES = [("right", "left"), ("l2r", "r2l"), ("->", "<-")]
VERBS = {"copy": ["copy", "push", "send"], "delete": ["delete", "remove", "drop"], "skip": ["skip", "hold", "defer"], "conflict": ["conflict", "clash", "diverge"], "move": ["move", "rename", "shift"],
         "mkdir": ["mkdir", "makedir", "newdir"], "rmdir": ["rmdir", "deldir", "prunedir"]}
THEMES = [
    ("the field-station backups", "The field station mirrors its logger folders to a shore server."),
    ("the quilt pattern library", "The quilt pattern library is kept in step between two laptops."),
    ("the lighthouse log archive", "The lighthouse log archive is synchronised with a harbour office."),
    ("the seed catalogue folders", "The seed catalogue is copied between the greenhouse and the shop."),
    ("the ferry timetable store", "The ferry timetable store is distributed to the ticket kiosks."),
]
DIRN = ["", "docs/", "docs/img/", "src/", "src/lib/", "notes/2024/", "a/b/c/", "build/", "tmp/", "a/", "a/b/"]
FNAMES = ["readme.md", "main.c", "util.h", "photo.jpg", "data.csv", "x.tmp", "old.bak", "log.txt", "a.log", "z", "plan.txt", "q.dat", "cache", "m.o", "t.log"]


def params(rng, level, i):
    pick = lambda k: rng.choice(VERBS[k])  # noqa: E731
    r, l = SIDES[(i + rng.randrange(2)) % len(SIDES)]
    return {
        "level": level, "same": rng.choice(["id", "sizeid", "sizemtime"]),
        "modes": ["mirror"] if level == 1 else ["mirror", "newer"] if level == 2 else ["mirror", "newer", "twoway"],
        "ignore": level >= 2, "maxsize": level >= 2, "move": level >= 4, "prefer": level >= 4, "dirs": level >= 5,
        "v": {k: pick(k) for k in VERBS}, "to_right": r, "to_left": l, "insync": rng.choice(["in sync", "nothing to do", "up to date"]), "theme": THEMES[(i + rng.randrange(2)) % len(THEMES)],
    }


def sol(lang, p):
    src = {"python": PY, "go": GO, "rust": RS, "java": JV}[lang]
    L = lambda s: K.lit(lang, s)  # noqa: E731
    b = (lambda v: "True" if v else "False") if lang == "python" else (lambda v: "true" if v else "false")  # noqa: E731
    ms = p["modes"]
    modes = "[" + ", ".join(L(m) for m in ms) + "]" if lang in ("python", "rust") else "{" + ", ".join(L(m) for m in ms) + "}"
    return K.subst(
        src, SAME=L(p["same"]), MODES=modes, IGNORE=b(p["ignore"]), MAXSIZE=b(p["maxsize"]), MOVE=b(p["move"]), PREFER=b(p["prefer"]), DIRS=b(p["dirs"]),
        V_COPY=L(p["v"]["copy"]), V_DELETE=L(p["v"]["delete"]), V_SKIP=L(p["v"]["skip"]), V_CONFLICT=L(p["v"]["conflict"]), V_MOVE=L(p["v"]["move"]), V_MKDIR=L(p["v"]["mkdir"]), V_RMDIR=L(p["v"]["rmdir"]),
        TO_RIGHT=L(p["to_right"]), TO_LEFT=L(p["to_left"]), INSYNC=L(p["insync"]),
    ).lstrip("\n")


def py_fix(src, p):
    """The Python template keeps string markers inside quotes; fill them literally."""
    return src


# ---------------------------------------------------------------------------------------------------------------
# scenarios


def rid(rng):
    return "".join(rng.choice("abcdef0123456789") for _ in range(rng.randint(2, 6)))


def rand_entry(rng):
    return (rng.choice([0, 1, 10, 80, 4096, 5000, 5001, rng.randrange(0, 200000)]), rng.choice([rng.randrange(1, 9999), rng.randrange(100000, 2000000000)]), rid(rng))


def universe(rng, n):
    base = {}
    while len(base) < n:
        base[rng.choice(DIRN) + rng.choice(FNAMES)] = rand_entry(rng)
    return base


def mutate(rng, base, wild=1.0):
    side = {}
    for path, (sz, mt, i) in base.items():
        r = rng.random()
        if r < 0.4 / wild:
            side[path] = (sz, mt, i)
        elif r < 0.55:
            side[path] = (sz, mt + rng.randint(1, 50), i)
        elif r < 0.7:
            side[path] = (rng.choice([sz + 1, sz * 2, rng.randrange(0, 9000)]), mt + rng.choice([0, 5, -3]) if mt > 10 else mt, rid(rng))
        elif r < 0.8:
            pass
        elif r < 0.9:
            side[rng.choice(DIRN) + rng.choice(FNAMES)] = (sz, mt, i)
        else:
            side[path] = (sz, mt, i)
    for _ in range(rng.randint(0, 2)):
        pth = rng.choice(DIRN) + rng.choice(FNAMES)
        if pth not in side:
            side[pth] = rand_entry(rng) if rng.random() < 0.7 or not base else rng.choice(list(base.values()))
    return side


def listing(rng, d, shuffle=True):
    ls = [f"{p} {e[0]} {e[1]} {e[2]}" for p, e in d.items()]
    if shuffle:
        rng.shuffle(ls)
    else:
        ls.sort()
    return "\n".join(ls) + ("\n" if ls and rng.random() < 0.3 else "")


def rand_rules(rng, p, mode, base):
    ls = []
    if mode != "mirror" or rng.random() < 0.2:
        ls.append(f"mode {mode}")
    if rng.random() < 0.45:
        ls.append("prune")
    if p["ignore"] and rng.random() < 0.5:
        ls += ["ignore " + g for g in rng.sample(GLOBS[:-1], rng.randint(1, 2))]
    if p["maxsize"] and rng.random() < 0.35:
        ls.append(f"maxsize {rng.choice([100, 5000, 5000, 100000])}")
    if p["prefer"] and mode == "twoway" and rng.random() < 0.45:
        ls.append("prefer " + rng.choice(["left", "right", "newer"]))
    rng.shuffle(ls)
    if mode == "twoway" or (rng.random() < 0.1 and base):
        ls.append("--")
        ls += [f"{pp} {e[0]} {e[1]} {e[2]}" for pp, e in base.items()]
    return "\n".join(ls)


def make_cases(rng, p, ns):
    plan = ns["plan"]
    cases = []
    L = p["level"]

    def add(a, b, c=""):
        cases.append((a, b, c))

    # random scenarios
    modes = p["modes"]
    for _ in range(72 if L >= 3 else 52):
        mode = rng.choice(modes) if L < 3 else rng.choice(["twoway", "twoway", "mirror", "newer"])
        base = universe(rng, rng.randint(2, 8))
        if mode == "twoway" and rng.random() < 0.3:
            # one-sided changes: the usual two-way situation
            left = mutate(rng, base, 1.0)
            right = dict(base)
            if rng.random() < 0.5:
                left, right = right, left
        else:
            left, right = mutate(rng, base), mutate(rng, base)
        rules = rand_rules(rng, p, mode, base)
        add(listing(rng, left), listing(rng, right), rules)
    # renames, duplicates of content
    if p["move"]:
        for k in range(14):
            base = universe(rng, rng.randint(3, 7))
            left = dict(base)
            right = dict(base)
            keys = sorted(base)
            for q in rng.sample(keys, rng.randint(1, min(3, len(keys)))):
                e = left.pop(q)
                left[rng.choice(DIRN) + rng.choice(FNAMES) + rng.choice(["", ".v2"])] = e
            if k % 3 == 1:
                dup = rng.choice(list(base.values()))
                left["dup/one.txt"] = dup
                left["dup/two.txt"] = dup
                base["dup/old.txt"] = dup
                right["dup/old.txt"] = dup
            if k % 3 == 2:
                q = rng.choice(keys)
                if q in right:
                    right[q] = (right[q][0], right[q][1] + 7, rid(rng))  # modified on the other side: no move
            if k % 4 == 3:
                left, right = right, left
            add(listing(rng, left), listing(rng, right), rand_rules(rng, p, "twoway", base))
    # directories
    if p["dirs"]:
        for k in range(12):
            base = universe(rng, rng.randint(3, 7))
            base["deep/er/path/file.txt"] = rand_entry(rng)
            left, right = mutate(rng, base), mutate(rng, base)
            if k % 2:
                for q in list(right):
                    if q.startswith("deep/"):
                        right.pop(q)
            mode = rng.choice(["mirror", "twoway", "twoway", "newer"])
            add(listing(rng, left), listing(rng, right), rand_rules(rng, p, mode, base))
    # hand-written listings
    A = "a/x.txt 5 100 aa11\nb.txt 7 200 bb22\nc.log 3 50 cc33\n"
    Bq = "b.txt 7 200 bb22\nc.log 3 60 cc33\nd/e.txt 9 1 dd44\n"
    for rules in ["", "prune", "mode mirror", "mode mirror\nprune", "prune\nmode mirror"]:
        add(A, Bq, rules)
    add("", "", "")
    add("", "", "prune")
    add(A, "", "")
    add("", A, "")
    add("", A, "prune")
    add(A.rstrip("\n"), A, "")
    add(A, A, "")
    add(A, A, "prune")
    if p["same"] == "id":
        add("f 1 1 aa", "f 2 2 aa", "")
        add("f 1 1 aa", "f 1 1 ab", "")
    elif p["same"] == "sizeid":
        add("f 1 1 aa", "f 1 2 aa", "")
        add("f 1 1 aa", "f 2 1 aa", "")
        add("f 1 1 aa", "f 1 1 ab", "")
    else:
        add("f 1 1 aa", "f 1 1 zz", "")
        add("f 1 1 aa", "f 1 2 aa", "")
        add("f 1 1 aa", "f 2 1 aa", "")
    # listing errors
    errs = ["a", "a 1", "a 1 2", "a 1 2 x y", "a  1 2 x", " a 1 2 x", "a 1 2 x ", "a 1 2  x", "a\t1 2 x", "/a 1 2 x", "a/ 1 2 x", "a//b 1 2 x", "./a 1 2 x", "a/./b 1 2 x", "../a 1 2 x", "a/.. 1 2 x", "a b 1 2 x", "a$ 1 2 x", "a 01 2 x", "a -1 2 x", "a 1.5 2 x", "a 1234567890 2 x",
            "a 123456789 2 x", "a 1 01 x", "a 1 -2 x", "a 1 12345678901 x", "a 1 1234567890 x", "a 1 2 X", "a 1 2 x-y", "a 1 2 123456789", "a 1 2 12345678", "a 1 2 ab_c", "", " ", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa 1 2 x", "a" * 60 + " 1 2 x", "é 1 2 x"[:0] + "a 1 2 x"]
    for e in errs:
        for where in (0, 1, 2):
            good = "ok.txt 1 1 aa"
            txt = e if rng.random() < 0.5 else good + "\n" + e
            if where == 0:
                add(txt, good, "")
            elif where == 1:
                add(good, txt, "")
            elif p["modes"][-1] == "twoway":
                add(good, good, "mode twoway\n--\n" + txt)
            else:
                add(good, good, "--\n" + txt)
    add("a 1 1 x\na 2 2 y", "", "")
    add("", "b 1 1 x\nb 1 1 x\n", "")
    add("a 1 1 x\n\nb 1 1 x", "", "")
    add("a 1 1 x\n\n", "", "")
    add("\n", "", "")
    add("a 1 1 x\nbad", "also bad", "")
    add("a 1 1 x", "also bad", "bogus")
    # rules errors
    rerr = ["bogus", "prune now", "mode", "mode  mirror", "mode mirror mirror", "mode Mirror", "mode bogus", "prune\nprune", "mode mirror\nmode mirror", "", "\n", "prune\n\nmode mirror", " prune", "prune ", "PRUNE", "mode: mirror", "ignore", "ignore *.tmp", "maxsize 5", "prefer left",
            "mode twoway", "mode newer", "--", "--\n", "prune\n--\nbad line", "-- ", "---", "prune\n--\na 1 1 x\na 1 1 x"]
    if p["ignore"]:
        rerr += ["ignore", "ignore ", "ignore a b", "ignore *.tmp\nignore *.bak", "ignore *.tmp\nignore *.tmp", "ignore  x"]
    if p["maxsize"]:
        rerr += ["maxsize", "maxsize 0", "maxsize 007", "maxsize -1", "maxsize 1.5", "maxsize 1234567890", "maxsize 123456789", "maxsize 5\nmaxsize 6", "maxsize x", "maxsize 5 6"]
    if p["prefer"]:
        rerr += ["prefer", "prefer both", "prefer left\nprefer right", "prefer Left", "prefer newer extra"]
    for rl in rerr:
        add(A, Bq, rl)
        if rng.random() < 0.3:
            add("bad", Bq, rl)
    # ignore globs
    if p["ignore"]:
        fl = "".join(f"{q} 1 1 aa\n" for q in ["a.tmp", "x/b.tmp", "x/y/c.tmp", "tmp/d", "tmp/e/f", "build/g.o", "build/h/i.o", "docs/j.md", "docs/img/k.png", "notes.bak", "x/notes.bak", "a.log", "ab.log", "x/a.log", "src/m.o", "src/lib/n.o", "src/lib/deep/o.o", "a/b/c/z", "a/b/q/c/z", "z/cache", "cache", "docs/cache"])
        for g in GLOBS:
            add(fl, "", f"ignore {g}")
        add(fl, "other 1 1 aa", "ignore *.tmp\nignore **/*.bak\nignore build/**\nprune")
        add(fl, fl, "ignore **")
        add(fl, "", "ignore a.tmp")
        add(fl, "", "ignore a")
        add(fl, "", "ignore ?")
        add(fl, "", "ignore ***")
        add(fl, "", "ignore **/**")
        add(fl, "", "ignore a/*/c/*")
        add(fl, "", "ignore **cache")
        add(fl, "", "ignore *cache")
        add(fl, "", "ignore */*.tmp")
        add(fl, "", "ignore **/*.tmp")
        add(fl, "", "ignore ?.tmp")
        add(fl, "", "ignore a.???")
        add(fl, "", "ignore .*")
        add(fl, "", "ignore tmp/**")
        add(fl, "", "ignore tmp/*")
    # maxsize and newer
    if p["maxsize"]:
        for mx in (0, 1, 79, 80, 81, 4096, 5000, 5001, 999999999):
            add("a 80 1 aa\nb 81 1 bb\nc 5000 1 cc\nd 5001 1 dd\ne 0 1 ee\n", "a 1 1 xx\nb 1 1 yy\n", f"maxsize {mx}")
    for rl in ("mode newer", "mode newer\nprune"):
        if "newer" in p["modes"]:
            add("a 1 5 aa\nb 1 5 bb\nc 1 5 cc\nd 1 5 dd\ne 2 9 ee", "a 1 4 xx\nb 1 5 yy\nc 1 6 zz\nd 1 5 dd\nf 1 1 ff", rl)
    # two-way table: every combination of presence and change
    if "twoway" in p["modes"]:
        ents = {"-": None, "a": (1, 1, "aa"), "b": (2, 2, "bb"), "c": (3, 3, "cc"), "a2": (1, 2, "aa"), "b5": (2, 5, "bb")}
        n = 0
        for bk in ("-", "a", "b"):
            for lk in ents:
                for rk in ents:
                    n += 1
                    if n % 2 and rng.random() < 0.5:
                        continue
                    L_, R_, B_ = ({"p": ents[k]} if ents[k] else {} for k in (lk, rk, bk))
                    add(listing(rng, L_), listing(rng, R_), "mode twoway\n--\n" + listing(rng, B_).rstrip("\n"))
                    if p["prefer"] and rng.random() < 0.3:
                        add(listing(rng, L_), listing(rng, R_), "mode twoway\nprefer " + rng.choice(["left", "right", "newer"]) + "\n--\n" + listing(rng, B_).rstrip("\n"))
    # dedupe, examples first
    ex = []
    ex.append(("a.txt 10 100 ab12\nnotes.md 4 90 c0de", "notes.md 4 90 c0de", ""))
    if "newer" in p["modes"]:
        ex.append(("a.txt 10 100 ab12\nb.txt 3 50 ee01", "a.txt 11 90 ab13\nb.txt 3 50 ee01\nold.txt 1 1 aa", "mode newer\nprune" if not p["ignore"] else "mode newer\nprune\nignore *.tmp"))
    if "twoway" in p["modes"]:
        ex.append(("a.txt 10 100 ab12\nnew.txt 1 120 f1", "a.txt 10 100 ab12\ngone.txt 5 80 d2", "mode twoway\n--\na.txt 10 100 ab12\ngone.txt 5 80 d2"))
    if p["move"]:
        ex.append(("docs/new.txt 5 60 e5e5\nx.txt 1 1 aa", "docs/old.txt 5 60 e5e5\nx.txt 1 1 aa", "mode twoway\n--\ndocs/old.txt 5 60 e5e5\nx.txt 1 1 aa"))
    nex = len(ex)
    allc = ex + cases
    out, seen = [], set()
    for c in allc:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex


def readme(p, api, lang, examples):
    v, R_, L_ = p["v"], p["to_right"], p["to_left"]
    S = {"id": "their IDs are equal (size and modification time are ignored)", "sizeid": "their SIZE and ID are both equal (the modification time is ignored)", "sizemtime": "their SIZE and MTIME are both equal (the ID is ignored)"}[p["same"]]
    X = []
    X.append(f"# File-sync planner for {p['theme'][0]}")
    X.append("")
    X.append(f"{p['theme'][1]} `plan(left, right, rules)` compares two directory listings and returns the list of actions that would bring them into line. Nothing is touched: the result is only text.")
    X.append("")
    X.append("## Listings")
    X.append("")
    X.append("A listing is text made of lines separated by `\\n`: the empty text is an empty listing, one final `\\n` is allowed, and any other empty line is an error. Each line describes one file with four fields separated by **single spaces**:")
    X.append("")
    X.append("    PATH SIZE MTIME ID")
    X.append("")
    X.append("* `PATH`: 1 to 60 characters from ASCII letters, digits, `.`, `_`, `-` and `/`; it does not start or end with `/`, has no empty segment (`//`), and no segment is `.` or `..`.")
    X.append("* `SIZE`: a decimal number of at most 9 digits, no leading zeros (`0` itself is fine). `MTIME`: the modification time, the same way but at most 10 digits.")
    X.append("* `ID`: 1 to 8 characters, lower-case letters and digits, standing for the file's content.")
    X.append("")
    X.append(f"A path appears at most once in a listing. Two entries for the same path are **the same** when {S}.")
    X.append("")
    X.append("## Rules")
    X.append("")
    X.append("`rules` is text in the same line format (lines separated by `\\n`, one final `\\n` allowed, no empty lines; empty text is fine). Each line is a directive: a word followed by its arguments, all separated by single spaces. A line that is exactly `--` ends the directives; the lines after it form the **base listing**, written in the listing format above. The base listing is only used by `mode twoway`" + (" (it is still checked in every mode)." if True else "."))
    X.append("")
    ds = [f"* `mode MODE`: `MODE` is one of " + ", ".join(f"`{m}`" for m in p["modes"]) + ". Default `mirror`."]
    ds.append("* `prune`: no arguments." + (" See `mirror`." if True else ""))
    if p["ignore"]:
        ds.append("* `ignore GLOB`: one non-empty argument (see *Ignoring*). May appear several times.")
    if p["maxsize"]:
        ds.append("* `maxsize N`: `N` a decimal number as in `SIZE`.")
    if p["prefer"]:
        ds.append("* `prefer WHO`: `WHO` is `left`, `right` or `newer` (see *Conflicts*).")
    X += ds
    X.append("")
    X.append("Every directive except `ignore` may appear at most once. A rules problem is reported as `error: rules line N: WHY` (`N` counts from 1), for the first line that has one, with `WHY` being `unknown` for a word that is not a directive of this list (an empty line counts), then `duplicate` for a second use, then `argument` for a wrong number of arguments or an invalid argument.")
    X.append("")
    X.append("## The plan")
    X.append("")
    X.append(f"The result is one action per line, joined by `\\n` with no trailing newline, or `{p['insync']}` when there is nothing to do. In the descriptions `PATH` ranges over the paths of all listings, in ascending **byte order** (plain ASCII order, so `A` before `a` and `-` before `/`).")
    X.append("")
    X.append("### Mirror")
    X.append("")
    X.append(f"In `mirror` mode (the default) `left` is the source and `right` the target. For every path:")
    X.append("")
    X.append(f"* only in `left`: `{v['copy']} PATH`.")
    X.append(f"* only in `right`: `{v['delete']} PATH` if `prune` is set, otherwise nothing.")
    X.append(f"* in both and the same: nothing. In both but not the same: `{v['copy']} PATH`.")
    X.append("")
    if "newer" in p["modes"]:
        X.append("### Newer")
        X.append("")
        X.append(f"`mode newer` is like `mirror`, except that a path in both listings that is not the same is copied only if the `left` MTIME is **strictly greater** than the `right` MTIME; otherwise the line is `{v['skip']} PATH`.")
        X.append("")
    if p["maxsize"]:
        X.append("### Size limit")
        X.append("")
        X.append(f"With `maxsize N`, any `{v['copy']}` line that would be produced for a file whose SIZE is greater than `N` is replaced by `{v['skip']} PATH`. (The size is that of the file that would be copied: the source.)")
        X.append("")
    if p["ignore"]:
        X.append("### Ignoring")
        X.append("")
        X.append("A path matching any `ignore` glob does not exist as far as the plan is concerned: it is dropped from `left`, `right` and the base listing before anything else happens (so it is never copied, deleted or counted). A glob must match the **whole** path. `?` matches one character other than `/`; `*` matches any run of characters (possibly empty) other than `/`; `**` matches any run of characters (possibly empty) including `/`; every other character matches itself. A run of stars is read left to right, taking `**` first.")
        X.append("")
    if "twoway" in p["modes"]:
        X.append("### Two-way")
        X.append("")
        X.append(f"`mode twoway` changes both sides. For every path let `L`, `R` and `B` be the entry in `left`, `right` and the base listing (or *absent*). Two entries are equivalent if both are absent or both are present and the same. Then:")
        X.append("")
        X.append("1. if `L` and `R` are equivalent: nothing.")
        X.append("2. otherwise a side is *changed* when its entry is not equivalent to `B`. If only `L` changed, the change is carried from left to right; if only `R` changed, from right to left. If both changed (and differ from each other), it is a conflict.")
        X.append("")
        X.append(f"Carrying a change *to a side* gives `{v['copy']} DIR PATH` when the source side has the file and `{v['delete']} DIR PATH` when it is absent there, where `DIR` is `{R_}` for changes applied to the right side and `{L_}` for changes applied to the left side. A copy of a file larger than `maxsize` is `{v['skip']} PATH` instead (no `DIR`)." if p["maxsize"] else
                 f"Carrying a change *to a side* gives `{v['copy']} DIR PATH` when the source side has the file and `{v['delete']} DIR PATH` when it is absent there, where `DIR` is `{R_}` for changes applied to the right side and `{L_}` for changes applied to the left side.")
        X.append(f"A conflict is the line `{v['conflict']} PATH` (no `DIR`).")
        X.append("")
        if p["prefer"]:
            X.append("### Conflicts")
            X.append("")
            X.append("With `prefer left` every conflict is resolved as if only `L` had changed; `prefer right` as if only `R` had changed (even when that means deleting a file). With `prefer newer`: if both entries are present, the one with the greater MTIME wins (equal MTIME stays a conflict); if one side is absent, the side that **has** the file wins (so the file is copied, not deleted).")
            X.append("")
        if p["move"]:
            X.append("### Moves")
            X.append("")
            X.append(f"After the lines above are decided, for each direction separately: take the `{v['delete']} DIR` lines and the `{v['copy']} DIR` lines of that direction. A deleted file is described by its **base** entry, a copied file by its **source** entry; two files *match* when their IDs and sizes are both equal. If exactly one deleted file and exactly one copied file match each other (no other deleted or copied file of that direction has the same ID and size), the two lines are replaced by the single line `{v['move']} DIR FROM TO` (`FROM` the deleted path, `TO` the copied path). Lines already turned into `{v['skip']}` or `{v['conflict']}` take no part. A move line sorts under its `TO` path.")
            X.append("")
    X.append("### Order")
    X.append("")
    if p["dirs"]:
        X.append("Directories are implicit: they exist when some file lies below them. The listings of this task give files only, and the plan must also create and remove directories. After the lines above are decided (before sorting), add:")
        X.append("")
        X.append(f"* `{v['mkdir']}" + (" DIR" if "twoway" in p["modes"] else "") + " PATH` for every directory that a written file needs and that does not exist on that side. A file is *written* by a `" + v["copy"] + "` line or as the `TO` of a `" + v["move"] + "` line, and the directories needed are all its proper ancestors (`a/b` and `a` for `a/b/f`). A directory exists on a side if some file of that side's original listing (before ignoring anything) lies below it. Each directory is created once per side.")
        X.append(f"* `{v['rmdir']}" + (" DIR" if "twoway" in p["modes"] else "") + " PATH` for every directory on a side that holds no file any more after the plan: take the files of that side's original listing, remove those deleted (or moved away, the `FROM` of a `" + v["move"] + "` line) and add those written, and report every proper ancestor of a removed file that is not an ancestor of any remaining file. Each directory once per side.")
        X.append("")
        X.append(f"The lines are then written in four groups: all `{v['mkdir']}` lines; then every line that is not a `{v['delete']}`, `{v['mkdir']}` or `{v['rmdir']}` line; then the `{v['delete']}` lines; then the `{v['rmdir']}` lines. Within a group lines are in ascending order of their path (`TO` for moves, the directory for `{v['mkdir']}`), except the `{v['rmdir']}` group which is in **descending** path order. Two lines with the same path (the same directory on both sides) put the `{R_}` line first." if "twoway" in p["modes"] else
                 f"The lines are then written in four groups: all `{v['mkdir']}` lines; then every line that is not a `{v['delete']}`, `{v['mkdir']}` or `{v['rmdir']}` line; then the `{v['delete']}` lines; then the `{v['rmdir']}` lines. Within a group lines are in ascending order of their path (the directory for `{v['mkdir']}`), except the `{v['rmdir']}` group which is in **descending** path order.")
        X.append("")
        if "twoway" in p["modes"]:
            X.append("In `mirror` and `newer` mode there is no `DIR` word anywhere (`" + v["copy"] + " PATH`, `" + v["delete"] + " PATH`, `" + v["mkdir"] + " PATH`, `" + v["rmdir"] + " PATH`); every action is applied to the right side. In `twoway` mode `" + v["skip"] + "` and `" + v["conflict"] + "` have no `DIR` either.")
            X.append("")
    else:
        if "twoway" in p["modes"]:
            X.append(f"Lines are sorted by their path (the `TO` path for moves), ascending in byte order; every path has at most one line. In `mirror` and `newer` mode lines are written as `VERB PATH` (every action applies to the right side); in `twoway` mode `{v['copy']}` and `{v['delete']}`" + (f" and `{v['move']}`" if p["move"] else "") + " carry the `DIR` word, `" + v["skip"] + "` and `" + v["conflict"] + "` do not.")
        else:
            X.append("Lines are sorted by path, ascending in byte order; every path has at most one line. Lines are written as `VERB PATH` (every action applies to the right side).")
        X.append("")
    X.append("## Errors")
    X.append("")
    X.append("Problems are reported instead of a plan, in this order (the first applies):")
    X.append("")
    X.append("1. `error: rules line N: WHY` as described above.")
    X.append("2. `error: left line N: WHY`, then `error: right line N: WHY`, then `error: base line N: WHY` (the line number counts inside that listing, for base from the line after `--`). In each listing the first bad line is reported. `WHY` is `fields` (not exactly four fields), then `path`, `size`, `mtime`, `id` (the first invalid field), and `duplicate` for a path that already appeared.")
    X.append("")
    X.append(K.interface_section(api, lang))
    X.append("## Examples")
    X.append("")
    for k, ((a, b, c), out) in enumerate(examples):
        X.append(f"**Example {k + 1}**")
        X.append("")
        X.append("```")
        X.append("left:")
        X += ["  " + ln for ln in a.split("\n")] if a else ["  (empty)"]
        X.append("right:")
        X += ["  " + ln for ln in b.split("\n")] if b else ["  (empty)"]
        X.append("rules:")
        X += ["  " + ln for ln in c.split("\n")] if c else ["  (empty)"]
        X.append("plan:")
        X += ["  " + ln for ln in out.split("\n")]
        X.append("```")
        X.append("")
    X.append(K.run_hint(lang, api.mod))
    return "\n".join(X) + "\n"


def prompt(rng, p, api, lang):
    where = api.short(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    feats = ["one-way mirroring"] + (["ignore globs, a size limit and a `newer` mode"] if p["ignore"] else []) + (["two-way sync against a base listing"] if "twoway" in p["modes"] else []) + (["rename detection and conflict preferences"] if p["move"] else []) + (["directory creation and removal"] if p["dirs"] else [])
    fl = ", ".join(feats[:-1]) + (" and " if len(feats) > 1 else "") + feats[-1]
    opts = [
        f"Keeping {p['theme'][0]} in sync needs a planner. Write `{fn}(left, right, rules)` in {ln}, in {where}: it only returns the action list, as specified in README.md ({fl}). {K.closer(rng)}",
        f"Implement the sync planner from README.md in {ln} (`{fn}`, {where}). This version covers {fl}. Output order and error priority are specified; hidden checks include malformed listings and rules. {K.closer(rng)}",
        f"{ln} task: build `{fn}` ({where}), a planner that turns two listings plus rules into a list of copy/delete actions. README.md has the format, the rules and the ordering. {K.closer(rng)}",
        f"Please write the file-sync planner described in README.md ({ln}; `{fn}` in {where}). Supported: {fl}.",
    ]
    return rng.choice(opts).strip()


LANG_PLAN = ["go", "rust", "java", "python", "go", "rust", "java", "go"]
LEVELS = [1, 1, 2, 2, 3, 3, 4, 5]


@family("greenfield-syncplan", category="greenfield", lang="mixed", kind="greenfield", n=8,
        summary="file-sync planner: mirror / newer / two-way with a base listing, globs, size limit, rename detection, conflict preferences and directory creation order")
def gen(rng, n):
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = LEVELS[i % len(LEVELS)]
        p = params(rng, level, i)
        api = K.Api(mod="syncplan", fn="plan", args=["left", "right", "rules"], arg_docs=["the left listing", "the right listing", "the rules text (directives, optionally `--` and a base listing)"], ret_doc="the action list, or an error text",
                    doc="file-sync planner")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["plan"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=level, slug=f"{i + 1:02d}-{lang}-{p['same']}-l{level}", oracle=(None if lang == "python" else ns["plan"]),
            tags=["planner", "parser"], notes={"level": level, "same": p["same"]},
        )
