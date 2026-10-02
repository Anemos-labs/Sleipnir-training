"""School timetable conflict checker (java): bugs injected into a scheduling-validation library."""
from fx import Lib, dd
from generators.fix._lang2 import JAVA_CHECK, java_test_main, register_libs

README = dd(r'''
    # timetable

    Checks a school timetable for clashes. Plain Java 17, no dependencies; sources in `src/school/`.

    The week has days `0` (Monday) to `4` (Friday); a day has ten *slots* (periods) numbered `0` to `9`.

    ## `Lesson(id, teacher, room, group, day, start, length)`

    A lesson of a class (`group`) with a teacher in a room, occupying the slots `start` to `start + length - 1` of one day.
    `id` must not be empty, `day` is `0..4`, `start` is `0..9`, `length >= 1` and `start + length <= 10`; otherwise
    `IllegalArgumentException`. Fields are public and final. Two lessons *overlap* when they are on the same day and share at
    least one slot (lessons that only touch, one ending where the other starts, do not overlap).

    ## `Rules`

    * `blockTeacher(teacher, day, slot)`: the teacher is not available in that slot (`day` `0..4`, `slot` `0..9`, else
      `IllegalArgumentException`).
    * `roomCapacity(room, capacity)` and `groupSize(group, size)`: both must be `>= 1` (else `IllegalArgumentException`).

    ## `Checker.check(lessons, rules)` returns a `List<Conflict>`

    Two lessons with the same `id` are an `IllegalArgumentException`. A `Conflict` has a `kind` (`Conflict.Kind`) and `ids`, the
    ids of the lessons involved in ascending (plain `String`) order. The kinds, in this order:

    1. `TEACHER_CLASH`, `ROOM_CLASH`, `GROUP_CLASH`: one conflict for every pair of overlapping lessons that share the teacher, the
       room, or the group respectively (a pair that shares several things gives several conflicts).
    2. `TEACHER_UNAVAILABLE`: one conflict, with the single lesson id, for each lesson that occupies a slot its teacher has
       blocked on that day.
    3. `ROOM_TOO_SMALL`: one for each lesson whose room capacity is known and smaller than the known size of its group (if either
       number is unknown there is no conflict; equal numbers are fine).
    4. `NO_LUNCH`: for each group and each day on which the group has lessons that together cover **all** of slots `4`, `5` and
       `6`: one conflict whose ids are those lessons of that group and day that occupy at least one of the slots 4 to 6.

    The result is sorted by kind (in the order above) and then by the ids joined with `,`; equal conflicts keep their order.

    ## `Checker.freeRuns(lessons, resource, name, day, minLength)`

    The free stretches of one day for a teacher, a room or a group (`Resource.TEACHER`, `ROOM`, `GROUP`; `name` is the teacher,
    room or group name). Returns the runs of consecutive free slots, in order of time, as `int[] {start, length}`, keeping only
    runs of at least `minLength` slots (`minLength >= 1`, else `IllegalArgumentException`). A slot is busy when a lesson of that
    resource on that day occupies it.
''')

RESOURCE = dd(r'''
    package school;

    public enum Resource {
        TEACHER,
        ROOM,
        GROUP
    }
''')

LESSON = dd(r'''
    package school;

    public final class Lesson {
        public final String id;
        public final String teacher;
        public final String room;
        public final String group;
        public final int day;
        public final int start;
        public final int length;

        public Lesson(String id, String teacher, String room, String group, int day, int start, int length) {
            if (id.isEmpty()) {
                throw new IllegalArgumentException("a lesson needs an id");
            }
            if (day < 0 || day > 4) {
                throw new IllegalArgumentException("day must be 0..4");
            }
            if (start < 0 || start > 9 || length < 1 || start + length > 10) {
                throw new IllegalArgumentException("a lesson must fit into the ten slots of a day");
            }
            this.id = id;
            this.teacher = teacher;
            this.room = room;
            this.group = group;
            this.day = day;
            this.start = start;
            this.length = length;
        }

        public boolean overlaps(Lesson other) {
            return day == other.day && start < other.start + other.length && other.start < start + length;
        }

        public boolean covers(int slot) {
            return slot >= start && slot < start + length;
        }
    }
''')

