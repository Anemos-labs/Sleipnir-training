"""Hidden python helper: values that count what is done to them (placed in tests/counting.py)."""

TEXT = '''"""Operation counting for performance tests."""


class BudgetExceeded(Exception):
    pass


class Ops:
    eq = 0
    lt = 0
    hash = 0
    reads = 0
    budget = None

    @classmethod
    def reset(cls):
        cls.eq = cls.lt = cls.hash = cls.reads = 0

    @classmethod
    def total(cls):
        return cls.eq + cls.lt + cls.hash + cls.reads

    @classmethod
    def tick(cls):
        if cls.budget is not None and cls.eq + cls.lt + cls.hash + cls.reads > cls.budget:
            raise BudgetExceeded()


class Tracked:
    """A value whose equality, ordering and hashing are counted."""

    __slots__ = ("v",)

    def __init__(self, v):
        self.v = v

    def __eq__(self, other):
        Ops.eq += 1
        Ops.tick()
        return isinstance(other, Tracked) and self.v == other.v

    def __ne__(self, other):
        Ops.eq += 1
        Ops.tick()
        return not (isinstance(other, Tracked) and self.v == other.v)

    def __lt__(self, other):
        Ops.lt += 1
        Ops.tick()
        return self.v < other.v

    def __le__(self, other):
        Ops.lt += 1
        Ops.tick()
        return self.v <= other.v

    def __gt__(self, other):
        Ops.lt += 1
        Ops.tick()
        return self.v > other.v

    def __ge__(self, other):
        Ops.lt += 1
        Ops.tick()
        return self.v >= other.v

    def __hash__(self):
        Ops.hash += 1
        Ops.tick()
        return hash(self.v)

    def __repr__(self):
        return "T(%r)" % (self.v,)


class CountingSeq:
    """A read-only sequence that counts element reads."""

    def __init__(self, data):
        self._data = list(data)

    def __len__(self):
        return len(self._data)

    def __getitem__(self, i):
        if isinstance(i, slice):
            Ops.reads += len(range(*i.indices(len(self._data))))
            Ops.tick()
            return self._data[i]
        Ops.reads += 1
        Ops.tick()
        return self._data[i]

    def __iter__(self):
        for x in self._data:
            Ops.reads += 1
            Ops.tick()
            yield x


class ShiftList(list):
    """A list that counts the element moves and scans that front operations cost."""

    def pop(self, index=-1):
        if index != -1 and index != len(self) - 1:
            Ops.reads += len(self) - (index if index >= 0 else len(self) + index) - 1
            Ops.tick()
        return super().pop(index)

    def insert(self, index, value):
        Ops.reads += max(0, len(self) - index)
        Ops.tick()
        super().insert(index, value)

    def remove(self, value):
        Ops.reads += len(self)
        Ops.tick()
        super().remove(value)

    def __contains__(self, value):
        Ops.reads += len(self)
        Ops.tick()
        return super().__contains__(value)

    def index(self, value, *args):
        Ops.reads += len(self)
        Ops.tick()
        return super().index(value, *args)

    def __getitem__(self, i):
        if isinstance(i, slice):
            Ops.reads += len(range(*i.indices(len(self))))
            Ops.tick()
            return ShiftList(list.__getitem__(self, i))
        return list.__getitem__(self, i)


class Counted:
    """A callable collaborator whose calls are counted (as reads)."""

    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *args):
        Ops.reads += 1
        Ops.tick()
        return self.fn(*args)


def plain(x):
    """Replace Tracked values by their payload, recursively (for comparing results with an oracle)."""
    if isinstance(x, Tracked):
        return x.v
    if isinstance(x, list):
        return [plain(i) for i in x]
    if isinstance(x, tuple):
        return tuple(plain(i) for i in x)
    if isinstance(x, dict):
        return {plain(k): plain(v) for k, v in x.items()}
    return x
'''
