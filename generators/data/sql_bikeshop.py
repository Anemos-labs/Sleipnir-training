"""SQL tasks on an invented bicycle workshop's bill of materials (recursive explosion with multiplied quantities, rollups, where-used, shortages by due date)."""
from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE parts (
      part_id          INTEGER PRIMARY KEY,
      sku              TEXT NOT NULL UNIQUE,
      name             TEXT NOT NULL,
      kind             TEXT NOT NULL CHECK (kind IN ('raw', 'assembly')),
      unit_cost_cents  INTEGER,                -- raw parts only; NULL = price not known yet
      stock            INTEGER NOT NULL
    );
    CREATE TABLE bom (
      parent_id  INTEGER NOT NULL REFERENCES parts(part_id),
      child_id   INTEGER NOT NULL REFERENCES parts(part_id),
      qty        INTEGER NOT NULL,             -- units of the child in ONE unit of the parent
      PRIMARY KEY (parent_id, child_id)
    );
    CREATE TABLE orders (
      order_id  INTEGER PRIMARY KEY,
      part_id   INTEGER NOT NULL REFERENCES parts(part_id),   -- the assembly to build
      qty       INTEGER NOT NULL,
      due_on    TEXT NOT NULL
    );
''')

DOC = dd('''
    The Ironwood Cycle Workshop builds bicycles from a bill of materials (BOM).

    * `parts` are either `raw` (bought, with a unit cost, or NULL if the price is not known yet) or `assembly` (built from other parts, no cost of its own).
    * `bom` says how many units of a child go into **one** unit of its parent. Assemblies can contain assemblies. The same part may appear in several assemblies and on several levels.
    * A **top-level** assembly is one that is not the child of any other part (the finished products).
    * Quantities multiply down the tree: 2 wheels per bike and 32 spokes per wheel need 64 spokes per bike. When a part is reachable through several paths, the quantities of all paths add up.
    * The **cost** of an assembly is the sum over its raw parts (with the multiplied quantities) of `qty x unit_cost_cents`. If any raw part below it has no price, the cost of the assembly is NULL.
    * `orders` ask for `qty` units of an assembly by `due_on`. For requirements, ignore the stock of assemblies and just explode the order down to raw parts. The stock of raw parts is what is on the shelf.
