"""Config-language lexer (go): identifiers, numbers with separators, duration literals, escapes, nested comments."""
from fx import Lib, dd, langs

from generators.fix._lang1 import gosrc, register_libs

README = dd(r'''
    # knotlex

    The lexer of "knot", the small configuration language of the deployment tool. `Lex(src string) ([]Token, error)` turns a
    source text into tokens; on the first problem it returns the tokens read so far and a `*Error`.

    ```go
    type Token struct {
        Kind      Kind   // EOF, Ident, Int, Duration, String, Punct
        Text      string // exact source text of the token
        Num       uint64 // value of an Int, milliseconds of a Duration
        Str       string // decoded value of a String
        Offset    int    // byte offset of the first byte
        Line, Col int    // 1-based; Col counts code points (runes), not bytes
    }
    type Error struct { Line, Col int; Msg string } // Error() is "<line>:<col>: <msg>"
    ```
    The result always ends with one `EOF` token (empty `Text`) positioned after the last character, unless an error stopped
    the scan. `Kind` has a `String()` method giving `EOF`, `Ident`, `Int`, `Duration`, `String`, `Punct`.

    ## Layout
    Spaces, tabs, `\r` and `\n` separate tokens. A `\n` starts a new line (`Line + 1`, `Col` back to 1); `\r` is skipped
    and never advances `Col`, so `\r\n` is one line break. `#` starts a comment that runs to the end of the line. `/*`
    starts a block comment that ends at the matching `*/`; block comments nest (`/* a /* b */ c */` is one comment).

    ## Identifiers
    `[A-Za-z_][A-Za-z0-9_]*` where a `-` may appear between identifier characters when the character right after it is a
    letter, digit or `_`: `a-b` is one identifier, but in `a->b` the `-` is not part of `a`, and a trailing `-` (`a- `)
    is not part of the identifier either. Only ASCII letters count.

    ## Numbers
    * Decimal `123`, hexadecimal `0x1F` / `0X1f`, binary `0b101` / `0B101`. A single `_` may separate digits (`1_000`,
      `0xFF_FF`), never at the start or end of the digits and never doubled. Text keeps the underscores; `Num` is the
      value. Values above `2^64-1` are errors.
    * **Durations**: a decimal number immediately followed by letters is a duration made of one or more
      `<digits><unit>` groups with the units `d h m s ms` (86400000, 3600000, 60000, 1000 and 1 ms): `5s`, `1h30m`,
      `250ms`. Units may repeat and come in any order (`5s10m` is fine); `Num` is the total in milliseconds, which must fit in
      a `uint64`. No underscores inside a duration.

    ## Strings
    Double-quoted. `Text` is the raw source including the quotes, `Str` the decoded value. Escapes: `\n \t \r \\ \" \0` and
    `\u{X}` with 1 to 6 hex digits naming a Unicode scalar value (at most 10FFFF, not a surrogate). Any other character
    (including non-ASCII) stands for itself; a raw newline is not allowed inside a string.

    ## Punctuation
    The two-character tokens `-> == != <= >= && ||` (always preferred when they match), and the single characters
    `= < > { } ( ) [ ] , . : ; + - * / ! & | %`. Kind `Punct`.

    ## Errors
    `Msg` and position are fixed:

    | Msg | position |
    |---|---|
    | `unexpected character` | the character |
    | `unterminated block comment` | the start of the outermost `/*` |
    | `unterminated string` | the opening quote (end of input or a raw newline inside) |
    | `invalid escape` | the backslash (including a backslash before a newline) |
    | `invalid unicode escape` | the backslash |
    | `bad digit separator` | the offending `_` |
    | `missing digits after prefix` | the start of the number (`0x`, `0b`, `0x_1`) |
    | `bad number suffix` | the character right after a number or duration that must not follow it (a letter, digit or `_`) |
    | `integer too large` | the start of the number |
    | `underscore in duration` | the start of the number |
    | `bad duration unit` | the start of the number (a letter run that is not one of the units) |
    | `missing duration unit` | the start of the number (a group of digits without a unit, `5m3`) |
    | `duration too large` | the start of the number |

    A backslash at the end of input inside a string is `unterminated string`.
''')

