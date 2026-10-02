"""API migration inside Python: a legacy python-2 package must run on python 3.

Each task is a package assembled from small *units*; every unit has a python-2 text (the start repository) and a
python-3 text (the reference solution). The py2 texts are never executed: expected values come from running the py3 text
on the listed calls, so the behaviour that matters (integer vs true division, rounding, bytes vs text, ordering of dict views,
lazy ``map``/``filter``/``zip``, removed special methods) is pinned by the tests and documented in the README.
"""
import json

from fx import Task, dd, family

from ._portlib import run_local

UNITS = {}


def unit(key, doc, py2, py3, calls):
    UNITS[key] = dict(key=key, doc=doc, py2="# legacy python-2 module (fx: nocompile)\n" + dd(py2), py3=dd(py3), calls=calls)


unit("ledger", [
    "`ledger_lines(pairs)`: add up `(sku, qty)` pairs per sku and return `\"sku=qty\"` lines sorted by sku.",
    "`ledger_total(pairs)`: the sum of all quantities as an integer.",
    "`ledger_dump(pairs)`: the text a report printer would print: one `sku=qty` line per sku (each ending in a newline) and then `total: <n>` **without** a trailing newline.",
    "`spread(n)`: `[0, 3, 6, ...]` with `n` entries.",
], r'''
    # -*- coding: utf-8 -*-
    """Stock ledger for a seed library."""
    import StringIO


    class Ledger(object):
        def __init__(self):
            self.lots = {}

        def add(self, sku, qty):
            if self.lots.has_key(sku):
                self.lots[sku] += qty
            else:
                self.lots[sku] = qty

        def lines(self):
            return ["%s=%d" % (sku, qty) for sku, qty in sorted(self.lots.iteritems())]

        def total(self):
            n = 0L
            for qty in self.lots.itervalues():
                n += qty
            return n


    def _fill(pairs):
        ledger = Ledger()
        for sku, qty in pairs:
            ledger.add(sku, qty)
        return ledger


    def ledger_lines(pairs):
        return _fill(pairs).lines()


    def ledger_total(pairs):
        return _fill(pairs).total()


    def ledger_dump(pairs):
        out = StringIO.StringIO()
        ledger = _fill(pairs)
        for line in ledger.lines():
            print >>out, line
        print >>out, "total:", ledger.total(),
        return out.getvalue()


    def spread(n):
        return [i * 3 for i in xrange(n)]
''', r'''
    """Stock ledger for a seed library."""
    import io


    class Ledger(object):
        def __init__(self):
            self.lots = {}

        def add(self, sku, qty):
            if sku in self.lots:
                self.lots[sku] += qty
            else:
                self.lots[sku] = qty

        def lines(self):
            return ["%s=%d" % (sku, qty) for sku, qty in sorted(self.lots.items())]

        def total(self):
            n = 0
            for qty in self.lots.values():
                n += qty
            return n


    def _fill(pairs):
        ledger = Ledger()
        for sku, qty in pairs:
            ledger.add(sku, qty)
        return ledger


    def ledger_lines(pairs):
        return _fill(pairs).lines()


    def ledger_total(pairs):
        return _fill(pairs).total()


    def ledger_dump(pairs):
        out = io.StringIO()
        ledger = _fill(pairs)
        for line in ledger.lines():
            print(line, file=out)
        print("total:", ledger.total(), end="", file=out)
        return out.getvalue()


    def spread(n):
        return [i * 3 for i in range(n)]
''', ["m.ledger_lines([('b', 2), ('a', 1), ('b', 5)])", "m.ledger_lines([])", "m.ledger_total([('x', 10), ('y', 20), ('x', -5)])", "m.ledger_dump([('b', 2), ('a', 1)])",
      "m.ledger_dump([])", "m.spread(4)", "m.spread(0)"])

