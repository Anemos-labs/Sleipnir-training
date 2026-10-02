"""SQL tasks on an invented bus network's tap-in/tap-out records (pairing taps with LEAD, zone fares and discounts, daily caps, transfers, duplicates)."""
from datetime import datetime, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE cards (
      card_id     INTEGER PRIMARY KEY,
      holder      TEXT NOT NULL CHECK (holder IN ('adult', 'student', 'senior')),
      issued_on   TEXT NOT NULL
    );
    CREATE TABLE stops (
      stop_id  INTEGER PRIMARY KEY,
      name     TEXT NOT NULL UNIQUE,
      zone     INTEGER NOT NULL
    );
    CREATE TABLE taps (
      tap_id     INTEGER PRIMARY KEY,
      card_id    INTEGER NOT NULL REFERENCES cards(card_id),
      tapped_at  TEXT NOT NULL,                -- YYYY-MM-DD HH:MM
      stop_id    INTEGER NOT NULL REFERENCES stops(stop_id),
      kind       TEXT NOT NULL CHECK (kind IN ('in', 'out'))
    );
    CREATE TABLE fares (
      zone_lo      INTEGER NOT NULL,
      zone_hi      INTEGER NOT NULL,
      adult_cents  INTEGER NOT NULL,
      PRIMARY KEY (zone_lo, zone_hi)
    );
''')

DOC = dd('''
    The Marl County bus network charges by zone and records every tap of a travel card.

    * Taps of one card are ordered by `tapped_at` (ties by `tap_id`). A **journey** is a tap `in` immediately followed (in that order, with no tap between) by a tap `out` of the same card.
      An `in` that is followed by another `in`, or by nothing, is an **incomplete journey**; an `out` that does not follow an `in` is ignored.
    * The fare of a complete journey comes from `fares` using the lower and the higher of the two stop zones (`zone_lo <= zone_hi`) and is the **adult** price.
      Students pay 50% and seniors 60% of it, computed as `(adult_cents * percent + 50) / 100` in integer arithmetic (half up). Incomplete journeys are not charged here.
    * The **day** of a journey is the date of its `in` tap.
    * A card's charge for a day is capped at **900 cents**: the sum of that day's journey fares, but never more than 900.
    * Timestamps are `YYYY-MM-DD HH:MM` text (24-hour clock, no seconds).
