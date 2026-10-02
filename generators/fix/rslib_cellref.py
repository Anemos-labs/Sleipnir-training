"""Spreadsheet cell references (rust): A1 notation, ranges, anchors, and shifting formulas when they are copied."""
from fx import Lib, dd

from generators.fix._lang1 import CARGO_CONFIG, cargo, register_libs

README = dd('''
    # cellref

    A1-style cell references for the report builder's formula engine: parsing, printing, ranges, and rewriting the
    references inside a formula when it is copied to another cell.

    Columns are `A..Z, AA..AZ, BA...` (bijective base 26, `A` is 1), at most `ZZZ` = 18278 (`MAX_COL`); rows start at 1
    and stop at 1 048 576 (`MAX_ROW`). A reference may carry `$` anchors: `$B$2`, `$B2`, `B$2`.

    ## Columns
    * `col_name(col: u32) -> Option<String>`: `1 -> "A"`, `26 -> "Z"`, `27 -> "AA"`, `702 -> "ZZ"`, `703 -> "AAA"`.
      `None` for 0 and for anything above `MAX_COL`.
    * `col_index(name: &str) -> Option<u32>`: the inverse; case-insensitive; 1 to 3 ASCII letters, otherwise `None`.

    ## `CellRef` and `parse_cell`
    `CellRef { col: u32, row: u32, abs_col: bool, abs_row: bool }`. `parse_cell(s) -> Result<CellRef, RefError>`
    reads `[$]letters[$]digits`, letters in either case. The whole string must be used. Errors (`RefError`), checked in
    this order of appearance in the text:

    * `Empty`: the string is empty;
    * `BadColumn`: no letters after the optional `$`, or more than three of them;
    * `BadRow`: no digits, or the digits start with `0` (so `A0` and `A01` are rejected);
    * `OutOfRange`: the row is above `MAX_ROW` (including numbers too large for a `u32`);
    * `Trailing`: something follows the reference (`A1B`, `A1 `).

    `Display` prints it normalised in upper case, with its anchors: `$AB7`, `c$3`-style input prints as `C$3`.

    ## `RangeRef`
    `RangeRef { from: CellRef, to: CellRef }`, always normalised so `from` is the top-left and `to` the bottom-right
    corner. `RangeRef::new(a, b)` takes any two corners; the column (with its `$` flag) comes from whichever cell has the
    smaller column (from `a` when they are equal), and likewise the row with its flag (from `a` when equal). `parse_range("B2:D4")` accepts two cells joined by one `:`, or
    a single cell (a 1x1 range); other text gives the error of the cell that failed to parse (`"A1:B2:C3"` is `Trailing`).

    * `Display` is `from:to`, or just the cell when the range is a single cell.
    * `width()` and `height()` are the numbers of columns and rows (`u32`), `len()` the number of cells (`u64`).
    * `contains(&CellRef)` ignores anchors.
    * `intersect(&RangeRef) -> Option<RangeRef>`: the overlapping rectangle (corners without anchors), `None` when the
      ranges share no cell (touching edges do not count, sharing a corner cell does).
    * `cells() -> Vec<CellRef>`: every cell in row-major order (left to right, then top to bottom), without anchors.

    ## Shifting
    `shift(&CellRef, drow: i64, dcol: i64) -> Option<CellRef>` moves a reference like copy-paste does: an anchored
    row or column does not move. `None` when the result would leave the sheet (`col < 1`, `col > MAX_COL`, `row < 1`,
    `row > MAX_ROW`).

    `shift_formula(formula: &str, drow: i64, dcol: i64) -> String` rewrites every cell reference inside a formula. A
    *word* is a maximal run of ASCII letters, digits and `$ _ .`. A word is rewritten (and printed normalised, so `a1`
    becomes `A2`) when

    * it parses as a cell with `parse_cell`, and
    * the character right after it is not `(` (so `LOG10(x)` is a function call, not a cell), and
    * it is not inside a double-quoted string literal (a doubled `""` inside a literal is an escaped quote; an unterminated
      literal runs to the end of the text).

    A reference that would leave the sheet is replaced by `#REF!`; the other text is copied unchanged, including
    non-ASCII characters. Each end of a range such as `A1:B2` is handled on its own.
''')

