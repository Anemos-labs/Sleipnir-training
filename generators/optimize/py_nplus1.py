"""N+1 queries and row-at-a-time writes against SQLite (python): the number of statements and commits is counted."""
from __future__ import annotations

import json
import random
from string import Template

from fx import Task, dd, family

from ._kit import PY_ALL, PY_CORRECT, PY_PERF, prove_opt

DBCOUNT = '''"""A sqlite3 connection that counts the statements and commits issued through it."""
import sqlite3


class CountingCursor(sqlite3.Cursor):
    def execute(self, *a, **k):
        self.connection.statements += 1
        return super().execute(*a, **k)

    def executemany(self, *a, **k):
        self.connection.statements += 1
        return super().executemany(*a, **k)

    def executescript(self, *a, **k):
        self.connection.statements += 1
        return super().executescript(*a, **k)


class CountingConnection(sqlite3.Connection):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.statements = 0
        self.commits = 0

    def cursor(self, factory=CountingCursor):
        return super().cursor(factory)

    def execute(self, *a, **k):
        self.statements += 1
        return super().execute(*a, **k)

    def executemany(self, *a, **k):
        self.statements += 1
        return super().executemany(*a, **k)

    def executescript(self, *a, **k):
        self.statements += 1
        return super().executescript(*a, **k)

    def commit(self):
        self.commits += 1
        super().commit()

    def reset(self):
        self.statements = 0
        self.commits = 0


def connect():
    return sqlite3.connect(":memory:", factory=CountingConnection)
'''

VOCABS = [
    dict(P="authors", PN="name", C="books", CT="title", FK="author_id", CD="published", pk="author", ck="book", pkg="library", noun="catalogue"),
    dict(P="playlists", PN="name", C="tracks", CT="title", FK="playlist_id", CD="added", pk="playlist", ck="track", pkg="jukebox", noun="music library"),
    dict(P="clinics", PN="name", C="visits", CT="reason", FK="clinic_id", CD="seen_on", pk="clinic", ck="visit", pkg="clinicdb", noun="clinic network"),
    dict(P="routes", PN="name", C="stops", CT="stop_name", FK="route_id", CD="planned", pk="route", ck="stop", pkg="transit", noun="timetable"),
    dict(P="labs", PN="name", C="samples", CT="label", FK="lab_id", CD="received", pk="lab", ck="sample", pkg="labtrack", noun="sample tracker"),
    dict(P="projects", PN="name", C="tasks", CT="summary", FK="project_id", CD="created", pk="project", ck="task", pkg="taskboard", noun="project board"),
]

SCHEMA = """CREATE TABLE $P (id INTEGER PRIMARY KEY, $PN TEXT NOT NULL);
CREATE TABLE $C (id INTEGER PRIMARY KEY, $FK INTEGER NOT NULL REFERENCES $P(id), $CT TEXT NOT NULL, $CD INTEGER NOT NULL);
CREATE INDEX idx_${C}_$FK ON $C($FK);
"""

