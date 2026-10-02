"""Java libraries for the testing families: gradebook, booklet imposition. Tests are plain classes with static ``test*()`` methods."""
from __future__ import annotations

from fx import dd, langs

from ._engine import TLib

WHERE_JAVA = ("Put your tests in `test/` as classes with `public static void test...()` methods (default package; `import` the library packages); "
              "`test/Check.java` has the assertion helpers and `test/TestMain.java` runs every such method it finds. No JUnit, the JDK only. "
              "Do not edit `Check.java` or `TestMain.java`. Build and run with `javac` over all `.java` files, then `java -cp build TestMain`.")

CHECK = dd('''
    import java.util.Objects;

    /** Tiny assertion helpers; every failure is an AssertionError. */
    public final class Check {
        private Check() {}

        public static void eq(Object expected, Object actual) {
            if (!Objects.equals(expected, actual)) {
                throw new AssertionError("expected <" + expected + "> but was <" + actual + ">");
            }
        }

        public static void isTrue(boolean cond) {
            if (!cond) {
                throw new AssertionError("expected true");
            }
        }

        public static void isFalse(boolean cond) {
            if (cond) {
                throw new AssertionError("expected false");
            }
        }

        public static void arrayEq(int[] expected, int[] actual) {
            if (!java.util.Arrays.equals(expected, actual)) {
                throw new AssertionError("expected " + java.util.Arrays.toString(expected) + " but was " + java.util.Arrays.toString(actual));
            }
        }

        /** The code must throw `type` (or a subclass). */
        public static void raises(Class<? extends Throwable> type, Runnable code) {
            try {
                code.run();
            } catch (Throwable t) {
                if (type.isInstance(t)) {
                    return;
                }
                throw new AssertionError("expected " + type.getSimpleName() + " but got " + t);
            }
            throw new AssertionError("expected " + type.getSimpleName() + " but nothing was thrown");
        }
    }
''')

TESTMAIN = dd('''
    import java.io.File;
    import java.lang.reflect.InvocationTargetException;
    import java.lang.reflect.Method;
    import java.lang.reflect.Modifier;
    import java.util.ArrayList;
    import java.util.Collections;
    import java.util.List;

    /** Runs every `public static void test*()` method of every class found in the build directory. */
    public final class TestMain {
        private static void collect(File dir, String prefix, List<String> out) {
            File[] kids = dir.listFiles();
            if (kids == null) {
                return;
            }
            for (File f : kids) {
                if (f.isDirectory()) {
                    collect(f, prefix + f.getName() + ".", out);
                } else if (f.getName().endsWith(".class")) {
                    out.add(prefix + f.getName().substring(0, f.getName().length() - 6));
                }
            }
        }

        public static void main(String[] args) throws Exception {
            List<String> names = new ArrayList<>();
            collect(new File("build"), "", names);
            Collections.sort(names);
            int ran = 0;
            int failed = 0;
            for (String name : names) {
                Class<?> c = Class.forName(name);
                Method[] methods = c.getDeclaredMethods();
                java.util.Arrays.sort(methods, java.util.Comparator.comparing(Method::getName));
                for (Method m : methods) {
                    if (!m.getName().startsWith("test") || !Modifier.isStatic(m.getModifiers()) || m.getParameterCount() != 0) {
                        continue;
                    }
                    ran++;
                    try {
                        m.invoke(null);
                    } catch (InvocationTargetException e) {
                        failed++;
                        System.out.println("FAIL " + name + "." + m.getName() + ": " + e.getCause());
                    }
                }
            }
            System.out.println(ran + " tests, " + failed + " failed");
            if (failed > 0 || ran == 0) {
                System.exit(1);
            }
        }
    }
''')

PROTECT_JAVA = ["test/Check.java", "test/TestMain.java"]

# ---------------------------------------------------------------------------------------------------------------------
# gradebook
# ---------------------------------------------------------------------------------------------------------------------

