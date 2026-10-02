"""Cinema seat holds, group seating and pricing (java): bugs injected into a small booking engine."""
from fx import Lib, dd
from generators.fix._lang2 import JAVA_CHECK, java_test_main, register_libs

README = dd(r'''
    # seatbook

    The seat engine of a small cinema's booking desk. Plain Java 17, no dependencies; sources in `src/venue/`.

    A hall has `rows` rows (`A` is the front row) of `perRow` seats numbered from 1. A seat label is the row letter
    followed by the seat number, `C12` for row `C`, seat 12. Some seats are permanently *blocked* (aisle chairs,
    broken seats).

    ## `SeatMap` (`SeatMap.java`)

    * `new SeatMap(rows, perRow, String... blocked)`: `rows` must be `1..26` and `perRow` `1..99`, otherwise
      `IllegalArgumentException`. A blocked label that does not parse or lies outside the hall is also an
      `IllegalArgumentException`.
    * `rows()`, `perRow()`, `isBlocked(row, seat)` (zero-based row, one-based seat).
    * `SeatMap.label(row, seat)`: `label(2, 12)` is `"C12"`.
    * `SeatMap.parse(label)` returns `{zeroBasedRow, seat}`: an upper-case letter followed by one or two digits, with no
      leading zero (`A0`, `A05`, `a1`, `A`, `A100`, `1A` are all `IllegalArgumentException`; so is `null`).

    ## `SeatFinder` (`SeatFinder.java`)

    * `sweetRow(rows)`: the best row, `min(rows - 1, rows * 3 / 5)` with integer division.
    * `findBlock(map, taken, size)` returns the labels of the best block of `size` neighbouring free seats in one row,
      left to right, or an empty list when no row has such a block. A seat is free when it is neither blocked nor in
      the set `taken`. `size` must be `1..8`, otherwise `IllegalArgumentException`.

    Choosing the block, in this order of importance:

    1. Blocks that do not leave a *lonely seat* come first. A block leaves a lonely seat when the unbroken run of
       free seats directly to its left, or directly to its right, is exactly one seat long (a wall, a blocked seat or a
       taken seat ends a run). If every possible block leaves a lonely seat, they all compete as equals.
    2. The row closest to `sweetRow` (distance `|row - sweetRow|`).
    3. The row nearer the screen (smaller row index).
    4. The block whose centre is closest to the centre of the row: the distance is
       `|2 * start + size - 1 - (perRow + 1)|` with `start` the first seat number.
    5. The block further left (smaller `start`).

    ## `Reservations` (`Reservations.java`)

    Holds and bookings over a `SeatMap`. Time is a number of minutes supplied by the caller.

    * `new Reservations(map, holdMinutes)`: `holdMinutes >= 1`, else `IllegalArgumentException`.
    * `hold(size, now)` returns an `Optional<Hold>`: the best block (as `SeatFinder.findBlock`, avoiding seats that are
      held or booked) is held until `now + holdMinutes`. `Hold` has `id`, `seats` and `expiresAt`. Hold ids are `H1`, `H2`,
      ... numbered in the order holds were *made successfully*. Without room the result is empty and no id is used up.
    * A hold is active while `now < expiresAt`; at `now == expiresAt` it is gone and its seats are free again.
    * `confirm(holdId, now)` turns an active hold into a booking and returns its seats. An unknown, released, already
      confirmed or expired hold is an `IllegalStateException`.
    * `release(holdId, now)` drops an active hold and returns `true`; `false` if there was none (also when expired).
    * `booked()` lists every booked seat in row order, then seat number (`A2` before `A10`).
    * `taken(now)` is the set of seats that are booked or under an active hold.
    * `freeCount(now)` is the number of seats that are not blocked and not taken.

    ## `Pricing` (`Pricing.java`)

    Prices are `int` cents. `roundDiv(num, den)` is `num / den` rounded half up (for `num >= 0`, `den > 0`).

    * `seatPrice(row, rows, baseCents)`: let `pos = row * 100 / rows` (integer division). Rows with `pos < 20` cost 80%
      of the base price, rows with `40 <= pos < 80` cost 125%, all others the base price; percentages are rounded half up.
    * `groupTotal(seats, rows, baseCents)`: the sum of the seat prices of the labels in `seats`; a group of 6 or more seats
      gets 10% off the sum (the discount is rounded half up).
''')

