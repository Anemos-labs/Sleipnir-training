"""Versions and constraints."""
import re

import config as C

NUM = r"(0|[1-9][0-9]{0,5})"
VERSION_RE = re.compile(r"^%s\.%s\.%s(?:-([a-z]+[0-9]*))?$" % (NUM, NUM, NUM))
PARTIAL_RE = re.compile(r"^%s(?:\.%s)?(?:\.%s)?(?:-([a-z]+[0-9]*))?$" % (NUM, NUM, NUM))
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")


class Version:
    def __init__(self, text):
        m = VERSION_RE.match(text)
        if not m or (m.group(4) and not C.TAGS):
            raise ValueError(text)
        self.text = text
        self.nums = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        self.tag = m.group(4)

    def key(self):
        # a version with a tag sorts below the same numbers without one; tags compare as plain text
        return (self.nums, 1 if self.tag is None else 0, self.tag or "")

    def __eq__(self, other):
        return self.key() == other.key()

    def __hash__(self):
        return hash(self.key())


def parse_partial(text):
    """'1', '1.2', '1.2.3', '1.2.3-rc1' -> Version (missing numbers are 0). A tag needs all three numbers."""
    m = PARTIAL_RE.match(text)
    if not m or (m.group(4) and (m.group(3) is None or not C.TAGS)):
        return None
    return Version("%s.%s.%s" % (m.group(1), m.group(2) or "0", m.group(3) or "0") + ("-" + m.group(4) if m.group(4) else ""))


def upper_bound(op, v):
    """Exclusive upper bound (as numbers) of the clauses ^ and ~."""
    M, m, p = v.nums
    if op == "~":
        return (M, m + 1, 0)
    if M > 0 or not C.CARET_ZERO:
        return (M + 1, 0, 0)
    if m > 0:
        return (0, m + 1, 0)
    return (0, 0, p + 1)


class Constraint:
    """A comma-separated list of clauses that must all hold."""

    def __init__(self, text):
        self.text = text
        self.clauses = [self._clause(part) for part in text.split(",")]

    @staticmethod
    def _clause(part):
        if part == "*":
            if "*" not in C.OPS:
                raise ValueError(part)
            return ("*", None)
        for op in (">=", "<=", "!=", ">", "<", "=", "^", "~"):
            if part.startswith(op):
                v = parse_partial(part[len(op):])
                if v is None or op not in C.OPS:
                    raise ValueError(part)
                return (op, v)
        v = parse_partial(part)
        if v is None:
            raise ValueError(part)
        return ("=", v)

    def allows(self, ver):
        k = ver.key()
        for op, v in self.clauses:
            if op == "*":
                continue
            if op == ">=" and not k >= v.key():
                return False
            if op == ">" and not k > v.key():
                return False
            if op == "<=" and not k <= v.key():
                return False
            if op == "<" and not k < v.key():
                return False
            if op == "=" and k != v.key():
                return False
            if op == "!=" and k == v.key():
                return False
            if op in ("^", "~") and not (k >= v.key() and ver.nums < upper_bound(op, v)):
                return False
        return True
