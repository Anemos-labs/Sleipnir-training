"""SQL tasks on an invented utility co-op's meter readings (cumulative counters with rollover, tariff periods, estimate streaks, missing months)."""
from datetime import date, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE sites (
      site_id  INTEGER PRIMARY KEY,
      name     TEXT NOT NULL UNIQUE,
      region   TEXT NOT NULL
    );
    CREATE TABLE meters (
      meter_id  INTEGER PRIMARY KEY,
      site_id   INTEGER NOT NULL REFERENCES sites(site_id),
      kind      TEXT NOT NULL CHECK (kind IN ('electric', 'gas', 'water')),
      serial    TEXT NOT NULL UNIQUE,
      dial_max  INTEGER NOT NULL             -- the dial shows 0..dial_max and then wraps to 0
    );
    CREATE TABLE readings (
      reading_id  INTEGER PRIMARY KEY,
      meter_id    INTEGER NOT NULL REFERENCES meters(meter_id),
      read_on     TEXT NOT NULL,
      value       INTEGER NOT NULL,           -- what the dial showed
      source      TEXT NOT NULL CHECK (source IN ('auto', 'manual', 'estimate'))
    );
    CREATE TABLE tariffs (
      tariff_id       INTEGER PRIMARY KEY,
      kind            TEXT NOT NULL,
      valid_from      TEXT NOT NULL,
      valid_to        TEXT,                   -- inclusive; NULL = still valid
      cents_per_unit  INTEGER NOT NULL
    );
''')

DOC = dd('''
    The Lowmoor Utilities Co-op reads the meters of its member sites about once a month.

    * A meter's `value` is a cumulative counter. The **consumption** of an interval is the value of a reading minus the value of the previous reading of the same meter (previous by `read_on`, ties by reading id).
      When the dial wraps from `dial_max` to 0 the new value is smaller than the old one, and the consumption is `value + (dial_max + 1) - previous`. The first reading of a meter has no interval.
    * A decrease is only a genuine wrap when the previous value was in the top tenth of the dial (at least `0.9 * dial_max`) and the new value is in the bottom tenth (at most `0.1 * dial_max`). Any other decrease is a **meter fault**.
    * An interval belongs to the month of its later reading (`substr(read_on, 1, 7)`) and is priced with the tariff of that kind that is in force on the later reading's date
      (`valid_from <= read_on` and `valid_to` is NULL or `read_on <= valid_to`).
    * `source` says how the value was obtained: automatically, by a person, or estimated by the co-op.
    * Dates are ISO text. The report date is **2037-01-31**.
