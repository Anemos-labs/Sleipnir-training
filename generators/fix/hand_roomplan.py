"""A layered java conference scheduler (slots, sessions, schedule, CSV report and import). Defects sit in a different class than
the symptom; review tickets combine causes."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, combo, tasks_from

README = dd('''
    # roomplan

    Scheduling of conference sessions in rooms (Java, package `plan`: `Slot`, `Session`, `Schedule`, `Report`, `Importer`; tests: `tests/TestMain.java`).

    ## Slot

    A slot is the half-open interval `[start, end)` in minutes since midnight (`0 <= start < end <= 1440`, otherwise `IllegalArgumentException`).
    Slots that only touch (one ends when the other starts) do **not** overlap. `Slot.parse("09:00-10:30")` reads the text form (also accepted
    with spaces around the parts); `toString()` is `09:00-10:30`. Slots are immutable, equal when start and end are equal, and ordered by start, then end.

    ## Schedule

    * `addRoom(name, seats)` registers a room (`seats > 0`). `add(id, title, speaker, room, slot, registered)` adds a session and returns it.
      Ids are unique (`IllegalArgumentException("duplicate session id N")`), the room must exist (`IllegalArgumentException("unknown room X")`),
      `registered` may not exceed the seats (`CapacityException`: exactly the seats is fine).
    * A session conflicts (`ConflictException`, nothing is added) with another session that overlaps in time and is in the same room, or has the same speaker
      *in any room*. Speakers are compared ignoring case and surrounding spaces; an empty speaker never conflicts. Room conflicts are checked first.
    * `move(id, slot)` gives the session a new slot with the same checks against all *other* sessions. On any failure nothing changes. Unknown id:
      `NoSuchElementException`.
    * `remove(id)` removes the session with that id (`NoSuchElementException` if there is none). Ids are arbitrary numbers, not positions.
    * `all()` lists the sessions by start, then room name, then id. `inRoom(room)` by start. `at(room, minute)` is the session of that room that is
      running at that minute (`start <= minute < end`), as an `Optional`.
    * `copy()` returns an independent schedule: changing the copy never changes the original, and the other way round.

    ## Report and Importer

    * `Report.csv(schedule)`: the header `id,title,speaker,room,start,end,fill`, then one line per session in the order of `all()`. A field containing a
      comma, a double quote or a newline is quoted, quotes inside doubled. `start` and `end` are `HH:MM`. `fill` is the registered share of the seats as a
      percentage with one decimal, rounded half up, always with a decimal point (`83.3`), whatever the default locale of the machine is.
    * `Importer.parse(text)` reads lines `id,title,room,start,end,registered,speaker` (the speaker may be empty, so the line can end with a comma;
      `start` and `end` are `HH:MM`) into `Importer.Row` objects (public fields `id`, `title`, `room`, `slot`, `registered`, `speaker`). Fields may be
      quoted (with `""` for a quote inside). Blank lines are skipped and `\\r\\n` line ends are fine. A bad line is an `IllegalArgumentException` whose
      message starts with `line N:` (N counts all physical lines, 1-based).
''')

SLOT = dd('''
    package plan;

    /** A half-open time slot [start, end) in minutes since midnight. */
    public final class Slot implements Comparable<Slot> {
        private final int start;
        private final int end;

        public Slot(int start, int end) {
            if (start < 0 || end > 24 * 60 || start >= end) {
                throw new IllegalArgumentException("bad slot " + start + "-" + end);
            }
            this.start = start;
            this.end = end;
        }

        public static Slot parse(String text) {
            String[] parts = text.trim().split("-");
            if (parts.length != 2) {
                throw new IllegalArgumentException("bad slot " + text);
            }
            return new Slot(minutes(parts[0]), minutes(parts[1]));
        }

        /** "09:30" to minutes since midnight. */
        public static int minutes(String hhmm) {
            String t = hhmm.trim();
            if (!t.matches("\\\\d{1,2}:\\\\d{2}")) {
                throw new IllegalArgumentException("bad time " + hhmm);
            }
            int colon = t.indexOf(':');
            int h = Integer.parseInt(t.substring(0, colon));
            int m = Integer.parseInt(t.substring(colon + 1));
            if (m > 59 || h > 24 || (h == 24 && m > 0)) {
                throw new IllegalArgumentException("bad time " + hhmm);
            }
            return h * 60 + m;
        }

        public static String hhmm(int minutes) {
            return String.format("%02d:%02d", minutes / 60, minutes % 60);
        }

        public int start() {
            return start;
        }

        public int end() {
            return end;
        }

        public int length() {
            return end - start;
        }

        public boolean overlaps(Slot other) {
            return start < other.end && other.start < end;
        }

        public Slot shift(int minutes) {
            return new Slot(start + minutes, end + minutes);
        }

        @Override
        public boolean equals(Object o) {
            if (!(o instanceof Slot)) {
                return false;
            }
            Slot other = (Slot) o;
            return start == other.start && end == other.end;
        }

        @Override
        public int hashCode() {
            return 31 * start + end;
        }

        @Override
        public int compareTo(Slot other) {
            return start != other.start ? Integer.compare(start, other.start) : Integer.compare(end, other.end);
        }

        @Override
        public String toString() {
            return hhmm(start) + "-" + hhmm(end);
        }
    }
''')

SESSION = dd('''
    package plan;

    /** An immutable session. */
    public final class Session {
        private final int id;
        private final String title;
        private final String speaker;
        private final String room;
        private final Slot slot;
        private final int registered;

        public Session(int id, String title, String speaker, String room, Slot slot, int registered) {
            this.id = id;
            this.title = title;
            this.speaker = speaker;
            this.room = room;
            this.slot = slot;
            this.registered = registered;
        }

        public int id() {
            return id;
        }

        public String title() {
            return title;
        }

        public String speaker() {
            return speaker;
        }

        public String room() {
            return room;
        }

        public Slot slot() {
            return slot;
        }

        public int registered() {
            return registered;
        }

        public Session withSlot(Slot newSlot) {
            return new Session(id, title, speaker, room, newSlot, registered);
        }

        @Override
        public String toString() {
            return "#" + id + " " + title + " [" + room + " " + slot + "]";
        }
    }
''')

EXC = {
    "src/plan/ConflictException.java": dd('''
        package plan;

        public class ConflictException extends RuntimeException {
            public ConflictException(String message) {
                super(message);
            }
        }
    '''),
    "src/plan/CapacityException.java": dd('''
        package plan;

        public class CapacityException extends RuntimeException {
            public CapacityException(String message) {
                super(message);
            }
        }
    '''),
}

SCHEDULE = dd('''
    package plan;

    import java.util.ArrayList;
    import java.util.Comparator;
    import java.util.List;
    import java.util.Map;
    import java.util.NoSuchElementException;
    import java.util.Optional;
    import java.util.TreeMap;

    /** Sessions in rooms; no room and no speaker is booked twice at the same time. */
    public class Schedule {
        private final Map<String, Integer> seats = new TreeMap<>();
        private List<Session> sessions = new ArrayList<>();

        public void addRoom(String name, int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("a room needs seats");
            }
            seats.put(name, capacity);
        }

        public int capacityOf(String room) {
            Integer c = seats.get(room);
            if (c == null) {
                throw new IllegalArgumentException("unknown room " + room);
            }
            return c;
        }

        public Session add(int id, String title, String speaker, String room, Slot slot, int registered) {
            if (find(id) != null) {
                throw new IllegalArgumentException("duplicate session id " + id);
            }
            Session s = new Session(id, title, speaker == null ? "" : speaker.trim(), room, slot, registered);
            check(s);
            sessions.add(s);
            return s;
        }

        public Session move(int id, Slot slot) {
            Session old = find(id);
            if (old == null) {
                throw new NoSuchElementException("no session " + id);
            }
            Session moved = old.withSlot(slot);
            check(moved);
            sessions.set(sessions.indexOf(old), moved);
            return moved;
        }

        public void remove(int id) {
            if (!sessions.removeIf(s -> s.id() == id)) {
                throw new NoSuchElementException("no session " + id);
            }
        }

        public Session get(int id) {
            Session s = find(id);
            if (s == null) {
                throw new NoSuchElementException("no session " + id);
            }
            return s;
        }

        public List<Session> all() {
            List<Session> out = new ArrayList<>(sessions);
            out.sort(Comparator.comparingInt((Session s) -> s.slot().start()).thenComparing(Session::room).thenComparingInt(Session::id));
            return out;
        }

        public List<Session> inRoom(String room) {
            List<Session> out = new ArrayList<>();
            for (Session s : sessions) {
                if (s.room().equals(room)) {
                    out.add(s);
                }
            }
            out.sort(Comparator.comparing(Session::slot));
            return out;
        }

        public Optional<Session> at(String room, int minute) {
            for (Session s : sessions) {
                if (s.room().equals(room) && s.slot().start() <= minute && minute < s.slot().end()) {
                    return Optional.of(s);
                }
            }
            return Optional.empty();
        }

        public Schedule copy() {
            Schedule c = new Schedule();
            c.seats.putAll(seats);
            c.sessions = new ArrayList<>(sessions);
            return c;
        }

        private Session find(int id) {
            for (Session s : sessions) {
                if (s.id() == id) {
                    return s;
                }
            }
            return null;
        }

        private void check(Session s) {
            int capacity = capacityOf(s.room());
            if (s.registered() > capacity) {
                throw new CapacityException(s.registered() + " registered for " + capacity + " seats in " + s.room());
            }
            for (Session o : sessions) {
                if (o.id() == s.id() || !o.slot().overlaps(s.slot())) {
                    continue;
                }
                if (o.room().equals(s.room())) {
                    throw new ConflictException("room " + s.room() + " busy " + o.slot() + " (session " + o.id() + ")");
                }
            }
            for (Session o : sessions) {
                if (o.id() == s.id() || !o.slot().overlaps(s.slot())) {
                    continue;
                }
                if (!s.speaker().isEmpty() && o.speaker().equalsIgnoreCase(s.speaker())) {
                    throw new ConflictException("speaker " + s.speaker() + " busy " + o.slot() + " (session " + o.id() + ")");
                }
            }
        }
    }
''')

REPORT = dd('''
    package plan;

    import java.util.Locale;

    /** CSV report of a schedule. */
    public final class Report {
        private Report() {
        }

        public static String csv(Schedule schedule) {
            StringBuilder sb = new StringBuilder("id,title,speaker,room,start,end,fill\\n");
            for (Session s : schedule.all()) {
                sb.append(s.id()).append(',')
                        .append(quote(s.title())).append(',')
                        .append(quote(s.speaker())).append(',')
                        .append(quote(s.room())).append(',')
                        .append(Slot.hhmm(s.slot().start())).append(',')
                        .append(Slot.hhmm(s.slot().end())).append(',')
                        .append(fill(s.registered(), schedule.capacityOf(s.room())))
                        .append('\\n');
            }
            return sb.toString();
        }

        static String quote(String value) {
            if (value.indexOf(',') >= 0 || value.indexOf('"') >= 0 || value.indexOf('\\n') >= 0) {
                return '"' + value.replace("\\"", "\\"\\"") + '"';
            }
            return value;
        }

        static String fill(int registered, int seats) {
            return String.format(Locale.ROOT, "%.1f", registered * 100.0 / seats);
        }
    }
''')

IMPORTER = dd('''
    package plan;

    import java.util.ArrayList;
    import java.util.List;

    /** Reads sessions from CSV text. */
    public final class Importer {
        private Importer() {
        }

        public static final class Row {
            public final int id;
            public final String title;
            public final String room;
            public final Slot slot;
            public final int registered;
            public final String speaker;

            Row(int id, String title, String room, Slot slot, int registered, String speaker) {
                this.id = id;
                this.title = title;
                this.room = room;
                this.slot = slot;
                this.registered = registered;
                this.speaker = speaker;
            }
        }

        public static List<Row> parse(String text) {
            List<Row> rows = new ArrayList<>();
            String[] lines = text.split("\\r?\\n", -1);
            for (int i = 0; i < lines.length; i++) {
                if (lines[i].trim().isEmpty()) {
                    continue;
                }
                try {
                    rows.add(row(fields(lines[i])));
                } catch (IllegalArgumentException e) {
                    throw new IllegalArgumentException("line " + (i + 1) + ": " + e.getMessage());
                }
            }
            return rows;
        }

        private static Row row(List<String> f) {
            if (f.size() != 7) {
                throw new IllegalArgumentException("want 7 fields, got " + f.size());
            }
            int id;
            int registered;
            try {
                id = Integer.parseInt(f.get(0).trim());
                registered = Integer.parseInt(f.get(5).trim());
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException("bad number");
            }
            Slot slot = new Slot(Slot.minutes(f.get(3)), Slot.minutes(f.get(4)));
            return new Row(id, f.get(1), f.get(2), slot, registered, f.get(6).trim());
        }

        /** Splits one CSV line; quoted fields may contain commas and doubled quotes. */
        static List<String> fields(String line) {
            List<String> out = new ArrayList<>();
            StringBuilder cur = new StringBuilder();
            boolean quoted = false;
            for (int i = 0; i < line.length(); i++) {
                char c = line.charAt(i);
                if (quoted) {
                    if (c == '"') {
                        if (i + 1 < line.length() && line.charAt(i + 1) == '"') {
                            cur.append('"');
                            i++;
                        } else {
                            quoted = false;
                        }
                    } else {
                        cur.append(c);
                    }
                } else if (c == '"') {
                    quoted = true;
                } else if (c == ',') {
                    out.add(cur.toString());
                    cur.setLength(0);
                } else {
                    cur.append(c);
                }
            }
            out.add(cur.toString());
            return out;
        }
    }
''')

VISIBLE = {
    "tests/TestMain.java": dd('''
        import plan.ConflictException;
        import plan.Schedule;
        import plan.Slot;

        public class TestMain {
            public static void main(String[] args) {
                Schedule s = new Schedule();
                s.addRoom("Hall A", 100);
                s.add(1, "Opening", "Ann", "Hall A", Slot.parse("09:00-10:00"), 80);
                boolean clash = false;
                try {
                    s.add(2, "Same room", "Bob", "Hall A", Slot.parse("09:30-10:30"), 10);
                } catch (ConflictException e) {
                    clash = true;
                }
                if (!clash) {
                    System.out.println("FAIL expected a room conflict");
                    System.exit(1);
                }
                if (!Slot.parse("09:00-10:30").toString().equals("09:00-10:30") || s.all().size() != 1) {
                    System.out.println("FAIL slot text or list");
                    System.exit(1);
                }
                System.out.println("all checks passed");
            }
        }
    '''),
}

HIDDEN = {
    "tests/TestMain.java": dd('''
        import java.util.ArrayList;
        import java.util.List;
        import java.util.Locale;
        import java.util.NoSuchElementException;
        import java.util.Optional;
        import plan.CapacityException;
        import plan.ConflictException;
        import plan.Importer;
        import plan.Report;
        import plan.Schedule;
        import plan.Session;
        import plan.Slot;

        public class TestMain {
            static int failures = 0;

            static void check(String what, boolean ok) {
                if (!ok) {
                    failures++;
                    System.out.println("FAIL " + what);
                }
            }

            static Slot slot(String s) {
                return Slot.parse(s);
            }

            static Schedule base() {
                Schedule s = new Schedule();
                s.addRoom("Hall A", 100);
                s.addRoom("Room B", 30);
                return s;
            }

            static List<Integer> ids(List<Session> list) {
                List<Integer> out = new ArrayList<>();
                for (Session s : list) {
                    out.add(s.id());
                }
                return out;
            }

            static String thrown(Runnable r) {
                try {
                    r.run();
                } catch (RuntimeException e) {
                    return e.getClass().getSimpleName() + ": " + e.getMessage();
                }
                return "nothing";
            }

            public static void main(String[] args) {
                // ---- slots
                check("slots that touch do not overlap", !slot("09:00-10:00").overlaps(slot("10:00-11:00")) && !slot("10:00-11:00").overlaps(slot("09:00-10:00")));
                check("slots that share a minute overlap", slot("09:00-10:01").overlaps(slot("10:00-11:00")) && slot("09:30-09:45").overlaps(slot("09:00-10:00")));
                check("equal slots overlap", slot("09:00-10:00").overlaps(slot("09:00-10:00")));
                check("slot text", slot(" 9:05 - 10:30 ").toString().equals("09:05-10:30"));
                check("slot equality and order", slot("09:00-10:00").equals(slot("09:00-10:00")) && slot("09:00-10:00").hashCode() == slot("09:00-10:00").hashCode()
                        && slot("09:00-10:00").compareTo(slot("09:00-11:00")) < 0 && slot("10:00-10:30").compareTo(slot("09:00-12:00")) > 0);
                for (String bad : new String[] {"10:00-09:00", "09:00-09:00", "09:00", "9-10", "09:00-25:00", "09:60-10:00", "-1:00-10:00"}) {
                    check("bad slot " + bad, thrown(() -> Slot.parse(bad)).startsWith("IllegalArgumentException"));
                }
                check("a slot may end at midnight", slot("23:00-24:00").length() == 60);

                // ---- adding
                Schedule s = base();
                s.add(1, "Opening", "Ann", "Hall A", slot("09:00-10:00"), 80);
                check("same room, overlapping", thrown(() -> s.add(2, "X", "Bob", "Hall A", slot("09:30-10:30"), 5))
                        .equals("ConflictException: room Hall A busy 09:00-10:00 (session 1)"));
                check("touching in the same room is fine", thrown(() -> s.add(2, "X", "Bob", "Hall A", slot("10:00-11:00"), 5)).equals("nothing"));
                check("speaker in another room at the same time", thrown(() -> s.add(4, "Z", "Ann", "Room B", slot("09:30-10:30"), 5))
                        .equals("ConflictException: speaker Ann busy 09:00-10:00 (session 1)"));
                check("speaker names ignore case and spaces", thrown(() -> s.add(4, "Z", "  ANN ", "Room B", slot("09:30-10:30"), 5))
                        .equals("ConflictException: speaker ANN busy 09:00-10:00 (session 1)"));
                check("other room, same time, other speaker", thrown(() -> s.add(3, "Y", "Cy", "Room B", slot("09:00-10:00"), 5)).equals("nothing"));
                check("an empty speaker never conflicts", thrown(() -> s.add(5, "Break", "", "Room B", slot("12:00-13:00"), 0)).equals("nothing")
                        && thrown(() -> s.add(6, "Break 2", null, "Hall A", slot("12:00-13:00"), 0)).equals("nothing")
                        && thrown(() -> s.add(7, "Break 3", " ", "Hall A", slot("14:00-15:00"), 0)).equals("nothing")
                        && thrown(() -> s.add(8, "Break 4", "", "Room B", slot("14:00-15:00"), 0)).equals("nothing"));
                check("room conflict is reported before speaker conflict", thrown(() -> s.add(9, "Both", "Ann", "Hall A", slot("09:00-10:00"), 5))
                        .startsWith("ConflictException: room Hall A"));
                check("duplicate ids", thrown(() -> s.add(1, "Again", "Dee", "Room B", slot("16:00-17:00"), 1)).equals("IllegalArgumentException: duplicate session id 1"));
                check("unknown room", thrown(() -> s.add(10, "Lost", "Dee", "Attic", slot("16:00-17:00"), 1)).equals("IllegalArgumentException: unknown room Attic"));
                check("failed adds add nothing", s.all().size() == 7);
                check("capacity: exactly the seats", thrown(() -> s.add(11, "Full", "Eve", "Room B", slot("16:00-17:00"), 30)).equals("nothing"));
                check("capacity: one more", thrown(() -> s.add(12, "Over", "Fay", "Room B", slot("17:00-18:00"), 31)).startsWith("CapacityException"));

                // ---- moving
                Schedule m = base();
                m.add(1, "Talk", "Ann", "Hall A", slot("09:00-10:00"), 10);
                m.add(2, "Other", "Bob", "Hall A", slot("11:00-12:00"), 10);
                check("nudging a session by a few minutes works", thrown(() -> m.move(1, slot("09:15-10:15"))).equals("nothing") && m.get(1).slot().equals(slot("09:15-10:15")));
                check("moving onto another session fails", thrown(() -> m.move(1, slot("10:30-11:30"))).equals("ConflictException: room Hall A busy 11:00-12:00 (session 2)"));
                check("a failed move changes nothing", m.get(1).slot().equals(slot("09:15-10:15")) && m.inRoom("Hall A").size() == 2 && ids(m.all()).equals(List.of(1, 2)));
                Schedule sp = base();
                sp.add(1, "A1", "Ann", "Hall A", slot("09:00-10:00"), 1);
                sp.add(2, "A2", "Ann", "Room B", slot("11:00-12:00"), 1);
                check("moving into a speaker clash fails", thrown(() -> sp.move(2, slot("09:30-10:30"))).startsWith("ConflictException: speaker Ann"));
                check("and changes nothing", sp.get(2).slot().equals(slot("11:00-12:00")) && ids(sp.all()).equals(List.of(1, 2)));
                check("moving an unknown session", thrown(() -> m.move(99, slot("08:00-09:00"))).startsWith("NoSuchElementException"));

                // ---- removing and ordering
                Schedule r = base();
                r.add(30, "Third", "A", "Hall A", slot("11:00-12:00"), 1);
                r.add(10, "First", "B", "Hall A", slot("09:00-10:00"), 1);
                r.add(20, "Second", "C", "Hall A", slot("10:00-11:00"), 1);
                r.add(5, "Fourth", "D", "Hall A", slot("12:00-13:00"), 1);
                check("remove by id", thrown(() -> r.remove(10)).equals("nothing"));
                check("remove by id, not by position", ids(r.all()).equals(List.of(20, 30, 5)));
                check("remove the last id", thrown(() -> r.remove(5)).equals("nothing") && ids(r.all()).equals(List.of(20, 30)));
                check("remove an unknown id", thrown(() -> r.remove(1)).startsWith("NoSuchElementException") && thrown(() -> r.remove(2)).startsWith("NoSuchElementException")
                        && ids(r.all()).equals(List.of(20, 30)));
                Schedule o2 = base();
                o2.addRoom("Hall A2", 5);
                o2.add(7, "p", "p7", "Room B", slot("09:00-10:00"), 1);
                o2.add(4, "q", "p4", "Hall A", slot("09:00-10:00"), 1);
                o2.add(6, "r", "p6", "Hall A2", slot("09:00-10:00"), 1);
                o2.add(2, "s", "p2", "Room B", slot("10:00-11:00"), 1);
                o2.add(1, "t", "p1", "Hall A", slot("08:00-09:00"), 1);
                check("all(): start, then room", ids(o2.all()).equals(List.of(1, 4, 6, 7, 2)));
                Schedule o3 = new Schedule();
                o3.addRoom("R", 10);
                o3.add(5, "five", "x5", "R", slot("11:00-12:00"), 1);
                o3.add(2, "two", "x2", "R", slot("09:00-10:00"), 1);
                check("inRoom sorted by start", ids(o3.inRoom("R")).equals(List.of(2, 5)) && o3.inRoom("nowhere").isEmpty());
                Schedule ties = base();
                ties.addRoom("Same", 10);
                ties.add(9, "n1", "q1", "Same", slot("09:00-10:00"), 1);
                ties.add(3, "n2", "q2", "Room B", slot("09:00-10:00"), 1);
                ties.add(4, "n3", "q3", "Hall A", slot("09:00-10:00"), 1);
                check("room names order the ties", ids(ties.all()).equals(List.of(4, 3, 9)));

                // ---- at()
                Schedule a = base();
                a.add(1, "t", "x", "Hall A", slot("09:00-10:00"), 1);
                a.add(2, "u", "y", "Hall A", slot("10:00-11:00"), 1);
                Optional<Session> at = a.at("Hall A", 9 * 60);
                check("at the first minute", at.isPresent() && at.get().id() == 1);
                check("at the last minute", a.at("Hall A", 10 * 60 - 1).get().id() == 1);
                check("at the end minute belongs to the next session", a.at("Hall A", 10 * 60).get().id() == 2);
                check("at after the last session", a.at("Hall A", 11 * 60).isEmpty() && a.at("Hall A", 8 * 60).isEmpty() && a.at("Room B", 9 * 60).isEmpty());

                // ---- copies
                Schedule orig = base();
                orig.add(1, "t", "x", "Hall A", slot("09:00-10:00"), 1);
                Schedule cp = orig.copy();
                cp.add(2, "u", "y", "Hall A", slot("10:00-11:00"), 1);
                cp.move(1, slot("08:00-09:00"));
                cp.remove(1);
                check("changes to the copy do not reach the original", orig.all().size() == 1 && orig.get(1).slot().equals(slot("09:00-10:00")));
                orig.add(3, "v", "z", "Room B", slot("09:00-10:00"), 1);
                check("changes to the original do not reach the copy", cp.all().size() == 1 && ids(cp.all()).equals(List.of(2)));
                check("a copy knows the rooms", thrown(() -> cp.add(4, "w", "q", "Room B", slot("12:00-13:00"), 1)).equals("nothing"));

                // ---- report
                Schedule rep = base();
                rep.add(2, "Say \\"hi\\"", "Bob, Jr.", "Room B", slot("10:00-11:15"), 25);
                rep.add(1, "Opening", "", "Hall A", slot("09:00-10:00"), 1);
                rep.add(3, "Closing", "Ann", "Hall A", slot("17:30-18:00"), 100);
                String expected = "id,title,speaker,room,start,end,fill\\n"
                        + "1,Opening,,Hall A,09:00,10:00,1.0\\n"
                        + "2,\\"Say \\"\\"hi\\"\\"\\",\\"Bob, Jr.\\",Room B,10:00,11:15,83.3\\n"
                        + "3,Closing,Ann,Hall A,17:30,18:00,100.0\\n";
                check("csv", Report.csv(rep).equals(expected));
                Locale saved = Locale.getDefault();
                Locale.setDefault(Locale.GERMANY);
                String german = Report.csv(rep);
                Locale.setDefault(saved);
                check("csv does not depend on the default locale", german.equals(expected));
                Schedule round = new Schedule();
                round.addRoom("R", 3);
                round.add(1, "a", "x", "R", slot("09:00-10:00"), 1);
                round.add(2, "b", "y", "R", slot("10:00-11:00"), 2);
                check("fill rounds half up with one decimal", Report.csv(round).endsWith("1,a,x,R,09:00,10:00,33.3\\n2,b,y,R,10:00,11:00,66.7\\n"));
                Schedule half = new Schedule();
                half.addRoom("H", 8);
                half.add(1, "a", "x", "H", slot("09:00-10:00"), 1);
                check("fill 12.5", Report.csv(half).endsWith(",12.5\\n"));
                Schedule newline = new Schedule();
                newline.addRoom("N", 10);
                newline.add(1, "two\\nlines", "x", "N", slot("09:00-10:00"), 5);
                check("a newline forces quotes", Report.csv(newline).contains(",\\"two\\nlines\\","));

                // ---- import
                String csv = "1,Opening,Hall A,09:00,10:00,80,Ann\\r\\n"
                        + "\\r\\n"
                        + "2,\\"Say \\"\\"hi\\"\\", loudly\\",Room B,10:15,11:00,25,\\"Bob, Jr.\\"\\r\\n"
                        + "3,Break,Hall A,12:00,13:00,0,\\n";
                List<Importer.Row> rows = Importer.parse(csv);
                check("three rows", rows.size() == 3);
                check("row 1", rows.get(0).id == 1 && rows.get(0).title.equals("Opening") && rows.get(0).room.equals("Hall A")
                        && rows.get(0).slot.equals(slot("09:00-10:00")) && rows.get(0).registered == 80 && rows.get(0).speaker.equals("Ann"));
                check("quotes, commas and doubled quotes", rows.get(1).title.equals("Say \\"hi\\", loudly") && rows.get(1).speaker.equals("Bob, Jr."));
                check("an empty last field is kept", rows.get(2).speaker.equals("") && rows.get(2).slot.equals(slot("12:00-13:00")));
                check("no rows for empty text", Importer.parse("").isEmpty() && Importer.parse("\\n\\n").isEmpty());
                check("import line numbers", thrown(() -> Importer.parse("1,a,R,09:00,10:00,1,x\\n\\n\\n2,b,R,09:00,10:00\\n")).equals("IllegalArgumentException: line 4: want 7 fields, got 5"));
                check("import bad number", thrown(() -> Importer.parse("x,a,R,09:00,10:00,1,x")).equals("IllegalArgumentException: line 1: bad number"));
                check("import bad time", thrown(() -> Importer.parse("1,a,R,9:00,25:00,1,x")).startsWith("IllegalArgumentException: line 1: bad time"));
                check("import reversed slot", thrown(() -> Importer.parse("1,a,R,10:00,09:00,1,x")).startsWith("IllegalArgumentException: line 1: bad slot"));

                if (failures > 0) {
                    System.exit(1);
                }
                System.out.println("all checks passed");
            }
        }
    '''),
}


def _prompts() -> dict:
    p = {}
    p["touching"] = (
        "The planner refuses to put a talk directly after another one in the same room: a 10:00-11:00 session is rejected next to 09:00-10:00 "
        "(`room Hall A busy 09:00-10:00`), although nobody is in the room at 10:00."
    )
    p["speaker"] = (
        "Ann was scheduled in Hall A and in Room B for the same hour and the planner accepted both. A speaker cannot be in two rooms at once."
    )
    p["case"] = "`Ann` and `ANN` (same person, typed differently by two organisers) were both scheduled for the same hour in different rooms."
    p["self"] = (
        "Nudging a session by a quarter of an hour (09:00-10:00 to 09:15-10:15) is refused with `room Hall A busy 09:00-10:00 (session 1)` - "
        "that is the session itself. Moving it to a free time far away works."
    )
    p["move-first"] = (
        "After a refused move the session was nevertheless at its new time in the list (the error message was right), so two sessions then "
        "overlapped in the same room. A refused move must leave everything as it was."
    )
    p["remove"] = (
        "Removing session 20 from the planner removes some other session, and removing session 30 crashes with an IndexOutOfBoundsException. "
        "Session ids are arbitrary numbers, not positions."
    )
    p["copy"] = (
        "The 'what if' planning view edits a copy of the schedule, but every move and removal there also changes the live schedule, and "
        "sessions added to the live one appear in the draft."
    )
    p["order"] = (
        "Sessions that start at the same time are listed in the order they were entered, not by room name as the README says, so the printed "
        "programme changes whenever organisers add sessions in a different order."
    )
    p["capacity"] = "A session with exactly as many registrations as seats (30 of 30) is rejected as over capacity."
    p["at"] = "The door display keeps showing the session that ended at 10:00 until 10:01, and the next one only appears a minute late."
    p["locale"] = (
        "The CSV report generated on our German server has decimal commas in the fill column (`83,3`), which breaks the import into our BI tool "
        "and shifts the columns. The same report from the UK server is fine."
    )
    p["fill-int"] = "The `fill` column of the report shows 83.0 for 25 of 30 seats (and 33.0 for 1 of 3) instead of 83.3 and 33.3."
    p["quote"] = (
        "Speaker names like `Bob, Jr.` shift the columns of the report in our spreadsheet: the field is not quoted. Titles with quotes are fine."
    )
    p["trailing"] = (
        "Importing a schedule where the speaker is not decided yet (the line simply ends with a comma) fails with `line 3: want 7 fields, got 6`."
    )
    p["quotes-in"] = "Titles with doubled quotes lose their quotes on import: `\"Say \"\"hi\"\"\"` becomes `Say hi`, but the report writes them correctly."
    return p


def _base() -> Base:
    P = _prompts()
    good = {
        "README.md": README, "src/plan/Slot.java": SLOT, "src/plan/Session.java": SESSION, "src/plan/Schedule.java": SCHEDULE,
        "src/plan/Report.java": REPORT, "src/plan/Importer.java": IMPORTER, **EXC,
    }
    sl, sc, rp, im = "src/plan/Slot.java", "src/plan/Schedule.java", "src/plan/Report.java", "src/plan/Importer.java"
    touching = ("        return start < other.end && other.start < end;\n", "        return start <= other.end && other.start <= end;\n")
    speaker = ("        for (Session o : sessions) {\n            if (o.id() == s.id() || !o.slot().overlaps(s.slot())) {\n                continue;\n            }\n            if (!s.speaker().isEmpty() && o.speaker().equalsIgnoreCase(s.speaker())) {\n                throw new ConflictException(\"speaker \" + s.speaker() + \" busy \" + o.slot() + \" (session \" + o.id() + \")\");\n            }\n        }\n", "")
    case = ("o.speaker().equalsIgnoreCase(s.speaker())", "o.speaker().equals(s.speaker())")
    self_ = ("        for (Session o : sessions) {\n            if (o.id() == s.id() || !o.slot().overlaps(s.slot())) {\n                continue;\n            }\n            if (o.room().equals(s.room())) {",
             "        for (Session o : sessions) {\n            if (!o.slot().overlaps(s.slot())) {\n                continue;\n            }\n            if (o.room().equals(s.room())) {")
    move_first = ("        check(moved);\n        sessions.set(sessions.indexOf(old), moved);\n", "        sessions.set(sessions.indexOf(old), moved);\n        check(moved);\n")
    remove = ("        if (!sessions.removeIf(s -> s.id() == id)) {\n            throw new NoSuchElementException(\"no session \" + id);\n        }\n", "        sessions.remove(id);\n")
    copy = ("        c.sessions = new ArrayList<>(sessions);\n", "        c.sessions = sessions;\n")
    order = (".thenComparing(Session::room).thenComparingInt(Session::id));\n", ".thenComparingInt(Session::id));\n")
    capacity = ("        if (s.registered() > capacity) {\n", "        if (s.registered() >= capacity) {\n")
    at = ("s.slot().start() <= minute && minute < s.slot().end()", "s.slot().start() <= minute && minute <= s.slot().end()")
    locale = ("        return String.format(Locale.ROOT, \"%.1f\", registered * 100.0 / seats);\n", "        return String.format(\"%.1f\", registered * 100.0 / seats);\n")
    fill_int = ("        return String.format(Locale.ROOT, \"%.1f\", registered * 100.0 / seats);\n", "        return String.format(Locale.ROOT, \"%.1f\", (double) (registered * 100 / seats));\n")
    quote = ("        if (value.indexOf(',') >= 0 || value.indexOf('\"') >= 0 || value.indexOf('\\n') >= 0) {\n", "        if (value.indexOf('\"') >= 0 || value.indexOf('\\n') >= 0) {\n")
    trailing = ("        out.add(cur.toString());\n        return out;\n", "        if (cur.length() > 0) {\n            out.add(cur.toString());\n        }\n        return out;\n")
    quotes_in = ("                if (c == '\"') {\n                    if (i + 1 < line.length() && line.charAt(i + 1) == '\"') {\n                        cur.append('\"');\n                        i++;\n                    } else {\n                        quoted = false;\n                    }\n                } else {\n",
                 "                if (c == '\"') {\n                    quoted = false;\n                } else {\n")
    bugs = [
        Bug("touching-slots-count-as-overlapping", 2, {sl: [touching]}, P["touching"]),
        Bug("speaker-names-compared-case-sensitively", 2, {sc: [case]}, P["case"]),
        Bug("registered-equal-to-the-seats-is-refused", 2, {sc: [capacity]}, P["capacity"]),
        Bug("at-includes-the-end-minute", 2, {sc: [at]}, P["at"]),
        Bug("same-start-sessions-ignore-the-room-order", 2, {sc: [order]}, P["order"]),
        Bug("fill-computed-with-integer-division", 2, {rp: [fill_int]}, P["fill-int"]),
        Bug("speaker-double-booking-is-not-detected", 3, {sc: [speaker]}, P["speaker"]),
        Bug("move-conflicts-with-itself", 3, {sc: [self_]}, P["self"]),
        Bug("move-changes-before-checking", 3, {sc: [move_first]}, P["move-first"]),
        Bug("remove-takes-a-position", 3, {sc: [remove]}, P["remove"]),
        Bug("copy-shares-the-session-list", 3, {sc: [copy]}, P["copy"]),
        Bug("fill-uses-the-default-locale", 3, {rp: [locale]}, P["locale"]),
        Bug("fields-with-commas-are-not-quoted", 3, {rp: [quote]}, P["quote"]),
        Bug("import-drops-an-empty-last-field", 3, {im: [trailing]}, P["trailing"]),
        Bug("import-loses-doubled-quotes", 3, {im: [quotes_in]}, P["quotes-in"]),
    ]
    base = Base("roomplan", "java", good, VISIBLE, HIDDEN, bugs)
    base.bugs.extend([
        combo(base, ["touching-slots-count-as-overlapping", "speaker-double-booking-is-not-detected"], 4, "committee-review",
              "Calendar review of the planner:"),
        combo(base, ["fields-with-commas-are-not-quoted", "import-drops-an-empty-last-field", "import-loses-doubled-quotes"], 4, "csv-round-trip-review",
              "The CSV round trip of the planner is broken in three places:"),
        combo(base, ["remove-takes-a-position", "touching-slots-count-as-overlapping", "fill-uses-the-default-locale", "import-drops-an-empty-last-field"], 5,
              "go-live-checklist", "Go-live checklist, four items filed by four people:"),
        combo(base, ["move-conflicts-with-itself", "move-changes-before-checking", "copy-shares-the-session-list"], 4, "what-if-planning-review",
              "The 'what if' planning feature has three problems:"),
    ])
    return base


@family("fix-hand-room-plan", category="fix", lang="java", kind="fix", n=19,
        summary="a layered java conference scheduler (slots, sessions, schedule, CSV report and import) with cross-class defects and review tickets")
def gen(rng, n):
    return tasks_from([_base()])