unit("grades", [
    "`average(scores)`: the arithmetic mean **rounded down** to an integer.",
    "`curve(scores, bump)`: a list with every score raised by `bump` and capped at 100.",
    "`ranking(names, scores)`: the names ordered by score (highest first), equal scores by name.",
    "`percent(part, whole)`: `part / whole` as a whole percentage; an exact half rounds **away from zero** (12.5 gives 13, -12.5 gives -13). Returns an `int`.",
    "`top_scores(scores, k)`: the scores that are at least `k`, as a list in the original order.",
    "`product(values)`: the product of all values (1 for none).",
], r'''
    """Classroom marks."""


    def average(scores):
        return sum(scores) / len(scores)


    def curve(scores, bump):
        return map(lambda s: min(100, s + bump), scores)


    def ranking(names, scores):
        pairs = zip(names, scores)
        pairs.sort(cmp=lambda a, b: cmp(b[1], a[1]) or cmp(a[0], b[0]))
        return [n for n, _ in pairs]


    def percent(part, whole):
        return int(round(part * 100.0 / whole))


    def top_scores(scores, k):
        return filter(lambda s: s >= k, scores)


    def product(values):
        return reduce(lambda a, b: a * b, values, 1)
''', r'''
    """Classroom marks."""
    import functools


    def average(scores):
        return sum(scores) // len(scores)


    def curve(scores, bump):
        return [min(100, s + bump) for s in scores]


    def ranking(names, scores):
        pairs = list(zip(names, scores))
        pairs.sort(key=lambda p: (-p[1], p[0]))
        return [n for n, _ in pairs]


    def percent(part, whole):
        x = part * 100.0 / whole
        return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


    def top_scores(scores, k):
        return [s for s in scores if s >= k]


    def product(values):
        return functools.reduce(lambda a, b: a * b, values, 1)
''', ["m.average([90, 85, 70])", "m.average([1, 2])", "m.average([100])", "m.curve([95, 80, 99], 7)", "m.ranking(['ann', 'bob', 'cy'], [80, 90, 80])", "m.ranking([], [])", "m.percent(1, 8)", "m.percent(1, 3)",
      "m.percent(5, 8)", "m.percent(-1, 8)", "m.percent(0, 5)", "m.top_scores([5, 9, 3, 9], 5)", "len(m.top_scores([5, 9, 3], 4))", "m.product([2, 3, 4])", "m.product([])"])

unit("tagging", [
    "`tag_of(text)`: the ASCII letters and digits of `text` (a `str` or UTF-8 `bytes`), upper-cased, everything else removed.",
    "`as_text(value)`: text for any value: `bytes` are decoded as UTF-8 (undecodable bytes become U+FFFD), text is returned as is, other values go through `str()`.",
    "`is_texty(value)`: true for text and for bytes.",
    "`initials(names)`: the first character of each name, upper-cased, joined.",
], r'''
    """Tags for catalogue records."""
    import string


    def tag_of(text):
        if isinstance(text, unicode):
            text = text.encode("ascii", "ignore")
        table = string.maketrans("", "")
        keep = string.letters + string.digits
        junk = table.translate(table, keep)
        return text.translate(table, junk).upper()


    def as_text(value):
        if isinstance(value, str):
            return value.decode("utf-8", "replace")
        if isinstance(value, unicode):
            return value
        return unicode(value)


    def is_texty(value):
        return isinstance(value, basestring)


    def initials(names):
        return u"".join(n[:1].upper() for n in names)
''', r'''
    """Tags for catalogue records."""
    import string


    def tag_of(text):
        if isinstance(text, bytes):
            text = text.decode("utf-8", "replace")
        keep = string.ascii_letters + string.digits
        return "".join(c for c in text if c in keep).upper()


    def as_text(value):
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        if isinstance(value, str):
            return value
        return str(value)


    def is_texty(value):
        return isinstance(value, (str, bytes))


    def initials(names):
        return "".join(n[:1].upper() for n in names)
''', ["m.tag_of('ab-12 c\\u00e9!')", "m.tag_of(b'x_y z\\xc3\\xa9 9')", "m.tag_of('')", "m.as_text(b'caf\\xc3\\xa9')", "m.as_text(b'bad\\xff')", "m.as_text('plain')", "m.as_text(42)", "m.as_text(None)", "m.is_texty('a')", "m.is_texty(b'a')", "m.is_texty(3)",
      "m.initials(['ada', 'grace', '\\u00e9mile'])", "m.initials([])"])

