"""Expert-level SQL tasks (difficulty 5) on six of the invented databases: sequential state machines in recursive CTEs, interval unions, nested caps, day-wise proration, hysteresis episodes, redundancy through group nesting and cousin relations."""
from fx import family
from generators.data import _sqlkit as K
from generators.data.sql_accessgraph import DOMAIN as ACCESS
from generators.data.sql_busfares import DOMAIN as BUS, JOURNEYS
from generators.data.sql_chessclub import DOMAIN as CHESS
from generators.data.sql_clinic import DOMAIN as CLINIC
from generators.data.sql_greenhouse import DOMAIN as GREEN
from generators.data.sql_kinship import DOMAIN as KIN
from generators.data.sql_meters import DOMAIN as METERS, INTERVALS


def E(slug, prompt, sql, cols, ordered=True, **kw):
    return K.Spec(slug, 5, prompt, sql.strip(), cols, ordered=ordered, **kw)


def wrap(dom, key, plant):
    """The same schema and rules as `dom`, with extra planted rows so that the hard cases occur in every dataset."""
    def gen(rng, big):
        data = dom.gen(rng, big)
        return plant(data, rng, big)
    return K.Domain(key, dom.title, dom.schema, dom.doc, gen)


# ---------------------------------------------------------------- meters

def plant_meters(data, rng, big):
    """A second fault two readings after the first one, on the same electric meter, so that 'the last three valid intervals' differs from 'the last three rows'."""
    readings = [list(r) for r in data["readings"]]
    elec = [m for m in data["meters"] if m[2] == "electric"]
    mine = sorted((r for r in readings if r[1] == elec[0][0]), key=lambda r: (r[2], r[0]))
    if len(mine) > 8 and mine[6][3] >= 1000:
        mine[7][3] = mine[6][3] - 300
    data["readings"] = [tuple(r) for r in readings]
    return data


METERS2 = wrap(METERS, "meters-experts", plant_meters)

PRORATED = f"""{INTERVALS}
, d(meter_id, kind, per_day, day, last) AS (
  SELECT meter_id, kind, used * 1.0 / (julianday(read_on) - julianday(prev_on)), prev_on, read_on FROM iv WHERE NOT fault AND read_on > prev_on
  UNION ALL SELECT meter_id, kind, per_day, date(day, '+1 day'), last FROM d WHERE date(day, '+1 day') < last
)
SELECT d.kind, ROUND(SUM(d.per_day * COALESCE(t.cents_per_unit, 0)) / 100.0, 2) AS cost_eur, SUM(t.tariff_id IS NULL) AS unpriced_days
FROM d LEFT JOIN tariffs t ON t.kind = d.kind AND t.valid_from <= d.day AND (t.valid_to IS NULL OR d.day <= t.valid_to)
GROUP BY d.kind ORDER BY d.kind;"""

PRORATED_INCLUSIVE = PRORATED.replace("WHERE date(day, '+1 day') < last", "WHERE date(day, '+1 day') <= last")
PRORATED_BY_LATER = f"""{INTERVALS}
SELECT iv.kind, ROUND(SUM(iv.used * COALESCE(t.cents_per_unit, 0)) / 100.0, 2), SUM(t.tariff_id IS NULL)
FROM iv LEFT JOIN tariffs t ON t.kind = iv.kind AND t.valid_from <= iv.read_on AND (t.valid_to IS NULL OR iv.read_on <= t.valid_to) WHERE NOT iv.fault GROUP BY iv.kind ORDER BY iv.kind;"""

FAULT_EST = f"""{INTERVALS}
, v AS (SELECT iv.*, julianday(read_on) - julianday(prev_on) AS days, ROW_NUMBER() OVER (PARTITION BY meter_id ORDER BY read_on, reading_id) AS rn FROM iv),
ok AS (SELECT meter_id, rn, used * 1.0 / days AS rate FROM v WHERE NOT fault)
SELECT v.serial, v.read_on, CAST(v.days AS INTEGER) AS days,
       ROUND(v.days * COALESCE((SELECT AVG(rate) FROM (SELECT rate FROM ok WHERE ok.meter_id = v.meter_id AND ok.rn < v.rn ORDER BY ok.rn DESC LIMIT 3)), 0), 1) AS estimate
FROM v WHERE v.fault ORDER BY v.serial, v.read_on;"""

