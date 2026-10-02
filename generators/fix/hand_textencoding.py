"""Text encodings, byte versus character counts: a decoding toolkit (python) and character-aware helpers (rust)."""
import re

from fx import dd, family, langs
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): textio, bytes in, text out.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # textio

    Input hygiene for a log shipper and a CSV importer. Files come from many systems (Windows, old Macs, Excel exports).

    * `decode_bytes(raw)`: a UTF-8 byte order mark is dropped; a UTF-16 byte order mark (either endianness) means the
      data is UTF-16 (the mark is dropped); otherwise the bytes are UTF-8 if they are valid UTF-8 and Latin-1 if not (every
      byte then is the character with the same code point). Returns `str`; empty input gives `""`.
    * `normalize_newlines(text)`: every CRLF and every lone CR becomes a single LF (`"a\\r\\n\\r\\nb"` has exactly one blank line).
    * `truncate_bytes(text, limit)`: the longest prefix of `text` whose UTF-8 encoding is at most `limit` bytes. It never
      contains half a character or a replacement character. A negative limit is a `ValueError`.
    * `csv_rows(raw)`: `decode_bytes` then `csv` parsing; the first non-empty row is the header (names stripped of
      surrounding spaces); empty lines are skipped; returns a list of dicts. Newlines **inside quoted fields are kept exactly
      as they are in the file** (a CRLF stays a CRLF); no newline normalisation happens in the CSV path.
''')

A_TEXTIO = dd('''
    import codecs
    import csv
    import io


    def decode_bytes(raw):
        if raw.startswith(codecs.BOM_UTF8):
            return raw[len(codecs.BOM_UTF8):].decode("utf-8")
        if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            return raw.decode("utf-16")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1")


    def normalize_newlines(text):
        return text.replace("\\r\\n", "\\n").replace("\\r", "\\n")


    def truncate_bytes(text, limit):
        if limit < 0:
            raise ValueError("limit must not be negative")
        data = text.encode("utf-8")
        if len(data) <= limit:
            return text
        return data[:limit].decode("utf-8", errors="ignore")


    def csv_rows(raw):
        text = decode_bytes(raw)
        rows = [r for r in csv.reader(io.StringIO(text, newline="")) if r]
        if not rows:
            return []
        header = [h.strip() for h in rows[0]]
        return [dict(zip(header, r)) for r in rows[1:]]