GB_README = dd('''
    # gradebook

    The grade arithmetic of a small school. Package `school`, three classes. Only whole numbers are used, "rounded" always means *half up*.

    ## `Grades`
    * `Grades.letter(int pct)` turns a whole percentage 0..100 into a letter: 97 and up `A+`, 93 `A`, 90 `A-`, 87 `B+`, 83 `B`, 80 `B-`, 77 `C+`, 73 `C`, 70 `C-`, 60 `D`,
      anything lower `F` (each number is the lowest percentage of its letter). Outside 0..100: `IllegalArgumentException`.
    * `Grades.toNextLetter(int pct)` is how many more percentage points are needed to reach the next higher letter, `0` for an `A+`. Outside 0..100: `IllegalArgumentException`.
    * `Grades.latePenalty(int points, int daysLate)` is the number of points kept for work handed in late: 10% of the points are deducted for every full day late, at most 50%;
      the deduction is rounded **down** (the student keeps the fraction). Negative `points` or `daysLate` is an `IllegalArgumentException`; any non-negative number of days is fine.

    ## `Gradebook`
    `new Gradebook(Map<String,Integer> weights)` takes category weights in percent. Every weight must be positive and the weights must add up to exactly 100,
    otherwise `IllegalArgumentException`.
    * `add(category, points, possible)` records a score. Unknown category, `possible <= 0`, `points < 0` or `points > possible` (no extra credit) are an `IllegalArgumentException`.
    * `setDrops(category, n)` says that the `n` lowest scores of that category are ignored (default 0): lowest *by percentage* (`points / possible`, compare exactly), on a tie the
      one that was entered first goes first. A category never drops its last remaining score, so with `n` larger than the number of scores minus one the best one stays.
      Negative `n` or an unknown category: `IllegalArgumentException`.
    * `categoryPercent(category)` is the category's percentage after the drops: all remaining points divided by all remaining possible points (not an average of percentages),
      rounded. A category without scores gives `-1` (a category whose scores are all 0 gives `0`). Unknown category: `IllegalArgumentException`.
    * `overall()` is the weighted average of the **rounded** category percentages, rounded again. Categories without scores are left out and the other weights count as if they
      were scaled up to 100. With no score at all in the book: `IllegalStateException`.
    * `letter()` is `Grades.letter(overall())`.
''')

GB_GRADES = dd('''
    package school;

    /** Letters and late penalties. */
    public final class Grades {
        private static final int[] CUTS = {97, 93, 90, 87, 83, 80, 77, 73, 70, 60};
        private static final String[] NAMES = {"A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D"};

        private Grades() {}

        private static void check(int pct) {
            if (pct < 0 || pct > 100) {
                throw new IllegalArgumentException("percentage out of range: " + pct);
            }
        }

        /** Letter for a whole percentage. */
        public static String letter(int pct) {
            check(pct);
            for (int i = 0; i < CUTS.length; i++) {
                if (pct >= CUTS[i]) {
                    return NAMES[i];
                }
            }
            return "F";
        }

        /** Percentage points missing for the next higher letter (0 for A+). */
        public static int toNextLetter(int pct) {
            check(pct);
            int missing = 0;
            for (int cut : CUTS) {
                if (cut > pct) {
                    missing = cut - pct;
                } else {
                    break;
                }
            }
            return missing;
        }

        /** Points kept after the late penalty. */
        public static int latePenalty(int points, int daysLate) {
            if (points < 0 || daysLate < 0) {
                throw new IllegalArgumentException("negative input");
            }
            int percent = Math.min(daysLate, 5) * 10;
            int deduction = points * percent / 100;
            return points - deduction;
        }
    }
''')

