"""Command-line front end: reads a script from standard input and prints what each command reports."""
import re
import sys

import config as C
from engine import Engine
from hashing import digest
from rules import good_path, parse_rule

UINT = re.compile(r"^[0-9]+$")


def unescape(text):
    out, i = [], 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text) and text[i + 1] in "nt\\":
            out.append({"n": "\n", "t": "\t", "\\": "\\"}[text[i + 1]])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def escape(text):
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")


class Script:
    def __init__(self):
        self.lines = []
        self.errors = 0
        self.engine = Engine(self.emit)

    def emit(self, line, is_error=False):
        self.lines.append(line)
        if is_error or line.startswith("fail ") or line.startswith("error:"):
            self.errors += 1

    def err(self, msg):
        self.emit("error: " + msg, True)

    # -- commands ---------------------------------------------------------------------------------------------------
    def cmd_put(self, rest):
        path, _, text = rest.lstrip(" ").partition(" ")
        if not path:
            return self.err("usage: %s PATH [TEXT]" % C.CMD_PUT)
        if not good_path(path):
            return self.err("bad path '%s'" % path)
        if self.engine.derived(path):
            return self.err("'%s' is derived, not a source file" % path)
        content = unescape(text)
        self.engine.put(path, content)
        self.emit("wrote %s (%d bytes)" % (path, len(content.encode("utf-8"))))

    def cmd_rule(self, tokens):
        fields, msg = parse_rule(tokens)
        if fields is None:
            return self.err(msg)
        target, deps, action, args, always = fields
        if self.engine.book.has_target(target):
            return self.err("duplicate rule for '%s'" % target)
        hits = self.engine.book.pattern_hits(target, self.engine.files)
        if hits:
            return self.err("'%s' already exists as a source file" % hits[0])
        self.engine.book.add(target, deps, action, args, always)
        self.emit("rule " + target)

    def cmd_build(self, tokens):
        keep, budget, i = False, None, 0
        while i < len(tokens) and tokens[i].startswith("-"):
            t = tokens[i]
            if t in ("--keep-going", "-k") and C.KEEP_GOING:
                keep = True
            elif t == "--max" and C.BUDGET:
                if i + 1 >= len(tokens) or not UINT.match(tokens[i + 1]):
                    return self.err("bad --max value '%s'" % (tokens[i + 1] if i + 1 < len(tokens) else ""))
                budget = int(tokens[i + 1])
                i += 1
            else:
                return self.err("unknown option '%s'" % t)
            i += 1
        targets = tokens[i:]
        if not targets:
            return self.err("%s needs at least one target" % C.CMD_BUILD)
        for t in targets:
            if not good_path(t):
                return self.err("bad path '%s'" % t)
        self.engine.build(targets, keep, budget, C.SUMMARY)

    def cmd_status(self, tokens):
        if not tokens:
            return self.err("status needs at least one target")
        for t in tokens:
            if not good_path(t):
                return self.err("bad path '%s'" % t)
        self.engine.status(tokens)

    def cmd_show(self, tokens):
        if len(tokens) != 1:
            return self.err("usage: show PATH")
        f = self.engine.files.get(tokens[0])
        if f is None:
            return self.err("no such file '%s'" % tokens[0])
        self.emit('%s = "%s"' % (tokens[0], escape(f.content)))

    def cmd_digest(self, tokens):
        if len(tokens) != 1:
            return self.err("usage: digest PATH")
        f = self.engine.files.get(tokens[0])
        if f is None:
            return self.err("no such file '%s'" % tokens[0])
        self.emit("%s %s" % (tokens[0], digest(f.content)))

    def cmd_touch(self, tokens):
        if len(tokens) != 1:
            return self.err("usage: touch PATH")
        if tokens[0] not in self.engine.files:
            return self.err("no such file '%s'" % tokens[0])
        self.engine.touch(tokens[0])
        self.emit("touched " + tokens[0])

    def cmd_clean(self, tokens):
        for t in tokens:
            if t not in self.engine.files or not self.engine.derived(t):
                return self.err("'%s' is not a derived file" % t)
        n = self.engine.clean(sorted(set(tokens)) if tokens else None)
        self.emit("cleaned %d files" % n)

    def cmd_ls(self, tokens):
        for p in sorted(self.engine.files):
            kind = "derived" if self.engine.derived(p) else "source"
            self.emit("%s %s %s" % (p, digest(self.engine.files[p].content), kind))

    def cmd_stats(self, tokens):
        e = self.engine
        self.emit("files=%d rules=%d actions=%d clock=%d" % (len(e.files), len(e.book.rules), e.actions_run, e.clock))

    def run_line(self, raw):
        line = raw.strip()
        if not line or line.startswith("#"):
            return
        cmd, _, rest = line.partition(" ")
        tokens = rest.split()
        table = {
            C.CMD_PUT: lambda: self.cmd_put(rest),
            "rule": lambda: self.cmd_rule(tokens),
            C.CMD_BUILD: lambda: self.cmd_build(tokens),
            "show": lambda: self.cmd_show(tokens),
            "digest": lambda: self.cmd_digest(tokens),
            "ls": lambda: self.cmd_ls(tokens),
            "stats": lambda: self.cmd_stats(tokens),
        }
        if C.HAS_STATUS:
            table["status"] = lambda: self.cmd_status(tokens)
        if C.HAS_CLEAN:
            table["clean"] = lambda: self.cmd_clean(tokens)
        if C.HAS_TOUCH:
            table["touch"] = lambda: self.cmd_touch(tokens)
        fn = table.get(cmd)
        if fn is None:
            return self.err("unknown command '%s'" % cmd)
        fn()


def main():
    script = Script()
    for raw in sys.stdin.read().split("\n"):
        script.run_line(raw)
    sys.stdout.write("".join(ln + "\n" for ln in script.lines))
    return 1 if script.errors else 0


if __name__ == "__main__":
    sys.exit(main())
