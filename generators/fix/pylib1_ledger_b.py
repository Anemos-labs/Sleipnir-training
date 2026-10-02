"""Python libraries, theme time/money/scheduling (batch ledger-b): late fees, layaway plans, budget envelopes."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# arrears: late-fee compounding, flat fee, cap and payment allocation
# ======================================================================================================================

AR_README = dd('''
    # arrears

    Late-payment charges of a supplier's invoicing system. Money is an `int` number of cents; dates are
    `datetime.date`.

    * `periods_late(due, paid_on)`: after a grace period of 5 days (a payment up to and including `due + 5 days` is
      on time) every **started** 30 days of lateness is a period. Paying on time gives `0`.
    * `compounded(principal, periods)`: the principal grown by 1.5% for every period, **compounding**: each step
      multiplies by 1.015 and is rounded half up to a whole cent before the next one.
    * `late_fee(principal, due, paid_on)`: `0` when no period has started (and `principal <= 0` is a `ValueError`).
      Otherwise the interest is `compounded(principal, periods) - principal`, but at most 25% of the principal
      (`principal * 25 // 100`). From the second period on a flat fee of 500 cents is added (it is not capped). The late
      fee is interest plus flat fee.
    * `amount_due(principal, due, paid_on)`: the principal plus the late fee.
    * `breakdown(principal, due, paid_on)`: a dict `{"principal": ..., "interest": ..., "fees": ...}` with the capped
      interest and the flat fee of `late_fee`.
    * `allocate_payment(debt, payment)`: `debt` is such a dict. A payment is used **fees first, then interest, then
      principal**. Returns `(new_debt, overpayment)`; the overpayment is what is left after the whole debt is cleared.
      `payment <= 0` is a `ValueError`; the argument is not modified.
''')

AR_SRC = dd('''
    GRACE_DAYS = 5
    PERIOD_DAYS = 30
    RATE_PERMILLE = 15
    FLAT_FROM_PERIOD = 2
    FLAT_FEE = 500
    CAP_PERCENT = 25


    def periods_late(due, paid_on):
        late = (paid_on - due).days
        if late <= GRACE_DAYS:
            return 0
        return -(-(late - GRACE_DAYS) // PERIOD_DAYS)


    def compounded(principal, periods):
        amount = principal
        for _ in range(periods):
            amount = (amount * (1000 + RATE_PERMILLE) * 2 + 1000) // 2000
        return amount


    def breakdown(principal, due, paid_on):
        if principal <= 0:
            raise ValueError("principal must be positive")
        periods = periods_late(due, paid_on)
        if periods == 0:
            return {"principal": principal, "interest": 0, "fees": 0}
        interest = min(compounded(principal, periods) - principal, principal * CAP_PERCENT // 100)
        fees = FLAT_FEE if periods >= FLAT_FROM_PERIOD else 0
        return {"principal": principal, "interest": interest, "fees": fees}


    def late_fee(principal, due, paid_on):
        parts = breakdown(principal, due, paid_on)
        return parts["interest"] + parts["fees"]


    def amount_due(principal, due, paid_on):
        return principal + late_fee(principal, due, paid_on)


    def allocate_payment(debt, payment):
        if payment <= 0:
            raise ValueError("payment must be positive")
        new = dict(debt)
        left = payment
        for key in ("fees", "interest", "principal"):
            used = min(new[key], left)
            new[key] -= used
            left -= used
        return new, left
''')

AR_VISIBLE = dd('''
    import unittest
    from datetime import date

    from arrears.fees import allocate_payment, compounded, periods_late


    class BasicTests(unittest.TestCase):
        def test_on_time(self):
            self.assertEqual(periods_late(date(2025, 3, 1), date(2025, 3, 6)), 0)

        def test_one_period(self):
            self.assertEqual(compounded(100_000, 1), 101_500)

        def test_fees_first(self):
            debt = {"fees": 500, "interest": 100, "principal": 1000}
            self.assertEqual(allocate_payment(debt, 400), ({"fees": 100, "interest": 100, "principal": 1000}, 0))


    if __name__ == "__main__":
        unittest.main()
''')

AR_HIDDEN = dd('''
    import unittest
    from datetime import date

    from arrears.fees import allocate_payment, amount_due, breakdown, compounded, late_fee, periods_late

    D = date
    DUE = D(2025, 3, 1)


    def late(days):
        return D.fromordinal(DUE.toordinal() + days)


    class Periods(unittest.TestCase):
        def test_grace_and_period_edges(self):
            table = {-10: 0, 0: 0, 5: 0, 6: 1, 35: 1, 36: 2, 65: 2, 66: 3, 95: 3, 96: 4, 365: 12}
            for days, periods in table.items():
                self.assertEqual(periods_late(DUE, late(days)), periods, days)

        def test_dates_across_months(self):
            self.assertEqual(periods_late(D(2025, 1, 31), D(2025, 3, 7)), 1)   # 35 days
            self.assertEqual(periods_late(D(2025, 1, 31), D(2025, 3, 8)), 2)   # 36 days


    class Compounding(unittest.TestCase):
        def test_values(self):
            table = {(100_000, 0): 100_000, (100_000, 1): 101_500, (100_000, 2): 103_023, (100_000, 3): 104_568,
                     (100_000, 4): 106_137, (1000, 1): 1015, (1000, 4): 1061, (33, 1): 33, (34, 1): 35, (1, 30): 1,
                     (100, 1): 102, (101, 1): 103, (0, 5): 0}
            for (amount, periods), want in table.items():
                self.assertEqual(compounded(amount, periods), want, (amount, periods))

        def test_each_step_is_rounded(self):
            # 101_500 * 1.015 = 103_022.5 -> 103_023 (half up); without rounding the steps 1000 -> 1061 would be 1061.36
            self.assertEqual(compounded(100_000, 2), 103_023)
            self.assertEqual(compounded(1000, 8), 1126)


    class Fee(unittest.TestCase):
        def test_on_time_is_free(self):
            self.assertEqual(late_fee(100_000, DUE, late(5)), 0)
            self.assertEqual(late_fee(100_000, DUE, late(-3)), 0)

        def test_one_period_has_no_flat_fee(self):
            self.assertEqual(late_fee(100_000, DUE, late(6)), 1500)
            self.assertEqual(late_fee(100_000, DUE, late(35)), 1500)

        def test_flat_fee_from_the_second_period(self):
            self.assertEqual(late_fee(100_000, DUE, late(36)), 3023 + 500)
            self.assertEqual(late_fee(100_000, DUE, late(66)), 4568 + 500)
            self.assertEqual(late_fee(100_000, DUE, late(96)), 6137 + 500)

        def test_cap_on_interest_only(self):
            # 1000 cents: the cap is 250; the interest passes it in the 16th period
            self.assertEqual(late_fee(1000, DUE, late(5 + 15 * 30)), 249 + 500)
            self.assertEqual(late_fee(1000, DUE, late(5 + 16 * 30)), 250 + 500)
            self.assertEqual(late_fee(1000, DUE, late(5 + 24 * 30)), 250 + 500)

        def test_cap_rounds_down(self):
            # principal 999 -> cap 249 (249.75)
            self.assertEqual(breakdown(999, DUE, late(5 + 24 * 30))["interest"], 249)

        def test_amount_due(self):
            self.assertEqual(amount_due(100_000, DUE, late(3)), 100_000)
            self.assertEqual(amount_due(100_000, DUE, late(40)), 103_523)

        def test_breakdown(self):
            self.assertEqual(breakdown(100_000, DUE, late(6)), {"principal": 100_000, "interest": 1500, "fees": 0})
            self.assertEqual(breakdown(100_000, DUE, late(40)), {"principal": 100_000, "interest": 3023, "fees": 500})
            self.assertEqual(breakdown(100_000, DUE, late(0)), {"principal": 100_000, "interest": 0, "fees": 0})

        def test_principal_must_be_positive(self):
            for principal in (0, -100):
                with self.assertRaises(ValueError):
                    late_fee(principal, DUE, late(100))
                with self.assertRaises(ValueError):
                    breakdown(principal, DUE, late(0))


    class Payment(unittest.TestCase):
        DEBT = {"fees": 500, "interest": 3023, "principal": 100_000}

        def test_fees_first(self):
            got, over = allocate_payment(self.DEBT, 400)
            self.assertEqual((got, over), ({"fees": 100, "interest": 3023, "principal": 100_000}, 0))

        def test_then_interest(self):
            got, over = allocate_payment(self.DEBT, 600)
            self.assertEqual((got, over), ({"fees": 0, "interest": 2923, "principal": 100_000}, 0))
            got, over = allocate_payment(self.DEBT, 3523)
            self.assertEqual((got, over), ({"fees": 0, "interest": 0, "principal": 100_000}, 0))

        def test_then_principal(self):
            got, over = allocate_payment(self.DEBT, 3524)
            self.assertEqual((got, over), ({"fees": 0, "interest": 0, "principal": 99_999}, 0))
            got, over = allocate_payment(self.DEBT, 50_000)
            self.assertEqual(got, {"fees": 0, "interest": 0, "principal": 53_523})

        def test_overpayment(self):
            got, over = allocate_payment(self.DEBT, 103_523)
            self.assertEqual((got, over), ({"fees": 0, "interest": 0, "principal": 0}, 0))
            got, over = allocate_payment(self.DEBT, 200_000)
            self.assertEqual((got, over), ({"fees": 0, "interest": 0, "principal": 0}, 96_477))

        def test_exact_fee(self):
            got, over = allocate_payment(self.DEBT, 500)
            self.assertEqual((got["fees"], got["interest"], over), (0, 3023, 0))

        def test_argument_is_not_modified(self):
            debt = dict(self.DEBT)
            allocate_payment(debt, 700)
            self.assertEqual(debt, self.DEBT)

        def test_payment_must_be_positive(self):
            for payment in (0, -5):
                with self.assertRaises(ValueError):
                    allocate_payment(self.DEBT, payment)

        def test_empty_debt(self):
            zero = {"fees": 0, "interest": 0, "principal": 0}
            self.assertEqual(allocate_payment(zero, 10), (zero, 10))


    if __name__ == "__main__":
        unittest.main()
''')

ARREARS = Lib(
    name="arrears", lang="python", title="the late-fee calculator (`arrears/fees.py`)",
    blurb="The supplier's invoicing system works out late-payment charges and applies part payments with arrears.",
    files={"arrears/__init__.py": "", "arrears/fees.py": AR_SRC, "README.md": AR_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": AR_VISIBLE},
    hidden_tests={"tests/test_full.py": AR_HIDDEN},
    mutate=["arrears/fees.py"], difficulty=2, tags=["late-fees", "compounding", "money"],
    probes=[
        "periods_late(date(2025, 3, 1), date(2025, 3, 6))", "periods_late(date(2025, 3, 1), date(2025, 3, 7))",
        "periods_late(date(2025, 3, 1), date(2025, 4, 5))", "periods_late(date(2025, 3, 1), date(2025, 4, 6))",
        "compounded(100_000, 2)", "compounded(34, 1)", "late_fee(100_000, date(2025, 3, 1), date(2025, 4, 10))",
        "late_fee(1000, date(2025, 3, 1), date(2026, 5, 3))", "late_fee(1000, date(2025, 3, 1), date(2026, 6, 2))",
        "breakdown(999, date(2025, 3, 1), date(2027, 3, 1))",
        "amount_due(100_000, date(2025, 3, 1), date(2025, 4, 10))",
        "allocate_payment({'fees': 500, 'interest': 3023, 'principal': 100_000}, 600)",
        "allocate_payment({'fees': 500, 'interest': 3023, 'principal': 100_000}, 200_000)",
    ],
    probe_import="from datetime import date\nfrom arrears.fees import *",
)

# ======================================================================================================================
# layaway: shop layaway (reserve-and-pay) plans
# ======================================================================================================================

LY_README = dd('''
    # layaway

    A shop lets customers reserve an item and pay it off weekly. Money is an `int` number of cents; dates are
    `datetime.date`.

    * `deposit(price)`: 10% of the price rounded **up**, but at least 500 cents and never more than the price. A price
      of `0` or less is a `ValueError`.
    * `instalments(price, weeks)`: `weeks` is 1 to 12 (otherwise `ValueError`). What remains after the deposit is paid
      in equal weekly amounts of `remaining / weeks` rounded **up to a multiple of 5 cents**; the last payment is
      whatever is left, so there can be fewer payments than weeks. Nothing remaining gives `[]`.
    * `schedule(price, weeks, start)`: `[(start, deposit)]` followed by the instalments on `start + 7`, `start + 14`,
      ... days.
    * `status(price, weeks, start, paid, today)`: a dict. `due` is the sum of the scheduled amounts dated on or before
      `today`. Payments are taken to cover the schedule in order, so an item counts as **missed** when it is due and
      the cumulative schedule up to and including it is more than `paid`. `late_fees` is 200 cents per missed item,
      `overdue` is `max(0, due - paid)`. `state` is `"complete"` when `paid >= price`, else `"forfeited"` with 3 or more
      missed items, else `"overdue"` with at least one, else `"on_track"`. The keys are `due`, `paid`, `overdue`,
      `missed`, `late_fees`, `state`.
    * `cancel_refund(price, paid)`: the customer gets back what was paid minus a cancellation fee, never below 0. The
      fee is 15% of the price rounded up, at least 1000 cents. A plan that is already fully paid cannot be cancelled
      (`ValueError`).
''')

LY_SRC = dd('''
    from datetime import timedelta

    MIN_DEPOSIT = 500
    DEPOSIT_PERCENT = 10
    MAX_WEEKS = 12
    STEP = 5
    LATE_FEE = 200
    FORFEIT_AFTER = 3
    CANCEL_PERCENT = 15
    CANCEL_MIN = 1000


    def deposit(price):
        if price <= 0:
            raise ValueError("price must be positive")
        wanted = max(MIN_DEPOSIT, -(-price * DEPOSIT_PERCENT // 100))
        return min(wanted, price)


    def instalments(price, weeks):
        if not 1 <= weeks <= MAX_WEEKS:
            raise ValueError("weeks must be between 1 and 12")
        left = price - deposit(price)
        each = -(-left // weeks)
        each = -(-each // STEP) * STEP
        payments = []
        while left > 0:
            pay = min(each, left)
            payments.append(pay)
            left -= pay
        return payments


    def schedule(price, weeks, start):
        items = [(start, deposit(price))]
        for i, amount in enumerate(instalments(price, weeks), 1):
            items.append((start + timedelta(days=7 * i), amount))
        return items


    def status(price, weeks, start, paid, today):
        due = 0
        missed = 0
        cumulative = 0
        for when, amount in schedule(price, weeks, start):
            cumulative += amount
            if when <= today:
                due += amount
                if paid < cumulative:
                    missed += 1
        if paid >= price:
            state = "complete"
        elif missed >= FORFEIT_AFTER:
            state = "forfeited"
        elif missed:
            state = "overdue"
        else:
            state = "on_track"
        return {"due": due, "paid": paid, "overdue": max(0, due - paid), "missed": missed,
                "late_fees": missed * LATE_FEE, "state": state}


    def cancel_refund(price, paid):
        if paid >= price:
            raise ValueError("the plan is fully paid")
        fee = max(CANCEL_MIN, -(-price * CANCEL_PERCENT // 100))
        return max(0, paid - fee)
''')

LY_VISIBLE = dd('''
    import unittest
    from datetime import date

    from layaway.plan import deposit, instalments, schedule


    class BasicTests(unittest.TestCase):
        def test_deposit(self):
            self.assertEqual(deposit(20_000), 2000)

        def test_instalments(self):
            self.assertEqual(instalments(20_000, 4), [4500] * 4)

        def test_schedule_dates(self):
            self.assertEqual(schedule(20_000, 4, date(2025, 3, 3))[1][0], date(2025, 3, 10))


    if __name__ == "__main__":
        unittest.main()
''')

LY_HIDDEN = dd('''
    import unittest
    from datetime import date

    from layaway.plan import cancel_refund, deposit, instalments, schedule, status

    D = date
    START = D(2025, 3, 3)


    class Deposit(unittest.TestCase):
        def test_values(self):
            table = {20_000: 2000, 5001: 501, 5000: 500, 4999: 500, 300: 300, 500: 500, 501: 500, 9999: 1000, 100_000: 10_000}
            for price, cents in table.items():
                self.assertEqual(deposit(price), cents, price)

        def test_invalid(self):
            for price in (0, -5):
                with self.assertRaises(ValueError):
                    deposit(price)


    class Instalments(unittest.TestCase):
        def test_even_split(self):
            self.assertEqual(instalments(20_000, 4), [4500] * 4)
            self.assertEqual(instalments(20_000, 12), [1500] * 12)
            self.assertEqual(instalments(20_000, 1), [18_000])

        def test_rounding_up_to_five_cents_and_short_last_payment(self):
            self.assertEqual(instalments(20_000, 7), [2575] * 6 + [2550])
            self.assertEqual(instalments(20_000, 5), [3600] * 5)
            self.assertEqual(instalments(20_000, 8), [2250] * 8)
            self.assertEqual(instalments(20_000, 11), [1640] * 10 + [1600])

        def test_fewer_payments_than_weeks(self):
            self.assertEqual(instalments(600, 12), [10] * 10)
            self.assertEqual(instalments(10_000, 12), [750] * 12)

        def test_small_remainder(self):
            self.assertEqual(instalments(1000, 12), [45] * 11 + [5])

        def test_nothing_left(self):
            self.assertEqual(instalments(400, 4), [])
            self.assertEqual(instalments(500, 3), [])

        def test_total_is_price_minus_deposit(self):
            for price in (600, 1000, 12_345, 99_999):
                for weeks in range(1, 13):
                    self.assertEqual(sum(instalments(price, weeks)), price - deposit(price), (price, weeks))
                    self.assertLessEqual(len(instalments(price, weeks)), weeks)

        def test_week_limits(self):
            for weeks in (0, 13, -1):
                with self.assertRaises(ValueError):
                    instalments(20_000, weeks)
            instalments(20_000, 12)
            instalments(20_000, 1)


    class Schedule(unittest.TestCase):
        def test_dates_and_amounts(self):
            self.assertEqual(schedule(20_000, 4, START), [(D(2025, 3, 3), 2000), (D(2025, 3, 10), 4500), (D(2025, 3, 17), 4500),
                                                          (D(2025, 3, 24), 4500), (D(2025, 3, 31), 4500)])

        def test_deposit_only(self):
            self.assertEqual(schedule(400, 4, START), [(START, 400)])

        def test_crosses_a_year(self):
            got = schedule(20_000, 12, D(2025, 12, 15))
            self.assertEqual(got[2][0], D(2025, 12, 29))
            self.assertEqual(got[3][0], D(2026, 1, 5))
            self.assertEqual(len(got), 13)


    class Status(unittest.TestCase):
        def st(self, paid, today, weeks=4):
            return status(20_000, weeks, START, paid, today)

        def test_before_start(self):
            self.assertEqual(self.st(0, D(2025, 3, 2)), {"due": 0, "paid": 0, "overdue": 0, "missed": 0, "late_fees": 0, "state": "on_track"})

        def test_deposit_unpaid(self):
            got = self.st(0, D(2025, 3, 3))
            self.assertEqual((got["due"], got["missed"], got["late_fees"], got["state"]), (2000, 1, 200, "overdue"))
            self.assertEqual(got["overdue"], 2000)

        def test_on_track(self):
            got = self.st(2000, D(2025, 3, 9))
            self.assertEqual(got, {"due": 2000, "paid": 2000, "overdue": 0, "missed": 0, "late_fees": 0, "state": "on_track"})
            got = self.st(6500, D(2025, 3, 12))
            self.assertEqual((got["due"], got["missed"], got["state"]), (6500, 0, "on_track"))

        def test_first_instalment_missed_on_its_due_date(self):
            got = self.st(2000, D(2025, 3, 10))
            self.assertEqual((got["due"], got["overdue"], got["missed"], got["late_fees"], got["state"]), (6500, 4500, 1, 200, "overdue"))
            got = self.st(2000, D(2025, 3, 9))
            self.assertEqual(got["missed"], 0)

        def test_two_missed(self):
            got = self.st(5000, D(2025, 3, 18))
            self.assertEqual((got["due"], got["overdue"], got["missed"], got["late_fees"], got["state"]), (11_000, 6000, 2, 400, "overdue"))

        def test_partial_payments_cover_the_schedule_in_order(self):
            got = self.st(6499, D(2025, 3, 10))
            self.assertEqual((got["missed"], got["overdue"]), (1, 1))
            got = self.st(6500, D(2025, 3, 10))
            self.assertEqual((got["missed"], got["overdue"]), (0, 0))

        def test_forfeited(self):
            got = self.st(2000, D(2025, 3, 24))
            self.assertEqual((got["missed"], got["late_fees"], got["state"]), (3, 600, "forfeited"))
            got = self.st(2000, D(2025, 3, 23))
            self.assertEqual((got["missed"], got["state"]), (2, "overdue"))

        def test_complete(self):
            got = self.st(20_000, D(2025, 3, 3))
            self.assertEqual(got["state"], "complete")
            self.assertEqual((got["missed"], got["late_fees"], got["overdue"]), (0, 0, 0))
            got = self.st(25_000, D(2025, 6, 1))
            self.assertEqual(got["state"], "complete")

        def test_complete_beats_forfeited(self):
            got = status(1000, 12, START, 1000, D(2026, 1, 1))
            self.assertEqual(got["state"], "complete")

        def test_everything_due_in_the_end(self):
            got = self.st(10_000, D(2026, 1, 1))
            self.assertEqual((got["due"], got["overdue"], got["state"]), (20_000, 10_000, "forfeited"))


    class Cancel(unittest.TestCase):
        def test_refund(self):
            self.assertEqual(cancel_refund(20_000, 8000), 5000)
            self.assertEqual(cancel_refund(20_000, 3000), 0)
            self.assertEqual(cancel_refund(20_000, 3001), 1)
            self.assertEqual(cancel_refund(20_000, 19_999), 16_999)

        def test_minimum_fee(self):
            self.assertEqual(cancel_refund(5000, 800), 0)
            self.assertEqual(cancel_refund(5000, 1000), 0)
            self.assertEqual(cancel_refund(5000, 1001), 1)
            self.assertEqual(cancel_refund(6667, 4000), 4000 - 1001)

        def test_fee_rounds_up(self):
            self.assertEqual(cancel_refund(10_001, 5000), 5000 - 1501)
            self.assertEqual(cancel_refund(10_000, 5000), 5000 - 1500)

        def test_nothing_paid(self):
            self.assertEqual(cancel_refund(20_000, 0), 0)

        def test_fully_paid_cannot_be_cancelled(self):
            with self.assertRaises(ValueError):
                cancel_refund(20_000, 20_000)
            with self.assertRaises(ValueError):
                cancel_refund(20_000, 21_000)


    if __name__ == "__main__":
        unittest.main()
''')

LAYAWAY = Lib(
    name="layaway", lang="python", title="the layaway plan rules (`layaway/plan.py`)",
    blurb="The shop's layaway desk builds payment schedules and tracks overdue plans with the layaway module.",
    files={"layaway/__init__.py": "", "layaway/plan.py": LY_SRC, "README.md": LY_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": LY_VISIBLE},
    hidden_tests={"tests/test_full.py": LY_HIDDEN},
    mutate=["layaway/plan.py"], difficulty=2, tags=["instalments", "retail", "dates"],
    probes=[
        "deposit(5001)", "deposit(300)", "deposit(9999)", "instalments(20_000, 7)", "instalments(600, 12)", "instalments(1000, 12)",
        "instalments(400, 4)", "schedule(20_000, 2, date(2025, 3, 3))",
        "status(20_000, 4, date(2025, 3, 3), 2000, date(2025, 3, 10))", "status(20_000, 4, date(2025, 3, 3), 6499, date(2025, 3, 10))",
        "status(20_000, 4, date(2025, 3, 3), 2000, date(2025, 3, 24))['state']", "status(20_000, 4, date(2025, 3, 3), 20_000, date(2025, 3, 3))['state']",
        "cancel_refund(20_000, 8000)", "cancel_refund(5000, 1001)", "cancel_refund(10_001, 5000)",
    ],
    probe_import="from datetime import date\nfrom layaway.plan import *",
)

# ======================================================================================================================
# envelopes: budget envelopes with rollover and caps
# ======================================================================================================================

EN_README = dd('''
    # envelopes

    Envelope budgeting for a household app. Money is an `int` number of cents. An envelope is
    `Envelope(name, budget, cap, balance)`: its monthly allowance, the most it may hold, and what it holds now.

    * `roll_month(envelopes, spent)`: moves every envelope one month on. `spent` maps names to what was spent from
      them this month (missing means 0). The new balance is `balance + budget - spent`, but never more than `cap`;
      overspending leaves a negative balance. Unknown names in `spent` and negative amounts are a `ValueError`.
      Returns a new list in the same order.
    * `allocate_income(income, envelopes)`: pays the month's income into the envelopes in list order. Each one receives
      `min(budget, cap - balance, income left)` (never negative, so a full envelope receives `0`). Returns
      `(allocations, left_over)` with `allocations` a dict name to cents (every envelope is in it).
    * `overspent(envelopes)`: the sorted names of envelopes with a negative balance.
    * `months_until_empty(balance, budget, monthly_spend)`: after how many months an envelope that is topped up with
      `budget` and drained by `monthly_spend` per month has run dry: `0` for a balance of 0 or less, `None` when the
      spending does not exceed the budget, else the balance divided by the monthly shortfall rounded up.
    * `transfer(envelopes, src, dst, amount)`: moves `amount` between two envelopes (new list). It is a `ValueError`
      for `amount <= 0`, unknown names, `src == dst`, a source that would go below zero, or a destination that would
      exceed its cap.
''')

EN_SRC = dd('''
    from collections import namedtuple

    Envelope = namedtuple("Envelope", "name budget cap balance")


    def _names(envelopes):
        return {e.name for e in envelopes}


    def roll_month(envelopes, spent):
        known = _names(envelopes)
        for name, amount in spent.items():
            if name not in known:
                raise ValueError(f"unknown envelope {name!r}")
            if amount < 0:
                raise ValueError("spending must not be negative")
        rolled = []
        for e in envelopes:
            balance = e.balance + e.budget - spent.get(e.name, 0)
            rolled.append(e._replace(balance=min(balance, e.cap)))
        return rolled


    def allocate_income(income, envelopes):
        left = income
        allocations = {}
        for e in envelopes:
            amount = max(0, min(e.budget, e.cap - e.balance, left))
            allocations[e.name] = amount
            left -= amount
        return allocations, left


    def overspent(envelopes):
        return sorted(e.name for e in envelopes if e.balance < 0)


    def months_until_empty(balance, budget, monthly_spend):
        if balance <= 0:
            return 0
        shortfall = monthly_spend - budget
        if shortfall <= 0:
            return None
        return -(-balance // shortfall)


    def transfer(envelopes, src, dst, amount):
        if amount <= 0:
            raise ValueError("amount must be positive")
        if src == dst:
            raise ValueError("source and destination are the same")
        by_name = {e.name: e for e in envelopes}
        if src not in by_name or dst not in by_name:
            raise ValueError("unknown envelope")
        if by_name[src].balance - amount < 0:
            raise ValueError("not enough money in the source envelope")
        if by_name[dst].balance + amount > by_name[dst].cap:
            raise ValueError("the destination would exceed its cap")
        out = []
        for e in envelopes:
            if e.name == src:
                e = e._replace(balance=e.balance - amount)
            elif e.name == dst:
                e = e._replace(balance=e.balance + amount)
            out.append(e)
        return out
''')

EN_VISIBLE = dd('''
    import unittest

    from envelopes.budget import Envelope, allocate_income, roll_month


    class BasicTests(unittest.TestCase):
        def test_roll(self):
            got = roll_month([Envelope("food", 40_000, 80_000, 10_000)], {"food": 35_000})
            self.assertEqual(got[0].balance, 15_000)

        def test_allocate(self):
            envs = [Envelope("rent", 90_000, 90_000, 0), Envelope("food", 40_000, 80_000, 0)]
            self.assertEqual(allocate_income(100_000, envs), ({"rent": 90_000, "food": 10_000}, 0))


    if __name__ == "__main__":
        unittest.main()
''')

EN_HIDDEN = dd('''
    import unittest

    from envelopes.budget import Envelope, allocate_income, months_until_empty, overspent, roll_month, transfer

    E = Envelope


    class Roll(unittest.TestCase):
        def test_carry_over(self):
            got = roll_month([E("food", 40_000, 80_000, 10_000)], {"food": 35_000})
            self.assertEqual(got, [E("food", 40_000, 80_000, 15_000)])

        def test_missing_spending_is_zero(self):
            got = roll_month([E("fun", 5000, 20_000, 1000), E("food", 40_000, 80_000, 0)], {})
            self.assertEqual([e.balance for e in got], [6000, 40_000])

        def test_cap(self):
            got = roll_month([E("fun", 5000, 20_000, 18_000)], {"fun": 1000})
            self.assertEqual(got[0].balance, 20_000)
            got = roll_month([E("fun", 5000, 20_000, 16_000)], {"fun": 1000})
            self.assertEqual(got[0].balance, 20_000)
            got = roll_month([E("fun", 5000, 20_000, 15_999)], {"fun": 1000})
            self.assertEqual(got[0].balance, 19_999)

        def test_overspending(self):
            got = roll_month([E("fun", 5000, 20_000, 1000)], {"fun": 9000})
            self.assertEqual(got[0].balance, -3000)

        def test_order_and_other_fields_are_kept(self):
            envs = [E("b", 1, 100, 5), E("a", 2, 200, 6)]
            got = roll_month(envs, {"a": 1})
            self.assertEqual(got, [E("b", 1, 100, 6), E("a", 2, 200, 7)])
            self.assertEqual(envs[0].balance, 5)

        def test_errors(self):
            envs = [E("food", 40_000, 80_000, 0)]
            with self.assertRaises(ValueError):
                roll_month(envs, {"rent": 10})
            with self.assertRaises(ValueError):
                roll_month(envs, {"food": -1})
            roll_month(envs, {"food": 0})


    class Allocate(unittest.TestCase):
        def test_in_order_until_the_money_runs_out(self):
            envs = [E("rent", 90_000, 90_000, 0), E("food", 40_000, 80_000, 0), E("fun", 5000, 20_000, 0)]
            self.assertEqual(allocate_income(100_000, envs), ({"rent": 90_000, "food": 10_000, "fun": 0}, 0))
            self.assertEqual(allocate_income(135_000, envs), ({"rent": 90_000, "food": 40_000, "fun": 5000}, 0))
            self.assertEqual(allocate_income(140_000, envs), ({"rent": 90_000, "food": 40_000, "fun": 5000}, 5000))

        def test_only_up_to_the_cap(self):
            envs = [E("fun", 5000, 20_000, 18_000), E("food", 40_000, 80_000, 0)]
            self.assertEqual(allocate_income(100_000, envs), ({"fun": 2000, "food": 40_000}, 58_000))

        def test_full_envelope_gets_nothing(self):
            envs = [E("fun", 5000, 20_000, 20_000), E("x", 100, 1000, 1000)]
            self.assertEqual(allocate_income(1000, envs), ({"fun": 0, "x": 0}, 1000))

        def test_negative_balance_is_refilled_up_to_the_budget_only(self):
            envs = [E("fun", 5000, 20_000, -3000)]
            self.assertEqual(allocate_income(100_000, envs), ({"fun": 5000}, 95_000))

        def test_no_income(self):
            envs = [E("fun", 5000, 20_000, 0)]
            self.assertEqual(allocate_income(0, envs), ({"fun": 0}, 0))

        def test_no_envelopes(self):
            self.assertEqual(allocate_income(500, []), ({}, 500))


    class Overspent(unittest.TestCase):
        def test_names(self):
            envs = [E("z", 1, 9, -1), E("a", 1, 9, -50), E("m", 1, 9, 0), E("q", 1, 9, 3)]
            self.assertEqual(overspent(envs), ["a", "z"])
            self.assertEqual(overspent([]), [])


    class Empty(unittest.TestCase):
        def test_values(self):
            self.assertEqual(months_until_empty(10_000, 4000, 5000), 10)
            self.assertEqual(months_until_empty(10_001, 4000, 5000), 11)
            self.assertEqual(months_until_empty(10_000, 4000, 4001), 10_000)
            self.assertEqual(months_until_empty(100, 0, 40), 3)
            self.assertEqual(months_until_empty(120, 0, 40), 3)

        def test_never(self):
            self.assertIsNone(months_until_empty(10_000, 5000, 5000))
            self.assertIsNone(months_until_empty(10_000, 5000, 100))

        def test_already_empty(self):
            self.assertEqual(months_until_empty(0, 4000, 5000), 0)
            self.assertEqual(months_until_empty(-5, 4000, 5000), 0)
            self.assertEqual(months_until_empty(0, 4000, 100), 0)


    class Transfer(unittest.TestCase):
        ENVS = [E("food", 40_000, 80_000, 30_000), E("fun", 5000, 20_000, 10_000), E("rent", 90_000, 90_000, 0)]

        def test_moves_money(self):
            got = transfer(self.ENVS, "food", "fun", 4000)
            self.assertEqual([e.balance for e in got], [26_000, 14_000, 0])
            self.assertEqual([e.name for e in got], ["food", "fun", "rent"])
            self.assertEqual(self.ENVS[0].balance, 30_000)

        def test_exact_amounts(self):
            got = transfer(self.ENVS, "food", "fun", 10_000)
            self.assertEqual([e.balance for e in got], [20_000, 20_000, 0])
            got = transfer(self.ENVS, "food", "rent", 30_000)
            self.assertEqual([e.balance for e in got], [0, 10_000, 30_000])

        def test_errors(self):
            bad = [("food", "fun", 0), ("food", "fun", -1), ("food", "food", 5), ("food", "fun", 30_001), ("food", "fun", 10_001),
                   ("fun", "food", 50_001), ("nope", "fun", 5), ("food", "nope", 5)]
            for src, dst, amount in bad:
                with self.assertRaises(ValueError, msg=(src, dst, amount)):
                    transfer(self.ENVS, src, dst, amount)


    if __name__ == "__main__":
        unittest.main()
''')

ENVELOPES = Lib(
    name="envelopes", lang="python", title="the budget-envelope helpers (`envelopes/budget.py`)",
    blurb="The household budgeting app rolls spending envelopes from month to month with the envelopes module.",
    files={"envelopes/__init__.py": "", "envelopes/budget.py": EN_SRC, "README.md": EN_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": EN_VISIBLE},
    hidden_tests={"tests/test_full.py": EN_HIDDEN},
    mutate=["envelopes/budget.py"], difficulty=1, tags=["budget", "envelopes", "money"],
    probes=[
        "roll_month([Envelope('fun', 5000, 20_000, 16_000)], {'fun': 1000})[0].balance",
        "roll_month([Envelope('fun', 5000, 20_000, 1000)], {'fun': 9000})[0].balance",
        "allocate_income(100_000, [Envelope('rent', 90_000, 90_000, 0), Envelope('food', 40_000, 80_000, 0)])",
        "allocate_income(1000, [Envelope('fun', 5000, 20_000, 20_000)])",
        "allocate_income(100_000, [Envelope('fun', 5000, 20_000, -3000)])",
        "overspent([Envelope('z', 1, 9, -1), Envelope('a', 1, 9, -50), Envelope('m', 1, 9, 0)])",
        "months_until_empty(10_001, 4000, 5000)", "months_until_empty(10_000, 5000, 5000)", "months_until_empty(0, 4000, 5000)",
        "[e.balance for e in transfer([Envelope('a', 1, 100, 30), Envelope('b', 1, 100, 10)], 'a', 'b', 30)]",
    ],
    probe_import="from envelopes.budget import *",
)

register_libs([ARREARS, LAYAWAY, ENVELOPES], n=10)
