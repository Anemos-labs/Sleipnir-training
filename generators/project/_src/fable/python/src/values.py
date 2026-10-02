"""Fable values: int, string, bool, nil (None), list (tuple), functions."""
import config as C

MIN_INT, MAX_INT = -2 ** 63, 2 ** 63 - 1


class Closure:
    def __init__(self, name, params, body, env):
        self.name = name
        self.params = params
        self.body = body  # an expression node
        self.env = env


class Builtin:
    def __init__(self, name, arity, fn):
        self.name = name
        self.arity = arity  # int or a tuple of allowed counts
        self.fn = fn


def type_name(v):
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, str):
        return "string"
    if isinstance(v, tuple):
        return "list"
    return "function"


def equal(a, b):
    ta, tb = type_name(a), type_name(b)
    if ta != tb:
        return False
    if ta == "list":
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    if ta == "function":
        return a is b
    return a == b


def quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r") + '"'


def show(v, nested=False):
    t = type_name(v)
    if t == "nil":
        return "nil"
    if t == "bool":
        return "true" if v else "false"
    if t == "int":
        return str(v)
    if t == "string":
        return quote(v) if nested else v
    if t == "list":
        return "[" + ", ".join(show(x, True) for x in v) + "]"
    if isinstance(v, Builtin):
        return "<builtin %s>" % v.name
    return "<fn %s>" % v.name if v.name else "<fn>"


def truthy(v):
    return v is not None and v is not False