''')

A_VISIBLE = {
    "tests/test_textio.py": dd('''
        import unittest

        from textio.textio import csv_rows, decode_bytes, normalize_newlines, truncate_bytes


        class Basics(unittest.TestCase):
            def test_decode_plain(self):
                self.assertEqual(decode_bytes("caf\\u00e9".encode("utf-8")), "caf\\u00e9")

            def test_newlines(self):
                self.assertEqual(normalize_newlines("a\\r\\nb\\nc"), "a\\nb\\nc")

            def test_truncate_ascii(self):
                self.assertEqual(truncate_bytes("hello", 3), "hel")

            def test_csv(self):
                self.assertEqual(csv_rows(b"id,name\\n1,Ann\\n"), [{"id": "1", "name": "Ann"}])


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_textio.py": dd('''
        import codecs
        import unittest

        from textio.textio import csv_rows, decode_bytes, normalize_newlines, truncate_bytes


        class Decoding(unittest.TestCase):
            def test_utf8_with_and_without_a_mark(self):
                self.assertEqual(decode_bytes("caf\\u00e9".encode("utf-8")), "caf\\u00e9")
                self.assertEqual(decode_bytes(codecs.BOM_UTF8 + "caf\\u00e9".encode("utf-8")), "caf\\u00e9")
                self.assertEqual(decode_bytes(codecs.BOM_UTF8), "")

            def test_utf16_with_a_mark(self):
                self.assertEqual(decode_bytes("h\\u00e9llo".encode("utf-16")), "h\\u00e9llo")
                self.assertEqual(decode_bytes(codecs.BOM_UTF16_BE + "h\\u00e9llo".encode("utf-16-be")), "h\\u00e9llo")
                self.assertEqual(decode_bytes(codecs.BOM_UTF16_LE + "\\u65e5\\u672c".encode("utf-16-le")), "\\u65e5\\u672c")

            def test_invalid_utf8_is_latin1(self):
                self.assertEqual(decode_bytes(b"caf\\xe9"), "caf\\u00e9")
                self.assertEqual(decode_bytes(b"\\xff\\xfe\\x41"[:1] + b"A"), "\\u00ffA")

            def test_valid_utf8_is_never_read_as_latin1(self):
                self.assertEqual(decode_bytes("na\\u00efve \\u2013 \\u65e5\\u672c".encode("utf-8")), "na\\u00efve \\u2013 \\u65e5\\u672c")

            def test_empty(self):
                self.assertEqual(decode_bytes(b""), "")


        class Newlines(unittest.TestCase):
            def test_all_three_kinds(self):
                self.assertEqual(normalize_newlines("a\\r\\nb\\rc\\nd"), "a\\nb\\nc\\nd")
                self.assertEqual(normalize_newlines("x\\r\\n\\r\\ny"), "x\\n\\ny")
                self.assertEqual(normalize_newlines("\\r\\r\\n"), "\\n\\n")
                self.assertEqual(normalize_newlines("one line"), "one line")
                self.assertEqual(normalize_newlines(""), "")
                self.assertEqual(normalize_newlines("end\\r"), "end\\n")


        class Truncation(unittest.TestCase):
            def test_ascii_and_fitting(self):
                self.assertEqual(truncate_bytes("hello", 10), "hello")
                self.assertEqual(truncate_bytes("hello", 5), "hello")
                self.assertEqual(truncate_bytes("hello", 3), "hel")
                self.assertEqual(truncate_bytes("abc", 0), "")

            def test_never_splits_a_character(self):
                self.assertEqual(truncate_bytes("h\\u00e9llo", 2), "h")
                self.assertEqual(truncate_bytes("h\\u00e9llo", 3), "h\\u00e9")
                self.assertEqual(truncate_bytes("\\u65e5\\u672c\\u8a9e", 7), "\\u65e5\\u672c")
                self.assertEqual(truncate_bytes("\\u65e5\\u672c\\u8a9e", 2), "")
                self.assertEqual(truncate_bytes("\\U0001f600\\U0001f600", 5), "\\U0001f600")

            def test_no_replacement_characters_and_size_bound(self):
                text = "a\\u00e9\\u65e5\\U0001f600" * 5
                for limit in range(0, len(text.encode("utf-8")) + 2):
                    out = truncate_bytes(text, limit)
                    self.assertNotIn("\\ufffd", out)
                    self.assertLessEqual(len(out.encode("utf-8")), limit)
                    self.assertTrue(text.startswith(out))

            def test_negative(self):
                with self.assertRaises(ValueError):
                    truncate_bytes("x", -1)


        class Csv(unittest.TestCase):
            def test_excel_style_export(self):
                raw = codecs.BOM_UTF8 + b'id,name,note\\r\\n1,Ann,"line1\\r\\nline2"\\r\\n\\r\\n2,"Bob, Jr.",plain\\r\\n'
                self.assertEqual(csv_rows(raw), [
                    {"id": "1", "name": "Ann", "note": "line1\\r\\nline2"},
                    {"id": "2", "name": "Bob, Jr.", "note": "plain"},
                ])

            def test_bom_does_not_end_up_in_the_first_header(self):
                rows = csv_rows(codecs.BOM_UTF8 + b"id,name\\n7,x\\n")
                self.assertEqual(list(rows[0]), ["id", "name"])

            def test_quoted_newlines_are_kept_verbatim(self):
                self.assertEqual(csv_rows(b'a,b\\n1,"x\\ry\\nz\\r\\nw"\\n'), [{"a": "1", "b": "x\\ry\\nz\\r\\nw"}])

            def test_headers_are_stripped_and_encodings_follow_decode_bytes(self):
                self.assertEqual(csv_rows(b"id , name\\n1,x\\n"), [{"id": "1", "name": "x"}])
                self.assertEqual(csv_rows(b"name\\ncaf\\xe9\\n"), [{"name": "caf\\u00e9"}])
                self.assertEqual(csv_rows("name\\r\\nzo\\u00eb\\r\\n".encode("utf-16")), [{"name": "zo\\u00eb"}])

            def test_empty_and_header_only(self):
                self.assertEqual(csv_rows(b""), [])
                self.assertEqual(csv_rows(b"id,name\\n"), [])
                self.assertEqual(csv_rows(b"\\n\\nid\\n5\\n"), [{"id": "5"}])


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["bom"] = lambda c: (
        "Customers who export their data from Excel as \"CSV UTF-8\" get an import error saying there is no `id` column. The header "
        "row looks fine in a text editor. A hex dump shows the file starts with EF BB BF. Here is what we parse:\n\n```\n"
        + c.probe("from textio.textio import csv_rows\nprint(list(csv_rows(b'\\xef\\xbb\\xbfid,name\\n1,Ann\\n')[0]))\n")[1]
        + "\n```\nIt should be `['id', 'name']`."
    )
    p["lone-cr"] = (
        "Log lines from the old Mac-based print server arrive glued together: the file uses a bare CR as line terminator and "
        "our normaliser leaves it alone, so the whole file is one giant line. Windows CRLF files are fine."
    )
    p["latin1-first"] = (
        "Everything non-ASCII turns into mojibake since the decoder refactor: \"café\" saved as UTF-8 is read as \"cafÃ©\". Files that really are "
        "Latin-1 are fine. The README says valid UTF-8 must be read as UTF-8."
    )
    p["truncate-replace"] = (
        "Preview strings cut to a byte budget sometimes end with a diamond question mark (U+FFFD) when the cut falls inside "
        "an accented letter or a Japanese character. The preview should simply stop before the character that does not fit."
    )
    p["cr-order"] = (
        "Windows log files now show a blank line between every two lines after we \"cleaned up\" the newline normaliser. Unix files "
        "and old-Mac files are fine. `normalize_newlines` is the only suspect."
    )
    p["csv-newlines"] = (
        "Multi-line addresses in imported CSV files lose their Windows line endings: a cell that is `line1<CR><LF>line2` in "
        "the file arrives as `line1<LF>line2`. Our downstream signature check hashes the exact text of cells and now rejects them. "
        "The README says the CSV path must not normalise newlines."
    )
    p["bom-csv"] = (
        "Two problems with files coming from Excel: the first column cannot be found (`id` is not in the header, the hex dump shows "
        "EF BB BF at the start), and cells with line breaks come out with different line endings than in the file. Both worked "
        "before the last import refactor. Please fix everything that breaks the CSV import of such files."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "textio/__init__.py": '"""Input hygiene."""\n', "textio/textio.py": A_TEXTIO}
    t = "textio/textio.py"
    bom = ('    if raw.startswith(codecs.BOM_UTF8):\n        return raw[len(codecs.BOM_UTF8):].decode("utf-8")\n', "")
    csvn = ("    text = decode_bytes(raw)\n    rows", "    text = normalize_newlines(decode_bytes(raw))\n    rows")
    bugs = [
        Bug("utf8-bom-kept", 1, {t: [bom]}, P["bom"]),
        Bug("bare-cr-left-alone", 1, {t: [('    return text.replace("\\r\\n", "\\n").replace("\\r", "\\n")\n', '    return text.replace("\\r\\n", "\\n")\n')]}, P["lone-cr"]),
        Bug("latin1-tried-first", 3, {t: [('    try:\n        return raw.decode("utf-8")\n    except UnicodeDecodeError:\n        return raw.decode("latin-1")\n', '    return raw.decode("latin-1")\n')]}, P["latin1-first"]),
        Bug("truncate-leaves-replacement", 3, {t: [('errors="ignore"', 'errors="replace"')]}, P["truncate-replace"]),
        Bug("cr-replaced-before-crlf", 3, {t: [('    return text.replace("\\r\\n", "\\n").replace("\\r", "\\n")\n', '    return text.replace("\\r", "\\n").replace("\\r\\n", "\\n")\n')]}, P["cr-order"]),
        Bug("csv-normalises-cells", 4, {t: [csvn]}, P["csv-newlines"]),
        Bug("bom-and-csv-newlines", 5, {t: [bom, csvn]}, P["bom-csv"]),
    ]
    return Base("textio", "python", good, A_VISIBLE, A_HIDDEN, bugs)


