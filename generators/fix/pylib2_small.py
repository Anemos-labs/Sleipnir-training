"""Text-format libraries (python), batch: small codecs and log folding."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# idcodec: base-32 ticket codes with a check character
# ======================================================================================================================

IDC_README = dd(r'''
    # idcodec

    The helpdesk prints ticket numbers as short base-32 codes that are easy to read over the phone. One module, `idcodec.py`.

    ## Alphabet
    `ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"`: 32 symbols, value 0 for `A` up to value 31 for `9` (no `I`, `O`, `0` or `1`).

    ## `encode_int(n, width=1) -> str`
    `n` (an `int`, at least 0, else `ValueError`) written big-endian in base 32 with the symbols above (`0` is `"A"`, `31` is `"9"`, `32` is `"BA"`), left-padded
    with `A` to at least `width` symbols (never truncated). `width` below 1 is a `ValueError`.

    ## `decode_int(text) -> int`
    The inverse: letters may be lower case, spaces and `-` are ignored anywhere. At least one symbol must remain and every one must be in the alphabet, else
    `ValueError`. Leading `A`s are zeros.

    ## `check_char(body) -> str`
    The check symbol of a code body (a non-empty string of alphabet symbols; case-insensitive, spaces and `-` ignored; otherwise `ValueError`):
    with `v1..vk` the values of the symbols from left to right, the check value is `(v1*1 + v2*2 + ... + vk*k) mod 32` and the check symbol is the alphabet
    symbol with that value.

    ## `format_code(n, width=6, group=4) -> str`
    `body = encode_int(n, width)`, the code is `body + check_char(body)`, written in groups of `group` symbols from the left separated by `-` (the last group
    may be shorter). `group` below 1 is a `ValueError`.

    ## `parse_code(text) -> int`
    Accepts what `format_code` writes (any grouping, any case, spaces or `-` anywhere). At least two symbols are needed (body and check); the last symbol must
    be the check symbol of the rest, otherwise `ValueError("bad check character")`. Returns the number.
''')

IDC_SRC = dd(r'''
    """Base-32 ticket codes."""

    ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    _VALUE = {c: i for i, c in enumerate(ALPHABET)}


    def _symbols(text):
        out = text.upper().replace("-", "").replace(" ", "")
        for c in out:
            if c not in _VALUE:
                raise ValueError("bad symbol: %r" % c)
        return out


    def encode_int(n, width=1):
        if n < 0:
            raise ValueError("n must not be negative")
        if width < 1:
            raise ValueError("width must be at least 1")
        digits = []
        while n:
            n, r = divmod(n, 32)
            digits.append(ALPHABET[r])
        text = "".join(reversed(digits))
        return text.rjust(width, ALPHABET[0])


    def decode_int(text):
        syms = _symbols(text)
        if not syms:
            raise ValueError("empty code")
        n = 0
        for c in syms:
            n = n * 32 + _VALUE[c]
        return n


    def check_char(body):
        syms = _symbols(body)
        if not syms:
            raise ValueError("empty body")
        total = sum(_VALUE[c] * i for i, c in enumerate(syms, 1))
        return ALPHABET[total % 32]


    def format_code(n, width=6, group=4):
        if group < 1:
            raise ValueError("group must be at least 1")
        body = encode_int(n, width)
        code = body + check_char(body)
        return "-".join(code[i:i + group] for i in range(0, len(code), group))


    def parse_code(text):
        syms = _symbols(text)
        if len(syms) < 2:
            raise ValueError("code too short")
        if check_char(syms[:-1]) != syms[-1]:
            raise ValueError("bad check character")
        return decode_int(syms[:-1])
''')

IDC_VISIBLE = dd(r'''
    import unittest

    from idcodec import ALPHABET, decode_int, encode_int, format_code, parse_code


    class BasicTests(unittest.TestCase):
        def test_encode(self):
            self.assertEqual(encode_int(32), "BA")

        def test_decode(self):
            self.assertEqual(decode_int("ba"), 32)

        def test_round_trip(self):
            self.assertEqual(parse_code(format_code(123456)), 123456)


    if __name__ == "__main__":
        unittest.main()
''')

IDC_HIDDEN = dd(r'''
    import unittest

    from idcodec import ALPHABET, check_char, decode_int, encode_int, format_code, parse_code


    class Encode(unittest.TestCase):
        def test_alphabet(self):
            self.assertEqual(ALPHABET, "ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
            self.assertEqual(len(set(ALPHABET)), 32)

        def test_small_values(self):
            self.assertEqual(encode_int(0), "A")
            self.assertEqual(encode_int(1), "B")
            self.assertEqual(encode_int(8), "J")
            self.assertEqual(encode_int(31), "9")
            self.assertEqual(encode_int(32), "BA")
            self.assertEqual(encode_int(33), "BB")
            self.assertEqual(encode_int(1023), "99")
            self.assertEqual(encode_int(1024), "BAA")

        def test_larger_values(self):
            self.assertEqual(encode_int(1000), "9J")
            self.assertEqual(encode_int(1000000), "8SUA")
            self.assertEqual(encode_int(32 ** 5), "BAAAAA")
            self.assertEqual(encode_int(32 ** 5 - 1), "99999")

        def test_each_symbol_value(self):
            for i, c in enumerate(ALPHABET):
                self.assertEqual(encode_int(i), c)

        def test_width_pads_with_a(self):
            self.assertEqual(encode_int(0, 4), "AAAA")
            self.assertEqual(encode_int(5, 3), "AAF")
            self.assertEqual(encode_int(32, 2), "BA")
            self.assertEqual(encode_int(32, 1), "BA")
            self.assertEqual(encode_int(1000000, 3), "8SUA")
            self.assertEqual(encode_int(1000000, 6), "AA8SUA")

        def test_errors(self):
            with self.assertRaises(ValueError):
                encode_int(-1)
            for w in (0, -3):
                with self.assertRaises(ValueError):
                    encode_int(1, w)


    class Decode(unittest.TestCase):
        def test_values(self):
            self.assertEqual(decode_int("A"), 0)
            self.assertEqual(decode_int("BA"), 32)
            self.assertEqual(decode_int("9"), 31)
            self.assertEqual(decode_int("8SUA"), 1000000)
            self.assertEqual(decode_int("AA8SUA"), 1000000)
            self.assertEqual(decode_int("AAAA"), 0)

        def test_case_and_separators(self):
            self.assertEqual(decode_int("8sua"), 1000000)
            self.assertEqual(decode_int("8S-UA"), 1000000)
            self.assertEqual(decode_int(" 8 s - u a "), 1000000)
            self.assertEqual(decode_int("-A-"), 0)

        def test_errors(self):
            for bad in ("", " ", "-", "- -", "I", "O", "0", "1", "AB1", "A_B", "a.b", "Ä", "BAD!", "ab\n"):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    decode_int(bad)

        def test_round_trip(self):
            for n in (0, 1, 31, 32, 1023, 1024, 999999, 32 ** 6 + 17, 2 ** 40 + 5):
                self.assertEqual(decode_int(encode_int(n)), n)
                self.assertEqual(decode_int(encode_int(n, 12)), n)


    class Check(unittest.TestCase):
        def test_values(self):
            self.assertEqual(check_char("A"), "A")
            self.assertEqual(check_char("B"), "B")
            self.assertEqual(check_char("9"), "9")
            self.assertEqual(check_char("BA"), "B")
            self.assertEqual(check_char("9J"), "R")
            self.assertEqual(check_char("AB"), "C")
            self.assertEqual(check_char("BB"), "D")
            self.assertEqual(check_char("8SUA"), ALPHABET[(30 * 1 + 16 * 2 + 18 * 3 + 0 * 4) % 32])

        def test_position_weights_start_at_one_from_the_left(self):
            self.assertEqual(check_char("AAAB"), ALPHABET[4])
            self.assertEqual(check_char("BAAA"), ALPHABET[1])
            self.assertEqual(check_char("ABAA"), ALPHABET[2])

        def test_wraps_mod_32(self):
            self.assertEqual(check_char("99"), ALPHABET[(31 * 1 + 31 * 2) % 32])
            self.assertEqual(check_char("9999"), ALPHABET[(31 * 10) % 32])
            self.assertEqual(check_char("B" * 32), ALPHABET[(32 * 33 // 2) % 32])

        def test_input_forms(self):
            self.assertEqual(check_char("9j"), check_char("9J"))
            self.assertEqual(check_char("9-J"), check_char("9J"))
            self.assertEqual(check_char(" 9 J "), check_char("9J"))

        def test_detects_adjacent_swaps(self):
            for a in range(32):
                for b in range(32):
                    if a != b:
                        x = ALPHABET[a] + ALPHABET[b] + "A"
                        y = ALPHABET[b] + ALPHABET[a] + "A"
                        self.assertNotEqual(check_char(x), check_char(y))

        def test_errors(self):
            for bad in ("", "-", "I", "A0", "a b!"):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    check_char(bad)


    class Codes(unittest.TestCase):
        def test_format(self):
            body = encode_int(1000000, 6)
            self.assertEqual(body, "AA8SUA")
            full = body + check_char(body)
            self.assertEqual(format_code(1000000), "%s-%s" % (full[:4], full[4:]))
            self.assertEqual(len(format_code(1000000)), 8)
            self.assertEqual(format_code(1000000, width=6, group=7), full)
            self.assertEqual(format_code(1000000, width=6, group=3), "-".join([full[0:3], full[3:6], full[6:]]))
            self.assertEqual(format_code(1000000, width=6, group=1), "-".join(full))

        def test_format_exact(self):
            self.assertEqual(format_code(0, width=3, group=2), "AA-AA")
            self.assertEqual(format_code(1, width=3, group=2), "AA-BD")
            self.assertEqual(format_code(31, width=2, group=4), "A9" + check_char("A9"))
            self.assertEqual(format_code(32, width=1, group=2), "BA-B")

        def test_width_is_a_minimum(self):
            code = format_code(32 ** 7, width=3, group=100)
            self.assertEqual(len(code), 9)
            self.assertEqual(parse_code(code), 32 ** 7)

        def test_group_errors(self):
            for g in (0, -1):
                with self.assertRaises(ValueError):
                    format_code(5, group=g)

        def test_parse(self):
            for n in (0, 1, 31, 32, 12345, 999999, 32 ** 6, 2 ** 33):
                code = format_code(n)
                self.assertEqual(parse_code(code), n)
                self.assertEqual(parse_code(code.lower()), n)
                self.assertEqual(parse_code(code.replace("-", "")), n)
                self.assertEqual(parse_code(" " + code.replace("-", " - ") + " "), n)

        def test_parse_any_grouping(self):
            body = encode_int(777, 4)
            code = body + check_char(body)
            self.assertEqual(parse_code("-".join(code)), 777)
            self.assertEqual(parse_code(code), 777)

        def test_bad_check_is_rejected(self):
            code = format_code(12345).replace("-", "")
            good = code[-1]
            for c in ALPHABET:
                if c != good:
                    with self.assertRaises(ValueError, msg=c) as cm:
                        parse_code(code[:-1] + c)
                    self.assertIn("check", str(cm.exception))

        def test_single_symbol_errors_are_mostly_caught(self):
            code = format_code(424242).replace("-", "")
            caught = 0
            total = 0
            for i in range(len(code)):
                for c in ALPHABET:
                    if c != code[i]:
                        total += 1
                        try:
                            parse_code(code[:i] + c + code[i + 1:])
                        except ValueError:
                            caught += 1
            self.assertGreater(caught, total * 0.9)

        def test_swapped_neighbours_are_caught(self):
            code = format_code(424242).replace("-", "")
            for i in range(len(code) - 2):
                if code[i] != code[i + 1]:
                    swapped = code[:i] + code[i + 1] + code[i] + code[i + 2:]
                    with self.assertRaises(ValueError):
                        parse_code(swapped)

        def test_too_short(self):
            for bad in ("", "A", "-A-", " "):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    parse_code(bad)
            self.assertEqual(parse_code("AA"), 0)

        def test_bad_symbols(self):
            for bad in ("AI", "A0A", "O", "AB-1C"):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    parse_code(bad)


    if __name__ == "__main__":
        unittest.main()
''')

IDC = Lib(
    name="idcodec", lang="python", title="the ticket code codec (`idcodec.py`)",
    blurb="The helpdesk prints and reads back short base-32 ticket codes with this module.",
    files={"idcodec.py": IDC_SRC, "README.md": IDC_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": IDC_VISIBLE},
    hidden_tests={"tests/test_full.py": IDC_HIDDEN},
    mutate=["idcodec.py"], difficulty=1, tags=["codes", "encoding"],
    probes=[
        'encode_int(1000000)',
        'encode_int(32 ** 5)',
        'encode_int(5, 3)',
        'decode_int("8s-ua")',
        'check_char("9J")',
        'check_char("9999")',
        'format_code(1000000)',
        'format_code(7, width=3, group=2)',
        'parse_code(format_code(12345).lower())',
        'parse_code("AA")',
    ],
    probe_import="from idcodec import *",
)


# ======================================================================================================================
# logfold: collapsing runs of repetitive log lines
# ======================================================================================================================

LF_README = dd(r'''
    # logfold

    Shortens noisy logs for the incident channel. One module, `logfold.py`.

    ## `template(line) -> str`
    The comparison form of a line: trailing whitespace removed, then every maximal run of ASCII digits replaced by a single `#`
    (`"retry 3 after 250 ms"` becomes `"retry # after # ms"`).

    ## `fold_lines(lines, min_run=3) -> list[str]`
    A *run* is a maximal sequence of consecutive lines with the same `template`. Runs shorter than `min_run` are copied unchanged (all their lines).
    A run of at least `min_run` lines is replaced by:
    * when all its lines are exactly equal after removing trailing whitespace: the first line (trailing whitespace removed) followed by ` (x` + the run length
      + `)`;
    * otherwise two lines: the first line of the run unchanged, and `  ... ` + (run length - 1) + ` more like it, last: ` + the last line of the run
      stripped of surrounding whitespace.
    `min_run` below 2 is a `ValueError`. Blank lines are lines like any other (their template is the empty string). The input is not modified.

    ## `fold_text(text, min_run=3) -> str`
    Splits `text` at `\n` (a final empty piece after a trailing `\n` is not a line), folds the lines and joins them with `\n`, adding a final `\n` exactly when
    the text ended with one. `"" ` stays `""`.

    ## `stats(lines, min_run=3) -> tuple`
    `(lines in, lines out, runs folded)` for `fold_lines(lines, min_run)`.
''')

LF_SRC = dd(r'''
    """Collapse repetitive log lines."""
    import re


    def template(line):
        return re.sub(r"[0-9]+", "#", line.rstrip())


    def _runs(lines):
        runs = []
        for line in lines:
            t = template(line)
            if runs and runs[-1][0] == t:
                runs[-1][1].append(line)
            else:
                runs.append((t, [line]))
        return runs


    def fold_lines(lines, min_run=3):
        if min_run < 2:
            raise ValueError("min_run must be at least 2")
        out = []
        for _, run in _runs(lines):
            if len(run) < min_run:
                out.extend(run)
            elif all(x.rstrip() == run[0].rstrip() for x in run):
                out.append("%s (x%d)" % (run[0].rstrip(), len(run)))
            else:
                out.append(run[0])
                out.append("  ... %d more like it, last: %s" % (len(run) - 1, run[-1].strip()))
        return out


    def fold_text(text, min_run=3):
        parts = text.split("\n")
        ended = parts[-1] == ""
        if ended:
            parts.pop()
        if not parts:
            return ""
        return "\n".join(fold_lines(parts, min_run)) + ("\n" if ended else "")


    def stats(lines, min_run=3):
        folded = sum(1 for _, run in _runs(lines) if len(run) >= min_run)
        return (len(lines), len(fold_lines(lines, min_run)), folded)
''')

LF_VISIBLE = dd(r'''
    import unittest

    from logfold import fold_lines, fold_text, template


    class BasicTests(unittest.TestCase):
        def test_template(self):
            self.assertEqual(template("retry 3 after 250 ms  "), "retry # after # ms")

        def test_identical(self):
            self.assertEqual(fold_lines(["x"] * 4), ["x (x4)"])

        def test_text(self):
            self.assertEqual(fold_text("a\nb\n"), "a\nb\n")


    if __name__ == "__main__":
        unittest.main()
''')

LF_HIDDEN = dd(r'''
    import unittest

    from logfold import fold_lines, fold_text, stats, template


    class Template(unittest.TestCase):
        def test_digit_runs(self):
            self.assertEqual(template("retry 3 after 250 ms"), "retry # after # ms")
            self.assertEqual(template("a1b22c333"), "a#b#c#")
            self.assertEqual(template("12:30:45 up"), "#:#:# up")
            self.assertEqual(template("1.5"), "#.#")
            self.assertEqual(template("no digits"), "no digits")
            self.assertEqual(template(""), "")
            self.assertEqual(template("007"), "#")

        def test_trailing_whitespace_only(self):
            self.assertEqual(template("x 1  \t"), "x #")
            self.assertEqual(template("  x 1"), "  x #")
            self.assertEqual(template("   "), "")

        def test_unicode_digits_are_not_digits_here(self):
            self.assertEqual(template("a٣"), "a٣")


    class Fold(unittest.TestCase):
        def test_identical_runs(self):
            self.assertEqual(fold_lines(["x"] * 3), ["x (x3)"])
            self.assertEqual(fold_lines(["x"] * 10), ["x (x10)"])
            self.assertEqual(fold_lines(["disk full"] * 4 + ["ok"]), ["disk full (x4)", "ok"])

        def test_short_runs_are_kept(self):
            self.assertEqual(fold_lines(["x", "x"]), ["x", "x"])
            self.assertEqual(fold_lines(["x"]), ["x"])
            self.assertEqual(fold_lines([]), [])
            self.assertEqual(fold_lines(["a", "a", "b", "b"]), ["a", "a", "b", "b"])

        def test_similar_runs(self):
            lines = ["retry 1 after 100 ms", "retry 2 after 200 ms", "retry 3 after 400 ms"]
            self.assertEqual(fold_lines(lines), ["retry 1 after 100 ms", "  ... 2 more like it, last: retry 3 after 400 ms"])
            lines = ["t=%d ping" % i for i in range(1, 8)]
            self.assertEqual(fold_lines(lines), ["t=1 ping", "  ... 6 more like it, last: t=7 ping"])

        def test_last_line_is_stripped_first_is_not(self):
            lines = ["  job 1 done  ", "  job 2 done", "  job 3 done \t"]
            self.assertEqual(fold_lines(lines), ["  job 1 done  ", "  ... 2 more like it, last: job 3 done"])

        def test_identical_after_trailing_whitespace(self):
            self.assertEqual(fold_lines(["x 1  ", "x 1", "x 1\t"]), ["x 1 (x3)"])
            self.assertEqual(fold_lines(["  x 1  ", "  x 1", "  x 1  "]), ["  x 1 (x3)"])

        def test_leading_whitespace_matters_for_templates(self):
            lines = ["x 1", " x 2", "x 3"]
            self.assertEqual(fold_lines(lines), lines)

        def test_min_run(self):
            lines = ["x"] * 4
            self.assertEqual(fold_lines(lines, min_run=2), ["x (x4)"])
            self.assertEqual(fold_lines(lines, min_run=4), ["x (x4)"])
            self.assertEqual(fold_lines(lines, min_run=5), lines)
            self.assertEqual(fold_lines(["a 1", "a 2"], min_run=2), ["a 1", "  ... 1 more like it, last: a 2"])
            self.assertEqual(fold_lines(["a 1", "a 2", "a 3"], min_run=4), ["a 1", "a 2", "a 3"])

        def test_bad_min_run(self):
            for n in (1, 0, -3):
                with self.assertRaises(ValueError):
                    fold_lines(["x"], min_run=n)

        def test_runs_are_consecutive_only(self):
            lines = ["a 1", "a 2", "b", "a 3", "a 4", "a 5"]
            self.assertEqual(fold_lines(lines), ["a 1", "a 2", "b", "a 3", "  ... 2 more like it, last: a 5"])

        def test_different_templates_split_runs(self):
            lines = ["x 1", "x 2", "x 3", "y 4", "y 5", "y 6", "y 7"]
            self.assertEqual(fold_lines(lines), ["x 1", "  ... 2 more like it, last: x 3", "y 4", "  ... 3 more like it, last: y 7"])

        def test_mixed_exact_and_similar(self):
            lines = ["x 1", "x 1", "x 2"]
            self.assertEqual(fold_lines(lines), ["x 1", "  ... 2 more like it, last: x 2"])
            lines = ["x 1", "x 1", "x 1", "x 2", "x 2", "x 2"]
            self.assertEqual(fold_lines(lines), ["x 1", "  ... 5 more like it, last: x 2"])

        def test_blank_lines(self):
            self.assertEqual(fold_lines(["", "", "", "a"]), [" (x3)", "a"])
            self.assertEqual(fold_lines(["", "  ", "\t"]), [" (x3)"])
            self.assertEqual(fold_lines(["", ""]), ["", ""])

        def test_input_not_modified(self):
            lines = ["x"] * 3
            fold_lines(lines)
            self.assertEqual(lines, ["x", "x", "x"])

        def test_longer_digit_runs_are_one_number(self):
            lines = ["id 5", "id 50", "id 500"]
            self.assertEqual(fold_lines(lines), ["id 5", "  ... 2 more like it, last: id 500"])
            lines = ["id 5", "id 5 6", "id 7"]
            self.assertEqual(fold_lines(lines), lines)


    class Text(unittest.TestCase):
        def test_trailing_newline_preserved(self):
            self.assertEqual(fold_text("a\nb\n"), "a\nb\n")
            self.assertEqual(fold_text("a\nb"), "a\nb")
            self.assertEqual(fold_text("x\nx\nx\n"), "x (x3)\n")
            self.assertEqual(fold_text("x\nx\nx"), "x (x3)")

        def test_empty_and_blank(self):
            self.assertEqual(fold_text(""), "")
            self.assertEqual(fold_text("\n"), "\n")
            self.assertEqual(fold_text("\n\n\n\n"), " (x4)\n")
            self.assertEqual(fold_text("a\n\n"), "a\n\n")

        def test_min_run_passthrough(self):
            self.assertEqual(fold_text("x\nx\n", min_run=2), "x (x2)\n")
            self.assertEqual(fold_text("x\nx\n"), "x\nx\n")

        def test_crlf_is_not_special(self):
            self.assertEqual(fold_text("a 1\r\na 2\r\na 3\r\n"), "a 1\r\n  ... 2 more like it, last: a 3\n")


    class Stats(unittest.TestCase):
        def test_counts(self):
            lines = ["x"] * 5 + ["a 1", "a 2", "a 3"] + ["y", "y"]
            self.assertEqual(stats(lines), (10, 5, 2))
            self.assertEqual(stats([]), (0, 0, 0))
            self.assertEqual(stats(["a", "b"]), (2, 2, 0))
            self.assertEqual(stats(["a 1", "a 2", "a 3"], min_run=2), (3, 2, 1))
            self.assertEqual(stats(["x"] * 3), (3, 1, 1))


    if __name__ == "__main__":
        unittest.main()
''')

LF = Lib(
    name="logfold", lang="python", title="the log folder (`logfold.py`)",
    blurb="The incident channel bot shortens noisy logs with this module before posting them.",
    files={"logfold.py": LF_SRC, "README.md": LF_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": LF_VISIBLE},
    hidden_tests={"tests/test_full.py": LF_HIDDEN},
    mutate=["logfold.py"], difficulty=2, tags=["logs", "text"],
    probes=[
        'template("retry 3 after 250 ms  ")',
        'fold_lines(["disk full"] * 4 + ["ok"])',
        'fold_lines(["retry 1 after 100 ms", "retry 2 after 200 ms", "retry 3 after 400 ms"])',
        'fold_lines(["  job 1 done  ", "job 2 done", "\\tjob 3 done \\t"])',
        'fold_lines(["x 1  ", "x 1", "x 1\\t"])',
        'fold_lines(["a 1", "a 2", "b", "a 3", "a 4", "a 5"])',
        'fold_lines(["x"] * 4, min_run=5)',
        'fold_text("x\\nx\\nx\\n")',
        'fold_text("\\n\\n\\n\\n")',
        'stats(["x"] * 5 + ["a 1", "a 2", "a 3"] + ["y", "y"])',
    ],
    probe_import="from logfold import *",
)


LIBS = [IDC, LF]
register_libs(LIBS, n=10)
