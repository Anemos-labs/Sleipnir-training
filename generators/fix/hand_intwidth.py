"""Integer width bugs: overflow, truncation, wrapping, signedness. Serial numbers (java), a tick meter (rust), pixels (go)."""
from fx import dd, family, langs
from generators.fix._hand_kit import Base, Bug, java_str, panic_excerpt, tasks_from


def fnv(key: str) -> int:
    h = 0x811C9DC5
    for b in key.encode():
        h ^= b
        h = (h * 16777619) & 0xFFFFFFFF
    return h


# ------------------------------------------------------------------------------------------------------------------
# Base A (java): serial numbers of a ticketing system.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # serials

    Serial numbers of a ticketing system (plain Java: `rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java') &&
    java -cp build TestMain`). A serial is a number from 0 to 999 999 999 999 (twelve digits); everything is `long` arithmetic.

    * `Serial.parse(text)`: exactly 1 to 12 decimal digits (leading zeros allowed) give the serial; anything else, including `null`, is
      an `IllegalArgumentException`.
    * `Serial.checksum(serial)`: `(serial * 7 + 3) mod 11`.
    * `Serial.format(serial)`: twelve digits, zero padded, a dash and the checksum, e.g. `000000000042-6`; a serial outside the range is an
      `IllegalArgumentException`.
    * `Serial.firstOfBlock(block, blockSize)`: the first serial of block number `block` when serials are handed out in blocks of
      `blockSize` (an `int` each), as a `long`: `block * blockSize`. Both arguments are ints up to 2^31-1.
    * `Serial.bucket(key, buckets)`: the shard of a key: the 32-bit FNV-1a hash of its UTF-8 bytes (offset basis `0x811c9dc5`, prime
      16777619), read as an **unsigned** number, modulo `buckets`.
''')

A_SERIAL = dd('''
    package serials;

    import java.nio.charset.StandardCharsets;

    public final class Serial {
        private Serial() {}

        public static final long MAX = 999_999_999_999L;

        public static long parse(String text) {
            if (text == null || !text.matches("[0-9]{1,12}")) {
                throw new IllegalArgumentException("bad serial: " + text);
            }
            return Long.parseLong(text);
        }

        public static int checksum(long serial) {
            return (int) ((serial * 7 + 3) % 11);
        }

        public static String format(long serial) {
            if (serial < 0 || serial > MAX) {
                throw new IllegalArgumentException("serial out of range: " + serial);
            }
            return String.format("%012d-%d", serial, checksum(serial));
        }

        public static long firstOfBlock(int block, int blockSize) {
            return (long) block * blockSize;
        }

        public static int bucket(String key, int buckets) {
            int hash = 0x811c9dc5;
            for (byte b : key.getBytes(StandardCharsets.UTF_8)) {
                hash ^= (b & 0xff);
                hash *= 16777619;
            }
            return (int) (Integer.toUnsignedLong(hash) % buckets);
        }
    }
