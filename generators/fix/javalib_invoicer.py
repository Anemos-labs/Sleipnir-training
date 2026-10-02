"""Invoice totals with line discounts, tax groups and rounding allocation (java): bugs injected into an invoicing library."""
from fx import Lib, dd
from generators.fix._lang2 import JAVA_CHECK, java_test_main, register_libs

README = dd(r'''
    # invoicer

    The totals engine of a small invoicing service. Plain Java 17, no dependencies; sources in `src/billing/`.
    All money is `int` cents; tax rates are in basis points (`2000` is 20 %).

    ## `Money` (`Money.java`)

    * `roundDiv(n, d)`: `n / d` rounded half up, for `n >= 0` and `d > 0` (`long` arguments, `int` result).
    * `allocate(total, weights)`: splits `total` cents over the weights so that the shares add up to exactly `total`
      (*largest remainder* method). `total` must be `>= 0` and every weight `>= 0`, otherwise `IllegalArgumentException`.
      Each share starts as `floor(total * weight / sum)`; the leftover cents (`total` minus the sum of the shares) go one each to
      the entries with the largest remainders `(total * weight) % sum`, ties to the lower index. If the weights add up to `0`,
      all shares are `0` (but a positive `total` is then an `IllegalArgumentException`).

    ## `LineItem(description, qty, unitCents, rateBp, taxIncluded, discountPct)`

    `qty >= 1`, `unitCents >= 0`, `0 <= rateBp <= 10000`, `0 <= discountPct <= 100`; anything else is an
    `IllegalArgumentException` from the constructor. All fields are public and final.

    ## `Calculator.compute(lines, orderDiscountCents)` returns an `Invoice`

    1. For every line: `gross = qty * unitCents`; `lineDiscount = roundDiv(gross * discountPct, 100)`; `base = gross - lineDiscount`.
    2. The order discount (`>= 0` and at most the sum of the bases, else `IllegalArgumentException`) is spread over the lines with
       `Money.allocate(orderDiscount, bases)`; the line's `orderShare` is its share, and its final `base` is
       `gross - lineDiscount - orderShare`.
    3. Lines are grouped by `(rateBp, taxIncluded)`. For a group with `sumBase` (the sum of its final bases):
       * tax **excluded** from the prices: `net = sumBase`, `tax = roundDiv(sumBase * rateBp, 10000)`;
       * tax **included** in the prices: `net = roundDiv(sumBase * 10000, 10000 + rateBp)`, `tax = sumBase - net`.
    4. `Invoice.net` and `Invoice.tax` are the sums over the groups; `Invoice.total = net + tax`.

    `Invoice` has `lines` (a `List<LineResult>` in input order, each with `description`, `gross`, `lineDiscount`, `orderShare` and
    `base`), `groups` (a `List<TaxGroup>` with `rateBp`, `taxIncluded`, `net`, `tax`, sorted by `rateBp` ascending, tax-excluded
    before tax-included at the same rate), `net`, `tax`, `total`. An empty list of lines gives an all-zero invoice (and
    only a zero order discount is allowed).

    `Calculator.payableCash(total)` rounds an amount to the nearest 5 cents, a remainder of 3 or 4 cents rounding up (so 27976 is
    27975 and 27978 is 27980).
''')

MONEY = dd(r'''
    package billing;

    public final class Money {
        private Money() {}

        /** n / d rounded half up, for n >= 0 and d > 0. */
        public static int roundDiv(long n, long d) {
            return (int) ((2 * n + d) / (2 * d));
        }

        public static int[] allocate(int total, int[] weights) {
            if (total < 0) {
                throw new IllegalArgumentException("total must not be negative");
            }
            long sum = 0;
            for (int w : weights) {
                if (w < 0) {
                    throw new IllegalArgumentException("weights must not be negative");
                }
                sum += w;
            }
            int[] shares = new int[weights.length];
            if (sum == 0) {
                if (total > 0) {
                    throw new IllegalArgumentException("nothing to allocate to");
                }
                return shares;
            }
            long[] remainder = new long[weights.length];
            int given = 0;
            for (int i = 0; i < weights.length; i++) {
                long scaled = (long) total * weights[i];
                shares[i] = (int) (scaled / sum);
                remainder[i] = scaled % sum;
                given += shares[i];
            }
            int left = total - given;
            while (left > 0) {
                int best = -1;
                for (int i = 0; i < weights.length; i++) {
                    if (remainder[i] >= 0 && (best < 0 || remainder[i] > remainder[best])) {
                        best = i;
                    }
                }
                shares[best]++;
                remainder[best] = -1;
                left--;
            }
            return shares;
        }
    }
''')

