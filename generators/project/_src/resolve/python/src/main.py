"""resolver command line: lock, upgrade, tree, check."""
import os
import sys

import config as C
from checker import check, fmt_feats, tree
from files import FormatError, read_index, read_lock, read_project
from solver import LimitReached, Solver


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def fail(msg):
    print("error: " + msg)
    return 1


def load(lock_mode):
    """(index, wants, lock) or an error string. lock_mode: "none" (lock.txt is not read), "optional" or "required"."""
    text = read("index.txt")
    if text is None:
        return "cannot read index.txt"
    index = read_index(text)
    text = read("project.txt")
    if text is None:
        return "cannot read project.txt"
    wants = read_project(text)
    lock = None
    if lock_mode != "none":
        ltext = read("lock.txt")
        if ltext is None:
            if lock_mode == "required":
                return "cannot read lock.txt"
        else:
            lock = read_lock(ltext)
    return index, wants, lock


def lock_lines(st):
    lines = []
    for name in sorted(st.chosen):
        p = st.chosen[name]
        feats = st.feats.get(name, set())
        lines.append("%s %s" % (name, p.version.text) + (" " + fmt_feats(feats) if feats else ""))
    return lines


def resolve(index, wants, oldest, prefer):
    s = Solver(index, wants, oldest, prefer)
    try:
        st = s.run()
    except LimitReached:
        return fail("search limit reached")
    if st is None:
        return fail(s.dead)
    lines = lock_lines(st)
    with open("lock.txt", "w", encoding="utf-8") as f:
        f.write("".join(l + "\n" for l in lines))
    for l in lines:
        print(l)
    print("locked %d packages" % len(lines))
    return 0


def cmd_lock(args):
    oldest = fresh = False
    for a in args:
        if a == "--oldest" and C.OLDEST_OPT:
            oldest = True
        elif a == "--fresh" and C.STICKY:
            fresh = True
        else:
            return fail("unknown option '%s'" % a) if a.startswith("-") else fail("usage: %s lock [OPTION...]" % C.TOOL)
    r = load("optional" if C.STICKY and not fresh else "none")
    if isinstance(r, str):
        return fail(r)
    index, wants, lock = r
    prefer = {}
    if C.STICKY and not fresh and lock:
        prefer = {n: v for n, (v, _) in lock.items()}
    return resolve(index, wants, oldest, prefer)


def cmd_upgrade(args):
    if not args:
        return fail("usage: %s upgrade NAME..." % C.TOOL)
    r = load("required")
    if isinstance(r, str):
        return fail(r)
    index, wants, lock = r
    for n in args:
        if n not in lock:
            return fail("%s is not locked" % n)
    prefer = {n: v for n, (v, _) in lock.items() if n not in args}
    return resolve(index, wants, False, prefer)


def cmd_tree(args):
    if args:
        return fail("usage: %s tree" % C.TOOL)
    r = load("required")
    if isinstance(r, str):
        return fail(r)
    index, wants, lock = r
    for l in tree(index, wants, lock):
        print(l)
    return 0


def cmd_check(args):
    if args:
        return fail("usage: %s check" % C.TOOL)
    r = load("required")
    if isinstance(r, str):
        return fail(r)
    index, wants, lock = r
    problems = check(index, wants, lock)
    for p in problems:
        print(p)
    if problems:
        print("FAILED: %d problems" % len(problems))
        return 1
    print("ok: %d packages" % len(lock))
    return 0


def main(argv):
    if not argv:
        return fail("usage: %s COMMAND [ARGS]" % C.TOOL)
    table = {"lock": cmd_lock, "tree": cmd_tree, "check": cmd_check}
    if C.STICKY:
        table["upgrade"] = cmd_upgrade
    fn = table.get(argv[0])
    if fn is None:
        return fail("unknown command '%s'" % argv[0])
    try:
        return fn(argv[1:])
    except FormatError as e:
        return fail(str(e))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
