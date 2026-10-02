"""SQL tasks on an invented repair co-op's ticket history (latest-status, durations between events, state machines, sweep line)."""
from datetime import date, datetime, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE technicians (
      tech_id    INTEGER PRIMARY KEY,
      name       TEXT NOT NULL UNIQUE,
      specialty  TEXT NOT NULL CHECK (specialty IN ('audio', 'computing', 'appliance', 'bicycle')),
      hired_on   TEXT NOT NULL
    );
    CREATE TABLE devices (
      device_id  INTEGER PRIMARY KEY,
      kind       TEXT NOT NULL,
      brand      TEXT NOT NULL,
      owner      TEXT NOT NULL
    );
    CREATE TABLE tickets (
      ticket_id  INTEGER PRIMARY KEY,
      device_id  INTEGER NOT NULL REFERENCES devices(device_id),
      tech_id    INTEGER REFERENCES technicians(tech_id),   -- NULL while nobody has picked the ticket up
      opened_on  TEXT NOT NULL,                              -- YYYY-MM-DD
      severity   INTEGER NOT NULL CHECK (severity BETWEEN 1 AND 3)
    );
    CREATE TABLE status_log (
      log_id      INTEGER PRIMARY KEY,
      ticket_id   INTEGER NOT NULL REFERENCES tickets(ticket_id),
      status      TEXT NOT NULL CHECK (status IN ('received', 'diagnosed', 'awaiting_parts', 'repairing', 'done', 'abandoned')),
      changed_at  TEXT NOT NULL                              -- 'YYYY-MM-DD HH:MM'; strictly increasing within a ticket
    );
    CREATE TABLE parts (
      sku            TEXT PRIMARY KEY,
      name           TEXT NOT NULL,
      stock          INTEGER NOT NULL,
      reorder_level  INTEGER NOT NULL
    );
    CREATE TABLE parts_used (
      use_id      INTEGER PRIMARY KEY,
      ticket_id   INTEGER NOT NULL REFERENCES tickets(ticket_id),
      sku         TEXT NOT NULL REFERENCES parts(sku),
      qty         INTEGER NOT NULL,
      unit_cents  INTEGER NOT NULL
    );
    CREATE TABLE sla (
      severity  INTEGER PRIMARY KEY,
      max_days  INTEGER NOT NULL      -- a ticket should reach 'done' within this many days of opened_on
    );
''')

DOC = dd('''
    Quillon is a repair co-op: people bring in radios, laptops, kettles and bicycles. Each job is a **ticket**; every time its
    status changes a row is appended to `status_log`, so the *current* status of a ticket is its latest log row.

    * Normal life of a ticket: `received` -> `diagnosed` -> (`awaiting_parts`) -> `repairing` -> `done`. It can also end as
      `abandoned`. A `done` ticket can be *reopened* (`done` -> `repairing`).
    * Allowed transitions: received -> diagnosed | abandoned; diagnosed -> awaiting_parts | repairing | abandoned;
      awaiting_parts -> repairing | abandoned; repairing -> done | awaiting_parts | abandoned; done -> repairing.
      The first row of every ticket must be `received`. Anything else in the log is a data error.
    * "Open" means the current status is neither `done` nor `abandoned`.
    * `parts_used` records the parts fitted to a ticket (`unit_cents` is the price charged per unit).
    * The co-op's reports are run as of **2031-09-30 00:00**: "now" is that moment.
