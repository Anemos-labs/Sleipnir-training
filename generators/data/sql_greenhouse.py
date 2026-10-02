"""SQL tasks on an invented greenhouse's irrigation events and sensor readings (durations, dry spells, readings before and after events, daily tops, trailing averages)."""
from datetime import datetime, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE zones (
      zone_id   INTEGER PRIMARY KEY,
      name      TEXT NOT NULL UNIQUE,
      crop      TEXT NOT NULL,
      area_m2   INTEGER NOT NULL
    );
    CREATE TABLE valves (
      valve_id  INTEGER PRIMARY KEY,
      zone_id   INTEGER NOT NULL REFERENCES zones(zone_id),
      label     TEXT NOT NULL UNIQUE,
      flow_lpm  REAL NOT NULL                 -- litres per minute while open
    );
    CREATE TABLE events (
      event_id   INTEGER PRIMARY KEY,
      valve_id   INTEGER NOT NULL REFERENCES valves(valve_id),
      opened_at  TEXT NOT NULL,               -- YYYY-MM-DD HH:MM
      closed_at  TEXT,                        -- NULL while the valve is still open
      trigger    TEXT NOT NULL CHECK (trigger IN ('timer', 'moisture', 'manual'))
    );
    CREATE TABLE readings (
      reading_id    INTEGER PRIMARY KEY,
      zone_id       INTEGER NOT NULL REFERENCES zones(zone_id),
      taken_at      TEXT NOT NULL,
      moisture_pct  REAL NOT NULL,
      temp_c        REAL NOT NULL
    );
    CREATE TABLE alerts (
      alert_id    INTEGER PRIMARY KEY,
      zone_id     INTEGER NOT NULL REFERENCES zones(zone_id),
      raised_at   TEXT NOT NULL,
      kind        TEXT NOT NULL CHECK (kind IN ('dry', 'hot', 'leak')),
      cleared_at  TEXT                        -- NULL while the alert is open
    );
''')

DOC = dd('''
    The Fernholt Growers' greenhouse is split into zones with their own irrigation valves and sensors.

    * An **event** is one watering by one valve from `opened_at` to `closed_at`. The **volume** of a closed event is `flow_lpm x minutes open`. An event with `closed_at` NULL is still running: it has no volume yet.
    * A **reading** is a sensor sample of a zone. Soil moisture should stay between 35 and 60 percent; a reading below 35 is *dry*. A temperature above 32 degrees is *hot*.
    * An **alert** is raised for a zone and stays open until `cleared_at`.
    * Timestamps are `YYYY-MM-DD HH:MM` text. The report time is **2039-06-20 12:00**.