SEATMAP = dd(r'''
    package venue;

    import java.util.HashSet;
    import java.util.Set;

    /** The seating plan of a hall: rows A.., seats numbered from 1, some seats permanently blocked. */
    public final class SeatMap {
        private final int rows;
        private final int perRow;
        private final Set<String> blocked = new HashSet<>();

        public SeatMap(int rows, int perRow, String... blockedSeats) {
            if (rows < 1 || rows > 26 || perRow < 1 || perRow > 99) {
                throw new IllegalArgumentException("hall must have 1..26 rows and 1..99 seats per row");
            }
            this.rows = rows;
            this.perRow = perRow;
            for (String label : blockedSeats) {
                int[] at = parse(label);
                if (at[0] >= rows || at[1] > perRow) {
                    throw new IllegalArgumentException("no such seat: " + label);
                }
                blocked.add(label);
            }
        }

        public int rows() {
            return rows;
        }

        public int perRow() {
            return perRow;
        }

        public boolean isBlocked(int row, int seat) {
            return blocked.contains(label(row, seat));
        }

        public static String label(int row, int seat) {
            return "" + (char) ('A' + row) + seat;
        }

        /** "C12" gives {2, 12}: zero-based row, one-based seat. */
        public static int[] parse(String label) {
            if (label == null || label.length() < 2 || label.length() > 3) {
                throw new IllegalArgumentException("bad seat label: " + label);
            }
            char letter = label.charAt(0);
            String digits = label.substring(1);
            if (letter < 'A' || letter > 'Z' || digits.charAt(0) == '0') {
                throw new IllegalArgumentException("bad seat label: " + label);
            }
            for (int i = 0; i < digits.length(); i++) {
                char c = digits.charAt(i);
                if (c < '0' || c > '9') {
                    throw new IllegalArgumentException("bad seat label: " + label);
                }
            }
            return new int[] {letter - 'A', Integer.parseInt(digits)};
        }
    }
''')

FINDER = dd(r'''
    package venue;

    import java.util.ArrayList;
    import java.util.List;
    import java.util.Set;

    /** Picks the best block of neighbouring seats for a group. */
    public final class SeatFinder {
        private SeatFinder() {}

        public static int sweetRow(int rows) {
            return Math.min(rows - 1, rows * 3 / 5);
        }

        /** Index 0 and perRow + 1 are walls; index s is seat s. */
        private static boolean[] freeSeats(SeatMap map, Set<String> taken, int row) {
            boolean[] free = new boolean[map.perRow() + 2];
            for (int s = 1; s <= map.perRow(); s++) {
                free[s] = !map.isBlocked(row, s) && !taken.contains(SeatMap.label(row, s));
            }
            return free;
        }

        /** Free seats in an unbroken run that ends at seat {@code end}, counting leftwards. */
        private static int runLeft(boolean[] free, int end) {
            int n = 0;
            for (int s = end; s >= 1 && free[s]; s--) {
                n++;
            }
            return n;
        }

        /** Free seats in an unbroken run that starts at seat {@code begin}, counting rightwards. */
        private static int runRight(boolean[] free, int begin, int perRow) {
            int n = 0;
            for (int s = begin; s <= perRow && free[s]; s++) {
                n++;
            }
            return n;
        }

        private static boolean less(int[] a, int[] b) {
            for (int i = 0; i < a.length; i++) {
                if (a[i] != b[i]) {
                    return a[i] < b[i];
                }
            }
            return false;
        }

        public static List<String> findBlock(SeatMap map, Set<String> taken, int size) {
            if (size < 1 || size > 8) {
                throw new IllegalArgumentException("group size must be 1..8");
            }
            int sweet = sweetRow(map.rows());
            int[] bestKey = null;
            int bestRow = -1;
            int bestStart = -1;
            for (int row = 0; row < map.rows(); row++) {
                boolean[] free = freeSeats(map, taken, row);
                for (int start = 1; start + size - 1 <= map.perRow(); start++) {
                    if (runRight(free, start, map.perRow()) < size) {
                        continue;
                    }
                    boolean lonely = runLeft(free, start - 1) == 1 || runRight(free, start + size, map.perRow()) == 1;
                    int[] key = {
                        lonely ? 1 : 0,
                        Math.abs(row - sweet),
                        row,
                        Math.abs(2 * start + size - 1 - (map.perRow() + 1)),
                        start,
                    };
                    if (bestKey == null || less(key, bestKey)) {
                        bestKey = key;
                        bestRow = row;
                        bestStart = start;
                    }
                }
            }
            List<String> seats = new ArrayList<>();
            if (bestKey != null) {
                for (int s = bestStart; s < bestStart + size; s++) {
                    seats.add(SeatMap.label(bestRow, s));
                }
            }
            return seats;
        }
    }
''')

