"""API migration inside Python: call sites of a legacy internal client move to its replacement.

Each task has a legacy client module (the old API, still importable in the start repository), the new client (already
present), a migration guide, and several application functions that use the old API. The application functions receive the
client as their first argument; after the migration they receive the *new* client. Hidden tests replace the legacy module
by a tripwire and compare what the in-memory backend recorded (and what the functions return) with the reference migration.
"""
import json

from fx import Task, dd, family

from ._portlib import run_local

# ---------------------------------------------------------------------------------------------------------------
# kind 1: notifications
# ---------------------------------------------------------------------------------------------------------------

NOTIFY_BACKEND = dd('''
    class Recorder(object):
        """In-memory delivery backend used by the tests and by local runs."""

        def __init__(self, fail=("ghost",)):
            self.events = []
            self.fail = set(fail)
            self._n = 0

        def deliver(self, to, text, prio, ttl_ms, attempts):
            if to in self.fail:
                return None, "unreachable:%s" % to
            self._n += 1
            self.events.append(["deliver", to, text, prio, ttl_ms, attempts])
            return "m%d" % self._n, None
''')

NOTIFY_NEW = dd('''
    """Notification client (v2)."""

    PRIORITIES = ("low", "normal", "high")


    class DeliveryError(Exception):
        def __init__(self, reason):
            Exception.__init__(self, reason)
            self.reason = reason


    class Message(object):
        def __init__(self, recipient, body, priority="normal", expires_in_ms=None, max_attempts=3):
            if priority not in PRIORITIES:
                raise ValueError("unknown priority %r" % (priority,))
            if max_attempts < 1:
                raise ValueError("max_attempts must be at least 1")
            self.recipient = recipient
            self.body = body
            self.priority = priority
            self.expires_in_ms = expires_in_ms
            self.max_attempts = max_attempts


    class Receipt(object):
        def __init__(self, id):
            self.id = id


    class Client(object):
        def __init__(self, backend):
            self._backend = backend

        def publish(self, message):
            ref, err = self._backend.deliver(message.recipient, message.body, message.priority, message.expires_in_ms, message.max_attempts)
            if err:
                raise DeliveryError(err)
            return Receipt(ref)

        def publish_all(self, messages):
            """One result per message, in order: a Receipt, or the DeliveryError instance (not raised) for a failed one."""
            out = []
            for m in messages:
                try:
                    out.append(self.publish(m))
                except DeliveryError as e:
                    out.append(e)
            return out
''')

NOTIFY_LEGACY = dd('''
    """Old notification client. Deprecated: use notifykit.client.Client."""


    class Notifier(object):
        def __init__(self, backend):
            self._b = backend

        def notify(self, user_id, text, urgent=False, ttl_s=None, retry=True):
            """Returns (True, message id) or (False, reason)."""
            prio = "high" if urgent else "normal"
            ttl_ms = None if ttl_s is None else int(ttl_s * 1000)
            attempts = 3 if retry else 1
            ref, err = self._b.deliver(user_id, text.rstrip(), prio, ttl_ms, attempts)
            if err:
                return False, err
            return True, ref

        def notify_many(self, user_ids, text, **kw):
            """List of (ok, ref-or-reason), one per user, in order."""
            return [self.notify(u, text, **kw) for u in user_ids]
''')

NOTIFY_GUIDE = dd('''
    # Migrating from `legacy_notify.Notifier` to `notifykit.client.Client`

    | old | new |
    |---|---|
    | `Notifier(backend)` | `Client(backend)` |
    | `n.notify(user, text)` -> `(ok, ref_or_reason)` | `c.publish(Message(user, body))` -> `Receipt` (`.id`); a failure **raises** `DeliveryError` (`.reason`) |
    | `urgent=True` / `urgent=False` | `priority="high"` / `priority="normal"` (the default) |
    | `ttl_s=<seconds>` | `expires_in_ms=<milliseconds>`; the old client truncated: `int(ttl_s * 1000)`; `None` stays `None` |
    | `retry=True` (default) / `retry=False` | `max_attempts=3` (default) / `max_attempts=1` |
    | `n.notify_many(users, text, **kw)` -> list of `(ok, ref_or_reason)` | `c.publish_all([Message(...), ...])` -> list of `Receipt` or `DeliveryError` instances (not raised) |

    Behaviour differences you must account for at the call sites:

    * The old client removed **trailing whitespace** from the text (`text.rstrip()`) before sending. The new client sends the body exactly as given.
    * The old `notify` never raised for delivery failures; the new `publish` does.
''')


