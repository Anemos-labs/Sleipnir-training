"""Template engine with an invented syntax: value tags, defaults, filters, conditionals, loops, partials (strict error order)."""
from __future__ import annotations

import re

from fx import family

from generators.greenfield import _kit as K

PY = r'''
OPEN = @OPEN@
CLOSE = @CLOSE@
S_IF = @S_IF@
S_NOT = @S_NOT@
S_EACH = @S_EACH@
S_ELSE = @S_ELSE@
S_END = @S_END@
S_COMMENT = @S_COMMENT@
HAS_COND = @COND@
HAS_LOOP = @LOOP@
HAS_PART = @PART@
HAS_PARENT = @PARENT@
FALSY = @FALSY@
FILTERS = @FILTERS@
MAXDEPTH = 4
LOW = "abcdefghijklmnopqrstuvwxyz"
DIG = "0123456789"


class Err(Exception):
    pass


def is_name(s):
    return s != "" and s[0] in LOW + "_" and all(c in LOW + DIG + "_" for c in s)


def parse_data(text):
    d = {}
    for line in text.split("\n"):
        if line == "":
            continue
        k, eq, v = line.partition("=")
        if not eq or not is_name(k) or k in d:
            raise Err("error: data")
        out = []
        i = 0
        while i < len(v):
            ch = v[i]
            if ch == "\\":
                if i + 1 >= len(v) or v[i + 1] not in "n\\":
                    raise Err("error: data")
                out.append("\n" if v[i + 1] == "n" else "\\")
                i += 2
            else:
                out.append(ch)
                i += 1
        d[k] = "".join(out)
    return d


def parse_filter(tok):
    if tok == "" or not all(c in LOW + DIG for c in tok):
        raise Err("error: syntax")
    name = tok.rstrip(DIG)
    arg = tok[len(name):]
    if name == "":
        raise Err("error: syntax")
    for alias, kind, takes in FILTERS:
        if alias == name:
            if takes:
                if arg == "" or arg[0] == "0" or len(arg) > 2:
                    raise Err("error: filter " + tok)
                return (kind, int(arg))
            if arg != "":
                raise Err("error: filter " + tok)
            return (kind, 0)
    raise Err("error: filter " + tok)


def parse_expr(c):
    body, eq, default = c.partition("=")
    segs = body.split("|")
    ref = segs[0]
    ok = is_name(ref) or (HAS_LOOP and ref in (".", "@")) or (HAS_PARENT and ref == "..")
    if not ok:
        raise Err("error: syntax")
    if len(segs) > 1 and not FILTERS:
        raise Err("error: syntax")
    filters = [parse_filter(t) for t in segs[1:]]
    return (ref, filters, default if eq else None)


def compile_t(text):
    root = []
    cur = root
    stack = []
    pos = 0
    n = len(text)
    while True:
        i = text.find(OPEN, pos)
        if i < 0:
            if pos < n:
                cur.append(("text", text[pos:]))
            break
        if i > pos:
            cur.append(("text", text[pos:i]))
        j = text.find(CLOSE, i + len(OPEN))
        if j < 0:
            raise Err("error: unclosed")
        c = text[i + len(OPEN):j]
        pos = j + len(CLOSE)
        if c == "":
            cur.append(("text", OPEN))
        elif c[0] == S_COMMENT:
            pass
        elif HAS_COND and c == S_ELSE:
            if not stack or stack[-1][3]:
                raise Err("error: unexpected")
            stack[-1][3] = True
            cur = stack[-1][2]
        elif HAS_COND and c == S_END:
            if not stack:
                raise Err("error: unexpected")
            cur = stack.pop()[0]
        elif HAS_COND and c[0] in (S_IF, S_NOT) or HAS_LOOP and c[0] == S_EACH:
            expr = parse_expr(c[1:])
            then, other = [], []
            if c[0] == S_EACH:
                cur.append(("each", expr, then, other))
            else:
                cur.append(("if", expr, c[0] == S_NOT, then, other))
            stack.append([cur, then, other, False])
            cur = then
        elif HAS_PART and c[0] == ">":
            if not is_name(c[1:]):
                raise Err("error: syntax")
            cur.append(("part", c[1:]))
        else:
            cur.append(("var", parse_expr(c)))
    if stack:
        raise Err("error: unclosed")
    return root


def apply_filter(f, v):
    kind, k = f
    if kind == "upper":
        return "".join(ch.upper() if "a" <= ch <= "z" else ch for ch in v)
    if kind == "lower":
        return "".join(ch.lower() if "A" <= ch <= "Z" else ch for ch in v)
    if kind == "trim":
        return v.strip(" ")
    if kind == "len":
        return str(len(v))
    if kind == "rev":
        return v[::-1]
    if kind == "pad":
        return v + " " * (k - len(v))
    if kind == "cut":
        return v[:k]
    if kind == "dash":
        return v.replace(" ", "-")
    if kind == "title":
        out = []
        prev = " "
        for ch in v:
            out.append(ch.upper() if prev == " " and "a" <= ch <= "z" else ch)
            prev = ch
        return "".join(out)
    if kind == "esc":
        return "".join({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}.get(ch, ch) for ch in v)
    raise AssertionError(kind)


def evaluate(expr, loops, data):
    ref, filters, default = expr
    val = None
    if ref == ".":
        val = loops[-1][0] if loops else None
    elif ref == "@":
        val = str(loops[-1][1]) if loops else None
    elif ref == "..":
        val = loops[-2][0] if len(loops) >= 2 else None
    else:
        val = data.get(ref)
    if (val is None or val == "") and default is not None:
        val = default
    if val is None:
        raise Err("error: undefined " + ref)
    for f in filters:
        val = apply_filter(f, val)
    return val


def run(nodes, loops, depth, data, out):
    for nd in nodes:
        k = nd[0]
        if k == "text":
            out.append(nd[1])
        elif k == "var":
            out.append(evaluate(nd[1], loops, data))
        elif k == "if":
            v = evaluate(nd[1], loops, data)
            truth = v not in FALSY
            if nd[2]:
                truth = not truth
            run(nd[3] if truth else nd[4], loops, depth, data, out)
        elif k == "each":
            v = evaluate(nd[1], loops, data)
            items = v.split(",") if v != "" else []
            if not items:
                run(nd[3], loops, depth, data, out)
            for ix, it in enumerate(items):
                run(nd[2], loops + [(it, ix + 1)], depth, data, out)
        elif k == "part":
            if nd[1] not in data:
                raise Err("error: undefined " + nd[1])
            if depth + 1 > MAXDEPTH:
                raise Err("error: depth")
            run(compile_t(data[nd[1]]), loops, depth + 1, data, out)


def render(template, data):
    try:
        d = parse_data(data)
        tree = compile_t(template)
        out = []
        run(tree, [], 0, d, out)
        return "".join(out)
    except Err as e:
        return str(e)
'''