def _panic_lines(out: str) -> str:
    """The `thread ... panicked at` line (without the thread id) and the message after it."""
    lines = out.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("thread "):
            first = re.sub(r" \(\d+\)", "", ln)
            return "\n".join([first] + lines[i + 1:i + 2])
    return "\n".join(lines[-3:])


# ------------------------------------------------------------------------------------------------------------------
# Base B (rust): snip, character-aware string helpers.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # snip

    Character-aware text helpers for a terminal UI (Rust, no dependencies). Everything counts **characters** (Unicode scalar
    values), never bytes.

    * `shorten(s, max)`: `s` itself when it has at most `max` characters, otherwise its first `max - 1` characters followed by
      `'…'` (so the result has exactly `max` characters). `max == 0` gives the empty string.
    * `initials(name)`: the upper-case first character of every whitespace-separated word, in order.
    * `find_char_index(hay, needle)`: the index, in characters, of the first occurrence of `needle` in `hay`.
    * `pad_center(s, width)`: `s` centred in `width` characters with spaces; when the space cannot be split evenly the extra
      space goes to the right; text that is already `width` characters or longer is returned unchanged.
    * `split_chars(s, idx)`: `(first idx characters, the rest)`; an `idx` past the end gives `(s, "")`.
''')

B_LIB = dd('''
    //! Character-aware text helpers.

    /// At most `max` characters: the text itself if it fits, otherwise its first `max - 1` characters and an ellipsis.
    pub fn shorten(s: &str, max: usize) -> String {
        if max == 0 {
            return String::new();
        }
        if s.chars().count() <= max {
            return s.to_string();
        }
        let mut out: String = s.chars().take(max - 1).collect();
        out.push('\\u{2026}');
        out
    }

    /// Upper-case first character of every whitespace-separated word.
    pub fn initials(name: &str) -> String {
        name.split_whitespace()
            .filter_map(|w| w.chars().next())
            .flat_map(|c| c.to_uppercase())
            .collect()
    }

    /// Index, in characters, of the first occurrence of `needle` in `hay`.
    pub fn find_char_index(hay: &str, needle: &str) -> Option<usize> {
        let byte = hay.find(needle)?;
        Some(hay[..byte].chars().count())
    }

    /// Centre `s` in `width` characters; extra space goes to the right.
    pub fn pad_center(s: &str, width: usize) -> String {
        let n = s.chars().count();
        if n >= width {
            return s.to_string();
        }
        let total = width - n;
        let left = total / 2;
        format!("{}{}{}", " ".repeat(left), s, " ".repeat(total - left))
    }

    /// Split after the first `idx` characters.
    pub fn split_chars(s: &str, idx: usize) -> (&str, &str) {
        match s.char_indices().nth(idx) {
            Some((byte, _)) => s.split_at(byte),
            None => (s, ""),
        }
    }
