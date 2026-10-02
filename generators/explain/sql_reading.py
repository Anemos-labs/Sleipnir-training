"""Predict the rows a SQL query returns over the data embedded in a small python repository (NULL traps, joins, windows)."""
from __future__ import annotations

from fx import family

from . import _check as C
from . import _fam as F
from . import _sqlgen as S
from . import _voice as V
from fx import dd


def _j(*parts) -> str:
    return " ".join(x for x in parts if x)


def _py_fn(name: str, sql: str, doc: str) -> str:
    body = "\n".join("    " + ln if ln else "" for ln in sql.split("\n"))
    return f'def {name}(conn):\n    """{doc}"""\n    return conn.execute(\n        """\n{body}\n        """\n    ).fetchall()\n'


@family("explain-sql-rows", category="explain", lang="python", kind="greenfield", n=14,
        summary="predict the rows of a SQL query over the seed data in a python repo (NULL semantics, joins, windows, ties), or of a hypothetical rewrite")
def sql_rows(rng, n):
    tiers = F.tier_plan(rng, n, (12, 26, 30, 20, 12))
    sk_order = list(range(len(S.SKINS)))
    for i in range(n):
        tier = tiers[i]
        sk = S.SKINS[(sk_order[i % len(sk_order)] + i // len(sk_order)) % len(S.SKINS)]
        sizes = {1: (4, 7, 12), 2: (5, 9, 18), 3: (6, 12, 26), 4: (8, 16, 40), 5: (9, 20, 70)}[tier]
        data = S.make_data(rng, sk, *sizes)
        con = S.connect(sk, data)
        tpls = S.templates(sk, rng)
        pool = [t for t in tpls if abs(t[2] - tier) <= 1]
        hypo_pool = [t for t in pool if t[4] is not None and t[3] in S.VARIANT_DESC]
        hypo = bool(hypo_pool) and tier >= 3 and rng.random() < 0.4
        target = rng.choice(hypo_pool if hypo else pool)
        name, sql, tdiff, topic, vsql = target
        rows_main = S.run_rows(con, sql)
        decoys = rng.sample([t for t in tpls if t[0] != name], 4)
        # the module holds the target and four other queries
        funcs = [(name, sql, f"{name.replace('_', ' ').capitalize()}.")]
        for dn, dsql, _, dtopic, _ in decoys:
            funcs.append((dn, dsql, f"{dn.replace('_', ' ').capitalize()}."))
        rng.shuffle(funcs)
        queries = f'"""Reporting queries for the {sk.title} database."""\n\n\n' + "\n\n".join(_py_fn(*f) for f in funcs)
        # two visible tests on decoy queries (their expected rows come from the same engine)
        tests = ['"""Checks for two of the reporting queries."""', "import unittest", "", "from app import db, queries", "", "",
                 "class QueryTests(unittest.TestCase):", "    def setUp(self):", "        self.conn = db.connect()", ""]
        for dn, dsql, _, _, _ in decoys[:2]:
            rows = con.execute(dsql).fetchall()
            tests.append(f"    def test_{dn}(self):")
            tests.append(f"        self.assertEqual(queries.{dn}(self.conn), {rows!r})")
            tests.append("")
        files = {
            "app/__init__.py": "",
            "app/schema.sql": S.schema(sk),
            "app/seed.sql": S.seed_sql(sk, data),
            "app/db.py": dd('''
                """Opens an in-memory SQLite database with the schema and the seed rows."""
                import sqlite3
                from pathlib import Path

                HERE = Path(__file__).parent


                def connect():
                    conn = sqlite3.connect(":memory:")
                    conn.executescript((HERE / "schema.sql").read_text())
                    conn.executescript((HERE / "seed.sql").read_text())
                    return conn
            '''),
            "app/queries.py": queries,
            "tests/test_queries.py": "\n".join(tests).rstrip("\n") + "\n",
            "README.md": f"# {sk.title.capitalize()} reports\n\nSQLite-backed reporting queries for the {sk.title} data set.\n\n- `app/schema.sql`, `app/seed.sql`: the data\n- `app/queries.py`: the report queries\n- `tests/`: unit tests\n",
        }
        if hypo:
            rows = S.run_rows(con, vsql)
            vdesc = S.VARIANT_DESC[topic]
            ask = rng.choice([
                f"In `app/queries.py`, `{name}` runs a query over the seeded data. Suppose someone {vdesc}. What would the rewritten query return?",
                f"Look at `{name}` in `app/queries.py`. If the query were changed so that it {vdesc}, which rows would it produce on the seed data?",
            ])
            d = F.clamp(tier)
        else:
            rows = rows_main
            ask = rng.choice([
                f"What does `queries.{name}(conn)` return on the seed data? Work it out from `app/queries.py` and `app/seed.sql`.",
                f"Predict the exact rows returned by `{name}` in `app/queries.py` when run against the data in `app/seed.sql`.",
                f"I have to explain the output of the `{name}` report. What rows does it give back for the seeded database?",
            ])
            d = F.clamp(tier)
        ordered = "ORDER BY" in (vsql if hypo else sql)
        spec = C.json_spec({"rows": C.jf("list" if ordered else "set", rows, norm="exact")})
        fmt = ("Write `answer.json` as {\"rows\": [\"col1|col2\", ...]}: one string per returned row, in the order returned, columns joined with `|`, "
               "SQL NULL written as `NULL`, numbers as SQLite prints them. If no rows come back use an empty list.")
        why = rng.choice(["", "", "The numbers on the dashboard don't match what I expect.", "Writing the expected values for a regression test."])
        prompt = V.frame(rng, ask, fmt, why, tag=sk.key[:3].upper())
        yield C.file_task(slug=f"{i + 1:02d}-{sk.key}-{topic}{'-hypo' if hypo else ''}", prompt=prompt, difficulty=d, start=files, spec=spec, answer={"rows": rows},
                          lang="python", tags=["sql", topic, "hypothetical" if hypo else "direct", "answer-json"],
                          notes={"skin": sk.key, "topic": topic, "tier": tier, "rows": len(rows), "hypothetical": hypo})
