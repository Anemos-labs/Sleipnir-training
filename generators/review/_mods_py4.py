"""Slot modules (python), part 4: print-shop invoices, job queue, portal authentication."""
from fx import dd

from ._slots import Bad, Module, Slot, validate_module

# ---------------------------------------------------------------------------------------------------------------------
# print shop invoices
# ---------------------------------------------------------------------------------------------------------------------

INVOICE_TEMPLATE = dd('''
    """Invoice maths for the Alder & Finch print shop. Money is int cents, rates are integer basis points (1/100 of a percent)."""
    import re
    from datetime import date


    @@round@@


    @@line@@


    @@tax@@


    @@coupons@@


    @@deposit@@


    @@number@@


    @@late@@


    @@find@@


    @@money@@
''')

_I_ROUND = dd('''
    def div_round(n, d):
        """n / d rounded half up, for n >= 0 and d > 0."""
        return (2 * n + d) // (2 * d)
''')
_I_LINE = dd('''
    def line_total(qty, unit_cents, discount_bp=0):
        """Quantity times unit price less the line discount, rounded half up to a cent."""
        if qty < 0 or unit_cents < 0 or not 0 <= discount_bp <= 10000:
            raise ValueError("bad invoice line")
        return div_round(qty * unit_cents * (10000 - discount_bp), 10000)
''')
_I_TAX = dd('''
    def invoice_tax(line_totals, rate_bp):
        """VAT is worked out per line (each line's tax rounded half up) and then summed."""
        return sum(div_round(t * rate_bp, 10000) for t in line_totals)
''')
_I_COUPONS = dd('''
    def apply_coupons(subtotal, coupons):
        """Apply ("pct", basis_points) and ("off", cents) coupons one after another; the amount never drops below zero."""
        amount = subtotal
        for kind, value in coupons:
            if kind == "pct":
                amount -= div_round(amount * value, 10000)
            elif kind == "off":
                amount -= value
            else:
                raise ValueError(f"unknown coupon {kind!r}")
            amount = max(amount, 0)
        return amount
''')
_I_DEPOSIT = dd('''
    def deposit_cents(total, pct_bp=3000, minimum=500):
        """Deposit asked up front: pct_bp of the total (half up) but at least `minimum`, and never more than the total."""
        return min(total, max(minimum, div_round(total * pct_bp, 10000)))
''')
_I_NUMBER = dd('''
    def invoice_number(seq, issued):
        """"2025-00042": the issue year and a 5 digit sequence number (1..99999)."""
        if not 1 <= seq <= 99999:
            raise ValueError(f"sequence out of range: {seq}")
        return f"{issued.year}-{seq:05d}"
''')
_I_LATE = dd('''
    def late_fee(due, paid, balance, daily_bp=5, grace_days=3, cap_bp=1000):
        """Late fee: daily_bp of the balance for every day paid after the grace period, capped at cap_bp of the balance."""
        days = (paid - due).days - grace_days
        if days <= 0:
            return 0
        fee = div_round(balance * daily_bp * days, 10000)
        return min(fee, div_round(balance * cap_bp, 10000))
''')
_I_FIND = dd('''
    def find_customers(db, prefix):
        """Customers whose name starts with `prefix` (case-insensitive); % and _ in the prefix are literal."""
        escaped = prefix.replace("\\\\", "\\\\\\\\").replace("%", "\\\\%").replace("_", "\\\\_")
        rows = db.execute("SELECT id, name FROM customers WHERE name LIKE ? ESCAPE '\\\\' ORDER BY name", (escaped + "%",))
        return rows.fetchall()
''')
_I_MONEY = dd('''
    def format_money(cents):
        """£1,234.50; negative amounts are written -£3.05."""
        sign = "-" if cents < 0 else ""
        pounds, pence = divmod(abs(cents), 100)
        return f"{sign}£{pounds:,}.{pence:02d}"
''')

