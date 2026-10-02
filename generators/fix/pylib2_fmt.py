"""Text-format libraries (python), batch: human formatting, identifier case, hex dumps."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# humanfmt: sizes and durations for people (formatting and parsing)
# ======================================================================================================================

HF_README = dd(r'''
    # humanfmt

    Number formatting for the storage dashboard. One module, `humanfmt.py`.

    ## `format_size(n, binary=True, precision=1) -> str`
    `n` is an `int` number of bytes (a `bool` or non-int is a `TypeError`... callers pass ints); `precision` is 0-3, else
    `ValueError`. A negative `n` is written as `-` followed by the text for `-n`.
    * Units: binary `B KiB MiB GiB TiB PiB` (steps of 1024), or decimal `B kB MB GB TB PB` (steps of 1000).
    * Below one step: the integer and ` B` (`512 B`).
    * Otherwise the largest unit `k` (at most the last) with `base**k <= n`; the number is `n / base**k` rounded half up to `precision`
      decimals using exact integer arithmetic. If rounding makes it reach `base` (and a larger unit exists) it is shown in the next unit
      instead: `1023.96 KiB` becomes `1 MiB`, not `1024 KiB`; in the last unit there is no promotion.
    * Trailing zeros of the decimals, and the point when no decimals remain, are removed: `1.5 MiB`, `2 MiB`, `0.25` is never produced
      (the number is always at least 1 except through promotion rounding, which gives exactly 1).
    * Examples: `format_size(1536)` is `1.5 KiB`, `format_size(1000, binary=False)` is `1 kB`, `format_size(999999, binary=False)` is `1 MB`.

    ## `parse_size(text) -> int`
    `text` is a number, optional blanks and an optional unit, with blanks around: the number has digits, optionally with single `_`
    between digits (`1_000`), and optionally a decimal point with digits (`1.5`); no sign, no exponent, no leading point.
    The unit is case-insensitive: nothing or `b` is 1; `kb mb gb tb pb` are powers of 1000; `kib mib gib tib pib` are powers of
    1024; the single letters `k m g t p` are powers of **1024**. The result is the exact product rounded half up to an `int`. Anything
    else is a `ValueError`.

    ## `format_duration(seconds, parts=2) -> str`
    `seconds` is an `int` or `float`; it is truncated toward zero to whole seconds. `parts` must be at least 1 (else `ValueError`).
    The units are `d` (86400 s), `h`, `m`, `s`. Starting at the largest unit whose value is not zero, the next `parts - 1`
    units follow (so `parts` consecutive units are looked at); units with value zero are left out; the pieces are joined by one space (`1h 5m`).
    Nothing (0 seconds) is `0s`. A negative value gets a leading `-` unless it truncated to zero.
    Examples: `format_duration(3725)` is `1h 2m`, `format_duration(3725, parts=3)` is `1h 2m 5s`, `format_duration(3601, parts=3)` is `1h 1s`,
    `format_duration(86400 + 5)` is `1d`.

    ## `parse_duration(text) -> int`
    Whole seconds. `text` is, after stripping, either a bare non-negative integer (seconds), or one or more components `number unit` (blanks
    between and inside components are optional) with an optional leading `-` for the whole text. A `number` has digits and an optional
    decimal part; units are `w` (604800), `d`, `h`, `m`, `s`, case-insensitive. A unit may appear only once. The total is exact and
    rounded half up to whole seconds (for a negative text: half away from zero). Anything else, including an empty text, is a `ValueError`.
''')

HF_SRC = dd(r'''
    """Human-friendly sizes and durations."""
    import re
    from fractions import Fraction

    _BIN = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    _DEC = ["B", "kB", "MB", "GB", "TB", "PB"]
    _SIZE = re.compile(r"\s*(\d+(?:_\d+)*(?:\.\d+)?)\s*([A-Za-z]*)\s*")
    _FACTORS = {"": 1, "b": 1}
    for _i, _p in enumerate("kmgtp", 1):
        _FACTORS[_p + "b"] = 1000 ** _i
        _FACTORS[_p + "ib"] = 1024 ** _i
        _FACTORS[_p] = 1024 ** _i
    _DURATION_UNITS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}


    def _half_up(x):
        return int((x + Fraction(1, 2)) // 1)


    def format_size(n, binary=True, precision=1):
        if not 0 <= precision <= 3:
            raise ValueError("precision must be 0..3")
        if n < 0:
            return "-" + format_size(-n, binary, precision)
        base = 1024 if binary else 1000
        units = _BIN if binary else _DEC
        if n < base:
            return "%d B" % n
        k = 1
        while k < 5 and base ** (k + 1) <= n:
            k += 1
        scale = 10 ** precision
        q = (2 * n * scale + base ** k) // (2 * base ** k)
        if q >= base * scale and k < 5:
            k += 1
            q = (2 * n * scale + base ** k) // (2 * base ** k)
        whole, frac = divmod(q, scale)
        text = str(whole)
        if precision and frac:
            text += "." + ("%0*d" % (precision, frac)).rstrip("0")
        return "%s %s" % (text, units[k])


    def parse_size(text):
        m = _SIZE.fullmatch(text)
        if not m:
            raise ValueError("bad size: %r" % text)
        unit = m.group(2).lower()
        if unit not in _FACTORS:
            raise ValueError("unknown unit: %r" % m.group(2))
        return _half_up(Fraction(m.group(1).replace("_", "")) * _FACTORS[unit])


    def format_duration(seconds, parts=2):
        if parts < 1:
            raise ValueError("parts must be at least 1")
        total = int(abs(seconds))
        if total == 0:
            return "0s"
        values = []
        rest = total
        for label, size in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
            values.append((rest // size, label))
            rest %= size
        first = next(i for i, (v, _) in enumerate(values) if v)
        out = ["%d%s" % (v, label) for v, label in values[first:first + parts] if v]
        return ("-" if seconds < 0 else "") + " ".join(out)


    def parse_duration(text):
        s = text.strip()
        if re.fullmatch(r"\d+", s):
            return int(s)
        sign = 1
        if s.startswith("-"):
            sign, s = -1, s[1:].lstrip()
        pos = 0
        seen = set()
        total = Fraction(0)
        comp = re.compile(r"(\d+(?:\.\d+)?)\s*([A-Za-z]+)\s*")
        if not s:
            raise ValueError("empty duration")
        while pos < len(s):
            m = comp.match(s, pos)
            if not m:
                raise ValueError("bad duration: %r" % text)
            unit = m.group(2).lower()
            if unit not in _DURATION_UNITS or unit in seen:
                raise ValueError("bad or repeated unit: %r" % m.group(2))
            seen.add(unit)
            total += Fraction(m.group(1)) * _DURATION_UNITS[unit]
            pos = m.end()
        return sign * _half_up(total)
''')

HF_VISIBLE = dd(r'''
    import unittest

    from humanfmt import format_duration, format_size, parse_duration, parse_size


    class BasicTests(unittest.TestCase):
        def test_format_size(self):
            self.assertEqual(format_size(1536), "1.5 KiB")
            self.assertEqual(format_size(512), "512 B")

        def test_parse_size(self):
            self.assertEqual(parse_size("2 KiB"), 2048)

        def test_duration(self):
            self.assertEqual(format_duration(3725), "1h 2m")
            self.assertEqual(parse_duration("1h 30m"), 5400)


    if __name__ == "__main__":
        unittest.main()
''')

HF_HIDDEN = dd(r'''
    import unittest

    from humanfmt import format_duration, format_size, parse_duration, parse_size


    class FormatSize(unittest.TestCase):
        def test_bytes(self):
            self.assertEqual(format_size(0), "0 B")
            self.assertEqual(format_size(1), "1 B")
            self.assertEqual(format_size(1023), "1023 B")
            self.assertEqual(format_size(999, binary=False), "999 B")

        def test_unit_boundaries(self):
            self.assertEqual(format_size(1024), "1 KiB")
            self.assertEqual(format_size(1024 ** 2), "1 MiB")
            self.assertEqual(format_size(1024 ** 3), "1 GiB")
            self.assertEqual(format_size(1024 ** 4), "1 TiB")
            self.assertEqual(format_size(1024 ** 5), "1 PiB")
            self.assertEqual(format_size(1000, binary=False), "1 kB")
            self.assertEqual(format_size(10 ** 6, binary=False), "1 MB")
            self.assertEqual(format_size(10 ** 9, binary=False), "1 GB")
            self.assertEqual(format_size(10 ** 12, binary=False), "1 TB")
            self.assertEqual(format_size(10 ** 15, binary=False), "1 PB")

        def test_decimals_and_trimming(self):
            self.assertEqual(format_size(1536), "1.5 KiB")
            self.assertEqual(format_size(2048), "2 KiB")
            self.assertEqual(format_size(1024 + 51), "1 KiB")
            self.assertEqual(format_size(1024 + 52), "1.1 KiB")
            self.assertEqual(format_size(1500, binary=False), "1.5 kB")
            self.assertEqual(format_size(1234, binary=False), "1.2 kB")
            self.assertEqual(format_size(1250, binary=False), "1.3 kB")
            self.assertEqual(format_size(1249, binary=False), "1.2 kB")
            self.assertEqual(format_size(10 * 1024), "10 KiB")
            self.assertEqual(format_size(10 * 1024 + 512), "10.5 KiB")

        def test_precision(self):
            self.assertEqual(format_size(1536, precision=0), "2 KiB")
            self.assertEqual(format_size(1535, precision=0), "1 KiB")
            self.assertEqual(format_size(1234, binary=False, precision=2), "1.23 kB")
            self.assertEqual(format_size(1235, binary=False, precision=2), "1.24 kB")
            self.assertEqual(format_size(1234, binary=False, precision=3), "1.234 kB")
            self.assertEqual(format_size(1200, binary=False, precision=3), "1.2 kB")
            self.assertEqual(format_size(1004, binary=False, precision=2), "1 kB")
            self.assertEqual(format_size(1005, binary=False, precision=2), "1.01 kB")
            self.assertEqual(format_size(1005, binary=False, precision=3), "1.005 kB")
            self.assertEqual(format_size(1050, binary=False, precision=3), "1.05 kB")

        def test_half_up_is_exact(self):
            self.assertEqual(format_size(1025, binary=False, precision=2), "1.03 kB")
            self.assertEqual(format_size(1250, binary=False, precision=1), "1.3 kB")
            self.assertEqual(format_size(1350, binary=False, precision=1), "1.4 kB")
            self.assertEqual(format_size(2500, binary=False, precision=0), "3 kB")
            self.assertEqual(format_size(2499, binary=False, precision=0), "2 kB")

        def test_promotion_on_rounding(self):
            self.assertEqual(format_size(1024 * 1024 - 1), "1 MiB")
            self.assertEqual(format_size(1024 * 1024 - 51), "1 MiB")
            self.assertEqual(format_size(1024 * 1024 - 52), "1023.9 KiB")
            self.assertEqual(format_size(999999, binary=False), "1 MB")
            self.assertEqual(format_size(999949, binary=False), "999.9 kB")
            self.assertEqual(format_size(999950, binary=False), "1 MB")
            self.assertEqual(format_size(999500, binary=False, precision=0), "1 MB")
            self.assertEqual(format_size(999499, binary=False, precision=0), "999 kB")

        def test_no_promotion_in_last_unit(self):
            self.assertEqual(format_size(1024 ** 6), "1024 PiB")
            self.assertEqual(format_size(2 * 1024 ** 6 + 1024 ** 5 // 2), "2048.5 PiB")
            self.assertEqual(format_size(10 ** 18, binary=False), "1000 PB")

        def test_negative(self):
            self.assertEqual(format_size(-1536), "-1.5 KiB")
            self.assertEqual(format_size(-5), "-5 B")
            self.assertEqual(format_size(-1000, binary=False), "-1 kB")

        def test_bad_precision(self):
            for p in (-1, 4):
                with self.assertRaises(ValueError):
                    format_size(1000, precision=p)

        def test_large_exact_arithmetic(self):
            self.assertEqual(format_size(10 ** 17 + 1, binary=False, precision=3), "100 PB")
            self.assertEqual(format_size(3 * 1024 ** 4 + 1024 ** 4 // 4), "3.3 TiB")


    class ParseSize(unittest.TestCase):
        def test_plain_and_bytes(self):
            self.assertEqual(parse_size("0"), 0)
            self.assertEqual(parse_size("512"), 512)
            self.assertEqual(parse_size("512 B"), 512)
            self.assertEqual(parse_size("512b"), 512)
            self.assertEqual(parse_size(" 7 "), 7)

        def test_units(self):
            self.assertEqual(parse_size("1kB"), 1000)
            self.assertEqual(parse_size("2 MB"), 2_000_000)
            self.assertEqual(parse_size("1 GB"), 10 ** 9)
            self.assertEqual(parse_size("1 TB"), 10 ** 12)
            self.assertEqual(parse_size("1 PB"), 10 ** 15)
            self.assertEqual(parse_size("1 KiB"), 1024)
            self.assertEqual(parse_size("1 MiB"), 1024 ** 2)
            self.assertEqual(parse_size("1 GiB"), 1024 ** 3)
            self.assertEqual(parse_size("1 TiB"), 1024 ** 4)
            self.assertEqual(parse_size("1 PiB"), 1024 ** 5)

        def test_single_letters_are_binary(self):
            for letter, power in zip("kmgtp", range(1, 6)):
                self.assertEqual(parse_size("1" + letter), 1024 ** power)
                self.assertEqual(parse_size("3 " + letter.upper()), 3 * 1024 ** power)

        def test_case_insensitive(self):
            self.assertEqual(parse_size("1 KIB"), 1024)
            self.assertEqual(parse_size("1 kib"), 1024)
            self.assertEqual(parse_size("1 Kb"), 1000)
            self.assertEqual(parse_size("1 mB"), 10 ** 6)

        def test_decimals_round_half_up(self):
            self.assertEqual(parse_size("1.5 KiB"), 1536)
            self.assertEqual(parse_size("0.5"), 1)
            self.assertEqual(parse_size("0.49"), 0)
            self.assertEqual(parse_size("2.5"), 3)
            self.assertEqual(parse_size("1.0005 kB"), 1001)
            self.assertEqual(parse_size("1.0004 kB"), 1000)
            self.assertEqual(parse_size("0.1 MB"), 100000)
            self.assertEqual(parse_size("1.25 GiB"), 1342177280)

        def test_underscores(self):
            self.assertEqual(parse_size("1_000"), 1000)
            self.assertEqual(parse_size("1_000_000 B"), 10 ** 6)
            self.assertEqual(parse_size("1_0.5 K"), 10 * 1024 + 512)

        def test_errors(self):
            for bad in ("", " ", "KiB", "-1", "+1", "1e3", ".5", "1.", "1__0", "_1", "1_", "1 XB", "1 KB B", "1 K B", "1,5 K", "0x10", "1 Mbit",
                        "1.5.2", "1 kiB2"):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    parse_size(bad)

        def test_round_trip(self):
            for n in (0, 1, 999, 1000, 1023, 1024, 1536, 5 * 1024 ** 3):
                self.assertEqual(parse_size(format_size(n, precision=3)), n)
            self.assertEqual(parse_size(format_size(1536)), 1536)
            self.assertEqual(parse_size(format_size(1024 ** 3)), 1024 ** 3)


    class FormatDuration(unittest.TestCase):
        def test_basic(self):
            self.assertEqual(format_duration(0), "0s")
            self.assertEqual(format_duration(1), "1s")
            self.assertEqual(format_duration(59), "59s")
            self.assertEqual(format_duration(60), "1m")
            self.assertEqual(format_duration(61), "1m 1s")
            self.assertEqual(format_duration(3599), "59m 59s")
            self.assertEqual(format_duration(3600), "1h")
            self.assertEqual(format_duration(3725), "1h 2m")
            self.assertEqual(format_duration(86400), "1d")
            self.assertEqual(format_duration(86400 + 5), "1d")
            self.assertEqual(format_duration(2 * 86400 + 3 * 3600 + 4 * 60 + 5), "2d 3h")

        def test_parts(self):
            self.assertEqual(format_duration(3725, parts=1), "1h")
            self.assertEqual(format_duration(3725, parts=3), "1h 2m 5s")
            self.assertEqual(format_duration(3725, parts=4), "1h 2m 5s")
            self.assertEqual(format_duration(2 * 86400 + 3 * 3600 + 4 * 60 + 5, parts=4), "2d 3h 4m 5s")
            self.assertEqual(format_duration(2 * 86400 + 3 * 3600 + 4 * 60 + 5, parts=3), "2d 3h 4m")
            self.assertEqual(format_duration(90, parts=1), "1m")
            self.assertEqual(format_duration(45, parts=3), "45s")

        def test_zero_units_are_skipped(self):
            self.assertEqual(format_duration(3601, parts=3), "1h 1s")
            self.assertEqual(format_duration(3601, parts=2), "1h")
            self.assertEqual(format_duration(86400 + 60, parts=2), "1d")
            self.assertEqual(format_duration(86400 + 60, parts=3), "1d 1m")
            self.assertEqual(format_duration(86400 + 1, parts=4), "1d 1s")
            self.assertEqual(format_duration(3600 + 5, parts=3), "1h 5s")
            self.assertEqual(format_duration(120, parts=3), "2m")

        def test_truncation_and_floats(self):
            self.assertEqual(format_duration(59.9), "59s")
            self.assertEqual(format_duration(0.9), "0s")
            self.assertEqual(format_duration(61.5), "1m 1s")
            self.assertEqual(format_duration(-0.5), "0s")
            self.assertEqual(format_duration(-59.9), "-59s")

        def test_negative(self):
            self.assertEqual(format_duration(-90), "-1m 30s")
            self.assertEqual(format_duration(-3600), "-1h")
            self.assertEqual(format_duration(-1), "-1s")

        def test_bad_parts(self):
            for p in (0, -1):
                with self.assertRaises(ValueError):
                    format_duration(10, parts=p)


    class ParseDuration(unittest.TestCase):
        def test_components(self):
            self.assertEqual(parse_duration("90s"), 90)
            self.assertEqual(parse_duration("1h 30m"), 5400)
            self.assertEqual(parse_duration("1h30m"), 5400)
            self.assertEqual(parse_duration("2d"), 172800)
            self.assertEqual(parse_duration("1w"), 604800)
            self.assertEqual(parse_duration("1w 1d 1h 1m 1s"), 604800 + 86400 + 3600 + 60 + 1)
            self.assertEqual(parse_duration("1s 1m"), 61)
            self.assertEqual(parse_duration("  1 h  30 m "), 5400)
            self.assertEqual(parse_duration("1H 2M 3S"), 3723)
            self.assertEqual(parse_duration("0s"), 0)

        def test_bare_number(self):
            self.assertEqual(parse_duration("90"), 90)
            self.assertEqual(parse_duration(" 0 "), 0)
            self.assertEqual(parse_duration("007"), 7)

        def test_decimals_and_rounding(self):
            self.assertEqual(parse_duration("1.5h"), 5400)
            self.assertEqual(parse_duration("0.5m"), 30)
            self.assertEqual(parse_duration("0.5s"), 1)
            self.assertEqual(parse_duration("0.4s"), 0)
            self.assertEqual(parse_duration("1.5s"), 2)
            self.assertEqual(parse_duration("2.5s"), 3)
            self.assertEqual(parse_duration("0.3s"), 0)
            self.assertEqual(parse_duration("0.25m 0.5s"), 16)
            self.assertEqual(parse_duration("0.1d"), 8640)

        def test_negative(self):
            self.assertEqual(parse_duration("-5m"), -300)
            self.assertEqual(parse_duration("- 1h 30m"), -5400)
            self.assertEqual(parse_duration("-0.5s"), -1)
            self.assertEqual(parse_duration("-0.4s"), 0)
            self.assertEqual(parse_duration("-1.5s"), -2)
            self.assertEqual(parse_duration("-0s"), 0)

        def test_errors(self):
            for bad in ("", "  ", "h", "1x", "1 hour", "1h 1h", "1h1H", "-", "- ", "--5s", "1h,30m", "1h and 30m", "1.h", ".5h", "1h -30m", "+5s", "-5",
                        "1.5", "5 s s", "1h30", "m5"):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    parse_duration(bad)

        def test_round_trips(self):
            for n in (0, 1, 59, 60, 61, 3599, 3600, 86399, 86400, 90061):
                self.assertEqual(parse_duration(format_duration(n, parts=4)), n)


    if __name__ == "__main__":
        unittest.main()
''')

HF = Lib(
    name="humanfmt", lang="python", title="the size and duration formatter (`humanfmt.py`)",
    blurb="The storage dashboard shows sizes and durations with this module and parses what users type.",
    files={"humanfmt.py": HF_SRC, "README.md": HF_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": HF_VISIBLE},
    hidden_tests={"tests/test_full.py": HF_HIDDEN},
    mutate=["humanfmt.py"], difficulty=3, tags=["formatting", "numbers"],
    probes=[
        'format_size(1024 * 1024 - 1)',
        'format_size(999950, binary=False)',
        'format_size(1250, binary=False)',
        'format_size(1005, binary=False, precision=2)',
        'format_size(1024 ** 6)',
        'format_size(-1536)',
        'parse_size("1.5 KiB")',
        'parse_size("3 g")',
        'parse_size("1_0.5 K")',
        'format_duration(3601, parts=3)',
        'format_duration(86400 + 60, parts=2)',
        'format_duration(-59.9)',
        'parse_duration("0.5s")',
        'parse_duration("- 1h 30m")',
        'parse_duration("1s 1m")',
    ],
    probe_import="from humanfmt import *",
)


# ======================================================================================================================
# identcase: identifier word splitting and case conversion with acronym rules
# ======================================================================================================================

IC_README = dd(r'''
    # identcase

    Renames identifiers between naming styles for the code-generator. One module, `identcase.py`.

    ## `split_words(ident) -> list[str]`
    Splits an identifier into words, keeping each word's letters as written:
    * `_`, `-`, `.` and space are separators; runs of them count as one, and leading/trailing ones are ignored.
    * A new word starts at an upper-case letter that follows a lower-case letter or a digit (`fooBar` gives `foo`, `Bar`; `foo2Bar` gives `foo2`, `Bar`).
    * A new word starts at an upper-case letter that follows another upper-case letter when it is itself followed by a lower-case letter, so that
      the last capital of an acronym begins the next word (`HTTPServer` gives `HTTP`, `Server`; `ABc` gives `A`, `Bc`).
    * Digits never start a word: they stay with the letters before them (`http2server` is one word, `v2` is one word); digits at the start of a word
      stay with the next letters (`2fa` is one word).
    * Empty input, or input made only of separators, gives `[]`.

    ## Conversions
    All take `ident` and, for the camel styles, the keyword argument `acronyms` (an iterable of words, compared case-insensitively; default none).
    * `to_snake(ident)`: words lower-cased, joined by `_`.
    * `to_kebab(ident)`: words lower-cased, joined by `-`.
    * `to_screaming(ident)`: words upper-cased, joined by `_`.
    * `to_pascal(ident, acronyms=())`: every word capitalised (first letter upper-case, the rest lower-case), except a word whose lower-case
      form is in `acronyms`, which becomes fully upper-case; no separators.
    * `to_camel(ident, acronyms=())`: like Pascal, but the first word is entirely lower-case (even if it is an acronym).
    The result for an identifier without words is `""`.
    * `convert(ident, style, acronyms=())` with `style` one of `"snake"`, `"kebab"`, `"screaming"`, `"pascal"`, `"camel"`; any other style is a `ValueError`.

    ## `detect_style(ident) -> str`
    Looks at `ident` (assumed to be a single identifier):
    * `"empty"` if it has no letters or digits at all;
    * `"screaming"` if it has no lower-case letters, at least one upper-case letter and at least one `_` (`MAX_SIZE`);
    * `"snake"` if it has a `_`, no `-`, and no upper-case letters;
    * `"kebab"` if it has a `-`, no `_`, and no upper-case letters;
    * `"camel"` if it has neither `_` nor `-`, starts with a lower-case letter and has an upper-case letter somewhere;
    * `"pascal"` if it has neither `_` nor `-`, starts with an upper-case letter and has a lower-case letter;
    * `"upper"` if it has neither separator and no lower-case letters but an upper-case one (`HTTP`);
    * `"lower"` if it has neither separator, no upper-case letters (`http`, `v2`);
    * `"mixed"` otherwise.
    The rules apply in this order.
''')

IC_SRC = dd(r'''
    """Identifier case conversion."""

    _SEPARATORS = "_-. "


    def split_words(ident):
        words = []
        cur = ""
        for i, ch in enumerate(ident):
            if ch in _SEPARATORS:
                if cur:
                    words.append(cur)
                    cur = ""
                continue
            if cur and ch.isupper():
                nxt = ident[i + 1] if i + 1 < len(ident) else ""
                last = cur[-1]
                if last.islower() or last.isdigit() or (last.isupper() and nxt.islower()):
                    words.append(cur)
                    cur = ""
            cur += ch
        if cur:
            words.append(cur)
        return words


    def to_snake(ident):
        return "_".join(w.lower() for w in split_words(ident))


    def to_kebab(ident):
        return "-".join(w.lower() for w in split_words(ident))


    def to_screaming(ident):
        return "_".join(w.upper() for w in split_words(ident))


    def _pascal_word(word, acronyms):
        if word.lower() in acronyms:
            return word.upper()
        return word[:1].upper() + word[1:].lower()


    def to_pascal(ident, acronyms=()):
        known = {a.lower() for a in acronyms}
        return "".join(_pascal_word(w, known) for w in split_words(ident))


    def to_camel(ident, acronyms=()):
        known = {a.lower() for a in acronyms}
        words = split_words(ident)
        if not words:
            return ""
        return words[0].lower() + "".join(_pascal_word(w, known) for w in words[1:])


    def convert(ident, style, acronyms=()):
        if style == "snake":
            return to_snake(ident)
        if style == "kebab":
            return to_kebab(ident)
        if style == "screaming":
            return to_screaming(ident)
        if style == "pascal":
            return to_pascal(ident, acronyms)
        if style == "camel":
            return to_camel(ident, acronyms)
        raise ValueError("unknown style: %r" % (style,))


    def detect_style(ident):
        if not any(c.isalnum() for c in ident):
            return "empty"
        has_upper = any(c.isupper() for c in ident)
        has_lower = any(c.islower() for c in ident)
        under, dash = "_" in ident, "-" in ident
        if not has_lower and has_upper and under:
            return "screaming"
        if under and not dash and not has_upper:
            return "snake"
        if dash and not under and not has_upper:
            return "kebab"
        if not under and not dash:
            if ident[0].islower() and has_upper:
                return "camel"
            if ident[0].isupper() and has_lower:
                return "pascal"
            if not has_lower and has_upper:
                return "upper"
            if not has_upper:
                return "lower"
        return "mixed"
''')

IC_VISIBLE = dd(r'''
    import unittest

    from identcase import detect_style, split_words, to_camel, to_snake


    class BasicTests(unittest.TestCase):
        def test_split(self):
            self.assertEqual(split_words("fooBar_baz"), ["foo", "Bar", "baz"])

        def test_snake_camel(self):
            self.assertEqual(to_snake("parseHTTPResponse"), "parse_http_response")
            self.assertEqual(to_camel("max_size"), "maxSize")

        def test_detect(self):
            self.assertEqual(detect_style("max_size"), "snake")


    if __name__ == "__main__":
        unittest.main()
''')

IC_HIDDEN = dd(r'''
    import unittest

    from identcase import convert, detect_style, split_words, to_camel, to_kebab, to_pascal, to_screaming, to_snake


    class Split(unittest.TestCase):
        def test_separators(self):
            self.assertEqual(split_words("foo_bar-baz.qux quux"), ["foo", "bar", "baz", "qux", "quux"])
            self.assertEqual(split_words("__foo__bar__"), ["foo", "bar"])
            self.assertEqual(split_words("-.-a. .b-"), ["a", "b"])
            self.assertEqual(split_words(""), [])
            self.assertEqual(split_words("___"), [])
            self.assertEqual(split_words(" . - _ "), [])

        def test_camel_boundaries(self):
            self.assertEqual(split_words("fooBar"), ["foo", "Bar"])
            self.assertEqual(split_words("fooBarBaz"), ["foo", "Bar", "Baz"])
            self.assertEqual(split_words("FooBar"), ["Foo", "Bar"])
            self.assertEqual(split_words("foo"), ["foo"])
            self.assertEqual(split_words("Foo"), ["Foo"])
            self.assertEqual(split_words("a"), ["a"])
            self.assertEqual(split_words("aB"), ["a", "B"])
            self.assertEqual(split_words("aBc"), ["a", "Bc"])

        def test_acronyms(self):
            self.assertEqual(split_words("HTTPServer"), ["HTTP", "Server"])
            self.assertEqual(split_words("parseHTTPResponse"), ["parse", "HTTP", "Response"])
            self.assertEqual(split_words("userID"), ["user", "ID"])
            self.assertEqual(split_words("IDs"), ["I", "Ds"])
            self.assertEqual(split_words("HTTP"), ["HTTP"])
            self.assertEqual(split_words("ABc"), ["A", "Bc"])
            self.assertEqual(split_words("ABCd"), ["AB", "Cd"])
            self.assertEqual(split_words("XMLHttpRequest"), ["XML", "Http", "Request"])
            self.assertEqual(split_words("getURL"), ["get", "URL"])
            self.assertEqual(split_words("URLs"), ["UR", "Ls"])

        def test_digits(self):
            self.assertEqual(split_words("http2server"), ["http2server"])
            self.assertEqual(split_words("http2Server"), ["http2", "Server"])
            self.assertEqual(split_words("v2"), ["v2"])
            self.assertEqual(split_words("2fa"), ["2fa"])
            self.assertEqual(split_words("sha256Sum"), ["sha256", "Sum"])
            self.assertEqual(split_words("HTTP2Server"), ["HTTP2", "Server"])
            self.assertEqual(split_words("a1B2c3"), ["a1", "B2c3"])
            self.assertEqual(split_words("x_2_y"), ["x", "2", "y"])
            self.assertEqual(split_words("123"), ["123"])
            self.assertEqual(split_words("ab12CD34"), ["ab12", "CD34"])

        def test_mixed_separators_and_case(self):
            self.assertEqual(split_words("Foo_barBaz-QUX"), ["Foo", "bar", "Baz", "QUX"])
            self.assertEqual(split_words("MAX_SIZE"), ["MAX", "SIZE"])
            self.assertEqual(split_words("some.dotted.Name"), ["some", "dotted", "Name"])
            self.assertEqual(split_words("a_B"), ["a", "B"])
            self.assertEqual(split_words("A_b"), ["A", "b"])


    class Conversions(unittest.TestCase):
        def test_snake_kebab_screaming(self):
            self.assertEqual(to_snake("parseHTTPResponse"), "parse_http_response")
            self.assertEqual(to_snake("Already_Mixed-Case"), "already_mixed_case")
            self.assertEqual(to_kebab("parseHTTPResponse"), "parse-http-response")
            self.assertEqual(to_kebab("snake_case_name"), "snake-case-name")
            self.assertEqual(to_screaming("maxSize"), "MAX_SIZE")
            self.assertEqual(to_screaming("http-server"), "HTTP_SERVER")
            self.assertEqual(to_snake("v2Api"), "v2_api")
            self.assertEqual(to_snake(""), "")
            self.assertEqual(to_kebab("__"), "")
            self.assertEqual(to_screaming(" "), "")

        def test_pascal(self):
            self.assertEqual(to_pascal("max_size"), "MaxSize")
            self.assertEqual(to_pascal("parseHTTPResponse"), "ParseHttpResponse")
            self.assertEqual(to_pascal("HTTP_SERVER"), "HttpServer")
            self.assertEqual(to_pascal("v2_api"), "V2Api")
            self.assertEqual(to_pascal("a"), "A")
            self.assertEqual(to_pascal(""), "")
            self.assertEqual(to_pascal("2fa_code"), "2faCode")

        def test_camel(self):
            self.assertEqual(to_camel("max_size"), "maxSize")
            self.assertEqual(to_camel("MaxSize"), "maxSize")
            self.assertEqual(to_camel("HTTP_SERVER"), "httpServer")
            self.assertEqual(to_camel("parse-HTTP-response"), "parseHttpResponse")
            self.assertEqual(to_camel("A"), "a")
            self.assertEqual(to_camel(""), "")
            self.assertEqual(to_camel("__x__"), "x")

        def test_acronyms_pascal(self):
            self.assertEqual(to_pascal("http_server", acronyms=["http"]), "HTTPServer")
            self.assertEqual(to_pascal("parse_http_response", acronyms={"http"}), "ParseHTTPResponse")
            self.assertEqual(to_pascal("user_id", acronyms=("ID",)), "UserID")
            self.assertEqual(to_pascal("user_id", acronyms=["Id", "x"]), "UserID")
            self.assertEqual(to_pascal("api_url", acronyms=["api", "url"]), "APIURL")
            self.assertEqual(to_pascal("http2_server", acronyms=["http"]), "Http2Server")
            self.assertEqual(to_pascal("a_b", acronyms=["a"]), "AB")
            self.assertEqual(to_pascal("xml_parser", acronyms=[]), "XmlParser")

        def test_acronyms_camel(self):
            self.assertEqual(to_camel("http_server", acronyms=["http"]), "httpServer")
            self.assertEqual(to_camel("parse_http_response", acronyms=["HTTP"]), "parseHTTPResponse")
            self.assertEqual(to_camel("get_url", acronyms=["url"]), "getURL")
            self.assertEqual(to_camel("id", acronyms=["id"]), "id")
            self.assertEqual(to_camel("user_id_list", acronyms=["id"]), "userIDList")

        def test_acronym_input_forms(self):
            self.assertEqual(to_pascal("ab_cd_ef", acronyms=iter(["cd"])), "AbCDEf")
            self.assertEqual(to_pascal("ab_cd_ef", acronyms=["CD"]), "AbCDEf")
            self.assertEqual(to_pascal("ab_cd_ef", acronyms=("cD",)), "AbCDEf")
            self.assertEqual(to_camel("ab_cd_ef", acronyms=iter(["ef"])), "abCdEF")

        def test_round_trips(self):
            for ident in ("parse_http_response", "max_size", "x", "ab_cd_ef", "v2_api"):
                self.assertEqual(to_snake(to_camel(ident)), ident)
                self.assertEqual(to_snake(to_pascal(ident)), ident)

        def test_convert_dispatch(self):
            self.assertEqual(convert("fooBar", "snake"), "foo_bar")
            self.assertEqual(convert("fooBar", "kebab"), "foo-bar")
            self.assertEqual(convert("fooBar", "screaming"), "FOO_BAR")
            self.assertEqual(convert("foo_bar", "pascal"), "FooBar")
            self.assertEqual(convert("foo_bar", "camel"), "fooBar")
            self.assertEqual(convert("foo_url", "pascal", acronyms=["url"]), "FooURL")
            self.assertEqual(convert("foo_url", "camel", ["url"]), "fooURL")
            for bad in ("Snake", "", "title", None):
                with self.assertRaises(ValueError):
                    convert("x", bad)


    class Detect(unittest.TestCase):
        def test_styles(self):
            cases = {
                "max_size": "snake", "a_b": "snake", "_x": "snake", "x_": "snake", "v2_api": "snake",
                "my-kebab-name": "kebab", "a-b": "kebab", "-x": "kebab",
                "MAX_SIZE": "screaming", "A_B": "screaming", "_A": "screaming", "X_1": "screaming",
                "maxSize": "camel", "aB": "camel", "xmlHTTPRequest": "camel",
                "MaxSize": "pascal", "Ab": "pascal", "HTTPServer": "pascal", "Xy2": "pascal",
                "HTTP": "upper", "A": "upper", "A1": "upper",
                "http": "lower", "v2": "lower", "x": "lower", "a1": "lower",
                "": "empty", "_": "empty", "-_-": "empty", ".": "empty",
                "Max_Size": "mixed", "max-Size": "mixed", "a_b-c": "mixed", "Foo-bar": "mixed", "foo_Bar": "mixed", "a-b_c": "mixed",
                "My_": "mixed", "MAX-SIZE": "mixed", "ABC-d": "mixed", "Foo_bar": "mixed",
            }
            for ident, want in cases.items():
                self.assertEqual(detect_style(ident), want, ident)

        def test_digits_only(self):
            self.assertEqual(detect_style("123"), "lower")
            self.assertEqual(detect_style("1_2"), "snake")
            self.assertEqual(detect_style("1-2"), "kebab")


    if __name__ == "__main__":
        unittest.main()
''')

IC = Lib(
    name="identcase", lang="python", title="the identifier case converter (`identcase.py`)",
    blurb="The code generator renames fields between snake, kebab, camel and Pascal case with this module.",
    files={"identcase.py": IC_SRC, "README.md": IC_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": IC_VISIBLE},
    hidden_tests={"tests/test_full.py": IC_HIDDEN},
    mutate=["identcase.py"], difficulty=2, tags=["naming", "text"],
    probes=[
        'split_words("parseHTTPResponse2Go")',
        'split_words("XMLHttpRequest")',
        'split_words("a1B2c3")',
        'split_words("__foo__bar__")',
        'to_snake("userID")',
        'to_pascal("http2_server", acronyms=["http"])',
        'to_pascal("parse_http_response", acronyms=["HTTP"])',
        'to_camel("http_server", acronyms=["http"])',
        'to_camel("user_id_list", acronyms=["id"])',
        'detect_style("My_")',
        'detect_style("HTTPServer")',
        'detect_style("A1")',
        'convert("foo_url", "camel", ["url"])',
    ],
    probe_import="from identcase import *",
)


# ======================================================================================================================
# hexdump: a hex dump format with run collapsing, and its reader
# ======================================================================================================================

HD_README = dd(r'''
    # hexdump

    Dump and re-read binary blobs in the team's text dump format. One module, `hexdump.py`.

    ## `dump(data, width=16, group=4, base=0) -> str`
    `data` is `bytes`. `width` is the number of bytes per row (1-64) and `group` the group size inside a row (1 to `width`); `base`
    (not negative) is the offset shown for the first byte. Violations are a `ValueError`.

    **Row**: `OFFSET`, two spaces, `HEX`, two spaces, `|ASCII|`.
    * `OFFSET` is `base +` the row's start, in lowercase hex with at least 6 digits.
    * `HEX` has every byte as two lowercase hex digits. Bytes in the same group are separated by one space, groups by two spaces. A short
      last row is padded with blanks (the missing bytes' two digits and their separators) so that it is as wide as a full row and the `|` of
      every row is in the same column.
    * `ASCII` has one character per byte of the row: the byte itself when it is in `0x20`-`0x7e`, `.` otherwise. (`|` itself is shown as is.)

    **Collapsing**: a run of three or more identical *full* rows is written as its first row followed by one line `*N`, where `N` is
    the number of rows left out (the run length minus one). A run of exactly two identical rows is written in full. The offsets of the rows
    that follow are not affected.

    **End**: the last line holds only the end offset (`base + len(data)`, lowercase hex, at least 6 digits). Empty data gives just that line.
    Lines are joined with `\n`, without a final newline.

    ## `parse_dump(text) -> bytes`
    The inverse of `dump` for any `width`, `group` and `base`. Blank lines are ignored. Every line is one of:
    * a row `OFFSET  HEX|ASCII|`... exactly as written by `dump`: offset of at least 6 lowercase hex digits, two spaces, bytes as two-digit
      lowercase hex numbers separated by any amount of spaces (one or more), then at least... the closing bar part `|ASCII|`. The text between the
      bars must have exactly as many characters as the row has bytes, and a row must have at least one byte;
    * a repeat line `*N` (`N` a positive integer): the previous row repeated `N` more times;
    * the end line: only an offset of at least 6 lowercase hex digits; it must be the last non-blank line.
    The rules: the first row's offset is the base; each later row's offset must equal `base` plus the number of bytes read so far; the first row's
    byte count is the row length; a row may be shorter than that only if it is the last row; no row may be longer; `*N` may only follow a full row;
    the end offset must equal `base` plus the bytes read (for an empty dump any offset is accepted). Missing end line, text after it, or any
    violation is a `ValueError`.
''')

HD_SRC = dd(r'''
    """Hex dump format."""
    import re

    _ROW = re.compile(r"([0-9a-f]{6,})  ([0-9a-f ]*)\|(.*)\|")


    def _hex(chunk, width, group):
        out = []
        for i in range(width):
            if i:
                out.append("  " if i % group == 0 else " ")
            out.append("%02x" % chunk[i] if i < len(chunk) else "  ")
        return "".join(out)


    def _ascii(chunk):
        return "".join(chr(b) if 0x20 <= b <= 0x7E else "." for b in chunk)


    def dump(data, width=16, group=4, base=0):
        if not 1 <= width <= 64:
            raise ValueError("width must be 1..64")
        if not 1 <= group <= width:
            raise ValueError("group must be 1..width")
        if base < 0:
            raise ValueError("base must not be negative")
        rows = [data[i:i + width] for i in range(0, len(data), width)]
        lines = []
        i = 0
        while i < len(rows):
            row = rows[i]
            lines.append("%06x  %s  |%s|" % (base + i * width, _hex(row, width, group), _ascii(row)))
            if len(row) == width:
                j = i + 1
                while j < len(rows) and rows[j] == row:
                    j += 1
                if j - i >= 3:
                    lines.append("*%d" % (j - i - 1))
                    i = j
                    continue
            i += 1
        lines.append("%06x" % (base + len(data)))
        return "\n".join(lines)


    def parse_dump(text):
        out = bytearray()
        prev = None
        base = None
        row_len = None
        short = False
        ended = False
        for line in (ln for ln in text.splitlines() if ln.strip()):
            if ended:
                raise ValueError("text after the end offset")
            m = re.fullmatch(r"\*([0-9]+)", line)
            if m:
                n = int(m.group(1))
                if n < 1 or prev is None or short:
                    raise ValueError("bad repeat line")
                out += prev * n
                continue
            m = re.fullmatch(r"[0-9a-f]{6,}", line)
            if m:
                end = int(line, 16)
                if base is not None and end != base + len(out):
                    raise ValueError("end offset does not match")
                ended = True
                continue
            m = _ROW.fullmatch(line)
            if not m:
                raise ValueError("cannot parse %r" % line)
            tokens = m.group(2).split()
            if not tokens or any(not re.fullmatch(r"[0-9a-f]{2}", t) for t in tokens):
                raise ValueError("bad hex bytes in %r" % line)
            row = bytes(int(t, 16) for t in tokens)
            if len(m.group(3)) != len(row):
                raise ValueError("ascii column has the wrong length")
            offset = int(m.group(1), 16)
            if base is None:
                base = offset
            elif offset != base + len(out):
                raise ValueError("offset mismatch")
            if row_len is None:
                row_len = len(row)
            elif short or len(row) > row_len:
                raise ValueError("row length")
            elif len(row) < row_len:
                short = True
            out += row
            prev = row
        if not ended:
            raise ValueError("missing end offset")
        return bytes(out)
''')

HD_VISIBLE = dd(r'''
    import unittest

    from hexdump import dump, parse_dump


    class BasicTests(unittest.TestCase):
        def test_dump(self):
            self.assertEqual(dump(b"ABCDEFGH", width=4, group=2), "000000  41 42  43 44  |ABCD|\n000004  45 46  47 48  |EFGH|\n000008")

        def test_empty(self):
            self.assertEqual(dump(b""), "000000")

        def test_round_trip(self):
            data = bytes(range(40))
            self.assertEqual(parse_dump(dump(data)), data)


    if __name__ == "__main__":
        unittest.main()
''')

HD_HIDDEN = dd(r'''
    import random
    import unittest

    from hexdump import dump, parse_dump


    def row(off, hexpart, ascii_, pad=0):
        return "%06x  %s%s  |%s|" % (off, hexpart, " " * pad, ascii_)


    class Dump(unittest.TestCase):
        def test_two_rows(self):
            self.assertEqual(dump(b"ABCDEFGH", width=4, group=2), "000000  41 42  43 44  |ABCD|\n000004  45 46  47 48  |EFGH|\n000008")

        def test_default_layout(self):
            data = bytes(range(0x41, 0x41 + 16))
            want = "000000  41 42 43 44  45 46 47 48  49 4a 4b 4c  4d 4e 4f 50  |ABCDEFGHIJKLMNOP|\n000010"
            self.assertEqual(dump(data), want)

        def test_group_sizes(self):
            data = b"ABCDEFGH"
            self.assertEqual(dump(data, width=8, group=1), "000000  41  42  43  44  45  46  47  48  |ABCDEFGH|\n000008")
            self.assertEqual(dump(data, width=8, group=8), "000000  41 42 43 44 45 46 47 48  |ABCDEFGH|\n000008")
            self.assertEqual(dump(data, width=8, group=3), "000000  41 42 43  44 45 46  47 48  |ABCDEFGH|\n000008")
            self.assertEqual(dump(data, width=8, group=4), "000000  41 42 43 44  45 46 47 48  |ABCDEFGH|\n000008")

        def test_short_last_row_is_padded(self):
            got = dump(b"ABCDEF", width=4, group=2).split("\n")
            self.assertEqual(got[0], "000000  41 42  43 44  |ABCD|")
            self.assertEqual(got[1], "000004  45 46" + " " * 9 + "|EF|")
            self.assertEqual(got[2], "000006")
            self.assertEqual(got[0].index("|"), got[1].index("|"))
            got = dump(b"ABCDEFG", width=4, group=2).split("\n")
            self.assertEqual(got[1], "000004  45 46  47" + " " * 5 + "|EFG|")

        def test_padding_keeps_columns_aligned_for_all_lengths(self):
            for n in range(1, 40):
                lines = dump(bytes(range(65, 65 + n)), width=8, group=3).split("\n")[:-1]
                bars = {ln.index("|") for ln in lines}
                self.assertEqual(len(bars), 1, n)

        def test_ascii_column(self):
            data = bytes([0x1f, 0x20, 0x41, 0x7e, 0x7f, 0x80, 0xff, 0x00, 0x7c, 0x22])
            got = dump(data, width=10, group=5)
            self.assertEqual(got.split("\n")[0], '000000  1f 20 41 7e 7f  80 ff 00 7c 22  |. A~....|"|')

        def test_offsets_grow_by_width(self):
            data = bytes(range(0, 200, 3))
            lines = dump(data, width=8, group=4).split("\n")
            offsets = [ln[:6] for ln in lines]
            self.assertEqual(offsets[:4], ["000000", "000008", "000010", "000018"])
            self.assertEqual(offsets[-1], "%06x" % len(data))

        def test_base_offset(self):
            got = dump(b"ABCDEFGH", width=4, group=2, base=0x1f0).split("\n")
            self.assertEqual(got[0].startswith("0001f0  "), True)
            self.assertEqual(got[1].startswith("0001f4  "), True)
            self.assertEqual(got[2], "0001f8")
            self.assertEqual(dump(b"", base=0x12345678), "12345678")
            self.assertEqual(dump(b"A", width=1, group=1, base=0xfffff)[:6], "0fffff")
            self.assertEqual(dump(b"AB", width=1, group=1, base=0xfffff).split("\n")[-1], "100001")

        def test_empty(self):
            self.assertEqual(dump(b""), "000000")
            self.assertEqual(dump(b"", width=1, group=1, base=5), "000005")

        def test_collapse_runs(self):
            z = b"\x00" * 4
            self.assertEqual(dump(z * 3, width=4, group=2).split("\n"), [row(0, "00 00  00 00", "...."), "*2", "00000c"])
            self.assertEqual(dump(z * 5, width=4, group=2).split("\n"), [row(0, "00 00  00 00", "...."), "*4", "000014"])

        def test_two_identical_rows_are_written_in_full(self):
            z = b"\x00" * 4
            self.assertEqual(dump(z * 2, width=4, group=2).split("\n"), [row(0, "00 00  00 00", "...."), row(4, "00 00  00 00", "...."), "000008"])

        def test_run_in_the_middle_and_offsets_after(self):
            data = b"ABCD" + b"xxxx" * 4 + b"EFGH"
            want = [row(0, "41 42  43 44", "ABCD"), row(4, "78 78  78 78", "xxxx"), "*3", row(20, "45 46  47 48", "EFGH"), "000018"]
            self.assertEqual(dump(data, width=4, group=2).split("\n"), want)

        def test_two_runs(self):
            data = b"aaaa" * 3 + b"bbbb" * 4
            want = [row(0, "61 61  61 61", "aaaa"), "*2", row(12, "62 62  62 62", "bbbb"), "*3", "00001c"]
            self.assertEqual(dump(data, width=4, group=2).split("\n"), want)

        def test_run_before_a_short_row(self):
            data = b"aaaa" * 3 + b"aa"
            got = dump(data, width=4, group=2).split("\n")
            self.assertEqual(got, [row(0, "61 61  61 61", "aaaa"), "*2", "00000c  61 61" + " " * 9 + "|aa|", "00000e"])

        def test_short_row_equal_prefix_is_not_collapsed(self):
            data = b"aaaa" * 2 + b"aaaa"[:3]
            got = dump(data, width=4, group=2).split("\n")
            self.assertEqual(len(got), 4)
            self.assertNotIn("*", "".join(got))

        def test_alternating_rows_do_not_collapse(self):
            data = (b"aaaa" + b"bbbb") * 3
            self.assertEqual(len(dump(data, width=4, group=2).split("\n")), 7)

        def test_parameter_errors(self):
            for kw in ({"width": 0}, {"width": 65}, {"width": -1}, {"group": 0}, {"width": 4, "group": 5}, {"base": -1}):
                with self.assertRaises(ValueError, msg=str(kw)):
                    dump(b"abc", **kw)
            dump(b"abc", width=64, group=64)
            dump(b"abc", width=1, group=1)


    class Parse(unittest.TestCase):
        def test_simple(self):
            self.assertEqual(parse_dump("000000  41 42  43 44  |ABCD|\n000004  45 46         |EF|\n000006"), b"ABCDEF")

        def test_grouping_is_free_form(self):
            self.assertEqual(parse_dump("000000  41    42 43  44  |ABCD|\n000004"), b"ABCD")
            self.assertEqual(parse_dump("000000  41 42 43 44|ABCD|\n000004"), b"ABCD")
            with self.assertRaises(ValueError):
                parse_dump("000000  41424344  |ABCD|\n000004")

        def test_blank_lines_and_crlf(self):
            text = "\n000000  41 42  |AB|\r\n\r\n\n000002\n\n"
            self.assertEqual(parse_dump(text), b"AB")

        def test_base_offset_and_empty(self):
            self.assertEqual(parse_dump("0001f0  41 42  |AB|\n0001f2"), b"AB")
            self.assertEqual(parse_dump("000000"), b"")
            self.assertEqual(parse_dump("00abcd"), b"")

        def test_repeat_lines(self):
            text = "000000  00 00  00 00  |....|\n*3\n000010"
            self.assertEqual(parse_dump(text), b"\x00" * 16)
            text = "000000  01 02  |..|\n*1\n000004"
            self.assertEqual(parse_dump(text), b"\x01\x02\x01\x02")
            text = "000000  01 02  |..|\n*2\n000006\n"
            self.assertEqual(parse_dump(text), b"\x01\x02" * 3)

        def test_ascii_column_may_contain_bars(self):
            self.assertEqual(parse_dump("000000  7c 7c 41  |||A|\n000003"), b"||A")
            self.assertEqual(parse_dump("000000  7c  |||\n000001"), b"|")

        def test_errors_missing_or_extra(self):
            for text in ("", "\n\n", "000000  41 42  |AB|", "000000  41 42  |AB|\n000002\n000002", "000000  41 42  |AB|\n000002\n000000  41  |A|",
                         "000000  41 42  |AB|\n000002\n*1"):
                with self.assertRaises(ValueError, msg=repr(text)):
                    parse_dump(text)

        def test_errors_offsets(self):
            for text in ("000000  41 42  |AB|\n000003", "000000  41 42  |AB|\n000004  43 44  |CD|\n000006", "000000  41 42  |AB|\n000001  43 44  |CD|\n000004",
                         "000010  41 42  |AB|\n000010"):
                with self.assertRaises(ValueError, msg=repr(text)):
                    parse_dump(text)

        def test_errors_row_shapes(self):
            for text in (
                "000000  41 42 43 44  |ABCD|\n000004  45 46  |EF|\n000006  47 48  |GH|\n000008",
                "000000  41 42  |AB|\n000002  43 44 45  |CDE|\n000005",
                "000000  41 42  |AB|\n000002  43  |C|\n*1\n000005",
                "000000  41 42  |ABC|\n000002",
                "000000  41 42  |A|\n000002",
                "000000  41 4  |A|\n000002",
                "000000  41 xx  |A.|\n000002",
                "000000  414  |A|\n000002",
                "000000    |\n000000",
                "000000    ||\n000000",
                "00000  41  |A|\n000001",
                "000000 41  |A|\n000001",
                "000000  41  A\n000001",
                "000000  41  |A|\n000001 extra",
                "000000  41  |A|\n*0\n000002",
                "*1\n000000",
                "000000  41  |A|\n*x\n000002",
                "0000000g  41  |A|\n000001",
                "000000  4A  |J|\n000001",
            ):
                with self.assertRaises(ValueError, msg=repr(text)):
                    parse_dump(text)

        def test_uppercase_hex_is_not_accepted(self):
            with self.assertRaises(ValueError):
                parse_dump("000000  4A  |J|\n000001")
            with self.assertRaises(ValueError):
                parse_dump("0000AB  41  |A|\n0000AC")

        def test_end_offset_with_longer_digits(self):
            self.assertEqual(parse_dump("0fffff  41  |A|\n100000"), b"A")
            self.assertEqual(parse_dump("0fffff  41  |A|\n100000"), b"A")


    class RoundTrip(unittest.TestCase):
        def test_fixed_samples(self):
            samples = [b"", b"A", bytes(range(256)), b"\x00" * 100, b"ab" * 50, b"\xff" * 33, bytes(range(5)) * 20, b"hello world, this is a hex dump"]
            for data in samples:
                for width, group in ((16, 4), (8, 2), (4, 4), (1, 1), (7, 3), (32, 8), (64, 64)):
                    for base in (0, 0xf0, 0xffff0):
                        text = dump(data, width=width, group=group, base=base)
                        self.assertEqual(parse_dump(text), data, (data[:6], width, group, base))

        def test_random(self):
            rng = random.Random(11)
            for _ in range(40):
                n = rng.randint(0, 120)
                pool = rng.choice([[0], [0, 1], list(range(256)), [65, 66, 0x7c]])
                data = bytes(rng.choice(pool) for _ in range(n))
                width = rng.randint(1, 12)
                group = rng.randint(1, width)
                self.assertEqual(parse_dump(dump(data, width=width, group=group)), data)


    if __name__ == "__main__":
        unittest.main()
''')

HD = Lib(
    name="hexdump", lang="python", title="the hex dump tool (`hexdump.py`)",
    blurb="The firmware team saves binary blobs as text dumps and reads them back with this module.",
    files={"hexdump.py": HD_SRC, "README.md": HD_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": HD_VISIBLE},
    hidden_tests={"tests/test_full.py": HD_HIDDEN},
    mutate=["hexdump.py"], difficulty=3, tags=["binary", "formats"],
    probes=[
        'dump(b"ABCDEFGH", width=4, group=2)',
        'dump(b"ABCDEF", width=4, group=2)',
        'dump(bytes([0x1f, 0x20, 0x7e, 0x7f, 0x80]), width=5, group=5)',
        'dump(b"\\x00" * 12, width=4, group=2)',
        'dump(b"\\x00" * 8, width=4, group=2)',
        'dump(b"ABCD" + b"xxxx" * 4 + b"EFGH", width=4, group=2)',
        'dump(b"AB", width=1, group=1, base=0xfffff)',
        'parse_dump(dump(bytes(range(40)), width=7, group=3, base=0x10))',
        'parse_dump("000000  01 02  |..|\\n*2\\n000006")',
        'dump(b"abc", width=4, group=3)',
    ],
    probe_import="from hexdump import *",
)


LIBS = [HF, IC, HD]
register_libs(LIBS, n=10)
