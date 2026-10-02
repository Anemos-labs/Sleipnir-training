"""A tiny stack machine with an assembler: renamed mnemonics, 32-bit arithmetic variants, limits and exact error texts."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

OPS = ["push", "pop", "dup", "swap", "over", "add", "sub", "mul", "div", "mod", "neg", "eq", "lt", "gt", "not", "jmp", "jz", "jnz",
       "call", "ret", "load", "store", "in", "out", "outc", "outs", "halt"]
CORE = ["push", "pop", "dup", "swap", "add", "sub", "mul", "out", "jmp", "jz", "halt", "lt"]
L4 = ["over", "div", "mod", "neg", "eq", "gt", "not", "jnz", "call", "ret", "load", "store", "in", "outc"]
L5 = ["outs"]
ALIASES = {
    "push": ["lit", "pushi", "ldc", "put"], "pop": ["drop", "discard", "nip1"], "dup": ["twin", "copy", "dupe"], "swap": ["flip", "exch", "xchg"],
    "over": ["peek2", "pick", "tuck2"], "add": ["plus", "iadd", "sum"], "sub": ["minus", "isub", "diff"], "mul": ["times", "imul", "prod"],
    "div": ["quot", "idiv", "divide"], "mod": ["rem", "imod", "modulo"], "neg": ["negate", "ineg", "flipsign"], "eq": ["same", "ceq", "equal"],
    "lt": ["less", "clt", "below"], "gt": ["more", "cgt", "above"], "not": ["inv", "lnot", "isz"], "jmp": ["goto", "br", "jump"],
    "jz": ["brz", "ifz", "jzero"], "jnz": ["brnz", "ifnz", "jnonzero"], "call": ["gosub", "invoke", "enter"], "ret": ["back", "leave", "rts"],
    "load": ["fetch", "ldm", "peekm"], "store": ["poke", "stm", "put2"], "in": ["read", "recv", "get"], "out": ["print", "emit", "show"],
    "outc": ["printc", "emitc", "putc"], "outs": ["prints", "emits", "puts"], "halt": ["stop", "end", "quit"],
}
LANG_PLAN = ["go", "rust", "java", "c", "python", "go", "rust", "java", "c", "go", "rust", "java"]


def params(rng, level):
    avail = list(CORE)
    if level >= 4:
        avail += L4
    if level >= 5:
        avail += L5
    names = {}
    used = set()
    for op in OPS:
        if op not in avail:
            continue
        if rng.random() < (0.35 if level <= 3 else 0.55):
            nm = rng.choice(ALIASES[op])
            if nm in used or nm in OPS:
                nm = op
        else:
            nm = op
        if nm in used:
            nm = op
        used.add(nm)
        names[op] = nm
    # a few ops must not collide with another canonical name of the same instance
    return {
        "level": level, "avail": avail, "names": names,
        "wrap": rng.random() < 0.5, "floor": rng.random() < 0.5,
        "stack": rng.choice([8, 12, 16, 32]), "mem": rng.choice([16, 32, 64]), "calls": rng.choice([4, 6, 8, 16]),
        "steps": rng.choice([300, 500, 1000, 2000]), "data": level >= 5,
    }


PY = r'''
OPS = ["push", "pop", "dup", "swap", "over", "add", "sub", "mul", "div", "mod", "neg", "eq", "lt", "gt", "not", "jmp", "jz", "jnz",
       "call", "ret", "load", "store", "in", "out", "outc", "outs", "halt"]
NAMES = @NAMES_PY@
WRAP = @WRAP@
FLOOR = @FLOOR@
STACK = @STACK@
MEM = @MEM@
CALLS = @CALLS@
STEPS = @STEPS@
HAS_DATA = @DATA@
LET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
DIG = "0123456789"
LO, HI = -2 ** 31, 2 ** 31 - 1


def ident(s):
    return s != "" and s[0] in LET and all(c in LET + DIG for c in s)


def to_int(t):
    body = t[1:] if t[:1] == "-" else t
    if body == "" or len(body) > 10 or any(c not in DIG for c in body):
        return None
    v = int(t)
    return v if LO <= v <= HI else None


def assemble(program):
    prog, labels, data, errs = [], {}, [], []
    refs = []
    for no, raw in enumerate(program.split("\n"), 1):
        toks = raw.split(";", 1)[0].split()
        if not toks:
            continue
        label = None
        if toks[0].endswith(":"):
            label = toks[0][:-1]
            toks = toks[1:]
            if not ident(label):
                errs.append((no, "bad label"))
                continue
        if toks and toks[0] == ".word" and HAS_DATA:
            nums = [to_int(t) for t in toks[1:]]
            if label is not None or prog or not nums or None in nums or len(data) + len(nums) > MEM:
                errs.append((no, "bad data"))
            else:
                data.extend(nums)
            continue
        if label is not None:
            if label in labels:
                errs.append((no, "duplicate label"))
                continue
            labels[label] = len(prog)
        if not toks:
            continue
        name = toks[0]
        if name not in NAMES:
            errs.append((no, "unknown instruction"))
            continue
        op = OPS[NAMES.index(name)]
        args = toks[1:]
        if op == "push":
            v = to_int(args[0]) if len(args) == 1 else None
            if v is None:
                errs.append((no, "bad operand"))
                continue
            prog.append((op, v, no))
        elif op in ("jmp", "jz", "jnz", "call"):
            if len(args) != 1 or not ident(args[0]):
                errs.append((no, "bad operand"))
                continue
            refs.append((no, args[0]))
            prog.append((op, args[0], no))
        else:
            if args:
                errs.append((no, "bad operand"))
                continue
            prog.append((op, 0, no))
    for no, lab in refs:
        if lab not in labels:
            errs.append((no, "unknown label"))
    return prog, labels, data, (min(errs) if errs else None)


def norm(x):
    if LO <= x <= HI:
        return x
    return None if not WRAP else (x + 2 ** 31) % 2 ** 32 - 2 ** 31


def tdiv(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def run(program, inp):
    prog, labels, data, err = assemble(program)
    if err:
        return "error: line %d: %s" % err
    mem = [0] * MEM
    for i, v in enumerate(data):
        mem[i] = v
    toks = inp.split()
    ti = 0
    stack, rs, out = [], [], []
    pc = 0
    steps = 0

    def fail(code):
        o = "".join(out)
        if o and not o.endswith("\n"):
            o += "\n"
        return o + "error: %s at %d" % (code, pc)

    while pc < len(prog):
        if steps >= STEPS:
            return fail("steps")
        steps += 1
        op, arg, _ = prog[pc]
        npc = pc + 1

        def need(n):
            return len(stack) >= n

        def push(v):
            if len(stack) >= STACK:
                return False
            stack.append(v)
            return True

        if op == "push":
            if not push(arg):
                return fail("stack-overflow")
        elif op == "pop":
            if not need(1):
                return fail("stack-underflow")
            stack.pop()
        elif op == "dup":
            if not need(1):
                return fail("stack-underflow")
            if not push(stack[-1]):
                return fail("stack-overflow")
        elif op == "swap":
            if not need(2):
                return fail("stack-underflow")
            stack[-1], stack[-2] = stack[-2], stack[-1]
        elif op == "over":
            if not need(2):
                return fail("stack-underflow")
            if not push(stack[-2]):
                return fail("stack-overflow")
        elif op in ("add", "sub", "mul", "div", "mod", "eq", "lt", "gt"):
            if not need(2):
                return fail("stack-underflow")
            b = stack.pop()
            a = stack.pop()
            if op == "add":
                r = norm(a + b)
            elif op == "sub":
                r = norm(a - b)
            elif op == "mul":
                r = norm(a * b)
            elif op in ("div", "mod"):
                if b == 0:
                    return fail("div0")
                if op == "div":
                    r = norm(a // b if FLOOR else tdiv(a, b))
                else:
                    r = a % b if FLOOR else a - b * tdiv(a, b)
            elif op == "eq":
                r = 1 if a == b else 0
            elif op == "lt":
                r = 1 if a < b else 0
            else:
                r = 1 if a > b else 0
            if r is None:
                return fail("overflow")
            stack.append(r)
        elif op == "neg":
            if not need(1):
                return fail("stack-underflow")
            r = norm(-stack.pop())
            if r is None:
                return fail("overflow")
            stack.append(r)
        elif op == "not":
            if not need(1):
                return fail("stack-underflow")
            stack.append(1 if stack.pop() == 0 else 0)
        elif op == "jmp":
            npc = labels[arg]
        elif op in ("jz", "jnz"):
            if not need(1):
                return fail("stack-underflow")
            v = stack.pop()
            if (v == 0) == (op == "jz"):
                npc = labels[arg]
        elif op == "call":
            if len(rs) >= CALLS:
                return fail("call-depth")
            rs.append(pc + 1)
            npc = labels[arg]
        elif op == "ret":
            if not rs:
                return fail("ret-empty")
            npc = rs.pop()
        elif op == "load":
            if not need(1):
                return fail("stack-underflow")
            a = stack.pop()
            if a < 0 or a >= MEM:
                return fail("bad-address")
            stack.append(mem[a])
        elif op == "store":
            if not need(2):
                return fail("stack-underflow")
            a = stack.pop()
            v = stack.pop()
            if a < 0 or a >= MEM:
                return fail("bad-address")
            mem[a] = v
        elif op == "in":
            if ti >= len(toks) or to_int(toks[ti]) is None:
                return fail("input")
            v = to_int(toks[ti])
            ti += 1
            if not push(v):
                return fail("stack-overflow")
        elif op == "out":
            if not need(1):
                return fail("stack-underflow")
            out.append("%d\n" % stack.pop())
        elif op == "outc":
            if not need(1):
                return fail("stack-underflow")
            v = stack.pop()
            if v < 1 or v > 127:
                return fail("char")
            out.append(chr(v))
        elif op == "outs":
            if not need(1):
                return fail("stack-underflow")
            a = stack.pop()
            if a < 0 or a >= MEM:
                return fail("bad-address")
            while mem[a] != 0:
                if mem[a] < 0 or mem[a] > 127:
                    return fail("char")
                out.append(chr(mem[a]))
                a += 1
                if a >= MEM:
                    return fail("bad-address")
        elif op == "halt":
            break
        pc = npc
    return "".join(out)
'''

GO = r'''
package bytevm

import (
	"fmt"
	"strconv"
	"strings"
)

const (
	wrap     = @WRAP@
	floorDiv = @FLOOR@
	stackMax = @STACK@
	memSize  = @MEM@
	callMax  = @CALLS@
	stepMax  = @STEPS@
	hasData  = @DATA@
)

const (
	oPush = iota
	oPop
	oDup
	oSwap
	oOver
	oAdd
	oSub
	oMul
	oDiv
	oMod
	oNeg
	oEq
	oLt
	oGt
	oNot
	oJmp
	oJz
	oJnz
	oCall
	oRet
	oLoad
	oStore
	oIn
	oOut
	oOutc
	oOuts
	oHalt
)

var names = @NAMES_GO@

const lo, hi = -2147483648, 2147483647
const letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
const digs = "0123456789"

func ident(s string) bool {
	if s == "" || !strings.ContainsRune(letters, rune(s[0])) {
		return false
	}
	for _, c := range s {
		if !strings.ContainsRune(letters+digs, c) {
			return false
		}
	}
	return true
}

func toInt(t string) (int64, bool) {
	body := t
	if strings.HasPrefix(t, "-") {
		body = t[1:]
	}
	if body == "" || len(body) > 10 || strings.Trim(body, digs) != "" {
		return 0, false
	}
	v, _ := strconv.ParseInt(t, 10, 64)
	if v < lo || v > hi {
		return 0, false
	}
	return v, true
}

type instr struct {
	op  int
	arg int64
	lab string
}

type asmErr struct {
	line int
	msg  string
}

func norm(x int64) (int64, bool) {
	if x >= lo && x <= hi {
		return x, true
	}
	if !wrap {
		return 0, false
	}
	m := (x + (1 << 31)) % (1 << 32)
	if m < 0 {
		m += 1 << 32
	}
	return m - (1 << 31), true
}

func tdiv(a, b int64) int64 {
	return a / b
}

func fdiv(a, b int64) int64 {
	q := a / b
	if (a%b != 0) && ((a < 0) != (b < 0)) {
		q--
	}
	return q
}

func assemble(program string) ([]instr, map[string]int, []int64, *asmErr) {
	var prog []instr
	labels := map[string]int{}
	var data []int64
	var errs []asmErr
	type ref struct {
		line int
		lab  string
	}
	var refs []ref
	for i, raw := range strings.Split(program, "\n") {
		no := i + 1
		if k := strings.IndexByte(raw, ';'); k >= 0 {
			raw = raw[:k]
		}
		toks := strings.Fields(raw)
		if len(toks) == 0 {
			continue
		}
		label, hasLabel := "", false
		if strings.HasSuffix(toks[0], ":") {
			label, hasLabel = toks[0][:len(toks[0])-1], true
			toks = toks[1:]
			if !ident(label) {
				errs = append(errs, asmErr{no, "bad label"})
				continue
			}
		}
		if len(toks) > 0 && toks[0] == ".word" && hasData {
			var nums []int64
			ok := len(toks) > 1
			for _, t := range toks[1:] {
				v, good := toInt(t)
				if !good {
					ok = false
				}
				nums = append(nums, v)
			}
			if hasLabel || len(prog) > 0 || !ok || len(data)+len(nums) > memSize {
				errs = append(errs, asmErr{no, "bad data"})
			} else {
				data = append(data, nums...)
			}
			continue
		}
		if hasLabel {
			if _, dup := labels[label]; dup {
				errs = append(errs, asmErr{no, "duplicate label"})
				continue
			}
			labels[label] = len(prog)
		}
		if len(toks) == 0 {
			continue
		}
		op := -1
		for k, n := range names {
			if n != "" && n == toks[0] {
				op = k
			}
		}
		if op < 0 {
			errs = append(errs, asmErr{no, "unknown instruction"})
			continue
		}
		args := toks[1:]
		switch op {
		case oPush:
			var v int64
			good := false
			if len(args) == 1 {
				v, good = toInt(args[0])
			}
			if !good {
				errs = append(errs, asmErr{no, "bad operand"})
				continue
			}
			prog = append(prog, instr{op: op, arg: v})
		case oJmp, oJz, oJnz, oCall:
			if len(args) != 1 || !ident(args[0]) {
				errs = append(errs, asmErr{no, "bad operand"})
				continue
			}
			refs = append(refs, ref{no, args[0]})
			prog = append(prog, instr{op: op, lab: args[0]})
		default:
			if len(args) > 0 {
				errs = append(errs, asmErr{no, "bad operand"})
				continue
			}
			prog = append(prog, instr{op: op})
		}
	}
	for _, r := range refs {
		if _, ok := labels[r.lab]; !ok {
			errs = append(errs, asmErr{r.line, "unknown label"})
		}
	}
	if len(errs) == 0 {
		return prog, labels, data, nil
	}
	best := errs[0]
	for _, e := range errs {
		if e.line < best.line {
			best = e
		}
	}
	return prog, labels, data, &best
}

// Run assembles and executes a program.
func Run(program, input string) string {
	prog, labels, data, aerr := assemble(program)
	if aerr != nil {
		return fmt.Sprintf("error: line %d: %s", aerr.line, aerr.msg)
	}
	mem := make([]int64, memSize)
	copy(mem, data)
	toks := strings.Fields(input)
	ti := 0
	var stack []int64
	var rs []int
	var out strings.Builder
	pc, steps := 0, 0
	fail := func(code string) string {
		o := out.String()
		if o != "" && !strings.HasSuffix(o, "\n") {
			o += "\n"
		}
		return fmt.Sprintf("%serror: %s at %d", o, code, pc)
	}
	push := func(v int64) bool {
		if len(stack) >= stackMax {
			return false
		}
		stack = append(stack, v)
		return true
	}
	for pc < len(prog) {
		if steps >= stepMax {
			return fail("steps")
		}
		steps++
		in := prog[pc]
		npc := pc + 1
		need := func(n int) bool { return len(stack) >= n }
		pop := func() int64 {
			v := stack[len(stack)-1]
			stack = stack[:len(stack)-1]
			return v
		}
		halted := false
		switch in.op {
		case oPush:
			if !push(in.arg) {
				return fail("stack-overflow")
			}
		case oPop:
			if !need(1) {
				return fail("stack-underflow")
			}
			pop()
		case oDup:
			if !need(1) {
				return fail("stack-underflow")
			}
			if !push(stack[len(stack)-1]) {
				return fail("stack-overflow")
			}
		case oSwap:
			if !need(2) {
				return fail("stack-underflow")
			}
			n := len(stack)
			stack[n-1], stack[n-2] = stack[n-2], stack[n-1]
		case oOver:
			if !need(2) {
				return fail("stack-underflow")
			}
			if !push(stack[len(stack)-2]) {
				return fail("stack-overflow")
			}
		case oAdd, oSub, oMul, oDiv, oMod, oEq, oLt, oGt:
			if !need(2) {
				return fail("stack-underflow")
			}
			b := pop()
			a := pop()
			var r int64
			ok := true
			switch in.op {
			case oAdd:
				r, ok = norm(a + b)
			case oSub:
				r, ok = norm(a - b)
			case oMul:
				r, ok = norm(a * b)
			case oDiv, oMod:
				if b == 0 {
					return fail("div0")
				}
				q := tdiv(a, b)
				if floorDiv {
					q = fdiv(a, b)
				}
				if in.op == oDiv {
					r, ok = norm(q)
				} else {
					r = a - b*q
				}
			case oEq:
				if a == b {
					r = 1
				}
			case oLt:
				if a < b {
					r = 1
				}
			case oGt:
				if a > b {
					r = 1
				}
			}
			if !ok {
				return fail("overflow")
			}
			stack = append(stack, r)
		case oNeg:
			if !need(1) {
				return fail("stack-underflow")
			}
			r, ok := norm(-pop())
			if !ok {
				return fail("overflow")
			}
			stack = append(stack, r)
		case oNot:
			if !need(1) {
				return fail("stack-underflow")
			}
			if pop() == 0 {
				stack = append(stack, 1)
			} else {
				stack = append(stack, 0)
			}
		case oJmp:
			npc = labels[in.lab]
		case oJz, oJnz:
			if !need(1) {
				return fail("stack-underflow")
			}
			v := pop()
			if (v == 0) == (in.op == oJz) {
				npc = labels[in.lab]
			}
		case oCall:
			if len(rs) >= callMax {
				return fail("call-depth")
			}
			rs = append(rs, pc+1)
			npc = labels[in.lab]
		case oRet:
			if len(rs) == 0 {
				return fail("ret-empty")
			}
			npc = rs[len(rs)-1]
			rs = rs[:len(rs)-1]
		case oLoad:
			if !need(1) {
				return fail("stack-underflow")
			}
			a := pop()
			if a < 0 || a >= memSize {
				return fail("bad-address")
			}
			stack = append(stack, mem[a])
		case oStore:
			if !need(2) {
				return fail("stack-underflow")
			}
			a := pop()
			v := pop()
			if a < 0 || a >= memSize {
				return fail("bad-address")
			}
			mem[a] = v
		case oIn:
			if ti >= len(toks) {
				return fail("input")
			}
			v, good := toInt(toks[ti])
			if !good {
				return fail("input")
			}
			ti++
			if !push(v) {
				return fail("stack-overflow")
			}
		case oOut:
			if !need(1) {
				return fail("stack-underflow")
			}
			out.WriteString(strconv.FormatInt(pop(), 10) + "\n")
		case oOutc:
			if !need(1) {
				return fail("stack-underflow")
			}
			v := pop()
			if v < 1 || v > 127 {
				return fail("char")
			}
			out.WriteByte(byte(v))
		case oOuts:
			if !need(1) {
				return fail("stack-underflow")
			}
			a := pop()
			if a < 0 || a >= memSize {
				return fail("bad-address")
			}
			for mem[a] != 0 {
				if mem[a] < 0 || mem[a] > 127 {
					return fail("char")
				}
				out.WriteByte(byte(mem[a]))
				a++
				if a >= memSize {
					return fail("bad-address")
				}
			}
		case oHalt:
			halted = true
		}
		if halted {
			break
		}
		pc = npc
	}
	return out.String()
}
'''

RS = r'''
const WRAP: bool = @WRAP@;
const FLOOR_DIV: bool = @FLOOR@;
const STACK_MAX: usize = @STACK@;
const MEM_SIZE: usize = @MEM@;
const CALL_MAX: usize = @CALLS@;
const STEP_MAX: usize = @STEPS@;
const HAS_DATA: bool = @DATA@;
const NAMES: [&str; 27] = @NAMES_RS@;
const LO: i64 = -2147483648;
const HI: i64 = 2147483647;
const LETTERS: &str = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_";
const DIGS: &str = "0123456789";

const PUSH: usize = 0;
const POP: usize = 1;
const DUP: usize = 2;
const SWAP: usize = 3;
const OVER: usize = 4;
const ADD: usize = 5;
const SUB: usize = 6;
const MUL: usize = 7;
const DIV: usize = 8;
const MOD: usize = 9;
const NEG: usize = 10;
const EQ: usize = 11;
const LT: usize = 12;
const GT: usize = 13;
const NOT: usize = 14;
const JMP: usize = 15;
const JZ: usize = 16;
const JNZ: usize = 17;
const CALL: usize = 18;
const RET: usize = 19;
const LOAD: usize = 20;
const STORE: usize = 21;
const IN: usize = 22;
const OUT: usize = 23;
const OUTC: usize = 24;
const OUTS: usize = 25;
const HALT: usize = 26;

fn ident(s: &str) -> bool {
    let mut cs = s.chars();
    match cs.next() {
        Some(c) if LETTERS.contains(c) => {}
        _ => return false,
    }
    s.chars().all(|c| LETTERS.contains(c) || DIGS.contains(c))
}

fn to_int(t: &str) -> Option<i64> {
    let body = t.strip_prefix('-').unwrap_or(t);
    if body.is_empty() || body.len() > 10 || !body.chars().all(|c| DIGS.contains(c)) {
        return None;
    }
    let v: i64 = t.parse().ok()?;
    if v < LO || v > HI { None } else { Some(v) }
}

struct Instr {
    op: usize,
    arg: i64,
    lab: String,
}

fn norm(x: i64) -> Option<i64> {
    if x >= LO && x <= HI {
        return Some(x);
    }
    if !WRAP {
        return None;
    }
    Some((x + (1i64 << 31)).rem_euclid(1i64 << 32) - (1i64 << 31))
}

fn tdiv(a: i64, b: i64) -> i64 {
    a / b
}

fn fdiv(a: i64, b: i64) -> i64 {
    let q = a / b;
    if a % b != 0 && ((a < 0) != (b < 0)) { q - 1 } else { q }
}

fn assemble(program: &str) -> (Vec<Instr>, Vec<(String, usize)>, Vec<i64>, Option<(usize, &'static str)>) {
    let mut prog: Vec<Instr> = Vec::new();
    let mut labels: Vec<(String, usize)> = Vec::new();
    let mut data: Vec<i64> = Vec::new();
    let mut errs: Vec<(usize, &'static str)> = Vec::new();
    let mut refs: Vec<(usize, String)> = Vec::new();
    for (i, raw) in program.split('\n').enumerate() {
        let no = i + 1;
        let text = raw.split(';').next().unwrap_or("");
        let mut toks: Vec<&str> = text.split_whitespace().collect();
        if toks.is_empty() {
            continue;
        }
        let mut label: Option<String> = None;
        if toks[0].ends_with(':') {
            let l = toks[0][..toks[0].len() - 1].to_string();
            toks.remove(0);
            if !ident(&l) {
                errs.push((no, "bad label"));
                continue;
            }
            label = Some(l);
        }
        if HAS_DATA && !toks.is_empty() && toks[0] == ".word" {
            let nums: Vec<Option<i64>> = toks[1..].iter().map(|t| to_int(t)).collect();
            if label.is_some() || !prog.is_empty() || nums.is_empty() || nums.iter().any(|x| x.is_none()) || data.len() + nums.len() > MEM_SIZE {
                errs.push((no, "bad data"));
            } else {
                data.extend(nums.iter().map(|x| x.unwrap()));
            }
            continue;
        }
        if let Some(l) = label {
            if labels.iter().any(|(n, _)| *n == l) {
                errs.push((no, "duplicate label"));
                continue;
            }
            labels.push((l, prog.len()));
        }
        if toks.is_empty() {
            continue;
        }
        let op = match NAMES.iter().position(|n| !n.is_empty() && *n == toks[0]) {
            Some(o) => o,
            None => {
                errs.push((no, "unknown instruction"));
                continue;
            }
        };
        let args = &toks[1..];
        match op {
            PUSH => {
                let v = if args.len() == 1 { to_int(args[0]) } else { None };
                match v {
                    Some(v) => prog.push(Instr { op, arg: v, lab: String::new() }),
                    None => errs.push((no, "bad operand")),
                }
            }
            JMP | JZ | JNZ | CALL => {
                if args.len() != 1 || !ident(args[0]) {
                    errs.push((no, "bad operand"));
                    continue;
                }
                refs.push((no, args[0].to_string()));
                prog.push(Instr { op, arg: 0, lab: args[0].to_string() });
            }
            _ => {
                if !args.is_empty() {
                    errs.push((no, "bad operand"));
                    continue;
                }
                prog.push(Instr { op, arg: 0, lab: String::new() });
            }
        }
    }
    for (no, lab) in &refs {
        if !labels.iter().any(|(n, _)| n == lab) {
            errs.push((*no, "unknown label"));
        }
    }
    let best = errs.iter().min_by_key(|e| e.0).cloned();
    (prog, labels, data, best)
}

fn target(labels: &[(String, usize)], lab: &str) -> usize {
    labels.iter().find(|(n, _)| n == lab).map(|(_, a)| *a).unwrap_or(0)
}

/// Assembles and executes a program.
pub fn run(program: &str, input: &str) -> String {
    let (prog, labels, data, err) = assemble(program);
    if let Some((line, msg)) = err {
        return format!("error: line {}: {}", line, msg);
    }
    let mut mem = vec![0i64; MEM_SIZE];
    for (i, v) in data.iter().enumerate() {
        mem[i] = *v;
    }
    let toks: Vec<&str> = input.split_whitespace().collect();
    let mut ti = 0usize;
    let mut stack: Vec<i64> = Vec::new();
    let mut rs: Vec<usize> = Vec::new();
    let mut out = String::new();
    let mut pc = 0usize;
    let mut steps = 0usize;
    macro_rules! fail {
        ($code:expr) => {{
            let mut o = out.clone();
            if !o.is_empty() && !o.ends_with('\n') {
                o.push('\n');
            }
            return format!("{}error: {} at {}", o, $code, pc);
        }};
    }
    while pc < prog.len() {
        if steps >= STEP_MAX {
            fail!("steps");
        }
        steps += 1;
        let ins = &prog[pc];
        let mut npc = pc + 1;
        let n = stack.len();
        match ins.op {
            PUSH => {
                if n >= STACK_MAX {
                    fail!("stack-overflow");
                }
                stack.push(ins.arg);
            }
            POP => {
                if n < 1 {
                    fail!("stack-underflow");
                }
                stack.pop();
            }
            DUP => {
                if n < 1 {
                    fail!("stack-underflow");
                }
                if n >= STACK_MAX {
                    fail!("stack-overflow");
                }
                let v = stack[n - 1];
                stack.push(v);
            }
            SWAP => {
                if n < 2 {
                    fail!("stack-underflow");
                }
                stack.swap(n - 1, n - 2);
            }
            OVER => {
                if n < 2 {
                    fail!("stack-underflow");
                }
                if n >= STACK_MAX {
                    fail!("stack-overflow");
                }
                let v = stack[n - 2];
                stack.push(v);
            }
            ADD | SUB | MUL | DIV | MOD | EQ | LT | GT => {
                if n < 2 {
                    fail!("stack-underflow");
                }
                let b = stack.pop().unwrap();
                let a = stack.pop().unwrap();
                let r: Option<i64> = match ins.op {
                    ADD => norm(a + b),
                    SUB => norm(a - b),
                    MUL => norm(a * b),
                    DIV | MOD => {
                        if b == 0 {
                            fail!("div0");
                        }
                        let q = if FLOOR_DIV { fdiv(a, b) } else { tdiv(a, b) };
                        if ins.op == DIV { norm(q) } else { Some(a - b * q) }
                    }
                    EQ => Some((a == b) as i64),
                    LT => Some((a < b) as i64),
                    _ => Some((a > b) as i64),
                };
                match r {
                    Some(v) => stack.push(v),
                    None => fail!("overflow"),
                }
            }
            NEG => {
                if n < 1 {
                    fail!("stack-underflow");
                }
                let a = stack.pop().unwrap();
                match norm(-a) {
                    Some(v) => stack.push(v),
                    None => fail!("overflow"),
                }
            }
            NOT => {
                if n < 1 {
                    fail!("stack-underflow");
                }
                let a = stack.pop().unwrap();
                stack.push((a == 0) as i64);
            }
            JMP => npc = target(&labels, &ins.lab),
            JZ | JNZ => {
                if n < 1 {
                    fail!("stack-underflow");
                }
                let v = stack.pop().unwrap();
                if (v == 0) == (ins.op == JZ) {
                    npc = target(&labels, &ins.lab);
                }
            }
            CALL => {
                if rs.len() >= CALL_MAX {
                    fail!("call-depth");
                }
                rs.push(pc + 1);
                npc = target(&labels, &ins.lab);
            }
            RET => match rs.pop() {
                Some(a) => npc = a,
                None => fail!("ret-empty"),
            },
            LOAD => {
                if n < 1 {
                    fail!("stack-underflow");
                }
                let a = stack.pop().unwrap();
                if a < 0 || a >= MEM_SIZE as i64 {
                    fail!("bad-address");
                }
                stack.push(mem[a as usize]);
            }
            STORE => {
                if n < 2 {
                    fail!("stack-underflow");
                }
                let a = stack.pop().unwrap();
                let v = stack.pop().unwrap();
                if a < 0 || a >= MEM_SIZE as i64 {
                    fail!("bad-address");
                }
                mem[a as usize] = v;
            }
            IN => {
                if ti >= toks.len() {
                    fail!("input");
                }
                let v = match to_int(toks[ti]) {
                    Some(v) => v,
                    None => fail!("input"),
                };
                ti += 1;
                if n >= STACK_MAX {
                    fail!("stack-overflow");
                }
                stack.push(v);
            }
            OUT => {
                if n < 1 {
                    fail!("stack-underflow");
                }
                let v = stack.pop().unwrap();
                out.push_str(&format!("{}\n", v));
            }
            OUTC => {
                if n < 1 {
                    fail!("stack-underflow");
                }
                let v = stack.pop().unwrap();
                if v < 1 || v > 127 {
                    fail!("char");
                }
                out.push(v as u8 as char);
            }
            OUTS => {
                if n < 1 {
                    fail!("stack-underflow");
                }
                let mut a = stack.pop().unwrap();
                if a < 0 || a >= MEM_SIZE as i64 {
                    fail!("bad-address");
                }
                while mem[a as usize] != 0 {
                    let c = mem[a as usize];
                    if c < 0 || c > 127 {
                        fail!("char");
                    }
                    out.push(c as u8 as char);
                    a += 1;
                    if a >= MEM_SIZE as i64 {
                        fail!("bad-address");
                    }
                }
            }
            _ => break,
        }
        pc = npc;
    }
    out
}
'''

JV = r'''
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class Bytevm {
    static final boolean WRAP = @WRAP@;
    static final boolean FLOOR_DIV = @FLOOR@;
    static final int STACK_MAX = @STACK@;
    static final int MEM_SIZE = @MEM@;
    static final int CALL_MAX = @CALLS@;
    static final int STEP_MAX = @STEPS@;
    static final boolean HAS_DATA = @DATA@;
    static final String[] NAMES = @NAMES_JAVA@;
    static final long LO = -2147483648L, HI = 2147483647L;
    static final String LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_";
    static final String DIGS = "0123456789";
    static final int PUSH = 0, POP = 1, DUP = 2, SWAP = 3, OVER = 4, ADD = 5, SUB = 6, MUL = 7, DIV = 8, MOD = 9, NEG = 10, EQ = 11, LT = 12,
        GT = 13, NOT = 14, JMP = 15, JZ = 16, JNZ = 17, CALL = 18, RET = 19, LOAD = 20, STORE = 21, IN = 22, OUT = 23, OUTC = 24,
        OUTS = 25, HALT = 26;

    static boolean ident(String s) {
        if (s.isEmpty() || LETTERS.indexOf(s.charAt(0)) < 0) return false;
        for (char c : s.toCharArray()) if (LETTERS.indexOf(c) < 0 && DIGS.indexOf(c) < 0) return false;
        return true;
    }

    static Long toInt(String t) {
        String body = t.startsWith("-") ? t.substring(1) : t;
        if (body.isEmpty() || body.length() > 10) return null;
        for (char c : body.toCharArray()) if (DIGS.indexOf(c) < 0) return null;
        long v = Long.parseLong(t);
        return (v < LO || v > HI) ? null : v;
    }

    static class Instr {
        int op;
        long arg;
        String lab;
        Instr(int op, long arg, String lab) { this.op = op; this.arg = arg; this.lab = lab; }
    }

    static Long norm(long x) {
        if (x >= LO && x <= HI) return x;
        if (!WRAP) return null;
        return Math.floorMod(x + (1L << 31), 1L << 32) - (1L << 31);
    }

    static long fdiv(long a, long b) {
        long q = a / b;
        if (a % b != 0 && ((a < 0) != (b < 0))) q--;
        return q;
    }

    static String[] split(String s) {
        String t = s.trim();
        return t.isEmpty() ? new String[0] : t.split("\\s+");
    }

    public static String run(String program, String input) {
        List<Instr> prog = new ArrayList<>();
        Map<String, Integer> labels = new HashMap<>();
        List<Long> data = new ArrayList<>();
        int errLine = Integer.MAX_VALUE;
        String errMsg = null;
        List<Object[]> refs = new ArrayList<>();
        String[] lines = program.split("\n", -1);
        for (int i = 0; i < lines.length; i++) {
            int no = i + 1;
            String raw = lines[i];
            int sc = raw.indexOf(';');
            if (sc >= 0) raw = raw.substring(0, sc);
            String[] all = split(raw);
            if (all.length == 0) continue;
            int start = 0;
            String label = null;
            String bad = null;
            if (all[0].endsWith(":")) {
                label = all[0].substring(0, all[0].length() - 1);
                start = 1;
                if (!ident(label)) bad = "bad label";
            }
            if (bad == null && HAS_DATA && all.length > start && all[start].equals(".word")) {
                boolean ok = all.length > start + 1;
                List<Long> nums = new ArrayList<>();
                for (int k = start + 1; k < all.length; k++) {
                    Long v = toInt(all[k]);
                    if (v == null) ok = false; else nums.add(v);
                }
                if (label != null || !prog.isEmpty() || !ok || data.size() + nums.size() > MEM_SIZE) bad = "bad data";
                else data.addAll(nums);
                if (bad != null && no < errLine) { errLine = no; errMsg = bad; }
                continue;
            }
            if (bad == null && label != null) {
                if (labels.containsKey(label)) bad = "duplicate label";
                else labels.put(label, prog.size());
            }
            if (bad != null) {
                if (no < errLine) { errLine = no; errMsg = bad; }
                continue;
            }
            if (all.length <= start) continue;
            int op = -1;
            for (int k = 0; k < NAMES.length; k++) if (!NAMES[k].isEmpty() && NAMES[k].equals(all[start])) op = k;
            if (op < 0) {
                if (no < errLine) { errLine = no; errMsg = "unknown instruction"; }
                continue;
            }
            int nargs = all.length - start - 1;
            String a0 = nargs > 0 ? all[start + 1] : null;
            if (op == PUSH) {
                Long v = nargs == 1 ? toInt(a0) : null;
                if (v == null) {
                    if (no < errLine) { errLine = no; errMsg = "bad operand"; }
                    continue;
                }
                prog.add(new Instr(op, v, null));
            } else if (op == JMP || op == JZ || op == JNZ || op == CALL) {
                if (nargs != 1 || !ident(a0)) {
                    if (no < errLine) { errLine = no; errMsg = "bad operand"; }
                    continue;
                }
                refs.add(new Object[] { no, a0 });
                prog.add(new Instr(op, 0, a0));
            } else {
                if (nargs > 0) {
                    if (no < errLine) { errLine = no; errMsg = "bad operand"; }
                    continue;
                }
                prog.add(new Instr(op, 0, null));
            }
        }
        for (Object[] r : refs) {
            if (!labels.containsKey((String) r[1]) && (Integer) r[0] < errLine) { errLine = (Integer) r[0]; errMsg = "unknown label"; }
        }
        if (errMsg != null) return "error: line " + errLine + ": " + errMsg;
        long[] mem = new long[MEM_SIZE];
        for (int i = 0; i < data.size(); i++) mem[i] = data.get(i);
        String[] toks = split(input);
        int ti = 0;
        long[] stack = new long[STACK_MAX];
        int sp = 0;
        int[] rs = new int[CALL_MAX];
        int rp = 0;
        StringBuilder out = new StringBuilder();
        int pc = 0, steps = 0;
        while (pc < prog.size()) {
            String code = null;
            if (steps >= STEP_MAX) code = "steps";
            steps++;
            Instr in = prog.get(pc);
            int npc = pc + 1;
            boolean halt = false;
            if (code == null) {
                switch (in.op) {
                    case PUSH:
                        if (sp >= STACK_MAX) code = "stack-overflow"; else stack[sp++] = in.arg;
                        break;
                    case POP:
                        if (sp < 1) code = "stack-underflow"; else sp--;
                        break;
                    case DUP:
                        if (sp < 1) code = "stack-underflow";
                        else if (sp >= STACK_MAX) code = "stack-overflow";
                        else { stack[sp] = stack[sp - 1]; sp++; }
                        break;
                    case SWAP:
                        if (sp < 2) code = "stack-underflow";
                        else { long t = stack[sp - 1]; stack[sp - 1] = stack[sp - 2]; stack[sp - 2] = t; }
                        break;
                    case OVER:
                        if (sp < 2) code = "stack-underflow";
                        else if (sp >= STACK_MAX) code = "stack-overflow";
                        else { stack[sp] = stack[sp - 2]; sp++; }
                        break;
                    case ADD: case SUB: case MUL: case DIV: case MOD: case EQ: case LT: case GT: {
                        if (sp < 2) { code = "stack-underflow"; break; }
                        long b = stack[--sp];
                        long a = stack[--sp];
                        Long r = null;
                        if (in.op == ADD) r = norm(a + b);
                        else if (in.op == SUB) r = norm(a - b);
                        else if (in.op == MUL) r = norm(a * b);
                        else if (in.op == DIV || in.op == MOD) {
                            if (b == 0) { code = "div0"; break; }
                            long q = FLOOR_DIV ? fdiv(a, b) : a / b;
                            r = in.op == DIV ? norm(q) : Long.valueOf(a - b * q);
                        } else if (in.op == EQ) r = a == b ? 1L : 0L;
                        else if (in.op == LT) r = a < b ? 1L : 0L;
                        else r = a > b ? 1L : 0L;
                        if (r == null) code = "overflow"; else stack[sp++] = r;
                        break;
                    }
                    case NEG: {
                        if (sp < 1) { code = "stack-underflow"; break; }
                        Long r = norm(-stack[--sp]);
                        if (r == null) code = "overflow"; else stack[sp++] = r;
                        break;
                    }
                    case NOT:
                        if (sp < 1) code = "stack-underflow"; else { stack[sp - 1] = stack[sp - 1] == 0 ? 1 : 0; }
                        break;
                    case JMP:
                        npc = labels.get(in.lab);
                        break;
                    case JZ: case JNZ: {
                        if (sp < 1) { code = "stack-underflow"; break; }
                        long v = stack[--sp];
                        if ((v == 0) == (in.op == JZ)) npc = labels.get(in.lab);
                        break;
                    }
                    case CALL:
                        if (rp >= CALL_MAX) code = "call-depth"; else { rs[rp++] = pc + 1; npc = labels.get(in.lab); }
                        break;
                    case RET:
                        if (rp == 0) code = "ret-empty"; else npc = rs[--rp];
                        break;
                    case LOAD: {
                        if (sp < 1) { code = "stack-underflow"; break; }
                        long a = stack[--sp];
                        if (a < 0 || a >= MEM_SIZE) code = "bad-address"; else stack[sp++] = mem[(int) a];
                        break;
                    }
                    case STORE: {
                        if (sp < 2) { code = "stack-underflow"; break; }
                        long a = stack[--sp];
                        long v = stack[--sp];
                        if (a < 0 || a >= MEM_SIZE) code = "bad-address"; else mem[(int) a] = v;
                        break;
                    }
                    case IN: {
                        if (ti >= toks.length) { code = "input"; break; }
                        Long v = toInt(toks[ti]);
                        if (v == null) { code = "input"; break; }
                        ti++;
                        if (sp >= STACK_MAX) code = "stack-overflow"; else stack[sp++] = v;
                        break;
                    }
                    case OUT:
                        if (sp < 1) code = "stack-underflow"; else out.append(stack[--sp]).append("\n");
                        break;
                    case OUTC: {
                        if (sp < 1) { code = "stack-underflow"; break; }
                        long v = stack[--sp];
                        if (v < 1 || v > 127) code = "char"; else out.append((char) v);
                        break;
                    }
                    case OUTS: {
                        if (sp < 1) { code = "stack-underflow"; break; }
                        long a = stack[--sp];
                        if (a < 0 || a >= MEM_SIZE) { code = "bad-address"; break; }
                        int p = (int) a;
                        while (mem[p] != 0) {
                            if (mem[p] < 0 || mem[p] > 127) { code = "char"; break; }
                            out.append((char) mem[p]);
                            p++;
                            if (p >= MEM_SIZE) { code = "bad-address"; break; }
                        }
                        break;
                    }
                    default:
                        halt = true;
                }
            }
            if (code != null) {
                String o = out.toString();
                if (!o.isEmpty() && !o.endsWith("\n")) o += "\n";
                return o + "error: " + code + " at " + pc;
            }
            if (halt) break;
            pc = npc;
        }
        return out.toString();
    }
}
'''

CC = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bytevm.h"

#define WRAP @WRAP@
#define FLOOR_DIV @FLOOR@
#define STACK_MAX @STACK@
#define MEM_SIZE @MEM@
#define CALL_MAX @CALLS@
#define STEP_MAX @STEPS@
#define HAS_DATA @DATA@
#define LO (-2147483648LL)
#define HI 2147483647LL
enum { PUSH, POP, DUP, SWAP, OVER, ADD, SUB, MUL, DIV, MOD, NEG, EQ, LT, GT, NOT, JMP, JZ, JNZ, CALL, RET, LOAD, STORE, IN, OUT, OUTC, OUTS, HALT, NOPS };
static const char *NAMES[NOPS] = @NAMES_C@;
static const char *LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_";
static const char *DIGS = "0123456789";

typedef struct { int op; long long arg; char lab[64]; int target; } Instr;
typedef struct { char *p; size_t n, cap; } Buf;

static void put(Buf *b, const char *s, size_t len) {
    if (b->n + len + 1 > b->cap) {
        b->cap = (b->n + len + 1) * 2;
        b->p = realloc(b->p, b->cap);
    }
    memcpy(b->p + b->n, s, len);
    b->n += len;
    b->p[b->n] = 0;
}

static int ident(const char *s) {
    if (!*s || !strchr(LETTERS, s[0])) return 0;
    for (size_t i = 0; s[i]; i++)
        if (!strchr(LETTERS, s[i]) && !strchr(DIGS, s[i])) return 0;
    return 1;
}

static int to_int(const char *t, long long *out) {
    const char *body = t[0] == '-' ? t + 1 : t;
    size_t n = strlen(body);
    if (n == 0 || n > 10) return 0;
    for (size_t i = 0; i < n; i++)
        if (!strchr(DIGS, body[i])) return 0;
    long long v = atoll(t);
    if (v < LO || v > HI) return 0;
    *out = v;
    return 1;
}

static int norm(long long x, long long *r) {
    if (x >= LO && x <= HI) { *r = x; return 1; }
    if (!WRAP) return 0;
    long long m = (x + (1LL << 31)) % (1LL << 32);
    if (m < 0) m += (1LL << 32);
    *r = m - (1LL << 31);
    return 1;
}

static long long fdiv(long long a, long long b) {
    long long q = a / b;
    if (a % b != 0 && ((a < 0) != (b < 0))) q--;
    return q;
}

static int split_ws(char *s, char **t, int max) {
    int n = 0;
    char *p = s;
    while (*p) {
        while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n' || *p == '\v' || *p == '\f') *p++ = 0;
        if (!*p) break;
        if (n < max) t[n] = p;
        n++;
        while (*p && !(*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n' || *p == '\v' || *p == '\f')) p++;
    }
    return n;
}

static char *dupstr(const char *s) {
    char *r = malloc(strlen(s) + 1);
    strcpy(r, s);
    return r;
}

typedef struct { char name[64]; int addr; } Label;

char *run(const char *program, const char *input) {
    size_t pl = strlen(program);
    Instr *prog = malloc((pl + 2) * sizeof(Instr));
    int np = 0;
    Label *labels = malloc((pl + 2) * sizeof(Label));
    int nl = 0;
    long long data[MEM_SIZE + 1];
    int nd = 0;
    int err_line = 1 << 30;
    const char *err_msg = NULL;
    int *ref_line = malloc((pl + 2) * sizeof(int));
    int nref = 0;
    char *copy = dupstr(program);
    int lineno = 0;
    char *cur = copy;
#define SETERR(msg) do { if (lineno < err_line) { err_line = lineno; err_msg = msg; } } while (0)
    while (1) {
        char *nlp = strchr(cur, '\n');
        if (nlp) *nlp = 0;
        lineno++;
        char *sc = strchr(cur, ';');
        if (sc) *sc = 0;
        char *toks[512];
        int nt = split_ws(cur, toks, 512);
        if (nt > 0) {
            int start = 0;
            int has_label = 0;
            char label[64];
            const char *bad = NULL;
            if (toks[0][strlen(toks[0]) - 1] == ':') {
                has_label = 1;
                size_t ll = strlen(toks[0]) - 1;
                if (ll >= 63) ll = 63;
                memcpy(label, toks[0], ll);
                label[ll] = 0;
                start = 1;
                if (!ident(label)) bad = "bad label";
            }
            if (!bad && HAS_DATA && nt > start && strcmp(toks[start], ".word") == 0) {
                int ok = nt > start + 1;
                long long nums[512];
                int nn = 0;
                for (int k = start + 1; k < nt; k++) {
                    long long v;
                    if (!to_int(toks[k], &v)) ok = 0;
                    else nums[nn++] = v;
                }
                if (has_label || np > 0 || !ok || nd + nn > MEM_SIZE) bad = "bad data";
                else for (int k = 0; k < nn; k++) data[nd++] = nums[k];
                if (bad) SETERR(bad);
            } else {
                if (!bad && has_label) {
                    int dup = 0;
                    for (int k = 0; k < nl; k++) if (strcmp(labels[k].name, label) == 0) dup = 1;
                    if (dup) bad = "duplicate label";
                    else { strcpy(labels[nl].name, label); labels[nl].addr = np; nl++; }
                }
                if (bad) SETERR(bad);
                else if (nt > start) {
                    int op = -1;
                    for (int k = 0; k < NOPS; k++) if (NAMES[k][0] && strcmp(NAMES[k], toks[start]) == 0) op = k;
                    int nargs = nt - start - 1;
                    const char *a0 = nargs > 0 ? toks[start + 1] : NULL;
                    if (op < 0) SETERR("unknown instruction");
                    else if (op == PUSH) {
                        long long v;
                        if (nargs != 1 || !to_int(a0, &v)) SETERR("bad operand");
                        else { prog[np].op = op; prog[np].arg = v; prog[np].lab[0] = 0; np++; }
                    } else if (op == JMP || op == JZ || op == JNZ || op == CALL) {
                        if (nargs != 1 || !ident(a0) || strlen(a0) >= 64) SETERR("bad operand");
                        else { prog[np].op = op; prog[np].arg = 0; strcpy(prog[np].lab, a0); ref_line[nref++] = lineno; np++; }
                    } else {
                        if (nargs > 0) SETERR("bad operand");
                        else { prog[np].op = op; prog[np].arg = 0; prog[np].lab[0] = 0; np++; }
                    }
                }
            }
        }
        if (!nlp) break;
        cur = nlp + 1;
    }
    /* resolve labels */
    {
        int r = 0;
        for (int i = 0; i < np; i++) {
            if (prog[i].lab[0]) {
                int found = -1;
                for (int k = 0; k < nl; k++) if (strcmp(labels[k].name, prog[i].lab) == 0) found = labels[k].addr;
                prog[i].target = found;
                if (found < 0) {
                    lineno = ref_line[r];
                    SETERR("unknown label");
                }
                r++;
            }
        }
    }
    free(copy);
    if (err_msg) {
        char buf[96];
        sprintf(buf, "error: line %d: %s", err_line, err_msg);
        free(prog); free(labels); free(ref_line);
        return dupstr(buf);
    }
    long long mem[MEM_SIZE];
    memset(mem, 0, sizeof mem);
    for (int i = 0; i < nd; i++) mem[i] = data[i];
    char *icopy = dupstr(input);
    int ntok = 0;
    char **itoks = malloc((strlen(input) + 2) * sizeof(char *));
    {
        char *p = icopy;
        while (*p) {
            while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n' || *p == '\v' || *p == '\f') *p++ = 0;
            if (!*p) break;
            itoks[ntok++] = p;
            while (*p && !(*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n' || *p == '\v' || *p == '\f')) p++;
        }
    }
    int ti = 0;
    long long stack[STACK_MAX + 1];
    int sp = 0;
    int rs[CALL_MAX + 1];
    int rp = 0;
    Buf out = {0};
    put(&out, "", 0);
    int pc = 0, steps = 0;
    char tmp[64];
    while (pc < np) {
        const char *code = NULL;
        if (steps >= STEP_MAX) code = "steps";
        steps++;
        Instr *in = &prog[pc];
        int npc = pc + 1;
        int halt = 0;
        if (!code) {
            switch (in->op) {
            case PUSH: if (sp >= STACK_MAX) code = "stack-overflow"; else stack[sp++] = in->arg; break;
            case POP: if (sp < 1) code = "stack-underflow"; else sp--; break;
            case DUP:
                if (sp < 1) code = "stack-underflow";
                else if (sp >= STACK_MAX) code = "stack-overflow";
                else { stack[sp] = stack[sp - 1]; sp++; }
                break;
            case SWAP:
                if (sp < 2) code = "stack-underflow";
                else { long long t = stack[sp - 1]; stack[sp - 1] = stack[sp - 2]; stack[sp - 2] = t; }
                break;
            case OVER:
                if (sp < 2) code = "stack-underflow";
                else if (sp >= STACK_MAX) code = "stack-overflow";
                else { stack[sp] = stack[sp - 2]; sp++; }
                break;
            case ADD: case SUB: case MUL: case DIV: case MOD: case EQ: case LT: case GT: {
                if (sp < 2) { code = "stack-underflow"; break; }
                long long b = stack[--sp];
                long long a = stack[--sp];
                long long r = 0;
                int ok = 1;
                if (in->op == ADD) ok = norm(a + b, &r);
                else if (in->op == SUB) ok = norm(a - b, &r);
                else if (in->op == MUL) ok = norm(a * b, &r);
                else if (in->op == DIV || in->op == MOD) {
                    if (b == 0) { code = "div0"; break; }
                    long long q = FLOOR_DIV ? fdiv(a, b) : a / b;
                    if (in->op == DIV) ok = norm(q, &r); else r = a - b * q;
                } else if (in->op == EQ) r = a == b;
                else if (in->op == LT) r = a < b;
                else r = a > b;
                if (!ok) code = "overflow"; else stack[sp++] = r;
                break;
            }
            case NEG: {
                if (sp < 1) { code = "stack-underflow"; break; }
                long long r;
                if (!norm(-stack[--sp], &r)) code = "overflow"; else stack[sp++] = r;
                break;
            }
            case NOT: if (sp < 1) code = "stack-underflow"; else stack[sp - 1] = stack[sp - 1] == 0; break;
            case JMP: npc = in->target; break;
            case JZ: case JNZ: {
                if (sp < 1) { code = "stack-underflow"; break; }
                long long v = stack[--sp];
                if ((v == 0) == (in->op == JZ)) npc = in->target;
                break;
            }
            case CALL: if (rp >= CALL_MAX) code = "call-depth"; else { rs[rp++] = pc + 1; npc = in->target; } break;
            case RET: if (rp == 0) code = "ret-empty"; else npc = rs[--rp]; break;
            case LOAD: {
                if (sp < 1) { code = "stack-underflow"; break; }
                long long a = stack[--sp];
                if (a < 0 || a >= MEM_SIZE) code = "bad-address"; else stack[sp++] = mem[a];
                break;
            }
            case STORE: {
                if (sp < 2) { code = "stack-underflow"; break; }
                long long a = stack[--sp];
                long long v = stack[--sp];
                if (a < 0 || a >= MEM_SIZE) code = "bad-address"; else mem[a] = v;
                break;
            }
            case IN: {
                long long v;
                if (ti >= ntok || !to_int(itoks[ti], &v)) { code = "input"; break; }
                ti++;
                if (sp >= STACK_MAX) code = "stack-overflow"; else stack[sp++] = v;
                break;
            }
            case OUT:
                if (sp < 1) code = "stack-underflow";
                else { sprintf(tmp, "%lld\n", stack[--sp]); put(&out, tmp, strlen(tmp)); }
                break;
            case OUTC: {
                if (sp < 1) { code = "stack-underflow"; break; }
                long long v = stack[--sp];
                if (v < 1 || v > 127) code = "char";
                else { char c = (char)v; put(&out, &c, 1); }
                break;
            }
            case OUTS: {
                if (sp < 1) { code = "stack-underflow"; break; }
                long long a = stack[--sp];
                if (a < 0 || a >= MEM_SIZE) { code = "bad-address"; break; }
                while (mem[a] != 0) {
                    if (mem[a] < 0 || mem[a] > 127) { code = "char"; break; }
                    char c = (char)mem[a];
                    put(&out, &c, 1);
                    a++;
                    if (a >= MEM_SIZE) { code = "bad-address"; break; }
                }
                break;
            }
            default: halt = 1;
            }
        }
        if (code) {
            if (out.n > 0 && out.p[out.n - 1] != '\n') put(&out, "\n", 1);
            sprintf(tmp, "error: %s at %d", code, pc);
            put(&out, tmp, strlen(tmp));
            free(prog); free(labels); free(ref_line); free(icopy); free(itoks);
            return out.p;
        }
        if (halt) break;
        pc = npc;
    }
    free(prog); free(labels); free(ref_line); free(icopy); free(itoks);
    return out.p;
}
'''


def _b(lang, v):
    if lang == "python":
        return "True" if v else "False"
    if lang == "c":
        return "1" if v else "0"
    return "true" if v else "false"


def sol(lang, p):
    names = [p["names"].get(op, "") for op in OPS]
    py = "[" + ", ".join(f'"{n}"' for n in names) + "]"
    go = "[27]string{" + ", ".join(f'"{n}"' for n in names) + "}"
    rs = "[" + ", ".join(f'"{n}"' for n in names) + "]"
    jv = "{" + ", ".join(f'"{n}"' for n in names) + "}"
    cc = "{" + ", ".join(f'"{n}"' for n in names) + "}"
    src = {"python": PY, "go": GO, "rust": RS, "java": JV, "c": CC}[lang]
    return K.subst(src, WRAP=_b(lang, p["wrap"]), FLOOR=_b(lang, p["floor"]), STACK=p["stack"], MEM=p["mem"], CALLS=p["calls"],
                   STEPS=p["steps"], DATA=_b(lang, p["data"]), NAMES_PY=py, NAMES_GO=go, NAMES_RS=rs, NAMES_JAVA=jv, NAMES_C=cc).lstrip("\n")


# ---------------------------------------------------------------------------------------------------------------

DESC = {
    "push": ("push N", "push the integer N (decimal, optional leading `-`, 32-bit range)"),
    "pop": ("pop", "drop the top value"),
    "dup": ("dup", "push a copy of the top value"),
    "swap": ("swap", "exchange the two top values"),
    "over": ("over", "push a copy of the second value from the top (`a b` becomes `a b a`)"),
    "add": ("add", "`a b` becomes `a + b` (b is the top)"),
    "sub": ("sub", "`a b` becomes `a - b`"),
    "mul": ("mul", "`a b` becomes `a * b`"),
    "div": ("div", "`a b` becomes `a / b` (see Arithmetic)"),
    "mod": ("mod", "`a b` becomes `a mod b` (see Arithmetic)"),
    "neg": ("neg", "`a` becomes `-a`"),
    "eq": ("eq", "`a b` becomes 1 if `a == b`, else 0"),
    "lt": ("lt", "`a b` becomes 1 if `a < b`, else 0"),
    "gt": ("gt", "`a b` becomes 1 if `a > b`, else 0"),
    "not": ("not", "`a` becomes 1 if `a == 0`, else 0"),
    "jmp": ("jmp L", "continue at label L"),
    "jz": ("jz L", "pop a value; if it is 0 continue at label L, else go on"),
    "jnz": ("jnz L", "pop a value; if it is not 0 continue at label L, else go on"),
    "call": ("call L", "push the index of the next instruction on the return stack and continue at label L"),
    "ret": ("ret", "pop the return stack and continue there"),
    "load": ("load", "pop an address `a`, push `mem[a]`"),
    "store": ("store", "pop an address `a` (top), then a value `v`; set `mem[a] = v`"),
    "in": ("in", "read the next integer from the input and push it"),
    "out": ("out", "pop a value and append its decimal text and a newline to the output"),
    "outc": ("outc", "pop a value `c` (1 to 127) and append the character with that code"),
    "outs": ("outs", "pop an address `a`; append the characters `mem[a], mem[a+1], ...` up to (not including) the first cell that is 0"),
    "halt": ("halt", "stop the machine normally"),
}


def readme(p, api, lang, examples):
    names = p["names"]

    def nm(op):
        return f"`{names.get(op, op)}`"

    L = ["# Quill machine", ""]
    L.append("The *Quill* is a small stack machine used to run the kiosk firmware of an imaginary ferry company. This library contains its assembler and its "
             "interpreter in one function: `run(program, input)` assembles the program text, executes it, and returns everything the program printed.")
    L.append("")
    L.append("## Machine state")
    L.append("")
    L.append(f"* a **data stack** of at most **{p['stack']}** values;")
    L.append(f"* **memory**: {p['mem']} cells (addresses 0 to {p['mem'] - 1}), all 0 at the start;")
    if "call" in p["avail"]:
        L.append(f"* a **return stack** of at most **{p['calls']}** entries;")
    L.append("* the program counter `pc`, the index (counting from 0) of the next instruction;")
    L.append(f"* a step counter: at most **{p['steps']}** instructions may be executed (the {nm('halt')} instruction counts).")
    L.append("")
    arith = ", ".join(nm(o) for o in ("add", "sub", "mul", "neg", "div") if o in names)
    L.append("All values are **32-bit signed integers** (-2147483648 to 2147483647). " +
             (f"When a result of {arith} leaves that range it **wraps around** (two's complement)." if p["wrap"] else
              f"When a result of {arith} leaves that range the instruction fails with `overflow`."))
    L.append("")
    L.append("## Program text")
    L.append("")
    L.append("A program is text with one line per instruction (lines are separated by `\\n`; line numbers count from 1). On every line, everything from a `;` on is a comment. "
             "The rest is split into *words* at blanks (spaces, tabs); a line without words is empty and ignored. "
             "A **label** is a first word that ends with `:`, e.g. `loop:`; the part before the colon must be an *identifier* (a letter or `_`, then letters, digits or `_`; ASCII only), otherwise the line is a `bad label`. "
             "A label may stand alone on its line or be followed by an instruction on the same line (separated by a blank: `loop:" + names["push"] + " 1` is **not** a label followed by an instruction). "
             "A label names the index of the next instruction that is assembled, so a label at the end of the program names the index one past the last instruction (jumping there ends the program). "
             "Mnemonics and labels are case-sensitive.")
    L.append("")
    if p["data"]:
        L.append("**Data directive.** A line `.word N1 N2 ...` (one or more integers, same syntax as `push N`) stores the numbers in consecutive memory cells, starting at cell 0 for the first directive and continuing after "
                 "the cells filled by earlier directives. `.word` lines may only appear before the first instruction, must not carry a label, and must fit in memory; otherwise the line is `bad data`.")
        L.append("")
    L.append("## Instructions")
    L.append("")
    L.append("| mnemonic | effect |")
    L.append("|---|---|")
    for op in OPS:
        if op in names:
            sig, eff = DESC[op]
            sig = sig.replace(op, names[op], 1)
            L.append(f"| `{sig}` | {eff} |")
    L.append("")
    L.append("These are *all* the mnemonics: any other first word of an instruction is an `unknown instruction`. "
             "Instructions without an operand in the table take none; an instruction with a missing, extra or malformed operand is a `bad operand`. "
             "A label operand must be an identifier. `N` is a decimal integer: digits with an optional leading `-`, at most 10 digits, within the 32-bit range.")
    L.append("")
    L.append("## Arithmetic")
    L.append("")
    L.append(f"For two values `a b` (b on top) the binary instructions pop both and push one result; {nm('sub')} computes `a - b`, {nm('lt')} tests `a < b`, and so on." +
             (f" Division and remainder use **floored** division: {nm('div')} rounds towards minus infinity and {nm('mod')} has the sign of the divisor (-7 divided by 2 is -4 with remainder 1; 7 modulo -2 is -1)." if p["floor"] and "div" in p["avail"] else
              " Division and remainder **truncate towards zero**: the remainder has the sign of the dividend (-7 divided by 2 is -3 with remainder -1)." if "div" in p["avail"] else ""))
    if "div" in p["avail"]:
        L.append(f"Dividing by 0 fails with `div0` (both {nm('div')} and {nm('mod')}). {nm('div')} can overflow (-2147483648 divided by -1); {nm('mod')} never does (its result for that pair is 0).")
    L.append("")
    L.append("## Execution")
    L.append("")
    L.append("Assembly happens first. If the program has assembly errors the result is only `error: line N: REASON` for the error on the **lowest line number** "
             "(`bad label`, " + ("`bad data`, " if p["data"] else "") + "`duplicate label`, `unknown instruction`, `bad operand`, or `unknown label` for a jump or call whose label is never defined; "
             "on a single line the first applicable reason in the order of this sentence, label problems before instruction problems, wins; an unknown label is attributed to the line of the jump). "
             "Nothing is executed then.")
    L.append("")
    own = ["`div0`" if "div" in names else None, "`overflow`"]
    fails = []
    if "div" in names:
        fails.append("`div0`")
    fails.append("`overflow`")
    if "load" in names:
        fails.append("`bad-address` for a memory address outside the memory")
    if "call" in names:
        fails.append(f"`call-depth` for {nm('call')} when the return stack is full")
        fails.append(f"`ret-empty` for {nm('ret')} with an empty return stack")
    if "in" in names:
        fails.append(f"`input` for {nm('in')} with no more integers or with a malformed one")
    if "outc" in names:
        fails.append(f"`char` for {nm('outc')}" + (f"/{nm('outs')}" if p["data"] else "") + " with a character code outside 1 to 127")
    if p["data"]:
        fails.append(f"`bad-address` for {nm('outs')} with an address outside the memory, or when the string runs past the last cell without a 0")
    L.append("Otherwise execution starts at `pc = 0` and repeats until the machine stops. **Before each instruction** the machine checks the step limit: if the limit of executed instructions is "
             "already reached, execution fails with `steps` (so a program of exactly that many instructions that ends by itself is fine). Then the instruction runs, in this order of checks: "
             "not enough values on the stack (`stack-underflow`; an instruction needs as many values as it pops), then the instruction's own failures (" + "; ".join(fails) + "), "
             "and finally pushes: a push onto a full data stack fails with `stack-overflow` (after the pops of the same instruction, so " + nm("dup") + " on a full stack fails, " + nm("add") + " never does). "
             "Jumps" + (" and calls" if "call" in names else "") + " go to the label's index. `pc` moves to the next instruction otherwise. The machine stops normally at " + nm("halt") + " or when `pc` reaches the end of the program.")
    L.append("")
    if "in" not in names:
        L.append("**Input**: this machine has no instruction that reads input; the `input` argument is accepted and ignored.")
        L.append("")
    if "in" in names:
        L.append(f"**Input**: the `input` text is split at blanks (spaces, tabs, newlines) into words; each {nm('in')} takes the next word, which must be an integer in the same syntax as `{names['push']} N`.")
    L.append("")
    L.append("## Result")
    L.append("")
    L.append(f"The result is the program's output: every {nm('out')} appends the decimal number followed by `\\n`" + (f", every {nm('outc')} appends one character" if "outc" in names else "") + (f", {nm('outs')} appends characters one by one" if p["data"] else "") + ". "
             "If the program stops normally the result is exactly that text (possibly empty). If it fails at run time, the result is the output produced so far, then a `\\n` if that output is not empty "
             "and does not already end with one, then `error: CODE at PC` where `PC` is the index of the instruction that failed (for `steps`, the index of the instruction that was about to run).")
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    for (prog, inp), out in examples:
        L.append("Program:")
        L.append("")
        L.append(K.fence(prog))
        if inp:
            L.append(f"Input: `{inp}`")
            L.append("")
        L.append("Result:")
        L.append("")
        L.append(K.fence(out) if out else "(empty)\n")
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


# canonical programs --------------------------------------------------------------------------------------------

def _progs(p, rng):
    S, M = p["stack"], p["mem"]
    out = []

    def add(text, inp="", need=None):
        out.append((text, inp))

    add("push 2\npush 3\nadd\nout\nhalt")
    add("""push 10
