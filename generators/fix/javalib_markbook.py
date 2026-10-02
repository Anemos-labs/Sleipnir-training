"""Weighted gradebook with dropped scores and letter bands (java): bugs injected into a grading library."""
from fx import Lib, dd
from generators.fix._lang2 import JAVA_CHECK, java_test_main, register_libs

README = dd(r'''
    # markbook

    The grade calculator of a school's report system. Plain Java 17, no dependencies; sources in `src/grades/`.
    Percentages are `int` **basis points** (hundredths of a percent): `8735` is 87.35 %, `10000` is 100 %.

    ## `Score(Integer earned, int possible, boolean excused)`

    `possible >= 1`; `earned` is `null` for a *missing* work (it counts as 0 points) or an integer `>= 0` (it may exceed
    `possible`: extra credit). A violation is an `IllegalArgumentException`. Fields are public and final.

    ## `Category(String name, int weightPct, int dropLowest)`

    `weightPct` is `0..100` and `dropLowest >= 0`, else `IllegalArgumentException`.

    ## `Gradebook`

    * `categoryBp(category, scores)`:
      1. excused scores are ignored completely;
      2. of the remaining `n` scores, `min(dropLowest, n - 1)` are dropped (the last remaining score is never dropped): the ones
         with the lowest ratio `earned / possible` (missing counts as `0`); ratios are compared exactly (cross-multiplied) and
         ties drop the score that comes earlier in the list;
      3. the result is `roundDiv(sumEarned * 10000, sumPossible)` over the kept scores (points are added up, percentages are *not*
         averaged), rounded half up; `-1` (`Gradebook.NO_GRADE`) when nothing is left (no scores, or all excused).
    * `finalBp(categories, scoresByCategory)`: the category weights must add up to exactly 100 (`IllegalArgumentException`
      otherwise). Every category that has a grade (`categoryBp >= 0`; categories missing from the map have no scores) takes
      part with its weight; the result is `roundDiv(sum(bp * weight), sum(weights of the graded categories))`, or `-1` if no
      category has a grade. Categories without a grade are left out and the remaining weights count in proportion.
    * `curve(bp, points)`: adds `points` basis points, but never beyond `10000`; `points < 0` or `bp < 0` is an
      `IllegalArgumentException`.
    * `roundDiv(n, d)`: `n / d` rounded half up for `n >= 0`, `d > 0`.

    ## `Letters`

    * `letter(bp)`: `bp` must be in `0..10000` (else `IllegalArgumentException`). The base letter is `A` from 9000, `B` from 8000,
      `C` from 7000, `D` from 6000, otherwise `F`. For A to D a `+` is added when `bp >= floor + 700` and a `-` when
      `bp < floor + 300`, where `floor` is the lowest value of the letter's band (`A+` from 9700, `A-` below 9300). `F` never has
      a sign.
    * `format(bp)`: `bp` as a percentage with two decimals: `8735` is `"87.35%"`, `5` is `"0.05%"`, `10000` is `"100.00%"`, `-1` is `"n/a"`.
      Other negative values or values above `20000` are an `IllegalArgumentException` (extra credit can exceed 100 %).
''')

SCORE = dd(r'''
    package grades;

    public final class Score {
        public final Integer earned;
        public final int possible;
        public final boolean excused;

        public Score(Integer earned, int possible, boolean excused) {
            if (possible < 1) {
                throw new IllegalArgumentException("possible points must be at least 1");
            }
            if (earned != null && earned < 0) {
                throw new IllegalArgumentException("earned points must not be negative");
            }
            this.earned = earned;
            this.possible = possible;
            this.excused = excused;
        }

        public int points() {
            return earned == null ? 0 : earned;
        }
    }
''')

CATEGORY = dd(r'''
    package grades;

    public final class Category {
        public final String name;
        public final int weightPct;
        public final int dropLowest;

        public Category(String name, int weightPct, int dropLowest) {
            if (weightPct < 0 || weightPct > 100) {
                throw new IllegalArgumentException("weight must be between 0 and 100");
            }
            if (dropLowest < 0) {
                throw new IllegalArgumentException("dropLowest must not be negative");
            }
            this.name = name;
            this.weightPct = weightPct;
            this.dropLowest = dropLowest;
        }
    }
''')

