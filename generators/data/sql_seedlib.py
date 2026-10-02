"""SQL tasks on an invented community seed library (anti-joins, weighted rates, gaps-and-islands, calendars)."""
from datetime import date, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE species (
      species_id       INTEGER PRIMARY KEY,
      common_name      TEXT NOT NULL UNIQUE,
      family           TEXT NOT NULL,
      sow_start_month  INTEGER NOT NULL,     -- 1..12
      sow_end_month    INTEGER NOT NULL      -- 1..12; smaller than the start when the window wraps over New Year
    );
    CREATE TABLE varieties (
      variety_id        INTEGER PRIMARY KEY,
      species_id        INTEGER NOT NULL REFERENCES species(species_id),
      name              TEXT NOT NULL UNIQUE,   -- variety names are unique across the whole library
      days_to_maturity  INTEGER NOT NULL,
      heirloom          INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE members (
      member_id  INTEGER PRIMARY KEY,
      name       TEXT NOT NULL,
      joined_on  TEXT NOT NULL
    );
    CREATE TABLE packets (
      packet_id     INTEGER PRIMARY KEY,
      variety_id    INTEGER NOT NULL REFERENCES varieties(variety_id),
      donor_id      INTEGER REFERENCES members(member_id),   -- NULL: bought by the library
      harvest_year  INTEGER NOT NULL,
      seeds_est     INTEGER NOT NULL,
      stored_on     TEXT NOT NULL
    );
    CREATE TABLE loans (
      loan_id         INTEGER PRIMARY KEY,
      packet_id       INTEGER NOT NULL REFERENCES packets(packet_id),
      member_id       INTEGER NOT NULL REFERENCES members(member_id),
      loaned_on       TEXT NOT NULL,
      seeds_taken     INTEGER NOT NULL,
      returned_on     TEXT,                  -- NULL until the member brings seed back from their harvest
      returned_seeds  INTEGER                -- NULL exactly when returned_on is NULL
    );
    CREATE TABLE germination_tests (
      test_id    INTEGER PRIMARY KEY,
      packet_id  INTEGER NOT NULL REFERENCES packets(packet_id),
      tested_on  TEXT NOT NULL,
      sown       INTEGER NOT NULL CHECK (sown > 0),
      sprouted   INTEGER NOT NULL
    );
''')

DOC = dd('''
    The Thistledown Seed Library lends packets of seed to members. A member plants them, lets a few plants go to seed and
    is expected to bring some seed back.

    * `species` -> `varieties` -> `packets`: a packet is one stored lot of one variety, from a given `harvest_year`.
      `seeds_est` is the estimated seed count when it was stored. `donor_id` is NULL when the library bought the lot.
    * A **loan** takes `seeds_taken` seeds out of a packet. When the member brings seed back, `returned_on` and
      `returned_seeds` are filled in (both NULL until then).
    * A **germination test** sows `sown` seeds of a packet and counts how many `sprouted`.
    * A species can be sown from `sow_start_month` to `sow_end_month` inclusive; if the end month is smaller than the
      start month the window runs over New Year (11 to 2 means November, December, January, February).
    * Dates are ISO text (`YYYY-MM-DD`). The library's books are closed on **2031-12-31**: "today" in any report is that date.
''')

SPECIES = [("Tomato", "Solanaceae"), ("Pepper", "Solanaceae"), ("Aubergine", "Solanaceae"), ("Kale", "Brassicaceae"), ("Radish", "Brassicaceae"),
           ("Turnip", "Brassicaceae"), ("Runner bean", "Fabaceae"), ("Broad bean", "Fabaceae"), ("Pea", "Fabaceae"), ("Squash", "Cucurbitaceae"),
           ("Cucumber", "Cucurbitaceae"), ("Carrot", "Apiaceae"), ("Parsnip", "Apiaceae"), ("Lettuce", "Asteraceae"), ("Beetroot", "Amaranthaceae"),
           ("Chard", "Amaranthaceae")]
ADJ = ["Old", "Golden", "Dunmore", "Tidewater", "Granny's", "Early", "Late", "Crimson", "Painted", "Hettie's", "Marrow", "Salt-marsh", "Frost", "Little", "Giant", "Blue"]
NOUN = ["Apron", "Lantern", "Pinch", "Reliable", "Gem", "Beauty", "Wonder", "Hamlet", "Cottager", "Pilgrim", "Ember", "Button", "Farthing", "Ridge"]
FIRST = ["Aldith", "Bram", "Cosima", "Dov", "Edda", "Florin", "Gwen", "Hamid", "Isolde", "Jarek", "Kit", "Lowri", "Mattias", "Noor", "Orla", "Pavel"]
LAST = ["Appleby", "Brandt", "Castellan", "Dyer", "Eskew", "Fenwick", "Gallo", "Hobbs", "Iyer", "Jessop"]


def gen(rng, big):
    nsp = 11 if big else 6
    sp_rows = []
    for i, k in enumerate(rng.sample(range(len(SPECIES)), nsp)):
        a = rng.randint(1, 12)
        b = rng.randint(1, 12)
        if i == 0:
            a, b = 11, 2  # always one wrapping window
        if i == 1:
            a = b = rng.randint(3, 9)  # and a one-month window
        sp_rows.append((i + 1, SPECIES[k][0], SPECIES[k][1], a, b))
    nv = 26 if big else 11
    seen, var_rows = set(), []
    vid = 0
    while len(var_rows) < nv:
        sp = rng.choice(sp_rows)[0]
        nm = f"{rng.choice(ADJ)} {rng.choice(NOUN)}"
        if nm in seen:
            continue
        seen.add(nm)
        vid += 1
        var_rows.append((vid, sp, nm, rng.choice([45, 55, 60, 70, 75, 80, 85, 90, 100, 110, 120]), rng.randint(0, 1)))
    nm_ = 16 if big else 6
    members = []
    names = K.uniq(rng, nm_, lambda: K.person(rng, FIRST, LAST))
    for i, nm in enumerate(names):
        members.append((i + 1, nm, K.iso(K.rdate(rng, date(2028, 1, 1), 1400))))
    # packets: most varieties have 1-3 packets; a few have none; a couple of duplicate entries
    packets = []
    pid = 0
    for v in var_rows[1:]:  # variety 1 never has a packet
        for _ in range(rng.choice([0, 1, 1, 2, 2, 3]) if big else rng.choice([1, 1, 2])):
            pid += 1
            yr = rng.randint(2026, 2031)
            packets.append([pid, v[0], rng.choice([None] + [m[0] for m in members]), yr, rng.choice([40, 60, 80, 100, 150, 200, 300, 450]),
                            f"{yr}-{rng.randint(9, 12):02d}-{rng.randint(1, 28):02d}"])
    # duplicate entries: same variety, harvest year and donor stored twice
    dups = rng.sample(packets, 2 if not big else 4)
    dups[0][2] = None  # at least one duplicated lot has no donor (NULL = NULL must still match)
    for p in dups:
        pid += 1
        packets.append([pid, p[1], p[2], p[3], rng.choice([40, 60, 80, 100]), p[5]])
    # consecutive harvest years for one variety (a streak) plus a broken one
    for base, yrs in ((var_rows[2][0], [2027, 2028, 2029, 2030]), (var_rows[3][0], [2026, 2027, 2029, 2030, 2031])):
        for yr in yrs:
            pid += 1
            packets.append([pid, base, rng.choice([None, 1]), yr, rng.choice([80, 120]), f"{yr}-10-{rng.randint(1, 28):02d}"])
    packets = [tuple(p) for p in packets]
    # loans
    loans = []
    lid = 0
    for _ in range(95 if big else 17):
        p = rng.choice(packets)
        lid += 1
        lo = K.rdate(rng, date(2031, 1, 5), 330)
        taken = rng.choice([10, 15, 20, 25, 30, 40])
        if rng.random() < 0.55:
            ret = lo + timedelta(days=rng.randint(60, 240))
            if ret > date(2031, 12, 31):
                loans.append((lid, p[0], rng.choice(members)[0], K.iso(lo), taken, None, None))
            else:
                loans.append((lid, p[0], rng.choice(members)[0], K.iso(lo), taken, K.iso(ret), rng.choice([0, 5, 20, 40, 60, 90])))
        else:
            loans.append((lid, p[0], rng.choice(members)[0], K.iso(lo), taken, None, None))
    # boundary loans: exactly 120 and 121 days before the books closed, both still out
    for day in ("2031-09-02", "2031-09-01"):
        lid += 1
        loans.append((lid, rng.choice(packets)[0], rng.choice(members)[0], day, rng.choice([10, 20]), None, None))
    # tests
    tests = []
    tid = 0
    for _ in range(85 if big else 16):
        p = rng.choice(packets)
        tid += 1
        sown = rng.choice([10, 20, 25, 40, 50])
        tests.append((tid, p[0], K.iso(K.rdate(rng, date(2031, 2, 1), 320)), sown, int(sown * rng.choice([0.2, 0.5, 0.65, 0.7, 0.7, 0.8, 0.9, 1.0]))))
    # same-day double test on one packet (tie on "latest")
    t0 = rng.choice(tests)
    tid += 1
    tests.append((tid, t0[1], t0[2], 20, rng.choice([5, 18])))
    return {"species": sp_rows, "varieties": var_rows, "members": members, "packets": packets, "loans": loans, "germination_tests": tests}


DOMAIN = K.Domain("seedlib", "Thistledown Seed Library", SCHEMA, DOC, gen)
S = K.Spec

SPECS = [
    S("quick-nightshades", 1,
      "Which heirloom varieties of any species in the family Solanaceae mature in under 80 days? I want the species' common name and the variety name, species first, then variety.",
      """SELECT s.common_name AS species, v.name AS variety
FROM varieties v JOIN species s ON s.species_id = v.species_id
WHERE s.family = 'Solanaceae' AND v.heirloom = 1 AND v.days_to_maturity < 80
ORDER BY s.common_name, v.name;""",
      ["species", "variety"], ordered=True, wrong=("""SELECT s.common_name, v.name FROM varieties v JOIN species s ON s.species_id = v.species_id
WHERE s.family = 'Solanaceae' AND v.heirloom = 1 AND v.days_to_maturity <= 80 ORDER BY s.common_name, v.name;""",)),
    S("never-lent-stock", 2,
      "The committee wants to push stock that nobody has ever borrowed. List every packet that has never appeared in a loan and holds an estimated 100 seeds or more: "
      "packet id, variety name and harvest year, oldest harvest first, then packet id.",
      """SELECT p.packet_id, v.name AS variety, p.harvest_year
FROM packets p JOIN varieties v ON v.variety_id = p.variety_id
WHERE p.seeds_est >= 100 AND NOT EXISTS (SELECT 1 FROM loans l WHERE l.packet_id = p.packet_id)
ORDER BY p.harvest_year, p.packet_id;""",
      ["packet_id", "variety", "harvest_year"], ordered=True,
      wrong=("""SELECT p.packet_id, v.name, p.harvest_year FROM packets p JOIN varieties v ON v.variety_id = p.variety_id
JOIN loans l ON l.packet_id = p.packet_id WHERE p.seeds_est >= 100 ORDER BY p.harvest_year, p.packet_id;""",)),
    S("overdue-borrowers", 2,
      "Who still owes us seed? Members with at least one loan that has not been returned and was taken more than 120 days before the books closed on 2031-12-31. "
      "Show the member name, how many such loans, and the date of the oldest one. Oldest first, ties by name.",
      """SELECT m.name AS member, COUNT(*) AS open_loans, MIN(l.loaned_on) AS oldest
FROM loans l JOIN members m ON m.member_id = l.member_id
WHERE l.returned_on IS NULL AND julianday('2031-12-31') - julianday(l.loaned_on) > 120
GROUP BY m.member_id
ORDER BY oldest, m.name;""",
      ["member", "open_loans", "oldest"], ordered=True,
      wrong=("""SELECT m.name, COUNT(*), MIN(l.loaned_on) AS oldest FROM loans l JOIN members m ON m.member_id = l.member_id
WHERE l.returned_on IS NULL AND julianday('2031-12-31') - julianday(l.loaned_on) >= 120 GROUP BY m.member_id ORDER BY oldest, m.name;""",)),
    S("germination-rate", 2,
      "Report the overall germination rate of every variety that has been tested at least twice, counting all its packets together: total sprouted divided by total sown, as a percentage rounded to one decimal "
      "(so a 50-seed test counts for more than a 10-seed test). Best rate first, ties by variety name.",
      """SELECT v.name AS variety, COUNT(*) AS tests, ROUND(100.0 * SUM(t.sprouted) / SUM(t.sown), 1) AS rate_pct
FROM germination_tests t
JOIN packets p ON p.packet_id = t.packet_id
JOIN varieties v ON v.variety_id = p.variety_id
GROUP BY v.variety_id
HAVING COUNT(*) >= 2
ORDER BY rate_pct DESC, v.name;""",
      ["variety", "tests", "rate_pct"], ordered=True,
      wrong=("""SELECT v.name, COUNT(*), ROUND(100.0 * AVG(1.0 * t.sprouted / t.sown), 1) AS r FROM germination_tests t
JOIN packets p ON p.packet_id = t.packet_id JOIN varieties v ON v.variety_id = p.variety_id GROUP BY v.variety_id HAVING COUNT(*) >= 2 ORDER BY r DESC, v.name;""",)),
    S("sow-window-length", 2,
      "How many calendar months long is each species' sowing window? The window runs from `sow_start_month` to `sow_end_month` inclusive and may wrap over New Year. "
      "List the common name and the number of months, longest window first, then name.",
      """SELECT common_name AS species,
       (sow_end_month - sow_start_month + 12) % 12 + 1 AS months
FROM species
ORDER BY months DESC, common_name;""",
      ["species", "months"], ordered=True,
      wrong=("""SELECT common_name, ABS(sow_end_month - sow_start_month) + 1 AS m FROM species ORDER BY m DESC, common_name;""",)),
    S("retire-list", 3,
      "Packets whose most recent germination test came in under 70% (sprouted/sown) should be retired. For every packet that has been tested, take its latest test "
      "(if two tests share the date, the higher test id is the latest) and list the packets where that test is below 70%. Show packet id, variety name, the test date and the rate as a percentage "
      "with one decimal. Order by packet id.",
      """SELECT p.packet_id, v.name AS variety, t.tested_on, ROUND(100.0 * t.sprouted / t.sown, 1) AS rate_pct
FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY packet_id ORDER BY tested_on DESC, test_id DESC) AS rn
  FROM germination_tests
) t
JOIN packets p ON p.packet_id = t.packet_id
JOIN varieties v ON v.variety_id = p.variety_id
WHERE t.rn = 1 AND 100.0 * t.sprouted / t.sown < 70
ORDER BY p.packet_id;""",
      ["packet_id", "variety", "tested_on", "rate_pct"], ordered=True,
      wrong=("""SELECT p.packet_id, v.name, t.tested_on, ROUND(100.0 * t.sprouted / t.sown, 1) FROM germination_tests t
JOIN packets p ON p.packet_id = t.packet_id JOIN varieties v ON v.variety_id = p.variety_id
WHERE 100.0 * t.sprouted / t.sown < 70 AND t.tested_on = (SELECT MAX(x.tested_on) FROM germination_tests x WHERE x.packet_id = t.packet_id) ORDER BY p.packet_id;""",)),
    S("biggest-variety-per-species", 3,
      "For each species, which variety do we hold the most seed of? Add up `seeds_est` over all packets of each variety; the winner per species is the variety with the largest total "
      "(on equal totals the alphabetically first variety name wins). Varieties with no packets do not compete, and species with no packets at all are omitted. "
      "Give species, variety and total, ordered by species name.",
      """SELECT species, variety, total FROM (
  SELECT s.common_name AS species, v.name AS variety, SUM(p.seeds_est) AS total,
         ROW_NUMBER() OVER (PARTITION BY s.species_id ORDER BY SUM(p.seeds_est) DESC, v.name) AS rn
  FROM species s
  JOIN varieties v ON v.species_id = s.species_id
  JOIN packets p ON p.variety_id = v.variety_id
  GROUP BY s.species_id, v.variety_id
) WHERE rn = 1
ORDER BY species;""",
      ["species", "variety", "total"], ordered=True,
      wrong=("""SELECT species, variety, seeds_est FROM (
  SELECT s.common_name AS species, v.name AS variety, p.seeds_est,
         ROW_NUMBER() OVER (PARTITION BY s.species_id ORDER BY p.seeds_est DESC, v.name) AS rn
  FROM species s JOIN varieties v ON v.species_id = s.species_id JOIN packets p ON p.variety_id = v.variety_id
) WHERE rn = 1 ORDER BY species;""",)),
    S("return-ratio", 3,
      "Which members give back what they take? For every member with at least one loan, compare the total `returned_seeds` they brought back with the total `seeds_taken` over ALL their loans "
      "(loans not yet returned count as 0 returned). Show member, seeds taken, seeds returned and the ratio returned/taken rounded to 2 decimals. Best ratio first, ties by member name.",
      """SELECT m.name AS member, SUM(l.seeds_taken) AS taken, COALESCE(SUM(l.returned_seeds), 0) AS returned,
       ROUND(1.0 * COALESCE(SUM(l.returned_seeds), 0) / SUM(l.seeds_taken), 2) AS ratio
FROM members m JOIN loans l ON l.member_id = m.member_id
GROUP BY m.member_id
ORDER BY ratio DESC, m.name;""",
      ["member", "taken", "returned", "ratio"], ordered=True,
      wrong=("""SELECT m.name, SUM(l.seeds_taken), COALESCE(SUM(l.returned_seeds), 0), ROUND(1.0 * SUM(l.returned_seeds) / SUM(l.seeds_taken), 2) AS ratio
FROM members m JOIN loans l ON l.member_id = m.member_id WHERE l.returned_on IS NOT NULL GROUP BY m.member_id ORDER BY ratio DESC, m.name;""",)),
    S("harvest-streaks", 4,
      "Seed savers love continuity. For every variety, find its runs of consecutive harvest years (a year counts once even if there are several packets from it), "
      "and list the runs that are 3 years or longer: variety name, first year, last year and length. Order by variety name, then first year.",
      """WITH yrs AS (SELECT DISTINCT variety_id, harvest_year FROM packets),
grp AS (
  SELECT variety_id, harvest_year,
         harvest_year - ROW_NUMBER() OVER (PARTITION BY variety_id ORDER BY harvest_year) AS g
  FROM yrs
)
SELECT v.name AS variety, MIN(harvest_year) AS first_year, MAX(harvest_year) AS last_year, COUNT(*) AS years
FROM grp JOIN varieties v ON v.variety_id = grp.variety_id
GROUP BY grp.variety_id, g
HAVING COUNT(*) >= 3
ORDER BY v.name, first_year;""",
      ["variety", "first_year", "last_year", "years"], ordered=True,
      wrong=("""SELECT v.name, MIN(p.harvest_year), MAX(p.harvest_year), MAX(p.harvest_year) - MIN(p.harvest_year) + 1 FROM packets p JOIN varieties v ON v.variety_id = p.variety_id
GROUP BY p.variety_id HAVING COUNT(DISTINCT p.harvest_year) >= 3 ORDER BY v.name, 2;""",)),
    S("duplicate-packets", 4,
      "Someone entered some lots twice. Two packets are duplicates when they have the same variety, the same harvest year and the same donor (two NULL donors count as the same donor). "
      "For each group keep the packet with the lowest id and report every other packet as a duplicate: `dup_id` and the `keep_id` it duplicates. Sort by dup_id.",
      """SELECT dup_id, keep_id FROM (
  SELECT p.packet_id AS dup_id,
         MIN(p.packet_id) OVER (PARTITION BY p.variety_id, p.harvest_year, COALESCE(p.donor_id, -1)) AS keep_id
  FROM packets p
)
WHERE dup_id <> keep_id
ORDER BY dup_id;""",
      ["dup_id", "keep_id"], ordered=True,
      wrong=("""SELECT b.packet_id, MIN(a.packet_id) FROM packets a JOIN packets b ON a.variety_id = b.variety_id AND a.harvest_year = b.harvest_year AND a.donor_id = b.donor_id
AND a.packet_id < b.packet_id GROUP BY b.packet_id ORDER BY b.packet_id;""",)),
    S("co-borrowers", 4,
      "Find pairs of members who borrowed packets of the same variety within 14 days of each other (the loan dates differ by at most 14 days, either way). "
      "A pair is listed once with the smaller member id first, together with the number of different varieties they overlapped on. Order by that number (largest first), then the two ids.",
      """WITH lv AS (
  SELECT l.member_id, p.variety_id, julianday(l.loaned_on) AS d
  FROM loans l JOIN packets p ON p.packet_id = l.packet_id
)
SELECT a.member_id AS member_a, b.member_id AS member_b, COUNT(DISTINCT a.variety_id) AS varieties
FROM lv a JOIN lv b ON a.variety_id = b.variety_id AND a.member_id < b.member_id AND ABS(a.d - b.d) <= 14
GROUP BY a.member_id, b.member_id
ORDER BY varieties DESC, member_a, member_b;""",
      ["member_a", "member_b", "varieties"], ordered=True,
      wrong=("""WITH lv AS (SELECT l.member_id, p.variety_id, julianday(l.loaned_on) AS d FROM loans l JOIN packets p ON p.packet_id = l.packet_id)
SELECT a.member_id, b.member_id, COUNT(DISTINCT a.variety_id) AS n FROM lv a JOIN lv b ON a.variety_id = b.variety_id AND a.member_id < b.member_id AND ABS(a.d - b.d) < 14
GROUP BY a.member_id, b.member_id ORDER BY n DESC, 1, 2;""",)),
    S("monthly-stock-position", 5,
      "Month-end stock of seeds per variety during 2031. A packet adds its `seeds_est` on `stored_on`, each loan removes `seeds_taken` on `loaned_on`, and a returned loan adds back `returned_seeds` on `returned_on`. "
      "For every variety that has at least one packet, and for every month-end 2031-01-31 .. 2031-12-31, give the stock on that day, all events dated on or before the month-end included "
      "(it can be negative: the books have errors). Columns: variety name, month-end date, stock. Order by variety name, then date.",
      """WITH RECURSIVE months(me) AS (
  SELECT '2031-01-31'
  UNION ALL
  SELECT date(me, '+1 day', 'start of month', '+1 month', '-1 day') FROM months WHERE me < '2031-12-01'
), events AS (
  SELECT p.variety_id, p.stored_on AS d, p.seeds_est AS qty FROM packets p
  UNION ALL
  SELECT p.variety_id, l.loaned_on, -l.seeds_taken FROM loans l JOIN packets p ON p.packet_id = l.packet_id
  UNION ALL
  SELECT p.variety_id, l.returned_on, l.returned_seeds FROM loans l JOIN packets p ON p.packet_id = l.packet_id WHERE l.returned_on IS NOT NULL
)
SELECT v.name AS variety, m.me AS month_end,
       COALESCE((SELECT SUM(e.qty) FROM events e WHERE e.variety_id = v.variety_id AND e.d <= m.me), 0) AS stock
FROM varieties v CROSS JOIN months m
WHERE EXISTS (SELECT 1 FROM packets p WHERE p.variety_id = v.variety_id)
ORDER BY v.name, m.me;""",
      ["variety", "month_end", "stock"], ordered=True, show=False,
      wrong=("""WITH RECURSIVE months(me) AS (SELECT '2031-01-31' UNION ALL SELECT date(me, '+1 day', 'start of month', '+1 month', '-1 day') FROM months WHERE me < '2031-12-01'),
events AS (SELECT p.variety_id, p.stored_on AS d, p.seeds_est AS qty FROM packets p UNION ALL SELECT p.variety_id, l.loaned_on, -l.seeds_taken FROM loans l JOIN packets p ON p.packet_id = l.packet_id)
SELECT v.name, m.me, COALESCE((SELECT SUM(e.qty) FROM events e WHERE e.variety_id = v.variety_id AND e.d <= m.me), 0)
FROM varieties v CROSS JOIN months m WHERE EXISTS (SELECT 1 FROM packets p WHERE p.variety_id = v.variety_id) ORDER BY v.name, m.me;""",)),
]


@family("data-seed-library", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL reports on a community seed library: anti-joins, weighted rates, islands, calendar generation")
def seedlib(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
