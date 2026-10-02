"""SQL tasks on an invented community tool library (overdue rules, interval overlaps, calendar tables, streaks, capped fees)."""
from datetime import date, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE members (
      member_id      INTEGER PRIMARY KEY,
      name           TEXT NOT NULL,
      joined_on      TEXT NOT NULL,
      tier           TEXT NOT NULL CHECK (tier IN ('basic', 'plus')),
      deposit_cents  INTEGER NOT NULL
    );
    CREATE TABLE categories (
      cat_id  INTEGER PRIMARY KEY,
      name    TEXT NOT NULL UNIQUE
    );
    CREATE TABLE tools (
      tool_id            INTEGER PRIMARY KEY,
      cat_id             INTEGER NOT NULL REFERENCES categories(cat_id),
      label              TEXT NOT NULL UNIQUE,
      replacement_cents  INTEGER NOT NULL,
      retired            INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE loans (
      loan_id      INTEGER PRIMARY KEY,
      tool_id      INTEGER NOT NULL REFERENCES tools(tool_id),
      member_id    INTEGER NOT NULL REFERENCES members(member_id),
      out_on       TEXT NOT NULL,
      due_on       TEXT NOT NULL,
      returned_on  TEXT                       -- NULL while the tool is still out
    );
    CREATE TABLE fees (
      fee_id        INTEGER PRIMARY KEY,
      loan_id       INTEGER NOT NULL REFERENCES loans(loan_id),
      kind          TEXT NOT NULL CHECK (kind IN ('late', 'damage', 'cleaning')),
      amount_cents  INTEGER NOT NULL,
      assessed_on   TEXT NOT NULL
    );
    CREATE TABLE reservations (
      res_id     INTEGER PRIMARY KEY,
      tool_id    INTEGER NOT NULL REFERENCES tools(tool_id),
      member_id  INTEGER NOT NULL REFERENCES members(member_id),
      start_on   TEXT NOT NULL,               -- first reserved day
      end_on     TEXT NOT NULL                -- last reserved day (inclusive)
    );
''')

DOC = dd('''
    The Brindle Street Tool Library lends tools to members.

    * A **loan** goes out on `out_on` and is due on `due_on`. It is **returned late** when `returned_on` is after `due_on`; the days late are the difference in days.
      A loan that is still out (`returned_on` IS NULL) is **overdue** when `due_on` is before today; a loan due today is not overdue yet. Today is **2033-06-20**.
    * Late fees are 50 cents per day late, capped at 25% of the tool's `replacement_cents` (integer arithmetic, rounded down). `fees` holds what was actually charged, one row per fee; some may be wrong or missing.
    * A **reservation** blocks a tool for whole days: from `start_on` to `end_on`, both included. A tool should not be reserved twice for the same day.
    * A loan occupies its tool from `out_on` until `returned_on` (or until `due_on` if it is still out), both days included.
    * Retired tools (`retired = 1`) are no longer lent. Dates are ISO text, money is in cents.
''')

CATS = ["ladders", "saws", "drills", "garden", "paint", "plumbing"]
NAMES = ["Ansel", "Beata", "Cyrus", "Dorrit", "Emeka", "Fenna", "Gustav", "Hana", "Ilario", "Jorun", "Kalani", "Liesl", "Mattis", "Noor", "Orla", "Pavel", "Quill", "Rosalind", "Soren", "Talia", "Ulf", "Vesna", "Wim", "Xanthe"]
TOOLS = ["step ladder", "extension ladder", "hand saw", "jigsaw", "circular saw", "cordless drill", "hammer drill", "lawn aerator", "hedge trimmer", "wheelbarrow", "roller kit", "paint sprayer", "pipe wrench", "drain snake", "tile cutter", "belt sander", "scaffold tower", "leaf blower", "mitre saw", "stud finder", "wet vac", "post hole digger", "angle grinder", "sawhorse pair"]
TODAY = date(2033, 6, 20)


def gen(rng, big):
    nm = 22 if big else 7
    members = [(i + 1, NAMES[i], K.iso(date(2031, 1, 1) + timedelta(days=rng.randint(0, 800))), rng.choice(["basic", "basic", "plus"]), rng.choice([2000, 3000, 5000])) for i in range(nm)]
    cats = [(i + 1, CATS[i]) for i in range(5 if big else 3)]
    nt = 22 if big else 9
    retired = set(rng.sample(range(nt), 3 if big else 2))
    tools = [(i + 1, rng.choice(cats[:-1])[0], TOOLS[i], rng.choice([2500, 4000, 6500, 9000, 15000, 30000]), 1 if i in retired else 0) for i in range(nt)]
    loans, fees, res = [], [], []
    lid = fid = 0
    nloans = 150 if big else 30
    for _ in range(nloans):
        lid += 1
        out = date(2033, 3, 1) + timedelta(days=rng.randint(0, 105))
        due = out + timedelta(days=rng.choice([7, 7, 14]))
        mem, tool = rng.choice(members), rng.choice(tools)
        if out + timedelta(days=3) > TODAY or rng.random() < 0.12:
            ret = None
        else:
            ret = due + timedelta(days=rng.choice([-3, -1, 0, 0, 0, 1, 2, 4, 9, 18, 30]))
            if ret < out:
                ret = out
            if ret > TODAY:
                ret = None
        loans.append([lid, tool[0], mem[0], K.iso(out), K.iso(due), K.iso(ret) if ret else None])
    # plant: a loan due today, one due tomorrow and one overdue by a single day, all still out; one loan returned exactly on its due date
    for off, extra in ((0, 7), (1, 14), (-1, 7)):
        lid += 1
        due = TODAY + timedelta(days=off)
        loans.append([lid, tools[off + 1][0], members[off + 1][0], K.iso(due - timedelta(days=extra)), K.iso(due), None])
    lid += 1
    loans.append([lid, tools[0][0], members[0][0], "2033-05-01", "2033-05-08", "2033-05-08"])
    tools = tools
    for ln in loans:
        if ln[5] and ln[5] > ln[4]:
            late = (date.fromisoformat(ln[5]) - date.fromisoformat(ln[4])).days
            repl = next(t[3] for t in tools if t[0] == ln[1])
            right = min(late * 50, repl * 25 // 100)
            r = rng.random()
            if r < 0.75:
                fid += 1
                fees.append((fid, ln[0], "late", right, ln[5]))
            elif r < 0.9:
                fid += 1
                fees.append((fid, ln[0], "late", right + rng.choice([-50, 50, 100]) if right > 100 else right + 50, ln[5]))
        if ln[5] and rng.random() < 0.08:
            fid += 1
            fees.append((fid, ln[0], rng.choice(["damage", "cleaning"]), rng.choice([500, 1000, 2500]), ln[5]))
    rid = 0
    for _ in range(40 if big else 10):
        rid += 1
        start = date(2033, 5, 15) + timedelta(days=rng.randint(0, 60))
        res.append((rid, rng.choice(tools)[0], rng.choice(members)[0], K.iso(start), K.iso(start + timedelta(days=rng.randint(0, 4)))))
    # plant: overlapping, touching and nested reservations on one tool
    for s, e in (("2033-07-01", "2033-07-05"), ("2033-07-05", "2033-07-08"), ("2033-07-09", "2033-07-12"), ("2033-07-02", "2033-07-03")):
        rid += 1
        res.append((rid, tools[2][0], members[rid % len(members)][0], s, e))
    return {"members": members, "categories": cats, "tools": tools, "loans": [tuple(x) for x in loans], "fees": fees, "reservations": res}


DOMAIN = K.Domain("toolshed", "Brindle Street Tool Library", SCHEMA, DOC, gen)
S = K.Spec

LATE_DAYS = "CAST(julianday(l.returned_on) - julianday(l.due_on) AS INTEGER)"

SPECS = [
    S("tools-per-category", 1,
      "How many tools that are still in service (not retired) does each category have? Show every category, including those with none, as category name and count. Order by category name.",
      """SELECT c.name AS category, COUNT(t.tool_id) AS tools FROM categories c LEFT JOIN tools t ON t.cat_id = c.cat_id AND t.retired = 0 GROUP BY c.cat_id ORDER BY c.name;""",
      ["category", "tools"], ordered=True,
      wrong=("SELECT c.name, COUNT(*) FROM categories c JOIN tools t ON t.cat_id = c.cat_id WHERE t.retired = 0 GROUP BY c.cat_id ORDER BY c.name;",)),
    S("overdue-today", 2,
      "Overdue loans as of 2033-06-20: member name, tool label and the number of days the loan is overdue (the loan is still out, due date before today). Most overdue first, ties by member name then tool label.",
      """SELECT m.name AS member, t.label AS tool, CAST(julianday('2033-06-20') - julianday(l.due_on) AS INTEGER) AS days_overdue
FROM loans l JOIN members m ON m.member_id = l.member_id JOIN tools t ON t.tool_id = l.tool_id
WHERE l.returned_on IS NULL AND l.due_on < '2033-06-20' ORDER BY days_overdue DESC, m.name, t.label;""",
      ["member", "tool", "days_overdue"], ordered=True,
      wrong=("""SELECT m.name, t.label, CAST(julianday('2033-06-20') - julianday(l.due_on) AS INTEGER) AS d FROM loans l JOIN members m ON m.member_id = l.member_id JOIN tools t ON t.tool_id = l.tool_id WHERE l.returned_on IS NULL AND l.due_on <= '2033-06-20' ORDER BY d DESC, m.name, t.label;""",)),
    S("never-lent", 2,
      "Which tools in service (not retired) have never been lent out? Show label and category name, ordered by category then label.",
      """SELECT t.label, c.name AS category FROM tools t JOIN categories c ON c.cat_id = t.cat_id
WHERE t.retired = 0 AND NOT EXISTS (SELECT 1 FROM loans l WHERE l.tool_id = t.tool_id) ORDER BY c.name, t.label;""",
      ["label", "category"], ordered=True, allow_empty=True),
    S("late-return-rate", 2,
      "Punctuality per member: among the loans a member has already returned, how many came back late and what percentage is that (1 decimal)? Only members with at least 3 returned loans. "
      "Columns: member name, returned loans, late loans, percentage. Highest percentage first, ties by name.",
      """SELECT m.name AS member, COUNT(*) AS returned, SUM(l.returned_on > l.due_on) AS late, ROUND(100.0 * SUM(l.returned_on > l.due_on) / COUNT(*), 1) AS pct
FROM loans l JOIN members m ON m.member_id = l.member_id WHERE l.returned_on IS NOT NULL
GROUP BY m.member_id HAVING COUNT(*) >= 3 ORDER BY pct DESC, m.name;""",
      ["member", "returned", "late", "pct"], ordered=True,
      wrong=("""SELECT m.name, COUNT(*), SUM(l.returned_on >= l.due_on), ROUND(100.0 * SUM(l.returned_on >= l.due_on) / COUNT(*), 1) AS p FROM loans l JOIN members m ON m.member_id = l.member_id WHERE l.returned_on IS NOT NULL GROUP BY m.member_id HAVING COUNT(*) >= 3 ORDER BY p DESC, m.name;""",)),
    S("fees-by-kind", 2,
      "Total fees per kind in euros (cents divided by 100, shown with 2 decimals) together with how many fees of that kind exist, and the average fee in euros (2 decimals). Order by total descending, then kind.",
      "SELECT kind, COUNT(*) AS n, ROUND(SUM(amount_cents) / 100.0, 2) AS total_eur, ROUND(AVG(amount_cents) / 100.0, 2) AS avg_eur FROM fees GROUP BY kind ORDER BY total_eur DESC, kind;",
      ["kind", "n", "total_eur", "avg_eur"], ordered=True),
    S("top-borrowers-by-tier", 3,
      "Within each membership tier, the most active members of 2033: count loans that went out in 2033 and keep the members whose rank by that count is 1 or 2 (RANK semantics: ties share a rank, so more than two may qualify). "
      "Members with no 2033 loans are not ranked. Columns: tier, member name, loans, rank. Order by tier, rank, name.",
      """WITH c AS (
  SELECT m.tier, m.name, COUNT(*) AS loans FROM loans l JOIN members m ON m.member_id = l.member_id WHERE l.out_on >= '2033-01-01' AND l.out_on < '2034-01-01' GROUP BY m.member_id
), r AS (SELECT *, RANK() OVER (PARTITION BY tier ORDER BY loans DESC) AS rnk FROM c)
SELECT tier, name, loans, rnk FROM r WHERE rnk <= 2 ORDER BY tier, rnk, name;""",
      ["tier", "member", "loans", "rank"], ordered=True,
      wrong=("""WITH c AS (SELECT m.tier, m.name, COUNT(*) AS loans FROM loans l JOIN members m ON m.member_id = l.member_id GROUP BY m.member_id),
r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY tier ORDER BY loans DESC, name) AS rnk FROM c) SELECT tier, name, loans, rnk FROM r WHERE rnk <= 2 ORDER BY tier, rnk, name;""",)),
    S("double-booked", 3,
      "Find double bookings: pairs of reservations for the same tool whose day ranges (both ends included) share at least one day. Report each pair once with the lower reservation id first: tool label, the two reservation ids, "
      "and the number of days they share. Order by tool label, then the first id, then the second.",
      """SELECT t.label AS tool, a.res_id AS res_a, b.res_id AS res_b,
       CAST(julianday(MIN(a.end_on, b.end_on)) - julianday(MAX(a.start_on, b.start_on)) AS INTEGER) + 1 AS shared_days
FROM reservations a JOIN reservations b ON b.tool_id = a.tool_id AND b.res_id > a.res_id AND b.start_on <= a.end_on AND a.start_on <= b.end_on
JOIN tools t ON t.tool_id = a.tool_id ORDER BY t.label, a.res_id, b.res_id;""",
      ["tool", "res_a", "res_b", "shared_days"], ordered=True,
      wrong=("""SELECT t.label, a.res_id, b.res_id, CAST(julianday(MIN(a.end_on, b.end_on)) - julianday(MAX(a.start_on, b.start_on)) AS INTEGER) FROM reservations a JOIN reservations b ON b.tool_id = a.tool_id AND b.res_id > a.res_id AND b.start_on < a.end_on AND a.start_on < b.end_on
JOIN tools t ON t.tool_id = a.tool_id ORDER BY t.label, a.res_id, b.res_id;""",)),
    S("loan-vs-reservation", 3,
      "Loans that collide with somebody else's reservation: a loan occupies its tool from `out_on` until `returned_on` (or `due_on` while still out); a reservation by a different member for the same tool blocks it from `start_on` to `end_on`. "
      "List every (loan, reservation) pair whose days overlap: loan id, reservation id, tool label. Order by loan id, then reservation id.",
      """SELECT l.loan_id, r.res_id, t.label AS tool
FROM loans l JOIN reservations r ON r.tool_id = l.tool_id AND r.member_id <> l.member_id
  AND r.start_on <= COALESCE(l.returned_on, l.due_on) AND l.out_on <= r.end_on
JOIN tools t ON t.tool_id = l.tool_id ORDER BY l.loan_id, r.res_id;""",
      ["loan_id", "res_id", "tool"], ordered=True, allow_empty=True,
      wrong=("""SELECT l.loan_id, r.res_id, t.label FROM loans l JOIN reservations r ON r.tool_id = l.tool_id AND r.start_on <= COALESCE(l.returned_on, l.due_on) AND l.out_on <= r.end_on JOIN tools t ON t.tool_id = l.tool_id ORDER BY l.loan_id, r.res_id;""",)),
    S("june-utilisation", 4,
      "June 2033 utilisation: for each tool in service, the number of days of June 1 to June 30 on which it was out on loan (a loan occupies its tool from `out_on` until `returned_on`, or until `due_on` while still out, both days included; "
      "several loans on the same day count that day once), and the utilisation as a percentage of 30 days, 1 decimal. Tools never out in June show 0. Order by utilisation descending, then label.",
      """WITH RECURSIVE d(day) AS (SELECT '2033-06-01' UNION ALL SELECT date(day, '+1 day') FROM d WHERE day < '2033-06-30'),
used AS (
  SELECT DISTINCT l.tool_id, d.day FROM loans l JOIN d ON d.day BETWEEN l.out_on AND COALESCE(l.returned_on, l.due_on)
)
SELECT t.label, COUNT(u.day) AS days_out, ROUND(100.0 * COUNT(u.day) / 30, 1) AS pct
FROM tools t LEFT JOIN used u ON u.tool_id = t.tool_id WHERE t.retired = 0 GROUP BY t.tool_id ORDER BY pct DESC, t.label;""",
      ["label", "days_out", "pct"], ordered=True,
      wrong=("""SELECT t.label, COALESCE(SUM(MAX(0, CAST(julianday(MIN(COALESCE(l.returned_on, l.due_on), '2033-06-30')) - julianday(MAX(l.out_on, '2033-06-01')) AS INTEGER) + 1)), 0) AS d, 0.0
FROM tools t LEFT JOIN loans l ON l.tool_id = t.tool_id WHERE t.retired = 0 GROUP BY t.tool_id ORDER BY d DESC, t.label;""",)),
    S("monthly-streaks", 4,
      "Loyalty streaks: for each member, the longest run of consecutive calendar months (by loan `out_on`) in which they borrowed at least once. Report members whose longest streak is 3 months or more: member name, streak length, "
      "and the first month of that streak as `YYYY-MM` (if two streaks tie, the earlier one). Order by streak length descending, then name.",
      """WITH m AS (
  SELECT DISTINCT member_id, substr(out_on, 1, 7) AS ym, CAST(substr(out_on, 1, 4) AS INTEGER) * 12 + CAST(substr(out_on, 6, 2) AS INTEGER) AS n FROM loans
), g AS (SELECT member_id, ym, n, n - ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY n) AS grp FROM m),
s AS (SELECT member_id, MIN(ym) AS first_ym, COUNT(*) AS len FROM g GROUP BY member_id, grp),
b AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY len DESC, first_ym) AS rn FROM s)
SELECT mem.name AS member, b.len, b.first_ym FROM b JOIN members mem ON mem.member_id = b.member_id WHERE b.rn = 1 AND b.len >= 3 ORDER BY b.len DESC, mem.name;""",
      ["member", "streak", "first_month"], ordered=True, allow_empty=True,
      wrong=("""SELECT mem.name, COUNT(DISTINCT substr(l.out_on, 1, 7)) AS c, MIN(substr(l.out_on, 1, 7)) FROM loans l JOIN members mem ON mem.member_id = l.member_id GROUP BY l.member_id HAVING c >= 3 ORDER BY c DESC, mem.name;""",)),
    S("wrong-late-fees", 4,
      "Audit the late fees. For every loan returned late, the correct fee is 50 cents per day late, capped at 25% of the tool's replacement cost (cents, rounded down). The recorded fee is the sum of its `late` fee rows (0 if there is none). "
      "List the loans where the recorded fee differs from the correct one: loan id, member name, correct cents, recorded cents. Order by loan id.",
      f"""SELECT l.loan_id, m.name AS member,
       MIN({LATE_DAYS} * 50, t.replacement_cents * 25 / 100) AS correct,
       COALESCE((SELECT SUM(f.amount_cents) FROM fees f WHERE f.loan_id = l.loan_id AND f.kind = 'late'), 0) AS recorded
FROM loans l JOIN members m ON m.member_id = l.member_id JOIN tools t ON t.tool_id = l.tool_id
WHERE l.returned_on > l.due_on
  AND MIN({LATE_DAYS} * 50, t.replacement_cents * 25 / 100) <> COALESCE((SELECT SUM(f.amount_cents) FROM fees f WHERE f.loan_id = l.loan_id AND f.kind = 'late'), 0)
ORDER BY l.loan_id;""",
      ["loan_id", "member", "correct", "recorded"], ordered=True,
      wrong=(f"""SELECT l.loan_id, m.name, {LATE_DAYS} * 50, COALESCE(f.amount_cents, 0) FROM loans l JOIN members m ON m.member_id = l.member_id LEFT JOIN fees f ON f.loan_id = l.loan_id AND f.kind = 'late'
WHERE l.returned_on > l.due_on AND {LATE_DAYS} * 50 <> COALESCE(f.amount_cents, 0) ORDER BY l.loan_id;""",)),
    S("deposit-exhausted", 4,
      "Deposits: each member's fees (all kinds, via their loans) are charged against their deposit in the order they were assessed (ties by fee id). For members whose cumulative fees ever exceed their deposit, "
      "report member name, the date of the fee that first pushed the cumulative total above the deposit, and the cumulative total at that moment in cents. Order by that date, then name.",
      """WITH x AS (
  SELECT m.member_id, m.name, m.deposit_cents, f.assessed_on,
         SUM(f.amount_cents) OVER (PARTITION BY m.member_id ORDER BY f.assessed_on, f.fee_id) AS cum
  FROM fees f JOIN loans l ON l.loan_id = f.loan_id JOIN members m ON m.member_id = l.member_id
), y AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY assessed_on, cum) AS rn FROM x WHERE cum > deposit_cents)
SELECT name AS member, assessed_on, cum FROM y WHERE rn = 1 ORDER BY assessed_on, name;""",
      ["member", "assessed_on", "cumulative_cents"], ordered=True, allow_empty=True,
      wrong=("""SELECT m.name, MIN(f.assessed_on), SUM(f.amount_cents) AS s FROM fees f JOIN loans l ON l.loan_id = f.loan_id JOIN members m ON m.member_id = l.member_id GROUP BY m.member_id HAVING s > m.deposit_cents ORDER BY 2, m.name;""",)),
    S("fix-overdue-list", 2,
      "The overdue report in `query.sql` lists loans that were returned late as well as loans that are still out, and it counts a loan due today as overdue. "
      "Fix it so that it lists only loans that are still out and due before 2033-06-20. Columns: loan id, member name, due date, days overdue. Order by days overdue descending, then loan id.",
      ref="""SELECT l.loan_id, m.name AS member, l.due_on, CAST(julianday('2033-06-20') - julianday(l.due_on) AS INTEGER) AS days_overdue
FROM loans l JOIN members m ON m.member_id = l.member_id WHERE l.returned_on IS NULL AND l.due_on < '2033-06-20' ORDER BY days_overdue DESC, l.loan_id;""",
      cols=["loan_id", "member", "due_on", "days_overdue"], ordered=True, show=False,
      buggy="""SELECT l.loan_id, m.name AS member, l.due_on, CAST(julianday('2033-06-20') - julianday(l.due_on) AS INTEGER) AS days_overdue
FROM loans l JOIN members m ON m.member_id = l.member_id
WHERE l.returned_on > l.due_on OR l.due_on <= '2033-06-20'
ORDER BY days_overdue DESC, l.loan_id;"""),
]


@family("data-tool-library", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL reports on a community tool library: overdue rules, interval overlaps, recursive calendars, month streaks, capped late fees, running deposits")
def tool_library(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)