JS = r'''
'use strict';
const OPEN = @OPEN@;
const CLOSE = @CLOSE@;
const S_IF = @S_IF@;
const S_NOT = @S_NOT@;
const S_EACH = @S_EACH@;
const S_ELSE = @S_ELSE@;
const S_END = @S_END@;
const S_COMMENT = @S_COMMENT@;
const HAS_COND = @COND@;
const HAS_LOOP = @LOOP@;
const HAS_PART = @PART@;
const HAS_PARENT = @PARENT@;
const FALSY = @FALSY@;
const FILTERS = @FILTERS@;
const MAXDEPTH = 4;
const LOW = 'abcdefghijklmnopqrstuvwxyz';
const DIG = '0123456789';

class Err extends Error {}

function isName(s) {
  if (s === '' || !(LOW + '_').includes(s[0])) return false;
  for (const c of s) if (!(LOW + DIG + '_').includes(c)) return false;
  return true;
}

function parseData(text) {
  const d = new Map();
  for (const line of text.split('\n')) {
    if (line === '') continue;
    const ei = line.indexOf('=');
    if (ei < 0) throw new Err('error: data');
    const k = line.slice(0, ei);
    const v = line.slice(ei + 1);
    if (!isName(k) || d.has(k)) throw new Err('error: data');
    let out = '';
    for (let i = 0; i < v.length; i++) {
      const ch = v[i];
      if (ch === '\\') {
        if (i + 1 >= v.length || (v[i + 1] !== 'n' && v[i + 1] !== '\\')) throw new Err('error: data');
        out += v[i + 1] === 'n' ? '\n' : '\\';
        i++;
      } else out += ch;
    }
    d.set(k, out);
  }
  return d;
}

function parseFilter(tok) {
  if (tok === '') throw new Err('error: syntax');
  for (const c of tok) if (!(LOW + DIG).includes(c)) throw new Err('error: syntax');
  let e = tok.length;
  while (e > 0 && DIG.includes(tok[e - 1])) e--;
  const name = tok.slice(0, e);
  const arg = tok.slice(e);
  if (name === '') throw new Err('error: syntax');
  for (const [alias, kind, takes] of FILTERS) {
    if (alias === name) {
      if (takes) {
        if (arg === '' || arg[0] === '0' || arg.length > 2) throw new Err('error: filter ' + tok);
        return [kind, parseInt(arg, 10)];
      }
      if (arg !== '') throw new Err('error: filter ' + tok);
      return [kind, 0];
    }
  }
  throw new Err('error: filter ' + tok);
}

function parseExpr(c) {
  const ei = c.indexOf('=');
  const body = ei < 0 ? c : c.slice(0, ei);
  const dflt = ei < 0 ? null : c.slice(ei + 1);
  const segs = body.split('|');
  const ref = segs[0];
  const ok = isName(ref) || (HAS_LOOP && (ref === '.' || ref === '@')) || (HAS_PARENT && ref === '..');
  if (!ok) throw new Err('error: syntax');
  if (segs.length > 1 && FILTERS.length === 0) throw new Err('error: syntax');
  return { ref, filters: segs.slice(1).map(parseFilter), dflt };
}

function compile(text) {
  const root = [];
  let cur = root;
  const stack = [];
  let pos = 0;
  for (;;) {
    const i = text.indexOf(OPEN, pos);
    if (i < 0) {
      if (pos < text.length) cur.push({ t: 'text', s: text.slice(pos) });
      break;
    }
    if (i > pos) cur.push({ t: 'text', s: text.slice(pos, i) });
    const j = text.indexOf(CLOSE, i + OPEN.length);
    if (j < 0) throw new Err('error: unclosed');
    const c = text.slice(i + OPEN.length, j);
    pos = j + CLOSE.length;
    if (c === '') cur.push({ t: 'text', s: OPEN });
    else if (c[0] === S_COMMENT) continue;
    else if (HAS_COND && c === S_ELSE) {
      if (stack.length === 0 || stack[stack.length - 1].inElse) throw new Err('error: unexpected');
      stack[stack.length - 1].inElse = true;
      cur = stack[stack.length - 1].other;
    } else if (HAS_COND && c === S_END) {
      if (stack.length === 0) throw new Err('error: unexpected');
      cur = stack.pop().parent;
    } else if ((HAS_COND && (c[0] === S_IF || c[0] === S_NOT)) || (HAS_LOOP && c[0] === S_EACH)) {
      const expr = parseExpr(c.slice(1));
      const then = [];
      const other = [];
      cur.push({ t: c[0] === S_EACH ? 'each' : 'if', expr, neg: c[0] === S_NOT, then, other });
      stack.push({ parent: cur, then, other, inElse: false });
      cur = then;
    } else if (HAS_PART && c[0] === '>') {
      if (!isName(c.slice(1))) throw new Err('error: syntax');
      cur.push({ t: 'part', name: c.slice(1) });
    } else cur.push({ t: 'var', expr: parseExpr(c) });
  }
  if (stack.length > 0) throw new Err('error: unclosed');
  return root;
}

function applyFilter([kind, k], v) {
  switch (kind) {
    case 'upper': return v.replace(/[a-z]/g, (ch) => ch.toUpperCase());
    case 'lower': return v.replace(/[A-Z]/g, (ch) => ch.toLowerCase());
    case 'trim': {
      let a = 0;
      let b = v.length;
      while (a < b && v[a] === ' ') a++;
      while (b > a && v[b - 1] === ' ') b--;
      return v.slice(a, b);
    }
    case 'len': return String(v.length);
    case 'rev': return v.split('').reverse().join('');
    case 'pad': return v.length < k ? v + ' '.repeat(k - v.length) : v;
    case 'cut': return v.slice(0, k);
    case 'dash': return v.split(' ').join('-');
    case 'title': {
      let out = '';
      let prev = ' ';
      for (const ch of v) {
        out += prev === ' ' && ch >= 'a' && ch <= 'z' ? ch.toUpperCase() : ch;
        prev = ch;
      }
      return out;
    }
    case 'esc': {
      const m = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
      return v.replace(/[&<>"]/g, (ch) => m[ch]);
    }
    default: throw new Error('bad filter ' + kind);
  }
}

function evaluate(expr, loops, data) {
  let val = null;
  const n = loops.length;
  if (expr.ref === '.') val = n >= 1 ? loops[n - 1][0] : null;
  else if (expr.ref === '@') val = n >= 1 ? String(loops[n - 1][1]) : null;
  else if (expr.ref === '..') val = n >= 2 ? loops[n - 2][0] : null;
  else val = data.has(expr.ref) ? data.get(expr.ref) : null;
  if ((val === null || val === '') && expr.dflt !== null) val = expr.dflt;
  if (val === null) throw new Err('error: undefined ' + expr.ref);
  for (const f of expr.filters) val = applyFilter(f, val);
  return val;
}

function run(nodes, loops, depth, data, out) {
  for (const nd of nodes) {
    if (nd.t === 'text') out.push(nd.s);
    else if (nd.t === 'var') out.push(evaluate(nd.expr, loops, data));
    else if (nd.t === 'if') {
      const v = evaluate(nd.expr, loops, data);
      let truth = !FALSY.includes(v);
      if (nd.neg) truth = !truth;
      run(truth ? nd.then : nd.other, loops, depth, data, out);
    } else if (nd.t === 'each') {
      const v = evaluate(nd.expr, loops, data);
      const items = v === '' ? [] : v.split(',');
      if (items.length === 0) run(nd.other, loops, depth, data, out);
      items.forEach((it, ix) => run(nd.then, loops.concat([[it, ix + 1]]), depth, data, out));
    } else if (nd.t === 'part') {
      if (!data.has(nd.name)) throw new Err('error: undefined ' + nd.name);
      if (depth + 1 > MAXDEPTH) throw new Err('error: depth');
      run(compile(data.get(nd.name)), loops, depth + 1, data, out);
    }
  }
}

function render(template, data) {
  try {
    const d = parseData(data);
    const tree = compile(template);
    const out = [];
    run(tree, [], 0, d, out);
    return out.join('');
  } catch (e) {
    if (e instanceof Err) return e.message;
    throw e;
  }
}

module.exports = { render };
'''

