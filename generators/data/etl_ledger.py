"""Python ETL tasks on structured documents (JSON lines, nested JSON, XML, change logs) for an invented parcel-tracking company."""
import json
from decimal import Decimal

from fx import dd, family
from generators.data import _etlkit as E

WORDS = ["amber", "birch", "cobalt", "dune", "ember", "fjord", "garnet", "harbor", "indigo", "jade", "kelp", "linen"]
NAMES = ["Alma", "Bruno", "Cleo", "Dag", "Esme", "Fynn", "Gita", "Hal", "Ines", "Jory"]


# ---------------------------------------------------------------------------------------------------------------- 1. flatten

def make_flatten(rng, big):
    n = rng.randint(14, 24) if big else 5
    lines = []
    for i in range(n):
        o = {"id": 1000 + i, "user": {"name": rng.choice(NAMES)}}
        if rng.random() < 0.6:
            o["user"]["tags"] = rng.sample(WORDS, rng.randint(1, 3))
        if rng.random() < 0.7:
            o["items"] = [{"sku": rng.choice(WORDS), "qty": rng.randint(1, 5)} | ({"price": rng.choice([2.5, 0.1, 7.3, 12.9])} if rng.random() < 0.4 else {}) for _ in range(rng.randint(1, 3))]
        o["ok"] = rng.random() < 0.7
        if rng.random() < 0.3:
            o["note"] = None
        if rng.random() < 0.2:
            o["meta"] = {}
        if rng.random() < 0.15:
            o["geo"] = {"lat": rng.choice([59.9, 60.4, 58.1]), "lon": rng.choice([10.7, 5.3, 8.0])}
        lines.append(json.dumps(o, ensure_ascii=False))
    lines.insert(rng.randint(1, n - 1), "")
    lines.insert(rng.randint(1, n - 1), "{broken json")
    lines.insert(rng.randint(1, n - 1), "[1, 2, 3]")
    return {"events.jsonl": "\n".join(lines) + "\n"}


REF_FLATTEN = dd('''
    import csv, json, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)


    def scalar(v):
        if v is None:
            return ""
        if v is True:
            return "true"
        if v is False:
            return "false"
        return str(v)


    def flat(o, prefix, out):
        if isinstance(o, dict):
            for k, v in o.items():
                flat(v, prefix + [k], out)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                flat(v, prefix + [str(i)], out)
        else:
            out[".".join(prefix)] = scalar(o)


    rows, bad = [], []
    for n, line in enumerate(open(os.path.join(indir, "events.jsonl"), encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            bad.append(n)
            continue
        if not isinstance(o, dict):
            bad.append(n)
            continue
        r = {}
        flat(o, [], r)
        rows.append(r)
    cols = sorted({k for r in rows for k in r})
    with open(os.path.join(outdir, "flat.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])
    with open(os.path.join(outdir, "rejects.txt"), "w", encoding="utf-8") as f:
        f.write("".join(f"{n}\\n" for n in bad))
''')

DOC_FLATTEN = dd('''
    The parcel scanners write `events.jsonl`: one JSON document per line. Flatten them into a table.

    * A line that is blank is skipped silently. A line that is not valid JSON, or whose JSON value is not an object, is a *reject* (its line number is recorded; the first line is line 1).
    * Each object is flattened into `path -> text` pairs: a nested object key is appended to the path with a dot (`user.name`); an array element is appended by its index (`items.0.sku`, `user.tags.1`).
      Only scalars (string, number, boolean, null) become values; an empty object or an empty array produces no column at all. `null` becomes an empty string, booleans become `true` / `false`,
      numbers and strings are written as they appear in the JSON (numbers in these files are integers or one-decimal numbers like `2.5`).
    * `python3 etl.py IN_DIR OUT_DIR` writes `flat.csv`: the header is every path that occurs in any good object, sorted as plain strings (`items.0.qty` before `items.0.sku` before `items.1.qty` ...);
      one row per good object in input order; a path the object does not have is an empty field. Also `rejects.txt`: the reject line numbers, one per line, in input order (an empty file if none).
''')


# ---------------------------------------------------------------------------------------------------------------- 2. invoices

