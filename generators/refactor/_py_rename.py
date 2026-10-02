"""Small python projects for rename refactors: modules, harnesses (old API), case generators and rename symbols."""
from __future__ import annotations

# ---------------------------------------------------------------------------------------------------------------------
# stockroom: warehouse stock lines with unit conversion and discounts
# ---------------------------------------------------------------------------------------------------------------------
STOCKROOM = {
    "stockroom/__init__.py": "",
    "stockroom/units.py": '''"""Unit conversion for stock quantities (everything is stored in grams)."""

FACTORS = {"g": 1, "kg": 1000, "oz": 28, "lb": 454}


def to_base(qty, unit):
    """Convert a quantity of the given unit to grams."""
    if unit not in FACTORS:
        raise ValueError("unknown unit: %s" % unit)
    return int(round(qty * FACTORS[unit]))


def pretty(grams):
    """Human readable weight."""
    if grams >= 1000:
        return "%.2f kg" % (grams / 1000)
    return "%d g" % grams
''',
    "stockroom/items.py": '''"""Stock items."""
from . import units


class StockItem:
    """A line of stock: sku, quantity in grams and a price per kilogram in cents."""

    def __init__(self, sku, qty, unit, price_cents):
        self.sku = sku
        self.grams = units.to_base(qty, unit)
        self.price_cents = price_cents

    def worth(self):
        """Value of the line in cents."""
        return self.grams * self.price_cents // 1000

    def label(self):
        return "%s (%s)" % (self.sku, units.pretty(self.grams))


def make_item(row):
    """Build an item from a (sku, qty, unit, price_cents) row."""
    sku, qty, unit, price = row
    return StockItem(sku, qty, unit, price)
''',
    "stockroom/pricing.py": '''"""Pricing rules."""
from .items import StockItem
from .units import to_base


def bulk_discount(grams):
    """Percent off for big lines."""
    if grams >= to_base(10, "kg"):
        return 10
    if grams >= to_base(2, "kg"):
        return 5
    return 0


def calc_price(item, extra_discount=0):
    """Price of an item in cents after the bulk discount and an optional extra discount in percent."""
    if not isinstance(item, StockItem):
        raise TypeError("expected a StockItem")
    pct = min(100, bulk_discount(item.grams) + extra_discount)
    return item.worth() * (100 - pct) // 100
''',
    "stockroom/report.py": '''"""Text reports."""
import stockroom.units as u

from .items import StockItem
from .pricing import calc_price


def render(items, with_header=True):
    """Fixed-width table of the items with their prices."""
    lines = ["sku                qty      price"] if with_header else []
    for it in items:
        lines.append("%-14s %8s %9d" % (it.sku, u.pretty(it.grams), calc_price(it)))
    return "\\n".join(lines)


def summarize(items):
    """Counts and money totals for a list of items."""
    value = sum(it.worth() for it in items if isinstance(it, StockItem))
    priced = sum(calc_price(it) for it in items)
    return {"count": len(items), "value": value, "after_discount": priced, "saved": value - priced, "weight": u.pretty(sum(it.grams for it in items))}
''',
    "stockroom/cli.py": '''"""Tiny command line front end: sku:qty:unit:price arguments, optional --bare."""
from . import report
from .items import make_item
from .pricing import calc_price


def parse_row(text):
    """'A1:2.5:kg:900' -> ('A1', 2.5, 'kg', 900)."""
    sku, qty, unit, price = text.split(":")
    return (sku, float(qty), unit, int(price))


def main(argv):
    """Build the report for the given rows."""
    bare = "--bare" in argv
    items = [make_item(parse_row(a)) for a in argv if not a.startswith("--")]
    text = report.render(items, with_header=not bare)
    cheapest = min(items, key=calc_price).sku if items else None
    return {"text": text, "summary": report.summarize(items), "cheapest": cheapest}
''',
}

