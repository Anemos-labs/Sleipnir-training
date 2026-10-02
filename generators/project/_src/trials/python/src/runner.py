"""Running a suite: fixture instances by scope, setup and teardown order, retries, outcomes."""
import config as C
from suite import SCOPES


class Failure(Exception):
    def __init__(self, kind, msg):
        Exception.__init__(self, msg)
        self.kind = kind  # fail error timeout
        self.msg = msg


class Instance:
    def __init__(self, fixture, error):
        self.fixture = fixture
        self.error = error  # None or the message of the failed setup


class Runner:
    def __init__(self, fixtures, tests, modules, opts, say):
        self.fixtures, self.tests, self.modules, self.opts, self.say = fixtures, tests, modules, opts, say
        self.clock = 0
        self.counts = {"passed": 0, "failed": 0, "errors": 0, "timeouts": 0, "skipped": 0, "xfailed": 0, "xpassed": 0}
        self.stop = False
        self.cache = {"module": {}, "session": {}}
        self.stack = {"module": [], "session": []}  # fixtures set up successfully, in order

    # -- steps ----------------------------------------------------------------------------------------------------------
    def run_step(self, step, who, ctx):
        k = step.kind
        if k == "log":
            self.say("    log: " + step.args[0])
        elif k == "tick":
            self.clock += step.args[0]
            if ctx is not None:
                ctx["ticks"] += step.args[0]
                if ctx["ticks"] > C.TIMEOUT:
                    raise Failure("timeout", "timeout after %d ms" % ctx["ticks"])
        elif k == "fail":
            raise Failure("fail" if ctx is not None else "error", step.args[0] or "failed")
        elif k == "raise":
            raise Failure("error", "raised " + step.args[0])
        elif k == "flaky":
            if ctx["attempt"] <= step.args[0]:
                raise Failure("fail", "flaky failure (attempt %d)" % ctx["attempt"])
        elif k == "expect":
            name, op, lit = step.args
            if name == "param" and ctx["param"] is not None:
                got = ctx["param"]
            elif name in ctx["values"]:
                got = ctx["values"][name]
            else:
                raise Failure("error", "unknown name '%s'" % name)
            ok = got == lit if op == "==" else got != lit if op == "!=" else self.numeric(got, lit, op)
            if not ok:
                raise Failure("fail", "expected %s %s %s but got %s" % (name, op, lit, got))

    @staticmethod
    def numeric(a, b, op):
        def num(x):
            try:
                return int(x) if x.lstrip("-").isdigit() and x.lstrip("-") != "" else None
            except ValueError:
                return None

        x, y = num(a), num(b)
        if x is None or y is None:
            return False
        return x < y if op == "<" else x > y

    # -- fixtures ---------------------------------------------------------------------------------------------------------
    def ensure(self, name, test_stack, ctx):
        f = self.fixtures[name]
        cache = self.cache.get(f.scope)
        if cache is None:
            cache = ctx["fixtures"]
        if name in cache:
            inst = cache[name]
            if inst.error is not None:
                raise Failure("error", inst.error)
            return inst
        for dep in f.needs:
            self.ensure(dep, test_stack, ctx)
        self.say("  setup " + name)
        try:
            for step in f.setup:
                self.run_step(step, name, None)
        except Failure as e:
            msg = "setup %s failed: %s" % (name, e.msg)
            cache[name] = Instance(f, msg)
            raise Failure("error", msg)
        inst = Instance(f, None)
        cache[name] = inst
        if f.scope == "test":
            test_stack.append(f)
        else:
            self.stack[f.scope].append(f)
        return inst

    def teardown_list(self, fixtures_in_order):
        """Tear down fixtures in reverse order; returns the first error message."""
        first = None
        for f in reversed(fixtures_in_order):
            self.say("  teardown " + f.name)
            try:
                for step in f.teardown:
                    self.run_step(step, f.name, None)
            except Failure as e:
                if first is None:
                    first = "teardown %s failed: %s" % (f.name, e.msg)
        return first

    # -- tests ----------------------------------------------------------------------------------------------------------------
    def attempt(self, test, param, attempt_no):
        ctx = {"ticks": 0, "attempt": attempt_no, "param": param, "values": {}, "fixtures": {}}
        stack = []
        outcome, msg = "pass", ""
        try:
            for name in test.needs:
                self.ensure(name, stack, ctx)
            ctx["values"] = {n: self.fixtures[n].value for n in self.needed_closure(test)}
            for step in test.steps:
                self.run_step(step, test.name, ctx)
        except Failure as e:
            outcome, msg = e.kind, e.msg
        err = self.teardown_list(stack)
        if err is not None and outcome == "pass":
            outcome, msg = "error", err
        return outcome, msg

    def needed_closure(self, test):
        seen = []

        def go(n):
            if n not in seen:
                seen.append(n)
                for d in self.fixtures[n].needs:
                    go(d)

        for n in test.needs:
            go(n)
        return seen

    def run_one(self, test, name, param):
        if "skip" in test.marks or (C.HAS_SKIP_SLOW and self.opts["skip_slow"] and "slow" in test.marks):
            self.say("  SKIP " + name)
            self.counts["skipped"] += 1
            return "skip"
        retries = self.opts["retries"]
        k = 0
        while True:
            if k > 0:
                self.say("  retry %d" % k)
            outcome, msg = self.attempt(test, param, k + 1)
            if outcome == "pass" or k >= retries:
                break
            k += 1
        suffix = " [retried %d]" % k if k else ""
        if "xfail" in test.marks:
            if outcome == "fail":
                outcome = "xfail"
            elif outcome == "pass":
                outcome = "xpass"
        label = {"pass": "PASS", "fail": "FAIL", "error": "ERROR", "timeout": "TIMEOUT", "xfail": "XFAIL", "xpass": "XPASS"}[outcome]
        key = {"pass": "passed", "fail": "failed", "error": "errors", "timeout": "timeouts", "xfail": "xfailed", "xpass": "xpassed"}[outcome]
        self.counts[key] += 1
        self.say("  %s %s%s" % (label, name, ((": " + msg) if msg and outcome != "xpass" and outcome != "pass" else "")) + suffix)
        return outcome

    def expanded(self):
        out = []
        for t in self.tests:
            if t.params:
                for v in t.params:
                    out.append((t, "%s[%s]" % (t.name, v), v))
            else:
                out.append((t, t.name, None))
        return out

    def run(self):
        selected = [(t, n, p) for t, n, p in self.expanded() if self.opts["only"] is None or self.opts["only"] in n]
        errors_after = 0
        for module in self.modules:
            mine = [x for x in selected if x[0].module == module]
            if not mine:
                continue
            self.say("module " + module)
            for t, n, p in mine:
                if self.stop:
                    break
                res = self.run_one(t, n, p)
                if self.opts["fail_fast"] and res in ("fail", "error", "timeout", "xpass"):
                    self.say("  stopped by --fail-fast")
                    self.stop = True
            err = self.teardown_list(self.stack["module"])
            self.stack["module"] = []
            self.cache["module"] = {}
            if err:
                self.say("  ERROR " + err)
                self.counts["errors"] += 1
            if self.stop:
                break
        if self.stack["session"]:
            err = self.teardown_list(self.stack["session"])
            if err:
                self.say("  ERROR " + err)
                self.counts["errors"] += 1
        c = self.counts
        self.say("summary: %d passed, %d failed, %d errors, %d timeouts, %d skipped, %d xfailed, %d xpassed" % (c["passed"], c["failed"], c["errors"], c["timeouts"], c["skipped"], c["xfailed"], c["xpassed"]))
        self.say("clock: %d ms" % self.clock)
        return c["failed"] + c["errors"] + c["timeouts"] + c["xpassed"] > 0