SRC = dd('''
    //! Spreadsheet-style cell references.
    use std::fmt;

    pub const MAX_COL: u32 = 18278; // "ZZZ"
    pub const MAX_ROW: u32 = 1_048_576;

    #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
    pub struct CellRef {
        pub col: u32,
        pub row: u32,
        pub abs_col: bool,
        pub abs_row: bool,
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum RefError {
        Empty,
        BadColumn,
        BadRow,
        OutOfRange,
        Trailing,
    }

    pub fn col_name(col: u32) -> Option<String> {
        if col == 0 || col > MAX_COL {
            return None;
        }
        let mut n = col;
        let mut letters = Vec::new();
        while n > 0 {
            n -= 1;
            letters.push(b'A' + (n % 26) as u8);
            n /= 26;
        }
        letters.reverse();
        Some(String::from_utf8(letters).unwrap())
    }

    pub fn col_index(name: &str) -> Option<u32> {
        if name.is_empty() || name.len() > 3 {
            return None;
        }
        let mut n = 0u32;
        for c in name.bytes() {
            if !c.is_ascii_alphabetic() {
                return None;
            }
            n = n * 26 + (c.to_ascii_uppercase() - b'A') as u32 + 1;
        }
        Some(n)
    }

    pub fn parse_cell(s: &str) -> Result<CellRef, RefError> {
        if s.is_empty() {
            return Err(RefError::Empty);
        }
        let b = s.as_bytes();
        let mut i = 0;
        let abs_col = b[0] == b'$';
        if abs_col {
            i += 1;
        }
        let letters = i;
        while i < b.len() && b[i].is_ascii_alphabetic() {
            i += 1;
        }
        let col = col_index(&s[letters..i]).ok_or(RefError::BadColumn)?;
        let abs_row = i < b.len() && b[i] == b'$';
        if abs_row {
            i += 1;
        }
        let digits = i;
        while i < b.len() && b[i].is_ascii_digit() {
            i += 1;
        }
        if digits == i || b[digits] == b'0' {
            return Err(RefError::BadRow);
        }
        let row: u32 = s[digits..i].parse().map_err(|_| RefError::OutOfRange)?;
        if row > MAX_ROW {
            return Err(RefError::OutOfRange);
        }
        if i < b.len() {
            return Err(RefError::Trailing);
        }
        Ok(CellRef { col, row, abs_col, abs_row })
    }

    impl fmt::Display for CellRef {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            let col = col_name(self.col).unwrap_or_default();
            write!(
                f,
                "{}{}{}{}",
                if self.abs_col { "$" } else { "" },
                col,
                if self.abs_row { "$" } else { "" },
                self.row
            )
        }
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub struct RangeRef {
        pub from: CellRef,
        pub to: CellRef,
    }

    impl RangeRef {
        pub fn new(a: CellRef, b: CellRef) -> RangeRef {
            let (left, right) = if a.col <= b.col { (a, b) } else { (b, a) };
            let (top, bottom) = if a.row <= b.row { (a, b) } else { (b, a) };
            RangeRef {
                from: CellRef { col: left.col, abs_col: left.abs_col, row: top.row, abs_row: top.abs_row },
                to: CellRef { col: right.col, abs_col: right.abs_col, row: bottom.row, abs_row: bottom.abs_row },
            }
        }

        pub fn width(&self) -> u32 {
            self.to.col - self.from.col + 1
        }

        pub fn height(&self) -> u32 {
            self.to.row - self.from.row + 1
        }

        pub fn len(&self) -> u64 {
            self.width() as u64 * self.height() as u64
        }

        pub fn contains(&self, c: &CellRef) -> bool {
            c.col >= self.from.col && c.col <= self.to.col && c.row >= self.from.row && c.row <= self.to.row
        }

        pub fn intersect(&self, other: &RangeRef) -> Option<RangeRef> {
            let col0 = self.from.col.max(other.from.col);
            let col1 = self.to.col.min(other.to.col);
            let row0 = self.from.row.max(other.from.row);
            let row1 = self.to.row.min(other.to.row);
            if col0 > col1 || row0 > row1 {
                return None;
            }
            let cell = |col, row| CellRef { col, row, abs_col: false, abs_row: false };
            Some(RangeRef { from: cell(col0, row0), to: cell(col1, row1) })
        }

        pub fn cells(&self) -> Vec<CellRef> {
            let mut out = Vec::with_capacity(self.len() as usize);
            for row in self.from.row..=self.to.row {
                for col in self.from.col..=self.to.col {
                    out.push(CellRef { col, row, abs_col: false, abs_row: false });
                }
            }
            out
        }
    }

    impl fmt::Display for RangeRef {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            if self.from.col == self.to.col && self.from.row == self.to.row {
                write!(f, "{}", self.from)
            } else {
                write!(f, "{}:{}", self.from, self.to)
            }
        }
    }

    pub fn parse_range(s: &str) -> Result<RangeRef, RefError> {
        match s.split_once(':') {
            None => {
                let c = parse_cell(s)?;
                Ok(RangeRef::new(c, c))
            }
            Some((a, b)) => Ok(RangeRef::new(parse_cell(a)?, parse_cell(b)?)),
        }
    }

    pub fn shift(c: &CellRef, drow: i64, dcol: i64) -> Option<CellRef> {
        let col = if c.abs_col { c.col as i64 } else { c.col as i64 + dcol };
        let row = if c.abs_row { c.row as i64 } else { c.row as i64 + drow };
        if col < 1 || col > MAX_COL as i64 || row < 1 || row > MAX_ROW as i64 {
            return None;
        }
        Some(CellRef { col: col as u32, row: row as u32, ..*c })
    }

    fn is_word_byte(c: u8) -> bool {
        c.is_ascii_alphanumeric() || c == b'$' || c == b'_' || c == b'.'
    }

    pub fn shift_formula(formula: &str, drow: i64, dcol: i64) -> String {
        let b = formula.as_bytes();
        let mut out = String::with_capacity(formula.len());
        let mut i = 0;
        while i < b.len() {
            if b[i] == b'"' {
                let mut j = i + 1;
                while j < b.len() {
                    if b[j] == b'"' {
                        if j + 1 < b.len() && b[j + 1] == b'"' {
                            j += 2;
                            continue;
                        }
                        j += 1;
                        break;
                    }
                    j += 1;
                }
                out.push_str(&formula[i..j]);
                i = j;
            } else if is_word_byte(b[i]) {
                let mut j = i;
                while j < b.len() && is_word_byte(b[j]) {
                    j += 1;
                }
                let word = &formula[i..j];
                let is_call = j < b.len() && b[j] == b'(';
                match parse_cell(word) {
                    Ok(cell) if !is_call => match shift(&cell, drow, dcol) {
                        Some(moved) => out.push_str(&moved.to_string()),
                        None => out.push_str("#REF!"),
                    },
                    _ => out.push_str(word),
                }
                i = j;
            } else {
                let ch = formula[i..].chars().next().unwrap();
                out.push(ch);
                i += ch.len_utf8();
            }
        }
        out
    }
''')

