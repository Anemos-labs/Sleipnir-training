"""wrapkit (rust): a text wrapping library extended with indents, prefixes, long-word breaking, paragraphs, justification, display widths, balanced lines."""
import random

from fx import dd, langs
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # wrapkit

    Text wrapping for a terminal tool: reflow text to a column width. Rust 2021, no dependencies; `cargo test` runs the tests.

    ## Layout

    * `src/wrapper.rs`: `Wrapper`, `WrapError`.
    * `tests/`: integration tests.

    ## Basics

    * `Wrapper::new(width) -> Result<Wrapper, WrapError>`: `width` is the number of columns a line may use; 0 is
      `WrapError::ZeroWidth`.
    * `wrapper.wrap(text) -> Vec<String>` reflows `text`. The text is split into words at white space
      (`str::split_whitespace`, so newlines and tabs count as blanks and runs of blanks collapse). A line takes words
      greedily: a word joins the current line, separated by one space, if the line stays within `width` characters (a
      character is one `char`); otherwise it starts the next line. A word longer than `width` stays whole on a line of its
      own. Lines never have leading or trailing spaces; text without words gives an empty vector.
    * `WrapError` implements `Display` (`width must be at least 1` for `ZeroWidth`), `Error`, `Debug`, `Clone` and `PartialEq`.
''')

LIB = '''\
//! Text wrapping.
pub mod wrapper;
@@slot mods

pub use wrapper::{WrapError, Wrapper};
@@slot reexports
'''

WRAPPER = '''\
use std::fmt;
@@uniq imports

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WrapError {
    ZeroWidth,
    @@slot variants
}

impl fmt::Display for WrapError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            WrapError::ZeroWidth => write!(f, "width must be at least 1"),
            @@slot display
        }
    }
}

impl std::error::Error for WrapError {}

@@default measure_fn
fn measure(s: &str) -> usize {
    s.chars().count()
}
@@end

/// A wrapping configuration.
#[derive(Debug, Clone)]
pub struct Wrapper {
    width: usize,
    @@slot fields
}

impl Wrapper {
    pub fn new(width: usize) -> Result<Wrapper, WrapError> {
        if width == 0 {
            return Err(WrapError::ZeroWidth);
        }
        Ok(Wrapper {
            width,
            @@slot init
        })
    }

    @@blocks builders

    fn indentation(&self, line_no: usize) -> usize {
        @@default indent_rule
        let _ = line_no;
        0
        @@end
    }

    /// What goes in front of line number `line_no` of a paragraph.
    fn lead(&self, line_no: usize) -> String {
        let mut s = String::new();
        @@slot lead_prefix
        s.push_str(&" ".repeat(self.indentation(line_no)));
        s
    }

    /// Columns available for words on line number `line_no` of a paragraph (at least 1).
    fn avail(&self, line_no: usize) -> usize {
        self.width.saturating_sub(measure(&self.lead(line_no))).max(1)
    }

    fn split_paragraphs(&self, text: &str) -> Vec<Vec<String>> {
        @@default split_paragraphs
        let words: Vec<String> = text.split_whitespace().map(|w| w.to_string()).collect();
        if words.is_empty() {
            Vec::new()
        } else {
            vec![words]
        }
        @@end
    }

    fn layout(&self, words: &[String]) -> Vec<Vec<String>> {
        @@slot layout_pre
        @@default layout_algo
        let mut lines: Vec<Vec<String>> = Vec::new();
        let mut cur: Vec<String> = Vec::new();
        let mut cur_w = 0usize;
        for word in words {
            let ww = measure(word);
            if !cur.is_empty() && cur_w + 1 + ww <= self.avail(lines.len()) {
                cur_w += 1 + ww;
                cur.push(word.clone());
                continue;
            }
            if !cur.is_empty() {
                lines.push(std::mem::take(&mut cur));
            }
            #[allow(unused_mut)]
            let mut rest = word.clone();
            @@slot long_word
            cur_w = measure(&rest);
            cur.push(rest);
        }
        if !cur.is_empty() {
            lines.push(cur);
        }
        lines
        @@end
    }

    pub fn wrap(&self, text: &str) -> Vec<String> {
        let mut out = Vec::new();
        for (pi, words) in self.split_paragraphs(text).iter().enumerate() {
            if pi > 0 {
                @@slot separator
            }
            let lines = self.layout(words);
            let n = lines.len();
            for (i, line) in lines.iter().enumerate() {
                #[allow(unused_mut)]
                let mut body = line.join(" ");
                @@slot justify_line
                let _ = n;
                out.push(format!("{}{}", self.lead(i), body));
            }
        }
        out
    }

    @@blocks methods
}
'''

HELPERS = '''\
use wrapkit::*;
@@uniq imports

const FOX: &str = "The quick brown fox jumps over the lazy dog";

fn w(width: usize) -> Wrapper {
    Wrapper::new(width).unwrap()
}
'''

VISIBLE = HELPERS + '''
#[test]
fn greedy_wrapping() {
    assert_eq!(w(10).wrap(FOX), ["The quick", "brown fox", "jumps over", "the lazy", "dog"]);
    assert_eq!(w(15).wrap(FOX), ["The quick brown", "fox jumps over", "the lazy dog"]);
    assert_eq!(w(100).wrap(FOX), [FOX]);
}

