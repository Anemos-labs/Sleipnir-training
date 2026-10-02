"""The actions a rule can run.  Every action is a pure function of the contents of the rule's inputs."""
import re

import config as C

INT_RE = re.compile(r"^-?[0-9]{1,9}$")
UINT_RE = re.compile(r"^[0-9]{1,9}$")
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


class ActionError(Exception):
    """An action that fails; the message is shown in the `fail` line."""


def split_lines(text):
    parts = text.split("\n")
    if parts[-1] == "":
        parts.pop()
    return parts


def ascii_upper(text):
    return "".join(chr(ord(c) - 32) if "a" <= c <= "z" else c for c in text)


def ascii_lower(text):
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in text)


def total(text):
    return sum(int(tok) for tok in text.split() if INT_RE.match(tok))


def valid(name, args):
    """True if `name` is an enabled action that accepts `args`."""
    if name not in C.ACTIONS:
        return False, "unknown action '%s'" % name
    ok = True
    if name in ("head", "cap"):
        ok = len(args) == 1 and UINT_RE.match(args[0]) is not None
    elif name in ("grep", "failif"):
        ok = len(args) == 1
    elif name == "tag":
        ok = len(args) == 1 and NAME_RE.match(args[0]) is not None
    elif name == "const":
        ok = True
    else:
        ok = len(args) == 0
    if not ok:
        return False, "bad arguments for '%s'" % name
    return True, ""


def run(name, args, inputs):
    text = "\n".join(inputs)
    if name == "cat":
        return text
    if name == "upper":
        return ascii_upper(text)
    if name == "lower":
        return ascii_lower(text)
    if name == "rev":
        return text[::-1]
    if name == "count":
        return str(len(text))
    if name == "lines":
        return str(len(split_lines(text)))
    if name == "head":
        return "\n".join(split_lines(text)[: int(args[0])])
    if name == "sort":
        return "\n".join(sorted(split_lines(text)))
    if name == "uniq":
        out = []
        for ln in split_lines(text):
            if not out or out[-1] != ln:
                out.append(ln)
        return "\n".join(out)
    if name == "grep":
        return "\n".join(ln for ln in split_lines(text) if args[0] in ln)
    if name == "tag":
        return "<%s>%s</%s>" % (args[0], text, args[0])
    if name == "sum":
        return str(total(text))
    if name == "cap":
        return str(min(total(text), int(args[0])))
    if name == "const":
        return " ".join(args)
    if name == "failif":
        if args[0] in text:
            raise ActionError("found " + args[0])
        return text
    if name == "fail":
        raise ActionError("always fails")
    raise ActionError("unknown action")