def make_invoices(rng, big):
    n = rng.randint(8, 14) if big else 3
    docs = []
    for i in range(n):
        lines = []
        for _ in range(rng.randint(1, 5)):
            lines.append({"sku": rng.choice(WORDS), "qty": rng.randint(1, 12), "unit": f"{rng.randint(1, 400)}.{rng.randint(0, 99):02d}", "rate": rng.choice(["0", "0.12", "0.25", "0.0775", "0.15"])})
        docs.append({"invoice": f"INV-{2000 + i}", "customer": rng.choice(NAMES), "lines": lines})
    rng.shuffle(docs)
    return {"invoices.json": json.dumps(docs, indent=1)}


REF_INVOICES = dd('''
    import csv, json, os, sys
    from decimal import Decimal, ROUND_HALF_UP

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    cent = Decimal("0.01")
    out = []
    for inv in json.load(open(os.path.join(indir, "invoices.json"), encoding="utf-8")):
        net = tax = Decimal(0)
        for ln in inv["lines"]:
            n = (Decimal(ln["unit"]) * ln["qty"]).quantize(cent, ROUND_HALF_UP)
            t = (n * Decimal(ln["rate"])).quantize(cent, ROUND_HALF_UP)
            net += n
            tax += t
        out.append((inv["invoice"], inv["customer"], net, tax, net + tax))
    out.sort(key=lambda r: r[0])
    with open(os.path.join(outdir, "totals.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["invoice", "customer", "net", "tax", "gross"])
        for r in out:
            w.writerow([r[0], r[1], f"{r[2]:.2f}", f"{r[3]:.2f}", f"{r[4]:.2f}"])
''')

DOC_INVOICES = dd('''
    `invoices.json` is a list of invoices: `{"invoice": "INV-2001", "customer": "Alma", "lines": [{"sku": ..., "qty": 3, "unit": "12.30", "rate": "0.25"}, ...]}`.
    `unit` is the unit price as a decimal string and `rate` the tax rate as a decimal string (`"0.0775"` is 7.75%). All money is exact decimal arithmetic, rounded half up to cents (0.005 becomes 0.01):

    * the *net* of a line is `qty x unit`, rounded to cents;
    * the *tax* of a line is `net of the line x rate`, rounded to cents (so every line is rounded on its own);
    * an invoice's net, tax and gross (net + tax) are the sums over its lines.

    `python3 etl.py IN_DIR OUT_DIR` writes `totals.csv`: header `invoice,customer,net,tax,gross`, one row per invoice sorted by invoice number (as text), all amounts with two decimals.
''')


# ---------------------------------------------------------------------------------------------------------------- 3. schema versions

def make_versions(rng, big):
    n = rng.randint(14, 24) if big else 6
    evs = []
    for i in range(n):
        v = rng.choice([1, 2, 3])
        day, h, m, s = rng.randint(1, 20), rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59)
        if v == 1:
            evs.append({"v": 1, "user": rng.choice(NAMES), "ts": f"2032-05-{day:02d} {h:02d}:{m:02d}:{s:02d}", "action": rng.choice(["scan", "load", "drop"])})
        elif v == 2:
            import calendar
            epoch = calendar.timegm((2032, 5, day, h, m, s))
            evs.append({"v": 2, "actor": {"id": rng.randint(1, 9), "name": rng.choice(NAMES)}, "time": epoch, "kind": rng.choice(["scan", "load", "drop"])})
        else:
            off = rng.choice(["+00:00", "+02:00", "-05:30", "Z"])
            evs.append({"v": 3, "actor_name": rng.choice(NAMES), "occurred_at": f"2032-05-{day:02d}T{h:02d}:{m:02d}:{s:02d}{off}", "kind": rng.choice(["scan", "load", "drop"])})
    if big:
        evs.insert(3, {"v": 9, "mystery": True})
    return {"events.jsonl": "\n".join(json.dumps(e) for e in evs) + "\n"}


REF_VERSIONS = dd('''
    import datetime, json, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    UTC = datetime.timezone.utc


    def iso(dt):
        return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


    out, skipped = [], 0
    for line in open(os.path.join(indir, "events.jsonl"), encoding="utf-8"):
        e = json.loads(line)
        v = e.get("v")
        if v == 1:
            rec = {"user": e["user"], "ts": iso(datetime.datetime.strptime(e["ts"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)), "kind": e["action"]}
        elif v == 2:
            rec = {"user": e["actor"]["name"], "ts": iso(datetime.datetime.fromtimestamp(e["time"], UTC)), "kind": e["kind"]}
        elif v == 3:
            rec = {"user": e["actor_name"], "ts": iso(datetime.datetime.fromisoformat(e["occurred_at"].replace("Z", "+00:00"))), "kind": e["kind"]}
        else:
            skipped += 1
            continue
        out.append(rec)
    out.sort(key=lambda r: r["ts"])
    with open(os.path.join(outdir, "events.jsonl"), "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, sort_keys=True) + "\\n")
    json.dump({"kept": len(out), "skipped": skipped}, open(os.path.join(outdir, "summary.json"), "w"), sort_keys=True)
''')

