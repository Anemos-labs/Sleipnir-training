"""Swim-meet seeding (java): bugs injected into a time parser and a heat and lane seeder."""
from fx import Lib, dd
from generators.fix._lang2 import JAVA_CHECK, java_test_main, register_libs

README = dd(r'''
    # lanedraw

    Seeding for a swimming meet: swim times, heats and lanes from the entries. Plain Java 17, no dependencies; sources in
    `src/meet/`.

    ## `Times`

    * `Times.parse(text)`: a swim time in milliseconds. Surrounding white space is ignored. Forms: `ss`, `ss.f`, `m:ss` and
      `m:ss.f`, where `m` is one or two digits of minutes, `ss` is the seconds and `f` is one to three digits of a fraction of a
      second (`.5` is 500 ms, `.25` is 250 ms, `.257` is 257 ms). With minutes the seconds have exactly two digits; without minutes
      they have one or two. Seconds are 0 to 59. A time of zero, and anything else, is an `IllegalArgumentException`.
    * `Times.format(millis)`: the time rounded to hundredths of a second (half up) and written as `m:ss.cc` from one minute up,
      below that as `s.cc` with the seconds not padded (`28.45`, `5.30`). `format(59996)` is `1:00.00`. A time of zero or less is an
      `IllegalArgumentException`.

    ## `Entry`

    * `new Entry(name, millis)`: the name is trimmed and must not be empty, `millis` must be above 0
      (`IllegalArgumentException`).
    * `Entry.noTime(name)`: an entry without a seed time (NT).
    * `Entry.of(name, timeText)`: `timeText` is read with `Times.parse`, or it is `NT` in any case for no time.
    * `name()`, `hasTime()`, `millis()` (`-1` for an entry without a time).

    ## `Draw`

    * `Draw.laneOrder(lanes)` (`lanes` from 4 to 10, else `IllegalArgumentException`): the lanes in the order in which the
      fastest swimmers of a heat are given them, middle outwards. Let `c = (lanes + 1) / 2` (integer division); the order is `c`,
      `c + 1`, `c - 1`, `c + 2`, `c - 2`, and so on, leaving out numbers outside `1..lanes`. With 8 lanes it is
      `[4, 5, 3, 6, 2, 7, 1, 8]`, with 5 lanes `[3, 4, 2, 5, 1]`.
    * `Draw.seed(entries, lanes)`: the heats, as a list of `Heat` (empty for no entries). Two entries with the same name (ignoring
      case) are an `IllegalArgumentException`.

    The entries are first put in seed order: those with a time, fastest first, then those without a time; equal times, and the
    entries without time among themselves, are ordered by name (plain `String` order). Then:

    1. There are `ceil(n / lanes)` heats. Heat 1 is the slowest and the last heat is the fastest. All heats are full except heat 1,
       which gets the swimmers that are left over (`n - (heats - 1) * lanes`), the slowest ones of the seed order.
    2. If there is more than one heat and heat 1 would get fewer than 3 swimmers, it takes enough swimmers from heat 2 (the slowest
       of them) to have 3; heat 2 is then not full.
    3. Inside a heat the swimmers, fastest first, get the lanes in `laneOrder` order.

    ## `Heat`

    `number()` (from 1), `seats()` (a list of `Seat`, ordered by lane, lowest lane first). A `Seat` has `lane()` and `entry()`.

    ## Text

    `Draw.format(heats)` writes the draw, one line per heat and per swimmer, joined with `\n`:

    ```
    Heat 1 of 2
      lane 3: Dee Lund 1:12.40
      lane 4: Ola Berg NT
    ```

    A seat shows the lane, the name and the time written with `Times.format` or `NT`. Heats come in order and the seats of a heat
    in lane order. `no entries` when the list of heats is empty.
''')

TIMES = dd(r'''
    package meet;

    public final class Times {
        private Times() {}

        public static int parse(String text) {
            String t = text.trim();
            String whole = t;
            String fraction = "";
            int dot = t.indexOf('.');
            if (dot >= 0) {
                whole = t.substring(0, dot);
                fraction = t.substring(dot + 1);
                if (fraction.length() < 1 || fraction.length() > 3 || !digits(fraction)) {
                    throw new IllegalArgumentException("bad fraction: " + text);
                }
            }
            long minutes = 0;
            String seconds = whole;
            int colon = whole.indexOf(':');
            if (colon >= 0) {
                String m = whole.substring(0, colon);
                seconds = whole.substring(colon + 1);
                if (m.length() < 1 || m.length() > 2 || !digits(m) || seconds.length() != 2) {
                    throw new IllegalArgumentException("bad time: " + text);
                }
                minutes = Long.parseLong(m);
            } else if (seconds.length() < 1 || seconds.length() > 2) {
                throw new IllegalArgumentException("bad time: " + text);
            }
            if (!digits(seconds)) {
                throw new IllegalArgumentException("bad time: " + text);
            }
            long s = Long.parseLong(seconds);
            if (s > 59) {
                throw new IllegalArgumentException("seconds are 0 to 59: " + text);
            }
            long millis = Long.parseLong((fraction + "000").substring(0, 3));
            long total = (minutes * 60 + s) * 1000 + millis;
            if (total == 0) {
                throw new IllegalArgumentException("a time of zero: " + text);
            }
            return (int) total;
        }

        private static boolean digits(String s) {
            if (s.isEmpty()) {
                return false;
            }
            for (char c : s.toCharArray()) {
                if (c < '0' || c > '9') {
                    return false;
                }
            }
            return true;
        }

        public static String format(int millis) {
            if (millis <= 0) {
                throw new IllegalArgumentException("time must be above zero");
            }
            long hundredths = (millis + 5L) / 10;
            long minutes = hundredths / 6000;
            long seconds = (hundredths / 100) % 60;
            long cc = hundredths % 100;
            String frac = String.format("%02d", cc);
            if (minutes > 0) {
                return minutes + ":" + String.format("%02d", seconds) + "." + frac;
            }
            return seconds + "." + frac;
        }
    }
''')

ENTRY = dd(r'''
    package meet;

    public final class Entry {
        private final String name;
        private final int millis;

        private Entry(String name, int millis, boolean timed) {
            String n = name.trim();
            if (n.isEmpty()) {
                throw new IllegalArgumentException("empty name");
            }
            if (timed && millis <= 0) {
                throw new IllegalArgumentException("time must be above zero");
            }
            this.name = n;
            this.millis = millis;
        }

        public Entry(String name, int millis) {
            this(name, millis, true);
        }

        public static Entry noTime(String name) {
            return new Entry(name, -1, false);
        }

        public static Entry of(String name, String timeText) {
            if (timeText.trim().equalsIgnoreCase("NT")) {
                return noTime(name);
            }
            return new Entry(name, Times.parse(timeText));
        }

        public String name() {
            return name;
        }

        public boolean hasTime() {
            return millis > 0;
        }

        public int millis() {
            return millis;
        }
    }
''')

SEAT = dd(r'''
    package meet;

    public final class Seat {
        private final int lane;
        private final Entry entry;

        Seat(int lane, Entry entry) {
            this.lane = lane;
            this.entry = entry;
        }

        public int lane() {
            return lane;
        }

        public Entry entry() {
            return entry;
        }
    }
''')

