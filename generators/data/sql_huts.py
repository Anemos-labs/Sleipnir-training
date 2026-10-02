"""SQL tasks on an invented network of mountain huts (night expansion with recursive CTEs, overbooking, seasonal pricing, trip chains, gaps)."""
from datetime import date, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE huts (
      hut_id       INTEGER PRIMARY KEY,
      name         TEXT NOT NULL UNIQUE,
      altitude_m   INTEGER NOT NULL,
      beds         INTEGER NOT NULL
    );
    CREATE TABLE rates (
      rate_id          INTEGER PRIMARY KEY,
      hut_id           INTEGER NOT NULL REFERENCES huts(hut_id),
      season           TEXT NOT NULL,
      start_md         TEXT NOT NULL,          -- first day of the window as MM-DD
      end_md           TEXT NOT NULL,          -- last day of the window as MM-DD (inclusive)
      per_night_cents  INTEGER NOT NULL        -- price per person and night
    );
    CREATE TABLE bookings (
      booking_id  INTEGER PRIMARY KEY,
      hut_id      INTEGER NOT NULL REFERENCES huts(hut_id),
      guest       TEXT NOT NULL,
      check_in    TEXT NOT NULL,
      nights      INTEGER NOT NULL,
      party       INTEGER NOT NULL,            -- number of people
      status      TEXT NOT NULL CHECK (status IN ('confirmed', 'cancelled', 'no-show'))
    );
    CREATE TABLE meals (
      meal_id      INTEGER PRIMARY KEY,
      booking_id   INTEGER NOT NULL REFERENCES bookings(booking_id),
      meal         TEXT NOT NULL,               -- dinner, breakfast, packed lunch
      qty          INTEGER NOT NULL,
      price_cents  INTEGER NOT NULL             -- price per portion
    );
''')

DOC = dd('''
    The Rimrock Alpine Club runs a few mountain huts and keeps their booking records for the 2035 season.

    * A booking starts on `check_in` and covers `nights` nights: the nights are `check_in`, `check_in + 1 day`, ... (the check-out morning is not a night). `party` people sleep there.
    * `cancelled` bookings never use beds. `confirmed` and `no-show` bookings do (the beds were held).
    * `rates` give the price per person per night, by season window. A night belongs to the window of its **month-day** (`MM-DD`, both ends included); the windows of a hut do not overlap and cover the whole season.
    * `meals` are extra portions on a booking; they are charged per portion.
    * Dates are ISO text, money is in cents.