GB_BOOK = dd('''
    package school;

    import java.util.ArrayList;
    import java.util.HashMap;
    import java.util.LinkedHashMap;
    import java.util.List;
    import java.util.Map;

    /** Weighted grades with drop-the-lowest. */
    public final class Gradebook {
        private final Map<String, Integer> weights = new LinkedHashMap<>();
        private final Map<String, Integer> drops = new HashMap<>();
        private final Map<String, List<int[]>> entries = new HashMap<>();

        public Gradebook(Map<String, Integer> weights) {
            int sum = 0;
            for (Map.Entry<String, Integer> e : weights.entrySet()) {
                if (e.getValue() <= 0) {
                    throw new IllegalArgumentException("weight must be positive: " + e.getKey());
                }
                sum += e.getValue();
            }
            if (sum != 100) {
                throw new IllegalArgumentException("weights must add up to 100, got " + sum);
            }
            this.weights.putAll(weights);
            for (String c : weights.keySet()) {
                entries.put(c, new ArrayList<>());
                drops.put(c, 0);
            }
        }

        private void need(String category) {
            if (!weights.containsKey(category)) {
                throw new IllegalArgumentException("unknown category: " + category);
            }
        }

        public void setDrops(String category, int n) {
            need(category);
            if (n < 0) {
                throw new IllegalArgumentException("negative drop count");
            }
            drops.put(category, n);
        }

        public void add(String category, int points, int possible) {
            need(category);
            if (possible <= 0 || points < 0 || points > possible) {
                throw new IllegalArgumentException("bad score " + points + "/" + possible);
            }
            entries.get(category).add(new int[] {points, possible});
        }

        /** Rounded percentage of the category after drops, -1 without scores. */
        public int categoryPercent(String category) {
            need(category);
            List<int[]> list = new ArrayList<>(entries.get(category));
            if (list.isEmpty()) {
                return -1;
            }
            int toDrop = Math.min(drops.get(category), list.size() - 1);
            for (int k = 0; k < toDrop; k++) {
                int worst = 0;
                for (int i = 1; i < list.size(); i++) {
                    if (list.get(i)[0] * list.get(worst)[1] < list.get(worst)[0] * list.get(i)[1]) {
                        worst = i;
                    }
                }
                list.remove(worst);
            }
            long got = 0;
            long max = 0;
            for (int[] s : list) {
                got += s[0];
                max += s[1];
            }
            return (int) ((200 * got + max) / (2 * max));
        }

        /** Weighted average of the rounded category percentages. */
        public int overall() {
            long num = 0;
            long den = 0;
            for (Map.Entry<String, Integer> e : weights.entrySet()) {
                int p = categoryPercent(e.getKey());
                if (p < 0) {
                    continue;
                }
                num += (long) p * e.getValue();
                den += e.getValue();
            }
            if (den == 0) {
                throw new IllegalStateException("no scores yet");
            }
            return (int) ((2 * num + den) / (2 * den));
        }

        public String letter() {
            return Grades.letter(overall());
        }
    }
''')

GB_GRADES_TEST = dd('''
    import school.Grades;

    public class GradesTest {
        public static void testLetterTable() {
            Object[][] table = {
                {100, "A+"}, {97, "A+"}, {96, "A"}, {93, "A"}, {92, "A-"}, {90, "A-"}, {89, "B+"}, {87, "B+"}, {86, "B"}, {83, "B"}, {82, "B-"}, {80, "B-"},
                {79, "C+"}, {77, "C+"}, {76, "C"}, {73, "C"}, {72, "C-"}, {70, "C-"}, {69, "D"}, {60, "D"}, {59, "F"}, {1, "F"}, {0, "F"},
            };
            for (Object[] row : table) {
                Check.eq(row[1], Grades.letter((Integer) row[0]));
            }
        }

        public static void testLetterRange() {
            Check.raises(IllegalArgumentException.class, () -> Grades.letter(-1));
            Check.raises(IllegalArgumentException.class, () -> Grades.letter(101));
        }

        public static void testToNextLetter() {
            int[][] table = {{85, 2}, {86, 1}, {87, 3}, {88, 2}, {89, 1}, {90, 3}, {92, 1}, {93, 4}, {96, 1}, {97, 0}, {100, 0}, {59, 1}, {60, 10}, {69, 1}, {70, 3}, {0, 60}, {79, 1}, {76, 1}};
            for (int[] row : table) {
                Check.eq(row[1], Grades.toNextLetter(row[0]));
            }
            Check.raises(IllegalArgumentException.class, () -> Grades.toNextLetter(-1));
            Check.raises(IllegalArgumentException.class, () -> Grades.toNextLetter(101));
        }

        public static void testLatePenalty() {
            Check.eq(100, Grades.latePenalty(100, 0));
            Check.eq(90, Grades.latePenalty(100, 1));
            Check.eq(80, Grades.latePenalty(100, 2));
            Check.eq(70, Grades.latePenalty(100, 3));
            Check.eq(60, Grades.latePenalty(100, 4));
            Check.eq(50, Grades.latePenalty(100, 5));
            Check.eq(50, Grades.latePenalty(100, 6));
            Check.eq(50, Grades.latePenalty(100, 1000000000));
            Check.eq(7, Grades.latePenalty(7, 1));
            Check.eq(14, Grades.latePenalty(15, 1));
            Check.eq(11, Grades.latePenalty(15, 3));
            Check.eq(50, Grades.latePenalty(99, 5));
            Check.eq(0, Grades.latePenalty(0, 3));
        }

        public static void testLatePenaltyRejectsNegatives() {
            Check.raises(IllegalArgumentException.class, () -> Grades.latePenalty(-1, 0));
            Check.raises(IllegalArgumentException.class, () -> Grades.latePenalty(10, -1));
        }
    }
''')

