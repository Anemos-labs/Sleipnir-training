"""Harder SQLite optimisation: the query *and* the schema both need work (window functions, keyset paging on a sorted column, several indexes).
Same checker as the other SQL families: a deterministic large database and a budget on SQLite virtual-machine steps."""
from __future__ import annotations

from fx import Task, family, merged

from ._kit import prove_opt
from .sql_opt import DIALECTS, SQL_ALL, SQL_CORRECT, SQL_PERF, VOCABS, _checker, _measure, _prepare, _tiny_test

HARD_SHAPES = {
    "top_n": dict(
        d=3, qname="latest_three", scale=("SMALL = 1\nBIG = 6", ),
        schema='''CREATE TABLE readings (id INTEGER PRIMARY KEY, device TEXT NOT NULL, ts INTEGER NOT NULL, value INTEGER NOT NULL);
''', query='''-- the three most recent readings of every device (newest first, ties: larger id first)
SELECT e.device, e.id, e.ts FROM readings e
WHERE (SELECT COUNT(*) FROM readings x WHERE x.device = e.device AND (x.ts > e.ts OR (x.ts = e.ts AND x.id > e.id))) < 3
ORDER BY e.device, e.ts DESC, e.id DESC;
''', fix=None, fast='''-- the three most recent readings of every device (newest first, ties: larger id first)
SELECT device, id, ts FROM (
    SELECT device, id, ts, ROW_NUMBER() OVER (PARTITION BY device ORDER BY ts DESC, id DESC) AS rn FROM readings
) WHERE rn <= 3 ORDER BY device, ts DESC, id DESC;
''', seed='''def seed(conn, rng, scale):
    rows = []
    for d in range(30):
        for _ in range(100 * scale):
            rows.append((len(rows) + 1, "dev%02d" % d, rng.randrange(20000), rng.randrange(1000)))
    conn.executemany("INSERT INTO readings VALUES (?, ?, ?, ?)", rows)
    return {"rows": rows}''', params='''def make_params(rng, data):
    return [{}]''', expected='''def expected(data, p):
    by = {}
    for (i, dev, ts, v) in data["rows"]:
        by.setdefault(dev, []).append((ts, i))
    out = []
    for dev in sorted(by):
        for ts, i in sorted(by[dev], reverse=True)[:3]:
            out.append((dev, i, ts))
    return out''', limit=0,
        spec="Returns `(device, id, ts)` of the three most recent readings of every device (fewer when a device has fewer), ordered by device, then newest first (equal timestamps: larger id first)."),
    "running": dict(
        d=3, qname="balances", scale=("SMALL = 1\nBIG = 6", ),
        schema='''CREATE TABLE ledger (id INTEGER PRIMARY KEY, account INTEGER NOT NULL, amount INTEGER NOT NULL);
''', query='''-- every ledger row with the running balance of its account (in id order)
SELECT l.id, l.account, (SELECT SUM(x.amount) FROM ledger x WHERE x.account = l.account AND x.id <= l.id) AS balance
FROM ledger l ORDER BY l.account, l.id;
''', fix=None, fast='''-- every ledger row with the running balance of its account (in id order)
SELECT id, account, SUM(amount) OVER (PARTITION BY account ORDER BY id) AS balance FROM ledger ORDER BY account, id;
''', seed='''def seed(conn, rng, scale):
    n = 3000 * scale
    rows = [(i + 1, rng.randrange(1, 41), rng.randrange(-500, 900)) for i in range(n)]
    conn.executemany("INSERT INTO ledger VALUES (?, ?, ?)", rows)
    return {"rows": rows}''', params='''def make_params(rng, data):
    return [{}]''', expected='''def expected(data, p):
    run, out = {}, []
    for (i, acc, amount) in data["rows"]:
        run[acc] = run.get(acc, 0) + amount
        out.append((i, acc, run[acc]))
    return sorted(out, key=lambda r: (r[1], r[0]))''', limit=0,
        spec="Returns `(id, account, balance)` for every ledger row, where `balance` is the sum of the amounts of that account's rows with an id up to and including this one; ordered by account, then id."),
    "keyset_sorted": dict(
        d=4, qname="page_by_price", scale=("SMALL = 1\nBIG = 20", ),
        schema='''CREATE TABLE items (id INTEGER PRIMARY KEY, title TEXT NOT NULL, price INTEGER NOT NULL);
''', query='''-- one page of 20 items in (price, id) order; :offset rows come before it, :last_price and :last_id are the price and id of the last row
-- of the previous page (0 and 0 for the first page)
SELECT id, title, price FROM items ORDER BY price, id LIMIT 20 OFFSET :offset;
''', fix='CREATE INDEX idx_items_price_id ON items(price, id);', fast='''-- one page of 20 items in (price, id) order; :offset rows come before it, :last_price and :last_id are the price and id of the last row
-- of the previous page (0 and 0 for the first page)
SELECT id, title, price FROM items WHERE (price, id) > (:last_price, :last_id) ORDER BY price, id LIMIT 20;
''', seed='''def seed(conn, rng, scale):
    n = 3000 * scale
    rows = [(i + 1, "item%d" % i, rng.randrange(1, 500)) for i in range(n)]
    conn.executemany("INSERT INTO items VALUES (?, ?, ?)", rows)
    return {"rows": rows}''', params='''def make_params(rng, data):
    ordered = sorted((price, i) for (i, t, price) in data["rows"])
    n = len(ordered)
    out = []
    for _ in range(8):
        off = rng.randrange(n // 2, n - 25)
        out.append({"offset": off, "last_price": ordered[off - 1][0], "last_id": ordered[off - 1][1]})
    out.append({"offset": 0, "last_price": 0, "last_id": 0})
    return out''', expected='''def expected(data, p):
    titles = {i: t for (i, t, price) in data["rows"]}
    ordered = sorted((price, i) for (i, t, price) in data["rows"])
    return [(i, titles[i], price) for price, i in ordered[p["offset"]:p["offset"] + 20]]''', limit=0,
        spec="Returns `(id, title, price)` of the 20 items that follow the first `:offset` items in (price, id) order. `:last_price` and `:last_id` are the price and id of the item just before the page (0 and 0 for the first page); the parameters are always consistent."),
    "multi_fix": dict(
        d=5, qname="orders_on_day", scale=("SMALL = 1\nBIG = 6", ),
        schema='''CREATE TABLE customers (id INTEGER PRIMARY KEY, email TEXT NOT NULL, name TEXT NOT NULL);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, ts INTEGER NOT NULL, amount INTEGER NOT NULL);
''', query='''-- the orders a customer (found by e-mail address, ignoring case) placed on one UTC day; :d is 'YYYY-MM-DD'
SELECT o.id, o.amount FROM orders o JOIN customers c ON c.id = o.customer_id
WHERE lower(c.email) = lower(:e) AND date(o.ts, 'unixepoch') = :d ORDER BY o.id;
''', fix='CREATE INDEX idx_customers_email_lower ON customers(lower(email));\nCREATE INDEX idx_orders_customer_ts ON orders(customer_id, ts);', fast='''-- the orders a customer (found by e-mail address, ignoring case) placed on one UTC day; :d is 'YYYY-MM-DD'
SELECT o.id, o.amount FROM customers c JOIN orders o ON o.customer_id = c.id
WHERE lower(c.email) = lower(:e)
  AND o.ts >= CAST(strftime('%s', :d) AS INTEGER) AND o.ts < CAST(strftime('%s', :d, '+1 day') AS INTEGER)
ORDER BY o.id;
''', seed='''import datetime

BASE = 1700000000


def day_of(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d")


def seed(conn, rng, scale):
    nc, no = 1500 * scale, 10000 * scale
    heavy = list(range(1, 21))
    customers = [(i + 1, "User%d@Example.%s" % (i, rng.choice(["org", "com"])), "name%d" % i) for i in range(nc)]
    orders = []
    for i in range(no):
        owner = rng.choice(heavy) if rng.random() < 0.8 else rng.randrange(1, nc + 1)
        orders.append((i + 1, owner, BASE + rng.randrange(0, 60 * 86400), rng.randrange(1, 500)))
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", customers)
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
    return {"customers": customers, "orders": orders}''', params='''def make_params(rng, data):
    emails = {c[0]: c[1] for c in data["customers"]}
    out = []
    busy = [o for o in data["orders"] if o[1] <= 20]
    for _ in range(20):
        o = rng.choice(busy)
        e = emails[o[1]]
        out.append({"e": e.swapcase() if rng.random() < 0.5 else e.lower(), "d": day_of(o[2])})
    out.append({"e": "nobody@example.org", "d": day_of(BASE)})
    return out''', expected='''def expected(data, p):
    ids = {c[0] for c in data["customers"] if c[1].lower() == p["e"].lower()}
    return sorted((o[0], o[3]) for o in data["orders"] if o[1] in ids and day_of(o[2]) == p["d"])''', limit=0,
        spec="Returns `(id, amount)` of the orders placed on the UTC day `:d` by the customer whose e-mail equals `:e` ignoring case, ordered by id."),
}