STOCKROOM_HARNESS = '''from stockroom import cli, items as items_mod, pricing, report, units
from stockroom.items import StockItem


def run_case(case):
    its = [items_mod.make_item(tuple(r)) for r in case["rows"]]
    direct = StockItem("Z9", case["qty"], case["unit"], case["price"])
    return {
        "labels": [i.label() for i in its],
        "worth": [i.worth() for i in its],
        "direct": [direct.worth(), pricing.calc_price(direct, case["extra"])],
        "prices": [pricing.calc_price(i) for i in its],
        "render": [report.render(its), report.render(its, with_header=False)],
        "summary": report.summarize(its),
        "cli": cli.main(case["argv"]),
        "pretty": units.pretty(case["grams"]),
        "base": units.to_base(case["qty"], case["unit"]),
        "isitem": isinstance(direct, items_mod.StockItem),
    }
'''


def stockroom_cases(rng, n):
    cases = []
    for k in range(n):
        rows = []
        for j in range(rng.randint(0, 4)):
            rows.append([rng.choice(["A", "B", "C", "D", "E"]) + str(rng.randint(10, 99)), rng.choice([0.5, 1, 2.5, 3, 12, 40]), rng.choice(["g", "kg", "oz", "lb"]), rng.randint(100, 2500)])
        unit = rng.choice(["g", "kg", "oz", "lb"] * 6 + ["stone"])
        argv = ["%s:%s:%s:%d" % (r[0], r[1], r[2], r[3]) for r in rows]
        if rng.random() < 0.4:
            argv.append("--bare")
        cases.append({"rows": rows, "qty": rng.choice([1, 2, 3, 5, 11]), "unit": unit, "price": rng.randint(100, 3000), "extra": rng.choice([0, 5, 20, 95]),
                      "argv": argv, "grams": rng.choice([0, 15, 999, 1000, 2500, 12345])})
    return cases


STOCKROOM_SYMBOLS = {
    "function": dict(old="calc_price", news=["price_for", "quote_cents"], home="stockroom/pricing.py", noun="the function",
                     probe='from stockroom.items import make_item\nfrom stockroom.pricing import calc_price\ncalc_price(make_item(("A", 3, "kg", 200)), 5)'),
    "class": dict(old="StockItem", news=["Item", "StockLine"], home="stockroom/items.py", noun="the class",
                  probe='from stockroom.items import StockItem\nStockItem("A", 3, "kg", 200)'),
    "method": dict(old="worth", news=["value_cents", "line_value"], home="stockroom/items.py", cls="StockItem", noun="the method",
                   probe='from stockroom.items import make_item\nmake_item(("A", 3, "kg", 200)).worth()'),
    "module": dict(old="units", news=["measures", "weights"], home="stockroom/units.py", noun="the module",
                   probe='import stockroom.units as u\nu.to_base(2, "kg")'),
    "param": dict(old="with_header", news=["include_header", "header"], home="stockroom/report.py", fn="render", noun="the keyword argument",
                  probe='from stockroom.items import make_item\nfrom stockroom.report import render\nrender([make_item(("A", 3, "kg", 200))], with_header=False)'),
}