JV = r'''
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class Template {
    static final String OPEN = @OPEN@;
    static final String CLOSE = @CLOSE@;
    static final char S_IF = @S_IF@.charAt(0);
    static final char S_NOT = @S_NOT@.charAt(0);
    static final char S_EACH = @S_EACH@.charAt(0);
    static final String S_ELSE = @S_ELSE@;
    static final String S_END = @S_END@;
    static final char S_COMMENT = @S_COMMENT@.charAt(0);
    static final boolean HAS_COND = @COND@;
    static final boolean HAS_LOOP = @LOOP@;
    static final boolean HAS_PART = @PART@;
    static final boolean HAS_PARENT = @PARENT@;
    static final String[] FALSY = @FALSY@;
    static final Object[][] FILTERS = @FILTERS@;
    static final int MAXDEPTH = 4;
    static final String LOW = "abcdefghijklmnopqrstuvwxyz";
    static final String DIG = "0123456789";

    static class Err extends RuntimeException {
        Err(String m) { super(m); }
    }

    static class Filter {
        String kind;
        int k;
        Filter(String kind, int k) { this.kind = kind; this.k = k; }
    }

    static class Expr {
        String ref;
        List<Filter> filters = new ArrayList<>();
        String dflt;
    }

    static class Node {
        String t; // text var if each part
        String s; // text, part name
        Expr expr;
        boolean neg;
        List<Node> then = new ArrayList<>();
        List<Node> other = new ArrayList<>();
    }

    static class Open {
        List<Node> parent, then, other;
        boolean inElse;
    }

    static boolean isName(String s) {
        if (s.isEmpty() || (LOW + "_").indexOf(s.charAt(0)) < 0) return false;
        for (int i = 0; i < s.length(); i++) if ((LOW + DIG + "_").indexOf(s.charAt(i)) < 0) return false;
        return true;
    }

    static Map<String, String> parseData(String text) {
        Map<String, String> d = new HashMap<>();
        for (String line : text.split("\n", -1)) {
            if (line.isEmpty()) continue;
            int ei = line.indexOf('=');
            if (ei < 0) throw new Err("error: data");
            String k = line.substring(0, ei);
            String v = line.substring(ei + 1);
            if (!isName(k) || d.containsKey(k)) throw new Err("error: data");
            StringBuilder out = new StringBuilder();
            for (int i = 0; i < v.length(); i++) {
                char ch = v.charAt(i);
                if (ch == '\\') {
                    if (i + 1 >= v.length() || (v.charAt(i + 1) != 'n' && v.charAt(i + 1) != '\\')) throw new Err("error: data");
                    out.append(v.charAt(i + 1) == 'n' ? '\n' : '\\');
                    i++;
                } else out.append(ch);
            }
            d.put(k, out.toString());
        }
        return d;
    }

    static Filter parseFilter(String tok) {
        if (tok.isEmpty()) throw new Err("error: syntax");
        for (int i = 0; i < tok.length(); i++) if ((LOW + DIG).indexOf(tok.charAt(i)) < 0) throw new Err("error: syntax");
        int e = tok.length();
        while (e > 0 && DIG.indexOf(tok.charAt(e - 1)) >= 0) e--;
        String name = tok.substring(0, e);
        String arg = tok.substring(e);
        if (name.isEmpty()) throw new Err("error: syntax");
        for (Object[] f : FILTERS) {
            if (f[0].equals(name)) {
                if ((Boolean) f[2]) {
                    if (arg.isEmpty() || arg.charAt(0) == '0' || arg.length() > 2) throw new Err("error: filter " + tok);
                    return new Filter((String) f[1], Integer.parseInt(arg));
                }
                if (!arg.isEmpty()) throw new Err("error: filter " + tok);
                return new Filter((String) f[1], 0);
            }
        }
        throw new Err("error: filter " + tok);
    }

    static Expr parseExpr(String c) {
        int ei = c.indexOf('=');
        String body = ei < 0 ? c : c.substring(0, ei);
        Expr x = new Expr();
        x.dflt = ei < 0 ? null : c.substring(ei + 1);
        String[] segs = body.split("\\|", -1);
        x.ref = segs[0];
        boolean ok = isName(x.ref) || (HAS_LOOP && (x.ref.equals(".") || x.ref.equals("@"))) || (HAS_PARENT && x.ref.equals(".."));
        if (!ok) throw new Err("error: syntax");
        if (segs.length > 1 && FILTERS.length == 0) throw new Err("error: syntax");
        for (int i = 1; i < segs.length; i++) x.filters.add(parseFilter(segs[i]));
        return x;
    }

    static List<Node> compile(String text) {
        List<Node> root = new ArrayList<>();
        List<Node> cur = root;
        List<Open> stack = new ArrayList<>();
        int pos = 0;
        for (;;) {
            int i = text.indexOf(OPEN, pos);
            if (i < 0) {
                if (pos < text.length()) cur.add(textNode(text.substring(pos)));
                break;
            }
            if (i > pos) cur.add(textNode(text.substring(pos, i)));
            int j = text.indexOf(CLOSE, i + OPEN.length());
            if (j < 0) throw new Err("error: unclosed");
            String c = text.substring(i + OPEN.length(), j);
            pos = j + CLOSE.length();
            if (c.isEmpty()) cur.add(textNode(OPEN));
            else if (c.charAt(0) == S_COMMENT) continue;
            else if (HAS_COND && c.equals(S_ELSE)) {
                if (stack.isEmpty() || stack.get(stack.size() - 1).inElse) throw new Err("error: unexpected");
                Open o = stack.get(stack.size() - 1);
                o.inElse = true;
                cur = o.other;
            } else if (HAS_COND && c.equals(S_END)) {
                if (stack.isEmpty()) throw new Err("error: unexpected");
                cur = stack.remove(stack.size() - 1).parent;
            } else if ((HAS_COND && (c.charAt(0) == S_IF || c.charAt(0) == S_NOT)) || (HAS_LOOP && c.charAt(0) == S_EACH)) {
                Node n = new Node();
                n.expr = parseExpr(c.substring(1));
                n.t = c.charAt(0) == S_EACH ? "each" : "if";
                n.neg = c.charAt(0) == S_NOT;
                cur.add(n);
                Open o = new Open();
                o.parent = cur;
                o.then = n.then;
                o.other = n.other;
                stack.add(o);
                cur = n.then;
            } else if (HAS_PART && c.charAt(0) == '>') {
                if (!isName(c.substring(1))) throw new Err("error: syntax");
                Node n = new Node();
                n.t = "part";
                n.s = c.substring(1);
                cur.add(n);
            } else {
                Node n = new Node();
                n.t = "var";
                n.expr = parseExpr(c);
                cur.add(n);
            }
        }
        if (!stack.isEmpty()) throw new Err("error: unclosed");
        return root;
    }

    static Node textNode(String s) {
        Node n = new Node();
        n.t = "text";
        n.s = s;
        return n;
    }

    static String applyFilter(Filter f, String v) {
        StringBuilder sb = new StringBuilder();
        switch (f.kind) {
            case "upper":
                for (char ch : v.toCharArray()) sb.append(ch >= 'a' && ch <= 'z' ? (char) (ch - 32) : ch);
                return sb.toString();
            case "lower":
                for (char ch : v.toCharArray()) sb.append(ch >= 'A' && ch <= 'Z' ? (char) (ch + 32) : ch);
                return sb.toString();
            case "trim": {
                int a = 0, b = v.length();
                while (a < b && v.charAt(a) == ' ') a++;
                while (b > a && v.charAt(b - 1) == ' ') b--;
                return v.substring(a, b);
            }
            case "len": return Integer.toString(v.length());
            case "rev": return new StringBuilder(v).reverse().toString();
            case "pad":
                sb.append(v);
                while (sb.length() < f.k) sb.append(' ');
                return sb.toString();
            case "cut": return v.length() <= f.k ? v : v.substring(0, f.k);
            case "dash": return v.replace(' ', '-');
            case "title": {
                char prev = ' ';
                for (char ch : v.toCharArray()) {
                    sb.append(prev == ' ' && ch >= 'a' && ch <= 'z' ? (char) (ch - 32) : ch);
                    prev = ch;
                }
                return sb.toString();
            }
            case "esc":
                for (char ch : v.toCharArray()) {
                    if (ch == '&') sb.append("&amp;");
                    else if (ch == '<') sb.append("&lt;");
                    else if (ch == '>') sb.append("&gt;");
                    else if (ch == '"') sb.append("&quot;");
                    else sb.append(ch);
                }
                return sb.toString();
            default: throw new IllegalStateException(f.kind);
        }
    }

    static String evaluate(Expr x, List<String[]> loops, Map<String, String> data) {
        String val = null;
        int n = loops.size();
        if (x.ref.equals(".")) val = n >= 1 ? loops.get(n - 1)[0] : null;
        else if (x.ref.equals("@")) val = n >= 1 ? loops.get(n - 1)[1] : null;
        else if (x.ref.equals("..")) val = n >= 2 ? loops.get(n - 2)[0] : null;
        else val = data.get(x.ref);
        if ((val == null || val.isEmpty()) && x.dflt != null) val = x.dflt;
        if (val == null) throw new Err("error: undefined " + x.ref);
        for (Filter f : x.filters) val = applyFilter(f, val);
        return val;
    }

    static void run(List<Node> nodes, List<String[]> loops, int depth, Map<String, String> data, StringBuilder out) {
        for (Node nd : nodes) {
            switch (nd.t) {
                case "text": out.append(nd.s); break;
                case "var": out.append(evaluate(nd.expr, loops, data)); break;
                case "if": {
                    String v = evaluate(nd.expr, loops, data);
                    boolean truth = true;
                    for (String f : FALSY) if (f.equals(v)) truth = false;
                    if (nd.neg) truth = !truth;
                    run(truth ? nd.then : nd.other, loops, depth, data, out);
                    break;
                }
                case "each": {
                    String v = evaluate(nd.expr, loops, data);
                    String[] items = v.isEmpty() ? new String[0] : v.split(",", -1);
                    if (items.length == 0) run(nd.other, loops, depth, data, out);
                    for (int ix = 0; ix < items.length; ix++) {
                        List<String[]> inner = new ArrayList<>(loops);
                        inner.add(new String[] { items[ix], Integer.toString(ix + 1) });
                        run(nd.then, inner, depth, data, out);
                    }
                    break;
                }
                case "part": {
                    if (!data.containsKey(nd.s)) throw new Err("error: undefined " + nd.s);
                    if (depth + 1 > MAXDEPTH) throw new Err("error: depth");
                    run(compile(data.get(nd.s)), loops, depth + 1, data, out);
                    break;
                }
                default: throw new IllegalStateException(nd.t);
            }
        }
    }

    public static String render(String template, String data) {
        try {
            Map<String, String> d = parseData(data);
            List<Node> tree = compile(template);
            StringBuilder out = new StringBuilder();
            run(tree, new ArrayList<>(), 0, d, out);
            return out.toString();
        } catch (Err e) {
            return e.getMessage();
        }
    }
}
'''

