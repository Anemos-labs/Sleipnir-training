"""The tiered store: a memtable, levels of immutable sorted runs, flushes and compactions."""
import config as C

TOMB = None  # a deleted key is stored as None


class Run:
    def __init__(self, rid, entries):
        self.id = rid
        self.entries = dict(sorted(entries.items()))  # key -> value or TOMB
        keys = list(self.entries)
        self.lo = keys[0]
        self.hi = keys[-1]


class Store:
    def __init__(self, say):
        self.say = say
        self.mem = {}
        self.levels = [[] for _ in range(C.LEVELS)]  # each level: runs, oldest first
        self.next_id = 1

    # -- writes ---------------------------------------------------------------------------------------------------
    def write(self, key, value):
        self.mem[key] = value
        if len(self.mem) >= C.MEM_LIMIT:
            self.flush()

    def flush(self):
        if not self.mem:
            return False
        run = Run(self.next_id, self.mem)
        self.next_id += 1
        self.levels[0].append(run)
        self.mem = {}
        self.say("flush #%d (%d entries)" % (run.id, len(run.entries)))
        self.cascade()
        return True

    # -- compaction -----------------------------------------------------------------------------------------------
    def limit(self, i):
        return C.L0_LIMIT if i == 0 else C.FANOUT

    def merge_level(self, i):
        runs = self.levels[i]
        k = len(runs) if C.MERGE == "all" else min(2, len(runs))
        take, rest = runs[:k], runs[k:]  # a level lists its runs oldest first
        last = len(self.levels) - 1
        target = min(i + 1, last)
        drop = all(not lv for lv in self.levels[i + 1:]) if C.DROP == "deep-empty" else i == last
        merged = {}
        for run in take:
            merged.update(run.entries)  # newer runs overwrite older ones
        if drop:
            merged = {key: v for key, v in merged.items() if v is not TOMB}
        new = None
        if merged:
            new = Run(self.next_id, merged)
            self.next_id += 1
        if target == i:
            self.levels[i] = ([new] if new else []) + rest  # the merged run takes the place of the runs it replaces
        else:
            self.levels[i] = rest
            if new:
                self.levels[target].append(new)
        if new:
            self.say("compact L%d (%d runs) -> L%d run #%d (%d entries)" % (i, len(take), target, new.id, len(new.entries)))
        else:
            self.say("compact L%d (%d runs) -> nothing" % (i, len(take)))

    def cascade(self):
        while True:
            for i in range(len(self.levels)):
                if len(self.levels[i]) >= self.limit(i):
                    self.merge_level(i)
                    break
            else:
                return

    def compact(self):
        """Merge the lowest non-empty level whatever its size, then cascade."""
        for i in range(len(self.levels)):
            if self.levels[i]:
                self.merge_level(i)
                self.cascade()
                return True
        return False

    def compact_all(self):
        runs = [r for lv in reversed(self.levels) for r in lv]  # oldest first
        if not runs:
            return False
        merged = {}
        for run in runs:
            merged.update(run.entries)
        merged = {k: v for k, v in merged.items() if v is not TOMB}
        last = len(self.levels) - 1
        self.levels = [[] for _ in self.levels]
        if merged:
            run = Run(self.next_id, merged)
            self.next_id += 1
            self.levels[last].append(run)
            self.say("compact all (%d runs) -> L%d run #%d (%d entries)" % (len(runs), last, run.id, len(run.entries)))
        else:
            self.say("compact all (%d runs) -> nothing" % len(runs))
        return True

    # -- reads ----------------------------------------------------------------------------------------------------
    def lookup(self, key):
        """(state, source, probed): state is 'live', 'deleted' or 'missing'."""
        if key in self.mem:
            return ("deleted" if self.mem[key] is TOMB else "live"), "memtable", 0, self.mem[key]
        probed = 0
        for i, level in enumerate(self.levels):
            for run in reversed(level):
                if C.RANGE_FILTER and not (run.lo <= key <= run.hi):
                    continue
                probed += 1
                if key in run.entries:
                    v = run.entries[key]
                    return ("deleted" if v is TOMB else "live"), "L%d #%d" % (i, run.id), probed, v
        return "missing", "", probed, None

    def view(self):
        """All live keys with their values, merged newest first."""
        seen = {}
        for k, v in self.mem.items():
            seen[k] = v
        for level in self.levels:
            for run in reversed(level):
                for k, v in run.entries.items():
                    seen.setdefault(k, v)
        return {k: v for k, v in sorted(seen.items()) if v is not TOMB}

    def stats(self):
        runs = [r for lv in self.levels for r in lv]
        entries = sum(len(r.entries) for r in runs)
        tombs = sum(1 for r in runs for v in r.entries.values() if v is TOMB)
        return len(runs), entries, tombs, len(self.view())
