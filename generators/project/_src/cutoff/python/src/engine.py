"""The file store and the build engine."""
import actions
import config as C
from hashing import digest
from rules import RuleBook


class File:
    def __init__(self, content, stamp, key):
        self.content = content
        self.stamp = stamp  # logical clock value of the last write
        self.key = key  # digest mode: key of the action run that produced it (None for sources)


class Build:
    """State of one `build` command."""

    def __init__(self, keep_going, budget):
        self.keep_going = keep_going
        self.budget = budget
        self.memo = {}
        self.stack = []
        self.ran = self.same = self.skipped = self.failed = self.blocked = 0
        self.executed = 0
        self.aborted = False


class Engine:
    def __init__(self, emit):
        self.emit = emit  # emit(line, is_error=False)
        self.files = {}
        self.book = RuleBook()
        self.clock = 0
        self.actions_run = 0

    # -- helpers ------------------------------------------------------------------------------------------------
    def derived(self, path):
        return self.book.lookup(path)[0] is not None

    def tick(self):
        self.clock += 1
        return self.clock

    def key_of(self, rule, deps):
        parts = ",".join(digest(self.files[d].content) for d in deps)
        return digest(rule.action_text() + "\x1f" + parts)

    # -- source files ---------------------------------------------------------------------------------------------
    def put(self, path, content):
        self.files[path] = File(content, self.tick(), None)

    def touch(self, path):
        self.files[path].stamp = self.tick()

    def clean(self, paths):
        if paths is None:
            paths = sorted(p for p in self.files if self.derived(p))
        for p in paths:
            del self.files[p]
        return len(paths)

    # -- building -------------------------------------------------------------------------------------------------
    def build(self, targets, keep_going, budget, summary):
        st = Build(keep_going, budget)
        for t in targets:
            if st.aborted:
                break
            self.visit(t, None, st)
        self.emit("%s: ran=%d same=%d skipped=%d failed=%d blocked=%d" % (summary, st.ran, st.same, st.skipped, st.failed, st.blocked))

    def fail(self, st, line):
        self.emit(line, True)
        st.failed += 1
        if not st.keep_going:
            st.aborted = True

    def visit(self, path, requester, st):
        if path in st.memo:
            return st.memo[path]
        rule, deps = self.book.lookup(path)
        if rule is None:
            if path in self.files:
                st.memo[path] = "source"
                return "source"
            need = "" if requester is None else " (needed by '%s')" % requester
            self.fail(st, "error: no rule to make '%s'%s" % (path, need))
            st.memo[path] = "failed"
            return "failed"
        if path in st.stack:
            i = st.stack.index(path)
            self.fail(st, "error: cycle " + " -> ".join(st.stack[i:] + [path]))
            return "failed"
        st.stack.append(path)
        bad = False
        for d in deps:
            if st.aborted:
                break
            if self.visit(d, path, st) in ("failed", "blocked"):
                bad = True
        st.stack.pop()
        if st.aborted:
            return "failed"
        if bad:
            self.emit("blocked " + path)
            st.blocked += 1
            st.memo[path] = "blocked"
            return "blocked"
        f = self.files.get(path)
        key = self.key_of(rule, deps)
        if C.MODE == "digest":
            stale = f is None or f.key != key
        else:
            stale = f is None or any(self.files[d].stamp > f.stamp for d in deps)
        if rule.always:
            stale = True
        if not stale:
            self.emit("skip " + path)
            st.skipped += 1
            st.memo[path] = "fresh"
            return "fresh"
        if st.budget is not None and st.executed >= st.budget:
            self.emit("halt: budget of %d actions reached" % st.budget)
            st.aborted = True
            return "failed"
        st.executed += 1
        self.actions_run += 1
        try:
            out = actions.run(rule.action, rule.args, [self.files[d].content for d in deps])
        except actions.ActionError as e:
            self.fail(st, "fail %s: %s" % (path, e))
            st.memo[path] = "failed"
            return "failed"
        same = f is not None and f.content == out
        self.files[path] = File(out, self.tick(), key)
        self.emit(("same " if same else "run ") + path)
        if same:
            st.same += 1
        else:
            st.ran += 1
        st.memo[path] = "built"
        return "built"

    # -- status (never runs an action) ----------------------------------------------------------------------------
    def status(self, targets):
        memo, stack = {}, []

        def walk(path, requester):
            if path in memo:
                return memo[path]
            rule, deps = self.book.lookup(path)
            if rule is None:
                if path in self.files:
                    memo[path] = "source"
                else:
                    need = "" if requester is None else " (needed by '%s')" % requester
                    self.emit("error: no rule to make '%s'%s" % (path, need), True)
                    memo[path] = "error"
                return memo[path]
            if path in stack:
                i = stack.index(path)
                self.emit("error: cycle " + " -> ".join(stack[i:] + [path]), True)
                return "error"
            stack.append(path)
            states = [walk(d, path) for d in deps]
            stack.pop()
            if "error" in states:
                memo[path] = "error"
                return "error"
            f = self.files.get(path)
            first_stale = next((d for d, s in zip(deps, states) if s == "stale"), None)
            if f is None:
                reason = "missing"
            elif first_stale is not None:
                reason = "dep " + first_stale
            elif rule.always:
                reason = "always"
            else:
                key = self.key_of(rule, deps)
                if C.MODE == "digest":
                    changed = f.key != key
                else:
                    changed = any(self.files[d].stamp > f.stamp for d in deps)
                reason = "changed" if changed else None
            if reason is None:
                self.emit("fresh " + path)
                memo[path] = "fresh"
            else:
                self.emit("stale %s (%s)" % (path, reason))
                memo[path] = "stale"
            return memo[path]

        for t in targets:
            walk(t, None)