''')

A_VISIBLE = {
    "tests/TestMain.java": dd('''
        import serials.Serial;

        public class TestMain {
            public static void main(String[] args) {
                if (Serial.parse("000000000042") != 42) {
                    System.out.println("FAIL parse");
                    System.exit(1);
                }
                if (!Serial.format(42).equals("000000000042-6")) {
                    System.out.println("FAIL format " + Serial.format(42));
                    System.exit(1);
                }
                if (Serial.firstOfBlock(3, 1000) != 3000) {
                    System.out.println("FAIL block");
                    System.exit(1);
                }
                System.out.println("all checks passed");
            }
        }
    '''),
}


def _a_hidden() -> dict:
    keys = ["alpha", "beta", "gamma", "delta", "omega", "user-1001", "user-1002", "user-1003", "order/77", "x", "session:abc", "a", "hello world", "café"]
    assert any(fnv(k) >= 2 ** 31 for k in keys)
    lines = []

    def chk(expr, want):
        lines.append(f'        check("{java_str(expr)}", {expr}, {want}L);')

    for text, want in [("0", 0), ("42", 42), ("000000000042", 42), ("2147483648", 2147483648), ("4294967296", 4294967296), ("999999999999", 999999999999), ("123456789012", 123456789012)]:
        chk(f'Serial.parse("{text}")', want)
    for serial in [0, 1, 42, 10, 999999999999, 2147483648, 3000000000, 123456789012, 6000000001, 307445734561]:
        chk(f"Serial.checksum({serial}L)", (serial * 7 + 3) % 11)
    fmt = []
    for serial in [0, 42, 999999999999, 3000000000, 123456789012]:
        fmt.append(f'        checkStr("Serial.format({serial}L)", Serial.format({serial}L), "{serial:012d}-{(serial * 7 + 3) % 11}");')
    for block, size in [(0, 1000), (3, 1000), (5000, 1048576), (2147483647, 2147483647), (70000, 70000), (65536, 65536)]:
        chk(f"Serial.firstOfBlock({block}, {size})", block * size)
    for k in keys:
        for n in (7, 1024, 1000003):
            chk(f'Serial.bucket("{java_str(k)}", {n})', fnv(k) % n)
    bad = ["", "abc", "1234567890123", "12 3", "-5", "+5", "1e3", "\uff11\uff12\uff13"]
    bad_lines = "\n".join(f'        mustReject("{java_str(b)}", () -> Serial.parse("{java_str(b)}"));' for b in bad)
    java = dd('''
        import serials.Serial;

        public class TestMain {
            static int failures = 0;

            static void check(String what, long got, long want) {
                if (got != want) {
                    failures++;
                    System.out.println("FAIL " + what + ": got " + got + ", want " + want);
                }
            }

            static void checkStr(String what, String got, String want) {
                if (!want.equals(got)) {
                    failures++;
                    System.out.println("FAIL " + what + ": got " + got + ", want " + want);
                }
            }

            static void mustReject(String what, Runnable r) {
                try {
                    r.run();
                } catch (NumberFormatException e) {
                    // a NumberFormatException is an IllegalArgumentException too
                    return;
                } catch (IllegalArgumentException e) {
                    return;
                }
                failures++;
                System.out.println("FAIL parse of \\"" + what + "\\" should be rejected");
            }

            public static void main(String[] args) {
        @@LINES@@
        @@FMT@@
        @@BAD@@
                mustReject("null", () -> Serial.parse(null));
                mustReject("out of range", () -> Serial.format(1_000_000_000_000L));
                mustReject("negative", () -> Serial.format(-1));
                if (failures > 0) {
                    System.out.println(failures + " check(s) failed");
                    System.exit(1);
                }
                System.out.println("all checks passed");
            }
        }
    ''')
    java = java.replace("@@LINES@@", "\n".join(lines)).replace("@@FMT@@", "\n".join(fmt)).replace("@@BAD@@", bad_lines)
    return {"tests/TestMain.java": java}


def _a_prompts():
    p = {}
    p["parse-int"] = (
        "Serials above 2147483647 cannot be parsed any more: the import of the new batch (serials around 3 billion) fails with a "
        "NumberFormatException on every row. Serials are twelve digits long."
    )
    p["checksum"] = (
        "For big serials the check digit printed on the tickets does not match the one our printer firmware computes (it uses exact "
        "arithmetic): for serial 3000000000 we print a different digit. Small serials are fine."
    )
    p["block"] = (
        "Block number 5000 of size 1048576 should start at serial 5242880000 but the allocator hands out a negative-looking number: "
        "`firstOfBlock` returns the wrong value as soon as `block * blockSize` is bigger than about two billion."
    )
    p["bucket"] = (
        "Roughly half of our keys end up on the wrong shard compared with the reference implementation (a Go service computing FNV-1a "
        "on unsigned 32-bit integers), and a few even get a negative shard number. Keys whose hash is small are fine."
    )
    p["two"] = (
        "Importing the new serial batch (12 digit numbers above 2^31) fails, and for the ones that are accepted by other tools the check "
        "digits we print are wrong. The unit tests only use small serials. Please make big serials work end to end."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "src/serials/Serial.java": A_SERIAL}
    s = "src/serials/Serial.java"
    parse = ("        return Long.parseLong(text);\n", "        return Integer.parseInt(text);\n")
    check = ("        return (int) ((serial * 7 + 3) % 11);\n", "        int s = (int) serial;\n        return (s * 7 + 3) % 11;\n")
    bugs = [
        Bug("parse-through-int", 1, {s: [parse]}, P["parse-int"]),
        Bug("block-start-multiplied-as-int", 1, {s: [("        return (long) block * blockSize;\n", "        return block * blockSize;\n")]}, P["block"]),
        Bug("checksum-in-int-arithmetic", 3, {s: [check]}, P["checksum"]),
        Bug("bucket-from-a-signed-hash", 3, {s: [("        return (int) (Integer.toUnsignedLong(hash) % buckets);\n", "        return Math.abs(hash) % buckets;\n")]}, P["bucket"]),
        Bug("big-serials-parse-and-checksum", 4, {s: [parse, check]}, P["two"]),
    ]
    return Base("serials", "java", good, A_VISIBLE, _a_hidden(), bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (rust): helpers of a hardware tick meter.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # meter

    Helpers for firmware that reads a free-running 32-bit tick counter (Rust, no dependencies; the tests are built in debug mode, so an
    arithmetic overflow is a panic).

    * `elapsed(start, end)`: ticks from `start` to `end` of a counter that wraps around at 2^32 (so `elapsed(u32::MAX - 5, 10)` is 16).
    * `average(samples)`: mean of the samples, rounded down; `0` for no samples. Any `u32` samples, any number of them.
    * `percent(part, whole)`: `part * 100 / whole`, rounded down, for **every** pair of `u32` values (the result is a `u32`; `part` may exceed
      `whole`); `0` when `whole` is 0.
    * `clamp_i16(x)`: an `i64` limited to the `i16` range.
    * `ring_index(pos, delta, len)`: the slot `delta` steps (negative or positive, any size) from slot `pos` in a ring of `len` slots; panics if
      `len == 0` or `pos >= len`.
''')

