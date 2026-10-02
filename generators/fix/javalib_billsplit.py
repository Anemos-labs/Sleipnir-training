"""Splitting a restaurant bill with shared dishes, coupon, tax and tip (java): bugs injected into a bill-splitting library."""
from fx import Lib, dd
from generators.fix._lang2 import JAVA_CHECK, java_test_main, register_libs

README = dd(r'''
    # billsplit

    Works out who owes what on a shared restaurant bill. Plain Java 17, no dependencies; sources in `src/tab/`.
    Money is `int` cents; tax and tip rates are in basis points (`800` is 8 %).

    ## `Split` (`Split.java`)

    * `splitItem(price, k)`: the price of one dish divided among `k` people as an `int[k]`: everybody gets `price / k` (integer
      division) and the `price % k` leftover cents go, one each, to the *first* entries. `price >= 0` and `k >= 1`, else
      `IllegalArgumentException`.
    * `allocate(total, weights)`: spreads `total` over the weights in proportion. Each share starts as `floor(total * weight / sum)`;
      the leftover cents (fewer than the number of weights) are given one each to the entries with the **largest weights**, ties to
      the lower index. `total >= 0` and every weight `>= 0` (else `IllegalArgumentException`); when the weights add up to `0`
      every share is `0` (and a positive `total` is an `IllegalArgumentException`).

    ## `Item(name, priceCents, sharedBy)`

    A dish with a price and the list of diners (names) who share it. `priceCents >= 0`; `sharedBy` must not be empty and must
    not name a diner twice, else `IllegalArgumentException`. Fields are public and final (`sharedBy` is copied into an unmodifiable
    list).

    ## `Bill.compute(items, discountCents, taxBp, tipBp, tipOnTax)` returns `List<Share>`

    1. Every item is split among its diners with `Split.splitItem` (leftover cents to the first names *in the item's list*). A
       diner's `sub` is the sum of their parts. Diners are reported in the order they first appear in the items.
    2. The coupon `discountCents` (`0 <= discountCents <= sum of all sub`, else `IllegalArgumentException`) is spread over the
       diners with `Split.allocate(discount, subs)`. `net = sub - discount` for each diner; `N` is the sum of the nets.
    3. `T = roundDiv(N * taxBp, 10000)` (half up) is spread over the nets with `allocate`: that is every diner's `tax`.
    4. `P = roundDiv(base * tipBp, 10000)` where `base` is `N` or, with `tipOnTax`, `N + T`; it is spread over the nets with
       `allocate`: every diner's `tip`.
    5. A diner's `total` is `net + tax + tip`. The totals therefore add up to exactly `N + T + P`.

    `taxBp` and `tipBp` must be `0..10000` (`IllegalArgumentException`). A `Share` has public final fields `diner`, `sub`,
    `discount`, `tax`, `tip` and `total`. With no items the result is an empty list (and only a zero coupon is allowed).
''')

ITEM = dd(r'''
    package tab;

    import java.util.ArrayList;
    import java.util.Collections;
    import java.util.HashSet;
    import java.util.List;
    import java.util.Set;

    public final class Item {
        public final String name;
        public final int priceCents;
        public final List<String> sharedBy;

        public Item(String name, int priceCents, List<String> sharedBy) {
            if (priceCents < 0) {
                throw new IllegalArgumentException("price must not be negative");
            }
            if (sharedBy.isEmpty()) {
                throw new IllegalArgumentException("a dish needs at least one diner");
            }
            Set<String> seen = new HashSet<>(sharedBy);
            if (seen.size() != sharedBy.size()) {
                throw new IllegalArgumentException("a diner is listed twice");
            }
            this.name = name;
            this.priceCents = priceCents;
            this.sharedBy = Collections.unmodifiableList(new ArrayList<>(sharedBy));
        }
    }
''')

SHARE = dd(r'''
    package tab;

    public final class Share {
        public final String diner;
        public final int sub;
        public final int discount;
        public final int tax;
        public final int tip;
        public final int total;

        public Share(String diner, int sub, int discount, int tax, int tip) {
            this.diner = diner;
            this.sub = sub;
            this.discount = discount;
            this.tax = tax;
            this.tip = tip;
            this.total = sub - discount + tax + tip;
        }
    }
''')