VISIBLE = dd('''
    use cellref::*;

    #[test]
    fn column_names() {
        assert_eq!(col_name(1).as_deref(), Some("A"));
        assert_eq!(col_index("AA"), Some(27));
    }

    #[test]
    fn parse_and_print() {
        let c = parse_cell("$b7").unwrap();
        assert_eq!(c.to_string(), "$B7");
    }
''')

HIDDEN = dd('''
    use cellref::*;

    fn cell(s: &str) -> CellRef {
        parse_cell(s).unwrap_or_else(|e| panic!("parse_cell({s:?}) failed: {e:?}"))
    }

    fn rng(s: &str) -> RangeRef {
        parse_range(s).unwrap_or_else(|e| panic!("parse_range({s:?}) failed: {e:?}"))
    }

    fn plain(col: u32, row: u32) -> CellRef {
        CellRef { col, row, abs_col: false, abs_row: false }
    }

    #[test]
    fn col_name_values() {
        let cases = [
            (1, "A"), (2, "B"), (26, "Z"), (27, "AA"), (28, "AB"), (52, "AZ"), (53, "BA"), (78, "BZ"), (79, "CA"),
            (702, "ZZ"), (703, "AAA"), (704, "AAB"), (18278, "ZZZ"), (16384, "XFD"), (18253, "ZZA"),
        ];
        for (n, want) in cases {
            assert_eq!(col_name(n).as_deref(), Some(want), "col_name({n})");
        }
        assert_eq!(col_name(0), None);
        assert_eq!(col_name(18279), None);
        assert_eq!(col_name(u32::MAX), None);
    }

    #[test]
    fn col_index_values() {
        let cases = [("A", 1), ("a", 1), ("z", 26), ("Z", 26), ("AA", 27), ("aZ", 52), ("BA", 53), ("ZZ", 702), ("AAA", 703), ("zzz", 18278), ("XFD", 16384)];
        for (s, want) in cases {
            assert_eq!(col_index(s), Some(want), "col_index({s:?})");
        }
        for bad in ["", "AAAA", "A1", "A ", " A", "1", "$A", "Ä", "A-"] {
            assert_eq!(col_index(bad), None, "col_index({bad:?})");
        }
    }

    #[test]
    fn col_names_round_trip() {
        for n in 1..=MAX_COL {
            let name = col_name(n).unwrap();
            assert!(name.len() <= 3);
            assert_eq!(col_index(&name), Some(n), "{name}");
        }
    }

    #[test]
    fn parse_plain_and_anchored() {
        assert_eq!(cell("A1"), plain(1, 1));
        assert_eq!(cell("B2"), plain(2, 2));
        assert_eq!(cell("$B$2"), CellRef { col: 2, row: 2, abs_col: true, abs_row: true });
        assert_eq!(cell("$B2"), CellRef { col: 2, row: 2, abs_col: true, abs_row: false });
        assert_eq!(cell("B$2"), CellRef { col: 2, row: 2, abs_col: false, abs_row: true });
        assert_eq!(cell("zz10"), plain(702, 10));
        assert_eq!(cell("XFD1048576"), plain(16384, 1_048_576));
        assert_eq!(cell("ZZZ1048576"), plain(18278, 1_048_576));
        assert_eq!(cell("AB100"), plain(28, 100));
        assert_eq!(cell("A10"), plain(1, 10));
        assert_eq!(cell("A1048575"), plain(1, 1_048_575));
    }

    #[test]
    fn parse_errors() {
        let cases = [
            ("", RefError::Empty),
            ("1A", RefError::BadColumn),
            ("$", RefError::BadColumn),
            ("$$A1", RefError::BadColumn),
            ("$1", RefError::BadColumn),
            ("AAAA1", RefError::BadColumn),
            ("A", RefError::BadRow),
            ("A$", RefError::BadRow),
            ("$A$", RefError::BadRow),
            ("A0", RefError::BadRow),
            ("A01", RefError::BadRow),
            ("A$0", RefError::BadRow),
            ("A1048577", RefError::OutOfRange),
            ("A99999999999", RefError::OutOfRange),
            ("A4294967296", RefError::OutOfRange),
            ("A1B", RefError::Trailing),
            ("A1 ", RefError::Trailing),
            ("A1$", RefError::Trailing),
            ("A1:B2", RefError::Trailing),
            ("A$1$", RefError::Trailing),
            ("B2.5", RefError::Trailing),
        ];
        for (s, want) in cases {
            assert_eq!(parse_cell(s), Err(want), "parse_cell({s:?})");
        }
    }

    #[test]
    fn display_is_normalised() {
        assert_eq!(cell("a1").to_string(), "A1");
        assert_eq!(cell("$ab7").to_string(), "$AB7");
        assert_eq!(cell("c$3").to_string(), "C$3");
        assert_eq!(cell("$c$3").to_string(), "$C$3");
        assert_eq!(cell("zzz1048576").to_string(), "ZZZ1048576");
        for s in ["A1", "$B$2", "XFD7", "$AA$100", "C$9"] {
            assert_eq!(cell(s).to_string(), s);
        }
    }

    #[test]
    fn range_normalisation() {
        let r = rng("B2:D4");
        assert_eq!((r.from, r.to), (plain(2, 2), plain(4, 4)));
        assert_eq!(rng("D4:B2"), r);
        assert_eq!(rng("D2:B4"), r);
        assert_eq!(rng("B4:D2"), r);
        let anchored = rng("$D$4:B2");
        assert_eq!(anchored.from, plain(2, 2));
        assert_eq!(anchored.to, CellRef { col: 4, row: 4, abs_col: true, abs_row: true });
        assert_eq!(anchored.to_string(), "B2:$D$4");
        let mixed = rng("$D2:B$4");
        assert_eq!(mixed.from, CellRef { col: 2, row: 2, abs_col: false, abs_row: false });
        assert_eq!(mixed.to, CellRef { col: 4, row: 4, abs_col: true, abs_row: true });
        let swapped = rng("$A5:C$1");
        assert_eq!(swapped.from, CellRef { col: 1, row: 1, abs_col: true, abs_row: true });
        assert_eq!(swapped.to, plain(3, 5));
        assert_eq!(swapped.to_string(), "$A$1:C5");
    }

    #[test]
    fn equal_columns_or_rows_take_the_first_cells_flags() {
        let r = rng("$A1:A$2");
        assert_eq!(r.from, CellRef { col: 1, row: 1, abs_col: true, abs_row: false });
        assert_eq!(r.to, CellRef { col: 1, row: 2, abs_col: false, abs_row: true });
        assert_eq!(r.to_string(), "$A1:A$2");
        let r = rng("A$2:$A1");
        assert_eq!(r.from, plain(1, 1));
        assert_eq!(r.to, CellRef { col: 1, row: 2, abs_col: true, abs_row: true });
        assert_eq!(r.to_string(), "A1:$A$2");
        let r = rng("$C5:$E$5");
        assert_eq!(r.to_string(), "$C5:$E$5");
        let r = rng("$E$5:$C5");
        assert_eq!(r.to_string(), "$C$5:$E5");
    }

    #[test]
    fn single_cell_ranges() {
        let r = rng("c3");
        assert_eq!(r.from, r.to);
        assert_eq!((r.width(), r.height(), r.len()), (1, 1, 1));
        assert_eq!(r.to_string(), "C3");
        assert_eq!(rng("C3:C3").to_string(), "C3");
        assert_eq!(rng("C3:C4").to_string(), "C3:C4");
        assert_eq!(rng("C3:D3").to_string(), "C3:D3");
    }

    #[test]
    fn range_errors() {
        assert_eq!(parse_range(""), Err(RefError::Empty));
        assert_eq!(parse_range("A1:"), Err(RefError::Empty));
        assert_eq!(parse_range(":B2"), Err(RefError::Empty));
        assert_eq!(parse_range("A1:B"), Err(RefError::BadRow));
        assert_eq!(parse_range("1:B2"), Err(RefError::BadColumn));
        assert_eq!(parse_range("A1:B2:C3"), Err(RefError::Trailing));
        assert_eq!(parse_range("A1:B1048577"), Err(RefError::OutOfRange));
        assert_eq!(parse_range("A0:B2"), Err(RefError::BadRow));
    }

    #[test]
    fn range_size() {
        let r = rng("B2:D4");
        assert_eq!((r.width(), r.height(), r.len()), (3, 3, 9));
        let r = rng("A1:A10");
        assert_eq!((r.width(), r.height(), r.len()), (1, 10, 10));
        let r = rng("C5:H5");
        assert_eq!((r.width(), r.height(), r.len()), (6, 1, 6));
        let r = rng("A1:XFD1048576");
        assert_eq!((r.width(), r.height()), (16384, 1_048_576));
        assert_eq!(r.len(), 17_179_869_184);
    }

    #[test]
    fn contains_ignores_anchors() {
        let r = rng("B2:D4");
        for (s, want) in [
            ("B2", true), ("D4", true), ("C3", true), ("$C$3", true), ("B4", true), ("D2", true),
            ("A2", false), ("B1", false), ("E4", false), ("D5", false), ("A1", false), ("E5", false),
        ] {
            assert_eq!(r.contains(&cell(s)), want, "contains({s})");
        }
    }

    #[test]
    fn intersections() {
        let cases = [
            ("B2:D4", "C3:E5", Some("C3:D4")),
            ("C3:E5", "B2:D4", Some("C3:D4")),
            ("B2:D4", "B2:D4", Some("B2:D4")),
            ("A1:Z26", "C3:D4", Some("C3:D4")),
            ("A1:B2", "B2:C3", Some("B2")),
            ("A1:B2", "C1:D2", None),
            ("A1:B2", "A3:B4", None),
            ("A1:B2", "C3:D4", None),
            ("B2:D4", "D1:F2", Some("D2")),
            ("B2:D4", "E1:F2", None),
            ("B2:D4", "A1:E2", Some("B2:D2")),
            ("B2:B9", "A5:C6", Some("B5:B6")),
            ("D4:D4", "D4:D4", Some("D4")),
        ];
        for (a, b, want) in cases {
            let got = rng(a).intersect(&rng(b)).map(|r| r.to_string());
            assert_eq!(got.as_deref(), want, "{a} ∩ {b}");
        }
        let anchored = rng("$B$2:$D$4").intersect(&rng("$C$3:E5")).unwrap();
        assert_eq!(anchored.to_string(), "C3:D4");
    }

    #[test]
    fn cells_in_row_major_order() {
        let got: Vec<String> = rng("B2:C3").cells().iter().map(|c| c.to_string()).collect();
        assert_eq!(got, ["B2", "C2", "B3", "C3"]);
        let got: Vec<String> = rng("$A$1:$C$1").cells().iter().map(|c| c.to_string()).collect();
        assert_eq!(got, ["A1", "B1", "C1"]);
        let got: Vec<String> = rng("D4:D6").cells().iter().map(|c| c.to_string()).collect();
        assert_eq!(got, ["D4", "D5", "D6"]);
        assert_eq!(rng("F9").cells(), vec![plain(6, 9)]);
        assert_eq!(rng("A1:J10").cells().len(), 100);
    }

    #[test]
    fn shift_moves_relative_parts() {
        let moved = shift(&cell("B2"), 1, 1).unwrap();
        assert_eq!(moved.to_string(), "C3");
        assert_eq!(shift(&cell("B2"), 3, 0).unwrap().to_string(), "B5");
        assert_eq!(shift(&cell("B2"), 0, 3).unwrap().to_string(), "E2");
        assert_eq!(shift(&cell("B2"), -1, -1).unwrap().to_string(), "A1");
        assert_eq!(shift(&cell("$B$2"), 5, 5).unwrap().to_string(), "$B$2");
        assert_eq!(shift(&cell("$B2"), 5, 5).unwrap().to_string(), "$B7");
        assert_eq!(shift(&cell("B$2"), 5, 5).unwrap().to_string(), "G$2");
        assert_eq!(shift(&cell("Z1"), 0, 1).unwrap().to_string(), "AA1");
        assert_eq!(shift(&cell("AA1"), 0, -1).unwrap().to_string(), "Z1");
    }

    #[test]
    fn shift_stays_on_the_sheet() {
        assert_eq!(shift(&cell("A1"), -1, 0), None);
        assert_eq!(shift(&cell("A1"), 0, -1), None);
        assert_eq!(shift(&cell("A1"), -1, -1), None);
        assert_eq!(shift(&cell("B2"), -2, 0), None);
        assert_eq!(shift(&cell("B2"), 0, -2), None);
        assert!(shift(&cell("B2"), -1, -1).is_some());
        assert_eq!(shift(&cell("ZZZ1"), 0, 1), None);
        assert!(shift(&cell("ZZZ1"), 0, 0).is_some());
        assert!(shift(&cell("ZZY1"), 0, 1).is_some());
        assert_eq!(shift(&cell("A1048576"), 1, 0), None);
        assert_eq!(shift(&cell("A1048576"), -1, 0).unwrap().row, 1_048_575);
        assert!(shift(&cell("A1048575"), 1, 0).is_some());
        // anchored parts may not leave the sheet either: they simply do not move
        assert!(shift(&cell("$A$1"), -5, -5).is_some());
        assert_eq!(shift(&cell("$A1"), -5, 0), None);
        assert_eq!(shift(&cell("A$1"), 0, -5), None);
        assert_eq!(shift(&cell("A1"), 1_000_000_000_000, 0), None);
    }

    #[test]
    fn formula_basic() {
        assert_eq!(shift_formula("=A1+B2", 1, 1), "=B2+C3");
        assert_eq!(shift_formula("=SUM(A1:B2)", 2, 0), "=SUM(A3:B4)");
        assert_eq!(shift_formula("=SUM(A1:B2)", 0, 1), "=SUM(B1:C2)");
        assert_eq!(shift_formula("A1", 0, 0), "A1");
        assert_eq!(shift_formula("", 3, 3), "");
        assert_eq!(shift_formula("=1+2", 3, 3), "=1+2");
        assert_eq!(shift_formula("=A1*(B1-C1)/D1", 10, 0), "=A11*(B11-C11)/D11");
        assert_eq!(shift_formula("=AB12", -2, 2), "=AD10");
    }

    #[test]
    fn formula_anchors() {
        assert_eq!(shift_formula("=$A$1+$A1+A$1+A1", 1, 1), "=$A$1+$A2+B$1+B2");
        assert_eq!(shift_formula("=SUM(A1:$C$3)", 1, 1), "=SUM(B2:$C$3)");
        assert_eq!(shift_formula("=SUM($A$1:$C$3)", 9, 9), "=SUM($A$1:$C$3)");
    }

    #[test]
    fn formula_functions_are_not_cells() {
        assert_eq!(shift_formula("=LOG10(A1)", 1, 0), "=LOG10(A2)");
        assert_eq!(shift_formula("=log10(a1)", 1, 0), "=log10(A2)");
        assert_eq!(shift_formula("=ATAN2(A1,B1)", 1, 1), "=ATAN2(B2,C2)");
        assert_eq!(shift_formula("=DEC2BIN(A1)", 1, 1), "=DEC2BIN(B2)");
        // a space before the parenthesis: the word is a cell again
        assert_eq!(shift_formula("=LOG10 (A1)", 1, 0), "=LOG11 (A2)");
        assert_eq!(shift_formula("=A1(2)", 1, 0), "=A1(2)");
        assert_eq!(shift_formula("=IF(A1>B1,1,0)", 1, 0), "=IF(A2>B2,1,0)");
        assert_eq!(shift_formula("=TRUE", 1, 0), "=TRUE");
        assert_eq!(shift_formula("=PI()*A1", 1, 0), "=PI()*A2");
    }

    #[test]
    fn formula_words_that_are_not_cells() {
        assert_eq!(shift_formula("=1.5*A1", 1, 0), "=1.5*A2");
        assert_eq!(shift_formula("=1E5+A1", 1, 0), "=1E5+A2");
        assert_eq!(shift_formula("=A1A+A1", 1, 0), "=A1A+A2");
        assert_eq!(shift_formula("=A1_x+A1", 1, 0), "=A1_x+A2");
        assert_eq!(shift_formula("=x.A1+A1", 1, 0), "=x.A1+A2");
        assert_eq!(shift_formula("=Sheet1!A1", 1, 0), "=Sheet1!A2");
        assert_eq!(shift_formula("=AAAA1+A1", 1, 0), "=AAAA1+A2");
        assert_eq!(shift_formula("=A0+A1", 1, 0), "=A0+A2");
        assert_eq!(shift_formula("=_A1+A1", 1, 0), "=_A1+A2");
        assert_eq!(shift_formula("=$A$1$", 1, 0), "=$A$1$");
    }

    #[test]
    fn formula_strings_are_left_alone() {
        assert_eq!(shift_formula("=CONCAT(\\"A1\\",A1)", 1, 0), "=CONCAT(\\"A1\\",A2)");
        assert_eq!(shift_formula("=\\"say \\"\\"A1\\"\\" now\\"&A1", 1, 0), "=\\"say \\"\\"A1\\"\\" now\\"&A2");
        assert_eq!(shift_formula("=\\"abc A1", 1, 0), "=\\"abc A1");
        assert_eq!(shift_formula("=\\"\\"&A1", 1, 0), "=\\"\\"&A2");
        assert_eq!(shift_formula("=\\"A1\\"&\\"B2\\"&C3", 1, 1), "=\\"A1\\"&\\"B2\\"&D4");
        assert_eq!(shift_formula("=A1&\\"x\\"", 1, 0), "=A2&\\"x\\"");
    }

    #[test]
    fn formula_literal_ending_in_an_escaped_quote() {
        assert_eq!(shift_formula("=\\"a\\"\\"\\"&A1", 1, 0), "=\\"a\\"\\"\\"&A2");
        assert_eq!(shift_formula("=\\"\\"\\"\\"&A1&\\"\\"", 1, 0), "=\\"\\"\\"\\"&A2&\\"\\"");
    }

    #[test]
    fn formula_out_of_range() {
        assert_eq!(shift_formula("=A1+A2", -1, 0), "=#REF!+A1");
        assert_eq!(shift_formula("=SUM(A1:B2)", -1, 0), "=SUM(#REF!:B1)");
        assert_eq!(shift_formula("=ZZZ5", 0, 1), "=#REF!");
        assert_eq!(shift_formula("=$A$1+A1", -1, -1), "=$A$1+#REF!");
        assert_eq!(shift_formula("=a1", 0, 0), "=A1");
    }

    #[test]
    fn formula_text_is_preserved() {
        assert_eq!(shift_formula("=Ä1+A1", 1, 1), "=Ä1+B2");
        assert_eq!(shift_formula("=\\"héllo wörld\\"&A1&\\"ü\\"", 1, 0), "=\\"héllo wörld\\"&A2&\\"ü\\"");
        assert_eq!(shift_formula("  =  A1 +\\tB1 ", 1, 0), "  =  A2 +\\tB2 ");
        assert_eq!(shift_formula("日本A1", 1, 0), "日本A2");
        assert_eq!(shift_formula("A1:", 1, 1), "B2:");
    }
''')

LIB = Lib(
    name="cellref", lang="rust", title="the cellref crate",
    blurb="The report builder's formula engine uses cellref to parse A1-style references and to rewrite formulas when cells are copied.",
    files={"Cargo.toml": cargo("cellref"), "src/lib.rs": SRC, "README.md": README, ".gitignore": "target/\n", ".cargo/config.toml": CARGO_CONFIG},
    visible_tests={"tests/basic.rs": VISIBLE},
    hidden_tests={"tests/full.rs": HIDDEN},
    mutate=["src/lib.rs"], difficulty=2, tags=["spreadsheet", "parsing", "formula"],
)

register_libs([LIB], n=8)