HEAT = dd(r'''
    package meet;

    import java.util.Collections;
    import java.util.List;

    public final class Heat {
        private final int number;
        private final List<Seat> seats;

        Heat(int number, List<Seat> seats) {
            this.number = number;
            this.seats = seats;
        }

        public int number() {
            return number;
        }

        public List<Seat> seats() {
            return Collections.unmodifiableList(seats);
        }
    }
''')

DRAW = dd(r'''
    package meet;

    import java.util.ArrayList;
    import java.util.Arrays;
    import java.util.HashSet;
    import java.util.List;
    import java.util.Set;

    public final class Draw {
        private static final int MIN_HEAT = 3;

        private Draw() {}

        public static List<Integer> laneOrder(int lanes) {
            if (lanes < 4 || lanes > 10) {
                throw new IllegalArgumentException("lanes are 4 to 10");
            }
            int c = (lanes + 1) / 2;
            List<Integer> order = new ArrayList<>();
            order.add(c);
            for (int step = 1; order.size() < lanes; step++) {
                if (c + step <= lanes) {
                    order.add(c + step);
                }
                if (c - step >= 1) {
                    order.add(c - step);
                }
            }
            return order;
        }

        public static List<Heat> seed(List<Entry> entries, int lanes) {
            List<Integer> order = laneOrder(lanes);
            Set<String> names = new HashSet<>();
            for (Entry e : entries) {
                if (!names.add(e.name().toLowerCase())) {
                    throw new IllegalArgumentException("duplicate entry: " + e.name());
                }
            }
            List<Entry> seeded = new ArrayList<>(entries);
            seeded.sort((a, b) -> {
                if (a.hasTime() != b.hasTime()) {
                    return a.hasTime() ? -1 : 1;
                }
                if (a.hasTime() && a.millis() != b.millis()) {
                    return Integer.compare(a.millis(), b.millis());
                }
                return a.name().compareTo(b.name());
            });
            int n = seeded.size();
            List<Heat> heats = new ArrayList<>();
            if (n == 0) {
                return heats;
            }
            int count = (n + lanes - 1) / lanes;
            int[] sizes = new int[count];
            Arrays.fill(sizes, lanes);
            sizes[0] = n - (count - 1) * lanes;
            if (count > 1 && sizes[0] < MIN_HEAT) {
                int shift = MIN_HEAT - sizes[0];
                sizes[0] += shift;
                sizes[1] -= shift;
            }
            List<List<Entry>> groups = new ArrayList<>();
            int end = n;
            for (int h = 0; h < count; h++) {
                groups.add(new ArrayList<>(seeded.subList(end - sizes[h], end)));
                end -= sizes[h];
            }
            for (int h = 0; h < groups.size(); h++) {
                List<Entry> group = groups.get(h);
                List<Seat> seats = new ArrayList<>();
                for (int i = 0; i < group.size(); i++) {
                    seats.add(new Seat(order.get(i), group.get(i)));
                }
                seats.sort((a, b) -> Integer.compare(a.lane(), b.lane()));
                heats.add(new Heat(h + 1, seats));
            }
            return heats;
        }

        public static String format(List<Heat> heats) {
            if (heats.isEmpty()) {
                return "no entries";
            }
            StringBuilder sb = new StringBuilder();
            for (Heat heat : heats) {
                if (sb.length() > 0) {
                    sb.append('\n');
                }
                sb.append("Heat ").append(heat.number()).append(" of ").append(heats.size());
                for (Seat seat : heat.seats()) {
                    Entry e = seat.entry();
                    sb.append("\n  lane ").append(seat.lane()).append(": ").append(e.name()).append(' ')
                            .append(e.hasTime() ? Times.format(e.millis()) : "NT");
                }
            }
            return sb.toString();
        }
    }
''')

BASIC = dd(r'''
    import java.util.List;
    import meet.Draw;
    import meet.Times;

    public class BasicTests {
        public static void run() {
            Check.test("parse a swim time", () -> {
                Check.eq(65200, Times.parse("1:05.20"));
                Check.eq("1:05.20", Times.format(65200));
            });
            Check.test("lane order", () -> {
                Check.eq(List.of(4, 5, 3, 6, 2, 7, 1, 8), Draw.laneOrder(8));
            });
        }
    }
''')