''')

STOPS = [("Mill Lane", 1), ("Town Hall", 1), ("Canal Basin", 1), ("Orchard Cross", 2), ("Quarry Gate", 2), ("Heron Park", 2), ("Far Ridge", 3), ("Wolds End", 3)]
FARES = [(1, 1, 225), (1, 2, 315), (1, 3, 425), (2, 2, 245), (2, 3, 335), (3, 3, 265)]
JOURNEYS = """WITH t AS (
  SELECT tap_id, card_id, tapped_at, stop_id, kind,
         LEAD(kind) OVER w AS next_kind, LEAD(tapped_at) OVER w AS next_at, LEAD(stop_id) OVER w AS next_stop
  FROM taps WINDOW w AS (PARTITION BY card_id ORDER BY tapped_at, tap_id)
), j AS (
  SELECT card_id, tap_id AS in_tap, tapped_at AS in_at, stop_id AS in_stop, next_at AS out_at, next_stop AS out_stop FROM t WHERE kind = 'in' AND next_kind = 'out'
), f AS (
  SELECT j.*, c.holder, zi.zone AS zin, zo.zone AS zout,
         (SELECT fa.adult_cents FROM fares fa WHERE fa.zone_lo = MIN(zi.zone, zo.zone) AND fa.zone_hi = MAX(zi.zone, zo.zone)) AS adult
  FROM j JOIN cards c ON c.card_id = j.card_id JOIN stops zi ON zi.stop_id = j.in_stop JOIN stops zo ON zo.stop_id = j.out_stop
), p AS (
  SELECT f.*, (adult * CASE holder WHEN 'student' THEN 50 WHEN 'senior' THEN 60 ELSE 100 END + 50) / 100 AS fare, substr(in_at, 1, 10) AS day FROM f
)"""


BUGGY_J = JOURNEYS.replace("(adult * CASE holder WHEN 'student' THEN 50 WHEN 'senior' THEN 60 ELSE 100 END + 50) / 100", "CAST(ROUND(adult * 0.5) AS INTEGER)")


def gen(rng, big):
    nc = 12 if big else 5
    cards = [(i + 1, rng.choice(["adult", "adult", "student", "senior"]), f"2037-{rng.randint(1, 6):02d}-{rng.randint(1, 28):02d}") for i in range(nc)]
    cards[1] = (cards[1][0], "adult", cards[1][2])
    stops = [(i + 1, s[0], s[1]) for i, s in enumerate(STOPS)]
    zone = {s[0]: s[2] for s in stops}
    taps, tid = [], 0
    for c in cards:
        for day in rng.sample(range(1, 22), rng.randint(3, 7) if big else 3):
            t = datetime(2037, 8, day, rng.randint(5, 22), rng.randint(0, 59))
            for _ in range(rng.randint(1, 4)):
                a, b = rng.sample(stops, 2)
                tid += 1
                taps.append((tid, c[0], t.strftime("%Y-%m-%d %H:%M"), a[0], "in"))
                if rng.random() < 0.05:
                    tid += 1
                    taps.append((tid, c[0], (t + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"), a[0], "in"))
                t += timedelta(minutes=rng.randint(9, 55))
                if rng.random() > 0.08:
                    tid += 1
                    taps.append((tid, c[0], t.strftime("%Y-%m-%d %H:%M"), b[0], "out"))
                t += timedelta(minutes=rng.choice([5, 20, 29, 30, 31, 90]))
    # plant: a heavy day above the cap for the first card, a transfer window of exactly 30 minutes, an 'out' without 'in', two identical taps
    c0 = cards[0][0]
    t = datetime(2037, 8, 25, 6, 0)
    for k in range(5):
        a, b = (1, 8) if k % 2 == 0 else (8, 1)
        tid += 1
        taps.append((tid, c0, t.strftime("%Y-%m-%d %H:%M"), a, "in"))
        t += timedelta(minutes=40)
        tid += 1
        taps.append((tid, c0, t.strftime("%Y-%m-%d %H:%M"), b, "out"))
        t += timedelta(minutes=30 if k < 2 else 120)
    t = datetime(2037, 8, 27, 10, 0)  # exactly 900 cents in one day: four zone-1 journeys at 225
    for k in range(4):
        tid += 1
        taps.append((tid, cards[1][0], t.strftime("%Y-%m-%d %H:%M"), 1 + k % 2, "in"))
        t += timedelta(minutes=12)
        tid += 1
        taps.append((tid, cards[1][0], t.strftime("%Y-%m-%d %H:%M"), 2 - k % 2, "out"))
        t += timedelta(minutes=45)
    tid += 1
    taps.append((tid, cards[-1][0], "2037-08-26 09:00", 2, "out"))
    tid += 1
    taps.append((tid, cards[-1][0], "2037-08-26 09:02", 3, "in"))
    tid += 1
    taps.append((tid, cards[-1][0], "2037-08-26 09:02", 3, "in"))
    tid += 1
    taps.append((tid, cards[-1][0], "2037-08-26 09:30", 4, "out"))
    return {"cards": cards, "stops": stops, "taps": taps, "fares": FARES}


DOMAIN = K.Domain("busfares", "Marl County buses: taps and fares", SCHEMA, DOC, gen)
S = K.Spec

SPECS = [
    S("taps-by-kind", 1, "How many taps of each kind (`in` / `out`) did each holder category make? Columns: holder, kind, taps. Order by holder, then kind.",
      "SELECT c.holder, t.kind, COUNT(*) AS taps FROM taps t JOIN cards c ON c.card_id = t.card_id GROUP BY c.holder, t.kind ORDER BY c.holder, t.kind;", ["holder", "kind", "taps"], ordered=True),
    S("journey-durations", 3,
      "List the complete journeys that took 45 minutes or longer: card id, in time, out time, duration in minutes (out minus in; both are on the same day). Longest first, ties by card id then in time.",
      f"""{JOURNEYS}
SELECT card_id, in_at, out_at, CAST(ROUND((julianday(out_at) - julianday(in_at)) * 1440) AS INTEGER) AS minutes FROM j WHERE (julianday(out_at) - julianday(in_at)) * 1440 >= 44.5 ORDER BY minutes DESC, card_id, in_at;""",
      ["card_id", "in_at", "out_at", "minutes"], ordered=True,
      wrong=("""SELECT a.card_id, a.tapped_at, b.tapped_at, CAST(ROUND((julianday(b.tapped_at) - julianday(a.tapped_at)) * 1440) AS INTEGER) AS m FROM taps a JOIN taps b ON b.card_id = a.card_id AND b.kind = 'out' AND b.tapped_at > a.tapped_at WHERE a.kind = 'in' AND (julianday(b.tapped_at) - julianday(a.tapped_at)) * 1440 >= 44.5 ORDER BY m DESC, a.card_id, a.tapped_at;""",)),
    S("incomplete-journeys", 3,
      "Find the incomplete journeys: `in` taps that are not followed by an `out` tap of the same card before the card's next tap of any kind (or that are the card's last tap). Columns: card id, in time, stop name. Order by card id, then in time.",
      """WITH t AS (SELECT tap_id, card_id, tapped_at, stop_id, kind, LEAD(kind) OVER (PARTITION BY card_id ORDER BY tapped_at, tap_id) AS next_kind FROM taps)
SELECT t.card_id, t.tapped_at AS in_at, s.name AS stop FROM t JOIN stops s ON s.stop_id = t.stop_id WHERE t.kind = 'in' AND (t.next_kind IS NULL OR t.next_kind = 'in') ORDER BY t.card_id, t.tapped_at, t.tap_id;""",
      ["card_id", "in_at", "stop"], ordered=True, allow_empty=True,
      wrong=("""SELECT t.card_id, t.tapped_at, s.name FROM taps t JOIN stops s ON s.stop_id = t.stop_id WHERE t.kind = 'in' AND NOT EXISTS (SELECT 1 FROM taps o WHERE o.card_id = t.card_id AND o.kind = 'out' AND o.tapped_at > t.tapped_at) ORDER BY t.card_id, t.tapped_at;""",)),
    S("fares-by-holder-and-zones", 4,
      "Revenue by holder category and zone pair: for every holder category and every pair (lower zone, higher zone) of the stops of a complete journey, the number of journeys and the total fare in cents after the discount (see the notes for the exact formula). "
      "Columns: holder, zone_lo, zone_hi, journeys, total fare. Order by holder, zone_lo, zone_hi.",
      f"""{JOURNEYS}
SELECT holder, MIN(zin, zout) AS zone_lo, MAX(zin, zout) AS zone_hi, COUNT(*) AS journeys, SUM(fare) AS total_cents FROM p GROUP BY holder, MIN(zin, zout), MAX(zin, zout) ORDER BY holder, zone_lo, zone_hi;""",
      ["holder", "zone_lo", "zone_hi", "journeys", "total_cents"], ordered=True,
      wrong=(f"""{JOURNEYS}
SELECT holder, MIN(zin, zout), MAX(zin, zout), COUNT(*), SUM(adult * CASE holder WHEN 'student' THEN 50 WHEN 'senior' THEN 60 ELSE 100 END / 100) FROM p GROUP BY holder, MIN(zin, zout), MAX(zin, zout) ORDER BY holder, 2, 3;""",)),
    S("daily-capped-charge", 5,
      "Daily charges: for every card and day with at least one complete journey, the uncapped sum of the journey fares, the capped charge (never more than 900) and how many journeys it covers. Only rows where the cap actually reduced the charge. "
      "Columns: card id, day, journeys, uncapped, charged. Order by card id, then day.",
      f"""{JOURNEYS}
SELECT card_id, day, COUNT(*) AS journeys, SUM(fare) AS uncapped, MIN(SUM(fare), 900) AS charged FROM p GROUP BY card_id, day HAVING SUM(fare) > 900 ORDER BY card_id, day;""",
      ["card_id", "day", "journeys", "uncapped", "charged"], ordered=True, allow_empty=True,
      wrong=(f"""{JOURNEYS}
SELECT card_id, day, COUNT(*), SUM(fare), 900 FROM p GROUP BY card_id, day HAVING SUM(fare) >= 900 ORDER BY card_id, day;""",)),
    S("revenue-per-day", 4,
      "Network revenue per day: add up the capped daily charges of all cards (a card's charge for a day is the sum of its journey fares but at most 900) and give day, number of cards that travelled, and revenue in cents. Order by day.",
      f"""{JOURNEYS}
, d AS (SELECT card_id, day, MIN(SUM(fare), 900) AS charged FROM p GROUP BY card_id, day)
SELECT day, COUNT(*) AS cards, SUM(charged) AS revenue FROM d GROUP BY day ORDER BY day;""",
      ["day", "cards", "revenue"], ordered=True,
      wrong=(f"""{JOURNEYS}
SELECT day, COUNT(DISTINCT card_id), SUM(fare) FROM p GROUP BY day ORDER BY day;""",)),
    S("transfers", 4,
      "Transfers: a journey is a transfer when the same card's previous complete journey ended no more than 30 minutes before (out time to in time, an exact 30 minutes counts) and the previous journey is the immediately preceding complete journey of that card. "
      "Report per card the number of transfers and the number of journeys. Cards without any transfer are left out. Order by transfers descending, then card id.",
      f"""{JOURNEYS}
, k AS (SELECT card_id, in_at, LAG(out_at) OVER (PARTITION BY card_id ORDER BY in_at, in_tap) AS prev_out FROM j)
SELECT card_id, SUM(prev_out IS NOT NULL AND (julianday(in_at) - julianday(prev_out)) * 1440 <= 30.5) AS transfers, COUNT(*) AS journeys FROM k GROUP BY card_id HAVING SUM(prev_out IS NOT NULL AND (julianday(in_at) - julianday(prev_out)) * 1440 <= 30.5) > 0 ORDER BY transfers DESC, card_id;""",
      ["card_id", "transfers", "journeys"], ordered=True,
      wrong=(f"""{JOURNEYS}
, k AS (SELECT card_id, in_at, LAG(out_at) OVER (PARTITION BY card_id ORDER BY in_at, in_tap) AS prev_out FROM j)
SELECT card_id, SUM(prev_out IS NOT NULL AND (julianday(in_at) - julianday(prev_out)) * 1440 < 29.5), COUNT(*) FROM k GROUP BY card_id HAVING SUM(prev_out IS NOT NULL AND (julianday(in_at) - julianday(prev_out)) * 1440 < 29.5) > 0 ORDER BY 2 DESC, card_id;""",)),
    S("rush-hour", 3,
      "Which hour of the day is busiest? Count the complete journeys by the hour of their `in` tap (0 to 23) and show the three busiest hours: hour, journeys. Ties go to the earlier hour. Order by journeys descending, then hour.",
      f"""{JOURNEYS}
SELECT CAST(substr(in_at, 12, 2) AS INTEGER) AS hour, COUNT(*) AS journeys FROM j GROUP BY hour ORDER BY journeys DESC, hour LIMIT 3;""",
      ["hour", "journeys"], ordered=True),
    S("zone-pairs", 3,
      "How are zones connected? For each origin zone (the zone of the `in` stop) count the complete journeys that ended in zone 1, zone 2 and zone 3 in one row: origin zone, to_1, to_2, to_3 (0 if none). Order by origin zone.",
      f"""{JOURNEYS}
SELECT zin AS origin, SUM(zout = 1) AS to_1, SUM(zout = 2) AS to_2, SUM(zout = 3) AS to_3 FROM f GROUP BY zin ORDER BY zin;""",
      ["origin", "to_1", "to_2", "to_3"], ordered=True),
    S("double-taps", 3,
      "Duplicate taps: for the same card, the same stop and the same kind, a tap that follows another one by at most 2 minutes is a double tap. Chains count from the previous tap, not from the first (A, B 1 minute later, C 2 minutes after B: B and C are double taps). "
      "List the double taps: tap id, card id, time, kind. Order by tap id.",
      """WITH x AS (SELECT tap_id, card_id, tapped_at, kind, LAG(tapped_at) OVER (PARTITION BY card_id, stop_id, kind ORDER BY tapped_at, tap_id) AS prev FROM taps)
SELECT tap_id, card_id, tapped_at, kind FROM x WHERE prev IS NOT NULL AND (julianday(tapped_at) - julianday(prev)) * 1440 <= 2.5 ORDER BY tap_id;""",
      ["tap_id", "card_id", "tapped_at", "kind"], ordered=True, allow_empty=True,
      wrong=("""SELECT t.tap_id, t.card_id, t.tapped_at, t.kind FROM taps t WHERE EXISTS (SELECT 1 FROM taps o WHERE o.card_id = t.card_id AND o.stop_id = t.stop_id AND o.kind = t.kind AND o.tap_id < t.tap_id AND o.tapped_at = t.tapped_at) ORDER BY t.tap_id;""",)),
    S("night-owls", 3,
      "Cards with at least 3 complete journeys that started between 22:00 and 04:59 (inclusive of 22:00:00 up to 04:59): card id, holder and the number of night journeys. Most first, ties by card id.",
      f"""{JOURNEYS}
SELECT p.card_id, p.holder, COUNT(*) AS night_journeys FROM p WHERE substr(p.in_at, 12, 5) >= '22:00' OR substr(p.in_at, 12, 5) <= '04:59' GROUP BY p.card_id HAVING COUNT(*) >= 3 ORDER BY night_journeys DESC, p.card_id;""",
      ["card_id", "holder", "night_journeys"], ordered=True, allow_empty=True,
      wrong=(f"""{JOURNEYS}
SELECT p.card_id, p.holder, COUNT(*) FROM p WHERE substr(p.in_at, 12, 5) >= '22:00' AND substr(p.in_at, 12, 5) <= '04:59' GROUP BY p.card_id HAVING COUNT(*) >= 3 ORDER BY 3 DESC, p.card_id;""",)),
    S("fix-discount-rounding", 3,
      "The fare report in `query.sql` computes the discounted fare with floating point and rounds the wrong way (`ROUND` on a float; the formula must be integer arithmetic `(adult * percent + 50) / 100`), and it forgets that students pay 50% and seniors 60%. "
      "Fix it so that it returns, per holder category, the number of complete journeys and the total fare in cents. Columns: holder, journeys, total fare. Order by holder.",
      ref=f"""{JOURNEYS}
SELECT holder, COUNT(*) AS journeys, SUM(fare) AS total_cents FROM p GROUP BY holder ORDER BY holder;""",
      cols=["holder", "journeys", "total_cents"], ordered=True, show=False,
      buggy=f"""{BUGGY_J}
SELECT holder, COUNT(*) AS journeys, SUM(fare) AS total_cents FROM p GROUP BY holder ORDER BY holder;"""),
]


@family("data-bus-fares", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL on bus tap records: pairing taps with LEAD, zone fares with integer discounts, daily caps, transfers, duplicate taps, night journeys")
def bus_fares(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
