"""quill: a scripted text editor core (buffer, marks, undo tree, wildcard search)."""
import re
import sys

import config as C
from buffer import Buffer
from history import History
from pattern import PatternError, compile_pattern, find_all, find_from

NUM = re.compile(r"^[0-9]{1,9}$")


class CmdError(Exception):
    pass


def unescape(text):
    out, i = [], 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text) and text[i + 1] in "nt\\":
            out.append({"n": "\n", "t": "\t", "\\": "\\"}[text[i + 1]])
            i += 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def escape(text):
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")


def num(tok):
    if not NUM.match(tok):
        raise CmdError("bad number '%s'" % tok)
    return int(tok)


class Editor:
    def __init__(self):
        self.buf = Buffer()
        self.hist = History(self.buf)
        self.reg = None
        self.out = []
        self.errors = 0

    def say(self, line):
        self.out.append(line)

    # -- helpers -------------------------------------------------------------------------------------------------
    def pos(self, tok):
        p = num(tok)
        if p > len(self.buf.text):
            raise CmdError("position %d out of range (0..%d)" % (p, len(self.buf.text)))
        return p

    def span(self, ptok, ltok):
        p, ln = num(ptok), num(ltok)
        if ln < 1:
            raise CmdError("bad length '%s'" % ltok)
        if p + ln > len(self.buf.text):
            raise CmdError("range %d+%d beyond end (%d)" % (p, ln, len(self.buf.text)))
        return p, ln

    def done(self, node):
        self.say("node %d" % node.id)

    def pattern(self, tok):
        try:
            return compile_pattern(tok)
        except PatternError as e:
            raise CmdError("bad pattern: %s" % e)

    # -- commands ------------------------------------------------------------------------------------------------
    def c_load(self, rest):
        self.buf.reset(unescape(rest))
        self.hist.reset()
        self.say("loaded %d chars" % len(self.buf.text))

    def c_ins(self, args, rest):
        if not args:
            raise CmdError("usage: ins POS TEXT")
        p = self.pos(args[0])
        text = unescape(rest)
        if text == "":
            raise CmdError("nothing to insert")
        self.done(self.hist.commit([("i", p, text)], "ins@%d+%d" % (p, len(text))))

    def c_del(self, args):
        if len(args) != 2:
            raise CmdError("usage: del POS LEN")
        p, ln = self.span(args[0], args[1])
        self.done(self.hist.commit([("d", p, self.buf.text[p:p + ln])], "del@%d-%d" % (p, ln)))

    def c_rep(self, args, rest):
        if len(args) < 2:
            raise CmdError("usage: rep POS LEN TEXT")
        p, ln = self.span(args[0], args[1])
        text = unescape(rest)
        prims = [("d", p, self.buf.text[p:p + ln])] + ([("i", p, text)] if text else [])
        self.done(self.hist.commit(prims, "rep@%d-%d+%d" % (p, ln, len(text))))

    def c_show(self):
        if self.buf.text == "":
            self.say("(empty)")
            return
        for i, line in enumerate(self.buf.text.split("\n"), 1):
            self.say("%d|%s" % (i, line))

    def c_text(self):
        self.say('"%s"' % escape(self.buf.text))

    def c_mark(self, args):
        if len(args) not in (2, 3):
            raise CmdError("usage: mark NAME POS [left|right]")
        if not re.match(r"^[A-Za-z][A-Za-z0-9_]{0,15}$", args[0]):
            raise CmdError("bad mark name '%s'" % args[0])
        p = self.pos(args[1])
        g = C.DEFAULT_GRAVITY
        if len(args) == 3:
            if args[2] not in ("left", "right"):
                raise CmdError("bad gravity '%s'" % args[2])
            g = args[2]
        self.buf.marks[args[0]] = [p, g]
        self.say("mark %s=%d %s" % (args[0], p, g))

    def c_unmark(self, args):
        if len(args) != 1:
            raise CmdError("usage: unmark NAME")
        if args[0] not in self.buf.marks:
            raise CmdError("no such mark '%s'" % args[0])
        del self.buf.marks[args[0]]
        self.say("unmarked %s" % args[0])

    def c_marks(self):
        if not self.buf.marks:
            self.say("(no marks)")
        for name in sorted(self.buf.marks):
            p, g = self.buf.marks[name]
            self.say("%s=%d %s" % (name, p, g))

    def c_at(self, args):
        if len(args) != 1:
            raise CmdError("usage: at NAME")
        if args[0] not in self.buf.marks:
            raise CmdError("no such mark '%s'" % args[0])
        self.say(str(self.buf.marks[args[0]][0]))

    def c_undo(self, args):
        if len(args) > 1:
            raise CmdError("usage: undo [N]")
        n = num(args[0]) if args else 1
        if n < 1:
            raise CmdError("bad number '0'")
        if self.hist.cur.parent is None:
            raise CmdError("nothing to undo")
        self.hist.undo(n)
        self.say("node %d" % self.hist.cur.id)

    def c_redo(self, args):
        if len(args) > 1:
            raise CmdError("usage: redo [N]")
        n = num(args[0]) if args else 1
        if n < 1:
            raise CmdError("bad number '0'")
        if self.hist.next_child() is None:
            raise CmdError("nothing to redo")
        self.hist.redo(n)
        self.say("node %d" % self.hist.cur.id)

    def c_goto(self, args):
        if len(args) != 1:
            raise CmdError("usage: goto ID")
        n = num(args[0])
        if n >= len(self.hist.nodes):
            raise CmdError("no such node %d" % n)
        self.hist.goto(self.hist.nodes[n])
        self.say("node %d" % n)

    def c_tree(self):
        for l in self.hist.tree_lines():
            self.say(l)

    def c_find(self, args):
        if len(args) not in (1, 3) or (len(args) == 3 and args[1] != "from"):
            raise CmdError("usage: find PATTERN [from POS]")
        toks = self.pattern(args[0])
        start = self.pos(args[2]) if len(args) == 3 else 0
        m = find_from(toks, self.buf.text, start)
        self.say("not found" if m is None else "found %d %d" % m)

    def c_count(self, args):
        if len(args) != 1:
            raise CmdError("usage: count PATTERN")
        self.say(str(len(find_all(self.pattern(args[0]), self.buf.text))))

    def c_sub(self, args, rest, every):
        if not args:
            raise CmdError("usage: %s PATTERN TEXT" % ("suball" if every else "sub"))
        toks = self.pattern(args[0])
        text = unescape(rest)
        ms = find_all(toks, self.buf.text)
        if not every:
            ms = ms[:1]
        if not ms:
            self.say("0 replaced")
            return
        prims = []
        for s, ln in reversed(ms):
            if ln:
                prims.append(("d", s, self.buf.text[s:s + ln]))
            if text:
                prims.append(("i", s, text))
        # the removed text of each match is read from the current buffer: matches are processed right to left,
        # so earlier positions are still valid
        if every and not C.SUB_GROUP:
            for s, ln in reversed(ms):
                one = ([("d", s, self.buf.text[s:s + ln])] if ln else []) + ([("i", s, text)] if text else [])
                if not one:
                    continue
                self.hist.commit(one, "sub@%d-%d+%d" % (s, ln, len(text)))
            self.say("%d replaced, node %d" % (len(ms), self.hist.cur.id))
            return
        if not prims:
            self.say("%d replaced" % len(ms))
            return
        self.hist.commit(prims, "%s x%d" % ("suball" if every else "sub", len(ms)))
        self.say("%d replaced, node %d" % (len(ms), self.hist.cur.id))

    def c_yank(self, args):
        if len(args) != 2:
            raise CmdError("usage: yank POS LEN")
        p, ln = self.span(args[0], args[1])
        self.reg = self.buf.text[p:p + ln]
        self.say("yanked %d" % ln)

    def c_put(self, args):
        if len(args) != 1:
            raise CmdError("usage: put POS")
        if self.reg is None:
            raise CmdError("register is empty")
        p = self.pos(args[0])
        self.done(self.hist.commit([("i", p, self.reg)], "put@%d+%d" % (p, len(self.reg))))

    def run(self, raw):
        line = raw.strip()
        if not line or line.startswith("#"):
            return
        cmd, _, rest = line.partition(" ")
        args = rest.split()
        try:
            if cmd == "load":
                self.c_load(rest)
            elif cmd in ("ins", "rep", "sub", "suball"):
                # TEXT is what follows the arguments: 1 word (ins POS, sub PAT), 2 words (rep POS LEN)
                nargs = 2 if cmd == "rep" else 1
                head = rest.lstrip(" ")
                words, tail = [], head
                for _ in range(nargs):
                    w, _, tail = tail.partition(" ")
                    if w:
                        words.append(w)
                if cmd == "ins":
                    self.c_ins(words, tail)
                elif cmd == "rep":
                    self.c_rep(words, tail)
                else:
                    self.c_sub(words, tail, cmd == "suball")
            elif cmd == "del":
                self.c_del(args)
            elif cmd == "show":
                self.c_show()
            elif cmd == "text":
                self.c_text()
            elif cmd == "mark":
                self.c_mark(args)
            elif cmd == "unmark":
                self.c_unmark(args)
            elif cmd == "marks":
                self.c_marks()
            elif cmd == "at":
                self.c_at(args)
            elif cmd == "undo":
                self.c_undo(args)
            elif cmd == "redo":
                self.c_redo(args)
            elif cmd == "goto":
                self.c_goto(args)
            elif cmd == "tree":
                self.c_tree()
            elif cmd == "find":
                self.c_find(args)
            elif cmd == "count":
                self.c_count(args)
            elif cmd == "yank" and C.HAS_REGISTER:
                self.c_yank(args)
            elif cmd == "put" and C.HAS_REGISTER:
                self.c_put(args)
            else:
                raise CmdError("unknown command '%s'" % cmd)
        except CmdError as e:
            self.say("error: " + str(e))
            self.errors += 1


def main():
    ed = Editor()
    for raw in sys.stdin.read().split("\n"):
        ed.run(raw)
    sys.stdout.write("".join(l + "\n" for l in ed.out))
    return 1 if ed.errors else 0


if __name__ == "__main__":
    sys.exit(main())
