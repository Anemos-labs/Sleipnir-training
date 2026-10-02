"""Command-line front end: reads calendar.txt and a script on standard input."""
import sys

import config as C
from calfile import CalendarError, read_calendar
from commands import Commands
from model import DateError, Model


def main():
    try:
        with open("calendar.txt", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        print("error: cannot read calendar.txt")
        return 1
    try:
        cal = read_calendar(text)
    except CalendarError as e:
        print("error: " + str(e))
        return 1
    cmds = Commands(Model(cal))
    table = {"date": cmds.date, "add": cmds.add, "diff": cmds.diff, "nth": cmds.nth, "next": cmds.next}
    if C.HAS_SERIAL:
        table["serial"] = cmds.serial
    if C.HAS_YEAR:
        table["year"] = cmds.year
    status = 0
    for raw in sys.stdin.read().split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        toks = line.split()
        fn = table.get(toks[0])
        try:
            if fn is None:
                raise DateError("unknown command '%s'" % toks[0])
            for out in fn(toks[1:]):
                print(out)
        except DateError as e:
            print("error: " + str(e))
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