def _names(rng, pool, used):
    for _ in range(50):
        n = rng.choice(pool)
        if n not in used:
            used.add(n)
            return n
    raise RuntimeError("out of names")


def n_alert(rng, used):
    fn = _names(rng, ["page_oncall", "alert_oncall", "ring_duty_officer", "raise_alarm"], used)
    urgent = rng.choice([True, True, False])
    retry = rng.choice([True, False])
    ttl = rng.choice([None, 30, 90, 1.5])
    kw_old = f", urgent={urgent}" + ("" if retry else ", retry=False") + ("" if ttl is None else f", ttl_s={ttl}")
    kw_new = f', priority="{"high" if urgent else "normal"}"' + ("" if retry else ", max_attempts=1") + ("" if ttl is None else f", expires_in_ms={int(ttl * 1000)}")
    old = dd(f'''
        def {fn}(notifier, team, text):
            ok, ref = notifier.notify(team["oncall"], text{kw_old})
            if not ok:
                return None
            return ref
    ''')
    new = dd(f'''
        def {fn}(client, team, text):
            try:
                receipt = client.publish(Message(team["oncall"], text.rstrip(){kw_new}))
            except DeliveryError:
                return None
            return receipt.id
    ''')
    return old, new, [(fn, '({"oncall": "u1"}, "disk full  ")'), (fn, '({"oncall": "ghost"}, "x")'), (fn, '({"oncall": "u2"}, "plain")')]


def n_broadcast(rng, used):
    fn = _names(rng, ["broadcast", "notify_roster", "tell_everyone", "announce"], used)
    urgent = rng.choice([True, False])
    old = dd(f'''
        def {fn}(notifier, users, text):
            results = notifier.notify_many(users, text, urgent={urgent})
            sent = len([r for r in results if r[0]])
            failed = [u for u, r in zip(users, results) if not r[0]]
            return sent, failed
    ''')
    new = dd(f'''
        def {fn}(client, users, text):
            results = client.publish_all([Message(u, text.rstrip(), priority="{"high" if urgent else "normal"}") for u in users])
            sent = len([r for r in results if isinstance(r, Receipt)])
            failed = [u for u, r in zip(users, results) if isinstance(r, DeliveryError)]
            return sent, failed
    ''')
    return old, new, [(fn, '(["a", "ghost", "b"], "hello \\n")'), (fn, '([], "none")'), (fn, '(["ghost"], "x")')]


def n_remind(rng, used):
    fn = _names(rng, ["remind", "schedule_nudge", "send_reminder", "nudge"], used)
    mult = rng.choice([30, 60, 90])
    old = dd(f'''
        def {fn}(notifier, user, text, minutes):
            ok, ref = notifier.notify(user, text, ttl_s=minutes * {mult}, retry=False)
            return ref if ok else None
    ''')
    new = dd(f'''
        def {fn}(client, user, text, minutes):
            ttl = minutes * {mult}
            try:
                return client.publish(Message(user, text.rstrip(), expires_in_ms=int(ttl * 1000), max_attempts=1)).id
            except DeliveryError:
                return None
    ''')
    return old, new, [(fn, '("u7", "stand up ", 2)'), (fn, '("ghost", "x", 1)'), (fn, '("u8", "half", 0.5)')]


def n_escalate(rng, used):
    fn = _names(rng, ["escalate", "walk_chain", "try_contacts", "first_reachable"], used)
    old = dd(f'''
        def {fn}(notifier, chain, text):
            for who in chain:
                ok, ref = notifier.notify(who, text, urgent=True)
                if ok:
                    return who
            return None
    ''')
    new = dd(f'''
        def {fn}(client, chain, text):
            for who in chain:
                try:
                    client.publish(Message(who, text.rstrip(), priority="high"))
                except DeliveryError:
                    continue
                return who
            return None
    ''')
    return old, new, [(fn, '(["ghost", "b", "c"], "up ")'), (fn, '(["ghost"], "x")'), (fn, '([], "x")')]


def n_digest(rng, used):
    fn = _names(rng, ["send_digest", "mail_summary", "post_digest", "push_summary"], used)
    sep = rng.choice(["\\n", " | ", "; "])
    old = dd(f'''
        def {fn}(notifier, user, lines):
            text = "{sep}".join(lines) + "\\n"
            ok, _ = notifier.notify(user, text, retry=False)
            return ok
    ''')
    new = dd(f'''
        def {fn}(client, user, lines):
            text = "{sep}".join(lines) + "\\n"
            try:
                client.publish(Message(user, text.rstrip(), max_attempts=1))
            except DeliveryError:
                return False
            return True
    ''')
    return old, new, [(fn, '("u1", ["a", "b"])'), (fn, '("ghost", ["a"])'), (fn, '("u2", [])')]


