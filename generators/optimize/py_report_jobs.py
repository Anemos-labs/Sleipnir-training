"""A nightly report job with several stacked bottlenecks (python): N+1 queries, uncached service calls, list scans, quadratic grouping.

Each bottleneck has its own budget (SELECT statements, collaborator calls, scanned list entries, executed lines), so a partial fix is visible in the failure.
"""
from __future__ import annotations

import random
from string import Template

from fx import Task, dd, family, merged, run

from ._kit import PY_ALL, PY_CORRECT, PY_PERF, prove_opt
from ._py_lines import TEXT as LINEMETER

SKINS = [
    dict(pkg="shopreports", what="revenue", T="orders", P="customers", row="order", rows="orders", party="customer", parties="customers", fk="customer_id", qty="qty", price="unit_cents",
         cur="currency", day="day", state="status", paid="paid", other="void", pname="name", pgroup="region", pkey="customer", gkey="region", ckey="orders",
         groups=["north", "south", "east", "west"], blurb="revenue per customer in the home currency"),
    dict(pkg="depotbilling", what="freight", T="shipments", P="depots", row="shipment", rows="shipments", party="depot", parties="depots", fk="depot_id", qty="parcels", price="fee_cents",
         cur="currency", day="day", state="state", paid="invoiced", other="draft", pname="title", pgroup="zone", pkey="depot", gkey="zone", ckey="parcels_billed",
         groups=["coastal", "inland", "alpine", "island"], blurb="freight billed per depot in the home currency"),
    dict(pkg="visitbilling", what="clinic billing", T="visits", P="patients", row="visit", rows="visits", party="patient", parties="patients", fk="patient_id", qty="units", price="tariff_cents",
         cur="currency", day="day", state="state", paid="settled", other="open", pname="full_name", pgroup="ward", pkey="patient", gkey="ward", ckey="visits",
         groups=["A", "B", "C", "D"], blurb="settled treatment cost per patient in the home currency"),
    dict(pkg="metering", what="api usage", T="calls", P="accounts", row="call batch", rows="calls", party="account", parties="accounts", fk="account_id", qty="calls_made", price="price_cents",
         cur="currency", day="day", state="state", paid="billable", other="free", pname="label", pgroup="plan", pkey="account", gkey="plan", ckey="batches",
         groups=["free", "team", "scale", "enterprise"], blurb="billable usage per account in the home currency"),
]

STORE_BASE = '''"""Queries used by the nightly ${what} report."""


def paid_rows(conn):
    """Every ${paid} ${row}: (id, ${fk}, ${qty}, ${price}, ${cur}, ${day}), ordered by id."""
    return conn.execute(
        "SELECT id, ${fk}, ${qty}, ${price}, ${cur}, ${day} FROM ${T} WHERE ${state} = '${paid}' ORDER BY id"
    ).fetchall()


def ${party}_by_id(conn, ${party}_id):
    """(${pname}, ${pgroup}) of one ${party}."""
    return conn.execute("SELECT ${pname}, ${pgroup} FROM ${P} WHERE id = ?", (${party}_id,)).fetchone()
'''

STORE_BULK = '''

def all_${parties}(conn):
    """{id: (${pname}, ${pgroup})} for every ${party}, in one query."""
    return {pid: (name, grp) for pid, name, grp in conn.execute("SELECT id, ${pname}, ${pgroup} FROM ${P}")}
'''

