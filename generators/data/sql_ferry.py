"""SQL tasks on an invented island-ferry booking database (joins, windows, recursion, intervals)."""
from datetime import date, datetime, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE ports (
      port_id   INTEGER PRIMARY KEY,
      name      TEXT NOT NULL UNIQUE,
      island    TEXT NOT NULL,
      has_ramp  INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE vessels (
      vessel_id     INTEGER PRIMARY KEY,
      name          TEXT NOT NULL UNIQUE,
      pax_capacity  INTEGER NOT NULL,
      car_capacity  INTEGER NOT NULL,
      commissioned  TEXT NOT NULL            -- ISO date
    );
    CREATE TABLE routes (
      route_id         INTEGER PRIMARY KEY,
      origin_id        INTEGER NOT NULL REFERENCES ports(port_id),
      dest_id          INTEGER NOT NULL REFERENCES ports(port_id),
      distance_nm      REAL NOT NULL,
      duration_min     INTEGER NOT NULL,
      base_fare_cents  INTEGER NOT NULL,     -- per foot passenger
      car_fare_cents   INTEGER NOT NULL      -- per car
    );
    CREATE TABLE sailings (
      sailing_id  INTEGER PRIMARY KEY,
      route_id    INTEGER NOT NULL REFERENCES routes(route_id),
      vessel_id   INTEGER NOT NULL REFERENCES vessels(vessel_id),
      departs_at  TEXT NOT NULL,             -- 'YYYY-MM-DD HH:MM', port local time
      status      TEXT NOT NULL CHECK (status IN ('scheduled', 'sailed', 'cancelled'))
    );
    CREATE TABLE bookings (
      booking_id  INTEGER PRIMARY KEY,
      sailing_id  INTEGER NOT NULL REFERENCES sailings(sailing_id),
      passenger   TEXT NOT NULL,
      pax         INTEGER NOT NULL,          -- foot passengers on this booking
      cars        INTEGER NOT NULL DEFAULT 0,
      paid_cents  INTEGER NOT NULL,
      booked_on   TEXT NOT NULL,             -- ISO date, never after the sailing date
      cancelled   INTEGER NOT NULL DEFAULT 0
    );
''')

DOC = dd('''
    Skerry Line runs a handful of small car-and-passenger ferries between islands. This is the booking database.

    * A **route** is directed: Harrow Quay -> Skerry Head and Skerry Head -> Harrow Quay are two routes. `duration_min`
      is the crossing time; a vessel arrives `duration_min` minutes after `departs_at`.
    * A **sailing** is one departure of one vessel on one route. `status` is `scheduled` (in the future), `sailed`, or
      `cancelled`. Times are local, written `YYYY-MM-DD HH:MM`, so plain string comparison orders them.
    * A **booking** reserves `pax` foot passengers and `cars` cars on a sailing. `passenger` is the name of the person
      who booked; the same name always means the same person. A booking with `cancelled = 1` occupies no space,
      but the cancellation fee stays in `paid_cents`. Bookings on cancelled sailings are all `cancelled = 1`.
    * Money is in whole cents.
''')

PORT_POOL = ["Harrow Quay", "Skerry Head", "Little Muckle", "Gannet Sound", "Corran Pier", "Westhaven", "Ruadh Point", "Inchmarlo",
             "Sule Stack", "Fiddler's Rest", "Talland Slip", "Orkie Green", "Bressay Mouth", "Eilean Dubh"]
ISLANDS = ["Harrow", "Skerry", "Muckle", "Gannet", "Corran", "Westhaven", "Ruadh", "Inch", "Sule", "Fiddler", "Talland", "Orkie", "Bressay", "Eilean"]
VESSELS = ["MV Curlew", "MV Petrel", "MV Shearwater", "MV Guillemot", "MV Fulmar", "MV Tern", "MV Skua", "MV Razorbill"]
FIRST = ["Ines", "Callum", "Maren", "Tobias", "Odile", "Rhys", "Sunniva", "Ewan", "Nadia", "Piers", "Elspeth", "Anders", "Kirsten", "Lachlan", "Mirela", "Joss"]
LAST = ["Marsh", "Voss", "Keane", "Lindqvist", "Ferrars", "Okafor", "Dunmore", "Haldane", "Ibarra", "Quill", "Tamm", "Rennick"]


def gen(rng, big):
    nports = rng.randint(8, 10) if big else 6
    nves = 5 if big else 3
    start = date(2031, 5, 28) if big else date(2031, 6, 1)
    days = 34 if big else 7
    cutoff = date(2031, 6, 20) if big else date(2031, 6, 5)
    ports = [(1, "Harrow Quay", "Harrow", 1), (2, "Skerry Head", "Skerry", rng.randint(0, 1))]
    for i, k in enumerate(rng.sample(range(2, len(PORT_POOL)), nports - 2)):
        ports.append((i + 3, PORT_POOL[k], ISLANDS[k], rng.randint(0, 1)))
    vessels = []
    names = rng.sample([v for v in VESSELS if v != "MV Skua"], nves - 1) + ["MV Skua"]
    for i, nm in enumerate(names):
        vessels.append((i + 1, nm, rng.choice([20, 24, 30, 36, 40, 48]), rng.choice([4, 6, 8]),
                        "2031-08-01" if nm == "MV Skua" else f"{rng.randint(2012, 2029)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"))
    # route graph: a chain through every port plus a few extra edges; both directions exist
    order = list(range(1, nports + 1))
    edges = [(1, 2)]
    rest = order[2:]
    rng.shuffle(rest)
    chain = [2] + rest
    for a, b in zip(chain, chain[1:]):
        edges.append((a, b))
    for _ in range(nports // 2):
        a, b = rng.sample(order, 2)
        if (a, b) not in edges and (b, a) not in edges:
            edges.append((a, b))
    routes = []
    rid = 0
    for a, b in edges:
        dist = round(rng.uniform(3, 38), 1)
        dur = int(dist * 5.5 + rng.randint(10, 25))
        fare = int(round(dist * 95 + 400, -1))
        for o, d in ((a, b), (b, a)):
            rid += 1
            routes.append((rid, o, d, dist, dur, fare, fare * 3))
    rmap = {r[0]: r for r in routes}
    weights = [5 if r[0] <= 2 else 1 for r in routes]
    # itineraries: every in-service vessel sails 1-3 legs a day, back to back, now and then double-booked
    sail = []
    sid = 0
    for v in vessels:
        if v[1] == "MV Skua":
            continue
        for k in range(days):
            if rng.random() > (0.42 if big else 0.72):
                continue
            day = start + timedelta(days=k)
            t = datetime(day.year, day.month, day.day, rng.randint(6, 9), rng.choice([0, 15, 30, 45]))
            for _ in range(rng.randint(1, 3)):
                rid = rng.choices([r[0] for r in routes], weights)[0]
                r = rmap[rid]
                sid += 1
                if day < cutoff:
                    status = "cancelled" if rng.random() < 0.1 else "sailed"
                elif day == cutoff:
                    status = rng.choice(["sailed", "scheduled"])
                else:
                    status = "cancelled" if rng.random() < 0.07 else "scheduled"
                sail.append([sid, rid, v[0], t.strftime("%Y-%m-%d %H:%M"), status])
                end = t + timedelta(minutes=r[4])
                while True:
                    gap = rng.choice([0, -20, -10, 25, 40, 55, 90, 140, 200, 300, 420, 520]) if rng.random() < 0.5 else rng.randint(20, 600)
                    if abs(gap - 360) > 5:
                        break
                t = end + timedelta(minutes=gap)
                if t.day != day.day or t.hour >= 22:
                    break
    # plant: ties on the latest sailing of a route, and boundary-day cancellations
    sailed = [s for s in sail if s[4] == "sailed"]
    if sailed:
        s0 = rng.choice(sailed[len(sailed) // 2:])
        others = [v[0] for v in vessels if v[0] != s0[2] and v[1] != "MV Skua"]
        sid += 1
        sail.append([sid, s0[1], rng.choice(others), s0[3], "sailed"])
    for dstr in ("2031-06-01", "2031-06-30", "2031-07-01"):
        cand = [s for s in sail if s[3].startswith(dstr)]
        if cand:
            rng.choice(cand)[4] = "cancelled"
    for _ in range(3 if big else 1):  # plant double-booked vessels: a second departure shortly after another one of the same vessel
        x = rng.choice([s for s in sail if s[4] != "cancelled"])
        sid += 1
        t = datetime.strptime(x[3], "%Y-%m-%d %H:%M") + timedelta(minutes=rng.choice([5, 15, 30]))
        sail.append([sid, rng.choice([r[0] for r in routes]), x[2], t.strftime("%Y-%m-%d %H:%M"), x[4]])
    sail.sort(key=lambda s: s[0])
    # bookings
    book = []
    bid = 0
    for s in sail:
        r = rmap[s[1]]
        v = next(x for x in vessels if x[0] == s[2])
        nb = 0 if rng.random() < 0.12 else rng.randint(1, 6 if big else 5)
        sd = datetime.strptime(s[3][:10], "%Y-%m-%d").date()
        for _ in range(nb):
            bid += 1
            pax = rng.choices([1, 2, 3, 4, 5, 6], [5, 5, 3, 2, 1, 1])[0]
            cars = rng.choices([0, 1, 2], [5, 3, 1])[0]
            lead = rng.choices([0, 1, 2, 3, 4, 7, 10, 14, 15, 21, 30, 40], [3, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1])[0]
            paid = pax * r[5] + cars * r[6]
            cancelled = 1 if (s[4] == "cancelled" or rng.random() < 0.12) else 0
            if cancelled:
                paid = paid // 7
            who = f"{rng.choice(FIRST[:10 if not big else 16])} {rng.choice(LAST[:4 if not big else 12])}"
            book.append((bid, s[0], who, pax, cars, paid, (sd - timedelta(days=lead)).isoformat(), cancelled))
    # plant nearly-full and overbooked sailings (including exactly 85% and exactly full)
    vcap = {v[0]: v for v in vessels}
    cands = [s for s in sail if s[4] != "cancelled"]
    for s in rng.sample(cands, min(len(cands), 8 if big else 4)):
        v = vcap[s[2]]
        target = round(v[2] * rng.choice([0.8, 0.85, 0.85, 0.9, 1.0, 1.1]))
        cur = sum(b[3] for b in book if b[1] == s[0] and not b[7])
        r = rmap[s[1]]
        sd = datetime.strptime(s[3][:10], "%Y-%m-%d").date()
        while cur < target:
            bid += 1
            pax = min(rng.randint(1, 6), target - cur)
            cars = rng.choice([0, 0, 1, 2])
            who = f"{rng.choice(FIRST[:10 if not big else 16])} {rng.choice(LAST[:4 if not big else 12])}"
            book.append((bid, s[0], who, pax, cars, pax * r[5] + cars * r[6], (sd - timedelta(days=rng.randint(0, 20))).isoformat(), 0))
            cur += pax
    return {"ports": ports, "vessels": vessels, "routes": routes, "sailings": [tuple(s) for s in sail], "bookings": book}


DOMAIN = K.Domain("ferry", "Skerry Line: ferry bookings", SCHEMA, DOC, gen)

S = K.Spec

SPECS = [
    S("cancelled-june", 1,
      "Ops wants a list of every sailing cancelled in June 2031 (by departure date): the sailing id, the names of the origin and destination ports, and the departure time. "
      "Oldest departure first; if two share a departure time, lower sailing id first.",
      """SELECT s.sailing_id, o.name AS origin, d.name AS destination, s.departs_at
FROM sailings s
JOIN routes r ON r.route_id = s.route_id
JOIN ports o ON o.port_id = r.origin_id
JOIN ports d ON d.port_id = r.dest_id
WHERE s.status = 'cancelled' AND s.departs_at >= '2031-06-01' AND s.departs_at < '2031-07-01'
ORDER BY s.departs_at, s.sailing_id;""",
      ["sailing_id", "origin", "destination", "departs_at"], ordered=True,
      wrong=("""SELECT s.sailing_id, o.name, d.name, s.departs_at FROM sailings s JOIN routes r ON r.route_id = s.route_id
JOIN ports o ON o.port_id = r.origin_id JOIN ports d ON d.port_id = r.dest_id
WHERE s.status = 'cancelled' AND s.departs_at BETWEEN '2031-06-01' AND '2031-06-30' ORDER BY s.departs_at, s.sailing_id;""",)),
    S("vessel-workload", 2,
      "Give me a workload line per vessel: how many sailings it has actually sailed, and how many foot passengers it carried on them (cancelled bookings carry nobody). "
      "Vessels that have not sailed at all still need a row with zeros. Busiest first, ties by vessel name.",
      """SELECT v.name AS vessel,
       COUNT(DISTINCT s.sailing_id) AS sailings,
       COALESCE(SUM(CASE WHEN b.cancelled = 0 THEN b.pax END), 0) AS passengers
FROM vessels v
LEFT JOIN sailings s ON s.vessel_id = v.vessel_id AND s.status = 'sailed'
LEFT JOIN bookings b ON b.sailing_id = s.sailing_id
GROUP BY v.vessel_id
ORDER BY passengers DESC, v.name;""",
      ["vessel", "sailings", "passengers"], ordered=True,
      wrong=("""SELECT v.name, COUNT(*) AS sailings, COALESCE(SUM(b.pax), 0) FROM vessels v
LEFT JOIN sailings s ON s.vessel_id = v.vessel_id AND s.status = 'sailed'
LEFT JOIN bookings b ON b.sailing_id = s.sailing_id AND b.cancelled = 0
GROUP BY v.vessel_id ORDER BY 3 DESC, v.name;""",
             """SELECT v.name, COUNT(DISTINCT s.sailing_id), SUM(b.pax) FROM vessels v
JOIN sailings s ON s.vessel_id = v.vessel_id AND s.status = 'sailed'
JOIN bookings b ON b.sailing_id = s.sailing_id AND b.cancelled = 0
GROUP BY v.vessel_id ORDER BY 3 DESC, v.name;""")),
    S("fill-rate-85", 2,
      "Which sailed sailings were nearly full? Count the foot passengers on non-cancelled bookings and compare with the vessel's passenger capacity; "
      "I want the ones at 85% or more, with the fill percentage rounded to one decimal. Fullest first, then lowest sailing id.",
      """SELECT s.sailing_id, v.name AS vessel, SUM(b.pax) AS pax, v.pax_capacity AS capacity,
       ROUND(100.0 * SUM(b.pax) / v.pax_capacity, 1) AS fill_pct
FROM sailings s
JOIN vessels v ON v.vessel_id = s.vessel_id
JOIN bookings b ON b.sailing_id = s.sailing_id AND b.cancelled = 0
WHERE s.status = 'sailed'
GROUP BY s.sailing_id
HAVING 100.0 * SUM(b.pax) >= 85.0 * v.pax_capacity
ORDER BY fill_pct DESC, s.sailing_id;""",
      ["sailing_id", "vessel", "pax", "capacity", "fill_pct"], ordered=True,
      wrong=("""SELECT s.sailing_id, v.name, SUM(b.pax), v.pax_capacity, ROUND(100.0 * SUM(b.pax) / v.pax_capacity, 1) AS fill_pct
FROM sailings s JOIN vessels v ON v.vessel_id = s.vessel_id JOIN bookings b ON b.sailing_id = s.sailing_id
WHERE s.status = 'sailed' GROUP BY s.sailing_id HAVING fill_pct >= 85 ORDER BY fill_pct DESC, s.sailing_id;""",)),
    S("round-trippers", 3,
      "Marketing wants the 'round trippers': passengers who have actually travelled (non-cancelled booking on a sailed sailing) both from Harrow Quay to Skerry Head and from Skerry Head to Harrow Quay. "
      "Each booking counts as one trip no matter how many pax it has. Show the name and the number of trips each way, sorted by name.",
      """WITH trips AS (
  SELECT b.passenger, o.name AS origin, d.name AS dest
  FROM bookings b
  JOIN sailings s ON s.sailing_id = b.sailing_id AND s.status = 'sailed'
  JOIN routes r ON r.route_id = s.route_id
  JOIN ports o ON o.port_id = r.origin_id
  JOIN ports d ON d.port_id = r.dest_id
  WHERE b.cancelled = 0
)
SELECT passenger,
       SUM(origin = 'Harrow Quay' AND dest = 'Skerry Head') AS outbound,
       SUM(origin = 'Skerry Head' AND dest = 'Harrow Quay') AS inbound
FROM trips
GROUP BY passenger
HAVING outbound > 0 AND inbound > 0
ORDER BY passenger;""",
      ["passenger", "outbound", "inbound"], ordered=True,
      wrong=("""SELECT passenger, SUM(origin = 'Harrow Quay' AND dest = 'Skerry Head') AS outbound, SUM(origin = 'Skerry Head' AND dest = 'Harrow Quay') AS inbound
FROM (SELECT b.passenger, o.name AS origin, d.name AS dest FROM bookings b JOIN sailings s ON s.sailing_id = b.sailing_id
JOIN routes r ON r.route_id = s.route_id JOIN ports o ON o.port_id = r.origin_id JOIN ports d ON d.port_id = r.dest_id
WHERE b.cancelled = 0) GROUP BY passenger HAVING outbound > 0 AND inbound > 0 ORDER BY passenger;""",)),
    S("latest-sailed-per-route", 3,
      "For each route, which sailing was the most recent one that actually sailed, and which vessel did it? "
      "When two sailings of a route share a departure time, the higher sailing id counts as the later one. Routes that never sailed are left out. Order by route id.",
      """SELECT route_id, sailing_id, departs_at, vessel FROM (
  SELECT s.route_id, s.sailing_id, s.departs_at, v.name AS vessel,
         ROW_NUMBER() OVER (PARTITION BY s.route_id ORDER BY s.departs_at DESC, s.sailing_id DESC) AS rn
  FROM sailings s JOIN vessels v ON v.vessel_id = s.vessel_id
  WHERE s.status = 'sailed'
) WHERE rn = 1
ORDER BY route_id;""",
      ["route_id", "sailing_id", "departs_at", "vessel"], ordered=True,
      wrong=("""SELECT s.route_id, s.sailing_id, s.departs_at, v.name FROM sailings s JOIN vessels v ON v.vessel_id = s.vessel_id
WHERE s.status = 'sailed' AND s.departs_at = (SELECT MAX(x.departs_at) FROM sailings x WHERE x.route_id = s.route_id AND x.status = 'sailed')
ORDER BY s.route_id;""",)),
    S("vessel-running-revenue", 3,
      "Finance needs a daily revenue sheet per vessel. For every vessel and every date on which it sailed something that took at least one booking, sum `paid_cents` of the bookings on that date's sailed sailings "
      "(cancelled bookings count, the fee is real money), and add a running total per vessel in date order. Sort by vessel name, then date.",
      """WITH daily AS (
  SELECT v.name AS vessel, substr(s.departs_at, 1, 10) AS day, SUM(b.paid_cents) AS revenue_cents
  FROM sailings s
  JOIN vessels v ON v.vessel_id = s.vessel_id
  JOIN bookings b ON b.sailing_id = s.sailing_id
  WHERE s.status = 'sailed'
  GROUP BY v.vessel_id, day
)
SELECT vessel, day, revenue_cents,
       SUM(revenue_cents) OVER (PARTITION BY vessel ORDER BY day) AS running_cents
FROM daily
ORDER BY vessel, day;""",
      ["vessel", "day", "revenue_cents", "running_cents"], ordered=True,
      wrong=("""WITH daily AS (SELECT v.name AS vessel, substr(s.departs_at, 1, 10) AS day, SUM(b.paid_cents) AS revenue_cents
FROM sailings s JOIN vessels v ON v.vessel_id = s.vessel_id JOIN bookings b ON b.sailing_id = s.sailing_id
WHERE s.status = 'sailed' AND b.cancelled = 0 GROUP BY v.vessel_id, day)
SELECT vessel, day, revenue_cents, SUM(revenue_cents) OVER (PARTITION BY vessel ORDER BY day) FROM daily ORDER BY vessel, day;""",)),
    S("booking-lead-buckets", 3,
      "How early do people book? Per route (label it `Origin > Destination` with the port names) count the non-cancelled bookings by lead time, "
      "meaning whole days between `booked_on` and the sailing's date: same day, 1 to 3 days, 4 to 14 days, 15 days or more. One row per route label that has any such booking, sorted by label.",
      """SELECT o.name || ' > ' || d.name AS route,
       SUM(x.lead = 0) AS same_day,
       SUM(x.lead BETWEEN 1 AND 3) AS d1_3,
       SUM(x.lead BETWEEN 4 AND 14) AS d4_14,
       SUM(x.lead >= 15) AS d15_plus
FROM (
  SELECT s.route_id,
         CAST(julianday(substr(s.departs_at, 1, 10)) - julianday(b.booked_on) AS INTEGER) AS lead
  FROM bookings b JOIN sailings s ON s.sailing_id = b.sailing_id
  WHERE b.cancelled = 0
) x
JOIN routes r ON r.route_id = x.route_id
JOIN ports o ON o.port_id = r.origin_id
JOIN ports d ON d.port_id = r.dest_id
GROUP BY r.route_id
ORDER BY route;""",
      ["route", "same_day", "d1_3", "d4_14", "d15_plus"], ordered=True,
      wrong=("""SELECT o.name || ' > ' || d.name AS route, SUM(x.lead = 0), SUM(x.lead BETWEEN 1 AND 3), SUM(x.lead BETWEEN 4 AND 14), SUM(x.lead >= 15)
FROM (SELECT s.route_id, CAST(julianday(substr(s.departs_at, 1, 10)) - julianday(b.booked_on) AS INTEGER) AS lead FROM bookings b JOIN sailings s ON s.sailing_id = b.sailing_id) x
JOIN routes r ON r.route_id = x.route_id JOIN ports o ON o.port_id = r.origin_id JOIN ports d ON d.port_id = r.dest_id GROUP BY r.route_id ORDER BY route;""",)),
    S("overbooked-sailings", 3,
      "Find the sailings (scheduled or sailed, not cancelled ones) where the non-cancelled bookings add up to more foot passengers or more cars than the vessel can take. "
      "Show by how much each limit is exceeded, with 0 for a limit that is respected. Sort by sailing id.",
      """SELECT s.sailing_id, v.name AS vessel,
       MAX(SUM(b.pax) - v.pax_capacity, 0) AS pax_over,
       MAX(SUM(b.cars) - v.car_capacity, 0) AS cars_over
FROM sailings s
JOIN vessels v ON v.vessel_id = s.vessel_id
JOIN bookings b ON b.sailing_id = s.sailing_id AND b.cancelled = 0
WHERE s.status <> 'cancelled'
GROUP BY s.sailing_id
HAVING SUM(b.pax) > v.pax_capacity OR SUM(b.cars) > v.car_capacity
ORDER BY s.sailing_id;""",
      ["sailing_id", "vessel", "pax_over", "cars_over"], ordered=True,
      wrong=("""SELECT s.sailing_id, v.name, MAX(SUM(b.pax) - v.pax_capacity, 0), MAX(SUM(b.cars) - v.car_capacity, 0)
FROM sailings s JOIN vessels v ON v.vessel_id = s.vessel_id JOIN bookings b ON b.sailing_id = s.sailing_id
WHERE s.status <> 'cancelled' GROUP BY s.sailing_id HAVING SUM(b.pax) > v.pax_capacity OR SUM(b.cars) > v.car_capacity ORDER BY s.sailing_id;""",)),
    S("vessel-idle-gaps", 4,
      "Harbour master question: for each vessel, look at its sailed sailings in departure order and find the consecutive pairs where it sat idle for more than 6 hours "
      "between arriving from one and departing on the next (arrival = departure + the route's `duration_min`). "
      "Show vessel name, both sailing ids and the idle time in hours rounded to 2 decimals. Order by vessel name, then the first sailing's id.",
      """WITH legs AS (
  SELECT s.vessel_id, s.sailing_id, s.departs_at,
         CAST(strftime('%s', s.departs_at) AS INTEGER) AS t0,
         CAST(strftime('%s', s.departs_at) AS INTEGER) + r.duration_min * 60 AS t1
  FROM sailings s JOIN routes r ON r.route_id = s.route_id
  WHERE s.status = 'sailed'
), pairs AS (
  SELECT vessel_id, sailing_id AS first_id, t1,
         LEAD(sailing_id) OVER w AS next_id, LEAD(t0) OVER w AS next_t0
  FROM legs
  WINDOW w AS (PARTITION BY vessel_id ORDER BY t0, sailing_id)
)
SELECT v.name AS vessel, p.first_id, p.next_id, ROUND((p.next_t0 - p.t1) / 3600.0, 2) AS idle_hours
FROM pairs p JOIN vessels v ON v.vessel_id = p.vessel_id
WHERE p.next_id IS NOT NULL AND p.next_t0 - p.t1 > 6 * 3600
ORDER BY v.name, p.first_id;""",
      ["vessel", "first_sailing", "next_sailing", "idle_hours"], ordered=True,
      wrong=("""WITH legs AS (SELECT s.vessel_id, s.sailing_id, CAST(strftime('%s', s.departs_at) AS INTEGER) AS t0, CAST(strftime('%s', s.departs_at) AS INTEGER) + r.duration_min * 60 AS t1
FROM sailings s JOIN routes r ON r.route_id = s.route_id WHERE s.status <> 'cancelled'),
pairs AS (SELECT vessel_id, sailing_id AS first_id, t1, LEAD(sailing_id) OVER w AS next_id, LEAD(t0) OVER w AS next_t0 FROM legs WINDOW w AS (PARTITION BY vessel_id ORDER BY t0, sailing_id))
SELECT v.name, p.first_id, p.next_id, ROUND((p.next_t0 - p.t1) / 3600.0, 2) FROM pairs p JOIN vessels v ON v.vessel_id = p.vessel_id
WHERE p.next_id IS NOT NULL AND p.next_t0 - p.t1 > 6 * 3600 ORDER BY v.name, p.first_id;""",)),
    S("double-booked-vessels", 4,
      "A vessel can't be in two places at once, but the timetable tool lets it happen. List every pair of non-cancelled sailings of the same vessel whose crossing times overlap "
      "(a sailing occupies its vessel from `departs_at` until `departs_at` plus the route's `duration_min`; leaving the very minute the other one arrives is fine). "
      "One row per pair with the smaller sailing id first, sorted by vessel id, then the two ids.",
      """WITH legs AS (
  SELECT s.sailing_id, s.vessel_id,
         CAST(strftime('%s', s.departs_at) AS INTEGER) AS t0,
         CAST(strftime('%s', s.departs_at) AS INTEGER) + r.duration_min * 60 AS t1
  FROM sailings s JOIN routes r ON r.route_id = s.route_id
  WHERE s.status <> 'cancelled'
)
SELECT a.vessel_id, a.sailing_id AS sailing_a, b.sailing_id AS sailing_b
FROM legs a
JOIN legs b ON b.vessel_id = a.vessel_id AND a.sailing_id < b.sailing_id AND a.t0 < b.t1 AND b.t0 < a.t1
ORDER BY a.vessel_id, a.sailing_id, b.sailing_id;""",
      ["vessel_id", "sailing_a", "sailing_b"], ordered=True,
      wrong=("""WITH legs AS (SELECT s.sailing_id, s.vessel_id, CAST(strftime('%s', s.departs_at) AS INTEGER) AS t0, CAST(strftime('%s', s.departs_at) AS INTEGER) + r.duration_min * 60 AS t1
FROM sailings s JOIN routes r ON r.route_id = s.route_id WHERE s.status <> 'cancelled')
SELECT a.vessel_id, a.sailing_id, b.sailing_id FROM legs a JOIN legs b ON b.vessel_id = a.vessel_id AND a.sailing_id < b.sailing_id AND a.t0 <= b.t1 AND b.t0 <= a.t1
ORDER BY a.vessel_id, a.sailing_id, b.sailing_id;""",)),
    S("cheapest-multi-leg", 4,
      "Passengers ask what the cheapest way from Harrow Quay to each other port is if they are willing to change ferries up to twice (so at most 3 legs in a row along existing routes, ignoring timetables). "
      "The price of a trip is the sum of the legs' `base_fare_cents`. For every port you can reach, give the lowest total and the smallest number of legs that achieves that lowest total. "
      "Do not list Harrow Quay itself. Sort by port name.",
      """WITH RECURSIVE trip(port_id, legs, fare) AS (
  SELECT port_id, 0, 0 FROM ports WHERE name = 'Harrow Quay'
  UNION ALL
  SELECT r.dest_id, t.legs + 1, t.fare + r.base_fare_cents
  FROM trip t JOIN routes r ON r.origin_id = t.port_id
  WHERE t.legs < 3
), best AS (
  SELECT port_id, MIN(fare) AS fare FROM trip WHERE legs > 0 GROUP BY port_id
)
SELECT p.name AS port, b.fare AS cheapest_cents, MIN(t.legs) AS legs
FROM best b
JOIN trip t ON t.port_id = b.port_id AND t.fare = b.fare AND t.legs > 0
JOIN ports p ON p.port_id = b.port_id
WHERE p.name <> 'Harrow Quay'
GROUP BY p.port_id
ORDER BY p.name;""",
      ["port", "cheapest_cents", "legs"], ordered=True, show=False,
      wrong=("""WITH RECURSIVE trip(port_id, legs, fare) AS (
  SELECT port_id, 0, 0 FROM ports WHERE name = 'Harrow Quay'
  UNION ALL SELECT r.dest_id, t.legs + 1, t.fare + r.base_fare_cents FROM trip t JOIN routes r ON r.origin_id = t.port_id WHERE t.legs < 2)
SELECT p.name, MIN(t.fare), MIN(t.legs) FROM trip t JOIN ports p ON p.port_id = t.port_id WHERE t.legs > 0 AND p.name <> 'Harrow Quay' GROUP BY p.port_id ORDER BY p.name;""",)),
    S("silver-tier-crossing", 4,
      "Customer loyalty: a passenger reaches Silver when the running total of their `paid_cents` over non-cancelled bookings (in order of `booked_on`, then `booking_id`) first reaches 25000 cents. "
      "For each passenger who got there, show the booking that took them over the line, with the running total at that point. Order the output by booked_on, then booking_id.",
      """WITH run AS (
  SELECT booking_id, passenger, booked_on,
         SUM(paid_cents) OVER (PARTITION BY passenger ORDER BY booked_on, booking_id) AS total
  FROM bookings
  WHERE cancelled = 0
), hit AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY passenger ORDER BY booked_on, booking_id) AS rn
  FROM run WHERE total >= 25000
)
SELECT passenger, booking_id, booked_on, total AS running_total_cents
FROM hit WHERE rn = 1
ORDER BY booked_on, booking_id;""",
      ["passenger", "booking_id", "booked_on", "running_total_cents"], ordered=True,
      wrong=("""WITH run AS (SELECT booking_id, passenger, booked_on, SUM(paid_cents) OVER (PARTITION BY passenger ORDER BY booked_on, booking_id) AS total FROM bookings),
hit AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY passenger ORDER BY booked_on, booking_id) AS rn FROM run WHERE total >= 25000)
SELECT passenger, booking_id, booked_on, total FROM hit WHERE rn = 1 ORDER BY booked_on, booking_id;""",)),
    S("fix-vessel-workload-fanout", 2,
      "The vessel workload report on the ops dashboard is wrong: on the sample data it lists @ROWS_BAD@ vessels but there are @ROWS_GOOD@ in the fleet, and the passenger totals look inflated. "
      "`query.sql` is supposed to give, per vessel, the number of sailed sailings and the foot passengers carried on them (non-cancelled bookings only), with zeros for vessels that have not sailed; "
      "busiest first, ties by vessel name. Please repair it.",
      ref="""SELECT v.name AS vessel,
       COUNT(DISTINCT s.sailing_id) AS sailings,
       COALESCE(SUM(CASE WHEN b.cancelled = 0 THEN b.pax END), 0) AS passengers
FROM vessels v
LEFT JOIN sailings s ON s.vessel_id = v.vessel_id AND s.status = 'sailed'
LEFT JOIN bookings b ON b.sailing_id = s.sailing_id
GROUP BY v.vessel_id
ORDER BY passengers DESC, v.name;""",
      cols=["vessel", "sailings", "passengers"], ordered=True, show=False,
      buggy="""SELECT v.name AS vessel, COUNT(*) AS sailings, SUM(b.pax) AS passengers
FROM vessels v
JOIN sailings s ON s.vessel_id = v.vessel_id
JOIN bookings b ON b.sailing_id = s.sailing_id
WHERE s.status = 'sailed'
GROUP BY v.name
ORDER BY passengers DESC, v.name;"""),
]


@family("data-ferry-timetable", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL reports on an island ferry company: joins, windows, recursion, interval overlap")
def ferry(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
