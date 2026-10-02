"""Token-level mutation: the cheap, language-agnostic way to make many distinct bugs from one correct library.

``mutants(lang, source, rng)`` yields ``Mutant`` objects: the whole mutated source plus a description. Edits are
made *in place* on the original text (operator tokens, literals, a deleted statement), so the code keeps its
formatting and a reader sees a realistic one-token bug rather than a reformatted file. Whether a mutant is useful
(compiles, is caught by the hidden tests, is not caught by the visible ones) is decided by ``fx.lib``.
"""
from __future__ import annotations

import io
import keyword
import random
import re
import tokenize
from dataclasses import dataclass


@dataclass
class Mutant:
    path: str
    text: str
    op: str  # operator family, e.g. "cmp", "arith", "logic", "const", "negate", "delete", "swap"
    line: int
    before: str
    after: str

    @property
    def desc(self) -> str:
        return f"{self.op}: {self.before!r} -> {self.after!r} at line {self.line}"


# ---- Python (tokenize based, exact) -------------------------------------------------------------------------------

_PY_OPS = {
    "<": ("cmp", ["<=", ">"]),
    "<=": ("cmp", ["<", ">="]),
    ">": ("cmp", [">=", "<"]),
    ">=": ("cmp", [">", "<="]),
    "==": ("cmp", ["!="]),
    "!=": ("cmp", ["=="]),
    "+": ("arith", ["-"]),
    "-": ("arith", ["+"]),
    "*": ("arith", ["+"]),
    "//": ("arith", ["/"]),
    "%": ("arith", ["//"]),
    "+=": ("arith", ["-="]),
    "-=": ("arith", ["+="]),
    "and": ("logic", ["or"]),
    "or": ("logic", ["and"]),
}
_PY_PAIRS = {
    "min": "max", "max": "min", "lstrip": "rstrip", "rstrip": "lstrip", "startswith": "endswith", "endswith": "startswith",
    "any": "all", "all": "any", "lower": "upper", "upper": "lower", "ceil": "floor", "floor": "ceil", "insert": "append",
    "popleft": "pop", "pop": "popleft", "sorted": "reversed", "ljust": "rjust", "rjust": "ljust",
    "True": "False", "False": "True", "first": "last", "last": "first",
}


def _line_starts(src: str) -> list[int]:
    out = [0]
    for m in re.finditer("\n", src):
        out.append(m.end())
    return out


def _py_mutants(path: str, src: str) -> list[Mutant]:
    out: list[Mutant] = []
    starts = _line_starts(src)
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError):
        return out

    def off(rc):
        return starts[rc[0] - 1] + rc[1]

    for i, t in enumerate(toks):
        s, e = off(t.start), off(t.end)
        text = t.string
        prev = toks[i - 1] if i else None
        if t.type == tokenize.OP and text in _PY_OPS:
            if text == "*" and (prev is None or prev.string in ("(", ",", "**", "=", "[", "{", ":", "return", "lambda")):
                continue  # *args / unpacking
            op, alts = _PY_OPS[text]
            for a in alts:
                out.append(Mutant(path, src[:s] + a + src[e:], op, t.start[0], text, a))
        elif t.type == tokenize.NAME and text in ("and", "or"):
            op, alts = _PY_OPS[text]
            for a in alts:
                out.append(Mutant(path, src[:s] + a + src[e:], op, t.start[0], text, a))
        elif t.type == tokenize.NAME and text == "not":
            # drop `not` (turns `is not` into `is`, `not in` into `in`)
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            if nxt is not None and nxt.string == "in":
                out.append(Mutant(path, src[:s] + src[off(nxt.start):], "negate", t.start[0], "not in", "in"))
            else:
                end = off(nxt.start) if nxt is not None and nxt.start[0] == t.end[0] else e
                out.append(Mutant(path, src[:s] + src[end:], "negate", t.start[0], "not", ""))
        elif t.type == tokenize.NAME and text in _PY_PAIRS:
            a = _PY_PAIRS[text]
            out.append(Mutant(path, src[:s] + a + src[e:], "swap", t.start[0], text, a))
        elif t.type == tokenize.NUMBER and re.fullmatch(r"\d+", text):
            n = int(text)
            for a in sorted({n + 1, max(n - 1, 0) if n else 1}):
                if a != n:
                    out.append(Mutant(path, src[:s] + str(a) + src[e:], "const", t.start[0], text, str(a)))
    # negate conditions: `if cond:` -> `if not (cond):`
    lines = src.split("\n")
    for ln, line in enumerate(lines, 1):
        m = re.match(r"^(\s*)(if|elif|while)\s+(.+):\s*(#.*)?$", line)
        if m and " not (" not in line:
            cond = m.group(3)
            new = f"{m.group(1)}{m.group(2)} not ({cond}):"
            out.append(Mutant(path, "\n".join(lines[: ln - 1] + [new] + lines[ln:]), "negate", ln, line.strip(), new.strip()))
    # delete a simple statement (replace by pass)
    for ln, line in enumerate(lines, 1):
        st = line.strip()
        if re.match(r"^(break|continue|return\b.*|[\w\.\[\]'\"]+\s*(\+=|-=|=)\s*[^=].*|[\w\.]+\(.*\))$", st) and st.count("(") == st.count(")") and st.count("[") == st.count("]") and not st.endswith((",", "\\")):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(Mutant(path, "\n".join(lines[: ln - 1] + [indent + "pass"] + lines[ln:]), "delete", ln, st, "pass"))
    return out


