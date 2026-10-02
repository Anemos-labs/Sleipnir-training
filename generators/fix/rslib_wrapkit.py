"""Text wrapping by display width (rust): wide and zero-width characters, hanging indents, alignment and justification."""
from fx import Lib, dd

from generators.fix._lang1 import CARGO_CONFIG, cargo, register_libs

README = dd('''
    # wrapkit

    Paragraph wrapping for the terminal report renderer. Widths are *display columns*, not bytes or characters: East Asian wide characters take
    two columns and combining marks none.

    ## Widths
    `char_width(c: char) -> usize`:
    * `0` for control characters (`U+0000..=U+001F`, `U+007F..=U+009F`), combining diacritics `U+0300..=U+036F` and zero-width spaces/joiners
      `U+200B..=U+200D`;
    * `2` for the wide ranges `1100-115F`, `2E80-303E`, `3041-33FF`, `3400-4DBF`, `4E00-9FFF`, `A000-A4CF`, `AC00-D7A3`, `F900-FAFF`, `FE30-FE6F`,
      `FF00-FF60`, `FFE0-FFE6`, `1F300-1F64F`, `1F900-1F9FF`, `20000-3FFFD` (hexadecimal code points);
    * `1` for everything else.

    `str_width(s: &str) -> usize` is the sum over its characters.

    ## `wrap(text: &str, opts: &Options) -> Result<Vec<String>, WrapError>`
    ```rust
    pub enum Align { Left, Right, Center, Justify }
    pub struct Options { pub width: usize, pub indent_first: usize, pub indent_rest: usize, pub align: Align }
    ```
    `WrapError::TooNarrow` when `width == 0` or `width <= max(indent_first, indent_rest)` (there must be room for text on every line).

    The text is split at `\\n` into paragraphs. In a paragraph, *words* are the pieces between spaces (only the ASCII space `' '` separates words; tabs, no-break
    spaces and other characters belong to words); runs of spaces collapse and leading/trailing spaces vanish. A paragraph without words produces one
    empty line `""` (no indent) so blank lines survive.

    Lines are filled greedily. The first line of a paragraph has `indent_first` columns of indent and the later lines `indent_rest`; the *room* of a line
    is `width - indent`. A word is added to the current line, after one space, when the line's text width plus 1 plus the word's width is at most the room; otherwise the
    line is closed and the word starts the next one. A word wider than the room of the line it would start is *split*: its characters are added to a
    piece while the piece's width stays within the room of the line the piece goes on (computed for each piece separately), and a piece always gets at
    least one character even if that character alone is too wide. Every piece except the last fills a line on its own; the last piece stays open as the current
    line, so following words can join it.

    ## Alignment
    Each finished line is rendered with its indent as that many leading spaces, then, with `room`, `text` (the words joined by single spaces) and `text_width`:
    * `Left`: `text`;
    * `Right`: `room - text_width` spaces, then `text`; `Center`: `(room - text_width) / 2` spaces (rounded down), then `text`. A line wider than its room counts as
      having no padding;
    * `Justify`: lines with at least two words that are not the last line of their paragraph have the gaps widened so the text is exactly `room` wide: with `extra = room -
      (sum of word widths)` and `gaps = words - 1` every gap gets `extra / gaps` spaces and the first `extra % gaps` gaps one more. The last line of a paragraph, and
      lines of one word, are rendered like `Left`.
    Lines never end with spaces.
''')

