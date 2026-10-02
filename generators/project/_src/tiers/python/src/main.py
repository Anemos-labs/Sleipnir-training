"""tiers: a scripted tiered key-value store (memtable, runs, compaction)."""
import re
import sys

import config as C
from store import TOMB, Store

KEY = re.compile(r"^[a-z0-9_]{1,8}$")
VAL = re.compile(r"^[A-Za-z0-9_.-]{1,12}$")


class CmdError(Exception):
    pass


def key_arg(tok):
    if not KEY.match(tok):
        raise CmdError("bad key '%s'" % tok)
    return tok


def main():
    out = []
    errors = [0]

    def say(line):
        out.append(line)

    st = Store(say)
    for raw in sys.stdin.read().split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        w = line.split()
        cmd, args = w[0], w[1:]
        try:
            if cmd == "put":
                if len(args) != 2:
                    raise CmdError("usage: put KEY VALUE")
                key_arg(args[0])
                if not VAL.match(args[1]):
                    raise CmdError("bad value '%s'" % args[1])
                st.write(args[0], args[1])
            elif cmd == "del":
                if len(args) != 1:
                    raise CmdError("usage: del KEY")
                st.write(key_arg(args[0]), TOMB)
            elif cmd == "get":
                if len(args) != 1:
                    raise CmdError("usage: get KEY")
                key = key_arg(args[0])
                state, src, probed, v = st.lookup(key)
                if state == "live":
                    say("%s = %s (%s, %d probed)" % (key, v, src, probed))
                elif state == "deleted":
                    say("%s deleted (%s, %d probed)" % (key, src, probed))
                else:
                    say("%s not found (%d probed)" % (key, probed))
            elif cmd == "scan":
                if len(args) != 2:
                    raise CmdError("usage: scan LO HI")
                lo, hi = key_arg(args[0]), key_arg(args[1])
                if lo >= hi:
                    raise CmdError("empty range")
                rows = [(k, v) for k, v in st.view().items() if lo <= k < hi]
                for k, v in rows:
                    say("%s = %s" % (k, v))
                say("%d keys" % len(rows))
            elif cmd == "flush":
                if args:
                    raise CmdError("usage: flush")
                if not st.flush():
                    say("memtable is empty")
            elif cmd == "compact":
                if args == ["all"] and C.HAS_ALL:
                    if not st.compact_all():
                        say("nothing to compact")
                elif not args:
                    if not st.compact():
                        say("nothing to compact")
                else:
                    raise CmdError("usage: compact" + (" [all]" if C.HAS_ALL else ""))
            elif cmd == "dump":
                if args:
                    raise CmdError("usage: dump")
                say("memtable: " + (" ".join("%s=%s" % (k, "<del>" if v is TOMB else v) for k, v in sorted(st.mem.items())) or "-"))
                for i, level in enumerate(st.levels):
                    say("L%d: " % i + (" ".join("#%d[%s..%s:%d]" % (r.id, r.lo, r.hi, len(r.entries)) for r in reversed(level)) or "-"))
            elif cmd == "stats":
                if args:
                    raise CmdError("usage: stats")
                runs, entries, tombs, live = st.stats()
                say("runs=%d entries=%d tombstones=%d live=%d next=%d" % (runs, entries, tombs, live, st.next_id))
            else:
                raise CmdError("unknown command '%s'" % cmd)
        except CmdError as e:
            say("error: " + str(e))
            errors[0] += 1
    sys.stdout.write("".join(l + "\n" for l in out))
    return 1 if errors[0] else 0


if __name__ == "__main__":
    sys.exit(main())
