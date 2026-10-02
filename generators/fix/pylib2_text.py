"""Text-format libraries (python), batch: whitespace helpers."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# tabstops: tab expansion and indentation re-tabbing
# ======================================================================================================================

TS_README = dd(r'''
    # tabstops

    Tab handling for the code-formatting tool. One module, `tabstops.py`. A *tab size* is a positive integer (`ValueError` otherwise); a tab advances to
    the next multiple of the size. Columns count characters (every character is one column); a `\n` starts a new line at column 0.

    ## `expand_tabs(text, size=8) -> str`
    Replaces every `\t` by the spaces that reach the next tab stop: a tab at column `c` becomes `size - c % size` spaces (a whole `size` when `c` is a multiple).
    Other characters are unchanged.

    ## `column_of(line, index, size=8) -> int`
    The column at which `line[index]` starts when tabs are expanded, that is the length of `expand_tabs(line[:index], size)`. `index` may be `len(line)`;
    outside `0..len(line)` is an `IndexError`.

    ## `indent_width(line, size=8) -> int`
    The width in columns of the leading whitespace of `line` (a run of spaces and tabs, tabs expanded). A line of only blanks has its whole length as indent.

    ## `indent_with_tabs(line, size=8) -> str`
    Rewrites the leading whitespace of `line` as tabs followed by spaces: `width // size` tabs and `width % size` spaces, where `width` is `indent_width(line, size)`.
    The rest of the line is unchanged (tabs and spaces inside it stay as they are).

    ## `retab(text, old, new) -> str`
    For every line of `text` (split on `\n`; line breaks kept): the leading whitespace, measured with tab size `old`, is rewritten for tab size `new` as in
    `indent_with_tabs(..., new)`, and every tab in the rest of the line is expanded to spaces with tab size `old` (counting columns from the start of the line,
    where the new indentation occupies the same width as the old one).
''')

TS_SRC = dd(r'''
    """Tab expansion."""


    def _check(size):
        if size < 1:
            raise ValueError("tab size must be at least 1")


    def expand_tabs(text, size=8):
        _check(size)
        out = []
        col = 0
        for ch in text:
            if ch == "\t":
                n = size - col % size
                out.append(" " * n)
                col += n
            elif ch == "\n":
                out.append(ch)
                col = 0
            else:
                out.append(ch)
                col += 1
        return "".join(out)


    def column_of(line, index, size=8):
        if not 0 <= index <= len(line):
            raise IndexError("index out of range")
        return len(expand_tabs(line[:index], size))


    def _split_indent(line):
        n = len(line) - len(line.lstrip(" \t"))
        return line[:n], line[n:]


    def indent_width(line, size=8):
        lead, _ = _split_indent(line)
        return len(expand_tabs(lead, size))


    def indent_with_tabs(line, size=8):
        lead, rest = _split_indent(line)
        width = len(expand_tabs(lead, size))
        return "\t" * (width // size) + " " * (width % size) + rest


    def retab(text, old, new):
        _check(old)
        _check(new)
        out = []
        for piece in text.split("\n"):
            lead, rest = _split_indent(piece)
            width = len(expand_tabs(lead, old))
            body = expand_tabs(" " * width + rest, old)[width:]
            out.append("\t" * (width // new) + " " * (width % new) + body)
        return "\n".join(out)
''')

TS_VISIBLE = dd(r'''
    import unittest

    from tabstops import column_of, expand_tabs, indent_width, indent_with_tabs, retab


    class BasicTests(unittest.TestCase):
        def test_expand(self):
            self.assertEqual(expand_tabs("a\tb", 4), "a   b")

        def test_column(self):
            self.assertEqual(column_of("\tx", 1, 4), 4)

        def test_indent(self):
            self.assertEqual(indent_width("    x", 4), 4)
            self.assertEqual(indent_with_tabs("    x", 4), "\tx")

        def test_retab(self):
            self.assertEqual(retab("\tx", 4, 2), "\t\tx")


    if __name__ == "__main__":
        unittest.main()
''')

TS_HIDDEN = dd(r'''
    import unittest

    from tabstops import column_of, expand_tabs, indent_width, indent_with_tabs, retab


    class Expand(unittest.TestCase):
        def test_stops(self):
            self.assertEqual(expand_tabs("\t", 4), "    ")
            self.assertEqual(expand_tabs("a\t", 4), "a   ")
            self.assertEqual(expand_tabs("abc\t", 4), "abc ")
            self.assertEqual(expand_tabs("abcd\t", 4), "abcd    ")
            self.assertEqual(expand_tabs("abcde\t", 4), "abcde   ")
            self.assertEqual(expand_tabs("a\tb\tc", 4), "a   b   c")
            self.assertEqual(expand_tabs("\t\t", 4), "        ")
            self.assertEqual(expand_tabs("ab\t", 8), "ab      ")

        def test_default_size_is_eight(self):
            self.assertEqual(expand_tabs("a\tb"), "a       b")
            self.assertEqual(expand_tabs("1234567\tx"), "1234567 x")
            self.assertEqual(expand_tabs("12345678\tx"), "12345678        x")

        def test_size_one(self):
            self.assertEqual(expand_tabs("a\tb\t", 1), "a b ")

        def test_newline_resets_column(self):
            self.assertEqual(expand_tabs("ab\n\tc", 4), "ab\n    c")
            self.assertEqual(expand_tabs("abc\n\tx\n\t", 4), "abc\n    x\n    ")
            self.assertEqual(expand_tabs("a\n\n\tb", 2), "a\n\n  b")

        def test_no_tabs_and_empty(self):
            self.assertEqual(expand_tabs("plain text", 4), "plain text")
            self.assertEqual(expand_tabs("", 4), "")

        def test_carriage_return_is_an_ordinary_character(self):
            self.assertEqual(expand_tabs("a\r\tb", 4), "a\r  b")

        def test_bad_size(self):
            for size in (0, -1):
                with self.assertRaises(ValueError):
                    expand_tabs("x", size)


    class Column(unittest.TestCase):
        def test_values(self):
            self.assertEqual(column_of("abc", 0, 4), 0)
            self.assertEqual(column_of("abc", 2, 4), 2)
            self.assertEqual(column_of("abc", 3, 4), 3)
            self.assertEqual(column_of("\tx", 1, 4), 4)
            self.assertEqual(column_of("a\tx", 2, 4), 4)
            self.assertEqual(column_of("abcd\tx", 5, 4), 8)
            self.assertEqual(column_of("\t\tx", 2, 4), 8)
            self.assertEqual(column_of("a\tb\tc", 3, 4), 5)
            self.assertEqual(column_of("a\tb\tc", 4, 4), 8)
            self.assertEqual(column_of("a\tb\tc", 4, 8), 16)
            self.assertEqual(column_of("\tx", 0, 4), 0)

        def test_default_size(self):
            self.assertEqual(column_of("\tx", 1), 8)

        def test_out_of_range(self):
            for idx in (-1, 4, 10):
                with self.assertRaises(IndexError):
                    column_of("abc", idx)
            self.assertEqual(column_of("", 0), 0)
            with self.assertRaises(IndexError):
                column_of("", 1)

        def test_bad_size(self):
            with self.assertRaises(ValueError):
                column_of("a", 0, 0)


    class Indent(unittest.TestCase):
        def test_width(self):
            self.assertEqual(indent_width("x", 4), 0)
            self.assertEqual(indent_width("    x", 4), 4)
            self.assertEqual(indent_width("\tx", 4), 4)
            self.assertEqual(indent_width("  \tx", 4), 4)
            self.assertEqual(indent_width("\t  x", 4), 6)
            self.assertEqual(indent_width("     \tx", 4), 8)
            self.assertEqual(indent_width("\t\tx", 4), 8)
            self.assertEqual(indent_width("   ", 4), 3)
            self.assertEqual(indent_width("\t", 4), 4)
            self.assertEqual(indent_width("", 4), 0)
            self.assertEqual(indent_width(" \t x\ty", 4), 5)

        def test_width_default(self):
            self.assertEqual(indent_width("\tx"), 8)
            self.assertEqual(indent_with_tabs("        x"), "\tx")
            self.assertEqual(indent_with_tabs("         x"), "\t x")
            self.assertEqual(indent_with_tabs("       x"), "       x")
            self.assertEqual(retab("\tx", 8, 4), "\t\tx")

        def test_with_tabs(self):
            self.assertEqual(indent_with_tabs("x", 4), "x")
            self.assertEqual(indent_with_tabs("    x", 4), "\tx")
            self.assertEqual(indent_with_tabs("      x", 4), "\t  x")
            self.assertEqual(indent_with_tabs("          x", 4), "\t\t  x")
            self.assertEqual(indent_with_tabs("  \tx", 4), "\tx")
            self.assertEqual(indent_with_tabs("\t  x", 4), "\t  x")
            self.assertEqual(indent_with_tabs("   x", 4), "   x")
            self.assertEqual(indent_with_tabs("        x", 8), "\tx")
            self.assertEqual(indent_with_tabs("   ", 4), "   ")
            self.assertEqual(indent_with_tabs("", 4), "")

        def test_with_tabs_leaves_the_rest_alone(self):
            self.assertEqual(indent_with_tabs("    a\tb    c", 4), "\ta\tb    c")
            self.assertEqual(indent_with_tabs("    a  b", 2), "\t\ta  b")

        def test_bad_size(self):
            with self.assertRaises(ValueError):
                indent_with_tabs("x", 0)


    class Retab(unittest.TestCase):
        def test_indentation(self):
            self.assertEqual(retab("\tx", 4, 2), "\t\tx")
            self.assertEqual(retab("\t\tx", 4, 8), "\tx")
            self.assertEqual(retab("\tx", 8, 4), "\t\tx")
            self.assertEqual(retab("\t  x", 4, 2), "\t\t\tx")
            self.assertEqual(retab("    x", 4, 3), "\t x")
            self.assertEqual(retab("  x", 4, 4), "  x")
            self.assertEqual(retab("x", 4, 2), "x")

        def test_multiple_lines_and_endings(self):
            self.assertEqual(retab("\ta\n\t\tb\n", 4, 2), "\t\ta\n\t\t\t\tb\n")
            self.assertEqual(retab("a\n\nb", 4, 2), "a\n\nb")
            self.assertEqual(retab("\ta\r\n\tb\r\n", 4, 8), "    a\r\n    b\r\n")
            self.assertEqual(retab("", 4, 2), "")

        def test_inner_tabs_become_spaces_measured_with_old_size(self):
            self.assertEqual(retab("\ta\tb", 4, 2), "\t\ta   b")
            self.assertEqual(retab("a\tb", 4, 2), "a   b")
            self.assertEqual(retab("  a\tb", 4, 2), "\ta b")
            self.assertEqual(retab("\tab\tc", 8, 4), "\t\tab      c")

        def test_blank_lines_keep_their_width(self):
            self.assertEqual(retab("  \n\t\n", 4, 2), "\t\n\t\t\n")

        def test_bad_sizes(self):
            with self.assertRaises(ValueError):
                retab("x", 0, 4)
            with self.assertRaises(ValueError):
                retab("x", 4, 0)


    if __name__ == "__main__":
        unittest.main()
''')

TS = Lib(
    name="tabstops", lang="python", title="the tab helpers (`tabstops.py`)",
    blurb="The code-formatting tool expands tabs and re-indents files with this module.",
    files={"tabstops.py": TS_SRC, "README.md": TS_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": TS_VISIBLE},
    hidden_tests={"tests/test_full.py": TS_HIDDEN},
    mutate=["tabstops.py"], difficulty=1, tags=["whitespace", "text"],
    probes=[
        'expand_tabs("abcd\\tx", 4)',
        'expand_tabs("ab\\n\\tc", 4)',
        'column_of("a\\tb\\tc", 3, 4)',
        'indent_width("  \\tx", 4)',
        'indent_width("\\t  x", 4)',
        'indent_with_tabs("      x", 4)',
        'indent_with_tabs("    a\\tb    c", 4)',
        'retab("\\t  x", 4, 2)',
        'retab("\\ta\\tb", 4, 2)',
        'retab("  \\n\\t\\n", 4, 2)',
    ],
    probe_import="from tabstops import *",
)


# ======================================================================================================================
# lineends: line-ending detection and normalisation
# ======================================================================================================================

LE_README = dd(r'''
    # lineends

    Line-ending hygiene for the repository linter. One module, `lineends.py`. The recognised line endings are `"\r\n"` (CRLF), `"\n"` (LF) and a lone `"\r"` (CR);
    a `\r` directly followed by `\n` is always one CRLF.

    ## `count_endings(text) -> dict`
    `{"crlf": n, "lf": n, "cr": n}`: how many line endings of each kind the text contains.

    ## `detect(text) -> str`
    `"none"` if there is no line ending at all; `"crlf"`, `"lf"` or `"cr"` if all endings are of that one kind; `"mixed"` if there are several kinds.

    ## `dominant(text) -> str`
    The most frequent ending itself (`"\r\n"`, `"\n"` or `"\r"`). Ties go to `"\n"`, then `"\r\n"`, then `"\r"`. A text without line endings gives `"\n"`.

    ## `normalize(text, eol="\n") -> str`
    Every line ending replaced by `eol`, which must be one of the three endings (else `ValueError`). Everything else is unchanged.

    ## `count_lines(text) -> int`
    The number of lines: every line ending ends a line, and a last piece without ending counts as a line too. The empty text has 0 lines, `"\n"` has 1.

    ## `ensure_final_newline(text, eol="\n") -> str`
    Adds `eol` unless the text is empty or already ends with a line ending (`\n` or `\r`). `eol` is validated as in `normalize`.

    ## `strip_trailing(text) -> str`
    Removes spaces and tabs at the end of every line (before its line ending, or at the end of the text), keeping all line endings as they are.
''')

LE_SRC = dd(r'''
    """Line endings."""
    import re

    _END = re.compile(r"\r\n|\r|\n")
    _EOLS = ("\r\n", "\n", "\r")


    def _check(eol):
        if eol not in _EOLS:
            raise ValueError("eol must be CRLF, LF or CR")


    def count_endings(text):
        counts = {"crlf": 0, "lf": 0, "cr": 0}
        for m in _END.finditer(text):
            counts[{"\r\n": "crlf", "\n": "lf", "\r": "cr"}[m.group()]] += 1
        return counts


    def detect(text):
        used = [k for k, v in count_endings(text).items() if v]
        if not used:
            return "none"
        return used[0] if len(used) == 1 else "mixed"


    def dominant(text):
        counts = count_endings(text)
        best = "\n"
        best_n = counts["lf"]
        for eol, key in (("\r\n", "crlf"), ("\r", "cr")):
            if counts[key] > best_n:
                best, best_n = eol, counts[key]
        return best


    def normalize(text, eol="\n"):
        _check(eol)
        return _END.sub(lambda m: eol, text)


    def count_lines(text):
        n = len(_END.findall(text))
        if text and not text.endswith(("\n", "\r")):
            n += 1
        return n


    def ensure_final_newline(text, eol="\n"):
        _check(eol)
        if text and not text.endswith(("\n", "\r")):
            return text + eol
        return text


    def strip_trailing(text):
        return re.sub(r"[ \t]+(?=\r\n|\r|\n|\Z)", "", text)
''')

LE_VISIBLE = dd(r'''
    import unittest

    from lineends import count_lines, detect, normalize


    class BasicTests(unittest.TestCase):
        def test_detect(self):
            self.assertEqual(detect("a\r\nb\r\n"), "crlf")

        def test_normalize(self):
            self.assertEqual(normalize("a\r\nb\rc\n"), "a\nb\nc\n")

        def test_count(self):
            self.assertEqual(count_lines("a\nb"), 2)


    if __name__ == "__main__":
        unittest.main()
''')

LE_HIDDEN = dd(r'''
    import unittest

    from lineends import count_endings, count_lines, detect, dominant, ensure_final_newline, normalize, strip_trailing


    class Counting(unittest.TestCase):
        def test_counts(self):
            self.assertEqual(count_endings(""), {"crlf": 0, "lf": 0, "cr": 0})
            self.assertEqual(count_endings("a\nb\n"), {"crlf": 0, "lf": 2, "cr": 0})
            self.assertEqual(count_endings("a\r\nb\r\n"), {"crlf": 2, "lf": 0, "cr": 0})
            self.assertEqual(count_endings("a\rb\rc"), {"crlf": 0, "lf": 0, "cr": 2})
            self.assertEqual(count_endings("a\r\nb\nc\rd"), {"crlf": 1, "lf": 1, "cr": 1})

        def test_crlf_is_one_ending(self):
            self.assertEqual(count_endings("\r\n"), {"crlf": 1, "lf": 0, "cr": 0})
            self.assertEqual(count_endings("\r\r\n"), {"crlf": 1, "lf": 0, "cr": 1})
            self.assertEqual(count_endings("\n\r"), {"crlf": 0, "lf": 1, "cr": 1})
            self.assertEqual(count_endings("\r\n\r\n\n"), {"crlf": 2, "lf": 1, "cr": 0})

        def test_detect(self):
            self.assertEqual(detect(""), "none")
            self.assertEqual(detect("no endings"), "none")
            self.assertEqual(detect("a\nb"), "lf")
            self.assertEqual(detect("a\r\nb\r\n"), "crlf")
            self.assertEqual(detect("a\rb"), "cr")
            self.assertEqual(detect("a\r\nb\n"), "mixed")
            self.assertEqual(detect("a\nb\r"), "mixed")
            self.assertEqual(detect("a\r\nb\r"), "mixed")
            self.assertEqual(detect("\n"), "lf")

        def test_dominant(self):
            self.assertEqual(dominant("a\r\nb\r\nc\n"), "\r\n")
            self.assertEqual(dominant("a\nb\nc\r\n"), "\n")
            self.assertEqual(dominant("a\rb\rc\rd\n"), "\r")
            self.assertEqual(dominant("no endings"), "\n")
            self.assertEqual(dominant(""), "\n")

        def test_dominant_ties(self):
            self.assertEqual(dominant("a\nb\r\n"), "\n")
            self.assertEqual(dominant("a\r\nb\r"), "\r\n")
            self.assertEqual(dominant("a\nb\r"), "\n")
            self.assertEqual(dominant("a\nb\r\nc\r"), "\n")
            self.assertEqual(dominant("a\r\nb\rc\n"), "\n")
            self.assertEqual(dominant("a\r\nb\r\nc\rd\r"), "\r\n")


    class Normalize(unittest.TestCase):
        def test_default_lf(self):
            self.assertEqual(normalize("a\r\nb\rc\nd"), "a\nb\nc\nd")
            self.assertEqual(normalize(""), "")
            self.assertEqual(normalize("plain"), "plain")
            self.assertEqual(normalize("\r\n\r\n"), "\n\n")
            self.assertEqual(normalize("\r\r\n"), "\n\n")

        def test_other_targets(self):
            self.assertEqual(normalize("a\nb\rc\r\n", "\r\n"), "a\r\nb\r\nc\r\n")
            self.assertEqual(normalize("a\nb\r\nc", "\r"), "a\rb\rc")
            self.assertEqual(normalize("a\r\nb", "\n"), "a\nb")

        def test_idempotent(self):
            for eol in ("\r\n", "\n", "\r"):
                once = normalize("a\r\nb\nc\rd\n", eol)
                self.assertEqual(normalize(once, eol), once)
                self.assertEqual(detect(once), {"\r\n": "crlf", "\n": "lf", "\r": "cr"}[eol])

        def test_bad_eol(self):
            for bad in ("", "\n\n", "x", "\r\r", " ", None):
                with self.assertRaises(ValueError):
                    normalize("a", bad)

        def test_other_whitespace_kept(self):
            self.assertEqual(normalize("a \t\r\n b\x0b\x0c\u2028c"), "a \t\n b\x0b\x0c\u2028c")


    class CountLines(unittest.TestCase):
        def test_values(self):
            self.assertEqual(count_lines(""), 0)
            self.assertEqual(count_lines("a"), 1)
            self.assertEqual(count_lines("a\n"), 1)
            self.assertEqual(count_lines("a\nb"), 2)
            self.assertEqual(count_lines("a\nb\n"), 2)
            self.assertEqual(count_lines("\n"), 1)
            self.assertEqual(count_lines("\n\n"), 2)
            self.assertEqual(count_lines("a\r\nb\r\n"), 2)
            self.assertEqual(count_lines("a\rb"), 2)
            self.assertEqual(count_lines("a\rb\r"), 2)
            self.assertEqual(count_lines("a\r\nb"), 2)
            self.assertEqual(count_lines("\r\n"), 1)
            self.assertEqual(count_lines("\r"), 1)
            self.assertEqual(count_lines("a\n\nb"), 3)


    class FinalNewline(unittest.TestCase):
        def test_adds_when_missing(self):
            self.assertEqual(ensure_final_newline("a"), "a\n")
            self.assertEqual(ensure_final_newline("a\nb"), "a\nb\n")
            self.assertEqual(ensure_final_newline("a", "\r\n"), "a\r\n")
            self.assertEqual(ensure_final_newline("a", "\r"), "a\r")
            self.assertEqual(ensure_final_newline("a ", "\n"), "a \n")

        def test_keeps_existing_endings(self):
            self.assertEqual(ensure_final_newline("a\n"), "a\n")
            self.assertEqual(ensure_final_newline("a\r\n"), "a\r\n")
            self.assertEqual(ensure_final_newline("a\r"), "a\r")
            self.assertEqual(ensure_final_newline("a\r\n", "\n"), "a\r\n")
            self.assertEqual(ensure_final_newline("\n"), "\n")

        def test_empty_stays_empty(self):
            self.assertEqual(ensure_final_newline(""), "")
            self.assertEqual(ensure_final_newline("", "\r\n"), "")

        def test_bad_eol(self):
            for bad in ("", "x", "\n\r"):
                with self.assertRaises(ValueError):
                    ensure_final_newline("a", bad)
            with self.assertRaises(ValueError):
                ensure_final_newline("a\n", "x")
            with self.assertRaises(ValueError):
                ensure_final_newline("", "x")


    class StripTrailing(unittest.TestCase):
        def test_values(self):
            self.assertEqual(strip_trailing("a  \nb\t\nc \t "), "a\nb\nc")
            self.assertEqual(strip_trailing("a  \r\nb  \r\n"), "a\r\nb\r\n")
            self.assertEqual(strip_trailing("a  \rb  \r"), "a\rb\r")
            self.assertEqual(strip_trailing("  a  b  \n"), "  a  b\n")
            self.assertEqual(strip_trailing("   \n"), "\n")
            self.assertEqual(strip_trailing("   "), "")
            self.assertEqual(strip_trailing(""), "")
            self.assertEqual(strip_trailing("a\n  \n  \nb"), "a\n\n\nb")

        def test_other_whitespace_is_kept(self):
            self.assertEqual(strip_trailing("a\x0b \nb\x0c"), "a\x0b\nb\x0c")
            self.assertEqual(strip_trailing("a \n"), "a \n")

        def test_mixed_endings_survive(self):
            self.assertEqual(strip_trailing("a \r\nb \nc \rd "), "a\r\nb\nc\rd")


    if __name__ == "__main__":
        unittest.main()
''')

LE = Lib(
    name="lineends", lang="python", title="the line-ending helpers (`lineends.py`)",
    blurb="The repository linter detects and normalises line endings with this module.",
    files={"lineends.py": LE_SRC, "README.md": LE_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": LE_VISIBLE},
    hidden_tests={"tests/test_full.py": LE_HIDDEN},
    mutate=["lineends.py"], difficulty=1, tags=["whitespace", "text"],
    probes=[
        'count_endings("a\\r\\nb\\nc\\rd\\r\\r\\n")',
        'detect("a\\r\\nb\\r")',
        'dominant("a\\nb\\r\\n")',
        'dominant("a\\r\\nb\\r\\nc\\rd\\r")',
        'normalize("a\\r\\nb\\rc\\nd", "\\r\\n")',
        'count_lines("a\\r\\nb")',
        'count_lines("\\r")',
        'ensure_final_newline("a\\r\\n", "\\n")',
        'ensure_final_newline("a", "\\r\\n")',
        'strip_trailing("a \\r\\nb \\nc \\rd ")',
    ],
    probe_import="from lineends import *",
)


# ======================================================================================================================
# trimmid: shortening long strings and long outputs
# ======================================================================================================================

TM_README = dd(r'''
    # trimmid

    Shortens long strings for table cells, subject lines and pasted command output. One module, `trimmid.py`.

    ## `truncate_middle(text, width, marker="...") -> str`
    Returns `text` unchanged when `len(text) <= width`. Otherwise the result is exactly `width` characters long: the start of the text, then `marker`, then
    the end of the text. Of the `kept = width - len(marker)` characters taken from the text, the start gets `ceil(kept / 2)` and the end gets `kept // 2`
    (so the start is the larger part when `kept` is odd; the end may be empty).
    A `width` smaller than `len(marker)` is a `ValueError`, checked first (even for a short text).

    Examples: `truncate_middle("abcdefghij", 7)` is `"ab...ij"`; width 8 gives `"abc...ij"`; width 4 gives `"a..."`; width 3 gives `"..."`.

    ## `truncate_words(text, width, marker="...") -> str`
    Returns `text` unchanged when `len(text) <= width`. Otherwise keeps as many leading *whole words* as fit together with the marker, and appends the marker.
    A word is a maximal run of non-whitespace characters; the text between kept words (and any leading whitespace) is kept exactly as written. A word fits when
    it ends at or before position `width - len(marker)`. The kept part then has trailing whitespace and trailing `,` `;` `:` `-` characters removed (repeatedly)
    before the marker is appended; if no word fits, the result is the marker alone. A `width` smaller than `len(marker)` is a `ValueError`, checked first.

    ## `clip_lines(text, max_lines, marker="[... {n} more lines]") -> str`
    Keeps the first `max_lines` lines of `text` (lines end at `\n`; a final `\n` does not start another line, and is kept in the result when the text had
    one). When more lines follow, they are replaced by one line, `marker` with every `{n}` replaced by the number of omitted lines. A marker is never used to
    replace a single line: when only one line would be omitted, the text is returned unchanged. `max_lines` below 1 is a `ValueError`.
''')

TM_SRC = dd(r'''
    """Shorten long strings."""
    import re

    _TRIM = " \t\r\n,;:-"


    def _check(width, marker):
        if width < len(marker):
            raise ValueError("width is smaller than the marker")


    def truncate_middle(text, width, marker="..."):
        _check(width, marker)
        if len(text) <= width:
            return text
        kept = width - len(marker)
        head = (kept + 1) // 2
        tail = kept // 2
        return text[:head] + marker + text[len(text) - tail:]


    def truncate_words(text, width, marker="..."):
        _check(width, marker)
        if len(text) <= width:
            return text
        room = width - len(marker)
        end = 0
        for m in re.finditer(r"\S+", text):
            if m.end() > room:
                break
            end = m.end()
        return text[:end].rstrip(_TRIM) + marker


    def clip_lines(text, max_lines, marker="[... {n} more lines]"):
        if max_lines < 1:
            raise ValueError("max_lines must be at least 1")
        ended = text.endswith("\n")
        lines = text.split("\n")
        if ended:
            lines.pop()
        omitted = len(lines) - max_lines
        if omitted >= 2:
            lines = lines[:max_lines] + [marker.replace("{n}", str(omitted))]
        out = "\n".join(lines)
        return out + "\n" if ended else out
''')

TM_VISIBLE = dd(r'''
    import unittest

    from trimmid import clip_lines, truncate_middle, truncate_words


    class BasicTests(unittest.TestCase):
        def test_middle(self):
            self.assertEqual(truncate_middle("abcdefghij", 7), "ab...ij")

        def test_words(self):
            self.assertEqual(truncate_words("the quick brown fox jumps", 20), "the quick brown...")

        def test_lines(self):
            self.assertEqual(clip_lines("a\nb\nc\nd\ne", 2), "a\nb\n[... 3 more lines]")


    if __name__ == "__main__":
        unittest.main()
''')

TM_HIDDEN = dd(r'''
    import unittest

    from trimmid import clip_lines, truncate_middle, truncate_words


    class Middle(unittest.TestCase):
        def test_unchanged_when_it_fits(self):
            self.assertEqual(truncate_middle("abcdefghij", 10), "abcdefghij")
            self.assertEqual(truncate_middle("abcdefghij", 50), "abcdefghij")
            self.assertEqual(truncate_middle("", 5), "")
            self.assertEqual(truncate_middle("", 3), "")
            self.assertEqual(truncate_middle("ab", 3), "ab")

        def test_split_of_kept_characters(self):
            self.assertEqual(truncate_middle("abcdefghij", 9), "abc...hij")
            self.assertEqual(truncate_middle("abcdefghij", 8), "abc...ij")
            self.assertEqual(truncate_middle("abcdefghij", 7), "ab...ij")
            self.assertEqual(truncate_middle("abcdefghij", 6), "ab...j")
            self.assertEqual(truncate_middle("abcdefghij", 5), "a...j")
            self.assertEqual(truncate_middle("abcdefghij", 4), "a...")

        def test_marker_only(self):
            self.assertEqual(truncate_middle("abcdefghij", 3), "...")
            self.assertEqual(truncate_middle("abcdefghij", 1, marker="~"), "~")

        def test_result_length_is_width(self):
            for width in range(3, 25):
                self.assertEqual(len(truncate_middle("x" * 40, width)), width)
            for width in range(4, 25):
                self.assertEqual(len(truncate_middle("y" * 25, width, marker="[..]")), width)

        def test_custom_markers(self):
            self.assertEqual(truncate_middle("0123456789", 5, marker="~"), "01~89")
            self.assertEqual(truncate_middle("0123456789", 4, marker="~"), "01~9")
            self.assertEqual(truncate_middle("0123456789", 6, marker="[..]"), "0[..]9")
            self.assertEqual(truncate_middle("0123456789", 4, marker=""), "0189")
            self.assertEqual(truncate_middle("0123456789", 5, marker=""), "01289")
            self.assertEqual(truncate_middle("0123456789", 0, marker=""), "")

        def test_bad_width_is_checked_first(self):
            for w in (0, 1, 2, -5):
                with self.assertRaises(ValueError):
                    truncate_middle("abcdefghij", w)
            with self.assertRaises(ValueError):
                truncate_middle("ab", 2)
            with self.assertRaises(ValueError):
                truncate_middle("", 0)
            with self.assertRaises(ValueError):
                truncate_middle("abcdefghij", 3, marker="[...]")

        def test_non_ascii_counts_characters(self):
            self.assertEqual(truncate_middle("éèêëàâä", 5, marker="-"), "éè-âä")


    class Words(unittest.TestCase):
        def test_unchanged_when_it_fits(self):
            self.assertEqual(truncate_words("a, b,", 10), "a, b,")
            self.assertEqual(truncate_words("the quick brown fox", 19), "the quick brown fox")
            self.assertEqual(truncate_words("", 3), "")

        def test_whole_words_only(self):
            text = "the quick brown fox jumps"
            self.assertEqual(truncate_words(text, 24), "the quick brown fox...")
            self.assertEqual(truncate_words(text, 20), "the quick brown...")
            self.assertEqual(truncate_words(text, 22), "the quick brown fox...")
            self.assertEqual(truncate_words(text, 19), "the quick brown...")
            self.assertEqual(truncate_words(text, 9), "the...")
            self.assertEqual(truncate_words(text, 6), "the...")

        def test_boundary_of_fit(self):
            self.assertEqual(truncate_words("aaa bbb ccc", 9), "aaa...")
            self.assertEqual(truncate_words("aaa bbb ccc", 10), "aaa bbb...")
            self.assertEqual(truncate_words("aaa bbb ccc", 11), "aaa bbb ccc")

        def test_nothing_fits(self):
            self.assertEqual(truncate_words("the quick brown fox jumps", 5), "...")
            self.assertEqual(truncate_words("the quick brown fox jumps", 3), "...")
            self.assertEqual(truncate_words("hello   ", 6), "...")

        def test_trailing_punctuation_is_removed(self):
            self.assertEqual(truncate_words("alpha, beta, gamma delta", 15), "alpha, beta...")
            self.assertEqual(truncate_words("one - two - three four", 14), "one - two...")
            self.assertEqual(truncate_words("one; two; three", 12), "one; two...")
            self.assertEqual(truncate_words("a: b: c: d: e", 8), "a: b...")
            self.assertEqual(truncate_words("end. more words here", 12), "end. more...")
            self.assertEqual(truncate_words("wait, , , more", 11), "wait...")

        def test_inner_spacing_is_kept(self):
            self.assertEqual(truncate_words("a    b    c    d", 12), "a    b...")
            self.assertEqual(truncate_words("  hello world again", 14), "  hello...")
            self.assertEqual(truncate_words("line one\nline two\nline three", 20), "line one\nline two...")
            self.assertEqual(truncate_words("a\tb\tc\td\te", 7), "a\tb...")
            self.assertEqual(truncate_words("a\tb\tc\td\te", 8), "a\tb\tc...")

        def test_custom_marker(self):
            self.assertEqual(truncate_words("the quick brown fox", 10, marker="…"), "the quick…")
            self.assertEqual(truncate_words("the quick brown fox", 12, marker=" [more]"), "the [more]")
            self.assertEqual(truncate_words("the quick brown fox", 9, marker=""), "the quick")
            self.assertEqual(truncate_words("the quick brown fox", 8, marker=""), "the")

        def test_bad_width_is_checked_first(self):
            with self.assertRaises(ValueError):
                truncate_words("abc", 2)
            with self.assertRaises(ValueError):
                truncate_words("", 2)
            with self.assertRaises(ValueError):
                truncate_words("abc def", 5, marker="[....]")


    class Clip(unittest.TestCase):
        def test_clipped(self):
            text = "a\nb\nc\nd\ne"
            self.assertEqual(clip_lines(text, 2), "a\nb\n[... 3 more lines]")
            self.assertEqual(clip_lines(text, 3), "a\nb\nc\n[... 2 more lines]")
            self.assertEqual(clip_lines(text, 1), "a\n[... 4 more lines]")

        def test_single_omitted_line_is_kept(self):
            text = "a\nb\nc\nd\ne"
            self.assertEqual(clip_lines(text, 4), text)
            self.assertEqual(clip_lines(text, 5), text)
            self.assertEqual(clip_lines(text, 99), text)
            self.assertEqual(clip_lines("a\nb", 1), "a\nb")

        def test_trailing_newline(self):
            self.assertEqual(clip_lines("a\nb\nc\nd\ne\n", 2), "a\nb\n[... 3 more lines]\n")
            self.assertEqual(clip_lines("a\nb\nc\nd\ne\n", 4), "a\nb\nc\nd\ne\n")
            self.assertEqual(clip_lines("a\nb\nc\n", 3), "a\nb\nc\n")
            self.assertEqual(clip_lines("a\nb\nc\nd\n", 3), "a\nb\nc\nd\n")
            self.assertEqual(clip_lines("a\nb\nc\nd\ne\nf\n", 3), "a\nb\nc\n[... 3 more lines]\n")

        def test_degenerate_texts(self):
            self.assertEqual(clip_lines("", 1), "")
            self.assertEqual(clip_lines("\n", 1), "\n")
            self.assertEqual(clip_lines("x", 1), "x")
            self.assertEqual(clip_lines("x\n", 1), "x\n")
            self.assertEqual(clip_lines("\n\n\n", 1), "\n[... 2 more lines]\n")

        def test_blank_lines_count(self):
            self.assertEqual(clip_lines("a\n\n\n\nb", 1), "a\n[... 4 more lines]")
            self.assertEqual(clip_lines("\n\n\n\n\n", 2), "\n\n[... 3 more lines]\n")

        def test_custom_marker(self):
            text = "l1\nl2\nl3\nl4\nl5\nl6"
            self.assertEqual(clip_lines(text, 2, marker="(+{n})"), "l1\nl2\n(+4)")
            self.assertEqual(clip_lines(text, 2, marker="<snip>"), "l1\nl2\n<snip>")
            self.assertEqual(clip_lines(text, 2, marker="{n}/{n}"), "l1\nl2\n4/4")
            self.assertEqual(clip_lines(text, 2, marker="{x} {n}"), "l1\nl2\n{x} 4")
            self.assertEqual(clip_lines(text, 2, marker=""), "l1\nl2\n")

        def test_carriage_returns_are_ordinary_characters(self):
            self.assertEqual(clip_lines("a\r\nb\r\nc\r\nd", 1), "a\r\n[... 3 more lines]")

        def test_bad_max_lines(self):
            for n in (0, -1):
                with self.assertRaises(ValueError):
                    clip_lines("a\nb\nc", n)


    if __name__ == "__main__":
        unittest.main()
''')

TM = Lib(
    name="trimmid", lang="python", title="the string shortener (`trimmid.py`)",
    blurb="Table cells, subject lines and pasted command output are shortened with this module.",
    files={"trimmid.py": TM_SRC, "README.md": TM_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": TM_VISIBLE},
    hidden_tests={"tests/test_full.py": TM_HIDDEN},
    mutate=["trimmid.py"], difficulty=2, tags=["strings", "text"],
    probes=[
        'truncate_middle("abcdefghij", 8)',
        'truncate_middle("abcdefghij", 4)',
        'truncate_middle("0123456789", 4, marker="")',
        'truncate_words("the quick brown fox jumps", 20)',
        'truncate_words("alpha, beta, gamma delta", 15)',
        'truncate_words("a    b    c    d", 12)',
        'clip_lines("a\\nb\\nc\\nd\\ne\\n", 2)',
        'clip_lines("a\\nb\\nc\\nd\\ne", 4)',
        'clip_lines("l1\\nl2\\nl3\\nl4\\nl5\\nl6", 2, marker="{n}/{n}")',
    ],
    probe_import="from trimmid import *",
)


# ======================================================================================================================
# headcase: headline capitalisation
# ======================================================================================================================

HC_README = dd(r'''
    # headcase

    Capitalisation for headlines and captions in the publishing tool. One module, `headcase.py`. Only ASCII letters are ever changed; every other character
    stays as it is.

    ## `SMALL_WORDS`
    The default small words: `a an and as at but by for in nor of on or the to up via vs`.

    ## `capitalize_word(word) -> str`
    Upper-cases the first letter of `word`, looking past leading characters that are not letters or digits (`"(hello)"` becomes `"(Hello)"`). Nothing changes when
    `word` already contains an ASCII capital letter anywhere (`"iPhone"`, `"NASA"`), or when the first letter or digit is a digit or a non-ASCII letter
    (`"3rd"`, `"élan"`), or when there is none. Only that one character changes (`"don't"` becomes `"Don't"`).

    ## `titlecase(text, small=None) -> str`
    Headline capitalisation. The text is split at single spaces (`" "`; tabs and newlines are ordinary characters, empty pieces from repeated spaces are kept
    so the spacing is preserved) into *words*; only the non-empty pieces count as words. Each word is handled as follows.
    * A word containing `-` is split at every `-` and each part is passed through `capitalize_word` (so small words inside it are capitalised too:
      `"state-of-the-art"` becomes `"State-Of-The-Art"`).
    * Any other word is passed through `capitalize_word`, unless it is a *small word* in the middle of the headline, in which case it stays as written. A word is
      small when it equals one of the small words once the punctuation around it is removed (the punctuation is every character that is not a letter, a digit or
      an underscore, at both ends of the word: `"(the)"` is small, `"it's"` is not).
    * A word is never left small when it is the first word, the last word, or comes right after a word that ends with `:` or is exactly `-`; it is capitalised.

    `small` replaces the default small words: an iterable of words, compared in lower case (`None` means `SMALL_WORDS`; an empty list means no small words).

    ## `titlecase_lines(text, small=None) -> str`
    Splits `text` at `\n`, applies `titlecase` to each line separately (so every line has its own first and last word) and joins the lines with `\n`.

    ## `sentence_case(text) -> str`
    Upper-cases the first lowercase ASCII letter of each sentence and leaves everything else alone. A sentence starts at the beginning of the text, after any
    leading whitespace, and after one or more of `.` `!` `?` followed by whitespace. Within the sentence start, characters that are neither word characters nor
    whitespace (quotes, brackets) are skipped; a sentence whose first word character is not a lowercase ASCII letter (a digit, a capital, an accented letter) is
    left alone. Abbreviations are not special: `"e.g. this"` becomes `"E.g. This"`.
''')

HC_SRC = dd(r'''
    """Headline capitalisation."""
    import re

    SMALL_WORDS = frozenset("a an and as at but by for in nor of on or the to up via vs".split())


    def _has_capital(text):
        return any("A" <= c <= "Z" for c in text)


    def capitalize_word(word):
        if _has_capital(word):
            return word
        i = 0
        while i < len(word) and not word[i].isalnum():
            i += 1
        if i < len(word) and "a" <= word[i] <= "z":
            return word[:i] + word[i].upper() + word[i + 1:]
        return word


    def _core(word):
        return re.fullmatch(r"\W*(.*?)\W*", word).group(1)


    def titlecase(text, small=None):
        smalls = SMALL_WORDS if small is None else frozenset(w.lower() for w in small)
        pieces = text.split(" ")
        where = [i for i, p in enumerate(pieces) if p]
        for n, i in enumerate(where):
            word = pieces[i]
            if "-" in word:
                pieces[i] = "-".join(capitalize_word(part) for part in word.split("-"))
                continue
            forced = n == 0 or n == len(where) - 1
            if not forced:
                before = pieces[where[n - 1]]
                forced = before.endswith(":") or before == "-"
            if forced or _core(word) not in smalls:
                pieces[i] = capitalize_word(word)
        return " ".join(pieces)


    def titlecase_lines(text, small=None):
        return "\n".join(titlecase(line, small) for line in text.split("\n"))


    def sentence_case(text):
        return re.sub(
            r"(\A\s*|[.!?]+\s+)([^\w\s]*)([a-z])",
            lambda m: m.group(1) + m.group(2) + m.group(3).upper(),
            text,
        )
''')

HC_VISIBLE = dd(r'''
    import unittest

    from headcase import capitalize_word, sentence_case, titlecase, titlecase_lines


    class BasicTests(unittest.TestCase):
        def test_word(self):
            self.assertEqual(capitalize_word("(hello)"), "(Hello)")

        def test_title(self):
            self.assertEqual(titlecase("the lord of the rings"), "The Lord of the Rings")

        def test_lines(self):
            self.assertEqual(titlecase_lines("go on\nand on"), "Go On\nAnd On")

        def test_sentences(self):
            self.assertEqual(sentence_case("hi. there"), "Hi. There")


    if __name__ == "__main__":
        unittest.main()
''')

HC_HIDDEN = dd(r'''
    import unittest

    from headcase import SMALL_WORDS, capitalize_word, sentence_case, titlecase, titlecase_lines


    class Word(unittest.TestCase):
        def test_plain(self):
            self.assertEqual(capitalize_word("hello"), "Hello")
            self.assertEqual(capitalize_word("a"), "A")
            self.assertEqual(capitalize_word("Hello"), "Hello")
            self.assertEqual(capitalize_word(""), "")

        def test_leading_punctuation(self):
            self.assertEqual(capitalize_word("(hello)"), "(Hello)")
            self.assertEqual(capitalize_word('"hello'), '"Hello')
            self.assertEqual(capitalize_word("'tis"), "'Tis")
            self.assertEqual(capitalize_word("-x"), "-X")
            self.assertEqual(capitalize_word("..."), "...")

        def test_only_one_letter_changes(self):
            self.assertEqual(capitalize_word("don't"), "Don't")
            self.assertEqual(capitalize_word("o'neil"), "O'neil")
            self.assertEqual(capitalize_word("hello world"), "Hello world")

        def test_existing_capitals_block_the_change(self):
            self.assertEqual(capitalize_word("hELLO"), "hELLO")
            self.assertEqual(capitalize_word("iPhone"), "iPhone")
            self.assertEqual(capitalize_word("NASA"), "NASA")
            self.assertEqual(capitalize_word("e-Mail"), "e-Mail")
            self.assertEqual(capitalize_word("(iOS)"), "(iOS)")

        def test_digits_and_accents(self):
            self.assertEqual(capitalize_word("3rd"), "3rd")
            self.assertEqual(capitalize_word("1st-place"), "1st-place")
            self.assertEqual(capitalize_word("(42nd"), "(42nd")
            self.assertEqual(capitalize_word("élan"), "élan")
            self.assertEqual(capitalize_word("éa"), "éa")
            self.assertEqual(capitalize_word("café"), "Café")

        def test_small_words_constant(self):
            self.assertEqual(len(SMALL_WORDS), 18)
            for w in ("a", "an", "and", "as", "at", "but", "by", "for", "in", "nor", "of", "on", "or", "the", "to", "up", "via", "vs"):
                self.assertIn(w, SMALL_WORDS)
            self.assertNotIn("is", SMALL_WORDS)


    class Title(unittest.TestCase):
        def test_small_words_in_the_middle(self):
            self.assertEqual(titlecase("the lord of the rings"), "The Lord of the Rings")
            self.assertEqual(titlecase("a tale of two cities"), "A Tale of Two Cities")
            self.assertEqual(titlecase("war and peace"), "War and Peace")
            self.assertEqual(titlecase("what to do in a crisis"), "What to Do in a Crisis")
            self.assertEqual(titlecase("to be or not to be"), "To Be or Not to Be")
            self.assertEqual(titlecase("walk via the old road by the sea"), "Walk via the Old Road by the Sea")

        def test_first_and_last_are_always_capitalised(self):
            self.assertEqual(titlecase("going up"), "Going Up")
            self.assertEqual(titlecase("up and away"), "Up and Away")
            self.assertEqual(titlecase("what is it for"), "What Is It For")
            self.assertEqual(titlecase("the"), "The")
            self.assertEqual(titlecase("a"), "A")
            self.assertEqual(titlecase("of"), "Of")

        def test_after_colon_or_dash(self):
            self.assertEqual(titlecase("learning python: the hard way again"), "Learning Python: The Hard Way Again")
            self.assertEqual(titlecase("a lot of things: of mice and men"), "A Lot of Things: Of Mice and Men")
            self.assertEqual(titlecase("intro: the story of the end"), "Intro: The Story of the End")
            self.assertEqual(titlecase("rock - the story of a band"), "Rock - The Story of a Band")
            self.assertEqual(titlecase("rock -the story of a band"), "Rock -The Story of a Band")
            self.assertEqual(titlecase("note; the end of it all"), "Note; the End of It All")
            self.assertEqual(titlecase("10:30 the end of it"), "10:30 the End of It")

        def test_only_the_next_word_is_forced(self):
            self.assertEqual(titlecase("part: a tale of the sea"), "Part: A Tale of the Sea")
            self.assertEqual(titlecase("part: a and the rest"), "Part: A and the Rest")

        def test_words_with_capitals_are_untouched(self):
            self.assertEqual(titlecase("using NASA data in the iPhone era"), "Using NASA Data in the iPhone Era")
            self.assertEqual(titlecase("The Lord Of The Rings"), "The Lord Of The Rings")
            self.assertEqual(titlecase("THE END"), "THE END")
            self.assertEqual(titlecase("meet McDonald in the park"), "Meet McDonald in the Park")

        def test_hyphenated_words(self):
            self.assertEqual(titlecase("state-of-the-art design"), "State-Of-The-Art Design")
            self.assertEqual(titlecase("a well-known fact"), "A Well-Known Fact")
            self.assertEqual(titlecase("self-Driving cars"), "Self-Driving Cars")
            self.assertEqual(titlecase("up-to-date news"), "Up-To-Date News")
            self.assertEqual(titlecase("pre-1990s tech"), "Pre-1990s Tech")
            self.assertEqual(titlecase("a well--known fact"), "A Well--Known Fact")
            self.assertEqual(titlecase("tips for e-mail use"), "Tips for E-Mail Use")
            self.assertEqual(titlecase("tips for e-Mail use"), "Tips for E-Mail Use")
            self.assertEqual(titlecase("hello the-end now"), "Hello The-End Now")

        def test_punctuation_around_words(self):
            self.assertEqual(titlecase('"the great gatsby"'), '"The Great Gatsby"')
            self.assertEqual(titlecase("birds, the bees, and the trees"), "Birds, the Bees, and the Trees")
            self.assertEqual(titlecase('say "and" then stop'), 'Say "and" Then Stop')
            self.assertEqual(titlecase("(the) end"), "(The) End")
            self.assertEqual(titlecase("fun (and games) for all"), "Fun (and Games) for All")
            self.assertEqual(titlecase("it's the end of it's life"), "It's the End of It's Life")
            self.assertEqual(titlecase("loud, but (a) bit rude"), "Loud, but (a) Bit Rude")

        def test_digits_and_accents(self):
            self.assertEqual(titlecase("top 10 of 2020"), "Top 10 of 2020")
            self.assertEqual(titlecase("3rd place"), "3rd Place")
            self.assertEqual(titlecase("café au lait"), "Café Au Lait")
            self.assertEqual(titlecase("über the éclair"), "über the éclair")

        def test_spacing_is_preserved(self):
            self.assertEqual(titlecase("  the  big   deal "), "  The  Big   Deal ")
            self.assertEqual(titlecase(""), "")
            self.assertEqual(titlecase(" "), " ")
            self.assertEqual(titlecase("   "), "   ")
            self.assertEqual(titlecase("a  of  the"), "A  of  The")

        def test_only_space_separates_words(self):
            self.assertEqual(titlecase("hello\nworld and more"), "Hello\nworld and More")
            self.assertEqual(titlecase("one\tof the best"), "One\tof the Best")

        def test_custom_small_words(self):
            self.assertEqual(titlecase("the cat sat on the mat", small=["on"]), "The Cat Sat on The Mat")
            self.assertEqual(titlecase("go to the park", small=[]), "Go To The Park")
            self.assertEqual(titlecase("go on and on", small=["ON"]), "Go on And On")
            self.assertEqual(titlecase("go to the park", small=("to", "the")), "Go to the Park")
            self.assertEqual(titlecase("go to the park", small=iter(["the"])), "Go To the Park")
            self.assertEqual(titlecase("go to the park", small=None), "Go to the Park")

        def test_default_small_words_are_exactly_the_documented_ones(self):
            words = "a an and as at but by for in nor of on or the to up via vs".split()
            text = "x " + " ".join(words) + " y"
            self.assertEqual(titlecase(text), "X " + " ".join(words) + " Y")
            for w in ("is", "it", "so", "with", "from", "into", "if", "be", "do", "yet"):
                self.assertEqual(titlecase("x %s y" % w), "X %s Y" % w.capitalize())


    class Lines(unittest.TestCase):
        def test_each_line_is_a_headline(self):
            self.assertEqual(
                titlecase_lines("the first line\nof the story\nin a book"),
                "The First Line\nOf the Story\nIn a Book",
            )

        def test_trailing_and_blank_lines(self):
            self.assertEqual(titlecase_lines("the end\n"), "The End\n")
            self.assertEqual(titlecase_lines("a b\n\nc d"), "A B\n\nC D")
            self.assertEqual(titlecase_lines(""), "")
            self.assertEqual(titlecase_lines("\n"), "\n")

        def test_small_is_passed_on(self):
            self.assertEqual(titlecase_lines("go on\non and on", small=["on"]), "Go On\nOn And On")
            self.assertEqual(titlecase_lines("a to b\nc to d", small=[]), "A To B\nC To D")

        def test_crlf(self):
            self.assertEqual(titlecase_lines("the end\r\nthe start"), "The End\r\nThe Start")


    class Sentences(unittest.TestCase):
        def test_basic(self):
            self.assertEqual(sentence_case("hello world. how are you? fine! ok"), "Hello world. How are you? Fine! Ok")
            self.assertEqual(sentence_case("done."), "Done.")
            self.assertEqual(sentence_case(""), "")
            self.assertEqual(sentence_case("a"), "A")

        def test_leading_whitespace_and_punctuation(self):
            self.assertEqual(sentence_case("  leading space"), "  Leading space")
            self.assertEqual(sentence_case('"quoted start" he said'), '"Quoted start" he said')
            self.assertEqual(sentence_case("(parenthetical) start. (another) one"), "(Parenthetical) start. (Another) one")
            self.assertEqual(sentence_case("\n\nhello"), "\n\nHello")

        def test_separators(self):
            self.assertEqual(sentence_case("wait... what"), "Wait... What")
            self.assertEqual(sentence_case("really?! yes"), "Really?! Yes")
            self.assertEqual(sentence_case("one.\ntwo"), "One.\nTwo")
            self.assertEqual(sentence_case("one.   two"), "One.   Two")
            self.assertEqual(sentence_case("e.g. this"), "E.g. This")

        def test_no_whitespace_after_the_stop_means_no_new_sentence(self):
            self.assertEqual(sentence_case("v1.5 is out"), "V1.5 is out")
            self.assertEqual(sentence_case("a.b c"), "A.b c")
            self.assertEqual(sentence_case("see x,y. then"), "See x,y. Then")

        def test_other_starts_are_left_alone(self):
            self.assertEqual(sentence_case("3 apples. 4 pears. five"), "3 apples. 4 pears. Five")
            self.assertEqual(sentence_case("already Fine. OK then"), "Already Fine. OK then")
            self.assertEqual(sentence_case("über. éa"), "über. éa")
            self.assertEqual(sentence_case("one. Two. three"), "One. Two. Three")

        def test_only_the_first_letter_changes(self):
            self.assertEqual(sentence_case("hELLO wORLD"), "HELLO wORLD")
            self.assertEqual(sentence_case("mixed Case words. more Words here"), "Mixed Case words. More Words here")

        def test_every_sentence_start_changes(self):
            self.assertEqual(sentence_case("a. b. c. d"), "A. B. C. D")


    if __name__ == "__main__":
        unittest.main()
''')

HC = Lib(
    name="headcase", lang="python", title="the headline capitaliser (`headcase.py`)",
    blurb="The publishing tool fixes the capitalisation of headlines and captions with this module.",
    files={"headcase.py": HC_SRC, "README.md": HC_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": HC_VISIBLE},
    hidden_tests={"tests/test_full.py": HC_HIDDEN},
    mutate=["headcase.py"], difficulty=2, tags=["capitalisation", "text"],
    probes=[
        'capitalize_word("(hello)")',
        'capitalize_word("3rd")',
        'titlecase("what to do in a crisis")',
        'titlecase("a lot of things: of mice and men")',
        'titlecase("state-of-the-art design")',
        'titlecase("birds, the bees, and the trees")',
        'titlecase("  the  big   deal ")',
        'titlecase("go on and on", small=["ON"])',
        'titlecase_lines("the first line\\nof the story\\nin a book")',
        'sentence_case("wait... what")',
        'sentence_case("3 apples. 4 pears. five")',
    ],
    probe_import="from headcase import *",
)


LIBS = [TS, LE, TM, HC]
register_libs(LIBS, n=10)