B_LIB = dd('''
    //! Tick meter helpers.

    pub fn elapsed(start: u32, end: u32) -> u32 {
        end.wrapping_sub(start)
    }

    pub fn average(samples: &[u32]) -> u32 {
        if samples.is_empty() {
            return 0;
        }
        let sum: u64 = samples.iter().map(|&s| s as u64).sum();
        (sum / samples.len() as u64) as u32
    }

    pub fn percent(part: u32, whole: u32) -> u32 {
        if whole == 0 {
            return 0;
        }
        ((part as u64 * 100) / whole as u64) as u32
    }

    pub fn clamp_i16(x: i64) -> i16 {
        x.clamp(i16::MIN as i64, i16::MAX as i64) as i16
    }

    pub fn ring_index(pos: usize, delta: isize, len: usize) -> usize {
        assert!(len > 0 && pos < len, "bad ring position");
        let n = len as i128;
        (((pos as i128 + delta as i128) % n + n) % n) as usize
    }
''')

B_VISIBLE = {
    "tests/basic.rs": dd('''
        use meter::*;

        #[test]
        fn small_values() {
            assert_eq!(elapsed(10, 25), 15);
            assert_eq!(average(&[2, 4, 6]), 4);
            assert_eq!(percent(1, 4), 25);
            assert_eq!(clamp_i16(7), 7);
            assert_eq!(ring_index(1, 1, 4), 2);
        }
    '''),
}