SPLIT = dd(r'''
    package tab;

    public final class Split {
        private Split() {}

        public static int[] splitItem(int price, int k) {
            if (price < 0 || k < 1) {
                throw new IllegalArgumentException("price must be >= 0 and k >= 1");
            }
            int[] parts = new int[k];
            int base = price / k;
            int extra = price % k;
            for (int i = 0; i < k; i++) {
                parts[i] = base + (i < extra ? 1 : 0);
            }
            return parts;
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
            int given = 0;
            for (int i = 0; i < weights.length; i++) {
                shares[i] = (int) ((long) total * weights[i] / sum);
                given += shares[i];
            }
            boolean[] taken = new boolean[weights.length];
            for (int left = total - given; left > 0; left--) {
                int best = -1;
                for (int i = 0; i < weights.length; i++) {
                    if (!taken[i] && (best < 0 || weights[i] > weights[best])) {
                        best = i;
                    }
                }
                shares[best]++;
                taken[best] = true;
            }
            return shares;
        }
    }
''')

BILL = dd(r'''
    package tab;

    import java.util.ArrayList;
    import java.util.LinkedHashMap;
    import java.util.List;
    import java.util.Map;

    public final class Bill {
        private Bill() {}

        private static int roundDiv(long n, long d) {
            return (int) ((2 * n + d) / (2 * d));
        }

        public static List<Share> compute(List<Item> items, int discountCents, int taxBp, int tipBp, boolean tipOnTax) {
            if (taxBp < 0 || taxBp > 10000 || tipBp < 0 || tipBp > 10000) {
                throw new IllegalArgumentException("rates must be between 0 and 10000 basis points");
            }
            Map<String, Integer> subs = new LinkedHashMap<>();
            for (Item item : items) {
                int[] parts = Split.splitItem(item.priceCents, item.sharedBy.size());
                for (int i = 0; i < parts.length; i++) {
                    subs.merge(item.sharedBy.get(i), parts[i], Integer::sum);
                }
            }
            List<String> diners = new ArrayList<>(subs.keySet());
            int[] sub = new int[diners.size()];
            int all = 0;
            for (int i = 0; i < sub.length; i++) {
                sub[i] = subs.get(diners.get(i));
                all += sub[i];
            }
            if (discountCents < 0 || discountCents > all) {
                throw new IllegalArgumentException("coupon out of range");
            }
            int[] discount = Split.allocate(discountCents, sub);
            int[] net = new int[sub.length];
            long netTotal = 0;
            for (int i = 0; i < net.length; i++) {
                net[i] = sub[i] - discount[i];
                netTotal += net[i];
            }
            int taxTotal = roundDiv(netTotal * taxBp, 10000);
            int tipTotal = roundDiv((tipOnTax ? netTotal + taxTotal : netTotal) * tipBp, 10000);
            int[] tax = Split.allocate(taxTotal, net);
            int[] tip = Split.allocate(tipTotal, net);
            List<Share> out = new ArrayList<>();
            for (int i = 0; i < net.length; i++) {
                out.add(new Share(diners.get(i), sub[i], discount[i], tax[i], tip[i]));
            }
            return out;
        }
    }
''')

BASIC = dd(r'''
    import tab.Split;

    public class BasicTests {
        public static void run() {
            Check.test("split an item", () -> Check.eq(new int[] {867, 866, 866}, Split.splitItem(2599, 3)));
            Check.test("allocate", () -> Check.eq(new int[] {5, 5}, Split.allocate(10, new int[] {1, 1})));
        }
    }
''')

