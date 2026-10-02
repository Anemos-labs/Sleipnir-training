"""A state-machine definition language: parse a definition, feed it events, print the trace (guards, counters, entry/exit actions, hierarchy)."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

ARROWS = ["->", "=>", ">>", "=>>"]
ON_KW = ["on", "when", "upon", "case"]
STATE_KW = ["state", "mode", "phase", "stage"]
ACT_SEP = ["/", "!", "do", "run"]
MACHINES = [
    ("a ferry-gate controller", ["closed", "opening", "open", "closing", "locked", "fault"], ["push", "timer", "key", "jam", "reset", "wave", "coin", "sensor"]),
    ("a tide-clock", ["idle", "rising", "falling", "slack", "alarm", "muted"], ["tick", "high", "low", "ack", "mute", "storm", "calm"]),
    ("a kettle", ["off", "heating", "boiling", "keepwarm", "dry", "error"], ["power", "boil", "lift", "place", "timeout", "refill", "tick"]),
    ("a library lending desk", ["free", "reserved", "lent", "overdue", "lost", "archived"], ["borrow", "return", "reserve", "remind", "fine", "audit", "cancel"]),
    ("a lighthouse lamp", ["dark", "warming", "beam", "sweep", "flash", "failsafe"], ["dusk", "dawn", "warm", "fog", "spin", "cut", "test"]),
]
EMITS = ["beep", "log", "lock", "unlock", "ring", "flash", "report", "reset", "notify", "open", "close", "hum", "alert", "ok", "bad"]
VARS = ["n", "tries", "count", "hits", "level", "fuel", "load", "z"]
LANG_PLAN = ["ruby", "java", "python", "javascript", "ruby", "java", "javascript", "python", "ruby", "java", "javascript", "ruby"]


def params(rng, level, i):
    m = rng.choice(MACHINES)
    return {
        "level": level, "machine": m, "arrow": rng.choice(ARROWS), "on": rng.choice(ON_KW), "state": rng.choice(STATE_KW), "act": rng.choice(ACT_SEP),
        "guards": level >= 3, "hier": level >= 4,
    }


PY = r'''
ARROW = "@ARROW@"
ON = "@ON@"
STATE = "@STATE@"
ACT = "@ACT@"
HAS_GUARDS = @GUARDS@
HAS_HIER = @HIER@
LET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
DIG = "0123456789"
OPS = ("<", "<=", ">", ">=", "==", "!=")


def ident(s):
    return s != "" and s[0] in LET and all(c in LET + DIG for c in s)


def integer(s):
    body = s[1:] if s[:1] == "-" else s
    return body != "" and len(body) <= 6 and all(c in DIG for c in body)


def parse_actions(text):
    acts = []
    if text.strip(" \t") == "":
        return None
    for piece in text.split(","):
        w = piece.split()
        if not w:
            return None
        v = w[0]
        if v == "emit" and len(w) == 2 and ident(w[1]):
            acts.append(("emit", w[1], 0))
        elif v == "set" and len(w) == 3 and ident(w[1]) and integer(w[2]):
            acts.append(("set", w[1], int(w[2])))
        elif v in ("inc", "dec") and len(w) in (2, 3) and ident(w[1]) and (len(w) == 2 or integer(w[2])):
            amt = int(w[2]) if len(w) == 3 else 1
            acts.append(("add", w[1], amt if v == "inc" else -amt))
        else:
            return None
    return acts


def parse(defn):
    states = {}
    errs = []
    refs = []
    initial = None
    cur = None
    for no, raw in enumerate(defn.split("\n"), 1):
        w = raw.split("#", 1)[0].split()
        if not w:
            continue
        k = w[0]
        if k == STATE:
            ok = (len(w) == 2) or (HAS_HIER and len(w) == 4 and w[2] == "<")
            if not ok or not ident(w[1]) or (len(w) == 4 and not ident(w[3])):
                errs.append((no, "bad state"))
            elif w[1] in states:
                errs.append((no, "duplicate state"))
            else:
                parent = w[3] if len(w) == 4 else None
                states[w[1]] = {"line": no, "parent": parent, "trans": [], "enter": [], "exit": []}
                if parent:
                    refs.append((no, parent))
                cur = w[1]
        elif k == "initial":
            if len(w) != 2 or not ident(w[1]):
                errs.append((no, "bad initial"))
            elif initial is not None:
                errs.append((no, "duplicate initial"))
            else:
                initial = w[1]
                refs.append((no, w[1]))
        elif k == ON or (HAS_GUARDS and k in ("enter", "exit")):
            if cur is None:
                errs.append((no, "outside state"))
                continue
            if k in ("enter", "exit"):
                acts = parse_actions(" ".join(w[1:]))
                if acts is None:
                    errs.append((no, "bad action"))
                else:
                    states[cur][k].extend(acts)
                continue
            v = w[1:]
            guard = None
            i = 1
            if len(v) < 3 or not ident(v[0]):
                errs.append((no, "bad transition"))
                continue
            if v[1] == "if":
                if not HAS_GUARDS or len(v) < 5 or not ident(v[2]) or v[3] not in OPS or not integer(v[4]):
                    errs.append((no, "bad transition"))
                    continue
                guard = (v[2], v[3], int(v[4]))
                i = 5
            if i >= len(v) or v[i] != ARROW or i + 1 >= len(v) or not ident(v[i + 1]):
                errs.append((no, "bad transition"))
                continue
            target = v[i + 1]
            rest = v[i + 2:]
            acts = []
            if rest:
                if rest[0] != ACT:
                    errs.append((no, "bad transition"))
                    continue
                acts = parse_actions(" ".join(rest[1:]))
                if acts is None:
                    errs.append((no, "bad action"))
                    continue
            states[cur]["trans"].append((v[0], guard, target, acts))
            refs.append((no, target))
        else:
            errs.append((no, "unknown directive"))
    for no, name in refs:
        if name not in states:
            errs.append((no, "unknown state"))
    for name, s in states.items():
        seen = set()
        x = name
        while x is not None and x in states and x not in seen:
            seen.add(x)
            x = states[x]["parent"]
        if x is not None and x in seen:
            errs.append((s["line"], "parent cycle"))
    if errs:
        return None, "error: line %d: %s" % min(errs)
    if initial is None:
        return None, "error: no initial state"
    return (states, initial), None


def ancestors(states, name):
    out = []
    p = states[name]["parent"]
    while p is not None:
        out.append(p)
        p = states[p]["parent"]
    return out


def machine(defn, events):
    parsed, err = parse(defn)
    if err:
        return err
    states, initial = parsed
    counters = {}
    touched = set()
    emitted = []

    def run(acts):
        for kind, name, val in acts:
            if kind == "emit":
                emitted.append(name)
            elif kind == "set":
                counters[name] = val
                touched.add(name)
            else:
                counters[name] = counters.get(name, 0) + val
                touched.add(name)

    def fmt(text):
        return text + (" | " + " ".join(emitted) if emitted else "")

    out = []
    chain = list(reversed(ancestors(states, initial))) + [initial]
    for s in chain:
        run(states[s]["enter"])
    out.append(fmt("start: -> " + initial))
    state = initial
    for e in events.split():
        emitted = []
        fired = None
        a = state
        while a is not None and fired is None:
            for t in states[a]["trans"]:
                if t[0] != e:
                    continue
                ok = True
                if t[1]:
                    v = counters.get(t[1][0], 0)
                    op, n = t[1][1], t[1][2]
                    ok = {"<": v < n, "<=": v <= n, ">": v > n, ">=": v >= n, "==": v == n, "!=": v != n}[op]
                if ok:
                    fired = t
                    break
            a = states[a]["parent"]
        if fired is None:
            out.append("%s: ignored" % e)
            continue
        target = fired[2]
        anc_t = ancestors(states, target)
        lca = None
        for x in ancestors(states, state):
            if x in anc_t:
                lca = x
                break
        exits = []
        x = state
        while x != lca:
            exits.append(x)
            x = states[x]["parent"]
        enters = []
        x = target
        while x != lca:
            enters.append(x)
            x = states[x]["parent"]
        enters.reverse()
        for s in exits:
            run(states[s]["exit"])
        run(fired[3])
        for s in enters:
            run(states[s]["enter"])
        out.append(fmt("%s: %s -> %s" % (e, state, target)))
        state = target
    fin = "final " + state + "".join(" %s=%d" % (n, counters[n]) for n in sorted(touched))
    out.append(fin)
    return "\n".join(out)
'''

RB = r'''
module Statemachine
  ARROW = '@ARROW@'
  ON = '@ON@'
  STATE = '@STATE@'
  ACT = '@ACT@'
  HAS_GUARDS = @GUARDS@
  HAS_HIER = @HIER@
  LET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_'
  DIG = '0123456789'
  OPS = %w[< <= > >= == !=]

  def self.ident?(s)
    !s.empty? && LET.include?(s[0]) && s.each_char.all? { |c| LET.include?(c) || DIG.include?(c) }
  end

  def self.integer?(s)
    body = s[0] == '-' ? s[1..] : s
    !body.empty? && body.length <= 6 && body.each_char.all? { |c| DIG.include?(c) }
  end

  def self.parse_actions(text)
    return nil if text.strip.empty?
    acts = []
    text.split(',', -1).each do |piece|
      w = piece.split
      return nil if w.empty?
      v = w[0]
      if v == 'emit' && w.length == 2 && ident?(w[1])
        acts << ['emit', w[1], 0]
      elsif v == 'set' && w.length == 3 && ident?(w[1]) && integer?(w[2])
        acts << ['set', w[1], w[2].to_i]
      elsif (v == 'inc' || v == 'dec') && [2, 3].include?(w.length) && ident?(w[1]) && (w.length == 2 || integer?(w[2]))
        amt = w.length == 3 ? w[2].to_i : 1
        acts << ['add', w[1], v == 'inc' ? amt : -amt]
      else
        return nil
      end
    end
    acts
  end

  def self.parse(defn)
    states = {}
    errs = []
    refs = []
    initial = nil
    cur = nil
    defn.split("\n", -1).each_with_index do |raw, idx|
      no = idx + 1
      w = raw.split('#', 2)[0].to_s.split
      next if w.empty?
      k = w[0]
      if k == STATE
        ok = w.length == 2 || (HAS_HIER && w.length == 4 && w[2] == '<')
        if !ok || !ident?(w[1]) || (w.length == 4 && !ident?(w[3]))
          errs << [no, 'bad state']
        elsif states.key?(w[1])
          errs << [no, 'duplicate state']
        else
          parent = w.length == 4 ? w[3] : nil
          states[w[1]] = { line: no, parent: parent, trans: [], enter: [], exit: [] }
          refs << [no, parent] if parent
          cur = w[1]
        end
      elsif k == 'initial'
        if w.length != 2 || !ident?(w[1])
          errs << [no, 'bad initial']
        elsif !initial.nil?
          errs << [no, 'duplicate initial']
        else
          initial = w[1]
          refs << [no, w[1]]
        end
      elsif k == ON || (HAS_GUARDS && (k == 'enter' || k == 'exit'))
        if cur.nil?
          errs << [no, 'outside state']
          next
        end
        if k == 'enter' || k == 'exit'
          acts = parse_actions(w[1..].join(' '))
          if acts.nil?
            errs << [no, 'bad action']
          else
            states[cur][k.to_sym].concat(acts)
          end
          next
        end
        v = w[1..]
        guard = nil
        i = 1
        if v.length < 3 || !ident?(v[0])
          errs << [no, 'bad transition']
          next
        end
        if v[1] == 'if'
          if !HAS_GUARDS || v.length < 5 || !ident?(v[2]) || !OPS.include?(v[3]) || !integer?(v[4])
            errs << [no, 'bad transition']
            next
          end
          guard = [v[2], v[3], v[4].to_i]
          i = 5
        end
        if i >= v.length || v[i] != ARROW || i + 1 >= v.length || !ident?(v[i + 1])
          errs << [no, 'bad transition']
          next
        end
        target = v[i + 1]
        rest = v[(i + 2)..]
        acts = []
        unless rest.empty?
          if rest[0] != ACT
            errs << [no, 'bad transition']
            next
          end
          acts = parse_actions(rest[1..].join(' '))
          if acts.nil?
            errs << [no, 'bad action']
            next
          end
        end
        states[cur][:trans] << [v[0], guard, target, acts]
        refs << [no, target]
      else
        errs << [no, 'unknown directive']
      end
    end
    refs.each { |no, name| errs << [no, 'unknown state'] unless states.key?(name) }
    states.each do |name, s|
      seen = {}
      x = name
      while !x.nil? && states.key?(x) && !seen[x]
        seen[x] = true
        x = states[x][:parent]
      end
      errs << [s[:line], 'parent cycle'] if !x.nil? && seen[x]
    end
    unless errs.empty?
      e = errs.min
      return [nil, "error: line #{e[0]}: #{e[1]}"]
    end
    return [nil, 'error: no initial state'] if initial.nil?
    [[states, initial], nil]
  end

  def self.ancestors(states, name)
    out = []
    p = states[name][:parent]
    until p.nil?
      out << p
      p = states[p][:parent]
    end
    out
  end

  def self.machine(defn, events)
    parsed, err = parse(defn)
    return err if err
    states, initial = parsed
    counters = {}
    touched = {}
    emitted = []
    run = lambda do |acts|
      acts.each do |kind, name, val|
        if kind == 'emit'
          emitted << name
        elsif kind == 'set'
          counters[name] = val
          touched[name] = true
        else
          counters[name] = (counters[name] || 0) + val
          touched[name] = true
        end
      end
    end
    fmt = ->(text) { emitted.empty? ? text : "#{text} | #{emitted.join(' ')}" }
    out = []
    (ancestors(states, initial).reverse + [initial]).each { |s| run.call(states[s][:enter]) }
    out << fmt.call("start: -> #{initial}")
    state = initial
    events.split.each do |e|
      emitted = []
      fired = nil
      a = state
      while !a.nil? && fired.nil?
        states[a][:trans].each do |t|
          next if t[0] != e
          ok = true
          if t[1]
            v = counters[t[1][0]] || 0
            n = t[1][2]
            ok = case t[1][1]
                 when '<' then v < n
                 when '<=' then v <= n
                 when '>' then v > n
                 when '>=' then v >= n
                 when '==' then v == n
                 else v != n
                 end
          end
          if ok
            fired = t
            break
          end
        end
        a = states[a][:parent]
      end
      if fired.nil?
        out << "#{e}: ignored"
        next
      end
      target = fired[2]
      anc_t = ancestors(states, target)
      lca = ancestors(states, state).find { |x| anc_t.include?(x) }
      exits = []
      x = state
      while x != lca
        exits << x
        x = states[x][:parent]
      end
      enters = []
      x = target
      while x != lca
        enters << x
        x = states[x][:parent]
      end
      enters.reverse!
      exits.each { |s| run.call(states[s][:exit]) }
      run.call(fired[3])
      enters.each { |s| run.call(states[s][:enter]) }
      out << fmt.call("#{e}: #{state} -> #{target}")
      state = target
    end
    out << ('final ' + state + touched.keys.sort.map { |n| " #{n}=#{counters[n]}" }.join)
    out.join("\n")
  end
end
'''

JS = r'''
'use strict';

const ARROW = '@ARROW@';
const ON = '@ON@';
const STATE = '@STATE@';
const ACT = '@ACT@';
const HAS_GUARDS = @GUARDS@;
const HAS_HIER = @HIER@;
const LET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_';
const DIG = '0123456789';
const OPS = ['<', '<=', '>', '>=', '==', '!='];

const words = (s) => s.split(/[ \t\r\n\v\f]+/).filter((x) => x.length > 0);
const ident = (s) => s !== '' && LET.includes(s[0]) && [...s].every((c) => LET.includes(c) || DIG.includes(c));

function integer(s) {
  const body = s[0] === '-' ? s.slice(1) : s;
  return body !== '' && body.length <= 6 && [...body].every((c) => DIG.includes(c));
}

function parseActions(text) {
  if (words(text).length === 0) return null;
  const acts = [];
  for (const piece of text.split(',')) {
    const w = words(piece);
    if (w.length === 0) return null;
    const v = w[0];
    if (v === 'emit' && w.length === 2 && ident(w[1])) acts.push(['emit', w[1], 0]);
    else if (v === 'set' && w.length === 3 && ident(w[1]) && integer(w[2])) acts.push(['set', w[1], parseInt(w[2], 10)]);
    else if ((v === 'inc' || v === 'dec') && (w.length === 2 || w.length === 3) && ident(w[1]) && (w.length === 2 || integer(w[2]))) {
      const amt = w.length === 3 ? parseInt(w[2], 10) : 1;
      acts.push(['add', w[1], v === 'inc' ? amt : -amt]);
    } else return null;
  }
  return acts;
}

function minErr(errs) {
  return errs.reduce((a, b) => (b[0] < a[0] ? b : a));
}

function parse(defn) {
  const states = new Map();
  const errs = [];
  const refs = [];
  let initial = null;
  let cur = null;
  const lines = defn.split('\n');
  for (let idx = 0; idx < lines.length; idx++) {
    const no = idx + 1;
    const w = words(lines[idx].split('#')[0]);
    if (w.length === 0) continue;
    const k = w[0];
    if (k === STATE) {
      const ok = w.length === 2 || (HAS_HIER && w.length === 4 && w[2] === '<');
      if (!ok || !ident(w[1]) || (w.length === 4 && !ident(w[3]))) errs.push([no, 'bad state']);
      else if (states.has(w[1])) errs.push([no, 'duplicate state']);
      else {
        const parent = w.length === 4 ? w[3] : null;
        states.set(w[1], { line: no, parent, trans: [], enter: [], exit: [] });
        if (parent) refs.push([no, parent]);
        cur = w[1];
      }
    } else if (k === 'initial') {
      if (w.length !== 2 || !ident(w[1])) errs.push([no, 'bad initial']);
      else if (initial !== null) errs.push([no, 'duplicate initial']);
      else { initial = w[1]; refs.push([no, w[1]]); }
    } else if (k === ON || (HAS_GUARDS && (k === 'enter' || k === 'exit'))) {
      if (cur === null) { errs.push([no, 'outside state']); continue; }
      if (k === 'enter' || k === 'exit') {
        const acts = parseActions(w.slice(1).join(' '));
        if (acts === null) errs.push([no, 'bad action']);
        else states.get(cur)[k].push(...acts);
        continue;
      }
      const v = w.slice(1);
      let guard = null;
      let i = 1;
      if (v.length < 3 || !ident(v[0])) { errs.push([no, 'bad transition']); continue; }
      if (v[1] === 'if') {
        if (!HAS_GUARDS || v.length < 5 || !ident(v[2]) || !OPS.includes(v[3]) || !integer(v[4])) { errs.push([no, 'bad transition']); continue; }
        guard = [v[2], v[3], parseInt(v[4], 10)];
        i = 5;
      }
      if (i >= v.length || v[i] !== ARROW || i + 1 >= v.length || !ident(v[i + 1])) { errs.push([no, 'bad transition']); continue; }
      const target = v[i + 1];
      const rest = v.slice(i + 2);
      let acts = [];
      if (rest.length > 0) {
        if (rest[0] !== ACT) { errs.push([no, 'bad transition']); continue; }
        acts = parseActions(rest.slice(1).join(' '));
        if (acts === null) { errs.push([no, 'bad action']); continue; }
      }
      states.get(cur).trans.push([v[0], guard, target, acts]);
      refs.push([no, target]);
    } else errs.push([no, 'unknown directive']);
  }
  for (const [no, name] of refs) if (!states.has(name)) errs.push([no, 'unknown state']);
  for (const [name, s] of states) {
    const seen = new Set();
    let x = name;
    while (x !== null && states.has(x) && !seen.has(x)) { seen.add(x); x = states.get(x).parent; }
    if (x !== null && seen.has(x)) errs.push([s.line, 'parent cycle']);
  }
  if (errs.length > 0) {
    const e = minErr(errs);
    return [null, `error: line ${e[0]}: ${e[1]}`];
  }
  if (initial === null) return [null, 'error: no initial state'];
  return [{ states, initial }, null];
}

function ancestors(states, name) {
  const out = [];
  let p = states.get(name).parent;
  while (p !== null) { out.push(p); p = states.get(p).parent; }
  return out;
}

function machine(defn, events) {
  const [parsed, err] = parse(defn);
  if (err) return err;
  const { states, initial } = parsed;
  const counters = new Map();
  const touched = new Set();
  let emitted = [];
  const run = (acts) => {
    for (const [kind, name, val] of acts) {
      if (kind === 'emit') emitted.push(name);
      else if (kind === 'set') { counters.set(name, val); touched.add(name); }
      else { counters.set(name, (counters.get(name) || 0) + val); touched.add(name); }
    }
  };
  const fmt = (text) => (emitted.length > 0 ? `${text} | ${emitted.join(' ')}` : text);
  const out = [];
  for (const s of [...ancestors(states, initial).reverse(), initial]) run(states.get(s).enter);
  out.push(fmt(`start: -> ${initial}`));
  let state = initial;
  for (const e of words(events)) {
    emitted = [];
    let fired = null;
    let a = state;
    while (a !== null && fired === null) {
      for (const t of states.get(a).trans) {
        if (t[0] !== e) continue;
        let ok = true;
        if (t[1]) {
          const v = counters.get(t[1][0]) || 0;
          const n = t[1][2];
          switch (t[1][1]) {
            case '<': ok = v < n; break;
            case '<=': ok = v <= n; break;
            case '>': ok = v > n; break;
            case '>=': ok = v >= n; break;
            case '==': ok = v === n; break;
            default: ok = v !== n;
          }
        }
        if (ok) { fired = t; break; }
      }
      a = states.get(a).parent;
    }
    if (fired === null) { out.push(`${e}: ignored`); continue; }
    const target = fired[2];
    const ancT = ancestors(states, target);
    let lca = null;
    for (const x of ancestors(states, state)) if (ancT.includes(x)) { lca = x; break; }
    const exits = [];
    let x = state;
    while (x !== lca) { exits.push(x); x = states.get(x).parent; }
    const enters = [];
    x = target;
    while (x !== lca) { enters.push(x); x = states.get(x).parent; }
    enters.reverse();
    for (const s of exits) run(states.get(s).exit);
    run(fired[3]);
    for (const s of enters) run(states.get(s).enter);
    out.push(fmt(`${e}: ${state} -> ${target}`));
    state = target;
  }
  const names = [...touched].sort((p, q) => (p < q ? -1 : p > q ? 1 : 0));
  out.push('final ' + state + names.map((n) => ` ${n}=${counters.get(n)}`).join(''));
  return out.join('\n');
}

module.exports = { machine };
'''

JV = r'''
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class Statemachine {
    static final String ARROW = "@ARROW@";
    static final String ON = "@ON@";
    static final String STATE = "@STATE@";
    static final String ACT = "@ACT@";
    static final boolean HAS_GUARDS = @GUARDS@;
    static final boolean HAS_HIER = @HIER@;
    static final String LET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_";
    static final String DIG = "0123456789";
    static final List<String> OPS = Arrays.asList("<", "<=", ">", ">=", "==", "!=");

    static List<String> words(String s) {
        List<String> out = new ArrayList<>();
        for (String w : s.split("[ \t\r\n\u000B\f]+")) if (!w.isEmpty()) out.add(w);
        return out;
    }

    static boolean ident(String s) {
        if (s.isEmpty() || LET.indexOf(s.charAt(0)) < 0) return false;
        for (char c : s.toCharArray()) if (LET.indexOf(c) < 0 && DIG.indexOf(c) < 0) return false;
        return true;
    }

    static boolean integer(String s) {
        String body = s.startsWith("-") ? s.substring(1) : s;
        if (body.isEmpty() || body.length() > 6) return false;
        for (char c : body.toCharArray()) if (DIG.indexOf(c) < 0) return false;
        return true;
    }

    static class Act {
        String kind, name;
        int val;
        Act(String kind, String name, int val) { this.kind = kind; this.name = name; this.val = val; }
    }

    static class Trans {
        String event, target;
        String gvar, gop;
        int gnum;
        boolean guarded;
        List<Act> acts;
    }

    static class St {
        int line;
        String parent;
        List<Trans> trans = new ArrayList<>();
        List<Act> enter = new ArrayList<>();
        List<Act> exit = new ArrayList<>();
    }

    static List<Act> parseActions(String text) {
        if (words(text).isEmpty()) return null;
        List<Act> acts = new ArrayList<>();
        for (String piece : text.split(",", -1)) {
            List<String> w = words(piece);
            if (w.isEmpty()) return null;
            String v = w.get(0);
            if (v.equals("emit") && w.size() == 2 && ident(w.get(1))) acts.add(new Act("emit", w.get(1), 0));
            else if (v.equals("set") && w.size() == 3 && ident(w.get(1)) && integer(w.get(2))) acts.add(new Act("set", w.get(1), Integer.parseInt(w.get(2))));
            else if ((v.equals("inc") || v.equals("dec")) && (w.size() == 2 || w.size() == 3) && ident(w.get(1)) && (w.size() == 2 || integer(w.get(2)))) {
                int amt = w.size() == 3 ? Integer.parseInt(w.get(2)) : 1;
                acts.add(new Act("add", w.get(1), v.equals("inc") ? amt : -amt));
            } else return null;
        }
        return acts;
    }

    static Map<String, St> states;
    static String initial;
    static String error;

    static void parse(String defn) {
        states = new LinkedHashMap<>();
        initial = null;
        error = null;
        int errLine = Integer.MAX_VALUE;
        String errMsg = null;
        List<Object[]> refs = new ArrayList<>();
        String cur = null;
        String[] lines = defn.split("\n", -1);
        for (int idx = 0; idx < lines.length; idx++) {
            int no = idx + 1;
            String raw = lines[idx];
            int h = raw.indexOf('#');
            if (h >= 0) raw = raw.substring(0, h);
            List<String> w = words(raw);
            if (w.isEmpty()) continue;
            String k = w.get(0);
            String bad = null;
            if (k.equals(STATE)) {
                boolean ok = w.size() == 2 || (HAS_HIER && w.size() == 4 && w.get(2).equals("<"));
                if (!ok || !ident(w.get(1)) || (w.size() == 4 && !ident(w.get(3)))) bad = "bad state";
                else if (states.containsKey(w.get(1))) bad = "duplicate state";
                else {
                    St s = new St();
                    s.line = no;
                    s.parent = w.size() == 4 ? w.get(3) : null;
                    states.put(w.get(1), s);
                    if (s.parent != null) refs.add(new Object[] { no, s.parent });
                    cur = w.get(1);
                }
            } else if (k.equals("initial")) {
                if (w.size() != 2 || !ident(w.get(1))) bad = "bad initial";
                else if (initial != null) bad = "duplicate initial";
                else { initial = w.get(1); refs.add(new Object[] { no, initial }); }
            } else if (k.equals(ON) || (HAS_GUARDS && (k.equals("enter") || k.equals("exit")))) {
                if (cur == null) bad = "outside state";
                else if (k.equals("enter") || k.equals("exit")) {
                    List<Act> acts = parseActions(String.join(" ", w.subList(1, w.size())));
                    if (acts == null) bad = "bad action";
                    else (k.equals("enter") ? states.get(cur).enter : states.get(cur).exit).addAll(acts);
                } else {
                    List<String> v = w.subList(1, w.size());
                    Trans t = new Trans();
                    int i = 1;
                    if (v.size() < 3 || !ident(v.get(0))) bad = "bad transition";
                    else {
                        if (v.get(1).equals("if")) {
                            if (!HAS_GUARDS || v.size() < 5 || !ident(v.get(2)) || !OPS.contains(v.get(3)) || !integer(v.get(4))) bad = "bad transition";
                            else { t.guarded = true; t.gvar = v.get(2); t.gop = v.get(3); t.gnum = Integer.parseInt(v.get(4)); i = 5; }
                        }
                        if (bad == null && (i >= v.size() || !v.get(i).equals(ARROW) || i + 1 >= v.size() || !ident(v.get(i + 1)))) bad = "bad transition";
                        if (bad == null) {
                            t.event = v.get(0);
                            t.target = v.get(i + 1);
                            List<String> rest = v.subList(i + 2, v.size());
                            t.acts = new ArrayList<>();
                            if (!rest.isEmpty()) {
                                if (!rest.get(0).equals(ACT)) bad = "bad transition";
                                else {
                                    List<Act> acts = parseActions(String.join(" ", rest.subList(1, rest.size())));
                                    if (acts == null) bad = "bad action"; else t.acts = acts;
                                }
                            }
                            if (bad == null) { states.get(cur).trans.add(t); refs.add(new Object[] { no, t.target }); }
                        }
                    }
                }
            } else bad = "unknown directive";
            if (bad != null && no < errLine) { errLine = no; errMsg = bad; }
        }
        for (Object[] r : refs) if (!states.containsKey((String) r[1]) && (Integer) r[0] < errLine) { errLine = (Integer) r[0]; errMsg = "unknown state"; }
        for (Map.Entry<String, St> en : states.entrySet()) {
            Set<String> seen = new HashSet<>();
            String x = en.getKey();
            while (x != null && states.containsKey(x) && !seen.contains(x)) { seen.add(x); x = states.get(x).parent; }
            if (x != null && seen.contains(x) && en.getValue().line < errLine) { errLine = en.getValue().line; errMsg = "parent cycle"; }
        }
        if (errMsg != null) error = "error: line " + errLine + ": " + errMsg;
        else if (initial == null) error = "error: no initial state";
    }

    static List<String> ancestors(String name) {
        List<String> out = new ArrayList<>();
        String p = states.get(name).parent;
        while (p != null) { out.add(p); p = states.get(p).parent; }
        return out;
    }

    static Map<String, Integer> counters;
    static Set<String> touched;
    static List<String> emitted;

    static void run(List<Act> acts) {
        for (Act a : acts) {
            if (a.kind.equals("emit")) emitted.add(a.name);
            else if (a.kind.equals("set")) { counters.put(a.name, a.val); touched.add(a.name); }
            else { counters.put(a.name, counters.getOrDefault(a.name, 0) + a.val); touched.add(a.name); }
        }
    }

    static String fmt(String text) {
        return emitted.isEmpty() ? text : text + " | " + String.join(" ", emitted);
    }

    public static String machine(String defn, String events) {
        parse(defn);
        if (error != null) return error;
        counters = new HashMap<>();
        touched = new TreeSet<>();
        emitted = new ArrayList<>();
        List<String> out = new ArrayList<>();
        List<String> chain = ancestors(initial);
        Collections.reverse(chain);
        chain.add(initial);
        for (String s : chain) run(states.get(s).enter);
        out.add(fmt("start: -> " + initial));
        String state = initial;
        for (String e : words(events)) {
            emitted = new ArrayList<>();
            Trans fired = null;
            String a = state;
            while (a != null && fired == null) {
                for (Trans t : states.get(a).trans) {
                    if (!t.event.equals(e)) continue;
                    boolean ok = true;
                    if (t.guarded) {
                        int v = counters.getOrDefault(t.gvar, 0);
                        switch (t.gop) {
                            case "<": ok = v < t.gnum; break;
                            case "<=": ok = v <= t.gnum; break;
                            case ">": ok = v > t.gnum; break;
                            case ">=": ok = v >= t.gnum; break;
                            case "==": ok = v == t.gnum; break;
                            default: ok = v != t.gnum;
                        }
                    }
                    if (ok) { fired = t; break; }
                }
                a = states.get(a).parent;
            }
            if (fired == null) { out.add(e + ": ignored"); continue; }
            String target = fired.target;
            List<String> ancT = ancestors(target);
            String lca = null;
            for (String x : ancestors(state)) if (ancT.contains(x)) { lca = x; break; }
            List<String> exits = new ArrayList<>();
            String x = state;
            while (x != null ? !x.equals(lca) : lca != null) { exits.add(x); x = states.get(x).parent; }
            List<String> enters = new ArrayList<>();
            x = target;
            while (x != null ? !x.equals(lca) : lca != null) { enters.add(x); x = states.get(x).parent; }
            Collections.reverse(enters);
            for (String s : exits) run(states.get(s).exit);
            run(fired.acts);
            for (String s : enters) run(states.get(s).enter);
            out.add(fmt(e + ": " + state + " -> " + target));
            state = target;
        }
        StringBuilder fin = new StringBuilder("final " + state);
        for (String n : touched) fin.append(" ").append(n).append("=").append(counters.get(n));
        out.add(fin.toString());
        return String.join("\n", out);
    }
}
'''

SOURCES = {"python": PY, "ruby": RB, "javascript": JS, "java": JV}


def _b(lang, v):
    if lang == "python":
        return "True" if v else "False"
    return "true" if v else "false"


def sol(lang, p):
    return K.subst(SOURCES[lang], ARROW=p["arrow"], ON=p["on"], STATE=p["state"], ACT=p["act"], GUARDS=_b(lang, p["guards"]), HIER=_b(lang, p["hier"])).lstrip("\n")


# ---------------------------------------------------------------------------------------------------------------

def readme(p, api, lang, examples):
    name, _, _ = p["machine"]
    A, ON, ST, ACT = p["arrow"], p["on"], p["state"], p["act"]
    L = [f"# Machine runner for {name}", ""]
    L.append(f"The firmware team describes {name} in a small text language and wants to *replay* event logs against it. `machine(definition, events)` parses the definition, "
             "starts the machine, feeds it the events and returns a trace. This document is the whole language.")
    L.append("")
    L.append("## Definition language")
    L.append("")
    L.append("The definition is text with one directive per line (lines are separated by `\\n`; line numbers count from 1). On every line everything from a `#` on is a comment. "
             "The rest is split into *words* at blanks (spaces and tabs); a line without words is ignored. The first word chooses the directive. "
             "A **name** (state, event or counter) is an *identifier*: a letter or `_`, followed by letters, digits or `_` (ASCII only, case-sensitive).")
    L.append("")
    sd = f"`{ST} NAME`" + (f" or `{ST} NAME < PARENT`" if p["hier"] else "")
    L.append(f"* {sd}: declares a state and makes it the *current declaration*; the directives below belong to it until the next `{ST}` line. States may be declared in any order."
             + (" `< PARENT` makes `PARENT` its parent state (see Hierarchy)." if p["hier"] else ""))
    L.append("* `initial NAME`: the state the machine starts in (exactly one such line).")
    guard = " [if VAR OP NUMBER]" if p["guards"] else ""
    L.append(f"* `{ON} EVENT{guard} {A} TARGET [{ACT} ACTIONS]`: a transition of the current declaration: when `EVENT` arrives" +
             (" and the guard holds" if p["guards"] else "") + f", the machine moves to `TARGET`, running the actions.")
    if p["guards"]:
        L.append("* `enter ACTIONS` and `exit ACTIONS`: actions run when the machine enters or leaves the current declaration (several lines of the same kind accumulate, in order).")
    L.append("")
    L.append("**Actions** are separated by commas (a comma never occurs inside an action); each one is, with `VAR` a name and `N` an integer written as optional `-` and one to six ASCII digits:")
    L.append("")
    L.append("* `emit NAME`: add `NAME` to the output of the current step;")
    L.append("* `set VAR N`: set the counter `VAR` to `N`;")
    L.append("* `inc VAR [N]` / `dec VAR [N]`: add or subtract `N` (default 1) to the counter. Counters that were never set are 0.")
    L.append("")
    if p["guards"]:
        L.append("A **guard** compares a counter with a constant: `OP` is one of `<`, `<=`, `>`, `>=`, `==`, `!=`, and `NUMBER` an integer as above. A guard is true when the counter's current value satisfies the comparison.")
        L.append("")
    L.append("`" + A + "`, `" + ACT + "`" + (", `if`" if p["guards"] else "") + (", `<`" if p["hier"] else "") + (" and the comparison operators" if p["guards"] else "") + " are words of their own: they must be separated from their neighbours by blanks.")
    L.append("")
    L.append("## Errors in the definition")
    L.append("")
    L.append("Every line is checked on its own; if any line has a problem the result of `machine` is just `error: line N: REASON` for the problem on the **lowest line number** (nothing runs). "
             "A line has at most one problem. The reasons:")
    L.append("")
    L.append("| reason | when |")
    L.append("|---|---|")
    L.append("| `unknown directive` | the first word is not a directive of this language" + (" (`enter` and `exit` do not exist here)" if not p["guards"] else "") + " |")
    L.append(f"| `bad state` | a `{ST}` line with the wrong shape or an invalid name |")
    L.append("| `duplicate state` | a second declaration of an already declared state |")
    L.append("| `bad initial` | an `initial` line with the wrong shape or an invalid name |")
    L.append("| `duplicate initial` | a second valid `initial` line |")
    L.append(f"| `outside state` | a `{ON}`" + (", `enter` or `exit`" if p["guards"] else "") + f" line before the first valid `{ST}` line |")
    L.append("| `bad transition` | a transition line that does not have the shape above (missing words, invalid names, wrong arrow or action separator word, bad guard" + (", or a guard where guards do not exist" if not p["guards"] else "") + f") |")
    L.append("| `bad action` | an action list that is empty (also `" + ACT + "` followed by nothing) or has an empty or malformed action, in a transition" + (" or in an `enter`/`exit` line" if p["guards"] else "") + " |")
    L.append("| `unknown state` | a reference (`initial`, a transition target" + (" or a parent" if p["hier"] else "") + ") to a state that is declared nowhere in the definition; reported on the line of the reference |")
    if p["hier"]:
        L.append("| `parent cycle` | the state's chain of parents comes back to a state already visited (a state that is its own parent, or two states that are each other's ancestors); reported on the declaration line of each state of the cycle |")
    L.append("")
    L.append("For a transition line, shape problems (`bad transition`) are judged first and the action list (`bad action`) afterwards. A line that causes `bad state`, `duplicate state`, `bad transition` or `bad action` is ignored otherwise "
             "(it declares nothing). If there are no line problems but no `initial` line at all, the result is `error: no initial state`.")
    L.append("")
    L.append("## Running")
    L.append("")
    L.append("`events` is text split into events at blanks (spaces, tabs, newlines); any word is an event name (no validation). The machine starts by *entering* the initial state" +
             (" (the `enter` actions of its ancestors, outermost first, then its own)" if p["hier"] else (" (its `enter` actions)" if p["guards"] else "")) +
             ", then handles each event in turn:")
    L.append("")
    L.append("1. The transitions of the current state are examined in declaration order; the **first** one with the right event whose guard (if any) is true fires." +
             (" If none of them fires, the transitions of its parent are examined the same way, then those of its grandparent, and so on." if p["hier"] else "") +
             " If no transition fires at all, the event is *ignored* (nothing changes).")
    L.append("2. A transition that fires moves the machine from the current state `S` to `TARGET`" + (" (the transition may be declared in an ancestor of `S`, but the machine always leaves from `S`)" if p["hier"] else "") + ". "
             "Guards use the counter values from *before* the step.")
    if p["guards"]:
        if p["hier"]:
            L.append("3. **Exits and enters.** Let `L` be the lowest state that is a *proper* ancestor of both `S` and `TARGET` (there may be none). The machine leaves `S`, then its parent, and so on **up to but not including** `L`, running each state's `exit` actions in that order "
                     "(innermost first). Then the transition's own actions run. Then it enters the states on the path from just below `L` down to `TARGET` (outermost first), running their `enter` actions. "
                     "So a transition to the current state leaves and re-enters it, and a transition to an ancestor leaves the state and re-enters the ancestor.")
        else:
            L.append("3. Running order: the `exit` actions of `S`, then the actions of the transition, then the `enter` actions of `TARGET`. A transition to the current state leaves and re-enters it.")
    else:
        L.append("3. The transition's actions run. A transition to the current state is allowed.")
    L.append("")
    L.append("## Trace")
    L.append("")
    L.append("The result is lines joined by `\\n` (no trailing newline):")
    L.append("")
    L.append("* first `start: -> INITIAL`;")
    L.append("* then one line per event, `EVENT: S -> TARGET` when a transition fired and `EVENT: ignored` otherwise;")
    L.append("* a line that ran any `emit` actions (during entering at the start, or during the step) ends with ` | ` and the emitted names separated by single spaces, in the order they were emitted;")
    L.append("* last `final STATE` followed, for every counter that was ever the subject of `set`, `inc` or `dec` (even if its value is 0 again), by ` NAME=VALUE`, sorted by name in ascending byte order.")
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    for (d, ev), out in examples:
        L.append("Definition:")
        L.append("")
        L.append(K.fence(d))
        L.append(f"Events: `{ev}`")
        L.append("")
        L.append("Result:")
        L.append("")
        L.append(K.fence(out))
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


def make_cases(rng, p, ns):
    mname, sts, evs = p["machine"]
    A, ON, ST, ACT = p["arrow"], p["on"], p["state"], p["act"]
    guards, hier = p["guards"], p["hier"]
    cases = []

    def add(defn, events):
        cases.append((defn, events))

    def mk_actions(k=None, with_counters=True):
        k = rng.randrange(0, 3) if k is None else k
        acts = []
        for _ in range(k):
            r = rng.random()
            if r < 0.6 or not guards or not with_counters:
                acts.append(f"emit {rng.choice(EMITS)}")
            elif r < 0.75:
                acts.append(f"set {rng.choice(VARS[:4])} {rng.randrange(-3, 6)}")
            else:
                acts.append(f"{rng.choice(['inc', 'dec'])} {rng.choice(VARS[:4])}" + (f" {rng.randrange(1, 4)}" if rng.random() < 0.4 else ""))
        return acts

    def machine_text(nstates=None, trans_each=None):
        n = nstates or rng.randrange(3, 6)
        names = rng.sample(sts, n)
        lines = []
        if rng.random() < 0.5:
            lines.append(f"initial {names[0]}")
        for i, s in enumerate(names):
            parent = ""
            if hier and i > 0 and rng.random() < 0.5:
                parent = f" < {rng.choice(names[:i])}"
            lines.append(f"{ST} {s}{parent}")
            if guards and rng.random() < 0.4:
                lines.append(f"  enter {', '.join(mk_actions(rng.randrange(1, 3)))}")
            if guards and rng.random() < 0.4:
                lines.append(f"  exit {', '.join(mk_actions(rng.randrange(1, 3)))}")
            for _ in range(trans_each or rng.randrange(1, 4)):
                ev = rng.choice(evs[:5])
                tgt = rng.choice(names)
                g = ""
                if guards and rng.random() < 0.4:
                    g = f" if {rng.choice(VARS[:4])} {rng.choice(['<', '<=', '>', '>=', '==', '!='])} {rng.randrange(-2, 5)}"
                acts = mk_actions()
                tail = f" {ACT} {', '.join(acts)}" if acts else ""
                lines.append(f"  {ON} {ev}{g} {A} {tgt}{tail}")
        if not any(ln.startswith("initial") for ln in lines):
            lines.insert(rng.randrange(0, len(lines) + 1), f"initial {names[0]}")
        return "\n".join(lines) + "\n", names

    def events(n=None):
        return " ".join(rng.choice(evs[:6]) for _ in range(n or rng.randrange(3, 10)))

    # examples
    d1 = f"initial {sts[0]}\n{ST} {sts[0]}\n  {ON} {evs[0]} {A} {sts[1]} {ACT} emit {EMITS[0]}\n{ST} {sts[1]}\n  {ON} {evs[1]} {A} {sts[0]}\n"
    add(d1, f"{evs[0]} {evs[2]} {evs[1]}")
    d, _ = machine_text(3)
    add(d, events(6))
    d, _ = machine_text(4)
    add(d, events(7))
    nex = len(cases)
    for _ in range(14):
        d, _ = machine_text()
        add(d, events())
    for _ in range(4):
        d, _ = machine_text(rng.randrange(4, 6), 3)
        add(d, events(rng.randrange(10, 16)))
    s0, s1, s2 = sts[0], sts[1], sts[2]
    e0, e1, e2 = evs[0], evs[1], evs[2]
    # basics
    add(f"initial {s0}\n{ST} {s0}\n", "")
    add(f"initial {s0}\n{ST} {s0}\n", e0)
    add(f"initial {s0}\n{ST} {s0}\n  {ON} {e0} {A} {s0}\n", f"{e0} {e0}")
    add(f"{ST} {s0}\ninitial {s0}\n  {ON} {e0} {A} {s0} {ACT} emit a, emit b\n", f"{e0}\n{e0}\t{e1}")
    add(f"# comment\n\n  initial   {s0}   # trailing\n{ST}\t{s0}\n   {ON}  {e0}   {A}  {s1}  \n{ST} {s1}\n", f"  {e0}  ")
    add(f"initial {s0}\n{ST} {s0}\n  {ON} {e0} {A} {s1}\n  {ON} {e0} {A} {s2}\n{ST} {s1}\n{ST} {s2}\n", e0)
    add(f"initial {s0}\n{ST} {s0}\n  {ON} {e0} {A} {s1} {ACT} emit x\n  {ON} {e0} {A} {s2} {ACT} emit y\n{ST} {s1}\n{ST} {s2}\n", f"{e0} {e0}")
    add(f"{ST} {s1}\n  {ON} {e0} {A} {s0}\n{ST} {s0}\n  {ON} {e0} {A} {s1}\ninitial {s0}\n", f"{e0} {e0} {e0}")
    add(f"initial {s0}\n{ST} {s0}\n  {ON} {e0} {A} {s1} {ACT} emit one, emit two,emit three\n{ST} {s1}\n", e0)
    add(f"initial {s0}\n{ST} {s0}\n  {ON} {e0} {A} {s1} {ACT} emit  one ,  emit   two\n{ST} {s1}\n", e0)
    # errors
    errs = [
        f"initial {s0}\n{ST} {s0}\n  frob {e0}\n",
        f"initial {s0}\n  {ON} {e0} {A} {s0}\n{ST} {s0}\n",
        f"initial {s0}\n{ST} {s0}\n{ST} {s0}\n",
        f"initial {s0}\ninitial {s1}\n{ST} {s0}\n{ST} {s1}\n",
        f"initial\n{ST} {s0}\n",
        f"initial {s0} {s1}\n{ST} {s0}\n",
        f"initial 9x\n{ST} {s0}\n",
        f"{ST} {s0}\n",
        "",
        "# only a comment\n",
        f"{ST}\n",
        f"{ST} {s0} {s1}\n",
        f"{ST} 1bad\n",
        f"{ST} {s0}\n  {ON}\n",
        f"{ST} {s0}\n  {ON} {e0}\n",
        f"{ST} {s0}\n  {ON} {e0} {A}\n",
        f"{ST} {s0}\n  {ON} {e0} {s0}\n",
        f"{ST} {s0}\n  {ON} {e0} {A} {s0} {s1}\n",
        f"{ST} {s0}\n  {ON} {e0} {A} {s0} {ACT}\n",
        f"{ST} {s0}\n  {ON} {e0} {A} {s0} {ACT} \n",
        f"{ST} {s0}\n  {ON} {e0} {A} {s0} {ACT} emit\n",
        f"{ST} {s0}\n  {ON} {e0} {A} {s0} {ACT} emit a b\n",
        f"{ST} {s0}\n  {ON} {e0} {A} {s0} {ACT} emit a,\n",
        f"{ST} {s0}\n  {ON} {e0} {A} {s0} {ACT} ,emit a\n",
        f"{ST} {s0}\n  {ON} {e0} {A} {s0} {ACT} emit a,,emit b\n",
        f"{ST} {s0}\n  {ON} {e0} {A} {s0} {ACT} emit 1a\n",
        f"{ST} {s0}\n  {ON} {e0} {A} {s0} {ACT} frob a\n",
        f"{ST} {s0}\n  {ON} {e0} {A}\t{s0}\tx emit a\n",
        f"{ST} {s0}\n  {ON} {e0}{A}{s0}\n",
        f"{ST} {s0}\n  {ON} {e0} {A}{s0}\n",
        f"{ST} {s0}\n  {ON} 1x {A} {s0}\n",
        f"{ST} {s0}\n  {ON} {e0} {A} 1x\n",
        f"{ST} {s0}\n  {ON} {e0} {A} {s0} {ACT} emit a\n  {ON} {e1} {A} nowhere\ninitial {s0}\n",
        f"initial nowhere\n{ST} {s0}\n",
        f"initial {s0}\n{ST} {s0}\n  {ON} {e0} {A} {s1}\n{ST} {s1}\n  {ON} {e0} {A} {s2}\n",
        f"initial {s0}\n{ST} {s0}\n  {ON} {e0} {A} nowhere\n  frob\n",
        f"initial {s0}\n  frob\n{ST} {s0}\n  {ON} {e0} {A} nowhere\n",
        f"{ST} {s0}\n  bogus\n  {ON} {e0} {A}\n",
        f"{ST} {s0}\ninitial {s0}\n  {ON} {e0} {A} {s0} {ACT} emit a\n  {ON} {e1} {A} {s0} {ACT} emit\n  {ON} {e2}\n",
        f"{ST} {s0}\n{ST} {s0}\n{ST} 1bad\n{ST}\n",
        f"{ST} {s0}\ninitial {s0}\n  {ON} {e0} {A} {s0} {ACT} emit a # comment\n",
        f"{ST} {s0}\ninitial {s0}\n#  {ON} {e0} {A} nowhere\n",
        f"{ST.upper()} {s0}\ninitial {s0}\n",
        f"{ST} {s0}\nINITIAL {s0}\n",
        f"{ST} {s0}\ninitial {s0}\n  {ON.upper()} {e0} {A} {s0}\n",
        f"{ST} {s0}\ninitial {s0}\n  {ON} {e0} -> {s0}\n" if A != "->" else f"{ST} {s0}\ninitial {s0}\n  {ON} {e0} => {s0}\n",
        f"{ST} {s0}\ninitial {s0}\n  {ON} {e0} {A} {s0} / emit a\n" if ACT != "/" else f"{ST} {s0}\ninitial {s0}\n  {ON} {e0} {A} {s0} ! emit a\n",
    ]
    for e in errs:
        add(e, f"{e0} {e1}")
    if guards:
        c = rng.choice(VARS[:4])
        add(f"initial {s0}\n{ST} {s0}\n  enter set {c} 3\n  exit inc {c}\n  {ON} {e0} if {c} > 3 {A} {s1} {ACT} emit big\n  {ON} {e0} if {c} <= 3 {A} {s0} {ACT} emit small\n{ST} {s1}\n", f"{e0} {e0} {e0}")
        for op in ["<", "<=", ">", ">=", "==", "!="]:
            for val in (-1, 0, 2):
                add(f"initial {s0}\n{ST} {s0}\n  enter set {c} {val}\n  {ON} {e0} if {c} {op} 0 {A} {s1} {ACT} emit yes\n  {ON} {e0} {A} {s2} {ACT} emit no\n{ST} {s1}\n{ST} {s2}\n", e0)
        add(f"initial {s0}\n{ST} {s0}\n  {ON} {e0} if {c} == 0 {A} {s0} {ACT} inc {c}, emit tick\n  {ON} {e0} if {c} < 3 {A} {s0} {ACT} inc {c} 2, emit tock\n  {ON} {e0} {A} {s1}\n{ST} {s1}\n", " ".join([e0] * 6))
        add(f"initial {s0}\n{ST} {s0}\n  {ON} {e0} {A} {s1} {ACT} inc a, inc b 5, dec c 2, set d -4, dec b\n{ST} {s1}\n  {ON} {e0} {A} {s0} {ACT} set a 0\n", f"{e0} {e0}")
        add(f"initial {s0}\n{ST} {s0}\n  enter emit in0\n  exit emit out0\n  {ON} {e0} {A} {s0} {ACT} emit mid\n  {ON} {e1} {A} {s1} {ACT} emit go\n{ST} {s1}\n  enter emit in1, set z 7\n  exit emit out1\n  {ON} {e0} {A} {s0}\n", f"{e0} {e1} {e0} {e2} {e1}")
        add(f"initial {s0}\n{ST} {s0}\n  enter emit a\n  enter emit b, emit c\n  exit emit d\n  exit emit e\n  {ON} {e0} {A} {s0}\n", f"{e0}")
        add(f"initial {s0}\n{ST} {s0}\n  {ON} {e0} if x == 0 {A} {s0} {ACT} set x 1\n  {ON} {e0} if x == 1 {A} {s0} {ACT} set x 2\n", f"{e0} {e0} {e0}")
        bad_g = [f"{ON} {e0} if {A} {s0}", f"{ON} {e0} if x {A} {s0}", f"{ON} {e0} if x < {A} {s0}", f"{ON} {e0} if x < 1.5 {A} {s0}", f"{ON} {e0} if x = 1 {A} {s0}",
                 f"{ON} {e0} if x <> 1 {A} {s0}", f"{ON} {e0} if 1 < x {A} {s0}", f"{ON} {e0} if x < 1234567 {A} {s0}", f"{ON} {e0} if x< 1 {A} {s0}", f"{ON} {e0} if x < +1 {A} {s0}",
                 f"{ON} {e0} IF x < 1 {A} {s0}", f"{ON} {e0} if x < -1 {A} {s0}", f"{ON} {e0} if x < 1 {A} {s0} {ACT} emit a", f"{ON} if x < 1 {A} {s0}", f"{ON} {e0} if x < 1 {s0}"]
        for g in bad_g:
            add(f"initial {s0}\n{ST} {s0}\n  {g}\n", f"{e0}")
        for a in ["enter", "exit"]:
            add(f"initial {s0}\n{ST} {s0}\n  {a}\n", e0)
            add(f"initial {s0}\n{ST} {s0}\n  {a} emit\n", e0)
            add(f"initial {s0}\n{a} emit a\n{ST} {s0}\n", e0)
            add(f"initial {s0}\n{ST} {s0}\n  {a} set x\n", e0)
            add(f"initial {s0}\n{ST} {s0}\n  {a} set x 1 2\n", e0)
            add(f"initial {s0}\n{ST} {s0}\n  {a} set x 1234567\n", e0)
            add(f"initial {s0}\n{ST} {s0}\n  {a} inc x y\n", e0)
            add(f"initial {s0}\n{ST} {s0}\n  {a} dec x 1 2\n", e0)
            add(f"initial {s0}\n{ST} {s0}\n  {a} inc\n", e0)
            add(f"initial {s0}\n{ST} {s0}\n  {a} set x -0\n  {ON} {e0} {A} {s0}\n", e0)
    else:
        add(f"initial {s0}\n{ST} {s0}\n  enter emit a\n", e0)
        add(f"initial {s0}\n{ST} {s0}\n  {ON} {e0} if x < 1 {A} {s0}\n", e0)
        add(f"initial {s0}\n{ST} {s0}\n  {ON} {e0} {A} {s0} {ACT} set x 1\n", e0)
        add(f"initial {s0}\n{ST} {s0}\n  {ON} {e0} {A} {s0} {ACT} inc x\n", e0)
        add(f"initial {s0}\n{ST} {s0}\n  {ON} {e0} {A} {s0} {ACT} emit a, set x 1\n", e0)
    if hier:
        s3, s4 = sts[3], sts[4]
        e3 = evs[3]
        add(f"initial {s1}\n{ST} {s0}\n  {ON} {e0} {A} {s2}\n{ST} {s1} < {s0}\n{ST} {s2}\n", f"{e0} {e0}")
        add(f"initial {s2}\n{ST} {s0}\n  enter emit E0\n  exit emit X0\n  {ON} {e0} {A} {s3} {ACT} emit t0\n{ST} {s1} < {s0}\n  enter emit E1\n  exit emit X1\n{ST} {s2} < {s1}\n  enter emit E2\n  exit emit X2\n{ST} {s3}\n  enter emit E3\n", f"{e0} {e1}")
        add(f"initial {s2}\n{ST} {s0}\n  enter emit E0\n  exit emit X0\n{ST} {s1} < {s0}\n  enter emit E1\n  exit emit X1\n  {ON} {e0} {A} {s1} {ACT} emit self\n{ST} {s2} < {s1}\n  enter emit E2\n  exit emit X2\n", f"{e0} {e0}")
        add(f"initial {s2}\n{ST} {s0}\n  enter emit E0\n  exit emit X0\n{ST} {s1} < {s0}\n  enter emit E1\n  exit emit X1\n{ST} {s2} < {s1}\n  enter emit E2\n  exit emit X2\n  {ON} {e0} {A} {s0} {ACT} emit up\n  {ON} {e1} {A} {s1} {ACT} emit up1\n  {ON} {e2} {A} {s2} {ACT} emit self\n", f"{e0} {e1} {e2}")
        add(f"initial {s0}\n{ST} {s0}\n  enter emit E0\n  exit emit X0\n  {ON} {e0} {A} {s2} {ACT} emit down\n{ST} {s1} < {s0}\n  enter emit E1\n  exit emit X1\n{ST} {s2} < {s1}\n  enter emit E2\n  exit emit X2\n", f"{e0}")
        add(f"initial {s1}\n{ST} {s0}\n  enter emit E0\n  exit emit X0\n{ST} {s1} < {s0}\n  enter emit E1\n  exit emit X1\n  {ON} {e0} {A} {s2}\n{ST} {s2} < {s0}\n  enter emit E2\n  exit emit X2\n  {ON} {e0} {A} {s1}\n", f"{e0} {e0} {e0}")
        add(f"initial {s1}\n{ST} {s0}\n  {ON} {e0} {A} {s0} {ACT} emit parent\n  {ON} {e1} {A} {s2} {ACT} emit p2\n{ST} {s1} < {s0}\n  {ON} {e0} {A} {s1} {ACT} emit child\n{ST} {s2}\n", f"{e0} {e1} {e0}")
        add(f"initial {s1}\n{ST} {s0}\n  {ON} {e0} if n < 2 {A} {s0} {ACT} inc n, emit p\n  {ON} {e0} {A} {s2} {ACT} emit done\n{ST} {s1} < {s0}\n  {ON} {e0} if n > 5 {A} {s1} {ACT} emit never\n{ST} {s2}\n" if guards else f"initial {s1}\n{ST} {s0}\n{ST} {s1} < {s0}\n", " ".join([e0] * 5))
        add(f"initial {s0}\n{ST} {s0}\n{ST} {s1} < {s0}\n{ST} {s2} < {s1}\n{ST} {s3} < {s2}\n  {ON} {e0} {A} {s0}\n", e0)
        add(f"initial {s3}\n{ST} {s0}\n{ST} {s1} < {s0}\n{ST} {s2} < {s1}\n{ST} {s3} < {s2}\n  {ON} {e0} {A} {s0}\n{ST} {s4}\n", f"{e0}")
        add(f"initial {s3}\n{ST} {s3} < {s2}\n  enter emit E3\n  exit emit X3\n  {ON} {e0} {A} {s4}\n{ST} {s2} < {s1}\n  enter emit E2\n  exit emit X2\n{ST} {s1} < {s0}\n  enter emit E1\n  exit emit X1\n{ST} {s0}\n  enter emit E0\n  exit emit X0\n{ST} {s4} < {s1}\n  enter emit E4\n  exit emit X4\n  {ON} {e1} {A} {s3}\n" if guards else f"initial {s3}\n{ST} {s3} < {s2}\n{ST} {s2}\n", f"{e0} {e1} {e0}")
        for bad in [f"{ST} {s0} <\n", f"{ST} {s0} < {s1} {s2}\n", f"{ST} {s0} < 1x\n", f"{ST} {s0} {s1} {s2}\n", f"{ST} {s0} < {s0}\ninitial {s0}\n", f"{ST} {s0} < {s1}\n{ST} {s1} < {s0}\ninitial {s0}\n",
                    f"{ST} {s0} < nowhere\ninitial {s0}\n", f"{ST} {s0} < {s1}\n{ST} {s1} < {s2}\n{ST} {s2} < {s0}\ninitial {s0}\n", f"{ST} {s0} < {s1}\ninitial {s0}\n",
                    f"{ST} {s0} < {s1}\n{ST} {s1}\n{ST} {s2} < {s2}\ninitial {s0}\n", f"{ST} {s0} << {s1}\n{ST} {s1}\n", f"{ST} {s0} < {s1}\n{ST} {s1} < {s2}\n{ST} {s2}\ninitial {s0}\n  {ON} {e0} {A} {s2}\n",
                    f"{ST} {s0} < {s1}\n{ST} {s1} < {s2}\n{ST} {s2} < {s1}\ninitial {s0}\n"]:
            add(bad, f"{e0}")
    else:
        add(f"initial {s0}\n{ST} {s0}\n{ST} {s1} < {s0}\n", e0)
        add(f"initial {s0}\n{ST} {s0} < {s1}\n{ST} {s1}\n", e0)
    for _ in range(6):
        d, _ = machine_text(rng.randrange(4, 6), rng.randrange(2, 4))
        add(d, events(rng.randrange(12, 20)))
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
    name = p["machine"][0]
    feats = []
    if p["guards"]:
        feats.append("counters with guards and enter/exit actions")
    if p["hier"]:
        feats.append("parent states with inherited transitions")
    ft = (" It also has " + " and ".join(feats) + ".") if feats else ""
    opts = [
        f"We describe {name} in a little state-machine language and need a replay tool: `{fn}(definition, events)` in {ln} ({where}). It parses the definition (with precise error messages), runs the events and returns the trace. README.md is the full spec.{ft} {K.closer(rng)}",
        f"Please implement the machine runner from README.md in {ln}. Function `{fn}`, file {where}. The definition language is invented (arrow `{p['arrow']}`, transition word `{p['on']}`) so don't assume anything from other state-machine tools.{ft}",
        f"state machine DSL interpreter, {ln}, `{fn}` in {where}. spec in README.md. the order in which things run (and which parse error is reported) is specified exactly.{ft}",
        f"Task: write `{fn}` ({ln}, {where}). Input: a machine definition for {name} and a list of events; output: the step-by-step trace described in README.md.{ft} Hidden tests cover malformed definitions line by line.",
    ]
    return rng.choice(opts).strip()


@family("greenfield-statemachine", category="greenfield", lang="mixed", kind="greenfield", n=12,
        summary="state-machine DSL: parse (with line-numbered errors), replay events, guards on counters, entry/exit actions, hierarchical states")
def gen(rng, n):
    levels = [2, 2, 3, 3, 3, 4, 4, 4, 3, 4, 2, 4]
    diffs = [2, 2, 3, 3, 3, 4, 4, 5, 3, 4, 2, 4]
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level, i)
        api = K.Api(mod="statemachine", fn="machine", args=["definition", "events"], arg_docs=["the machine definition text", "the events, separated by blanks"],
                    ret_doc="the trace text, or an `error: ...` line", doc="state machine definition language runner")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["machine"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=diffs[i % len(diffs)], slug=f"{i + 1:02d}-{lang}-{p['machine'][0].split()[-1]}-l{level}",
            oracle=(None if lang == "python" else ns["machine"]), tags=["dsl", "parser", "state-machine"],
            notes={"level": level, "arrow": p["arrow"], "on": p["on"], "act": p["act"]},
        )
