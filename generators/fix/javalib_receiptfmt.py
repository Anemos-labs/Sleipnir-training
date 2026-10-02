"""Fixed-width receipt layout: centring, padding, wrapping (java): bugs injected into a text-layout library."""
from fx import Lib, dd
from generators.fix._lang2 import JAVA_CHECK, java_test_main, register_libs

README = dd(r'''
    # receiptfmt

    Text layout for a till printer with a fixed number of characters per line. Plain Java 17, no dependencies; sources in
    `src/receipt/`.

    ## `Layout(int width)`

    `width` must be `16..80` (`IllegalArgumentException`). All methods return text of at most `width` characters per line.

    * `center(text)`: the text with `(width - length) / 2` spaces in front (integer division: an odd leftover space is *not*
      added; empty text therefore gives just those spaces). Text longer than `width` (or equal to it) is cut to its first
      `width` characters, without padding. Nothing is added after the text.
    * `leftRight(left, right)`: one line of exactly `width` characters with `left` at the left edge and `right` at the right
      edge, at least one space apart. `right` longer than `width - 2` is an `IllegalArgumentException`. If `left` and `right`
      cannot be separated by a space (`left.length() + 1 + right.length() > width`), `left` is cut to
      `width - 1 - right.length()` characters and its last remaining character is replaced by `~`.
    * `rule(c)`: `c` repeated `width` times.
    * `wrap(text, indent)`: breaks `text` into lines. `indent` is `0..width - 8` (`IllegalArgumentException`) and applies to every
      line except the first. Words are the pieces between runs of whitespace (leading and trailing whitespace is ignored;
      empty text gives an empty list). Words are put on a line separated by single spaces as long as the line stays within
      its capacity (`width` for the first line, `width - indent` after the indent); otherwise a new line starts. A word longer
      than the capacity of a full line is broken into pieces of exactly that capacity (each full piece on its own line); the
      last, shorter piece stays on its line and later words may follow it. A word that does not fit on the current line, but fits
      on a fresh one, moves to a fresh line first. Continuation lines start with `indent` spaces; no line has trailing spaces.
    * `itemLine(name, qty, unitCents)`: `leftRight(label, money(qty * unitCents))` where `label` is `name` when `qty == 1` and
      `qty + " x " + name` otherwise. `qty >= 1` and `unitCents >= 0` (`IllegalArgumentException`); the product is computed
      as a `long`.

    ## `Layout.money(long cents)`

    A static helper: `1234` is `"12.34"`, `5` is `"0.05"`, `0` is `"0.00"`, `-250` is `"-2.50"`, `100000` is `"1000.00"`
    (no thousands separator).
''')

LAYOUT = dd(r'''
    package receipt;

    import java.util.ArrayList;
    import java.util.List;

    public final class Layout {
        private final int width;

        public Layout(int width) {
            if (width < 16 || width > 80) {
                throw new IllegalArgumentException("width must be between 16 and 80");
            }
            this.width = width;
        }

        public static String money(long cents) {
            long abs = Math.abs(cents);
            long rest = abs % 100;
            return (cents < 0 ? "-" : "") + (abs / 100) + "." + (rest < 10 ? "0" : "") + rest;
        }

        private static String spaces(int n) {
            return " ".repeat(Math.max(0, n));
        }

        public String center(String text) {
            if (text.length() >= width) {
                return text.substring(0, width);
            }
            return spaces((width - text.length()) / 2) + text;
        }

        public String rule(char c) {
            return String.valueOf(c).repeat(width);
        }

        public String leftRight(String left, String right) {
            if (right.length() > width - 2) {
                throw new IllegalArgumentException("right part too long");
            }
            if (left.length() + 1 + right.length() <= width) {
                return left + spaces(width - left.length() - right.length()) + right;
            }
            int keep = width - 1 - right.length();
            return left.substring(0, keep - 1) + "~" + " " + right;
        }

        public String itemLine(String name, int qty, int unitCents) {
            if (qty < 1 || unitCents < 0) {
                throw new IllegalArgumentException("qty must be >= 1 and the price >= 0");
            }
            String label = qty == 1 ? name : qty + " x " + name;
            return leftRight(label, money((long) qty * unitCents));
        }

        private String lineOf(boolean first, int indent, CharSequence text) {
            return (first ? "" : spaces(indent)) + text;
        }

        public List<String> wrap(String text, int indent) {
            if (indent < 0 || indent > width - 8) {
                throw new IllegalArgumentException("indent out of range");
            }
            List<String> lines = new ArrayList<>();
            String trimmed = text.trim();
            if (trimmed.isEmpty()) {
                return lines;
            }
            StringBuilder line = new StringBuilder();
            boolean first = true;
            for (String word : trimmed.split("\\s+")) {
                String w = word;
                int cap = first ? width : width - indent;
                if (line.length() > 0 && line.length() + 1 + w.length() > cap) {
                    lines.add(lineOf(first, indent, line));
                    line.setLength(0);
                    first = false;
                    cap = width - indent;
                }
                while (w.length() > cap) {
                    lines.add(lineOf(first, indent, w.substring(0, cap)));
                    first = false;
                    w = w.substring(cap);
                    cap = width - indent;
                }
                if (line.length() > 0) {
                    line.append(' ');
                }
                line.append(w);
            }
            lines.add(lineOf(first, indent, line));
            return lines;
        }
    }
''')