LINE = dd(r'''
    package billing;

    public final class LineItem {
        public final String description;
        public final int qty;
        public final int unitCents;
        public final int rateBp;
        public final boolean taxIncluded;
        public final int discountPct;

        public LineItem(String description, int qty, int unitCents, int rateBp, boolean taxIncluded, int discountPct) {
            if (qty < 1) {
                throw new IllegalArgumentException("qty must be at least 1");
            }
            if (unitCents < 0) {
                throw new IllegalArgumentException("unit price must not be negative");
            }
            if (rateBp < 0 || rateBp > 10000) {
                throw new IllegalArgumentException("tax rate must be between 0 and 10000 basis points");
            }
            if (discountPct < 0 || discountPct > 100) {
                throw new IllegalArgumentException("discount must be between 0 and 100 percent");
            }
            this.description = description;
            this.qty = qty;
            this.unitCents = unitCents;
            this.rateBp = rateBp;
            this.taxIncluded = taxIncluded;
            this.discountPct = discountPct;
        }
    }
''')

INVOICE = dd(r'''
    package billing;

    import java.util.List;

    public final class Invoice {
        public static final class LineResult {
            public final String description;
            public final int gross;
            public final int lineDiscount;
            public final int orderShare;
            public final int base;

            LineResult(String description, int gross, int lineDiscount, int orderShare, int base) {
                this.description = description;
                this.gross = gross;
                this.lineDiscount = lineDiscount;
                this.orderShare = orderShare;
                this.base = base;
            }
        }

        public static final class TaxGroup {
            public final int rateBp;
            public final boolean taxIncluded;
            public final int net;
            public final int tax;

            TaxGroup(int rateBp, boolean taxIncluded, int net, int tax) {
                this.rateBp = rateBp;
                this.taxIncluded = taxIncluded;
                this.net = net;
                this.tax = tax;
            }
        }

        public final List<LineResult> lines;
        public final List<TaxGroup> groups;
        public final int net;
        public final int tax;
        public final int total;

        Invoice(List<LineResult> lines, List<TaxGroup> groups, int net, int tax) {
            this.lines = lines;
            this.groups = groups;
            this.net = net;
            this.tax = tax;
            this.total = net + tax;
        }
    }
''')

CALC = dd(r'''
    package billing;

    import java.util.ArrayList;
    import java.util.List;
    import java.util.Map;
    import java.util.TreeMap;

    public final class Calculator {
        private Calculator() {}

        public static Invoice compute(List<LineItem> items, int orderDiscountCents) {
            int n = items.size();
            int[] gross = new int[n];
            int[] lineDiscount = new int[n];
            int[] base = new int[n];
            int sumBase = 0;
            for (int i = 0; i < n; i++) {
                LineItem it = items.get(i);
                gross[i] = it.qty * it.unitCents;
                lineDiscount[i] = Money.roundDiv((long) gross[i] * it.discountPct, 100);
                base[i] = gross[i] - lineDiscount[i];
                sumBase += base[i];
            }
            if (orderDiscountCents < 0 || orderDiscountCents > sumBase) {
                throw new IllegalArgumentException("order discount out of range");
            }
            int[] share = Money.allocate(orderDiscountCents, base);

            List<Invoice.LineResult> lines = new ArrayList<>();
            Map<Long, Integer> sums = new TreeMap<>();
            for (int i = 0; i < n; i++) {
                LineItem it = items.get(i);
                int finalBase = base[i] - share[i];
                lines.add(new Invoice.LineResult(it.description, gross[i], lineDiscount[i], share[i], finalBase));
                long key = (long) it.rateBp * 2 + (it.taxIncluded ? 1 : 0);
                sums.merge(key, finalBase, Integer::sum);
            }

            List<Invoice.TaxGroup> groups = new ArrayList<>();
            int net = 0;
            int tax = 0;
            for (Map.Entry<Long, Integer> e : sums.entrySet()) {
                int rate = (int) (e.getKey() / 2);
                boolean included = e.getKey() % 2 == 1;
                int sum = e.getValue();
                int groupNet;
                int groupTax;
                if (included) {
                    groupNet = Money.roundDiv((long) sum * 10000, 10000L + rate);
                    groupTax = sum - groupNet;
                } else {
                    groupNet = sum;
                    groupTax = Money.roundDiv((long) sum * rate, 10000);
                }
                groups.add(new Invoice.TaxGroup(rate, included, groupNet, groupTax));
                net += groupNet;
                tax += groupTax;
            }
            return new Invoice(lines, groups, net, tax);
        }

        public static int payableCash(int total) {
            return Money.roundDiv(total, 5) * 5;
        }
    }
''')

