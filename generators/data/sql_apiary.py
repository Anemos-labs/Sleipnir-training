"""SQL tasks on an invented beekeeping association's hive records (top-n per group, running shares, before/after pairs, streaks)."""
from datetime import date, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE apiaries (
      apiary_id    INTEGER PRIMARY KEY,
      name         TEXT NOT NULL UNIQUE,
      elevation_m  INTEGER NOT NULL
    );
    CREATE TABLE hives (
      hive_id     INTEGER PRIMARY KEY,
      apiary_id   INTEGER NOT NULL REFERENCES apiaries(apiary_id),
      label       TEXT NOT NULL,
      queen_year  INTEGER NOT NULL,            -- year the current queen was born
      breed       TEXT NOT NULL,
      active      INTEGER NOT NULL DEFAULT 1,  -- 0 once the colony died or was merged
      UNIQUE (apiary_id, label)
    );
    CREATE TABLE inspections (
      insp_id         INTEGER PRIMARY KEY,
      hive_id         INTEGER NOT NULL REFERENCES hives(hive_id),
      inspected_on    TEXT NOT NULL,           -- YYYY-MM-DD
      brood_frames    INTEGER NOT NULL,
      varroa_per_100  REAL NOT NULL,           -- mites per 100 bees
      queen_seen      INTEGER NOT NULL,        -- 1 if the queen was spotted
      temperament     INTEGER NOT NULL         -- 1 calm .. 5 aggressive
    );
    CREATE TABLE harvests (
      harvest_id    INTEGER PRIMARY KEY,
      hive_id       INTEGER NOT NULL REFERENCES hives(hive_id),
      harvested_on  TEXT NOT NULL,
      honey_kg      REAL NOT NULL,
      moisture_pct  REAL NOT NULL
    );
    CREATE TABLE treatments (
      treat_id    INTEGER PRIMARY KEY,
      hive_id     INTEGER NOT NULL REFERENCES hives(hive_id),
      applied_on  TEXT NOT NULL,
      product     TEXT NOT NULL
    );
''')

DOC = dd('''
    The Marram Valley Beekeepers' Association keeps shared records for its apiaries (bee yards) and the hives in them.

    * A hive belongs to one apiary; `label` is unique inside the apiary. `active = 0` means the colony is gone (its old rows stay).
    * An **inspection** records brood frames, `varroa_per_100` (mites per 100 bees; above 3.0 a colony needs treatment),
      whether the queen was seen and the temperament.
    * A **harvest** is honey taken from one hive on one day; `moisture_pct` above 18.5 is too wet to sell as table honey.
    * A **treatment** is a varroa product applied to a hive on a date.
    * Dates are ISO text. The association's "today" in reports is **2031-09-30**.