GO = r'''
package template

import (
	"strconv"
	"strings"
)

const (
	openD   = @OPEN@
	closeD  = @CLOSE@
	sIf     = @S_IF@
	sNot    = @S_NOT@
	sEach   = @S_EACH@
	sElse   = @S_ELSE@
	sEnd    = @S_END@
	sCmt    = @S_COMMENT@
	hasCond = @COND@
	hasLoop = @LOOP@
	hasPart = @PART@
	hasPar  = @PARENT@
	maxDep  = 4
)

var falsy = []string@FALSY@

type filterDef struct {
	alias, kind string
	takes       bool
}

var filterDefs = []filterDef@FILTERS@

type tmplErr struct{ msg string }

type filter struct {
	kind string
	k    int
}

type expr struct {
	ref     string
	filters []filter
	dflt    string
	hasDef  bool
}

type node struct {
	t     string
	s     string
	e     expr
	neg   bool
	then  *[]node
	other *[]node
}

type frame struct {
	parent  *[]node
	other   *[]node
	inElse  bool
}

func fail(m string) { panic(tmplErr{m}) }

func isName(s string) bool {
	if s == "" {
		return false
	}
	c := s[0]
	if !(c >= 'a' && c <= 'z') && c != '_' {
		return false
	}
	for i := 0; i < len(s); i++ {
		c = s[i]
		if !(c >= 'a' && c <= 'z') && !(c >= '0' && c <= '9') && c != '_' {
			return false
		}
	}
	return true
}

func parseData(text string) map[string]string {
	d := map[string]string{}
	for _, line := range strings.Split(text, "\n") {
		if line == "" {
			continue
		}
		ei := strings.IndexByte(line, '=')
		if ei < 0 {
			fail("error: data")
		}
		k, v := line[:ei], line[ei+1:]
		if _, dup := d[k]; !isName(k) || dup {
			fail("error: data")
		}
		var out strings.Builder
		for i := 0; i < len(v); i++ {
			if v[i] == '\\' {
				if i+1 >= len(v) || (v[i+1] != 'n' && v[i+1] != '\\') {
					fail("error: data")
				}
				if v[i+1] == 'n' {
					out.WriteByte('\n')
				} else {
					out.WriteByte('\\')
				}
				i++
			} else {
				out.WriteByte(v[i])
			}
		}
		d[k] = out.String()
	}
	return d
}

func isDigit(c byte) bool { return c >= '0' && c <= '9' }

func parseFilter(tok string) filter {
	if tok == "" {
		fail("error: syntax")
	}
	for i := 0; i < len(tok); i++ {
		if !(tok[i] >= 'a' && tok[i] <= 'z') && !isDigit(tok[i]) {
			fail("error: syntax")
		}
	}
	e := len(tok)
	for e > 0 && isDigit(tok[e-1]) {
		e--
	}
	name, arg := tok[:e], tok[e:]
	if name == "" {
		fail("error: syntax")
	}
	for _, f := range filterDefs {
		if f.alias == name {
			if f.takes {
				if arg == "" || arg[0] == '0' || len(arg) > 2 {
					fail("error: filter " + tok)
				}
				n, _ := strconv.Atoi(arg)
				return filter{f.kind, n}
			}
			if arg != "" {
				fail("error: filter " + tok)
			}
			return filter{f.kind, 0}
		}
	}
	fail("error: filter " + tok)
	return filter{}
}

func parseExpr(c string) expr {
	var x expr
	body := c
	if ei := strings.IndexByte(c, '='); ei >= 0 {
		body = c[:ei]
		x.dflt = c[ei+1:]
		x.hasDef = true
	}
	segs := strings.Split(body, "|")
	x.ref = segs[0]
	ok := isName(x.ref) || (hasLoop && (x.ref == "." || x.ref == "@")) || (hasPar && x.ref == "..")
	if !ok {
		fail("error: syntax")
	}
	if len(segs) > 1 && len(filterDefs) == 0 {
		fail("error: syntax")
	}
	for _, t := range segs[1:] {
		x.filters = append(x.filters, parseFilter(t))
	}
	return x
}

func compile(text string) []node {
	root := []node{}
	cur := &root
	var stack []*frame
	pos := 0
	for {
		i := strings.Index(text[pos:], openD)
		if i < 0 {
			if pos < len(text) {
				*cur = append(*cur, node{t: "text", s: text[pos:]})
			}
			break
		}
		i += pos
		if i > pos {
			*cur = append(*cur, node{t: "text", s: text[pos:i]})
		}
		j := strings.Index(text[i+len(openD):], closeD)
		if j < 0 {
			fail("error: unclosed")
		}
		j += i + len(openD)
		c := text[i+len(openD) : j]
		pos = j + len(closeD)
		switch {
		case c == "":
			*cur = append(*cur, node{t: "text", s: openD})
		case c[0] == sCmt[0]:
		case hasCond && c == sElse:
			if len(stack) == 0 || stack[len(stack)-1].inElse {
				fail("error: unexpected")
			}
			f := stack[len(stack)-1]
			f.inElse = true
			cur = f.other
		case hasCond && c == sEnd:
			if len(stack) == 0 {
				fail("error: unexpected")
			}
			cur = stack[len(stack)-1].parent
			stack = stack[:len(stack)-1]
		case (hasCond && (c[0] == sIf[0] || c[0] == sNot[0])) || (hasLoop && c[0] == sEach[0]):
			n := node{t: "if", e: parseExpr(c[1:]), neg: c[0] == sNot[0], then: &[]node{}, other: &[]node{}}
			if c[0] == sEach[0] {
				n.t = "each"
			}
			*cur = append(*cur, n)
			stack = append(stack, &frame{parent: cur, other: n.other})
			cur = n.then
		case hasPart && c[0] == '>':
			if !isName(c[1:]) {
				fail("error: syntax")
			}
			*cur = append(*cur, node{t: "part", s: c[1:]})
		default:
			*cur = append(*cur, node{t: "var", e: parseExpr(c)})
		}
	}
	if len(stack) > 0 {
		fail("error: unclosed")
	}
	return root
}

func applyFilter(f filter, v string) string {
	switch f.kind {
	case "upper":
		b := []byte(v)
		for i, c := range b {
			if c >= 'a' && c <= 'z' {
				b[i] = c - 32
			}
		}
		return string(b)
	case "lower":
		b := []byte(v)
		for i, c := range b {
			if c >= 'A' && c <= 'Z' {
				b[i] = c + 32
			}
		}
		return string(b)
	case "trim":
		return strings.Trim(v, " ")
	case "len":
		return strconv.Itoa(len(v))
	case "rev":
		b := []byte(v)
		for i, j := 0, len(b)-1; i < j; i, j = i+1, j-1 {
			b[i], b[j] = b[j], b[i]
		}
		return string(b)
	case "pad":
		if len(v) < f.k {
			return v + strings.Repeat(" ", f.k-len(v))
		}
		return v
	case "cut":
		if len(v) > f.k {
			return v[:f.k]
		}
		return v
	case "dash":
		return strings.ReplaceAll(v, " ", "-")
	case "title":
		b := []byte(v)
		prev := byte(' ')
		for i, c := range b {
			if prev == ' ' && c >= 'a' && c <= 'z' {
				b[i] = c - 32
			}
			prev = c
		}
		return string(b)
	case "esc":
		var sb strings.Builder
		for i := 0; i < len(v); i++ {
			switch v[i] {
			case '&':
				sb.WriteString("&amp;")
			case '<':
				sb.WriteString("&lt;")
			case '>':
				sb.WriteString("&gt;")
			case '"':
				sb.WriteString("&quot;")
			default:
				sb.WriteByte(v[i])
			}
		}
		return sb.String()
	}
	panic("bad filter " + f.kind)
}

type loopItem struct {
	item string
	idx  int
}

func evaluate(x expr, loops []loopItem, data map[string]string) string {
	val, have := "", false
	n := len(loops)
	switch x.ref {
	case ".":
		if n >= 1 {
			val, have = loops[n-1].item, true
		}
	case "@":
		if n >= 1 {
			val, have = strconv.Itoa(loops[n-1].idx), true
		}
	case "..":
		if n >= 2 {
			val, have = loops[n-2].item, true
		}
	default:
		val, have = data[x.ref]
	}
	if (!have || val == "") && x.hasDef {
		val, have = x.dflt, true
	}
	if !have {
		fail("error: undefined " + x.ref)
	}
	for _, f := range x.filters {
		val = applyFilter(f, val)
	}
	return val
}

func run(nodes []node, loops []loopItem, depth int, data map[string]string, out *strings.Builder) {
	for _, nd := range nodes {
		switch nd.t {
		case "text":
			out.WriteString(nd.s)
		case "var":
			out.WriteString(evaluate(nd.e, loops, data))
		case "if":
			v := evaluate(nd.e, loops, data)
			truth := true
			for _, f := range falsy {
				if f == v {
					truth = false
				}
			}
			if nd.neg {
				truth = !truth
			}
			if truth {
				run(*nd.then, loops, depth, data, out)
			} else {
				run(*nd.other, loops, depth, data, out)
			}
		case "each":
			v := evaluate(nd.e, loops, data)
			var items []string
			if v != "" {
				items = strings.Split(v, ",")
			}
			if len(items) == 0 {
				run(*nd.other, loops, depth, data, out)
			}
			for ix, it := range items {
				inner := append(append([]loopItem{}, loops...), loopItem{it, ix + 1})
				run(*nd.then, inner, depth, data, out)
			}
		case "part":
			src, ok := data[nd.s]
			if !ok {
				fail("error: undefined " + nd.s)
			}
			if depth+1 > maxDep {
				fail("error: depth")
			}
			run(compile(src), loops, depth+1, data, out)
		}
	}
}

// Render renders a template against data lines.
func Render(tpl, data string) (res string) {
	defer func() {
		if r := recover(); r != nil {
			if e, ok := r.(tmplErr); ok {
				res = e.msg
				return
			}
			panic(r)
		}
	}()
	d := parseData(data)
	tree := compile(tpl)
	var out strings.Builder
	run(tree, nil, 0, d, &out)
	return out.String()
}
'''

