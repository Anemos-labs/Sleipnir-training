"""Text-format libraries (python), batch: ordering and fixed-width records."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# natsort: shelf ordering of titles and unique numbered names
# ======================================================================================================================

NS_README = dd(r'''
    # natsort

    Ordering rules of the library catalogue. One module, `natsort.py`.

    ## `sort_key(text) -> tuple`
    The key that defines the order. It is built in these steps:
    1. `text` is stripped of surrounding whitespace. If it then starts with the article `the`, `a` or `an` (any capitalisation) followed by whitespace
       and at least one more non-blank character, that article and the whitespace after it are removed (only one article, only at the start).
       `"A"`, `"The"` and `"Theodore"` keep their text.
    2. Every run of whitespace, `_` and `-` characters becomes one space, and the result is stripped again.
    3. The result is case-folded (`str.casefold()`).
    4. It is cut into chunks: maximal runs of ASCII digits and maximal runs of anything else. A digit chunk becomes `(0, int(chunk), "")`, any other chunk
       `(1, 0, chunk)`, so at the same position numbers come before text, numbers compare by value, text by code points.
    5. The key is `(chunks as a tuple, zeros, original text)` where `zeros` is the total number of leading zeros of all digit chunks (a chunk of only
       zeros, such as `000`, counts all its digits), and the original text is `text` exactly as given. So equal-looking titles order by fewer
       leading zeros first, then by the plain order of the original strings.

    ## `natsorted(items, key=None, reverse=False) -> list`
    A new list of `items` sorted by `sort_key` of `key(item)` (or of the item itself when `key` is `None`). Stable. With `reverse=True` the order is
    the exact reverse of the sort key order, except that items with equal keys keep their original relative order.

    ## `compare(a, b) -> int`
    `-1`, `0` or `1` comparing `sort_key(a)` and `sort_key(b)`.

    ## `unique_name(base, existing) -> str`
    A name not yet used. Names are compared case-insensitively (`casefold`). If `base` is not among `existing`, it is returned unchanged. Otherwise
    numbered candidates are tried: if `base` ends with a space and digits (`"report 3"`), the stem is the text before that space and the counter
    starts at that number plus one; otherwise the stem is `base` and the counter starts at 2. The candidates `stem + " " + str(counter)` are tried
    with an increasing counter and the first one not in `existing` is returned (written with the stem's own capitalisation).
''')

NS_SRC = dd(r'''
    """Natural ordering and unique names."""
    import re

    _ARTICLE = re.compile(r"(?:the|a|an)\s+(?=\S)", re.I)
    _CHUNK = re.compile(r"[0-9]+|[^0-9]+")


    def sort_key(text):
        t = text.strip()
        m = _ARTICLE.match(t)
        if m:
            t = t[m.end():]
        t = re.sub(r"[\s_-]+", " ", t).strip().casefold()
        chunks = []
        zeros = 0
        for c in _CHUNK.findall(t):
            if c[0].isdigit():
                chunks.append((0, int(c), ""))
                zeros += len(c) - len(c.lstrip("0"))
            else:
                chunks.append((1, 0, c))
        return (tuple(chunks), zeros, text)


    def natsorted(items, key=None, reverse=False):
        pick = key if key is not None else (lambda x: x)
        return sorted(items, key=lambda x: sort_key(pick(x)), reverse=reverse)


    def compare(a, b):
        ka, kb = sort_key(a), sort_key(b)
        return (ka > kb) - (ka < kb)


    def unique_name(base, existing):
        taken = {e.casefold() for e in existing}
        if base.casefold() not in taken:
            return base
        m = re.fullmatch(r"(.*) ([0-9]+)", base)
        stem, counter = (m.group(1), int(m.group(2)) + 1) if m else (base, 2)
        while ("%s %d" % (stem, counter)).casefold() in taken:
            counter += 1
        return "%s %d" % (stem, counter)
''')

NS_VISIBLE = dd(r'''
    import unittest

    from natsort import natsorted, sort_key, unique_name


    class BasicTests(unittest.TestCase):
        def test_numbers(self):
            self.assertEqual(natsorted(["img12", "img2", "img1"]), ["img1", "img2", "img12"])

        def test_articles(self):
            self.assertEqual(natsorted(["The Hobbit", "Dune"]), ["Dune", "The Hobbit"])

        def test_unique(self):
            self.assertEqual(unique_name("report", ["report", "report 2"]), "report 3")


    if __name__ == "__main__":
        unittest.main()
''')

NS_HIDDEN = dd(r'''
    import unittest

    from natsort import compare, natsorted, sort_key, unique_name


    class Order(unittest.TestCase):
        def test_numbers_by_value(self):
            self.assertEqual(natsorted(["img12", "img2", "img1", "Img10"]), ["img1", "img2", "Img10", "img12"])
            self.assertEqual(natsorted(["v10", "v9", "v100", "v1"]), ["v1", "v9", "v10", "v100"])
            self.assertEqual(natsorted(["a2b10", "a2b9", "a10b1", "a1b99"]), ["a1b99", "a2b9", "a2b10", "a10b1"])
            self.assertEqual(natsorted(["99999999999999999999", "100000000000000000000"]), ["99999999999999999999", "100000000000000000000"])

        def test_case_is_folded_then_original_breaks_ties(self):
            self.assertEqual(natsorted(["b", "B", "a"]), ["a", "B", "b"])
            self.assertEqual(natsorted(["Zed", "alpha", "Beta"]), ["alpha", "Beta", "Zed"])
            self.assertEqual(natsorted(["ß", "ss"]), ["ss", "ß"])

        def test_leading_zeros(self):
            self.assertEqual(natsorted(["x007", "x7", "x07"]), ["x7", "x07", "x007"])
            self.assertEqual(natsorted(["x10", "x9", "x010"]), ["x9", "x10", "x010"])
            self.assertEqual(natsorted(["a01b2", "a1b02", "a1b2"]), ["a1b2", "a01b2", "a1b02"])
            self.assertEqual(natsorted(["0", "00", "000", "1"]), ["0", "00", "000", "1"])
            self.assertEqual(natsorted(["01", "1", "001"]), ["1", "01", "001"])

        def test_zeros_count_is_total(self):
            self.assertEqual(natsorted(["a01b01", "a001b2", "a1b1", "a01b1"]), ["a1b1", "a01b1", "a01b01", "a001b2"])

        def test_numbers_before_text(self):
            self.assertEqual(natsorted(["abc", "1abc", "9", "Abc"]), ["1abc", "9", "Abc", "abc"])
            self.assertEqual(natsorted(["k b", "k 1", "k"]), ["k", "k 1", "k b"])
            self.assertEqual(natsorted(["file b", "file 2", "file 10"]), ["file 2", "file 10", "file b"])

        def test_separators_are_spaces(self):
            self.assertEqual(sort_key("file_2")[0], sort_key("file 2")[0])
            self.assertEqual(sort_key("file-2")[0], sort_key("file 2")[0])
            self.assertEqual(sort_key("  file \t _ - 2  ")[0], sort_key("file 2")[0])
            self.assertEqual(natsorted(["x_y", "x y", "x-y", "x  y"]), ["x  y", "x y", "x-y", "x_y"])
            self.assertEqual(natsorted(["x-3", "x_10", "x 2"]), ["x 2", "x-3", "x_10"])

        def test_articles(self):
            self.assertEqual(natsorted(["The Hobbit", "A Wizard of Earthsea", "An Ember in the Ashes", "Dune"]),
                             ["Dune", "An Ember in the Ashes", "The Hobbit", "A Wizard of Earthsea"])
            self.assertEqual(natsorted(["the zebra", "ant", "THE bee"]), ["ant", "THE bee", "the zebra"])

        def test_article_edge_cases(self):
            self.assertEqual(sort_key("A")[0], sort_key("a")[0])
            self.assertEqual(sort_key("A")[0], ((1, 0, "a"),))
            self.assertEqual(sort_key("The")[0], ((1, 0, "the"),))
            self.assertEqual(sort_key("Theodore")[0], ((1, 0, "theodore"),))
            self.assertEqual(sort_key("The A Team")[0], ((1, 0, "a team"),))
            self.assertEqual(sort_key("  The   Hobbit ")[0], ((1, 0, "hobbit"),))
            self.assertEqual(sort_key("An  ")[0], ((1, 0, "an"),))
            self.assertEqual(sort_key("Another")[0], ((1, 0, "another"),))
            self.assertEqual(sort_key("a1")[0], ((1, 0, "a"), (0, 1, "")))
            self.assertEqual(sort_key("The 39 Steps")[0], ((0, 39, ""), (1, 0, " steps")))
            self.assertEqual(sort_key("a_b")[0], ((1, 0, "a b"),))
            self.assertEqual(sort_key("a b")[0], ((1, 0, "b"),))
            self.assertEqual(sort_key("x y")[0], ((1, 0, "x y"),))
            self.assertEqual(sort_key("a 1")[0], ((0, 1, ""),))

        def test_key_structure(self):
            self.assertEqual(sort_key("File007"), (((1, 0, "file"), (0, 7, "")), 2, "File007"))
            self.assertEqual(sort_key(" x "), (((1, 0, "x"),), 0, " x "))
            self.assertEqual(sort_key("a000b"), (((1, 0, "a"), (0, 0, ""), (1, 0, "b")), 3, "a000b"))
            self.assertEqual(sort_key("1.50"), (((0, 1, ""), (1, 0, "."), (0, 50, "")), 0, "1.50"))
            self.assertEqual(sort_key("1.05"), (((0, 1, ""), (1, 0, "."), (0, 5, "")), 1, "1.05"))
            self.assertEqual(sort_key(""), ((), 0, ""))

        def test_decimals_are_separate_numbers(self):
            self.assertEqual(natsorted(["1.10", "1.9", "1.2", "1.02"]), ["1.2", "1.02", "1.9", "1.10"])

        def test_empty_and_single(self):
            self.assertEqual(natsorted([]), [])
            self.assertEqual(natsorted(["x"]), ["x"])
            self.assertEqual(natsorted(["b", "", "a"]), ["", "a", "b"])


    class Options(unittest.TestCase):
        def test_key_function(self):
            rows = [("img12", 1), ("img2", 2), ("img1", 3)]
            self.assertEqual(natsorted(rows, key=lambda r: r[0]), [("img1", 3), ("img2", 2), ("img12", 1)])
            self.assertEqual(natsorted({"b2": 1, "b10": 2, "b1": 3}), ["b1", "b2", "b10"])

        def test_reverse(self):
            self.assertEqual(natsorted(["img1", "img12", "img2"], reverse=True), ["img12", "img2", "img1"])
            self.assertEqual(natsorted(["b", "a"], reverse=True), ["b", "a"])

        def test_reverse_keeps_stability_for_equal_keys(self):
            rows = [("x1", "first"), ("x1", "second"), ("x2", "third")]
            self.assertEqual(natsorted(rows, key=lambda r: r[0], reverse=True), [("x2", "third"), ("x1", "first"), ("x1", "second")])
            self.assertEqual(natsorted(rows, key=lambda r: r[0]), [("x1", "first"), ("x1", "second"), ("x2", "third")])

        def test_stable_for_identical_titles(self):
            rows = [("same", 1), ("same", 2), ("same", 3)]
            self.assertEqual(natsorted(rows, key=lambda r: r[0]), rows)

        def test_input_untouched(self):
            data = ["b", "a"]
            natsorted(data)
            self.assertEqual(data, ["b", "a"])

        def test_compare(self):
            self.assertEqual(compare("a2", "a10"), -1)
            self.assertEqual(compare("a10", "a2"), 1)
            self.assertEqual(compare("a2", "a2"), 0)
            self.assertEqual(compare("a02", "a2"), 1)
            self.assertEqual(compare("The Hobbit", "Hobbit"), 1)
            self.assertEqual(compare("Hobbit", "The Hobbit"), -1)
            self.assertEqual(compare("hobbit", "The Hobbit"), 1)
            self.assertEqual(compare("B", "b"), -1)
            self.assertEqual(compare("1", "a"), -1)


    class UniqueName(unittest.TestCase):
        def test_free_base(self):
            self.assertEqual(unique_name("report", []), "report")
            self.assertEqual(unique_name("report", ["other"]), "report")
            self.assertEqual(unique_name("report 2", ["report"]), "report 2")
            self.assertEqual(unique_name("", []), "")

        def test_numbering_starts_at_two(self):
            self.assertEqual(unique_name("report", ["report"]), "report 2")
            self.assertEqual(unique_name("report", ["report", "report 3"]), "report 2")
            self.assertEqual(unique_name("report", ["report", "report 2", "report 3"]), "report 4")
            self.assertEqual(unique_name("report", ["report", "report 2", "report 4"]), "report 3")

        def test_case_insensitive(self):
            self.assertEqual(unique_name("Report", ["report"]), "Report 2")
            self.assertEqual(unique_name("report", ["REPORT", "Report 2"]), "report 3")
            self.assertEqual(unique_name("Report", ["REPORT"]), "Report 2")
            self.assertEqual(unique_name("Straße", ["straße"]), "Straße 2")

        def test_base_with_number_continues_from_it(self):
            self.assertEqual(unique_name("report 3", ["report", "report 3"]), "report 4")
            self.assertEqual(unique_name("report 3", ["report 3", "report 4", "REPORT 5"]), "report 6")
            self.assertEqual(unique_name("report 3", ["report 2", "report 3"]), "report 4")
            self.assertEqual(unique_name("report 3", ["report 4"]), "report 3")
            self.assertEqual(unique_name("Report 9", ["report 9"]), "Report 10")
            self.assertEqual(unique_name("x 007", ["x 007"]), "x 8")
            self.assertEqual(unique_name("x 0", ["x 0"]), "x 1")

        def test_only_trailing_number_counts(self):
            self.assertEqual(unique_name("v 2 beta", ["v 2 beta"]), "v 2 beta 2")
            self.assertEqual(unique_name("a1", ["a1"]), "a1 2")
            self.assertEqual(unique_name("2024", ["2024"]), "2024 2")
            self.assertEqual(unique_name("a  7", ["a  7"]), "a  8")
            self.assertEqual(unique_name("a 1 2", ["a 1 2"]), "a 1 3")

        def test_existing_can_be_any_iterable(self):
            self.assertEqual(unique_name("a", iter(["a", "a 2"])), "a 3")
            self.assertEqual(unique_name("a", {"a", "a 2"}), "a 3")
            self.assertEqual(unique_name("a", ("a",)), "a 2")


    if __name__ == "__main__":
        unittest.main()
''')

NS = Lib(
    name="natsort", lang="python", title="the catalogue ordering helpers (`natsort.py`)",
    blurb="The library catalogue orders titles and invents unique numbered names with this module.",
    files={"natsort.py": NS_SRC, "README.md": NS_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": NS_VISIBLE},
    hidden_tests={"tests/test_full.py": NS_HIDDEN},
    mutate=["natsort.py"], difficulty=1, tags=["sorting", "text"],
    probes=[
        'natsorted(["img12", "img2", "img1", "Img10"])',
        'natsorted(["x007", "x7", "x07"])',
        'natsorted(["b", "B", "a"])',
        'natsorted(["The Hobbit", "A Wizard of Earthsea", "An Ember in the Ashes", "Dune"])',
        'natsorted(["a b", "a 1", "a"])',
        'natsorted(["x-3", "x_10", "x 2"])',
        'sort_key("The 39 Steps")',
        'sort_key("a000b")',
        'compare("a02", "a2")',
        'unique_name("report", ["report", "report 3"])',
        'unique_name("report 3", ["report 3", "report 4", "REPORT 5"])',
        'unique_name("Report", ["REPORT", "report 2"])',
    ],
    probe_import="from natsort import *",
)


# ======================================================================================================================
# fixedrec: fixed-width record layouts (decode and encode)
# ======================================================================================================================

FR_README = dd(r'''
    # fixedrec

    Reader and writer for the fixed-width records exchanged with the mainframe. One module, `fixedrec.py`.

    ## Layouts
    `parse_layout(spec) -> list[Field]`. `Field` is a `namedtuple` `(name, start, end, kind, scale)`. `spec` is a list of fields separated by commas
    (blanks around any part are ignored, empty items are skipped); a field is `NAME:COLUMNS:TYPE`:
    * `NAME`: `[a-z_][a-z0-9_]*`, unique in the layout.
    * `COLUMNS`: `START-END` or a single `START`; columns are **1-based and inclusive** (`7-16` is ten characters); `START` is at least 1 and `END` at
      least `START`. Fields must not overlap; gaps between fields are allowed (they are blank on encoding, ignored on decoding). The order of the
      fields in the spec is kept.
    * `TYPE`: `str`, `int`, `date`, `flag` or `decN` with `N` from 0 to 6 (`dec2` is a decimal number with two implied decimals); a `dec` field has
      `kind` `"dec"` and `scale` N; for all other kinds `scale` is 0. A `date` field must be exactly 8 columns wide and a `flag` field exactly 1.
    Anything else, and an empty layout, is a `ValueError`. `record_width(layout) -> int` is the largest `end`.

    ## `decode(line, layout) -> dict`
    A trailing `\r\n` or `\n` is removed from `line`; a line shorter than the record width is padded with spaces; text beyond the record width is ignored.
    Each field is the slice of its columns, converted by kind (blank means all spaces):
    * `str`: the slice with trailing spaces removed (leading spaces stay); a blank field is `""`.
    * `int`: the slice stripped of spaces must be `[+-]?digits` and gives an `int`; blank gives `None`.
    * `dec`: the same digits give `Decimal(n).scaleb(-scale)` (so `00123450` with scale 2 is `Decimal("1234.50")`); blank gives `None`.
    * `date`: eight digits `YYYYMMDD` that form a real date give a `datetime.date`; blank gives `None`.
    * `flag`: `Y` gives `True`, `N` gives `False`, blank gives `None`.
    A bad value raises `ValueError` whose message starts with `field 'NAME':`.

    ## `encode(record, layout) -> str`
    `record` is a dict; keys that are not in the layout are ignored; a missing key or a `None` value leaves the field blank (all spaces). The line has
    exactly `record_width` characters; columns that belong to no field are spaces. Field texts:
    * `str`: the text (`str(value)`), left-aligned and padded with spaces; longer than the field, or containing a line break, is a `ValueError`.
    * `int`: the number right-aligned and padded with `0` to the field width; a negative number is `-` followed by the zero-padded magnitude filling the
      rest of the width (`-7` in 6 columns is `-00007`). A number that does not fit is a `ValueError`.
    * `dec`: `value` is an `int`, a `Decimal` or a `str` holding a decimal number; it is multiplied by `10**scale`, which must give a whole number (else
      `ValueError`, nothing is rounded), and written like an `int`.
    * `date`: `YYYYMMDD`. A `date` is required.
    * `flag`: `Y` for `True`, `N` for `False`; any other value is a `ValueError`.
    Errors from a field have messages starting with `field 'NAME':`. `decode(encode(r, L), L) == r` for records of values that fit (missing values
    come back as `None`, blank strings as `""`).
''')

FR_SRC = dd(r'''
    """Fixed-width records."""
    import re
    from collections import namedtuple
    from datetime import date
    from decimal import Decimal

    Field = namedtuple("Field", "name start end kind scale")

    _NAME = re.compile(r"[a-z_][a-z0-9_]*")
    _COLS = re.compile(r"([0-9]+)(?:-([0-9]+))?")
    _KIND = re.compile(r"str|int|date|flag|dec([0-6])")


    def parse_layout(spec):
        fields = []
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            bits = [b.strip() for b in part.split(":")]
            if len(bits) != 3:
                raise ValueError("bad field %r" % part)
            name, cols, kind = bits
            if not _NAME.fullmatch(name):
                raise ValueError("bad field name %r" % name)
            if any(f.name == name for f in fields):
                raise ValueError("duplicate field %r" % name)
            m = _COLS.fullmatch(cols)
            if not m:
                raise ValueError("bad columns %r" % cols)
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) is not None else start
            if start < 1 or end < start:
                raise ValueError("bad columns %r" % cols)
            km = _KIND.fullmatch(kind)
            if not km:
                raise ValueError("bad type %r" % kind)
            scale = int(km.group(1)) if km.group(1) is not None else 0
            base = "dec" if km.group(1) is not None else kind
            width = end - start + 1
            if (base == "date" and width != 8) or (base == "flag" and width != 1):
                raise ValueError("wrong width for %r" % name)
            if any(start <= f.end and f.start <= end for f in fields):
                raise ValueError("field %r overlaps another" % name)
            fields.append(Field(name, start, end, base, scale))
        if not fields:
            raise ValueError("empty layout")
        return fields


    def record_width(layout):
        return max(f.end for f in layout)


    def _decode_field(text, f):
        if f.kind == "str":
            return text.rstrip(" ")
        t = text.strip(" ")
        if t == "":
            return None
        if f.kind == "flag":
            if t not in ("Y", "N"):
                raise ValueError("bad flag %r" % t)
            return t == "Y"
        if f.kind == "date":
            if not re.fullmatch(r"[0-9]{8}", t):
                raise ValueError("bad date %r" % t)
            return date(int(t[:4]), int(t[4:6]), int(t[6:]))
        if not re.fullmatch(r"[+-]?[0-9]+", t):
            raise ValueError("bad number %r" % t)
        n = int(t)
        return n if f.kind == "int" else Decimal(n).scaleb(-f.scale)


    def decode(line, layout):
        line = line.rstrip("\r\n").ljust(record_width(layout))
        rec = {}
        for f in layout:
            try:
                rec[f.name] = _decode_field(line[f.start - 1:f.end], f)
            except ValueError as exc:
                raise ValueError("field %r: %s" % (f.name, exc)) from None
        return rec


    def _number(n, width):
        text = "-" + str(-n).zfill(width - 1) if n < 0 else str(n).zfill(width)
        if len(text) > width:
            raise ValueError("number does not fit in %d columns" % width)
        return text


    def _encode_field(v, f, width):
        if f.kind == "str":
            text = str(v)
            if "\n" in text or "\r" in text:
                raise ValueError("line break in text")
            if len(text) > width:
                raise ValueError("text is longer than %d columns" % width)
            return text.ljust(width)
        if f.kind == "int":
            return _number(int(v), width)
        if f.kind == "dec":
            scaled = Decimal(v).scaleb(f.scale)
            if scaled != scaled.to_integral_value():
                raise ValueError("more than %d decimals" % f.scale)
            return _number(int(scaled), width)
        if f.kind == "date":
            if not isinstance(v, date):
                raise ValueError("a date is required")
            return "%04d%02d%02d" % (v.year, v.month, v.day)
        if v is True:
            return "Y"
        if v is False:
            return "N"
        raise ValueError("a flag must be True or False")


    def encode(record, layout):
        out = [" "] * record_width(layout)
        for f in layout:
            v = record.get(f.name)
            if v is None:
                continue
            try:
                text = _encode_field(v, f, f.end - f.start + 1)
            except ValueError as exc:
                raise ValueError("field %r: %s" % (f.name, exc)) from None
            out[f.start - 1:f.end] = list(text)
        return "".join(out)
''')

FR_VISIBLE = dd(r'''
    import unittest
    from datetime import date
    from decimal import Decimal

    from fixedrec import decode, encode, parse_layout, record_width

    L = parse_layout("id:1-6:int, name:7-16:str, amount:17-25:dec2, born:26-33:date, active:34:flag")


    class BasicTests(unittest.TestCase):
        def test_width(self):
            self.assertEqual(record_width(L), 34)

        def test_decode(self):
            rec = decode("000042Ada King  00012345019900517Y", L)
            self.assertEqual(rec["id"], 42)
            self.assertEqual(rec["name"], "Ada King")

        def test_encode_id(self):
            self.assertTrue(encode({"id": 42}, L).startswith("000042"))


    if __name__ == "__main__":
        unittest.main()
''')

FR_HIDDEN = dd(r'''
    import unittest
    from datetime import date
    from decimal import Decimal

    from fixedrec import Field, decode, encode, parse_layout, record_width

    SPEC = "id:1-6:int, name:7-16:str, amount:17-25:dec2, born:26-33:date, active:34:flag"
    L = parse_layout(SPEC)
    LINE = "000042Ada King  00012345019900517Y"
    REC = {"id": 42, "name": "Ada King", "amount": Decimal("1234.50"), "born": date(1990, 5, 17), "active": True}


    class Layout(unittest.TestCase):
        def test_fields(self):
            self.assertEqual(L[0], Field("id", 1, 6, "int", 0))
            self.assertEqual(L[1], Field("name", 7, 16, "str", 0))
            self.assertEqual(L[2], Field("amount", 17, 25, "dec", 2))
            self.assertEqual(L[3], Field("born", 26, 33, "date", 0))
            self.assertEqual(L[4], Field("active", 34, 34, "flag", 0))
            self.assertEqual(record_width(L), 34)

        def test_single_column_and_order_kept(self):
            lay = parse_layout("b:9:str, a:1-3:int")
            self.assertEqual([f.name for f in lay], ["b", "a"])
            self.assertEqual(lay[0], Field("b", 9, 9, "str", 0))
            self.assertEqual(record_width(lay), 9)

        def test_blanks_and_empty_items(self):
            lay = parse_layout(" a : 1-3 : str ,, b:4:flag , ")
            self.assertEqual(lay, [Field("a", 1, 3, "str", 0), Field("b", 4, 4, "flag", 0)])

        def test_dec_scales(self):
            for n in range(0, 7):
                self.assertEqual(parse_layout("x:1-9:dec%d" % n)[0], Field("x", 1, 9, "dec", n))

        def test_adjacent_fields_are_fine_overlap_is_not(self):
            parse_layout("a:1-3:str, b:4-6:str")
            parse_layout("b:4-6:str, a:1-3:str")
            parse_layout("a:1:str, c:5:str")
            for bad in ("a:1-3:str, b:3-5:str", "a:1-3:str, b:2:str", "a:2:str, b:1-3:str", "a:1-3:str, b:1-3:str", "b:4-6:str, a:1-4:str"):
                with self.assertRaises(ValueError, msg=bad):
                    parse_layout(bad)

        def test_errors(self):
            for bad in ("", " , ", "a", "a:1", "a:1:str:x", "A:1:str", "1a:1:str", "a-b:1:str", "a:0:str", "a:0-3:str", "a:5-3:str", "a:x:str", "a:1-:str",
                        "a:-3:str", "a:1:text", "a:1:dec7", "a:1:dec", "a:1:dec-1", "a:1-7:date", "a:1-9:date", "a:1-2:flag", "a:1:str, a:2:str",
                        "a:1:STR", "a: :str", "a:1-2-3:str", "a:1:dec10"):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    parse_layout(bad)

        def test_date_and_flag_widths(self):
            self.assertEqual(parse_layout("d:3-10:date")[0].end, 10)
            self.assertEqual(parse_layout("f:3:flag")[0].start, 3)


    class Decode(unittest.TestCase):
        def test_full_line(self):
            self.assertEqual(decode(LINE, L), REC)

        def test_trailing_newlines_and_extra_text(self):
            self.assertEqual(decode(LINE + "\n", L), REC)
            self.assertEqual(decode(LINE + "\r\n", L), REC)
            self.assertEqual(decode(LINE + "ignored tail", L), REC)

        def test_short_line_is_padded(self):
            rec = decode("000042Ada", L)
            self.assertEqual(rec, {"id": 42, "name": "Ada", "amount": None, "born": None, "active": None})
            self.assertEqual(decode("", L), {"id": None, "name": "", "amount": None, "born": None, "active": None})

        def test_str_keeps_leading_spaces_only(self):
            lay = parse_layout("s:1-6:str")
            self.assertEqual(decode("  ab  ", lay), {"s": "  ab"})
            self.assertEqual(decode("      ", lay), {"s": ""})
            self.assertEqual(decode("ab\tc  ", lay), {"s": "ab\tc"})

        def test_int(self):
            lay = parse_layout("n:1-6:int")
            for text, want in (("000042", 42), ("    42", 42), ("42    ", 42), ("  -007", -7), ("+00012", 12), ("-00000", 0), ("000000", 0), ("999999", 999999),
                               ("", None), ("      ", None)):
                self.assertEqual(decode(text, lay), {"n": want}, text)

        def test_int_errors_name_the_field(self):
            lay = parse_layout("a:1-3:int, num:4-6:int")
            for bad in ("12 3 5", "1x3456", "1 3 45", "- 12", "1.5", "--1", "0x1", "1,0"):
                with self.assertRaises(ValueError, msg=bad) as cm:
                    decode(bad.ljust(6), lay)
                self.assertTrue(str(cm.exception).startswith("field "), str(cm.exception))

        def test_error_message_names_the_right_field(self):
            lay = parse_layout("a:1-3:int, num:4-6:int")
            with self.assertRaises(ValueError) as cm:
                decode("001x12", lay)
            self.assertTrue(str(cm.exception).startswith("field 'num':"), str(cm.exception))
            with self.assertRaises(ValueError) as cm:
                decode("0x1012", lay)
            self.assertTrue(str(cm.exception).startswith("field 'a':"), str(cm.exception))

        def test_dec(self):
            lay = parse_layout("a:1-9:dec2")
            self.assertEqual(decode("000123450", lay)["a"], Decimal("1234.50"))
            self.assertEqual(str(decode("000123450", lay)["a"]), "1234.50")
            self.assertEqual(decode("-00000005", lay)["a"], Decimal("-0.05"))
            self.assertEqual(str(decode("-00000005", lay)["a"]), "-0.05")
            self.assertEqual(decode("        7", lay)["a"], Decimal("0.07"))
            self.assertEqual(decode("         ", lay)["a"], None)
            self.assertEqual(decode("000000000", lay)["a"], Decimal("0.00"))
            self.assertEqual(str(decode("000000000", lay)["a"]), "0.00")

        def test_dec_scales(self):
            self.assertEqual(decode("12345", parse_layout("a:1-5:dec0"))["a"], Decimal("12345"))
            self.assertEqual(decode("12345", parse_layout("a:1-5:dec1"))["a"], Decimal("1234.5"))
            self.assertEqual(str(decode("12345", parse_layout("a:1-5:dec3"))["a"]), "12.345")
            self.assertEqual(str(decode("00012", parse_layout("a:1-5:dec6"))["a"]), "0.000012")

        def test_dec_errors(self):
            lay = parse_layout("a:1-9:dec2")
            for bad in ("12.50    ", "1 2 3    ", "abc      "):
                with self.assertRaises(ValueError, msg=bad):
                    decode(bad, lay)

        def test_date(self):
            lay = parse_layout("d:1-8:date")
            self.assertEqual(decode("19900517", lay)["d"], date(1990, 5, 17))
            self.assertEqual(decode("20000229", lay)["d"], date(2000, 2, 29))
            self.assertEqual(decode("        ", lay)["d"], None)
            for bad in ("19900231", "20010229", "19901301", "19900001", "1990051", "1990-5-1", "abcdefgh", "  199005", "19900517".replace("5", " ", 1)):
                with self.assertRaises(ValueError, msg=bad):
                    decode(bad, lay)

        def test_flag(self):
            lay = parse_layout("f:1:flag")
            self.assertEqual(decode("Y", lay), {"f": True})
            self.assertEqual(decode("N", lay), {"f": False})
            self.assertEqual(decode(" ", lay), {"f": None})
            for bad in ("y", "n", "1", "T", "X"):
                with self.assertRaises(ValueError, msg=bad):
                    decode(bad, lay)

        def test_gaps_are_ignored(self):
            lay = parse_layout("a:2:str, b:6-7:int")
            self.assertEqual(decode("xAyyy12", lay), {"a": "A", "b": 12})
            self.assertEqual(decode("!A???12", lay), {"a": "A", "b": 12})
            self.assertEqual(decode("xAyyy 1", lay), {"a": "A", "b": 1})

        def test_column_arithmetic(self):
            lay = parse_layout("a:1:str, b:2-3:str, c:4-6:str")
            self.assertEqual(decode("123456", lay), {"a": "1", "b": "23", "c": "456"})
            lay = parse_layout("late:4-5:str")
            self.assertEqual(decode("abcde", lay), {"late": "de"})


    class Encode(unittest.TestCase):
        def test_full_record(self):
            self.assertEqual(encode(REC, L), LINE)

        def test_missing_and_none_are_blank(self):
            self.assertEqual(encode({"id": 42}, L), "000042" + " " * 28)
            self.assertEqual(encode({}, L), " " * 34)
            self.assertEqual(encode({"id": None, "name": None, "amount": None}, L), " " * 34)
            self.assertEqual(encode({"unknown": 1, "id": 1}, L), "000001" + " " * 28)

        def test_gaps_are_spaces(self):
            lay = parse_layout("a:2:str, b:6-7:int")
            self.assertEqual(encode({"a": "A", "b": 12}, lay), " A   12")
            self.assertEqual(encode({"b": 3}, lay), "     03")

        def test_str(self):
            lay = parse_layout("s:1-5:str")
            self.assertEqual(encode({"s": "ab"}, lay), "ab   ")
            self.assertEqual(encode({"s": "abcde"}, lay), "abcde")
            self.assertEqual(encode({"s": ""}, lay), "     ")
            self.assertEqual(encode({"s": 12}, lay), "12   ")
            self.assertEqual(encode({"s": " x"}, lay), " x   ")
            for bad in ("abcdef", "a\nb", "a\rb"):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    encode({"s": bad}, lay)

        def test_int(self):
            lay = parse_layout("n:1-6:int")
            for value, want in ((42, "000042"), (0, "000000"), (999999, "999999"), (-7, "-00007"), (-99999, "-99999"), (1, "000001"), (-1, "-00001"), (100000, "100000")):
                self.assertEqual(encode({"n": value}, lay), want)

        def test_int_overflow(self):
            lay = parse_layout("n:1-6:int")
            for bad in (1000000, -100000, -1000000):
                with self.assertRaises(ValueError, msg=str(bad)) as cm:
                    encode({"n": bad}, lay)
                self.assertTrue(str(cm.exception).startswith("field 'n':"))
            self.assertEqual(encode({"n": 5}, parse_layout("n:1:int")), "5")
            with self.assertRaises(ValueError):
                encode({"n": -5}, parse_layout("n:1:int"))
            self.assertEqual(encode({"n": -5}, parse_layout("n:1-2:int")), "-5")

        def test_dec(self):
            lay = parse_layout("a:1-9:dec2")
            self.assertEqual(encode({"a": Decimal("1234.50")}, lay), "000123450")
            self.assertEqual(encode({"a": Decimal("1234.5")}, lay), "000123450")
            self.assertEqual(encode({"a": Decimal("1234.500")}, lay), "000123450")
            self.assertEqual(encode({"a": 12}, lay), "000001200")
            self.assertEqual(encode({"a": "3.14"}, lay), "000000314")
            self.assertEqual(encode({"a": Decimal("-0.05")}, lay), "-00000005")
            self.assertEqual(encode({"a": Decimal("0")}, lay), "000000000")
            self.assertEqual(encode({"a": Decimal("0.01")}, lay), "000000001")
            self.assertEqual(encode({"a": Decimal("-12.34")}, lay), "-00001234")
            self.assertEqual(encode({"a": Decimal("9999999.99")}, lay), "999999999")

        def test_dec_scales(self):
            self.assertEqual(encode({"a": Decimal("12")}, parse_layout("a:1-5:dec0")), "00012")
            self.assertEqual(encode({"a": Decimal("1.5")}, parse_layout("a:1-5:dec1")), "00015")
            self.assertEqual(encode({"a": Decimal("0.000012")}, parse_layout("a:1-5:dec6")), "00012")

        def test_dec_errors(self):
            lay = parse_layout("a:1-9:dec2")
            for bad in (Decimal("1.234"), "0.001", Decimal("10000000.00"), Decimal("-9999999.99"), Decimal("0.005")):
                with self.assertRaises((ValueError, ArithmeticError), msg=str(bad)):
                    encode({"a": bad}, lay)
            with self.assertRaises(ValueError) as cm:
                encode({"a": Decimal("1.234")}, lay)
            self.assertTrue(str(cm.exception).startswith("field 'a':"))
            with self.assertRaises(ValueError):
                encode({"a": Decimal("0.5")}, parse_layout("a:1-3:dec0"))

        def test_date(self):
            lay = parse_layout("d:1-8:date")
            self.assertEqual(encode({"d": date(1990, 5, 17)}, lay), "19900517")
            self.assertEqual(encode({"d": date(2000, 1, 2)}, lay), "20000102")
            self.assertEqual(encode({"d": date(999, 12, 31)}, lay), "09991231")
            for bad in ("19900517", 19900517, (1990, 5, 17)):
                with self.assertRaises(ValueError, msg=str(bad)):
                    encode({"d": bad}, lay)

        def test_flag(self):
            lay = parse_layout("f:1:flag")
            self.assertEqual(encode({"f": True}, lay), "Y")
            self.assertEqual(encode({"f": False}, lay), "N")
            self.assertEqual(encode({"f": None}, lay), " ")
            for bad in (1, 0, "Y", "yes", "", 2.0):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    encode({"f": bad}, lay)

        def test_record_not_modified(self):
            rec = dict(REC)
            encode(rec, L)
            self.assertEqual(rec, REC)


    class RoundTrip(unittest.TestCase):
        def test_samples(self):
            samples = [
                REC,
                {"id": -7, "name": "", "amount": Decimal("-0.05"), "born": date(2000, 2, 29), "active": False},
                {"id": 999999, "name": "X" * 10, "amount": Decimal("9999999.99"), "born": date(1999, 12, 31), "active": True},
                {"id": 0, "name": " lead", "amount": Decimal("0.00"), "born": date(2024, 1, 1), "active": None},
                {"id": None, "name": "", "amount": None, "born": None, "active": None},
            ]
            for rec in samples:
                line = encode(rec, L)
                self.assertEqual(len(line), 34)
                back = decode(line, L)
                self.assertEqual(back, rec)

        def test_str_trailing_spaces_are_lost(self):
            self.assertEqual(decode(encode({"name": "ab  "}, L), L)["name"], "ab")


    if __name__ == "__main__":
        unittest.main()
''')

FR = Lib(
    name="fixedrec", lang="python", title="the fixed-width record codec (`fixedrec.py`)",
    blurb="The nightly import reads and writes the mainframe's fixed-width records with this module.",
    files={"fixedrec.py": FR_SRC, "README.md": FR_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": FR_VISIBLE},
    hidden_tests={"tests/test_full.py": FR_HIDDEN},
    mutate=["fixedrec.py"], difficulty=3, tags=["formats", "records", "decimal"],
    probes=[
        'parse_layout("a:1-3:str, b:4:flag, c:5-13:dec2")',
        'record_width(parse_layout("b:9:str, a:1-3:int"))',
        'decode("000042Ada King  00012345019900517Y", parse_layout("id:1-6:int, name:7-16:str, amount:17-25:dec2, born:26-33:date, active:34:flag"))',
        'decode("  -007", parse_layout("n:1-6:int"))',
        'str(decode("-00000005", parse_layout("a:1-9:dec2"))["a"])',
        'decode("xAyyy 12", parse_layout("a:2:str, b:6-7:int"))',
        'encode({"n": -7}, parse_layout("n:1-6:int"))',
        'encode({"a": Decimal("-12.34")}, parse_layout("a:1-9:dec2"))',
        'encode({"a": "A", "b": 12}, parse_layout("a:2:str, b:6-7:int"))',
        'encode({"d": date(999, 12, 31)}, parse_layout("d:1-8:date"))',
        'encode({"f": True, "s": "ab"}, parse_layout("s:1-4:str, f:5:flag"))',
    ],
    probe_import="from datetime import date\nfrom decimal import Decimal\nfrom fixedrec import *",
)


# ======================================================================================================================
# searchq: the issue-search query language (parser and evaluator)
# ======================================================================================================================

SQ_README = dd(r'''
    # searchq

    The query language of the issue tracker's search box. One module, `searchq.py`.

    ## Syntax
    A query is made of *terms*, the operators `AND`, `OR`, `NOT` (upper case only) and parentheses.
    * **Tokens** are separated by whitespace. `(` and `)` are tokens of their own when they start a token or, for `)`, end one; in the middle of a
      word they are ordinary characters. A double quote starts a quoted part that runs to the next double quote and may contain whitespace and
      parentheses (the quotes are removed); a missing closing quote is a `ValueError`. A token that contains a quoted part is never an operator.
    * A **term** is one token (an empty one, such as `""`, is a `ValueError`). It can be:
      * `field:value` (the field is `[A-Za-z_][A-Za-z0-9_]*`): *equality*; `value` may be several alternatives separated by commas (`label:bug,feature`);
        alternatives must not be empty. `*` in a value matches any run of characters (possibly empty); the rest is literal; the whole text must match.
      * `field>=N`, `field<=N`, `field>N`, `field<N`: *comparison* with a number `N` (`-?digits[.digits]`, else `ValueError`).
      * anything else, including a token that *starts* with a quote, is a **text** term: a word or phrase.
      * A leading `-` directly before a term (a token starting with `-` and having more characters) negates it.
    * `NOT x` negates the following term or group. `a b` (juxtaposition) means `a AND b`.
    * Precedence from tightest: `NOT` / `-`, `AND` (explicit or implicit), `OR`. Parentheses group. Unbalanced parentheses, a missing operand (`a AND`,
      `OR a`, `NOT`), an empty query or a leftover `)` are a `ValueError`.

    ## `parse_query(text) -> node`
    A tuple tree: `("text", s)`, `("eq", field, (v1, ...))`, `("cmp", field, op, number)` with `number` a `float`, `("not", node)`, `("and", [nodes])`,
    `("or", [nodes])`. Texts and equality values are case-folded (`str.casefold()`). `and`/`or` nodes always have at least two children (a single
    operand is returned as is); a chain `a AND b AND c` is one node with three children, and so is `a b c`.

    ## `matches(record, node) -> bool`
    `record` is a dict.
    * `text`: true if the text is contained in any string value of the record or in any string item of a list/tuple value (case-folded comparison).
      Values that are not strings (numbers, `None`, ...) are never searched.
    * `eq`: the field's value (for a list or tuple: any of its items; missing or `None`: false) converted with `str()` and case-folded matches at
      least one alternative (with `*` wildcards, whole text).
    * `cmp`: the field's value must be a number (`int` or `float` but not `bool`) or a string that is a plain number (`-?digits[.digits]`); anything
      else, including a missing field, is false. Then the comparison with `number` is made.
    * `not`, `and`, `or` as usual.

    ## `search(records, text) -> list`
    The records for which the query matches, in their order. The query is parsed once; syntax errors are raised even for an empty list of records.

    ## `describe(node) -> str`
    A canonical text of the tree: text terms as the case-folded text, quoted with `"` when it contains whitespace or parentheses; `field:v1,v2` (values
    quoted when needed); `field>=N` with the number written without `.0` when it is whole; `NOT x`; `(a AND b)` and `(a OR b)` for nodes with
    several children (all children joined by the operator). `describe` of a single term has no parentheses.
''')

SQ_SRC = dd(r'''
    """Issue-search query language."""
    import re

    _FIELD = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(>=|<=|>|<|:)(.*)", re.S)
    _NUM = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")
    _OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, "<": lambda a, b: a < b}


    def tokenize(text):
        toks = []
        i, n = 0, len(text)
        while i < n:
            c = text[i]
            if c.isspace():
                i += 1
            elif c == "(":
                toks.append(("(", None))
                i += 1
            elif c == ")":
                toks.append((")", None))
                i += 1
            else:
                starts_quoted = c == '"'
                quoted = False
                buf = []
                while i < n and not text[i].isspace() and text[i] != ")":
                    if text[i] == '"':
                        j = text.find('"', i + 1)
                        if j < 0:
                            raise ValueError("unterminated quote")
                        buf.append(text[i + 1:j])
                        quoted = True
                        i = j + 1
                    else:
                        buf.append(text[i])
                        i += 1
                word = "".join(buf)
                if not quoted and word in ("AND", "OR", "NOT"):
                    toks.append((word, None))
                else:
                    toks.append(("term", (word, starts_quoted)))
        return toks


    def _term(word, starts_quoted):
        if not word:
            raise ValueError("empty term")
        negate = False
        if word.startswith("-") and len(word) > 1 and not starts_quoted:
            negate, word = True, word[1:]
        m = None if starts_quoted else _FIELD.fullmatch(word)
        if m:
            field, op, value = m.groups()
            if op == ":":
                values = tuple(v.casefold() for v in value.split(","))
                if any(v == "" for v in values):
                    raise ValueError("empty value in %r" % word)
                node = ("eq", field, values)
            else:
                if not _NUM.fullmatch(value):
                    raise ValueError("number expected in %r" % word)
                node = ("cmp", field, op, float(value))
        else:
            node = ("text", word.casefold())
        return ("not", node) if negate else node


    class _Parser:
        def __init__(self, toks):
            self.toks = toks
            self.i = 0

        def kind(self):
            return self.toks[self.i][0] if self.i < len(self.toks) else None

        def or_expr(self):
            nodes = [self.and_expr()]
            while self.kind() == "OR":
                self.i += 1
                nodes.append(self.and_expr())
            return nodes[0] if len(nodes) == 1 else ("or", nodes)

        def and_expr(self):
            nodes = [self.not_expr()]
            while True:
                if self.kind() == "AND":
                    self.i += 1
                elif self.kind() not in ("term", "(", "NOT"):
                    break
                nodes.append(self.not_expr())
            return nodes[0] if len(nodes) == 1 else ("and", nodes)

        def not_expr(self):
            if self.kind() == "NOT":
                self.i += 1
                return ("not", self.not_expr())
            return self.atom()

        def atom(self):
            kind = self.kind()
            if kind == "(":
                self.i += 1
                node = self.or_expr()
                if self.kind() != ")":
                    raise ValueError("missing )")
                self.i += 1
                return node
            if kind == "term":
                word, starts_quoted = self.toks[self.i][1]
                self.i += 1
                return _term(word, starts_quoted)
            raise ValueError("operand expected")


    def parse_query(text):
        toks = tokenize(text)
        if not toks:
            raise ValueError("empty query")
        p = _Parser(toks)
        node = p.or_expr()
        if p.i != len(toks):
            raise ValueError("unexpected token")
        return node


    def _strings(record):
        for v in record.values():
            if isinstance(v, str):
                yield v.casefold()
            elif isinstance(v, (list, tuple)):
                for item in v:
                    if isinstance(item, str):
                        yield item.casefold()


    def _glob(pattern, text):
        return re.fullmatch(".*".join(re.escape(p) for p in pattern.split("*")), text, re.S) is not None


    def _number(v):
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str) and _NUM.fullmatch(v):
            return float(v)
        return None


    def matches(record, node):
        kind = node[0]
        if kind == "and":
            return all(matches(record, n) for n in node[1])
        if kind == "or":
            return any(matches(record, n) for n in node[1])
        if kind == "not":
            return not matches(record, node[1])
        if kind == "text":
            return any(node[1] in s for s in _strings(record))
        if kind == "eq":
            value = record.get(node[1])
            items = value if isinstance(value, (list, tuple)) else [value]
            return any(x is not None and any(_glob(v, str(x).casefold()) for v in node[2]) for x in items)
        number = _number(record.get(node[1]))
        return number is not None and _OPS[node[2]](number, node[3])


    def search(records, text):
        node = parse_query(text)
        return [r for r in records if matches(r, node)]


    def _word(s):
        return '"%s"' % s if any(c.isspace() or c in "()" for c in s) else s


    def describe(node):
        kind = node[0]
        if kind == "text":
            return _word(node[1])
        if kind == "eq":
            return "%s:%s" % (node[1], ",".join(_word(v) for v in node[2]))
        if kind == "cmp":
            num = node[3]
            return "%s%s%s" % (node[1], node[2], repr(int(num)) if num == int(num) else repr(num))
        if kind == "not":
            return "NOT " + describe(node[1])
        return "(" + (" AND " if kind == "and" else " OR ").join(describe(n) for n in node[1]) + ")"
''')

SQ_VISIBLE = dd(r'''
    import unittest

    from searchq import parse_query, search

    RECORDS = [
        {"id": 1, "title": "Crash on startup", "status": "open", "label": ["bug"]},
        {"id": 2, "title": "Add dark mode", "status": "closed", "label": ["feature"]},
    ]


    class BasicTests(unittest.TestCase):
        def test_eq(self):
            self.assertEqual([r["id"] for r in search(RECORDS, "status:open")], [1])

        def test_text(self):
            self.assertEqual([r["id"] for r in search(RECORDS, "dark")], [2])

        def test_parse(self):
            self.assertEqual(parse_query("status:Open"), ("eq", "status", ("open",)))


    if __name__ == "__main__":
        unittest.main()
''')

SQ_HIDDEN = dd(r'''
    import unittest

    from searchq import describe, matches, parse_query, search, tokenize

    R = [
        {"id": 1, "title": "Crash on startup", "status": "open", "label": ["bug", "needs info"], "assignee": "me", "priority": 3},
        {"id": 2, "title": "Add dark mode", "status": "open", "label": ["feature"], "assignee": "ada", "priority": 1},
        {"id": 3, "title": "Crash when saving", "status": "closed", "label": ["bug"], "assignee": "me", "priority": "2"},
        {"id": 4, "title": "Docs typo", "status": "closed", "label": [], "priority": 0.5},
        {"id": 5, "title": "Slow search", "status": "open", "label": ["bug", "perf"], "assignee": "bob", "priority": 5},
    ]


    def ids(query, records=R):
        return [r["id"] for r in search(records, query)]


    class Equality(unittest.TestCase):
        def test_simple_and_case(self):
            self.assertEqual(ids("status:open"), [1, 2, 5])
            self.assertEqual(ids("status:OPEN"), [1, 2, 5])
            self.assertEqual(ids("STATUS:open"), [])
            self.assertEqual(ids("status:closed"), [3, 4])

        def test_list_fields_match_any_item(self):
            self.assertEqual(ids("label:bug"), [1, 3, 5])
            self.assertEqual(ids("label:perf"), [5])
            self.assertEqual(ids("label:BUG"), [1, 3, 5])

        def test_alternatives(self):
            self.assertEqual(ids("label:bug,feature"), [1, 2, 3, 5])
            self.assertEqual(ids("status:open,closed"), [1, 2, 3, 4, 5])
            self.assertEqual(ids("assignee:ada,bob"), [2, 5])

        def test_whole_text_must_match(self):
            self.assertEqual(ids("title:crash"), [])
            self.assertEqual(ids("label:needs"), [])
            self.assertEqual(ids("status:ope"), [])

        def test_wildcards(self):
            self.assertEqual(ids("title:*crash*"), [1, 3])
            self.assertEqual(ids("title:crash*"), [1, 3])
            self.assertEqual(ids("title:*mode"), [2])
            self.assertEqual(ids("title:*s*a*"), [1, 3, 5])
            self.assertEqual(ids("status:o*"), [1, 2, 5])
            self.assertEqual(ids("status:*"), [1, 2, 3, 4, 5])
            self.assertEqual(ids("status:*n"), [1, 2, 5])
            self.assertEqual(ids("assignee:*"), [1, 2, 3, 5])
            self.assertEqual(ids('title:"C*h on s*up"'), [1])

        def test_wildcard_is_the_only_special_character(self):
            rows = [{"t": "a.b"}, {"t": "axb"}, {"t": "a+b"}, {"t": "a?b"}, {"t": "[x]"}]
            self.assertEqual([r["t"] for r in search(rows, "t:a.b")], ["a.b"])
            self.assertEqual([r["t"] for r in search(rows, "t:a+b")], ["a+b"])
            self.assertEqual([r["t"] for r in search(rows, "t:a?b")], ["a?b"])
            self.assertEqual([r["t"] for r in search(rows, "t:[x]")], ["[x]"])
            self.assertEqual([r["t"] for r in search(rows, "t:a*b")], ["a.b", "axb", "a+b", "a?b"])

        def test_quoted_values(self):
            self.assertEqual(ids('label:"needs info"'), [1])
            self.assertEqual(ids('title:"Add dark mode"'), [2])
            self.assertEqual(ids('title:"crash*"'), [1, 3])
            self.assertEqual(ids('label:"needs info",perf'), [1, 5])

        def test_non_string_values_are_converted(self):
            self.assertEqual(ids("priority:3"), [1])
            self.assertEqual(ids("priority:2"), [3])
            self.assertEqual(ids("priority:0.5"), [4])
            self.assertEqual(ids("id:4"), [4])
            self.assertEqual(ids("id:1,2"), [1, 2])

        def test_missing_and_none(self):
            rows = [{"a": None, "b": "x"}, {"b": "y"}, {"a": "", "b": "z"}]
            self.assertEqual([r["b"] for r in search(rows, "a:*")], ["z"])
            self.assertEqual([r["b"] for r in search(rows, "-a:*")], ["x", "y"])

        def test_empty_list_matches_nothing(self):
            self.assertEqual(ids("label:*"), [1, 2, 3, 5])


    class Comparison(unittest.TestCase):
        def test_operators(self):
            self.assertEqual(ids("priority>=3"), [1, 5])
            self.assertEqual(ids("priority>2"), [1, 5])
            self.assertEqual(ids("priority<=1"), [2, 4])
            self.assertEqual(ids("priority<2"), [2, 4])
            self.assertEqual(ids("priority<1"), [4])
            self.assertEqual(ids("priority>1.5"), [1, 3, 5])
            self.assertEqual(ids("priority>=5"), [5])
            self.assertEqual(ids("priority<=0.5"), [4])
            self.assertEqual(ids("priority>-1"), [1, 2, 3, 4, 5])
            self.assertEqual(ids("priority<-1"), [])

        def test_non_numbers_never_match(self):
            self.assertEqual(ids("assignee>1"), [])
            self.assertEqual(ids("assignee<1"), [])
            self.assertEqual(ids("nothing>=0"), [])
            rows = [{"n": True}, {"n": False}, {"n": None}, {"n": "x"}, {"n": " 5"}, {"n": "5"}, {"n": 5.5}, {"n": [7]}]
            self.assertEqual([r["n"] for r in search(rows, "n>=0")], ["5", 5.5])

        def test_negative_numbers_in_records(self):
            rows = [{"t": -3}, {"t": "-2.5"}, {"t": 4}]
            self.assertEqual([r["t"] for r in search(rows, "t<0")], [-3, "-2.5"])
            self.assertEqual([r["t"] for r in search(rows, "t>=-2.5")], ["-2.5", 4])

        def test_bad_numbers(self):
            for bad in ("priority>x", "priority>", "priority>=1e3", "priority>=.5", "priority>=1.", "priority>+1", "priority<1.2.3", "priority>=--1"):
                with self.assertRaises(ValueError, msg=bad):
                    parse_query(bad)

        def test_number_nodes_are_floats(self):
            self.assertEqual(parse_query("p>=3"), ("cmp", "p", ">=", 3.0))
            self.assertIsInstance(parse_query("p>=3")[3], float)
            self.assertEqual(parse_query("p<-2.5"), ("cmp", "p", "<", -2.5))


    class TextTerms(unittest.TestCase):
        def test_substring_in_strings_and_list_items(self):
            self.assertEqual(ids("crash"), [1, 3])
            self.assertEqual(ids("CRASH"), [1, 3])
            self.assertEqual(ids("perf"), [5])
            self.assertEqual(ids("needs"), [1])
            self.assertEqual(ids("open"), [1, 2, 5])
            self.assertEqual(ids("ada"), [2])
            self.assertEqual(ids("zzz"), [])

        def test_numbers_are_not_searched_but_numeric_strings_are(self):
            self.assertEqual(ids("5"), [])
            self.assertEqual(ids("2"), [3])
            self.assertEqual(ids("3"), [])

        def test_phrases(self):
            self.assertEqual(ids('"dark mode"'), [2])
            self.assertEqual(ids('"dark  mode"'), [])
            self.assertEqual(ids('"needs info"'), [1])
            self.assertEqual(ids('"on start"'), [1])
            self.assertEqual(ids("dark mode"), [2])
            self.assertEqual(ids("dark crash"), [])

        def test_quoted_term_is_text_even_with_colon(self):
            rows = [{"t": "a:b"}, {"a": "b", "t": "x"}]
            self.assertEqual([r["t"] for r in search(rows, '"a:b"')], ["a:b"])
            self.assertEqual([r["t"] for r in search(rows, "a:b")], ["x"])
            self.assertEqual(parse_query('"a:b"'), ("text", "a:b"))

        def test_lowercase_operators_are_words(self):
            rows = [{"t": "salt and pepper"}, {"t": "salt"}, {"t": "pepper"}, {"t": "or else"}, {"t": "not now"}]
            self.assertEqual([r["t"] for r in search(rows, "salt and pepper")], ["salt and pepper"])
            self.assertEqual([r["t"] for r in search(rows, "or")], ["or else"])
            self.assertEqual([r["t"] for r in search(rows, "not")], ["not now"])

        def test_quoted_operators_are_words(self):
            rows = [{"t": "AND x"}, {"t": "and"}, {"t": "OR y"}, {"t": "NOT z"}, {"t": "plain"}]
            self.assertEqual([r["t"] for r in search(rows, '"AND"')], ["AND x", "and"])
            self.assertEqual([r["t"] for r in search(rows, '"OR"')], ["OR y"])
            self.assertEqual(parse_query('"NOT"'), ("text", "not"))
            self.assertEqual(parse_query('plain "AND" plain'), ("and", [("text", "plain"), ("text", "and"), ("text", "plain")]))

        def test_dash_alone_is_a_word(self):
            rows = [{"t": "a-b"}, {"t": "ab"}]
            self.assertEqual([r["t"] for r in search(rows, "-")], ["a-b"])

        def test_negated_text(self):
            self.assertEqual(ids("-crash"), [2, 4, 5])
            self.assertEqual(ids("NOT crash"), [2, 4, 5])
            self.assertEqual(ids('-"dark mode"'), [1, 3, 4, 5])


    class Logic(unittest.TestCase):
        def test_implicit_and_explicit(self):
            self.assertEqual(ids("status:open label:bug"), [1, 5])
            self.assertEqual(ids("status:open AND label:bug"), [1, 5])
            self.assertEqual(ids("status:open label:bug assignee:bob"), [5])

        def test_or(self):
            self.assertEqual(ids("label:bug OR label:feature"), [1, 2, 3, 5])
            self.assertEqual(ids("assignee:ada OR assignee:bob OR id:4"), [2, 4, 5])

        def test_negation(self):
            self.assertEqual(ids("-label:bug"), [2, 4])
            self.assertEqual(ids("NOT label:bug"), [2, 4])
            self.assertEqual(ids("status:open -assignee:me"), [2, 5])
            self.assertEqual(ids("-assignee:me"), [2, 4, 5])
            self.assertEqual(ids("NOT NOT status:open"), [1, 2, 5])
            self.assertEqual(ids("NOT -status:open"), [1, 2, 5])
            self.assertEqual(ids("- status:open"), [])

        def test_precedence(self):
            self.assertEqual(ids("label:bug OR label:feature status:open"), [1, 2, 3, 5])
            self.assertEqual(ids("label:feature status:open OR label:perf"), [2, 5])
            self.assertEqual(ids("NOT status:open OR label:feature"), [2, 3, 4])
            self.assertEqual(ids("NOT status:open label:feature"), [])
            self.assertEqual(ids("-status:open OR label:feature"), [2, 3, 4])

        def test_parentheses(self):
            self.assertEqual(ids("(label:bug OR label:feature) status:open"), [1, 2, 5])
            self.assertEqual(ids("NOT (status:open AND label:bug)"), [2, 3, 4])
            self.assertEqual(ids("((status:open))"), [1, 2, 5])
            self.assertEqual(ids("status:open (label:bug OR label:feature) -assignee:me"), [2, 5])
            self.assertEqual(ids("(status:open OR status:closed) AND (label:bug OR label:perf) priority>=3"), [1, 5])

        def test_parenthesis_spacing_and_inside_words(self):
            self.assertEqual(ids("(status:open)(label:bug)"), [1, 5])
            self.assertEqual(ids("( status:open )"), [1, 2, 5])
            rows = [{"t": "f(x)"}, {"t": "fx"}]
            self.assertEqual([r["t"] for r in search(rows, "f(x")], ["f(x)"])
            self.assertEqual([r["t"] for r in search(rows, '"f(x)"')], ["f(x)"])

        def test_operators_between_parentheses(self):
            self.assertEqual(ids("(label:perf) OR (label:feature)"), [2, 5])
            self.assertEqual(ids("(label:perf)(status:open)"), [5])

        def test_all_children_of_chains_are_kept(self):
            self.assertEqual(parse_query("a b c"), ("and", [("text", "a"), ("text", "b"), ("text", "c")]))
            self.assertEqual(parse_query("a AND b AND c"), ("and", [("text", "a"), ("text", "b"), ("text", "c")]))
            self.assertEqual(parse_query("a OR b OR c"), ("or", [("text", "a"), ("text", "b"), ("text", "c")]))
            self.assertEqual(parse_query("a b OR c d"), ("or", [("and", [("text", "a"), ("text", "b")]), ("and", [("text", "c"), ("text", "d")])]))
            self.assertEqual(parse_query("a AND NOT b"), ("and", [("text", "a"), ("not", ("text", "b"))]))
            self.assertEqual(parse_query("a"), ("text", "a"))
            self.assertEqual(parse_query("(a)"), ("text", "a"))

        def test_errors(self):
            for bad in ("", "   ", "(", ")", "a)", "(a", "((a)", "a AND", "AND a", "OR a", "a OR", "a OR OR b", "NOT", "a AND AND b", "()", "status:", "status:a,,b",
                        "status:,a", 'label:"open', '""', '"" a', "a (", "NOT NOT", "a NOT"):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    parse_query(bad)

        def test_errors_even_without_records(self):
            with self.assertRaises(ValueError):
                search([], "a AND")
            self.assertEqual(search([], "a"), [])


    class Parse(unittest.TestCase):
        def test_nodes(self):
            self.assertEqual(parse_query("status:Open"), ("eq", "status", ("open",)))
            self.assertEqual(parse_query("label:Bug,Feature"), ("eq", "label", ("bug", "feature")))
            self.assertEqual(parse_query("-assignee:me"), ("not", ("eq", "assignee", ("me",))))
            self.assertEqual(parse_query("CRASH"), ("text", "crash"))
            self.assertEqual(parse_query("p>=3"), ("cmp", "p", ">=", 3.0))
            self.assertEqual(parse_query("a:b:c"), ("eq", "a", ("b:c",)))
            self.assertEqual(parse_query("a_1:x"), ("eq", "a_1", ("x",)))
            self.assertEqual(parse_query("1a:x"), ("text", "1a:x"))
            self.assertEqual(parse_query("-a"), ("not", ("text", "a")))
            self.assertEqual(parse_query("--a"), ("not", ("text", "-a")))

        def test_tokenize(self):
            self.assertEqual(tokenize('a (b OR "c d") -e'), [("term", ("a", False)), ("(", None), ("term", ("b", False)), ("OR", None),
                                                           ("term", ("c d", True)), (")", None), ("term", ("-e", False))])
            self.assertEqual(tokenize("x:\"a b\"y"), [("term", ("x:a by", False))])
            self.assertEqual(tokenize("AND OR NOT"), [("AND", None), ("OR", None), ("NOT", None)])
            self.assertEqual(tokenize("and or not"), [("term", ("and", False)), ("term", ("or", False)), ("term", ("not", False))])
            self.assertEqual(tokenize(""), [])

        def test_whitespace_kinds(self):
            self.assertEqual(parse_query("a\tAND\nb"), ("and", [("text", "a"), ("text", "b")]))


    class Describe(unittest.TestCase):
        def test_terms(self):
            self.assertEqual(describe(parse_query("status:Open")), "status:open")
            self.assertEqual(describe(parse_query("CRASH")), "crash")
            self.assertEqual(describe(parse_query('"dark mode"')), '"dark mode"')
            self.assertEqual(describe(parse_query("label:bug,Feature")), "label:bug,feature")
            self.assertEqual(describe(parse_query('label:"needs info",perf')), 'label:"needs info",perf')
            self.assertEqual(describe(parse_query('"f(x)"')), '"f(x)"')

        def test_numbers(self):
            self.assertEqual(describe(parse_query("p>=3")), "p>=3")
            self.assertEqual(describe(parse_query("p<2.5")), "p<2.5")
            self.assertEqual(describe(parse_query("p>-1")), "p>-1")
            self.assertEqual(describe(parse_query("p<=3.0")), "p<=3")
            self.assertEqual(describe(parse_query("p>0.5")), "p>0.5")
            self.assertEqual(describe(parse_query("p<-0")), "p<0")

        def test_structure(self):
            q = 'status:open AND (label:bug OR label:Feature) -assignee:me priority>=3 "dark mode"'
            self.assertEqual(describe(parse_query(q)), '(status:open AND (label:bug OR label:feature) AND NOT assignee:me AND priority>=3 AND "dark mode")')
            self.assertEqual(describe(parse_query("a OR b")), "(a OR b)")
            self.assertEqual(describe(parse_query("a OR b OR c")), "(a OR b OR c)")
            self.assertEqual(describe(parse_query("NOT (a OR b)")), "NOT (a OR b)")
            self.assertEqual(describe(parse_query("NOT NOT a")), "NOT NOT a")
            self.assertEqual(describe(parse_query("a b OR c")), "((a AND b) OR c)")

        def test_round_trip(self):
            for q in ("a", "(a AND b)", "(a OR (b AND c))", "NOT (a OR b)", "(status:open AND NOT label:bug,feature)", "p>=3", '("x y" OR z)'):
                self.assertEqual(describe(parse_query(q)), q)


    class MatchesDirect(unittest.TestCase):
        def test_matches_on_nodes(self):
            node = parse_query("a:1 OR b:2")
            self.assertTrue(matches({"a": 1}, node))
            self.assertTrue(matches({"b": "2"}, node))
            self.assertFalse(matches({"a": 2, "b": 1}, node))
            self.assertFalse(matches({}, node))

        def test_tuple_values_behave_like_lists(self):
            self.assertTrue(matches({"t": ("x", "y")}, parse_query("t:y")))
            self.assertTrue(matches({"t": ("x", "y")}, parse_query("y")))
            self.assertFalse(matches({"t": (1, 2)}, parse_query("1")))


    if __name__ == "__main__":
        unittest.main()
''')

SQ = Lib(
    name="searchq", lang="python", title="the search query language (`searchq.py`)",
    blurb="The issue tracker parses and evaluates the search box's query language with this module.",
    files={"searchq.py": SQ_SRC, "README.md": SQ_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": SQ_VISIBLE},
    hidden_tests={"tests/test_full.py": SQ_HIDDEN},
    mutate=["searchq.py"], difficulty=4, tags=["parsing", "query", "evaluator"],
    probes=[
        'parse_query("a b OR c d")',
        'parse_query("NOT status:open OR label:Feature")',
        'parse_query("p>=3.0 -x:y \\"q r\\"")',
        'tokenize("x:\\"a b\\"y (z)")',
        'describe(parse_query("status:open AND (label:bug OR label:Feature) -assignee:me priority>=3"))',
        'describe(parse_query("a b OR c"))',
        'search([{"t": "salt and pepper"}, {"t": "or else"}], "or")',
        'search([{"n": 5}, {"n": "5"}, {"n": True}, {"n": "x"}], "n>=5")',
        'search([{"t": "a.b"}, {"t": "axb"}], "t:a.b")',
        'search([{"t": "crash on x", "s": "open"}, {"t": "dark", "s": "open"}], "s:o* -crash")',
    ],
    probe_import="from searchq import *",
)


# ======================================================================================================================
# globrules: glob patterns and the ordered keep/skip rule files of the sync tool
# ======================================================================================================================

GR_README = dd(r'''
    # globrules

    Which files does the sync tool copy? Glob patterns and ordered rule files. Package `globrules` with the modules `glob` (patterns) and `rules`
    (rule files).

    ## `globrules.glob`
    ### `match_glob(pattern, text) -> bool`
    Matches `text`, a relative path whose segments are separated by `/`, against `pattern` (the whole text must match; case-sensitive).
    * `*` matches any run of characters (possibly empty) that does not contain `/`; `?` matches exactly one character other than `/`.
    * `**` as a *whole segment* of the pattern (`a/**/b`, `**/x`, `a/**`, `**`) matches whole path segments: in the middle or at the start it
      stands for zero or more segments (`a/**/b` matches `a/b`, `a/x/b`, `a/x/y/b`; `**/x` matches `x` and `d/x`); at the end it stands for
      one or more segments (`a/**` matches `a/x` and `a/x/y`, not `a`); the pattern `**` alone matches every non-empty text. `**` inside a
      segment (`a**b`) is just two `*`.
    * `[abc]`, `[a-f]`, `[!abc]` / `[^abc]`: one character from (or, negated, not from) the set; a range runs from its first to its last character
      (a range written backwards, an empty set, or a missing `]` is a `ValueError`); a class never matches `/`.
    * `{a,b,c}`: alternatives (each may contain the other wildcards); several groups multiply out; groups cannot nest and must be closed, else `ValueError`.
    * A backslash makes the next character literal (`\*`, `\{`, `\\`); a trailing backslash is a `ValueError`.
    * Any other character stands for itself.

    ## `globrules.rules`
    ### `parse_rules(text) -> list[Rule]`
    `Rule` is a `namedtuple` `(sign, pattern, dir_only)`. Lines are stripped; empty lines and lines starting with `#` are skipped. Every other line
    is `+PATTERN` (keep) or `-PATTERN` (skip), the pattern stripped of blanks and not empty after the following steps: a trailing `/` is removed and sets
    `dir_only`; a leading `/` is removed. A line that does not start with `+` or `-`, an empty pattern, or an invalid glob is a `ValueError` whose
    message begins with `line N:` (N counts from 1, all lines included).

    ### `decide(rules, path, is_dir=False) -> str`
    `"keep"` or `"skip"` for a relative path (segments separated by `/`, no empty segments, no `.` or `..` segments, no leading `/`; otherwise `ValueError`).
    * A rule *matches* a path `p` (with `is_dir` telling whether `p` is a directory) if it is not `dir_only` or `p` is a directory, and: when its
      pattern contains a `/`, `match_glob(pattern, p)` holds; when it does not, the pattern matches the **last segment** of `p`.
    * For one path the answer is the sign of the *last* matching rule, `"keep"` if none matches.
    * The path is skipped if any of its ancestor directories is skipped (each ancestor is judged on its own as a directory, from the top); a later
      `+` rule cannot bring back a file below a skipped directory. Otherwise the answer for the path itself decides.

    ### `filter_paths(rules_text, paths, dirs=()) -> list[str]`
    The paths (in the given order) that are kept; the paths in `dirs` are treated as directories. `rules_text` is parsed with `parse_rules`.
''')

GR_GLOB = dd(r'''
    """Glob patterns."""
    import re


    def _brace_expand(p):
        i = 0
        while i < len(p):
            c = p[i]
            if c == "\\":
                i += 2
                continue
            if c == "{":
                j = i + 1
                alts = []
                cur = ""
                while True:
                    if j >= len(p):
                        raise ValueError("unterminated {")
                    d = p[j]
                    if d == "\\":
                        cur += p[j:j + 2]
                        j += 2
                        continue
                    if d == "{":
                        raise ValueError("nested {")
                    if d == ",":
                        alts.append(cur)
                        cur = ""
                    elif d == "}":
                        alts.append(cur)
                        break
                    else:
                        cur += d
                    j += 1
                rest = _brace_expand(p[j + 1:])
                return [p[:i] + a + r for a in alts for r in rest]
            i += 1
        return [p]


    def _class(seg, i):
        """seg[i] == '['. Returns (regex, next index)."""
        j = i + 1
        negate = False
        if j < len(seg) and seg[j] in "!^":
            negate = True
            j += 1
        items = []
        while True:
            if j >= len(seg):
                raise ValueError("unterminated [")
            c = seg[j]
            if c == "]":
                break
            if c == "\\":
                if j + 1 >= len(seg):
                    raise ValueError("backslash at the end")
                c = seg[j + 1]
                j += 1
            if j + 2 < len(seg) and seg[j + 1] == "-" and seg[j + 2] != "]":
                hi = seg[j + 2]
                if hi == "\\" and j + 3 < len(seg):
                    hi = seg[j + 3]
                    j += 1
                if hi < c:
                    raise ValueError("backwards range")
                items.append("%s-%s" % (re.escape(c), re.escape(hi)))
                j += 3
            else:
                items.append(re.escape(c))
                j += 1
        if not items:
            raise ValueError("empty character class")
        return "(?!/)[%s%s]" % ("^" if negate else "", "".join(items)), j + 1


    def _segment(seg):
        out = []
        i = 0
        while i < len(seg):
            c = seg[i]
            if c == "*":
                out.append("[^/]*")
            elif c == "?":
                out.append("[^/]")
            elif c == "[":
                rx, i = _class(seg, i)
                out.append(rx)
                continue
            elif c == "\\":
                if i + 1 >= len(seg):
                    raise ValueError("backslash at the end")
                out.append(re.escape(seg[i + 1]))
                i += 1
            else:
                out.append(re.escape(c))
            i += 1
        return "".join(out)


    def _to_regex(p):
        segs = p.split("/")
        out = []
        for idx, seg in enumerate(segs):
            last = idx == len(segs) - 1
            if seg == "**":
                out.append(".+" if last else "(?:[^/]+/)*")
            else:
                out.append(_segment(seg) + ("" if last else "/"))
        return "".join(out)


    def match_glob(pattern, text):
        found = False
        for p in _brace_expand(pattern):
            if re.fullmatch(_to_regex(p), text):
                found = True
        return found
''')

GR_RULES = dd(r'''
    """Ordered keep/skip rule files."""
    from collections import namedtuple

    from .glob import match_glob

    Rule = namedtuple("Rule", "sign pattern dir_only")


    def parse_rules(text):
        rules = []
        for no, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line[0] not in "+-":
                raise ValueError("line %d: a rule starts with + or -" % no)
            pattern = line[1:].strip()
            dir_only = pattern.endswith("/")
            if dir_only:
                pattern = pattern[:-1]
            if pattern.startswith("/"):
                pattern = pattern[1:]
            if not pattern:
                raise ValueError("line %d: empty pattern" % no)
            try:
                match_glob(pattern, "")
            except ValueError as exc:
                raise ValueError("line %d: %s" % (no, exc)) from None
            rules.append(Rule(line[0], pattern, dir_only))
        return rules


    def _applies(rule, path, is_dir):
        if rule.dir_only and not is_dir:
            return False
        if "/" in rule.pattern:
            return match_glob(rule.pattern, path)
        return match_glob(rule.pattern, path.rsplit("/", 1)[-1])


    def _own(rules, path, is_dir):
        answer = "keep"
        for rule in rules:
            if _applies(rule, path, is_dir):
                answer = "keep" if rule.sign == "+" else "skip"
        return answer


    def decide(rules, path, is_dir=False):
        segs = path.split("/")
        if not path or any(s in ("", ".", "..") for s in segs):
            raise ValueError("bad path: %r" % path)
        for i in range(1, len(segs)):
            if _own(rules, "/".join(segs[:i]), True) == "skip":
                return "skip"
        return _own(rules, path, is_dir)


    def filter_paths(rules_text, paths, dirs=()):
        rules = parse_rules(rules_text)
        return [p for p in paths if decide(rules, p, p in dirs) == "keep"]
''')

GR_INIT = dd(r'''
    from .glob import match_glob  # noqa: F401
    from .rules import Rule, decide, filter_paths, parse_rules  # noqa: F401
''')

GR_VISIBLE = dd(r'''
    import unittest

    from globrules import decide, filter_paths, match_glob, parse_rules


    class BasicTests(unittest.TestCase):
        def test_star(self):
            self.assertTrue(match_glob("*.py", "main.py"))
            self.assertFalse(match_glob("*.py", "src/main.py"))

        def test_rules(self):
            rules = parse_rules("-*.log\n+keep.log\n")
            self.assertEqual(decide(rules, "a.log"), "skip")
            self.assertEqual(decide(rules, "keep.log"), "keep")

        def test_filter(self):
            self.assertEqual(filter_paths("-build/", ["a.c", "build/a.o"], dirs=["build"]), ["a.c"])


    if __name__ == "__main__":
        unittest.main()
''')

GR_HIDDEN = dd(r'''
    import unittest

    from globrules import Rule, decide, filter_paths, match_glob, parse_rules


    def m(pattern, text):
        return match_glob(pattern, text)


    class Wildcards(unittest.TestCase):
        def test_literal(self):
            self.assertTrue(m("abc", "abc"))
            self.assertFalse(m("abc", "abcd"))
            self.assertFalse(m("abc", "xabc"))
            self.assertFalse(m("abc", "ABC"))
            self.assertTrue(m("a/b", "a/b"))
            self.assertFalse(m("a/b", "a/b/c"))
            self.assertTrue(m("a.b", "a.b"))
            self.assertFalse(m("a.b", "axb"))
            self.assertFalse(m("", "x"))
            self.assertTrue(m("", ""))

        def test_star(self):
            self.assertTrue(m("*.py", "main.py"))
            self.assertTrue(m("*.py", ".py"))
            self.assertFalse(m("*.py", "main.pyc"))
            self.assertFalse(m("*.py", "src/main.py"))
            self.assertTrue(m("a*", "a"))
            self.assertTrue(m("a*b", "ab"))
            self.assertTrue(m("a*b", "axxb"))
            self.assertFalse(m("a*b", "a/b"))
            self.assertTrue(m("*", "anything"))
            self.assertFalse(m("*", "a/b"))
            self.assertTrue(m("src/*.c", "src/x.c"))
            self.assertFalse(m("src/*.c", "src/sub/x.c"))
            self.assertTrue(m("a*b*c", "aXbYc"))
            self.assertTrue(m("*/*", "a/b"))
            self.assertFalse(m("*/*", "a/b/c"))

        def test_question_mark(self):
            self.assertTrue(m("a?c", "abc"))
            self.assertFalse(m("a?c", "ac"))
            self.assertFalse(m("a?c", "abbc"))
            self.assertFalse(m("a?c", "a/c"))
            self.assertTrue(m("???", "xyz"))

        def test_double_star_middle_and_start(self):
            self.assertTrue(m("a/**/b", "a/b"))
            self.assertTrue(m("a/**/b", "a/x/b"))
            self.assertTrue(m("a/**/b", "a/x/y/b"))
            self.assertFalse(m("a/**/b", "ab"))
            self.assertFalse(m("a/**/b", "a/xb"))
            self.assertFalse(m("a/**/b", "x/a/b"))
            self.assertTrue(m("**/x", "x"))
            self.assertTrue(m("**/x", "d/x"))
            self.assertTrue(m("**/x", "d/e/x"))
            self.assertFalse(m("**/x", "dx"))
            self.assertFalse(m("**/x", "d/xy"))
            self.assertTrue(m("**/*.c", "a/b/c.c"))
            self.assertTrue(m("**/*.c", "c.c"))

        def test_double_star_at_the_end(self):
            self.assertTrue(m("a/**", "a/x"))
            self.assertTrue(m("a/**", "a/x/y"))
            self.assertFalse(m("a/**", "a"))
            self.assertFalse(m("a/**", "ab/x"))
            self.assertTrue(m("**", "a"))
            self.assertTrue(m("**", "a/b/c"))
            self.assertFalse(m("**", ""))

        def test_double_star_inside_a_segment(self):
            self.assertTrue(m("a**b", "axb"))
            self.assertFalse(m("a**b", "a/b"))
            self.assertFalse(m("a**b", "ax/yb"))
            self.assertTrue(m("src/a**", "src/abc"))
            self.assertFalse(m("src/a**", "src/abc/d"))

        def test_character_classes(self):
            self.assertTrue(m("[abc]x", "bx"))
            self.assertFalse(m("[abc]x", "dx"))
            self.assertTrue(m("[a-f]x", "cx"))
            self.assertTrue(m("[a-f]x", "ax"))
            self.assertTrue(m("[a-f]x", "fx"))
            self.assertFalse(m("[a-f]x", "gx"))
            self.assertTrue(m("[!abc]x", "dx"))
            self.assertFalse(m("[!abc]x", "ax"))
            self.assertTrue(m("[^abc]x", "dx"))
            self.assertFalse(m("[^abc]x", "bx"))
            self.assertTrue(m("[a-cx-z]", "y"))
            self.assertFalse(m("[a-cx-z]", "m"))
            self.assertTrue(m("[0-9][0-9]", "42"))
            self.assertFalse(m("[0-9][0-9]", "4x"))

        def test_class_never_matches_slash(self):
            self.assertFalse(m("a[!x]b", "a/b"))
            self.assertTrue(m("a[!x]b", "ayb"))

        def test_class_special_characters(self):
            self.assertTrue(m("[.]x", ".x"))
            self.assertFalse(m("[.]x", "ax"))
            self.assertTrue(m("[a-]", "-"))
            self.assertTrue(m("[a-]", "a"))
            self.assertTrue(m("[-a]", "-"))
            self.assertTrue(m(r"[\]]", "]"))
            self.assertTrue(m(r"[\-x]", "-"))
            self.assertFalse(m(r"[\-x]", "y"))
            self.assertTrue(m("[*?]", "*"))
            self.assertFalse(m("[*?]", "a"))
            self.assertTrue(m(r"[a-\z]", "m"))
            self.assertTrue(m(r"[a-\z]", "z"))
            self.assertFalse(m(r"[a-\z]", "A"))
            self.assertTrue(m(r"[#-\~]x", "ax"))
            self.assertFalse(m(r"[#-\~]x", " x"))

        def test_class_errors(self):
            for bad in ("[abc", "[", "[]", "[!]", "[z-a]", "[a-", r"[\]"):
                with self.assertRaises(ValueError, msg=bad):
                    m(bad, "x")

        def test_braces(self):
            self.assertTrue(m("*.{c,h}", "x.c"))
            self.assertTrue(m("*.{c,h}", "x.h"))
            self.assertFalse(m("*.{c,h}", "x.o"))
            self.assertTrue(m("{a,b}{c,d}", "bd"))
            self.assertTrue(m("{a,b}{c,d}", "ac"))
            self.assertFalse(m("{a,b}{c,d}", "ab"))
            self.assertTrue(m("src/{lib,bin}/*.rs", "src/lib/x.rs"))
            self.assertTrue(m("{a*,b}", "abc"))
            self.assertFalse(m("{a*,b}", "bc"))
            self.assertTrue(m("x{,y}", "x"))
            self.assertTrue(m("x{,y}", "xy"))
            self.assertTrue(m("{a,b/c}", "b/c"))
            self.assertTrue(m("{**/x,y}", "d/x"))

        def test_brace_errors(self):
            for bad in ("{a,b", "{", "{a,{b,c}}", "a{b{c}d}"):
                with self.assertRaises(ValueError, msg=bad):
                    m(bad, "x")

        def test_escapes(self):
            self.assertTrue(m(r"\*", "*"))
            self.assertFalse(m(r"\*", "a"))
            self.assertTrue(m(r"a\?b", "a?b"))
            self.assertFalse(m(r"a\?b", "axb"))
            self.assertTrue(m(r"\{a,b\}", "{a,b}"))
            self.assertTrue(m(r"\[x]", "[x]"))
            self.assertTrue(m(r"a\\b", "a\\b"))
            self.assertTrue(m(r"\\{x,y}", "\\y"))
            self.assertTrue(m(r"\{{a,b}", "{b"))
            self.assertFalse(m(r"\{{a,b}", "b"))
            self.assertTrue(m(r"\a", "a"))
            self.assertTrue(m(r"{a\,b,c}", "a,b"))
            self.assertFalse(m(r"{a\,b,c}", "a"))
            with self.assertRaises(ValueError):
                m("abc\\", "abc")

        def test_regex_characters_are_literal(self):
            self.assertTrue(m("a+b", "a+b"))
            self.assertFalse(m("a+b", "aab"))
            self.assertTrue(m("(a|b)", "(a|b)"))
            self.assertFalse(m("(a|b)", "a"))
            self.assertTrue(m("a$", "a$"))
            self.assertTrue(m("^a", "^a"))
            self.assertTrue(m("a.b*", "a.bxx"))


    class ParseRules(unittest.TestCase):
        def test_basic(self):
            rules = parse_rules("# comment\n\n-*.log\n+keep.log\n  - build/ \n-/top.txt\n+src/**\n")
            self.assertEqual(rules, [Rule("-", "*.log", False), Rule("+", "keep.log", False), Rule("-", "build", True), Rule("-", "top.txt", False),
                                     Rule("+", "src/**", False)])

        def test_empty(self):
            self.assertEqual(parse_rules(""), [])
            self.assertEqual(parse_rules("\n# only comments\n   \n"), [])

        def test_slash_handling(self):
            self.assertEqual(parse_rules("-/a/b/"), [Rule("-", "a/b", True)])
            self.assertEqual(parse_rules("-a//"), [Rule("-", "a/", True)])
            self.assertEqual(parse_rules("-//a"), [Rule("-", "/a", False)])

        def test_errors_have_line_numbers(self):
            cases = [("*.log", 1), ("-*.log\nbuild/", 2), ("\n\n!x", 3), ("-", 1), ("+ ", 1), ("-/", 1), ("# c\n-[abc", 2), ("-a{b", 1), ("-x\\", 1),
                     ("-[z-a]", 1), ("-{a,{b}}", 1), ("+ok\n\n- /  ", 3)]
            for text, line in cases:
                with self.assertRaises(ValueError, msg=repr(text)) as cm:
                    parse_rules(text)
                self.assertTrue(str(cm.exception).startswith("line %d:" % line), (text, str(cm.exception)))

        def test_crlf_and_trailing_spaces(self):
            self.assertEqual(parse_rules("-a.log  \r\n+b\r\n"), [Rule("-", "a.log", False), Rule("+", "b", False)])


    class Decide(unittest.TestCase):
        def test_default_is_keep(self):
            self.assertEqual(decide([], "a/b.txt"), "keep")
            self.assertEqual(decide(parse_rules("-*.log"), "a.txt"), "keep")

        def test_basename_rules_match_at_any_depth(self):
            r = parse_rules("-*.log")
            self.assertEqual(decide(r, "x.log"), "skip")
            self.assertEqual(decide(r, "a/b/x.log"), "skip")
            self.assertEqual(decide(r, "a/x.logs"), "keep")
            self.assertEqual(decide(r, "a.log/x"), "skip")

        def test_rules_with_slash_match_the_whole_path(self):
            r = parse_rules("-src/*.tmp")
            self.assertEqual(decide(r, "src/a.tmp"), "skip")
            self.assertEqual(decide(r, "x/src/a.tmp"), "keep")
            self.assertEqual(decide(r, "src/sub/a.tmp"), "keep")
            r = parse_rules("-**/gen/*.c")
            self.assertEqual(decide(r, "gen/a.c"), "skip")
            self.assertEqual(decide(r, "x/y/gen/a.c"), "skip")
            self.assertEqual(decide(r, "x/gen/a.h"), "keep")

        def test_leading_slash_is_just_removed(self):
            r = parse_rules("-/top.txt")
            self.assertEqual(decide(r, "top.txt"), "skip")
            self.assertEqual(decide(r, "d/top.txt"), "skip")
            r = parse_rules("-/d/top.txt")
            self.assertEqual(decide(r, "d/top.txt"), "skip")
            self.assertEqual(decide(r, "x/d/top.txt"), "keep")

        def test_last_matching_rule_wins(self):
            r = parse_rules("-*.log\n+keep.log")
            self.assertEqual(decide(r, "a.log"), "skip")
            self.assertEqual(decide(r, "keep.log"), "keep")
            self.assertEqual(decide(r, "d/keep.log"), "keep")
            r = parse_rules("+keep.log\n-*.log")
            self.assertEqual(decide(r, "keep.log"), "skip")
            r = parse_rules("-a\n+a\n-a")
            self.assertEqual(decide(r, "a"), "skip")
            r = parse_rules("-*\n+*.c")
            self.assertEqual(decide(r, "x.c"), "keep")
            self.assertEqual(decide(r, "x.h"), "skip")

        def test_dir_only_rules(self):
            r = parse_rules("-build/")
            self.assertEqual(decide(r, "build", is_dir=True), "skip")
            self.assertEqual(decide(r, "build"), "keep")
            self.assertEqual(decide(r, "build/x.o"), "skip")
            self.assertEqual(decide(r, "src/build/x.o"), "skip")
            self.assertEqual(decide(r, "src/build", is_dir=True), "skip")
            self.assertEqual(decide(r, "src/build"), "keep")
            self.assertEqual(decide(r, "builder/x"), "keep")
            self.assertEqual(decide(r, "mybuild/x"), "keep")

        def test_skipped_ancestor_wins_over_later_keep(self):
            r = parse_rules("-vendor/\n+vendor/keep.txt\n+*.txt")
            self.assertEqual(decide(r, "vendor/keep.txt"), "skip")
            self.assertEqual(decide(r, "vendor/a/b.txt"), "skip")
            self.assertEqual(decide(r, "other.txt"), "keep")

        def test_keep_rule_can_rescue_a_directory_before_its_files(self):
            r = parse_rules("-vendor/\n+vendor/")
            self.assertEqual(decide(r, "vendor/x.txt"), "keep")
            r = parse_rules("-*\n+*/\n+*.c")
            self.assertEqual(decide(r, "src/a.c"), "keep")
            self.assertEqual(decide(r, "src/a.h"), "skip")
            self.assertEqual(decide(r, "src", is_dir=True), "keep")

        def test_ancestors_are_judged_as_directories(self):
            r = parse_rules("-tmp")
            self.assertEqual(decide(r, "tmp/x"), "skip")
            self.assertEqual(decide(r, "a/tmp/x"), "skip")
            self.assertEqual(decide(r, "tmp", is_dir=True), "skip")
            r = parse_rules("-a/b/")
            self.assertEqual(decide(r, "a/b/c/d"), "skip")
            self.assertEqual(decide(r, "a/c/b/d"), "keep")

        def test_double_star_rules(self):
            r = parse_rules("-docs/**\n+docs/api/**")
            self.assertEqual(decide(r, "docs/readme.md"), "skip")
            self.assertEqual(decide(r, "docs/api/x.md"), "skip")
            self.assertEqual(decide(r, "docs", is_dir=True), "keep")
            r = parse_rules("-**/node_modules/")
            self.assertEqual(decide(r, "node_modules/x/y.js"), "skip")
            self.assertEqual(decide(r, "a/node_modules/x/y.js"), "skip")

        def test_bad_paths(self):
            for bad in ("", "/abs", "a//b", "a/", "./a", "a/./b", "../a", "a/../b", "a/.."):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    decide([], bad)

        def test_dotfiles_are_ordinary_names(self):
            r = parse_rules("-.*")
            self.assertEqual(decide(r, ".git/config"), "skip")
            self.assertEqual(decide(r, "a/.env"), "skip")
            self.assertEqual(decide(r, "a.b"), "keep")
            self.assertEqual(decide(r, "..x"), "skip")
            self.assertEqual(decide(r, "x..y"), "keep")


    class FilterPaths(unittest.TestCase):
        RULES = "# sync rules\n-*.log\n-build/\n+important.log\n-/secrets.txt\n-**/tmp/**\n"
        PATHS = ["main.c", "debug.log", "important.log", "logs/x.log", "build", "build/a.o", "src/build/b.o", "src/main.c", "secrets.txt", "docs/secrets.txt",
                 "tmp/a", "x/tmp/b/c", "x/tmpfile"]

        def test_filter(self):
            got = filter_paths(self.RULES, self.PATHS, dirs=["build"])
            self.assertEqual(got, ["main.c", "important.log", "src/main.c", "x/tmpfile"])

        def test_dirs_decide_dir_only_rules(self):
            self.assertEqual(filter_paths("-build/", ["build"], dirs=["build"]), [])
            self.assertEqual(filter_paths("-build/", ["build"]), ["build"])
            self.assertEqual(filter_paths("-build/", ["build", "build/x"], dirs=["build"]), [])
            self.assertEqual(filter_paths("-build/", ["build", "build/x"]), ["build"])

        def test_order_preserved_and_errors(self):
            self.assertEqual(filter_paths("", ["b", "a", "c"]), ["b", "a", "c"])
            self.assertEqual(filter_paths("-a", ["b", "a", "c"]), ["b", "c"])
            with self.assertRaises(ValueError):
                filter_paths("oops", ["a"])
            with self.assertRaises(ValueError):
                filter_paths("-a", ["/abs"])


    if __name__ == "__main__":
        unittest.main()
''')

GR = Lib(
    name="globrules", lang="python", title="the glob and rule-file package (`globrules/`)",
    blurb="The sync tool decides which files to copy with the glob patterns and ordered keep/skip rule files of this package.",
    files={"globrules/__init__.py": GR_INIT, "globrules/glob.py": GR_GLOB, "globrules/rules.py": GR_RULES,
           "README.md": GR_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": GR_VISIBLE},
    hidden_tests={"tests/test_full.py": GR_HIDDEN},
    mutate=["globrules/glob.py", "globrules/rules.py"], difficulty=4, tags=["glob", "paths", "rules"],
    probes=[
        'match_glob("a/**/b", "a/b")',
        'match_glob("a/**", "a")',
        'match_glob("**", "a/b/c")',
        'match_glob("*.{c,h}", "x.h")',
        'match_glob("a[!x]b", "a/b")',
        'match_glob("[a-f]x", "gx")',
        'match_glob("a**b", "a/b")',
        'parse_rules("-/a/b/\\n+ok\\n")',
        'decide(parse_rules("-vendor/\\n+vendor/keep.txt"), "vendor/keep.txt")',
        'decide(parse_rules("-build/"), "build")',
        'decide(parse_rules("-build/"), "build", is_dir=True)',
        'decide(parse_rules("-src/*.tmp"), "x/src/a.tmp")',
        'decide(parse_rules("-*.log\\n+keep.log"), "d/keep.log")',
        'filter_paths("-*.log\\n-tmp/", ["a.log", "tmp/x", "b.txt"], dirs=["tmp"])',
    ],
    probe_import="from globrules import *",
)


LIBS = [NS, FR, SQ, GR]
register_libs(LIBS, n=10)
