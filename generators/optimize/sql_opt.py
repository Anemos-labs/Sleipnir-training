"""SQL optimisation on SQLite: add the right index, or rewrite the query. A Python checker builds a large deterministic database, compares the
results with an independent computation and counts SQLite virtual-machine steps (progress handler); runaway queries are cut off by a step budget."""
from __future__ import annotations

import json
import re
from string import Template

from fx import Task, family, merged, run

from ._kit import prove_opt

SQL_ALL = "python3 checks/verify.py"
SQL_CORRECT = "python3 checks/verify.py correct"
SQL_PERF = "python3 checks/verify.py perf"
SQL_MEASURE = "python3 checks/verify.py measure"

CHECKER = r'''import json
import pathlib
import random
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUERY_FILE = "queries/@QNAME@.sql"
STEP = 50
LIMIT = @LIMIT@
BUDGET_FACTOR = 40


@SEED@


@PARAMS@


@EXPECTED@


class Over(Exception):
    pass


def build(scale):
    conn = sqlite3.connect(":memory:")
    conn.executescript((ROOT / "schema.sql").read_text())
    rng = random.Random(@SEEDN@)
    data = seed(conn, rng, scale)
    conn.commit()
    return conn, data, rng


def run_query(conn, sql, params, budget):
    steps = [0]

    def handler():
        steps[0] += 1
        return 1 if budget is not None and steps[0] * STEP > budget else 0

    conn.set_progress_handler(handler, STEP)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as e:
        if "interrupt" in str(e).lower():
            raise Over()
        raise
    finally:
        conn.set_progress_handler(None, 0)
    return [tuple(r) for r in rows], steps[0] * STEP


def check(scale, budget, report):
    conn, data, rng = build(scale)
    sql = (ROOT / QUERY_FILE).read_text()
    total = 0
    for p in make_params(rng, data):
        try:
            rows, steps = run_query(conn, sql, p, None if budget is None else budget - total)
        except Over:
            return "over", total
        total += steps
        want = expected(data, p)
        if rows != want:
            print("wrong result for %s:\n  got  %s\n  want %s" % (json.dumps(p), rows[:5], want[:5]))
            return "wrong", total
    return "ok", total


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    failures = 0
    if mode in ("all", "correct"):
        state, _ = check(SMALL, None, False)
        if state != "ok":
            print("correctness check failed")
            failures += 1
    if mode in ("all", "perf", "measure"):
        state, steps = check(BIG, None if mode == "measure" else LIMIT * BUDGET_FACTOR, True)
        if mode == "measure":
            print("MEASURE|%s|%d" % (state, steps))
            return 0
        if state == "over":
            print("PERF: the queries used more than %d virtual machine steps (limit %d) on a large database: the query plan is far too expensive" % (LIMIT * BUDGET_FACTOR, LIMIT))
            failures += 1
        elif state == "wrong":
            failures += 1
        elif steps > LIMIT:
            print("PERF: the queries used %d virtual machine steps on a large database (limit %d): the query plan is too expensive" % (steps, LIMIT))
            failures += 1
    if failures:
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

SEEDS = {}


# ---------------------------------------------------------------------------------------------------------------------
# index shapes (the fix goes into schema.sql)
# ---------------------------------------------------------------------------------------------------------------------
INDEX_SHAPES = {
    "lookup": dict(
        d=2, qname="by_owner", scale=("SMALL = 1\nBIG = 20", ), fix='CREATE INDEX idx_${C}_$FK ON $C($FK);',
        schema='''CREATE TABLE $P (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE $C (id INTEGER PRIMARY KEY, $FK INTEGER NOT NULL, kind TEXT NOT NULL, amount INTEGER NOT NULL);
''', query='''-- amounts of one $pk's $ck rows
SELECT id, amount FROM $C WHERE $FK = :p ORDER BY id;
''', seed='''def seed(conn, rng, scale):
    np, nc = 50 * scale, 2000 * scale
    parents = [(i + 1, "name%d" % i) for i in range(np)]
    rows = [(i + 1, rng.randrange(1, np + 1), rng.choice(["a", "b", "c"]), rng.randrange(1, 1000)) for i in range(nc)]
    conn.executemany("INSERT INTO $P VALUES (?, ?)", parents)
    conn.executemany("INSERT INTO $C VALUES (?, ?, ?, ?)", rows)
    return {"np": np, "rows": rows}''', params='''def make_params(rng, data):
    return [{"p": k} for k in rng.sample(range(1, data["np"] + 1), 25)]''',
        expected='''def expected(data, p):
    return [(i, amount) for (i, fk, kind, amount) in data["rows"] if fk == p["p"]]''', limit=60000,
        spec="Returns `(id, amount)` of every `{C}` row of one `{P}` (named parameter `:p`), ordered by id."),
    "range_top": dict(
        d=2, qname="recent", scale=("SMALL = 1\nBIG = 15", ), fix='CREATE INDEX idx_${C}_$TS ON $C($TS);',
        schema='''CREATE TABLE $C (id INTEGER PRIMARY KEY, device TEXT NOT NULL, $TS INTEGER NOT NULL, value INTEGER NOT NULL);
''', query='''-- the first 20 $ck rows at or after a point in time
SELECT id, $TS FROM $C WHERE $TS >= :t ORDER BY $TS, id LIMIT 20;
''', seed='''def seed(conn, rng, scale):
    n = 3000 * scale
    rows = [(i + 1, "d%d" % rng.randrange(40), rng.randrange(1000000), rng.randrange(100)) for i in range(n)]
    conn.executemany("INSERT INTO $C VALUES (?, ?, ?, ?)", rows)
    return {"rows": rows}''', params='''def make_params(rng, data):
    return [{"t": rng.randrange(0, 900000)} for _ in range(12)]''',
        expected='''def expected(data, p):
    rows = sorted((ts, i) for (i, dev, ts, v) in data["rows"] if ts >= p["t"])[:20]
    return [(i, ts) for ts, i in rows]''', limit=40000,
        spec="Returns `(id, {TS})` of the first 20 `{C}` rows whose `{TS}` is at least `:t`, ordered by `{TS}` then id."),
    "composite": dict(
        d=3, qname="open_since", scale=("SMALL = 1\nBIG = 15", ), fix='DROP INDEX idx_${C}_status;\nCREATE INDEX idx_${C}_status_created ON $C(status, created);',
        schema='''CREATE TABLE $C (id INTEGER PRIMARY KEY, status TEXT NOT NULL, created INTEGER NOT NULL, owner INTEGER NOT NULL);
CREATE INDEX idx_${C}_status ON $C(status);
''', query='''-- the 30 oldest $ck rows of a status created at or after a time
SELECT id FROM $C WHERE status = :s AND created >= :c ORDER BY created, id LIMIT 30;
''', seed='''def seed(conn, rng, scale):
    n = 3000 * scale
    rows = [(i + 1, rng.choice(["new", "open", "held", "done", "void"]), rng.randrange(1000000), rng.randrange(100)) for i in range(n)]
    conn.executemany("INSERT INTO $C VALUES (?, ?, ?, ?)", rows)
    return {"rows": rows}''', params='''def make_params(rng, data):
    return [{"s": rng.choice(["new", "open", "held", "done"]), "c": rng.randrange(0, 900000)} for _ in range(12)]''',
        expected='''def expected(data, p):
    rows = sorted((created, i) for (i, st, created, o) in data["rows"] if st == p["s"] and created >= p["c"])[:30]
    return [(i,) for created, i in rows]''', limit=40000,
        spec="Returns the ids of the 30 `{C}` rows with status `:s` and `created >= :c` that were created first (ties by id)."),
    "expr": dict(
        d=3, qname="find_by_email", scale=("SMALL = 1\nBIG = 20", ), fix='CREATE INDEX idx_${C}_email_lower ON $C(lower(email));',
        schema='''CREATE TABLE $C (id INTEGER PRIMARY KEY, email TEXT NOT NULL, name TEXT NOT NULL);
''', query='''-- case-insensitive lookup of a $pk by e-mail address
SELECT id, name FROM $C WHERE lower(email) = lower(:e) ORDER BY id;
''', seed='''def seed(conn, rng, scale):
    n = 2500 * scale
    rows = [(i + 1, ("User%d@Example.%s" % (i, rng.choice(["org", "com"]))), "name%d" % i) for i in range(n)]
    conn.executemany("INSERT INTO $C VALUES (?, ?, ?)", rows)
    return {"rows": rows}''', params='''def make_params(rng, data):
    out = []
    for _ in range(30):
        r = rng.choice(data["rows"])
        out.append({"e": r[1].swapcase() if rng.random() < 0.5 else r[1].lower()})
    out.append({"e": "nobody@example.org"})
    return out''',
        expected='''def expected(data, p):
    return [(i, name) for (i, email, name) in data["rows"] if email.lower() == p["e"].lower()]''', limit=50000,
        spec="Returns `(id, name)` of the `{C}` rows whose e-mail equals `:e` ignoring case, ordered by id."),
    "pair": dict(
        d=2, qname="follows", scale=("SMALL = 1\nBIG = 15", ), fix='CREATE UNIQUE INDEX uq_${C}_pair ON $C(a_id, b_id);',
        schema='''CREATE TABLE $C (id INTEGER PRIMARY KEY, a_id INTEGER NOT NULL, b_id INTEGER NOT NULL, since INTEGER NOT NULL);
''', query='''-- when did one account start following another (no row when it does not)
SELECT since FROM $C WHERE a_id = :a AND b_id = :b;
''', seed='''def seed(conn, rng, scale):
    n = 3000 * scale
    seen, rows = set(), []
    while len(rows) < n:
        a, b = rng.randrange(1, 400 * scale), rng.randrange(1, 400 * scale)
        if (a, b) in seen:
            continue
        seen.add((a, b))
        rows.append((len(rows) + 1, a, b, rng.randrange(1000)))
    conn.executemany("INSERT INTO $C VALUES (?, ?, ?, ?)", rows)
    return {"rows": rows}''', params='''def make_params(rng, data):
    out = []
    for _ in range(100):
        r = rng.choice(data["rows"])
        out.append({"a": r[1], "b": r[2]} if rng.random() < 0.7 else {"a": r[1], "b": 999999})
    return out''',
        expected='''def expected(data, p):
    return [(since,) for (i, a, b, since) in data["rows"] if a == p["a"] and b == p["b"]]''', limit=60000,
        spec="Returns the `since` value of the row for the pair (`:a`, `:b`), or no row."),
    "join": dict(
        d=3, qname="spend_by_product", scale=("SMALL = 1\nBIG = 15", ), fix='CREATE INDEX idx_orders_customer ON orders(customer_id);',
        schema='''CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, product_id INTEGER NOT NULL, qty INTEGER NOT NULL);