RB = r'''
module Template
  OPEN = @OPEN@
  CLOSE = @CLOSE@
  S_IF = @S_IF@
  S_NOT = @S_NOT@
  S_EACH = @S_EACH@
  S_ELSE = @S_ELSE@
  S_END = @S_END@
  S_COMMENT = @S_COMMENT@
  HAS_COND = @COND@
  HAS_LOOP = @LOOP@
  HAS_PART = @PART@
  HAS_PARENT = @PARENT@
  FALSY = @FALSY@
  FILTERS = @FILTERS@
  MAXDEPTH = 4
  LOW = 'abcdefghijklmnopqrstuvwxyz'
  DIG = '0123456789'

  class Err < StandardError; end

  def self.name?(s)
    return false if s.empty? || !(LOW + '_').include?(s[0])
    s.each_char { |c| return false unless (LOW + DIG + '_').include?(c) }
    true
  end

  def self.parse_data(text)
    d = {}
    text.split("\n", -1).each do |line|
      next if line.empty?
      ei = line.index('=')
      raise Err, 'error: data' if ei.nil?
      k = line[0, ei]
      v = line[(ei + 1)..-1]
      raise Err, 'error: data' if !name?(k) || d.key?(k)
      out = +''
      i = 0
      while i < v.length
        ch = v[i]
        if ch == '\\'
          raise Err, 'error: data' if i + 1 >= v.length || (v[i + 1] != 'n' && v[i + 1] != '\\')
          out << (v[i + 1] == 'n' ? "\n" : '\\')
          i += 2
        else
          out << ch
          i += 1
        end
      end
      d[k] = out
    end
    d
  end

  def self.parse_filter(tok)
    raise Err, 'error: syntax' if tok.empty?
    tok.each_char { |c| raise Err, 'error: syntax' unless (LOW + DIG).include?(c) }
    e = tok.length
    e -= 1 while e > 0 && DIG.include?(tok[e - 1])
    name = tok[0, e]
    arg = tok[e..-1]
    raise Err, 'error: syntax' if name.empty?
    FILTERS.each do |alias_, kind, takes|
      next unless alias_ == name
      if takes
        raise Err, "error: filter #{tok}" if arg.empty? || arg[0] == '0' || arg.length > 2
        return [kind, arg.to_i]
      end
      raise Err, "error: filter #{tok}" unless arg.empty?
      return [kind, 0]
    end
    raise Err, "error: filter #{tok}"
  end

  def self.parse_expr(c)
    ei = c.index('=')
    body = ei.nil? ? c : c[0, ei]
    dflt = ei.nil? ? nil : c[(ei + 1)..-1]
    segs = body.empty? ? [''] : body.split('|', -1)
    ref = segs[0]
    ok = name?(ref) || (HAS_LOOP && (ref == '.' || ref == '@')) || (HAS_PARENT && ref == '..')
    raise Err, 'error: syntax' unless ok
    raise Err, 'error: syntax' if segs.length > 1 && FILTERS.empty?
    { ref: ref, filters: segs[1..-1].map { |t| parse_filter(t) }, dflt: dflt }
  end

  def self.compile(text)
    root = []
    cur = root
    stack = []
    pos = 0
    loop do
      i = text.index(OPEN, pos)
      if i.nil?
        cur << { t: :text, s: text[pos..-1] } if pos < text.length
        break
      end
      cur << { t: :text, s: text[pos...i] } if i > pos
      j = text.index(CLOSE, i + OPEN.length)
      raise Err, 'error: unclosed' if j.nil?
      c = text[(i + OPEN.length)...j]
      pos = j + CLOSE.length
      if c.empty?
        cur << { t: :text, s: OPEN }
      elsif c[0] == S_COMMENT
        next
      elsif HAS_COND && c == S_ELSE
        raise Err, 'error: unexpected' if stack.empty? || stack[-1][:in_else]
        stack[-1][:in_else] = true
        cur = stack[-1][:other]
      elsif HAS_COND && c == S_END
        raise Err, 'error: unexpected' if stack.empty?
        cur = stack.pop[:parent]
      elsif (HAS_COND && (c[0] == S_IF || c[0] == S_NOT)) || (HAS_LOOP && c[0] == S_EACH)
        expr = parse_expr(c[1..-1])
        node = { t: (c[0] == S_EACH ? :each : :if), expr: expr, neg: c[0] == S_NOT, then: [], other: [] }
        cur << node
        stack << { parent: cur, other: node[:other], in_else: false }
        cur = node[:then]
      elsif HAS_PART && c[0] == '>'
        raise Err, 'error: syntax' unless name?(c[1..-1])
        cur << { t: :part, s: c[1..-1] }
      else
        cur << { t: :var, expr: parse_expr(c) }
      end
    end
    raise Err, 'error: unclosed' unless stack.empty?
    root
  end

  def self.apply_filter(f, v)
    kind, k = f
    case kind
    when 'upper' then v.gsub(/[a-z]/) { |ch| (ch.ord - 32).chr }
    when 'lower' then v.gsub(/[A-Z]/) { |ch| (ch.ord + 32).chr }
    when 'trim'
      a = 0
      b = v.length
      a += 1 while a < b && v[a] == ' '
      b -= 1 while b > a && v[b - 1] == ' '
      v[a...b]
    when 'len' then v.length.to_s
    when 'rev' then v.reverse
    when 'pad' then v.length < k ? v + (' ' * (k - v.length)) : v
    when 'cut' then v[0, k]
    when 'dash' then v.tr(' ', '-')
    when 'title'
      out = +''
      prev = ' '
      v.each_char do |ch|
        out << (prev == ' ' && ch >= 'a' && ch <= 'z' ? (ch.ord - 32).chr : ch)
        prev = ch
      end
      out
    when 'esc'
      m = { '&' => '&amp;', '<' => '&lt;', '>' => '&gt;', '"' => '&quot;' }
      v.gsub(/[&<>"]/) { |ch| m[ch] }
    else raise "bad filter #{kind}"
    end
  end

  def self.evaluate(x, loops, data)
    n = loops.length
    val = case x[:ref]
          when '.' then n >= 1 ? loops[n - 1][0] : nil
          when '@' then n >= 1 ? loops[n - 1][1].to_s : nil
          when '..' then n >= 2 ? loops[n - 2][0] : nil
          else data[x[:ref]]
          end
    val = x[:dflt] if (val.nil? || val.empty?) && !x[:dflt].nil?
    raise Err, "error: undefined #{x[:ref]}" if val.nil?
    x[:filters].each { |f| val = apply_filter(f, val) }
    val
  end

  def self.run(nodes, loops, depth, data, out)
    nodes.each do |nd|
      case nd[:t]
      when :text then out << nd[:s]
      when :var then out << evaluate(nd[:expr], loops, data)
      when :if
        v = evaluate(nd[:expr], loops, data)
        truth = !FALSY.include?(v)
        truth = !truth if nd[:neg]
        run(truth ? nd[:then] : nd[:other], loops, depth, data, out)
      when :each
        v = evaluate(nd[:expr], loops, data)
        items = v.empty? ? [] : v.split(',', -1)
        run(nd[:other], loops, depth, data, out) if items.empty?
        items.each_with_index { |it, ix| run(nd[:then], loops + [[it, ix + 1]], depth, data, out) }
      when :part
        raise Err, "error: undefined #{nd[:s]}" unless data.key?(nd[:s])
        raise Err, 'error: depth' if depth + 1 > MAXDEPTH
        run(compile(data[nd[:s]]), loops, depth + 1, data, out)
      end
    end
  end

  def self.render(template, data)
    d = parse_data(data)
    tree = compile(template)
    out = +''
    run(tree, [], 0, d, out)
    out
  rescue Err => e
    e.message
  end
end
'''



ALL_KINDS = ["upper", "lower", "trim", "len", "rev", "dash", "pad", "cut", "esc", "title"]
ALIASES = {"upper": ["upper", "up", "caps", "shout"], "lower": ["lower", "low", "quiet", "down"], "trim": ["trim", "strip", "clip"], "len": ["len", "size", "count"], "rev": ["rev", "flip", "mirror"],
           "dash": ["dash", "kebab", "hyphen"], "pad": ["pad", "ljust", "fill"], "cut": ["cut", "trunc", "take"], "esc": ["esc", "safe", "html"], "title": ["title", "cap", "proper"]}
TAKES = {"pad", "cut"}
DELIMS = [("{{", "}}"), ("<<", ">>"), ("[%", "%]"), ("((", "))"), ("<%", "%>")]
THEMES = [
    ("the ferry office", "The ferry office prints its passenger notices from templates."),
    ("the lighthouse log", "The lighthouse keeper's log is generated from a template."),
    ("the seed library", "The seed library fills in its loan slips with a template."),
    ("the kiln schedule", "The kiln schedule page is produced from a template."),
    ("the beekeepers' newsletter", "The beekeepers' newsletter is assembled from a template."),
]
WORDS = ["Dear", "visitor", "the", "ferry", "leaves", "at", "dawn", "please", "arrive", "early", "gate", "open", "closed", "today", "no", "refunds", "-", ":", ",", ".", "!", "bring", "a", "coat", "see", "you", "tide", "table", "x", "7"]
CAN = {"?": "if", "!": "not", "*": "each", "#": "comment"}


def params(rng, level, i):
    o, c = DELIMS[(i + rng.randrange(len(DELIMS))) % len(DELIMS)]
    kinds = []
    if level >= 2:
        kinds = ["upper"] + rng.sample(["lower", "trim", "len", "rev", "dash"], 2)
        if level >= 3:
            kinds.append("pad")
        if level >= 4:
            kinds.append("cut")
        if level >= 5:
            kinds += ["esc", "title"]
    filters = [(rng.choice(ALIASES[k]), k, k in TAKES) for k in kinds]
    return {
        "level": level, "open": o, "close": c, "cond": level >= 3, "loop": level >= 4, "part": level >= 5, "parent": level >= 5,
        "if": rng.choice("?+"), "not": rng.choice("!-"), "each": rng.choice("*~"), "else": rng.choice([":", "^"]), "end": rng.choice(["/", ";"]), "comment": rng.choice(["#", "'"]),
        "falsy": rng.choice([["", "0"], ["", "0", "no"], ["", "0", "no", "false", "off"]]), "filters": filters, "theme": THEMES[(i + rng.randrange(2)) % len(THEMES)],
    }


def sol(lang, p):
    src = {"python": PY, "javascript": JS, "java": JV, "go": GO, "ruby": RB}[lang]
    L = lambda s: K.lit(lang, s)  # noqa: E731
    if lang == "python":
        b = lambda v: "True" if v else "False"  # noqa: E731
    else:
        b = lambda v: "true" if v else "false"  # noqa: E731
    fl = p["filters"]
    if lang == "python":
        falsy = "[" + ", ".join(L(x) for x in p["falsy"]) + "]"
        filters = "[" + "".join(f"({L(a)}, {L(k)}, {b(t)}), " for a, k, t in fl) + "]"
    elif lang == "javascript":
        falsy = "[" + ", ".join(L(x) for x in p["falsy"]) + "]"
        filters = "[" + "".join(f"[{L(a)}, {L(k)}, {b(t)}], " for a, k, t in fl) + "]"
    elif lang == "ruby":
        falsy = "[" + ", ".join(L(x) for x in p["falsy"]) + "]"
        filters = "[" + "".join(f"[{L(a)}, {L(k)}, {b(t)}], " for a, k, t in fl) + "]"
    elif lang == "java":
        falsy = "{" + ", ".join(L(x) for x in p["falsy"]) + "}"
        filters = "{" + "".join(f"{{{L(a)}, {L(k)}, {b(t)}}}, " for a, k, t in fl) + "}"
    else:  # go
        falsy = "{" + ", ".join(L(x) for x in p["falsy"]) + "}"
        filters = "{" + "".join(f"{{{L(a)}, {L(k)}, {b(t)}}}, " for a, k, t in fl) + "}"
    return K.subst(
        src, OPEN=L(p["open"]), CLOSE=L(p["close"]), S_IF=L(p["if"]), S_NOT=L(p["not"]), S_EACH=L(p["each"]), S_ELSE=L(p["else"]), S_END=L(p["end"]), S_COMMENT=L(p["comment"]),
        COND=b(p["cond"]), LOOP=b(p["loop"]), PART=b(p["part"]), PARENT=b(p["parent"]), FALSY=falsy, FILTERS=filters,
    ).lstrip("\n")


# ---------------------------------------------------------------------------------------------------------------
# canonical notation -> instance syntax


def tr(p, s):
    sig = {"?": p["if"], "!": p["not"], "*": p["each"], "#": p["comment"]}
    alias = {k: a for a, k, _ in p["filters"]}

    def conv(m):
        c = m.group(1)
        if c == ":":
            c = p["else"]
        elif c == "/":
            c = p["end"]
        else:
            if c[:1] in sig:
                c = sig[c[0]] + c[1:]
            if c[:1] != p["comment"]:
                body, eq, rest = c.partition("=")
                segs = body.split("|")
                for k in range(1, len(segs)):
                    mm = re.fullmatch(r"([a-z]+)(\d*)", segs[k])
                    if mm and mm.group(1) in alias:
                        segs[k] = alias[mm.group(1)] + mm.group(2)
                c = "|".join(segs) + eq + rest
        return p["open"] + c + p["close"]

    s = re.sub(r"\{\{(.*?)\}\}", conv, s, flags=re.S)
    return s.replace("{{", p["open"]).replace("}}", p["close"])