def n_make(rng, used):
    fn = _names(rng, ["make_notifier", "build_client", "open_channel", "connect"], used)
    old = dd(f'''
        def {fn}(backend):
            return Notifier(backend)
    ''')
    new = dd(f'''
        def {fn}(backend):
            return Client(backend)
    ''')
    return old, new, [(fn, "(rec,)")]


def n_quiet(rng, used):
    fn = _names(rng, ["fire_and_forget", "quiet_send", "best_effort", "try_notify"], used)
    old = dd(f'''
        def {fn}(notifier, users, text):
            for u in users:
                notifier.notify(u, text)
    ''')
    new = dd(f'''
        def {fn}(client, users, text):
            for u in users:
                try:
                    client.publish(Message(u, text.rstrip()))
                except DeliveryError:
                    pass
    ''')
    return old, new, [(fn, '(["a", "ghost", "b"], "psst  ")'), (fn, '([], "x")')]


NOTIFY = dict(
    slug="notify", pkg="notifykit", legacy="legacy_notify", client_module="notifykit.client", client_class="Client", fail="('ghost',)",
    legacy_text=NOTIFY_LEGACY, new_text=NOTIFY_NEW, backend_text=NOTIFY_BACKEND, guide=NOTIFY_GUIDE,
    legacy_imports="from legacy_notify import Notifier\n", new_imports="from notifykit.client import Client, DeliveryError, Message, Receipt\n",
    patterns=[n_alert, n_broadcast, n_remind, n_escalate, n_digest, n_make, n_quiet],
    blurb="the notification client", title="notification client",
)

# ---------------------------------------------------------------------------------------------------------------
# kind 2: blob store
# ---------------------------------------------------------------------------------------------------------------

BLOB_BACKEND = dd('''
    class Recorder(object):
        """In-memory object store backend used by the tests and by local runs."""

        def __init__(self):
            self.objects = {}
            self.events = []

        def write(self, key, data, ctype):
            self.objects[key] = (data, ctype)
            self.events.append(["write", key, data, ctype])

        def read(self, key):
            self.events.append(["read", key])
            return self.objects[key][0] if key in self.objects else None

        def has(self, key):
            return key in self.objects

        def drop(self, key):
            self.events.append(["drop", key])
            return self.objects.pop(key, None) is not None

        def scan(self, prefix):
            self.events.append(["scan", prefix])
            return sorted(k for k in self.objects if k.startswith(prefix))
''')

BLOB_NEW = dd('''
    """Object store client (v2)."""


    class NotFound(KeyError):
        pass


    class Conflict(Exception):
        pass


    class Blob(object):
        def __init__(self, key, payload, media_type="application/octet-stream", if_absent=False):
            if not isinstance(payload, bytes):
                raise TypeError("payload must be bytes")
            self.key = key
            self.payload = payload
            self.media_type = media_type
            self.if_absent = if_absent


    class Store(object):
        def __init__(self, backend):
            self._backend = backend

        def write(self, blob):
            if blob.if_absent and self._backend.has(blob.key):
                raise Conflict(blob.key)
            self._backend.write(blob.key, blob.payload, blob.media_type)

        def read(self, key):
            data = self._backend.read(key)
            if data is None:
                raise NotFound(key)
            return data

        def has(self, key):
            return self._backend.has(key)

        def delete(self, key):
            if not self._backend.drop(key):
                raise NotFound(key)

        def list(self, prefix=""):
            """A lazy iterator over the keys (sorted)."""
            return iter(self._backend.scan(prefix))
''')

BLOB_LEGACY = dd('''
    """Old object store client. Deprecated: use blobkit.client.Store."""


    class BlobStore(object):
        def __init__(self, backend):
            self._b = backend

        def put(self, key, data, content_type=None, overwrite=True):
            """Store data (str is encoded as UTF-8). Returns False, and stores nothing, when overwrite is False and the key exists."""
            if not overwrite and self._b.has(key):
                return False
            if not isinstance(data, bytes):
                data = data.encode("utf-8")
            self._b.write(key, data, content_type or "application/octet-stream")
            return True

        def get(self, key, default=None):
            data = self._b.read(key)
            return default if data is None else data

        def exists(self, key):
            return self._b.has(key)

        def remove(self, key):
            """True if something was removed."""
            return self._b.drop(key)

        def keys(self, prefix=""):
            """A sorted list of keys."""
            return self._b.scan(prefix)
''')

