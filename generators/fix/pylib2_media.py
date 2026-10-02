"""Text-format libraries (python), batch: subtitle cues, calendar lines, redaction."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# cuetime: a subtitle cue format with timing tools
# ======================================================================================================================

CT_README = dd(r'''
    # cuetime

    Reading, retiming and checking the `.cue` subtitle files of the video team. One module, `cuetime.py`. All times are `int`
    milliseconds.

    ## File format
    One cue per line: `[START-END flags] text`.

        [00:01.500-00:04.000] Hello there | second line
        [1:02:03.250-1:02:05.000 top italic] Up here

    * Blank lines (only whitespace) and lines starting with `;` (after stripping) are ignored. Lines are stripped first.
    * `START` and `END` are times (below). `flags` is zero or more words from `top`, `bottom`, `italic`, each after blanks; `top` and
      `bottom` together are invalid. Blanks before the closing `]` are allowed. The text after `]` (blanks skipped) must not be empty;
      it is split at ` | ` (space, bar, space) into lines, each stripped and non-empty.
    * `END` must be later than `START`; each cue's start must not be before the previous cue's start (overlaps are allowed).
    * Every `ValueError` raised for a line has a message that starts with `line N:` (N counts from 1, blank and comment lines included).

    ## `parse_time(text) -> int` and `format_time(ms) -> str`
    A time is `HH:MM:SS.mmm` style: optional hours (one or more digits) and a colon, then exactly two digits of minutes, `:`, two digits of
    seconds, `.`, three digits of milliseconds. Seconds must be below 60; with hours present minutes must be below 60 too (without hours
    they may be up to 99). Anything else is a `ValueError`. `format_time` writes `MM:SS.mmm` for values below one hour and
    `H:MM:SS.mmm` (hours without leading zeros) otherwise; a negative value is a `ValueError`.

    ## `parse_cues(text) -> list[Cue]` and `format_cues(cues) -> str`
    `Cue` is a `namedtuple` `(start, end, lines, flags)`: `lines` a tuple of strings, `flags` a tuple of the distinct flags in alphabetical order.
    `format_cues` writes the format back (`format_time` for the times, flags after the end separated by single spaces, lines joined by ` | `,
    cues joined by `\n`, no final newline); `parse_cues(format_cues(c)) == c`.

    ## `shift(cues, delta) -> list[Cue]`
    Adds `delta` to every start and end. A cue that would end at or before 0 is dropped; one that would start before 0 starts at 0 instead.

    ## `retime(cues, t1, u1, t2, u2) -> list[Cue]`
    Linear re-synchronisation: a time `t` becomes `u1 + (t - t1) * (u2 - u1) / (t2 - t1)`, computed exactly and rounded half up (to the
    next integer when exactly halfway) to a whole millisecond. `t1 == t2`, or a mapping that is not increasing (`(u2 - u1) / (t2 - t1)` not
    positive), is a `ValueError`. After mapping, a cue whose end is not after its start gets `end = start + 1`; then the rules of `shift`
    for times before 0 apply (dropped if the end is at or before 0, start clamped to 0 otherwise, and the cue keeps `end > start`).

    ## `merge_close(cues, max_gap) -> list[Cue]`
    Walks the cues in order and merges a cue into the current one when both have the same `lines` and the same `flags` and
    `cue.start - current.end <= max_gap` (so overlapping cues and touching cues merge); the merged cue ends at the later of both ends.

    ## `find_overlaps(cues) -> list[(i, j)]`
    All index pairs `i < j` with `cues[j].start < cues[i].end`, ordered by `i` then `j`. Cues must be sorted by start.

    ## `too_fast(cues, max_cps) -> list[int]`
    Indexes of cues whose reading speed is above `max_cps` characters per second: the number of characters in all their lines (separators
    not counted) times 1000 is greater than `max_cps` times the duration in milliseconds.
''')

CT_SRC = dd(r'''
    """Subtitle cue files."""
    import re
    from collections import namedtuple
    from fractions import Fraction

    Cue = namedtuple("Cue", "start end lines flags")

    _TIME = re.compile(r"(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})")
    _CUE = re.compile(r"\[([0-9:.]+)-([0-9:.]+)((?:\s+[a-z]+)*)\s*\]\s*(.+)")
    _FLAGS = ("bottom", "italic", "top")


    def parse_time(text):
        m = _TIME.fullmatch(text)
        if not m:
            raise ValueError("bad time: %r" % text)
        hours, minutes, seconds, millis = m.groups()
        minutes, seconds = int(minutes), int(seconds)
        if seconds >= 60 or (hours is not None and minutes >= 60):
            raise ValueError("bad time: %r" % text)
        return ((int(hours or 0) * 60 + minutes) * 60 + seconds) * 1000 + int(millis)


    def format_time(ms):
        if ms < 0:
            raise ValueError("negative time")
        if ms >= 3600000:
            hours, rest = divmod(ms, 3600000)
            return "%d:%02d:%02d.%03d" % (hours, rest // 60000, rest // 1000 % 60, rest % 1000)
        return "%02d:%02d.%03d" % (ms // 60000, ms // 1000 % 60, ms % 1000)


    def parse_cues(text):
        cues = []
        for no, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith(";"):
                continue
            try:
                m = _CUE.fullmatch(line)
                if not m:
                    raise ValueError("cannot parse %r" % line)
                start, end = parse_time(m.group(1)), parse_time(m.group(2))
                if end <= start:
                    raise ValueError("end must be after start")
                flags = m.group(3).split()
                if any(f not in _FLAGS for f in flags) or ("top" in flags and "bottom" in flags):
                    raise ValueError("bad flags %r" % flags)
                lines = [p.strip() for p in m.group(4).split(" | ")]
                if any(not p for p in lines):
                    raise ValueError("empty text line")
                if cues and start < cues[-1].start:
                    raise ValueError("cue starts before the previous one")
            except ValueError as exc:
                raise ValueError("line %d: %s" % (no, exc)) from None
            cues.append(Cue(start, end, tuple(lines), tuple(sorted(set(flags)))))
        return cues


    def format_cues(cues):
        out = []
        for c in cues:
            flags = "".join(" " + f for f in c.flags)
            out.append("[%s-%s%s] %s" % (format_time(c.start), format_time(c.end), flags, " | ".join(c.lines)))
        return "\n".join(out)


    def _place(cue, start, end):
        if end <= 0:
            return None
        return cue._replace(start=max(start, 0), end=end)


    def shift(cues, delta):
        out = []
        for c in cues:
            moved = _place(c, c.start + delta, c.end + delta)
            if moved is not None:
                out.append(moved)
        return out


    def _half_up(x):
        return (x + Fraction(1, 2)) // 1


    def retime(cues, t1, u1, t2, u2):
        if t1 == t2 or (u2 - u1) * (t2 - t1) <= 0:
            raise ValueError("mapping must be increasing")

        def f(t):
            return int(u1 + _half_up(Fraction((t - t1) * (u2 - u1), t2 - t1)))

        out = []
        for c in cues:
            start, end = f(c.start), f(c.end)
            if end <= start:
                end = start + 1
            moved = _place(c, start, end)
            if moved is not None:
                out.append(moved)
        return out


    def merge_close(cues, max_gap):
        out = []
        cur = None
        for c in cues:
            if cur is not None and c.lines == cur.lines and c.flags == cur.flags and c.start - cur.end <= max_gap:
                cur = cur._replace(end=max(cur.end, c.end))
            else:
                if cur is not None:
                    out.append(cur)
                cur = c
        if cur is not None:
            out.append(cur)
        return out


    def find_overlaps(cues):
        pairs = []
        for i in range(len(cues)):
            for j in range(i + 1, len(cues)):
                if cues[j].start >= cues[i].end:
                    break
                pairs.append((i, j))
        return pairs


    def too_fast(cues, max_cps):
        return [i for i, c in enumerate(cues)
                if sum(len(line) for line in c.lines) * 1000 > max_cps * (c.end - c.start)]
''')

CT_VISIBLE = dd(r'''
    import unittest

    from cuetime import Cue, format_time, parse_cues, parse_time, shift


    class BasicTests(unittest.TestCase):
        def test_time(self):
            self.assertEqual(parse_time("00:01.500"), 1500)
            self.assertEqual(format_time(61500), "01:01.500")

        def test_parse(self):
            cues = parse_cues("[00:01.500-00:04.000] Hello | there\n")
            self.assertEqual(cues, [Cue(1500, 4000, ("Hello", "there"), ())])

        def test_shift(self):
            c = [Cue(1000, 2000, ("a",), ())]
            self.assertEqual(shift(c, 500), [Cue(1500, 2500, ("a",), ())])


    if __name__ == "__main__":
        unittest.main()
''')

CT_HIDDEN = dd(r'''
    import unittest

    from cuetime import (Cue, find_overlaps, format_cues, format_time, merge_close, parse_cues, parse_time, retime, shift,
                         too_fast)


    def C(start, end, *lines, flags=()):
        return Cue(start, end, tuple(lines or ("x",)), tuple(flags))


    class Times(unittest.TestCase):
        def test_parse(self):
            self.assertEqual(parse_time("00:00.000"), 0)
            self.assertEqual(parse_time("00:01.500"), 1500)
            self.assertEqual(parse_time("01:00.000"), 60000)
            self.assertEqual(parse_time("59:59.999"), 3599999)
            self.assertEqual(parse_time("75:10.000"), 4510000)
            self.assertEqual(parse_time("99:59.999"), 99 * 60000 + 59999)
            self.assertEqual(parse_time("1:00:00.000"), 3600000)
            self.assertEqual(parse_time("1:02:03.250"), 3723250)
            self.assertEqual(parse_time("0:00:00.001"), 1)
            self.assertEqual(parse_time("12:34:56.789"), ((12 * 60 + 34) * 60 + 56) * 1000 + 789)
            self.assertEqual(parse_time("100:00:00.000"), 360000000)
            self.assertEqual(parse_time("00:00:00.000"), 0)

        def test_bad(self):
            for bad in ("", "1.500", "00:60.000", "1:60:00.000", "1:00:60.000", "5:03.250", "00:01.5", "00:01.5000", "00:01,500", "0:1:01.000",
                        "00:1.500", " 00:01.500", "00:01.500 ", "-00:01.500", "00:01", "a:bc.def", "1:2:3:04.000", "00:00:00:00.000"):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    parse_time(bad)

        def test_format(self):
            self.assertEqual(format_time(0), "00:00.000")
            self.assertEqual(format_time(1), "00:00.001")
            self.assertEqual(format_time(1500), "00:01.500")
            self.assertEqual(format_time(61500), "01:01.500")
            self.assertEqual(format_time(3599999), "59:59.999")
            self.assertEqual(format_time(3600000), "1:00:00.000")
            self.assertEqual(format_time(3723250), "1:02:03.250")
            self.assertEqual(format_time(360000000), "100:00:00.000")
            self.assertEqual(format_time(43 * 3600000 + 5 * 60000 + 9 * 1000 + 7), "43:05:09.007")

        def test_format_negative(self):
            with self.assertRaises(ValueError):
                format_time(-1)

        def test_round_trip(self):
            for ms in (0, 999, 1000, 59999, 60000, 3599999, 3600000, 3661001, 86399999, 90000000):
                self.assertEqual(parse_time(format_time(ms)), ms)


    class Parse(unittest.TestCase):
        def test_basic(self):
            cues = parse_cues("[00:01.500-00:04.000] Hello there | second line\n[00:05.000-00:06.000] Bye\n")
            self.assertEqual(cues, [C(1500, 4000, "Hello there", "second line"), C(5000, 6000, "Bye")])

        def test_flags(self):
            cues = parse_cues("[00:01.000-00:02.000 top] a\n[00:03.000-00:04.000 italic bottom] b\n[00:05.000-00:06.000  italic   italic ] c\n")
            self.assertEqual([c.flags for c in cues], [("top",), ("bottom", "italic"), ("italic",)])

        def test_blank_and_comment_lines(self):
            text = "\n; a comment\n   \n[00:01.000-00:02.000] a\n  ; indented comment\n[00:03.000-00:04.000] b"
            self.assertEqual(parse_cues(text), [C(1000, 2000, "a"), C(3000, 4000, "b")])
            self.assertEqual(parse_cues(""), [])
            self.assertEqual(parse_cues("; only\n"), [])

        def test_whitespace_and_crlf(self):
            text = "  [00:01.000-00:02.000]    spaced  out   \r\n\t[00:03.000-00:04.000]\tb | c  \r\n"
            self.assertEqual(parse_cues(text), [C(1000, 2000, "spaced  out"), C(3000, 4000, "b", "c")])

        def test_hours(self):
            cues = parse_cues("[59:59.000-1:00:01.000] long\n")
            self.assertEqual(cues, [C(3599000, 3601000, "long")])

        def test_bar_without_spaces_is_text(self):
            self.assertEqual(parse_cues("[00:01.000-00:02.000] a|b | c ||d")[0].lines, ("a|b", "c ||d"))

        def test_overlap_and_equal_starts_are_fine(self):
            cues = parse_cues("[00:01.000-00:05.000] a\n[00:01.000-00:03.000] b\n[00:02.000-00:03.000] c\n")
            self.assertEqual(len(cues), 3)

        def test_errors_have_line_numbers(self):
            cases = [
                ("[00:02.000-00:01.000] a", 1), ("[00:01.000-00:01.000] a", 1), ("garbage", 1), ("; c\n\n[00:01.000-00:02.000]", 3),
                ("[00:01.000-00:02.000] a\n[00:00.500-00:02.000] b", 2), ("[00:01.000-00:02.000] a |  | b", 1),
                ("[00:01.000-00:02.000 loud] a", 1), ("[00:01.000-00:02.000 top bottom] a", 1), ("[00:61.000-00:62.000] a", 1),
                ("[00:01.000-00:02.000 TOP] a", 1), ("\n\n\n[1-2] a", 4), ("[00:01.000 00:02.000] a", 1), ("[00:01.000-00:02.000 top,italic] a", 1),
                ("00:01.000-00:02.000 a", 1), ("[00:01.000-00:02.000] a\n[00:03.000-00:02.500] b", 2),
            ]
            for text, line in cases:
                with self.assertRaises(ValueError, msg=text) as cm:
                    parse_cues(text)
                self.assertTrue(str(cm.exception).startswith("line %d:" % line), (text, str(cm.exception)))

        def test_earlier_start_is_checked_against_previous_cue_only(self):
            parse_cues("[00:05.000-00:06.000] a\n[00:05.000-00:07.000] b\n[00:06.000-00:07.000] c\n")
            with self.assertRaises(ValueError):
                parse_cues("[00:05.000-00:06.000] a\n[00:07.000-00:08.000] b\n[00:06.000-00:07.000] c\n")


    class Format(unittest.TestCase):
        def test_exact(self):
            cues = [C(1500, 4000, "Hello there", "second line"), C(3723250, 3725000, "Up here", flags=("italic", "top"))]
            self.assertEqual(format_cues(cues), "[00:01.500-00:04.000] Hello there | second line\n[1:02:03.250-1:02:05.000 italic top] Up here")
            self.assertEqual(format_cues([]), "")

        def test_round_trip(self):
            text = "[00:00.000-00:00.001] a\n[00:59.000-1:00:01.000 bottom] b | c | d\n[1:00:00.000-100:00:00.000 italic top] e\n"
            cues = parse_cues(text)
            self.assertEqual(parse_cues(format_cues(cues)), cues)
            self.assertEqual(format_cues(cues) + "\n", text)


    class Shift(unittest.TestCase):
        def test_forward_and_back(self):
            cues = [C(1000, 2000, "a"), C(3000, 4000, "b")]
            self.assertEqual(shift(cues, 500), [C(1500, 2500, "a"), C(3500, 4500, "b")])
            self.assertEqual(shift(cues, -500), [C(500, 1500, "a"), C(2500, 3500, "b")])
            self.assertEqual(shift(cues, 0), cues)
            self.assertEqual(shift([], 5), [])

        def test_clamping_and_dropping(self):
            cues = [C(1000, 2000, "a"), C(3000, 4000, "b"), C(5000, 6000, "c")]
            self.assertEqual(shift(cues, -1500), [C(0, 500, "a"), C(1500, 2500, "b"), C(3500, 4500, "c")])
            self.assertEqual(shift(cues, -2000), [C(1000, 2000, "b"), C(3000, 4000, "c")])
            self.assertEqual(shift(cues, -2001), [C(999, 1999, "b"), C(2999, 3999, "c")])
            self.assertEqual(shift(cues, -1999), [C(0, 1, "a"), C(1001, 2001, "b"), C(3001, 4001, "c")])
            self.assertEqual(shift(cues, -6000), [])
            self.assertEqual(shift(cues, -5999), [C(0, 1, "c")])

        def test_keeps_text_and_flags(self):
            got = shift([C(1000, 2000, "a", "b", flags=("top",))], 1)
            self.assertEqual(got, [C(1001, 2001, "a", "b", flags=("top",))])


    class Retime(unittest.TestCase):
        def test_scale_and_offset(self):
            cues = [C(0, 1000, "a"), C(10000, 20000, "b")]
            self.assertEqual(retime(cues, 0, 0, 10000, 20000), [C(0, 2000, "a"), C(20000, 40000, "b")])
            self.assertEqual(retime(cues, 0, 500, 10000, 10500), [C(500, 1500, "a"), C(10500, 20500, "b")])
            self.assertEqual(retime(cues, 10000, 10000, 20000, 15000), [C(5000, 5500, "a"), C(10000, 15000, "b")])

        def test_rounding_half_up(self):
            self.assertEqual(retime([C(1, 3, "a")], 0, 0, 2, 3), [C(2, 5, "a")])
            self.assertEqual(retime([C(1, 5, "a")], 0, 0, 2, 1), [C(1, 3, "a")])
            self.assertEqual(retime([C(2, 4, "a")], 0, 0, 4, 1), [C(1, 2, "a")])
            self.assertEqual(retime([C(100, 300, "a")], 0, 0, 3, 1), [C(33, 100, "a")])

        def test_frame_rate_style_mapping(self):
            cues = [C(60000, 61000, "a")]
            self.assertEqual(retime(cues, 0, 0, 25000, 23976), [C(57542, 58501, "a")])

        def test_minimum_duration_of_one_ms(self):
            self.assertEqual(retime([C(1000, 1001, "a")], 0, 0, 1000, 100), [C(100, 101, "a")])
            self.assertEqual(retime([C(10, 11, "a")], 0, 0, 100, 10), [C(1, 2, "a")])

        def test_before_zero(self):
            cues = [C(0, 1000, "a"), C(5000, 6000, "b")]
            self.assertEqual(retime(cues, 2000, 0, 4000, 2000), [C(3000, 4000, "b")])
            self.assertEqual(retime([C(0, 1000, "a")], 1000, 0, 2000, 1000), [])
            self.assertEqual(retime([C(0, 1500, "a")], 1000, 0, 2000, 1000), [C(0, 500, "a")])

        def test_bad_mappings(self):
            for args in ((5, 0, 5, 10), (0, 0, 10, 0), (0, 10, 10, 0), (10, 0, 0, 10), (0, 5, 10, 5)):
                with self.assertRaises(ValueError, msg=str(args)):
                    retime([C(1, 2, "a")], *args)

        def test_decreasing_anchor_order_is_fine_when_increasing(self):
            self.assertEqual(retime([C(1000, 2000, "a")], 10000, 20000, 0, 0), [C(2000, 4000, "a")])


    class Merge(unittest.TestCase):
        def test_gap_rule(self):
            cues = [C(0, 1000, "a"), C(1200, 2000, "a"), C(2600, 3000, "a")]
            self.assertEqual(merge_close(cues, 200), [C(0, 2000, "a"), C(2600, 3000, "a")])
            self.assertEqual(merge_close(cues, 199), cues)
            self.assertEqual(merge_close(cues, 600), [C(0, 3000, "a")])
            self.assertEqual(merge_close(cues, 0), cues)

        def test_touching_and_overlapping(self):
            self.assertEqual(merge_close([C(0, 1000, "a"), C(1000, 2000, "a")], 0), [C(0, 2000, "a")])
            self.assertEqual(merge_close([C(0, 3000, "a"), C(1000, 2000, "a")], 0), [C(0, 3000, "a")])
            self.assertEqual(merge_close([C(0, 1000, "a"), C(500, 2000, "a")], 0), [C(0, 2000, "a")])

        def test_text_and_flags_must_match(self):
            cues = [C(0, 1000, "a"), C(1000, 2000, "b"), C(2000, 3000, "b", flags=("top",)), C(3000, 4000, "b", flags=("top",))]
            self.assertEqual(merge_close(cues, 100), [C(0, 1000, "a"), C(1000, 2000, "b"), C(2000, 4000, "b", flags=("top",))])
            self.assertEqual(merge_close([C(0, 1, "a", "b"), C(1, 2, "a")], 10), [C(0, 1, "a", "b"), C(1, 2, "a")])

        def test_chain_and_empty(self):
            cues = [C(0, 100, "a"), C(150, 250, "a"), C(300, 400, "a")]
            self.assertEqual(merge_close(cues, 50), [C(0, 400, "a")])
            self.assertEqual(merge_close([], 10), [])
            self.assertEqual(merge_close([C(0, 1, "a")], 10), [C(0, 1, "a")])

        def test_only_with_the_current_cue(self):
            cues = [C(0, 1000, "a"), C(1100, 1200, "b"), C(1300, 1400, "a")]
            self.assertEqual(merge_close(cues, 500), cues)


    class Checks(unittest.TestCase):
        def test_overlaps(self):
            cues = [C(0, 5000, "a"), C(1000, 2000, "b"), C(2000, 3000, "c"), C(4000, 6000, "d"), C(6000, 7000, "e")]
            self.assertEqual(find_overlaps(cues), [(0, 1), (0, 2), (0, 3)])
            self.assertEqual(find_overlaps([C(0, 1000, "a"), C(1000, 2000, "b")]), [])
            self.assertEqual(find_overlaps([C(0, 1000, "a"), C(999, 2000, "b")]), [(0, 1)])
            self.assertEqual(find_overlaps([]), [])
            self.assertEqual(find_overlaps([C(0, 10, "a")]), [])

        def test_overlaps_chain(self):
            cues = [C(0, 3000, "a"), C(1000, 4000, "b"), C(2000, 5000, "c")]
            self.assertEqual(find_overlaps(cues), [(0, 1), (0, 2), (1, 2)])

        def test_too_fast(self):
            cues = [C(0, 1000, "abcdefghij"), C(0, 1000, "abcdefghijk"), C(0, 2000, "abcde", "fghij", "klmno"), C(0, 500, "abcde")]
            self.assertEqual(too_fast(cues, 10), [1])
            self.assertEqual(too_fast(cues, 9), [0, 1, 3])
            self.assertEqual(too_fast(cues, 8), [0, 1, 3])
            self.assertEqual(too_fast(cues, 7), [0, 1, 2, 3])
            self.assertEqual(too_fast(cues, 11), [])
            self.assertEqual(too_fast(cues, 5), [0, 1, 2, 3])
            self.assertEqual(too_fast([], 5), [])

        def test_too_fast_counts_characters_not_lines(self):
            cues = [C(0, 1000, "ab", "cd", "ef")]
            self.assertEqual(too_fast(cues, 5), [0])
            self.assertEqual(too_fast(cues, 6), [])


    if __name__ == "__main__":
        unittest.main()
''')

CT = Lib(
    name="cuetime", lang="python", title="the subtitle cue tools (`cuetime.py`)",
    blurb="The video team's tools read, retime and check `.cue` subtitle files with this module.",
    files={"cuetime.py": CT_SRC, "README.md": CT_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": CT_VISIBLE},
    hidden_tests={"tests/test_full.py": CT_HIDDEN},
    mutate=["cuetime.py"], difficulty=3, tags=["subtitles", "time", "parsing"],
    probes=[
        'parse_time("75:10.000")',
        'format_time(3599999)',
        'format_time(3600000)',
        'parse_cues("[00:01.000-00:02.000 italic bottom] a | b\\n")',
        'shift([Cue(1000, 2000, ("a",), ()), Cue(5000, 6000, ("b",), ())], -1500)',
        'shift([Cue(1000, 2000, ("a",), ())], -2000)',
        'retime([Cue(1, 3, ("a",), ())], 0, 0, 2, 3)',
        'retime([Cue(60000, 61000, ("a",), ())], 0, 0, 25000, 23976)',
        'merge_close([Cue(0, 1000, ("a",), ()), Cue(1200, 2000, ("a",), ())], 200)',
        'find_overlaps([Cue(0, 3000, ("a",), ()), Cue(1000, 4000, ("b",), ()), Cue(2000, 5000, ("c",), ())])',
        'too_fast([Cue(0, 1000, ("abcdefghij",), ()), Cue(0, 1000, ("abcdefghijk",), ())], 10)',
    ],
    probe_import="from cuetime import *",
)


# ======================================================================================================================
# icsfold: content lines of a calendar interchange format (folding, escaping, parameters, components)
# ======================================================================================================================

ICS_README = dd(r'''
    # icsfold

    Reader and writer helpers for the team calendar's interchange files (`.tcal`), a text format of "content lines". One module,
    `icsfold.py`.

    ## Folding
    A logical line may be split into physical lines of at most `width` UTF-8 bytes; each continuation line starts with one space.
    ### `fold(line, width=48) -> list[str]`
    Returns the physical lines. If the line's UTF-8 length is at most `width` it is returned whole (`[line]`, also for `""`). Otherwise the
    first physical line takes as many characters as fit in `width` bytes, and every following one is a single space plus as many characters
    as fit in `width - 1` bytes (so a physical line, space included, never exceeds `width` bytes). A character is never split. `width` below 5
    is a `ValueError`.

    ### `unfold(text) -> list[str]`
    Splits `text` at `\n` or `\r\n` only (no other Unicode line breaks). Empty lines are skipped. A line that starts with a space or a tab
    is a continuation: its first character is dropped and the rest is appended to the previous logical line (a continuation with no previous
    line is a `ValueError`). Returns the logical lines.

    ## Text escaping
    `escape_text(s)`: `\` becomes `\\`, `;` becomes `\;`, `,` becomes `\,`, and a newline (`\n`, also `\r\n`) becomes the two characters `\n`.
    `unescape_text(s)` reverses this: `\\`, `\;`, `\,` and `\n` or `\N` (newline). Any other backslash sequence, and a backslash at the very
    end, is a `ValueError`. `unescape_text(escape_text(s)) == s` for texts without a bare `\r`.

    ## Properties
    `Prop` is a `namedtuple` `(name, params, value)`.
    ### `parse_line(line) -> Prop`
    A logical line is `NAME`, zero or more `;PARAM=VALUES`, a colon, and the value. Names (property and parameter) are made of `A-Za-z0-9-`
    and returned upper-cased. `params` maps each parameter name to a list of strings: `VALUES` are one or more values separated by commas, each
    either a double-quoted string (may contain `;`, `:`, `,`; the quotes are removed) or a run of characters other than `; : , "`; a parameter
    that occurs again adds its values to the list. The value after the first colon that follows the parameters is returned as is (it may be empty
    and may contain colons). A missing name, a parameter without `=`, an unterminated or stray quote, or a missing colon is a `ValueError`.

    ### `format_prop(name, params, value) -> str`
    `NAME` upper-cased, then for each item of the `params` dict (in dict order) `;KEY=` with the values (a string or a list of strings) joined by
    commas, then `:` and `value`. A parameter value containing `;`, `:` or `,` is written in double quotes; a value containing `"` is a
    `ValueError`, as is a name or key that is not made of `A-Za-z0-9-`. `parse_line(format_prop(n, p, v))` returns the same name, lists and value.

    ## Components
    `Component` is a `namedtuple` `(name, props, children)`; `props` is a list of `Prop`, `children` a list of `Component`.
    ### `parse_components(text) -> list[Component]`
    Unfolds `text`, parses every line, and builds the components from `BEGIN:NAME` / `END:NAME` lines (the name is upper-cased; the BEGIN/END
    lines themselves are not props). Components may be nested; a nested one goes to the `children` of its parent, in order. A prop
    outside any component, an `END` that does not match the innermost open component, an `END` with no open component, or a component
    left open at the end is a `ValueError`. Returns the top-level components.

    ### `values(component, name) -> list[str]`
    The unescaped (`unescape_text`) values of the component's own props called `name` (case-insensitive), in order; children are not searched.
''')

ICS_SRC = dd(r'''
    """Calendar content lines."""
    import re
    from collections import namedtuple

    Prop = namedtuple("Prop", "name params value")
    Component = namedtuple("Component", "name props children")

    _NAME = re.compile(r"[A-Za-z0-9-]+")


    def fold(line, width=48):
        if width < 5:
            raise ValueError("width must be at least 5")
        out = []
        cur = ""
        used = 0
        limit = width
        for ch in line:
            n = len(ch.encode("utf-8"))
            if used + n > limit:
                out.append(cur if not out else " " + cur)
                cur, used, limit = "", 0, width - 1
            cur += ch
            used += n
        out.append(cur if not out else " " + cur)
        return out


    def unfold(text):
        lines = []
        for raw in re.split(r"\r?\n", text):
            if raw == "":
                continue
            if raw[0] in " \t":
                if not lines:
                    raise ValueError("continuation line without a previous line")
                lines[-1] += raw[1:]
            else:
                lines.append(raw)
        return lines


    def escape_text(s):
        s = s.replace("\r\n", "\n")
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


    def unescape_text(s):
        out = []
        i = 0
        while i < len(s):
            c = s[i]
            if c != "\\":
                out.append(c)
                i += 1
                continue
            if i + 1 >= len(s):
                raise ValueError("backslash at the end")
            nxt = s[i + 1]
            if nxt in "\\;,":
                out.append(nxt)
            elif nxt in "nN":
                out.append("\n")
            else:
                raise ValueError("bad escape: \\%s" % nxt)
            i += 2
        return "".join(out)


    def parse_line(line):
        m = _NAME.match(line)
        if not m:
            raise ValueError("missing property name")
        name = m.group().upper()
        pos = m.end()
        params = {}
        while line[pos:pos + 1] == ";":
            m = _NAME.match(line, pos + 1)
            if not m or line[m.end():m.end() + 1] != "=":
                raise ValueError("bad parameter")
            pname = m.group().upper()
            pos = m.end() + 1
            vals = []
            while True:
                if line[pos:pos + 1] == '"':
                    end = line.find('"', pos + 1)
                    if end < 0:
                        raise ValueError("unterminated quote")
                    vals.append(line[pos + 1:end])
                    pos = end + 1
                else:
                    end = pos
                    while end < len(line) and line[end] not in ';:,"':
                        end += 1
                    if line[end:end + 1] == '"':
                        raise ValueError("stray quote")
                    vals.append(line[pos:end])
                    pos = end
                if line[pos:pos + 1] == ",":
                    pos += 1
                    continue
                break
            params.setdefault(pname, []).extend(vals)
        if line[pos:pos + 1] != ":":
            raise ValueError("missing colon")
        return Prop(name, params, line[pos + 1:])


    def _param_value(v):
        if '"' in v:
            raise ValueError("a parameter value cannot contain a double quote")
        return '"%s"' % v if any(c in v for c in ";:,") else v


    def format_prop(name, params, value):
        if not _NAME.fullmatch(name):
            raise ValueError("bad name: %r" % name)
        parts = [name.upper()]
        for key, vals in params.items():
            if not _NAME.fullmatch(key):
                raise ValueError("bad parameter name: %r" % key)
            if isinstance(vals, str):
                vals = [vals]
            parts.append("%s=%s" % (key.upper(), ",".join(_param_value(v) for v in vals)))
        return ";".join(parts) + ":" + value


    def parse_components(text):
        top = []
        stack = []
        for line in unfold(text):
            prop = parse_line(line)
            if prop.name == "BEGIN":
                stack.append(Component(prop.value.upper(), [], []))
            elif prop.name == "END":
                if not stack or stack[-1].name != prop.value.upper():
                    raise ValueError("unmatched END:%s" % prop.value)
                done = stack.pop()
                (stack[-1].children if stack else top).append(done)
            else:
                if not stack:
                    raise ValueError("property outside a component")
                stack[-1].props.append(prop)
        if stack:
            raise ValueError("component %s is not closed" % stack[-1].name)
        return top


    def values(component, name):
        return [unescape_text(p.value) for p in component.props if p.name == name.upper()]
''')

ICS_VISIBLE = dd(r'''
    import unittest

    from icsfold import escape_text, fold, parse_line, unfold


    class BasicTests(unittest.TestCase):
        def test_fold(self):
            self.assertEqual(fold("abcdefghijklmnopqrstuvwxyz", 10), ["abcdefghij", " klmnopqrs", " tuvwxyz"])

        def test_unfold(self):
            self.assertEqual(unfold("ab\n cd\nef\n"), ["abcd", "ef"])

        def test_escape(self):
            self.assertEqual(escape_text("a,b;c"), "a\\,b\\;c")

        def test_parse(self):
            p = parse_line("DTSTART;TZID=Europe/Oslo:20250101T090000")
            self.assertEqual((p.name, p.params, p.value), ("DTSTART", {"TZID": ["Europe/Oslo"]}, "20250101T090000"))


    if __name__ == "__main__":
        unittest.main()
''')

ICS_HIDDEN = dd(r'''
    import unittest

    from icsfold import (Component, Prop, escape_text, fold, format_prop, parse_components, parse_line, unescape_text, unfold,
                         values)


    class Fold(unittest.TestCase):
        def test_short_lines_whole(self):
            self.assertEqual(fold("", 10), [""])
            self.assertEqual(fold("abc", 10), ["abc"])
            self.assertEqual(fold("abcdefghij", 10), ["abcdefghij"])
            self.assertEqual(fold("x" * 48), ["x" * 48])

        def test_ascii_fold(self):
            self.assertEqual(fold("abcdefghijk", 10), ["abcdefghij", " k"])
            self.assertEqual(fold("abcdefghijklmnopqrstuvwxyz", 10), ["abcdefghij", " klmnopqrs", " tuvwxyz"])
            self.assertEqual(fold("a" * 19, 10), ["a" * 10, " " + "a" * 9])
            self.assertEqual(fold("a" * 20, 10), ["a" * 10, " " + "a" * 9, " a"])
            self.assertEqual(fold("a" * 28, 10), ["a" * 10, " " + "a" * 9, " " + "a" * 9])
            self.assertEqual(fold("a" * 29, 10), ["a" * 10, " " + "a" * 9, " " + "a" * 9, " a"])

        def test_default_width(self):
            parts = fold("y" * 100)
            self.assertEqual([len(p) for p in parts], [48, 48, 6])
            self.assertEqual(parts[1][0], " ")
            self.assertEqual("".join([parts[0]] + [p[1:] for p in parts[1:]]), "y" * 100)

        def test_multibyte_is_not_split(self):
            self.assertEqual(fold("\u00e9" * 11, 10), ["\u00e9" * 5, " " + "\u00e9" * 4, " " + "\u00e9" * 2])
            self.assertEqual(fold("\u20ac" * 7, 10), ["\u20ac" * 3, " " + "\u20ac" * 3, " \u20ac"])
            self.assertEqual(fold("\U0001F600" * 5, 10), ["\U0001F600" * 2, " " + "\U0001F600" * 2, " \U0001F600"])

        def test_multibyte_budget_counts_bytes(self):
            self.assertEqual(fold("ab\u20ac\u20ac\u20accd", 10), ["ab\u20ac\u20ac", " \u20accd"])
            self.assertEqual(fold("abcdefgh\u20ac", 10), ["abcdefgh", " \u20ac"])
            self.assertEqual(fold("abcdefg\u20ac", 10), ["abcdefg\u20ac"])
            self.assertEqual(fold("a\u00e9" * 6, 10), ["a\u00e9" * 3 + "a", " \u00e9a\u00e9a\u00e9"])

        def test_each_physical_line_fits(self):
            text = "Meeting \u2013 caf\u00e9 \u20ac5 \U0001F600 ends at 10:00, bring notes; thanks! " * 3
            for width in (5, 6, 9, 10, 17, 48, 75):
                parts = fold(text, width)
                for p in parts:
                    self.assertLessEqual(len(p.encode("utf-8")), width)
                self.assertEqual(unfold("\n".join(parts))[0], text)

        def test_width_limit(self):
            for w in (-1, 0, 4):
                with self.assertRaises(ValueError):
                    fold("abc", w)
            self.assertEqual(fold("\U0001F600\U0001F600", 5), ["\U0001F600", " \U0001F600"])


    class Unfold(unittest.TestCase):
        def test_basic(self):
            self.assertEqual(unfold("ab\n cd\n\tef\ngh\n"), ["abcdef", "gh"])
            self.assertEqual(unfold("ab\r\n cd\r\nef"), ["abcd", "ef"])
            self.assertEqual(unfold(""), [])
            self.assertEqual(unfold("\n\n"), [])

        def test_only_one_space_is_dropped(self):
            self.assertEqual(unfold("ab\n  cd\n"), ["ab cd"])
            self.assertEqual(unfold("ab\n \n cd\n"), ["abcd"])

        def test_empty_lines_skipped(self):
            self.assertEqual(unfold("a\n\nb\n"), ["a", "b"])
            self.assertEqual(unfold("a\n\n b\n"), ["ab"])

        def test_other_line_breaks_are_text(self):
            self.assertEqual(unfold("a\u2028b\x0bc\x0cd\n e\n"), ["a\u2028b\x0bc\x0cde"])

        def test_leading_continuation(self):
            with self.assertRaises(ValueError):
                unfold(" abc\n")
            with self.assertRaises(ValueError):
                unfold("\n\n\tabc")

        def test_fold_unfold(self):
            line = "DESCRIPTION:" + "word " * 40
            self.assertEqual(unfold("\n".join(fold(line, 30))), [line])


    class Escape(unittest.TestCase):
        def test_escape(self):
            self.assertEqual(escape_text("plain"), "plain")
            self.assertEqual(escape_text("a,b;c\\d"), "a\\,b\\;c\\\\d")
            self.assertEqual(escape_text("line1\nline2"), "line1\\nline2")
            self.assertEqual(escape_text("win\r\nline"), "win\\nline")
            self.assertEqual(escape_text(""), "")
            self.assertEqual(escape_text("\\n"), "\\\\n")
            self.assertEqual(escape_text("::"), "::")

        def test_unescape(self):
            self.assertEqual(unescape_text("a\\,b\\;c\\\\d"), "a,b;c\\d")
            self.assertEqual(unescape_text("x\\ny"), "x\ny")
            self.assertEqual(unescape_text("x\\Ny"), "x\ny")
            self.assertEqual(unescape_text("\\\\n"), "\\n")
            self.assertEqual(unescape_text(""), "")
            self.assertEqual(unescape_text("\\\\"), "\\")

        def test_unescape_errors(self):
            for bad in ("\\", "abc\\", "\\x", "a\\:b", "\\ ", "\\\\\\", "\\t"):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    unescape_text(bad)

        def test_round_trip(self):
            for s in ("", "a", "a,b", "a;b", "a\\b", "\\n", "x\ny\nz", ",;\\\n", "\\\\;;,,", "end\\"):
                self.assertEqual(unescape_text(escape_text(s)), s)


    class ParseLine(unittest.TestCase):
        def test_simple(self):
            self.assertEqual(parse_line("SUMMARY:Team sync"), Prop("SUMMARY", {}, "Team sync"))
            self.assertEqual(parse_line("summary:lower"), Prop("SUMMARY", {}, "lower"))
            self.assertEqual(parse_line("X-Custom-1:v"), Prop("X-CUSTOM-1", {}, "v"))

        def test_value_may_have_colons_and_be_empty(self):
            self.assertEqual(parse_line("URL:https://example.org:8080/a?b=c").value, "https://example.org:8080/a?b=c")
            self.assertEqual(parse_line("DESCRIPTION:").value, "")
            self.assertEqual(parse_line("A::").value, ":")
            self.assertEqual(parse_line('A;B="x":y;z,w"q').value, 'y;z,w"q')

        def test_parameters(self):
            p = parse_line("DTSTART;TZID=Europe/Oslo:20250101T090000")
            self.assertEqual(p, Prop("DTSTART", {"TZID": ["Europe/Oslo"]}, "20250101T090000"))
            p = parse_line("ATTENDEE;cn=Ada;ROLE=CHAIR:mailto:ada@example.org")
            self.assertEqual(p.params, {"CN": ["Ada"], "ROLE": ["CHAIR"]})
            self.assertEqual(p.value, "mailto:ada@example.org")

        def test_multiple_values(self):
            self.assertEqual(parse_line("A;M=x,y,z:v").params, {"M": ["x", "y", "z"]})
            self.assertEqual(parse_line("A;M=x;M=y,z:v").params, {"M": ["x", "y", "z"]})
            self.assertEqual(parse_line("A;M=:v").params, {"M": [""]})
            self.assertEqual(parse_line("A;M=x,:v").params, {"M": ["x", ""]})
            self.assertEqual(parse_line("A;M=,x:v").params, {"M": ["", "x"]})

        def test_quoted_values(self):
            p = parse_line('ATTENDEE;CN="Doe; Jane: the 2nd, Esq.";ROLE=REQ:mailto:j@e.org')
            self.assertEqual(p.params, {"CN": ["Doe; Jane: the 2nd, Esq."], "ROLE": ["REQ"]})
            self.assertEqual(p.value, "mailto:j@e.org")
            self.assertEqual(parse_line('A;M="a","b",c:v').params, {"M": ["a", "b", "c"]})
            self.assertEqual(parse_line('A;M="":v').params, {"M": [""]})
            self.assertEqual(parse_line('A;M="x y":v').params, {"M": ["x y"]})

        def test_param_values_keep_spaces_and_case(self):
            self.assertEqual(parse_line("A;M=x y Z:v").params, {"M": ["x y Z"]})

        def test_errors(self):
            for bad in ("", ":v", "NAME", "NAME;X:v", "NAME;=x:v", "NAME;X=y", 'NAME;X="y:v', 'NAME;X=a"b":v', 'NAME;X="a"b:v', "NA ME:v", "NAME;;X=1:v",
                        "NAME;X=1;:v", "N\u00e9:v", "NAME ;X=1:v", ";X=1:v"):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    parse_line(bad)


    class FormatProp(unittest.TestCase):
        def test_plain(self):
            self.assertEqual(format_prop("summary", {}, "x"), "SUMMARY:x")
            self.assertEqual(format_prop("A", {"tzid": "Europe/Oslo"}, "v"), "A;TZID=Europe/Oslo:v")
            self.assertEqual(format_prop("A", {"x": ["1", "2"], "y": "3"}, "v"), "A;X=1,2;Y=3:v")
            self.assertEqual(format_prop("A", {"x": []}, "v"), "A;X=:v")
            self.assertEqual(format_prop("A", {}, ""), "A:")

        def test_quoting(self):
            self.assertEqual(format_prop("A", {"cn": "Doe, Jane"}, "v"), 'A;CN="Doe, Jane":v')
            self.assertEqual(format_prop("A", {"cn": "a;b"}, "v"), 'A;CN="a;b":v')
            self.assertEqual(format_prop("A", {"cn": "a:b"}, "v"), 'A;CN="a:b":v')
            self.assertEqual(format_prop("A", {"m": ["plain", "with,comma"]}, "v"), 'A;M=plain,"with,comma":v')
            self.assertEqual(format_prop("A", {"m": "with space"}, "v"), "A;M=with space:v")
            self.assertEqual(format_prop("A", {"m": ""}, "v"), "A;M=:v")

        def test_value_is_not_escaped(self):
            self.assertEqual(format_prop("A", {}, "x;y:z,\\n"), "A:x;y:z,\\n")

        def test_errors(self):
            for args in (("", {}, "v"), ("A B", {}, "v"), ("A", {"b c": "x"}, "v"), ("A", {"": "x"}, "v"), ("A", {"x": 'a"b'}, "v"), ("A", {"x": ["ok", 'q"']}, "v"),
                         ("A:", {}, "v"), ("A;B", {}, "v")):
                with self.assertRaises(ValueError, msg=repr(args)):
                    format_prop(*args)

        def test_round_trip(self):
            for params in ({}, {"TZID": ["Europe/Oslo"]}, {"CN": ["Doe; Jane, Esq."], "ROLE": ["A", "B:C"]}, {"X": ["", "y"]}):
                line = format_prop("attendee", params, "mailto:a@b.c")
                p = parse_line(line)
                self.assertEqual((p.name, p.params, p.value), ("ATTENDEE", params, "mailto:a@b.c"))


    CAL = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        "SUMMARY:Planning\\, part 1\r\n"
        "DESCRIPTION:Agenda:\\n- one\\n- t\r\n"
        " wo\r\n"
        "X-NOTE:a\r\n"
        "X-NOTE:b\\;c\r\n"
        "BEGIN:VALARM\r\n"
        "TRIGGER:-PT15M\r\n"
        "END:VALARM\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "SUMMARY:Second\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )


    class Components(unittest.TestCase):
        def test_structure(self):
            top = parse_components(CAL)
            self.assertEqual(len(top), 1)
            cal = top[0]
            self.assertEqual(cal.name, "VCALENDAR")
            self.assertEqual([p.name for p in cal.props], ["VERSION"])
            self.assertEqual([c.name for c in cal.children], ["VEVENT", "VEVENT"])
            ev = cal.children[0]
            self.assertEqual([p.name for p in ev.props], ["SUMMARY", "DESCRIPTION", "X-NOTE", "X-NOTE"])
            self.assertEqual([c.name for c in ev.children], ["VALARM"])
            self.assertEqual(ev.children[0].props, [Prop("TRIGGER", {}, "-PT15M")])
            self.assertEqual(cal.children[1].props, [Prop("SUMMARY", {}, "Second")])
            self.assertEqual(cal.children[1].children, [])

        def test_unfolding_applies(self):
            ev = parse_components(CAL)[0].children[0]
            self.assertEqual(ev.props[1].value, "Agenda:\\n- one\\n- two")

        def test_values(self):
            ev = parse_components(CAL)[0].children[0]
            self.assertEqual(values(ev, "summary"), ["Planning, part 1"])
            self.assertEqual(values(ev, "DESCRIPTION"), ["Agenda:\n- one\n- two"])
            self.assertEqual(values(ev, "x-note"), ["a", "b;c"])
            self.assertEqual(values(ev, "TRIGGER"), [])
            self.assertEqual(values(ev, "NOPE"), [])

        def test_values_do_not_search_children(self):
            cal = parse_components(CAL)[0]
            self.assertEqual(values(cal, "SUMMARY"), [])
            self.assertEqual(values(cal, "version"), ["2.0"])

        def test_several_top_level_components(self):
            top = parse_components("BEGIN:A\nEND:A\nBEGIN:b\nX:1\nEND:B\n")
            self.assertEqual([c.name for c in top], ["A", "B"])
            self.assertEqual(top[1].props, [Prop("X", {}, "1")])

        def test_case_insensitive_names(self):
            top = parse_components("begin:vcalendar\nsummary:x\nend:VCalendar\n")
            self.assertEqual(top, [Component("VCALENDAR", [Prop("SUMMARY", {}, "x")], [])])

        def test_empty(self):
            self.assertEqual(parse_components(""), [])
            self.assertEqual(parse_components("\n\n"), [])

        def test_errors(self):
            for text in ("SUMMARY:x\n", "BEGIN:A\n", "BEGIN:A\nEND:B\n", "END:A\n", "BEGIN:A\nBEGIN:B\nEND:A\nEND:B\n", "BEGIN:A\nEND:A\nEND:A\n",
                         "BEGIN:A\nEND:A\nX:1\n", "BEGIN:A\nBEGIN:B\nEND:B\n", "BEGIN:A\nbad line\nEND:A\n", " BEGIN:A\nEND:A\n"):
                with self.assertRaises(ValueError, msg=repr(text)):
                    parse_components(text)

        def test_params_survive(self):
            top = parse_components('BEGIN:E\nDTSTART;TZID="Europe/Oslo":20250101T090000\nEND:E\n')
            self.assertEqual(top[0].props[0], Prop("DTSTART", {"TZID": ["Europe/Oslo"]}, "20250101T090000"))


    if __name__ == "__main__":
        unittest.main()
''')

ICS = Lib(
    name="icsfold", lang="python", title="the calendar content-line helpers (`icsfold.py`)",
    blurb="The team calendar imports and exports `.tcal` files, a line-folded text interchange format, with this module.",
    files={"icsfold.py": ICS_SRC, "README.md": ICS_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": ICS_VISIBLE},
    hidden_tests={"tests/test_full.py": ICS_HIDDEN},
    mutate=["icsfold.py"], difficulty=3, tags=["calendar", "parsing", "unicode"],
    probes=[
        'fold("a" * 29, 10)',
        'fold("\\u20ac" * 7, 10)',
        'fold("ab\\u20ac\\u20ac\\u20accd", 10)',
        'unfold("ab\\n  cd\\n \\n ef\\n")',
        'unescape_text("x\\\\Ny\\\\,")',
        'escape_text("a,b;c\\\\d\\r\\ne")',
        'parse_line("A;M=x;M=y,z;cn=\\"Doe; Jane\\":v:w")',
        'parse_line("A;M=,x:v").params',
        'format_prop("a", {"cn": ["Doe, Jane", "x"], "m": ""}, "v")',
        'parse_components("BEGIN:A\\nX:1\\nBEGIN:B\\nEND:B\\nEND:A\\n")',
        'values(parse_components("BEGIN:E\\nsummary:a\\\\,b\\nEND:E\\n")[0], "SUMMARY")',
    ],
    probe_import="from icsfold import *",
)


# ======================================================================================================================
# redactor: pattern-based redaction of sensitive tokens in log text
# ======================================================================================================================

RD_README = dd(r'''
    # redactor

    Scrubs sensitive tokens from text before it leaves the building. One module, `redactor.py`.

    ## Rules
    A `Rule` is a `namedtuple` `(name, pattern, validate, mask)`: `pattern` a compiled regex, `validate` a function from the matched
    text to `bool` (or `None` for no check) and `mask` a function from the matched text to its replacement. `DEFAULT_RULES` lists, in
    this order, `email`, `card`, `ipv4`, `secret`, `hexid`:

    | rule | what is found | replacement |
    |---|---|---|
    | `email` | `local@domain`: local part of `A-Za-z0-9._%+-` (not preceded by such a character), domain of dot-separated labels of `A-Za-z0-9-`, the last one 2+ letters and not followed by `A-Za-z0-9-` | the first character of the local part and `*` for the others; `@`; every domain label except the last as `*` of the same length; the last label unchanged: `ada.l@mail.example.org` becomes `a****@****.*******.org` |
    | `card` | 13 to 19 digits, optionally with a single space or `-` between any two digits, not preceded or followed by a digit; the number of digits must be 13 to 19 and the sum of the digits divisible by 10 | every digit except the last four replaced by `*`, separators kept |
    | `ipv4` | four numbers of 1-3 digits separated by dots, not preceded by a letter, digit, `_` or `.`, not followed by a letter, digit, `_` or by a dot and a digit; every number is `0`-`255` and has no leading zeros (except `0` itself) | the last two numbers replaced by `*`: `192.168.0.7` becomes `192.168.*.*` |
    | `secret` | `sk_`, `pk_` or `tok_` followed by 8 or more `A-Za-z0-9`, on word boundaries | `[secret]` |
    | `hexid` | 32 or more lower-case hex digits, not preceded or followed by `A-Za-z0-9` | the first 4 characters and `*` for the rest |

    `custom_rule(name, regex, replacement) -> Rule` builds a rule from a regex string (compiled as is) whose matches are replaced by the fixed
    text `replacement`, with no validation.

    ## `find_spans(text, rules=DEFAULT_RULES, allow=()) -> list[Span]`
    `Span` is a `namedtuple` `(start, end, rule)` (`rule` the rule name). Every match of every rule (found left to right per rule, without
    overlapping itself) that passes its `validate` and whose exact text is not in `allow` is a candidate. Overlaps between candidates are
    resolved greedily: candidates are taken in the order longest first, then earlier rule in `rules`, then smaller `start`; a candidate that
    overlaps one already taken is dropped. The result is sorted by `start`.

    ## `redact(text, rules=DEFAULT_RULES, allow=(), only=None, skip=()) -> str`
    Replaces every span by its rule's `mask` of the matched text. `only` (a collection of rule names, or `None` for all) keeps just those rules;
    `skip` removes rules by name; both are applied to `rules` before searching. Unknown names are ignored.

    ## `report(text, rules=DEFAULT_RULES, allow=()) -> dict`
    How many spans each rule produced after overlap resolution, only rules with at least one, with the keys in alphabetical order.
''')

RD_SRC = dd(r'''
    """Pattern-based redaction."""
    import re
    from collections import namedtuple

    Rule = namedtuple("Rule", "name pattern validate mask")
    Span = namedtuple("Span", "start end rule")


    def _mask_email(s):
        local, _, domain = s.partition("@")
        labels = domain.split(".")
        masked = [("*" * len(label)) for label in labels[:-1]] + [labels[-1]]
        return local[0] + "*" * (len(local) - 1) + "@" + ".".join(masked)


    def _mask_card(s):
        total = sum(c.isdigit() for c in s)
        seen = 0
        out = []
        for c in s:
            if c.isdigit():
                seen += 1
                out.append(c if seen > total - 4 else "*")
            else:
                out.append(c)
        return "".join(out)


    def _valid_card(s):
        digits = [int(c) for c in s if c.isdigit()]
        return 13 <= len(digits) <= 19 and sum(digits) % 10 == 0


    def _valid_ipv4(s):
        for part in s.split("."):
            if int(part) > 255 or (len(part) > 1 and part[0] == "0"):
                return False
        return True


    def _mask_ipv4(s):
        parts = s.split(".")
        return ".".join(parts[:2] + ["*", "*"])


    DEFAULT_RULES = [
        Rule("email",
             re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?![A-Za-z0-9-])"),
             None, _mask_email),
        Rule("card", re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"), _valid_card, _mask_card),
        Rule("ipv4", re.compile(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?![\w])(?!\.\d)"), _valid_ipv4, _mask_ipv4),
        Rule("secret", re.compile(r"\b(?:sk|pk|tok)_[A-Za-z0-9]{8,}\b"), None, lambda s: "[secret]"),
        Rule("hexid", re.compile(r"(?<![A-Za-z0-9])[0-9a-f]{32,}(?![A-Za-z0-9])"), None, lambda s: s[:4] + "*" * (len(s) - 4)),
    ]


    def custom_rule(name, regex, replacement):
        return Rule(name, re.compile(regex), None, lambda s: replacement)


    def find_spans(text, rules=DEFAULT_RULES, allow=()):
        cands = []
        for index, rule in enumerate(rules):
            for m in rule.pattern.finditer(text):
                s = m.group()
                if rule.validate is not None and not rule.validate(s):
                    continue
                if s in allow:
                    continue
                cands.append((-(m.end() - m.start()), index, m.start(), m.end(), rule.name))
        cands.sort()
        taken = []
        for _, _, start, end, name in cands:
            if all(end <= a or start >= b for a, b, _ in taken):
                taken.append((start, end, name))
        return [Span(*t) for t in sorted(taken)]


    def redact(text, rules=DEFAULT_RULES, allow=(), only=None, skip=()):
        chosen = [r for r in rules if (only is None or r.name in only) and r.name not in skip]
        by_name = {r.name: r for r in chosen}
        out = []
        pos = 0
        for span in find_spans(text, chosen, allow):
            out.append(text[pos:span.start])
            out.append(by_name[span.rule].mask(text[span.start:span.end]))
            pos = span.end
        out.append(text[pos:])
        return "".join(out)


    def report(text, rules=DEFAULT_RULES, allow=()):
        counts = {}
        for span in find_spans(text, rules, allow):
            counts[span.rule] = counts.get(span.rule, 0) + 1
        return {k: counts[k] for k in sorted(counts)}
''')

RD_VISIBLE = dd(r'''
    import unittest

    from redactor import redact, report


    class BasicTests(unittest.TestCase):
        def test_email(self):
            self.assertEqual(redact("mail ada.l@mail.example.org now"), "mail a****@****.*******.org now")

        def test_ipv4(self):
            self.assertEqual(redact("from 192.168.0.7 ok"), "from 192.168.*.* ok")

        def test_report(self):
            self.assertEqual(report("a@b.org and 10.0.0.1"), {"email": 1, "ipv4": 1})


    if __name__ == "__main__":
        unittest.main()
''')

RD_HIDDEN = dd(r'''
    import re
    import unittest

    from redactor import DEFAULT_RULES, Span, custom_rule, find_spans, redact, report


    class Email(unittest.TestCase):
        def test_masking(self):
            self.assertEqual(redact("ada.l@mail.example.org"), "a****@****.*******.org")
            self.assertEqual(redact("a@b.org"), "a@*.org")
            self.assertEqual(redact("ab@cd.io"), "a*@**.io")
            self.assertEqual(redact("john.doe+tag@sub.dom-ain.co.uk"), "j" + "*" * 11 + "@***.*******.**.uk")

        def test_exact_masks(self):
            self.assertEqual(redact("x_y.z@my-host.com"), "x****@*******.com")
            self.assertEqual(redact("name@a.b.c.dd"), "n***@*.*.*.dd")
            self.assertEqual(redact("n@host.museum"), "n@****.museum")

        def test_context(self):
            self.assertEqual(redact("mail: bob@x.org."), "mail: b**@*.org.")
            self.assertEqual(redact("<bob@x.org>, (cy@y.io);"), "<b**@*.org>, (c*@*.io);")
            self.assertEqual(redact("a@b.org,c@d.org"), "a@*.org,c@*.org")

        def test_not_emails(self):
            for text in ("no at sign.org", "@host.org", "user@host", "user@host.c", "user@.org", "user@host..org", "a @ b.org"):
                self.assertEqual(redact(text, only={"email"}), text, text)

        def test_tld_must_be_letters_and_end(self):
            self.assertEqual(redact("a@b.org1"), "a@b.org1")
            self.assertEqual(redact("a@b.o-g"), "a@b.o-g")
            self.assertEqual(redact("a@b.c1.org"), "a@*.**.org")

        def test_not_preceded_by_local_chars(self):
            self.assertEqual(redact("x@y@z.org"), "x@y@*.org")


    class Card(unittest.TestCase):
        def test_masking_keeps_last_four(self):
            self.assertEqual(redact("4242424242424244"), "************4244")
            self.assertEqual(redact("4242 4242 4242 4244"), "**** **** **** 4244")
            self.assertEqual(redact("4242-4242-4242-4244"), "****-****-****-4244")

        def test_digit_sum_rule(self):
            self.assertEqual(redact("4242424242424245"), "4242424242424245")
            self.assertEqual(redact("4242424242424243"), "4242424242424243")
            self.assertEqual(redact("5500000000000000"), "************0000")
            self.assertEqual(redact("5500000000000001"), "5500000000000001")
            self.assertEqual(redact("0000000000000"), "*********0000")

        def test_length_limits(self):
            self.assertEqual(redact("1234567890123"), "1234567890123")
            self.assertEqual(redact("0000000000000"), "*" * 9 + "0000")
            self.assertEqual(redact("000000000000"), "000000000000")
            self.assertEqual(redact("0" * 19), "*" * 15 + "0000")
            self.assertEqual(redact("0" * 20), "0" * 20)
            self.assertEqual(redact("0" * 14), "*" * 10 + "0000")

        def test_not_inside_longer_digit_runs(self):
            self.assertEqual(redact("a4242424242424244b"), "a************4244b")
            self.assertEqual(redact("x" + "0" * 20 + "y"), "x" + "0" * 20 + "y")

        def test_mixed_separators_and_context(self):
            self.assertEqual(redact("card 5500 0000-0000 0000 ok"), "card **** ****-**** 0000 ok")
            self.assertEqual(redact("pay 4242424242424244."), "pay ************4244.")

        def test_double_separator_breaks(self):
            self.assertEqual(redact("4242  4242  4242  4244"), "4242  4242  4242  4244")


    class Ipv4(unittest.TestCase):
        def test_masking(self):
            self.assertEqual(redact("192.168.0.7"), "192.168.*.*")
            self.assertEqual(redact("10.0.0.1 and 8.8.8.8"), "10.0.*.* and 8.8.*.*")
            self.assertEqual(redact("host 255.255.255.255!"), "host 255.255.*.*!")
            self.assertEqual(redact("0.0.0.0"), "0.0.*.*")

        def test_octet_validation(self):
            for bad in ("256.1.1.1", "1.2.3.256", "1.1.1.300", "999.999.999.999", "01.2.3.4", "1.2.3.04", "1.02.3.4", "1.2.003.4"):
                self.assertEqual(redact(bad, only={"ipv4"}), bad, bad)
            self.assertEqual(redact("1.2.3.0"), "1.2.*.*")
            self.assertEqual(redact("100.200.30.40"), "100.200.*.*")

        def test_context_rules(self):
            for text in ("1.2.3.4.5", "v1.2.3.4", "_1.2.3.4", "1.2.3.4a", "1.2.3.4_", "a1.2.3.4", "1.2.3.4.5.6", "1.2.3", ".1.2.3.4", "11.22.33.4444"):
                self.assertEqual(redact(text, only={"ipv4"}), text, text)
            self.assertEqual(redact("at 1.2.3.4."), "at 1.2.*.*.")
            self.assertEqual(redact("(1.2.3.4)"), "(1.2.*.*)")
            self.assertEqual(redact("1.2.3.4,5.6.7.8"), "1.2.*.*,5.6.*.*")
            self.assertEqual(redact("ip=1.2.3.4"), "ip=1.2.*.*")
            self.assertEqual(redact("1.2.3.4-5.6.7.8"), "1.2.*.*-5.6.*.*")


    class SecretsAndIds(unittest.TestCase):
        def test_secret(self):
            self.assertEqual(redact("key sk_abcdefgh12 end"), "key [secret] end")
            self.assertEqual(redact("pk_ABCDEFGH tok_12345678"), "[secret] [secret]")
            self.assertEqual(redact("sk_abcdefg"), "sk_abcdefg")
            self.assertEqual(redact("sk_abcdefgh"), "[secret]")
            self.assertEqual(redact("xsk_abcdefgh12"), "xsk_abcdefgh12")
            self.assertEqual(redact("sk_abcdefgh12_more"), "sk_abcdefgh12_more")
            self.assertEqual(redact("api_abcdefgh12"), "api_abcdefgh12")
            self.assertEqual(redact("sk-abcdefgh12"), "sk-abcdefgh12")

        def test_hexid(self):
            h32 = "0123456789abcdef0123456789abcdef"
            self.assertEqual(redact("id " + h32), "id 0123" + "*" * 28)
            self.assertEqual(redact(h32[:31]), h32[:31])
            self.assertEqual(redact(h32 + "0"), "0123" + "*" * 29)
            self.assertEqual(redact("x" + h32), "x" + h32)
            self.assertEqual(redact(h32 + "g"), h32 + "g")
            self.assertEqual(redact(h32.upper()), h32.upper())
            self.assertEqual(redact("(" + h32 + ")"), "(0123" + "*" * 28 + ")")
            self.assertEqual(redact("a" * 40), "aaaa" + "*" * 36)

        def test_hexid_is_not_a_card(self):
            self.assertEqual(redact("0" * 32), "0000" + "*" * 28)


    class Spans(unittest.TestCase):
        def test_sorted_and_positions(self):
            text = "to a@b.org via 1.2.3.4 key sk_abcdefgh12"
            spans = find_spans(text)
            self.assertEqual(spans, [Span(3, 10, "email"), Span(15, 22, "ipv4"), Span(27, 40, "secret")])
            self.assertEqual(text[3:10], "a@b.org")

        def test_longest_wins(self):
            h = "0123456789abcdef0123456789abcdef"
            text = h + "@x.org"
            self.assertEqual(find_spans(text), [Span(0, len(text), "email")])
            self.assertEqual(redact(text), "0" + "*" * 31 + "@*.org")

        def test_equal_length_goes_to_earlier_rule(self):
            a = custom_rule("first", r"abcd", "[1]")
            b = custom_rule("second", r"abcd", "[2]")
            self.assertEqual(find_spans("xabcdx", [a, b]), [Span(1, 5, "first")])
            self.assertEqual(find_spans("xabcdx", [b, a]), [Span(1, 5, "second")])
            self.assertEqual(redact("xabcdx", [b, a]), "x[2]x")

        def test_equal_length_overlap_goes_to_earlier_rule(self):
            r = custom_rule("r", r"ab|bc", "#")
            self.assertEqual(find_spans("abc", [r]), [Span(0, 2, "r")])
            r2 = custom_rule("p", r"bc", "#")
            r1 = custom_rule("q", r"ab", "@")
            self.assertEqual(find_spans("abc", [r1, r2]), [Span(0, 2, "q")])
            self.assertEqual(find_spans("abc", [r2, r1]), [Span(1, 3, "p")])

        def test_longer_beats_earlier_rule(self):
            short = custom_rule("short", r"ab", "[s]")
            long_ = custom_rule("long", r"abc", "[l]")
            self.assertEqual(find_spans("abc", [short, long_]), [Span(0, 3, "long")])
            self.assertEqual(redact("abcab", [short, long_]), "[l][s]")

        def test_adjacent_spans_do_not_overlap(self):
            r = custom_rule("r", r"ab|cd", "#")
            self.assertEqual(find_spans("abcd", [r]), [Span(0, 2, "r"), Span(2, 4, "r")])
            self.assertEqual(redact("abcd", [r]), "##")

        def test_no_matches(self):
            self.assertEqual(find_spans("nothing here"), [])
            self.assertEqual(find_spans(""), [])
            self.assertEqual(redact(""), "")
            self.assertEqual(redact("plain text"), "plain text")

        def test_allow_list(self):
            text = "noreply@example.org and bob@example.org"
            self.assertEqual(redact(text, allow=["noreply@example.org"]), "noreply@example.org and b**@*******.org")
            self.assertEqual(redact(text, allow=("noreply@example.org", "bob@example.org")), text)
            self.assertEqual(report(text, allow={"noreply@example.org"}), {"email": 1})

        def test_allowed_candidate_does_not_block_others(self):
            h = "0123456789abcdef0123456789abcdef"
            text = h + "@x.org"
            self.assertEqual(redact(text, allow=[text]), "0123" + "*" * 28 + "@x.org")


    class OnlySkipAndCustom(unittest.TestCase):
        TEXT = "a@b.org 1.2.3.4 sk_abcdefgh12"

        def test_only(self):
            self.assertEqual(redact(self.TEXT, only={"ipv4"}), "a@b.org 1.2.*.* sk_abcdefgh12")
            self.assertEqual(redact(self.TEXT, only=["email", "secret"]), "a@*.org 1.2.3.4 [secret]")
            self.assertEqual(redact(self.TEXT, only=[]), self.TEXT)
            self.assertEqual(redact(self.TEXT, only={"nope"}), self.TEXT)

        def test_skip(self):
            self.assertEqual(redact(self.TEXT, skip={"email"}), "a@b.org 1.2.*.* [secret]")
            self.assertEqual(redact(self.TEXT, skip=["email", "ipv4", "secret"]), self.TEXT)
            self.assertEqual(redact(self.TEXT, skip=["nope"]), "a@*.org 1.2.*.* [secret]")

        def test_only_and_skip_together(self):
            self.assertEqual(redact(self.TEXT, only={"email", "ipv4"}, skip={"ipv4"}), "a@*.org 1.2.3.4 sk_abcdefgh12")

        def test_filtering_happens_before_overlap_resolution(self):
            h = "0123456789abcdef0123456789abcdef"
            text = h + "@x.org"
            self.assertEqual(redact(text, skip={"email"}), "0123" + "*" * 28 + "@x.org")
            self.assertEqual(redact(text, only={"hexid"}), "0123" + "*" * 28 + "@x.org")

        def test_custom_rule(self):
            r = custom_rule("ticket", r"TKT-\d+", "[ticket]")
            self.assertEqual(redact("see TKT-123 and TKT-9", [r]), "see [ticket] and [ticket]")
            self.assertEqual(redact("see TKT-123 a@b.org", DEFAULT_RULES + [r]), "see [ticket] a@*.org")
            self.assertEqual(r.validate, None)
            self.assertIsInstance(r.pattern, type(re.compile("x")))

        def test_default_rule_names_and_order(self):
            self.assertEqual([r.name for r in DEFAULT_RULES], ["email", "card", "ipv4", "secret", "hexid"])


    class Report(unittest.TestCase):
        def test_counts(self):
            text = "card 4242424242424244 ok a@b.org c@d.org 1.2.3.4 sk_abcdefgh12 sk_12345678ab"
            self.assertEqual(report(text), {"card": 1, "email": 2, "ipv4": 1, "secret": 2})
            self.assertEqual(list(report(text)), ["card", "email", "ipv4", "secret"])

        def test_empty_and_overlap_resolution(self):
            self.assertEqual(report("nothing"), {})
            h = "0123456789abcdef0123456789abcdef"
            self.assertEqual(report(h + "@x.org"), {"email": 1})
            self.assertEqual(report(h), {"hexid": 1})


    if __name__ == "__main__":
        unittest.main()
''')

RD = Lib(
    name="redactor", lang="python", title="the log redactor (`redactor.py`)",
    blurb="The support tooling scrubs emails, card numbers, addresses and secrets from logs with this module before sharing them.",
    files={"redactor.py": RD_SRC, "README.md": RD_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": RD_VISIBLE},
    hidden_tests={"tests/test_full.py": RD_HIDDEN},
    mutate=["redactor.py"], difficulty=3, tags=["security", "text", "regex"],
    probes=[
        'redact("mail ada.l@mail.example.org now")',
        'redact("a@b.org,c@d.org (e@f.io)")',
        'redact("4242-4242-4242-4244 and 4242424242424245")',
        'redact("0000000000000 000000000000")',
        'redact("1.2.3.4. 256.1.1.1 01.2.3.4 1.2.3.4.5")',
        'redact("sk_abcdefgh12 sk_abcdefg")',
        'redact("0123456789abcdef0123456789abcdef@x.org")',
        'find_spans("to a@b.org via 1.2.3.4")',
        'redact("noreply@example.org and bob@example.org", allow=["noreply@example.org"])',
        'redact("a@b.org 1.2.3.4", only={"ipv4"})',
        'report("a@b.org c@d.org 1.2.3.4 sk_abcdefgh12")',
    ],
    probe_import="from redactor import *",
)


LIBS = [CT, ICS, RD]
register_libs(LIBS, n=10)