GB_BOOK_TEST = dd('''
    import java.util.LinkedHashMap;
    import java.util.Map;
    import school.Gradebook;

    public class GradebookTest {
        private static Map<String, Integer> w(Object... kv) {
            Map<String, Integer> m = new LinkedHashMap<>();
            for (int i = 0; i < kv.length; i += 2) {
                m.put((String) kv[i], (Integer) kv[i + 1]);
            }
            return m;
        }

        private static Gradebook course() {
            return new Gradebook(w("homework", 30, "quizzes", 20, "exam", 50));
        }

        public static void testWeightsMustAddUpAndBePositive() {
            Check.raises(IllegalArgumentException.class, () -> new Gradebook(w("a", 50, "b", 49)));
            Check.raises(IllegalArgumentException.class, () -> new Gradebook(w("a", 50, "b", 51)));
            Check.raises(IllegalArgumentException.class, () -> new Gradebook(w("a", 100, "b", 0)));
            Check.raises(IllegalArgumentException.class, () -> new Gradebook(w("a", 110, "b", -10)));
            new Gradebook(w("only", 100));
        }

        public static void testAddValidation() {
            Gradebook g = course();
            Check.raises(IllegalArgumentException.class, () -> g.add("labs", 5, 10));
            Check.raises(IllegalArgumentException.class, () -> g.add("exam", 5, 0));
            Check.raises(IllegalArgumentException.class, () -> g.add("exam", 5, -10));
            Check.raises(IllegalArgumentException.class, () -> g.add("exam", -1, 10));
            Check.raises(IllegalArgumentException.class, () -> g.add("exam", 11, 10));
            g.add("exam", 10, 10);
            g.add("exam", 0, 10);
            Check.eq(50, g.categoryPercent("exam"));
        }

        public static void testCategoryPercentRoundsHalfUp() {
            Gradebook g = course();
            g.add("homework", 1, 8);
            Check.eq(13, g.categoryPercent("homework"));
            Gradebook h = course();
            h.add("homework", 1, 3);
            Check.eq(33, h.categoryPercent("homework"));
            Gradebook i = course();
            i.add("homework", 2, 3);
            Check.eq(67, i.categoryPercent("homework"));
            Gradebook j = course();
            j.add("homework", 17, 20);
            Check.eq(85, j.categoryPercent("homework"));
        }

        public static void testCategoryPercentPoolsThePoints() {
            Gradebook g = course();
            g.add("homework", 1, 10);
            g.add("homework", 50, 100);
            Check.eq(46, g.categoryPercent("homework"));
        }

        public static void testEmptyAndZeroCategories() {
            Gradebook g = course();
            Check.eq(-1, g.categoryPercent("quizzes"));
            g.add("quizzes", 0, 5);
            Check.eq(0, g.categoryPercent("quizzes"));
            Check.raises(IllegalArgumentException.class, () -> g.categoryPercent("labs"));
        }

        public static void testDropsTheLowestByPercentage() {
            Gradebook g = course();
            g.add("homework", 10, 10);
            g.add("homework", 5, 10);
            g.add("homework", 9, 10);
            g.setDrops("homework", 1);
            Check.eq(95, g.categoryPercent("homework"));
            g.setDrops("homework", 2);
            Check.eq(100, g.categoryPercent("homework"));
            g.setDrops("homework", 7);
            Check.eq(100, g.categoryPercent("homework"));
            Gradebook h = course();
            h.add("homework", 9, 10);
            h.add("homework", 40, 50);
            h.setDrops("homework", 1);
            Check.eq(90, h.categoryPercent("homework"));
        }

        public static void testDropsTwice() {
            Gradebook g = course();
            g.add("homework", 3, 10);
            g.add("homework", 6, 10);
            g.add("homework", 9, 10);
            g.add("homework", 2, 10);
            g.setDrops("homework", 2);
            Check.eq(75, g.categoryPercent("homework"));
        }

        public static void testTieDropsTheEarlierScore() {
            Gradebook g = course();
            g.add("homework", 5, 10);
            g.add("homework", 50, 100);
            g.add("homework", 10, 10);
            g.setDrops("homework", 1);
            Check.eq(55, g.categoryPercent("homework"));
        }

        public static void testDropsValidation() {
            Gradebook g = course();
            Check.raises(IllegalArgumentException.class, () -> g.setDrops("homework", -1));
            Check.raises(IllegalArgumentException.class, () -> g.setDrops("labs", 1));
            g.setDrops("homework", 0);
        }

        public static void testOverallWeightsTheCategories() {
            Gradebook g = course();
            g.add("homework", 8, 10);
            g.add("homework", 9, 10);
            g.add("quizzes", 3, 4);
            g.add("exam", 70, 100);
            Check.eq(76, g.overall());
            Check.eq("C", g.letter());
        }

        public static void testOverallLeavesOutEmptyCategories() {
            Gradebook g = course();
            g.add("homework", 17, 20);
            g.add("exam", 61, 100);
            Check.eq(70, g.overall());
        }

        public static void testOverallUsesRoundedCategoryPercents() {
            Gradebook g = new Gradebook(w("a", 50, "b", 50));
            g.add("a", 1, 8);
            g.add("b", 0, 10);
            Check.eq(7, g.overall());
        }

        public static void testOverallWithoutScores() {
            Gradebook g = course();
            Check.raises(IllegalStateException.class, g::overall);
            Check.raises(IllegalStateException.class, g::letter);
        }

        public static void testSingleCategoryOverall() {
            Gradebook g = new Gradebook(w("only", 100));
            g.add("only", 97, 100);
            Check.eq(97, g.overall());
            Check.eq("A+", g.letter());
        }
    }
''')

