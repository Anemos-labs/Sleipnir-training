"""SQL tasks on an invented tram operator's timetable, run log and workshop faults (delays, skipped stops, bunching, load profiles, medians)."""
from datetime import date, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE lines (
      line_id  INTEGER PRIMARY KEY,
      code     TEXT NOT NULL UNIQUE,
      colour   TEXT NOT NULL
    );
    CREATE TABLE stops (
      stop_id  INTEGER PRIMARY KEY,
      name     TEXT NOT NULL UNIQUE,
      zone     INTEGER NOT NULL
    );
    CREATE TABLE trams (
      tram_id     INTEGER PRIMARY KEY,
      fleet_no    TEXT NOT NULL UNIQUE,
      model       TEXT NOT NULL,
      built_year  INTEGER NOT NULL,
      depot       TEXT NOT NULL
    );
    CREATE TABLE runs (
      run_id           INTEGER PRIMARY KEY,
      line_id          INTEGER NOT NULL REFERENCES lines(line_id),
      tram_id          INTEGER NOT NULL REFERENCES trams(tram_id),
      service_date     TEXT NOT NULL,            -- YYYY-MM-DD
      direction        TEXT NOT NULL CHECK (direction IN ('out', 'in')),
      scheduled_start  TEXT NOT NULL,            -- HH:MM
      cancelled        INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE stop_events (
      event_id    INTEGER PRIMARY KEY,
      run_id      INTEGER NOT NULL REFERENCES runs(run_id),
      seq         INTEGER NOT NULL,              -- position of the stop on this run, 1 = first
      stop_id     INTEGER NOT NULL REFERENCES stops(stop_id),
      sched_time  TEXT NOT NULL,                 -- HH:MM
      actual_time TEXT,                          -- HH:MM, NULL when the tram skipped the stop
      boarded     INTEGER NOT NULL,
      alighted    INTEGER NOT NULL,
      UNIQUE (run_id, seq)
    );
    CREATE TABLE faults (
      fault_id     INTEGER PRIMARY KEY,
      tram_id      INTEGER NOT NULL REFERENCES trams(tram_id),
      reported_on  TEXT NOT NULL,
      fixed_on     TEXT,                         -- NULL while open
      category     TEXT NOT NULL,
      severity     INTEGER NOT NULL              -- 1 minor .. 5 withdraws the tram
    );
''')

DOC = dd('''
    The Karst Valley tram operator logs every timetabled trip (a **run**) and every stop made on it.

    * A run belongs to one line and one tram on one service date and goes `out` or `in`. `cancelled = 1` means it did not run; cancelled runs have no stop events.
    * A **stop event** has the scheduled time and the actual time. Both are `HH:MM` on the service date (no run crosses midnight). `actual_time` is NULL when the tram skipped the stop.
    * **Delay** = actual minus scheduled, in minutes (negative = early). A stop is **late** when its delay is more than 3 minutes. Skipped stops have no delay.
    * `faults` are workshop reports for a tram; `fixed_on` is NULL while the fault is open. Severity 4 or 5 is serious.
    * Reports use **2032-03-15** as "today".
''')

LINES = [("T1", "red"), ("T2", "green"), ("T3", "blue"), ("T4", "amber")]
STOPS = ["Alder Gate", "Brickworks", "Cinder Row", "Dovecote", "Eel Wharf", "Foundry Lane", "Gasometer", "Hop Market", "Ironbridge", "Jetty Road", "Kiln Park", "Lamplighter", "Mill Pond", "Nettle Cross"]
MODELS = ["Vega-3", "Vega-3", "Orion-5", "Heritage-60"]
DEPOTS = ["North", "South"]
CATS = ["doors", "pantograph", "brakes", "heating", "ticketing"]


def hm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def mins(s):
    return int(s[:2]) * 60 + int(s[3:])


def gen(rng, big):
    nl = 4 if big else 2
    lines = [(i + 1, LINES[i][0], LINES[i][1]) for i in range(nl)]
    stops = [(i + 1, STOPS[i], 1 + i // 5) for i in range(len(STOPS))]
    nt = 12 if big else 5
    trams = [(i + 1, f"{rng.choice([4, 5, 6])}{i + 1:02d}", rng.choice(MODELS), rng.randint(1998, 2024), DEPOTS[i % 2]) for i in range(nt)]
    routes = {}
    for ln in lines:
        k = rng.randint(6, 8) if big else rng.randint(4, 5)
        routes[ln[0]] = rng.sample(range(1, len(STOPS) + 1), k)
    runs, events, rid, eid = [], [], 0, 0
    days = [date(2032, 3, 9) + timedelta(days=d) for d in range(7 if big else 3)]
    for day in days:
        for ln in lines:
            for direction in ("out", "in"):
                for start in rng.sample([6 * 60, 6 * 60 + 50, 7 * 60 + 10, 8 * 60 + 20, 11 * 60 + 52, 12 * 60, 17 * 60 + 5, 17 * 60 + 49, 18 * 60 + 15], 4 if big else 3):
                    rid += 1
                    tram = rng.choice(trams)[0]
                    cancelled = 1 if rng.random() < 0.08 else 0
                    runs.append((rid, ln[0], tram, day.isoformat(), direction, hm(start), cancelled))
                    if cancelled:
                        continue
                    route = routes[ln[0]] if direction == "out" else routes[ln[0]][::-1]
                    t, delay = start, rng.choice([0, 0, 1, 2])
                    load = 0
                    for seq, sid in enumerate(route, 1):
                        eid += 1
                        sched = t
                        delay = max(-2, delay + rng.choice([-1, 0, 0, 1, 1, 2, 3]))
                        skipped = 1 if (0 < seq < len(route) and rng.random() < 0.07) else 0
                        board = 0 if skipped else rng.randint(0, 14)
                        alight = 0 if skipped else min(load, rng.randint(0, 12))
                        load += board - alight
                        events.append((eid, rid, seq, sid, hm(sched), None if skipped else hm(sched + delay), board, alight))
                        t += rng.choice([3, 4, 4, 5])
    # plant: one stop is skipped three times (it must not be a terminus), whatever the random walk did
    inner = [e for e in events if e[2] > 1 and any(r[0] == e[1] for r in runs)]
    from collections import Counter
    top = Counter(e[3] for e in inner).most_common(1)[0][0]
    hit = [i for i, e in enumerate(events) if e[3] == top and e[2] > 1][:3]
    for i in hit:
        e = events[i]
        events[i] = (e[0], e[1], e[2], e[3], e[4], None, 0, 0)
    faults, fid = [], 0
    for tr in trams:
        for _ in range(rng.choice([0, 1, 2, 3]) if big else rng.choice([0, 1, 2])):
            fid += 1
            rep = date(2032, 1, 5) + timedelta(days=rng.randint(0, 70))
            fixed = None if rng.random() < 0.3 else (rep + timedelta(days=rng.choice([0, 1, 2, 3, 5, 8, 13]))).isoformat()
            faults.append((fid, tr[0], rep.isoformat(), fixed, rng.choice(CATS), rng.randint(1, 5)))
    if big:
        base = date(2032, 2, 10)
        for k, off in enumerate((0, 9, 20, 40)):  # three doors faults within 30 days on tram 1, a fourth later
            fid += 1
            faults.append((fid, 1, (base + timedelta(days=off)).isoformat(), (base + timedelta(days=off + 2)).isoformat(), "doors", 2))
        for off in (0, 35, 70):  # three brake faults, but more than 30 days between the first and the third
            fid += 1
            faults.append((fid, 3, (base + timedelta(days=off)).isoformat(), (base + timedelta(days=off + 1)).isoformat(), "brakes", 3))
        fid += 1
        faults.append((fid, 2, "2032-03-01", "2032-03-01", "heating", 1))  # fixed the day it was reported
    for tid, rep, fix in ((trams[0][0], "2032-02-01", "2032-02-04"), (trams[1][0], "2032-02-10", "2032-02-12"), (trams[0][0], "2032-02-20", "2032-02-27")):
        fid += 1
        faults.append((fid, tid, rep, fix, "doors", 2))
    return {"lines": lines, "stops": stops, "trams": trams, "runs": runs, "stop_events": events, "faults": faults}


DOMAIN = K.Domain("tramdepot", "Karst Valley trams: timetable run log and workshop", SCHEMA, DOC, gen)
S = K.Spec

MIN = "(CAST(substr({0}, 1, 2) AS INTEGER) * 60 + CAST(substr({0}, 4, 2) AS INTEGER))"
DELAY = f"({MIN.format('e.actual_time')} - {MIN.format('e.sched_time')})"

SPECS = [
    S("fleet-by-depot", 1,
      "Fleet summary per depot: depot, number of trams, and the average build year rounded to 1 decimal. Order by depot.",
      "SELECT depot, COUNT(*) AS trams, ROUND(AVG(built_year), 1) AS avg_year FROM trams GROUP BY depot ORDER BY depot;",
      ["depot", "trams", "avg_year"], ordered=True),
    S("late-share-per-line", 2,
      "For each line: the number of stop events that were made (not skipped), how many of them were late, and the late share as a percentage rounded to 1 decimal. Skipped stops are neither late nor counted. Order by line code.",
      f"""SELECT l.code AS line, COUNT(*) AS made, SUM({DELAY} > 3) AS late, ROUND(100.0 * SUM({DELAY} > 3) / COUNT(*), 1) AS late_pct
FROM stop_events e JOIN runs r ON r.run_id = e.run_id JOIN lines l ON l.line_id = r.line_id
WHERE e.actual_time IS NOT NULL
GROUP BY l.line_id ORDER BY l.code;""",
      ["line", "made", "late", "late_pct"], ordered=True,
      wrong=(f"""SELECT l.code, COUNT(*), SUM({DELAY} >= 3), ROUND(100.0 * SUM({DELAY} >= 3) / COUNT(*), 1) FROM stop_events e JOIN runs r ON r.run_id = e.run_id JOIN lines l ON l.line_id = r.line_id WHERE e.actual_time IS NOT NULL GROUP BY l.line_id ORDER BY l.code;""",
             f"""SELECT l.code, COUNT(*), SUM(CASE WHEN e.actual_time IS NOT NULL AND {DELAY} > 3 THEN 1 ELSE 0 END), ROUND(100.0 * SUM(CASE WHEN e.actual_time IS NOT NULL AND {DELAY} > 3 THEN 1 ELSE 0 END) / COUNT(*), 1) FROM stop_events e JOIN runs r ON r.run_id = e.run_id JOIN lines l ON l.line_id = r.line_id GROUP BY l.line_id ORDER BY l.code;""")),
    S("skip-hotspots", 2,
      "Which stops get skipped the most? List the stops where trams skipped at least 2 events: stop name and the number of skipped events, most first, ties by stop name.",
      """SELECT s.name AS stop, COUNT(*) AS skipped FROM stop_events e JOIN stops s ON s.stop_id = e.stop_id
WHERE e.actual_time IS NULL GROUP BY s.stop_id HAVING COUNT(*) >= 2 ORDER BY skipped DESC, s.name;""",
      ["stop", "skipped"], ordered=True),
    S("open-fault-age", 2,
      "Open faults of severity 3 or more: tram fleet number, category, severity and the number of days it has been open as of 2032-03-15 (reported on that day = 0). Longest open first, ties by fleet number then category.",
      """SELECT t.fleet_no, f.category, f.severity, CAST(julianday('2032-03-15') - julianday(f.reported_on) AS INTEGER) AS days_open
FROM faults f JOIN trams t ON t.tram_id = f.tram_id WHERE f.fixed_on IS NULL AND f.severity >= 3
ORDER BY days_open DESC, t.fleet_no, f.category;""",
      ["fleet_no", "category", "severity", "days_open"], ordered=True, allow_empty=True),
    S("worst-stop-per-run", 3,
      "For every run that actually ran (not cancelled) and made at least one stop, find its largest delay and where it happened. When two stops share the largest delay take the earlier one (lower seq). "
      "Columns: run id, service date, line code, stop name, delay in minutes. Only runs whose largest delay is at least 6 minutes are of interest. Order by delay descending, then run id.",
      f"""WITH d AS (
  SELECT e.run_id, e.seq, e.stop_id, {DELAY} AS delay,
         ROW_NUMBER() OVER (PARTITION BY e.run_id ORDER BY {DELAY} DESC, e.seq) AS rn
  FROM stop_events e WHERE e.actual_time IS NOT NULL
)
SELECT r.run_id, r.service_date, l.code AS line, s.name AS stop, d.delay
FROM d JOIN runs r ON r.run_id = d.run_id JOIN lines l ON l.line_id = r.line_id JOIN stops s ON s.stop_id = d.stop_id
WHERE d.rn = 1 AND d.delay >= 6 AND r.cancelled = 0
ORDER BY d.delay DESC, r.run_id;""",
      ["run_id", "service_date", "line", "stop", "delay"], ordered=True,
      wrong=(f"""SELECT r.run_id, r.service_date, l.code, s.name, {DELAY} AS delay FROM stop_events e JOIN runs r ON r.run_id = e.run_id JOIN lines l ON l.line_id = r.line_id JOIN stops s ON s.stop_id = e.stop_id
WHERE e.actual_time IS NOT NULL AND {DELAY} >= 6 ORDER BY delay DESC, r.run_id;""",)),
    S("delay-build-up", 3,
      "Runs that fell behind: compare the delay at the first stop actually made with the delay at the last stop actually made (by seq; skipped stops are ignored). List runs where the delay grew by at least 5 minutes. "
      "Columns: run id, first delay, last delay, growth. Order by growth descending, then run id.",
      f"""WITH m AS (
  SELECT e.run_id, {DELAY} AS delay,
         ROW_NUMBER() OVER (PARTITION BY e.run_id ORDER BY e.seq) AS fwd,
         ROW_NUMBER() OVER (PARTITION BY e.run_id ORDER BY e.seq DESC) AS bwd
  FROM stop_events e WHERE e.actual_time IS NOT NULL
)
SELECT f.run_id, f.delay AS first_delay, l.delay AS last_delay, l.delay - f.delay AS growth
FROM m f JOIN m l ON l.run_id = f.run_id AND l.bwd = 1
WHERE f.fwd = 1 AND l.delay - f.delay >= 5 ORDER BY growth DESC, f.run_id;""",
      ["run_id", "first_delay", "last_delay", "growth"], ordered=True,
      wrong=(f"""SELECT e.run_id, MIN({DELAY}), MAX({DELAY}), MAX({DELAY}) - MIN({DELAY}) AS g FROM stop_events e WHERE e.actual_time IS NOT NULL GROUP BY e.run_id HAVING g >= 5 ORDER BY g DESC, e.run_id;""",)),
    S("busiest-hour-per-stop", 3,
      "For each stop, which hour of the day (taken from the scheduled time) sees the most boardings in total? Ties go to the earlier hour. "
      "Columns: stop name, hour (0-23 as a number), total boardings in that hour. Stops without any boarding do not appear. Order by stop name.",
      """WITH h AS (
  SELECT e.stop_id, CAST(substr(e.sched_time, 1, 2) AS INTEGER) AS hr, SUM(e.boarded) AS b FROM stop_events e GROUP BY e.stop_id, hr HAVING SUM(e.boarded) > 0
), r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY stop_id ORDER BY b DESC, hr) AS rn FROM h)
SELECT s.name AS stop, r.hr AS hour, r.b AS boardings FROM r JOIN stops s ON s.stop_id = r.stop_id WHERE r.rn = 1 ORDER BY s.name;""",
      ["stop", "hour", "boardings"], ordered=True,
      wrong=("""SELECT s.name, CAST(substr(e.sched_time, 1, 2) AS INTEGER) AS hr, MAX(e.boarded) FROM stop_events e JOIN stops s ON s.stop_id = e.stop_id GROUP BY s.stop_id ORDER BY s.name;""",)),
    S("reliability-rank", 3,
      "Reliability of each tram: the number of runs assigned to it, how many were cancelled, and the cancelled share in percent rounded to 1 decimal (trams without runs are left out). "
      "Then rank the trams of the same model by that share, lowest first, using RANK (ties share a rank). Columns: fleet number, model, runs, cancelled, share, rank. Order by model, rank, fleet number.",
      """WITH t AS (
  SELECT tr.tram_id, tr.fleet_no, tr.model, COUNT(*) AS runs, SUM(r.cancelled) AS cancelled,
         ROUND(100.0 * SUM(r.cancelled) / COUNT(*), 1) AS share
  FROM trams tr JOIN runs r ON r.tram_id = tr.tram_id GROUP BY tr.tram_id
)
SELECT fleet_no, model, runs, cancelled, share, RANK() OVER (PARTITION BY model ORDER BY share) AS rnk FROM t ORDER BY model, rnk, fleet_no;""",
      ["fleet_no", "model", "runs", "cancelled", "share", "rank"], ordered=True,
      wrong=("""WITH t AS (SELECT tr.tram_id, tr.fleet_no, tr.model, COUNT(*) AS runs, SUM(r.cancelled) AS cancelled, ROUND(100.0 * SUM(r.cancelled) / COUNT(*), 1) AS share FROM trams tr JOIN runs r ON r.tram_id = tr.tram_id GROUP BY tr.tram_id)
SELECT fleet_no, model, runs, cancelled, share, ROW_NUMBER() OVER (PARTITION BY model ORDER BY share, fleet_no) FROM t ORDER BY model, 6, fleet_no;""",)),
    S("repeat-faults", 4,
      "Repeat offenders: find every pair of faults on the same tram and in the same category where the second was reported 1 to 30 days after the first, and report the trams (once each) that have at least one third fault of that category "
      "within 30 days of the first one of a trio (three faults of one category inside a 30-day span: first and third reported at most 30 days apart). "
      "Columns: fleet number, category, date of the first fault of the earliest such trio. Order by fleet number, category.",
      """WITH x AS (
  SELECT f.tram_id, f.category, f.reported_on, LEAD(f.reported_on, 2) OVER (PARTITION BY f.tram_id, f.category ORDER BY f.reported_on, f.fault_id) AS third
  FROM faults f
)
SELECT t.fleet_no, x.category, MIN(x.reported_on) AS first_report
FROM x JOIN trams t ON t.tram_id = x.tram_id
WHERE x.third IS NOT NULL AND julianday(x.third) - julianday(x.reported_on) <= 30
GROUP BY x.tram_id, x.category ORDER BY t.fleet_no, x.category;""",
      ["fleet_no", "category", "first_report"], ordered=True, allow_empty=True,
      wrong=("""SELECT t.fleet_no, f.category, MIN(f.reported_on) FROM faults f JOIN trams t ON t.tram_id = f.tram_id GROUP BY f.tram_id, f.category HAVING COUNT(*) >= 3 ORDER BY t.fleet_no, f.category;""",)),
    S("bunching", 4,
      "Bunching: at one stop, on one service date, for trams of the same line and direction, two consecutive arrivals (ordered by actual time) less than 2 minutes apart. "
      "Skipped stops and cancelled runs have no arrival. Report each such close pair: stop name, service date, line code, the later run's id and the gap in minutes. Order by service date, stop name, later run id.",
      f"""WITH a AS (
  SELECT e.stop_id, r.service_date, r.line_id, r.direction, r.run_id, {MIN.format('e.actual_time')} AS m,
         LAG({MIN.format('e.actual_time')}) OVER w AS prev_m
  FROM stop_events e JOIN runs r ON r.run_id = e.run_id
  WHERE e.actual_time IS NOT NULL AND r.cancelled = 0
  WINDOW w AS (PARTITION BY e.stop_id, r.service_date, r.line_id, r.direction ORDER BY {MIN.format('e.actual_time')}, r.run_id)
)
SELECT s.name AS stop, a.service_date, l.code AS line, a.run_id, a.m - a.prev_m AS gap
FROM a JOIN stops s ON s.stop_id = a.stop_id JOIN lines l ON l.line_id = a.line_id
WHERE a.prev_m IS NOT NULL AND a.m - a.prev_m < 2
ORDER BY a.service_date, s.name, a.run_id;""",
      ["stop", "service_date", "line", "run_id", "gap"], ordered=True, allow_empty=True,
      wrong=(f"""SELECT s.name, r.service_date, l.code, r.run_id, 0 FROM stop_events e JOIN runs r ON r.run_id = e.run_id JOIN stops s ON s.stop_id = e.stop_id JOIN lines l ON l.line_id = r.line_id
WHERE e.actual_time IS NOT NULL AND EXISTS (SELECT 1 FROM stop_events e2 JOIN runs r2 ON r2.run_id = e2.run_id WHERE e2.stop_id = e.stop_id AND r2.service_date = r.service_date AND r2.line_id = r.line_id AND r2.run_id <> r.run_id AND e2.actual_time = e.actual_time)
ORDER BY r.service_date, s.name, r.run_id;""",)),
    S("max-load", 4,
      "Passenger load: on each run that ran, the number of people on board after each stop is the cumulative sum of boarded minus alighted (in seq order). "
      "For every run report the peak load and the stop where it first occurs (lowest seq). Only runs whose peak load is at least 20. Columns: run id, line code, stop name, peak load. Order by peak load descending, then run id.",
      """WITH l AS (
  SELECT e.run_id, e.seq, e.stop_id, SUM(e.boarded - e.alighted) OVER (PARTITION BY e.run_id ORDER BY e.seq) AS onboard FROM stop_events e
), p AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY run_id ORDER BY onboard DESC, seq) AS rn FROM l)
SELECT p.run_id, li.code AS line, s.name AS stop, p.onboard AS peak
FROM p JOIN runs r ON r.run_id = p.run_id JOIN lines li ON li.line_id = r.line_id JOIN stops s ON s.stop_id = p.stop_id
WHERE p.rn = 1 AND p.onboard >= 20 ORDER BY p.onboard DESC, p.run_id;""",
      ["run_id", "line", "stop", "peak"], ordered=True,
      wrong=("""SELECT e.run_id, li.code, s.name, SUM(e.boarded) AS b FROM stop_events e JOIN runs r ON r.run_id = e.run_id JOIN lines li ON li.line_id = r.line_id JOIN stops s ON s.stop_id = e.stop_id GROUP BY e.run_id HAVING b >= 20 ORDER BY b DESC, e.run_id;""",)),
    S("median-days-to-fix", 4,
      "Median repair time: for each fault category, the median number of days between `reported_on` and `fixed_on` over the faults that have been fixed. With an even number of faults the median is the mean of the two middle values. "
      "Columns: category, number of fixed faults, median days (as a number with at most one decimal, e.g. 2 or 2.5). Order by category.",
      """WITH d AS (
  SELECT category, julianday(fixed_on) - julianday(reported_on) AS days,
         ROW_NUMBER() OVER (PARTITION BY category ORDER BY julianday(fixed_on) - julianday(reported_on)) AS rn,
         COUNT(*) OVER (PARTITION BY category) AS n
  FROM faults WHERE fixed_on IS NOT NULL
)
SELECT category, MAX(n) AS fixed, AVG(days) AS median_days FROM d
WHERE rn IN ((n + 1) / 2, (n + 2) / 2) GROUP BY category ORDER BY category;""",
      ["category", "fixed", "median_days"], ordered=True, places=2,
      wrong=("""SELECT category, COUNT(*), AVG(julianday(fixed_on) - julianday(reported_on)) FROM faults WHERE fixed_on IS NOT NULL GROUP BY category ORDER BY category;""",)),
    S("fix-delay-minutes", 2,
      "`query.sql` is meant to list the stop events that were more than 3 minutes late, with the delay in minutes, but it compares the `HH:MM` strings and treats `09:05` against `08:58` as 7 minutes... "
      "which only works inside one hour. Fix it: columns run id, seq, delay in minutes (actual minus scheduled, computed from hours and minutes); only events with an actual time and a delay above 3. Order by delay descending, then run id, then seq.",
      ref=f"""SELECT e.run_id, e.seq, {DELAY} AS delay FROM stop_events e WHERE e.actual_time IS NOT NULL AND {DELAY} > 3 ORDER BY delay DESC, e.run_id, e.seq;""",
      cols=["run_id", "seq", "delay"], ordered=True, show=False,
      buggy="""SELECT e.run_id, e.seq, CAST(substr(e.actual_time, 4, 2) AS INTEGER) - CAST(substr(e.sched_time, 4, 2) AS INTEGER) AS delay
FROM stop_events e
WHERE e.actual_time > e.sched_time AND CAST(substr(e.actual_time, 4, 2) AS INTEGER) - CAST(substr(e.sched_time, 4, 2) AS INTEGER) > 3
ORDER BY delay DESC, e.run_id, e.seq;"""),
]


@family("data-tram-depot", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL reports on a tram operator's run log: late shares, worst stop per run, delay build-up, bunching, load profiles, medians")
def tram_depot(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