BASIC = dd(r'''
    import receipt.Layout;

    public class BasicTests {
        public static void run() {
            Check.test("money", () -> {
                Check.eq("12.34", Layout.money(1234));
                Check.eq("0.05", Layout.money(5));
            });
            Check.test("leftRight", () -> {
                Layout l = new Layout(16);
                Check.eq("Latte       3.50", l.leftRight("Latte", "3.50"));
            });
        }
    }
''')

FULL = dd(r'''
    import java.util.List;
    import receipt.Layout;

    public class FullTests {
        public static void run() {
            Check.test("width limits", () -> {
                Check.raises(IllegalArgumentException.class, () -> new Layout(15));
                Check.raises(IllegalArgumentException.class, () -> new Layout(81));
                Check.raises(IllegalArgumentException.class, () -> new Layout(0));
                new Layout(16);
                new Layout(80);
            });

            Check.test("rule", () -> {
                Check.eq("----------------", new Layout(16).rule('-'));
                Check.eq("========================", new Layout(24).rule('='));
                Check.eq(80, new Layout(80).rule('*').length());
            });

            Check.test("wrap indent limits", () -> {
                Layout l = new Layout(16);
                Check.raises(IllegalArgumentException.class, () -> l.wrap("x", -1));
                Check.raises(IllegalArgumentException.class, () -> l.wrap("x", 9));
                Check.eq(List.of("x"), l.wrap("x", 8));
            });

            Check.test("leftRight needs room for the right part", () -> {
                Layout l = new Layout(20);
                Check.eq(20, l.leftRight("x", "123456789012345678").length());
            });

            Check.test("money", () -> {
                Check.eq("0.00", Layout.money(0L));
                Check.eq("0.05", Layout.money(5L));
                Check.eq("0.10", Layout.money(10L));
                Check.eq("0.99", Layout.money(99L));
                Check.eq("1.00", Layout.money(100L));
                Check.eq("1.01", Layout.money(101L));
                Check.eq("12.34", Layout.money(1234L));
                Check.eq("1000.00", Layout.money(100000L));
                Check.eq("-2.50", Layout.money(-250L));
                Check.eq("-0.05", Layout.money(-5L));
                Check.eq("-0.99", Layout.money(-99L));
                Check.eq("21474836.47", Layout.money(2147483647L));
                Check.eq("92233720368547758.07", Layout.money(9223372036854775807L));
                Check.eq("-1.00", Layout.money(-100L));
                Check.eq("-1.01", Layout.money(-101L));
            });

            Check.test("center", () -> {
                Layout l = new Layout(20);
                Check.eq("       TOTAL", l.center("TOTAL"));
                Check.eq("    Corner Cafe", l.center("Corner Cafe"));
                Check.eq("         Hi", l.center("Hi"));
                Check.eq("          ", l.center(""));
                Check.eq("        Odd", l.center("Odd"));
                Check.eq("12345678901234567890", l.center("12345678901234567890"));
                Check.eq("12345678901234567890", l.center("12345678901234567890XYZ"));
                Check.eq("1234567890123456789", l.center("1234567890123456789"));
                Check.eq("abcdefghijklmnopqrs", l.center("abcdefghijklmnopqrs"));
                Layout s = new Layout(16);
                Check.eq("      abc", s.center("abc"));
                Check.eq("      abcd", s.center("abcd"));
                Check.eq("     abcde", s.center("abcde"));
                Check.eq("     abcdef", s.center("abcdef"));
                Check.eq("0123456789ABCDEF", s.center("0123456789ABCDEF"));
                Check.eq("0123456789ABCDE", s.center("0123456789ABCDE"));
                Check.eq("0123456789ABCDEF", s.center("0123456789ABCDEFGHI"));
                Check.eq("       x", s.center("x"));
            });

            Check.test("leftRight", () -> {
                Layout l = new Layout(20);
                Check.eq("Latte           3.50", l.leftRight("Latte", "3.50"));
                Check.eq("a                  b", l.leftRight("a", "b"));
                Check.eq("12345678901234  3.50", l.leftRight("12345678901234", "3.50"));
                Check.eq("123456789012345 4.50", l.leftRight("123456789012345", "4.50"));
                Check.eq("12345678901234 14.50", l.leftRight("12345678901234", "14.50"));
                Check.eq("1234567890123 214.50", l.leftRight("1234567890123", "214.50"));
                Check.eq("                1.00", l.leftRight("", "1.00"));
                Check.eq("x 123456789012345678", l.leftRight("x", "123456789012345678"));
                Check.eq("                    ", l.leftRight("", ""));
                Check.eq("12345678901234~ 4.50", l.leftRight("1234567890123456", "4.50"));
                Check.eq("12345678901234~ 4.50", l.leftRight("12345678901234567", "4.50"));
                Check.eq("1234567890123~ 14.50", l.leftRight("12345678901234567890", "14.50"));
                Check.eq("~ 123456789012345678", l.leftRight("abcdefgh", "123456789012345678"));
                Check.eq("~ 123456789012345678", l.leftRight("xy", "123456789012345678"));
                Check.eq("a very long pr~ 9.99", l.leftRight("a very long product name indeed", "9.99"));
                Check.eq("1234567890123456 3.5", l.leftRight("1234567890123456", "3.5"));
                Check.eq("123456789012345~ 3.5", l.leftRight("12345678901234567", "3.5"));
                Check.raises(IllegalArgumentException.class, () -> l.leftRight("x", "1234567890123456789"));
                Check.raises(IllegalArgumentException.class, () -> l.leftRight("x", "1234567890123456789012"));
            });

            Check.test("item lines", () -> {
                Layout l = new Layout(24);
                Check.eq("Latte               3.50", l.itemLine("Latte", 1, 350));
                Check.eq("2 x Latte           7.00", l.itemLine("Latte", 2, 350));
                Check.eq("3 x Muffin         10.50", l.itemLine("Muffin", 3, 350));
                Check.eq("Free sample         0.00", l.itemLine("Free sample", 1, 0));
                Check.eq("100 x Tea        1500.00", l.itemLine("Tea", 100, 1500));
                Check.eq("2 x Very long coff~ 9.90", l.itemLine("Very long coffee name", 2, 495));
                Check.eq("5000 x Pen     214700.00", l.itemLine("Pen", 5000, 4294));
                Layout wide = new Layout(40);
                Check.eq("2 x Gold bar                 42949672.94", wide.itemLine("Gold bar", 2, 2147483647));
                Check.raises(IllegalArgumentException.class, () -> wide.itemLine("x", 0, 100));
                Check.raises(IllegalArgumentException.class, () -> wide.itemLine("x", -1, 100));
                Check.raises(IllegalArgumentException.class, () -> wide.itemLine("x", 1, -1));
            });

            Check.test("wrap", () -> {
                Layout w16 = new Layout(16);
                Layout w20 = new Layout(20);
                Layout w24 = new Layout(24);
                Layout w32 = new Layout(32);
                Check.eq(List.of("The quick brown", "fox jumps over", "the lazy dog"), w16.wrap("The quick brown fox jumps over the lazy dog", 0));
                Check.eq(List.of("The quick brown", "    fox jumps", "    over the", "    lazy dog"), w16.wrap("The quick brown fox jumps over the lazy dog", 4));
                Check.eq(List.of("hello world"), w16.wrap("hello world", 0));
                Check.eq(List.of(), w16.wrap("", 0));
                Check.eq(List.of(), w16.wrap("   \t  ", 0));
                Check.eq(List.of("one two three"), w16.wrap("  one   two\tthree  ", 0));
                Check.eq(List.of("aaaaaaa bbbbbbbb", "c"), w16.wrap("aaaaaaa bbbbbbbb c", 0));
                Check.eq(List.of("aaaaaaa", "bbbbbbbbb c"), w16.wrap("aaaaaaa bbbbbbbbb c", 0));
                Check.eq(List.of("1234567890123456"), w16.wrap("1234567890123456", 0));
                Check.eq(List.of("12345678901234", "ab"), w16.wrap("12345678901234 ab", 0));
                Check.eq(List.of("12345678901234 a", "b"), w16.wrap("12345678901234 a b", 0));
                Check.eq(List.of("aaaa bbbb cccc", "  ddddd eeeee", "  fffff"), w16.wrap("aaaa bbbb cccc ddddd eeeee fffff", 2));
                Check.eq(List.of("one two three"), w16.wrap("one two three", 2));
                Check.eq(List.of("x"), w16.wrap("x", 8));
                Check.eq(List.of("abcdefghijklmnop", "qrstuvwxyz"), w16.wrap("abcdefghijklmnopqrstuvwxyz", 0));
                Check.eq(List.of("abcdefghijklmnop", "qrstuvwxyz hi"), w16.wrap("abcdefghijklmnopqrstuvwxyz hi", 0));
                Check.eq(List.of("hi", "abcdefghijklmnop", "qrstuvwxyz"), w16.wrap("hi abcdefghijklmnopqrstuvwxyz", 0));
                Check.eq(List.of("abcdefghijklmnop", "abcdefghijklmnop", "abc"), w16.wrap("abcdefghijklmnopabcdefghijklmnopabc", 0));
                Check.eq(List.of("abcdefghijklmnop", "abcdefghijklmnop"), w16.wrap("abcdefghijklmnopabcdefghijklmnop", 0));
                Check.eq(List.of("abcdefghijklmnop", "    qrstuvwxyz", "    hi"), w16.wrap("abcdefghijklmnopqrstuvwxyz hi", 4));
                Check.eq(List.of("see", "    0123456789ab", "    cdefghij"), w16.wrap("see 0123456789abcdefghij", 4));
                Check.eq(List.of("hi", "    0123456789ab", "    cdefghijklmn", "    o"), w16.wrap("hi 0123456789abcdefghijklmno", 4));
                Check.eq(List.of("0123456789abcdef", "        ghijklmn", "        opqrstuv", "        wxyz"), w16.wrap("0123456789abcdefghijklmnopqrstuvwxyz", 8));
                Check.eq(List.of("a b c d e f g h", "i j k l m n o p", "q r s t u v w x", "y z"), w16.wrap("a b c d e f g h i j k l m n o p q r s t u v w x y z", 0));
                Check.eq(List.of("a b c d e f g h", "      i j k l m", "      n o p q r", "      s t u v w", "      x y z"), w16.wrap("a b c d e f g h i j k l m n o p q r s t u v w x y z", 6));
                Check.eq(List.of("Total due within 30 days", "     of the invoice", "     date. Late payments", "     incur a fee of 2%", "     per month."), w24.wrap("Total due within 30 days of the invoice date. Late payments incur a fee of 2% per month.", 5));
                Check.eq(List.of("bcrdlsbqgbcnnchcrnbsdhu", "    sbssmbhbrejnerdsjrvf", "    dss", "    gldrwcsbtgpvrnykosol", "    jhz wyh sj", "    pkxojtcdqnfyke", "    nbvcyrszkkw tpszoc", "    ip"), w24.wrap("bcrdlsbqgbcnnchcrnbsdhu sbssmbhbrejnerdsjrvfdss gldrwcsbtgpvrnykosoljhz wyh sj pkxojtcdqnfyke nbvcyrszkkw tpszoc ip", 4));
                Check.eq(List.of("svojwmvlaolftdpb", "gyjexhm pcfomrie", "riwnlvmh cfe", "vhap", "fijaenrltskewqtu", "vxb yvzrmmmmdpu"), w16.wrap("svojwmvlaolftdpbgyjexhm pcfomrie riwnlvmh cfe vhap fijaenrltskewqtuvxb yvzrmmmmdpu", 0));
                Check.eq(List.of("go dkt d s rdl", " acgtmeuiltlpddpoppj"), w32.wrap("go dkt d s rdl acgtmeuiltlpddpoppj", 1));
                Check.eq(List.of("kxipwfqagqlewray", "  qjucwiqlflyhrr", "  y", "  kuhtzzygzhmxzh", "  qplx a"), w16.wrap("kxipwfqagqlewrayqjucwiqlflyhrry kuhtzzygzhmxzh qplx a", 2));
                Check.eq(List.of("wtlo", "               llchdhpgk", "               gpttapulz", "               ucvdmzwyg", "               pfnz", "               kczxmomxc", "               xffeaesoz", "               uettp", "               lerreaazx", "               udqxengga", "               igjqh", "               kirnebxlo", "               vsqnqereq", "               q o tay"), w24.wrap("wtlo llchdhpgkgpttapulzucvdmzwygpfnz kczxmomxcxffeaesozuettp lerreaazxudqxenggaigjqh kirnebxlovsqnqereqq o tay", 15));
                Check.eq(List.of("txdrbkvqqrp rb giby", "  qo aycoktqtqgwioq"), w20.wrap("txdrbkvqqrp rb giby qo aycoktqtqgwioq", 2));
                Check.eq(List.of("qirgoendmokcvhncgvjzdyewuvleieo", "                xdmp vhf", "                nqmknglkcxlakroo", "                wamkqtjqcdzhdci", "                byfiy nvi"), w32.wrap("qirgoendmokcvhncgvjzdyewuvleieo xdmp vhf nqmknglkcxlakroowamkqtjqcdzhdci byfiy nvi", 16));
                Check.eq(List.of("spwkcibzwfncia", "    czicthcidoakrnitebqwhdf", "    bfgju qygjo vfilzaibaaxqrg", "    phodvunvprmqjw hkgw", "    uemlbeacuxinfbcvmqvjthwjboff", "    ioa lkrkh j lfak"), w32.wrap("spwkcibzwfncia czicthcidoakrnitebqwhdf bfgju qygjo vfilzaibaaxqrg phodvunvprmqjw hkgw uemlbeacuxinfbcvmqvjthwjboffioa lkrkh j lfak", 4));
                Check.eq(List.of("qughq c cemsb ajjuhcsq vwz", "  mykxpejxtuebwqunxwz", "  eqyqszavszwvwu cabe", "  ldmorbuaurvhpiaozcxqrcv", "  cxxpizcihxyghx"), w32.wrap("qughq c cemsb ajjuhcsq vwz mykxpejxtuebwqunxwz eqyqszavszwvwu cabe ldmorbuaurvhpiaozcxqrcv cxxpizcihxyghx", 2));
                Check.eq(List.of("pv ybtuu ctek uxwjt", "               eapbpivdwgvpjwqjo", "               oo rg cpajo qo", "               mggcs"), w32.wrap("pv ybtuu ctek uxwjt eapbpivdwgvpjwqjooo rg cpajo qo mggcs", 15));
            });
        }
    }
''')

