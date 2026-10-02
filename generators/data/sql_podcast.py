"""SQL tasks on an invented podcast network's download counts (RANGE windows over days, decay shares, percent ranks, fan-out traps, sponsor revenue)."""
from datetime import date, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE shows (
      show_id      INTEGER PRIMARY KEY,
      title        TEXT NOT NULL UNIQUE,
      genre        TEXT NOT NULL,
      launched_on  TEXT NOT NULL
    );
    CREATE TABLE episodes (
      episode_id    INTEGER PRIMARY KEY,
      show_id       INTEGER NOT NULL REFERENCES shows(show_id),
      ep_no         INTEGER NOT NULL,
      published_on  TEXT NOT NULL,
      minutes       INTEGER NOT NULL,
      UNIQUE (show_id, ep_no)
    );
    CREATE TABLE downloads (
      day         TEXT NOT NULL,                -- YYYY-MM-DD
      episode_id  INTEGER NOT NULL REFERENCES episodes(episode_id),
      count       INTEGER NOT NULL,
      PRIMARY KEY (day, episode_id)
    );
    CREATE TABLE sponsors (
      sponsor_id  INTEGER PRIMARY KEY,
      name        TEXT NOT NULL UNIQUE
    );
    CREATE TABLE spots (
      spot_id     INTEGER PRIMARY KEY,
      episode_id  INTEGER NOT NULL REFERENCES episodes(episode_id),
      sponsor_id  INTEGER NOT NULL REFERENCES sponsors(sponsor_id),
      position    TEXT NOT NULL CHECK (position IN ('pre', 'mid', 'post')),
      cpm_cents   INTEGER NOT NULL               -- price per 1000 downloads, in cents
    );
''')

DOC = dd('''
    Static Harbour Audio hosts a handful of podcasts and counts downloads per episode and day.

    * `downloads` has one row per episode and day **that had downloads**; a day without a row means zero downloads.
    * An episode's **first week** is the 7 calendar days starting on `published_on` (day 0 to day 6).
    * A **spot** is an ad slot in an episode sold to a sponsor. It earns `downloads of the whole episode / 1000 x cpm_cents` cents (a fractional number; round only when asked).
    * Several spots can sit in one episode, and an episode has many daily rows: joins through both fan out (mind that when adding things up).
    * Dates are ISO text; weekdays follow SQLite's `strftime('%w')` (0 = Sunday).
