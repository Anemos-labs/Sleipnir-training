"""God-module domains for the split-module family: each domain is a set of areas that live in one big util module."""
from __future__ import annotations

from dataclasses import dataclass
from string import Template
from typing import Callable


@dataclass
class Area:
    name: str
    code: str  # python source with $params
    deps: tuple = ()
    optional: bool = False
    cases: Callable | None = None  # (rng, params) -> list of [fname, args]


@dataclass
class God:
    key: str
    package: str
    doc: str
    topic: str
    areas: list
    params: Callable  # rng -> dict
    app: str  # source of app.py (uses `from <package>.util import ...`)
    app_fn: str
    app_cases: Callable  # (rng, params, areas) -> list of ["app", args]


# ----------------------------------------------------------------------------------------------------------------
# bakery
# ----------------------------------------------------------------------------------------------------------------
BAKERY_PARAMS = lambda rng: {  # noqa: E731
    "bulk_qty": rng.choice([6, 10, 12]), "bulk_pct": rng.choice([5, 8, 10]), "food_tax": rng.choice([5, 7, 9]), "other_tax": rng.choice([16, 19, 21]),
    "voucher_pct": rng.choice([10, 15, 20]), "low": rng.choice([3, 5, 8]), "p1": rng.randrange(250, 450, 10), "p2": rng.randrange(450, 800, 10),
    "p3": rng.randrange(80, 250, 5), "p4": rng.randrange(900, 1600, 10), "min_voucher": rng.choice([800, 1000, 1500]),
}

BAKERY_MONEY = '''
CURRENCY = "EUR"
SYMBOLS = {"EUR": "E", "USD": "$$"}


def to_cents(text):
    """Parse '12.50' (or '12') into whole cents."""
    text = text.strip()
    if not text or text.count(".") > 1:
        raise ValueError("not an amount: %r" % text)
    whole, _, frac = text.partition(".")
    if not (whole.isdigit() and (frac == "" or frac.isdigit())) or len(frac) > 2:
        raise ValueError("not an amount: %r" % text)
    return int(whole) * 100 + int((frac + "00")[:2])


def fmt_money(cents):
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return "%s%s%d.%02d" % (sign, SYMBOLS[CURRENCY], cents // 100, cents % 100)


def round_half_up(numerator, denominator):
    return (2 * numerator + denominator) // (2 * denominator)
'''

BAKERY_CATALOG = '''
PRODUCTS = {
    "sourdough": {"price": $p2, "unit": "loaf", "tax": "food"},
    "croissant": {"price": $p1, "unit": "piece", "tax": "food"},
    "rye roll": {"price": $p3, "unit": "piece", "tax": "food"},
    "gift box": {"price": $p4, "unit": "box", "tax": "other"},
}
TAX_RATES = {"food": $food_tax, "other": $other_tax}


def get_product(name):
    try:
        return PRODUCTS[name]
    except KeyError:
        raise ValueError("unknown product: %s" % name) from None


def list_products(tax=None):
    return sorted(n for n, p in PRODUCTS.items() if tax is None or p["tax"] == tax)
'''

BAKERY_PRICING = '''
def line_total(name, qty):
    """Price of one basket line, with the bulk discount."""
    if qty <= 0:
        raise ValueError("quantity must be positive")
    base = get_product(name)["price"] * qty
    if qty >= $bulk_qty:
        base -= round_half_up(base * $bulk_pct, 100)
    return base


def basket_total(lines):
    """Net, tax and gross for a list of (name, qty) lines."""
    net = 0
    tax = 0
    for name, qty in lines:
        amount = line_total(name, qty)
        net += amount
        tax += round_half_up(amount * TAX_RATES[get_product(name)["tax"]], 100)
    return {"net": net, "tax": tax, "gross": net + tax}


def apply_voucher(gross, code):
    """Take a percentage off the gross amount for a valid voucher."""
    if code is None:
        return gross
    if code != "WELCOME":
        raise ValueError("invalid voucher")
    if gross < $min_voucher:
        raise ValueError("voucher needs a larger basket")
    return gross - round_half_up(gross * $voucher_pct, 100)
'''

BAKERY_STOCK = '''
class Stock:
    """Counts of what is on the shelf."""

    def __init__(self, counts):
        self.counts = dict(counts)

    def reserve(self, name, qty):
        get_product(name)
        if self.counts.get(name, 0) < qty:
            raise ValueError("not enough %s" % name)
        self.counts[name] -= qty

    def release(self, name, qty):
        get_product(name)
        self.counts[name] = self.counts.get(name, 0) + qty

    def low_items(self):
        return sorted(n for n, c in self.counts.items() if c < $low)
'''

