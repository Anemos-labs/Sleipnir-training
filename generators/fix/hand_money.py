"""Money handling: rounding, order of operations, parsing and splitting. Ferry fares (python) and locker fees (java)."""
from fractions import Fraction

from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from


def pct(cents: int, bp: int) -> int:
    """Oracle: cents * bp / 10000 rounded half away from zero."""
    r = int(Fraction(abs(cents) * bp, 10000) + Fraction(1, 2))
    return -r if cents < 0 else r


def split(total: int, n: int) -> list[int]:
    base, rem = divmod(abs(total), n)
    sign = -1 if total < 0 else 1
    return [sign * (base + (1 if i < rem else 0)) for i in range(n)]


# ------------------------------------------------------------------------------------------------------------------
# Base A (python): farepack, ferry ticket pricing.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # farepack

    Pricing of ferry tickets. Money is always an `int` number of cents.

    ## `farepack.money`
    * `to_cents(text)`: exact parse of a price such as `12`, `12.5` or `12.50` (one or two decimals; `12.5` is
      twelve fifty). Anything else is a `ValueError`.
    * `fmt(cents)`: `"12.50"`, negative amounts as `"-0.05"`.
    * `pct_of(cents, bp)`: `cents * bp / 10000` (basis points) rounded **half away from zero**, integers only.
    * `split_even(total, n)`: `n` amounts that add up to `total`; the extra cents go one each to the first
      amounts; a negative total is split by magnitude and negated; `n < 1` is a `ValueError`.

    ## `farepack.tariff.Tariff`
    `Tariff.parse(text)` reads lines `<kind> <price>` (blank lines and `#` comments allowed). `price(kind)` is in
    cents; an unknown kind is a `KeyError`.

    ## `farepack.invoice.price_order(tariff, items, discount_bp=0, tax_bp=0)`
    `items` is a list of `(kind, qty)` (a negative `qty` is a refund). For **each line**:
    `gross = price * qty`; `discount = pct_of(gross, discount_bp)`; `taxable = gross - discount`;
    `tax = pct_of(taxable, tax_bp)`; `total = taxable + tax`. The order's `gross`, `discount`, `tax` and `total` are
    the sums of the lines' values (so the order total is always the sum of the line totals).
    The result is `{"lines": [{kind, qty, gross, discount, tax, total}, ...], "gross", "discount", "tax", "total"}`.
''')

A_MONEY = dd('''
    import re

    _PRICE = re.compile(r"^(\\d+)(?:\\.(\\d{1,2}))?$")


    def to_cents(text):
        m = _PRICE.match(text.strip())
        if not m:
            raise ValueError(f"bad price: {text!r}")
        whole, frac = m.group(1), (m.group(2) or "").ljust(2, "0")
        return int(whole) * 100 + int(frac)


    def fmt(cents):
        sign = "-" if cents < 0 else ""
        c = abs(cents)
        return f"{sign}{c // 100}.{c % 100:02d}"


    def pct_of(cents, bp):
        n = abs(cents) * bp
        r = (n + 5000) // 10000
        return -r if cents < 0 else r


    def split_even(total, n):
        if n < 1:
            raise ValueError("n must be at least 1")
        sign = -1 if total < 0 else 1
        base, rem = divmod(abs(total), n)
        return [sign * (base + (1 if i < rem else 0)) for i in range(n)]
''')

A_TARIFF = dd('''
    from .money import to_cents


    class Tariff:
        def __init__(self, prices):
            self.prices = dict(prices)

        @classmethod
        def parse(cls, text):
            prices = {}
            for raw in text.splitlines():
                line = raw.split("#", 1)[0].strip()
                if not line:
                    continue
                kind, price = line.split()
                prices[kind] = to_cents(price)
            return cls(prices)

        def price(self, kind):
            try:
                return self.prices[kind]
            except KeyError:
                raise KeyError(f"no fare for {kind!r}") from None
''')

A_INVOICE = dd('''
    from .money import pct_of


    def price_order(tariff, items, discount_bp=0, tax_bp=0):
        lines = []
        for kind, qty in items:
            gross = tariff.price(kind) * qty
            discount = pct_of(gross, discount_bp)
            taxable = gross - discount
            tax = pct_of(taxable, tax_bp)
            lines.append({"kind": kind, "qty": qty, "gross": gross, "discount": discount, "tax": tax, "total": taxable + tax})
        return {
            "lines": lines,
            "gross": sum(l["gross"] for l in lines),
            "discount": sum(l["discount"] for l in lines),
            "tax": sum(l["tax"] for l in lines),
            "total": sum(l["total"] for l in lines),
        }