RULES = dd(r'''
    package school;

    import java.util.HashMap;
    import java.util.HashSet;
    import java.util.Map;
    import java.util.Set;

    public final class Rules {
        private final Map<String, Set<Integer>> blocked = new HashMap<>();
        private final Map<String, Integer> capacities = new HashMap<>();
        private final Map<String, Integer> sizes = new HashMap<>();

        public void blockTeacher(String teacher, int day, int slot) {
            if (day < 0 || day > 4 || slot < 0 || slot > 9) {
                throw new IllegalArgumentException("no such slot");
            }
            blocked.computeIfAbsent(teacher, k -> new HashSet<>()).add(day * 10 + slot);
        }

        public void roomCapacity(String room, int capacity) {
            if (capacity < 1) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            capacities.put(room, capacity);
        }

        public void groupSize(String group, int size) {
            if (size < 1) {
                throw new IllegalArgumentException("size must be positive");
            }
            sizes.put(group, size);
        }

        public boolean isBlocked(String teacher, int day, int slot) {
            Set<Integer> set = blocked.get(teacher);
            return set != null && set.contains(day * 10 + slot);
        }

        public Integer capacityOf(String room) {
            return capacities.get(room);
        }

        public Integer sizeOf(String group) {
            return sizes.get(group);
        }
    }
''')

CONFLICT = dd(r'''
    package school;

    import java.util.List;

    public final class Conflict {
        public enum Kind {
            TEACHER_CLASH,
            ROOM_CLASH,
            GROUP_CLASH,
            TEACHER_UNAVAILABLE,
            ROOM_TOO_SMALL,
            NO_LUNCH
        }

        public final Kind kind;
        public final List<String> ids;

        public Conflict(Kind kind, List<String> ids) {
            this.kind = kind;
            this.ids = ids;
        }

        public String key() {
            return String.join(",", ids);
        }
    }
''')

