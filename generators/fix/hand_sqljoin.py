"""SQL semantics in embedded SQLite: outer joins, fan-out, NULLs, relational division, integer division (python)."""
from datetime import date

from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A: a public library's reports (members, books, loans, fines).
# ------------------------------------------------------------------------------------------------------------------

A_SCHEMA = dd('''
    SCHEMA = """
    CREATE TABLE members (id INTEGER PRIMARY KEY, name TEXT NOT NULL, tier TEXT NOT NULL);
    CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT NOT NULL, copies INTEGER NOT NULL);
    CREATE TABLE loans (
        id INTEGER PRIMARY KEY,
        member_id INTEGER,                -- NULL for a walk-in (guest) loan
        book_id INTEGER NOT NULL,
        out_date TEXT NOT NULL,           -- ISO date
        due_date TEXT NOT NULL,
        returned_date TEXT                -- NULL while the book is still out
    );
    CREATE TABLE fines (id INTEGER PRIMARY KEY, member_id INTEGER NOT NULL, cents INTEGER NOT NULL, paid INTEGER NOT NULL DEFAULT 0);
    """


    def create_schema(conn):
        conn.executescript(SCHEMA)
''')

A_REPORT = dd('''
    def loan_counts(conn, since=None):
        sql = """
            SELECT m.name, COUNT(l.id) AS n
            FROM members m
            LEFT JOIN loans l ON l.member_id = m.id AND (? IS NULL OR l.out_date >= ?)
            GROUP BY m.id
            ORDER BY n DESC, m.name
        """
        return conn.execute(sql, (since, since)).fetchall()


    def members_without_loans(conn):
        sql = """
            SELECT m.name FROM members m
            WHERE NOT EXISTS (SELECT 1 FROM loans l WHERE l.member_id = m.id)
            ORDER BY m.name
        """
        return [r[0] for r in conn.execute(sql)]


    def overdue(conn, today):
        sql = """
            SELECT l.id, m.name, CAST(julianday(?) - julianday(l.due_date) AS INTEGER) AS late
            FROM loans l JOIN members m ON m.id = l.member_id
            WHERE l.returned_date IS NULL AND l.due_date < ?
            ORDER BY late DESC, l.id
        """
        return conn.execute(sql, (today, today)).fetchall()


    def fines_owed(conn):
        sql = """
            SELECT m.name, COALESCE(f.owed, 0) AS owed, COALESCE(o.n, 0) AS open_loans
            FROM members m
            LEFT JOIN (SELECT member_id, SUM(cents) AS owed FROM fines WHERE paid = 0 GROUP BY member_id) f ON f.member_id = m.id
            LEFT JOIN (SELECT member_id, COUNT(*) AS n FROM loans WHERE returned_date IS NULL GROUP BY member_id) o ON o.member_id = m.id
            WHERE COALESCE(f.owed, 0) > 0 OR COALESCE(o.n, 0) > 0
            ORDER BY owed DESC, m.name
        """
        return conn.execute(sql).fetchall()


    def availability(conn):
        sql = """
            SELECT b.title, b.copies - COUNT(l.id)
            FROM books b
            LEFT JOIN loans l ON l.book_id = b.id AND l.returned_date IS NULL
            GROUP BY b.id
            ORDER BY b.title
        """
        return conn.execute(sql).fetchall()


    def loans_between(conn, start, end):
        sql = "SELECT id FROM loans WHERE out_date BETWEEN ? AND ? ORDER BY out_date, id"
        return [r[0] for r in conn.execute(sql, (start, end))]
''')