''')

A_INVOICE_TAX_ON_TOTAL = dd('''
    from .money import pct_of


    def price_order(tariff, items, discount_bp=0, tax_bp=0):
        lines = []
        for kind, qty in items:
            gross = tariff.price(kind) * qty
            discount = pct_of(gross, discount_bp)
            taxable = gross - discount
            tax = pct_of(taxable, tax_bp)
            lines.append({"kind": kind, "qty": qty, "gross": gross, "discount": discount, "tax": tax, "total": taxable + tax})
        gross = sum(l["gross"] for l in lines)
        discount = sum(l["discount"] for l in lines)
        tax = pct_of(gross - discount, tax_bp)
        return {"lines": lines, "gross": gross, "discount": discount, "tax": tax, "total": gross - discount + tax}
''')

A_INVOICE_DISCOUNT_AFTER_TAX = dd('''
    from .money import pct_of


    def price_order(tariff, items, discount_bp=0, tax_bp=0):
        lines = []
        for kind, qty in items:
            gross = tariff.price(kind) * qty
            tax = pct_of(gross, tax_bp)
            discount = pct_of(gross + tax, discount_bp)
            lines.append({"kind": kind, "qty": qty, "gross": gross, "discount": discount, "tax": tax, "total": gross + tax - discount})
        return {
            "lines": lines,
            "gross": sum(l["gross"] for l in lines),
            "discount": sum(l["discount"] for l in lines),
            "tax": sum(l["tax"] for l in lines),
            "total": sum(l["total"] for l in lines),
        }