''')

B_VISIBLE = {
    "tests/basic.rs": dd('''
        use snip::*;

        #[test]
        fn shorten_ascii() {
            assert_eq!(shorten("hello world", 6), "hello\\u{2026}");
            assert_eq!(shorten("hi", 6), "hi");
        }

        #[test]
        fn initials_ascii() {
            assert_eq!(initials("ada lovelace"), "AL");
        }

        #[test]
        fn pad_and_split_ascii() {
            assert_eq!(pad_center("ab", 5), " ab  ");
            assert_eq!(split_chars("hello", 2), ("he", "llo"));
            assert_eq!(find_char_index("hello", "ll"), Some(2));
        }
    '''),
}

B_HIDDEN = {
    "tests/hidden_snip.rs": dd('''
        use snip::*;

        #[test]
        fn shorten_counts_characters_not_bytes() {
            assert_eq!(shorten("h\\u{e9}llo", 5), "h\\u{e9}llo");
            assert_eq!(shorten("h\\u{e9}llo w\\u{f6}rld", 6), "h\\u{e9}llo\\u{2026}");
            assert_eq!(shorten("\\u{65e5}\\u{672c}\\u{8a9e}\\u{306e}\\u{30c6}\\u{30ad}\\u{30b9}\\u{30c8}", 4), "\\u{65e5}\\u{672c}\\u{8a9e}\\u{2026}");
            assert_eq!(shorten("\\u{65e5}\\u{672c}\\u{8a9e}", 3), "\\u{65e5}\\u{672c}\\u{8a9e}");
            assert_eq!(shorten("\\u{1f600}\\u{1f600}\\u{1f600}\\u{1f600}", 3), "\\u{1f600}\\u{1f600}\\u{2026}");
            assert_eq!(shorten("abcdef", 1), "\\u{2026}");
            assert_eq!(shorten("abcdef", 0), "");
            assert_eq!(shorten("", 3), "");
            assert_eq!(shorten("abc", 3), "abc");
        }

        #[test]
        fn shorten_result_has_at_most_max_characters() {
            let text = "a\\u{e9}\\u{65e5}\\u{1f600}b\\u{f1}c";
            for max in 0..12 {
                assert!(shorten(text, max).chars().count() <= max, "max {}", max);
            }
        }

        #[test]
        fn initials_use_characters() {
            assert_eq!(initials("ada lovelace"), "AL");
            assert_eq!(initials("\\u{e9}mile zola"), "\\u{c9}Z");
            assert_eq!(initials("  \\u{f1}and\\u{fa}   p\\u{e9}rez  "), "\\u{d1}P");
            assert_eq!(initials("\\u{65e5}\\u{672c} \\u{8a9e}"), "\\u{65e5}\\u{8a9e}");
            assert_eq!(initials(""), "");
            assert_eq!(initials("   "), "");
        }

        #[test]
        fn find_returns_a_character_index() {
            assert_eq!(find_char_index("hello", "ll"), Some(2));
            assert_eq!(find_char_index("h\\u{e9}llo w\\u{f6}rld", "w\\u{f6}r"), Some(6));
            assert_eq!(find_char_index("\\u{65e5}\\u{672c}\\u{8a9e}", "\\u{8a9e}"), Some(2));
            assert_eq!(find_char_index("abc", "z"), None);
            assert_eq!(find_char_index("abc", ""), Some(0));
        }

        #[test]
        fn pad_center_counts_characters() {
            assert_eq!(pad_center("ab", 5), " ab  ");
            assert_eq!(pad_center("\\u{e9}", 4), " \\u{e9}  ");
            assert_eq!(pad_center("\\u{65e5}\\u{672c}", 5), " \\u{65e5}\\u{672c}  ");
            assert_eq!(pad_center("abcd", 4), "abcd");
            assert_eq!(pad_center("\\u{65e5}\\u{672c}\\u{8a9e}", 2), "\\u{65e5}\\u{672c}\\u{8a9e}");
            assert_eq!(pad_center("", 3), "   ");
        }

        #[test]
        fn split_chars_works_on_characters() {
            assert_eq!(split_chars("hello", 2), ("he", "llo"));
            assert_eq!(split_chars("h\\u{e9}llo", 2), ("h\\u{e9}", "llo"));
            assert_eq!(split_chars("\\u{65e5}\\u{672c}\\u{8a9e}", 1), ("\\u{65e5}", "\\u{672c}\\u{8a9e}"));
            assert_eq!(split_chars("\\u{65e5}\\u{672c}\\u{8a9e}", 3), ("\\u{65e5}\\u{672c}\\u{8a9e}", ""));
            assert_eq!(split_chars("abc", 0), ("", "abc"));
            assert_eq!(split_chars("abc", 10), ("abc", ""));
        }
    '''),
}


def _b_prompts():
    p = {}
    p["shorten-len"] = (
        "Titles with accents are shortened although they fit: \"h\u00e9llo\" with a limit of 5 characters comes back as \"h\u00e9ll\u2026\", the "
        "UI treats 'limit' as characters everywhere else. ASCII titles behave. `shorten` in `src/lib.rs`."
    )
    p["shorten-slice"] = lambda c: (
        "The status bar panics when it shortens a long title that contains non-ASCII text. A minimal test that I wrote shows "
        "(trimmed):\n\n```\n"
        + _panic_lines(c.bad_run("use snip::shorten;\n\n#[test]\nfn status_bar_title() {\n    assert_eq!(shorten(\"w\\u{f6}rld wide\", 3), \"w\\u{f6}\\u{2026}\");\n}\n",
                                 cmd="cargo test --offline --quiet --test probe 2>&1", name="tests/probe.rs"))
        + "\n```\n\nASCII titles are fine. Please fix `shorten` so that it counts and cuts characters."
    )
    p["initials-byte"] = (
        "The avatar badge shows \"\u00c3Z\" for \"\u00e9mile zola\" and a garbage character for names starting with \u00f1 or Japanese "
        "characters. The initials should be the upper-case first *character* of each word."
    )
    p["find-byte"] = (
        "The highlighter in the terminal UI is shifted to the right by one column per accented letter in front of the match: "
        "searching \"w\u00f6r\" in \"h\u00e9llo w\u00f6rld\" reports position 7, but the match starts at character index 6. "
        "The function is documented to return a character index."
    )
    p["pad-bytes"] = (
        "Centered column headings with accents or CJK characters are visibly off-centre: \"\u00e9\" in a 4 wide cell gets one space too "
        "few on the right. It looks like the padding is computed from the byte length."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "Cargo.toml": langs.cargo_toml("snip"), "src/lib.rs": B_LIB}
    lib = "src/lib.rs"
    bugs = [
        Bug("shorten-compares-bytes", 2, {lib: [("    if s.chars().count() <= max {\n", "    if s.len() <= max {\n")]}, P["shorten-len"]),
        Bug("pad-center-by-bytes", 2, {lib: [("    let n = s.chars().count();\n    if n >= width {", "    let n = s.len();\n    if n >= width {")]}, P["pad-bytes"]),
        Bug("shorten-slices-bytes", 3, {lib: [("    let mut out: String = s.chars().take(max - 1).collect();\n    out.push('\\u{2026}');\n    out\n",
                                               "    let mut out = s[..max - 1].to_string();\n    out.push('\\u{2026}');\n    out\n")]}, P["shorten-slice"]),
        Bug("initials-first-byte", 3, {lib: [("        .filter_map(|w| w.chars().next())\n        .flat_map(|c| c.to_uppercase())\n        .collect()\n",
                                              "        .filter_map(|w| w.as_bytes().first().map(|b| (*b as char).to_ascii_uppercase()))\n        .collect()\n")]}, P["initials-byte"]),
        Bug("find-returns-byte-offset", 3, {lib: [("    let byte = hay.find(needle)?;\n    Some(hay[..byte].chars().count())\n", "    hay.find(needle)\n")]}, P["find-byte"]),
    ]
    return Base("snip", "rust", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-text-encoding", category="fix", lang="python", kind="fix", n=12,
        summary="text encodings and byte-versus-character counts: decoding toolkit (python), character-aware helpers (rust)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
