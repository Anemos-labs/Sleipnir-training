"""API migration inside Python: deprecated or removed standard-library calls -> their current replacements.

Every task is a small package whose functions call APIs that warn (or are gone) on the Python 3.11 of the checkout. The
verifier runs the behaviour tests with ``python3 -W error``, so a leftover deprecated call fails, and a text scan rejects
silencing warnings. Expected values are computed from the migrated code, never typed.
"""
import json
import random

from fx import Task, dd, family

from ._portlib import run_local

# Each snippet: code written against the OLD API; ``subs`` turn it into the migrated code (every pair must match once).
SNIPPETS = [
    dict(key="audit-log", theme="logs", imports=["import logging"],
         doc="`audit_lines(name, messages)` logs each message at WARNING level on a private logger and returns the records as `LEVEL:audit <text>` strings.",
         code=r'''
class _Collector(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.lines = []

    def emit(self, record):
        self.lines.append("%s:%s" % (record.levelname, record.getMessage()))


def audit_lines(name, messages):
    log = logging.getLogger("audit." + name)
    log.propagate = False
    log.setLevel(logging.DEBUG)
    handler = _Collector()
    log.addHandler(handler)
    try:
        for m in messages:
            log.warn("audit %s", m)
    finally:
        log.removeHandler(handler)
    return handler.lines
''', subs=[("log.warn(", "log.warning(")],
         calls=["m.audit_lines('a', ['x', 'y z'])", "m.audit_lines('b', [])", "m.audit_lines('c', ['100%', 'caf\\u00e9'])"]),
    dict(key="flatten-mapping", theme="data", imports=["import collections"],
         doc="`flatten(obj)` flattens nested mappings into a dict with dotted keys; `is_table(x)` tells whether `x` is a mapping.",
         code=r'''
def flatten(obj, prefix=""):
    out = {}
    for key in sorted(obj):
        value = obj[key]
        name = prefix + str(key)
        if isinstance(value, collections.Mapping):
            out.update(flatten(value, name + "."))
        else:
            out[name] = value
    return out


def is_table(x):
    return isinstance(x, collections.Mapping)
''', subs=[("import collections", "import collections.abc"), ("isinstance(value, collections.Mapping)", "isinstance(value, collections.abc.Mapping)"), ("isinstance(x, collections.Mapping)", "isinstance(x, collections.abc.Mapping)")],
         calls=["m.flatten({'a': {'b': 1, 'c': {'d': 2}}, 'e': 3})", "m.flatten({})", "m.is_table({'a': 1})", "m.is_table([('a', 1)])", "m.flatten({'x': {}, 'y': {'z': None}})"]),
    dict(key="required-args", theme="data", imports=["import inspect"],
         doc="`required_args(fn)` returns the names of the positional parameters of `fn` that have no default.",
         code=r'''
def required_args(fn):
    spec = inspect.getargspec(fn)
    defaults = spec.defaults or ()
    return spec.args[:len(spec.args) - len(defaults)]
''', subs=[("inspect.getargspec(fn)", "inspect.getfullargspec(fn)")],
         calls=["m.required_args(lambda a, b, c=1: None)", "m.required_args(lambda: None)", "m.required_args(lambda x=1, y=2: None)", "m.required_args(lambda p, q: None)"]),
    dict(key="ratio-gcd", theme="data", imports=["import fractions"],
         doc="`reduce_ratio(a, b)` reduces a ratio to lowest terms as `\"a:b\"`; a zero denominator is a `ValueError`.",
         code=r'''
def reduce_ratio(a, b):
    if b == 0:
        raise ValueError("zero denominator")
    g = fractions.gcd(a, b)
    return "%d:%d" % (a // g, b // g)
''', subs=[("import fractions", "import math"), ("fractions.gcd(a, b)", "math.gcd(a, b)")],
         calls=["m.reduce_ratio(6, 4)", "m.reduce_ratio(7, 3)", "m.reduce_ratio(0, 5)", "m.reduce_ratio(100, 10)", "m.reduce_ratio(12, 18)"]),
    dict(key="blob-wrap", theme="text", imports=["import base64"],
         doc="`wrap_blob(data)` returns the base64 text of `data` (bytes) with line breaks every 76 characters and a final newline; `unwrap_blob(text)` reverses it.",
         code=r'''
def wrap_blob(data):
    return base64.encodestring(data).decode("ascii")


def unwrap_blob(text):
    return base64.decodestring(text.encode("ascii"))
''', subs=[("base64.encodestring(data)", "base64.encodebytes(data)"), ("base64.decodestring(", "base64.decodebytes(")],
         calls=["m.wrap_blob(b'hello world')", "m.wrap_blob(bytes(range(100)))", "m.unwrap_blob(m.wrap_blob(b'round trip'))", "m.wrap_blob(b'')"]),
    dict(key="sample-pack", theme="data", imports=["import array", "import binascii"],
         doc="`pack_samples(values)` packs signed 16-bit samples into bytes (native order) and returns them as lower-case hex.",
         code=r'''
def pack_samples(values):
    raw = array.array("h", values).tostring()
    return binascii.hexlify(raw).decode("ascii")
''', subs=[(".tostring()", ".tobytes()")],
         calls=["m.pack_samples([1, 2, 3])", "m.pack_samples([])", "m.pack_samples([-1, 32767, -32768])"]),
    dict(key="stopwatch", theme="workers", imports=["import time"],
         doc="`measure(fn, *args)` returns `(result, ok)` where `ok` is true when the measured duration is not negative.",
         code=r'''
def measure(fn, *args):
    start = time.clock()
    result = fn(*args)
    elapsed = time.clock() - start
    return result, elapsed >= 0
''', subs=[("start = time.clock()", "start = time.perf_counter()"), ("elapsed = time.clock() - start", "elapsed = time.perf_counter() - start")],
         calls=["m.measure(lambda a, b: a + b, 2, 3)", "m.measure(sorted, [3, 1, 2])", "m.measure(len, 'abc')"]),
    dict(key="worker-thread", theme="workers", imports=["import threading"],
         doc="`run_worker(label, fn)` runs `fn()` on a daemon thread named `label`, waits for it, and returns `(result, thread name, alive afterwards)`; `current_name()` is the name of the calling thread.",
         code=r'''
def run_worker(label, fn):
    box = []
    t = threading.Thread(target=lambda: box.append(fn()))
    t.setName(label)
    t.setDaemon(True)
    t.start()
    t.join()
    return box[0], t.getName(), t.isAlive()


def current_name():
    return threading.currentThread().getName()
''', subs=[("t.setName(label)", "t.name = label"), ("t.setDaemon(True)", "t.daemon = True"), ("t.getName(), t.isAlive()", "t.name, t.is_alive()"),
                  ("threading.currentThread().getName()", "threading.current_thread().name")],
         calls=["m.run_worker('w1', lambda: 6 * 7)", "m.run_worker('batch-2', lambda: 'done')", "m.current_name()"]),
    dict(key="money-locale", theme="text", imports=["import locale"],
         doc="`money(amount)` formats a number with two decimals and digit grouping in the C locale (so no group separators appear).",
         code=r'''
def money(amount):
    locale.setlocale(locale.LC_ALL, "C")
    return locale.format("%.2f", amount, grouping=True)
''', subs=[('locale.format("%.2f", amount, grouping=True)', 'locale.format_string("%.2f", amount, grouping=True)')],
         calls=["m.money(1234.5)", "m.money(0)", "m.money(-7.125)", "m.money(1000000)"]),
    dict(key="settings-ini", theme="config", imports=["import configparser", "import io"],
         doc="`load_settings(text)` parses INI text and returns `{section: {key: value}}` with sections and keys sorted; interpolation uses `%(name)s`.",
         code=r'''
def load_settings(text):
    parser = configparser.SafeConfigParser()
    parser.readfp(io.StringIO(text))
    return {s: {k: parser.get(s, k) for k in sorted(parser.options(s))} for s in sorted(parser.sections())}
''', subs=[("configparser.SafeConfigParser()", "configparser.ConfigParser()"), ("parser.readfp(io.StringIO(text))", "parser.read_file(io.StringIO(text))")],
         calls=["m.load_settings('[db]\\nhost = localhost\\nurl = %(host)s:5432\\n[app]\\nname = demo\\n')", "m.load_settings('')", "m.load_settings('[a]\\nb = 1\\n[z]\\ny=2\\nx=3\\n')"]),
    dict(key="draw-options", theme="data", imports=["import random"],
         doc="`draw(options, k, seed)` seeds the generator and returns `k` options (a set of strings) chosen without replacement; the choice must be reproducible for the same set and seed, whatever the set's iteration order.",
         code=r'''
def draw(options, k, seed):
    rng = random.Random(seed)
    return rng.sample(options, k)
''', subs=[("rng.sample(options, k)", "rng.sample(sorted(options), k)")],
         calls=["m.draw({'a', 'b', 'c', 'd', 'e'}, 2, 7)", "m.draw({'x'}, 1, 0)", "m.draw({'p', 'q', 'r'}, 3, 99)", "m.draw(set(), 0, 1)"]),
    dict(key="line-count", theme="io", imports=[],
         doc="`count_lines(path)` returns the number of lines of a text file; universal newlines apply (`\\n`, `\\r\\n` and `\\r` each end a line).",
         code=r'''
def count_lines(path):
    with open(path, "rU") as fh:
        return sum(1 for _ in fh)
''', subs=[('open(path, "rU")', 'open(path, "r", newline=None)')],
         calls=["m.count_lines(P['lf'])", "m.count_lines(P['crlf'])", "m.count_lines(P['cr'])", "m.count_lines(P['empty'])"]),
    dict(key="suite-size", theme="data", imports=["import unittest"],
         doc="`suite_size(case)` is the number of test methods unittest discovers in the `TestCase` class `case`.",
         code=r'''
def suite_size(case):
    return unittest.makeSuite(case).countTestCases()
''', subs=[("unittest.makeSuite(case)", "unittest.TestLoader().loadTestsFromTestCase(case)")],
         calls=["m.suite_size(Sample)", "m.suite_size(Empty)"]),
    dict(key="xml-children", theme="text", imports=["import xml.etree.ElementTree as ET"],
         doc="`child_tags(xml_text)` lists the tag names of the root's direct children; `item_ids(xml_text)` lists the `id` attribute of every `item` element anywhere in the document, in document order.",
         code=r'''
def child_tags(xml_text):
    root = ET.fromstring(xml_text)
    return [c.tag for c in root.getchildren()]


def item_ids(xml_text):
    root = ET.fromstring(xml_text)
    return [e.get("id") for e in root.getiterator("item")]
''', subs=[("root.getchildren()", "list(root)"), ('root.getiterator("item")', 'root.iter("item")')],
         calls=["m.child_tags('<r><a/><b><c/></b><a/></r>')", "m.child_tags('<r/>')", "m.item_ids('<r><item id=\"1\"/><g><item id=\"2\"/></g><item id=\"3\"/></r>')", "m.item_ids('<r><x/></r>')"]),
    dict(key="html-text", theme="text", imports=["import html.parser"],
         doc="`plain_text(s)` replaces HTML character references (`&amp;`, `&#65;`, `&eacute;`, ...) by the characters they stand for.",
         code=r'''
def plain_text(s):
    return html.parser.HTMLParser().unescape(s)
''', subs=[("import html.parser", "import html"), ("html.parser.HTMLParser().unescape(s)", "html.unescape(s)")],
         calls=["m.plain_text('Tom &amp; Jerry')", "m.plain_text('&#65;&#x42;&eacute;')", "m.plain_text('no entities')", "m.plain_text('&lt;b&gt;')"]),
    dict(key="plist-read", theme="config", imports=["import plistlib"],
         doc="`read_plist(data)` parses an XML property list given as bytes and returns the value.",
         code=r'''
def read_plist(data):
    return plistlib.readPlistFromBytes(data)
''', subs=[("plistlib.readPlistFromBytes(data)", "plistlib.loads(data)")],
         calls=["m.read_plist(PL1)", "m.read_plist(PL2)"]),
    dict(key="module-from-text", theme="config", imports=["import imp"],
         doc="`value_of(name, source)` executes Python source text as a fresh module called `name` and returns the module's `VALUE`; `module_name(name, source)` returns that module's `__name__`.",
         code=r'''
def _build(name, source):
    mod = imp.new_module(name)
    exec(source, mod.__dict__)
    return mod


def value_of(name, source):
    return _build(name, source).VALUE


def module_name(name, source):
    return _build(name, source).__name__
''', subs=[("import imp", "import types"), ("imp.new_module(name)", "types.ModuleType(name)")],
         calls=["m.value_of('cfg', 'VALUE = 6 * 7')", "m.module_name('plug', 'VALUE = 1')", "m.value_of('x', 'A = 2\\nVALUE = A ** 5')"]),
    dict(key="escape-title", theme="text", imports=["import cgi"],
         doc="`escape_title(s)` escapes `&`, `<`, `>`, double and single quotes for use inside an HTML attribute (`'` becomes `&#x27;`).",
         code=r'''
def escape_title(s):
    return cgi.escape(s, quote=True)
''', subs=[("import cgi", "import html"), ("cgi.escape(s, quote=True)", "html.escape(s, quote=True)")],
         calls=["m.escape_title('a < b & c')", "m.escape_title('say \"hi\"')", "m.escape_title(\"it's\")", "m.escape_title('plain')"]),
    dict(key="shell-words", theme="text", imports=["import pipes"],
         doc="`shell_line(words)` quotes each word so that a POSIX shell reads it back as one argument and joins them with single spaces.",
         code=r'''
def shell_line(words):
    return " ".join(pipes.quote(w) for w in words)
''', subs=[("import pipes", "import shlex"), ("pipes.quote(w)", "shlex.quote(w)")],
         calls=["m.shell_line(['echo', 'hello world'])", "m.shell_line([])", "m.shell_line(['a', \"it's\", ''])", "m.shell_line(['safe-1.txt', '$HOME'])"]),
    dict(key="module-exists", theme="config", imports=["import importlib"],
         doc="`module_exists(name)` tells whether a top-level or dotted module can be found without importing it; `names_found(names)` filters a list of module names to those that exist.",
         code=r'''
def module_exists(name):
    return importlib.find_loader(name) is not None


def names_found(names):
    return [n for n in names if module_exists(n)]
''', subs=[("import importlib", "import importlib.util"), ("importlib.find_loader(name) is not None", "importlib.util.find_spec(name) is not None")],
         calls=["m.module_exists('json')", "m.module_exists('no_such_module_xyz')", "m.names_found(['os', 'nope_abc', 'json.tool'])"]),
    dict(key="async-pipeline", theme="workers", imports=["import asyncio"],
         doc="`run_pipeline(values)` doubles every value in a coroutine pipeline (one step per value, in order) and returns the list; the coroutine function `double(x)` yields the doubled value.",
         code=r'''
@asyncio.coroutine
def double(x):
    yield from asyncio.sleep(0)
    return x * 2


@asyncio.coroutine
def _pipeline(values):
    out = []
    for v in values:
        out.append((yield from double(v)))
    return out


def run_pipeline(values):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_pipeline(values))
    finally:
        loop.close()
''', subs=[("@asyncio.coroutine\ndef double(x):\n    yield from asyncio.sleep(0)", "async def double(x):\n    await asyncio.sleep(0)"),
                  ("@asyncio.coroutine\ndef _pipeline(values):", "async def _pipeline(values):"), ("out.append((yield from double(v)))", "out.append(await double(v))")],
         calls=["m.run_pipeline([1, 2, 3])", "m.run_pipeline([])", "m.run_pipeline([10])"]),
    dict(key="daemon-flag", theme="workers", imports=["import threading"],
         doc="`describe_thread(name, daemon)` creates (but does not start) a thread and returns `\"<name>:<daemon|normal>\"` using the thread's own attributes.",
         code=r'''
def describe_thread(name, daemon):
    t = threading.Thread(name=name, target=lambda: None)
    t.setDaemon(daemon)
    return "%s:%s" % (t.getName(), "daemon" if t.isDaemon() else "normal")


def live_threads():
    return threading.activeCount() >= 1
''', subs=[("t.setDaemon(daemon)", "t.daemon = daemon"), ("t.getName(), \"daemon\" if t.isDaemon()", "t.name, \"daemon\" if t.daemon"), ("threading.activeCount()", "threading.active_count()")],
         calls=["m.describe_thread('a', True)", "m.describe_thread('b', False)", "m.live_threads()"]),
    dict(key="assert-helpers", theme="data", imports=["import unittest"],
         doc="`check_report(expected, actual)` returns an empty list when the two dicts agree on every key of `expected` and otherwise a sorted list of the differing keys.",
         code=r'''
class _Probe(unittest.TestCase):
    def runTest(self):
        pass


def check_report(expected, actual):
    probe = _Probe()
    bad = []
    for key in sorted(expected):
        try:
            probe.assertEquals(expected[key], actual.get(key))
        except AssertionError:
            bad.append(key)
    return bad
''', subs=[("probe.assertEquals(", "probe.assertEqual(")],
         calls=["m.check_report({'a': 1, 'b': 2}, {'a': 1, 'b': 3})", "m.check_report({}, {'a': 1})", "m.check_report({'x': 1}, {})", "m.check_report({'k': [1, 2]}, {'k': [1, 2]})"]),
]