''')

HUTS = [("Falcon Saddle", 2350), ("Marmot Col", 2010), ("Ibex Ledge", 2680), ("Gentian Hut", 1790)]
GUESTS = ["Ruth Alder", "Tomas Keel", "Ines Barrow", "Piet Lund", "Sade Orme", "Kai Vance", "Mira Holt", "Odin Rask", "Lena Cobb", "Yusuf Reed", "Anja Voss", "Bruno Tarn"]
MEALS = [("dinner", 2200), ("breakfast", 900), ("packed lunch", 1100)]


def gen(rng, big):
    nh = 4 if big else 2
    huts = [(i + 1, HUTS[i][0], HUTS[i][1], rng.choice([24, 32, 40, 56])) for i in range(nh)]
    rates, rid = [], 0
    for h in huts:
        base = rng.choice([3800, 4200, 4800])
        for season, a, b, mult in (("low", "05-15", "06-30", 1.0), ("high", "07-01", "09-14", 1.35), ("low", "09-15", "10-15", 1.0)):
            rid += 1
            rates.append((rid, h[0], season, a, b, int(base * mult / 50) * 50))
    bookings, meals, bid, mid = [], [], 0, 0
    for _ in range(70 if big else 16):
        bid += 1
        h = rng.choice(huts)
        ci = date(2035, 5, 20) + timedelta(days=rng.randint(0, 135))
        st = rng.choices(["confirmed", "cancelled", "no-show"], [0.82, 0.12, 0.06])[0]
        bookings.append((bid, h[0], rng.choice(GUESTS[:10 if big else 6]), ci.isoformat(), rng.choice([1, 1, 2, 2, 3, 4]), rng.choice([1, 2, 2, 3, 4, 6, 8]), st))
        for _ in range(rng.choice([0, 0, 1, 2, 3])):
            mid += 1
            m = rng.choice(MEALS)
            meals.append((mid, bid, m[0], rng.randint(1, 8), m[1]))
    # plant: a guest walking from hut to hut (each check-in on the previous check-out day), a gap, and an overbooked night
    g = "Ruth Alder"
    d0 = date(2035, 7, 10)
    for k, (h, n) in enumerate(((huts[0][0], 2), (huts[1][0], 1), (huts[0][0], 3))):
        bid += 1
        bookings.append((bid, h, g, d0.isoformat(), n, 2, "confirmed"))
        mid += 1
        meals.append((mid, bid, "dinner", 2, 2200))
        d0 += timedelta(days=n)
    bid += 1
    bookings.append((bid, huts[0][0], g, (d0 + timedelta(days=2)).isoformat(), 1, 2, "confirmed"))  # a gap of two days: a new trip
    for k in range(3):
        bid += 1
        bookings.append((bid, huts[1][0], f"Group {k + 1}", "2035-08-14", 2, huts[1][3] // 2 + 1 if k < 2 else 3, "confirmed" if k < 3 else "cancelled"))
    bid += 1
    bookings.append((bid, huts[1][0], "Group 4", "2035-08-14", 2, 20, "cancelled"))
    for ci, nn in (("2035-09-01", 4), ("2035-09-02", 1), ("2035-10-14", 1)):  # a long stay hides a short one: the quiet spell is measured from the latest check-out
        bid += 1
        bookings.append((bid, huts[-1][0], rng.choice(GUESTS[:6]), ci, nn, 2, "confirmed"))
    ns_guest = rng.choice(GUESTS[3:])
    for _ in range(rng.randint(2, 4) if big else rng.randint(2, 3)):
        bid += 1
        bookings.append((bid, huts[0][0], ns_guest, f"2035-06-{rng.randint(1, 20):02d}", 1, 1, "no-show"))
    if big:
        for _ in range(2):
            bid += 1
            bookings.append((bid, huts[-1][0], rng.choice(GUESTS[:3]), "2035-09-20", 1, 2, "no-show"))
    return {"huts": huts, "rates": rates, "bookings": bookings, "meals": meals}


DOMAIN = K.Domain("huts", "Rimrock Alpine Club: hut bookings 2035", SCHEMA, DOC, gen)
S = K.Spec

NIGHTS = """WITH RECURSIVE n(booking_id, hut_id, party, night, left) AS (
  SELECT booking_id, hut_id, party, check_in, nights - 1 FROM bookings WHERE status <> 'cancelled'
  UNION ALL SELECT booking_id, hut_id, party, date(night, '+1 day'), left - 1 FROM n WHERE left > 0
)"""

SPECS = [
    S("huts-by-altitude", 1, "List the huts from the highest to the lowest: name, altitude in metres and number of beds. Ties by name.",
      "SELECT name, altitude_m, beds FROM huts ORDER BY altitude_m DESC, name;", ["name", "altitude_m", "beds"], ordered=True),
    S("cancellation-rates", 2,
      "Per hut: total number of bookings, how many were cancelled and the cancelled share in percent with 1 decimal. Order by share descending, then hut name.",
      "SELECT h.name AS hut, COUNT(*) AS bookings, SUM(b.status = 'cancelled') AS cancelled, ROUND(100.0 * SUM(b.status = 'cancelled') / COUNT(*), 1) AS pct FROM bookings b JOIN huts h ON h.hut_id = b.hut_id GROUP BY h.hut_id ORDER BY pct DESC, h.name;",
      ["hut", "bookings", "cancelled", "pct"], ordered=True),
    S("meal-revenue", 2,
      "Meal sales by kind: meal, portions sold, revenue in euros (2 decimals) and the number of different bookings that ordered it. Meals on cancelled bookings are not sold. Order by revenue descending, then meal.",
      """SELECT m.meal, SUM(m.qty) AS portions, ROUND(SUM(m.qty * m.price_cents) / 100.0, 2) AS revenue_eur, COUNT(DISTINCT m.booking_id) AS bookings
FROM meals m JOIN bookings b ON b.booking_id = m.booking_id WHERE b.status <> 'cancelled' GROUP BY m.meal ORDER BY revenue_eur DESC, m.meal;""",
      ["meal", "portions", "revenue_eur", "bookings"], ordered=True,
      wrong=("SELECT meal, SUM(qty), ROUND(SUM(qty * price_cents) / 100.0, 2), COUNT(DISTINCT booking_id) FROM meals GROUP BY meal ORDER BY 3 DESC, meal;",)),
    S("repeat-no-shows", 2,
      "Guests with at least two no-shows: guest name and how many no-shows, most first, ties by name.",
      "SELECT guest, COUNT(*) AS no_shows FROM bookings WHERE status = 'no-show' GROUP BY guest HAVING COUNT(*) >= 2 ORDER BY no_shows DESC, guest;",
      ["guest", "no_shows"], ordered=True),
    S("party-size-brackets", 2,
      "Count the non-cancelled bookings of each hut by party size bracket: `small` (1 or 2 people), `medium` (3 to 5), `large` (6 or more). Show every hut and bracket that occurs: hut, bracket, bookings, people. Order by hut name, then small, medium, large.",
      """SELECT h.name AS hut, CASE WHEN b.party <= 2 THEN 'small' WHEN b.party <= 5 THEN 'medium' ELSE 'large' END AS bracket, COUNT(*) AS bookings, SUM(b.party) AS people
FROM bookings b JOIN huts h ON h.hut_id = b.hut_id WHERE b.status <> 'cancelled' GROUP BY h.hut_id, bracket
ORDER BY h.name, CASE bracket WHEN 'small' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END;""",
      ["hut", "bracket", "bookings", "people"], ordered=True),
    S("overbooked-nights", 4,
      "Find overbooked nights: for every hut and night, add up the people of all bookings that use beds that night (confirmed and no-show bookings; the check-out morning is not a night). "
      "List the hut-nights where that sum exceeds the number of beds: hut name, night, people, beds. Order by night, then hut name.",
      f"""{NIGHTS}
SELECT h.name AS hut, n.night, SUM(n.party) AS people, h.beds FROM n JOIN huts h ON h.hut_id = n.hut_id GROUP BY n.hut_id, n.night HAVING SUM(n.party) > h.beds ORDER BY n.night, h.name;""",
      ["hut", "night", "people", "beds"], ordered=True, allow_empty=True,
      wrong=("""SELECT h.name, b.check_in, SUM(b.party), h.beds FROM bookings b JOIN huts h ON h.hut_id = b.hut_id WHERE b.status <> 'cancelled' GROUP BY b.hut_id, b.check_in HAVING SUM(b.party) > h.beds ORDER BY b.check_in, h.name;""",)),
    S("peak-night", 3,
      "For each hut, its busiest night: the night with the most people (same rules as for beds used: cancelled bookings never count). Ties go to the earlier night. Columns: hut name, night, people. Order by hut name.",
      f"""{NIGHTS}, t AS (SELECT hut_id, night, SUM(party) AS people FROM n GROUP BY hut_id, night), r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY hut_id ORDER BY people DESC, night) AS rn FROM t)
SELECT h.name AS hut, r.night, r.people FROM r JOIN huts h ON h.hut_id = r.hut_id WHERE r.rn = 1 ORDER BY h.name;""",
      ["hut", "night", "people"], ordered=True,
      wrong=("""SELECT h.name, b.check_in, MAX(b.party) FROM bookings b JOIN huts h ON h.hut_id = b.hut_id WHERE b.status <> 'cancelled' GROUP BY h.hut_id ORDER BY h.name;""",)),
    S("booking-price", 4,
      "Price every non-cancelled booking: each night costs `party x per-night rate` where the rate is the one whose MM-DD window contains that night's month-day. Report booking id, guest, hut name and the lodging total in cents, "
      "for the bookings whose lodging total is at least 40000 cents. Order by total descending, then booking id.",
      f"""{NIGHTS}
SELECT b.booking_id, b.guest, h.name AS hut, SUM(n.party * r.per_night_cents) AS lodging_cents
FROM n JOIN bookings b ON b.booking_id = n.booking_id JOIN huts h ON h.hut_id = n.hut_id
JOIN rates r ON r.hut_id = n.hut_id AND substr(n.night, 6) BETWEEN r.start_md AND r.end_md
GROUP BY b.booking_id HAVING SUM(n.party * r.per_night_cents) >= 40000 ORDER BY lodging_cents DESC, b.booking_id;""",
      ["booking_id", "guest", "hut", "lodging_cents"], ordered=True,
      wrong=("""SELECT b.booking_id, b.guest, h.name, b.nights * b.party * r.per_night_cents AS t FROM bookings b JOIN huts h ON h.hut_id = b.hut_id JOIN rates r ON r.hut_id = b.hut_id AND substr(b.check_in, 6) BETWEEN r.start_md AND r.end_md WHERE b.status <> 'cancelled' AND t >= 40000 ORDER BY t DESC, b.booking_id;""",)),
    S("hut-to-hut-trips", 4,
      "Hut-to-hut trips: for each guest, sort their non-cancelled bookings by check-in date; a booking continues the previous trip when it checks in on the day the previous one ends (check-in plus nights), otherwise it starts a new trip. "
      "List the trips with at least 2 bookings: guest, first check-in, last night of the trip, number of bookings, total nights. Order by guest, then first check-in.",
      """WITH b AS (
  SELECT guest, check_in, nights, date(check_in, '+' || nights || ' day') AS check_out, LAG(date(check_in, '+' || nights || ' day')) OVER (PARTITION BY guest ORDER BY check_in, booking_id) AS prev_out
  FROM bookings WHERE status <> 'cancelled'
), f AS (SELECT *, SUM(CASE WHEN prev_out IS NULL OR prev_out <> check_in THEN 1 ELSE 0 END) OVER (PARTITION BY guest ORDER BY check_in, check_out) AS trip FROM b)
SELECT guest, MIN(check_in) AS first_in, date(MAX(check_out), '-1 day') AS last_night, COUNT(*) AS bookings, SUM(nights) AS nights FROM f GROUP BY guest, trip HAVING COUNT(*) >= 2 ORDER BY guest, first_in;""",
      ["guest", "first_in", "last_night", "bookings", "nights"], ordered=True,
      wrong=("""SELECT guest, MIN(check_in), MAX(check_in), COUNT(*), SUM(nights) FROM bookings WHERE status <> 'cancelled' GROUP BY guest HAVING COUNT(*) >= 2 ORDER BY guest, 2;""",)),
    S("longest-quiet-spell", 5,
      "How long does each hut stand idle between bookings? Take the non-cancelled bookings of a hut in order of check-in (ties by booking id). For each booking compute the idle days before it: its check-in minus the latest check-out of all earlier bookings of that hut "
      "(0 when it starts before or on that day; the first booking of a hut has no previous booking and is ignored). Report per hut the largest idle spell and the check-in date of the booking that ended it. "
      "Huts with no idle days at all are left out. Columns: hut name, idle days, check-in date (the earliest if tied). Order by idle days descending, then hut name.",
      """WITH b AS (
  SELECT hut_id, booking_id, check_in, date(check_in, '+' || nights || ' day') AS out_d,
         MAX(date(check_in, '+' || nights || ' day')) OVER (PARTITION BY hut_id ORDER BY check_in, booking_id ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_out
  FROM bookings WHERE status <> 'cancelled'
), g AS (SELECT hut_id, check_in, CAST(julianday(check_in) - julianday(prev_out) AS INTEGER) AS idle FROM b WHERE prev_out IS NOT NULL AND check_in > prev_out),
r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY hut_id ORDER BY idle DESC, check_in) AS rn FROM g)
SELECT h.name AS hut, r.idle, r.check_in FROM r JOIN huts h ON h.hut_id = r.hut_id WHERE r.rn = 1 ORDER BY r.idle DESC, h.name;""",
      ["hut", "idle_days", "check_in"], ordered=True,
      wrong=("""WITH b AS (SELECT hut_id, check_in, date(check_in, '+' || nights || ' day') AS out_d, LAG(date(check_in, '+' || nights || ' day')) OVER (PARTITION BY hut_id ORDER BY check_in, booking_id) AS prev_out FROM bookings WHERE status <> 'cancelled'),
g AS (SELECT hut_id, check_in, CAST(julianday(check_in) - julianday(prev_out) AS INTEGER) AS idle FROM b WHERE prev_out IS NOT NULL AND check_in > prev_out), r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY hut_id ORDER BY idle DESC, check_in) AS rn FROM g)
SELECT h.name, r.idle, r.check_in FROM r JOIN huts h ON h.hut_id = r.hut_id WHERE r.rn = 1 ORDER BY r.idle DESC, h.name;""",)),
    S("weekend-nights", 3,
      "Which share of the nights spent in each hut fell on a Friday or Saturday night? Count person-nights (a booking's party counts once per night; cancelled bookings never count) and give per hut: total person-nights, "
      "person-nights on Friday and Saturday nights, and the share in percent with 1 decimal. Order by share descending, then hut name.",
      f"""{NIGHTS}
SELECT h.name AS hut, SUM(n.party) AS person_nights, SUM(CASE WHEN strftime('%w', n.night) IN ('5', '6') THEN n.party ELSE 0 END) AS weekend,
       ROUND(100.0 * SUM(CASE WHEN strftime('%w', n.night) IN ('5', '6') THEN n.party ELSE 0 END) / SUM(n.party), 1) AS pct
FROM n JOIN huts h ON h.hut_id = n.hut_id GROUP BY n.hut_id ORDER BY pct DESC, h.name;""",
      ["hut", "person_nights", "weekend", "pct"], ordered=True,
      wrong=("""SELECT h.name, SUM(b.party * b.nights), SUM(CASE WHEN strftime('%w', b.check_in) IN ('5','6') THEN b.party * b.nights ELSE 0 END), ROUND(100.0 * SUM(CASE WHEN strftime('%w', b.check_in) IN ('5','6') THEN b.party * b.nights ELSE 0 END) / SUM(b.party * b.nights), 1) AS p
FROM bookings b JOIN huts h ON h.hut_id = b.hut_id WHERE b.status <> 'cancelled' GROUP BY h.hut_id ORDER BY p DESC, h.name;""",)),
    S("meals-per-person-night", 3,
      "Catering per hut: the number of meal portions ordered on non-cancelled bookings divided by the person-nights of those bookings (party times nights, summed). Show hut name, portions, person-nights and the ratio with 2 decimals. "
      "Huts without any non-cancelled booking do not appear. Order by ratio descending, then hut name.",
      """WITH p AS (SELECT hut_id, SUM(party * nights) AS pn FROM bookings WHERE status <> 'cancelled' GROUP BY hut_id),
m AS (SELECT b.hut_id, SUM(m.qty) AS portions FROM meals m JOIN bookings b ON b.booking_id = m.booking_id WHERE b.status <> 'cancelled' GROUP BY b.hut_id)
SELECT h.name AS hut, COALESCE(m.portions, 0) AS portions, p.pn AS person_nights, ROUND(1.0 * COALESCE(m.portions, 0) / p.pn, 2) AS ratio
FROM p JOIN huts h ON h.hut_id = p.hut_id LEFT JOIN m ON m.hut_id = p.hut_id ORDER BY ratio DESC, h.name;""",
      ["hut", "portions", "person_nights", "ratio"], ordered=True, places=2,
      wrong=("""SELECT h.name, SUM(m.qty), SUM(b.party * b.nights), ROUND(1.0 * SUM(m.qty) / SUM(b.party * b.nights), 2) AS r FROM bookings b JOIN huts h ON h.hut_id = b.hut_id JOIN meals m ON m.booking_id = b.booking_id WHERE b.status <> 'cancelled' GROUP BY h.hut_id ORDER BY r DESC, h.name;""",)),
    S("fix-bed-nights", 3,
      "The 'bed nights per hut' report in `query.sql` counts the check-out day as a night and includes cancelled bookings. Fix it: for every hut (also huts without bookings) the total person-nights "
      "(party times nights) of its confirmed and no-show bookings, 0 if none. Columns: hut name, person-nights. Order by person-nights descending, then name.",
      ref="""SELECT h.name AS hut, COALESCE(SUM(b.party * b.nights), 0) AS person_nights FROM huts h LEFT JOIN bookings b ON b.hut_id = h.hut_id AND b.status <> 'cancelled' GROUP BY h.hut_id ORDER BY person_nights DESC, h.name;""",
      cols=["hut", "person_nights"], ordered=True, show=False,
      buggy="""SELECT h.name AS hut, SUM(b.party * (b.nights + 1)) AS person_nights FROM huts h JOIN bookings b ON b.hut_id = h.hut_id GROUP BY h.hut_id ORDER BY person_nights DESC, h.name;"""),
]


@family("data-mountain-huts", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL on mountain-hut bookings: night expansion with recursive CTEs, overbooking, seasonal pricing, hut-to-hut trip chains, idle spells")
def mountain_huts(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