unit("money", [
    "`ordered(values)`: the cent amounts in ascending order.",
    "`nonzero(values)`: for each amount, whether it is non-zero.",
    "`halves(values)`: each amount divided by 2 (floor division of the cents), written as text `[-]W.CC`.",
    "`fmt(values)`: each amount written as text `[-]W.CC` (`-5` is `-0.05`, `1234` is `12.34`).",
    "`biggest(values)`: the largest amount in cents.",
], r'''
    """Money amounts in whole cents."""


    class Cents(object):
        def __init__(self, n):
            self.n = n

        def __cmp__(self, other):
            return cmp(self.n, other.n)

        def __hash__(self):
            return hash(self.n)

        def __nonzero__(self):
            return self.n != 0

        def __div__(self, k):
            return Cents(self.n // k)

        def __unicode__(self):
            whole, cents = divmod(abs(self.n), 100)
            return u"%s%d.%02d" % ("-" if self.n < 0 else "", whole, cents)

        def __str__(self):
            return unicode(self).encode("utf-8")


    def ordered(values):
        return [c.n for c in sorted(map(Cents, values))]


    def nonzero(values):
        return [bool(Cents(v)) for v in values]


    def halves(values):
        return [unicode(Cents(v) / 2) for v in values]


    def fmt(values):
        return [unicode(Cents(v)) for v in values]


    def biggest(values):
        return max(map(Cents, values)).n
''', r'''
    """Money amounts in whole cents."""
    import functools


    @functools.total_ordering
    class Cents(object):
        def __init__(self, n):
            self.n = n

        def __eq__(self, other):
            return self.n == other.n

        def __lt__(self, other):
            return self.n < other.n

        def __hash__(self):
            return hash(self.n)

        def __bool__(self):
            return self.n != 0

        def __truediv__(self, k):
            return Cents(self.n // k)

        def __str__(self):
            whole, cents = divmod(abs(self.n), 100)
            return "%s%d.%02d" % ("-" if self.n < 0 else "", whole, cents)


    def ordered(values):
        return [c.n for c in sorted(map(Cents, values))]


    def nonzero(values):
        return [bool(Cents(v)) for v in values]


    def halves(values):
        return [str(Cents(v) / 2) for v in values]


    def fmt(values):
        return [str(Cents(v)) for v in values]


    def biggest(values):
        return max(map(Cents, values)).n
''', ["m.ordered([300, -5, 120, 0])", "m.ordered([])", "m.nonzero([0, 5, -1])", "m.halves([1234, 5, -5, 0, 101])", "m.fmt([1234, 5, -5, 0, 100, -100050])", "m.biggest([5, 900, -3])"])

unit("hashing", [
    "`digest(text, algo)`: the hex digest of the UTF-8 bytes of `text` for the hash algorithm named `algo` (default `md5`).",
    "`to_hex(text)`: the lower-case hex of the UTF-8 bytes of `text`; `from_hex(h)` reverses it and returns text.",
    "`xor_mask(text, key)`: every UTF-8 byte of `text` XOR `key` (0..255), as lower-case hex.",
    "`byte_sum(text)`: the sum of the UTF-8 bytes of `text`.",
], r'''
    """Digests and byte helpers for the label printer."""
    import hashlib


    def _bytes(text):
        if isinstance(text, unicode):
            return text.encode("utf-8")
        return text


    def digest(text, algo="md5"):
        return hashlib.new(algo, _bytes(text)).hexdigest()


    def to_hex(text):
        return _bytes(text).encode("hex")


    def from_hex(h):
        return h.decode("hex").decode("utf-8")


    def xor_mask(text, key):
        data = _bytes(text)
        return "".join(chr(ord(b) ^ key) for b in data).encode("hex")


    def byte_sum(text):
        return sum(ord(b) for b in _bytes(text))
''', r'''
    """Digests and byte helpers for the label printer."""
    import hashlib


    def _bytes(text):
        return text.encode("utf-8")


    def digest(text, algo="md5"):
        return hashlib.new(algo, _bytes(text)).hexdigest()


    def to_hex(text):
        return _bytes(text).hex()


    def from_hex(h):
        return bytes.fromhex(h).decode("utf-8")


    def xor_mask(text, key):
        return bytes(b ^ key for b in _bytes(text)).hex()


    def byte_sum(text):
        return sum(_bytes(text))
''', ["m.digest('hello')", "m.digest('caf\\u00e9', 'sha1')", "m.digest('')", "m.to_hex('A\\u00e9')", "m.from_hex('41c3a9')", "m.from_hex(m.to_hex('round trip \\u4e2d'))", "m.xor_mask('abc', 255)", "m.xor_mask('\\u00e9', 1)",
      "m.byte_sum('abc')", "m.byte_sum('\\u00e9')", "m.from_hex('zz')"])

