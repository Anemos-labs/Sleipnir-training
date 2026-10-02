"""Ticket codes with a check letter (java): bugs injected into a tiny code generator and parser."""
from fx import Lib, dd
from generators.fix._lang2 import JAVA_CHECK, java_test_main, register_libs

README = dd(r'''
    # ticketcode

    Support-ticket codes such as `TK-123456T`, read aloud over the phone and typed back by hand. Plain Java 17, no
    dependencies; sources in `src/tickets/`.

    A code is `TK-`, six digits, and a **check letter**. The check letter comes from the 24-letter alphabet
    `ABCDEFGHJKLMNPQRSTUVWXYZ` (no `I` and no `O`): multiply the six digits, left to right, by the weights `7 3 1 7 3 1`, add
    the products up, and take the letter at index `sum % 24` (`A` is index 0). For `123456` the sum is 65, `65 % 24 = 17`, the
    letter is `T`.

    ## `Codes`

    * `check(digits)`: the check letter for a string of exactly six digits (`IllegalArgumentException` otherwise).
    * `encode(n)`: the code for ticket number `n`, `0..999999` (else `IllegalArgumentException`): `TK-` plus `n` padded with zeros
      to six digits plus the check letter (`encode(42)` is `TK-000042Q`).
    * `parse(text)`: the ticket number of a typed code, or `IllegalArgumentException`. Leading and trailing whitespace is ignored
      and letters may be lower case. After `TK` there may be one `-` or one space; the six digits may be followed by one `-` or one
      space before the check letter. People confuse letters with digits, so in the digit part `O` counts as `0`, and `I` and `L`
      count as `1`. The check letter must be the right one for the digits (after that correction), and nothing may follow it.
    * `isValid(text)`: `true` when `parse` accepts the text.
    * `next(code)`: the code of the following ticket (`parse` then `encode(n + 1)`); the code of ticket `999999` has no successor
      (`IllegalArgumentException`).
    * `pretty(code)`: the code as `TK 123 456 T` (digits in two groups of three); the argument is parsed like in `parse`.
''')

CODES = dd(r'''
    package tickets;

    public final class Codes {
        private static final String ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ";
        private static final int[] WEIGHTS = {7, 3, 1, 7, 3, 1};

        private Codes() {}

        public static char check(String digits) {
            if (digits.length() != 6) {
                throw new IllegalArgumentException("six digits expected");
            }
            int sum = 0;
            for (int i = 0; i < 6; i++) {
                char c = digits.charAt(i);
                if (c < '0' || c > '9') {
                    throw new IllegalArgumentException("not a digit: " + c);
                }
                sum += (c - '0') * WEIGHTS[i];
            }
            return ALPHABET.charAt(sum % 24);
        }

        public static String encode(int n) {
            if (n < 0 || n > 999999) {
                throw new IllegalArgumentException("ticket number out of range");
            }
            String digits = String.format("%06d", n);
            return "TK-" + digits + check(digits);
        }

        public static int parse(String text) {
            String t = text.trim().toUpperCase();
            if (!t.startsWith("TK")) {
                throw new IllegalArgumentException("a code starts with TK");
            }
            int i = 2;
            if (i < t.length() && (t.charAt(i) == '-' || t.charAt(i) == ' ')) {
                i++;
            }
            if (t.length() < i + 6) {
                throw new IllegalArgumentException("too short");
            }
            StringBuilder digits = new StringBuilder();
            for (int k = 0; k < 6; k++) {
                char c = t.charAt(i + k);
                if (c == 'O') {
                    c = '0';
                } else if (c == 'I' || c == 'L') {
                    c = '1';
                }
                if (c < '0' || c > '9') {
                    throw new IllegalArgumentException("not a digit: " + c);
                }
                digits.append(c);
            }
            i += 6;
            if (i < t.length() && (t.charAt(i) == '-' || t.charAt(i) == ' ')) {
                i++;
            }
            if (t.length() != i + 1) {
                throw new IllegalArgumentException("one check letter expected");
            }
            if (t.charAt(i) != check(digits.toString())) {
                throw new IllegalArgumentException("wrong check letter");
            }
            return Integer.parseInt(digits.toString());
        }

        public static boolean isValid(String text) {
            try {
                parse(text);
                return true;
            } catch (IllegalArgumentException e) {
                return false;
            }
        }

        public static String next(String code) {
            return encode(parse(code) + 1);
        }

        public static String pretty(String code) {
            int n = parse(code);
            String digits = String.format("%06d", n);
            return "TK " + digits.substring(0, 3) + " " + digits.substring(3) + " " + check(digits);
        }
    }
''')

