"""`check` (validate a lock against the index and the project) and `tree` (print the locked dependency tree)."""
import config as C


def fmt_feats(feats):
    return ",".join(sorted(feats))


def check(index, wants, lock):
    out = []
    for name, cons, feats in wants:
        if name not in lock:
            out.append("problem: root wants %s %s but %s is not locked" % (name, cons.text, name))
            continue
        ver, enabled = lock[name]
        if not cons.allows(ver):
            out.append("problem: root wants %s %s but locked %s is %s" % (name, cons.text, name, ver.text))
        for f in feats:
            if f not in enabled:
                out.append("problem: root wants %s +%s but the lock does not enable it" % (name, f))
    for name in sorted(lock):
        ver, enabled = lock[name]
        pkg = index.find(name, ver)
        if pkg is None:
            out.append("problem: %s %s is not in the index" % (name, ver.text))
            continue
        for f in sorted(enabled):
            if f not in pkg.features:
                out.append("problem: %s %s has no feature %s" % (name, ver.text, f))
        for need in pkg.active_needs(enabled):
            if need.dep not in lock:
                out.append("problem: %s %s needs %s %s but %s is not locked" % (name, ver.text, need.dep, need.constraint.text, need.dep))
                continue
            dver, denabled = lock[need.dep]
            if not need.constraint.allows(dver):
                out.append("problem: %s %s needs %s %s but locked %s is %s" % (name, ver.text, need.dep, need.constraint.text, need.dep, dver.text))
            for f in need.feats:
                if f not in denabled:
                    out.append("problem: %s %s needs %s +%s but the lock does not enable it" % (name, ver.text, need.dep, f))
        for target, c in pkg.breaks:
            if target in lock and c.allows(lock[target][0]):
                out.append("problem: %s %s breaks %s %s but locked %s is %s" % (name, ver.text, target, c.text, target, lock[target][0].text))
    if C.CHECK_UNUSED:
        reach = reachable(index, wants, lock)
        for name in sorted(lock):
            if name not in reach:
                out.append("problem: %s is locked but nothing needs it" % name)
    return out


def deps_of(index, name, lock):
    """Names a locked package depends on (active needs of its locked version), sorted."""
    ver, enabled = lock[name]
    pkg = index.find(name, ver)
    if pkg is None:
        return []
    return sorted({n.dep for n in pkg.active_needs(enabled)})


def reachable(index, wants, lock):
    seen = set()
    todo = [w[0] for w in wants]
    while todo:
        n = todo.pop()
        if n in seen or n not in lock:
            continue
        seen.add(n)
        todo.extend(deps_of(index, n, lock))
    return seen


def tree(index, wants, lock):
    lines = ["root"]
    shown = set()

    def label(name):
        if name not in lock:
            return "%s (not locked)" % name
        ver, enabled = lock[name]
        return "%s %s" % (name, ver.text) + (" [%s]" % fmt_feats(enabled) if enabled else "")

    def walk(name, depth):
        text = label(name)
        if name in lock and name in shown:
            lines.append("  " * depth + text + " (*)")
            return
        lines.append("  " * depth + text)
        if name not in lock:
            return
        shown.add(name)
        for d in deps_of(index, name, lock):
            walk(d, depth + 1)

    for name in sorted({w[0] for w in wants}):
        walk(name, 1)
    return lines
