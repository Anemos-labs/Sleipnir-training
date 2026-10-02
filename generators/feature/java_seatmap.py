"""seatmap (java): a small box office extended with limits, seat maps, access seats, block search, pricing, holds, audit."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # seatmap

    The seat bookkeeping of a small theatre box office (Java 17, standard library only). A hall has rows `A`, `B`, ...
    with seats numbered from 1; a seat id is the row letter followed by the number, for example `C4`.
    The tests are a plain `TestMain` (no JUnit): `javac -d build $(find . -name '*.java') && java -cp build TestMain`.

    ## Layout

    * `src/seatmap/BoxOffice.java`: the rules.
    * `src/seatmap/Booking.java`: an immutable booking.
    * `test/TestMain.java`: tests.

    ## Basics

    * `new BoxOffice(rows, seatsPerRow)`: 1 to 26 rows and 1 to 99 seats per row, otherwise `IllegalArgumentException`.
    * `exists(seat)`, `isFree(seat)` (`IllegalArgumentException` for a seat that does not exist), `freeSeats()` (row by
      row, left to right).
    * `reserve(holder, seats...)` books seats and returns a `Booking` with ids `R001`, `R002`, ... A blank holder, no
      seats, a repeated seat or a seat that does not exist is an `IllegalArgumentException`; a seat that is already taken is
      an `IllegalStateException`. Nothing changes when a call fails. The price is 2500 cents per seat.
    * `Booking` has `id()`, `holder()`, `seats()` (unmodifiable list, in the requested order) and `priceCents()`.
    * `cancel(bookingId)` frees the seats and returns the booking; `booking(id)` and `cancel` throw
      `NoSuchElementException` for an unknown id. `bookings()` lists all bookings ordered by id.
''')

BOX = '''\
package seatmap;

import java.util.*;
@@uniq imports

/** Seats and bookings of one show. */
public class BoxOffice {
    private final int rows;
    private final int perRow;
    private final Map<String, Booking> bookings = new LinkedHashMap<>();
    private final Map<String, String> taken = new HashMap<>();
    private int nextId = 1;
    @@slot fields

    public BoxOffice(int rows, int perRow) {
        if (rows < 1 || rows > 26 || perRow < 1 || perRow > 99) {
            throw new IllegalArgumentException("hall size out of range");
        }
        this.rows = rows;
        this.perRow = perRow;
        @@slot ctor
    }

    public int rows() {
        return rows;
    }

    public int perRow() {
        return perRow;
    }

    /** Seat id for zero-based row and seat indexes. */
    public static String seatId(int row, int number) {
        return "" + (char) ('A' + row) + (number + 1);
    }

    public boolean exists(String seat) {
        if (seat == null || seat.length() < 2) {
            return false;
        }
        int row = seat.charAt(0) - 'A';
        if (row < 0 || row >= rows) {
            return false;
        }
        String digits = seat.substring(1);
        try {
            int n = Integer.parseInt(digits);
            return n >= 1 && n <= perRow && digits.equals(String.valueOf(n));
        } catch (NumberFormatException e) {
            return false;
        }
    }

    private void requireSeat(String seat) {
        if (!exists(seat)) {
            throw new IllegalArgumentException("no such seat: " + seat);
        }
    }

    public boolean isFree(String seat) {
        requireSeat(seat);
        return !taken.containsKey(seat);
    }

    public List<String> freeSeats() {
        List<String> out = new ArrayList<>();
        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < perRow; c++) {
                String s = seatId(r, c);
                if (!taken.containsKey(s)) {
                    out.add(s);
                }
            }
        }
        return out;
    }

    private Set<String> checked(String holder, String[] seats) {
        if (holder == null || holder.isBlank()) {
            throw new IllegalArgumentException("holder is required");
        }
        if (seats == null || seats.length == 0) {
            throw new IllegalArgumentException("at least one seat is required");
        }
        Set<String> want = new LinkedHashSet<>(Arrays.asList(seats));
        if (want.size() != seats.length) {
            throw new IllegalArgumentException("duplicate seat in request");
        }
        for (String s : want) {
            requireSeat(s);
            if (taken.containsKey(s)) {
                throw new IllegalStateException("seat taken: " + s);
            }
        }
        @@slot reserve_checks
        return want;
    }

    public Booking reserve(String holder, String... seats) {
        Set<String> want = checked(holder, seats);
        @@default price_call
        int price = want.size() * 2500;
        @@end
        String id = String.format("R%03d", nextId++);
        Booking b = new Booking(id, holder, new ArrayList<>(want), price);
        bookings.put(id, b);
        for (String s : want) {
            taken.put(s, id);
        }
        @@slot on_reserve
        return b;
    }

    public Booking booking(String id) {
        Booking b = bookings.get(id);
        if (b == null) {
            throw new NoSuchElementException("no such booking: " + id);
        }
        return b;
    }

    public Booking cancel(String bookingId) {
        Booking b = booking(bookingId);
        bookings.remove(bookingId);
        for (String s : b.seats()) {
            taken.remove(s);
        }
        @@slot on_cancel
        return b;
    }

    public List<Booking> bookings() {
        return new ArrayList<>(bookings.values());
    }

    @@blocks methods
}
'''

BOOKING = '''\
package seatmap;

import java.util.Collections;
import java.util.List;

/** An immutable booking. */
public final class Booking {
    private final String id;
    private final String holder;
    private final List<String> seats;
    private final int priceCents;

    Booking(String id, String holder, List<String> seats, int priceCents) {
        this.id = id;
        this.holder = holder;
        this.seats = Collections.unmodifiableList(seats);
        this.priceCents = priceCents;
    }

    public String id() {
        return id;
    }

    public String holder() {
        return holder;
    }

    public List<String> seats() {
        return seats;
    }

    public int priceCents() {
        return priceCents;
    }

    @Override
    public String toString() {
        return id + " " + holder + " " + seats + " " + priceCents;
    }
}
'''

TEST_HEAD = '''\
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.*;
import seatmap.*;
@@uniq imports

public class TestMain {
    static int failures = 0;

    static void eq(Object expected, Object actual, String msg) {
        if (!Objects.equals(expected, actual)) {
            failures++;
            System.out.println("FAIL: " + msg + ": expected <" + expected + "> but got <" + actual + ">");
        }
    }

    static void check(boolean cond, String msg) {
        if (!cond) {
            failures++;
            System.out.println("FAIL: " + msg);
        }
    }

    static void expect(Class<? extends Throwable> type, Runnable r, String msg) {
        try {
            r.run();
        } catch (Throwable t) {
            if (!type.isInstance(t)) {
                failures++;
                System.out.println("FAIL: " + msg + ": threw " + t);
            }
            return;
        }
        failures++;
        System.out.println("FAIL: " + msg + ": no exception");
    }

    static BoxOffice office() {
        return new BoxOffice(4, 6);
    }

    static List<String> list(String... xs) {
        return new ArrayList<>(Arrays.asList(xs));
    }

    @@blocks tests

    public static void main(String[] args) throws Exception {
        List<Method> tests = new ArrayList<>();
        for (Method m : TestMain.class.getDeclaredMethods()) {
            if (m.getName().startsWith("test") && m.getParameterCount() == 0) {
                tests.add(m);
            }
        }
        tests.sort(Comparator.comparing(Method::getName));
        for (Method m : tests) {
            try {
                m.invoke(null);
            } catch (InvocationTargetException e) {
                failures++;
                System.out.println("ERROR in " + m.getName() + ": " + e.getCause());
                e.getCause().printStackTrace(System.out);
            }
        }
        System.out.println(tests.size() + " tests, " + failures + " failures");
        if (failures > 0) {
            System.exit(1);
        }
    }
}
'''

VISIBLE_BASE = '''
    static void testReserveAndPrice() {
        BoxOffice o = office();
        Booking b = o.reserve("ana", "B2", "B3");
        eq("R001", b.id(), "id");
        eq(list("B2", "B3"), b.seats(), "seats");
        eq(5000, b.priceCents(), "price");
        check(!o.isFree("B2") && o.isFree("B4"), "free flags");
        eq(22, o.freeSeats().size(), "free count");
    }

    static void testTakenAndInvalid() {
        BoxOffice o = office();
        o.reserve("ana", "A1");
        expect(IllegalStateException.class, () -> o.reserve("bob", "A1", "A2"), "taken seat");
        check(o.isFree("A2"), "nothing changed");
        expect(IllegalArgumentException.class, () -> o.reserve("bob", "Z9"), "unknown seat");
        expect(IllegalArgumentException.class, () -> o.reserve(" ", "A2"), "blank holder");
    }

    static void testCancel() {
        BoxOffice o = office();
        Booking b = o.reserve("ana", "C1", "C2");
        eq(b, o.cancel("R001"), "cancel returns booking");
        check(o.isFree("C1"), "freed");
        expect(java.util.NoSuchElementException.class, () -> o.cancel("R001"), "cancel twice");
    }
'''

HIDDEN_BASE = '''
    static void testBaseRules() {
        BoxOffice o = office();
        eq(24, o.freeSeats().size(), "all free");
        eq(list("A1", "A2"), o.freeSeats().subList(0, 2), "row-major order");
        eq("B1", o.freeSeats().get(6), "second row starts at index 6");
        check(o.exists("D6") && !o.exists("D7") && !o.exists("E1") && !o.exists("A0") && !o.exists("A01") && !o.exists("") && !o.exists(null), "exists");
        expect(IllegalArgumentException.class, () -> o.isFree("Q3"), "isFree unknown");
        expect(IllegalArgumentException.class, () -> o.reserve("x"), "no seats");
        expect(IllegalArgumentException.class, () -> o.reserve("x", "A1", "A1"), "duplicate");
        expect(IllegalArgumentException.class, () -> o.reserve(null, "A1"), "null holder");
        expect(IllegalArgumentException.class, () -> new BoxOffice(0, 5), "no rows");
        expect(IllegalArgumentException.class, () -> new BoxOffice(27, 5), "too many rows");
        expect(IllegalArgumentException.class, () -> new BoxOffice(3, 100), "too wide");
        Booking b = o.reserve("ana", "D6", "D5");
        eq(list("D6", "D5"), b.seats(), "requested order kept");
        expect(UnsupportedOperationException.class, () -> b.seats().add("A1"), "seats immutable");
        Booking c = o.reserve("bob", "A1");
        eq("R002", c.id(), "second id");
        eq(list("R001", "R002"), ids(o.bookings()), "bookings by id");
        o.cancel("R001");
        eq(list("R002"), ids(o.bookings()), "after cancel");
        eq("R003", o.reserve("cy", "D5").id(), "ids are not reused");
        expect(java.util.NoSuchElementException.class, () -> o.booking("R404"), "unknown booking");
    }

    static List<String> ids(List<Booking> bs) {
        List<String> out = new ArrayList<>();
        for (Booking b : bs) {
            out.add(b.id());
        }
        return out;
    }
'''


def make_slices(rng: random.Random):
    limit = rng.choice([4, 6, 8])
    free_ch, taken_ch = rng.choice([(".", "#"), ("o", "x"), ("_", "X")])
    from_back = rng.choice([False, True])
    ticks = rng.choice([2, 3, 5])
    S = []

    S.append(Slice(
        id="booking-limit", title="Seats per booking", d=1,
        pitch=("One person block-booked the whole front row for a sold-out show.",
               "The box office wants a cap on how many seats a single booking may take."),
        reqs=(f"`reserve` rejects a request for more than {limit} seats with an `IllegalArgumentException` (the limit is public: `BoxOffice.MAX_SEATS`, an `int` constant). Exactly {limit} seats are fine.",
              "The limit is checked after the existing validation of the seats, and a rejected request changes nothing."),
        code={
            "src/seatmap/BoxOffice.java::fields": f"public static final int MAX_SEATS = {limit};",
            "src/seatmap/BoxOffice.java::reserve_checks": '''
                if (want.size() > MAX_SEATS) {
                    throw new IllegalArgumentException("at most " + MAX_SEATS + " seats per booking");
                }
            ''',
        },
        readme=f"## Seats per booking\n\nA booking may hold at most `BoxOffice.MAX_SEATS` ({limit}) seats; more is an `IllegalArgumentException`.\n",
        vtests='''
            static void testLimitConstant() {
                check(BoxOffice.MAX_SEATS >= 1, "limit exists");
            }
        ''',
        tests=fmt('''
            static void testSeatLimit() {
                BoxOffice o = new BoxOffice(5, 10);
                eq(__N__, BoxOffice.MAX_SEATS, "constant");
                String[] ok = new String[__N__];
                String[] tooMany = new String[__N__ + 1];
                for (int i = 0; i < tooMany.length; i++) {
                    tooMany[i] = "A" + (i + 1);
                    if (i < ok.length) {
                        ok[i] = "B" + (i + 1);
                    }
                }
                expect(IllegalArgumentException.class, () -> o.reserve("ana", tooMany), "one over the limit");
                eq(50, o.freeSeats().size(), "nothing changed");
                eq(__N__ * 2500, o.reserve("ana", ok).priceCents(), "exactly the limit");
                eq(50 - __N__, o.freeSeats().size(), "booked");
            }
        ''', N=limit),
    ))

    S.append(Slice(
        id="seat-map", title="Text seat map", d=2,
        pitch=("The front desk wants to see the hall at a glance instead of listing free seats.",
               "Staff would like a quick text picture of which seats are taken."),
        reqs=(f"`BoxOffice.render()` returns the seat map as text: one line per row, `ROW SEATS`, where ROW is the row letter, then one space, then one character per seat from left to right: `{free_ch}` for a free seat and `{taken_ch}` for a taken one. Every line ends with a newline.",
              "The map always shows the current state (bookings and cancellations)."),
        code={
            "src/seatmap/BoxOffice.java::methods": f'''
                public String render() {{
                    StringBuilder sb = new StringBuilder();
                    for (int r = 0; r < rows; r++) {{
                        sb.append((char) ('A' + r)).append(' ');
                        for (int c = 0; c < perRow; c++) {{
                            sb.append(taken.containsKey(seatId(r, c)) ? '{taken_ch}' : '{free_ch}');
                        }}
                        sb.append('\\n');
                    }}
                    return sb.toString();
                }}
            ''',
        },
        readme=f"## Seat map\n\n`render()` prints one line per row: the row letter, a space, and `{free_ch}` (free) or `{taken_ch}` (taken) for each seat.\n",
        vtests='''
            static void testRenderShape() {
                check(office().render().startsWith("A "), "starts with the row letter");
            }
        ''',
        tests=fmt('''
            static void testRender() {
                BoxOffice o = new BoxOffice(3, 5);
                eq("A __F____F____F____F____F__\\nB __F____F____F____F____F__\\nC __F____F____F____F____F__\\n", o.render(), "empty hall");
                o.reserve("ana", "A2", "A3", "C5");
                eq("A __F____T____T____F____F__\\nB __F____F____F____F____F__\\nC __F____F____F____F____T__\\n", o.render(), "some taken");
                o.cancel("R001");
                eq("A __F____F____F____F____F__\\nB __F____F____F____F____F__\\nC __F____F____F____F____F__\\n", o.render(), "after cancel");
            }
        ''', F=free_ch, T=taken_ch),
    ))

    S.append(Slice(
        id="accessible", title="Wheelchair seats", d=3,
        pitch=("Wheelchair spaces are being sold to people who do not need them and then wheelchair users cannot get in.",
               "A few seats must be kept for people who need step-free access."),
        reqs=("`markAccessible(String... seats)` flags seats as accessible (all-or-nothing: an `IllegalArgumentException` for any seat that does not exist, and then none is flagged). `isAccessible(seat)` says whether a seat is flagged (`IllegalArgumentException` for an unknown seat) and `accessibleSeats()` lists the flagged seats row by row, left to right.",
              "`reserve` refuses a request that contains an accessible seat with an `IllegalArgumentException` (checked after the existing validation).",
              "`reserveAccessible(holder, seats...)` is `reserve` for people who need access: the request must contain at least one accessible seat (otherwise `IllegalArgumentException`); the other seats may be ordinary companion seats. Everything else (ids, prices, taken seats) works as for `reserve`."),
        code={
            "src/seatmap/BoxOffice.java::fields": "private final Set<String> accessible = new HashSet<>();\nprivate boolean accessBooking;",
            "src/seatmap/BoxOffice.java::reserve_checks": '''
                if (!accessBooking) {
                    for (String s : want) {
                        if (accessible.contains(s)) {
                            throw new IllegalArgumentException("seat is kept for wheelchair users: " + s);
                        }
                    }
                }
            ''',
            "src/seatmap/BoxOffice.java::methods": '''
                public void markAccessible(String... seats) {
                    for (String s : seats) {
                        requireSeat(s);
                    }
                    accessible.addAll(Arrays.asList(seats));
                }

                public boolean isAccessible(String seat) {
                    requireSeat(seat);
                    return accessible.contains(seat);
                }

                public List<String> accessibleSeats() {
                    List<String> out = new ArrayList<>();
                    for (int r = 0; r < rows; r++) {
                        for (int c = 0; c < perRow; c++) {
                            if (accessible.contains(seatId(r, c))) {
                                out.add(seatId(r, c));
                            }
                        }
                    }
                    return out;
                }

                public Booking reserveAccessible(String holder, String... seats) {
                    boolean any = false;
                    if (seats != null) {
                        for (String s : seats) {
                            any |= accessible.contains(s);
                        }
                    }
                    if (!any) {
                        throw new IllegalArgumentException("at least one accessible seat is required");
                    }
                    accessBooking = true;
                    try {
                        return reserve(holder, seats);
                    } finally {
                        accessBooking = false;
                    }
                }
            ''',
        },
        readme=dd('''
            ## Wheelchair seats

            `markAccessible(seats...)`, `isAccessible(seat)`, `accessibleSeats()`. Plain `reserve` refuses accessible seats;
            `reserveAccessible(holder, seats...)` requires at least one accessible seat in the request and otherwise behaves like `reserve`.
        '''),
        vtests='''
            static void testMarkAccessible() {
                BoxOffice o = office();
                o.markAccessible("A1");
                check(o.isAccessible("A1") && !o.isAccessible("A2"), "flags");
            }
        ''',
        tests='''
            static void testAccessibleFlags() {
                BoxOffice o = office();
                o.markAccessible("C1", "A2", "A2");
                eq(list("A2", "C1"), o.accessibleSeats(), "row-major listing");
                expect(IllegalArgumentException.class, () -> o.markAccessible("B1", "Z9"), "unknown seat");
                check(!o.isAccessible("B1"), "all or nothing");
                expect(IllegalArgumentException.class, () -> o.isAccessible("Z9"), "isAccessible unknown");
                eq(list("A2", "C1"), o.accessibleSeats(), "unchanged");
            }

            static void testAccessibleBooking() {
                BoxOffice o = office();
                o.markAccessible("A1", "A2");
                expect(IllegalArgumentException.class, () -> o.reserve("ana", "A1"), "plain reserve refuses");
                expect(IllegalArgumentException.class, () -> o.reserve("ana", "B1", "A2"), "mixed plain reserve refuses");
                check(o.isFree("A1") && o.isFree("B1"), "nothing changed");
                expect(IllegalArgumentException.class, () -> o.reserveAccessible("ana", "B1", "B2"), "needs an accessible seat");
                Booking b = o.reserveAccessible("ana", "A1", "B1");
                eq("R001", b.id(), "id");
                eq(list("A1", "B1"), b.seats(), "seats");
                eq(5000, b.priceCents(), "price");
                expect(IllegalStateException.class, () -> o.reserveAccessible("bob", "A1"), "taken");
                Booking c = o.reserveAccessible("cy", "A2");
                eq("R002", c.id(), "second");
                o.cancel("R001");
                eq("R003", o.reserveAccessible("dee", "A1", "B1").id(), "again after cancel");
                eq("R004", o.reserve("eve", "B5", "B6").id(), "ordinary seats are fine");
            }

            static void testOrdinaryBookingsUnaffected() {
                BoxOffice o = office();
                o.markAccessible("A1");
                eq("R001", o.reserve("ana", "B1", "B2").id(), "ordinary booking");
                check(o.isFree("A1"), "flag does not book");
            }
        ''',
    ))

    S.append(Slice(
        id="adjacent", title="Seats together", d=2,
        pitch=("Groups want to sit together and the box office spends minutes hunting for a free block.",
               "The desk wants the system to suggest seats next to each other."),
        reqs=(f"`BoxOffice.findBlock(int count)` returns `count` free seats that are side by side in one row (consecutive numbers), as a list in left-to-right order, or an empty list if there is no such block. Rows are scanned {'from the last row backwards (the back of the hall first)' if from_back else 'from row A onwards (the front first)'}, and inside a row from the left; the first block found is returned.",
              "`count` below 1 or above the number of seats in a row is an `IllegalArgumentException`. The call does not book anything."),
        code={
            "src/seatmap/BoxOffice.java::methods": f'''
                public List<String> findBlock(int count) {{
                    if (count < 1 || count > perRow) {{
                        throw new IllegalArgumentException("count must be between 1 and " + perRow);
                    }}
                    for (int i = 0; i < rows; i++) {{
                        int r = {'rows - 1 - i' if from_back else 'i'};
                        int run = 0;
                        for (int c = 0; c < perRow; c++) {{
                            run = taken.containsKey(seatId(r, c)) ? 0 : run + 1;
                            if (run == count) {{
                                List<String> out = new ArrayList<>();
                                for (int k = c - count + 1; k <= c; k++) {{
                                    out.add(seatId(r, k));
                                }}
                                return out;
                            }}
                        }}
                    }}
                    return new ArrayList<>();
                }}
            ''',
        },
        readme=f"## Seats together\n\n`findBlock(count)` returns the first run of `count` free adjacent seats in one row, scanning {'from the back row' if from_back else 'from row A'} and left to right; empty if none.\n",
        vtests='''
            static void testFindBlockBasic() {
                eq(2, office().findBlock(2).size(), "two seats");
            }
        ''',
        tests=fmt('''
            static void testFindBlock() {
                BoxOffice o = new BoxOffice(3, 6);
                String f = "__F__";
                String s = "B";
                String t = "__T__";
                eq(list(f + "1", f + "2", f + "3"), o.findBlock(3), "empty hall");
                o.reserve("ana", f + "2");
                eq(list(f + "3", f + "4", f + "5"), o.findBlock(3), "first run that fits");
                eq(list(f + "1"), o.findBlock(1), "single seat");
                eq(list(s + "1", s + "2", s + "3", s + "4", s + "5"), o.findBlock(5), "next row when no run fits");
                eq(list(s + "1", s + "2", s + "3", s + "4", s + "5", s + "6"), o.findBlock(6), "whole row");
                check(o.isFree(f + "3") && o.isFree(s + "1"), "searching books nothing");
                o.reserve("bob", s + "4");
                o.reserve("cy", t + "3");
                eq(list(f + "3", f + "4", f + "5", f + "6"), o.findBlock(4), "run at the end of the row");
                eq(new ArrayList<String>(), o.findBlock(6), "no complete row left");
                expect(IllegalArgumentException.class, () -> o.findBlock(0), "zero");
                expect(IllegalArgumentException.class, () -> o.findBlock(7), "wider than the hall");
            }
        ''', F="C" if from_back else "A", T="A" if from_back else "C"),
    ))

    S.append(Slice(
        id="pricing", title="Price rules", d=3,
        pitch=("Front rows should cost more than the back, and right now every seat has the same price.",
               "The theatre wants to price seats differently without a code change per show."),
        reqs=("A new public functional interface `seatmap.PriceRule` with the method `int priceCents(String seat)`, and a final utility class `seatmap.PriceRules` with two factories: `flat(int cents)` (same price for every seat) and `byRow(int... cents)` (row A costs `cents[0]`, row B `cents[1]`, and so on; rows beyond the list use the last value). A negative price, or `byRow` with no values, is an `IllegalArgumentException`.",
              "`BoxOffice.setPricing(PriceRule rule)` selects the rule (`null` is an `IllegalArgumentException`). The price of a new booking is the sum of the rule's price for each of its seats. The default rule is `flat(2500)`. Bookings made earlier keep their price."),
        files={
            "src/seatmap/PriceRule.java": dd('''
                package seatmap;

                /** Price of one seat in cents. */
                @FunctionalInterface
                public interface PriceRule {
                    int priceCents(String seat);
                }
            '''),
            "src/seatmap/PriceRules.java": dd('''
                package seatmap;

                /** Ready-made price rules. */
                public final class PriceRules {
                    private PriceRules() {
                    }

                    public static PriceRule flat(int cents) {
                        if (cents < 0) {
                            throw new IllegalArgumentException("negative price");
                        }
                        return seat -> cents;
                    }

                    public static PriceRule byRow(int... cents) {
                        if (cents.length == 0) {
                            throw new IllegalArgumentException("at least one price is required");
                        }
                        int[] copy = cents.clone();
                        for (int c : copy) {
                            if (c < 0) {
                                throw new IllegalArgumentException("negative price");
                            }
                        }
                        return seat -> copy[Math.min(seat.charAt(0) - 'A', copy.length - 1)];
                    }
                }
            '''),
        },
        code={
            "src/seatmap/BoxOffice.java::fields": "private PriceRule pricing = PriceRules.flat(2500);",
            "src/seatmap/BoxOffice.java::price_call": '''
                int price = 0;
                for (String s : want) {
                    price += pricing.priceCents(s);
                }
            ''',
            "src/seatmap/BoxOffice.java::methods": '''
                public void setPricing(PriceRule rule) {
                    if (rule == null) {
                        throw new IllegalArgumentException("rule is required");
                    }
                    this.pricing = rule;
                }
            ''',
        },
        readme=dd('''
            ## Price rules

            `PriceRule` (`int priceCents(String seat)`) and `PriceRules.flat(cents)` / `PriceRules.byRow(cents...)`;
            `BoxOffice.setPricing(rule)` chooses the rule for later bookings (default `flat(2500)`).
        '''),
        vtests='''
            static void testDefaultPricing() {
                eq(2500, office().reserve("ana", "A1").priceCents(), "default price");
            }
        ''',
        tests='''
            static void testPriceRules() {
                BoxOffice o = office();
                Booking early = o.reserve("ana", "A6");
                o.setPricing(PriceRules.byRow(4000, 3000, 2000));
                eq(9000, o.reserve("bob", "A1", "B2", "D3").priceCents(), "by row, last value repeats");
                eq(2500, early.priceCents(), "earlier booking keeps its price");
                o.setPricing(PriceRules.flat(700));
                eq(1400, o.reserve("cy", "C1", "C2").priceCents(), "flat");
                o.setPricing(seat -> seat.endsWith("1") ? 100 : 200);
                eq(300, o.reserve("dee", "B1", "B3").priceCents(), "custom rule");
                o.setPricing(PriceRules.byRow(1234));
                eq(2468, o.reserve("eve", "C5", "D5").priceCents(), "single value for every row");
            }

            static void testPriceRuleErrors() {
                expect(IllegalArgumentException.class, () -> PriceRules.flat(-1), "negative flat");
                expect(IllegalArgumentException.class, () -> PriceRules.byRow(), "empty byRow");
                expect(IllegalArgumentException.class, () -> PriceRules.byRow(100, -5), "negative byRow");
                expect(IllegalArgumentException.class, () -> office().setPricing(null), "null rule");
                eq(0, PriceRules.flat(0).priceCents("A1"), "free is allowed");
                BoxOffice o = office();
                o.setPricing(PriceRules.flat(10));
                eq(10, o.reserve("ana", "A1").priceCents(), "applies");
            }
        ''',
    ))

    S.append(Slice(
        id="idempotent", title="Safe retries", d=2,
        pitch=("The ticket kiosk retries a request when the network drops and customers end up with two bookings.",
               "A retried reservation must not take the seats twice."),
        reqs=("`BoxOffice.reserveOnce(String requestId, String holder, String... seats)` is `reserve` with an idempotency key. The first call with a key behaves exactly like `reserve` and remembers the key; a later call with the same key returns the very same `Booking` object and changes nothing, whatever its other arguments are (also after that booking has been cancelled).",
              "A call that fails is not remembered, so the key can be retried. A `null` or blank key is an `IllegalArgumentException`."),
        code={
            "src/seatmap/BoxOffice.java::fields": "private final Map<String, Booking> requests = new HashMap<>();",
            "src/seatmap/BoxOffice.java::methods": '''
                public Booking reserveOnce(String requestId, String holder, String... seats) {
                    if (requestId == null || requestId.isBlank()) {
                        throw new IllegalArgumentException("request id is required");
                    }
                    Booking known = requests.get(requestId);
                    if (known != null) {
                        return known;
                    }
                    Booking b = reserve(holder, seats);
                    requests.put(requestId, b);
                    return b;
                }
            ''',
        },
        readme=dd('''
            ## Safe retries

            `reserveOnce(requestId, holder, seats...)` returns the original `Booking` for a repeated key and changes nothing;
            failures are not remembered; a blank key is an `IllegalArgumentException`.
        '''),
        vtests='''
            static void testReserveOnceBasic() {
                BoxOffice o = office();
                Booking a = o.reserveOnce("k", "ana", "A1");
                check(a == o.reserveOnce("k", "ana", "A1"), "same booking");
            }
        ''',
        tests='''
            static void testReserveOnce() {
                BoxOffice o = office();
                Booking a = o.reserveOnce("req-1", "ana", "A1", "A2");
                Booking again = o.reserveOnce("req-1", "bob", "C1");
                check(a == again, "same booking object");
                eq(1, o.bookings().size(), "one booking");
                check(o.isFree("C1"), "replay changes nothing");
                o.cancel(a.id());
                check(o.reserveOnce("req-1", "ana", "A1") == a, "replay after cancel");
                check(o.isFree("A1") && o.bookings().isEmpty(), "replay after cancel books nothing");
            }

            static void testReserveOnceFailures() {
                BoxOffice o = office();
                o.reserve("zed", "B1");
                expect(IllegalStateException.class, () -> o.reserveOnce("req-2", "ana", "B1"), "taken seat");
                o.cancel("R001");
                Booking b = o.reserveOnce("req-2", "ana", "B1");
                eq("R002", b.id(), "failure was not remembered");
                expect(IllegalArgumentException.class, () -> o.reserveOnce(null, "ana", "C1"), "null key");
                expect(IllegalArgumentException.class, () -> o.reserveOnce("  ", "ana", "C1"), "blank key");
                expect(IllegalArgumentException.class, () -> o.reserveOnce("req-3", "", "C1"), "bad holder");
                eq("R003", o.reserveOnce("req-3", "ana", "C1").id(), "bad calls do not use ids");
            }
        ''',
    ))

    S.append(Slice(
        id="hold", title="Timed seat holds", d=4,
        pitch=("People pick seats on the website and then take ten minutes to pay; meanwhile somebody else buys them.",
               "Seats need to be held for a short time while a customer checks out."),
        reqs=(f"`hold(holder, seats...)` holds seats without booking them and returns a `Hold` (new public class) with `id()` (`H001`, `H002`, ... from its own counter), `holder()`, `seats()` and `expiresAt()` (a `long`). It validates like `reserve` (same exceptions and limits), and a held seat counts as taken: `isFree` is false, `freeSeats()` leaves it out, and `reserve` or `hold` of it throw `IllegalStateException`.",
              f"Time is a counter that starts at 0 and only moves with `tick()`. A hold made at time `t` expires at `t + {ticks}` (`BoxOffice.HOLD_TICKS` is that public `int` constant): on the tick that brings the clock to `expiresAt()` its seats become free again.",
              "`confirm(holdId)` turns a hold into a booking by calling `reserve` for the same holder and seats (so the booking gets the next `R` id and the price in force at that moment) and returns it; the hold is gone. `release(holdId)` drops a hold and frees its seats. Both throw `NoSuchElementException` for an unknown or expired hold. `activeHolds()` counts the holds that have not expired, been confirmed or been released."),
        files={
            "src/seatmap/Hold.java": dd('''
                package seatmap;

                import java.util.Collections;
                import java.util.List;

                /** A temporary claim on seats. */
                public final class Hold {
                    private final String id;
                    private final String holder;
                    private final List<String> seats;
                    private final long expiresAt;

                    Hold(String id, String holder, List<String> seats, long expiresAt) {
                        this.id = id;
                        this.holder = holder;
                        this.seats = Collections.unmodifiableList(seats);
                        this.expiresAt = expiresAt;
                    }

                    public String id() {
                        return id;
                    }

                    public String holder() {
                        return holder;
                    }

                    public List<String> seats() {
                        return seats;
                    }

                    public long expiresAt() {
                        return expiresAt;
                    }
                }
            '''),
        },
        code={
            "src/seatmap/BoxOffice.java::fields": f"public static final int HOLD_TICKS = {ticks};\nprivate final Map<String, Hold> holds = new LinkedHashMap<>();\nprivate int nextHold = 1;\nprivate long clock = 0;",
            "src/seatmap/BoxOffice.java::methods": '''
                public Hold hold(String holder, String... seats) {
                    Set<String> want = checked(holder, seats);
                    String id = String.format("H%03d", nextHold++);
                    Hold h = new Hold(id, holder, new ArrayList<>(want), clock + HOLD_TICKS);
                    holds.put(id, h);
                    for (String s : want) {
                        taken.put(s, id);
                    }
                    @@slot on_hold
                    return h;
                }

                public Booking confirm(String holdId) {
                    Hold h = holds.get(holdId);
                    if (h == null) {
                        throw new NoSuchElementException("no such hold: " + holdId);
                    }
                    holds.remove(holdId);
                    for (String s : h.seats()) {
                        taken.remove(s);
                    }
                    Booking b = reserve(h.holder(), h.seats().toArray(new String[0]));
                    @@slot on_confirm
                    return b;
                }

                public void release(String holdId) {
                    Hold h = holds.remove(holdId);
                    if (h == null) {
                        throw new NoSuchElementException("no such hold: " + holdId);
                    }
                    for (String s : h.seats()) {
                        taken.remove(s);
                    }
                    @@slot on_release
                }

                public void tick() {
                    clock++;
                    for (Hold h : new ArrayList<>(holds.values())) {
                        if (h.expiresAt() <= clock) {
                            holds.remove(h.id());
                            for (String s : h.seats()) {
                                taken.remove(s);
                            }
                            @@slot on_expire
                        }
                    }
                }

                public int activeHolds() {
                    return holds.size();
                }
            ''',
        },
        readme=fmt(dd('''
            ## Timed holds

            `hold(holder, seats...)` returns a `Hold` (`id()`, `holder()`, `seats()`, `expiresAt()`) and makes the seats count as
            taken. The clock only moves with `tick()`; a hold made at time `t` expires at `t + HOLD_TICKS` (__T__).
            `confirm(holdId)` books the held seats via `reserve`; `release(holdId)` frees them; `activeHolds()` counts live holds.
        '''), T=ticks),
        vtests='''
            static void testHoldBasic() {
                BoxOffice o = office();
                Hold h = o.hold("ana", "A1");
                check(!o.isFree("A1") && h.id().startsWith("H"), "held");
            }
        ''',
        tests=fmt('''
            static void testHoldBlocksSeats() {
                BoxOffice o = office();
                Hold h = o.hold("ana", "A1", "A2");
                eq("H001", h.id(), "id");
                eq("ana", h.holder(), "holder");
                eq(list("A1", "A2"), h.seats(), "seats");
                eq((long) __T__, h.expiresAt(), "expiry");
                eq(__T__, BoxOffice.HOLD_TICKS, "constant");
                check(!o.isFree("A1"), "held seat is not free");
                eq(22, o.freeSeats().size(), "free count");
                expect(IllegalStateException.class, () -> o.reserve("bob", "A2"), "reserve held seat");
                expect(IllegalStateException.class, () -> o.hold("bob", "A2", "A3"), "hold held seat");
                check(o.isFree("A3"), "failed hold changed nothing");
                eq(1, o.activeHolds(), "active");
                o.release("H001");
                check(o.isFree("A1") && o.isFree("A2"), "released");
                eq(0, o.activeHolds(), "none left");
                expect(java.util.NoSuchElementException.class, () -> o.release("H001"), "release twice");
                eq("H002", o.hold("cy", "A1").id(), "ids are not reused");
            }

            static void testHoldValidation() {
                BoxOffice o = office();
                expect(IllegalArgumentException.class, () -> o.hold(" ", "A1"), "blank holder");
                expect(IllegalArgumentException.class, () -> o.hold("ana"), "no seats");
                expect(IllegalArgumentException.class, () -> o.hold("ana", "Z1"), "unknown seat");
                expect(IllegalArgumentException.class, () -> o.hold("ana", "A1", "A1"), "duplicate seat");
                eq(0, o.activeHolds(), "nothing held");
                eq("H001", o.hold("ana", "A1").id(), "failed calls use no ids");
            }

            static void testConfirmHold() {
                BoxOffice o = office();
                o.reserve("zed", "D1");
                Hold h = o.hold("ana", "B1", "B2");
                Booking b = o.confirm(h.id());
                eq("R002", b.id(), "next booking id");
                eq("ana", b.holder(), "holder");
                eq(list("B1", "B2"), b.seats(), "seats");
                eq(0, o.activeHolds(), "hold is gone");
                expect(java.util.NoSuchElementException.class, () -> o.confirm("H001"), "confirm twice");
                expect(java.util.NoSuchElementException.class, () -> o.confirm("H404"), "unknown hold");
                o.cancel("R002");
                check(o.isFree("B1") && o.isFree("B2"), "cancel frees the seats");
            }

            static void testHoldsExpire() {
                BoxOffice o = office();
                Hold h = o.hold("ana", "C1");
                for (int i = 0; i < __T__ - 1; i++) {
                    o.tick();
                }
                check(!o.isFree("C1"), "still held");
                eq(1, o.activeHolds(), "still active");
                o.tick();
                check(o.isFree("C1"), "expired");
                eq(0, o.activeHolds(), "none active");
                expect(java.util.NoSuchElementException.class, () -> o.confirm(h.id()), "expired hold cannot be confirmed");
                Hold a = o.hold("ana", "D1");
                o.tick();
                Hold b = o.hold("bob", "D2");
                eq(a.expiresAt() + 1, b.expiresAt(), "later hold expires later");
                for (int i = 0; i < __T__ - 1; i++) {
                    o.tick();
                }
                check(o.isFree("D1") && !o.isFree("D2"), "first expired, second not yet");
                o.tick();
                check(o.isFree("D2"), "second expired");
            }
        ''', T=ticks),
        cross={
            "booking-limit": {"tests": '''
                static void testHoldObeysSeatLimit() {
                    BoxOffice o = new BoxOffice(5, 10);
                    String[] seats = new String[BoxOffice.MAX_SEATS + 1];
                    for (int i = 0; i < seats.length; i++) {
                        seats[i] = "A" + (i + 1);
                    }
                    expect(IllegalArgumentException.class, () -> o.hold("ana", seats), "hold over the limit");
                    eq(0, o.activeHolds(), "nothing held");
                }
            '''},
            "accessible": {
                "reqs": ("`hold` refuses accessible seats exactly like plain `reserve` does (`IllegalArgumentException`).",),
                "tests": '''
                    static void testHoldRefusesAccessibleSeats() {
                        BoxOffice o = office();
                        o.markAccessible("A1");
                        expect(IllegalArgumentException.class, () -> o.hold("ana", "A1"), "accessible seat");
                        check(o.isFree("A1"), "still free");
                        eq("H001", o.hold("ana", "B1").id(), "ordinary seat");
                    }
                '''},
            "pricing": {
                "reqs": ("A confirmed booking costs what the pricing rule says at the moment of `confirm`, not at the moment of the hold.",),
                "tests": '''
                    static void testConfirmUsesCurrentPricing() {
                        BoxOffice o = office();
                        Hold h = o.hold("ana", "A1", "A2");
                        o.setPricing(PriceRules.flat(1000));
                        eq(2000, o.confirm(h.id()).priceCents(), "price at confirm time");
                    }
                '''},
            "seat-map": {
                "reqs": ("Held seats are drawn like taken seats in `render()`.",),
                "tests": fmt('''
                    static void testHeldSeatsAreDrawnTaken() {
                        BoxOffice o = new BoxOffice(1, 4);
                        o.hold("ana", "A2");
                        eq("A __F____T____F____F__\\n", o.render(), "map with a hold");
                        o.release("H001");
                        eq("A __F____F____F____F__\\n", o.render(), "map after release");
                    }
                ''', F=free_ch, T=taken_ch)},
        },
    ))

    S.append(Slice(
        id="audit", title="Audit log", d=3,
        pitch=("When the stalls and the ledger disagree nobody can tell who booked or cancelled what.",
               "The box office manager wants a record of every booking and cancellation."),
        reqs=("`BoxOffice.auditLog()` returns a copy of the log, oldest entry first, as a list of strings. Each successful `reserve` appends `reserve ID HOLDER SEATS` (the seats in booking order, joined with a comma and no spaces, for example `reserve R001 ana A1,A2`); each successful `cancel` appends `cancel ID`. Calls that throw append nothing.",
              "Changing the returned list does not change the log."),
        code={
            "src/seatmap/BoxOffice.java::fields": "private final List<String> audit = new ArrayList<>();",
            "src/seatmap/BoxOffice.java::on_reserve": 'audit.add("reserve " + id + " " + holder + " " + String.join(",", b.seats()));',
            "src/seatmap/BoxOffice.java::on_cancel": 'audit.add("cancel " + bookingId);',
            "src/seatmap/BoxOffice.java::methods": '''
                public List<String> auditLog() {
                    return new ArrayList<>(audit);
                }
            ''',
        },
        readme=dd('''
            ## Audit log

            `auditLog()` returns a copy of the log: `reserve ID HOLDER SEATS` (seats comma-joined) for each successful
            `reserve`, `cancel ID` for each successful `cancel`.
        '''),
        vtests='''
            static void testAuditBasic() {
                BoxOffice o = office();
                o.reserve("ana", "A1");
                eq(1, o.auditLog().size(), "one entry");
            }
        ''',
        tests='''
            static void testAuditLog() {
                BoxOffice o = office();
                o.reserve("ana", "A1", "A2");
                o.reserve("bob", "C3");
                expect(IllegalStateException.class, () -> o.reserve("cy", "A1"), "taken seat");
                o.cancel("R001");
                expect(java.util.NoSuchElementException.class, () -> o.cancel("R404"), "unknown booking");
                eq(list("reserve R001 ana A1,A2", "reserve R002 bob C3", "cancel R001"), o.auditLog(), "log");
                o.auditLog().add("tampered");
                eq(3, o.auditLog().size(), "copy");
            }
        ''',
        cross={
            "idempotent": {"tests": '''
                static void testReplayIsNotLogged() {
                    BoxOffice o = office();
                    o.reserveOnce("k", "ana", "A1");
                    o.reserveOnce("k", "ana", "A1");
                    eq(list("reserve R001 ana A1"), o.auditLog(), "one entry");
                }
            '''},
            "hold": {
                "reqs": ("Holds are logged too: `hold HOLDID HOLDER SEATS` when a hold is made, `release HOLDID` when it is released and `expire HOLDID` when it expires (in hold order within one tick). Confirming a hold appends the normal `reserve ...` entry (produced by the booking) followed by `confirm HOLDID BOOKINGID`.",),
                "code": {
                    "src/seatmap/BoxOffice.java::on_hold": 'audit.add("hold " + id + " " + holder + " " + String.join(",", h.seats()));',
                    "src/seatmap/BoxOffice.java::on_confirm": 'audit.add("confirm " + holdId + " " + b.id());',
                    "src/seatmap/BoxOffice.java::on_release": 'audit.add("release " + holdId);',
                    "src/seatmap/BoxOffice.java::on_expire": 'audit.add("expire " + h.id());',
                },
                "tests": '''
                    static void testHoldsAreLogged() {
                        BoxOffice o = office();
                        Hold a = o.hold("ana", "A1", "A2");
                        Hold b = o.hold("bob", "B1");
                        Hold c = o.hold("cy", "C1");
                        o.confirm(a.id());
                        o.release(c.id());
                        for (int i = 0; i < BoxOffice.HOLD_TICKS; i++) {
                            o.tick();
                        }
                        eq(list("hold H001 ana A1,A2", "hold H002 bob B1", "hold H003 cy C1", "reserve R001 ana A1,A2",
                                "confirm H001 R001", "release H003", "expire H002"), o.auditLog(), "log with holds");
                    }
                '''},
        },
    ))
    return S


APP = App(
    name="seatmap", lang="java", title="the box office seat library", role="a box office clerk", key="SEAT",
    base={
        "README.md": README + "\n@@blocks features\n",
        "src/seatmap/BoxOffice.java": BOX,
        "src/seatmap/Booking.java": BOOKING,
        ".gitignore": "build/\n",
    },
    visible={"test/TestMain.java": TEST_HEAD.replace("@@blocks tests", VISIBLE_BASE + "\n    @@blocks tests")},
    hidden={"test/TestMain.java": TEST_HEAD.replace("@@blocks tests", HIDDEN_BASE + "\n    @@blocks tests")},
)

register_app("feature-java-seatmap", APP, make_slices, n=16, summary="box office seats: limits, maps, access seats, blocks, pricing, holds, retries, audit")