FAULT_EST_ALL = FAULT_EST.replace("ORDER BY ok.rn DESC LIMIT 3", "ORDER BY ok.rn DESC")
FAULT_EST_ROWS = f"""{INTERVALS}
, v AS (SELECT iv.*, julianday(read_on) - julianday(prev_on) AS days, CASE WHEN NOT fault THEN used * 1.0 / (julianday(read_on) - julianday(prev_on)) END AS rate FROM iv),
w AS (SELECT v.*, AVG(rate) OVER (PARTITION BY meter_id ORDER BY read_on, reading_id ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS avg_rate FROM v)
SELECT serial, read_on, CAST(days AS INTEGER), ROUND(days * COALESCE(avg_rate, 0), 1) FROM w WHERE fault ORDER BY serial, read_on;"""

METER_SPECS = [
    E("prorated-tariff-cost", "Price the year fairly across tariff changes. Spread the units of every interval (faults excluded) evenly over its days: the days from the previous reading's date (included) up to the later reading's date (excluded). "
      "Price each day with the tariff of that kind in force on that very day; days with no tariff in force are free but must be counted. Columns: kind, total cost in euros (2 decimals), number of days without a tariff. Order by kind.",
      PRORATED, ["kind", "cost_eur", "unpriced_days"], places=2,
      wrong=(PRORATED_INCLUSIVE, PRORATED_BY_LATER)),
    E("fault-gap-estimates", "A meter fault hides the real use of its interval. Estimate it: take the up-to-three most recent earlier intervals of the same meter that are **not** faults (genuine wraps are fine, with their corrected units), "
      "average their units per day, and multiply by the number of days of the faulty interval. A fault with no earlier valid interval is estimated as 0. Columns: serial, date of the later reading, days in the interval, estimated units with 1 decimal. Order by serial, then date.",
      FAULT_EST, ["serial", "read_on", "days", "estimate"], places=1,
      wrong=(FAULT_EST_ALL, FAULT_EST_ROWS)),
]


# ---------------------------------------------------------------- chess

def elo_sql(k, update_state=True, order="game_id"):
    if update_state:
        wr, br = "json_extract(r.st, '$.p' || g.white_id)", "json_extract(r.st, '$.p' || g.black_id)"
        ea = f"(1.0 / (1.0 + pow(10.0, ({br} - {wr}) / 400.0)))"
        step = (f"SELECT g.n, json_set(json_set(r.st, '$.p' || g.white_id, {wr} + {k} * (g.sw - {ea})), '$.p' || g.black_id, {br} + {k} * ({ea} - g.sw)) FROM r JOIN g ON g.n = r.n + 1")
        return f"""WITH RECURSIVE g AS (
  SELECT ROW_NUMBER() OVER (ORDER BY {order}) AS n, white_id, black_id, CASE result WHEN '1-0' THEN 1.0 WHEN '0-1' THEN 0.0 ELSE 0.5 END AS sw FROM games
), r(n, st) AS (
  SELECT 0, (SELECT json_group_object('p' || player_id, rating * 1.0) FROM players)
  UNION ALL
  {step}
)
SELECT p.name, ROUND(j.value, 1) AS rating FROM (SELECT st FROM r ORDER BY n DESC LIMIT 1) f, json_each(f.st) j JOIN players p ON 'p' || p.player_id = j.key
ORDER BY rating DESC, p.name;"""
    return f"""WITH g AS (SELECT white_id, black_id, CASE result WHEN '1-0' THEN 1.0 WHEN '0-1' THEN 0.0 ELSE 0.5 END AS sw FROM games),
d AS (SELECT g.white_id AS pid, {k} * (g.sw - 1.0 / (1.0 + pow(10.0, (b.rating - w.rating) / 400.0))) AS delta FROM g JOIN players w ON w.player_id = g.white_id JOIN players b ON b.player_id = g.black_id
      UNION ALL SELECT g.black_id, {k} * ((1.0 - g.sw) - 1.0 / (1.0 + pow(10.0, (w.rating - b.rating) / 400.0))) FROM g JOIN players w ON w.player_id = g.white_id JOIN players b ON b.player_id = g.black_id)
SELECT p.name, ROUND(p.rating + COALESCE(SUM(d.delta), 0), 1) AS rating FROM players p LEFT JOIN d ON d.pid = p.player_id GROUP BY p.player_id ORDER BY rating DESC, p.name;"""