A_README = dd('''
    # libdesk

    Reports of a public library, as SQL over SQLite (`libdesk/schema.py` has the tables; a loan with `member_id` NULL is a
    walk-in loan by a guest). All functions take a `sqlite3` connection and return plain lists of tuples.

    * `loan_counts(conn, since=None)`: `[(name, n)]` for **every** member, `n` = number of that member's loans (with `out_date >= since`
      when `since` is given; members with no such loans show `0`), ordered by `n` descending then name.
    * `members_without_loans(conn)`: names of members who never borrowed anything, sorted. Guest loans do not matter.
    * `overdue(conn, today)`: `[(loan_id, name, days_late)]` for loans that are still out (`returned_date` NULL), belong to a member and
      whose `due_date < today`; `days_late` is whole days; ordered by `days_late` descending then loan id.
    * `fines_owed(conn)`: `[(name, owed_cents, open_loans)]` for members who owe unpaid fines or have loans still out, where `owed_cents`
      is the sum of their unpaid fines and `open_loans` the number of their loans still out; ordered by `owed_cents` descending then name.
    * `availability(conn)`: `[(title, copies_left)]` by title; `copies_left` is `copies` minus the loans of that book still out.
    * `loans_between(conn, start, end)`: ids of loans with `start <= out_date <= end` (both ends included), ordered by date then id.
''')

MEMBERS = [(1, "Ana", "gold"), (2, "Bo", "basic"), (3, "Cy", "basic"), (4, "Di", "gold"), (5, "Eli", "basic")]
BOOKS = [(1, "Atlas", 2), (2, "Borges", 1), (3, "Cyclops", 3), (4, "Dune", 4)]
LOANS = [
    (1, 1, 1, "2025-01-05", "2025-01-19", "2025-01-18"),
    (2, 1, 2, "2025-02-01", "2025-02-15", None),
    (3, 2, 1, "2025-02-03", "2025-02-17", None),
    (4, 2, 3, "2025-02-10", "2025-02-24", None),
    (5, 3, 3, "2025-01-20", "2025-02-03", "2025-02-10"),
    (6, None, 1, "2025-02-05", "2025-02-19", None),
    (7, 2, 2, "2025-03-01", "2025-03-15", None),
]
FINES = [(1, 1, 500, 0), (2, 1, 250, 1), (3, 3, 700, 0), (4, 3, 100, 0), (5, 2, 300, 0)]


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


def a_expect():
    names = {m[0]: m[1] for m in MEMBERS}

    def counts(since):
        rows = []
        for mid, name, _ in MEMBERS:
            n = sum(1 for l in LOANS if l[1] == mid and (since is None or l[3] >= since))
            rows.append((name, n))
        return sorted(rows, key=lambda r: (-r[1], r[0]))

    without = sorted(names[m] for m in names if not any(l[1] == m for l in LOANS))
    today = "2025-03-10"
    od = sorted(((l[0], names[l[1]], _days(today, l[4])) for l in LOANS if l[5] is None and l[1] is not None and l[4] < today), key=lambda r: (-r[2], r[0]))
    owed = []
    for mid, name, _ in MEMBERS:
        o = sum(f[2] for f in FINES if f[1] == mid and f[3] == 0)
        n = sum(1 for l in LOANS if l[1] == mid and l[5] is None)
        if o > 0 or n > 0:
            owed.append((name, o, n))
    owed.sort(key=lambda r: (-r[1], r[0]))
    avail = sorted(((b[1], b[2] - sum(1 for l in LOANS if l[2] == b[0] and l[5] is None)) for b in BOOKS), key=lambda r: r[0])
    between = [l[0] for l in sorted(LOANS, key=lambda l: (l[3], l[0])) if "2025-02-01" <= l[3] <= "2025-02-10"]
    return {"counts_all": counts(None), "counts_since": counts("2025-02-01"), "without": without, "overdue": od, "owed": owed,
            "avail": avail, "between": between, "today": today}


