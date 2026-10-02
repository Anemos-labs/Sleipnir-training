"""Text-format libraries (python), batch: text layout and terminal output."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# wrapjust: paragraph filling with soft hyphens, hanging indents and justification
# ======================================================================================================================

WRAP_README = dd(r'''
    # wrapjust

    Text filling for the man-page generator.

    ## `wrap(text, width, indent="", hanging="", align="left", justify=False) -> list[str]`
    Returns the output lines. `fill(...)` takes the same arguments and returns the lines joined by `"\n"`.

    ### Paragraphs and words
    * Paragraphs are separated by one or more blank lines (lines that are empty or only whitespace). Inside a paragraph all
      whitespace (spaces, tabs, single newlines) separates words. Leading and trailing blank lines are ignored.
      The output has exactly one empty string between two paragraphs. No text (or only whitespace) gives `[]`.
    * `indent` is put in front of the first line of every paragraph, `hanging` in front of every other line. Both
      count toward `width`. The text space of a line is `width - len(prefix)`; if that is below 1 for either prefix,
      `ValueError`. `align` must be `"left"`, `"right"` or `"center"`, else `ValueError`.

    ### Filling (greedy)
    A line holds words separated by exactly one space. Lines are filled greedily with as many words as fit in the
    text space. Inside a word there are *break opportunities*: right after a `-` that has an alphanumeric character
    on both sides, and at each soft hyphen `­` (which is invisible: it is removed from the output unless a line
    is broken there, in which case a `-` is appended to the line piece).
    When the next word does not fit whole on the current line:
    1. the longest prefix of the word that ends at a break opportunity (not the end of the word), including the
       appended `-` for a soft hyphen, and fits in the remaining space (counting the separating space when the line
       already has words) is placed on the line, the line is closed, and the rest of the word goes on;
    2. otherwise, if the line already has words, the line is closed and the word is tried again on a fresh line;
    3. otherwise (empty line, even the shortest piece is too long) the word, soft hyphens removed, is cut after exactly
       as many characters as the text space; the cut piece takes the line, and the rest is handled as a new word.

    ### Alignment
    * `justify=True`: every line of a paragraph except its last, which has at least two words on it, is widened to
      the full text space by spreading extra spaces over the gaps between its words: every gap gets
      `extra // gaps` more spaces and the first `extra % gaps` gaps one more. Other lines (last lines, single-word
      lines) are left-aligned. `align` is ignored.
    * Otherwise `align="right"` right-aligns every line in its text space and `"center"` centres it by putting
      `(space - len(line)) // 2` blanks in front; `"left"` leaves it. Alignment never adds trailing spaces.
    * The prefix (`indent`/`hanging`) always comes first and is never aligned or justified.
''')

WRAP_SRC = dd(r'''
    """Paragraph filling."""

    SOFT = "­"


    def _fragments(word):
        """(text, soft) pieces of a word, each ending at a break opportunity; soft marks a soft-hyphen break."""
        frags = []
        cur = []
        for i, ch in enumerate(word):
            if ch == SOFT:
                if cur:
                    frags.append(("".join(cur), True))
                    cur = []
                continue
            cur.append(ch)
            if ch == "-" and 0 < i < len(word) - 1 and word[i - 1].isalnum() and word[i + 1].isalnum():
                frags.append(("".join(cur), False))
                cur = []
        if cur:
            frags.append(("".join(cur), False))
        if frags and frags[-1][1]:
            frags[-1] = (frags[-1][0], False)
        return frags


    def _layout(words, first_avail, rest_avail):
        lines = []
        cur = []
        cur_len = 0
        avail = first_avail
        for word in words:
            frags = _fragments(word)
            while frags:
                text = "".join(t for t, _ in frags)
                sep = 1 if cur else 0
                if cur_len + sep + len(text) <= avail:
                    cur.append(text)
                    cur_len += sep + len(text)
                    break
                best = None
                acc = ""
                for k in range(len(frags) - 1):
                    acc += frags[k][0]
                    shown = acc + ("-" if frags[k][1] else "")
                    if cur_len + sep + len(shown) <= avail:
                        best = (k, shown)
                if best is not None:
                    cur.append(best[1])
                    frags = frags[best[0] + 1:]
                elif cur:
                    pass
                else:
                    cur.append(text[:avail])
                    frags = _fragments(text[avail:])
                lines.append(cur)
                cur, cur_len, avail = [], 0, rest_avail
        if cur:
            lines.append(cur)
        return lines


    def _render(words, space, justify, align, last):
        text = " ".join(words)
        if justify:
            if last or len(words) < 2:
                return text
            extra = space - len(text)
            gaps = len(words) - 1
            out = []
            for i, w in enumerate(words[:-1]):
                out.append(w + " " * (1 + extra // gaps + (1 if i < extra % gaps else 0)))
            return "".join(out) + words[-1]
        if align == "right":
            return " " * (space - len(text)) + text
        if align == "center":
            return " " * ((space - len(text)) // 2) + text
        return text


    def wrap(text, width, indent="", hanging="", align="left", justify=False):
        if align not in ("left", "right", "center"):
            raise ValueError("bad align: %r" % align)
        first_avail, rest_avail = width - len(indent), width - len(hanging)
        if first_avail < 1 or rest_avail < 1:
            raise ValueError("width too small for the indents")
        paragraphs = []
        block = []
        for line in text.split("\n"):
            if line.strip():
                block.append(line)
            elif block:
                paragraphs.append(" ".join(block))
                block = []
        if block:
            paragraphs.append(" ".join(block))
        out = []
        for p, para in enumerate(paragraphs):
            if p:
                out.append("")
            lines = _layout(para.split(), first_avail, rest_avail)
            for i, words in enumerate(lines):
                prefix = indent if i == 0 else hanging
                out.append(prefix + _render(words, width - len(prefix), justify, align, i == len(lines) - 1))
        return out


    def fill(text, width, **kw):
        return "\n".join(wrap(text, width, **kw))
''')

WRAP_VISIBLE = dd(r'''
    import unittest

    from wrapjust import fill, wrap


    class BasicTests(unittest.TestCase):
        def test_simple(self):
            self.assertEqual(wrap("the quick brown fox jumps", 10), ["the quick", "brown fox", "jumps"])

        def test_paragraphs(self):
            self.assertEqual(wrap("a b\n\nc d", 10), ["a b", "", "c d"])

        def test_fill(self):
            self.assertEqual(fill("aa bb cc", 5), "aa bb\ncc")


    if __name__ == "__main__":
        unittest.main()
''')

WRAP_HIDDEN = dd(r'''
    import unittest

    from wrapjust import fill, wrap

    S = "­"


    class Basics(unittest.TestCase):
        def test_exact_fit_and_overflow(self):
            self.assertEqual(wrap("aaa bbb ccc", 7), ["aaa bbb", "ccc"])
            self.assertEqual(wrap("aaa bbb ccc", 6), ["aaa", "bbb", "ccc"])
            self.assertEqual(wrap("aaa bbb ccc", 11), ["aaa bbb ccc"])
            self.assertEqual(wrap("aaa bbb ccc", 100), ["aaa bbb ccc"])

        def test_whitespace_collapsed(self):
            self.assertEqual(wrap("  aa \t bb\n cc   dd  ", 20), ["aa bb cc dd"])

        def test_empty(self):
            self.assertEqual(wrap("", 10), [])
            self.assertEqual(wrap("  \n \n\t", 10), [])
            self.assertEqual(wrap("\n\n", 10, indent="> "), [])

        def test_paragraphs(self):
            self.assertEqual(wrap("a b\n\n\n  \nc d", 10), ["a b", "", "c d"])
            self.assertEqual(wrap("\n\na b\nc\n\n", 10), ["a b c"])
            self.assertEqual(wrap("one\ntwo\n\nthree", 5), ["one", "two", "", "three"])
            self.assertEqual(wrap("x\n\ny\n\nz", 5), ["x", "", "y", "", "z"])

        def test_fill_joins_lines(self):
            self.assertEqual(fill("aaa bbb ccc", 7), "aaa bbb\nccc")
            self.assertEqual(fill("a\n\nb", 5), "a\n\nb")
            self.assertEqual(fill("", 5), "")

        def test_width_errors(self):
            with self.assertRaises(ValueError):
                wrap("a", 0)
            with self.assertRaises(ValueError):
                wrap("a", 3, indent="   ")
            with self.assertRaises(ValueError):
                wrap("a", 3, hanging="   ")
            with self.assertRaises(ValueError):
                wrap("a", 5, align="middle")
            self.assertEqual(wrap("a", 4, indent="   "), ["   a"])
            self.assertEqual(wrap("ab", 4, indent="   "), ["   a", "b"])


    class Indents(unittest.TestCase):
        def test_indent_and_hanging(self):
            self.assertEqual(wrap("aaa bbb ccc ddd", 9, indent="* ", hanging="  "), ["* aaa bbb", "  ccc ddd"])

        def test_prefix_counts_toward_width(self):
            self.assertEqual(wrap("aaa bbb ccc ddd", 8, indent="* ", hanging="  "), ["* aaa", "  bbb", "  ccc", "  ddd"])
            self.assertEqual(wrap("aa bb cc", 8, indent="> "), ["> aa bb", "cc"])
            self.assertEqual(wrap("aa bb cc dd", 8, hanging="    "), ["aa bb cc", "    dd"])

        def test_each_paragraph_restarts(self):
            self.assertEqual(wrap("aa bb\n\ncc dd", 6, indent="- ", hanging="  "), ["- aa", "  bb", "", "- cc", "  dd"])

        def test_different_widths_per_line(self):
            self.assertEqual(wrap("aaaa bbbb cccc dddd", 12, indent="1234567 ", hanging=""), ["1234567 aaaa", "bbbb cccc", "dddd"])
            self.assertEqual(wrap("aaaa bbbb cccc dddd", 12, indent="", hanging="1234567 "), ["aaaa bbbb", "1234567 cccc", "1234567 dddd"])


    class Hyphens(unittest.TestCase):
        def test_break_after_real_hyphen(self):
            self.assertEqual(wrap("a well-known fact", 10), ["a well-", "known fact"])
            self.assertEqual(wrap("a well-known fact", 8), ["a well-", "known", "fact"])

        def test_hyphen_needs_alnum_both_sides(self):
            self.assertEqual(wrap("aaa -bbbbbb", 6), ["aaa", "-bbbbb", "b"])
            self.assertEqual(wrap("aaa bbbbbb- c", 6), ["aaa", "bbbbbb", "- c"])
            self.assertEqual(wrap("aaa b--c", 6), ["aaa", "b--c"])
            self.assertEqual(wrap("aa --x--- b", 5), ["aa", "--x--", "- b"])

        def test_longest_prefix_wins(self):
            self.assertEqual(wrap("x aa-bb-cc", 8), ["x aa-bb-", "cc"])
            self.assertEqual(wrap("x aa-bb-cc", 7), ["x aa-", "bb-cc"])
            self.assertEqual(wrap("x aa-bb-cc", 6), ["x aa-", "bb-cc"])
            self.assertEqual(wrap("x aa-bb-cc", 5), ["x aa-", "bb-cc"])

        def test_prefix_on_empty_line(self):
            self.assertEqual(wrap("aa-bb-cc", 6), ["aa-bb-", "cc"])
            self.assertEqual(wrap("aa-bb-cc", 5), ["aa-", "bb-cc"])
            self.assertEqual(wrap("aa-bb-cc", 3), ["aa-", "bb-", "cc"])

        def test_whole_word_preferred(self):
            self.assertEqual(wrap("aa-bb cc", 5), ["aa-bb", "cc"])

        def test_soft_hyphen_unused_is_removed(self):
            self.assertEqual(wrap("co" + S + "op" + S + "erate", 20), ["cooperate"])
            self.assertEqual(wrap("a" + S + "b", 5), ["ab"])

        def test_soft_hyphen_break_adds_hyphen(self):
            self.assertEqual(wrap("go co" + S + "operate", 8), ["go co-", "operate"])
            self.assertEqual(wrap("x ab" + S + "cd" + S + "ef", 6), ["x ab-", "cdef"])
            self.assertEqual(wrap("x ab" + S + "cd" + S + "ef", 7), ["x abcd-", "ef"])
            self.assertEqual(wrap("x ab" + S + "cd" + S + "ef", 8), ["x abcdef"])

        def test_soft_hyphen_hyphen_counts_toward_width(self):
            self.assertEqual(wrap("ab" + S + "cd", 3), ["ab-", "cd"])
            self.assertEqual(wrap("ab" + S + "cd", 2), ["ab", "cd"])
            self.assertEqual(wrap("xx ab" + S + "cd", 6), ["xx ab-", "cd"])
            self.assertEqual(wrap("xx ab" + S + "cd", 5), ["xx", "abcd"])

        def test_soft_hyphen_edges_ignored(self):
            self.assertEqual(wrap(S + "abc" + S, 10), ["abc"])
            self.assertEqual(wrap("abc" + S + " def", 10), ["abc def"])
            self.assertEqual(wrap("abc" + S + " def", 3), ["abc", "def"])

        def test_mixed_hyphen_kinds(self):
            self.assertEqual(wrap("ab" + S + "cd-ef", 4), ["ab-", "cd-", "ef"])
            self.assertEqual(wrap("ab" + S + "cd-ef", 5), ["abcd-", "ef"])
            self.assertEqual(wrap("ab" + S + "cd-ef", 7), ["abcd-ef"])


    class HardSplit(unittest.TestCase):
        def test_long_word_is_cut(self):
            self.assertEqual(wrap("abcdefghij", 4), ["abcd", "efgh", "ij"])
            self.assertEqual(wrap("abcdefgh", 4), ["abcd", "efgh"])
            self.assertEqual(wrap("abcdefghi", 4), ["abcd", "efgh", "i"])

        def test_cut_after_closing_line(self):
            self.assertEqual(wrap("ab cdefghij", 4), ["ab", "cdef", "ghij"])
            self.assertEqual(wrap("ab cd efghijk", 5), ["ab cd", "efghi", "jk"])

        def test_cut_uses_line_width_with_prefix(self):
            self.assertEqual(wrap("abcdefgh", 5, indent="> ", hanging="  "), ["> abc", "  def", "  gh"])

        def test_cut_removes_soft_hyphens(self):
            self.assertEqual(wrap("abc" + S + "defgh", 2), ["ab", "cd", "ef", "gh"])

        def test_cut_remainder_can_still_break_at_hyphens(self):
            self.assertEqual(wrap("abcdefg-hi", 5), ["abcde", "fg-hi"])
            self.assertEqual(wrap("abcdefg-hijk", 5), ["abcde", "fg-", "hijk"])


    class Alignment(unittest.TestCase):
        def test_right_and_center(self):
            self.assertEqual(wrap("aa bbbb c", 6, align="right"), ["    aa", "bbbb c"])
            self.assertEqual(wrap("ab cdef", 6, align="right"), ["    ab", "  cdef"])
            self.assertEqual(wrap("ab cdef", 6, align="center"), ["  ab", " cdef"])
            self.assertEqual(wrap("abc", 7, align="center"), ["  abc"])
            self.assertEqual(wrap("abcd", 7, align="center"), [" abcd"])
            self.assertEqual(wrap("abc", 3, align="center"), ["abc"])
            self.assertEqual(wrap("abc", 3, align="right"), ["abc"])

        def test_prefix_not_aligned(self):
            self.assertEqual(wrap("ab cdef", 8, indent="> ", hanging="| ", align="right"), [">     ab", "|   cdef"])
            self.assertEqual(wrap("ab cdef", 8, indent="> ", hanging="| ", align="center"), ["> " + " " * 2 + "ab", "| " + " " + "cdef"])
            self.assertEqual(wrap("ab cdef", 9, indent="> ", hanging="| ", align="right"), ["> ab cdef"])

        def test_no_trailing_spaces(self):
            for align in ("left", "right", "center"):
                for line in wrap("aa bb cc dd ee ff gg", 7, align=align):
                    self.assertEqual(line, line.rstrip())

        def test_left_is_default(self):
            self.assertEqual(wrap("aa bb", 10), wrap("aa bb", 10, align="left"))


    class Justify(unittest.TestCase):
        def test_distribution(self):
            self.assertEqual(wrap("aa bb cc dd", 8, justify=True), ["aa bb cc", "dd"])
            self.assertEqual(wrap("a b c dd e", 7, justify=True), ["a  b  c", "dd e"])
            self.assertEqual(wrap("aa bb cc dd", 10, justify=True), ["aa  bb  cc", "dd"])

        def test_remainder_goes_to_leftmost_gaps(self):
            self.assertEqual(wrap("a b c dd e", 6, justify=True), ["a  b c", "dd e"])
            self.assertEqual(wrap("aa bb cc dd ee", 12, justify=True), ["aa  bb cc dd", "ee"])
            self.assertEqual(wrap("a b c d eee", 10, justify=True), ["a  b  c  d", "eee"])
            self.assertEqual(wrap("a bb c d eee", 10, justify=True), ["a  bb  c d", "eee"])

        def test_last_and_single_word_lines_untouched(self):
            self.assertEqual(wrap("aa bb cc", 5, justify=True), ["aa bb", "cc"])
            self.assertEqual(wrap("abcdefgh ij", 9, justify=True), ["abcdefgh", "ij"])
            self.assertEqual(wrap("short", 20, justify=True), ["short"])

        def test_exact_fit_line_unchanged(self):
            self.assertEqual(wrap("aa bb cc dd", 5, justify=True), ["aa bb", "cc dd"])

        def test_every_paragraph_has_its_own_last_line(self):
            self.assertEqual(wrap("aa bb cc\n\ndd ee ff", 5, justify=True), ["aa bb", "cc", "", "dd ee", "ff"])
            self.assertEqual(wrap("a b c d\n\ne f", 5, justify=True), ["a b c", "d", "", "e f"])

        def test_justify_with_prefix(self):
            self.assertEqual(wrap("aa bb cc dd ee", 9, indent="> ", hanging="  ", justify=True), ["> aa   bb", "  cc   dd", "  ee"])
            self.assertEqual(wrap("a b c d e f g", 10, indent="* ", hanging="  ", justify=True), ["* a  b c d", "  e f g"])

        def test_justify_ignores_align(self):
            self.assertEqual(wrap("a b c d", 5, justify=True, align="right"), wrap("a b c d", 5, justify=True))

        def test_justified_line_is_full_width(self):
            text = "the quick brown fox jumps over the lazy dog and keeps running far away"
            for width in (12, 15, 20, 27):
                lines = wrap(text, width, justify=True)
                for ln in lines[:-1]:
                    if " " in ln:
                        self.assertEqual(len(ln), width)
                self.assertEqual(" ".join(" ".join(lines).split()), text)

        def test_broken_word_piece_line_is_justified_by_gaps_only(self):
            self.assertEqual(wrap("a b aa-bb-cc", 9, justify=True), ["a  b  aa-", "bb-cc"])


    if __name__ == "__main__":
        unittest.main()
''')

WRAP = Lib(
    name="wrapjust", lang="python", title="the text filler (`wrapjust.py`)",
    blurb="The man-page generator uses this module to fill paragraphs to a fixed width.",
    files={"wrapjust.py": WRAP_SRC, "README.md": WRAP_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": WRAP_VISIBLE},
    hidden_tests={"tests/test_full.py": WRAP_HIDDEN},
    mutate=["wrapjust.py"], difficulty=4, tags=["text", "layout"],
    probes=[
        'wrap("aaa bbb ccc", 7)',
        'wrap("a well-known fact", 10)',
        'wrap("go co\\u00adoperate", 8)',
        'wrap("abcdefghij", 4)',
        'wrap("aa bb cc dd ee", 9, indent="> ", hanging="  ", justify=True)',
        'wrap("a b c dd e", 8, justify=True)',
        'wrap("ab cdef", 7, align="right")',
        'wrap("ab cdef", 7, align="center")',
        'wrap("aa bb\\n\\ncc dd", 6, indent="- ", hanging="  ")',
        'wrap("abcdefg-hijk", 5)',
    ],
    probe_import="from wrapjust import *",
)


# ======================================================================================================================
# gridrender: aligned plain-text tables (render and parse back)
# ======================================================================================================================

GRID_README = dd(r'''
    # gridrender

    Aligned plain-text tables for the ops console. Two modules: `gridrender.width` (display widths and fitting) and
    `gridrender.table` (render and parse).

    ## `gridrender.width`
    ### `dwidth(text) -> int`
    Display width in terminal cells: combining marks (`unicodedata.combining(ch) != 0`) count 0, characters whose
    `unicodedata.east_asian_width` is `W` or `F` count 2, all others 1.

    ### `fit(text, width) -> str`
    `text` if its `dwidth` is at most `width`. Otherwise the longest prefix whose `dwidth` is at most `width - 1`,
    followed by `…` (one cell). `width < 1` is a `ValueError`.

    ## `gridrender.table`
    ### `render_table(rows, header=None, align="", max_width=None, gap=2) -> str`
    * `rows` is a list of sequences; every cell is turned into text with `str()` (`None` becomes `""`). Every row (and the
      header) must have the same number of cells, else `ValueError`. No header and no rows give `""`.
    * Column width: the largest `dwidth` among header and cells, but at least 1.
    * `align` has one letter per column: `l` left, `r` right, `c` centre (extra cells split `pad // 2` before, the rest
      after). Missing letters default to `l`; more letters than columns or any other letter is a `ValueError`.
    * `max_width`: if the table (widths plus `gap` between columns) is wider than `max_width`, repeatedly take the widest column
      (on a tie the rightmost) among those wider than 3 and shrink it by one, until the table fits. When no column
      can shrink any more and it is still too wide: `ValueError`. Cells wider than their column are cut with `fit`.
    * Lines: with a header, the header line, then a rule line of `-` repeated to each column's width, then the rows.
      Cells are padded to the column width (by `dwidth`) according to the alignment and joined by `gap` spaces. Every line
      has its trailing whitespace removed. Lines are joined by `"\n"` without a final newline.

    ### `parse_table(text) -> list[dict]`
    Reads what `render_table` writes (with a header). The first non-blank line is the header and the next line is the
    rule: it may consist only of `-` and spaces and must contain at least one `-`, else `ValueError`. Each run of `-`
    in the rule starts a column; column *i* covers the character positions from the start of its run up to the start of the next
    run, the last column up to the end of the line. Header cells and row cells are those slices stripped. Header names must be
    non-empty and unique (`ValueError`). Every later non-blank line is a row: a dict from header name to cell text (a line that
    is too short gives `""` for the missing cells). Blank lines are skipped. Positions are counted in characters.
''')

GRID_WIDTH = dd(r'''
    """Display widths."""
    import unicodedata


    def dwidth(text):
        w = 0
        for ch in text:
            if unicodedata.combining(ch):
                continue
            w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        return w


    def fit(text, width):
        if width < 1:
            raise ValueError("width must be at least 1")
        if dwidth(text) <= width:
            return text
        out = []
        used = 0
        for ch in text:
            cw = dwidth(ch)
            if used + cw > width - 1:
                break
            out.append(ch)
            used += cw
        return "".join(out) + "…"
''')

GRID_TABLE = dd(r'''
    """Render and parse aligned tables."""
    import re

    from .width import dwidth, fit


    def _pad(text, width, how):
        pad = width - dwidth(text)
        if how == "r":
            return " " * pad + text
        if how == "c":
            return " " * (pad // 2) + text + " " * (pad - pad // 2)
        return text + " " * pad


    def render_table(rows, header=None, align="", max_width=None, gap=2):
        grid = [["" if c is None else str(c) for c in row] for row in rows]
        head = None if header is None else ["" if c is None else str(c) for c in header]
        everything = ([head] if head is not None else []) + grid
        if not everything:
            return ""
        ncols = len(everything[0])
        if any(len(r) != ncols for r in everything):
            raise ValueError("rows have different lengths")
        if len(align) > ncols or any(a not in "lrc" for a in align):
            raise ValueError("bad align: %r" % align)
        align = align + "l" * (ncols - len(align))
        widths = [max([1] + [dwidth(r[i]) for r in everything]) for i in range(ncols)]
        if max_width is not None:
            while sum(widths) + gap * (ncols - 1) > max_width:
                cand = [i for i, w in enumerate(widths) if w > 3]
                if not cand:
                    raise ValueError("cannot fit the table into %d cells" % max_width)
                i = max(cand, key=lambda k: (widths[k], k))
                widths[i] -= 1
        sep = " " * gap

        def line(cells):
            return sep.join(_pad(fit(c, widths[i]), widths[i], align[i]) for i, c in enumerate(cells)).rstrip()

        out = []
        if head is not None:
            out.append(line(head))
            out.append(sep.join("-" * w for w in widths))
        out.extend(line(r) for r in grid)
        return "\n".join(out)


    def parse_table(text):
        lines = [ln for ln in text.splitlines()]
        while lines and not lines[0].strip():
            lines.pop(0)
        if len(lines) < 2:
            raise ValueError("need a header and a rule line")
        head, rule = lines[0], lines[1]
        if not re.fullmatch(r"[- ]*-[- ]*", rule):
            raise ValueError("second line is not a rule")
        starts = [m.start() for m in re.finditer(r"-+", rule)]
        spans = [(s, starts[i + 1] if i + 1 < len(starts) else None) for i, s in enumerate(starts)]

        def cells(ln):
            return [ln[a:b].strip() for a, b in spans]

        names = cells(head)
        if any(not n for n in names) or len(set(names)) != len(names):
            raise ValueError("header names must be non-empty and unique")
        return [dict(zip(names, cells(ln))) for ln in lines[2:] if ln.strip()]
''')

GRID_VISIBLE = dd(r'''
    import unittest

    from gridrender.table import render_table
    from gridrender.width import dwidth


    class BasicTests(unittest.TestCase):
        def test_dwidth(self):
            self.assertEqual(dwidth("abc"), 3)

        def test_render(self):
            out = render_table([["apple", 3], ["fig", 12]], header=["name", "qty"], align="lr")
            self.assertEqual(out, "name   qty\n-----  ---\napple    3\nfig     12")


    if __name__ == "__main__":
        unittest.main()
''')

GRID_HIDDEN = dd(r'''
    import unittest

    from gridrender.table import parse_table, render_table
    from gridrender.width import dwidth, fit


    class Width(unittest.TestCase):
        def test_dwidth(self):
            self.assertEqual(dwidth(""), 0)
            self.assertEqual(dwidth("hello"), 5)
            self.assertEqual(dwidth("你好"), 4)
            self.assertEqual(dwidth("a你b"), 4)
            self.assertEqual(dwidth("é"), 1)
            self.assertEqual(dwidth("Ａ"), 2)
            self.assertEqual(dwidth("é"), 1)
            self.assertEqual(dwidth("カタ"), 4)

        def test_fit_no_change(self):
            self.assertEqual(fit("abc", 3), "abc")
            self.assertEqual(fit("abc", 10), "abc")
            self.assertEqual(fit("", 1), "")

        def test_fit_cuts(self):
            self.assertEqual(fit("abcdef", 4), "abc…")
            self.assertEqual(fit("abcdef", 5), "abcd…")
            self.assertEqual(fit("abcdef", 1), "…")
            self.assertEqual(fit("abcd", 3), "ab…")

        def test_fit_wide(self):
            self.assertEqual(fit("你好世界", 8), "你好世界")
            self.assertEqual(fit("你好世界", 7), "你好世…")
            self.assertEqual(fit("你好世界", 6), "你好…")
            self.assertEqual(fit("你好世界", 4), "你…")
            self.assertEqual(fit("你好世界", 2), "…")
            self.assertEqual(fit("a你好", 4), "a你…")
            self.assertEqual(fit("ab你", 3), "ab…")

        def test_fit_bad_width(self):
            for w in (0, -1):
                with self.assertRaises(ValueError):
                    fit("abc", w)


    class Render(unittest.TestCase):
        def test_header_and_rule(self):
            out = render_table([["apple", 3], ["fig", 12]], header=["name", "qty"])
            self.assertEqual(out, "name   qty\n-----  ---\napple  3\nfig    12")

        def test_widths_from_header_and_cells(self):
            out = render_table([["a", "b"]], header=["long header", "x"])
            self.assertEqual(out, "long header  x\n-----------  -\na            b")

        def test_alignments(self):
            rows = [["a", "bb", "ccc"], ["dddd", "e", "f"]]
            self.assertEqual(render_table(rows, align="lrc"), "a     bb  ccc\ndddd   e   f")
            self.assertEqual(render_table(rows, align="rcl"), "   a  bb  ccc\ndddd  e   f")

        def test_centre_split(self):
            self.assertEqual(render_table([["abcd"], ["x"]], align="c"), "abcd\n x")
            self.assertEqual(render_table([["abcde"], ["xy"]], align="c"), "abcde\n xy")
            self.assertEqual(render_table([["abcdef"], ["x"]], align="c"), "abcdef\n  x")

        def test_align_defaults_and_errors(self):
            rows = [["a", "b", "c"], ["dd", "ee", "ff"]]
            self.assertEqual(render_table(rows, align="r"), " a  b   c\ndd  ee  ff")
            for bad in ("lrcl", "x", "lL", "l-"):
                with self.assertRaises(ValueError, msg=bad):
                    render_table(rows, align=bad)

        def test_gap(self):
            out = render_table([["a", "b"], ["cc", "d"]], gap=1)
            self.assertEqual(out, "a  b\ncc d")
            out = render_table([["a", "b"], ["cc", "d"]], header=["h1", "h2"], gap=4)
            self.assertEqual(out, "h1    h2\n--    --\na     b\ncc    d")
            self.assertEqual(render_table([["a", "b"]], gap=0), "ab")

        def test_trailing_whitespace_removed(self):
            out = render_table([["a", ""], ["b", "c"]], header=["x", "y"])
            for ln in out.split("\n"):
                self.assertEqual(ln, ln.rstrip())
            self.assertEqual(out, "x  y\n-  -\na\nb  c")

        def test_none_and_str(self):
            self.assertEqual(render_table([[None, 1.5, True]]), "   1.5  True")
            self.assertEqual(render_table([[None, "x"]], header=["a", "b"]), "a  b\n-  -\n   x")

        def test_min_width_one(self):
            self.assertEqual(render_table([["", "x"]], header=["", ""]), "\n-  -\n   x")

        def test_no_rows(self):
            self.assertEqual(render_table([], header=["a", "bb"]), "a  bb\n-  --")
            self.assertEqual(render_table([]), "")

        def test_no_header_no_rule(self):
            self.assertEqual(render_table([["a", "b"]]), "a  b")

        def test_ragged_rejected(self):
            with self.assertRaises(ValueError):
                render_table([["a", "b"], ["c"]])
            with self.assertRaises(ValueError):
                render_table([["a", "b"]], header=["x"])

        def test_wide_characters_pad_by_display_width(self):
            out = render_table([["你好", "x"], ["ab", "y"]], header=["name", "k"])
            self.assertEqual(out, "name  k\n----  -\n你好  x\nab    y")
            out = render_table([["你", "x"], ["abc", "y"]], align="rl")
            self.assertEqual(out, " 你  x\nabc  y")

        def test_max_width_shrinks_widest_rightmost(self):
            rows = [["abcdef", "abcdef", "ab"]]
            self.assertEqual(render_table(rows, max_width=20), "abcdef  abcdef  ab")
            self.assertEqual(render_table(rows, max_width=17), "abcdef  abcd…  ab")
            self.assertEqual(render_table(rows, max_width=16), "abcd…  abcd…  ab")
            self.assertEqual(render_table(rows, max_width=15), "abcd…  abc…  ab")
            self.assertEqual(render_table(rows, max_width=14), "abc…  abc…  ab")

        def test_max_width_exact_and_gap(self):
            rows = [["abcdef", "abcdef"]]
            self.assertEqual(render_table(rows, max_width=14), "abcdef  abcdef")
            self.assertEqual(render_table(rows, max_width=13), "abcdef  abcd…")
            self.assertEqual(render_table(rows, max_width=13, gap=1), "abcdef abcdef")
            self.assertEqual(render_table(rows, max_width=12, gap=1), "abcdef abcd…")

        def test_max_width_applies_to_header_widths_too(self):
            out = render_table([["x", "y"]], header=["averyverylongname", "k"], max_width=10)
            self.assertEqual(out, "averyv…  k\n-------  -\nx        y")

        def test_min_column_width_three(self):
            rows = [["abcdef", "abcdef"]]
            self.assertEqual(render_table(rows, max_width=8), "ab…  ab…")
            with self.assertRaises(ValueError):
                render_table(rows, max_width=7)

        def test_max_width_impossible(self):
            with self.assertRaises(ValueError):
                render_table([["a", "b", "c"]], max_width=3)
            self.assertEqual(render_table([["a", "b", "c"]], max_width=7), "a  b  c")

        def test_max_width_truncates_wide_cells_by_display_width(self):
            out = render_table([["你好世界", "x"]], max_width=8, gap=1)
            self.assertEqual(out, "你好…  x")


    class Parse(unittest.TestCase):
        T = "name   qty  price\n-----  ---  -----\napple    3   1.20\nfig     12  10.00\n"

        def test_basic(self):
            self.assertEqual(parse_table(self.T), [{"name": "apple", "qty": "3", "price": "1.20"}, {"name": "fig", "qty": "12", "price": "10.00"}])

        def test_leading_blank_and_blank_rows(self):
            got = parse_table("\n\n" + self.T.replace("fig", "\nfig"))
            self.assertEqual([r["name"] for r in got], ["apple", "fig"])

        def test_short_rows(self):
            got = parse_table("a  b  c\n-  -  -\nx\ny  z\n")
            self.assertEqual(got, [{"a": "x", "b": "", "c": ""}, {"a": "y", "b": "z", "c": ""}])

        def test_last_column_extends_to_line_end(self):
            got = parse_table("k  note\n-  ----\n1  a much longer note than the header\n")
            self.assertEqual(got, [{"k": "1", "note": "a much longer note than the header"}])

        def test_cells_span_to_next_column_start(self):
            got = parse_table("a    b\n---  --\nxx   yy\n")
            self.assertEqual(got, [{"a": "xx", "b": "yy"}])
            got = parse_table("a    b\n---  --\nxxxxyyy\n")
            self.assertEqual(got, [{"a": "xxxxy", "b": "yy"}])

        def test_values_with_inner_spaces(self):
            got = parse_table("name       city\n---------  --------\nAda King   New York\n")
            self.assertEqual(got, [{"name": "Ada King", "city": "New York"}])

        def test_rule_with_extra_spaces(self):
            got = parse_table(" a  b\n -  -\n x  y\n")
            self.assertEqual(got, [{"a": "x", "b": "y"}])

        def test_header_only(self):
            self.assertEqual(parse_table("a  b\n-  -\n"), [])

        def test_errors(self):
            for text in ("", "a  b\n", "a  b\nxx yy\n", "a  b\n   \n", "a  a\n-  -\n", "a  \n-  -\n1  2\n", "\n\n"):
                with self.assertRaises(ValueError, msg=repr(text)):
                    parse_table(text)

        def test_round_trip(self):
            rows = [["apple", "3", "1.20"], ["fig and kiwi", "12", "10.00"], ["", "7", ""]]
            text = render_table(rows, header=["name", "qty", "price"], align="lrr")
            got = parse_table(text)
            self.assertEqual([[r["name"], r["qty"], r["price"]] for r in got], rows)


    if __name__ == "__main__":
        unittest.main()
''')

GRID = Lib(
    name="gridrender", lang="python", title="the plain-text table package (`gridrender/`)",
    blurb="The ops console prints and re-reads aligned text tables with this package.",
    files={"gridrender/__init__.py": "", "gridrender/width.py": GRID_WIDTH, "gridrender/table.py": GRID_TABLE,
           "README.md": GRID_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": GRID_VISIBLE},
    hidden_tests={"tests/test_full.py": GRID_HIDDEN},
    mutate=["gridrender/width.py", "gridrender/table.py"], difficulty=3, tags=["text", "layout"],
    probes=[
        'dwidth("a\你e\́")',
        'fit("\你\好\世\界", 7)',
        'fit("abcdef", 4)',
        'render_table([["a", "bb", "ccc"], ["dddd", "e", "f"]], align="rcl")',
        'render_table([["abcd"], ["x"]], align="c")',
        'render_table([["abcdef", "abcdef", "ab"]], max_width=16)',
        'render_table([["abcdef", "abcdef"]], max_width=13, gap=1)',
        'render_table([["\你\好", "x"], ["ab", "y"]], header=["name", "k"])',
        'render_table([[None, "x"]], header=["a", "b"])',
        'parse_table("a    b\\n---  --\\nxx   yy\\nz\\n")',
        'parse_table("k  note\\n-  ----\\n1  a much longer note\\n")',
    ],
    probe_import="from gridrender.width import *\nfrom gridrender.table import *",
)


# ======================================================================================================================
# ansispan: ANSI escape handling (strip, style spans, truncation that keeps styles)
# ======================================================================================================================

ANSI_README = dd(r'''
    # ansispan

    Helpers for the log pager to handle terminal escape sequences. `ESC` is `\x1b`.

    ## Escape sequences
    A sequence is one of:
    * CSI: `ESC [`, parameter bytes `0-9 : ; < = > ?`, intermediate bytes (space to `/`), one final byte `@` to `~`;
    * OSC: `ESC ]`, any text without `BEL` or `ESC`, ended by `BEL` or by `ESC \`;
    * two-byte: `ESC` followed by one of `@ A-Z \ ^ _`.
    An `ESC` that does not start a complete sequence is an ordinary character (it is visible text).

    ### `strip(text) -> str`
    `text` with every sequence removed.

    ### `visible_len(text) -> int`
    The number of characters left after `strip` (not display cells).

    ## Styles
    SGR sequences (a CSI with final byte `m`, no intermediate bytes, and only digits and `;` as parameters) change the
    current style; a CSI `m` with any other parameter byte, and all other sequences, do not touch it. The parameters are
    separated by `;`, an empty parameter counts as `0`, and no parameters at all is `[0]`. They are applied left to right:

    | code | effect |
    |---|---|
    | `0` | reset everything |
    | `1` bold, `2` dim, `3` italic, `4` underline | set the attribute |
    | `22` | clear bold **and** dim; `23` clear italic; `24` clear underline |
    | `30`-`37` | foreground colour `black red green yellow blue magenta cyan white` |
    | `90`-`97` | foreground `bright-black` ... `bright-white` |
    | `38;5;N` / `38;2;R;G;B` | foreground `256:N` / `rgb:R,G,B` (the numbers as given) |
    | `39` | default foreground |
    | `40`-`47`, `100`-`107`, `48;...`, `49` | the same for the background |
    Anything else is ignored. A `38`/`48` with too few parameters following it (`38;5` alone, `38;2;1;2`) or with a
    mode other than `5`/`2` ends the processing of that sequence: the rest of its parameters are ignored.

    ### `spans(text) -> list[(style, str)]`
    The visible text split by style. `style` is a tuple of strings for the active attributes in this order: `bold`, `dim`,
    `italic`, `underline`, `fg=<colour>`, `bg=<colour>` (an unstyled run has `()`). Empty runs are not listed and adjacent
    runs with equal style are merged, so a style change that happens without text in between leaves no trace.

    ### `normalize(text) -> str`
    Rewrites `text` canonically: for every span with a non-empty style `ESC[` + the codes joined by `;` + `m`, the text,
    `ESC[0m`; unstyled spans are written as is. The codes are, in the order of the style tuple: `1`, `2`, `3`, `4`,
    then the foreground (`30`-`37`, `90`-`97`, `38;5;N`, `38;2;R;G;B`), then the background (`40`-`47`, `100`-`107`,
    `48;5;N`, `48;2;R;G;B`). All other sequences disappear.

    ### `truncate(text, width) -> str`
    `width < 0` is a `ValueError`. If `visible_len(text) <= width` the text is returned unchanged. Otherwise the result holds
    the first `width` visible characters together with every sequence that occurs before the `width`-th visible
    character is written (sequences after it are dropped); if the style in force at the cut is not the default, `ESC[0m` is
    appended. `width == 0` gives `""`.
''')

ANSI_SRC = dd(r'''
    """ANSI escape handling."""
    import re

    _CSI = r"\x1b\[[0-?]*[ -/]*[@-~]"
    _OSC = r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    _TWO = r"\x1b[@-Z\\^_]"
    _ANY = re.compile("%s|%s|%s" % (_CSI, _OSC, _TWO))
    _SGR = re.compile(r"\x1b\[([0-9;]*)m")

    _NAMES = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]


    def _tokens(text):
        out = []
        pos = 0
        for m in _ANY.finditer(text):
            if m.start() > pos:
                out.append(("text", text[pos:m.start()]))
            out.append(("esc", m.group()))
            pos = m.end()
        if pos < len(text):
            out.append(("text", text[pos:]))
        return out


    def strip(text):
        return "".join(t for kind, t in _tokens(text) if kind == "text")


    def visible_len(text):
        return len(strip(text))


    def _extended(params, i):
        """params[i] is 38 or 48. Returns (colour or None, next index)."""
        if i + 1 < len(params) and params[i + 1] == 5 and i + 2 < len(params):
            return "256:%d" % params[i + 2], i + 3
        if i + 1 < len(params) and params[i + 1] == 2 and i + 4 < len(params):
            return "rgb:%d,%d,%d" % tuple(params[i + 2:i + 5]), i + 5
        return None, len(params)


    def _apply(state, seq):
        m = _SGR.fullmatch(seq)
        if not m:
            return state
        params = [int(p) if p else 0 for p in m.group(1).split(";")]
        state = dict(state)
        i = 0
        while i < len(params):
            p = params[i]
            i += 1
            if p == 0:
                state = {}
            elif p in (1, 2, 3, 4):
                state[("bold", "dim", "italic", "underline")[p - 1]] = True
            elif p == 22:
                state.pop("bold", None)
                state.pop("dim", None)
            elif p == 23:
                state.pop("italic", None)
            elif p == 24:
                state.pop("underline", None)
            elif 30 <= p <= 37:
                state["fg"] = _NAMES[p - 30]
            elif 90 <= p <= 97:
                state["fg"] = "bright-" + _NAMES[p - 90]
            elif 40 <= p <= 47:
                state["bg"] = _NAMES[p - 40]
            elif 100 <= p <= 107:
                state["bg"] = "bright-" + _NAMES[p - 100]
            elif p == 39:
                state.pop("fg", None)
            elif p == 49:
                state.pop("bg", None)
            elif p in (38, 48):
                colour, i = _extended(params, i - 1)
                if colour is not None:
                    state["fg" if p == 38 else "bg"] = colour
        return state


    def _style(state):
        out = [k for k in ("bold", "dim", "italic", "underline") if state.get(k)]
        for k in ("fg", "bg"):
            if k in state:
                out.append("%s=%s" % (k, state[k]))
        return tuple(out)


    def spans(text):
        out = []
        state = {}
        for kind, t in _tokens(text):
            if kind == "esc":
                state = _apply(state, t)
            elif t:
                style = _style(state)
                if out and out[-1][0] == style:
                    out[-1] = (style, out[-1][1] + t)
                else:
                    out.append((style, t))
        return out


    def _codes(style):
        codes = []
        for item in style:
            if item == "bold":
                codes.append("1")
            elif item == "dim":
                codes.append("2")
            elif item == "italic":
                codes.append("3")
            elif item == "underline":
                codes.append("4")
            else:
                which, _, colour = item.partition("=")
                base = 30 if which == "fg" else 40
                if colour.startswith("256:"):
                    codes.append("%d;5;%s" % (base + 8, colour[4:]))
                elif colour.startswith("rgb:"):
                    codes.append("%d;2;%s" % (base + 8, colour[4:].replace(",", ";")))
                elif colour.startswith("bright-"):
                    codes.append(str(base + 60 + _NAMES.index(colour[7:])))
                else:
                    codes.append(str(base + _NAMES.index(colour)))
        return ";".join(codes)


    def normalize(text):
        out = []
        for style, t in spans(text):
            if style:
                out.append("\x1b[%sm%s\x1b[0m" % (_codes(style), t))
            else:
                out.append(t)
        return "".join(out)


    def truncate(text, width):
        if width < 0:
            raise ValueError("width must not be negative")
        if visible_len(text) <= width:
            return text
        out = []
        state = {}
        left = width
        for kind, t in _tokens(text):
            if left == 0:
                break
            if kind == "esc":
                out.append(t)
                state = _apply(state, t)
            else:
                out.append(t[:left])
                left -= min(left, len(t))
        if _style(state):
            out.append("\x1b[0m")
        return "".join(out)
''')

ANSI_VISIBLE = dd(r'''
    import unittest

    from ansispan import normalize, spans, strip, truncate, visible_len

    E = "\x1b"


    class BasicTests(unittest.TestCase):
        def test_strip(self):
            self.assertEqual(strip(E + "[31mred" + E + "[0m ok"), "red ok")
            self.assertEqual(visible_len(E + "[1mab" + E + "[0m"), 2)

        def test_spans(self):
            self.assertEqual(spans("a" + E + "[1mb"), [((), "a"), (("bold",), "b")])

        def test_truncate_plain(self):
            self.assertEqual(truncate("abcdef", 3), "abc")


    if __name__ == "__main__":
        unittest.main()
''')

ANSI_HIDDEN = dd(r'''
    import unittest

    from ansispan import normalize, spans, strip, truncate, visible_len

    E = "\x1b"


    def sgr(*codes):
        return E + "[" + ";".join(str(c) for c in codes) + "m"


    class Strip(unittest.TestCase):
        def test_csi(self):
            self.assertEqual(strip(E + "[31mred" + E + "[0m"), "red")
            self.assertEqual(strip(E + "[1;4;38;5;208mx" + E + "[m"), "x")
            self.assertEqual(strip("a" + E + "[2Kb" + E + "[10;20Hc" + E + "[?25lD"), "abcD")
            self.assertEqual(strip("a" + E + "[ qb"), "ab")
            self.assertEqual(strip("a" + E + "[<5;1;2Mb"), "ab")

        def test_osc(self):
            self.assertEqual(strip(E + "]0;window title\x07text"), "text")
            self.assertEqual(strip(E + "]8;;http://x" + E + "\\link" + E + "]8;;" + E + "\\"), "link")
            self.assertEqual(strip("a" + E + "]0;t\x07" + "b" + E + "]2;u" + E + "\\c"), "abc")

        def test_two_byte(self):
            self.assertEqual(strip("a" + E + "Mb" + E + "7c" + E + "=d" + E + "Ne"), "a" + "b" + E + "7c" + E + "=d" + "e")
            self.assertEqual(strip("a" + E + "cb"), "a" + E + "cb")
            self.assertEqual(strip("a" + E + "\\b" + E + "^c" + E + "_d"), "abcd")

        def test_incomplete_sequences_are_text(self):
            self.assertEqual(strip("a" + E), "a" + E)
            self.assertEqual(strip("a" + E + "[31"), "a" + E + "[31")
            self.assertEqual(strip(E + "]0;never ends"), E + "]0;never ends")
            self.assertEqual(strip("a" + E + " b"), "a" + E + " b")

        def test_plain_and_empty(self):
            self.assertEqual(strip(""), "")
            self.assertEqual(strip("plain [31m text"), "plain [31m text")
            self.assertEqual(strip("a\nb\t" + E + "[0mc"), "a\nb\tc")

        def test_adjacent_sequences(self):
            self.assertEqual(strip(E + "[1m" + E + "[31m" + E + "[0m"), "")

        def test_visible_len(self):
            self.assertEqual(visible_len(""), 0)
            self.assertEqual(visible_len(E + "[31mabc" + E + "[0mde"), 5)
            self.assertEqual(visible_len("a" + E), 2)


    class Spans(unittest.TestCase):
        def test_basic_styles(self):
            t = sgr(1) + "a" + sgr(4) + "b" + sgr(0) + "c"
            self.assertEqual(spans(t), [(("bold",), "a"), (("bold", "underline"), "b"), ((), "c")])

        def test_attribute_order_is_fixed(self):
            self.assertEqual(spans(sgr(4, 3, 2, 1) + "x"), [(("bold", "dim", "italic", "underline"), "x")])
            self.assertEqual(spans(sgr(41, 32, 1) + "x"), [(("bold", "fg=green", "bg=red"), "x")])

        def test_colours(self):
            for i, name in enumerate(["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]):
                self.assertEqual(spans(sgr(30 + i) + "x"), [(("fg=" + name,), "x")])
                self.assertEqual(spans(sgr(40 + i) + "x"), [(("bg=" + name,), "x")])
                self.assertEqual(spans(sgr(90 + i) + "x"), [(("fg=bright-" + name,), "x")])
                self.assertEqual(spans(sgr(100 + i) + "x"), [(("bg=bright-" + name,), "x")])

        def test_extended_colours(self):
            self.assertEqual(spans(sgr(38, 5, 208) + "x"), [(("fg=256:208",), "x")])
            self.assertEqual(spans(sgr(48, 5, 17) + "x"), [(("bg=256:17",), "x")])
            self.assertEqual(spans(sgr(38, 2, 255, 0, 128) + "x"), [(("fg=rgb:255,0,128",), "x")])
            self.assertEqual(spans(sgr(48, 2, 1, 2, 3) + "x"), [(("bg=rgb:1,2,3",), "x")])
            self.assertEqual(spans(sgr(1, 38, 5, 9, 4) + "x"), [(("bold", "underline", "fg=256:9"), "x")])

        def test_bad_extended_colours_end_the_sequence(self):
            self.assertEqual(spans(sgr(1, 38, 5) + "x"), [(("bold",), "x")])
            self.assertEqual(spans(sgr(1, 38, 2, 1, 2) + "x"), [(("bold",), "x")])
            self.assertEqual(spans(sgr(38, 7, 1) + "x"), [((), "x")])
            self.assertEqual(spans(sgr(38) + "x"), [((), "x")])
            self.assertEqual(spans(sgr(1, 38, 9, 4) + "x"), [(("bold",), "x")])

        def test_clearing_codes(self):
            self.assertEqual(spans(sgr(1, 2, 3, 4) + sgr(22) + "x"), [(("italic", "underline"), "x")])
            self.assertEqual(spans(sgr(3, 4) + sgr(23) + "x"), [(("underline",), "x")])
            self.assertEqual(spans(sgr(3, 4) + sgr(24) + "x"), [(("italic",), "x")])
            self.assertEqual(spans(sgr(31, 42) + sgr(39) + "x"), [(("bg=green",), "x")])
            self.assertEqual(spans(sgr(31, 42) + sgr(49) + "x"), [(("fg=red",), "x")])
            self.assertEqual(spans(sgr(38, 5, 1) + sgr(39) + "x"), [((), "x")])
            self.assertEqual(spans(sgr(1, 31) + sgr(0) + "x"), [((), "x")])

        def test_reset_variants(self):
            self.assertEqual(spans(sgr(1) + E + "[m" + "x"), [((), "x")])
            self.assertEqual(spans(sgr(1) + E + "[;m" + "x"), [((), "x")])
            self.assertEqual(spans(E + "[1;;4m" + "x"), [(("underline",), "x")])
            self.assertEqual(spans(E + "[4;m" + "x"), [((), "x")])

        def test_unknown_codes_ignored(self):
            self.assertEqual(spans(sgr(1, 99, 5, 21, 53) + "x"), [(("bold",), "x")])
            self.assertEqual(spans(sgr(108) + "x"), [((), "x")])
            self.assertEqual(spans(sgr(29) + "x"), [((), "x")])

        def test_later_colour_wins(self):
            self.assertEqual(spans(sgr(31) + sgr(34) + "x"), [(("fg=blue",), "x")])
            self.assertEqual(spans(sgr(31, 94) + "x"), [(("fg=bright-blue",), "x")])

        def test_merging_and_empty_runs(self):
            t = sgr(1) + "a" + sgr(1) + "b" + sgr(4) + sgr(24) + "c" + sgr(0) + sgr(0) + "d" + "e"
            self.assertEqual(spans(t), [(("bold",), "abc"), ((), "de")])
            self.assertEqual(spans(sgr(1) + sgr(0)), [])
            self.assertEqual(spans(""), [])

        def test_non_sgr_sequences_keep_style(self):
            t = sgr(1) + "a" + E + "[2K" + "b" + E + "]0;t\x07" + "c"
            self.assertEqual(spans(t), [(("bold",), "abc")])

        def test_csi_m_with_other_bytes_is_not_sgr(self):
            self.assertEqual(spans(sgr(1) + E + "[?1m" + "x"), [(("bold",), "x")])
            self.assertEqual(spans(sgr(1) + E + "[1 m" + "x"), [(("bold",), "x")])
            self.assertEqual(spans(sgr(1) + E + "[0:1m" + "x"), [(("bold",), "x")])

        def test_trailing_text_and_leading_text(self):
            self.assertEqual(spans("a" + sgr(31) + "b" + sgr(0) + "c"), [((), "a"), (("fg=red",), "b"), ((), "c")])


    class Normalize(unittest.TestCase):
        def test_plain_unchanged(self):
            self.assertEqual(normalize("plain"), "plain")
            self.assertEqual(normalize(""), "")

        def test_attributes_and_order(self):
            self.assertEqual(normalize(sgr(4, 1) + "x"), E + "[1;4mx" + E + "[0m")
            self.assertEqual(normalize(sgr(2, 3) + "x"), E + "[2;3mx" + E + "[0m")

        def test_colours(self):
            self.assertEqual(normalize(sgr(31) + "x"), E + "[31mx" + E + "[0m")
            self.assertEqual(normalize(sgr(97) + "x"), E + "[97mx" + E + "[0m")
            self.assertEqual(normalize(sgr(44) + "x"), E + "[44mx" + E + "[0m")
            self.assertEqual(normalize(sgr(103) + "x"), E + "[103mx" + E + "[0m")
            self.assertEqual(normalize(sgr(38, 5, 208) + "x"), E + "[38;5;208mx" + E + "[0m")
            self.assertEqual(normalize(sgr(48, 5, 17) + "x"), E + "[48;5;17mx" + E + "[0m")
            self.assertEqual(normalize(sgr(38, 2, 1, 2, 3) + "x"), E + "[38;2;1;2;3mx" + E + "[0m")
            self.assertEqual(normalize(sgr(48, 2, 9, 8, 7) + "x"), E + "[48;2;9;8;7mx" + E + "[0m")
            self.assertEqual(normalize(sgr(30) + "x"), E + "[30mx" + E + "[0m")
            self.assertEqual(normalize(sgr(47) + "x"), E + "[47mx" + E + "[0m")

        def test_full_combination(self):
            t = sgr(44, 1, 91, 4) + "x"
            self.assertEqual(normalize(t), E + "[1;4;91;44mx" + E + "[0m")

        def test_merges_runs(self):
            t = sgr(1) + "a" + sgr(1) + "b" + sgr(0) + "c" + sgr(31) + "d"
            self.assertEqual(normalize(t), E + "[1mab" + E + "[0mc" + E + "[31md" + E + "[0m")

        def test_drops_other_sequences(self):
            self.assertEqual(normalize("a" + E + "[2K" + "b" + E + "]0;t\x07"), "ab")

        def test_idempotent(self):
            t = sgr(1, 31) + "ab" + sgr(0) + "c" + sgr(48, 2, 1, 2, 3) + "d" + sgr(39, 49)
            once = normalize(t)
            self.assertEqual(normalize(once), once)
            self.assertEqual(spans(once), spans(t))


    class Truncate(unittest.TestCase):
        def test_plain(self):
            self.assertEqual(truncate("abcdef", 3), "abc")
            self.assertEqual(truncate("abcdef", 6), "abcdef")
            self.assertEqual(truncate("abcdef", 10), "abcdef")
            self.assertEqual(truncate("abcdef", 0), "")
            self.assertEqual(truncate("", 0), "")
            self.assertEqual(truncate("abcdef", 5), "abcde")
            self.assertEqual(truncate("abcdef", 1), "a")

        def test_negative(self):
            with self.assertRaises(ValueError):
                truncate("abc", -1)

        def test_short_text_unchanged_including_trailing_sequences(self):
            t = sgr(1) + "ab" + sgr(0)
            self.assertEqual(truncate(t, 2), t)
            self.assertEqual(truncate(t, 5), t)
            t = sgr(1) + "ab"
            self.assertEqual(truncate(t, 2), t)

        def test_cut_inside_style_appends_reset(self):
            t = sgr(1) + "abcdef" + sgr(0)
            self.assertEqual(truncate(t, 3), sgr(1) + "abc" + sgr(0))
            t = sgr(31) + "abcdef"
            self.assertEqual(truncate(t, 4), sgr(31) + "abcd" + sgr(0))

        def test_cut_in_default_style_adds_nothing(self):
            t = "ab" + sgr(1) + "cd" + sgr(0) + "efgh"
            self.assertEqual(truncate(t, 6), "ab" + sgr(1) + "cd" + sgr(0) + "ef")
            self.assertEqual(truncate(t, 2), "ab")
            self.assertEqual(truncate("ab" + sgr(0) + "cdef", 3), "ab" + sgr(0) + "c")

        def test_sequences_after_the_cut_are_dropped(self):
            t = "abc" + sgr(31) + "def"
            self.assertEqual(truncate(t, 3), "abc")
            t = sgr(1) + "abc" + sgr(0) + "def"
            self.assertEqual(truncate(t, 3), sgr(1) + "abc" + sgr(0))
            t = sgr(1) + "abc" + sgr(31) + "def"
            self.assertEqual(truncate(t, 3), sgr(1) + "abc" + sgr(0))

        def test_reset_just_before_cut_leaves_default(self):
            t = sgr(1) + "ab" + sgr(0) + "cdef"
            self.assertEqual(truncate(t, 3), sgr(1) + "ab" + sgr(0) + "c")

        def test_other_sequences_kept_before_cut(self):
            t = "a" + E + "[2K" + "bcdef"
            self.assertEqual(truncate(t, 3), "a" + E + "[2K" + "bc")
            t = "ab" + E + "]0;t\x07" + "cdef"
            self.assertEqual(truncate(t, 3), "ab" + E + "]0;t\x07" + "c")

        def test_state_tracking_uses_sgr_semantics(self):
            t = sgr(1, 2) + "abc" + sgr(22) + "def"
            self.assertEqual(truncate(t, 4), sgr(1, 2) + "abc" + sgr(22) + "d")
            t = sgr(38, 5, 9) + "abc" + sgr(39) + "def"
            self.assertEqual(truncate(t, 5), sgr(38, 5, 9) + "abc" + sgr(39) + "de")
            t = sgr(4) + "ab" + sgr(24) + "cdef"
            self.assertEqual(truncate(t, 3), sgr(4) + "ab" + sgr(24) + "c")

        def test_width_zero_drops_everything(self):
            self.assertEqual(truncate(sgr(1) + "abc", 0), "")

        def test_visible_length_of_result(self):
            t = sgr(1) + "hello " + sgr(32) + "wide" + sgr(0) + " world"
            for w in range(0, 17):
                self.assertEqual(visible_len(truncate(t, w)), min(w, visible_len(t)))


    if __name__ == "__main__":
        unittest.main()
''')

ANSI = Lib(
    name="ansispan", lang="python", title="the ANSI escape helpers (`ansispan.py`)",
    blurb="The log pager measures, restyles and truncates terminal output with this module.",
    files={"ansispan.py": ANSI_SRC, "README.md": ANSI_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": ANSI_VISIBLE},
    hidden_tests={"tests/test_full.py": ANSI_HIDDEN},
    mutate=["ansispan.py"], difficulty=4, tags=["terminal", "text"],
    probes=[
        'strip("a\\x1b[2Kb\\x1b]0;t\\x07c\\x1b")',
        'visible_len("\\x1b[31mabc\\x1b[0mde\\x1b")',
        'spans("\\x1b[1;;4mx")',
        'spans("\\x1b[1;38;5mx")',
        'spans("\\x1b[1;2m\\x1b[22mx")',
        'spans("\\x1b[31;94mx\\x1b[39;49my")',
        'normalize("\\x1b[4;1;44mx\\x1b[1my")',
        'normalize("\\x1b[48;2;1;2;3mab\\x1b[0mc")',
        'truncate("\\x1b[1mabcdef\\x1b[0m", 3)',
        'truncate("abc\\x1b[31mdef", 3)',
        'truncate("\\x1b[1mab\\x1b[0mcdef", 3)',
    ],
    probe_import="from ansispan import *",
)


LIBS = [WRAP, GRID, ANSI]
register_libs(LIBS, n=10)