JOBKIT = '''"""Hidden helpers: seeded database, counting collaborators, reference implementation."""
import random
import sqlite3

SCHEMA = """
CREATE TABLE ${P} (id INTEGER PRIMARY KEY, ${pname} TEXT NOT NULL, ${pgroup} TEXT NOT NULL);
CREATE TABLE ${T} (id INTEGER PRIMARY KEY, ${fk} INTEGER NOT NULL, ${qty} INTEGER NOT NULL, ${price} INTEGER NOT NULL,
                   ${cur} TEXT NOT NULL, ${day} INTEGER NOT NULL, ${state} TEXT NOT NULL);
"""
CURRENCIES = ["EUR", "USD", "GBP", "JPY", "CHF"]
GROUPS = ${groups}


class FakeRates:
    """Stands in for the remote exchange-rate service."""

    def __init__(self):
        self.calls = 0

    def lookup(self, currency, day):
        self.calls += 1
        return 8000 + (sum(map(ord, currency)) * 37 + day * 11) % 2500


class ScanList(list):
    """A list that counts how many entries membership tests and iteration touch."""

    scanned = 0

    def __contains__(self, item):
        try:
            idx = self.index(item)
        except ValueError:
            self.scanned += len(self)
            return False
        self.scanned += idx + 1
        return True

    def __iter__(self):
        for x in list.__iter__(self):
            self.scanned += 1
            yield x

    def __getitem__(self, i):
        self.scanned += 1
        return list.__getitem__(self, i)


def make_db(seed, n_parties, n_rows, n_cur, n_days, blocked_share=0.3):
    rng = random.Random(seed)
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    ids = rng.sample(range(100, 100 + 4 * max(n_parties, 1)), n_parties)
    for pid in ids:
        conn.execute("INSERT INTO ${P} VALUES (?, ?, ?)", (pid, "n%d" % pid, rng.choice(GROUPS)))
    rows = []
    for rid in range(1, n_rows + 1):
        rows.append((rid, rng.choice(ids), rng.randint(1, 9), rng.randint(50, 900), rng.choice(CURRENCIES[:n_cur]), rng.randint(1, n_days),
                     rng.choice(["${paid}"] * 4 + ["${other}"])))
    conn.executemany("INSERT INTO ${T} VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    blocked = [pid for pid in ids if rng.random() < blocked_share] + [rng.randint(5000, 9000) for _ in range(max(2, n_parties // 10))]
    rng.shuffle(blocked)
    return conn, blocked


def reference(conn, rates, blocked):
    skip = set(blocked)
    known = {pid: (n, g) for pid, n, g in conn.execute("SELECT id, ${pname}, ${pgroup} FROM ${P}")}
    out = {}
    for rid, owner, q, p, c, d in conn.execute("SELECT id, ${fk}, ${qty}, ${price}, ${cur}, ${day} FROM ${T} WHERE ${state} = '${paid}' ORDER BY id"):
        if owner in skip:
            continue
        entry = out.setdefault(owner, {"${pkey}": owner, "name": known[owner][0], "${gkey}": known[owner][1], "${ckey}": 0, "total": 0})
        entry["${ckey}"] += 1
        entry["total"] += q * p * rates.lookup(c, d) // 10000
    return sorted(out.values(), key=lambda e: (-e["total"], e["${pkey}"]))


def distinct_pairs(conn):
    return len(conn.execute("SELECT DISTINCT ${cur}, ${day} FROM ${T} WHERE ${state} = '${paid}'").fetchall())
'''

CORRECT = '''import unittest

from jobkit import FakeRates, ScanList, make_db, reference
from ${pkg}.jobs import build_report


class CorrectnessTests(unittest.TestCase):
    def check(self, seed, parties, rows, cur, days, share=0.3):
        conn, blocked = make_db(seed, parties, rows, cur, days, share)
        got = build_report(conn, FakeRates(), list(blocked))
        self.assertEqual(got, reference(conn, FakeRates(), blocked))
        return got

    def test_matches_the_reference_on_assorted_databases(self):
        for seed, parties, rows, cur, days in [(1, 5, 40, 2, 3), (2, 12, 150, 3, 10), (3, 30, 220, 5, 6), (4, 1, 9, 1, 1), (5, 8, 60, 4, 20)]:
            self.check(seed, parties, rows, cur, days)

    def test_empty_and_fully_blocked_cases(self):
        self.assertEqual(self.check(6, 0, 0, 1, 1), [])
        self.assertEqual(self.check(7, 6, 0, 2, 2), [])
        conn, blocked = make_db(8, 6, 50, 2, 4)
        everyone = [r[0] for r in conn.execute("SELECT id FROM ${P}")]
        self.assertEqual(build_report(conn, FakeRates(), everyone), [])

    def test_nothing_blocked(self):
        self.assertTrue(self.check(9, 10, 100, 3, 5, share=0.0))

    def test_works_with_any_sequence_for_blocked(self):
        conn, blocked = make_db(10, 9, 80, 3, 7)
        want = reference(conn, FakeRates(), blocked)
        self.assertEqual(build_report(conn, FakeRates(), tuple(blocked)), want)
        self.assertEqual(build_report(conn, FakeRates(), ScanList(blocked)), want)
'''