unit("modes", [
    "`parse_mode(text)`: a file mode written as octal digits only (`[0-7]+`) and at most `0777`; anything else is a `ValueError`.",
    "`format_mode(value)`: `'0'` followed by the octal digits (`420` is `'0644'`).",
    "`describe(d)`: `key=repr(value)` pairs joined with `;`, ordered by key.",
    "`clamp_int(v)`: `v` limited to the largest native size integer (`sys.maxsize`).",
], r'''
    """Permission modes for the sync agent."""
    import re
    import string
    import sys


    def parse_mode(text):
        if not re.match(r"[0-7]+$", text):
            raise ValueError, "bad mode %r" % text
        try:
            value = int(text, 8)
        except ValueError, e:
            raise ValueError, "bad mode %r" % text
        if value <> value & 0777:
            raise ValueError, "mode out of range: %r" % text
        return value


    def format_mode(value):
        return "0%o" % value


    def describe(d):
        keys = d.keys()
        keys.sort()
        return string.join(["%s=%s" % (k, `d[k]`) for k in keys], ";")


    def clamp_int(v):
        return min(v, sys.maxint)
''', r'''
    """Permission modes for the sync agent."""
    import re
    import sys


    def parse_mode(text):
        if not re.fullmatch(r"[0-7]+", text):
            raise ValueError("bad mode %r" % text)
        value = int(text, 8)
        if value != value & 0o777:
            raise ValueError("mode out of range: %r" % text)
        return value


    def format_mode(value):
        return "0%o" % value


    def describe(d):
        return ";".join("%s=%r" % (k, d[k]) for k in sorted(d))


    def clamp_int(v):
        return min(v, sys.maxsize)
''', ["m.parse_mode('644')", "m.parse_mode('0755')", "m.parse_mode('1000')", "m.parse_mode('89')", "m.parse_mode('')", "m.parse_mode('7_7')", "m.parse_mode('0o17')", "m.format_mode(420)", "m.format_mode(0)",
      "m.describe({'b': 'x', 'a': 1})", "m.describe({})", "m.describe({'k': [1, 'two']})", "m.clamp_int(5)", "m.clamp_int(2 ** 80) == m.sys.maxsize"])