loop:
dup
out
push 1
sub
dup
jz done
jmp loop
done:
halt""")
    add("push 7\npush 6\nmul\nout")
    add("; comment only\npush 5 ; five\n\n  push 4\nsub\nout\n")
    add("push 1\npush 2\nswap\nsub\nout")
    add("push 3\ndup\nmul\nout\npush 0\nout")
    add("push 5\nl1: push 1\nsub\ndup\nout\ndup\njz end\njmp l1\nend: pop\nhalt")
    add("""push 1
push 5
lt
jz no
push 111
out
halt
no:
push 222
out""")
    # sums
    add("push 0\nout\nhalt\npush 99\nout")
    add("jmp end\npush 1\nout\nend:")
    add("")
    add("   \n; nothing\n")
    add("push -5\npush 3\nadd\nout\npush -2147483648\nout\npush 2147483647\nout")
    add("push 2147483647\npush 1\nadd\nout")
    add("push -2147483648\npush 1\nsub\nout")
    add("push 65536\npush 65536\nmul\nout")
    add("push 46341\ndup\nmul\nout")
    add("push 100000\npush 100000\nmul\nout")
    # underflows / fall off
    add("add")
    add("push 1\nadd")
    add("pop")
    add("dup")
    add("push 1\nswap")
    add("out")
    add("push 1\nout\nout")
    add("jz x\nx:")
    # stack overflow
    add("\n".join(["push 1"] * S + ["out"]))
    add("\n".join(["push 1"] * (S + 1)))
    add("\n".join(["push 1"] * (S - 1) + ["dup", "add", "out"]))
    add("\n".join(["push 1"] * S + ["add", "out"]))
    add("\n".join(["push 1"] * S + ["dup"]))
    # infinite loops / steps
    add("l: jmp l")
    add("l: push 1\npop\njmp l")
    n = p["steps"]
    add("\n".join(["push 1", "pop"] * (n // 2)))
    add("\n".join(["push 1", "pop"] * (n // 2) + ["push 5"]))
    add("\n".join(["push 1", "pop"] * (n // 2 - 1) + ["push 5", "out"]))
    add("\n".join(["push 1", "pop"] * (n // 2 - 1) + ["push 5", "out", "halt"]))
    add("\n".join(["push 1", "pop"] * (n // 2 - 1) + ["push 5", "halt", "push 6"]))
    # countdown with accumulate
    add("""push 0