CHECKER = dd(r'''
    package school;

    import java.util.ArrayList;
    import java.util.Collections;
    import java.util.HashSet;
    import java.util.List;
    import java.util.Set;
    import java.util.TreeSet;

    public final class Checker {
        private Checker() {}

        private static List<String> sorted(String... ids) {
            List<String> l = new ArrayList<>(List.of(ids));
            Collections.sort(l);
            return l;
        }

        public static List<Conflict> check(List<Lesson> lessons, Rules rules) {
            Set<String> seen = new HashSet<>();
            for (Lesson l : lessons) {
                if (!seen.add(l.id)) {
                    throw new IllegalArgumentException("duplicate lesson id " + l.id);
                }
            }
            List<Conflict> out = new ArrayList<>();
            for (int i = 0; i < lessons.size(); i++) {
                for (int j = i + 1; j < lessons.size(); j++) {
                    Lesson a = lessons.get(i);
                    Lesson b = lessons.get(j);
                    if (!a.overlaps(b)) {
                        continue;
                    }
                    if (a.teacher.equals(b.teacher)) {
                        out.add(new Conflict(Conflict.Kind.TEACHER_CLASH, sorted(a.id, b.id)));
                    }
                    if (a.room.equals(b.room)) {
                        out.add(new Conflict(Conflict.Kind.ROOM_CLASH, sorted(a.id, b.id)));
                    }
                    if (a.group.equals(b.group)) {
                        out.add(new Conflict(Conflict.Kind.GROUP_CLASH, sorted(a.id, b.id)));
                    }
                }
            }
            for (Lesson l : lessons) {
                for (int s = l.start; s < l.start + l.length; s++) {
                    if (rules.isBlocked(l.teacher, l.day, s)) {
                        out.add(new Conflict(Conflict.Kind.TEACHER_UNAVAILABLE, sorted(l.id)));
                        break;
                    }
                }
                Integer capacity = rules.capacityOf(l.room);
                Integer size = rules.sizeOf(l.group);
                if (capacity != null && size != null && capacity < size) {
                    out.add(new Conflict(Conflict.Kind.ROOM_TOO_SMALL, sorted(l.id)));
                }
            }
            Set<String> groups = new TreeSet<>();
            for (Lesson l : lessons) {
                groups.add(l.group);
            }
            for (String g : groups) {
                for (int day = 0; day < 5; day++) {
                    List<Lesson> today = new ArrayList<>();
                    for (Lesson l : lessons) {
                        if (l.group.equals(g) && l.day == day) {
                            today.add(l);
                        }
                    }
                    boolean all = true;
                    for (int slot = 4; slot <= 6; slot++) {
                        boolean covered = false;
                        for (Lesson l : today) {
                            covered |= l.covers(slot);
                        }
                        all &= covered;
                    }
                    if (all) {
                        Set<String> ids = new TreeSet<>();
                        for (Lesson l : today) {
                            if (l.covers(4) || l.covers(5) || l.covers(6)) {
                                ids.add(l.id);
                            }
                        }
                        out.add(new Conflict(Conflict.Kind.NO_LUNCH, new ArrayList<>(ids)));
                    }
                }
            }
            out.sort((x, y) -> x.kind != y.kind ? x.kind.ordinal() - y.kind.ordinal() : x.key().compareTo(y.key()));
            return out;
        }

        public static List<int[]> freeRuns(List<Lesson> lessons, Resource resource, String name, int day, int minLength) {
            if (minLength < 1) {
                throw new IllegalArgumentException("minLength must be at least 1");
            }
            boolean[] busy = new boolean[10];
            for (Lesson l : lessons) {
                String owner = resource == Resource.TEACHER ? l.teacher : resource == Resource.ROOM ? l.room : l.group;
                if (l.day == day && owner.equals(name)) {
                    for (int s = l.start; s < l.start + l.length; s++) {
                        busy[s] = true;
                    }
                }
            }
            List<int[]> runs = new ArrayList<>();
            int s = 0;
            while (s < 10) {
                if (busy[s]) {
                    s++;
                    continue;
                }
                int e = s;
                while (e < 10 && !busy[e]) {
                    e++;
                }
                if (e - s >= minLength) {
                    runs.add(new int[] {s, e - s});
                }
                s = e;
            }
            return runs;
        }
    }
''')

BASIC = dd(r'''
    import school.Lesson;

    public class BasicTests {
        public static void run() {
            Check.test("overlap", () -> {
                Lesson a = new Lesson("A", "t", "r", "g", 0, 0, 2);
                Lesson b = new Lesson("B", "t", "r", "g", 0, 1, 2);
                Lesson c = new Lesson("C", "t", "r", "g", 0, 2, 2);
                Check.yes(a.overlaps(b), "A and B share slot 1");
                Check.yes(!a.overlaps(c), "A and C only touch");
            });
        }
    }
''')