THEMES = {"logs": ("logkit", "audit"), "data": ("datakit", "shapes"), "text": ("textkit", "encoding"), "workers": ("workkit", "runtime"), "config": ("confkit", "loading"), "io": ("iokit", "files")}

VISIBLE_PRELUDE = dd('''
    import unittest
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
''')

HIDDEN_PRELUDE = dd('''
    import ast
    import importlib
    import os
    import re
    import sys
    import tempfile
    import unittest

    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, ROOT)

    PL1 = b'<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict><key>name</key><string>demo</string><key>n</key><integer>7</integer><key>on</key><true/></dict></plist>'
    PL2 = b'<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><array><string>a</string><real>1.5</real></array></plist>'


    class Sample(unittest.TestCase):
        def test_one(self):
            pass

        def test_two(self):
            pass

        def helper(self):
            pass


    class Empty(unittest.TestCase):
        pass


    def make_files(tmp):
        out = {}
        for name, data in (("lf", b"a\\nb\\nc\\n"), ("crlf", b"a\\r\\nb\\r\\n"), ("cr", b"a\\rb\\rc\\rd"), ("empty", b"")):
            p = os.path.join(tmp, name + ".txt")
            with open(p, "wb") as fh:
                fh.write(data)
            out[name] = p
        return out
''')