GB_STUB = dd('''
    import school.Grades;

    public class SmokeTest {
        public static void testSmoke() {
            Check.eq("A", Grades.letter(95));
        }
    }
''')


def gradebook(rng) -> TLib:
    files = {
        "README.md": GB_README, "src/school/Grades.java": GB_GRADES, "src/school/Gradebook.java": GB_BOOK,
        "test/Check.java": CHECK, "test/TestMain.java": TESTMAIN, ".gitignore": langs.GITIGNORE["java"],
    }
    wrong = [
        ("test/GradesTest.java", '{92, "A-"}', '{92, "A"}'),
        ("test/GradesTest.java", "Check.eq(11, Grades.latePenalty(15, 3));", "Check.eq(10, Grades.latePenalty(15, 3));"),
        ("test/GradesTest.java", "{87, 3}", "{87, 2}"),
        ("test/GradebookTest.java", "Check.eq(46, g.categoryPercent(\"homework\"));", "Check.eq(30, g.categoryPercent(\"homework\"));"),
        ("test/GradebookTest.java", "Check.eq(55, g.categoryPercent(\"homework\"));", "Check.eq(75, g.categoryPercent(\"homework\"));"),
        ("test/GradebookTest.java", "Check.eq(7, g.overall());", "Check.eq(6, g.overall());"),
    ]
    return TLib(
        name="java-gradebook", lang="java", title="the school gradebook arithmetic", blurb="The report-card generator calls `Grades` and `Gradebook` to turn marks into letters.",
        files=files, stub={"test/SmokeTest.java": GB_STUB}, gold={"test/GradesTest.java": GB_GRADES_TEST, "test/GradebookTest.java": GB_BOOK_TEST},
        mutate=["src/school/Grades.java", "src/school/Gradebook.java"], cmd=langs.VERIFY["java"], where=WHERE_JAVA, difficulty=3,
        wrong_edits=wrong, timeout=60, protect=["src/school/*.java", *PROTECT_JAVA], strip_keep={"test/Check.java": CHECK, "test/TestMain.java": TESTMAIN},
        focus="the letter cut-offs, rounding half up (also of the overall figure), the drop rules (lowest by percentage, ties, never the last score) and empty categories",
    )


# ---------------------------------------------------------------------------------------------------------------------
# booklet imposition
# ---------------------------------------------------------------------------------------------------------------------

BK_README = dd('''
    # booklet

    Helpers of the print shop's imposition tool. Package `print`, class `Booklet` (all static).

    ## Saddle-stitched booklets
    A sheet of paper carries four pages (front left / front right / back left / back right); a booklet of `pages` pages needs `Booklet.sheets(pages)` sheets, i.e. the page count
    rounded up to a multiple of 4, divided by 4. `pages < 1` is an `IllegalArgumentException`.

    `Booklet.sheet(pages, s)` gives the page numbers of sheet `s` (0 is the outermost sheet) as `int[4] {frontLeft, frontRight, backLeft, backRight}`. With `n = 4 * sheets(pages)`:
    `{n - 2s, 2s + 1, 2s + 2, n - 2s - 1}`. A number above `pages` is a blank page and is reported as `0`. A sheet index outside `0..sheets-1` is an `IllegalArgumentException`.

    `Booklet.imposition(pages)` is the list of all sheets, outermost first.

    ## Page ranges
    `Booklet.parseRanges(String spec, int max)` parses a print dialog's page field into a list of page numbers. `max` (the last page of the document) must be at least 1,
    otherwise `IllegalArgumentException`.
    * `null` or a blank spec means every page `1..max`.
    * Items are separated by commas, spaces around items and around the dash are ignored. An item is a page number `7` or an inclusive range `3-5`. Numbers are plain digits.
    * Pages must lie in `1..max`; a descending range (`5-3`), an empty item (`1,,2`, a leading or trailing comma) or anything that is not a number is an `IllegalArgumentException`.
    * The result keeps the order in which pages were written and lists every page once (the first occurrence wins).

    ## Compressing
    `Booklet.compress(List<Integer> pages)` writes a list of pages back as a spec: `[1, 2, 3, 5, 7, 8, 9]` becomes `"1-3,5,7-9"`. Only runs of **three or more** consecutive
    pages become a range; a run of two is written as two numbers (`[4, 5]` is `"4,5"`). The list must be strictly ascending and start at 1 or higher, otherwise
    `IllegalArgumentException`. An empty list gives `""`.
''')