def _a_hidden() -> dict:
    e = a_expect()
    test = dd('''
        import sqlite3
        import unittest

        from libdesk import report
        from libdesk.schema import create_schema

        MEMBERS = @MEMBERS@
        BOOKS = @BOOKS@
        LOANS = @LOANS@
        FINES = @FINES@


        def db():
            conn = sqlite3.connect(":memory:")
            create_schema(conn)
            conn.executemany("INSERT INTO members VALUES (?, ?, ?)", MEMBERS)
            conn.executemany("INSERT INTO books VALUES (?, ?, ?)", BOOKS)
            conn.executemany("INSERT INTO loans VALUES (?, ?, ?, ?, ?, ?)", LOANS)
            conn.executemany("INSERT INTO fines VALUES (?, ?, ?, ?)", FINES)
            return conn


        class Reports(unittest.TestCase):
            def setUp(self):
                self.conn = db()

            def test_loan_counts_include_members_with_no_loans(self):
                self.assertEqual(report.loan_counts(self.conn), @COUNTS_ALL@)

            def test_loan_counts_since_keeps_members_without_recent_loans(self):
                self.assertEqual(report.loan_counts(self.conn, "2025-02-01"), @COUNTS_SINCE@)

            def test_loan_counts_since_the_future(self):
                rows = report.loan_counts(self.conn, "2030-01-01")
                self.assertEqual(rows, [("Ana", 0), ("Bo", 0), ("Cy", 0), ("Di", 0), ("Eli", 0)])

            def test_members_without_loans_ignores_guest_loans(self):
                self.assertEqual(report.members_without_loans(self.conn), @WITHOUT@)

            def test_overdue(self):
                self.assertEqual(report.overdue(self.conn, "@TODAY@"), @OVERDUE@)

            def test_overdue_on_an_early_date(self):
                self.assertEqual(report.overdue(self.conn, "2025-02-16"), [(2, "Ana", 1)])
                self.assertEqual(report.overdue(self.conn, "2025-02-15"), [])

            def test_fines_owed_does_not_multiply_by_the_number_of_loans(self):
                self.assertEqual(report.fines_owed(self.conn), @OWED@)

            def test_availability_counts_only_loans_still_out(self):
                self.assertEqual(report.availability(self.conn), @AVAIL@)

            def test_loans_between_includes_both_ends(self):
                self.assertEqual(report.loans_between(self.conn, "2025-02-01", "2025-02-10"), @BETWEEN@)
                self.assertEqual(report.loans_between(self.conn, "2025-02-10", "2025-02-10"), [4])
                self.assertEqual(report.loans_between(self.conn, "2025-04-01", "2025-04-30"), [])


        if __name__ == "__main__":
            unittest.main()
    ''')
    for k, v in [("@MEMBERS@", MEMBERS), ("@BOOKS@", BOOKS), ("@LOANS@", LOANS), ("@FINES@", FINES), ("@COUNTS_ALL@", e["counts_all"]),
                 ("@COUNTS_SINCE@", e["counts_since"]), ("@WITHOUT@", e["without"]), ("@OVERDUE@", e["overdue"]), ("@OWED@", e["owed"]),
                 ("@AVAIL@", e["avail"]), ("@BETWEEN@", e["between"])]:
        test = test.replace(k, repr(v))
    test = test.replace("@TODAY@", e["today"])
    return {"tests/test_hidden_reports.py": test}