BAKERY_RECEIPT = '''
def render_receipt(lines, voucher=None):
    out = []
    for name, qty in lines:
        out.append("%-12s x%-3d %s" % (name, qty, fmt_money(line_total(name, qty))))
    totals = basket_total(lines)
    out.append("tax %s" % fmt_money(totals["tax"]))
    final = apply_voucher(totals["gross"], voucher)
    if final != totals["gross"]:
        out.append("voucher -%s" % fmt_money(totals["gross"] - final))
    out.append("TOTAL %s" % fmt_money(final))
    return "\\n".join(out)
'''


def _bakery_cases(area):
    def f(rng, p):
        names = ["sourdough", "croissant", "rye roll", "gift box"]
        if area == "money":
            return ([["to_cents", [rng.choice(["12.50", "3", "0.05", "7.5", "oops", "1.234", " 9.99 "])]] for _ in range(5)]
                    + [["fmt_money", [rng.choice([0, 5, 1250, -330, 100000])]] for _ in range(3)]
                    + [["round_half_up", [rng.randrange(0, 500), rng.choice([3, 7, 100])]] for _ in range(3)])
        if area == "catalog":
            return [["get_product", [rng.choice(names + ["bagel"])]] for _ in range(3)] + [["list_products", []], ["list_products", ["food"]]]
        if area == "pricing":
            return ([["line_total", [rng.choice(names), rng.choice([1, 5, 6, 10, 12, 0])]] for _ in range(6)]
                    + [["basket_total", [[[rng.choice(names), rng.randrange(1, 14)] for _ in range(rng.randrange(1, 4))]]] for _ in range(3)]
                    + [["apply_voucher", [rng.choice([500, 900, 1200, 4000]), rng.choice([None, "WELCOME", "NOPE"])]] for _ in range(4)])
        return []
    return f


BAKERY = God(
    key="bakery", package="bakeshop", doc="Everything the bakery till needs", topic="bakery till",
    areas=[
        Area("money", BAKERY_MONEY, (), cases=_bakery_cases("money")),
        Area("catalog", BAKERY_CATALOG, (), cases=_bakery_cases("catalog")),
        Area("pricing", BAKERY_PRICING, ("money", "catalog"), cases=_bakery_cases("pricing")),
        Area("stock", BAKERY_STOCK, ("catalog",)),
        Area("receipt", BAKERY_RECEIPT, ("money", "pricing"), optional=True, cases=lambda rng, p: [["render_receipt", [[[rng.choice(["sourdough", "croissant", "rye roll", "gift box"]), rng.randrange(1, 14)] for _ in range(rng.randrange(1, 4))], rng.choice([None, "WELCOME"])]] for _ in range(4)]),
    ],
    params=BAKERY_PARAMS,
    app='''"""The till: sells a basket and prints the receipt."""
from bakeshop.util import Stock, apply_voucher, basket_total, fmt_money, list_products


def checkout(counts, lines, voucher=None):
    stock = Stock(counts)
    for name, qty in lines:
        stock.reserve(name, qty)
    totals = basket_total(lines)
    final = apply_voucher(totals["gross"], voucher)
    return {"paid": fmt_money(final), "low": stock.low_items(), "menu": list_products()}
''',
    app_fn="checkout",
    app_cases=lambda rng, p, areas: [["app", [{n: rng.choice([0, 2, 5, 9, 30]) for n in ["sourdough", "croissant", "rye roll", "gift box"]},
                                              [[rng.choice(["sourdough", "croissant", "rye roll", "gift box"]), rng.randrange(1, 8)] for _ in range(rng.randrange(1, 4))],
                                              rng.choice([None, "WELCOME", "BAD"])]] for _ in range(6)],
)


# ----------------------------------------------------------------------------------------------------------------
# trail club
# ----------------------------------------------------------------------------------------------------------------
TRAIL_PARAMS = lambda rng: {  # noqa: E731
    "junior_age": rng.choice([14, 16, 18]), "senior_age": rng.choice([60, 65]), "base": rng.randrange(40, 90, 5), "late_days": rng.choice([14, 30]),
    "late_pct": rng.choice([10, 20, 25]), "max_group": rng.choice([8, 10, 12]), "night_fee": rng.randrange(5, 20),
}

TRAIL_DATES = '''
MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def day_of_year(year, month, day):
    days = sum(MONTH_DAYS[: month - 1]) + day
    if month > 2 and is_leap(year):
        days += 1
    return days


def days_between(a, b):
    """Whole days from date a to date b, both (year, month, day) tuples, same or consecutive years."""
    (ya, ma, da), (yb, mb, db) = a, b
    span = sum(366 if is_leap(y) else 365 for y in range(ya, yb))
    return span + day_of_year(yb, mb, db) - day_of_year(ya, ma, da)
'''