# ---- C-like (go, js, ts, java, rust, c, cpp, php) -----------------------------------------------------------------

_C_OPS3 = ["<<=", ">>=", "...", "===", "!=="]
_C_OPS2 = ["&&", "||", "==", "!=", "<=", ">=", "+=", "-=", "*=", "/=", "%=", "<<", ">>", "++", "--", "->", "=>", ":=", "::", "??"]

_C_TOK = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<lc>//[^\n]*)
  | (?P<bc>/\*.*?\*/)
  | (?P<str>"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`)
  | (?P<chr>'(?:\\.|[^'\\\n])+'(?!\w))
  | (?P<num>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?[uUlLfF]*)
  | (?P<id>[A-Za-z_$][A-Za-z0-9_$]*)
  | (?P<op><<=|>>=|\.\.\.|===|!==|&&|\|\||==|!=|<=|>=|\+=|-=|\*=|/=|%=|<<|>>|\+\+|--|->|=>|:=|::|\?\?|[-+*/%<>=!&|^~?:;,.(){}\[\]])
  | (?P<other>.)
    """,
    re.X | re.S,
)

_C_CMP = {"<": ["<=", ">"], "<=": ["<", ">="], ">": [">=", "<"], ">=": [">", "<="], "==": ["!="], "!=": ["=="], "===": ["!=="], "!==": ["==="]}
_C_ARITH = {"+": ["-"], "-": ["+"], "*": ["+"], "/": ["*"], "%": ["/"], "+=": ["-="], "-=": ["+="], "<<": [">>"], ">>": ["<<"], "++": ["--"], "--": ["++"]}
_C_LOGIC = {"&&": ["||"], "||": ["&&"]}
_C_PAIRS = {
    "min": "max", "max": "min", "Min": "Max", "Max": "Min", "floor": "ceil", "ceil": "floor", "Floor": "Ceil", "Ceil": "Floor",
    "HasPrefix": "HasSuffix", "HasSuffix": "HasPrefix", "startsWith": "endsWith", "endsWith": "startsWith", "starts_with": "ends_with",
    "ends_with": "starts_with", "ToLower": "ToUpper", "ToUpper": "ToLower", "toLowerCase": "toUpperCase", "toUpperCase": "toLowerCase",
    "to_lowercase": "to_uppercase", "to_uppercase": "to_lowercase", "TrimLeft": "TrimRight", "TrimRight": "TrimLeft", "trimStart": "trimEnd",
    "trimEnd": "trimStart", "some": "every", "every": "some", "shift": "pop", "pop": "shift", "true": "false", "false": "true",
    "True": "False", "False": "True", "unwrap_or": "unwrap_or_default", "saturating_sub": "wrapping_sub", "checked_add": "wrapping_add",
}


def _c_tokens(src: str):
    pos = 0
    out = []
    while pos < len(src):
        m = _C_TOK.match(src, pos)
        if not m:  # unterminated something: stop tokenising
            break
        kind = m.lastgroup
        out.append((kind, m.group(), m.start(), m.end()))
        pos = m.end()
    return out


def _c_mutants(path: str, src: str, lang: str) -> list[Mutant]:
    out: list[Mutant] = []
    toks = [t for t in _c_tokens(src) if t[0] not in ("ws", "lc", "bc")]
    starts = _line_starts(src)

    def line_of(off: int) -> int:
        lo, hi = 0, len(starts)
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if starts[mid] <= off:
                lo = mid
            else:
                hi = mid
        return lo + 1

    for i, (kind, text, s, e) in enumerate(toks):
        prev = toks[i - 1] if i else None
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        ln = line_of(s)
        if kind == "op":
            table = None
            if text in _C_CMP:
                table, op = _C_CMP, "cmp"
            elif text in _C_ARITH:
                table, op = _C_ARITH, "arith"
            elif text in _C_LOGIC:
                table, op = _C_LOGIC, "logic"
            if table is not None:
                # skip generics / pointers / references / unary & star: only binary position (prev is an operand)
                if text in ("<", ">", "*", "-", "+") and prev is not None and prev[0] == "op" and prev[1] not in (")", "]", "}"):
                    if text != "-" and text != "+":
                        continue
                    continue
                if text in ("<", ">") and lang in ("rust", "java", "typescript", "cpp") and nxt is not None and nxt[0] == "id" and prev is not None and prev[0] == "id" and prev[1][:1].isupper():
                    continue  # likely generics: Vec<T>, List<String>
                for a in table[text]:
                    out.append(Mutant(path, src[:s] + a + src[e:], op, ln, text, a))
            elif text == "!" and nxt is not None and (nxt[0] == "id" or nxt[1] == "(") and (prev is None or prev[0] == "op" and prev[1] not in (")", "]", "}") or prev[1] in ("return",)):
                out.append(Mutant(path, src[:s] + src[nxt[2]:], "negate", ln, "!", ""))
        elif kind == "num" and re.fullmatch(r"\d+", text):
            n = int(text)
            for a in sorted({n + 1, max(n - 1, 0) if n else 1}):
                if a != n:
                    out.append(Mutant(path, src[:s] + str(a) + src[e:], "const", ln, text, str(a)))
        elif kind == "id" and text in _C_PAIRS and (prev is None or prev[1] not in ("fn", "func", "function", "def")):
            a = _C_PAIRS[text]
            out.append(Mutant(path, src[:s] + a + src[e:], "swap", ln, text, a))
    # `if (cond)` -> `if (!(cond))` with balanced parens
    for m in re.finditer(r"\b(if|while)\s*\(", src):
        i = m.end()
        depth, j = 1, i
        while j < len(src) and depth:
            c = src[j]
            if c in "\"'`":
                q = c
                j += 1
                while j < len(src) and src[j] != q:
                    j += 2 if src[j] == "\\" else 1
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            j += 1
        if depth == 0:
            cond = src[i : j - 1]
            if "\n" not in cond and len(cond) < 120:
                out.append(Mutant(path, src[:i] + "!(" + cond + ")" + src[j - 1 :], "negate", line_of(m.start()), f"{m.group(1)} ({cond})", f"{m.group(1)} (!({cond}))"))
    # Go / Rust style: `if cond {` without parens
    if lang in ("go", "rust"):
        for m in re.finditer(r"(?m)^(\s*)(if|} else if|for)\s+([^{\n]+?)\s*\{\s*$", src):
            cond = m.group(3)
            if m.group(2) == "for" and (";" in cond or "range" in cond or ":=" in cond):
                continue
            if m.group(2) == "if" and (":=" in cond or "let " in cond or ";" in cond):
                continue
            if "\n" in cond or len(cond) > 120:
                continue
            ln = line_of(m.start(3))
            new = f"!({cond})"
            out.append(Mutant(path, src[: m.start(3)] + new + src[m.end(3) :], "negate", ln, cond, new))
    # statement deletion
    lines = src.split("\n")
    comment = "//" if lang != "php" else "//"
    for ln, line in enumerate(lines, 1):
        st = line.strip()
        if not st or st.startswith(("//", "/*", "*", "#", "}", "{", "if", "for", "while", "else", "switch", "case", "func ", "fn ", "function", "class", "let ", "const ", "var ", "int ", "return {", "type ", "use ", "import", "package", "pub ", "struct", "impl", "enum", "match", "loop")):
            continue
        if st.endswith(("{", ",", "(", "[", "&&", "||", "+", "-", "\\", ":")):
            continue
        if st.count("(") != st.count(")") or st.count("[") != st.count("]") or st.count("{") != st.count("}"):
            continue
        if re.match(r"^(break|continue)\b;?$|^[\w\.\[\]\*]+\s*(\+=|-=|=)\s*[^=].*$|^[\w\.:]+\(.*\);?$|^return\b.*$", st):
            indent = line[: len(line) - len(line.lstrip())]
            repl = indent + (";" if lang not in ("go",) else "")
            # keep line count stable
            out.append(Mutant(path, "\n".join(lines[: ln - 1] + [repl] + lines[ln:]), "delete", ln, st, "(deleted)"))
    return out


# ---- public -------------------------------------------------------------------------------------------------------

def mutants(lang: str, path: str, src: str, rng: random.Random) -> list[Mutant]:
    """All single-edit mutants of ``src``, shuffled deterministically, de-duplicated by resulting text."""
    if lang == "python":
        ms = _py_mutants(path, src)
    elif lang in ("go", "javascript", "typescript", "java", "rust", "c", "cpp", "php"):
        ms = _c_mutants(path, src, lang)
    else:
        raise ValueError(f"no mutator for {lang}")
    seen, uniq = {src}, []
    for m in ms:
        if m.text in seen:
            continue
        seen.add(m.text)
        uniq.append(m)
    rng.shuffle(uniq)
    return uniq


def python_compiles(text: str) -> bool:
    try:
        compile(text, "<mutant>", "exec")
        return True
    except SyntaxError:
        return False