''', query='''-- what one customer bought, per product
SELECT p.name, SUM(o.qty) FROM orders o JOIN products p ON p.id = o.product_id WHERE o.customer_id = :c GROUP BY p.id ORDER BY p.name;
''', seed='''def seed(conn, rng, scale):
    np, nc, no = 60, 300 * scale, 3000 * scale
    products = [(i + 1, "product%02d" % i) for i in range(np)]
    orders = [(i + 1, rng.randrange(1, nc + 1), rng.randrange(1, np + 1), rng.randrange(1, 9)) for i in range(no)]
    conn.executemany("INSERT INTO products VALUES (?, ?)", products)
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
    return {"nc": nc, "products": products, "orders": orders}''', params='''def make_params(rng, data):
    return [{"c": rng.randrange(1, data["nc"] + 1)} for _ in range(25)]''',
        expected='''def expected(data, p):
    names = dict(data["products"])
    totals = {}
    for (i, c, prod, qty) in data["orders"]:
        if c == p["c"]:
            totals[prod] = totals.get(prod, 0) + qty
    return sorted((names[k], v) for k, v in totals.items())''', limit=80000,
        spec="Returns `(product name, total quantity)` for one customer (`:c`), ordered by product name."),
}

# ---------------------------------------------------------------------------------------------------------------------
# rewrite shapes (the fix goes into the query file; schema.sql is protected)
# ---------------------------------------------------------------------------------------------------------------------
REWRITE_SHAPES = {
    "sargable_date": dict(
        d=2, qname="day_report", scale=("SMALL = 1\nBIG = 15", ),
        schema='''CREATE TABLE events (id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, device TEXT NOT NULL, value INTEGER NOT NULL);
