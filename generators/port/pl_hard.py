"""Hard port libraries (difficulty 5): a settings-file parser with quoting rules (Python/TypeScript/Go) and a glob matcher with braces and classes over code points."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

# ======================================================================================================================
# kv-lines: sections, bare and quoted values, comments, escapes
# ======================================================================================================================

KV_SPEC = dd('''
    A settings text in a small line-based format. Text is a sequence of Unicode code points.

    **Lines.** A U+FEFF at the very start of the text is ignored. Lines end at `\\n`; a `\\r` that is the last character of a line is dropped (CRLF files; the last line needs no line end, and a text that ends with `\\n` has no extra empty line).
    Any control character anywhere in the text is an error: U+0000..U+001F except TAB, and U+007F (a `\\r` in the middle of a line included). **Blanks** are exactly space and TAB: other white space (U+00A0, U+0085, U+2003, ...) is ordinary text.
    Blanks at the start and the end of a line are ignored. A line that is empty or starts with `#` is skipped. Every other line is a section header or an entry; anything else is an error.

    **Section header** `[name]`: `name` is `[a-z][a-z0-9_-]*`. Only blanks or a `#` comment may follow the `]`. From then on every entry key is prefixed with `name.` (until the next header; there is no way back to "no section").

    **Entry** `key = value`: the key is lower-case letters, digits, `_` and `-`, starting with a letter, in one or more parts separated by single dots (`a`, `a.b-c`, `x1.y_2` are fine; `A`, `1a`, `a.`, `.a`, `a..b` are not). Blanks around `=` are optional. The full key is `section.key` inside a section.

    **Values.** If the first non-blank character after `=` is `"` the value is a *quoted string*: it ends at the next unescaped `"`, and after that only blanks or a `#` comment may follow. Escapes: `\\n`, `\\t`, `\\r`, `\\"`, `\\\\` and `\\u{X}` with 1 to 6 hex digits
    (either case) naming a code point up to U+10FFFF that is not a surrogate (U+D800..U+DFFF). Any other escape, a missing closing quote or a dangling backslash is an error. A raw TAB is fine inside the quotes.
    Otherwise the value is *bare*: the text after the `=` up to the first `#` that is directly preceded by a space or TAB (looking at the text after the `=`; a `#` that is the very first character after the `=` is not preceded by anything), or up to the end of the line,
    with blanks trimmed at both ends. So `k=#x` is `#x`, `k = #x` is empty, `u=http://h/#top` keeps its `#top`, `a = b #c` is `b`. A bare value may be empty and may contain quotes and backslashes (no escapes are processed).

    **Functions.** Every function parses the whole text first; any syntax error makes the call fail (also when the asked key would have been fine). Duplicate keys are allowed.
    `count(text)` is the number of entries. `keys(text)` lists the distinct full keys in order of first appearance. `has(text, key)` tells whether a full key is present. `get(text, key)` is the value of the *last* entry with that key (an error when there is none).
    `get_all(text, key)` lists all values of the key in order (empty when there is none). `get_int(text, key)` is `get`, which must be a decimal integer: an optional `-`, then `0` or digits without a leading zero, and `|n| <= 2^53` (9007199254740992); anything else is an error.
    `dump(text)` rewrites the entries in file order, one per line, as `full.key = "escaped"` followed by `\\n`: the value is written in quotes with `\\\\`, `\\"`, `\\n`, `\\t`, `\\r` for those characters, `\\u{x}` (lower-case hex, no padding) for every other control character
    (U+0000..U+001F, U+007F) and everything else verbatim. A text without entries dumps to the empty string.
''')

KV_FNS = [
    Fn("count", [("text", "str")], "int", err=True),
    Fn("keys", [("text", "str")], "list<str>", err=True),
    Fn("has", [("text", "str"), ("key", "str")], "bool", err=True),
    Fn("get", [("text", "str"), ("key", "str")], "str", err=True),
    Fn("get_all", [("text", "str"), ("key", "str")], "list<str>", err=True),
    Fn("get_int", [("text", "str"), ("key", "str")], "int", err=True),
    Fn("dump", [("text", "str")], "str", err=True),
]

KV_PY = dd(r'''
import re

_KEY = re.compile(r"[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)*")
_SECTION = re.compile(r"[a-z][a-z0-9_-]*")
_HEX = re.compile(r"[0-9a-fA-F]{1,6}")
_INT = re.compile(r"-?(?:0|[1-9][0-9]{0,15})")
_BLANKS = " \t"


def _lines(text):
    if text.startswith("\ufeff"):
        text = text[1:]
    parts = text.split("\n")
    if parts[-1] == "":
        parts.pop()
    return [p[:-1] if p.endswith("\r") else p for p in parts]


def _value(rest):
    body = rest.lstrip(_BLANKS)
    if body.startswith('"'):
        out = []
        i = 1
        while True:
            if i >= len(body):
                raise ValueError("unterminated string")
            c = body[i]
            if c == '"':
                i += 1
                break
            if c != "\\":
                out.append(c)
                i += 1
                continue
            i += 1
            if i >= len(body):
                raise ValueError("dangling backslash")
            e = body[i]
            if e in "ntr":
                out.append({"n": "\n", "t": "\t", "r": "\r"}[e])
                i += 1
            elif e in '"\\':
                out.append(e)
                i += 1
            elif e == "u":
                if body[i + 1:i + 2] != "{":
                    raise ValueError("bad unicode escape")
                j = body.find("}", i + 2)
                if j < 0 or not _HEX.fullmatch(body[i + 2:j]):
                    raise ValueError("bad unicode escape")
                cp = int(body[i + 2:j], 16)
                if cp > 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
                    raise ValueError("bad code point")
                out.append(chr(cp))
                i = j + 1
            else:
                raise ValueError("unknown escape")
        tail = body[i:].strip(_BLANKS)
        if tail and tail[0] != "#":
            raise ValueError("junk after string")
        return "".join(out)
    cut = len(rest)
    for i in range(1, len(rest)):
        if rest[i] == "#" and rest[i - 1] in _BLANKS:
            cut = i
            break
    return rest[:cut].strip(_BLANKS)


def _parse(text):
    section = None
    entries = []
    for raw in _lines(text):
        if any((ord(c) < 32 and c != "\t") or ord(c) == 127 for c in raw):
            raise ValueError("control character")
        line = raw.strip(_BLANKS)
        if not line or line[0] == "#":
            continue
        if line[0] == "[":
            end = line.find("]")
            if end < 0 or not _SECTION.fullmatch(line[1:end]):
                raise ValueError("bad section header")
            rest = line[end + 1:].strip(_BLANKS)
            if rest and rest[0] != "#":
                raise ValueError("junk after section header")
            section = line[1:end]
            continue
        m = _KEY.match(line)
        if not m:
            raise ValueError("bad key")
        rest = line[m.end():].lstrip(_BLANKS)
        if not rest.startswith("="):
            raise ValueError("missing =")
        key = m.group(0) if section is None else section + "." + m.group(0)
        entries.append((key, _value(rest[1:])))
    return entries


def count(text):
    return len(_parse(text))


def keys(text):
    seen = []
    for k, _ in _parse(text):
        if k not in seen:
            seen.append(k)
    return seen


def has(text, key):
    return any(k == key for k, _ in _parse(text))


def get(text, key):
    found = [v for k, v in _parse(text) if k == key]
    if not found:
        raise KeyError(key)
    return found[-1]


def get_all(text, key):
    return [v for k, v in _parse(text) if k == key]


def get_int(text, key):
    v = get(text, key)
    if not _INT.fullmatch(v):
        raise ValueError("not an integer")
    n = int(v)
    if abs(n) > 2 ** 53:
        raise ValueError("integer out of range")
    return n


def _esc(v):
    out = []
    for c in v:
        o = ord(c)
        if c == "\\":
            out.append("\\\\")
        elif c == '"':
            out.append('\\"')
        elif c == "\n":
            out.append("\\n")
        elif c == "\t":
            out.append("\\t")
        elif c == "\r":
            out.append("\\r")
        elif o < 32 or o == 127:
            out.append("\\u{%x}" % o)
        else:
            out.append(c)
    return "".join(out)


def dump(text):
    return "".join('%s = "%s"\n' % (k, _esc(v)) for k, v in _parse(text))
''')

KV_TS = dd(r'''
const KEY = /^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)*/;
const SECTION = /^[a-z][a-z0-9_-]*$/;
const HEX = /^[0-9a-fA-F]{1,6}$/;
const INT = /^-?(?:0|[1-9][0-9]{0,15})$/;

function isBlank(c: string): boolean {
  return c === ' ' || c === '\t';
}

function lstrip(s: string): string {
  let a = 0;
  while (a < s.length && isBlank(s[a])) a++;
  return s.slice(a);
}

function strip(s: string): string {
  let a = 0;
  let b = s.length;
  while (a < b && isBlank(s[a])) a++;
  while (b > a && isBlank(s[b - 1])) b--;
  return s.slice(a, b);
}

function lines(input: string): string[] {
  let text = input;
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const parts = text.split('\n');
  if (parts[parts.length - 1] === '') parts.pop();
  return parts.map((p) => (p.endsWith('\r') ? p.slice(0, -1) : p));
}

function parseValue(rest: string): string {
  const body = lstrip(rest);
  if (body.startsWith('"')) {
    const out: string[] = [];
    let i = 1;
    for (;;) {
      if (i >= body.length) throw new Error('unterminated string');
      const c = body[i];
      if (c === '"') {
        i++;
        break;
      }
      if (c !== '\\') {
        out.push(c);
        i++;
        continue;
      }
      i++;
      if (i >= body.length) throw new Error('dangling backslash');
      const e = body[i];
      if (e === 'n') {
        out.push('\n');
        i++;
      } else if (e === 't') {
        out.push('\t');
        i++;
      } else if (e === 'r') {
        out.push('\r');
        i++;
      } else if (e === '"' || e === '\\') {
        out.push(e);
        i++;
      } else if (e === 'u') {
        if (body[i + 1] !== '{') throw new Error('bad unicode escape');
        const j = body.indexOf('}', i + 2);
        if (j < 0 || !HEX.test(body.slice(i + 2, j))) throw new Error('bad unicode escape');
        const cp = parseInt(body.slice(i + 2, j), 16);
        if (cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff)) throw new Error('bad code point');
        out.push(String.fromCodePoint(cp));
        i = j + 1;
      } else {
        throw new Error('unknown escape');
      }
    }
    const tail = strip(body.slice(i));
    if (tail !== '' && tail[0] !== '#') throw new Error('junk after string');
    return out.join('');
  }
  let cut = rest.length;
  for (let i = 1; i < rest.length; i++) {
    if (rest[i] === '#' && isBlank(rest[i - 1])) {
      cut = i;
      break;
    }
  }
  return strip(rest.slice(0, cut));
}

function parse(text: string): Array<[string, string]> {
  let section: string | null = null;
  const entries: Array<[string, string]> = [];
  for (const raw of lines(text)) {
    for (let i = 0; i < raw.length; i++) {
      const o = raw.charCodeAt(i);
      if ((o < 32 && o !== 9) || o === 127) throw new Error('control character');
    }
    const line = strip(raw);
    if (line === '' || line[0] === '#') continue;
    if (line[0] === '[') {
      const end = line.indexOf(']');
      if (end < 0 || !SECTION.test(line.slice(1, end))) throw new Error('bad section header');
      const rest = strip(line.slice(end + 1));
      if (rest !== '' && rest[0] !== '#') throw new Error('junk after section header');
      section = line.slice(1, end);
      continue;
    }
    const m = KEY.exec(line);
    if (!m) throw new Error('bad key');
    const rest = lstrip(line.slice(m[0].length));
    if (!rest.startsWith('=')) throw new Error('missing =');
    const key = section === null ? m[0] : section + '.' + m[0];
    entries.push([key, parseValue(rest.slice(1))]);
  }
  return entries;
}

export function count(text: string): number {
  return parse(text).length;
}

export function keys(text: string): string[] {
  const seen: string[] = [];
  for (const [k] of parse(text)) {
    if (!seen.includes(k)) seen.push(k);
  }
  return seen;
}

export function has(text: string, key: string): boolean {
  return parse(text).some(([k]) => k === key);
}

export function getAll(text: string, key: string): string[] {
  return parse(text).filter(([k]) => k === key).map(([, v]) => v);
}

export function get(text: string, key: string): string {
  const found = getAll(text, key);
  if (found.length === 0) throw new Error('no such key');
  return found[found.length - 1];
}

export function getInt(text: string, key: string): number {
  const v = get(text, key);
  if (!INT.test(v)) throw new Error('not an integer');
  const n = BigInt(v);
  const limit = BigInt(9007199254740992);
  if (n > limit || n < -limit) throw new Error('integer out of range');
  return Number(n);
}

function esc(v: string): string {
  let out = '';
  for (const c of v) {
    const o = c.codePointAt(0) as number;
    if (c === '\\') out += '\\\\';
    else if (c === '"') out += '\\"';
    else if (c === '\n') out += '\\n';
    else if (c === '\t') out += '\\t';
    else if (c === '\r') out += '\\r';
    else if (o < 32 || o === 127) out += '\\u{' + o.toString(16) + '}';
    else out += c;
  }
  return out;
}

export function dump(text: string): string {
  return parse(text).map(([k, v]) => k + ' = "' + esc(v) + '"\n').join('');
}
''')

KV_GO = dd(r'''
package kvlines

import (
	"errors"
	"strconv"
	"strings"
	"unicode/utf8"
)

type entry struct{ key, value string }

var errSyntax = errors.New("syntax error")

func isBlank(c byte) bool { return c == ' ' || c == '\t' }
func isLower(c byte) bool { return c >= 'a' && c <= 'z' }
func isDigit(c byte) bool { return c >= '0' && c <= '9' }
func isWord(c byte) bool  { return isLower(c) || isDigit(c) || c == '_' || c == '-' }
func isHex(c byte) bool {
	return isDigit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')
}

func lstrip(s string) string {
	a := 0
	for a < len(s) && isBlank(s[a]) {
		a++
	}
	return s[a:]
}

func strip(s string) string {
	a, b := 0, len(s)
	for a < b && isBlank(s[a]) {
		a++
	}
	for b > a && isBlank(s[b-1]) {
		b--
	}
	return s[a:b]
}

// scanKey returns the length of the key at the start of s (0 when there is none).
func scanKey(s string) int {
	if len(s) == 0 || !isLower(s[0]) {
		return 0
	}
	i := 1
	for i < len(s) && isWord(s[i]) {
		i++
	}
	for i < len(s) && s[i] == '.' {
		j := i + 1
		for j < len(s) && isWord(s[j]) {
			j++
		}
		if j == i+1 {
			break
		}
		i = j
	}
	return i
}

func validSection(s string) bool {
	if len(s) == 0 || !isLower(s[0]) {
		return false
	}
	for i := 1; i < len(s); i++ {
		if !isWord(s[i]) {
			return false
		}
	}
	return true
}

func parseValue(rest string) (string, error) {
	body := lstrip(rest)
	if strings.HasPrefix(body, "\"") {
		var out []byte
		i := 1
		for {
			if i >= len(body) {
				return "", errSyntax
			}
			c := body[i]
			if c == '"' {
				i++
				break
			}
			if c != '\\' {
				out = append(out, c)
				i++
				continue
			}
			i++
			if i >= len(body) {
				return "", errSyntax
			}
			switch e := body[i]; e {
			case 'n':
				out = append(out, '\n')
				i++
			case 't':
				out = append(out, '\t')
				i++
			case 'r':
				out = append(out, '\r')
				i++
			case '"', '\\':
				out = append(out, e)
				i++
			case 'u':
				if i+1 >= len(body) || body[i+1] != '{' {
					return "", errSyntax
				}
				j := strings.IndexByte(body[i+2:], '}')
				if j < 0 {
					return "", errSyntax
				}
				digits := body[i+2 : i+2+j]
				if len(digits) < 1 || len(digits) > 6 {
					return "", errSyntax
				}
				for k := 0; k < len(digits); k++ {
					if !isHex(digits[k]) {
						return "", errSyntax
					}
				}
				cp, _ := strconv.ParseUint(digits, 16, 32)
				if cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF) {
					return "", errSyntax
				}
				out = utf8.AppendRune(out, rune(cp))
				i = i + 2 + j + 1
			default:
				return "", errSyntax
			}
		}
		tail := strip(body[i:])
		if tail != "" && tail[0] != '#' {
			return "", errSyntax
		}
		return string(out), nil
	}
	cut := len(rest)
	for i := 1; i < len(rest); i++ {
		if rest[i] == '#' && isBlank(rest[i-1]) {
			cut = i
			break
		}
	}
	return strip(rest[:cut]), nil
}

func parse(text string) ([]entry, error) {
	text = strings.TrimPrefix(text, "\uFEFF")
	parts := strings.Split(text, "\n")
	if parts[len(parts)-1] == "" {
		parts = parts[:len(parts)-1]
	}
	section := ""
	inSection := false
	var entries []entry
	for _, raw := range parts {
		raw = strings.TrimSuffix(raw, "\r")
		for i := 0; i < len(raw); i++ {
			if (raw[i] < 32 && raw[i] != '\t') || raw[i] == 127 {
				return nil, errSyntax
			}
		}
		line := strip(raw)
		if line == "" || line[0] == '#' {
			continue
		}
		if line[0] == '[' {
			end := strings.IndexByte(line, ']')
			if end < 0 || !validSection(line[1:end]) {
				return nil, errSyntax
			}
			rest := strip(line[end+1:])
			if rest != "" && rest[0] != '#' {
				return nil, errSyntax
			}
			section = line[1:end]
			inSection = true
			continue
		}
		n := scanKey(line)
		if n == 0 {
			return nil, errSyntax
		}
		rest := lstrip(line[n:])
		if !strings.HasPrefix(rest, "=") {
			return nil, errSyntax
		}
		key := line[:n]
		if inSection {
			key = section + "." + key
		}
		v, err := parseValue(rest[1:])
		if err != nil {
			return nil, err
		}
		entries = append(entries, entry{key, v})
	}
	return entries, nil
}

func Count(text string) (int64, error) {
	es, err := parse(text)
	return int64(len(es)), err
}

func Keys(text string) ([]string, error) {
	es, err := parse(text)
	if err != nil {
		return nil, err
	}
	seen := map[string]bool{}
	out := []string{}
	for _, e := range es {
		if !seen[e.key] {
			seen[e.key] = true
			out = append(out, e.key)
		}
	}
	return out, nil
}

func Has(text, key string) (bool, error) {
	es, err := parse(text)
	if err != nil {
		return false, err
	}
	for _, e := range es {
		if e.key == key {
			return true, nil
		}
	}
	return false, nil
}

func GetAll(text, key string) ([]string, error) {
	es, err := parse(text)
	if err != nil {
		return nil, err
	}
	out := []string{}
	for _, e := range es {
		if e.key == key {
			out = append(out, e.value)
		}
	}
	return out, nil
}

func Get(text, key string) (string, error) {
	all, err := GetAll(text, key)
	if err != nil {
		return "", err
	}
	if len(all) == 0 {
		return "", errors.New("no such key")
	}
	return all[len(all)-1], nil
}

func GetInt(text, key string) (int64, error) {
	v, err := Get(text, key)
	if err != nil {
		return 0, err
	}
	digits := strings.TrimPrefix(v, "-")
	if len(digits) < 1 || len(digits) > 16 || (len(digits) > 1 && digits[0] == '0') {
		return 0, errors.New("not an integer")
	}
	for i := 0; i < len(digits); i++ {
		if !isDigit(digits[i]) {
			return 0, errors.New("not an integer")
		}
	}
	n, err := strconv.ParseInt(v, 10, 64)
	if err != nil {
		return 0, err
	}
	if n > 1<<53 || n < -(1<<53) {
		return 0, errors.New("integer out of range")
	}
	return n, nil
}

func Dump(text string) (string, error) {
	es, err := parse(text)
	if err != nil {
		return "", err
	}
	var b strings.Builder
	for _, e := range es {
		b.WriteString(e.key)
		b.WriteString(" = \"")
		for i := 0; i < len(e.value); i++ {
			c := e.value[i]
			switch {
			case c == '\\':
				b.WriteString("\\\\")
			case c == '"':
				b.WriteString("\\\"")
			case c == '\n':
				b.WriteString("\\n")
			case c == '\t':
				b.WriteString("\\t")
			case c == '\r':
				b.WriteString("\\r")
			case c < 32 || c == 127:
				b.WriteString("\\u{" + strconv.FormatInt(int64(c), 16) + "}")
			default:
				b.WriteByte(c)
			}
		}
		b.WriteString("\"\n")
	}
	return b.String(), nil
}
''')

KV_KEYS = ["name", "port", "a.b", "x-1", "retry_count", "path.to.file", "k", "timeout", "log.level", "e1.f2.g3"]
KV_SECTIONS = ["db", "web-ui", "x_1", "cache", "s"]
KV_VALUES = ["", "plain", "two words", "http://h/#top", "a#b", "  padded  ", "42", "-7", "0", "007", "1e3", "9007199254740993", "-9007199254740992", "9007199254740992", "tab\there", 'say "hi"', "back\\slash",
             "caf\u00e9", "\U0001f600 smile", "\u00a0nbsp\u00a0", "\u2003em", "k=v", "[x]", "# not comment", "x #y", "line1\nline2", "cr\rhere", "nul\x00byte", "\x7f", "\u2028sep", "\ufefftail", "\u00e9\u0301", "-0", "+5", "1_000", "12345678901234567"]
KV_HAND = [
    "", "\n", "\r\n", "# only a comment\n", "  \t \n", "a = 1", "a = 1\n", "a = 1\r\n", "a = 1\r", "a=1\n\nb=2\n", "\ufeffa = 1\n", "\ufeff", "\ufeff\ufeffa=1", "a = 1\rb = 2\n", "a = 1\r\r\n",
    "[db]\nhost = h\nport = 5432\n[web]\nport = 80\n", "[db]\n[db]\nk=1\n[web-ui]\nk=2\n", "[a]\nx=1\n[b]\nx=2\n[a]\nx=3\n", "[Bad]\nk=1\n", "[1a]\nk=1\n", "[]\nk=1\n", "[a b]\nk=1\n", "[a.b]\nk=1\n", "[a]]\nk=1\n", "[a] # c\nk=1\n", "[a] x\nk=1\n", "  [a]  \nk=1\n", "[a\nk=1\n",
    "k = bare value\n", "k=#x\n", "k = #x\n", "k =\t#x\n", "u=http://h/#top\n", "a = b #c\n", "a = b#c\n", "a = b \t# c\n", "a = b  \n", "a =\n", "a = \n", "a=\n", "a = '\"x'\n", "a = x\"y\"\n", "a = x\\ny\n", "a = \\\n",
    'q = "plain"\n', 'q = "a b"  \n', 'q = "a" # comment\n', 'q = "a"#comment\n', 'q = "a" b\n', 'q = "a""b"\n', 'q = "\\n\\t\\r\\"\\\\"\n', 'q = "\\x"\n', 'q = "\\u{41}"\n', 'q = "\\u{1F600}"\n', 'q = "\\u{10FFFF}"\n', 'q = "\\u{110000}"\n', 'q = "\\u{D800}"\n', 'q = "\\u{DFFF}"\n',
    'q = "\\u{E000}"\n', 'q = "\\u{0}"\n', 'q = "\\u{}"\n', 'q = "\\u{1234567}"\n', 'q = "\\u{00000041}"\n', 'q = "\\u{0000041}"\n', 'q = "\\u{000041}"\n', 'q = "\\u{00041}"\n', 'q = "\\u{a}"\n', 'q = "\\u{A}"\n', 'q = "\\u{12G}"\n', 'q = "\\u41"\n', 'q = "\\u{41"\n', 'q = "\\u{ 41}"\n', 'q = "\\U{41}"\n', 'q = "unterminated\n', 'q = "dangling\\"\n', 'q = "dangling\\', 'q = "tab\there"\n', 'q = "a\\u{9}b"\n',
    'q = "caf\u00e9 \U0001f600"\n', 'q = "\u2003"\n', 'q = " # not a comment "\n', 'q = "x" \u00a0\n', 'q = "x" \t\n', 'q = ""\n', 'q = "" # c\n', 'q ="x"\n', 'q= "x"\n',
    "A = 1\n", "1a = 1\n", "a. = 1\n", ".a = 1\n", "a..b = 1\n", "a.b = 1\n", "a-b.c_d = 1\n", "a b = 1\n", "a\t= 1\n", "= 1\n", "a\n", "a 1\n", "a == 1\n", "a:1\n", "a-=1\n", "\u00e9 = 1\n", "a = 1 = 2\n", "-a = 1\n", "_a = 1\n", "a-- = 1\n", "a.-b = 1\n", "a._ = 1\n",
    "a = 1\na = 2\nb = 3\na = 4\n", "[s]\na = 1\na = 2\n", "x = 1\n[s]\nx = 2\ns.x = 3\n", "[s]\nk = 1\n[t]\nk = 2\n", "a=1\n# c\n\nb = 2 # tail\n   c = 3\n",
    "\x00", "a = 1\x00\n", "a = 1\x01\n", "a = \x0b1\n", "a = 1\x0c\n", "a = 1\x1f\n", "a = 1\x7f\n", "# comment \x01\n", 'a = "\x01"\n', "a = x\u00a0y\n", "a = \u00a0\n", "a =\u00a01\n", "\u00a0a = 1\n", "a = 1\u00a0\n", "a = 1\u2003\n", "\u0085a = 1\n", "a = 1\u2028b = 2\n",
    "n = 0\n", "n = -0\n", "n = 007\n", "n = 7\n", "n = -7\n", "n = +7\n", "n = 1_0\n", "n = 1e3\n", "n = 0x10\n", "n = 9007199254740992\n", "n = -9007199254740992\n", "n = 9007199254740993\n", "n = 9999999999999999\n", "n = -9007199254740993\n", "n = -9007199254740994\n", "n = -9999999999999999\n", "n = 9007199254740991\n", "n = -9007199254740991\n", "n = 12345678901234567\n", "n = 1.0\n", "n = \n", 'n = "42"\n', 'n = "4\\u{32}"\n', "n = 42 \n", "n = \u0663\n", "n = -\n",
    "a = b\nc = d", "a=b\nc=d\r\n", "a=1\n\n\n", "\n\na=1", "[a]\n", "[a]\nb.c = 1\n", "[a-b_c]\nd = 1\n", "# [a]\nb=1\n", "  # c\nb=1\n", "b=1 # c1 # c2\n", "b = \"x # y\" # z\n", "b = x\\\n",
]


def _kv_render_value(rng, v):
    bare_ok = (v == v.strip(" \t") and " #" not in v and "\t#" not in v and not v.startswith('"') and not v.startswith("#")
               and not any((ord(c) < 32 and c != "\t") or ord(c) == 127 for c in v) and not v.startswith("\ufeff") or v == "")
    if bare_ok and rng.random() < 0.55:
        return v
    out = ['"']
    for c in v:
        o = ord(c)
        if c == "\\":
            out.append("\\\\")
        elif c == '"':
            out.append('\\"')
        elif c == "\n":
            out.append("\\n")
        elif c == "\r":
            out.append("\\r")
        elif c == "\t" and rng.random() < 0.5:
            out.append("\\t")
        elif (o < 32 and c != "\t") or o == 127 or (o > 127 and rng.random() < 0.3):
            out.append("\\u{%s}" % (("%x" % o).upper() if rng.random() < 0.5 else "%x" % o))
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


def _kv_random_text(rng):
    lines = []
    section = None
    for _ in range(rng.randint(0, 9)):
        r = rng.random()
        pad = rng.choice(["", "", " ", "\t", "  "])
        if r < 0.15:
            section = rng.choice(KV_SECTIONS)
            lines.append(pad + "[%s]" % section + rng.choice(["", "", " # c", "  "]))
        elif r < 0.25:
            lines.append(rng.choice(["# comment", "  # c2", "", "   ", "#k = v"]))
        else:
            key = rng.choice(KV_KEYS)
            eq = rng.choice([" = ", "=", " =", "= ", "\t=\t"])
            val = rng.choice(KV_VALUES)
            tail = rng.choice(["", "", "", " # tail", "\t# tail"])
            lines.append(pad + key + eq + _kv_render_value(rng, val) + tail)
    text = rng.choice(["\n", "\n", "\r\n"]).join(lines)
    if lines and rng.random() < 0.8:
        text += rng.choice(["\n", "\r\n"])
    if rng.random() < 0.08:
        text = "\ufeff" + text
    return text


def _kv_mutate(rng, text):
    if not text:
        return text
    i = rng.randrange(len(text))
    op = rng.randrange(4)
    if op == 0:
        return text[:i] + text[i + 1:]
    if op == 1:
        return text[:i] + rng.choice(['"', "\\", "#", "[", "]", "=", "\x01", "\r", "{", "}", "\u00a0", " "]) + text[i:]
    if op == 2:
        return text[:i]
    return text[:i] + rng.choice(["=", "x", "\n", "\\u{", "\\", '"']) + text[i + 1:]


def kv_cases(rng):
    out = [("count", ["a = 1\nb = 2\n"]), ("keys", ["[s]\nk = 1\nk = 2\n"]), ("has", ["a = 1", "a"]), ("get", ["a = 1\na = 2", "a"]), ("get_all", ["a = 1\na = 2", "a"]), ("get_int", ["n = 42", "n"]), ("dump", ['q = "x\\ny"\n'])]
    texts = list(KV_HAND)
    for _ in range(60):
        texts.append(_kv_random_text(rng))
    for _ in range(25):
        texts.append(_kv_mutate(rng, _kv_random_text(rng)))
    for t in texts:
        out.append(("count", [t]))
        out.append(("keys", [t]))
        out.append(("dump", [t]))
    for t in texts:
        # ask for keys that are likely to exist in the text
        found = _kv_guess_keys(t)
        for key in found[:2] + ["nokey"][: 1 if rng.random() < 0.15 else 0]:
            out.append(("get", [t, key]))
            if rng.random() < 0.6:
                out.append(("get_all", [t, key]))
                out.append(("has", [t, key]))
            if rng.random() < 0.7:
                out.append(("get_int", [t, key]))
    for t in KV_HAND:
        if t.startswith("n = "):
            out.append(("get_int", [t, "n"]))
            out.append(("get", [t, "n"]))
    for t, key in [("[s]\nx=1\n", "s.x"), ("[s]\nx=1\n", "x"), ("a = 1\n", "A"), ("a = 1\n", ""), ("n = 5\n", "n "), ("[a]\nb.c = 1\n", "a.b.c"), ("x = 1\n[s]\nx = 2\ns.x = 3\n", "s.x"), ("k = v\n", "k\n")]:
        out.append(("get", [t, key]))
        out.append(("get_all", [t, key]))
        out.append(("has", [t, key]))
    return out


def _kv_guess_keys(text):
    import re
    keys = []
    section = None
    for line in text.replace("\r", "\n").split("\n"):
        line = line.strip(" \t")
        m = re.match(r"\[([a-z][a-z0-9_-]*)\]", line)
        if m:
            section = m.group(1)
            continue
        m = re.match(r"[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)*", line)
        if m:
            key = m.group(0) if section is None else section + "." + m.group(0)
            if key not in keys:
                keys.append(key)
    return keys


KV = PortLib(
    slug="kv-lines",
    title="settings file parser",
    blurb="A deployment tool reads a small line-based settings format with sections, quoted strings and comments, and a rewrite in another language must accept and reject exactly the same files.",
    spec=KV_SPEC,
    fns=KV_FNS,
    impls={"python": {"kv_lines.py": KV_PY}, "typescript": {"src/kv_lines.ts": KV_TS}, "go": {"kvlines.go": KV_GO}},
    cases=kv_cases,
    difficulty=5,
    n_examples=12,
    pairs=[("python", "go", "full"), ("go", "typescript", "full"), ("typescript", "python", "stub"), ("python", "typescript", "stub")],
    traps=["white space definitions (trim/strip/splitlines differ per language)", "code points versus UTF-16 units and bytes", "escape validation (surrogates, hex digit counts)", "integers beyond 2^53", "CR handling", "BOM"],
    tags=["parsing", "unicode", "strict-parsing"],
)
register_port(KV, __name__)

# ======================================================================================================================
# glob-lite: path-like globs with classes, braces and ** over code points
# ======================================================================================================================

GL_SPEC = dd('''
    Asset names are matched against glob patterns. Patterns and names are sequences of **Unicode code points** (not bytes, not UTF-16 units); a pattern must match the whole name.

    **Syntax.**

    * `?` matches one code point other than `/`; `*` matches zero or more code points other than `/`; `**` matches zero or more code points of any kind including `/`. Two or more consecutive `*` are one `**`.
    * `[...]` is a class and matches one code point other than `/`. A `!` right after `[` negates it (a negated class still never matches `/`). The items are single code points or ranges `lo-hi` by code point value (`lo > hi` is an error).
      An item that is followed by `-` and then any code point other than `]` starts a range; otherwise `-` is an ordinary item (`[a-]`, `[-a]`). A `]` that is the first item (right after `[` or `[!`) is an ordinary item (`[]a]`). Inside a class a backslash makes the next code point
      an ordinary item or range end; every other code point (`* ? [ { }` and `/` included) is ordinary there. A class that is never closed is an error (so `[]` and `[!]` are errors).
    * `{a,b,c}` lists alternatives (nesting is fine, alternatives may be empty: `{,x}`). A comma outside braces and a `}` that closes nothing are ordinary. A `{` that is never closed is an error. Braces are expanded first; the name has to match one of the expanded patterns.
      Braces inside a class or after a backslash are ordinary code points.
    * `\\x` stands for the code point `x` itself (`\\*`, `\\?`, `\\[`, `\\{`, `\\\\`, `\\/` ...). A pattern that ends with a lone backslash is an error.
    * Everything else matches itself.
    * With `ci` true, matching is case-insensitive for the **ASCII letters only**: a name code point `t` matches a literal `c` when they are equal or the same ASCII letter in the other case, and it is in a class when it or its other-case ASCII twin is a class member
      (a negated class is the opposite of that). Non-ASCII letters are never folded (`\u00c9` does not match `\u00e9`).

    **Functions.**

    * `glob_match(pattern, text, ci)` tells whether the pattern matches the whole text. An invalid pattern is an error even when the text could not match anyway (every expanded alternative is checked).
    * `expand_braces(pattern)` is the list of patterns after brace expansion, in this order: the first top-level brace group varies slowest (`{a,b}{c,d}` gives `ac, ad, bc, bd`); nested groups are expanded inside their alternative; backslash escapes and classes are left as written.
      More than 256 results, an unclosed `{`, an unclosed class or a trailing backslash is an error; other pattern errors (such as reversed ranges) are not detected by this function.
    * `filter_names(pattern, names, ci)` returns the 0-based indices of the matching names in order; an invalid pattern is an error.
    * `literal_prefix(pattern)` is the longest prefix of the pattern (cut at a code point boundary) that contains none of `* ? [ { \\`.
    * `is_valid(pattern)` is true when `glob_match` would not report an error for it.
''')

GL_FNS = [
    Fn("glob_match", [("pattern", "str"), ("text", "str"), ("ci", "bool")], "bool", err=True),
    Fn("expand_braces", [("pattern", "str")], "list<str>", err=True),
    Fn("filter_names", [("pattern", "str"), ("names", "list<str>"), ("ci", "bool")], "list<int>", err=True),
    Fn("literal_prefix", [("pattern", "str")], "str"),
    Fn("is_valid", [("pattern", "str")], "bool"),
]

GL_PY = dd(r'''
_MAX_ALTERNATIVES = 256


def _class_end(p, i):
    """p[i] == '['. Returns the index just after the closing ']' of the class that starts here."""
    n = len(p)
    j = i + 1
    if j < n and p[j] == "!":
        j += 1
    first = True
    while j < n:
        c = p[j]
        if c == "]" and not first:
            return j + 1
        first = False
        if c == "\\":
            if j + 1 >= n:
                raise ValueError("trailing backslash")
            j += 2
        else:
            j += 1
    raise ValueError("unclosed class")


def _group_end(p, i):
    """p[i] == '{'. Returns (index of the matching '}', indices of the top-level commas)."""
    n = len(p)
    depth = 0
    commas = []
    j = i
    while j < n:
        c = p[j]
        if c == "\\":
            if j + 1 >= n:
                raise ValueError("trailing backslash")
            j += 2
            continue
        if c == "[":
            j = _class_end(p, j)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j, commas
        elif c == "," and depth == 1:
            commas.append(j)
        j += 1
    raise ValueError("unclosed brace")


def _expand(p, out):
    n = len(p)
    j = 0
    while j < n:
        c = p[j]
        if c == "\\":
            if j + 1 >= n:
                raise ValueError("trailing backslash")
            j += 2
        elif c == "[":
            j = _class_end(p, j)
        elif c == "{":
            end, commas = _group_end(p, j)
            cuts = [j] + commas + [end]
            for a, b in zip(cuts, cuts[1:]):
                _expand(p[:j] + p[a + 1:b] + p[end + 1:], out)
            return
        else:
            j += 1
    out.append(p)
    if len(out) > _MAX_ALTERNATIVES:
        raise ValueError("too many alternatives")


def expand_braces(pattern):
    out = []
    _expand(pattern, out)
    return out


def _tokens(p):
    toks = []
    n = len(p)
    i = 0
    while i < n:
        c = p[i]
        if c == "\\":
            if i + 1 >= n:
                raise ValueError("trailing backslash")
            toks.append(("lit", p[i + 1]))
            i += 2
        elif c == "?":
            toks.append(("any",))
            i += 1
        elif c == "*":
            j = i
            while j < n and p[j] == "*":
                j += 1
            toks.append(("dstar",) if j - i >= 2 else ("star",))
            i = j
        elif c == "[":
            end = _class_end(p, i)
            j = i + 1
            neg = False
            if p[j] == "!":
                neg = True
                j += 1
            items = []
            first = True
            while j < end - 1 or (first and j < end):
                if p[j] == "]" and not first:
                    break
                first = False
                lo = p[j]
                if lo == "\\":
                    lo = p[j + 1]
                    j += 2
                else:
                    j += 1
                if j + 1 < end and p[j] == "-" and p[j + 1] != "]":
                    j += 1
                    hi = p[j]
                    if hi == "\\":
                        hi = p[j + 1]
                        j += 2
                    else:
                        j += 1
                    if ord(hi) < ord(lo):
                        raise ValueError("reversed range")
                    items.append((ord(lo), ord(hi)))
                else:
                    items.append((ord(lo), ord(lo)))
            toks.append(("class", neg, items))
            i = end
        else:
            toks.append(("lit", c))
            i += 1
    return toks


def _twin(c):
    if "a" <= c <= "z":
        return chr(ord(c) - 32)
    if "A" <= c <= "Z":
        return chr(ord(c) + 32)
    return c


def _single(tok, ch, ci):
    kind = tok[0]
    if kind == "lit":
        return ch == tok[1] or (ci and _twin(ch) == tok[1])
    if ch == "/":
        return False
    if kind == "any":
        return True
    inside = any(lo <= ord(ch) <= hi for lo, hi in tok[2])
    if not inside and ci:
        t = _twin(ch)
        inside = any(lo <= ord(t) <= hi for lo, hi in tok[2])
    return inside != tok[1]


def _match(tokens, s, ci):
    n = len(s)
    nxt = [False] * (n + 1)
    nxt[n] = True
    for tok in reversed(tokens):
        cur = [False] * (n + 1)
        if tok[0] == "dstar":
            cur[n] = nxt[n]
            for j in range(n - 1, -1, -1):
                cur[j] = nxt[j] or cur[j + 1]
        elif tok[0] == "star":
            cur[n] = nxt[n]
            for j in range(n - 1, -1, -1):
                cur[j] = nxt[j] or (s[j] != "/" and cur[j + 1])
        else:
            for j in range(n):
                cur[j] = nxt[j + 1] and _single(tok, s[j], ci)
        nxt = cur
    return nxt[0]


def _compile(pattern):
    return [_tokens(alt) for alt in expand_braces(pattern)]


def glob_match(pattern, text, ci):
    compiled = _compile(pattern)
    chars = list(text)
    return any(_match(t, chars, ci) for t in compiled)


def filter_names(pattern, names, ci):
    compiled = _compile(pattern)
    return [i for i, name in enumerate(names) if any(_match(t, list(name), ci) for t in compiled)]


def literal_prefix(pattern):
    for i, c in enumerate(pattern):
        if c in "*?[{\\":
            return pattern[:i]
    return pattern


def is_valid(pattern):
    try:
        _compile(pattern)
        return True
    except ValueError:
        return False
''')

GL_GO = dd(r'''
package globlite

import (
	"errors"
)

const maxAlternatives = 256

var errPattern = errors.New("invalid pattern")

func classEnd(p []rune, i int) (int, error) {
	n := len(p)
	j := i + 1
	if j < n && p[j] == '!' {
		j++
	}
	first := true
	for j < n {
		c := p[j]
		if c == ']' && !first {
			return j + 1, nil
		}
		first = false
		if c == '\\' {
			if j+1 >= n {
				return 0, errPattern
			}
			j += 2
		} else {
			j++
		}
	}
	return 0, errPattern
}

func groupEnd(p []rune, i int) (int, []int, error) {
	n := len(p)
	depth := 0
	var commas []int
	j := i
	for j < n {
		c := p[j]
		if c == '\\' {
			if j+1 >= n {
				return 0, nil, errPattern
			}
			j += 2
			continue
		}
		if c == '[' {
			e, err := classEnd(p, j)
			if err != nil {
				return 0, nil, err
			}
			j = e
			continue
		}
		if c == '{' {
			depth++
		} else if c == '}' {
			depth--
			if depth == 0 {
				return j, commas, nil
			}
		} else if c == ',' && depth == 1 {
			commas = append(commas, j)
		}
		j++
	}
	return 0, nil, errPattern
}

func expand(p []rune, out *[]string) error {
	n := len(p)
	j := 0
	for j < n {
		c := p[j]
		switch c {
		case '\\':
			if j+1 >= n {
				return errPattern
			}
			j += 2
		case '[':
			e, err := classEnd(p, j)
			if err != nil {
				return err
			}
			j = e
		case '{':
			end, commas, err := groupEnd(p, j)
			if err != nil {
				return err
			}
			cuts := append([]int{j}, commas...)
			cuts = append(cuts, end)
			for k := 0; k+1 < len(cuts); k++ {
				a, b := cuts[k], cuts[k+1]
				q := make([]rune, 0, n)
				q = append(q, p[:j]...)
				q = append(q, p[a+1:b]...)
				q = append(q, p[end+1:]...)
				if err := expand(q, out); err != nil {
					return err
				}
			}
			return nil
		default:
			j++
		}
	}
	*out = append(*out, string(p))
	if len(*out) > maxAlternatives {
		return errPattern
	}
	return nil
}

func ExpandBraces(pattern string) ([]string, error) {
	out := []string{}
	if err := expand([]rune(pattern), &out); err != nil {
		return nil, err
	}
	return out, nil
}

type span struct{ lo, hi rune }

type token struct {
	kind  byte // 'l' literal, '?' any, '*' star, 'D' double star, 'c' class
	lit   rune
	neg   bool
	items []span
}

func tokens(p []rune) ([]token, error) {
	var toks []token
	n := len(p)
	i := 0
	for i < n {
		c := p[i]
		switch {
		case c == '\\':
			if i+1 >= n {
				return nil, errPattern
			}
			toks = append(toks, token{kind: 'l', lit: p[i+1]})
			i += 2
		case c == '?':
			toks = append(toks, token{kind: '?'})
			i++
		case c == '*':
			j := i
			for j < n && p[j] == '*' {
				j++
			}
			if j-i >= 2 {
				toks = append(toks, token{kind: 'D'})
			} else {
				toks = append(toks, token{kind: '*'})
			}
			i = j
		case c == '[':
			end, err := classEnd(p, i)
			if err != nil {
				return nil, err
			}
			j := i + 1
			neg := false
			if p[j] == '!' {
				neg = true
				j++
			}
			var items []span
			first := true
			for j < end-1 || (first && j < end) {
				if p[j] == ']' && !first {
					break
				}
				first = false
				lo := p[j]
				if lo == '\\' {
					lo = p[j+1]
					j += 2
				} else {
					j++
				}
				if j+1 < end && p[j] == '-' && p[j+1] != ']' {
					j++
					hi := p[j]
					if hi == '\\' {
						hi = p[j+1]
						j += 2
					} else {
						j++
					}
					if hi < lo {
						return nil, errPattern
					}
					items = append(items, span{lo, hi})
				} else {
					items = append(items, span{lo, lo})
				}
			}
			toks = append(toks, token{kind: 'c', neg: neg, items: items})
			i = end
		default:
			toks = append(toks, token{kind: 'l', lit: c})
			i++
		}
	}
	return toks, nil
}

func twin(c rune) rune {
	if c >= 'a' && c <= 'z' {
		return c - 32
	}
	if c >= 'A' && c <= 'Z' {
		return c + 32
	}
	return c
}

func inItems(items []span, c rune) bool {
	for _, it := range items {
		if it.lo <= c && c <= it.hi {
			return true
		}
	}
	return false
}

func single(t token, ch rune, ci bool) bool {
	if t.kind == 'l' {
		return ch == t.lit || (ci && twin(ch) == t.lit)
	}
	if ch == '/' {
		return false
	}
	if t.kind == '?' {
		return true
	}
	inside := inItems(t.items, ch)
	if !inside && ci {
		inside = inItems(t.items, twin(ch))
	}
	return inside != t.neg
}

func match(toks []token, s []rune, ci bool) bool {
	n := len(s)
	nxt := make([]bool, n+1)
	nxt[n] = true
	for k := len(toks) - 1; k >= 0; k-- {
		t := toks[k]
		cur := make([]bool, n+1)
		switch t.kind {
		case 'D':
			cur[n] = nxt[n]
			for j := n - 1; j >= 0; j-- {
				cur[j] = nxt[j] || cur[j+1]
			}
		case '*':
			cur[n] = nxt[n]
			for j := n - 1; j >= 0; j-- {
				cur[j] = nxt[j] || (s[j] != '/' && cur[j+1])
			}
		default:
			for j := 0; j < n; j++ {
				cur[j] = nxt[j+1] && single(t, s[j], ci)
			}
		}
		nxt = cur
	}
	return nxt[0]
}

func compile(pattern string) ([][]token, error) {
	alts, err := ExpandBraces(pattern)
	if err != nil {
		return nil, err
	}
	var out [][]token
	for _, a := range alts {
		t, err := tokens([]rune(a))
		if err != nil {
			return nil, err
		}
		out = append(out, t)
	}
	return out, nil
}

func GlobMatch(pattern, text string, ci bool) (bool, error) {
	compiled, err := compile(pattern)
	if err != nil {
		return false, err
	}
	s := []rune(text)
	for _, t := range compiled {
		if match(t, s, ci) {
			return true, nil
		}
	}
	return false, nil
}

func FilterNames(pattern string, names []string, ci bool) ([]int64, error) {
	compiled, err := compile(pattern)
	if err != nil {
		return nil, err
	}
	out := []int64{}
	for i, name := range names {
		s := []rune(name)
		for _, t := range compiled {
			if match(t, s, ci) {
				out = append(out, int64(i))
				break
			}
		}
	}
	return out, nil
}

func LiteralPrefix(pattern string) string {
	for i, c := range pattern {
		switch c {
		case '*', '?', '[', '{', '\\':
			return pattern[:i]
		}
	}
	return pattern
}

func IsValid(pattern string) bool {
	_, err := compile(pattern)
	return err == nil
}
''')

GL_TS = dd(r'''
const MAX_ALTERNATIVES = 256;

function classEnd(p: string[], i: number): number {
  const n = p.length;
  let j = i + 1;
  if (j < n && p[j] === '!') j++;
  let first = true;
  while (j < n) {
    const c = p[j];
    if (c === ']' && !first) return j + 1;
    first = false;
    if (c === '\\') {
      if (j + 1 >= n) throw new Error('trailing backslash');
      j += 2;
    } else {
      j++;
    }
  }
  throw new Error('unclosed class');
}

function groupEnd(p: string[], i: number): [number, number[]] {
  const n = p.length;
  let depth = 0;
  const commas: number[] = [];
  let j = i;
  while (j < n) {
    const c = p[j];
    if (c === '\\') {
      if (j + 1 >= n) throw new Error('trailing backslash');
      j += 2;
      continue;
    }
    if (c === '[') {
      j = classEnd(p, j);
      continue;
    }
    if (c === '{') {
      depth++;
    } else if (c === '}') {
      depth--;
      if (depth === 0) return [j, commas];
    } else if (c === ',' && depth === 1) {
      commas.push(j);
    }
    j++;
  }
  throw new Error('unclosed brace');
}

function expand(p: string[], out: string[]): void {
  const n = p.length;
  let j = 0;
  while (j < n) {
    const c = p[j];
    if (c === '\\') {
      if (j + 1 >= n) throw new Error('trailing backslash');
      j += 2;
    } else if (c === '[') {
      j = classEnd(p, j);
    } else if (c === '{') {
      const [end, commas] = groupEnd(p, j);
      const cuts = [j, ...commas, end];
      for (let k = 0; k + 1 < cuts.length; k++) {
        expand([...p.slice(0, j), ...p.slice(cuts[k] + 1, cuts[k + 1]), ...p.slice(end + 1)], out);
      }
      return;
    } else {
      j++;
    }
  }
  out.push(p.join(''));
  if (out.length > MAX_ALTERNATIVES) throw new Error('too many alternatives');
}

export function expandBraces(pattern: string): string[] {
  const out: string[] = [];
  expand(Array.from(pattern), out);
  return out;
}

type Token =
  | { kind: 'lit'; lit: string }
  | { kind: 'any' }
  | { kind: 'star' }
  | { kind: 'dstar' }
  | { kind: 'class'; neg: boolean; items: Array<[number, number]> };

function cp(c: string): number {
  return c.codePointAt(0) as number;
}

function tokens(p: string[]): Token[] {
  const toks: Token[] = [];
  const n = p.length;
  let i = 0;
  while (i < n) {
    const c = p[i];
    if (c === '\\') {
      if (i + 1 >= n) throw new Error('trailing backslash');
      toks.push({ kind: 'lit', lit: p[i + 1] });
      i += 2;
    } else if (c === '?') {
      toks.push({ kind: 'any' });
      i++;
    } else if (c === '*') {
      let j = i;
      while (j < n && p[j] === '*') j++;
      toks.push(j - i >= 2 ? { kind: 'dstar' } : { kind: 'star' });
      i = j;
    } else if (c === '[') {
      const end = classEnd(p, i);
      let j = i + 1;
      let neg = false;
      if (p[j] === '!') {
        neg = true;
        j++;
      }
      const items: Array<[number, number]> = [];
      let first = true;
      while (j < end - 1 || (first && j < end)) {
        if (p[j] === ']' && !first) break;
        first = false;
        let lo = p[j];
        if (lo === '\\') {
          lo = p[j + 1];
          j += 2;
        } else {
          j++;
        }
        if (j + 1 < end && p[j] === '-' && p[j + 1] !== ']') {
          j++;
          let hi = p[j];
          if (hi === '\\') {
            hi = p[j + 1];
            j += 2;
          } else {
            j++;
          }
          if (cp(hi) < cp(lo)) throw new Error('reversed range');
          items.push([cp(lo), cp(hi)]);
        } else {
          items.push([cp(lo), cp(lo)]);
        }
      }
      toks.push({ kind: 'class', neg, items });
      i = end;
    } else {
      toks.push({ kind: 'lit', lit: c });
      i++;
    }
  }
  return toks;
}

function twin(c: string): string {
  if (c >= 'a' && c <= 'z') return String.fromCharCode(c.charCodeAt(0) - 32);
  if (c >= 'A' && c <= 'Z') return String.fromCharCode(c.charCodeAt(0) + 32);
  return c;
}

function inItems(items: Array<[number, number]>, c: string): boolean {
  const v = cp(c);
  return items.some(([lo, hi]) => lo <= v && v <= hi);
}

function single(tok: Token, ch: string, ci: boolean): boolean {
  if (tok.kind === 'lit') return ch === tok.lit || (ci && twin(ch) === tok.lit);
  if (ch === '/') return false;
  if (tok.kind === 'any') return true;
  if (tok.kind !== 'class') return false;
  let inside = inItems(tok.items, ch);
  if (!inside && ci) inside = inItems(tok.items, twin(ch));
  return inside !== tok.neg;
}

function matchTokens(toks: Token[], s: string[], ci: boolean): boolean {
  const n = s.length;
  let nxt: boolean[] = new Array(n + 1).fill(false);
  nxt[n] = true;
  for (let k = toks.length - 1; k >= 0; k--) {
    const tok = toks[k];
    const cur: boolean[] = new Array(n + 1).fill(false);
    if (tok.kind === 'dstar') {
      cur[n] = nxt[n];
      for (let j = n - 1; j >= 0; j--) cur[j] = nxt[j] || cur[j + 1];
    } else if (tok.kind === 'star') {
      cur[n] = nxt[n];
      for (let j = n - 1; j >= 0; j--) cur[j] = nxt[j] || (s[j] !== '/' && cur[j + 1]);
    } else {
      for (let j = 0; j < n; j++) cur[j] = nxt[j + 1] && single(tok, s[j], ci);
    }
    nxt = cur;
  }
  return nxt[0];
}

function compile(pattern: string): Token[][] {
  return expandBraces(pattern).map((alt) => tokens(Array.from(alt)));
}

export function globMatch(pattern: string, text: string, ci: boolean): boolean {
  const compiled = compile(pattern);
  const s = Array.from(text);
  return compiled.some((t) => matchTokens(t, s, ci));
}

export function filterNames(pattern: string, names: string[], ci: boolean): number[] {
  const compiled = compile(pattern);
  const out: number[] = [];
  names.forEach((name, i) => {
    const s = Array.from(name);
    if (compiled.some((t) => matchTokens(t, s, ci))) out.push(i);
  });
  return out;
}

export function literalPrefix(pattern: string): string {
  let out = '';
  for (const c of pattern) {
    if ('*?[{\\'.includes(c)) return out;
    out += c;
  }
  return out;
}

export function isValid(pattern: string): boolean {
  try {
    compile(pattern);
    return true;
  } catch (e) {
    return false;
  }
}
''')

GL_FRAGS = ["a", "b", "c", "x", "/", "*", "**", "?", "[ab]", "[!a]", "[a-c]", "[]a]", "[a-]", "[-a]", "{x,y}", "{,a}", "{a,b,c}", "\\*", "\\?", "\\[", "\\{", "\\\\", "\u00e9", "\U0001f600", "[\u00e9-\u00fc]", "[\U0001f600-\U0001f64f]", ".", "-", "}", ",", "]", "[", "{", "\\", "{a,{b,c}}", "{a/b,c}", "[{,}]", "[!/]", "[\\]]", "[a-\\]]", "A", "B", "[A-C]", "[!A-C]", "{,}", "{}", "[z-a]", "***", "*?", "?*", "\\/", "[/]", "[*]", "[?]"]
GL_CHARS = ["a", "b", "c", "x", "y", "/", "A", "B", "C", "\u00e9", "\u00c9", "\U0001f600", "\U0001f601", "*", "?", "-", ".", "]", "[", "{", "}", ",", "\\", "z"]
GL_HAND = [
    "a", "*", "**", "?", "a*", "*a", "a*b", "*.txt", "**/*.txt", "src/**/test_*.py", "src/*/main.c", "[abc]", "[a-c]x", "[!a]", "[!a-c]", "[]a]", "[a-]", "[-a]", "[a\\-z]", "[\\]]", "a{b,c}d", "{a,b}{c,d}", "{a,{b,c}}x", "{,x}y", "{x,}", "{a,b}", "x{1,2}{3,4}y",
    "\\*", "\\?", "\\[", "\\{", "\\\\", "\\a", "a\\", "\\", "[", "[]", "[!]", "[a", "[a-", "[z-a]", "[a-c-e]", "{", "{a", "{a,b", "}", "a}", "{a}}", "{a,b}}", "a,b", "{a,b},c", "[{]", "[}]", "[{,}]x", "{[},]}", "\\{a,b}", "{a\\,b,c}", "{a,b\\}",
    "[b-a]", "[c-b]x", "[a-a]", "[a-b]", "[\\a-a]", "[a-\\a]", "[\\b-\\a]", "[a-c]{1,2}", "*{a,b}*", "**/{a,b}/*", "?", "??", "???", "?*?", "*?*", "***", "*?**", "a**b", "a***b", "\u00e9*", "?\u00e9", "[\u00e9-\u00fc]", "[\u00c9]", "[!\u00e9]", "\U0001f600", "?\U0001f600", "[\U0001f600-\U0001f64f]", "??", "\u00e9{a,\u00e9}",
    "{" + ",".join("a%d" % i for i in range(16)) + "}{" + ",".join("b%d" % i for i in range(16)) + "}", "{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}", "{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}", "{" + ",".join("a%d" % i for i in range(256)) + "}", "{" + ",".join("a%d" % i for i in range(257)) + "}",
    "{" + ",".join("a%d" % i for i in range(16)) + "}{" + ",".join("b%d" % i for i in range(16)) + "}x", "{{a,b},{c,d}}", "{a,{b,{c,d}}}", "{,{,}}",
]
GL_NAMES = ["a", "b", "ab", "abc", "a/b", "a/b/c", "x.txt", "dir/x.txt", "dir/sub/x.txt", "src/main.c", "src/a/main.c", "src/a/b/main.c", "src/test_a.py", "src/pkg/test_a.py", "src/pkg/sub/test_b.py", "", "/", "//", "A", "AB", "Ab", "\u00e9", "\u00c9", "\u00e9\u00e9", "\U0001f600", "\U0001f601", "a\U0001f600", "*", "?", "[", "{", "a,b", "a-b", "a.b", "-", "]", "}", ",", "\\", "a\\", "ac1", "b3", "a0b0", "a15b15", "a1b2", "ay", "1x", "x3y", "x13y", "x24y", "bd", "xc", "xy", "ax", "az", "zz", "a/", "/a", "dir/", "C", "c", "\u00fc", "\u00e9a"]


def gl_cases(rng):
    out = [("glob_match", ["*.txt", "a.txt", False]), ("expand_braces", ["a{b,c}d"]), ("filter_names", ["a*", ["ab", "ba", "a"], False]), ("literal_prefix", ["src/*.c"]), ("is_valid", ["[abc"]), ("glob_match", ["**/x", "a/b/x", False])]
    pats = list(GL_HAND)
    for _ in range(80):
        pats.append("".join(rng.choice(GL_FRAGS) for _ in range(rng.randint(1, 5))))
    for p in pats:
        out.append(("is_valid", [p]))
        out.append(("expand_braces", [p]))
        out.append(("literal_prefix", [p]))
    texts = list(GL_NAMES)
    for _ in range(40):
        texts.append("".join(rng.choice(GL_CHARS) for _ in range(rng.randint(0, 6))))
    for p in pats:
        for t in rng.sample(texts, 6):
            out.append(("glob_match", [p, t, rng.random() < 0.35]))
        if rng.random() < 0.7:
            out.append(("filter_names", [p, rng.sample(texts, rng.randint(0, 12)), rng.random() < 0.4]))
    for p in ["*.TXT", "[a-c]", "[!a]", "[!A]", "[b-d]x", "\u00e9", "\u00c9", "[\u00e9]", "[A-Z]", "[!A-Z]", "a{B,C}", "[z-a]", "[\\a-c]", "\\A"]:
        for t in ["a.txt", "A.TXT", "a.TxT", "B", "b", "Ax", "ax", "a", "\u00e9", "\u00c9", "aB", "ac", "C", "x", "bx", "BX"]:
            out.append(("glob_match", [p, t, True]))
            out.append(("glob_match", [p, t, False]))
    return out


GL = PortLib(
    slug="glob-lite",
    title="asset glob matcher",
    blurb="An asset pipeline selects files with glob patterns (classes, braces, ** and escapes) and every tool in it must agree on what a pattern means, Unicode names included.",
    spec=GL_SPEC,
    fns=GL_FNS,
    impls={"python": {"glob_lite.py": GL_PY}, "go": {"globlite.go": GL_GO}, "typescript": {"src/glob_lite.ts": GL_TS}},
    cases=gl_cases,
    difficulty=5,
    n_examples=12,
    pairs=[("python", "go", "full"), ("go", "typescript", "full"), ("typescript", "python", "stub"), ("python", "typescript", "stub")],
    traps=["code points versus UTF-16 units versus bytes", "brace and class scanning order", "ASCII-only case folding", "non-crossing star versus double star", "validation of all alternatives"],
    tags=["glob", "unicode", "parsing"],
)
register_port(GL, __name__)
