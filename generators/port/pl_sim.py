"""Port libraries that replay a command script against a small state machine and return the output lines."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

# ======================================================================================================================
# dock-queue: berth queue with aging
# ======================================================================================================================

DQ_SPEC = dd('''
    A harbour's berth queue. `replay(commands)` runs a list of command lines against an initially empty queue and returns
    one output line per command. A command is words separated by **single spaces** (a leading or trailing space, a double space
    or an empty line makes the command malformed). A **malformed command makes the whole replay an error**: unknown verb, wrong
    number of words, a bad identifier, a number that is not made of ASCII digits only (no sign, no underscores, no other
    Unicode digits) or is outside its range.

    Identifiers match `[A-Za-z0-9_-]+`. The clock `now` starts at 0. A waiting ship has an id, a priority (0..9), a size
    (1..99999) and the time it arrived. Its **effective priority** is `priority + (now - arrived) / 5` (integer division).

    * `arrive ID PRIO SIZE`: if `ID` is already waiting the output is `dup ID` and nothing changes; otherwise the ship joins and the
      output is `queued ID`.
    * `tick N` (N in 0..1000): `now` grows by `N`; output `time <now>`.
    * `serve`: removes the waiting ship with the highest effective priority (ties: the one that **arrived first**, counting
      arrivals in command order) and outputs `served <id> size=<size> eff=<effective priority>`; with nobody waiting the output is `empty`.
    * `peek`: like `serve` but nothing is removed: `next <id> eff=<effective priority>` or `empty`.
    * `cancel ID`: `cancelled ID` if it was waiting (it leaves), otherwise `unknown ID`.
    * `len`: `waiting <number of ships>`.
''')

DQ_FNS = [Fn("replay", [("commands", "list<str>")], "list<str>", err=True)]

DQ_PY = dd(r'''
import re

_ID = re.compile(r"[A-Za-z0-9_-]+")
_NUM = re.compile(r"[0-9]+")


def _num(s, lo, hi):
    if not _NUM.fullmatch(s):
        raise ValueError("bad number")
    v = int(s)
    if v < lo or v > hi:
        raise ValueError("number out of range")
    return v


def _ident(s):
    if not _ID.fullmatch(s):
        raise ValueError("bad identifier")
    return s


def replay(commands):
    now, seq = 0, 0
    waiting = []
    out = []

    def eff(e):
        return e["prio"] + (now - e["at"]) // 5

    def best():
        return min(waiting, key=lambda e: (-eff(e), e["seq"])) if waiting else None

    for line in commands:
        w = line.split(" ")
        verb = w[0]
        if verb == "arrive" and len(w) == 4:
            name = _ident(w[1])
            prio, size = _num(w[2], 0, 9), _num(w[3], 1, 99999)
            if any(e["id"] == name for e in waiting):
                out.append("dup " + name)
            else:
                waiting.append({"id": name, "prio": prio, "size": size, "at": now, "seq": seq})
                seq += 1
                out.append("queued " + name)
        elif verb == "tick" and len(w) == 2:
            now += _num(w[1], 0, 1000)
            out.append("time %d" % now)
        elif verb == "serve" and len(w) == 1:
            b = best()
            if b is None:
                out.append("empty")
            else:
                waiting.remove(b)
                out.append("served %s size=%d eff=%d" % (b["id"], b["size"], eff(b)))
        elif verb == "peek" and len(w) == 1:
            b = best()
            out.append("empty" if b is None else "next %s eff=%d" % (b["id"], eff(b)))
        elif verb == "cancel" and len(w) == 2:
            name = _ident(w[1])
            hit = [e for e in waiting if e["id"] == name]
            if hit:
                waiting.remove(hit[0])
                out.append("cancelled " + name)
            else:
                out.append("unknown " + name)
        elif verb == "len" and len(w) == 1:
            out.append("waiting %d" % len(waiting))
        else:
            raise ValueError("malformed command")
    return out
''')

DQ_JAVA = dd(r'''
import java.util.*;

public final class DockQueue {
    private DockQueue() {}

    private static final class Ship {
        String id;
        long prio, size, at, seq;
    }

    private static boolean idOk(String s) {
        if (s.isEmpty()) return false;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            boolean ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-';
            if (!ok) return false;
        }
        return true;
    }

    private static String ident(String s) {
        if (!idOk(s)) throw new IllegalArgumentException("bad identifier");
        return s;
    }

    private static long num(String s, long lo, long hi) {
        if (s.isEmpty() || s.length() > 12) throw new IllegalArgumentException("bad number");
        for (int i = 0; i < s.length(); i++) {
            if (s.charAt(i) < '0' || s.charAt(i) > '9') throw new IllegalArgumentException("bad number");
        }
        long v = Long.parseLong(s);
        if (v < lo || v > hi) throw new IllegalArgumentException("number out of range");
        return v;
    }

    public static List<String> replay(List<String> commands) {
        long now = 0, seq = 0;
        List<Ship> waiting = new ArrayList<>();
        List<String> out = new ArrayList<>();
        for (String line : commands) {
            String[] w = line.split(" ", -1);
            String verb = w[0];
            final long clock = now;
            Comparator<Ship> order = (a, b) -> {
                long ea = a.prio + (clock - a.at) / 5, eb = b.prio + (clock - b.at) / 5;
                if (ea != eb) return Long.compare(eb, ea);
                return Long.compare(a.seq, b.seq);
            };
            if (verb.equals("arrive") && w.length == 4) {
                String id = ident(w[1]);
                long prio = num(w[2], 0, 9), size = num(w[3], 1, 99999);
                boolean dup = false;
                for (Ship s : waiting) if (s.id.equals(id)) dup = true;
                if (dup) {
                    out.add("dup " + id);
                } else {
                    Ship s = new Ship();
                    s.id = id; s.prio = prio; s.size = size; s.at = now; s.seq = seq++;
                    waiting.add(s);
                    out.add("queued " + id);
                }
            } else if (verb.equals("tick") && w.length == 2) {
                now += num(w[1], 0, 1000);
                out.add("time " + now);
            } else if (verb.equals("serve") && w.length == 1) {
                if (waiting.isEmpty()) {
                    out.add("empty");
                } else {
                    Ship b = Collections.min(waiting, order);
                    waiting.remove(b);
                    out.add("served " + b.id + " size=" + b.size + " eff=" + (b.prio + (now - b.at) / 5));
                }
            } else if (verb.equals("peek") && w.length == 1) {
                if (waiting.isEmpty()) {
                    out.add("empty");
                } else {
                    Ship b = Collections.min(waiting, order);
                    out.add("next " + b.id + " eff=" + (b.prio + (now - b.at) / 5));
                }
            } else if (verb.equals("cancel") && w.length == 2) {
                String id = ident(w[1]);
                Ship hit = null;
                for (Ship s : waiting) if (s.id.equals(id)) hit = s;
                if (hit != null) {
                    waiting.remove(hit);
                    out.add("cancelled " + id);
                } else {
                    out.add("unknown " + id);
                }
            } else if (verb.equals("len") && w.length == 1) {
                out.add("waiting " + waiting.size());
            } else {
                throw new IllegalArgumentException("malformed command");
            }
        }
        return out;
    }
}
''')

DQ_GO = dd(r'''
package dockqueue

import (
	"errors"
	"fmt"
	"strconv"
	"strings"
)

var errBad = errors.New("dockqueue: malformed command")

type ship struct {
	id         string
	prio, size int64
	at, seq    int64
}

func validID(s string) bool {
	if s == "" {
		return false
	}
	for i := 0; i < len(s); i++ {
		c := s[i]
		if !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-') {
			return false
		}
	}
	return true
}

func num(s string, lo, hi int64) (int64, error) {
	if s == "" || len(s) > 12 {
		return 0, errBad
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return 0, errBad
		}
	}
	v, err := strconv.ParseInt(s, 10, 64)
	if err != nil || v < lo || v > hi {
		return 0, errBad
	}
	return v, nil
}

func Replay(commands []string) ([]string, error) {
	var now, seq int64
	var waiting []*ship
	out := []string{}
	eff := func(s *ship) int64 { return s.prio + (now-s.at)/5 }
	best := func() int {
		bi := -1
		for i, s := range waiting {
			if bi < 0 || eff(s) > eff(waiting[bi]) || (eff(s) == eff(waiting[bi]) && s.seq < waiting[bi].seq) {
				bi = i
			}
		}
		return bi
	}
	find := func(id string) int {
		for i, s := range waiting {
			if s.id == id {
				return i
			}
		}
		return -1
	}
	for _, line := range commands {
		w := strings.Split(line, " ")
		switch {
		case w[0] == "arrive" && len(w) == 4:
			if !validID(w[1]) {
				return nil, errBad
			}
			prio, err := num(w[2], 0, 9)
			if err != nil {
				return nil, err
			}
			size, err := num(w[3], 1, 99999)
			if err != nil {
				return nil, err
			}
			if find(w[1]) >= 0 {
				out = append(out, "dup "+w[1])
			} else {
				waiting = append(waiting, &ship{w[1], prio, size, now, seq})
				seq++
				out = append(out, "queued "+w[1])
			}
		case w[0] == "tick" && len(w) == 2:
			n, err := num(w[1], 0, 1000)
			if err != nil {
				return nil, err
			}
			now += n
			out = append(out, fmt.Sprintf("time %d", now))
		case w[0] == "serve" && len(w) == 1:
			if bi := best(); bi < 0 {
				out = append(out, "empty")
			} else {
				s := waiting[bi]
				out = append(out, fmt.Sprintf("served %s size=%d eff=%d", s.id, s.size, eff(s)))
				waiting = append(waiting[:bi], waiting[bi+1:]...)
			}
		case w[0] == "peek" && len(w) == 1:
			if bi := best(); bi < 0 {
				out = append(out, "empty")
			} else {
				out = append(out, fmt.Sprintf("next %s eff=%d", waiting[bi].id, eff(waiting[bi])))
			}
		case w[0] == "cancel" && len(w) == 2:
			if !validID(w[1]) {
				return nil, errBad
			}
			if i := find(w[1]); i >= 0 {
				waiting = append(waiting[:i], waiting[i+1:]...)
				out = append(out, "cancelled "+w[1])
			} else {
				out = append(out, "unknown "+w[1])
			}
		case w[0] == "len" && len(w) == 1:
			out = append(out, fmt.Sprintf("waiting %d", len(waiting)))
		default:
			return nil, errBad
		}
	}
	return out, nil
}
''')


def dq_cases(rng):
    scripts = [
        ["arrive A 3 100", "arrive B 5 200", "peek", "serve", "serve", "serve"],
        ["arrive A 0 10", "tick 5", "arrive B 0 10", "peek", "tick 4", "peek", "serve", "serve"],
        ["arrive A 1 10", "arrive A 9 99", "len", "cancel A", "cancel A", "len"],
        ["tick 0", "tick 1000", "tick 1000", "len"],
        ["arrive A 2 1", "arrive B 2 1", "arrive C 2 1", "serve", "arrive D 2 1", "serve", "serve", "serve", "serve"],
        ["arrive S1 9 5", "tick 50", "arrive S2 9 5", "serve", "serve"],
        ["arrive A 0 1", "tick 4", "peek", "tick 1", "peek", "arrive B 1 1", "peek", "tick 5", "serve", "peek"],
        [], ["len"], ["serve"], ["peek"], ["cancel Z"],
        ["arrive a-b_9 0 99999", "serve"], ["arrive A 9 1", "arrive B 8 1", "tick 5", "serve", "serve"], ["arrive A 5 1", "tick 25", "arrive B 9 1", "serve"],
    ]
    out = [("replay", [s]) for s in scripts]
    bad = [["fly A"], ["arrive A 3"], ["arrive A 3 4 5"], ["arrive A 10 5"], ["arrive A 3 0"], ["arrive A 3 100000"], ["arrive A -1 5"], ["arrive A +3 5"], ["arrive A 3 1_0"], ["arrive A 3 ٣"], ["arrive Aé 3 5"], ["arrive  A 3 5"], [" serve"], ["serve "],
           ["serve now"], ["tick"], ["tick -1"], ["tick 1001"], ["tick 1.5"], ["tick x"], ["cancel"], ["cancel A B"], ["cancel a b"], ["cancel é"], ["len 1"], ["peek 1"], [""], ["Serve"], ["arrive A 3 5", "oops"], ["arrive A 3 5", "serve", "tick 0 0"],
           ["arrive A 03 005", "serve"], ["tick 0001"], ["arrive A 3 5\n"], ["arrive A 3 5\t"], ["arrive A 3 99999999999999999999"], ["tick 99999999999999"]]
    out += [("replay", [s]) for s in bad]
    names = ["A", "B", "C", "ship-1", "ship_2", "X9", "q"]
    for _ in range(25):
        cmds = []
        for _ in range(rng.randint(1, 18)):
            r = rng.random()
            if r < 0.35:
                cmds.append("arrive %s %d %d" % (rng.choice(names), rng.randint(0, 9), rng.randint(1, 500)))
            elif r < 0.55:
                cmds.append("tick %d" % rng.choice([0, 1, 2, 3, 4, 5, 6, 9, 10, 17, 30, 100]))
            elif r < 0.75:
                cmds.append("serve")
            elif r < 0.82:
                cmds.append("peek")
            elif r < 0.9:
                cmds.append("cancel " + rng.choice(names))
            else:
                cmds.append("len")
        out.append(("replay", [cmds]))
    return out


DQ = PortLib(
    slug="dock-queue",
    title="berth queue with priority aging",
    blurb="A small harbour's berth scheduler serves ships by priority, but a ship that has waited long enough eventually outranks newer, more urgent ones.",
    spec=DQ_SPEC,
    fns=DQ_FNS,
    impls={"python": {"dock_queue.py": DQ_PY}, "java": {"DockQueue.java": DQ_JAVA}, "go": {"dockqueue.go": DQ_GO}},
    cases=dq_cases,
    difficulty=3,
    traps=["strict ASCII digit parsing (Python int accepts underscores and Unicode digits)", "stable tie-breaking", "state replay", "error idioms"],
    tags=["state-machine", "replay", "strict-parsing"],
    pairs=[("python", "java", "full"), ("python", "go", "full"), ("go", "java", "stub"), ("java", "python", "stub")],
)
register_port(DQ, __name__)

# ======================================================================================================================
# vend-fsm: vending machine
# ======================================================================================================================

VF_SPEC = dd('''
    A vending machine. `replay(config, events)` builds a machine from `config` and processes `events`, returning one output
    line per event. Entries and events are words separated by single spaces; **malformed input makes the whole call an error**
    (this includes numbers that are not plain ASCII digits).

    **Config.** Each entry is `CODE:PRICE:STOCK`: `CODE` is an upper-case letter followed by one digit (`A1`), `PRICE` is a number of
    cents that is a positive multiple of 5 and at most 9995, `STOCK` is 0..99. Duplicate codes are an error. The machine starts with
    credit 0.

    **Events.** Accepted coins are 5, 10, 25, 50, 100 and 200 cents.

    * `coin V`: an accepted coin adds to the credit, output `credit <credit>`; any other positive number is `reject <V>` (credit unchanged).
    * `select CODE`: unknown code: `unknown <CODE>`; stock 0: `soldout <CODE>`; credit below the price: `need <missing cents>`;
      otherwise the item is dispensed, stock drops by one, credit becomes 0 and the output is `vend <CODE> change=<coins>`.
    * `refund`: output `refund <credit> coins=<coins>` and credit becomes 0.
    * `restock CODE N` (N in 1..99): unknown code `unknown <CODE>`; if the stock would exceed 99 the output is `full <CODE>` and nothing changes;
      otherwise `stock <CODE> <new stock>`.
    * `status`: `credit <credit> slots=<CODE:stock,...>` with the slots sorted by code (plain character order), or `slots=-` when there are none.

    `<coins>` is the **greedy** change in the largest coins first, written like `100+25+5`, or `-` when the amount is 0. Greedy
    uses 200, 100, 50, 25, 10, 5.
''')

VF_FNS = [Fn("replay", [("config", "list<str>"), ("events", "list<str>")], "list<str>", err=True)]

VF_PY = dd(r'''
import re

_CODE = re.compile(r"[A-Z][0-9]")
_NUM = re.compile(r"[0-9]+")
COINS = (200, 100, 50, 25, 10, 5)


def _num(s, lo, hi):
    if not _NUM.fullmatch(s) or len(s) > 9:
        raise ValueError("bad number")
    v = int(s)
    if v < lo or v > hi:
        raise ValueError("number out of range")
    return v


def _change(c):
    parts = []
    for coin in COINS:
        while c >= coin:
            parts.append(str(coin))
            c -= coin
    return "+".join(parts) if parts else "-"


def replay(config, events):
    slots = {}
    for entry in config:
        f = entry.split(":")
        if len(f) != 3 or not _CODE.fullmatch(f[0]) or f[0] in slots:
            raise ValueError("bad config entry")
        price = _num(f[1], 5, 9995)
        if price % 5:
            raise ValueError("price must be a multiple of 5")
        slots[f[0]] = [price, _num(f[2], 0, 99)]
    credit = 0
    out = []
    for line in events:
        w = line.split(" ")
        verb = w[0]
        if verb == "coin" and len(w) == 2:
            v = _num(w[1], 1, 999999)
            if v in COINS:
                credit += v
                out.append("credit %d" % credit)
            else:
                out.append("reject %d" % v)
        elif verb == "select" and len(w) == 2:
            code = w[1]
            if not _CODE.fullmatch(code):
                raise ValueError("bad code")
            if code not in slots:
                out.append("unknown " + code)
            elif slots[code][1] == 0:
                out.append("soldout " + code)
            elif credit < slots[code][0]:
                out.append("need %d" % (slots[code][0] - credit))
            else:
                slots[code][1] -= 1
                out.append("vend %s change=%s" % (code, _change(credit - slots[code][0])))
                credit = 0
        elif verb == "refund" and len(w) == 1:
            out.append("refund %d coins=%s" % (credit, _change(credit)))
            credit = 0
        elif verb == "restock" and len(w) == 3:
            code = w[1]
            if not _CODE.fullmatch(code):
                raise ValueError("bad code")
            n = _num(w[2], 1, 99)
            if code not in slots:
                out.append("unknown " + code)
            elif slots[code][1] + n > 99:
                out.append("full " + code)
            else:
                slots[code][1] += n
                out.append("stock %s %d" % (code, slots[code][1]))
        elif verb == "status" and len(w) == 1:
            listing = ",".join("%s:%d" % (c, slots[c][1]) for c in sorted(slots)) or "-"
            out.append("credit %d slots=%s" % (credit, listing))
        else:
            raise ValueError("malformed event")
    return out
''')

VF_GO = dd(r'''
package vendfsm

import (
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
)

var errBad = errors.New("vendfsm: malformed input")

var coins = []int64{200, 100, 50, 25, 10, 5}

func validCode(s string) bool {
	return len(s) == 2 && s[0] >= 'A' && s[0] <= 'Z' && s[1] >= '0' && s[1] <= '9'
}

func num(s string, lo, hi int64) (int64, error) {
	if s == "" || len(s) > 9 {
		return 0, errBad
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return 0, errBad
		}
	}
	v, _ := strconv.ParseInt(s, 10, 64)
	if v < lo || v > hi {
		return 0, errBad
	}
	return v, nil
}

func change(c int64) string {
	var parts []string
	for _, coin := range coins {
		for c >= coin {
			parts = append(parts, strconv.FormatInt(coin, 10))
			c -= coin
		}
	}
	if len(parts) == 0 {
		return "-"
	}
	return strings.Join(parts, "+")
}

type slot struct{ price, stock int64 }

func Replay(config []string, events []string) ([]string, error) {
	slots := map[string]*slot{}
	for _, entry := range config {
		f := strings.Split(entry, ":")
		if len(f) != 3 || !validCode(f[0]) {
			return nil, errBad
		}
		if _, dup := slots[f[0]]; dup {
			return nil, errBad
		}
		price, err := num(f[1], 5, 9995)
		if err != nil || price%5 != 0 {
			return nil, errBad
		}
		stock, err := num(f[2], 0, 99)
		if err != nil {
			return nil, err
		}
		slots[f[0]] = &slot{price, stock}
	}
	var credit int64
	out := []string{}
	for _, line := range events {
		w := strings.Split(line, " ")
		switch {
		case w[0] == "coin" && len(w) == 2:
			v, err := num(w[1], 1, 999999)
			if err != nil {
				return nil, err
			}
			accepted := false
			for _, c := range coins {
				if c == v {
					accepted = true
				}
			}
			if accepted {
				credit += v
				out = append(out, fmt.Sprintf("credit %d", credit))
			} else {
				out = append(out, fmt.Sprintf("reject %d", v))
			}
		case w[0] == "select" && len(w) == 2:
			if !validCode(w[1]) {
				return nil, errBad
			}
			s, ok := slots[w[1]]
			switch {
			case !ok:
				out = append(out, "unknown "+w[1])
			case s.stock == 0:
				out = append(out, "soldout "+w[1])
			case credit < s.price:
				out = append(out, fmt.Sprintf("need %d", s.price-credit))
			default:
				s.stock--
				out = append(out, fmt.Sprintf("vend %s change=%s", w[1], change(credit-s.price)))
				credit = 0
			}
		case w[0] == "refund" && len(w) == 1:
			out = append(out, fmt.Sprintf("refund %d coins=%s", credit, change(credit)))
			credit = 0
		case w[0] == "restock" && len(w) == 3:
			if !validCode(w[1]) {
				return nil, errBad
			}
			n, err := num(w[2], 1, 99)
			if err != nil {
				return nil, err
			}
			s, ok := slots[w[1]]
			switch {
			case !ok:
				out = append(out, "unknown "+w[1])
			case s.stock+n > 99:
				out = append(out, "full "+w[1])
			default:
				s.stock += n
				out = append(out, fmt.Sprintf("stock %s %d", w[1], s.stock))
			}
		case w[0] == "status" && len(w) == 1:
			var codes []string
			for c := range slots {
				codes = append(codes, c)
			}
			sort.Strings(codes)
			parts := make([]string, len(codes))
			for i, c := range codes {
				parts[i] = fmt.Sprintf("%s:%d", c, slots[c].stock)
			}
			listing := strings.Join(parts, ",")
			if listing == "" {
				listing = "-"
			}
			out = append(out, fmt.Sprintf("credit %d slots=%s", credit, listing))
		default:
			return nil, errBad
		}
	}
	return out, nil
}
''')

VF_RS = dd(r'''
use std::collections::BTreeMap;

const COINS: [i64; 6] = [200, 100, 50, 25, 10, 5];

fn valid_code(s: &str) -> bool {
    let b = s.as_bytes();
    b.len() == 2 && b[0].is_ascii_uppercase() && b[1].is_ascii_digit()
}

fn num(s: &str, lo: i64, hi: i64) -> Result<i64, String> {
    if s.is_empty() || s.len() > 9 || !s.bytes().all(|c| c.is_ascii_digit()) {
        return Err("bad number".to_string());
    }
    let v: i64 = s.parse().unwrap();
    if v < lo || v > hi {
        return Err("number out of range".to_string());
    }
    Ok(v)
}

fn change(mut c: i64) -> String {
    let mut parts: Vec<String> = Vec::new();
    for coin in COINS {
        while c >= coin {
            parts.push(coin.to_string());
            c -= coin;
        }
    }
    if parts.is_empty() { "-".to_string() } else { parts.join("+") }
}

pub fn replay(config: &[String], events: &[String]) -> Result<Vec<String>, String> {
    let mut slots: BTreeMap<String, (i64, i64)> = BTreeMap::new();
    for entry in config {
        let f: Vec<&str> = entry.split(':').collect();
        if f.len() != 3 || !valid_code(f[0]) || slots.contains_key(f[0]) {
            return Err("bad config entry".to_string());
        }
        let price = num(f[1], 5, 9995)?;
        if price % 5 != 0 {
            return Err("price must be a multiple of 5".to_string());
        }
        slots.insert(f[0].to_string(), (price, num(f[2], 0, 99)?));
    }
    let mut credit = 0i64;
    let mut out = Vec::new();
    for line in events {
        let w: Vec<&str> = line.split(' ').collect();
        match (w[0], w.len()) {
            ("coin", 2) => {
                let v = num(w[1], 1, 999999)?;
                if COINS.contains(&v) {
                    credit += v;
                    out.push(format!("credit {}", credit));
                } else {
                    out.push(format!("reject {}", v));
                }
            }
            ("select", 2) => {
                if !valid_code(w[1]) {
                    return Err("bad code".to_string());
                }
                match slots.get_mut(w[1]) {
                    None => out.push(format!("unknown {}", w[1])),
                    Some(s) if s.1 == 0 => out.push(format!("soldout {}", w[1])),
                    Some(s) if credit < s.0 => out.push(format!("need {}", s.0 - credit)),
                    Some(s) => {
                        s.1 -= 1;
                        out.push(format!("vend {} change={}", w[1], change(credit - s.0)));
                        credit = 0;
                    }
                }
            }
            ("refund", 1) => {
                out.push(format!("refund {} coins={}", credit, change(credit)));
                credit = 0;
            }
            ("restock", 3) => {
                if !valid_code(w[1]) {
                    return Err("bad code".to_string());
                }
                let n = num(w[2], 1, 99)?;
                match slots.get_mut(w[1]) {
                    None => out.push(format!("unknown {}", w[1])),
                    Some(s) if s.1 + n > 99 => out.push(format!("full {}", w[1])),
                    Some(s) => {
                        s.1 += n;
                        out.push(format!("stock {} {}", w[1], s.1));
                    }
                }
            }
            ("status", 1) => {
                let listing: Vec<String> = slots.iter().map(|(c, s)| format!("{}:{}", c, s.1)).collect();
                let listing = if listing.is_empty() { "-".to_string() } else { listing.join(",") };
                out.push(format!("credit {} slots={}", credit, listing));
            }
            _ => return Err("malformed event".to_string()),
        }
    }
    Ok(out)
}
''')


def vf_cases(rng):
    cfgs = [
        ["A1:150:3", "B2:75:0", "C3:35:5"], [], ["A1:5:1"], ["Z9:9995:99"], ["B1:100:2", "A2:100:2", "A1:100:2"],
    ]
    evs = [
        ["coin 100", "coin 50", "select A1", "status"], ["coin 25", "select A1", "coin 200", "select A1", "status"], ["select B2", "select Q1", "select C3", "coin 100", "select C3"],
        ["coin 3", "coin 0", "coin 1000", "coin 5", "refund", "refund"], ["coin 200", "coin 200", "coin 200", "select C3", "status"], ["restock A1 97", "restock A1 96", "restock A1 1", "restock B2 5", "restock Z1 1", "status"],
        ["coin 200", "coin 25", "select A1", "coin 200", "select A1", "coin 200", "select A1", "coin 200", "select A1"], [], ["status"], ["refund"], ["coin 10", "coin 10", "coin 5", "refund", "status"],
        ["coin 200", "coin 100", "coin 50", "coin 25", "coin 10", "coin 5", "refund"], ["coin 200", "select C3", "select C3", "status"],
    ]
    out = []
    for c in cfgs:
        for e in evs:
            if rng.random() < 0.6:
                out.append(("replay", [c, e]))
    out.append(("replay", [cfgs[0], evs[0]]))
    out.append(("replay", [cfgs[0], evs[5]]))
    bad_cfg = [["A1"], ["A1:100"], ["A1:100:1:1"], ["a1:100:1"], ["A:100:1"], ["A11:100:1"], ["A1:0:1"], ["A1:7:1"], ["A1:10000:1"], ["A1:100:100"], ["A1:100:-1"], ["A1:+100:1"], ["A1:1_00:1"], ["A1:1٠٠:1"], ["A1:100:1", "A1:50:1"], ["A1: 100:1"], ["A1:100:1 "], ["A1:0100:1"]]
    for c in bad_cfg:
        out.append(("replay", [c, ["status"]]))
    bad_ev = [["coin"], ["coin 5 5"], ["coin -5"], ["coin +5"], ["coin 5.0"], ["coin 1_0"], ["coin ٥"], ["coin 0005"], ["coin 1000000"], ["coin 99999999999"], ["select"], ["select a1"], ["select A"], ["select A1 A1"], ["refund 5"], ["restock A1"], ["restock A1 0"], ["restock A1 100"], ["restock a1 5"],
              ["status now"], ["Status"], [""], [" status"], ["status "], ["coin  5"], ["dispense A1"], ["coin 5", "bogus"], ["select é1"]]
    for e in bad_ev:
        out.append(("replay", [cfgs[0], e]))
    for _ in range(25):
        c = rng.choice(cfgs)
        e = []
        for _ in range(rng.randint(1, 16)):
            r = rng.random()
            if r < 0.4:
                e.append("coin %d" % rng.choice([5, 10, 25, 50, 100, 200, 200, 1, 2, 75]))
            elif r < 0.65:
                e.append("select %s" % rng.choice(["A1", "B2", "C3", "A2", "B1", "Z9", "Q1"]))
            elif r < 0.75:
                e.append("refund")
            elif r < 0.85:
                e.append("restock %s %d" % (rng.choice(["A1", "B2", "C3", "Z9"]), rng.choice([1, 5, 50, 97, 99])))
            else:
                e.append("status")
        out.append(("replay", [c, e]))
    return out


VF = PortLib(
    slug="vend-fsm",
    title="vending machine controller",
    blurb="The controller of a campus vending machine is driven by a stream of coin, selection and service events and prints a one-line response for each.",
    spec=VF_SPEC,
    fns=VF_FNS,
    impls={"go": {"vendfsm.go": VF_GO}, "python": {"vend_fsm.py": VF_PY}, "rust": {"src/lib.rs": VF_RS}},
    cases=vf_cases,
    difficulty=3,
    traps=["greedy change formatting", "strict ASCII digit parsing", "sorted listing", "error idioms"],
    tags=["state-machine", "replay"],
    pairs=[("go", "python", "full"), ("python", "rust", "full"), ("rust", "go", "stub"), ("go", "rust", "stub")],
)
register_port(VF, __name__)

# ======================================================================================================================
# score-board: league standings replay
# ======================================================================================================================

SB_SPEC = dd('''
    A league table. `replay(commands)` runs commands against an empty league and returns the output lines (some commands print
    several lines). Words are separated by single spaces; a **malformed command makes the whole replay an error**: unknown verb, wrong
    word count, a team name that is not `[A-Za-z0-9_]+`, a goal count that is not made of ASCII digits only or is above 99,
    or a match of a team against itself.

    * `match HOME AWAY HG AG`: records a result (teams appear in the league the first time they are named). A win is 3 points,
      a draw 1 point, a loss 0. Goals for/against accumulate. Output `recorded <HOME> <HG>-<AG> <AWAY>`.
    * `rename OLD NEW`: if `OLD` is not in the league the output is `unknown <OLD>`; if `NEW` is already in the league `taken <NEW>`;
      otherwise the team keeps its record under the new name and the output is `renamed <OLD> <NEW>`.
    * `standings`: prints one line per team, best first: ordered by points, then goal difference (goals for minus goals against), then
      goals for (all descending), then name in plain character order. The line is `<rank> <name> pts=<points> gd=<gd> gf=<goals for>`, where
      `rank` is `1 +` the number of teams that are strictly better on the triple (points, goal difference, goals for) - so teams equal on all
      three share a rank - and `gd` is written with an explicit sign for positive values (`+3`, `0`, `-2`). With no teams the output is the single line `no teams`.
''')

SB_FNS = [Fn("replay", [("commands", "list<str>")], "list<str>", err=True)]

SB_PY = dd(r'''
import re

_NAME = re.compile(r"[A-Za-z0-9_]+")
_NUM = re.compile(r"[0-9]+")


def _name(s):
    if not _NAME.fullmatch(s):
        raise ValueError("bad team name")
    return s


def _goals(s):
    if not _NUM.fullmatch(s) or len(s) > 6 or int(s) > 99:
        raise ValueError("bad goal count")
    return int(s)


def _gd(v):
    return "+%d" % v if v > 0 else "%d" % v


def replay(commands):
    teams = {}
    out = []
    for line in commands:
        w = line.split(" ")
        if w[0] == "match" and len(w) == 5:
            home, away = _name(w[1]), _name(w[2])
            hg, ag = _goals(w[3]), _goals(w[4])
            if home == away:
                raise ValueError("a team cannot play itself")
            for t in (home, away):
                teams.setdefault(t, [0, 0, 0])
            teams[home][1] += hg
            teams[home][2] += ag
            teams[away][1] += ag
            teams[away][2] += hg
            if hg > ag:
                teams[home][0] += 3
            elif hg < ag:
                teams[away][0] += 3
            else:
                teams[home][0] += 1
                teams[away][0] += 1
            out.append("recorded %s %d-%d %s" % (home, hg, ag, away))
        elif w[0] == "rename" and len(w) == 3:
            old, new = _name(w[1]), _name(w[2])
            if old not in teams:
                out.append("unknown " + old)
            elif new in teams:
                out.append("taken " + new)
            else:
                teams[new] = teams.pop(old)
                out.append("renamed %s %s" % (old, new))
        elif w[0] == "standings" and len(w) == 1:
            if not teams:
                out.append("no teams")
                continue
            key = {t: (v[0], v[1] - v[2], v[1]) for t, v in teams.items()}
            for t in sorted(teams, key=lambda t: (-key[t][0], -key[t][1], -key[t][2], t)):
                rank = 1 + sum(1 for u in teams if key[u] > key[t])
                out.append("%d %s pts=%d gd=%s gf=%d" % (rank, t, key[t][0], _gd(key[t][1]), key[t][2]))
        else:
            raise ValueError("malformed command")
    return out
''')

SB_JAVA = dd(r'''
import java.util.*;

public final class ScoreBoard {
    private ScoreBoard() {}

    private static boolean nameOk(String s) {
        if (s.isEmpty()) return false;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_')) return false;
        }
        return true;
    }

    private static String name(String s) {
        if (!nameOk(s)) throw new IllegalArgumentException("bad team name");
        return s;
    }

    private static int goals(String s) {
        if (s.isEmpty() || s.length() > 6) throw new IllegalArgumentException("bad goal count");
        for (int i = 0; i < s.length(); i++) {
            if (s.charAt(i) < '0' || s.charAt(i) > '9') throw new IllegalArgumentException("bad goal count");
        }
        int v = Integer.parseInt(s);
        if (v > 99) throw new IllegalArgumentException("bad goal count");
        return v;
    }

    private static int cmpPoints(String a, String b) {
        int[] x = a.codePoints().toArray(), y = b.codePoints().toArray();
        for (int i = 0; i < Math.min(x.length, y.length); i++) if (x[i] != y[i]) return x[i] < y[i] ? -1 : 1;
        return Integer.compare(x.length, y.length);
    }

    public static List<String> replay(List<String> commands) {
        Map<String, int[]> teams = new HashMap<>();
        List<String> out = new ArrayList<>();
        for (String line : commands) {
            String[] w = line.split(" ", -1);
            if (w[0].equals("match") && w.length == 5) {
                String home = name(w[1]), away = name(w[2]);
                int hg = goals(w[3]), ag = goals(w[4]);
                if (home.equals(away)) throw new IllegalArgumentException("a team cannot play itself");
                teams.putIfAbsent(home, new int[3]);
                teams.putIfAbsent(away, new int[3]);
                int[] h = teams.get(home), a = teams.get(away);
                h[1] += hg; h[2] += ag; a[1] += ag; a[2] += hg;
                if (hg > ag) h[0] += 3; else if (hg < ag) a[0] += 3; else { h[0] += 1; a[0] += 1; }
                out.add("recorded " + home + " " + hg + "-" + ag + " " + away);
            } else if (w[0].equals("rename") && w.length == 3) {
                String oldName = name(w[1]), newName = name(w[2]);
                if (!teams.containsKey(oldName)) out.add("unknown " + oldName);
                else if (teams.containsKey(newName)) out.add("taken " + newName);
                else {
                    teams.put(newName, teams.remove(oldName));
                    out.add("renamed " + oldName + " " + newName);
                }
            } else if (w[0].equals("standings") && w.length == 1) {
                if (teams.isEmpty()) {
                    out.add("no teams");
                    continue;
                }
                final Map<String, int[]> t = teams;
                List<String> names = new ArrayList<>(teams.keySet());
                names.sort((p, q) -> {
                    int[] a = t.get(p), b = t.get(q);
                    if (a[0] != b[0]) return Integer.compare(b[0], a[0]);
                    int gda = a[1] - a[2], gdb = b[1] - b[2];
                    if (gda != gdb) return Integer.compare(gdb, gda);
                    if (a[1] != b[1]) return Integer.compare(b[1], a[1]);
                    return cmpPoints(p, q);
                });
                for (String n : names) {
                    int[] a = teams.get(n);
                    int gd = a[1] - a[2];
                    int rank = 1;
                    for (int[] b : teams.values()) {
                        int gdb = b[1] - b[2];
                        if (b[0] > a[0] || (b[0] == a[0] && (gdb > gd || (gdb == gd && b[1] > a[1])))) rank++;
                    }
                    out.add(rank + " " + n + " pts=" + a[0] + " gd=" + (gd > 0 ? "+" + gd : "" + gd) + " gf=" + a[1]);
                }
            } else {
                throw new IllegalArgumentException("malformed command");
            }
        }
        return out;
    }
}
''')

SB_JS = dd(r'''
'use strict';

const NAME = /^[A-Za-z0-9_]+$/;
const NUM = /^[0-9]+$/;

function name(s) {
  if (!NAME.test(s)) throw new Error('bad team name');
  return s;
}

function goals(s) {
  if (!NUM.test(s) || s.length > 6 || Number(s) > 99) throw new Error('bad goal count');
  return Number(s);
}

function replay(commands) {
  const teams = new Map();
  const out = [];
  for (const line of commands) {
    const w = line.split(' ');
    if (w[0] === 'match' && w.length === 5) {
      const home = name(w[1]);
      const away = name(w[2]);
      const hg = goals(w[3]);
      const ag = goals(w[4]);
      if (home === away) throw new Error('a team cannot play itself');
      for (const t of [home, away]) if (!teams.has(t)) teams.set(t, [0, 0, 0]);
      const h = teams.get(home);
      const a = teams.get(away);
      h[1] += hg;
      h[2] += ag;
      a[1] += ag;
      a[2] += hg;
      if (hg > ag) h[0] += 3;
      else if (hg < ag) a[0] += 3;
      else {
        h[0] += 1;
        a[0] += 1;
      }
      out.push(`recorded ${home} ${hg}-${ag} ${away}`);
    } else if (w[0] === 'rename' && w.length === 3) {
      const oldName = name(w[1]);
      const newName = name(w[2]);
      if (!teams.has(oldName)) out.push('unknown ' + oldName);
      else if (teams.has(newName)) out.push('taken ' + newName);
      else {
        teams.set(newName, teams.get(oldName));
        teams.delete(oldName);
        out.push(`renamed ${oldName} ${newName}`);
      }
    } else if (w[0] === 'standings' && w.length === 1) {
      if (teams.size === 0) {
        out.push('no teams');
        continue;
      }
      const key = new Map();
      for (const [t, v] of teams) key.set(t, [v[0], v[1] - v[2], v[1]]);
      const cmpPoints = (p, q) => {
        const x = Array.from(p);
        const y = Array.from(q);
        for (let i = 0; i < Math.min(x.length, y.length); i++) {
          const c = x[i].codePointAt(0) - y[i].codePointAt(0);
          if (c) return c;
        }
        return x.length - y.length;
      };
      const names = [...teams.keys()].sort((p, q) => {
        const a = key.get(p);
        const b = key.get(q);
        return b[0] - a[0] || b[1] - a[1] || b[2] - a[2] || cmpPoints(p, q);
      });
      for (const n of names) {
        const k = key.get(n);
        let rank = 1;
        for (const o of key.values()) {
          if (o[0] > k[0] || (o[0] === k[0] && (o[1] > k[1] || (o[1] === k[1] && o[2] > k[2])))) rank++;
        }
        out.push(`${rank} ${n} pts=${k[0]} gd=${k[1] > 0 ? '+' + k[1] : String(k[1])} gf=${k[2]}`);
      }
    } else {
      throw new Error('malformed command');
    }
  }
  return out;
}

module.exports = { replay };
''')


def sb_cases(rng):
    teams = ["Ajax", "bees", "Cats", "dogs", "E_1", "owls", "Wolves", "x"]
    scripts = [
        ["standings"], ["match Ajax bees 2 1", "standings"], ["match Ajax bees 1 1", "standings"], ["match Ajax bees 0 3", "match bees Cats 2 2", "match Cats Ajax 1 0", "standings"],
        ["match A B 1 0", "match C D 1 0", "standings"], ["match A B 1 0", "match C D 1 0", "match B C 0 0", "match D A 0 0", "standings"], ["match A B 2 0", "rename A Z", "standings", "rename A Y", "rename B Z", "rename B Q", "standings"],
        ["match a B 1 0", "match B c 1 0", "match c a 1 0", "standings"], ["match A B 5 5", "match A B 5 5", "standings"], ["match Zed Alf 0 1", "match Alf Zed 0 1", "standings", "rename Zed zed", "standings"],
        ["match A B 99 0", "match B A 99 0", "match A B 0 0", "standings"], ["rename Q R", "standings"], ["match A B 3 0", "match A C 3 0", "match B C 0 0", "standings"],
    ]
    out = [("replay", [s]) for s in scripts]
    bad = [["fly"], ["match A B 1"], ["match A B 1 2 3"], ["match A A 1 1"], ["match A B 100 0"], ["match A B -1 0"], ["match A B +1 0"], ["match A B 1_0 0"], ["match A B ١ 0"], ["match A B 1.0 0"], ["match A-1 B 1 0"], ["match Aé B 1 0"], ["match  A B 1 0"], ["match A B 1 0 "],
           ["rename A"], ["rename A B C"], ["rename A B-"], ["rename a a"], ["standings now"], ["Standings"], [""], ["match A B 001 0"], ["match A B 1234567 0"], ["match A B 1 0", "oops"]]
    out += [("replay", [s]) for s in bad]
    for _ in range(25):
        cmds = []
        for _ in range(rng.randint(1, 14)):
            r = rng.random()
            if r < 0.6:
                a, b = rng.sample(teams, 2)
                cmds.append("match %s %s %d %d" % (a, b, rng.randint(0, 4), rng.randint(0, 4)))
            elif r < 0.75:
                cmds.append("rename %s %s" % (rng.choice(teams), rng.choice(teams + ["new1", "new2"])))
            else:
                cmds.append("standings")
        out.append(("replay", [cmds]))
    return out


SB = PortLib(
    slug="score-board",
    title="league standings from a match log",
    blurb="A hobby league's website rebuilds the standings table by replaying a log of recorded results and administrative renames.",
    spec=SB_SPEC,
    fns=SB_FNS,
    impls={"java": {"ScoreBoard.java": SB_JAVA}, "python": {"score_board.py": SB_PY}, "javascript": {"src/score_board.js": SB_JS}},
    cases=sb_cases,
    difficulty=3,
    traps=["multi-key ordering with code point tie-break", "signed formatting", "shared ranks", "strict parsing"],
    tags=["state-machine", "replay", "sorting"],
    pairs=[("java", "python", "full"), ("python", "javascript", "full"), ("javascript", "java", "stub"), ("java", "javascript", "stub")],
)
register_port(SB, __name__)
