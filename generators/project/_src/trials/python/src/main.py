"""trials: runs a suite of tests with scoped fixtures from suite.txt."""
import re
import sys

import config as C
from runner import Runner
from suite import SuiteError, read_suite


def main(argv):
    opts = {"only": None, "fail_fast": False, "retries": 0, "skip_slow": False, "list": False}
    i = 0
    try:
        while i < len(argv):
            a = argv[i]
            if a == "--only":
                if i + 1 >= len(argv):
                    raise ValueError("missing value for --only")
                opts["only"] = argv[i + 1]
                i += 2
            elif a == "--retries" and C.HAS_RETRIES:
                if i + 1 >= len(argv):
                    raise ValueError("missing value for --retries")
                if not re.match(r"^[0-5]$", argv[i + 1]):
                    raise ValueError("bad value '%s' for --retries" % argv[i + 1])
                opts["retries"] = int(argv[i + 1])
                i += 2
            elif a == "--fail-fast":
                opts["fail_fast"] = True
                i += 1
            elif a == "--skip-slow" and C.HAS_SKIP_SLOW:
                opts["skip_slow"] = True
                i += 1
            elif a == "--list":
                opts["list"] = True
                i += 1
            else:
                raise ValueError("unknown option '%s'" % a)
    except ValueError as e:
        print("error: " + str(e))
        return 1
    try:
        with open("suite.txt", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        print("error: cannot read suite.txt")
        return 1
    try:
        fixtures, tests, modules = read_suite(text)
    except SuiteError as e:
        print("error: " + str(e))
        return 1
    out = []
    runner = Runner(fixtures, tests, modules, opts, out.append)
    if opts["list"]:
        for t, name, _ in runner.expanded():
            if opts["only"] is None or opts["only"] in name:
                out.append("%s/%s" % (t.module, name) + ("  [%s]" % " ".join(t.marks) if t.marks else ""))
        status = 0
    else:
        status = 1 if runner.run() else 0
    sys.stdout.write("".join(l + "\n" for l in out))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