FULL = dd(r'''
    import java.util.ArrayList;
    import java.util.List;
    import tab.Bill;
    import tab.Item;
    import tab.Share;
    import tab.Split;

    public class FullTests {
        static Item item(String name, int price, String... diners) {
            return new Item(name, price, List.of(diners));
        }

        static List<Item> dinner() {
            List<Item> l = new ArrayList<>();
            l.add(item("Pizza", 2599, "ann", "bob", "cy"));
            l.add(item("Salad", 1100, "bob"));
            l.add(item("Wine", 3000, "ann", "cy"));
            l.add(item("Dessert", 701, "cy", "ann"));
            return l;
        }

        static String line(Share s) {
            return s.diner + ":" + s.sub + "/" + s.discount + "/" + s.tax + "/" + s.tip + "=" + s.total;
        }

        static String lines(List<Share> shares) {
            StringBuilder sb = new StringBuilder();
            for (Share s : shares) {
                sb.append(line(s)).append(' ');
            }
            return sb.toString().trim();
        }

        public static void run() {
            Check.test("splitItem leftover cents go to the first", () -> {
                Check.eq(new int[] {867, 866, 866}, Split.splitItem(2599, 3));
                Check.eq(new int[] {351, 350}, Split.splitItem(701, 2));
                Check.eq(new int[] {2, 2, 1}, Split.splitItem(5, 3));
                Check.eq(new int[] {0, 0}, Split.splitItem(0, 2));
                Check.eq(new int[] {1, 0, 0, 0}, Split.splitItem(1, 4));
                Check.eq(new int[] {7}, Split.splitItem(7, 1));
                Check.eq(new int[] {5, 5, 5, 5}, Split.splitItem(20, 4));
                Check.eq(new int[] {4, 3, 3}, Split.splitItem(10, 3));
            });

            Check.test("splitItem validation", () -> {
                Check.raises(IllegalArgumentException.class, () -> Split.splitItem(-1, 2));
                Check.raises(IllegalArgumentException.class, () -> Split.splitItem(10, 0));
                Check.raises(IllegalArgumentException.class, () -> Split.splitItem(10, -1));
                Check.eq(new int[] {0}, Split.splitItem(0, 1));
            });

            Check.test("allocate: leftover goes to the largest weights", () -> {
                Check.eq(new int[] {1, 1, 0}, Split.allocate(2, new int[] {5, 5, 1}));
                Check.eq(new int[] {1, 0, 0, 2}, Split.allocate(3, new int[] {2, 2, 2, 9}));
                Check.eq(new int[] {0, 0, 5}, Split.allocate(5, new int[] {0, 0, 7}));
                Check.eq(new int[] {184, 132, 184}, Split.allocate(500, new int[] {2717, 1966, 2717}));
                Check.eq(new int[] {203, 146, 203}, Split.allocate(552, new int[] {2533, 1834, 2533}));
                Check.eq(new int[] {0, 0}, Split.allocate(0, new int[] {3, 4}));
            });

            Check.test("allocate: ties and small totals", () -> {
                Check.eq(new int[] {0, 1, 0}, Split.allocate(1, new int[] {1, 3, 3}));
                Check.eq(new int[] {1, 0}, Split.allocate(1, new int[] {5, 5}));
                Check.eq(new int[] {1, 1}, Split.allocate(2, new int[] {5, 5}));
                Check.eq(new int[] {1, 0, 0}, Split.allocate(1, new int[] {9, 1, 1}));
                Check.eq(new int[] {0, 1}, Split.allocate(1, new int[] {1, 9}));
                Check.eq(new int[] {3, 1, 0}, Split.allocate(4, new int[] {4, 1, 1}));
            });

            Check.test("allocate always adds up", () -> {
                int[][] ws = {{1, 2, 3}, {7, 7, 7, 7}, {100, 1}, {5, 5, 5, 5, 5}, {13, 0, 29, 5}};
                for (int[] w : ws) {
                    for (int total = 0; total < 80; total++) {
                        int sum = 0;
                        for (int s : Split.allocate(total, w)) {
                            sum += s;
                        }
                        Check.eq(total, sum);
                    }
                }
            });

            Check.test("allocate validation", () -> {
                Check.raises(IllegalArgumentException.class, () -> Split.allocate(-1, new int[] {1}));
                Check.raises(IllegalArgumentException.class, () -> Split.allocate(1, new int[] {1, -1}));
                Check.raises(IllegalArgumentException.class, () -> Split.allocate(1, new int[] {0, 0}));
                Check.raises(IllegalArgumentException.class, () -> Split.allocate(1, new int[] {}));
                Check.eq(new int[] {0}, Split.allocate(0, new int[] {0}));
            });

            Check.test("item validation", () -> {
                Check.raises(IllegalArgumentException.class, () -> new Item("x", -1, List.of("a")));
                Check.raises(IllegalArgumentException.class, () -> new Item("x", 10, List.of()));
                Check.raises(IllegalArgumentException.class, () -> new Item("x", 10, List.of("a", "b", "a")));
                Item it = new Item("x", 0, List.of("a", "b"));
                Check.eq("x", it.name);
                Check.eq(2, it.sharedBy.size());
                Check.raises(UnsupportedOperationException.class, () -> it.sharedBy.add("c"));
                List<String> mutable = new ArrayList<>(List.of("a"));
                Item copy = new Item("y", 5, mutable);
                mutable.add("b");
                Check.eq(1, copy.sharedBy.size());
            });

            Check.test("no coupon, tax or tip", () -> {
                Check.eq("ann:2717/0/0/0=2717 bob:1966/0/0/0=1966 cy:2717/0/0/0=2717", lines(Bill.compute(dinner(), 0, 0, 0, false)));
            });

            Check.test("coupon, tax and tip", () -> {
                Check.eq("ann:2717/184/203/456=3192 bob:1966/132/146/330=2310 cy:2717/184/203/456=3192",
                    lines(Bill.compute(dinner(), 500, 800, 1800, false)));
            });

            Check.test("tip on tax", () -> {
                Check.eq("ann:2717/184/203/493=3229 bob:1966/132/146/356=2336 cy:2717/184/203/492=3228",
                    lines(Bill.compute(dinner(), 500, 800, 1800, true)));
            });

            Check.test("tip only", () -> {
                Check.eq("ann:2717/0/0/544=3261 bob:1966/0/0/393=2359 cy:2717/0/0/543=3260", lines(Bill.compute(dinner(), 0, 0, 2000, false)));
            });

            Check.test("the totals add up to net + tax + tip", () -> {
                int[][] params = {{0, 0, 0}, {500, 800, 1800}, {123, 725, 1250}, {7399, 1000, 1000}, {1, 1, 1}};
                for (int[] p : params) {
                    for (boolean onTax : new boolean[] {false, true}) {
                        List<Share> shares = Bill.compute(dinner(), p[0], p[1], p[2], onTax);
                        int total = 0;
                        int sub = 0;
                        for (Share s : shares) {
                            total += s.total;
                            sub += s.sub;
                        }
                        int n = 7400 - p[0];
                        int tax = (2 * n * p[1] + 10000) / 20000;
                        int tip = (2 * (onTax ? n + tax : n) * p[2] + 10000) / 20000;
                        Check.eq(7400, sub);
                        Check.eq(n + tax + tip, total);
                    }
                }
            });

            Check.test("a coupon for the whole bill", () -> {
                List<Share> shares = Bill.compute(dinner(), 7400, 800, 1800, false);
                for (Share s : shares) {
                    Check.eq(s.sub, s.discount);
                    Check.eq(0, s.tax);
                    Check.eq(0, s.tip);
                    Check.eq(0, s.total);
                }
            });

            Check.test("diner order follows first appearance", () -> {
                List<Item> l = new ArrayList<>();
                l.add(item("a", 100, "zed", "amy"));
                l.add(item("b", 50, "bob", "zed"));
                List<Share> shares = Bill.compute(l, 0, 0, 0, false);
                Check.eq("zed", shares.get(0).diner);
                Check.eq("amy", shares.get(1).diner);
                Check.eq("bob", shares.get(2).diner);
                Check.eq(75, shares.get(0).sub);
                Check.eq(50, shares.get(1).sub);
                Check.eq(25, shares.get(2).sub);
            });

            Check.test("tax and tip round half up on the totals", () -> {
                List<Item> l = new ArrayList<>();
                l.add(item("x", 100, "a"));
                l.add(item("y", 100, "b"));
                List<Share> s = Bill.compute(l, 0, 0, 1500, false);
                Check.eq(15, s.get(0).tip);
                Check.eq(15, s.get(1).tip);
                List<Item> tiny = new ArrayList<>();
                tiny.add(item("x", 1, "a", "b"));
                List<Share> t = Bill.compute(tiny, 0, 1000, 1000, false);
                Check.eq(1, t.get(0).total);
                Check.eq(0, t.get(1).total);
                Check.eq(0, t.get(0).tax);
                List<Item> five = new ArrayList<>();
                five.add(item("x", 5, "a"));
                Check.eq(1, Bill.compute(five, 0, 1000, 0, false).get(0).tax);
                List<Item> four = new ArrayList<>();
                four.add(item("x", 4, "a"));
                Check.eq(0, Bill.compute(four, 0, 1000, 0, false).get(0).tax);
            });

            Check.test("bill validation", () -> {
                Check.raises(IllegalArgumentException.class, () -> Bill.compute(dinner(), -1, 0, 0, false));
                Check.raises(IllegalArgumentException.class, () -> Bill.compute(dinner(), 7401, 0, 0, false));
                Check.raises(IllegalArgumentException.class, () -> Bill.compute(dinner(), 0, -1, 0, false));
                Check.raises(IllegalArgumentException.class, () -> Bill.compute(dinner(), 0, 10001, 0, false));
                Check.raises(IllegalArgumentException.class, () -> Bill.compute(dinner(), 0, 0, -1, false));
                Check.raises(IllegalArgumentException.class, () -> Bill.compute(dinner(), 0, 0, 10001, false));
                Check.eq(3, Bill.compute(dinner(), 7400, 10000, 10000, true).size());
                Check.eq(0, Bill.compute(new ArrayList<>(), 0, 800, 800, false).size());
                Check.raises(IllegalArgumentException.class, () -> Bill.compute(new ArrayList<>(), 1, 0, 0, false));
            });
        }
    }
''')

