"""Tiny invented databases (six skins over one parent/child/event shape) and a library of reading-trap queries.

Every answer is computed by executing the SQL with python's sqlite3 on the exact data that is written into the repository.
"""
from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass


@dataclass
class Skin:
    key: str
    title: str
    P: str            # parent table
    P_grp: str        # nullable text column of the parent
    C: str            # child table
    C_kind: str
    C_size: str       # nullable integer
    E: str            # event table
    E_amount: str
    E_flag: str       # nullable 0/1
    parent_names: list
    groups: list
    kinds: list
    labels: list
    notes: list
    day0: str


SKINS = [
    Skin("harbor", "harbour stays", "owner", "country", "vessel", "kind", "length_m", "stay", "fee", "paid",
         ["Brandt Marine", "Seaward Co", "Linnea Ahlberg", "Tidewater Ltd", "K. Okonkwo", "Mistral Charters", "Ostrava Yachts", "Pilar Soto", "Gannet Cooperative", "H. Varga", "Northline"],
         ["NO", "DK", "GB", "PT", "NL", "SE", "IE"], ["ketch", "sloop", "trawler", "ferry", "catamaran", "tug"],
         ["Alba", "Brisa", "Corvo", "Dagny", "Estrela", "Fram", "Gull", "Haldis", "Isla", "Juno", "Kestrel", "Luna", "Marisol", "Nixie", "Ondine", "Petrel"],
         ["fuel", "water", "late arrival", "crane", "pump-out", "storm hold", "none"], "2031-03-01"),
    Skin("seeds", "seed library", "donor", "region", "packet", "species", "qty", "loan", "days_out", "returned",
         ["Ashgrove Allotments", "M. Pereira", "Hollin Farm", "Wren Street Garden", "Dunmore School", "Yusuf Demir", "Calder Valley Co-op", "I. Novak", "Rookery Lane", "Sunnyside Beds"],
         ["north", "south", "east", "west", "coast"], ["bean", "kale", "leek", "pea", "beet", "squash", "chard", "dill"],
         ["Blue Lake", "Cavolo", "Musselburgh", "Kelvedon", "Detroit", "Uchiki", "Fordhook", "Mammoth", "Bouquet", "Early Wonder", "Giant Red", "Lincoln", "Rainbow", "Tendersweet"],
         ["swap", "annual", "late", "damaged", "none", "demo day"], "2031-01-05"),
    Skin("observatory", "observing log", "observer", "institute", "session", "scope", "hours", "shot", "frames", "kept",
         ["R. Hallam", "Ines Carvalho", "T. Obuya", "Lindgren", "Fatima Rahal", "P. Dubois", "J. Whitcombe", "Mara Stoica", "K. Aoki"],
         ["Aldgate", "Bexley", "Calder", "Dunstan", "Eskdale"], ["refractor", "newtonian", "schmidt", "dobsonian"],
         ["Night A", "Night B", "Night C", "Night D", "Night E", "Night F", "Night G", "Night H", "Night I", "Night J", "Night K", "Night L", "Night M", "Night N"],
         ["clouds", "dew", "tracking", "good seeing", "none", "satellite"], "2031-09-14"),
    Skin("bells", "bell deliveries", "foundry", "town", "bell", "tone", "kg", "delivery", "fee", "fragile",
         ["Hallward & Sons", "Petit Fonderie", "St Clement Works", "Brandling Foundry", "Aberlour Bells", "O. Maier"],
         ["Loughton", "Rennes", "Aachen", "Whitby", "Carrick"], ["C", "D", "E", "F", "G", "A"],
         ["Gabriel", "Michael", "Ursula", "Tobias", "Mary", "Agnes", "Anselm", "Bede", "Clare", "Dunstan", "Edith", "Felix", "Gertrude", "Hilda"],
         ["crated", "crane", "rail", "escort", "none", "rush"], "2031-05-02"),
    Skin("hives", "hive inspections", "apiary", "valley", "hive", "breed", "frames", "inspection", "honey_g", "swarm_risk",
         ["Lower Mead", "Hawthorn Rise", "Coombe End", "Pennywell", "Ashby Fold", "High Brae", "Mill Orchard"],
         ["Dale", "Fen", "Coombe", "Moor"], ["buckfast", "carniolan", "native", "italian", "caucasian"],
         ["H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10", "H11", "H12", "H13", "H14", "H15", "H16", "H17", "H18"],
         ["queen seen", "queenless", "chalkbrood", "robbing", "none", "new super"], "2031-04-10"),
    Skin("tram", "tram shifts", "depot", "line", "tram", "model", "seats", "shift", "km", "late",
         ["Northgate", "Millbrook", "Harbour Road", "Eastfield", "Quarry Lane", "Old Mill"],
         ["A", "B", "C", "D"], ["T-100", "T-200", "T-300", "Combino", "Flexity"],
         ["Tram 11", "Tram 12", "Tram 14", "Tram 21", "Tram 22", "Tram 31", "Tram 32", "Tram 33", "Tram 41", "Tram 42", "Tram 43", "Tram 51", "Tram 52", "Tram 61"],
         ["delay", "fault", "diversion", "ok", "none", "relief"], "2031-02-03"),
]