def kinds_used(s):
    return set(re.findall(r"\|([a-z]+)\d*", "".join(re.findall(r"\{\{(.*?)\}\}", s, flags=re.S))))


def esc_data(v):
    return v.replace("\\", "\\\\").replace("\n", "\\n")


def data_text(pairs):
    return "\n".join(f"{k}={esc_data(v)}" for k, v in pairs)


def main_data(p):
    o, c = p["open"], p["close"]
    t = lambda s: tr(p, s)  # noqa: E731
    pairs = [("name", "Ada Lovelace"), ("city", "Port Aster"), ("flag", "1"), ("zero", "0"), ("off", "off"), ("empty", ""), ("items", "red,green,blue"), ("nums", "1,2,3,4"), ("one", "solo"),
             ("list2", "x,,y"), ("msg", 'a<b & "c"'), ("pad_text", "  spaced out  "), ("text", "line one\nline two"), ("no_value", "no")]
    if p["part"]:
        pairs += [("_row", t("{{@}}:{{.}};")), ("_head", t("[{{name|upper}}]")), ("_flagged", t("{{?flag}}Y{{:}}N{{/}}")), ("_loop", t("{{*nums}}<{{.}}{{>_inner}}>{{/}}")),
                  ("_inner", t("{{*list2}}({{..}}/{{.}}){{/}}")), ("_self", t("S{{>_self}}")), ("_ping", t("a{{>_pong}}")), ("_pong", t("b{{>_ping}}")), ("_bad", t("x{{?}}y")),
                  ("_open", t("x{{")), ("_text", "plain text, no tags"), ("_two", t("{{>_text}}+{{>_text}}")), ("_deep", t("{{>_d2}}")), ("_d2", t("{{>_d3}}")), ("_d3", t("{{>_d4}}")), ("_d4", t("D4"))]
    return pairs


SCALARS = ["name", "city", "flag", "zero", "off", "empty", "one", "msg", "pad_text", "no_value"]
LISTS = ["items", "nums", "one", "list2", "empty"]


def have(p, k):
    return any(kk == k for _, kk, _ in p["filters"])


def rand_filters(rng, p, maxn=2):
    out = []
    for _ in range(rng.randint(0, maxn) if p["filters"] else 0):
        a, k, takes = rng.choice(p["filters"])
        out.append(k + (str(rng.randint(1, 14)) if takes else ""))
    return out


def rand_ref(rng, p, loops, ghost):
    if p["loop"] and loops >= 1 and rng.random() < 0.55:
        r = rng.random()
        if p["parent"] and loops >= 2 and r < 0.3:
            return ".."
        return "." if r < 0.7 else "@"
    if ghost and rng.random() < 0.06:
        return "ghost"
    return rng.choice(SCALARS + LISTS)


def rand_expr(rng, p, loops, ghost, lst=False):
    if lst:
        ref = rng.choice(LISTS) if not (loops and rng.random() < 0.3) else rng.choice([".", "@"])
        if ghost and rng.random() < 0.05:
            ref = "ghost"
    else:
        ref = rand_ref(rng, p, loops, ghost)
    fl = rand_filters(rng, p, 1 if lst else 2)
    e = "|".join([ref] + fl)
    if rng.random() < 0.15:
        e += "=" + rng.choice(["none", "n/a", "", "-", "a|b", "x=y", "0", "1"])
    return e


def rand_text(rng):
    return " ".join(rng.choice(WORDS) for _ in range(rng.randint(1, 4))) + rng.choice(["", " ", "\n", " "])


def rand_body(rng, p, depth, loops, ghost):
    out = []
    for _ in range(rng.randint(1, 4)):
        r = rng.random()
        if r < 0.28:
            out.append(rand_text(rng))
        elif r < 0.62:
            out.append("{{" + rand_expr(rng, p, loops, ghost) + "}}")
        elif r < 0.66:
            out.append("{{#" + rng.choice(["note", "x y", ""]) + "}}")
        elif r < 0.69:
            out.append("{{}}")
        elif p["cond"] and depth < 3 and r < 0.86:
            sig = rng.choice("?!")
            blk = "{{" + sig + rand_expr(rng, p, loops, ghost) + "}}" + rand_body(rng, p, depth + 1, loops, ghost)
            if rng.random() < 0.55:
                blk += "{{:}}" + rand_body(rng, p, depth + 1, loops, ghost)
            out.append(blk + "{{/}}")
        elif p["loop"] and depth < 3 and loops < 2 and r < 0.96:
            blk = "{{*" + rand_expr(rng, p, loops, ghost, lst=True) + "}}" + rand_body(rng, p, depth + 1, loops + 1, ghost)
            if rng.random() < 0.4:
                blk += "{{:}}" + rand_body(rng, p, depth + 1, loops, ghost)
            out.append(blk + "{{/}}")
        elif p["part"]:
            out.append("{{>" + rng.choice(["_row", "_head", "_flagged", "_text", "_two", "_row", "_loop"]) + "}}")
        else:
            out.append(rand_text(rng))
    return "".join(out)


