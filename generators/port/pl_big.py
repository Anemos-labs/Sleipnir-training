"""Larger port libraries: a stack VM, a checked-arithmetic expression engine and a schedule matcher."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

# ======================================================================================================================
# mini-vm: a small stack machine with 32-bit wrapping arithmetic
# ======================================================================================================================

VM_SPEC = dd('''
    A tiny stack machine used by a lab's teaching tool. All numbers are **signed 32-bit** integers.

    **Program text.** A program is a list of lines. Each line is first stripped of leading and trailing spaces and tabs. Empty lines and
    lines starting with `#` are ignored. A line that ends with `:` defines a **label** (name `[a-z_][a-z0-9_]*`; defining a name twice
    is an error) for the index of the next instruction (a label after the last instruction is allowed and refers to "the end"). Every
    other line is an instruction: a lower-case mnemonic, and for the instructions below that take one, a single space and the operand.
    A **load error** is any other line shape (unknown mnemonic, missing or extra operand, two spaces, wrong operand), a `push`
    operand that is not `-?[0-9]+` (ASCII digits) or does not fit in 32 bits (leading zeros are fine; `-0` is 0), or a jump to a label
    that is not defined.

    **Instructions.** `push N`; `pop`; `dup`; `swap`; `over` (stack `a b` becomes `a b a`, `b` on top); `add`, `sub`, `mul`, `div`, `mod`,
    `eq`, `lt`, `gt` (pop `b`, then `a`, push `a OP b`; `add`, `sub`, `mul` wrap around modulo 2^32; `div` **truncates toward zero** and
    `mod` is the matching remainder, which takes the sign of `a` (`-7 div 2 = -3`, `-7 mod 2 = -1`); `div`/`mod` by zero is a runtime error;
    `-2147483648 div -1` is `-2147483648` and `-2147483648 mod -1` is `0`; `eq`, `lt`, `gt` push 1 or 0); `neg` (wraps: negating
    `-2147483648` gives `-2147483648`); `not` (pops `x`, pushes 1 if `x` is 0, else 0); `jmp L`; `jz L` / `jnz L` (pop `x`, jump if it is zero /
    non-zero); `call L` (push the index of the next instruction on the return stack and jump); `ret` (pop the return stack and jump
    there); `in` (push the next input value); `out` (pop and append to the output); `halt`.

    **Execution** starts at the first instruction. Running past the last instruction stops normally, like `halt`. These are runtime errors:
    popping an empty stack, a data stack that would grow beyond 256 values, a return stack beyond 64 entries, `ret` with an empty return
    stack, `in` when the input is used up, division by zero, and executing more than **10000** instructions (every executed
    instruction counts, including `halt`; the 10001st is the error).

    * `run(program, input)` is the list of output values.
    * `steps(program, input)` is the number of instructions executed until the machine stopped.
    * `count_ops(program)` is the number of instructions in the program (labels and comments do not count); only load errors apply.
    * `disasm(program)` lists the instructions, one string each, like `3: jz 7`: the index, a colon, a space, the mnemonic and, when it has one,
      a space and the operand, where a jump operand is shown as the **index** of its target (a label at the end shows the instruction
      count) and a `push` operand is shown in canonical form (`push 007` is `push 7`); only load errors apply.
''')

VM_FNS = [
    Fn("run", [("program", "list<str>"), ("input", "list<i32>")], "list<int>", err=True),
    Fn("steps", [("program", "list<str>"), ("input", "list<i32>")], "int", err=True),
    Fn("count_ops", [("program", "list<str>")], "int", err=True),
    Fn("disasm", [("program", "list<str>")], "list<str>", err=True),
]

VM_PY = dd(r'''
import re

_LABEL = re.compile(r"[a-z_][a-z0-9_]*")
_INT = re.compile(r"-?[0-9]+")
_NOARG = {"pop", "dup", "swap", "over", "add", "sub", "mul", "div", "mod", "neg", "eq", "lt", "gt", "not", "ret", "in", "out", "halt"}
_JUMPS = {"jmp", "jz", "jnz", "call"}
_MIN, _MAX = -2147483648, 2147483647


def _wrap(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v >= (1 << 31) else v


def _load(program):
    labels, ins = {}, []
    for raw in program:
        line = raw.strip(" \t")
        if not line or line.startswith("#"):
            continue
        if line.endswith(":"):
            name = line[:-1]
            if not _LABEL.fullmatch(name) or name in labels:
                raise ValueError("bad label")
            labels[name] = len(ins)
            continue
        op, sep, arg = line.partition(" ")
        if op == "push":
            if not sep or not _INT.fullmatch(arg) or not (_MIN <= int(arg) <= _MAX):
                raise ValueError("bad push")
            ins.append((op, int(arg)))
        elif op in _JUMPS:
            if not sep or not _LABEL.fullmatch(arg):
                raise ValueError("bad jump")
            ins.append((op, arg))
        elif op in _NOARG and not sep:
            ins.append((op, None))
        else:
            raise ValueError("bad instruction")
    for op, arg in ins:
        if op in _JUMPS and arg not in labels:
            raise ValueError("unknown label")
    return ins, labels


def _exec(program, inp):
    ins, labels = _load(program)
    stack, calls, out = [], [], []
    pc = steps = pos = 0

    def pop():
        if not stack:
            raise ValueError("stack underflow")
        return stack.pop()

    def push(v):
        if len(stack) >= 256:
            raise ValueError("stack overflow")
        stack.append(v)

    while pc < len(ins):
        steps += 1
        if steps > 10000:
            raise ValueError("step limit")
        op, arg = ins[pc]
        pc += 1
        if op == "push":
            push(arg)
        elif op == "pop":
            pop()
        elif op == "dup":
            a = pop()
            push(a)
            push(a)
        elif op == "swap":
            b = pop()
            a = pop()
            push(b)
            push(a)
        elif op == "over":
            b = pop()
            a = pop()
            push(a)
            push(b)
            push(a)
        elif op in ("add", "sub", "mul", "div", "mod", "eq", "lt", "gt"):
            b = pop()
            a = pop()
            if op == "add":
                push(_wrap(a + b))
            elif op == "sub":
                push(_wrap(a - b))
            elif op == "mul":
                push(_wrap(a * b))
            elif op in ("div", "mod"):
                if b == 0:
                    raise ValueError("division by zero")
                q = abs(a) // abs(b)
                if (a < 0) != (b < 0):
                    q = -q
                push(_wrap(q) if op == "div" else _wrap(a - b * q))
            elif op == "eq":
                push(1 if a == b else 0)
            elif op == "lt":
                push(1 if a < b else 0)
            else:
                push(1 if a > b else 0)
        elif op == "neg":
            push(_wrap(-pop()))
        elif op == "not":
            push(1 if pop() == 0 else 0)
        elif op == "jmp":
            pc = labels[arg]
        elif op in ("jz", "jnz"):
            x = pop()
            if (x == 0) == (op == "jz"):
                pc = labels[arg]
        elif op == "call":
            if len(calls) >= 64:
                raise ValueError("call stack overflow")
            calls.append(pc)
            pc = labels[arg]
        elif op == "ret":
            if not calls:
                raise ValueError("ret without call")
            pc = calls.pop()
        elif op == "in":
            if pos >= len(inp):
                raise ValueError("input exhausted")
            push(inp[pos])
            pos += 1
        elif op == "out":
            out.append(pop())
        elif op == "halt":
            break
    return out, steps


def run(program, input):
    return _exec(program, input)[0]


def steps(program, input):
    return _exec(program, input)[1]


def count_ops(program):
    return len(_load(program)[0])


def disasm(program):
    ins, labels = _load(program)
    out = []
    for i, (op, arg) in enumerate(ins):
        if op in _JUMPS:
            out.append("%d: %s %d" % (i, op, labels[arg]))
        elif arg is not None:
            out.append("%d: %s %d" % (i, op, arg))
        else:
            out.append("%d: %s" % (i, op))
    return out
''')

VM_GO = dd(r'''
package minivm

import (
	"errors"
	"fmt"
	"strconv"
	"strings"
)

var errVM = errors.New("minivm: error")

type instr struct {
	op     string
	arg    int32
	target int
	label  string
}

func isLabel(s string) bool {
	if s == "" {
		return false
	}
	for i := 0; i < len(s); i++ {
		c := s[i]
		lower := (c >= 'a' && c <= 'z') || c == '_'
		digit := c >= '0' && c <= '9'
		if i == 0 && !lower {
			return false
		}
		if !lower && !digit {
			return false
		}
	}
	return true
}

func isInt(s string) bool {
	if strings.HasPrefix(s, "-") {
		s = s[1:]
	}
	if s == "" {
		return false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	return true
}

var noArg = map[string]bool{"pop": true, "dup": true, "swap": true, "over": true, "add": true, "sub": true, "mul": true, "div": true,
	"mod": true, "neg": true, "eq": true, "lt": true, "gt": true, "not": true, "ret": true, "in": true, "out": true, "halt": true}
var jumps = map[string]bool{"jmp": true, "jz": true, "jnz": true, "call": true}

func load(program []string) ([]instr, error) {
	labels := map[string]int{}
	var ins []instr
	for _, raw := range program {
		line := strings.Trim(raw, " \t")
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasSuffix(line, ":") {
			name := line[:len(line)-1]
			if _, dup := labels[name]; dup || !isLabel(name) {
				return nil, errVM
			}
			labels[name] = len(ins)
			continue
		}
		op, arg, hasArg := strings.Cut(line, " ")
		switch {
		case op == "push":
			if !hasArg || !isInt(arg) {
				return nil, errVM
			}
			v, err := strconv.ParseInt(arg, 10, 32)
			if err != nil {
				return nil, errVM
			}
			ins = append(ins, instr{op: op, arg: int32(v)})
		case jumps[op]:
			if !hasArg || !isLabel(arg) {
				return nil, errVM
			}
			ins = append(ins, instr{op: op, label: arg})
		case noArg[op] && !hasArg:
			ins = append(ins, instr{op: op})
		default:
			return nil, errVM
		}
	}
	for i := range ins {
		if jumps[ins[i].op] {
			t, ok := labels[ins[i].label]
			if !ok {
				return nil, errVM
			}
			ins[i].target = t
		}
	}
	return ins, nil
}

func exec(program []string, input []int32) ([]int64, int64, error) {
	ins, err := load(program)
	if err != nil {
		return nil, 0, err
	}
	var stack []int32
	var calls []int
	out := []int64{}
	pc, steps, pos := 0, int64(0), 0
	pop := func() (int32, bool) {
		if len(stack) == 0 {
			return 0, false
		}
		v := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		return v, true
	}
	push := func(v int32) bool {
		if len(stack) >= 256 {
			return false
		}
		stack = append(stack, v)
		return true
	}
	b2i := func(b bool) int32 {
		if b {
			return 1
		}
		return 0
	}
loop:
	for pc < len(ins) {
		steps++
		if steps > 10000 {
			return nil, 0, errVM
		}
		in := ins[pc]
		pc++
		ok := true
		switch in.op {
		case "push":
			ok = push(in.arg)
		case "pop":
			_, ok = pop()
		case "dup":
			var a int32
			if a, ok = pop(); ok {
				ok = push(a) && push(a)
			}
		case "swap":
			b, ok1 := pop()
			a, ok2 := pop()
			ok = ok1 && ok2 && push(b) && push(a)
		case "over":
			b, ok1 := pop()
			a, ok2 := pop()
			ok = ok1 && ok2 && push(a) && push(b) && push(a)
		case "add", "sub", "mul", "div", "mod", "eq", "lt", "gt":
			b, ok1 := pop()
			a, ok2 := pop()
			if !ok1 || !ok2 {
				ok = false
				break
			}
			var r int32
			switch in.op {
			case "add":
				r = a + b
			case "sub":
				r = a - b
			case "mul":
				r = a * b
			case "div", "mod":
				if b == 0 {
					return nil, 0, errVM
				}
				if in.op == "div" {
					r = a / b
				} else {
					r = a % b
				}
			case "eq":
				r = b2i(a == b)
			case "lt":
				r = b2i(a < b)
			case "gt":
				r = b2i(a > b)
			}
			ok = push(r)
		case "neg":
			var a int32
			if a, ok = pop(); ok {
				ok = push(-a)
			}
		case "not":
			var a int32
			if a, ok = pop(); ok {
				ok = push(b2i(a == 0))
			}
		case "jmp":
			pc = in.target
		case "jz", "jnz":
			var a int32
			if a, ok = pop(); ok && (a == 0) == (in.op == "jz") {
				pc = in.target
			}
		case "call":
			if len(calls) >= 64 {
				ok = false
			} else {
				calls = append(calls, pc)
				pc = in.target
			}
		case "ret":
			if len(calls) == 0 {
				ok = false
			} else {
				pc = calls[len(calls)-1]
				calls = calls[:len(calls)-1]
			}
		case "in":
			if pos >= len(input) {
				ok = false
			} else {
				ok = push(input[pos])
				pos++
			}
		case "out":
			var a int32
			if a, ok = pop(); ok {
				out = append(out, int64(a))
			}
		case "halt":
			break loop
		}
		if !ok {
			return nil, 0, errVM
		}
	}
	return out, steps, nil
}

func Run(program []string, input []int32) ([]int64, error) {
	out, _, err := exec(program, input)
	return out, err
}

func Steps(program []string, input []int32) (int64, error) {
	_, n, err := exec(program, input)
	return n, err
}

func CountOps(program []string) (int64, error) {
	ins, err := load(program)
	return int64(len(ins)), err
}

func Disasm(program []string) ([]string, error) {
	ins, err := load(program)
	if err != nil {
		return nil, err
	}
	out := []string{}
	for i, in := range ins {
		switch {
		case jumps[in.op]:
			out = append(out, fmt.Sprintf("%d: %s %d", i, in.op, in.target))
		case in.op == "push":
			out = append(out, fmt.Sprintf("%d: push %d", i, in.arg))
		default:
			out = append(out, fmt.Sprintf("%d: %s", i, in.op))
		}
	}
	return out, nil
}
''')

VM_RS = dd(r'''
use std::collections::HashMap;

#[derive(Clone)]
struct Instr {
    op: String,
    arg: i32,
    target: usize,
    label: String,
}

fn is_label(s: &str) -> bool {
    let b = s.as_bytes();
    !b.is_empty()
        && b.iter().enumerate().all(|(i, &c)| {
            let lower = c.is_ascii_lowercase() || c == b'_';
            if i == 0 { lower } else { lower || c.is_ascii_digit() }
        })
}

const NO_ARG: [&str; 18] = ["pop", "dup", "swap", "over", "add", "sub", "mul", "div", "mod", "neg", "eq", "lt", "gt", "not", "ret", "in", "out", "halt"];
const JUMPS: [&str; 4] = ["jmp", "jz", "jnz", "call"];

fn load(program: &[String]) -> Result<Vec<Instr>, String> {
    let mut labels: HashMap<String, usize> = HashMap::new();
    let mut ins: Vec<Instr> = Vec::new();
    for raw in program {
        let line = raw.trim_matches(|c| c == ' ' || c == '\t');
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some(name) = line.strip_suffix(':') {
            if !is_label(name) || labels.contains_key(name) {
                return Err("bad label".to_string());
            }
            labels.insert(name.to_string(), ins.len());
            continue;
        }
        let (op, arg) = match line.split_once(' ') {
            Some((a, b)) => (a, Some(b)),
            None => (line, None),
        };
        if op == "push" {
            let a = arg.ok_or("bad push")?;
            let digits = a.strip_prefix('-').unwrap_or(a);
            if digits.is_empty() || !digits.bytes().all(|c| c.is_ascii_digit()) {
                return Err("bad push".to_string());
            }
            let v: i32 = a.parse().map_err(|_| "push out of range".to_string())?;
            ins.push(Instr { op: op.to_string(), arg: v, target: 0, label: String::new() });
        } else if JUMPS.contains(&op) {
            let a = arg.ok_or("bad jump")?;
            if !is_label(a) {
                return Err("bad jump".to_string());
            }
            ins.push(Instr { op: op.to_string(), arg: 0, target: 0, label: a.to_string() });
        } else if NO_ARG.contains(&op) && arg.is_none() {
            ins.push(Instr { op: op.to_string(), arg: 0, target: 0, label: String::new() });
        } else {
            return Err("bad instruction".to_string());
        }
    }
    for i in ins.iter_mut() {
        if JUMPS.contains(&i.op.as_str()) {
            i.target = *labels.get(&i.label).ok_or("unknown label")?;
        }
    }
    Ok(ins)
}

fn exec(program: &[String], input: &[i32]) -> Result<(Vec<i64>, i64), String> {
    let ins = load(program)?;
    let mut stack: Vec<i32> = Vec::new();
    let mut calls: Vec<usize> = Vec::new();
    let mut out: Vec<i64> = Vec::new();
    let (mut pc, mut steps, mut pos) = (0usize, 0i64, 0usize);
    fn pop(s: &mut Vec<i32>) -> Result<i32, String> {
        s.pop().ok_or_else(|| "stack underflow".to_string())
    }
    fn push(s: &mut Vec<i32>, v: i32) -> Result<(), String> {
        if s.len() >= 256 {
            return Err("stack overflow".to_string());
        }
        s.push(v);
        Ok(())
    }
    while pc < ins.len() {
        steps += 1;
        if steps > 10000 {
            return Err("step limit".to_string());
        }
        let i = &ins[pc];
        pc += 1;
        match i.op.as_str() {
            "push" => push(&mut stack, i.arg)?,
            "pop" => {
                pop(&mut stack)?;
            }
            "dup" => {
                let a = pop(&mut stack)?;
                push(&mut stack, a)?;
                push(&mut stack, a)?;
            }
            "swap" => {
                let b = pop(&mut stack)?;
                let a = pop(&mut stack)?;
                push(&mut stack, b)?;
                push(&mut stack, a)?;
            }
            "over" => {
                let b = pop(&mut stack)?;
                let a = pop(&mut stack)?;
                push(&mut stack, a)?;
                push(&mut stack, b)?;
                push(&mut stack, a)?;
            }
            "add" | "sub" | "mul" | "div" | "mod" | "eq" | "lt" | "gt" => {
                let b = pop(&mut stack)?;
                let a = pop(&mut stack)?;
                let r = match i.op.as_str() {
                    "add" => a.wrapping_add(b),
                    "sub" => a.wrapping_sub(b),
                    "mul" => a.wrapping_mul(b),
                    "div" | "mod" => {
                        if b == 0 {
                            return Err("division by zero".to_string());
                        }
                        if i.op == "div" { a.wrapping_div(b) } else { a.wrapping_rem(b) }
                    }
                    "eq" => (a == b) as i32,
                    "lt" => (a < b) as i32,
                    _ => (a > b) as i32,
                };
                push(&mut stack, r)?;
            }
            "neg" => {
                let a = pop(&mut stack)?;
                push(&mut stack, a.wrapping_neg())?;
            }
            "not" => {
                let a = pop(&mut stack)?;
                push(&mut stack, (a == 0) as i32)?;
            }
            "jmp" => pc = i.target,
            "jz" | "jnz" => {
                let a = pop(&mut stack)?;
                if (a == 0) == (i.op == "jz") {
                    pc = i.target;
                }
            }
            "call" => {
                if calls.len() >= 64 {
                    return Err("call stack overflow".to_string());
                }
                calls.push(pc);
                pc = i.target;
            }
            "ret" => pc = calls.pop().ok_or("ret without call")?,
            "in" => {
                let v = *input.get(pos).ok_or("input exhausted")?;
                pos += 1;
                push(&mut stack, v)?;
            }
            "out" => out.push(pop(&mut stack)? as i64),
            _ => break,
        }
    }
    Ok((out, steps))
}

pub fn run(program: &[String], input: &[i32]) -> Result<Vec<i64>, String> {
    exec(program, input).map(|r| r.0)
}

pub fn steps(program: &[String], input: &[i32]) -> Result<i64, String> {
    exec(program, input).map(|r| r.1)
}

pub fn count_ops(program: &[String]) -> Result<i64, String> {
    Ok(load(program)?.len() as i64)
}

pub fn disasm(program: &[String]) -> Result<Vec<String>, String> {
    let ins = load(program)?;
    Ok(ins
        .iter()
        .enumerate()
        .map(|(n, i)| {
            if JUMPS.contains(&i.op.as_str()) {
                format!("{}: {} {}", n, i.op, i.target)
            } else if i.op == "push" {
                format!("{}: push {}", n, i.arg)
            } else {
                format!("{}: {}", n, i.op)
            }
        })
        .collect())
}
''')


def vm_cases(rng):
    progs = {
        "sum_input": ["in", "in", "add", "out"],
        "echo_until_zero": ["loop:", "in", "dup", "jz end", "out", "jmp loop", "end:", "pop"],
        "square_call": ["in", "call sq", "out", "halt", "sq:", "dup", "mul", "ret"],
        "wrap": ["push 2147483647", "push 1", "add", "out", "push -2147483648", "push 1", "sub", "out", "push 65536", "push 65536", "mul", "out", "push 2147483647", "push 2", "mul", "out"],
        "divmod": ["in", "in", "over", "over", "div", "out", "mod", "out"],
        "neg": ["in", "neg", "out", "in", "not", "out", "in", "not", "out"],
        "cmp": ["in", "in", "over", "over", "eq", "out", "over", "over", "lt", "out", "gt", "out", "pop"],
        "countdown": ["in", "loop:", "dup", "out", "push -1", "add", "dup", "jnz loop", "pop"],
        "forever": ["loop:", "jmp loop"],
        "almost": ["push 4998", "loop:", "push -1", "add", "dup", "jnz loop", "pop"],
        "stack_deep": ["push 1", "loop:", "dup", "jmp loop"],
        "recurse": ["go:", "call go"],
        "fall_off": ["push 1", "push 2", "add"],
        "halt_mid": ["push 1", "out", "halt", "push 2", "out"],
        "over_swap": ["push 1", "push 2", "over", "out", "out", "out", "push 5", "push 6", "swap", "out", "out"],
        "label_end": ["push 1", "jmp end", "push 2", "out", "end:"],
        "jz_taken": ["push 0", "jz t", "push 9", "out", "t:", "push 7", "out"],
        "ws": ["  push 3\t", "", "# comment", "   # indented comment", "\tout  "],
    }
    inputs = {
        "sum_input": [[3, 4], [2147483647, 1], [-5, 5], [1], []], "echo_until_zero": [[1, 2, 3, 0], [0], [5], []], "square_call": [[7], [65536], [-3], [46341]],
        "divmod": [[7, 2], [-7, 2], [7, -2], [-7, -2], [-2147483648, -1], [5, 0], [0, 3], [2147483647, 2147483647]], "neg": [[5, 0, 3], [-2147483648, 1, 0]],
        "cmp": [[1, 2], [2, 2], [3, 2], [-1, 1]], "countdown": [[3], [0], [1], [5]], "wrap": [[]], "forever": [[]], "almost": [[]], "stack_deep": [[]], "recurse": [[]], "fall_off": [[]], "halt_mid": [[]],
        "over_swap": [[]], "label_end": [[]], "jz_taken": [[]], "ws": [[]],
    }
    out = []
    for name, p in progs.items():
        for inp in inputs.get(name, [[]]):
            out.append(("run", [p, inp]))
            out.append(("steps", [p, inp]))
        out.append(("count_ops", [p]))
        out.append(("disasm", [p]))
    gcd = ["in", "in", "loop:", "dup", "jz done", "swap", "over", "mod", "jmp loop", "done:", "pop", "out"]
    for a, b in [(12, 18), (17, 5), (100, 75), (7, 7), (0, 5), (5, 0), (-12, 18), (270, 192)]:
        out.append(("run", [gcd, [a, b]]))
        out.append(("steps", [gcd, [a, b]]))
    out.append(("count_ops", [gcd]))
    out.append(("disasm", [gcd]))
    sumto = ["in", "push 0", "swap", "loop:", "dup", "jz done", "dup", "push -1", "add", "swap", "pop", "swap", "over", "add", "swap", "jmp loop", "done:", "pop", "out"]
    out.append(("count_ops", [sumto]))
    bad_progs = [
        ["frobnicate"], ["push"], ["push x"], ["push 1 2"], ["push  1"], ["push 2147483648"], ["push -2147483649"], ["push +1"], ["push 1_0"], ["push ١"], ["push 00000000000000000007"], ["push -0"], ["add 1"], ["jmp"], ["jmp nowhere"],
        ["jz A"], ["a:", "a:"], ["A:"], ["1a:"], [":"], ["loop :"], ["call f", "f:", "ret"], ["pop"], ["add"], ["push 1", "add"], ["ret"], ["in"], ["push 1", "push 0", "div"], ["push 1", "push 0", "mod"], ["Push 1"], ["push 1 "], [" halt"], ["halt\n"],
        ["x: "], ["x:y"], ["jmp x", "x:", "x:"], ["push 5", "dup", "swap", "swap", "mul", "out"], ["dup"], ["swap"], ["push 1", "swap"], ["over"], ["push 1", "over"], ["neg"], ["not"], ["out"], ["jz x", "x:"], ["push 0", "jz x", "x:", "out"],
    ]
    for p in bad_progs:
        out.append(("run", [p, []]))
        out.append(("count_ops", [p]))
        out.append(("disasm", [p]))
    out.append(("run", [["in", "out"], []]))
    out.append(("run", [["in", "in", "out", "out"], [1]]))
    out.append(("run", [["push 1"] * 256, []]))
    out.append(("run", [["push 1"] * 257, []]))
    out.append(("run", [["push 1"] * 255 + ["dup"], []]))
    out.append(("run", [["push 1"] * 255 + ["dup", "dup"], []]))
    out.append(("run", [["push 1"] * 255 + ["push 2", "over"], []]))
    out.append(("run", [["push 1", "push 2", "over", "out", "out", "out"], []]))
    out.append(("run", [["push 1"] * 255 + ["swap"], []]))
    out.append(("run", [["push 3", "call a", "out", "halt", "a:", "dup", "jz z", "push -1", "add", "call a", "z:", "ret"], []]))
    depth = ["push 63", "call a", "halt", "a:", "dup", "jz z", "push -1", "add", "call a", "z:", "pop", "ret"]
    out.append(("run", [depth, []]))
    out.append(("steps", [depth, []]))
    depth64 = list(depth)
    depth64[0] = "push 64"
    out.append(("run", [depth64, []]))
    out.append(("run", [["push 4999", "loop:", "push -1", "add", "dup", "jnz loop", "pop"], []]))
    out.append(("steps", [["push 4999", "loop:", "push -1", "add", "dup", "jnz loop", "pop"], []]))
    out.append(("run", [["push 3333", "loop:", "push -1", "add", "dup", "jnz loop", "pop", "halt"], []]))
    out.append(("steps", [["push 3333", "loop:", "push -1", "add", "dup", "jnz loop", "pop", "halt"], []]))
    exact = ["push 2499", "loop:", "push -1", "add", "dup", "jnz loop"]  # 1 + 4*2499 + ... steps
    out.append(("steps", [exact, []]))
    ops = ["add", "sub", "mul", "div", "mod", "neg", "eq", "lt", "gt", "not", "dup", "swap", "over", "pop"]
    for _ in range(40):
        p = ["push %d" % rng.choice([0, 1, -1, 2, 3, 7, -7, 100, 2147483647, -2147483648, 65536, rng.randint(-1000, 1000)]) for _ in range(rng.randint(2, 5))]
        for _ in range(rng.randint(2, 10)):
            p.append(rng.choice(ops))
            if rng.random() < 0.5:
                p.append("out")
        out.append(("run", [p, []]))
        out.append(("steps", [p, []]))
    return out


VM = PortLib(
    slug="mini-vm",
    title="a small stack machine",
    blurb="A teaching lab runs student programs on a deliberately tiny stack machine with 32-bit integers, and the interpreter is being rewritten in another language.",
    spec=VM_SPEC,
    fns=VM_FNS,
    impls={"go": {"minivm.go": VM_GO}, "rust": {"src/lib.rs": VM_RS}, "python": {"mini_vm.py": VM_PY}},
    cases=vm_cases,
    difficulty=5,
    traps=["truncating division/remainder with INT_MIN / -1", "32-bit wrap on every arithmetic op", "exact step/stack/call limits", "strict program text", "error idioms"],
    tags=["interpreter", "i32", "state-machine"],
    pairs=[("go", "rust", "full"), ("rust", "python", "full"), ("python", "go", "stub"), ("go", "python", "stub")],
    diff_adj={"python>go": 0},
)
register_port(VM, __name__)

# ======================================================================================================================
# calc-checked: expression evaluator with checked 32-bit arithmetic
# ======================================================================================================================

CC_SPEC = dd('''
    An expression engine for a spreadsheet's formula bar, with **checked signed 32-bit arithmetic**: any operation whose exact
    result does not fit in `-2147483648..2147483647` is an error (not a wrap-around).

    **Syntax.** Tokens are decimal integer literals, the operators `+ - * / %` and the parentheses `(` `)`. Spaces and tabs may
    appear between tokens and are ignored; any other character (letters, newlines, other Unicode digits, decimal points, ...) is an
    error. A literal is one or more ASCII digits without a leading zero unless it is exactly `0`, and at most `2147483647`.
    Grammar (all binary operators are left-associative):

        expr    = term { ("+" | "-") term }
        term    = unary { ("*" | "/" | "%") unary }
        unary   = "-" unary | primary
        primary = literal | "(" expr ")"

    Parentheses may nest at most 200 deep (deeper is an error). Empty input, a missing operand, trailing tokens or unbalanced
    parentheses are errors.

    **Semantics.** `/` is **floor division** (the quotient rounds toward negative infinity: `-7 / 2` is `-4`, `7 / -2` is `-4`) and `%` is
    the matching **floor modulo** (the result has the sign of the divisor: `-7 % 2` is `1`, `7 % -2` is `-1`). A zero divisor is an error;
    `-2147483648 / -1` does not fit and is an error, while `-2147483648 % -1` is `0`. Unary minus errors only on `-2147483648`.
    A literal `2147483648` is never valid, so `-2147483648` must be written as e.g. `-2147483647 - 1`.

    * `eval_expr(text)` is the value.
    * `tokens(text)` is the list of token strings in order (literals as written, operators and parentheses); lexical errors only.
    * `depth(text)` is the deepest parenthesis nesting of a syntactically valid expression (0 without parentheses); syntax errors apply,
      overflow and division by zero do not (nothing is evaluated).
    * `rpn(text)` is the expression in reverse Polish order as a list of tokens, with unary minus written as `neg`: `3 + -4 * 2` gives
      `["3", "4", "neg", "2", "*", "+"]`; the same errors as `depth`.
''')

CC_FNS = [
    Fn("eval_expr", [("text", "str")], "int", err=True),
    Fn("tokens", [("text", "str")], "list<str>", err=True),
    Fn("depth", [("text", "str")], "int", err=True),
    Fn("rpn", [("text", "str")], "list<str>", err=True),
]

CC_PY = dd(r'''
MAXV = 2147483647
MINV = -2147483648


def tokens(text):
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t":
            i += 1
        elif c in "+-*/%()":
            out.append(c)
            i += 1
        elif "0" <= c <= "9":
            j = i
            while j < n and "0" <= text[j] <= "9":
                j += 1
            lit = text[i:j]
            if (len(lit) > 1 and lit[0] == "0") or int(lit) > MAXV:
                raise ValueError("bad literal")
            out.append(lit)
            i = j
        else:
            raise ValueError("bad character")
    return out


class _Parser:
    def __init__(self, toks):
        self.t, self.i, self.rpn, self.depth, self.maxdepth = toks, 0, [], 0, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def expr(self):
        self.term()
        while self.peek() in ("+", "-"):
            op = self.t[self.i]
            self.i += 1
            self.term()
            self.rpn.append(op)

    def term(self):
        self.unary()
        while self.peek() in ("*", "/", "%"):
            op = self.t[self.i]
            self.i += 1
            self.unary()
            self.rpn.append(op)

    def unary(self):
        if self.peek() == "-":
            self.i += 1
            self.unary()
            self.rpn.append("neg")
        else:
            self.primary()

    def primary(self):
        p = self.peek()
        if p is None:
            raise ValueError("missing operand")
        if p == "(":
            self.i += 1
            self.depth += 1
            if self.depth > 200:
                raise ValueError("nesting too deep")
            self.maxdepth = max(self.maxdepth, self.depth)
            self.expr()
            if self.peek() != ")":
                raise ValueError("missing )")
            self.i += 1
            self.depth -= 1
        elif p[0].isdigit() and p.isascii():
            self.rpn.append(p)
            self.i += 1
        else:
            raise ValueError("unexpected token")


def _parse(text):
    p = _Parser(tokens(text))
    p.expr()
    if p.peek() is not None:
        raise ValueError("trailing tokens")
    return p


def _fit(v):
    if v < MINV or v > MAXV:
        raise OverflowError("overflow")
    return v


def eval_expr(text):
    st = []
    for tok in _parse(text).rpn:
        if tok == "neg":
            st.append(_fit(-st.pop()))
        elif tok in "+-*/%" and len(tok) == 1:
            b, a = st.pop(), st.pop()
            if tok == "+":
                st.append(_fit(a + b))
            elif tok == "-":
                st.append(_fit(a - b))
            elif tok == "*":
                st.append(_fit(a * b))
            else:
                if b == 0:
                    raise ZeroDivisionError("division by zero")
                st.append(_fit(a // b) if tok == "/" else a % b)
        else:
            st.append(int(tok))
    return st[0]


def depth(text):
    return _parse(text).maxdepth


def rpn(text):
    return _parse(text).rpn
''')

CC_RS = dd(r'''
const MAXV: i64 = 2147483647;
const MINV: i64 = -2147483648;

pub fn tokens(text: &str) -> Result<Vec<String>, String> {
    let c: Vec<char> = text.chars().collect();
    let mut out = Vec::new();
    let mut i = 0;
    while i < c.len() {
        let ch = c[i];
        if ch == ' ' || ch == '\t' {
            i += 1;
        } else if "+-*/%()".contains(ch) {
            out.push(ch.to_string());
            i += 1;
        } else if ch.is_ascii_digit() {
            let mut j = i;
            while j < c.len() && c[j].is_ascii_digit() {
                j += 1;
            }
            let lit: String = c[i..j].iter().collect();
            if (lit.len() > 1 && lit.starts_with('0')) || lit.len() > 10 || lit.parse::<i64>().unwrap() > MAXV {
                return Err("bad literal".to_string());
            }
            out.push(lit);
            i = j;
        } else {
            return Err("bad character".to_string());
        }
    }
    Ok(out)
}

struct Parser {
    t: Vec<String>,
    i: usize,
    rpn: Vec<String>,
    depth: i64,
    maxdepth: i64,
}

impl Parser {
    fn peek(&self) -> Option<&str> {
        self.t.get(self.i).map(|s| s.as_str())
    }
    fn expr(&mut self) -> Result<(), String> {
        self.term()?;
        while matches!(self.peek(), Some("+") | Some("-")) {
            let op = self.t[self.i].clone();
            self.i += 1;
            self.term()?;
            self.rpn.push(op);
        }
        Ok(())
    }
    fn term(&mut self) -> Result<(), String> {
        self.unary()?;
        while matches!(self.peek(), Some("*") | Some("/") | Some("%")) {
            let op = self.t[self.i].clone();
            self.i += 1;
            self.unary()?;
            self.rpn.push(op);
        }
        Ok(())
    }
    fn unary(&mut self) -> Result<(), String> {
        if self.peek() == Some("-") {
            self.i += 1;
            self.unary()?;
            self.rpn.push("neg".to_string());
            Ok(())
        } else {
            self.primary()
        }
    }
    fn primary(&mut self) -> Result<(), String> {
        let p = self.peek().ok_or("missing operand")?.to_string();
        if p == "(" {
            self.i += 1;
            self.depth += 1;
            if self.depth > 200 {
                return Err("nesting too deep".to_string());
            }
            self.maxdepth = self.maxdepth.max(self.depth);
            self.expr()?;
            if self.peek() != Some(")") {
                return Err("missing )".to_string());
            }
            self.i += 1;
            self.depth -= 1;
            Ok(())
        } else if p.as_bytes()[0].is_ascii_digit() {
            self.rpn.push(p);
            self.i += 1;
            Ok(())
        } else {
            Err("unexpected token".to_string())
        }
    }
}

fn parse(text: &str) -> Result<Parser, String> {
    let mut p = Parser { t: tokens(text)?, i: 0, rpn: Vec::new(), depth: 0, maxdepth: 0 };
    p.expr()?;
    if p.peek().is_some() {
        return Err("trailing tokens".to_string());
    }
    Ok(p)
}

fn fit(v: i64) -> Result<i64, String> {
    if v < MINV || v > MAXV {
        Err("overflow".to_string())
    } else {
        Ok(v)
    }
}

fn floor_div(a: i64, b: i64) -> i64 {
    let q = a / b;
    if (a % b != 0) && ((a < 0) != (b < 0)) { q - 1 } else { q }
}

fn floor_mod(a: i64, b: i64) -> i64 {
    a - b * floor_div(a, b)
}

pub fn eval_expr(text: &str) -> Result<i64, String> {
    let mut st: Vec<i64> = Vec::new();
    for tok in parse(text)?.rpn {
        match tok.as_str() {
            "neg" => {
                let a = st.pop().unwrap();
                st.push(fit(-a)?);
            }
            "+" | "-" | "*" | "/" | "%" => {
                let b = st.pop().unwrap();
                let a = st.pop().unwrap();
                st.push(match tok.as_str() {
                    "+" => fit(a + b)?,
                    "-" => fit(a - b)?,
                    "*" => fit(a * b)?,
                    "/" => {
                        if b == 0 {
                            return Err("division by zero".to_string());
                        }
                        fit(floor_div(a, b))?
                    }
                    _ => {
                        if b == 0 {
                            return Err("division by zero".to_string());
                        }
                        floor_mod(a, b)
                    }
                });
            }
            lit => st.push(lit.parse().unwrap()),
        }
    }
    Ok(st[0])
}

pub fn depth(text: &str) -> Result<i64, String> {
    Ok(parse(text)?.maxdepth)
}

pub fn rpn(text: &str) -> Result<Vec<String>, String> {
    Ok(parse(text)?.rpn)
}
''')

CC_JAVA = dd(r'''
import java.util.*;

public final class CalcChecked {
    private CalcChecked() {}

    private static final long MAXV = 2147483647L;
    private static final long MINV = -2147483648L;

    public static List<String> tokens(String text) {
        List<String> out = new ArrayList<>();
        int i = 0, n = text.length();
        while (i < n) {
            char c = text.charAt(i);
            if (c == ' ' || c == '\t') {
                i++;
            } else if ("+-*/%()".indexOf(c) >= 0) {
                out.add(String.valueOf(c));
                i++;
            } else if (c >= '0' && c <= '9') {
                int j = i;
                while (j < n && text.charAt(j) >= '0' && text.charAt(j) <= '9') j++;
                String lit = text.substring(i, j);
                if ((lit.length() > 1 && lit.charAt(0) == '0') || lit.length() > 10 || Long.parseLong(lit) > MAXV) throw new IllegalArgumentException("bad literal");
                out.add(lit);
                i = j;
            } else {
                throw new IllegalArgumentException("bad character");
            }
        }
        return out;
    }

    private static final class Parser {
        final List<String> t;
        int i = 0, depth = 0, maxdepth = 0;
        final List<String> rpn = new ArrayList<>();

        Parser(List<String> t) { this.t = t; }

        String peek() { return i < t.size() ? t.get(i) : null; }

        void expr() {
            term();
            while ("+".equals(peek()) || "-".equals(peek())) {
                String op = t.get(i++);
                term();
                rpn.add(op);
            }
        }

        void term() {
            unary();
            while ("*".equals(peek()) || "/".equals(peek()) || "%".equals(peek())) {
                String op = t.get(i++);
                unary();
                rpn.add(op);
            }
        }

        void unary() {
            if ("-".equals(peek())) {
                i++;
                unary();
                rpn.add("neg");
            } else {
                primary();
            }
        }

        void primary() {
            String p = peek();
            if (p == null) throw new IllegalArgumentException("missing operand");
            if (p.equals("(")) {
                i++;
                if (++depth > 200) throw new IllegalArgumentException("nesting too deep");
                maxdepth = Math.max(maxdepth, depth);
                expr();
                if (!")".equals(peek())) throw new IllegalArgumentException("missing )");
                i++;
                depth--;
            } else if (p.charAt(0) >= '0' && p.charAt(0) <= '9') {
                rpn.add(p);
                i++;
            } else {
                throw new IllegalArgumentException("unexpected token");
            }
        }
    }

    private static Parser parse(String text) {
        Parser p = new Parser(tokens(text));
        p.expr();
        if (p.peek() != null) throw new IllegalArgumentException("trailing tokens");
        return p;
    }

    private static long fit(long v) {
        if (v < MINV || v > MAXV) throw new ArithmeticException("overflow");
        return v;
    }

    public static long evalExpr(String text) {
        Deque<Long> st = new ArrayDeque<>();
        for (String tok : parse(text).rpn) {
            switch (tok) {
                case "neg": st.push(fit(-st.pop())); break;
                case "+": case "-": case "*": case "/": case "%": {
                    long b = st.pop(), a = st.pop();
                    long r;
                    if (tok.equals("+")) r = fit(a + b);
                    else if (tok.equals("-")) r = fit(a - b);
                    else if (tok.equals("*")) r = fit(a * b);
                    else {
                        if (b == 0) throw new ArithmeticException("division by zero");
                        r = tok.equals("/") ? fit(Math.floorDiv(a, b)) : Math.floorMod(a, b);
                    }
                    st.push(r);
                    break;
                }
                default: st.push(Long.parseLong(tok));
            }
        }
        return st.pop();
    }

    public static long depth(String text) { return parse(text).maxdepth; }

    public static List<String> rpn(String text) { return parse(text).rpn; }
}
''')


def cc_cases(rng):
    good = [
        "1", "0", "2147483647", "1 + 2", "1+2*3", "(1+2)*3", " 7 ", "\t7\t", "-5", "--5", "---5", "-(-5)", "2*-3", "2 - -3", "10 / 3", "-10 / 3", "10 / -3", "-10 / -3", "10 % 3", "-10 % 3", "10 % -3", "-10 % -3", "7 / 2", "-7 / 2", "7 / -2", "-7 / -2",
        "-7 % 2", "7 % -2", "6 / 3", "-6 / 3", "6 % 3", "-6 % 3", "0 / 5", "0 % 5", "0 / -5", "2147483647 + 0", "2147483647 - 2147483647", "-2147483647 - 1", "(-2147483647 - 1) % -1", "(0 - 2147483647 - 1) / 1", "46340 * 46340", "-46340 * 46340", "2147483647 * 1",
        "2147483647 * -1", "1 - 2 - 3", "100 / 10 / 5", "100 / 10 * 5", "2 * 3 % 4", "100 % 7 % 4", "((((1))))", "((1 + 2) * (3 + 4))", "1 + (2 + (3 + (4 + 5)))", "-(1 + 2) * 3", "-2 * -3", "2147483647 % 2147483647", "-2147483647 % 2147483647",
        "1000000 * 2147", "46341 * 46340", "5 - 10", "-3 * -3 * -3", "(2147483647 - 1) + 1", "7 / 7 / 7", "9 % 10", "-9 % 10", "9 % -10",
    ]
    bad = [
        "", " ", "+", "1 +", "+ 1", "1 + + 1", "1 2", "(1", "1)", "()", "(1 + )", "1 + (2", "((1)", "(1))", "1.5", "1e3", "a", "1 + a", "0x10", "007", "00", "01", "2147483648", "99999999999", "-2147483648", "1 +\n2", "1\n", "1\r", "١", "１", "1 2",
        "1 / 0", "1 % 0", "0 / 0", "5 / (3 - 3)", "-2147483647 - 2", "2147483647 + 1", "2147483647 * 2", "-2147483647 * 2", "46341 * 46341", "(-2147483647 - 1) / -1", "-(-2147483647 - 1)", "-(0 - 2147483647 - 1)", "(0 - 2147483647 - 1) * -1", "1 +* 2", "* 1", "1 */ 2",
        "1 ** 2", "1 // 2", "- ", "-", "(-)", "1 - ", "((", "))", "1 (2)", "(1) 2", "(1)(2)", "1;2", "1,2", "1_000",
    ]
    out = []
    for s in good + bad:
        out.append(("eval_expr", [s]))
        out.append(("tokens", [s]))
        out.append(("depth", [s]))
        out.append(("rpn", [s]))
    deep200 = "(" * 200 + "1" + ")" * 200
    deep201 = "(" * 201 + "1" + ")" * 201
    for s in [deep200, deep201, "(" * 200 + "1", "1" + ")" * 3, "(" * 100 + "1+2" + ")" * 100 + "*" + "(" * 150 + "3" + ")" * 150]:
        out.append(("eval_expr", [s]))
        out.append(("depth", [s]))
    for s in ["3 + -4 * 2", "-(2 + 3) * 4 - 5 / 2", "1 - (2 - 3)", "2 * (3 + 4) % 5", "- - 4", "-2147483647 - 1 + 0", "1 + 2 * 3 - 4 / 5 % 6"]:
        out.append(("rpn", [s]))
        out.append(("eval_expr", [s]))
    atoms = ["1", "2", "3", "7", "10", "100", "46340", "2147483647", "0"]
    ops = ["+", "-", "*", "/", "%"]
    for _ in range(40):
        parts = [rng.choice(atoms)]
        for _ in range(rng.randint(1, 5)):
            parts.append(rng.choice(ops))
            parts.append(rng.choice(["-", ""]) + rng.choice(atoms))
        s = " ".join(parts)
        if rng.random() < 0.4:
            s = "(" + s + ") " + rng.choice(ops) + " " + rng.choice(atoms)
        out.append(("eval_expr", [s]))
        out.append(("rpn", [s]))
    return out


CC = PortLib(
    slug="calc-checked",
    title="a checked 32-bit formula evaluator",
    blurb="A spreadsheet formula bar evaluates integer expressions with overflow detection instead of silent wrap-around, and the engine is being ported to a new platform.",
    spec=CC_SPEC,
    fns=CC_FNS,
    impls={"python": {"calc_checked.py": CC_PY}, "rust": {"src/lib.rs": CC_RS}, "java": {"CalcChecked.java": CC_JAVA}},
    cases=cc_cases,
    difficulty=4,
    traps=["floor division and floor modulo (Rust's euclid remainder differs for negative divisors)", "checked 32-bit arithmetic", "strict lexing", "recursion depth limit"],
    tags=["parser", "checked-arithmetic", "floor-div"],
    pairs=[("python", "rust", "full"), ("rust", "java", "full"), ("java", "python", "stub"), ("python", "java", "stub")],
)
register_port(CC, __name__)

# ======================================================================================================================
# cron-lite: a three-field schedule matcher on a 30-day-month calendar
# ======================================================================================================================

CR_SPEC = dd('''
    A scheduler for a game server whose calendar has **30-day months**. Time `t` is a whole number of minutes (`t >= 0`); minute-of-hour is
    `t mod 60`, hour is `(t div 60) mod 24` and day-of-month is `((t div 1440) mod 30) + 1` (so `t = 0` is minute 0, hour 0, day 1).

    A **spec** is three fields separated by exactly one space: `MINUTE HOUR DAY` with allowed values `0-59`, `0-23` and `1-30`. A field is a
    comma-separated list (no empty item) of items; an item is one of

    * `*` (every allowed value), `N` (that value), `A-B` (every value from `A` to `B` inclusive, `A <= B`),
    * `*/S`, `A-B/S`, `N/S` (every `S`-th value starting at the first one: `N/S` means `N-max/S` with `max` the field's largest value),

    where numbers are 1 or 2 ASCII digits only (no sign), every value must lie inside the field's range, and a step `S` must be at least 1. Anything
    else (extra spaces, wrong field count, `5-`, `*/0`, `a`, ...) is an error.

    * `expand(spec)` returns three sorted lists without duplicates: the minute, hour and day values the spec allows.
    * `matches(spec, t)`: does time `t` match all three fields? `t < 0` is an error.
    * `next_after(spec, t)`: the smallest matching time strictly after `t` (`t >= 0` else error). One always exists.
    * `count_between(spec, start, end)`: the number of matching times `x` with `start <= x < end`; `0 <= start <= end` or error.
''')

CR_FNS = [
    Fn("expand", [("spec", "str")], "list<list<int>>", err=True),
    Fn("matches", [("spec", "str"), ("t", "int")], "bool", err=True),
    Fn("next_after", [("spec", "str"), ("t", "int")], "int", err=True),
    Fn("count_between", [("spec", "str"), ("start", "int"), ("end_", "int")], "int", err=True),
]

CR_PY = dd(r'''
import re

_RANGES = [(0, 59), (0, 23), (1, 30)]
_NUM = re.compile(r"[0-9]{1,2}")


def _val(s, lo, hi):
    if not _NUM.fullmatch(s):
        raise ValueError("bad number")
    v = int(s)
    if v < lo or v > hi:
        raise ValueError("value out of range")
    return v


def _field(text, lo, hi):
    values = set()
    for item in text.split(","):
        if item == "":
            raise ValueError("empty item")
        base, slash, step_text = item.partition("/")
        step = 1
        if slash:
            step = _val(step_text, 0, 99)
            if step < 1:
                raise ValueError("bad step")
        if base == "*":
            a, b = lo, hi
        elif "-" in base:
            x, _, y = base.partition("-")
            a, b = _val(x, lo, hi), _val(y, lo, hi)
            if a > b:
                raise ValueError("reversed range")
        else:
            a = _val(base, lo, hi)
            b = hi if slash else a
        values.update(range(a, b + 1, step))
    return sorted(values)


def expand(spec):
    parts = spec.split(" ")
    if len(parts) != 3:
        raise ValueError("need three fields")
    return [_field(p, lo, hi) for p, (lo, hi) in zip(parts, _RANGES)]


def _match(sets, t):
    return t % 60 in sets[0] and (t // 60) % 24 in sets[1] and (t // 1440) % 30 + 1 in sets[2]


def matches(spec, t):
    sets = [set(s) for s in expand(spec)]
    if t < 0:
        raise ValueError("negative time")
    return _match(sets, t)


def next_after(spec, t):
    sets = [set(s) for s in expand(spec)]
    if t < 0:
        raise ValueError("negative time")
    x = t + 1
    while not _match(sets, x):
        x += 1
    return x


def count_between(spec, start, end_):
    sets = [set(s) for s in expand(spec)]
    if start < 0 or end_ < start:
        raise ValueError("bad range")
    return sum(1 for x in range(start, end_) if _match(sets, x))
''')

CR_GO = dd(r'''
package cronlite

import (
	"errors"
	"sort"
	"strings"
)

var errBad = errors.New("cronlite: bad input")

var ranges = [3][2]int64{{0, 59}, {0, 23}, {1, 30}}

func val(s string, lo, hi int64) (int64, error) {
	if len(s) < 1 || len(s) > 2 {
		return 0, errBad
	}
	var v int64
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return 0, errBad
		}
		v = v*10 + int64(s[i]-'0')
	}
	if v < lo || v > hi {
		return 0, errBad
	}
	return v, nil
}

func field(text string, lo, hi int64) ([]int64, error) {
	set := map[int64]bool{}
	for _, item := range strings.Split(text, ",") {
		if item == "" {
			return nil, errBad
		}
		base, stepText, slash := strings.Cut(item, "/")
		step := int64(1)
		if slash {
			s, err := val(stepText, 0, 99)
			if err != nil || s < 1 {
				return nil, errBad
			}
			step = s
		}
		var a, b int64
		switch {
		case base == "*":
			a, b = lo, hi
		case strings.Contains(base, "-"):
			x, y, _ := strings.Cut(base, "-")
			var err error
			if a, err = val(x, lo, hi); err != nil {
				return nil, err
			}
			if b, err = val(y, lo, hi); err != nil {
				return nil, err
			}
			if a > b {
				return nil, errBad
			}
		default:
			var err error
			if a, err = val(base, lo, hi); err != nil {
				return nil, err
			}
			b = a
			if slash {
				b = hi
			}
		}
		for v := a; v <= b; v += step {
			set[v] = true
		}
	}
	out := make([]int64, 0, len(set))
	for v := range set {
		out = append(out, v)
	}
	sort.Slice(out, func(i, j int) bool { return out[i] < out[j] })
	return out, nil
}

func Expand(spec string) ([][]int64, error) {
	parts := strings.Split(spec, " ")
	if len(parts) != 3 {
		return nil, errBad
	}
	out := make([][]int64, 3)
	for i, p := range parts {
		f, err := field(p, ranges[i][0], ranges[i][1])
		if err != nil {
			return nil, err
		}
		out[i] = f
	}
	return out, nil
}

func sets(spec string) ([3]map[int64]bool, error) {
	var out [3]map[int64]bool
	lists, err := Expand(spec)
	if err != nil {
		return out, err
	}
	for i, l := range lists {
		out[i] = map[int64]bool{}
		for _, v := range l {
			out[i][v] = true
		}
	}
	return out, nil
}

func match(s [3]map[int64]bool, t int64) bool {
	return s[0][t%60] && s[1][(t/60)%24] && s[2][(t/1440)%30+1]
}

func Matches(spec string, t int64) (bool, error) {
	s, err := sets(spec)
	if err != nil {
		return false, err
	}
	if t < 0 {
		return false, errBad
	}
	return match(s, t), nil
}

func NextAfter(spec string, t int64) (int64, error) {
	s, err := sets(spec)
	if err != nil {
		return 0, err
	}
	if t < 0 {
		return 0, errBad
	}
	x := t + 1
	for !match(s, x) {
		x++
	}
	return x, nil
}

func CountBetween(spec string, start, end int64) (int64, error) {
	s, err := sets(spec)
	if err != nil {
		return 0, err
	}
	if start < 0 || end < start {
		return 0, errBad
	}
	var n int64
	for x := start; x < end; x++ {
		if match(s, x) {
			n++
		}
	}
	return n, nil
}
''')

CR_TS = dd(r'''
const RANGES: number[][] = [[0, 59], [0, 23], [1, 30]];

function val(s: string, lo: number, hi: number): number {
  if (!/^[0-9]{1,2}$/.test(s)) throw new Error('bad number');
  const v = Number(s);
  if (v < lo || v > hi) throw new Error('value out of range');
  return v;
}

function field(text: string, lo: number, hi: number): number[] {
  const values = new Set<number>();
  for (const item of text.split(',')) {
    if (item === '') throw new Error('empty item');
    const slash = item.indexOf('/');
    const base = slash >= 0 ? item.slice(0, slash) : item;
    let step = 1;
    if (slash >= 0) {
      step = val(item.slice(slash + 1), 0, 99);
      if (step < 1) throw new Error('bad step');
    }
    let a: number;
    let b: number;
    if (base === '*') {
      a = lo;
      b = hi;
    } else if (base.includes('-')) {
      const dash = base.indexOf('-');
      a = val(base.slice(0, dash), lo, hi);
      b = val(base.slice(dash + 1), lo, hi);
      if (a > b) throw new Error('reversed range');
    } else {
      a = val(base, lo, hi);
      b = slash >= 0 ? hi : a;
    }
    for (let v = a; v <= b; v += step) values.add(v);
  }
  return [...values].sort((x, y) => x - y);
}

export function expand(spec: string): number[][] {
  const parts = spec.split(' ');
  if (parts.length !== 3) throw new Error('need three fields');
  return parts.map((p, i) => field(p, RANGES[i][0], RANGES[i][1]));
}

function sets(spec: string): Set<number>[] {
  return expand(spec).map((l) => new Set(l));
}

function match(s: Set<number>[], t: number): boolean {
  return s[0].has(t % 60) && s[1].has(Math.floor(t / 60) % 24) && s[2].has((Math.floor(t / 1440) % 30) + 1);
}

export function matches(spec: string, t: number): boolean {
  const s = sets(spec);
  if (t < 0) throw new Error('negative time');
  return match(s, t);
}

export function nextAfter(spec: string, t: number): number {
  const s = sets(spec);
  if (t < 0) throw new Error('negative time');
  let x = t + 1;
  while (!match(s, x)) x++;
  return x;
}

export function countBetween(spec: string, start: number, end: number): number {
  const s = sets(spec);
  if (start < 0 || end < start) throw new Error('bad range');
  let n = 0;
  for (let x = start; x < end; x++) if (match(s, x)) n++;
  return n;
}
''')


def cr_cases(rng):
    specs = ["* * *", "0 0 1", "30 12 15", "*/15 * *", "0 */6 *", "0 0 */10", "5,35 8-17 *", "0 0 1,15", "59 23 30", "*/45 * *", "10-20/5 * *", "5/20 * *", "0 22/2 *", "0 0 5/10", "1,1,1 * *", "0-59/30 0 *", "15 3 29-30", "7 7 7", "*/7 */5 */9",
             "0,30 9-17 1-5", "3-3 3-3 3-3", "59/1 23/1 30/1", "0 0 1-30/29"]
    bad = ["", " ", "*", "* *", "* * * *", "*  * *", " * * *", "* * * ", "60 * *", "* 24 *", "* * 0", "* * 31", "-1 * *", "+1 * *", "1.5 * *", "a * *", "* * *\n", "*/0 * *", "*/ * *", "/5 * *", "5- * *", "-5 * *", "5-3 * *", "1,,2 * *", ",1 * *", "1, * *", "1-2-3 * *",
           "1/2/3 * *", "*/*", "** * *", "1 - 2 * *", "0*5 * *", "100 * *", "001 * *", "1٠ * *", "１ * *", "*/100 * *", "*/99 * *", "5/0 * *", "5-10/0 * *", "* * 1-31", "* 0-24 *", "0-60 * *", "*/-1 * *", "1/ * *", "1,2/3,4-5/2 * *", "\t* * *", "*\t* *"]
    out = []
    for s in specs + bad:
        out.append(("expand", [s]))
    for s in specs:
        for t in [0, 1, 59, 60, 1439, 1440, 1441, 43199, 43200, 43201, 86400, 100000, 123456, 2000000, 99999999]:
            if rng.random() < 0.35:
                out.append(("matches", [s, t]))
        for t in [0, 1, 59, 1439, 43199, 43200, 100000, 5000000]:
            out.append(("next_after", [s, t]))
        out.append(("count_between", [s, 0, 43200]))
        out.append(("count_between", [s, 1000, 1000]))
        out.append(("count_between", [s, 4000, 90000]))
    for s in bad[:20]:
        out.append(("matches", [s, 0]))
        out.append(("next_after", [s, 0]))
        out.append(("count_between", [s, 0, 10]))
    for s in ["* * *", "5 5 5"]:
        out.append(("matches", [s, -1]))
        out.append(("next_after", [s, -1]))
        out.append(("count_between", [s, -1, 5]))
        out.append(("count_between", [s, 10, 9]))
        out.append(("count_between", [s, 10, 10]))
        out.append(("count_between", [s, 0, 1]))
    for _ in range(25):
        s = "%s %s %s" % (rng.choice(["*", "*/20", "0", "15", "5,10", "1-3", "*/7", "30/10"]), rng.choice(["*", "*/5", "0", "12", "3,4", "8-10", "20/2"]), rng.choice(["*", "*/10", "1", "15", "3,30", "1-5", "28/1"]))
        t = rng.randint(0, 10 ** rng.randint(3, 7))
        out.append(("next_after", [s, t]))
        out.append(("matches", [s, t]))
        out.append(("count_between", [s, t, t + rng.randint(0, 50000)]))
    return out


CR = PortLib(
    slug="cron-lite",
    title="a three-field schedule matcher",
    blurb="A game server schedules recurring events with a cron-like three-field syntax over its own 30-day-month calendar.",
    spec=CR_SPEC,
    fns=CR_FNS,
    impls={"python": {"cron_lite.py": CR_PY}, "go": {"cronlite.go": CR_GO}, "typescript": {"src/cron_lite.ts": CR_TS}},
    cases=cr_cases,
    difficulty=4,
    traps=["strict grammar (ASCII digits, steps from a start value)", "floor division for time decomposition in languages without it", "error idioms", "sets and sorted output"],
    tags=["scheduling", "strict-parsing", "calendar"],
    pairs=[("python", "go", "full"), ("go", "typescript", "full"), ("typescript", "python", "stub"), ("python", "typescript", "stub")],
)
register_port(CR, __name__)