''')

SHOWS = [("Static Harbour Daily", "news"), ("The Long Furrow", "farming"), ("Brass & Bellows", "music"), ("Night Ferry Tales", "fiction"), ("Rustworks", "tech"), ("Gull Court", "comedy")]
SPONSORS = ["Tideline Coffee", "North Gate Bank", "Kettle & Co", "Anchor Insure", "Lumen Bikes", "Quay Books"]


def gen(rng, big):
    ns = 6 if big else 3
    shows = [(i + 1, SHOWS[i][0], SHOWS[i][1], f"2036-{rng.randint(1, 9):02d}-01") for i in range(ns)]
    eps, dls, eid = [], [], 0
    for s in shows:
        start = date.fromisoformat(s[3]) + timedelta(days=rng.randint(0, 20))
        n = rng.randint(7, 12) if big else rng.randint(4, 6)
        for k in range(n):
            eid += 1
            gap = 28 if s[0] == 2 else 7  # one show releases monthly: its daily totals have holes
            pub = start + timedelta(days=gap * k + rng.choice([0, 0, 1]))
            eps.append((eid, s[0], k + 1, pub.isoformat(), rng.choice([18, 25, 32, 41, 55, 67])))
            if rng.random() < 0.06 and k > 0:
                continue  # an episode nobody downloaded
            base = rng.choice([40, 120, 300, 800])
            horizon = 8 if s[0] == 2 else rng.randint(14, 32 if big else 20)
            for d in range(horizon):
                if rng.random() < 0.1:
                    continue
                c = int(base * (0.82 ** d) * rng.uniform(0.7, 1.3)) + (rng.randint(0, 3) if d > 5 else 0)
                if c > 0:
                    dls.append((pub + timedelta(days=d), eid, c))
    dls = [(d.isoformat(), e, c) for d, e, c in dls]
    sps = [(i + 1, SPONSORS[i]) for i in range(6 if big else 4)]
    spots, sid = [], 0
    for e in eps:
        for pos in rng.sample(["pre", "mid", "post"], rng.choice([0, 1, 2, 2, 3])):
            sid += 1
            spots.append((sid, e[0], rng.choice(sps)[0], pos, rng.choice([1800, 2200, 2500, 3200, 4000])))
    # plant: one sponsor dominates the first show (a strong CPM on every episode, others rare and cheap)
    spots = [sp for sp in spots if not (next(e for e in eps if e[0] == sp[1])[1] == 1 and sp[2] != 1)]
    have = {sp[1] for sp in spots if sp[2] == 1}
    for e in eps:
        if e[1] == 1 and e[0] not in have:
            sid += 1
            spots.append((sid, e[0], 1, "pre", 4000))
    return {"shows": shows, "episodes": eps, "downloads": dls, "sponsors": sps, "spots": spots}


DOMAIN = K.Domain("podcast", "Static Harbour Audio: podcast downloads", SCHEMA, DOC, gen)
S = K.Spec

TOTALS = "(SELECT episode_id, SUM(count) AS total FROM downloads GROUP BY episode_id)"

SPECS = [
    S("shows-per-genre", 1, "Number of shows per genre and the date the earliest show launched. Columns: genre, shows, first launch. Order by genre.",
      "SELECT genre, COUNT(*) AS shows, MIN(launched_on) AS first_launch FROM shows GROUP BY genre ORDER BY genre;", ["genre", "shows", "first_launch"], ordered=True),
    S("episode-length-stats", 2,
      "Per show: number of episodes, average length in minutes with 1 decimal, and the longest episode in minutes. Order by average length descending, then show title.",
      "SELECT s.title, COUNT(*) AS episodes, ROUND(AVG(e.minutes), 1) AS avg_minutes, MAX(e.minutes) AS longest FROM shows s JOIN episodes e ON e.show_id = s.show_id GROUP BY s.show_id ORDER BY avg_minutes DESC, s.title;",
      ["title", "episodes", "avg_minutes", "longest"], ordered=True),
    S("first-week-downloads", 2,
      "Downloads in each episode's first week (the 7 days starting on its publication day): show title, episode number, downloads in the first week (0 if none). Show the 8 episodes with the most first-week downloads, ties by show title then episode number.",
      """SELECT s.title, e.ep_no, COALESCE((SELECT SUM(d.count) FROM downloads d WHERE d.episode_id = e.episode_id AND d.day >= e.published_on AND d.day < date(e.published_on, '+7 day')), 0) AS first_week
FROM episodes e JOIN shows s ON s.show_id = e.show_id ORDER BY first_week DESC, s.title, e.ep_no LIMIT 8;""",
      ["title", "ep_no", "first_week"], ordered=True,
      wrong=("""SELECT s.title, e.ep_no, COALESCE(SUM(d.count), 0) AS fw FROM episodes e JOIN shows s ON s.show_id = e.show_id LEFT JOIN downloads d ON d.episode_id = e.episode_id AND d.day <= date(e.published_on, '+7 day') AND d.day >= e.published_on GROUP BY e.episode_id ORDER BY fw DESC, s.title, e.ep_no LIMIT 8;""",)),
    S("silent-episodes", 2, "Episodes without a single download row: show title and episode number, ordered by title then episode number.",
      "SELECT s.title, e.ep_no FROM episodes e JOIN shows s ON s.show_id = e.show_id WHERE NOT EXISTS (SELECT 1 FROM downloads d WHERE d.episode_id = e.episode_id) ORDER BY s.title, e.ep_no;",
      ["title", "ep_no"], ordered=True, allow_empty=True),
    S("best-episode-per-show", 3,
      "The most downloaded episode of every show (all-time total over all its days); ties go to the lower episode number. Columns: show title, episode number, total downloads. Shows without downloads are not listed. Order by show title.",
      f"""WITH t AS {TOTALS}, r AS (SELECT e.show_id, e.ep_no, t.total, ROW_NUMBER() OVER (PARTITION BY e.show_id ORDER BY t.total DESC, e.ep_no) AS rn FROM episodes e JOIN t ON t.episode_id = e.episode_id)
SELECT s.title, r.ep_no, r.total FROM r JOIN shows s ON s.show_id = r.show_id WHERE r.rn = 1 ORDER BY s.title;""",
      ["title", "ep_no", "total"], ordered=True,
      wrong=("""SELECT s.title, e.ep_no, MAX(d.count) FROM downloads d JOIN episodes e ON e.episode_id = d.episode_id JOIN shows s ON s.show_id = e.show_id GROUP BY s.show_id ORDER BY s.title;""",)),
    S("publishing-gaps", 3,
      "Gaps in the release schedule: for every show, consecutive episodes (by episode number) published more than 9 days apart. Columns: show title, the earlier episode number, the later episode number, days between. Order by days between descending, then title.",
      """WITH g AS (SELECT show_id, ep_no, published_on, LAG(ep_no) OVER w AS prev_no, LAG(published_on) OVER w AS prev_on FROM episodes WINDOW w AS (PARTITION BY show_id ORDER BY ep_no))
SELECT s.title, g.prev_no AS from_ep, g.ep_no AS to_ep, CAST(julianday(g.published_on) - julianday(g.prev_on) AS INTEGER) AS days FROM g JOIN shows s ON s.show_id = g.show_id WHERE g.prev_no IS NOT NULL AND julianday(g.published_on) - julianday(g.prev_on) > 9 ORDER BY days DESC, s.title, g.ep_no;""",
      ["title", "from_ep", "to_ep", "days"], ordered=True, allow_empty=True),
    S("weekday-profile", 3,
      "Average downloads per weekday over all recorded rows of the whole network: the weekday name (Sunday .. Saturday), the number of download rows on such days and the average count per row, 1 decimal. Order Sunday first through Saturday.",
      """SELECT CASE strftime('%w', day) WHEN '0' THEN 'Sunday' WHEN '1' THEN 'Monday' WHEN '2' THEN 'Tuesday' WHEN '3' THEN 'Wednesday' WHEN '4' THEN 'Thursday' WHEN '5' THEN 'Friday' ELSE 'Saturday' END AS weekday,
       COUNT(*) AS rows_, ROUND(AVG(count), 1) AS avg_count FROM downloads GROUP BY strftime('%w', day) ORDER BY strftime('%w', day);""",
      ["weekday", "rows", "avg_count"], ordered=True),
    S("sponsor-revenue", 3,
      "Revenue per sponsor in euros: for every spot, earnings are the episode's total downloads divided by 1000 times the CPM (in cents); add them up per sponsor and divide by 100, rounded to 2 decimals. "
      "Give sponsor name, number of spots and revenue, including sponsors with no spots (0 spots, 0 revenue). Order by revenue descending, then name.",
      f"""WITH t AS {TOTALS}
SELECT sp.name AS sponsor, COUNT(s.spot_id) AS spots, ROUND(COALESCE(SUM(COALESCE(t.total, 0) / 1000.0 * s.cpm_cents), 0) / 100.0, 2) AS revenue_eur
FROM sponsors sp LEFT JOIN spots s ON s.sponsor_id = sp.sponsor_id LEFT JOIN t ON t.episode_id = s.episode_id GROUP BY sp.sponsor_id ORDER BY revenue_eur DESC, sp.name;""",
      ["sponsor", "spots", "revenue_eur"], ordered=True, places=2,
      wrong=("""SELECT sp.name, COUNT(*), ROUND(SUM(d.count / 1000.0 * s.cpm_cents) / 100.0, 2) AS r FROM sponsors sp JOIN spots s ON s.sponsor_id = sp.sponsor_id JOIN downloads d ON d.episode_id = s.episode_id GROUP BY sp.sponsor_id ORDER BY r DESC, sp.name;""",)),
    S("first-week-share", 4,
      "How front-loaded are the shows? For every episode with at least 100 downloads in total, the share of its downloads that arrived in the first week (7 days from the publication day). "
      "Report per show the number of such episodes and the average share as a percentage with 1 decimal. Shows without such an episode are left out. Order by the average share descending, then title.",
      f"""WITH t AS {TOTALS}, fw AS (SELECT e.episode_id, e.show_id, t.total, COALESCE((SELECT SUM(d.count) FROM downloads d WHERE d.episode_id = e.episode_id AND d.day >= e.published_on AND d.day < date(e.published_on, '+7 day')), 0) AS first FROM episodes e JOIN t ON t.episode_id = e.episode_id WHERE t.total >= 100)
SELECT s.title, COUNT(*) AS episodes, ROUND(100.0 * AVG(1.0 * fw.first / fw.total), 1) AS avg_first_week_pct FROM fw JOIN shows s ON s.show_id = fw.show_id GROUP BY fw.show_id ORDER BY avg_first_week_pct DESC, s.title;""",
      ["title", "episodes", "avg_first_week_pct"], ordered=True,
      wrong=(f"""WITH t AS {TOTALS}, fw AS (SELECT e.episode_id, e.show_id, t.total, COALESCE((SELECT SUM(d.count) FROM downloads d WHERE d.episode_id = e.episode_id AND d.day >= e.published_on AND d.day < date(e.published_on, '+7 day')), 0) AS first FROM episodes e JOIN t ON t.episode_id = e.episode_id WHERE t.total >= 100)
SELECT s.title, COUNT(*), ROUND(100.0 * SUM(fw.first) / SUM(fw.total), 1) AS p FROM fw JOIN shows s ON s.show_id = fw.show_id GROUP BY fw.show_id ORDER BY p DESC, s.title;""",)),
    S("peak-rolling-week", 4,
      "For each show add up its daily downloads over all episodes, then compute for every day with downloads the rolling total of that day and the previous 6 calendar days (days without rows count as zero). "
      "Report each show's peak: show title, the day on which the rolling total is highest (earliest if tied) and that total. Order by show title.",
      """WITH day_tot AS (SELECT e.show_id, d.day, SUM(d.count) AS n FROM downloads d JOIN episodes e ON e.episode_id = d.episode_id GROUP BY e.show_id, d.day),
roll AS (SELECT show_id, day, SUM(n) OVER (PARTITION BY show_id ORDER BY julianday(day) RANGE BETWEEN 6 PRECEDING AND CURRENT ROW) AS week FROM day_tot),
best AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY show_id ORDER BY week DESC, day) AS rn FROM roll)
SELECT s.title, b.day, b.week FROM best b JOIN shows s ON s.show_id = b.show_id WHERE b.rn = 1 ORDER BY s.title;""",
      ["title", "day", "week"], ordered=True,
      wrong=("""WITH day_tot AS (SELECT e.show_id, d.day, SUM(d.count) AS n FROM downloads d JOIN episodes e ON e.episode_id = d.episode_id GROUP BY e.show_id, d.day),
roll AS (SELECT show_id, day, SUM(n) OVER (PARTITION BY show_id ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS week FROM day_tot), best AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY show_id ORDER BY week DESC, day) AS rn FROM roll)
SELECT s.title, b.day, b.week FROM best b JOIN shows s ON s.show_id = b.show_id WHERE b.rn = 1 ORDER BY s.title;""",)),
    S("top-decile-episodes", 4,
      "Within each show, rank episodes by all-time downloads with PERCENT_RANK (0 for the least downloaded, 1 for the most; episodes without downloads count as 0 downloads and take part). "
      "List the episodes whose percent rank is at least 0.8: show title, episode number, total downloads, percent rank with 2 decimals. Order by show title, then rank descending, then episode number.",
      f"""WITH t AS {TOTALS}, r AS (SELECT e.show_id, e.ep_no, COALESCE(t.total, 0) AS total, PERCENT_RANK() OVER (PARTITION BY e.show_id ORDER BY COALESCE(t.total, 0)) AS pr FROM episodes e LEFT JOIN t ON t.episode_id = e.episode_id)
SELECT s.title, r.ep_no, r.total, ROUND(r.pr, 2) AS pr FROM r JOIN shows s ON s.show_id = r.show_id WHERE r.pr >= 0.8 ORDER BY s.title, r.pr DESC, r.ep_no;""",
      ["title", "ep_no", "total", "percent_rank"], ordered=True, places=2,
      wrong=(f"""WITH t AS {TOTALS}, r AS (SELECT e.show_id, e.ep_no, t.total, PERCENT_RANK() OVER (PARTITION BY e.show_id ORDER BY t.total) AS pr FROM episodes e JOIN t ON t.episode_id = e.episode_id)
SELECT s.title, r.ep_no, r.total, ROUND(r.pr, 2) FROM r JOIN shows s ON s.show_id = r.show_id WHERE r.pr >= 0.8 ORDER BY s.title, r.pr DESC, r.ep_no;""",)),
    S("sponsor-dominance", 4,
      "Sponsor dominance: for every show add up the earnings of all spots (episode total downloads / 1000 x cpm cents) per sponsor, and report the sponsors that earn more than half of the show's spot earnings. "
      "Columns: show title, sponsor name, sponsor's earnings in cents rounded to the nearest whole number, their share of the show in percent with 1 decimal. Order by share descending, then show title.",
      f"""WITH t AS {TOTALS}, e AS (SELECT ep.show_id, sp.sponsor_id, SUM(COALESCE(t.total, 0) / 1000.0 * sp.cpm_cents) AS earn FROM spots sp JOIN episodes ep ON ep.episode_id = sp.episode_id LEFT JOIN t ON t.episode_id = sp.episode_id GROUP BY ep.show_id, sp.sponsor_id),
x AS (SELECT *, earn / SUM(earn) OVER (PARTITION BY show_id) AS share FROM e)
SELECT s.title, so.name AS sponsor, CAST(ROUND(x.earn) AS INTEGER) AS earn_cents, ROUND(100.0 * x.share, 1) AS share_pct FROM x JOIN shows s ON s.show_id = x.show_id JOIN sponsors so ON so.sponsor_id = x.sponsor_id WHERE x.share > 0.5 ORDER BY share_pct DESC, s.title;""",
      ["title", "sponsor", "earn_cents", "share_pct"], ordered=True, allow_empty=True, places=1,
      wrong=(f"""WITH e AS (SELECT ep.show_id, sp.sponsor_id, SUM(sp.cpm_cents) AS earn FROM spots sp JOIN episodes ep ON ep.episode_id = sp.episode_id GROUP BY ep.show_id, sp.sponsor_id), x AS (SELECT *, 1.0 * earn / SUM(earn) OVER (PARTITION BY show_id) AS share FROM e)
SELECT s.title, so.name, x.earn, ROUND(100.0 * x.share, 1) FROM x JOIN shows s ON s.show_id = x.show_id JOIN sponsors so ON so.sponsor_id = x.sponsor_id WHERE x.share > 0.5 ORDER BY 4 DESC, s.title;""",)),
    S("fix-ad-earnings", 3,
      "The earnings per episode in `query.sql` are inflated: it joins the daily rows with the spots, so every spot is multiplied by the number of download days, and it divides by 100 instead of 1000. "
      "Fix it: for every episode that has at least one spot, the total earnings in euros (episode downloads / 1000 x cpm cents summed over its spots, divided by 100), rounded to 2 decimals. "
      "Columns: show title, episode number, euros. Order by euros descending, then title, then episode number.",
      ref=f"""WITH t AS {TOTALS}
SELECT s.title, e.ep_no, ROUND(SUM(COALESCE(t.total, 0) / 1000.0 * sp.cpm_cents) / 100.0, 2) AS eur FROM spots sp JOIN episodes e ON e.episode_id = sp.episode_id JOIN shows s ON s.show_id = e.show_id LEFT JOIN t ON t.episode_id = e.episode_id GROUP BY e.episode_id ORDER BY eur DESC, s.title, e.ep_no;""",
      cols=["title", "ep_no", "eur"], ordered=True, show=False, places=2,
      buggy="""SELECT s.title, e.ep_no, ROUND(SUM(d.count / 100.0 * sp.cpm_cents) / 100.0, 2) AS eur FROM spots sp JOIN episodes e ON e.episode_id = sp.episode_id JOIN shows s ON s.show_id = e.show_id JOIN downloads d ON d.episode_id = e.episode_id
GROUP BY e.episode_id ORDER BY eur DESC, s.title, e.ep_no;"""),
]


@family("data-podcast-network", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL on podcast download counts: RANGE windows over calendar days, first-week shares, percent ranks, fan-out traps in sponsor revenue")
def podcast_network(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