SRC = gosrc(dd(r'''
    // Package knotlex tokenizes the knot configuration language.
    package knotlex

    import (
        "fmt"
        "math/bits"
        "strconv"
        "strings"
        "unicode/utf8"
    )

    // Kind is the type of a token.
    type Kind int

    const (
        EOF Kind = iota
        Ident
        Int
        Duration
        String
        Punct
    )

    func (k Kind) String() string {
        return [...]string{"EOF", "Ident", "Int", "Duration", "String", "Punct"}[k]
    }

    // Token is one lexical element.
    type Token struct {
        Kind      Kind
        Text      string
        Num       uint64
        Str       string
        Offset    int
        Line, Col int
    }

    // Error is a lexical error with its position.
    type Error struct {
        Line, Col int
        Msg       string
    }

    func (e *Error) Error() string { return fmt.Sprintf("%d:%d: %s", e.Line, e.Col, e.Msg) }

    type lexer struct {
        src       string
        pos       int
        line, col int
    }

    func (l *lexer) eof() bool { return l.pos >= len(l.src) }

    // peekAt returns the rune k runes ahead, or -1 at the end of the input.
    func (l *lexer) peekAt(k int) rune {
        p := l.pos
        for ; k > 0 && p < len(l.src); k-- {
            _, w := utf8.DecodeRuneInString(l.src[p:])
            p += w
        }
        if p >= len(l.src) {
            return -1
        }
        r, _ := utf8.DecodeRuneInString(l.src[p:])
        return r
    }

    func (l *lexer) peek() rune { return l.peekAt(0) }

    func (l *lexer) adv() rune {
        r, w := utf8.DecodeRuneInString(l.src[l.pos:])
        l.pos += w
        switch r {
        case '\n':
            l.line++
            l.col = 1
        case '\r':
        default:
            l.col++
        }
        return r
    }

    func (l *lexer) errHere(msg string) *Error { return &Error{l.line, l.col, msg} }

    func isAlpha(r rune) bool { return r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' }
    func isDigit(r rune) bool { return r >= '0' && r <= '9' }
    func isBin(r rune) bool   { return r == '0' || r == '1' }
    func isHex(r rune) bool   { return isDigit(r) || r >= 'a' && r <= 'f' || r >= 'A' && r <= 'F' }
    func isIdentPart(r rune) bool {
        return isAlpha(r) || isDigit(r) || r == '_'
    }

    func (l *lexer) skip() *Error {
        for !l.eof() {
            c := l.peek()
            switch {
            case c == ' ' || c == '\t' || c == '\r' || c == '\n':
                l.adv()
            case c == '#':
                for !l.eof() && l.peek() != '\n' {
                    l.adv()
                }
            case c == '/' && l.peekAt(1) == '*':
                line, col := l.line, l.col
                l.adv()
                l.adv()
                for depth := 1; depth > 0; {
                    switch {
                    case l.eof():
                        return &Error{line, col, "unterminated block comment"}
                    case l.peek() == '/' && l.peekAt(1) == '*':
                        l.adv()
                        l.adv()
                        depth++
                    case l.peek() == '*' && l.peekAt(1) == '/':
                        l.adv()
                        l.adv()
                        depth--
                    default:
                        l.adv()
                    }
                }
            default:
                return nil
            }
        }
        return nil
    }

    // scanDigits consumes digits with single underscores between them.
    func (l *lexer) scanDigits(valid func(rune) bool) *Error {
        got := false
        for {
            c := l.peek()
            switch {
            case valid(c):
                l.adv()
                got = true
            case c == '_':
                if !got || !valid(l.peekAt(1)) {
                    return l.errHere("bad digit separator")
                }
                l.adv()
            default:
                return nil
            }
        }
    }

    var durUnits = map[string]uint64{"d": 86400000, "h": 3600000, "m": 60000, "s": 1000, "ms": 1}

    func (l *lexer) duration(start, line, col int) (Token, *Error) {
        digits := l.src[start:l.pos]
        if strings.Contains(digits, "_") {
            return Token{}, &Error{line, col, "underscore in duration"}
        }
        var total uint64
        for {
            u := l.pos
            for isAlpha(l.peek()) {
                l.adv()
            }
            mult, ok := durUnits[l.src[u:l.pos]]
            if !ok {
                return Token{}, &Error{line, col, "bad duration unit"}
            }
            n, err := strconv.ParseUint(digits, 10, 64)
            if err != nil {
                return Token{}, &Error{line, col, "duration too large"}
            }
            hi, lo := bits.Mul64(n, mult)
            sum, carry := bits.Add64(total, lo, 0)
            if hi != 0 || carry != 0 {
                return Token{}, &Error{line, col, "duration too large"}
            }
            total = sum
            if !isDigit(l.peek()) {
                break
            }
            d0 := l.pos
            for isDigit(l.peek()) {
                l.adv()
            }
            digits = l.src[d0:l.pos]
            if !isAlpha(l.peek()) {
                return Token{}, &Error{line, col, "missing duration unit"}
            }
        }
        if l.peek() == '_' {
            return Token{}, l.errHere("bad number suffix")
        }
        return Token{Kind: Duration, Text: l.src[start:l.pos], Num: total, Offset: start, Line: line, Col: col}, nil
    }

    func (l *lexer) number(start, line, col int) (Token, *Error) {
        base := 10
        valid := isDigit
        if l.peek() == '0' {
            switch l.peekAt(1) {
            case 'x', 'X':
                base, valid = 16, isHex
            case 'b', 'B':
                base, valid = 2, isBin
            }
        }
        if base != 10 {
            l.adv()
            l.adv()
            if !valid(l.peek()) {
                return Token{}, &Error{line, col, "missing digits after prefix"}
            }
        }
        if err := l.scanDigits(valid); err != nil {
            return Token{}, err
        }
        if base == 10 && isAlpha(l.peek()) {
            return l.duration(start, line, col)
        }
        if c := l.peek(); base != 10 && (isAlpha(c) || isDigit(c) || c == '_') {
            return Token{}, l.errHere("bad number suffix")
        }
        text := l.src[start:l.pos]
        digits := text
        if base != 10 {
            digits = text[2:]
        }
        v, err := strconv.ParseUint(strings.ReplaceAll(digits, "_", ""), base, 64)
        if err != nil {
            return Token{}, &Error{line, col, "integer too large"}
        }
        return Token{Kind: Int, Text: text, Num: v, Offset: start, Line: line, Col: col}, nil
    }

    func (l *lexer) str(start, line, col int) (Token, *Error) {
        l.adv()
        var sb strings.Builder
        for {
            c := l.peek()
            if c == -1 || c == '\n' {
                return Token{}, &Error{line, col, "unterminated string"}
            }
            if c == '"' {
                l.adv()
                break
            }
            if c != '\\' {
                sb.WriteRune(l.adv())
                continue
            }
            eline, ecol := l.line, l.col
            l.adv()
            switch e := l.peek(); e {
            case -1:
                return Token{}, &Error{line, col, "unterminated string"}
            case 'n', 't', 'r', '\\', '"', '0':
                l.adv()
                sb.WriteByte(map[rune]byte{'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', '"': '"', '0': 0}[e])
            case 'u':
                l.adv()
                bad := &Error{eline, ecol, "invalid unicode escape"}
                if l.peek() != '{' {
                    return Token{}, bad
                }
                l.adv()
                h := ""
                for isHex(l.peek()) {
                    h += string(l.adv())
                }
                if l.peek() != '}' || len(h) < 1 || len(h) > 6 {
                    return Token{}, bad
                }
                l.adv()
                v, _ := strconv.ParseUint(h, 16, 32)
                if v > 0x10FFFF || (v >= 0xD800 && v <= 0xDFFF) {
                    return Token{}, bad
                }
                sb.WriteRune(rune(v))
            default:
                return Token{}, &Error{eline, ecol, "invalid escape"}
            }
        }
        return Token{Kind: String, Text: l.src[start:l.pos], Str: sb.String(), Offset: start, Line: line, Col: col}, nil
    }

    var twoChar = []string{"->", "==", "!=", "<=", ">=", "&&", "||"}

    const oneChar = "=<>{}()[],.:;+-*/!&|%"

    // Lex splits src into tokens.
    func Lex(src string) ([]Token, error) {
        l := &lexer{src: src, line: 1, col: 1}
        var toks []Token
        for {
            if err := l.skip(); err != nil {
                return toks, err
            }
            start, line, col := l.pos, l.line, l.col
            if l.eof() {
                return append(toks, Token{Kind: EOF, Offset: start, Line: line, Col: col}), nil
            }
            c := l.peek()
            var tok Token
            var err *Error
            switch {
            case isAlpha(c) || c == '_':
                l.adv()
                for {
                    if p := l.peek(); isIdentPart(p) {
                        l.adv()
                    } else if p == '-' && isIdentPart(l.peekAt(1)) {
                        l.adv()
                        l.adv()
                    } else {
                        break
                    }
                }
                tok = Token{Kind: Ident, Text: src[start:l.pos], Offset: start, Line: line, Col: col}
            case isDigit(c):
                tok, err = l.number(start, line, col)
            case c == '"':
                tok, err = l.str(start, line, col)
            default:
                text := ""
                for _, two := range twoChar {
                    if strings.HasPrefix(src[start:], two) {
                        text = two
                    }
                }
                if text == "" && strings.ContainsRune(oneChar, c) {
                    text = string(c)
                }
                if text == "" {
                    return toks, &Error{line, col, "unexpected character"}
                }
                for range text {
                    l.adv()
                }
                tok = Token{Kind: Punct, Text: text, Offset: start, Line: line, Col: col}
            }
            if err != nil {
                return toks, err
            }
            toks = append(toks, tok)
        }
    }
'''))