def _b_hidden() -> dict:
    ring = [(2, -3, 5), (0, -1, 5), (4, 1, 5), (1, 12, 5), (3, -13, 5), (0, 0, 1), (0, -9223372036854775808, 7), (6, 9223372036854775807, 7), (2, -2, 5)]
    ring_lines = "\n".join(f"    assert_eq!(ring_index({p}, {d}isize, {n}), {((p + d) % n + n) % n});" for p, d, n in ring)
    ring_lines = ring_lines.replace("-9223372036854775808isize", "isize::MIN").replace("9223372036854775807isize", "isize::MAX")
    text = dd('''
        use meter::*;

        #[test]
        fn elapsed_survives_the_counter_wrapping() {
            assert_eq!(elapsed(u32::MAX - 5, 10), 16);
            assert_eq!(elapsed(u32::MAX, 0), 1);
            assert_eq!(elapsed(10, 10), 0);
            assert_eq!(elapsed(0, u32::MAX), u32::MAX);
            assert_eq!(elapsed(4_000_000_000, 100), 294_967_396);
            assert_eq!(elapsed(5, 3), u32::MAX - 1);
        }

        #[test]
        fn average_does_not_overflow() {
            assert_eq!(average(&[]), 0);
            assert_eq!(average(&[1, 2]), 1);
            assert_eq!(average(&[u32::MAX, u32::MAX, u32::MAX]), u32::MAX);
            assert_eq!(average(&[4_000_000_000, 4_000_000_000]), 4_000_000_000);
            assert_eq!(average(&[u32::MAX, 1]), 2_147_483_648);
            assert_eq!(average(&[7]), 7);
            assert_eq!(average(&vec![1_000_000_000; 10]), 1_000_000_000);
        }

        #[test]
        fn percent_for_every_u32() {
            assert_eq!(percent(u32::MAX, u32::MAX), 100);
            assert_eq!(percent(50_000_000, 100_000_000), 50);
            assert_eq!(percent(43_000_000, 86_000_000), 50);
            assert_eq!(percent(1, 3), 33);
            assert_eq!(percent(2, 3), 66);
            assert_eq!(percent(5, 0), 0);
            assert_eq!(percent(0, 9), 0);
            assert_eq!(percent(300, 100), 300);
            assert_eq!(percent(u32::MAX, 1_000_000), 429_496);
            assert_eq!(percent(4_000_000_000, 4_000_000_001), 99);
        }

        #[test]
        fn clamp_keeps_the_sign_and_the_limits() {
            assert_eq!(clamp_i16(40_000), i16::MAX);
            assert_eq!(clamp_i16(-40_000), i16::MIN);
            assert_eq!(clamp_i16(5), 5);
            assert_eq!(clamp_i16(-5), -5);
            assert_eq!(clamp_i16(i64::MAX), i16::MAX);
            assert_eq!(clamp_i16(i64::MIN), i16::MIN);
            assert_eq!(clamp_i16(65_536 + 3), i16::MAX);
            assert_eq!(clamp_i16(32_767), 32_767);
            assert_eq!(clamp_i16(32_768), 32_767);
            assert_eq!(clamp_i16(-32_768), -32_768);
        }

        #[test]
        fn ring_index_wraps_in_both_directions() {
        @@RING@@
        }

        #[test]
        #[should_panic]
        fn ring_needs_a_slot() {
            ring_index(0, 1, 0);
        }

        #[test]
        #[should_panic]
        fn ring_position_must_be_inside() {
            ring_index(5, 1, 5);
        }
    ''')
    return {"tests/hidden_meter.rs": text.replace("@@RING@@", ring_lines)}