PERF = '''import importlib
import os
import unittest

from jobkit import FakeRates, ScanList, distinct_pairs, make_db, reference
from linemeter import BudgetExceeded, LineMeter
from ${pkg}.jobs import build_report

PACKAGE_DIR = os.path.dirname(os.path.abspath(importlib.import_module("${pkg}").__file__))
PARTIES, ROWS, CURRENCIES, DAYS = ${parties_n}, ${rows_n}, 4, 30
LINE_LIMIT = ${line_limit}


class PerformanceTests(unittest.TestCase):
    def database(self):
        return make_db(${seed}, PARTIES, ROWS, CURRENCIES, DAYS)

    def test_queries_are_not_issued_per_row(self):
        conn, blocked = self.database()
        statements = []
        conn.set_trace_callback(statements.append)
        build_report(conn, FakeRates(), list(blocked))
        selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
        self.assertLessEqual(len(selects), 5, "PERF: %d SELECT statements for %d rows (budget 5): the database is queried once per row" % (len(selects), ROWS))

    def test_rate_service_calls_are_not_repeated(self):
        conn, blocked = self.database()
        rates = FakeRates()
        build_report(conn, rates, list(blocked))
        distinct = distinct_pairs(conn)
        self.assertLessEqual(rates.calls, distinct, "PERF: %d rate lookups for %d distinct (currency, day) pairs: the same lookups are repeated" % (rates.calls, distinct))

    def test_blocked_list_is_not_scanned_per_row(self):
        conn, blocked = self.database()
        scan = ScanList(blocked)
        build_report(conn, FakeRates(), scan)
        budget = 10 * (len(blocked) + ROWS)
        self.assertLessEqual(scan.scanned, budget, "PERF: %d entries of the blocked list were scanned (budget %d): membership is tested with a linear scan" % (scan.scanned, budget))

    def test_total_work_is_not_quadratic(self):
        conn, blocked = self.database()
        meter = LineMeter(PACKAGE_DIR, budget=2 * LINE_LIMIT)
        try:
            with meter:
                build_report(conn, FakeRates(), list(blocked))
        except BudgetExceeded:
            self.fail("PERF: still running after %d executed lines of ${pkg} code (budget %d): some step does work proportional to rows times ${parties}" % (meter.lines, LINE_LIMIT))
        self.assertLessEqual(meter.lines, LINE_LIMIT, "PERF: %d executed lines of ${pkg} code (budget %d): some step does too much work" % (meter.lines, LINE_LIMIT))

    def test_result_on_the_big_database_is_right(self):
        conn, blocked = self.database()
        self.assertEqual(build_report(conn, FakeRates(), list(blocked)), reference(conn, FakeRates(), blocked))
'''

CALIB = '''import importlib, os, sys
sys.path.insert(0, "tests")
from jobkit import FakeRates, make_db
from linemeter import LineMeter
from ${pkg}.jobs import build_report
root = os.path.dirname(os.path.abspath(importlib.import_module("${pkg}").__file__))
conn, blocked = make_db(${seed}, ${parties_n}, ${rows_n}, 4, 30)
m = LineMeter(root)
with m:
    build_report(conn, FakeRates(), list(blocked))
print("LINES", m.lines)
'''