VISIBLE = gosrc(dd(r'''
    package knotlex

    import "testing"

    func TestLexAssignment(t *testing.T) {
        toks, err := Lex("port = 8_080")
        if err != nil || len(toks) != 4 {
            t.Fatalf("got %d tokens, %v", len(toks), err)
        }
        if toks[2].Kind != Int || toks[2].Num != 8080 {
            t.Fatalf("got %+v", toks[2])
        }
    }

    func TestLexDuration(t *testing.T) {
        toks, err := Lex("1m30s")
        if err != nil || toks[0].Kind != Duration || toks[0].Num != 90000 {
            t.Fatalf("got %+v, %v", toks, err)
        }
    }
'''))

CASES = '''
    {"",
        "EOF:@1:1+0"},
    {"   \\n\\t ",
        "EOF:@2:3+6"},
    {"foo bar_baz _x x1 __ Z9_",
        "Ident:foo@1:1+0 | Ident:bar_baz@1:5+4 | Ident:_x@1:13+12 | Ident:x1@1:16+15 | Ident:__@1:19+18 | Ident:Z9_@1:22+21 | EOF:@1:25+24"},
    {"a-b a->b a- a-1 a--b a-_ -a x-y-z",
        "Ident:a-b@1:1+0 | Ident:a@1:5+4 | Punct:->@1:6+5 | Ident:b@1:8+7 | Ident:a@1:10+9 | Punct:-@1:11+10 | Ident:a-1@1:13+12 | Ident:a@1:17+16 | Punct:-@1:18+17 | Punct:-@1:19+18 | Ident:b@1:20+19 | Ident:a-_@1:22+21 | Punct:-@1:26+25 | Ident:a@1:27+26 | Ident:x-y-z@1:29+28 | EOF:@1:34+33"},
    {"foo = 5s",
        "Ident:foo@1:1+0 | Punct:=@1:5+4 | Duration:5s@1:7+6=5000 | EOF:@1:9+8"},
    {"0 7 007 1_000 1_0_0 0x1F 0XaB_cD 0b1010 0B1_0 0x0 0b0",
        "Int:0@1:1+0=0 | Int:7@1:3+2=7 | Int:007@1:5+4=7 | Int:1_000@1:9+8=1000 | Int:1_0_0@1:15+14=100 | Int:0x1F@1:21+20=31 | Int:0XaB_cD@1:26+25=43981 | Int:0b1010@1:34+33=10 | Int:0B1_0@1:41+40=2 | Int:0x0@1:47+46=0 | Int:0b0@1:51+50=0 | EOF:@1:54+53"},
    {"18446744073709551615 0xFFFFFFFFFFFFFFFF 0b1111111111111111111111111111111111111111111111111111111111111111",
        "Int:18446744073709551615@1:1+0=18446744073709551615 | Int:0xFFFFFFFFFFFFFFFF@1:22+21=18446744073709551615 | Int:0b1111111111111111111111111111111111111111111111111111111111111111@1:41+40=18446744073709551615 | EOF:@1:107+106"},
    {"18446744073709551616",
        " !! 1:1 integer too large"},
    {"0x10000000000000000",
        " !! 1:1 integer too large"},
    {"99999999999999999999999",
        " !! 1:1 integer too large"},
    {"0b10000000000000000000000000000000000000000000000000000000000000000",
        " !! 1:1 integer too large"},
    {"5s 5ms 1h30m 2d 1d2h3m4s5ms 10m5s 5s10m 1m1m 0s 000ms 90s 1d1d",
        "Duration:5s@1:1+0=5000 | Duration:5ms@1:4+3=5 | Duration:1h30m@1:8+7=5400000 | Duration:2d@1:14+13=172800000 | Duration:1d2h3m4s5ms@1:17+16=93784005 | Duration:10m5s@1:29+28=605000 | Duration:5s10m@1:35+34=605000 | Duration:1m1m@1:41+40=120000 | Duration:0s@1:46+45=0 | Duration:000ms@1:49+48=0 | Duration:90s@1:55+54=90000 | Duration:1d1d@1:59+58=172800000 | EOF:@1:63+62"},
    {"5mm",
        " !! 1:1 bad duration unit"},
    {"5x",
        " !! 1:1 bad duration unit"},
    {"5m3",
        " !! 1:1 missing duration unit"},
    {"1h30",
        " !! 1:1 missing duration unit"},
    {"1_000ms",
        " !! 1:1 underscore in duration"},
    {"5m_",
        " !! 1:3 bad number suffix"},
    {"5s_1",
        " !! 1:3 bad number suffix"},
    {"12abc",
        " !! 1:1 bad duration unit"},
    {"7 s",
        "Int:7@1:1+0=7 | Ident:s@1:3+2 | EOF:@1:4+3"},
    {"5ms5",
        " !! 1:1 missing duration unit"},
    {"5sm",
        " !! 1:1 bad duration unit"},
    {"1H",
        " !! 1:1 bad duration unit"},
    {"99999999999999999999d",
        " !! 1:1 duration too large"},
    {"213503982335d",
        " !! 1:1 duration too large"},
    {"213503982334d",
        "Duration:213503982334d@1:1+0=18446744073657600000 | EOF:@1:14+13"},
    {"18446744073709551615ms",
        "Duration:18446744073709551615ms@1:1+0=18446744073709551615 | EOF:@1:23+22"},
    {"18446744073709551615ms1ms",
        " !! 1:1 duration too large"},
    {"1d 213503982334d",
        "Duration:1d@1:1+0=86400000 | Duration:213503982334d@1:4+3=18446744073657600000 | EOF:@1:17+16"},
    {"1_",
        " !! 1:2 bad digit separator"},
    {"_1",
        "Ident:_1@1:1+0 | EOF:@1:3+2"},
    {"1__0",
        " !! 1:2 bad digit separator"},
    {"0x_1",
        " !! 1:1 missing digits after prefix"},
    {"0x1_",
        " !! 1:4 bad digit separator"},
    {"0b1__0",
        " !! 1:4 bad digit separator"},
    {"0x1G",
        " !! 1:4 bad number suffix"},
    {"0b102",
        " !! 1:5 bad number suffix"},
    {"0xZ",
        " !! 1:1 missing digits after prefix"},
    {"0b2",
        " !! 1:1 missing digits after prefix"},
    {"0b",
        " !! 1:1 missing digits after prefix"},
    {"0x",
        " !! 1:1 missing digits after prefix"},
    {"1_000_",
        " !! 1:6 bad digit separator"},
    {"12_a",
        " !! 1:3 bad digit separator"},
    {"\\"\\" \\"a\\" \\"hello world\\" \\"tab\\\\there\\" \\"q\\\\\\"uote\\" \\"back\\\\\\\\slash\\" \\"nl\\\\n\\" \\"cr\\\\r\\" \\"nul\\\\0\\"",
        "String:\\"\\"@1:1+0=\\"\\" | String:\\"a\\"@1:4+3=\\"a\\" | String:\\"hello world\\"@1:8+7=\\"hello world\\" | String:\\"tab\\\\there\\"@1:22+21=\\"tab\\\\there\\" | String:\\"q\\\\\\"uote\\"@1:34+33=\\"q\\\\\\"uote\\" | String:\\"back\\\\\\\\slash\\"@1:44+43=\\"back\\\\\\\\slash\\" | String:\\"nl\\\\n\\"@1:58+57=\\"nl\\\\n\\" | String:\\"cr\\\\r\\"@1:65+64=\\"cr\\\\r\\" | String:\\"nul\\\\0\\"@1:72+71=\\"nul\\\\x00\\" | EOF:@1:79+78"},
    {"\\"\\\\u{41}\\\\u{1F600}\\\\u{0}\\\\u{3b1}\\\\u{e9}\\\\u{000041}\\"",
        "String:\\"\\\\u{41}\\\\u{1F600}\\\\u{0}\\\\u{3b1}\\\\u{e9}\\\\u{000041}\\"@1:1+0=\\"A😀\\\\x00αéA\\" | EOF:@1:46+45"},
    {"\\"héllo wörld\\"",
        "String:\\"héllo wörld\\"@1:1+0=\\"héllo wörld\\" | EOF:@1:14+15"},
    {"\\"# not a comment /* nor this\\"",
        "String:\\"# not a comment /* nor this\\"@1:1+0=\\"# not a comment /* nor this\\" | EOF:@1:30+29"},
    {"\\"a\\" \\"b\\"x",
        "String:\\"a\\"@1:1+0=\\"a\\" | String:\\"b\\"@1:5+4=\\"b\\" | Ident:x@1:8+7 | EOF:@1:9+8"},
    {"\\"abc",
        " !! 1:1 unterminated string"},
    {"\\"abc\\ndef\\"",
        " !! 1:1 unterminated string"},
    {"\\"\\\\q\\"",
        " !! 1:2 invalid escape"},
    {"\\"\\\\u41\\"",
        " !! 1:2 invalid unicode escape"},
    {"\\"\\\\u{}\\"",
        " !! 1:2 invalid unicode escape"},
    {"\\"\\\\u{1234567}\\"",
        " !! 1:2 invalid unicode escape"},
    {"\\"\\\\u{110000}\\"",
        " !! 1:2 invalid unicode escape"},
    {"\\"\\\\u{D800}\\"",
        " !! 1:2 invalid unicode escape"},
    {"\\"\\\\u{DFFF}\\"",
        " !! 1:2 invalid unicode escape"},
    {"\\"\\\\u{41\\"",
        " !! 1:2 invalid unicode escape"},
    {"\\"abc\\\\",
        " !! 1:1 unterminated string"},
    {"\\"a\\\\\\nb\\"",
        " !! 1:3 invalid escape"},
    {"\\"\\\\u{g1}\\"",
        " !! 1:2 invalid unicode escape"},
    {"x \\"ok\\" \\"bad\\\\x\\"",
        "Ident:x@1:1+0 | String:\\"ok\\"@1:3+2=\\"ok\\" !! 1:12 invalid escape"},
    {"# only",
        "EOF:@1:7+6"},
    {"a # c\\nb",
        "Ident:a@1:1+0 | Ident:b@2:1+6 | EOF:@2:2+7"},
    {"a#c\\r\\nb",
        "Ident:a@1:1+0 | Ident:b@2:1+5 | EOF:@2:2+6"},
    {"/* c */ x",
        "Ident:x@1:9+8 | EOF:@1:10+9"},
    {"/* a /* b */ c */ x",
        "Ident:x@1:19+18 | EOF:@1:20+19"},
    {"/* unterminated",
        " !! 1:1 unterminated block comment"},
    {"a /* /* */ x",
        "Ident:a@1:1+0 !! 1:3 unterminated block comment"},
    {"/**/x",
        "Ident:x@1:5+4 | EOF:@1:6+5"},
    {"/***/x",
        "Ident:x@1:6+5 | EOF:@1:7+6"},
    {"/*/ x */ y",
        "Ident:y@1:10+9 | EOF:@1:11+10"},
    {"x / y",
        "Ident:x@1:1+0 | Punct:/@1:3+2 | Ident:y@1:5+4 | EOF:@1:6+5"},
    {"x /* c */ / y",
        "Ident:x@1:1+0 | Punct:/@1:11+10 | Ident:y@1:13+12 | EOF:@1:14+13"},
    {"/* multi\\nline */ z",
        "Ident:z@2:9+17 | EOF:@2:10+18"},
    {"x\\n  /* never\\nends",
        "Ident:x@1:1+0 !! 2:3 unterminated block comment"},
    {"/* a /* b */",
        " !! 1:1 unterminated block comment"},
    {"-> == != <= >= && || = < > { } ( ) [ ] , . : ; + - * / ! & | %",
        "Punct:->@1:1+0 | Punct:==@1:4+3 | Punct:!=@1:7+6 | Punct:<=@1:10+9 | Punct:>=@1:13+12 | Punct:&&@1:16+15 | Punct:||@1:19+18 | Punct:=@1:22+21 | Punct:<@1:24+23 | Punct:>@1:26+25 | Punct:{@1:28+27 | Punct:}@1:30+29 | Punct:(@1:32+31 | Punct:)@1:34+33 | Punct:[@1:36+35 | Punct:]@1:38+37 | Punct:,@1:40+39 | Punct:.@1:42+41 | Punct::@1:44+43 | Punct:;@1:46+45 | Punct:+@1:48+47 | Punct:-@1:50+49 | Punct:*@1:52+51 | Punct:/@1:54+53 | Punct:!@1:56+55 | Punct:&@1:58+57 | Punct:|@1:60+59 | Punct:%@1:62+61 | EOF:@1:63+62"},
    {"a<=b>=c==d!=e",
        "Ident:a@1:1+0 | Punct:<=@1:2+1 | Ident:b@1:4+3 | Punct:>=@1:5+4 | Ident:c@1:7+6 | Punct:==@1:8+7 | Ident:d@1:10+9 | Punct:!=@1:11+10 | Ident:e@1:13+12 | EOF:@1:14+13"},
    {"<<",
        "Punct:<@1:1+0 | Punct:<@1:2+1 | EOF:@1:3+2"},
    {"=>=",
        "Punct:=@1:1+0 | Punct:>=@1:2+1 | EOF:@1:4+3"},
    {"--",
        "Punct:-@1:1+0 | Punct:-@1:2+1 | EOF:@1:3+2"},
    {"&&&",
        "Punct:&&@1:1+0 | Punct:&@1:3+2 | EOF:@1:4+3"},
    {"|||",
        "Punct:||@1:1+0 | Punct:|@1:3+2 | EOF:@1:4+3"},
    {"!==",
        "Punct:!=@1:1+0 | Punct:=@1:3+2 | EOF:@1:4+3"},
    {"->->",
        "Punct:->@1:1+0 | Punct:->@1:3+2 | EOF:@1:5+4"},
    {"@",
        " !! 1:1 unexpected character"},
    {"a $ b",
        "Ident:a@1:1+0 !! 1:3 unexpected character"},
    {"`",
        " !! 1:1 unexpected character"},
    {"~",
        " !! 1:1 unexpected character"},
    {"é",
        " !! 1:1 unexpected character"},
    {"x ^",
        "Ident:x@1:1+0 !! 1:3 unexpected character"},
    {"ab\\n  \\\\",
        "Ident:ab@1:1+0 !! 2:3 unexpected character"},
    {"a ? b",
        "Ident:a@1:1+0 !! 1:3 unexpected character"},
    {"a \\"é\\" b\\n  c \\"日本語\\" d",
        "Ident:a@1:1+0 | String:\\"é\\"@1:3+2=\\"é\\" | Ident:b@1:7+7 | Ident:c@2:3+11 | String:\\"日本語\\"@2:5+13=\\"日本語\\" | Ident:d@2:11+25 | EOF:@2:12+26"},
    {"s = \\"ü\\"; t = 1",
        "Ident:s@1:1+0 | Punct:=@1:3+2 | String:\\"ü\\"@1:5+4=\\"ü\\" | Punct:;@1:8+8 | Ident:t@1:10+10 | Punct:=@1:12+12 | Int:1@1:14+14=1 | EOF:@1:15+15"},
    {"a\\r\\nb\\r\\n  c",
        "Ident:a@1:1+0 | Ident:b@2:1+3 | Ident:c@3:3+8 | EOF:@3:4+9"},
    {"a\\rb",
        "Ident:a@1:1+0 | Ident:b@1:2+2 | EOF:@1:3+3"},
    {"a\\n\\n\\nb",
        "Ident:a@1:1+0 | Ident:b@4:1+4 | EOF:@4:2+5"},
    {"\\n\\n  x",
        "Ident:x@3:3+4 | EOF:@3:4+5"},
    {"# service definition\\nservice \\"api-gateway\\" {\\n    port = 8_080\\n    timeout = 1m30s\\n    retries = 0x03\\n    tags = [\\"edge\\", \\"v2\\"]  /* inline */\\n    limit -> cpu: 250ms;\\n}\\n",
        "Ident:service@2:1+21 | String:\\"api-gateway\\"@2:9+29=\\"api-gateway\\" | Punct:{@2:23+43 | Ident:port@3:5+49 | Punct:=@3:10+54 | Int:8_080@3:12+56=8080 | Ident:timeout@4:5+66 | Punct:=@4:13+74 | Duration:1m30s@4:15+76=90000 | Ident:retries@5:5+86 | Punct:=@5:13+94 | Int:0x03@5:15+96=3 | Ident:tags@6:5+105 | Punct:=@6:10+110 | Punct:[@6:12+112 | String:\\"edge\\"@6:13+113=\\"edge\\" | Punct:,@6:19+119 | String:\\"v2\\"@6:21+121=\\"v2\\" | Punct:]@6:25+125 | Ident:limit@7:5+145 | Punct:->@7:11+151 | Ident:cpu@7:14+154 | Punct::@7:17+157 | Duration:250ms@7:19+159=250 | Punct:;@7:24+164 | Punct:}@8:1+166 | EOF:@9:1+168"},
    {"x = 1\\ny = \\"oops\\nz = 2",
        "Ident:x@1:1+0 | Punct:=@1:3+2 | Int:1@1:5+4=1 | Ident:y@2:1+6 | Punct:=@2:3+8 !! 2:5 unterminated string"},
    {"name = \\"ok\\"\\nsize = 12abc\\n",
        "Ident:name@1:1+0 | Punct:=@1:6+5 | String:\\"ok\\"@1:8+7=\\"ok\\" | Ident:size@2:1+12 | Punct:=@2:6+17 !! 2:8 bad duration unit"},
    {"a = 0x1F\\nb = 0b102\\n",
        "Ident:a@1:1+0 | Punct:=@1:3+2 | Int:0x1F@1:5+4=31 | Ident:b@2:1+9 | Punct:=@2:3+11 !! 2:9 bad number suffix"},
    {"k = 1_\\n",
        "Ident:k@1:1+0 | Punct:=@1:3+2 !! 1:6 bad digit separator"},
    {"key-with-dash = 1\\nother_key=2",
        "Ident:key-with-dash@1:1+0 | Punct:=@1:15+14 | Int:1@1:17+16=1 | Ident:other_key@2:1+18 | Punct:=@2:10+27 | Int:2@2:11+28=2 | EOF:@2:12+29"},
    {"a.b.c",
        "Ident:a@1:1+0 | Punct:.@1:2+1 | Ident:b@1:3+2 | Punct:.@1:4+3 | Ident:c@1:5+4 | EOF:@1:6+5"},
    {"f(1,2)",
        "Ident:f@1:1+0 | Punct:(@1:2+1 | Int:1@1:3+2=1 | Punct:,@1:4+3 | Int:2@1:5+4=2 | Punct:)@1:6+5 | EOF:@1:7+6"},
    {"x=-1",
        "Ident:x@1:1+0 | Punct:=@1:2+1 | Punct:-@1:3+2 | Int:1@1:4+3=1 | EOF:@1:5+4"},
    {"x==-1",
        "Ident:x@1:1+0 | Punct:==@1:2+1 | Punct:-@1:4+3 | Int:1@1:5+4=1 | EOF:@1:6+5"},
    {"a--b",
        "Ident:a@1:1+0 | Punct:-@1:2+1 | Punct:-@1:3+2 | Ident:b@1:4+3 | EOF:@1:5+4"},
    {"é # c\\n",
        " !! 1:1 unexpected character"},
    {"\\"a\\\\\\"\\" b",
        "String:\\"a\\\\\\"\\"@1:1+0=\\"a\\\\\\"\\" | Ident:b@1:7+6 | EOF:@1:8+7"},
    {"\\"\\\\\\\\\\" x",
        "String:\\"\\\\\\\\\\"@1:1+0=\\"\\\\\\\\\\" | Ident:x@1:6+5 | EOF:@1:7+6"},
    {"\\"\\\\\\\\\\\\\\"\\" x",
        "String:\\"\\\\\\\\\\\\\\"\\"@1:1+0=\\"\\\\\\\\\\\\\\"\\" | Ident:x@1:8+7 | EOF:@1:9+8"},
    {"az AZ za z Z A a _ __",
        "Ident:az@1:1+0 | Ident:AZ@1:4+3 | Ident:za@1:7+6 | Ident:z@1:10+9 | Ident:Z@1:12+11 | Ident:A@1:14+13 | Ident:a@1:16+15 | Ident:_@1:18+17 | Ident:__@1:20+19 | EOF:@1:22+21"},
    {"0xA0 0xa0 0xFf 0xfF 0xf 0xF 0x9 0xA",
        "Int:0xA0@1:1+0=160 | Int:0xa0@1:6+5=160 | Int:0xFf@1:11+10=255 | Int:0xfF@1:16+15=255 | Int:0xf@1:21+20=15 | Int:0xF@1:25+24=15 | Int:0x9@1:29+28=9 | Int:0xA@1:33+32=10 | EOF:@1:36+35"},
    {"0x1g",
        " !! 1:4 bad number suffix"},
    {"0xg",
        " !! 1:1 missing digits after prefix"},
    {"0xG",
        " !! 1:1 missing digits after prefix"},
    {"0b1 0B1",
        "Int:0b1@1:1+0=1 | Int:0B1@1:5+4=1 | EOF:@1:8+7"},
    {"x@y",
        "Ident:x@1:1+0 !! 1:2 unexpected character"},
    {"x[y",
        "Ident:x@1:1+0 | Punct:[@1:2+1 | Ident:y@1:3+2 | EOF:@1:4+3"},
    {"x`y",
        "Ident:x@1:1+0 !! 1:2 unexpected character"},
    {"x{y",
        "Ident:x@1:1+0 | Punct:{@1:2+1 | Ident:y@1:3+2 | EOF:@1:4+3"},
    {"\\"\\\\u 41}\\"",
        " !! 1:2 invalid unicode escape"},
    {"\\"\\\\uX41}\\"",
        " !! 1:2 invalid unicode escape"},
    {"\\"\\\\u(41}\\"",
        " !! 1:2 invalid unicode escape"},
    {"\\"\\\\u{0000041}\\"",
        " !! 1:2 invalid unicode escape"},
    {"\\"\\\\u{1234567}\\"",
        " !! 1:2 invalid unicode escape"},
    {"\\"\\\\u41}\\"",
        " !! 1:2 invalid unicode escape"},
    {"\\"ok\\\\u}\\"",
        " !! 1:4 invalid unicode escape"},
    {"/* /*/ */",
        " !! 1:1 unterminated block comment"},
    {"/* /*/ */ */ x",
        "Ident:x@1:14+13 | EOF:@1:15+14"},
    {"/*/ a */ b",
        "Ident:b@1:10+9 | EOF:@1:11+10"},
    {"/**/ a",
        "Ident:a@1:6+5 | EOF:@1:7+6"},
    {"/* /**/ */ a",
        "Ident:a@1:12+11 | EOF:@1:13+12"},
    {"/* /* */",
        " !! 1:1 unterminated block comment"},
    {"/*/",
        " !! 1:1 unterminated block comment"},
    {"18446744073709551616ms",
        " !! 1:1 duration too large"},
    {"99999999999999999999ms",
        " !! 1:1 duration too large"},
    {"1h99999999999999999999ms",
        " !! 1:1 duration too large"},
    {"18446744073709551615ms",
        "Duration:18446744073709551615ms@1:1+0=18446744073709551615 | EOF:@1:23+22"},
    {"1ms18446744073709551615ms",
        " !! 1:1 duration too large"},
    {"5s99999999999999999999s",
        " !! 1:1 duration too large"},
'''.strip('\n').split('\n')

