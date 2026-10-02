"""typeset: lays a text document out on fixed-size pages."""
import re
import sys

import config as C
from blocks import DocError, parse, render
from paginate import paginate


def main(argv):
    opts = {"width": C.WIDTH, "height": C.HEIGHT, "orphans": C.ORPHANS, "widows": C.WIDOWS, "justify": False}
    ranges = {"width": (10, 120), "height": (4, 80), "orphans": (1, 4), "widows": (1, 4)}
    i = 0
    try:
        while i < len(argv):
            a = argv[i]
            name = a[2:]
            if a == "--justify" and C.JUSTIFY_OPT:
                opts["justify"] = True
                i += 1
            elif a in ("--width", "--height", "--orphans", "--widows"):
                if i + 1 >= len(argv):
                    raise ValueError("missing value for " + a)
                v = argv[i + 1]
                lo, hi = ranges[name]
                if not re.match(r"^[0-9]{1,3}$", v) or not lo <= int(v) <= hi:
                    raise ValueError("bad value '%s' for %s" % (v, a))
                opts[name] = int(v)
                i += 2
            else:
                raise ValueError("unknown option '%s'" % a)
    except ValueError as e:
        print("error: " + str(e))
        return 1
    try:
        blocks = parse(sys.stdin.read())
        for b in blocks:
            b.lines = render(b, opts["width"], opts["justify"])
            if b.kind == "figure" and b.height > opts["height"]:
                raise DocError("line %d: figure %s is taller than a page" % (b.line, b.name))
    except DocError as e:
        print("error: " + str(e))
        return 1
    pages = paginate(blocks, opts["height"], opts["orphans"], opts["widows"])
    out = []
    for n, page in enumerate(pages, 1):
        if n > 1:
            out.append("")
        out += page
        out.append("-- %d/%d --" % (n, len(pages)))
    sys.stdout.write("".join(l.rstrip() + "\n" for l in out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
