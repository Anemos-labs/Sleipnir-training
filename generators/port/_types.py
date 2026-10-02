"""Neutral type system and per-language API rendering for the port families.

A *port library* is described once by a table of functions with language-neutral types:

    i32 u32 u8 int bool str   list<T>   opt<T> (return type only)

``int`` is a signed 64-bit integer whose values stay within +-2**53 in every test vector (so a JavaScript ``number``
is exact). Every language gets one conventional spelling (see ``TYPE_NAMES``); the README of each task shows the exact
signature a hidden test will call.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SCALARS = ("i32", "u32", "u8", "int", "bool", "str")

RESERVED = {
    "type", "in", "from", "end", "class", "new", "fn", "match", "use", "mod", "ref", "self", "let", "loop", "final", "default",
    "var", "func", "range", "map", "len", "string", "list", "int", "str", "bool", "do", "if", "else", "for", "while", "return",
    "def", "pub", "impl", "trait", "struct", "enum", "const", "static", "true", "false", "null", "nil", "and", "or", "not",
    "is", "as", "async", "await", "yield", "with", "pass", "lambda", "global", "print", "echo", "case", "switch", "import",
    "package", "interface", "this", "super", "void", "char", "long", "short", "byte", "double", "float", "object", "unsafe",
    "move", "where", "select", "chan", "go", "defer", "goto", "throw", "try", "catch", "begin", "rescue", "ensure", "module",
    "undef", "then", "until", "unless", "next", "break", "continue", "delete", "typeof", "function", "export", "extends",
    "abstract", "native", "dict", "set", "tuple", "array", "isset", "unset", "empty", "clone", "exit", "die", "eval",
    "include", "require", "namespace", "main", "assert", "fmt", "out", "cap", "min", "max", "abs",
}


@dataclass(frozen=True)
class T:
    kind: str
    inner: "T | None" = None

    def __str__(self) -> str:
        return self.kind if self.inner is None else f"{self.kind}<{self.inner}>"

    @property
    def is_list(self) -> bool:
        return self.kind == "list"

    @property
    def is_opt(self) -> bool:
        return self.kind == "opt"


def parse_type(s: str) -> T:
    s = s.strip()
    m = re.fullmatch(r"(list|opt)<(.+)>", s)
    if m:
        return T(m.group(1), parse_type(m.group(2)))
    if s in SCALARS:
        return T(s)
    raise ValueError(f"unknown type {s!r}")


@dataclass
class Fn:
    name: str  # snake_case
    args: list[tuple[str, str]]  # [(name, type string)]
    ret: str
    err: bool = False  # may fail: Go (T, error), Rust Result, others throw
    doc: str = ""

    def __post_init__(self):
        for a, t in self.args:
            parse_type(t)
            if a in RESERVED:
                raise ValueError(f"argument name {a!r} of {self.name} is a reserved word somewhere")
        if self.name in RESERVED:
            raise ValueError(f"function name {self.name!r} is a reserved word somewhere")
        rt = parse_type(self.ret)
        if rt.is_opt:
            if self.err:
                raise ValueError("opt return with err is not supported")
            if rt.inner.kind in ("list", "opt"):
                raise ValueError("opt<list>/opt<opt> is not supported")

    @property
    def rtype(self) -> T:
        return parse_type(self.ret)

    @property
    def atypes(self) -> list[T]:
        return [parse_type(t) for _, t in self.args]


def snake_parts(s: str) -> list[str]:
    return [p for p in s.replace("-", "_").split("_") if p]


def pascal(s: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in snake_parts(s))


def camel(s: str) -> str:
    p = pascal(s)
    return p[:1].lower() + p[1:]


def snake(s: str) -> str:
    return "_".join(snake_parts(s))


def flat(s: str) -> str:
    return "".join(snake_parts(s))


def fn_name(lang: str, name: str) -> str:
    if lang in ("javascript", "typescript", "java", "php"):
        return camel(name)
    if lang == "go":
        return pascal(name)
    return name  # python rust ruby c


def arg_name(lang: str, name: str) -> str:
    if lang in ("javascript", "typescript", "java", "php", "go"):
        return camel(name)
    return name


# ---- type spellings ---------------------------------------------------------------------------------------------

_GO = {"i32": "int32", "u32": "uint32", "u8": "uint8", "int": "int64", "bool": "bool", "str": "string"}
_RS = {"i32": "i32", "u32": "u32", "u8": "u8", "int": "i64", "bool": "bool", "str": "String"}
_JAVA = {"i32": "int", "u32": "long", "u8": "int", "int": "long", "bool": "boolean", "str": "String"}
_JAVA_BOX = {"i32": "Integer", "u32": "Long", "u8": "Integer", "int": "Long", "bool": "Boolean", "str": "String"}
_PY = {"i32": "int", "u32": "int", "u8": "int", "int": "int", "bool": "bool", "str": "str"}
_TS = {"i32": "number", "u32": "number", "u8": "number", "int": "number", "bool": "boolean", "str": "string"}
_C = {"i32": "int32_t", "u32": "uint32_t", "u8": "uint8_t", "int": "int64_t", "bool": "int", "str": "const char *"}


def tname(lang: str, t: T, role: str = "arg") -> str:
    """Spelling of type ``t`` in ``lang``; role is "arg" or "ret"."""
    k = t.kind
    if lang == "go":
        if k == "list":
            return "[]" + tname(lang, t.inner, role)
        if k == "opt":
            return tname(lang, t.inner, role)
        return _GO[k]
    if lang == "rust":
        if k == "list":
            inner = tname(lang, t.inner, "elem")
            return f"&[{inner}]" if role == "arg" else f"Vec<{inner}>"
        if k == "opt":
            return f"Option<{tname(lang, t.inner, 'elem')}>"
        if k == "str":
            return "&str" if role == "arg" else "String"
        return _RS[k]
    if lang == "java":
        if k == "list":
            return f"List<{jbox(t.inner)}>"
        if k == "opt":
            return jbox(t.inner)
        return _JAVA[k]
    if lang in ("javascript", "typescript"):
        if k == "list":
            return tname(lang, t.inner, role) + "[]"
        if k == "opt":
            return tname(lang, t.inner, role) + " | null"
        return _TS[k]
    if lang == "python":
        if k == "list":
            return f"list[{tname(lang, t.inner, role)}]"
        if k == "opt":
            return f"{tname(lang, t.inner, role)} | None"
        return _PY[k]
    if lang == "ruby":
        if k == "list":
            return f"Array<{tname(lang, t.inner, role)}>"
        if k == "opt":
            return f"{tname(lang, t.inner, role)} or nil"
        return {"i32": "Integer", "u32": "Integer", "u8": "Integer", "int": "Integer", "bool": "true/false", "str": "String"}[k]
    if lang == "php":
        if k == "list":
            return "array"
        if k == "opt":
            return "?" + tname(lang, t.inner, role)
        return {"i32": "int", "u32": "int", "u8": "int", "int": "int", "bool": "bool", "str": "string"}[k]
    if lang == "c":
        return _C[k]
    raise ValueError(lang)


def jbox(t: T) -> str:
    if t.kind == "list":
        return f"List<{jbox(t.inner)}>"
    return _JAVA_BOX[t.kind]


def rust_owned(t: T) -> str:
    """Element type used inside Vec/slices."""
    if t.kind == "list":
        return f"Vec<{rust_owned(t.inner)}>"
    return _RS[t.kind]


def signature(lang: str, fn: Fn, mod: str = "") -> str:
    """One line signature of ``fn`` as the hidden harness calls it. ``mod`` is the Pascal-case class/module name."""
    name = fn_name(lang, fn.name)
    rt = fn.rtype
    if lang == "python":
        a = ", ".join(f"{n}: {tname(lang, parse_type(t))}" for n, t in fn.args)
        return f"def {name}({a}) -> {tname(lang, rt, 'ret')}"
    if lang == "go":
        a = ", ".join(f"{arg_name(lang, n)} {tname(lang, parse_type(t))}" for n, t in fn.args)
        if fn.err:
            r = f"({tname(lang, rt)}, error)"
        elif rt.is_opt:
            r = f"({tname(lang, rt.inner)}, bool)"
        else:
            r = tname(lang, rt)
        return f"func {name}({a}) {r}"
    if lang == "rust":
        a = ", ".join(f"{n}: {tname(lang, parse_type(t))}" for n, t in fn.args)
        r = tname(lang, rt, "ret")
        if fn.err:
            r = f"Result<{r}, E>"
        return f"pub fn {name}({a}) -> {r}"
    if lang == "java":
        a = ", ".join(f"{tname(lang, parse_type(t))} {arg_name(lang, n)}" for n, t in fn.args)
        return f"public static {tname(lang, rt, 'ret')} {name}({a})"
    if lang == "javascript":
        a = ", ".join(arg_name(lang, n) for n, _ in fn.args)
        types = ", ".join(f"{arg_name(lang, n)}: {tname(lang, parse_type(t))}" for n, t in fn.args)
        return f"{name}({a})   // ({types}) -> {tname(lang, rt, 'ret')}"
    if lang == "typescript":
        a = ", ".join(f"{arg_name(lang, n)}: {tname(lang, parse_type(t))}" for n, t in fn.args)
        return f"export function {name}({a}): {tname(lang, rt, 'ret')}"
    if lang == "ruby":
        a = ", ".join(n for n, _ in fn.args)
        return f"{mod}.{name}({a})   # -> {tname(lang, rt, 'ret')}"
    if lang == "php":
        a = ", ".join(f"{tname(lang, parse_type(t))} ${arg_name(lang, n)}" for n, t in fn.args)
        return f"public static function {name}({a}): {tname(lang, rt, 'ret')}"
    if lang == "c":
        parts = []
        for n, t in fn.args:
            ty = parse_type(t)
            if ty.is_list:
                el = ty.inner
                if el.kind == "str":
                    parts.append(f"const char *const *{n}, size_t {n}_len")
                else:
                    parts.append(f"const {_C[el.kind]} *{n}, size_t {n}_len")
            elif ty.kind == "str":
                parts.append(f"const char *{n}")
            else:
                parts.append(f"{_C[ty.kind]} {n}")
        rk = rt.kind
        if rk == "str":
            parts += ["char *out", "size_t cap"]
            r = "int"
        elif fn.err or rt.is_opt:
            parts.append(f"{_C[rt.inner.kind if rt.is_opt else rk]} *out")
            r = "int"
        else:
            r = _C[rk]
        return f"{r} {mod}_{fn.name}({', '.join(parts)})"
    raise ValueError(lang)


def jsonable_ok(v, t: T) -> bool:
    """Is python value ``v`` a legal value of type ``t``?"""
    k = t.kind
    if k == "opt":
        return v is None or jsonable_ok(v, t.inner)
    if k == "list":
        return isinstance(v, list) and all(jsonable_ok(x, t.inner) for x in v)
    if k == "bool":
        return isinstance(v, bool)
    if k == "str":
        return isinstance(v, str)
    if isinstance(v, bool) or not isinstance(v, int):
        return False
    return {"i32": -2**31 <= v < 2**31, "u32": 0 <= v < 2**32, "u8": 0 <= v < 256, "int": abs(v) <= 2**53}[k]
