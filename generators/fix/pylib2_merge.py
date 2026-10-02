"""Text-format libraries (python), batch: three-way merge."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# threeway: three-way merge of line lists with house conflict markers
# ======================================================================================================================

TW_README = dd(r'''
    # threeway

    Three-way merging of text files for the wiki's offline editor. Package `threeway` with `threeway.lcs` (diff) and `threeway.merge`.
    Texts are lists of lines (strings without line breaks).

    ## `threeway.lcs`
    `Hunk` is a `namedtuple` `(start, removed, added)`: `start` is the **0-based** index in the old list where the hunk begins, `removed` and `added`
    are tuples of lines; the hunk replaces `old[start:start+len(removed)]` by `added`.

    ### `diff(old, new) -> list[Hunk]`
    Let `L[i][j]` be the length of a longest common subsequence of `old[i:]` and `new[j:]`. Walk from `i = j = 0`: if `old[i] == new[j]` both advance; otherwise,
    if `j` is past the end, or `i` is not and `L[i+1][j] >= L[i][j+1]`, `old[i]` is removed (`i` advances), else `new[j]` is added (`j` advances). A maximal run of
    non-matching steps is one hunk (all its removed lines and all its added lines, in order) whose `start` is the value of `i` when the run began. Equal lists
    give `[]`.

    ## `threeway.merge`
    ### `merge3(base, ours, theirs, prefer=None) -> MergeResult`
    `MergeResult` is a `namedtuple` `(lines, conflicts)`. `prefer` is `None`, `"ours"` or `"theirs"` (anything else is a `ValueError`).
    1. `diff(base, ours)` and `diff(base, theirs)` give the hunks of both sides. Each hunk covers the half-open base range `[start, start + len(removed))` (an
       insertion covers the empty range at its start).
    2. An *ours* hunk and a *theirs* hunk **interact** when their ranges overlap (`a1 < b2 and a2 < b1`), or when both are insertions at the same point
       (`a1 == b1 == a2 == b2`). Insertions that merely touch the edge of the other hunk's range do not interact. Hunks of the same side never interact
       directly.
    3. The connected groups of interacting hunks (a hunk that interacts with nobody is a group of its own) are the *units*. A unit's range runs from the smallest
       start to the largest end of its hunks.
    4. The result is built from left to right: base lines between units are copied; units are ordered by `(range start, range end)`. For each unit the text of its range
       is computed once from the base with only the *ours* hunks of the unit applied, and once with only the *theirs* hunks:
       * a unit with hunks from one side only, or whose two texts are equal (both sides made the same change), contributes that text;
       * otherwise it is a conflict: with `prefer` set, the text of the preferred side; without it, the lines `<<ours`, the *ours* text, `==`, the *theirs*
         text and `theirs>>`, and `conflicts` is increased by one.

    ### `parse_conflicts(lines) -> list`
    Splits a merged list of lines into segments: `("text", [lines])` for plain runs and `("conflict", [ours lines], [theirs lines])` for a block; consecutive plain
    lines form one segment and empty segments are not produced. A line that is exactly `<<ours` opens a block, `==` switches to the theirs part, `theirs>>` closes it.
    Markers anywhere else (a `==` or `theirs>>` outside a block, a `<<ours` inside one, a second `==` in a block) or a block that is not closed are a `ValueError`.
''')

TW_LCS = dd(r'''
    """Line diff."""
    from collections import namedtuple

    Hunk = namedtuple("Hunk", "start removed added")


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
                cur = [i, [], []]
            if j >= m or (i < n and lcs[i + 1][j] >= lcs[i][j + 1]):
                cur[1].append(old[i])
                i += 1
            else:
                cur[2].append(new[j])
                j += 1
        if cur is not None:
            hunks.append(Hunk(cur[0], tuple(cur[1]), tuple(cur[2])))
        return hunks
''')

TW_MERGE = dd(r'''
    """Three-way merge."""
    from collections import namedtuple

    from .lcs import diff

    MergeResult = namedtuple("MergeResult", "lines conflicts")


    def _span(h):
        return (h.start, h.start + len(h.removed))


    def _interact(x, y):
        (a1, b1), (a2, b2) = x, y
        return (a1 < b2 and a2 < b1) or (a1 == b1 == a2 == b2)


    def _apply(base, lo, hi, hunks):
        out = []
        pos = lo
        for h in sorted(hunks):
            out.extend(base[pos:h.start])
            out.extend(h.added)
            pos = h.start + len(h.removed)
        out.extend(base[pos:hi])
        return out


    def _units(base, ours, theirs):
        nodes = [("o", h) for h in diff(base, ours)] + [("t", h) for h in diff(base, theirs)]
        parent = list(range(len(nodes)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if nodes[i][0] != nodes[j][0] and _interact(_span(nodes[i][1]), _span(nodes[j][1])):
                    parent[find(i)] = find(j)
        groups = {}
        for i in range(len(nodes)):
            groups.setdefault(find(i), []).append(nodes[i])
        units = []
        for members in groups.values():
            lo = min(_span(h)[0] for _, h in members)
            hi = max(_span(h)[1] for _, h in members)
            units.append((lo, hi, [h for s, h in members if s == "o"], [h for s, h in members if s == "t"]))
        units.sort(key=lambda u: (u[0], u[1]))
        return units


    def merge3(base, ours, theirs, prefer=None):
        if prefer not in (None, "ours", "theirs"):
            raise ValueError("prefer must be None, 'ours' or 'theirs'")
        out = []
        pos = 0
        conflicts = 0
        for lo, hi, o_hunks, t_hunks in _units(base, ours, theirs):
            out.extend(base[pos:lo])
            o_text = _apply(base, lo, hi, o_hunks)
            t_text = _apply(base, lo, hi, t_hunks)
            if not o_hunks or not t_hunks or o_text == t_text:
                out.extend(o_text if o_hunks else t_text)
            elif prefer == "ours":
                out.extend(o_text)
            elif prefer == "theirs":
                out.extend(t_text)
            else:
                conflicts += 1
                out.extend(["<<ours"] + o_text + ["=="] + t_text + ["theirs>>"])
            pos = hi
        out.extend(base[pos:])
        return MergeResult(out, conflicts)


    def parse_conflicts(lines):
        segments = []
        text = []
        state = "text"
        ours = theirs = None
        for line in lines:
            if line == "<<ours":
                if state != "text":
                    raise ValueError("conflict block inside a conflict block")
                if text:
                    segments.append(("text", text))
                    text = []
                state, ours, theirs = "ours", [], []
            elif line == "==" and state != "text":
                if state != "ours":
                    raise ValueError("second == in a conflict block")
                state = "theirs"
            elif line == "theirs>>" and state != "text":
                if state != "theirs":
                    raise ValueError("theirs>> before ==")
                segments.append(("conflict", ours, theirs))
                state = "text"
            elif line in ("==", "theirs>>"):
                raise ValueError("marker outside a conflict block")
            elif state == "ours":
                ours.append(line)
            elif state == "theirs":
                theirs.append(line)
            else:
                text.append(line)
        if state != "text":
            raise ValueError("unterminated conflict block")
        if text:
            segments.append(("text", text))
        return segments
''')

TW_INIT = dd(r'''
    from .lcs import Hunk, diff  # noqa: F401
    from .merge import MergeResult, merge3, parse_conflicts  # noqa: F401
''')

TW_VISIBLE = dd(r'''
    import unittest

    from threeway import Hunk, diff, merge3

    BASE = ["a", "b", "c", "d", "e"]


    class BasicTests(unittest.TestCase):
        def test_diff(self):
            self.assertEqual(diff(BASE, ["a", "X", "c", "d", "e"]), [Hunk(1, ("b",), ("X",))])

        def test_clean_merge(self):
            got = merge3(BASE, ["a", "B", "c", "d", "e"], ["a", "b", "c", "D", "e"])
            self.assertEqual(got.lines, ["a", "B", "c", "D", "e"])
            self.assertEqual(got.conflicts, 0)


    if __name__ == "__main__":
        unittest.main()
''')

TW_HIDDEN = dd(r'''
    import unittest

    from threeway import Hunk, MergeResult, diff, merge3, parse_conflicts

    BASE = ["a", "b", "c", "d", "e"]


    def M(base, ours, theirs, **kw):
        return merge3(base, ours, theirs, **kw)


    class Diff(unittest.TestCase):
        def test_equal(self):
            self.assertEqual(diff([], []), [])
            self.assertEqual(diff(BASE, BASE), [])

        def test_starts_are_zero_based(self):
            self.assertEqual(diff(BASE, ["a", "X", "c", "d", "e"]), [Hunk(1, ("b",), ("X",))])
            self.assertEqual(diff(BASE, ["X", "b", "c", "d", "e"]), [Hunk(0, ("a",), ("X",))])
            self.assertEqual(diff(BASE, ["a", "b", "c", "d", "X"]), [Hunk(4, ("e",), ("X",))])
            self.assertEqual(diff(BASE, ["a", "c", "d", "e"]), [Hunk(1, ("b",), ())])
            self.assertEqual(diff(BASE, ["a", "b", "N", "c", "d", "e"]), [Hunk(2, (), ("N",))])
            self.assertEqual(diff(BASE, BASE + ["f", "g"]), [Hunk(5, (), ("f", "g"))])
            self.assertEqual(diff(BASE, ["z"] + BASE), [Hunk(0, (), ("z",))])
            self.assertEqual(diff([], ["x"]), [Hunk(0, (), ("x",))])
            self.assertEqual(diff(["x"], []), [Hunk(0, ("x",), ())])

        def test_several_hunks(self):
            got = diff(["a", "b", "c", "d", "e", "f"], ["a", "B", "c", "d", "f", "g"])
            self.assertEqual(got, [Hunk(1, ("b",), ("B",)), Hunk(4, ("e",), ()), Hunk(6, (), ("g",))])

        def test_tie_breaking(self):
            self.assertEqual(diff(["a", "b"], ["b", "a"]), [Hunk(0, ("a",), ()), Hunk(2, (), ("a",))])
            self.assertEqual(diff(["x"], ["y"]), [Hunk(0, ("x",), ("y",))])
            self.assertEqual(diff(["a", "a"], ["a"]), [Hunk(1, ("a",), ())])
            self.assertEqual(diff(["a"], ["a", "a"]), [Hunk(1, (), ("a",))])

        def test_multi_line_hunk(self):
            self.assertEqual(diff(BASE, ["a", "X", "Y", "d", "e"]), [Hunk(1, ("b", "c"), ("X", "Y"))])
            self.assertEqual(diff(["k", "a", "b", "m"], ["k", "x", "m"]), [Hunk(1, ("a", "b"), ("x",))])


    class OneSideOnly(unittest.TestCase):
        def test_only_ours(self):
            self.assertEqual(M(BASE, ["a", "B", "c", "d", "e"], BASE), MergeResult(["a", "B", "c", "d", "e"], 0))

        def test_only_theirs(self):
            self.assertEqual(M(BASE, BASE, ["a", "b", "c", "D", "e"]), MergeResult(["a", "b", "c", "D", "e"], 0))

        def test_nothing_changed(self):
            self.assertEqual(M(BASE, BASE, BASE), MergeResult(BASE, 0))
            self.assertEqual(M([], [], []), MergeResult([], 0))

        def test_empty_base(self):
            self.assertEqual(M([], ["x"], []), MergeResult(["x"], 0))
            self.assertEqual(M([], [], ["y"]), MergeResult(["y"], 0))

        def test_input_untouched(self):
            base, ours, theirs = list(BASE), ["a", "X", "c", "d", "e"], ["a", "Y", "c", "d", "e"]
            M(base, ours, theirs)
            self.assertEqual((base, ours, theirs), (BASE, ["a", "X", "c", "d", "e"], ["a", "Y", "c", "d", "e"]))


    class Independent(unittest.TestCase):
        def test_distant_changes(self):
            got = M(BASE, ["a", "B", "c", "d", "e"], ["a", "b", "c", "D", "e"])
            self.assertEqual(got, MergeResult(["a", "B", "c", "D", "e"], 0))
            got = M(BASE, ["a", "b", "c", "D", "e"], ["a", "B", "c", "d", "e"])
            self.assertEqual(got, MergeResult(["a", "B", "c", "D", "e"], 0))

        def test_adjacent_replacements(self):
            got = M(BASE, ["a", "X", "c", "d", "e"], ["a", "b", "Y", "d", "e"])
            self.assertEqual(got, MergeResult(["a", "X", "Y", "d", "e"], 0))
            got = M(BASE, ["a", "b", "Y", "d", "e"], ["a", "X", "c", "d", "e"])
            self.assertEqual(got, MergeResult(["a", "X", "Y", "d", "e"], 0))

        def test_insert_at_edge_of_a_deletion(self):
            got = M(BASE, ["a", "b", "N", "c", "d", "e"], ["a", "b", "d", "e"])
            self.assertEqual(got, MergeResult(["a", "b", "N", "d", "e"], 0))
            got = M(BASE, ["a", "b", "d", "e"], ["a", "b", "N", "c", "d", "e"])
            self.assertEqual(got, MergeResult(["a", "b", "N", "d", "e"], 0))
            got = M(BASE, ["a", "b", "c", "N", "d", "e"], ["a", "b", "d", "e"])
            self.assertEqual(got, MergeResult(["a", "b", "N", "d", "e"], 0))

        def test_changes_at_both_ends(self):
            got = M(BASE, ["z", "a", "b", "c", "d", "e"], ["a", "b", "c", "d", "e", "f"])
            self.assertEqual(got, MergeResult(["z", "a", "b", "c", "d", "e", "f"], 0))

        def test_several_hunks_per_side(self):
            ours = ["A", "b", "c", "D", "e"]
            theirs = ["a", "B", "c", "d", "E"]
            self.assertEqual(M(BASE, ours, theirs), MergeResult(["A", "B", "c", "D", "E"], 0))


    class SameChange(unittest.TestCase):
        def test_identical_replacement(self):
            got = M(BASE, ["a", "X", "c", "d", "e"], ["a", "X", "c", "d", "e"])
            self.assertEqual(got, MergeResult(["a", "X", "c", "d", "e"], 0))

        def test_identical_deletion(self):
            got = M(BASE, ["a", "c", "d", "e"], ["a", "c", "d", "e"])
            self.assertEqual(got, MergeResult(["a", "c", "d", "e"], 0))

        def test_identical_insertion(self):
            got = M(BASE, ["a", "b", "X", "c", "d", "e"], ["a", "b", "X", "c", "d", "e"])
            self.assertEqual(got, MergeResult(["a", "b", "X", "c", "d", "e"], 0))

        def test_same_result_reached_differently(self):
            ours = ["a", "X", "d", "e"]
            theirs = ["a", "X", "d", "e"]
            self.assertEqual(M(BASE, ours, theirs), MergeResult(["a", "X", "d", "e"], 0))


    class Conflicts(unittest.TestCase):
        def test_same_line_changed_differently(self):
            got = M(BASE, ["a", "X", "c", "d", "e"], ["a", "Y", "c", "d", "e"])
            self.assertEqual(got.lines, ["a", "<<ours", "X", "==", "Y", "theirs>>", "c", "d", "e"])
            self.assertEqual(got.conflicts, 1)

        def test_prefer(self):
            ours, theirs = ["a", "X", "c", "d", "e"], ["a", "Y", "c", "d", "e"]
            self.assertEqual(M(BASE, ours, theirs, prefer="ours"), MergeResult(["a", "X", "c", "d", "e"], 0))
            self.assertEqual(M(BASE, ours, theirs, prefer="theirs"), MergeResult(["a", "Y", "c", "d", "e"], 0))
            self.assertEqual(M(BASE, ours, theirs, prefer=None).conflicts, 1)

        def test_prefer_validation(self):
            for bad in ("both", "", "OURS", 1):
                with self.assertRaises(ValueError):
                    M(BASE, BASE, BASE, prefer=bad)

        def test_prefer_does_not_touch_clean_parts(self):
            ours = ["A", "X", "c", "d", "e"]
            theirs = ["a", "Y", "c", "D", "e"]
            self.assertEqual(M(BASE, ours, theirs, prefer="ours").lines, ["A", "X", "c", "D", "e"])
            self.assertEqual(M(BASE, ours, theirs, prefer="theirs").lines, ["a", "Y", "c", "D", "e"])

        def test_deletion_against_edit(self):
            got = M(BASE, ["a", "c", "d", "e"], ["a", "B", "c", "d", "e"])
            self.assertEqual(got.lines, ["a", "<<ours", "==", "B", "theirs>>", "c", "d", "e"])
            self.assertEqual(got.conflicts, 1)
            got = M(BASE, ["a", "B", "c", "d", "e"], ["a", "c", "d", "e"])
            self.assertEqual(got.lines, ["a", "<<ours", "B", "==", "theirs>>", "c", "d", "e"])

        def test_insertion_inside_a_replaced_range(self):
            got = M(BASE, ["a", "X", "d", "e"], ["a", "b", "N", "c", "d", "e"])
            self.assertEqual(got.lines, ["a", "<<ours", "X", "==", "b", "N", "c", "theirs>>", "d", "e"])
            self.assertEqual(got.conflicts, 1)

        def test_insertions_at_the_same_point(self):
            got = M(BASE, ["a", "b", "X", "c", "d", "e"], ["a", "b", "Y", "c", "d", "e"])
            self.assertEqual(got.lines, ["a", "b", "<<ours", "X", "==", "Y", "theirs>>", "c", "d", "e"])
            self.assertEqual(got.conflicts, 1)
            got = M(BASE, BASE + ["x"], BASE + ["y"])
            self.assertEqual(got.lines, BASE + ["<<ours", "x", "==", "y", "theirs>>"])
            got = M([], ["x"], ["y"])
            self.assertEqual(got.lines, ["<<ours", "x", "==", "y", "theirs>>"])

        def test_range_deleted_against_edit_inside(self):
            got = M(BASE, ["a", "e"], ["a", "b", "C", "d", "e"])
            self.assertEqual(got.lines, ["a", "<<ours", "==", "b", "C", "d", "theirs>>", "e"])

        def test_cluster_of_several_hunks(self):
            ours = ["A", "b", "C", "d", "e"]
            theirs = ["Z", "d", "e"]
            got = M(BASE, ours, theirs)
            self.assertEqual(got.lines, ["<<ours", "A", "b", "C", "==", "Z", "theirs>>", "d", "e"])
            self.assertEqual(got.conflicts, 1)

        def test_two_separate_conflicts(self):
            ours = ["a", "X", "c", "X2", "e"]
            theirs = ["a", "Y", "c", "Y2", "e"]
            got = M(BASE, ours, theirs)
            self.assertEqual(got.lines, ["a", "<<ours", "X", "==", "Y", "theirs>>", "c", "<<ours", "X2", "==", "Y2", "theirs>>", "e"])
            self.assertEqual(got.conflicts, 2)

        def test_conflict_and_clean_change_together(self):
            ours = ["A", "X", "c", "d", "e"]
            theirs = ["a", "Y", "c", "d", "E"]
            got = M(BASE, ours, theirs)
            self.assertEqual(got.lines, ["<<ours", "A", "X", "==", "a", "Y", "theirs>>", "c", "d", "E"])
            self.assertEqual(got.conflicts, 1)

        def test_only_directly_interacting_hunks_form_a_unit(self):
            ours = ["a", "X", "Y", "d", "e"]
            theirs = ["a", "X", "c", "Y", "e"]
            got = M(BASE, ours, theirs)
            self.assertEqual(got.conflicts, 1)
            self.assertEqual(got.lines, ["a", "<<ours", "X", "Y", "==", "X", "c", "theirs>>", "Y", "e"])

        def test_whole_file_replaced_both_ways(self):
            got = M(BASE, ["p"], ["q"])
            self.assertEqual(got.lines, ["<<ours", "p", "==", "q", "theirs>>"])
            self.assertEqual(M(BASE, ["p"], ["p"]), MergeResult(["p"], 0))
            self.assertEqual(M(BASE, [], ["q"]).lines, ["<<ours", "==", "q", "theirs>>"])


    class ParseConflicts(unittest.TestCase):
        def test_segments(self):
            lines = ["a", "<<ours", "X", "==", "Y", "theirs>>", "c", "d", "<<ours", "==", "Z", "theirs>>"]
            self.assertEqual(parse_conflicts(lines), [("text", ["a"]), ("conflict", ["X"], ["Y"]), ("text", ["c", "d"]), ("conflict", [], ["Z"])])

        def test_no_conflicts_and_empty(self):
            self.assertEqual(parse_conflicts(["a", "b"]), [("text", ["a", "b"])])
            self.assertEqual(parse_conflicts([]), [])
            self.assertEqual(parse_conflicts(["<<ours", "==", "theirs>>"]), [("conflict", [], [])])

        def test_adjacent_blocks(self):
            lines = ["<<ours", "a", "==", "b", "theirs>>", "<<ours", "c", "==", "d", "theirs>>"]
            self.assertEqual(parse_conflicts(lines), [("conflict", ["a"], ["b"]), ("conflict", ["c"], ["d"])])

        def test_marker_lookalikes_are_text(self):
            lines = ["== x", "<<ours ", " ==", "theirs>> y", "===", "<<<ours"]
            self.assertEqual(parse_conflicts(lines), [("text", lines)])

        def test_errors(self):
            bad = [
                ["==", "x"], ["theirs>>"], ["a", "==", "b"], ["<<ours", "a"], ["<<ours", "a", "=="], ["<<ours", "a", "==", "b"], ["<<ours", "<<ours", "==", "theirs>>"],
                ["<<ours", "a", "==", "b", "==", "theirs>>"], ["<<ours", "a", "theirs>>"], ["<<ours", "==", "<<ours", "theirs>>"], ["x", "theirs>>", "y"],
            ]
            for lines in bad:
                with self.assertRaises(ValueError, msg=str(lines)):
                    parse_conflicts(lines)

        def test_round_trip_with_merge(self):
            got = M(BASE, ["a", "X", "c", "X2", "e"], ["a", "Y", "c", "Y2", "e"])
            segs = parse_conflicts(got.lines)
            self.assertEqual([s[0] for s in segs], ["text", "conflict", "text", "conflict", "text"])
            self.assertEqual(segs[1][1:], (["X"], ["Y"]))
            self.assertEqual(segs[3][1:], (["X2"], ["Y2"]))
            self.assertEqual(len([s for s in segs if s[0] == "conflict"]), got.conflicts)


    if __name__ == "__main__":
        unittest.main()
''')

TW = Lib(
    name="threeway", lang="python", title="the three-way merge package (`threeway/`)",
    blurb="The wiki's offline editor merges concurrent edits of a page with this package.",
    files={"threeway/__init__.py": TW_INIT, "threeway/lcs.py": TW_LCS, "threeway/merge.py": TW_MERGE, "README.md": TW_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": TW_VISIBLE},
    hidden_tests={"tests/test_full.py": TW_HIDDEN},
    mutate=["threeway/lcs.py", "threeway/merge.py"], difficulty=4, tags=["merge", "diff", "text"],
    probes=[
        'diff(["a", "b", "c", "d", "e"], ["a", "b", "N", "c", "d", "e"])',
        'diff(["a", "b"], ["b", "a"])',
        'merge3(["a", "b", "c", "d", "e"], ["a", "X", "c", "d", "e"], ["a", "Y", "c", "d", "e"])',
        'merge3(["a", "b", "c", "d", "e"], ["a", "b", "N", "c", "d", "e"], ["a", "b", "d", "e"]).lines',
        'merge3(["a", "b", "c", "d", "e"], ["a", "X", "d", "e"], ["a", "b", "N", "c", "d", "e"]).lines',
        'merge3(["a", "b", "c", "d", "e"], ["A", "b", "C", "d", "e"], ["Z", "d", "e"]).lines',
        'merge3(["a", "b", "c", "d", "e"], ["a", "X", "c", "d", "e"], ["a", "Y", "c", "d", "e"], prefer="theirs").lines',
        'merge3([], ["x"], ["y"]).lines',
        'merge3(["a", "b"], ["a", "X"], ["a", "X"])',
        'parse_conflicts(["a", "<<ours", "X", "==", "Y", "theirs>>", "c"])',
    ],
    probe_import="from threeway import *",
)


LIBS = [TW]
register_libs(LIBS, n=10)