def _derive(snippet):
    new = snippet["code"]
    for a, b in snippet["subs"]:
        if a.startswith("import "):
            continue
        if new.count(a) != 1:
            raise RuntimeError(f"snippet {snippet['key']}: substitution {a!r} matches {new.count(a)} times")
        new = new.replace(a, b)
    imports_new = list(snippet["imports"])
    for a, b in snippet["subs"]:
        for i, line in enumerate(imports_new):
            if line == a:
                imports_new[i] = b
    return new


def _module_text(snips, which, header):
    imports = []
    for s in snips:
        lines = list(s["imports"])
        if which == "new":
            for a, b in s["subs"]:
                lines = [b if ln == a else ln for ln in lines]
        for ln in lines:
            if ln not in imports:
                imports.append(ln)
    body = "\n\n".join((s["code"] if which == "old" else _derive(s)).strip("\n") + "\n" for s in snips)
    return f'"""{header}"""\n' + "\n".join(sorted(imports)) + ("\n\n\n" if imports else "\n") + body.replace("\n\n\n\n", "\n\n\n")


def _expected(module_texts, groups, files_needed):
    """Run the migrated modules and evaluate every call; returns {expr: repr(result)}."""
    driver = HIDDEN_PRELUDE + dd('''
        import json

        results = {}
        tmp = tempfile.mkdtemp()
        P = make_files(tmp)
        CALLS = json.load(open("calls.json"))
        for modname, exprs in CALLS.items():
            m = importlib.import_module(modname)
            for e in exprs:
                try:
                    results[modname + "|" + e] = ["ok", repr(eval(e, {"m": m, "P": P, "Sample": Sample, "Empty": Empty, "PL1": PL1, "PL2": PL2}))]
                except Exception as ex:
                    results[modname + "|" + e] = ["raises", type(ex).__name__]
        print(json.dumps(results))
    ''')
    files = dict(module_texts)
    files["calls.json"] = json.dumps(groups)
    files["driver.py"] = driver
    code, out = run_local(files, ["python3", "-W", "error", "driver.py"], timeout=60)
    if code != 0:
        raise RuntimeError("migrated modules fail under -W error:\n" + out[-1500:])
    return json.loads(out.strip().splitlines()[-1])