DOC_VERSIONS = dd('''
    Scanner firmware changed its event format twice. `events.jsonl` (one JSON object per line) mixes the versions, told apart by the field `v`:

    | v | user | time | kind |
    |---|---|---|---|
    | 1 | `user` | `ts`, text `YYYY-MM-DD HH:MM:SS`, **UTC** | `action` |
    | 2 | `actor.name` | `time`, Unix seconds (an integer) | `kind` |
    | 3 | `actor_name` | `occurred_at`, ISO 8601 with an offset: `2032-05-04T10:00:00+02:00`, `-05:30`, `+00:00` or `Z` | `kind` |

    Any other `v` is *skipped* (not an error).

    `python3 etl.py IN_DIR OUT_DIR` writes `events.jsonl` into `OUT_DIR`: one object `{"user": ..., "ts": ..., "kind": ...}` per kept event, with `ts` converted to UTC and written as `YYYY-MM-DDTHH:MM:SSZ`.
    Sort by `ts`; events with the same `ts` keep their input order. Also `summary.json`: `{"kept": N, "skipped": M}`.
''')


# ---------------------------------------------------------------------------------------------------------------- 4. merge patch

def rnd_doc(rng, depth=0):
    d = {}
    for k in rng.sample(["name", "color", "size", "tags", "owner", "limits", "flags", "notes"], rng.randint(2, 5)):
        if k == "tags":
            d[k] = rng.sample(WORDS, rng.randint(1, 3))
        elif k in ("owner", "limits", "flags") and depth < 2:
            d[k] = rnd_doc(rng, depth + 1) if rng.random() < 0.7 else rng.choice(WORDS)
        else:
            d[k] = rng.choice([rng.choice(WORDS), rng.randint(1, 99), rng.random() < 0.5])
    return d


def make_patches(rng, big):
    n = rng.randint(5, 8) if big else 3
    docs = {f"d{i + 1}": rnd_doc(rng) for i in range(n)}
    patches = []
    for k in range(rng.randint(6, 12) if big else 4):
        target = rng.choice(list(docs))
        p = {}
        for key in rng.sample(["name", "color", "size", "tags", "owner", "limits", "flags", "notes"], rng.randint(1, 3)):
            c = rng.random()
            if c < 0.3:
                p[key] = None
            elif c < 0.5:
                p[key] = rnd_doc(rng, 1)
            elif key == "tags":
                p[key] = rng.sample(WORDS, 2)
            else:
                p[key] = rng.choice([rng.choice(WORDS), rng.randint(1, 99)])
        patches.append({"doc": target, "patch": p})
    return {"docs.json": json.dumps([{"id": k, "body": v} for k, v in docs.items()], indent=1), "patches.jsonl": "\n".join(json.dumps(p) for p in patches) + "\n"}


REF_PATCHES = dd('''
    import json, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)


    def merge(target, patch):
        if not isinstance(patch, dict):
            return patch
        if not isinstance(target, dict):
            target = {}
        target = dict(target)
        for k, v in patch.items():
            if v is None:
                target.pop(k, None)
            else:
                target[k] = merge(target.get(k), v)
        return target


    docs = {d["id"]: d["body"] for d in json.load(open(os.path.join(indir, "docs.json"), encoding="utf-8"))}
    for line in open(os.path.join(indir, "patches.jsonl"), encoding="utf-8"):
        if line.strip():
            p = json.loads(line)
            docs[p["doc"]] = merge(docs[p["doc"]], p["patch"])
    json.dump([{"id": k, "body": docs[k]} for k in sorted(docs)], open(os.path.join(outdir, "result.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
''')

