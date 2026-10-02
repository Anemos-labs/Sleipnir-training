"""Schema evolution by SQL migration files: what does the table look like after the runner has applied them (order traps, manifests, skips)?"""
from __future__ import annotations

import json

import fx
from fx import dd, family

from . import _check as C
from . import _fam as F
from . import _sqlgen as S
from . import _voice as V

ADD_COLS = {
    "harbor": [("notes", "TEXT"), ("draft_m", "REAL"), ("flag_state", "TEXT DEFAULT 'XX'"), ("insured", "INTEGER DEFAULT 0"), ("crew", "INTEGER"), ("callsign", "TEXT"), ("berth", "TEXT")],
    "seeds": [("origin", "TEXT"), ("packed_on", "TEXT"), ("organic", "INTEGER DEFAULT 0"), ("lot_code", "TEXT"), ("germ_pct", "INTEGER"), ("bin", "TEXT"), ("tag", "TEXT")],
    "observatory": [("moon_pct", "INTEGER"), ("filterset", "TEXT"), ("remote", "INTEGER DEFAULT 0"), ("log_note", "TEXT"), ("temp_c", "REAL"), ("operator", "TEXT"), ("dome", "TEXT")],
    "bells": [("alloy", "TEXT"), ("cast_on", "TEXT"), ("tuned", "INTEGER DEFAULT 0"), ("strike_note", "TEXT"), ("yoke", "TEXT"), ("mould_no", "INTEGER"), ("pit", "TEXT")],
    "hives": [("queen_year", "INTEGER"), ("super_count", "INTEGER DEFAULT 1"), ("temper", "TEXT"), ("site", "TEXT"), ("treated", "INTEGER DEFAULT 0"), ("mark", "TEXT"), ("moved_on", "TEXT")],
    "tram": [("depot_bay", "TEXT"), ("serviced_on", "TEXT"), ("accessible", "INTEGER DEFAULT 1"), ("fleet_no", "INTEGER"), ("livery", "TEXT"), ("notes", "TEXT"), ("track", "TEXT")],
}
RENAMES = {"label": ["title", "name_tag", "display_name"], "parent_id": ["owner_ref", "group_id", "parent_ref"]}
SLUGS = ["add", "extend", "backfill", "tidy", "rename", "widen", "drop", "reshape"]


def _runner(order: str, skip: list, manifest: list) -> str:
    head = '"""Applies the SQL files in migrations/ to a SQLite database, oldest first."""\nimport re\nimport sqlite3\nimport sys\nfrom pathlib import Path\n\nDIR = Path(__file__).parent / "migrations"\nAPPLIED = []\n'
    if order == "lex":
        body = dd('''

            def files():
                return sorted(p for p in DIR.iterdir() if p.suffix == ".sql")
        ''')
    elif order == "numeric":
        body = dd('''

            def _num(path):
                return int(re.match(r"(\\d+)", path.name).group(1))


            def files():
                return sorted((p for p in DIR.iterdir() if p.suffix == ".sql"), key=_num)
        ''')
    elif order == "skip":
        body = "\nSKIP = {" + ", ".join(f'"{x}"' for x in skip) + "}\n" + dd('''

            def _num(path):
                return int(re.match(r"(\\d+)", path.name).group(1))


            def files():
                found = [p for p in DIR.iterdir() if p.suffix == ".sql" and p.name not in SKIP]
                return sorted(found, key=_num)
        ''')
    else:  # manifest
        body = dd('''

            def files():
                names = [ln.strip() for ln in (DIR / "ORDER").read_text().splitlines() if ln.strip() and not ln.startswith("#")]
                return [DIR / name for name in names]
        ''')
    tail = dd('''

        def apply(conn):
            for path in files():
                conn.executescript(path.read_text())
                APPLIED.append(path.name)


        def connect(url=":memory:"):
            conn = sqlite3.connect(url)
            apply(conn)
            return conn


        if __name__ == "__main__":
            connect(sys.argv[1] if len(sys.argv) > 1 else ":memory:")
            print("applied", len(APPLIED), "migrations")
    ''')
    import re as _re
    text = head + body + tail
    return _re.sub(r"\n+(def |if __name__)", r"\n\n\n\1", text)


@family("explain-migration-schema", category="explain", lang="python", kind="greenfield", n=12,
        summary="after the migration runner has applied its files (lexical vs numeric order, a manifest, a skip list), what columns does a table have, or which files ran in which order")