#[test]
fn blanks_and_long_words() {
    assert_eq!(w(10).wrap("a\\n b\\t\\tc"), ["a b c"]);
    assert_eq!(w(5).wrap("a verylongword b"), ["a", "verylongword", "b"]);
    assert!(w(5).wrap("  \\n ").is_empty());
    assert_eq!(Wrapper::new(0).unwrap_err(), WrapError::ZeroWidth);
}
@@blocks tests
'''

HIDDEN = HELPERS + '''
#[test]
fn base_wrapping() {
    assert_eq!(w(10).wrap(FOX), ["The quick", "brown fox", "jumps over", "the lazy", "dog"]);
    assert_eq!(w(15).wrap(FOX), ["The quick brown", "fox jumps over", "the lazy dog"]);
    assert_eq!(w(43).wrap(FOX), [FOX]);
    assert_eq!(w(42).wrap(FOX), ["The quick brown fox jumps over the lazy", "dog"]);
    assert_eq!(w(1).wrap("a bc d"), ["a", "bc", "d"]);
    assert_eq!(w(3).wrap("aa bb cc"), ["aa", "bb", "cc"]);
    assert_eq!(w(5).wrap("aa bb cc"), ["aa bb", "cc"]);
    assert_eq!(w(80).wrap(""), Vec::<String>::new());
    assert_eq!(w(80).wrap(" \\t\\n "), Vec::<String>::new());
    assert_eq!(w(10).wrap("  lots   of\\nspace  "), ["lots of", "space"]);
    assert_eq!(w(4).wrap("é é é é é"), ["é é", "é é", "é"]);
}