BLOB_GUIDE = dd('''
    # Migrating from `legacy_blobs.BlobStore` to `blobkit.client.Store`

    | old | new |
    |---|---|
    | `BlobStore(backend)` | `Store(backend)` |
    | `s.put(key, data, content_type=ct, overwrite=True)` | `s.write(Blob(key, payload, media_type=ct))`; `payload` must be `bytes` |
    | `s.put(key, data, overwrite=False)` -> `False` when the key exists | `s.write(Blob(key, payload, if_absent=True))` **raises** `Conflict` when the key exists |
    | `content_type=None` | leave out `media_type` (the default is `application/octet-stream`, the same value the old client used) |
    | `s.get(key, default)` | `s.read(key)` **raises** `NotFound` when the key is missing |
    | `s.exists(key)` | `s.has(key)` |
    | `s.remove(key)` -> bool | `s.delete(key)` **raises** `NotFound` when there was nothing to remove |
    | `s.keys(prefix)` -> sorted list | `s.list(prefix)` -> lazy iterator over the sorted keys; wrap in `list(...)` where a list is needed |

    Behaviour differences you must account for at the call sites:

    * The old `put` encoded `str` data as UTF-8 for you; `Blob` accepts bytes only.
    * `get` with a default and `remove` never raised; the new calls do.
''')


def b_save(rng, used):
    fn = _names(rng, ["save_report", "store_summary", "write_note", "keep_record"], used)
    prefix = rng.choice(["reports/", "notes/", "records/", "out/"])
    ctype = rng.choice(["text/plain", "text/markdown", "application/json"])
    old = dd(f'''
        def {fn}(store, name, text):
            store.put("{prefix}" + name, text, content_type="{ctype}")
            return "{prefix}" + name
    ''')
    new = dd(f'''
        def {fn}(client, name, text):
            client.write(Blob("{prefix}" + name, text.encode("utf-8"), media_type="{ctype}"))
            return "{prefix}" + name
    ''')
    return old, new, [(fn, '("a.txt", "h\\u00e9llo")'), (fn, '("b.txt", "")')]


def b_load(rng, used):
    fn = _names(rng, ["load_or_default", "read_setting", "fetch_cached", "get_blob_text"], used)
    old = dd(f'''
        def {fn}(store, key, default):
            data = store.get(key, None)
            if data is None:
                return default
            return data.decode("utf-8")
    ''')
    new = dd(f'''
        def {fn}(client, key, default):
            try:
                data = client.read(key)
            except NotFound:
                return default
            return data.decode("utf-8")
    ''')
    return old, new, [(fn, '("k1", "none")'), (fn, '("seeded", "none")')]


def b_once(rng, used):
    fn = _names(rng, ["put_once", "claim_slot", "create_if_new", "first_writer_wins"], used)
    old = dd(f'''
        def {fn}(store, key, data):
            return store.put(key, data, overwrite=False)
    ''')
    new = dd(f'''
        def {fn}(client, key, data):
            try:
                client.write(Blob(key, data.encode("utf-8"), if_absent=True))
            except Conflict:
                return False
            return True
    ''')
    return old, new, [(fn, '("fresh", "v1")'), (fn, '("seeded", "v2")')]


def b_remove(rng, used):
    fn = _names(rng, ["remove_if_present", "discard", "forget_key", "purge_one"], used)
    old = dd(f'''
        def {fn}(store, key):
            return store.remove(key)
    ''')
    new = dd(f'''
        def {fn}(client, key):
            try:
                client.delete(key)
            except NotFound:
                return False
            return True
    ''')
    return old, new, [(fn, '("seeded",)'), (fn, '("missing",)')]


def b_keys(rng, used):
    fn = _names(rng, ["archive_keys", "list_group", "names_under", "enumerate_prefix"], used)
    old = dd(f'''
        def {fn}(store, prefix):
            keys = store.keys(prefix)
            return [k[len(prefix):] for k in keys]
    ''')
    new = dd(f'''
        def {fn}(client, prefix):
            keys = list(client.list(prefix))
            return [k[len(prefix):] for k in keys]
    ''')
    return old, new, [(fn, '("logs/",)'), (fn, '("zzz/",)')]


