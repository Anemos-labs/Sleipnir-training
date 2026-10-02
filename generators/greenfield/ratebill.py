"""Rate-plan billing: milli-rate pricing, exact sums, rounding modes, wrapping windows, minimum bill, allowance, seasons, demand charge, tax and credit (invented plan language)."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

PY = r'''
MONEY = @MONEY@
L_OTHER = @L_OTHER@
L_TOTAL = @L_TOTAL@
HAS_WINDOW = @WINDOW@
HAS_ALLOW = @ALLOW@
HAS_TAX = @TAX@
LOW = "abcdefghijklmnopqrstuvwxyz"
DG = "0123456789"


class Err(Exception):
    pass


def split_lines(text):
    if text == "":
        return []
    ls = text.split("\n")
    if ls[-1] == "":
        ls.pop()
    return ls


def num(s, lo, hi):
    return 1 <= len(s) <= 7 and all(c in DG for c in s) and (len(s) == 1 or s[0] != "0") and lo <= int(s) <= hi


def parse_time(s):
    if len(s) != 5 or s[2] != ":" or not all(c in DG for c in s[:2] + s[3:]):
        return None
    h, m = int(s[:2]), int(s[3:])
    if h > 23 or m > 59:
        return None
    return h * 60 + m


def parse_plan(text):
    P = {"rate": None, "base": 0, "round": "nearest", "windows": [], "minimum": None, "allow": None, "season": None, "demand": None, "tax": None, "exempt": [], "credit": None}
    seen = set()
    single = ["rate", "base", "round"] + (["minimum"] if HAS_WINDOW else []) + (["allow", "season", "demand"] if HAS_ALLOW else []) + (["tax", "credit"] if HAS_TAX else [])
    multi = (["window"] if HAS_WINDOW else []) + (["exempt"] if HAS_TAX else [])
    exempt_lines = []
    for n, line in enumerate(split_lines(text), 1):
        w = line.split(" ")
        d = w[0]
        if d not in single and d not in multi:
            raise Err("error: plan %d: unknown" % n)
        bad = Err("error: plan %d: argument" % n)
        a = w[1:]
        val = None
        if d == "rate":
            if len(a) != 1 or not num(a[0], 1, 999999):
                raise bad
            val = int(a[0])
        elif d == "base":
            if len(a) != 1 or not num(a[0], 0, 9999999):
                raise bad
            val = int(a[0])
        elif d == "round":
            if len(a) != 1 or a[0] not in ("up", "down", "nearest"):
                raise bad
            val = a[0]
        elif d == "minimum" or d == "demand" or d == "credit":
            if len(a) != 1 or not num(a[0], 1 if d != "minimum" else 0, 9999999):
                raise bad
            val = int(a[0])
        elif d == "tax":
            if len(a) != 1 or not num(a[0], 1, 100):
                raise bad
            val = int(a[0])
        elif d == "allow":
            if len(a) != 2 or not num(a[0], 1, 9999999) or not num(a[1], 0, 999999):
                raise bad
            val = (int(a[0]), int(a[1]))
        elif d == "season":
            if len(a) != 2 or not num(a[1], 1, 500):
                raise bad
            ms = a[0].split(",")
            if not all(num(m, 1, 12) for m in ms) or len(set(ms)) != len(ms):
                raise bad
            val = ([int(m) for m in ms], int(a[1]))
        elif d == "window":
            if len(a) != 3 or not (1 <= len(a[0]) <= 8 and all(c in LOW for c in a[0])) or a[0] == L_OTHER:
                raise bad
            r = a[1].split("-")
            if len(r) != 2 or parse_time(r[0]) is None or parse_time(r[1]) is None or r[0] == r[1] or not num(a[2], 1, 999999):
                raise bad
            val = (a[0], parse_time(r[0]), parse_time(r[1]), int(a[2]))
        elif d == "exempt":
            if len(a) != 1 or not (1 <= len(a[0]) <= 8 and all(c in LOW for c in a[0])):
                raise bad
            val = a[0]
        if d in single:
            if d in seen:
                raise Err("error: plan %d: duplicate" % n)
            seen.add(d)
            P[d] = val
        elif d == "window":
            if any(x[0] == val[0] for x in P["windows"]):
                raise Err("error: plan %d: duplicate" % n)
            mins = minutes(val)
            for x in P["windows"]:
                if mins & minutes(x):
                    raise Err("error: plan %d: overlap" % n)
            P["windows"].append(val)
        else:
            if val in P["exempt"]:
                raise Err("error: plan %d: duplicate" % n)
            P["exempt"].append(val)
            exempt_lines.append((n, val))
    names = {x[0] for x in P["windows"]} | {L_OTHER, "base", "minimum", "demand", "allow"}
    for n, nm in exempt_lines:
        if nm not in names:
            raise Err("error: plan %d: argument" % n)
    if P["rate"] is None:
        raise Err("error: plan: no rate")
    return P


def minutes(w):
    s, e = w[1], w[2]
    return set(range(s, e)) if s < e else set(range(s, 1440)) | set(range(0, e))


def parse_readings(text):
    out = []
    for n, line in enumerate(split_lines(text), 1):
        w = line.split(" ")
        why = None
        if len(w) != 3:
            why = "fields"
        else:
            d = w[0]
            ok = len(d) == 10 and d[4] == "-" and d[7] == "-" and all(c in DG for c in d[:4] + d[5:7] + d[8:])
            if ok:
                mo, da = int(d[5:7]), int(d[8:])
                ok = 1 <= mo <= 12 and 1 <= da <= 31
            if not ok:
                why = "date"
            elif parse_time(w[1]) is None:
                why = "time"
            elif not (1 <= len(w[2]) <= 6 and all(c in DG for c in w[2]) and (len(w[2]) == 1 or w[2][0] != "0")):
                why = "units"
        if why:
            raise Err("error: reading %d: %s" % (n, why))
        out.append((w[0], parse_time(w[1]), int(w[2]), int(w[0][5:7])))
    return out


def rnd(mode, numer, denom):
    if mode == "up":
        return -((-numer) // denom)
    if mode == "down":
        return numer // denom
    return (2 * numer + denom) // (2 * denom)


def money(c):
    if MONEY == "cents":
        return str(c)
    return ("-" if c < 0 else "") + "%d.%02d" % (abs(c) // 100, abs(c) % 100)


def bill(plan, readings):
    try:
        return do_bill(plan, readings)
    except Err as e:
        return str(e)


def do_bill(plan, readings):
    P = parse_plan(plan)
    R = parse_readings(readings)
    order = sorted(range(len(R)), key=lambda i: (R[i][0], R[i][1], i))
    mode = P["round"]
    windows = P["windows"]
    allow_left = P["allow"][0] if P["allow"] else 0
    lines = {}  # label -> [units, rational numerator]
    labels = ["allow"] if P["allow"] else []
    labels += [w[0] for w in windows] + [L_OTHER]
    for lb in labels:
        lines[lb] = [0, 0]
    for i in order:
        date, t, units, month = R[i]
        pct = P["season"][1] if P["season"] and month in P["season"][0] else 100
        name, milli = L_OTHER, P["rate"]
        for w in windows:
            s, e = w[1], w[2]
            inside = s <= t < e if s < e else (t >= s or t < e)
            if inside:
                name, milli = w[0], w[3]
                break
        a = min(units, allow_left) if P["allow"] else 0
        if a:
            allow_left -= a
            lines["allow"][0] += a
            lines["allow"][1] += a * P["allow"][1] * pct
        rest = units - a
        lines[name][0] += rest
        lines[name][1] += rest * milli * pct
    items = []  # (label, units or None, amount)
    base = P["base"]
    items.append(("base", None, base))
    for lb in labels:
        u, nu = lines[lb]
        items.append((lb, u, rnd(mode, nu, 100000)))
    if P["demand"] is not None:
        items.append(("demand", None, max([r[2] for r in R] or [0]) * P["demand"]))
    sub = sum(x[2] for x in items)
    if P["minimum"] is not None and sub < P["minimum"]:
        items.append(("minimum", None, P["minimum"] - sub))
    if P["tax"] is not None:
        ex = set(P["exempt"])
        taxable = sum(x[2] for x in items if x[0] not in ex)
        items.append(("tax", None, rnd(mode, taxable * P["tax"], 100)))
    if P["credit"] is not None:
        cur = sum(x[2] for x in items)
        items.append(("credit", None, -min(P["credit"], cur)))
    total = sum(x[2] for x in items)
    out = []
    for lb, u, amt in items:
        out.append("%s %d units %s" % (lb, u, money(amt)) if u is not None else "%s %s" % (lb, money(amt)))
    out.append("%s %s" % (L_TOTAL, money(total)))
    return "\n".join(out)
'''

JS = r'''
'use strict';
const MONEY = @MONEY@;
const L_OTHER = @L_OTHER@;
const L_TOTAL = @L_TOTAL@;
const HAS_WINDOW = @WINDOW@;
const HAS_ALLOW = @ALLOW@;
const HAS_TAX = @TAX@;
const LOW = 'abcdefghijklmnopqrstuvwxyz';
const DG = '0123456789';

class Err extends Error {}

function splitLines(text) {
  if (text === '') return [];
  const ls = text.split('\n');
  if (ls[ls.length - 1] === '') ls.pop();
  return ls;
}

function allIn(s, set) {
  for (const c of s) if (!set.includes(c)) return false;
  return true;
}

function num(s, lo, hi) {
  return s.length >= 1 && s.length <= 7 && allIn(s, DG) && (s.length === 1 || s[0] !== '0') && Number(s) >= lo && Number(s) <= hi;
}

function parseTime(s) {
  if (s.length !== 5 || s[2] !== ':' || !allIn(s.slice(0, 2) + s.slice(3), DG)) return null;
  const h = Number(s.slice(0, 2));
  const m = Number(s.slice(3));
  if (h > 23 || m > 59) return null;
  return h * 60 + m;
}

function inWindow(w, t) {
  const s = w.s;
  const e = w.e;
  return s < e ? s <= t && t < e : t >= s || t < e;
}

function overlap(a, b) {
  for (let t = 0; t < 1440; t++) if (inWindow(a, t) && inWindow(b, t)) return true;
  return false;
}

function parsePlan(text) {
  const P = { rate: null, base: 0, round: 'nearest', windows: [], minimum: null, allow: null, season: null, demand: null, tax: null, exempt: [], credit: null };
  const seen = new Set();
  const single = ['rate', 'base', 'round'].concat(HAS_WINDOW ? ['minimum'] : [], HAS_ALLOW ? ['allow', 'season', 'demand'] : [], HAS_TAX ? ['tax', 'credit'] : []);
  const multi = (HAS_WINDOW ? ['window'] : []).concat(HAS_TAX ? ['exempt'] : []);
  const exemptLines = [];
  const lines = splitLines(text);
  for (let i = 0; i < lines.length; i++) {
    const n = i + 1;
    const w = lines[i].split(' ');
    const d = w[0];
    if (!single.includes(d) && !multi.includes(d)) throw new Err('error: plan ' + n + ': unknown');
    const bad = () => new Err('error: plan ' + n + ': argument');
    const a = w.slice(1);
    let val = null;
    if (d === 'rate') {
      if (a.length !== 1 || !num(a[0], 1, 999999)) throw bad();
      val = Number(a[0]);
    } else if (d === 'base') {
      if (a.length !== 1 || !num(a[0], 0, 9999999)) throw bad();
      val = Number(a[0]);
    } else if (d === 'round') {
      if (a.length !== 1 || !['up', 'down', 'nearest'].includes(a[0])) throw bad();
      val = a[0];
    } else if (d === 'minimum' || d === 'demand' || d === 'credit') {
      if (a.length !== 1 || !num(a[0], d !== 'minimum' ? 1 : 0, 9999999)) throw bad();
      val = Number(a[0]);
    } else if (d === 'tax') {
      if (a.length !== 1 || !num(a[0], 1, 100)) throw bad();
      val = Number(a[0]);
    } else if (d === 'allow') {
      if (a.length !== 2 || !num(a[0], 1, 9999999) || !num(a[1], 0, 999999)) throw bad();
      val = [Number(a[0]), Number(a[1])];
    } else if (d === 'season') {
      if (a.length !== 2 || !num(a[1], 1, 500)) throw bad();
      const ms = a[0].split(',');
      if (!ms.every((m) => num(m, 1, 12)) || new Set(ms).size !== ms.length) throw bad();
      val = [ms.map(Number), Number(a[1])];
    } else if (d === 'window') {
      if (a.length !== 3 || !(a[0].length >= 1 && a[0].length <= 8 && allIn(a[0], LOW)) || a[0] === L_OTHER) throw bad();
      const r = a[1].split('-');
      if (r.length !== 2 || parseTime(r[0]) === null || parseTime(r[1]) === null || r[0] === r[1] || !num(a[2], 1, 999999)) throw bad();
      val = { name: a[0], s: parseTime(r[0]), e: parseTime(r[1]), milli: Number(a[2]) };
    } else if (d === 'exempt') {
      if (a.length !== 1 || !(a[0].length >= 1 && a[0].length <= 8 && allIn(a[0], LOW))) throw bad();
      val = a[0];
    }
    if (single.includes(d)) {
      if (seen.has(d)) throw new Err('error: plan ' + n + ': duplicate');
      seen.add(d);
      P[d] = val;
    } else if (d === 'window') {
      if (P.windows.some((x) => x.name === val.name)) throw new Err('error: plan ' + n + ': duplicate');
      if (P.windows.some((x) => overlap(x, val))) throw new Err('error: plan ' + n + ': overlap');
      P.windows.push(val);
    } else {
      if (P.exempt.includes(val)) throw new Err('error: plan ' + n + ': duplicate');
      P.exempt.push(val);
      exemptLines.push([n, val]);
    }
  }
  const names = new Set(P.windows.map((x) => x.name).concat([L_OTHER, 'base', 'minimum', 'demand', 'allow']));
  for (const [n, nm] of exemptLines) if (!names.has(nm)) throw new Err('error: plan ' + n + ': argument');
  if (P.rate === null) throw new Err('error: plan: no rate');
  return P;
}

function parseReadings(text) {
  const out = [];
  const lines = splitLines(text);
  for (let i = 0; i < lines.length; i++) {
    const w = lines[i].split(' ');
    let why = null;
    if (w.length !== 3) why = 'fields';
    else {
      const d = w[0];
      let ok = d.length === 10 && d[4] === '-' && d[7] === '-' && allIn(d.slice(0, 4) + d.slice(5, 7) + d.slice(8), DG);
      if (ok) {
        const mo = Number(d.slice(5, 7));
        const da = Number(d.slice(8));
        ok = mo >= 1 && mo <= 12 && da >= 1 && da <= 31;
      }
      if (!ok) why = 'date';
      else if (parseTime(w[1]) === null) why = 'time';
      else if (!(w[2].length >= 1 && w[2].length <= 6 && allIn(w[2], DG) && (w[2].length === 1 || w[2][0] !== '0'))) why = 'units';
    }
    if (why) throw new Err('error: reading ' + (i + 1) + ': ' + why);
    out.push({ date: w[0], t: parseTime(w[1]), units: BigInt(w[2]), month: Number(w[0].slice(5, 7)), idx: i });
  }
  return out;
}

function rnd(mode, numer, denom) {
  if (mode === 'up') return (numer + denom - 1n) / denom;
  if (mode === 'down') return numer / denom;
  return (2n * numer + denom) / (2n * denom);
}

function money(c) {
  if (MONEY === 'cents') return c.toString();
  const a = c < 0n ? -c : c;
  return (c < 0n ? '-' : '') + (a / 100n).toString() + '.' + (a % 100n).toString().padStart(2, '0');
}

function doBill(plan, readings) {
  const P = parsePlan(plan);
  const R = parseReadings(readings);
  const order = R.slice().sort((x, y) => (x.date < y.date ? -1 : x.date > y.date ? 1 : x.t - y.t || x.idx - y.idx));
  const mode = P.round;
  let allowLeft = P.allow ? BigInt(P.allow[0]) : 0n;
  const labels = (P.allow ? ['allow'] : []).concat(P.windows.map((w) => w.name), [L_OTHER]);
  const lines = new Map();
  for (const lb of labels) lines.set(lb, [0n, 0n]);
  for (const r of order) {
    const pct = BigInt(P.season && P.season[0].includes(r.month) ? P.season[1] : 100);
    let name = L_OTHER;
    let milli = BigInt(P.rate);
    for (const w of P.windows) {
      if (inWindow(w, r.t)) {
        name = w.name;
        milli = BigInt(w.milli);
        break;
      }
    }
    let a = 0n;
    if (P.allow) a = r.units < allowLeft ? r.units : allowLeft;
    if (a > 0n) {
      allowLeft -= a;
      const l = lines.get('allow');
      l[0] += a;
      l[1] += a * BigInt(P.allow[1]) * pct;
    }
    const rest = r.units - a;
    const l = lines.get(name);
    l[0] += rest;
    l[1] += rest * milli * pct;
  }
  const items = [['base', null, BigInt(P.base)]];
  for (const lb of labels) {
    const [u, nu] = lines.get(lb);
    items.push([lb, u, rnd(mode, nu, 100000n)]);
  }
  const sum = () => items.reduce((acc, x) => acc + x[2], 0n);
  if (P.demand !== null) {
    let mx = 0n;
    for (const r of R) if (r.units > mx) mx = r.units;
    items.push(['demand', null, mx * BigInt(P.demand)]);
  }
  const sub = sum();
  if (P.minimum !== null && sub < BigInt(P.minimum)) items.push(['minimum', null, BigInt(P.minimum) - sub]);
  if (P.tax !== null) {
    let taxable = 0n;
    for (const x of items) if (!P.exempt.includes(x[0])) taxable += x[2];
    items.push(['tax', null, rnd(mode, taxable * BigInt(P.tax), 100n)]);
  }
  if (P.credit !== null) {
    const cur = sum();
    const c = BigInt(P.credit);
    items.push(['credit', null, -(c < cur ? c : cur)]);
  }
  const total = sum();
  const out = items.map(([lb, u, amt]) => (u !== null ? lb + ' ' + u.toString() + ' units ' + money(amt) : lb + ' ' + money(amt)));
  out.push(L_TOTAL + ' ' + money(total));
  return out.join('\n');
}

function bill(plan, readings) {
  try {
    return doBill(plan, readings);
  } catch (e) {
    if (e instanceof Err) return e.message;
    throw e;
  }
}

module.exports = { bill };
'''

RB = r'''
module Ratebill
  MONEY = @MONEY@
  L_OTHER = @L_OTHER@
  L_TOTAL = @L_TOTAL@
  HAS_WINDOW = @WINDOW@
  HAS_ALLOW = @ALLOW@
  HAS_TAX = @TAX@
  LOW = 'abcdefghijklmnopqrstuvwxyz'
  DG = '0123456789'

  class Err < StandardError; end

  def self.split_lines(text)
    return [] if text.empty?
    ls = text.split("\n", -1)
    ls.pop if ls[-1] == ''
    ls
  end

  def self.all_in?(s, set)
    s.each_char { |c| return false unless set.include?(c) }
    true
  end

  def self.num?(s, lo, hi)
    s.length >= 1 && s.length <= 7 && all_in?(s, DG) && (s.length == 1 || s[0] != '0') && s.to_i >= lo && s.to_i <= hi
  end

  def self.parse_time(s)
    return nil if s.length != 5 || s[2] != ':' || !all_in?(s[0, 2] + s[3..-1], DG)
    h = s[0, 2].to_i
    m = s[3..-1].to_i
    return nil if h > 23 || m > 59
    h * 60 + m
  end

  def self.in_window?(w, t)
    s = w[:s]
    e = w[:e]
    s < e ? (s <= t && t < e) : (t >= s || t < e)
  end

  def self.overlap?(a, b)
    (0...1440).any? { |t| in_window?(a, t) && in_window?(b, t) }
  end

  def self.name?(s)
    s.length >= 1 && s.length <= 8 && all_in?(s, LOW)
  end

  def self.parse_plan(text)
    p = { rate: nil, base: 0, round: 'nearest', windows: [], minimum: nil, allow: nil, season: nil, demand: nil, tax: nil, exempt: [], credit: nil }
    seen = {}
    single = %w[rate base round]
    single += %w[minimum] if HAS_WINDOW
    single += %w[allow season demand] if HAS_ALLOW
    single += %w[tax credit] if HAS_TAX
    multi = (HAS_WINDOW ? %w[window] : []) + (HAS_TAX ? %w[exempt] : [])
    exempt_lines = []
    split_lines(text).each_with_index do |line, i|
      n = i + 1
      w = line.split(/ /, -1)
      d = w[0]
      raise Err, "error: plan #{n}: unknown" unless single.include?(d) || multi.include?(d)
      bad = Err.new("error: plan #{n}: argument")
      a = w[1..-1]
      val = nil
      case d
      when 'rate'
        raise bad if a.length != 1 || !num?(a[0], 1, 999_999)
        val = a[0].to_i
      when 'base'
        raise bad if a.length != 1 || !num?(a[0], 0, 9_999_999)
        val = a[0].to_i
      when 'round'
        raise bad if a.length != 1 || !%w[up down nearest].include?(a[0])
        val = a[0]
      when 'minimum', 'demand', 'credit'
        raise bad if a.length != 1 || !num?(a[0], d != 'minimum' ? 1 : 0, 9_999_999)
        val = a[0].to_i
      when 'tax'
        raise bad if a.length != 1 || !num?(a[0], 1, 100)
        val = a[0].to_i
      when 'allow'
        raise bad if a.length != 2 || !num?(a[0], 1, 9_999_999) || !num?(a[1], 0, 999_999)
        val = [a[0].to_i, a[1].to_i]
      when 'season'
        raise bad if a.length != 2 || !num?(a[1], 1, 500)
        ms = a[0].split(/,/, -1)
        ms = [''] if a[0].empty?
        raise bad if !ms.all? { |m| num?(m, 1, 12) } || ms.uniq.length != ms.length
        val = [ms.map(&:to_i), a[1].to_i]
      when 'window'
        raise bad if a.length != 3 || !name?(a[0]) || a[0] == L_OTHER
        r = a[1].split(/-/, -1)
        raise bad if r.length != 2 || parse_time(r[0]).nil? || parse_time(r[1]).nil? || r[0] == r[1] || !num?(a[2], 1, 999_999)
        val = { name: a[0], s: parse_time(r[0]), e: parse_time(r[1]), milli: a[2].to_i }
      when 'exempt'
        raise bad if a.length != 1 || !name?(a[0])
        val = a[0]
      end
      if single.include?(d)
        raise Err, "error: plan #{n}: duplicate" if seen[d]
        seen[d] = true
        p[d.to_sym] = val
      elsif d == 'window'
        raise Err, "error: plan #{n}: duplicate" if p[:windows].any? { |x| x[:name] == val[:name] }
        raise Err, "error: plan #{n}: overlap" if p[:windows].any? { |x| overlap?(x, val) }
        p[:windows] << val
      else
        raise Err, "error: plan #{n}: duplicate" if p[:exempt].include?(val)
        p[:exempt] << val
        exempt_lines << [n, val]
      end
    end
    names = p[:windows].map { |x| x[:name] } + [L_OTHER, 'base', 'minimum', 'demand', 'allow']
    exempt_lines.each { |n, nm| raise Err, "error: plan #{n}: argument" unless names.include?(nm) }
    raise Err, 'error: plan: no rate' if p[:rate].nil?
    p
  end

  def self.parse_readings(text)
    out = []
    split_lines(text).each_with_index do |line, i|
      w = line.split(/ /, -1)
      why = nil
      if w.length != 3
        why = 'fields'
      else
        d = w[0]
        ok = d.length == 10 && d[4] == '-' && d[7] == '-' && all_in?(d[0, 4] + d[5, 2] + d[8..-1], DG)
        if ok
          mo = d[5, 2].to_i
          da = d[8..-1].to_i
          ok = mo >= 1 && mo <= 12 && da >= 1 && da <= 31
        end
        if !ok
          why = 'date'
        elsif parse_time(w[1]).nil?
          why = 'time'
        elsif !(w[2].length >= 1 && w[2].length <= 6 && all_in?(w[2], DG) && (w[2].length == 1 || w[2][0] != '0'))
          why = 'units'
        end
      end
      raise Err, "error: reading #{i + 1}: #{why}" if why
      out << { date: w[0], t: parse_time(w[1]), units: w[2].to_i, month: w[0][5, 2].to_i, idx: i }
    end
    out
  end

  def self.rnd(mode, numer, denom)
    return (numer + denom - 1) / denom if mode == 'up'
    return numer / denom if mode == 'down'
    (2 * numer + denom) / (2 * denom)
  end

  def self.money(c)
    return c.to_s if MONEY == 'cents'
    a = c.abs
    (c < 0 ? '-' : '') + format('%d.%02d', a / 100, a % 100)
  end

  def self.do_bill(plan, readings)
    p = parse_plan(plan)
    r = parse_readings(readings)
    order = r.sort_by { |x| [x[:date], x[:t], x[:idx]] }
    mode = p[:round]
    allow_left = p[:allow] ? p[:allow][0] : 0
    labels = (p[:allow] ? ['allow'] : []) + p[:windows].map { |w| w[:name] } + [L_OTHER]
    lines = {}
    labels.each { |lb| lines[lb] = [0, 0] }
    order.each do |x|
      pct = p[:season] && p[:season][0].include?(x[:month]) ? p[:season][1] : 100
      name = L_OTHER
      milli = p[:rate]
      p[:windows].each do |w|
        if in_window?(w, x[:t])
          name = w[:name]
          milli = w[:milli]
          break
        end
      end
      a = p[:allow] ? [x[:units], allow_left].min : 0
      if a > 0
        allow_left -= a
        lines['allow'][0] += a
        lines['allow'][1] += a * p[:allow][1] * pct
      end
      rest = x[:units] - a
      lines[name][0] += rest
      lines[name][1] += rest * milli * pct
    end
    items = [['base', nil, p[:base]]]
    labels.each { |lb| items << [lb, lines[lb][0], rnd(mode, lines[lb][1], 100_000)] }
    sum = -> { items.sum { |x| x[2] } }
    items << ['demand', nil, (r.map { |x| x[:units] }.max || 0) * p[:demand]] unless p[:demand].nil?
    sub = sum.call
    items << ['minimum', nil, p[:minimum] - sub] if !p[:minimum].nil? && sub < p[:minimum]
    unless p[:tax].nil?
      taxable = items.reject { |x| p[:exempt].include?(x[0]) }.sum { |x| x[2] }
      items << ['tax', nil, rnd(mode, taxable * p[:tax], 100)]
    end
    unless p[:credit].nil?
      cur = sum.call
      items << ['credit', nil, -[p[:credit], cur].min]
    end
    total = sum.call
    out = items.map { |lb, u, amt| u.nil? ? "#{lb} #{money(amt)}" : "#{lb} #{u} units #{money(amt)}" }
    out << "#{L_TOTAL} #{money(total)}"
    out.join("\n")
  end

  def self.bill(plan, readings)
    do_bill(plan, readings)
  rescue Err => e
    e.message
  end
end
'''

CC = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ratebill.h"

#define MONEY_CENTS @MONEY_CENTS@
#define L_OTHER @L_OTHER@
#define L_TOTAL @L_TOTAL@
#define HAS_WINDOW @WINDOW@
#define HAS_ALLOW @ALLOW@
#define HAS_TAX @TAX@

typedef long long ll;

typedef struct { char name[16]; int s, e; ll milli; } Win;
typedef struct { char date[16]; int t; ll units; int month; int idx; } Rd;
typedef struct { char label[16]; int has_units; ll units; ll amt; } Item;

typedef struct {
    ll rate, base;
    int round; /* 0 nearest, 1 up, 2 down */
    Win *w;
    int nw;
    int has_min;
    ll minimum;
    int has_allow;
    ll allow_units, allow_milli;
    int has_season, nseason, season_months[12];
    ll season_pct;
    int has_demand;
    ll demand;
    int has_tax;
    ll tax;
    char (*ex)[16];
    int nex;
    int has_credit;
    ll credit;
} Plan;

static char errbuf[96];

static int fail(const char *fmt, int n, const char *why) {
    if (n >= 0) sprintf(errbuf, fmt, n, why);
    else sprintf(errbuf, "%s", fmt);
    return 0;
}

static char *dupstr(const char *s) {
    char *r = malloc(strlen(s) + 1);
    strcpy(r, s);
    return r;
}

/* splits text into lines (copies); returns the count */
static int split_lines(const char *text, char ***out) {
    size_t len = strlen(text);
    int n = 0, cap = 8;
    char **ls = malloc((size_t)cap * sizeof(char *));
    if (len == 0) {
        *out = ls;
        return 0;
    }
    size_t pos = 0;
    while (pos <= len) {
        const char *e = memchr(text + pos, '\n', len - pos);
        size_t ll_ = e ? (size_t)(e - (text + pos)) : len - pos;
        if (!e && ll_ == 0) break;
        if (n == cap) {
            cap *= 2;
            ls = realloc(ls, (size_t)cap * sizeof(char *));
        }
        char *l = malloc(ll_ + 1);
        memcpy(l, text + pos, ll_);
        l[ll_] = 0;
        ls[n++] = l;
        if (!e) break;
        pos += ll_ + 1;
    }
    *out = ls;
    return n;
}

static void free_lines(char **ls, int n) {
    for (int i = 0; i < n; i++) free(ls[i]);
    free(ls);
}

static int split_words(char *line, char ***out) {
    int cnt = 1;
    for (char *p = line; *p; p++)
        if (*p == ' ') cnt++;
    char **w = malloc((size_t)cnt * sizeof(char *));
    int n = 0;
    char *p = line;
    for (;;) {
        w[n++] = p;
        char *e = strchr(p, ' ');
        if (!e) break;
        *e = 0;
        p = e + 1;
    }
    *out = w;
    return n;
}

static int all_digits(const char *s) {
    for (; *s; s++)
        if (*s < '0' || *s > '9') return 0;
    return 1;
}

static int num(const char *s, ll lo, ll hi) {
    size_t n = strlen(s);
    if (n < 1 || n > 7 || !all_digits(s) || (n > 1 && s[0] == '0')) return 0;
    ll v = atoll(s);
    return v >= lo && v <= hi;
}

static int parse_time(const char *s) {
    if (strlen(s) != 5 || s[2] != ':' || !(s[0] >= '0' && s[0] <= '9' && s[1] >= '0' && s[1] <= '9' && s[3] >= '0' && s[3] <= '9' && s[4] >= '0' && s[4] <= '9')) return -1;
    int h = (s[0] - '0') * 10 + (s[1] - '0'), m = (s[3] - '0') * 10 + (s[4] - '0');
    if (h > 23 || m > 59) return -1;
    return h * 60 + m;
}

static int in_window(const Win *w, int t) {
    return w->s < w->e ? (w->s <= t && t < w->e) : (t >= w->s || t < w->e);
}

static int overlap(const Win *a, const Win *b) {
    for (int t = 0; t < 1440; t++)
        if (in_window(a, t) && in_window(b, t)) return 1;
    return 0;
}

static int good_name(const char *s) {
    size_t n = strlen(s);
    if (n < 1 || n > 8) return 0;
    for (size_t i = 0; i < n; i++)
        if (s[i] < 'a' || s[i] > 'z') return 0;
    return 1;
}

static int is_single(const char *d) {
    if (!strcmp(d, "rate") || !strcmp(d, "base") || !strcmp(d, "round")) return 1;
    if (HAS_WINDOW && !strcmp(d, "minimum")) return 1;
    if (HAS_ALLOW && (!strcmp(d, "allow") || !strcmp(d, "season") || !strcmp(d, "demand"))) return 1;
    if (HAS_TAX && (!strcmp(d, "tax") || !strcmp(d, "credit"))) return 1;
    return 0;
}

static int is_multi(const char *d) {
    return (HAS_WINDOW && !strcmp(d, "window")) || (HAS_TAX && !strcmp(d, "exempt"));
}

static int parse_plan(const char *text, Plan *P) {
    memset(P, 0, sizeof *P);
    P->round = 0;
    char **ls;
    int nl = split_lines(text, &ls);
    int seen_rate = 0, seen_base = 0, seen_round = 0, seen_min = 0, seen_allow = 0, seen_season = 0, seen_demand = 0, seen_tax = 0, seen_credit = 0;
    int cap_ex = 4;
    P->ex = malloc((size_t)cap_ex * 16);
    int *ex_line = malloc((size_t)cap_ex * sizeof(int));
    int cap_w = 4;
    P->w = malloc((size_t)cap_w * sizeof(Win));
    int ok = 1;
    for (int i = 0; ok && i < nl; i++) {
        int n = i + 1;
        char **w;
        int nw = split_words(ls[i], &w);
        const char *d = w[0];
        char **a = w + 1;
        int na = nw - 1;
        if (!is_single(d) && !is_multi(d)) {
            ok = fail("error: plan %d: %s", n, "unknown");
            free(w);
            break;
        }
        int bad = 0;
        ll v1 = 0, v2 = 0;
        Win nwin;
        memset(&nwin, 0, sizeof nwin);
        if (!strcmp(d, "rate")) {
            if (na != 1 || !num(a[0], 1, 999999)) bad = 1;
            else v1 = atoll(a[0]);
        } else if (!strcmp(d, "base")) {
            if (na != 1 || !num(a[0], 0, 9999999)) bad = 1;
            else v1 = atoll(a[0]);
        } else if (!strcmp(d, "round")) {
            if (na != 1 || !(!strcmp(a[0], "up") || !strcmp(a[0], "down") || !strcmp(a[0], "nearest"))) bad = 1;
            else v1 = !strcmp(a[0], "nearest") ? 0 : !strcmp(a[0], "up") ? 1 : 2;
        } else if (!strcmp(d, "minimum") || !strcmp(d, "demand") || !strcmp(d, "credit")) {
            if (na != 1 || !num(a[0], strcmp(d, "minimum") ? 1 : 0, 9999999)) bad = 1;
            else v1 = atoll(a[0]);
        } else if (!strcmp(d, "tax")) {
            if (na != 1 || !num(a[0], 1, 100)) bad = 1;
            else v1 = atoll(a[0]);
        } else if (!strcmp(d, "allow")) {
            if (na != 2 || !num(a[0], 1, 9999999) || !num(a[1], 0, 999999)) bad = 1;
            else {
                v1 = atoll(a[0]);
                v2 = atoll(a[1]);
            }
        } else if (!strcmp(d, "season")) {
            if (na != 2 || !num(a[1], 1, 500)) bad = 1;
            else {
                int cnt = 0;
                char *p = a[0];
                for (;;) {
                    char *e = strchr(p, ',');
                    char save = e ? *e : 0;
                    if (e) *e = 0;
                    if (!num(p, 1, 12) || cnt >= 12) bad = 1;
                    else {
                        int m = atoi(p);
                        for (int k = 0; k < cnt; k++)
                            if (P->season_months[k] == m) bad = 1;
                        P->season_months[cnt++] = m;
                    }
                    if (e) *e = save;
                    if (!e || bad) break;
                    p = e + 1;
                }
                if (!bad) {
                    P->nseason = cnt;
                    v1 = atoll(a[1]);
                }
            }
        } else if (!strcmp(d, "window")) {
            if (na != 3 || !good_name(a[0]) || !strcmp(a[0], L_OTHER)) bad = 1;
            else {
                char *dash = strchr(a[1], '-');
                if (!dash || strchr(dash + 1, '-')) bad = 1;
                else {
                    *dash = 0;
                    int s = parse_time(a[1]), e = parse_time(dash + 1);
                    if (s < 0 || e < 0 || s == e || !num(a[2], 1, 999999)) bad = 1;
                    else {
                        strcpy(nwin.name, a[0]);
                        nwin.s = s;
                        nwin.e = e;
                        nwin.milli = atoll(a[2]);
                    }
                    *dash = '-';
                }
            }
        } else if (!strcmp(d, "exempt")) {
            if (na != 1 || !good_name(a[0])) bad = 1;
        }
        if (bad) {
            ok = fail("error: plan %d: %s", n, "argument");
            free(w);
            break;
        }
        if (is_single(d)) {
            int *flag = !strcmp(d, "rate") ? &seen_rate : !strcmp(d, "base") ? &seen_base : !strcmp(d, "round") ? &seen_round : !strcmp(d, "minimum") ? &seen_min : !strcmp(d, "allow") ? &seen_allow : !strcmp(d, "season") ? &seen_season :
                         !strcmp(d, "demand") ? &seen_demand : !strcmp(d, "tax") ? &seen_tax : &seen_credit;
            if (*flag) {
                ok = fail("error: plan %d: %s", n, "duplicate");
                free(w);
                break;
            }
            *flag = 1;
            if (!strcmp(d, "rate")) P->rate = v1;
            else if (!strcmp(d, "base")) P->base = v1;
            else if (!strcmp(d, "round")) P->round = (int)v1;
            else if (!strcmp(d, "minimum")) P->has_min = 1, P->minimum = v1;
            else if (!strcmp(d, "allow")) P->has_allow = 1, P->allow_units = v1, P->allow_milli = v2;
            else if (!strcmp(d, "season")) P->has_season = 1, P->season_pct = v1;
            else if (!strcmp(d, "demand")) P->has_demand = 1, P->demand = v1;
            else if (!strcmp(d, "tax")) P->has_tax = 1, P->tax = v1;
            else P->has_credit = 1, P->credit = v1;
        } else if (!strcmp(d, "window")) {
            for (int k = 0; k < P->nw; k++)
                if (!strcmp(P->w[k].name, nwin.name)) ok = fail("error: plan %d: %s", n, "duplicate");
            for (int k = 0; ok && k < P->nw; k++)
                if (overlap(&P->w[k], &nwin)) ok = fail("error: plan %d: %s", n, "overlap");
            if (!ok) {
                free(w);
                break;
            }
            if (P->nw == cap_w) {
                cap_w *= 2;
                P->w = realloc(P->w, (size_t)cap_w * sizeof(Win));
            }
            P->w[P->nw++] = nwin;
        } else {
            for (int k = 0; k < P->nex; k++)
                if (!strcmp(P->ex[k], a[0])) ok = fail("error: plan %d: %s", n, "duplicate");
            if (!ok) {
                free(w);
                break;
            }
            if (P->nex == cap_ex) {
                cap_ex *= 2;
                P->ex = realloc(P->ex, (size_t)cap_ex * 16);
                ex_line = realloc(ex_line, (size_t)cap_ex * sizeof(int));
            }
            strcpy(P->ex[P->nex], a[0]);
            ex_line[P->nex++] = n;
        }
        free(w);
    }
    if (ok) {
        for (int k = 0; ok && k < P->nex; k++) {
            const char *nm = P->ex[k];
            int found = !strcmp(nm, L_OTHER) || !strcmp(nm, "base") || !strcmp(nm, "minimum") || !strcmp(nm, "demand") || !strcmp(nm, "allow");
            for (int j = 0; j < P->nw; j++)
                if (!strcmp(P->w[j].name, nm)) found = 1;
            if (!found) ok = fail("error: plan %d: %s", ex_line[k], "argument");
        }
    }
    if (ok && !seen_rate) ok = fail("error: plan: no rate", -1, "");
    free_lines(ls, nl);
    free(ex_line);
    return ok;
}

static int cmp_rd(const void *x, const void *y) {
    const Rd *a = x, *b = y;
    int c = strcmp(a->date, b->date);
    if (c) return c;
    if (a->t != b->t) return a->t < b->t ? -1 : 1;
    return a->idx < b->idx ? -1 : a->idx > b->idx;
}

static int parse_readings(const char *text, Rd **out, int *nout) {
    char **ls;
    int nl = split_lines(text, &ls);
    Rd *rs = malloc((size_t)(nl + 1) * sizeof(Rd));
    int ok = 1;
    for (int i = 0; i < nl && ok; i++) {
        char **w;
        int nw = split_words(ls[i], &w);
        const char *why = NULL;
        if (nw != 3) why = "fields";
        else {
            const char *d = w[0];
            int dok = strlen(d) == 10 && d[4] == '-' && d[7] == '-';
            for (int k = 0; dok && k < 10; k++)
                if (k != 4 && k != 7 && (d[k] < '0' || d[k] > '9')) dok = 0;
            int mo = 0, da = 0;
            if (dok) {
                mo = (d[5] - '0') * 10 + (d[6] - '0');
                da = (d[8] - '0') * 10 + (d[9] - '0');
                dok = mo >= 1 && mo <= 12 && da >= 1 && da <= 31;
            }
            size_t un = strlen(w[2]);
            if (!dok) why = "date";
            else if (parse_time(w[1]) < 0) why = "time";
            else if (!(un >= 1 && un <= 6 && all_digits(w[2]) && (un == 1 || w[2][0] != '0'))) why = "units";
            else {
                strcpy(rs[i].date, d);
                rs[i].t = parse_time(w[1]);
                rs[i].units = atoll(w[2]);
                rs[i].month = mo;
                rs[i].idx = i;
            }
        }
        if (why) ok = fail("error: reading %d: %s", i + 1, why);
        free(w);
    }
    free_lines(ls, nl);
    *out = rs;
    *nout = nl;
    return ok;
}

static ll rnd(int mode, ll numer, ll denom) {
    if (mode == 1) return (numer + denom - 1) / denom;
    if (mode == 2) return numer / denom;
    return (2 * numer + denom) / (2 * denom);
}

static void money(ll c, char *buf) {
    if (MONEY_CENTS) {
        sprintf(buf, "%lld", c);
        return;
    }
    ll a = c < 0 ? -c : c;
    sprintf(buf, "%s%lld.%02lld", c < 0 ? "-" : "", a / 100, a % 100);
}

char *bill(const char *plan, const char *readings) {
    Plan P;
    if (!parse_plan(plan, &P)) {
        free(P.w);
        free(P.ex);
        return dupstr(errbuf);
    }
    Rd *R;
    int nr;
    if (!parse_readings(readings, &R, &nr)) {
        free(P.w);
        free(P.ex);
        free(R);
        return dupstr(errbuf);
    }
    qsort(R, (size_t)nr, sizeof(Rd), cmp_rd);
    int nlab = (P.has_allow ? 1 : 0) + P.nw + 1;
    char (*labels)[16] = malloc((size_t)nlab * 16);
    int li = 0;
    if (P.has_allow) strcpy(labels[li++], "allow");
    for (int k = 0; k < P.nw; k++) strcpy(labels[li++], P.w[k].name);
    strcpy(labels[li++], L_OTHER);
    ll *lunits = calloc((size_t)nlab, sizeof(ll)), *lnum = calloc((size_t)nlab, sizeof(ll));
    ll allow_left = P.has_allow ? P.allow_units : 0;
    ll max_units = 0;
    for (int i = 0; i < nr; i++) {
        ll units = R[i].units;
        if (units > max_units) max_units = units;
        ll pct = 100;
        if (P.has_season)
            for (int k = 0; k < P.nseason; k++)
                if (P.season_months[k] == R[i].month) pct = P.season_pct;
        int idx = nlab - 1;
        ll milli = P.rate;
        for (int k = 0; k < P.nw; k++) {
            if (in_window(&P.w[k], R[i].t)) {
                idx = (P.has_allow ? 1 : 0) + k;
                milli = P.w[k].milli;
                break;
            }
        }
        ll a = 0;
        if (P.has_allow) a = units < allow_left ? units : allow_left;
        if (a > 0) {
            allow_left -= a;
            lunits[0] += a;
            lnum[0] += a * P.allow_milli * pct;
        }
        ll rest = units - a;
        lunits[idx] += rest;
        lnum[idx] += rest * milli * pct;
    }
    Item *items = malloc((size_t)(nlab + 8) * sizeof(Item));
    int ni = 0;
    strcpy(items[ni].label, "base");
    items[ni].has_units = 0;
    items[ni++].amt = P.base;
    for (int k = 0; k < nlab; k++) {
        strcpy(items[ni].label, labels[k]);
        items[ni].has_units = 1;
        items[ni].units = lunits[k];
        items[ni++].amt = rnd(P.round, lnum[k], 100000);
    }
    ll sum = 0;
    if (P.has_demand) {
        strcpy(items[ni].label, "demand");
        items[ni].has_units = 0;
        items[ni++].amt = max_units * P.demand;
    }
    for (int k = 0; k < ni; k++) sum += items[k].amt;
    if (P.has_min && sum < P.minimum) {
        strcpy(items[ni].label, "minimum");
        items[ni].has_units = 0;
        items[ni++].amt = P.minimum - sum;
    }
    if (P.has_tax) {
        ll taxable = 0;
        for (int k = 0; k < ni; k++) {
            int ex = 0;
            for (int j = 0; j < P.nex; j++)
                if (!strcmp(P.ex[j], items[k].label)) ex = 1;
            if (!ex) taxable += items[k].amt;
        }
        strcpy(items[ni].label, "tax");
        items[ni].has_units = 0;
        items[ni++].amt = rnd(P.round, taxable * P.tax, 100);
    }
    if (P.has_credit) {
        ll cur = 0;
        for (int k = 0; k < ni; k++) cur += items[k].amt;
        strcpy(items[ni].label, "credit");
        items[ni].has_units = 0;
        items[ni++].amt = -(P.credit < cur ? P.credit : cur);
    }
    ll total = 0;
    for (int k = 0; k < ni; k++) total += items[k].amt;
    size_t cap = (size_t)(ni + 2) * 80;
    char *out = malloc(cap);
    out[0] = 0;
    char buf[64];
    for (int k = 0; k < ni; k++) {
        money(items[k].amt, buf);
        char line[160];
        if (items[k].has_units) sprintf(line, "%s %lld units %s\n", items[k].label, items[k].units, buf);
        else sprintf(line, "%s %s\n", items[k].label, buf);
        strcat(out, line);
    }
    money(total, buf);
    strcat(out, L_TOTAL);
    strcat(out, " ");
    strcat(out, buf);
    free(P.w);
    free(P.ex);
    free(R);
    free(labels);
    free(lunits);
    free(lnum);
    free(items);
    return out;
}
'''



WINDOWS = [("night", "22:00-06:00"), ("peak", "16:00-20:00"), ("morn", "06:00-09:30"), ("noon", "11:45-12:15"), ("late", "20:00-00:00"), ("edge", "23:59-00:00"), ("dawn", "05:00-05:01"), ("day", "09:30-16:00"), ("eve", "18:30-21:15")]
THEMES = ["the tide-pump co-op", "the greenhouse heating share", "the harbour cranes", "the kiln power meter", "the cold-store compressors"]
TIMES = ["00:00", "00:01", "05:00", "05:01", "06:00", "09:29", "09:30", "11:44", "11:45", "12:14", "12:15", "15:59", "16:00", "19:59", "20:00", "21:14", "21:15", "22:00", "23:58", "23:59", "12:00", "03:30", "18:45"]


def params(rng, level, i):
    return {
        "level": level, "money": rng.choice(["cents", "dollars"]), "other": rng.choice(["other", "standard", "day", "flat"]), "total": rng.choice(["total", "due", "sum"]),
        "window": level >= 2, "allow": level >= 3, "tax": level >= 4, "theme": THEMES[(i + rng.randrange(2)) % len(THEMES)],
    }


def sol(lang, p):
    src = {"python": PY, "javascript": JS, "ruby": RB, "c": CC}[lang]
    L = lambda s: K.lit(lang, s)  # noqa: E731
    b = (lambda v: "True" if v else "False") if lang == "python" else (lambda v: "1" if v else "0") if lang == "c" else (lambda v: "true" if v else "false")  # noqa: E731
    return K.subst(src, MONEY=L(p["money"]), MONEY_CENTS="1" if p["money"] == "cents" else "0", L_OTHER=L(p["other"]), L_TOTAL=L(p["total"]), WINDOW=b(p["window"]), ALLOW=b(p["allow"]), TAX=b(p["tax"])).lstrip("\n")


def minutes(spec):
    s, e = spec.split("-")
    sm, em = int(s[:2]) * 60 + int(s[3:]), int(e[:2]) * 60 + int(e[3:])
    return set(range(sm, em)) if sm < em else set(range(sm, 1440)) | set(range(0, em))


def rand_plan(rng, p, full=False):
    lines = [f"rate {rng.choice([1, 5, 150, 500, 999, 12345, 999999])}"]
    if rng.random() < 0.8 or full:
        lines.append(f"base {rng.choice([0, 100, 1200, 4599, 9999999])}")
    if rng.random() < 0.6 or full:
        lines.append(f"round {rng.choice(['up', 'down', 'nearest'])}")
    names = [p["other"], "base"]
    if p["window"]:
        chosen, used = [], set()
        for nm, spec in rng.sample(WINDOWS, len(WINDOWS)):
            if len(chosen) >= (rng.randint(1, 3) if not full else 3):
                break
            if not (minutes(spec) & used):
                used |= minutes(spec)
                chosen.append((nm, spec))
        for nm, spec in chosen:
            lines.append(f"window {nm} {spec} {rng.choice([1, 40, 80, 250, 999, 31415, 999999])}")
        names += [c[0] for c in chosen] + ["minimum"]
        if rng.random() < 0.5 or full:
            lines.append(f"minimum {rng.choice([0, 500, 2000, 5000, 100000])}")
    if p["allow"]:
        names += ["allow", "demand"]
        if rng.random() < 0.55 or full:
            lines.append(f"allow {rng.choice([1, 100, 500, 2500, 9999999])} {rng.choice([0, 0, 10, 100])}")
        if rng.random() < 0.55 or full:
            ms = rng.sample(range(1, 13), rng.randint(1, 4))
            lines.append(f"season {','.join(map(str, ms))} {rng.choice([1, 50, 100, 125, 150, 500])}")
        if rng.random() < 0.5 or full:
            lines.append(f"demand {rng.choice([1, 3, 10, 250])}")
    if p["tax"]:
        if rng.random() < 0.7 or full:
            lines.append(f"tax {rng.choice([1, 5, 7, 10, 20, 100])}")
            for nm in rng.sample(names, rng.randint(0, min(3, len(names)))):
                lines.append(f"exempt {nm}")
        if rng.random() < 0.5 or full:
            lines.append(f"credit {rng.choice([1, 50, 500, 5000, 9999999])}")
    rng.shuffle(lines)
    return "\n".join(lines) + ("\n" if rng.random() < 0.3 else "")


def rand_readings(rng, n=None):
    n = rng.randint(0, 14) if n is None else n
    ls = []
    for _ in range(n):
        month = rng.choice([1, 5, 6, 7, 8, 12])
        day = rng.randint(1, 28)
        units = rng.choice([0, 1, 7, 50, 100, 250, 999, 4000, 123456, 999999, rng.randrange(0, 5000)])
        ls.append(f"2024-{month:02d}-{day:02d} {rng.choice(TIMES)} {units}")
    return "\n".join(ls) + ("\n" if ls and rng.random() < 0.3 else "")


def make_cases(rng, p, ns):
    cases = []
    L = p["level"]

    def add(a, b):
        cases.append((a, b))

    for k in range(60 if L >= 3 else 44):
        add(rand_plan(rng, p, full=(k % 6 == 0)), rand_readings(rng))
    # rounding edges
    for rate, units in [(500, 100), (500, 101), (5, 10), (1, 1), (99999, 1), (100000 - 1, 1), (50000, 1), (50001, 1), (49999, 1), (150, 1000), (3, 33334), (3, 33333)]:
        for md in ("up", "down", "nearest"):
            add(f"rate {rate}\nround {md}", f"2024-06-01 10:00 {units}")
    add("rate 5", "")
    add("rate 5\n", "\n")
    add("base 100\nrate 5", "2024-06-01 10:00 0")
    add("rate 999999\nbase 9999999", "\n".join(f"2024-06-{d:02d} 10:00 999999" for d in range(1, 29)))
    add("rate 7", "2024-06-01 10:00 5\n2024-06-01 10:00 6\n2024-05-31 23:59 7")
    # plan errors
    errs = ["", "\n", "base 100", "round up", "rate", "rate 0", "rate 1000000", "rate 01", "rate -5", "rate 1.5", "rate x", "rate 5 6", "rate  5", " rate 5", "rate 5 ", "Rate 5", "rate 5\nrate 6", "rate 5\n\nbase 1", "rate 5\nbase", "rate 5\nbase -1", "rate 5\nbase 10000000", "rate 5\nbase 9999999",
            "rate 5\nbase 1\nbase 2", "rate 5\nround", "rate 5\nround UP", "rate 5\nround upward", "rate 5\nround up\nround down", "rate 5\nround up down", "rate 5\nbogus 1", "rate 5\nbogus", "rate 5\n#c", "rate 5\nrate", "base x\nrate 5\nbogus"]
    if p["window"]:
        errs += ["rate 5\nwindow", "rate 5\nwindow a", "rate 5\nwindow a 01:00-02:00", "rate 5\nwindow a 01:00-02:00 5 6", "rate 5\nwindow a 01:00-02:00 0", "rate 5\nwindow a 01:00-02:00 1000000", "rate 5\nwindow A 01:00-02:00 5", "rate 5\nwindow abcdefghi 01:00-02:00 5", "rate 5\nwindow a1 01:00-02:00 5", "rate 5\nwindow a 01:00-01:00 5",
                 "rate 5\nwindow a 1:00-02:00 5", "rate 5\nwindow a 01:00-24:00 5", "rate 5\nwindow a 01:60-02:00 5", "rate 5\nwindow a 01:00 5", "rate 5\nwindow a 01:00-02:00-03:00 5", "rate 5\nwindow a 01:00_02:00 5", "rate 5\nwindow a -02:00 5", "rate 5\nwindow a 01:00- 5", "rate 5\nwindow " + p["other"] + " 01:00-02:00 5",
                 "rate 5\nwindow a 01:00-02:00 5\nwindow a 03:00-04:00 5", "rate 5\nwindow a 01:00-03:00 5\nwindow b 02:00-04:00 5", "rate 5\nwindow a 01:00-03:00 5\nwindow b 03:00-04:00 5", "rate 5\nwindow a 22:00-02:00 5\nwindow b 01:00-03:00 5", "rate 5\nwindow a 22:00-02:00 5\nwindow b 02:00-03:00 5", "rate 5\nwindow a 22:00-02:00 5\nwindow b 23:00-23:30 5",
                 "rate 5\nwindow a 22:00-00:00 5\nwindow b 00:00-01:00 5", "rate 5\nwindow a 22:00-00:00 5\nwindow b 23:59-00:01 5", "rate 5\nwindow a 00:00-23:59 5\nwindow b 23:59-00:00 5", "rate 5\nwindow a 00:00-23:59 5\nwindow b 23:58-00:00 5", "rate 5\nwindow b 02:00-04:00 5\nwindow a 01:00-03:00 x", "rate 5\nwindow b 02:00-04:00 5\nwindow b 01:00-03:00 x",
                 "rate 5\nminimum", "rate 5\nminimum -1", "rate 5\nminimum 10000000", "rate 5\nminimum 0", "rate 5\nminimum 5\nminimum 6", "rate 5\nminimum x"]
    else:
        errs += ["rate 5\nwindow a 01:00-02:00 5", "rate 5\nminimum 100"]
    if p["allow"]:
        errs += ["rate 5\nallow", "rate 5\nallow 100", "rate 5\nallow 0 5", "rate 5\nallow 100 1000000", "rate 5\nallow 10000000 5", "rate 5\nallow 100 5 6", "rate 5\nallow 100 5\nallow 200 5", "rate 5\nallow x 5", "rate 5\nallow 100 x", "rate 5\nallow 100 0", "rate 5\nseason", "rate 5\nseason 6", "rate 5\nseason 6 0", "rate 5\nseason 6 501", "rate 5\nseason 0 100",
                 "rate 5\nseason 13 100", "rate 5\nseason 06 100", "rate 5\nseason 6,6 100", "rate 5\nseason 6,,7 100", "rate 5\nseason 6, 100", "rate 5\nseason ,6 100", "rate 5\nseason 6,7, 100", "rate 5\nseason a 100", "rate 5\nseason 6;7 100", "rate 5\nseason 1,2,3,4,5,6,7,8,9,10,11,12 100", "rate 5\nseason 6 100\nseason 7 100", "rate 5\ndemand", "rate 5\ndemand 0", "rate 5\ndemand 10000000",
                 "rate 5\ndemand 1 2", "rate 5\ndemand 5\ndemand 6", "rate 5\ndemand x"]
    else:
        errs += ["rate 5\nallow 100 5", "rate 5\nseason 6 100", "rate 5\ndemand 3"]
    if p["tax"]:
        errs += ["rate 5\ntax", "rate 5\ntax 0", "rate 5\ntax 101", "rate 5\ntax 100", "rate 5\ntax 5\ntax 6", "rate 5\ntax x", "rate 5\ntax 5 6", "rate 5\nexempt", "rate 5\nexempt base base", "rate 5\nexempt base\nexempt base", "rate 5\nexempt " + p["other"], "rate 5\nexempt nowhere", "rate 5\nexempt Base", "rate 5\nexempt abcdefghi",
                 "rate 5\nexempt nowhere\nbogus", "rate 5\nexempt nowhere\nwindow nowhere 01:00-02:00 5", "rate 5\nwindow w 01:00-02:00 5\nexempt w", "rate 5\nexempt w\nwindow w 01:00-02:00 5", "rate 5\nexempt minimum", "rate 5\nexempt demand", "rate 5\nexempt allow", "rate 5\ncredit", "rate 5\ncredit 0", "rate 5\ncredit 10000000", "rate 5\ncredit 5\ncredit 6", "rate 5\ncredit x",
                 "exempt nowhere", "exempt base\nrate 5\nexempt base", "exempt nowhere\nexempt nowhere"]
    else:
        errs += ["rate 5\ntax 5", "rate 5\nexempt base", "rate 5\ncredit 5"]
    for e in errs:
        add(e, "2024-06-01 10:00 5")
        if rng.random() < 0.3:
            add(e, "bad")
    # readings errors
    for r in ["a", "2024-06-01", "2024-06-01 10:00", "2024-06-01 10:00 5 6", "2024-06-01  10:00 5", " 2024-06-01 10:00 5", "2024-06-01 10:00 5 ", "2024-6-01 10:00 5", "2024-06-1 10:00 5", "24-06-01 10:00 5", "2024/06/01 10:00 5", "2024-13-01 10:00 5", "2024-00-01 10:00 5", "2024-06-00 10:00 5", "2024-06-32 10:00 5", "2024-06-31 10:00 5", "2024-02-31 10:00 5",
              "2024-06-01T10:00 5", "2024-06-01 10:00:00 5", "2024-06-01 1:00 5", "2024-06-01 24:00 5", "2024-06-01 10:60 5", "2024-06-01 10:00 -5", "2024-06-01 10:00 05", "2024-06-01 10:00 1.5", "2024-06-01 10:00 x", "2024-06-01 10:00 1000000", "2024-06-01 10:00 999999", "2024-06-01 10:00 0", "2024-06-01 10:00 00", "2024-06-01 10:00 ",
              "2024-06-01 10:00 5\n\n2024-06-01 10:00 5", "2024-06-01 10:00 5\n2024-06-01 10:00 5\n\n", "\n2024-06-01 10:00 5", "2024-06-01 10:00 5\nbad\nworse", "2024-06-01 10:00 5\n2024-13-01 10:00 5\n2024-06-01 25:00 5", "\n"]:
        add("rate 5\nbase 100", r)
    add("bogus", "bad")
    add("", "bad")
    add("rate 5", "bad")
    # window and season structure
    if p["window"]:
        pl = "rate 100\nwindow night 22:00-06:00 40\nwindow peak 16:00-20:00 300\nwindow wrap 23:59-00:00 7\nbase 50"
        for t in TIMES:
            add(pl, f"2024-06-01 {t} 100")
        add(pl, "\n".join(f"2024-06-01 {t} {10 + i}" for i, t in enumerate(TIMES)))
        add("rate 100\nwindow all 00:00-23:59 40\nwindow last 23:59-00:00 9", "2024-06-01 00:00 10\n2024-06-01 23:59 10\n2024-06-01 12:00 10")
        add("rate 100\nwindow a 00:00-00:01 40", "2024-06-01 00:00 10\n2024-06-01 00:01 10")
        add("rate 100\nminimum 5000\nbase 100", "2024-06-01 12:00 10")
        add("rate 100\nminimum 5000\nbase 100", "2024-06-01 12:00 5000")
        add("rate 100\nminimum 0", "")
        add("rate 100\nminimum 100\nbase 100", "")
    if p["allow"]:
        pl = "rate 1000\nallow 100 100\nwindow night 22:00-06:00 500\nseason 6,7 150"
        add(pl, "2024-06-01 23:00 60\n2024-06-01 08:00 60\n2024-06-01 09:00 60")
        add(pl, "2024-06-01 09:00 60\n2024-06-01 23:00 60\n2024-06-01 08:00 60")
        add(pl, "2024-06-02 23:00 60\n2024-06-01 23:00 60\n2024-06-01 08:00 60")
        add(pl, "2024-05-31 23:00 100\n2024-06-01 08:00 100")
        add(pl, "2024-05-31 23:00 99\n2024-06-01 08:00 100")
        add(pl, "2024-05-31 23:00 101\n2024-06-01 08:00 100")
        add("rate 1000\nallow 100 0\ndemand 5", "2024-06-01 08:00 40\n2024-06-01 09:00 400\n2024-06-01 10:00 7")
        add("rate 1000\ndemand 5", "")
        add("rate 1000\ndemand 5", "2024-06-01 10:00 0")
        add("rate 1000\nseason 5,6 200", "2024-05-01 10:00 100\n2024-06-01 10:00 100\n2024-07-01 10:00 100")
        add("rate 1000\nseason 1 1\nround up", "2024-01-01 10:00 1\n2024-01-01 10:00 2")
        add("rate 1000\nseason 12 500\nallow 3 0", "2024-12-01 10:00 2\n2024-12-02 10:00 2")
    if p["tax"]:
        pl = "rate 1000\nbase 1000\nwindow night 22:00-06:00 500\nminimum 20000\ntax 10\nexempt base\nexempt night\nallow 10 0\ndemand 2\ncredit 700" if p["allow"] else "rate 1000\nbase 1000\nwindow night 22:00-06:00 500\nminimum 20000\ntax 10\nexempt base\nexempt night\ncredit 700"
        for rd in ["", "2024-06-01 23:00 100\n2024-06-01 12:00 100", "2024-06-01 23:00 1000\n2024-06-01 12:00 1000", "2024-06-01 12:00 3"]:
            add(pl, rd)
            for md in ("up", "down", "nearest"):
                add(pl + "\nround " + md, rd)
        add("rate 1000\ncredit 100000", "2024-06-01 12:00 10")
        add("rate 1000\ncredit 100000\ntax 10", "2024-06-01 12:00 10")
        add("rate 1000\nbase 500\ntax 100\nexempt minimum\nminimum 900", "")
        add("rate 1000\nbase 500\ntax 100\nexempt base\nminimum 900", "")
        add("rate 1000\nbase 500\ntax 3\nround up", "2024-06-01 12:00 1")
    # examples
    ex = [("rate 150\nbase 1200", "2024-06-03 08:15 4000\n2024-06-17 19:40 1500")]
    if p["window"]:
        ex.append(("rate 150\nwindow night 22:00-06:00 80\nminimum 2500\nbase 600", "2024-06-03 23:30 400\n2024-06-04 07:00 1000\n2024-06-04 02:00 150"))
    if p["allow"]:
        ex.append(("rate 200\nallow 100 0\nseason 6,7 150\ndemand 3\nround up", "2024-06-04 09:00 80\n2024-06-03 09:00 70\n2024-05-30 09:00 40"))
    if p["tax"]:
        ex.append(("rate 100\nbase 1000\ntax 10\nexempt base\ncredit 50\nround down", "2024-06-04 09:00 1234"))
    nex = len(ex)
    out, seen = [], set()
    for c in ex + cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex


def readme(p, api, lang, examples):
    oth, tot = p["other"], p["total"]
    X = [f"# Rate-plan billing for {p['theme']}", ""]
    X.append(f"`bill(plan, readings)` prices a list of meter readings with a rate plan and returns the invoice text for {p['theme']}. All money is computed with exact integer arithmetic.")
    X.append("")
    X.append("## The readings")
    X.append("")
    X.append("`readings` is text made of lines separated by `\\n` (empty text means no readings; one final `\\n` is allowed; any other empty line is an error). Each line is `DATE TIME UNITS`, three fields separated by single spaces:")
    X.append("")
    X.append("* `DATE`: `YYYY-MM-DD`, written exactly so; month `01` to `12`, day `01` to `31` (no per-month check). Only the month matters for pricing.")
    X.append("* `TIME`: `HH:MM`, hour `00` to `23`, minute `00` to `59`.")
    X.append("* `UNITS`: whole units used since the previous reading: 1 to 6 digits, no leading zeros (`0` is fine).")
    X.append("")
    X.append("A bad line is `error: reading N: WHY` (`N` counts from 1; the first bad line): `fields` (not three fields), then `date`, `time`, `units` (the first bad field).")
    X.append("")
    X.append("## The plan")
    X.append("")
    X.append("`plan` is text in the same line layout (lines separated by `\\n`, one final `\\n` allowed). Each line is a directive: a word and its arguments separated by single spaces. All numbers are written in decimal without sign, leading zeros or blanks, at most 7 digits. A **milli-rate** is a price per unit in thousandths of a cent (`150` means 0.15 cents per unit).")
    X.append("")
    ds = ["* `rate MILLI`: the default milli-rate, 1 to 999999. **Required**.", "* `base CENTS`: a fixed charge, 0 to 9999999. Default 0.", "* `round up|down|nearest`: how fractions of a cent are rounded (see below). Default `nearest`."]
    if p["window"]:
        ds += [f"* `window NAME HH:MM-HH:MM MILLI`: readings whose time falls in the window use `MILLI` (1 to 999999) instead of the default rate. `NAME` is 1 to 8 lower-case ASCII letters and not `{oth}`. The window starts at the first time (included) and ends at the second (excluded); if the second time is **earlier** than the first the window wraps around midnight (`22:00-06:00`, or `22:00-00:00` for the evening only); equal times are not allowed. May be repeated.",
               "* `minimum CENTS`: the invoice is raised to at least this many cents (0 to 9999999)."]
    if p["allow"]:
        ds += ["* `allow UNITS MILLI`: the first `UNITS` (1 to 9999999) units of the bill, taken in time order, cost `MILLI` (0 to 999999) per unit instead of the usual rate.", "* `season M,M,... PCT`: readings in these months (numbers 1 to 12 without leading zeros, no repeats, separated by single commas) pay `PCT` percent (1 to 500) of the normal price.",
               "* `demand CENTS`: a demand charge of `CENTS` (1 to 9999999) cents for each unit of the **largest single reading**."]
    if p["tax"]:
        ds += ["* `tax PCT`: a tax of `PCT` percent (1 to 100) on the taxable lines.", f"* `exempt NAME`: the invoice line `NAME` is not taxed. `NAME` is `base`, `{oth}`, `minimum`, `demand`, `allow` or the name of a window of the plan (anywhere in the plan). May be repeated.", "* `credit CENTS`: a credit of up to `CENTS` cents (1 to 9999999) taken off at the end."]
    X += ds
    X.append("")
    single = "`rate`, `base`, `round`" + (", `minimum`" if p["window"] else "") + (", `allow`, `season`, `demand`" if p["allow"] else "") + (", `tax`, `credit`" if p["tax"] else "")
    X.append(f"Each of {single} may appear **once** (a second use is `duplicate`)" + ("; a window name or an `exempt` name may not repeat either" if p["window"] or p["tax"] else "") + ". Problems in the plan are `error: plan N: WHY` for the first line with one, in this order of checks for a line: `unknown` (not a directive of this list; an empty line counts), `argument` (wrong number of arguments or an invalid one), `duplicate`" + (", `overlap` (a window shares at least one minute of the day with an earlier window)" if p["window"] else "") +
             (". An `exempt` name that is not known is checked after the whole plan was read, as `argument` on its line" if p["tax"] else "") + ". If nothing else is wrong but there is no `rate` line the result is `error: plan: no rate`. Plan problems come before reading problems.")
    X.append("")
    X.append("## Pricing")
    X.append("")
    X.append("The readings are processed in **time order**: ascending by `DATE`, then `TIME`, ties in input order. For every reading:")
    X.append("")
    X.append(f"1. its price per unit is " + (f"the milli-rate of the window it falls in, or the default `rate` if there is none (that is invoice line `{oth}`)" if p["window"] else f"the default `rate` (invoice line `{oth}`)") + ".")
    n = 2
    if p["allow"]:
        X.append(f"{n}. while some `allow` units are left, up to that many units of the reading are priced at the allowance milli-rate instead (they belong to the invoice line `allow`); the rest follows the rule above.")
        n += 1
        X.append(f"{n}. if the reading's month is in the `season` list, its price is multiplied by `PCT / 100`.")
        n += 1
    X.append(f"{n}. a reading's cost is `units * milli-rate * PCT / 100` in thousandths of a cent (`PCT` is 100 without a season); no rounding yet.")
    X.append("")
    X.append("An invoice line adds up the costs of its readings **exactly** and only then converts to whole cents: `cents = cost / 100000` (cost in thousandths of a cent times percent, so divide by 1000 and by 100), rounded by the plan's `round` mode: `nearest` rounds halves up, `up` is the ceiling, `down` the floor.")
    X.append("")
    X.append("## The invoice")
    X.append("")
    lines = ["`base AMOUNT`"] + (["`allow UNITS units AMOUNT` (only when the plan has `allow`)"] if p["allow"] else []) + ([f"one `NAME UNITS units AMOUNT` line per window, in the order the windows appear in the plan"] if p["window"] else []) + [f"`{oth} UNITS units AMOUNT`"] + (["`demand AMOUNT` (only with `demand`; the `UNITS` of the largest single reading times the demand `CENTS`; 0 without readings)"] if p["allow"] else []) + \
        (["`minimum AMOUNT` (only if the sum so far is below the plan's `minimum`; AMOUNT is the difference)"] if p["window"] else []) + (["`tax AMOUNT` (only with `tax`): the sum of all lines above that are not exempt, times `PCT / 100`, rounded in the plan's mode (cents)", "`credit AMOUNT` (only with `credit`): the amount is **negative**: minus the smaller of `CENTS` and the sum of all lines so far (so the invoice never goes below 0)"] if p["tax"] else []) + [f"`{tot} AMOUNT`: the sum of all amounts above"]
    X.append("The invoice lists, in this order (joined by `\\n`, no trailing newline):")
    X.append("")
    X += [f"* {ln}" for ln in lines]
    X.append("")
    X.append("`UNITS` is the number of units priced on that line (for window and default lines those not covered by the allowance). " + ("Amounts are written in cents as plain integers (`-50`, `1200`)." if p["money"] == "cents" else "Amounts are written in dollars with two decimals: `D.CC` (`12.00`, `0.05`, `-0.50`), where cents `c` print as `c div 100`, a dot and `c mod 100` on two digits, with a leading `-` for negative amounts."))
    X.append("")
    X.append(K.interface_section(api, lang))
    X.append("## Examples")
    X.append("")
    for k, ((pl, rd), out) in enumerate(examples):
        X.append(f"**Example {k + 1}**")
        X.append("")
        X.append("```")
        X.append("plan:")
        X += ["  " + ln for ln in pl.split("\n")]
        X.append("readings:")
        X += ["  " + ln for ln in rd.split("\n")] if rd else ["  (empty)"]
        X.append("invoice:")
        X += ["  " + ln for ln in out.split("\n")]
        X.append("```")
        X.append("")
    X.append(K.run_hint(lang, api.mod))
    return "\n".join(X) + "\n"


def prompt(rng, p, api, lang):
    where = api.short(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    feats = ["flat rates and rounding"] + (["time-of-day windows and a minimum bill"] if p["window"] else []) + (["an allowance, seasonal prices and a demand charge"] if p["allow"] else []) + (["tax with exemptions and a credit"] if p["tax"] else [])
    fl = ", ".join(feats[:-1]) + (" and " if len(feats) > 1 else "") + feats[-1]
    opts = [
        f"Write a rate-plan billing engine for {p['theme']} in {ln}: `{fn}(plan, readings)` in {where}, as README.md specifies ({fl}). {K.closer(rng)}",
        f"Implement `{fn}` ({ln}, {where}) from README.md: it prices meter readings with a plan text and returns an invoice. Features: {fl}. Rounding and the order of errors are specified exactly. {K.closer(rng)}",
        f"{ln} task: invoice calculator for {p['theme']}. `{fn}` in {where}; README.md has the plan directives, the pricing rules and the output format ({fl}).",
        f"Please build the billing function described in README.md ({ln}; `{fn}`; {where}). This version covers {fl}. Hidden checks probe rounding edges and malformed plans.",
    ]
    return rng.choice(opts).strip()


LANG_PLAN = ["c", "ruby", "javascript", "python", "c", "ruby", "javascript", "c"]
LEVELS = [1, 1, 2, 2, 3, 3, 4, 4]


@family("greenfield-ratebill", category="greenfield", lang="mixed", kind="greenfield", n=8,
        summary="rate-plan billing: milli-rate pricing with exact rational sums and three rounding modes, wrapping time windows, minimum bill, chronological allowance, seasons, demand charge, tax with exemptions and credit")
def gen(rng, n):
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = LEVELS[i % len(LEVELS)]
        p = params(rng, level, i)
        api = K.Api(mod="ratebill", fn="bill", args=["plan", "readings"], arg_docs=["the plan text (one directive per line)", "the meter readings text (one reading per line)"], ret_doc="the invoice text, or an error text", doc="rate-plan billing")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["bill"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=level, slug=f"{i + 1:02d}-{lang}-{p['money']}-l{level}", oracle=(None if lang == "python" else ns["bill"]),
            tags=["billing", "parser", "money"], notes={"level": level, "money": p["money"]},
        )