def canon_cases(p):
    """(template in canonical notation, data key) for hand-written edge cases"""
    c = []
    A = c.append
    for t in ["Hello, {{name}}!", "{{city}}", "{{name}} of {{city}}", "{{name}}{{city}}", "no tags here", "", "{{missing}}", "{{missing=none}}", "{{empty=fallback}}", "{{name=zzz}}", "{{empty=}}x",
              "{{missing=}}|", "{{#a comment}}text", "a{{}}b", "{{}}{{}}", "{{ name}}", "{{name }}", "{{Name}}", "{{1x}}", "{{na-me}}", "{{=x}}", "{{name", "text {{", "{{name}}}}", "}}{{name}}", "{{{name}}}",
              "{{name=a=b}}", "{{#}}", "{{#{{name}}", "{{#a}}{{#b}}", "{{name}}\n{{city}}\n", "{{text}}", "[{{msg}}]", "{{_x}}", "{{x_}}", "{{name=}}", "{{zero}}{{off}}{{no_value}}", "{{empty}}", "{{empty=}}",
              "{{name=a|b}}", "{{.}}", "{{@}}", "{{..}}", "{{?name}}", "{{:}}", "{{/}}", "{{*items}}", "{{>name}}", "{{name|upper}}", "{{name|}}", "{{|}}", "{{name|x}}", "{{ }}", "{{\t}}", "{{name}} {{ghost=}}!"]:
        A(t)
    if p["filters"]:
        for t in ["{{name|upper}}", "{{name|lower}}", "{{name|trim}}", "{{pad_text|trim}}", "[{{pad_text|trim|len}}]", "{{name|len}}", "{{name|rev}}", "{{name|dash}}", "{{name|upper|lower}}", "{{name|upper|len}}",
                  "{{missing|upper}}", "{{missing=none|upper}}", "{{empty=quiet voice|upper}}", "{{empty|len}}", "{{empty=|len}}", "{{msg|upper}}", "{{name|Upper}}", "{{name|up per}}", "{{name|up-per}}", "{{name||upper}}",
                  "{{name|upper|}}", "{{name|1}}", "{{name|9up}}", "{{name|upper2}}", "{{name|lower0}}", "{{name|bogus}}", "{{name|upper=x}}", "{{name=x|upper}}", "{{name|trim|trim}}", "{{pad_text|len}}",
                  "{{name|upper}}{{city|lower}}", "{{text|len}}", "{{text|rev}}", "{{text|dash}}", "{{one|rev|upper}}"]:
            A(t)
    if have(p, "pad"):
        for t in ["[{{name|pad20}}]", "[{{name|pad3}}]", "[{{name|pad12}}]", "[{{name|pad1}}]", "[{{one|pad99}}]", "[{{name|pad}}]", "[{{name|pad0}}]", "[{{name|pad05}}]", "[{{name|pad100}}]", "[{{name|pad-3}}]", "[{{name|pad3x}}]",
                  "[{{empty=|pad4}}]", "[{{name|upper|pad14}}|{{city|pad14}}]", "{{name|pad8|len}}", "{{name|trim|pad30|len}}"]:
            A(t)
    if have(p, "cut"):
        for t in ["{{name|cut3}}", "{{name|cut1}}", "{{name|cut50}}", "{{name|cut}}", "{{name|cut0}}", "{{name|cut007}}", "{{name|cut3|upper}}", "{{name|upper|cut5|rev}}", "{{empty=abcdef|cut2}}", "{{name|cut12}}{{city|cut4}}"]:
            A(t)
    if have(p, "esc"):
        for t in ["{{msg|esc}}", "{{msg|esc|esc}}", "{{msg|esc|len}}", "{{name|esc}}", "{{msg|esc|upper}}", "{{empty=<b>|esc}}"]:
            A(t)
    if have(p, "title"):
        for t in ["{{name|title}}", "{{pad_text|title}}", "{{name|lower|title}}", "{{text|title}}", "{{empty=a b  c|title}}", "{{name|title|dash}}", "{{city|title|rev}}"]:
            A(t)
    if p["cond"]:
        for t in ["{{?flag}}yes{{:}}no{{/}}", "{{?zero}}yes{{:}}no{{/}}", "{{?empty}}yes{{:}}no{{/}}", "{{?off}}yes{{:}}no{{/}}", "{{?no_value}}yes{{:}}no{{/}}", "{{?name}}yes{{/}}", "{{?zero}}yes{{/}}after",
                  "{{!flag}}yes{{:}}no{{/}}", "{{!zero}}yes{{:}}no{{/}}", "{{!empty}}yes{{/}}", "{{!off}}x{{:}}y{{/}}", "{{?missing}}a{{:}}b{{/}}", "{{?missing=0}}a{{:}}b{{/}}", "{{?missing=1}}a{{:}}b{{/}}", "{{?flag}}{{missing}}{{:}}fine{{/}}",
                  "{{?zero}}{{missing}}{{:}}fine{{/}}", "{{!flag}}{{missing}}{{/}}ok", "{{?flag}}a{{?zero}}b{{:}}c{{/}}d{{:}}e{{/}}", "{{?zero}}a{{?flag}}b{{/}}{{:}}e{{/}}", "{{?flag}}{{?flag}}{{?flag}}deep{{/}}{{/}}{{/}}",
                  "{{?flag}}a{{:}}b{{:}}c{{/}}", "{{:}}x", "{{/}}x", "x{{/}}", "{{?flag}}a", "{{?flag}}a{{:}}b", "{{?flag}}{{?zero}}a{{/}}", "{{?}}a{{/}}", "{{? flag}}a{{/}}", "{{?Flag}}a{{/}}", "{{?flag}}a{{/}}{{/}}",
                  "{{?flag}}a{{#c}}b{{/}}", "{{?flag}}{{}}{{/}}", "{{?flag}}", "{{?flag}}a{{name", "a{{?flag}}b{{:}}{{:}}c{{/}}", "{{?flag}}a{{/}}{{:}}", "{{!}}a{{/}}", "{{?flag|bogus}}a{{/}}", "{{?flag}}{{name|bogus}}{{:}}x{{/}}",
                  "{{?zero}}{{name|bogus}}{{:}}x{{/}}", "{{?zero}}{{?}}{{:}}x{{/}}", "{{?name}}{{:}}{{/}}", "{{?empty=1}}[{{empty}}]{{/}}", "{{?flag}}a{{:}}b{{/}}{{?flag}}c{{/}}"]:
            A(t)
        if p["filters"]:
            for t in ["{{?items|len}}many{{/}}", "{{?empty|len}}one{{:}}none{{/}}", "{{?zero|len}}[{{zero|len}}]{{/}}", "{{?flag|upper}}x{{/}}", "{{?empty=0|upper}}t{{:}}f{{/}}", "{{!flag|len}}a{{:}}b{{/}}"]:
                A(t)
    if p["loop"]:
        for t in ["{{*items}}[{{.}}]{{/}}", "{{*items}}{{@}}:{{.}} {{/}}", "{{*nums}}{{.}}{{/}}", "{{*one}}<{{.}}>{{/}}", "{{*empty}}x{{:}}none{{/}}", "{{*list2}}[{{.}}]{{/}}", "{{*list2}}{{@}}{{.=-}}{{/}}", "{{*items}}x{{:}}none{{/}}",
                  "{{*missing}}x{{:}}none{{/}}", "{{*missing=a,b}}{{.}}{{/}}", "{{*empty=p,q}}{{.}}{{/}}", "{{*name}}[{{.}}]{{/}}", "{{*msg}}[{{.}}]{{/}}", "{{.}}{{@}}", "{{*items}}{{*nums}}{{.}}{{/}}|{{/}}", "{{*items}}{{@}}{{*nums}}{{@}}{{/}}{{/}}",
                  "{{*items}}{{.}}{{?flag}}!{{/}} {{/}}", "{{*nums}}{{?.}}{{.}}{{:}}-{{/}}{{/}}", "{{*list2}}{{?.}}{{.}}{{:}}_{{/}}{{/}}", "{{*items}}{{*nums}}{{@}}{{/}}{{/}}", "{{*items}}", "{{*items}}{{:}}x", "{{*items}}a{{:}}b{{:}}c{{/}}",
                  "{{*}}x{{/}}", "{{* items}}x{{/}}", "{{*items}}{{missing}}{{/}}", "{{*empty}}{{missing}}{{:}}fine{{/}}", "{{*items}}{{.}}{{/}}{{.}}", "{{@}}{{*items}}{{/}}", "{{*items}}a{{/}}{{*nums}}b{{/}}", "{{*items}}{{.=z}}{{/}}",
                  "{{*list2}}{{.=z}}{{/}}", "{{*list2}}{{.|}}{{/}}", "{{*nums}}{{?@}}{{@}}{{/}}{{/}}", "{{*items}}{{!.}}x{{:}}y{{/}}{{/}}", "{{*one}}{{*one}}{{@}}{{.}}{{/}}{{/}}", "{{*nums|len}}x{{/}}", "{{*items}}{{#c}}{{/}}"]:
            A(t)
        if p["filters"]:
            for t in ["{{*items}}{{.|upper}} {{/}}", "{{*items}}{{@}}.{{.|rev}} {{/}}", "{{*nums|len}}n{{/}}", "{{*items}}{{.|len}}{{/}}", "{{*name|dash}}[{{.}}]{{/}}", "{{*items}}{{.|bogus}}{{:}}x{{/}}", "{{*empty}}{{.|bogus}}{{:}}x{{/}}"]:
                A(t)
    if p["part"]:
        for t in ["{{>_head}}", "{{>_row}}", "{{*items}}{{>_row}}{{/}}", "{{*nums}}{{>_row}}{{/}}", "{{>_flagged}}", "{{>_loop}}", "{{*items}}{{>_inner}}{{/}}", "{{>_self}}", "{{>_ping}}", "{{>_pong}}", "{{>_bad}}", "{{>_open}}", "{{>_two}}", "{{>_deep}}",
                  "{{>_d2}}", "{{>_d3}}", "{{>_d4}}", "{{>missing}}", "{{>name}}", "{{>}}", "{{>Name}}", "{{> name}}", "{{>_head|upper}}", "{{>_head=x}}", "{{?zero}}{{>_self}}{{:}}ok{{/}}", "{{?flag}}{{>_self}}{{:}}ok{{/}}", "{{?zero}}{{>_nothere}}{{/}}fine",
                  "{{*items}}{{*nums}}{{.}}/{{..}} {{/}}{{/}}", "{{*items}}{{..}}{{/}}", "{{*items}}{{*one}}{{..}}{{@}}{{/}}{{/}}", "{{..}}", "{{*items}}{{..=none}}{{/}}", "{{*items}}{{*list2}}{{..}}{{.=_}}{{/}}{{/}}", "{{>_head}}{{>_head}}", "{{>_text}}{{>_text}}",
                  "{{#x}}{{>_text}}", "{{>_flagged}}{{>_flagged}}"]:
            A(t)
    return c


def make_cases(rng, p, ns):
    render = ns["render"]
    main = data_text(main_data(p))
    small = "name=Ada\ncity=Oslo"
    odd = "flag=\nzero=0\nname=a=b\nempty=\nitems=\nnums=1\none=x,\nlist2=,\nmsg=\\\\q\\n\ntext=l1\\nl2"
    sets = {"main": main, "small": small, "odd": odd}
    cases = []

    def add(t, d):
        cases.append((t, d))

    # handwritten canonical cases against the main data
    for t in canon_cases(p):
        if any(not have(p, k) for k in kinds_used(t) if k in ALL_KINDS):
            continue
        add(tr(p, t), main)
        if rng.random() < 0.18:
            add(tr(p, t), rng.choice([small, odd]))
    # random templates
    good = 0
    tries = 0
    target = 110
    while good < target and tries < 2000:
        tries += 1
        t = rand_body(rng, p, 0, 0, ghost=(tries % 7 == 0))
        if any(not have(p, k) for k in kinds_used(t) if k in ALL_KINDS):
            continue
        tt = tr(p, t)
        d = rng.choice([main, main, main, small, odd])
        out = render(tt, d)
        if out.startswith("error: ") and rng.random() < 0.7:
            continue
        add(tt, d)
        good += 1
    # data errors
    for d in ["name", "name=", "=x", "Name=x", "a=1\na=2", "a=\\q", "a=x\\", "a=1\n\nb=2\n", "1a=b", "a b=c", "a=b=c", "\n", "\n\nname=x\n\n", "a=\\n\\\\", "a=\\\\\\", "a=\\\\n", "a-b=1", "a=1\nb", "a=1\r\nb=2", "_u=1\n_u=2", "x=\\N"]:
        add(tr(p, "{{name=ok}}"), d)
    add("{{", "name")  # data error beats template error
    add(tr(p, "{{name}}"), "x")
    add(tr(p, "{{}}"), "")
    add(tr(p, "plain"), "")
    add(tr(p, "{{missing}}"), "name=Ada\nname=Bob")
    # multi-line data values land in the output
    add(tr(p, "{{text}}|{{msg}}"), main)
    # delimiters of the other families are plain text here
    for o, c in DELIMS:
        if (o, c) != (p["open"], p["close"]) and o != p["open"][0] + p["open"][0]:
            add(f"{o}name{c} {tr(p, '{{name}}')}", main)
    # examples first
    ex = []
    ex.append((tr(p, "Hello, {{name}}!"), small))
    ex.append((tr(p, "{{city=nowhere}} / {{missing=none}}"), "name=Ada"))
    if p["filters"]:
        a = [al for al, k, _ in p["filters"] if k == "upper"][0]
        ex.append((tr(p, "{{name|upper}} ({{city|len}})") if have(p, "len") else tr(p, "{{name|upper}}"), small))
    if p["cond"]:
        ex.append((tr(p, "{{?flag}}on{{:}}off{{/}} {{!flag}}x{{/}}"), "flag=1"))
    if p["loop"]:
        ex.append((tr(p, "{{*items}}{{@}}={{.}}; {{:}}nothing{{/}}"), "items=ant,bee"))
    if p["part"]:
        ex.append((tr(p, "{{*items}}{{>_row}}{{/}}"), "items=ant,bee\n_row=" + tr(p, "{{@}}:{{.}} ")))
    nex = len(ex)
    allc = ex + cases
    out, seen = [], set()
    for cc in allc:
        if cc not in seen:
            seen.add(cc)
            out.append(cc)
    return out, nex