CHAIN = """WITH RECURSIVE w AS (
  SELECT game_id, round, CASE result WHEN '1-0' THEN white_id ELSE black_id END AS winner, CASE result WHEN '1-0' THEN black_id ELSE white_id END AS loser FROM games WHERE result <> '1/2-1/2'
), c(first_game, round, loser, len) AS (
  SELECT game_id, round, loser, 1 FROM w
  UNION ALL SELECT c.first_game, w.round, w.loser, c.len + 1 FROM c JOIN w ON w.winner = c.loser AND w.round > c.round
)
SELECT MAX(len) AS longest, COUNT(*) AS chains FROM c WHERE len = (SELECT MAX(len) FROM c);"""

CHAIN_STARTS = CHAIN.replace("SELECT MAX(len) AS longest, COUNT(*) AS chains FROM c WHERE len = (SELECT MAX(len) FROM c);", "SELECT MAX(len), COUNT(DISTINCT first_game) FROM c WHERE len = (SELECT MAX(len) FROM c);")
CHAIN_BY_ID = """WITH RECURSIVE w AS (
  SELECT game_id, round, CASE result WHEN '1-0' THEN white_id ELSE black_id END AS winner, CASE result WHEN '1-0' THEN black_id ELSE white_id END AS loser FROM games WHERE result <> '1/2-1/2'
), c(first_game, gid, loser, len) AS (
  SELECT game_id, game_id, loser, 1 FROM w
  UNION ALL SELECT c.first_game, w.game_id, w.loser, c.len + 1 FROM c JOIN w ON w.winner = c.loser AND w.game_id > c.gid
)
SELECT MAX(len), COUNT(*) FROM c WHERE len = (SELECT MAX(len) FROM c);"""

CHESS_SPECS = [
    E("elo-ladder", "Replay the tournament as an Elo ladder. Everybody starts with their `rating`. Process the games in `game_id` order; for each game both players are updated at once from their ratings **before** the game: "
      "`expected(White) = 1 / (1 + 10^((Black - White) / 400))`, White's new rating is `White + 24 * (score - expected)` and Black moves by the opposite amount (`score` is 1, 0.5 or 0 for White). Do not round between games. "
      "Byes change nothing. Columns: name, final rating rounded to 1 decimal. Order by rating descending, then name.",
      elo_sql(24), ["name", "rating"], places=1,
      wrong=(elo_sql(32), elo_sql(24, update_state=False), elo_sql(24, order="round, game_id")),
      notes="`pow()`, `json_set`, `json_extract` and `json_group_object` are available in this SQLite; a recursive CTE can carry a JSON text as its state."),
    E("win-chains", "A **win chain** is a sequence of decisive games g1, g2, ..., gk (k >= 1) in which the winner of each game is the loser of the game before it, and every game is played in a later round than the one before. "
      "Draws never belong to a chain. Report the length (number of games) of the longest chain, and how many different chains (different sequences of games) have that length. One row: longest, chains.",
      CHAIN, ["longest", "chains"],
      wrong=(CHAIN_STARTS, CHAIN_BY_ID)),
]


# ---------------------------------------------------------------- clinic

def plant_clinic(data, rng, big):
    """Book the overlapping and nested slots the base data only creates empty, so that booked intervals really overlap."""
    appts = list(data["appointments"])
    by_start = {(s[1], s[2]): s for s in data["slots"]}
    aid = max(a[0] for a in appts) + 1
    taken = {a[1] for a in appts if a[3] != "cancelled"}
    pat = data["patients"][0][0]
    for key in ((1, "2038-03-16 10:00"), (1, "2038-03-16 10:20"), (1, "2038-03-16 10:50"), (1, "2038-03-17 14:00"), (1, "2038-03-17 14:10"), (1, "2038-03-17 15:30")):
        s = by_start.get(key)
        if s and s[0] not in taken:
            appts.append((aid, s[0], data["patients"][(aid * 7) % len(data["patients"])][0], "booked", "2038-03-12"))
            aid += 1
    sid = max(x[0] for x in data["slots"]) + 1
    slots = list(data["slots"])
    slots.append((sid, 1, "2038-03-17 14:35", 20))  # starts after the short nested slot ended but inside the long slot
    appts.append((aid, sid, data["patients"][-1][0], "booked", "2038-03-12"))
    data["slots"], data["appointments"] = slots, appts
    return data