SHAPES = {
    "children": dict(
        d=2, limit=3, fname="{ck}s_by_{pk}", doc="Every {pk} with the titles of its {ck}s.", signature="conn",
        naive='''def $f(conn):
    """$doc"""
    out = []
    owners = conn.execute("SELECT id, $PN FROM $P ORDER BY $PN").fetchall()
    for owner_id, owner_name in owners:
        rows = conn.execute("SELECT $CT FROM $C WHERE $FK = ? ORDER BY $CT", (owner_id,)).fetchall()
        out.append((owner_name, [r[0] for r in rows]))
    return out
''', fast='''def $f(conn):
    """$doc"""
    out = {}
    order = []
    rows = conn.execute(
        "SELECT p.$PN, c.$CT FROM $P p LEFT JOIN $C c ON c.$FK = p.id ORDER BY p.$PN, c.$CT"
    ).fetchall()
    for owner_name, title in rows:
        if owner_name not in out:
            out[owner_name] = []
            order.append(owner_name)
        if title is not None:
            out[owner_name].append(title)
    return [(name, out[name]) for name in order]
''', spec="Returns a list of `(name, [titles])`: every row of `{P}` (even those without `{C}`) ordered by name, with the `{CT}` values of its `{C}` rows sorted alphabetically.",
        seed="children", expected="children"),
    "lookup": dict(
        d=2, limit=3, fname="{ck}_{pk}_names", doc="Every {ck} with the name of the {pk} it belongs to.", signature="conn",
        naive='''def $f(conn):
    """$doc"""
    out = []
    for row_id, owner_id in conn.execute("SELECT id, $FK FROM $C ORDER BY id").fetchall():
        name = conn.execute("SELECT $PN FROM $P WHERE id = ?", (owner_id,)).fetchone()[0]
        out.append((row_id, name))
    return out
''', fast='''def $f(conn):
    """$doc"""
    rows = conn.execute("SELECT c.id, p.$PN FROM $C c JOIN $P p ON p.id = c.$FK ORDER BY c.id")
    return [(row_id, name) for row_id, name in rows]
''', spec="Returns `(id, name)` for every row of `{C}` in id order, where `name` is the `{PN}` of the `{P}` row it points to.", seed="children", expected="lookup"),
    "counts": dict(
        d=2, limit=3, fname="{ck}_counts", doc="How many {ck}s every {pk} has.", signature="conn",
        naive='''def $f(conn):
    """$doc"""
    counts = {}
    for owner_id, name in conn.execute("SELECT id, $PN FROM $P").fetchall():
        counts[name] = conn.execute("SELECT COUNT(*) FROM $C WHERE $FK = ?", (owner_id,)).fetchone()[0]
    return counts
''', fast='''def $f(conn):
    """$doc"""
    rows = conn.execute(
        "SELECT p.$PN, COUNT(c.id) FROM $P p LEFT JOIN $C c ON c.$FK = p.id GROUP BY p.id"
    )
    return {name: n for name, n in rows}
''', spec="Returns a dict from every `{PN}` of `{P}` to the number of its `{C}` rows (0 when it has none).", seed="children", expected="counts"),
    "latest": dict(
        d=3, limit=3, fname="latest_{ck}_per_{pk}", doc="The most recent {ck} of every {pk}.", signature="conn",
        naive='''def $f(conn):
    """$doc"""
    out = []
    for owner_id, name in conn.execute("SELECT id, $PN FROM $P ORDER BY $PN").fetchall():
        row = conn.execute(
            "SELECT $CT FROM $C WHERE $FK = ? ORDER BY $CD DESC, id DESC LIMIT 1", (owner_id,)
        ).fetchone()
        out.append((name, row[0] if row else None))
    return out
''', fast='''def $f(conn):
    """$doc"""
    rows = conn.execute(
        "SELECT p.$PN, (SELECT c.$CT FROM $C c WHERE c.$FK = p.id ORDER BY c.$CD DESC, c.id DESC LIMIT 1) "
        "FROM $P p ORDER BY p.$PN"
    )
    return [(name, title) for name, title in rows]
''', spec="Returns `(name, {CT})` for every `{P}` row ordered by name: the `{CT}` of its newest `{C}` row (largest `{CD}`, ties broken by the larger id), or `None` when it has none.",
        seed="children", expected="latest", limit_hint=3),
    "missing": dict(
        d=2, limit=3, fname="unknown_{ck}_codes", doc="Which of the requested codes are not in the table.", signature="conn, codes",
        naive='''def $f(conn, codes):
    """$doc"""
    missing = []
    for code in codes:
        row = conn.execute("SELECT 1 FROM $C WHERE $CT = ?", (code,)).fetchone()
        if row is None:
            missing.append(code)
    return missing
''', fast='''def $f(conn, codes):
    """$doc"""
    known = {row[0] for row in conn.execute("SELECT $CT FROM $C")}
    return [code for code in codes if code not in known]
''', spec="`codes` is a list of strings. Returns those that do not occur in the `{CT}` column of `{C}`, in the order given (repeats stay).", seed="children", expected="missing"),
    "import": dict(
        d=3, limit=3, fname="import_{ck}s", doc="Load new rows, skipping ones that already exist.", signature="conn, rows",
        naive='''def $f(conn, rows):
    """$doc"""
    import sqlite3

    added = 0
    for owner_id, title, when in rows:
        try:
            conn.execute("INSERT INTO $C ($FK, $CT, $CD) VALUES (?, ?, ?)", (owner_id, title, when))
            conn.commit()
            added += 1
        except sqlite3.IntegrityError:
            conn.rollback()
    return added
''', fast='''def $f(conn, rows):
    """$doc"""
    before = conn.total_changes
    conn.executemany("INSERT OR IGNORE INTO $C ($FK, $CT, $CD) VALUES (?, ?, ?)", rows)
    conn.commit()
    return conn.total_changes - before
''', spec="`rows` is a list of `({FK}, {CT}, {CD})` tuples. Inserts those that are not yet present: a row is a duplicate when the `({FK}, {CT})` pair already exists in `{C}` (the table has a unique index on it). Returns how many rows were added, and commits once at the end.",
        seed="children", expected="import"),
}