def readme(p, api, lang, examples, ns):
    O, C = p["open"], p["close"]
    t = lambda s: tr(p, s)  # noqa: E731
    L = [f"# Text templates for {p['theme'][0]}", ""]
    L.append(f"{p['theme'][1]} `render(template, data)` fills a template with values from a list of `NAME=VALUE` lines and returns the text.")
    L.append("")
    L.append("## Data")
    L.append("")
    L.append("`data` is text made of lines separated by `\\n`. Empty lines are ignored. Every other line is `NAME=VALUE`: `NAME` consists of lower-case ASCII letters, digits and `_` and does not start with a digit; `VALUE` is everything after the first `=` (it may be empty and may contain further `=`). "
             "Inside a value, a backslash and an `n` (`\\n`) stand for a newline and two backslashes (`\\\\`) for one backslash; any other use of a backslash is an error. A line that does not have this form, or a name that appears twice, is an error (`error: data`). All text is ASCII.")
    L.append("")
    L.append("## Templates")
    L.append("")
    L.append(f"Text is copied unchanged, except for **tags**. A tag starts with `{O}` and ends at the first `{C}` after it (a `{C}` that is not inside a tag is ordinary text). The text between the two delimiters is the tag's *content*; it is never trimmed, so a space inside a tag counts. The first character of the content decides what kind of tag it is:")
    L.append("")
    L.append(f"* **empty content** (`{O}{C}`): outputs the text `{O}` (the way to write the opening delimiter literally).")
    L.append(f"* starts with `{p['comment']}`: a **comment**; it produces nothing.")
    if p["cond"]:
        L.append(f"* content exactly `{p['else']}` is an **else** marker and exactly `{p['end']}` an **end** marker (see *Conditionals*{' and *Loops*' if p['loop'] else ''}).")
        L.append(f"* starts with `{p['if']}` or `{p['not']}`: the start of a **conditional** block.")
    if p["loop"]:
        L.append(f"* starts with `{p['each']}`: the start of a **loop** block.")
    if p["part"]:
        L.append("* starts with `>`: a **partial** (see *Partials*).")
    L.append("* anything else is a **value tag**: its content is an expression and the tag is replaced by its value." + (" Content that does not fit any form is `error: syntax`." if True else ""))
    L.append("")
    L.append("## Expressions")
    L.append("")
    refs = "a data name" + (", or `.` or `@` inside a loop" if p["loop"] else "") + (" (and `..`, see *Loops*)" if p["parent"] else "")
    L.append(f"An expression is `REF`" + (", then any number of filters each introduced by `|`," if p["filters"] else "") + " then optionally `=DEFAULT`. The **first `=`** in the expression starts the default, which runs to the end of the content and may contain any characters, even `|` and `=`. " + f"`REF` is {refs}; anything else is `error: syntax`.")
    L.append("")
    L.append("To evaluate it: take the value of `REF`. If `REF` has no value (a data name that is not defined" + (", or `.`/`@`/`..` outside the loops they refer to" if p["loop"] else "") + ") **or its value is the empty text**, and a default is present, the default (possibly empty) is used instead. If there is still no value the result is `error: undefined REF`."
             + (" Then the filters are applied from left to right." if p["filters"] else ""))
    L.append("")
    if p["filters"]:
        L.append("### Filters")
        L.append("")
        L.append("A filter is written as a token of lower-case letters followed by an optional number. Any other token (an empty one, one with capitals, `-` or blanks) is `error: syntax`. A well-formed token that is not in the table, or that has a missing number where one is needed, a number where none is allowed, or a number that is not `1` to `99` without leading zeros, is `error: filter TOKEN` (with the token as written).")
        L.append("")
        L.append("| filter | effect |")
        L.append("|---|---|")
        desc = {
            "upper": "ASCII letters `a` to `z` become capitals; everything else is unchanged", "lower": "ASCII capitals become lower-case; everything else is unchanged",
            "trim": "removes spaces (only the space character) from both ends", "len": "the number of characters, as a decimal number", "rev": "the characters in reverse order",
            "dash": "every space becomes `-`", "pad": "appends spaces until the text has `N` characters (a longer text is unchanged)", "cut": "keeps the first `N` characters (a shorter text is unchanged)",
            "esc": "`&` becomes `&amp;`, `<` becomes `&lt;`, `>` becomes `&gt;` and `\"` becomes `&quot;`", "title": "every ASCII letter `a` to `z` that is at the start or directly after a space becomes a capital",
        }
        for a, k, takes in p["filters"]:
            L.append(f"| `{a}{'N' if takes else ''}` | {desc[k]} |")
        L.append("")
    else:
        L.append("There are no filters in this version of the language; a `|` in the reference part is `error: syntax`.")
        L.append("")
    if p["cond"]:
        L.append("## Conditionals")
        L.append("")
        fl = ", ".join(f"`{x}`" if x else "the empty text" for x in p["falsy"])
        L.append(f"`{p['if']}EXPR` ... `{p['else']}` ... `{p['end']}` (the else part is optional). The expression is evaluated as above and its text is *false* if it is exactly one of {fl} (case-sensitive), otherwise *true*. The first part is rendered when true, the else part when false. `{p['not']}EXPR` is the opposite test. Blocks may be nested. "
                 "Only the chosen part is rendered: expressions in the other part are never evaluated, so an undefined name there is not an error. Every part is still *parsed*, so syntax errors are reported wherever they are.")
        L.append("")
    if p["loop"]:
        L.append("## Loops")
        L.append("")
        L.append(f"`{p['each']}EXPR` ... `{p['end']}`: the expression's text is split at every `,` into items (the empty text gives no items; `a,,b` gives three items, the middle one empty). The body is rendered once per item, with `.` standing for the item and `@` for its number counting from 1. "
                 f"If there are no items the else part (`{p['else']}`, optional) is rendered instead. `.` and `@` refer to the innermost loop." + (" Inside two nested loops `..` is the item of the enclosing loop (one level up; there is no `...`)." if p["parent"] else ""))
        L.append("")
    if p["part"]:
        L.append("## Partials")
        L.append("")
        L.append("`>NAME` (where `NAME` is a valid name): the value of the data entry `NAME` is itself a template. It is rendered with the same data and the same loops (so `.`, `@` and `..` keep their meaning) and its output replaces the tag. If there is no such entry the result is `error: undefined NAME`. "
                 "A partial that renders partials that render partials... may be nested at most **4** levels deep (a template rendered from the top is level 0, a partial it includes level 1, and so on); needing level 5 is `error: depth`. A partial is parsed when it is reached, so its own errors are reported at that moment.")
        L.append("")
    L.append("## Errors")
    L.append("")
    L.append("Any error ends the whole render: the result is just the error text, never partial output. The order is:")
    L.append("")
    L.append("1. `error: data`, found while reading the whole data text.")
    probs = ["`error: syntax`"]
    if p["filters"]:
        probs.append("`error: filter TOKEN`")
    if p["cond"]:
        probs.append("`error: unexpected` (an else or end marker with no open block, or a second else marker in one block)")
    probs.append("`error: unclosed` (an opening delimiter with no closing delimiter after it" + (", or a block still open at the end of the template)" if p["cond"] else ")"))
    L.append("2. while scanning the template from left to right, the **first** problem found: " + ", ".join(probs) + ". A template is scanned completely before any of it is rendered.")
    L.append("3. while rendering, in output order: `error: undefined NAME`" + (", `error: depth`." if p["part"] else "."))
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    for k, ((tpl, d), out) in enumerate(examples):
        L.append(f"**Example {k + 1}**")
        L.append("")
        L.append(f"* template: `{tpl}`")
        L.append("* data: " + (", ".join(f"`{ln}`" for ln in d.split("\n")) if d else "(empty)"))
        L.append(f"* result: `{out}`")
        L.append("")
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


def prompt(rng, p, api, lang):
    where = api.short(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    feats = ["value tags with defaults and comments"] + (["filters"] if p["filters"] else []) + (["conditionals"] if p["cond"] else []) + (["loops"] if p["loop"] else []) + (["partials"] if p["part"] else [])
    fl = ", ".join(feats[:-1]) + (" and " if len(feats) > 1 else "") + feats[-1]
    opts = [
        f"{p['theme'][0].capitalize()} needs a small template engine. Write `{fn}(template, data)` in {ln}, in {where}, following README.md ({fl}). {K.closer(rng)}",
        f"Implement the template renderer described in README.md in {ln} (`{fn}`, {where}). This version supports {fl}; pay attention to the order in which errors are reported. {K.closer(rng)}",
        f"Template engine with invented syntax, {ln}: `{fn}` in {where}; delimiters, sigils and error texts are all in README.md. Hidden checks include malformed tags and edge-case data. {K.closer(rng)}",
        f"Please build `{fn}` ({ln}, {where}) from the spec in README.md: it renders a template against `NAME=VALUE` data lines and supports {fl}.",
    ]
    return rng.choice(opts).strip()


DNAME = {"{{": "braces", "<<": "angles", "[%": "brackets", "((": "parens", "<%": "percent"}
LANG_PLAN = ["javascript", "ruby", "go", "java", "ruby", "javascript", "java", "go"]
LEVELS = [1, 1, 2, 2, 3, 3, 4, 5]


@family("greenfield-template", category="greenfield", lang="mixed", kind="greenfield", n=8,
        summary="template engine with an invented syntax: value tags, defaults, filters, conditionals, loops and partials, with strict ordered error reporting")
def gen(rng, n):
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = LEVELS[i % len(LEVELS)]
        p = params(rng, level, i)
        api = K.Api(mod="template", fn="render", args=["template", "data"], arg_docs=["the template text", "the data: lines of `NAME=VALUE`"], ret_doc="the rendered text, or an error text", doc="template renderer")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["render"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples, ns)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=level, slug=f"{i + 1:02d}-{lang}-{DNAME[p['open']]}-l{level}", oracle=(None if lang == "python" else ns["render"]),
            tags=["template", "parser"], notes={"level": level, "open": p["open"], "close": p["close"]},
        )
