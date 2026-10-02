"""Java identity and equality: equals/hashCode/compareTo contracts, boxing and BigDecimal (seat reservations, money)."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A: seat reservations.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # seats

    Seat reservations of a small theatre (plain Java: `rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java') && java -cp build
    TestMain`).

    ## `seats.SeatId`
    An immutable seat: a row letter `A`-`Z` and a number 1-999 (`IllegalArgumentException` otherwise). `parse("B12")`, `row()`, `number()`, `toString()` (`B12`).
    Two `SeatId`s with the same row and number are **equal in every collection** (`equals(Object)` and `hashCode()` agree). `compareTo` orders by row, then by
    number, and is consistent with `equals`.

    ## `seats.Reservations`
    * `book(seat, customer)`: `true`, or `false` if the seat is taken. `holder(seat)` returns the customer or `null`. `release(seat, customer)`: only the holder can
      release; returns whether it did.
    * `seatsOf(customer)`: a `SortedSet<SeatId>` of the customer's seats.
    * `sameCustomer(a, b)`: names are equal ignoring case and surrounding white space.
    * `joinWaitlist(ticketNo)` (ignored if already waiting), `leaveWaitlist(ticketNo)` (`true` if it was waiting, else `false`), `waitlistPosition(ticketNo)`
      (1-based, `-1` if not waiting). Ticket numbers are arbitrary ints.
    * `sameTickets(a, b)`: two maps `name -> count` hold the same entries (same names, equal counts, counts can be any size).
''')

A_SEAT = dd('''
    package seats;

    public final class SeatId implements Comparable<SeatId> {
        private final char row;
        private final int number;

        public SeatId(char row, int number) {
            if (row < 'A' || row > 'Z' || number < 1 || number > 999) {
                throw new IllegalArgumentException("bad seat " + row + number);
            }
            this.row = row;
            this.number = number;
        }

        public static SeatId parse(String text) {
            if (text == null || !text.matches("[A-Z][0-9]{1,3}")) {
                throw new IllegalArgumentException("bad seat: " + text);
            }
            return new SeatId(text.charAt(0), Integer.parseInt(text.substring(1)));
        }

        public char row() {
            return row;
        }

        public int number() {
            return number;
        }

        @Override
        public boolean equals(Object o) {
            if (this == o) {
                return true;
            }
            if (!(o instanceof SeatId)) {
                return false;
            }
            SeatId s = (SeatId) o;
            return row == s.row && number == s.number;
        }

        @Override
        public int hashCode() {
            return 31 * row + number;
        }

        @Override
        public int compareTo(SeatId o) {
            int c = Character.compare(row, o.row);
            return c != 0 ? c : Integer.compare(number, o.number);
        }

        @Override
        public String toString() {
            return "" + row + number;
        }
    }
''')

A_RES = dd('''
    package seats;

    import java.util.ArrayList;
    import java.util.HashMap;
    import java.util.List;
    import java.util.Map;
    import java.util.SortedSet;
    import java.util.TreeSet;

    public final class Reservations {
        private final Map<SeatId, String> holders = new HashMap<>();
        private final List<Integer> waitlist = new ArrayList<>();

        public boolean book(SeatId seat, String customer) {
            if (holders.containsKey(seat)) {
                return false;
            }
            holders.put(seat, customer);
            return true;
        }

        public String holder(SeatId seat) {
            return holders.get(seat);
        }

        public boolean release(SeatId seat, String customer) {
            if (!customer.equals(holders.get(seat))) {
                return false;
            }
            holders.remove(seat);
            return true;
        }

        public SortedSet<SeatId> seatsOf(String customer) {
            SortedSet<SeatId> out = new TreeSet<>();
            for (Map.Entry<SeatId, String> e : holders.entrySet()) {
                if (e.getValue().equals(customer)) {
                    out.add(e.getKey());
                }
            }
            return out;
        }

        public static boolean sameCustomer(String a, String b) {
            return a.trim().toLowerCase().equals(b.trim().toLowerCase());
        }

        public void joinWaitlist(int ticketNo) {
            if (!waitlist.contains(ticketNo)) {
                waitlist.add(ticketNo);
            }
        }

        public boolean leaveWaitlist(int ticketNo) {
            return waitlist.remove(Integer.valueOf(ticketNo));
        }

        public int waitlistPosition(int ticketNo) {
            int i = waitlist.indexOf(ticketNo);
            return i < 0 ? -1 : i + 1;
        }

        public static boolean sameTickets(Map<String, Integer> a, Map<String, Integer> b) {
            if (!a.keySet().equals(b.keySet())) {
                return false;
            }
            for (String k : a.keySet()) {
                if (!a.get(k).equals(b.get(k))) {
                    return false;
                }
            }
            return true;
        }
    }
''')

A_VISIBLE = {
    "tests/TestMain.java": dd('''
        import seats.Reservations;
        import seats.SeatId;

        public class TestMain {
            public static void main(String[] args) {
                Reservations r = new Reservations();
                SeatId a1 = new SeatId('A', 1);
                if (!r.book(a1, "ann") || r.book(a1, "bob")) {
                    System.out.println("FAIL booking the same object twice");
                    System.exit(1);
                }
                if (!a1.toString().equals("A1") || !SeatId.parse("B12").toString().equals("B12")) {
                    System.out.println("FAIL toString/parse");
                    System.exit(1);
                }
                System.out.println("all checks passed");
            }
        }
    '''),
}

A_HIDDEN = {
    "tests/TestMain.java": dd('''
        import java.util.ArrayList;
        import java.util.HashMap;
        import java.util.HashSet;
        import java.util.List;
        import java.util.Map;
        import java.util.Set;
        import java.util.TreeSet;
        import seats.Reservations;
        import seats.SeatId;

        public class TestMain {
            static int failures = 0;

            static void check(String what, boolean ok) {
                if (!ok) {
                    failures++;
                    System.out.println("FAIL " + what);
                }
            }

            static List<String> names(Iterable<SeatId> seats) {
                List<String> out = new ArrayList<>();
                for (SeatId s : seats) {
                    out.add(s.toString());
                }
                return out;
            }

            public static void main(String[] args) {
                // equality and hashing of seats
                SeatId a = new SeatId('B', 12);
                SeatId b = SeatId.parse("B12");
                Object asObject = b;
                check("equals(Object) on equal seats", a.equals(asObject));
                check("equal seats have equal hash codes", a.hashCode() == b.hashCode());
                check("different seats are not equal", !a.equals(new SeatId('B', 13)) && !a.equals(new SeatId('C', 12)) && !a.equals("B12") && !a.equals(null));
                Set<SeatId> set = new HashSet<>();
                set.add(a);
                set.add(b);
                set.add(new SeatId('A', 1));
                check("a HashSet treats equal seats as one", set.size() == 2 && set.contains(new SeatId('B', 12)));

                Reservations r = new Reservations();
                check("book", r.book(new SeatId('A', 1), "ann"));
                check("booking an equal seat again is refused", !r.book(new SeatId('A', 1), "bob"));
                check("holder through an equal seat", "ann".equals(r.holder(SeatId.parse("A1"))));
                check("unknown seat has no holder", r.holder(new SeatId('Z', 999)) == null);
                check("only the holder can release", !r.release(new SeatId('A', 1), "bob") && r.release(new SeatId('A', 1), "ann") && r.holder(new SeatId('A', 1)) == null);
                check("rebook after release", r.book(new SeatId('A', 1), "bob"));

                // ordering
                Reservations s = new Reservations();
                s.book(new SeatId('C', 3), "kim");
                s.book(new SeatId('A', 10), "kim");
                s.book(new SeatId('A', 2), "kim");
                s.book(new SeatId('C', 1), "kim");
                s.book(new SeatId('B', 7), "lee");
                check("seats of a customer in order", names(s.seatsOf("kim")).equals(List.of("A2", "A10", "C1", "C3")));
                check("seats of another customer", names(s.seatsOf("lee")).equals(List.of("B7")));
                check("seats of nobody", s.seatsOf("zed").isEmpty());
                TreeSet<SeatId> tree = new TreeSet<>(List.of(new SeatId('A', 5), new SeatId('A', 1), new SeatId('A', 3)));
                check("compareTo separates seats of one row", names(tree).equals(List.of("A1", "A3", "A5")));
                check("compareTo is consistent with equals", new SeatId('A', 1).compareTo(new SeatId('A', 1)) == 0 && new SeatId('A', 1).compareTo(new SeatId('A', 2)) < 0
                        && new SeatId('B', 1).compareTo(new SeatId('A', 999)) > 0);

                // validation
                for (String bad : new String[] {"", "a1", "A", "A0", "A1000", "AA1", "1A", "A-1"}) {
                    boolean threw = false;
                    try {
                        SeatId.parse(bad);
                    } catch (IllegalArgumentException e) {
                        threw = true;
                    }
                    check("parse(" + bad + ") is rejected", threw);
                }

                // customers: equal text in different objects
                String built = new String("ann");
                check("sameCustomer compares text", Reservations.sameCustomer(built, "ann"));
                check("sameCustomer ignores case and spaces", Reservations.sameCustomer("  Ann ", new String("aNN")));
                check("sameCustomer tells people apart", !Reservations.sameCustomer("ann", "anna"));

                // waitlist: ticket numbers are ints, not positions
                Reservations w = new Reservations();
                w.joinWaitlist(1001);
                w.joinWaitlist(1002);
                w.joinWaitlist(1003);
                w.joinWaitlist(1002);
                check("positions", w.waitlistPosition(1001) == 1 && w.waitlistPosition(1002) == 2 && w.waitlistPosition(1003) == 3 && w.waitlistPosition(5) == -1);
                check("leaving by ticket number", w.leaveWaitlist(1002));
                check("positions after leaving", w.waitlistPosition(1003) == 2 && w.waitlistPosition(1002) == -1);
                check("leaving twice", !w.leaveWaitlist(1002));
                check("leaving with a small number that is not a ticket", !w.leaveWaitlist(1));
                w.joinWaitlist(0);
                check("ticket 0", w.waitlistPosition(0) == 3 && w.leaveWaitlist(0));

                // counts above the Integer cache
                Map<String, Integer> x = new HashMap<>();
                Map<String, Integer> y = new HashMap<>();
                x.put("stalls", 5000);
                y.put("stalls", Integer.parseInt("5000"));
                x.put("balcony", 12);
                y.put("balcony", Integer.valueOf(12));
                check("same ticket counts above 127", Reservations.sameTickets(x, y));
                y.put("balcony", 13);
                check("different counts", !Reservations.sameTickets(x, y));
                y.put("balcony", 12);
                y.put("boxes", 1);
                check("different names", !Reservations.sameTickets(x, y));

                if (failures > 0) {
                    System.out.println(failures + " check(s) failed");
                    System.exit(1);
                }
                System.out.println("all checks passed");
            }
        }
    '''),
}


def _a_prompts():
    p = {}
    p["equals-overload"] = (
        "Booking the same seat twice works only when the very same `SeatId` object is used: `book(new SeatId('A', 1), ...)` followed by "
        "`book(new SeatId('A', 1), ...)` succeeds both times and `holder(SeatId.parse(\"A1\"))` returns null. `SeatId` has an `equals` and a "
        "`hashCode`, so I do not understand why the map does not find equal seats."
    )
    p["hashcode"] = (
        "Customers can book the same seat twice from two browser sessions, and `HashSet<SeatId>` keeps duplicates of equal seats. The `equals` "
        "method of `SeatId` is correct (I tested it directly). Look at what else the contract needs."
    )
    p["compare"] = (
        "A customer's ticket list shows only one seat per row: Kim booked A2, A10, C1 and C3 and the confirmation shows two seats. "
        "Sorted seat lists are built with `SortedSet<SeatId>` (a TreeSet)."
    )
    p["strings"] = (
        "Loyalty points are not credited when the name typed at the desk is not the same string object as the one in the booking (it happens for names "
        "read from the database or typed in); `sameCustomer(\"ann\", new String(\"ann\"))` is false. Names should be compared by content, ignoring case "
        "and surrounding spaces."
    )
    p["list-remove"] = (
        "Cancelling a waitlist ticket crashes with an `IndexOutOfBoundsException` for real ticket numbers like 1002, and for small numbers it removes "
        "someone else (ticket number 1 removes the *first person in the list*). `leaveWaitlist(ticketNo)` should remove the ticket with that number."
    )
    p["integer"] = (
        "The box office reconciliation says two ticket-count maps differ when both say 5000 stalls tickets, but is fine for counts like 12. "
        "Counts are `Integer` values; something compares them in a way that only works for small numbers."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "src/seats/SeatId.java": A_SEAT, "src/seats/Reservations.java": A_RES}
    sid, res = "src/seats/SeatId.java", "src/seats/Reservations.java"
    equals_old = ("    @Override\n    public boolean equals(Object o) {\n        if (this == o) {\n            return true;\n        }\n        if (!(o instanceof SeatId)) {\n            return false;\n        }\n        SeatId s = (SeatId) o;\n        return row == s.row && number == s.number;\n    }\n",
                  "    public boolean equals(SeatId s) {\n        return s != null && row == s.row && number == s.number;\n    }\n")
    bugs = [
        Bug("customer-names-compared-by-reference", 1, {res: [("        return a.trim().toLowerCase().equals(b.trim().toLowerCase());\n", "        return a.trim().toLowerCase() == b.trim().toLowerCase();\n")]}, P["strings"]),
        Bug("equals-overloaded-not-overridden", 3, {sid: [equals_old]}, P["equals-overload"]),
        Bug("equals-without-hashcode", 3, {sid: [("    @Override\n    public int hashCode() {\n        return 31 * row + number;\n    }\n\n", "")]}, P["hashcode"]),
        Bug("compareto-looks-at-the-row-only", 3, {sid: [("        int c = Character.compare(row, o.row);\n        return c != 0 ? c : Integer.compare(number, o.number);\n", "        return Character.compare(row, o.row);\n")]}, P["compare"]),
        Bug("waitlist-removes-by-position", 3, {res: [("        return waitlist.remove(Integer.valueOf(ticketNo));\n", "        return waitlist.remove(ticketNo) != null;\n")]}, P["list-remove"]),
        Bug("boxed-counts-compared-by-reference", 3, {res: [("            if (!a.get(k).equals(b.get(k))) {\n", "            if (a.get(k) != b.get(k)) {\n")]}, P["integer"]),
    ]
    return Base("seats", "java", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B: money with BigDecimal.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # cash

    A money value class on `BigDecimal` (plain Java: `rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java') && java -cp build TestMain`).

    * `Money.of(String, currency)` and `Money.of(double, currency)` (the double is read by its **decimal text**: `of(0.1, "EUR")` is exactly 0.1).
    * Equality is by value: same currency and the same numeric amount, **whatever the scale** (`2.0 EUR` equals `2.00 EUR`); `hashCode` agrees, so a `HashSet` holds one
      of them.
    * `plus(other)` needs the same currency (`IllegalArgumentException` otherwise).
    * `format()`: the amount rounded **half up** to two decimals in plain notation, a space and the currency: `1234567.80 USD`, `2.01 USD` for 2.005, `-0.01 USD` for -0.005.
    * `split(parts)`: `parts` amounts, each a multiple of 0.01, adding up to the amount rounded to cents; rounding never creates money: every part is the
      amount divided by `parts` rounded **down** to cents, and the leftover cents are given one each to the first parts. `parts < 1` or a negative amount is an
      `IllegalArgumentException`.
''')

B_MONEY = dd('''
    package cash;

    import java.math.BigDecimal;
    import java.math.RoundingMode;
    import java.util.ArrayList;
    import java.util.List;
    import java.util.Objects;

    public final class Money {
        private final BigDecimal amount;
        private final String currency;

        private Money(BigDecimal amount, String currency) {
            this.amount = amount;
            this.currency = currency;
        }

        public static Money of(String amount, String currency) {
            return new Money(new BigDecimal(amount), currency);
        }

        public static Money of(double amount, String currency) {
            return new Money(BigDecimal.valueOf(amount), currency);
        }

        public BigDecimal amount() {
            return amount;
        }

        public String currency() {
            return currency;
        }

        public Money plus(Money other) {
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("different currencies: " + currency + " and " + other.currency);
            }
            return new Money(amount.add(other.amount), currency);
        }

        public String format() {
            return amount.setScale(2, RoundingMode.HALF_UP).toPlainString() + " " + currency;
        }

        public List<Money> split(int parts) {
            if (parts < 1 || amount.signum() < 0) {
                throw new IllegalArgumentException("cannot split " + amount + " into " + parts);
            }
            BigDecimal total = amount.setScale(2, RoundingMode.HALF_UP);
            BigDecimal base = total.divide(BigDecimal.valueOf(parts), 2, RoundingMode.DOWN);
            BigDecimal rest = total.subtract(base.multiply(BigDecimal.valueOf(parts)));
            int extra = rest.movePointRight(2).intValueExact();
            List<Money> out = new ArrayList<>();
            for (int i = 0; i < parts; i++) {
                out.add(new Money(i < extra ? base.add(new BigDecimal("0.01")) : base, currency));
            }
            return out;
        }

        @Override
        public boolean equals(Object o) {
            if (this == o) {
                return true;
            }
            if (!(o instanceof Money)) {
                return false;
            }
            Money m = (Money) o;
            return currency.equals(m.currency) && amount.compareTo(m.amount) == 0;
        }

        @Override
        public int hashCode() {
            return Objects.hash(currency, amount.stripTrailingZeros());
        }

        @Override
        public String toString() {
            return amount.toPlainString() + " " + currency;
        }
    }
''')

B_VISIBLE = {
    "tests/TestMain.java": dd('''
        import cash.Money;

        public class TestMain {
            public static void main(String[] args) {
                if (!Money.of("10.00", "EUR").plus(Money.of("2.50", "EUR")).format().equals("12.50 EUR")) {
                    System.out.println("FAIL plus/format");
                    System.exit(1);
                }
                if (!Money.of("3.00", "USD").equals(Money.of("3.00", "USD"))) {
                    System.out.println("FAIL equals");
                    System.exit(1);
                }
                System.out.println("all checks passed");
            }
        }
    '''),
}

B_HIDDEN = {
    "tests/TestMain.java": dd('''
        import cash.Money;
        import java.math.BigDecimal;
        import java.util.ArrayList;
        import java.util.HashSet;
        import java.util.List;
        import java.util.Set;

        public class TestMain {
            static int failures = 0;

            static void check(String what, boolean ok) {
                if (!ok) {
                    failures++;
                    System.out.println("FAIL " + what);
                }
            }

            static List<String> amounts(List<Money> parts) {
                List<String> out = new ArrayList<>();
                for (Money m : parts) {
                    out.add(m.amount().toPlainString());
                }
                return out;
            }

            public static void main(String[] args) {
                // equality by value, whatever the scale
                check("2.0 equals 2.00", Money.of("2.0", "EUR").equals(Money.of("2.00", "EUR")));
                check("hash codes agree", Money.of("2.0", "EUR").hashCode() == Money.of("2.00", "EUR").hashCode());
                check("hash codes agree for 100 and 1E+2", Money.of("100", "EUR").hashCode() == Money.of("1E+2", "EUR").hashCode());
                check("zero at any scale", Money.of("0", "EUR").equals(Money.of("0.000", "EUR")) && Money.of("0", "EUR").hashCode() == Money.of("0.00", "EUR").hashCode());
                check("currency matters", !Money.of("2", "EUR").equals(Money.of("2", "USD")));
                check("amount matters", !Money.of("2.00", "EUR").equals(Money.of("2.01", "EUR")));
                check("not equal to other types", !Money.of("2", "EUR").equals("2 EUR") && !Money.of("2", "EUR").equals(null));
                Set<Money> set = new HashSet<>();
                set.add(Money.of("5.5", "EUR"));
                set.add(Money.of("5.50", "EUR"));
                set.add(Money.of("5.500", "EUR"));
                check("a HashSet keeps one", set.size() == 1 && set.contains(Money.of("5.5000", "EUR")));

                // doubles by their decimal text
                check("of(0.1) is exactly 0.1", Money.of(0.1, "EUR").amount().equals(new BigDecimal("0.1")));
                check("of(19.99) is exactly 19.99", Money.of(19.99, "EUR").amount().equals(new BigDecimal("19.99")));
                check("of(0.1) equals of(\\"0.10\\")", Money.of(0.1, "EUR").equals(Money.of("0.10", "EUR")));
                check("of(100.0) equals 100", Money.of(100.0, "EUR").equals(Money.of("100", "EUR")));

                // plus
                check("plus", Money.of("0.1", "EUR").plus(Money.of("0.2", "EUR")).equals(Money.of("0.30", "EUR")));
                boolean threw = false;
                try {
                    Money.of("1", "EUR").plus(Money.of("1", "USD"));
                } catch (IllegalArgumentException e) {
                    threw = true;
                }
                check("plus of two currencies is refused", threw);

                // format
                check("format pads", Money.of("1", "USD").format().equals("1.00 USD"));
                check("format rounds half up", Money.of("2.005", "USD").format().equals("2.01 USD") && Money.of("2.004", "USD").format().equals("2.00 USD"));
                check("format rounds half up away from zero", Money.of("-0.005", "USD").format().equals("-0.01 USD"));
                check("format is plain notation", Money.of("1E+3", "USD").format().equals("1000.00 USD") && Money.of("1234567.8", "USD").format().equals("1234567.80 USD"));
                check("format of exact cents", Money.of("12.50", "EUR").format().equals("12.50 EUR"));

                // split
                check("10.00 into 3", amounts(Money.of("10.00", "EUR").split(3)).equals(List.of("3.34", "3.33", "3.33")));
                check("10.00 into 4", amounts(Money.of("10", "EUR").split(4)).equals(List.of("2.50", "2.50", "2.50", "2.50")));
                check("0.05 into 2", amounts(Money.of("0.05", "EUR").split(2)).equals(List.of("0.03", "0.02")));
                check("100 into 7", amounts(Money.of("100", "EUR").split(7)).equals(List.of("14.29", "14.29", "14.29", "14.29", "14.28", "14.28", "14.28")));
                check("1 into 1", amounts(Money.of("1", "EUR").split(1)).equals(List.of("1.00")));
                check("0.01 into 3", amounts(Money.of("0.01", "EUR").split(3)).equals(List.of("0.01", "0.00", "0.00")));
                check("2.005 is rounded to cents first", amounts(Money.of("2.005", "EUR").split(2)).equals(List.of("1.01", "1.00")));
                BigDecimal sum = BigDecimal.ZERO;
                for (Money part : Money.of("1000.00", "EUR").split(7)) {
                    sum = sum.add(part.amount());
                }
                check("parts add up", sum.compareTo(new BigDecimal("1000.00")) == 0);
                for (int bad : new int[] {0, -1}) {
                    boolean rejected = false;
                    try {
                        Money.of("1", "EUR").split(bad);
                    } catch (IllegalArgumentException e) {
                        rejected = true;
                    }
                    check("split(" + bad + ") is refused", rejected);
                }
                boolean negative = false;
                try {
                    Money.of("-1", "EUR").split(2);
                } catch (IllegalArgumentException e) {
                    negative = true;
                }
                check("negative amounts are refused", negative);

                if (failures > 0) {
                    System.out.println(failures + " check(s) failed");
                    System.exit(1);
                }
                System.out.println("all checks passed");
            }
        }
    '''),
}


def _b_prompts():
    p = {}
    p["equals-scale"] = (
        "`Money.of(\"2.0\", \"EUR\")` is not equal to `Money.of(\"2.00\", \"EUR\")`, so our duplicate-payment detection misses payments that "
        "arrive with a different number of decimals from different banks. Equality is supposed to be numeric."
    )
    p["hash-scale"] = (
        "Our de-duplication set (`HashSet<Money>`) keeps both `5.5 EUR` and `5.50 EUR` although `equals` says they are the same (I checked `equals` "
        "separately, it is fine). Look at how the hash code is built."
    )
    p["double"] = (
        "Amounts built from doubles carry binary noise: `Money.of(0.1, \"EUR\").amount()` prints `0.1000000000000000055511151231257827021181583404541015625`, "
        "so comparisons and totals are off. A double should be read by its decimal text."
    )
    p["divide"] = (
        "Splitting a bill in three throws `ArithmeticException: Non-terminating decimal expansion; no exact representable decimal result.` "
        "(`split(3)` of 10.00). Splitting in two or four is fine."
    )
    p["setscale"] = (
        "`format()` throws `ArithmeticException: Rounding necessary` for amounts with more than two decimals (like 2.005). The README says it "
        "rounds half up."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "src/cash/Money.java": B_MONEY}
    m = "src/cash/Money.java"
    bugs = [
        Bug("divide-without-a-scale", 1, {m: [("        BigDecimal base = total.divide(BigDecimal.valueOf(parts), 2, RoundingMode.DOWN);\n", "        BigDecimal base = total.divide(BigDecimal.valueOf(parts));\n")]}, P["divide"]),
        Bug("format-without-a-rounding-mode", 1, {m: [("        return amount.setScale(2, RoundingMode.HALF_UP).toPlainString() + \" \" + currency;\n", "        return amount.setScale(2).toPlainString() + \" \" + currency;\n")]}, P["setscale"]),
        Bug("doubles-through-the-binary-constructor", 3, {m: [("        return new Money(BigDecimal.valueOf(amount), currency);\n", "        return new Money(new BigDecimal(amount), currency);\n")]}, P["double"]),
        Bug("equals-compares-the-scale-too", 2, {m: [("        return currency.equals(m.currency) && amount.compareTo(m.amount) == 0;\n", "        return currency.equals(m.currency) && amount.equals(m.amount);\n")]}, P["equals-scale"]),
        Bug("hash-code-depends-on-the-scale", 3, {m: [("        return Objects.hash(currency, amount.stripTrailingZeros());\n", "        return Objects.hash(currency, amount);\n")]}, P["hash-scale"]),
    ]
    return Base("cash", "java", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-java-equality", category="fix", lang="java", kind="fix", n=11,
        summary="java equals/hashCode/compareTo contracts, reference comparison, list.remove(int) and BigDecimal (seats, money)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
