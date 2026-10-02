"""Readers for index.txt, project.txt and lock.txt."""
import config as C
from versions import NAME_RE, Constraint, Version


class FormatError(Exception):
    def __init__(self, where, line, msg):
        Exception.__init__(self, "%s:%d: %s" % (where, line, msg))


class Need:
    def __init__(self, dep, constraint, feats, gate):
        self.dep = dep
        self.constraint = constraint
        self.feats = feats  # features requested of the dependency (sorted tuple)
        self.gate = gate  # feature of the owner that must be enabled, or None


class Package:
    def __init__(self, name, version):
        self.name = name
        self.version = version
        self.needs = []
        self.breaks = []  # (name, Constraint)
        self.features = []  # declared, in order
        self.yanked = False

    def active_needs(self, enabled):
        return [n for n in self.needs if n.gate is None or n.gate in enabled]


class Index:
    def __init__(self):
        self.pkgs = {}  # name -> packages, newest first

    def versions(self, name):
        return self.pkgs.get(name, [])

    def find(self, name, version):
        for p in self.pkgs.get(name, []):
            if p.version == version:
                return p
        return None


def words(line):
    return line.split("#", 1)[0].split()


def features_of(tokens, where, n):
    feats = set()
    for t in tokens:
        if not t.startswith("+") or not NAME_RE.match(t[1:]):
            raise FormatError(where, n, "bad name '%s'" % t.lstrip("+"))
        feats.add(t[1:])
    return tuple(sorted(feats))


def need_line(w, n):
    """needs NAME CONSTRAINT [+FEATURE...] [if FEATURE] -> (dep, constraint, feats, gate)."""
    gate = None
    if C.FEATURES and len(w) >= 3 and w[-2] == "if":
        gate = w[-1]
        w = w[:-2]
    if len(w) < 3 or (not C.FEATURES and len(w) != 3):
        raise FormatError("index.txt", n, "bad line")
    for name in [w[1]] + ([gate] if gate else []):
        if not NAME_RE.match(name):
            raise FormatError("index.txt", n, "bad name '%s'" % name)
    try:
        cons = Constraint(w[2])
    except ValueError:
        raise FormatError("index.txt", n, "bad constraint '%s'" % w[2])
    return w[1], cons, features_of(w[3:], "index.txt", n), gate


def read_index(text):
    index = Index()
    cur = None
    allp = []
    for n, line in enumerate(text.split("\n"), 1):
        w = words(line)
        if not w:
            continue
        d = w[0]
        if d == "pkg":
            if len(w) != 3:
                raise FormatError("index.txt", n, "bad line")
            if not NAME_RE.match(w[1]):
                raise FormatError("index.txt", n, "bad name '%s'" % w[1])
            try:
                ver = Version(w[2])
            except ValueError:
                raise FormatError("index.txt", n, "bad version '%s'" % w[2])
            if any(p.name == w[1] and p.version == ver for p in allp):
                raise FormatError("index.txt", n, "duplicate package %s %s" % (w[1], w[2]))
            cur = Package(w[1], ver)
            allp.append(cur)
            continue
        known = ["needs", "yanked"] + (["breaks"] if C.BREAKS else []) + (["feature"] if C.FEATURES else [])
        if d not in known:
            raise FormatError("index.txt", n, "unknown directive '%s'" % d)
        if cur is None:
            raise FormatError("index.txt", n, "'%s' outside a package block" % d)
        if d == "yanked":
            if len(w) != 1:
                raise FormatError("index.txt", n, "bad line")
            cur.yanked = True
        elif d == "feature":
            if len(w) != 2:
                raise FormatError("index.txt", n, "bad line")
            if not NAME_RE.match(w[1]):
                raise FormatError("index.txt", n, "bad name '%s'" % w[1])
            if w[1] in cur.features:
                raise FormatError("index.txt", n, "duplicate feature '%s'" % w[1])
            cur.features.append(w[1])
        elif d == "breaks":
            if len(w) != 3:
                raise FormatError("index.txt", n, "bad line")
            if not NAME_RE.match(w[1]):
                raise FormatError("index.txt", n, "bad name '%s'" % w[1])
            try:
                cur.breaks.append((w[1], Constraint(w[2])))
            except ValueError:
                raise FormatError("index.txt", n, "bad constraint '%s'" % w[2])
        else:
            dep, cons, feats, gate = need_line(w, n)
            if gate is not None and gate not in cur.features:
                raise FormatError("index.txt", n, "undeclared feature '%s'" % gate)
            cur.needs.append(Need(dep, cons, feats, gate))
    for p in allp:
        index.pkgs.setdefault(p.name, []).append(p)
    for lst in index.pkgs.values():
        lst.sort(key=lambda p: p.version.key(), reverse=True)
    return index


def read_project(text):
    wants = []  # (name, Constraint, feats)
    for n, line in enumerate(text.split("\n"), 1):
        w = words(line)
        if not w:
            continue
        if w[0] != "want":
            raise FormatError("project.txt", n, "unknown directive '%s'" % w[0])
        if len(w) < 3 or (not C.FEATURES and len(w) != 3):
            raise FormatError("project.txt", n, "bad line")
        if not NAME_RE.match(w[1]):
            raise FormatError("project.txt", n, "bad name '%s'" % w[1])
        try:
            cons = Constraint(w[2])
        except ValueError:
            raise FormatError("project.txt", n, "bad constraint '%s'" % w[2])
        wants.append((w[1], cons, features_of(w[3:], "project.txt", n)))
    return wants


def read_lock(text):
    """name -> (Version, set of enabled features)."""
    out = {}
    for n, line in enumerate(text.split("\n"), 1):
        w = words(line)
        if not w:
            continue
        if len(w) not in (2, 3) or (len(w) == 3 and not C.FEATURES):
            raise FormatError("lock.txt", n, "bad line")
        if not NAME_RE.match(w[0]):
            raise FormatError("lock.txt", n, "bad name '%s'" % w[0])
        try:
            ver = Version(w[1])
        except ValueError:
            raise FormatError("lock.txt", n, "bad version '%s'" % w[1])
        feats = features_of(["+" + f for f in w[2].split(",")] if len(w) == 3 else [], "lock.txt", n)
        if w[0] in out:
            raise FormatError("lock.txt", n, "duplicate package '%s'" % w[0])
        out[w[0]] = (ver, set(feats))
    return out