CREATE INDEX idx_events_ts ON events(ts);
''', query='''-- the events of one calendar day (UTC); :d is 'YYYY-MM-DD'
SELECT id, value FROM events WHERE date(ts, 'unixepoch') = :d ORDER BY id;
''', fast='''-- the events of one calendar day (UTC); :d is 'YYYY-MM-DD'
SELECT id, value FROM events
WHERE ts >= CAST(strftime('%s', :d) AS INTEGER) AND ts < CAST(strftime('%s', :d, '+1 day') AS INTEGER)
ORDER BY id;
''', seed='''import datetime

BASE = 1700000000


def seed(conn, rng, scale):
    n = 4000 * scale
    rows = [(i + 1, BASE + rng.randrange(0, 60 * 86400), "d%d" % rng.randrange(30), rng.randrange(100)) for i in range(n)]
    conn.executemany("INSERT INTO events VALUES (?, ?, ?, ?)", rows)
    return {"rows": rows}''', params='''def make_params(rng, data):
    days = sorted({datetime.datetime.fromtimestamp(r[1], datetime.timezone.utc).strftime("%Y-%m-%d") for r in data["rows"]})
    return [{"d": d} for d in rng.sample(days, 6)]''',
        expected='''def expected(data, p):
    out = []
    for (i, ts, dev, v) in data["rows"]:
        if datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d") == p["d"]:
            out.append((i, v))
    return sorted(out)''', limit=50000, spec="Returns `(id, value)` of the events whose UTC date is `:d`, ordered by id."),
    "sargable_prefix": dict(
        d=2, qname="by_prefix", scale=("SMALL = 1\nBIG = 15", ),
        schema='''CREATE TABLE parts (id INTEGER PRIMARY KEY, code TEXT NOT NULL, name TEXT NOT NULL);
