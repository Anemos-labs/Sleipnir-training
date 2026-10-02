"""Python libraries, theme time/money/scheduling (batch money-a): invented land-transfer duty, payroll bands, invoice
numbering and allocation, currency desk with spreads."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# veldmark: land-transfer duty of an invented republic
# ======================================================================================================================

VM_README = dd('''
    # veldmark

    Land-transfer duty of the Republic of Veldmark. Prices and duty are whole marks (`int`). Rates are in basis
    points (1 bp = 0.01%).

    ## Bands (`veldmark/bands.py`)

    The standard rates are marginal: the rate of a band applies only to the part of the price inside that band.

    | price from | to | rate |
    |-----------:|---:|-----:|
    | 0 | 150 000 | 0 bp |
    | 150 000 | 400 000 | 200 bp |
    | 400 000 | 900 000 | 500 bp |
    | 900 000 | no limit | 900 bp |

    `band_numerator(price)` is the sum over the bands of `part of the price in the band * rate in bp`.
    `round_div(n, d)` is `n / d` rounded half up for `n >= 0`, `d > 0`.

    ## Duty (`veldmark/duty.py`)

    `surcharge_bp(investment, resident)`: 300 bp for an investment property plus 200 bp for a non-resident buyer
    (the two add up).

    `transfer_duty(price, investment=False, resident=True, first_time=False)`:

    * `price <= 0` is a `ValueError`. A price below 20 000 is a nominal transfer: duty `0`, no surcharge either.
    * The duty is `round_div(band_numerator(price) + price * surcharge_bp(...), 10000)`: one rounding for the whole
      amount, surcharges apply to the **whole price**.
    * A first-time buyer who is a resident and buys a non-investment property gets a relief off the rounded duty
      (never below `0`): `relief(price)`. Nobody else gets it.

    `relief(price)` is `3000` up to and including a price of 450 000; between 450 000 and 600 000 (exclusive) it
    shrinks to `3000 * (600000 - price) // 150000`; from 600 000 it is `0`.

    `effective_rate_bp(price, **options)` is `duty * 10000 // price` (rounded down); the options are those of
    `transfer_duty`.

    ## Lodging (`veldmark/lodge.py`)

    The duty must be lodged within 30 days of the contract date: `lodgement_deadline(contract_date)` is the contract
    date plus 30 days, moved to the following Monday when that is a Saturday or a Sunday.

    `penalty(duty, days_late)`: nothing for `days_late <= 0`; otherwise 1% of the duty for every **started** week
    late, at most 25%, rounded down to whole marks.

    `total_due(duty, contract_date, lodged_on)` is the duty plus the penalty for the days after the deadline.
''')

VM_BANDS = dd('''
    BANDS = [(0, 0), (150_000, 200), (400_000, 500), (900_000, 900)]


    def band_numerator(price):
        total = 0
        for i, (low, bp) in enumerate(BANDS):
            high = BANDS[i + 1][0] if i + 1 < len(BANDS) else None
            if price <= low:
                break
            top = price if high is None else min(price, high)
            total += (top - low) * bp
        return total


    def round_div(n, d):
        return (2 * n + d) // (2 * d)
''')

VM_DUTY = dd('''
    from .bands import band_numerator, round_div

    NOMINAL_BELOW = 20_000
    INVESTMENT_BP = 300
    NON_RESIDENT_BP = 200
    FULL_RELIEF = 3000
    RELIEF_FULL_UNTIL = 450_000
    RELIEF_ENDS = 600_000


    def surcharge_bp(investment, resident):
        bp = 0
        if investment:
            bp += INVESTMENT_BP
        if not resident:
            bp += NON_RESIDENT_BP
        return bp


    def relief(price):
        if price <= RELIEF_FULL_UNTIL:
            return FULL_RELIEF
        if price < RELIEF_ENDS:
            return FULL_RELIEF * (RELIEF_ENDS - price) // (RELIEF_ENDS - RELIEF_FULL_UNTIL)
        return 0


    def transfer_duty(price, investment=False, resident=True, first_time=False):
        if price <= 0:
            raise ValueError("price must be positive")
        if price < NOMINAL_BELOW:
            return 0
        numerator = band_numerator(price) + price * surcharge_bp(investment, resident)
        duty = round_div(numerator, 10_000)
        if first_time and resident and not investment:
            duty = max(0, duty - relief(price))
        return duty


    def effective_rate_bp(price, **options):
        return transfer_duty(price, **options) * 10_000 // price
''')

VM_LODGE = dd('''
    from datetime import timedelta

    LODGE_DAYS = 30
    PENALTY_CAP_PERCENT = 25


    def lodgement_deadline(contract_date):
        due = contract_date + timedelta(days=LODGE_DAYS)
        if due.weekday() == 5:
            due += timedelta(days=2)
        elif due.weekday() == 6:
            due += timedelta(days=1)
        return due


    def penalty(duty, days_late):
        if days_late <= 0:
            return 0
        weeks = -(-days_late // 7)
        percent = min(weeks, PENALTY_CAP_PERCENT)
        return duty * percent // 100


    def total_due(duty, contract_date, lodged_on):
        late = (lodged_on - lodgement_deadline(contract_date)).days
        return duty + penalty(duty, late)
''')

VM_VISIBLE = dd('''
    import unittest
    from datetime import date

    from veldmark.bands import band_numerator
    from veldmark.duty import transfer_duty
    from veldmark.lodge import lodgement_deadline


    class BasicTests(unittest.TestCase):
        def test_numerator(self):
            self.assertEqual(band_numerator(200_000), 10_000_000)

        def test_duty_mid_price(self):
            self.assertEqual(transfer_duty(400_000), 5000)

        def test_deadline(self):
            self.assertEqual(lodgement_deadline(date(2025, 3, 3)), date(2025, 4, 2))


    if __name__ == "__main__":
        unittest.main()
''')

VM_HIDDEN = dd('''
    import unittest
    from datetime import date

    from veldmark.bands import band_numerator, round_div
    from veldmark.duty import effective_rate_bp, relief, surcharge_bp, transfer_duty
    from veldmark.lodge import lodgement_deadline, penalty, total_due


    class Bands(unittest.TestCase):
        def test_numerator_values(self):
            table = {1: 0, 100_000: 0, 150_000: 0, 150_001: 200, 200_000: 10_000_000, 400_000: 50_000_000,
                     400_001: 50_000_500, 500_000: 100_000_000, 900_000: 300_000_000, 900_001: 300_000_900,
                     1_000_000: 390_000_000, 2_000_000: 1_290_000_000}
            for price, numer in table.items():
                self.assertEqual(band_numerator(price), numer, price)

        def test_zero(self):
            self.assertEqual(band_numerator(0), 0)

        def test_round_div(self):
            self.assertEqual(round_div(5, 10), 1)
            self.assertEqual(round_div(4, 10), 0)
            self.assertEqual(round_div(15, 10), 2)
            self.assertEqual(round_div(14, 10), 1)
            self.assertEqual(round_div(0, 7), 0)
            self.assertEqual(round_div(7, 7), 1)
            self.assertEqual(round_div(10_000, 10_000), 1)
            self.assertEqual(round_div(25_000, 10_000), 3)


    class Duty(unittest.TestCase):
        def test_plain(self):
            table = {20_000: 0, 100_000: 0, 150_000: 0, 200_000: 1000, 400_000: 5000, 500_000: 10_000,
                     900_000: 30_000, 1_000_000: 39_000}
            for price, duty in table.items():
                self.assertEqual(transfer_duty(price), duty, price)

        def test_rounding_is_half_up_and_once(self):
            self.assertEqual(transfer_duty(150_003), 0)
            self.assertEqual(transfer_duty(150_024), 0)
            self.assertEqual(transfer_duty(150_025), 1)
            self.assertEqual(transfer_duty(150_026), 1)
            self.assertEqual(transfer_duty(150_075), 2)
            self.assertEqual(transfer_duty(400_001), 5000)
            self.assertEqual(transfer_duty(400_009), 5000)
            self.assertEqual(transfer_duty(400_010), 5001)
            self.assertEqual(transfer_duty(400_011), 5001)

        def test_nominal_transfers(self):
            self.assertEqual(transfer_duty(1), 0)
            self.assertEqual(transfer_duty(19_999), 0)
            self.assertEqual(transfer_duty(19_999, investment=True, resident=False), 0)
            self.assertEqual(transfer_duty(20_000, investment=True), 600)
            self.assertEqual(transfer_duty(20_000, resident=False), 400)

        def test_bad_price(self):
            for price in (0, -1, -250_000):
                with self.assertRaises(ValueError):
                    transfer_duty(price)

        def test_surcharges(self):
            self.assertEqual(surcharge_bp(False, True), 0)
            self.assertEqual(surcharge_bp(True, True), 300)
            self.assertEqual(surcharge_bp(False, False), 200)
            self.assertEqual(surcharge_bp(True, False), 500)
            self.assertEqual(transfer_duty(200_000, investment=True), 7000)
            self.assertEqual(transfer_duty(200_000, resident=False), 5000)
            self.assertEqual(transfer_duty(200_000, investment=True, resident=False), 11_000)
            self.assertEqual(transfer_duty(100_000, investment=True), 3000)
            self.assertEqual(transfer_duty(1_000_000, investment=True, resident=False), 89_000)

        def test_surcharge_rounding_is_in_the_single_rounding(self):
            self.assertEqual(transfer_duty(20_001, investment=True), 600)
            self.assertEqual(transfer_duty(20_002, investment=True), 600)
            self.assertEqual(transfer_duty(20_020, investment=True), 601)
            self.assertEqual(transfer_duty(20_024, resident=False, investment=False), 400)
            self.assertEqual(transfer_duty(20_025, resident=False, investment=False), 401)

        def test_relief_values(self):
            table = {1: 3000, 250_000: 3000, 450_000: 3000, 450_001: 2999, 525_000: 1500, 599_999: 0, 600_000: 0, 900_000: 0}
            for price, amount in table.items():
                self.assertEqual(relief(price), amount, price)

        def test_first_time_buyers(self):
            self.assertEqual(transfer_duty(250_000, first_time=True), 0)
            self.assertEqual(transfer_duty(450_000, first_time=True), 4500)
            self.assertEqual(transfer_duty(450_001, first_time=True), 4501)
            self.assertEqual(transfer_duty(525_000, first_time=True), 9750)
            self.assertEqual(transfer_duty(599_999, first_time=True), transfer_duty(599_999))
            self.assertEqual(transfer_duty(600_000, first_time=True), transfer_duty(600_000))
            self.assertEqual(transfer_duty(300_000, first_time=True), 0)
            self.assertEqual(transfer_duty(350_000, first_time=True), 1000)
            self.assertEqual(transfer_duty(380_000, first_time=True), 1600)

        def test_relief_is_only_for_resident_owner_occupiers(self):
            self.assertEqual(transfer_duty(450_000, first_time=True, investment=True), 7500 + 13_500)
            self.assertEqual(transfer_duty(450_000, first_time=True, resident=False), 7500 + 9000)
            self.assertEqual(transfer_duty(450_000, first_time=False), 7500)

        def test_effective_rate(self):
            self.assertEqual(effective_rate_bp(500_000), 200)
            self.assertEqual(effective_rate_bp(1_000_000), 390)
            self.assertEqual(effective_rate_bp(100_000), 0)
            self.assertEqual(effective_rate_bp(200_000, investment=True), 350)
            self.assertEqual(effective_rate_bp(450_000, first_time=True), 100)
            self.assertEqual(effective_rate_bp(333_333), 110)


    class Lodging(unittest.TestCase):
        def test_deadline(self):
            self.assertEqual(lodgement_deadline(date(2025, 3, 3)), date(2025, 4, 2))
            self.assertEqual(lodgement_deadline(date(2025, 3, 7)), date(2025, 4, 7))
            self.assertEqual(lodgement_deadline(date(2025, 3, 6)), date(2025, 4, 7))
            self.assertEqual(lodgement_deadline(date(2025, 3, 8)), date(2025, 4, 7))
            self.assertEqual(lodgement_deadline(date(2025, 3, 5)), date(2025, 4, 4))
            self.assertEqual(lodgement_deadline(date(2025, 12, 20)), date(2026, 1, 19))
            self.assertEqual(lodgement_deadline(date(2024, 1, 31)), date(2024, 3, 1))

        def test_penalty(self):
            table = {-3: 0, 0: 0, 1: 100, 7: 100, 8: 200, 14: 200, 15: 300, 70: 1000, 175: 2500, 176: 2500, 400: 2500}
            for late, amount in table.items():
                self.assertEqual(penalty(10_000, late), amount, late)

        def test_penalty_rounds_down(self):
            self.assertEqual(penalty(99, 1), 0)
            self.assertEqual(penalty(250, 15), 7)
            self.assertEqual(penalty(199, 1), 1)

        def test_total_due(self):
            contract = date(2025, 3, 3)
            self.assertEqual(total_due(10_000, contract, date(2025, 4, 2)), 10_000)
            self.assertEqual(total_due(10_000, contract, date(2025, 3, 20)), 10_000)
            self.assertEqual(total_due(10_000, contract, date(2025, 4, 3)), 10_100)
            self.assertEqual(total_due(10_000, contract, date(2025, 4, 9)), 10_100)
            self.assertEqual(total_due(10_000, contract, date(2025, 4, 10)), 10_200)
            self.assertEqual(total_due(10_000, date(2025, 3, 7), date(2025, 4, 7)), 10_000)
            self.assertEqual(total_due(10_000, date(2025, 3, 7), date(2025, 4, 8)), 10_100)


    if __name__ == "__main__":
        unittest.main()
''')

VELDMARK = Lib(
    name="veldmark", lang="python", title="the Veldmark transfer-duty calculator (`veldmark/`)",
    blurb="The conveyancing office computes the duty on a property purchase and the lodging deadline with veldmark.",
    files={"veldmark/__init__.py": "", "veldmark/bands.py": VM_BANDS, "veldmark/duty.py": VM_DUTY,
           "veldmark/lodge.py": VM_LODGE, "README.md": VM_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": VM_VISIBLE},
    hidden_tests={"tests/test_full.py": VM_HIDDEN},
    mutate=["veldmark/bands.py", "veldmark/duty.py", "veldmark/lodge.py"], difficulty=2, tags=["tax", "bands", "rounding"],
    probes=[
        "band_numerator(400_001)", "round_div(25_000, 10_000)", "transfer_duty(150_025)", "transfer_duty(19_999, investment=True)",
        "transfer_duty(200_000, investment=True, resident=False)", "relief(450_001)", "relief(600_000)",
        "transfer_duty(450_000, first_time=True)", "transfer_duty(450_000, first_time=True, investment=True)",
        "transfer_duty(525_000, first_time=True)", "effective_rate_bp(333_333)",
        "lodgement_deadline(date(2025, 3, 6))", "lodgement_deadline(date(2025, 3, 5))", "penalty(10_000, 8)", "penalty(10_000, 176)",
        "total_due(10_000, date(2025, 3, 3), date(2025, 4, 3))",
    ],
    probe_import="from datetime import date\nfrom veldmark.bands import *\nfrom veldmark.duty import *\nfrom veldmark.lodge import *",
)

# ======================================================================================================================
# norrpay: gross-to-net payroll for an invented country (half-even rounding, tapered allowance, age-based employer rate)
# ======================================================================================================================

NP_README = dd('''
    # norrpay

    Monthly gross-to-net pay for the Norrland payroll office. Money is an `int` number of cents.

    ## Rounding (`norrpay/rounding.py`)

    `div_half_even(n, d)` is `n / d` rounded to the nearest integer, ties to the even integer, for `n >= 0` and
    `d > 0`: `div_half_even(5, 2) == 2`, `div_half_even(7, 2) == 4`, `div_half_even(1, 3) == 0`. Every amount below
    is rounded **once** with it, from an exact numerator.

    ## Components (`norrpay/components.py`)

    * `pension(gross)`: the employee contributes 6% of the pensionable pay, which is the part of the gross between
      800.00 and 7000.00 (`80_000` and `700_000` cents): `min(gross, 700_000) - 80_000`, or `0` when the gross does
      not exceed `80_000`.
    * `allowance(gross)`: the tax-free allowance is `110_000`, but for a gross above `1_000_000` it is reduced by
      half of the excess (`(gross - 1_000_000) // 2`, never below `0`).
    * `income_tax(taxable)`: marginal bands on the taxable amount: 10% up to `200_000`, 24% from `200_000` to
      `600_000`, 41% above. Zero or negative taxable amounts owe `0`.
    * `social(gross)`: social contribution of 7.5% of the gross up to `500_000` plus 2% of the part above it.

    ## Pay slip (`norrpay/payslip.py`)

    `payslip(gross)` returns a dict with the keys `gross`, `pension`, `allowance`, `taxable`, `tax`, `social`,
    `net`. The pension is deducted before tax: `taxable = max(0, gross - pension - allowance)`;
    `net = gross - pension - tax - social`. A negative gross is a `ValueError`.

    `employer_cost(gross, age)`: the gross plus the employer's contribution. The contribution is 14.1% of the gross,
    except for employees younger than 25 or aged 67 or older, for whom the first `300_000` of the gross carries
    only 7.1% (the rest 14.1%). The contribution is rounded once. `age < 16` is a `ValueError`.

    `year_to_date(grosses)`: the pay slips of each monthly gross in `grosses` added up key by key (`allowance` and
    `taxable` too); an empty list gives all zeros.
''')

NP_ROUNDING = dd('''
    def div_half_even(n, d):
        q, r = divmod(n, d)
        if 2 * r > d or (2 * r == d and q % 2 == 1):
            q += 1
        return q
''')

NP_COMPONENTS = dd('''
    from .rounding import div_half_even

    PENSION_LOWER = 80_000
    PENSION_UPPER = 700_000
    ALLOWANCE = 110_000
    TAPER_FROM = 1_000_000
    TAX_BANDS = [(0, 10), (200_000, 24), (600_000, 41)]
    SOCIAL_CEILING = 500_000


    def pension(gross):
        if gross <= PENSION_LOWER:
            return 0
        pensionable = min(gross, PENSION_UPPER) - PENSION_LOWER
        return div_half_even(pensionable * 6, 100)


    def allowance(gross):
        if gross <= TAPER_FROM:
            return ALLOWANCE
        return max(0, ALLOWANCE - (gross - TAPER_FROM) // 2)


    def income_tax(taxable):
        total = 0
        for i, (low, percent) in enumerate(TAX_BANDS):
            high = TAX_BANDS[i + 1][0] if i + 1 < len(TAX_BANDS) else None
            if taxable <= low:
                break
            top = taxable if high is None else min(taxable, high)
            total += (top - low) * percent
        return div_half_even(total, 100)


    def social(gross):
        base = min(gross, SOCIAL_CEILING)
        extra = max(0, gross - SOCIAL_CEILING)
        return div_half_even(base * 75 + extra * 20, 1000)
''')

NP_PAYSLIP = dd('''
    from .components import allowance, income_tax, pension, social
    from .rounding import div_half_even

    KEYS = ("gross", "pension", "allowance", "taxable", "tax", "social", "net")


    def payslip(gross):
        if gross < 0:
            raise ValueError("gross pay must not be negative")
        p = pension(gross)
        a = allowance(gross)
        taxable = max(0, gross - p - a)
        t = income_tax(taxable)
        s = social(gross)
        return {"gross": gross, "pension": p, "allowance": a, "taxable": taxable, "tax": t, "social": s,
                "net": gross - p - t - s}


    def employer_cost(gross, age):
        if age < 16:
            raise ValueError("employees must be at least 16")
        if age < 25 or age >= 67:
            reduced = min(gross, 300_000)
            contribution = div_half_even(reduced * 71 + (gross - reduced) * 141, 1000)
        else:
            contribution = div_half_even(gross * 141, 1000)
        return gross + contribution


    def year_to_date(grosses):
        totals = {key: 0 for key in KEYS}
        for gross in grosses:
            for key, value in payslip(gross).items():
                totals[key] += value
        return totals
''')

NP_VISIBLE = dd('''
    import unittest

    from norrpay.components import pension, social
    from norrpay.payslip import payslip
    from norrpay.rounding import div_half_even


    class BasicTests(unittest.TestCase):
        def test_div(self):
            self.assertEqual(div_half_even(7, 2), 4)

        def test_pension(self):
            self.assertEqual(pension(180_000), 6000)

        def test_social(self):
            self.assertEqual(social(100_000), 7500)

        def test_payslip_net(self):
            self.assertEqual(payslip(0)["net"], 0)


    if __name__ == "__main__":
        unittest.main()
''')

NP_HIDDEN = dd('''
    import unittest
    from fractions import Fraction

    from norrpay.components import allowance, income_tax, pension, social
    from norrpay.payslip import employer_cost, payslip, year_to_date
    from norrpay.rounding import div_half_even


    def half_even(x):
        return round(Fraction(x))  # Python rounds Fractions half to even


    class Rounding(unittest.TestCase):
        def test_ties_go_to_even(self):
            table = {(1, 2): 0, (3, 2): 2, (5, 2): 2, (7, 2): 4, (9, 2): 4, (5, 10): 0, (15, 10): 2, (25, 10): 2,
                     (35, 10): 4, (0, 5): 0, (1, 3): 0, (2, 3): 1, (4, 3): 1, (5, 3): 2, (10, 5): 2, (7, 7): 1}
            for (n, d), want in table.items():
                self.assertEqual(div_half_even(n, d), want, (n, d))

        def test_against_fractions(self):
            for d in (1, 2, 3, 4, 6, 7, 10, 100, 1000):
                for n in range(0, 400):
                    self.assertEqual(div_half_even(n, d), half_even(Fraction(n, d)), (n, d))


    class Components(unittest.TestCase):
        def test_pension(self):
            table = {0: 0, 80_000: 0, 80_001: 0, 80_009: 1, 80_008: 0, 80_025: 2, 80_075: 4, 180_000: 6000, 500_000: 25_200,
                     700_000: 37_200, 700_001: 37_200, 2_000_000: 37_200}
            for gross, want in table.items():
                self.assertEqual(pension(gross), want, gross)

        def test_pension_rounds_half_even(self):
            # 6% of 25 cents is 1.5 -> 2 ; of 75 cents is 4.5 -> 4 ; of 125 is 7.5 -> 8
            self.assertEqual(pension(80_000 + 25), 2)
            self.assertEqual(pension(80_000 + 75), 4)
            self.assertEqual(pension(80_000 + 125), 8)
            self.assertEqual(pension(80_000 + 8), 0)

        def test_allowance(self):
            table = {0: 110_000, 500_000: 110_000, 1_000_000: 110_000, 1_000_001: 110_000, 1_000_002: 109_999,
                     1_100_000: 60_000, 1_219_999: 1, 1_220_000: 0, 1_300_000: 0, 5_000_000: 0}
            for gross, want in table.items():
                self.assertEqual(allowance(gross), want, gross)

        def test_income_tax(self):
            table = {-100: 0, 0: 0, 1: 0, 5: 0, 6: 1, 200_000: 20_000, 200_001: 20_000, 200_002: 20_000, 300_000: 44_000,
                     600_000: 116_000, 600_001: 116_000, 600_002: 116_001, 1_000_000: 280_000}
            for taxable, want in table.items():
                self.assertEqual(income_tax(taxable), want, taxable)

        def test_income_tax_rounds_once(self):
            # 10% of 5 is 0.5 -> 0 ; of 15 is 1.5 -> 2 ; 24% of 200_000 + 2 adds 0.48 -> total 20_000.48 -> 20_000
            self.assertEqual(income_tax(5), 0)
            self.assertEqual(income_tax(15), 2)
            self.assertEqual(income_tax(25), 2)
            self.assertEqual(income_tax(35), 4)
            self.assertEqual(income_tax(200_000 + 3), 20_001)
            self.assertEqual(income_tax(200_000 + 2), 20_000)

        def test_social(self):
            table = {0: 0, 100_000: 7500, 500_000: 37_500, 500_001: 37_500, 500_026: 37_501, 600_000: 39_500, 1_000_000: 47_500,
                     13: 1, 6: 0, 7: 1, 20: 2, 60: 4}
            for gross, want in table.items():
                self.assertEqual(social(gross), want, gross)

        def test_social_rounds_half_even(self):
            self.assertEqual(social(20), 2)   # 1.5 -> 2
            self.assertEqual(social(60), 4)   # 4.5 -> 4
            self.assertEqual(social(100), 8)  # 7.5 -> 8


    class Payslip(unittest.TestCase):
        def test_low_pay(self):
            p = payslip(80_000)
            self.assertEqual(p, {"gross": 80_000, "pension": 0, "allowance": 110_000, "taxable": 0, "tax": 0, "social": 6000,
                                 "net": 74_000})

        def test_typical(self):
            p = payslip(400_000)
            self.assertEqual(p["pension"], 19_200)
            self.assertEqual(p["allowance"], 110_000)
            self.assertEqual(p["taxable"], 270_800)
            self.assertEqual(p["tax"], 20_000 + 16_992)
            self.assertEqual(p["social"], 30_000)
            self.assertEqual(p["net"], 400_000 - 19_200 - 36_992 - 30_000)

        def test_high_pay(self):
            p = payslip(1_200_000)
            self.assertEqual(p["pension"], 37_200)
            self.assertEqual(p["allowance"], 10_000)
            self.assertEqual(p["taxable"], 1_152_800)
            self.assertEqual(p["tax"], 20_000 + 96_000 + 226_648)
            self.assertEqual(p["social"], 37_500 + 14_000)
            self.assertEqual(p["net"], 1_200_000 - 37_200 - 342_648 - 51_500)

        def test_zero(self):
            self.assertEqual(payslip(0)["net"], 0)
            self.assertEqual(payslip(0)["taxable"], 0)

        def test_negative(self):
            with self.assertRaises(ValueError):
                payslip(-1)

        def test_net_adds_up_everywhere(self):
            for gross in (0, 1, 79_999, 80_000, 80_001, 123_456, 499_999, 500_000, 500_001, 699_999, 700_001, 999_999,
                          1_000_001, 1_219_999, 1_220_001, 2_345_678):
                p = payslip(gross)
                self.assertEqual(p["net"], p["gross"] - p["pension"] - p["tax"] - p["social"], gross)
                self.assertEqual(p["pension"], pension(gross))
                self.assertEqual(p["tax"], income_tax(p["taxable"]))
                self.assertEqual(p["taxable"], max(0, gross - p["pension"] - p["allowance"]))
                self.assertGreaterEqual(p["net"], 0)

        def test_pension_reduces_taxable_pay(self):
            p = payslip(700_000)
            self.assertEqual(p["taxable"], 700_000 - 37_200 - 110_000)

        def test_employer_cost(self):
            self.assertEqual(employer_cost(100_000, 30), 114_100)
            self.assertEqual(employer_cost(1_000_000, 40), 1_141_000)
            self.assertEqual(employer_cost(0, 30), 0)

        def test_employer_cost_ages(self):
            self.assertEqual(employer_cost(100_000, 24), 107_100)
            self.assertEqual(employer_cost(100_000, 25), 114_100)
            self.assertEqual(employer_cost(100_000, 66), 114_100)
            self.assertEqual(employer_cost(100_000, 67), 107_100)
            self.assertEqual(employer_cost(100_000, 16), 107_100)
            self.assertEqual(employer_cost(300_000, 20), 321_300)
            self.assertEqual(employer_cost(500_000, 20), 500_000 + 21_300 + 28_200)
            self.assertEqual(employer_cost(300_001, 70), 300_001 + 21_300)
            self.assertEqual(employer_cost(310_000, 70), 310_000 + 21_300 + 1410)

        def test_employer_cost_rounding(self):
            self.assertEqual(employer_cost(50, 30), 57)   # 7.05 -> 7
            self.assertEqual(employer_cost(10, 30), 11)   # 1.41 -> 1
            self.assertEqual(employer_cost(7, 20), 7)     # 0.497 -> 0
            self.assertEqual(employer_cost(1_000, 30), 1141)

        def test_employer_age_limit(self):
            for age in (15, 0, -3):
                with self.assertRaises(ValueError):
                    employer_cost(100_000, age)


    class YearToDate(unittest.TestCase):
        def test_empty(self):
            self.assertEqual(year_to_date([]), {k: 0 for k in ("gross", "pension", "allowance", "taxable", "tax", "social", "net")})

        def test_sums(self):
            months = [400_000] * 11 + [1_200_000]
            ytd = year_to_date(months)
            one, big = payslip(400_000), payslip(1_200_000)
            for key in one:
                self.assertEqual(ytd[key], 11 * one[key] + big[key], key)
            self.assertEqual(ytd["gross"], 5_600_000)

        def test_order_does_not_matter(self):
            self.assertEqual(year_to_date([100_000, 900_000, 5000]), year_to_date([5000, 100_000, 900_000]))

        def test_single(self):
            self.assertEqual(year_to_date([123_456]), payslip(123_456))


    if __name__ == "__main__":
        unittest.main()
''')

NORRPAY = Lib(
    name="norrpay", lang="python", title="the Norrland gross-to-net calculator (`norrpay/`)",
    blurb="The Norrland payroll office turns a monthly gross salary into a pay slip and an employer cost with norrpay.",
    files={"norrpay/__init__.py": "", "norrpay/rounding.py": NP_ROUNDING, "norrpay/components.py": NP_COMPONENTS,
           "norrpay/payslip.py": NP_PAYSLIP, "README.md": NP_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": NP_VISIBLE},
    hidden_tests={"tests/test_full.py": NP_HIDDEN},
    mutate=["norrpay/rounding.py", "norrpay/components.py", "norrpay/payslip.py"], difficulty=3,
    tags=["payroll", "tax", "rounding"],
    probes=[
        "div_half_even(5, 2)", "div_half_even(7, 2)", "pension(80_025)", "pension(700_001)", "allowance(1_100_000)",
        "allowance(1_300_000)", "income_tax(600_002)", "income_tax(25)", "social(500_026)", "social(60)",
        "payslip(400_000)", "payslip(1_200_000)['net']", "employer_cost(100_000, 24)", "employer_cost(100_000, 67)",
        "employer_cost(500_000, 20)", "year_to_date([400_000, 400_000])['tax']",
    ],
    probe_import="from norrpay.rounding import *\nfrom norrpay.components import *\nfrom norrpay.payslip import *",
)

register_libs([VELDMARK, NORRPAY], n=10)