push 10
loop:
dup
jz done
swap
push 3
add
swap
push 1
sub
jmp loop
done:
pop
out""")
    # syntax-level assembler errors
    add("bogus")
    add("push")
    add("push 1 2")
    add("push x")
    add("push 2147483648")
    add("push -2147483649")
    add("push 2147483647\npush -2147483648\nadd\nout")
    add("push 12345678901")
    add("push 0012\nout")
    add("push -0\nout")
    add("push +5\nout")
    add("push 0x10")
    add("push 1.5")
    add("pop 1")
    add("jmp")
    add("jmp a b")
    add("jmp 1x")
    add("jmp nowhere")
    add("jz nowhere\nx:")
    add("a:\na:\npush 1")
    add("a: push 1\nb: push 2\na: push 3")
    add("1a: push 1")
    add(": push 1")
    add("a:push 1")
    add("a: : push 1")
    add("push 1\nfoo bar\nbogus\njmp zip")
    add("jmp zip\nbogus")
    add("bogus\njmp zip")
    add("a: bogus\na: push 1")
    add("x:\nx: bogus")
    add("PUSH 1\nout")
    add("push 1\n\n\nbad\n")
    add("push 1 ; fine\n  \t out ; also fine\nx:\n")
    add("end:\nx: y: push 1")
    add("push\t4\t\nout")
    names = p["names"]
    # canonical names that are NOT instruction names of this instance
    for op in OPS:
        if op in names and names[op] != op:
            add(op if op not in ("push", "jmp", "jz", "jnz", "call") else op + " x")
            break
    # label tests
    add("push 1\njmp over\npush 2\nout\nover: push 3\nout")
    add("jmp b\na: push 1\nout\nhalt\nb: jmp a")
    add("start: push 1\nout\nhalt\njmp start")
    add("x: halt")
    add("halt\nhalt")
    add("push 1\njmp e\ne:")
    add("_a1: push 4\nout\n_B2: push 5\nout")
    return out


def _progs4(p, rng):
    S, M, R = p["stack"], p["mem"], p["calls"]
    out = []

    def add(text, inp=""):
        out.append((text, inp))

    add("push 7\npush 2\ndiv\nout\npush -7\npush 2\ndiv\nout\npush 7\npush -2\ndiv\nout\npush -7\npush -2\ndiv\nout")
    add("push 7\npush 2\nmod\nout\npush -7\npush 2\nmod\nout\npush 7\npush -2\nmod\nout\npush -7\npush -2\nmod\nout")
    add("push 6\npush 3\nmod\nout\npush -6\npush 3\nmod\nout\npush 0\npush 5\ndiv\nout\npush 0\npush -5\nmod\nout")
    add("push 5\npush 0\ndiv")
    add("push 5\npush 0\nmod")
    add("push 0\npush 0\ndiv")
    add("push -2147483648\npush -1\ndiv\nout")
    add("push -2147483648\npush -1\nmod\nout")
    add("push -2147483648\nneg\nout")
    add("push 2147483647\nneg\nout")
    add("push 5\nneg\nout\npush -5\nneg\nout\npush 0\nneg\nout")
    add("push 1\npush 1\neq\nout\npush 1\npush 2\neq\nout\npush 3\npush 2\ngt\nout\npush 2\npush 3\ngt\nout\npush 2\npush 2\ngt\nout")
    add("push 0\nnot\nout\npush 5\nnot\nout\npush -1\nnot\nout")
    add("push 1\npush 2\nover\nout\nout\nout")
    add("push 1\nover")
    add("\n".join(["push 1"] * S + ["over"]))
    add("\n".join(["push 1"] * (S - 1) + ["push 2", "over"]))
    add("push 10\nloop: dup\nout\npush 1\nsub\ndup\njnz loop\npop")
    add("push 0\njnz x\npush 1\nout\nx:")
    add("push 3\njnz x\npush 1\nout\nx: push 2\nout")
    add("jnz x\nx:")
    # memory
    add("push 42\npush 5\nstore\npush 5\nload\nout")
    add("push 9\npush 0\nstore\npush 0\nload\nout\npush 1\nload\nout")
    add(f"push 1\npush {M - 1}\nstore\npush {M - 1}\nload\nout")
    add(f"push 1\npush {M}\nstore")
    add(f"push {M}\nload")
    add("push -1\nload")
    add("push 1\npush -1\nstore")
    add("load")
    add("push 1\nstore")
    add("push 5\npush 1\nstore\npush 6\npush 2\nstore\npush 1\nload\npush 2\nload\nadd\nout")
    # input
    add("in\nin\nadd\nout", "3 4")
    add("in\nout", "-12")
    add("in\nout", "")
    add("in\nout", "abc")
    add("in\nin\nout\nout", "5")
    add("in\nout", "2147483648")
    add("in\nout", "007\n")
    add("in\nout", "  \t 9  ")
    add("in\nout\nin\nout", "1\n2")
    add("in\nout\nin\nout", "1 x")
    add("push 0\nloop: in\ndup\njz end\nadd\njmp loop\nend: pop\nout", "5 6 7 0")
    add("push 0\nloop: in\ndup\njz end\nadd\njmp loop\nend: pop\nout", "5 6 7")
    # outc
    add("push 72\noutc\npush 105\noutc\npush 10\noutc")
    add("push 72\noutc\npush 105\noutc")
    add("push 128\noutc")
    add("push -1\noutc")
    add("push 65\noutc\npush 200\noutc")
    add("push 65\nout\npush 66\noutc")
    add("push 0\noutc\npush 49\noutc")
    # calls
    add("push 5\ncall sq\nout\nhalt\nsq: dup\nmul\nret")
    add("call f\npush 1\nout\nhalt\nf: push 2\nout\nret")
    add("ret")
    add("call f\nf: ret\nout")
    add("push 4\ncall fact\nout\nhalt\nfact:\ndup\njz base\ndup\npush 1\nsub\ncall fact\nmul\nret\nbase:\npop\npush 1\nret")
    add("f: call f")
    add("call f\nhalt\nf: call g\nret\ng: push 7\nout\nret")
    # depth exactly R
    lines = ["call d1", "halt"]
    for i in range(1, R):
        lines.append(f"d{i}: call d{i + 1}")
        lines.append("ret")
    lines.append(f"d{R}: push 9\nout\nret")
    add("\n".join(lines))
    lines = ["call d1", "halt"]
    for i in range(1, R + 1):
        lines.append(f"d{i}: call d{i + 1}")
        lines.append("ret")
    lines.append(f"d{R + 1}: push 9\nout\nret")
    add("\n".join(lines))
    add("push 3\ncall rec\nout\nhalt\nrec: dup\njz z\npush 1\nsub\ncall rec\npush 1\nadd\nret\nz: ret")
    # gcd
    add("in\nin\ng: dup\njz done\nswap\nover\nmod\njmp g\ndone: pop\nout", "48 18")
    add("in\nin\ng: dup\njz done\nswap\nover\nmod\njmp g\ndone: pop\nout", "-48 18")
    add("in\nin\ng: dup\njz done\nswap\nover\nmod\njmp g\ndone: pop\nout", "17 -5")
    # fib with memory
    add("push 0\npush 0\nstore\npush 1\npush 1\nstore\npush 8\nl: dup\njz e\npush 0\nload\npush 1\nload\ndup\npush 0\nstore\nadd\npush 1\nstore\npush 1\nsub\njmp l\ne: pop\npush 1\nload\nout")
    # array sum
    add("push 3\npush 0\nstore\npush 4\npush 1\nstore\npush 5\npush 2\nstore\npush 0\npush 3\ni: dup\njz e\npush 1\nsub\ndup\nrot2: pop\njmp i\ne: out")
    add("push 1\npush 2\npush 3\nout\nout\nout\nout")
    return out


def _progs5(p, rng):
    M = p["mem"]
    out = []

    def add(text, inp=""):
        out.append((text, inp))

    def words(s):
        return "\n".join(f".word {' '.join(str(ord(c)) for c in s[i:i + 8])}" for i in range(0, len(s), 8)) if s else ""

    hello = "Hello"
    add(words(hello + "\0") + "\npush 0\nouts")
    add(words(hello + "\0") + "\npush 0\nouts\npush 10\noutc")
    add(words("Hi\0ho\0") + "\npush 3\nouts\npush 0\nouts")
    add(".word 72 105 0\npush 0\nouts")
    add(".word 72 105\npush 0\nouts")
    add(".word 72 300 0\npush 0\nouts")
    add(".word 72 -1 0\npush 0\nouts")
    add(f"push 5\nouts")
    add(f"push {M}\nouts")
    add(f"push -1\nouts")
    add("outs")
    add(".word 1 2 3\n.word 4 5\npush 0\nload\nout\npush 3\nload\nout\npush 4\nload\nout\npush 5\nload\nout")
    add(".word 5\npush 0\nload\nout")
    add(".word\npush 1\nout")
    add(".word 1 x\npush 1")
    add("push 1\n.word 5")
    add("a: .word 5\npush 1")
    add("a:\n.word 5\npush 0\nload\nout")
    add(".word " + " ".join(["7"] * M) + "\npush 0\nload\nout")
    add(".word " + " ".join(["7"] * (M + 1)) + "\npush 0\nload\nout")
    add(".word " + " ".join(["7"] * M) + "\n.word 1\npush 0\nload\nout")
    add(".word " + " ".join(["7"] * (M - 1)) + "\n.word 1\npush " + str(M - 1) + "\nload\nout")
    add(".word 2147483647 -2147483648\npush 0\nload\nout\npush 1\nload\nout")
    add(".word 2147483648\nhalt")
    add(".word 5 ; comment\n  .word 6\npush 1\nload\nout")
    add("  \t.word 9\npush 0\nload\nout")
    add(".WORD 5")
    add(".word5 5")
    add("." "word 1")
    # string with outs hitting end of memory
    add(f".word {' '.join(['65'] * M)}\npush 0\nouts")
    add(f".word {' '.join(['65'] * (M - 1))} 0\npush 0\nouts")
    add(f".word {' '.join(['66'] * (M - 2))} 67 0\npush {M - 2}\nouts\npush {M - 3}\nouts")
    # copy a string to the end and print through a loop: use in as loop count
    add(".word 3 4 5\npush 0\nouts")
    add(".word 72 0\npush 0\nouts\npush 0\nouts")
    add(".word 72 0\npush 0\nload\noutc\npush 1\nload\noutc")
    add(".word 33 33 0\npush 1\nouts\nhalt")
    return out


def make_cases(rng, p, ns):
    names = p["names"]
    canon_to_inst = names
    avail = set(p["avail"])
    prog_list = _progs(p, rng)
    if p["level"] >= 4:
        prog_list += _progs4(p, rng)
    if p["level"] >= 5:
        prog_list += _progs5(p, rng)

    import re

    def translate(text):
        lines = []
        for ln in text.split("\n"):
            m = re.match(r"^(\s*(?:[A-Za-z_][A-Za-z0-9_]*:\s+)*)([a-z]+)(.*)$", ln)
            if m and m.group(2) in names:
                ln = m.group(1) + names[m.group(2)] + m.group(3)
            elif m and m.group(2) in OPS and m.group(2) in names:
                pass
            lines.append(ln)
        return "\n".join(lines)

    def uses_unavailable(text):
        for ln in text.split("\n"):
            ln = ln.split(";")[0]
            m = re.match(r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*:\s*)*([a-z]+)", ln)
            if m and m.group(1) in OPS and m.group(1) not in avail:
                return True
        return False

    cases = []
    for text, inp in prog_list:
        if uses_unavailable(text):
            continue
        cases.append((translate(text), inp))
    # unavailable canonical instructions are unknown instructions
    for op in OPS:
        if op not in avail:
            cases.append((f"push 1\n{op}" + (" x" if op in ("jmp", "jz", "jnz", "call") else ""), ""))
            break
    # random straight-line arithmetic
    binops = [o for o in ("add", "sub", "mul", "lt", "div", "mod", "eq", "gt") if o in avail]
    big = [0, 1, -1, 2, 7, -7, 100, -100, 46340, 46341, 65536, 1000000, 2147483647, -2147483648, 2147483646, -2147483647, 3, 10, -3, 12345]
    for _ in range(30 if p["level"] >= 4 else 18):
        lines = []
        depth = 0
        n = rng.randrange(4, 12)
        for _ in range(n):
            if depth < 2 or rng.random() < 0.4:
                lines.append(f"push {rng.choice(big)}")
                depth += 1
            else:
                op = rng.choice(binops)
                lines.append(names[op])
                depth -= 1
        for _ in range(depth):
            lines.append(names["out"])
        cases.append(("\n".join(lines), ""))
    # random programs with control flow: loop N times accumulating
    for _ in range(4):
        k = rng.randrange(2, 9)
        step = rng.randrange(-5, 9)
        t = f"""push 0