SRC = dd('''
    //! Display-width aware text wrapping.

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum Align {
        Left,
        Right,
        Center,
        Justify,
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub struct Options {
        pub width: usize,
        pub indent_first: usize,
        pub indent_rest: usize,
        pub align: Align,
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum WrapError {
        TooNarrow,
    }

    const WIDE: [(u32, u32); 14] = [
        (0x1100, 0x115F),
        (0x2E80, 0x303E),
        (0x3041, 0x33FF),
        (0x3400, 0x4DBF),
        (0x4E00, 0x9FFF),
        (0xA000, 0xA4CF),
        (0xAC00, 0xD7A3),
        (0xF900, 0xFAFF),
        (0xFE30, 0xFE6F),
        (0xFF00, 0xFF60),
        (0xFFE0, 0xFFE6),
        (0x1F300, 0x1F64F),
        (0x1F900, 0x1F9FF),
        (0x20000, 0x3FFFD),
    ];

    pub fn char_width(c: char) -> usize {
        let u = c as u32;
        if u < 0x20 || (0x7F..=0x9F).contains(&u) || (0x0300..=0x036F).contains(&u) || (0x200B..=0x200D).contains(&u) {
            return 0;
        }
        if WIDE.iter().any(|&(lo, hi)| u >= lo && u <= hi) {
            return 2;
        }
        1
    }

    pub fn str_width(s: &str) -> usize {
        s.chars().map(char_width).sum()
    }

    fn render(row: &[String], index: usize, last: bool, opts: &Options) -> String {
        let indent = if index == 0 { opts.indent_first } else { opts.indent_rest };
        let room = opts.width - indent;
        let text = row.join(" ");
        let text_width = str_width(&text);
        let mut line = " ".repeat(indent);
        match opts.align {
            Align::Right => {
                line.push_str(&" ".repeat(room.saturating_sub(text_width)));
                line.push_str(&text);
            }
            Align::Center => {
                line.push_str(&" ".repeat(room.saturating_sub(text_width) / 2));
                line.push_str(&text);
            }
            Align::Justify if !last && row.len() >= 2 => {
                let gaps = row.len() - 1;
                let extra = room.saturating_sub(row.iter().map(|w| str_width(w)).sum::<usize>());
                for (k, word) in row.iter().enumerate() {
                    line.push_str(word);
                    if k < gaps {
                        let spaces = extra / gaps + usize::from(k < extra % gaps);
                        line.push_str(&" ".repeat(spaces));
                    }
                }
            }
            _ => line.push_str(&text),
        }
        line
    }

    pub fn wrap(text: &str, opts: &Options) -> Result<Vec<String>, WrapError> {
        if opts.width == 0 || opts.width <= opts.indent_first.max(opts.indent_rest) {
            return Err(WrapError::TooNarrow);
        }
        let room = |row: usize| opts.width - if row == 0 { opts.indent_first } else { opts.indent_rest };
        let mut lines = Vec::new();
        for paragraph in text.split('\\n') {
            let words: Vec<&str> = paragraph.split(' ').filter(|w| !w.is_empty()).collect();
            if words.is_empty() {
                lines.push(String::new());
                continue;
            }
            let mut rows: Vec<Vec<String>> = Vec::new();
            let mut cur: Vec<String> = Vec::new();
            let mut cur_width = 0usize;
            for word in words {
                let w = str_width(word);
                if !cur.is_empty() && cur_width + 1 + w <= room(rows.len()) {
                    cur.push(word.to_string());
                    cur_width += 1 + w;
                    continue;
                }
                if !cur.is_empty() {
                    rows.push(std::mem::take(&mut cur));
                }
                if w > room(rows.len()) {
                    let mut piece = String::new();
                    let mut piece_width = 0;
                    for ch in word.chars() {
                        let c = char_width(ch);
                        if !piece.is_empty() && piece_width + c > room(rows.len()) {
                            rows.push(vec![std::mem::take(&mut piece)]);
                            piece_width = 0;
                        }
                        piece.push(ch);
                        piece_width += c;
                    }
                    cur = vec![piece];
                    cur_width = piece_width;
                } else {
                    cur = vec![word.to_string()];
                    cur_width = w;
                }
            }
            rows.push(cur);
            let n = rows.len();
            for (i, row) in rows.iter().enumerate() {
                lines.push(render(row, i, i == n - 1, opts));
            }
        }
        Ok(lines)
    }
''')

VISIBLE = dd('''
    use wrapkit::*;

    fn opts(width: usize) -> Options {
        Options { width, indent_first: 0, indent_rest: 0, align: Align::Left }
    }

    #[test]
    fn simple_wrap() {
        let lines = wrap("the quick brown fox", &opts(10)).unwrap();
        assert_eq!(lines, ["the quick", "brown fox"]);
    }

    #[test]
    fn widths() {
        assert_eq!(char_width('a'), 1);
        assert_eq!(char_width('日'), 2);
        assert_eq!(str_width("ab日"), 4);
    }
''')