DOC_PATCHES = dd('''
    `docs.json` holds JSON documents `[{"id": "d1", "body": {...}}, ...]` and `patches.jsonl` a list of updates, one JSON object per line: `{"doc": "d1", "patch": {...}}`, to be applied **in file order**.
    A patch is an RFC 7396 *JSON merge patch*:

    * if the patch is not an object it replaces the whole value (this includes arrays: an array in a patch replaces the old array, it is not merged);
    * if it is an object it is merged key by key into the target: a key whose patch value is `null` is **removed** from the target (if it exists); any other value is merged recursively
      (when the target value is not an object, or is missing, it is treated as an empty object first).

    `python3 etl.py IN_DIR OUT_DIR` writes `result.json`: the list `[{"id": ..., "body": ...}]` of all documents after all patches, sorted by id (as text).
''')


# ---------------------------------------------------------------------------------------------------------------- 5. daily rollup

def make_rollup(rng, big):
    n = rng.randint(80, 140) if big else 20
    lines = []
    for _ in range(n):
        day = rng.randint(1, 4 if big else 2)
        lines.append(json.dumps({"ts": f"2032-06-{day:02d}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}Z", "user": rng.choice(NAMES), "latency_ms": rng.choice([12, 18, 25, 40, 55, 90, 140, 300, 900]) + rng.randint(0, 9), "status": rng.choice([200] * 8 + [404, 500, 503])}))
    return {"requests.jsonl": "\n".join(lines) + "\n"}


REF_ROLLUP = dd('''
    import json, math, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    days = {}
    for line in open(os.path.join(indir, "requests.jsonl"), encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            days.setdefault(r["ts"][:10], []).append(r)


    def pct(vals, p):
        vals = sorted(vals)
        return vals[max(1, math.ceil(p * len(vals) / 100)) - 1]


    out = {}
    for d, rs in sorted(days.items()):
        lat = [r["latency_ms"] for r in rs]
        out[d] = {"requests": len(rs), "users": len({r["user"] for r in rs}), "errors": sum(1 for r in rs if r["status"] >= 500), "p50": pct(lat, 50), "p95": pct(lat, 95)}
    json.dump(out, open(os.path.join(outdir, "rollup.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
''')

DOC_ROLLUP = dd('''
    `requests.jsonl` has one request per line: `{"ts": "2032-06-01T12:30:05Z", "user": "Alma", "latency_ms": 42, "status": 200}`. Group the requests by UTC day (`ts[:10]`).

    `python3 etl.py IN_DIR OUT_DIR` writes `rollup.json`: an object keyed by day (`"2032-06-01"`), each value an object with
    `requests` (count), `users` (number of distinct users), `errors` (requests with status 500 or more), `p50` and `p95` (the 50th and 95th percentile of `latency_ms`).
    Percentiles use the **nearest-rank** method: sort the latencies; the p-th percentile is the value at 1-based position `ceil(p / 100 x n)` (at least 1); no interpolation. Only days that occur in the input appear.
''')


# ---------------------------------------------------------------------------------------------------------------- 6. sessions

def make_sessions(rng, big):
    users = rng.sample(NAMES, 4 if big else 2)
    rows = []
    t0 = 1_780_000_000
    for u in users:
        t = t0 + rng.randint(0, 5000)
        for _ in range(rng.randint(8, 18) if big else 6):
            t += rng.choice([5, 20, 60, 300, 1799, 1800, 1801, 4000, 9000])
            rows.append((u, t, rng.choice(["/", "/track", "/rates", "/help", "/account", "/pay"])))
    rng.shuffle(rows)
    return {"clicks.csv": "user,ts,page\n" + "\n".join(f"{u},{t},{p}" for u, t, p in rows) + "\n"}


REF_SESSIONS = dd('''
    import csv, datetime, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    rows = list(csv.DictReader(open(os.path.join(indir, "clicks.csv"), newline="", encoding="utf-8")))
    by = {}
    for r in rows:
        by.setdefault(r["user"], []).append((int(r["ts"]), r["page"]))
    out = []
    for u in sorted(by):
        ev = sorted(by[u], key=lambda x: x[0])
        sess = []
        for ts, page in ev:
            if sess and ts - sess[-1][-1][0] <= 1800:
                sess[-1].append((ts, page))
            else:
                sess.append([(ts, page)])
        for i, s in enumerate(sess, 1):
            f = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            out.append([f"{u}#{i}", u, f(s[0][0]), f(s[-1][0]), len(s), s[-1][0] - s[0][0], s[0][1], s[-1][1]])
    with open(os.path.join(outdir, "sessions.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\\n")
        w.writerow(["session", "user", "start", "end", "pages", "duration_s", "first_page", "last_page"])
        w.writerows(out)
''')