BASIC = dd(r'''
    import tickets.Codes;

    public class BasicTests {
        public static void run() {
            Check.test("encode", () -> Check.eq("TK-123456T", Codes.encode(123456)));
            Check.test("parse", () -> Check.eq(123456, Codes.parse("TK-123456T")));
        }
    }
''')

FULL = dd(r'''
    import tickets.Codes;

    public class FullTests {
        public static void run() {
            Check.test("check letters", () -> {
                Check.eq('T', Codes.check("123456"));
                Check.eq('A', Codes.check("000000"));
                Check.eq('B', Codes.check("000001"));
                Check.eq('H', Codes.check("000007"));
                Check.eq('Q', Codes.check("000042"));
                Check.eq('G', Codes.check("999999"));
                Check.eq('L', Codes.check("000024"));
                Check.eq('M', Codes.check("000025"));
                Check.eq('W', Codes.check("000048"));
                Check.eq('H', Codes.check("100000"));
            });

            Check.test("the alphabet skips I and O", () -> {
                StringBuilder seen = new StringBuilder();
                for (int d = 0; d < 10; d++) {
                    seen.append(Codes.check("00000" + d));
                }
                Check.eq("ABCDEFGHJK", seen.toString());
                StringBuilder tens = new StringBuilder();
                for (int d = 0; d < 10; d++) {
                    tens.append(Codes.check("0000" + d + "0"));
                }
                Check.eq("ADGKNRUXAD", tens.toString());
                for (int n = 0; n < 1000000; n += 997) {
                    char c = Codes.check(String.format("%06d", n));
                    Check.yes(c != 'I' && c != 'O', "no I or O in " + n);
                }
            });

            Check.test("check validation", () -> {
                Check.raises(IllegalArgumentException.class, () -> Codes.check("12345"));
                Check.raises(IllegalArgumentException.class, () -> Codes.check("1234567"));
                Check.raises(IllegalArgumentException.class, () -> Codes.check("12345a"));
                Check.raises(IllegalArgumentException.class, () -> Codes.check("12 456"));
                Check.raises(IllegalArgumentException.class, () -> Codes.check(""));
            });

            Check.test("encode", () -> {
                Check.eq("TK-000000A", Codes.encode(0));
                Check.eq("TK-000001B", Codes.encode(1));
                Check.eq("TK-000007H", Codes.encode(7));
                Check.eq("TK-000042Q", Codes.encode(42));
                Check.eq("TK-001234E", Codes.encode(1234));
                Check.eq("TK-123456T", Codes.encode(123456));
                Check.eq("TK-999999G", Codes.encode(999999));
                Check.eq("TK-100000H", Codes.encode(100000));
                Check.eq("TK-999998F", Codes.encode(999998));
                Check.raises(IllegalArgumentException.class, () -> Codes.encode(-1));
                Check.raises(IllegalArgumentException.class, () -> Codes.encode(1000000));
            });

            Check.test("parse accepts typed variants", () -> {
                Check.eq(123456, Codes.parse("TK-123456T"));
                Check.eq(123456, Codes.parse("tk-123456t"));
                Check.eq(123456, Codes.parse("  TK-123456T \t"));
                Check.eq(123456, Codes.parse("TK123456T"));
                Check.eq(123456, Codes.parse("TK 123456 T"));
                Check.eq(123456, Codes.parse("tk 123456-t"));
                Check.eq(123456, Codes.parse("TK-123456 T"));
                Check.eq(0, Codes.parse("TK-000000A"));
                Check.eq(999999, Codes.parse("TK-999999G"));
                Check.eq(42, Codes.parse("tk-000042q"));
            });

            Check.test("parse corrects look-alike letters in the digits", () -> {
                Check.eq(123456, Codes.parse("TK-I23456T"));
                Check.eq(123456, Codes.parse("TK-L23456T"));
                Check.eq(123456, Codes.parse("tk-l23456t"));
                Check.eq(0, Codes.parse("TK-OOOOOOA"));
                Check.eq(1, Codes.parse("TK-OOOOOIB"));
                Check.eq(1, Codes.parse("TK-OOOOOLB"));
                Check.eq(100000, Codes.parse("TK-1OOOOOH"));
            });

            Check.test("parse rejects bad codes", () -> {
                String[] bad = {
                    "", "TK", "TK-", "TK-123456", "TK-12345T", "TK-1234567T", "XX-123456T", "T-123456T", "TK-123456A", "TK-123456I", "TK-123456O",
                    "TK-12 3456T", "TK--123456T", "TK-123456TT", "TK-123456-T-", "TK-12345XT", "TK-12-456T", "TK-123456", "TK-1234 56T", "123456T", "TK-123456!",
                    "TK-12345OT", "TK-123456 T extra", "TK  123456T", "TK-123456--T",
                };
                for (String text : bad) {
                    Check.raises(IllegalArgumentException.class, () -> Codes.parse(text));
                }
            });

            Check.test("a wrong check letter is rejected for every other letter", () -> {
                String alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ";
                for (char c : alphabet.toCharArray()) {
                    String code = "TK-123456" + c;
                    Check.eq(c == 'T', Codes.isValid(code));
                }
            });

            Check.test("isValid", () -> {
                Check.yes(Codes.isValid("TK-123456T"), "valid");
                Check.yes(Codes.isValid(" tk 123456 t "), "typed variant");
                Check.yes(!Codes.isValid("TK-123456S"), "wrong letter");
                Check.yes(!Codes.isValid(""), "empty");
                Check.yes(!Codes.isValid("TK-123456TT"), "too long");
            });

            Check.test("encode and parse round trip", () -> {
                int[] numbers = {0, 1, 9, 10, 99, 100, 999, 1000, 4711, 65535, 99999, 100000, 500000, 999998, 999999};
                for (int n : numbers) {
                    Check.eq(n, Codes.parse(Codes.encode(n)));
                }
                for (int n = 0; n < 2000; n += 7) {
                    Check.eq(n, Codes.parse(Codes.encode(n).toLowerCase()));
                }
            });

            Check.test("next", () -> {
                Check.eq("TK-000001B", Codes.next("TK-000000A"));
                Check.eq(Codes.encode(43), Codes.next("TK-000042Q"));
                Check.eq("TK-999999G", Codes.next("TK-999998F"));
                Check.eq(Codes.encode(124), Codes.next("tk 000123 s"));
                Check.raises(IllegalArgumentException.class, () -> Codes.next("TK-999999G"));
                Check.raises(IllegalArgumentException.class, () -> Codes.next("nonsense"));
            });

            Check.test("pretty", () -> {
                Check.eq("TK 123 456 T", Codes.pretty("TK-123456T"));
                Check.eq("TK 000 042 Q", Codes.pretty("tk-000042q"));
                Check.eq("TK 000 000 A", Codes.pretty("TK-000000A"));
                Check.eq("TK 999 999 G", Codes.pretty("TK999999G"));
                Check.eq("TK 100 000 H", Codes.pretty("TK-1OOOOOH"));
                Check.raises(IllegalArgumentException.class, () -> Codes.pretty("TK-123456A"));
            });
        }
    }
''')