INVOICE = Module(
    name="py-printinvoice", lang="python", path="billing/invoice.py", difficulty=2,
    title="Invoice helpers: line totals, VAT, coupons, deposits, late fees",
    blurb="The `billing` package prices jobs and produces invoices for a small print shop.",
    intro=dd('''
        The shop's invoices were built in a spreadsheet; this PR moves the arithmetic into code so the order form and the
        accounts export agree:
    '''),
    outro="Customer names are typed by staff at the counter. Numbers compared with ten real invoices from last month.",
    new_file=True,
    template=INVOICE_TEMPLATE,
    ctx={"README.md": "# billing\n\nInvoice helpers for the print shop.\n", "billing/__init__.py": '"""Print shop billing."""\n'},
    scenario=dd('''
        import sqlite3
        from datetime import date

        from billing.invoice import (apply_coupons, deposit_cents, find_customers, format_money, invoice_number, invoice_tax, late_fee,
                                     line_total)

        print("lines:", line_total(3, 1999), line_total(7, 333, 1500), line_total(1, 1, 5000), line_total(0, 500), line_total(12, 250, 10000))
        for bad in ((-1, 5, 0), (1, -5, 0), (1, 5, 10001), (1, 5, -1)):
            try:
                line_total(*bad)
                print("accepted", bad)
            except ValueError:
                print("refused", bad)
        totals = [103, 103, 103, 33, 47]
        print("totals:", totals, "tax:", invoice_tax(totals, 2000), "tax on sum:", (sum(totals) * 2000 + 5000) // 10000)
        print("coupons:", apply_coupons(10_000, [("pct", 1000), ("off", 500)]), apply_coupons(10_000, [("off", 500), ("pct", 1000)]),
              apply_coupons(10_000, [("pct", 5000), ("pct", 5000)]), apply_coupons(1_000, [("off", 5_000), ("pct", 1000)]),
              apply_coupons(1_000, [("off", 5_000), ("off", -200)]))
        try:
            apply_coupons(100, [("bogus", 1)])
        except ValueError as exc:
            print("coupon refused:", exc)
        print("deposit:", deposit_cents(1_000), deposit_cents(100_000), deposit_cents(300), deposit_cents(1_667), deposit_cents(500))
        print("numbers:", invoice_number(42, date(2025, 3, 1)), invoice_number(99999, date(2024, 12, 31)), invoice_number(1, date(2026, 1, 1)))
        for seq in (0, 100000):
            try:
                invoice_number(seq, date(2025, 1, 1))
            except ValueError as exc:
                print("number refused:", exc)
        due = date(2025, 3, 1)
        print("late:", [late_fee(due, date(2025, 3, d), 50_000) for d in (1, 4, 5, 6, 20, 31)], late_fee(due, date(2025, 2, 20), 50_000), late_fee(due, date(2026, 3, 1), 50_000),
              late_fee(due, date(2025, 3, 6), 12_345, 7, 0, 50))
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
        db.executemany("INSERT INTO customers (name) VALUES (?)", [("Alder & Sons",), ("alder_works",), ("Alderley Print",), ("100% Paper",), ("Birch",)])
        for p in ("Ald", "alder_", "%", "100%", "_", "x' OR '1'='1", ""):
            print("find", repr(p), [n for _, n in find_customers(db, p)])
        print("money:", format_money(123450), format_money(5), format_money(-305), format_money(0), format_money(-99), format_money(100000000), format_money(-100))
    '''),
    slots=[
        Slot("round", "div_round", _I_ROUND, [
            Bad(_I_ROUND.replace("(2 * n + d) // (2 * d)", "n // d"), "logic", "integer division truncates instead of rounding half up", ("round", "half", "truncat", "//")),
            Bad(_I_ROUND.replace("(2 * n + d) // (2 * d)", "(2 * n + d - 1) // (2 * d)"), "off-by-one", "the `- 1` makes exact halves round down instead of up", ("half", "round", "- 1", "down")),
        ], note="adds `div_round()`, the single rounding rule (half up)"),
        Slot("line", "line_total", _I_LINE, [
            Bad(_I_LINE.replace("not 0 <= discount_bp <= 10000", "not 0 <= discount_bp < 10000"), "off-by-one", "a 100% discount (10000 bp) is refused", ("100%", "10000", "<", "discount")),
            Bad(_I_LINE.replace("(10000 - discount_bp), 10000)", "(10000 - discount_bp) // 10000, 1)"), "logic", "the discount factor is divided with integer division before the multiplication is rounded, so every line with a discount is wrong", ("division", "//", "discount", "round")),
            Bad(_I_LINE.replace("qty < 0 or unit_cents < 0 or ", ""), "validation", "negative quantities and prices are no longer rejected", ("negative", "validation", "qty", "unit_cents")),
        ], note="adds `line_total()` with line discounts"),
        Slot("tax", "invoice_tax", _I_TAX, [
            Bad(_I_TAX.replace("sum(div_round(t * rate_bp, 10000) for t in line_totals)", "div_round(sum(line_totals) * rate_bp, 10000)"), "logic", "tax is computed on the invoice total instead of per line, which differs by cents from the shop's rule (round each line)", ("per line", "sum", "rounding", "total")),
            Bad(_I_TAX.replace("div_round(t * rate_bp, 10000)", "int(t * rate_bp / 10000)"), "api-misuse", "float arithmetic and int() truncate: money must stay in integer maths and round half up", ("float", "int(", "truncat", "round")),
        ], note="adds `invoice_tax()`: VAT per line"),
        Slot("coupons", "apply_coupons", _I_COUPONS, [
            Bad(_I_COUPONS.replace("amount -= div_round(amount * value, 10000)", "amount -= div_round(subtotal * value, 10000)"), "logic", "percentage coupons are taken from the original subtotal instead of the running amount, so stacked coupons over-discount", ("subtotal", "running", "stack", "amount")),
            Bad(_I_COUPONS.replace("        amount = max(amount, 0)\n", ""), "logic", "the amount is no longer clamped at zero after each coupon, so an oversized coupon makes the invoice negative", ("clamp", "max", "negative", "zero")),
            Bad(_I_COUPONS.replace("        amount = max(amount, 0)\n    return amount\n", "    return max(amount, 0)\n"), "logic", "the zero clamp is applied only at the end, so a coupon that overshoots and a later one that adds nothing back give a different result from clamping after each step", ("clamp", "max", "end", "each coupon")),
        ], note="adds `apply_coupons()`: percentage and fixed-amount coupons in order"),
        Slot("deposit", "deposit_cents", _I_DEPOSIT, [
            Bad(_I_DEPOSIT.replace("min(total, max(minimum, div_round(total * pct_bp, 10000)))", "max(minimum, div_round(total * pct_bp, 10000))"), "logic", "the deposit can exceed the total of a small invoice (the `min(total, ...)` cap is gone)", ("min", "cap", "exceed", "total")),
        ], note="adds `deposit_cents()`"),
        Slot("number", "invoice_number", _I_NUMBER, [
            Bad(_I_NUMBER.replace("not 1 <= seq <= 99999", "not 1 <= seq < 99999"), "off-by-one", "sequence 99999 is rejected although it is the last valid number", ("99999", "<", "range", "boundary")),
            Bad(_I_NUMBER.replace("{seq:05d}", "{seq:5d}"), "logic", "the sequence is space padded instead of zero padded (`00042` becomes `   42`)", ("pad", "05d", "zero", "format")),
        ], note="adds `invoice_number()`"),
        Slot("late", "late_fee", _I_LATE, [
            Bad(_I_LATE.replace("(paid - due).days - grace_days", "(paid - due).days - grace_days + 1"), "off-by-one", "the day count is one too high, so the fee already starts on the last day of the grace period", ("grace", "days", "+ 1", "boundary")),
            Bad(_I_LATE.replace("(paid - due).days - grace_days", "(paid - due).days"), "logic", "the grace period is ignored", ("grace", "days", "grace_days")),
            Bad(_I_LATE.replace("return min(fee, div_round(balance * cap_bp, 10000))", "return fee"), "logic", "the cap on the fee is gone", ("cap", "min", "cap_bp")),
        ], note="adds `late_fee()` with a grace period and a cap"),
        Slot("find", "find_customers", _I_FIND, [
            Bad(dd('''
                def find_customers(db, prefix):
                    """Customers whose name starts with `prefix` (case-insensitive); % and _ in the prefix are literal."""
                    rows = db.execute(f"SELECT id, name FROM customers WHERE name LIKE '{prefix}%' ORDER BY name")
                    return rows.fetchall()
            '''), "security", "the prefix is pasted into the SQL text: SQL injection from whatever the clerk (or a pasted order form) contains", ("sql", "injection", "f-string", "parameter")),
            Bad(_I_FIND.replace('''    escaped = prefix.replace("\\\\", "\\\\\\\\").replace("%", "\\\\%").replace("_", "\\\\_")
''', '''    escaped = prefix
'''), "logic", "LIKE wildcards in the prefix are not escaped, so `%` or `_` match everything", ("escape", "wildcard", "like", "%")),
        ], note="adds `find_customers()` for the counter search box"),
        Slot("money", "format_money", _I_MONEY, [
            Bad(_I_MONEY.replace("divmod(abs(cents), 100)", "divmod(cents, 100)"), "logic", "divmod of a negative number floors toward minus infinity, so -305 formats as -£-4.95", ("divmod", "negative", "abs", "floor")),
            Bad(_I_MONEY.replace("{pounds:,}", "{pounds}"), "logic", "no thousands separator", ("separator", "comma", ":,")),
        ], nit=_I_MONEY.replace('sign = "-" if cents < 0 else ""', 'sign = "-" if (cents < 0) else ""'), note="adds `format_money()`"),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# job queue
# ---------------------------------------------------------------------------------------------------------------------

JOBS_TEMPLATE = dd('''
    """Priority job queue with retries, a dead-letter list and de-duplication keys. Lower priority numbers run first."""
    import heapq

    MAX_ATTEMPTS = 3
    BACKOFF = (5, 30, 120)  # seconds to wait before retry 1, 2, 3


    class JobQueue:
        def __init__(self):
            self.heap = []  # (priority, seq, run_at, job_id)
            self.jobs = {}  # live jobs: job_id -> {"priority", "attempts"}
            self.dead = []  # job ids that ran out of attempts
            self.keys = {}  # de-duplication key -> job_id
            self.seq = 0

        @@push@@

        @@pop@@

        @@fail@@

        @@done@@

        @@cancel@@

        @@depth@@
''')

_J_PUSH = dd('''
    def push(self, job_id, priority, run_at, key=None):
        """Queue a job. A key that belongs to a job that is still queued returns that job's id instead."""
        if job_id in self.jobs:
            raise ValueError(f"duplicate job id {job_id}")
        if key is not None:
            if key in self.keys and self.keys[key] in self.jobs:
                return self.keys[key]
            self.keys[key] = job_id
        self.seq += 1
        self.jobs[job_id] = {"priority": priority, "attempts": 0}
        heapq.heappush(self.heap, (priority, self.seq, run_at, job_id))
        return job_id
''')
_J_POP = dd('''
    def pop_ready(self, now):
        """The ready job (run_at <= now) with the lowest priority number, oldest first among equals; None if nothing is ready."""
        held = []
        result = None
        while self.heap:
            prio, seq, run_at, job_id = heapq.heappop(self.heap)
            if job_id not in self.jobs:
                continue  # cancelled or finished
            if run_at > now:
                held.append((prio, seq, run_at, job_id))
                continue
            result = job_id
            break
        for item in held:
            heapq.heappush(self.heap, item)
        return result
''')
_J_FAIL = dd('''
    def fail(self, job_id, now):
        """Record a failed run: retry after BACKOFF, or move to the dead-letter list after MAX_ATTEMPTS failures."""
        job = self.jobs[job_id]
        job["attempts"] += 1
        if job["attempts"] >= MAX_ATTEMPTS:
            del self.jobs[job_id]
            self.dead.append(job_id)
            return "dead"
        self.seq += 1
        heapq.heappush(self.heap, (job["priority"], self.seq, now + BACKOFF[job["attempts"] - 1], job_id))
        return "retry"
''')
_J_DONE = dd('''
    def done(self, job_id):
        """The job finished successfully."""
        del self.jobs[job_id]
''')
_J_CANCEL = dd('''
    def cancel(self, job_id):
        """Cancel a queued job; returns False if there is no such job."""
        return self.jobs.pop(job_id, None) is not None
''')
_J_DEPTH = dd('''
    def depth_by_priority(self):
        """{priority: number of live jobs}, lowest priority first."""
        counts = {}
        for job in self.jobs.values():
            counts[job["priority"]] = counts.get(job["priority"], 0) + 1
        return dict(sorted(counts.items()))
''')

JOBS = Module(
    name="py-jobqueue", lang="python", path="jobs/queue.py", difficulty=3,
    title="Job queue: priorities, retries with backoff, dead letters, de-duplication",
    blurb="The `jobs` package schedules background work (thumbnails, exports, e-mails) for a small web shop.",
    intro="Background work currently runs from cron with no retry logic. This adds an in-process queue:",
    outro="Single process only, no persistence yet. Exercised with the three example jobs in the ticket.",
    new_file=True,
    template=JOBS_TEMPLATE,
    ctx={"README.md": "# jobs\n\nIn-process job queue.\n", "jobs/__init__.py": '"""Background jobs."""\n'},
    scenario=dd('''
        from jobs.queue import JobQueue

        q = JobQueue()
        print("push:", q.push("a", 5, 0), q.push("b", 1, 0), q.push("c", 5, 0), q.push("d", 1, 100), q.push("e", 3, 0, key="k1"))
        print("dedup:", q.push("f", 3, 0, key="k1"))
        try:
            q.push("a", 1, 0)
        except ValueError as exc:
            print("refused:", exc)
        print("depth:", q.depth_by_priority())
        print("pops at 10:", [q.pop_ready(10) for _ in range(4)])
        print("d is not ready at 99:", q.pop_ready(99), "but at 100:", q.pop_ready(100))
        for j in "bacde":
            q.done(j)
        print("depth after done:", q.depth_by_priority())

        q = JobQueue()
        q.push("p", 4, 0)
        q.push("r", 4, 0)
        q.push("s", 4, 0)
        print("cancel:", q.cancel("r"), q.cancel("r"), q.cancel("zzz"))
        print("after cancel:", q.pop_ready(0), q.pop_ready(0), q.pop_ready(0))

        q = JobQueue()
        print("key:", q.push("h", 4, 0, key="k2"), end=" ")
        q.pop_ready(0)
        q.done("h")
        print(q.push("i", 4, 0, key="k2"), end=" ")
        print(q.push("j", 4, 0, key="k2"))
        q.pop_ready(0)
        q.done("i")

        q = JobQueue()
        print("insertion order:", [q.push(x, 7, 0) for x in "zyx"], [q.pop_ready(0) for _ in range(3)])

        q = JobQueue()
        q.push("late", 1, 50)
        q.push("early", 1, 40)
        print("due exactly now:", q.pop_ready(40), q.pop_ready(40), q.pop_ready(50))

        q = JobQueue()
        q.push("m", 1, 0)
        q.push("n", 2, 0)
        print("first run:", q.pop_ready(0), q.pop_ready(0))
        print("n fails:", q.fail("n", 0))
        q.push("o", 1, 5)
        print("at 4:", q.pop_ready(4), "| at 5:", q.pop_ready(5), q.pop_ready(5))
        print("fail again:", q.fail("n", 5), "| due at 35, not before:", q.pop_ready(34), q.pop_ready(35))
        print("third failure:", q.fail("n", 35), "dead:", q.dead, "alive:", sorted(q.jobs))
    '''),
    slots=[
        Slot("push", "JobQueue.push", _J_PUSH, [
            Bad(_J_PUSH.replace("if key in self.keys and self.keys[key] in self.jobs:", "if key in self.keys:"), "logic", "a key stays reserved forever: once a job with that key has finished or been cancelled, new jobs with the same key are swallowed", ("key", "stale", "finished", "dedup")),
            Bad(_J_PUSH.replace("    self.seq += 1\n", ""), "logic", "seq is not incremented, so equal-priority jobs tie on seq and are ordered by run_at/job id instead of insertion order", ("seq", "insertion", "tie", "order")),
            Bad(_J_PUSH.replace('if job_id in self.jobs:', 'if job_id in self.dead:'), "validation", "duplicate ids are only detected among dead jobs, so a live job can be overwritten by a second push with the same id", ("duplicate", "jobs", "overwrite", "dead")),
        ], note="adds `JobQueue.push()` with priorities and de-duplication keys"),
        Slot("pop", "JobQueue.pop_ready", _J_POP, [
            Bad(_J_POP.replace("if run_at > now:", "if run_at >= now:"), "off-by-one", "a job that is due exactly now is treated as not ready", (">=", "due", "now", "boundary")),
            Bad(_J_POP.replace('''    for item in held:
        heapq.heappush(self.heap, item)
''', ""), "logic", "jobs that were skipped because they are not ready yet are never pushed back, so they vanish from the heap", ("held", "push back", "lost", "heappush")),
            Bad(_J_POP.replace('''        if job_id not in self.jobs:
            continue  # cancelled or finished
''', ""), "logic", "heap entries of cancelled or finished jobs are not skipped, so they are returned (and `fail`/`done` then raise KeyError)", ("cancelled", "finished", "stale", "KeyError")),
        ], note="adds `JobQueue.pop_ready()`"),
        Slot("fail", "JobQueue.fail", _J_FAIL, [
            Bad(_J_FAIL.replace('if job["attempts"] >= MAX_ATTEMPTS:', 'if job["attempts"] > MAX_ATTEMPTS:'), "off-by-one", "one attempt too many: the job needs four failures to be dead-lettered (and BACKOFF is indexed out of range)", (">", "MAX_ATTEMPTS", "IndexError", "off by one")),
            Bad(_J_FAIL.replace('now + BACKOFF[job["attempts"] - 1]', 'now + BACKOFF[job["attempts"]]'), "off-by-one", "BACKOFF is indexed by attempts instead of attempts - 1, so the first retry waits 30 s instead of 5 s", ("BACKOFF", "index", "attempts - 1", "first retry")),
            Bad(_J_FAIL.replace('job["priority"], self.seq,', '0, self.seq,'), "logic", "retried jobs are re-queued with priority 0, jumping ahead of everything else", ("priority", "retry", "0", "jump")),
        ], note="adds `JobQueue.fail()`: backoff retries and a dead-letter list"),
        Slot("done", "JobQueue.done", _J_DONE, [
            Bad(_J_DONE.replace("del self.jobs[job_id]", "self.jobs[job_id]['attempts'] = 0"), "logic", "a finished job stays in `jobs`, so it still counts in the depth report and blocks its de-duplication key", ("done", "del", "stays", "jobs")),
        ], note="adds `JobQueue.done()`"),
        Slot("cancel", "JobQueue.cancel", _J_CANCEL, [
            Bad(_J_CANCEL.replace("is not None", "is None"), "logic", "the return value is inverted: True for an unknown job, False for a cancelled one", ("return", "inverted", "is None", "cancel")),
        ], note="adds `JobQueue.cancel()`"),
        Slot("depth", "JobQueue.depth_by_priority", _J_DEPTH, [
            Bad(_J_DEPTH.replace("return dict(sorted(counts.items()))", "return counts"), "logic", "the result is not ordered lowest priority first as documented", ("sorted", "order", "lowest")),
        ], nit=_J_DEPTH.replace('counts[job["priority"]] = counts.get(job["priority"], 0) + 1', 'prio = job["priority"]\n        counts[prio] = counts.get(prio, 0) + 1'), note="adds `depth_by_priority()` for the dashboard"),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# portal authentication
# ---------------------------------------------------------------------------------------------------------------------

AUTH_TEMPLATE = dd('''
    """Accounts for the allotment-society portal: password hashing, login throttling, sessions, reset tokens, safe redirects."""
    import hashlib
    import hmac
    import logging
    import secrets

    log = logging.getLogger("authkit")

    ITERATIONS = 600_000
    MAX_FAILURES = 5
    LOCK_SECONDS = 900
    SESSION_TTL = 3600
    RESET_TTL = 1800


    @@hash@@


    @@check@@


    class Accounts:
        def __init__(self):
            self.users = {}  # name -> stored password hash
            self.failures = {}  # name -> [count, locked_until]
            self.sessions = {}  # token -> (name, expires)
            self.resets = {}  # token -> (name, expires)

        def add_user(self, name, password):
            self.users[name] = hash_password(password)

        @@login@@

        @@session@@

        @@checksession@@

        @@reset@@
    @@redirect@@
''')

_A_HASH = dd('''
    def hash_password(password, salt=None):
        """"pbkdf2$<iterations>$<salt hex>$<hash hex>" with a random 16 byte salt unless one is given."""
        salt = secrets.token_bytes(16) if salt is None else salt
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
        return f"pbkdf2${ITERATIONS}${salt.hex()}${digest.hex()}"
''')
_A_CHECK = dd('''
    def check_password(stored, password):
        """True if `password` matches the stored hash (computed with the iteration count stored in it)."""
        try:
            _, iterations, salt, digest = stored.split("$")
            expected = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        except ValueError:
            return False
        return hmac.compare_digest(expected.hex(), digest)
''')
_A_LOGIN = dd('''
    def login(self, name, password, now):
        """Returns "ok", "locked" or "bad-credentials" (the same answer for an unknown user and a wrong password).
        After MAX_FAILURES wrong passwords the account is locked for LOCK_SECONDS."""
        count, locked_until = self.failures.get(name, [0, 0])
        if now < locked_until:
            return "locked"
        stored = self.users.get(name)
        if stored is None or not check_password(stored, password):
            count += 1
            if count >= MAX_FAILURES:
                self.failures[name] = [0, now + LOCK_SECONDS]
            else:
                self.failures[name] = [count, 0]
            log.warning("failed login for %s", name)
            return "bad-credentials"
        self.failures.pop(name, None)
        return "ok"
''')
_A_SESSION = dd('''
    def open_session(self, name, now):
        """A new random session token valid for SESSION_TTL seconds."""
        token = secrets.token_urlsafe(32)
        self.sessions[token] = (name, now + SESSION_TTL)
        return token
''')
_A_CHECKSESSION = dd('''
    def session_user(self, token, now):
        """The user a session token belongs to, or None if it is unknown or expired."""
        entry = self.sessions.get(token)
        if entry is None or now >= entry[1]:
            return None
        return entry[0]
''')
_A_RESET = dd('''
    def start_reset(self, name, now):
        """A single-use password-reset token valid for RESET_TTL seconds."""
        token = secrets.token_urlsafe(32)
        self.resets[token] = (name, now + RESET_TTL)
        return token

    def finish_reset(self, token, new_password, now):
        """Set a new password if the token is known, unexpired and unused. Returns True on success."""
        entry = self.resets.pop(token, None)
        if entry is None or now >= entry[1]:
            return False
        self.users[entry[0]] = hash_password(new_password)
        self.failures.pop(entry[0], None)
        return True
''')
_A_REDIRECT = dd('''
    def safe_redirect(next_url, default="/"):
        """Where to send the user after login: only a path on this site ("/x/y?z=1"), never another host."""
        if not next_url.startswith("/") or next_url.startswith("//") or "\\\\" in next_url:
            return default
        return next_url
''')

AUTHKIT = Module(
    name="py-portalauth", lang="python", path="authkit/accounts.py", difficulty=4,
    title="Portal accounts: password hashing, login throttling, sessions, reset tokens",
    blurb="The `authkit` package handles member logins for the allotment society's web portal.",
    intro="Members currently share one password. This PR adds real accounts:",
    outro="Login form posts the `next` parameter straight from the query string. Failure counters for names that do not exist are cleaned up by the nightly job. No tests yet; I tried it by hand in the shell.",
    new_file=True,
    template=AUTH_TEMPLATE,
    ctx={"README.md": "# authkit\n\nLogin helpers for the portal.\n", "authkit/__init__.py": '"""Portal authentication."""\n'},
    scenario=dd('''
        import logging
        import sys

        from authkit import accounts
        from authkit.accounts import Accounts, check_password, hash_password, safe_redirect

        logging.basicConfig(stream=sys.stdout, level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
        accounts.ITERATIONS = 1_000  # keep the demonstration fast
        stored = hash_password("correct horse", salt=b"\\x01" * 16)
        print("hash format:", stored.split("$")[:2], len(stored.split("$")[3]))
        print("same salt, same hash:", stored == hash_password("correct horse", salt=b"\\x01" * 16), "different salt:", stored == hash_password("correct horse", salt=b"\\x02" * 16))
        print("check:", check_password(stored, "correct horse"), check_password(stored, "wrong"), check_password("garbage", "x"), check_password("a$b$zz$d", "x"))
        accounts.ITERATIONS = 2_000
        print("old hash after raising the cost:", check_password(stored, "correct horse"))
        acc = Accounts()
        acc.add_user("marta", "tomatoes!")
        T = 1_000_000
        print("unknown user:", acc.login("nobody", "x", T), "wrong password:", acc.login("marta", "x", T))
        print("failures:", [acc.login("marta", "bad", T + i) for i in range(1, 5)])
        print("locked:", acc.login("marta", "tomatoes!", T + 10), acc.login("marta", "tomatoes!", T + 903))
        print("unlocked exactly at the end of the lock:", acc.login("marta", "tomatoes!", T + 904))
        for i in range(3):
            acc.login("marta", "bad", T + 2000 + i)
        acc.login("marta", "tomatoes!", T + 2010)
        print("three more failures after a success:", [acc.login("marta", "bad", T + 2020 + i) for i in range(3)], acc.login("marta", "tomatoes!", T + 2030))
        tok = acc.open_session("marta", T)
        print("session:", len(tok) >= 32, acc.session_user(tok, T + 3599), acc.session_user(tok, T + 3600), acc.session_user("nope", T))
        rt = acc.start_reset("marta", T)
        print("reset:", acc.finish_reset(rt, "newpass", T + 10), "reuse:", acc.finish_reset(rt, "again", T + 11))
        rt2 = acc.start_reset("marta", T)
        print("expired reset:", acc.finish_reset(rt2, "x", T + 1800), "unknown:", acc.finish_reset("zzz", "x", T))
        print("new password works:", acc.login("marta", "newpass", T + 5000), acc.login("marta", "tomatoes!", T + 5001))
        for url in ("/members/plots?id=3", "https://evil.example/x", "//evil.example/x", "/\\\\evil.example", "members", "", "/ok#frag", "javascript:alert(1)"):
            print("redirect", repr(url), "->", safe_redirect(url))
    '''),
    slots=[
        Slot("hash", "hash_password", _A_HASH, [
            Bad(_A_HASH.replace('hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)', 'hashlib.sha256(salt + password.encode())'), "security", "a single fast SHA-256 round is used instead of a slow key-derivation function, which makes offline guessing cheap", ("sha256", "pbkdf2", "slow", "kdf", "iterations")),
            Bad(_A_HASH.replace("salt = secrets.token_bytes(16) if salt is None else salt", 'salt = b"portal-salt" if salt is None else salt'), "security", "the default salt is a constant, so equal passwords hash equally and rainbow tables work", ("salt", "constant", "random", "token_bytes")),
            Bad(_A_HASH.replace("hashlib.pbkdf2_hmac(\"sha256\"", "hashlib.pbkdf2_hmac(\"md5\""), "security", "pbkdf2 is run with md5 as the underlying hash", ("md5", "pbkdf2", "hash")),
        ], note="adds `hash_password()` (PBKDF2-HMAC-SHA256 with a random salt)"),
        Slot("check", "check_password", _A_CHECK, [
            Bad(_A_CHECK.replace("return hmac.compare_digest(expected.hex(), digest)", "return expected.hex() == digest"), "security", "the digest is compared with `==`, which leaks timing information", ("compare_digest", "timing", "==", "constant")),
            Bad(_A_CHECK.replace("int(iterations)", "ITERATIONS"), "logic", "the stored iteration count is ignored, so every hash made before the cost was raised stops verifying", ("iterations", "stored", "ITERATIONS", "cost")),
            Bad(_A_CHECK.replace("    except ValueError:\n        return False\n", "    except ValueError:\n        return True\n"), "security", "a malformed stored hash makes the check succeed (fail-open)", ("fail-open", "except", "True", "malformed")),
        ], note="adds `check_password()`"),
        Slot("login", "Accounts.login", _A_LOGIN, [
            Bad(_A_LOGIN.replace('if now < locked_until:', 'if now <= locked_until:'), "off-by-one", "the account stays locked one second longer than LOCK_SECONDS", ("<=", "locked_until", "boundary", "lock")),
            Bad(_A_LOGIN.replace("if count >= MAX_FAILURES", "if count > MAX_FAILURES"), "off-by-one", "the lock only starts after the sixth wrong password instead of the fifth", (">", "MAX_FAILURES", "fifth", "lock")),
            Bad(dd('''
                def login(self, name, password, now):
                    """Returns "ok", "locked" or "bad-credentials" (the same answer for an unknown user and a wrong password).
                    After MAX_FAILURES wrong passwords the account is locked for LOCK_SECONDS."""
                    count, locked_until = self.failures.get(name, [0, 0])
                    if now < locked_until:
                        return "locked"
                    stored = self.users.get(name)
                    if stored is None:
                        return "unknown-user"
                    if not check_password(stored, password):
                        count += 1
                        if count >= MAX_FAILURES:
                            self.failures[name] = [0, now + LOCK_SECONDS]
                        else:
                            self.failures[name] = [count, 0]
                        log.warning("failed login for %s", name)
                        return "bad-password"
                    self.failures.pop(name, None)
                    return "ok"
            '''), "security", "distinct answers for an unknown user and a wrong password allow user enumeration", ("enumeration", "unknown", "same answer", "bad-password")),
            Bad(_A_LOGIN.replace('log.warning("failed login for %s", name)', 'log.warning("failed login for %s with password %r", name, password)'), "security", "the attempted password is written to the log", ("password", "log", "sensitive", "plaintext")),
            Bad(_A_LOGIN.replace('    self.failures.pop(name, None)\n    return "ok"', '    return "ok"'), "logic", "a successful login does not reset the failure counter, so failures accumulate across days", ("reset", "failures", "counter", "pop")),
        ], note="adds `Accounts.login()` with throttling and a uniform failure answer"),
        Slot("session", "Accounts.open_session", _A_SESSION, [
            Bad(dd('''
                def open_session(self, name, now):
                    """A new random session token valid for SESSION_TTL seconds."""
                    token = f"{name}-{now}"
                    self.sessions[token] = (name, now + SESSION_TTL)
                    return token
            '''), "security", "the session token is predictable (user name and login time) instead of random", ("predictable", "random", "token", "secrets")),
        ], note="adds `Accounts.open_session()`"),
        Slot("checksession", "Accounts.session_user", _A_CHECKSESSION, [
            Bad(_A_CHECKSESSION.replace("now >= entry[1]", "now > entry[1]"), "off-by-one", "a session is valid for one second longer than SESSION_TTL", (">", ">=", "expires", "boundary")),
            Bad(_A_CHECKSESSION.replace("entry is None or now >= entry[1]", "entry is None"), "security", "sessions never expire", ("expire", "ttl", "SESSION_TTL")),
        ], note="adds `Accounts.session_user()`"),
        Slot("reset", "Accounts.finish_reset", _A_RESET, [
            Bad(_A_RESET.replace("self.resets.pop(token, None)", "self.resets.get(token)"), "security", "the reset token is not consumed, so it can be used again until it expires", ("single-use", "pop", "reuse", "consumed")),
            Bad(_A_RESET.replace("    self.failures.pop(entry[0], None)\n", ""), "logic", "a successful reset does not clear the failure counter, so a locked-out member is still locked after resetting", ("failures", "lock", "reset")),
            Bad(_A_RESET.replace("entry is None or now >= entry[1]", "entry is None"), "security", "reset tokens never expire", ("expire", "RESET_TTL", "ttl")),
        ], note="adds single-use password reset tokens"),
        Slot("redirect", "safe_redirect", _A_REDIRECT, [
            Bad(_A_REDIRECT.replace('if not next_url.startswith("/") or next_url.startswith("//") or "\\\\" in next_url:', 'if not next_url.startswith("/"):'), "security", "only the leading slash is checked, so `//evil.example` and `/\\evil.example` (protocol-relative URLs) redirect off the site (open redirect)", ("open redirect", "//", "protocol-relative", "backslash")),
            Bad(_A_REDIRECT.replace('or "\\\\" in next_url', ""), "security", "a backslash after the slash (`/\\evil.example`) is treated as a path by the server but as a host by browsers, so it is an open redirect", ("backslash", "open redirect", "browser")),
        ], note="adds `safe_redirect()` for the login form's `next` parameter"),
    ],
)

MODULES = [INVOICE, JOBS, AUTHKIT]
for _m in MODULES:
    validate_module(_m)
