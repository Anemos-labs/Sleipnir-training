"""SQL tasks on an invented observatory's observing log (pivots, islands, range windows, interval union, relational division)."""
from datetime import date, datetime, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE telescopes (
      tel_id        INTEGER PRIMARY KEY,
      name          TEXT NOT NULL UNIQUE,
      aperture_mm   INTEGER NOT NULL
    );
    CREATE TABLE targets (
      target_id    INTEGER PRIMARY KEY,
      designation  TEXT NOT NULL UNIQUE,
      kind         TEXT NOT NULL CHECK (kind IN ('galaxy', 'nebula', 'cluster', 'planet', 'variable'))
    );
    CREATE TABLE nights (
      night      TEXT PRIMARY KEY,           -- date the evening starts, YYYY-MM-DD; nights the dome was shut for repairs have no row
      weather    TEXT NOT NULL CHECK (weather IN ('clear', 'partial', 'cloudy', 'closed')),
      moon_pct   INTEGER NOT NULL            -- illuminated fraction of the moon, 0..100
    );
    CREATE TABLE sessions (
      session_id  INTEGER PRIMARY KEY,
      night       TEXT NOT NULL REFERENCES nights(night),
      tel_id      INTEGER NOT NULL REFERENCES telescopes(tel_id),
      observer    TEXT NOT NULL,
      started_at  TEXT NOT NULL,             -- 'YYYY-MM-DD HH:MM'
      ended_at    TEXT NOT NULL              -- may be on the next calendar day
    );
    CREATE TABLE exposures (
      exp_id      INTEGER PRIMARY KEY,
      session_id  INTEGER NOT NULL REFERENCES sessions(session_id),
      target_id   INTEGER NOT NULL REFERENCES targets(target_id),
      filter      TEXT NOT NULL CHECK (filter IN ('L', 'R', 'G', 'B', 'Ha')),
      seconds     INTEGER NOT NULL,
      started_at  TEXT NOT NULL,             -- 'YYYY-MM-DD HH:MM'
      quality     INTEGER                    -- 1 (poor) .. 5 (excellent); NULL when nobody rated the frame
    );
''')

DOC = dd('''
    Kestrel Ridge is a small amateur observatory. Every clear-ish night someone logs an observing **session** on one of
    the telescopes, and each frame taken during it is an **exposure** of one target through one filter.

    * An exposure occupies the telescope from `started_at` for `seconds` seconds. Exposures of one session never overlap.
    * `weather` is `clear`, `partial`, `cloudy` or `closed`. Sessions only exist on `clear` and `partial` nights.
    * Times are local, `YYYY-MM-DD HH:MM`, so string comparison orders them. A session that starts in the evening usually ends after midnight.
    * Total exposure time is the sum of `seconds`; "hours" means seconds / 3600.