HIDDEN = gosrc(dd(r'''
    package knotlex

    import (
        "fmt"
        "strconv"
        "strings"
        "testing"
    )

    func dump(src string) string {
        toks, err := Lex(src)
        var parts []string
        for _, t := range toks {
            d := fmt.Sprintf("%v:%s@%d:%d+%d", t.Kind, t.Text, t.Line, t.Col, t.Offset)
            switch t.Kind {
            case Int, Duration:
                d += fmt.Sprintf("=%d", t.Num)
            case String:
                d += "=" + strconv.Quote(t.Str)
            }
            parts = append(parts, d)
        }
        out := strings.Join(parts, " | ")
        if err != nil {
            e := err.(*Error)
            out += fmt.Sprintf(" !! %d:%d %s", e.Line, e.Col, e.Msg)
        }
        return out
    }

    var cases = []struct{ src, want string }{
    ''')) + gosrc("\n".join(CASES)) + "\n" + gosrc(dd(r'''
    }

    func TestLexTable(t *testing.T) {
        for _, c := range cases {
            if got := dump(c.src); got != c.want {
                t.Errorf("Lex(%q)\n got  %s\n want %s", c.src, got, c.want)
            }
        }
    }

    func TestErrorText(t *testing.T) {
        _, err := Lex("a\n  @")
        if err == nil || err.Error() != "2:3: unexpected character" {
            t.Errorf("got %v", err)
        }
        e, ok := err.(*Error)
        if !ok || e.Line != 2 || e.Col != 3 || e.Msg != "unexpected character" {
            t.Errorf("got %#v", err)
        }
    }

    func TestKindString(t *testing.T) {
        want := map[Kind]string{EOF: "EOF", Ident: "Ident", Int: "Int", Duration: "Duration", String: "String", Punct: "Punct"}
        for k, w := range want {
            if k.String() != w {
                t.Errorf("%d.String() = %q", int(k), k.String())
            }
        }
    }

    func TestTokensBeforeAnErrorAreReturned(t *testing.T) {
        toks, err := Lex("a = 1\nb = @")
        if err == nil || len(toks) != 5 || toks[4].Text != "=" {
            t.Fatalf("got %d tokens, %v", len(toks), err)
        }
        toks, err = Lex("ok \"unterminated")
        if err == nil || len(toks) != 1 || toks[0].Text != "ok" {
            t.Fatalf("got %+v, %v", toks, err)
        }
    }

    func TestLargestScalarValue(t *testing.T) {
        toks, err := Lex("\"\\u{10FFFF}\\u{000041}\"")
        if err != nil || toks[0].Str != string(rune(0x10FFFF))+"A" {
            t.Fatalf("got %+q, %v", toks, err)
        }
    }

    func TestLongInputIsLinear(t *testing.T) {
        src := strings.Repeat("name = \"value\" # comment\n", 4000)
        toks, err := Lex(src)
        if err != nil || len(toks) != 3*4000+1 {
            t.Fatalf("got %d tokens, %v", len(toks), err)
        }
        last := toks[len(toks)-1]
        if last.Kind != EOF || last.Line != 4001 || last.Col != 1 {
            t.Errorf("EOF at %d:%d", last.Line, last.Col)
        }
    }
'''))

LIB = Lib(
    name="knotlex", lang="go", title="the knotlex package",
    blurb="The deployment tool reads its configuration language with knotlex, a lexer that reports precise positions and understands duration literals and nested comments.",
    files={"go.mod": langs.go_mod("knotlex"), "knotlex.go": SRC, "README.md": README},
    visible_tests={"knotlex_basic_test.go": VISIBLE},
    hidden_tests={"knotlex_full_test.go": HIDDEN},
    mutate=["knotlex.go"], difficulty=4, tags=["lexer", "parsing", "positions"],
)

register_libs([LIB], n=8)