A_VISIBLE = {
    "tests/test_reports.py": dd('''
        import sqlite3
        import unittest

        from libdesk import report
        from libdesk.schema import create_schema


        class SmokeTests(unittest.TestCase):
            def test_a_tiny_library(self):
                conn = sqlite3.connect(":memory:")
                create_schema(conn)
                conn.execute("INSERT INTO members VALUES (1, 'Ana', 'gold')")
                conn.execute("INSERT INTO books VALUES (1, 'Atlas', 2)")
                conn.execute("INSERT INTO loans VALUES (1, 1, 1, '2025-01-05', '2025-01-19', NULL)")
                self.assertEqual(report.loan_counts(conn), [("Ana", 1)])
                self.assertEqual(report.availability(conn), [("Atlas", 1)])
                self.assertEqual(report.overdue(conn, "2025-02-01"), [(1, "Ana", 13)])


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["inner-join"] = (
        "The monthly report \"loans per member\" lists only members who borrowed something; members with zero loans (we want to "
        "send them a reminder) are missing from it. `loan_counts` in `libdesk/report.py`."
    )
    p["where-filter"] = (
        "`loan_counts(conn, since)` is fine without a date, but as soon as `since` is given the members who have not borrowed since that "
        "date disappear from the list instead of showing 0. That is exactly the group the outreach team wants to see."
    )
    p["count-star"] = (
        "In the loans-per-member report, members who never borrowed show 1 loan instead of 0. Everyone else has the right number."
    )
    p["fan-out"] = lambda c: (
        "Finance says the fines report overstates what members owe. In a quick test, a member (Bo) with a single unpaid fine of 3.00 "
        "and three books still out comes back as "
        + c.probe("import sqlite3\nfrom libdesk import report\nfrom libdesk.schema import create_schema\nconn = sqlite3.connect(':memory:')\ncreate_schema(conn)\n"
                  "conn.executemany('INSERT INTO members VALUES (?,?,?)', [(1, 'Bo', 'basic')])\n"
                  "conn.executemany('INSERT INTO loans VALUES (?,?,?,?,?,?)', [(1, 1, 1, '2025-01-01', '2025-01-15', None), (2, 1, 1, '2025-01-02', '2025-01-16', None), (3, 1, 1, '2025-01-03', '2025-01-17', None)])\n"
                  "conn.execute('INSERT INTO fines VALUES (1, 1, 300, 0)')\nprint(report.fines_owed(conn))\n")[1]
        + " from `fines_owed` (tuples are name, owed_cents, open_loans), although the fine is only 300 cents. It gets worse with "
        "more loans. Please fix the query."
    )
    p["not-in"] = (
        "The \"never borrowed\" list is empty since we started recording walk-in (guest) loans, although we know several members have "
        "never borrowed. Before guest loans existed it was right. The query is in `members_without_loans`."
    )
    p["between"] = (
        "A librarian asked for all loans of 1-10 February and the ones made on 10 February are missing. Both ends of a date range should be "
        "included, as in the README."
    )
    p["overdue-returned"] = (
        "The overdue list contains books that were returned, late: they show up as overdue forever. Only loans that are still out "
        "belong in the list."
    )
    p["fan-out-and-overdue"] = (
        "Two reports are off in the library system: the overdue list contains books that have long been returned, and the fines report "
        "multiplies amounts for members with several loans. I believe both are SQL mistakes. The unit tests we have only use a tiny "
        "database with one loan and no fines. Please fix both."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "libdesk/__init__.py": '"""Library reports."""\n', "libdesk/schema.py": A_SCHEMA, "libdesk/report.py": A_REPORT}
    r = "libdesk/report.py"
    fan = ('        SELECT m.name, COALESCE(f.owed, 0) AS owed, COALESCE(o.n, 0) AS open_loans\n        FROM members m\n'
           '        LEFT JOIN (SELECT member_id, SUM(cents) AS owed FROM fines WHERE paid = 0 GROUP BY member_id) f ON f.member_id = m.id\n'
           '        LEFT JOIN (SELECT member_id, COUNT(*) AS n FROM loans WHERE returned_date IS NULL GROUP BY member_id) o ON o.member_id = m.id\n'
           '        WHERE COALESCE(f.owed, 0) > 0 OR COALESCE(o.n, 0) > 0\n        ORDER BY owed DESC, m.name\n',
           '        SELECT m.name, COALESCE(SUM(CASE WHEN f.paid = 0 THEN f.cents END), 0) AS owed, COUNT(l.id) AS open_loans\n        FROM members m\n'
           '        LEFT JOIN fines f ON f.member_id = m.id\n        LEFT JOIN loans l ON l.member_id = m.id AND l.returned_date IS NULL\n'
           '        GROUP BY m.id\n        HAVING owed > 0 OR open_loans > 0\n        ORDER BY owed DESC, m.name\n')
    ov = ("        WHERE l.returned_date IS NULL AND l.due_date < ?\n", "        WHERE l.due_date < ?\n")
    bugs = [
        Bug("loan-counts-inner-join", 1, {r: [("        LEFT JOIN loans l ON l.member_id = m.id AND (? IS NULL OR l.out_date >= ?)\n", "        JOIN loans l ON l.member_id = m.id AND (? IS NULL OR l.out_date >= ?)\n")]}, P["inner-join"]),
        Bug("loan-counts-count-star", 1, {r: [("        SELECT m.name, COUNT(l.id) AS n\n", "        SELECT m.name, COUNT(*) AS n\n")]}, P["count-star"]),
        Bug("since-filter-in-where", 3, {r: [("        LEFT JOIN loans l ON l.member_id = m.id AND (? IS NULL OR l.out_date >= ?)\n        GROUP BY m.id\n",
                                               "        LEFT JOIN loans l ON l.member_id = m.id\n        WHERE (? IS NULL OR l.out_date >= ?)\n        GROUP BY m.id\n")]}, P["where-filter"]),
        Bug("never-borrowed-not-in", 3, {r: [("        WHERE NOT EXISTS (SELECT 1 FROM loans l WHERE l.member_id = m.id)\n", "        WHERE m.id NOT IN (SELECT member_id FROM loans)\n")]}, P["not-in"]),
        Bug("overdue-includes-returned", 3, {r: [ov]}, P["overdue-returned"]),
        Bug("range-end-excluded", 1, {r: [('    sql = "SELECT id FROM loans WHERE out_date BETWEEN ? AND ? ORDER BY out_date, id"\n',
                                           '    sql = "SELECT id FROM loans WHERE out_date >= ? AND out_date < ? ORDER BY out_date, id"\n')]}, P["between"]),
        Bug("fines-join-fan-out", 4, {r: [fan]}, P["fan-out"]),
        Bug("fan-out-and-returned-overdue", 5, {r: [fan, ov]}, P["fan-out-and-overdue"]),
    ]
    return Base("libdesk", "python", good, A_VISIBLE, _a_hidden(), bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B: course enrollment, waitlists and relational division.
# ------------------------------------------------------------------------------------------------------------------

B_SCHEMA = dd('''
    SCHEMA = """
    CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
    CREATE TABLE courses (id INTEGER PRIMARY KEY, title TEXT NOT NULL, capacity INTEGER NOT NULL);
    CREATE TABLE enrollments (
        student_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('enrolled', 'waitlist', 'dropped')),
        ts INTEGER NOT NULL,
        PRIMARY KEY (student_id, course_id)
    );
    """


    def create_schema(conn):
        conn.executescript(SCHEMA)
''')

B_QUERIES = dd('''
    def seats_left(conn, course_id):
        sql = """
            SELECT MAX(0, c.capacity - (SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id AND e.status = 'enrolled'))
            FROM courses c WHERE c.id = ?
        """
        row = conn.execute(sql, (course_id,)).fetchone()
        if row is None:
            raise KeyError(course_id)
        return row[0]


    def waitlist(conn, course_id):
        sql = """
            SELECT s.name FROM enrollments e JOIN students s ON s.id = e.student_id
            WHERE e.course_id = ? AND e.status = 'waitlist'
            ORDER BY e.ts, s.id
        """
        return [(i, r[0]) for i, r in enumerate(conn.execute(sql, (course_id,)), start=1)]


    def students_in_all(conn, course_ids):
        wanted = sorted(set(course_ids))
        if not wanted:
            return []
        marks = ",".join("?" for _ in wanted)
        sql = f"""
            SELECT s.name FROM students s JOIN enrollments e ON e.student_id = s.id
            WHERE e.status = 'enrolled' AND e.course_id IN ({marks})
            GROUP BY s.id HAVING COUNT(DISTINCT e.course_id) = ?
            ORDER BY s.name
        """
        return [r[0] for r in conn.execute(sql, (*wanted, len(wanted)))]


    def average_load(conn):
        sql = """
            SELECT AVG(n) FROM (
                SELECT COUNT(e.course_id) AS n FROM students s
                LEFT JOIN enrollments e ON e.student_id = s.id AND e.status = 'enrolled'
                GROUP BY s.id
            )
        """
        value = conn.execute(sql).fetchone()[0]
        return 0.0 if value is None else round(value, 2)


    def fullest(conn, n):
        sql = """
            SELECT c.title, COUNT(e.student_id) AS enrolled, c.capacity
            FROM courses c LEFT JOIN enrollments e ON e.course_id = c.id AND e.status = 'enrolled'
            GROUP BY c.id
            ORDER BY enrolled * 1.0 / c.capacity DESC, c.title
            LIMIT ?
        """
        return conn.execute(sql, (n,)).fetchall()
''')

B_README = dd('''
    # enroll

    Queries behind a university enrollment desk (SQLite, `enroll/schema.py` has the tables). An enrollment has a `status`:
    `enrolled`, `waitlist` or `dropped`; `ts` orders requests in time.

    * `seats_left(conn, course_id)`: `capacity` minus the number of **enrolled** students, never below 0 (courses can be overbooked
      by hand); unknown course is a `KeyError`.
    * `waitlist(conn, course_id)`: `[(position, name)]` for students on the waitlist, position counted from 1, ordered by `ts` and
      then by student id.
    * `students_in_all(conn, course_ids)`: names (sorted) of students who are **enrolled** (not waitlisted, not dropped) in *every* one of
      the given courses; repeated ids count once; no ids gives `[]`.
    * `average_load(conn)`: average number of courses a student is enrolled in, **over all students** (students with none count as 0),
      rounded to 2 decimals; `0.0` if there are no students.
    * `fullest(conn, n)`: the `n` courses with the highest fill ratio (enrolled / capacity, as a real number), ties by title, as
      `[(title, enrolled, capacity)]`.
''')

STUDENTS = [(1, "Zoe"), (2, "Yan"), (3, "Xia"), (4, "Wes"), (5, "Val"), (6, "Uma")]
COURSES = [(1, "Algebra", 5), (2, "Biology", 3), (3, "Chemistry", 4), (4, "Drawing", 2)]
ENROLL = [
    (1, 1, "enrolled", 10), (2, 1, "enrolled", 11), (3, 1, "waitlist", 12), (4, 1, "waitlist", 12), (5, 1, "dropped", 13),
    (1, 2, "enrolled", 20), (2, 2, "enrolled", 21), (3, 2, "enrolled", 22), (4, 2, "waitlist", 23),
    (1, 3, "enrolled", 30), (2, 3, "waitlist", 31), (5, 3, "enrolled", 32), (6, 3, "waitlist", 31),
    (1, 4, "enrolled", 40), (2, 4, "dropped", 41),
]


def b_expect():
    enrolled = {}
    for s, c, st, ts in ENROLL:
        if st == "enrolled":
            enrolled.setdefault(c, set()).add(s)
    names = dict(STUDENTS)
    seats = {c: max(0, cap - len(enrolled.get(c, ()))) for c, _, cap in COURSES}

    def wl(c):
        rows = sorted((ts, s) for s, cc, st, ts in ENROLL if cc == c and st == "waitlist")
        return [(i, names[s]) for i, (ts, s) in enumerate(rows, start=1)]

    def inall(ids):
        ids = set(ids)
        if not ids:
            return []
        return sorted(names[s] for s in names if all(s in enrolled.get(c, ()) for c in ids))

    per_student = {s: sum(1 for x in ENROLL if x[0] == s and x[2] == "enrolled") for s in names}
    avg = round(sum(per_student.values()) / len(names), 2)
    ratio = sorted(((len(enrolled.get(c, ())) / cap, t, len(enrolled.get(c, ())), cap) for c, t, cap in COURSES), key=lambda r: (-r[0], r[1]))
    fullest = [(t, e, cap) for _, t, e, cap in ratio]
    return {"seats": seats, "wl1": wl(1), "wl3": wl(3), "all12": inall([1, 2]), "all123": inall([1, 2, 3]), "all1": inall([1]), "avg": avg, "fullest": fullest}


def _b_hidden() -> dict:
    e = b_expect()
    test = dd('''
        import sqlite3
        import unittest

        from enroll import queries
        from enroll.schema import create_schema

        STUDENTS = @STUDENTS@
        COURSES = @COURSES@
        ENROLL = @ENROLL@


        def db(enroll=None, students=None):
            conn = sqlite3.connect(":memory:")
            create_schema(conn)
            conn.executemany("INSERT INTO students VALUES (?, ?)", STUDENTS if students is None else students)
            conn.executemany("INSERT INTO courses VALUES (?, ?, ?)", COURSES)
            conn.executemany("INSERT INTO enrollments VALUES (?, ?, ?, ?)", ENROLL if enroll is None else enroll)
            return conn


        class Queries(unittest.TestCase):
            def setUp(self):
                self.conn = db()

            def test_seats_left_counts_only_enrolled_students(self):
                for course, left in @SEATS@.items():
                    self.assertEqual(queries.seats_left(self.conn, course), left, course)

            def test_seats_never_negative(self):
                conn = db(enroll=[(1, 4, "enrolled", 1), (2, 4, "enrolled", 2), (3, 4, "enrolled", 3)])
                self.assertEqual(queries.seats_left(conn, 4), 0)

            def test_unknown_course(self):
                with self.assertRaises(KeyError):
                    queries.seats_left(self.conn, 99)

            def test_waitlist_positions_and_tie_order(self):
                self.assertEqual(queries.waitlist(self.conn, 1), @WL1@)
                self.assertEqual(queries.waitlist(self.conn, 3), @WL3@)
                self.assertEqual(queries.waitlist(self.conn, 4), [])

            def test_waitlist_ties_are_broken_by_student_id_not_insertion_order(self):
                conn = db(enroll=[(6, 2, "waitlist", 5), (3, 2, "waitlist", 5), (1, 2, "waitlist", 5)])
                self.assertEqual(queries.waitlist(conn, 2), [(1, "Zoe"), (2, "Xia"), (3, "Uma")])

            def test_students_in_all_courses(self):
                self.assertEqual(queries.students_in_all(self.conn, [1, 2]), @ALL12@)
                self.assertEqual(queries.students_in_all(self.conn, [1, 2, 3]), @ALL123@)
                self.assertEqual(queries.students_in_all(self.conn, [1]), @ALL1@)

            def test_students_in_all_ignores_repeated_ids_and_handles_nothing(self):
                self.assertEqual(queries.students_in_all(self.conn, [1, 1, 2, 2, 2]), @ALL12@)
                self.assertEqual(queries.students_in_all(self.conn, []), [])
                self.assertEqual(queries.students_in_all(self.conn, [1, 99]), [])

            def test_waitlisted_and_dropped_do_not_count_as_enrolled(self):
                conn = db(enroll=[(1, 1, "enrolled", 1), (1, 2, "waitlist", 2), (2, 1, "enrolled", 3), (2, 2, "enrolled", 4), (3, 1, "dropped", 5), (3, 2, "enrolled", 6)])
                self.assertEqual(queries.students_in_all(conn, [1, 2]), ["Yan"])

            def test_average_load_counts_students_with_no_courses(self):
                self.assertEqual(queries.average_load(self.conn), @AVG@)

            def test_average_load_is_not_an_integer_division(self):
                conn = db(enroll=[(1, 1, "enrolled", 1), (1, 2, "enrolled", 2), (2, 1, "enrolled", 3)], students=[(1, "Zoe"), (2, "Yan"), (3, "Xia")])
                self.assertEqual(queries.average_load(conn), 1.0)
                conn = db(enroll=[(1, 1, "enrolled", 1)], students=[(1, "Zoe"), (2, "Yan"), (3, "Xia")])
                self.assertEqual(queries.average_load(conn), 0.33)
                self.assertEqual(queries.average_load(db(enroll=[], students=[])), 0.0)

            def test_fullest_courses_by_ratio(self):
                self.assertEqual(queries.fullest(self.conn, 4), @FULLEST@)
                self.assertEqual(queries.fullest(self.conn, 2), @FULLEST@[:2])
                self.assertEqual(queries.fullest(self.conn, 0), [])


        if __name__ == "__main__":
            unittest.main()
    ''')
    for k, v in [("@STUDENTS@", STUDENTS), ("@COURSES@", COURSES), ("@ENROLL@", ENROLL), ("@SEATS@", e["seats"]), ("@WL1@", e["wl1"]), ("@WL3@", e["wl3"]),
                 ("@ALL12@", e["all12"]), ("@ALL123@", e["all123"]), ("@ALL1@", e["all1"]), ("@AVG@", e["avg"]), ("@FULLEST@", e["fullest"])]:
        test = test.replace(k, repr(v))
    return {"tests/test_hidden_queries.py": test}


B_VISIBLE = {
    "tests/test_queries.py": dd('''
        import sqlite3
        import unittest

        from enroll import queries
        from enroll.schema import create_schema


        class SmokeTests(unittest.TestCase):
            def test_one_course(self):
                conn = sqlite3.connect(":memory:")
                create_schema(conn)
                conn.execute("INSERT INTO students VALUES (1, 'Zoe')")
                conn.execute("INSERT INTO courses VALUES (1, 'Algebra', 2)")
                conn.execute("INSERT INTO enrollments VALUES (1, 1, 'enrolled', 1)")
                self.assertEqual(queries.seats_left(conn, 1), 1)
                self.assertEqual(queries.students_in_all(conn, [1]), ["Zoe"])
                self.assertEqual(queries.waitlist(conn, 1), [])


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _b_prompts():
    p = {}
    p["dropped"] = (
        "Algebra shows no free seats although two students dropped it this week. Dropped and waitlisted students seem to be "
        "counted against the capacity; only enrolled ones should be."
    )
    p["negative"] = (
        "The enrollment desk shows \"-1 seats left\" for the courses that were overbooked by hand. The README says the number "
        "is never below zero."
    )
    p["division-status"] = (
        "The \"students taking all of these courses\" filter returns students who are only on the waitlist for one of the courses. "
        "Only enrolled students count; waitlisted and dropped ones do not."
    )
    p["ratio"] = (
        "The 'fullest courses' widget shows courses in a seemingly random order: Biology (3 of 3 enrolled) is not first and half-full "
        "courses are ranked with empty ones. It looks like the fill ratio comes out as 0 or 1."
    )
    p["average-zero"] = (
        "The dashboard's average course load looks too high. Students who are not enrolled in anything do not seem to be part of the "
        "average, although the README says they count as 0."
    )
    p["waitlist-ties"] = (
        "Waitlist positions are not stable: students who joined in the same second swap places between page loads. Ties on the time "
        "must be broken by student id so that everyone sees the same order."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "enroll/__init__.py": '"""Enrollment queries."""\n', "enroll/schema.py": B_SCHEMA, "enroll/queries.py": B_QUERIES}
    q = "enroll/queries.py"
    bugs = [
        Bug("all-statuses-take-a-seat", 2, {q: [("(SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id AND e.status = 'enrolled')", "(SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id)")]}, P["dropped"]),
        Bug("overbooked-goes-negative", 2, {q: [("        SELECT MAX(0, c.capacity - (SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id AND e.status = 'enrolled'))\n",
                                                 "        SELECT c.capacity - (SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id AND e.status = 'enrolled')\n")]}, P["negative"]),
        Bug("waitlist-ties-unordered", 2, {q: [("        ORDER BY e.ts, s.id\n", "        ORDER BY e.ts\n")]}, P["waitlist-ties"]),
        Bug("division-ignores-status", 2, {q: [("        WHERE e.status = 'enrolled' AND e.course_id IN ({marks})\n", "        WHERE e.course_id IN ({marks})\n")]}, P["division-status"]),
        Bug("fill-ratio-integer-division", 2, {q: [("        ORDER BY enrolled * 1.0 / c.capacity DESC, c.title\n", "        ORDER BY enrolled / c.capacity DESC, c.title\n")]}, P["ratio"]),
        Bug("average-skips-idle-students", 3, {q: [("            LEFT JOIN enrollments e ON e.student_id = s.id AND e.status = 'enrolled'\n", "            JOIN enrollments e ON e.student_id = s.id AND e.status = 'enrolled'\n")]}, P["average-zero"]),
    ]
    return Base("enroll", "python", good, B_VISIBLE, _b_hidden(), bugs)


@family("fix-hand-sql-join", category="fix", lang="python", kind="fix", n=14,
        summary="SQL semantics in embedded SQLite: outer joins, fan-out, NOT IN with NULLs, relational division, integer division")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
