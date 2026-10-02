"""Python libraries, theme time/money/scheduling (batch small-c): event ticket pricing, tip pooling, print-shop pricing,
parcel rates. Small single-module libraries."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# ticketing: tiered event tickets, early-bird and group discounts, booking fee
# ======================================================================================================================

TK_README = dd('''
    # ticketing

    Ticket pricing for the Harbour Lights festival. Money is an `int` number of cents; dates are `datetime.date`.
    The venue holds 500 tickets.

    * `unit_price(sold)`: the price of the ticket that would be sold after `sold` tickets have already been sold:
      4000 for the first 100 tickets (`sold` 0 to 99), 5000 for tickets 101 to 300, 6500 for tickets 301 to 500.
      `sold` outside `0..499` is a `ValueError`.
    * `group_percent(qty)`: the group discount in percent: 15 for 10 or more tickets in one order, 10 for 6 to 9,
      otherwise 0.
    * `booking_fee(amount)`: 3% of the amount rounded half up, but at least 150 and at most 900 cents.
    * `order_total(sold, qty, bought_on, early_until)`: the price of an order of `qty` tickets when `sold` have been sold
      before. Every ticket is priced by its own position (`unit_price(sold + i)`), so an order can span two tiers.
      The subtotal is reduced by 15% when `bought_on <= early_until` (early bird) and by the group discount; both
      discounts are applied together and the result is rounded half up to a cent **once**. The booking fee for that
      amount is added. `qty` must be 1 to 12 and the tickets must still be available (`sold + qty <= 500`), otherwise
      `ValueError`.
''')

TK_SRC = dd('''
    CAPACITY = 500
    TIERS = [(100, 4000), (300, 5000), (CAPACITY, 6500)]
    EARLY_PERCENT_OFF = 15
    GROUP_TIERS = [(10, 15), (6, 10)]
    MAX_PER_ORDER = 12
    FEE_BP = 300
    FEE_MIN = 150
    FEE_MAX = 900


    def unit_price(sold):
        if not 0 <= sold < CAPACITY:
            raise ValueError("no ticket left at this position")
        for limit, price in TIERS:
            if sold < limit:
                return price


    def group_percent(qty):
        for minimum, percent in GROUP_TIERS:
            if qty >= minimum:
                return percent
        return 0


    def booking_fee(amount):
        fee = (amount * FEE_BP * 2 + 10_000) // 20_000
        return max(FEE_MIN, min(FEE_MAX, fee))


    def order_total(sold, qty, bought_on, early_until):
        if not 1 <= qty <= MAX_PER_ORDER:
            raise ValueError("quantity out of range")
        if sold + qty > CAPACITY:
            raise ValueError("not enough tickets left")
        subtotal = sum(unit_price(sold + i) for i in range(qty))
        early = EARLY_PERCENT_OFF if bought_on <= early_until else 0
        numerator = subtotal * (100 - early) * (100 - group_percent(qty))
        amount = (2 * numerator + 10_000) // 20_000
        return amount + booking_fee(amount)
''')

TK_VISIBLE = dd('''
    import unittest

    from ticketing.pricing import group_percent, unit_price


    class BasicTests(unittest.TestCase):
        def test_first_tier(self):
            self.assertEqual(unit_price(0), 4000)

        def test_group(self):
            self.assertEqual(group_percent(6), 10)


    if __name__ == "__main__":
        unittest.main()
''')

TK_HIDDEN = dd('''
    import unittest
    from datetime import date

    from ticketing.pricing import booking_fee, group_percent, order_total, unit_price

    EARLY = date(2025, 3, 10)
    ON_TIME = date(2025, 3, 10)
    LATE = date(2025, 3, 11)


    class UnitPrice(unittest.TestCase):
        def test_tiers(self):
            table = {0: 4000, 99: 4000, 100: 5000, 299: 5000, 300: 6500, 499: 6500}
            for sold, price in table.items():
                self.assertEqual(unit_price(sold), price, sold)

        def test_out_of_range(self):
            for sold in (-1, 500, 1000):
                with self.assertRaises(ValueError):
                    unit_price(sold)


    class Group(unittest.TestCase):
        def test_tiers(self):
            self.assertEqual([group_percent(q) for q in range(1, 13)], [0, 0, 0, 0, 0, 10, 10, 10, 10, 15, 15, 15])


    class Fee(unittest.TestCase):
        def test_bounds(self):
            table = {0: 150, 1000: 150, 5000: 150, 5001: 150, 6649: 199, 6650: 200, 6651: 200, 30_000: 900, 30_001: 900, 100_000: 900}
            for amount, fee in table.items():
                self.assertEqual(booking_fee(amount), fee, amount)

        def test_half_up(self):
            self.assertEqual(booking_fee(10_050), 302)   # 301.5
            self.assertEqual(booking_fee(10_016), 300)   # 300.48
            self.assertEqual(booking_fee(10_017), 301)   # 300.51


    class Order(unittest.TestCase):
        def test_spans_two_tiers(self):
            self.assertEqual(order_total(98, 4, LATE, EARLY), 18_540)   # 2 * 4000 + 2 * 5000 = 18000, fee 540

        def test_single_ticket(self):
            self.assertEqual(order_total(0, 1, LATE, EARLY), 4150)
            self.assertEqual(order_total(100, 1, LATE, EARLY), 5150)
            self.assertEqual(order_total(499, 1, LATE, EARLY), 6695)

        def test_early_bird_is_inclusive_of_the_last_day(self):
            self.assertEqual(order_total(98, 4, ON_TIME, EARLY), 15_759)
            self.assertEqual(order_total(98, 4, date(2025, 3, 1), EARLY), 15_759)
            self.assertEqual(order_total(98, 4, LATE, EARLY), 18_540)

        def test_group_discounts(self):
            self.assertEqual(order_total(0, 5, LATE, EARLY), 20_600)
            self.assertEqual(order_total(0, 6, LATE, EARLY), 22_248)
            self.assertEqual(order_total(0, 9, LATE, EARLY), 33_300)
            self.assertEqual(order_total(0, 10, LATE, EARLY), 34_900)
            self.assertEqual(order_total(0, 12, LATE, EARLY), 41_700)

        def test_early_and_group_are_combined_before_rounding(self):
            self.assertEqual(order_total(0, 6, ON_TIME, EARLY), 18_911)
            self.assertEqual(order_total(0, 5, ON_TIME, EARLY), 17_510)
            self.assertEqual(order_total(300, 7, ON_TIME, EARLY), 35_708)   # 45500 * 0.85 * 0.9 = 34807.5 -> 34808, fee capped

        def test_last_tickets(self):
            self.assertEqual(order_total(496, 4, LATE, EARLY), 26_780)
            self.assertEqual(order_total(488, 12, LATE, EARLY), 67_200)   # 12 * 6500 * 0.85 = 66300, fee capped at 900

        def test_quantity_limits(self):
            for qty in (0, 13, -1):
                with self.assertRaises(ValueError):
                    order_total(0, qty, LATE, EARLY)

        def test_sold_out(self):
            with self.assertRaises(ValueError):
                order_total(497, 4, LATE, EARLY)
            with self.assertRaises(ValueError):
                order_total(500, 1, LATE, EARLY)
            order_total(497, 3, LATE, EARLY)


    if __name__ == "__main__":
        unittest.main()
''')

TICKETING = Lib(
    name="ticketing", lang="python", title="the festival ticket pricing (`ticketing/pricing.py`)",
    blurb="The Harbour Lights festival box office prices ticket orders with the ticketing module.",
    files={"ticketing/__init__.py": "", "ticketing/pricing.py": TK_SRC, "README.md": TK_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": TK_VISIBLE},
    hidden_tests={"tests/test_full.py": TK_HIDDEN},
    mutate=["ticketing/pricing.py"], difficulty=1, tags=["tickets", "discounts", "rounding"],
    probes=[
        "unit_price(99)", "unit_price(100)", "unit_price(300)", "group_percent(5)", "group_percent(6)", "group_percent(10)",
        "booking_fee(6649)", "booking_fee(10_050)", "booking_fee(30_000)",
        "order_total(98, 4, date(2025, 3, 11), date(2025, 3, 10))", "order_total(98, 4, date(2025, 3, 10), date(2025, 3, 10))",
        "order_total(0, 6, date(2025, 3, 10), date(2025, 3, 10))", "order_total(300, 7, date(2025, 3, 10), date(2025, 3, 10))",
        "order_total(0, 10, date(2025, 3, 11), date(2025, 3, 10))",
    ],
    probe_import="from datetime import date\nfrom ticketing.pricing import *",
)

# ======================================================================================================================
# tipsplit: restaurant tip pool shared by role points and minutes worked
# ======================================================================================================================

TS_README = dd('''
    # tipsplit

    Tip pooling for a restaurant. Money is an `int` number of cents; shifts are whole minutes.

    * `card_fee(card_tips)`: the card processor keeps 3% of card tips, rounded **up** to a cent.
    * `pool_total(card_tips, cash_tips)`: card tips minus `card_fee`, plus cash tips.
    * `weight(role, minutes)`: roles earn points per minute: `server` 3, `bar` 2, `kitchen` 2, `host` 1. The weight is
      `points * minutes`, but a shift shorter than 60 minutes earns no weight at all. An unknown role is a `ValueError`.
    * `split_pool(total, staff)`: `staff` is a list of `(name, role, minutes)`; returns `{name: cents}` adding up to
      `total`. Each share is `total * weight // sum of weights` (rounded down); the cents left over go one each to the
      staff with the largest weights (ties by name), skipping everybody whose weight is 0. Staff without weight get 0
      and are still in the result. Duplicate names are a `ValueError`; so is a list in which nobody has weight.
''')

TS_SRC = dd('''
    POINTS = {"server": 3, "bar": 2, "kitchen": 2, "host": 1}
    MIN_MINUTES = 60
    CARD_FEE_PERCENT = 3


    def card_fee(card_tips):
        return -(-card_tips * CARD_FEE_PERCENT // 100)


    def pool_total(card_tips, cash_tips):
        return card_tips - card_fee(card_tips) + cash_tips


    def weight(role, minutes):
        if role not in POINTS:
            raise ValueError(f"unknown role {role!r}")
        if minutes < MIN_MINUTES:
            return 0
        return POINTS[role] * minutes


    def split_pool(total, staff):
        weights = {name: weight(role, minutes) for name, role, minutes in staff}
        if len(weights) != len(staff):
            raise ValueError("duplicate name")
        all_weight = sum(weights.values())
        if all_weight == 0:
            raise ValueError("nobody qualifies for the pool")
        shares = {name: total * w // all_weight for name, w in weights.items()}
        left = total - sum(shares.values())
        order = sorted((n for n in weights if weights[n] > 0), key=lambda n: (-weights[n], n))
        for name in order[:left]:
            shares[name] += 1
        return shares
''')

TS_VISIBLE = dd('''
    import unittest

    from tipsplit.pool import card_fee, weight


    class BasicTests(unittest.TestCase):
        def test_fee(self):
            self.assertEqual(card_fee(1000), 30)

        def test_weight(self):
            self.assertEqual(weight("server", 240), 720)


    if __name__ == "__main__":
        unittest.main()
''')

TS_HIDDEN = dd('''
    import unittest

    from tipsplit.pool import card_fee, pool_total, split_pool, weight

    STAFF = [("ann", "server", 480), ("bo", "bar", 420), ("cy", "host", 300), ("di", "kitchen", 59), ("ed", "server", 360)]


    class Fee(unittest.TestCase):
        def test_rounds_up(self):
            table = {0: 0, 1: 1, 33: 1, 34: 2, 100: 3, 1000: 30, 12_345: 371}
            for tips, fee in table.items():
                self.assertEqual(card_fee(tips), fee, tips)

        def test_pool_total(self):
            self.assertEqual(pool_total(10_000, 2000), 11_700)
            self.assertEqual(pool_total(0, 500), 500)
            self.assertEqual(pool_total(1, 0), 0)
            self.assertEqual(pool_total(12_345, 55), 12_345 - 371 + 55)


    class Weight(unittest.TestCase):
        def test_points(self):
            self.assertEqual(weight("server", 60), 180)
            self.assertEqual(weight("bar", 60), 120)
            self.assertEqual(weight("kitchen", 240), 480)
            self.assertEqual(weight("host", 240), 240)

        def test_short_shifts(self):
            for role in ("server", "bar", "kitchen", "host"):
                self.assertEqual(weight(role, 59), 0)
                self.assertEqual(weight(role, 0), 0)
                self.assertGreater(weight(role, 60), 0)

        def test_unknown_role(self):
            for role in ("chef", "", "Server"):
                with self.assertRaises(ValueError):
                    weight(role, 120)
            with self.assertRaises(ValueError):
                weight("chef", 10)


    class Split(unittest.TestCase):
        def test_proportional(self):
            got = split_pool(10_000, STAFF)
            self.assertEqual(got, {"ann": 3935, "bo": 2295, "cy": 819, "di": 0, "ed": 2951})
            self.assertEqual(sum(got.values()), 10_000)

        def test_leftover_goes_to_the_biggest_weights(self):
            self.assertEqual(split_pool(1, STAFF), {"ann": 1, "bo": 0, "cy": 0, "di": 0, "ed": 0})
            self.assertEqual(split_pool(7, STAFF), {"ann": 3, "bo": 1, "cy": 0, "di": 0, "ed": 3})

        def test_ties_by_name(self):
            equal = [("c", "server", 120), ("a", "server", 120), ("b", "server", 120)]
            self.assertEqual(split_pool(100, equal), {"a": 34, "b": 33, "c": 33})
            self.assertEqual(split_pool(1000, equal), {"a": 334, "b": 333, "c": 333})
            self.assertEqual(split_pool(2, equal), {"a": 1, "b": 1, "c": 0})

        def test_weights_come_before_names(self):
            staff = [("b", "server", 120), ("a", "server", 60), ("c", "bar", 120)]
            self.assertEqual(split_pool(100, staff), {"b": 47, "a": 23, "c": 30})

        def test_zero_weight_never_gets_a_leftover_cent(self):
            staff = [("a", "server", 59), ("b", "host", 60), ("c", "host", 60), ("d", "bar", 30)]
            got = split_pool(3, staff)
            self.assertEqual(got, {"a": 0, "b": 2, "c": 1, "d": 0})

        def test_zero_total(self):
            self.assertEqual(split_pool(0, STAFF), {name: 0 for name, _, _ in STAFF})

        def test_single_person(self):
            self.assertEqual(split_pool(999, [("ann", "host", 100)]), {"ann": 999})

        def test_errors(self):
            with self.assertRaises(ValueError):
                split_pool(100, [("a", "chef", 100)])
            with self.assertRaises(ValueError):
                split_pool(100, [("a", "server", 30)])
            with self.assertRaises(ValueError):
                split_pool(100, [("a", "server", 100), ("a", "bar", 100)])
            with self.assertRaises(ValueError):
                split_pool(100, [])


    if __name__ == "__main__":
        unittest.main()
''')

TIPSPLIT = Lib(
    name="tipsplit", lang="python", title="the restaurant tip pool (`tipsplit/pool.py`)",
    blurb="The restaurant's payroll app shares the tip pool between the staff with the tipsplit module.",
    files={"tipsplit/__init__.py": "", "tipsplit/pool.py": TS_SRC, "README.md": TS_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": TS_VISIBLE},
    hidden_tests={"tests/test_full.py": TS_HIDDEN},
    mutate=["tipsplit/pool.py"], difficulty=1, tags=["tips", "allocation", "payroll"],
    probes=[
        "card_fee(34)", "card_fee(12_345)", "pool_total(10_000, 2000)", "weight('server', 59)", "weight('server', 60)", "weight('host', 240)",
        "split_pool(10_000, [('ann', 'server', 480), ('bo', 'bar', 420), ('cy', 'host', 300), ('di', 'kitchen', 59), ('ed', 'server', 360)])",
        "split_pool(7, [('ann', 'server', 480), ('bo', 'bar', 420), ('cy', 'host', 300), ('di', 'kitchen', 59), ('ed', 'server', 360)])",
        "split_pool(100, [('c', 'server', 120), ('a', 'server', 120), ('b', 'server', 120)])",
        "split_pool(100, [('b', 'server', 120), ('a', 'server', 60), ('c', 'bar', 120)])",
        "split_pool(3, [('a', 'server', 59), ('b', 'host', 60), ('c', 'host', 60), ('d', 'bar', 30)])",
    ],
    probe_import="from tipsplit.pool import *",
)

# ======================================================================================================================
# printjob: print-shop pricing with copy tiers, duplex, binding and rush surcharge
# ======================================================================================================================

PJ_README = dd('''
    # printjob

    Price list of a copy shop. Money is an `int` number of cents.

    * `page_rate(rates, copies)`: `rates` is a list of `(below, cents)` pairs, the last with `below = None`; the rate of
      the first pair with `copies < below` (the last pair when none matches).
    * Page prices per page and copy, by the number of copies: black and white `BW_RATES` = 12 cents below 10 copies,
      9 cents below 100 copies, 7 cents from 100 copies; colour `COLOR_RATES` = 55, 45 and 38 cents in the same tiers.
    * `job_price(bw_pages, color_pages, copies, binding="none", duplex=False, rush=False)`:
      - `ValueError` when a page count is negative or there are no pages at all, when `copies < 1`, or for an unknown
        binding.
      - One copy costs `bw_pages * bw_rate + color_pages * color_rate`; the pages cost that times `copies`.
      - `duplex` (double-sided printing) takes 10% off the **pages** cost, rounded half up to a cent.
      - Binding is charged per copy: `none` 0, `staple` 50, `spiral` 400, `hardcover` 1500 cents.
      - `rush` adds 25% to the sum of pages and binding, rounded half up to a cent.
      - The minimum order is 300 cents.
''')

PJ_SRC = dd('''
    BW_RATES = [(10, 12), (100, 9), (None, 7)]
    COLOR_RATES = [(10, 55), (100, 45), (None, 38)]
    BINDING = {"none": 0, "staple": 50, "spiral": 400, "hardcover": 1500}
    DUPLEX_PERCENT_OFF = 10
    RUSH_PERCENT = 25
    MINIMUM = 300


    def page_rate(rates, copies):
        for below, rate in rates:
            if below is None or copies < below:
                return rate


    def job_price(bw_pages, color_pages, copies, binding="none", duplex=False, rush=False):
        if bw_pages < 0 or color_pages < 0 or bw_pages + color_pages == 0:
            raise ValueError("a job needs at least one page")
        if copies < 1:
            raise ValueError("copies must be at least 1")
        if binding not in BINDING:
            raise ValueError(f"unknown binding {binding!r}")
        per_copy = bw_pages * page_rate(BW_RATES, copies) + color_pages * page_rate(COLOR_RATES, copies)
        pages_cost = per_copy * copies
        if duplex:
            pages_cost = (pages_cost * (100 - DUPLEX_PERCENT_OFF) * 2 + 100) // 200
        total = pages_cost + BINDING[binding] * copies
        if rush:
            total = (total * (100 + RUSH_PERCENT) * 2 + 100) // 200
        return max(total, MINIMUM)
''')

PJ_VISIBLE = dd('''
    import unittest

    from printjob.pricing import job_price, page_rate


    class BasicTests(unittest.TestCase):
        def test_rate(self):
            self.assertEqual(page_rate([(10, 12), (None, 9)], 3), 12)

        def test_plain_job(self):
            self.assertEqual(job_price(20, 0, 2), 480)


    if __name__ == "__main__":
        unittest.main()
''')

PJ_HIDDEN = dd('''
    import unittest

    from printjob.pricing import BW_RATES, COLOR_RATES, job_price, page_rate


    class Rates(unittest.TestCase):
        def test_tiers(self):
            self.assertEqual([page_rate(BW_RATES, c) for c in (1, 9, 10, 99, 100, 500)], [12, 12, 9, 9, 7, 7])
            self.assertEqual([page_rate(COLOR_RATES, c) for c in (1, 9, 10, 99, 100, 500)], [55, 55, 45, 45, 38, 38])

        def test_generic_table(self):
            table = [(5, 10), (50, 8), (None, 6)]
            self.assertEqual([page_rate(table, c) for c in (1, 4, 5, 49, 50, 51)], [10, 10, 8, 8, 6, 6])


    class Price(unittest.TestCase):
        def test_plain(self):
            self.assertEqual(job_price(20, 0, 2), 480)
            self.assertEqual(job_price(26, 0, 1), 312)
            self.assertEqual(job_price(3, 3, 9), 1809)
            self.assertEqual(job_price(3, 3, 10), 1620)
            self.assertEqual(job_price(3, 3, 99), 16_038)
            self.assertEqual(job_price(100, 0, 100), 70_000)
            self.assertEqual(job_price(10, 2, 10), 1800)

        def test_minimum_order(self):
            self.assertEqual(job_price(1, 0, 1), 300)
            self.assertEqual(job_price(24, 0, 1), 300)
            self.assertEqual(job_price(25, 0, 1), 300)
            self.assertEqual(job_price(26, 0, 1), 312)
            self.assertEqual(job_price(0, 1, 1), 300)

        def test_binding(self):
            self.assertEqual(job_price(20, 0, 1, "staple"), 300)   # 240 + 50 is below the minimum
            self.assertEqual(job_price(20, 0, 2, "spiral"), 1280)
            self.assertEqual(job_price(30, 5, 5, "hardcover"), 10_675)
            self.assertEqual(job_price(30, 0, 1, "staple"), 410)
            self.assertEqual(job_price(30, 0, 3, "none"), 1080)

        def test_duplex(self):
            self.assertEqual(job_price(37, 0, 1, duplex=True), 400)    # 444 * 0.9 = 399.6
            self.assertEqual(job_price(0, 13, 1, duplex=True), 644)    # 715 * 0.9 = 643.5
            self.assertEqual(job_price(25, 0, 3, duplex=True), 810)
            self.assertEqual(job_price(10, 2, 10, duplex=True), 1620)

        def test_duplex_does_not_touch_binding(self):
            self.assertEqual(job_price(10, 2, 10, "spiral", duplex=True), 1620 + 4000)

        def test_rush(self):
            self.assertEqual(job_price(7, 0, 3, "staple", rush=True), 503)    # 402 * 1.25 = 502.5
            self.assertEqual(job_price(20, 0, 2, rush=True), 600)
            self.assertEqual(job_price(30, 0, 1, rush=True), 450)
            self.assertEqual(job_price(5, 0, 1, rush=True), 300)

        def test_rush_covers_binding_and_comes_after_duplex(self):
            self.assertEqual(job_price(10, 2, 10, "spiral", duplex=True, rush=True), 7025)
            self.assertEqual(job_price(30, 5, 5, "hardcover", rush=True), 13_344)

        def test_errors(self):
            for args in ((0, 0, 1), (-1, 2, 1), (5, -1, 1), (5, 0, 0), (5, 0, -2)):
                with self.assertRaises(ValueError, msg=args):
                    job_price(*args)
            with self.assertRaises(ValueError):
                job_price(5, 0, 1, "glue")
            with self.assertRaises(ValueError):
                job_price(5, 0, 1, "")


    if __name__ == "__main__":
        unittest.main()
''')

PRINTJOB = Lib(
    name="printjob", lang="python", title="the copy-shop price list (`printjob/pricing.py`)",
    blurb="The copy shop's till prices print jobs with the printjob module.",
    files={"printjob/__init__.py": "", "printjob/pricing.py": PJ_SRC, "README.md": PJ_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": PJ_VISIBLE},
    hidden_tests={"tests/test_full.py": PJ_HIDDEN},
    mutate=["printjob/pricing.py"], difficulty=1, tags=["printing", "pricing", "rounding"],
    probes=[
        "page_rate(BW_RATES, 9)", "page_rate(BW_RATES, 10)", "page_rate(COLOR_RATES, 100)", "job_price(26, 0, 1)", "job_price(25, 0, 1)",
        "job_price(3, 3, 10)", "job_price(20, 0, 2, 'spiral')", "job_price(37, 0, 1, duplex=True)", "job_price(0, 13, 1, duplex=True)",
        "job_price(7, 0, 3, 'staple', rush=True)", "job_price(10, 2, 10, 'spiral', duplex=True, rush=True)", "job_price(0, 0, 1)",
    ],
    probe_import="from printjob.pricing import *",
)

# ======================================================================================================================
# parcelrate: parcel shipping quote with dimensional weight, zone bands, fuel surcharge, remote fee, insurance
# ======================================================================================================================

PR_README = dd('''
    # parcelrate

    Rate quotes of a parcel carrier. Money is an `int` number of cents; weights are whole grams; sizes are whole
    centimetres.

    * `billable_grams(actual, length, width, height)`: the larger of the actual weight and the dimensional weight
      (`ceil(length * width * height / 5)` grams), rounded **up** to a multiple of 500 grams.
    * `band_price(zone, grams)`: the zone's price for the weight band that holds `grams` (bands end at 1000, 2000, 5000,
      10000, 20000 and 30000 grams, the end included). Zone 1: 595, 695, 895, 1295, 1895, 2495; zone 2: 695, 795, 1095,
      1595, 2295, 2995; zone 3: 895, 1095, 1495, 2195, 3195, 4195. An unknown zone, a weight of 0 or less, or more than
      30000 grams is a `ValueError`.
    * `is_remote(postcode)`: whether the postcode (spaces ignored, case ignored) starts with one of `IV`, `KW`, `PA`,
      `ZE`.
    * `insurance(declared)`: nothing up to a declared value of 5000; above that 1% of the part over 5000 (rounded down)
      but at least 100.
    * `quote(zone, actual, size, postcode, declared=0)`: `size` is `(length, width, height)`. The total is the band
      price of the billable weight, plus a fuel surcharge of 8% of that price (rounded half up), plus 450 for a remote
      postcode, plus the insurance.
''')

PR_SRC = dd('''
    DIM_DIVISOR = 5
    STEP = 500
    BANDS = [1000, 2000, 5000, 10_000, 20_000, 30_000]
    PRICES = {
        1: [595, 695, 895, 1295, 1895, 2495],
        2: [695, 795, 1095, 1595, 2295, 2995],
        3: [895, 1095, 1495, 2195, 3195, 4195],
    }
    FUEL_PERCENT = 8
    REMOTE_PREFIXES = ("IV", "KW", "PA", "ZE")
    REMOTE_FEE = 450
    INSURANCE_FREE = 5000
    INSURANCE_BP = 100
    INSURANCE_MIN = 100


    def billable_grams(actual, length, width, height):
        dimensional = -(-length * width * height // DIM_DIVISOR)
        heavier = max(actual, dimensional)
        return -(-heavier // STEP) * STEP


    def band_price(zone, grams):
        if zone not in PRICES:
            raise ValueError(f"unknown zone {zone!r}")
        if grams <= 0 or grams > BANDS[-1]:
            raise ValueError("weight out of range")
        for limit, price in zip(BANDS, PRICES[zone]):
            if grams <= limit:
                return price


    def is_remote(postcode):
        return postcode.replace(" ", "").upper().startswith(REMOTE_PREFIXES)


    def insurance(declared):
        if declared <= INSURANCE_FREE:
            return 0
        return max(INSURANCE_MIN, (declared - INSURANCE_FREE) * INSURANCE_BP // 10_000)


    def quote(zone, actual, size, postcode, declared=0):
        grams = billable_grams(actual, *size)
        base = band_price(zone, grams)
        fuel = (base * FUEL_PERCENT * 2 + 100) // 200
        remote = REMOTE_FEE if is_remote(postcode) else 0
        return base + fuel + remote + insurance(declared)
''')

PR_VISIBLE = dd('''
    import unittest

    from parcelrate.rates import billable_grams, band_price


    class BasicTests(unittest.TestCase):
        def test_actual_weight_wins(self):
            self.assertEqual(billable_grams(1000, 10, 10, 10), 1000)

        def test_band(self):
            self.assertEqual(band_price(1, 1000), 595)


    if __name__ == "__main__":
        unittest.main()
''')

PR_HIDDEN = dd('''
    import unittest

    from parcelrate.rates import band_price, billable_grams, insurance, is_remote, quote


    class Billable(unittest.TestCase):
        def test_values(self):
            table = [((100, 10, 10, 10), 500), ((1000, 10, 10, 10), 1000), ((1001, 10, 10, 10), 1500), ((200, 30, 20, 10), 1500),
                     ((250, 30, 20, 10), 1500), ((1500, 40, 30, 20), 5000), ((0, 1, 1, 1), 500), ((500, 10, 10, 10), 500),
                     ((501, 5, 5, 5), 1000)]
            for args, grams in table:
                self.assertEqual(billable_grams(*args), grams, args)

        def test_dimensional_weight_rounds_up(self):
            self.assertEqual(billable_grams(0, 10, 10, 10), 500)       # 200 g
            self.assertEqual(billable_grams(0, 10, 10, 25), 500)       # exactly 500 g
            self.assertEqual(billable_grams(0, 10, 10, 26), 1000)      # 520 g
            self.assertEqual(billable_grams(0, 20, 20, 25), 2000)      # 2000 g
            self.assertEqual(billable_grams(0, 20, 20, 26), 2500)      # 2080 g
            self.assertEqual(billable_grams(0, 7, 7, 7), 500)           # 68.6 -> 69 g


    class Bands(unittest.TestCase):
        def test_zone_one(self):
            table = {500: 595, 1000: 595, 1500: 695, 2000: 695, 2500: 895, 5000: 895, 5500: 1295, 10_000: 1295, 10_500: 1895,
                     20_000: 1895, 20_500: 2495, 30_000: 2495}
            for grams, price in table.items():
                self.assertEqual(band_price(1, grams), price, grams)

        def test_zones(self):
            self.assertEqual([band_price(z, 5000) for z in (1, 2, 3)], [895, 1095, 1495])
            self.assertEqual([band_price(z, 30_000) for z in (1, 2, 3)], [2495, 2995, 4195])
            self.assertEqual([band_price(z, 1) for z in (1, 2, 3)], [595, 695, 895])

        def test_errors(self):
            for zone, grams in ((9, 500), (0, 500), (1, 0), (1, -5), (1, 30_001), (1, 100_000)):
                with self.assertRaises(ValueError, msg=(zone, grams)):
                    band_price(zone, grams)


    class Remote(unittest.TestCase):
        def test_prefixes(self):
            for code in ("IV1 1AA", "iv11aa", "KW 1", "ZE1 0AB", "PA20 9AA", " pa 3", "I V2"):
                self.assertTrue(is_remote(code), code)
            for code in ("AB1", "XIV", "", "K", "BT1 1AA", "P"):
                self.assertFalse(is_remote(code), code)


    class Insurance(unittest.TestCase):
        def test_values(self):
            table = {0: 0, 5000: 0, 5001: 100, 5099: 100, 10_000: 100, 20_000: 150, 100_000: 950, 25_099: 200, 25_100: 201}
            for declared, cents in table.items():
                self.assertEqual(insurance(declared), cents, declared)


    class Quote(unittest.TestCase):
        def test_simple(self):
            self.assertEqual(quote(1, 500, (10, 10, 10), "AB1 2CD"), 643)
            self.assertEqual(quote(1, 1000, (10, 10, 10), "AB1"), 643)
            self.assertEqual(quote(1, 1001, (10, 10, 10), "AB1"), 751)
            self.assertEqual(quote(1, 900, (10, 10, 10), "AB1"), 643)

        def test_remote(self):
            self.assertEqual(quote(1, 500, (10, 10, 10), "IV1 2CD"), 1093)

        def test_dimensions_and_insurance(self):
            self.assertEqual(quote(2, 1500, (40, 30, 20), "AB1", 20_000), 1333)

        def test_everything(self):
            self.assertEqual(quote(3, 25_000, (10, 10, 10), "ZE1 0AB", 9000), 5081)

        def test_fuel_rounds_half_up(self):
            # 895 * 8% = 71.6 -> 72 ; 695 * 8% = 55.6 -> 56 ; 1295 * 8% = 103.6 -> 104
            self.assertEqual(quote(1, 5000, (1, 1, 1), "AB1"), 895 + 72)
            self.assertEqual(quote(1, 1500, (1, 1, 1), "AB1"), 695 + 56)
            self.assertEqual(quote(1, 10_000, (1, 1, 1), "AB1"), 1295 + 104)

        def test_errors(self):
            with self.assertRaises(ValueError):
                quote(9, 500, (1, 1, 1), "AB")
            with self.assertRaises(ValueError):
                quote(1, 31_000, (1, 1, 1), "AB")
            with self.assertRaises(ValueError):
                quote(1, 0, (0, 0, 0), "AB")


    if __name__ == "__main__":
        unittest.main()
''')

PARCELRATE = Lib(
    name="parcelrate", lang="python", title="the parcel carrier rate quote (`parcelrate/rates.py`)",
    blurb="The carrier's website quotes parcel prices with the parcelrate module.",
    files={"parcelrate/__init__.py": "", "parcelrate/rates.py": PR_SRC, "README.md": PR_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": PR_VISIBLE},
    hidden_tests={"tests/test_full.py": PR_HIDDEN},
    mutate=["parcelrate/rates.py"], difficulty=2, tags=["shipping", "rates", "weights"],
    probes=[
        "billable_grams(201, 10, 10, 10)", "billable_grams(0, 20, 20, 26)", "billable_grams(1001, 10, 10, 10)", "billable_grams(1500, 40, 30, 20)",
        "band_price(1, 1000)", "band_price(1, 1500)", "band_price(3, 30_000)", "band_price(1, 30_001)", "is_remote('iv11aa')", "is_remote('XIV')",
        "insurance(5001)", "insurance(100_000)", "quote(1, 1001, (10, 10, 10), 'AB1')", "quote(2, 1500, (40, 30, 20), 'AB1', 20_000)",
        "quote(3, 25_000, (10, 10, 10), 'ZE1 0AB', 9000)", "quote(1, 500, (10, 10, 10), 'IV1 2CD')",
    ],
    probe_import="from parcelrate.rates import *",
)

register_libs([TICKETING, TIPSPLIT, PRINTJOB, PARCELRATE], n=10)