GRADEBOOK = dd(r'''
    package grades;

    import java.util.ArrayList;
    import java.util.List;
    import java.util.Map;

    public final class Gradebook {
        public static final int NO_GRADE = -1;

        private Gradebook() {}

        public static int roundDiv(long n, long d) {
            return (int) ((2 * n + d) / (2 * d));
        }

        public static int categoryBp(Category category, List<Score> scores) {
            List<Score> live = new ArrayList<>();
            for (Score s : scores) {
                if (!s.excused) {
                    live.add(s);
                }
            }
            int drop = Math.min(category.dropLowest, live.size() - 1);
            for (int round = 0; round < drop; round++) {
                int worst = 0;
                for (int i = 1; i < live.size(); i++) {
                    Score a = live.get(i);
                    Score b = live.get(worst);
                    // a is worse than b when a.points / a.possible < b.points / b.possible
                    if ((long) a.points() * b.possible < (long) b.points() * a.possible) {
                        worst = i;
                    }
                }
                live.remove(worst);
            }
            long earned = 0;
            long possible = 0;
            for (Score s : live) {
                earned += s.points();
                possible += s.possible;
            }
            if (possible == 0) {
                return NO_GRADE;
            }
            return roundDiv(earned * 10000, possible);
        }

        public static int finalBp(List<Category> categories, Map<String, List<Score>> scores) {
            int total = 0;
            for (Category c : categories) {
                total += c.weightPct;
            }
            if (total != 100) {
                throw new IllegalArgumentException("weights must add up to 100");
            }
            long weighted = 0;
            long weights = 0;
            for (Category c : categories) {
                List<Score> list = scores.get(c.name);
                if (list == null) {
                    continue;
                }
                int bp = categoryBp(c, list);
                if (bp >= 0) {
                    weighted += (long) bp * c.weightPct;
                    weights += c.weightPct;
                }
            }
            if (weights == 0) {
                return NO_GRADE;
            }
            return roundDiv(weighted, weights);
        }

        public static int curve(int bp, int points) {
            if (bp < 0 || points < 0) {
                throw new IllegalArgumentException("bp and points must not be negative");
            }
            return Math.min(10000, bp + points);
        }
    }
''')

LETTERS = dd(r'''
    package grades;

    public final class Letters {
        private Letters() {}

        public static String letter(int bp) {
            if (bp < 0 || bp > 10000) {
                throw new IllegalArgumentException("bp must be between 0 and 10000");
            }
            int floor;
            String base;
            if (bp >= 9000) {
                floor = 9000;
                base = "A";
            } else if (bp >= 8000) {
                floor = 8000;
                base = "B";
            } else if (bp >= 7000) {
                floor = 7000;
                base = "C";
            } else if (bp >= 6000) {
                floor = 6000;
                base = "D";
            } else {
                return "F";
            }
            if (bp >= floor + 700) {
                return base + "+";
            }
            if (bp < floor + 300) {
                return base + "-";
            }
            return base;
        }

        public static String format(int bp) {
            if (bp == -1) {
                return "n/a";
            }
            if (bp < 0 || bp > 20000) {
                throw new IllegalArgumentException("bp out of range");
            }
            int cents = bp % 100;
            return (bp / 100) + "." + (cents < 10 ? "0" : "") + cents + "%";
        }
    }
''')

BASIC = dd(r'''
    import grades.Letters;

    public class BasicTests {
        public static void run() {
            Check.test("letters", () -> {
                Check.eq("A+", Letters.letter(9700));
                Check.eq("F", Letters.letter(5999));
            });
            Check.test("format", () -> Check.eq("87.35%", Letters.format(8735)));
        }
    }
''')