CLINIC2 = wrap(CLINIC, "clinic-experts", plant_clinic)

WAIT_FCFS = """WITH RECURSIVE free AS (
  SELECT s.slot_id, s.starts_at, d.specialty FROM slots s JOIN doctors d ON d.doctor_id = s.doctor_id
  WHERE s.starts_at >= '2038-03-15' AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.slot_id AND a.status <> 'cancelled')
), q AS (
  SELECT wait_id, patient_id, specialty, earliest, ROW_NUMBER() OVER (ORDER BY requested_on, wait_id) AS n FROM waitlist
), a(n, taken) AS (
  SELECT 0, '[]'
  UNION ALL
  SELECT q.n, json_insert(a.taken, '$[#]', COALESCE((
      SELECT f.slot_id FROM free f WHERE f.specialty = q.specialty AND f.starts_at >= q.earliest AND f.slot_id NOT IN (SELECT value FROM json_each(a.taken))
      ORDER BY f.starts_at, f.slot_id LIMIT 1), 0))
  FROM a JOIN q ON q.n = a.n + 1
), final AS (SELECT taken FROM a ORDER BY n DESC LIMIT 1)
SELECT q.wait_id, p.name AS patient, NULLIF(j.value, 0) AS slot_id
FROM final, json_each(final.taken) j JOIN q ON q.n = j.key + 1 JOIN patients p ON p.patient_id = q.patient_id ORDER BY q.wait_id;"""

WAIT_INDEPENDENT = """WITH free AS (
  SELECT s.slot_id, s.starts_at, d.specialty FROM slots s JOIN doctors d ON d.doctor_id = s.doctor_id
  WHERE s.starts_at >= '2038-03-15' AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.slot_id AND a.status <> 'cancelled')
)
SELECT w.wait_id, p.name, (SELECT f.slot_id FROM free f WHERE f.specialty = w.specialty AND f.starts_at >= w.earliest ORDER BY f.starts_at, f.slot_id LIMIT 1)
FROM waitlist w JOIN patients p ON p.patient_id = w.patient_id ORDER BY w.wait_id;"""

WAIT_BY_ID = WAIT_FCFS.replace("ROW_NUMBER() OVER (ORDER BY requested_on, wait_id)", "ROW_NUMBER() OVER (ORDER BY wait_id)")

UNION_MIN = """WITH b AS (
  SELECT DISTINCT s.slot_id, s.doctor_id, substr(s.starts_at, 1, 10) AS day,
         CAST(strftime('%s', s.starts_at) AS INTEGER) / 60 AS a, CAST(strftime('%s', s.starts_at) AS INTEGER) / 60 + s.minutes AS z
  FROM slots s JOIN appointments p ON p.slot_id = s.slot_id WHERE p.status <> 'cancelled'
), m AS (
  SELECT b.*, MAX(z) OVER (PARTITION BY doctor_id, day ORDER BY a, slot_id ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_end FROM b
), g AS (
  SELECT m.*, SUM(CASE WHEN prev_end IS NULL OR a > prev_end THEN 1 ELSE 0 END) OVER (PARTITION BY doctor_id, day ORDER BY a, slot_id) AS grp FROM m
), blocks AS (SELECT doctor_id, day, grp, MAX(z) - MIN(a) AS len FROM g GROUP BY doctor_id, day, grp)
SELECT d.name AS doctor, x.day, SUM(x.len) AS booked_minutes, COUNT(*) AS blocks FROM blocks x JOIN doctors d ON d.doctor_id = x.doctor_id GROUP BY x.doctor_id, x.day ORDER BY d.name, x.day;"""

UNION_NAIVE = """SELECT d.name, substr(s.starts_at, 1, 10) AS day, SUM(s.minutes), COUNT(*) FROM slots s JOIN doctors d ON d.doctor_id = s.doctor_id
WHERE EXISTS (SELECT 1 FROM appointments p WHERE p.slot_id = s.slot_id AND p.status <> 'cancelled') GROUP BY s.doctor_id, day ORDER BY d.name, day;"""

UNION_PREV_ONLY = UNION_MIN.replace("MAX(z) OVER (PARTITION BY doctor_id, day ORDER BY a, slot_id ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)", "LAG(z) OVER (PARTITION BY doctor_id, day ORDER BY a, slot_id)")