''')

APIARIES = ["Hollow Oak", "Gorse Bank", "Long Meadow", "Quarry Edge", "Salt Fen"]
BREEDS = ["buckfast", "carniolan", "native black", "italian"]
PRODUCTS = ["oxalic-vap", "formic-pad", "thymol-gel", "drone-cull"]


def gen(rng, big):
    na = 4 if big else 2
    apiaries = [(i + 1, APIARIES[i], rng.choice([20, 85, 140, 260, 410])) for i in range(na)]
    hives, hid = [], 0
    for a in apiaries:
        for j in range(rng.randint(4, 6) if big else rng.randint(2, 3)):
            hid += 1
            hives.append((hid, a[0], f"H{j + 1:02d}", rng.randint(2026, 2031), rng.choice(BREEDS), 0 if rng.random() < 0.12 else 1))
    hives[-1] = hives[-1][:5] + (1,)  # the newest hive is active and has never been inspected
    insp, iid = [], 0
    rising = {hives[1][0]: [1.0, 2.0, 3.5], hives[3][0]: [0.5, 1.5, 1.5]} if len(hives) > 3 else {hives[1][0]: [1.0, 2.0, 3.5]}  # one strictly rising, one not
    queenless = hives[2][0]
    for h in hives:
        if h is hives[-1]:
            continue
        d = date(2031, 4, rng.randint(1, 20))
        n = rng.randint(4, 8) if big else rng.randint(3, 5)
        v = rng.choice([0.5, 1.0, 1.5, 2.0])
        dates = []
        for k in range(n):
            dates.append(d)
            d = d + timedelta(days=rng.choice([7, 14, 14, 21, 30]))
        if not h[5]:
            dates = [x for x in dates if x < date(2031, 7, 1)] or dates[:1]
        elif h[0] % 4 == 0:
            dates = [x for x in dates if x < date(2031, 8, 28)] or dates[:1]  # no recent inspection
        for k, d in enumerate(dates):
            iid += 1
            v = max(0.0, v + rng.choice([-1.0, -0.5, 0.0, 0.5, 1.0, 1.5]))
            queen = 0 if (h[0] == queenless and k in (1, 2, 3)) or rng.random() < 0.12 else 1
            insp.append([iid, h[0], K.iso(d), rng.randint(2, 10), v, queen, rng.randint(1, 5)])
        if h[0] in rising:  # the last three inspections carry the planted varroa pattern
            for row, val in zip(insp[-3:], rising[h[0]]):
                row[4] = val
    harv, hv = [], 0
    for h in hives:
        for yr in (2029, 2030, 2031):
            if h[2] == "H01" and False:
                continue
            if h[1] == 1 + (na - 1) and yr == 2030 and big:
                continue  # the last apiary had no harvest at all in 2030
            if yr < h[3] - 1 and rng.random() < 0.6:
                continue
            for _ in range(rng.choice([0, 1, 1, 2])):
                hv += 1
                harv.append((hv, h[0], K.iso(date(yr, rng.randint(6, 8), rng.randint(1, 28))), rng.choice(range(8, 51)) / 2.0, rng.choice(range(31, 42)) / 2.0))
    if big:
        harv.append((hv + 1, hives[0][0], "2031-08-02", 12.5, 18.5))  # exactly on the moisture limit
    treat, tid = [], 0
    for h in hives:
        rows = [r for r in insp if r[1] == h[0]]
        if len(rows) >= 3 and h[5] and rng.random() < 0.7:
            tid += 1
            at = date.fromisoformat(rows[len(rows) // 2][2]) + timedelta(days=rng.choice([1, 3]))
            treat.append((tid, h[0], K.iso(at), rng.choice(PRODUCTS)))
    return {"apiaries": apiaries, "hives": hives, "inspections": [tuple(r) for r in insp], "harvests": harv, "treatments": treat}


DOMAIN = K.Domain("apiary", "Marram Valley Beekeepers: hive records", SCHEMA, DOC, gen)
S = K.Spec

SPECS = [
    S("old-queens", 1,
      "Which active hives still have a queen born in 2028 or earlier? Show the apiary name, the hive label and the queen's birth year, ordered by queen year, then apiary, then label.",
      """SELECT a.name AS apiary, h.label, h.queen_year
FROM hives h JOIN apiaries a ON a.apiary_id = h.apiary_id
WHERE h.active = 1 AND h.queen_year <= 2028
ORDER BY h.queen_year, a.name, h.label;""",
      ["apiary", "label", "queen_year"], ordered=True),
    S("honey-per-apiary-year", 2,
      "Honey totals by apiary and year, 2029 to 2031: apiary name, harvest year, total kilograms, and the average moisture weighted by kilograms, both rounded to 1 decimal. "
      "Only apiary-years with at least one harvest appear. Order by apiary, then year.",
      """SELECT a.name AS apiary, CAST(substr(v.harvested_on, 1, 4) AS INTEGER) AS year,
       ROUND(SUM(v.honey_kg), 1) AS kg, ROUND(SUM(v.honey_kg * v.moisture_pct) / SUM(v.honey_kg), 1) AS moisture
FROM harvests v JOIN hives h ON h.hive_id = v.hive_id JOIN apiaries a ON a.apiary_id = h.apiary_id
WHERE v.harvested_on >= '2029-01-01' AND v.harvested_on < '2032-01-01'
GROUP BY a.apiary_id, year
ORDER BY a.name, year;""",
      ["apiary", "year", "kg", "moisture"], ordered=True,
      wrong=("""SELECT a.name, CAST(substr(v.harvested_on, 1, 4) AS INTEGER) AS y, ROUND(SUM(v.honey_kg), 1), ROUND(AVG(v.moisture_pct), 1)
FROM harvests v JOIN hives h ON h.hive_id = v.hive_id JOIN apiaries a ON a.apiary_id = h.apiary_id GROUP BY a.apiary_id, y ORDER BY a.name, y;""",)),
    S("not-inspected-lately", 2,
      "Active hives that have not been inspected in the last 30 days (an inspection on or after 2031-08-31 counts as recent). Give apiary, label and the date of the most recent inspection "
      "(NULL if the hive was never inspected). Order by apiary name, then label.",
      """SELECT a.name AS apiary, h.label, (SELECT MAX(i.inspected_on) FROM inspections i WHERE i.hive_id = h.hive_id) AS last_inspected
FROM hives h JOIN apiaries a ON a.apiary_id = h.apiary_id
WHERE h.active = 1 AND NOT EXISTS (SELECT 1 FROM inspections i WHERE i.hive_id = h.hive_id AND i.inspected_on >= '2031-08-31')
ORDER BY a.name, h.label;""",
      ["apiary", "label", "last_inspected"], ordered=True,
      wrong=("""SELECT a.name, h.label, MAX(i.inspected_on) AS m FROM hives h JOIN apiaries a ON a.apiary_id = h.apiary_id LEFT JOIN inspections i ON i.hive_id = h.hive_id
WHERE h.active = 1 GROUP BY h.hive_id HAVING m < '2031-08-31' ORDER BY a.name, h.label;""",
             """SELECT a.name, h.label, MAX(i.inspected_on) FROM hives h JOIN apiaries a ON a.apiary_id = h.apiary_id LEFT JOIN inspections i ON i.hive_id = h.hive_id AND i.inspected_on < '2031-08-31'
WHERE h.active = 1 GROUP BY h.hive_id ORDER BY a.name, h.label;""")),
    S("treat-now", 3,
      "Treatment list: for each active hive take its most recent inspection (when two share a date, the higher inspection id is the most recent) and list the hives whose varroa count there is above 3.0 per 100 bees. "
      "Columns: apiary, hive label, inspection date, varroa. Worst first, ties by apiary then label.",
      """SELECT a.name AS apiary, h.label, i.inspected_on, i.varroa_per_100 AS varroa FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY hive_id ORDER BY inspected_on DESC, insp_id DESC) AS rn FROM inspections
) i
JOIN hives h ON h.hive_id = i.hive_id JOIN apiaries a ON a.apiary_id = h.apiary_id
WHERE i.rn = 1 AND h.active = 1 AND i.varroa_per_100 > 3.0
ORDER BY i.varroa_per_100 DESC, a.name, h.label;""",
      ["apiary", "label", "inspected_on", "varroa"], ordered=True,
      wrong=("""SELECT a.name, h.label, i.inspected_on, i.varroa_per_100 FROM inspections i JOIN hives h ON h.hive_id = i.hive_id JOIN apiaries a ON a.apiary_id = h.apiary_id
WHERE h.active = 1 AND i.varroa_per_100 > 3.0 ORDER BY i.varroa_per_100 DESC, a.name, h.label;""",)),
    S("top-two-hives", 3,
      "Inside each apiary, which hives produced the most honey over all years? Rank hives by total kilograms with DENSE_RANK semantics (equal totals share a rank, no gaps) and show everyone with rank 1 or 2. "
      "Hives with no harvest are not ranked. Columns: apiary, label, total kg, rank. Order by apiary, rank, label.",
      """WITH t AS (
  SELECT h.apiary_id, h.label, SUM(v.honey_kg) AS kg FROM hives h JOIN harvests v ON v.hive_id = h.hive_id GROUP BY h.hive_id
), r AS (
  SELECT apiary_id, label, kg, DENSE_RANK() OVER (PARTITION BY apiary_id ORDER BY kg DESC) AS rnk FROM t
)
SELECT a.name AS apiary, r.label, r.kg, r.rnk FROM r JOIN apiaries a ON a.apiary_id = r.apiary_id
WHERE r.rnk <= 2 ORDER BY a.name, r.rnk, r.label;""",
      ["apiary", "label", "kg", "rank"], ordered=True,
      wrong=("""WITH t AS (SELECT h.apiary_id, h.label, SUM(v.honey_kg) AS kg FROM hives h JOIN harvests v ON v.hive_id = h.hive_id GROUP BY h.hive_id),
r AS (SELECT apiary_id, label, kg, ROW_NUMBER() OVER (PARTITION BY apiary_id ORDER BY kg DESC, label) AS rnk FROM t)
SELECT a.name, r.label, r.kg, r.rnk FROM r JOIN apiaries a ON a.apiary_id = r.apiary_id WHERE r.rnk <= 2 ORDER BY a.name, r.rnk, r.label;""",)),
    S("year-on-year-honey", 3,
      "For every apiary and every harvest year it has data for, show the total honey in kg and the change against the previous calendar year as a percentage rounded to 1 decimal "
      "(NULL when the apiary has no harvest in the previous calendar year, or when that year's total is 0). Order by apiary, then year.",
      """WITH y AS (
  SELECT h.apiary_id, CAST(substr(v.harvested_on, 1, 4) AS INTEGER) AS yr, SUM(v.honey_kg) AS kg
  FROM harvests v JOIN hives h ON h.hive_id = v.hive_id GROUP BY h.apiary_id, yr
)
SELECT a.name AS apiary, c.yr AS year, c.kg,
       CASE WHEN p.kg IS NULL OR p.kg = 0 THEN NULL ELSE ROUND(100.0 * (c.kg - p.kg) / p.kg, 1) END AS change_pct
FROM y c JOIN apiaries a ON a.apiary_id = c.apiary_id
LEFT JOIN y p ON p.apiary_id = c.apiary_id AND p.yr = c.yr - 1
ORDER BY a.name, c.yr;""",
      ["apiary", "year", "kg", "change_pct"], ordered=True,
      wrong=("""WITH y AS (SELECT h.apiary_id, CAST(substr(v.harvested_on, 1, 4) AS INTEGER) AS yr, SUM(v.honey_kg) AS kg FROM harvests v JOIN hives h ON h.hive_id = v.hive_id GROUP BY h.apiary_id, yr)
 SELECT a.name, yr, kg, ROUND(100.0 * (kg - LAG(kg) OVER (PARTITION BY y.apiary_id ORDER BY yr)) / LAG(kg) OVER (PARTITION BY y.apiary_id ORDER BY yr), 1)
FROM y JOIN apiaries a ON a.apiary_id = y.apiary_id ORDER BY a.name, yr;""",)),
    S("pareto-hives", 4,
      "Pareto check: in each apiary, line up hives from the biggest honey producer to the smallest (ties by hive label) and find the smallest group at the top that together reaches at least 80% of the apiary's total honey. "
      "List those hives: apiary, label, kg, and the cumulative percentage after adding the hive, rounded to 1 decimal. Order by apiary, then position in the line-up.",
      """WITH t AS (
  SELECT h.apiary_id, h.label, SUM(v.honey_kg) AS kg FROM hives h JOIN harvests v ON v.hive_id = h.hive_id GROUP BY h.hive_id
), c AS (
  SELECT apiary_id, label, kg,
         SUM(kg) OVER (PARTITION BY apiary_id ORDER BY kg DESC, label) AS cum,
         SUM(kg) OVER (PARTITION BY apiary_id) AS total,
         ROW_NUMBER() OVER (PARTITION BY apiary_id ORDER BY kg DESC, label) AS pos
  FROM t
)
SELECT a.name AS apiary, c.label, c.kg, ROUND(100.0 * c.cum / c.total, 1) AS cum_pct
FROM c JOIN apiaries a ON a.apiary_id = c.apiary_id
WHERE c.cum - c.kg < 0.8 * c.total
ORDER BY a.name, c.pos;""",
      ["apiary", "label", "kg", "cum_pct"], ordered=True,
      wrong=("""WITH t AS (SELECT h.apiary_id, h.label, SUM(v.honey_kg) AS kg FROM hives h JOIN harvests v ON v.hive_id = h.hive_id GROUP BY h.hive_id),
c AS (SELECT apiary_id, label, kg, SUM(kg) OVER (PARTITION BY apiary_id ORDER BY kg DESC, label) AS cum, SUM(kg) OVER (PARTITION BY apiary_id) AS total, ROW_NUMBER() OVER (PARTITION BY apiary_id ORDER BY kg DESC, label) AS pos FROM t)
SELECT a.name, c.label, c.kg, ROUND(100.0 * c.cum / c.total, 1) FROM c JOIN apiaries a ON a.apiary_id = c.apiary_id WHERE c.cum <= 0.8 * c.total ORDER BY a.name, c.pos;""",)),
    S("rising-varroa", 4,
      "Early warning: find active hives whose last three inspections (by date, ties by inspection id) show the varroa count strictly increasing from the oldest of the three to the newest. "
      "Hives with fewer than three inspections can't qualify. Show apiary, label, and the three readings as `v1` (oldest), `v2`, `v3` (newest). Order by apiary, then label.",
      """WITH r AS (
  SELECT hive_id, varroa_per_100 AS v, ROW_NUMBER() OVER (PARTITION BY hive_id ORDER BY inspected_on DESC, insp_id DESC) AS rn FROM inspections
), p AS (
  SELECT hive_id,
         MAX(CASE WHEN rn = 3 THEN v END) AS v1, MAX(CASE WHEN rn = 2 THEN v END) AS v2, MAX(CASE WHEN rn = 1 THEN v END) AS v3
  FROM r WHERE rn <= 3 GROUP BY hive_id
)
SELECT a.name AS apiary, h.label, p.v1, p.v2, p.v3
FROM p JOIN hives h ON h.hive_id = p.hive_id JOIN apiaries a ON a.apiary_id = h.apiary_id
WHERE h.active = 1 AND p.v1 IS NOT NULL AND p.v1 < p.v2 AND p.v2 < p.v3
ORDER BY a.name, h.label;""",
      ["apiary", "label", "v1", "v2", "v3"], ordered=True,
      wrong=("""WITH r AS (SELECT hive_id, varroa_per_100 AS v, ROW_NUMBER() OVER (PARTITION BY hive_id ORDER BY inspected_on DESC, insp_id DESC) AS rn FROM inspections),
p AS (SELECT hive_id, MAX(CASE WHEN rn = 3 THEN v END) AS v1, MAX(CASE WHEN rn = 2 THEN v END) AS v2, MAX(CASE WHEN rn = 1 THEN v END) AS v3 FROM r WHERE rn <= 3 GROUP BY hive_id)
SELECT a.name, h.label, p.v1, p.v2, p.v3 FROM p JOIN hives h ON h.hive_id = p.hive_id JOIN apiaries a ON a.apiary_id = h.apiary_id
WHERE h.active = 1 AND p.v1 <= p.v2 AND p.v2 <= p.v3 ORDER BY a.name, h.label;""",)),
    S("queenless-streaks", 4,
      "A hive that keeps failing to show its queen may have lost her. For each hive, find runs of consecutive inspections (in date order, ties by inspection id) in which the queen was not seen, "
      "and list the runs of two or more: apiary, hive label, date of the first inspection of the run, date of the last, and the length. Order by apiary, label, first date.",
      """WITH s AS (
  SELECT hive_id, inspected_on, queen_seen,
         ROW_NUMBER() OVER (PARTITION BY hive_id ORDER BY inspected_on, insp_id) AS rn,
         ROW_NUMBER() OVER (PARTITION BY hive_id, queen_seen ORDER BY inspected_on, insp_id) AS rk
  FROM inspections
)
SELECT a.name AS apiary, h.label, MIN(s.inspected_on) AS first_on, MAX(s.inspected_on) AS last_on, COUNT(*) AS len
FROM s JOIN hives h ON h.hive_id = s.hive_id JOIN apiaries a ON a.apiary_id = h.apiary_id
WHERE s.queen_seen = 0
GROUP BY s.hive_id, s.rn - s.rk
HAVING COUNT(*) >= 2
ORDER BY a.name, h.label, first_on;""",
      ["apiary", "label", "first_on", "last_on", "length"], ordered=True,
      wrong=("""SELECT a.name, h.label, MIN(i.inspected_on), MAX(i.inspected_on), COUNT(*) FROM inspections i JOIN hives h ON h.hive_id = i.hive_id JOIN apiaries a ON a.apiary_id = h.apiary_id
WHERE i.queen_seen = 0 GROUP BY i.hive_id HAVING COUNT(*) >= 2 ORDER BY a.name, h.label, 3;""",)),
    S("treatment-effect", 5,
      "Did the treatments work? For each treatment, the 'before' reading is the varroa count of the latest inspection strictly before the application date and the 'after' reading is the varroa count of the "
      "earliest inspection at least 7 days after it (ties on the date: the lower inspection id). Treatments missing either reading are ignored. "
      "Per product, report how many treatments were measured, the average drop (before minus after) rounded to 2 decimals, and how many treatments actually reduced the count (drop > 0). Order by average drop descending, then product.",
      """WITH m AS (
  SELECT t.treat_id, t.product,
         (SELECT i.varroa_per_100 FROM inspections i WHERE i.hive_id = t.hive_id AND i.inspected_on < t.applied_on
          ORDER BY i.inspected_on DESC, i.insp_id DESC LIMIT 1) AS before_v,
         (SELECT i.varroa_per_100 FROM inspections i WHERE i.hive_id = t.hive_id AND julianday(i.inspected_on) >= julianday(t.applied_on) + 7
          ORDER BY i.inspected_on, i.insp_id LIMIT 1) AS after_v
  FROM treatments t
)
SELECT product, COUNT(*) AS measured, ROUND(AVG(before_v - after_v), 2) AS avg_drop, SUM(before_v - after_v > 0) AS reduced
FROM m WHERE before_v IS NOT NULL AND after_v IS NOT NULL
GROUP BY product ORDER BY avg_drop DESC, product;""",
      ["product", "measured", "avg_drop", "reduced"], ordered=True, show=False,
      wrong=("""WITH m AS (SELECT t.treat_id, t.product, (SELECT i.varroa_per_100 FROM inspections i WHERE i.hive_id = t.hive_id AND i.inspected_on <= t.applied_on ORDER BY i.inspected_on DESC, i.insp_id DESC LIMIT 1) AS before_v,
(SELECT i.varroa_per_100 FROM inspections i WHERE i.hive_id = t.hive_id AND julianday(i.inspected_on) > julianday(t.applied_on) ORDER BY i.inspected_on, i.insp_id LIMIT 1) AS after_v FROM treatments t)
SELECT product, COUNT(*), ROUND(AVG(before_v - after_v), 2) AS d, SUM(before_v - after_v > 0) FROM m WHERE before_v IS NOT NULL AND after_v IS NOT NULL GROUP BY product ORDER BY d DESC, product;""",)),
    S("fix-honey-per-hive", 2,
      "The 'average honey per active hive' figure for each apiary is wrong: it divides the apiary's honey by the number of harvest rows, not by the number of hives, "
      "and it also leaves out hives that never produced anything. Fix `query.sql` so it returns, for every apiary, the total kilograms of honey from its ACTIVE hives (0 if none) divided by its number of active hives, "
      "rounded to 2 decimals (0 for an apiary with no active hive). Order by apiary name.",
      ref="""SELECT a.name AS apiary,
       CASE WHEN COUNT(DISTINCT h.hive_id) = 0 THEN 0
            ELSE ROUND(COALESCE(SUM(v.honey_kg), 0) / COUNT(DISTINCT h.hive_id), 2) END AS kg_per_hive
FROM apiaries a
LEFT JOIN hives h ON h.apiary_id = a.apiary_id AND h.active = 1
LEFT JOIN harvests v ON v.hive_id = h.hive_id
GROUP BY a.apiary_id
ORDER BY a.name;""",
      cols=["apiary", "kg_per_hive"], ordered=True, show=False,
      buggy="""SELECT a.name AS apiary, ROUND(SUM(v.honey_kg) / COUNT(*), 2) AS kg_per_hive
FROM apiaries a
JOIN hives h ON h.apiary_id = a.apiary_id
JOIN harvests v ON v.hive_id = h.hive_id
WHERE h.active = 1
GROUP BY a.apiary_id
ORDER BY a.name;"""),
]


@family("data-apiary-records", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL reports on a beekeepers' association: top-n per group, running shares, before/after pairs, streaks")
def apiary(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