def _b_prompts():
    p = {}
    p["elapsed"] = lambda c: (
        "The uptime display panics after the 32-bit timer wraps around (about every 49 days at 1 kHz). A minimal test shows:\n\n```\n"
        + panic_excerpt(c.bad_run("use meter::elapsed;\n\n#[test]\nfn timer_wrap() {\n    assert_eq!(elapsed(u32::MAX - 5, 10), 16);\n}\n",
                                  cmd="cargo test --offline --quiet --test probe 2>&1", name="tests/probe.rs"))
        + "\n```\n\nElapsed time must be computed modulo 2^32."
    )
    p["average"] = (
        "The sensor dashboard panics with an arithmetic overflow when averaging a few large readings (three readings near 4 billion are "
        "enough), in debug builds, and silently shows nonsense in release builds. `average` must work for any u32 samples."
    )
    p["percent"] = (
        "Progress bars for big transfers are wrong or crash: `percent(50_000_000, 100_000_000)` should be 50 but the function overflows "
        "in the multiplication by 100 as soon as the numerator is above about 42 million."
    )
    p["clamp"] = (
        "Audio samples that are louder than the 16-bit range come out as the wrong sign (a loud positive peak becomes a loud negative "
        "one) instead of being limited. `clamp_i16` is supposed to limit the value to the i16 range."
    )
    p["ring"] = (
        "Stepping backwards in the log ring buffer lands on slot numbers that make no sense: from slot 2, going back 3 slots in a "
        "ring of 5 should give slot 4 but we get something else (or an out-of-range panic). Forward steps are fine."
    )
    p["two"] = (
        "Two arithmetic problems in the meter code that only show with large numbers: percentages of big counters panic with an overflow, "
        "and averages of large samples as well. Please make them correct for every u32 input."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "Cargo.toml": langs.cargo_toml("meter"), "src/lib.rs": B_LIB}
    lib = "src/lib.rs"
    avg = ("    let sum: u64 = samples.iter().map(|&s| s as u64).sum();\n    (sum / samples.len() as u64) as u32\n", "    let sum: u32 = samples.iter().sum();\n    sum / samples.len() as u32\n")
    pct = ("    ((part as u64 * 100) / whole as u64) as u32\n", "    part * 100 / whole\n")
    bugs = [
        Bug("elapsed-subtracts-plainly", 1, {lib: [("    end.wrapping_sub(start)\n", "    end - start\n")]}, P["elapsed"]),
        Bug("clamp-by-cast", 2, {lib: [("    x.clamp(i16::MIN as i64, i16::MAX as i64) as i16\n", "    x as i16\n")]}, P["clamp"]),
        Bug("average-sums-in-u32", 3, {lib: [avg]}, P["average"]),
        Bug("percent-multiplies-in-u32", 2, {lib: [pct]}, P["percent"]),
        Bug("ring-index-casts-negative-positions", 3, {lib: [("    let n = len as i128;\n    (((pos as i128 + delta as i128) % n + n) % n) as usize\n", "    ((pos as isize + delta) as usize) % len\n")]}, P["ring"]),
        Bug("average-and-percent-overflow", 4, {lib: [avg, pct]}, P["two"]),
    ]
    return Base("meter", "rust", good, B_VISIBLE, _b_hidden(), bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base C (go): 8-bit pixel arithmetic.
# ------------------------------------------------------------------------------------------------------------------

C_README = dd('''
    # pixels

    Small image helpers on 8-bit channels (Go).

    * `Brighten(v, delta)`: `v + delta` limited to 0..255 (`delta` may be negative and any `int`).
    * `Mix(a, b, weight)`: weighted blend, `weight` 0 gives `a`, 255 gives `b`: `(a*(255-weight) + b*weight) / 255`, rounded down, computed exactly.
    * `Index(x, y, width)`: position of pixel `(x, y)` in a row-major image `width` pixels wide, as an `int64` (images can have billions of pixels; all
      arguments are `int32`).
    * `Average(values)`: mean of the values rounded to nearest, halves up; `0` for none; any number of values.
''')

C_PIXELS = dd('''
    package pixels

    // Brighten adds delta to v, limited to 0..255.
    func Brighten(v uint8, delta int) uint8 {
    	n := int(v) + delta
    	if n < 0 {
    		return 0
    	}
    	if n > 255 {
    		return 255
    	}
    	return uint8(n)
    }

    // Mix blends a and b.
    func Mix(a, b, weight uint8) uint8 {
    	w := int(weight)
    	return uint8((int(a)*(255-w) + int(b)*w) / 255)
    }

    // Index is the position of (x, y) in a row-major image.
    func Index(x, y, width int32) int64 {
    	return int64(y)*int64(width) + int64(x)
    }

    // Average is the mean rounded to nearest, halves up.
    func Average(values []uint8) uint8 {
    	if len(values) == 0 {
    		return 0
    	}
    	sum := 0
    	for _, v := range values {
    		sum += int(v)
    	}
    	return uint8((2*sum + len(values)) / (2 * len(values)))
    }
''')

C_VISIBLE = {
    "pixels_test.go": dd('''
        package pixels

        import "testing"

        func TestSmallValues(t *testing.T) {
        	if Brighten(100, 20) != 120 || Brighten(10, -20) != 0 {
        		t.Fatal("brighten")
        	}
        	if Mix(0, 100, 0) != 0 || Mix(0, 100, 255) != 100 {
        		t.Fatal("mix ends")
        	}
        	if Index(3, 2, 10) != 23 {
        		t.Fatal("index")
        	}
        	if Average([]uint8{1, 2, 3}) != 2 {
        		t.Fatal("average")
        	}
        }
    '''),
}


def _c_hidden() -> dict:
    def brighten(v, d):
        return max(0, min(255, v + d))

    def mix(a, b, w):
        return (a * (255 - w) + b * w) // 255

    def avg(vs):
        return 0 if not vs else (2 * sum(vs) + len(vs)) // (2 * len(vs))

    bright = [(200, 100), (250, 6), (0, -1), (255, 1), (10, 300), (128, -128), (128, -129), (100, 1 << 40), (100, -(1 << 40)), (255, 0)]
    mixes = [(0, 255, 128), (255, 255, 200), (200, 100, 128), (255, 0, 1), (255, 0, 254), (17, 230, 77), (255, 255, 255), (255, 255, 0), (128, 128, 64)]
    idx = [(3, 2, 10), (0, 0, 5), (70000, 70000, 70000), (2147483647, 2147483647, 2147483647), (65535, 65536, 65536), (1, 100000, 100000), (5, 0, 7)]
    avgs = [[], [255, 255, 255], [255] * 300, [1, 2], [1, 2, 3, 4], [200, 201, 202, 203, 204], [0, 255], [254, 255]]
    t = []
    for v, d in bright:
        t.append(f"\tif got := Brighten({v}, {d}); got != {brighten(v, d)} {{\n\t\tt.Errorf(\"Brighten({v}, {d}) = %d, want {brighten(v, d)}\", got)\n\t}}")
    b = "\n".join(t)
    t = []
    for a, bb, w in mixes:
        t.append(f"\tif got := Mix({a}, {bb}, {w}); got != {mix(a, bb, w)} {{\n\t\tt.Errorf(\"Mix({a}, {bb}, {w}) = %d, want {mix(a, bb, w)}\", got)\n\t}}")
    m = "\n".join(t)
    t = []
    for x, y, w in idx:
        t.append(f"\tif got := Index({x}, {y}, {w}); got != {y * w + x} {{\n\t\tt.Errorf(\"Index({x}, {y}, {w}) = %d, want {y * w + x}\", got)\n\t}}")
    ix = "\n".join(t)
    t = []
    for vs in avgs:
        lit = ", ".join(str(v) for v in vs)
        t.append(f"\tif got := Average([]uint8{{{lit}}}); got != {avg(vs)} {{\n\t\tt.Errorf(\"Average(%d values) = %d, want {avg(vs)}\", {len(vs)}, got)\n\t}}")
    av = "\n".join(t)
    src = ("package pixels\n\nimport \"testing\"\n\n"
           "func TestBrighten(t *testing.T) {\n" + b + "\n}\n\n"
           "func TestMix(t *testing.T) {\n" + m + "\n}\n\n"
           "func TestIndexHasNoOverflow(t *testing.T) {\n" + ix + "\n}\n\n"
           "func TestAverage(t *testing.T) {\n" + av + "\n}\n")
    return {"pixels_hidden_test.go": src}


def _c_prompts():
    p = {}
    p["brighten"] = (
        "The brighten slider turns highlights black: raising a channel of 250 by 10 gives 4 instead of 255, and darkening below zero wraps to "
        "bright. It should saturate at 0 and 255."
    )
    p["index"] = (
        "Exporting a 100000 x 100000 pixel image overwrites the wrong places: `Index(5, 99999, 100000)` goes negative. The function returns an "
        "int64 but something in it overflows before that."
    )
    p["average"] = (
        "Averaging many pixels (blurring a big region) gives garbage: the mean of 300 values that are all 255 is not 255. Small averages are "
        "correct."
    )
    return p


def _base_c() -> Base:
    P = _c_prompts()
    good = {"README.md": C_README, "go.mod": langs.go_mod("pixels"), "pixels.go": C_PIXELS}
    f = "pixels.go"
    bugs = [
        Bug("brighten-wraps-around", 2, {f: [("\tn := int(v) + delta\n\tif n < 0 {\n\t\treturn 0\n\t}\n\tif n > 255 {\n\t\treturn 255\n\t}\n\treturn uint8(n)\n", "\treturn uint8(int(v) + delta)\n")]}, P["brighten"]),
        Bug("index-multiplied-in-int32", 2, {f: [("\treturn int64(y)*int64(width) + int64(x)\n", "\treturn int64(y*width + x)\n")]}, P["index"]),
        Bug("average-sums-in-uint8", 3, {f: [("\tsum := 0\n\tfor _, v := range values {\n\t\tsum += int(v)\n\t}\n\treturn uint8((2*sum + len(values)) / (2 * len(values)))\n",
                                              "\tvar sum uint8\n\tfor _, v := range values {\n\t\tsum += v\n\t}\n\treturn (2*sum + uint8(len(values))) / (2 * uint8(len(values)))\n")]}, P["average"]),
    ]
    return Base("pixels", "go", good, C_VISIBLE, _c_hidden(), bugs)


@family("fix-hand-int-width", category="fix", lang="java", kind="fix", n=14,
        summary="integer width bugs: overflow, truncation, wrapping and signedness (java serials, rust tick meter, go pixels)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b(), _base_c()])