@family("port-stdlib-modernize", category="port", lang="python", kind="fix", n=10,
        summary="replace deprecated or removed standard-library calls so the package runs warning-free on python 3.11")
def gen_stdlib(rng, n):
    keys = [s["key"] for s in SNIPPETS]
    by_key = {s["key"]: s for s in SNIPPETS}
    plans = [(3, 1), (4, 2), (3, 1), (5, 2), (6, 2), (4, 3), (5, 3), (7, 3), (8, 4), (10, 4)]
    for i in range(n):
        count, nmods = plans[i % len(plans)]
        picked = rng.sample(keys, count)
        # group by theme into modules; merge themes if there are too many modules
        themed: dict[str, list] = {}
        for k in picked:
            themed.setdefault(by_key[k]["theme"], []).append(by_key[k])
        groups = list(themed.items())
        while len(groups) > nmods:
            groups.sort(key=lambda g: len(g[1]))
            a, b = groups.pop(0), groups.pop(0)
            groups.append((b[0], b[1] + a[1]))
        pkg = rng.choice(["opskit", "acctools", "deskutil", "fieldlib", "harbortools", "labkit"])
        mods = {}
        for theme, snips in groups:
            base, desc = THEMES[theme]
            name = f"{pkg}/{base}.py"
            mods[name] = snips
        old_files, new_files, calls = {"%s/__init__.py" % pkg: ""}, {"%s/__init__.py" % pkg: ""}, {}
        doc_lines = []
        for path, snips in mods.items():
            modname = path[:-3].replace("/", ".")
            hdr = f"Helpers for {THEMES[snips[0]['theme']][1]}."
            old_files[path] = _module_text(snips, "old", hdr)
            new_files[path] = _module_text(snips, "new", hdr)
            calls[modname] = [c for s in snips for c in s["calls"]]
            for s in snips:
                doc_lines.append(f"* `{modname}`: {s['doc']}")
        expected = _expected(new_files, calls, True)
        # hidden tests
        cases = []
        for modname, exprs in calls.items():
            for e in exprs:
                cases.append((modname, e, expected[modname + "|" + e]))
        hidden_py = HIDDEN_PRELUDE + dd('''

            CASES = %s


            class Behaviour(unittest.TestCase):
                def test_calls(self):
                    tmp = tempfile.mkdtemp()
                    P = make_files(tmp)
                    bad = []
                    for modname, expr, want in CASES:
                        m = importlib.import_module(modname)
                        try:
                            got = ["ok", repr(eval(expr, {"m": m, "P": P, "Sample": Sample, "Empty": Empty, "PL1": PL1, "PL2": PL2}))]
                        except Exception as ex:
                            got = ["raises", type(ex).__name__]
                        if got != want:
                            bad.append("%%s: %%s -> %%s, want %%s" %% (modname, expr, got, want))
                    self.assertEqual(bad, [], "\\n" + "\\n".join(bad[:8]))

                def test_no_warning_filters(self):
                    pat = re.compile(r"filterwarnings|simplefilter|catch_warnings|PYTHONWARNINGS|warnings\\.warn|ignore::")
                    hits = []
                    for dirpath, _, names in os.walk(ROOT):
                        if "tests" in dirpath.split(os.sep):
                            continue
                        for n in names:
                            if n.endswith(".py") and pat.search(open(os.path.join(dirpath, n), encoding="utf-8").read()):
                                hits.append(os.path.join(dirpath, n))
                    self.assertEqual(hits, [], "do not silence warnings, remove the deprecated calls")


            if __name__ == "__main__":
                unittest.main()
        ''') % json.dumps([[a, b, c] for a, b, c in cases], ensure_ascii=True)
        # visible test: a sample of the calls (first call of each snippet)
        vis_cases = []
        for path, snips in mods.items():
            modname = path[:-3].replace("/", ".")
            for s in snips:
                e = s["calls"][0]
                vis_cases.append((modname, e, expected[modname + "|" + e]))
        visible_py = HIDDEN_PRELUDE.split("class Sample")[0] + dd('''

            class Sample(unittest.TestCase):
                def test_one(self):
                    pass

                def test_two(self):
                    pass

                def helper(self):
                    pass


            class Empty(unittest.TestCase):
                pass


            def make_files(tmp):
                out = {}
                for name, data in (("lf", b"a\\nb\\nc\\n"), ("crlf", b"a\\r\\nb\\r\\n"), ("cr", b"a\\rb\\rc\\rd"), ("empty", b"")):
                    p = os.path.join(tmp, name + ".txt")
                    with open(p, "wb") as fh:
                        fh.write(data)
                    out[name] = p
                return out


            CASES = %s


            class SmokeTests(unittest.TestCase):
                def test_one_call_each(self):
                    P = make_files(tempfile.mkdtemp())
                    for modname, expr, want in CASES:
                        m = importlib.import_module(modname)
                        got = ["ok", repr(eval(expr, {"m": m, "P": P, "Sample": Sample, "Empty": Empty, "PL1": PL1, "PL2": PL2}))]
                        self.assertEqual(got, want, "%%s: %%s" %% (modname, expr))


            if __name__ == "__main__":
                unittest.main()
        ''') % json.dumps([[a, b, c] for a, b, c in vis_cases], ensure_ascii=True)
        readme = (f"# {pkg}\n\nSmall helper modules used by the {pkg} command-line tools. The test suite is run with warnings turned into errors "
                  f"(`python3 -W error -m unittest discover -s tests`) on Python 3.11.\n\n## Behaviour to preserve\n\n" + "\n".join(doc_lines) + "\n\n"
                  "Public names, signatures and results stay exactly as they are; only the way the standard library is called changes. "
                  "Warnings must be removed, not filtered.\n")
        d = 1 + (count >= 4) + (count >= 7) + (nmods >= 3)
        d = max(2, min(4, d))
        styles = [
            f"CI for {pkg} now runs the tests with `python3 -W error` on Python 3.11 and the whole suite is red: some of our helpers still call standard-library APIs that were deprecated or removed. Fix the library code so the suite is green again without changing behaviour. README.md lists what each helper must return; don't add warning filters.",
            f"`python3 -W error -m unittest discover -s tests` fails in this repo with DeprecationWarnings and AttributeErrors from the stdlib. Please migrate every deprecated or removed call in the package to the current API. Results must stay identical, and silencing the warnings doesn't count.",
            f"we're moving {pkg} to a python 3.11 runner with warnings-as-errors. several modules use old stdlib calls (some of them don't even exist any more). port them to the modern equivalents, keep the behaviour in README.md, tests under tests/ are the visible part of the check",
            f"Ticket: make {pkg} warning-free on Python 3.11. Acceptance: the package imports and every helper listed in README.md works under `-W error`, behaviour unchanged, no `warnings` filters anywhere.",
        ]
        yield Task(
            slug=f"{i + 1:02d}-{count}fn-{nmods}mod",
            prompt=rng.choice(styles),
            difficulty=d,
            lang="python",
            kind="fix",
            start={**old_files, "README.md": readme, "tests/test_smoke.py": visible_py},
            hidden={"tests/test_behaviour.py": hidden_py},
            solution={p: t for p, t in new_files.items() if old_files.get(p) != t},
            verify="python3 -W error -m unittest discover -s tests -v",
            tags=["api-migration", "stdlib", "python"],
            notes={"snippets": picked, "modules": len(mods)},
        )