BK_SRC = dd('''
    package print;

    import java.util.ArrayList;
    import java.util.HashSet;
    import java.util.List;
    import java.util.Set;

    /** Booklet imposition and page-range helpers. */
    public final class Booklet {
        private Booklet() {}

        /** Sheets of paper for a saddle-stitched booklet. */
        public static int sheets(int pages) {
            if (pages < 1) {
                throw new IllegalArgumentException("pages must be at least 1");
            }
            return (pages + 3) / 4;
        }

        /** {frontLeft, frontRight, backLeft, backRight} of sheet s; blanks are 0. */
        public static int[] sheet(int pages, int s) {
            int count = sheets(pages);
            if (s < 0 || s >= count) {
                throw new IllegalArgumentException("no such sheet: " + s);
            }
            int n = count * 4;
            int[] p = {n - 2 * s, 2 * s + 1, 2 * s + 2, n - 2 * s - 1};
            for (int i = 0; i < 4; i++) {
                if (p[i] > pages) {
                    p[i] = 0;
                }
            }
            return p;
        }

        public static List<int[]> imposition(int pages) {
            List<int[]> out = new ArrayList<>();
            for (int s = 0; s < sheets(pages); s++) {
                out.add(sheet(pages, s));
            }
            return out;
        }

        private static int number(String s) {
            if (s.isEmpty()) {
                throw new IllegalArgumentException("not a page number");
            }
            for (int i = 0; i < s.length(); i++) {
                char c = s.charAt(i);
                if (c < '0' || c > '9') {
                    throw new IllegalArgumentException("not a page number: " + s);
                }
            }
            return Integer.parseInt(s);
        }

        /** Parses "1-3, 5, 7-9" style page fields. */
        public static List<Integer> parseRanges(String spec, int max) {
            if (max < 1) {
                throw new IllegalArgumentException("max must be at least 1");
            }
            List<Integer> out = new ArrayList<>();
            if (spec == null || spec.trim().isEmpty()) {
                for (int i = 1; i <= max; i++) {
                    out.add(i);
                }
                return out;
            }
            Set<Integer> seen = new HashSet<>();
            for (String raw : spec.split(",", -1)) {
                String part = raw.trim();
                if (part.isEmpty()) {
                    throw new IllegalArgumentException("empty item");
                }
                int lo;
                int hi;
                int dash = part.indexOf('-');
                if (dash < 0) {
                    lo = number(part);
                    hi = lo;
                } else {
                    lo = number(part.substring(0, dash).trim());
                    hi = number(part.substring(dash + 1).trim());
                }
                if (lo > hi) {
                    throw new IllegalArgumentException("descending range: " + part);
                }
                if (lo < 1 || hi > max) {
                    throw new IllegalArgumentException("out of range: " + part);
                }
                for (int page = lo; page <= hi; page++) {
                    if (seen.add(page)) {
                        out.add(page);
                    }
                }
            }
            return out;
        }

        /** Inverse of parseRanges for ascending lists; runs of three or more become ranges. */
        public static String compress(List<Integer> pages) {
            if (!pages.isEmpty() && pages.get(0) < 1) {
                throw new IllegalArgumentException("pages start at 1");
            }
            for (int k = 1; k < pages.size(); k++) {
                if (pages.get(k) <= pages.get(k - 1)) {
                    throw new IllegalArgumentException("pages must be strictly ascending");
                }
            }
            StringBuilder sb = new StringBuilder();
            int i = 0;
            while (i < pages.size()) {
                int j = i;
                while (j + 1 < pages.size() && pages.get(j + 1) == pages.get(j) + 1) {
                    j++;
                }
                if (sb.length() > 0) {
                    sb.append(',');
                }
                if (j - i >= 2) {
                    sb.append(pages.get(i)).append('-').append(pages.get(j));
                } else {
                    sb.append(pages.get(i));
                    if (j > i) {
                        sb.append(',').append(pages.get(j));
                    }
                }
                i = j + 1;
            }
            return sb.toString();
        }
    }
''')