RESERVATIONS = dd(r'''
    package venue;

    import java.util.ArrayList;
    import java.util.HashSet;
    import java.util.LinkedHashMap;
    import java.util.List;
    import java.util.Map;
    import java.util.Optional;
    import java.util.Set;
    import java.util.TreeSet;

    /** Holds (temporary, expiring) and bookings (permanent) over one hall. */
    public final class Reservations {
        public static final class Hold {
            public final String id;
            public final List<String> seats;
            public final int expiresAt;

            Hold(String id, List<String> seats, int expiresAt) {
                this.id = id;
                this.seats = seats;
                this.expiresAt = expiresAt;
            }
        }

        private final SeatMap map;
        private final int holdMinutes;
        private final Map<String, Hold> holds = new LinkedHashMap<>();
        private final Set<String> booked = new HashSet<>();
        private int counter = 0;

        public Reservations(SeatMap map, int holdMinutes) {
            if (holdMinutes < 1) {
                throw new IllegalArgumentException("holdMinutes must be at least 1");
            }
            this.map = map;
            this.holdMinutes = holdMinutes;
        }

        private void expire(int now) {
            holds.values().removeIf(h -> h.expiresAt <= now);
        }

        public Set<String> taken(int now) {
            expire(now);
            Set<String> all = new HashSet<>(booked);
            for (Hold h : holds.values()) {
                all.addAll(h.seats);
            }
            return all;
        }

        public Optional<Hold> hold(int size, int now) {
            List<String> seats = SeatFinder.findBlock(map, taken(now), size);
            if (seats.isEmpty()) {
                return Optional.empty();
            }
            counter++;
            Hold h = new Hold("H" + counter, seats, now + holdMinutes);
            holds.put(h.id, h);
            return Optional.of(h);
        }

        public List<String> confirm(String holdId, int now) {
            expire(now);
            Hold h = holds.remove(holdId);
            if (h == null) {
                throw new IllegalStateException("no active hold " + holdId);
            }
            booked.addAll(h.seats);
            return h.seats;
        }

        public boolean release(String holdId, int now) {
            expire(now);
            return holds.remove(holdId) != null;
        }

        public List<String> booked() {
            TreeSet<String> sorted = new TreeSet<>((a, b) -> {
                int[] x = SeatMap.parse(a);
                int[] y = SeatMap.parse(b);
                return x[0] != y[0] ? Integer.compare(x[0], y[0]) : Integer.compare(x[1], y[1]);
            });
            sorted.addAll(booked);
            return new ArrayList<>(sorted);
        }

        public int freeCount(int now) {
            Set<String> gone = taken(now);
            int free = 0;
            for (int r = 0; r < map.rows(); r++) {
                for (int s = 1; s <= map.perRow(); s++) {
                    if (!map.isBlocked(r, s) && !gone.contains(SeatMap.label(r, s))) {
                        free++;
                    }
                }
            }
            return free;
        }
    }
''')

PRICING = dd(r'''
    package venue;

    import java.util.List;

    /** Seat prices by zone and the group discount. */
    public final class Pricing {
        private Pricing() {}

        /** num / den rounded half up, for num >= 0 and den > 0. */
        public static int roundDiv(long num, long den) {
            return (int) ((2 * num + den) / (2 * den));
        }

        public static int seatPrice(int row, int rows, int baseCents) {
            int pos = row * 100 / rows;
            if (pos < 20) {
                return roundDiv((long) baseCents * 80, 100);
            }
            if (pos >= 40 && pos < 80) {
                return roundDiv((long) baseCents * 125, 100);
            }
            return baseCents;
        }

        public static int groupTotal(List<String> seats, int rows, int baseCents) {
            int sum = 0;
            for (String label : seats) {
                sum += seatPrice(SeatMap.parse(label)[0], rows, baseCents);
            }
            return seats.size() >= 6 ? sum - roundDiv(sum, 10) : sum;
        }
    }
''')

