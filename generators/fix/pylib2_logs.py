"""Text-format libraries (python), batch: log lines, env-file dialect, query strings."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# lanternlog: the log-line format of the lantern daemons (two modules)
# ======================================================================================================================

LANTERN_README = dd(r'''
    # lanternlog

    Parser, formatter and query helpers for the line format written by the lantern daemons:

        2025-03-14T09:26:53Z WARN pump.3: queue is slow | depth=412 host="gate 7" retry

    ## `lanternlog.parse`

    ### `parse_line(line) -> Entry`
    `Entry` is a `namedtuple` `(ts, level, source, message, fields)`. A trailing `\r\n` is ignored.

    * `ts`: first token, exactly `YYYY-MM-DDTHH:MM:SSZ` (digits only, no calendar validation), kept as a string.
    * `level`: second token, case-insensitive, one of `TRACE DEBUG INFO WARN ERROR FATAL`; `WARNING` is accepted as
      an alias of `WARN`. Stored upper-case in canonical form.
    * `source`: third token. It must end with `:`; without the colon it is one or more dot-separated names made of
      `a-z 0-9 _ -`. Stored without the colon.
    * `message`: the text after the source up to the first ` | ` (space, pipe, space), stripped. Without that
      separator the whole rest of the line is the message and `fields` is `{}`.
    * `fields`: after the separator, whitespace-separated `key=value` items. A value is either a bare run of
      non-space characters or a double-quoted string in which a backslash makes the next character literal
      (`\"`, `\\`); quoted values may contain spaces. An item without `=` is a flag and its value is `True`. When a
      key repeats the last value wins. An unterminated quote is a `ValueError`, as is an empty key.

    Anything that breaks these rules raises `ValueError`. Values read from a line are always `str` (or `True`).

    ### `normalize_level(name) -> str`
    The canonical upper-case level for `name` (alias applied), or `ValueError`.

    ### `format_entry(entry) -> str`
    The inverse of `parse_line`: `<ts> <LEVEL> <source>: <message>`, then, if there are fields, ` | ` and the items
    sorted by key and separated by single spaces. A `True` value is written as the bare key. Other values are written
    as `str(value)`, double-quoted (with `\` and `"` backslash-escaped) when the text is empty or contains whitespace,
    `"`, `\` or `=`. For entries with a non-empty message, `parse_line(format_entry(e)) == e` when all values are
    strings or `True`.

    ## `lanternlog.query`

    ### `select(entries, min_level="TRACE", source=None, since=None, until=None) -> list`
    The entries (original order kept) that satisfy all given conditions:

    * level at least `min_level` (order: TRACE < DEBUG < INFO < WARN < ERROR < FATAL; an unknown level is a `ValueError`);
    * `source` equal to the entry's source or a dotted ancestor of it: `"pump"` matches `pump` and `pump.3`, not `pumps`;
    * `since <= ts` and `ts < until`, comparing timestamp strings (a bound left as `None` is not applied).

    ### `to_seconds(ts) -> int`
    Seconds since the proleptic Gregorian day 1 (`date.toordinal()` of the date times 86400, plus the time of day).
    Only differences between two values are meaningful.

    ### `summarize(entries) -> dict`
    `{"counts": [(level, n), ...], "worst": level or None, "top_source": (source, n) or None}`: counts only for levels
    that occur, in level order; `worst` is the highest level present; `top_source` is the most frequent source, the
    alphabetically first one on a tie.

    ### `bursts(entries, min_level="ERROR", max_gap=60) -> list`
    Looks only at entries with level at least `min_level`, in the order given. Consecutive qualifying entries belong to
    the same burst when the later one is `0..max_gap` seconds (inclusive) after the previous qualifying one. An entry
    earlier than its predecessor starts a new burst. Returns `(first_ts, last_ts, count)` per burst.
''')

LANTERN_PARSE = dd(r'''
    """Parsing and formatting of lantern log lines."""
    import re
    from collections import namedtuple

    LEVELS = ("TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL")
    _ALIASES = {"WARNING": "WARN"}
    _TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
    _SRC = re.compile(r"[a-z0-9_-]+(\.[a-z0-9_-]+)*")

    Entry = namedtuple("Entry", "ts level source message fields")


    def normalize_level(name):
        up = name.upper()
        up = _ALIASES.get(up, up)
        if up not in LEVELS:
            raise ValueError("unknown level: %r" % name)
        return up


    def _parse_fields(text):
        fields = {}
        i, n = 0, len(text)
        while i < n:
            if text[i].isspace():
                i += 1
                continue
            j = i
            while j < n and not text[j].isspace() and text[j] != "=":
                j += 1
            key = text[i:j]
            if not key:
                raise ValueError("empty field name")
            if j < n and text[j] == "=":
                j += 1
                if j < n and text[j] == '"':
                    j += 1
                    buf = []
                    while True:
                        if j >= n:
                            raise ValueError("unterminated quoted value")
                        c = text[j]
                        if c == "\\" and j + 1 < n:
                            buf.append(text[j + 1])
                            j += 2
                        elif c == '"':
                            j += 1
                            break
                        else:
                            buf.append(c)
                            j += 1
                    value = "".join(buf)
                else:
                    k = j
                    while k < n and not text[k].isspace():
                        k += 1
                    value = text[j:k]
                    j = k
            else:
                value = True
            fields[key] = value
            i = j
        return fields


    def parse_line(line):
        parts = line.rstrip("\r\n").split(None, 3)
        if len(parts) < 3:
            raise ValueError("expected timestamp, level and source")
        ts, level, source = parts[0], parts[1], parts[2]
        rest = parts[3] if len(parts) == 4 else ""
        if not _TS.fullmatch(ts):
            raise ValueError("bad timestamp: %r" % ts)
        level = normalize_level(level)
        if not source.endswith(":") or not _SRC.fullmatch(source[:-1]):
            raise ValueError("bad source: %r" % source)
        message, sep, tail = rest.partition(" | ")
        fields = _parse_fields(tail) if sep else {}
        return Entry(ts, level, source[:-1], message.strip(), fields)


    def _quote(value):
        if value is True:
            return None
        s = str(value)
        if s == "" or any(c.isspace() or c in '"\\=' for c in s):
            return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return s


    def format_entry(entry):
        head = "%s %s %s: %s" % (entry.ts, entry.level, entry.source, entry.message)
        if not entry.fields:
            return head
        items = []
        for key in sorted(entry.fields):
            q = _quote(entry.fields[key])
            items.append(key if q is None else key + "=" + q)
        return head + " | " + " ".join(items)
''')

LANTERN_QUERY = dd(r'''
    """Filtering and summarising parsed lantern entries."""
    from datetime import date

    from .parse import LEVELS, normalize_level


    def _rank(level):
        return LEVELS.index(normalize_level(level))


    def select(entries, min_level="TRACE", source=None, since=None, until=None):
        floor = _rank(min_level)
        out = []
        for e in entries:
            if _rank(e.level) < floor:
                continue
            if source is not None and not (e.source == source or e.source.startswith(source + ".")):
                continue
            if since is not None and e.ts < since:
                continue
            if until is not None and e.ts >= until:
                continue
            out.append(e)
        return out


    def to_seconds(ts):
        y, mo, d = int(ts[0:4]), int(ts[5:7]), int(ts[8:10])
        h, mi, s = int(ts[11:13]), int(ts[14:16]), int(ts[17:19])
        return date(y, mo, d).toordinal() * 86400 + h * 3600 + mi * 60 + s


    def summarize(entries):
        counts = {}
        per_source = {}
        for e in entries:
            counts[e.level] = counts.get(e.level, 0) + 1
            per_source[e.source] = per_source.get(e.source, 0) + 1
        by_level = [(lv, counts[lv]) for lv in LEVELS if lv in counts]
        worst = by_level[-1][0] if by_level else None
        top = None
        for src in sorted(per_source):
            if top is None or per_source[src] > top[1]:
                top = (src, per_source[src])
        return {"counts": by_level, "worst": worst, "top_source": top}


    def bursts(entries, min_level="ERROR", max_gap=60):
        floor = _rank(min_level)
        runs = []
        cur = None  # [first_ts, last_ts, count, last_seconds]
        for e in entries:
            if _rank(e.level) < floor:
                continue
            t = to_seconds(e.ts)
            if cur is not None and 0 <= t - cur[3] <= max_gap:
                cur[1] = e.ts
                cur[2] += 1
                cur[3] = t
            else:
                if cur is not None:
                    runs.append((cur[0], cur[1], cur[2]))
                cur = [e.ts, e.ts, 1, t]
        if cur is not None:
            runs.append((cur[0], cur[1], cur[2]))
        return runs
''')

LANTERN_VISIBLE = dd(r'''
    import unittest

    from lanternlog.parse import parse_line
    from lanternlog.query import select


    class BasicTests(unittest.TestCase):
        def test_parse_simple(self):
            e = parse_line("2025-03-14T09:26:53Z WARN pump.3: queue is slow | depth=412 retry")
            self.assertEqual((e.ts, e.level, e.source, e.message), ("2025-03-14T09:26:53Z", "WARN", "pump.3", "queue is slow"))
            self.assertEqual(e.fields, {"depth": "412", "retry": True})

        def test_select_level(self):
            es = [parse_line("2025-03-14T09:26:53Z INFO a: x"), parse_line("2025-03-14T09:26:54Z ERROR a: y")]
            self.assertEqual([e.message for e in select(es, min_level="WARN")], ["y"])


    if __name__ == "__main__":
        unittest.main()
''')

LANTERN_HIDDEN = dd(r'''
    import unittest

    from lanternlog.parse import Entry, format_entry, normalize_level, parse_line
    from lanternlog.query import bursts, select, summarize, to_seconds

    T = "2025-03-14T09:26:53Z"


    def E(ts, level, source, message="m", **fields):
        return Entry(ts, level, source, message, fields)


    class ParseLine(unittest.TestCase):
        def test_plain(self):
            e = parse_line(T + " INFO net: link up")
            self.assertEqual(e, Entry(T, "INFO", "net", "link up", {}))

        def test_trailing_newlines(self):
            self.assertEqual(parse_line(T + " INFO net: link up\r\n").message, "link up")
            self.assertEqual(parse_line(T + " INFO net: link up\n").message, "link up")

        def test_level_case_and_alias(self):
            self.assertEqual(parse_line(T + " warn a: x").level, "WARN")
            self.assertEqual(parse_line(T + " Warning a: x").level, "WARN")
            self.assertEqual(parse_line(T + " fatal a: x").level, "FATAL")
            self.assertEqual(parse_line(T + " trace a: x").level, "TRACE")

        def test_bad_level(self):
            for lv in ("NOTICE", "WARNINGS", "ERR", "", "5"):
                with self.assertRaises(ValueError):
                    parse_line("%s %s a: x" % (T, lv))

        def test_bad_timestamp(self):
            for ts in ("2025-03-14 09:26:53Z", "2025-03-14T09:26:53", "2025-3-14T09:26:53Z", "2025-03-14T09:26:53ZZ",
                       "x2025-03-14T09:26:53Z", "2025-03-14T09:26:5Z"):
                with self.assertRaises(ValueError):
                    parse_line(ts + " INFO a: x")

        def test_bad_source(self):
            for src in ("net", "Net:", "net.:", ".net:", "ne t:", ":", "net..x:", "a/b:"):
                with self.assertRaises(ValueError):
                    parse_line("%s INFO %s x" % (T, src))

        def test_good_sources(self):
            for src in ("a", "pump.3", "x-y_z.9.q-1"):
                self.assertEqual(parse_line("%s INFO %s: x" % (T, src)).source, src)

        def test_too_short(self):
            for line in ("", T, T + " INFO", "   "):
                with self.assertRaises(ValueError):
                    parse_line(line)

        def test_message_may_be_empty_without_fields(self):
            e = parse_line(T + " INFO net:")
            self.assertEqual((e.message, e.fields), ("", {}))

        def test_message_spacing_and_pipes(self):
            e = parse_line(T + " INFO net:   spaced   out   ")
            self.assertEqual(e.message, "spaced   out")
            e = parse_line(T + " INFO net: a|b | c=1")
            self.assertEqual(e.message, "a|b")
            self.assertEqual(e.fields, {"c": "1"})

        def test_fields(self):
            e = parse_line(T + ' WARN p: m | a=1 b="x y" c d=')
            self.assertEqual(e.fields, {"a": "1", "b": "x y", "c": True, "d": ""})

        def test_field_escapes(self):
            e = parse_line(T + r' WARN p: m | a="say \"hi\"" b="back\\slash" c="a=b"')
            self.assertEqual(e.fields, {"a": 'say "hi"', "b": "back\\slash", "c": "a=b"})

        def test_field_bare_value_with_equals(self):
            e = parse_line(T + " WARN p: m | url=a=b")
            self.assertEqual(e.fields, {"url": "a=b"})

        def test_duplicate_key_last_wins(self):
            e = parse_line(T + " WARN p: m | a=1 a=2 a")
            self.assertEqual(e.fields, {"a": True})
            e = parse_line(T + " WARN p: m | a=1 a=2")
            self.assertEqual(e.fields, {"a": "2"})

        def test_field_errors(self):
            with self.assertRaises(ValueError):
                parse_line(T + ' WARN p: m | a="open')
            with self.assertRaises(ValueError):
                parse_line(T + " WARN p: m | =x")
            with self.assertRaises(ValueError):
                parse_line(T + ' WARN p: m | a="ends\\')

        def test_quoted_value_then_more_fields(self):
            e = parse_line(T + ' WARN p: m | a="1 2"   b=3')
            self.assertEqual(e.fields, {"a": "1 2", "b": "3"})


    class NormalizeLevel(unittest.TestCase):
        def test_values(self):
            self.assertEqual(normalize_level("info"), "INFO")
            self.assertEqual(normalize_level("WARNING"), "WARN")
            self.assertEqual(normalize_level("Error"), "ERROR")
            with self.assertRaises(ValueError):
                normalize_level("loud")


    class FormatEntry(unittest.TestCase):
        def test_without_fields(self):
            self.assertEqual(format_entry(E(T, "INFO", "net", "link up")), T + " INFO net: link up")

        def test_fields_sorted_and_quoted(self):
            e = E(T, "WARN", "p", "slow", zeta="1", alpha="two words", flag=True, empty="", eq="a=b", q='say "x"', bs="a\\b")
            self.assertEqual(
                format_entry(e),
                T + ' WARN p: slow | alpha="two words" bs="a\\\\b" empty="" eq="a=b" flag q="say \\"x\\"" zeta=1',
            )

        def test_non_string_values(self):
            self.assertEqual(format_entry(E(T, "INFO", "a", "m", n=42)), T + " INFO a: m | n=42")

        def test_round_trip(self):
            e = E(T, "ERROR", "a.b", "boom", k='v "q" \\ = x', flag=True, e="", plain="ok", tab="a\tb")
            self.assertEqual(parse_line(format_entry(e)), e)


    LOG = [
        E("2025-03-14T09:00:00Z", "INFO", "pump", "a"),
        E("2025-03-14T09:00:10Z", "WARN", "pump.3", "b"),
        E("2025-03-14T09:01:00Z", "ERROR", "pumps", "c"),
        E("2025-03-14T09:01:30Z", "DEBUG", "gate.1", "d"),
        E("2025-03-14T09:02:00Z", "FATAL", "pump.3.x", "e"),
        E("2025-03-14T09:05:00Z", "ERROR", "gate.1", "f"),
    ]


    def msgs(es):
        return [e.message for e in es]


    class Select(unittest.TestCase):
        def test_defaults_keep_everything(self):
            self.assertEqual(select(LOG), LOG)

        def test_min_level(self):
            self.assertEqual(msgs(select(LOG, min_level="WARN")), ["b", "c", "e", "f"])
            self.assertEqual(msgs(select(LOG, min_level="error")), ["c", "e", "f"])
            self.assertEqual(msgs(select(LOG, min_level="FATAL")), ["e"])
            self.assertEqual(msgs(select(LOG, min_level="DEBUG")), msgs(LOG))
            self.assertEqual(msgs(select(LOG, min_level="INFO")), ["a", "b", "c", "e", "f"])
            self.assertEqual(msgs(select(LOG, min_level="WARNING")), ["b", "c", "e", "f"])

        def test_unknown_level(self):
            with self.assertRaises(ValueError):
                select(LOG, min_level="LOUD")

        def test_source_boundaries(self):
            self.assertEqual(msgs(select(LOG, source="pump")), ["a", "b", "e"])
            self.assertEqual(msgs(select(LOG, source="pump.3")), ["b", "e"])
            self.assertEqual(msgs(select(LOG, source="pumps")), ["c"])
            self.assertEqual(msgs(select(LOG, source="gate")), ["d", "f"])
            self.assertEqual(msgs(select(LOG, source="pu")), [])

        def test_time_window_is_half_open(self):
            self.assertEqual(msgs(select(LOG, since="2025-03-14T09:00:10Z", until="2025-03-14T09:02:00Z")), ["b", "c", "d"])
            self.assertEqual(msgs(select(LOG, since="2025-03-14T09:02:00Z")), ["e", "f"])
            self.assertEqual(msgs(select(LOG, until="2025-03-14T09:00:10Z")), ["a"])

        def test_combined(self):
            got = select(LOG, min_level="WARN", source="pump", since="2025-03-14T09:00:05Z", until="2025-03-14T09:02:01Z")
            self.assertEqual(msgs(got), ["b", "e"])

        def test_empty_input(self):
            self.assertEqual(select([], min_level="ERROR"), [])


    class ToSeconds(unittest.TestCase):
        def test_differences(self):
            a = to_seconds("2025-03-14T09:00:00Z")
            self.assertEqual(to_seconds("2025-03-14T09:00:01Z") - a, 1)
            self.assertEqual(to_seconds("2025-03-14T09:01:00Z") - a, 60)
            self.assertEqual(to_seconds("2025-03-14T10:00:00Z") - a, 3600)
            self.assertEqual(to_seconds("2025-03-15T09:00:00Z") - a, 86400)
            self.assertEqual(to_seconds("2025-04-14T09:00:00Z") - a, 31 * 86400)
            self.assertEqual(to_seconds("2026-03-14T09:00:00Z") - a, 365 * 86400)
            self.assertEqual(to_seconds("2024-03-01T00:00:00Z") - to_seconds("2024-02-01T00:00:00Z"), 29 * 86400)
            self.assertEqual(to_seconds("2025-03-14T23:59:59Z") - to_seconds("2025-03-14T00:00:00Z"), 86399)


    class Summarize(unittest.TestCase):
        def test_counts_in_level_order(self):
            s = summarize(LOG)
            self.assertEqual(s["counts"], [("DEBUG", 1), ("INFO", 1), ("WARN", 1), ("ERROR", 2), ("FATAL", 1)])
            self.assertEqual(s["worst"], "FATAL")

        def test_top_source_and_tie(self):
            es = [E(T, "INFO", "b"), E(T, "INFO", "a"), E(T, "INFO", "b"), E(T, "INFO", "a"), E(T, "INFO", "c")]
            self.assertEqual(summarize(es)["top_source"], ("a", 2))
            es.append(E(T, "WARN", "c"))
            es.append(E(T, "WARN", "c"))
            self.assertEqual(summarize(es)["top_source"], ("c", 3))
            self.assertEqual(summarize(es)["worst"], "WARN")

        def test_tie_prefers_alphabetical_not_first_seen(self):
            self.assertEqual(summarize([E(T, "INFO", "a"), E(T, "INFO", "b")])["top_source"], ("a", 1))
            self.assertEqual(summarize([E(T, "INFO", "b"), E(T, "INFO", "a")])["top_source"], ("a", 1))

        def test_empty(self):
            self.assertEqual(summarize([]), {"counts": [], "worst": None, "top_source": None})

        def test_single_level_not_first(self):
            s = summarize([E(T, "ERROR", "x")])
            self.assertEqual(s, {"counts": [("ERROR", 1)], "worst": "ERROR", "top_source": ("x", 1)})


    class Bursts(unittest.TestCase):
        def at(self, hms, level="ERROR"):
            return E("2025-03-14T%sZ" % hms, level, "s")

        def test_gap_inclusive(self):
            es = [self.at("10:00:00"), self.at("10:01:00"), self.at("10:02:01"), self.at("10:02:05")]
            self.assertEqual(
                bursts(es),
                [("2025-03-14T10:00:00Z", "2025-03-14T10:01:00Z", 2), ("2025-03-14T10:02:01Z", "2025-03-14T10:02:05Z", 2)],
            )

        def test_custom_gap(self):
            es = [self.at("10:00:00"), self.at("10:00:05"), self.at("10:00:11")]
            self.assertEqual([b[2] for b in bursts(es, max_gap=5)], [2, 1])
            self.assertEqual([b[2] for b in bursts(es, max_gap=4)], [1, 1, 1])
            self.assertEqual([b[2] for b in bursts(es, max_gap=6)], [3])
            self.assertEqual([b[2] for b in bursts(es, max_gap=0)], [1, 1, 1])

        def test_chain_extends_beyond_gap(self):
            es = [self.at("10:00:00"), self.at("10:00:50"), self.at("10:01:40"), self.at("10:02:30")]
            self.assertEqual(bursts(es), [("2025-03-14T10:00:00Z", "2025-03-14T10:02:30Z", 4)])

        def test_level_filter_skips_low_entries(self):
            es = [self.at("10:00:00"), self.at("10:00:30", "INFO"), self.at("10:01:30")]
            self.assertEqual(bursts(es), [("2025-03-14T10:00:00Z", "2025-03-14T10:00:00Z", 1), ("2025-03-14T10:01:30Z", "2025-03-14T10:01:30Z", 1)])
            self.assertEqual(len(bursts(es, min_level="INFO")), 1)
            self.assertEqual(len(bursts(es, min_level="FATAL")), 0)
            self.assertEqual(len(bursts([self.at("10:00:00", "WARN")], min_level="warning")), 1)

        def test_out_of_order_starts_new_burst(self):
            es = [self.at("10:00:30"), self.at("10:00:10"), self.at("10:00:20")]
            self.assertEqual(
                bursts(es),
                [("2025-03-14T10:00:30Z", "2025-03-14T10:00:30Z", 1), ("2025-03-14T10:00:10Z", "2025-03-14T10:00:20Z", 2)],
            )

        def test_same_second(self):
            es = [self.at("10:00:00"), self.at("10:00:00")]
            self.assertEqual(bursts(es), [("2025-03-14T10:00:00Z", "2025-03-14T10:00:00Z", 2)])

        def test_across_midnight(self):
            es = [E("2025-03-14T23:59:50Z", "ERROR", "s"), E("2025-03-15T00:00:10Z", "ERROR", "s")]
            self.assertEqual(bursts(es), [("2025-03-14T23:59:50Z", "2025-03-15T00:00:10Z", 2)])

        def test_empty(self):
            self.assertEqual(bursts([]), [])


    if __name__ == "__main__":
        unittest.main()
''')

LANTERN = Lib(
    name="lanternlog", lang="python", title="the lantern log toolkit (`lanternlog/`)",
    blurb="Operations tooling uses this package to read and filter the one-line logs of the lantern daemons.",
    files={"lanternlog/__init__.py": "", "lanternlog/parse.py": LANTERN_PARSE, "lanternlog/query.py": LANTERN_QUERY,
           "README.md": LANTERN_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": LANTERN_VISIBLE},
    hidden_tests={"tests/test_full.py": LANTERN_HIDDEN},
    mutate=["lanternlog/parse.py", "lanternlog/query.py"], difficulty=3, tags=["logs", "parsing"],
    probes=[
        'parse_line("2025-03-14T09:26:53Z warning pump.3: slow | a=1 b=\\"x y\\" c").fields',
        'parse_line("2025-03-14T09:26:53Z warning pump.3: slow | a=1 b=\\"x y\\" c").level',
        'format_entry(Entry("2025-03-14T09:26:53Z", "INFO", "a", "m", {"k": "a b", "z": True, "e": ""}))',
        'to_seconds("2025-03-15T09:00:00Z") - to_seconds("2025-03-14T09:00:00Z")',
        'len(select([Entry("2025-03-14T09:00:00Z", "INFO", "pumps", "m", {}), Entry("2025-03-14T09:00:01Z", "INFO", "pump.1", "m", {})], source="pump"))',
        'select([Entry("2025-03-14T09:00:00Z", "INFO", "a", "x", {}), Entry("2025-03-14T09:00:05Z", "INFO", "a", "y", {})], since="2025-03-14T09:00:00Z", until="2025-03-14T09:00:05Z")[-1].message',
        'bursts([Entry("2025-03-14T10:00:00Z", "ERROR", "s", "m", {}), Entry("2025-03-14T10:01:00Z", "ERROR", "s", "m", {})])',
        'summarize([Entry("2025-03-14T10:00:00Z", "ERROR", "s", "m", {}), Entry("2025-03-14T10:01:00Z", "INFO", "t", "m", {})])',
    ],
    probe_import="from lanternlog.parse import *\nfrom lanternlog.query import *",
)

LIBS = [LANTERN]
register_libs(LIBS, n=10)