BASIC = '''import sqlite3
import unittest

from ${pkg}.jobs import build_report


class StubRates:
    def lookup(self, currency, day):
        return 8000 + (sum(map(ord, currency)) * 37 + day * 11) % 2500


def database():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
${schema}
    """)
    return conn


class BasicTests(unittest.TestCase):
    def test_small_example(self):
        conn = database()
${inserts}
        self.assertEqual(build_report(conn, StubRates(), ${blocked!r}), ${expected!r})

    def test_empty_database(self):
        self.assertEqual(build_report(database(), StubRates(), []), [])


if __name__ == "__main__":
    unittest.main()
'''

NAMES = {"queries": "test_queries_are_not_issued_per_row", "rates": "test_rate_service_calls_are_not_repeated", "blocked": "test_blocked_list_is_not_scanned_per_row",
         "lines": "test_total_work_is_not_quadratic"}


def jobs_source(sel, sk):
    """build_report with the selected bottlenecks in their slow form and the others already efficient."""
    pre, check, fetch, rate, group = [], [], [], [], []
    if "queries" in sel:
        fetch = ["name, group = store.${party}_by_id(conn, owner)"]
    else:
        pre.append("known = store.all_${parties}(conn)")
        fetch = ["name, group = known[owner]"]
    if "blocked" in sel:
        check = ["if owner in blocked:", "    continue"]
    else:
        pre.append("blocked_ids = set(blocked)")
        check = ["if owner in blocked_ids:", "    continue"]
    if "rates" in sel:
        rate = ["rate = rates.lookup(cur, day)"]
    else:
        pre.append("rate_cache = {}")
        rate = ["key = (cur, day)", "if key not in rate_cache:", "    rate_cache[key] = rates.lookup(cur, day)", "rate = rate_cache[key]"]
    if "lines" in sel:
        group = ["people = {}", "for owner, name, group, _ in kept:", "    people[owner] = (name, group)", "report = []", "for owner, (name, group) in people.items():", "    total = 0",
                 "    count = 0", "    for other, _, _, amount in kept:", "        if other == owner:", "            total += amount", "            count += 1",
                 '    report.append({"${pkey}": owner, "name": name, "${gkey}": group, "${ckey}": count, "total": total})']
    else:
        group = ["grouped = {}", "for owner, name, group, amount in kept:", "    entry = grouped.get(owner)", "    if entry is None:",
                 '        entry = grouped[owner] = {"${pkey}": owner, "name": name, "${gkey}": group, "${ckey}": 0, "total": 0}', '    entry["${ckey}"] += 1',
                 '    entry["total"] += amount', "report = list(grouped.values())"]

    def ind(lines, n):
        return "\n".join(" " * n + ln for ln in lines)

    parts = ['"""Nightly ${what} report."""', "from . import store", "", "",
             "def build_report(conn, rates, blocked):", '    """${blurb^}: one dict per ${party}, biggest total first (see README)."""']
    if pre:
        parts.append(ind(pre, 4))
    parts.append("    kept = []")
    parts.append("    for _id, owner, qty, price, cur, day in store.paid_rows(conn):")
    parts.append(ind(check + fetch + rate, 8))
    parts.append("        kept.append((owner, name, group, qty * price * rate // 10000))")
    parts.append(ind(group, 4))
    parts.append('    report.sort(key=lambda item: (-item["total"], item["${pkey}"]))')
    parts.append("    return report")
    text = "\n".join(parts) + "\n"
    text = text.replace("${blurb^}", sk["blurb"][0].upper() + sk["blurb"][1:])
    return Template(text).substitute(sk)