BASIC = dd(r'''
    import billing.Money;

    public class BasicTests {
        public static void run() {
            Check.test("roundDiv", () -> {
                Check.eq(1, Money.roundDiv(1, 2));
                Check.eq(0, Money.roundDiv(1, 3));
            });
            Check.test("allocate", () -> Check.eq(new int[] {3, 3, 4}, Money.allocate(10, new int[] {3, 3, 4})));
        }
    }
''')

FULL = dd(r'''
    import billing.Calculator;
    import billing.Invoice;
    import billing.LineItem;
    import billing.Money;
    import java.util.ArrayList;
    import java.util.List;

    public class FullTests {
        static LineItem line(String d, int qty, int unit, int rate, boolean incl, int disc) {
            return new LineItem(d, qty, unit, rate, incl, disc);
        }

        static List<LineItem> sample() {
            List<LineItem> l = new ArrayList<>();
            l.add(line("Widget", 3, 1999, 2000, false, 10));
            l.add(line("Gadget", 1, 12000, 2000, false, 0));
            l.add(line("Book", 2, 1050, 500, true, 0));
            l.add(line("Service", 1, 5000, 0, false, 0));
            return l;
        }

        static String groups(Invoice inv) {
            StringBuilder sb = new StringBuilder();
            for (Invoice.TaxGroup g : inv.groups) {
                sb.append(g.rateBp).append(g.taxIncluded ? "i" : "x").append(':').append(g.net).append('/').append(g.tax).append(' ');
            }
            return sb.toString().trim();
        }

        public static void run() {
            Check.test("roundDiv rounds half up", () -> {
                Check.eq(0, Money.roundDiv(0, 7));
                Check.eq(0, Money.roundDiv(49, 100));
                Check.eq(1, Money.roundDiv(50, 100));
                Check.eq(1, Money.roundDiv(149, 100));
                Check.eq(2, Money.roundDiv(150, 100));
                Check.eq(3, Money.roundDiv(5, 2));
                Check.eq(4, Money.roundDiv(7, 2));
                Check.eq(2, Money.roundDiv(7, 3));
                Check.eq(3, Money.roundDiv(8, 3));
                Check.eq(1, Money.roundDiv(3, 3));
                Check.eq(2000000, Money.roundDiv(4000000000L, 2000));
            });

            Check.test("allocate: exact and remainder cases", () -> {
                Check.eq(new int[] {34, 33, 33}, Money.allocate(100, new int[] {1, 1, 1}));
                Check.eq(new int[] {3, 3, 4}, Money.allocate(10, new int[] {3, 3, 4}));
                Check.eq(new int[] {0, 0, 5}, Money.allocate(5, new int[] {0, 0, 5}));
                Check.eq(new int[] {2, 2, 2, 1}, Money.allocate(7, new int[] {2, 2, 2, 1}));
                Check.eq(new int[] {220, 490, 86, 204}, Money.allocate(1000, new int[] {5397, 12000, 2100, 5000}));
                Check.eq(new int[] {0, 0}, Money.allocate(0, new int[] {4, 6}));
                Check.eq(new int[] {5}, Money.allocate(5, new int[] {9}));
                Check.eq(new int[] {}, Money.allocate(0, new int[] {}));
            });

            Check.test("allocate: ties go to the lower index, the largest remainder wins", () -> {
                Check.eq(new int[] {1, 1, 0}, Money.allocate(2, new int[] {1, 1, 1}));
                Check.eq(new int[] {1, 0, 0}, Money.allocate(1, new int[] {5, 5, 5}));
                Check.eq(new int[] {0, 1, 0}, Money.allocate(1, new int[] {1, 3, 2}));
                Check.eq(new int[] {1, 2, 2}, Money.allocate(5, new int[] {1, 3, 3}));
                Check.eq(new int[] {2, 1, 1}, Money.allocate(4, new int[] {1, 1, 1}));
                Check.eq(new int[] {0, 1}, Money.allocate(1, new int[] {49, 51}));
                Check.eq(new int[] {1, 0}, Money.allocate(1, new int[] {51, 49}));
            });

            Check.test("allocate always adds up", () -> {
                int[][] ws = {{1, 2, 3}, {7, 7, 7, 7}, {100, 1}, {1, 1, 1, 1, 1, 1, 1}, {13, 0, 29, 5}};
                for (int[] w : ws) {
                    for (int total = 0; total < 60; total++) {
                        int sum = 0;
                        for (int s : Money.allocate(total, w)) {
                            sum += s;
                        }
                        Check.eq(total, sum);
                    }
                }
                int[] big = Money.allocate(2000000000, new int[] {1, 1, 1});
                Check.eq(2000000000, big[0] + big[1] + big[2]);
                Check.eq(666666667, big[0]);
            });

            Check.test("allocate: bad input", () -> {
                Check.raises(IllegalArgumentException.class, () -> Money.allocate(-1, new int[] {1, 2}));
                Check.raises(IllegalArgumentException.class, () -> Money.allocate(5, new int[] {1, -2}));
                Check.raises(IllegalArgumentException.class, () -> Money.allocate(5, new int[] {0, 0}));
                Check.raises(IllegalArgumentException.class, () -> Money.allocate(5, new int[] {}));
                Check.eq(new int[] {0, 0}, Money.allocate(0, new int[] {0, 0}));
            });

            Check.test("line item validation", () -> {
                Check.raises(IllegalArgumentException.class, () -> line("x", 0, 100, 0, false, 0));
                Check.raises(IllegalArgumentException.class, () -> line("x", -1, 100, 0, false, 0));
                Check.raises(IllegalArgumentException.class, () -> line("x", 1, -1, 0, false, 0));
                Check.raises(IllegalArgumentException.class, () -> line("x", 1, 100, -1, false, 0));
                Check.raises(IllegalArgumentException.class, () -> line("x", 1, 100, 10001, false, 0));
                Check.raises(IllegalArgumentException.class, () -> line("x", 1, 100, 0, false, -1));
                Check.raises(IllegalArgumentException.class, () -> line("x", 1, 100, 0, false, 101));
                LineItem edge = line("x", 1, 0, 10000, true, 100);
                Check.eq("x", edge.description);
                Check.eq(10000, edge.rateBp);
                Check.eq(100, edge.discountPct);
                Check.yes(edge.taxIncluded, "included");
            });

            Check.test("a plain invoice", () -> {
                Invoice inv = Calculator.compute(sample(), 0);
                Check.eq(4, inv.lines.size());
                Check.eq(5997, inv.lines.get(0).gross);
                Check.eq(600, inv.lines.get(0).lineDiscount);
                Check.eq(0, inv.lines.get(0).orderShare);
                Check.eq(5397, inv.lines.get(0).base);
                Check.eq("Widget", inv.lines.get(0).description);
                Check.eq(2100, inv.lines.get(2).gross);
                Check.eq("Service", inv.lines.get(3).description);
                Check.eq("0x:5000/0 500i:2000/100 2000x:17397/3479", groups(inv));
                Check.eq(24397, inv.net);
                Check.eq(3579, inv.tax);
                Check.eq(27976, inv.total);
            });

            Check.test("an order discount is spread proportionally", () -> {
                Invoice inv = Calculator.compute(sample(), 1000);
                int[] shares = new int[4];
                int[] bases = new int[4];
                for (int i = 0; i < 4; i++) {
                    shares[i] = inv.lines.get(i).orderShare;
                    bases[i] = inv.lines.get(i).base;
                }
                Check.eq(new int[] {220, 490, 86, 204}, shares);
                Check.eq(new int[] {5177, 11510, 2014, 4796}, bases);
                Check.eq("0x:4796/0 500i:1918/96 2000x:16687/3337", groups(inv));
                Check.eq(23401, inv.net);
                Check.eq(3433, inv.tax);
                Check.eq(26834, inv.total);
            });

            Check.test("order discount limits", () -> {
                Check.raises(IllegalArgumentException.class, () -> Calculator.compute(sample(), -1));
                Check.raises(IllegalArgumentException.class, () -> Calculator.compute(sample(), 24498));
                Invoice all = Calculator.compute(sample(), 24497);
                Check.eq(0, all.total);
                Check.eq(0, all.net);
                for (Invoice.LineResult r : all.lines) {
                    Check.eq(0, r.base);
                }
            });

            Check.test("empty invoice", () -> {
                Invoice inv = Calculator.compute(new ArrayList<>(), 0);
                Check.eq(0, inv.lines.size());
                Check.eq(0, inv.groups.size());
                Check.eq(0, inv.total);
                Check.raises(IllegalArgumentException.class, () -> Calculator.compute(new ArrayList<>(), 1));
            });

            Check.test("tax included in the price", () -> {
                List<LineItem> l = new ArrayList<>();
                l.add(line("x", 1, 1000, 1000, true, 0));
                Invoice inv = Calculator.compute(l, 0);
                Check.eq("1000i:909/91", groups(inv));
                Check.eq(1000, inv.total);
                List<LineItem> m = new ArrayList<>();
                m.add(line("y", 3, 333, 1900, true, 0));
                Invoice inv2 = Calculator.compute(m, 0);
                Check.eq("1900i:839/160", groups(inv2));
                Check.eq(999, inv2.total);
            });

            Check.test("tax excluded from the price rounds half up per group", () -> {
                List<LineItem> l = new ArrayList<>();
                l.add(line("x", 1, 999, 2000, false, 0));
                Check.eq("2000x:999/200", groups(Calculator.compute(l, 0)));
                List<LineItem> m = new ArrayList<>();
                m.add(line("y", 1, 1, 2000, false, 0));
                Check.eq("2000x:1/0", groups(Calculator.compute(m, 0)));
                List<LineItem> three = new ArrayList<>();
                three.add(line("a", 1, 2, 2500, false, 0));
                three.add(line("b", 1, 2, 2500, false, 0));
                Check.eq("2500x:4/1", groups(Calculator.compute(three, 0)));
                List<LineItem> half = new ArrayList<>();
                half.add(line("c", 1, 10, 500, false, 0));
                Check.eq("500x:10/1", groups(Calculator.compute(half, 0)));
                List<LineItem> below = new ArrayList<>();
                below.add(line("c", 1, 9, 500, false, 0));
                Check.eq("500x:9/0", groups(Calculator.compute(below, 0)));
            });

            Check.test("groups are separate for each rate and each included flag, sorted", () -> {
                List<LineItem> l = new ArrayList<>();
                l.add(line("a", 1, 1000, 2000, true, 0));
                l.add(line("b", 1, 1000, 2000, false, 0));
                l.add(line("c", 1, 1000, 500, false, 0));
                l.add(line("d", 1, 1000, 500, true, 0));
                l.add(line("e", 1, 1000, 2000, false, 0));
                Invoice inv = Calculator.compute(l, 0);
                Check.eq("500x:1000/50 500i:952/48 2000x:2000/400 2000i:833/167", groups(inv));
                Check.eq(4785, inv.net);
                Check.eq(665, inv.tax);
                Check.eq(5450, inv.total);
            });

            Check.test("line discounts round half up", () -> {
                List<LineItem> l = new ArrayList<>();
                l.add(line("a", 1, 1005, 0, false, 10));
                l.add(line("b", 1, 1004, 0, false, 10));
                l.add(line("c", 1, 1, 0, false, 50));
                l.add(line("d", 1, 1, 0, false, 49));
                l.add(line("e", 2, 500, 0, false, 100));
                Invoice inv = Calculator.compute(l, 0);
                Check.eq(101, inv.lines.get(0).lineDiscount);
                Check.eq(100, inv.lines.get(1).lineDiscount);
                Check.eq(1, inv.lines.get(2).lineDiscount);
                Check.eq(0, inv.lines.get(3).lineDiscount);
                Check.eq(1000, inv.lines.get(4).lineDiscount);
                Check.eq(0, inv.lines.get(4).base);
                Check.eq(1809, inv.total);
            });

            Check.test("a zero rate and a free line", () -> {
                List<LineItem> l = new ArrayList<>();
                l.add(line("gift", 5, 0, 2000, false, 0));
                Invoice inv = Calculator.compute(l, 0);
                Check.eq("2000x:0/0", groups(inv));
                Check.eq(0, inv.total);
                List<LineItem> full = new ArrayList<>();
                full.add(line("t", 1, 500, 10000, false, 0));
                Check.eq("10000x:500/500", groups(Calculator.compute(full, 0)));
                List<LineItem> inc = new ArrayList<>();
                inc.add(line("t", 1, 500, 10000, true, 0));
                Check.eq("10000i:250/250", groups(Calculator.compute(inc, 0)));
            });

            Check.test("big amounts do not overflow", () -> {
                List<LineItem> l = new ArrayList<>();
                l.add(line("x", 1, 200000000, 2000, false, 50));
                Invoice inv = Calculator.compute(l, 0);
                Check.eq(100000000, inv.lines.get(0).lineDiscount);
                Check.eq("2000x:100000000/20000000", groups(inv));
                Check.eq(120000000, inv.total);
            });

            Check.test("payableCash", () -> {
                Check.eq(0, Calculator.payableCash(0));
                Check.eq(0, Calculator.payableCash(1));
                Check.eq(0, Calculator.payableCash(2));
                Check.eq(5, Calculator.payableCash(3));
                Check.eq(5, Calculator.payableCash(4));
                Check.eq(5, Calculator.payableCash(5));
                Check.eq(27975, Calculator.payableCash(27976));
                Check.eq(27975, Calculator.payableCash(27977));
                Check.eq(27980, Calculator.payableCash(27978));
                Check.eq(27980, Calculator.payableCash(27979));
                Check.eq(27980, Calculator.payableCash(27980));
                Check.eq(2000000000, Calculator.payableCash(2000000000));
            });
        }
    }
''')