''')

CROPS = [("tomatoes", 90), ("basil", 40), ("peppers", 70), ("cucumbers", 60), ("lettuce", 55)]


def gen(rng, big):
    nz = 5 if big else 3
    zones = [(i + 1, f"Bay {chr(65 + i)}", rng.choice(CROPS)[0], rng.choice([40, 55, 60, 70, 90, 120])) for i in range(nz)]
    valves = []
    for z in zones:
        for k in range(rng.choice([2, 2, 3])):
            valves.append((len(valves) + 1, z[0], f"V{z[0]}{chr(97 + k)}", rng.choice([6.0, 8.5, 10.0, 12.5, 15.0])))
    days = [datetime(2039, 6, 6) + timedelta(days=d) for d in range(15 if big else 6)]
    events, readings, alerts = [], [], []
    eid = rid = aid = 0
    for z in zones:
        m = 31.0 if z[0] == 1 else rng.uniform(25, 50)
        for day in days:
            t = day + timedelta(hours=rng.randint(0, 2), minutes=rng.randint(0, 59))
            while t < day + timedelta(days=1):
                m = max(15.0, min(75.0, m - rng.uniform(0.2, 1.4) + (rng.uniform(8, 25) if rng.random() < 0.05 else 0)))
                rid += 1
                readings.append((rid, z[0], t.strftime("%Y-%m-%d %H:%M"), round(m, 1), round(rng.uniform(17, 36), 1)))
                t += timedelta(minutes=rng.choice([30, 45, 60, 90, 120]))
        # events
        for v in [v for v in valves if v[1] == z[0]]:
            for day in days:
                for _ in range(rng.choice([0, 1, 1, 2])):
                    eid += 1
                    o = day + timedelta(hours=rng.choice([5, 6, 12, 18, 19]), minutes=rng.choice([0, 15, 30, 45]))
                    c = o + timedelta(minutes=rng.choice([10, 15, 20, 30, 45]))
                    if o > datetime(2039, 6, 20, 12, 0):
                        continue
                    events.append((eid, v[0], o.strftime("%Y-%m-%d %H:%M"), c.strftime("%Y-%m-%d %H:%M") if c <= datetime(2039, 6, 20, 12, 0) else None, rng.choice(["timer", "timer", "moisture", "manual"])))
        for _ in range(rng.randint(1, 3)):
            aid += 1
            r = datetime(2039, 6, rng.randint(6, 19), rng.randint(0, 23), rng.choice([0, 15, 30, 45]))
            cleared = None if rng.random() < 0.3 else (r + timedelta(hours=rng.choice([1, 2, 5, 9, 26]))).strftime("%Y-%m-%d %H:%M")
            alerts.append((aid, z[0], r.strftime("%Y-%m-%d %H:%M"), rng.choice(["dry", "hot", "leak"]), cleared))
    # plant: a valve still open since the early morning, two events on one valve that overlap, two events 5 minutes apart, a leaking valve with a huge day
    eid += 1
    events.append((eid, rng.choice(valves)[0], f"2039-06-20 0{rng.randint(1, 7)}:{rng.choice(['00', '15', '30', '45'])}", None, "manual"))
    eid += 1
    events.append((eid, valves[1][0], "2039-06-12 07:00", "2039-06-12 07:40", "timer"))
    eid += 1
    events.append((eid, valves[1][0], "2039-06-12 07:30", "2039-06-12 07:50", "manual"))
    eid += 1
    events.append((eid, valves[2][0], "2039-06-13 06:00", "2039-06-13 06:20", "timer"))
    eid += 1
    events.append((eid, valves[2][0], "2039-06-13 06:25", "2039-06-13 06:40", "timer"))
    for k in range(3):
        eid += 1
        events.append((eid, valves[3][0], f"2039-06-18 {8 + 2 * k:02d}:00", f"2039-06-18 {9 + 2 * k:02d}:50", "manual"))
    return {"zones": zones, "valves": valves, "events": events, "readings": readings, "alerts": alerts}


DOMAIN = K.Domain("greenhouse", "Fernholt Growers: irrigation and sensors", SCHEMA, DOC, gen)
S = K.Spec

MINUTES = "(julianday(e.closed_at) - julianday(e.opened_at)) * 1440"

SPECS = [
    S("zones-by-crop", 1, "Every zone with its crop, area and number of valves. Columns: zone name, crop, area_m2, valves. Order by area descending, then zone name.",
      "SELECT z.name AS zone, z.crop, z.area_m2, COUNT(v.valve_id) AS valves FROM zones z LEFT JOIN valves v ON v.zone_id = z.zone_id GROUP BY z.zone_id ORDER BY z.area_m2 DESC, z.name;", ["zone", "crop", "area_m2", "valves"], ordered=True),
    S("water-per-zone", 2,
      f"Water used per zone from 2039-06-10 to 2039-06-16 (events that opened on those dates, both days included; only closed events have a volume): zone name, number of events, total litres (1 decimal) and litres per square metre (2 decimals). Order by litres per m2 descending, then zone name.",
      f"""SELECT z.name AS zone, COUNT(*) AS events, ROUND(SUM({MINUTES} * v.flow_lpm), 1) AS litres, ROUND(SUM({MINUTES} * v.flow_lpm) / z.area_m2, 2) AS litres_per_m2
FROM events e JOIN valves v ON v.valve_id = e.valve_id JOIN zones z ON z.zone_id = v.zone_id WHERE e.closed_at IS NOT NULL AND e.opened_at >= '2039-06-10' AND e.opened_at < '2039-06-17' GROUP BY z.zone_id ORDER BY litres_per_m2 DESC, z.name;""",
      ["zone", "events", "litres", "litres_per_m2"], ordered=True, places=2,
      wrong=(f"""SELECT z.name, COUNT(*), ROUND(SUM({MINUTES} * v.flow_lpm), 1), ROUND(SUM({MINUTES} * v.flow_lpm) / z.area_m2, 2) AS l FROM events e JOIN valves v ON v.valve_id = e.valve_id JOIN zones z ON z.zone_id = v.zone_id WHERE e.closed_at IS NOT NULL AND e.opened_at >= '2039-06-10' AND e.opened_at <= '2039-06-16' GROUP BY z.zone_id ORDER BY l DESC, z.name;""",)),
    S("valves-left-open", 2,
      "Valves that have been open for 4 hours or more at the report time (2039-06-20 12:00): events with no `closed_at`. Columns: valve label, zone name, opened at, hours open with 1 decimal. Longest first, ties by label.",
      """SELECT v.label AS valve, z.name AS zone, e.opened_at, ROUND((julianday('2039-06-20 12:00') - julianday(e.opened_at)) * 24, 1) AS hours_open FROM events e JOIN valves v ON v.valve_id = e.valve_id JOIN zones z ON z.zone_id = v.zone_id
WHERE e.closed_at IS NULL AND (julianday('2039-06-20 12:00') - julianday(e.opened_at)) * 24 >= 4 ORDER BY hours_open DESC, v.label;""",
      ["valve", "zone", "opened_at", "hours_open"], ordered=True, places=1),
    S("dry-share", 2,
      "Share of dry readings per zone: number of readings, number below 35 percent moisture and the share in percent with 1 decimal. Order by share descending, then zone name.",
      "SELECT z.name AS zone, COUNT(*) AS readings, SUM(r.moisture_pct < 35) AS dry, ROUND(100.0 * SUM(r.moisture_pct < 35) / COUNT(*), 1) AS dry_pct FROM readings r JOIN zones z ON z.zone_id = r.zone_id GROUP BY z.zone_id ORDER BY dry_pct DESC, z.name;",
      ["zone", "readings", "dry", "dry_pct"], ordered=True),
    S("longest-dry-spell", 4,
      "Dry spells: for each zone find runs of consecutive readings (time order, ties by id) below 35 percent moisture. Report each zone's longest run: zone name, number of readings in it, time of its first reading, time of its last (the earliest such run if several tie). "
      "Zones with no dry reading are not listed. Order by run length descending, then zone name.",
      """WITH r AS (SELECT zone_id, taken_at, moisture_pct < 35 AS dry, ROW_NUMBER() OVER (PARTITION BY zone_id ORDER BY taken_at, reading_id) AS rn, ROW_NUMBER() OVER (PARTITION BY zone_id, moisture_pct < 35 ORDER BY taken_at, reading_id) AS rk FROM readings),
s AS (SELECT zone_id, COUNT(*) AS len, MIN(taken_at) AS first_at, MAX(taken_at) AS last_at FROM r WHERE dry = 1 GROUP BY zone_id, rn - rk), b AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY zone_id ORDER BY len DESC, first_at) AS x FROM s)
SELECT z.name AS zone, b.len, b.first_at, b.last_at FROM b JOIN zones z ON z.zone_id = b.zone_id WHERE b.x = 1 ORDER BY b.len DESC, z.name;""",
      ["zone", "len", "first_at", "last_at"], ordered=True,
      wrong=("""SELECT z.name, COUNT(*), MIN(r.taken_at), MAX(r.taken_at) FROM readings r JOIN zones z ON z.zone_id = r.zone_id WHERE r.moisture_pct < 35 GROUP BY z.zone_id ORDER BY 2 DESC, z.name;""",)),
    S("moisture-response", 4,
      "Does moisture-triggered watering work? For every closed event with trigger `moisture`, take the moisture of the zone's latest reading at or before the opening time (`before`) and of its earliest reading at least 30 minutes after the closing time (`after`); "
      "events missing either reading are ignored. Report per zone the number of such events and the average gain (after minus before) with 2 decimals. Order by gain descending, then zone name.",
      """WITH m AS (SELECT z.zone_id, (SELECT r.moisture_pct FROM readings r WHERE r.zone_id = z.zone_id AND r.taken_at <= e.opened_at ORDER BY r.taken_at DESC, r.reading_id DESC LIMIT 1) AS before_m,
  (SELECT r.moisture_pct FROM readings r WHERE r.zone_id = z.zone_id AND julianday(r.taken_at) >= julianday(e.closed_at) + 30.0 / 1440 - 1e-9 ORDER BY r.taken_at, r.reading_id LIMIT 1) AS after_m
  FROM events e JOIN valves v ON v.valve_id = e.valve_id JOIN zones z ON z.zone_id = v.zone_id WHERE e.trigger = 'moisture' AND e.closed_at IS NOT NULL)
SELECT z.name AS zone, COUNT(*) AS events, ROUND(AVG(after_m - before_m), 2) AS avg_gain FROM m JOIN zones z ON z.zone_id = m.zone_id WHERE before_m IS NOT NULL AND after_m IS NOT NULL GROUP BY m.zone_id ORDER BY avg_gain DESC, z.name;""",
      ["zone", "events", "avg_gain"], ordered=True, places=2,
      wrong=("""WITH m AS (SELECT z.zone_id, (SELECT r.moisture_pct FROM readings r WHERE r.zone_id = z.zone_id AND r.taken_at <= e.opened_at ORDER BY r.taken_at DESC LIMIT 1) AS before_m, (SELECT r.moisture_pct FROM readings r WHERE r.zone_id = z.zone_id AND r.taken_at > e.closed_at ORDER BY r.taken_at LIMIT 1) AS after_m FROM events e JOIN valves v ON v.valve_id = e.valve_id JOIN zones z ON z.zone_id = v.zone_id WHERE e.trigger = 'moisture' AND e.closed_at IS NOT NULL)
SELECT z.name, COUNT(*), ROUND(AVG(after_m - before_m), 2) AS g FROM m JOIN zones z ON z.zone_id = m.zone_id WHERE before_m IS NOT NULL AND after_m IS NOT NULL GROUP BY m.zone_id ORDER BY g DESC, z.name;""",)),
    S("overlapping-events", 3,
      "Data check: pairs of events of the same valve whose open periods overlap (event b opens before event a closes and a opens before b closes; events that are still open count as open until the report time 2039-06-20 12:00). "
      "Report each pair once with the lower event id first: valve label, the two ids, minutes of overlap (whole minutes). Order by valve label, then the first id.",
      """WITH e AS (SELECT event_id, valve_id, opened_at, COALESCE(closed_at, '2039-06-20 12:00') AS closed FROM events)
SELECT v.label AS valve, a.event_id AS event_a, b.event_id AS event_b, CAST(ROUND((julianday(MIN(a.closed, b.closed)) - julianday(MAX(a.opened_at, b.opened_at))) * 1440) AS INTEGER) AS overlap_min
FROM e a JOIN e b ON b.valve_id = a.valve_id AND b.event_id > a.event_id AND b.opened_at < a.closed AND a.opened_at < b.closed JOIN valves v ON v.valve_id = a.valve_id ORDER BY v.label, a.event_id, b.event_id;""",
      ["valve", "event_a", "event_b", "overlap_min"], ordered=True, allow_empty=True,
      wrong=("""SELECT v.label, a.event_id, b.event_id, 0 FROM events a JOIN events b ON b.valve_id = a.valve_id AND b.event_id > a.event_id AND b.opened_at < a.closed_at AND a.opened_at < b.closed_at JOIN valves v ON v.valve_id = a.valve_id ORDER BY v.label, a.event_id, b.event_id;""",)),
    S("top-zone-per-day", 3,
      "For every day on which any closed event opened, the zone that received the most water that day (litres summed over the day's closed events of all its valves; ties go to the lower zone id): day, zone name, litres with 1 decimal. Order by day.",
      f"""WITH d AS (SELECT substr(e.opened_at, 1, 10) AS day, v.zone_id, SUM({MINUTES} * v.flow_lpm) AS litres FROM events e JOIN valves v ON v.valve_id = e.valve_id WHERE e.closed_at IS NOT NULL GROUP BY day, v.zone_id),
r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY day ORDER BY litres DESC, zone_id) AS rn FROM d)
SELECT r.day, z.name AS zone, ROUND(r.litres, 1) AS litres FROM r JOIN zones z ON z.zone_id = r.zone_id WHERE r.rn = 1 ORDER BY r.day;""",
      ["day", "zone", "litres"], ordered=True, places=1,
      wrong=(f"""SELECT substr(e.opened_at, 1, 10), z.name, ROUND(MAX({MINUTES} * v.flow_lpm), 1) FROM events e JOIN valves v ON v.valve_id = e.valve_id JOIN zones z ON z.zone_id = v.zone_id WHERE e.closed_at IS NOT NULL GROUP BY substr(e.opened_at, 1, 10) ORDER BY 1;""",)),
    S("alert-durations", 3,
      "Alert handling per kind: the number of alerts raised, how many are still open, and the average time to clear in hours (1 decimal) over the cleared ones (NULL if none was cleared). Order by kind.",
      "SELECT kind, COUNT(*) AS raised, SUM(cleared_at IS NULL) AS still_open, ROUND(AVG((julianday(cleared_at) - julianday(raised_at)) * 24), 1) AS avg_hours FROM alerts GROUP BY kind ORDER BY kind;",
      ["kind", "raised", "still_open", "avg_hours"], ordered=True,
      wrong=("SELECT kind, COUNT(*), SUM(cleared_at IS NULL), ROUND(AVG((julianday(COALESCE(cleared_at, '2039-06-20 12:00')) - julianday(raised_at)) * 24), 1) FROM alerts GROUP BY kind ORDER BY kind;",)),
    S("leak-suspects", 5,
      "Leak suspects: for every valve add up the litres of its closed events per day, and compare each day with the average of the valve's previous 7 days **that have events** (the 7 rows before it in date order, fewer at the start; the first day has nothing to compare). "
      "List the valve-days where the day's litres are more than twice that trailing average: valve label, day, litres (1 decimal), trailing average (1 decimal). Order by day, then valve label.",
      f"""WITH d AS (SELECT e.valve_id, substr(e.opened_at, 1, 10) AS day, SUM({MINUTES} * v.flow_lpm) AS litres FROM events e JOIN valves v ON v.valve_id = e.valve_id WHERE e.closed_at IS NOT NULL GROUP BY e.valve_id, day),
t AS (SELECT *, AVG(litres) OVER (PARTITION BY valve_id ORDER BY day ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING) AS trailing FROM d)
SELECT v.label AS valve, t.day, ROUND(t.litres, 1) AS litres, ROUND(t.trailing, 1) AS trailing_avg FROM t JOIN valves v ON v.valve_id = t.valve_id WHERE t.trailing IS NOT NULL AND t.litres > 2 * t.trailing ORDER BY t.day, v.label;""",
      ["valve", "day", "litres", "trailing_avg"], ordered=True, places=1, allow_empty=True,
      wrong=(f"""WITH d AS (SELECT e.valve_id, substr(e.opened_at, 1, 10) AS day, SUM({MINUTES} * v.flow_lpm) AS litres FROM events e JOIN valves v ON v.valve_id = e.valve_id WHERE e.closed_at IS NOT NULL GROUP BY e.valve_id, day),
t AS (SELECT *, AVG(litres) OVER (PARTITION BY valve_id ORDER BY day ROWS BETWEEN 7 PRECEDING AND CURRENT ROW) AS trailing FROM d)
SELECT v.label, t.day, ROUND(t.litres, 1), ROUND(t.trailing, 1) FROM t JOIN valves v ON v.valve_id = t.valve_id WHERE t.litres > 2 * t.trailing ORDER BY t.day, v.label;""",)),
    S("hottest-hour", 3,
      "For each zone, the hour of the day (0 to 23) with the highest average temperature over all its readings (ties go to the earlier hour): zone name, hour, average temperature with 1 decimal. Order by zone name.",
      """WITH h AS (SELECT zone_id, CAST(substr(taken_at, 12, 2) AS INTEGER) AS hour, AVG(temp_c) AS avg_t FROM readings GROUP BY zone_id, hour), r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY zone_id ORDER BY avg_t DESC, hour) AS rn FROM h)
SELECT z.name AS zone, r.hour, ROUND(r.avg_t, 1) AS avg_temp FROM r JOIN zones z ON z.zone_id = r.zone_id WHERE r.rn = 1 ORDER BY z.name;""",
      ["zone", "hour", "avg_temp"], ordered=True, places=1,
      wrong=("""SELECT z.name, CAST(substr(r.taken_at, 12, 2) AS INTEGER), MAX(r.temp_c) FROM readings r JOIN zones z ON z.zone_id = r.zone_id GROUP BY z.zone_id ORDER BY z.name;""",)),
    S("back-to-back-waterings", 3,
      "Waterings that could be merged: consecutive closed events of the same valve (by opening time) where the next one opens less than 10 minutes after the previous one closed (a negative gap is an overlap and also counts). "
      "Columns: valve label, the earlier event id, the later event id, gap in minutes (negative for overlaps). Order by valve label, then the earlier id.",
      """WITH x AS (SELECT valve_id, event_id, opened_at, closed_at, LAG(event_id) OVER w AS prev_id, LAG(closed_at) OVER w AS prev_closed FROM events WHERE closed_at IS NOT NULL WINDOW w AS (PARTITION BY valve_id ORDER BY opened_at, event_id))
SELECT v.label AS valve, x.prev_id AS first_id, x.event_id AS second_id, CAST(ROUND((julianday(x.opened_at) - julianday(x.prev_closed)) * 1440) AS INTEGER) AS gap_min FROM x JOIN valves v ON v.valve_id = x.valve_id
WHERE x.prev_id IS NOT NULL AND (julianday(x.opened_at) - julianday(x.prev_closed)) * 1440 < 9.5 ORDER BY v.label, x.prev_id;""",
      ["valve", "first_id", "second_id", "gap_min"], ordered=True, allow_empty=True,
      wrong=("""WITH x AS (SELECT valve_id, event_id, opened_at, closed_at, LAG(event_id) OVER w AS prev_id, LAG(closed_at) OVER w AS prev_closed FROM events WINDOW w AS (PARTITION BY valve_id ORDER BY opened_at, event_id))
SELECT v.label, x.prev_id, x.event_id, CAST(ROUND((julianday(x.opened_at) - julianday(x.prev_closed)) * 1440) AS INTEGER) FROM x JOIN valves v ON v.valve_id = x.valve_id WHERE x.prev_id IS NOT NULL AND (julianday(x.opened_at) - julianday(x.prev_closed)) * 1440 BETWEEN 0 AND 9.5 ORDER BY v.label, x.prev_id;""",)),
    S("fix-litres-per-zone", 3,
      "The litres report in `query.sql` counts events that are still running (they have no closing time) and multiplies the flow by the number of events instead of by the minutes the valve was open. "
      "Fix it: for every zone (also zones without events, with 0 litres) the total litres of its CLOSED events, `flow_lpm x minutes open`, rounded to 1 decimal. Columns: zone name, litres. Order by litres descending, then zone name.",
      ref=f"""SELECT z.name AS zone, ROUND(COALESCE(SUM({MINUTES} * v.flow_lpm), 0), 1) AS litres FROM zones z LEFT JOIN valves v ON v.zone_id = z.zone_id LEFT JOIN events e ON e.valve_id = v.valve_id AND e.closed_at IS NOT NULL GROUP BY z.zone_id ORDER BY litres DESC, z.name;""",
      cols=["zone", "litres"], ordered=True, places=1, show=False,
      buggy="""SELECT z.name AS zone, ROUND(SUM(v.flow_lpm) * COUNT(e.event_id), 1) AS litres FROM zones z JOIN valves v ON v.zone_id = z.zone_id JOIN events e ON e.valve_id = v.valve_id GROUP BY z.zone_id ORDER BY litres DESC, z.name;"""),
]


@family("data-greenhouse-log", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL on greenhouse irrigation logs: event durations and volumes, dry spells, readings before and after events, daily tops, trailing averages for leak detection")
def greenhouse_log(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
