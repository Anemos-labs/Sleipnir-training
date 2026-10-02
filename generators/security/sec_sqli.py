"""Security family: SQL injection in sqlite3 code (values, identifiers, LIKE, ORDER BY, stacked statements, second order)."""
from fx import dd, family

from . import _sec

P = _sec.PY_PRELUDE + "import sqlite3\n\n\n"


def readme(title, body):
    return f"# {title}\n\n{body.strip()}\n"


def vis_test(mod, setup, body):
    body = "".join("    " + line if line.strip() else line for line in body.splitlines(True))
    return {f"tests/test_{mod}_basic.py": _sec.PY_PRELUDE + "import sqlite3\n\nimport " + mod + " as m\n\n\n" + setup + "\n\nclass Basic(unittest.TestCase):\n" + body + "\n\nif __name__ == \"__main__\":\n    unittest.main()\n"}


SC = []

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="user-lookup", d=1, product="the customer portal", func="find_user", cwe="CWE-89",
    finding="`find_user` builds its SQL by pasting the name into a string, so `' OR '1'='1` returns every customer and a name with an apostrophe (`O'Brien`) breaks the query.",
    start={
        "customers.py": dd('''
            """Customer lookup."""


            def find_user(conn, name):
                """Rows (id, name, email) of the customers whose name is exactly `name`, ordered by id."""
                sql = "SELECT id, name, email FROM customers WHERE name = '%s' ORDER BY id" % name
                return conn.execute(sql).fetchall()
        '''),
        "README.md": readme("customers", "`find_user(conn, name)` returns the `(id, name, email)` rows of customers whose name equals `name` exactly (case-sensitive), ordered by id. Names may contain quotes, percent signs and SQL keywords."),
    },
    solution={"customers.py": dd('''
        """Customer lookup."""


        def find_user(conn, name):
            """Rows (id, name, email) of the customers whose name is exactly `name`, ordered by id."""
            return conn.execute("SELECT id, name, email FROM customers WHERE name = ? ORDER BY id", (name,)).fetchall()
    ''')},
    visible=vis_test("customers", dd('''
        def make():
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
            conn.executemany("INSERT INTO customers (name, email) VALUES (?, ?)", [("Ann", "ann@x.io"), ("Bob", "bob@x.io")])
            return conn
    '''), dd('''
            def test_find(self):
                self.assertEqual(m.find_user(make(), "Ann"), [(1, "Ann", "ann@x.io")])
    ''')),
    hidden={"tests/test_customers_security.py": P + dd('''
        import customers as m


        def make():
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
            conn.executemany("INSERT INTO customers (name, email) VALUES (?, ?)", [("Ann", "ann@x.io"), ("Bob", "bob@x.io"), ("O'Brien", "ob@x.io"), ("100% Real", "r@x.io"), ("x' OR '1'='1", "evil@x.io"), ("Ann", "ann2@x.io")])
            return conn


        class CustomerTest(unittest.TestCase):
            def test_normal(self):
                conn = make()
                self.assertEqual(m.find_user(conn, "Ann"), [(1, "Ann", "ann@x.io"), (6, "Ann", "ann2@x.io")])
                self.assertEqual(m.find_user(conn, "O'Brien"), [(3, "O'Brien", "ob@x.io")])
                self.assertEqual(m.find_user(conn, "100% Real"), [(4, "100% Real", "r@x.io")])
                self.assertEqual(m.find_user(conn, "nobody"), [])
                self.assertEqual(m.find_user(conn, "ann"), [])

            def test_injection(self):
                conn = make()
                self.assertEqual(m.find_user(conn, "x' OR '1'='1"), [(5, "x' OR '1'='1", "evil@x.io")])
                for payload in ["' OR '1'='1", "' OR 1=1 --", "Ann' --", "Ann'/*", "' UNION SELECT 1, sqlite_version(), 'x' --", "'; DROP TABLE customers; --"]:
                    res = attempt(m.find_user, conn, payload)
                    self.assertEqual(res or [], [], payload)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 6)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="order-id", d=2, product="the order tracker", func="get_order", cwe="CWE-89",
    finding="`get_order` formats the order id straight into the statement with an f-string; ids arrive as strings from the URL, so `1 OR 1=1` returns every order and `0 UNION SELECT ...` reads other tables.",
    start={
        "orders.py": dd('''
            """Order tracking."""


            def get_order(conn, order_id):
                """The row (id, customer, total_cents, status) of the order with this id, or None. `order_id` comes from a URL and may be an int or a decimal string."""
                row = conn.execute(f"SELECT id, customer, total_cents, status FROM orders WHERE id = {order_id}").fetchone()
                return row


            def orders_for(conn, customer, status="open"):
                """Ids of the orders of `customer` with the given status, ascending."""
                rows = conn.execute("SELECT id FROM orders WHERE customer = ? AND status = ? ORDER BY id", (customer, status)).fetchall()
                return [r[0] for r in rows]
        '''),
        "README.md": readme("orders", "`get_order(conn, order_id)` returns the order row or `None`. `order_id` may be an `int` or a string of decimal digits (`\"7\"`); anything that is not a plain integer is invalid and must raise `ValueError`. `orders_for(conn, customer, status)` lists order ids."),
    },
    solution={"orders.py": dd('''
        """Order tracking."""


        def get_order(conn, order_id):
            """The row (id, customer, total_cents, status) of the order with this id, or None. `order_id` comes from a URL and may be an int or a decimal string."""
            if isinstance(order_id, bool):
                raise ValueError("bad order id")
            if isinstance(order_id, str):
                if not order_id.isascii() or not order_id.isdigit():
                    raise ValueError("bad order id")
                order_id = int(order_id)
            elif not isinstance(order_id, int):
                raise ValueError("bad order id")
            return conn.execute("SELECT id, customer, total_cents, status FROM orders WHERE id = ?", (order_id,)).fetchone()


        def orders_for(conn, customer, status="open"):
            """Ids of the orders of `customer` with the given status, ascending."""
            rows = conn.execute("SELECT id FROM orders WHERE customer = ? AND status = ? ORDER BY id", (customer, status)).fetchall()
            return [r[0] for r in rows]
    ''')},
    hidden={"tests/test_orders_security.py": P + dd('''
        import orders as m


        def make():
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer TEXT, total_cents INTEGER, status TEXT)")
            conn.execute("CREATE TABLE secrets (k TEXT, v TEXT)")
            conn.execute("INSERT INTO secrets VALUES ('api', 'TOP-SECRET')")
            conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", [(1, "ann", 500, "open"), (2, "bob", 900, "shipped"), (3, "ann", 150, "open"), (7, "cy", 1, "open")])
            return conn


        class OrderTest(unittest.TestCase):
            def test_normal(self):
                conn = make()
                self.assertEqual(m.get_order(conn, 1), (1, "ann", 500, "open"))
                self.assertEqual(m.get_order(conn, "7"), (7, "cy", 1, "open"))
                self.assertIsNone(m.get_order(conn, 99))
                self.assertIsNone(m.get_order(conn, "0"))
                self.assertEqual(m.orders_for(conn, "ann"), [1, 3])
                self.assertEqual(m.orders_for(conn, "bob", "shipped"), [2])

            def test_injection(self):
                conn = make()
                for bad in ["1 OR 1=1", "1; DROP TABLE orders", "0 UNION SELECT 1, v, 3, 'x' FROM secrets", "1 --", "-1 OR id > 0", "1.0", "", " ", "1 ", "\\u0661", "(SELECT 1)", None, 1.5, [1]]:
                    with self.assertRaises(ValueError, msg=repr(bad)):
                        m.get_order(conn, bad)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 4)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="product-search", d=2, product="the shop search", func="search_products", cwe="CWE-89",
    finding="`search_products` concatenates the search term into a `LIKE '%...%'` pattern inside the SQL text (so quotes break out of the string), and `%`/`_` in the term act as wildcards instead of ordinary characters.",
    start={
        "shop.py": dd('''
            """Product search."""


            def search_products(conn, term, limit=20):
                """Names of the products whose name contains `term` (case-insensitive), in plain byte order of the name, at most `limit`."""
                sql = "SELECT name FROM products WHERE name LIKE '%" + term + "%' ORDER BY name LIMIT " + str(int(limit))
                return [r[0] for r in conn.execute(sql).fetchall()]
        '''),
        "README.md": readme("shop", "`search_products(conn, term, limit=20)` returns the names (sorted in plain byte order, e.g. `Z` before `a`) of products whose name contains `term` (the match ignores letter case). The term is taken **literally**: `%` and `_` are ordinary characters (searching `50%` finds `Rope 50% off`, not everything starting with 50). `limit` is an integer."),
    },
    solution={"shop.py": dd('''
        """Product search."""


        def search_products(conn, term, limit=20):
            """Names of the products whose name contains `term` (case-insensitive), in plain byte order of the name, at most `limit`."""
            escaped = term.replace("\\\\", "\\\\\\\\").replace("%", "\\\\%").replace("_", "\\\\_")
            rows = conn.execute("SELECT name FROM products WHERE name LIKE ? ESCAPE '\\\\' ORDER BY name LIMIT ?", ("%" + escaped + "%", int(limit))).fetchall()
            return [r[0] for r in rows]
    ''')},
    hidden={"tests/test_shop_security.py": P + dd('''
        import shop as m

        NAMES = ["Rope 50% off", "Rope 20m", "snake_case mug", "snakeXcase mug", "Back\\\\slash tee", "Tom's hat", "Garden hose", "garden gnome", "100% cotton", "A_B", "AxB"]


        def make():
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("CREATE TABLE secrets (v TEXT)")
            conn.execute("INSERT INTO secrets VALUES ('TOP-SECRET')")
            conn.executemany("INSERT INTO products (name) VALUES (?)", [(n,) for n in NAMES])
            return conn


        class ShopTest(unittest.TestCase):
            def test_normal(self):
                conn = make()
                self.assertEqual(m.search_products(conn, "rope"), ["Rope 20m", "Rope 50% off"])
                self.assertEqual(m.search_products(conn, "GARDEN"), ["Garden hose", "garden gnome"])
                self.assertEqual(m.search_products(conn, "tom's"), ["Tom's hat"])
                self.assertEqual(m.search_products(conn, "", limit=3), sorted(NAMES)[:3])
                self.assertEqual(m.search_products(conn, "zzz"), [])

            def test_literal_wildcards(self):
                conn = make()
                self.assertEqual(m.search_products(conn, "%"), ["100% cotton", "Rope 50% off"])
                self.assertEqual(m.search_products(conn, "50%"), ["Rope 50% off"])
                self.assertEqual(m.search_products(conn, "_"), ["A_B", "snake_case mug"])
                self.assertEqual(m.search_products(conn, "a_b"), ["A_B"])
                self.assertEqual(m.search_products(conn, "\\\\"), ["Back\\\\slash tee"])

            def test_injection(self):
                conn = make()
                for payload in ["' OR '1'='1", "%' OR 1=1 --", "x' UNION SELECT v FROM secrets --", "'; DROP TABLE products; --", "' AND 1=2 UNION SELECT v FROM secrets --"]:
                    res = attempt(m.search_products, conn, payload) or []
                    self.assertEqual(res, [], payload)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM products").fetchone()[0], len(NAMES))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="task-sorting", d=3, product="the task board API", func="list_tasks", cwe="CWE-89",
    finding="`list_tasks` pastes the `sort_by` and `direction` query parameters into the ORDER BY clause; they cannot be bound as parameters, and an expression such as `(CASE WHEN (SELECT ...) THEN id ELSE -id END)` turns the ordering into a data-leaking oracle.",
    start={
        "board.py": dd('''
            """Task board queries."""


            def list_tasks(conn, sort_by="id", direction="asc", status=None):
                """Rows (id, title, priority, due) of the tasks, optionally only those with `status`, sorted by the column `sort_by` in `direction`."""
                sql = "SELECT id, title, priority, due FROM tasks"
                params = []
                if status is not None:
                    sql += " WHERE status = ?"
                    params.append(status)
                sql += " ORDER BY " + sort_by + " " + direction + ", id"
                return conn.execute(sql, params).fetchall()
        '''),
        "README.md": readme("board", "`list_tasks(conn, sort_by, direction, status)`: `sort_by` is one of `id`, `title`, `priority`, `due`; `direction` is `asc` or `desc` (any letter case); ties are broken by `id` ascending. Anything else raises `ValueError`. `status` filters when given."),
    },
    solution={"board.py": dd('''
        """Task board queries."""

        COLUMNS = {"id", "title", "priority", "due"}


        def list_tasks(conn, sort_by="id", direction="asc", status=None):
            """Rows (id, title, priority, due) of the tasks, optionally only those with `status`, sorted by the column `sort_by` in `direction`."""
            if not isinstance(sort_by, str) or sort_by not in COLUMNS:
                raise ValueError("bad sort column")
            if not isinstance(direction, str) or direction.lower() not in ("asc", "desc"):
                raise ValueError("bad sort direction")
            sql = "SELECT id, title, priority, due FROM tasks"
            params = []
            if status is not None:
                sql += " WHERE status = ?"
                params.append(status)
            sql += " ORDER BY " + sort_by + " " + direction.lower() + ", id"
            return conn.execute(sql, params).fetchall()
    ''')},
    hidden={"tests/test_board_security.py": P + dd('''
        import board as m


        def make():
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, priority INTEGER, due TEXT, status TEXT)")
            conn.execute("CREATE TABLE secrets (v TEXT)")
            conn.execute("INSERT INTO secrets VALUES ('TOP-SECRET')")
            conn.executemany("INSERT INTO tasks VALUES (?, ?, ?, ?, ?)", [(1, "write", 2, "2024-05-02", "open"), (2, "test", 1, "2024-05-01", "open"), (3, "ship", 2, "2024-04-30", "done"), (4, "alpha", 1, "2024-05-02", "open")])
            return conn


        class BoardTest(unittest.TestCase):
            def test_normal(self):
                conn = make()
                self.assertEqual([r[0] for r in m.list_tasks(conn)], [1, 2, 3, 4])
                self.assertEqual([r[0] for r in m.list_tasks(conn, "priority", "desc")], [1, 3, 2, 4])
                self.assertEqual([r[0] for r in m.list_tasks(conn, "title", "ASC")], [4, 3, 2, 1])
                self.assertEqual([r[0] for r in m.list_tasks(conn, "due", "Desc", status="open")], [1, 4, 2])
                self.assertEqual(m.list_tasks(conn, "id", "asc", status="none"), [])

            def test_rejected(self):
                conn = make()
                bad_cols = ["(SELECT 1)", "id; DROP TABLE tasks", "CASE WHEN (SELECT substr(v,1,1) FROM secrets)='T' THEN id ELSE -id END", "status", "1", "id,priority", "ID", "title--", "", None, 3]
                for col in bad_cols:
                    with self.assertRaises(ValueError, msg=repr(col)):
                        m.list_tasks(conn, col)
                for d in ["asc; DROP TABLE tasks", "desc, (SELECT 1)", "up", "", None, "asc--"]:
                    with self.assertRaises(ValueError, msg=repr(d)):
                        m.list_tasks(conn, "id", d)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 4)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="id-list", d=3, product="the bulk export", func="get_users", cwe="CWE-89",
    finding="`get_users` joins the ids it is given into an `IN (...)` list as text; ids come from a query string, so one element such as `2) OR (1=1` returns the whole table, and an empty list produces invalid SQL on some databases.",
    start={
        "bulk.py": dd('''
            """Bulk user export."""


            def get_users(conn, ids):
                """Rows (id, name) of the users with these ids (ids may be ints or decimal strings), ordered by id. An empty list gives an empty result."""
                if not ids:
                    return []
                sql = "SELECT id, name FROM users WHERE id IN (" + ",".join(str(i) for i in ids) + ") ORDER BY id"
                return conn.execute(sql).fetchall()
        '''),
        "README.md": readme("bulk", "`get_users(conn, ids)` returns `(id, name)` for the listed ids (ints or decimal strings such as `\"12\"`), ordered by id; unknown ids are ignored, an empty list gives `[]`, a very long list (several thousand ids) must work. Any element that is not an integer or a plain decimal digit string raises `ValueError` and nothing is queried."),
    },
    solution={"bulk.py": dd('''
        """Bulk user export."""


        def _clean(i):
            if isinstance(i, bool):
                raise ValueError("bad id")
            if isinstance(i, int):
                return i
            if isinstance(i, str) and i.isascii() and i.isdigit():
                return int(i)
            raise ValueError("bad id")


        def get_users(conn, ids):
            """Rows (id, name) of the users with these ids (ids may be ints or decimal strings), ordered by id. An empty list gives an empty result."""
            clean = sorted({_clean(i) for i in ids})
            out = []
            for start in range(0, len(clean), 500):
                chunk = clean[start:start + 500]
                marks = ",".join("?" * len(chunk))
                out.extend(conn.execute("SELECT id, name FROM users WHERE id IN (" + marks + ")", chunk).fetchall())
            return sorted(out)
    ''')},
    hidden={"tests/test_bulk_security.py": P + dd('''
        import bulk as m


        def make():
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
            conn.executemany("INSERT INTO users VALUES (?, ?)", [(i, "u%d" % i) for i in range(1, 3001)])
            return conn


        class BulkTest(unittest.TestCase):
            def test_normal(self):
                conn = make()
                self.assertEqual(m.get_users(conn, [3, "1", 2]), [(1, "u1"), (2, "u2"), (3, "u3")])
                self.assertEqual(m.get_users(conn, []), [])
                self.assertEqual(m.get_users(conn, [5000, 7]), [(7, "u7")])
                self.assertEqual(m.get_users(conn, [4, 4, "4"]), [(4, "u4")])
                big = m.get_users(conn, list(range(1, 3001)))
                self.assertEqual(len(big), 3000)
                self.assertEqual(big[-1], (3000, "u3000"))

            def test_injection(self):
                conn = make()
                for bad in [[1, "2) OR (1=1"], ["1 OR 1=1"], [1, "2); DROP TABLE users; --"], ["", 1], [1.5], [None], ["-1 UNION SELECT 1, 'x'"], ["١"], [True]]:
                    with self.assertRaises(ValueError, msg=repr(bad)):
                        m.get_users(conn, bad)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 3000)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="table-export", d=3, product="the admin export tool", func="export_table", cwe="CWE-89",
    finding="`export_table` and `column_names` insert the table name from the request into the statement; the name is only checked for being non-empty, so `sqlite_master`, `secrets` or `orders UNION SELECT ...` can be exported.",
    start={
        "exporter.py": dd('''
            """CSV export of selected tables."""
            import csv
            import io

            EXPORTABLE = ("customers", "orders", "products")


            def column_names(conn, table):
                """Column names of `table`."""
                if not table:
                    raise ValueError("no table")
                return [r[1] for r in conn.execute("PRAGMA table_info(" + table + ")")]


            def export_table(conn, table):
                """CSV text (header line, then rows ordered by the first column) of one of the exportable tables."""
                if not table:
                    raise ValueError("no table")
                cols = column_names(conn, table)
                out = io.StringIO()
                w = csv.writer(out, lineterminator="\\n")
                w.writerow(cols)
                for row in conn.execute("SELECT * FROM " + table + " ORDER BY 1"):
                    w.writerow(row)
                return out.getvalue()
        '''),
        "README.md": readme("exporter", "Only the tables `customers`, `orders` and `products` can be exported (exact names); any other table name - including internal tables, other-case spellings, quoting tricks or anything that is not a bare identifier - raises `ValueError`. `export_table` returns CSV text (`\\n` line ends), `column_names` the column list."),
    },
    solution={"exporter.py": dd('''
        """CSV export of selected tables."""
        import csv
        import io

        EXPORTABLE = ("customers", "orders", "products")


        def _check(table):
            if not isinstance(table, str) or table not in EXPORTABLE:
                raise ValueError("table is not exportable")
            return table


        def column_names(conn, table):
            """Column names of `table`."""
            _check(table)
            return [r[1] for r in conn.execute("PRAGMA table_info(" + table + ")")]


        def export_table(conn, table):
            """CSV text (header line, then rows ordered by the first column) of one of the exportable tables."""
            _check(table)
            cols = column_names(conn, table)
            out = io.StringIO()
            w = csv.writer(out, lineterminator="\\n")
            w.writerow(cols)
            for row in conn.execute("SELECT * FROM " + table + " ORDER BY 1"):
                w.writerow(row)
            return out.getvalue()
    ''')},
    hidden={"tests/test_exporter_security.py": P + dd('''
        import exporter as m


        def make():
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, total INTEGER)")
            conn.execute("CREATE TABLE products (sku TEXT PRIMARY KEY, title TEXT)")
            conn.execute("CREATE TABLE secrets (k TEXT, v TEXT)")
            conn.execute("INSERT INTO secrets VALUES ('api', 'TOP-SECRET')")
            conn.executemany("INSERT INTO customers VALUES (?, ?)", [(2, "Bo, Jr."), (1, "Ann")])
            conn.execute("INSERT INTO orders VALUES (10, 1, 500)")
            conn.execute("INSERT INTO products VALUES ('A1', 'Pen \\"X\\"')")
            return conn


        class ExportTest(unittest.TestCase):
            def test_normal(self):
                conn = make()
                self.assertEqual(m.export_table(conn, "customers"), 'id,name\\n1,Ann\\n2,"Bo, Jr."\\n')
                self.assertEqual(m.export_table(conn, "orders"), "id,customer_id,total\\n10,1,500\\n")
                self.assertEqual(m.export_table(conn, "products"), 'sku,title\\nA1,"Pen ""X"""\\n')
                self.assertEqual(m.column_names(conn, "orders"), ["id", "customer_id", "total"])

            def test_rejected(self):
                conn = make()
                for bad in ["secrets", "sqlite_master", "Customers", "customers ", "customers; DROP TABLE secrets", "orders UNION SELECT k, v, 1 FROM secrets", '"secrets"', "main.secrets", "", None, "customers--", "(SELECT 1)"]:
                    with self.assertRaises(ValueError, msg=repr(bad)):
                        m.export_table(conn, bad)
                    with self.assertRaises(ValueError, msg=repr(bad)):
                        m.column_names(conn, bad)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="second-order", d=3, product="the forum", func="posts_by_author", cwe="CWE-89",
    finding="user names are stored safely at registration, but `posts_by_author` later reads a name from the users table and pastes it into a new query; a user who registered as `x' OR '1'='1` makes the summary list everybody's posts (second-order injection).",
    start={
        "forum.py": dd('''
            """A tiny forum."""


            def register(conn, name):
                """Create a user and return its id. Names must be unique and may contain any characters."""
                cur = conn.execute("INSERT INTO users (name) VALUES (?)", (name,))
                return cur.lastrowid


            def post(conn, user_id, text):
                conn.execute("INSERT INTO posts (author, body) VALUES ((SELECT name FROM users WHERE id = ?), ?)", (user_id, text))


            def posts_by_author(conn, user_id):
                """Bodies of the posts written by this user, in the order they were posted."""
                name = conn.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()[0]
                rows = conn.execute("SELECT body FROM posts WHERE author = '%s' ORDER BY id" % name).fetchall()
                return [r[0] for r in rows]
        '''),
        "README.md": readme("forum", "`register(conn, name)` creates a user, `post(conn, user_id, text)` stores a post under the user's name, `posts_by_author(conn, user_id)` returns the bodies of that user's own posts in order. Names may contain any characters (quotes included); two users can never see each other's posts."),
    },
    solution={"forum.py": dd('''
        """A tiny forum."""


        def register(conn, name):
            """Create a user and return its id. Names must be unique and may contain any characters."""
            cur = conn.execute("INSERT INTO users (name) VALUES (?)", (name,))
            return cur.lastrowid


        def post(conn, user_id, text):
            conn.execute("INSERT INTO posts (author, body) VALUES ((SELECT name FROM users WHERE id = ?), ?)", (user_id, text))


        def posts_by_author(conn, user_id):
            """Bodies of the posts written by this user, in the order they were posted."""
            name = conn.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()[0]
            rows = conn.execute("SELECT body FROM posts WHERE author = ? ORDER BY id", (name,)).fetchall()
            return [r[0] for r in rows]
    ''')},
    hidden={"tests/test_forum_security.py": P + dd('''
        import forum as m


        def make():
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT UNIQUE)")
            conn.execute("CREATE TABLE posts (id INTEGER PRIMARY KEY, author TEXT, body TEXT)")
            return conn


        class ForumTest(unittest.TestCase):
            def test_normal(self):
                conn = make()
                a, b = m.register(conn, "ann"), m.register(conn, "o'neil")
                m.post(conn, a, "hello")
                m.post(conn, b, "it's me")
                m.post(conn, a, "again")
                self.assertEqual(m.posts_by_author(conn, a), ["hello", "again"])
                self.assertEqual(m.posts_by_author(conn, b), ["it's me"])

            def test_second_order(self):
                conn = make()
                a = m.register(conn, "ann")
                evil = m.register(conn, "x' OR '1'='1")
                evil2 = m.register(conn, "zed' UNION SELECT name FROM users --")
                evil3 = m.register(conn, "q'; DELETE FROM posts; --")
                m.post(conn, a, "ann's secret")
                m.post(conn, evil, "evil post")
                m.post(conn, evil2, "evil2 post")
                m.post(conn, evil3, "evil3 post")
                self.assertEqual(m.posts_by_author(conn, evil), ["evil post"])
                self.assertEqual(m.posts_by_author(conn, evil2), ["evil2 post"])
                self.assertEqual(m.posts_by_author(conn, evil3), ["evil3 post"])
                self.assertEqual(m.posts_by_author(conn, a), ["ann's secret"])
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0], 4)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="comment-script", d=4, product="the blog engine", func="add_comment", cwe="CWE-89",
    finding="`add_comment` builds an INSERT with string formatting and runs it with `executescript`, which executes stacked statements: a comment such as `x'); DROP TABLE comments; --` destroys the table, and ordinary comments containing apostrophes fail.",
    start={
        "comments.py": dd('''
            """Comments of the blog engine."""


            def add_comment(conn, post_id, author, body):
                """Store a comment (any text is allowed in author and body) and return how many comments the post has now."""
                conn.executescript(
                    "INSERT INTO comments (post_id, author, body) VALUES (%d, '%s', '%s');" % (int(post_id), author, body)
                )
                return conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = %d" % int(post_id)).fetchone()[0]


            def comments_of(conn, post_id):
                """(author, body) pairs of the post's comments, oldest first."""
                return conn.execute("SELECT author, body FROM comments WHERE post_id = ? ORDER BY id", (int(post_id),)).fetchall()


            def rename_author(conn, old, new):
                """Change the author name on all comments; returns the number of comments changed."""
                conn.executescript("UPDATE comments SET author = '%s' WHERE author = '%s';" % (new, old))
                return conn.execute("SELECT COUNT(*) FROM comments WHERE author = ?", (new,)).fetchone()[0]
        '''),
        "README.md": readme("comments", "`add_comment`, `comments_of` and `rename_author` store and read comments. Authors and bodies are arbitrary text (quotes, semicolons, SQL keywords, comment markers) and must be stored exactly as given. `post_id` must be an integer (or digit string); otherwise `ValueError`."),
    },
    solution={"comments.py": dd('''
        """Comments of the blog engine."""


        def _pid(post_id):
            if isinstance(post_id, bool) or not isinstance(post_id, (int, str)):
                raise ValueError("bad post id")
            return int(post_id)


        def add_comment(conn, post_id, author, body):
            """Store a comment (any text is allowed in author and body) and return how many comments the post has now."""
            pid = _pid(post_id)
            conn.execute("INSERT INTO comments (post_id, author, body) VALUES (?, ?, ?)", (pid, author, body))
            return conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", (pid,)).fetchone()[0]


        def comments_of(conn, post_id):
            """(author, body) pairs of the post's comments, oldest first."""
            return conn.execute("SELECT author, body FROM comments WHERE post_id = ? ORDER BY id", (_pid(post_id),)).fetchall()


        def rename_author(conn, old, new):
            """Change the author name on all comments; returns the number of comments changed."""
            conn.execute("UPDATE comments SET author = ? WHERE author = ?", (new, old))
            return conn.execute("SELECT COUNT(*) FROM comments WHERE author = ?", (new,)).fetchone()[0]
    ''')},
    hidden={"tests/test_comments_security.py": P + dd('''
        import comments as m


        def make():
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE comments (id INTEGER PRIMARY KEY, post_id INTEGER, author TEXT, body TEXT)")
            return conn


        class CommentTest(unittest.TestCase):
            def test_normal(self):
                conn = make()
                self.assertEqual(m.add_comment(conn, 1, "ann", "It's great!"), 1)
                self.assertEqual(m.add_comment(conn, "1", "o'neil", 'say "hi"; DROP -- nope'), 2)
                self.assertEqual(m.add_comment(conn, 2, "bob", ""), 1)
                self.assertEqual(m.comments_of(conn, 1), [("ann", "It's great!"), ("o'neil", 'say "hi"; DROP -- nope')])
                self.assertEqual(m.rename_author(conn, "ann", "Ann M."), 1)
                self.assertEqual(m.comments_of(conn, "1")[0], ("Ann M.", "It's great!"))

            def test_injection(self):
                conn = make()
                m.add_comment(conn, 1, "ann", "keep me")
                payloads = [("x'); DROP TABLE comments; --", "b"), ("a", "x'); DELETE FROM comments; --"), ("a", "'); UPDATE comments SET body='pwn'; --"), ("a'||(SELECT 1)||'", "b")]
                for author, body in payloads:
                    m.add_comment(conn, 1, author, body)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0], 5)
                rows = m.comments_of(conn, 1)
                self.assertEqual(rows[0], ("ann", "keep me"))
                self.assertEqual(rows[1:], payloads)
                m.rename_author(conn, "ann", "x'; DELETE FROM comments; --")
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0], 5)
                self.assertEqual(m.comments_of(conn, 1)[0][0], "x'; DELETE FROM comments; --")
                for bad in ["1; DROP TABLE comments", "1 OR 1=1", None, 1.5, "x"]:
                    with self.assertRaises(ValueError, msg=repr(bad)):
                        m.comments_of(conn, bad)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="filter-builder", d=4, product="the property search", func="search", cwe="CWE-89",
    finding="`search` builds its WHERE clause from the filter dict it receives: the *keys* (column names) are pasted into the SQL as well as the values, so a request with the key `1=1 OR city` (or a value containing quotes) changes the query.",
    start={
        "listings.py": dd('''
            """Property search with optional filters."""

            FIELDS = ("city", "status", "min_price", "max_price", "bedrooms")


            def search(conn, filters, limit=50):
                """Rows (id, city, price, bedrooms) of the listings that match all `filters`, cheapest first (ties by id), at most `limit` rows.

                Filter keys: city (equals), status (equals), min_price / max_price (price bounds, inclusive), bedrooms (equals)."""
                clauses = []
                for key, value in filters.items():
                    if key == "min_price":
                        clauses.append("price >= %s" % value)
                    elif key == "max_price":
                        clauses.append("price <= %s" % value)
                    else:
                        clauses.append("%s = '%s'" % (key, value))
                sql = "SELECT id, city, price, bedrooms FROM listings"
                if clauses:
                    sql += " WHERE " + " AND ".join(clauses)
                sql += " ORDER BY price, id LIMIT %d" % int(limit)
                return conn.execute(sql).fetchall()
        '''),
        "README.md": readme("listings", "`search(conn, filters, limit=50)` returns `(id, city, price, bedrooms)` rows. Allowed filter keys are `city`, `status`, `min_price`, `max_price` and `bedrooms`; any other key raises `ValueError`. Values are data: they can contain quotes and other punctuation (`St. John's`). `min_price`, `max_price` and `bedrooms` must be integers (or digit strings), otherwise `ValueError`."),
    },
    solution={"listings.py": dd('''
        """Property search with optional filters."""

        FIELDS = ("city", "status", "min_price", "max_price", "bedrooms")


        def _int(v):
            if isinstance(v, bool):
                raise ValueError("not an integer")
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.isascii() and v.isdigit():
                return int(v)
            raise ValueError("not an integer")


        def search(conn, filters, limit=50):
            """Rows (id, city, price, bedrooms) of the listings that match all `filters`, cheapest first (ties by id), at most `limit` rows.

            Filter keys: city (equals), status (equals), min_price / max_price (price bounds, inclusive), bedrooms (equals)."""
            clauses, params = [], []
            for key, value in filters.items():
                if key not in FIELDS:
                    raise ValueError("unknown filter " + repr(key))
                if key == "min_price":
                    clauses.append("price >= ?")
                    params.append(_int(value))
                elif key == "max_price":
                    clauses.append("price <= ?")
                    params.append(_int(value))
                elif key == "bedrooms":
                    clauses.append("bedrooms = ?")
                    params.append(_int(value))
                else:
                    clauses.append(key + " = ?")
                    params.append(value)
            sql = "SELECT id, city, price, bedrooms FROM listings"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY price, id LIMIT ?"
            params.append(_int(limit))
            return conn.execute(sql, params).fetchall()
    ''')},
    hidden={"tests/test_listings_security.py": P + dd('''
        import listings as m


        def make():
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE listings (id INTEGER PRIMARY KEY, city TEXT, status TEXT, price INTEGER, bedrooms INTEGER)")
            conn.executemany("INSERT INTO listings VALUES (?, ?, ?, ?, ?)", [(1, "Oslo", "open", 300, 2), (2, "Rome", "open", 250, 1), (3, "St. John's", "sold", 120, 3), (4, "Oslo", "sold", 300, 2), (5, "Bergen", "open", 90, 1)])
            return conn


        class ListingTest(unittest.TestCase):
            def test_normal(self):
                conn = make()
                ids = lambda rows: [r[0] for r in rows]
                self.assertEqual(ids(m.search(conn, {})), [5, 3, 2, 1, 4])
                self.assertEqual(ids(m.search(conn, {"city": "Oslo"})), [1, 4])
                self.assertEqual(ids(m.search(conn, {"city": "St. John's"})), [3])
                self.assertEqual(ids(m.search(conn, {"status": "open", "min_price": 100, "max_price": "300"})), [2, 1])
                self.assertEqual(ids(m.search(conn, {"bedrooms": "1"})), [5, 2])
                self.assertEqual(ids(m.search(conn, {}, limit=2)), [5, 3])
                self.assertEqual(m.search(conn, {"city": "Nowhere"}), [])

            def test_injection(self):
                conn = make()
                for filters in [{"1=1 OR city": "x"}, {"city": "x' OR '1'='1"}, {"min_price": "0 OR 1=1"}, {"max_price": "1; DROP TABLE listings"}, {"bedrooms": "1 OR 1=1"}, {"city": "x", "(SELECT 1)": "1"}, {"id": 1}, {"price": 5},
                                {"min_price": 1.5}, {"min_price": None}, {"status": "open'--", "bedrooms": "9' OR '1'='1"}]:
                    try:
                        res = m.search(conn, filters)
                    except ValueError:
                        continue
                    self.assertEqual(res, [], filters)
                with self.assertRaises(ValueError):
                    m.search(conn, {"1=1 OR city": "x"})
                with self.assertRaises(ValueError):
                    m.search(conn, {"id": 1})
                with self.assertRaises(ValueError):
                    m.search(conn, {"min_price": "0 OR 1=1"})
                with self.assertRaises(ValueError):
                    m.search(conn, {}, limit="5; DROP TABLE listings")
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0], 5)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="account-service", d=5, product="the account service", func="login/search_accounts/audit_trail/purge", cwe="CWE-89",
    finding="the account service has four injectable queries written in different styles: `login` pastes the credentials into the WHERE clause (`' OR 1=1 --` logs in as anyone), `search_accounts` concatenates a LIKE pattern, `audit_trail` takes `limit`/`offset` as text, and `purge` builds a DELETE with an f-string over a list of ids.",
    start={
        "accounts.py": dd('''
            """Accounts: login, search, audit trail, purge."""
            import hashlib


            def _hash(password):
                return hashlib.sha256(password.encode("utf-8")).hexdigest()


            def create(conn, name, password, role="user"):
                conn.execute("INSERT INTO accounts (name, pw_hash, role, active) VALUES (?, ?, ?, 1)", (name, _hash(password), role))


            def login(conn, name, password):
                """The (id, name, role) of the active account with this name and password, or None."""
                sql = "SELECT id, name, role FROM accounts WHERE name = '" + name + "' AND pw_hash = '" + _hash(password) + "' AND active = 1"
                return conn.execute(sql).fetchone()


            def search_accounts(conn, term):
                """Names of the active accounts whose name contains `term` (case-insensitive), alphabetically; `%` and `_` in the term are literal."""
                sql = "SELECT name FROM accounts WHERE active = 1 AND name LIKE '%" + term + "%' ORDER BY name"
                return [r[0] for r in conn.execute(sql).fetchall()]


            def audit_trail(conn, account_id, limit="20", offset="0"):
                """Lines `<ts> <action>` of the audit log of the account, newest first (ties by id descending); `limit` and `offset` are integers (or digit strings)."""
                sql = "SELECT ts, action FROM audit WHERE account_id = %d ORDER BY ts DESC, id DESC LIMIT %s OFFSET %s" % (int(account_id), limit, offset)
                return ["%s %s" % row for row in conn.execute(sql).fetchall()]


            def purge(conn, ids):
                """Deactivate (not delete) the accounts with these ids; returns how many were changed. Ids are ints or digit strings; the admin account (role 'admin') is never changed."""
                if not ids:
                    return 0
                cur = conn.execute(f"UPDATE accounts SET active = 0 WHERE role != 'admin' AND active = 1 AND id IN ({', '.join(str(i) for i in ids)})")
                return cur.rowcount
        '''),
        "README.md": readme("accounts", "Four functions, all over sqlite. `login` compares the SHA-256 of the password and needs an active account; `search_accounts` treats the term literally (including `%` and `_`); `audit_trail` takes `limit` and `offset` as integers or digit strings and raises `ValueError` for anything else; `purge` deactivates accounts by id (digits only, `ValueError` otherwise, nothing happens to admins) and returns the number changed. Names, passwords and search terms may contain any characters."),
    },
    solution={"accounts.py": dd('''
        """Accounts: login, search, audit trail, purge."""
        import hashlib


        def _hash(password):
            return hashlib.sha256(password.encode("utf-8")).hexdigest()


        def _int(v):
            if isinstance(v, bool):
                raise ValueError("not an integer")
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.isascii() and v.isdigit():
                return int(v)
            raise ValueError("not an integer")


        def create(conn, name, password, role="user"):
            conn.execute("INSERT INTO accounts (name, pw_hash, role, active) VALUES (?, ?, ?, 1)", (name, _hash(password), role))


        def login(conn, name, password):
            """The (id, name, role) of the active account with this name and password, or None."""
            return conn.execute("SELECT id, name, role FROM accounts WHERE name = ? AND pw_hash = ? AND active = 1", (name, _hash(password))).fetchone()


        def search_accounts(conn, term):
            """Names of the active accounts whose name contains `term` (case-insensitive), alphabetically; `%` and `_` in the term are literal."""
            esc = term.replace("\\\\", "\\\\\\\\").replace("%", "\\\\%").replace("_", "\\\\_")
            rows = conn.execute("SELECT name FROM accounts WHERE active = 1 AND name LIKE ? ESCAPE '\\\\' ORDER BY name", ("%" + esc + "%",)).fetchall()
            return [r[0] for r in rows]


        def audit_trail(conn, account_id, limit="20", offset="0"):
            """Lines `<ts> <action>` of the audit log of the account, newest first (ties by id descending); `limit` and `offset` are integers (or digit strings)."""
            rows = conn.execute("SELECT ts, action FROM audit WHERE account_id = ? ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?", (_int(account_id), _int(limit), _int(offset))).fetchall()
            return ["%s %s" % row for row in rows]


        def purge(conn, ids):
            """Deactivate (not delete) the accounts with these ids; returns how many were changed. Ids are ints or digit strings; the admin account (role 'admin') is never changed."""
            clean = sorted({_int(i) for i in ids})
            if not clean:
                return 0
            marks = ", ".join("?" * len(clean))
            cur = conn.execute("UPDATE accounts SET active = 0 WHERE role != 'admin' AND active = 1 AND id IN (" + marks + ")", clean)
            return cur.rowcount
    ''')},
    hidden={"tests/test_accounts_security.py": P + dd('''
        import accounts as m


        def make():
            conn = sqlite3.connect(":memory:")
            conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT, pw_hash TEXT, role TEXT, active INTEGER)")
            conn.execute("CREATE TABLE audit (id INTEGER PRIMARY KEY, account_id INTEGER, ts TEXT, action TEXT)")
            m.create(conn, "admin", "root-pw", "admin")
            m.create(conn, "ann", "pw1")
            m.create(conn, "o'neil", "p'w")
            m.create(conn, "50%_off", "pw3")
            m.create(conn, "gone", "pw4")
            conn.execute("UPDATE accounts SET active = 0 WHERE name = 'gone'")
            conn.executemany("INSERT INTO audit (account_id, ts, action) VALUES (?, ?, ?)", [(2, "2024-01-01", "login"), (2, "2024-01-03", "edit"), (2, "2024-01-03", "logout"), (3, "2024-01-02", "login")])
            return conn


        class AccountTest(unittest.TestCase):
            def test_normal(self):
                conn = make()
                self.assertEqual(m.login(conn, "ann", "pw1"), (2, "ann", "user"))
                self.assertEqual(m.login(conn, "o'neil", "p'w"), (3, "o'neil", "user"))
                self.assertIsNone(m.login(conn, "ann", "wrong"))
                self.assertIsNone(m.login(conn, "gone", "pw4"))
                self.assertEqual(m.search_accounts(conn, "N"), ["admin", "ann", "o'neil"])
                self.assertEqual(m.search_accounts(conn, "%"), ["50%_off"])
                self.assertEqual(m.search_accounts(conn, "_"), ["50%_off"])
                self.assertEqual(m.audit_trail(conn, 2), ["2024-01-03 logout", "2024-01-03 edit", "2024-01-01 login"])
                self.assertEqual(m.audit_trail(conn, "2", "1", "1"), ["2024-01-03 edit"])
                self.assertEqual(m.purge(conn, [2, "3", 1]), 2)
                self.assertIsNone(m.login(conn, "ann", "pw1"))
                self.assertEqual(m.login(conn, "admin", "root-pw")[2], "admin")
                self.assertEqual(m.purge(conn, []), 0)

            def test_injection(self):
                conn = make()
                for name, pw in [("' OR 1=1 --", "x"), ("admin' --", "x"), ("ann", "' OR '1'='1"), ("x' OR name='admin", "y")]:
                    self.assertIsNone(attempt(m.login, conn, name, pw), name)
                for term in ["' OR '1'='1", "%' OR 1=1 --", "x' UNION SELECT pw_hash FROM accounts --"]:
                    self.assertEqual(attempt(m.search_accounts, conn, term) or [], [], term)
                for lim, off in [("1; DROP TABLE audit", "0"), ("5", "0; DELETE FROM audit"), ("(SELECT 1)", "0"), ("-1", "0"), ("20", "1 UNION SELECT 1, 2"), (1.5, 0)]:
                    with self.assertRaises(ValueError, msg=repr((lim, off))):
                        m.audit_trail(conn, 2, lim, off)
                for ids in [[2, "3) OR (1=1"], ["1 OR 1=1"], [2, "3); UPDATE accounts SET role='admin'; --"], [None], [1.5]]:
                    with self.assertRaises(ValueError, msg=repr(ids)):
                        m.purge(conn, ids)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM accounts WHERE active = 1").fetchone()[0], 4)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 4)
                self.assertEqual(conn.execute("SELECT role FROM accounts WHERE name = 'ann'").fetchone()[0], "user")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))


@family("security-sql-injection", category="security", lang="python", kind="fix", n=10,
        summary="parameterise sqlite queries: values, identifiers, LIKE, ORDER BY, IN lists, stacked statements, second order")
def gen_sqli(rng, n):
    return list(_sec.emit(rng, SC[:n], tags=["sql"]))