TRAIL_MEMBERS = '''
def age_on(birth, today):
    years = today[0] - birth[0]
    if (today[1], today[2]) < (birth[1], birth[2]):
        years -= 1
    return years


def member_class(birth, today):
    age = age_on(birth, today)
    if age < $junior_age:
        return "junior"
    if age >= $senior_age:
        return "senior"
    return "adult"
'''

TRAIL_FEES = '''
CLASS_PERCENT = {"junior": 50, "adult": 100, "senior": 70}


def annual_fee(birth, today):
    return $base * CLASS_PERCENT[member_class(birth, today)] // 100


def fee_with_late(birth, today, due):
    """The annual fee, with a surcharge once the due date is more than $late_days days past."""
    fee = annual_fee(birth, today)
    late = days_between(due, today) if due <= today else 0
    if late > $late_days:
        fee += fee * $late_pct // 100
    return fee
'''

TRAIL_PERMITS = '''
def group_permit(members, nights, today):
    """Permit price for a group; groups over the limit are refused."""
    if not members or len(members) > $max_group:
        raise ValueError("group size must be 1..$max_group")
    kinds = [member_class(b, today) for b in members]
    if "junior" in kinds and not ("adult" in kinds or "senior" in kinds):
        raise ValueError("juniors need an adult")
    return len(members) * nights * $night_fee
'''

TRAIL_SUMMARY = '''
def summary_line(name, birth, today, due):
    fee = fee_with_late(birth, today, due)
    return "%s (%s): %d" % (name, member_class(birth, today), fee)


def summary(rows, today):
    lines = [summary_line(n, b, today, d) for n, b, d in sorted(rows)]
    total = sum(fee_with_late(b, today, d) for _, b, d in rows)
    return lines + ["total: %d" % total]
'''


def _trail_cases(area):
    def f(rng, p):
        def date(lo=1960, hi=2012):
            return [rng.randrange(lo, hi), rng.randrange(1, 13), rng.randrange(1, 29)]
        if area == "dates":
            return ([["is_leap", [rng.choice([1900, 2000, 2024, 2023, 2100])]] for _ in range(3)]
                    + [["day_of_year", [2024, rng.randrange(1, 13), rng.randrange(1, 29)]] for _ in range(3)]
                    + [["days_between", [[2023, 3, 4], [2024, rng.randrange(1, 13), rng.randrange(1, 29)]]] for _ in range(3)])
        if area == "members":
            return [["age_on", [date(), [2025, 6, 15]]] for _ in range(3)] + [["member_class", [date(1940, 2012), [2025, 6, 15]]] for _ in range(5)]
        if area == "fees":
            return ([["annual_fee", [date(1940, 2012), [2025, 6, 15]]] for _ in range(4)]
                    + [["fee_with_late", [date(1940, 2012), [2025, 6, 15], [2025, rng.randrange(1, 6), rng.randrange(1, 29)]]] for _ in range(4)])
        if area == "permits":
            return [["group_permit", [[date(1940, 2015) for _ in range(rng.randrange(0, 14))], rng.randrange(1, 4), [2025, 6, 15]]] for _ in range(6)]
        return []
    return f


TRAIL = God(
    key="trail", package="trailclub", doc="Dates, members, fees and permits for the hiking club", topic="hiking club admin",
    areas=[
        Area("dates", TRAIL_DATES, (), cases=_trail_cases("dates")),
        Area("members", TRAIL_MEMBERS, (), cases=_trail_cases("members")),
        Area("fees", TRAIL_FEES, ("dates", "members"), cases=_trail_cases("fees")),
        Area("permits", TRAIL_PERMITS, ("members",), optional=True, cases=_trail_cases("permits")),
        Area("summary", TRAIL_SUMMARY, ("fees", "members"), optional=True, cases=lambda rng, p: [["summary", [[["m%d" % i, [rng.randrange(1945, 2012), rng.randrange(1, 13), rng.randrange(1, 29)], [2025, rng.randrange(1, 7), rng.randrange(1, 29)]] for i in range(rng.randrange(1, 4))], [2025, 6, 15]]] for _ in range(3)]),
    ],
    params=TRAIL_PARAMS,
    app='''"""Month-end run for the club treasurer."""
from trailclub.util import annual_fee, days_between, member_class


def month_end(rows, today):
    out = []
    for name, birth, due in rows:
        late = days_between(due, today) if due <= today else 0
        out.append({"name": name, "class": member_class(birth, today), "fee": annual_fee(birth, today), "late_days": late})
    return out
''',
    app_fn="month_end",
    app_cases=lambda rng, p, areas: [["app", [[["m%d" % i, [rng.randrange(1945, 2012), rng.randrange(1, 13), rng.randrange(1, 29)],
                                                  [2025, rng.randrange(1, 7), rng.randrange(1, 29)]] for i in range(rng.randrange(1, 5))], [2025, 6, 15]]]
                                     for _ in range(5)],
)


