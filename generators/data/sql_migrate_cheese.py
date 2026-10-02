"""SQL script tasks on the cheese cave database: derived columns, data repairs, status flags with triggers, views and history tables."""
from fx import family
from generators.data import _sqlkit as K
from generators.data.sql_cheesecave import DOMAIN

S = K.ScriptSpec

SPECS = [
    S("ripe-date-column", 2,
      "Add a column `ripe_on` (TEXT) to `batches` and set it to the date 90 days after `made_on` (`YYYY-MM-DD`). Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="ALTER TABLE batches ADD COLUMN ripe_on TEXT;\nUPDATE batches SET ripe_on = date(made_on, '+90 days');",
      checks=["SELECT batch_id, ripe_on FROM batches"], struct=["columns:batches"],
      wrong=("ALTER TABLE batches ADD COLUMN ripe_on TEXT;\nUPDATE batches SET ripe_on = date(made_on, '+3 months');",)),
    S("cap-impossible-weights", 3,
      "Some checks report a weight above the wheel's starting weight, which is impossible. Fix the data: for every check whose `weight_g` exceeds the wheel's `start_g`, set `weight_g` to `start_g`. Other checks stay. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="UPDATE checks SET weight_g = (SELECT w.start_g FROM wheels w WHERE w.wheel_id = checks.wheel_id) WHERE weight_g > (SELECT w.start_g FROM wheels w WHERE w.wheel_id = checks.wheel_id);",
      checks=["SELECT check_id, weight_g FROM checks"],
      buggy="UPDATE checks SET weight_g = (SELECT MAX(start_g) FROM wheels);",
      wrong=("UPDATE checks SET weight_g = (SELECT w.start_g FROM wheels w WHERE w.wheel_id = checks.wheel_id) WHERE weight_g >= (SELECT w.start_g FROM wheels w WHERE w.wheel_id = checks.wheel_id) - 5;",)),
    S("merge-shelves", 2,
      "The cave was rebuilt: shelves `A1` and `A2` become one shelf `A`. Update the wheels accordingly; all other shelves keep their names. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="UPDATE wheels SET shelf = 'A' WHERE shelf IN ('A1', 'A2');",
      checks=["SELECT wheel_id, shelf FROM wheels"],
      wrong=("UPDATE wheels SET shelf = 'A' WHERE shelf = 'A1';",)),
    S("humidity-clamp", 2,
      "A faulty sensor wrote impossible humidities. Clamp `humidity_pct` of every check into the range 70 to 95 (values below 70 become 70, values above 95 become 95; the rest stays). Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="UPDATE checks SET humidity_pct = MIN(95.0, MAX(70.0, humidity_pct));",
      checks=["SELECT check_id, humidity_pct FROM checks"],
      wrong=("UPDATE checks SET humidity_pct = MAX(70.0, humidity_pct);",)),
    S("price-floor", 2,
      "Raise every sale price below 2000 cents to exactly 2000 cents (the agreed minimum). Prices of 2000 and above stay. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="UPDATE sales SET price_cents = 2000 WHERE price_cents < 2000;",
      checks=["SELECT sale_id, price_cents FROM sales"],
      wrong=("UPDATE sales SET price_cents = 2000 WHERE price_cents < 1800;", "UPDATE sales SET price_cents = MAX(price_cents, 2200);")),
    S("sold-flag-and-trigger", 4,
      "Add a column `sold` (INTEGER, NOT NULL, default 0) to `wheels`, set it to 1 for every wheel that has a sale, and add a trigger that sets it to 1 whenever a row is inserted into `sales`. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="""ALTER TABLE wheels ADD COLUMN sold INTEGER NOT NULL DEFAULT 0;
UPDATE wheels SET sold = 1 WHERE wheel_id IN (SELECT wheel_id FROM sales);
CREATE TRIGGER sales_mark_sold AFTER INSERT ON sales BEGIN UPDATE wheels SET sold = 1 WHERE wheel_id = NEW.wheel_id; END;""",
      post=[{"sql": "INSERT INTO sales (wheel_id, sold_on, price_cents, buyer) SELECT wheel_id, '2034-02-09', 3000, 'Deli Norte' FROM wheels WHERE wheel_id NOT IN (SELECT wheel_id FROM sales) ORDER BY wheel_id LIMIT 2"}],
      checks=["SELECT wheel_id, sold FROM wheels"], struct=["columns:wheels", "triggers"],
      wrong=("""ALTER TABLE wheels ADD COLUMN sold INTEGER NOT NULL DEFAULT 0;
UPDATE wheels SET sold = 1 WHERE wheel_id IN (SELECT wheel_id FROM sales);""",)),
    S("needs-turning-view", 3,
      "Create a view `needs_turning` listing every wheel that has not been sold and whose latest *turned* check (`turned = 1`) is more than 3 days before 2034-02-10, or that has never been turned. "
      "Columns: `wheel_id`, `last_turned` (date of the latest turned check, NULL if never) and `days_since` (whole days from that date to 2034-02-10, NULL if never turned). Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="""CREATE VIEW needs_turning AS
SELECT w.wheel_id, MAX(c.checked_on) AS last_turned, CAST(julianday('2034-02-10') - julianday(MAX(c.checked_on)) AS INTEGER) AS days_since
FROM wheels w LEFT JOIN checks c ON c.wheel_id = w.wheel_id AND c.turned = 1
WHERE w.wheel_id NOT IN (SELECT wheel_id FROM sales) GROUP BY w.wheel_id HAVING MAX(c.checked_on) IS NULL OR julianday('2034-02-10') - julianday(MAX(c.checked_on)) > 3;""",
      checks=["SELECT wheel_id, last_turned, days_since FROM needs_turning"], struct=["views", "tables"],
      wrong=("""CREATE VIEW needs_turning AS SELECT w.wheel_id, MAX(c.checked_on) AS last_turned, CAST(julianday('2034-02-10') - julianday(MAX(c.checked_on)) AS INTEGER) AS days_since FROM wheels w JOIN checks c ON c.wheel_id = w.wheel_id AND c.turned = 1 GROUP BY w.wheel_id HAVING julianday('2034-02-10') - julianday(MAX(c.checked_on)) > 3;""",)),
    S("sync-wheel-counts", 3,
      "`batches.wheels` is meant to hold the number of rows in `wheels` for the batch, but the numbers drifted. Set it to the real count for every batch (0 for a batch without wheel rows). Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="UPDATE batches SET wheels = (SELECT COUNT(*) FROM wheels w WHERE w.batch_id = batches.batch_id);",
      checks=["SELECT batch_id, wheels FROM batches"],
      wrong=("UPDATE batches SET wheels = (SELECT COUNT(*) FROM wheels);",)),
    S("rind-change-history", 4,
      "Create `rind_changes (wheel_id INTEGER, changed_on TEXT, from_rind TEXT, to_rind TEXT)` and fill it with one row for every check whose rind differs from the previous check of the same wheel (previous by date, ties by check id): "
      "`changed_on` is the date of the later check. The first check of a wheel has no previous check and produces no row. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="""CREATE TABLE rind_changes (wheel_id INTEGER, changed_on TEXT, from_rind TEXT, to_rind TEXT);
INSERT INTO rind_changes
SELECT wheel_id, checked_on, prev_rind, rind FROM (SELECT wheel_id, checked_on, rind, LAG(rind) OVER (PARTITION BY wheel_id ORDER BY checked_on, check_id) AS prev_rind FROM checks) WHERE prev_rind IS NOT NULL AND prev_rind <> rind;""",
      checks=["SELECT wheel_id, changed_on, from_rind, to_rind FROM rind_changes"], struct=["tables", "columns:rind_changes"],
      wrong=("""CREATE TABLE rind_changes (wheel_id INTEGER, changed_on TEXT, from_rind TEXT, to_rind TEXT);
INSERT INTO rind_changes SELECT wheel_id, checked_on, NULL, rind FROM checks WHERE rind IN ('mould', 'crack', 'wet');""",)),
    S("defect-register", 3,
      "Create `defect_register (wheel_id INTEGER PRIMARY KEY, first_defect_on TEXT NOT NULL, defect_checks INTEGER NOT NULL)` with one row for every wheel that ever had a defect rind (`mould`, `crack` or `wet`): the date of its first such check and how many such checks it had. Write `maintenance.sql`.",
      script="maintenance.sql",
      ref="""CREATE TABLE defect_register (wheel_id INTEGER PRIMARY KEY, first_defect_on TEXT NOT NULL, defect_checks INTEGER NOT NULL);
INSERT INTO defect_register SELECT wheel_id, MIN(checked_on), COUNT(*) FROM checks WHERE rind IN ('mould', 'crack', 'wet') GROUP BY wheel_id;""",
      checks=["SELECT wheel_id, first_defect_on, defect_checks FROM defect_register"], struct=["tables", "columns:defect_register"],
      wrong=("""CREATE TABLE defect_register (wheel_id INTEGER PRIMARY KEY, first_defect_on TEXT NOT NULL, defect_checks INTEGER NOT NULL);
INSERT INTO defect_register SELECT wheel_id, MIN(checked_on), COUNT(*) FROM checks WHERE rind <> 'clean' GROUP BY wheel_id;""",)),
]


@family("data-cheese-cave-maintenance", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL maintenance scripts on a cheese cave database: derived columns, repairs, clamping, flag columns with triggers, views and history tables built with window functions")
def cheese_cave_maintenance(rng, n):
    return K.script_tasks(DOMAIN, SPECS, rng, n)
