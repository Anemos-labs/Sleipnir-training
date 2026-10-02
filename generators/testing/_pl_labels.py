"""Python libraries about identifiers and counters (parametrised)."""
from __future__ import annotations

from fx import dd

from ._engine import TLib
from ._pygold import gold_tests
from ._pl_pricing import STUB_INIT, WHERE_PY  # noqa: F401


def labelcode(rng) -> TLib:
    """Lab sample labels PREFIX-YYMM-SSSS-C with a weighted mod-11 check character."""
    weights = rng.choice([(3, 7, 1), (2, 3, 4, 5), (1, 3, 9), (5, 2, 7)])
    from_right = rng.choice([True, False])
    pmin, pmax = rng.choice([(2, 4), (3, 5), (2, 3)])
    ymin = rng.choice([2010, 2020])
    seq_max = rng.choice([999, 9999])
    width = len(str(seq_max))
    sep = rng.choice(["-", "/"])
    swap_o = rng.choice([True, False])
    ws = ", ".join(str(w) for w in weights)
    digits_walk = "right to left" if from_right else "left to right"
    src = dd(f'''
        """Sample labels of the Stonebridge soil lab: PREFIX{sep}YYMM{sep}SSSS{sep}C."""
        import re

        WEIGHTS = ({ws},)
        PREFIX_MIN, PREFIX_MAX = {pmin}, {pmax}
        YEAR_MIN, YEAR_MAX = {ymin}, 2099
        SEQ_MAX = {seq_max}
        SEP = "{sep}"
        FROM_RIGHT = {from_right}

        _PATTERN = re.compile(r"([A-Z]{{%d,%d}})%s(\\d{{2}})(\\d{{2}})%s(\\d{{%d}})%s([0-9X])" % (PREFIX_MIN, PREFIX_MAX, re.escape(SEP), re.escape(SEP), {width}, re.escape(SEP)))


        class LabelError(ValueError):
            """The label is malformed or its check character is wrong."""


        def check_char(digits):
            """Weighted mod-11 check character of a digit string: each digit is multiplied by the next weight from WEIGHTS
            (cycling), walking the digits right to left when FROM_RIGHT is true and left to right otherwise; the sum mod 11
            is the check character, with 10 written as 'X'."""
            if not digits or not digits.isdigit():
                raise LabelError(f"not a digit string: {{digits!r}}")
            seq = digits[::-1] if FROM_RIGHT else digits
            total = sum(int(d) * WEIGHTS[i % len(WEIGHTS)] for i, d in enumerate(seq))
            r = total % 11
            return "X" if r == 10 else str(r)


        def make_label(prefix, year, month, seq):
            """The label for a sample. prefix: PREFIX_MIN..PREFIX_MAX capital letters; year YEAR_MIN..YEAR_MAX; month 1..12;
            seq 1..SEQ_MAX. Anything else is a LabelError."""
            if not (isinstance(prefix, str) and PREFIX_MIN <= len(prefix) <= PREFIX_MAX and prefix.isascii() and prefix.isalpha() and prefix.isupper()):
                raise LabelError(f"bad prefix: {{prefix!r}}")
            if not YEAR_MIN <= year <= YEAR_MAX:
                raise LabelError(f"bad year: {{year}}")
            if not 1 <= month <= 12:
                raise LabelError(f"bad month: {{month}}")
            if not 1 <= seq <= SEQ_MAX:
                raise LabelError(f"bad sequence number: {{seq}}")
            body = f"{{year % 100:02d}}{{month:02d}}{{seq:0{width}d}}"
            return f"{{prefix}}{{SEP}}{{body[:4]}}{{SEP}}{{body[4:]}}{{SEP}}{{check_char(body)}}"


        def normalize(text):
            """Tidy up a hand-typed label: surrounding blanks removed, upper case, runs of blanks/underscores/dots turned into
            the separator{(" and, inside the digit groups only, the letter O read as 0" if swap_o else "")}."""
            t = re.sub(r"[ _.]+", SEP, text.strip().upper())
            if not t:
                return t
            parts = t.split(SEP)
            if len(parts) == 4:
                parts = [parts[0]] + [{"re.sub('O', '0', p)" if swap_o else "p"} for p in parts[1:3]] + [parts[3]]
            return SEP.join(parts)


        def parse_label(text):
            """Validate a label (after normalize) and return {{"prefix", "year", "month", "seq"}}. LabelError for a wrong
            format, an impossible month or year, or a check character that does not match."""
            m = _PATTERN.fullmatch(normalize(text))
            if not m:
                raise LabelError(f"bad label format: {{text!r}}")
            prefix, yy, mm, seq, check = m.groups()
            year, month = 2000 + int(yy), int(mm)
            if not 1 <= month <= 12 or year < YEAR_MIN:
                raise LabelError(f"bad date in label: {{text!r}}")
            if check_char(yy + mm + seq) != check:
                raise LabelError(f"check character mismatch: {{text!r}}")
            return {{"prefix": prefix, "year": year, "month": month, "seq": int(seq)}}


        def next_seq(labels, prefix, year, month):
            """The next free sequence number for a prefix and month: one more than the highest used by the valid labels in
            `labels` with that prefix, year and month (invalid labels are ignored). 1 when there is none. LabelError when
            SEQ_MAX is used up."""
            highest = 0
            for text in labels:
                try:
                    info = parse_label(text)
                except LabelError:
                    continue
                if (info["prefix"], info["year"], info["month"]) == (prefix, year, month):
                    highest = max(highest, info["seq"])
            if highest >= SEQ_MAX:
                raise LabelError("sequence numbers exhausted")
            return highest + 1


        def batch(prefix, year, month, start, count):
            """`count` (1..500) consecutive labels beginning at sequence number `start`."""
            if not 1 <= count <= 500:
                raise LabelError(f"bad batch size: {{count}}")
            return [make_label(prefix, year, month, start + i) for i in range(count)]
    ''')
    readme = dd(f'''
        # labelcodes

        Sample labels for the Stonebridge soil lab look like `SOIL{sep}2503{sep}{"42".zfill(width)}{sep}7`: a prefix of {pmin}-{pmax} capital
        letters, the year and month (`YYMM`), a {width}-digit sequence number and one check character.

        ## `check_char(digits) -> str`
        Weighted check character of a non-empty digit string. The weights are {ws} and repeat; the digits are walked {digits_walk}
        (the first digit visited gets the first weight). The weighted sum modulo 11 is the check character; a remainder of 10 is
        written `X`. Anything but digits raises `LabelError`.

        ## `make_label(prefix, year, month, seq) -> str`
        Builds a label: `prefix` {pmin}-{pmax} capital ASCII letters, `year` {ymin}..2099, `month` 1..12, `seq` 1..{seq_max} (zero padded to
        {width} digits). The check character covers the 4 digits of year and month plus the sequence digits. Out-of-range or
        wrongly typed arguments raise `LabelError`.

        ## `normalize(text) -> str`
        Tidies a hand-typed label: surrounding blanks are removed, letters are upper-cased, and every run of spaces, underscores
        and dots becomes one `{sep}`.{" Inside the digit groups (the two groups between the separators) the letter `O` is read as the digit `0`." if swap_o else ""}
        Text that does not split into four parts is only upper-cased and cleaned that way.

        ## `parse_label(text) -> dict`
        Normalises, validates and returns `{{"prefix", "year", "month", "seq"}}`. A wrong format, a month outside 1..12, a year before
        {ymin}, or a wrong check character raises `LabelError`.

        ## `next_seq(labels, prefix, year, month) -> int`
        The next free sequence number: one more than the highest used by the valid labels in `labels` that have that prefix, year and
        month (invalid labels are skipped); `1` when there is none; `LabelError` when {seq_max} is already used.

        ## `batch(prefix, year, month, start, count) -> list[str]`
        `count` (1..500) consecutive labels starting at `start`; `LabelError` for a bad count or when a label would be out of range.
    ''')
    files = {"README.md": readme, "labelcodes/__init__.py": '"""Soil lab sample labels."""\n', "labelcodes/labels.py": src, "tests/__init__.py": ""}
    stub = {"tests/test_smoke.py": dd('''
        import unittest

        from labelcodes import labels


        class SmokeTest(unittest.TestCase):
            def test_api_is_there(self):
                self.assertTrue(callable(labels.make_label))
    ''')}
    ns: dict = {}
    exec(src, ns)
    P = "SOIL" if pmin <= 4 <= pmax else "SOI"
    P2 = "AB" if pmin <= 2 <= pmax else "ABC"
    big = seq_max
    steps = [
        ("check_chars", [("eq", f"check_char({d!r})") for d in ("0", "1", "12", "250342", "99999999", "00000001", "10000000", "2503" + "0".zfill(width)[:width - 1] + "1")]
                        + [("raises", "LabelError", "check_char('')"), ("raises", "LabelError", "check_char('12a')"), ("raises", "LabelError", "check_char('1 2')")]),
        ("check_char_x", [("eq", f"check_char({d!r})") for d in _find_x(ns)]),
        ("make_basic", [("eq", f"make_label({P!r}, 2025, 3, 42)"), ("eq", f"make_label({P2!r}, 2031, 12, {big})"), ("eq", f"make_label({P!r}, {ymin}, 1, 1)"),
                        ("eq", f"make_label({P!r}, 2099, 10, 7)")]),
        ("make_errors", [("raises", "LabelError", f"make_label({x}, 2025, 3, 5)") for x in
                         (repr(P[:pmin - 1]), repr(P + "ABCDEFG"[:pmax - len(P) + 1]), repr(P.lower()), repr(P[:-1] + "1"), "None", repr(P[:-1] + "É"))]
                        + [("raises", "LabelError", f"make_label({P!r}, {y}, 3, 5)") for y in (ymin - 1, 2100)]
                        + [("raises", "LabelError", f"make_label({P!r}, 2025, {m}, 5)") for m in (0, 13)]
                        + [("raises", "LabelError", f"make_label({P!r}, 2025, 3, {s})") for s in (0, big + 1, -4)]),
        ("make_boundaries_ok", [("eq", f"make_label('{'A' * pmin}', 2025, 1, 1)"), ("eq", f"make_label('{'Z' * pmax}', 2025, 12, {big})")]),
        ("normalize_basics", [("eq", f"normalize({t!r})") for t in (
            f"  {P.lower()} 2503 {'42'.zfill(width)} 7 ", f"{P}_2503__{'42'.zfill(width)}..7", f"{P}{sep}2503{sep}{'42'.zfill(width)}{sep}7", "", "   ", f"{P.lower()}.2503.{'9'.zfill(width)}.x",
            "just some text", f"{P} 25O3 00O1 5" if swap_o else f"{P} 2503 {'1'.zfill(width)} 5", f"O{P[1:]} 2503 {'3'.zfill(width)} 4", f"{P} 2503 {'3'.zfill(width)} 4 9")]),
        ("parse_roundtrip", [("do", f"lab = make_label({P!r}, 2025, 3, 42)"), ("eq", "parse_label(lab)"), ("eq", f"parse_label(lab.lower())"),
                             ("eq", f"parse_label('  ' + lab.replace({sep!r}, ' ') + '  ')"), ("eq", f"parse_label(make_label({P2!r}, 2099, 12, {big}))")]),
        ("parse_errors", [("raises", "LabelError", "parse_label('')"), ("raises", "LabelError", f"parse_label({P!r} + '-2503-0042')"),
                          ("do", f"good = make_label({P!r}, 2025, 3, 42)"),
                          ("raises", "LabelError", "parse_label(good[:-1] + ('0' if good[-1] != '0' else '1'))"),
                          ("raises", "LabelError", "parse_label(good + '9')"), ("raises", "LabelError", "parse_label('9' + good)"),
                          ("raises", "LabelError", f"parse_label({P.lower()[:pmin - 1]!r} + good[len({P!r}):])"),
                          ("raises", "LabelError", "parse_label(good.replace('2503', '2513'))")]),
        ("parse_bad_month", [("do", f"body = '2513' + '42'.zfill({width})"), ("do", f"fake = {P!r} + {sep!r} + '2513' + {sep!r} + '42'.zfill({width}) + {sep!r} + check_char(body)"),
                             ("raises", "LabelError", "parse_label(fake)"),
                             ("do", f"body0 = '2500' + '42'.zfill({width})"),
                             ("do", f"fake0 = {P!r} + {sep!r} + '2500' + {sep!r} + '42'.zfill({width}) + {sep!r} + check_char(body0)"),
                             ("raises", "LabelError", "parse_label(fake0)")]),
        ("parse_old_year", [("do", f"yy = '{(ymin - 1) % 100:02d}'"), ("do", f"fake = {P!r} + {sep!r} + yy + '06' + {sep!r} + '5'.zfill({width}) + {sep!r} + check_char(yy + '06' + '5'.zfill({width}))"),
                            ("raises", "LabelError", "parse_label(fake)")]),
        ("parse_x_check", [("do", f"xl = make_label({P!r}, 2025, 3, {s})") for s in _find_x_seq(ns, P, width)[:1]]
                          + ([("eq", "parse_label(xl)['seq']"), ("eq", "xl[-1]")] if _find_x_seq(ns, P, width) else [])),
        ("next_seq", [("do", f"labs = [make_label({P!r}, 2025, 3, s) for s in (1, 2, 7)] + [make_label({P2!r}, 2025, 3, 50), make_label({P!r}, 2025, 4, 30), make_label({P!r}, 2024, 3, 40), 'garbage', {P!r} + '-2503-0099-0']"),
                      ("eq", f"next_seq(labs, {P!r}, 2025, 3)"), ("eq", f"next_seq(labs, {P2!r}, 2025, 3)"), ("eq", f"next_seq(labs, {P!r}, 2025, 4)"), ("eq", f"next_seq(labs, {P!r}, 2024, 3)"),
                      ("eq", f"next_seq(labs, {P!r}, 2025, 5)"), ("eq", f"next_seq([], {P!r}, 2025, 3)"), ("eq", f"next_seq([lab.lower() for lab in labs], {P!r}, 2025, 3)")]),
        ("next_seq_exhausted", [("raises", "LabelError", f"next_seq([make_label({P!r}, 2025, 3, {big})], {P!r}, 2025, 3)"), ("eq", f"next_seq([make_label({P!r}, 2025, 3, {big - 1})], {P!r}, 2025, 3)")]),
        ("batch_ok", [("eq", f"batch({P!r}, 2025, 3, 5, 3)"), ("eq", f"len(batch({P!r}, 2025, 3, 1, 500)) if {big} >= 500 else 500"), ("eq", f"batch({P!r}, 2025, 3, {big}, 1)"),
                      ("eq", f"batch({P!r}, 2025, 3, 1, 1)")]),
        ("batch_errors", [("raises", "LabelError", f"batch({P!r}, 2025, 3, 1, 0)"), ("raises", "LabelError", f"batch({P!r}, 2025, 3, 1, 501)"),
                          ("raises", "LabelError", f"batch({P!r}, 2025, 3, {big}, 2)"), ("raises", "LabelError", f"batch({P!r}, 2025, 3, 0, 2)")]),
    ]
    imp = "from labelcodes.labels import *\nfrom labelcodes import labels"
    gold = gold_tests(files, imp, steps, path="tests/test_labels.py", cls="LabelTests")
    rr = [("pattern", [("eq", f"bool(labels._PATTERN.fullmatch(make_label({P!r}, 2025, 3, 42)))"), ("eq", f"labels._PATTERN.fullmatch('{P}{sep}2503{sep}{'42'.zfill(width)}{sep}7') is not None"),
                       ("eq", "labels._PATTERN.groups")]),
          ("messages", [("raisesre", "LabelError", "check_char('')", "not a digit string"), ("raisesre", "LabelError", f"make_label({P.lower()!r}, 2025, 3, 5)", "bad prefix"),
                        ("raisesre", "LabelError", f"make_label({P!r}, 2025, 13, 5)", "bad month: 13"), ("raisesre", "LabelError", f"make_label({P!r}, 2025, 3, 0)", "bad sequence number"),
                        ("raisesre", "LabelError", "parse_label('nonsense')", "bad label format"), ("raisesre", "LabelError", f"batch({P!r}, 2025, 3, 1, 0)", "bad batch size")])]
    internal = gold_tests(files, imp, rr, path="tests/test_internals.py", cls="InternalsTests")
    probes = [f"check_char('250342')", f"make_label({P!r}, 2025, 3, 42)", f"make_label({P!r}, 2025, 12, {big})", f"normalize('  {P.lower()} 2503 {'42'.zfill(width)} 7')",
              f"parse_label(make_label({P!r}, 2025, 3, 42))", f"next_seq([make_label({P!r}, 2025, 3, 7)], {P!r}, 2025, 3)", f"len(batch({P!r}, 2025, 3, 1, 3))"]
    return TLib(
        name="py-labelcodes", lang="python", title="the soil-lab sample label codec", blurb="The lab information system prints and scans sample labels with `labelcodes`.",
        files=files, stub=stub, gold=gold, mutate=["labelcodes/labels.py"], cmd="python3 -m unittest discover -s tests -t .", where=WHERE_PY, difficulty=3,
        probes=probes, probe_import="from labelcodes.labels import *", renames={"_PATTERN": "_LABEL_RE"},
        py_groups=steps, py_imports=imp, internals=internal,
        msg_swaps={"bad prefix": "invalid prefix", "bad sequence number": "sequence number out of range", "bad label format": "unrecognised label", "not a digit string": "digits only", "bad month": "invalid month", "bad batch size": "invalid batch size"},
        focus="the check character (weights, direction, the X case), the ranges accepted by make_label, normalisation, and the next_seq bookkeeping",
    )


def _find_x(ns: dict) -> list[str]:
    out = []
    for n in range(1, 400):
        d = f"{n:04d}"
        if ns["check_char"](d) == "X":
            out.append(d)
        if len(out) >= 2:
            break
    for n in range(9990, 9990 - 400, -1):
        d = f"{n:04d}"
        if ns["check_char"](d) == "X" and d not in out:
            out.append(d)
            break
    return out or ["0"]


def _find_x_seq(ns: dict, prefix: str, width: int) -> list[int]:
    for s in range(1, 10 ** width):
        if ns["check_char"]("2503" + f"{s:0{width}d}") == "X":
            return [s]
    return []