#[test]
fn base_long_words_and_errors() {
    assert_eq!(w(5).wrap("a verylongword b"), ["a", "verylongword", "b"]);
    assert_eq!(w(5).wrap("verylongword"), ["verylongword"]);
    assert_eq!(w(5).wrap("ab verylongword"), ["ab", "verylongword"]);
    assert_eq!(w(12).wrap("verylongword b"), ["verylongword", "b"]);
    assert_eq!(w(14).wrap("verylongword b"), ["verylongword b"]);
    assert_eq!(w(13).wrap("verylongword b"), ["verylongword", "b"]);
    assert_eq!(Wrapper::new(0).unwrap_err(), WrapError::ZeroWidth);
    assert_eq!(WrapError::ZeroWidth.to_string(), "width must be at least 1");
    assert!(Wrapper::new(1).is_ok());
    let e: Box<dyn std::error::Error> = Box::new(WrapError::ZeroWidth);
    assert_eq!(e.to_string(), "width must be at least 1");
    let w2 = w(10);
    let again = w2.clone();
    assert_eq!(w2.wrap("x y"), again.wrap("x y"));
}
@@blocks tests
'''

WIDE = [(0x1100, 0x115F), (0x2E80, 0xA4CF), (0xAC00, 0xD7A3), (0xF900, 0xFAFF), (0xFE30, 0xFE6F), (0xFF00, 0xFF60), (0xFFE0, 0xFFE6)]


def cwid(c, uni):
    if not uni:
        return 1
    u = ord(c)
    if 0x300 <= u <= 0x36F:
        return 0
    if any(a <= u <= b for a, b in WIDE):
        return 2
    return 1


def meas(s, uni):
    return sum(cwid(c, uni) for c in s)


def ref_wrap(text, width, indent=0, first=None, prefix="", brk=False, just=False, bal=False, para=False, uni=False):
    """Reference implementation, written from the specification."""
    def lead(i):
        ind = (first if first is not None else indent) if i == 0 else indent
        return prefix + " " * ind

    def avail(i):
        return max(1, width - meas(lead(i), uni))

    if para:
        paras, cur = [], []
        for ln in text.split("\n"):
            ln = ln[:-1] if ln.endswith("\r") else ln
            ws = ln.split()
            if not ws:
                if cur:
                    paras.append(cur)
                    cur = []
            else:
                cur += ws
        if cur:
            paras.append(cur)
    else:
        ws = text.split()
        paras = [ws] if ws else []

    def greedy(words):
        lines, cur, cur_w = [], [], 0
        for word in words:
            ww = meas(word, uni)
            if cur and cur_w + 1 + ww <= avail(len(lines)):
                cur_w += 1 + ww
                cur.append(word)
                continue
            if cur:
                lines.append(cur)
                cur = []
            rest = word
            if brk:
                while meas(rest, uni) > avail(len(lines)):
                    limit = avail(len(lines))
                    taken, cut = 0, 0
                    for idx, ch in enumerate(rest):
                        cw = cwid(ch, uni)
                        if taken + cw > limit and cut > 0:
                            break
                        taken += cw
                        cut = idx + 1
                    lines.append([rest[:cut]])
                    rest = rest[cut:]
                if rest == "":
                    cur_w = 0
                    continue
            cur_w = meas(rest, uni)
            cur.append(rest)
        if cur:
            lines.append(cur)
        return lines

    def balance(words):
        n = len(words)
        wd = [meas(x, uni) for x in words]
        best = [0] * (n + 1)
        nxt = [n] * (n + 1)
        for i in range(n - 1, -1, -1):
            av = avail(0) if i == 0 else avail(1)
            width_ = 0
            chosen = None
            for j in range(i + 1, n + 1):
                width_ += wd[j - 1] + (1 if j - 1 > i else 0)
                fits = width_ <= av
                if not fits and j > i + 1:
                    break
                cost = 0 if (j == n or not fits) else (av - width_) ** 2
                total = cost + best[j]
                if chosen is None or total <= chosen[0]:
                    chosen = (total, j)
            best[i], nxt[i] = chosen
        lines, i = [], 0
        while i < n:
            lines.append(words[i:nxt[i]])
            i = nxt[i]
        return lines

    out = []
    for pi, words in enumerate(paras):
        if pi:
            out.append(prefix.rstrip() if prefix else "")
        lines = balance(words) if bal else greedy(words)
        n = len(lines)
        for i, line in enumerate(lines):
            body = " ".join(line)
            if just and i + 1 < n and len(line) > 1:
                target = avail(i)
                words_w = sum(meas(x, uni) for x in line)
                gaps = len(line) - 1
                if words_w + gaps < target:
                    spaces = target - words_w
                    each, extra = divmod(spaces, gaps)
                    body = ""
                    for k, x in enumerate(line):
                        body += x
                        if k < gaps:
                            body += " " * (each + (1 if k < extra else 0))
            out.append(lead(i) + body)
    return out


def rv(lines):
    """A Rust array literal of string literals."""
    def lit(s):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return "[" + ", ".join(lit(x) for x in lines) + "]"


def rs_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + '"'


FOX = "The quick brown fox jumps over the lazy dog"
LONGS = "An extraordinarily long word: supercalifragilisticexpialidocious appears here, and then some more words follow it"
PARAS = "First paragraph with\nsome words in it.\n\n\n  Second one is short.  \n\nThird paragraph, a little longer than the others are."
PARAS_CRLF = "alpha beta\r\ngamma\r\n\r\ndelta epsilon zeta\r\n"
CJK = "日本語 の 文章 です。 mixed with ascii words and 漢字 too"
BAL = "aaa bb cc ddddd"
BAL2 = "Four score and seven years ago our fathers brought forth on this continent a new nation conceived in liberty"


def make_slices(rng: random.Random):
    pfx = rng.choice(["> ", "| ", "# "])
    S = []

    S.append(Slice(
        id="indent", title="Indentation", d=1,
        pitch=("Quoted blocks in the generated emails sit flush against the margin.",
               "Wrapped text needs to be indented."),
        reqs=("`wrapper.indent(n) -> Result<Wrapper, WrapError>` makes every output line start with `n` spaces (default 0). The indent counts towards the width: the words of a line get `width - n` columns, but at least 1. An indent of `width` or more is the new error `WrapError::IndentTooWide { indent, width }` (`Display`: `indent N must be smaller than the width W`).",),
        code={
            "src/wrapper.rs::variants": "IndentTooWide { indent: usize, width: usize },",
            "src/wrapper.rs::display": 'WrapError::IndentTooWide { indent, width } => write!(f, "indent {} must be smaller than the width {}", indent, width),',
            "src/wrapper.rs::fields": "indent: usize,",
            "src/wrapper.rs::init": "indent: 0,",
            "src/wrapper.rs::indent_rule": "let _ = line_no;\nself.indent",
            "src/wrapper.rs::builders": '''
                pub fn indent(mut self, n: usize) -> Result<Wrapper, WrapError> {
                    if n >= self.width {
                        return Err(WrapError::IndentTooWide { indent: n, width: self.width });
                    }
                    self.indent = n;
                    Ok(self)
                }
            ''',
        },
        readme="## Indentation\n\n`wrapper.indent(n)` puts `n` spaces in front of every line; the indent counts towards the width (words get at least 1 column). `n >= width` is `WrapError::IndentTooWide { indent, width }`.\n",
        vtests=f'''
            #[test]
            fn indent_basic() {{
                let lines = w(20).indent(4).unwrap().wrap(FOX);
                assert_eq!(lines[0], "    {ref_wrap(FOX, 20, indent=4)[0].strip()}");
            }}
        ''',
        tests=fmt('''
            #[test]
            fn indent_counts_towards_the_width() {
                assert_eq!(w(20).indent(4).unwrap().wrap(FOX), __A__);
                assert_eq!(w(20).indent(0).unwrap().wrap(FOX), w(20).wrap(FOX));
                assert_eq!(w(10).indent(8).unwrap().wrap("a bb ccc"), __B__);
                let wide = w(12).indent(11).unwrap();
                assert_eq!(wide.wrap("ab c"), __C__);
            }

            #[test]
            fn indent_too_wide() {
                assert_eq!(w(10).indent(10).unwrap_err(), WrapError::IndentTooWide { indent: 10, width: 10 });
                assert_eq!(w(10).indent(25).unwrap_err(), WrapError::IndentTooWide { indent: 25, width: 10 });
                assert!(w(10).indent(9).is_ok());
                assert_eq!(w(10).indent(10).unwrap_err().to_string(), "indent 10 must be smaller than the width 10");
            }
        ''', A=rv(ref_wrap(FOX, 20, indent=4)), B=rv(ref_wrap("a bb ccc", 10, indent=8)), C=rv(ref_wrap("ab c", 12, indent=11))),
    ))

    S.append(Slice(
        id="first-indent", title="Hanging and first-line indents", d=2, needs=("indent",),
        pitch=("Bulleted lists in the help output need the first line out-dented relative to the continuation lines.",
               "The first line of a paragraph should be indented differently from the rest."),
        reqs=("`wrapper.first_indent(n) -> Result<Wrapper, WrapError>` sets the indent of the first line of every paragraph, independently of `indent` (which keeps applying to all the other lines). Without it the first line uses `indent` as before. The same rule as for `indent` applies: `n >= width` is `WrapError::IndentTooWide`, and the first line's words get `width - n` columns (at least 1).",),
        code={
            "src/wrapper.rs::fields": "first_indent: Option<usize>,",
            "src/wrapper.rs::init": "first_indent: None,",
            "src/wrapper.rs::builders": '''
                pub fn first_indent(mut self, n: usize) -> Result<Wrapper, WrapError> {
                    if n >= self.width {
                        return Err(WrapError::IndentTooWide { indent: n, width: self.width });
                    }
                    self.first_indent = Some(n);
                    Ok(self)
                }
            ''',
        },
        readme="## Hanging and first-line indents\n\n`wrapper.first_indent(n)` indents only the first line of each paragraph (default: `indent`); `n >= width` is `IndentTooWide`.\n",
        vtests=f'''
            #[test]
            fn first_indent_basic() {{
                let lines = w(20).indent(2).unwrap().first_indent(0).unwrap().wrap(FOX);
                assert_eq!(lines[1], "  {ref_wrap(FOX, 20, indent=2, first=0)[1].strip()}");
            }}
        ''',
        tests=fmt('''
            #[test]
            fn first_line_has_its_own_indent() {
                assert_eq!(w(20).indent(4).unwrap().first_indent(0).unwrap().wrap(FOX), __A__);
                assert_eq!(w(20).indent(0).unwrap().first_indent(6).unwrap().wrap(FOX), __B__);
                assert_eq!(w(20).indent(3).unwrap().wrap(FOX), w(20).indent(3).unwrap().first_indent(3).unwrap().wrap(FOX));
                assert_eq!(w(16).indent(2).unwrap().first_indent(10).unwrap().wrap("alpha beta gamma delta"), __C__);
            }

            #[test]
            fn first_indent_errors() {
                assert_eq!(w(10).first_indent(10).unwrap_err(), WrapError::IndentTooWide { indent: 10, width: 10 });
                assert!(w(10).first_indent(9).is_ok());
                assert_eq!(w(10).indent(2).unwrap().first_indent(12).unwrap_err().to_string(), "indent 12 must be smaller than the width 10");
            }
        ''', A=rv(ref_wrap(FOX, 20, indent=4, first=0)), B=rv(ref_wrap(FOX, 20, indent=0, first=6)),
            C=rv(ref_wrap("alpha beta gamma delta", 16, indent=2, first=10))),
        cross={
            "indent": {
                "code": {"src/wrapper.rs::indent_rule": "if line_no == 0 {\n    self.first_indent.unwrap_or(self.indent)\n} else {\n    self.indent\n}"},
            },
        },
    ))

    S.append(Slice(
        id="prefix", title="Line prefix", d=2,
        pitch=("Replies in the mail client have to be quoted with `> ` on every line.",
               "Every wrapped line needs a fixed prefix such as a quote marker."),
        reqs=(f"`wrapper.prefix(p) -> Result<Wrapper, WrapError>` puts the text `p` at the start of every output line, in front of any indentation. The prefix counts towards the width like an indent does. A prefix that is as wide as the width or wider (in characters) is the new error `WrapError::PrefixTooWide {{ prefix, width }}` (both numbers in characters; `Display`: `prefix of N columns does not fit into width W`). The default prefix is empty.",),
        code={
            "src/wrapper.rs::variants": "PrefixTooWide { prefix: usize, width: usize },",
            "src/wrapper.rs::display": 'WrapError::PrefixTooWide { prefix, width } => write!(f, "prefix of {} columns does not fit into width {}", prefix, width),',
            "src/wrapper.rs::fields": "prefix: String,",
            "src/wrapper.rs::init": "prefix: String::new(),",
            "src/wrapper.rs::lead_prefix": "s.push_str(&self.prefix);",
            "src/wrapper.rs::builders": '''
                pub fn prefix(mut self, p: &str) -> Result<Wrapper, WrapError> {
                    let cols = measure(p);
                    if cols >= self.width {
                        return Err(WrapError::PrefixTooWide { prefix: cols, width: self.width });
                    }
                    self.prefix = p.to_string();
                    Ok(self)
                }
            ''',
        },
        readme="## Line prefix\n\n`wrapper.prefix(p)` starts every line with `p` (before indentation); the prefix counts towards the width. A prefix as wide as the width or wider is `WrapError::PrefixTooWide { prefix, width }`.\n",
        vtests=f'''
            #[test]
            fn prefix_basic() {{
                let lines = w(20).prefix("{pfx}").unwrap().wrap(FOX);
                assert!(lines.iter().all(|l| l.starts_with("{pfx}")));
            }}
        ''',
        tests=fmt('''
            #[test]
            fn prefix_counts_towards_the_width() {
                assert_eq!(w(20).prefix("__P__").unwrap().wrap(FOX), __A__);
                assert_eq!(w(20).prefix("").unwrap().wrap(FOX), w(20).wrap(FOX));
                assert_eq!(w(8).prefix("=>").unwrap().wrap("a bb ccc dddd"), __B__);
            }

            #[test]
            fn prefix_errors() {
                assert_eq!(w(4).prefix("abcd").unwrap_err(), WrapError::PrefixTooWide { prefix: 4, width: 4 });
                assert_eq!(w(4).prefix("abcde").unwrap_err().to_string(), "prefix of 5 columns does not fit into width 4");
                assert!(w(4).prefix("abc").is_ok());
                assert_eq!(w(2).prefix("é").unwrap().wrap("a b"), ["éa", "éb"]);
            }
        ''', P=pfx, A=rv(ref_wrap(FOX, 20, prefix=pfx)), B=rv(ref_wrap("a bb ccc dddd", 8, prefix="=>"))),
        cross={
            "indent": {
                "reqs": ("The prefix comes first, then the indentation spaces, then the words; both count towards the width.",),
                "tests": fmt('''
                    #[test]
                    fn prefix_and_indent() {
                        assert_eq!(w(24).prefix("__P__").unwrap().indent(2).unwrap().wrap(FOX), __A__);
                    }
                ''', P=pfx, A=rv(ref_wrap(FOX, 24, prefix=pfx, indent=2))),
            },
            "first-indent": {"tests": fmt('''
                #[test]
                fn prefix_and_first_indent() {
                    assert_eq!(w(24).prefix("__P__").unwrap().indent(4).unwrap().first_indent(1).unwrap().wrap(FOX), __A__);
                }
            ''', P=pfx, A=rv(ref_wrap(FOX, 24, prefix=pfx, indent=4, first=1)))},
        },
    ))

    S.append(Slice(
        id="paragraphs", title="Paragraphs", d=2,
        pitch=("The release notes lose all their blank lines when they are reflowed.",
               "Blank lines in the input must survive as paragraph breaks."),
        reqs=("`wrap` now treats the input as paragraphs. A line that is empty or holds only white space ends the current paragraph (several blank lines count as one, blank lines at the start and the end of the text are ignored); the other lines of a paragraph are joined as before (`\\r\\n` line ends are fine). Every paragraph is wrapped on its own, and between two paragraphs the output has one empty string. Text with a single paragraph gives the same output as before.",),
        code={
            "src/wrapper.rs::split_paragraphs": '''
                let mut paras: Vec<Vec<String>> = Vec::new();
                let mut cur: Vec<String> = Vec::new();
                for line in text.lines() {
                    let ws: Vec<String> = line.split_whitespace().map(|w| w.to_string()).collect();
                    if ws.is_empty() {
                        if !cur.is_empty() {
                            paras.push(std::mem::take(&mut cur));
                        }
                    } else {
                        cur.extend(ws);
                    }
                }
                if !cur.is_empty() {
                    paras.push(cur);
                }
                paras
            ''',
            "src/wrapper.rs::separator": "out.push(self.blank_line());",
            "src/wrapper.rs::methods": '''
                fn blank_line(&self) -> String {
                    let mut s = String::new();
                    @@slot blank_prefix
                    s
                }
            ''',
        },
        readme="## Paragraphs\n\nBlank lines separate paragraphs; each is wrapped on its own and one empty string separates them in the output (leading and trailing blank lines are ignored, runs of blank lines count once).\n",
        vtests=f'''
            #[test]
            fn paragraphs_basic() {{
                assert_eq!(w(20).wrap("a b\\n\\nc d"), ["a b", "", "c d"]);
            }}
        ''',
        tests=fmt('''
            #[test]
            fn paragraphs_are_wrapped_separately() {
                assert_eq!(w(20).wrap(__T__), __A__);
                assert_eq!(w(12).wrap(__T__), __B__);
                assert_eq!(w(10).wrap(__CRLF__), __C__);
            }

            #[test]
            fn paragraph_edge_cases() {
                assert_eq!(w(20).wrap("\\n\\n  \\n"), Vec::<String>::new());
                assert_eq!(w(20).wrap("\\n\\none\\n\\n"), ["one"]);
                assert_eq!(w(20).wrap("one two\\nthree"), ["one two three"]);
                assert_eq!(w(5).wrap("a\\n\\n\\n\\nb"), ["a", "", "b"]);
                assert_eq!(w(5).wrap("a\\n \\t \\nb"), ["a", "", "b"]);
                assert_eq!(w(80).wrap(__T__).len(), 5);
            }
        ''', T=rs_str(PARAS), CRLF=rs_str(PARAS_CRLF), A=rv(ref_wrap(PARAS, 20, para=True)), B=rv(ref_wrap(PARAS, 12, para=True)),
            C=rv(ref_wrap(PARAS_CRLF, 10, para=True))),
        cross={
            "prefix": {
                "reqs": ("The empty line between two paragraphs carries the prefix with its trailing white space removed (so `> ` gives `>`).",),
                "code": {"src/wrapper.rs::blank_prefix": "s.push_str(self.prefix.trim_end());"},
                "tests": fmt('''
                    #[test]
                    fn blank_lines_carry_the_trimmed_prefix() {
                        assert_eq!(w(20).prefix("__P__").unwrap().wrap(__T__), __A__);
                    }
                ''', P=pfx, T=rs_str(PARAS), A=rv(ref_wrap(PARAS, 20, prefix=pfx, para=True))),
            },
        },
    ))

    S.append(Slice(
        id="break-long", title="Breaking long words", d=2,
        pitch=("A URL longer than the terminal makes the whole table spill over to the next screen line.",
               "Words that do not fit on a line should be cut instead of overflowing."),
        reqs=("`wrapper.break_long(on) -> Wrapper` (default off) makes the wrapper cut words that are too long. A word that does not fit on the line it would start (after the current line has been closed) is cut into pieces: every piece except the last takes as many characters as fit into the columns available on its line (at least one character) and gets a line of its own; the last piece becomes the start of a normal line that following words can join. A word that fits stays whole. With the option off nothing changes.",),
        code={
            "src/wrapper.rs::fields": "break_long: bool,",
            "src/wrapper.rs::init": "break_long: false,",
            "src/wrapper.rs::builders": '''
                pub fn break_long(mut self, on: bool) -> Wrapper {
                    self.break_long = on;
                    self
                }
            ''',
            "src/wrapper.rs::long_word": '''
                if self.break_long {
                    while measure(&rest) > self.avail(lines.len()) {
                        let limit = self.avail(lines.len());
                        let mut taken = 0usize;
                        let mut cut = 0usize;
                        for (idx, c) in rest.char_indices() {
                            let cw = measure(&c.to_string());
                            if taken + cw > limit && cut > 0 {
                                break;
                            }
                            taken += cw;
                            cut = idx + c.len_utf8();
                        }
                        lines.push(vec![rest[..cut].to_string()]);
                        rest = rest[cut..].to_string();
                    }
                    if rest.is_empty() {
                        cur_w = 0;
                        continue;
                    }
                }
            ''',
        },
        readme="## Breaking long words\n\n`wrapper.break_long(true)` cuts words that do not fit: full pieces get lines of their own, the last piece starts a normal line.\n",
        vtests='''
            #[test]
            fn break_long_basic() {
                assert_eq!(w(4).break_long(true).wrap("abcdefghij"), ["abcd", "efgh", "ij"]);
            }
        ''',
        tests=fmt('''
            #[test]
            fn long_words_are_cut() {
                assert_eq!(w(12).break_long(true).wrap(__T__), __A__);
                assert_eq!(w(4).break_long(true).wrap("abcdefghij kl m"), __B__);
                assert_eq!(w(5).break_long(true).wrap("abcde abcdef"), ["abcde", "abcde", "f"]);
                assert_eq!(w(5).break_long(true).wrap("ab abcdefghijkl"), __C__);
                assert_eq!(w(3).break_long(true).wrap("é𝄞ñoüx"), ["é𝄞ñ", "oüx"]);
            }

            #[test]
            fn long_words_stay_whole_by_default() {
                assert_eq!(w(12).wrap(__T__), w(12).break_long(false).wrap(__T__));
                assert_eq!(w(4).break_long(false).wrap("abcdefghij"), ["abcdefghij"]);
                assert_eq!(w(4).break_long(true).break_long(false).wrap("abcdefghij"), ["abcdefghij"]);
                assert_eq!(w(10).break_long(true).wrap(FOX), w(10).wrap(FOX));
            }
        ''', T=rs_str(LONGS), A=rv(ref_wrap(LONGS, 12, brk=True)), B=rv(ref_wrap("abcdefghij kl m", 4, brk=True)),
            C=rv(ref_wrap("ab abcdefghijkl", 5, brk=True))),
        conflicts=("balance",),
        cross={
            "indent": {
                "reqs": ("The available columns are the width minus the prefix and indent of the line the piece lands on.",),
                "tests": fmt('''
                    #[test]
                    fn pieces_respect_the_indent() {
                        assert_eq!(w(8).indent(3).unwrap().break_long(true).wrap("abcdefghijkl mn"), __A__);
                    }
                ''', A=rv(ref_wrap("abcdefghijkl mn", 8, indent=3, brk=True))),
            },
            "first-indent": {
                "reqs": ("The first line of a paragraph may have fewer or more columns than the others; the pieces follow the line they land on.",),
                "tests": fmt('''
                    #[test]
                    fn pieces_respect_the_first_indent() {
                        assert_eq!(w(8).indent(1).unwrap().first_indent(4).unwrap().break_long(true).wrap("abcdefghijklmnop qr"), __A__);
                    }
                ''', A=rv(ref_wrap("abcdefghijklmnop qr", 8, indent=1, first=4, brk=True))),
            },
            "prefix": {"tests": fmt('''
                #[test]
                fn pieces_respect_the_prefix() {
                    assert_eq!(w(6).prefix("> ").unwrap().break_long(true).wrap("abcdefghi jk"), __A__);
                }
            ''', A=rv(ref_wrap("abcdefghi jk", 6, prefix="> ", brk=True)))},
            "paragraphs": {"tests": fmt('''
                #[test]
                fn pieces_in_every_paragraph() {
                    assert_eq!(w(4).break_long(true).wrap("abcdefg\\n\\nhijklmn"), __A__);
                }
            ''', A=rv(ref_wrap("abcdefg\n\nhijklmn", 4, brk=True, para=True)))},
        },
    ))

    S.append(Slice(
        id="justify", title="Justified text", d=3,
        pitch=("The printed manual looks ragged next to the old typeset version.",
               "Some output needs to be justified to both margins."),
        reqs=("`wrapper.justify(on) -> Wrapper` (default off) pads the lines of a paragraph to the full width available on them. Every line except the last line of its paragraph and except lines with a single word is stretched: the gaps between words start at one space and the missing spaces (`available - total width of the words`) are spread evenly over the gaps, with the left-most gaps getting one more when they do not divide evenly. Lines that already use the whole width, lines that overflow, the last line of each paragraph and single-word lines are left alone. Indentation and prefix are added after padding.",),
        code={
            "src/wrapper.rs::fields": "justify: bool,",
            "src/wrapper.rs::init": "justify: false,",
            "src/wrapper.rs::builders": '''
                pub fn justify(mut self, on: bool) -> Wrapper {
                    self.justify = on;
                    self
                }
            ''',
            "src/wrapper.rs::justify_line": '''
                if self.justify && i + 1 < n && line.len() > 1 {
                    let target = self.avail(i);
                    let words_w: usize = line.iter().map(|w| measure(w)).sum();
                    let gaps = line.len() - 1;
                    if words_w + gaps < target {
                        let spaces = target - words_w;
                        let (each, extra) = (spaces / gaps, spaces % gaps);
                        body = String::new();
                        for (k, word) in line.iter().enumerate() {
                            body.push_str(word);
                            if k < gaps {
                                body.push_str(&" ".repeat(each + usize::from(k < extra)));
                            }
                        }
                    }
                }
            ''',
        },
        readme="## Justified text\n\n`wrapper.justify(true)` stretches every line but the last of a paragraph (and single-word lines) to the available width, spreading spaces evenly with the left-most gaps getting the extra ones.\n",
        vtests='''
            #[test]
            fn justify_basic() {
                assert_eq!(w(15).justify(true).wrap(FOX)[1], "fox  jumps over");
            }
        ''',
        tests=fmt('''
            #[test]
            fn justified_lines() {
                assert_eq!(w(15).justify(true).wrap(FOX), __A__);
                assert_eq!(w(20).justify(true).wrap(FOX), __B__);
                assert_eq!(w(26).justify(true).wrap(__T2__), __C__);
                assert_eq!(w(10).justify(true).wrap("a verylongword b c d"), __D__);
            }

            #[test]
            fn justify_leaves_the_rest_alone() {
                assert_eq!(w(15).justify(false).wrap(FOX), w(15).wrap(FOX));
                assert_eq!(w(40).justify(true).wrap("short text"), ["short text"]);
                assert_eq!(w(12).justify(true).wrap("one two three"), __E__);
                assert_eq!(w(5).justify(true).wrap("a b c d e f"), __F__);
            }
        ''', A=rv(ref_wrap(FOX, 15, just=True)), B=rv(ref_wrap(FOX, 20, just=True)), T2=rs_str(BAL2), C=rv(ref_wrap(BAL2, 26, just=True)),
            D=rv(ref_wrap("a verylongword b c d", 10, just=True)), E=rv(ref_wrap("one two three", 12, just=True)),
            F=rv(ref_wrap("a b c d e f", 5, just=True))),
        cross={
            "indent": {"tests": fmt('''
                #[test]
                fn justify_inside_the_indent() {
                    assert_eq!(w(22).indent(3).unwrap().justify(true).wrap(__T__), __A__);
                }
            ''', T=rs_str(BAL2), A=rv(ref_wrap(BAL2, 22, indent=3, just=True)))},
            "prefix": {"tests": fmt('''
                #[test]
                fn justify_inside_the_prefix() {
                    assert_eq!(w(22).prefix("__P__").unwrap().justify(true).wrap(__T__), __A__);
                }
            ''', P=pfx, T=rs_str(BAL2), A=rv(ref_wrap(BAL2, 22, prefix=pfx, just=True)))},
            "paragraphs": {
                "reqs": ("Every paragraph keeps its own last line unjustified.",),
                "tests": fmt('''
                    #[test]
                    fn justify_every_paragraph() {
                        assert_eq!(w(20).justify(true).wrap(__T__), __A__);
                    }
                ''', T=rs_str(PARAS), A=rv(ref_wrap(PARAS, 20, just=True, para=True))),
            },
        },
    ))

    S.append(Slice(
        id="unicode-width", title="Display widths", d=3,
        pitch=("Chinese and Japanese text overflows the table columns because every character counts as one.",
               "Widths should be measured in terminal columns, not in characters."),
        reqs=("All widths (the wrapper width, the lengths of words and lines, indents, prefixes and the padding of justified lines) are measured in terminal columns instead of characters. The width of a character is 0 for U+0300 to U+036F (combining marks), 2 for the code points in U+1100-U+115F, U+2E80-U+A4CF, U+AC00-U+D7A3, U+F900-U+FAFF, U+FE30-U+FE6F, U+FF00-U+FF60 and U+FFE0-U+FFE6, and 1 for everything else. Ordinary text is unaffected.",
              "The measure is public as `wrapkit::display_width(&str) -> usize` (in the new file `src/width.rs`)."),
        files={
            "src/width.rs": '''\
