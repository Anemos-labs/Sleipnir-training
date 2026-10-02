"""Port libraries about text: encodings, display width, folding and fixed-width formats."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

# ======================================================================================================================
# msg-split: byte-budgeted message segments
# ======================================================================================================================

MS_SPEC = dd('''
    A notification gateway can carry at most `limit` **UTF-8 bytes** per message. Texts are sequences of Unicode code
    points (no lone surrogates); a code point takes 1 byte below U+0080, 2 below U+0800, 3 below U+10000 and 4 above. A
    code point is never split.

    * `utf8_len(text)` is the number of bytes of the UTF-8 encoding.
    * `truncate_bytes(text, limit)` is the longest prefix of whole code points whose `utf8_len` is `<= limit`.
      `limit < 0` is an error.
    * `split_segments(text, limit)` cuts a text into segments, none longer than `limit` bytes. `limit < 4` is an error.
      The empty text gives no segments. Otherwise repeat on the remaining text `R`:
      1. let `P = truncate_bytes(R, limit)`;
      2. if `P` is all of `R`, the last segment is `P`;
      3. else if the last code point of `P` is not a space (U+0020) **and** the first code point of what follows `P`
         is not a space either, the cut would fall inside a word: if `P` contains a space at some position `>= 1`
         (counting code points from 0), cut after the **last** such space (the space stays at the end of the segment),
         otherwise cut `P` as it is;
      4. in every other case the segment is `P`.
      Segments are never empty and their concatenation is the original text.
    * `count_segments(text, limit)` is the number of segments `split_segments` returns (same errors).
''')

MS_FNS = [
    Fn("utf8_len", [("text", "str")], "int"),
    Fn("truncate_bytes", [("text", "str"), ("limit", "int")], "str", err=True),
    Fn("split_segments", [("text", "str"), ("limit", "int")], "list<str>", err=True),
    Fn("count_segments", [("text", "str"), ("limit", "int")], "int", err=True),
]

MS_PY = dd(r'''
def _width(ch):
    c = ord(ch)
    return 1 if c < 0x80 else 2 if c < 0x800 else 3 if c < 0x10000 else 4


def utf8_len(text):
    return sum(_width(ch) for ch in text)


def _prefix_count(text, start, limit):
    used = n = 0
    while start + n < len(text):
        w = _width(text[start + n])
        if used + w > limit:
            break
        used += w
        n += 1
    return n


def truncate_bytes(text, limit):
    if limit < 0:
        raise ValueError("negative limit")
    return text[:_prefix_count(text, 0, limit)]


def split_segments(text, limit):
    if limit < 4:
        raise ValueError("limit too small")
    out = []
    pos = 0
    while pos < len(text):
        n = _prefix_count(text, pos, limit)
        if pos + n < len(text) and text[pos + n - 1] != " " and text[pos + n] != " ":
            j = text.rfind(" ", pos + 1, pos + n)
            if j != -1:
                n = j - pos + 1
        out.append(text[pos:pos + n])
        pos += n
    return out


def count_segments(text, limit):
    return len(split_segments(text, limit))
''')

MS_GO = dd(r'''
package msgsplit

import (
	"errors"
	"unicode/utf8"
)

func Utf8Len(text string) int64 { return int64(len(text)) }

func prefixCount(rs []rune, start int, limit int64) int {
	var used int64
	n := 0
	for start+n < len(rs) {
		w := int64(utf8.RuneLen(rs[start+n]))
		if used+w > limit {
			break
		}
		used += w
		n++
	}
	return n
}

func TruncateBytes(text string, limit int64) (string, error) {
	if limit < 0 {
		return "", errors.New("negative limit")
	}
	rs := []rune(text)
	return string(rs[:prefixCount(rs, 0, limit)]), nil
}

func splitRunes(text string, limit int64) ([]string, error) {
	if limit < 4 {
		return nil, errors.New("limit too small")
	}
	rs := []rune(text)
	out := []string{}
	pos := 0
	for pos < len(rs) {
		n := prefixCount(rs, pos, limit)
		if pos+n < len(rs) && rs[pos+n-1] != ' ' && rs[pos+n] != ' ' {
			for j := pos + n - 1; j >= pos+1; j-- {
				if rs[j] == ' ' {
					n = j - pos + 1
					break
				}
			}
		}
		out = append(out, string(rs[pos:pos+n]))
		pos += n
	}
	return out, nil
}

func SplitSegments(text string, limit int64) ([]string, error) { return splitRunes(text, limit) }

func CountSegments(text string, limit int64) (int64, error) {
	segs, err := splitRunes(text, limit)
	if err != nil {
		return 0, err
	}
	return int64(len(segs)), nil
}
''')

MS_JS = dd(r'''
'use strict';

function width(ch) {
  const c = ch.codePointAt(0);
  return c < 0x80 ? 1 : c < 0x800 ? 2 : c < 0x10000 ? 3 : 4;
}

function utf8Len(text) {
  let n = 0;
  for (const ch of text) n += width(ch);
  return n;
}

function prefixCount(cps, start, limit) {
  let used = 0;
  let n = 0;
  while (start + n < cps.length) {
    const w = width(cps[start + n]);
    if (used + w > limit) break;
    used += w;
    n += 1;
  }
  return n;
}

function truncateBytes(text, limit) {
  if (limit < 0) throw new Error('negative limit');
  const cps = Array.from(text);
  return cps.slice(0, prefixCount(cps, 0, limit)).join('');
}

function splitSegments(text, limit) {
  if (limit < 4) throw new Error('limit too small');
  const cps = Array.from(text);
  const out = [];
  let pos = 0;
  while (pos < cps.length) {
    let n = prefixCount(cps, pos, limit);
    if (pos + n < cps.length && cps[pos + n - 1] !== ' ' && cps[pos + n] !== ' ') {
      for (let j = pos + n - 1; j >= pos + 1; j--) {
        if (cps[j] === ' ') {
          n = j - pos + 1;
          break;
        }
      }
    }
    out.push(cps.slice(pos, pos + n).join(''));
    pos += n;
  }
  return out;
}

function countSegments(text, limit) {
  return splitSegments(text, limit).length;
}

module.exports = { utf8Len, truncateBytes, splitSegments, countSegments };
''')


def ms_cases(rng):
    alphabet = ["a", "b", "c", "d", "e", " ", " ", "\u00e9", "\u00fc", "\u4e2d", "\u6587", "\U0001F600", "\U0001F680", "\u20ac", "x", "yy", "zzz", "\u0301"]
    out = [("utf8_len", ["h\u00e9llo"]), ("utf8_len", ["\U0001F600"]), ("truncate_bytes", ["h\u00e9llo", 2]), ("truncate_bytes", ["\u4e2d\u6587", 4]),
           ("split_segments", ["hello brave new world", 8]), ("split_segments", ["\U0001F600\U0001F600\U0001F600", 8]), ("split_segments", ["", 10]), ("count_segments", ["hello brave new world", 8])]
    for t in ["", "a", "abc", "\u00e9", "\u20ac", "\U0001F600", "a\u0301", "\u4e2d\u6587\u6587", "caf\u00e9 \u2615", "\U00010000\U0010FFFF", "\x00\x7f", "\u07ff\u0800", "\uffff\U00010000"]:
        out.append(("utf8_len", [t]))
    for t in ["h\u00e9llo", "\U0001F600abc", "ab\U0001F600", "", "\u4e2d\u6587", "abc", "\u20ac\u20ac"]:
        for lim in [0, 1, 2, 3, 4, 5, 6, 100]:
            out.append(("truncate_bytes", [t, lim]))
    out.append(("truncate_bytes", ["abc", -1]))
    for t in ["a b", "ab cd ef gh", " ab", "  ", "abcdefghij", "abc defghij klm", "aaaa bbbb", "aaaa bbbbb cc", "\u4e2d\u6587\u6587\u6587 \u4e2d", "x \U0001F600\U0001F600 y", "word  word", "ab cd", "abcd efgh", "abcd  efgh", " abcdef"]:
        for lim in [4, 5, 6, 7, 9]:
            out.append(("split_segments", [t, lim]))
    for lim in [3, 0, -1]:
        out.append(("split_segments", ["abc", lim]))
        out.append(("count_segments", ["abc", lim]))
    for _ in range(40):
        t = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        lim = rng.choice([4, 4, 5, 6, 8, 10, 16, 25])
        out.append(("split_segments", [t, lim]))
        out.append(("count_segments", [t, lim]))
        out.append(("truncate_bytes", [t, rng.randint(0, 30)]))
        out.append(("utf8_len", [t]))
    return out


MS = PortLib(
    slug="msg-split",
    title="byte-budget message splitting",
    blurb="A notification gateway delivers text over a channel that limits each message to a number of UTF-8 bytes, and long messages are cut into segments.",
    spec=MS_SPEC,
    fns=MS_FNS,
    impls={"python": {"msg_split.py": MS_PY}, "go": {"msgsplit.go": MS_GO}, "javascript": {"src/msg_split.js": MS_JS}},
    cases=ms_cases,
    difficulty=4,
    traps=["bytes vs code points vs UTF-16 units", "astral characters", "word-aware cutting rule"],
    tags=["unicode", "utf-8"],
    pairs=[("python", "go", "full"), ("go", "javascript", "full"), ("javascript", "python", "stub"), ("python", "javascript", "stub")],
    diff_adj={"go>javascript": 0, "python>javascript": 0},
)
register_port(MS, __name__)

# ======================================================================================================================
# col-wrap: display-width aware wrapping
# ======================================================================================================================

CW_SPEC = dd('''
    Terminal columns. Every Unicode code point has a **display width**:

    * `0` for the combining marks U+0300..U+036F,
    * `2` for the "wide" code points in these ranges (inclusive): U+1100..U+115F, U+2E80..U+303E, U+3041..U+33FF,
      U+3400..U+4DBF, U+4E00..U+9FFF, U+A000..U+A4CF, U+AC00..U+D7A3, U+F900..U+FAFF, U+FE30..U+FE4F, U+FF00..U+FF60,
      U+FFE0..U+FFE6, U+1F300..U+1F64F, U+1F900..U+1F9FF, U+20000..U+2FFFD, U+30000..U+3FFFD,
    * `1` for everything else.

    A text is a sequence of code points (no lone surrogates). The only separator is the space U+0020; `\\n` ends a paragraph.

    * `display_width(text)` is the sum of the widths of its code points.
    * `clip(text, width)` is the longest prefix of whole code points whose cumulative width stays `<= width`; scanning stops
      at the first code point that does not fit. `width < 0` is an error.
    * `pad_to(text, width)` appends spaces until the display width reaches `width`; a text that is already as wide or wider is
      returned unchanged.
    * `wrap(text, width)` returns lines. `width < 2` is an error. Split the text on `\\n`; every paragraph is wrapped on its own and an
      empty paragraph (no words) gives one empty line `""`. Inside a paragraph, words are the maximal runs of non-space
      code points (runs of spaces collapse, leading and trailing spaces vanish). Words are added greedily to the current
      line, separated by one space, as long as the line's display width stays `<= width`. A word whose own display width
      exceeds `width` is broken: the current line (if any) is closed first, then the word is cut with repeated `clip`
      calls into pieces; every full piece is a line and the final remainder (which fits) becomes the current line, so
      following words can join it. A closed line is never empty except for the empty-paragraph case.
''')

CW_FNS = [
    Fn("display_width", [("text", "str")], "int"),
    Fn("clip", [("text", "str"), ("width", "int")], "str", err=True),
    Fn("pad_to", [("text", "str"), ("width", "int")], "str"),
    Fn("wrap", [("text", "str"), ("width", "int")], "list<str>", err=True),
]

CW_PY = dd(r'''
_WIDE = [(0x1100, 0x115F), (0x2E80, 0x303E), (0x3041, 0x33FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xA000, 0xA4CF),
         (0xAC00, 0xD7A3), (0xF900, 0xFAFF), (0xFE30, 0xFE4F), (0xFF00, 0xFF60), (0xFFE0, 0xFFE6), (0x1F300, 0x1F64F),
         (0x1F900, 0x1F9FF), (0x20000, 0x2FFFD), (0x30000, 0x3FFFD)]


def _w(ch):
    c = ord(ch)
    if 0x300 <= c <= 0x36F:
        return 0
    for lo, hi in _WIDE:
        if lo <= c <= hi:
            return 2
    return 1


def display_width(text):
    return sum(_w(ch) for ch in text)


def clip(text, width):
    if width < 0:
        raise ValueError("negative width")
    used = 0
    for i, ch in enumerate(text):
        w = _w(ch)
        if used + w > width:
            return text[:i]
        used += w
    return text


def pad_to(text, width):
    return text + " " * max(0, width - display_width(text))


def _wrap_paragraph(par, width, out):
    words = [w for w in par.split(" ") if w]
    if not words:
        out.append("")
        return
    line = ""
    for word in words:
        ww = display_width(word)
        if ww > width:
            if line:
                out.append(line)
                line = ""
            rest = word
            while display_width(rest) > width:
                piece = clip(rest, width)
                out.append(piece)
                rest = rest[len(piece):]
            line = rest
        elif not line:
            line = word
        elif display_width(line) + 1 + ww <= width:
            line += " " + word
        else:
            out.append(line)
            line = word
    if line:
        out.append(line)


def wrap(text, width):
    if width < 2:
        raise ValueError("width too small")
    out = []
    for par in text.split("\n"):
        _wrap_paragraph(par, width, out)
    return out
''')

CW_RS = dd(r'''
const WIDE: [(u32, u32); 15] = [
    (0x1100, 0x115F), (0x2E80, 0x303E), (0x3041, 0x33FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xA000, 0xA4CF),
    (0xAC00, 0xD7A3), (0xF900, 0xFAFF), (0xFE30, 0xFE4F), (0xFF00, 0xFF60), (0xFFE0, 0xFFE6), (0x1F300, 0x1F64F),
    (0x1F900, 0x1F9FF), (0x20000, 0x2FFFD), (0x30000, 0x3FFFD),
];

fn w(c: char) -> i64 {
    let c = c as u32;
    if (0x300..=0x36F).contains(&c) {
        return 0;
    }
    if WIDE.iter().any(|&(lo, hi)| lo <= c && c <= hi) {
        return 2;
    }
    1
}

pub fn display_width(text: &str) -> i64 {
    text.chars().map(w).sum()
}

fn clip_chars(chars: &[char], width: i64) -> usize {
    let mut used = 0;
    for (i, &c) in chars.iter().enumerate() {
        let cw = w(c);
        if used + cw > width {
            return i;
        }
        used += cw;
    }
    chars.len()
}

pub fn clip(text: &str, width: i64) -> Result<String, String> {
    if width < 0 {
        return Err("negative width".to_string());
    }
    let chars: Vec<char> = text.chars().collect();
    Ok(chars[..clip_chars(&chars, width)].iter().collect())
}

pub fn pad_to(text: &str, width: i64) -> String {
    let have = display_width(text);
    let pad = if width > have { (width - have) as usize } else { 0 };
    format!("{}{}", text, " ".repeat(pad))
}

fn wrap_paragraph(par: &str, width: i64, out: &mut Vec<String>) {
    let words: Vec<&str> = par.split(' ').filter(|x| !x.is_empty()).collect();
    if words.is_empty() {
        out.push(String::new());
        return;
    }
    let mut line = String::new();
    for word in words {
        let ww = display_width(word);
        if ww > width {
            if !line.is_empty() {
                out.push(std::mem::take(&mut line));
            }
            let mut rest: Vec<char> = word.chars().collect();
            while rest.iter().map(|&c| w(c)).sum::<i64>() > width {
                let n = clip_chars(&rest, width);
                out.push(rest[..n].iter().collect());
                rest = rest[n..].to_vec();
            }
            line = rest.iter().collect();
        } else if line.is_empty() {
            line = word.to_string();
        } else if display_width(&line) + 1 + ww <= width {
            line.push(' ');
            line.push_str(word);
        } else {
            out.push(std::mem::replace(&mut line, word.to_string()));
        }
    }
    if !line.is_empty() {
        out.push(line);
    }
}

pub fn wrap(text: &str, width: i64) -> Result<Vec<String>, String> {
    if width < 2 {
        return Err("width too small".to_string());
    }
    let mut out = Vec::new();
    for par in text.split('\n') {
        wrap_paragraph(par, width, &mut out);
    }
    Ok(out)
}
''')

CW_TS = dd(r'''
const WIDE: number[][] = [
  [0x1100, 0x115f], [0x2e80, 0x303e], [0x3041, 0x33ff], [0x3400, 0x4dbf], [0x4e00, 0x9fff], [0xa000, 0xa4cf],
  [0xac00, 0xd7a3], [0xf900, 0xfaff], [0xfe30, 0xfe4f], [0xff00, 0xff60], [0xffe0, 0xffe6], [0x1f300, 0x1f64f],
  [0x1f900, 0x1f9ff], [0x20000, 0x2fffd], [0x30000, 0x3fffd],
];

function w(ch: string): number {
  const c = ch.codePointAt(0) as number;
  if (c >= 0x300 && c <= 0x36f) return 0;
  for (const [lo, hi] of WIDE) {
    if (c >= lo && c <= hi) return 2;
  }
  return 1;
}

function widthOf(cps: string[]): number {
  let s = 0;
  for (const ch of cps) s += w(ch);
  return s;
}

export function displayWidth(text: string): number {
  return widthOf(Array.from(text));
}

function clipCount(cps: string[], width: number): number {
  let used = 0;
  for (let i = 0; i < cps.length; i++) {
    const cw = w(cps[i]);
    if (used + cw > width) return i;
    used += cw;
  }
  return cps.length;
}

export function clip(text: string, width: number): string {
  if (width < 0) throw new Error('negative width');
  const cps = Array.from(text);
  return cps.slice(0, clipCount(cps, width)).join('');
}

export function padTo(text: string, width: number): string {
  const have = displayWidth(text);
  return text + ' '.repeat(Math.max(0, width - have));
}

function wrapParagraph(par: string, width: number, out: string[]): void {
  const words = par.split(' ').filter((x) => x.length > 0);
  if (words.length === 0) {
    out.push('');
    return;
  }
  let line = '';
  for (const word of words) {
    const ww = displayWidth(word);
    if (ww > width) {
      if (line) {
        out.push(line);
        line = '';
      }
      let rest = Array.from(word);
      while (widthOf(rest) > width) {
        const n = clipCount(rest, width);
        out.push(rest.slice(0, n).join(''));
        rest = rest.slice(n);
      }
      line = rest.join('');
    } else if (!line) {
      line = word;
    } else if (displayWidth(line) + 1 + ww <= width) {
      line += ' ' + word;
    } else {
      out.push(line);
      line = word;
    }
  }
  if (line) out.push(line);
}

export function wrap(text: string, width: number): string[] {
  if (width < 2) throw new Error('width too small');
  const out: string[] = [];
  for (const par of text.split('\n')) wrapParagraph(par, width, out);
  return out;
}
''')


def cw_cases(rng):
    pieces = ["a", "bb", "ccc", "dddd", "\u4e2d", "\u4e2d\u6587", "\U0001F600", "e\u0301", "\u00e9", "\uff21", "\u3042\u3044", "xyz", "\u1100", "\u0301", "\u20ac", "\U00020000", "\uffe5"]
    out = [("display_width", ["abc"]), ("display_width", ["\u4e2d\u6587a"]), ("display_width", ["e\u0301"]), ("clip", ["\u4e2d\u6587abc", 3]), ("pad_to", ["\u4e2d", 4]),
           ("wrap", ["the quick brown fox jumps", 10]), ("wrap", ["\u4e2d\u6587\u6587 abc \u4e2d", 6]), ("wrap", ["a\n\nb", 5])]
    for t in ["", "a", "\u4e2d", "\U0001F600", "\U0001F680", "\u4e2d\u6587", "e\u0301", "\u0301", "a\u0301\u0302", "\uff21\uff22", "\u3042\u3044\u3046", "\uac00\ud7a3", "\ud7a4", "\u00e9\u00e8", "\u1100\u1160",
              "\u303e\u303f", "\u3040\u3041", "\u33ff\u3400", "\u4dbf\u4dc0", "\u9fff\ua000", "\ua4cf\ua4d0", "\ufe30\ufe4f\ufe50", "\uff60\uff61", "\uffe0\uffe6\uffe7", "\U0001F64F\U0001F650", "\U0001F8ff\U0001F900\U0001F9ff\U0001FA00",
              "\U0001F2ff\U0001F300", "\U0001FFFD\U00020000\U0002FFFD\U0002FFFE", "\U0003FFFD\U0003FFFE", "tab\there"]:
        out.append(("display_width", [t]))
    for t in ["abcdef", "\u4e2d\u6587\u6587abc", "a\u4e2d", "\u4e2d\u4e2d", "e\u0301e\u0301", "\U0001F600\U0001F600", "\u0301abc", "ab\u0301c", ""]:
        for wd in [0, 1, 2, 3, 4, 5, 8]:
            out.append(("clip", [t, wd]))
    out.append(("clip", ["abc", -1]))
    for t in ["", "ab", "\u4e2d", "e\u0301", "\U0001F600x"]:
        for wd in [-3, 0, 1, 2, 3, 6]:
            out.append(("pad_to", [t, wd]))
    for t in ["hello world", "a b c d e f g", "  lead  and   trail  ", "\n", "x\n", "\nx", "one\ntwo\n\nthree", "supercalifragilistic", "ab supercalifragilistic cd", "\u4e2d\u6587\u6587\u6587\u6587 a", "a \u4e2d\u6587\u6587 b", "e\u0301e\u0301 e\u0301", "   ",
              "\U0001F600 \U0001F600 \U0001F600 \U0001F600", "\u4e2d\u6587\u6587\u6587\u6587\u6587\u6587 x", "ab\u4e2d\u6587\u6587", "\u0301\u0301 a", "aaa bb cccc"]:
        for wd in [2, 3, 4, 5, 7, 10]:
            out.append(("wrap", [t, wd]))
    out.append(("wrap", ["abc", 1]))
    out.append(("wrap", ["abc", 0]))
    for _ in range(30):
        words = ["".join(rng.choice(pieces) for _ in range(rng.randint(1, 5))) for _ in range(rng.randint(0, 8))]
        t = rng.choice([" ", " ", "  ", "\n"]).join(words)
        out.append(("wrap", [t, rng.randint(2, 14)]))
        out.append(("display_width", [t]))
        out.append(("clip", [t, rng.randint(0, 12)]))
    return out


CW = PortLib(
    slug="col-wrap",
    title="terminal column wrapping",
    blurb="A command-line report tool lays text out in terminal columns, where CJK characters and emoji occupy two cells and combining marks none.",
    spec=CW_SPEC,
    fns=CW_FNS,
    impls={"rust": {"src/lib.rs": CW_RS}, "python": {"col_wrap.py": CW_PY}, "typescript": {"src/col_wrap.ts": CW_TS}},
    cases=cw_cases,
    difficulty=4,
    traps=["display width vs length", "code points vs UTF-16 units", "greedy wrapping with long-word breaking"],
    tags=["unicode", "display-width"],
    pairs=[("rust", "python", "full"), ("python", "typescript", "full"), ("typescript", "rust", "stub"), ("rust", "typescript", "stub")],
)
register_port(CW, __name__)

# ======================================================================================================================
# ascii-fold: key normalisation for an index
# ======================================================================================================================

AF_SPEC = dd('''
    Keys for a catalogue index. **Only ASCII is folded**: the letters `A-Z` become `a-z` and nothing else changes case, so
    `É`, `ß`, `İ` and every other non-ASCII character are left exactly as they are. The only *whitespace* is the four characters
    space, tab (`\\t`), line feed (`\\n`) and carriage return (`\\r`); other space-like characters (no-break space U+00A0,
    U+2003, ...) are ordinary characters. Texts are sequences of Unicode code points (no lone surrogates) and order is
    always **code point order** (U+FF5E sorts before U+1F600).

    * `fold_key(text)` lowercases `A-Z`, turns every run of whitespace into a single space and removes whitespace at both ends.
    * `cmp_keys(a, b)` compares `fold_key(a)` with `fold_key(b)` code point by code point (a proper prefix is smaller) and
      returns `-1`, `0` or `1`.
    * `sort_keys(xs)` returns the strings of `xs` (unchanged) ordered by their folded key; equal keys keep their original order.
    * `dedupe_keys(xs)` keeps, for each folded key, only the first string that has it (unchanged), in the original order.
    * `initials(text)`: split `text` on whitespace (empty pieces dropped); the result is the first code point of each word,
      with `a-z` turned into `A-Z`, concatenated. A word starting with an emoji contributes the whole emoji.
''')

AF_FNS = [
    Fn("fold_key", [("text", "str")], "str"),
    Fn("cmp_keys", [("a", "str"), ("b", "str")], "i32"),
    Fn("sort_keys", [("xs", "list<str>")], "list<str>"),
    Fn("dedupe_keys", [("xs", "list<str>")], "list<str>"),
    Fn("initials", [("text", "str")], "str"),
]

AF_JS = dd(r'''
'use strict';

const WS = new Set([' ', '\t', '\n', '\r']);

function words(text) {
  const out = [];
  let cur = [];
  for (const ch of text) {
    if (WS.has(ch)) {
      if (cur.length) out.push(cur.join(''));
      cur = [];
    } else {
      cur.push(ch);
    }
  }
  if (cur.length) out.push(cur.join(''));
  return out;
}

function lowerAscii(s) {
  return s.replace(/[A-Z]/g, (c) => String.fromCharCode(c.charCodeAt(0) + 32));
}

function foldKey(text) {
  return words(lowerAscii(text)).join(' ');
}

function cmpPoints(a, b) {
  const x = Array.from(a);
  const y = Array.from(b);
  const n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i++) {
    const p = x[i].codePointAt(0);
    const q = y[i].codePointAt(0);
    if (p !== q) return p < q ? -1 : 1;
  }
  return x.length === y.length ? 0 : x.length < y.length ? -1 : 1;
}

function cmpKeys(a, b) {
  return cmpPoints(foldKey(a), foldKey(b));
}

function sortKeys(xs) {
  return xs
    .map((s, i) => ({ s, k: foldKey(s), i }))
    .sort((a, b) => cmpPoints(a.k, b.k) || a.i - b.i)
    .map((e) => e.s);
}

function dedupeKeys(xs) {
  const seen = new Set();
  const out = [];
  for (const s of xs) {
    const k = foldKey(s);
    if (!seen.has(k)) {
      seen.add(k);
      out.push(s);
    }
  }
  return out;
}

function initials(text) {
  return words(text)
    .map((w) => {
      const first = Array.from(w)[0];
      return first >= 'a' && first <= 'z' ? first.toUpperCase() : first;
    })
    .join('');
}

module.exports = { foldKey, cmpKeys, sortKeys, dedupeKeys, initials };
''')

AF_PY = dd(r'''
_WS = " \t\n\r"


def _words(text):
    out, cur = [], []
    for ch in text:
        if ch in _WS:
            if cur:
                out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


def _lower_ascii(s):
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in s)


def fold_key(text):
    return " ".join(_words(_lower_ascii(text)))


def _points(s):
    return [ord(c) for c in s]


def cmp_keys(a, b):
    x, y = _points(fold_key(a)), _points(fold_key(b))
    return (x > y) - (x < y)


def sort_keys(xs):
    return sorted(xs, key=lambda s: _points(fold_key(s)))


def dedupe_keys(xs):
    seen, out = set(), []
    for s in xs:
        k = fold_key(s)
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def initials(text):
    out = []
    for w in _words(text):
        c = w[0]
        out.append(chr(ord(c) - 32) if "a" <= c <= "z" else c)
    return "".join(out)
''')

AF_GO = dd(r'''
package asciifold

import (
	"sort"
	"strings"
)

func isWS(r rune) bool { return r == ' ' || r == '\t' || r == '\n' || r == '\r' }

func words(text string) []string {
	var out []string
	var cur []rune
	for _, r := range text {
		if isWS(r) {
			if len(cur) > 0 {
				out = append(out, string(cur))
			}
			cur = nil
		} else {
			cur = append(cur, r)
		}
	}
	if len(cur) > 0 {
		out = append(out, string(cur))
	}
	return out
}

func lowerASCII(s string) string {
	rs := []rune(s)
	for i, r := range rs {
		if r >= 'A' && r <= 'Z' {
			rs[i] = r + 32
		}
	}
	return string(rs)
}

func FoldKey(text string) string {
	return strings.Join(words(lowerASCII(text)), " ")
}

func cmpRunes(a, b string) int32 {
	x, y := []rune(a), []rune(b)
	n := len(x)
	if len(y) < n {
		n = len(y)
	}
	for i := 0; i < n; i++ {
		if x[i] != y[i] {
			if x[i] < y[i] {
				return -1
			}
			return 1
		}
	}
	switch {
	case len(x) == len(y):
		return 0
	case len(x) < len(y):
		return -1
	}
	return 1
}

func CmpKeys(a, b string) int32 { return cmpRunes(FoldKey(a), FoldKey(b)) }

func SortKeys(xs []string) []string {
	type entry struct {
		s, k string
	}
	es := make([]entry, len(xs))
	for i, s := range xs {
		es[i] = entry{s, FoldKey(s)}
	}
	sort.SliceStable(es, func(i, j int) bool { return cmpRunes(es[i].k, es[j].k) < 0 })
	out := make([]string, len(xs))
	for i, e := range es {
		out[i] = e.s
	}
	return out
}

func DedupeKeys(xs []string) []string {
	seen := map[string]bool{}
	out := []string{}
	for _, s := range xs {
		k := FoldKey(s)
		if !seen[k] {
			seen[k] = true
			out = append(out, s)
		}
	}
	return out
}

func Initials(text string) string {
	var b strings.Builder
	for _, w := range words(text) {
		r := []rune(w)[0]
		if r >= 'a' && r <= 'z' {
			r -= 32
		}
		b.WriteRune(r)
	}
	return b.String()
}
''')


def af_cases(rng):
    pieces = ["a", "B", "\u00c9", "\u00e9", "\u00df", "\u0130", "i", " ", "  ", "\t", "\n", "\u00a0", "\u2003", "\uff5e", "\U0001F600", "\u1e9e", "Z", "z", "1", "-", "\u212a", "K", "k", "\u0301"]
    out = [("fold_key", ["  Hello \t World \n"]), ("fold_key", ["\u00c9COLE"]), ("cmp_keys", ["Apple", "apple"]), ("cmp_keys", ["\uff5e", "\U0001F600"]), ("sort_keys", [["b", "A", "a", "B"]]),
           ("dedupe_keys", [["Foo", "foo ", "FOO", "bar"]]), ("initials", ["hello big \U0001F600 world"]), ("initials", ["  \u00e9clair  au chocolat "])]
    for t in ["", " ", "A", "abc", "ABC", "AbC dEf", "  lead", "trail  ", "a\t\tb", "a\r\nb", "\u00a0a\u00a0", "a\u2003b", "\u00c9\u00e9", "\u00df", "\u1e9e", "\u0130", "\u212a", "K", "\U0001F600 A", "a\u0301", "Z z", "MIXED\tcase\nLINES  here", "\x0b\x0c"]:
        out.append(("fold_key", [t]))
        out.append(("initials", [t]))
    for a, b in [("a", "a"), ("a", "A"), ("a", "b"), ("b", "a"), ("", ""), ("", "a"), ("a", ""), ("ab", "abc"), ("abc", "ab"), ("\uff5e", "\U0001F600"), ("\U0001F600", "\uff5e"), ("\ud7ff", "\ue000"), ("\uffff", "\U00010000"),
                 ("\U00010000", "\uffff"), ("\u00e9", "E"), ("\u00c9", "\u00e9"), ("  x  y ", "x y"), ("x  y", "x\ty"), ("a\u00a0b", "a b"), ("\uff5e a", "\U0001F600 a")]:
        out.append(("cmp_keys", [a, b]))
    for xs in [[], ["b", "a", "c"], ["B", "a", "C", "b"], ["\U0001F600", "\uff5e", "z", "\u00e9", "e"], ["x y", "x  y", "X Y", "x\ty"], ["\u00c9", "\u00e9", "E", "e"], ["\uffff", "\U00010000", "\ud7ff", "\ue000"], ["a", "A", "a ", " a"]]:
        out.append(("sort_keys", [xs]))
        out.append(("dedupe_keys", [xs]))
    for _ in range(40):
        xs = ["".join(rng.choice(pieces) for _ in range(rng.randint(0, 5))) for _ in range(rng.randint(0, 8))]
        out.append(("sort_keys", [xs]))
        out.append(("dedupe_keys", [xs]))
        out.append(("fold_key", [xs[0] if xs else ""]))
        out.append(("initials", [" ".join(xs)]))
        if len(xs) >= 2:
            out.append(("cmp_keys", [xs[0], xs[1]]))
    return out


AF = PortLib(
    slug="ascii-fold",
    title="catalogue key folding and ordering",
    blurb="A museum catalogue builds index keys from free-text titles and must order them exactly the same way in every service that touches them.",
    spec=AF_SPEC,
    fns=AF_FNS,
    impls={"javascript": {"src/ascii_fold.js": AF_JS}, "python": {"ascii_fold.py": AF_PY}, "go": {"asciifold.go": AF_GO}},
    cases=af_cases,
    difficulty=3,
    traps=["ASCII-only case folding", "code point order vs UTF-16 order", "narrow whitespace definition", "astral first character", "stable sort"],
    tags=["unicode", "collation"],
    pairs=[("javascript", "python", "full"), ("python", "go", "full"), ("go", "javascript", "stub"), ("javascript", "go", "stub")],
)
register_port(AF, __name__)

# ======================================================================================================================
# fixed-cols: fixed-width records
# ======================================================================================================================

FC_SPEC = dd('''
    A mainframe export writes one record per line with **fixed-width columns**. A *layout* is a list of `name:width`
    strings: `name` matches `[a-z][a-z0-9_]*`, `width` is 1 to 99 (decimal digits, no sign, no leading zero) and names are
    unique; an empty layout or any other entry is an error. Widths count **Unicode code points**, not bytes or UTF-16 units.

    * `total_width(layout)` is the sum of the widths.
    * `column_offsets(layout)` is the start offset (in code points) of every column.
    * `format_row(layout, values)` pads every value on the right with spaces to its column width and concatenates the
      columns. The number of values must equal the number of columns, no value may be longer than its column, and no value
      may contain a line feed or carriage return (error otherwise).
    * `parse_row(layout, line)` is the inverse: `line` must be exactly `total_width` code points and contain no `\\n` or
      `\\r`; each field is the column's text with the **trailing spaces** removed (leading spaces are kept).
    * `field(layout, line, name)` is the parsed value of one named column; an unknown name is an error (and so is a bad
      layout or line).
''')

FC_FNS = [
    Fn("total_width", [("layout", "list<str>")], "int", err=True),
    Fn("column_offsets", [("layout", "list<str>")], "list<int>", err=True),
    Fn("format_row", [("layout", "list<str>"), ("values", "list<str>")], "str", err=True),
    Fn("parse_row", [("layout", "list<str>"), ("line", "str")], "list<str>", err=True),
    Fn("field", [("layout", "list<str>"), ("line", "str"), ("name", "str")], "str", err=True),
]

FC_PY = dd(r'''
import re

_ENTRY = re.compile(r"([a-z][a-z0-9_]*):([1-9][0-9]?)")


def _layout(layout):
    if not layout:
        raise ValueError("empty layout")
    cols, seen = [], set()
    for e in layout:
        m = _ENTRY.fullmatch(e)
        if not m or m.group(1) in seen:
            raise ValueError("bad layout entry: %r" % e)
        seen.add(m.group(1))
        cols.append((m.group(1), int(m.group(2))))
    return cols


def total_width(layout):
    return sum(w for _, w in _layout(layout))


def column_offsets(layout):
    out, pos = [], 0
    for _, w in _layout(layout):
        out.append(pos)
        pos += w
    return out


def format_row(layout, values):
    cols = _layout(layout)
    if len(values) != len(cols):
        raise ValueError("wrong number of values")
    out = []
    for (_, w), v in zip(cols, values):
        if len(v) > w or "\n" in v or "\r" in v:
            raise ValueError("value does not fit")
        out.append(v + " " * (w - len(v)))
    return "".join(out)


def parse_row(layout, line):
    cols = _layout(layout)
    if len(line) != sum(w for _, w in cols) or "\n" in line or "\r" in line:
        raise ValueError("bad line")
    out, pos = [], 0
    for _, w in cols:
        out.append(line[pos:pos + w].rstrip(" "))
        pos += w
    return out


def field(layout, line, name):
    cols = _layout(layout)
    values = parse_row(layout, line)
    for (n, _), v in zip(cols, values):
        if n == name:
            return v
    raise KeyError(name)
''')

FC_JAVA = dd(r'''
import java.util.*;

public final class FixedCols {
    private FixedCols() {}

    private static final class Col {
        final String name;
        final int width;
        Col(String n, int w) { name = n; width = w; }
    }

    private static List<Col> layout(List<String> layout) {
        if (layout.isEmpty()) throw new IllegalArgumentException("empty layout");
        List<Col> cols = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (String e : layout) {
            int colon = e.indexOf(':');
            if (colon < 1) throw new IllegalArgumentException("bad layout entry");
            String name = e.substring(0, colon);
            String w = e.substring(colon + 1);
            if (!(name.charAt(0) >= 'a' && name.charAt(0) <= 'z')) throw new IllegalArgumentException("bad name");
            for (int i = 1; i < name.length(); i++) {
                char c = name.charAt(i);
                if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_')) throw new IllegalArgumentException("bad name");
            }
            if (w.length() < 1 || w.length() > 2 || w.charAt(0) < '1' || w.charAt(0) > '9') throw new IllegalArgumentException("bad width");
            for (int i = 0; i < w.length(); i++) if (w.charAt(i) < '0' || w.charAt(i) > '9') throw new IllegalArgumentException("bad width");
            if (!seen.add(name)) throw new IllegalArgumentException("duplicate name");
            cols.add(new Col(name, Integer.parseInt(w)));
        }
        return cols;
    }

    private static int[] points(String s) { return s.codePoints().toArray(); }

    private static String str(int[] cps, int from, int to) { return new String(cps, from, to - from); }

    public static long totalWidth(List<String> layout) {
        long t = 0;
        for (Col c : layout(layout)) t += c.width;
        return t;
    }

    public static List<Long> columnOffsets(List<String> layout) {
        List<Long> out = new ArrayList<>();
        long pos = 0;
        for (Col c : layout(layout)) {
            out.add(pos);
            pos += c.width;
        }
        return out;
    }

    public static String formatRow(List<String> layout, List<String> values) {
        List<Col> cols = layout(layout);
        if (values.size() != cols.size()) throw new IllegalArgumentException("wrong number of values");
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < cols.size(); i++) {
            String v = values.get(i);
            int n = v.codePointCount(0, v.length());
            if (n > cols.get(i).width || v.indexOf('\n') >= 0 || v.indexOf('\r') >= 0) throw new IllegalArgumentException("value does not fit");
            b.append(v);
            for (int k = n; k < cols.get(i).width; k++) b.append(' ');
        }
        return b.toString();
    }

    public static List<String> parseRow(List<String> layout, String line) {
        List<Col> cols = layout(layout);
        int[] cps = points(line);
        int total = 0;
        for (Col c : cols) total += c.width;
        if (cps.length != total || line.indexOf('\n') >= 0 || line.indexOf('\r') >= 0) throw new IllegalArgumentException("bad line");
        List<String> out = new ArrayList<>();
        int pos = 0;
        for (Col c : cols) {
            int end = pos + c.width;
            int trimmed = end;
            while (trimmed > pos && cps[trimmed - 1] == ' ') trimmed--;
            out.add(str(cps, pos, trimmed));
            pos = end;
        }
        return out;
    }

    public static String field(List<String> layout, String line, String name) {
        List<Col> cols = layout(layout);
        List<String> values = parseRow(layout, line);
        for (int i = 0; i < cols.size(); i++) if (cols.get(i).name.equals(name)) return values.get(i);
        throw new NoSuchElementException(name);
    }
}
''')

FC_RS = dd(r'''
struct Col {
    name: String,
    width: usize,
}

fn layout(entries: &[String]) -> Result<Vec<Col>, String> {
    if entries.is_empty() {
        return Err("empty layout".to_string());
    }
    let mut cols: Vec<Col> = Vec::new();
    for e in entries {
        let (name, w) = e.split_once(':').ok_or("bad layout entry")?;
        let nb = name.as_bytes();
        let name_ok = !nb.is_empty()
            && nb[0].is_ascii_lowercase()
            && nb.iter().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == b'_');
        let wb = w.as_bytes();
        let width_ok = (wb.len() == 1 || wb.len() == 2) && wb[0] >= b'1' && wb.iter().all(|c| c.is_ascii_digit());
        if !name_ok || !width_ok || cols.iter().any(|c| c.name == name) {
            return Err(format!("bad layout entry {:?}", e));
        }
        cols.push(Col { name: name.to_string(), width: w.parse().unwrap() });
    }
    Ok(cols)
}

pub fn total_width(entries: &[String]) -> Result<i64, String> {
    Ok(layout(entries)?.iter().map(|c| c.width as i64).sum())
}

pub fn column_offsets(entries: &[String]) -> Result<Vec<i64>, String> {
    let mut pos = 0i64;
    let mut out = Vec::new();
    for c in layout(entries)? {
        out.push(pos);
        pos += c.width as i64;
    }
    Ok(out)
}

pub fn format_row(entries: &[String], values: &[String]) -> Result<String, String> {
    let cols = layout(entries)?;
    if cols.len() != values.len() {
        return Err("wrong number of values".to_string());
    }
    let mut out = String::new();
    for (c, v) in cols.iter().zip(values) {
        let n = v.chars().count();
        if n > c.width || v.contains('\n') || v.contains('\r') {
            return Err("value does not fit".to_string());
        }
        out.push_str(v);
        out.push_str(&" ".repeat(c.width - n));
    }
    Ok(out)
}

pub fn parse_row(entries: &[String], line: &str) -> Result<Vec<String>, String> {
    let cols = layout(entries)?;
    let chars: Vec<char> = line.chars().collect();
    let total: usize = cols.iter().map(|c| c.width).sum();
    if chars.len() != total || line.contains('\n') || line.contains('\r') {
        return Err("bad line".to_string());
    }
    let mut pos = 0;
    let mut out = Vec::new();
    for c in &cols {
        let cell: String = chars[pos..pos + c.width].iter().collect();
        out.push(cell.trim_end_matches(' ').to_string());
        pos += c.width;
    }
    Ok(out)
}

pub fn field(entries: &[String], line: &str, name: &str) -> Result<String, String> {
    let cols = layout(entries)?;
    let values = parse_row(entries, line)?;
    for (c, v) in cols.iter().zip(values) {
        if c.name == name {
            return Ok(v);
        }
    }
    Err(format!("unknown column {:?}", name))
}
''')


def fc_cases(rng):
    L1 = ["id:4", "name:10", "city:8"]
    L2 = ["a:1", "b_2:3", "c3:2"]
    out = [("total_width", [L1]), ("column_offsets", [L1]), ("format_row", [L1, ["7", "Ann", "Oslo"]]), ("parse_row", [L1, "7   Ann       Oslo    "]), ("field", [L1, "7   Ann       Oslo    ", "city"]),
           ("format_row", [L2, ["x", "caf\u00e9", "ab"]])]
    bad_layouts = [[], ["a"], ["a:"], [":3"], ["A:3"], ["a:0"], ["a:00"], ["a:03"], ["a:100"], ["a:+3"], ["a:3", "a:4"], ["a:3b"], ["a b:3"], ["1a:3"], ["a-b:3"], ["a:3:4"], ["a:\u0663"], ["\u00e9:3"], [" a:3"], ["a:3 "], ["a:3\n"]]
    for lay in [L1, L2, ["x:99"], ["x:1"], ["a:5", "b:5", "c:5", "d:5"], ["k_1:12", "v:7"]]:
        out.append(("total_width", [lay]))
        out.append(("column_offsets", [lay]))
    for lay in bad_layouts:
        out.append(("total_width", [lay]))
        out.append(("column_offsets", [lay]))
        out.append(("format_row", [lay, []]))
    rows = [(L1, ["1", "Bob", "Rome"]), (L1, ["1234", "ABCDEFGHIJ", "12345678"]), (L1, ["", "", ""]), (L1, ["12345", "x", "y"]), (L1, ["1", "x"]), (L1, ["1", "x", "y", "z"]), (L1, ["1", "a\nb", "c"]), (L1, ["1", "a\rb", "c"]),
            (L2, ["z", "\u00e9\u00e8\u00ea", "\U0001F600\U0001F600"]), (L2, ["\U0001F600", "ab", "c"]), (L2, ["\U0001F600\U0001F600", "ab", "c"]), (L2, ["a", "\u4e2d\u6587\u6587", "x"]), (L2, ["a", "\u4e2d\u6587\u6587\u6587", "x"]),
            (L1, [" 1", " Bob", "  Rome"]), (L1, ["1 ", "Bob ", "Rome "]), (["w:1"], ["\u00e9"]), (["w:2"], ["\U0001F600"]), (["w:2"], ["e\u0301"])]
    for lay, vals in rows:
        out.append(("format_row", [lay, vals]))
    lines = [(L1, "1   Bob       Rome    "), (L1, "1   Bob       Rome   "), (L1, "1   Bob       Rome     "), (L1, ""), (L1, "    " + " " * 10 + " " * 8), (L1, " 1  Bob       Rome    "), (L1, "1   Bob       Rome   \n"), (L1, "1   Bob   \n   Rome    "),
             (L1, "1\r  Bob       Rome    "), (L2, "z\u00e9\u00e8\u00eaab"), (L2, "z\u00e9\u00e8\u00ea\U0001F600"), (L2, "z\U0001F600\U0001F600\U0001F600\U0001F600\U0001F600"), (L2, "x  a  "), (L2, "xabc  "), (L2, "xab   "), (["t:3"], "a b"), (["t:3"], "  b"),
             (["t:3"], "a  "), (["t:2"], "e\u0301"), (["t:2"], "\U0001F600"), (["t:1"], "\U0001F600"), (["a:2", "b:2"], "\U0001F600\u4e2d ")]
    for lay, line in lines:
        out.append(("parse_row", [lay, line]))
        for nm in ["id", "name", "city", "a", "b_2", "c3", "t", "b", "zzz"]:
            if rng.random() < 0.3:
                out.append(("field", [lay, line, nm]))
    for lay, line, nm in [(L1, "1   Bob       Rome    ", "id"), (L1, "1   Bob       Rome    ", "name"), (L1, "1   Bob       Rome    ", "city"), (L1, "1   Bob       Rome    ", "zip"), (L1, "1   Bob       Rome    ", "ID"),
                          (L1, "short", "id"), ([], "x", "id"), (L2, "x  a  ", "b_2"), (L2, "x  a  ", "c3")]:
        out.append(("field", [lay, line, nm]))
    pool = ["a", "b", "\u00e9", "\U0001F600", "\u4e2d", " ", "e\u0301", "Z", "9"]
    for _ in range(30):
        ncol = rng.randint(1, 4)
        widths = [rng.randint(1, 6) for _ in range(ncol)]
        lay = [f"c{i}:{w}" for i, w in enumerate(widths)]
        vals = ["".join(rng.choice(pool) for _ in range(rng.randint(0, w))) for w in widths]
        out.append(("format_row", [lay, vals]))
        padded = "".join(v + " " * (w - len(v)) for v, w in zip(vals, widths))
        out.append(("parse_row", [lay, padded]))
        out.append(("column_offsets", [lay]))
    return out


FC = PortLib(
    slug="fixed-cols",
    title="fixed-width record columns",
    blurb="A nightly export from a legacy ledger system uses fixed-width text records, and the new tooling needs to read and write them identically.",
    spec=FC_SPEC,
    fns=FC_FNS,
    impls={"python": {"fixed_cols.py": FC_PY}, "java": {"FixedCols.java": FC_JAVA}, "rust": {"src/lib.rs": FC_RS}},
    cases=fc_cases,
    difficulty=2,
    traps=["widths in code points (not bytes / UTF-16 units)", "right trim of spaces only", "strict layout grammar"],
    tags=["unicode", "fixed-width"],
    pairs=[("python", "java", "full"), ("java", "rust", "full"), ("rust", "python", "stub"), ("python", "rust", "stub")],
)
register_port(FC, __name__)