FULL = dd(r'''
    import java.util.ArrayList;
    import java.util.List;
    import meet.Draw;
    import meet.Entry;
    import meet.Heat;
    import meet.Seat;
    import meet.Times;

    public class FullTests {
        static void draw(String entries, int lanes, String expected) {
            List<Entry> list = new ArrayList<>();
            for (String part : entries.split(";")) {
                String[] p = part.split("\\|");
                list.add(Entry.of(p[0], p[1]));
            }
            Check.eq(entries + " on " + lanes + " lanes", expected, Draw.format(Draw.seed(list, lanes)));
        }

        public static void run() {
            Check.test("Entry", () -> {
                Entry a = new Entry("  Ann Lee ", 65200);
                Check.eq("Ann Lee", a.name());
                Check.eq(65200, a.millis());
                Check.yes(a.hasTime(), "has a time");
                Entry n = Entry.noTime(" Bo ");
                Check.eq("Bo", n.name());
                Check.eq(-1, n.millis());
                Check.yes(!n.hasTime(), "no time");
                Check.eq(65200, Entry.of("Cy", "1:05.20").millis());
                Check.yes(Entry.of("Cy", "nt").millis() < 0, "nt");
                Check.yes(!Entry.of("Cy", " NT ").hasTime(), "NT with spaces");
                Check.yes(!Entry.of("Cy", "Nt").hasTime(), "Nt");
                Check.yes(Entry.of("Cy", "59.9").hasTime(), "time");
                Check.eq(1, new Entry("X", 1).millis());
            });

            Check.test("Entry is validated", () -> {
                Check.raises(IllegalArgumentException.class, () -> new Entry("", 1000));
                Check.raises(IllegalArgumentException.class, () -> new Entry("   ", 1000));
                Check.raises(IllegalArgumentException.class, () -> new Entry("Ann", 0));
                Check.raises(IllegalArgumentException.class, () -> new Entry("Ann", -5));
                Check.raises(IllegalArgumentException.class, () -> Entry.noTime(""));
                Check.raises(IllegalArgumentException.class, () -> Entry.noTime("  "));
                Check.raises(IllegalArgumentException.class, () -> Entry.of("", "28.45"));
                Check.raises(IllegalArgumentException.class, () -> Entry.of("Ann", "fast"));
                Check.raises(IllegalArgumentException.class, () -> Entry.of("Ann", "0"));
                Check.raises(IllegalArgumentException.class, () -> Entry.of("Ann", ""));
            });

            Check.test("Times.parse", () -> {
                Check.eq(28450, Times.parse("28.45"));
                Check.eq(5300, Times.parse("5.3"));
                Check.eq(5000, Times.parse("5"));
                Check.eq(59000, Times.parse("59"));
                Check.eq(59999, Times.parse("59.999"));
                Check.eq(500, Times.parse("0.5"));
                Check.eq(500, Times.parse("00.50"));
                Check.eq(65000, Times.parse("1:05"));
                Check.eq(65200, Times.parse("1:05.2"));
                Check.eq(65200, Times.parse("1:05.20"));
                Check.eq(65257, Times.parse("1:05.257"));
                Check.eq(600000, Times.parse("10:00"));
                Check.eq(5999999, Times.parse("99:59.999"));
                Check.eq(65200, Times.parse("01:05.20"));
                Check.eq(28450, Times.parse("  28.45 "));
                Check.eq(30500, Times.parse("0:30.5"));
                Check.eq(427070, Times.parse("7:07.07"));
                Check.eq(1000, Times.parse("0:01"));
                Check.eq(12005, Times.parse("12.005"));
                Check.eq(12050, Times.parse("12.050"));
                Check.eq(12500, Times.parse("12.500"));
            });

            Check.test("Times.parse rejects bad text", () -> {
                Check.raises(IllegalArgumentException.class, () -> Times.parse(""));
                Check.raises(IllegalArgumentException.class, () -> Times.parse(" "));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("0"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("0.0"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("0:00"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("0:00.000"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("60"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("1:60"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("60.00"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("1:5"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("1:005"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("123.4"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("5."));
                Check.raises(IllegalArgumentException.class, () -> Times.parse(".5"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("5.1234"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("1:05."));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("-5"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("1:-5"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("1e3"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("abc"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("NT"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("1:05:03"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("100:00"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("1: 05"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("1 :05"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("5 .5"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("5,5"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("5.5.5"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("::"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("1::05"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("+5"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("1:+5"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("1.5:00"));
                Check.raises(IllegalArgumentException.class, () -> Times.parse("0x10"));
            });

            Check.test("Times.format", () -> {
                Check.eq("0.00", Times.format(1));
                Check.eq("0.00", Times.format(4));
                Check.eq("0.01", Times.format(5));
                Check.eq("0.01", Times.format(6));
                Check.eq("0.01", Times.format(10));
                Check.eq("0.01", Times.format(14));
                Check.eq("0.02", Times.format(15));
                Check.eq("0.02", Times.format(16));
                Check.eq("1.00", Times.format(995));
                Check.eq("1.00", Times.format(1000));
                Check.eq("5.30", Times.format(5300));
                Check.eq("28.45", Times.format(28450));
                Check.eq("28.45", Times.format(28454));
                Check.eq("28.46", Times.format(28455));
                Check.eq("28.46", Times.format(28456));
                Check.eq("59.99", Times.format(59994));
                Check.eq("1:00.00", Times.format(59995));
                Check.eq("1:00.00", Times.format(59996));
                Check.eq("1:00.00", Times.format(59999));
                Check.eq("1:00.00", Times.format(60000));
                Check.eq("1:00.00", Times.format(60004));
                Check.eq("1:00.01", Times.format(60005));
                Check.eq("1:05.20", Times.format(65200));
                Check.eq("1:05.20", Times.format(65204));
                Check.eq("1:05.21", Times.format(65205));
                Check.eq("2:00.00", Times.format(119999));
                Check.eq("10:00.00", Times.format(599995));
                Check.eq("60:00.00", Times.format(3599999));
                Check.eq("60:00.00", Times.format(3600000));
                Check.eq("61:05.00", Times.format(3665000));
                Check.eq("100:00.00", Times.format(5999999));
                Check.raises(IllegalArgumentException.class, () -> Times.format(0));
                Check.raises(IllegalArgumentException.class, () -> Times.format(-5));
            });

            Check.test("lane order", () -> {
                Check.eq(List.of(2, 3, 1, 4), Draw.laneOrder(4));
                Check.eq(List.of(3, 4, 2, 5, 1), Draw.laneOrder(5));
                Check.eq(List.of(3, 4, 2, 5, 1, 6), Draw.laneOrder(6));
                Check.eq(List.of(4, 5, 3, 6, 2, 7, 1), Draw.laneOrder(7));
                Check.eq(List.of(4, 5, 3, 6, 2, 7, 1, 8), Draw.laneOrder(8));
                Check.eq(List.of(5, 6, 4, 7, 3, 8, 2, 9, 1), Draw.laneOrder(9));
                Check.eq(List.of(5, 6, 4, 7, 3, 8, 2, 9, 1, 10), Draw.laneOrder(10));
                Check.raises(IllegalArgumentException.class, () -> Draw.laneOrder(-1));
                Check.raises(IllegalArgumentException.class, () -> Draw.laneOrder(0));
                Check.raises(IllegalArgumentException.class, () -> Draw.laneOrder(1));
                Check.raises(IllegalArgumentException.class, () -> Draw.laneOrder(3));
                Check.raises(IllegalArgumentException.class, () -> Draw.laneOrder(11));
                Check.raises(IllegalArgumentException.class, () -> Draw.laneOrder(12));
            });

            Check.test("heat sizes with 8 lanes", () -> {
                draw("Abe|1:00.55", 8,
                        "Heat 1 of 1\n  lane 4: Abe 1:00.55");
                draw("Di|1:08.15;Wes|1:09.70", 8,
                        "Heat 1 of 1\n  lane 4: Di 1:08.15\n  lane 5: Wes 1:09.70");
                draw("Abe|1:17.15;Vic|1:19.85;Jo|1:01.60", 8,
                        "Heat 1 of 1\n  lane 3: Vic 1:19.85\n  lane 4: Jo 1:01.60\n  lane 5: Abe 1:17.15");
                draw("Vic|1:14.75;Flo|1:14.95;Pia|1:10.15;Dot|1:01.25;Hal|1:05.65;Cam|1:01.15;Jo|1:14.25", 8,
                        "Heat 1 of 1\n  lane 1: Flo 1:14.95\n  lane 2: Jo 1:14.25\n  lane 3: Hal 1:05.65\n  lane 4: Cam 1:01.15\n  lane 5: Dot 1:01.25\n  lane 6: Pia 1:10.15\n  lane 7: Vic 1:14.75");
                draw("Vic|1:12.10;Flo|1:09.70;Ivy|1:18.55;Yul|1:02.90;Tia|1:16.95;Cam|1:06.60;Kai|1:02.45;Xan|1:01.60", 8,
                        "Heat 1 of 1\n  lane 1: Tia 1:16.95\n  lane 2: Flo 1:09.70\n  lane 3: Yul 1:02.90\n  lane 4: Xan 1:01.60\n  lane 5: Kai 1:02.45\n  lane 6: Cam 1:06.60\n  lane 7: Vic 1:12.10\n  lane 8: Ivy 1:18.55");
                draw("Pia|1:19.10;Zoe|1:02.60;Abe|1:07.45;Yul|1:05.20;Uma|1:17.25;Rae|1:05.70;Wes|1:18.55;Di|1:10.75;Jo|1:02.20", 8,
                        "Heat 1 of 2\n  lane 3: Pia 1:19.10\n  lane 4: Uma 1:17.25\n  lane 5: Wes 1:18.55\nHeat 2 of 2\n  lane 2: Abe 1:07.45\n  lane 3: Yul 1:05.20\n  lane 4: Jo 1:02.20\n  lane 5: Zoe 1:02.60\n  lane 6: Rae 1:05.70\n  lane 7: Di 1:10.75");
                draw("Hal|1:17.55;Rae|1:07.75;Wes|1:16.90;Ed|1:09.25;Uma|1:03.40;Jo|1:11.65;Bea|1:19.65;Max|1:06.10;Cy|1:11.25;Xan|1:15.70", 8,
                        "Heat 1 of 2\n  lane 3: Bea 1:19.65\n  lane 4: Wes 1:16.90\n  lane 5: Hal 1:17.55\nHeat 2 of 2\n  lane 1: Xan 1:15.70\n  lane 2: Cy 1:11.25\n  lane 3: Rae 1:07.75\n  lane 4: Uma 1:03.40\n  lane 5: Max 1:06.10\n  lane 6: Ed 1:09.25\n  lane 7: Jo 1:11.65");
                draw("Tia|1:13.50;Jo|1:01.60;Ned|1:01.50;Max|1:00.90;Wes|1:04.85;Lea|1:06.15;Cam|1:15.35;Hal|1:00.75;Vic|1:19.90;Ann|1:11.85;Kai|1:08.35", 8,
                        "Heat 1 of 2\n  lane 3: Vic 1:19.90\n  lane 4: Tia 1:13.50\n  lane 5: Cam 1:15.35\nHeat 2 of 2\n  lane 1: Kai 1:08.35\n  lane 2: Wes 1:04.85\n  lane 3: Ned 1:01.50\n  lane 4: Hal 1:00.75\n  lane 5: Max 1:00.90\n  lane 6: Jo 1:01.60\n  lane 7: Lea 1:06.15\n  lane 8: Ann 1:11.85");
                draw("Sol|1:11.85;Gus|1:11.65;Xan|1:15.30;Bo|1:16.00;Uma|1:18.00;Dot|1:07.55;Max|1:05.70;Di|1:20.00;Rae|1:07.90;Ed|1:09.25;Bea|1:06.60;Cy|1:10.75;Kai|1:02.20;Flo|1:08.90;Vic|1:12.65;Quin|1:10.80", 8,
                        "Heat 1 of 2\n  lane 1: Uma 1:18.00\n  lane 2: Xan 1:15.30\n  lane 3: Sol 1:11.85\n  lane 4: Quin 1:10.80\n  lane 5: Gus 1:11.65\n  lane 6: Vic 1:12.65\n  lane 7: Bo 1:16.00\n  lane 8: Di 1:20.00\nHeat 2 of 2\n  lane 1: Ed 1:09.25\n  lane 2: Rae 1:07.90\n  lane 3: Bea 1:06.60\n  lane 4: Kai 1:02.20\n  lane 5: Max 1:05.70\n  lane 6: Dot 1:07.55\n  lane 7: Flo 1:08.90\n  lane 8: Cy 1:10.75");
                draw("Dot|1:18.30;Vic|1:16.35;Tia|1:01.75;Oda|1:07.90;Bea|1:10.45;Yul|1:02.05;Bo|1:12.95;Sol|1:12.10;Cy|1:16.35;Gus|1:15.35;Kai|1:03.60;Xan|1:17.45;Uma|1:10.45;Pia|1:12.95;Ed|1:08.60;Cam|1:00.45;Max|1:11.05", 8,
                        "Heat 1 of 3\n  lane 3: Dot 1:18.30\n  lane 4: Vic 1:16.35\n  lane 5: Xan 1:17.45\nHeat 2 of 3\n  lane 2: Gus 1:15.35\n  lane 3: Bo 1:12.95\n  lane 4: Max 1:11.05\n  lane 5: Sol 1:12.10\n  lane 6: Pia 1:12.95\n  lane 7: Cy 1:16.35\nHeat 3 of 3\n  lane 1: Bea 1:10.45\n  lane 2: Oda 1:07.90\n  lane 3: Yul 1:02.05\n  lane 4: Cam 1:00.45\n  lane 5: Tia 1:01.75\n  lane 6: Kai 1:03.60\n  lane 7: Ed 1:08.60\n  lane 8: Uma 1:10.45");
                draw("Ned|1:17.30;Ann|1:19.35;Yul|1:12.60;Rae|1:05.50;Zoe|1:18.30;Xan|1:07.65;Max|1:06.75;Quin|1:00.15;Cy|1:08.75;Sol|1:10.35;Tia|1:05.60;Bo|1:19.75;Lea|1:18.60;Ed|1:10.35;Cam|1:13.75;Ivy|1:08.85;Abe|1:15.15;Jo|1:14.65", 8,
                        "Heat 1 of 3\n  lane 3: Bo 1:19.75\n  lane 4: Lea 1:18.60\n  lane 5: Ann 1:19.35\nHeat 2 of 3\n  lane 1: Zoe 1:18.30\n  lane 2: Abe 1:15.15\n  lane 3: Cam 1:13.75\n  lane 4: Sol 1:10.35\n  lane 5: Yul 1:12.60\n  lane 6: Jo 1:14.65\n  lane 7: Ned 1:17.30\nHeat 3 of 3\n  lane 1: Ivy 1:08.85\n  lane 2: Xan 1:07.65\n  lane 3: Tia 1:05.60\n  lane 4: Quin 1:00.15\n  lane 5: Rae 1:05.50\n  lane 6: Max 1:06.75\n  lane 7: Cy 1:08.75\n  lane 8: Ed 1:10.35");
                draw("Tia|1:13.85;Cy|1:11.65;Pia|1:09.90;Hal|1:18.75;Kai|1:01.85;Ned|1:02.50;Uma|1:10.60;Ann|1:00.40;Dot|1:02.50;Wes|1:14.80;Cam|1:18.60;Oda|1:10.80;Flo|1:19.30;Xan|1:10.10;Rae|1:11.25;Bea|1:16.85;Ivy|1:07.65;Ed|1:14.60;Sol|1:12.85", 8,
                        "Heat 1 of 3\n  lane 3: Flo 1:19.30\n  lane 4: Cam 1:18.60\n  lane 5: Hal 1:18.75\nHeat 2 of 3\n  lane 1: Wes 1:14.80\n  lane 2: Tia 1:13.85\n  lane 3: Cy 1:11.65\n  lane 4: Oda 1:10.80\n  lane 5: Rae 1:11.25\n  lane 6: Sol 1:12.85\n  lane 7: Ed 1:14.60\n  lane 8: Bea 1:16.85\nHeat 3 of 3\n  lane 1: Xan 1:10.10\n  lane 2: Ivy 1:07.65\n  lane 3: Dot 1:02.50\n  lane 4: Ann 1:00.40\n  lane 5: Kai 1:01.85\n  lane 6: Ned 1:02.50\n  lane 7: Pia 1:09.90\n  lane 8: Uma 1:10.60");
                draw("Tia|1:15.65;Pia|1:04.00;Cam|1:17.40;Dot|1:08.35;Bea|1:07.80;Di|1:01.90;Vic|1:13.85;Hal|1:16.60;Uma|1:09.35;Ivy|1:16.90;Rae|1:00.85;Bo|1:05.45;Kai|1:08.05;Lea|1:08.65;Ned|1:19.00;Quin|1:01.75;Oda|1:07.95;Ann|1:02.45;Jo|1:06.25;Ed|1:17.00;Cy|1:15.25;Xan|1:03.90;Yul|1:12.50;Zoe|1:07.25", 8,
                        "Heat 1 of 3\n  lane 1: Cam 1:17.40\n  lane 2: Ivy 1:16.90\n  lane 3: Tia 1:15.65\n  lane 4: Vic 1:13.85\n  lane 5: Cy 1:15.25\n  lane 6: Hal 1:16.60\n  lane 7: Ed 1:17.00\n  lane 8: Ned 1:19.00\nHeat 2 of 3\n  lane 1: Uma 1:09.35\n  lane 2: Dot 1:08.35\n  lane 3: Oda 1:07.95\n  lane 4: Zoe 1:07.25\n  lane 5: Bea 1:07.80\n  lane 6: Kai 1:08.05\n  lane 7: Lea 1:08.65\n  lane 8: Yul 1:12.50\nHeat 3 of 3\n  lane 1: Bo 1:05.45\n  lane 2: Xan 1:03.90\n  lane 3: Di 1:01.90\n  lane 4: Rae 1:00.85\n  lane 5: Quin 1:01.75\n  lane 6: Ann 1:02.45\n  lane 7: Pia 1:04.00\n  lane 8: Jo 1:06.25");
                draw("Zoe|1:13.40;Hal|1:02.65;Lea|1:16.25;Cy|1:17.35;Ed|1:02.50;Dot|1:15.35;Cam|1:14.90;Flo|1:09.10;Tia|1:10.60;Vic|1:09.00;Kai|1:04.80;Oda|1:17.30;Sol|1:04.10;Quin|1:15.80;Rae|1:11.75;Di|1:01.85;Ned|1:01.80;Xan|1:10.30;Wes|1:14.40;Ivy|1:01.75;Bo|1:13.15;Pia|1:16.25;Uma|1:03.25;Jo|1:18.65;Gus|1:01.00", 8,
                        "Heat 1 of 4\n  lane 3: Jo 1:18.65\n  lane 4: Oda 1:17.30\n  lane 5: Cy 1:17.35\nHeat 2 of 4\n  lane 2: Lea 1:16.25\n  lane 3: Dot 1:15.35\n  lane 4: Wes 1:14.40\n  lane 5: Cam 1:14.90\n  lane 6: Quin 1:15.80\n  lane 7: Pia 1:16.25\nHeat 3 of 4\n  lane 1: Bo 1:13.15\n  lane 2: Tia 1:10.60\n  lane 3: Flo 1:09.10\n  lane 4: Kai 1:04.80\n  lane 5: Vic 1:09.00\n  lane 6: Xan 1:10.30\n  lane 7: Rae 1:11.75\n  lane 8: Zoe 1:13.40\nHeat 4 of 4\n  lane 1: Uma 1:03.25\n  lane 2: Ed 1:02.50\n  lane 3: Ned 1:01.80\n  lane 4: Gus 1:01.00\n  lane 5: Ivy 1:01.75\n  lane 6: Di 1:01.85\n  lane 7: Hal 1:02.65\n  lane 8: Sol 1:04.10");
            });

            Check.test("heat sizes with other lane counts", () -> {
                draw("Oda|1:18.10;Xan|1:04.65;Ivy|1:15.65;Hal|1:07.95;Uma|1:13.45", 4,
                        "Heat 1 of 2\n  lane 1: Oda 1:18.10\n  lane 2: Uma 1:13.45\n  lane 3: Ivy 1:15.65\nHeat 2 of 2\n  lane 2: Xan 1:04.65\n  lane 3: Hal 1:07.95");
                draw("Abe|1:08.95;Yul|1:01.90;Vic|1:07.35;Uma|1:08.90;Tia|1:08.45;Dot|1:04.55", 4,
                        "Heat 1 of 2\n  lane 1: Abe 1:08.95\n  lane 2: Tia 1:08.45\n  lane 3: Uma 1:08.90\nHeat 2 of 2\n  lane 1: Vic 1:07.35\n  lane 2: Yul 1:01.90\n  lane 3: Dot 1:04.55");
                draw("Dot|1:02.90;Quin|1:01.95;Cam|1:04.10;Gus|1:01.60;Oda|1:12.60;Bo|1:04.80;Max|1:03.90", 4,
                        "Heat 1 of 2\n  lane 1: Oda 1:12.60\n  lane 2: Cam 1:04.10\n  lane 3: Bo 1:04.80\nHeat 2 of 2\n  lane 1: Dot 1:02.90\n  lane 2: Gus 1:01.60\n  lane 3: Quin 1:01.95\n  lane 4: Max 1:03.90");
                draw("Xan|1:15.90;Abe|1:05.15;Tia|1:03.50;Lea|1:15.30;Yul|1:18.50;Ned|1:04.60;Ann|1:10.35;Flo|1:16.95;Max|1:17.00", 4,
                        "Heat 1 of 3\n  lane 1: Yul 1:18.50\n  lane 2: Flo 1:16.95\n  lane 3: Max 1:17.00\nHeat 2 of 3\n  lane 2: Lea 1:15.30\n  lane 3: Xan 1:15.90\nHeat 3 of 3\n  lane 1: Abe 1:05.15\n  lane 2: Tia 1:03.50\n  lane 3: Ned 1:04.60\n  lane 4: Ann 1:10.35");
                draw("Dot|1:02.90;Quin|1:01.95;Cam|1:04.10;Gus|1:01.60;Oda|1:12.60;Bo|1:04.80;Max|1:03.90", 6,
                        "Heat 1 of 2\n  lane 2: Oda 1:12.60\n  lane 3: Cam 1:04.10\n  lane 4: Bo 1:04.80\nHeat 2 of 2\n  lane 2: Dot 1:02.90\n  lane 3: Gus 1:01.60\n  lane 4: Quin 1:01.95\n  lane 5: Max 1:03.90");
                draw("Cam|1:19.05;Zoe|1:18.50;Hal|1:14.40;Sol|1:11.45;Tia|1:00.85;Dot|1:08.80;Ann|1:18.50;Pia|1:08.45", 6,
                        "Heat 1 of 2\n  lane 2: Cam 1:19.05\n  lane 3: Ann 1:18.50\n  lane 4: Zoe 1:18.50\nHeat 2 of 2\n  lane 1: Hal 1:14.40\n  lane 2: Dot 1:08.80\n  lane 3: Tia 1:00.85\n  lane 4: Pia 1:08.45\n  lane 5: Sol 1:11.45");
                draw("Oda|1:13.30;Vic|1:09.00;Cam|1:04.40;Sol|1:15.80;Yul|1:19.45;Bo|1:05.60;Di|1:15.50;Flo|1:06.85;Gus|1:16.55;Kai|1:12.60;Max|1:17.50;Tia|1:11.80;Ed|1:04.20", 6,
                        "Heat 1 of 3\n  lane 2: Yul 1:19.45\n  lane 3: Gus 1:16.55\n  lane 4: Max 1:17.50\nHeat 2 of 3\n  lane 2: Di 1:15.50\n  lane 3: Kai 1:12.60\n  lane 4: Oda 1:13.30\n  lane 5: Sol 1:15.80\nHeat 3 of 3\n  lane 1: Vic 1:09.00\n  lane 2: Bo 1:05.60\n  lane 3: Ed 1:04.20\n  lane 4: Cam 1:04.40\n  lane 5: Flo 1:06.85\n  lane 6: Tia 1:11.80");
                draw("Sol|1:10.40;Jo|1:01.60;Oda|1:10.85;Bo|1:19.45;Cy|1:13.00;Ann|1:02.75;Ivy|1:07.50;Dot|1:02.50;Di|1:08.65;Lea|1:11.75;Ed|1:05.50", 5,
                        "Heat 1 of 3\n  lane 2: Bo 1:19.45\n  lane 3: Lea 1:11.75\n  lane 4: Cy 1:13.00\nHeat 2 of 3\n  lane 2: Oda 1:10.85\n  lane 3: Di 1:08.65\n  lane 4: Sol 1:10.40\nHeat 3 of 3\n  lane 1: Ivy 1:07.50\n  lane 2: Ann 1:02.75\n  lane 3: Jo 1:01.60\n  lane 4: Dot 1:02.50\n  lane 5: Ed 1:05.50");
                draw("Abe|1:08.95;Yul|1:01.90;Vic|1:07.35;Uma|1:08.90;Tia|1:08.45;Dot|1:04.55", 5,
                        "Heat 1 of 2\n  lane 2: Abe 1:08.95\n  lane 3: Tia 1:08.45\n  lane 4: Uma 1:08.90\nHeat 2 of 2\n  lane 2: Vic 1:07.35\n  lane 3: Yul 1:01.90\n  lane 4: Dot 1:04.55");
                draw("Dot|1:13.30;Max|1:08.80;Cy|1:10.40;Bea|1:15.60;Ivy|1:10.20;Rae|1:06.50;Bo|1:00.50;Uma|1:01.65;Ed|1:01.75;Kai|1:17.30;Cam|1:05.70;Zoe|1:07.85", 10,
                        "Heat 1 of 2\n  lane 4: Kai 1:17.30\n  lane 5: Dot 1:13.30\n  lane 6: Bea 1:15.60\nHeat 2 of 2\n  lane 1: Cy 1:10.40\n  lane 2: Max 1:08.80\n  lane 3: Rae 1:06.50\n  lane 4: Ed 1:01.75\n  lane 5: Bo 1:00.50\n  lane 6: Uma 1:01.65\n  lane 7: Cam 1:05.70\n  lane 8: Zoe 1:07.85\n  lane 9: Ivy 1:10.20");
                draw("Xan|1:06.00;Ed|1:16.55;Oda|1:10.90;Ivy|1:13.55;Zoe|1:12.50;Pia|1:04.65;Wes|1:16.65;Di|1:08.25;Lea|1:02.85;Bea|1:10.55;Cam|1:00.55;Hal|1:03.70;Ann|1:08.55;Dot|1:11.75;Abe|1:09.35;Rae|1:09.50;Bo|1:18.85;Ned|1:15.40;Vic|1:15.65;Jo|1:00.20;Kai|1:14.30", 10,
                        "Heat 1 of 3\n  lane 4: Bo 1:18.85\n  lane 5: Ed 1:16.55\n  lane 6: Wes 1:16.65\nHeat 2 of 3\n  lane 2: Ned 1:15.40\n  lane 3: Ivy 1:13.55\n  lane 4: Dot 1:11.75\n  lane 5: Bea 1:10.55\n  lane 6: Oda 1:10.90\n  lane 7: Zoe 1:12.50\n  lane 8: Kai 1:14.30\n  lane 9: Vic 1:15.65\nHeat 3 of 3\n  lane 1: Abe 1:09.35\n  lane 2: Di 1:08.25\n  lane 3: Pia 1:04.65\n  lane 4: Lea 1:02.85\n  lane 5: Jo 1:00.20\n  lane 6: Cam 1:00.55\n  lane 7: Hal 1:03.70\n  lane 8: Xan 1:06.00\n  lane 9: Ann 1:08.55\n  lane 10: Rae 1:09.50");
                draw("Rae|1:15.85;Bo|1:02.05;Pia|1:13.40;Dot|1:15.25;Ann|1:12.60;Uma|1:07.20;Max|1:09.45;Ed|1:15.90;Bea|1:01.00;Zoe|1:13.80;Kai|1:08.05;Yul|1:10.10;Ned|1:11.15;Cam|1:03.75;Ivy|1:17.55;Wes|1:09.40;Vic|1:09.75;Abe|1:01.80;Di|1:11.65;Flo|1:02.10;Sol|1:15.55;Oda|1:00.55", 10,
                        "Heat 1 of 3\n  lane 4: Ivy 1:17.55\n  lane 5: Rae 1:15.85\n  lane 6: Ed 1:15.90\nHeat 2 of 3\n  lane 1: Sol 1:15.55\n  lane 2: Zoe 1:13.80\n  lane 3: Ann 1:12.60\n  lane 4: Ned 1:11.15\n  lane 5: Vic 1:09.75\n  lane 6: Yul 1:10.10\n  lane 7: Di 1:11.65\n  lane 8: Pia 1:13.40\n  lane 9: Dot 1:15.25\nHeat 3 of 3\n  lane 1: Wes 1:09.40\n  lane 2: Uma 1:07.20\n  lane 3: Flo 1:02.10\n  lane 4: Abe 1:01.80\n  lane 5: Oda 1:00.55\n  lane 6: Bea 1:01.00\n  lane 7: Bo 1:02.05\n  lane 8: Cam 1:03.75\n  lane 9: Kai 1:08.05\n  lane 10: Max 1:09.45");
                draw("Quin|1:08.05;Jo|1:18.70;Lea|1:11.45;Tia|1:02.60;Ed|1:01.10;Vic|1:02.35;Hal|1:17.05;Gus|1:03.60;Ann|1:03.20;Oda|1:00.50;Xan|1:07.45;Zoe|1:11.00;Abe|1:14.65;Pia|1:12.20;Bea|1:06.75;Flo|1:12.00;Wes|1:00.90;Sol|1:19.65;Kai|1:07.80;Uma|1:08.75;Rae|1:13.35;Max|1:12.35;Dot|1:05.25", 7,
                        "Heat 1 of 4\n  lane 3: Sol 1:19.65\n  lane 4: Hal 1:17.05\n  lane 5: Jo 1:18.70\nHeat 2 of 4\n  lane 2: Rae 1:13.35\n  lane 3: Pia 1:12.20\n  lane 4: Lea 1:11.45\n  lane 5: Flo 1:12.00\n  lane 6: Max 1:12.35\n  lane 7: Abe 1:14.65\nHeat 3 of 4\n  lane 1: Zoe 1:11.00\n  lane 2: Quin 1:08.05\n  lane 3: Xan 1:07.45\n  lane 4: Dot 1:05.25\n  lane 5: Bea 1:06.75\n  lane 6: Kai 1:07.80\n  lane 7: Uma 1:08.75\nHeat 4 of 4\n  lane 1: Gus 1:03.60\n  lane 2: Tia 1:02.60\n  lane 3: Ed 1:01.10\n  lane 4: Oda 1:00.50\n  lane 5: Wes 1:00.90\n  lane 6: Vic 1:02.35\n  lane 7: Ann 1:03.20");
                draw("Sol|1:00.35;Ivy|1:18.25;Ned|1:05.15;Flo|1:13.40;Max|1:08.40;Bea|1:15.55;Quin|1:06.30;Lea|1:16.40;Xan|1:18.30;Tia|1:07.05;Hal|1:15.30;Oda|1:05.95;Vic|1:06.45;Ann|1:10.50;Cy|1:09.45", 7,
                        "Heat 1 of 3\n  lane 3: Xan 1:18.30\n  lane 4: Lea 1:16.40\n  lane 5: Ivy 1:18.25\nHeat 2 of 3\n  lane 2: Bea 1:15.55\n  lane 3: Flo 1:13.40\n  lane 4: Cy 1:09.45\n  lane 5: Ann 1:10.50\n  lane 6: Hal 1:15.30\nHeat 3 of 3\n  lane 1: Max 1:08.40\n  lane 2: Vic 1:06.45\n  lane 3: Oda 1:05.95\n  lane 4: Sol 1:00.35\n  lane 5: Ned 1:05.15\n  lane 6: Quin 1:06.30\n  lane 7: Tia 1:07.05");
            });

            Check.test("entries without a time", () -> {
                draw("Ann|1:05.20;Bo|NT;Cy|59.90;Di|NT;Ed|1:05.20", 8,
                        "Heat 1 of 1\n  lane 2: Di NT\n  lane 3: Ed 1:05.20\n  lane 4: Cy 59.90\n  lane 5: Ann 1:05.20\n  lane 6: Bo NT");
                draw("Zed|NT;Amy|NT;Bob|NT", 6,
                        "Heat 1 of 1\n  lane 2: Zed NT\n  lane 3: Amy NT\n  lane 4: Bob NT");
                draw("Zed|NT;Amy|NT;Bob|1:30.00;Cal|NT;Dan|2:01.10;Eve|58.10;Fay|59.00;Gil|59.50;Hal|NT;Ian|1:00.10", 5,
                        "Heat 1 of 2\n  lane 1: Zed NT\n  lane 2: Cal NT\n  lane 3: Dan 2:01.10\n  lane 4: Amy NT\n  lane 5: Hal NT\nHeat 2 of 2\n  lane 1: Bob 1:30.00\n  lane 2: Gil 59.50\n  lane 3: Eve 58.10\n  lane 4: Fay 59.00\n  lane 5: Ian 1:00.10");
            });

            Check.test("equal times are ordered by name", () -> {
                draw("dee|1:00.00;Bob|1:00.00;Cat|1:00.00;Abe|1:00.00;Eli|59.99", 6,
                        "Heat 1 of 1\n  lane 1: dee 1:00.00\n  lane 2: Bob 1:00.00\n  lane 3: Eli 59.99\n  lane 4: Abe 1:00.00\n  lane 5: Cat 1:00.00");
                draw("Ann Lee|1:00.50;Ann  Lee|1:00.50;Ann Li|1:00.50;Bo|1:00.49; Cy |1:00.51", 4,
                        "Heat 1 of 2\n  lane 1: Cy 1:00.51\n  lane 2: Ann Lee 1:00.50\n  lane 3: Ann Li 1:00.50\nHeat 2 of 2\n  lane 2: Bo 1:00.49\n  lane 3: Ann  Lee 1:00.50");
                draw("b|30.00;B2|30.00;a|30.00;A2|30.00;_x|30.00;1|30.00", 4,
                        "Heat 1 of 2\n  lane 1: b 30.00\n  lane 2: _x 30.00\n  lane 3: a 30.00\nHeat 2 of 2\n  lane 1: B2 30.00\n  lane 2: 1 30.00\n  lane 3: A2 30.00");
            });

            Check.test("times are shown rounded to hundredths", () -> {
                draw("A|28.454;B|28.455;C|28.456;D|59.996;E|59.994;F|1:59.999;G|1:00.004;H|1:00.005", 8,
                        "Heat 1 of 1\n  lane 1: H 1:00.01\n  lane 2: D 1:00.00\n  lane 3: C 28.46\n  lane 4: A 28.45\n  lane 5: B 28.46\n  lane 6: E 59.99\n  lane 7: G 1:00.00\n  lane 8: F 2:00.00");
                draw("A|0.001;B|0.004;C|0.005;D|0.01;E|5.3;F|5.30;G|9:59.999;H|10:00", 8,
                        "Heat 1 of 1\n  lane 1: G 10:00.00\n  lane 2: E 5.30\n  lane 3: C 0.01\n  lane 4: A 0.00\n  lane 5: B 0.00\n  lane 6: D 0.01\n  lane 7: F 5.30\n  lane 8: H 10:00.00");
            });

            Check.test("mixed meets", () -> {
                draw("Dot|44.55;Pia|30.55;Vic|35.55;Ned|40.65;Abe|32.90;Bo|41.65;Tia|29.70;Zoe|26.05;Wes|38.15;Sol|43.75;Ivy|32.40;Di|36.90;Xan|29.15;Cam|36.45;Kai|35.60;Quin|31.25;Uma|42.60", 9,
                        "Heat 1 of 2\n  lane 2: Sol 43.75\n  lane 3: Bo 41.65\n  lane 4: Wes 38.15\n  lane 5: Cam 36.45\n  lane 6: Di 36.90\n  lane 7: Ned 40.65\n  lane 8: Uma 42.60\n  lane 9: Dot 44.55\nHeat 2 of 2\n  lane 1: Kai 35.60\n  lane 2: Abe 32.90\n  lane 3: Quin 31.25\n  lane 4: Tia 29.70\n  lane 5: Zoe 26.05\n  lane 6: Xan 29.15\n  lane 7: Pia 30.55\n  lane 8: Ivy 32.40\n  lane 9: Vic 35.55");
                draw("Max|38.35;Bo|NT;Oda|NT;Hal|NT", 6,
                        "Heat 1 of 1\n  lane 2: Hal NT\n  lane 3: Max 38.35\n  lane 4: Bo NT\n  lane 5: Oda NT");
                draw("Yul|1:08.40;Jo|1:12.80;Sol|1:05.90;Ivy|1:18.30;Dot|1:06.30;Abe|1:06.10;Wes|1:19.95;Ned|1:19.90;Zoe|1:08.90;Uma|1:02.65;Hal|NT;Vic|NT", 5,
                        "Heat 1 of 3\n  lane 2: Vic NT\n  lane 3: Wes 1:19.95\n  lane 4: Hal NT\nHeat 2 of 3\n  lane 2: Ivy 1:18.30\n  lane 3: Zoe 1:08.90\n  lane 4: Jo 1:12.80\n  lane 5: Ned 1:19.90\nHeat 3 of 3\n  lane 1: Yul 1:08.40\n  lane 2: Abe 1:06.10\n  lane 3: Uma 1:02.65\n  lane 4: Sol 1:05.90\n  lane 5: Dot 1:06.30");
                draw("Abe|2:22.75;Dot|2:14.50;Yul|2:10.85;Wes|2:22.75;Quin|2:27.30;Pia|2:14.40;Rae|2:29.85;Oda|2:26.50;Kai|2:16.95;Tia|2:29.70;Hal|2:13.45;Uma|2:27.90;Ivy|2:10.80;Sol|2:12.90;Zoe|2:21.40;Xan|2:28.30;Lea|2:26.95", 5,
                        "Heat 1 of 4\n  lane 2: Rae 2:29.85\n  lane 3: Xan 2:28.30\n  lane 4: Tia 2:29.70\nHeat 2 of 4\n  lane 2: Quin 2:27.30\n  lane 3: Oda 2:26.50\n  lane 4: Lea 2:26.95\n  lane 5: Uma 2:27.90\nHeat 3 of 4\n  lane 1: Wes 2:22.75\n  lane 2: Zoe 2:21.40\n  lane 3: Dot 2:14.50\n  lane 4: Kai 2:16.95\n  lane 5: Abe 2:22.75\nHeat 4 of 4\n  lane 1: Pia 2:14.40\n  lane 2: Sol 2:12.90\n  lane 3: Ivy 2:10.80\n  lane 4: Yul 2:10.85\n  lane 5: Hal 2:13.45");
                draw("Max|2:16.95;Wes|2:11.60;Pia|2:22.15;Ivy|2:27.45;Oda|2:17.40;Zoe|2:24.30;Tia|2:29.90;Di|2:10.80;Vic|2:17.90;Abe|2:17.80;Quin|2:28.05;Gus|2:17.40;Hal|2:21.95;Cam|2:19.75;Bo|2:11.70;Jo|2:29.80;Rae|2:19.00", 7,
                        "Heat 1 of 3\n  lane 3: Tia 2:29.90\n  lane 4: Quin 2:28.05\n  lane 5: Jo 2:29.80\nHeat 2 of 3\n  lane 1: Ivy 2:27.45\n  lane 2: Pia 2:22.15\n  lane 3: Cam 2:19.75\n  lane 4: Vic 2:17.90\n  lane 5: Rae 2:19.00\n  lane 6: Hal 2:21.95\n  lane 7: Zoe 2:24.30\nHeat 3 of 3\n  lane 1: Abe 2:17.80\n  lane 2: Gus 2:17.40\n  lane 3: Bo 2:11.70\n  lane 4: Di 2:10.80\n  lane 5: Wes 2:11.60\n  lane 6: Max 2:16.95\n  lane 7: Oda 2:17.40");
                draw("Max|30.45;Tia|36.55;Abe|41.85;Bo|35.50;Rae|32.00;Sol|28.05;Lea|36.10;Quin|NT;Ned|NT", 7,
                        "Heat 1 of 2\n  lane 3: Quin NT\n  lane 4: Abe 41.85\n  lane 5: Ned NT\nHeat 2 of 2\n  lane 2: Lea 36.10\n  lane 3: Rae 32.00\n  lane 4: Sol 28.05\n  lane 5: Max 30.45\n  lane 6: Bo 35.50\n  lane 7: Tia 36.55");
                draw("Yul|39.10;Rae|44.85;Kai|37.90;Jo|32.60;Pia|42.10;Ed|37.70;Dot|31.20;Sol|29.90;Oda|28.35;Cam|26.80;Ivy|38.90;Wes|32.20;Vic|40.50;Cy|30.05", 8,
                        "Heat 1 of 2\n  lane 2: Pia 42.10\n  lane 3: Yul 39.10\n  lane 4: Kai 37.90\n  lane 5: Ivy 38.90\n  lane 6: Vic 40.50\n  lane 7: Rae 44.85\nHeat 2 of 2\n  lane 1: Jo 32.60\n  lane 2: Dot 31.20\n  lane 3: Sol 29.90\n  lane 4: Cam 26.80\n  lane 5: Oda 28.35\n  lane 6: Cy 30.05\n  lane 7: Wes 32.20\n  lane 8: Ed 37.70");
                draw("Hal|2:10.60;Ann|2:28.25;Rae|2:12.90;Di|NT", 6,
                        "Heat 1 of 1\n  lane 2: Ann 2:28.25\n  lane 3: Hal 2:10.60\n  lane 4: Rae 2:12.90\n  lane 5: Di NT");
            });

            Check.test("heats and seats", () -> {
                List<Entry> list = new ArrayList<>();
                for (int i = 1; i <= 10; i++) {
                    list.add(new Entry("S" + (char) ('A' + i), 60000 + i * 100));
                }
                List<Heat> heats = Draw.seed(list, 8);
                Check.eq(2, heats.size());
                Check.eq(1, heats.get(0).number());
                Check.eq(2, heats.get(1).number());
                Check.eq(3, heats.get(0).seats().size());
                Check.eq(7, heats.get(1).seats().size());
                Check.eq(List.of(3, 4, 5), lanes(heats.get(0)));
                Check.eq(List.of(1, 2, 3, 4, 5, 6, 7), lanes(heats.get(1)));
                Check.eq("SK", heats.get(0).seats().get(0).entry().name());
                Check.eq("SI", heats.get(0).seats().get(1).entry().name());
                Check.eq("SJ", heats.get(0).seats().get(2).entry().name());
                Check.eq("SH", heats.get(1).seats().get(0).entry().name());
                Check.eq("SB", heats.get(1).seats().get(3).entry().name());
                Check.eq(List.of(), Draw.seed(new ArrayList<>(), 8));
                Check.eq("no entries", Draw.format(new ArrayList<>()));
            });

            Check.test("seed validates", () -> {
                List<Entry> dup = List.of(new Entry("Ann", 60000), new Entry("ann", 61000));
                Check.raises(IllegalArgumentException.class, () -> Draw.seed(dup, 8));
                Check.raises(IllegalArgumentException.class, () -> Draw.seed(List.of(new Entry("Ann", 60000), Entry.noTime(" ANN ")), 8));
                Check.raises(IllegalArgumentException.class, () -> Draw.seed(List.of(new Entry("Ann", 60000)), 3));
                Check.raises(IllegalArgumentException.class, () -> Draw.seed(List.of(new Entry("Ann", 60000)), 11));
                Check.raises(IllegalArgumentException.class, () -> Draw.seed(new ArrayList<>(), 2));
                Check.eq(1, Draw.seed(List.of(new Entry("Ann", 60000), new Entry("Anna", 60000)), 4).size());
            });
        }

        static List<Integer> lanes(Heat heat) {
            List<Integer> out = new ArrayList<>();
            for (Seat s : heat.seats()) {
                out.add(s.lane());
            }
            return out;
        }
    }
''')