CLINIC_SPECS = [
    E("waitlist-first-come", "Serve the waiting list in order. Take the entries by `requested_on` (ties by wait id). Each entry gets the earliest free slot (earliest start, then lowest slot id) of any doctor with the requested specialty that starts on or after today (2038-03-15) and on or after the entry's `earliest` date, "
      "and that **no earlier entry has already taken**. Entries that find no slot get NULL. Columns: wait id, patient name, slot id. Order by wait id.",
      WAIT_FCFS, ["wait_id", "patient", "slot_id"],
      wrong=(WAIT_INDEPENDENT, WAIT_BY_ID),
      notes="Free means: no appointment with a status other than `cancelled`. A slot taken by one entry is gone for the entries after it, even when the same patient is on the list twice."),
    E("booked-union-minutes", "The clinic's records contain slots of one doctor that overlap, and some of them are booked. For each doctor and day, how many minutes are covered by **at least one** slot that has a non-cancelled appointment (overlapping time counts once)? "
      "Columns: doctor name, day (`YYYY-MM-DD`), covered minutes, number of separate blocks (stretches of covered time; slots that merely touch end to start form one block). Only days with at least one such slot. Order by doctor name, then day.",
      UNION_MIN, ["doctor", "day", "booked_minutes", "blocks"],
      wrong=(UNION_NAIVE, UNION_PREV_ONLY)),
]


# ---------------------------------------------------------------- family tree

COUSINS = """WITH RECURSIVE up(p, anc, d) AS (
  SELECT child_id, parent_id, 1 FROM parent_links
  UNION ALL SELECT up.p, l.parent_id, up.d + 1 FROM up JOIN parent_links l ON l.child_id = up.anc
)
SELECT a.name AS name_a, b.name AS name_b FROM persons a JOIN persons b ON a.person_id < b.person_id
WHERE EXISTS (SELECT 1 FROM up x JOIN up y ON y.anc = x.anc WHERE x.p = a.person_id AND y.p = b.person_id AND x.d = 3 AND y.d = 3)
  AND NOT EXISTS (SELECT 1 FROM up x JOIN up y ON y.anc = x.anc WHERE x.p = a.person_id AND y.p = b.person_id AND (x.d <= 2 OR y.d <= 2))
ORDER BY a.person_id, b.person_id;"""

COUSINS_LOOSE = COUSINS.replace("""
  AND NOT EXISTS (SELECT 1 FROM up x JOIN up y ON y.anc = x.anc WHERE x.p = a.person_id AND y.p = b.person_id AND (x.d <= 2 OR y.d <= 2))""", "")
COUSINS_BIRTH = COUSINS.replace("SELECT child_id, parent_id, 1 FROM parent_links", "SELECT child_id, parent_id, 1 FROM parent_links WHERE kind = 'birth'").replace("JOIN parent_links l ON l.child_id = up.anc", "JOIN parent_links l ON l.child_id = up.anc AND l.kind = 'birth'")

KIN_SPECS = [
    E("second-cousins", "List the pairs of **second cousins**. Two different persons are second cousins when some ancestor is exactly three parent links above both of them (links of any kind), "
      "and they have no common ancestor at all that is only one or two links above either of them (that would make them siblings, first cousins, or a niece and an aunt, and so on). "
      "Each pair appears once, lower person id first. Columns: name of the first, name of the second. Order by the first id, then the second.",
      COUSINS, ["name_a", "name_b"],
      wrong=(COUSINS_LOOSE, COUSINS_BIRTH)),
]


# ---------------------------------------------------------------- access graph

def plant_access(data, rng, big):
    """Redundant grants: an allow to a group and the same allow to a group nested inside it (twice), and an expired grant that makes nothing redundant."""
    grants = list(data["grants"])
    gid = max(g[0] for g in grants)
    today_ok = None
    rows = ((1, 3, "write", "allow", None), (3, 3, "write", "allow", None), (3, 3, "write", "allow", None),
            (1, 4, "write", "allow", "2036-04-01"), (3, 4, "write", "allow", None),
            (2, 3, "admin", "allow", "2036-12-31"), (4, 3, "admin", "allow", None), (4, 3, "admin", "deny", None))
    for g, r, p, e, x in rows:
        gid += 1
        grants.append((gid, g, r, p, e, x))
    data["grants"] = grants
    return data


