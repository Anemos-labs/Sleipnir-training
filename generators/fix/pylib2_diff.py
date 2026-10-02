"""Text-format libraries (python), batch: diff/patch, changelog, page specs."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# linepatch: line diffs in a house hunk format, with offset-tolerant patching
# ======================================================================================================================

LP_README = dd(r'''
    # linepatch

    Line-based diff and patch for the config-sync agent. The hunk format is its own ("stitch" format). Everything is
    in the package `linepatch`: `linepatch.diff` (diff and statistics) and `linepatch.stitch` (text format and patching).

    ## Lines
    `lines(text) -> list[str]` splits on `\n`; a final empty piece caused by a trailing newline is dropped (`""` gives `[]`,
    `"a\n"` and `"a"` both give `["a"]`). `unlines(lines) -> str` writes every line followed by `\n` (`[]` gives `""`).

    ## Hunks
    `Hunk` is a `namedtuple` `(start, removed, added)`: `start` is a 1-based line number **in the old text**, `removed` and
    `added` are tuples of lines. The hunk replaces the old lines `start .. start+len(removed)-1` by `added`. With nothing
    removed, `added` is inserted before old line `start` (`start == len(old) + 1` appends).

    ## `diff(old, new) -> list[Hunk]` (`old`, `new` are lists of lines)
    The hunks that turn `old` into `new`, in ascending order, built from this exact walk. Let `L[i][j]` be the length of a
    longest common subsequence of `old[i:]` and `new[j:]`. Start at `i = j = 0`: if `old[i] == new[j]` the lines match and both
    advance; otherwise, if `j` is past the end, or `i` is not and `L[i+1][j] >= L[i][j+1]`, the line `old[i]` is *removed*
    (`i` advances); otherwise `new[j]` is *added* (`j` advances). A maximal run of non-matching steps is one hunk
    (all its removed lines, all its added lines, each in order); its `start` is `i + 1` for the `i` at the beginning of
    the run. Equal inputs give `[]`.

    ## `stats(hunks) -> (added, removed)`
    Total numbers of added and removed lines.

    ## `format_patch(hunks) -> str` and `parse_patch(text) -> list[Hunk]`
    The text of a hunk is a header line `@ START -NR +NA` followed by NR lines `-` + removed line and then NA lines `+` +
    added line (so an empty line is just `-` or `+`). Every line ends with `\n`. Hunks follow each other. Parsing: lines that are empty
    or start with `#` are ignored between hunks; a header with `START` below 1, a missing or wrongly marked line, or any other
    text where a header is expected raises `PatchError` (a `ValueError`). `parse_patch(format_patch(h)) == h`.

    ## `apply_patch(old, hunks, max_shift=0) -> list[str]`
    Applies `hunks` (ascending, non-overlapping) to the list of lines `old`; the input is not modified. Every hunk that removes lines
    must find exactly those lines. The expected place of a hunk is `start - 1 + shift` (0-based; `shift` starts at 0). The hunk is
    applied at the first place that matches in the order `shift+0, -1, +1, -2, +2, ...` up to `max_shift` away from the expected
    place, but never before the end of the previous hunk and never beyond the end of `old`. The distance found is added to `shift`
    for all later hunks. Hunks that remove nothing are inserted at their expected place (they are checked only for the range:
    after the previous hunk, at most at the end of `old`). If a hunk finds no place, or the range is violated, `PatchError`
    with a message that contains `hunk N` (N counts from 1).

    ## `invert(hunks) -> list[Hunk]`
    The hunks that turn the new text back into the old one: removed and added swapped, and each `start` moved to its position in
    the new text (shifted by the net growth of all earlier hunks). `apply_patch(new, invert(diff(old, new))) == old`.
''')

LP_DIFF = dd(r'''
    """Line diff and statistics."""
    from collections import namedtuple

    Hunk = namedtuple("Hunk", "start removed added")


    def lines(text):
        parts = text.split("\n")
        if parts and parts[-1] == "":
            parts.pop()
        return parts


    def unlines(items):
        return "".join(line + "\n" for line in items)


    def diff(old, new):
        n, m = len(old), len(new)
        lcs = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(n - 1, -1, -1):
            for j in range(m - 1, -1, -1):
                if old[i] == new[j]:
                    lcs[i][j] = lcs[i + 1][j + 1] + 1
                else:
                    lcs[i][j] = max(lcs[i + 1][j], lcs[i][j + 1])
        hunks = []
        cur = None
        i = j = 0
        while i < n or j < m:
            if i < n and j < m and old[i] == new[j]:
                if cur is not None:
                    hunks.append(Hunk(cur[0], tuple(cur[1]), tuple(cur[2])))
                    cur = None
                i += 1
                j += 1
                continue
            if cur is None:
                cur = [i + 1, [], []]
            if j >= m or (i < n and lcs[i + 1][j] >= lcs[i][j + 1]):
                cur[1].append(old[i])
                i += 1
            else:
                cur[2].append(new[j])
                j += 1
        if cur is not None:
            hunks.append(Hunk(cur[0], tuple(cur[1]), tuple(cur[2])))
        return hunks


    def stats(hunks):
        return (sum(len(h.added) for h in hunks), sum(len(h.removed) for h in hunks))
''')

LP_STITCH = dd(r'''
    """The stitch hunk format and patching."""
    import re

    from .diff import Hunk


    class PatchError(ValueError):
        pass


    _HEADER = re.compile(r"@ (\d+) -(\d+) \+(\d+)")


    def format_patch(hunks):
        out = []
        for h in hunks:
            out.append("@ %d -%d +%d\n" % (h.start, len(h.removed), len(h.added)))
            out.extend("-" + line + "\n" for line in h.removed)
            out.extend("+" + line + "\n" for line in h.added)
        return "".join(out)


    def parse_patch(text):
        ls = text.split("\n")
        if ls and ls[-1] == "":
            ls.pop()
        hunks = []
        i = 0
        while i < len(ls):
            line = ls[i]
            if line == "" or line.startswith("#"):
                i += 1
                continue
            m = _HEADER.fullmatch(line)
            if not m:
                raise PatchError("expected a hunk header, got %r" % line)
            start, nr, na = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if start < 1:
                raise PatchError("hunk %d: start must be at least 1" % (len(hunks) + 1))
            body = ls[i + 1:i + 1 + nr + na]
            if len(body) < nr + na:
                raise PatchError("hunk %d: truncated" % (len(hunks) + 1))
            removed, added = body[:nr], body[nr:]
            if any(not b.startswith("-") for b in removed) or any(not b.startswith("+") for b in added):
                raise PatchError("hunk %d: bad line marker" % (len(hunks) + 1))
            hunks.append(Hunk(start, tuple(b[1:] for b in removed), tuple(b[1:] for b in added)))
            i += 1 + nr + na
        return hunks


    def _find(old, removed, want, max_shift, lower):
        for d in range(max_shift + 1):
            for cand in ([want] if d == 0 else [want - d, want + d]):
                if lower <= cand <= len(old) - len(removed) and tuple(old[cand:cand + len(removed)]) == tuple(removed):
                    return cand
        return None


    def apply_patch(old, hunks, max_shift=0):
        out = []
        pos = 0
        shift = 0
        for k, h in enumerate(hunks, 1):
            want = h.start - 1 + shift
            if h.removed:
                at = _find(old, h.removed, want, max_shift, pos)
                if at is None:
                    raise PatchError("hunk %d does not match" % k)
                shift += at - want
            else:
                at = want
                if not (pos <= at <= len(old)):
                    raise PatchError("hunk %d is out of range" % k)
            out.extend(old[pos:at])
            out.extend(h.added)
            pos = at + len(h.removed)
        out.extend(old[pos:])
        return out


    def invert(hunks):
        out = []
        growth = 0
        for h in hunks:
            out.append(Hunk(h.start + growth, h.added, h.removed))
            growth += len(h.added) - len(h.removed)
        return out
''')

LP_INIT = dd(r'''
    from .diff import Hunk, diff, lines, stats, unlines  # noqa: F401
    from .stitch import PatchError, apply_patch, format_patch, invert, parse_patch  # noqa: F401
''')

LP_VISIBLE = dd(r'''
    import unittest

    from linepatch import Hunk, apply_patch, diff, format_patch, lines, parse_patch


    class BasicTests(unittest.TestCase):
        def test_lines(self):
            self.assertEqual(lines("a\nb\n"), ["a", "b"])

        def test_diff_and_apply(self):
            old, new = ["a", "b", "c"], ["a", "x", "c"]
            h = diff(old, new)
            self.assertEqual(h, [Hunk(2, ("b",), ("x",))])
            self.assertEqual(apply_patch(old, h), new)

        def test_format(self):
            self.assertEqual(format_patch([Hunk(2, ("b",), ("x", "y"))]), "@ 2 -1 +2\n-b\n+x\n+y\n")
            self.assertEqual(parse_patch("@ 2 -1 +2\n-b\n+x\n+y\n"), [Hunk(2, ("b",), ("x", "y"))])


    if __name__ == "__main__":
        unittest.main()
''')

LP_HIDDEN = dd(r'''
    import random
    import unittest

    from linepatch import (Hunk, PatchError, apply_patch, diff, format_patch, invert, lines, parse_patch, stats,
                           unlines)


    class Lines(unittest.TestCase):
        def test_lines(self):
            self.assertEqual(lines(""), [])
            self.assertEqual(lines("a"), ["a"])
            self.assertEqual(lines("a\n"), ["a"])
            self.assertEqual(lines("a\nb"), ["a", "b"])
            self.assertEqual(lines("a\n\n"), ["a", ""])
            self.assertEqual(lines("\n"), [""])
            self.assertEqual(lines("\n\nx"), ["", "", "x"])
            self.assertEqual(lines("a\r\nb\n"), ["a\r", "b"])

        def test_unlines(self):
            self.assertEqual(unlines([]), "")
            self.assertEqual(unlines(["a"]), "a\n")
            self.assertEqual(unlines(["a", "", "b"]), "a\n\nb\n")
            self.assertEqual(lines(unlines(["x", "", ""])), ["x", "", ""])


    class Diff(unittest.TestCase):
        def test_equal(self):
            self.assertEqual(diff([], []), [])
            self.assertEqual(diff(["a", "b"], ["a", "b"]), [])

        def test_pure_insert(self):
            self.assertEqual(diff(["a", "c"], ["a", "b", "c"]), [Hunk(2, (), ("b",))])
            self.assertEqual(diff([], ["x", "y"]), [Hunk(1, (), ("x", "y"))])
            self.assertEqual(diff(["a"], ["a", "b", "c"]), [Hunk(2, (), ("b", "c"))])
            self.assertEqual(diff(["a"], ["z", "a"]), [Hunk(1, (), ("z",))])

        def test_pure_delete(self):
            self.assertEqual(diff(["a", "b", "c"], ["a", "c"]), [Hunk(2, ("b",), ())])
            self.assertEqual(diff(["x", "y"], []), [Hunk(1, ("x", "y"), ())])
            self.assertEqual(diff(["a", "b", "c"], ["c"]), [Hunk(1, ("a", "b"), ())])
            self.assertEqual(diff(["a", "b", "c"], ["a"]), [Hunk(2, ("b", "c"), ())])

        def test_replace(self):
            self.assertEqual(diff(["a", "b", "c"], ["a", "x", "c"]), [Hunk(2, ("b",), ("x",))])
            self.assertEqual(diff(["a", "b"], ["x", "y", "z"]), [Hunk(1, ("a", "b"), ("x", "y", "z"))])

        def test_several_hunks(self):
            old = ["a", "b", "c", "d", "e", "f"]
            new = ["a", "B", "c", "d", "f", "g"]
            self.assertEqual(diff(old, new), [Hunk(2, ("b",), ("B",)), Hunk(5, ("e",), ()), Hunk(7, (), ("g",))])

        def test_start_of_insertions_counts_old_lines(self):
            self.assertEqual(diff(["a", "b", "c"], ["a", "b", "x", "c", "y"]), [Hunk(3, (), ("x",)), Hunk(4, (), ("y",))])

        def test_tie_breaking_deletes_first(self):
            self.assertEqual(diff(["a", "b"], ["b", "a"]), [Hunk(1, ("a",), ()), Hunk(3, (), ("a",))])
            self.assertEqual(diff(["x"], ["y"]), [Hunk(1, ("x",), ("y",))])
            self.assertEqual(diff(["a", "a"], ["a"]), [Hunk(2, ("a",), ())])
            self.assertEqual(diff(["a"], ["a", "a"]), [Hunk(2, (), ("a",))])

        def test_prefers_longest_common_subsequence(self):
            old = ["1", "2", "3", "4", "5"]
            new = ["2", "3", "4", "5", "6"]
            self.assertEqual(diff(old, new), [Hunk(1, ("1",), ()), Hunk(6, (), ("6",))])
            old = ["a", "x", "b", "y", "c"]
            new = ["a", "b", "c"]
            self.assertEqual(diff(old, new), [Hunk(2, ("x",), ()), Hunk(4, ("y",), ())])

        def test_repeated_lines(self):
            old = ["x", "", "x", "", "x"]
            new = ["x", "", "x"]
            self.assertEqual(apply_patch(old, diff(old, new)), new)
            self.assertEqual(stats(diff(old, new)), (0, 2))

        def test_interleaved_run_is_one_hunk(self):
            self.assertEqual(diff(["a", "b", "c"], ["x", "y", "z"]), [Hunk(1, ("a", "b", "c"), ("x", "y", "z"))])
            self.assertEqual(diff(["k", "a", "b", "m"], ["k", "x", "m"]), [Hunk(2, ("a", "b"), ("x",))])

        def test_inputs_not_modified(self):
            old, new = ["a", "b"], ["b", "c"]
            diff(old, new)
            self.assertEqual((old, new), (["a", "b"], ["b", "c"]))


    class Stats(unittest.TestCase):
        def test_counts(self):
            self.assertEqual(stats([]), (0, 0))
            self.assertEqual(stats([Hunk(1, ("a", "b"), ("x",)), Hunk(5, (), ("y", "z"))]), (3, 2))
            self.assertEqual(stats(diff(["a", "b", "c"], ["a", "x", "y", "c"])), (2, 1))


    class Format(unittest.TestCase):
        def test_format(self):
            hunks = [Hunk(2, ("b", ""), ("x",)), Hunk(7, (), ("y", "")), Hunk(9, ("z",), ())]
            text = "@ 2 -2 +1\n-b\n-\n+x\n@ 7 -0 +2\n+y\n+\n@ 9 -1 +0\n-z\n"
            self.assertEqual(format_patch(hunks), text)
            self.assertEqual(parse_patch(text), hunks)
            self.assertEqual(format_patch([]), "")
            self.assertEqual(parse_patch(""), [])

        def test_lines_with_markers_inside(self):
            hunks = [Hunk(1, ("-x", "+y", "@ 1 -1 +1"), ("#c", "- d"))]
            self.assertEqual(parse_patch(format_patch(hunks)), hunks)

        def test_parse_ignores_blank_and_comments_between_hunks(self):
            text = "# sync patch\n\n@ 1 -1 +1\n-a\n+b\n\n# next\n@ 4 -0 +1\n+c\n"
            self.assertEqual(parse_patch(text), [Hunk(1, ("a",), ("b",)), Hunk(4, (), ("c",))])

        def test_parse_without_final_newline(self):
            self.assertEqual(parse_patch("@ 1 -1 +0\n-a"), [Hunk(1, ("a",), ())])

        def test_parse_errors(self):
            bad = [
                "garbage\n", "@ 0 -1 +0\n-a\n", "@ 1 -2 +0\n-a\n", "@ 1 -1 +1\n-a\n", "@ 1 -1 +1\n+a\n+b\n", "@ 1 -1 +0\n+a\n",
                "@ 1 -0 +1\n-a\n", "@ 1 -1 +1 \n-a\n+b\n", "@1 -1 +1\n-a\n+b\n", "@ 1 -1 +1\n-a\n+b\nextra\n", "@ x -1 +1\n-a\n+b\n",
                "@ 1 -1 +0\n a\n", "@ -1 -1 +0\n-a\n",
            ]
            for text in bad:
                with self.assertRaises(PatchError, msg=repr(text)):
                    parse_patch(text)

        def test_patch_error_is_value_error(self):
            self.assertTrue(issubclass(PatchError, ValueError))

        def test_round_trip_of_diff(self):
            old = ["a", "b", "", "c", "d"]
            new = ["a", "", "x", "d", "e", ""]
            h = diff(old, new)
            self.assertEqual(parse_patch(format_patch(h)), h)


    class Apply(unittest.TestCase):
        OLD = ["l1", "l2", "l3", "l4", "l5", "l6"]

        def test_basic(self):
            self.assertEqual(apply_patch(self.OLD, [Hunk(2, ("l2",), ("L2", "L2b"))]), ["l1", "L2", "L2b", "l3", "l4", "l5", "l6"])
            self.assertEqual(apply_patch(self.OLD, [Hunk(1, ("l1", "l2"), ())]), ["l3", "l4", "l5", "l6"])
            self.assertEqual(apply_patch(self.OLD, [Hunk(5, ("l5", "l6"), ())]), ["l1", "l2", "l3", "l4"])
            self.assertEqual(apply_patch(self.OLD, []), self.OLD)

        def test_insertions_and_appends(self):
            self.assertEqual(apply_patch(self.OLD, [Hunk(1, (), ("top",))])[:2], ["top", "l1"])
            self.assertEqual(apply_patch(self.OLD, [Hunk(7, (), ("end",))])[-2:], ["l6", "end"])
            self.assertEqual(apply_patch([], [Hunk(1, (), ("a", "b"))]), ["a", "b"])
            self.assertEqual(apply_patch(self.OLD, [Hunk(4, (), ("x",))]), ["l1", "l2", "l3", "x", "l4", "l5", "l6"])

        def test_several_hunks_use_old_coordinates(self):
            hunks = [Hunk(1, (), ("n1", "n2")), Hunk(3, ("l3",), ()), Hunk(6, ("l6",), ("z",))]
            self.assertEqual(apply_patch(self.OLD, hunks), ["n1", "n2", "l1", "l2", "l4", "l5", "z"])

        def test_adjacent_hunks(self):
            hunks = [Hunk(2, ("l2",), ("a",)), Hunk(3, ("l3",), ("b",))]
            self.assertEqual(apply_patch(self.OLD, hunks), ["l1", "a", "b", "l4", "l5", "l6"])
            hunks = [Hunk(2, ("l2",), ()), Hunk(3, (), ("ins",))]
            self.assertEqual(apply_patch(self.OLD, hunks), ["l1", "ins", "l3", "l4", "l5", "l6"])

        def test_input_not_modified(self):
            old = list(self.OLD)
            apply_patch(old, [Hunk(2, ("l2",), ())])
            self.assertEqual(old, self.OLD)

        def test_mismatch_raises_with_hunk_number(self):
            with self.assertRaises(PatchError) as cm:
                apply_patch(self.OLD, [Hunk(1, ("l1",), ()), Hunk(3, ("nope",), ())])
            self.assertIn("hunk 2", str(cm.exception))
            with self.assertRaises(PatchError) as cm:
                apply_patch(self.OLD, [Hunk(2, ("l3",), ())])
            self.assertIn("hunk 1", str(cm.exception))

        def test_multi_line_removal_must_match_fully(self):
            with self.assertRaises(PatchError):
                apply_patch(self.OLD, [Hunk(2, ("l2", "other"), ())])
            with self.assertRaises(PatchError):
                apply_patch(self.OLD, [Hunk(6, ("l6", "l7"), ())])

        def test_out_of_range(self):
            for h in (Hunk(8, (), ("x",)), Hunk(0, (), ("x",)), Hunk(-3, (), ("x",))):
                with self.assertRaises(PatchError) as cm:
                    apply_patch(self.OLD, [h])
                self.assertIn("hunk 1", str(cm.exception))
            with self.assertRaises(PatchError):
                apply_patch(self.OLD, [Hunk(7, ("l6",), ())])

        def test_overlap_and_order(self):
            with self.assertRaises(PatchError):
                apply_patch(self.OLD, [Hunk(3, ("l3", "l4"), ()), Hunk(4, ("l4",), ())])
            with self.assertRaises(PatchError):
                apply_patch(self.OLD, [Hunk(5, ("l5",), ()), Hunk(2, ("l2",), ())])
            with self.assertRaises(PatchError) as cm:
                apply_patch(self.OLD, [Hunk(4, ("l4",), ()), Hunk(2, (), ("x",))])
            self.assertIn("hunk 2", str(cm.exception))

        def test_shift_search_order(self):
            old = ["a", "x", "b", "x", "c", "x", "d"]
            h = [Hunk(3, ("x",), ("Y",))]
            self.assertEqual(apply_patch(old, [Hunk(2, ("x",), ("Y",))]), ["a", "Y", "b", "x", "c", "x", "d"])
            self.assertEqual(apply_patch(old, h, max_shift=1), ["a", "Y", "b", "x", "c", "x", "d"])
            old2 = ["p", "q", "x", "r", "s", "x", "t"]
            self.assertEqual(apply_patch(old2, [Hunk(4, ("x",), ("Y",))], max_shift=2), ["p", "q", "Y", "r", "s", "x", "t"])
            old3 = ["p", "q", "r", "x", "s", "t", "x"]
            self.assertEqual(apply_patch(old3, [Hunk(5, ("x",), ("Y",))], max_shift=2), ["p", "q", "r", "Y", "s", "t", "x"])

        def test_shift_limits(self):
            old = ["a", "b", "c", "d", "x"]
            with self.assertRaises(PatchError):
                apply_patch(old, [Hunk(1, ("x",), ())], max_shift=3)
            self.assertEqual(apply_patch(old, [Hunk(1, ("x",), ())], max_shift=4), ["a", "b", "c", "d"])
            self.assertEqual(apply_patch(["x", "a"], [Hunk(2, ("x",), ())], max_shift=1), ["a"])
            with self.assertRaises(PatchError):
                apply_patch(["x", "a"], [Hunk(2, ("x",), ())], max_shift=0)

        def test_shift_carries_over_to_later_hunks(self):
            old = ["n", "a", "b", "c", "d"]
            hunks = [Hunk(1, ("a",), ("A",)), Hunk(3, ("c",), ("C",))]
            self.assertEqual(apply_patch(old, hunks, max_shift=1), ["n", "A", "b", "C", "d"])
            with self.assertRaises(PatchError):
                apply_patch(old, hunks, max_shift=0)
            self.assertEqual(apply_patch(old, [Hunk(1, ("a",), ("A",)), Hunk(3, (), ("ins",))], max_shift=1), ["n", "A", "b", "ins", "c", "d"])

        def test_shift_never_goes_before_previous_hunk(self):
            old = ["a", "x", "b", "c"]
            hunks = [Hunk(2, ("x",), ()), Hunk(2, ("x",), ())]
            with self.assertRaises(PatchError):
                apply_patch(old, hunks, max_shift=2)

        def test_shift_stays_inside_old(self):
            old = ["a", "b", "x"]
            with self.assertRaises(PatchError):
                apply_patch(old, [Hunk(5, ("q",), ())], max_shift=5)
            self.assertEqual(apply_patch(old, [Hunk(5, ("x",), ())], max_shift=3), ["a", "b"])


    class Invert(unittest.TestCase):
        def test_simple(self):
            old, new = ["a", "b", "c"], ["a", "x", "y", "c"]
            h = diff(old, new)
            self.assertEqual(invert(h), [Hunk(2, ("x", "y"), ("b",))])
            self.assertEqual(apply_patch(new, invert(h)), old)

        def test_positions_follow_growth(self):
            hunks = [Hunk(1, (), ("n1", "n2", "n3")), Hunk(4, ("d",), ()), Hunk(9, ("e",), ("E", "F"))]
            self.assertEqual(invert(hunks), [Hunk(1, ("n1", "n2", "n3"), ()), Hunk(7, (), ("d",)), Hunk(11, ("E", "F"), ("e",))])
            self.assertEqual(invert([]), [])

        def test_double_inversion_is_not_identity_but_round_trips_text(self):
            old = ["a", "b", "c", "d", "e", "f"]
            new = ["b", "c", "X", "e", "f", "g", "h"]
            self.assertEqual(apply_patch(apply_patch(old, diff(old, new)), invert(diff(old, new))), old)

        def test_random_round_trips(self):
            rng = random.Random(7)
            alphabet = ["a", "b", "c", "", "d"]
            for _ in range(60):
                old = [rng.choice(alphabet) for _ in range(rng.randint(0, 9))]
                new = [rng.choice(alphabet) for _ in range(rng.randint(0, 9))]
                h = diff(old, new)
                self.assertEqual(apply_patch(old, h), new)
                self.assertEqual(apply_patch(new, invert(h)), old)
                self.assertEqual(parse_patch(format_patch(h)), h)
                added, removed = stats(h)
                self.assertEqual(len(old) + added - removed, len(new))


    if __name__ == "__main__":
        unittest.main()
''')

LP = Lib(
    name="linepatch", lang="python", title="the line diff/patch package (`linepatch/`)",
    blurb="The config-sync agent computes and applies small line patches with this package.",
    files={"linepatch/__init__.py": LP_INIT, "linepatch/diff.py": LP_DIFF, "linepatch/stitch.py": LP_STITCH,
           "README.md": LP_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": LP_VISIBLE},
    hidden_tests={"tests/test_full.py": LP_HIDDEN},
    mutate=["linepatch/diff.py", "linepatch/stitch.py"], difficulty=4, tags=["diff", "text"],
    probes=[
        'diff(["a", "b"], ["b", "a"])',
        'diff(["a", "b", "c", "d", "e", "f"], ["a", "B", "c", "d", "f", "g"])',
        'diff(["a", "c"], ["a", "b", "c"])',
        'diff(["a", "a"], ["a"])',
        'format_patch(diff(["a", "b", "c"], ["a", "x", "y", "c"]))',
        'parse_patch("# c\\n\\n@ 1 -1 +1\\n-a\\n+b\\n")',
        'apply_patch(["a", "x", "b", "x"], [Hunk(2, ("x",), ("Y",))], max_shift=1)',
        'apply_patch(["n", "a", "b", "c", "d"], [Hunk(1, ("a",), ("A",)), Hunk(3, ("c",), ("C",))], max_shift=1)',
        'invert([Hunk(1, (), ("n1", "n2", "n3")), Hunk(4, ("d",), ())])',
        'stats(diff(["a", "b", "c"], ["a", "x", "y", "c"]))',
        'lines("a\\r\\nb\\n\\n")',
    ],
    probe_import="from linepatch import *",
)


# ======================================================================================================================
# pagespec: page-selection mini language for the print spooler
# ======================================================================================================================

PS_README = dd(r'''
    # pagespec

    The print spooler lets users choose pages with a small language. One module, `pagespec.py`.

    ## `parse(spec, total) -> list[int]`
    `total` is the number of pages (at least 1, else `ValueError`). `spec` is a list of *items* separated by commas; blank
    items are skipped (so `""` selects nothing, giving `[]`). Items are applied left to right to a result list; spaces
    around and inside items are ignored.

    An item is an optional `!` (remove instead of add), then a selector, with an optional step `/S` (`S` a positive integer) after
    a range-like selector:

    | selector | pages |
    |---|---|
    | `N` | page `N` (no step allowed) |
    | `A-B` | from `A` to `B` inclusive; counting **down** when `A > B` |
    | `A-` | from `A` to the last page |
    | `-B` | from page 1 to `B` |
    | `all` | pages 1 to `total` |
    | `odd` / `even` | the odd / even pages from 1 to `total` |

    An endpoint (`N`, `A`, `B`) is either a positive integer or `~K`, the page that is `K` from the end (`~1` is the last
    page, `~2` the one before it). A step `S` takes every `S`-th page from the first one named: `1-10/3` is `1, 4, 7, 10`,
    `10-1/4` is `10, 6, 2`; the last endpoint is only included when the step reaches it. Steps are allowed after `A-B`, `A-`, `-B`
    and `all`, not after `N`, `odd`, `even`.

    Adding appends the pages in selector order, skipping pages already in the result. Removing deletes the pages from the result
    (pages not in it are ignored) and keeps the order of the rest. Every page mentioned must lie in `1..total`, else `ValueError` (also for
    removals); malformed items (unknown words, empty parts such as `-`, a zero step, `~0`, ...) are a `ValueError` too.

    ## `compress(pages) -> str`
    Writes a list of distinct positive integers as a spec: maximal runs of consecutive ascending pages (`n, n+1, n+2, ...`) with at
    least 3 members become `first-last`, everything else is written one number per item; items joined by `,`. The order of
    `pages` is kept. `[]` gives `""`. `parse(compress(p), N) == p` when all pages are in `1..N`.

    ## `count_sheets(pages, per_sheet=2) -> int`
    Number of sheets needed to print `len(pages)` pages with `per_sheet` pages on a sheet (rounded up); `per_sheet` below 1 is a `ValueError`.
''')

PS_SRC = dd(r'''
    """Page-selection language."""
    import re

    _INT = re.compile(r"[1-9][0-9]*")


    def _endpoint(text, total, item):
        if text.startswith("~"):
            k = text[1:]
            if not _INT.fullmatch(k):
                raise ValueError("bad endpoint in %r" % item)
            page = total - int(k) + 1
        elif _INT.fullmatch(text):
            page = int(text)
        else:
            raise ValueError("bad endpoint in %r" % item)
        if not 1 <= page <= total:
            raise ValueError("page out of range in %r" % item)
        return page


    def _span(lo, hi, step):
        if lo <= hi:
            return list(range(lo, hi + 1, step))
        return list(range(lo, hi - 1, -step))


    def _selector(body, total, item):
        step = 1
        has_step = False
        if "/" in body:
            body, _, s = body.partition("/")
            if not _INT.fullmatch(s):
                raise ValueError("bad step in %r" % item)
            step, has_step = int(s), True
        if body == "all":
            return _span(1, total, step)
        if body in ("odd", "even"):
            if has_step:
                raise ValueError("no step for %r" % item)
            return [p for p in range(1, total + 1) if (p % 2 == 1) == (body == "odd")]
        if body.startswith("-"):
            return _span(1, _endpoint(body[1:], total, item), step)
        if body.endswith("-"):
            return _span(_endpoint(body[:-1], total, item), total, step)
        if "-" in body:
            a, _, b = body.partition("-")
            return _span(_endpoint(a, total, item), _endpoint(b, total, item), step)
        if has_step:
            raise ValueError("no step for a single page: %r" % item)
        return [_endpoint(body, total, item)]


    def parse(spec, total):
        if total < 1:
            raise ValueError("total must be at least 1")
        result = []
        for raw in spec.split(","):
            item = "".join(raw.split())
            if not item:
                continue
            remove = item.startswith("!")
            pages = _selector(item[1:] if remove else item, total, raw.strip())
            if remove:
                result = [p for p in result if p not in pages]
            else:
                for p in pages:
                    if p not in result:
                        result.append(p)
        return result


    def compress(pages):
        out = []
        i = 0
        while i < len(pages):
            j = i
            while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1:
                j += 1
            if j - i >= 2:
                out.append("%d-%d" % (pages[i], pages[j]))
            else:
                out.extend(str(p) for p in pages[i:j + 1])
            i = j + 1
        return ",".join(out)


    def count_sheets(pages, per_sheet=2):
        if per_sheet < 1:
            raise ValueError("per_sheet must be at least 1")
        return -(-len(pages) // per_sheet)
''')

PS_VISIBLE = dd(r'''
    import unittest

    from pagespec import compress, count_sheets, parse


    class BasicTests(unittest.TestCase):
        def test_parse(self):
            self.assertEqual(parse("1-3,5", 10), [1, 2, 3, 5])

        def test_open_range(self):
            self.assertEqual(parse("8-", 10), [8, 9, 10])

        def test_compress(self):
            self.assertEqual(compress([1, 2, 3, 5]), "1-3,5")

        def test_sheets(self):
            self.assertEqual(count_sheets([1, 2, 3]), 2)


    if __name__ == "__main__":
        unittest.main()
''')

PS_HIDDEN = dd(r'''
    import unittest

    from pagespec import compress, count_sheets, parse


    class Selectors(unittest.TestCase):
        def test_single_and_ranges(self):
            self.assertEqual(parse("3", 10), [3])
            self.assertEqual(parse("1", 1), [1])
            self.assertEqual(parse("2-5", 10), [2, 3, 4, 5])
            self.assertEqual(parse("4-4", 10), [4])
            self.assertEqual(parse("1-10", 10), list(range(1, 11)))

        def test_open_ends(self):
            self.assertEqual(parse("8-", 10), [8, 9, 10])
            self.assertEqual(parse("10-", 10), [10])
            self.assertEqual(parse("-3", 10), [1, 2, 3])
            self.assertEqual(parse("-1", 10), [1])
            self.assertEqual(parse("-10", 10), list(range(1, 11)))

        def test_all_odd_even(self):
            self.assertEqual(parse("all", 4), [1, 2, 3, 4])
            self.assertEqual(parse("odd", 6), [1, 3, 5])
            self.assertEqual(parse("even", 6), [2, 4, 6])
            self.assertEqual(parse("odd", 5), [1, 3, 5])
            self.assertEqual(parse("even", 5), [2, 4])
            self.assertEqual(parse("even", 1), [])
            self.assertEqual(parse("odd", 1), [1])

        def test_descending(self):
            self.assertEqual(parse("5-2", 10), [5, 4, 3, 2])
            self.assertEqual(parse("3-1", 3), [3, 2, 1])
            self.assertEqual(parse("2-1", 5), [2, 1])

        def test_from_the_end(self):
            self.assertEqual(parse("~1", 10), [10])
            self.assertEqual(parse("~3", 10), [8])
            self.assertEqual(parse("~10", 10), [1])
            self.assertEqual(parse("~3-~1", 10), [8, 9, 10])
            self.assertEqual(parse("~1-~3", 10), [10, 9, 8])
            self.assertEqual(parse("2-~2", 6), [2, 3, 4, 5])
            self.assertEqual(parse("~2-", 6), [5, 6])
            self.assertEqual(parse("-~2", 6), [1, 2, 3, 4, 5])
            self.assertEqual(parse("~4-5", 6), [3, 4, 5])


    class Steps(unittest.TestCase):
        def test_steps(self):
            self.assertEqual(parse("1-10/3", 10), [1, 4, 7, 10])
            self.assertEqual(parse("1-9/3", 10), [1, 4, 7])
            self.assertEqual(parse("2-10/4", 10), [2, 6, 10])
            self.assertEqual(parse("1-10/1", 10), list(range(1, 11)))
            self.assertEqual(parse("1-3/5", 10), [1])
            self.assertEqual(parse("3-3/2", 10), [3])

        def test_descending_steps(self):
            self.assertEqual(parse("10-1/4", 10), [10, 6, 2])
            self.assertEqual(parse("10-1/3", 10), [10, 7, 4, 1])
            self.assertEqual(parse("5-1/2", 10), [5, 3, 1])

        def test_steps_on_open_and_all(self):
            self.assertEqual(parse("3-/2", 10), [3, 5, 7, 9])
            self.assertEqual(parse("-7/3", 10), [1, 4, 7])
            self.assertEqual(parse("all/3", 10), [1, 4, 7, 10])
            self.assertEqual(parse("~9-~1/4", 10), [2, 6, 10])

        def test_bad_steps(self):
            for bad in ("1-5/0", "1-5/", "1-5/x", "1-5/-1", "3/2", "odd/2", "even/2", "1-5/2/3", "all/0", "1-5/01"):
                with self.assertRaises(ValueError, msg=bad):
                    parse(bad, 10)


    class Combining(unittest.TestCase):
        def test_order_is_given_order_without_duplicates(self):
            self.assertEqual(parse("5,1-3", 10), [5, 1, 2, 3])
            self.assertEqual(parse("1-3,2-5", 10), [1, 2, 3, 4, 5])
            self.assertEqual(parse("3,3,3", 10), [3])
            self.assertEqual(parse("5-3,4-6", 10), [5, 4, 3, 6])
            self.assertEqual(parse("odd,even", 4), [1, 3, 2, 4])

        def test_blank_items_and_spaces(self):
            self.assertEqual(parse("", 10), [])
            self.assertEqual(parse("  ", 10), [])
            self.assertEqual(parse(",,", 10), [])
            self.assertEqual(parse(" 1 - 3 , , 5 ", 10), [1, 2, 3, 5])
            self.assertEqual(parse("1 -\t3", 10), [1, 2, 3])
            self.assertEqual(parse("1-10 / 3", 10), [1, 4, 7, 10])
            self.assertEqual(parse(" ! 2 ", 3) , [])

        def test_removal(self):
            self.assertEqual(parse("1-6,!3", 10), [1, 2, 4, 5, 6])
            self.assertEqual(parse("all,!2-4", 6), [1, 5, 6])
            self.assertEqual(parse("all,!odd", 6), [2, 4, 6])
            self.assertEqual(parse("1-10,!even,!~1", 10), [1, 3, 5, 7, 9])
            self.assertEqual(parse("5-1,!3", 5), [5, 4, 2, 1])
            self.assertEqual(parse("1-10,!1-10/2", 10), [2, 4, 6, 8, 10])

        def test_removal_is_ordered(self):
            self.assertEqual(parse("!3,1-5", 10), [1, 2, 3, 4, 5])
            self.assertEqual(parse("1-5,!3,3", 10), [1, 2, 4, 5, 3])
            self.assertEqual(parse("1-3,!1-3,2", 10), [2])

        def test_removal_of_absent_pages_is_fine(self):
            self.assertEqual(parse("1-3,!7", 10), [1, 2, 3])
            self.assertEqual(parse("!1", 10), [])


    class Errors(unittest.TestCase):
        def test_out_of_range(self):
            for bad in ("0", "11", "1-11", "0-3", "11-", "-11", "~11", "~0", "!11", "!0", "all,!99", "5-0", "-0"):
                with self.assertRaises(ValueError, msg=bad):
                    parse(bad, 10)

        def test_boundaries_are_valid(self):
            self.assertEqual(parse("10", 10), [10])
            self.assertEqual(parse("1", 10), [1])
            self.assertEqual(parse("~10", 10), [1])

        def test_malformed(self):
            for bad in ("-", "--3", "1--3", "1-2-3", "a", "1,a", "x-3", "1-y", "all-3", "odd-", "3.5", "1;2", "~", "~x", "~-3", "!", "!!1", "~~1",
                        "-/2", "1-/", "even-4", "007", "+3", "1-+3"):
                with self.assertRaises(ValueError, msg=bad):
                    parse(bad, 10)

        def test_bad_total(self):
            for total in (0, -1):
                with self.assertRaises(ValueError):
                    parse("1", total)
            self.assertEqual(parse("", 1), [])

        def test_case_sensitive_words(self):
            for bad in ("ALL", "Odd", "EVEN"):
                with self.assertRaises(ValueError, msg=bad):
                    parse(bad, 10)


    class Compress(unittest.TestCase):
        def test_runs(self):
            self.assertEqual(compress([1, 2, 3, 5]), "1-3,5")
            self.assertEqual(compress([1, 2]), "1,2")
            self.assertEqual(compress([1, 2, 3]), "1-3")
            self.assertEqual(compress([4, 5, 6, 7, 9, 10, 12, 13, 14]), "4-7,9,10,12-14")
            self.assertEqual(compress([7]), "7")
            self.assertEqual(compress([]), "")

        def test_order_is_kept(self):
            self.assertEqual(compress([5, 1, 2, 3]), "5,1-3")
            self.assertEqual(compress([3, 2, 1]), "3,2,1")
            self.assertEqual(compress([1, 2, 3, 1 + 9, 11, 12, 13, 14]), "1-3,10-14")
            self.assertEqual(compress([2, 3, 1, 2]), "2,3,1,2")

        def test_runs_split_by_order(self):
            self.assertEqual(compress([1, 2, 3, 4, 7, 8, 9]), "1-4,7-9")
            self.assertEqual(compress([9, 10, 11, 5, 6]), "9-11,5,6")

        def test_round_trip(self):
            for pages in ([1, 2, 3, 5, 7, 8, 9, 10], [5, 1, 2, 3], [10, 9, 8], [1], [], [2, 4, 6]):
                self.assertEqual(parse(compress(pages), 10), pages)
            self.assertEqual(compress(parse("all,!odd", 10)), "2,4,6,8,10")
            self.assertEqual(compress(parse("3-9,!5", 10)), "3,4,6-9")


    class Sheets(unittest.TestCase):
        def test_values(self):
            self.assertEqual(count_sheets([]), 0)
            self.assertEqual(count_sheets([1]), 1)
            self.assertEqual(count_sheets([1, 2]), 1)
            self.assertEqual(count_sheets([1, 2, 3]), 2)
            self.assertEqual(count_sheets(list(range(10)), 4), 3)
            self.assertEqual(count_sheets(list(range(8)), 4), 2)
            self.assertEqual(count_sheets(list(range(5)), 1), 5)

        def test_bad_per_sheet(self):
            for n in (0, -2):
                with self.assertRaises(ValueError):
                    count_sheets([1], n)


    if __name__ == "__main__":
        unittest.main()
''')

PS = Lib(
    name="pagespec", lang="python", title="the page-selection language (`pagespec.py`)",
    blurb="The print spooler turns a user's page selection like `1-3,!2,~1` into page lists with this module.",
    files={"pagespec.py": PS_SRC, "README.md": PS_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": PS_VISIBLE},
    hidden_tests={"tests/test_full.py": PS_HIDDEN},
    mutate=["pagespec.py"], difficulty=3, tags=["parsing", "printing"],
    probes=[
        'parse("1-10/3", 10)',
        'parse("10-1/4", 10)',
        'parse("~3-~1,!9", 10)',
        'parse("5-3,4-6", 10)',
        'parse("all,!odd", 7)',
        'parse("1-5,!3,3", 10)',
        'parse("-~2", 6)',
        'compress([4, 5, 6, 7, 9, 10, 12, 13, 14])',
        'compress([5, 1, 2, 3])',
        'count_sheets(list(range(10)), 4)',
    ],
    probe_import="from pagespec import *",
)


# ======================================================================================================================
# relnotes: release-log parser and version-bump suggestions
# ======================================================================================================================

RN_README = dd(r'''
    # relnotes

    Tools for the `RELEASES` file of our projects, a hand-edited log with this format:

        == Unreleased ==
        + export to CSV (#41)
        == 2.1.0 (2024-03-05) ==
        ~ BREAKING: config files must be UTF-8 (#38, #39)
        ! crash on empty input
          that happened with piped data (#37)
        == 2.0.0 (2024-01-10) ==
        - dropped the legacy API

    ## Types
    `Entry` is a `namedtuple` `(kind, text, refs, breaking)`; `Release` is `(version, date, entries)` where `version` is a
    `str` or `None` (the *Unreleased* section), `date` a `"YYYY-MM-DD"` string or `None`, `entries` a list of `Entry`.
    `KINDS` maps the markers `+ ~ ! - ^` to `added changed fixed removed security`; `ORDER` is that list of kinds in this order.

    ## `parse_log(text) -> list[Release]`
    Lines are read in order; `\r\n` is accepted. Blank lines (only whitespace) are ignored.
    * A heading is `==`, optional blanks, the title, optional blanks and a final `==`. The title is either `Unreleased` (any capitalisation;
      no date allowed) or a version `N.N.N` (digits) optionally followed by `-` and a pre-release of `[0-9A-Za-z.]`; after the
      version there may be blanks and a date `(YYYY-MM-DD)`, which must be a real calendar date. Anything else that
      starts with `==` is a `ValueError`.
    * An entry is a line that starts with a marker, one space and the text; it belongs to the latest heading (an
      entry before any heading is a `ValueError`). A line that starts with two or more spaces and has text continues the previous
      entry: its stripped text is appended after one space (a continuation without a previous entry is a `ValueError`).
      An entry with no text is a `ValueError` (also when nothing is left of the text after the references and the `BREAKING:` prefix are taken
      off; that error names the release instead of a line).
    * After the lines of an entry have been joined: if the text ends with a reference group such as `(#12)` or `(#12, #15)` (blanks
      around the commas allowed), the numbers go to `refs` as a tuple of `int` in written order and the group (with the blanks before
      it) is removed. Then, if the text starts with `BREAKING:`, `breaking` is true and the prefix and the blanks after it are
      removed. Text is stripped.
    * Any other line is a `ValueError`. Every `ValueError` message from reading a line begins with `line N:` (N from 1).
    * Order: `Unreleased` may only be the first release; versions must strictly decrease (compare the numbers; at equal numbers
      a version without pre-release is greater than one with, and pre-releases compare as plain strings). A violation (or a duplicate) is
      a `ValueError` naming the version.

    ## `render(releases) -> str`
    Writes releases back: `== VERSION (DATE) ==` (or `== VERSION ==`, `== Unreleased ==`), then one line per entry: marker, space,
    `BREAKING: ` if breaking, the text, and ` (#a, #b)` if there are refs. Releases are separated by one empty line; the result ends
    with a newline; no releases give `""`. For single-line entry texts `parse_log(render(r)) == r`.

    ## `summary(release) -> dict`
    Entry counts per kind, only kinds that occur, in `ORDER` order.

    ## `refs_index(releases) -> dict`
    Maps each referenced issue number to the list of release labels (the version string, `"Unreleased"` for `None`) that mention it,
    in log order without repeats; keys are in ascending order.

    ## `suggest_bump(entries, version=None) -> str or None`
    * `"major"` if some entry is breaking or of kind `removed`;
    * else `"minor"` if some entry is `added` or `changed`;
    * else `"patch"` if some entry is `fixed` or `security`;
    * else `None` (no entries).
    When `version` (a string whose major number is read) has major `0`, `"major"` becomes `"minor"` and `"minor"` becomes `"patch"`
    (`"patch"` stays).

    ## `bump(version, level) -> str`
    `version` must be plain `N.N.N` (`ValueError` otherwise). `"major"` gives `M+1.0.0`, `"minor"` `M.m+1.0`, `"patch"` `M.m.p+1`,
    `None` the version unchanged; any other level is a `ValueError`.

    ## `next_version(current, entries) -> str`
    `bump(current, suggest_bump(entries, current))`.
''')

RN_SRC = dd(r'''
    """Release-log tools."""
    import re
    from collections import namedtuple
    from datetime import date

    Entry = namedtuple("Entry", "kind text refs breaking")
    Release = namedtuple("Release", "version date entries")

    KINDS = {"+": "added", "~": "changed", "!": "fixed", "-": "removed", "^": "security"}
    ORDER = ["added", "changed", "fixed", "removed", "security"]
    _MARKER = {v: k for k, v in KINDS.items()}

    _HEAD = re.compile(r"==\s*(\S+?)(?:\s+\(([^)]*)\))?\s*==")
    _VER = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.]+))?")
    _PLAIN = re.compile(r"(\d+)\.(\d+)\.(\d+)")
    _REFS = re.compile(r"\s*\((#\d+(?:\s*,\s*#\d+)*)\)$")


    def _vkey(version):
        m = _VER.fullmatch(version)
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), 0 if m.group(4) else 1, m.group(4) or "")


    def _heading(line):
        m = _HEAD.fullmatch(line)
        if not m:
            raise ValueError("bad heading %r" % line)
        title, when = m.group(1), m.group(2)
        if title.lower() == "unreleased":
            if when is not None:
                raise ValueError("Unreleased takes no date")
            return None, None
        if not _VER.fullmatch(title):
            raise ValueError("bad version %r" % title)
        if when is not None:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", when):
                raise ValueError("bad date %r" % when)
            try:
                date(int(when[:4]), int(when[5:7]), int(when[8:]))
            except ValueError:
                raise ValueError("bad date %r" % when) from None
        return title, when


    def _entry(kind, text):
        refs = ()
        m = _REFS.search(text)
        if m:
            refs = tuple(int(n) for n in re.findall(r"#(\d+)", m.group(1)))
            text = text[:m.start()]
        breaking = False
        if text.startswith("BREAKING:"):
            breaking = True
            text = text[len("BREAKING:"):]
        return Entry(kind, text.strip(), refs, breaking)


    def parse_log(text):
        releases = []   # [version, date, [pending entries as [kind, text]]]
        for no, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                if line.startswith("=="):
                    version, when = _heading(line.strip())
                    releases.append([version, when, []])
                elif line[0] in KINDS and line[1:2] == " ":
                    if not releases:
                        raise ValueError("entry outside a release")
                    if not line[2:].strip():
                        raise ValueError("empty entry")
                    releases[-1][2].append([KINDS[line[0]], line[2:].strip()])
                elif line.startswith("  "):
                    if not releases or not releases[-1][2]:
                        raise ValueError("continuation without an entry")
                    releases[-1][2][-1][1] += " " + line.strip()
                else:
                    raise ValueError("cannot parse %r" % line)
            except ValueError as exc:
                raise ValueError("line %d: %s" % (no, exc)) from None
        out = []
        for version, when, pending in releases:
            entries = [_entry(k, t) for k, t in pending]
            if any(not e.text for e in entries):
                raise ValueError("empty entry in release %s" % (version or "Unreleased"))
            out.append(Release(version, when, entries))
        for i, r in enumerate(out):
            if r.version is None:
                if i != 0:
                    raise ValueError("Unreleased must come first")
            elif i > 0 and out[i - 1].version is not None and _vkey(out[i - 1].version) <= _vkey(r.version):
                raise ValueError("release %s is out of order" % r.version)
        return out


    def render(releases):
        blocks = []
        for r in releases:
            if r.version is None:
                head = "== Unreleased =="
            elif r.date:
                head = "== %s (%s) ==" % (r.version, r.date)
            else:
                head = "== %s ==" % r.version
            lines = [head]
            for e in r.entries:
                line = "%s %s%s" % (_MARKER[e.kind], "BREAKING: " if e.breaking else "", e.text)
                if e.refs:
                    line += " (%s)" % ", ".join("#%d" % n for n in e.refs)
                lines.append(line)
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks) + "\n" if blocks else ""


    def summary(release):
        counts = {}
        for e in release.entries:
            counts[e.kind] = counts.get(e.kind, 0) + 1
        return {k: counts[k] for k in ORDER if k in counts}


    def refs_index(releases):
        index = {}
        for r in releases:
            label = r.version if r.version is not None else "Unreleased"
            for e in r.entries:
                for n in e.refs:
                    labels = index.setdefault(n, [])
                    if label not in labels:
                        labels.append(label)
        return {n: index[n] for n in sorted(index)}


    def suggest_bump(entries, version=None):
        kinds = {e.kind for e in entries}
        if any(e.breaking for e in entries) or "removed" in kinds:
            level = "major"
        elif kinds & {"added", "changed"}:
            level = "minor"
        elif kinds & {"fixed", "security"}:
            level = "patch"
        else:
            return None
        if version is not None and int(version.split(".")[0]) == 0:
            level = {"major": "minor", "minor": "patch", "patch": "patch"}[level]
        return level


    def bump(version, level):
        m = _PLAIN.fullmatch(version)
        if not m:
            raise ValueError("not a plain version: %r" % version)
        major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if level is None:
            return version
        if level == "major":
            return "%d.0.0" % (major + 1)
        if level == "minor":
            return "%d.%d.0" % (major, minor + 1)
        if level == "patch":
            return "%d.%d.%d" % (major, minor, patch + 1)
        raise ValueError("unknown level: %r" % (level,))


    def next_version(current, entries):
        return bump(current, suggest_bump(entries, current))
''')

RN_VISIBLE = dd(r'''
    import unittest

    from relnotes import Entry, Release, bump, parse_log, suggest_bump


    class BasicTests(unittest.TestCase):
        def test_parse(self):
            rs = parse_log("== 1.0.0 (2024-01-02) ==\n+ first release (#1)\n")
            self.assertEqual(rs, [Release("1.0.0", "2024-01-02", [Entry("added", "first release", (1,), False)])])

        def test_bump(self):
            self.assertEqual(bump("1.2.3", "minor"), "1.3.0")

        def test_suggest(self):
            self.assertEqual(suggest_bump([Entry("fixed", "x", (), False)]), "patch")


    if __name__ == "__main__":
        unittest.main()
''')

RN_HIDDEN = dd(r'''
    import unittest

    from relnotes import (KINDS, ORDER, Entry, Release, bump, next_version, parse_log, refs_index, render, suggest_bump,
                          summary)


    def E(kind, text, refs=(), breaking=False):
        return Entry(kind, text, tuple(refs), breaking)


    class Headings(unittest.TestCase):
        def test_versions_and_dates(self):
            text = "== 2.0.0 (2024-02-29) ==\n== 1.9.0 ==\n== 1.0.0-rc.1 (2020-01-01) ==\n"
            self.assertEqual(parse_log(text), [Release("2.0.0", "2024-02-29", []), Release("1.9.0", None, []), Release("1.0.0-rc.1", "2020-01-01", [])])

        def test_unreleased(self):
            for title in ("Unreleased", "unreleased", "UNRELEASED"):
                self.assertEqual(parse_log("== %s ==\n+ x\n" % title), [Release(None, None, [E("added", "x")])])

        def test_spacing_variants(self):
            for line in ("==1.0.0==", "==  1.0.0  ==", "== 1.0.0 (2024-01-02)==", "==1.0.0   (2024-01-02)  =="):
                got = parse_log(line + "\n")
                self.assertEqual(got[0].version, "1.0.0", line)

        def test_bad_headings(self):
            for line in ("== ==", "== 1.0 ==", "== v1.0.0 ==", "== 1.0.0 (2024-13-01) ==", "== 1.0.0 (2023-02-29) ==", "== 1.0.0 (24-01-01) ==",
                         "== 1.0.0 (2024-1-1) ==", "== Unreleased (2024-01-01) ==", "== 1.0.0", "== 1.0.0 ( ) ==", "=== 1.0.0 ===",
                         "== 1.0.0 (2024-01-01) (x) ==", "== 1.0.0 extra ==", "==", "== 1.0.0 (2024-00-10) =="):
                with self.assertRaises(ValueError, msg=line) as cm:
                    parse_log(line + "\n")
                self.assertTrue(str(cm.exception).startswith("line 1:"), line)

        def test_error_line_numbers(self):
            with self.assertRaises(ValueError) as cm:
                parse_log("== 1.0.0 ==\n\n+ ok\n\nnonsense\n")
            self.assertTrue(str(cm.exception).startswith("line 5:"))
            with self.assertRaises(ValueError) as cm:
                parse_log("\n\n+ orphan\n")
            self.assertTrue(str(cm.exception).startswith("line 3:"))

        def test_empty_and_blank(self):
            self.assertEqual(parse_log(""), [])
            self.assertEqual(parse_log("\n  \n\t\n"), [])
            self.assertEqual(parse_log("== 1.0.0 ==\r\n+ a\r\n"), [Release("1.0.0", None, [E("added", "a")])])


    class Entries(unittest.TestCase):
        def test_markers(self):
            text = "== 1.0.0 ==\n+ a\n~ b\n! c\n- d\n^ e\n"
            kinds = [e.kind for e in parse_log(text)[0].entries]
            self.assertEqual(kinds, ["added", "changed", "fixed", "removed", "security"])
            self.assertEqual(KINDS, {"+": "added", "~": "changed", "!": "fixed", "-": "removed", "^": "security"})
            self.assertEqual(ORDER, ["added", "changed", "fixed", "removed", "security"])

        def test_text_is_stripped(self):
            self.assertEqual(parse_log("== 1.0.0 ==\n+   spaced out   \n")[0].entries, [E("added", "spaced out")])

        def test_entry_outside_release(self):
            with self.assertRaises(ValueError):
                parse_log("+ a\n== 1.0.0 ==\n")
            with self.assertRaises(ValueError):
                parse_log("  continued\n== 1.0.0 ==\n")

        def test_bad_lines(self):
            for line in ("+no space", "x text", "* text", "text", "+", "+ ", "-  ", "\ttab", "#comment"):
                with self.assertRaises(ValueError, msg=repr(line)):
                    parse_log("== 1.0.0 ==\n" + line + "\n")

        def test_continuations(self):
            text = "== 1.0.0 ==\n! first\n  second\n      third  \n+ next\n  more\n"
            self.assertEqual(parse_log(text)[0].entries, [E("fixed", "first second third"), E("added", "next more")])

        def test_continuation_needs_an_entry_in_this_release(self):
            with self.assertRaises(ValueError):
                parse_log("== 2.0.0 ==\n+ a\n== 1.0.0 ==\n  stray\n")

        def test_blank_line_does_not_end_entry(self):
            self.assertEqual(parse_log("== 1.0.0 ==\n+ a\n\n  b\n")[0].entries, [E("added", "a b")])

        def test_refs(self):
            text = "== 1.0.0 ==\n+ one (#12)\n+ two (#12, #15)\n+ three ( #1 )\n+ four (#3 ,#4,  #5)\n+ five (#2)(#3)\n"
            es = parse_log(text)[0].entries
            self.assertEqual(es[0], E("added", "one", (12,)))
            self.assertEqual(es[1], E("added", "two", (12, 15)))
            self.assertEqual(es[2].refs, ())
            self.assertEqual(es[2].text, "three ( #1 )")
            self.assertEqual(es[3], E("added", "four", (3, 4, 5)))
            self.assertEqual(es[4], E("added", "five (#2)", (3,)))

        def test_refs_only_at_the_end(self):
            es = parse_log("== 1.0.0 ==\n+ see (#12) for details\n+ bug #9 fixed\n")[0].entries
            self.assertEqual(es[0], E("added", "see (#12) for details"))
            self.assertEqual(es[1], E("added", "bug #9 fixed"))

        def test_refs_after_continuation(self):
            es = parse_log("== 1.0.0 ==\n! crash\n  on empty input (#37, #40)\n")[0].entries
            self.assertEqual(es, [E("fixed", "crash on empty input", (37, 40))])

        def test_ref_numbers_are_ints_in_written_order(self):
            es = parse_log("== 1.0.0 ==\n+ x (#10, #2, #007)\n")[0].entries
            self.assertEqual(es[0].refs, (10, 2, 7))

        def test_breaking(self):
            es = parse_log("== 1.0.0 ==\n~ BREAKING: config must be UTF-8 (#38)\n~ BREAKING:tight\n~ not BREAKING: here\n~ breaking: lower\n")[0].entries
            self.assertEqual(es[0], E("changed", "config must be UTF-8", (38,), True))
            self.assertEqual(es[1], E("changed", "tight", (), True))
            self.assertEqual(es[2], E("changed", "not BREAKING: here"))
            self.assertEqual(es[3], E("changed", "breaking: lower"))

        def test_breaking_after_refs_stripped(self):
            es = parse_log("== 1.0.0 ==\n~ BREAKING: x\n  y (#1)\n")[0].entries
            self.assertEqual(es, [E("changed", "x y", (1,), True)])

        def test_breaking_without_text_is_an_error(self):
            with self.assertRaises(ValueError):
                parse_log("== 1.0.0 ==\n~ BREAKING:\n")
            with self.assertRaises(ValueError):
                parse_log("== 1.0.0 ==\n~ (#4)\n")


    class Ordering(unittest.TestCase):
        def test_valid_orders(self):
            parse_log("== Unreleased ==\n== 1.10.0 ==\n== 1.9.9 ==\n== 1.9.9-rc.2 ==\n== 1.9.9-rc.1 ==\n== 0.1.0 ==\n")
            parse_log("== 2.0.0 ==\n== 1.99.99 ==\n")
            parse_log("== 1.0.10 ==\n== 1.0.9 ==\n")

        def test_invalid_orders(self):
            for text in ("== 1.0.0 ==\n== 2.0.0 ==\n", "== 1.0.0 ==\n== 1.0.0 ==\n", "== 1.0.0 ==\n== Unreleased ==\n", "== 1.9.0 ==\n== 1.10.0 ==\n",
                         "== 1.0.0-rc.1 ==\n== 1.0.0 ==\n", "== 1.0.0-rc.1 ==\n== 1.0.0-rc.2 ==\n", "== Unreleased ==\n== Unreleased ==\n",
                         "== 2.0.0 ==\n== 1.0.0 ==\n== 1.0.1 ==\n", "== 1.0.1 ==\n== 1.0.2 ==\n"):
                with self.assertRaises(ValueError, msg=text):
                    parse_log(text)

        def test_error_names_the_version(self):
            with self.assertRaises(ValueError) as cm:
                parse_log("== 1.0.0 ==\n== 2.5.0 ==\n")
            self.assertIn("2.5.0", str(cm.exception))


    class Render(unittest.TestCase):
        def test_exact_text(self):
            rs = [Release(None, None, [E("added", "export", (41,))]),
                  Release("2.1.0", "2024-03-05", [E("changed", "config is UTF-8", (38, 39), True), E("fixed", "crash")]),
                  Release("2.0.0", None, [E("removed", "legacy API"), E("security", "escape names")]),
                  Release("1.0.0", "2023-01-01", [])]
            text = ("== Unreleased ==\n+ export (#41)\n\n== 2.1.0 (2024-03-05) ==\n~ BREAKING: config is UTF-8 (#38, #39)\n! crash\n\n"
                    "== 2.0.0 ==\n- legacy API\n^ escape names\n\n== 1.0.0 (2023-01-01) ==\n")
            self.assertEqual(render(rs), text)
            self.assertEqual(parse_log(text), rs)

        def test_empty(self):
            self.assertEqual(render([]), "")

        def test_round_trip_from_source(self):
            src = "== 3.0.0 (2024-05-05) ==\n~ BREAKING: a (#1)\n+ b\n\n== 2.0.0 ==\n! c (#2, #3)\n"
            self.assertEqual(render(parse_log(src)), src)


    class Summary(unittest.TestCase):
        def test_counts_in_order(self):
            r = Release("1.0.0", None, [E("fixed", "a"), E("added", "b"), E("fixed", "c"), E("security", "d"), E("added", "e"), E("added", "f")])
            self.assertEqual(summary(r), {"added": 3, "fixed": 2, "security": 1})
            self.assertEqual(list(summary(r)), ["added", "fixed", "security"])
            self.assertEqual(summary(Release("1.0.0", None, [])), {})

        def test_refs_index(self):
            rs = parse_log("== Unreleased ==\n+ a (#5)\n+ b (#2, #5)\n== 1.1.0 ==\n! c (#5, #9)\n! d (#9)\n== 1.0.0 ==\n+ e (#2)\n+ f\n")
            idx = refs_index(rs)
            self.assertEqual(idx, {2: ["Unreleased", "1.0.0"], 5: ["Unreleased", "1.1.0"], 9: ["1.1.0"]})
            self.assertEqual(list(idx), [2, 5, 9])
            self.assertEqual(refs_index([]), {})
            self.assertEqual(refs_index(parse_log("== 1.0.0 ==\n+ x\n")), {})


    class Bumps(unittest.TestCase):
        def test_levels(self):
            self.assertEqual(suggest_bump([E("fixed", "a")]), "patch")
            self.assertEqual(suggest_bump([E("security", "a")]), "patch")
            self.assertEqual(suggest_bump([E("added", "a")]), "minor")
            self.assertEqual(suggest_bump([E("changed", "a")]), "minor")
            self.assertEqual(suggest_bump([E("removed", "a")]), "major")
            self.assertEqual(suggest_bump([E("changed", "a", (), True)]), "major")
            self.assertEqual(suggest_bump([E("fixed", "a", (), True)]), "major")
            self.assertEqual(suggest_bump([]), None)

        def test_highest_wins(self):
            self.assertEqual(suggest_bump([E("fixed", "a"), E("added", "b")]), "minor")
            self.assertEqual(suggest_bump([E("added", "a"), E("fixed", "b"), E("removed", "c")]), "major")
            self.assertEqual(suggest_bump([E("fixed", "a"), E("security", "b")]), "patch")

        def test_zero_major_downgrades(self):
            self.assertEqual(suggest_bump([E("removed", "a")], "0.4.1"), "minor")
            self.assertEqual(suggest_bump([E("added", "a")], "0.4.1"), "patch")
            self.assertEqual(suggest_bump([E("fixed", "a")], "0.4.1"), "patch")
            self.assertEqual(suggest_bump([], "0.4.1"), None)
            self.assertEqual(suggest_bump([E("removed", "a")], "1.0.0"), "major")
            self.assertEqual(suggest_bump([E("added", "a")], "10.0.0"), "minor")
            self.assertEqual(suggest_bump([E("added", "a")], "0.0.0"), "patch")

        def test_bump(self):
            self.assertEqual(bump("1.2.3", "major"), "2.0.0")
            self.assertEqual(bump("1.2.3", "minor"), "1.3.0")
            self.assertEqual(bump("1.2.3", "patch"), "1.2.4")
            self.assertEqual(bump("1.2.3", None), "1.2.3")
            self.assertEqual(bump("9.9.9", "major"), "10.0.0")
            self.assertEqual(bump("0.9.9", "minor"), "0.10.0")
            self.assertEqual(bump("0.0.9", "patch"), "0.0.10")

        def test_bump_errors(self):
            for v in ("1.2", "1.2.3-rc.1", "v1.2.3", "", "1.2.3.4", "a.b.c"):
                with self.assertRaises(ValueError, msg=v):
                    bump(v, "patch")
            with self.assertRaises(ValueError):
                bump("1.2.3", "huge")
            with self.assertRaises(ValueError):
                bump("1.2", None)

        def test_next_version(self):
            self.assertEqual(next_version("1.2.3", [E("fixed", "a")]), "1.2.4")
            self.assertEqual(next_version("1.2.3", [E("added", "a")]), "1.3.0")
            self.assertEqual(next_version("1.2.3", [E("removed", "a")]), "2.0.0")
            self.assertEqual(next_version("0.2.3", [E("removed", "a")]), "0.3.0")
            self.assertEqual(next_version("0.2.3", [E("added", "a")]), "0.2.4")
            self.assertEqual(next_version("1.2.3", []), "1.2.3")


    if __name__ == "__main__":
        unittest.main()
''')

RN = Lib(
    name="relnotes", lang="python", title="the release-log tools (`relnotes.py`)",
    blurb="The release tooling reads each project's hand-edited `RELEASES` log with this module and suggests the next version.",
    files={"relnotes.py": RN_SRC, "README.md": RN_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": RN_VISIBLE},
    hidden_tests={"tests/test_full.py": RN_HIDDEN},
    mutate=["relnotes.py"], difficulty=3, tags=["changelog", "parsing"],
    probes=[
        'parse_log("== 1.0.0 (2024-02-29) ==\\n+ a (#1, #2)\\n! b\\n  c (#9)\\n")',
        'parse_log("== 1.0.0 ==\\n~ BREAKING: x\\n  y (#1)\\n")',
        'parse_log("== 1.0.0 ==\\n+ see (#12) here\\n")[0].entries[0].refs',
        'render(parse_log("== Unreleased ==\\n+ a (#4)\\n\\n== 1.0.0 (2024-01-01) ==\\n- b\\n"))',
        'refs_index(parse_log("== 1.1.0 ==\\n+ a (#5, #2)\\n== 1.0.0 ==\\n+ b (#2)\\n"))',
        'summary(parse_log("== 1.0.0 ==\\n! a\\n+ b\\n! c\\n")[0])',
        'suggest_bump(parse_log("== 1.0.0 ==\\n+ a\\n- b\\n")[0].entries, "0.3.1")',
        'bump("0.9.9", "minor")',
        'next_version("1.2.3", parse_log("== 1.3.0 ==\\n~ BREAKING: a\\n")[0].entries)',
    ],
    probe_import="from relnotes import *",
)


LIBS = [LP, PS, RN]
register_libs(LIBS, n=10)