unit("cursor", [
    "`countdown_list(n)`: `[n, n-1, ..., 1]` produced by iterating a `Countdown` object (an iterator class that is part of the module).",
    "`pairwise_sum(a, b)`: element-wise sums, stopping at the shorter list.",
    "`pad_pairs(a, b)`: pairs `(x, y)` of the two lists, the shorter padded with `None`.",
    "`evens_then_odds(n)`: the even numbers below `n` followed by the odd ones, as one list.",
    "`first_two(factory)`: calls `factory()` to get a generator and returns its first two values as a list.",
    "`only_value(d)`: the single value of a one-entry dict.",
], r'''
    """Iteration helpers for the playlist builder."""
    import itertools


    class Countdown(object):
        def __init__(self, n):
            self.n = n

        def __iter__(self):
            return self

        def next(self):
            if self.n <= 0:
                raise StopIteration
            self.n -= 1
            return self.n + 1


    def countdown_list(n):
        return list(Countdown(n))


    def pairwise_sum(a, b):
        return [x + y for x, y in itertools.izip(a, b)]


    def pad_pairs(a, b):
        return list(itertools.izip_longest(a, b))


    def evens_then_odds(n):
        return range(0, n, 2) + range(1, n, 2)


    def first_two(factory):
        g = factory()
        return [g.next(), g.next()]


    def only_value(d):
        return d.values()[0]
''', r'''
    """Iteration helpers for the playlist builder."""
    import itertools


    class Countdown(object):
        def __init__(self, n):
            self.n = n

        def __iter__(self):
            return self

        def __next__(self):
            if self.n <= 0:
                raise StopIteration
            self.n -= 1
            return self.n + 1


    def countdown_list(n):
        return list(Countdown(n))


    def pairwise_sum(a, b):
        return [x + y for x, y in zip(a, b)]


    def pad_pairs(a, b):
        return list(itertools.zip_longest(a, b))


    def evens_then_odds(n):
        return list(range(0, n, 2)) + list(range(1, n, 2))


    def first_two(factory):
        g = factory()
        return [next(g), next(g)]


    def only_value(d):
        return list(d.values())[0]
''', ["m.countdown_list(4)", "m.countdown_list(0)", "m.pairwise_sum([1, 2, 3], [10, 20])", "m.pad_pairs([1, 2, 3], ['a'])", "m.pad_pairs([], [])", "m.evens_then_odds(7)", "m.evens_then_odds(0)",
      "m.first_two(lambda: (i * i for i in range(10)))", "m.first_two(lambda: iter([5]))", "m.only_value({'k': 7})"])

unit("compat", [
    "`encode_query(d)`: `key=value` pairs sorted by key and joined with `&`, keys and values percent-encoded (UTF-8, everything but letters, digits and `_.-~/` escaped).",
    "`settings(text)`: parse INI text with a raw (non-interpolating) parser into `{section: {key: value}}`, sections and keys sorted.",
    "`drain(items)`: put the items on a FIFO queue and take them all off again; returns them in order.",
    "`roundtrip(obj)`: serialise `obj` with pickle protocol 2 and load it back.",
], r'''
    """Odds and ends for the config loader."""
    import ConfigParser
    import Queue
    import StringIO
    import cPickle
    import urllib


    def encode_query(d):
        return "&".join("%s=%s" % (urllib.quote(k), urllib.quote(v)) for k, v in sorted(d.items()))


    def settings(text):
        cp = ConfigParser.RawConfigParser()
        cp.readfp(StringIO.StringIO(text))
        return dict((s, dict(sorted(cp.items(s)))) for s in sorted(cp.sections()))


    def drain(items):
        q = Queue.Queue()
        for item in items:
            q.put(item)
        out = []
        while not q.empty():
            out.append(q.get())
        return out


    def roundtrip(obj):
        return cPickle.loads(cPickle.dumps(obj, 2))
''', r'''
    """Odds and ends for the config loader."""
    import configparser
    import io
    import pickle
    import queue
    from urllib.parse import quote


    def encode_query(d):
        return "&".join("%s=%s" % (quote(k), quote(v)) for k, v in sorted(d.items()))


    def settings(text):
        cp = configparser.RawConfigParser()
        cp.read_file(io.StringIO(text))
        return {s: dict(sorted(cp.items(s))) for s in sorted(cp.sections())}


    def drain(items):
        q = queue.Queue()
        for item in items:
            q.put(item)
        out = []
        while not q.empty():
            out.append(q.get())
        return out


    def roundtrip(obj):
        return pickle.loads(pickle.dumps(obj, 2))
''', ["m.encode_query({'q': 'a b', 'z': 'caf\\u00e9/1'})", "m.encode_query({})", "m.settings('[b]\\nx = 1\\n[a]\\ny = %(x)s\\n')", "m.settings('')", "m.drain([3, 1, 2])", "m.drain([])",
      "m.roundtrip({'a': [1, 2, (3, 4)], 'b': None})", "m.roundtrip('text')"])