CREATE INDEX idx_parts_code ON parts(code);
''', query='''-- parts whose code starts with a three-letter family prefix
SELECT id, code FROM parts WHERE substr(code, 1, 3) = :p ORDER BY code;
''', fast='''-- parts whose code starts with a three-letter family prefix
SELECT id, code FROM parts WHERE code >= :p AND code < :p || '~' ORDER BY code;
''', seed='''def seed(conn, rng, scale):
    n = 4000 * scale
    fams = sorted({"".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(3)) for _ in range(60)})
    rows = [(i + 1, "%s-%05d" % (rng.choice(fams), rng.randrange(100000)), "part%d" % i) for i in range(n)]
    conn.executemany("INSERT INTO parts VALUES (?, ?, ?)", rows)
    return {"rows": rows, "fams": sorted(set(fams))}''', params='''def make_params(rng, data):
    return [{"p": f} for f in rng.sample(data["fams"], 8)] + [{"p": "000"}]''',
        expected='''def expected(data, p):
    return [(i, code) for code, i in sorted((code, i) for (i, code, name) in data["rows"] if code[:3] == p["p"])]
''', limit=40000, spec="Returns `(id, code)` of the parts whose code starts with `:p` (a three letter prefix), ordered by code then id."),
    "latest": dict(
        d=3, qname="latest_value", scale=("SMALL = 1\nBIG = 10", ),
        schema='''CREATE TABLE readings (id INTEGER PRIMARY KEY, device TEXT NOT NULL, ts INTEGER NOT NULL, value INTEGER NOT NULL);
