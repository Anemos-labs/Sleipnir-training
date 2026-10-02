"""The evaluator: scopes, closures, calls, handlers (emit / handle), defer."""
import config as C
from lexer import FableError
from values import MAX_INT, MIN_INT, Builtin, Closure, equal, show, truthy, type_name


class Return(Exception):
    def __init__(self, value):
        Exception.__init__(self)
        self.value = value


class Env:
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def find(self, name):
        e = self
        while e is not None:
            if name in e.vars:
                return e
            e = e.parent
        return None


def err(line, msg):
    raise FableError(line, msg)


def checked(line, n):
    if n < MIN_INT or n > MAX_INT:
        err(line, "integer overflow")
    return n


class Interp:
    def __init__(self, out):
        self.out = out
        self.depth = 0
        self.steps = 0
        self.handlers = []  # (tag, callable)
        self.fn_depth = 0
        self.globals = Env()
        from builtins_ import install
        install(self)

    # -- calls ----------------------------------------------------------------------------------------------------------
    def call(self, f, args, line, name_hint=None):
        if isinstance(f, Closure):
            if len(args) != len(f.params):
                err(line, "wrong number of arguments for %s: expected %d, got %d" % (f.name or "function", len(f.params), len(args)))
            if self.depth >= C.DEPTH_LIMIT:
                err(line, "call depth exceeded")
            env = Env(f.env)
            for p, a in zip(f.params, args):
                env.vars[p] = a
            self.depth += 1
            self.fn_depth += 1
            try:
                return self.eval(f.body, env)
            except Return as r:
                return r.value
            finally:
                self.depth -= 1
                self.fn_depth -= 1
        if isinstance(f, Builtin):
            ok = f.arity if isinstance(f.arity, tuple) else (f.arity,)
            if len(args) not in ok:
                err(line, "wrong number of arguments for %s: expected %s, got %d" % (f.name, " or ".join(str(a) for a in ok), len(args)))
            return f.fn(self, line, args)
        err(line, "type error: %s is not callable" % type_name(f))

    # -- statements -------------------------------------------------------------------------------------------------------
    def run_block(self, stmts, env, scope=True):
        """Run statements in a new scope; the value is that of the last statement (nil if none). Deferred expressions run at exit."""
        inner = Env(env) if scope else env
        deferred = []
        value = None
        try:
            for st in stmts:
                value = self.exec(st, inner, deferred)
        except Return:
            self.run_deferred(deferred, inner)
            raise
        self.run_deferred(deferred, inner)
        return value

    def run_deferred(self, deferred, env):
        while deferred:
            stmt = deferred.pop()
            later = []
            self.exec(stmt, env, later)
            self.run_deferred(later, env)

    def exec(self, st, env, deferred):
        k = st[0]
        if k == "expr":
            return self.eval(st[2], env)
        if k == "let":
            env.vars[st[2]] = self.eval(st[3], env)
            return None
        if k == "fndef":
            f = Closure(st[2], st[3], st[4], env)
            env.vars[st[2]] = f
            return None
        if k == "assign":
            v = self.eval(st[3], env)
            e = env.find(st[2])
            if e is None:
                err(st[1], "cannot assign to unbound variable '%s'" % st[2])
            e.vars[st[2]] = v
            return None
        if k == "print":
            self.out.append(show(self.eval(st[2], env)))
            return None
        if k == "return":
            if self.fn_depth == 0:
                err(st[1], "return outside function")
            raise Return(None if st[2] is None else self.eval(st[2], env))
        if k == "defer":
            deferred.append(st[2])
            return None
        if k == "while":
            while truthy(self.eval(st[2], env)):
                self.tick(st[1])
                self.run_block(st[3], env)
            return None
        if k == "for":
            seq = self.eval(st[3], env)
            if isinstance(seq, str):
                items = list(seq)
            elif isinstance(seq, tuple):
                items = list(seq)
            else:
                err(st[1], "type error: cannot iterate over %s" % type_name(seq))
            for item in items:
                self.tick(st[1])
                inner = Env(env)
                inner.vars[st[2]] = item
                self.run_block(st[4], inner)
            return None
        raise AssertionError(k)

    def tick(self, line):
        self.steps += 1
        if self.steps > C.LOOP_LIMIT:
            err(line, "step limit exceeded")

    # -- expressions ------------------------------------------------------------------------------------------------------
    def eval(self, n, env):
        k = n[0]
        if k == "lit":
            return n[2]
        if k == "var":
            e = env.find(n[2])
            if e is None:
                err(n[1], "unbound variable '%s'" % n[2])
            return e.vars[n[2]]
        if k == "bin":
            return self.binary(n, env)
        if k == "call":
            f = self.eval(n[2], env)
            args = [self.eval(a, env) for a in n[3]]
            return self.call(f, args, n[1])
        if k == "pipe":
            left = self.eval(n[2], env)
            right = n[3]
            if right[0] == "call":
                f = self.eval(right[2], env)
                args = [left] + [self.eval(a, env) for a in right[3]]
            else:
                f = self.eval(right, env)
                args = [left]
            return self.call(f, args, n[1])
        if k == "if":
            if truthy(self.eval(n[2], env)):
                return self.run_block(n[3], env)
            return self.run_block(n[4], env) if n[4] is not None else None
        if k == "do":
            return self.run_block(n[2], env)
        if k == "lambda":
            return Closure(None, n[2], n[3], env)
        if k == "list":
            return tuple(self.eval(x, env) for x in n[2])
        if k == "index":
            return self.index(n, env)
        if k == "and":
            left = self.eval(n[2], env)
            return self.eval(n[3], env) if truthy(left) else left
        if k == "or":
            left = self.eval(n[2], env)
            return left if truthy(left) else self.eval(n[3], env)
        if k == "not":
            return not truthy(self.eval(n[2], env))
        if k == "neg":
            v = self.eval(n[2], env)
            if type_name(v) != "int":
                err(n[1], "type error: cannot apply '-' to %s" % type_name(v))
            return checked(n[1], -v)
        if k == "emit":
            value = self.eval(n[3], env)
            for idx in range(len(self.handlers) - 1, -1, -1):
                if self.handlers[idx][0] == n[2]:
                    break
            else:
                err(n[1], "unhandled emit '%s'" % n[2])
            handler = self.handlers[idx][1]
            saved = self.handlers
            self.handlers = saved[:idx]
            try:
                return self.call(handler, [value], n[1])
            finally:
                self.handlers = saved
        if k == "handle":
            h = self.eval(n[3], env)
            if not isinstance(h, (Closure, Builtin)):
                err(n[1], "type error: %s is not callable" % type_name(h))
            self.handlers = self.handlers + [(n[2], h)]
            depth = len(self.handlers)
            try:
                return self.run_block(n[4], env)
            finally:
                self.handlers = self.handlers[: depth - 1]
        raise AssertionError(k)

    def binary(self, n, env):
        op = n[2]
        a = self.eval(n[3], env)
        b = self.eval(n[4], env)
        ta, tb = type_name(a), type_name(b)
        if op == "==":
            return equal(a, b)
        if op == "!=":
            return not equal(a, b)
        if op in ("<", "<=", ">", ">="):
            if ta == tb and ta in ("int", "string"):
                return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
        elif op == "+":
            if ta == tb == "int":
                return checked(n[1], a + b)
            if ta == tb and ta in ("string", "list"):
                return a + b
        elif ta == tb == "int":
            if op == "-":
                return checked(n[1], a - b)
            if op == "*":
                return checked(n[1], a * b)
            if b == 0:
                err(n[1], "division by zero")
            q = abs(a) // abs(b)
            q = q if (a < 0) == (b < 0) else -q
            return checked(n[1], q) if op == "/" else a - b * q
        err(n[1], "type error: cannot apply '%s' to %s and %s" % (op, ta, tb))

    def index(self, n, env):
        seq = self.eval(n[2], env)
        i = self.eval(n[3], env)
        ts, ti = type_name(seq), type_name(i)
        if ts not in ("list", "string") or ti != "int":
            err(n[1], "type error: cannot index %s with %s" % (ts, ti))
        ln = len(seq)
        j = i + ln if i < 0 else i
        if not 0 <= j < ln:
            err(n[1], "index out of range: %d (length %d)" % (i, ln))
        return seq[j]