def _schema(v, shape):
    s = Template(SCHEMA).substitute(v)
    if shape == "import":
        s += Template("CREATE UNIQUE INDEX uq_${C} ON $C($FK, $CT);\n").substitute(v)
    if shape == "missing":
        s += Template("CREATE UNIQUE INDEX uq_${C}_code ON $C($CT);\n").substitute(v)
    return s


HELPERS = '''
def expected(shape, parents, children, extra=None):
    names = {pid: name for pid, name in parents}
    if shape == "children":
        by = {pid: [] for pid, _ in parents}
        for _, pid, title, _ in children:
            by[pid].append(title)
        return [(names[pid], sorted(by[pid])) for pid, _ in sorted(parents, key=lambda p: p[1])]
    if shape == "lookup":
        return [(cid, names[pid]) for cid, pid, _, _ in sorted(children)]
    if shape == "counts":
        out = {name: 0 for _, name in parents}
        for _, pid, _, _ in children:
            out[names[pid]] += 1
        return out
    if shape == "latest":
        best = {}
        for cid, pid, title, when in children:
            if pid not in best or (when, cid) > best[pid][0]:
                best[pid] = ((when, cid), title)
        return [(names[pid], best[pid][1] if pid in best else None) for pid, _ in sorted(parents, key=lambda p: p[1])]
    if shape == "missing":
        known = {title for _, _, title, _ in children}
        return [c for c in extra if c not in known]
    if shape == "import":
        have = {(pid, title) for _, pid, title, _ in children}
        added = 0
        for pid, title, when in extra:
            if (pid, title) not in have:
                have.add((pid, title))
                added += 1
        return added


def seed(rng, shape, n_parents, n_children):
    parents = [(i + 1, "P%03d" % i) for i in range(n_parents)]
    children, seen, k = [], set(), 0
    while len(children) < n_children:
        pid = rng.randrange(1, n_parents + 1)
        if shape == "missing":
            title = "C%05d" % k
        elif shape == "import":
            title = "t%03d" % rng.randrange(0, 4 * n_children)
        else:
            title = "t%03d" % rng.randrange(0, 40)
        key = title if shape == "missing" else (pid, title)
        k += 1
        if shape in ("import", "missing") and key in seen:
            continue
        seen.add(key)
        children.append((len(children) + 1, pid, title, rng.randrange(0, 50 if shape == "latest" else 1000)))
    return parents, children


def make_extra(rng, shape, parents, children, big):
    if shape == "missing":
        known = [c[2] for c in children]
        n = 300 if big else 12
        return [rng.choice(known) if (known and rng.random() < 0.5) else "X%05d" % rng.randrange(0, 99999) for _ in range(n)]
    if shape == "import":
        have = [(c[1], c[2]) for c in children]
        n = 300 if big else 10
        rows = []
        for _ in range(n):
            if have and rng.random() < 0.3:
                pid, title = rng.choice(have)
            else:
                pid, title = rng.randrange(1, len(parents) + 1), "new%04d" % rng.randrange(0, 4 * n)
            rows.append((pid, title, rng.randrange(0, 1000)))
        return rows
    return None
'''


