"""SQL tasks on an invented cheese-ageing cave's check log (weight loss, turning lapses, out-of-range runs, medians, quartiles, moving averages)."""
from datetime import date, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE batches (
      batch_id  INTEGER PRIMARY KEY,
      cheese    TEXT NOT NULL,
      milk      TEXT NOT NULL,
      made_on   TEXT NOT NULL,
      wheels    INTEGER NOT NULL
    );
    CREATE TABLE wheels (
      wheel_id  INTEGER PRIMARY KEY,
      batch_id  INTEGER NOT NULL REFERENCES batches(batch_id),
      start_g   INTEGER NOT NULL,              -- weight when it went into the cave
      shelf     TEXT NOT NULL
    );
    CREATE TABLE checks (
      check_id      INTEGER PRIMARY KEY,
      wheel_id      INTEGER NOT NULL REFERENCES wheels(wheel_id),
      checked_on    TEXT NOT NULL,
      weight_g      INTEGER NOT NULL,
      rind          TEXT NOT NULL CHECK (rind IN ('clean', 'bloom', 'mould', 'crack', 'wet')),
      humidity_pct  REAL NOT NULL,
      turned        INTEGER NOT NULL           -- 1 if the wheel was turned during this check
    );
    CREATE TABLE sales (
      sale_id      INTEGER PRIMARY KEY,
      wheel_id     INTEGER NOT NULL UNIQUE REFERENCES wheels(wheel_id),
      sold_on      TEXT NOT NULL,
      price_cents  INTEGER NOT NULL,
      buyer        TEXT NOT NULL
    );
''')

DOC = dd('''
    The Tarn Hollow cheese cave ages wheels from several batches and records every inspection.

    * A **batch** is made on one day; its wheels start at `start_g` grams and sit on a `shelf`.
    * A **check** records weight, rind condition, humidity and whether the wheel was turned. Rinds `mould`, `crack` and `wet` are **defects**; `clean` and `bloom` are fine.
    * Weight loss is `(start_g - weight) / start_g` in percent. The cave's target humidity is 82 to 88 percent (both ends are fine).
    * A wheel must be turned at least every 3 days: two consecutive *turned* checks more than 3 days apart are a **turning lapse**.
    * A wheel is **sold** at most once (`sales.wheel_id` is unique). Age at sale is the number of days from the batch's `made_on` to `sold_on`.
    * Dates are ISO text. The cave's "today" is **2034-02-10**.