LIB = Lib(
    name="ticketcode", lang="java", title="the ticketcode library",
    blurb="The help desk's ticket numbers are generated and read back with ticketcode, including the check letter.",
    files={"src/tickets/Codes.java": CODES, "README.md": README, ".gitignore": "build/\n"},
    visible_tests={"test/Check.java": JAVA_CHECK, "test/BasicTests.java": BASIC, "test/TestMain.java": java_test_main("BasicTests")},
    hidden_tests={"test/FullTests.java": FULL, "test/TestMain.java": java_test_main("BasicTests", "FullTests")},
    mutate=["src/tickets/Codes.java"], difficulty=1, tags=["checksum", "codes", "parsing"],
    probe_import="import tickets.*;",
    probes=[
        "Codes.check(\"123456\")", "Codes.check(\"000024\")", "Codes.check(\"999999\")", "Codes.encode(42)", "Codes.encode(999999)", "Codes.encode(1000000)",
        "Codes.parse(\"tk 123456-t\")", "Codes.parse(\"TK-I23456T\")", "Codes.parse(\"TK-OOOOOLB\")", "Codes.parse(\"TK-123456A\")", "Codes.parse(\"TK-123456TT\")", "Codes.parse(\"TK--123456T\")",
        "Codes.isValid(\" tk 123456 t \")", "Codes.isValid(\"TK-123456S\")", "Codes.next(\"TK-000042Q\")", "Codes.next(\"TK-999999G\")", "Codes.pretty(\"tk-000042q\")", "Codes.pretty(\"TK999999G\")",
    ],
)

register_libs([LIB], n=8)