@family("optimize-py-nplus1", category="optimize", lang="python", kind="feature", n=9,
        summary="N+1 queries, per-row lookups and row-at-a-time commits on SQLite: the statement and commit counts must stay constant")
def gen(rng, n):
    order = list(SHAPES) * 3
    rng.shuffle(order)
    vocabs = list(VOCABS) * 3
    rng.shuffle(vocabs)
    for i in range(n):
        shape = order[i]
        sp = SHAPES[shape]
        v = vocabs[i]
        f = sp["fname"].format(**v)
        pkg = v["pkg"]
        mod = rng.choice(["queries", "reports", "repo", "store"])
        subs = {**v, "f": f, "doc": sp["doc"].format(**v)}
        head_doc = f'"""{pkg}: reports over the {v["noun"]} database."""\n\n\n'
        start_src = head_doc + Template(sp["naive"]).substitute(subs)
        sol_src = head_doc + Template(sp["fast"]).substitute(subs)
        schema = _schema(v, shape)
        readme = (f"# {pkg}\n\nThe database is SQLite; every function takes an open `sqlite3.Connection` that the caller owns.\n\n"
                  f"## `{mod}.{f}({sp['signature']})`\n\n{sp['doc'].format(**v)}\n\n{sp['spec'].format(**v)}\n\n"
                  "The tables hold tens of thousands of rows in production and the database is reached over a slow network\n"
                  "filesystem, so the number of statements (and commits) a call issues matters more than anything else.\n\n"
                  f"```sql\n{schema.strip()}\n```\n")
        files = {f"{pkg}/{mod}.py": start_src, f"{pkg}/__init__.py": "", "README.md": readme}
        two = shape in ("missing", "import")
        call = f"{f}(conn, extra)" if two else f"{f}(conn)"
        table_rows = f'def table_rows(conn):\n    return sorted(conn.execute("SELECT {v["FK"]}, {v["CT"]} FROM {v["C"]}").fetchall())\n'
        build = (f"def build(rng, n_parents, n_children):\n    conn = connect()\n    conn.executescript(SCHEMA)\n    parents, children = seed(rng, SHAPE, n_parents, n_children)\n"
                 f"    conn.executemany(\"INSERT INTO {v['P']} (id, {v['PN']}) VALUES (?, ?)\", parents)\n"
                 f"    conn.executemany(\"INSERT INTO {v['C']} (id, {v['FK']}, {v['CT']}, {v['CD']}) VALUES (?, ?, ?, ?)\", children)\n"
                 "    conn.commit()\n    conn.reset()\n    return conn, parents, children\n")
        common = (f"import random\nimport unittest\n\nfrom dbcount import connect\nfrom {pkg}.{mod} import {f}\n\nSCHEMA = {json.dumps(schema)}\nSHAPE = {shape!r}\n"
                  + HELPERS + "\n" + table_rows + "\n" + build)
        seedn = 1000 + i
        post = ""
        if shape == "import":
            post = ("                    have = {(c[1], c[2]) for c in children} | {(pid, title) for pid, title, _ in extra}\n"
                    "                    self.assertEqual(table_rows(conn), sorted(have))\n")
        corr = (common + "\n\nclass CorrectnessTests(unittest.TestCase):\n    def test_random_databases(self):\n"
                f"        rng = random.Random({seedn})\n        for trial in range(25):\n"
                "            conn, parents, children = build(rng, rng.randrange(1, 9), rng.randrange(0, 30))\n"
                "            extra = make_extra(rng, SHAPE, parents, children, False)\n"
                "            want = expected(SHAPE, parents, children, extra)\n"
                f"            self.assertEqual({call}, want)\n"
                + post.replace("                    have", "            have").replace("                    self", "            self") +
                "\n    def test_empty_tables(self):\n        conn, parents, children = build(random.Random(1), 1, 0)\n"
                "        extra = make_extra(random.Random(2), SHAPE, parents, children, False)\n"
                f"        self.assertEqual({call}, expected(SHAPE, parents, children, extra))\n")
        limit = sp["limit"]
        perf = (common + "\n\nclass PerformanceTests(unittest.TestCase):\n    def test_statement_count_does_not_grow_with_the_data(self):\n"
                f"        rng = random.Random({seedn})\n        conn, parents, children = build(rng, 150, 1200)\n"
                "        extra = make_extra(rng, SHAPE, parents, children, True)\n"
                f"        got = {call}\n        self.assertEqual(got, expected(SHAPE, parents, children, extra))\n"
                f"        self.assertLessEqual(conn.statements, {limit}, \"PERF: %d statements for 150 parents and 1200 child rows (limit {limit}): queries are issued per row\" % conn.statements)\n"
                "        self.assertLessEqual(conn.commits, 2, \"PERF: %d commits (limit 2)\" % conn.commits)\n")
        hidden = {"tests/dbcount.py": DBCOUNT, "tests/test_correct_db.py": corr, "tests/test_perf_db.py": perf}
        ns = {}
        exec(HELPERS, ns)
        vr = random.Random(500 + i)
        parents, children = ns["seed"](vr, shape, 3, 7)
        extra = ns["make_extra"](vr, shape, parents, children, False)
        want = ns["expected"](shape, parents, children, extra)
        vis = (f"import sqlite3\nimport unittest\n\nfrom {pkg}.{mod} import {f}\n\nSCHEMA = {json.dumps(schema)}\nPARENTS = {parents!r}\nCHILDREN = {children!r}\nEXTRA = {extra!r}\n\n\n"
               "class BasicTests(unittest.TestCase):\n    def setUp(self):\n        self.conn = sqlite3.connect(\":memory:\")\n        self.conn.executescript(SCHEMA)\n"
               f"        self.conn.executemany(\"INSERT INTO {v['P']} (id, {v['PN']}) VALUES (?, ?)\", PARENTS)\n"
               f"        self.conn.executemany(\"INSERT INTO {v['C']} (id, {v['FK']}, {v['CT']}, {v['CD']}) VALUES (?, ?, ?, ?)\", CHILDREN)\n"
               "        self.conn.commit()\n\n    def test_small_database(self):\n        conn = self.conn\n        extra = EXTRA\n"
               f"        self.assertEqual({call}, {want!r})\n\n\nif __name__ == \"__main__\":\n    unittest.main()\n")
        start = {**files, "tests/test_basic.py": vis}
        solution = {f"{pkg}/{mod}.py": sol_src}
        prove_opt(f"{shape}/{v['pkg']}", start, hidden, solution, PY_CORRECT, PY_PERF, PY_ALL)
        prompts = [
            f"The {v['noun']} report `{f}` in `{pkg}/{mod}.py` is painfully slow in production: the database sits on a network filesystem and the page for a big install takes "
            f"minutes. It looks like it talks to SQLite far too often. Fix it so the number of statements no longer depends on the amount of data. The README describes the result; it must not change.",
            f"perf: `{f}` ({pkg}/{mod}.py) issues one query (or one commit) per row. Make the statement count constant, keep the output identical.",
            f"Support ticket: \"the {v['noun']} export takes forever for large accounts.\" A trace shows `{f}` running hundreds of tiny statements. Please restructure it to a handful of "
            f"statements (batching, a join, or a set-based query), and keep the results exactly as documented. Don't change its signature. Our CI counts statements and commits per call.",
            f"Could you fix the N+1 pattern in `{f}` (`{pkg}/{mod}.py`)? {sp['doc'].format(**v)} The behaviour has to stay exactly the same.",
        ]
        yield Task(slug=f"{i + 1:02d}-{shape}-{v['pk']}", prompt=rng.choice(prompts), difficulty=sp["d"], start=start, hidden=hidden, solution=solution, verify=PY_ALL,
                   tags=["sqlite", "n-plus-one", "batching", "query-counter"], notes={"shape": shape, "vocab": v["pk"]})