FULL = dd(r'''
    import grades.Category;
    import grades.Gradebook;
    import grades.Letters;
    import grades.Score;
    import java.util.ArrayList;
    import java.util.HashMap;
    import java.util.List;
    import java.util.Map;

    public class FullTests {
        static Score s(int earned, int possible) {
            return new Score(earned, possible, false);
        }

        static Score missing(int possible) {
            return new Score(null, possible, false);
        }

        static Score excused(int possible) {
            return new Score(0, possible, true);
        }

        static List<Score> list(Score... scores) {
            List<Score> l = new ArrayList<>();
            for (Score x : scores) {
                l.add(x);
            }
            return l;
        }

        static Category cat(int weight, int drop) {
            return new Category("c", weight, drop);
        }

        public static void run() {
            Check.test("score validation", () -> {
                Check.raises(IllegalArgumentException.class, () -> new Score(5, 0, false));
                Check.raises(IllegalArgumentException.class, () -> new Score(5, -1, false));
                Check.raises(IllegalArgumentException.class, () -> new Score(-1, 10, false));
                Check.eq(0, new Score(null, 10, false).points());
                Check.eq(12, new Score(12, 10, false).points());
                Check.eq(0, new Score(0, 1, false).points());
            });

            Check.test("category validation", () -> {
                Check.raises(IllegalArgumentException.class, () -> new Category("x", -1, 0));
                Check.raises(IllegalArgumentException.class, () -> new Category("x", 101, 0));
                Check.raises(IllegalArgumentException.class, () -> new Category("x", 10, -1));
                new Category("x", 0, 0);
                new Category("x", 100, 5);
            });

            Check.test("roundDiv", () -> {
                Check.eq(0, Gradebook.roundDiv(0, 5));
                Check.eq(0, Gradebook.roundDiv(2, 5));
                Check.eq(1, Gradebook.roundDiv(3, 5));
                Check.eq(1, Gradebook.roundDiv(1, 2));
                Check.eq(2, Gradebook.roundDiv(3, 2));
                Check.eq(7, Gradebook.roundDiv(20, 3));
                Check.eq(6, Gradebook.roundDiv(19, 3));
            });

            Check.test("category: points are added, not averaged", () -> {
                Check.eq(6571, Gradebook.categoryBp(cat(100, 0), list(s(8, 10), s(15, 20), s(0, 5))));
                Check.eq(8000, Gradebook.categoryBp(cat(100, 0), list(s(8, 10))));
                Check.eq(10000, Gradebook.categoryBp(cat(100, 0), list(s(10, 10))));
                Check.eq(0, Gradebook.categoryBp(cat(100, 0), list(s(0, 10))));
                Check.eq(3333, Gradebook.categoryBp(cat(100, 0), list(s(1, 3))));
                Check.eq(6667, Gradebook.categoryBp(cat(100, 0), list(s(2, 3))));
            });

            Check.test("category: extra credit and missing work", () -> {
                Check.eq(12000, Gradebook.categoryBp(cat(100, 0), list(s(12, 10))));
                Check.eq(5000, Gradebook.categoryBp(cat(100, 0), list(s(10, 10), missing(10))));
                Check.eq(0, Gradebook.categoryBp(cat(100, 0), list(missing(10))));
                Check.eq(10500, Gradebook.categoryBp(cat(100, 0), list(s(11, 10), s(10, 10))));
            });

            Check.test("category: excused scores vanish", () -> {
                Check.eq(Gradebook.NO_GRADE, Gradebook.categoryBp(cat(100, 0), list()));
                Check.eq(Gradebook.NO_GRADE, Gradebook.categoryBp(cat(100, 0), list(excused(10))));
                Check.eq(Gradebook.NO_GRADE, Gradebook.categoryBp(cat(100, 2), list(excused(10), excused(5))));
                Check.eq(9000, Gradebook.categoryBp(cat(100, 0), list(s(9, 10), excused(100))));
                Check.eq(8000, Gradebook.categoryBp(cat(100, 1), list(s(8, 10), excused(50), s(1, 10))));
            });

            Check.test("category: dropping the lowest", () -> {
                List<Score> three = list(s(8, 10), s(15, 20), s(0, 5));
                Check.eq(6571, Gradebook.categoryBp(cat(100, 0), three));
                Check.eq(7667, Gradebook.categoryBp(cat(100, 1), three));
                Check.eq(8000, Gradebook.categoryBp(cat(100, 2), three));
                Check.eq(8000, Gradebook.categoryBp(cat(100, 5), three));
                Check.eq(8000, Gradebook.categoryBp(cat(100, 1), list(s(7, 10), missing(10), s(9, 10))));
                Check.eq(3, three.size());
            });

            Check.test("category: the lowest is found by ratio, not by points", () -> {
                Check.eq(10000, Gradebook.categoryBp(cat(100, 1), list(s(1, 2), s(10, 10), s(90, 90))));
                Check.eq(10000, Gradebook.categoryBp(cat(100, 1), list(s(90, 90), s(1, 2), s(10, 10))));
                Check.eq(10000, Gradebook.categoryBp(cat(100, 1), list(s(10, 10), s(90, 90), s(1, 2))));
                Check.eq(9500, Gradebook.categoryBp(cat(100, 1), list(s(19, 20), s(1, 10), s(19, 20))));
                Check.eq(9500, Gradebook.categoryBp(cat(100, 2), list(s(9, 10), s(10, 10), s(0, 10), s(2, 10), s(19, 20))));
            });

            Check.test("category: ties drop the earlier score", () -> {
                // ratios 0.5, 0.5, 0.5 and 1: the first (5/10) goes, leaving 10/20 + 1/2 + 10/10 = 21/32
                Check.eq(6563, Gradebook.categoryBp(cat(100, 1), list(s(5, 10), s(10, 20), s(1, 2), s(10, 10))));
                // 1/2 at index 1 is dropped, not 2/4 at index 2: 10 + 2 + 1 = 13 of 10 + 4 + 2 = 16
                Check.eq(8125, Gradebook.categoryBp(cat(100, 1), list(s(10, 10), s(1, 2), s(2, 4), s(1, 2))));
            });

            Check.test("category: dropping several", () -> {
                List<Score> five = list(s(9, 10), s(10, 10), s(0, 10), s(2, 10), s(19, 20));
                Check.eq(9500, Gradebook.categoryBp(cat(100, 2), five));
                Check.eq(9667, Gradebook.categoryBp(cat(100, 3), five));
                Check.eq(10000, Gradebook.categoryBp(cat(100, 4), five));
            });

            Check.test("final grade", () -> {
                List<Category> cats = new ArrayList<>();
                cats.add(new Category("homework", 20, 1));
                cats.add(new Category("quizzes", 20, 0));
                cats.add(new Category("exams", 60, 0));
                Map<String, List<Score>> sc = new HashMap<>();
                sc.put("homework", list(s(9, 10), s(4, 10), s(10, 10)));
                sc.put("quizzes", list(s(7, 10), s(8, 10)));
                sc.put("exams", list(s(78, 100), s(91, 100)));
                Check.eq(9500, Gradebook.categoryBp(cats.get(0), sc.get("homework")));
                Check.eq(7500, Gradebook.categoryBp(cats.get(1), sc.get("quizzes")));
                Check.eq(8450, Gradebook.categoryBp(cats.get(2), sc.get("exams")));
                Check.eq(8470, Gradebook.finalBp(cats, sc));
            });

            Check.test("final grade: categories without scores are left out", () -> {
                List<Category> cats = new ArrayList<>();
                cats.add(new Category("homework", 20, 1));
                cats.add(new Category("quizzes", 20, 0));
                cats.add(new Category("exams", 60, 0));
                Map<String, List<Score>> sc = new HashMap<>();
                sc.put("homework", list(s(9, 10)));
                sc.put("exams", list(s(70, 100)));
                Check.eq(7500, Gradebook.finalBp(cats, sc));
                sc.put("quizzes", list(excused(10)));
                Check.eq(7500, Gradebook.finalBp(cats, sc));
                sc.put("quizzes", list());
                Check.eq(7500, Gradebook.finalBp(cats, sc));
                Check.eq(Gradebook.NO_GRADE, Gradebook.finalBp(cats, new HashMap<>()));
                Map<String, List<Score>> only = new HashMap<>();
                only.put("quizzes", list(s(1, 3)));
                Check.eq(3333, Gradebook.finalBp(cats, only));
            });

            Check.test("final grade: a zero weight category does not count", () -> {
                List<Category> cats = new ArrayList<>();
                cats.add(new Category("main", 100, 0));
                cats.add(new Category("extra", 0, 0));
                Map<String, List<Score>> sc = new HashMap<>();
                sc.put("main", list(s(8, 10)));
                sc.put("extra", list(s(0, 10)));
                Check.eq(8000, Gradebook.finalBp(cats, sc));
                Map<String, List<Score>> extraOnly = new HashMap<>();
                extraOnly.put("extra", list(s(5, 10)));
                Check.eq(Gradebook.NO_GRADE, Gradebook.finalBp(cats, extraOnly));
            });

            Check.test("final grade: weights must add up to 100", () -> {
                List<Category> low = new ArrayList<>();
                low.add(new Category("a", 50, 0));
                low.add(new Category("b", 49, 0));
                Check.raises(IllegalArgumentException.class, () -> Gradebook.finalBp(low, new HashMap<>()));
                List<Category> high = new ArrayList<>();
                high.add(new Category("a", 60, 0));
                high.add(new Category("b", 41, 0));
                Check.raises(IllegalArgumentException.class, () -> Gradebook.finalBp(high, new HashMap<>()));
                List<Category> ok = new ArrayList<>();
                ok.add(new Category("a", 33, 0));
                ok.add(new Category("b", 33, 0));
                ok.add(new Category("c", 34, 0));
                Map<String, List<Score>> sc = new HashMap<>();
                sc.put("a", list(s(1, 1)));
                sc.put("b", list(s(0, 1)));
                sc.put("c", list(s(1, 1)));
                Check.eq(6700, Gradebook.finalBp(ok, sc));
            });

            Check.test("final grade rounds half up", () -> {
                List<Category> cats = new ArrayList<>();
                cats.add(new Category("a", 50, 0));
                cats.add(new Category("b", 50, 0));
                Map<String, List<Score>> sc = new HashMap<>();
                sc.put("a", list(s(1, 3)));
                sc.put("b", list(s(1, 2)));
                // (3333 * 50 + 5000 * 50) / 100 = 4166.5 -> 4167
                Check.eq(4167, Gradebook.finalBp(cats, sc));
            });

            Check.test("curve", () -> {
                Check.eq(8500, Gradebook.curve(8000, 500));
                Check.eq(8000, Gradebook.curve(8000, 0));
                Check.eq(10000, Gradebook.curve(9900, 500));
                Check.eq(10000, Gradebook.curve(9500, 500));
                Check.eq(9999, Gradebook.curve(9500, 499));
                Check.eq(10000, Gradebook.curve(10000, 100));
                Check.eq(500, Gradebook.curve(0, 500));
                Check.raises(IllegalArgumentException.class, () -> Gradebook.curve(8000, -1));
                Check.raises(IllegalArgumentException.class, () -> Gradebook.curve(-1, 100));
            });

            Check.test("letters", () -> {
                String[][] cases = {
                    {"10000", "A+"}, {"9700", "A+"}, {"9699", "A"}, {"9300", "A"}, {"9299", "A-"}, {"9000", "A-"},
                    {"8999", "B+"}, {"8700", "B+"}, {"8699", "B"}, {"8300", "B"}, {"8299", "B-"}, {"8000", "B-"},
                    {"7999", "C+"}, {"7700", "C+"}, {"7699", "C"}, {"7300", "C"}, {"7299", "C-"}, {"7000", "C-"},
                    {"6999", "D+"}, {"6700", "D+"}, {"6699", "D"}, {"6300", "D"}, {"6299", "D-"}, {"6000", "D-"},
                    {"5999", "F"}, {"3000", "F"}, {"0", "F"},
                };
                for (String[] c : cases) {
                    Check.eq("bp " + c[0], c[1], Letters.letter(Integer.parseInt(c[0])));
                }
            });

            Check.test("letter range", () -> {
                Check.raises(IllegalArgumentException.class, () -> Letters.letter(-1));
                Check.raises(IllegalArgumentException.class, () -> Letters.letter(10001));
                Check.eq("A+", Letters.letter(10000));
            });

            Check.test("format", () -> {
                Check.eq("87.35%", Letters.format(8735));
                Check.eq("0.05%", Letters.format(5));
                Check.eq("0.00%", Letters.format(0));
                Check.eq("0.10%", Letters.format(10));
                Check.eq("0.99%", Letters.format(99));
                Check.eq("1.00%", Letters.format(100));
                Check.eq("1.01%", Letters.format(101));
                Check.eq("100.00%", Letters.format(10000));
                Check.eq("66.70%", Letters.format(6670));
                Check.eq("120.00%", Letters.format(12000));
                Check.eq("200.00%", Letters.format(20000));
                Check.eq("n/a", Letters.format(Gradebook.NO_GRADE));
                Check.raises(IllegalArgumentException.class, () -> Letters.format(-2));
                Check.raises(IllegalArgumentException.class, () -> Letters.format(20001));
            });
        }
    }
''')