LIB = Lib(
    name="lanedraw", lang="java", title="the lanedraw library",
    blurb="The swim club's meet software reads entry times and builds the heats and lanes with lanedraw.",
    files={
        "src/meet/Times.java": TIMES, "src/meet/Entry.java": ENTRY, "src/meet/Seat.java": SEAT, "src/meet/Heat.java": HEAT, "src/meet/Draw.java": DRAW,
        "README.md": README, ".gitignore": "build/\n",
    },
    visible_tests={"test/Check.java": JAVA_CHECK, "test/BasicTests.java": BASIC, "test/TestMain.java": java_test_main("BasicTests")},
    hidden_tests={"test/FullTests.java": FULL, "test/TestMain.java": java_test_main("BasicTests", "FullTests")},
    mutate=["src/meet/Draw.java", "src/meet/Times.java", "src/meet/Entry.java"], difficulty=2, tags=["sports", "seeding", "parsing"],
    probe_import="import meet.*;",
    probes=[
        "Times.parse(\"1:05.20\")",
        "Times.parse(\"5.3\")",
        "Times.parse(\"1:05.257\")",
        "Times.parse(\"60.00\")",
        "Times.parse(\"0\")",
        "Times.parse(\"1:5\")",
        "Times.format(65200)",
        "Times.format(28455)",
        "Times.format(59996)",
        "Times.format(5300)",
        "Times.format(3665000)",
        "Draw.laneOrder(8)",
        "Draw.laneOrder(5)",
        "Draw.laneOrder(10)",
        "Draw.laneOrder(3)",
        "Draw.format(Draw.seed(java.util.List.of(Entry.of(\"Ann\", \"1:05.20\"), Entry.of(\"Bo\", \"NT\"), Entry.of(\"Cy\", \"59.90\")), 8))",
        "Draw.format(Draw.seed(java.util.List.of(Entry.of(\"A\", \"30.1\"), Entry.of(\"B\", \"30.2\"), Entry.of(\"C\", \"30.3\"), Entry.of(\"D\", \"30.4\"), Entry.of(\"E\", \"30.5\")), 4))",
        "Draw.format(Draw.seed(java.util.List.of(Entry.of(\"dee\", \"1:00.00\"), Entry.of(\"Bob\", \"1:00.00\"), Entry.of(\"Abe\", \"1:00.00\")), 6))",
        "Draw.format(java.util.List.of())",
    ],
)

register_libs([LIB], n=8)