//! Terminal column widths.

/// The number of terminal columns a text takes.
pub fn display_width(s: &str) -> usize {
    s.chars().map(char_width).sum()
}

fn char_width(c: char) -> usize {
    let u = c as u32;
    if (0x0300..=0x036F).contains(&u) {
        return 0;
    }
    let wide = [
        (0x1100, 0x115F),
        (0x2E80, 0xA4CF),
        (0xAC00, 0xD7A3),
        (0xF900, 0xFAFF),
        (0xFE30, 0xFE6F),
        (0xFF00, 0xFF60),
        (0xFFE0, 0xFFE6),
    ];
    if wide.iter().any(|&(a, b)| (a..=b).contains(&u)) {
        return 2;
    }
    1
}
''',
        },
        code={
            "src/lib.rs::mods": "pub mod width;",
            "src/lib.rs::reexports": "pub use width::display_width;",
            "src/wrapper.rs::measure_fn": '''
                fn measure(s: &str) -> usize {
                    crate::width::display_width(s)
                }
            ''',
        },
        readme="## Display widths\n\nWidths are measured in terminal columns (`wrapkit::display_width`): combining marks U+0300-U+036F take 0, the East Asian ranges U+1100-U+115F, U+2E80-U+A4CF, U+AC00-U+D7A3, U+F900-U+FAFF, U+FE30-U+FE6F, U+FF00-U+FF60 and U+FFE0-U+FFE6 take 2, everything else 1.\n",
        vtests='''
            #[test]
            fn display_width_basic() {
                assert_eq!(display_width("日本語"), 6);
            }
        ''',
        tests=fmt('''
            #[test]
            fn widths() {
                assert_eq!(display_width(""), 0);
                assert_eq!(display_width("hello"), 5);
                assert_eq!(display_width("日本語"), 6);
                assert_eq!(display_width("e\\u{301}"), 1);
                assert_eq!(display_width("ｆｕｌｌ"), 8);
                assert_eq!(display_width("한글"), 4);
                assert_eq!(display_width("a\\u{300}\\u{301}b"), 2);
                assert_eq!(display_width("é"), 1);
                assert_eq!(display_width("ア"), 2);
                assert_eq!(display_width("¡"), 1);
            }

            #[test]
            fn wrapping_by_columns() {
                assert_eq!(w(8).wrap(__T__), __A__);
                assert_eq!(w(5).wrap("日本語 ab"), ["日本語", "ab"]);
                assert_eq!(w(6).wrap("日本語 ab"), ["日本語", "ab"]);
                assert_eq!(w(9).wrap("日本語 ab"), ["日本語 ab"]);
                assert_eq!(w(4).wrap("e\\u{301}e\\u{301}e\\u{301}e\\u{301} x"), ["e\\u{301}e\\u{301}e\\u{301}e\\u{301}", "x"]);
                assert_eq!(w(12).wrap(__T__), __B__);
            }
        ''', T=rs_str(CJK), A=rv(ref_wrap(CJK, 8, uni=True)), B=rv(ref_wrap(CJK, 12, uni=True))),
        cross={
            "break-long": {"tests": fmt('''
                #[test]
                fn wide_characters_are_cut_by_columns() {
                    assert_eq!(w(5).break_long(true).wrap("日本語の文章"), __A__);
                    assert_eq!(w(1).break_long(true).wrap("日本"), ["日", "本"]);
                }
            ''', A=rv(ref_wrap("日本語の文章", 5, brk=True, uni=True)))},
            "justify": {"tests": fmt('''
                #[test]
                fn justify_pads_by_columns() {
                    assert_eq!(w(14).justify(true).wrap(__T__), __A__);
                }
            ''', T=rs_str(CJK), A=rv(ref_wrap(CJK, 14, just=True, uni=True)))},
            "indent": {"tests": fmt('''
                #[test]
                fn indent_is_measured_in_columns_too() {
                    assert_eq!(w(10).indent(2).unwrap().wrap("日本語 の 文章"), __A__);
                }
            ''', A=rv(ref_wrap("日本語 の 文章", 10, indent=2, uni=True)))},
            "prefix": {
                "reqs": ("A prefix is measured in columns as well (`WrapError::PrefixTooWide` reports columns).",),
                "tests": '''
                    #[test]
                    fn prefix_in_columns() {
                        assert_eq!(w(4).prefix("日").unwrap().wrap("ab c"), ["日ab", "日c"]);
                        assert_eq!(w(4).prefix("日日").unwrap_err(), WrapError::PrefixTooWide { prefix: 4, width: 4 });
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="balance", title="Balanced lines", d=4, conflicts=("break-long",),
        pitch=("Greedy wrapping leaves a single short word hanging at the end of the second last line and the captions look ragged.",
               "Some outputs should have evenly filled lines instead of greedy ones."),
        reqs=("`wrapper.balance(on) -> Wrapper` (default off) chooses the line breaks of every paragraph so that the lines are as even as possible. The cost of a break set is the sum, over all lines except the last one of the paragraph, of `(available - line width)^2`, where the line width counts the words and one space between neighbours and `available` is the width left for words on that line (a line that is a single word wider than `available` costs 0, and a line may only hold more than one word if it fits). The break set with the smallest cost wins; among equal costs the one that puts more words on the earlier lines (comparing line by line from the first) wins. Word widths, indentation and prefixes work as without `balance`; justification (if enabled) works on the balanced lines. Long words are not cut.",),
        code={
            "src/wrapper.rs::fields": "balance: bool,",
            "src/wrapper.rs::init": "balance: false,",
            "src/wrapper.rs::builders": '''
                pub fn balance(mut self, on: bool) -> Wrapper {
                    self.balance = on;
                    self
                }
            ''',
            "src/wrapper.rs::methods": '''
                fn balanced(&self, words: &[String]) -> Vec<Vec<String>> {
                    let n = words.len();
                    let w: Vec<usize> = words.iter().map(|x| measure(x)).collect();
                    let mut best = vec![0u64; n + 1];
                    let mut next = vec![n; n + 1];
                    for i in (0..n).rev() {
                        let avail = (if i == 0 { self.avail(0) } else { self.avail(1) }) as u64;
                        let mut width = 0u64;
                        let mut chosen: Option<(u64, usize)> = None;
                        for j in (i + 1)..=n {
                            width += w[j - 1] as u64 + if j - 1 > i { 1 } else { 0 };
                            let fits = width <= avail;
                            if !fits && j > i + 1 {
                                break;
                            }
                            let cost = if j == n || !fits { 0 } else { (avail - width).pow(2) };
                            let total = cost + best[j];
                            match chosen {
                                Some((c, _)) if total > c => {}
                                _ => chosen = Some((total, j)),
                            }
                        }
                        let (c, j) = chosen.unwrap();
                        best[i] = c;
                        next[i] = j;
                    }
                    let mut lines = Vec::new();
                    let mut i = 0;
                    while i < n {
                        lines.push(words[i..next[i]].to_vec());
                        i = next[i];
                    }
                    lines
                }
            ''',
            "src/wrapper.rs::layout_pre": '''
                if self.balance {
                    return self.balanced(words);
                }
            ''',
        },
        readme="## Balanced lines\n\n`wrapper.balance(true)` minimises the sum of squared unused columns over all lines but the last of a paragraph; ties go to the break set with more words on the earlier lines. Long words are not cut.\n",
        vtests='''
            #[test]
            fn balance_basic() {
                assert_eq!(w(6).balance(true).wrap("aaa bb cc ddddd"), ["aaa", "bb cc", "ddddd"]);
            }
        ''',
        tests=fmt('''
            #[test]
            fn balanced_lines() {
                assert_eq!(w(6).wrap("aaa bb cc ddddd"), ["aaa bb", "cc", "ddddd"]);
                assert_eq!(w(6).balance(true).wrap("aaa bb cc ddddd"), ["aaa", "bb cc", "ddddd"]);
                assert_eq!(w(30).balance(true).wrap(__T__), __A__);
                assert_eq!(w(20).balance(true).wrap(__T__), __B__);
                assert_eq!(w(15).balance(true).wrap(FOX), __C__);
                assert_eq!(w(10).balance(true).wrap("a verylongword b c d e"), __D__);
            }

            #[test]
            fn balance_edge_cases() {
                assert_eq!(w(10).balance(true).wrap(""), Vec::<String>::new());
                assert_eq!(w(10).balance(true).wrap("one"), ["one"]);
                assert_eq!(w(100).balance(true).wrap(FOX), [FOX]);
                assert_eq!(w(10).balance(false).wrap(FOX), w(10).wrap(FOX));
                assert_eq!(w(7).balance(true).wrap("ab cd ef gh ij kl"), __E__);
                assert_eq!(w(3).balance(true).wrap("aaaa bbbb c"), ["aaaa", "bbbb", "c"]);
            }
        ''', T=rs_str(BAL2), A=rv(ref_wrap(BAL2, 30, bal=True)), B=rv(ref_wrap(BAL2, 20, bal=True)), C=rv(ref_wrap(FOX, 15, bal=True)),
            D=rv(ref_wrap("a verylongword b c d e", 10, bal=True)), E=rv(ref_wrap("ab cd ef gh ij kl", 7, bal=True))),
        cross={
            "justify": {"tests": fmt('''
                #[test]
                fn balanced_and_justified() {
                    assert_eq!(w(24).balance(true).justify(true).wrap(__T__), __A__);
                }
            ''', T=rs_str(BAL2), A=rv(ref_wrap(BAL2, 24, bal=True, just=True)))},
            "indent": {"tests": fmt('''
                #[test]
                fn balance_respects_the_indent() {
                    assert_eq!(w(24).indent(4).unwrap().balance(true).wrap(__T__), __A__);
                }
            ''', T=rs_str(BAL2), A=rv(ref_wrap(BAL2, 24, indent=4, bal=True)))},
            "first-indent": {
                "reqs": ("The first line of a paragraph is balanced with its own available width.",),
                "tests": fmt('''
                    #[test]
                    fn balance_respects_the_first_indent() {
                        assert_eq!(w(22).indent(2).unwrap().first_indent(8).unwrap().balance(true).wrap(__T__), __A__);
                    }
                ''', T=rs_str(BAL2), A=rv(ref_wrap(BAL2, 22, indent=2, first=8, bal=True)))},
            "paragraphs": {"tests": fmt('''
                #[test]
                fn balance_every_paragraph() {
                    assert_eq!(w(16).balance(true).wrap(__T__), __A__);
                }
            ''', T=rs_str(PARAS), A=rv(ref_wrap(PARAS, 16, bal=True, para=True)))},
            "unicode-width": {"tests": fmt('''
                #[test]
                fn balance_by_columns() {
                    assert_eq!(w(10).balance(true).wrap(__T__), __A__);
                }
            ''', T=rs_str(CJK), A=rv(ref_wrap(CJK, 10, bal=True, uni=True)))},
        },
    ))

    return S


APP = App(
    name="wrapkit", lang="rust", title="the text wrapping library", role="a command-line tool author", key="WRAP",
    base={
        "README.md": README + "\n@@blocks features\n",
        "Cargo.toml": langs.cargo_toml("wrapkit"),
        "src/lib.rs": LIB,
        "src/wrapper.rs": WRAPPER,
        ".gitignore": langs.GITIGNORE["rust"],
    },
    visible={"tests/basic.rs": VISIBLE},
    hidden={"tests/features.rs": HIDDEN},
)

register_app("feature-rs-wrapkit", APP, make_slices, n=18, summary="text wrapping: indents, prefixes, paragraphs, long-word breaking, justification, display widths, balanced lines")