unit("schedule", [
    "`merge_tables(a, b)`: pair up two lists position by position, padding the shorter with `None`.",
    "`call_with(fn, args)`: call `fn` with the items of `args` as positional arguments.",
    "`sort_slots(slots)`: a new list of `(name, minute)` slots ordered by minute, then name.",
    "`sum_pairs(pairs)`: a list with `a + b` for every `(a, b)` pair.",
    "`weighted(items, weights)`: a list of `item * weight` for each `(item, weight)` taken from the two lists in step.",
    "`parse_count(text)`: the integer value of a decimal text with optional surrounding spaces; `join_names(names)`: names joined with `-`.",
], r'''
    """Timetable helpers for the ferry office."""
    import string


    def merge_tables(a, b):
        return map(None, a, b)


    def call_with(fn, args):
        return apply(fn, args)


    def sort_slots(slots):
        out = list(slots)
        out.sort(lambda x, y: cmp(x[1], y[1]) or cmp(x[0], y[0]))
        return out


    def sum_pairs(pairs):
        return map(lambda (a, b): a + b, pairs)


    def weighted(items, weights):
        def scale(x, (item, weight)):
            return x * item * weight
        return [scale(1, p) for p in zip(items, weights)]


    def parse_count(text):
        return string.atoi(text)


    def join_names(names):
        return string.join(names, "-")
''', r'''
    """Timetable helpers for the ferry office."""
    import itertools


    def merge_tables(a, b):
        return list(itertools.zip_longest(a, b))


    def call_with(fn, args):
        return fn(*args)


    def sort_slots(slots):
        out = list(slots)
        out.sort(key=lambda s: (s[1], s[0]))
        return out


    def sum_pairs(pairs):
        return [a + b for a, b in pairs]


    def weighted(items, weights):
        return [item * weight for item, weight in zip(items, weights)]


    def parse_count(text):
        return int(text)


    def join_names(names):
        return "-".join(names)
''', ["m.merge_tables([1, 2], ['a', 'b', 'c'])", "m.merge_tables([], [])", "m.call_with(max, [3, 9, 4])", "m.call_with(lambda a, b: a - b, (10, 3))", "m.sort_slots([('b', 5), ('a', 5), ('c', 1)])",
      "m.sum_pairs([(1, 2), (3, 4)])", "m.sum_pairs([])", "m.weighted([1, 2, 3], [4, 5])", "m.parse_count(' 42 ')", "m.parse_count('x')", "m.join_names(['a', 'b', 'c'])"])

unit("inputs", [
    "`load_numbers(path)`: all whitespace-separated integers of a text file, in order.",
    "`count_rows(path)`: the number of lines of a text file (universal newlines).",
    "`read_total(path)`: the sum of the integers in the file.",
    "`words_of(path)`: the words of a UTF-8 text file (whitespace separated).",
], r'''
    """Reading the nightly count files."""


    def load_numbers(path):
        f = file(path)
        try:
            return [long(x) for x in f.read().split()]
        finally:
            f.close()


    def count_rows(path):
        n = 0
        f = open(path, "U")
        for line in f.xreadlines():
            n += 1
        f.close()
        return n


    def read_total(path):
        return sum(load_numbers(path))


    def words_of(path):
        f = open(path, "rb")
        try:
            return f.read().decode("utf-8").split()
        finally:
            f.close()
''', r'''
    """Reading the nightly count files."""


    def load_numbers(path):
        with open(path) as f:
            return [int(x) for x in f.read().split()]


    def count_rows(path):
        n = 0
        with open(path, newline=None) as f:
            for _ in f:
                n += 1
        return n


    def read_total(path):
        return sum(load_numbers(path))


    def words_of(path):
        with open(path, "rb") as f:
            return f.read().decode("utf-8").split()
''', ["m.load_numbers(P['nums'])", "m.count_rows(P['nums'])", "m.count_rows(P['crlf'])", "m.read_total(P['nums'])", "m.words_of(P['words'])", "m.load_numbers(P['empty'])", "m.count_rows(P['empty'])", "m.load_numbers(P['bad'])"])