BK_TEST = dd('''
    import java.util.Arrays;
    import java.util.List;
    import print.Booklet;

    public class BookletTest {
        public static void testSheets() {
            int[][] table = {{1, 1}, {2, 1}, {3, 1}, {4, 1}, {5, 2}, {8, 2}, {9, 3}, {12, 3}, {13, 4}, {100, 25}};
            for (int[] row : table) {
                Check.eq(row[1], Booklet.sheets(row[0]));
            }
            Check.raises(IllegalArgumentException.class, () -> Booklet.sheets(0));
            Check.raises(IllegalArgumentException.class, () -> Booklet.sheets(-3));
        }

        public static void testSheetLayout() {
            Check.arrayEq(new int[] {8, 1, 2, 7}, Booklet.sheet(8, 0));
            Check.arrayEq(new int[] {6, 3, 4, 5}, Booklet.sheet(8, 1));
            Check.arrayEq(new int[] {12, 1, 2, 11}, Booklet.sheet(12, 0));
            Check.arrayEq(new int[] {10, 3, 4, 9}, Booklet.sheet(12, 1));
            Check.arrayEq(new int[] {8, 5, 6, 7}, Booklet.sheet(12, 2));
        }

        public static void testBlankPages() {
            Check.arrayEq(new int[] {0, 1, 2, 0}, Booklet.sheet(5, 0));
            Check.arrayEq(new int[] {0, 3, 4, 5}, Booklet.sheet(5, 1));
            Check.arrayEq(new int[] {0, 1, 0, 0}, Booklet.sheet(1, 0));
            Check.arrayEq(new int[] {0, 1, 2, 3}, Booklet.sheet(3, 0));
            Check.arrayEq(new int[] {4, 1, 2, 3}, Booklet.sheet(4, 0));
        }

        public static void testSheetIndexRange() {
            Check.raises(IllegalArgumentException.class, () -> Booklet.sheet(8, -1));
            Check.raises(IllegalArgumentException.class, () -> Booklet.sheet(8, 2));
            Check.raises(IllegalArgumentException.class, () -> Booklet.sheet(0, 0));
        }

        public static void testImposition() {
            List<int[]> all = Booklet.imposition(6);
            Check.eq(2, all.size());
            Check.arrayEq(new int[] {0, 1, 2, 0}, all.get(0));
            Check.arrayEq(new int[] {6, 3, 4, 5}, all.get(1));
            Check.eq(1, Booklet.imposition(4).size());
            Check.eq(3, Booklet.imposition(10).size());
        }

        public static void testBlankSpecMeansEverything() {
            Check.eq(Arrays.asList(1, 2, 3, 4), Booklet.parseRanges("", 4));
            Check.eq(Arrays.asList(1, 2, 3, 4), Booklet.parseRanges("   ", 4));
            Check.eq(Arrays.asList(1, 2, 3, 4), Booklet.parseRanges(null, 4));
            Check.eq(Arrays.asList(1), Booklet.parseRanges(null, 1));
        }

        public static void testParseRanges() {
            Check.eq(Arrays.asList(1, 2, 3, 5, 7, 8, 9), Booklet.parseRanges("1-3,5,7-9", 10));
            Check.eq(Arrays.asList(5, 1, 2), Booklet.parseRanges("5, 1 - 2", 10));
            Check.eq(Arrays.asList(4), Booklet.parseRanges("4-4", 10));
            Check.eq(Arrays.asList(10), Booklet.parseRanges("10", 10));
            Check.eq(Arrays.asList(1, 2, 3, 4), Booklet.parseRanges("1-3,2-4,3", 10));
            Check.eq(Arrays.asList(1), Booklet.parseRanges(" 1 ", 1));
            Check.eq(Arrays.asList(9, 10), Booklet.parseRanges("9-10", 10));
        }

        public static void testParseRangesRejects() {
            String[] bad = {"11", "0", "0-3", "3-2", "1,,2", "1,", ",1", "a", "-3", "+3", "1-2-3", "1.5", "3-", "5-11", "1 2", "--"};
            for (String spec : bad) {
                Check.raises(IllegalArgumentException.class, () -> Booklet.parseRanges(spec, 10));
            }
            Check.raises(IllegalArgumentException.class, () -> Booklet.parseRanges("1", 0));
            Check.raises(IllegalArgumentException.class, () -> Booklet.parseRanges("", 0));
        }

        public static void testCompress() {
            Check.eq("", Booklet.compress(Arrays.asList()));
            Check.eq("1", Booklet.compress(Arrays.asList(1)));
            Check.eq("1,2", Booklet.compress(Arrays.asList(1, 2)));
            Check.eq("1-3", Booklet.compress(Arrays.asList(1, 2, 3)));
            Check.eq("1-3,5,7-9", Booklet.compress(Arrays.asList(1, 2, 3, 5, 7, 8, 9)));
            Check.eq("4,5,9-12,20", Booklet.compress(Arrays.asList(4, 5, 9, 10, 11, 12, 20)));
            Check.eq("1,3,5", Booklet.compress(Arrays.asList(1, 3, 5)));
            Check.eq("2,3,6", Booklet.compress(Arrays.asList(2, 3, 6)));
            Check.eq("7-9", Booklet.compress(Arrays.asList(7, 8, 9)));
            Check.eq("1-3,5,7-9", Booklet.compress(Booklet.parseRanges("1-3,5,7-9", 20)));
        }

        public static void testCompressRejects() {
            Check.raises(IllegalArgumentException.class, () -> Booklet.compress(Arrays.asList(3, 1)));
            Check.raises(IllegalArgumentException.class, () -> Booklet.compress(Arrays.asList(2, 2)));
            Check.raises(IllegalArgumentException.class, () -> Booklet.compress(Arrays.asList(0, 1)));
            Check.raises(IllegalArgumentException.class, () -> Booklet.compress(Arrays.asList(-1, 2)));
            Check.raises(IllegalArgumentException.class, () -> Booklet.compress(Arrays.asList(1, 2, 2, 3)));
        }
    }
''')