# ----------------------------------------------------------------------------------------------------------------
# tide tables
# ----------------------------------------------------------------------------------------------------------------
TIDE_PARAMS = lambda rng: {  # noqa: E731
    "mean": rng.choice([2.4, 3.1, 3.6]), "amp": rng.choice([1.2, 1.8, 2.2]), "lag": rng.choice([20, 35, 50]), "period": rng.choice([745, 750, 744]),
    "storm": rng.choice([4.4, 4.8, 5.2]), "low": rng.choice([0.4, 0.6, 0.8]), "step": rng.choice([30, 60]),
}

TIDE_UNITS = '''
FEET_PER_METRE = 3.28084


def metres_to_feet(m):
    return round(m * FEET_PER_METRE, 2)


def minutes_to_clock(minutes):
    minutes %= 1440
    return "%02d:%02d" % (minutes // 60, minutes % 60)
'''

TIDE_HARMONICS = '''
def height_at(minute, phase=0):
    """Water height in metres at a minute of the day: one dominant component plus an overtide."""
    x = 2 * 3.141592653589793 * (minute - $lag + phase) / $period
    return round($mean + $amp * _cos(x) + 0.15 * _cos(2 * x), 3)


def _cos(x):
    # short Taylor series after folding into [-pi, pi]; plenty for a harbour board
    pi = 3.141592653589793
    x = (x + pi) % (2 * pi) - pi
    term, total = 1.0, 1.0
    for k in range(1, 9):
        term *= -x * x / ((2 * k - 1) * (2 * k))
        total += term
    return total
'''

TIDE_TABLES = '''
def day_table(phase=0):
    """Height every $step minutes for one day."""
    return [(m, height_at(m, phase)) for m in range(0, 1440, $step)]


def extremes(table):
    """Local highs and lows of a table (interior points only)."""
    out = []
    for i in range(1, len(table) - 1):
        before, here, after = table[i - 1][1], table[i][1], table[i + 1][1]
        if here > before and here >= after:
            out.append(("high", table[i][0], here))
        elif here < before and here <= after:
            out.append(("low", table[i][0], here))
    return out
'''

TIDE_ALERTS = '''
def alerts(table):
    out = []
    for minute, h in table:
        if h > $storm:
            out.append("flood watch at %s" % minutes_to_clock(minute))
        elif h < $low:
            out.append("shoal warning at %s" % minutes_to_clock(minute))
    return out
'''

TIDE_RENDER = '''
def render_board(phase=0, feet=False):
    lines = []
    for kind, minute, h in extremes(day_table(phase)):
        value = metres_to_feet(h) if feet else h
        lines.append("%s %s %s%s" % (minutes_to_clock(minute), kind, value, "ft" if feet else "m"))
    return lines
'''


def _tide_cases(area):
    def f(rng, p):
        if area == "units":
            return ([["metres_to_feet", [rng.choice([0, 1, 2.5, 4.123])]] for _ in range(3)]
                    + [["minutes_to_clock", [rng.choice([0, 59, 61, 725, 1440, 1500, 3000])]] for _ in range(4)])
        if area == "harmonics":
            return [["height_at", [rng.randrange(0, 1440), rng.choice([0, 30, -45])]] for _ in range(6)]
        if area == "tables":
            return [["day_table", [rng.choice([0, 60, -90])]] for _ in range(2)]
        return []
    return f


TIDES = God(
    key="tides", package="tideboard", doc="Tide heights, tables and warnings for the harbour board", topic="harbour tide board",
    areas=[
        Area("units", TIDE_UNITS, (), cases=_tide_cases("units")),
        Area("harmonics", TIDE_HARMONICS, (), cases=_tide_cases("harmonics")),
        Area("tables", TIDE_TABLES, ("harmonics",), cases=_tide_cases("tables")),
        Area("alerts", TIDE_ALERTS, ("units",), optional=True, cases=lambda rng, p: [["alerts", [[[m, round(rng.uniform(0.1, 5.6), 2)] for m in range(0, 600, 60)]]] for _ in range(3)]),
        Area("render", TIDE_RENDER, ("units", "tables"), optional=True, cases=lambda rng, p: [["render_board", [rng.choice([0, 25, -40]), rng.random() < 0.5]] for _ in range(3)]),
    ],
    params=TIDE_PARAMS,
    app='''"""What the harbour master reads out in the morning."""
from tideboard.util import day_table, extremes, minutes_to_clock


def morning_brief(phase=0):
    table = day_table(phase)
    return ["%s %s %.2f" % (minutes_to_clock(m), kind, h) for kind, m, h in extremes(table)]
''',
    app_fn="morning_brief",
    app_cases=lambda rng, p, areas: [["app", [rng.choice([0, 20, -30, 90])]] for _ in range(5)],
)

GODS = [BAKERY, TRAIL, TIDES]
