"""SQL script tasks on the bicycle workshop's bill of materials: price rules, restructuring the tree, flattening, stock consumption, cleanup, validation triggers (including a recursive cycle guard)."""
from fx import family
from generators.data import _sqlkit as K
from generators.data.sql_bikeshop import DOMAIN

S = K.ScriptSpec

EXPLODE = """WITH RECURSIVE x(top, part, qty) AS (
  SELECT parent_id, child_id, qty FROM bom
  UNION ALL SELECT x.top, b.child_id, x.qty * b.qty FROM x JOIN bom b ON b.parent_id = x.part
)"""

SPECS = [
    S("price-rise", 2,
      "Prices go up: raw parts that cost less than 1000 cents rise by 10%, all other raw parts by 5%. Compute in integer arithmetic and round half up: `(cost * 110 + 50) / 100` and `(cost * 105 + 50) / 100`. Parts without a price (NULL) and assemblies stay as they are. Write `update.sql`.",
      script="update.sql",
      ref="UPDATE parts SET unit_cost_cents = CASE WHEN unit_cost_cents < 1000 THEN (unit_cost_cents * 110 + 50) / 100 ELSE (unit_cost_cents * 105 + 50) / 100 END WHERE kind = 'raw' AND unit_cost_cents IS NOT NULL;",
      checks=["SELECT part_id, unit_cost_cents FROM parts"],
      buggy="UPDATE parts SET unit_cost_cents = CASE WHEN unit_cost_cents < 1000 THEN unit_cost_cents * 110 / 100 ELSE unit_cost_cents * 105 / 100 END;",
      wrong=("UPDATE parts SET unit_cost_cents = (unit_cost_cents * 105 + 50) / 100 WHERE kind = 'raw' AND unit_cost_cents IS NOT NULL;",)),
    S("spoke-set", 3,
      "Introduce an intermediate assembly for the wheel: create the assembly part `ASM-SPOKE-SET` (name `spoke set`, kind `assembly`, no cost, stock 0). In the BOM, the wheel `ASM-WHEEL` must no longer contain `RAW-RIM` and `RAW-SPOKE` directly; "
      "instead the wheel contains one `ASM-SPOKE-SET`, and the spoke set contains the rim (1) and the spokes (the quantity the wheel had before). All other BOM rows stay. Write `update.sql`.",
      script="update.sql",
      ref="""INSERT INTO parts (sku, name, kind, unit_cost_cents, stock) VALUES ('ASM-SPOKE-SET', 'spoke set', 'assembly', NULL, 0);
INSERT INTO bom (parent_id, child_id, qty) SELECT (SELECT part_id FROM parts WHERE sku = 'ASM-SPOKE-SET'), child_id, qty FROM bom WHERE parent_id = (SELECT part_id FROM parts WHERE sku = 'ASM-WHEEL') AND child_id IN (SELECT part_id FROM parts WHERE sku IN ('RAW-RIM', 'RAW-SPOKE'));
DELETE FROM bom WHERE parent_id = (SELECT part_id FROM parts WHERE sku = 'ASM-WHEEL') AND child_id IN (SELECT part_id FROM parts WHERE sku IN ('RAW-RIM', 'RAW-SPOKE'));
INSERT INTO bom (parent_id, child_id, qty) VALUES ((SELECT part_id FROM parts WHERE sku = 'ASM-WHEEL'), (SELECT part_id FROM parts WHERE sku = 'ASM-SPOKE-SET'), 1);""",
      checks=["SELECT p.sku, c.sku, b.qty FROM bom b JOIN parts p ON p.part_id = b.parent_id JOIN parts c ON c.part_id = b.child_id", "SELECT sku, name, kind, unit_cost_cents, stock FROM parts"],
      wrong=("""INSERT INTO parts (sku, name, kind, unit_cost_cents, stock) VALUES ('ASM-SPOKE-SET', 'spoke set', 'assembly', NULL, 0);
INSERT INTO bom (parent_id, child_id, qty) VALUES ((SELECT part_id FROM parts WHERE sku = 'ASM-WHEEL'), (SELECT part_id FROM parts WHERE sku = 'ASM-SPOKE-SET'), 1);""",)),
    S("replace-tube", 3,
      "The inner tube is replaced by a better model: create the raw part `RAW-TUBE-V2` (name `tube v2`, cost 5% above the old tube's cost rounded half up in integer arithmetic `(cost * 105 + 50) / 100`, stock 0), "
      "point every BOM row that uses `RAW-TUBE` to it (same quantities) and delete the old part `RAW-TUBE`. Write `update.sql`.",
      script="update.sql",
      ref="""INSERT INTO parts (sku, name, kind, unit_cost_cents, stock) SELECT 'RAW-TUBE-V2', 'tube v2', 'raw', (unit_cost_cents * 105 + 50) / 100, 0 FROM parts WHERE sku = 'RAW-TUBE';
UPDATE bom SET child_id = (SELECT part_id FROM parts WHERE sku = 'RAW-TUBE-V2') WHERE child_id = (SELECT part_id FROM parts WHERE sku = 'RAW-TUBE');
DELETE FROM parts WHERE sku = 'RAW-TUBE';""",
      checks=["SELECT p.sku, c.sku, b.qty FROM bom b JOIN parts p ON p.part_id = b.parent_id JOIN parts c ON c.part_id = b.child_id", "SELECT sku, name, kind, unit_cost_cents, stock FROM parts"],
      wrong=("""INSERT INTO parts (sku, name, kind, unit_cost_cents, stock) SELECT 'RAW-TUBE-V2', 'tube v2', 'raw', unit_cost_cents * 105 / 100, 0 FROM parts WHERE sku = 'RAW-TUBE';
UPDATE bom SET child_id = (SELECT part_id FROM parts WHERE sku = 'RAW-TUBE-V2') WHERE child_id = (SELECT part_id FROM parts WHERE sku = 'RAW-TUBE');
DELETE FROM parts WHERE sku = 'RAW-TUBE';""",)),
    S("order-empty-products", 3,
      "Production planning: for every finished product (an assembly that is not a component of anything) whose `stock` is 0, insert an order for 5 units due on `2036-09-30`. Products with stock keep no new order. Write `update.sql`.",
      script="update.sql",
      ref="INSERT INTO orders (part_id, qty, due_on) SELECT part_id, 5, '2036-09-30' FROM parts WHERE kind = 'assembly' AND stock = 0 AND part_id NOT IN (SELECT child_id FROM bom);",
      checks=["SELECT part_id, qty, due_on FROM orders"],
      wrong=("INSERT INTO orders (part_id, qty, due_on) SELECT part_id, 5, '2036-09-30' FROM parts WHERE kind = 'assembly' AND stock = 0;",)),
    S("rolled-cost-column", 4,
      "Add a column `rolled_cost_cents` (INTEGER, NULL allowed) to `parts` and fill it: for a raw part its own unit cost (NULL if unknown); for an assembly the sum over all raw parts below it of the multiplied quantity times the unit cost, "
      "or NULL when any raw part below it has no price. Write `update.sql`.",
      script="update.sql",
      ref=f"""ALTER TABLE parts ADD COLUMN rolled_cost_cents INTEGER;
UPDATE parts SET rolled_cost_cents = unit_cost_cents WHERE kind = 'raw';
{EXPLODE.replace('WITH RECURSIVE', 'CREATE TEMP TABLE flat AS WITH RECURSIVE')}
SELECT top, part, SUM(qty) AS qty FROM x GROUP BY top, part;
UPDATE parts SET rolled_cost_cents = (SELECT CASE WHEN SUM(r.unit_cost_cents IS NULL) > 0 THEN NULL ELSE SUM(f.qty * r.unit_cost_cents) END FROM flat f JOIN parts r ON r.part_id = f.part AND r.kind = 'raw' WHERE f.top = parts.part_id) WHERE kind = 'assembly';""",
      checks=["SELECT part_id, rolled_cost_cents FROM parts"], struct=["columns:parts"],
      wrong=("""ALTER TABLE parts ADD COLUMN rolled_cost_cents INTEGER;
UPDATE parts SET rolled_cost_cents = unit_cost_cents WHERE kind = 'raw';
UPDATE parts SET rolled_cost_cents = (SELECT SUM(b.qty * COALESCE(r.unit_cost_cents, 0)) FROM bom b JOIN parts r ON r.part_id = b.child_id AND r.kind = 'raw' WHERE b.parent_id = parts.part_id) WHERE kind = 'assembly';""",)),
    S("flatten-bom", 4,
      "Create the table `bom_flat (top_id INTEGER, part_id INTEGER, qty INTEGER, PRIMARY KEY (top_id, part_id))` and fill it with the exploded requirements: for every finished product (assembly that is not a component of anything) and every raw part somewhere below it the total quantity for one product "
      "(quantities multiply along paths and add up over paths). Write `update.sql`.",
      script="update.sql",
      ref=f"""CREATE TABLE bom_flat (top_id INTEGER, part_id INTEGER, qty INTEGER, PRIMARY KEY (top_id, part_id));
INSERT INTO bom_flat
{EXPLODE}
SELECT x.top, x.part, SUM(x.qty) FROM x JOIN parts r ON r.part_id = x.part AND r.kind = 'raw' WHERE x.top IN (SELECT part_id FROM parts WHERE kind = 'assembly' AND part_id NOT IN (SELECT child_id FROM bom)) GROUP BY x.top, x.part;""",
      checks=["SELECT top_id, part_id, qty FROM bom_flat"], struct=["tables", "columns:bom_flat"],
      wrong=("""CREATE TABLE bom_flat (top_id INTEGER, part_id INTEGER, qty INTEGER, PRIMARY KEY (top_id, part_id));
INSERT INTO bom_flat SELECT parent_id, child_id, qty FROM bom WHERE parent_id IN (SELECT part_id FROM parts WHERE kind = 'assembly' AND part_id NOT IN (SELECT child_id FROM bom)) AND child_id IN (SELECT part_id FROM parts WHERE kind = 'raw');""",)),
    S("consume-stock", 4,
      "Order number 1 (the order with `order_id` 1) has just been built: take the raw parts it used out of stock. Every raw part below the ordered assembly loses `order qty x exploded quantity per unit` units from its `stock` (the stock may go negative; "
      "assemblies keep their stock). Raw parts that are not below the ordered assembly are untouched. Write `update.sql`.",
      script="update.sql",
      ref=f"""CREATE TEMP TABLE used AS
{EXPLODE}
SELECT x.part AS part_id, SUM(x.qty) * (SELECT qty FROM orders WHERE order_id = 1) AS n FROM x WHERE x.top = (SELECT part_id FROM orders WHERE order_id = 1) GROUP BY x.part;
UPDATE parts SET stock = stock - (SELECT n FROM used WHERE used.part_id = parts.part_id) WHERE kind = 'raw' AND part_id IN (SELECT part_id FROM used);""",
      checks=["SELECT part_id, stock FROM parts"],
      wrong=("""UPDATE parts SET stock = stock - (SELECT o.qty * b.qty FROM orders o JOIN bom b ON b.parent_id = o.part_id WHERE o.order_id = 1 AND b.child_id = parts.part_id) WHERE kind = 'raw' AND part_id IN (SELECT b.child_id FROM orders o JOIN bom b ON b.parent_id = o.part_id WHERE o.order_id = 1);""",)),
    S("drop-unused-raw", 2,
      "Delete the raw parts that no BOM row uses as a child. Assemblies, and raw parts that are used somewhere, stay. Write `update.sql`.",
      script="update.sql",
      ref="DELETE FROM parts WHERE kind = 'raw' AND part_id NOT IN (SELECT child_id FROM bom);",
      checks=["SELECT part_id FROM parts"],
      wrong=("DELETE FROM parts WHERE part_id NOT IN (SELECT child_id FROM bom);",)),
    S("positive-qty-trigger", 4,
      "Reject nonsense quantities: create two triggers, one `BEFORE INSERT` and one `BEFORE UPDATE OF qty` on `bom`, that abort (with `RAISE(ABORT, ...)`) when the new `qty` is zero or negative. Valid statements keep working. Write `update.sql`.",
      script="update.sql",
      ref="""CREATE TRIGGER bom_qty_insert BEFORE INSERT ON bom WHEN NEW.qty <= 0 BEGIN SELECT RAISE(ABORT, 'qty must be positive'); END;
CREATE TRIGGER bom_qty_update BEFORE UPDATE OF qty ON bom WHEN NEW.qty <= 0 BEGIN SELECT RAISE(ABORT, 'qty must be positive'); END;""",
      post=[{"sql": "INSERT INTO bom (parent_id, child_id, qty) SELECT parent_id, (SELECT MAX(part_id) FROM parts), 0 FROM bom LIMIT 1"},
            {"sql": "UPDATE bom SET qty = -1 WHERE rowid = (SELECT MIN(rowid) FROM bom)"},
            {"sql": "UPDATE bom SET qty = qty + 1 WHERE rowid = (SELECT MIN(rowid) FROM bom)"}],
      checks=["SELECT parent_id, child_id, qty FROM bom", "SELECT name FROM sqlite_master WHERE type = 'trigger'"], struct=["triggers"],
      wrong=("""CREATE TRIGGER bom_qty_insert BEFORE INSERT ON bom WHEN NEW.qty <= 0 BEGIN SELECT RAISE(ABORT, 'qty must be positive'); END;""",)),
    S("no-cycles-trigger", 5,
      "A bill of materials must not contain cycles. Create a trigger that makes an `INSERT` into `bom` fail (`RAISE(ABORT, ...)`) when it would close a cycle: the new child is the new parent itself, or the new parent is reachable below the new child "
      "(through any chain of existing BOM rows). Harmless inserts must still work. Write `update.sql`.",
      script="update.sql",
      ref="""CREATE TRIGGER bom_no_cycle BEFORE INSERT ON bom
WHEN NEW.parent_id = NEW.child_id OR EXISTS (
  WITH RECURSIVE below(id) AS (SELECT NEW.child_id UNION SELECT b.child_id FROM bom b JOIN below ON b.parent_id = below.id)
  SELECT 1 FROM below WHERE id = NEW.parent_id)
BEGIN SELECT RAISE(ABORT, 'cycle in the bill of materials'); END;""",
      post=[{"sql": "INSERT INTO bom (parent_id, child_id, qty) VALUES (1, 1, 1)"},
            {"sql": "INSERT INTO bom (parent_id, child_id, qty) SELECT child_id, parent_id, 1 FROM bom WHERE parent_id IN (SELECT part_id FROM parts WHERE kind = 'assembly') AND child_id IN (SELECT part_id FROM parts WHERE kind = 'assembly') ORDER BY rowid LIMIT 1"},
            {"sql": "INSERT INTO bom (parent_id, child_id, qty) SELECT (SELECT MIN(part_id) FROM parts WHERE kind = 'assembly'), (SELECT MAX(part_id) FROM parts), 2 WHERE (SELECT MAX(part_id) FROM parts) NOT IN (SELECT child_id FROM bom WHERE parent_id = (SELECT MIN(part_id) FROM parts WHERE kind = 'assembly'))"}],
      checks=["SELECT parent_id, child_id, qty FROM bom"], struct=["triggers"],
      wrong=("""CREATE TRIGGER bom_no_cycle BEFORE INSERT ON bom WHEN NEW.parent_id = NEW.child_id BEGIN SELECT RAISE(ABORT, 'cycle'); END;""",)),
    S("bom-names-view", 2,
      "Create a view `bom_names` with the columns `parent_sku`, `child_sku`, `qty` and `child_kind` (the kind of the child part), one row per BOM row. Write `update.sql`.",
      script="update.sql",
      ref="CREATE VIEW bom_names AS SELECT p.sku AS parent_sku, c.sku AS child_sku, b.qty, c.kind AS child_kind FROM bom b JOIN parts p ON p.part_id = b.parent_id JOIN parts c ON c.part_id = b.child_id;",
      checks=["SELECT parent_sku, child_sku, qty, child_kind FROM bom_names"], struct=["views", "tables"],
      wrong=("CREATE VIEW bom_names AS SELECT p.sku AS parent_sku, c.sku AS child_sku, b.qty, p.kind AS child_kind FROM bom b JOIN parts p ON p.part_id = b.parent_id JOIN parts c ON c.part_id = b.child_id;",)),
]


@family("data-bike-workshop-updates", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL update scripts on a bill of materials: integer price rules, tree restructuring, recursive flattening and rollups, stock consumption, validation triggers including a recursive cycle guard")
def bike_workshop_updates(rng, n):
    return K.script_tasks(DOMAIN, SPECS, rng, n)