PROMPTS = [
    "`queries/{q}.sql` is the slowest thing on the {noun} dashboard. {spec} Make it cheap on a production-sized database: you may change the query and add to `schema.sql`, "
    "but the results must stay exactly the same. CI counts SQLite virtual machine steps on a large generated database; a budget that a good query plan meets easily is "
    "far below what the current one needs, and a single small tweak will probably not be enough.",
    "perf: `queries/{q}.sql` ({noun} data). {spec} Both the query text and the schema (`schema.sql`) are yours to change; the output must be identical. "
    "The check counts SQLite VM steps for a bunch of calls on a big database, so think about the whole plan, not just one detail.",
    "The {noun} team says `queries/{q}.sql` takes ages. {spec} Fix it properly (schema and/or query, whatever it takes); same rows in the same order afterwards. "
    "Measured by SQLite VM steps on a large database against a fixed budget.",
]


@family("optimize-sql-hard", category="optimize", lang="sql", kind="feature", n=8,
        summary="queries that need both a rewrite and an index (top-n per group with a window function, running totals, keyset paging on a sorted column, expression + range + join indexes)")
def gen(rng, n):
    order = list(HARD_SHAPES) * 3
    rng.shuffle(order)
    vocabs = list(VOCABS) * 3
    rng.shuffle(vocabs)
    for i in range(n):
        shape = order[i]
        v = vocabs[i % len(vocabs)]
        sp = _prepare(HARD_SHAPES[shape], v, DIALECTS[i % len(DIALECTS)])
        q = sp["qname"]
        seedn = 700 + i
        readme = (f"# {v['noun']} database\n\nSQLite. `schema.sql` creates the tables, `queries/{q}.sql` is the query the application runs "
                  f"(named parameters, executed with the Python `sqlite3` module).\n\n{sp['spec']}\n\n"
                  "The tables hold hundreds of thousands of rows in production; the query is run many times per page view.\n")
        files = {"schema.sql": sp["schema"], f"queries/{q}.sql": sp["query"], "README.md": readme, "tests/test_query.py": _tiny_test(sp, v, q, seedn)}
        solution = {f"queries/{q}.sql": sp["fast"]}
        if sp["fix"]:
            solution["schema.sql"] = sp["schema"].rstrip("\n") + "\n" + sp["fix"] + "\n"
        naive_state, naive_steps = _measure(files, sp, v, q, seedn)
        fast_state, fast_steps = _measure(merged(files, solution), sp, v, q, seedn)
        if fast_state != "ok":
            raise RuntimeError(f"{shape}: the reference fails: {fast_state}")
        limit = max(int(fast_steps * 2), 4000)
        if naive_state == "ok" and naive_steps < 4 * limit:
            raise RuntimeError(f"{shape}/{v['pk']}: naive {naive_steps} too close to limit {limit} (fast {fast_steps})")
        if sp["fix"]:
            # each half of the fix alone must not be enough
            only_schema = merged(files, {"schema.sql": solution["schema.sql"]})
            only_query = merged(files, {f"queries/{q}.sql": sp["fast"]})
            for label, tree in (("schema only", only_schema), ("query only", only_query)):
                state, steps = _measure(tree, sp, v, q, seedn)
                if state == "ok" and steps <= limit:
                    raise RuntimeError(f"{shape}/{v['pk']}: {label} already meets the budget ({steps} <= {limit}); the task is not a two-part fix")
        checker = _checker(sp, v, q, limit, seedn)
        hidden = {"checks/verify.py": checker}
        prove_opt(f"{shape}/{v['pk']}", files, hidden, solution, SQL_CORRECT, SQL_PERF, SQL_ALL, timeout=150)
        prompt = rng.choice(PROMPTS).format(q=q, noun=v["noun"], spec=sp["spec"])
        yield Task(slug=f"{i + 1:02d}-{shape}-{v['pk']}", prompt=prompt, difficulty=sp["d"], start=files, hidden=hidden, solution=solution, verify=SQL_ALL, timeout_s=150,
                   tags=["sql", "sqlite", "query-plan", "vm-steps", "window-function", "index"],
                   notes={"shape": shape, "naive_steps": naive_steps, "naive_state": naive_state, "fast_steps": fast_steps, "limit": limit})