def b_size(rng, used):
    fn = _names(rng, ["total_size", "bytes_under", "usage_of", "weigh_prefix"], used)
    old = dd(f'''
        def {fn}(store, prefix):
            return sum(len(store.get(k)) for k in store.keys(prefix))
    ''')
    new = dd(f'''
        def {fn}(client, prefix):
            return sum(len(client.read(k)) for k in client.list(prefix))
    ''')
    return old, new, [(fn, '("logs/",)'), (fn, '("",)'), (fn, '("none/",)')]


def b_make(rng, used):
    fn = _names(rng, ["open_store", "make_store", "connect_blobs", "attach"], used)
    old = dd(f'''
        def {fn}(backend):
            return BlobStore(backend)
    ''')
    new = dd(f'''
        def {fn}(backend):
            return Store(backend)
    ''')
    return old, new, [(fn, "(rec,)")]


BLOBS = dict(
    slug="blobs", pkg="blobkit", legacy="legacy_blobs", client_module="blobkit.client", client_class="Store", fail="()",
    legacy_text=BLOB_LEGACY, new_text=BLOB_NEW, backend_text=BLOB_BACKEND, guide=BLOB_GUIDE,
    legacy_imports="from legacy_blobs import BlobStore\n", new_imports="from blobkit.client import Blob, Conflict, NotFound, Store\n",
    patterns=[b_save, b_load, b_once, b_remove, b_keys, b_size, b_make],
    blurb="the object-store client", title="object store client",
    seed="rec.write('seeded', b'seed-value', 'text/plain'); rec.write('logs/a', b'aa', 'x/y'); rec.write('logs/b', b'bbb', 'x/y'); rec.write('other', b'o', 'x/y'); rec.events.clear()",
)

# ---------------------------------------------------------------------------------------------------------------
# kind 3: metrics
# ---------------------------------------------------------------------------------------------------------------

METRIC_BACKEND = dd('''
    class Recorder(object):
        """In-memory metrics sink used by the tests and by local runs."""

        def __init__(self):
            self.events = []

        def emit(self, name, kind, value, tags):
            self.events.append(["emit", name, kind, value, sorted(tags.items())])
''')

METRIC_NEW = dd('''
    """Metrics client (v2)."""


    class Metrics(object):
        def __init__(self, sink, prefix=""):
            self._sink = sink
            self._prefix = prefix

        def _name(self, name):
            return self._prefix + name

        def incr(self, name, by=1, **tags):
            """Count `by` (any integer, zero included) under `name`; tags are keyword arguments."""
            self._sink.emit(self._name(name), "count", by, dict((k, str(v)) for k, v in tags.items()))

        def observe(self, name, seconds, **tags):
            """Record a duration given in SECONDS (float); the sink receives whole milliseconds, rounded to nearest (halves up)."""
            self._sink.emit(self._name(name), "timing", int(seconds * 1000 + 0.5), dict((k, str(v)) for k, v in tags.items()))

        def level(self, name, value, **tags):
            self._sink.emit(self._name(name), "gauge", value, dict((k, str(v)) for k, v in tags.items()))
''')

METRIC_LEGACY = dd('''
    """Old metrics client. Deprecated: use metrickit.client.Metrics."""


    class Meter(object):
        def __init__(self, sink, prefix=""):
            self._sink = sink
            self._prefix = prefix

        def _emit(self, name, kind, value, tags):
            d = {}
            for t in tags or []:
                k, _, v = t.partition(":")
                d[k] = v
            self._sink.emit(self._prefix + name.lower(), kind, value, d)

        def count(self, name, n=1, tags=None):
            """Does nothing when n is 0. Tags are a list of "key:value" strings."""
            if n == 0:
                return
            self._emit(name, "count", n, tags)

        def timing(self, name, ms, tags=None):
            self._emit(name, "timing", int(ms), tags)

        def gauge(self, name, value, tags=None):
            self._emit(name, "gauge", value, tags)
''')

METRIC_GUIDE = dd('''
    # Migrating from `legacy_metrics.Meter` to `metrickit.client.Metrics`

    | old | new |
    |---|---|
    | `Meter(sink, prefix)` | `Metrics(sink, prefix)` |
    | `m.count(name, n, tags=["k:v", ...])` | `m.incr(name, by=n, k="v", ...)` (tags become keyword arguments) |
    | `m.timing(name, ms, tags=...)` (milliseconds) | `m.observe(name, seconds, **tags)` (**seconds**; the new client rounds to whole milliseconds, halves up) |
    | `m.gauge(name, value, tags=...)` | `m.level(name, value, **tags)` |

    Behaviour differences you must account for at the call sites:

    * The old client **lower-cased the metric name** before emitting; the new one keeps it as given.
    * The old `count(name, 0)` emitted nothing; `incr(name, by=0)` emits a zero. Keep the old behaviour.
    * The old `timing` truncated with `int(ms)`; the new `observe` rounds `seconds * 1000` to the nearest integer (halves up). Pass `ms / 1000.0` and make sure
      the emitted value stays what the old call would have emitted whenever `ms` is a whole number.
    * Tags in the old API were `"key:value"` strings (everything after the first colon is the value).
''')