unit("reports", [
    "`prune(d, limit)`: remove every entry whose value is below `limit` from the dict `d` (in place) and return the remaining items sorted by key.",
    "`histogram(words)`: `(word, count)` pairs, most frequent first, equal counts by word.",
    "`pairs_len(a, b)`: the number of positions both lists have in common.",
    "`merge_dicts(a, b)`: the items of both dicts (values of `b` win) sorted by key.",
    "`invert(d)`: `(value, key)` pairs of a dict sorted ascending.",
], r'''
    """Report builders for the volunteer roster."""


    def prune(d, limit):
        for k in d.keys():
            if d[k] < limit:
                del d[k]
        return sorted(d.items())


    def histogram(words):
        counts = {}
        for w in words:
            counts[w] = counts.get(w, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


    def pairs_len(a, b):
        return len(zip(a, b))


    def merge_dicts(a, b):
        return sorted(dict(a.items() + b.items()).items())


    def invert(d):
        return sorted((v, k) for k, v in d.iteritems())
''', r'''
    """Report builders for the volunteer roster."""


    def prune(d, limit):
        for k in list(d.keys()):
            if d[k] < limit:
                del d[k]
        return sorted(d.items())


    def histogram(words):
        counts = {}
        for w in words:
            counts[w] = counts.get(w, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


    def pairs_len(a, b):
        return len(list(zip(a, b)))


    def merge_dicts(a, b):
        return sorted({**a, **b}.items())


    def invert(d):
        return sorted((v, k) for k, v in d.items())
''', ["m.prune({'a': 1, 'b': 5, 'c': 3}, 3)", "m.prune({}, 1)", "m.histogram(['x', 'y', 'x', 'z', 'y', 'x'])", "m.histogram([])", "m.pairs_len([1, 2, 3], [4, 5])", "m.merge_dicts({'a': 1, 'b': 2}, {'b': 3, 'c': 4})",
      "m.invert({'a': 2, 'b': 1})"])

PKG_NAMES = ["fieldkit", "harbor_utils", "deskpack", "labcore", "tidebook", "ledgerlib", "parcelkit", "campkit"]

HIDDEN = dd('''
    import importlib
    import json
    import os
    import sys
    import tempfile
    import unittest

    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, ROOT)

    CASES = %s


    def make_files(tmp):
        out = {}
        for name, data in (("nums", b"10 20\\n30\\n  40 \\n"), ("crlf", b"a\\r\\nb\\r\\nc"), ("empty", b""), ("bad", b"1 two 3"),
                           ("words", "caf\\u00e9 cr\\u00e8me  \\u4e2d\\u6587\\nplain".encode("utf-8"))):
            p = os.path.join(tmp, name + ".txt")
            with open(p, "wb") as fh:
                fh.write(data)
            out[name] = p
        return out


    def evaluate(modname, expr, P):
        m = importlib.import_module(modname)
        try:
            return ["ok", json.dumps(eval(expr, {"m": m, "P": P}), sort_keys=True)]
        except Exception as ex:
            return ["raises", type(ex).__name__]


    class Behaviour(unittest.TestCase):
        def test_calls(self):
            P = make_files(tempfile.mkdtemp())
            bad = []
            for modname, expr, want in CASES:
                got = evaluate(modname, expr, P)
                if got != want:
                    bad.append("%%s: %%s -> %%s, want %%s" %% (modname, expr, got, want))
            self.assertEqual(bad, [], "\\n" + "\\n".join(bad[:8]))


    if __name__ == "__main__":
        unittest.main()
''')


def _expected(files, calls):
    driver = dd('''
        import importlib, json, os, sys, tempfile
        sys.path.insert(0, ".")
        exec(open("tests_prelude.py").read())
        tmp = tempfile.mkdtemp()
        P = make_files(tmp)
        CALLS = json.load(open("calls.json"))
        out = []
        for modname, expr in CALLS:
            out.append([modname, expr, evaluate(modname, expr, P)])
        print(json.dumps(out))
    ''')
    prelude = HIDDEN.split("class Behaviour")[0].replace("CASES = %s", "CASES = []")
    files = dict(files)
    files["driver.py"] = driver
    files["tests_prelude.py"] = prelude
    files["calls.json"] = json.dumps(calls)
    code, out = run_local(files, ["python3", "driver.py"], timeout=60)
    if code != 0:
        raise RuntimeError("py3 units fail:\n" + out[-1500:])
    return json.loads(out.strip().splitlines()[-1])