ACCESS2 = wrap(ACCESS, "access-experts", plant_access)

REDUNDANT = """WITH RECURSIVE up(grp, anc) AS (
  SELECT member_id, group_id FROM memberships WHERE member_kind = 'group'
  UNION SELECT up.grp, m.group_id FROM up JOIN memberships m ON m.member_kind = 'group' AND m.member_id = up.anc
), live AS (
  SELECT * FROM grants WHERE effect = 'allow' AND (expires_on IS NULL OR expires_on >= '2036-05-01')
)
SELECT a.grant_id, gr.name AS grp, r.path, a.perm, MIN(b.grant_id) AS covered_by
FROM live a JOIN live b ON b.resource_id = a.resource_id AND b.perm = a.perm AND b.grant_id <> a.grant_id
  AND (b.group_id IN (SELECT anc FROM up WHERE up.grp = a.group_id) OR (b.group_id = a.group_id AND b.grant_id < a.grant_id))
JOIN groups gr ON gr.group_id = a.group_id JOIN resources r ON r.resource_id = a.resource_id
GROUP BY a.grant_id ORDER BY a.grant_id;"""

REDUNDANT_NO_EXPIRY = REDUNDANT.replace("effect = 'allow' AND (expires_on IS NULL OR expires_on >= '2036-05-01')", "effect = 'allow'")
REDUNDANT_DIRECT = REDUNDANT.replace("b.group_id IN (SELECT anc FROM up WHERE up.grp = a.group_id)", "b.group_id IN (SELECT group_id FROM memberships WHERE member_kind = 'group' AND member_id = a.group_id)")
REDUNDANT_BOTH = REDUNDANT.replace("OR (b.group_id = a.group_id AND b.grant_id < a.grant_id)", "OR b.group_id = a.group_id")

ACCESS_SPECS = [
    E("redundant-grants", "Find the redundant grants. An **in-force allow grant A** is redundant when another in-force allow grant B gives the same permission on the same resource to a group that **contains A's group** (directly or through any chain of nested groups), "
      "or to the very same group with a lower grant id (so of two identical grants only the later one is redundant). Deny grants and expired grants take no part, neither as A nor as B. "
      "Columns: grant id, group name, resource path, permission, and the lowest grant id of a covering B. Order by grant id.",
      REDUNDANT, ["grant_id", "group", "path", "perm", "covered_by"],
      wrong=(REDUNDANT_NO_EXPIRY, REDUNDANT_DIRECT, REDUNDANT_BOTH)),
]


# ---------------------------------------------------------------- bus fares (nested caps)

DAILY_CAP, WEEKLY_CAP = 900, 1400


def caps_sql(daily=DAILY_CAP, weekly=WEEKLY_CAP, week="date(day, 'weekday 0')"):
    return f"""{JOURNEYS}
, q AS (
  SELECT p.*, {week} AS wk,
         MAX(0, MIN(fare, {daily} - COALESCE(SUM(fare) OVER (PARTITION BY card_id, day ORDER BY in_at, in_tap ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0))) AS day_part
  FROM p
), c AS (
  SELECT q.*, SUM(day_part) OVER (PARTITION BY card_id, wk ORDER BY in_at, in_tap ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum
  FROM q
)
SELECT card_id, in_at, fare, MIN(cum, {weekly}) - MIN(cum - day_part, {weekly}) AS collected FROM c WHERE MIN(cum, {weekly}) - MIN(cum - day_part, {weekly}) < fare ORDER BY card_id, in_at, in_tap;"""


DAILY_ONLY = caps_sql(weekly=10 ** 9)
SUNDAY_WEEKS = caps_sql(week="date(day, 'weekday 6')")
WEEKLY_FIRST = f"""{JOURNEYS}
, c AS (SELECT p.*, SUM(fare) OVER (PARTITION BY card_id, date(day, 'weekday 0') ORDER BY in_at, in_tap) AS cum FROM p)
SELECT card_id, in_at, fare, MIN(cum, {WEEKLY_CAP}) - MIN(cum - fare, {WEEKLY_CAP}) AS collected FROM c WHERE MIN(cum, {WEEKLY_CAP}) - MIN(cum - fare, {WEEKLY_CAP}) < fare ORDER BY card_id, in_at, in_tap;"""