# ---------------------------------------------------------------------------------------------------------------------
# libdesk: library loans and fines
# ---------------------------------------------------------------------------------------------------------------------
LIBDESK = {
    "libdesk/__init__.py": "",
    "libdesk/shelfcode.py": '''"""Shelf codes: nine digits plus a check digit (weights 3, 1, 2 repeating, modulo 7)."""

WEIGHTS = (3, 1, 2)


def normalize(text):
    """Strip dashes and spaces."""
    return "".join(ch for ch in text if ch not in "- ")


def check_digit(body):
    """Check digit for the first nine digits of a shelf code."""
    total = sum(WEIGHTS[i % 3] * int(ch) for i, ch in enumerate(body[:9]))
    return str(total % 7)


def is_valid(text):
    """True for ten digits whose last one is the right check digit."""
    code = normalize(text)
    return len(code) == 10 and code.isdigit() and check_digit(code[:9]) == code[9]
''',
    "libdesk/catalog.py": '''"""The book catalogue."""
from . import shelfcode


class Book:
    """A title with a number of copies on the shelf."""

    def __init__(self, code, title, copies=1):
        self.code = shelfcode.normalize(code)
        self.title = title
        self.copies = copies

    def available_label(self):
        return "%s [%d]" % (self.title, self.copies)


def find_book(books, code):
    """The book with this code (any formatting), or None."""
    code = shelfcode.normalize(code)
    for book in books:
        if book.code == code:
            return book
    return None
''',
    "libdesk/loans.py": '''"""Loans and due dates."""
from datetime import timedelta

from .catalog import Book

LOAN_DAYS = 21


class LoanRecord:
    """A book on loan to a member."""

    def __init__(self, book, member, start):
        if not isinstance(book, Book):
            raise TypeError("book must be a Book")
        self.book = book
        self.member = member
        self.start = start

    def due(self):
        """Last day without a fine."""
        return self.start + timedelta(days=LOAN_DAYS)

    def days_late(self, today):
        """Whole days past the due date (0 when on time)."""
        return max(0, (today - self.due()).days)


def lend(book, member, start):
    """Lend a copy of the book; raises ValueError when none is left."""
    if book.copies <= 0:
        raise ValueError("no copies left")
    book.copies -= 1
    return LoanRecord(book, member, start)
''',
    "libdesk/fines.py": '''"""Late fees."""
from .loans import LoanRecord


def calc_fine(record, today, waive=False):
    """Fine in cents: 25 per late day, capped at 1000; zero when waived."""
    if not isinstance(record, LoanRecord):
        raise TypeError("expected a LoanRecord")
    if waive:
        return 0
    return min(1000, 25 * record.days_late(today))
''',
    "libdesk/desk.py": '''"""Front desk operations."""
from . import shelfcode
from .catalog import find_book
from .fines import calc_fine
from .loans import LoanRecord, lend


def checkout(books, code, member, start):
    """Lend the book with this code; raises KeyError for unknown or malformed codes."""
    if not shelfcode.is_valid(code):
        raise KeyError(code)
    book = find_book(books, code)
    if book is None:
        raise KeyError(code)
    return lend(book, member, start)


def close_account(records, today, waive_all=False):
    """Total fines of the records: (cents, titles of late books)."""
    total, late = 0, []
    for rec in records:
        if not isinstance(rec, LoanRecord):
            continue
        fine = calc_fine(rec, today, waive=waive_all)
        if fine:
            late.append(rec.book.title)
        total += fine
    return total, late
''',
}

LIBDESK_HARNESS = '''from datetime import date

from libdesk import catalog, desk, fines, shelfcode, loans


def run_case(case):
    books = [catalog.Book(c, t, n) for c, t, n in case["books"]]
    start = date(*case["start"])
    today = date(*case["today"])
    records = [desk.checkout(books, code, member, start) for code, member in case["loans"]]
    return {
        "valid": [shelfcode.is_valid(b[0]) for b in case["books"]],
        "digit": shelfcode.check_digit(case["body"]),
        "late": [r.days_late(today) for r in records],
        "fines": [fines.calc_fine(r, today) for r in records],
        "waived": [fines.calc_fine(r, today, waive=True) for r in records],
        "close": desk.close_account(records, today),
        "close_waived": desk.close_account(records, today, waive_all=case["wipe"]),
        "labels": [b.available_label() for b in books],
        "isloan": [isinstance(r, loans.LoanRecord) for r in records],
    }
'''


def _shelf_code(body):
    total = sum((3, 1, 2)[i % 3] * int(ch) for i, ch in enumerate(body))
    return body + str(total % 7)


def libdesk_cases(rng, n):
    cases = []
    for k in range(n):
        books = []
        for j in range(rng.randint(1, 3)):
            body = "".join(str(rng.randint(0, 9)) for _ in range(9))
            code = _shelf_code(body)
            if rng.random() < 0.15:
                code = code[:-1] + ("0" if code[-1] != "0" else "1")
            books.append([code[:1] + "-" + code[1:4] + "-" + code[4:] if rng.random() < 0.5 else code, rng.choice(["Dune", "Emma", "Ulysses", "Kim", "Walden"]), rng.randint(1, 3)])
        loans = []
        for j in range(rng.randint(0, 3)):
            b = books[rng.randrange(len(books))]
            loans.append([b[0] if rng.random() < 0.9 else "9-999-99999-9", rng.choice(["ann", "bo", "cy"])])
        cases.append({"books": books, "loans": loans, "start": [2024, rng.randint(1, 6), rng.randint(1, 28)], "today": [2024, rng.randint(6, 12), rng.randint(1, 28)],
                      "body": "".join(str(rng.randint(0, 9)) for _ in range(9)), "wipe": rng.random() < 0.5})
    return cases