LIB = Lib(
    name="receiptfmt", lang="java", title="the receiptfmt layout library",
    blurb="The till software prints receipts with receiptfmt: centred headers, item lines with prices at the right edge, wrapped notes.",
    files={"src/receipt/Layout.java": LAYOUT, "README.md": README, ".gitignore": "build/\n"},
    visible_tests={"test/Check.java": JAVA_CHECK, "test/BasicTests.java": BASIC, "test/TestMain.java": java_test_main("BasicTests")},
    hidden_tests={"test/FullTests.java": FULL, "test/TestMain.java": java_test_main("BasicTests", "FullTests")},
    mutate=["src/receipt/Layout.java"], difficulty=1, tags=["formatting", "text-layout", "printing"],
    probe_import="import java.util.*;\nimport receipt.*;",
    probes=[
        "Layout.money(5)", "Layout.money(-250)", "Layout.money(100000)", "Layout.money(99)",
        "new Layout(16).center(\"abcd\")", "new Layout(16).center(\"0123456789ABCDEFG\")", "new Layout(20).center(\"Corner Cafe\")",
        "new Layout(20).leftRight(\"Latte\", \"3.50\")", "new Layout(20).leftRight(\"123456789012345\", \"4.50\")", "new Layout(20).leftRight(\"1234567890123456\", \"4.50\")", "new Layout(20).leftRight(\"x\", \"1234567890123456789\")",
        "new Layout(24).itemLine(\"Muffin\", 3, 350)", "new Layout(24).itemLine(\"Tea\", 100, 1500)", "new Layout(24).itemLine(\"Latte\", 0, 350)",
        "new Layout(16).wrap(\"The quick brown fox jumps over the lazy dog\", 0)", "new Layout(16).wrap(\"The quick brown fox jumps over the lazy dog\", 4)",
        "new Layout(16).wrap(\"aaaaaaa bbbbbbbb c\", 0)", "new Layout(16).wrap(\"12345678901234 a b\", 0)", "new Layout(16).wrap(\"abcdefghijklmnopqrstuvwxyz hi\", 0)",
        "new Layout(16).wrap(\"hi abcdefghijklmnopqrstuvwxyz\", 0)", "new Layout(16).wrap(\"abcdefghijklmnopabcdefghijklmnop\", 0)", "new Layout(16).wrap(\"hi 0123456789abcdefghijklmno\", 4)", "new Layout(16).wrap(\"x\", 9)",
    ],
)

register_libs([LIB], n=8)