def m_hit(rng, used):
    fn = _names(rng, ["record_hit", "count_request", "tick_visit", "note_event"], used)
    base = rng.choice(["Web.Hits", "API.Calls", "Site.Views", "Queue.Pops"])
    route = rng.choice(["route", "path", "handler"])
    old = dd(f'''
        def {fn}(meter, {route}, n):
            meter.count("{base}", n, tags=["{route}:" + {route}, "kind:hit"])
    ''')
    new = dd(f'''
        def {fn}(client, {route}, n):
            if n == 0:
                return
            client.incr("{base.lower()}", by=n, {route}={route}, kind="hit")
    ''')
    return old, new, [(fn, '("/home", 3)'), (fn, '("/x", 0)'), (fn, '("a:b", 1)')]


def m_time(rng, used):
    fn = _names(rng, ["record_latency", "time_call", "log_duration", "note_runtime"], used)
    base = rng.choice(["Db.Query", "Cache.Fill", "Render.Page"])
    old = dd(f'''
        def {fn}(meter, op, ms):
            meter.timing("{base}", ms, tags=["op:" + op])
    ''')
    new = dd(f'''
        def {fn}(client, op, ms):
            client.observe("{base.lower()}", ms / 1000.0, op=op)
    ''')
    return old, new, [(fn, '("select", 120)'), (fn, '("insert", 7)'), (fn, '("noop", 0)'), (fn, '("slow", 123456)')]


def m_gauge(rng, used):
    fn = _names(rng, ["report_depth", "set_level", "publish_gauge", "snapshot_size"], used)
    base = rng.choice(["Queue.Depth", "Pool.InUse", "Disk.FreeMB"])
    old = dd(f'''
        def {fn}(meter, shard, value):
            meter.gauge("{base}", value, tags=["shard:%s" % shard])
    ''')
    new = dd(f'''
        def {fn}(client, shard, value):
            client.level("{base.lower()}", value, shard=shard)
    ''')
    return old, new, [(fn, '(3, 17)'), (fn, '("eu", 0)')]


def m_batch(rng, used):
    fn = _names(rng, ["record_batch", "count_each", "tally_many", "bulk_count"], used)
    base = rng.choice(["Jobs.Done", "Msgs.Sent", "Rows.Loaded"])
    old = dd(f'''
        def {fn}(meter, counts):
            for kind in sorted(counts):
                meter.count("{base}", counts[kind], tags=["kind:" + kind, "batch:yes"])
            return len(counts)
    ''')
    new = dd(f'''
        def {fn}(client, counts):
            for kind in sorted(counts):
                if counts[kind] != 0:
                    client.incr("{base.lower()}", by=counts[kind], kind=kind, batch="yes")
            return len(counts)
    ''')
    return old, new, [(fn, '({"a": 2, "b": 0, "c": 5},)'), (fn, '({},)')]


def m_timer(rng, used):
    fn = _names(rng, ["timed", "measure_step", "run_and_time", "with_timing"], used)
    base = rng.choice(["Step.Duration", "Job.Runtime"])
    old = dd(f'''
        def {fn}(meter, name, durations_ms):
            total = 0
            for d in durations_ms:
                meter.timing("{base}", d, tags=["step:" + name])
                total += d
            return total
    ''')
    new = dd(f'''
        def {fn}(client, name, durations_ms):
            total = 0
            for d in durations_ms:
                client.observe("{base.lower()}", d / 1000.0, step=name)
                total += d
            return total
    ''')
    return old, new, [(fn, '("load", [5, 10, 1500])'), (fn, '("none", [])')]


def m_make(rng, used):
    fn = _names(rng, ["make_meter", "open_metrics", "connect_stats", "attach_meter"], used)
    prefix = rng.choice(["svc.", "app.", "edge."])
    old = dd(f'''
        def {fn}(sink):
            return Meter(sink, "{prefix}")
    ''')
    new = dd(f'''
        def {fn}(sink):
            return Metrics(sink, "{prefix}")
    ''')
    return old, new, [(fn, "(rec,)")]