def _sql_str(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def schema(sk: Skin) -> str:
    return (
        f"CREATE TABLE {sk.P} (\n  id INTEGER PRIMARY KEY,\n  name TEXT NOT NULL,\n  {sk.P_grp} TEXT\n);\n\n"
        f"CREATE TABLE {sk.C} (\n  id INTEGER PRIMARY KEY,\n  parent_id INTEGER REFERENCES {sk.P}(id),\n  label TEXT NOT NULL,\n  {sk.C_kind} TEXT NOT NULL,\n  {sk.C_size} INTEGER\n);\n\n"
        f"CREATE TABLE {sk.E} (\n  id INTEGER PRIMARY KEY,\n  child_id INTEGER NOT NULL REFERENCES {sk.C}(id),\n  day TEXT NOT NULL,\n  {sk.E_amount} INTEGER NOT NULL,\n  {sk.E_flag} INTEGER,\n  note TEXT\n);\n"
    )


def make_data(rng: random.Random, sk: Skin, n_parent: int, n_child: int, n_event: int) -> dict:
    parents = []
    for i, nm in enumerate(rng.sample(sk.parent_names, min(n_parent, len(sk.parent_names))), 1):
        parents.append((i, nm, rng.choice(sk.groups + [None, None])))
    labels = list(sk.labels)
    rng.shuffle(labels)
    children = []
    for i in range(1, n_child + 1):
        pid = rng.choice([p[0] for p in parents] + [None]) if i > 1 else None
        if i == 2:
            pid = parents[0][0]
        label = labels[(i - 1) % len(labels)] + ("" if i <= len(labels) else f" {i}")
        children.append((i, pid, label, rng.choice(sk.kinds), rng.choice([rng.randint(3, 40), rng.randint(3, 40), rng.randint(3, 40), None])))
    # a child without parent and a parent without children must exist for the traps to bite
    if not any(c[1] is None for c in children):
        c = children[-1]
        children[-1] = (c[0], None, c[2], c[3], c[4])
    used = {c[1] for c in children if c[1] is not None}
    if all(p[0] in used for p in parents):
        # move the last parent's children to the first parent
        last = parents[-1][0]
        children = [(c[0], parents[0][0] if c[1] == last else c[1], c[2], c[3], c[4]) for c in children]
    events = []
    import datetime as dt
    d0 = dt.date.fromisoformat(sk.day0)
    for i in range(1, n_event + 1):
        cid = rng.choice([c[0] for c in children])
        day = (d0 + dt.timedelta(days=rng.randint(0, 40))).isoformat()
        events.append((i, cid, day, rng.randint(2, 90), rng.choice([0, 1, 1, None]), rng.choice(sk.notes)))
    return {"parents": parents, "children": children, "events": events}


def seed_sql(sk: Skin, data: dict) -> str:
    out = []
    for tbl, cols, rows in ((sk.P, f"id, name, {sk.P_grp}", data["parents"]),
                            (sk.C, f"id, parent_id, label, {sk.C_kind}, {sk.C_size}", data["children"]),
                            (sk.E, f"id, child_id, day, {sk.E_amount}, {sk.E_flag}, note", data["events"])):
        out.append(f"INSERT INTO {tbl} ({cols}) VALUES")
        out.append(",\n".join("  (" + ", ".join(_sql_str(v) for v in r) + ")" for r in rows) + ";")
        out.append("")
    return "\n".join(out)


def connect(sk: Skin, data: dict) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.executescript(schema(sk))
    con.executescript(seed_sql(sk, data))
    return con


def run_rows(con: sqlite3.Connection, sql: str) -> list:
    cur = con.execute(sql)
    return ["|".join("NULL" if v is None else str(v) for v in row) for row in cur.fetchall()]


# --------------------------------------------------------------------------------------------------------------------
# query templates. Each returns (function_name, sql, difficulty, topic, hypothetical variant sql or None)
def templates(sk: Skin, rng: random.Random) -> list:
    P, C, E = sk.P, sk.C, sk.E
    g, kind, size, amt, flag = sk.P_grp, sk.C_kind, sk.C_size, sk.E_amount, sk.E_flag
    k = rng.randint(2, 4)
    lim = rng.randint(2, 4)
    a, b = sorted(rng.sample([8, 10, 12, 15, 18, 20, 25, 30], 2))
    kindv = rng.choice(sk.kinds)
    letter = rng.choice([x[0] for x in sk.labels]).lower()
    ts = []
    ts.append((f"top_{P}s_by_{amt}", f"""SELECT p.name, SUM(e.{amt}) AS total
FROM {P} p
JOIN {C} c ON c.parent_id = p.id
JOIN {E} e ON e.child_id = c.id
GROUP BY p.id
ORDER BY total DESC, p.name
LIMIT {lim}""", 2, "join+group", None))
    ts.append((f"{kind}_counts", f"""SELECT {kind}, COUNT(*) AS n
FROM {C}
GROUP BY {kind}
HAVING COUNT(*) >= 2
ORDER BY n DESC, {kind}""", 1, "having", None))
    ts.append((f"{C}s_per_{P}", f"""SELECT p.name, COUNT(c.id) AS n
FROM {P} p
LEFT JOIN {C} c ON c.parent_id = p.id
GROUP BY p.id
ORDER BY n, p.name""", 2, "left-join-count", f"""SELECT p.name, COUNT(*) AS n
FROM {P} p
LEFT JOIN {C} c ON c.parent_id = p.id
GROUP BY p.id
ORDER BY n, p.name"""))
    ts.append((f"{P}s_without_{C}s", f"""SELECT p.name
FROM {P} p
WHERE p.id NOT IN (SELECT parent_id FROM {C})
ORDER BY p.name""", 3, "not-in-null", f"""SELECT p.name
FROM {P} p
WHERE NOT EXISTS (SELECT 1 FROM {C} c WHERE c.parent_id = p.id)
ORDER BY p.name"""))
    ts.append((f"average_{size}_by_{kind}", f"""SELECT {kind}, printf('%.1f', AVG({size})) AS avg_size, COUNT(*) AS n
FROM {C}
GROUP BY {kind}
ORDER BY {kind}""", 3, "avg-null", f"""SELECT {kind}, printf('%.1f', SUM({size}) * 1.0 / COUNT(*)) AS avg_size, COUNT(*) AS n
FROM {C}
GROUP BY {kind}
ORDER BY {kind}"""))
    ts.append((f"mean_{amt}_per_{P}", f"""SELECT p.name, SUM(e.{amt}) / COUNT(*) AS mean
FROM {P} p
JOIN {C} c ON c.parent_id = p.id
JOIN {E} e ON e.child_id = c.id
GROUP BY p.id
ORDER BY mean DESC, p.name""", 3, "integer-division", None))
    ts.append((f"top_{amt}_ranked", f"""SELECT label, {amt}, rk FROM (
  SELECT c.label AS label, e.{amt} AS {amt}, RANK() OVER (ORDER BY e.{amt} DESC) AS rk, e.id AS eid
  FROM {E} e JOIN {C} c ON c.id = e.child_id
)
WHERE rk <= {lim + 1}
ORDER BY rk, eid""", 4, "window-rank", None))
    ts.append((f"running_{amt}", f"""SELECT day, {amt}, running FROM (
  SELECT e.day AS day, e.{amt} AS {amt}, e.id AS id,
         SUM(e.{amt}) OVER (ORDER BY e.day, e.id) AS running
  FROM {E} e
)
ORDER BY day DESC, id DESC
LIMIT {lim}""", 4, "window-running", None))
    ts.append((f"{size}_buckets", f"""SELECT CASE WHEN {size} < {a} THEN 'small' WHEN {size} < {b} THEN 'medium' ELSE 'large' END AS bucket, COUNT(*) AS n
FROM {C}
GROUP BY bucket
ORDER BY bucket""", 3, "case-null", None))
    ts.append((f"{C}s_starting_{letter}", f"""SELECT label
FROM {C}
WHERE label LIKE '{letter}%'
ORDER BY label""", 2, "like-case", f"""SELECT label
FROM {C}
WHERE label GLOB '{letter}*'
ORDER BY label"""))
    ts.append((f"{C}_activity_span", f"""SELECT c.label, CAST(julianday(MAX(e.day)) - julianday(MIN(e.day)) AS INTEGER) AS span
FROM {C} c JOIN {E} e ON e.child_id = c.id
GROUP BY c.id
HAVING span >= {k * 4}
ORDER BY span DESC, c.label""", 4, "date-diff", None))
    ts.append((f"above_{C}_average", f"""SELECT e.id, e.{amt}
FROM {E} e
WHERE e.{amt} > (SELECT AVG(e2.{amt}) FROM {E} e2 WHERE e2.child_id = e.child_id)
ORDER BY e.id""", 4, "correlated", None))
    ts.append((f"distinct_labels", f"""SELECT COUNT(*) FROM (
  SELECT {kind} AS v FROM {C}
  UNION
  SELECT {g} FROM {P}
)""", 3, "union", f"""SELECT COUNT(*) FROM (
  SELECT {kind} AS v FROM {C}
  UNION ALL
  SELECT {g} FROM {P}
)"""))
    ts.append((f"{P}s_with_flagged_{E}s", f"""SELECT COUNT(DISTINCT p.id)
FROM {P} p
JOIN {C} c ON c.parent_id = p.id
JOIN {E} e ON e.child_id = c.id
WHERE e.{flag} = 1""", 3, "distinct-join", f"""SELECT COUNT(*)
FROM {P} p
JOIN {C} c ON c.parent_id = p.id
JOIN {E} e ON e.child_id = c.id
WHERE e.{flag} = 1"""))
    ts.append((f"unflagged_{E}s", f"""SELECT COUNT(*) FROM {E} WHERE {flag} != 1""", 3, "null-compare", f"""SELECT COUNT(*) FROM {E} WHERE {flag} IS NOT 1"""))
    ts.append((f"{C}_pairs", f"""SELECT a.label, b.label
FROM {C} a
JOIN {C} b ON a.parent_id = b.parent_id AND a.id < b.id
ORDER BY a.id, b.id""", 4, "self-join", None))
    ts.append((f"smallest_{C}s", f"""SELECT label, {size}
FROM {C}
ORDER BY {size}, id
LIMIT {lim}""", 3, "order-null", f"""SELECT label, {size}
FROM {C}
WHERE {size} IS NOT NULL
ORDER BY {size}, id
LIMIT {lim}"""))
    ts.append((f"{kind}_{kindv.replace('-', '_')}_share", f"""SELECT COUNT(*) AS n, SUM(CASE WHEN {kind} = '{kindv}' THEN 1 ELSE 0 END) AS hits, COUNT({size}) AS sized
FROM {C}""", 2, "count-col", None))
    ts.append((f"{P}_{g}_totals", f"""WITH per_parent AS (
  SELECT p.id AS pid, p.{g} AS grp, COUNT(DISTINCT c.id) AS kids, COALESCE(SUM(e.{amt}), 0) AS total
  FROM {P} p
  LEFT JOIN {C} c ON c.parent_id = p.id
  LEFT JOIN {E} e ON e.child_id = c.id
  GROUP BY p.id
)
SELECT COALESCE(grp, '(none)') AS grp, SUM(kids) AS kids, SUM(total) AS total
FROM per_parent
GROUP BY grp
ORDER BY total DESC, grp""", 5, "cte-two-level", None))
    return ts


VARIANT_DESC = {
    "left-join-count": "changed `COUNT(c.id)` into `COUNT(*)`",
    "not-in-null": "rewrote the `NOT IN (subquery)` condition as a correlated `NOT EXISTS`",
    "avg-null": "replaced `AVG(...)` by `SUM(...) * 1.0 / COUNT(*)`",
    "like-case": "replaced `LIKE 'x%'` by `GLOB 'x*'`",
    "union": "used `UNION ALL` instead of `UNION`",
    "distinct-join": "dropped the `DISTINCT` and counted joined rows instead",
    "null-compare": "wrote the condition as `IS NOT 1` instead of `!= 1`",
    "order-null": "added a `WHERE ... IS NOT NULL` filter on the sort column",
}