def plant_bus(data, rng, big):
    """A heavy weekend: three days in a row (Saturday, Sunday, Monday) of three expensive journeys, so the weekly cap binds in a Monday-to-Sunday week and a Sunday-to-Saturday week gives another answer."""
    from datetime import datetime, timedelta
    taps = list(data["taps"])
    tid = max(t[0] for t in taps)
    card = data["cards"][2][0]
    for day in (15, 16, 17):
        t = datetime(2037, 8, day, 7, 0)
        for k in range(3):
            for stop, kind in ((1 if k % 2 == 0 else 8, "in"), (8 if k % 2 == 0 else 1, "out")):
                tid += 1
                taps.append((tid, card, t.strftime("%Y-%m-%d %H:%M"), stop, kind))
                t += timedelta(minutes=35 if kind == "in" else 100)
    data["taps"] = taps
    return data


BUS2 = wrap(BUS, "bus-experts", plant_bus)

BUS_SPECS = [
    E("daily-and-weekly-caps", f"The council adds a **weekly** cap to the daily one. A card is never charged more than {DAILY_CAP} cents per day (days are the date of the `in` tap) and never more than {WEEKLY_CAP} cents per week (weeks run Monday to Sunday). "
      "Process each card's complete journeys in order (by `in` time, ties by the `in` tap id): a journey is charged its fare, reduced so that neither the day's nor the week's amount **already charged** (not already fared) goes over its cap, never below 0. "
      "List the journeys that were charged less than their fare: card id, `in` time, fare, amount charged. Order by card id, then `in` time, then `in` tap id.",
      caps_sql(), ["card_id", "in_at", "fare", "collected"],
      wrong=(DAILY_ONLY, SUNDAY_WEEKS, WEEKLY_FIRST),
      notes="The fare of a journey is worked out as in the notes above (zone fare, student and senior percentages); incomplete journeys are not charged."),
]


# ---------------------------------------------------------------- greenhouse (hysteresis)

def plant_green(data, rng, big):
    """A zone that dips below 30, climbs into the grey band (30-40) and dips again before it recovers, over several hours."""
    from datetime import datetime, timedelta
    readings = list(data["readings"])
    rid = max(r[0] for r in readings)
    zone = data["zones"][-1][0]
    t = datetime(2039, 6, 19, 2, 0)
    for m in (33.0, 28.5, 26.0, 34.5, 36.0, 27.5, 29.0, 38.0, 41.5, 44.0, 31.0, 29.5, 33.0):
        rid += 1
        readings.append((rid, zone, t.strftime("%Y-%m-%d %H:%M"), m, 21.5))
        t += timedelta(minutes=20)
    data["readings"] = readings
    return data


GREEN2 = wrap(GREEN, "greenhouse-experts", plant_green)

EPISODES = """WITH s AS (
  SELECT r.zone_id, z.name, r.taken_at, r.moisture_pct, r.reading_id,
         CASE WHEN r.moisture_pct < 30 THEN 1 WHEN r.moisture_pct >= 40 THEN 0 END AS sig,
         ROW_NUMBER() OVER (PARTITION BY r.zone_id ORDER BY r.taken_at, r.reading_id) AS rn
  FROM readings r JOIN zones z ON z.zone_id = r.zone_id
), st AS (
  SELECT s.*, COALESCE((SELECT b.sig FROM s b WHERE b.zone_id = s.zone_id AND b.rn <= s.rn AND b.sig IS NOT NULL ORDER BY b.rn DESC LIMIT 1), 0) AS state FROM s
), pv AS (
  SELECT st.*, LAG(state, 1, 0) OVER (PARTITION BY zone_id ORDER BY rn) AS prev_state FROM st
), ed AS (
  SELECT pv.*, SUM(CASE WHEN state = 1 AND prev_state = 0 THEN 1 ELSE 0 END) OVER (PARTITION BY zone_id ORDER BY rn) AS ep FROM pv
)
SELECT e.name AS zone, e.started, n.taken_at AS ended, e.lowest
FROM (SELECT zone_id, name, MIN(taken_at) AS started, MAX(rn) AS last_rn, MIN(moisture_pct) AS lowest FROM ed WHERE state = 1 GROUP BY zone_id, ep) e
LEFT JOIN s n ON n.zone_id = e.zone_id AND n.rn = e.last_rn + 1 ORDER BY e.name, e.started;"""