METRICS = dict(
    slug="metrics", pkg="metrickit", legacy="legacy_metrics", client_module="metrickit.client", client_class="Metrics", fail="()",
    legacy_text=METRIC_LEGACY, new_text=METRIC_NEW, backend_text=METRIC_BACKEND, guide=METRIC_GUIDE,
    legacy_imports="from legacy_metrics import Meter\n", new_imports="from metrickit.client import Metrics\n",
    patterns=[m_hit, m_time, m_gauge, m_batch, m_timer, m_make],
    blurb="the metrics client", title="metrics client",
)

KINDS = {k["slug"]: k for k in (NOTIFY, BLOBS, METRICS)}

APP_MODULES = ["alerts", "jobs", "reports", "intake", "sync", "ops", "billing", "cleanup"]

HIDDEN_TEST = dd('''
    import importlib
    import json
    import os
    import sys
    import unittest

    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, ROOT)

    from %(pkg)s.backend import Recorder
    from %(client_module)s import %(client_class)s

    CASES = %(cases)s


    def norm(v):
        return json.loads(json.dumps(v, default=repr))


    def run_case(modname, func, args_expr):
        rec = Recorder()
        %(seed)s
        client = %(client_class)s(rec)
        mod = importlib.import_module(modname)
        args = eval(args_expr, {"rec": rec})
        factory = func.startswith(("make_", "open_", "connect", "attach", "build_"))
        try:
            ret = getattr(mod, func)(*args) if factory else getattr(mod, func)(client, *args)
        except Exception as ex:
            ret = "raises:" + type(ex).__name__
        if factory and type(ret).__name__ == "%(client_class)s":
            ret = "client"
        return norm([ret, rec.events])


    class MigrationTest(unittest.TestCase):
        def test_sites(self):
            bad = []
            for modname, func, args_expr, want in CASES:
                got = run_case(modname, func, args_expr)
                if got != want:
                    bad.append("%%s.%%s%%s -> %%s, want %%s" %% (modname, func, args_expr, got, want))
            self.assertEqual(bad, [], "\\n" + "\\n".join(bad[:6]))

        def test_legacy_is_not_used(self):
            import ast
            for dirpath, _, names in os.walk(os.path.join(ROOT, "app")):
                for n in names:
                    if n.endswith(".py"):
                        tree = ast.parse(open(os.path.join(dirpath, n), encoding="utf-8").read())
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.Import, ast.ImportFrom)):
                                mod = getattr(node, "module", None) or ",".join(a.name for a in node.names)
                                self.assertNotIn("%(legacy)s", mod, "%%s still imports the legacy client" %% n)


    if __name__ == "__main__":
        unittest.main()
''')

TRIPWIRE = dd('''
    """The legacy client has been removed."""
    raise ImportError("the legacy client is gone: migrate to the new client")
''')


def _run_expected(kind, files, cases):
    driver = HIDDEN_TEST % dict(pkg=kind["pkg"], client_module=kind["client_module"], client_class=kind["client_class"], cases="[]",
                                seed=kind.get("seed", "pass"), legacy=kind["legacy"])
    driver = driver.split("class MigrationTest")[0] + dd('''
        out = []
        for modname, func, args_expr in json.load(open("cases_in.json")):
            out.append([modname, func, args_expr, run_case(modname, func, args_expr)])
        print(json.dumps(out))
    ''')
    f = dict(files)
    f["driver.py"] = driver
    f["cases_in.json"] = json.dumps(cases)
    code, out = run_local(f, ["python3", "driver.py"], timeout=60)
    if code != 0:
        raise RuntimeError("reference migration fails:\n" + out[-1800:])
    return json.loads(out.strip().splitlines()[-1])


@family("port-client-migration", category="port", lang="python", kind="refactor", n=9,
        summary="migrate call sites from a legacy internal client API to its replacement (notifications, object store, metrics)")