''')

SITES = [("Alder Croft", "north"), ("Bracken Mill", "north"), ("Cinder Barn", "south"), ("Dunlin Lodge", "south"), ("Eyot Cottage", "east")]
KINDS = {"electric": (9999, (250, 800)), "gas": (999, (20, 120)), "water": (9999, (5, 30))}


def gen(rng, big):
    ns = 5 if big else 2
    sites = [(i + 1, SITES[i][0], SITES[i][1]) for i in range(ns)]
    meters, readings, mid, rid = [], [], 0, 0
    for s in sites:
        for kind in ["electric"] + rng.sample(["gas", "water"], rng.choice([0, 1, 1, 2]) if big else 1):
            mid += 1
            dmax, (lo, hi) = KINDS[kind]
            meters.append((mid, s[0], kind, f"{kind[0].upper()}{rng.randint(10000, 99999)}", dmax))
            val = rng.randint(int(dmax * 0.4), dmax)
            d = date(2036, 1, rng.randint(1, 20))
            while d <= date(2037, 1, 28):
                rid += 1
                readings.append([rid, mid, d.isoformat(), val, rng.choices(["auto", "manual", "estimate"], [0.6, 0.3, 0.1])[0]])
                val = (val + rng.randint(lo, hi)) % (dmax + 1)
                d += timedelta(days=rng.randint(27, 35))
    # plant: a meter fault (the value drops far from the top of the dial), a gap of two months in one electric meter, two consecutive estimates
    by = {}
    for r in readings:
        by.setdefault(r[1], []).append(r)
    elec = [m for m in meters if m[2] == "electric"]
    rows = by[elec[0][0]]
    rows[5][3] = max(0, rows[4][3] - 400) if rows[4][3] > 500 else rows[4][3]
    if rows[5][3] >= rows[4][3]:
        rows[5][3] = max(0, rows[4][3] - 1)
    for r in by[elec[-1][0]][3:5]:
        r[4] = "estimate"
    drop = {by[elec[0][0]][8][0], by[elec[0][0]][9][0]} if len(by[elec[0][0]]) > 10 else set()
    readings = [r for r in readings if r[0] not in drop]
    tariffs = [(1, "electric", "2036-01-01", "2036-06-30", 28), (2, "electric", "2036-07-01", None, 31), (3, "gas", "2036-01-01", "2036-03-31", 9), (4, "gas", "2036-05-01", None, 11), (5, "water", "2036-01-01", None, 4)]
    return {"sites": sites, "meters": meters, "readings": [tuple(r) for r in readings], "tariffs": tariffs}


DOMAIN = K.Domain("meters", "Lowmoor Utilities Co-op: meter readings", SCHEMA, DOC, gen)
S = K.Spec

INTERVALS = """WITH r AS (
  SELECT x.*, m.dial_max, m.kind, m.site_id, m.serial, LAG(x.value) OVER w AS prev_v, LAG(x.read_on) OVER w AS prev_on
  FROM readings x JOIN meters m ON m.meter_id = x.meter_id
  WINDOW w AS (PARTITION BY x.meter_id ORDER BY x.read_on, x.reading_id)
), iv AS (
  SELECT *, CASE WHEN value >= prev_v THEN value - prev_v ELSE value + dial_max + 1 - prev_v END AS used,
         (value < prev_v AND prev_v >= 0.9 * dial_max AND value <= 0.1 * dial_max) AS wrapped,
         (value < prev_v AND NOT (prev_v >= 0.9 * dial_max AND value <= 0.1 * dial_max)) AS fault
  FROM r WHERE prev_v IS NOT NULL
)"""

SPECS = [
    S("meters-per-site", 1, "For each site: the number of meters of each kind in one row: site name, electric meters, gas meters, water meters (zeros included). Order by site name.",
      "SELECT s.name AS site, SUM(m.kind = 'electric') AS electric, SUM(m.kind = 'gas') AS gas, SUM(m.kind = 'water') AS water FROM sites s LEFT JOIN meters m ON m.site_id = s.site_id GROUP BY s.site_id ORDER BY s.name;",
      ["site", "electric", "gas", "water"], ordered=True),
    S("latest-reading", 2,
      "The latest reading of every meter (latest date, ties by the higher reading id): serial, date, value and source. Meters without any reading are not listed. Order by serial.",
      "SELECT m.serial, x.read_on, x.value, x.source FROM meters m JOIN readings x ON x.meter_id = m.meter_id WHERE x.reading_id = (SELECT y.reading_id FROM readings y WHERE y.meter_id = m.meter_id ORDER BY y.read_on DESC, y.reading_id DESC LIMIT 1) ORDER BY m.serial;",
      ["serial", "read_on", "value", "source"], ordered=True),
    S("meter-faults", 3,
      "Find meter faults: readings where the counter went down although it did not genuinely wrap around the dial (see the notes on wrapping). Columns: serial, date, previous value, value. Order by serial, then date.",
      f"""{INTERVALS}
SELECT serial, read_on, prev_v AS previous, value FROM iv WHERE fault ORDER BY serial, read_on, reading_id;""",
      ["serial", "read_on", "previous", "value"], ordered=True, allow_empty=True,
      wrong=("""SELECT m.serial, x.read_on, 0, x.value FROM readings x JOIN meters m ON m.meter_id = x.meter_id WHERE x.value < (SELECT y.value FROM readings y WHERE y.meter_id = x.meter_id AND y.read_on < x.read_on ORDER BY y.read_on DESC LIMIT 1) ORDER BY m.serial, x.read_on;""",)),
    S("total-consumption", 3,
      "Total consumption per meter over all its intervals with rollover handled (genuine wraps use the wrap formula; meter faults are excluded from the totals): serial, kind, number of intervals counted, number of genuine wraps, total units. Order by serial.",
      f"""{INTERVALS}
SELECT serial, kind, COUNT(*) AS intervals, SUM(wrapped) AS wraps, SUM(used) AS total_units FROM iv WHERE NOT fault GROUP BY meter_id ORDER BY serial;""",
      ["serial", "kind", "intervals", "wraps", "total_units"], ordered=True,
      wrong=("""WITH r AS (SELECT x.*, LAG(x.value) OVER (PARTITION BY x.meter_id ORDER BY x.read_on, x.reading_id) AS pv FROM readings x)
SELECT m.serial, m.kind, COUNT(*), 0, SUM(r.value - r.pv) FROM r JOIN meters m ON m.meter_id = r.meter_id WHERE r.pv IS NOT NULL GROUP BY r.meter_id ORDER BY m.serial;""",)),
    S("monthly-by-site", 3,
      "Monthly electricity use per site: for the electric meters, add up the consumption of the intervals whose later reading falls in each month (faults excluded) and give site name, month (`YYYY-MM`) and total units. Order by month, then site name.",
      f"""{INTERVALS}
SELECT s.name AS site, substr(iv.read_on, 1, 7) AS month, SUM(iv.used) AS units FROM iv JOIN sites s ON s.site_id = iv.site_id WHERE iv.kind = 'electric' AND NOT iv.fault GROUP BY iv.site_id, month ORDER BY month, s.name;""",
      ["site", "month", "units"], ordered=True),
    S("cost-by-kind", 4,
      "Cost of the year: for each kind, total consumption (faults excluded) and the total cost in euros (2 decimals), pricing every interval with the tariff in force on the later reading's date. Intervals for which no tariff is in force are not priced "
      "(they count in the units but not in the cost); also report how many intervals had no tariff. Columns: kind, units, cost in euros, unpriced intervals. Order by kind.",
      f"""{INTERVALS}
SELECT iv.kind, SUM(iv.used) AS units, ROUND(SUM(iv.used * COALESCE(t.cents_per_unit, 0)) / 100.0, 2) AS cost_eur, SUM(t.tariff_id IS NULL) AS unpriced
FROM iv LEFT JOIN tariffs t ON t.kind = iv.kind AND t.valid_from <= iv.read_on AND (t.valid_to IS NULL OR iv.read_on <= t.valid_to) WHERE NOT iv.fault GROUP BY iv.kind ORDER BY iv.kind;""",
      ["kind", "units", "cost_eur", "unpriced"], ordered=True,
      wrong=(f"""{INTERVALS}
SELECT iv.kind, SUM(iv.used), ROUND(SUM(iv.used * t.cents_per_unit) / 100.0, 2), 0 FROM iv JOIN tariffs t ON t.kind = iv.kind AND t.valid_from <= iv.read_on AND (t.valid_to IS NULL OR iv.read_on < t.valid_to) WHERE NOT iv.fault GROUP BY iv.kind ORDER BY iv.kind;""",)),
    S("estimate-streaks", 4,
      "Meters read by estimate again and again: find runs of two or more consecutive readings of a meter (in date order, ties by reading id) whose source is `estimate`. Columns: serial, first date of the run, last date, number of readings. Order by serial, then first date.",
      """WITH s AS (SELECT meter_id, read_on, source, ROW_NUMBER() OVER (PARTITION BY meter_id ORDER BY read_on, reading_id) AS rn, ROW_NUMBER() OVER (PARTITION BY meter_id, source ORDER BY read_on, reading_id) AS rk FROM readings)
SELECT m.serial, MIN(s.read_on) AS first_on, MAX(s.read_on) AS last_on, COUNT(*) AS readings FROM s JOIN meters m ON m.meter_id = s.meter_id WHERE s.source = 'estimate' GROUP BY s.meter_id, s.rn - s.rk HAVING COUNT(*) >= 2 ORDER BY m.serial, first_on;""",
      ["serial", "first_on", "last_on", "readings"], ordered=True, allow_empty=True,
      wrong=("""SELECT m.serial, MIN(x.read_on), MAX(x.read_on), COUNT(*) FROM readings x JOIN meters m ON m.meter_id = x.meter_id WHERE x.source = 'estimate' GROUP BY x.meter_id HAVING COUNT(*) >= 2 ORDER BY m.serial, 2;""",)),
    S("missing-months", 4,
      "Months without a reading: for every electric meter, list the calendar months of 2036 (`2036-01` to `2036-12`) in which it has no reading at all. Columns: serial, month. Order by serial, then month.",
      """WITH RECURSIVE mo(m) AS (SELECT '2036-01' UNION ALL SELECT strftime('%Y-%m', m || '-01', '+1 month') FROM mo WHERE m < '2036-12')
SELECT t.serial, mo.m AS month FROM meters t CROSS JOIN mo WHERE t.kind = 'electric' AND NOT EXISTS (SELECT 1 FROM readings x WHERE x.meter_id = t.meter_id AND substr(x.read_on, 1, 7) = mo.m) ORDER BY t.serial, mo.m;""",
      ["serial", "month"], ordered=True, allow_empty=True,
      wrong=("""SELECT t.serial, substr(x.read_on, 1, 7) FROM meters t JOIN readings x ON x.meter_id = t.meter_id WHERE t.kind = 'electric' AND x.source = 'estimate' ORDER BY t.serial, 2;""",)),
    S("peak-daily-rate", 3,
      "For each site, which interval of an electric meter had the highest average use per day (units divided by the days between the two readings; faults excluded)? Ties go to the earlier later-reading date, then lower serial. "
      "Columns: site name, serial, later reading date, units per day with 2 decimals. Order by site name.",
      f"""{INTERVALS}
, p AS (SELECT iv.*, used * 1.0 / (julianday(read_on) - julianday(prev_on)) AS rate, ROW_NUMBER() OVER (PARTITION BY site_id ORDER BY used * 1.0 / (julianday(read_on) - julianday(prev_on)) DESC, read_on, serial) AS rn FROM iv WHERE kind = 'electric' AND NOT fault)
SELECT s.name AS site, p.serial, p.read_on, ROUND(p.rate, 2) AS per_day FROM p JOIN sites s ON s.site_id = p.site_id WHERE p.rn = 1 ORDER BY s.name;""",
      ["site", "serial", "read_on", "per_day"], ordered=True, places=2,
      wrong=(f"""{INTERVALS}
SELECT s.name, iv.serial, iv.read_on, ROUND(MAX(iv.used), 2) FROM iv JOIN sites s ON s.site_id = iv.site_id WHERE iv.kind = 'electric' AND NOT iv.fault GROUP BY iv.site_id ORDER BY s.name;""",)),
    S("rolling-quarter", 4,
      "Rolling three-month use: for each electric meter and each month in which it has an interval, total its intervals' units for that month (faults excluded) and add the totals of the two previous months that have data for that meter "
      "(just the previous rows in month order, not calendar neighbours). Report only the months where this rolling total exceeds 2000 units: serial, month, rolling units. Order by serial, month.",
      f"""{INTERVALS}
, mm AS (SELECT meter_id, serial, substr(read_on, 1, 7) AS month, SUM(used) AS u FROM iv WHERE kind = 'electric' AND NOT fault GROUP BY meter_id, month),
rr AS (SELECT serial, month, SUM(u) OVER (PARTITION BY meter_id ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS rolling FROM mm)
SELECT serial, month, rolling FROM rr WHERE rolling > 2000 ORDER BY serial, month;""",
      ["serial", "month", "rolling"], ordered=True,
      wrong=(f"""{INTERVALS}
, mm AS (SELECT meter_id, serial, substr(read_on, 1, 7) AS month, SUM(used) AS u FROM iv WHERE kind = 'electric' AND NOT fault GROUP BY meter_id, month),
rr AS (SELECT serial, month, SUM(u) OVER (PARTITION BY meter_id ORDER BY month ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS rolling FROM mm)
SELECT serial, month, rolling FROM rr WHERE rolling > 2000 ORDER BY serial, month;""",)),
    S("long-gaps", 2,
      "Meters that were not read for a long time: list every pair of consecutive readings (date order, ties by id) of one meter that are more than 45 days apart. Columns: serial, date of the earlier reading, date of the later, days between. Order by days between descending, then serial.",
      """WITH g AS (SELECT meter_id, read_on, LAG(read_on) OVER (PARTITION BY meter_id ORDER BY read_on, reading_id) AS prev FROM readings)
SELECT m.serial, g.prev AS from_on, g.read_on AS to_on, CAST(julianday(g.read_on) - julianday(g.prev) AS INTEGER) AS days FROM g JOIN meters m ON m.meter_id = g.meter_id WHERE g.prev IS NOT NULL AND julianday(g.read_on) - julianday(g.prev) > 45 ORDER BY days DESC, m.serial, from_on;""",
      ["serial", "from_on", "to_on", "days"], ordered=True, allow_empty=True),
    S("untariffed-readings", 3,
      "Readings that cannot be priced: readings (except the first of each meter) for which no tariff of the meter's kind is in force on the reading date. Columns: serial, reading date, kind. Order by kind, serial, date.",
      """WITH r AS (SELECT x.*, ROW_NUMBER() OVER (PARTITION BY x.meter_id ORDER BY x.read_on, x.reading_id) AS rn FROM readings x)
SELECT m.serial, r.read_on, m.kind FROM r JOIN meters m ON m.meter_id = r.meter_id WHERE r.rn > 1 AND NOT EXISTS (SELECT 1 FROM tariffs t WHERE t.kind = m.kind AND t.valid_from <= r.read_on AND (t.valid_to IS NULL OR r.read_on <= t.valid_to)) ORDER BY m.kind, m.serial, r.read_on;""",
      ["serial", "read_on", "kind"], ordered=True, allow_empty=True),
    S("fix-wrap-consumption", 3,
      "The consumption report in `query.sql` shows negative numbers whenever a dial wraps past its maximum. Fix it: for each meter, the total consumption over all consecutive reading pairs (date order, ties by reading id), "
      "where a smaller value than before is a wrap (consumption `value + dial_max + 1 - previous`). Treat every decrease as a wrap here. Columns: serial, total units. Order by serial.",
      ref="""WITH r AS (SELECT x.meter_id, x.value, LAG(x.value) OVER (PARTITION BY x.meter_id ORDER BY x.read_on, x.reading_id) AS pv FROM readings x)
SELECT m.serial, SUM(CASE WHEN r.value >= r.pv THEN r.value - r.pv ELSE r.value + m.dial_max + 1 - r.pv END) AS total_units FROM r JOIN meters m ON m.meter_id = r.meter_id WHERE r.pv IS NOT NULL GROUP BY r.meter_id ORDER BY m.serial;""",
      cols=["serial", "total_units"], ordered=True, show=False,
      buggy="""WITH r AS (SELECT x.meter_id, x.value, LAG(x.value) OVER (PARTITION BY x.meter_id ORDER BY x.read_on, x.reading_id) AS pv FROM readings x)
SELECT m.serial, SUM(r.value - r.pv) AS total_units FROM r JOIN meters m ON m.meter_id = r.meter_id WHERE r.pv IS NOT NULL GROUP BY r.meter_id ORDER BY m.serial;"""),
]


@family("data-meter-readings", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL on utility meter readings: cumulative counters with rollover and faults, tariff periods, estimate streaks, missing months, rolling sums")
def meter_readings(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