TABLE = r'''
        ("the quick brown fox jumps over the lazy dog and keeps running far away", 20, 2, 4, Align::Left, &["  the quick brown", "    fox jumps over", "    the lazy dog and", "    keeps running", "    far away"]),
        ("the quick brown fox jumps over the lazy dog and keeps running far away", 16, 0, 0, Align::Left, &["the quick brown", "fox jumps over", "the lazy dog and", "keeps running", "far away"]),
        ("the quick brown fox jumps over the lazy dog and keeps running far away", 20, 2, 4, Align::Right, &["     the quick brown", "      fox jumps over", "    the lazy dog and", "       keeps running", "            far away"]),
        ("the quick brown fox jumps over the lazy dog and keeps running far away", 16, 0, 0, Align::Right, &[" the quick brown", "  fox jumps over", "the lazy dog and", "   keeps running", "        far away"]),
        ("the quick brown fox jumps over the lazy dog and keeps running far away", 20, 2, 4, Align::Center, &["   the quick brown", "     fox jumps over", "    the lazy dog and", "     keeps running", "        far away"]),
        ("the quick brown fox jumps over the lazy dog and keeps running far away", 16, 0, 0, Align::Center, &["the quick brown", " fox jumps over", "the lazy dog and", " keeps running", "    far away"]),
        ("the quick brown fox jumps over the lazy dog and keeps running far away", 20, 2, 4, Align::Justify, &["  the   quick  brown", "    fox  jumps  over", "    the lazy dog and", "    keeps    running", "    far away"]),
        ("the quick brown fox jumps over the lazy dog and keeps running far away", 16, 0, 0, Align::Justify, &["the  quick brown", "fox  jumps  over", "the lazy dog and", "keeps    running", "far away"]),
        ("", 10, 0, 0, Align::Left, &[""]),
        ("   ", 10, 0, 0, Align::Left, &[""]),
        ("a", 10, 0, 0, Align::Left, &["a"]),
        ("hello", 5, 0, 0, Align::Left, &["hello"]),
        ("hello", 4, 0, 0, Align::Left, &["hell", "o"]),
        ("hello world", 5, 0, 0, Align::Left, &["hello", "world"]),
        ("hello world", 11, 0, 0, Align::Left, &["hello world"]),
        ("hello world", 10, 0, 0, Align::Left, &["hello", "world"]),
        ("one\ntwo\n\nthree", 10, 0, 0, Align::Left, &["one", "two", "", "three"]),
        ("x  y   z\n\n  \nlast line here", 6, 0, 0, Align::Left, &["x y z", "", "", "last", "line", "here"]),
        ("  leading and trailing  ", 30, 0, 0, Align::Left, &["leading and trailing"]),
        ("supercalifragilisticexpialidocious is long", 10, 2, 0, Align::Left, &["  supercal", "ifragilist", "icexpialid", "ocious is", "long"]),
        ("supercalifragilisticexpialidocious is long", 10, 0, 3, Align::Left, &["supercalif", "   ragilis", "   ticexpi", "   alidoci", "   ous is", "   long"]),
        ("supercalifragilisticexpialidocious is long", 10, 0, 0, Align::Right, &["supercalif", "ragilistic", "expialidoc", "   ious is", "      long"]),
        ("supercalifragilisticexpialidocious is long", 10, 0, 0, Align::Center, &["supercalif", "ragilistic", "expialidoc", " ious is", "   long"]),
        ("日本語のテキストを折り返す example 日本", 10, 1, 2, Align::Left, &[" 日本語の", "  テキスト", "  を折り返", "  す", "  example", "  日本"]),
        ("日本語 日本語 日本語", 7, 0, 0, Align::Left, &["日本語", "日本語", "日本語"]),
        ("日本語 日本語 日本語", 7, 0, 0, Align::Right, &[" 日本語", " 日本語", " 日本語"]),
        ("日本語 日本語 日本語", 8, 0, 0, Align::Justify, &["日本語", "日本語", "日本語"]),
        ("日本語 ab 日本語 cd", 9, 0, 0, Align::Center, &["日本語 ab", "日本語 cd"]),
        ("日本", 3, 2, 0, Align::Left, &["  日", "本"]),
        ("日本", 1, 0, 0, Align::Left, &["日", "本"]),
        ("e\u{301}ab abc", 4, 0, 0, Align::Left, &["e\u{301}ab", "abc"]),
        ("a\u{200b}b c", 3, 0, 0, Align::Left, &["a\u{200b}b", "c"]),
        ("a b c d e f g h", 3, 0, 0, Align::Justify, &["a b", "c d", "e f", "g h"]),
        ("a b c d e f g h i j", 9, 0, 0, Align::Justify, &["a b c d e", "f g h i j"]),
        ("aa bb cc dd ee ff", 14, 0, 0, Align::Justify, &["aa bb cc dd ee", "ff"]),
        ("aa bb cc dd ee ff", 8, 1, 1, Align::Justify, &[" aa   bb", " cc   dd", " ee ff"]),
        ("one two three four five six seven eight nine ten eleven", 15, 0, 2, Align::Justify, &["one  two  three", "  four five six", "  seven   eight", "  nine      ten", "  eleven"]),
        ("ab cd", 5, 0, 0, Align::Center, &["ab cd"]),
        ("ab cd", 6, 0, 0, Align::Center, &["ab cd"]),
        ("abc", 6, 0, 0, Align::Center, &[" abc"]),
        ("abcd", 7, 1, 0, Align::Center, &["  abcd"]),
        ("abcd", 7, 1, 0, Align::Right, &["   abcd"]),
        ("a b", 20, 3, 3, Align::Right, &["                 a b"]),
        ("tab\tchar and\u{a0}nbsp", 8, 0, 0, Align::Left, &["tab\tchar", "and\u{a0}nbsp"]),
'''.strip("\n")