LIB = Lib(
    name="markbook", lang="java", title="the markbook library",
    blurb="The school's report system computes weighted course grades with markbook and prints them as letters and percentages.",
    files={"src/grades/Score.java": SCORE, "src/grades/Category.java": CATEGORY, "src/grades/Gradebook.java": GRADEBOOK,
           "src/grades/Letters.java": LETTERS, "README.md": README, ".gitignore": "build/\n"},
    visible_tests={"test/Check.java": JAVA_CHECK, "test/BasicTests.java": BASIC, "test/TestMain.java": java_test_main("BasicTests")},
    hidden_tests={"test/FullTests.java": FULL, "test/TestMain.java": java_test_main("BasicTests", "FullTests")},
    mutate=["src/grades/Gradebook.java", "src/grades/Letters.java", "src/grades/Score.java"], difficulty=2, tags=["education", "grades", "weights"],
    probe_import="import java.util.*;\nimport grades.*;",
    probes=[
        "Letters.letter(9699)", "Letters.letter(9300)", "Letters.letter(8000)", "Letters.letter(6999)", "Letters.letter(6000)", "Letters.letter(5999)", "Letters.letter(10001)",
        "Letters.format(5)", "Letters.format(8735)", "Letters.format(100)", "Letters.format(-1)", "Letters.format(20001)",
        "Gradebook.roundDiv(3, 2)", "Gradebook.curve(9500, 499)", "Gradebook.curve(9900, 500)", "Gradebook.curve(8000, -1)",
        "Gradebook.categoryBp(new Category(\"c\", 100, 0), List.of(new Score(8, 10, false), new Score(15, 20, false), new Score(0, 5, false)))",
        "Gradebook.categoryBp(new Category(\"c\", 100, 1), List.of(new Score(8, 10, false), new Score(15, 20, false), new Score(0, 5, false)))",
        "Gradebook.categoryBp(new Category(\"c\", 100, 1), List.of(new Score(1, 2, false), new Score(10, 10, false), new Score(90, 90, false)))",
        "Gradebook.categoryBp(new Category(\"c\", 100, 1), List.of(new Score(5, 10, false), new Score(10, 20, false), new Score(1, 2, false), new Score(10, 10, false)))",
        "Gradebook.categoryBp(new Category(\"c\", 100, 0), List.of(new Score(9, 10, false), new Score(0, 100, true)))",
        "Gradebook.categoryBp(new Category(\"c\", 100, 0), List.of(new Score(0, 10, true)))",
        "Gradebook.categoryBp(new Category(\"c\", 100, 3), List.of(new Score(9, 10, false), new Score(10, 10, false), new Score(0, 10, false), new Score(2, 10, false), new Score(19, 20, false)))",
        "Gradebook.finalBp(List.of(new Category(\"a\", 50, 0), new Category(\"b\", 50, 0)), Map.of(\"a\", List.of(new Score(1, 3, false)), \"b\", List.of(new Score(1, 2, false))))",
        "Gradebook.finalBp(List.of(new Category(\"a\", 20, 0), new Category(\"b\", 80, 0)), Map.of(\"a\", List.of(new Score(9, 10, false))))",
        "Gradebook.finalBp(List.of(new Category(\"a\", 50, 0), new Category(\"b\", 49, 0)), Map.of())",
    ],
)

register_libs([LIB], n=8)
