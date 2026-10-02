"""Port imperative python reports to a single SQL query (sqlite): the query must reproduce the python output on any data."""
import json
import sqlite3

from fx import Task, dd, family

HIDDEN = dd('''
    import json
    import os
    import sqlite3
    import unittest

    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    SCHEMA = %(schema)s
    CASES = json.loads(%(cases)s)


    def load_query():
        with open(os.path.join(ROOT, "query.sql"), encoding="utf-8") as fh:
            sql = fh.read()
        if not sqlite3.complete_statement(sql if sql.rstrip().endswith(";") else sql.rstrip() + ";"):
            raise AssertionError("query.sql is not one complete SQL statement")
        body = sql.strip().rstrip(";").strip()
        if ";" in body.replace("';'", ""):
            raise AssertionError("query.sql must hold a single statement")
        if body.split(None, 1)[0].upper() not in ("SELECT", "WITH"):
            raise AssertionError("query.sql must be a SELECT (optionally with CTEs)")
        return sql


    def build(data):
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA)
        for table, rows in data.items():
            if rows:
                conn.executemany("INSERT INTO %%s VALUES (%%s)" %% (table, ",".join("?" * len(rows[0]))), rows)
        return conn


    class QueryTest(unittest.TestCase):
        def test_datasets(self):
            sql = load_query()
            bad = []
            for i, case in enumerate(CASES):
                conn = build(case["data"])
                got = [list(r) for r in conn.execute(sql)]
                if got != case["want"]:
                    bad.append("dataset %%d: want %%s, got %%s" %% (i, json.dumps(case["want"])[:300], json.dumps(got)[:300]))
            self.assertEqual(bad, [], "\\n" + "\\n".join(bad[:3]))


    if __name__ == "__main__":
        unittest.main()
''')

REPORTS = {}


def report(key, title, blurb, schema, reference, readme, gen_data, difficulty):
    REPORTS[key] = dict(key=key, title=title, blurb=blurb, schema=dd(schema), reference=dd(reference), readme=dd(readme), gen=gen_data, difficulty=difficulty)


# ---------------------------------------------------------------------------------------------------------------
def _ferry_data(rng, k):
    routes = ["north", "isles", "mainland", "bay"]
    sailings = []
    for sid in range(1, rng.randint(3, 8) + 1):
        sailings.append([sid, rng.choice(routes), "2024-06-%02d %02d:00" % (rng.randint(1, 5), rng.choice([6, 9, 12, 15, 18])), rng.choice([4, 6, 10, 20, 30])])
    bookings = []
    for bid in range(1, rng.randint(0, 25) + 1):
        bookings.append([bid, rng.randint(1, len(sailings) + (1 if k % 3 == 0 else 0)), rng.randint(1, 9), rng.choice(["confirmed", "pending", "cancelled", "confirmed", "pending"])])
    return {"sailings": sailings, "bookings": bookings}


report("ferry-load", "ferry sailing load", "A ferry company shows how full each sailing is, counting pending bookings as half-held seats.",
       '''
    CREATE TABLE sailings (
      id INTEGER PRIMARY KEY,
      route TEXT NOT NULL,
      depart TEXT NOT NULL,       -- 'YYYY-MM-DD HH:MM'
      capacity INTEGER NOT NULL
    );
    CREATE TABLE bookings (
      id INTEGER PRIMARY KEY,
      sailing_id INTEGER NOT NULL REFERENCES sailings(id),
      party_size INTEGER NOT NULL,
      status TEXT NOT NULL        -- 'confirmed', 'pending' or 'cancelled'
    );
''', '''
    def report(conn):
        rows = []
        for sid, route, depart, cap in conn.execute("SELECT id, route, depart, capacity FROM sailings"):
            held = 0
            for size, status in conn.execute("SELECT party_size, status FROM bookings WHERE sailing_id = ?", (sid,)):
                if status == "confirmed":
                    held += size
                elif status == "pending":
                    held += (size + 1) // 2
            rows.append((route, depart, cap, held, cap - held, 1 if held > cap else 0, sid))
        rows.sort(key=lambda r: (r[0], r[1], r[6]))
        return [r[:6] for r in rows]
''', '''
    For every sailing: its `route`, `depart`, `capacity`, the number of seats `held`, the seats still `free` (`capacity - held`, may be negative) and `over`
    (1 when `held > capacity`, else 0).

    * A `confirmed` booking holds `party_size` seats; a `pending` booking holds half of them rounded **up** (`(party_size + 1) / 2` in integer division); a `cancelled`
      booking holds nothing. A sailing without bookings holds 0.
    * Rows are ordered by `route`, then `depart`, then the sailing `id` (not part of the output).
''', _ferry_data, 2)


