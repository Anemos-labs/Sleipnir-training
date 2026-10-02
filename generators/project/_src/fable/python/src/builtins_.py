"""Builtin functions."""
import re

import config as C
from interp_helpers import bad, expect
from values import Builtin, show, truthy, type_name


def install(it):
    def reg(name, arity, fn):
        if name in C.BUILTINS:
            it.globals.vars[name] = Builtin(name, arity, fn)

    def b_len(it, line, a):
        if type_name(a[0]) not in ("list", "string"):
            bad(line, "len")
        return len(a[0])

    def b_str(it, line, a):
        return show(a[0])

    def b_int(it, line, a):
        v = a[0]
        if type_name(v) == "int":
            return v
        if type_name(v) == "string" and re.match(r"^-?[0-9]{1,18}$", v):
            return int(v)
        if type_name(v) == "string":
            from interp_helpers import fail
            fail(line, "cannot convert '%s' to int" % v)
        bad(line, "int")

    def b_push(it, line, a):
        if type_name(a[0]) != "list":
            bad(line, "push")
        return a[0] + (a[1],)

    def b_range(it, line, a):
        if any(type_name(x) != "int" for x in a):
            bad(line, "range")
        lo, hi = (0, a[0]) if len(a) == 1 else (a[0], a[1])
        if hi - lo > 10000:
            from interp_helpers import fail
            fail(line, "range too large")
        return tuple(range(lo, hi))

    def b_map(it, line, a):
        if type_name(a[0]) != "list":
            bad(line, "map")
        return tuple(it.call(a[1], [x], line) for x in a[0])

    def b_filter(it, line, a):
        if type_name(a[0]) != "list":
            bad(line, "filter")
        return tuple(x for x in a[0] if truthy(it.call(a[1], [x], line)))

    def b_fold(it, line, a):
        if type_name(a[0]) != "list":
            bad(line, "fold")
        acc = a[1]
        for x in a[0]:
            acc = it.call(a[2], [acc, x], line)
        return acc

    def b_join(it, line, a):
        if type_name(a[0]) != "list" or type_name(a[1]) != "string":
            bad(line, "join")
        return a[1].join(show(x) for x in a[0])

    def b_split(it, line, a):
        if type_name(a[0]) != "string" or type_name(a[1]) != "string" or a[1] == "":
            bad(line, "split")
        return tuple(a[0].split(a[1]))

    def b_upper(it, line, a):
        if type_name(a[0]) != "string":
            bad(line, "upper")
        return "".join(chr(ord(c) - 32) if "a" <= c <= "z" else c for c in a[0])

    def b_slice(it, line, a):
        if type_name(a[0]) not in ("list", "string") or type_name(a[1]) != "int" or type_name(a[2]) != "int":
            bad(line, "slice")
        n = len(a[0])
        lo, hi = max(0, min(n, a[1])), max(0, min(n, a[2]))
        return a[0][lo:hi] if lo < hi else a[0][0:0]

    reg("len", 1, b_len)
    reg("str", 1, b_str)
    reg("int", 1, b_int)
    reg("push", 2, b_push)
    reg("range", (1, 2), b_range)
    reg("map", 2, b_map)
    reg("filter", 2, b_filter)
    reg("fold", 3, b_fold)
    reg("join", 2, b_join)
    reg("split", 2, b_split)
    reg("upper", 1, b_upper)
    reg("slice", 3, b_slice)