HIDDEN = dd('''
    use wrapkit::*;

    #[test]
    fn char_width_table() {
        let cases: [(char, usize); 40] = [
            ('a', 1), ('Z', 1), (' ', 1), ('~', 1), ('\\u{7f}', 0), ('\\u{0}', 0), ('\\u{1f}', 0), ('\\u{20}', 1), ('\\t', 0), ('\\n', 0),
            ('\\u{9f}', 0), ('\\u{a0}', 1), ('\\u{a1}', 1), ('é', 1), ('\\u{2ff}', 1), ('\\u{300}', 0), ('\\u{36f}', 0), ('\\u{370}', 1),
            ('\\u{200a}', 1), ('\\u{200b}', 0), ('\\u{200d}', 0), ('\\u{200e}', 1), ('\\u{1100}', 2), ('\\u{115f}', 2), ('\\u{1160}', 1),
            ('日', 2), ('本', 2), ('ひ', 2), ('ー', 2), ('가', 2), ('힣', 2), ('\\u{d7a4}', 1), ('！', 2), ('｡', 1), ('\\u{ff60}', 2),
            ('\\u{ff61}', 1), ('\\u{1f600}', 2), ('\\u{1f64f}', 2), ('\\u{1f650}', 1), ('\\u{20000}', 2),
        ];
        for (c, w) in cases {
            assert_eq!(char_width(c), w, "char_width({:#x})", c as u32);
        }
        assert_eq!(char_width('\\u{3fffd}'), 2);
        assert_eq!(char_width('\\u{3fffe}'), 1);
        assert_eq!(char_width('\\u{2e80}'), 2);
        assert_eq!(char_width('\\u{2e7f}'), 1);
        assert_eq!(char_width('\\u{303e}'), 2);
        assert_eq!(char_width('\\u{303f}'), 1);
        assert_eq!(char_width('\\u{3041}'), 2);
        assert_eq!(char_width('\\u{3040}'), 1);
        assert_eq!(char_width('\\u{33ff}'), 2);
        assert_eq!(char_width('\\u{3400}'), 2);
        assert_eq!(char_width('\\u{4dbf}'), 2);
        assert_eq!(char_width('\\u{4dc0}'), 1);
        assert_eq!(char_width('\\u{9fff}'), 2);
        assert_eq!(char_width('\\u{a000}'), 2);
        assert_eq!(char_width('\\u{a4cf}'), 2);
        assert_eq!(char_width('\\u{a4d0}'), 1);
        assert_eq!(char_width('\\u{f900}'), 2);
        assert_eq!(char_width('\\u{faff}'), 2);
        assert_eq!(char_width('\\u{fb00}'), 1);
        assert_eq!(char_width('\\u{fe30}'), 2);
        assert_eq!(char_width('\\u{fe6f}'), 2);
        assert_eq!(char_width('\\u{fe70}'), 1);
        assert_eq!(char_width('\\u{ffe0}'), 2);
        assert_eq!(char_width('\\u{ffe6}'), 2);
        assert_eq!(char_width('\\u{ffe7}'), 1);
        assert_eq!(char_width('\\u{1f300}'), 2);
        assert_eq!(char_width('\\u{1f2ff}'), 1);
        assert_eq!(char_width('\\u{1f900}'), 2);
        assert_eq!(char_width('\\u{1f9ff}'), 2);
        assert_eq!(char_width('\\u{1fa00}'), 1);
    }

    #[test]
    fn str_width_sums() {
        assert_eq!(str_width(""), 0);
        assert_eq!(str_width("hello"), 5);
        assert_eq!(str_width("日本語"), 6);
        assert_eq!(str_width("a日b"), 4);
        assert_eq!(str_width("e\\u{301}"), 1);
        assert_eq!(str_width("a\\u{200b}b"), 2);
        assert_eq!(str_width("tab\\there"), 7);
    }

    #[test]
    fn too_narrow() {
        let o = |width, indent_first, indent_rest| Options { width, indent_first, indent_rest, align: Align::Left };
        for (w, a, b) in [(0, 0, 0), (3, 3, 0), (3, 0, 4), (5, 5, 5), (2, 0, 2), (4, 9, 1)] {
            assert_eq!(wrap("x", &o(w, a, b)), Err(WrapError::TooNarrow), "{w} {a} {b}");
        }
        assert_eq!(wrap("x", &o(5, 4, 4)).unwrap(), ["    x"]);
        assert_eq!(wrap("x", &o(1, 0, 0)).unwrap(), ["x"]);
        assert_eq!(wrap("x", &o(3, 2, 0)).unwrap(), ["  x"]);
        assert_eq!(wrap("", &o(0, 0, 0)), Err(WrapError::TooNarrow));
    }

    #[test]
    fn wrapping_table() {
        let cases: &[(&str, usize, usize, usize, Align, &[&str])] = &[
''') + TABLE + "\n" + dd('''
        ];
        for (i, &(text, width, indent_first, indent_rest, align, want)) in cases.iter().enumerate() {
            let opts = Options { width, indent_first, indent_rest, align };
            let got = wrap(text, &opts).unwrap();
            assert_eq!(got, want, "case {i}: wrap({text:?}, {opts:?})");
        }
    }

    #[test]
    fn words_survive_and_lines_stay_in_the_room() {
        let text = "pack my box with five dozen liquor jugs 日本語 and a verylongwordthatmustbesplitacrosslines then more";
        for width in [6usize, 7, 10, 13, 20, 40] {
            for align in [Align::Left, Align::Right, Align::Center, Align::Justify] {
                let opts = Options { width, indent_first: 2, indent_rest: 1, align };
                let lines = wrap(text, &opts).unwrap();
                let joined: String = lines.iter().flat_map(|l| l.chars()).filter(|c| *c != ' ').collect();
                let want: String = text.chars().filter(|c| *c != ' ').collect();
                assert_eq!(joined, want, "width {width} {align:?}");
                for (i, l) in lines.iter().enumerate() {
                    assert!(!l.ends_with(' '), "trailing space in {l:?}");
                    let indent = if i == 0 { 2 } else { 1 };
                    assert!(l.starts_with(&" ".repeat(indent)), "indent of {l:?}");
                    assert!(str_width(l) <= width, "line {l:?} is wider than {width}");
                }
            }
        }
    }

    #[test]
    fn justified_lines_fill_the_room() {
        let opts = Options { width: 30, indent_first: 3, indent_rest: 0, align: Align::Justify };
        let lines = wrap("lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore", &opts).unwrap();
        for (i, l) in lines.iter().enumerate() {
            if i + 1 < lines.len() {
                assert_eq!(str_width(l), 30, "line {i}: {l:?}");
            }
        }
        assert!(str_width(lines.last().unwrap()) < 30);
        assert!(!lines.last().unwrap().contains("  "));
    }

    #[test]
    fn paragraphs_are_independent() {
        let opts = Options { width: 8, indent_first: 2, indent_rest: 0, align: Align::Justify };
        let lines = wrap("aa bb cc dd\\nee ff gg hh\\n\\nii", &opts).unwrap();
        assert_eq!(lines, ["  aa  bb", "cc dd", "  ee  ff", "gg hh", "", "  ii"]);
    }

    #[test]
    fn a_trailing_newline_gives_a_trailing_blank_line() {
        let o = Options { width: 10, indent_first: 0, indent_rest: 0, align: Align::Left };
        assert_eq!(wrap("abc\\n", &o).unwrap(), ["abc", ""]);
        assert_eq!(wrap("\\n", &o).unwrap(), ["", ""]);
        assert_eq!(wrap("\\nabc", &o).unwrap(), ["", "abc"]);
    }
''')

LIB = Lib(
    name="wrapkit", lang="rust", title="the wrapkit crate",
    blurb="The terminal report renderer wraps and aligns paragraphs with wrapkit, which measures text in display columns so wide characters line up.",
    files={"Cargo.toml": cargo("wrapkit"), "src/lib.rs": SRC, "README.md": README, ".gitignore": "target/\n", ".cargo/config.toml": CARGO_CONFIG},
    visible_tests={"tests/basic.rs": VISIBLE},
    hidden_tests={"tests/full.rs": HIDDEN},
    mutate=["src/lib.rs"], difficulty=3, tags=["text", "unicode", "layout"],
)

register_libs([LIB], n=8)