LIB = Lib(
    name="invoicer", lang="java", title="the invoicer library",
    blurb="The invoicing service of a small shop computes line discounts, tax groups and totals with invoicer.",
    files={"src/billing/Money.java": MONEY, "src/billing/LineItem.java": LINE, "src/billing/Invoice.java": INVOICE,
           "src/billing/Calculator.java": CALC, "README.md": README, ".gitignore": "build/\n"},
    visible_tests={"test/Check.java": JAVA_CHECK, "test/BasicTests.java": BASIC, "test/TestMain.java": java_test_main("BasicTests")},
    hidden_tests={"test/FullTests.java": FULL, "test/TestMain.java": java_test_main("BasicTests", "FullTests")},
    mutate=["src/billing/Calculator.java", "src/billing/Money.java", "src/billing/LineItem.java"], difficulty=3, tags=["invoicing", "tax", "rounding"],
    probe_import="import java.util.*;\nimport billing.*;",
    probes=[
        "Money.roundDiv(5, 2)", "Money.roundDiv(7, 3)", "Money.allocate(100, new int[] {1, 1, 1})", "Money.allocate(1, new int[] {1, 3, 2})", "Money.allocate(5, new int[] {1, 3, 3})",
        "Money.allocate(1000, new int[] {5397, 12000, 2100, 5000})", "Money.allocate(5, new int[] {0, 0})", "Money.allocate(-1, new int[] {1, 2})",
        "Calculator.payableCash(27976)", "Calculator.payableCash(27978)", "Calculator.payableCash(3)",
        "Calculator.compute(List.of(new LineItem(\"x\", 1, 1000, 1000, true, 0)), 0).tax",
        "Calculator.compute(List.of(new LineItem(\"y\", 3, 333, 1900, true, 0)), 0).net",
        "Calculator.compute(List.of(new LineItem(\"a\", 1, 2, 2500, false, 0), new LineItem(\"b\", 1, 2, 2500, false, 0)), 0).tax",
        "Calculator.compute(List.of(new LineItem(\"a\", 1, 1005, 0, false, 10)), 0).total",
        "Calculator.compute(List.of(new LineItem(\"a\", 1, 1000, 2000, true, 0), new LineItem(\"b\", 1, 1000, 2000, false, 0), new LineItem(\"c\", 1, 1000, 500, false, 0)), 0).total",
        "Calculator.compute(List.of(new LineItem(\"a\", 1, 3000, 0, false, 0), new LineItem(\"b\", 1, 1000, 0, false, 0)), 1).total",
        "Calculator.compute(List.of(new LineItem(\"a\", 1, 100, 0, false, 0)), 101)",
        "new LineItem(\"x\", 0, 100, 0, false, 0)",
    ],
)

register_libs([LIB], n=8)
