"""Shared machinery for the SQL families of the `data` category.

A *domain* is an invented schema plus a data generator. A *spec* is one task on that domain: a prompt, a reference SQL
solution and a few flags. ``query_tasks`` turns specs into fixtures:

    start/   README.md, schema.sql, seed.sql (a small SAMPLE), query.sql (stub or buggy query), tools/runsql.py
    hidden/  tests/check_query.py, tests/spec.json, tests/schema.sql, tests/data1.sql ... (other datasets), tests/ref.sql

The hidden checker builds fresh SQLite databases from the hidden datasets (same schema, different rows), runs the
agent's ``query.sql`` and the reference query against each one and compares the rows. Hard-coding the sample fails.

Guards run at generation time (a failure raises, so a bad spec never ships):
  * the reference result is the same when every table's rows are inserted in another order (no hidden tie-breaking
    decisions: a fair spec has a fully determined result);
  * the reference result is not empty on the hidden datasets and differs from the sample result;
  * every ``wrong`` query given with a spec is rejected by the real checker (the hidden data discriminates).
"""
from __future__ import annotations

import json
import random
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Callable

from fx import Task, dd, merged, run

# --------------------------------------------------------------------------------------------------------------
# literals and datasets


def lit(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(round(v, 6))
    return "'" + str(v).replace("'", "''") + "'"


def table_columns(schema: str) -> dict[str, list[str]]:
    con = sqlite3.connect(":memory:")
    con.executescript(schema)
    out = {}
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid"):
        out[name] = [r[1] for r in con.execute(f"PRAGMA table_info({name})")]
    return out


def dataset_sql(cols: dict[str, list[str]], data: dict[str, list[tuple]], pretty: bool = False, shuffle: random.Random | None = None) -> str:
    out: list[str] = []
    for table, rows in data.items():
        rows = list(rows)
        if shuffle is not None:
            shuffle.shuffle(rows)
        if not rows:
            continue
        cl = ", ".join(cols[table])
        if pretty:
            for r in rows:
                out.append(f"INSERT INTO {table} ({cl}) VALUES ({', '.join(lit(v) for v in r)});")
        else:
            for i in range(0, len(rows), 40):
                chunk = rows[i:i + 40]
                out.append(f"INSERT INTO {table} ({cl}) VALUES\n" + ",\n".join("  (" + ", ".join(lit(v) for v in r) + ")" for r in chunk) + ";")
        out.append("")
    return "\n".join(out)


def exec_rows(schema: str, data_sql: str, sql: str, timeout: float = 10.0) -> list[tuple]:
    con = sqlite3.connect(":memory:")
    con.executescript(schema)
    con.executescript(data_sql)
    t0 = time.time()
    con.set_progress_handler(lambda: 1 if time.time() - t0 > timeout else 0, 100000)
    return con.execute(sql).fetchall()


def norm_rows(rows, places: int = 4, ordered: bool = False):
    def nv(v):
        if isinstance(v, float):
            r = round(v, places)
            return int(r) if r == int(r) else r
        if isinstance(v, bytes):
            return v.hex()
        return v

    out = [tuple(nv(v) for v in r) for r in rows]
    if not ordered:
        out.sort(key=lambda r: [(x is None, str(x)) for x in r])
    return out


def fmt_table(cols: list[str], rows: list[tuple], limit: int = 12) -> str:
    def s(v):
        if v is None:
            return "NULL"
        if isinstance(v, float):
            return f"{v:.4f}".rstrip("0").rstrip(".")
        return str(v)

    body = [[s(v) for v in r] for r in rows[:limit]]
    widths = [max(len(c), *(len(r[i]) for r in body)) if body else len(c) for i, c in enumerate(cols)]
    lines = [" | ".join(c.ljust(w) for c, w in zip(cols, widths)).rstrip(),
             "-+-".join("-" * w for w in widths)]
    lines += [" | ".join(v.ljust(w) for v, w in zip(r, widths)).rstrip() for r in body]
    if len(rows) > limit:
        lines.append(f"... ({len(rows)} rows in all)")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------------------------
# visible helper and hidden checkers

RUNSQL = r'''#!/usr/bin/env python3
"""Run a .sql file against an in-memory SQLite database built from schema.sql + seed.sql and print what it returns.

    python3 tools/runsql.py                # runs query.sql
    python3 tools/runsql.py other.sql      # runs another file
    python3 tools/runsql.py --explain q.sql   # also prints EXPLAIN QUERY PLAN

The file may hold several statements; rows of the last statement that returns any are printed.
"""
import sqlite3
import sys


def show(cur):
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description or []]
    def s(v):
        return "NULL" if v is None else str(v)
    body = [[s(v) for v in r] for r in rows]
    widths = [max([len(c)] + [len(r[i]) for r in body]) for i, c in enumerate(cols)]
    print(" | ".join(c.ljust(w) for c, w in zip(cols, widths)).rstrip())
    print("-+-".join("-" * w for w in widths))
    for r in body:
        print(" | ".join(v.ljust(w) for v, w in zip(r, widths)).rstrip())
    print(f"({len(rows)} rows)")


def main(argv):
    explain = "--explain" in argv
    args = [a for a in argv if not a.startswith("--")]
    path = args[0] if args else "query.sql"
    con = sqlite3.connect(":memory:")
    con.executescript(open("schema.sql", encoding="utf-8").read())
    con.executescript(open("seed.sql", encoding="utf-8").read())
    sql = open(path, encoding="utf-8").read()
    buf = ""
    last = None
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if explain:
                show(con.execute("EXPLAIN QUERY PLAN " + buf))
            cur = con.execute(buf)
            if cur.description:
                last = cur
                rows = cur.fetchall()
                cur2 = type("C", (), {"fetchall": lambda self, r=rows: r, "description": cur.description})()
                last = cur2
            buf = ""
    if buf.strip() and not all(l.strip().startswith("--") or not l.strip() for l in buf.splitlines()):
        print("warning: the file ends with an unterminated statement (missing semicolon?)", file=sys.stderr)
        cur = con.execute(buf)
        if cur.description:
            rows = cur.fetchall()
            last = type("C", (), {"fetchall": lambda self, r=rows: r, "description": cur.description})()
    if last is None:
        print("(no statement returned rows)")
    else:
        show(last)


if __name__ == "__main__":
    main(sys.argv[1:])
'''

_CHECK_COMMON = r'''
import json
import re
import sqlite3
import sys
import time

SPEC = json.load(open("tests/spec.json", encoding="utf-8"))
SCHEMA = open("tests/schema.sql", encoding="utf-8").read()
PLACES = SPEC.get("places", 4)


def build(path):
    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA)
    con.executescript(open(path, encoding="utf-8").read())
    return con


def guarded(con, sql, seconds=10):
    t0 = time.time()
    con.set_progress_handler(lambda: 1 if time.time() - t0 > seconds else 0, 100000)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.set_progress_handler(None, 0)


def norm(rows, ordered):
    def nv(v):
        if isinstance(v, float):
            r = round(v, PLACES)
            return int(r) if r == int(r) else r
        if isinstance(v, bytes):
            return v.hex()
        return v
    out = [tuple(nv(v) for v in r) for r in rows]
    if not ordered:
        out.sort(key=lambda r: [(x is None, str(x)) for x in r])
    return out


def fail(msg):
    print("FAIL: " + msg)
    sys.exit(1)
'''

CHECK_QUERY = _CHECK_COMMON + r'''

def main():
    sql = open("query.sql", encoding="utf-8").read()
    body = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")).strip()
    if not body:
        fail("query.sql is empty")
    ref = open("tests/ref.sql", encoding="utf-8").read()
    ordered = SPEC["ordered"]
    for i, path in enumerate(SPEC["datasets"], 1):
        con = build(path)
        try:
            got = guarded(con, sql)
        except sqlite3.Error as e:
            fail(f"query.sql raised {type(e).__name__}: {e}")
        want = guarded(con, ref)
        if got and len(got[0]) != len(want[0]):
            fail(f"dataset {i}: the query returns {len(got[0])} columns, expected {len(want[0])}")
        g, w = norm(got, ordered), norm(want, ordered)
        if g != w:
            extra = ""
            if len(g) != len(w):
                extra = f" (got {len(g)} rows, expected {len(w)})"
            elif ordered and sorted(map(repr, g)) == sorted(map(repr, w)):
                extra = " (right rows, wrong order)"
            else:
                bad = sum(1 for a, b in zip(g, w) if a != b)
                extra = f" ({bad} of {len(w)} rows differ)"
            fail(f"dataset {i}: result differs from the expected one{extra}")
    print(f"ok: {len(SPEC['datasets'])} datasets")


main()
'''

CHECK_SCRIPT = _CHECK_COMMON + r'''

def struct_facts(con, kind):
    what, _, arg = kind.partition(":")
    if what == "tables":
        return sorted(r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
    if what == "views":
        return sorted(r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='view'"))
    if what == "triggers":
        return sorted(r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='trigger'"))
    if what == "columns":
        return sorted((r[1], (r[2] or "").upper(), r[3], 1 if r[5] else 0) for r in con.execute(f"PRAGMA table_info({arg})"))
    if what == "fks":
        return sorted((r[3], r[2], r[4] or "", (r[6] or "").upper()) for r in con.execute(f"PRAGMA foreign_key_list({arg})"))
    if what == "indexes":
        out = []
        for r in con.execute(f"PRAGMA index_list({arg})"):
            if r[3] in ("c", "u"):
                cols = tuple(c[2] for c in con.execute(f"PRAGMA index_info({r[1]})"))
                out.append((r[2], cols))
        return sorted(out)
    raise SystemExit("bad struct kind " + kind)


def run_all(path, script_path, twice):
    con = build(path)
    text = open(script_path, encoding="utf-8").read()
    try:
        con.executescript(text)
        if twice:
            con.executescript(text)
    except sqlite3.Error as e:
        return con, f"{script_path} raised {type(e).__name__}: {e}"
    return con, None


def main():
    script = SPEC["script"]
    body = "\n".join(l for l in open(script, encoding="utf-8").read().splitlines() if not l.strip().startswith("--")).strip()
    if not body:
        fail(f"{script} is empty")
    twice = SPEC.get("twice", False)
    for i, path in enumerate(SPEC["datasets"], 1):
        a, err = run_all(path, script, twice)
        if err:
            fail(f"dataset {i}: {err}")
        r, err = run_all(path, "tests/ref.sql", False)
        assert err is None, err
        if SPEC.get("integrity", True):
            if a.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                fail(f"dataset {i}: integrity_check failed")
        if SPEC.get("fk_check", True):
            if a.execute("PRAGMA foreign_key_check").fetchall():
                fail(f"dataset {i}: dangling foreign keys after {script}")
        for kind in SPEC.get("struct", []):
            if struct_facts(a, kind) != struct_facts(r, kind):
                fail(f"dataset {i}: schema differs from the expected one ({kind.split(':')[0]}{' of ' + kind.split(':')[1] if ':' in kind else ''})")
        for j, step in enumerate(SPEC.get("post", []), 1):
            outcomes = []
            for con in (a, r):
                try:
                    con.executescript(step["sql"]) if step.get("script") else con.execute(step["sql"]).fetchall()
                    outcomes.append(None)
                except sqlite3.Error as e:
                    outcomes.append(type(e).__name__)
            if (outcomes[0] is None) != (outcomes[1] is None):
                what = "was rejected" if outcomes[0] else "was accepted"
                fail(f"dataset {i}: an operation after the {script} {what} but should not have been")
        for j, chk in enumerate(SPEC["checks"], 1):
            ordered = chk.startswith("ORDERED:")
            sql = chk[len("ORDERED:"):] if ordered else chk
            try:
                got = guarded(a, sql)
            except sqlite3.Error as e:
                fail(f"dataset {i}: check {j} could not run after the script ({type(e).__name__}: {e})")
            want = guarded(r, sql)
            if norm(got, ordered) != norm(want, ordered):
                fail(f"dataset {i}: the data after {script} is not what is expected (check {j}: {len(got)} rows vs {len(want)} expected)")
    print(f"ok: {len(SPEC['datasets'])} datasets")


main()
'''

CHECK_INDEX = _CHECK_COMMON + r'''

def plan(con, sql):
    return [r[3] for r in con.execute("EXPLAIN QUERY PLAN " + sql)]


def main():
    text = open("indexes.sql", encoding="utf-8").read()
    for i, path in enumerate(SPEC["datasets"], 1):
        con = build(path)
        before = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        try:
            con.executescript(text)
        except sqlite3.Error as e:
            fail(f"indexes.sql raised {type(e).__name__}: {e}")
        names = con.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").fetchall()
        new = [n for n in names if n[0] not in before]
        if len(new) > SPEC["max_indexes"]:
            fail(f"{len(new)} indexes created; the budget is {SPEC['max_indexes']}")
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if tables != set(SPEC["tables"]):
            fail("indexes.sql must only create indexes (the set of tables changed)")
        for q in SPEC["queries"]:
            p = plan(con, q["sql"])
            joined = " | ".join(p)
            for t in q.get("no_scan", []):
                for line in p:
                    if re.match(r"SCAN (TABLE )?" + re.escape(t) + r"( |$)", line) and " USING " not in line:
                        fail(f"query {q['name']}: full scan of {t} ({line})")
            if q.get("no_sort") and "TEMP B-TREE" in joined:
                fail(f"query {q['name']}: still sorts with a temporary b-tree ({joined})")
            if q.get("covering") and "COVERING INDEX" not in joined:
                fail(f"query {q['name']}: expected a covering index to be used ({joined})")
            got = guarded(con, q["sql"])
            ref = sqlite3.connect(":memory:")
            ref.executescript(SCHEMA)
            ref.executescript(open(path, encoding="utf-8").read())
            if norm(got, False) != norm(guarded(ref, q["sql"]), False):
                fail(f"query {q['name']}: results changed")
    print(f"ok: {len(SPEC['datasets'])} datasets")


main()
'''


# --------------------------------------------------------------------------------------------------------------
# domains and specs


@dataclass
class Domain:
    key: str
    title: str  # "the ferry company's booking database"
    schema: str
    doc: str  # business rules and conventions, markdown
    gen: Callable[[random.Random, bool], dict[str, list[tuple]]]  # (rng, big) -> {table: rows}, tables in FK order


@dataclass
class Spec:
    slug: str
    d: int
    prompt: str
    ref: str
    cols: list[str]
    ordered: bool = False
    places: int = 4
    buggy: str = ""  # a wrong query shipped as query.sql (a "fix" task)
    show: bool = True  # include the expected sample output in the README
    wrong: tuple = ()  # plausible wrong queries the hidden datasets must reject
    allow_empty: bool = False
    notes: str = ""  # extra README paragraph (rules the prompt does not repeat)
    tags: tuple = ()


_COLS_PHRASES = ["Return the columns {c}, in that order.", "Columns, in order: {c}.", "The result needs exactly these columns, in this order: {c}.",
                 "Output columns: {c} (in this order)."]


def readme(dom: Domain, spec: Spec, sample_out: str | None, script_name: str = "query.sql") -> str:
    parts = [f"# {dom.title}", "", dom.doc.strip(), "", "## Files", "",
             "* `schema.sql`: the tables.",
             "* `seed.sql`: a small SAMPLE dataset so you can try things out. The real database has the same schema but many more rows,",
             "  with the awkward cases a sample does not show (ties, NULLs, missing links, duplicates).",
             f"* `{script_name}`: your answer.",
             "* `tools/runsql.py`: runs a .sql file against schema.sql + seed.sql and prints the rows (`python3 tools/runsql.py`).",
             "",
             "The database is SQLite (3.45 syntax: window functions, CTEs, `RETURNING`, `IIF`, `strftime` are all available)."]
    if script_name == "query.sql":
        parts += ["`query.sql` holds exactly one statement: a `SELECT` (a leading `WITH` is fine). Column names do not matter, column order does."]
    if spec.notes:
        parts += ["", "## Notes", "", spec.notes.strip()]
    if sample_out is not None:
        parts += ["", "## Expected output on the sample data", "", "```", sample_out.rstrip("\n"), "```"]
    return "\n".join(parts) + "\n"


def _stub(spec: Spec) -> str:
    if spec.buggy:
        return spec.buggy.strip("\n") + "\n"
    return "-- write your query here\n"


def query_tasks(dom: Domain, specs: list[Spec], rng: random.Random, n: int, base_tags: tuple = ()) -> list[Task]:
    schema = dom.schema
    cols = table_columns(schema)
    tasks: list[Task] = []
    for si, spec in enumerate(specs[:n]):
        srng = random.Random(rng.random())
        vis = dom.gen(random.Random(srng.random()), False)
        vis_sql = dataset_sql(cols, vis, pretty=True)
        hidden_sets = [dom.gen(random.Random(srng.random()), True) for _ in range(3)]
        hidden_sql = [dataset_sql(cols, h) for h in hidden_sets]
        # guards
        sample_rows = exec_rows(schema, vis_sql, spec.ref)
        results = []
        for k, (h, hs) in enumerate(zip(hidden_sets, hidden_sql)):
            r1 = norm_rows(exec_rows(schema, hs, spec.ref), spec.places, spec.ordered)
            shuffled = dataset_sql(cols, h, shuffle=random.Random(k + 7))
            r2 = norm_rows(exec_rows(schema, shuffled, spec.ref), spec.places, spec.ordered)
            if r1 != r2:
                raise RuntimeError(f"{spec.slug}: reference result depends on row order in hidden dataset {k + 1} (under-determined spec)")
            if not r1 and not spec.allow_empty:
                raise RuntimeError(f"{spec.slug}: reference returns nothing on hidden dataset {k + 1}")
            results.append(r1)
        if len({json.dumps(r, default=str) for r in results}) < 2 and not spec.allow_empty:
            raise RuntimeError(f"{spec.slug}: hidden datasets give identical results")
        if norm_rows(sample_rows, spec.places, spec.ordered) in results:
            raise RuntimeError(f"{spec.slug}: sample result equals a hidden result (hard-codable)")
        if not sample_rows and not spec.allow_empty:
            raise RuntimeError(f"{spec.slug}: reference returns nothing on the sample")
        if spec.buggy:
            bad_rows = exec_rows(schema, vis_sql, spec.buggy)
        for wi, w in enumerate(spec.wrong):
            diffs = 0
            for hs in hidden_sql:
                try:
                    rows = exec_rows(schema, hs, w)
                except sqlite3.Error as e:
                    raise RuntimeError(f"{spec.slug}: wrong#{wi} does not even run: {e}")
                want = exec_rows(schema, hs, spec.ref)
                if norm_rows(rows, spec.places, spec.ordered) != norm_rows(want, spec.places, spec.ordered):
                    diffs += 1
            if diffs == 0:
                raise RuntimeError(f"{spec.slug}: wrong query #{wi} is indistinguishable from the reference on the hidden datasets")
        if spec.buggy:
            diffs = 0
            for hs in hidden_sql:
                if norm_rows(exec_rows(schema, hs, spec.buggy), spec.places, spec.ordered) != norm_rows(exec_rows(schema, hs, spec.ref), spec.places, spec.ordered):
                    diffs += 1
            if diffs == 0:
                raise RuntimeError(f"{spec.slug}: the buggy query is not caught by the hidden datasets")
        # prompt
        prompt = spec.prompt.strip()
        prompt = prompt.replace("@ROWS@", str(len(sample_rows)))
        if spec.buggy:
            prompt = prompt.replace("@ROWS_BAD@", str(len(bad_rows))).replace("@ROWS_GOOD@", str(len(sample_rows)))
        cphrase = srng.choice(_COLS_PHRASES).format(c=", ".join(f"`{c}`" for c in spec.cols))
        prompt = prompt + "\n\n" + cphrase
        sample_out = fmt_table(spec.cols, sample_rows) if spec.show else None
        spec_json = {"ordered": spec.ordered, "places": spec.places, "datasets": [f"tests/data{k + 1}.sql" for k in range(len(hidden_sql))]}
        hidden = {
            "tests/check_query.py": CHECK_QUERY,
            "tests/spec.json": json.dumps(spec_json, indent=1) + "\n",
            "tests/schema.sql": "-- verifier copy of schema.sql\n" + schema,
            "tests/ref.sql": spec.ref.strip() + "\n",
        }
        for k, hs in enumerate(hidden_sql):
            hidden[f"tests/data{k + 1}.sql"] = hs
        start = {
            "README.md": readme(dom, spec, sample_out),
            "schema.sql": schema,
            "seed.sql": vis_sql,
            "query.sql": _stub(spec),
            "tools/runsql.py": RUNSQL,
        }
        kind = "fix" if spec.buggy else "feature"
        t = Task(
            slug=f"{si + 1:02d}-{spec.slug}", prompt=prompt, difficulty=spec.d, start=start, hidden=hidden,
            solution={"query.sql": spec.ref.strip() + "\n"}, verify="python3 tests/check_query.py", kind=kind, lang="sql",
            tags=["sql", *base_tags, *spec.tags], notes={"domain": dom.key, "spec": spec.slug},
        )
        # the reject-wrong guard through the real checker (also proves the checker runs end to end)
        for wi, w in enumerate(spec.wrong):
            tree = merged(start, hidden, {"query.sql": w.strip() + "\n"})
            res = run(tree, t.verify, timeout=60)
            if res.ok:
                raise RuntimeError(f"{spec.slug}: checker accepted wrong query #{wi}")
        tasks.append(t)
    return tasks


# --------------------------------------------------------------------------------------------------------------
# script tasks (migrations, upserts, repairs, triggers): the agent writes a .sql script that is run on each dataset


@dataclass
class ScriptSpec:
    slug: str
    d: int
    prompt: str
    ref: str  # reference script
    checks: list[str]  # SELECTs compared between the agent's database and the reference's ("ORDERED:" prefix for ordered)
    script: str = "migration.sql"
    struct: list[str] = field(default_factory=list)
    post: list[dict] = field(default_factory=list)  # [{"sql": ..., "script": bool}] run after the script on both
    twice: bool = False  # run the agent's script twice (idempotence); the reference runs once
    buggy: str = ""
    places: int = 4
    wrong: tuple = ()
    notes: str = ""
    tags: tuple = ()
    show_sql: str = ""  # a SELECT whose sample output after the reference script goes into the README


def script_tasks(dom: Domain, specs: list[ScriptSpec], rng: random.Random, n: int, base_tags: tuple = ()) -> list[Task]:
    schema = dom.schema
    cols = table_columns(schema)
    tasks: list[Task] = []
    for si, spec in enumerate(specs[:n]):
        srng = random.Random(rng.random())
        vis = dom.gen(random.Random(srng.random()), False)
        vis_sql = dataset_sql(cols, vis, pretty=True)
        hidden_sets = [dom.gen(random.Random(srng.random()), True) for _ in range(3)]
        hidden_sql = [dataset_sql(cols, h) for h in hidden_sets]
        # guard: the reference script runs on every dataset and its checks differ from the pre-state somewhere
        changed = 0
        for hs in hidden_sql:
            con = sqlite3.connect(":memory:")
            con.executescript(schema)
            con.executescript(hs)
            con.executescript(spec.ref)
            for step in spec.post:
                try:
                    con.executescript(step["sql"]) if step.get("script") else con.execute(step["sql"]).fetchall()
                except sqlite3.Error:
                    pass
            for c in spec.checks:
                rows = con.execute(c.removeprefix("ORDERED:")).fetchall()
                if rows:
                    changed += 1
            if con.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise RuntimeError(f"{spec.slug}: reference breaks integrity")
        if not changed:
            raise RuntimeError(f"{spec.slug}: checks return nothing after the reference script")
        prompt = spec.prompt.strip()
        sample_out = None
        if spec.show_sql:
            con = sqlite3.connect(":memory:")
            con.executescript(schema)
            con.executescript(vis_sql)
            con.executescript(spec.ref)
            cur = con.execute(spec.show_sql)
            sample_out = fmt_table([d[0] for d in cur.description], cur.fetchall(), 14)
        spec_json = {"script": spec.script, "datasets": [f"tests/data{k + 1}.sql" for k in range(len(hidden_sql))], "checks": spec.checks,
                     "struct": spec.struct, "post": spec.post, "twice": spec.twice, "places": spec.places}
        hidden = {
            "tests/check_script.py": CHECK_SCRIPT,
            "tests/spec.json": json.dumps(spec_json, indent=1) + "\n",
            "tests/schema.sql": "-- verifier copy of schema.sql\n" + schema,
            "tests/ref.sql": spec.ref.strip() + "\n",
        }
        for k, hs in enumerate(hidden_sql):
            hidden[f"tests/data{k + 1}.sql"] = hs
        stub = (spec.buggy.strip("\n") + "\n") if spec.buggy else f"-- write the {spec.script.removesuffix('.sql')} here\n"
        rd = readme(dom, Spec(slug=spec.slug, d=spec.d, prompt="", ref="", cols=[], notes=spec.notes), None, spec.script)
        if sample_out is not None:
            rd += "\n## Sample: what the data looks like after a correct script\n\n```\n" + sample_out.rstrip("\n") + "\n```\n"
        rd = rd.replace("`tools/runsql.py`: runs a .sql file against schema.sql + seed.sql and prints the rows (`python3 tools/runsql.py`).",
                        "`tools/runsql.py`: runs a .sql file against schema.sql + seed.sql and prints the rows of the last statement that returns any (`python3 tools/runsql.py migration.sql`).")
        start = {"README.md": rd, "schema.sql": schema, "seed.sql": vis_sql, spec.script: stub, "tools/runsql.py": RUNSQL}
        t = Task(
            slug=f"{si + 1:02d}-{spec.slug}", prompt=prompt, difficulty=spec.d, start=start, hidden=hidden,
            solution={spec.script: spec.ref.strip() + "\n"}, verify="python3 tests/check_script.py", kind="fix" if spec.buggy else "feature",
            lang="sql", tags=["sql", *base_tags, *spec.tags], notes={"domain": dom.key, "spec": spec.slug},
        )
        for wi, w in enumerate(spec.wrong):
            tree = merged(start, hidden, {spec.script: w.strip() + "\n"})
            res = run(tree, t.verify, timeout=60)
            if res.ok:
                raise RuntimeError(f"{spec.slug}: checker accepted wrong script #{wi}")
        if spec.buggy:
            res = run(merged(start, hidden), t.verify, timeout=60)
            if res.ok:
                raise RuntimeError(f"{spec.slug}: checker accepts the buggy script")
        tasks.append(t)
    return tasks


# --------------------------------------------------------------------------------------------------------------
# index tasks


@dataclass
class IndexSpec:
    slug: str
    d: int
    prompt: str
    queries: list[dict]  # {"name", "sql", "no_scan": [tables], "no_sort": bool, "covering": bool}
    ref: str  # reference indexes.sql
    max_indexes: int = 3
    wrong: tuple = ()
    notes: str = ""


def index_tasks(dom: Domain, specs: list[IndexSpec], rng: random.Random, n: int) -> list[Task]:
    schema = dom.schema
    cols = table_columns(schema)
    tasks: list[Task] = []
    for si, spec in enumerate(specs[:n]):
        srng = random.Random(rng.random())
        vis = dom.gen(random.Random(srng.random()), False)
        vis_sql = dataset_sql(cols, vis, pretty=True)
        hidden_sql = [dataset_sql(cols, dom.gen(random.Random(srng.random()), True)) for _ in range(2)]
        tables = sorted(cols)
        spec_json = {"datasets": [f"tests/data{k + 1}.sql" for k in range(len(hidden_sql))], "queries": spec.queries,
                     "max_indexes": spec.max_indexes, "tables": tables}
        hidden = {
            "tests/check_index.py": CHECK_INDEX,
            "tests/spec.json": json.dumps(spec_json, indent=1) + "\n",
            "tests/schema.sql": "-- verifier copy of schema.sql\n" + schema,
        }
        for k, hs in enumerate(hidden_sql):
            hidden[f"tests/data{k + 1}.sql"] = hs
        qdoc = "\n\n".join(f"### {q['name']}\n\n```sql\n{q['sql'].strip()}\n```" for q in spec.queries)
        rd = readme(dom, Spec(slug=spec.slug, d=spec.d, prompt="", ref="", cols=[], notes=spec.notes), None, "indexes.sql")
        rd += (f"\n## The workload\n\nThese are the queries the application runs all the time (they must keep returning the same rows):\n\n{qdoc}\n\n"
               f"`indexes.sql` may contain only `CREATE INDEX` statements (at most {spec.max_indexes} new indexes: every index slows writes down). "
               "Check plans with `python3 tools/runsql.py --explain query.sql`-style `EXPLAIN QUERY PLAN` statements.\n")
        start = {"README.md": rd, "schema.sql": schema, "seed.sql": vis_sql, "indexes.sql": "-- CREATE INDEX statements go here\n", "tools/runsql.py": RUNSQL}
        t = Task(
            slug=f"{si + 1:02d}-{spec.slug}", prompt=spec.prompt.strip(), difficulty=spec.d, start=start, hidden=hidden,
            solution={"indexes.sql": spec.ref.strip() + "\n"}, verify="python3 tests/check_index.py", kind="feature", lang="sql",
            tags=["sql", "index", "query-plan"], notes={"domain": dom.key, "spec": spec.slug},
        )
        res = run(merged(start, hidden), t.verify, timeout=60)
        if res.ok:
            raise RuntimeError(f"{spec.slug}: no indexes already passes")
        for wi, w in enumerate(spec.wrong):
            res = run(merged(start, hidden, {"indexes.sql": w.strip() + "\n"}), t.verify, timeout=60)
            if res.ok:
                raise RuntimeError(f"{spec.slug}: checker accepted wrong indexes #{wi}")
        tasks.append(t)
    return tasks