DOC_SESSIONS = dd('''
    `clicks.csv` (`user,ts,page`) lists page views with Unix-second timestamps, in no particular order. A user's *session* is a maximal run of that user's views (sorted by timestamp) in which each view is at most
    **1800 seconds** after the previous one; a gap of 1801 seconds or more starts a new session. Views of the same user with equal timestamps keep their input order.

    `python3 etl.py IN_DIR OUT_DIR` writes `sessions.csv` with the header `session,user,start,end,pages,duration_s,first_page,last_page`, one row per session, ordered by user name and then start time.
    `session` is `<user>#<n>` where n counts the user's sessions from 1 in time order; `start` and `end` are the first and last view as `YYYY-MM-DDTHH:MM:SSZ` (UTC); `pages` is the number of views;
    `duration_s` is end minus start in seconds; `first_page` / `last_page` are the pages of the first and last view.
''')


# ---------------------------------------------------------------------------------------------------------------- 7. snapshot diff

def make_diff(rng, big):
    n = rng.randint(10, 18) if big else 5
    old = {}
    for i in range(n):
        old[i + 1] = {"id": i + 1, "name": rng.choice(WORDS), "qty": rng.randint(0, 20), "loc": {"shelf": rng.choice("ABC"), "bin": rng.randint(1, 9)}, "tags": rng.sample(WORDS, 2)}
    new = {k: json.loads(json.dumps(v)) for k, v in old.items()}
    for k in rng.sample(list(new), max(2, n // 3)):
        c = rng.choice(["qty", "name", "loc", "tags", "drop", "add"])
        if c == "qty":
            new[k]["qty"] += rng.randint(1, 5)
        elif c == "name":
            new[k]["name"] = rng.choice([w for w in WORDS if w != old[k]["name"]])
        elif c == "loc":
            new[k]["loc"]["bin"] = (new[k]["loc"]["bin"] % 9) + 1
        elif c == "tags":
            new[k]["tags"].reverse() if rng.random() < 0.5 else new[k]["tags"].append("extra")
        elif c == "drop":
            del new[k]["tags"]
        else:
            new[k]["color"] = rng.choice(WORDS)
    for k in rng.sample(list(new), 2 if big else 1):
        del new[k]
    both = [k for k in new if k in old and "tags" in new[k] and len(new[k]["tags"]) == 2 and new[k]["tags"] == old[k]["tags"]]
    if both:  # same tags in the opposite order: the order matters
        new[both[0]]["tags"] = old[both[0]]["tags"][::-1]
    for j in range(rng.randint(1, 3)):
        new[100 + j] = {"id": 100 + j, "name": rng.choice(WORDS), "qty": 1, "loc": {"shelf": "Z", "bin": 1}, "tags": []}
    dump = lambda d: json.dumps(list(d.values()), indent=1)
    items_new = list(new.values())
    rng.shuffle(items_new)
    return {"old.json": dump(old), "new.json": json.dumps(items_new, indent=1)}


REF_DIFF = dd('''
    import json, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    old = {r["id"]: r for r in json.load(open(os.path.join(indir, "old.json"), encoding="utf-8"))}
    new = {r["id"]: r for r in json.load(open(os.path.join(indir, "new.json"), encoding="utf-8"))}
    changed = {}
    for k in sorted(old.keys() & new.keys()):
        fields = {}
        for f in sorted(old[k].keys() | new[k].keys()):
            a, b = old[k].get(f), new[k].get(f)
            if f in old[k] and f in new[k] and a == b:
                continue
            fields[f] = [a, b]
        if fields:
            changed[str(k)] = fields
    json.dump({"added": sorted(new.keys() - old.keys()), "removed": sorted(old.keys() - new.keys()), "changed": changed}, open(os.path.join(outdir, "diff.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
''')

DOC_DIFF = dd('''
    `old.json` and `new.json` are two snapshots of an inventory: each is a JSON list of objects with a unique integer `id` (the objects have a few more fields, some nested; lists and nested objects are compared as whole values, order inside lists matters).

    `python3 etl.py IN_DIR OUT_DIR` writes `diff.json`:

    * `added`: ids that exist only in `new.json`, ascending;
    * `removed`: ids that exist only in `old.json`, ascending;
    * `changed`: an object keyed by the id **as a string**, for every id in both snapshots whose objects differ; its value maps each differing field to `[old, new]`.
      A field that exists in only one of the two objects is differing, with `null` standing for the missing side. Fields that are equal are left out; ids without any difference do not appear.
''')


# ---------------------------------------------------------------------------------------------------------------- 8. path tree

def make_tree(rng, big):
    n = rng.randint(20, 40) if big else 7
    dirs = ["src", "docs", "assets/img", "assets/fonts", "src/core", "src/util", "tests"]
    lines = []
    for i in range(n):
        d = rng.choice(dirs)
        lines.append(f"{rng.randint(0, 5000)} {d}/{rng.choice(WORDS)}{rng.randint(1, 5)}.{rng.choice(['py', 'md', 'png', 'ttf', 'txt'])}")
    lines += [f"{rng.randint(1, 50)} {rng.choice(WORDS)}.cfg" for _ in range(2)]
    lines += [lines[0].split(" ", 1)[0] + " " + lines[0].split(" ", 1)[1]]  # the same path listed twice: sizes add up
    rng.shuffle(lines)
    return {"files.txt": "\n".join(lines) + "\n"}


REF_TREE = dd('''
    import json, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    sizes = {}
    for line in open(os.path.join(indir, "files.txt"), encoding="utf-8"):
        line = line.rstrip("\\n")
        if not line.strip():
            continue
        size, path = line.split(" ", 1)
        sizes[path] = sizes.get(path, 0) + int(size)
    root = {"name": ".", "children": {}}
    for path, size in sizes.items():
        node = root
        parts = path.split("/")
        for p in parts[:-1]:
            node = node["children"].setdefault(p, {"name": p, "children": {}})
        node["children"][parts[-1]] = {"name": parts[-1], "size": size}


    def fin(n):
        if "children" not in n:
            return n
        kids = [fin(c) for _, c in sorted(n["children"].items())]
        return {"name": n["name"], "size": sum(k["size"] for k in kids), "children": kids}


    json.dump(fin(root), open(os.path.join(outdir, "tree.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
''')

DOC_TREE = dd('''
    `files.txt` lists files, one per line: `SIZE PATH` (size in bytes, one space, then the relative path with `/` separators; no leading slash; paths contain no spaces). A path may be listed several times; its sizes add up.

    `python3 etl.py IN_DIR OUT_DIR` writes `tree.json`: the directory tree as nested objects. Every node has `name` and `size`; a directory also has `children`, a list sorted by `name` (plain string order, files and directories mixed).
    A file's size is its total from the listing; a directory's size is the sum of its children. The root is a directory named `"."` that holds all top-level entries.
''')


# ---------------------------------------------------------------------------------------------------------------- 9. xml config

def make_xml(rng, big):
    n = rng.randint(6, 10) if big else 3
    out = ['<?xml version="1.0" encoding="UTF-8"?>', "<fleet>", f'  <defaults port="{rng.choice([8080, 9000])}" zone="{rng.choice(["north", "south"])}"/>', "  <!-- generated -->"]
    for i in range(n):
        attrs = f'id="srv{i + 1:02d}" host="{rng.choice(WORDS)}-{i + 1}.example.net"'
        if rng.random() < 0.5:
            attrs += f' port="{rng.randint(1000, 9999)}"'
        if rng.random() < 0.4:
            attrs += f' zone="{rng.choice(["east", "west"])}"'
        out.append(f"  <server {attrs}>")
        for t in rng.sample(WORDS, rng.randint(0, 3)):
            out.append(f"    <tag>{t}</tag>")
        if rng.random() < 0.3:
            out.append("    <note>fish &amp; chips &lt;beta&gt;</note>")
        out.append("  </server>")
    out.append("</fleet>")
    return {"fleet.xml": "\n".join(out) + "\n"}


REF_XML = dd('''
    import json, os, sys
    import xml.etree.ElementTree as ET

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    root = ET.parse(os.path.join(indir, "fleet.xml")).getroot()
    d = root.find("defaults")
    dport, dzone = int(d.get("port")), d.get("zone")
    out = []
    for s in root.findall("server"):
        rec = {"id": s.get("id"), "host": s.get("host"), "port": int(s.get("port", dport)), "zone": s.get("zone", dzone), "tags": sorted(t.text for t in s.findall("tag"))}
        note = s.find("note")
        if note is not None:
            rec["note"] = note.text
        out.append(rec)
    out.sort(key=lambda r: r["id"])
    json.dump(out, open(os.path.join(outdir, "servers.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
''')

DOC_XML = dd('''
    `fleet.xml` describes servers: a `<defaults port=".." zone=".."/>` element and `<server id=".." host=".." [port=".."] [zone=".."]>` elements, each with zero or more `<tag>` children and optionally one `<note>`.
    XML comments and entities (`&amp;`, `&lt;`) appear and must be handled like any XML parser does.

    `python3 etl.py IN_DIR OUT_DIR` writes `servers.json`: a list of objects sorted by `id`, each with `id`, `host`, `port` (an integer; the server's own attribute, else the default), `zone` (own or default),
    `tags` (the tag texts as a list sorted alphabetically, empty when there are none) and, only when the server has a `<note>`, `note` (its decoded text).
''')


# ---------------------------------------------------------------------------------------------------------------- 10. change log

def make_cdc(rng, big):
    n = rng.randint(8, 14) if big else 4
    rows = [(i + 1, rng.choice(WORDS), rng.randint(0, 30)) for i in range(n)]
    changes = []
    seq = 0
    for _ in range(rng.randint(14, 28) if big else 7):
        seq += rng.randint(1, 3)
        rid = rng.randint(1, n + 3)
        if rng.random() < 0.25:
            changes.append({"seq": seq, "op": "delete", "id": rid})
        else:
            s = {}
            if rng.random() < 0.7:
                s["qty"] = rng.randint(0, 40)
            if rng.random() < 0.5 or not s:
                s["name"] = rng.choice(WORDS)
            changes.append({"seq": seq, "op": "upsert", "id": rid, "set": s})
    if big:
        changes.append(dict(changes[2]))  # a duplicated delivery of the same change
    rng.shuffle(changes)
    top = max(c["seq"] for c in changes) + 1
    changes += [{"seq": top, "op": "upsert", "id": 1, "set": {"qty": 111}}, {"seq": top, "op": "upsert", "id": 1, "set": {"qty": 999}}]  # same seq twice: the first one in the file wins
    return {"snapshot.csv": "id,name,qty\n" + "\n".join(f"{a},{b},{c}" for a, b, c in rows) + "\n", "changes.jsonl": "\n".join(json.dumps(c) for c in changes) + "\n"}


REF_CDC = dd('''
    import csv, json, os, sys

    indir, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    table = {int(r["id"]): {"name": r["name"], "qty": int(r["qty"])} for r in csv.DictReader(open(os.path.join(indir, "snapshot.csv"), newline="", encoding="utf-8"))}
    seen, changes = set(), []
    for line in open(os.path.join(indir, "changes.jsonl"), encoding="utf-8"):
        if not line.strip():
            continue
        c = json.loads(line)
        if c["seq"] in seen:
            continue
        seen.add(c["seq"])
        changes.append(c)
    for c in sorted(changes, key=lambda c: c["seq"]):
        if c["op"] == "delete":
            table.pop(c["id"], None)
        else:
            row = table.setdefault(c["id"], {"name": "", "qty": 0})
            row.update(c.get("set", {}))
    with open(os.path.join(outdir, "table.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\\n")
        w.writerow(["id", "name", "qty"])
        for k in sorted(table):
            w.writerow([k, table[k]["name"], table[k]["qty"]])
''')

DOC_CDC = dd('''
    `snapshot.csv` (`id,name,qty`) is a table dump. `changes.jsonl` is a change log delivered out of order: one JSON object per line, either `{"seq": 7, "op": "delete", "id": 3}`
    or `{"seq": 8, "op": "upsert", "id": 5, "set": {"qty": 10}}` (`set` holds any of the fields `name` and `qty`).

    * Apply the changes in ascending `seq` order. A `seq` that occurs more than once is applied **once**: only the first line carrying it counts (the rest are duplicate deliveries and are ignored).
    * `delete` removes the row if it exists (nothing happens otherwise). `upsert` changes the given fields of the row; if the row does not exist it is created first with `name` empty and `qty` 0.
      A row that was deleted and later upserted comes back with only the fields of that upsert.

    `python3 etl.py IN_DIR OUT_DIR` writes `table.csv`: header `id,name,qty`, the final rows sorted by `id` numerically.
''')


def spec(slug, d, prompt, doc, make, ref, outputs, **kw):
    return E.EtlSpec(slug=slug, d=d, prompt=prompt, doc=doc, make=make, ref=ref, outputs=outputs, **kw)


SPECS = [
    spec("jsonl-flatten", 2, "Write `etl.py` that flattens the nested JSON lines of `events.jsonl` into one CSV table with dotted column paths, and records the lines it cannot use. Read README.md for the exact rules.", DOC_FLATTEN, make_flatten, REF_FLATTEN, {"flat.csv": "csv", "rejects.txt": "text"},
         wrong=(REF_FLATTEN.replace('v is True', 'v is True and False').replace('return "true"', 'return "True"'),)),
    spec("invoice-tax", 3, "Write `etl.py` that computes net, tax and gross of every invoice in `invoices.json` with exact decimal arithmetic and per-line rounding. Read README.md.", DOC_INVOICES, make_invoices, REF_INVOICES, {"totals.csv": "csv"},
         wrong=(REF_INVOICES.replace("t = (n * Decimal(ln[\"rate\"])).quantize(cent, ROUND_HALF_UP)", "t = Decimal(0)").replace("net += n\n            tax += t", "net += n\n            tax += (n * Decimal(ln[\"rate\"]))"),)),
    spec("schema-versions", 3, "Write `etl.py` that normalises the three event formats in `events.jsonl` into one schema with UTC timestamps. Read README.md.", DOC_VERSIONS, make_versions, REF_VERSIONS, {"events.jsonl": "text", "summary.json": "json"},
         wrong=(REF_VERSIONS.replace('.astimezone(UTC)', ''),)),
    spec("merge-patches", 3, "Write `etl.py` that applies the JSON merge patches in `patches.jsonl` to the documents in `docs.json`. Read README.md.", DOC_PATCHES, make_patches, REF_PATCHES, {"result.json": "json"},
         wrong=(REF_PATCHES.replace('target.pop(k, None)', 'target[k] = None'),)),
    spec("daily-rollup", 3, "Write `etl.py` that rolls the request log in `requests.jsonl` up to one summary per UTC day, with nearest-rank percentiles. Read README.md.", DOC_ROLLUP, make_rollup, REF_ROLLUP, {"rollup.json": "json"},
         wrong=(REF_ROLLUP.replace("math.ceil(p * len(vals) / 100)", "int(p * len(vals) / 100)"),)),
    spec("sessionise-clicks", 4, "Write `etl.py` that groups the page views in `clicks.csv` into sessions with a 30-minute inactivity rule. Read README.md.", DOC_SESSIONS, make_sessions, REF_SESSIONS, {"sessions.csv": "csv"},
         wrong=(REF_SESSIONS.replace("<= 1800", "< 1800"),)),
    spec("snapshot-diff", 4, "Write `etl.py` that compares the two inventory snapshots `old.json` and `new.json` and reports added, removed and changed items. Read README.md.", DOC_DIFF, make_diff, REF_DIFF, {"diff.json": "json"},
         wrong=(REF_DIFF.replace("if f in old[k] and f in new[k] and a == b:", "if f in old[k] and f in new[k] and (sorted(a) == sorted(b) if isinstance(a, list) else a == b):"),)),
    spec("path-tree", 3, "Write `etl.py` that turns the flat file listing in `files.txt` into a nested JSON tree with directory sizes. Read README.md.", DOC_TREE, make_tree, REF_TREE, {"tree.json": "json"},
         wrong=(REF_TREE.replace("sizes[path] = sizes.get(path, 0) + int(size)", "sizes[path] = int(size)"),)),
    spec("xml-servers", 3, "Write `etl.py` that reads `fleet.xml` and writes the servers as JSON with the defaults applied. Read README.md.", DOC_XML, make_xml, REF_XML, {"servers.json": "json"},
         wrong=(REF_XML.replace('int(s.get("port", dport))', 'int(s.get("port") or 0)'),)),
    spec("apply-change-log", 4, "Write `etl.py` that applies the out-of-order change log in `changes.jsonl` to the table in `snapshot.csv`. Read README.md.", DOC_CDC, make_cdc, REF_CDC, {"table.csv": "csv"},
         wrong=(REF_CDC.replace('if c["seq"] in seen:', 'if False:'),)),
]


@family("data-etl-documents", category="data", lang="python", kind="feature", n=len(SPECS),
        summary="python ETL on structured documents: JSON-lines flattening, exact-decimal invoices, schema versions, merge patches, rollups with nearest-rank percentiles, sessions, snapshot diffs, trees, XML, change logs")
def etl_documents(rng, n):
    return E.etl_tasks("etl-documents", SPECS, rng, n, "Parcel-tracking data wrangling")
