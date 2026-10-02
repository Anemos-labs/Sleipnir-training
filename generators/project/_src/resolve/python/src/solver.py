"""The resolver: a depth-first search with chronological backtracking over a queue of package names."""
import config as C


class LimitReached(Exception):
    pass


class State:
    def __init__(self):
        self.chosen = {}  # name -> Package
        self.reqs = {}  # name -> [(Constraint, who)] in the order the requirements arrived
        self.feats = {}  # name -> set of requested features
        self.queue = []  # names waiting for a decision, in order of first requirement
        self.queued = set()
        self.breaks = []  # (name, Constraint)

    def clone(self):
        s = State()
        s.chosen = dict(self.chosen)
        s.reqs = {k: list(v) for k, v in self.reqs.items()}
        s.feats = {k: set(v) for k, v in self.feats.items()}
        s.queue = list(self.queue)
        s.queued = set(self.queued)
        s.breaks = list(self.breaks)
        return s


class Solver:
    def __init__(self, index, wants, oldest, prefer):
        self.index = index
        self.wants = wants
        self.oldest = oldest
        self.prefer = prefer  # name -> Version preferred first
        self.attempts = 0
        self.dead = None  # message of the first dead end

    # -- requirements -------------------------------------------------------------------------------------------
    def apply(self, st, work):
        """Process (owner, Need) pairs first-in first-out; False if a chosen package cannot accept one."""
        while work:
            owner, need = work.pop(0)
            who = "%s %s" % (owner.name, owner.version.text)
            st.reqs.setdefault(need.dep, []).append((need.constraint, who))
            have = st.feats.setdefault(need.dep, set())
            new = set(need.feats) - have
            have |= new
            if need.dep in st.chosen:
                dp = st.chosen[need.dep]
                if not need.constraint.allows(dp.version):
                    return False
                if any(f not in dp.features for f in new):
                    return False
                work.extend((dp, n) for n in dp.needs if n.gate in new)
            elif need.dep not in st.queued:
                st.queued.add(need.dep)
                st.queue.append(need.dep)
        return True

    def candidates(self, st, name):
        cons = [c for c, _ in st.reqs.get(name, [])]
        locked = self.prefer.get(name)
        out = []
        for p in self.index.versions(name):
            if p.yanked and not (locked is not None and p.version == locked):
                continue
            if not all(c.allows(p.version) for c in cons):
                continue
            if any(t == name and c.allows(p.version) for t, c in st.breaks):
                continue
            if any(f not in p.features for f in st.feats.get(name, ())):
                continue
            out.append(p)
        if self.oldest:
            out.reverse()
        if locked is not None:
            out.sort(key=lambda p: 0 if p.version == locked else 1)  # stable: only moves the locked one to the front
        return out

    def choose(self, st, p):
        st.chosen[p.name] = p
        st.feats.setdefault(p.name, set())
        for target, c in p.breaks:
            if target in st.chosen and c.allows(st.chosen[target].version):
                return False
            st.breaks.append((target, c))
        return self.apply(st, [(p, n) for n in p.active_needs(st.feats[p.name])])

    # -- search ---------------------------------------------------------------------------------------------------
    def solve(self, st):
        if not st.queue:
            return st
        name = st.queue[0]
        if not self.index.versions(name):
            if self.dead is None:
                self.dead = "unknown package %s" % name
            return None
        for p in self.candidates(st, name):
            self.attempts += 1
            if self.attempts > C.LIMIT:
                raise LimitReached()
            s2 = st.clone()
            s2.queue.pop(0)
            if self.choose(s2, p):
                r = self.solve(s2)
                if r is not None:
                    return r
        if self.dead is None:
            needs = ", ".join("%s (%s)" % (c.text, who) for c, who in st.reqs.get(name, []))
            self.dead = "cannot resolve %s: needs %s" % (name, needs)
        return None

    def run(self):
        st = State()
        for name, cons, feats in self.wants:
            st.reqs.setdefault(name, []).append((cons, "root"))
            st.feats.setdefault(name, set()).update(feats)
            if name not in st.queued:
                st.queued.add(name)
                st.queue.append(name)
        return self.solve(st)