EPISODES_NAIVE = """WITH s AS (SELECT r.zone_id, z.name, r.taken_at, r.moisture_pct, ROW_NUMBER() OVER (PARTITION BY r.zone_id ORDER BY r.taken_at, r.reading_id) AS rn,
         ROW_NUMBER() OVER (PARTITION BY r.zone_id, r.moisture_pct < 30 ORDER BY r.taken_at, r.reading_id) AS rk FROM readings r JOIN zones z ON z.zone_id = r.zone_id)
SELECT e.name, e.started, n.taken_at, e.lowest
FROM (SELECT zone_id, name, MIN(taken_at) AS started, MAX(rn) AS last_rn, MIN(moisture_pct) AS lowest FROM s WHERE moisture_pct < 30 GROUP BY zone_id, rn - rk) e
LEFT JOIN s n ON n.zone_id = e.zone_id AND n.rn = e.last_rn + 1 ORDER BY e.name, e.started;"""

EPISODES_BAND_ENDS = EPISODES.replace("WHEN r.moisture_pct >= 40 THEN 0", "WHEN r.moisture_pct >= 35 THEN 0")

GREEN_SPECS = [
    E("dry-episodes-hysteresis", "The grower's rule for a *dry episode* has hysteresis. Walk the readings of each zone in time order (ties by reading id). A zone is **dry** from the first reading below 30 percent moisture, "
      "and stays dry until a reading of **40 or more**; readings between 30 and 39.9 change nothing (a reading below 30 while already dry changes nothing either). Before the first reading below 30 or at least 40, a zone is not dry. "
      "Report each episode: zone name, `taken_at` of the reading that started it, `taken_at` of the reading that ended it (NULL if the zone was still dry at its last reading), and the lowest moisture among the readings from the start up to, but not including, the ending reading. "
      "Order by zone name, then start.",
      EPISODES, ["zone", "started", "ended", "lowest"],
      wrong=(EPISODES_NAIVE, EPISODES_BAND_ENDS)),
]


# ---------------------------------------------------------------- families

@family("data-expert-meters", category="data", lang="sql", kind="feature", n=len(METER_SPECS),
        summary="expert SQL on utility meter readings: day-wise proration across tariff changes, estimating faulty intervals from the last valid ones")
def expert_meters(rng, n):
    return K.query_tasks(METERS2, METER_SPECS, rng, n)


@family("data-expert-chess", category="data", lang="sql", kind="feature", n=len(CHESS_SPECS),
        summary="expert SQL on a chess tournament: an Elo ladder replayed as a recursive state machine, longest win chains over rounds")
def expert_chess(rng, n):
    return K.query_tasks(CHESS, CHESS_SPECS, rng, n)


@family("data-expert-clinic", category="data", lang="sql", kind="feature", n=len(CLINIC_SPECS),
        summary="expert SQL on clinic slots: first-come waiting-list allocation without reuse, union of overlapping booked intervals")
def expert_clinic(rng, n):
    return K.query_tasks(CLINIC2, CLINIC_SPECS, rng, n)


@family("data-expert-genealogy", category="data", lang="sql", kind="feature", n=len(KIN_SPECS),
        summary="expert SQL on a family tree: second cousins through exact ancestor depths with exclusions")
def expert_genealogy(rng, n):
    return K.query_tasks(KIN, KIN_SPECS, rng, n)


@family("data-expert-vault", category="data", lang="sql", kind="feature", n=len(ACCESS_SPECS),
        summary="expert SQL on a document vault: redundant grants through group nesting, expiry and duplicates")
def expert_vault(rng, n):
    return K.query_tasks(ACCESS2, ACCESS_SPECS, rng, n)


@family("data-expert-bus-caps", category="data", lang="sql", kind="feature", n=len(BUS_SPECS),
        summary="expert SQL on bus taps: nested daily and weekly fare caps applied journey by journey")
def expert_bus(rng, n):
    return K.query_tasks(BUS2, BUS_SPECS, rng, n)


@family("data-expert-greenhouse", category="data", lang="sql", kind="feature", n=len(GREEN_SPECS),
        summary="expert SQL on greenhouse sensors: dry episodes with hysteresis thresholds")
def expert_greenhouse(rng, n):
    return K.query_tasks(GREEN2, GREEN_SPECS, rng, n)