PROMPTS = [
    "The nightly {what} report (`build_report` in `{pkg}/jobs.py`) has gone from seconds to minutes as the tables grew. {symptom} Make it scale without changing what it returns. "
    "There is no stopwatch in the check: it measures database round trips (SELECT statements), calls to the rate service, how much of the `blocked` list gets scanned, and the "
    "Python lines executed inside `{pkg}`, each against a budget that a sensible implementation meets with plenty of room. Look at the whole path, `store.py` included. "
    "The README has the contract.",
    "perf ticket: `{pkg}.jobs.build_report` is far too slow on a real database ({rows_n:,} rows, {parties_n} {parties}). {symptom} Fix what is slow and keep the output byte-for-byte "
    "identical (same dicts, same order). The grader counts SELECTs, `rates.lookup` calls, entries scanned in `blocked` and executed Python lines in the package; there are "
    "budgets for each, so one fix alone will probably not be enough.",
    "Could you make `build_report` in `{pkg}/jobs.py` fast? The report is {blurb}. {symptom} The results have to stay exactly as they are today. "
    "I will run it against a database with thousands of rows and compare database round trips, remote rate lookups, linear scans of `blocked` and total Python work with fixed budgets.",
]
SYMPTOMS = [
    "On the production database it is slow in more than one way, not just one.",
    "Profiling shows the time is spread over several different things rather than one hot spot.",
    "Nobody has looked at it since the first version; the code is simple, but it does a lot of work per row.",
]


def make_start(sk, sel, jobs_text):
    store = Template(STORE_BASE + ("" if "queries" in sel else STORE_BULK)).substitute(sk)
    readme = Template(dd('''
        # ${pkg}

        `jobs.build_report(conn, rates, blocked)` produces the nightly ${what} report: ${blurb}.

        * `conn` is a SQLite connection with the tables `${P}(id, ${pname}, ${pgroup})` and `${T}(id, ${fk}, ${qty}, ${price}, ${cur}, ${day}, ${state})`.
        * Only ${row}s with `${state} = '${paid}'` count, and their `${fk}` must not be in `blocked` (a list of ids; it can hold thousands of entries, some of them unknown).
        * `rates.lookup(currency, day)` returns the exchange rate in basis points of the home currency (10000 = parity). It talks to a remote service, so calls are expensive.
        * The amount of one row is `${qty} * ${price} * rate // 10000`.
        * The result is a list with one dict per ${party}: `${pkey}` (the id), `name`, `${gkey}`, `${ckey}` (number of ${row}s counted) and `total`, sorted by `total`
          descending, then by `${pkey}` ascending. ${Parties} without counted ${row}s do not appear.

        The tables hold many thousands of rows in production.
        ''')).substitute({**sk, "Parties": sk["parties"].capitalize()}) + "\n"
    return {f"{sk['pkg']}/__init__.py": "", f"{sk['pkg']}/store.py": store, f"{sk['pkg']}/jobs.py": jobs_text, "README.md": readme}


@family("optimize-py-report-jobs", category="optimize", lang="python", kind="feature", n=16,
        summary="a report job with 2-4 stacked bottlenecks (N+1 queries, repeated service calls, list scans, quadratic grouping), each with its own counted budget")