''')

BRANDS = ["Valtor", "Brennan", "Kesmark", "Oloff", "Tamsin & Rye", "Hexa", "Pelham", "Norvik"]
KINDS = ["radio", "laptop", "kettle", "turntable", "e-bike", "amplifier", "toaster", "tablet", "sewing machine", "desk fan"]
NAMES = ["Yuri Castellanos", "Bea Thornfield", "Ravi Mehra", "Linnea Ford", "Osei Bonsu", "Tess Harlan", "Mika Voss", "Jun Park", "Dara Quinn", "Eli Santoro"]
ALLOWED = {"received": ["diagnosed", "abandoned"], "diagnosed": ["awaiting_parts", "repairing", "abandoned"],
           "awaiting_parts": ["repairing", "abandoned"], "repairing": ["done", "awaiting_parts", "abandoned"], "done": ["repairing"]}


def gen(rng, big):
    techs = [(i + 1, nm, rng.choice(["audio", "computing", "appliance", "bicycle"]), K.iso(K.rdate(rng, date(2026, 1, 1), 1500)))
             for i, nm in enumerate(["Ines Calloway", "Mateus Brandt", "Wen Ostrowski", "Hester Dunne", "Abel Nakamura"][:5 if big else 3])]
    nd = 26 if big else 9
    devices = [(i + 1, rng.choice(KINDS), rng.choice(BRANDS), rng.choice(NAMES)) for i in range(nd)]
    skus = ["BELT-02", "CAP-470", "FUSE-5A", "PSU-12V", "SWITCH-A", "TIRE-700", "CHAIN-9S", "HDD-250", "LCD-10", "KNOB-3"]
    parts = [(s, s.split("-")[0].title() + " " + s.split("-")[1], rng.randint(0, 30), rng.choice([3, 5, 8])) for s in skus[:8 if big else 5]]
    tickets, log = [], []
    lid = 0
    nt = 60 if big else 10
    now = datetime(2031, 9, 30)
    for tid in range(1, nt + 1):
        op = K.rdate(rng, date(2031, 7, 1), 85)
        tech = None if rng.random() < 0.1 else rng.choice(techs[:-1])[0]
        tickets.append((tid, rng.choice(devices)[0], tech, K.iso(op), rng.choice([1, 2, 2, 3])))
        t = datetime(op.year, op.month, op.day, rng.randint(8, 11), rng.choice([0, 10, 20, 40]))
        st = "received"
        seq = [(st, t)]
        for _ in range(12):
            if st in ("abandoned",):
                break
            if st == "done" and rng.random() < 0.85:
                break
            nxt = rng.choice(ALLOWED[st]) if st in ALLOWED else None
            if st == "repairing" and rng.random() < 0.55:
                nxt = "done"
            if st == "diagnosed" and rng.random() < 0.5:
                nxt = "repairing"
            if st == "received" and rng.random() < 0.9:
                nxt = "diagnosed"
            if rng.random() < 0.04:
                nxt = rng.choice(["received", "done", "diagnosed", "awaiting_parts", "repairing"])
            t = t + timedelta(days=rng.choice([0, 1, 1, 2, 3, 5, 9, 15, 21]), hours=rng.randint(0, 6), minutes=rng.choice([0, 7, 30, 45]))
            if t >= now:
                break
            seq.append((nxt, t))
            st = nxt
            if rng.random() < 0.18 and st not in ("done", "abandoned"):
                break  # still in progress
        if tid % (7 if big else 4) == 3 and seq[-1][0] == "done":  # plant a reopening that is finished again
            for stt, dd_ in (("repairing", 3), ("done", 6)):
                tm = seq[-1][1] + timedelta(days=dd_ - 2, hours=rng.randint(1, 5))
                if tm < now:
                    seq.append((stt, tm))
        if tid % (9 if big else 5) == 4:  # plant an illegal transition
            last = seq[-1][0]
            bad = [x for x in ("received", "done", "diagnosed", "awaiting_parts") if x not in ALLOWED.get(last, []) and x != last]
            tm = seq[-1][1] + timedelta(days=1, hours=rng.randint(1, 5))
            if tm < now:
                seq.append((rng.choice(bad), tm))
        if tid % (17 if big else 7) == 6:  # and a ticket whose first row is not 'received'
            seq[0] = ("diagnosed", seq[0][1])
        for stt, tm in seq:
            lid += 1
            log.append((lid, tid, stt, K.iso(tm)))
    # a technician (the last one) who only has two waves of tickets: the second wave is received at the very minute the first wave is released
    k = 3 if big else 2
    tid = nt
    for wave, (t0, t1) in enumerate(((datetime(2031, 9, 20, 8, 0), datetime(2031, 9, 22, 10, 0)), (datetime(2031, 9, 22, 10, 0), datetime(2031, 9, 25, 16, 30)))):
        for _ in range(k):
            tid += 1
            tickets.append((tid, rng.choice(devices)[0], techs[-1][0], K.iso(t0.date()), 2))
            for stt, tm in (("received", t0), ("diagnosed", t0 + timedelta(minutes=30)), ("repairing", t0 + timedelta(hours=1)), ("done", t1)):
                lid += 1
                log.append((lid, tid, stt, K.iso(tm)))
    # two long waits for parts: one resolved after 18 days, one still waiting at 'now'
    for t0, steps in ((datetime(2031, 8, 1, 9, 0), [("received", 0), ("diagnosed", 1), ("awaiting_parts", 24), ("repairing", 24 + 18 * 24), ("done", 24 + 20 * 24)]),
                      (datetime(2031, 9, 8, 9, 30), [("received", 0), ("diagnosed", 2), ("awaiting_parts", 48)])):
        tid += 1
        tickets.append((tid, rng.choice(devices)[0], techs[0][0], K.iso(t0.date()), 3))
        for stt, hrs in steps:
            lid += 1
            log.append((lid, tid, stt, K.iso(t0 + timedelta(hours=hrs))))
    nt = tid
    used = []
    uid = 0
    for tid in range(1, nt + 1):
        for _ in range(rng.choice([0, 0, 1, 1, 2])):
            uid += 1
            p = rng.choice(parts)
            used.append((uid, tid, p[0], rng.randint(1, 3), rng.choice([450, 900, 1250, 2800, 4900, 9900])))
    sla = [(1, 21), (2, 14), (3, 7)]
    return {"technicians": techs, "devices": devices, "tickets": tickets, "status_log": log, "parts": parts, "parts_used": used, "sla": sla}


DOMAIN = K.Domain("repairshop", "Quillon Repair Co-op: tickets and status history", SCHEMA, DOC, gen)
S = K.Spec

_CUR = """(SELECT l.ticket_id, l.status, l.changed_at FROM status_log l
 WHERE l.log_id = (SELECT x.log_id FROM status_log x WHERE x.ticket_id = l.ticket_id ORDER BY x.changed_at DESC, x.log_id DESC LIMIT 1))"""

SPECS = [
    S("severe-september", 1,
      "Which urgent jobs (severity 3) were opened in September 2031? Ticket id, opened date, and the device's brand and kind. Earliest first, then ticket id.",
      """SELECT t.ticket_id, t.opened_on, d.brand, d.kind
FROM tickets t JOIN devices d ON d.device_id = t.device_id
WHERE t.severity = 3 AND t.opened_on >= '2031-09-01' AND t.opened_on < '2031-10-01'
ORDER BY t.opened_on, t.ticket_id;""",
      ["ticket_id", "opened_on", "brand", "kind"], ordered=True),
    S("current-status", 2,
      "Give me the current status of every ticket and when it entered that status (the latest row in its status log). Ticket id, status, since. Order by ticket id.",
      f"""SELECT ticket_id, status, changed_at AS since FROM {_CUR} ORDER BY ticket_id;""".replace(_CUR, _CUR),
      ["ticket_id", "status", "since"], ordered=True,
      wrong=("""SELECT ticket_id, status, MIN(changed_at) FROM status_log GROUP BY ticket_id ORDER BY ticket_id;""",)),
    S("ticket-parts-cost", 2,
      "For every ticket whose current status is `done`, what did the parts cost the customer? Sum qty * unit_cents over the parts used on that ticket (0 if none). "
      "Show ticket id, the parts total in cents and the number of distinct parts, for tickets with a total over 5000 cents, most expensive first, ties by ticket id.",
      f"""SELECT c.ticket_id, COALESCE(SUM(u.qty * u.unit_cents), 0) AS parts_cents, COUNT(DISTINCT u.sku) AS part_kinds
FROM {_CUR} c LEFT JOIN parts_used u ON u.ticket_id = c.ticket_id
WHERE c.status = 'done'
GROUP BY c.ticket_id
HAVING COALESCE(SUM(u.qty * u.unit_cents), 0) > 5000
ORDER BY parts_cents DESC, c.ticket_id;""",
      ["ticket_id", "parts_cents", "part_kinds"], ordered=True,
      wrong=("""SELECT t.ticket_id, SUM(u.qty * u.unit_cents), COUNT(DISTINCT u.sku) FROM tickets t JOIN parts_used u ON u.ticket_id = t.ticket_id
WHERE EXISTS (SELECT 1 FROM status_log l WHERE l.ticket_id = t.ticket_id AND l.status = 'done')
GROUP BY t.ticket_id HAVING SUM(u.qty * u.unit_cents) > 5000 ORDER BY 2 DESC, 1;""",)),
    S("monthly-completions", 3,
      "How many tickets did each technician finish per month? Count a ticket for the month of its FIRST `done` entry only (a reopened ticket is not counted again). "
      "One row per technician with columns for July, August and September 2031 (`jul`, `aug`, `sep`, zeros where nothing was finished), covering every technician. Order by technician name.",
      """WITH first_done AS (
  SELECT ticket_id, MIN(changed_at) AS at FROM status_log WHERE status = 'done' GROUP BY ticket_id
)
SELECT te.name AS technician,
       COALESCE(SUM(substr(f.at, 1, 7) = '2031-07'), 0) AS jul,
       COALESCE(SUM(substr(f.at, 1, 7) = '2031-08'), 0) AS aug,
       COALESCE(SUM(substr(f.at, 1, 7) = '2031-09'), 0) AS sep
FROM technicians te
LEFT JOIN tickets t ON t.tech_id = te.tech_id
LEFT JOIN first_done f ON f.ticket_id = t.ticket_id
GROUP BY te.tech_id
ORDER BY te.name;""",
      ["technician", "jul", "aug", "sep"], ordered=True,
      wrong=("""SELECT te.name, COALESCE(SUM(substr(l.changed_at, 1, 7) = '2031-07'), 0), COALESCE(SUM(substr(l.changed_at, 1, 7) = '2031-08'), 0), COALESCE(SUM(substr(l.changed_at, 1, 7) = '2031-09'), 0)
FROM technicians te LEFT JOIN tickets t ON t.tech_id = te.tech_id LEFT JOIN status_log l ON l.ticket_id = t.ticket_id AND l.status = 'done' GROUP BY te.tech_id ORDER BY te.name;""",)),
    S("reopened-tickets", 3,
      "Which tickets were reopened? A reopening is a status row of `repairing` whose previous row (by time) in the same ticket was `done`. "
      "List ticket id, how many times it was reopened, and the time of the first reopening, ordered by ticket id.",
      """WITH s AS (
  SELECT ticket_id, status, changed_at, LAG(status) OVER (PARTITION BY ticket_id ORDER BY changed_at, log_id) AS prev
  FROM status_log
)
SELECT ticket_id, COUNT(*) AS reopenings, MIN(changed_at) AS first_reopened
FROM s WHERE prev = 'done' AND status = 'repairing'
GROUP BY ticket_id ORDER BY ticket_id;""",
      ["ticket_id", "reopenings", "first_reopened"], ordered=True,
      wrong=("""WITH s AS (SELECT ticket_id, status, changed_at, LAG(status) OVER (PARTITION BY ticket_id ORDER BY changed_at, log_id) AS prev FROM status_log)
SELECT ticket_id, COUNT(*), MIN(changed_at) FROM s WHERE prev = 'done' GROUP BY ticket_id ORDER BY ticket_id;""",)),
    S("reorder-after-commitments", 3,
      "Stock check before the Friday order: for every part, subtract the quantity already fitted to tickets that are still open from its `stock`, "
      "and list the parts where what is left is at or below `reorder_level`. Show sku, stock, committed quantity on open tickets (0 if none), what is left, and the reorder level. Order by what is left, then sku.",
      f"""SELECT p.sku, p.stock, COALESCE(c.q, 0) AS committed, p.stock - COALESCE(c.q, 0) AS remaining, p.reorder_level
FROM parts p
LEFT JOIN (
  SELECT u.sku, SUM(u.qty) AS q FROM parts_used u JOIN {_CUR} cur ON cur.ticket_id = u.ticket_id
  WHERE cur.status NOT IN ('done', 'abandoned') GROUP BY u.sku
) c ON c.sku = p.sku
WHERE p.stock - COALESCE(c.q, 0) <= p.reorder_level
ORDER BY remaining, p.sku;""",
      ["sku", "stock", "committed", "remaining", "reorder_level"], ordered=True,
      wrong=("""SELECT p.sku, p.stock, COALESCE(SUM(u.qty), 0), p.stock - COALESCE(SUM(u.qty), 0), p.reorder_level FROM parts p LEFT JOIN parts_used u ON u.sku = p.sku
GROUP BY p.sku HAVING p.stock - COALESCE(SUM(u.qty), 0) <= p.reorder_level ORDER BY 4, p.sku;""",)),
    S("waiting-for-parts", 4,
      "Tickets spend a lot of time waiting for parts. For each ticket, total the days it spent in `awaiting_parts`: each stay lasts from its log row until the next log row of that ticket, "
      "or until now (2031-09-30 00:00) when it is the last row. Show tickets with MORE than 14 days of waiting in total: ticket id, technician name (or the text 'unassigned'), "
      "days waiting rounded to 1 decimal. Longest first, ties by ticket id.",
      """WITH s AS (
  SELECT ticket_id, status, changed_at,
         LEAD(changed_at, 1, '2031-09-30 00:00') OVER (PARTITION BY ticket_id ORDER BY changed_at, log_id) AS nxt
  FROM status_log
), w AS (
  SELECT ticket_id, SUM(CAST(strftime('%s', nxt) AS INTEGER) - CAST(strftime('%s', changed_at) AS INTEGER)) / 86400.0 AS days
  FROM s WHERE status = 'awaiting_parts' GROUP BY ticket_id
)
SELECT w.ticket_id, COALESCE(te.name, 'unassigned') AS technician, ROUND(w.days, 1) AS days_waiting
FROM w JOIN tickets t ON t.ticket_id = w.ticket_id LEFT JOIN technicians te ON te.tech_id = t.tech_id
WHERE w.days > 14
ORDER BY w.days DESC, w.ticket_id;""",
      ["ticket_id", "technician", "days_waiting"], ordered=True,
      wrong=("""WITH s AS (SELECT ticket_id, status, changed_at, LEAD(changed_at) OVER (PARTITION BY ticket_id ORDER BY changed_at, log_id) AS nxt FROM status_log),
w AS (SELECT ticket_id, SUM(CAST(strftime('%s', nxt) AS INTEGER) - CAST(strftime('%s', changed_at) AS INTEGER)) / 86400.0 AS days FROM s WHERE status = 'awaiting_parts' AND nxt IS NOT NULL GROUP BY ticket_id)
SELECT w.ticket_id, COALESCE(te.name, 'unassigned'), ROUND(w.days, 1) FROM w JOIN tickets t ON t.ticket_id = w.ticket_id LEFT JOIN technicians te ON te.tech_id = t.tech_id
WHERE w.days > 14 ORDER BY w.days DESC, w.ticket_id;""",)),
    S("sla-breaches", 4,
      "SLA report. A ticket breaches its SLA when the number of whole days from `opened_on` to the date of its FIRST `done` entry exceeds `max_days` for its severity, "
      "or, if it has never been done, when it is not abandoned and the days from `opened_on` to the date 2031-09-30 exceed `max_days`. "
      "Return ticket id, severity, the number of days counted and whether it was finished (`finished` is 1 for the first case, 0 for the second). Order by days over the limit (days minus max_days) descending, then ticket id.",
      """WITH fd AS (
  SELECT ticket_id, MIN(substr(changed_at, 1, 10)) AS done_on FROM status_log WHERE status = 'done' GROUP BY ticket_id
), ab AS (
  SELECT DISTINCT ticket_id FROM status_log WHERE status = 'abandoned'
), x AS (
  SELECT t.ticket_id, t.severity, s.max_days,
         CASE WHEN fd.done_on IS NOT NULL THEN CAST(julianday(fd.done_on) - julianday(t.opened_on) AS INTEGER)
              ELSE CAST(julianday('2031-09-30') - julianday(t.opened_on) AS INTEGER) END AS days,
         CASE WHEN fd.done_on IS NOT NULL THEN 1 ELSE 0 END AS finished
  FROM tickets t JOIN sla s ON s.severity = t.severity
  LEFT JOIN fd ON fd.ticket_id = t.ticket_id
  WHERE fd.done_on IS NOT NULL OR t.ticket_id NOT IN (SELECT ticket_id FROM ab)
)
SELECT ticket_id, severity, days, finished FROM x WHERE days > max_days
ORDER BY days - max_days DESC, ticket_id;""",
      ["ticket_id", "severity", "days", "finished"], ordered=True,
      wrong=("""SELECT t.ticket_id, t.severity, CAST(julianday(COALESCE(MIN(CASE WHEN l.status = 'done' THEN substr(l.changed_at, 1, 10) END), '2031-09-30')) - julianday(t.opened_on) AS INTEGER) AS days,
MIN(CASE WHEN l.status = 'done' THEN 1 ELSE 0 END) AS f
FROM tickets t JOIN sla s ON s.severity = t.severity JOIN status_log l ON l.ticket_id = t.ticket_id GROUP BY t.ticket_id
HAVING days > MAX(s.max_days) ORDER BY days - MAX(s.max_days) DESC, t.ticket_id;""",)),
    S("illegal-transitions", 4,
      "Data quality sweep of `status_log`: list every row that breaks the rules in the README, i.e. a row whose transition from the previous row of the same ticket (by time) is not allowed, "
      "and every ticket's first row when it is not `received`. Return log id, ticket id, the previous status (NULL for a first row) and the status. Order by log id.",
      """WITH s AS (
  SELECT log_id, ticket_id, status, LAG(status) OVER (PARTITION BY ticket_id ORDER BY changed_at, log_id) AS prev FROM status_log
), ok(a, b) AS (
  VALUES ('received','diagnosed'), ('received','abandoned'), ('diagnosed','awaiting_parts'), ('diagnosed','repairing'), ('diagnosed','abandoned'),
         ('awaiting_parts','repairing'), ('awaiting_parts','abandoned'), ('repairing','done'), ('repairing','awaiting_parts'), ('repairing','abandoned'), ('done','repairing')
)
SELECT s.log_id, s.ticket_id, s.prev AS previous, s.status
FROM s
WHERE (s.prev IS NULL AND s.status <> 'received')
   OR (s.prev IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ok WHERE ok.a = s.prev AND ok.b = s.status))
ORDER BY s.log_id;""",
      ["log_id", "ticket_id", "previous", "status"], ordered=True,
      wrong=("""WITH s AS (SELECT log_id, ticket_id, status, LAG(status) OVER (PARTITION BY ticket_id ORDER BY changed_at, log_id) AS prev FROM status_log)
SELECT log_id, ticket_id, prev, status FROM s WHERE prev IS NOT NULL AND NOT ((prev = 'received' AND status IN ('diagnosed','abandoned')) OR (prev = 'diagnosed' AND status IN ('awaiting_parts','repairing','abandoned'))
OR (prev = 'awaiting_parts' AND status IN ('repairing','abandoned')) OR (prev = 'repairing' AND status IN ('done','awaiting_parts','abandoned')) OR (prev = 'done' AND status = 'repairing')) ORDER BY log_id;""",)),
    S("median-days-to-done", 4,
      "What is each technician's typical turnaround? For every technician, take their tickets that reached `done` at some point, measure whole days from `opened_on` to the date of the FIRST `done` entry, "
      "and report the median of those numbers (for an even count, the mean of the two middle values), rounded to 1 decimal, together with how many tickets that is. "
      "Technicians with no finished ticket are left out. Order by technician name.",
      """WITH fd AS (
  SELECT ticket_id, MIN(substr(changed_at, 1, 10)) AS done_on FROM status_log WHERE status = 'done' GROUP BY ticket_id
), v AS (
  SELECT t.tech_id, CAST(julianday(fd.done_on) - julianday(t.opened_on) AS INTEGER) AS days
  FROM tickets t JOIN fd ON fd.ticket_id = t.ticket_id WHERE t.tech_id IS NOT NULL
), r AS (
  SELECT tech_id, days, ROW_NUMBER() OVER (PARTITION BY tech_id ORDER BY days) AS rn, COUNT(*) OVER (PARTITION BY tech_id) AS n FROM v
)
SELECT te.name AS technician, ROUND(AVG(r.days), 1) AS median_days, MAX(r.n) AS tickets
FROM r JOIN technicians te ON te.tech_id = r.tech_id
WHERE r.rn IN ((r.n + 1) / 2, (r.n + 2) / 2)
GROUP BY te.tech_id ORDER BY te.name;""",
      ["technician", "median_days", "tickets"], ordered=True,
      wrong=("""SELECT te.name, ROUND(AVG(CAST(julianday(f.done_on) - julianday(t.opened_on) AS INTEGER)), 1), COUNT(*)
FROM technicians te JOIN tickets t ON t.tech_id = te.tech_id JOIN (SELECT ticket_id, MIN(substr(changed_at, 1, 10)) AS done_on FROM status_log WHERE status = 'done' GROUP BY ticket_id) f ON f.ticket_id = t.ticket_id
GROUP BY te.tech_id ORDER BY te.name;""",)),
    S("peak-parallel-load", 5,
      "How many jobs does each technician juggle at once? A ticket assigned to a technician is *held* from the timestamp of its `received` row until the timestamp of its first `done` or `abandoned` row "
      "(still held at 2031-09-30 00:00 if it has neither). If one ticket is released at the same minute another one is received, the release counts first. "
      "Return, per technician who has any assigned ticket, the highest number of tickets held at the same time and the first timestamp at which that peak was reached. Order by technician name.",
      """WITH span AS (
  SELECT t.tech_id, t.ticket_id,
         (SELECT MIN(changed_at) FROM status_log l WHERE l.ticket_id = t.ticket_id AND l.status = 'received') AS a,
         COALESCE((SELECT MIN(changed_at) FROM status_log l WHERE l.ticket_id = t.ticket_id AND l.status IN ('done', 'abandoned')), '2031-09-30 00:00') AS b
  FROM tickets t WHERE t.tech_id IS NOT NULL
), ev AS (
  SELECT tech_id, a AS at, 1 AS delta, 1 AS ord FROM span WHERE a IS NOT NULL
  UNION ALL
  SELECT tech_id, b, -1, 0 FROM span WHERE a IS NOT NULL
), run AS (
  SELECT tech_id, at, SUM(delta) OVER (PARTITION BY tech_id ORDER BY at, ord ROWS UNBOUNDED PRECEDING) AS held FROM ev
), best AS (
  SELECT tech_id, MAX(held) AS peak FROM run GROUP BY tech_id
)
SELECT te.name AS technician, b.peak, MIN(r.at) AS first_at
FROM best b JOIN run r ON r.tech_id = b.tech_id AND r.held = b.peak JOIN technicians te ON te.tech_id = b.tech_id
GROUP BY te.tech_id ORDER BY te.name;""",
      ["technician", "peak", "first_at"], ordered=True, show=False,
      notes="If a ticket's `received` row is missing (data error) it is ignored. Several events of one technician at the same minute: all releases first, then all receptions.",
      wrong=("""WITH span AS (SELECT t.tech_id, t.ticket_id, (SELECT MIN(changed_at) FROM status_log l WHERE l.ticket_id = t.ticket_id AND l.status = 'received') AS a,
COALESCE((SELECT MIN(changed_at) FROM status_log l WHERE l.ticket_id = t.ticket_id AND l.status IN ('done', 'abandoned')), '2031-09-30 00:00') AS b FROM tickets t WHERE t.tech_id IS NOT NULL),
ev AS (SELECT tech_id, a AS at, 1 AS delta, 0 AS ord FROM span WHERE a IS NOT NULL UNION ALL SELECT tech_id, b, -1, 1 FROM span WHERE a IS NOT NULL),
run AS (SELECT tech_id, at, SUM(delta) OVER (PARTITION BY tech_id ORDER BY at, ord ROWS UNBOUNDED PRECEDING) AS held FROM ev),
best AS (SELECT tech_id, MAX(held) AS peak FROM run GROUP BY tech_id)
SELECT te.name, b.peak, MIN(r.at) FROM best b JOIN run r ON r.tech_id = b.tech_id AND r.held = b.peak JOIN technicians te ON te.tech_id = b.tech_id GROUP BY te.tech_id ORDER BY te.name;""",)),
    S("fix-open-per-technician", 2,
      "Our 'open tickets per technician' query keeps giving huge numbers, and technicians with nothing open vanish from it (@ROWS_BAD@ rows on the sample data instead of @ROWS_GOOD@). "
      "A ticket is open when its CURRENT (latest) status is neither `done` nor `abandoned`. Repair `query.sql` so that it returns, for every technician (including those with nothing open), the number of open tickets assigned to them. Order by the count descending, then name.",
      ref=f"""SELECT te.name AS technician, COUNT(c.ticket_id) AS open_tickets
FROM technicians te
LEFT JOIN tickets t ON t.tech_id = te.tech_id
LEFT JOIN {_CUR} c ON c.ticket_id = t.ticket_id AND c.status NOT IN ('done', 'abandoned')
GROUP BY te.tech_id
ORDER BY open_tickets DESC, te.name;""",
      cols=["technician", "open_tickets"], ordered=True, show=False,
      buggy="""SELECT te.name AS technician, COUNT(*) AS open_tickets
FROM technicians te
JOIN tickets t ON t.tech_id = te.tech_id
JOIN status_log l ON l.ticket_id = t.ticket_id
WHERE l.status NOT IN ('done', 'abandoned')
GROUP BY te.tech_id
ORDER BY open_tickets DESC, te.name;"""),
]


@family("data-repair-coop", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL reports on a repair co-op's ticket history: latest status, LAG/LEAD durations, state machine audit, sweep line")
def repairshop(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