''')

TEMPL = {
    "bike": [("wheel", 2), ("frame", 1), ("drivetrain", 1), ("brakes", 1), ("cockpit", 1)],
    "ebike": [("wheel", 2), ("frame", 1), ("drivetrain", 1), ("brakes", 1), ("cockpit", 1), ("motor kit", 1)],
    "wheel": [("rim", 1), ("spoke", (28, 36)), ("hub", 1), ("tyre", 1), ("tube", 1)],
    "drivetrain": [("chain", 1), ("cassette", 1), ("crankset", 1), ("derailleur", 1)],
    "crankset": [("crank arm", 2), ("chainring", 1), ("crank bolt", (4, 6))],
    "brakes": [("brake lever", 2), ("caliper", 2), ("cable set", (1, 2))],
    "cockpit": [("handlebar", 1), ("stem", 1), ("grip", 2), ("headset", 1)],
    "motor kit": [("motor", 1), ("battery", 1), ("controller", 1), ("harness", 1)],
    "frame": [("frame tube set", 1), ("fork", 1), ("seat post", 1), ("frame bolt", (8, 12))],
}
RAW_COST = {"rim": 2400, "spoke": 18, "hub": 3100, "tyre": 1900, "tube": 650, "chain": 1400, "cassette": 2900, "derailleur": 3700, "crank arm": 2200, "chainring": 1500, "crank bolt": 90, "brake lever": 1250, "caliper": 2600,
            "cable set": 800, "handlebar": 1700, "stem": 1350, "grip": 450, "headset": 1600, "motor": 31000, "battery": 28000, "controller": 9500, "harness": 2200, "frame tube set": 14000, "fork": 6800, "seat post": 1900, "frame bolt": 60}
SPARE = ["bottle cage", "bell", "kickstand", "mudguard set", "pedal pair"]


def gen(rng, big):
    tpl = dict(TEMPL)
    if rng.random() < 0.5:  # the drivetrain is a flat list of parts in some designs
        tpl["drivetrain"] = [("chain", 1), ("cassette", 1), ("crank arm", 2), ("chainring", 1), ("crank bolt", (4, 6)), ("derailleur", 1)]
        del tpl["crankset"]
    if rng.random() < 0.5:  # and the battery is an assembly of its own in others
        tpl["motor kit"] = [("motor", 1), ("battery pack", 1), ("controller", 1), ("harness", 1)]
        tpl["battery pack"] = [("cell module", (4, 6)), ("battery management board", 1), ("battery casing", 1)]
    kids = {}
    products = ["bike", "ebike"] if big or rng.random() < 0.5 else ["bike"]
    if not big:
        products = ["bike", "ebike"]
    need = set(products)
    stack = list(products)
    while stack:
        a = stack.pop()
        for c, q in tpl[a]:
            if a not in ("bike", "ebike") and c not in ("rim", "hub", "chain") and rng.random() < 0.08:
                continue
            kids.setdefault(a, []).append((c, rng.randint(*q) if isinstance(q, tuple) else q))
            if c in tpl and c not in need:
                need.add(c)
                stack.append(c)
    raw = sorted({c for a in kids for c, _ in kids[a] if c not in tpl} | set(rng.sample(SPARE, 2 if not big else 3)))
    asm = [a for a in tpl if a in need]
    parts, pid, ids = [], 0, {}
    for a in asm:
        pid += 1
        ids[a] = pid
        parts.append((pid, "ASM-" + a.upper().replace(" ", "-"), a, "assembly", None, rng.choice([0, 0, 1, 2, 5])))
    for r in raw:
        pid += 1
        ids[r] = pid
        cost = RAW_COST.get(r, rng.choice([300, 700, 1500]))
        cost = int(cost * rng.choice([0.9, 1.0, 1.0, 1.1])) if big else cost
        parts.append((pid, "RAW-" + r.upper().replace(" ", "-"), r, "raw", cost, rng.choice([0, 3, 12, 40, 80, 150, 400])))
    if big:  # one raw part has no price yet
        victim = ids["cable set"] if "cable set" in ids else ids[raw[0]]
        parts = [p if p[0] != victim else p[:4] + (None,) + p[5:] for p in parts]
    bom = [(ids[a], ids[c], q) for a in kids for c, q in kids[a]]
    orders, oid = [], 0
    for i in range(7 if big else 4):
        oid += 1
        target = rng.choice(products + ["wheel"] if "wheel" in ids else products)
        orders.append((oid, ids[target], rng.randint(2, 15), f"2036-0{rng.randint(1, 6)}-{rng.randint(1, 28):02d}"))
    return {"parts": parts, "bom": bom, "orders": orders}


DOMAIN = K.Domain("bikeshop", "Ironwood Cycle Workshop: bill of materials", SCHEMA, DOC, gen)
S = K.Spec

EXPLODE = """WITH RECURSIVE x(top, part, qty) AS (
  SELECT parent_id, child_id, qty FROM bom
  UNION ALL SELECT x.top, b.child_id, x.qty * b.qty FROM x JOIN bom b ON b.parent_id = x.part
)"""

TOPS = "SELECT part_id FROM parts WHERE kind = 'assembly' AND part_id NOT IN (SELECT child_id FROM bom)"

SPECS = [
    S("parts-by-kind", 1, "How many parts of each kind are there, how many of them are in stock (stock above 0), and what is the total stock? Columns: kind, parts, in_stock, total_stock. Order by kind.",
      "SELECT kind, COUNT(*) AS parts, SUM(stock > 0) AS in_stock, SUM(stock) AS total_stock FROM parts GROUP BY kind ORDER BY kind;", ["kind", "parts", "in_stock", "total_stock"], ordered=True),
    S("component-counts", 2,
      "For every assembly: its sku, the number of direct components and the total number of component units in one unit of it (the sum of `qty` over its direct components). Order by units descending, then sku.",
      "SELECT p.sku, COUNT(*) AS components, SUM(b.qty) AS units FROM bom b JOIN parts p ON p.part_id = b.parent_id GROUP BY p.part_id ORDER BY units DESC, p.sku;",
      ["sku", "components", "units"], ordered=True),
    S("unused-parts", 2,
      "Which raw parts are not used in any assembly at all? sku and name, ordered by sku.",
      "SELECT sku, name FROM parts WHERE kind = 'raw' AND part_id NOT IN (SELECT child_id FROM bom) ORDER BY sku;", ["sku", "name"], ordered=True),
    S("raw-per-product", 4,
      "Explode every finished product (top-level assembly) down to raw parts: for each product and each raw part below it, the total number of units needed for ONE product (quantities multiply along each path and add up over paths). "
      "Columns: product sku, raw sku, quantity. Order by product sku, then raw sku.",
      f"""{EXPLODE}
SELECT t.sku AS product, r.sku AS raw, SUM(x.qty) AS qty FROM x JOIN parts r ON r.part_id = x.part AND r.kind = 'raw' JOIN parts t ON t.part_id = x.top
WHERE x.top IN ({TOPS}) GROUP BY x.top, x.part ORDER BY t.sku, r.sku;""",
      ["product", "raw", "qty"], ordered=True,
      wrong=("""SELECT t.sku, r.sku, SUM(b.qty) FROM bom b JOIN parts r ON r.part_id = b.child_id AND r.kind = 'raw' JOIN parts t ON t.part_id = b.parent_id WHERE b.parent_id IN (SELECT part_id FROM parts WHERE kind = 'assembly' AND part_id NOT IN (SELECT child_id FROM bom)) GROUP BY b.parent_id, b.child_id ORDER BY t.sku, r.sku;""",)),
    S("rolled-up-cost", 4,
      "Rolled-up cost of every assembly in euros with 2 decimals: the sum over all raw parts below it of the multiplied quantity times the unit cost. If any raw part below an assembly has no price (NULL) its cost is NULL. "
      "Columns: assembly sku, number of distinct raw parts below it, cost in euros. Order by cost descending (NULL last), then sku.",
      f"""{EXPLODE}
SELECT a.sku, COUNT(DISTINCT x.part) AS raw_parts,
       CASE WHEN SUM(r.unit_cost_cents IS NULL) > 0 THEN NULL ELSE ROUND(SUM(x.qty * r.unit_cost_cents) / 100.0, 2) END AS cost_eur
FROM parts a JOIN x ON x.top = a.part_id JOIN parts r ON r.part_id = x.part AND r.kind = 'raw' WHERE a.kind = 'assembly'
GROUP BY a.part_id ORDER BY cost_eur IS NULL, cost_eur DESC, a.sku;""",
      ["sku", "raw_parts", "cost_eur"], ordered=True,
      wrong=(f"""{EXPLODE}
SELECT a.sku, COUNT(DISTINCT x.part), ROUND(SUM(x.qty * COALESCE(r.unit_cost_cents, 0)) / 100.0, 2) AS c FROM parts a JOIN x ON x.top = a.part_id JOIN parts r ON r.part_id = x.part AND r.kind = 'raw' WHERE a.kind = 'assembly' GROUP BY a.part_id ORDER BY c DESC, a.sku;""",)),
    S("where-used", 3,
      "For every raw part: the number of distinct finished products (top-level assemblies) that contain it somewhere below. Raw parts that are in no product get 0. Columns: raw sku, products. Order by products descending, then sku.",
      f"""{EXPLODE}
SELECT r.sku, COUNT(DISTINCT x.top) AS products FROM parts r LEFT JOIN x ON x.part = r.part_id AND x.top IN ({TOPS}) WHERE r.kind = 'raw' GROUP BY r.part_id ORDER BY products DESC, r.sku;""",
      ["sku", "products"], ordered=True,
      wrong=("""SELECT r.sku, COUNT(DISTINCT b.parent_id) FROM parts r LEFT JOIN bom b ON b.child_id = r.part_id WHERE r.kind = 'raw' GROUP BY r.part_id ORDER BY 2 DESC, r.sku;""",)),
    S("bom-depth", 3,
      "How deep is each finished product's tree? Depth counts levels of parent-child links down to the deepest raw part: a product made only of raw parts has depth 1. Columns: product sku, depth. Deepest first, ties by sku.",
      """WITH RECURSIVE d(top, part, depth) AS (
  SELECT parent_id, child_id, 1 FROM bom WHERE parent_id IN (SELECT part_id FROM parts WHERE kind = 'assembly' AND part_id NOT IN (SELECT child_id FROM bom))
  UNION ALL SELECT d.top, b.child_id, d.depth + 1 FROM d JOIN bom b ON b.parent_id = d.part
)
SELECT p.sku AS product, MAX(d.depth) AS depth FROM d JOIN parts p ON p.part_id = d.top GROUP BY d.top ORDER BY depth DESC, p.sku;""",
      ["product", "depth"], ordered=True),
    S("shared-raw-parts", 3,
      "Raw parts that go into at least two different finished products: sku, name, and in how many products. Order by that number descending, then sku.",
      f"""{EXPLODE}
SELECT r.sku, r.name, COUNT(DISTINCT x.top) AS products FROM x JOIN parts r ON r.part_id = x.part AND r.kind = 'raw' WHERE x.top IN ({TOPS}) GROUP BY x.part HAVING COUNT(DISTINCT x.top) >= 2 ORDER BY products DESC, r.sku;""",
      ["sku", "name", "products"], ordered=True),
    S("order-shortages", 4,
      "Raw material shortages: explode every order (quantity times the exploded quantities per unit; ignore assembly stock) and add up the need per raw part over all orders. List the raw parts whose total need exceeds the stock: "
      "sku, needed, stock, missing. Order by missing descending, then sku.",
      f"""{EXPLODE}
, need AS (SELECT x.part, SUM(o.qty * x.qty) AS needed FROM orders o JOIN x ON x.top = o.part_id GROUP BY x.part)
SELECT r.sku, n.needed, r.stock, n.needed - r.stock AS missing FROM need n JOIN parts r ON r.part_id = n.part AND r.kind = 'raw' WHERE n.needed > r.stock ORDER BY missing DESC, r.sku;""",
      ["sku", "needed", "stock", "missing"], ordered=True, allow_empty=True,
      wrong=("""SELECT r.sku, SUM(o.qty * b.qty), r.stock, SUM(o.qty * b.qty) - r.stock AS m FROM orders o JOIN bom b ON b.parent_id = o.part_id JOIN parts r ON r.part_id = b.child_id AND r.kind = 'raw' GROUP BY r.part_id HAVING SUM(o.qty * b.qty) > r.stock ORDER BY m DESC, r.sku;""",)),
    S("first-order-to-stall", 5,
      "Which order first runs a raw part dry? Serve the orders in due-date order (ties by order id) and let each take its exploded raw requirements from the stock. "
      "For every raw part whose cumulative need over the orders exceeds its stock at some point, report the first order at which that happens: raw sku, order id, due date, cumulative need after that order, stock. "
      "Order by due date, then sku.",
      f"""{EXPLODE}
, need AS (SELECT o.order_id, o.due_on, x.part, SUM(o.qty * x.qty) AS n FROM orders o JOIN x ON x.top = o.part_id GROUP BY o.order_id, x.part),
cum AS (SELECT part, order_id, due_on, SUM(n) OVER (PARTITION BY part ORDER BY due_on, order_id) AS cumulative FROM need),
hit AS (SELECT c.*, ROW_NUMBER() OVER (PARTITION BY c.part ORDER BY c.due_on, c.order_id) AS rn FROM cum c JOIN parts p ON p.part_id = c.part AND p.kind = 'raw' WHERE c.cumulative > p.stock)
SELECT p.sku, h.order_id, h.due_on, h.cumulative, p.stock FROM hit h JOIN parts p ON p.part_id = h.part WHERE h.rn = 1 ORDER BY h.due_on, p.sku;""",
      ["sku", "order_id", "due_on", "cumulative", "stock"], ordered=True, allow_empty=True,
      wrong=(f"""{EXPLODE}
, need AS (SELECT o.order_id, o.due_on, x.part, SUM(o.qty * x.qty) AS n FROM orders o JOIN x ON x.top = o.part_id GROUP BY o.order_id, x.part)
SELECT p.sku, n.order_id, n.due_on, n.n, p.stock FROM need n JOIN parts p ON p.part_id = n.part AND p.kind = 'raw' WHERE n.n > p.stock AND NOT EXISTS (SELECT 1 FROM need m WHERE m.part = n.part AND m.n > p.stock AND (m.due_on < n.due_on OR (m.due_on = n.due_on AND m.order_id < n.order_id))) ORDER BY n.due_on, p.sku;""",)),
    S("priciest-component-line", 5,
      "For each finished product, which direct component line costs the most? A line costs `qty x cost of the child` where the child's cost is its rolled-up cost (raw: its unit cost; assembly: the sum over its raw parts). "
      "Lines whose child cost is NULL are skipped (unknown price). Report product sku, child sku and the line cost in euros (2 decimals); ties go to the lower child sku. Order by product sku.",
      f"""{EXPLODE}
, cost AS (
  SELECT part_id AS pid, unit_cost_cents AS c FROM parts WHERE kind = 'raw'
  UNION ALL
  SELECT x.top, CASE WHEN SUM(r.unit_cost_cents IS NULL) > 0 THEN NULL ELSE SUM(x.qty * r.unit_cost_cents) END FROM x JOIN parts r ON r.part_id = x.part AND r.kind = 'raw' GROUP BY x.top
), line AS (
  SELECT b.parent_id, b.child_id, b.qty * c.c AS lc, ROW_NUMBER() OVER (PARTITION BY b.parent_id ORDER BY b.qty * c.c DESC, ch.sku) AS rn
  FROM bom b JOIN cost c ON c.pid = b.child_id JOIN parts ch ON ch.part_id = b.child_id WHERE c.c IS NOT NULL
)
SELECT p.sku AS product, ch.sku AS child, ROUND(l.lc / 100.0, 2) AS line_eur FROM line l JOIN parts p ON p.part_id = l.parent_id JOIN parts ch ON ch.part_id = l.child_id
WHERE l.rn = 1 AND l.parent_id IN ({TOPS}) ORDER BY p.sku;""",
      ["product", "child", "line_eur"], ordered=True, places=2,
      wrong=("""SELECT p.sku, ch.sku, ROUND(MAX(b.qty * ch.unit_cost_cents) / 100.0, 2) FROM bom b JOIN parts p ON p.part_id = b.parent_id JOIN parts ch ON ch.part_id = b.child_id WHERE ch.kind = 'raw' AND b.parent_id IN (SELECT part_id FROM parts WHERE kind = 'assembly' AND part_id NOT IN (SELECT child_id FROM bom)) GROUP BY b.parent_id ORDER BY p.sku;""",)),
    S("fix-spokes-per-bike", 3,
      "The explosion in `query.sql` forgets to multiply the quantities down the tree (it just adds the `qty` of every link). Fix it: for each finished product (top-level assembly), the raw parts with total units for ONE product. "
      "Columns: product sku, raw sku, quantity. Order by product sku, then raw sku.",
      ref=f"""{EXPLODE}
SELECT t.sku AS product, r.sku AS raw, SUM(x.qty) AS qty FROM x JOIN parts r ON r.part_id = x.part AND r.kind = 'raw' JOIN parts t ON t.part_id = x.top WHERE x.top IN ({TOPS}) GROUP BY x.top, x.part ORDER BY t.sku, r.sku;""",
      cols=["product", "raw", "qty"], ordered=True, show=False,
      buggy=f"""WITH RECURSIVE x(top, part, qty) AS (
  SELECT parent_id, child_id, qty FROM bom
  UNION ALL SELECT x.top, b.child_id, x.qty + b.qty FROM x JOIN bom b ON b.parent_id = x.part
)
SELECT t.sku AS product, r.sku AS raw, SUM(x.qty) AS qty FROM x JOIN parts r ON r.part_id = x.part AND r.kind = 'raw' JOIN parts t ON t.part_id = x.top
WHERE x.top IN ({TOPS}) GROUP BY x.top, x.part ORDER BY t.sku, r.sku;"""),
]


@family("data-bike-workshop", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL on a bicycle workshop's bill of materials: recursive explosion with multiplied quantities, cost rollups with unknown prices, where-used, shortages by due date")
def bike_workshop(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