LIBDESK_SYMBOLS = {
    "function": dict(old="calc_fine", news=["late_fee", "fine_for"], home="libdesk/fines.py", noun="the function",
                     probe='from datetime import date\nfrom libdesk.catalog import Book\nfrom libdesk.loans import lend\nfrom libdesk.fines import calc_fine\n'
                           'rec = lend(Book("0306406155", "T", 1), "m", date(2024, 1, 1))\ncalc_fine(rec, date(2024, 3, 1))'),
    "class": dict(old="LoanRecord", news=["Loan", "Checkout"], home="libdesk/loans.py", noun="the class",
                  probe='from datetime import date\nfrom libdesk.catalog import Book\nfrom libdesk.loans import LoanRecord\nLoanRecord(Book("0306406155", "T", 1), "m", date(2024, 1, 1))'),
    "method": dict(old="days_late", news=["overdue_days", "days_overdue"], home="libdesk/loans.py", cls="LoanRecord", noun="the method",
                   probe='from datetime import date\nfrom libdesk.catalog import Book\nfrom libdesk.loans import lend\n'
                         'lend(Book("0306406155", "T", 1), "m", date(2024, 1, 1)).days_late(date(2024, 3, 1))'),
    "module": dict(old="shelfcode", news=["labelcodes", "stockmarks"], home="libdesk/shelfcode.py", noun="the module",
                   probe='import libdesk.shelfcode as m\nm.normalize("0-306-40615-5")'),
    "param": dict(old="waive", news=["excused", "forgive"], home="libdesk/fines.py", fn="calc_fine", noun="the keyword argument",
                  probe='from datetime import date\nfrom libdesk.catalog import Book\nfrom libdesk.loans import lend\nfrom libdesk.fines import calc_fine\n'
                        'rec = lend(Book("0306406155", "T", 1), "m", date(2024, 1, 1))\ncalc_fine(rec, date(2024, 3, 1), waive=True)'),
}

# ---------------------------------------------------------------------------------------------------------------------
# tempo: time entries and invoice lines
# ---------------------------------------------------------------------------------------------------------------------
TEMPO = {
    "tempo/__init__.py": "",
    "tempo/spans.py": '''"""Parsing and formatting of time spans such as 1h30m."""
import re

_PART = re.compile(r"(\\d+)([hm])")


def parse_span(text):
    """Minutes in a span such as '1h30m', '45m' or '2h'."""
    text = text.strip().lower()
    parts = _PART.findall(text)
    if not parts or "".join(n + u for n, u in parts) != text:
        raise ValueError("bad span: %r" % text)
    return sum(int(n) * (60 if u == "h" else 1) for n, u in parts)


def format_span(total):
    """Inverse of parse_span: 90 -> '1h30m'."""
    h, m = divmod(total, 60)
    return ("%dh" % h if h else "") + ("%dm" % m if m or not h else "")
''',
    "tempo/entries.py": '''"""Time entries."""
from . import spans


class TimeEntry:
    """Time booked on a task at an hourly rate (cents)."""

    def __init__(self, task, span, rate_cents=0):
        self.task = task
        self.span = span
        self.rate_cents = rate_cents

    def minutes(self):
        """Duration in minutes."""
        return spans.parse_span(self.span)

    def pretty(self):
        return "%s %s" % (self.task, spans.format_span(self.minutes()))


def load_entries(rows):
    """Entries from (task, span, rate_cents) rows."""
    return [TimeEntry(task, span, rate) for task, span, rate in rows]
''',
    "tempo/billing.py": '''"""Billing."""
from .entries import TimeEntry


def hourly_cost(entry):
    """Cost of an entry in cents, rounded half up per entry."""
    if not isinstance(entry, TimeEntry):
        raise TypeError("expected a TimeEntry")
    return (entry.minutes() * entry.rate_cents + 30) // 60


def invoice_lines(entries, group=True):
    """(task, minutes, cents) lines; same-named tasks are merged when group is true."""
    if not group:
        return [(e.task, e.minutes(), hourly_cost(e)) for e in entries]
    merged = {}
    for e in entries:
        minutes, cents = merged.get(e.task, (0, 0))
        merged[e.task] = (minutes + e.minutes(), cents + hourly_cost(e))
    return [(t, m, c) for t, (m, c) in sorted(merged.items())]
''',
    "tempo/app.py": '''"""Small driver used by the command line and the tests."""
from . import spans
from .billing import hourly_cost, invoice_lines
from .entries import TimeEntry, load_entries


def summarize(rows, combine=True):
    """Invoice lines, the total in cents and the booked time."""
    entries = load_entries(rows)
    lines = invoice_lines(entries, group=combine)
    return {
        "lines": lines,
        "total": sum(hourly_cost(e) for e in entries if isinstance(e, TimeEntry)),
        "time": spans.format_span(sum(e.minutes() for e in entries)),
    }
''',
}