def migration_schema(rng, n):
    tiers = F.tier_plan(rng, n, (8, 24, 32, 24, 12))
    for i in range(n):
        tier = tiers[i]
        sk = S.SKINS[(i + rng.randrange(len(S.SKINS))) % len(S.SKINS)]
        order = {1: "numeric", 2: "numeric", 3: rng.choice(["skip", "manifest", "numeric"]), 4: rng.choice(["lex", "skip", "manifest"]),
                 5: rng.choice(["lex", "manifest", "skip"])}[tier]
        nops = {1: 3, 2: 4, 3: 6, 4: 9, 5: 12}[tier]
        if order == "lex":
            nops = rng.choice([10, 11, 12, 13]) if tier == 4 else rng.choice([13, 14, 15])
        adds = list(ADD_COLS[sk.key])
        rng.shuffle(adds)
        ops = []
        used_rename = set()
        for k in range(nops):
            r = rng.random() if order != "lex" else rng.choice([0.1, 0.1, 0.2, 0.3, 0.9, 0.95])
            if r < 0.55 and adds:
                col, typ = adds.pop()
                ops.append(("add", f"ALTER TABLE {sk.C} ADD COLUMN {col} {typ};"))
            elif r < 0.75 and "label" not in used_rename:
                used_rename.add("label")
                new = rng.choice(RENAMES["label"])
                ops.append(("rename", f"ALTER TABLE {sk.C} RENAME COLUMN label TO {new};"))
            elif r < 0.88 and "size" not in used_rename:
                used_rename.add("size")
                ops.append(("drop", f"ALTER TABLE {sk.C} DROP COLUMN {sk.C_size};"))
            elif adds:
                col, typ = adds.pop()
                ops.append(("add", f"ALTER TABLE {sk.C} ADD COLUMN {col} {typ};"))
            else:
                ops.append(("index", f"CREATE INDEX idx_{sk.C}_{kk(k)} ON {sk.C}({sk.C_kind});"))
        # file names
        files = {}
        numbered = [("base", S.schema(sk))] + [(op, sql + "\n") for op, sql in ops]
        names = []
        width = 4 if order in ("numeric", "skip") and rng.random() < 0.5 else 0
        for idx, (op, sql) in enumerate(numbered, 0 if order == "lex" else 1):
            slug = "create_tables" if op == "base" else f"{op}_{kk(idx)}"
            if order == "manifest":
                nm = f"2031_{3 + idx // 9:02d}_{(idx * 3) % 28 + 1:02d}_{slug}.sql"
            elif width:
                nm = f"{idx:04d}_{slug}.sql"
            else:
                nm = f"{idx}_{slug}.sql"
            names.append(nm)
            files[f"migrations/{nm}"] = sql
        skip = []
        if order == "skip":
            skip = rng.sample(names[1:], min(2, len(names) - 1))
        manifest = []
        if order == "manifest":
            manifest = [names[0]] + rng.sample(names[1:], len(names) - 1)
            # leave one file out of the manifest (never run)
            out = rng.choice(manifest[1:])
            manifest.remove(out)
            files["migrations/ORDER"] = "# applied top to bottom; keep in sync when adding files\n" + "\n".join(manifest) + "\n"
        files["migrate.py"] = _runner(order, skip, manifest)
        files["tests/test_migrate.py"] = dd(f'''
            import unittest

            import migrate


            class MigrateTests(unittest.TestCase):
                def test_creates_tables(self):
                    conn = migrate.connect()
                    names = {{r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}}
                    self.assertTrue({{"{sk.P}", "{sk.C}", "{sk.E}"}} <= names)

                def test_first_file_is_the_base_schema(self):
                    migrate.connect()
                    self.assertTrue(migrate.APPLIED[0].endswith("create_tables.sql"))
        ''')
        files["README.md"] = f"# {sk.title.capitalize()} database\n\nSchema changes live in `migrations/` as plain SQL files; `python3 migrate.py [db-file]` applies them.\n"
        # ground truth: run the real runner
        probe = dd(f'''
            import json
            import migrate

            conn = migrate.connect()
            cols = [r[1] for r in conn.execute("PRAGMA table_info({sk.C})")]
            print(json.dumps({{"columns": cols, "applied": migrate.APPLIED}}))
        ''')
        res = fx.run({**files, "_probe.py": probe}, "python3 _probe.py", timeout=30)
        assert res.ok, res.out
        got = json.loads(res.out.strip().splitlines()[-1])
        mode = "columns" if tier <= 2 or rng.random() < 0.65 else "order"
        if mode == "columns":
            ans = got["columns"]
            ask = rng.choice([
                f"After `migrate.py` has applied the migrations, which columns does the `{sk.C}` table have, in table order (the order `PRAGMA table_info` lists them)?",
                f"What does the `{sk.C}` table look like once all migrations have run? I need the column names in order.",
                f"List the columns of `{sk.C}` after a fresh `python3 migrate.py`, left to right.",
            ])
            spec = C.json_spec({"columns": C.jf("list", ans, norm="exact")})
            fmt = "Write `answer.json` as {\"columns\": [\"name\", ...]}."
            obj = {"columns": ans}
            d = F.clamp(tier)
        else:
            ans = got["applied"]
            ask = rng.choice([
                "In which order does `migrate.py` actually apply the migration files? Give the file names, first to last, leaving out any file that is never applied.",
                "Which migration files get applied, and in what order? Follow what the runner really does, not what the file names suggest.",
            ])
            spec = C.json_spec({"applied": C.jf("list", ans, norm="exact")})
            fmt = "Write `answer.json` as {\"applied\": [\"file name\", ...]} using bare file names such as `0003_add_x.sql`."
            obj = {"applied": ans}
            d = F.clamp(tier)
        why = rng.choice(["", "", "Staging and production disagree about the column order.", "A new colleague needs to know what the schema will look like."])
        prompt = V.frame(rng, ask, fmt, why, tag=sk.key[:3].upper())
        yield C.file_task(slug=f"{i + 1:02d}-{sk.key}-{order}-{mode}", prompt=prompt, difficulty=d, start=files, spec=spec, answer=obj, lang="python",
                          tags=["sql", "migrations", order, mode, "answer-json"], notes={"skin": sk.key, "order": order, "migrations": len(numbered), "tier": tier})


def kk(i) -> str:
    return ["sync", "audit", "cache", "stats", "rollup", "trace", "hist", "flag", "usage", "note", "meta", "stamp", "scan", "ref"][int(i) % 14]