def _streak_data(rng, k):
    rows = []
    for s in rng.sample(["s1", "s2", "s3", "kelp", "reef", "buoy"], rng.randint(2, 5)):
        day = rng.randint(1, 5)
        for _ in range(rng.randint(3, 22)):
            day += rng.choice([1, 1, 1, 1, 2, 3])
            rows.append([s, day, rng.choice([2, 5, 9, 10, 10, 11, 14, 20, 30])])
    return {"readings": rows}


report("reading-streaks", "longest hot streak per sensor", "A marine-monitoring dashboard highlights, for every sensor, its longest run of consecutive 'hot' days.",
       '''
    CREATE TABLE readings (
      sensor TEXT NOT NULL,
      day INTEGER NOT NULL,       -- day number; not every day has a row
      value INTEGER NOT NULL,
      PRIMARY KEY (sensor, day)
    );
''', '''
    def report(conn):
        out = []
        sensors = [r[0] for r in conn.execute("SELECT DISTINCT sensor FROM readings ORDER BY sensor")]
        for sensor in sensors:
            best = None
            start = prev = None
            for day, value in conn.execute("SELECT day, value FROM readings WHERE sensor = ? ORDER BY day", (sensor,)):
                if value >= 10:
                    if prev is not None and day == prev + 1:
                        prev = day
                    else:
                        start, prev = day, day
                    length = prev - start + 1
                    if best is None or length > best[2]:
                        best = (sensor, start, length)
                else:
                    start = prev = None
            if best is not None:
                out.append(best)
        return out
''', '''
    For every sensor that has at least one *hot* day (a row with `value >= 10`), its longest streak of hot days that are consecutive day numbers: `sensor`,
    `start_day` (the first day of the streak) and `length` (number of days).

    * A day without a row, or with a row whose value is below 10, ends a streak; a streak of consecutive hot days is as long as the run of consecutive numbers.
    * If a sensor has several streaks of the same longest length, the one that starts **first** is reported.
    * Sensors without hot days do not appear. Rows are ordered by `sensor`.
''', _streak_data, 4)


def _tide_data(rng, k):
    rows, seen = [], set()
    for st in rng.sample(["harbor", "bay", "point", "reef"], rng.randint(1, 3)):
        for _ in range(rng.randint(2, 18)):
            ts = "2024-03-%02d %02d:%02d" % (rng.randint(1, 4), rng.randint(0, 23), rng.choice([0, 15, 30, 45]))
            if (st, ts) in seen:
                continue
            seen.add((st, ts))
            rows.append([st, ts, rng.choice([120, 200, 310, 310, 450, 450, 500, 80])])
    return {"tides": rows}


report("tide-top", "highest tides per station and day", "A tide-table site lists, for every station and calendar day, the two highest readings.",
       '''
    CREATE TABLE tides (
      station TEXT NOT NULL,
      ts TEXT NOT NULL,           -- 'YYYY-MM-DD HH:MM'
      height_cm INTEGER NOT NULL,
      PRIMARY KEY (station, ts)
    );
''', '''
    def report(conn):
        out = []
        groups = {}
        for station, ts, h in conn.execute("SELECT station, ts, height_cm FROM tides"):
            groups.setdefault((station, ts[:10]), []).append((h, ts))
        for (station, day) in sorted(groups):
            ranked = sorted(groups[(station, day)], key=lambda t: (-t[0], t[1]))
            for rank, (h, ts) in enumerate(ranked[:2], 1):
                out.append((station, day, rank, ts, h))
        return out
''', '''
    For every `station` and calendar day (the first 10 characters of `ts`), the two highest readings: `station`, `day`, `rank` (1 or 2), `ts` and `height_cm`.

    * Higher readings rank first; readings of equal height rank by the **earlier** `ts`. A day with a single reading yields only rank 1.
    * Rows are ordered by `station`, `day`, `rank`.
''', _tide_data, 3)