FULL = dd(r'''
    import java.util.ArrayList;
    import java.util.List;
    import school.Checker;
    import school.Conflict;
    import school.Lesson;
    import school.Resource;
    import school.Rules;

    public class FullTests {
        static Lesson lesson(String id, String teacher, String room, String group, int day, int start, int length) {
            return new Lesson(id, teacher, room, group, day, start, length);
        }

        static List<String> describe(List<Conflict> conflicts) {
            List<String> out = new ArrayList<>();
            for (Conflict c : conflicts) {
                out.add(c.kind + ":" + String.join(",", c.ids));
            }
            return out;
        }

        static List<String> runs(List<int[]> runs) {
            List<String> out = new ArrayList<>();
            for (int[] r : runs) {
                out.add(r[0] + "+" + r[1]);
            }
            return out;
        }

        public static void run() {
            Check.test("lesson validation", () -> {
                Check.raises(IllegalArgumentException.class, () -> lesson("", "t", "r", "g", 0, 0, 1));
                Check.raises(IllegalArgumentException.class, () -> lesson("A", "t", "r", "g", -1, 0, 1));
                Check.raises(IllegalArgumentException.class, () -> lesson("A", "t", "r", "g", 5, 0, 1));
                Check.raises(IllegalArgumentException.class, () -> lesson("A", "t", "r", "g", 0, -1, 1));
                Check.raises(IllegalArgumentException.class, () -> lesson("A", "t", "r", "g", 0, 10, 1));
                Check.raises(IllegalArgumentException.class, () -> lesson("A", "t", "r", "g", 0, 0, 0));
                Check.raises(IllegalArgumentException.class, () -> lesson("A", "t", "r", "g", 0, 9, 2));
                Check.raises(IllegalArgumentException.class, () -> lesson("A", "t", "r", "g", 0, 0, 11));
                lesson("A", "t", "r", "g", 4, 9, 1);
                lesson("A", "t", "r", "g", 0, 0, 10);
            });

            Check.test("overlap and covers", () -> {
                Lesson a = lesson("A", "t", "r", "g", 0, 2, 3);
                Check.yes(a.overlaps(lesson("B", "t", "r", "g", 0, 4, 2)), "end overlap");
                Check.yes(!a.overlaps(lesson("B", "t", "r", "g", 0, 5, 2)), "touching at the end");
                Check.yes(a.overlaps(lesson("B", "t", "r", "g", 0, 0, 3)), "start overlap");
                Check.yes(!a.overlaps(lesson("B", "t", "r", "g", 0, 0, 2)), "touching at the start");
                Check.yes(a.overlaps(lesson("B", "t", "r", "g", 0, 3, 1)), "inside");
                Check.yes(!a.overlaps(lesson("B", "t", "r", "g", 1, 2, 3)), "other day");
                Check.yes(a.covers(2) && a.covers(4) && !a.covers(1) && !a.covers(5), "covers");
            });

            Check.test("rules validation", () -> {
                Rules rules = new Rules();
                Check.raises(IllegalArgumentException.class, () -> rules.blockTeacher("t", -1, 0));
                Check.raises(IllegalArgumentException.class, () -> rules.blockTeacher("t", 5, 0));
                Check.raises(IllegalArgumentException.class, () -> rules.blockTeacher("t", 0, -1));
                Check.raises(IllegalArgumentException.class, () -> rules.blockTeacher("t", 0, 10));
                Check.raises(IllegalArgumentException.class, () -> rules.roomCapacity("r", 0));
                Check.raises(IllegalArgumentException.class, () -> rules.groupSize("g", 0));
                rules.blockTeacher("t", 4, 9);
                rules.roomCapacity("r", 1);
                rules.groupSize("g", 1);
                Check.yes(rules.isBlocked("t", 4, 9), "blocked");
                Check.yes(!rules.isBlocked("t", 4, 8), "not blocked");
                Check.yes(!rules.isBlocked("t", 3, 9), "other day");
                Check.yes(!rules.isBlocked("u", 4, 9), "other teacher");
            });

            Check.test("duplicate ids", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("A", "t", "r", "g", 0, 0, 1));
                lessons.add(lesson("A", "u", "s", "h", 1, 0, 1));
                Check.raises(IllegalArgumentException.class, () -> Checker.check(lessons, new Rules()));
            });

            Check.test("a full timetable", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("L1", "ames", "R1", "7A", 0, 0, 2));
                lessons.add(lesson("L2", "ames", "R2", "7B", 0, 1, 2));
                lessons.add(lesson("L3", "bose", "R1", "7C", 0, 1, 1));
                lessons.add(lesson("L4", "cruz", "R3", "7A", 0, 1, 2));
                lessons.add(lesson("L5", "cruz", "R3", "7A", 1, 3, 2));
                lessons.add(lesson("L6", "dahl", "R1", "7A", 1, 5, 2));
                lessons.add(lesson("L7", "bose", "R2", "7B", 1, 4, 1));
                lessons.add(lesson("L8", "eide", "R3", "7B", 1, 6, 1));
                lessons.add(lesson("L9", "eide", "R4", "7B", 2, 0, 2));
                Rules rules = new Rules();
                rules.blockTeacher("bose", 0, 1);
                rules.blockTeacher("bose", 1, 4);
                rules.blockTeacher("bose", 2, 7);
                rules.blockTeacher("cruz", 3, 0);
                rules.roomCapacity("R1", 30);
                rules.roomCapacity("R2", 20);
                rules.roomCapacity("R3", 15);
                rules.roomCapacity("R4", 40);
                rules.groupSize("7A", 28);
                rules.groupSize("7B", 24);
                rules.groupSize("7C", 10);
                List<String> got = describe(Checker.check(lessons, rules));
                Check.eq(List.of("TEACHER_CLASH:L1,L2", "ROOM_CLASH:L1,L3", "GROUP_CLASH:L1,L4", "TEACHER_UNAVAILABLE:L3", "TEACHER_UNAVAILABLE:L7", "ROOM_TOO_SMALL:L2", "ROOM_TOO_SMALL:L4", "ROOM_TOO_SMALL:L5", "ROOM_TOO_SMALL:L7", "ROOM_TOO_SMALL:L8", "NO_LUNCH:L5,L6"), got);
            });

            Check.test("touching lessons do not clash", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("A", "t1", "r1", "g1", 0, 0, 2));
                lessons.add(lesson("B", "t1", "r1", "g1", 0, 2, 1));
                lessons.add(lesson("C", "t1", "r1", "g1", 0, 3, 2));
                Rules rules = new Rules();
                Check.eq(List.of(), describe(Checker.check(lessons, rules)));
            });

            Check.test("lessons on different days do not clash", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("A", "t1", "r1", "g1", 0, 0, 3));
                lessons.add(lesson("B", "t1", "r1", "g1", 1, 0, 3));
                lessons.add(lesson("C", "t1", "r1", "g1", 4, 9, 1));
                Rules rules = new Rules();
                Check.eq(List.of(), describe(Checker.check(lessons, rules)));
            });

            Check.test("one overlapping pair can clash in three ways", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("B", "t1", "r1", "g1", 2, 4, 2));
                lessons.add(lesson("A", "t1", "r1", "g1", 2, 5, 2));
                Rules rules = new Rules();
                Check.eq(List.of("TEACHER_CLASH:A,B", "ROOM_CLASH:A,B", "GROUP_CLASH:A,B", "NO_LUNCH:A,B"), describe(Checker.check(lessons, rules)));
            });

            Check.test("a lesson fully inside another one clashes", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("A", "t1", "r1", "g1", 0, 2, 6));
                lessons.add(lesson("B", "t1", "r2", "g2", 0, 4, 1));
                Rules rules = new Rules();
                Check.eq(List.of("TEACHER_CLASH:A,B", "NO_LUNCH:A"), describe(Checker.check(lessons, rules)));
            });

            Check.test("three lessons give three pairs", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("X", "t1", "r9", "g1", 3, 0, 2));
                lessons.add(lesson("Y", "t1", "r8", "g2", 3, 1, 2));
                lessons.add(lesson("Z", "t1", "r7", "g3", 3, 0, 3));
                Rules rules = new Rules();
                Check.eq(List.of("TEACHER_CLASH:X,Y", "TEACHER_CLASH:X,Z", "TEACHER_CLASH:Y,Z"), describe(Checker.check(lessons, rules)));
            });

            Check.test("single-slot overlap at the last slot", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("A", "t", "r", "g", 0, 8, 2));
                lessons.add(lesson("B", "t", "r", "g", 0, 9, 1));
                Rules rules = new Rules();
                Check.eq(List.of("TEACHER_CLASH:A,B", "ROOM_CLASH:A,B", "GROUP_CLASH:A,B"), describe(Checker.check(lessons, rules)));
            });

            Check.test("blocked slots of a teacher", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("A", "t1", "r1", "g1", 0, 0, 3));
                lessons.add(lesson("B", "t1", "r1", "g2", 1, 2, 1));
                lessons.add(lesson("C", "t2", "r1", "g3", 0, 0, 3));
                Rules rules = new Rules();
                rules.blockTeacher("t1", 0, 2);
                rules.blockTeacher("t1", 1, 2);
                rules.blockTeacher("t1", 1, 3);
                Check.eq(List.of("ROOM_CLASH:A,C", "TEACHER_UNAVAILABLE:A", "TEACHER_UNAVAILABLE:B"), describe(Checker.check(lessons, rules)));
            });

            Check.test("a teacher block must lie inside the lesson", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("A", "t1", "r1", "g1", 0, 3, 2));
                Rules rules = new Rules();
                rules.blockTeacher("t1", 0, 2);
                rules.blockTeacher("t1", 0, 5);
                rules.blockTeacher("t1", 1, 3);
                Check.eq(List.of(), describe(Checker.check(lessons, rules)));
            });

            Check.test("room capacity equal to the group is fine", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("A", "t1", "r1", "g1", 0, 0, 1));
                lessons.add(lesson("B", "t2", "r2", "g2", 1, 0, 1));
                lessons.add(lesson("C", "t3", "r3", "g3", 2, 0, 1));
                Rules rules = new Rules();
                rules.roomCapacity("r1", 20);
                rules.roomCapacity("r2", 19);
                rules.roomCapacity("r3", 21);
                rules.groupSize("g1", 20);
                rules.groupSize("g2", 20);
                rules.groupSize("g3", 20);
                Check.eq(List.of("ROOM_TOO_SMALL:B"), describe(Checker.check(lessons, rules)));
            });

            Check.test("capacity checks need both numbers", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("A", "t1", "r1", "g1", 0, 0, 1));
                lessons.add(lesson("B", "t2", "r2", "g2", 1, 0, 1));
                Rules rules = new Rules();
                rules.roomCapacity("r1", 5);
                rules.groupSize("g2", 50);
                Check.eq(List.of(), describe(Checker.check(lessons, rules)));
            });

            Check.test("lunch: all of slots 4 5 6 covered", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("A", "t1", "r1", "g1", 0, 2, 3));
                lessons.add(lesson("B", "t2", "r2", "g1", 0, 5, 2));
                Rules rules = new Rules();
                Check.eq(List.of("NO_LUNCH:A,B"), describe(Checker.check(lessons, rules)));
            });

            Check.test("lunch: a gap in 4..6 is enough", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("A", "t1", "r1", "g1", 0, 2, 3));
                lessons.add(lesson("B", "t2", "r2", "g1", 0, 6, 2));
                Rules rules = new Rules();
                Check.eq(List.of(), describe(Checker.check(lessons, rules)));
            });

            Check.test("lunch: one long lesson over the lunch hours", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("A", "t1", "r1", "g1", 1, 3, 5));
                Rules rules = new Rules();
                Check.eq(List.of("NO_LUNCH:A"), describe(Checker.check(lessons, rules)));
            });

            Check.test("lunch: two groups are checked separately", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("A", "t1", "r1", "g1", 2, 4, 3));
                lessons.add(lesson("B", "t2", "r2", "g2", 2, 4, 2));
                lessons.add(lesson("C", "t3", "r3", "g2", 2, 6, 1));
                Rules rules = new Rules();
                Check.eq(List.of("NO_LUNCH:A", "NO_LUNCH:B,C"), describe(Checker.check(lessons, rules)));
            });

            Check.test("lunch is reported per day", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("A", "t1", "r1", "g1", 0, 4, 3));
                lessons.add(lesson("B", "t1", "r1", "g1", 1, 4, 3));
                Rules rules = new Rules();
                Check.eq(List.of("NO_LUNCH:A", "NO_LUNCH:B"), describe(Checker.check(lessons, rules)));
            });

            Check.test("free runs", () -> {
                List<Lesson> lessons = new ArrayList<>();
                lessons.add(lesson("L1", "ames", "R1", "7A", 0, 0, 2));
                lessons.add(lesson("L2", "ames", "R2", "7B", 0, 1, 2));
                lessons.add(lesson("L3", "bose", "R1", "7C", 0, 1, 1));
                lessons.add(lesson("L4", "cruz", "R3", "7A", 0, 1, 2));
                lessons.add(lesson("L5", "cruz", "R3", "7A", 1, 3, 2));
                lessons.add(lesson("L6", "dahl", "R1", "7A", 1, 5, 2));
                lessons.add(lesson("L7", "bose", "R2", "7B", 1, 4, 1));
                lessons.add(lesson("L8", "eide", "R3", "7B", 1, 6, 1));
                lessons.add(lesson("L9", "eide", "R4", "7B", 2, 0, 2));
                Check.eq(List.of("3+7"), runs(Checker.freeRuns(lessons, Resource.GROUP, "7A", 0, 1)));
                Check.eq(List.of("0+3", "7+3"), runs(Checker.freeRuns(lessons, Resource.GROUP, "7A", 1, 2)));
                Check.eq(List.of("3+7"), runs(Checker.freeRuns(lessons, Resource.TEACHER, "ames", 0, 3)));
                Check.eq(List.of("2+8"), runs(Checker.freeRuns(lessons, Resource.ROOM, "R1", 0, 2)));
                Check.eq(List.of("0+10"), runs(Checker.freeRuns(lessons, Resource.GROUP, "7C", 4, 10)));
                Check.eq(List.of(), runs(Checker.freeRuns(lessons, Resource.GROUP, "7C", 4, 11)));
                Check.eq(List.of("0+4", "5+1", "7+3"), runs(Checker.freeRuns(lessons, Resource.GROUP, "7B", 1, 1)));
                Check.eq(List.of("2+8"), runs(Checker.freeRuns(lessons, Resource.TEACHER, "eide", 2, 1)));
                Check.eq(List.of("0+3", "5+1", "7+3"), runs(Checker.freeRuns(lessons, Resource.ROOM, "R3", 1, 1)));
                Check.eq(List.of("3+7"), runs(Checker.freeRuns(lessons, Resource.ROOM, "R3", 0, 4)));
            });

            Check.test("free runs validation", () -> {
                List<Lesson> none = new ArrayList<>();
                Check.raises(IllegalArgumentException.class, () -> Checker.freeRuns(none, Resource.ROOM, "r", 0, 0));
                Check.eq(List.of("0+10"), runs(Checker.freeRuns(none, Resource.ROOM, "r", 0, 1)));
            });
        }
    }
''')

LIB = Lib(
    name="timetable", lang="java", title="the timetable checker",
    blurb="The school office checks every draft timetable for clashes of teachers, rooms and classes with the timetable checker.",
    files={"src/school/Resource.java": RESOURCE, "src/school/Lesson.java": LESSON, "src/school/Rules.java": RULES, "src/school/Conflict.java": CONFLICT,
           "src/school/Checker.java": CHECKER, "README.md": README, ".gitignore": "build/\n"},
    visible_tests={"test/Check.java": JAVA_CHECK, "test/BasicTests.java": BASIC, "test/TestMain.java": java_test_main("BasicTests")},
    hidden_tests={"test/FullTests.java": FULL, "test/TestMain.java": java_test_main("BasicTests", "FullTests")},
    mutate=["src/school/Checker.java", "src/school/Lesson.java", "src/school/Rules.java"], difficulty=3, tags=["scheduling", "timetable", "school"],
)

register_libs([LIB], n=8)
