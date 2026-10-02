"""SQL script tasks on the tool library: migrations, backfills, repairs, archiving, triggers and views. The agent writes migration.sql; the checker runs it on fresh databases and compares data and structure."""
from fx import family
from generators.data import _sqlkit as K
from generators.data.sql_toolshed import DOMAIN

S = K.ScriptSpec

SPECS = [
    S("add-loan-counter", 2,
      "Add a column `loan_count` (INTEGER, NOT NULL, default 0) to `members` and fill it with the number of loans each member has made so far (all loans, returned or not). Put the statements in `migration.sql`.",
      ref="""ALTER TABLE members ADD COLUMN loan_count INTEGER NOT NULL DEFAULT 0;
UPDATE members SET loan_count = (SELECT COUNT(*) FROM loans l WHERE l.member_id = members.member_id);""",
      checks=["SELECT member_id, loan_count FROM members"], struct=["columns:members"],
      wrong=("ALTER TABLE members ADD COLUMN loan_count INTEGER NOT NULL DEFAULT 0;", """ALTER TABLE members ADD COLUMN loan_count INTEGER NOT NULL DEFAULT 0;
UPDATE members SET loan_count = (SELECT COUNT(*) FROM loans l WHERE l.member_id = members.member_id AND l.returned_on IS NOT NULL);"""),
      show_sql="SELECT member_id, name, loan_count FROM members ORDER BY member_id"),
    S("rename-label", 2,
      "The column `tools.label` is confusing: rename it to `name` without losing data or the uniqueness of the values. Write `migration.sql`.",
      ref="ALTER TABLE tools RENAME COLUMN label TO name;",
      checks=["SELECT tool_id, name FROM tools"], struct=["columns:tools", "indexes:tools"],
      wrong=("ALTER TABLE tools ADD COLUMN name TEXT; UPDATE tools SET name = label;",)),
    S("split-deposits", 3,
      "Deposits deserve a table of their own. Create `deposits (member_id INTEGER PRIMARY KEY REFERENCES members(member_id), amount_cents INTEGER NOT NULL)`, copy every member's deposit into it, "
      "and remove the column `deposit_cents` from `members`. Nothing else may change. Write `migration.sql`.",
      ref="""CREATE TABLE deposits (member_id INTEGER PRIMARY KEY REFERENCES members(member_id), amount_cents INTEGER NOT NULL);
INSERT INTO deposits (member_id, amount_cents) SELECT member_id, deposit_cents FROM members;
ALTER TABLE members DROP COLUMN deposit_cents;""",
      checks=["SELECT member_id, amount_cents FROM deposits", "SELECT member_id, name, joined_on, tier FROM members"], struct=["tables", "columns:members", "columns:deposits", "fks:deposits"],
      wrong=("""CREATE TABLE deposits (member_id INTEGER PRIMARY KEY, amount_cents INTEGER NOT NULL);
INSERT INTO deposits SELECT member_id, deposit_cents FROM members;
ALTER TABLE members DROP COLUMN deposit_cents;""",),
      buggy="""CREATE TABLE deposits (member_id INTEGER PRIMARY KEY REFERENCES members(member_id), amount_cents INTEGER NOT NULL);
ALTER TABLE members DROP COLUMN deposit_cents;
INSERT INTO deposits (member_id, amount_cents) SELECT member_id, deposit_cents FROM members;"""),
    S("merge-categories", 3,
      "The library no longer wants separate `saws` and `drills` categories. Create one category called `power-tools`, move every tool of the two old categories to it, and delete the two old categories. All other categories and tools stay as they are. Write `migration.sql`.",
      ref="""INSERT INTO categories (name) VALUES ('power-tools');
UPDATE tools SET cat_id = (SELECT cat_id FROM categories WHERE name = 'power-tools') WHERE cat_id IN (SELECT cat_id FROM categories WHERE name IN ('saws', 'drills'));
DELETE FROM categories WHERE name IN ('saws', 'drills');""",
      checks=["SELECT t.tool_id, c.name FROM tools t JOIN categories c ON c.cat_id = t.cat_id", "SELECT name FROM categories"],
      wrong=("""UPDATE categories SET name = 'power-tools' WHERE name = 'saws';
DELETE FROM categories WHERE name = 'drills';""", """INSERT INTO categories (name) VALUES ('power-tools');
DELETE FROM categories WHERE name IN ('saws', 'drills');""")),
    S("retired-to-date", 3,
      "Replace the flag `tools.retired` by a date: add `retired_on` (TEXT, NULL for tools in service), set it to `2033-06-20` for every tool that is retired today, and drop the `retired` column. Write `migration.sql`.",
      ref="""ALTER TABLE tools ADD COLUMN retired_on TEXT;
UPDATE tools SET retired_on = '2033-06-20' WHERE retired = 1;
ALTER TABLE tools DROP COLUMN retired;""",
      checks=["SELECT tool_id, retired_on FROM tools"], struct=["columns:tools"],
      wrong=("""ALTER TABLE tools ADD COLUMN retired_on TEXT;
UPDATE tools SET retired_on = '2033-06-20';
ALTER TABLE tools DROP COLUMN retired;""",)),
    S("repair-late-fees", 4,
      "Repair the late fees. A loan returned after its due date must have exactly one `late` fee of 50 cents per day late, capped at 25% of the tool's replacement cost (integer division, rounded down), assessed on the return date. "
      "Remove wrong late fees (including duplicates and fees on loans that were not late) and add the missing ones. Fees of other kinds are untouched. Write `migration.sql`.",
      ref="""DELETE FROM fees WHERE kind = 'late';
INSERT INTO fees (loan_id, kind, amount_cents, assessed_on)
SELECT l.loan_id, 'late', MIN(CAST(julianday(l.returned_on) - julianday(l.due_on) AS INTEGER) * 50, t.replacement_cents * 25 / 100), l.returned_on
FROM loans l JOIN tools t ON t.tool_id = l.tool_id WHERE l.returned_on > l.due_on;""",
      checks=["SELECT loan_id, kind, amount_cents, assessed_on FROM fees"],
      wrong=("""DELETE FROM fees WHERE kind = 'late';
INSERT INTO fees (loan_id, kind, amount_cents, assessed_on) SELECT l.loan_id, 'late', CAST(julianday(l.returned_on) - julianday(l.due_on) AS INTEGER) * 50, l.returned_on FROM loans l WHERE l.returned_on > l.due_on;""",)),
    S("archive-old-loans", 4,
      "Archive history: create `loans_archive` and `fees_archive` with the same columns as `loans` and `fees` (plain tables, no constraints needed), copy into them every loan that was returned before 2033-05-01 together with its fees, "
      "and delete those loans and fees from the live tables. Loans still out or returned later stay. The database must stay consistent (no fee may point at a missing loan). Write `migration.sql`.",
      ref="""CREATE TABLE loans_archive AS SELECT * FROM loans WHERE returned_on < '2033-05-01';
CREATE TABLE fees_archive AS SELECT * FROM fees WHERE loan_id IN (SELECT loan_id FROM loans_archive);
DELETE FROM fees WHERE loan_id IN (SELECT loan_id FROM loans_archive);
DELETE FROM loans WHERE loan_id IN (SELECT loan_id FROM loans_archive);""",
      checks=["SELECT * FROM loans", "SELECT * FROM fees", "SELECT * FROM loans_archive", "SELECT * FROM fees_archive"], struct=["tables"],
      wrong=("""CREATE TABLE loans_archive AS SELECT * FROM loans WHERE returned_on < '2033-05-01';
CREATE TABLE fees_archive AS SELECT * FROM fees WHERE loan_id IN (SELECT loan_id FROM loans_archive);
DELETE FROM loans WHERE loan_id IN (SELECT loan_id FROM loans_archive);""",)),
    S("fee-audit-trigger", 4,
      "Keep an audit trail of fee changes. Create `fee_audit (audit_id INTEGER PRIMARY KEY AUTOINCREMENT, fee_id INTEGER NOT NULL, old_cents INTEGER NOT NULL, new_cents INTEGER NOT NULL)` and a trigger that appends a row "
      "whenever the `amount_cents` of a fee is updated to a *different* value. Updates that leave the amount unchanged must not be logged. Write `migration.sql`.",
      ref="""CREATE TABLE fee_audit (audit_id INTEGER PRIMARY KEY AUTOINCREMENT, fee_id INTEGER NOT NULL, old_cents INTEGER NOT NULL, new_cents INTEGER NOT NULL);
CREATE TRIGGER fees_amount_audit AFTER UPDATE OF amount_cents ON fees WHEN OLD.amount_cents <> NEW.amount_cents
BEGIN INSERT INTO fee_audit (fee_id, old_cents, new_cents) VALUES (OLD.fee_id, OLD.amount_cents, NEW.amount_cents); END;""",
      post=[{"sql": "UPDATE fees SET amount_cents = amount_cents + 100 WHERE fee_id % 3 = 0; UPDATE fees SET amount_cents = amount_cents WHERE fee_id % 3 = 1; UPDATE fees SET amount_cents = 5 WHERE fee_id % 3 = 2;", "script": True}],
      checks=["SELECT fee_id, old_cents, new_cents FROM fee_audit", "SELECT fee_id, amount_cents FROM fees"], struct=["tables", "triggers"],
      wrong=("""CREATE TABLE fee_audit (audit_id INTEGER PRIMARY KEY AUTOINCREMENT, fee_id INTEGER NOT NULL, old_cents INTEGER NOT NULL, new_cents INTEGER NOT NULL);
CREATE TRIGGER fees_amount_audit AFTER UPDATE OF amount_cents ON fees BEGIN INSERT INTO fee_audit (fee_id, old_cents, new_cents) VALUES (OLD.fee_id, OLD.amount_cents, NEW.amount_cents); END;""",)),
    S("no-retired-loans", 4,
      "Stop loans of retired tools at the database level: add a trigger that makes an `INSERT` into `loans` fail (with `RAISE(ABORT, ...)`) when the tool is retired (`retired = 1`). Inserts for tools in service must keep working. Existing rows are not touched. Write `migration.sql`.",
      ref="""CREATE TRIGGER loans_no_retired BEFORE INSERT ON loans WHEN (SELECT retired FROM tools WHERE tool_id = NEW.tool_id) = 1
BEGIN SELECT RAISE(ABORT, 'tool is retired'); END;""",
      post=[{"sql": "INSERT INTO loans (tool_id, member_id, out_on, due_on) SELECT tool_id, 1, '2033-06-20', '2033-06-27' FROM tools WHERE retired = 1 ORDER BY tool_id LIMIT 1"},
            {"sql": "INSERT INTO loans (tool_id, member_id, out_on, due_on) SELECT tool_id, 1, '2033-06-20', '2033-06-27' FROM tools WHERE retired = 0 ORDER BY tool_id LIMIT 1"}],
      checks=["SELECT COUNT(*) FROM loans", "SELECT name FROM sqlite_master WHERE type = 'trigger'"], struct=["triggers"],
      wrong=("""CREATE TRIGGER loans_no_retired BEFORE INSERT ON loans BEGIN SELECT RAISE(ABORT, 'no loans'); END;""",)),
    S("overdue-view", 2,
      "Create a view `overdue_loans` for the daily report: one row per loan that is still out and due before 2033-06-20, with the columns `loan_id`, `member_id`, `tool_id`, `due_on` and `days_overdue` (whole days between the due date and 2033-06-20). Write `migration.sql`.",
      ref="""CREATE VIEW overdue_loans AS
SELECT loan_id, member_id, tool_id, due_on, CAST(julianday('2033-06-20') - julianday(due_on) AS INTEGER) AS days_overdue
FROM loans WHERE returned_on IS NULL AND due_on < '2033-06-20';""",
      checks=["SELECT loan_id, member_id, tool_id, due_on, days_overdue FROM overdue_loans"], struct=["views", "tables"],
      wrong=("""CREATE VIEW overdue_loans AS SELECT loan_id, member_id, tool_id, due_on, CAST(julianday('2033-06-20') - julianday(due_on) AS INTEGER) AS days_overdue FROM loans WHERE returned_on IS NULL AND due_on <= '2033-06-20';""",)),
    S("seed-categories", 3,
      "Make sure the categories `electrical` and `masonry` exist. The script will be run more than once (on every deploy), so running it again must not fail and must not create duplicates; categories that exist already stay untouched. Write `migration.sql`.",
      ref="INSERT OR IGNORE INTO categories (name) VALUES ('electrical'), ('masonry');",
      twice=True, checks=["SELECT name FROM categories"],
      wrong=("INSERT INTO categories (name) VALUES ('electrical'), ('masonry');", "INSERT INTO categories (name) SELECT 'electrical'; INSERT INTO categories (name) SELECT 'masonry' WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = 'masonry');")),
    S("member-loan-numbers", 4,
      "Number every member's loans in the order they went out: add `member_seq` (INTEGER) to `loans` and set it to 1 for a member's first loan, 2 for the second, and so on, ordered by `out_on`, ties by `loan_id`. Write `migration.sql`.",
      ref="""ALTER TABLE loans ADD COLUMN member_seq INTEGER;
UPDATE loans SET member_seq = (SELECT n FROM (SELECT loan_id, ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY out_on, loan_id) AS n FROM loans) x WHERE x.loan_id = loans.loan_id);""",
      checks=["SELECT loan_id, member_seq FROM loans"], struct=["columns:loans"],
      wrong=("""ALTER TABLE loans ADD COLUMN member_seq INTEGER;
UPDATE loans SET member_seq = (SELECT COUNT(*) FROM loans l2 WHERE l2.member_id = loans.member_id AND l2.out_on < loans.out_on) + 1;""",)),
    S("balance-table", 4,
      "Create a table `member_balance (member_id INTEGER PRIMARY KEY, fees_cents INTEGER NOT NULL, deposit_left_cents INTEGER NOT NULL)` with one row per member: the sum of all fees charged on the member's loans (0 if none) "
      "and the deposit minus those fees (it can be negative). Write `migration.sql`.",
      ref="""CREATE TABLE member_balance (member_id INTEGER PRIMARY KEY, fees_cents INTEGER NOT NULL, deposit_left_cents INTEGER NOT NULL);
INSERT INTO member_balance (member_id, fees_cents, deposit_left_cents)
SELECT m.member_id, COALESCE(f.s, 0), m.deposit_cents - COALESCE(f.s, 0)
FROM members m LEFT JOIN (SELECT l.member_id, SUM(fe.amount_cents) AS s FROM fees fe JOIN loans l ON l.loan_id = fe.loan_id GROUP BY l.member_id) f ON f.member_id = m.member_id;""",
      checks=["SELECT member_id, fees_cents, deposit_left_cents FROM member_balance"], struct=["tables", "columns:member_balance"],
      wrong=("""CREATE TABLE member_balance (member_id INTEGER PRIMARY KEY, fees_cents INTEGER NOT NULL, deposit_left_cents INTEGER NOT NULL);
INSERT INTO member_balance SELECT l.member_id, SUM(fe.amount_cents), m.deposit_cents - SUM(fe.amount_cents) FROM fees fe JOIN loans l ON l.loan_id = fe.loan_id JOIN members m ON m.member_id = l.member_id GROUP BY l.member_id;""",)),
]


@family("data-tool-library-migrations", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL migration and repair scripts on a tool-library database: backfills, column moves, merges, archiving, triggers, views, idempotent seeding")
def tool_library_migrations(rng, n):
    return K.script_tasks(DOMAIN, SPECS, rng, n)
