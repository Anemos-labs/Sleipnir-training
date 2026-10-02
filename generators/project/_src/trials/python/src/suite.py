"""Reader for suite.txt."""
import re

import config as C

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
SCOPES = {"test": 0, "module": 1, "session": 2}
LITERAL_RE = re.compile(r"^[A-Za-z0-9_.-]{1,16}$")


class SuiteError(Exception):
    pass


class Step:
    def __init__(self, kind, args, line):
        self.kind = kind
        self.args = args
        self.line = line


class Fixture:
    def __init__(self, name, scope, needs, line):
        self.name = name
        self.scope = scope
        self.needs = needs
        self.line = line
        self.setup = []
        self.teardown = []
        self.value = "-"


class Test:
    def __init__(self, name, needs, marks, params, line, module):
        self.name = name
        self.needs = needs
        self.marks = marks
        self.params = params
        self.line = line
        self.module = module
        self.steps = []


def fail(n, msg):
    raise SuiteError("suite.txt:%d: %s" % (n, msg))


def clauses(words, n, allowed):
    """`needs A B marks x` -> {"needs": [A, B], "marks": [x]}; a clause word needs at least one value and may appear once."""
    out, cur = {}, None
    for w in words:
        if w in allowed:
            if w in out:
                fail(n, "bad line")
            out[w] = []
            cur = w
        elif cur is None:
            fail(n, "bad line")
        else:
            out[cur].append(w)
    if any(not v for v in out.values()):
        fail(n, "bad line")
    return out


def parse_step(words, n, where):
    kind = words[0]
    rest = words[1:]
    if kind == "log":
        return Step("log", [" ".join(rest)], n)
    if kind == "fail":
        return Step("fail", [" ".join(rest)], n)
    if kind == "raise":
        if len(rest) != 1 or not NAME_RE.match(rest[0]):
            fail(n, "bad step '%s'" % " ".join(words))
        return Step("raise", rest, n)
    if kind == "tick":
        if len(rest) != 1 or not re.match(r"^[0-9]{1,5}$", rest[0]):
            fail(n, "bad step '%s'" % " ".join(words))
        return Step("tick", [int(rest[0])], n)
    if kind == "expect" and where == "test":
        if len(rest) != 3 or rest[1] not in ("==", "!=", "<", ">") or not LITERAL_RE.match(rest[2]):
            fail(n, "bad step '%s'" % " ".join(words))
        return Step("expect", rest, n)
    if kind == "flaky" and where == "test" and C.HAS_FLAKY:
        if len(rest) != 1 or not re.match(r"^[0-9]$", rest[0]):
            fail(n, "bad step '%s'" % " ".join(words))
        return Step("flaky", [int(rest[0])], n)
    fail(n, "bad step '%s'" % " ".join(words))


def read_suite(text):
    fixtures, tests, modules = {}, [], []
    cur = None  # the open fixture or test
    module = "main"
    for n, raw in enumerate(text.split("\n"), 1):
        body = raw.split("#", 1)[0].rstrip()
        if not body.strip():
            continue
        words = body.split()
        if body[0] in " \t":
            if cur is None:
                fail(n, "indented line outside a block")
            if isinstance(cur, Fixture):
                if words[0] in ("setup", "teardown"):
                    if len(words) < 2:
                        fail(n, "bad step '%s'" % " ".join(words))
                    (cur.setup if words[0] == "setup" else cur.teardown).append(parse_step(words[1:], n, "fixture"))
                elif words[0] == "value":
                    if len(words) != 2 or not LITERAL_RE.match(words[1]):
                        fail(n, "bad value")
                    cur.value = words[1]
                else:
                    fail(n, "unknown fixture line '%s'" % words[0])
            else:
                if words[0] != "step" or len(words) < 2:
                    fail(n, "unknown test line '%s'" % words[0])
                cur.steps.append(parse_step(words[1:], n, "test"))
            continue
        d = words[0]
        if d == "module":
            if len(words) != 2 or not NAME_RE.match(words[1]):
                fail(n, "bad line")
            module = words[1]
            cur = None
        elif d == "fixture":
            if len(words) < 2 or not NAME_RE.match(words[1]):
                fail(n, "bad line")
            name = words[1]
            if name in fixtures:
                fail(n, "duplicate fixture '%s'" % name)
            cl = clauses(words[2:], n, ("scope", "needs"))
            scope = "test"
            if "scope" in cl:
                if len(cl["scope"]) != 1:
                    fail(n, "bad line")
                if cl["scope"][0] not in SCOPES:
                    fail(n, "bad scope '%s'" % cl["scope"][0])
                scope = cl["scope"][0]
            cur = Fixture(name, scope, cl.get("needs", []), n)
            fixtures[name] = cur
        elif d == "test":
            if len(words) < 2 or not NAME_RE.match(words[1]):
                fail(n, "bad line")
            name = words[1]
            if any(t.name == name for t in tests):
                fail(n, "duplicate test '%s'" % name)
            cl = clauses(words[2:], n, ("needs", "marks", "param"))
            for v in cl.get("param", []):
                if not LITERAL_RE.match(v):
                    fail(n, "bad value")
            cur = Test(name, cl.get("needs", []), cl.get("marks", []), cl.get("param", []), n, module)
            tests.append(cur)
            if module not in modules:
                modules.append(module)
        else:
            fail(n, "unknown directive '%s'" % d)
    for f in fixtures.values():
        for need in f.needs:
            if need not in fixtures:
                fail(f.line, "unknown fixture '%s'" % need)
    for t in tests:
        for need in t.needs:
            if need not in fixtures:
                fail(t.line, "unknown fixture '%s'" % need)
    # cycles, then scope widths
    def visit(f, path):
        if f.name in path:
            fail(f.line, "fixture cycle " + " -> ".join(path[path.index(f.name):] + [f.name]))
        for need in f.needs:
            visit(fixtures[need], path + [f.name])

    for f in fixtures.values():
        visit(f, [])
    for f in fixtures.values():
        for need in f.needs:
            if SCOPES[fixtures[need].scope] < SCOPES[f.scope]:
                fail(f.line, "fixture '%s' has a wider scope than its dependency '%s'" % (f.name, need))
    return fixtures, tests, modules
