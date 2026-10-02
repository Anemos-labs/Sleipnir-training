"""Event-sourced lending ledger: append-only log, folded state, expected-version conflicts, clock and fees, as-of queries, snapshots and compaction (invented domain)."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

PY = r'''
ITEM = @ITEM@
WHO = @WHO@
LIMIT = @LIMIT@
MAXD = @MAXD@
RATE = @RATE@
HAS_VER = @VER@
HAS_CLOCK = @CLOCK@
HAS_ASOF = @ASOF@
HAS_SNAP = @SNAP@
LOW = "abcdefghijklmnopqrstuvwxyz"
DG = "0123456789"


def good_name(s):
    return 1 <= len(s) <= 10 and s[0] in LOW and all(c in LOW + DG + "_" for c in s)


def num_text(s):
    return 1 <= len(s) <= 6 and all(c in DG for c in s) and (len(s) == 1 or s[0] != "0")


def num_in(s, lo, hi):
    return num_text(s) and lo <= int(s) <= hi


def copy_state(st):
    return {"who": {k: {"fees": v["fees"], "rent": set(v["rent"])} for k, v in st["who"].items()}, "item": {k: dict(v) for k, v in st["item"].items()}}


def apply_event(st, ev):
    seq, typ, f = ev
    if typ == "Registered":
        st["who"][f[WHO]] = {"fees": 0, "rent": set()}
    elif typ == "Commissioned":
        st["item"][f[ITEM]] = {"seats": f["seats"], "renter": None, "due": 0, "rseq": 0}
    elif typ == "Rented":
        b = st["item"][f[ITEM]]
        b["renter"], b["due"], b["rseq"] = f[WHO], f["day"] + f["days"], seq
        st["who"][f[WHO]]["rent"].add(f[ITEM])
    elif typ in ("Returned", "Voided"):
        st["item"][f[ITEM]]["renter"] = None
        st["who"][f[WHO]]["rent"].discard(f[ITEM])
    elif typ == "FeeCharged":
        st["who"][f[WHO]]["fees"] += f["amount"]
    elif typ == "Paid":
        st["who"][f[WHO]]["fees"] -= f["amount"]


def fmt_event(ev):
    seq, typ, f = ev
    return "#%d %s %s" % (seq, typ, " ".join("%s=%s" % (k, v) for k, v in f.items()))


def stream_of(ev):
    typ, f = ev[1], ev[2]
    if typ in ("Commissioned", "Rented", "Returned", "Voided"):
        return ITEM + ":" + f[ITEM]
    return WHO + ":" + f[WHO]


class Store:
    def __init__(self):
        self.events = []
        self.seq = 0
        self.versions = {}
        self.base_state = {"who": {}, "item": {}}
        self.base_seq = 0
        self.base_versions = {}
        self.snap = None
        self.clock = 0

    def state(self, upto=None):
        st = copy_state(self.base_state)
        for ev in self.events:
            if upto is None or ev[0] <= upto:
                apply_event(st, ev)
        return st

    def append(self, typ, fields):
        self.seq += 1
        ev = (self.seq, typ, fields)
        self.events.append(ev)
        s = stream_of(ev)
        self.versions[s] = self.versions.get(s, 0) + 1
        return self.seq

    def version(self, stream, upto=None):
        if upto is None:
            return self.versions.get(stream, 0)
        n = self.base_versions.get(stream, 0)
        for ev in self.events:
            if ev[0] <= upto and stream_of(ev) == stream:
                n += 1
        return n


def run_query(store, st, w, upto):
    v = w[0]
    if v == ITEM and len(w) == 2:
        b = st["item"].get(w[1])
        if b is None:
            return ["no such " + ITEM]
        if b["renter"] is None:
            return ["%s seats=%d free" % (w[1], b["seats"])]
        return ["%s seats=%d rented by %s until %d" % (w[1], b["seats"], b["renter"], b["due"])]
    if v == WHO and len(w) == 2:
        m = st["who"].get(w[1])
        if m is None:
            return ["no such " + WHO]
        s = "%s rentals=%s" % (w[1], ",".join(sorted(m["rent"])) or "-")
        if HAS_CLOCK:
            s += " fees=%d" % m["fees"]
        return [s]
    if v == "log" and len(w) in (1, 2):
        frm = 1
        if len(w) == 2:
            if not num_text(w[1]):
                return None
            frm = int(w[1])
        evs = [e for e in store.events if e[0] >= frm and (upto is None or e[0] <= upto)]
        return [fmt_event(e) for e in evs] or ["(empty)"]
    if HAS_VER and v == "version" and len(w) == 2:
        return ["%s version %d" % (w[1], store.version(w[1], upto))]
    if HAS_ASOF and v == "history" and len(w) == 2:
        evs = [e for e in store.events if stream_of(e) == ITEM + ":" + w[1] and (upto is None or e[0] <= upto)]
        return [fmt_event(e) for e in evs] or ["(empty)"]
    return None


def run(script):
    store = Store()
    out = []
    for cmd in script.split("\n"):
        if cmd == "":
            continue
        out.append("> " + cmd)
        out.extend(do(store, cmd))
    return "\n".join(out)


def do(store, cmd):
    w = cmd.split(" ")
    exp = None
    bad = ["error: command"]
    if HAS_VER and len(w) > 1 and w[-1].startswith("@"):
        if not num_text(w[-1][1:]) and w[-1][1:] != "0":
            return bad
        exp = int(w[-1][1:])
        w = w[:-1]
    v = w[0]
    if HAS_ASOF and v == "asof" and exp is None:
        if len(w) < 3 or not num_text(w[1]):
            return bad
        n = int(w[1])
        if HAS_SNAP and n < store.base_seq:
            return ["error: compacted"]
        if n > store.seq:
            return ["error: future"]
        res = run_query(store, store.state(n), w[2:], n)
        return res if res is not None else bad
    if exp is None:
        q = run_query(store, store.state(), w, None)
        if q is not None:
            return q
    st = store.state()

    def conflict(stream):
        return exp is not None and store.version(stream) != exp

    if v == "register" and len(w) == 2 and good_name(w[1]):
        if conflict(WHO + ":" + w[1]):
            return ["rejected: conflict"]
        if w[1] in st["who"]:
            return ["rejected: exists"]
        return ["ok #%d" % store.append("Registered", {WHO: w[1]})]
    if v == "commission" and len(w) == 3 and good_name(w[1]) and num_in(w[2], 1, 12):
        if conflict(ITEM + ":" + w[1]):
            return ["rejected: conflict"]
        if w[1] in st["item"]:
            return ["rejected: exists"]
        return ["ok #%d" % store.append("Commissioned", {ITEM: w[1], "seats": int(w[2])})]
    if v == "rent" and len(w) == 4 and good_name(w[1]) and good_name(w[2]) and num_text(w[3]):
        who, item, days = w[1], w[2], int(w[3])
        if conflict(ITEM + ":" + item):
            return ["rejected: conflict"]
        if who not in st["who"]:
            return ["rejected: no " + WHO]
        if item not in st["item"]:
            return ["rejected: no " + ITEM]
        if not 1 <= days <= MAXD:
            return ["rejected: days"]
        if st["item"][item]["renter"] is not None:
            return ["rejected: busy"]
        if len(st["who"][who]["rent"]) >= LIMIT:
            return ["rejected: limit"]
        if HAS_CLOCK and st["who"][who]["fees"] > 0:
            return ["rejected: fees"]
        return ["ok #%d" % store.append("Rented", {ITEM: item, WHO: who, "days": days, "day": store.clock})]
    if v == "return" and len(w) == 2 and good_name(w[1]):
        item = w[1]
        if conflict(ITEM + ":" + item):
            return ["rejected: conflict"]
        if item not in st["item"]:
            return ["rejected: no " + ITEM]
        b = st["item"][item]
        if b["renter"] is None:
            return ["rejected: not rented"]
        who = b["renter"]
        seqs = [store.append("Returned", {ITEM: item, WHO: who, "day": store.clock})]
        late = store.clock - b["due"]
        if HAS_CLOCK and late > 0:
            seqs.append(store.append("FeeCharged", {WHO: who, "amount": late * RATE}))
        return ["ok " + " ".join("#%d" % s for s in seqs)]
    if HAS_CLOCK and v == "pay" and len(w) == 3 and good_name(w[1]) and num_text(w[2]):
        if conflict(WHO + ":" + w[1]):
            return ["rejected: conflict"]
        if w[1] not in st["who"]:
            return ["rejected: no " + WHO]
        if not 1 <= int(w[2]) <= st["who"][w[1]]["fees"]:
            return ["rejected: amount"]
        return ["ok #%d" % store.append("Paid", {WHO: w[1], "amount": int(w[2])})]
    if HAS_CLOCK and v == "tick" and len(w) == 2 and exp is None and num_in(w[1], 1, 365):
        store.clock += int(w[1])
        return ["day %d" % store.clock]
    if HAS_SNAP and v == "snapshot" and len(w) == 1 and exp is None:
        store.snap = (store.seq, copy_state(st), dict(store.versions))
        return ["snapshot at #%d" % store.seq]
    if HAS_SNAP and v == "compact" and len(w) == 1 and exp is None:
        if store.snap is None:
            return ["rejected: no snapshot"]
        s, state, vers = store.snap
        n = sum(1 for e in store.events if e[0] <= s)
        store.events = [e for e in store.events if e[0] > s]
        store.base_state, store.base_seq, store.base_versions = state, s, vers
        return ["compacted %d events" % n]
    if HAS_SNAP and v == "void" and len(w) == 2 and num_text(w[1]):
        n = int(w[1])
        ev = next((e for e in store.events if e[0] == n), None)
        if ev is None or ev[1] != "Rented":
            return ["rejected: cannot void"]
        item = ev[2][ITEM]
        if conflict(ITEM + ":" + item):
            return ["rejected: conflict"]
        b = st["item"][item]
        if b["renter"] is None or b["rseq"] != n:
            return ["rejected: cannot void"]
        return ["ok #%d" % store.append("Voided", {ITEM: item, WHO: ev[2][WHO], "target": n})]
    return bad
'''

RB = r'''
module Eventstore
  ITEM = @ITEM@
  WHO = @WHO@
  LIMIT = @LIMIT@
  MAXD = @MAXD@
  RATE = @RATE@
  HAS_VER = @VER@
  HAS_CLOCK = @CLOCK@
  HAS_ASOF = @ASOF@
  HAS_SNAP = @SNAP@
  LOW = 'abcdefghijklmnopqrstuvwxyz'
  DG = '0123456789'

  def self.good_name?(s)
    return false if s.length < 1 || s.length > 10 || !LOW.include?(s[0])
    s.each_char { |c| return false unless (LOW + DG + '_').include?(c) }
    true
  end

  def self.num_text?(s)
    return false if s.length < 1 || s.length > 6
    s.each_char { |c| return false unless DG.include?(c) }
    s.length == 1 || s[0] != '0'
  end

  def self.num_in?(s, lo, hi)
    num_text?(s) && s.to_i >= lo && s.to_i <= hi
  end

  def self.copy_state(st)
    who = {}
    st[:who].each { |k, v| who[k] = { fees: v[:fees], rent: v[:rent].dup } }
    item = {}
    st[:item].each { |k, v| item[k] = v.dup }
    { who: who, item: item }
  end

  def self.apply_event(st, ev)
    seq, typ, f = ev
    case typ
    when 'Registered' then st[:who][f[WHO]] = { fees: 0, rent: [] }
    when 'Commissioned' then st[:item][f[ITEM]] = { seats: f['seats'], renter: nil, due: 0, rseq: 0 }
    when 'Rented'
      b = st[:item][f[ITEM]]
      b[:renter] = f[WHO]
      b[:due] = f['day'] + f['days']
      b[:rseq] = seq
      st[:who][f[WHO]][:rent] << f[ITEM] unless st[:who][f[WHO]][:rent].include?(f[ITEM])
    when 'Returned', 'Voided'
      st[:item][f[ITEM]][:renter] = nil
      st[:who][f[WHO]][:rent].delete(f[ITEM])
    when 'FeeCharged' then st[:who][f[WHO]][:fees] += f['amount']
    when 'Paid' then st[:who][f[WHO]][:fees] -= f['amount']
    end
  end

  def self.fmt_event(ev)
    seq, typ, f = ev
    "##{seq} #{typ} " + f.map { |k, v| "#{k}=#{v}" }.join(' ')
  end

  def self.stream_of(ev)
    typ, f = ev[1], ev[2]
    return "#{ITEM}:#{f[ITEM]}" if %w[Commissioned Rented Returned Voided].include?(typ)
    "#{WHO}:#{f[WHO]}"
  end

  class Store
    attr_accessor :events, :seq, :versions, :base_state, :base_seq, :base_versions, :snap, :clock

    def initialize
      @events = []
      @seq = 0
      @versions = Hash.new(0)
      @base_state = { who: {}, item: {} }
      @base_seq = 0
      @base_versions = Hash.new(0)
      @snap = nil
      @clock = 0
    end

    def state(upto = nil)
      st = Eventstore.copy_state(@base_state)
      @events.each { |ev| Eventstore.apply_event(st, ev) if upto.nil? || ev[0] <= upto }
      st
    end

    def append(typ, fields)
      @seq += 1
      ev = [@seq, typ, fields]
      @events << ev
      @versions[Eventstore.stream_of(ev)] += 1
      @seq
    end

    def version(stream, upto = nil)
      return @versions[stream] if upto.nil?
      n = @base_versions[stream]
      @events.each { |ev| n += 1 if ev[0] <= upto && Eventstore.stream_of(ev) == stream }
      n
    end
  end

  def self.run_query(store, st, w, upto)
    v = w[0]
    if v == ITEM && w.length == 2
      b = st[:item][w[1]]
      return ["no such #{ITEM}"] if b.nil?
      return ["#{w[1]} seats=#{b[:seats]} free"] if b[:renter].nil?
      return ["#{w[1]} seats=#{b[:seats]} rented by #{b[:renter]} until #{b[:due]}"]
    end
    if v == WHO && w.length == 2
      m = st[:who][w[1]]
      return ["no such #{WHO}"] if m.nil?
      r = m[:rent].sort.join(',')
      r = '-' if r.empty?
      s = "#{w[1]} rentals=#{r}"
      s += " fees=#{m[:fees]}" if HAS_CLOCK
      return [s]
    end
    if v == 'log' && (w.length == 1 || w.length == 2)
      frm = 1
      if w.length == 2
        return nil unless num_text?(w[1])
        frm = w[1].to_i
      end
      evs = store.events.select { |e| e[0] >= frm && (upto.nil? || e[0] <= upto) }
      return evs.empty? ? ['(empty)'] : evs.map { |e| fmt_event(e) }
    end
    return ["#{w[1]} version #{store.version(w[1], upto)}"] if HAS_VER && v == 'version' && w.length == 2
    if HAS_ASOF && v == 'history' && w.length == 2
      evs = store.events.select { |e| stream_of(e) == "#{ITEM}:#{w[1]}" && (upto.nil? || e[0] <= upto) }
      return evs.empty? ? ['(empty)'] : evs.map { |e| fmt_event(e) }
    end
    nil
  end

  def self.run(script)
    store = Store.new
    out = []
    script.split("\n", -1).each do |cmd|
      next if cmd.empty?
      out << "> #{cmd}"
      out.concat(do_cmd(store, cmd))
    end
    out.join("\n")
  end

  def self.do_cmd(store, cmd)
    w = cmd.split(/ /, -1)
    exp = nil
    bad = ['error: command']
    if HAS_VER && w.length > 1 && w[-1].start_with?('@')
      return bad unless num_text?(w[-1][1..-1])
      exp = w[-1][1..-1].to_i
      w = w[0...-1]
    end
    v = w[0]
    if HAS_ASOF && v == 'asof' && exp.nil?
      return bad if w.length < 3 || !num_text?(w[1])
      n = w[1].to_i
      return ['error: compacted'] if HAS_SNAP && n < store.base_seq
      return ['error: future'] if n > store.seq
      res = run_query(store, store.state(n), w[2..-1], n)
      return res.nil? ? bad : res
    end
    if exp.nil?
      q = run_query(store, store.state, w, nil)
      return q unless q.nil?
    end
    st = store.state
    conflict = ->(stream) { !exp.nil? && store.version(stream) != exp }
    if v == 'register' && w.length == 2 && good_name?(w[1])
      return ['rejected: conflict'] if conflict.call("#{WHO}:#{w[1]}")
      return ['rejected: exists'] if st[:who].key?(w[1])
      return ["ok ##{store.append('Registered', [[WHO, w[1]]].to_h)}"]
    end
    if v == 'commission' && w.length == 3 && good_name?(w[1]) && num_in?(w[2], 1, 12)
      return ['rejected: conflict'] if conflict.call("#{ITEM}:#{w[1]}")
      return ['rejected: exists'] if st[:item].key?(w[1])
      return ["ok ##{store.append('Commissioned', { ITEM => w[1], 'seats' => w[2].to_i })}"]
    end
    if v == 'rent' && w.length == 4 && good_name?(w[1]) && good_name?(w[2]) && num_text?(w[3])
      who, item, days = w[1], w[2], w[3].to_i
      return ['rejected: conflict'] if conflict.call("#{ITEM}:#{item}")
      return ["rejected: no #{WHO}"] unless st[:who].key?(who)
      return ["rejected: no #{ITEM}"] unless st[:item].key?(item)
      return ['rejected: days'] unless days >= 1 && days <= MAXD
      return ['rejected: busy'] unless st[:item][item][:renter].nil?
      return ['rejected: limit'] if st[:who][who][:rent].length >= LIMIT
      return ['rejected: fees'] if HAS_CLOCK && st[:who][who][:fees] > 0
      return ["ok ##{store.append('Rented', { ITEM => item, WHO => who, 'days' => days, 'day' => store.clock })}"]
    end
    if v == 'return' && w.length == 2 && good_name?(w[1])
      item = w[1]
      return ['rejected: conflict'] if conflict.call("#{ITEM}:#{item}")
      return ["rejected: no #{ITEM}"] unless st[:item].key?(item)
      b = st[:item][item]
      return ['rejected: not rented'] if b[:renter].nil?
      who = b[:renter]
      seqs = [store.append('Returned', { ITEM => item, WHO => who, 'day' => store.clock })]
      late = store.clock - b[:due]
      seqs << store.append('FeeCharged', { WHO => who, 'amount' => late * RATE }) if HAS_CLOCK && late > 0
      return ['ok ' + seqs.map { |s| "##{s}" }.join(' ')]
    end
    if HAS_CLOCK && v == 'pay' && w.length == 3 && good_name?(w[1]) && num_text?(w[2])
      return ['rejected: conflict'] if conflict.call("#{WHO}:#{w[1]}")
      return ["rejected: no #{WHO}"] unless st[:who].key?(w[1])
      return ['rejected: amount'] unless w[2].to_i >= 1 && w[2].to_i <= st[:who][w[1]][:fees]
      return ["ok ##{store.append('Paid', { WHO => w[1], 'amount' => w[2].to_i })}"]
    end
    if HAS_CLOCK && v == 'tick' && w.length == 2 && exp.nil? && num_in?(w[1], 1, 365)
      store.clock += w[1].to_i
      return ["day #{store.clock}"]
    end
    if HAS_SNAP && v == 'snapshot' && w.length == 1 && exp.nil?
      store.snap = [store.seq, copy_state(st), store.versions.dup]
      return ["snapshot at ##{store.seq}"]
    end
    if HAS_SNAP && v == 'compact' && w.length == 1 && exp.nil?
      return ['rejected: no snapshot'] if store.snap.nil?
      s, state, vers = store.snap
      n = store.events.count { |e| e[0] <= s }
      store.events = store.events.select { |e| e[0] > s }
      store.base_state = state
      store.base_seq = s
      bv = Hash.new(0)
      vers.each { |k, x| bv[k] = x }
      store.base_versions = bv
      return ["compacted #{n} events"]
    end
    if HAS_SNAP && v == 'void' && w.length == 2 && num_text?(w[1])
      n = w[1].to_i
      ev = store.events.find { |e| e[0] == n }
      return ['rejected: cannot void'] if ev.nil? || ev[1] != 'Rented'
      item = ev[2][ITEM]
      return ['rejected: conflict'] if conflict.call("#{ITEM}:#{item}")
      b = st[:item][item]
      return ['rejected: cannot void'] if b[:renter].nil? || b[:rseq] != n
      return ["ok ##{store.append('Voided', { ITEM => item, WHO => ev[2][WHO], 'target' => n })}"]
    end
    bad
  end
end
'''

JV = r'''
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

public class Eventstore {
    static final String ITEM = @ITEM@;
    static final String WHO = @WHO@;
    static final int LIMIT = @LIMIT@;
    static final int MAXD = @MAXD@;
    static final int RATE = @RATE@;
    static final boolean HAS_VER = @VER@;
    static final boolean HAS_CLOCK = @CLOCK@;
    static final boolean HAS_ASOF = @ASOF@;
    static final boolean HAS_SNAP = @SNAP@;
    static final String LOW = "abcdefghijklmnopqrstuvwxyz";
    static final String DG = "0123456789";

    static class Ev {
        int seq;
        String type;
        Map<String, String> f = new LinkedHashMap<>();
    }

    static class Member {
        long fees;
        TreeSet<String> rent = new TreeSet<>();
    }

    static class Boat {
        int seats;
        String renter;
        long due;
        int rseq;
    }

    static class State {
        Map<String, Member> who = new HashMap<>();
        Map<String, Boat> item = new HashMap<>();

        State copy() {
            State s = new State();
            for (Map.Entry<String, Member> e : who.entrySet()) {
                Member m = new Member();
                m.fees = e.getValue().fees;
                m.rent = new TreeSet<>(e.getValue().rent);
                s.who.put(e.getKey(), m);
            }
            for (Map.Entry<String, Boat> e : item.entrySet()) {
                Boat b = new Boat();
                b.seats = e.getValue().seats;
                b.renter = e.getValue().renter;
                b.due = e.getValue().due;
                b.rseq = e.getValue().rseq;
                s.item.put(e.getKey(), b);
            }
            return s;
        }
    }

    static boolean goodName(String s) {
        if (s.length() < 1 || s.length() > 10 || LOW.indexOf(s.charAt(0)) < 0) return false;
        for (int i = 0; i < s.length(); i++) if ((LOW + DG + "_").indexOf(s.charAt(i)) < 0) return false;
        return true;
    }

    static boolean numText(String s) {
        if (s.length() < 1 || s.length() > 6) return false;
        for (int i = 0; i < s.length(); i++) if (DG.indexOf(s.charAt(i)) < 0) return false;
        return s.length() == 1 || s.charAt(0) != '0';
    }

    static boolean numIn(String s, int lo, int hi) {
        return numText(s) && Integer.parseInt(s) >= lo && Integer.parseInt(s) <= hi;
    }

    static void applyEvent(State st, Ev ev) {
        Map<String, String> f = ev.f;
        switch (ev.type) {
            case "Registered":
                st.who.put(f.get(WHO), new Member());
                break;
            case "Commissioned": {
                Boat b = new Boat();
                b.seats = Integer.parseInt(f.get("seats"));
                st.item.put(f.get(ITEM), b);
                break;
            }
            case "Rented": {
                Boat b = st.item.get(f.get(ITEM));
                b.renter = f.get(WHO);
                b.due = Long.parseLong(f.get("day")) + Long.parseLong(f.get("days"));
                b.rseq = ev.seq;
                st.who.get(f.get(WHO)).rent.add(f.get(ITEM));
                break;
            }
            case "Returned":
            case "Voided":
                st.item.get(f.get(ITEM)).renter = null;
                st.who.get(f.get(WHO)).rent.remove(f.get(ITEM));
                break;
            case "FeeCharged":
                st.who.get(f.get(WHO)).fees += Long.parseLong(f.get("amount"));
                break;
            case "Paid":
                st.who.get(f.get(WHO)).fees -= Long.parseLong(f.get("amount"));
                break;
            default:
                break;
        }
    }

    static String fmtEvent(Ev ev) {
        StringBuilder sb = new StringBuilder("#" + ev.seq + " " + ev.type + " ");
        boolean first = true;
        for (Map.Entry<String, String> e : ev.f.entrySet()) {
            if (!first) sb.append(' ');
            first = false;
            sb.append(e.getKey()).append('=').append(e.getValue());
        }
        return sb.toString();
    }

    static String streamOf(Ev ev) {
        switch (ev.type) {
            case "Commissioned":
            case "Rented":
            case "Returned":
            case "Voided":
                return ITEM + ":" + ev.f.get(ITEM);
            default:
                return WHO + ":" + ev.f.get(WHO);
        }
    }

    static class Store {
        List<Ev> events = new ArrayList<>();
        int seq = 0;
        Map<String, Integer> versions = new HashMap<>();
        State baseState = new State();
        int baseSeq = 0;
        Map<String, Integer> baseVersions = new HashMap<>();
        boolean hasSnap = false;
        int snapSeq;
        State snapState;
        Map<String, Integer> snapVersions;
        int clock = 0;

        State state(int upto) {
            State st = baseState.copy();
            for (Ev ev : events) if (upto < 0 || ev.seq <= upto) applyEvent(st, ev);
            return st;
        }

        int append(String type, String... kv) {
            seq++;
            Ev ev = new Ev();
            ev.seq = seq;
            ev.type = type;
            for (int i = 0; i < kv.length; i += 2) ev.f.put(kv[i], kv[i + 1]);
            events.add(ev);
            versions.merge(streamOf(ev), 1, Integer::sum);
            return seq;
        }

        int version(String stream, int upto) {
            if (upto < 0) return versions.getOrDefault(stream, 0);
            int n = baseVersions.getOrDefault(stream, 0);
            for (Ev ev : events) if (ev.seq <= upto && streamOf(ev).equals(stream)) n++;
            return n;
        }
    }

    static List<String> one(String s) {
        List<String> l = new ArrayList<>();
        l.add(s);
        return l;
    }

    static List<String> evLines(List<Ev> evs) {
        List<String> out = new ArrayList<>();
        for (Ev e : evs) out.add(fmtEvent(e));
        if (out.isEmpty()) out.add("(empty)");
        return out;
    }

    static List<String> runQuery(Store store, State st, String[] w, int upto) {
        String v = w[0];
        if (v.equals(ITEM) && w.length == 2) {
            Boat b = st.item.get(w[1]);
            if (b == null) return one("no such " + ITEM);
            if (b.renter == null) return one(w[1] + " seats=" + b.seats + " free");
            return one(w[1] + " seats=" + b.seats + " rented by " + b.renter + " until " + b.due);
        }
        if (v.equals(WHO) && w.length == 2) {
            Member m = st.who.get(w[1]);
            if (m == null) return one("no such " + WHO);
            String r = String.join(",", m.rent);
            String s = w[1] + " rentals=" + (r.isEmpty() ? "-" : r);
            if (HAS_CLOCK) s += " fees=" + m.fees;
            return one(s);
        }
        if (v.equals("log") && (w.length == 1 || w.length == 2)) {
            int frm = 1;
            if (w.length == 2) {
                if (!numText(w[1])) return null;
                frm = Integer.parseInt(w[1]);
            }
            List<Ev> evs = new ArrayList<>();
            for (Ev e : store.events) if (e.seq >= frm && (upto < 0 || e.seq <= upto)) evs.add(e);
            return evLines(evs);
        }
        if (HAS_VER && v.equals("version") && w.length == 2) return one(w[1] + " version " + store.version(w[1], upto));
        if (HAS_ASOF && v.equals("history") && w.length == 2) {
            List<Ev> evs = new ArrayList<>();
            for (Ev e : store.events) if (streamOf(e).equals(ITEM + ":" + w[1]) && (upto < 0 || e.seq <= upto)) evs.add(e);
            return evLines(evs);
        }
        return null;
    }

    static List<String> doCmd(Store store, String cmd) {
        String[] w = cmd.split(" ", -1);
        int exp = -1;
        List<String> bad = one("error: command");
        if (HAS_VER && w.length > 1 && w[w.length - 1].startsWith("@")) {
            String t = w[w.length - 1].substring(1);
            if (!numText(t)) return bad;
            exp = Integer.parseInt(t);
            w = Arrays.copyOf(w, w.length - 1);
        }
        String v = w[0];
        if (HAS_ASOF && v.equals("asof") && exp < 0) {
            if (w.length < 3 || !numText(w[1])) return bad;
            int n = Integer.parseInt(w[1]);
            if (HAS_SNAP && n < store.baseSeq) return one("error: compacted");
            if (n > store.seq) return one("error: future");
            List<String> res = runQuery(store, store.state(n), Arrays.copyOfRange(w, 2, w.length), n);
            return res == null ? bad : res;
        }
        if (exp < 0) {
            List<String> q = runQuery(store, store.state(-1), w, -1);
            if (q != null) return q;
        }
        State st = store.state(-1);
        final int fexp = exp;
        java.util.function.Predicate<String> conflict = (stream) -> fexp >= 0 && store.version(stream, -1) != fexp;
        if (v.equals("register") && w.length == 2 && goodName(w[1])) {
            if (conflict.test(WHO + ":" + w[1])) return one("rejected: conflict");
            if (st.who.containsKey(w[1])) return one("rejected: exists");
            return one("ok #" + store.append("Registered", WHO, w[1]));
        }
        if (v.equals("commission") && w.length == 3 && goodName(w[1]) && numIn(w[2], 1, 12)) {
            if (conflict.test(ITEM + ":" + w[1])) return one("rejected: conflict");
            if (st.item.containsKey(w[1])) return one("rejected: exists");
            return one("ok #" + store.append("Commissioned", ITEM, w[1], "seats", w[2]));
        }
        if (v.equals("rent") && w.length == 4 && goodName(w[1]) && goodName(w[2]) && numText(w[3])) {
            String who = w[1], item = w[2];
            int days = Integer.parseInt(w[3]);
            if (conflict.test(ITEM + ":" + item)) return one("rejected: conflict");
            if (!st.who.containsKey(who)) return one("rejected: no " + WHO);
            if (!st.item.containsKey(item)) return one("rejected: no " + ITEM);
            if (days < 1 || days > MAXD) return one("rejected: days");
            if (st.item.get(item).renter != null) return one("rejected: busy");
            if (st.who.get(who).rent.size() >= LIMIT) return one("rejected: limit");
            if (HAS_CLOCK && st.who.get(who).fees > 0) return one("rejected: fees");
            return one("ok #" + store.append("Rented", ITEM, item, WHO, who, "days", Integer.toString(days), "day", Integer.toString(store.clock)));
        }
        if (v.equals("return") && w.length == 2 && goodName(w[1])) {
            String item = w[1];
            if (conflict.test(ITEM + ":" + item)) return one("rejected: conflict");
            if (!st.item.containsKey(item)) return one("rejected: no " + ITEM);
            Boat b = st.item.get(item);
            if (b.renter == null) return one("rejected: not rented");
            String who = b.renter;
            StringBuilder sb = new StringBuilder("ok #" + store.append("Returned", ITEM, item, WHO, who, "day", Integer.toString(store.clock)));
            long late = store.clock - b.due;
            if (HAS_CLOCK && late > 0) sb.append(" #").append(store.append("FeeCharged", WHO, who, "amount", Long.toString(late * RATE)));
            return one(sb.toString());
        }
        if (HAS_CLOCK && v.equals("pay") && w.length == 3 && goodName(w[1]) && numText(w[2])) {
            if (conflict.test(WHO + ":" + w[1])) return one("rejected: conflict");
            if (!st.who.containsKey(w[1])) return one("rejected: no " + WHO);
            long amt = Long.parseLong(w[2]);
            if (amt < 1 || amt > st.who.get(w[1]).fees) return one("rejected: amount");
            return one("ok #" + store.append("Paid", WHO, w[1], "amount", w[2]));
        }
        if (HAS_CLOCK && v.equals("tick") && w.length == 2 && exp < 0 && numIn(w[1], 1, 365)) {
            store.clock += Integer.parseInt(w[1]);
            return one("day " + store.clock);
        }
        if (HAS_SNAP && v.equals("snapshot") && w.length == 1 && exp < 0) {
            store.hasSnap = true;
            store.snapSeq = store.seq;
            store.snapState = st.copy();
            store.snapVersions = new HashMap<>(store.versions);
            return one("snapshot at #" + store.seq);
        }
        if (HAS_SNAP && v.equals("compact") && w.length == 1 && exp < 0) {
            if (!store.hasSnap) return one("rejected: no snapshot");
            int n = 0;
            List<Ev> kept = new ArrayList<>();
            for (Ev e : store.events) {
                if (e.seq <= store.snapSeq) n++;
                else kept.add(e);
            }
            store.events = kept;
            store.baseState = store.snapState.copy();
            store.baseSeq = store.snapSeq;
            store.baseVersions = new HashMap<>(store.snapVersions);
            return one("compacted " + n + " events");
        }
        if (HAS_SNAP && v.equals("void") && w.length == 2 && numText(w[1])) {
            int n = Integer.parseInt(w[1]);
            Ev ev = null;
            for (Ev e : store.events) if (e.seq == n) ev = e;
            if (ev == null || !ev.type.equals("Rented")) return one("rejected: cannot void");
            String item = ev.f.get(ITEM);
            if (conflict.test(ITEM + ":" + item)) return one("rejected: conflict");
            Boat b = st.item.get(item);
            if (b.renter == null || b.rseq != n) return one("rejected: cannot void");
            return one("ok #" + store.append("Voided", ITEM, item, WHO, ev.f.get(WHO), "target", Integer.toString(n)));
        }
        return bad;
    }

    public static String run(String script) {
        Store store = new Store();
        List<String> out = new ArrayList<>();
        for (String cmd : script.split("\n", -1)) {
            if (cmd.isEmpty()) continue;
            out.add("> " + cmd);
            out.addAll(doCmd(store, cmd));
        }
        return String.join("\n", out);
    }
}
'''

GO = r'''
package eventstore

import (
	"sort"
	"strconv"
	"strings"
)

const (
	itemW    = @ITEM@
	whoW     = @WHO@
	limit    = @LIMIT@
	maxD     = @MAXD@
	rate     = @RATE@
	hasVer   = @VER@
	hasClock = @CLOCK@
	hasAsof  = @ASOF@
	hasSnap  = @SNAP@
)

type kv struct{ k, v string }

type ev struct {
	seq int
	typ string
	f   []kv
}

func (e ev) get(k string) string {
	for _, x := range e.f {
		if x.k == k {
			return x.v
		}
	}
	return ""
}

type member struct {
	fees int64
	rent map[string]bool
}

type boat struct {
	seats  int
	renter string
	has    bool
	due    int64
	rseq   int
}

type state struct {
	who  map[string]*member
	item map[string]*boat
}

func newState() *state { return &state{who: map[string]*member{}, item: map[string]*boat{}} }

func (s *state) copy() *state {
	c := newState()
	for k, m := range s.who {
		nm := &member{fees: m.fees, rent: map[string]bool{}}
		for r := range m.rent {
			nm.rent[r] = true
		}
		c.who[k] = nm
	}
	for k, b := range s.item {
		nb := *b
		c.item[k] = &nb
	}
	return c
}

func goodName(s string) bool {
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

func numText(s string) bool {
	if len(s) < 1 || len(s) > 6 {
		return false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	return len(s) == 1 || s[0] != '0'
}

func numIn(s string, lo, hi int) bool {
	if !numText(s) {
		return false
	}
	n, _ := strconv.Atoi(s)
	return n >= lo && n <= hi
}

func atoi(s string) int64 {
	n, _ := strconv.ParseInt(s, 10, 64)
	return n
}

func applyEvent(st *state, e ev) {
	switch e.typ {
	case "Registered":
		st.who[e.get(whoW)] = &member{rent: map[string]bool{}}
	case "Commissioned":
		st.item[e.get(itemW)] = &boat{seats: int(atoi(e.get("seats")))}
	case "Rented":
		b := st.item[e.get(itemW)]
		b.renter, b.has = e.get(whoW), true
		b.due = atoi(e.get("day")) + atoi(e.get("days"))
		b.rseq = e.seq
		st.who[e.get(whoW)].rent[e.get(itemW)] = true
	case "Returned", "Voided":
		st.item[e.get(itemW)].has = false
		delete(st.who[e.get(whoW)].rent, e.get(itemW))
	case "FeeCharged":
		st.who[e.get(whoW)].fees += atoi(e.get("amount"))
	case "Paid":
		st.who[e.get(whoW)].fees -= atoi(e.get("amount"))
	}
}

func fmtEvent(e ev) string {
	parts := []string{"#" + strconv.Itoa(e.seq), e.typ}
	for _, x := range e.f {
		parts = append(parts, x.k+"="+x.v)
	}
	return strings.Join(parts, " ")
}

func streamOf(e ev) string {
	switch e.typ {
	case "Commissioned", "Rented", "Returned", "Voided":
		return itemW + ":" + e.get(itemW)
	}
	return whoW + ":" + e.get(whoW)
}

type store struct {
	events       []ev
	seq          int
	versions     map[string]int
	baseState    *state
	baseSeq      int
	baseVersions map[string]int
	hasSnap      bool
	snapSeq      int
	snapState    *state
	snapVersions map[string]int
	clock        int
}

func newStore() *store {
	return &store{versions: map[string]int{}, baseState: newState(), baseVersions: map[string]int{}}
}

func (s *store) state(upto int) *state {
	st := s.baseState.copy()
	for _, e := range s.events {
		if upto < 0 || e.seq <= upto {
			applyEvent(st, e)
		}
	}
	return st
}

func (s *store) append(typ string, f ...string) int {
	s.seq++
	e := ev{seq: s.seq, typ: typ}
	for i := 0; i < len(f); i += 2 {
		e.f = append(e.f, kv{f[i], f[i+1]})
	}
	s.events = append(s.events, e)
	s.versions[streamOf(e)]++
	return s.seq
}

func (s *store) version(stream string, upto int) int {
	if upto < 0 {
		return s.versions[stream]
	}
	n := s.baseVersions[stream]
	for _, e := range s.events {
		if e.seq <= upto && streamOf(e) == stream {
			n++
		}
	}
	return n
}

func evLines(evs []ev) []string {
	var out []string
	for _, e := range evs {
		out = append(out, fmtEvent(e))
	}
	if len(out) == 0 {
		out = []string{"(empty)"}
	}
	return out
}

func runQuery(s *store, st *state, w []string, upto int) []string {
	v := w[0]
	if v == itemW && len(w) == 2 {
		b, ok := st.item[w[1]]
		if !ok {
			return []string{"no such " + itemW}
		}
		if !b.has {
			return []string{w[1] + " seats=" + strconv.Itoa(b.seats) + " free"}
		}
		return []string{w[1] + " seats=" + strconv.Itoa(b.seats) + " rented by " + b.renter + " until " + strconv.FormatInt(b.due, 10)}
	}
	if v == whoW && len(w) == 2 {
		m, ok := st.who[w[1]]
		if !ok {
			return []string{"no such " + whoW}
		}
		var rs []string
		for r := range m.rent {
			rs = append(rs, r)
		}
		sort.Strings(rs)
		r := strings.Join(rs, ",")
		if r == "" {
			r = "-"
		}
		out := w[1] + " rentals=" + r
		if hasClock {
			out += " fees=" + strconv.FormatInt(m.fees, 10)
		}
		return []string{out}
	}
	if v == "log" && (len(w) == 1 || len(w) == 2) {
		frm := 1
		if len(w) == 2 {
			if !numText(w[1]) {
				return nil
			}
			frm = int(atoi(w[1]))
		}
		var evs []ev
		for _, e := range s.events {
			if e.seq >= frm && (upto < 0 || e.seq <= upto) {
				evs = append(evs, e)
			}
		}
		return evLines(evs)
	}
	if hasVer && v == "version" && len(w) == 2 {
		return []string{w[1] + " version " + strconv.Itoa(s.version(w[1], upto))}
	}
	if hasAsof && v == "history" && len(w) == 2 {
		var evs []ev
		for _, e := range s.events {
			if streamOf(e) == itemW+":"+w[1] && (upto < 0 || e.seq <= upto) {
				evs = append(evs, e)
			}
		}
		return evLines(evs)
	}
	return nil
}

func doCmd(s *store, cmd string) []string {
	w := strings.Split(cmd, " ")
	exp := -1
	bad := []string{"error: command"}
	if hasVer && len(w) > 1 && strings.HasPrefix(w[len(w)-1], "@") {
		t := w[len(w)-1][1:]
		if !numText(t) {
			return bad
		}
		exp = int(atoi(t))
		w = w[:len(w)-1]
	}
	v := w[0]
	if hasAsof && v == "asof" && exp < 0 {
		if len(w) < 3 || !numText(w[1]) {
			return bad
		}
		n := int(atoi(w[1]))
		if hasSnap && n < s.baseSeq {
			return []string{"error: compacted"}
		}
		if n > s.seq {
			return []string{"error: future"}
		}
		if res := runQuery(s, s.state(n), w[2:], n); res != nil {
			return res
		}
		return bad
	}
	if exp < 0 {
		if q := runQuery(s, s.state(-1), w, -1); q != nil {
			return q
		}
	}
	st := s.state(-1)
	conflict := func(stream string) bool { return exp >= 0 && s.version(stream, -1) != exp }
	rej := func(m string) []string { return []string{"rejected: " + m} }
	switch {
	case v == "register" && len(w) == 2 && goodName(w[1]):
		if conflict(whoW + ":" + w[1]) {
			return rej("conflict")
		}
		if _, ok := st.who[w[1]]; ok {
			return rej("exists")
		}
		return []string{"ok #" + strconv.Itoa(s.append("Registered", whoW, w[1]))}
	case v == "commission" && len(w) == 3 && goodName(w[1]) && numIn(w[2], 1, 12):
		if conflict(itemW + ":" + w[1]) {
			return rej("conflict")
		}
		if _, ok := st.item[w[1]]; ok {
			return rej("exists")
		}
		return []string{"ok #" + strconv.Itoa(s.append("Commissioned", itemW, w[1], "seats", w[2]))}
	case v == "rent" && len(w) == 4 && goodName(w[1]) && goodName(w[2]) && numText(w[3]):
		who, item := w[1], w[2]
		days := int(atoi(w[3]))
		if conflict(itemW + ":" + item) {
			return rej("conflict")
		}
		if _, ok := st.who[who]; !ok {
			return rej("no " + whoW)
		}
		if _, ok := st.item[item]; !ok {
			return rej("no " + itemW)
		}
		if days < 1 || days > maxD {
			return rej("days")
		}
		if st.item[item].has {
			return rej("busy")
		}
		if len(st.who[who].rent) >= limit {
			return rej("limit")
		}
		if hasClock && st.who[who].fees > 0 {
			return rej("fees")
		}
		return []string{"ok #" + strconv.Itoa(s.append("Rented", itemW, item, whoW, who, "days", strconv.Itoa(days), "day", strconv.Itoa(s.clock)))}
	case v == "return" && len(w) == 2 && goodName(w[1]):
		item := w[1]
		if conflict(itemW + ":" + item) {
			return rej("conflict")
		}
		b, ok := st.item[item]
		if !ok {
			return rej("no " + itemW)
		}
		if !b.has {
			return rej("not rented")
		}
		who := b.renter
		out := "ok #" + strconv.Itoa(s.append("Returned", itemW, item, whoW, who, "day", strconv.Itoa(s.clock)))
		late := int64(s.clock) - b.due
		if hasClock && late > 0 {
			out += " #" + strconv.Itoa(s.append("FeeCharged", whoW, who, "amount", strconv.FormatInt(late*rate, 10)))
		}
		return []string{out}
	case hasClock && v == "pay" && len(w) == 3 && goodName(w[1]) && numText(w[2]):
		if conflict(whoW + ":" + w[1]) {
			return rej("conflict")
		}
		m, ok := st.who[w[1]]
		if !ok {
			return rej("no " + whoW)
		}
		amt := atoi(w[2])
		if amt < 1 || amt > m.fees {
			return rej("amount")
		}
		return []string{"ok #" + strconv.Itoa(s.append("Paid", whoW, w[1], "amount", w[2]))}
	case hasClock && v == "tick" && len(w) == 2 && exp < 0 && numIn(w[1], 1, 365):
		s.clock += int(atoi(w[1]))
		return []string{"day " + strconv.Itoa(s.clock)}
	case hasSnap && v == "snapshot" && len(w) == 1 && exp < 0:
		s.hasSnap = true
		s.snapSeq = s.seq
		s.snapState = st.copy()
		s.snapVersions = map[string]int{}
		for k, x := range s.versions {
			s.snapVersions[k] = x
		}
		return []string{"snapshot at #" + strconv.Itoa(s.seq)}
	case hasSnap && v == "compact" && len(w) == 1 && exp < 0:
		if !s.hasSnap {
			return rej("no snapshot")
		}
		n := 0
		var kept []ev
		for _, e := range s.events {
			if e.seq <= s.snapSeq {
				n++
			} else {
				kept = append(kept, e)
			}
		}
		s.events = kept
		s.baseState = s.snapState.copy()
		s.baseSeq = s.snapSeq
		s.baseVersions = map[string]int{}
		for k, x := range s.snapVersions {
			s.baseVersions[k] = x
		}
		return []string{"compacted " + strconv.Itoa(n) + " events"}
	case hasSnap && v == "void" && len(w) == 2 && numText(w[1]):
		n := int(atoi(w[1]))
		var found *ev
		for i := range s.events {
			if s.events[i].seq == n {
				found = &s.events[i]
			}
		}
		if found == nil || found.typ != "Rented" {
			return rej("cannot void")
		}
		item := found.get(itemW)
		if conflict(itemW + ":" + item) {
			return rej("conflict")
		}
		b := st.item[item]
		if !b.has || b.rseq != n {
			return rej("cannot void")
		}
		return []string{"ok #" + strconv.Itoa(s.append("Voided", itemW, item, whoW, found.get(whoW), "target", strconv.Itoa(n)))}
	}
	return bad
}

// Run plays a script of commands against a fresh event store and returns the transcript.
func Run(script string) string {
	s := newStore()
	var out []string
	for _, cmd := range strings.Split(script, "\n") {
		if cmd == "" {
			continue
		}
		out = append(out, "> "+cmd)
		out = append(out, doCmd(s, cmd)...)
	}
	return strings.Join(out, "\n")
}
'''



PAIRS = [("boat", "member"), ("bike", "rider"), ("tool", "borrower"), ("sled", "musher")]
PEOPLE = ["ann", "bo", "cy", "dee", "eli", "fay"]
THINGS = ["gull", "tern", "skua", "puffin", "petrel", "plover", "shag"]
THEMES = ["the boat shed", "the bike co-op", "the tool library", "the sled kennel"]


def params(rng, level, i):
    item, who = PAIRS[(i + rng.randrange(2)) % len(PAIRS)]
    return {"level": level, "item": item, "who": who, "limit": rng.choice([2, 3]), "maxd": rng.choice([7, 14, 30]), "rate": rng.choice([2, 5, 10]), "ver": level >= 2, "clock": level >= 3, "asof": level >= 4, "snap": level >= 5}


def sol(lang, p):
    src = {"python": PY, "ruby": RB, "java": JV, "go": GO}[lang]
    L = lambda s: K.lit(lang, s)  # noqa: E731
    b = (lambda v: "True" if v else "False") if lang == "python" else (lambda v: "true" if v else "false")  # noqa: E731
    return K.subst(src, ITEM=L(p["item"]), WHO=L(p["who"]), LIMIT=p["limit"], MAXD=p["maxd"], RATE=p["rate"], VER=b(p["ver"]), CLOCK=b(p["clock"]), ASOF=b(p["asof"]), SNAP=b(p["snap"])).lstrip("\n")


def rand_script(rng, p, ns, n):
    store = ns["Store"]()
    cmds = []
    item, who = p["item"], p["who"]
    people = rng.sample(PEOPLE, rng.randint(2, 4))
    things = rng.sample(THINGS, rng.randint(2, 4))

    def emit(c):
        cmds.append(c)
        ns["do"](store, c)

    def ver(stream):
        return store.version(stream) if hasattr(store, "version") else 0

    def suffix(stream):
        if p["ver"] and rng.random() < 0.28:
            v = store.version(stream)
            return " @%d" % rng.choice([v, v, v, v + 1, max(0, v - 1)])
        return ""

    for m in people[:2]:
        emit(f"register {m}" + suffix(who + ":" + m))
    for t in things[:2]:
        emit(f"commission {t} {rng.randint(1, 12)}" + suffix(item + ":" + t))
    for _ in range(n):
        r = rng.random()
        st = store.state()
        if r < 0.1:
            m = rng.choice(people + ["zed"])
            emit(f"register {m}" + suffix(who + ":" + m))
        elif r < 0.17:
            t = rng.choice(things + ["ghost"])
            emit(f"commission {t} {rng.choice([1, 4, 8, 12, 13, 0])}" + suffix(item + ":" + t))
        elif r < 0.38:
            m, t = rng.choice(people + ["zed"]), rng.choice(things + ["ghost"])
            d = rng.choice([1, 2, 3, p["maxd"], p["maxd"] + 1, 0])
            emit(f"rent {m} {t} {d}" + suffix(item + ":" + t))
        elif r < 0.55:
            rented = [k for k, b in st["item"].items() if b["renter"] is not None]
            t = rng.choice(rented) if rented and rng.random() < 0.8 else rng.choice(things + ["ghost"])
            emit(f"return {t}" + suffix(item + ":" + t))
        elif p["clock"] and r < 0.65:
            emit("tick %d" % rng.choice([1, 2, 3, 5, 10, 400, 0]))
        elif p["clock"] and r < 0.71:
            m = rng.choice(people)
            fees = st["who"].get(m, {"fees": 0})["fees"]
            emit(f"pay {m} {rng.choice([1, max(1, fees), fees + 1, 2, 0])}" + suffix(who + ":" + m))
        elif r < 0.78:
            emit(rng.choice([f"{item} {rng.choice(things + ['ghost'])}", f"{who} {rng.choice(people + ['zed'])}", "log", "log", f"log {rng.randint(0, store.seq + 1)}"]))
        elif p["ver"] and r < 0.82:
            emit("version " + rng.choice([item + ":" + rng.choice(things), who + ":" + rng.choice(people), item + ":nope", "zzz"]))
        elif p["asof"] and r < 0.9:
            q = rng.choice([f"{item} {rng.choice(things)}", f"{who} {rng.choice(people)}", "log", f"history {rng.choice(things)}", f"version {item}:{rng.choice(things)}", "tick 1", "register x"])
            emit(f"asof {rng.randint(0, store.seq + 1)} {q}")
        elif p["snap"] and r < 0.94:
            emit(rng.choice(["snapshot", "compact", "snapshot", "compact"]))
        elif p["snap"] and r < 0.98:
            rented = [e[0] for e in store.events if e[1] == "Rented"]
            emit(f"void {rng.choice(rented) if rented and rng.random() < 0.85 else rng.randint(0, store.seq + 1)}" + (" @%d" % rng.randint(0, 3) if p["ver"] and rng.random() < 0.15 else ""))
        else:
            emit(rng.choice(["", "bogus", "register", "rent", "rent a b", "return", "tick", "log x", "REGISTER ann", "register ann extra", "commission x", "commission x y", " register ann", "register  ann"]).strip("\n") or "log")
    return "\n".join(c for c in cmds) + ("\n" if rng.random() < 0.3 else "")


def make_cases(rng, p, ns):
    cases = []
    L = p["level"]
    item, who = p["item"], p["who"]

    def add(s):
        cases.append((s,))

    for _ in range(14 if L >= 3 else 18):
        add(rand_script(rng, p, ns, rng.randint(10, 32)))
    base = f"register ann\nregister bo\ncommission a1 4\ncommission a2 2\ncommission a3 6\n"
    # basic scenarios
    scen = ["", "\n", "log", f"{item} a1", f"{who} ann", "register ann\nregister ann\nlog", "register Ann", "register 1ann", "register a-b", "register abcdefghijk", "register abcdefghij", "register", "register a b", "commission x 0", "commission x 13", "commission x 12", "commission x 01", "commission x 1", "commission x -1", "commission x", "commission x 1 2",
            "commission x 1\ncommission x 2", base + "rent ann a1 3\nrent bo a1 3\nrent ann a1 3", base + "rent ann a1 3\nrent ann a2 3\nrent ann a3 3\nrent bo a3 3", base + "rent zed a1 3", base + "rent ann zz 3", base + "rent ann a1 0", base + "rent ann a1 1\nrent ann a2 " + str(p["maxd"]) + "\nrent bo a3 " + str(p["maxd"] + 1),
            base + "rent ann a1 007", base + "rent ann a1 x", base + "rent ann a1", base + "rent ann a1 3 4", base + f"rent ann a1 3\nreturn a1\nreturn a1\nreturn zz\n{who} ann\n{item} a1\nlog", base + "return a1", base + "rent ann a1 3\nlog 3\nlog 5\nlog 6\nlog 0\nlog 99\nlog x\nlog 1 2\nlog 01", base + "rent ann a1 3\n" + f"{who} ann\n{who} bo\n{who} zed\n{item} a1\n{item} a2\n{item} zz",
            base + f"RENT ann a1 3\nrent ann  a1 3\n rent ann a1 3\nlog\n{item}\n{who}\n{item} a1 a2", "register ann\n\n\nlog\n\n"]
    for s in scen:
        add(s)
    if p["ver"]:
        v = [base + "commission a1 4 @0", base + "commission a1 4 @1", base + "commission a4 4 @0", base + "commission a4 4 @1", base + "register ann @1", base + "register cy @0", base + "register cy @1", base + "rent ann a1 3 @1\nrent bo a1 3 @2", base + "rent ann a1 3 @0", base + "rent ann a1 3 @2", base + "rent ann zz 3 @0", base + "rent zed a1 3 @9",
             base + "rent ann a1 3 @1\nreturn a1 @1\nreturn a1 @2\nreturn a1 @3", base + "return a1 @1", base + "return zz @0", base + "version boat:a1\nversion " + item + ":a1\nversion " + who + ":ann\nversion " + who + ":zz\nversion\nversion a b\nversion x:y", base + "rent ann a1 3\nversion " + item + ":a1\nreturn a1\nversion " + item + ":a1", base + "log @1", base + f"{item} a1 @1", "log @",
             base + "register cy @", base + "register cy @x", base + "register cy @01", base + "register cy @-1", base + "register cy @1x", base + "register cy @ 1", base + "register cy @0 @0", base + "register cy@0", base + "register @0", base + "rent @0", base + "@0", base + "version " + item + ":a1 @1", "register ann @0\nregister ann @0\nregister ann @1\nlog", base + "rent ann a1 3 @1\nrent ann a2 3 @1\nrent ann a3 3 @1\nlog"]
        for s in v:
            add(s)
    if p["clock"]:
        c = [base + "tick 1\ntick 2\nlog", base + "tick 0", base + "tick 366", base + "tick 365\ntick 365\ntick 1", base + "tick -1", base + "tick x", base + "tick", base + "tick 1 2", base + "tick 01", base + "tick 1 @0", base + f"rent ann a1 3\ntick 3\nreturn a1\n{who} ann\nlog", base + f"rent ann a1 3\ntick 4\nreturn a1\n{who} ann\nrent ann a2 1\npay ann 1\n{who} ann\npay ann {p['rate']}\npay ann 99\nrent ann a2 1\nlog",
             base + f"rent ann a1 3\ntick 10\nreturn a1\n{who} ann\npay ann {7 * p['rate']}\n{who} ann\npay ann 1\npay ann 0\nrent ann a2 1", base + f"rent ann a1 3\ntick 3\nreturn a1\n{who} ann\nrent ann a1 1\ntick 1\n{item} a1\nreturn a1\n{who} ann", base + "pay ann 1", base + "pay zed 1", base + "pay ann", base + "pay ann x", base + "pay ann 1 2",
             base + f"rent ann a1 1\ntick 1\nreturn a1\n{who} ann\nrent ann a2 5\ntick 5\n{item} a2\ntick 1\n{item} a2\nreturn a2\n{who} ann\n{who} bo\nlog", base + f"rent ann a1 5\ntick 5\n{item} a1\nreturn a1\n{who} ann\nlog", base + f"tick 7\nrent ann a1 2\ntick 3\n{item} a1\nreturn a1\n{who} ann"]
        for s in c:
            add(s)
    if p["asof"]:
        a = [base + "rent ann a1 3\nasof 0 log", base + "asof 0 " + item + " a1", base + "asof 1 log", base + "asof 5 log", base + "asof 5 " + item + " a1", base + "asof 6 log", base + "asof 7 log", base + "asof 99 log", base + f"rent ann a1 3\nreturn a1\nasof 5 {item} a1\nasof 6 {item} a1\nasof 7 {item} a1\nasof 6 {who} ann\nasof 7 {who} ann\nasof 7 history a1\nasof 6 history a1\nasof 3 history a1\nasof 0 history a1\nhistory a1\nhistory zz\nhistory\nhistory a1 a2",
             base + "asof", base + "asof 1", base + "asof x log", base + "asof 01 log", base + "asof -1 log", base + "asof 1 bogus", base + "asof 1 asof 1 log", base + "asof 1 register zed\nlog", base + "asof 1 rent ann a1 3\nlog", base + "asof 1 tick 1", base + f"rent ann a1 3\nasof 5 version {item}:a1\nasof 6 version {item}:a1\nasof 5 version {who}:ann\nasof 7 version {who}:ann\nversion {item}:a1",
             base + "asof 5 log 4\nasof 5 log 6", base + "asof 3 " + item + " a1 @1", base + "asof 3 log @1", base + "asof 2 " + who + " bo", base + "asof 1 " + who + " bo", base + "asof 0 " + who + " ann"]
        for s in a:
            add(s)
    if p["snap"]:
        sn = [base + "snapshot\nlog\ncompact\nlog\nasof 5 log\nasof 4 log\nasof 6 log\nasof 99 log", base + "compact", base + "snapshot\ncompact\ncompact", base + "snapshot\nrent ann a1 3\nsnapshot\nrent bo a2 3\ncompact\nlog\nasof 5 log\nasof 6 log\nasof 7 log\nversion " + item + ":a1\nversion " + who + ":ann\nasof 6 version " + item + ":a1\nasof 7 version " + item + ":a1\nhistory a1\nasof 7 history a1",
              base + f"rent ann a1 3\nvoid 6\nlog\n{item} a1\n{who} ann\nrent bo a1 2\nvoid 6\nvoid 8\n{item} a1\nlog", base + "void 6", base + "void 1", base + "void 0", base + "void 99", base + "void", base + "void x", base + "void 6 7", base + "void 01", base + "rent ann a1 3\nreturn a1\nvoid 6", base + "rent ann a1 3\nvoid 6\nvoid 6", base + "rent ann a1 3\nvoid 6 @1\nvoid 6 @2\nvoid 6 @3",
              base + "rent ann a1 3\nsnapshot\ncompact\nvoid 6\nlog", base + "rent ann a1 3\nsnapshot\nvoid 6\ncompact\nlog\nasof 6 log\nasof 7 log\nasof 8 log", base + "snapshot\nsnapshot extra", base + "snapshot @0", base + "compact @0", base + "snapshot\nsnapshot\ncompact\nregister cy\nlog\nversion " + who + ":cy\nasof 5 log", base + f"rent ann a1 2\ntick 5\nreturn a1\nsnapshot\ncompact\n{who} ann\nlog\nasof 7 {who} ann\nasof 8 {who} ann\nasof 8 log",
              base + "rent ann a1 3\nsnapshot\nreturn a1\nrent bo a1 3\nvoid 6\nvoid 8\nlog\nhistory a1\ncompact\nlog\nhistory a1\nasof 7 history a1", base + f"rent ann a1 3\nrent bo a2 3\nvoid 6\nvoid 7\nrent ann a1 3\nlog\n{item} a1\n{item} a2"]
        for s in sn:
            add(s)
    # examples
    ex = []
    ex.append(("register ann\ncommission " + THINGS[0] + " 4\nrent ann " + THINGS[0] + " 3\nrent ann " + THINGS[0] + " 2\n" + item + " " + THINGS[0] + "\n" + who + " ann\nreturn " + THINGS[0] + "\nlog",))
    if p["ver"]:
        ex.append(("register ann\ncommission " + THINGS[1] + " 2 @0\ncommission " + THINGS[2] + " 2 @1\nversion " + item + ":" + THINGS[1] + "\nrent ann " + THINGS[1] + " 1 @1\nrent ann " + THINGS[1] + " 1 @1",))
    if p["clock"]:
        ex.append((f"register ann\ncommission {THINGS[0]} 4\nrent ann {THINGS[0]} 3\ntick 5\nreturn {THINGS[0]}\n{who} ann\nrent ann {THINGS[0]} 1\npay ann {p['rate']}\n{who} ann",))
    if p["asof"]:
        ex.append((f"register ann\ncommission {THINGS[0]} 4\nrent ann {THINGS[0]} 3\nreturn {THINGS[0]}\nasof 3 {item} {THINGS[0]}\nasof 4 {item} {THINGS[0]}\nhistory {THINGS[0]}",))
    if p["snap"]:
        ex.append((f"register ann\ncommission {THINGS[0]} 4\nrent ann {THINGS[0]} 3\nsnapshot\nvoid 3\nreturn {THINGS[0]}\ncompact\nlog\nasof 2 log\nasof 4 {item} {THINGS[0]}",))
    nex = len(ex)
    out, seen = [], set()
    for c in ex + cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex


def readme(p, api, lang, examples):
    item, who = p["item"], p["who"]
    X = [f"# Event-sourced rental ledger: {THEMES[PAIRS.index((item, who))]}", ""]
    X.append(f"`run(script)` plays a script of commands against a fresh in-memory **event store** for {THEMES[PAIRS.index((item, who))]} and returns the transcript. The store never changes an event after writing it; everything the commands show is *folded* from the events.")
    X.append("")
    X.append("## Events and streams")
    X.append("")
    X.append(f"Every accepted command appends one or more events to a single global log. Events are numbered `#1, #2, ...` in the order written (the **sequence number**). Each event also belongs to one **stream**: `{item}:NAME` or `{who}:NAME`, and the **version** of a stream is the number of events ever written to it.")
    X.append("")
    X.append("| event | stream | fields (in this order) |")
    X.append("|---|---|---|")
    X.append(f"| `Registered` | `{who}:NAME` | `{who}` |")
    X.append(f"| `Commissioned` | `{item}:NAME` | `{item}`, `seats` |")
    X.append(f"| `Rented` | `{item}:NAME` | `{item}`, `{who}`, `days`, `day` |")
    X.append(f"| `Returned` | `{item}:NAME` | `{item}`, `{who}`, `day` |")
    if p["clock"]:
        X.append(f"| `FeeCharged` | `{who}:NAME` | `{who}`, `amount` |")
        X.append(f"| `Paid` | `{who}:NAME` | `{who}`, `amount` |")
    if p["snap"]:
        X.append(f"| `Voided` | `{item}:NAME` | `{item}`, `{who}`, `target` |")
    X.append("")
    X.append("In the `log` output an event is written `#SEQ TYPE field=value field=value ...` with the fields in the order of the table, single spaces between them.")
    X.append("")
    X.append("**State** (what the queries show) is folded from the events: " + f"a `{item}` is *free* or *rented by* a `{who}` *until* a day (`day + days` of its `Rented` event)" + (", a " + f"`{who}` has fees (the sum of `FeeCharged` amounts minus `Paid` amounts)" if p["clock"] else "") + f"; a `{who}` holds the set of `{item}`s currently rented to them. `Returned`" + (" and `Voided`" if p["snap"] else "") + f" make the `{item}` free again.")
    X.append("")
    X.append("## The script")
    X.append("")
    X.append("`script` is text made of lines separated by `\\n`; empty lines are skipped. A command is words separated by single spaces, case-sensitive. A `NAME` is 1 to 10 characters: a lower-case ASCII letter, then lower-case letters, digits or `_`; a number is written in decimal without leading zeros (and at most 6 digits). The transcript has the line `> ` plus the command exactly as written, then its response lines; lines are joined with `\\n`, no trailing newline.")
    X.append("")
    X.append(f"A line that is not a valid command (unknown word, wrong number of words, a bad `NAME` or number, a number outside the range given below) answers the single line `error: command` and has no effect. A valid command that the rules refuse answers `rejected: WHY` and writes no event. Accepted commands answer `ok #S` with the sequence number of the event they wrote (`ok #S1 #S2` when they wrote two).")
    X.append("")
    cmds = [(f"register NAME", f"adds a `{who}`: event `Registered`. Refused: `exists`."), (f"commission NAME SEATS", f"adds a `{item}` with 1 to 12 seats (`SEATS` out of range is `error: command`): event `Commissioned`. Refused: `exists`."),
            (f"rent {who.upper()} {item.upper()} DAYS", f"(here `{who.upper()}` and `{item.upper()}` stand for names) `{who}` rents `{item}` for DAYS days. Refused, checked in this order: `no {who}`, `no {item}`, `days` (DAYS must be 1 to {p['maxd']}), `busy` (the `{item}` is rented), `limit` (the `{who}` already rents {p['limit']} `{item}`s)" + (", `fees` (the `" + who + "` owes fees)" if p["clock"] else "") + ". Event `Rented` with `day` = the current day" + (" (see `tick`; the day is 0 until then)" if p["clock"] else " (always 0)") + "."),
            (f"return {item.upper()}", f"the renter returns the `{item}`. Refused: `no {item}`, `not rented`. Event `Returned`" + (f"; if the current day is later than the rental's *until* day, a `FeeCharged` event follows with `amount` = days late times {p['rate']}. The answer lists both: `ok #5 #6`." if p["clock"] else "."))]
    if p["clock"]:
        cmds += [("pay NAME AMOUNT", f"the `{who}` pays AMOUNT of their fees (a number from 1 up to what they owe, otherwise `rejected: amount`; unknown `{who}`: `rejected: no {who}`): event `Paid`."), ("tick DAYS", "moves the current day forward by DAYS (1 to 365) and answers `day N` with the new current day. It writes no event.")]
    if p["snap"]:
        cmds += [("snapshot", "remembers the current state, the sequence number and the stream versions (replacing an older snapshot); answers `snapshot at #N` with the last sequence number (`#0` if nothing was written). No event."),
                 ("compact", "forgets all events up to and including the snapshot's sequence number and keeps the snapshot as the starting point from which the remaining events are folded; answers `compacted K events` (`K` events forgotten, possibly 0). `rejected: no snapshot` if there never was a snapshot. Stream versions are not reduced."),
                 ("void N", f"cancels the rental written by event `#N`: refused with `cannot void` unless `#N` is a `Rented` event that is still in the log and that rental is the `{item}`'s current rental (not returned or voided). Event `Voided` (in the `{item}` stream, with the `target` sequence number); the `{item}` becomes free and no fee is charged.")]
    X.append("| command | effect |")
    X.append("|---|---|")
    for c, e in cmds:
        X.append(f"| `{c}` | {e} |")
    X.append("")
    if p["ver"]:
        X.append("**Expected version.** A command that writes events may end with one extra word `@N` (`N` a number, zero allowed): the command is then only carried out if the *stream* it writes to has version exactly `N`; otherwise it answers `rejected: conflict` and writes nothing. The stream is `" + f"{who}:NAME` for `register`" + (" and `pay`" if p["clock"] else "") + f", and `{item}:NAME` for `commission`, `rent`, `return`" + (" and `void` (the `" + item + "` of the voided rental)" if p["snap"] else "") + ". The version check comes **before** every other refusal (an unknown name has version 0). `@N` is not allowed on any other command (that is `error: command`).")
        X.append("")
    X.append("## Queries")
    X.append("")
    q = [(f"{item} NAME", f"`NAME seats=S free` or `NAME seats=S rented by WHO until D`; `no such {item}` if there is none."),
         (f"{who} NAME", f"`NAME rentals=a,b" + (" fees=F" if p["clock"] else "") + f"` (the rented `{item}`s in ascending byte order, `-` for none" + (", `F` the fees" if p["clock"] else "") + f"); `no such {who}`."),
         ("log", "all events, one per line; `(empty)` if the log holds none."), ("log N", "the events with sequence number N or higher (N a number, zero allowed; `(empty)` if none).")]
    if p["ver"]:
        q.append(("version STREAM", "`STREAM version V`: the version of any stream name (`V` is 0 for a stream that does not exist; the text is not checked)."))
    if p["asof"]:
        q.append((f"history NAME", f"the events of stream `{item}:NAME`, like `log` (`(empty)` if none)."))
        q.append(("asof N QUERY", f"answers `QUERY` (any of the queries above, including its arguments) as the store was after the first N events: state, `log`, `history` and `version` all only count events up to #N. `N` is a number (zero allowed). Answers `error: future` if N is above the last sequence number" + (", and `error: compacted` if N is lower than the sequence number the log was compacted up to (checked first)" if p["snap"] else "") + ". `QUERY` that is not a query is `error: command`."))
    X.append("| query | answer |")
    X.append("|---|---|")
    for c, e in q:
        X.append(f"| `{c}` | {e} |")
    X.append("")
    X.append("Queries answer a single line unless stated otherwise and never write events.")
    X.append("")
    X.append(K.interface_section(api, lang))
    X.append("## Examples")
    X.append("")
    for k, ((s,), out) in enumerate(examples):
        X.append(f"**Example {k + 1}**")
        X.append("")
        X.append("```")
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
    feats = ["an append-only event log with folded state"] + (["optimistic concurrency checks"] if p["ver"] else []) + (["a day clock with late fees"] if p["clock"] else []) + (["time-travel queries"] if p["asof"] else []) + (["snapshots, compaction and voiding"] if p["snap"] else [])
    fl = ", ".join(feats[:-1]) + (" and " if len(feats) > 1 else "") + feats[-1]
    opts = [
        f"Build the event-sourced ledger from README.md in {ln}: `{fn}(script)` in {where} plays commands against an in-memory event store and returns the transcript ({fl}). {K.closer(rng)}",
        f"Implement `{fn}` ({ln}, {where}) as specified in README.md: a small event store with commands, queries and exact output lines. This version has {fl}. {K.closer(rng)}",
        f"{ln} task: an event-sourcing exercise with an invented lending domain. `{fn}` in {where}; README.md defines the events, streams, commands, rejections and the transcript format. Features: {fl}.",
        f"Please write the rental-ledger engine from README.md ({ln}; `{fn}`; {where}). It supports {fl}; rejection order is specified.",
    ]
    return rng.choice(opts).strip()


LANG_PLAN = ["ruby", "go", "java", "ruby", "java", "go", "java", "go"]
LEVELS = [1, 2, 2, 3, 3, 4, 5, 5]


@family("greenfield-eventstore", category="greenfield", lang="mixed", kind="greenfield", n=8,
        summary="event-sourced lending ledger: append-only log, folded state, expected-version conflicts, day clock with late fees, as-of queries, snapshots with compaction and compensating events")
def gen(rng, n):
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = LEVELS[i % len(LEVELS)]
        p = params(rng, level, i)
        api = K.Api(mod="eventstore", fn="run", args=["script"], arg_docs=["the command script, one command per line"], ret_doc="the transcript", doc="event-sourced rental ledger")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["run"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=level, slug=f"{i + 1:02d}-{lang}-{p['item']}-l{level}", oracle=(None if lang == "python" else ns["run"]),
            tags=["event-sourcing", "state", "parser"], notes={"level": level, "item": p["item"], "limit": p["limit"]},
        )