LIB = Lib(
    name="billsplit", lang="java", title="the billsplit library",
    blurb="The group-dining app uses billsplit to work out what everyone at the table owes, including shared dishes, a coupon, tax and tip.",
    files={"src/tab/Item.java": ITEM, "src/tab/Share.java": SHARE, "src/tab/Split.java": SPLIT, "src/tab/Bill.java": BILL,
           "README.md": README, ".gitignore": "build/\n"},
    visible_tests={"test/Check.java": JAVA_CHECK, "test/BasicTests.java": BASIC, "test/TestMain.java": java_test_main("BasicTests")},
    hidden_tests={"test/FullTests.java": FULL, "test/TestMain.java": java_test_main("BasicTests", "FullTests")},
    mutate=["src/tab/Bill.java", "src/tab/Split.java", "src/tab/Item.java"], difficulty=1, tags=["restaurant", "money", "allocation"],
    probe_import="import java.util.*;\nimport tab.*;",
    probes=[
        "Split.splitItem(2599, 3)", "Split.splitItem(701, 2)", "Split.splitItem(1, 4)", "Split.splitItem(10, 0)",
        "Split.allocate(500, new int[] {2717, 1966, 2717})", "Split.allocate(3, new int[] {2, 2, 2, 9})", "Split.allocate(1, new int[] {1, 3, 3})", "Split.allocate(1, new int[] {0, 0})",
        "Bill.compute(List.of(new Item(\"p\", 2599, List.of(\"ann\", \"bob\", \"cy\")), new Item(\"s\", 1100, List.of(\"bob\"))), 0, 0, 0, false).get(0).sub",
        "Bill.compute(List.of(new Item(\"x\", 100, List.of(\"a\")), new Item(\"y\", 100, List.of(\"b\"))), 0, 0, 1500, false).get(1).tip",
        "Bill.compute(List.of(new Item(\"x\", 5, List.of(\"a\"))), 0, 1000, 0, false).get(0).tax",
        "Bill.compute(List.of(new Item(\"x\", 4, List.of(\"a\"))), 0, 1000, 0, false).get(0).tax",
        "Bill.compute(List.of(new Item(\"x\", 1000, List.of(\"a\", \"b\"))), 1000, 800, 1800, true).get(0).total",
        "Bill.compute(List.of(new Item(\"x\", 3000, List.of(\"a\")), new Item(\"y\", 1000, List.of(\"b\"))), 400, 0, 0, false).get(0).discount",
        "Bill.compute(List.of(new Item(\"x\", 100, List.of(\"zed\", \"amy\")), new Item(\"y\", 50, List.of(\"bob\", \"zed\"))), 0, 0, 0, false).get(0).diner",
        "Bill.compute(List.of(new Item(\"x\", 100, List.of(\"a\"))), 101, 0, 0, false)",
    ],
)

register_libs([LIB], n=8)