CREATE INDEX idx_readings_device ON readings(device);
''', query='''-- the latest reading of every device
SELECT r.device, r.value FROM readings r
WHERE r.ts = (SELECT MAX(r2.ts) FROM readings r2 WHERE r2.device = r.device)
ORDER BY r.device;
''', fast='''-- the latest reading of every device
SELECT r.device, r.value FROM readings r
JOIN (SELECT device, MAX(ts) AS m FROM readings GROUP BY device) x ON x.device = r.device AND x.m = r.ts
ORDER BY r.device;
''', seed='''def seed(conn, rng, scale):
    ndev = 30
    rows, i = [], 0
    for d in range(ndev):
        stamps = rng.sample(range(10 ** 6), 100 * scale)
        for ts in stamps:
            i += 1
            rows.append((i, "dev%02d" % d, ts, rng.randrange(1000)))
    conn.executemany("INSERT INTO readings VALUES (?, ?, ?, ?)", rows)
    return {"rows": rows}''', params='''def make_params(rng, data):
    return [{}]''',
        expected='''def expected(data, p):
    best = {}
    for (i, dev, ts, v) in data["rows"]:
        if dev not in best or ts > best[dev][0]:
            best[dev] = (ts, v)
    return sorted((d, v) for d, (ts, v) in best.items())''', limit=100000, spec="Returns `(device, value)` of the reading with the largest `ts` of every device (timestamps are distinct per device), ordered by device."),
    "keyset": dict(
        d=3, qname="page", scale=("SMALL = 1\nBIG = 40", ),
        schema='''CREATE TABLE items (id INTEGER PRIMARY KEY, title TEXT NOT NULL, price INTEGER NOT NULL);
''', query='''-- one page of 20 items; :offset rows come before it, :last_id is the id of the last row of the previous page (0 for the first page)
SELECT id, title FROM items ORDER BY id LIMIT 20 OFFSET :offset;
''', fast='''-- one page of 20 items; :offset rows come before it, :last_id is the id of the last row of the previous page (0 for the first page)
SELECT id, title FROM items WHERE id > :last_id ORDER BY id LIMIT 20;
''', seed='''def seed(conn, rng, scale):
    n = 3000 * scale
    ids = sorted(rng.sample(range(1, 4 * n), n))
    rows = [(k, "item%d" % k, rng.randrange(1000)) for k in ids]
    conn.executemany("INSERT INTO items VALUES (?, ?, ?)", rows)
    return {"rows": rows}''', params='''def make_params(rng, data):
    n = len(data["rows"])
    out = []
    for _ in range(8):
        off = rng.randrange(n // 2, n - 25)
        out.append({"offset": off, "last_id": data["rows"][off - 1][0]})
    out.append({"offset": 0, "last_id": 0})
    return out''',
        expected='''def expected(data, p):
    return [(i, t) for (i, t, price) in data["rows"][p["offset"]:p["offset"] + 20]]''', limit=20000,
        spec="Returns `(id, title)` of the 20 items that follow the first `:offset` items in id order. `:last_id` is the id of the item just before the page (0 for the first page); both parameters are always consistent."),
    "exists": dict(
        d=3, qname="active_customers", scale=("SMALL = 1\nBIG = 8", ),
        schema='''CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, status TEXT NOT NULL);