push {k}
top:
dup
jz fin
swap
push {step}
add
swap
push 1
sub
jmp top
fin:
pop
out"""
        cases.append((translate(t), ""))
    out, seen = [], set()
    for c in cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    # examples: first three runnable ones with non-error output
    ex = []
    for c in out:
        if not ns["run"](*c).startswith("error") and ns["run"](*c) != "" and "\n" in c[0] and len(ex) < 2 and c not in ex:
            ex.append(c)
    errs = [c for c in out if ns["run"](*c).startswith("error: line")]
    if errs:
        ex.append(errs[0])
    for c in ex:
        out.remove(c)
    out = ex + out
    return out, len(ex)


def prompt(rng, p, api, lang):
    where = api.short(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    feats = []
    if "call" in p["avail"]:
        feats.append("subroutines")
    if "load" in p["avail"]:
        feats.append("memory")
    if p["data"]:
        feats.append("a data directive")
    ft = (" It supports " + ", ".join(feats) + ".") if feats else ""
    opts = [
        f"Please write the Quill machine in {ln}: an assembler plus interpreter behind one function, `{fn}(program, input)`. README.md has the instruction table, the arithmetic rules ({'wrapping' if p['wrap'] else 'trapping'} 32-bit), the limits and every error text.{ft} Put it in {where}. {K.closer(rng)}",
        f"We're resurrecting an old ferry-kiosk firmware that ran on a stack machine. I need an emulator in {ln} - README.md describes the mnemonics (they're renamed from the usual ones, so read the table), the error precedence and how output is formed. Implement `{fn}` in {where}.{ft}",
        f"Implement `{fn}` ({ln}, {where}) according to README.md: assemble the text, run it with the given input, return the printed output or the exact error line. The hidden checks hammer the limits (stack, steps, memory) and the order in which errors are reported.",
        f"bytecode VM task, {ln}. spec in README.md (stack machine, labels, 32-bit values, error texts like `error: div0 at 7`). one function `{fn}` in {where}.{ft} {K.closer(rng)}",
    ]
    return rng.choice(opts).strip()


@family("greenfield-bytevm", category="greenfield", lang="mixed", kind="greenfield", n=12,
        summary="stack-machine assembler + interpreter: renamed mnemonics, wrap/trap 32-bit maths, step/stack/call limits, exact error order")
def gen(rng, n):
    levels = [3, 3, 4, 4, 4, 4, 5, 5, 3, 4, 5, 4]
    diffs = [3, 3, 3, 4, 4, 4, 5, 5, 2, 4, 5, 3]
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level)
        api = K.Api(mod="bytevm", fn="run", args=["program", "input"],
                    arg_docs=["the assembly text", ("the integers that the `" + p["names"]["in"] + "` instruction reads, as text") if "in" in p["names"] else "input text for programs that read integers; this machine has no such instruction, so the argument is ignored"],
                    ret_doc="the program output, or an error text", doc="stack machine assembler and interpreter")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["run"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=diffs[i % len(diffs)], slug=f"{i + 1:02d}-{lang}-{'wrap' if p['wrap'] else 'trap'}-{'floor' if p['floor'] else 'trunc'}-l{level}",
            oracle=(None if lang == "python" else ns["run"]), tags=["vm", "assembler", "interpreter"],
            notes={"level": level, "wrap": p["wrap"], "floor": p["floor"], "stack": p["stack"], "steps": p["steps"]},
        )