''')

A_VISIBLE = {
    "tests/test_farepack.py": dd('''
        import unittest

        from farepack.invoice import price_order
        from farepack.money import fmt, pct_of, split_even, to_cents
        from farepack.tariff import Tariff

        TARIFF = Tariff.parse("adult 12.50\\nchild 6.25\\n")


        class Basics(unittest.TestCase):
            def test_parse_and_format(self):
                self.assertEqual(to_cents("12.50"), 1250)
                self.assertEqual(fmt(1250), "12.50")

            def test_pct(self):
                self.assertEqual(pct_of(1000, 1000), 100)

            def test_plain_order(self):
                r = price_order(TARIFF, [("adult", 2), ("child", 1)])
                self.assertEqual(r["total"], 3125)

            def test_split(self):
                self.assertEqual(split_even(9, 3), [3, 3, 3])


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _render_a_hidden() -> dict:
    """The hidden test text is assembled from oracle values; plain str.replace keeps the braces of the python code intact."""
    tariff = "adult 12.50\nchild 6.25\nsenior 9.9   # trimmed fare\nbike 4.35\nebike 8.20\ncart 19.99\nsticker 1.05\n"
    prices = {"adult": 1250, "child": 625, "senior": 990, "bike": 435, "ebike": 820, "cart": 1999, "sticker": 105}

    def line(kind, qty, d, t):
        gross = prices[kind] * qty
        disc = pct(gross, d)
        taxable = gross - disc
        tax = pct(taxable, t)
        return dict(kind=kind, qty=qty, gross=gross, discount=disc, tax=tax, total=taxable + tax)

    def order(items, d, t):
        ls = [line(k, q, d, t) for k, q in items]
        return {"lines": ls, "gross": sum(x["gross"] for x in ls), "discount": sum(x["discount"] for x in ls),
                "tax": sum(x["tax"] for x in ls), "total": sum(x["total"] for x in ls)}

    cases = [
        ([("adult", 2), ("child", 1)], 1000, 800),
        ([("sticker", 1), ("sticker", 1), ("sticker", 1)], 0, 1000),
        ([("senior", 3), ("bike", 2), ("ebike", 1)], 1500, 650),
        ([("cart", 1), ("cart", 3)], 250, 1900),
        ([("child", -1), ("adult", 1)], 1000, 800),
        ([("child", -3)], 1250, 800),
        ([("bike", 7), ("sticker", 5), ("ebike", 2)], 0, 0),
        ([("adult", 1)], 10000, 800),
    ]
    methods = []
    for i, (items, d, t) in enumerate(cases):
        exp = order(items, d, t)
        methods.append(
            f"    def test_order_{i + 1}(self):\n"
            f"        r = price_order(TARIFF, {items!r}, discount_bp={d}, tax_bp={t})\n"
            f"        self.assertEqual(r, {exp!r})\n")
    pct_cases = [(625, 1000), (-625, 1000), (1, 5000), (-1, 5000), (105, 1000), (-105, 1000), (0, 1234), (999, 1), (1999, 1900),
                 (-1999, 1900), (333, 3333), (10 ** 12 + 7, 8000)]
    pct_lines = "".join(f"        self.assertEqual(pct_of({c}, {b}), {pct(c, b)})\n" for c, b in pct_cases)
    split_cases = [(100, 3), (101, 3), (1, 4), (0, 3), (-10, 3), (-1, 2), (7, 1), (1000, 7)]
    split_lines = "".join(f"        self.assertEqual(split_even({t}, {n}), {split(t, n)})\n" for t, n in split_cases)
    parse_ok = [("12", 1200), ("12.5", 1250), ("12.50", 1250), ("0.05", 5), ("0.5", 50), ("4.35", 435), ("8.20", 820), ("19.99", 1999),
                ("0.57", 57), ("1.15", 115), ("2.30", 230), (" 3.10 ", 310), ("0", 0), ("0.0", 0)]
    parse_lines = "".join(f"        self.assertEqual(to_cents({t!r}), {c})\n" for t, c in parse_ok)
    head = (
        "import unittest\n\nfrom farepack.invoice import price_order\nfrom farepack.money import fmt, pct_of, split_even, to_cents\n"
        "from farepack.tariff import Tariff\n\n"
        f"TARIFF = Tariff.parse({tariff!r})\n\n\n")
    body = (
        "class Money(unittest.TestCase):\n    def test_to_cents(self):\n" + parse_lines + "\n"
        "    def test_to_cents_rejects_junk(self):\n"
        "        for bad in (\"\", \"abc\", \"1.234\", \"-1.00\", \"1,50\", \"1.\", \".5\", \"1e2\"):\n"
        "            with self.assertRaises(ValueError, msg=bad):\n                to_cents(bad)\n\n"
        "    def test_fmt(self):\n"
        "        self.assertEqual(fmt(1250), \"12.50\")\n        self.assertEqual(fmt(5), \"0.05\")\n        self.assertEqual(fmt(0), \"0.00\")\n"
        "        self.assertEqual(fmt(-5), \"-0.05\")\n        self.assertEqual(fmt(-1999), \"-19.99\")\n\n"
        "    def test_pct_rounds_half_away_from_zero(self):\n" + pct_lines + "\n"
        "    def test_split_even(self):\n" + split_lines +
        "        for t, n in ((100, 3), (101, 3), (-10, 3), (1000, 7)):\n            self.assertEqual(sum(split_even(t, n)), t)\n"
        "        with self.assertRaises(ValueError):\n            split_even(10, 0)\n\n\n"
        "class Tariffs(unittest.TestCase):\n"
        "    def test_parse(self):\n        self.assertEqual(TARIFF.price(\"senior\"), 990)\n        self.assertEqual(TARIFF.price(\"bike\"), 435)\n"
        "        self.assertEqual(TARIFF.price(\"sticker\"), 105)\n\n"
        "    def test_unknown_kind(self):\n        with self.assertRaises(KeyError):\n            TARIFF.price(\"dog\")\n\n\n"
        "class Orders(unittest.TestCase):\n" + "\n".join(methods) + "\n"
        "    def test_total_is_the_sum_of_the_lines(self):\n"
        "        r = price_order(TARIFF, [(\"sticker\", 1)] * 7, tax_bp=1000)\n"
        "        self.assertEqual(r[\"total\"], sum(l[\"total\"] for l in r[\"lines\"]))\n"
        "        self.assertEqual(r[\"tax\"], sum(l[\"tax\"] for l in r[\"lines\"]))\n\n\n"
        "if __name__ == \"__main__\":\n    unittest.main()\n")
    return {"tests/test_hidden_farepack.py": head + body}