@family("port-py2-to-py3", category="port", lang="python", kind="refactor", n=10,
        summary="port a legacy python 2 package to python 3 (division, text/bytes, iterators, removed special methods, renamed modules)")
def gen_py2(rng, n):
    keys = sorted(UNITS)
    counts = [2, 2, 3, 3, 3, 4, 4, 5, 6, 7]
    prompts = [
        "This little package ({pkg}) was written for Python 2 and now has to run on Python 3.11. Port it: the public functions listed in README.md must behave exactly as documented (watch integer division, rounding, text versus bytes and iterator laziness). Don't change the tests.",
        "{pkg} still has Python 2 code in it (print statements, `iteritems`, `except X, e`, ...). Make it work on Python 3. README.md says what every function returns; the tests in the repo only cover part of it.",
        "port {pkg} from py2 to py3. keep behaviour as described in README.md, there are hidden checks beyond the visible tests so don't just make it import",
        "Ticket: migrate the {pkg} helper package to Python 3.11. Acceptance: all modules import, and every function in README.md returns what is documented there. No `six`/`future` dependency, the stdlib only.",
        "The {pkg} package can't even be imported on our new Python 3 images. Fix whatever is Python-2-only so that it works there with the documented behaviour (README.md). Some of the changes are silent behaviour changes, not just syntax.",
    ]
    for i in range(n):
        picked = rng.sample(keys, counts[i % len(counts)])
        pkg = PKG_NAMES[(i + rng.randrange(len(PKG_NAMES))) % len(PKG_NAMES)]
        old_files, new_files, calls, docs = {f"{pkg}/__init__.py": ""}, {}, [], []
        for k in picked:
            u = UNITS[k]
            old_files[f"{pkg}/{k}.py"] = u["py2"]
            new_files[f"{pkg}/{k}.py"] = u["py3"]
            docs.append(f"### `{pkg}.{k}`\n\n" + "\n".join(f"* {d}" for d in u["doc"]))
            calls += [(f"{pkg}.{k}", c) for c in u["calls"]]
        exp = _expected({**new_files, f"{pkg}/__init__.py": ""}, calls)
        cases = [(m, e, r) for m, e, r in exp]
        hidden = HIDDEN % json.dumps(cases, ensure_ascii=True)
        vis_cases = []
        for k in picked:
            seen = 0
            for m, e, r in cases:
                if m == f"{pkg}.{k}" and seen < 2:
                    vis_cases.append((m, e, r))
                    seen += 1
        visible = HIDDEN.split("class Behaviour")[0] % json.dumps(vis_cases, ensure_ascii=True) + dd('''
            class SmokeTests(unittest.TestCase):
                def test_sample_calls(self):
                    P = make_files(tempfile.mkdtemp())
                    for modname, expr, want in CASES:
                        self.assertEqual(evaluate(modname, expr, P), want, "%s: %s" % (modname, expr))


            if __name__ == "__main__":
                unittest.main()
        ''')
        readme = (f"# {pkg}\n\nSmall helper modules used by the {pkg} tools. They were written for Python 2 and are being moved to Python 3.11 "
                  f"(standard library only; no compatibility layers). The functions below must keep their documented behaviour. Text means `str`; "
                  f"files are UTF-8.\n\n" + "\n\n".join(docs) + "\n")
        count = len(picked)
        d = max(2, min(5, 1 + (count >= 3) + (count >= 5) + (count >= 7) + (1 if {"money", "grades", "reports", "schedule"} & set(picked) else 0)))
        yield Task(
            slug=f"{i + 1:02d}-{count}-modules",
            prompt=rng.choice(prompts).format(pkg=pkg),
            difficulty=d,
            lang="python",
            kind="refactor",
            start={**old_files, "README.md": readme, "tests/test_sample.py": visible},
            hidden={"tests/test_behaviour.py": hidden},
            solution=new_files,
            verify="python3 -m unittest discover -s tests -v",
            tags=["api-migration", "py2-to-py3", "python"],
            notes={"units": picked},
        )