def gen_clients(rng, n):
    plan = [("notify", 3), ("blobs", 3), ("metrics", 3), ("notify", 5), ("blobs", 5), ("metrics", 4), ("notify", 7), ("blobs", 7), ("metrics", 6)]
    prompts = [
        "We are retiring `{legacy}` ({blurb}). Everything under app/ still calls the old API; move every call site to the new client in `{client_module}`, following docs/MIGRATION.md. The functions in app/ keep their names and arguments, but they now receive the *new* client as their first argument, and what they return and what ends up in the backend must stay exactly as before.",
        "The old `{legacy}` module is being deleted next week. Port the code in app/ to the new client ({client_module}); docs/MIGRATION.md lists the mapping and the behaviour differences. Return values and recorded backend events must not change, including edge cases (failures, empty inputs, whitespace).",
        "migrate app/ off {legacy} onto {client_module}. the guide is docs/MIGRATION.md. careful: the new client raises where the old one returned flags/defaults, and a couple of defaults changed. the functions get the new client object as first arg now",
        "Ticket: drop the deprecated {title}. Acceptance: nothing in app/ imports `{legacy}`; every function behaves as before when handed a `{client_module}` client (same return values, same events in the backend). See docs/MIGRATION.md.",
    ]
    for i in range(n):
        kslug, count = plan[i % len(plan)]
        kind = KINDS[kslug]
        used = set()
        pats = rng.sample(kind["patterns"], min(count, len(kind["patterns"])))
        built = [p(rng, used) for p in pats]
        nmods = 1 if count <= 3 else 2 if count <= 5 else 3
        mod_names = rng.sample(APP_MODULES, nmods)
        buckets = {m: [] for m in mod_names}
        for k, b in enumerate(built):
            buckets[mod_names[k % nmods]].append(b)
        old_files, new_files, cases = {}, {}, []
        pkg = kind["pkg"]
        for mname, bs in buckets.items():
            if not bs:
                continue
            uses_legacy_ctor = any("Notifier(" in b[0] or "BlobStore(" in b[0] or "Meter(" in b[0] for b in bs)
            old_head = f'"""Application code of the service."""\n' + (kind["legacy_imports"] if uses_legacy_ctor else "") + "\n\n"
            new_head = f'"""Application code of the service."""\n' + kind["new_imports"] + "\n\n"
            old_files[f"app/{mname}.py"] = old_head + "\n\n".join(b[0].rstrip("\n") + "\n" for b in bs)
            new_files[f"app/{mname}.py"] = new_head + "\n\n".join(b[1].rstrip("\n") + "\n" for b in bs)
            for b in bs:
                for fn, args in b[2]:
                    cases.append((f"app.{mname}", fn, args))
        old_files["app/__init__.py"] = ""
        base_files = {f"{pkg}/__init__.py": "", f"{pkg}/backend.py": kind["backend_text"], f"{pkg}/client.py": kind["new_text"]}
        exp = _run_expected(kind, {**base_files, **new_files}, cases)
        hidden_test = HIDDEN_TEST % dict(pkg=pkg, client_module=kind["client_module"], client_class=kind["client_class"], cases=repr(exp),
                                         seed=kind.get("seed", "pass"), legacy=kind["legacy"])
        vis_cases = []
        seen = set()
        for c in exp:
            if (c[0], c[1]) not in seen:
                seen.add((c[0], c[1]))
                vis_cases.append(c)
        visible_test = HIDDEN_TEST % dict(pkg=pkg, client_module=kind["client_module"], client_class=kind["client_class"], cases=repr(vis_cases),
                                          seed=kind.get("seed", "pass"), legacy=kind["legacy"])
        visible_test = visible_test.split("        def test_legacy_is_not_used")[0] + "\n\nif __name__ == \"__main__\":\n    unittest.main()\n"
        start = {**old_files, **base_files, f"{kind['legacy']}.py": kind["legacy_text"], "docs/MIGRATION.md": kind["guide"], "tests/test_sites.py": visible_test,
                 "README.md": f"# {pkg} service\n\nA small service that talks to {kind['blurb']}. `app/` holds the application functions; `{kind['legacy']}.py` is the deprecated client and `{kind['client_module'].replace('.', '/')}.py` its replacement (see `docs/MIGRATION.md`).\n"}
        d = 2 + (count >= 4) + (count >= 6) + (1 if kslug != "notify" and count >= 5 else 0)
        d = max(2, min(5, d))
        yield Task(
            slug=f"{i + 1:02d}-{kslug}-{count}-sites",
            prompt=rng.choice(prompts).format(legacy=kind["legacy"], blurb=kind["blurb"], client_module=kind["client_module"], title=kind["title"]),
            difficulty=d,
            lang="python",
            kind="refactor",
            start=start,
            hidden={"tests/test_migration.py": hidden_test, f"{kind['legacy']}.py": TRIPWIRE},
            solution=new_files,
            verify="python3 -m unittest discover -s tests -v",
            protected=[f"{pkg}/client.py", f"{pkg}/backend.py", f"{pkg}/__init__.py", "docs/MIGRATION.md"],
            tags=["api-migration", "client", kslug, "python"],
            notes={"kind": kslug, "patterns": [p.__name__ for p in pats]},
        )