BK_STUB = dd('''
    import print.Booklet;

    public class SmokeTest {
        public static void testSmoke() {
            Check.eq(2, Booklet.sheets(5));
        }
    }
''')


def booklet(rng) -> TLib:
    files = {
        "README.md": BK_README, "src/print/Booklet.java": BK_SRC,
        "test/Check.java": CHECK, "test/TestMain.java": TESTMAIN, ".gitignore": langs.GITIGNORE["java"],
    }
    wrong = [
        ("test/BookletTest.java", "Check.arrayEq(new int[] {6, 3, 4, 5}, Booklet.sheet(8, 1));", "Check.arrayEq(new int[] {6, 3, 5, 4}, Booklet.sheet(8, 1));"),
        ("test/BookletTest.java", '{5, 2}', '{5, 3}'),
        ("test/BookletTest.java", 'Check.eq("4,5,9-12,20", Booklet.compress(Arrays.asList(4, 5, 9, 10, 11, 12, 20)));', 'Check.eq("4-5,9-12,20", Booklet.compress(Arrays.asList(4, 5, 9, 10, 11, 12, 20)));'),
        ("test/BookletTest.java", "Check.eq(Arrays.asList(5, 1, 2), Booklet.parseRanges(\"5, 1 - 2\", 10));", "Check.eq(Arrays.asList(1, 2, 5), Booklet.parseRanges(\"5, 1 - 2\", 10));"),
        ("test/BookletTest.java", "Check.eq(3, Booklet.imposition(10).size());", "Check.eq(4, Booklet.imposition(10).size());"),
    ]
    return TLib(
        name="java-booklet", lang="java", title="the print shop's booklet imposition helpers", blurb="The imposition tool lays out saddle-stitched booklets and reads the page field of the print dialog.",
        files=files, stub={"test/SmokeTest.java": BK_STUB}, gold={"test/BookletTest.java": BK_TEST}, mutate=["src/print/Booklet.java"], cmd=langs.VERIFY["java"],
        where=WHERE_JAVA, difficulty=3, wrong_edits=wrong, timeout=60, protect=["src/print/*.java", *PROTECT_JAVA],
        strip_keep={"test/Check.java": CHECK, "test/TestMain.java": TESTMAIN},
        focus="where the blank pages land, the sheet layout formula, the grammar of the page field (order, duplicates, whitespace, bad items) and when a run becomes a range",
    )