''')

OBS = ["Dagny Roe", "Pim Aalto", "Sefa Lindgren", "Hollis Wray", "Imke Bos"]
KINDS = ["galaxy", "nebula", "cluster", "planet", "variable"]


def gen(rng, big):
    tel = [(1, "Heron 40", 400), (2, "Merlin 25", 250)] + ([(3, "Plover 60", 600)] if big else [])
    ntar = 12 if big else 7
    tnames = K.uniq(rng, ntar, lambda: f"KR-{rng.randint(100, 999)}")
    targets = [(i + 1, tnames[i], KINDS[i % 5] if i < 5 else rng.choice(KINDS)) for i in range(ntar)]
    nn = 30 if big else 12
    start = date(2031, 3, 1) if big else date(2031, 3, 5)
    skip = {14, rng.choice([20, 24, 26])} if big else {8}
    ws, w = [], "clear"
    for k in range(nn):
        if rng.random() > 0.58:
            w = rng.choices(["clear", "partial", "cloudy", "closed"], [5, 2, 2, 1])[0]
        ws.append(w)
    for k in ([5, 6, 7, 8, 12, 13, 14, 15, 16] if big else [1, 2, 3, 4, 7, 9]):  # guaranteed runs, one of them interrupted by a missing night
        ws[k] = "clear"
    nights = [(K.iso(start + timedelta(days=k)), ws[k], rng.choice(range(0, 101, 5))) for k in range(nn) if k not in skip]
    sessions, exps = [], []
    sid = eid = 0
    for n_ in nights:
        if n_[1] not in ("clear", "partial"):
            continue
        for t in tel:
            if rng.random() > (0.55 if big else 0.7):
                continue
            sid += 1
            s0 = datetime.strptime(n_[0], "%Y-%m-%d") + timedelta(hours=rng.randint(20, 22), minutes=rng.choice([0, 15, 30, 45]))
            s1 = s0 + timedelta(minutes=rng.choice([90, 120, 180, 240, 300, 420]))
            sessions.append((sid, n_[0], t[0], rng.choice(OBS if big else OBS[:3]), K.iso(s0), K.iso(s1)))
            cur = s0 + timedelta(minutes=rng.choice([0, 3, 10]))
            for _ in range(rng.randint(3, 8) if big else rng.randint(3, 6)):
                secs = rng.choice([60, 120, 180, 300, 600, 900])
                end = cur + timedelta(seconds=secs)
                if end > s1:
                    break
                eid += 1
                exps.append((eid, sid, rng.choice(targets[:-2] if big else targets[:-1])[0], rng.choice(["L", "L", "R", "G", "B", "Ha"]), secs, K.iso(cur),
                             None if rng.random() < 0.25 else rng.randint(1, 5)))
                cur = end + timedelta(minutes=rng.choice([0, 0, 1, 2, 5, 12, 25, 40]))
                cur = cur.replace(second=0)
    # plant: a session that overlaps another one on a different telescope and one that touches it exactly
    return {"telescopes": tel, "targets": targets, "nights": nights, "sessions": sessions, "exposures": exps}


DOMAIN = K.Domain("observatory", "Kestrel Ridge Observatory: observing log", SCHEMA, DOC, gen)
S = K.Spec

SPECS = [
    S("dark-clear-nights", 1,
      "List the nights that were `clear` with the moon at most 20% illuminated, with the moon percentage, earliest first. We want to plan faint-galaxy runs around them.",
      """SELECT night, moon_pct FROM nights WHERE weather = 'clear' AND moon_pct <= 20 ORDER BY night;""",
      ["night", "moon_pct"], ordered=True),
    S("filter-hours-pivot", 2,
      "I need integration time per target and filter in hours, one row per target that has at least one exposure, with the five filters as columns L, R, G, B, Ha "
      "(0 when a filter was never used on that target) rounded to 2 decimals. Order by designation.",
      """SELECT t.designation,
       ROUND(SUM(CASE WHEN e.filter = 'L'  THEN e.seconds ELSE 0 END) / 3600.0, 2) AS l_h,
       ROUND(SUM(CASE WHEN e.filter = 'R'  THEN e.seconds ELSE 0 END) / 3600.0, 2) AS r_h,
       ROUND(SUM(CASE WHEN e.filter = 'G'  THEN e.seconds ELSE 0 END) / 3600.0, 2) AS g_h,
       ROUND(SUM(CASE WHEN e.filter = 'B'  THEN e.seconds ELSE 0 END) / 3600.0, 2) AS b_h,
       ROUND(SUM(CASE WHEN e.filter = 'Ha' THEN e.seconds ELSE 0 END) / 3600.0, 2) AS ha_h
FROM targets t JOIN exposures e ON e.target_id = t.target_id
GROUP BY t.target_id
ORDER BY t.designation;""",
      ["designation", "l_h", "r_h", "g_h", "b_h", "ha_h"], ordered=True,
      wrong=("""SELECT t.designation, SUM(e.filter='L')*1.0, SUM(e.filter='R')*1.0, SUM(e.filter='G')*1.0, SUM(e.filter='B')*1.0, SUM(e.filter='Ha')*1.0
FROM targets t JOIN exposures e ON e.target_id = t.target_id GROUP BY t.target_id ORDER BY t.designation;""",)),
    S("untouched-targets", 2,
      "Which catalogue targets have never been photographed? Give designation and kind, ordered by kind then designation.",
      """SELECT t.designation, t.kind FROM targets t
WHERE NOT EXISTS (SELECT 1 FROM exposures e WHERE e.target_id = t.target_id)
ORDER BY t.kind, t.designation;""",
      ["designation", "kind"], ordered=True,
      wrong=("""SELECT t.designation, t.kind FROM targets t LEFT JOIN exposures e ON e.target_id = t.target_id WHERE e.quality IS NULL ORDER BY t.kind, t.designation;""",)),
    S("clear-streaks", 3,
      "Find the runs of consecutive calendar nights that were all `clear` and last 3 nights or longer. A night with no row in `nights` (dome shut for repairs) breaks a run. "
      "Return the first night, the last night and the length in nights, ordered by first night.",
      """WITH c AS (
  SELECT night, julianday(night) - ROW_NUMBER() OVER (ORDER BY night) AS g
  FROM nights WHERE weather = 'clear'
)
SELECT MIN(night) AS first_night, MAX(night) AS last_night, COUNT(*) AS nights
FROM c GROUP BY g HAVING COUNT(*) >= 3 ORDER BY first_night;""",
      ["first_night", "last_night", "nights"], ordered=True,
      wrong=("""WITH c AS (SELECT night, ROW_NUMBER() OVER (ORDER BY night) - ROW_NUMBER() OVER (PARTITION BY weather ORDER BY night) AS g, weather FROM nights)
SELECT MIN(night), MAX(night), COUNT(*) FROM c WHERE weather = 'clear' GROUP BY g HAVING COUNT(*) >= 3 ORDER BY 1;""",)),
    S("best-session-per-observer", 3,
      "Each observer's most productive session: the one with the largest total exposure time. If two of an observer's sessions tie, take the earlier `started_at`, and if that ties too the lower session id. "
      "Sessions without any exposure do not count. Show observer, session id, night and the exposure minutes (seconds/60, rounded to 1 decimal), ordered by observer.",
      """SELECT observer, session_id, night, ROUND(secs / 60.0, 1) AS minutes FROM (
  SELECT s.observer, s.session_id, s.night, SUM(e.seconds) AS secs,
         ROW_NUMBER() OVER (PARTITION BY s.observer ORDER BY SUM(e.seconds) DESC, s.started_at, s.session_id) AS rn
  FROM sessions s JOIN exposures e ON e.session_id = s.session_id
  GROUP BY s.session_id
) WHERE rn = 1 ORDER BY observer;""",
      ["observer", "session_id", "night", "minutes"], ordered=True),
    S("quality-top-three", 3,
      "Rank the targets inside each kind by their mean frame quality (only frames that have a rating; unrated frames are ignored entirely, and targets without any rated frame are not ranked) "
      "and show the top 3 per kind, where targets with exactly equal (unrounded) means share a rank and a tie at rank 3 keeps everyone. Columns: kind, designation, mean quality rounded to 2 decimals, rank. "
      "Order by kind, rank, designation.",
      """WITH m AS (
  SELECT t.kind, t.designation, ROUND(AVG(e.quality), 2) AS mean_q, AVG(e.quality) AS raw
  FROM targets t JOIN exposures e ON e.target_id = t.target_id
  WHERE e.quality IS NOT NULL
  GROUP BY t.target_id
), r AS (
  SELECT kind, designation, mean_q, RANK() OVER (PARTITION BY kind ORDER BY raw DESC) AS rnk FROM m
)
SELECT kind, designation, mean_q, rnk FROM r WHERE rnk <= 3 ORDER BY kind, rnk, designation;""",
      ["kind", "designation", "mean_quality", "rank"], ordered=True,
      wrong=("""WITH m AS (SELECT t.kind, t.designation, ROUND(SUM(COALESCE(e.quality, 0)) * 1.0 / COUNT(*), 2) AS mean_q, SUM(COALESCE(e.quality, 0)) * 1.0 / COUNT(*) AS raw
FROM targets t JOIN exposures e ON e.target_id = t.target_id GROUP BY t.target_id),
r AS (SELECT kind, designation, mean_q, RANK() OVER (PARTITION BY kind ORDER BY raw DESC) AS rnk FROM m)
SELECT kind, designation, mean_q, rnk FROM r WHERE rnk <= 3 ORDER BY kind, rnk, designation;""",)),
    S("rgb-complete-targets", 4,
      "A colour image needs all of R, G and B. Which targets have been exposed in all three of those filters on at least 3 different nights (the night of the session)? "
      "Show the designation and on how many distinct nights it was photographed in any filter, ordered by that number descending, then designation.",
      """SELECT t.designation, COUNT(DISTINCT s.night) AS nights_any
FROM targets t
JOIN exposures e ON e.target_id = t.target_id
JOIN sessions s ON s.session_id = e.session_id
WHERE t.target_id IN (
  SELECT e2.target_id FROM exposures e2 JOIN sessions s2 ON s2.session_id = e2.session_id
  WHERE e2.filter IN ('R', 'G', 'B')
  GROUP BY e2.target_id
  HAVING COUNT(DISTINCT e2.filter) = 3 AND COUNT(DISTINCT s2.night) >= 3
)
GROUP BY t.target_id
ORDER BY nights_any DESC, t.designation;""",
      ["designation", "nights_any"], ordered=True,
      wrong=("""SELECT t.designation, COUNT(DISTINCT s.night) FROM targets t JOIN exposures e ON e.target_id = t.target_id JOIN sessions s ON s.session_id = e.session_id
WHERE e.filter IN ('R', 'G', 'B') GROUP BY t.target_id HAVING COUNT(DISTINCT e.filter) = 3 ORDER BY 2 DESC, t.designation;""",)),
    S("session-dead-time", 4,
      "Dead time is telescope time inside a session in which no frame was being exposed. For each session with at least two exposures, add up the gaps between the end of each exposure "
      "(start + seconds) and the start of the next one in the same session, in minutes; return the sessions whose dead time exceeds 30 minutes: session id, observer, number of exposures, dead minutes (integer). "
      "Order by dead minutes descending, then session id.",
      """WITH x AS (
  SELECT session_id, started_at,
         CAST(strftime('%s', started_at) AS INTEGER) AS t0,
         CAST(strftime('%s', started_at) AS INTEGER) + seconds AS t1
  FROM exposures
), g AS (
  SELECT session_id, t0 - LAG(t1) OVER (PARTITION BY session_id ORDER BY t0, started_at) AS gap FROM x
)
SELECT s.session_id, s.observer, (SELECT COUNT(*) FROM exposures e WHERE e.session_id = s.session_id) AS frames,
       CAST(SUM(g.gap) / 60 AS INTEGER) AS dead_min
FROM g JOIN sessions s ON s.session_id = g.session_id
WHERE g.gap IS NOT NULL
GROUP BY s.session_id
HAVING SUM(g.gap) > 30 * 60
ORDER BY dead_min DESC, s.session_id;""",
      ["session_id", "observer", "frames", "dead_min"], ordered=True,
      wrong=("""SELECT s.session_id, s.observer, COUNT(e.exp_id), CAST((CAST(strftime('%s', s.ended_at) AS INTEGER) - CAST(strftime('%s', s.started_at) AS INTEGER) - SUM(e.seconds)) / 60 AS INTEGER) AS d
FROM sessions s JOIN exposures e ON e.session_id = s.session_id GROUP BY s.session_id HAVING COUNT(e.exp_id) >= 2 AND d > 30 ORDER BY d DESC, s.session_id;""",)),
    S("rolling-week-hours", 4,
      "How hard is each telescope working? For every telescope and every night on which it had a session, give that night's exposure hours (sum of seconds / 3600, rounded to 2 decimals) "
      "and the total over the 7-calendar-day window ending that night (that night and the 6 days before it; nights without sessions simply contribute nothing), also rounded to 2 decimals. "
      "Rows: telescope name, night, hours, week_hours; order by telescope name, night.",
      """WITH d AS (
  SELECT tel_id, night, SUM(secs) AS secs FROM (
    SELECT s.tel_id, s.night, e.seconds AS secs FROM sessions s JOIN exposures e ON e.session_id = s.session_id
  ) GROUP BY tel_id, night
)
SELECT t.name AS telescope, d.night, ROUND(d.secs / 3600.0, 2) AS hours,
       ROUND(SUM(d.secs) OVER (PARTITION BY d.tel_id ORDER BY julianday(d.night) RANGE BETWEEN 6 PRECEDING AND CURRENT ROW) / 3600.0, 2) AS week_hours
FROM d JOIN telescopes t ON t.tel_id = d.tel_id
ORDER BY t.name, d.night;""",
      ["telescope", "night", "hours", "week_hours"], ordered=True, show=False,
      notes="A telescope can have two sessions in one night in theory; treat them together, one row per telescope and night.",
      wrong=("""WITH d AS (SELECT s.tel_id, s.night, SUM(e.seconds) AS secs FROM sessions s JOIN exposures e ON e.session_id = s.session_id GROUP BY s.tel_id, s.night)
SELECT t.name, d.night, ROUND(d.secs / 3600.0, 2), ROUND(SUM(d.secs) OVER (PARTITION BY d.tel_id ORDER BY d.night ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) / 3600.0, 2)
FROM d JOIN telescopes t ON t.tel_id = d.tel_id ORDER BY t.name, d.night;""",)),
    S("open-minutes-per-night", 5,
      "How long was the observatory actually open each night? Sessions on different telescopes may overlap in time, so don't double count: for every night that has sessions, "
      "report the total minutes covered by the union of that night's sessions (from `started_at` to `ended_at`). Columns: night, number of sessions, open minutes (integer). Order by night.",
      """WITH s AS (
  SELECT night, session_id,
         CAST(strftime('%s', started_at) AS INTEGER) AS a, CAST(strftime('%s', ended_at) AS INTEGER) AS b
  FROM sessions
), f AS (
  SELECT *, MAX(b) OVER (PARTITION BY night ORDER BY a, session_id ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_end FROM s
), m AS (
  SELECT *, SUM(CASE WHEN prev_end IS NULL OR a > prev_end THEN 1 ELSE 0 END) OVER (PARTITION BY night ORDER BY a, session_id) AS island FROM f
), isl AS (
  SELECT night, island, MAX(b) - MIN(a) AS len FROM m GROUP BY night, island
)
SELECT isl.night, (SELECT COUNT(*) FROM sessions x WHERE x.night = isl.night) AS sessions, SUM(isl.len) / 60 AS open_min
FROM isl GROUP BY isl.night ORDER BY isl.night;""",
      ["night", "sessions", "open_min"], ordered=True, show=False,
      wrong=("""SELECT night, COUNT(*), SUM(CAST(strftime('%s', ended_at) AS INTEGER) - CAST(strftime('%s', started_at) AS INTEGER)) / 60 FROM sessions GROUP BY night ORDER BY night;""",)),
    S("fix-mean-quality", 2,
      "The 'mean frame quality per target' query in `query.sql` gives numbers that are too low for targets with unrated frames (the unrated ones are being treated as zero). "
      "Unrated frames (NULL quality) must be ignored, and a target with no rated frames at all must not appear. Fix it: designation, mean quality rounded to 2 decimals, best first, ties by designation.",
      ref="""SELECT t.designation, ROUND(AVG(e.quality), 2) AS mean_quality
FROM targets t JOIN exposures e ON e.target_id = t.target_id
WHERE e.quality IS NOT NULL
GROUP BY t.target_id
ORDER BY mean_quality DESC, t.designation;""",
      cols=["designation", "mean_quality"], ordered=True, show=False,
      buggy="""SELECT t.designation, ROUND(SUM(COALESCE(e.quality, 0)) * 1.0 / COUNT(*), 2) AS mean_quality
FROM targets t JOIN exposures e ON e.target_id = t.target_id
GROUP BY t.target_id
ORDER BY mean_quality DESC, t.designation;"""),
]


@family("data-observatory-log", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL reports on an observatory's observing log: pivots, runs of nights, range windows, interval union")
def observatory(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