BASIC = dd(r'''
    import java.util.HashSet;
    import java.util.List;
    import venue.SeatFinder;
    import venue.SeatMap;

    public class BasicTests {
        public static void run() {
            Check.test("label", () -> Check.eq("C12", SeatMap.label(2, 12)));
            Check.test("empty hall, pair goes to the middle of the sweet row", () -> {
                SeatMap map = new SeatMap(5, 10);
                Check.eq(List.of("D5", "D6"), SeatFinder.findBlock(map, new HashSet<>(), 2));
            });
        }
    }
''')

HIDDEN_MAIN = java_test_main("BasicTests", "FullTests")
VISIBLE_MAIN = java_test_main("BasicTests")

FULL = dd(r'''
    import java.util.HashSet;
    import java.util.List;
    import java.util.Optional;
    import java.util.Set;
    import venue.Pricing;
    import venue.Reservations;
    import venue.SeatFinder;
    import venue.SeatMap;

    public class FullTests {
        static Set<String> set(String... labels) {
            return new HashSet<>(List.of(labels));
        }

        static List<String> find(SeatMap map, int size, String... taken) {
            return SeatFinder.findBlock(map, set(taken), size);
        }

        static Set<String> fullRows(int width, char... letters) {
            Set<String> out = new HashSet<>();
            for (char letter : letters) {
                for (int s = 1; s <= width; s++) {
                    out.add("" + letter + s);
                }
            }
            return out;
        }

        public static void run() {
            Check.test("label and parse", () -> {
                Check.eq("A1", SeatMap.label(0, 1));
                Check.eq("C12", SeatMap.label(2, 12));
                Check.eq("Z99", SeatMap.label(25, 99));
                Check.eq(new int[] {0, 1}, SeatMap.parse("A1"));
                Check.eq(new int[] {2, 12}, SeatMap.parse("C12"));
                Check.eq(new int[] {25, 99}, SeatMap.parse("Z99"));
                Check.eq(new int[] {1, 10}, SeatMap.parse("B10"));
            });

            Check.test("parse rejects malformed labels", () -> {
                for (String bad : new String[] {"A0", "A05", "a1", "A", "A100", "1A", "", "AB", "A-1", "A1x", "A 1", "AA1", "A1.", "[1"}) {
                    Check.raises(IllegalArgumentException.class, () -> SeatMap.parse(bad));
                }
                Check.raises(IllegalArgumentException.class, () -> SeatMap.parse(null));
            });

            Check.test("hall size limits", () -> {
                Check.raises(IllegalArgumentException.class, () -> new SeatMap(0, 10));
                Check.raises(IllegalArgumentException.class, () -> new SeatMap(27, 10));
                Check.raises(IllegalArgumentException.class, () -> new SeatMap(5, 0));
                Check.raises(IllegalArgumentException.class, () -> new SeatMap(5, 100));
                new SeatMap(1, 1);
                new SeatMap(26, 99);
            });

            Check.test("blocked seats", () -> {
                SeatMap map = new SeatMap(3, 5, "A1", "C5");
                Check.eq(3, map.rows());
                Check.eq(5, map.perRow());
                Check.yes(map.isBlocked(0, 1), "A1 blocked");
                Check.yes(map.isBlocked(2, 5), "C5 blocked");
                Check.yes(!map.isBlocked(0, 2), "A2 free");
                Check.yes(!map.isBlocked(1, 1), "B1 free");
                Check.yes(!map.isBlocked(2, 4), "C4 free");
                Check.raises(IllegalArgumentException.class, () -> new SeatMap(3, 5, "D1"));
                Check.raises(IllegalArgumentException.class, () -> new SeatMap(3, 5, "A6"));
                Check.raises(IllegalArgumentException.class, () -> new SeatMap(3, 5, "nonsense"));
                new SeatMap(3, 5, "C5");
            });

            Check.test("sweet row", () -> {
                Check.eq(0, SeatFinder.sweetRow(1));
                Check.eq(1, SeatFinder.sweetRow(2));
                Check.eq(1, SeatFinder.sweetRow(3));
                Check.eq(2, SeatFinder.sweetRow(4));
                Check.eq(3, SeatFinder.sweetRow(5));
                Check.eq(6, SeatFinder.sweetRow(10));
                Check.eq(15, SeatFinder.sweetRow(26));
            });

            Check.test("empty hall: groups sit in the middle of the sweet row", () -> {
                SeatMap map = new SeatMap(5, 10);
                Check.eq(List.of("D5"), find(map, 1));
                Check.eq(List.of("D5", "D6"), find(map, 2));
                Check.eq(List.of("D4", "D5", "D6"), find(map, 3));
                Check.eq(List.of("D4", "D5", "D6", "D7"), find(map, 4));
                Check.eq(List.of("D3", "D4", "D5", "D6", "D7"), find(map, 5));
                Check.eq(List.of("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"), find(map, 8));
            });

            Check.test("odd row width", () -> {
                SeatMap map = new SeatMap(1, 9);
                Check.eq(List.of("A5"), find(map, 1));
                Check.eq(List.of("A4", "A5"), find(map, 2));
                Check.eq(List.of("A4", "A5", "A6"), find(map, 3));
                Check.eq(List.of("A3", "A4", "A5", "A6"), find(map, 4));
            });

            Check.test("size limits", () -> {
                SeatMap map = new SeatMap(5, 10);
                Check.raises(IllegalArgumentException.class, () -> find(map, 0));
                Check.raises(IllegalArgumentException.class, () -> find(map, 9));
                Check.raises(IllegalArgumentException.class, () -> find(map, -1));
                Check.eq(8, find(map, 8).size());
            });

            Check.test("a lonely seat is avoided", () -> {
                SeatMap map = new SeatMap(5, 10);
                Check.eq(List.of("D6", "D7"), find(map, 2, "D5"));
                Check.eq(List.of("D6", "D7", "D8"), find(map, 3, "D5"));
            });

            Check.test("lonely seat rule against blocked seats and walls", () -> {
                SeatMap map = new SeatMap(1, 10, "A5");
                Check.eq(List.of("A6", "A7", "A8"), find(map, 3));
                Check.eq(List.of("A6", "A7"), find(map, 2));
                SeatMap tight = new SeatMap(1, 4);
                Check.eq(List.of("A1", "A2"), find(tight, 2));
                Check.eq(List.of("A1", "A2", "A3", "A4"), find(tight, 4));
            });

            Check.test("a lonely seat is accepted when there is no alternative", () -> {
                SeatMap map = new SeatMap(1, 3);
                Check.eq(List.of("A1", "A2"), find(map, 2));
                Check.eq(List.of("A1"), find(map, 1, "A2", "A3"));
                Check.eq(List.of("A3"), find(map, 1, "A1", "A2"));
                Check.eq(List.of("A2", "A3"), find(map, 2, "A1"));
            });

            Check.test("a gap of two is fine", () -> {
                SeatMap map = new SeatMap(1, 8);
                Check.eq(List.of("A3", "A4", "A5"), find(map, 3, "A1", "A2", "A8"));
                Check.eq(List.of("A5", "A6", "A7"), find(map, 3, "A1", "A2", "A8", "A4"));
            });

            Check.test("rows are tried by distance from the sweet row", () -> {
                SeatMap map = new SeatMap(5, 10);
                Check.eq(List.of("C5", "C6"), SeatFinder.findBlock(map, fullRows(10, 'D'), 2));
                Check.eq(List.of("E5", "E6"), SeatFinder.findBlock(map, fullRows(10, 'D', 'C'), 2));
                Check.eq(List.of("B5", "B6"), SeatFinder.findBlock(map, fullRows(10, 'D', 'C', 'E'), 2));
                Check.eq(List.of("A5", "A6"), SeatFinder.findBlock(map, fullRows(10, 'D', 'C', 'E', 'B'), 2));
            });

            Check.test("a clean block further away beats a lonely seat in the sweet row", () -> {
                SeatMap map = new SeatMap(5, 5);
                // row D has only D2..D4 free: any pair leaves one seat alone. Row C is clean.
                Check.eq(List.of("C1", "C2"), find(map, 2, "D1", "D5"));
                Check.eq(List.of("D2", "D3", "D4"), find(map, 3, "D1", "D5"));
            });

            Check.test("no room gives an empty list", () -> {
                SeatMap map = new SeatMap(2, 3, "A2");
                Check.eq(List.of("B1", "B2", "B3"), find(map, 3));
                Check.eq(List.of(), find(map, 3, "B2"));
                Check.eq(List.of(), find(map, 2, "B2"));
                Check.eq(List.of("A1"), find(map, 1, "B1", "B2", "B3", "A3"));
                Check.eq(List.of(), find(map, 1, "B1", "B2", "B3", "A1", "A3"));
            });

            Check.test("hold picks a block and expires", () -> {
                Reservations res = new Reservations(new SeatMap(5, 10), 10);
                Reservations.Hold h = res.hold(2, 0).get();
                Check.eq("H1", h.id);
                Check.eq(List.of("D5", "D6"), h.seats);
                Check.eq(10, h.expiresAt);
                Check.eq(48, res.freeCount(9));
                Check.eq(set("D5", "D6"), res.taken(9));
                Check.eq(50, res.freeCount(10));
                Check.eq(set(), res.taken(10));
            });

            Check.test("a second hold avoids the first", () -> {
                Reservations res = new Reservations(new SeatMap(5, 10), 10);
                res.hold(2, 0);
                Reservations.Hold h2 = res.hold(2, 5).get();
                Check.eq("H2", h2.id);
                Check.eq(List.of("D3", "D4"), h2.seats);
                Check.eq(15, h2.expiresAt);
                Check.eq(46, res.freeCount(9));
                Check.eq(48, res.freeCount(10));
                Check.eq(50, res.freeCount(15));
            });

            Check.test("an expired hold lets the same seats be held again", () -> {
                Reservations res = new Reservations(new SeatMap(5, 10), 10);
                res.hold(2, 0);
                Check.eq(List.of("D3", "D4"), res.hold(2, 9).get().seats);
                Check.eq(List.of("D5", "D6"), res.hold(2, 11).get().seats);
            });

            Check.test("confirm turns a hold into a booking", () -> {
                Reservations res = new Reservations(new SeatMap(5, 10), 10);
                Reservations.Hold h = res.hold(3, 0).get();
                Check.eq(List.of("D4", "D5", "D6"), res.confirm(h.id, 9));
                Check.eq(List.of("D4", "D5", "D6"), res.booked());
                Check.eq(47, res.freeCount(1000));
                Check.eq(set("D4", "D5", "D6"), res.taken(1000));
                Check.raises(IllegalStateException.class, () -> res.confirm(h.id, 9));
            });

            Check.test("confirm fails after expiry, for unknown ids and after release", () -> {
                Reservations res = new Reservations(new SeatMap(5, 10), 10);
                Reservations.Hold h = res.hold(2, 0).get();
                Check.raises(IllegalStateException.class, () -> res.confirm(h.id, 10));
                Check.raises(IllegalStateException.class, () -> res.confirm("H99", 0));
                Reservations.Hold g = res.hold(2, 20).get();
                Check.eq("H2", g.id);
                Check.yes(res.release(g.id, 25), "release active");
                Check.raises(IllegalStateException.class, () -> res.confirm(g.id, 26));
                Check.yes(res.booked().isEmpty(), "nothing booked");
            });

            Check.test("confirm succeeds on the last minute", () -> {
                Reservations res = new Reservations(new SeatMap(5, 10), 10);
                Reservations.Hold h = res.hold(2, 0).get();
                Check.eq(List.of("D5", "D6"), res.confirm(h.id, 9));
            });

            Check.test("release", () -> {
                Reservations res = new Reservations(new SeatMap(5, 10), 10);
                Reservations.Hold h = res.hold(2, 0).get();
                Check.yes(!res.release("H7", 1), "unknown id");
                Check.yes(res.release(h.id, 1), "first release");
                Check.yes(!res.release(h.id, 1), "second release");
                Check.eq(50, res.freeCount(1));
                Reservations.Hold again = res.hold(2, 1).get();
                Check.eq(List.of("D5", "D6"), again.seats);
                Check.yes(!res.release(again.id, 11), "expired holds cannot be released");
            });

            Check.test("hold ids are only used up by successful holds", () -> {
                Reservations res = new Reservations(new SeatMap(1, 3), 5);
                Check.eq("H1", res.hold(3, 0).get().id);
                Check.yes(res.hold(1, 1).isEmpty(), "full hall");
                Check.yes(res.hold(2, 2).isEmpty(), "still full");
                Check.eq("H2", res.hold(1, 5).get().id);
            });

            Check.test("booked seats are sorted by row then seat number", () -> {
                Reservations res = new Reservations(new SeatMap(2, 12), 5);
                for (int i = 0; i < 24; i++) {
                    res.confirm(res.hold(1, 0).get().id, 0);
                }
                List<String> expected = new java.util.ArrayList<>();
                for (char row = 'A'; row <= 'B'; row++) {
                    for (int seat = 1; seat <= 12; seat++) {
                        expected.add("" + row + seat);
                    }
                }
                Check.eq(expected, res.booked());
                Check.eq(0, res.freeCount(0));
                Check.yes(res.hold(1, 0).isEmpty(), "hall is full");
            });

            Check.test("single seats fill the hall from the middle outwards", () -> {
                Reservations res = new Reservations(new SeatMap(1, 7), 5);
                String[] order = {"A4", "A3", "A5", "A2", "A1", "A6", "A7"};
                for (String want : order) {
                    Check.eq(List.of(want), res.hold(1, 0).get().seats);
                }
            });

            Check.test("blocked seats do not count as free", () -> {
                Reservations res = new Reservations(new SeatMap(2, 3, "A1", "B3"), 5);
                Check.eq(4, res.freeCount(0));
                res.hold(2, 0);
                Check.eq(2, res.freeCount(0));
            });

            Check.test("holdMinutes validation", () -> {
                Check.raises(IllegalArgumentException.class, () -> new Reservations(new SeatMap(2, 3), 0));
                Check.raises(IllegalArgumentException.class, () -> new Reservations(new SeatMap(2, 3), -3));
                new Reservations(new SeatMap(2, 3), 1);
            });

            Check.test("hold validates the group size", () -> {
                Reservations res = new Reservations(new SeatMap(5, 10), 5);
                Check.raises(IllegalArgumentException.class, () -> res.hold(0, 0));
                Check.raises(IllegalArgumentException.class, () -> res.hold(9, 0));
            });

            Check.test("roundDiv rounds half up", () -> {
                Check.eq(0, Pricing.roundDiv(0, 100));
                Check.eq(0, Pricing.roundDiv(49, 100));
                Check.eq(1, Pricing.roundDiv(50, 100));
                Check.eq(1, Pricing.roundDiv(149, 100));
                Check.eq(2, Pricing.roundDiv(150, 100));
                Check.eq(3, Pricing.roundDiv(5, 2));
                Check.eq(2, Pricing.roundDiv(7, 4));
                Check.eq(1, Pricing.roundDiv(4, 4));
                Check.eq(4000000, Pricing.roundDiv(4000000L * 100, 100));
            });

            Check.test("seat price zones", () -> {
                int[] expected = {800, 800, 1000, 1000, 1250, 1250, 1250, 1250, 1000, 1000};
                for (int row = 0; row < 10; row++) {
                    Check.eq("row " + row, expected[row], Pricing.seatPrice(row, 10, 1000));
                }
                Check.eq(800, Pricing.seatPrice(0, 7, 1000));
                Check.eq(800, Pricing.seatPrice(1, 7, 1000));
                Check.eq(1000, Pricing.seatPrice(2, 7, 1000));
                Check.eq(1250, Pricing.seatPrice(3, 7, 1000));
                Check.eq(1250, Pricing.seatPrice(5, 7, 1000));
                Check.eq(1000, Pricing.seatPrice(6, 7, 1000));
                Check.eq(1250, Pricing.seatPrice(12, 25, 1000));
                Check.eq(800, Pricing.seatPrice(0, 1, 1000));
                Check.eq(25000000, Pricing.seatPrice(5, 10, 20000000));
            });

            Check.test("seat price rounding", () -> {
                Check.eq(804, Pricing.seatPrice(0, 10, 1005));
                Check.eq(801, Pricing.seatPrice(0, 10, 1001));
                Check.eq(802, Pricing.seatPrice(0, 10, 1002));
                Check.eq(1251, Pricing.seatPrice(5, 10, 1001));
                Check.eq(1253, Pricing.seatPrice(5, 10, 1002));
                Check.eq(1254, Pricing.seatPrice(5, 10, 1003));
                Check.eq(1258, Pricing.seatPrice(5, 10, 1006));
                Check.eq(2147483, Pricing.seatPrice(5, 10, 1717986));
            });

            Check.test("group totals and the six-seat discount", () -> {
                Check.eq(0, Pricing.groupTotal(List.of(), 10, 1000));
                Check.eq(2000, Pricing.groupTotal(List.of("D5", "D6"), 10, 1000));
                Check.eq(800 + 1250, Pricing.groupTotal(List.of("A1", "E1"), 10, 1000));
                Check.eq(5400, Pricing.groupTotal(List.of("D1", "D2", "D3", "D4", "D5", "D6"), 10, 1000));
                Check.eq(5000, Pricing.groupTotal(List.of("D1", "D2", "D3", "D4", "D5"), 10, 1000));
                Check.eq(5737, Pricing.groupTotal(List.of("E1", "F1", "G1", "C1", "A1", "B1"), 10, 1004));
                Check.eq(6300, Pricing.groupTotal(List.of("D1", "D2", "D3", "D4", "D5", "D6", "D7"), 10, 1000));
            });
        }
    }
''')