CREATE INDEX idx_orders_customer ON orders(customer_id);
''', query='''-- customers with at least one refunded order
SELECT c.id, c.name FROM customers c
WHERE (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.id AND o.status = 'refunded') > 0
ORDER BY c.id;
''', fast='''-- customers with at least one refunded order
SELECT c.id, c.name FROM customers c
WHERE EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id AND o.status = 'refunded')
ORDER BY c.id;
''', seed='''def seed(conn, rng, scale):
    nc, per = 60 * scale, 400
    customers = [(i + 1, "customer%d" % i) for i in range(nc)]
    orders = []
    for c in range(1, nc + 1):
        heavy = rng.random() < 0.9
        for _ in range(per):
            orders.append((len(orders) + 1, c, "refunded" if (heavy and rng.random() < 0.5) else rng.choice(["paid", "open"])))
    conn.executemany("INSERT INTO customers VALUES (?, ?)", customers)
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?)", orders)
    return {"customers": customers, "orders": orders}''', params='''def make_params(rng, data):
    return [{}]''',
        expected='''def expected(data, p):
    refunded = {c for (i, c, s) in data["orders"] if s == "refunded"}
    return [(i, n) for (i, n) in data["customers"] if i in refunded]''', limit=40000,
        spec="Returns `(id, name)` of the customers that have at least one order with status `refunded`, ordered by id."),
}

VOCABS = [
    dict(P="authors", C="books", FK="author_id", TS="published", pk="author", ck="book", noun="library", pkg="library"),
    dict(P="clinics", C="visits", FK="clinic_id", TS="seen_at", pk="clinic", ck="visit", noun="clinic", pkg="clinicdb"),
    dict(P="routes", C="trips", FK="route_id", TS="departed", pk="route", ck="trip", noun="transit", pkg="transit"),
    dict(P="labs", C="samples", FK="lab_id", TS="received", pk="lab", ck="sample", noun="lab", pkg="labtrack"),
    dict(P="boards", C="cards", FK="board_id", TS="moved_at", pk="board", ck="card", noun="kanban", pkg="taskboard"),
]

PROMPTS_INDEX = [
    "A report query in `queries/{q}.sql` got slow after the {noun} database grew: the page that runs it a few dozen times takes many seconds. {spec} "
    "Figure out what the database is missing and fix it in the schema (`schema.sql`) or the query; the query must keep returning exactly what it returns now. "
    "Our CI counts SQLite virtual machine steps on a large generated database.",
    "perf: `queries/{q}.sql` does a full table scan (or sorts far too much) for every call. {spec} Make it cheap: add what is needed to `schema.sql` (indexes) and/or adjust the query. Same results.",
    "The {noun} dashboard is crawling. EXPLAIN QUERY PLAN for `queries/{q}.sql` shows a scan. {spec} Fix it so it uses an index; results must not change.",
]
PROMPTS_REWRITE = [
    "`queries/{q}.sql` is very slow on the production-sized {noun} data and nobody may touch the schema (`schema.sql` is owned by another team and already has the indexes it needs). "
    "{spec} Rewrite the query so SQLite can use the existing indexes / do far less work, with exactly the same results.",
    "perf: `queries/{q}.sql`. {spec} It is correct but the plan is awful, and we can't change the schema. Rewrite the query only. Same rows, same order.",
    "Could you speed up `queries/{q}.sql`? {spec} Only the query may change (the schema stays). CI counts SQLite VM steps on a large database, so a small tweak is not enough.",
]


DIALECTS = [
    {},
    {"events": "visits", "parts": "components", "readings": "measurements", "items": "listings", "customers": "clients", "orders": "purchases", "products": "wares"},
    {"events": "trips", "parts": "fittings", "readings": "samples", "items": "lots", "customers": "members", "orders": "bookings", "products": "courses"},
    {"events": "logs", "parts": "spares", "readings": "pings", "items": "articles", "customers": "accounts", "orders": "invoices", "products": "plans"},
]


def _rename(text, dialect):
    for old, new in dialect.items():
        text = re.sub(r"(?<![A-Za-z.])" + old + r"(?![A-Za-z])", new, text)
    return text


def _prepare(sp, v, dialect):
    """The shape's texts with vocabulary placeholders filled and canonical table names renamed for the dialect."""
    out = {}
    for k, val in sp.items():
        if isinstance(val, str):
            out[k] = _rename(Template(val).safe_substitute(v), dialect) if k not in ("spec",) else _rename(val.format(**v) if "{" in val else val, dialect)
        else:
            out[k] = val
    return out


def _checker(sp, v, q, limit, seedn):
    s = sp["seed"]
    text = (CHECKER.replace("@SEED@", s).replace("@PARAMS@", sp["params"]).replace("@EXPECTED@", sp["expected"]).replace("@QNAME@", q)
            .replace("@LIMIT@", str(limit)).replace("@SEEDN@", str(seedn)))
    small, big = sp["scale"][0].split("\n")
    return text.replace("SMALL", small.split("=")[1].strip()).replace("BIG", big.split("=")[1].strip()) if False else text.replace("check(SMALL,", f"check({small.split('=')[1].strip()},").replace("check(BIG,", f"check({big.split('=')[1].strip()},")


def _measure(files, sp, v, q, seedn):
    checker = _checker(sp, v, q, 10 ** 9, seedn)
    r = run(merged(files, {"checks/verify.py": checker}), SQL_MEASURE, timeout=120)
    m = re.search(r"MEASURE\|(\w+)\|(\d+)", r.out)
    if not m:
        raise RuntimeError("measure failed:\n" + r.out[-1500:])
    return m.group(1), int(m.group(2))


def _tiny_test(sp, v, q, seedn):
    s = sp["seed"]
    return (f"import pathlib\nimport random\nimport sqlite3\nimport unittest\n\nROOT = pathlib.Path(__file__).resolve().parent.parent\n\n\n{s}\n\n\n{sp['params']}\n\n\n{sp['expected']}\n\n\n"
            f"class QueryTests(unittest.TestCase):\n    def test_small_database(self):\n        conn = sqlite3.connect(':memory:')\n        conn.executescript((ROOT / 'schema.sql').read_text())\n"
            f"        rng = random.Random({seedn + 1})\n        data = seed(conn, rng, 1)\n        sql = (ROOT / 'queries' / '{q}.sql').read_text()\n"
            "        for p in make_params(rng, data):\n            self.assertEqual([tuple(r) for r in conn.execute(sql, p).fetchall()], expected(data, p), p)\n\n\nif __name__ == '__main__':\n    unittest.main()\n")


def _register(name, shapes, rewrite):
    @family(name, category="optimize", lang="sql", kind="feature", n=12 if not rewrite else 12,
            summary=("queries that need a rewrite (non-sargable predicates, correlated subqueries, deep OFFSET, COUNT vs EXISTS): SQLite VM steps with a budget" if rewrite
                     else "missing or wrong indexes (lookup, range + order, composite order, expression index, pair, join key): SQLite VM steps with a budget"))
    def gen(rng, n):
        order = list(shapes) * 3
        rng.shuffle(order)
        vocabs = list(VOCABS) * 3
        rng.shuffle(vocabs)
        for i in range(n):
            shape = order[i]
            v = vocabs[i % len(vocabs)]
            sp = _prepare(shapes[shape], v, DIALECTS[i % len(DIALECTS)])
            q = sp["qname"]
            schema = sp["schema"]
            query = sp["query"]
            seedn = 400 + i
            readme = (f"# {v['noun']} database\n\nSQLite. `schema.sql` creates the tables, `queries/{q}.sql` is the query the application runs "
                      f"(named parameters, executed with the Python `sqlite3` module).\n\n{sp['spec']}\n\n"
                      "The tables hold hundreds of thousands of rows in production; the query is run many times per page view.\n")
            files = {"schema.sql": schema, f"queries/{q}.sql": query, "README.md": readme, "tests/test_query.py": _tiny_test(sp, v, q, seedn)}
            if rewrite:
                solution = {f"queries/{q}.sql": sp["fast"]}
            else:
                fix = sp["fix"]
                solution = {"schema.sql": schema.rstrip("\n") + "\n" + fix + "\n"}
            naive_state, naive_steps = _measure(files, sp, v, q, seedn)
            sol_files = merged(files, solution)
            fast_state, fast_steps = _measure(sol_files, sp, v, q, seedn)
            if fast_state != "ok":
                raise RuntimeError(f"{shape}: the reference fails: {fast_state}")
            limit = max(int(fast_steps * 2), 4000)
            if naive_state == "ok" and naive_steps < 4 * limit:
                raise RuntimeError(f"{shape}/{v['pk']}: naive {naive_steps} too close to limit {limit} (fast {fast_steps})")
            checker = _checker(sp, v, q, limit, seedn)
            hidden = {"checks/verify.py": checker}
            prove_opt(f"{shape}/{v['pk']}", files, hidden, solution, SQL_CORRECT, SQL_PERF, SQL_ALL, timeout=150)
            prompt = rng.choice(PROMPTS_REWRITE if rewrite else PROMPTS_INDEX).format(q=q, noun=v["noun"], spec=sp["spec"])
            yield Task(slug=f"{i + 1:02d}-{shape}-{v['pk']}", prompt=prompt, difficulty=sp["d"], start=files, hidden=hidden, solution=solution, verify=SQL_ALL, timeout_s=150,
                       protected=["schema.sql"] if rewrite else [], tags=["sql", "sqlite", "query-plan", "vm-steps", "rewrite" if rewrite else "index"],
                       notes={"shape": shape, "naive_steps": naive_steps, "naive_state": naive_state, "fast_steps": fast_steps, "limit": limit})
    return gen


_register("optimize-sql-indexes", INDEX_SHAPES, False)
_register("optimize-sql-rewrites", REWRITE_SHAPES, True)
