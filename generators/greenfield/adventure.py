"""Text-adventure interpreter: world-file parser with three-pass errors, movement, items, locked doors, darkness, scoring, undo and saves (invented rules)."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

PY = r'''
DIRS = @DIRS@
SHOW = @SHOW@
HAS_ITEMS = @ITEMS@
HAS_LOCKS = @LOCKS@
HAS_DARK = @DARK@
HAS_UNDO = @UNDO@
HANDS = @HANDS@
M_NOWAY = @M_NOWAY@
M_LOCKED = @M_LOCKED@
M_NOITEM = @M_NOITEM@
M_NOHAVE = @M_NOHAVE@
M_FULL = @M_FULL@
M_DARK = @M_DARK@
M_DARKTAKE = @M_DARKTAKE@
M_UNKNOWN = @M_UNKNOWN@
M_TAKEN = @M_TAKEN@
M_DROPPED = @M_DROPPED@
LOW = "abcdefghijklmnopqrstuvwxyz"
DG = "0123456789"


class Err(Exception):
    pass


def good_id(s):
    return 1 <= len(s) <= 10 and s[0] in LOW and all(c in LOW + DG + "_" for c in s)


def good_text(s, mx):
    return 1 <= len(s) <= mx and s[0] != " " and s[-1] != " " and all(" " <= c <= "~" for c in s)


def good_num(s):
    return 1 <= len(s) <= 3 and all(c in DG for c in s) and (len(s) == 1 or s[0] != "0")


def directives():
    d = {"room": ["id", "text40"], "desc": ["id", "text120"], "exit": ["id", "dir", "id"], "start": ["id"]}
    if HAS_ITEMS:
        d["item"] = ["id", "id", "text40"]
    if HAS_LOCKS:
        d["lock"] = ["id", "dir", "id"]
    if HAS_DARK:
        d["dark"] = ["id"]
        d["light"] = ["id"]
        d["value"] = ["id", "num"]
        d["vault"] = ["id"]
    return d


def parse_world(text):
    spec = directives()
    W = {"rooms": {}, "desc": {}, "exits": {}, "start": None, "items": {}, "locks": {}, "dark": set(), "light": set(), "value": {}, "vault": set()}
    refs = []
    seen_start = False
    for n, line in enumerate(text.split("\n"), 1):
        if line == "":
            continue
        kw = line.split(" ", 1)[0]
        if kw not in spec:
            raise Err("error: world line %d: syntax" % n)
        kinds = spec[kw]
        if kinds[-1].startswith("text"):
            parts = line.split(" ", len(kinds))
        else:
            parts = line.split(" ")
        if len(parts) != 1 + len(kinds):
            raise Err("error: world line %d: syntax" % n)
        args = parts[1:]
        for kind, a in zip(kinds, args):
            if kind == "id" and not good_id(a):
                raise Err("error: world line %d: id" % n)
            if kind == "dir" and a not in DIRS:
                raise Err("error: world line %d: syntax" % n)
            if kind == "num" and not good_num(a):
                raise Err("error: world line %d: syntax" % n)
            if kind.startswith("text") and not good_text(a, int(kind[4:])):
                raise Err("error: world line %d: syntax" % n)
        dup = False
        r = []
        if kw == "room":
            dup = args[0] in W["rooms"]
            W["rooms"][args[0]] = args[1]
        elif kw == "desc":
            dup = args[0] in W["desc"]
            W["desc"][args[0]] = args[1]
            r = [("room", args[0])]
        elif kw == "exit":
            k = (args[0], args[1])
            dup = k in W["exits"]
            W["exits"][k] = args[2]
            r = [("room", args[0]), ("room", args[2])]
        elif kw == "start":
            dup = seen_start
            seen_start = True
            W["start"] = args[0]
            r = [("room", args[0])]
        elif kw == "item":
            dup = args[0] in W["items"]
            W["items"][args[0]] = (args[1], args[2])
            r = [("room", args[1])]
        elif kw == "lock":
            k = (args[0], args[1])
            dup = k in W["locks"]
            W["locks"][k] = args[2]
            r = [("exit", args[0], args[1]), ("item", args[2])]
        elif kw == "dark":
            dup = args[0] in W["dark"]
            W["dark"].add(args[0])
            r = [("room", args[0])]
        elif kw == "light":
            dup = args[0] in W["light"]
            W["light"].add(args[0])
            r = [("item", args[0])]
        elif kw == "value":
            dup = args[0] in W["value"]
            W["value"][args[0]] = int(args[1])
            r = [("item", args[0])]
        elif kw == "vault":
            dup = args[0] in W["vault"]
            W["vault"].add(args[0])
            r = [("room", args[0])]
        if dup:
            raise Err("error: world line %d: duplicate" % n)
        refs.append((n, r))
    for n, r in refs:
        for ref in r:
            if ref[0] == "room" and ref[1] not in W["rooms"]:
                raise Err("error: world line %d: unknown" % n)
            if ref[0] == "item" and ref[1] not in W["items"]:
                raise Err("error: world line %d: unknown" % n)
            if ref[0] == "exit" and (ref[1], ref[2]) not in W["exits"]:
                raise Err("error: world line %d: unknown" % n)
    if W["start"] is None:
        raise Err("error: world: no start")
    return W


def lit_room(W, st):
    if not HAS_DARK:
        return True
    return st["loc"] not in W["dark"] or any(i in W["light"] for i in st["inv"])


def view(W, st):
    if not lit_room(W, st):
        return [M_DARK]
    loc = st["loc"]
    out = ["== %s ==" % W["rooms"][loc]]
    if loc in W["desc"]:
        out.append(W["desc"][loc])
    ex = [d for d in SHOW if (loc, d) in W["exits"]]
    out.append("Exits: " + (", ".join(ex) if ex else "none"))
    if HAS_ITEMS and st["here"][loc]:
        out.append("Items: " + ", ".join(sorted(st["here"][loc])))
    return out


def snap(st):
    return {"loc": st["loc"], "inv": set(st["inv"]), "here": {k: set(v) for k, v in st["here"].items()}, "turns": st["turns"]}


class Game:
    def __init__(self, W):
        self.W = W
        self.st = {"loc": W["start"], "inv": set(), "here": {r: set() for r in W["rooms"]}, "turns": 0}
        for name, (room, _) in W["items"].items():
            self.st["here"][room].add(name)
        self.undo = []
        self.saves = {}

    def do(self, cmd):
        W, st, undo, saves = self.W, self.st, self.undo, self.saves
        w = cmd.split(" ")
        v = w[0]
        if v == "look" and len(w) == 1:
            return view(W, st)
        if v == "go" and len(w) == 2 and w[1] in DIRS:
            tgt = W["exits"].get((st["loc"], w[1]))
            if tgt is None:
                return [M_NOWAY]
            if HAS_LOCKS and (st["loc"], w[1]) in W["locks"] and W["locks"][(st["loc"], w[1])] not in st["inv"]:
                return [M_LOCKED]
            undo.append(snap(st))
            st["loc"] = tgt
            st["turns"] += 1
            return view(W, st)
        if HAS_ITEMS and v == "take" and len(w) == 2:
            if not lit_room(W, st):
                return [M_DARKTAKE]
            if w[1] not in st["here"][st["loc"]]:
                return [M_NOITEM.replace("{X}", w[1])]
            if len(st["inv"]) >= HANDS:
                return [M_FULL]
            undo.append(snap(st))
            st["here"][st["loc"]].discard(w[1])
            st["inv"].add(w[1])
            return [M_TAKEN]
        if HAS_ITEMS and v == "drop" and len(w) == 2:
            if w[1] not in st["inv"]:
                return [M_NOHAVE.replace("{X}", w[1])]
            undo.append(snap(st))
            st["inv"].discard(w[1])
            st["here"][st["loc"]].add(w[1])
            return [M_DROPPED]
        if HAS_ITEMS and v == "examine" and len(w) == 2:
            if w[1] in st["inv"] or (lit_room(W, st) and w[1] in st["here"][st["loc"]]):
                return [W["items"][w[1]][1]]
            return [M_NOITEM.replace("{X}", w[1])]
        if HAS_ITEMS and v == "inv" and len(w) == 1:
            return ["You carry: " + ", ".join(sorted(st["inv"]))] if st["inv"] else ["You carry nothing."]
        if HAS_DARK and v == "score" and len(w) == 1:
            tot = 0
            for r in W["vault"]:
                for i in st["here"][r]:
                    tot += W["value"].get(i, 0)
            return ["Score: %d" % tot]
        if HAS_UNDO and v == "undo" and len(w) == 1:
            if not undo:
                return ["Nothing to undo."]
            st.update(undo.pop())
            return ["Undone."]
        if HAS_UNDO and v == "turns" and len(w) == 1:
            return ["Turns: %d" % st["turns"]]
        if HAS_UNDO and v == "save" and len(w) == 2 and good_id(w[1]):
            saves[w[1]] = snap(st)
            return ["Saved."]
        if HAS_UNDO and v == "load" and len(w) == 2 and good_id(w[1]):
            if w[1] not in saves:
                return ["No such save."]
            undo.append(snap(st))
            st.update(snap(saves[w[1]]))
            return ["Loaded."]
        return [M_UNKNOWN]


def adventure(world, script):
    try:
        W = parse_world(world)
    except Err as e:
        return str(e)
    g = Game(W)
    out = []
    for cmd in script.split("\n"):
        if cmd == "":
            continue
        out.append("> " + cmd)
        out.extend(g.do(cmd))
    return "\n".join(out)
'''

JS = r'''
'use strict';
const DIRS = @DIRS@;
const SHOW = @SHOW@;
const HAS_ITEMS = @ITEMS@;
const HAS_LOCKS = @LOCKS@;
const HAS_DARK = @DARK@;
const HAS_UNDO = @UNDO@;
const HANDS = @HANDS@;
const M_NOWAY = @M_NOWAY@;
const M_LOCKED = @M_LOCKED@;
const M_NOITEM = @M_NOITEM@;
const M_NOHAVE = @M_NOHAVE@;
const M_FULL = @M_FULL@;
const M_DARK = @M_DARK@;
const M_DARKTAKE = @M_DARKTAKE@;
const M_UNKNOWN = @M_UNKNOWN@;
const M_TAKEN = @M_TAKEN@;
const M_DROPPED = @M_DROPPED@;
const LOW = 'abcdefghijklmnopqrstuvwxyz';
const DG = '0123456789';

class Err extends Error {}

function goodId(s) {
  if (s.length < 1 || s.length > 10 || !LOW.includes(s[0])) return false;
  for (const c of s) if (!(LOW + DG + '_').includes(c)) return false;
  return true;
}

function goodText(s, mx) {
  if (s.length < 1 || s.length > mx || s[0] === ' ' || s[s.length - 1] === ' ') return false;
  for (const c of s) if (c < ' ' || c > '~') return false;
  return true;
}

function goodNum(s) {
  if (s.length < 1 || s.length > 3) return false;
  for (const c of s) if (!DG.includes(c)) return false;
  return s.length === 1 || s[0] !== '0';
}

function directives() {
  const d = { room: ['id', 'text40'], desc: ['id', 'text120'], exit: ['id', 'dir', 'id'], start: ['id'] };
  if (HAS_ITEMS) d.item = ['id', 'id', 'text40'];
  if (HAS_LOCKS) d.lock = ['id', 'dir', 'id'];
  if (HAS_DARK) {
    d.dark = ['id'];
    d.light = ['id'];
    d.value = ['id', 'num'];
    d.vault = ['id'];
  }
  return d;
}

function splitMax(line, n) {
  // like Python's line.split(' ', n)
  const out = [];
  let rest = line;
  while (out.length < n) {
    const i = rest.indexOf(' ');
    if (i < 0) break;
    out.push(rest.slice(0, i));
    rest = rest.slice(i + 1);
  }
  out.push(rest);
  return out;
}

function parseWorld(text) {
  const spec = directives();
  const W = { rooms: new Map(), desc: new Map(), exits: new Map(), start: null, items: new Map(), locks: new Map(), dark: new Set(), light: new Set(), value: new Map(), vault: new Set() };
  const refs = [];
  let seenStart = false;
  const lines = text.split('\n');
  for (let ln = 0; ln < lines.length; ln++) {
    const n = ln + 1;
    const line = lines[ln];
    if (line === '') continue;
    const kw = splitMax(line, 1)[0];
    if (!Object.prototype.hasOwnProperty.call(spec, kw)) throw new Err('error: world line ' + n + ': syntax');
    const kinds = spec[kw];
    const parts = kinds[kinds.length - 1].startsWith('text') ? splitMax(line, kinds.length) : line.split(' ');
    if (parts.length !== 1 + kinds.length) throw new Err('error: world line ' + n + ': syntax');
    const args = parts.slice(1);
    for (let i = 0; i < kinds.length; i++) {
      const kind = kinds[i];
      const a = args[i];
      if (kind === 'id' && !goodId(a)) throw new Err('error: world line ' + n + ': id');
      if (kind === 'dir' && !DIRS.includes(a)) throw new Err('error: world line ' + n + ': syntax');
      if (kind === 'num' && !goodNum(a)) throw new Err('error: world line ' + n + ': syntax');
      if (kind.startsWith('text') && !goodText(a, parseInt(kind.slice(4), 10))) throw new Err('error: world line ' + n + ': syntax');
    }
    let dup = false;
    let r = [];
    if (kw === 'room') {
      dup = W.rooms.has(args[0]);
      W.rooms.set(args[0], args[1]);
    } else if (kw === 'desc') {
      dup = W.desc.has(args[0]);
      W.desc.set(args[0], args[1]);
      r = [['room', args[0]]];
    } else if (kw === 'exit') {
      const k = args[0] + ' ' + args[1];
      dup = W.exits.has(k);
      W.exits.set(k, args[2]);
      r = [['room', args[0]], ['room', args[2]]];
    } else if (kw === 'start') {
      dup = seenStart;
      seenStart = true;
      W.start = args[0];
      r = [['room', args[0]]];
    } else if (kw === 'item') {
      dup = W.items.has(args[0]);
      W.items.set(args[0], [args[1], args[2]]);
      r = [['room', args[1]]];
    } else if (kw === 'lock') {
      const k = args[0] + ' ' + args[1];
      dup = W.locks.has(k);
      W.locks.set(k, args[2]);
      r = [['exit', args[0] + ' ' + args[1]], ['item', args[2]]];
    } else if (kw === 'dark') {
      dup = W.dark.has(args[0]);
      W.dark.add(args[0]);
      r = [['room', args[0]]];
    } else if (kw === 'light') {
      dup = W.light.has(args[0]);
      W.light.add(args[0]);
      r = [['item', args[0]]];
    } else if (kw === 'value') {
      dup = W.value.has(args[0]);
      W.value.set(args[0], parseInt(args[1], 10));
      r = [['item', args[0]]];
    } else if (kw === 'vault') {
      dup = W.vault.has(args[0]);
      W.vault.add(args[0]);
      r = [['room', args[0]]];
    }
    if (dup) throw new Err('error: world line ' + n + ': duplicate');
    refs.push([n, r]);
  }
  for (const [n, r] of refs) {
    for (const ref of r) {
      if (ref[0] === 'room' && !W.rooms.has(ref[1])) throw new Err('error: world line ' + n + ': unknown');
      if (ref[0] === 'item' && !W.items.has(ref[1])) throw new Err('error: world line ' + n + ': unknown');
      if (ref[0] === 'exit' && !W.exits.has(ref[1])) throw new Err('error: world line ' + n + ': unknown');
    }
  }
  if (W.start === null) throw new Err('error: world: no start');
  return W;
}

function carriesLight(W, st) {
  for (const i of st.inv) if (W.light.has(i)) return true;
  return false;
}

function litRoom(W, st) {
  if (!HAS_DARK) return true;
  return !W.dark.has(st.loc) || carriesLight(W, st);
}

function view(W, st) {
  if (!litRoom(W, st)) return [M_DARK];
  const loc = st.loc;
  const out = ['== ' + W.rooms.get(loc) + ' =='];
  if (W.desc.has(loc)) out.push(W.desc.get(loc));
  const ex = SHOW.filter((d) => W.exits.has(loc + ' ' + d));
  out.push('Exits: ' + (ex.length ? ex.join(', ') : 'none'));
  const here = st.here.get(loc);
  if (HAS_ITEMS && here.size > 0) out.push('Items: ' + Array.from(here).sort().join(', '));
  return out;
}

function snap(st) {
  const here = new Map();
  for (const [k, v] of st.here) here.set(k, new Set(v));
  return { loc: st.loc, inv: new Set(st.inv), here, turns: st.turns };
}

function adventure(world, script) {
  let W;
  try {
    W = parseWorld(world);
  } catch (e) {
    if (e instanceof Err) return e.message;
    throw e;
  }
  const st = { loc: W.start, inv: new Set(), here: new Map(), turns: 0 };
  for (const r of W.rooms.keys()) st.here.set(r, new Set());
  for (const [name, [room]] of W.items) st.here.get(room).add(name);
  const undo = [];
  const saves = new Map();
  const out = [];
  const restore = (s) => {
    st.loc = s.loc;
    st.inv = s.inv;
    st.here = s.here;
    st.turns = s.turns;
  };
  for (const cmd of script.split('\n')) {
    if (cmd === '') continue;
    out.push('> ' + cmd);
    const w = cmd.split(' ');
    const v = w[0];
    let res;
    if (v === 'look' && w.length === 1) res = view(W, st);
    else if (v === 'go' && w.length === 2 && DIRS.includes(w[1])) {
      const key = st.loc + ' ' + w[1];
      const tgt = W.exits.get(key);
      if (tgt === undefined) res = [M_NOWAY];
      else if (HAS_LOCKS && W.locks.has(key) && !st.inv.has(W.locks.get(key))) res = [M_LOCKED];
      else {
        undo.push(snap(st));
        st.loc = tgt;
        st.turns += 1;
        res = view(W, st);
      }
    } else if (HAS_ITEMS && v === 'take' && w.length === 2) {
      if (!litRoom(W, st)) res = [M_DARKTAKE];
      else if (!st.here.get(st.loc).has(w[1])) res = [M_NOITEM.split('{X}').join(w[1])];
      else if (st.inv.size >= HANDS) res = [M_FULL];
      else {
        undo.push(snap(st));
        st.here.get(st.loc).delete(w[1]);
        st.inv.add(w[1]);
        res = [M_TAKEN];
      }
    } else if (HAS_ITEMS && v === 'drop' && w.length === 2) {
      if (!st.inv.has(w[1])) res = [M_NOHAVE.split('{X}').join(w[1])];
      else {
        undo.push(snap(st));
        st.inv.delete(w[1]);
        st.here.get(st.loc).add(w[1]);
        res = [M_DROPPED];
      }
    } else if (HAS_ITEMS && v === 'examine' && w.length === 2) {
      if (st.inv.has(w[1]) || (litRoom(W, st) && st.here.get(st.loc).has(w[1]))) res = [W.items.get(w[1])[1]];
      else res = [M_NOITEM.split('{X}').join(w[1])];
    } else if (HAS_ITEMS && v === 'inv' && w.length === 1) {
      res = st.inv.size > 0 ? ['You carry: ' + Array.from(st.inv).sort().join(', ')] : ['You carry nothing.'];
    } else if (HAS_DARK && v === 'score' && w.length === 1) {
      let tot = 0;
      for (const r of W.vault) for (const i of st.here.get(r)) tot += W.value.has(i) ? W.value.get(i) : 0;
      res = ['Score: ' + tot];
    } else if (HAS_UNDO && v === 'undo' && w.length === 1) {
      if (undo.length === 0) res = ['Nothing to undo.'];
      else {
        restore(undo.pop());
        res = ['Undone.'];
      }
    } else if (HAS_UNDO && v === 'turns' && w.length === 1) res = ['Turns: ' + st.turns];
    else if (HAS_UNDO && v === 'save' && w.length === 2 && goodId(w[1])) {
      saves.set(w[1], snap(st));
      res = ['Saved.'];
    } else if (HAS_UNDO && v === 'load' && w.length === 2 && goodId(w[1])) {
      if (!saves.has(w[1])) res = ['No such save.'];
      else {
        undo.push(snap(st));
        restore(snap(saves.get(w[1])));
        res = ['Loaded.'];
      }
    } else res = [M_UNKNOWN];
    for (const x of res) out.push(x);
  }
  return out.join('\n');
}

module.exports = { adventure };
'''

JV = r'''
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class Adventure {
    static final String[] DIRS = @DIRS@;
    static final String[] SHOW = @SHOW@;
    static final boolean HAS_ITEMS = @ITEMS@;
    static final boolean HAS_LOCKS = @LOCKS@;
    static final boolean HAS_DARK = @DARK@;
    static final boolean HAS_UNDO = @UNDO@;
    static final int HANDS = @HANDS@;
    static final String M_NOWAY = @M_NOWAY@;
    static final String M_LOCKED = @M_LOCKED@;
    static final String M_NOITEM = @M_NOITEM@;
    static final String M_NOHAVE = @M_NOHAVE@;
    static final String M_FULL = @M_FULL@;
    static final String M_DARK = @M_DARK@;
    static final String M_DARKTAKE = @M_DARKTAKE@;
    static final String M_UNKNOWN = @M_UNKNOWN@;
    static final String M_TAKEN = @M_TAKEN@;
    static final String M_DROPPED = @M_DROPPED@;
    static final String LOW = "abcdefghijklmnopqrstuvwxyz";
    static final String DG = "0123456789";

    static class Err extends RuntimeException {
        Err(String m) { super(m); }
    }

    static class World {
        Map<String, String> rooms = new HashMap<>();
        Map<String, String> desc = new HashMap<>();
        Map<String, String> exits = new HashMap<>();
        String start = null;
        Map<String, String[]> items = new HashMap<>();
        Map<String, String> locks = new HashMap<>();
        Set<String> dark = new HashSet<>();
        Set<String> light = new HashSet<>();
        Map<String, Integer> value = new HashMap<>();
        Set<String> vault = new HashSet<>();
    }

    static class State {
        String loc;
        Set<String> inv = new HashSet<>();
        Map<String, Set<String>> here = new HashMap<>();
        int turns;

        State copy() {
            State s = new State();
            s.loc = loc;
            s.inv = new HashSet<>(inv);
            for (Map.Entry<String, Set<String>> e : here.entrySet()) s.here.put(e.getKey(), new HashSet<>(e.getValue()));
            s.turns = turns;
            return s;
        }

        void restore(State s) {
            loc = s.loc;
            inv = s.inv;
            here = s.here;
            turns = s.turns;
        }
    }

    static boolean inArr(String[] a, String x) {
        for (String s : a) if (s.equals(x)) return true;
        return false;
    }

    static boolean goodId(String s) {
        if (s.length() < 1 || s.length() > 10 || LOW.indexOf(s.charAt(0)) < 0) return false;
        for (int i = 0; i < s.length(); i++) if ((LOW + DG + "_").indexOf(s.charAt(i)) < 0) return false;
        return true;
    }

    static boolean goodText(String s, int mx) {
        if (s.length() < 1 || s.length() > mx || s.charAt(0) == ' ' || s.charAt(s.length() - 1) == ' ') return false;
        for (int i = 0; i < s.length(); i++) if (s.charAt(i) < ' ' || s.charAt(i) > '~') return false;
        return true;
    }

    static boolean goodNum(String s) {
        if (s.length() < 1 || s.length() > 3) return false;
        for (int i = 0; i < s.length(); i++) if (DG.indexOf(s.charAt(i)) < 0) return false;
        return s.length() == 1 || s.charAt(0) != '0';
    }

    static Map<String, String[]> directives() {
        Map<String, String[]> d = new HashMap<>();
        d.put("room", new String[] { "id", "text40" });
        d.put("desc", new String[] { "id", "text120" });
        d.put("exit", new String[] { "id", "dir", "id" });
        d.put("start", new String[] { "id" });
        if (HAS_ITEMS) d.put("item", new String[] { "id", "id", "text40" });
        if (HAS_LOCKS) d.put("lock", new String[] { "id", "dir", "id" });
        if (HAS_DARK) {
            d.put("dark", new String[] { "id" });
            d.put("light", new String[] { "id" });
            d.put("value", new String[] { "id", "num" });
            d.put("vault", new String[] { "id" });
        }
        return d;
    }

    static Err werr(int n, String why) {
        return new Err("error: world line " + n + ": " + why);
    }

    static World parseWorld(String text) {
        Map<String, String[]> spec = directives();
        World w = new World();
        List<Object[]> refs = new ArrayList<>();
        boolean seenStart = false;
        String[] lines = text.split("\n", -1);
        for (int ln = 0; ln < lines.length; ln++) {
            int n = ln + 1;
            String line = lines[ln];
            if (line.isEmpty()) continue;
            String kw = line.split(" ", 2)[0];
            if (!spec.containsKey(kw)) throw werr(n, "syntax");
            String[] kinds = spec.get(kw);
            String[] parts = kinds[kinds.length - 1].startsWith("text") ? line.split(" ", kinds.length + 1) : line.split(" ", -1);
            if (parts.length != 1 + kinds.length) throw werr(n, "syntax");
            String[] args = Arrays.copyOfRange(parts, 1, parts.length);
            for (int i = 0; i < kinds.length; i++) {
                String kind = kinds[i], a = args[i];
                if (kind.equals("id") && !goodId(a)) throw werr(n, "id");
                if (kind.equals("dir") && !inArr(DIRS, a)) throw werr(n, "syntax");
                if (kind.equals("num") && !goodNum(a)) throw werr(n, "syntax");
                if (kind.startsWith("text") && !goodText(a, Integer.parseInt(kind.substring(4)))) throw werr(n, "syntax");
            }
            boolean dup = false;
            List<String[]> r = new ArrayList<>();
            switch (kw) {
                case "room":
                    dup = w.rooms.containsKey(args[0]);
                    w.rooms.put(args[0], args[1]);
                    break;
                case "desc":
                    dup = w.desc.containsKey(args[0]);
                    w.desc.put(args[0], args[1]);
                    r.add(new String[] { "room", args[0] });
                    break;
                case "exit": {
                    String k = args[0] + " " + args[1];
                    dup = w.exits.containsKey(k);
                    w.exits.put(k, args[2]);
                    r.add(new String[] { "room", args[0] });
                    r.add(new String[] { "room", args[2] });
                    break;
                }
                case "start":
                    dup = seenStart;
                    seenStart = true;
                    w.start = args[0];
                    r.add(new String[] { "room", args[0] });
                    break;
                case "item":
                    dup = w.items.containsKey(args[0]);
                    w.items.put(args[0], new String[] { args[1], args[2] });
                    r.add(new String[] { "room", args[1] });
                    break;
                case "lock": {
                    String k = args[0] + " " + args[1];
                    dup = w.locks.containsKey(k);
                    w.locks.put(k, args[2]);
                    r.add(new String[] { "exit", k });
                    r.add(new String[] { "item", args[2] });
                    break;
                }
                case "dark":
                    dup = !w.dark.add(args[0]);
                    r.add(new String[] { "room", args[0] });
                    break;
                case "light":
                    dup = !w.light.add(args[0]);
                    r.add(new String[] { "item", args[0] });
                    break;
                case "value":
                    dup = w.value.containsKey(args[0]);
                    w.value.put(args[0], Integer.parseInt(args[1]));
                    r.add(new String[] { "item", args[0] });
                    break;
                case "vault":
                    dup = !w.vault.add(args[0]);
                    r.add(new String[] { "room", args[0] });
                    break;
                default:
                    break;
            }
            if (dup) throw werr(n, "duplicate");
            refs.add(new Object[] { n, r });
        }
        for (Object[] e : refs) {
            int n = (Integer) e[0];
            @SuppressWarnings("unchecked")
            List<String[]> r = (List<String[]>) e[1];
            for (String[] ref : r) {
                if (ref[0].equals("room") && !w.rooms.containsKey(ref[1])) throw werr(n, "unknown");
                if (ref[0].equals("item") && !w.items.containsKey(ref[1])) throw werr(n, "unknown");
                if (ref[0].equals("exit") && !w.exits.containsKey(ref[1])) throw werr(n, "unknown");
            }
        }
        if (w.start == null) throw new Err("error: world: no start");
        return w;
    }

    static boolean litRoom(World w, State st) {
        if (!HAS_DARK) return true;
        if (!w.dark.contains(st.loc)) return true;
        for (String i : st.inv) if (w.light.contains(i)) return true;
        return false;
    }

    static List<String> view(World w, State st) {
        List<String> out = new ArrayList<>();
        if (!litRoom(w, st)) {
            out.add(M_DARK);
            return out;
        }
        String loc = st.loc;
        out.add("== " + w.rooms.get(loc) + " ==");
        if (w.desc.containsKey(loc)) out.add(w.desc.get(loc));
        List<String> ex = new ArrayList<>();
        for (String d : SHOW) if (w.exits.containsKey(loc + " " + d)) ex.add(d);
        out.add("Exits: " + (ex.isEmpty() ? "none" : String.join(", ", ex)));
        Set<String> here = st.here.get(loc);
        if (HAS_ITEMS && !here.isEmpty()) out.add("Items: " + String.join(", ", new TreeSet<>(here)));
        return out;
    }

    public static String adventure(String world, String script) {
        World w;
        try {
            w = parseWorld(world);
        } catch (Err e) {
            return e.getMessage();
        }
        State st = new State();
        st.loc = w.start;
        for (String r : w.rooms.keySet()) st.here.put(r, new HashSet<>());
        for (Map.Entry<String, String[]> e : w.items.entrySet()) st.here.get(e.getValue()[0]).add(e.getKey());
        List<State> undo = new ArrayList<>();
        Map<String, State> saves = new HashMap<>();
        List<String> out = new ArrayList<>();
        for (String cmd : script.split("\n", -1)) {
            if (cmd.isEmpty()) continue;
            out.add("> " + cmd);
            String[] ws = cmd.split(" ", -1);
            String v = ws[0];
            List<String> res = new ArrayList<>();
            if (v.equals("look") && ws.length == 1) {
                res = view(w, st);
            } else if (v.equals("go") && ws.length == 2 && inArr(DIRS, ws[1])) {
                String key = st.loc + " " + ws[1];
                String tgt = w.exits.get(key);
                if (tgt == null) res.add(M_NOWAY);
                else if (HAS_LOCKS && w.locks.containsKey(key) && !st.inv.contains(w.locks.get(key))) res.add(M_LOCKED);
                else {
                    undo.add(st.copy());
                    st.loc = tgt;
                    st.turns++;
                    res = view(w, st);
                }
            } else if (HAS_ITEMS && v.equals("take") && ws.length == 2) {
                if (!litRoom(w, st)) res.add(M_DARKTAKE);
                else if (!st.here.get(st.loc).contains(ws[1])) res.add(M_NOITEM.replace("{X}", ws[1]));
                else if (st.inv.size() >= HANDS) res.add(M_FULL);
                else {
                    undo.add(st.copy());
                    st.here.get(st.loc).remove(ws[1]);
                    st.inv.add(ws[1]);
                    res.add(M_TAKEN);
                }
            } else if (HAS_ITEMS && v.equals("drop") && ws.length == 2) {
                if (!st.inv.contains(ws[1])) res.add(M_NOHAVE.replace("{X}", ws[1]));
                else {
                    undo.add(st.copy());
                    st.inv.remove(ws[1]);
                    st.here.get(st.loc).add(ws[1]);
                    res.add(M_DROPPED);
                }
            } else if (HAS_ITEMS && v.equals("examine") && ws.length == 2) {
                if (st.inv.contains(ws[1]) || (litRoom(w, st) && st.here.get(st.loc).contains(ws[1]))) res.add(w.items.get(ws[1])[1]);
                else res.add(M_NOITEM.replace("{X}", ws[1]));
            } else if (HAS_ITEMS && v.equals("inv") && ws.length == 1) {
                if (st.inv.isEmpty()) res.add("You carry nothing.");
                else res.add("You carry: " + String.join(", ", new TreeSet<>(st.inv)));
            } else if (HAS_DARK && v.equals("score") && ws.length == 1) {
                int tot = 0;
                for (String r : w.vault) for (String i : st.here.get(r)) tot += w.value.containsKey(i) ? w.value.get(i) : 0;
                res.add("Score: " + tot);
            } else if (HAS_UNDO && v.equals("undo") && ws.length == 1) {
                if (undo.isEmpty()) res.add("Nothing to undo.");
                else {
                    st.restore(undo.remove(undo.size() - 1));
                    res.add("Undone.");
                }
            } else if (HAS_UNDO && v.equals("turns") && ws.length == 1) {
                res.add("Turns: " + st.turns);
            } else if (HAS_UNDO && v.equals("save") && ws.length == 2 && goodId(ws[1])) {
                saves.put(ws[1], st.copy());
                res.add("Saved.");
            } else if (HAS_UNDO && v.equals("load") && ws.length == 2 && goodId(ws[1])) {
                if (!saves.containsKey(ws[1])) res.add("No such save.");
                else {
                    undo.add(st.copy());
                    st.restore(saves.get(ws[1]).copy());
                    res.add("Loaded.");
                }
            } else {
                res.add(M_UNKNOWN);
            }
            out.addAll(res);
        }
        return String.join("\n", out);
    }
}
'''

GO = r'''
package adventure

import (
	"sort"
	"strconv"
	"strings"
)

const (
	hasItems = @ITEMS@
	hasLocks = @LOCKS@
	hasDark  = @DARK@
	hasUndo  = @UNDO@
	hands    = @HANDS@
	mNoway   = @M_NOWAY@
	mLocked  = @M_LOCKED@
	mNoitem  = @M_NOITEM@
	mNohave  = @M_NOHAVE@
	mFull    = @M_FULL@
	mDark    = @M_DARK@
	mDarkTk  = @M_DARKTAKE@
	mUnk     = @M_UNKNOWN@
	mTaken   = @M_TAKEN@
	mDropped = @M_DROPPED@
)

var dirs = []string@DIRS@
var show = []string@SHOW@

type worldErr struct{ msg string }

type world struct {
	rooms map[string]string
	desc  map[string]string
	exits map[string]string
	start string
	items map[string][2]string
	locks map[string]string
	dark  map[string]bool
	light map[string]bool
	value map[string]int
	vault map[string]bool
}

type state struct {
	loc   string
	inv   map[string]bool
	here  map[string]map[string]bool
	turns int
}

func fail(m string) { panic(worldErr{m}) }

func werr(n int, why string) { fail("error: world line " + strconv.Itoa(n) + ": " + why) }

func inDirs(s string) bool {
	for _, d := range dirs {
		if d == s {
			return true
		}
	}
	return false
}

func goodID(s string) bool {
	if len(s) < 1 || len(s) > 10 || !(s[0] >= 'a' && s[0] <= 'z') {
		return false
	}
	for i := 0; i < len(s); i++ {
		c := s[i]
		if !(c >= 'a' && c <= 'z') && !(c >= '0' && c <= '9') && c != '_' {
			return false
		}
	}
	return true
}

func goodText(s string, mx int) bool {
	if len(s) < 1 || len(s) > mx || s[0] == ' ' || s[len(s)-1] == ' ' {
		return false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < ' ' || s[i] > '~' {
			return false
		}
	}
	return true
}

func goodNum(s string) bool {
	if len(s) < 1 || len(s) > 3 {
		return false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	return len(s) == 1 || s[0] != '0'
}

func directives() map[string][]string {
	d := map[string][]string{"room": {"id", "text40"}, "desc": {"id", "text120"}, "exit": {"id", "dir", "id"}, "start": {"id"}}
	if hasItems {
		d["item"] = []string{"id", "id", "text40"}
	}
	if hasLocks {
		d["lock"] = []string{"id", "dir", "id"}
	}
	if hasDark {
		d["dark"] = []string{"id"}
		d["light"] = []string{"id"}
		d["value"] = []string{"id", "num"}
		d["vault"] = []string{"id"}
	}
	return d
}

type ref struct{ kind, a string }

func parseWorld(text string) *world {
	spec := directives()
	w := &world{rooms: map[string]string{}, desc: map[string]string{}, exits: map[string]string{}, items: map[string][2]string{}, locks: map[string]string{}, dark: map[string]bool{}, light: map[string]bool{}, value: map[string]int{}, vault: map[string]bool{}}
	type lineRefs struct {
		n    int
		refs []ref
	}
	var all []lineRefs
	seenStart := false
	started := false
	for ln, line := range strings.Split(text, "\n") {
		n := ln + 1
		if line == "" {
			continue
		}
		kw := strings.SplitN(line, " ", 2)[0]
		kinds, ok := spec[kw]
		if !ok {
			werr(n, "syntax")
		}
		var parts []string
		if strings.HasPrefix(kinds[len(kinds)-1], "text") {
			parts = strings.SplitN(line, " ", len(kinds)+1)
		} else {
			parts = strings.Split(line, " ")
		}
		if len(parts) != 1+len(kinds) {
			werr(n, "syntax")
		}
		args := parts[1:]
		for i, kind := range kinds {
			a := args[i]
			if kind == "id" && !goodID(a) {
				werr(n, "id")
			}
			if kind == "dir" && !inDirs(a) {
				werr(n, "syntax")
			}
			if kind == "num" && !goodNum(a) {
				werr(n, "syntax")
			}
			if strings.HasPrefix(kind, "text") {
				mx, _ := strconv.Atoi(kind[4:])
				if !goodText(a, mx) {
					werr(n, "syntax")
				}
			}
		}
		dup := false
		var r []ref
		switch kw {
		case "room":
			_, dup = w.rooms[args[0]]
			w.rooms[args[0]] = args[1]
		case "desc":
			_, dup = w.desc[args[0]]
			w.desc[args[0]] = args[1]
			r = []ref{{"room", args[0]}}
		case "exit":
			k := args[0] + " " + args[1]
			_, dup = w.exits[k]
			w.exits[k] = args[2]
			r = []ref{{"room", args[0]}, {"room", args[2]}}
		case "start":
			dup = seenStart
			seenStart = true
			started = true
			w.start = args[0]
			r = []ref{{"room", args[0]}}
		case "item":
			_, dup = w.items[args[0]]
			w.items[args[0]] = [2]string{args[1], args[2]}
			r = []ref{{"room", args[1]}}
		case "lock":
			k := args[0] + " " + args[1]
			_, dup = w.locks[k]
			w.locks[k] = args[2]
			r = []ref{{"exit", k}, {"item", args[2]}}
		case "dark":
			dup = w.dark[args[0]]
			w.dark[args[0]] = true
			r = []ref{{"room", args[0]}}
		case "light":
			dup = w.light[args[0]]
			w.light[args[0]] = true
			r = []ref{{"item", args[0]}}
		case "value":
			_, dup = w.value[args[0]]
			w.value[args[0]], _ = strconv.Atoi(args[1])
			r = []ref{{"item", args[0]}}
		case "vault":
			dup = w.vault[args[0]]
			w.vault[args[0]] = true
			r = []ref{{"room", args[0]}}
		}
		if dup {
			werr(n, "duplicate")
		}
		all = append(all, lineRefs{n, r})
	}
	for _, lr := range all {
		for _, rf := range lr.refs {
			switch rf.kind {
			case "room":
				if _, ok := w.rooms[rf.a]; !ok {
					werr(lr.n, "unknown")
				}
			case "item":
				if _, ok := w.items[rf.a]; !ok {
					werr(lr.n, "unknown")
				}
			case "exit":
				if _, ok := w.exits[rf.a]; !ok {
					werr(lr.n, "unknown")
				}
			}
		}
	}
	if !started {
		fail("error: world: no start")
	}
	return w
}

func litRoom(w *world, st *state) bool {
	if !hasDark {
		return true
	}
	if !w.dark[st.loc] {
		return true
	}
	for i := range st.inv {
		if w.light[i] {
			return true
		}
	}
	return false
}

func sortedKeys(m map[string]bool) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func view(w *world, st *state) []string {
	if !litRoom(w, st) {
		return []string{mDark}
	}
	loc := st.loc
	out := []string{"== " + w.rooms[loc] + " =="}
	if d, ok := w.desc[loc]; ok {
		out = append(out, d)
	}
	var ex []string
	for _, d := range show {
		if _, ok := w.exits[loc+" "+d]; ok {
			ex = append(ex, d)
		}
	}
	if len(ex) == 0 {
		out = append(out, "Exits: none")
	} else {
		out = append(out, "Exits: "+strings.Join(ex, ", "))
	}
	if hasItems && len(st.here[loc]) > 0 {
		out = append(out, "Items: "+strings.Join(sortedKeys(st.here[loc]), ", "))
	}
	return out
}

func snap(st *state) *state {
	s := &state{loc: st.loc, inv: map[string]bool{}, here: map[string]map[string]bool{}, turns: st.turns}
	for k := range st.inv {
		s.inv[k] = true
	}
	for r, items := range st.here {
		s.here[r] = map[string]bool{}
		for k := range items {
			s.here[r][k] = true
		}
	}
	return s
}

func restore(st *state, s *state) {
	st.loc, st.inv, st.here, st.turns = s.loc, s.inv, s.here, s.turns
}

func run(worldText, script string) string {
	w := parseWorld(worldText)
	st := &state{loc: w.start, inv: map[string]bool{}, here: map[string]map[string]bool{}}
	for r := range w.rooms {
		st.here[r] = map[string]bool{}
	}
	for name, it := range w.items {
		st.here[it[0]][name] = true
	}
	var undo []*state
	saves := map[string]*state{}
	var out []string
	for _, cmd := range strings.Split(script, "\n") {
		if cmd == "" {
			continue
		}
		out = append(out, "> "+cmd)
		ws := strings.Split(cmd, " ")
		v := ws[0]
		var res []string
		switch {
		case v == "look" && len(ws) == 1:
			res = view(w, st)
		case v == "go" && len(ws) == 2 && inDirs(ws[1]):
			key := st.loc + " " + ws[1]
			tgt, ok := w.exits[key]
			if !ok {
				res = []string{mNoway}
			} else if _, locked := w.locks[key]; hasLocks && locked && !st.inv[w.locks[key]] {
				res = []string{mLocked}
			} else {
				undo = append(undo, snap(st))
				st.loc = tgt
				st.turns++
				res = view(w, st)
			}
		case hasItems && v == "take" && len(ws) == 2:
			if !litRoom(w, st) {
				res = []string{mDarkTk}
			} else if !st.here[st.loc][ws[1]] {
				res = []string{strings.ReplaceAll(mNoitem, "{X}", ws[1])}
			} else if len(st.inv) >= hands {
				res = []string{mFull}
			} else {
				undo = append(undo, snap(st))
				delete(st.here[st.loc], ws[1])
				st.inv[ws[1]] = true
				res = []string{mTaken}
			}
		case hasItems && v == "drop" && len(ws) == 2:
			if !st.inv[ws[1]] {
				res = []string{strings.ReplaceAll(mNohave, "{X}", ws[1])}
			} else {
				undo = append(undo, snap(st))
				delete(st.inv, ws[1])
				st.here[st.loc][ws[1]] = true
				res = []string{mDropped}
			}
		case hasItems && v == "examine" && len(ws) == 2:
			if st.inv[ws[1]] || (litRoom(w, st) && st.here[st.loc][ws[1]]) {
				res = []string{w.items[ws[1]][1]}
			} else {
				res = []string{strings.ReplaceAll(mNoitem, "{X}", ws[1])}
			}
		case hasItems && v == "inv" && len(ws) == 1:
			if len(st.inv) == 0 {
				res = []string{"You carry nothing."}
			} else {
				res = []string{"You carry: " + strings.Join(sortedKeys(st.inv), ", ")}
			}
		case hasDark && v == "score" && len(ws) == 1:
			tot := 0
			for r := range w.vault {
				for i := range st.here[r] {
					tot += w.value[i]
				}
			}
			res = []string{"Score: " + strconv.Itoa(tot)}
		case hasUndo && v == "undo" && len(ws) == 1:
			if len(undo) == 0 {
				res = []string{"Nothing to undo."}
			} else {
				restore(st, undo[len(undo)-1])
				undo = undo[:len(undo)-1]
				res = []string{"Undone."}
			}
		case hasUndo && v == "turns" && len(ws) == 1:
			res = []string{"Turns: " + strconv.Itoa(st.turns)}
		case hasUndo && v == "save" && len(ws) == 2 && goodID(ws[1]):
			saves[ws[1]] = snap(st)
			res = []string{"Saved."}
		case hasUndo && v == "load" && len(ws) == 2 && goodID(ws[1]):
			s, ok := saves[ws[1]]
			if !ok {
				res = []string{"No such save."}
			} else {
				undo = append(undo, snap(st))
				restore(st, snap(s))
				res = []string{"Loaded."}
			}
		default:
			res = []string{mUnk}
		}
		out = append(out, res...)
	}
	return strings.Join(out, "\n")
}

// Adventure runs a script against a world description and returns the transcript.
func Adventure(worldText, script string) (res string) {
	defer func() {
		if r := recover(); r != nil {
			if e, ok := r.(worldErr); ok {
				res = e.msg
				return
			}
			panic(r)
		}
	}()
	return run(worldText, script)
}
'''

RB = r'''
require 'set'

module Adventure
  DIRS = @DIRS@
  SHOW = @SHOW@
  HAS_ITEMS = @ITEMS@
  HAS_LOCKS = @LOCKS@
  HAS_DARK = @DARK@
  HAS_UNDO = @UNDO@
  HANDS = @HANDS@
  M_NOWAY = @M_NOWAY@
  M_LOCKED = @M_LOCKED@
  M_NOITEM = @M_NOITEM@
  M_NOHAVE = @M_NOHAVE@
  M_FULL = @M_FULL@
  M_DARK = @M_DARK@
  M_DARKTAKE = @M_DARKTAKE@
  M_UNKNOWN = @M_UNKNOWN@
  M_TAKEN = @M_TAKEN@
  M_DROPPED = @M_DROPPED@
  LOW = 'abcdefghijklmnopqrstuvwxyz'
  DG = '0123456789'

  class Err < StandardError; end

  def self.good_id?(s)
    return false if s.length < 1 || s.length > 10 || !LOW.include?(s[0])
    s.each_char { |c| return false unless (LOW + DG + '_').include?(c) }
    true
  end

  def self.good_text?(s, mx)
    return false if s.length < 1 || s.length > mx || s[0] == ' ' || s[-1] == ' '
    s.each_char { |c| return false if c < ' ' || c > '~' }
    true
  end

  def self.good_num?(s)
    return false if s.length < 1 || s.length > 3
    s.each_char { |c| return false unless DG.include?(c) }
    s.length == 1 || s[0] != '0'
  end

  def self.directives
    d = { 'room' => %w[id text40], 'desc' => %w[id text120], 'exit' => %w[id dir id], 'start' => %w[id] }
    d['item'] = %w[id id text40] if HAS_ITEMS
    d['lock'] = %w[id dir id] if HAS_LOCKS
    if HAS_DARK
      d['dark'] = %w[id]
      d['light'] = %w[id]
      d['value'] = %w[id num]
      d['vault'] = %w[id]
    end
    d
  end

  def self.parse_world(text)
    spec = directives
    w = { rooms: {}, desc: {}, exits: {}, start: nil, items: {}, locks: {}, dark: Set.new, light: Set.new, value: {}, vault: Set.new }
    refs = []
    seen_start = false
    text.split("\n", -1).each_with_index do |line, ln|
      n = ln + 1
      next if line.empty?
      kw = line.split(/ /, 2)[0]
      raise Err, "error: world line #{n}: syntax" unless spec.key?(kw)
      kinds = spec[kw]
      parts = kinds[-1].start_with?('text') ? line.split(/ /, kinds.length + 1) : line.split(/ /, -1)
      raise Err, "error: world line #{n}: syntax" if parts.length != 1 + kinds.length
      args = parts[1..-1]
      kinds.each_with_index do |kind, i|
        a = args[i]
        raise Err, "error: world line #{n}: id" if kind == 'id' && !good_id?(a)
        raise Err, "error: world line #{n}: syntax" if kind == 'dir' && !DIRS.include?(a)
        raise Err, "error: world line #{n}: syntax" if kind == 'num' && !good_num?(a)
        raise Err, "error: world line #{n}: syntax" if kind.start_with?('text') && !good_text?(a, kind[4..-1].to_i)
      end
      dup = false
      r = []
      case kw
      when 'room'
        dup = w[:rooms].key?(args[0])
        w[:rooms][args[0]] = args[1]
      when 'desc'
        dup = w[:desc].key?(args[0])
        w[:desc][args[0]] = args[1]
        r = [['room', args[0]]]
      when 'exit'
        k = "#{args[0]} #{args[1]}"
        dup = w[:exits].key?(k)
        w[:exits][k] = args[2]
        r = [['room', args[0]], ['room', args[2]]]
      when 'start'
        dup = seen_start
        seen_start = true
        w[:start] = args[0]
        r = [['room', args[0]]]
      when 'item'
        dup = w[:items].key?(args[0])
        w[:items][args[0]] = [args[1], args[2]]
        r = [['room', args[1]]]
      when 'lock'
        k = "#{args[0]} #{args[1]}"
        dup = w[:locks].key?(k)
        w[:locks][k] = args[2]
        r = [['exit', k], ['item', args[2]]]
      when 'dark'
        dup = w[:dark].include?(args[0])
        w[:dark].add(args[0])
        r = [['room', args[0]]]
      when 'light'
        dup = w[:light].include?(args[0])
        w[:light].add(args[0])
        r = [['item', args[0]]]
      when 'value'
        dup = w[:value].key?(args[0])
        w[:value][args[0]] = args[1].to_i
        r = [['item', args[0]]]
      when 'vault'
        dup = w[:vault].include?(args[0])
        w[:vault].add(args[0])
        r = [['room', args[0]]]
      end
      raise Err, "error: world line #{n}: duplicate" if dup
      refs << [n, r]
    end
    refs.each do |n, r|
      r.each do |ref|
        raise Err, "error: world line #{n}: unknown" if ref[0] == 'room' && !w[:rooms].key?(ref[1])
        raise Err, "error: world line #{n}: unknown" if ref[0] == 'item' && !w[:items].key?(ref[1])
        raise Err, "error: world line #{n}: unknown" if ref[0] == 'exit' && !w[:exits].key?(ref[1])
      end
    end
    raise Err, 'error: world: no start' if w[:start].nil?
    w
  end

  def self.lit_room?(w, st)
    return true unless HAS_DARK
    !w[:dark].include?(st[:loc]) || st[:inv].any? { |i| w[:light].include?(i) }
  end

  def self.view(w, st)
    return [M_DARK] unless lit_room?(w, st)
    loc = st[:loc]
    out = ["== #{w[:rooms][loc]} =="]
    out << w[:desc][loc] if w[:desc].key?(loc)
    ex = SHOW.select { |d| w[:exits].key?("#{loc} #{d}") }
    out << ('Exits: ' + (ex.empty? ? 'none' : ex.join(', ')))
    here = st[:here][loc]
    out << ('Items: ' + here.to_a.sort.join(', ')) if HAS_ITEMS && !here.empty?
    out
  end

  def self.snap(st)
    here = {}
    st[:here].each { |k, v| here[k] = v.dup }
    { loc: st[:loc], inv: st[:inv].dup, here: here, turns: st[:turns] }
  end

  def self.adventure(world, script)
    begin
      w = parse_world(world)
    rescue Err => e
      return e.message
    end
    st = { loc: w[:start], inv: Set.new, here: {}, turns: 0 }
    w[:rooms].each_key { |r| st[:here][r] = Set.new }
    w[:items].each { |name, (room, _)| st[:here][room].add(name) }
    undo = []
    saves = {}
    out = []
    script.split("\n", -1).each do |cmd|
      next if cmd.empty?
      out << "> #{cmd}"
      ws = cmd.split(/ /, -1)
      v = ws[0]
      res = nil
      if v == 'look' && ws.length == 1
        res = view(w, st)
      elsif v == 'go' && ws.length == 2 && DIRS.include?(ws[1])
        key = "#{st[:loc]} #{ws[1]}"
        tgt = w[:exits][key]
        if tgt.nil?
          res = [M_NOWAY]
        elsif HAS_LOCKS && w[:locks].key?(key) && !st[:inv].include?(w[:locks][key])
          res = [M_LOCKED]
        else
          undo << snap(st)
          st[:loc] = tgt
          st[:turns] += 1
          res = view(w, st)
        end
      elsif HAS_ITEMS && v == 'take' && ws.length == 2
        if !lit_room?(w, st)
          res = [M_DARKTAKE]
        elsif !st[:here][st[:loc]].include?(ws[1])
          res = [M_NOITEM.gsub('{X}') { ws[1] }]
        elsif st[:inv].size >= HANDS
          res = [M_FULL]
        else
          undo << snap(st)
          st[:here][st[:loc]].delete(ws[1])
          st[:inv].add(ws[1])
          res = [M_TAKEN]
        end
      elsif HAS_ITEMS && v == 'drop' && ws.length == 2
        if !st[:inv].include?(ws[1])
          res = [M_NOHAVE.gsub('{X}') { ws[1] }]
        else
          undo << snap(st)
          st[:inv].delete(ws[1])
          st[:here][st[:loc]].add(ws[1])
          res = [M_DROPPED]
        end
      elsif HAS_ITEMS && v == 'examine' && ws.length == 2
        if st[:inv].include?(ws[1]) || (lit_room?(w, st) && st[:here][st[:loc]].include?(ws[1]))
          res = [w[:items][ws[1]][1]]
        else
          res = [M_NOITEM.gsub('{X}') { ws[1] }]
        end
      elsif HAS_ITEMS && v == 'inv' && ws.length == 1
        res = st[:inv].empty? ? ['You carry nothing.'] : ['You carry: ' + st[:inv].to_a.sort.join(', ')]
      elsif HAS_DARK && v == 'score' && ws.length == 1
        tot = 0
        w[:vault].each { |r| st[:here][r].each { |i| tot += w[:value][i] || 0 } }
        res = ["Score: #{tot}"]
      elsif HAS_UNDO && v == 'undo' && ws.length == 1
        if undo.empty?
          res = ['Nothing to undo.']
        else
          s = undo.pop
          st.merge!(s)
          res = ['Undone.']
        end
      elsif HAS_UNDO && v == 'turns' && ws.length == 1
        res = ["Turns: #{st[:turns]}"]
      elsif HAS_UNDO && v == 'save' && ws.length == 2 && good_id?(ws[1])
        saves[ws[1]] = snap(st)
        res = ['Saved.']
      elsif HAS_UNDO && v == 'load' && ws.length == 2 && good_id?(ws[1])
        if !saves.key?(ws[1])
          res = ['No such save.']
        else
          undo << snap(st)
          st.merge!(snap(saves[ws[1]]))
          res = ['Loaded.']
        end
      else
        res = [M_UNKNOWN]
      end
      out.concat(res)
    end
    out.join("\n")
  end
end
'''



DIR6 = ["north", "south", "east", "west", "up", "down"]
OPP = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up"}
ROOMS = [("gate", "Gatehouse"), ("shed", "Boat Shed"), ("market", "Fish Market"), ("lamp", "Lamp Room"), ("cellar", "Wet Cellar"), ("stair", "Spiral Stair"), ("gallery", "Lantern Gallery"), ("pier", "Old Pier"),
         ("store", "Salt Store"), ("office", "Harbour Office"), ("yard", "Rope Yard"), ("cave", "Sea Cave")]
DESCS = ["A draughty room that smells of tar.", "Nets hang from every beam.", "Water drips somewhere in the dark.", "Gulls scream outside the window.", "A long table stands here, scarred by knives.", "The floor is covered in sand."]
ITEMS = [("lamp", "a brass lamp"), ("key", "an iron key"), ("rope", "a coil of rope"), ("coin", "a silver coin"), ("map", "a damp map"), ("shell", "a spiral shell"), ("flask", "a leather flask"), ("bell", "a small bell"), ("pearl", "a grey pearl")]
MSG = {
    "noway": ["You can't go that way.", "There is no exit that way.", "Nothing but wall that way."],
    "locked": ["The door is locked.", "It is locked, and you lack the key.", "A lock bars the way."],
    "noitem": ["You see no {X} here.", "There is no {X} here.", "No {X} in sight."],
    "nohave": ["You have no {X}.", "You aren't carrying {X}.", "No {X} in your pack."],
    "full": ["Your hands are full.", "You cannot carry more.", "Too much to carry."],
    "dark": ["It is dark.", "Pitch black.", "You see nothing in the dark."],
    "darktake": ["It is too dark to find anything.", "You fumble in the dark.", "Too dark to reach for anything."],
    "unknown": ["I don't understand.", "Pardon?", "That means nothing here."],
    "taken": ["Taken.", "Done.", "You pick it up."],
    "dropped": ["Dropped.", "Done.", "You put it down."],
}
THEMES = ["a lighthouse keeper's rounds", "a night at the fish market", "the harbour office after hours", "a walk through the old salt store", "the boatyard at dusk"]
JUNK = ["dance", "LOOK", "look around", "go", "go up now", "take", "take lamp key", "drop", "inventory", "n", "go North", "  look", "look ", "examine", "save", "save Bad!", "load", "load x y", "go  north", "undo now", "turns 1", "score please", ""]


def params(rng, level, i):
    nd = 4 if level < 3 else 6
    dirs = DIR6[:nd]
    return {
        "level": level, "dirs": dirs, "show": rng.sample(dirs, nd), "items": level >= 2, "locks": level >= 3, "dark": level >= 4, "undo": level >= 5, "hands": rng.choice([2, 3, 4]),
        "msg": {k: rng.choice(v) for k, v in MSG.items()}, "theme": THEMES[(i + rng.randrange(2)) % len(THEMES)],
    }


def sol(lang, p):
    src = {"python": PY, "javascript": JS, "java": JV, "go": GO, "ruby": RB}[lang]
    L = lambda s: K.lit(lang, s)  # noqa: E731
    b = (lambda v: "True" if v else "False") if lang == "python" else (lambda v: "true" if v else "false")  # noqa: E731
    arr = lambda xs: ("[" + ", ".join(L(x) for x in xs) + "]") if lang in ("python", "javascript", "ruby") else ("{" + ", ".join(L(x) for x in xs) + "}")  # noqa: E731
    m = p["msg"]
    return K.subst(
        src, DIRS=arr(p["dirs"]), SHOW=arr(p["show"]), ITEMS=b(p["items"]), LOCKS=b(p["locks"]), DARK=b(p["dark"]), UNDO=b(p["undo"]), HANDS=p["hands"],
        M_NOWAY=L(m["noway"]), M_LOCKED=L(m["locked"]), M_NOITEM=L(m["noitem"]), M_NOHAVE=L(m["nohave"]), M_FULL=L(m["full"]), M_DARK=L(m["dark"]), M_DARKTAKE=L(m["darktake"]), M_UNKNOWN=L(m["unknown"]),
        M_TAKEN=L(m["taken"]), M_DROPPED=L(m["dropped"]),
    ).lstrip("\n")


def make_world(rng, p, nrooms, shuffle=False):
    dirs = p["dirs"]
    rooms = rng.sample(ROOMS, nrooms)
    exits = {}
    placed = [rooms[0]]
    for r in rooms[1:]:
        for _ in range(40):
            a = rng.choice(placed)
            d = rng.choice(dirs)
            if (a[0], d) not in exits and (r[0], OPP[d]) not in exits:
                exits[(a[0], d)] = r[0]
                exits[(r[0], OPP[d])] = a[0]
                break
        placed.append(r)
    for _ in range(rng.randint(0, 3)):
        a, b = rng.choice(rooms)[0], rng.choice(rooms)[0]
        d = rng.choice(dirs)
        if (a, d) not in exits:
            exits[(a, d)] = b
    lines = []
    lines += [f"room {rid} {title}" for rid, title in rooms]
    for rid, _ in rooms:
        if rng.random() < 0.6:
            lines.append(f"desc {rid} {rng.choice(DESCS)}")
    lines += [f"exit {a} {d} {b}" for (a, d), b in exits.items()]
    items = []
    if p["items"]:
        required = ([ITEMS[0]] if p["dark"] else []) + ([ITEMS[1]] if p["locks"] else [])
        others = rng.sample([i for i in ITEMS if i not in required], rng.randint(3, 5))
        items = required + others
        rng.shuffle(items)
        for name, text in items:
            lines.append(f"item {name} {rng.choice(rooms)[0]} {text}")
    if p["locks"]:
        names = [i[0] for i in items]
        for (a, d) in rng.sample(sorted(exits), min(len(exits), rng.randint(1, 2))):
            lines.append(f"lock {a} {d} {rng.choice(names)}")
    if p["dark"]:
        for rid, _ in rng.sample(rooms, rng.randint(1, 2)):
            lines.append(f"dark {rid}")
        lines.append("light lamp")
        for name, _ in items:
            if rng.random() < 0.7:
                lines.append(f"value {name} {rng.choice([1, 5, 10, 25, 100, 999])}")
        for rid, _ in rng.sample(rooms, rng.randint(1, 2)):
            lines.append(f"vault {rid}")
    lines.append(f"start {rooms[0][0]}")
    if shuffle:
        rng.shuffle(lines)
    return "\n".join(lines) + ("\n" if rng.random() < 0.3 else "")


def rand_script(rng, p, ns, world, n):
    W = ns["parse_world"](world)
    g = ns["Game"](W)
    cmds = []
    dirs = p["dirs"]
    names = sorted(W["items"]) or ["lamp"]
    for _ in range(n):
        st = g.st
        loc = st["loc"]
        r = rng.random()
        here = sorted(st["here"][loc])
        exits_here = [d for d in dirs if (loc, d) in W["exits"]]
        if r < 0.33 and exits_here:
            cmd = "go " + rng.choice(exits_here)
        elif r < 0.39:
            cmd = "go " + rng.choice(dirs)
        elif r < 0.45:
            cmd = "look"
        elif p["items"] and r < 0.58 and here:
            cmd = "take " + rng.choice(here)
        elif p["items"] and r < 0.63 and st["inv"]:
            cmd = "drop " + rng.choice(sorted(st["inv"]))
        elif p["items"] and r < 0.68:
            cmd = "examine " + rng.choice(names)
        elif p["items"] and r < 0.71:
            cmd = "inv"
        elif p["dark"] and r < 0.75:
            cmd = "score"
        elif p["undo"] and r < 0.84:
            cmd = rng.choice(["undo", "undo", "turns", "save s" + str(rng.randint(1, 2)), "load s" + str(rng.randint(1, 3))])
        elif r < 0.9:
            cmd = rng.choice(JUNK)
        elif p["items"]:
            cmd = rng.choice(["take ", "drop "]) + rng.choice(names + ["ghost"])
        else:
            cmd = "look"
        g.do(cmd) if cmd else None
        cmds.append(cmd)
    return "\n".join(cmds) + ("\n" if rng.random() < 0.3 else "")


def make_cases(rng, p, ns):
    cases = []
    L = p["level"]

    def add(w, s):
        cases.append((w, s))

    tiny = "room a Hall\nroom b Yard\nexit a north b\nexit b south a\nstart a\n"
    # worlds with random scripts
    for k in range(5):
        w = make_world(rng, p, rng.randint(3, 8), shuffle=(k % 2 == 1 and L >= 3))
        for _ in range(7 if L >= 3 else 9):
            add(w, rand_script(rng, p, ns, w, rng.randint(6, 26)))
    # tiny world basics
    for s in ["", "\n", "look", "look\n", "go north\nlook", "go south", "go east", "go north\ngo south\ngo north\ngo south", "go up", "go down", "GO north", "go North", "go", "go north east", "look\n\nlook", "\nlook\n\n", " look", "look "]:
        add(tiny, s)
    # world errors
    base = ["room a Hall", "room b Yard", "exit a north b", "exit b south a", "start a"]
    if p["items"]:
        base.insert(2, "item lamp a a brass lamp")
    bad = []
    bad += [["foo a"], ["ROOM a x"], [""], ["room"], ["room a"], ["room a "], ["room a  x"], ["room a x "], ["room Bad x"], ["room 1a x"], ["room a_b x"], ["room abcdefghijk x"], ["room abcdefghij x"], ["room a " + "t" * 40], ["room a " + "t" * 41], ["room a t\tx"],
            ["room a x", "room a y"], ["desc a"], ["desc a x"], ["room a x", "desc a"], ["room a x", "desc a  y"], ["room a x", "desc a y", "desc a z"], ["room a x", "desc a " + "d" * 120, "start a"], ["room a x", "desc a " + "d" * 121, "start a"],
            ["room a x", "exit a north"], ["room a x", "exit a north a extra"], ["room a x", "exit a upward a"], ["room a x", "exit a North a"], ["room a x", "exit a north a", "exit a north a", "start a"], ["room a x", "exit a north b", "start a"], ["room a x", "exit b north a", "start a"],
            ["room a x", "exit a north a", "start a"], ["room a x", "start"], ["room a x", "start a", "start a"], ["room a x", "start b"], ["room a x"], ["start a"], [], ["", "", ""], ["room a x", "", "foo", "start a"], ["room a x", "start a", "start b", "room b y"],
            ["exit a north b", "room a x", "room b y", "start a"], ["start a", "room a x"], ["room a x", "exit a north b", "room b y", "start a"], ["room a x", "exit a north b", "foo", "start a"], ["room a x", "desc zz y", "foo", "start a"], ["room a x", "desc zz y", "start a"],
            ["room a x", "start a", "desc zz y", "exit a north yy"], ["room a x", "exit a up a", "start a"], ["room a x", "exit a down a", "start a"], ["room a x", "exit a west a", "start a"], ["room a x", "exit a south a", "start a", "exit a south a"],
            ["room a x", "start a", "exit a north a extra words"], ["room a x", "start a ", ], ["room a x", " start a"], ["room a x", "start  a"], ["room a x", "start A"], ["room a x", "exit a north A", "start a"]]
    if p["items"]:
        bad += [["room a x", "item"], ["room a x", "item k a"], ["room a x", "item k a "], ["room a x", "item k a t", "start a"], ["room a x", "item k b t", "start a"], ["room a x", "item k a t", "item k a u", "start a"], ["room a x", "item K a t", "start a"],
                ["room a x", "item k a  t", "start a"], ["room a x", "item k a t ", "start a"], ["room a x", "item k a " + "t" * 41, "start a"], ["room a x", "item k a " + "t" * 40, "start a"], ["room a x", "item a k t", "start a"], ["room a x", "item k a two words here", "start a"],
                ["room a x", "item k a t", "item j zz u", "start a"], ["room a x", "item k zz t", "item j a u", "item j a v", "start a"]]
    else:
        bad += [["room a x", "item k a t", "start a"], ["room a x", "lock a north k", "start a"], ["room a x", "dark a", "start a"]]
    if p["locks"]:
        bad += [["room a x", "exit a north a", "lock a north k", "item k a t", "start a"], ["room a x", "item k a t", "exit a north a", "lock a north k", "start a"], ["room a x", "item k a t", "exit a north a", "lock a north k", "lock a north k", "start a"],
                ["room a x", "item k a t", "lock a north k", "start a"], ["room a x", "item k a t", "exit a north a", "lock a north zz", "start a"], ["room a x", "item k a t", "exit a north a", "lock zz north k", "start a"], ["room a x", "item k a t", "exit a north a", "lock a up k", "start a"],
                ["room a x", "item k a t", "exit a north a", "lock a north", "start a"], ["room a x", "item k a t", "exit a north a", "lock a north k extra", "start a"], ["room a x", "item k a t", "exit a north a", "lock a nowhere k", "start a"], ["room a x", "item k a t", "exit a north a", "lock a north K", "start a"],
                ["room a x", "item k a t", "exit a north a", "exit a east a", "lock a north k", "lock a east k", "start a"]]
    if p["dark"]:
        bad += [["room a x", "dark a", "start a"], ["room a x", "dark a", "dark a", "start a"], ["room a x", "dark b", "start a"], ["room a x", "dark", "start a"], ["room a x", "dark a b", "start a"], ["room a x", "item l a t", "light l", "start a"], ["room a x", "item l a t", "light l", "light l", "start a"],
                ["room a x", "light l", "start a"], ["room a x", "item l a t", "value l 5", "start a"], ["room a x", "item l a t", "value l 0", "start a"], ["room a x", "item l a t", "value l 1000", "start a"], ["room a x", "item l a t", "value l 05", "start a"], ["room a x", "item l a t", "value l -5", "start a"],
                ["room a x", "item l a t", "value l 999", "value l 5", "start a"], ["room a x", "item l a t", "value l", "start a"], ["room a x", "item l a t", "value l 5 5", "start a"], ["room a x", "item l a t", "value l x", "start a"], ["room a x", "vault a", "start a"], ["room a x", "vault a", "vault a", "start a"],
                ["room a x", "vault b", "start a"], ["room a x", "item l a t", "value zz 5", "start a"], ["room a x", "item l a t", "light zz", "start a"]]
    else:
        bad += [["room a x", "light l", "start a"], ["room a x", "vault a", "start a"], ["room a x", "value l 5", "start a"]]
    for lines in bad:
        add("\n".join(lines) + ("\n" if rng.random() < 0.3 else ""), "look")
        if rng.random() < 0.25:
            add("\n".join(lines), "")
    # scripted scenarios on the tiny world and on a fixed richer world
    if p["items"]:
        w2 = "room a Hall\nroom b Yard\nroom c Shed\nexit a north b\nexit b south a\nexit b east c\nexit c west b\nstart a\nitem lamp a a brass lamp\nitem key b an iron key\nitem rope c a coil of rope\nitem coin c a silver coin\nitem map a a damp map\nitem bell a a small bell\n"
        if p["locks"]:
            w2 += "lock b east key\n"
        if p["dark"]:
            w2 += "dark c\nlight lamp\nvalue coin 25\nvalue rope 5\nvalue bell 10\nvault a\n"
        for s in ["look\ntake lamp\ntake map\ntake bell\ntake key\ninv\nlook", "take lamp\ntake lamp\ndrop lamp\ndrop lamp\ninv\nlook", "examine lamp\nexamine key\ntake lamp\nexamine lamp\nexamine map\nexamine ghost\nexamine", "go north\nlook\ngo east\ngo south\ntake lamp\ngo north\ntake key\ngo east\nlook\ntake coin\ntake rope\ninv",
                  "take lamp\ngo north\ntake key\ngo east\ntake coin\ntake rope\ngo west\ngo south\ndrop coin\ndrop rope\nscore\ndrop lamp\nscore\ninv", "go north\ngo east\nlook\ntake coin\ngo west\ntake key\ngo east\ntake coin", "inv", "inv\ntake", "take lamp\nexamine", "drop", "take map\ndrop map\ntake map\ndrop map\nlook",
                  "take lamp\ntake map\ntake bell", "take lamp\ndrop lamp\nlook\nlook\ninv"]:
            add(w2, s)
        if p["undo"]:
            for s in ["undo", "take lamp\nundo\nundo\nlook", "go north\ngo south\nundo\nundo\nundo\nturns", "save a\ngo north\nturns\nload a\nturns\nundo\nturns\nundo", "load a", "save a\nload b", "save a\ntake lamp\nsave a\ntake map\nload a\ninv\nload a\ninv\nundo\ninv", "go north\nsave x\ngo south\nload x\nlook\nturns\nundo\nlook",
                      "take lamp\ngo north\ndrop lamp\nundo\nundo\ninv\nlook\nundo\nundo\nundo\nundo", "save\nload\nsave Bad\nload Bad\nsave a b\nundo extra\nturns now", "go north\nundo\ngo south\nundo\nlook", "take lamp\nsave one\ndrop lamp\nload one\nundo\ninv"]:
                add(w2, s)
    # examples first
    ex = []
    ex.append(("room hall Entrance Hall\ndesc hall A cold hall with a dusty floor.\nroom yard Back Yard\nexit hall north yard\nexit yard south hall\nstart hall", "look\ngo north\ngo north\nlook"))
    if p["items"]:
        ex.append(("room hall Entrance Hall\nroom yard Back Yard\nexit hall north yard\nexit yard south hall\nstart hall\nitem lamp hall a brass lamp\nitem rope yard a coil of rope", "take lamp\nexamine lamp\ngo north\nlook\ntake rope\ninv\ndrop lamp"))
    if p["locks"]:
        ex.append(("room hall Entrance Hall\nroom vault Vault\nexit hall east vault\nexit vault west hall\nitem key hall an iron key\nlock hall east key\nstart hall", "go east\ntake key\ngo east\ndrop key\ngo west\ngo east"))
    if p["dark"]:
        ex.append(("room hall Entrance Hall\nroom cave Cave\nexit hall down cave\nexit cave up hall\nitem lamp hall a brass lamp\nitem coin cave a silver coin\nlight lamp\ndark cave\nvault hall\nvalue coin 25\nstart hall", "go down\nlook\ngo up\ntake lamp\ngo down\nlook\ntake coin\ngo up\ndrop coin\nscore"))
    if p["undo"]:
        ex.append(("room hall Entrance Hall\nroom yard Back Yard\nexit hall north yard\nexit yard south hall\nstart hall", "save here\ngo north\nturns\nundo\nlook\ngo north\nload here\nturns\nundo\nturns\nundo"))
    nex = len(ex)
    out, seen = [], set()
    for c in ex + cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex


def readme(p, api, lang, examples):
    m = p["msg"]
    X = [f"# Text adventure engine: {p['theme']}", ""]
    X.append(f"`adventure(world, script)` builds a small world from a description, plays a script of commands on it and returns the transcript. The world is the setting of {p['theme']}.")
    X.append("")
    X.append("## The world description")
    X.append("")
    X.append("`world` is text made of lines separated by `\\n`. Empty lines are ignored (but they count when line numbers are reported). Every other line is one directive: a keyword and its arguments separated by **single spaces**:")
    X.append("")
    X.append("    room ID TITLE          a room")
    X.append("    desc ID TEXT           the description shown in that room (optional, at most once per room)")
    X.append("    exit ID DIR TARGET     a one-way exit from room ID in direction DIR to room TARGET")
    X.append("    start ID               the room where the player begins (exactly one)")
    if p["items"]:
        X.append("    item NAME ROOM TEXT    an item that starts out lying in ROOM; TEXT is what `examine` shows")
    if p["locks"]:
        X.append("    lock ROOM DIR KEY      the exit DIR of ROOM can only be used while the player carries the item KEY")
    if p["dark"]:
        X.append("    dark ID                the room is dark")
        X.append("    light NAME             this item is a light source")
        X.append("    value NAME N           the item is worth N points")
        X.append("    vault ID               items lying in this room score")
    X.append("")
    X.append("* `ID` and item `NAME`: 1 to 10 characters, a lower-case ASCII letter followed by lower-case letters, digits or `_`.")
    X.append("* `DIR` is one of " + ", ".join(f"`{d}`" for d in p["dirs"]) + ".")
    X.append("* `TITLE` and `TEXT` are the **rest of the line** after the arguments before them: " + ("`TITLE` and item `TEXT` are 1 to 40 characters, `desc` text 1 to 120" if p["items"] else "`TITLE` is 1 to 40 characters, `desc` text 1 to 120") + ", printable ASCII (space to `~`), and neither starts nor ends with a space.")
    if p["dark"]:
        X.append("* `N` is a decimal number from 1 to 999 without leading zeros.")
    X.append("")
    X.append("A world error stops everything: the result is just the error text, with no transcript. Errors are found in three passes:")
    X.append("")
    X.append("1. line by line, the first line with `error: world line N: WHY`: `syntax` (unknown keyword, wrong number of words, a `DIR` that is not in the list, a `TITLE`/`TEXT`/number that breaks its rule), then `id` (an `ID` or `NAME` that is not valid; checked left to right in the line, together with the other word checks), then `duplicate` (see below).")
    dup = ["a room defined twice", "a second `desc` for a room", "the same `ID` and `DIR` in two `exit` lines", "a second `start`"]
    if p["items"]:
        dup.append("an item name used twice")
    if p["locks"]:
        dup.append("two `lock` lines for the same `ROOM` and `DIR`")
    if p["dark"]:
        dup.append("a second `dark`, `light`, `value` or `vault` for the same room or item")
    X.append("   `duplicate` is reported for: " + "; ".join(dup) + ".")
    refs = "every `ID` that names a room must be defined by a `room` line anywhere in the text" + (", every item `NAME` by an `item` line" if p["items"] else "") + (", and a `lock` must name an existing `exit`" if p["locks"] else "")
    X.append("2. then, if pass 1 found nothing, in line order, the first line that refers to something that does not exist is `error: world line N: unknown`: " + refs + ".")
    X.append("3. finally `error: world: no start` if there is no `start` line.")
    X.append("")
    X.append("## Playing")
    X.append("")
    X.append("`script` is text made of lines separated by `\\n`; empty lines are skipped. Each other line is a command, case-sensitive, words separated by single spaces. The player starts in the `start` room" + (" carrying nothing and may carry at most " + str(p["hands"]) + " items" if p["items"] else "") + ". The transcript has, for every command, the line `> ` followed by the command text exactly as written, then the response lines. Lines are joined with `\\n` and there is no trailing newline (an empty script gives the empty text).")
    X.append("")
    cmds = [("look", "shows the room (see below)"), ("go DIR", "moves through the exit and shows the new room")]
    if p["items"]:
        cmds += [("take NAME", "picks an item up from the room"), ("drop NAME", "puts a carried item down in the room"), ("examine NAME", "shows the item's `TEXT`; works for a carried item, or for an item lying in the room (not when the room is dark)"), ("inv", "lists what the player carries")]
    if p["dark"]:
        cmds.append(("score", "shows the score"))
    if p["undo"]:
        cmds += [("undo", "takes back the last state change"), ("turns", "shows the move count"), ("save NAME", "remembers the current state under a name"), ("load NAME", "goes back to a saved state")]
    X.append("| command | effect |")
    X.append("|---|---|")
    for c, e in cmds:
        X.append(f"| `{c}` | {e} |")
    X.append("")
    X.append("A command with the wrong number of words (or with a `DIR` that is not in the list, or a `save`/`load` name that is not a valid `ID`) is not understood, and so is any other text: the response is the single line `" + m["unknown"] + "`.")
    X.append("")
    X.append("**Room view** (the response of `look`, and of a successful `go`):")
    X.append("")
    X.append("```")
    X.append("== TITLE ==")
    X.append("TEXT of the desc line      (only if the room has one)")
    X.append("Exits: " + ", ".join(p["show"][:3]) + "      (the room's exits in this fixed order: " + ", ".join(p["show"]) + "; `Exits: none` if there are none)")
    if p["items"]:
        X.append("Items: a, b                (items lying here, ascending byte order; the line is left out if there are none)")
    X.append("```")
    X.append("")
    X.append(f"`go DIR`: if the room has no exit that way the response is `{m['noway']}`." + (f" If the exit is locked and the player does not carry its key it is `{m['locked']}` (nothing changes); the key is not used up." if p["locks"] else "") + " Otherwise the player moves and gets the room view of the new room.")
    if p["items"]:
        X.append("")
        X.append(f"`take NAME`, checked in this order: " + (f"if the room is dark and the player carries no light source: `{m['darktake']}`; " if p["dark"] else "") + f"if the item is not lying in this room: `{m['noitem']}` (`{{X}}` is replaced by the name as typed, whatever it is); "
                 f"if the player already carries {p['hands']} items: `{m['full']}`; otherwise the item moves to the player and the response is `{m['taken']}`. "
                 f"`drop NAME`: if the player does not carry it `{m['nohave']}` (again with `{{X}}` replaced), otherwise it is left in the current room and the response is `{m['dropped']}`. "
                 f"`examine NAME` with an item that is neither carried nor visible: `{m['noitem']}`. `inv`: `You carry: a, b` (ascending byte order) or `You carry nothing.`")
    if p["dark"]:
        X.append("")
        X.append(f"**Darkness.** A dark room is *lit* when the player carries at least one light source (any item named by a `light` line); in a dark room that is not lit the room view is the single line `{m['dark']}` (for `look` and after `go`). Moving is still allowed. "
                 "`score` responds `Score: N`, where `N` is the sum of the `value`s of all items currently lying in the rooms named by `vault` lines (an item without a `value` counts 0).")
    if p["undo"]:
        X.append("")
        X.append("**State, undo and saves.** The state is the player's room, the carried items, where every item lies, and the move count (the number of successful `go` commands). Every *successful* `go`, `take`, `drop` and `load` first remembers the state before it, on a stack. "
                 "`undo` pops that stack and restores the state (`Undone.`); with an empty stack it responds `Nothing to undo.` and nothing else happens. `turns` responds `Turns: N`. `save NAME` stores the current state under NAME (overwriting an older save) and responds `Saved.`; "
                 "`load NAME` responds `No such save.` if there is none, otherwise it remembers the current state on the undo stack, restores the saved one and responds `Loaded.` (the save itself stays). Failed commands, `look`, `inv`, `score`, `turns`, `save` and `undo` do not touch the stack.")
    X.append("")
    X.append(K.interface_section(api, lang))
    X.append("## Examples")
    X.append("")
    for k, ((w, s), out) in enumerate(examples):
        X.append(f"**Example {k + 1}**")
        X.append("")
        X.append("```")
        X.append("world:")
        X += ["  " + ln for ln in w.rstrip("\n").split("\n")]
        X.append("script:")
        X += ["  " + ln for ln in s.split("\n")]
        X.append("result:")
        X += ["  " + ln for ln in out.split("\n")]
        X.append("```")
        X.append("")
    X.append(K.run_hint(lang, api.mod))
    return "\n".join(X) + "\n"


def prompt(rng, p, api, lang):
    where = api.short(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    feats = ["rooms and exits"] + (["items"] if p["items"] else []) + (["locked doors"] if p["locks"] else []) + (["darkness and scoring"] if p["dark"] else []) + (["undo and saves"] if p["undo"] else [])
    fl = ", ".join(feats[:-1]) + (" and " if len(feats) > 1 else "") + feats[-1]
    opts = [
        f"Write the text-adventure engine from README.md in {ln}: `{fn}(world, script)` in {where} parses a world description, runs a command script and returns the transcript ({fl}). {K.closer(rng)}",
        f"Implement `{fn}` ({ln}, {where}) as specified in README.md. The world format has strict error rules (three passes) and the transcript format is exact. This version has {fl}. {K.closer(rng)}",
        f"{ln} task: a tiny adventure-game interpreter. `{fn}` in {where}; README.md defines the world file, the commands and every message. Features: {fl}.",
        f"Please build the adventure engine described in README.md ({ln}, `{fn}`, {where}). It supports {fl}. Hidden checks include malformed worlds and odd commands.",
    ]
    return rng.choice(opts).strip()


LANG_PLAN = ["javascript", "ruby", "java", "go", "ruby", "java", "go", "javascript"]
LEVELS = [1, 1, 2, 2, 3, 4, 5, 5]


@family("greenfield-adventure", category="greenfield", lang="mixed", kind="greenfield", n=8,
        summary="text-adventure interpreter: world-file parser with three-pass error reporting, movement, items, locked doors, darkness and scoring, undo and saves; exact transcripts")
def gen(rng, n):
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = LEVELS[i % len(LEVELS)]
        p = params(rng, level, i)
        api = K.Api(mod="adventure", fn="adventure", args=["world", "script"], arg_docs=["the world description text", "the command script, one command per line"], ret_doc="the transcript, or a world error text", doc="text adventure engine")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["adventure"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=level, slug=f"{i + 1:02d}-{lang}-{len(p['dirs'])}dirs-l{level}", oracle=(None if lang == "python" else ns["adventure"]),
            tags=["interpreter", "game", "parser"], notes={"level": level, "hands": p["hands"]},
        )