def gen(rng, n):
    plan = [2, 2, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4]
    rng.shuffle(plan)
    allb = ["queries", "rates", "blocked", "lines"]
    for i in range(n):
        k = plan[i % len(plan)]
        sk = SKINS[i % len(SKINS)]
        sel = sorted(rng.sample(allb, k), key=allb.index)
        parties_n, rows_n = rng.choice([(300, 1500), (260, 1400), (320, 1600)])
        seed = 3000 + i
        jobs_start = jobs_source(sel, sk)
        start_files = make_start(sk, sel, jobs_start)
        sol_files = {f"{sk['pkg']}/jobs.py": jobs_source([], sk)}
        if "queries" in sel:
            sol_files[f"{sk['pkg']}/store.py"] = Template(STORE_BASE + STORE_BULK).substitute(sk)
        kit = Template(JOBKIT).substitute(sk | {"groups": repr(sk["groups"])})
        ns = {}
        exec(kit, ns)
        # visible example from a small seeded database
        conn, blocked = ns["make_db"](seed, 6, 14, 2, 3)
        schema_lines = [ln for ln in ns["SCHEMA"].strip().splitlines()]
        ptable = [list(r) for r in conn.execute(f"SELECT * FROM {sk['P']} ORDER BY id")]
        mtable = [list(r) for r in conn.execute(f"SELECT * FROM {sk['T']} ORDER BY id")]
        inserts = "\n".join([f"        conn.executemany(\"INSERT INTO {sk['P']} VALUES (?, ?, ?)\", {ptable!r})",
                             f"        conn.executemany(\"INSERT INTO {sk['T']} VALUES (?, ?, ?, ?, ?, ?, ?)\", {mtable!r})"])

        class _R:
            def lookup(self, c, d):
                return 8000 + (sum(map(ord, c)) * 37 + d * 11) % 2500

        shown_blocked = blocked[:2]
        expected = ns["reference"](conn, _R(), shown_blocked)
        basic = Template(BASIC.replace("${blocked!r}", repr(shown_blocked)).replace("${expected!r}", repr(expected))).substitute(
            pkg=sk["pkg"], schema="\n".join("    " + ln for ln in schema_lines), inserts=inserts)
        start = {**start_files, "tests/test_basic.py": basic}
        # line budget: three times the reference, rounded; checked against the reference run below
        calib = Template(CALIB).substitute(pkg=sk["pkg"], seed=seed, parties_n=parties_n, rows_n=rows_n)
        base = {"tests/jobkit.py": kit, "tests/linemeter.py": LINEMETER}
        probe = run(merged(start, base, sol_files, {"calib.py": calib}), "python3 calib.py", timeout=180)
        if "LINES" not in probe.out:
            raise RuntimeError(f"report-jobs-{i}: calibration failed:\n{probe.out[-1500:]}")
        ref_lines = int(probe.out.split("LINES")[1].split()[0])
        line_limit = (ref_lines * 4 // 1000 + 1) * 1000
        sub = dict(pkg=sk["pkg"], parties=sk["parties"], parties_n=parties_n, rows_n=rows_n, seed=seed, line_limit=line_limit, P=sk["P"])
        hidden = {**base, "tests/test_correct_jobs.py": Template(CORRECT).substitute(sub), "tests/test_perf_jobs.py": Template(PERF).substitute(sub)}
        prove_opt(f"report-jobs-{i}", start, hidden, sol_files, PY_CORRECT, PY_PERF, PY_ALL, timeout=240)
        # each budget must fail on the start exactly when its bottleneck is present
        for key, test in NAMES.items():
            r = run(merged(start, hidden), f"python3 -m unittest discover -s tests -p 'test_perf*.py' -k {test}", timeout=240)
            if (key in sel) == r.ok:
                raise RuntimeError(f"report-jobs-{i}: budget {key!r} {'passes' if r.ok else 'fails'} on the start although the bottleneck is {'present' if key in sel else 'absent'}:\n{r.out[-1200:]}")
        prompt = rng.choice(PROMPTS).format(what=sk["what"], pkg=sk["pkg"], symptom=rng.choice(SYMPTOMS), rows_n=rows_n, parties_n=parties_n, parties=sk["parties"], blurb=sk["blurb"])
        yield Task(slug=f"{i + 1:02d}-{sk['pkg']}-{'-'.join(sel)}", prompt=prompt, difficulty=k + 1, start=start, hidden=hidden, solution=sol_files, verify=PY_ALL, timeout_s=300,
                   tags=["n-plus-one", "caching", "hash-lookup", "complexity", "multi-bottleneck"], notes={"bottlenecks": sel, "rows": rows_n, "line_limit": line_limit})