def _a_prompts():
    p = {}
    p["half-even"] = lambda c: (
        "Finance noticed that the 10% staff discount on a child ticket (fare 6.25) leaves a price of "
        + c.probe("from farepack.money import fmt, pct_of\nprint(fmt(625 - pct_of(625, 1000)))\n")[1]
        + " in the app, while the fare card says "
        + c.probe("from farepack.money import fmt, pct_of\nprint(fmt(625 - pct_of(625, 1000)))\n")[0]
        + ". The rule is that halves round away from zero, so the discount is 0.63. Our totals are a cent off on exactly "
        "these half-cent cases. Please fix the rounding."
    )
    p["short-fraction"] = lambda c: (
        "The tariff file has `senior 9.9 # trimmed fare` (the typist left off the last zero). The invoice prints the senior "
        "fare as "
        + c.probe("from farepack.tariff import Tariff\nfrom farepack.money import fmt\nprint(fmt(Tariff.parse('senior 9.9').price('senior')))\n")[1]
        + " instead of 9.90. The README says one decimal is allowed."
    )
    p["tax-on-total"] = (
        "Customer service sent us an invoice where the order tax is a cent lower than the sum of the taxes printed on the "
        "lines, and the total is not the sum of the line totals either (3 stickers at 1.05 each with 10% tax). The README is "
        "explicit that order values are the sums of the line values. Please repair `price_order`."
    )
    p["discount-after-tax"] = (
        "The 15% group discount is applied on top of the taxed price, so it also discounts the tax. By the pricing rules the "
        "discount comes off the fare first and tax is charged on what is left. Check an order of 3 senior tickets, 2 bikes "
        "and an e-bike with 15% discount and 6.5% tax and you will see the difference."
    )
    p["float-parse"] = lambda c: (
        "Some line totals are one cent short compared with the printed fare card, but only for some fares: bike (4.35), e-bike "
        "(8.20) and the cart (19.99) are affected, adult and child are fine. For example the tariff line `bike 4.35` is "
        + c.probe("from farepack.money import to_cents\nprint(to_cents('4.35'))\n")[1]
        + " cents in the system. We are sure the fare file is right."
    )
    p["two-causes"] = (
        "The month-end reconciliation is out by a few cents on several invoices and nobody agrees on why. Two things I noticed: "
        "the e-bike fare (8.20 in the tariff file) is charged as 8.19, and on multi-line orders the tax at the bottom "
        "does not equal the sum of the line taxes. Both are probably real bugs; please check everything that touches the "
        "numbers."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "farepack/__init__.py": '"""Ferry ticket pricing."""\n', "farepack/money.py": A_MONEY,
            "farepack/tariff.py": A_TARIFF, "farepack/invoice.py": A_INVOICE}
    m, i = "farepack/money.py", "farepack/invoice.py"
    floatp = ("    whole, frac = m.group(1), (m.group(2) or \"\").ljust(2, \"0\")\n    return int(whole) * 100 + int(frac)\n",
              "    return int(float(text.strip()) * 100)\n")
    bugs = [
        Bug("half-even-discounts", 2, {m: [("    n = abs(cents) * bp\n    r = (n + 5000) // 10000\n", "    r = round(abs(cents) * bp / 10000)\n")]}, P["half-even"]),
        Bug("one-decimal-misparsed", 2, {m: [('(m.group(2) or "").ljust(2, "0")', '(m.group(2) or "").rjust(2, "0")')]}, P["short-fraction"]),
        Bug("tax-on-order-total", 3, {i: A_INVOICE_TAX_ON_TOTAL}, P["tax-on-total"]),
        Bug("discount-after-tax", 3, {i: A_INVOICE_DISCOUNT_AFTER_TAX}, P["discount-after-tax"]),
        Bug("price-via-float", 3, {m: [floatp]}, P["float-parse"]),
        Bug("float-price-and-order-tax", 5, {m: [floatp], i: A_INVOICE_TAX_ON_TOTAL}, P["two-causes"]),
    ]
    return Base("farepack", "python", good, A_VISIBLE, _render_a_hidden(), bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (java): lockerfee, storage fees of a parcel locker network.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # lockerfee

    Fee arithmetic of a parcel locker network. Money is a `long` number of cents. Plain Java, no dependencies:
    `rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java') && java -cp build TestMain`.

    ## `lockerfee.Fees`
    * `storageFee(minutes, rateCents, capCents)`: the first 1440 minutes are free; after that every **started** block
      of 720 minutes costs `rateCents`; the fee never exceeds `capCents`. Negative minutes are an
      `IllegalArgumentException`.
    * `percentOf(cents, basisPoints)`: `cents * basisPoints / 10000`, rounded **half away from zero**, exact in integer
      arithmetic (amounts up to 10^12 cents must work, negative amounts are refunds).
    * `invoiceTotal(storage, surchargeBp, vatBp, weekend)`: the weekend surcharge (on `storage`, only when `weekend`)
      is added first, then VAT is charged on that sum: `base + percentOf(base, vatBp)`.
    * `split(total, parts)`: `parts` amounts that add up to `total`, extra cents going one each to the first parts;
      a negative total is split by magnitude and negated (`split(-10, 3)` is `{-4, -3, -3}`); `parts < 1` is an
      `IllegalArgumentException`.
    * `sum(amounts)`: the exact sum of the amounts.

    ## `lockerfee.Statement`
    `shares(lineAmounts, vatBp, owners)`: every line gets its own VAT (`line + percentOf(line, vatBp)`), the lines are
    added up, and the total is `Fees.split` between the `owners`.
''')

B_FEES = dd('''
    package lockerfee;

    public final class Fees {
        private Fees() {}

        public static long storageFee(int minutes, long rateCents, long capCents) {
            if (minutes < 0) {
                throw new IllegalArgumentException("minutes must not be negative");
            }
            int billable = minutes - 1440;
            if (billable <= 0) {
                return 0;
            }
            long blocks = (billable + 719) / 720;
            return Math.min(blocks * rateCents, capCents);
        }

        public static long percentOf(long cents, int basisPoints) {
            long n = Math.abs(cents) * basisPoints;
            long r = (n + 5000) / 10000;
            return cents < 0 ? -r : r;
        }

        public static long invoiceTotal(long storage, int surchargeBp, int vatBp, boolean weekend) {
            long base = storage + (weekend ? percentOf(storage, surchargeBp) : 0);
            return base + percentOf(base, vatBp);
        }

        public static long[] split(long total, int parts) {
            if (parts < 1) {
                throw new IllegalArgumentException("parts must be at least 1");
            }
            long mag = Math.abs(total);
            long base = mag / parts;
            long rem = mag % parts;
            long sign = total < 0 ? -1 : 1;
            long[] out = new long[parts];
            for (int i = 0; i < parts; i++) {
                out[i] = sign * (base + (i < rem ? 1 : 0));
            }
            return out;
        }

        public static long sum(long[] amounts) {
            long total = 0;
            for (long a : amounts) {
                total += a;
            }
            return total;
        }
    }
''')

B_STATEMENT = dd('''
    package lockerfee;

    public final class Statement {
        private Statement() {}

        public static long[] shares(long[] lineAmounts, int vatBp, int owners) {
            long total = 0;
            for (long line : lineAmounts) {
                total += line + Fees.percentOf(line, vatBp);
            }
            return Fees.split(total, owners);
        }
    }
''')

B_VISIBLE = {
    "tests/TestMain.java": dd('''
        import lockerfee.Fees;
        import lockerfee.Statement;

        public class TestMain {
            static int failures = 0;

            static void check(String what, long got, long want) {
                if (got != want) {
                    failures++;
                    System.out.println("FAIL " + what + ": got " + got + ", want " + want);
                }
            }

            public static void main(String[] args) {
                check("free day", Fees.storageFee(1440, 150, 900), 0);
                check("two blocks", Fees.storageFee(1440 + 1440, 150, 900), 300);
                check("percentOf", Fees.percentOf(1000, 1000), 100);
                check("sum", Fees.sum(new long[] {1, 2, 3}), 6);
                if (failures > 0) {
                    System.exit(1);
                }
                System.out.println("all checks passed");
            }
        }
    '''),
}


def _b_hidden() -> dict:
    lines = []

    def chk(expr, want):
        lines.append(f'        check("{expr}", {expr}, {want}L);')

    for minutes, rate, cap in [(0, 150, 900), (1440, 150, 900), (1441, 150, 900), (1440 + 720, 150, 900), (1440 + 721, 150, 900), (1440 + 1, 275, 100000),
                               (5000, 150, 900), (100000, 150, 900), (2160, 99, 10 ** 9)]:
        blocks = 0 if minutes <= 1440 else -(-(minutes - 1440) // 720)
        chk(f"Fees.storageFee({minutes}, {rate}L, {cap}L)", min(blocks * rate, cap))
    for c, b in [(625, 1000), (-625, 1000), (1, 5000), (-1, 5000), (105, 1000), (-105, 1000), (0, 1234), (1999, 1900), (-1999, 1900),
                 (333, 3333), (10 ** 12, 9999), (-(10 ** 12) - 7, 8000), (7, 0)]:
        chk(f"Fees.percentOf({c}L, {b})", pct(c, b))
    for s, sur, vat, we in [(300, 2000, 800, True), (300, 2000, 800, False), (105, 1000, 1000, True), (1, 5000, 5000, True), (-300, 2000, 800, True), (0, 2000, 800, True)]:
        base = s + (pct(s, sur) if we else 0)
        chk(f"Fees.invoiceTotal({s}L, {sur}, {vat}, {'true' if we else 'false'})", base + pct(base, vat))
    arrs = []
    for t, n in [(100, 3), (101, 3), (1, 4), (0, 3), (-10, 3), (-1, 2), (7, 1), (1000, 7), (-1000, 7)]:
        arrs.append(f'        checkArr("split({t}, {n})", Fees.split({t}L, {n}), new long[] {{{", ".join(str(x) + "L" for x in split(t, n))}}});')
    big = [2_000_000_000, 2_000_000_000, 2_000_000_000]
    chk("Fees.sum(new long[] {2000000000L, 2000000000L, 2000000000L})", sum(big))
    chk("Fees.sum(new long[] {2000000000L, 2000000000L})", 4_000_000_000)
    chk("Fees.sum(new long[] {5L, -3L, 10L})", 12)
    chk("Fees.sum(new long[] {})", 0)
    stm = []
    for lines_, vat, owners in [([105, 105, 105], 1000, 1), ([105, 105, 105], 1000, 2), ([1050, 1050, 1050], 1000, 1), ([1050, 1050, 1050], 1000, 2), ([300, 705, 99], 800, 3), ([-1050, -1050, 500], 1000, 2),
                                ([-625, -625], 1000, 3), ([5_000_000_000, 7], 2500, 4)]:
        total = sum(x + pct(x, vat) for x in lines_)
        arr = ", ".join(f"{x}L" for x in lines_)
        stm.append(f'        checkArr("shares({lines_}, {vat}, {owners})", Statement.shares(new long[] {{{arr}}}, {vat}, {owners}), '
                   f'new long[] {{{", ".join(str(x) + "L" for x in split(total, owners))}}});')
    java = dd('''
        import java.util.Arrays;
        import lockerfee.Fees;
        import lockerfee.Statement;

        public class TestMain {
            static int failures = 0;

            static void check(String what, long got, long want) {
                if (got != want) {
                    failures++;
                    System.out.println("FAIL " + what + ": got " + got + ", want " + want);
                }
            }

            static void checkArr(String what, long[] got, long[] want) {
                if (!Arrays.equals(got, want)) {
                    failures++;
                    System.out.println("FAIL " + what + ": got " + Arrays.toString(got) + ", want " + Arrays.toString(want));
                }
            }

            static void mustThrow(String what, Runnable r) {
                try {
                    r.run();
                } catch (IllegalArgumentException e) {
                    return;
                }
                failures++;
                System.out.println("FAIL " + what + ": expected IllegalArgumentException");
            }

            public static void main(String[] args) {
        @@LINES@@
        @@ARRS@@
        @@STM@@
                mustThrow("negative minutes", () -> Fees.storageFee(-1, 100, 100));
                mustThrow("zero parts", () -> Fees.split(10, 0));
                if (failures > 0) {
                    System.out.println(failures + " check(s) failed");
                    System.exit(1);
                }
                System.out.println("all checks passed");
            }
        }
    ''')
    java = java.replace("@@LINES@@", "\n".join(lines)).replace("@@ARRS@@", "\n".join(arrs)).replace("@@STM@@", "\n".join(stm))
    return {"tests/TestMain.java": java}


def _b_prompts():
    p = {}
    p["blocks-floor"] = (
        "A customer left a parcel for 25 hours (1500 minutes) and was charged nothing; the network rules say that every "
        "*started* 12 hour block after the free first day is billed. Ops saw the same for 37 hours. Please fix `storageFee` "
        "in `Fees.java`."
    )
    p["percent-double"] = (
        "Refunds are one cent too small in magnitude for half-cent cases: refunding 10% of 6.25 gives -0.62 where we owe "
        "-0.63, while the charge side gives 0.63. The rule is half away from zero in both directions. Look at `percentOf`."
    )
    p["sum-int"] = (
        "The monthly roll-up for the biggest operator shows a negative total (-294967296 cents) for a month with two "
        "shipments of 20 million euros each (two is enough). Single amounts are fine. Please find where the total goes wrong."
    )
    p["split-negative"] = (
        "Splitting a refund among co-owners loses money: `Fees.split(-10, 3)` gives {-3, -3, -3}, nine cents of ten. The "
        "documented result is {-4, -3, -3}, summing to the total. Positive totals are fine."
    )
    p["vat-on-storage"] = (
        "Weekend invoices have the wrong VAT: it seems to be computed on the storage fee instead of on the fee with the "
        "weekend surcharge added. Check `invoiceTotal` against the README: surcharge first, then VAT on the sum."
    )
    p["vat-on-sum"] = (
        "Statement shares do not match what the lines add up to when each line has its own rounded VAT. With three lines of "
        "1.05 and 10% VAT a single owner is billed 3.47, while the lines say 3 x 1.16 = 3.48 (each line's VAT of 0.105 rounds up). The README says "
        "VAT is per line. Please fix `Statement.shares`."
    )
    p["refund-two"] = (
        "Refund statements are wrong in two ways that I could not separate: shares of a refund do not add up to the refund total, "
        "and the half-cent VAT on refund lines is rounded the wrong way. The tests we have only cover positive amounts. "
        "Please make refunds behave as documented."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "src/lockerfee/Fees.java": B_FEES, "src/lockerfee/Statement.java": B_STATEMENT}
    f, st = "src/lockerfee/Fees.java", "src/lockerfee/Statement.java"
    pdouble = ("        long n = Math.abs(cents) * basisPoints;\n        long r = (n + 5000) / 10000;\n        return cents < 0 ? -r : r;\n",
               "        return Math.round(cents * (basisPoints / 10000.0));\n")
    splitneg = ("        long mag = Math.abs(total);\n        long base = mag / parts;\n        long rem = mag % parts;\n        long sign = total < 0 ? -1 : 1;\n",
                "        long base = total / parts;\n        long rem = total % parts;\n        long sign = 1;\n")
    bugs = [
        Bug("started-blocks-floored", 2, {f: [("        long blocks = (billable + 719) / 720;", "        long blocks = billable / 720;")]}, P["blocks-floor"]),
        Bug("sum-in-int", 2, {f: [("        long total = 0;\n        for (long a : amounts) {", "        int total = 0;\n        for (long a : amounts) {")]}, P["sum-int"]),
        Bug("percent-via-double", 3, {f: [pdouble]}, P["percent-double"]),
        Bug("split-negative-total", 3, {f: [splitneg]}, P["split-negative"]),
        Bug("vat-on-storage-only", 3, {f: [("        return base + percentOf(base, vatBp);", "        return base + percentOf(storage, vatBp);")]}, P["vat-on-storage"]),
        Bug("statement-vat-on-sum", 4, {st: [("        long total = 0;\n        for (long line : lineAmounts) {\n            total += line + Fees.percentOf(line, vatBp);\n        }\n",
                                              "        long total = Fees.sum(lineAmounts);\n        total += Fees.percentOf(total, vatBp);\n")]}, P["vat-on-sum"]),
        Bug("refund-split-and-percent", 5, {f: [pdouble, splitneg]}, P["refund-two"]),
    ]
    return Base("lockerfee", "java", good, B_VISIBLE, _b_hidden(), bugs)


@family("fix-hand-money-rounding", category="fix", lang="python", kind="fix", n=13,
        summary="cents arithmetic: rounding direction, order of operations, parsing and splitting (ferry fares in python, locker fees in java)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