LIB = Lib(
    name="seatbook", lang="java", title="the seatbook engine",
    blurb="The cinema's booking desk uses seatbook to pick seats for groups, hold them for a few minutes and price them.",
    files={"src/venue/SeatMap.java": SEATMAP, "src/venue/SeatFinder.java": FINDER, "src/venue/Reservations.java": RESERVATIONS,
           "src/venue/Pricing.java": PRICING, "README.md": README, ".gitignore": "build/\n"},
    visible_tests={"test/Check.java": JAVA_CHECK, "test/BasicTests.java": BASIC, "test/TestMain.java": VISIBLE_MAIN},
    hidden_tests={"test/FullTests.java": FULL, "test/TestMain.java": HIDDEN_MAIN},
    mutate=["src/venue/SeatFinder.java", "src/venue/Reservations.java", "src/venue/Pricing.java", "src/venue/SeatMap.java"],
    difficulty=3, tags=["booking", "seating", "pricing"],
    probe_import="import java.util.*;\nimport venue.*;",
    probes=[
        "SeatFinder.sweetRow(10)", "SeatFinder.sweetRow(26)",
        "SeatFinder.findBlock(new SeatMap(5, 10), new HashSet<String>(), 3)",
        "SeatFinder.findBlock(new SeatMap(5, 10), new HashSet<String>(), 8)",
        "SeatFinder.findBlock(new SeatMap(5, 10), new HashSet<String>(List.of(\"D5\")), 2)",
        "SeatFinder.findBlock(new SeatMap(1, 10, \"A5\"), new HashSet<String>(), 3)",
        "SeatFinder.findBlock(new SeatMap(5, 5), new HashSet<String>(List.of(\"D1\", \"D5\")), 2)",
        "SeatFinder.findBlock(new SeatMap(1, 3), new HashSet<String>(), 2)",
        "SeatFinder.findBlock(new SeatMap(2, 3, \"A2\"), new HashSet<String>(List.of(\"B2\")), 2)",
        "SeatMap.label(2, 12)", "SeatMap.parse(\"C12\")", "SeatMap.parse(\"A05\")",
        "Pricing.seatPrice(5, 10, 1002)", "Pricing.seatPrice(1, 7, 1000)", "Pricing.seatPrice(0, 10, 1001)",
        "Pricing.groupTotal(List.of(\"E1\", \"F1\", \"G1\", \"C1\", \"A1\", \"B1\"), 10, 1004)",
        "Pricing.groupTotal(List.of(\"D1\", \"D2\", \"D3\", \"D4\", \"D5\"), 10, 1000)",
        "Pricing.roundDiv(5, 2)",
    ],
)

register_libs([LIB], n=8)