''')

CHEESES = [("alpine tomme", "cow"), ("blue vein", "sheep"), ("washed rind", "cow"), ("farm cheddar", "cow"), ("smoked goat", "goat"), ("mountain gouda", "cow")]
SHELVES = ["A1", "A2", "B1", "B2", "C1"]
BUYERS = ["Deli Norte", "The Larder", "Crumb & Rind", "Harbour Market", "Cellar Door", "Quarter Bakery"]


def gen(rng, big):
    nb = 8 if big else 4
    batches, wheels, checks, sales = [], [], [], []
    wid = cid = sid = 0
    for b in range(nb):
        ch, milk = CHEESES[b % len(CHEESES)] if big else CHEESES[b]
        made = date(2033, 6, 1) + timedelta(days=rng.randint(0, 160))
        nw = rng.randint(3, 6) if big else rng.randint(3, 4)
        batches.append((b + 1, ch, milk, made.isoformat(), nw))
        for _ in range(nw):
            wid += 1
            start = rng.choice([1800, 2000, 2400, 4100, 4300])
            wheels.append((wid, b + 1, start, rng.choice(SHELVES)))
            day, w, hum = made + timedelta(days=rng.randint(5, 9)), float(start), rng.choice([83.0, 85.0, 87.0])
            horizon = date(2034, 2, 10)
            sold = None
            if rng.random() < 0.6 and (horizon - made).days > 70:
                sold = made + timedelta(days=rng.randint(60, min(150, (horizon - made).days)))
            end = sold - timedelta(days=1) if sold else horizon
            lap = 0
            while day <= end:
                lap += 1
                w -= start * rng.choice([0.001, 0.002, 0.003, 0.004])
                if rng.random() < 0.12:
                    w += start * 0.012  # a wheel can regain weight (humid spell, rewetting)
                hum = max(76.0, min(93.0, hum + rng.choice([-3.0, -1.5, -0.5, 0.0, 0.5, 1.5, 3.0])))
                rind = rng.choice(["clean", "clean", "clean", "bloom", "bloom"])
                if (day - made).days > 30 and rng.random() < 0.06:
                    rind = rng.choice(["mould", "crack", "wet"])
                cid += 1
                checks.append((cid, wid, day.isoformat(), int(w), rind, hum, 1 if rng.random() < 0.7 else 0))
                day += timedelta(days=rng.choice([1, 2, 2, 3, 4, 5]))
            if sold is not None:
                sid += 1
                sales.append((sid, wid, sold.isoformat(), rng.choice([1800, 2400, 3200, 4500, 5200]), rng.choice(BUYERS)))
    # plant: one wheel that was never checked and unsold, one wheel sold right after a defect check, one wheel with a run of wet checks
    wid += 1
    wheels.append((wid, 1, 2000, "C1"))
    wid += 1
    wheels.append((wid, 2, 2000, "C1"))
    cid += 1
    checks.append((cid, wid, "2033-12-01", 1900, "mould", 85.0, 1))
    sid += 1
    sales.append((sid, wid, "2033-12-02", 2400, "The Larder"))
    wid += 1
    wheels.append((wid, 1, 2000, "B2"))
    for k, h in enumerate((89.5, 91.0, 90.0, 88.5, 80.0, 66.5, 98.2)):
        cid += 1
        checks.append((cid, wid, (date(2034, 1, 1) + timedelta(days=2 * k)).isoformat(), 1950 - 3 * k, "clean", h, 1))
    made1 = date.fromisoformat(batches[0][3])
    for age in (60, 120, 59, 119):  # sales exactly on the bracket boundaries
        wid += 1
        wheels.append((wid, 1, 2000, "A1"))
        sid += 1
        sales.append((sid, wid, (made1 + timedelta(days=age)).isoformat(), 2000 + age, "Cellar Door"))
    return {"batches": batches, "wheels": wheels, "checks": checks, "sales": sales}


DOMAIN = K.Domain("cheesecave", "Tarn Hollow cheese cave: ageing log", SCHEMA, DOC, gen)
S = K.Spec

LAST_W = "(SELECT c.weight_g FROM checks c WHERE c.wheel_id = w.wheel_id ORDER BY c.checked_on DESC, c.check_id DESC LIMIT 1)"

SPECS = [
    S("wheels-per-cheese", 1,
      "For each cheese: the number of batches, the number of wheels recorded in `wheels`, and their total starting weight in kilograms (1 decimal). Order by cheese.",
      "SELECT b.cheese, COUNT(DISTINCT b.batch_id) AS batches, COUNT(w.wheel_id) AS wheels, ROUND(SUM(w.start_g) / 1000.0, 1) AS start_kg FROM batches b LEFT JOIN wheels w ON w.batch_id = b.batch_id GROUP BY b.cheese ORDER BY b.cheese;",
      ["cheese", "batches", "wheels", "start_kg"], ordered=True,
      wrong=("SELECT b.cheese, COUNT(*), SUM(b.wheels), ROUND(SUM(w.start_g) / 1000.0, 1) FROM batches b JOIN wheels w ON w.batch_id = b.batch_id GROUP BY b.cheese ORDER BY b.cheese;",)),
    S("never-checked", 2,
      "Wheels that have never been checked and are not sold yet: wheel id, batch id and shelf, ordered by wheel id.",
      "SELECT w.wheel_id, w.batch_id, w.shelf FROM wheels w WHERE NOT EXISTS (SELECT 1 FROM checks c WHERE c.wheel_id = w.wheel_id) AND NOT EXISTS (SELECT 1 FROM sales s WHERE s.wheel_id = w.wheel_id) ORDER BY w.wheel_id;",
      ["wheel_id", "batch_id", "shelf"], ordered=True),
    S("weight-loss", 2,
      "Weight loss so far of every wheel that has at least one check: wheel id, cheese, the weight at its latest check (latest date, ties by check id) and the loss in percent of its starting weight rounded to 1 decimal. "
      "Show the wheels that have lost at least 8 percent, biggest loss first, ties by wheel id.",
      f"""SELECT w.wheel_id, b.cheese, {LAST_W} AS last_g, ROUND(100.0 * (w.start_g - {LAST_W}) / w.start_g, 1) AS loss_pct
FROM wheels w JOIN batches b ON b.batch_id = w.batch_id
WHERE {LAST_W} IS NOT NULL AND 100.0 * (w.start_g - {LAST_W}) / w.start_g >= 8 ORDER BY loss_pct DESC, w.wheel_id;""",
      ["wheel_id", "cheese", "last_g", "loss_pct"], ordered=True,
      wrong=("""SELECT w.wheel_id, b.cheese, MIN(c.weight_g), ROUND(100.0 * (w.start_g - MIN(c.weight_g)) / w.start_g, 1) AS l FROM wheels w JOIN batches b ON b.batch_id = w.batch_id JOIN checks c ON c.wheel_id = w.wheel_id GROUP BY w.wheel_id HAVING l >= 8 ORDER BY l DESC, w.wheel_id;""",)),
    S("defect-rate", 2,
      "For each cheese: how many of its wheels have at least one check at all, how many of those have shown a defect (rind mould, crack or wet) at least once, and the percentage with 1 decimal. Order by percentage descending, then cheese.",
      """SELECT b.cheese, COUNT(DISTINCT w.wheel_id) AS checked, COUNT(DISTINCT CASE WHEN c.rind IN ('mould', 'crack', 'wet') THEN w.wheel_id END) AS defective,
       ROUND(100.0 * COUNT(DISTINCT CASE WHEN c.rind IN ('mould', 'crack', 'wet') THEN w.wheel_id END) / COUNT(DISTINCT w.wheel_id), 1) AS pct
FROM batches b JOIN wheels w ON w.batch_id = b.batch_id JOIN checks c ON c.wheel_id = w.wheel_id GROUP BY b.cheese ORDER BY pct DESC, b.cheese;""",
      ["cheese", "checked", "defective", "pct"], ordered=True,
      wrong=("""SELECT b.cheese, COUNT(*), SUM(c.rind IN ('mould','crack','wet')), ROUND(100.0 * SUM(c.rind IN ('mould','crack','wet')) / COUNT(*), 1) AS p FROM batches b JOIN wheels w ON w.batch_id = b.batch_id JOIN checks c ON c.wheel_id = w.wheel_id GROUP BY b.cheese ORDER BY p DESC, b.cheese;""",)),
    S("sold-after-defect", 3,
      "Customers who may have received a bad wheel: sold wheels whose last check before the sale date (checks on the sale day do not count; latest date first, ties by check id) showed a defect. "
      "Columns: wheel id, buyer, sale date, defect (the rind value). Order by sale date, then wheel id.",
      """WITH last AS (
  SELECT s.wheel_id, s.sold_on, s.buyer, c.rind, ROW_NUMBER() OVER (PARTITION BY s.wheel_id ORDER BY c.checked_on DESC, c.check_id DESC) AS rn
  FROM sales s JOIN checks c ON c.wheel_id = s.wheel_id AND c.checked_on < s.sold_on
)
SELECT wheel_id, buyer, sold_on, rind AS defect FROM last WHERE rn = 1 AND rind IN ('mould', 'crack', 'wet') ORDER BY sold_on, wheel_id;""",
      ["wheel_id", "buyer", "sold_on", "defect"], ordered=True, allow_empty=True,
      wrong=("""SELECT s.wheel_id, s.buyer, s.sold_on, c.rind FROM sales s JOIN checks c ON c.wheel_id = s.wheel_id WHERE c.rind IN ('mould','crack','wet') ORDER BY s.sold_on, s.wheel_id;""",)),
    S("age-at-sale", 3,
      "Sales by age bracket and cheese: the age at sale is the days from the batch's `made_on` to `sold_on`; bracket `young` is under 60 days, `mature` is 60 to 119, `old` is 120 or more. "
      "For every cheese and bracket that occurs: cheese, bracket, number of sales and revenue in euros with 2 decimals. Order by cheese, then bracket in the order young, mature, old.",
      """SELECT b.cheese,
       CASE WHEN julianday(s.sold_on) - julianday(b.made_on) < 60 THEN 'young' WHEN julianday(s.sold_on) - julianday(b.made_on) < 120 THEN 'mature' ELSE 'old' END AS bracket,
       COUNT(*) AS sales, ROUND(SUM(s.price_cents) / 100.0, 2) AS revenue_eur
FROM sales s JOIN wheels w ON w.wheel_id = s.wheel_id JOIN batches b ON b.batch_id = w.batch_id
GROUP BY b.cheese, bracket ORDER BY b.cheese, CASE bracket WHEN 'young' THEN 1 WHEN 'mature' THEN 2 ELSE 3 END;""",
      ["cheese", "bracket", "sales", "revenue_eur"], ordered=True,
      wrong=("""SELECT b.cheese, CASE WHEN julianday(s.sold_on) - julianday(b.made_on) <= 60 THEN 'young' WHEN julianday(s.sold_on) - julianday(b.made_on) <= 120 THEN 'mature' ELSE 'old' END AS br, COUNT(*), ROUND(SUM(s.price_cents) / 100.0, 2)
FROM sales s JOIN wheels w ON w.wheel_id = s.wheel_id JOIN batches b ON b.batch_id = w.batch_id GROUP BY b.cheese, br ORDER BY b.cheese, CASE br WHEN 'young' THEN 1 WHEN 'mature' THEN 2 ELSE 3 END;""",)),
    S("best-month", 3,
      "For each cheese the calendar month (`YYYY-MM` of `sold_on`) with the highest revenue; ties go to the earlier month. Columns: cheese, month, revenue in cents, number of sales that month. Order by cheese.",
      """WITH m AS (SELECT b.cheese, substr(s.sold_on, 1, 7) AS month, SUM(s.price_cents) AS rev, COUNT(*) AS n FROM sales s JOIN wheels w ON w.wheel_id = s.wheel_id JOIN batches b ON b.batch_id = w.batch_id GROUP BY b.cheese, month),
r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY cheese ORDER BY rev DESC, month) AS rn FROM m)
SELECT cheese, month, rev, n FROM r WHERE rn = 1 ORDER BY cheese;""",
      ["cheese", "month", "revenue_cents", "sales"], ordered=True,
      wrong=("""SELECT b.cheese, substr(s.sold_on, 1, 7), MAX(s.price_cents), COUNT(*) FROM sales s JOIN wheels w ON w.wheel_id = s.wheel_id JOIN batches b ON b.batch_id = w.batch_id GROUP BY b.cheese ORDER BY b.cheese;""",)),
    S("turning-lapses", 4,
      "Turning lapses: for each wheel look only at the checks where it was turned (`turned = 1`), in date order (ties by check id), and report every pair of consecutive turned checks that are more than 3 days apart: "
      "wheel id, date of the earlier, date of the later, days between. Order by days between descending, then wheel id, then earlier date.",
      """WITH t AS (SELECT wheel_id, checked_on, LAG(checked_on) OVER (PARTITION BY wheel_id ORDER BY checked_on, check_id) AS prev FROM checks WHERE turned = 1)
SELECT wheel_id, prev AS from_date, checked_on AS to_date, CAST(julianday(checked_on) - julianday(prev) AS INTEGER) AS days
FROM t WHERE prev IS NOT NULL AND julianday(checked_on) - julianday(prev) > 3 ORDER BY days DESC, wheel_id, from_date;""",
      ["wheel_id", "from_date", "to_date", "days"], ordered=True,
      wrong=("""WITH t AS (SELECT wheel_id, checked_on, LAG(checked_on) OVER (PARTITION BY wheel_id ORDER BY checked_on, check_id) AS prev FROM checks)
SELECT wheel_id, prev, checked_on, CAST(julianday(checked_on) - julianday(prev) AS INTEGER) AS d FROM t WHERE prev IS NOT NULL AND julianday(checked_on) - julianday(prev) > 3 ORDER BY d DESC, wheel_id, prev;""",)),
    S("humidity-excursions", 4,
      "Humidity excursions: for each wheel, find runs of consecutive checks (date order, ties by check id) whose humidity is outside the 82 to 88 range, and report the runs of 3 or more checks: "
      "wheel id, date of the first check in the run, date of the last, and the number of checks. Order by wheel id, then first date.",
      """WITH c AS (
  SELECT wheel_id, checked_on, (humidity_pct < 82 OR humidity_pct > 88) AS bad,
         ROW_NUMBER() OVER (PARTITION BY wheel_id ORDER BY checked_on, check_id) AS rn,
         ROW_NUMBER() OVER (PARTITION BY wheel_id, (humidity_pct < 82 OR humidity_pct > 88) ORDER BY checked_on, check_id) AS rk
  FROM checks
)
SELECT wheel_id, MIN(checked_on) AS first_on, MAX(checked_on) AS last_on, COUNT(*) AS checks FROM c WHERE bad = 1 GROUP BY wheel_id, rn - rk HAVING COUNT(*) >= 3 ORDER BY wheel_id, first_on;""",
      ["wheel_id", "first_on", "last_on", "checks"], ordered=True,
      wrong=("""SELECT wheel_id, MIN(checked_on), MAX(checked_on), COUNT(*) FROM checks WHERE humidity_pct < 82 OR humidity_pct > 88 GROUP BY wheel_id HAVING COUNT(*) >= 3 ORDER BY wheel_id, 2;""",)),
    S("median-humidity", 4,
      "Median humidity of all checks per cheese (the mean of the two middle values when the count is even), rounded to 2 decimals, and the number of checks. Order by cheese.",
      """WITH h AS (SELECT b.cheese, c.humidity_pct AS h, ROW_NUMBER() OVER (PARTITION BY b.cheese ORDER BY c.humidity_pct, c.check_id) AS rn, COUNT(*) OVER (PARTITION BY b.cheese) AS n
  FROM checks c JOIN wheels w ON w.wheel_id = c.wheel_id JOIN batches b ON b.batch_id = w.batch_id)
SELECT cheese, MAX(n) AS checks, ROUND(AVG(h), 2) AS median FROM h WHERE rn IN ((n + 1) / 2, (n + 2) / 2) GROUP BY cheese ORDER BY cheese;""",
      ["cheese", "checks", "median"], ordered=True, places=2,
      wrong=("""SELECT b.cheese, COUNT(*), ROUND(AVG(c.humidity_pct), 2) FROM checks c JOIN wheels w ON w.wheel_id = c.wheel_id JOIN batches b ON b.batch_id = w.batch_id GROUP BY b.cheese ORDER BY b.cheese;""",)),
    S("price-quartiles", 4,
      "Price quartiles inside each cheese: split the sales of a cheese into four groups with NTILE(4) over the price (lowest first, ties by sale id) and report, for every cheese and quartile that occurs, the number of sales, the lowest and the highest price in cents. "
      "Order by cheese, then quartile. (Cheeses with fewer than 4 sales fill only the first quartiles.)",
      """WITH q AS (SELECT b.cheese, s.price_cents, NTILE(4) OVER (PARTITION BY b.cheese ORDER BY s.price_cents, s.sale_id) AS quartile
  FROM sales s JOIN wheels w ON w.wheel_id = s.wheel_id JOIN batches b ON b.batch_id = w.batch_id)
SELECT cheese, quartile, COUNT(*) AS sales, MIN(price_cents) AS lowest, MAX(price_cents) AS highest FROM q GROUP BY cheese, quartile ORDER BY cheese, quartile;""",
      ["cheese", "quartile", "sales", "lowest", "highest"], ordered=True,
      wrong=("""WITH q AS (SELECT b.cheese, s.price_cents, NTILE(4) OVER (PARTITION BY b.cheese ORDER BY s.price_cents DESC, s.sale_id) AS quartile FROM sales s JOIN wheels w ON w.wheel_id = s.wheel_id JOIN batches b ON b.batch_id = w.batch_id)
SELECT cheese, quartile, COUNT(*), MIN(price_cents), MAX(price_cents) FROM q GROUP BY cheese, quartile ORDER BY cheese, quartile;""",)),
    S("humid-moving-average", 4,
      "Smooth the humidity readings: for every check compute the average humidity of that check and the two checks before it on the same wheel (date order, ties by check id; fewer checks at the start of a wheel's history just average what exists). "
      "List the checks where this moving average is above 88: wheel id, check date, moving average with 2 decimals. Order by wheel id, then date.",
      """WITH m AS (SELECT wheel_id, checked_on, check_id, AVG(humidity_pct) OVER (PARTITION BY wheel_id ORDER BY checked_on, check_id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS avg3 FROM checks)
SELECT wheel_id, checked_on, ROUND(avg3, 2) AS avg_humidity FROM m WHERE avg3 > 88 ORDER BY wheel_id, checked_on, check_id;""",
      ["wheel_id", "checked_on", "avg_humidity"], ordered=True, places=2, allow_empty=True,
      wrong=("""WITH m AS (SELECT wheel_id, checked_on, check_id, AVG(humidity_pct) OVER (PARTITION BY wheel_id ORDER BY checked_on, check_id ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS avg3 FROM checks)
SELECT wheel_id, checked_on, ROUND(avg3, 2) FROM m WHERE avg3 > 88 ORDER BY wheel_id, checked_on, check_id;""",)),
    S("fix-loss-per-batch", 3,
      "The weight-loss report in `query.sql` is wrong: it compares each wheel's first and last check instead of its starting weight, and averages over checks instead of wheels. "
      "Fix it so that it returns, per batch id, the number of wheels that have at least one check and the average (over those wheels) of the loss in percent between `start_g` and the weight at the wheel's latest check "
      "(latest date, ties by check id), rounded to 2 decimals. Order by batch id.",
      ref=f"""SELECT w.batch_id, COUNT(*) AS wheels, ROUND(AVG(100.0 * (w.start_g - {LAST_W}) / w.start_g), 2) AS avg_loss_pct FROM wheels w WHERE {LAST_W} IS NOT NULL GROUP BY w.batch_id ORDER BY w.batch_id;""",
      cols=["batch_id", "wheels", "avg_loss_pct"], ordered=True, places=2, show=False,
      buggy="""SELECT w.batch_id, COUNT(*) AS wheels,
       ROUND(AVG(100.0 * (first.weight_g - last.weight_g) / first.weight_g), 2) AS avg_loss_pct
FROM wheels w
JOIN checks first ON first.wheel_id = w.wheel_id AND first.checked_on = (SELECT MIN(checked_on) FROM checks WHERE wheel_id = w.wheel_id)
JOIN checks last ON last.wheel_id = w.wheel_id AND last.checked_on = (SELECT MAX(checked_on) FROM checks WHERE wheel_id = w.wheel_id)
GROUP BY w.batch_id ORDER BY w.batch_id;"""),
]


@family("data-cheese-cave", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL on a cheese cave's ageing log: weight loss, turning lapses, humidity excursions, medians, NTILE quartiles, moving averages")
def cheese_cave(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