def _fee_data(rng, k):
    members = [[i, rng.choice(["Ann", "Bo", "Cy", "Di", "Eli", "Flo", "Gus"]) + str(i), rng.choice(["standard", "gold", "standard"])] for i in range(1, rng.randint(3, 6) + 1)]
    loans = []
    for lid in range(1, rng.randint(3, 20) + 1):
        d0 = rng.randint(1, 300)
        b = "2024-%02d-%02d" % (1 + d0 // 28 % 12, 1 + d0 % 28)
        late = rng.choice([0, 0, 3, 14, 20, 40, 100])
        if rng.random() < 0.15:
            r = None
        else:
            import datetime
            r = (datetime.date.fromisoformat(b) + datetime.timedelta(days=rng.choice([5, 14, 15, 21, 22]) + late)).isoformat()
        loans.append([lid, rng.randint(1, len(members)), b, r])
    return {"members": members, "loans": loans}


report("late-fees", "library late fees per member", "A library tallies late fees per member, with a longer loan period for gold members and a cap per loan.",
       '''
    CREATE TABLE members (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      tier TEXT NOT NULL          -- 'standard' or 'gold'
    );
    CREATE TABLE loans (
      id INTEGER PRIMARY KEY,
      member_id INTEGER NOT NULL REFERENCES members(id),
      borrowed_on TEXT NOT NULL,  -- 'YYYY-MM-DD'
      returned_on TEXT            -- NULL while the book is still out
    );
''', '''
    import datetime

    AS_OF = "2024-12-31"


    def report(conn):
        out = []
        for mid, name, tier in conn.execute("SELECT id, name, tier FROM members"):
            allowed = 21 if tier == "gold" else 14
            total = late_loans = 0
            for borrowed, returned in conn.execute("SELECT borrowed_on, returned_on FROM loans WHERE member_id = ?", (mid,)):
                end = datetime.date.fromisoformat(returned or AS_OF)
                days = (end - datetime.date.fromisoformat(borrowed)).days
                fee = min(max(0, days - allowed) * 25, 1000)
                if fee > 0:
                    late_loans += 1
                    total += fee
            if total > 0:
                out.append((name, late_loans, total))
        out.sort(key=lambda r: (-r[2], r[0]))
        return out
''', '''
    For every member with unpaid late fees: `name`, `late_loans` (the number of their loans that incurred a fee) and `total_fee` in cents.

    * A loan may be kept for 14 days (21 days for `gold` members). The loan lasts from `borrowed_on` to `returned_on`, or, while it is still out (`returned_on IS NULL`),
      to the fixed date `2024-12-31`. Days are whole calendar days (`returned_on - borrowed_on`).
    * Every day beyond the allowed period costs 25 cents; the fee of a single loan is capped at 1000 cents. Loans on time (or exactly at the limit) cost nothing.
    * Members whose total is 0 do not appear. Rows are ordered by `total_fee` descending, then `name`.
''', _fee_data, 3)


def _pair_data(rng, k):
    items = ["bread", "milk", "jam", "tea", "eggs", "rice", "salt", "oil"]
    rows = []
    for oid in range(1, rng.randint(4, 14) + 1):
        for it in rng.sample(items, rng.randint(1, 5)):
            rows.append([oid, it])
            if rng.random() < 0.12:
                rows.append([oid, it])
    return {"order_lines": rows}


report("item-pairs", "items bought together", "A shop looks for items that are often bought in the same order.",
       '''
    CREATE TABLE order_lines (
      order_id INTEGER NOT NULL,
      item TEXT NOT NULL          -- an item can appear twice in one order
    );
''', '''
    from itertools import combinations


    def report(conn):
        orders = {}
        for oid, item in conn.execute("SELECT order_id, item FROM order_lines"):
            orders.setdefault(oid, set()).add(item)
        counts = {}
        for items in orders.values():
            for a, b in combinations(sorted(items), 2):
                counts[(a, b)] = counts.get((a, b), 0) + 1
        rows = [(a, b, n) for (a, b), n in counts.items() if n >= 2]
        rows.sort(key=lambda r: (-r[2], r[0], r[1]))
        return rows
''', '''
    Pairs of different items that appear together in at least two orders: `item_a`, `item_b` (with `item_a < item_b`, plain string comparison) and `orders`, the number of
    orders that contain both.

    * An order counts once for a pair no matter how often it lists the items.
    * Rows are ordered by `orders` descending, then `item_a`, then `item_b`.
''', _pair_data, 3)


def _stock_data(rng, k):
    sp = rng.sample(["fern", "moss", "kelp", "aloe"], rng.randint(1, 3))
    lots, sales, lid, sid = [], [], 0, 0
    for s in sp:
        for _ in range(rng.randint(0, 4)):
            lid += 1
            lots.append([lid, s, "2024-0%d-%02d" % (rng.randint(1, 6), rng.randint(1, 28)), rng.choice([0, 5, 10, 25, 40])])
        for _ in range(rng.randint(0, 5)):
            sid += 1
            sales.append([sid, s, "2024-0%d-%02d" % (rng.randint(1, 9), rng.randint(1, 28)), rng.choice([0, 3, 8, 15, 30, 60])])
    return {"lots": lots, "sales": sales}


report("seed-stock", "first-in-first-out stock allocation", "A nursery reconciles which received lots each sale was taken from, oldest lot first, and flags what could not be covered.",
       '''
    CREATE TABLE lots (
      id INTEGER PRIMARY KEY,
      species TEXT NOT NULL,
      received_on TEXT NOT NULL,  -- 'YYYY-MM-DD'
      qty INTEGER NOT NULL
    );
    CREATE TABLE sales (
      id INTEGER PRIMARY KEY,
      species TEXT NOT NULL,
      sold_on TEXT NOT NULL,      -- 'YYYY-MM-DD'
      qty INTEGER NOT NULL
    );
''', '''
    def report(conn):
        out = []
        species = sorted(r[0] for r in conn.execute("SELECT species FROM lots UNION SELECT species FROM sales"))
        for sp in species:
            lots = list(conn.execute("SELECT id, qty FROM lots WHERE species = ? ORDER BY received_on, id", (sp,)))
            i = 0
            left = lots[0][1] if lots else 0
            for sid, qty in conn.execute("SELECT id, qty FROM sales WHERE species = ? ORDER BY sold_on, id", (sp,)):
                need = qty
                while need > 0 and i < len(lots):
                    take = min(need, left)
                    if take > 0:
                        out.append((sp, sid, lots[i][0], take))
                    need -= take
                    left -= take
                    if left == 0:
                        i += 1
                        left = lots[i][1] if i < len(lots) else 0
                if need > 0:
                    out.append((sp, sid, None, need))
        return out
''', '''
    Per species, the sales (oldest `sold_on` first, ties by sale `id`) take their quantities from the lots of that species in FIFO order (oldest `received_on` first, ties by lot
    `id`), regardless of dates: the first sale empties the first lot before touching the second, and so on; a lot is never used beyond its `qty`.

    Output rows `species`, `sale_id`, `lot_id`, `qty` - one row for every (sale, lot) pair where the sale took a positive quantity from the lot - and, when the lots of the species ran out
    before the sale was covered, one extra row with `lot_id` NULL holding the **missing** quantity (after the rows of that sale's lots). Sales of quantity 0 and lots of quantity 0 produce no rows.

    Rows are ordered by `species`, then the order of the sales (as above), then the lot order, with the NULL row last for its sale.
''', _stock_data, 5)


@family("port-python-to-sql", category="port", lang="sql", kind="greenfield", n=6,
        summary="translate an imperative python report into one SQL query that matches it on any data (sqlite)")
def gen_sql(rng, n):
    keys = ["ferry-load", "item-pairs", "tide-top", "late-fees", "reading-streaks", "seed-stock"]
    prompts = [
        "`reference.py` computes the {title} report with loops over sqlite queries. We want the same result from one SQL statement. Write it to `query.sql` (a single SELECT, CTEs and window functions are fine). README.md describes the output columns and ordering; the query will be run against several different datasets and compared with what `reference.py` returns.",
        "port the python report in reference.py ({title}) to SQL: put one SELECT in query.sql, same columns, same rows, same order, for any data with the schema in schema.sql. hidden datasets include empty tables, ties and NULLs.",
        "Ticket: replace the Python loops of the {title} report by a single query. Acceptance: `query.sql` holds one SELECT statement; on every dataset it returns exactly the rows `reference.py` would return, in the same order (see README.md for the rules).",
        "The {title} report is slow because it queries sqlite in a loop. Translate `report(conn)` from reference.py into one statement in query.sql. Behaviour must match precisely, including ordering and tie-breaking; README.md has the specification.",
    ]
    for i in range(n):
        r = REPORTS[keys[i % len(keys)]]
        datasets = [r["gen"](rng, k) for k in range(7)]
        datasets.append({t: [] for t in r["gen"](rng, 0)})
        schema_sql = r["schema"]
        # expected results from the reference implementation
        ns = {}
        exec(compile(r["reference"], "reference.py", "exec"), ns)
        cases = []
        for data in datasets:
            conn = sqlite3.connect(":memory:")
            conn.executescript(schema_sql)
            for table, rows in data.items():
                if rows:
                    conn.executemany("INSERT INTO %s VALUES (%s)" % (table, ",".join("?" * len(rows[0]))), rows)
            want = [list(x) for x in ns["report"](conn)]
            cases.append({"data": data, "want": want})
        if sum(1 for c in cases if c["want"]) < 4:
            raise RuntimeError(f"{keys[i % len(keys)]}: too many empty expected results")
        hidden = HIDDEN % dict(schema=repr(schema_sql), cases=repr(json.dumps(cases)))
        vis = HIDDEN % dict(schema=repr(schema_sql), cases=repr(json.dumps([next(c for c in cases if c["want"])])))
        # reference solution query is written by hand per report below
        sol = SOLUTIONS[r["key"]]
        conn = sqlite3.connect(":memory:")
        for c in cases:
            conn = sqlite3.connect(":memory:")
            conn.executescript(schema_sql)
            for table, rows in c["data"].items():
                if rows:
                    conn.executemany("INSERT INTO %s VALUES (%s)" % (table, ",".join("?" * len(rows[0]))), rows)
            got = [list(x) for x in conn.execute(sol)]
            if got != c["want"]:
                raise RuntimeError(f"{r['key']}: reference SQL disagrees with the python reference:\n{got[:3]}\n{c['want'][:3]}")
        readme = (f"# {r['title']}\n\n{r['blurb']}\n\n`schema.sql` holds the tables, `reference.py` the current Python implementation (`report(conn)` returns the rows). "
                  f"The goal is `query.sql`: one SQL statement for sqlite (SELECT, optionally with CTEs and window functions) that returns exactly the same rows as `report(conn)`, "
                  f"in the same order, with the same column order and value types (integers stay integers; NULL is None).\n\n## Output\n\n{r['readme']}")
        yield Task(
            slug=f"{i + 1:02d}-{r['key']}",
            prompt=rng.choice(prompts).format(title=r["title"]),
            difficulty=r["difficulty"],
            lang="sql",
            kind="greenfield",
            start={"schema.sql": schema_sql, "reference.py": "import sqlite3\n\n\n" + r["reference"], "README.md": readme, "tests/test_example.py": vis},
            hidden={"tests/test_datasets.py": hidden},
            solution={"query.sql": sol},
            verify="python3 -m unittest discover -s tests -v",
            protected=["schema.sql", "reference.py", "README.md"],
            tags=["port", "python-to-sql", r["key"]],
            notes={"report": r["key"], "datasets": len(cases)},
        )


SOLUTIONS = {
    "ferry-load": dd('''
        SELECT s.route, s.depart, s.capacity,
               COALESCE(SUM(CASE b.status WHEN 'confirmed' THEN b.party_size WHEN 'pending' THEN (b.party_size + 1) / 2 ELSE 0 END), 0) AS held,
               s.capacity - COALESCE(SUM(CASE b.status WHEN 'confirmed' THEN b.party_size WHEN 'pending' THEN (b.party_size + 1) / 2 ELSE 0 END), 0) AS free,
               CASE WHEN COALESCE(SUM(CASE b.status WHEN 'confirmed' THEN b.party_size WHEN 'pending' THEN (b.party_size + 1) / 2 ELSE 0 END), 0) > s.capacity THEN 1 ELSE 0 END AS over
        FROM sailings s
        LEFT JOIN bookings b ON b.sailing_id = s.id
        GROUP BY s.id
        ORDER BY s.route, s.depart, s.id;
    '''),
    "item-pairs": dd('''
        WITH distinct_lines AS (
          SELECT DISTINCT order_id, item FROM order_lines
        )
        SELECT a.item AS item_a, b.item AS item_b, COUNT(*) AS orders
        FROM distinct_lines a
        JOIN distinct_lines b ON a.order_id = b.order_id AND a.item < b.item
        GROUP BY a.item, b.item
        HAVING COUNT(*) >= 2
        ORDER BY orders DESC, item_a, item_b;
    '''),
    "tide-top": dd('''
        WITH ranked AS (
          SELECT station, substr(ts, 1, 10) AS day, ts, height_cm,
                 ROW_NUMBER() OVER (PARTITION BY station, substr(ts, 1, 10) ORDER BY height_cm DESC, ts ASC) AS rank
          FROM tides
        )
        SELECT station, day, rank, ts, height_cm
        FROM ranked
        WHERE rank <= 2
        ORDER BY station, day, rank;
    '''),
    "late-fees": dd('''
        WITH fees AS (
          SELECT m.id AS member_id, m.name AS name,
                 MIN(MAX(CAST(julianday(COALESCE(l.returned_on, '2024-12-31')) - julianday(l.borrowed_on) AS INTEGER)
                         - CASE m.tier WHEN 'gold' THEN 21 ELSE 14 END, 0) * 25, 1000) AS fee
          FROM members m
          JOIN loans l ON l.member_id = m.id
        )
        SELECT name, COUNT(*) AS late_loans, SUM(fee) AS total_fee
        FROM fees
        WHERE fee > 0
        GROUP BY member_id, name
        ORDER BY total_fee DESC, name;
    '''),
    "reading-streaks": dd('''
        WITH hot AS (
          SELECT sensor, day, day - ROW_NUMBER() OVER (PARTITION BY sensor ORDER BY day) AS grp
          FROM readings
          WHERE value >= 10
        ),
        streaks AS (
          SELECT sensor, MIN(day) AS start_day, COUNT(*) AS length
          FROM hot
          GROUP BY sensor, grp
        ),
        best AS (
          SELECT sensor, start_day, length,
                 ROW_NUMBER() OVER (PARTITION BY sensor ORDER BY length DESC, start_day ASC) AS rn
          FROM streaks
        )
        SELECT sensor, start_day, length FROM best WHERE rn = 1 ORDER BY sensor;
    '''),
    "seed-stock": dd('''
        WITH lot_ranges AS (
          SELECT id AS lot_id, species, qty,
                 SUM(qty) OVER (PARTITION BY species ORDER BY received_on, id) - qty AS lo,
                 SUM(qty) OVER (PARTITION BY species ORDER BY received_on, id) AS hi,
                 ROW_NUMBER() OVER (PARTITION BY species ORDER BY received_on, id) AS lot_rank
          FROM lots
        ),
        sale_ranges AS (
          SELECT id AS sale_id, species, qty,
                 SUM(qty) OVER (PARTITION BY species ORDER BY sold_on, id) - qty AS lo,
                 SUM(qty) OVER (PARTITION BY species ORDER BY sold_on, id) AS hi,
                 ROW_NUMBER() OVER (PARTITION BY species ORDER BY sold_on, id) AS sale_rank
          FROM sales
        ),
        totals AS (
          SELECT species, SUM(qty) AS total FROM lots GROUP BY species
        ),
        taken AS (
          SELECT s.species, s.sale_rank, s.sale_id, 0 AS is_missing, l.lot_rank AS lot_rank, l.lot_id AS lot_id,
                 MIN(s.hi, l.hi) - MAX(s.lo, l.lo) AS q
          FROM sale_ranges s
          JOIN lot_ranges l ON l.species = s.species AND MIN(s.hi, l.hi) > MAX(s.lo, l.lo)
        ),
        missing AS (
          SELECT s.species, s.sale_rank, s.sale_id, 1 AS is_missing, 0 AS lot_rank, NULL AS lot_id,
                 s.hi - MAX(s.lo, COALESCE(t.total, 0)) AS q
          FROM sale_ranges s
          LEFT JOIN totals t ON t.species = s.species
          WHERE s.hi > COALESCE(t.total, 0) AND s.qty > 0
        ),
        all_rows AS (
          SELECT * FROM taken UNION ALL SELECT * FROM missing
        )
        SELECT species, sale_id, lot_id, q AS qty
        FROM all_rows
        ORDER BY species, sale_rank, is_missing, lot_rank;
    '''),
}