TEMPO_HARNESS = '''from tempo import app, billing, entries, spans


def run_case(case):
    rows = [tuple(r) for r in case["rows"]]
    es = entries.load_entries(rows)
    return {
        "minutes": [e.minutes() for e in es],
        "pretty": [e.pretty() for e in es],
        "costs": [billing.hourly_cost(e) for e in es],
        "grouped": billing.invoice_lines(es),
        "flat": billing.invoice_lines(es, group=False),
        "summary": app.summarize(rows, combine=case["combine"]),
        "parse": spans.parse_span(case["span"]),
        "isentry": [isinstance(e, entries.TimeEntry) for e in es],
    }
'''


def tempo_cases(rng, n):
    cases = []
    spans_ = ["1h30m", "45m", "2h", "10m", "3h5m", "1h", "90m", "0m"]
    for k in range(n):
        rows = [[rng.choice(["design", "review", "build", "deploy"]), rng.choice(spans_), rng.choice([0, 4500, 6000, 8250])] for _ in range(rng.randint(0, 5))]
        cases.append({"rows": rows, "combine": rng.random() < 0.5, "span": rng.choice(spans_ * 3 + ["1h 30m", "abc", "", "5"])})
    return cases


TEMPO_SYMBOLS = {
    "function": dict(old="hourly_cost", news=["entry_cost", "cost_cents"], home="tempo/billing.py", noun="the function",
                     probe='from tempo.entries import TimeEntry\nfrom tempo.billing import hourly_cost\nhourly_cost(TimeEntry("a", "1h30m", 6000))'),
    "class": dict(old="TimeEntry", news=["Entry", "Booking"], home="tempo/entries.py", noun="the class",
                  probe='from tempo.entries import TimeEntry\nTimeEntry("a", "1h30m", 6000)'),
    "method": dict(old="minutes", news=["duration_minutes", "length_min"], home="tempo/entries.py", cls="TimeEntry", noun="the method",
                   probe='from tempo.entries import load_entries\nload_entries([("a", "1h30m", 6000)])[0].minutes()'),
    "module": dict(old="spans", news=["durations", "timespan"], home="tempo/spans.py", noun="the module",
                   probe='import tempo.spans as s\ns.parse_span("1h30m")'),
    "param": dict(old="group", news=["merge_tasks", "collapse"], home="tempo/billing.py", fn="invoice_lines", noun="the keyword argument",
                  probe='from tempo.entries import load_entries\nfrom tempo.billing import invoice_lines\ninvoice_lines(load_entries([("a", "1h", 100)]), group=False)'),
}

SKELETONS = {
    "stockroom": dict(pkg="stockroom", files=STOCKROOM, harness=STOCKROOM_HARNESS, cases=stockroom_cases, symbols=STOCKROOM_SYMBOLS),
    "libdesk": dict(pkg="libdesk", files=LIBDESK, harness=LIBDESK_HARNESS, cases=libdesk_cases, symbols=LIBDESK_SYMBOLS),
    "tempo": dict(pkg="tempo", files=TEMPO, harness=TEMPO_HARNESS, cases=tempo_cases, symbols=TEMPO_SYMBOLS),
}
