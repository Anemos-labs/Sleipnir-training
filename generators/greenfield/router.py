"""In-process HTTP-style router: pattern syntax with typed parameters, specificity, 405 handling, wildcards, trailing slash and percent-decoding rules."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

SITES = ["the ferry booking API", "the Saltmarsh library service", "the lighthouse status page", "the tide-clock backend", "the Hollin allotment portal", "a harbour fee service"]
LANG_PLAN = ["javascript", "go", "java", "ruby", "javascript", "go", "java", "ruby", "javascript", "go", "java", "ruby"]
ALL_TYPES = ["int", "slug", "alpha", "hex"]


def params(rng, level, i):
    types = rng.sample(ALL_TYPES, rng.choice([2, 3])) if level >= 3 else []
    return {
        "level": level, "site": rng.choice(SITES), "methods": level >= 3, "types": types, "wild": level >= 4, "slash": rng.choice(["strict", "lenient"]) if level >= 4 else "strict",
        "casei": level >= 4 and rng.random() < 0.5, "pct": level >= 4,
    }


PY = r'''
HAS_METHODS = @METHODS@
TYPES = @TYPES_PY@
HAS_WILD = @WILD@
LENIENT = @LENIENT@
CASEI = @CASEI@
HAS_PCT = @PCT@
METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]
LIT = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._~-"
LOW = "abcdefghijklmnopqrstuvwxyz"
DG = "0123456789"
HEX = "0123456789abcdefABCDEF"


def ident(s, maxlen):
    return 1 <= len(s) <= maxlen and s[0] in LOW and all(c in LOW + DG + "_" for c in s)


def parse_pattern(p):
    if p == "/":
        return []
    if not p.startswith("/") or p.endswith("/"):
        return None
    segs = []
    names = set()
    parts = p[1:].split("/")
    for i, s in enumerate(parts):
        if s == "":
            return None
        if s[0] == ":":
            body = s[1:]
            typ = None
            if "<" in body:
                if not body.endswith(">") or body.count("<") != 1:
                    return None
                body, typ = body[:-1].split("<")
                if typ not in TYPES:
                    return None
            if not ident(body, 16) or body in names:
                return None
            names.add(body)
            segs.append(("typed" if typ else "param", body, typ))
        elif s[0] == "*":
            if not HAS_WILD or i != len(parts) - 1 or not ident(s[1:], 16) or s[1:] in names:
                return None
            segs.append(("wild", s[1:], None))
        else:
            if not all(c in LIT for c in s):
                return None
            segs.append(("lit", s, None))
    return segs


def parse_table(text):
    routes = []
    for no, raw in enumerate(text.split("\n"), 1):
        w = raw.split("#", 1)[0].split()
        if not w:
            continue
        def err(m):
            return "error: table line %d: %s" % (no, m)
        if len(w) != (3 if HAS_METHODS else 2):
            return None, err("bad directive")
        method = "*"
        if HAS_METHODS:
            method = w[0]
            if method != "*" and method not in METHODS:
                return None, err("bad method")
        segs = parse_pattern(w[-2])
        if segs is None:
            return None, err("bad pattern")
        if not ident(w[-1], 24):
            return None, err("bad handler")
        routes.append((method, segs, w[-1]))
    return routes, None


def type_ok(typ, s):
    if typ == "int":
        return 1 <= len(s) <= 9 and all(c in DG for c in s)
    if typ == "slug":
        return s != "" and all(c in LOW + DG + "-" for c in s) and not s.startswith("-") and not s.endswith("-") and "--" not in s
    if typ == "alpha":
        return s != "" and all(c in LOW + LOW.upper() for c in s)
    return s != "" and all(c in HEX for c in s)


def match(segs, path):
    caps = []
    i = 0
    for kind, name, typ in segs:
        if kind == "wild":
            if i >= len(path):
                return None
            caps.append((name, "/".join(path[i:])))
            return caps
        if i >= len(path):
            return None
        s = path[i]
        if kind == "lit":
            if (s.lower() != name.lower()) if CASEI else (s != name):
                return None
        else:
            if s == "":
                return None
            if kind == "typed" and not type_ok(typ, s):
                return None
            caps.append((name, s))
        i += 1
    return caps if i == len(path) else None


def decode(seg):
    out = []
    i = 0
    while i < len(seg):
        c = seg[i]
        if c == "%":
            h = seg[i + 1:i + 3]
            if len(h) != 2 or any(x not in HEX for x in h):
                return None
            c = chr(int(h, 16))
            i += 3
        else:
            i += 1
        if not (" " <= c <= "~"):
            return None
        out.append(c)
    return "".join(out)


RANK = {"lit": 3, "typed": 2, "param": 1, "wild": 0}


def route(table, requests):
    routes, err = parse_table(table)
    if err:
        return err
    out = []
    for raw in requests.split("\n"):
        if raw.lstrip(" \t").startswith("#"):
            continue
        w = raw.split()
        if not w:
            continue
        if len(w) != (2 if HAS_METHODS else 1):
            out.append("400")
            continue
        method = "GET"
        if HAS_METHODS:
            method = w[0]
            if not method.isascii() or not method.isalpha() or not method.isupper():
                out.append("400")
                continue
        path = w[-1].split("?", 1)[0]
        if not path.startswith("/"):
            out.append("400")
            continue
        body = path[1:]
        if path == "/":
            segs = []
        else:
            if LENIENT and body.endswith("/"):
                body = body[:-1]
            segs = body.split("/")
            if "" in segs[:-1] or (len(segs) == 1 and segs[0] == "" and body == ""):
                out.append("400")
                continue
        bad = False
        if HAS_PCT:
            dec = []
            for s in segs:
                d = decode(s)
                if d is None:
                    bad = True
                    break
                dec.append(d)
            segs = dec
        if bad:
            out.append("400")
            continue
        cands = []
        pathmatch = []
        for idx, (m, rs, h) in enumerate(routes):
            caps = match(rs, segs)
            if caps is None:
                continue
            pathmatch.append(m)
            ok = m == "*" or m == method or (method == "HEAD" and m == "GET")
            if ok:
                spec = [RANK[k] for k, _, _ in rs]
                exact = 2 if m == method else 1 if m == "*" else 0
                cands.append((spec, exact, idx, h, caps))
        if cands:
            best = None
            for c in cands:
                if best is None:
                    best = c
                    continue
                a, b = c[0], best[0]
                n = max(len(a), len(b))
                a2 = a + [-1] * (n - len(a))
                b2 = b + [-1] * (n - len(b))
                if (a2, c[1]) > (b2, best[1]):
                    best = c
            out.append(" ".join(["200", best[3]] + ["%s=%s" % kv for kv in best[4]]))
        elif pathmatch:
            allowed = set()
            for m in pathmatch:
                if m == "*":
                    allowed.update(METHODS)
                elif m == "GET":
                    allowed.update(("GET", "HEAD"))
                else:
                    allowed.add(m)
            out.append("405 allow=" + ",".join(x for x in METHODS if x in allowed))
        else:
            out.append("404")
    return "\n".join(out)
'''

JS = r'''
'use strict';

const HAS_METHODS = @METHODS@;
const TYPES = @TYPES_JS@;
const HAS_WILD = @WILD@;
const LENIENT = @LENIENT@;
const CASEI = @CASEI@;
const HAS_PCT = @PCT@;
const METHODS = ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE'];
const LOW = 'abcdefghijklmnopqrstuvwxyz';
const UP = LOW.toUpperCase();
const DG = '0123456789';
const HEX = '0123456789abcdefABCDEF';
const LIT = LOW + UP + DG + '._~-';
const RANK = { lit: 3, typed: 2, param: 1, wild: 0 };

const words = (s) => s.split(/[ \t\r\n\v\f]+/).filter((x) => x.length > 0);
const all = (s, set) => [...s].every((c) => set.includes(c));
const ident = (s, max) => s.length >= 1 && s.length <= max && LOW.includes(s[0]) && all(s, LOW + DG + '_');

function parsePattern(p) {
  if (p === '/') return [];
  if (!p.startsWith('/') || p.endsWith('/')) return null;
  const segs = [];
  const names = new Set();
  const parts = p.slice(1).split('/');
  for (let i = 0; i < parts.length; i++) {
    const s = parts[i];
    if (s === '') return null;
    if (s[0] === ':') {
      let body = s.slice(1);
      let typ = null;
      if (body.includes('<')) {
        if (!body.endsWith('>') || body.split('<').length !== 2) return null;
        [body, typ] = body.slice(0, -1).split('<');
        if (!TYPES.includes(typ)) return null;
      }
      if (!ident(body, 16) || names.has(body)) return null;
      names.add(body);
      segs.push([typ ? 'typed' : 'param', body, typ]);
    } else if (s[0] === '*') {
      if (!HAS_WILD || i !== parts.length - 1 || !ident(s.slice(1), 16) || names.has(s.slice(1))) return null;
      segs.push(['wild', s.slice(1), null]);
    } else {
      if (!all(s, LIT)) return null;
      segs.push(['lit', s, null]);
    }
  }
  return segs;
}

function typeOk(typ, s) {
  if (typ === 'int') return s.length >= 1 && s.length <= 9 && all(s, DG);
  if (typ === 'slug') return s !== '' && all(s, LOW + DG + '-') && !s.startsWith('-') && !s.endsWith('-') && !s.includes('--');
  if (typ === 'alpha') return s !== '' && all(s, LOW + UP);
  return s !== '' && all(s, HEX);
}

function match(segs, path) {
  const caps = [];
  let i = 0;
  for (const [kind, name, typ] of segs) {
    if (kind === 'wild') {
      if (i >= path.length) return null;
      caps.push([name, path.slice(i).join('/')]);
      return caps;
    }
    if (i >= path.length) return null;
    const s = path[i];
    if (kind === 'lit') {
      if (CASEI ? s.toLowerCase() !== name.toLowerCase() : s !== name) return null;
    } else {
      if (s === '') return null;
      if (kind === 'typed' && !typeOk(typ, s)) return null;
      caps.push([name, s]);
    }
    i++;
  }
  return i === path.length ? caps : null;
}

function decode(seg) {
  let out = '';
  let i = 0;
  while (i < seg.length) {
    let c = seg[i];
    if (c === '%') {
      const h = seg.slice(i + 1, i + 3);
      if (h.length !== 2 || ![...h].every((x) => HEX.includes(x))) return null;
      c = String.fromCharCode(parseInt(h, 16));
      i += 3;
    } else i++;
    if (c < ' ' || c > '~') return null;
    out += c;
  }
  return out;
}

function parseTable(text) {
  const routes = [];
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const w = words(lines[i].split('#')[0]);
    if (w.length === 0) continue;
    const err = (m) => `error: table line ${i + 1}: ${m}`;
    if (w.length !== (HAS_METHODS ? 3 : 2)) return [null, err('bad directive')];
    let method = '*';
    if (HAS_METHODS) {
      method = w[0];
      if (method !== '*' && !METHODS.includes(method)) return [null, err('bad method')];
    }
    const segs = parsePattern(w[w.length - 2]);
    if (segs === null) return [null, err('bad pattern')];
    if (!ident(w[w.length - 1], 24)) return [null, err('bad handler')];
    routes.push([method, segs, w[w.length - 1]]);
  }
  return [routes, null];
}

function route(table, requests) {
  const [routes, err] = parseTable(table);
  if (err) return err;
  const out = [];
  for (const raw of requests.split('\n')) {
    if (raw.replace(/^[ \t]+/, '').startsWith('#')) continue;
    const w = words(raw);
    if (w.length === 0) continue;
    if (w.length !== (HAS_METHODS ? 2 : 1)) { out.push('400'); continue; }
    let method = 'GET';
    if (HAS_METHODS) {
      method = w[0];
      if (!/^[A-Z]+$/.test(method)) { out.push('400'); continue; }
    }
    const path = w[w.length - 1].split('?')[0];
    if (!path.startsWith('/')) { out.push('400'); continue; }
    let body = path.slice(1);
    let segs;
    if (path === '/') segs = [];
    else {
      if (LENIENT && body.endsWith('/')) body = body.slice(0, -1);
      segs = body.split('/');
      const inner = segs.slice(0, -1);
      if (inner.includes('') || (segs.length === 1 && segs[0] === '' && body === '')) { out.push('400'); continue; }
    }
    if (HAS_PCT) {
      const dec = [];
      let bad = false;
      for (const s of segs) {
        const d = decode(s);
        if (d === null) { bad = true; break; }
        dec.push(d);
      }
      if (bad) { out.push('400'); continue; }
      segs = dec;
    }
    const cands = [];
    const pathmatch = [];
    routes.forEach(([m, rs, h], idx) => {
      const caps = match(rs, segs);
      if (caps === null) return;
      pathmatch.push(m);
      if (m === '*' || m === method || (method === 'HEAD' && m === 'GET')) {
        cands.push([rs.map(([k]) => RANK[k]), m === method ? 2 : m === '*' ? 1 : 0, idx, h, caps]);
      }
    });
    if (cands.length > 0) {
      let best = null;
      for (const c of cands) {
        if (best === null) { best = c; continue; }
        const n = Math.max(c[0].length, best[0].length);
        let cmp = 0;
        for (let k = 0; k < n && cmp === 0; k++) {
          const a = k < c[0].length ? c[0][k] : -1;
          const b = k < best[0].length ? best[0][k] : -1;
          cmp = a - b;
        }
        if (cmp === 0) cmp = c[1] - best[1];
        if (cmp > 0) best = c;
      }
      out.push(['200', best[3], ...best[4].map(([k, v]) => `${k}=${v}`)].join(' '));
    } else if (pathmatch.length > 0) {
      const allowed = new Set();
      for (const m of pathmatch) {
        if (m === '*') METHODS.forEach((x) => allowed.add(x));
        else if (m === 'GET') { allowed.add('GET'); allowed.add('HEAD'); } else allowed.add(m);
      }
      out.push('405 allow=' + METHODS.filter((x) => allowed.has(x)).join(','));
    } else out.push('404');
  }
  return out.join('\n');
}

module.exports = { route };
'''

GO = r'''
package router

import (
	"fmt"
	"strconv"
	"strings"
)

const (
	hasMethods = @METHODS@
	hasWild    = @WILD@
	lenient    = @LENIENT@
	caseI      = @CASEI@
	hasPct     = @PCT@
	low        = "abcdefghijklmnopqrstuvwxyz"
	up         = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
	dg         = "0123456789"
	hexc       = "0123456789abcdefABCDEF"
)

var types = @TYPES_GO@
var methods = []string{"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}

type seg struct{ kind, name, typ string }

type rt struct {
	method  string
	segs    []seg
	handler string
}

func allIn(s, set string) bool {
	for i := 0; i < len(s); i++ {
		if !strings.ContainsRune(set, rune(s[i])) {
			return false
		}
	}
	return true
}

func ident(s string, max int) bool {
	return len(s) >= 1 && len(s) <= max && strings.ContainsRune(low, rune(s[0])) && allIn(s, low+dg+"_")
}

func inList(l []string, s string) bool {
	for _, x := range l {
		if x == s {
			return true
		}
	}
	return false
}

func parsePattern(p string) ([]seg, bool) {
	if p == "/" {
		return []seg{}, true
	}
	if !strings.HasPrefix(p, "/") || strings.HasSuffix(p, "/") {
		return nil, false
	}
	var segs []seg
	names := map[string]bool{}
	parts := strings.Split(p[1:], "/")
	for i, s := range parts {
		if s == "" {
			return nil, false
		}
		switch s[0] {
		case ':':
			body := s[1:]
			typ := ""
			if strings.Contains(body, "<") {
				if !strings.HasSuffix(body, ">") || strings.Count(body, "<") != 1 {
					return nil, false
				}
				sp := strings.Split(body[:len(body)-1], "<")
				body, typ = sp[0], sp[1]
				if !inList(types, typ) {
					return nil, false
				}
			}
			if !ident(body, 16) || names[body] {
				return nil, false
			}
			names[body] = true
			kind := "param"
			if typ != "" {
				kind = "typed"
			}
			segs = append(segs, seg{kind, body, typ})
		case '*':
			if !hasWild || i != len(parts)-1 || !ident(s[1:], 16) || names[s[1:]] {
				return nil, false
			}
			segs = append(segs, seg{"wild", s[1:], ""})
		default:
			if !allIn(s, low+up+dg+"._~-") {
				return nil, false
			}
			segs = append(segs, seg{"lit", s, ""})
		}
	}
	return segs, true
}

func typeOk(typ, s string) bool {
	switch typ {
	case "int":
		return len(s) >= 1 && len(s) <= 9 && allIn(s, dg)
	case "slug":
		return s != "" && allIn(s, low+dg+"-") && !strings.HasPrefix(s, "-") && !strings.HasSuffix(s, "-") && !strings.Contains(s, "--")
	case "alpha":
		return s != "" && allIn(s, low+up)
	}
	return s != "" && allIn(s, hexc)
}

type cap2 struct{ k, v string }

func match(segs []seg, path []string) ([]cap2, bool) {
	var caps []cap2
	i := 0
	for _, sg := range segs {
		if sg.kind == "wild" {
			if i >= len(path) {
				return nil, false
			}
			caps = append(caps, cap2{sg.name, strings.Join(path[i:], "/")})
			return caps, true
		}
		if i >= len(path) {
			return nil, false
		}
		s := path[i]
		if sg.kind == "lit" {
			if caseI {
				if strings.ToLower(s) != strings.ToLower(sg.name) {
					return nil, false
				}
			} else if s != sg.name {
				return nil, false
			}
		} else {
			if s == "" {
				return nil, false
			}
			if sg.kind == "typed" && !typeOk(sg.typ, s) {
				return nil, false
			}
			caps = append(caps, cap2{sg.name, s})
		}
		i++
	}
	return caps, i == len(path)
}

func decode(s string) (string, bool) {
	var out []byte
	for i := 0; i < len(s); {
		c := s[i]
		if c == '%' {
			if i+3 > len(s) {
				return "", false
			}
			h := s[i+1 : i+3]
			if !allIn(h, hexc) {
				return "", false
			}
			v, _ := strconv.ParseUint(h, 16, 8)
			c = byte(v)
			i += 3
		} else {
			i++
		}
		if c < ' ' || c > '~' {
			return "", false
		}
		out = append(out, c)
	}
	return string(out), true
}

func rank(k string) int {
	switch k {
	case "lit":
		return 3
	case "typed":
		return 2
	case "param":
		return 1
	}
	return 0
}

func parseTable(text string) ([]rt, string) {
	var routes []rt
	for i, raw := range strings.Split(text, "\n") {
		if h := strings.IndexByte(raw, '#'); h >= 0 {
			raw = raw[:h]
		}
		w := strings.Fields(raw)
		if len(w) == 0 {
			continue
		}
		err := func(m string) string { return fmt.Sprintf("error: table line %d: %s", i+1, m) }
		want := 2
		if hasMethods {
			want = 3
		}
		if len(w) != want {
			return nil, err("bad directive")
		}
		method := "*"
		if hasMethods {
			method = w[0]
			if method != "*" && !inList(methods, method) {
				return nil, err("bad method")
			}
		}
		segs, ok := parsePattern(w[len(w)-2])
		if !ok {
			return nil, err("bad pattern")
		}
		if !ident(w[len(w)-1], 24) {
			return nil, err("bad handler")
		}
		routes = append(routes, rt{method, segs, w[len(w)-1]})
	}
	return routes, ""
}

type cand struct {
	spec    []int
	exact   int
	handler string
	caps    []cap2
}

// Route answers one line per request.
func Route(table, requests string) string {
	routes, errText := parseTable(table)
	if errText != "" {
		return errText
	}
	var out []string
	for _, raw := range strings.Split(requests, "\n") {
		if strings.HasPrefix(strings.TrimLeft(raw, " \t"), "#") {
			continue
		}
		w := strings.Fields(raw)
		if len(w) == 0 {
			continue
		}
		want := 1
		if hasMethods {
			want = 2
		}
		if len(w) != want {
			out = append(out, "400")
			continue
		}
		method := "GET"
		if hasMethods {
			method = w[0]
			ok := len(method) > 0
			for i := 0; i < len(method); i++ {
				if method[i] < 'A' || method[i] > 'Z' {
					ok = false
				}
			}
			if !ok {
				out = append(out, "400")
				continue
			}
		}
		path := w[len(w)-1]
		if q := strings.IndexByte(path, '?'); q >= 0 {
			path = path[:q]
		}
		if !strings.HasPrefix(path, "/") {
			out = append(out, "400")
			continue
		}
		body := path[1:]
		var segs []string
		if path == "/" {
			segs = []string{}
		} else {
			if lenient && strings.HasSuffix(body, "/") {
				body = body[:len(body)-1]
			}
			segs = strings.Split(body, "/")
			bad := len(segs) == 1 && segs[0] == "" && body == ""
			for _, s := range segs[:len(segs)-1] {
				if s == "" {
					bad = true
				}
			}
			if bad {
				out = append(out, "400")
				continue
			}
		}
		if hasPct {
			dec := make([]string, 0, len(segs))
			bad := false
			for _, s := range segs {
				d, ok := decode(s)
				if !ok {
					bad = true
					break
				}
				dec = append(dec, d)
			}
			if bad {
				out = append(out, "400")
				continue
			}
			segs = dec
		}
		var best *cand
		var pathmatch []string
		for _, r := range routes {
			caps, ok := match(r.segs, segs)
			if !ok {
				continue
			}
			pathmatch = append(pathmatch, r.method)
			if r.method == "*" || r.method == method || (method == "HEAD" && r.method == "GET") {
				spec := make([]int, len(r.segs))
				for i, s := range r.segs {
					spec[i] = rank(s.kind)
				}
				exact := 0
				if r.method == method {
					exact = 2
				} else if r.method == "*" {
					exact = 1
				}
				c := &cand{spec, exact, r.handler, caps}
				if best == nil {
					best = c
					continue
				}
				n := len(c.spec)
				if len(best.spec) > n {
					n = len(best.spec)
				}
				cmp := 0
				for k := 0; k < n && cmp == 0; k++ {
					a, b := -1, -1
					if k < len(c.spec) {
						a = c.spec[k]
					}
					if k < len(best.spec) {
						b = best.spec[k]
					}
					cmp = a - b
				}
				if cmp == 0 {
					cmp = c.exact - best.exact
				}
				if cmp > 0 {
					best = c
				}
			}
		}
		switch {
		case best != nil:
			parts := []string{"200", best.handler}
			for _, c := range best.caps {
				parts = append(parts, c.k+"="+c.v)
			}
			out = append(out, strings.Join(parts, " "))
		case len(pathmatch) > 0:
			allowed := map[string]bool{}
			for _, m := range pathmatch {
				switch m {
				case "*":
					for _, x := range methods {
						allowed[x] = true
					}
				case "GET":
					allowed["GET"] = true
					allowed["HEAD"] = true
				default:
					allowed[m] = true
				}
			}
			var l []string
			for _, x := range methods {
				if allowed[x] {
					l = append(l, x)
				}
			}
			out = append(out, "405 allow="+strings.Join(l, ","))
		default:
			out = append(out, "404")
		}
	}
	return strings.Join(out, "\n")
}
'''

JV = r'''
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class Router {
    static final boolean HAS_METHODS = @METHODS@;
    static final List<String> TYPES = Arrays.asList(@TYPES_JAVA@);
    static final boolean HAS_WILD = @WILD@;
    static final boolean LENIENT = @LENIENT@;
    static final boolean CASEI = @CASEI@;
    static final boolean HAS_PCT = @PCT@;
    static final List<String> METHODS = Arrays.asList("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE");
    static final String LOW = "abcdefghijklmnopqrstuvwxyz";
    static final String UP = LOW.toUpperCase();
    static final String DG = "0123456789";
    static final String HEX = "0123456789abcdefABCDEF";

    static class Seg {
        String kind, name, typ;
        Seg(String k, String n, String t) { kind = k; name = n; typ = t; }
    }

    static class Rt {
        String method, handler;
        List<Seg> segs;
    }

    static boolean all(String s, String set) {
        for (char c : s.toCharArray()) if (set.indexOf(c) < 0) return false;
        return true;
    }

    static boolean ident(String s, int max) {
        return s.length() >= 1 && s.length() <= max && LOW.indexOf(s.charAt(0)) >= 0 && all(s, LOW + DG + "_");
    }

    static List<String> words(String s) {
        List<String> out = new ArrayList<>();
        for (String w : s.split("[ \t\r\n\u000B\f]+")) if (!w.isEmpty()) out.add(w);
        return out;
    }

    static List<Seg> parsePattern(String p) {
        List<Seg> segs = new ArrayList<>();
        if (p.equals("/")) return segs;
        if (!p.startsWith("/") || p.endsWith("/")) return null;
        Set<String> names = new LinkedHashSet<>();
        String[] parts = p.substring(1).split("/", -1);
        for (int i = 0; i < parts.length; i++) {
            String s = parts[i];
            if (s.isEmpty()) return null;
            if (s.charAt(0) == ':') {
                String body = s.substring(1);
                String typ = null;
                if (body.contains("<")) {
                    int n = body.length() - body.replace("<", "").length();
                    if (!body.endsWith(">") || n != 1) return null;
                    String inner = body.substring(0, body.length() - 1);
                    int lt = inner.indexOf('<');
                    body = inner.substring(0, lt);
                    typ = inner.substring(lt + 1);
                    if (!TYPES.contains(typ)) return null;
                }
                if (!ident(body, 16) || names.contains(body)) return null;
                names.add(body);
                segs.add(new Seg(typ != null ? "typed" : "param", body, typ));
            } else if (s.charAt(0) == '*') {
                String nm = s.substring(1);
                if (!HAS_WILD || i != parts.length - 1 || !ident(nm, 16) || names.contains(nm)) return null;
                segs.add(new Seg("wild", nm, null));
            } else {
                if (!all(s, LOW + UP + DG + "._~-")) return null;
                segs.add(new Seg("lit", s, null));
            }
        }
        return segs;
    }

    static boolean typeOk(String typ, String s) {
        switch (typ) {
            case "int": return s.length() >= 1 && s.length() <= 9 && all(s, DG);
            case "slug": return !s.isEmpty() && all(s, LOW + DG + "-") && !s.startsWith("-") && !s.endsWith("-") && !s.contains("--");
            case "alpha": return !s.isEmpty() && all(s, LOW + UP);
            default: return !s.isEmpty() && all(s, HEX);
        }
    }

    static List<String[]> match(List<Seg> segs, List<String> path) {
        List<String[]> caps = new ArrayList<>();
        int i = 0;
        for (Seg sg : segs) {
            if (sg.kind.equals("wild")) {
                if (i >= path.size()) return null;
                caps.add(new String[] { sg.name, String.join("/", path.subList(i, path.size())) });
                return caps;
            }
            if (i >= path.size()) return null;
            String s = path.get(i);
            if (sg.kind.equals("lit")) {
                if (CASEI ? !s.toLowerCase(java.util.Locale.ROOT).equals(sg.name.toLowerCase(java.util.Locale.ROOT)) : !s.equals(sg.name)) return null;
            } else {
                if (s.isEmpty()) return null;
                if (sg.kind.equals("typed") && !typeOk(sg.typ, s)) return null;
                caps.add(new String[] { sg.name, s });
            }
            i++;
        }
        return i == path.size() ? caps : null;
    }

    static String decode(String seg) {
        StringBuilder out = new StringBuilder();
        int i = 0;
        while (i < seg.length()) {
            char c = seg.charAt(i);
            if (c == '%') {
                if (i + 3 > seg.length()) return null;
                String h = seg.substring(i + 1, i + 3);
                if (!all(h, HEX)) return null;
                c = (char) Integer.parseInt(h, 16);
                i += 3;
            } else i++;
            if (c < ' ' || c > '~') return null;
            out.append(c);
        }
        return out.toString();
    }

    static int rank(String k) {
        switch (k) {
            case "lit": return 3;
            case "typed": return 2;
            case "param": return 1;
            default: return 0;
        }
    }

    static List<Rt> routes;

    static String parseTable(String text) {
        routes = new ArrayList<>();
        String[] lines = text.split("\n", -1);
        for (int i = 0; i < lines.length; i++) {
            String raw = lines[i];
            int h = raw.indexOf('#');
            if (h >= 0) raw = raw.substring(0, h);
            List<String> w = words(raw);
            if (w.isEmpty()) continue;
            String pre = "error: table line " + (i + 1) + ": ";
            if (w.size() != (HAS_METHODS ? 3 : 2)) return pre + "bad directive";
            String method = "*";
            if (HAS_METHODS) {
                method = w.get(0);
                if (!method.equals("*") && !METHODS.contains(method)) return pre + "bad method";
            }
            List<Seg> segs = parsePattern(w.get(w.size() - 2));
            if (segs == null) return pre + "bad pattern";
            if (!ident(w.get(w.size() - 1), 24)) return pre + "bad handler";
            Rt r = new Rt();
            r.method = method;
            r.segs = segs;
            r.handler = w.get(w.size() - 1);
            routes.add(r);
        }
        return null;
    }

    public static String route(String table, String requests) {
        String err = parseTable(table);
        if (err != null) return err;
        List<String> out = new ArrayList<>();
        for (String raw : requests.split("\n", -1)) {
            if (raw.replaceAll("^[ \t]+", "").startsWith("#")) continue;
            List<String> w = words(raw);
            if (w.isEmpty()) continue;
            if (w.size() != (HAS_METHODS ? 2 : 1)) { out.add("400"); continue; }
            String method = "GET";
            if (HAS_METHODS) {
                method = w.get(0);
                boolean ok = true;
                for (char c : method.toCharArray()) if (c < 'A' || c > 'Z') ok = false;
                if (!ok) { out.add("400"); continue; }
            }
            String path = w.get(w.size() - 1);
            int q = path.indexOf('?');
            if (q >= 0) path = path.substring(0, q);
            if (!path.startsWith("/")) { out.add("400"); continue; }
            String body = path.substring(1);
            List<String> segs;
            if (path.equals("/")) segs = new ArrayList<>();
            else {
                if (LENIENT && body.endsWith("/")) body = body.substring(0, body.length() - 1);
                segs = new ArrayList<>(Arrays.asList(body.split("/", -1)));
                boolean bad = segs.size() == 1 && segs.get(0).isEmpty() && body.isEmpty();
                for (int k = 0; k < segs.size() - 1; k++) if (segs.get(k).isEmpty()) bad = true;
                if (bad) { out.add("400"); continue; }
            }
            if (HAS_PCT) {
                List<String> dec = new ArrayList<>();
                boolean bad = false;
                for (String s : segs) {
                    String d = decode(s);
                    if (d == null) { bad = true; break; }
                    dec.add(d);
                }
                if (bad) { out.add("400"); continue; }
                segs = dec;
            }
            int[] bestSpec = null;
            int bestExact = 0;
            String bestHandler = null;
            List<String[]> bestCaps = null;
            List<String> pathmatch = new ArrayList<>();
            for (Rt r : routes) {
                List<String[]> caps = match(r.segs, segs);
                if (caps == null) continue;
                pathmatch.add(r.method);
                if (r.method.equals("*") || r.method.equals(method) || (method.equals("HEAD") && r.method.equals("GET"))) {
                    int[] spec = new int[r.segs.size()];
                    for (int k = 0; k < spec.length; k++) spec[k] = rank(r.segs.get(k).kind);
                    int exact = r.method.equals(method) ? 2 : r.method.equals("*") ? 1 : 0;
                    boolean take = bestSpec == null;
                    if (!take) {
                        int n = Math.max(spec.length, bestSpec.length);
                        int cmp = 0;
                        for (int k = 0; k < n && cmp == 0; k++) {
                            int a = k < spec.length ? spec[k] : -1;
                            int b = k < bestSpec.length ? bestSpec[k] : -1;
                            cmp = a - b;
                        }
                        if (cmp == 0) cmp = exact - bestExact;
                        take = cmp > 0;
                    }
                    if (take) { bestSpec = spec; bestExact = exact; bestHandler = r.handler; bestCaps = caps; }
                }
            }
            if (bestSpec != null) {
                StringBuilder sb = new StringBuilder("200 " + bestHandler);
                for (String[] c : bestCaps) sb.append(" ").append(c[0]).append("=").append(c[1]);
                out.add(sb.toString());
            } else if (!pathmatch.isEmpty()) {
                Set<String> allowed = new LinkedHashSet<>();
                for (String m : pathmatch) {
                    if (m.equals("*")) allowed.addAll(METHODS);
                    else if (m.equals("GET")) { allowed.add("GET"); allowed.add("HEAD"); } else allowed.add(m);
                }
                List<String> l = new ArrayList<>();
                for (String m : METHODS) if (allowed.contains(m)) l.add(m);
                out.add("405 allow=" + String.join(",", l));
            } else out.add("404");
        }
        return String.join("\n", out);
    }
}
'''

RB = r'''
module Router
  HAS_METHODS = @METHODS@
  TYPES = @TYPES_RB@
  HAS_WILD = @WILD@
  LENIENT = @LENIENT@
  CASEI = @CASEI@
  HAS_PCT = @PCT@
  METHODS = %w[GET HEAD POST PUT PATCH DELETE]
  LOW = 'abcdefghijklmnopqrstuvwxyz'
  UP = LOW.upcase
  DG = '0123456789'
  HEX = '0123456789abcdefABCDEF'
  RANK = { 'lit' => 3, 'typed' => 2, 'param' => 1, 'wild' => 0 }

  def self.all?(s, set)
    s.each_char.all? { |c| set.include?(c) }
  end

  def self.ident?(s, max)
    s.length >= 1 && s.length <= max && LOW.include?(s[0]) && all?(s, LOW + DG + '_')
  end

  def self.parse_pattern(p)
    return [] if p == '/'
    return nil if !p.start_with?('/') || p.end_with?('/')
    segs = []
    names = []
    parts = p[1..].split('/', -1)
    parts.each_with_index do |s, i|
      return nil if s.empty?
      if s[0] == ':'
        body = s[1..]
        typ = nil
        if body.include?('<')
          return nil if !body.end_with?('>') || body.count('<') != 1
          inner = body[0...-1]
          body, typ = inner.split('<', 2)
          return nil unless TYPES.include?(typ)
        end
        return nil if !ident?(body, 16) || names.include?(body)
        names << body
        segs << [typ ? 'typed' : 'param', body, typ]
      elsif s[0] == '*'
        nm = s[1..]
        return nil if !HAS_WILD || i != parts.length - 1 || !ident?(nm, 16) || names.include?(nm)
        segs << ['wild', nm, nil]
      else
        return nil unless all?(s, LOW + UP + DG + '._~-')
        segs << ['lit', s, nil]
      end
    end
    segs
  end

  def self.type_ok?(typ, s)
    case typ
    when 'int' then s.length >= 1 && s.length <= 9 && all?(s, DG)
    when 'slug' then !s.empty? && all?(s, LOW + DG + '-') && !s.start_with?('-') && !s.end_with?('-') && !s.include?('--')
    when 'alpha' then !s.empty? && all?(s, LOW + UP)
    else !s.empty? && all?(s, HEX)
    end
  end

  def self.match(segs, path)
    caps = []
    i = 0
    segs.each do |kind, name, typ|
      if kind == 'wild'
        return nil if i >= path.length
        caps << [name, path[i..].join('/')]
        return caps
      end
      return nil if i >= path.length
      s = path[i]
      if kind == 'lit'
        return nil if (CASEI ? s.downcase != name.downcase : s != name)
      else
        return nil if s.empty?
        return nil if kind == 'typed' && !type_ok?(typ, s)
        caps << [name, s]
      end
      i += 1
    end
    i == path.length ? caps : nil
  end

  def self.decode(seg)
    out = +''
    i = 0
    while i < seg.length
      c = seg[i]
      if c == '%'
        h = seg[i + 1, 2]
        return nil if h.nil? || h.length != 2 || !all?(h, HEX)
        c = h.to_i(16).chr
        i += 3
      else
        i += 1
      end
      return nil if c < ' ' || c > '~'
      out << c
    end
    out
  end

  def self.parse_table(text)
    routes = []
    text.split("\n", -1).each_with_index do |raw, i|
      w = raw.split('#', 2)[0].to_s.split
      next if w.empty?
      pre = "error: table line #{i + 1}: "
      return [nil, pre + 'bad directive'] if w.length != (HAS_METHODS ? 3 : 2)
      method = '*'
      if HAS_METHODS
        method = w[0]
        return [nil, pre + 'bad method'] if method != '*' && !METHODS.include?(method)
      end
      segs = parse_pattern(w[-2])
      return [nil, pre + 'bad pattern'] if segs.nil?
      return [nil, pre + 'bad handler'] unless ident?(w[-1], 24)
      routes << [method, segs, w[-1]]
    end
    [routes, nil]
  end

  def self.route(table, requests)
    routes, err = parse_table(table)
    return err if err
    out = []
    requests.split("\n", -1).each do |raw|
      next if raw.sub(/\A[ \t]+/, '').start_with?('#')
      w = raw.split
      next if w.empty?
      if w.length != (HAS_METHODS ? 2 : 1)
        out << '400'
        next
      end
      method = 'GET'
      if HAS_METHODS
        method = w[0]
        unless method.match?(/\A[A-Z]+\z/)
          out << '400'
          next
        end
      end
      path = w[-1].split('?', 2)[0].to_s
      unless path.start_with?('/')
        out << '400'
        next
      end
      body = path[1..]
      if path == '/'
        segs = []
      else
        body = body[0...-1] if LENIENT && body.end_with?('/')
        segs = body.empty? ? [''] : body.split('/', -1)
        bad = segs.length == 1 && segs[0].empty? && body.empty?
        segs[0...-1].each { |s| bad = true if s.empty? }
        if bad
          out << '400'
          next
        end
      end
      if HAS_PCT
        dec = []
        bad = false
        segs.each do |s|
          d = decode(s)
          if d.nil?
            bad = true
            break
          end
          dec << d
        end
        if bad
          out << '400'
          next
        end
        segs = dec
      end
      best = nil
      pathmatch = []
      routes.each do |m, rs, h|
        caps = match(rs, segs)
        next if caps.nil?
        pathmatch << m
        next unless m == '*' || m == method || (method == 'HEAD' && m == 'GET')
        spec = rs.map { |k, _, _| RANK[k] }
        exact = m == method ? 2 : m == '*' ? 1 : 0
        if best.nil?
          best = [spec, exact, h, caps]
          next
        end
        n = [spec.length, best[0].length].max
        cmp = 0
        k = 0
        while k < n && cmp == 0
          a = k < spec.length ? spec[k] : -1
          b = k < best[0].length ? best[0][k] : -1
          cmp = a - b
          k += 1
        end
        cmp = exact - best[1] if cmp == 0
        best = [spec, exact, h, caps] if cmp > 0
      end
      if best
        out << (['200', best[2]] + best[3].map { |k, v| "#{k}=#{v}" }).join(' ')
      elsif !pathmatch.empty?
        allowed = []
        pathmatch.each do |m|
          if m == '*' then allowed.concat(METHODS)
          elsif m == 'GET' then allowed.push('GET', 'HEAD')
          else allowed << m
          end
        end
        out << ('405 allow=' + METHODS.select { |x| allowed.include?(x) }.join(','))
      else
        out << '404'
      end
    end
    out.join("\n")
  end
end
'''

SOURCES = {"python": PY, "javascript": JS, "go": GO, "java": JV, "ruby": RB}


def _b(lang, v):
    if lang == "python":
        return "True" if v else "False"
    return "true" if v else "false"


def sol(lang, p):
    t = p["types"]
    return K.subst(
        SOURCES[lang], METHODS=_b(lang, p["methods"]), WILD=_b(lang, p["wild"]), LENIENT=_b(lang, p["slash"] == "lenient"), CASEI=_b(lang, p["casei"]), PCT=_b(lang, p["pct"]),
        TYPES_PY="[" + ", ".join(f'"{x}"' for x in t) + "]", TYPES_JS="[" + ", ".join(f"'{x}'" for x in t) + "]", TYPES_GO="[]string{" + ", ".join(f'"{x}"' for x in t) + "}",
        TYPES_JAVA=", ".join(f'"{x}"' for x in t), TYPES_RB="[" + ", ".join(f"'{x}'" for x in t) + "]",
    ).lstrip("\n")


# ---------------------------------------------------------------------------------------------------------------

def readme(p, api, lang, examples):
    L = [f"# Router for {p['site']}", ""]
    L.append(f"This library decides which handler serves a request for {p['site']}. `route(table, requests)` reads a *route table* and a list of requests and answers one line per request. There is no network: everything is text.")
    L.append("")
    L.append("## Route table")
    L.append("")
    if p["methods"]:
        L.append("One route per line: `METHOD PATTERN HANDLER` (exactly three words separated by blanks). `METHOD` is one of `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`, or `*` (any method).")
    else:
        L.append("One route per line: `PATTERN HANDLER` (exactly two words separated by blanks). Routes answer every request; requests carry no method.")
    L.append("Everything from `#` to the end of a line is a comment; lines without words are ignored. Lines are numbered from 1 (comments and blank lines count).")
    L.append("")
    L.append("A **handler** is 1 to 24 characters: a lower-case ASCII letter, then lower-case letters, digits or `_`.")
    L.append("")
    L.append("A **pattern** starts with `/`. The pattern `/` alone is the root. Otherwise it is segments separated by single `/`, with no empty segment and **no trailing slash**. A segment is:")
    L.append("")
    L.append("* a *literal*: one or more of `A-Z a-z 0-9 . _ ~ -`;")
    pn = "a *parameter* `:name`: matches any one non-empty path segment and captures it"
    if p["types"]:
        pn += f"; `:name<type>` matches only segments of that type, with the types " + ", ".join(f"`{t}`" for t in p["types"])
    L.append("* " + pn + ". `name` is 1 to 16 characters, a lower-case letter then lower-case letters, digits or `_`, and a name may occur only once in a pattern;")
    if p["types"]:
        td = {"int": "`int`: 1 to 9 ASCII digits", "slug": "`slug`: lower-case letters and digits in groups separated by single `-` (no leading, trailing or double `-`)", "alpha": "`alpha`: ASCII letters, either case", "hex": "`hex`: ASCII hex digits, either case"}
        L.append("* the types: " + "; ".join(td[t] for t in p["types"]) + ";")
    if p["wild"]:
        L.append("* a *wildcard* `*name` (same naming rules, and the name must differ from the other names), allowed only as the **last** segment: it matches **one or more** remaining segments and captures them joined with `/`.")
    L.append("")
    L.append("A line with the wrong number of words is `bad directive`; otherwise" + (" an unknown method is `bad method`, " if p["methods"] else " ") + "an invalid pattern `bad pattern`, an invalid handler `bad handler` (checked in that order). "
             "The first bad line makes the whole result `error: table line N: REASON`.")
    L.append("")
    L.append("## Requests")
    L.append("")
    L.append(("Each non-blank line is `METHOD PATH` (exactly two words): the method is one or more upper-case ASCII letters (any such word is allowed, not only the six above)." if p["methods"] else
              "Each non-blank line is just a `PATH` (exactly one word).") +
             " Lines starting with `#` (after optional blanks) and blank lines produce no output. A request line that does not have the right shape gets the answer `400`.")
    L.append("")
    L.append("The **path** is the word after the method with everything from the first `?` removed (the query string is ignored). It must start with `/`, otherwise `400`. The root path is `/`. For any other path the text after the first `/` is split at every `/` into segments. "
             "An empty segment *inside* the path (`//`) is `400`. A path with a trailing `/` ends with one empty segment: "
             + ("with the **lenient** slash policy that one trailing slash is simply dropped before matching (so `/a/` is `/a`, but `/a//` is `400`, and `//` is `400`); " if p["slash"] == "lenient" else
                "with the **strict** slash policy it stays, and since no pattern segment can match an empty segment `/a/` is just a path that matches nothing (`404` unless the 400 rules above apply); ") +
             ("" if True else ""))
    L.append("")
    if p["pct"]:
        L.append("**Percent-encoding.** After splitting, every segment is decoded: `%XX` (two hex digits, either case) stands for the character with that code. A `%` not followed by two hex digits, or a decoded character outside the printable ASCII range `0x20`-`0x7E` "
                 "(so `%00`, `%1F`, `%7F` and every byte from `%80` up are rejected), makes the request `400`. `+` is an ordinary character. A decoded `/` (`%2F`) does **not** separate segments. Matching, typing and the captured values all use the decoded text.")
        L.append("")
    L.append("## Matching")
    L.append("")
    L.append("A route's pattern **matches** a path if the path has exactly as many segments as the pattern (a wildcard takes all the rest, at least one), and every pattern segment accepts its path segment: literals must be equal" +
             (" ignoring ASCII case (a request for `/Members` matches the literal `members`; captured values keep their case)" if p["casei"] else " (case-sensitively)") + ", parameters need a non-empty segment" + (" of the right type" if p["types"] else "") + ".")
    L.append("")
    if p["methods"]:
        L.append("A matching route is *eligible* when its method is `*`, equals the request method, or is `GET` while the request method is `HEAD`. If several routes are eligible, the best one wins: compare their patterns segment by segment from the left, ranking "
                 "literal > " + ("typed parameter > " if p["types"] else "") + "parameter" + (" > wildcard" if p["wild"] else "") + " (a position that exists in only one pattern ranks below any kind); the first difference decides. "
                 "If the patterns are equally specific, an exact method match beats `*`, which beats `GET`-for-`HEAD`; if still tied, the route written **first** in the table wins.")
    else:
        L.append("If several routes match, the best one wins: compare their patterns segment by segment from the left, ranking literal > " + ("typed parameter > " if p["types"] else "") + "parameter" + (" > wildcard" if p["wild"] else "") +
                 " (a position that exists in only one pattern ranks below any kind); the first difference decides; if still tied the route written **first** wins.")
    L.append("")
    L.append("## Answers")
    L.append("")
    L.append("* `200 HANDLER name=value ...`: the winning route's handler followed by its captures in the order of the pattern (`name=value`, separated by single blanks; no captures, nothing more).")
    if p["methods"]:
        L.append("* `405 allow=M1,M2,...`: no route is eligible but at least one route's pattern matches the path. The methods are collected from those routes (a `*` route contributes all six methods, a `GET` route contributes `GET` and `HEAD`), "
                 "without duplicates, in the order `GET,HEAD,POST,PUT,PATCH,DELETE`.")
    L.append("* `404`: no route's pattern matches the path.")
    L.append("* `400`: malformed request (see above).")
    L.append("")
    L.append("The result is the answers joined by `\\n` (no trailing newline); with no requests it is the empty text.")
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    for (t, r), out in examples:
        L.append("Table:")
        L.append("")
        L.append(K.fence(t))
        L.append("Requests:")
        L.append("")
        L.append(K.fence(r))
        L.append("Answers:")
        L.append("")
        L.append(K.fence(out) if out else "(empty)\n")
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


def make_cases(rng, p, ns):
    cases = []
    methods = p["methods"]
    types = p["types"]
    HAND = ["home", "list_items", "show_item", "edit_item", "create_item", "files", "health", "docs", "about", "user", "search", "report", "feed", "admin_panel"]
    SEG = ["users", "items", "files", "docs", "api", "v1", "v2", "tags", "orders", "status"]

    def add(t, r):
        cases.append((t, r))

    def mk_pattern():
        n = rng.randrange(1, 4)
        segs = []
        used = set()
        for k in range(n):
            r = rng.random()
            if r < 0.45:
                segs.append(rng.choice(SEG))
            else:
                nm = rng.choice(["id", "name", "slug", "n", "key", "rest"])
                if nm in used:
                    nm += str(k)
                used.add(nm)
                if types and rng.random() < 0.6:
                    segs.append(f":{nm}<{rng.choice(types)}>")
                else:
                    segs.append(f":{nm}")
        if p["wild"] and rng.random() < 0.2:
            segs.append("*tail" if "tail" not in used else "*more")
        return "/" + "/".join(segs)

    def mk_table(n=None):
        n = n or rng.randrange(3, 8)
        lines = []
        for _ in range(n):
            h = rng.choice(HAND)
            pat = mk_pattern() if rng.random() < 0.9 else "/"
            if methods:
                lines.append(f"{rng.choice(['GET', 'GET', 'GET', 'POST', 'PUT', 'DELETE', 'PATCH', '*', 'HEAD'])} {pat} {h}")
            else:
                lines.append(f"{pat} {h}")
        return "\n".join(lines) + "\n"

    def paths_for(table):
        out = []
        for ln in table.split("\n"):
            w = ln.split()
            if len(w) < 2:
                continue
            pat = w[-2]
            segs = [s for s in pat.split("/") if s]
            filled = []
            for s in segs:
                if s.startswith(":"):
                    typ = s[s.find("<") + 1:-1] if "<" in s else None
                    v = {"int": str(rng.randrange(1, 9999)), "slug": rng.choice(["abc", "a-b", "x1-y2"]), "alpha": rng.choice(["Abc", "xyz"]), "hex": rng.choice(["ff", "A0b1"])}.get(typ, rng.choice(["42", "abc", "x_y", "Q"]))
                    filled.append(v)
                elif s.startswith("*"):
                    filled.append("/".join(rng.choice(["a", "b2", "c.d"]) for _ in range(rng.randrange(1, 4))))
                else:
                    filled.append(s)
            out.append("/" + "/".join(filled))
        return out

    def reqs(table, n=None):
        ps = paths_for(table) or ["/"]
        lines = []
        for _ in range(n or rng.randrange(4, 10)):
            pth = rng.choice(ps)
            r = rng.random()
            if r < 0.15:
                pth = pth + "/"
            elif r < 0.25:
                pth = pth + "?x=1&y=%20"
            elif r < 0.3:
                pth = "/zzz" + pth
            elif r < 0.35:
                pth = pth + "/extra"
            if methods:
                lines.append(f"{rng.choice(['GET', 'GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'PATCH', 'OPTIONS'])} {pth}")
            else:
                lines.append(pth)
        return "\n".join(lines) + "\n"

    t = mk_table(4)
    add(t, reqs(t, 5))
    t = mk_table(5)
    add(t, reqs(t, 6))
    t = mk_table(4)
    add(t, reqs(t, 5))
    nex = len(cases)
    for _ in range(14):
        t = mk_table()
        add(t, reqs(t))
    for _ in range(3):
        t = mk_table(rng.randrange(8, 12))
        add(t, reqs(t, rng.randrange(10, 16)))
    M = (lambda m, pat, h: f"{m} {pat} {h}") if methods else (lambda m, pat, h: f"{pat} {h}")  # noqa: E731
    G = (lambda path: f"GET {path}") if methods else (lambda path: path)  # noqa: E731
    # specificity
    tab = "\n".join([M("GET", "/a/:x", "param"), M("GET", "/a/b", "lit"), M("GET", "/:y/b", "late"), M("GET", "/:y/:z", "both")]) + "\n"
    add(tab, "\n".join(G(x) for x in ["/a/b", "/a/c", "/z/b", "/z/c", "/a", "/a/b/c", "/", ""]))
    tab2 = "\n".join([M("GET", "/:y/:z", "first"), M("GET", "/:p/:q", "second")]) + "\n"
    add(tab2, G("/a/b"))
    tab3 = "\n".join([M("GET", "/", "root"), M("GET", "/about", "about"), M("GET", "/about/team", "team")]) + "\n"
    add(tab3, "\n".join(G(x) for x in ["/", "/about", "/about/team", "/about/team/x", "/team", "", "/About", "/ABOUT/TEAM"]))
    add("", G("/"))
    add("# empty\n", G("/a"))
    add(tab3, "")
    add(tab3, "\n\n   \n# only a comment\n")
    add(tab3, "\n".join(["# c", G("/"), "  # indented comment", G("/about")]))
    # request shape
    shape = [G("a"), G(""), G("//"), G("/a//b"), G("//a"), G("/a/"), G("/about/"), G("/about//"), G("/about/team/"), G("/?x"), G("/about?x=1"), G("/about?"), G("/about?/team"), G("/?"), G("/abou?t"), G("?"), G("/a b")]
    add(tab3, "\n".join(shape))
    add(tab3, "\n".join(["/", "/ extra", "/about /team", "  /about  ", "\t/about\t"] if not methods else ["GET", "GET /", "GET / extra", "get /", "GeT /", "GET1 /", "GET-X /", "/", "/ GET", "  GET   /about  ", "\tGET\t/about\t", "OPTIONS /about", "X /about", "G /about"]))
    if methods:
        tab4 = "\n".join(["GET /item/:id<int>" if "int" in types else "GET /item/:id", "POST /item", "PUT /item/:id", "DELETE /item/:id", "* /any", "GET /any/get", "HEAD /headonly", "GET /g", "POST /g"]) + "\n"
        reqs4 = ["GET /item/5", "HEAD /item/5", "POST /item/5", "PUT /item/5", "DELETE /item/5", "PATCH /item/5", "OPTIONS /item/5", "GET /item", "POST /item", "HEAD /item", "DELETE /item",
                 "GET /any", "POST /any", "DELETE /any", "HEAD /any", "FOO /any", "GET /any/get", "POST /any/get", "HEAD /any/get", "PUT /any/get", "GET /headonly", "HEAD /headonly", "POST /headonly",
                 "HEAD /g", "POST /g", "PUT /g", "GET /g", "GET /nothing", "GET /item/5/x", "FOO /nothing", "HEAD /nothing"]
        add(tab4, "\n".join(reqs4))
        tab5 = "GET /x h1\nHEAD /x h2\n* /x h3\nPOST /x h4\n"
        add(tab5, "\n".join(f"{m} /x" for m in ("GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS", "PATCH")))
        tab6 = "* /y h1\nGET /y h2\n"
        add(tab6, "\n".join(f"{m} /y" for m in ("GET", "HEAD", "POST")))
        tab7 = "GET /:a/b h1\nGET /c/:d h2\nPOST /c/b h3\n"
        add(tab7, "\n".join(f"{m} /c/b" for m in ("GET", "POST", "HEAD", "PUT")))
        tab8 = "POST /z h1\nPUT /z h2\nDELETE /z h3\nPATCH /z h4\nHEAD /z h5\n"
        add(tab8, "GET /z\nHEAD /z\nOPTIONS /z\nPOST /z")
        tab9 = "GET /w/:a h1\nGET /w/lit h2\n"
        add(tab9, "HEAD /w/lit\nHEAD /w/other\nPOST /w/lit\nPOST /w/other\nPOST /w")
        # table errors with methods
        for bad in ("GET /a", "GET /a h h", "get /a h", "FETCH /a h", "GET a h", "GET /a/ h", "GET /a//b h", "GET //a h", "GET /a/ b h", "GET /a Handler", "GET /a 1h", "GET /a h-x", "GET /a h" + "x" * 24, "GET /a " + "x" * 24,
                    "GET /a " + "x" * 25, "OPTIONS /a h", "* /a h", "HEAD /a h", "GET /:id/:id h", "GET /:ID h", "GET /: h", "GET /:1a h", "GET /:a-b h", "GET /a b h", "GET /a%20b h", "GET /a+b h", "GET /a* h", "GET /*x h", "GET /a/b/ h",
                    "GET /" + ":" + "x" * 16 + " h", "GET /" + ":" + "x" * 17 + " h", "GET /:a<int h", "GET /:a<int>x h", "GET /:a<> h", "GET /:a<nosuch> h", "GET /:a<int><int> h", "GET /:a<int h", "GET /a<int> h", "GET /:<int> h", "GET /$ h"):
            add(bad + "\n", G("/a"))
        add("GET /a h1\nGET /b\n", G("/a"))
        add("GET /a h1\n\n# c\nbogus line here now\n", G("/a"))
        add("POST /a h1 # trailing comment\nGET /a h2   # another\n", "POST /a\nGET /a")
    else:
        for bad in ("/a", "/a h h", "a h", "/a/ h", "/a//b h", "//a h", "/a Handler", "/a 1h", "/a h-x", "/a " + "x" * 25, "/:id/:id h", "/:ID h", "/: h", "/a b h", "/a* h", "/*x h", "/$ h", "GET /a h", "/:a<int> h"):
            add(bad + "\n", G("/a"))
        add("/a h1\n/b\n", G("/a"))
        add("/a h1\n\n# c\nbogus line here\n", G("/a"))
        add("/a h1 # trailing\n/b h2   # another\n", "/a\n/b")
    # parameters
    ptab = M("GET", "/u/:id", "u") + "\n" + M("GET", "/u/:id/p/:pid", "up") + "\n" + M("GET", "/r/:a/:b/:c", "r") + "\n" + M("GET", "/", "root") + "\n"
    add(ptab, "\n".join(G(x) for x in ["/u/1", "/u/abc", "/u/A%", "/u/a.b", "/u/a~b", "/u/-", "/u/_", "/u/1/p/2", "/u/1/p", "/u/1/p/", "/u/1/q/2", "/r/1/2/3", "/r/1/2", "/r/1/2/3/4", "/u/", "/u", "/u//1"]))
    add(ptab, "\n".join(G(x) for x in ["/u/" + "x" * 50, "/u/1?id=2", "/u/1#frag", "/u/1;a=b", "/u/a:b", "/u/a@b", "/u/a,b", "/u/a=b", "/u/a&b", "/u/!", "/u/(x)", "/u/[x]", "/u/{x}", "/u/a*b", "/u/+", "/u/'"]))
    # types
    if types:
        ttab = "\n".join(M("GET", f"/{t}/:v<{t}>", f"h_{t}") for t in types) + "\n" + M("GET", "/any/:v", "h_any") + "\n"
        samples = ["0", "7", "007", "123456789", "1234567890", "-1", "+1", "1.5", "abc", "ABC", "aBc", "a1", "a-b", "-a", "a-", "a--b", "a-b-c", "ff", "FF", "fF0", "g", "0x1f", "", "a b", "é", "1e3", "٣"]
        samples = [s for s in samples if all(ord(c) < 128 for c in s)]
        for t in types:
            add(ttab, "\n".join(G(f"/{t}/{s}") for s in samples if s))
        add(ttab + M("GET", "/int/:w", "h_loose") + "\n", "\n".join(G(f"/int/{s}") for s in ("5", "x")))
        # typed vs untyped at the same position
        ctab = "\n".join([M("GET", f"/c/:a<{types[0]}>", "typed"), M("GET", "/c/:b", "plain"), M("GET", "/c/special", "lit")]) + "\n"
        add(ctab, "\n".join(G(f"/c/{s}") for s in ("special", "12", "abc", "ff", "a-b", "Special")))
        ctab2 = "\n".join([M("GET", "/c/:b", "plain"), M("GET", f"/c/:a<{types[0]}>", "typed")]) + "\n"
        add(ctab2, "\n".join(G(f"/c/{s}") for s in ("12", "abc", "ff")))
        ctab3 = "\n".join([M("GET", f"/d/:a<{types[0]}>/x", "t1"), M("GET", "/d/:b/:c", "t2"), M("GET", "/d/:a/x", "t3")]) + "\n"
        add(ctab3, "\n".join(G(f"/d/{s}/x") for s in ("12", "abc", "ff", "a-b")))
        for bad in (f"GET /:a<{types[0]}> h", f"GET /:a<{types[0]}>/:a h", f"GET /:a<{types[0]}>/:b<{types[-1]}> h"):
            if methods:
                add(bad + "\n", G("/x"))
        if "int" not in types:
            add(M("GET", "/:a<int>", "h") + "\n", G("/5"))
        if "hex" not in types:
            add(M("GET", "/:a<hex>", "h") + "\n", G("/ff"))
    else:
        add(M("GET", "/:a<int>", "h") + "\n", G("/5"))
        add(M("GET", "/a:b", "h") + "\n", G("/a:b"))
    # wildcards
    if p["wild"]:
        wtab = "\n".join([M("GET", "/files/*path", "files"), M("GET", "/files/readme", "readme"), M("GET", "/files/:name/meta", "meta"), M("GET", "/*all", "catch")]) + "\n"
        add(wtab, "\n".join(G(x) for x in ["/files", "/files/", "/files/a", "/files/a/b/c", "/files/readme", "/files/readme/x", "/files/x/meta", "/files/x/y/meta", "/other", "/other/deep/er", "/", "/files//a"]))
        add(wtab, "\n".join(G(x) for x in ["/files/a%2Fb", "/files/a%20b/c", "/files/%41/%62"] if True))
        add(M("GET", "/*rest", "all") + "\n", "\n".join(G(x) for x in ["/", "/a", "/a/b", "/a/", "/a//b", "/%2F"]))
        for bad in ("GET /a/*x/b h", "GET /*x/*y h", "GET /*x/b h", "GET /* h", "GET /a/* h", "GET /*X h", "GET /:x/*x h", "GET /*x/ h", "GET /a*b h", "GET /*x*y h", "GET /*1x h"):
            add((bad if methods else bad.replace("GET ", "")) + "\n", G("/a"))
    else:
        add(M("GET", "/*rest", "h") + "\n", G("/a"))
        add(M("GET", "/a/*rest", "h") + "\n", G("/a/b"))
    # slash policy
    stab = "\n".join([M("GET", "/s", "s"), M("GET", "/s/:x", "sx"), M("POST", "/s", "post_s")]) + "\n"
    add(stab, "\n".join(G(x) for x in ["/s", "/s/", "/s//", "/s/a", "/s/a/", "/s/a//", "/", "//", "///", "/s?x=1", "/s/?x=1", "/s//?x=1", "/s/a/b/"]))
    if methods:
        add(stab, "POST /s/\nPOST /s\nHEAD /s/\nDELETE /s/\nGET /s/")
    # case
    ctab4 = "\n".join([M("GET", "/Members/:id", "u"), M("GET", "/X-Y", "xy")]) + "\n"
    add(ctab4, "\n".join(G(x) for x in ["/Members/Bob", "/members/Bob", "/MEMBERS/bob", "/mEmBeRs/BOB", "/x-y", "/X-Y", "/x-Y", "/X_Y"]))
    # percent decoding
    if p["pct"]:
        dtab = "\n".join([M("GET", "/d/:v", "dv"), M("GET", "/d/a b/x", "space"), M("GET", "/e/lit-eral", "lit"), M("GET", "/m/:a/:b", "m")]) + "\n"
        pcs = ["/d/a%20b", "/d/a%20b/x", "/d/%61", "/d/%41", "/d/%7e", "/d/%7E", "/d/%2f", "/d/%2F", "/d/a%2Fb", "/d/%25", "/d/%2525", "/d/%", "/d/%2", "/d/%G1", "/d/%1G", "/d/%zz", "/d/a%", "/d/a%2", "/d/%00", "/d/%1f", "/d/%7f",
               "/d/%80", "/d/%C3%A9", "/d/%ff", "/d/%20", "/d/%20%20", "/d/+", "/d/a+b", "/d/a%2bb", "/e/lit%2Deral", "/e/LIT%2DERAL", "/e/lit-eral%", "/m/%41/%42", "/m/%41%2F%42/c", "/m/a/%", "/%64/x", "/d%2Fx", "/d/%7E%7e", "/d/%3f", "/d/a%3Fb?z=1",
               "/d/%2", "/d/%2%32", "/d/%3a", "/d/%3A%3a", "/d/%e", "/d/%E9"]
        add(dtab, "\n".join(G(x) for x in pcs))
        if types:
            ttab2 = "\n".join(M("GET", f"/t/:v<{t}>", f"h_{t}") for t in types) + "\n"
            add(ttab2, "\n".join(G(f"/t/{s}") for s in ["%31%32", "%61bc", "%41bc", "%66%66", "%2d", "a%2db", "12%", "%2B1", "%31"]))
        add(M("GET", "/a%20b", "h") + "\n", G("/a%20b"))
    else:
        add(M("GET", "/d/:v", "dv") + "\n", "\n".join(G(x) for x in ["/d/a%20b", "/d/%41", "/d/%", "/d/%zz", "/d/%C3%A9"]))
    out, seen = [], set()
    for c in cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex


def prompt(rng, p, api, lang):
    where = api.short(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    feats = ["literal and `:param` segments"] + (["typed parameters"] if p["types"] else []) + (["methods with 405 answers"] if p["methods"] else []) + (["wildcards", f"the {p['slash']} trailing-slash policy", "percent-decoding"] if p["wild"] else [])
    ft = ", ".join(feats)
    opts = [
        f"Please write the request router for {p['site']} in {ln}: `{fn}(table, requests)` ({where}). The route patterns, the specificity rules and the exact answers are in README.md. Features: {ft}. {K.closer(rng)}",
        f"Implement `{fn}` ({ln}, {where}) per README.md: a route table in, one answer line per request out. It supports {ft}. The hidden checks look hard at which route wins and at the 400/404/405 distinctions.",
        f"router task. {ln}. `{fn}` in {where}. spec = README.md ({ft}). note: no trailing slash in patterns, specificity compared left to right, first route wins ties. {K.closer(rng)}",
        f"We need the routing core for {p['site']} (no HTTP server, just text in and out). Language {ln}; function `{fn}`; file {where}. README.md describes everything: {ft}.",
    ]
    return rng.choice(opts).strip()


@family("greenfield-router", category="greenfield", lang="mixed", kind="greenfield", n=12,
        summary="in-process router: pattern syntax, typed params, left-to-right specificity, method fallbacks and 405 allow lists, wildcards, slash and case policies, percent-decoding")
def gen(rng, n):
    levels = [2, 2, 3, 3, 3, 4, 4, 4, 3, 4, 2, 4]
    diffs = [2, 2, 3, 3, 3, 4, 4, 5, 3, 4, 2, 4]
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level, i)
        api = K.Api(mod="router", fn="route", args=["table", "requests"], arg_docs=["the route table text", "the requests, one per line"],
                    ret_doc="one answer line per request (or an `error: table line ...` text)", doc="in-process request router")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["route"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=diffs[i % len(diffs)], slug=f"{i + 1:02d}-{lang}-l{level}-{p['slash']}{'-ci' if p['casei'] else ''}", oracle=(None if lang == "python" else ns["route"]),
            tags=["parser", "routing", "http"], notes={"level": level, "types": p["types"], "slash": p["slash"], "casei": p["casei"]},
        )
