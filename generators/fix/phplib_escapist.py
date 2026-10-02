"""Context-specific output escaping (php): HTML text, attributes, JavaScript strings, URL components and CSS, with strict UTF-8 handling; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # Esc

    Output escaping for a templating layer (`src/Esc.php`, class `Esc`, static methods). Every function takes a byte string and returns a byte string. Inputs are meant to be UTF-8: where a function
    has to look at characters, the **strict UTF-8 rules** below apply.

    **Strict UTF-8**: a character is 1 to 4 bytes (`00-7F`; `C2-DF` + 1 continuation; `E0-EF` + 2; `F0-F4` + 3, continuation bytes being `80-BF`) in the shortest form, not a surrogate
    (`U+D800-U+DFFF`) and not above `U+10FFFF`. Anything else is invalid: each byte of it (taken one at a time, re-trying the byte after it) counts as a single *invalid byte*.

    ## `Esc::html(string $s): string` - HTML text and quoted attribute values
    `&` becomes `&amp;`, `<` `&lt;`, `>` `&gt;`, `"` `&quot;`, `'` `&#39;`. The control characters other than tab (09), line feed (0A) and carriage return (0D), that is `00-08`, `0B`, `0C`, `0E-1F` and `7F`, are replaced by
    the replacement character U+FFFD (the UTF-8 bytes `EF BF BD`). Everything else, including valid and invalid UTF-8 bytes, is left alone.

    ## `Esc::attr(string $s): string` - unquoted-safe attribute values
    Every byte below `0x80` that is not an ASCII letter, a digit, or one of `,` `.` `_` `-` becomes `&#xHH;` (two **upper-case** hex digits of the byte, e.g. space is `&#x20;`, `<` is `&#x3C;`). Bytes `0x80` and above are left alone.

    ## `Esc::js(string $s): string` - inside a JavaScript string literal
    ASCII letters, digits and `,` `.` `_` `-` and the space are kept. Every other ASCII character becomes `\xHH` (two upper-case hex digits; `'` is `\x27`, a newline `\x0A`, NUL `\x00`).
    Every non-ASCII character becomes `\uHHHH` with four upper-case hex digits; a character above `U+FFFF` becomes the two escapes of its UTF-16 surrogate pair (`😀`). Each invalid byte becomes `�`.

    ## `Esc::url(string $s): string` - a URL component
    The unreserved characters (ASCII letters, digits, `-` `.` `_` `~`) are kept; every other **byte** (so every byte of a multi-byte character, and of invalid UTF-8) becomes `%HH` with two upper-case hex digits (space is `%20`).

    ## `Esc::css(string $s): string` - inside a CSS identifier or string
    ASCII letters, digits, `-` and `_` are kept, and so are bytes `0x80` and above. Every other ASCII character becomes a CSS hex escape: a backslash, the character's code in upper-case hex **without leading zeros**, and one space
    (`<` is `\3C `, tab is `\9 `, NUL is `\0 `, space is `\20 `).

    ## `Esc::unhtml(string $s): string` - the inverse for the entities above
    One left-to-right pass that replaces `&amp;` `&lt;` `&gt;` `&quot;` `&#39;`, **and** decimal `&#N;` (N is 1-7 digits) and hexadecimal `&#xH;` / `&#XH;` (1-6 hex digits, either case) character references by the character they stand for,
    written as UTF-8, provided the code point is valid (1 to `0x10FFFF`, not a surrogate); an invalid reference and any other `&...` text is left as it is. The output of a replacement is never looked at again
    (`&amp;lt;` becomes `&lt;`, not `<`).
''')

F2 = dd(r'''
    <?php
    declare(strict_types=1);

    class Esc
    {
        /** Decode one strict UTF-8 character at $pos; returns [codepoint|null, length]. null = invalid byte. */
        private static function decode(string $s, int $pos): array
        {
            $n = strlen($s);
            $c = ord($s[$pos]);
            if ($c < 0x80) {
                return [$c, 1];
            }
            if ($c >= 0xC2 && $c <= 0xDF) {
                $need = 1;
                $cp = $c & 0x1F;
                $min = 0x80;
            } elseif ($c >= 0xE0 && $c <= 0xEF) {
                $need = 2;
                $cp = $c & 0x0F;
                $min = 0x800;
            } elseif ($c >= 0xF0 && $c <= 0xF4) {
                $need = 3;
                $cp = $c & 0x07;
                $min = 0x10000;
            } else {
                return [null, 1];
            }
            if ($pos + $need >= $n) {
                return [null, 1];
            }
            for ($i = 1; $i <= $need; $i++) {
                $b = ord($s[$pos + $i]);
                if (($b & 0xC0) !== 0x80) {
                    return [null, 1];
                }
                $cp = ($cp << 6) | ($b & 0x3F);
            }
            if ($cp < $min || $cp > 0x10FFFF || ($cp >= 0xD800 && $cp <= 0xDFFF)) {
                return [null, 1];
            }
            return [$cp, $need + 1];
        }

        private static function hex2(int $b): string
        {
            return strtoupper(str_pad(dechex($b), 2, '0', STR_PAD_LEFT));
        }

        private static function isSafe(int $c): bool
        {
            return ($c >= 0x30 && $c <= 0x39) || ($c >= 0x41 && $c <= 0x5A) || ($c >= 0x61 && $c <= 0x7A);
        }

        public static function html(string $s): string
        {
            $out = '';
            $n = strlen($s);
            for ($i = 0; $i < $n; $i++) {
                $ch = $s[$i];
                $c = ord($ch);
                if ($ch === '&') {
                    $out .= '&amp;';
                } elseif ($ch === '<') {
                    $out .= '&lt;';
                } elseif ($ch === '>') {
                    $out .= '&gt;';
                } elseif ($ch === '"') {
                    $out .= '&quot;';
                } elseif ($ch === "'") {
                    $out .= '&#39;';
                } elseif (($c < 0x20 && $c !== 0x09 && $c !== 0x0A && $c !== 0x0D) || $c === 0x7F) {
                    $out .= "\xEF\xBF\xBD";
                } else {
                    $out .= $ch;
                }
            }
            return $out;
        }

        public static function attr(string $s): string
        {
            $out = '';
            $n = strlen($s);
            for ($i = 0; $i < $n; $i++) {
                $c = ord($s[$i]);
                if ($c >= 0x80 || self::isSafe($c) || $c === 0x2C || $c === 0x2E || $c === 0x5F || $c === 0x2D) {
                    $out .= $s[$i];
                } else {
                    $out .= '&#x' . self::hex2($c) . ';';
                }
            }
            return $out;
        }

        public static function js(string $s): string
        {
            $out = '';
            $n = strlen($s);
            $i = 0;
            while ($i < $n) {
                [$cp, $len] = self::decode($s, $i);
                $i += $len;
                if ($cp === null) {
                    $out .= '\\uFFFD';
                } elseif ($cp < 0x80) {
                    if (self::isSafe($cp) || $cp === 0x2C || $cp === 0x2E || $cp === 0x5F || $cp === 0x2D || $cp === 0x20) {
                        $out .= chr($cp);
                    } else {
                        $out .= '\\x' . self::hex2($cp);
                    }
                } elseif ($cp <= 0xFFFF) {
                    $out .= '\\u' . strtoupper(str_pad(dechex($cp), 4, '0', STR_PAD_LEFT));
                } else {
                    $v = $cp - 0x10000;
                    $hi = 0xD800 + ($v >> 10);
                    $lo = 0xDC00 + ($v & 0x3FF);
                    $out .= '\\u' . strtoupper(dechex($hi)) . '\\u' . strtoupper(dechex($lo));
                }
            }
            return $out;
        }

        public static function url(string $s): string
        {
            $out = '';
            $n = strlen($s);
            for ($i = 0; $i < $n; $i++) {
                $c = ord($s[$i]);
                if (self::isSafe($c) || $c === 0x2D || $c === 0x2E || $c === 0x5F || $c === 0x7E) {
                    $out .= $s[$i];
                } else {
                    $out .= '%' . self::hex2($c);
                }
            }
            return $out;
        }

        public static function css(string $s): string
        {
            $out = '';
            $n = strlen($s);
            for ($i = 0; $i < $n; $i++) {
                $c = ord($s[$i]);
                if ($c >= 0x80 || self::isSafe($c) || $c === 0x2D || $c === 0x5F) {
                    $out .= $s[$i];
                } else {
                    $out .= '\\' . strtoupper(dechex($c)) . ' ';
                }
            }
            return $out;
        }

        public static function unhtml(string $s): string
        {
            return preg_replace_callback('/&(amp|lt|gt|quot|#39|#[0-9]{1,7}|#[xX][0-9A-Fa-f]{1,6});/', function (array $m): string {
                $e = $m[1];
                switch ($e) {
                    case 'amp':
                        return '&';
                    case 'lt':
                        return '<';
                    case 'gt':
                        return '>';
                    case 'quot':
                        return '"';
                }
                $cp = ($e[1] === 'x' || $e[1] === 'X') ? hexdec(substr($e, 2)) : (int)substr($e, 1);
                if ($cp < 1 || $cp > 0x10FFFF || ($cp >= 0xD800 && $cp <= 0xDFFF)) {
                    return $m[0];
                }
                if ($cp < 0x80) {
                    return chr($cp);
                }
                if ($cp < 0x800) {
                    return chr(0xC0 | ($cp >> 6)) . chr(0x80 | ($cp & 0x3F));
                }
                if ($cp < 0x10000) {
                    return chr(0xE0 | ($cp >> 12)) . chr(0x80 | (($cp >> 6) & 0x3F)) . chr(0x80 | ($cp & 0x3F));
                }
                return chr(0xF0 | ($cp >> 18)) . chr(0x80 | (($cp >> 12) & 0x3F)) . chr(0x80 | (($cp >> 6) & 0x3F)) . chr(0x80 | ($cp & 0x3F));
            }, $s);
        }
    }
''')

V3 = dd(r'''
    require __DIR__ . '/../src/Esc.php';

    test('basics', function () {
        eq(Esc::html('<a href="x">Tom & Jerry\'s</a>'), '&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&#39;s&lt;/a&gt;');
        eq(Esc::url('a b/c'), 'a%20b%2Fc');
        eq(Esc::js("it's"), 'it\\x27s');
        eq(Esc::unhtml('&lt;b&gt;'), '<b>');
    });

    t_done();
''')

H4 = dd(r'''
    require __DIR__ . '/../src/Esc.php';

    $HTML = [
        ["\x00", "\xEF\xBF\xBD"],
        ["\x01", "\xEF\xBF\xBD"],
        ["\x02", "\xEF\xBF\xBD"],
        ["\x03", "\xEF\xBF\xBD"],
        ["\x04", "\xEF\xBF\xBD"],
        ["\x05", "\xEF\xBF\xBD"],
        ["\x06", "\xEF\xBF\xBD"],
        ["\x07", "\xEF\xBF\xBD"],
        ["\x08", "\xEF\xBF\xBD"],
        ["\x09", "\x09"],
        ["\x0A", "\x0A"],
        ["\x0B", "\xEF\xBF\xBD"],
        ["\x0C", "\xEF\xBF\xBD"],
        ["\x0D", "\x0D"],
        ["\x0E", "\xEF\xBF\xBD"],
        ["\x0F", "\xEF\xBF\xBD"],
        ["\x10", "\xEF\xBF\xBD"],
        ["\x11", "\xEF\xBF\xBD"],
        ["\x12", "\xEF\xBF\xBD"],
        ["\x13", "\xEF\xBF\xBD"],
        ["\x14", "\xEF\xBF\xBD"],
        ["\x15", "\xEF\xBF\xBD"],
        ["\x16", "\xEF\xBF\xBD"],
        ["\x17", "\xEF\xBF\xBD"],
        ["\x18", "\xEF\xBF\xBD"],
        ["\x19", "\xEF\xBF\xBD"],
        ["\x1A", "\xEF\xBF\xBD"],
        ["\x1B", "\xEF\xBF\xBD"],
        ["\x1C", "\xEF\xBF\xBD"],
        ["\x1D", "\xEF\xBF\xBD"],
        ["\x1E", "\xEF\xBF\xBD"],
        ["\x1F", "\xEF\xBF\xBD"],
        [" ", " "],
        ["!", "!"],
        ["\x22", "&quot;"],
        ["#", "#"],
        ["\x24", "\x24"],
        ["%", "%"],
        ["&", "&amp;"],
        ["'", "&#39;"],
        ["(", "("],
        [")", ")"],
        ["*", "*"],
        ["+", "+"],
        [",", ","],
        ["-", "-"],
        [".", "."],
        ["/", "/"],
        ["0", "0"],
        ["1", "1"],
        ["2", "2"],
        ["3", "3"],
        ["4", "4"],
        ["5", "5"],
        ["6", "6"],
        ["7", "7"],
        ["8", "8"],
        ["9", "9"],
        [":", ":"],
        [";", ";"],
        ["<", "&lt;"],
        ["=", "="],
        [">", "&gt;"],
        ["?", "?"],
        ["@", "@"],
        ["A", "A"],
        ["B", "B"],
        ["C", "C"],
        ["D", "D"],
        ["E", "E"],
        ["F", "F"],
        ["G", "G"],
        ["H", "H"],
        ["I", "I"],
        ["J", "J"],
        ["K", "K"],
        ["L", "L"],
        ["M", "M"],
        ["N", "N"],
        ["O", "O"],
        ["P", "P"],
        ["Q", "Q"],
        ["R", "R"],
        ["S", "S"],
        ["T", "T"],
        ["U", "U"],
        ["V", "V"],
        ["W", "W"],
        ["X", "X"],
        ["Y", "Y"],
        ["Z", "Z"],
        ["[", "["],
        ["\x5C", "\x5C"],
        ["]", "]"],
        ["^", "^"],
        ["_", "_"],
        ["`", "`"],
        ["a", "a"],
        ["b", "b"],
        ["c", "c"],
        ["d", "d"],
        ["e", "e"],
        ["f", "f"],
        ["g", "g"],
        ["h", "h"],
        ["i", "i"],
        ["j", "j"],
        ["k", "k"],
        ["l", "l"],
        ["m", "m"],
        ["n", "n"],
        ["o", "o"],
        ["p", "p"],
        ["q", "q"],
        ["r", "r"],
        ["s", "s"],
        ["t", "t"],
        ["u", "u"],
        ["v", "v"],
        ["w", "w"],
        ["x", "x"],
        ["y", "y"],
        ["z", "z"],
        ["{", "{"],
        ["|", "|"],
        ["}", "}"],
        ["~", "~"],
        ["\x7F", "\xEF\xBF\xBD"],
        ["\x80", "\x80"],
        ["\xBF", "\xBF"],
        ["\xC0", "\xC0"],
        ["\xC1", "\xC1"],
        ["\xC2", "\xC2"],
        ["\xDF", "\xDF"],
        ["\xE0", "\xE0"],
        ["\xEF", "\xEF"],
        ["\xF0", "\xF0"],
        ["\xF4", "\xF4"],
        ["\xF5", "\xF5"],
        ["\xFF", "\xFF"],
        ["\xC3\xA9", "\xC3\xA9"],
        ["\xE6\x97\xA5\xE6\x9C\xAC\xE8\xAA\x9E", "\xE6\x97\xA5\xE6\x9C\xAC\xE8\xAA\x9E"],
        ["\xF0\x9F\x98\x80", "\xF0\x9F\x98\x80"],
        ["a\xE2\x82\xACb", "a\xE2\x82\xACb"],
        ["\xCC\x80", "\xCC\x80"],
        ["\x7F", "\xEF\xBF\xBD"],
        ["\xC2\x80", "\xC2\x80"],
        ["\xDF\xBF", "\xDF\xBF"],
        ["\xE0\xA0\x80", "\xE0\xA0\x80"],
        ["\xEF\xBF\xBF", "\xEF\xBF\xBF"],
        ["\xF0\x90\x80\x80", "\xF0\x90\x80\x80"],
        ["\xF4\x8F\xBF\xBF", "\xF4\x8F\xBF\xBF"],
        ["\xED\x9F\xBF", "\xED\x9F\xBF"],
        ["\xEE\x80\x80", "\xEE\x80\x80"],
        ["\xC3", "\xC3"],
        ["\xE2\x82", "\xE2\x82"],
        ["\xE2(\xA1", "\xE2(\xA1"],
        ["\xF0\x9F\x98", "\xF0\x9F\x98"],
        ["\xC0\x80", "\xC0\x80"],
        ["\xE0\x80\x80", "\xE0\x80\x80"],
        ["\xE0\x9F\xBF", "\xE0\x9F\xBF"],
        ["\xED\xA0\x80", "\xED\xA0\x80"],
        ["\xED\xBF\xBF", "\xED\xBF\xBF"],
        ["\xF4\x90\x80\x80", "\xF4\x90\x80\x80"],
        ["\xF0\x80\x80\x80", "\xF0\x80\x80\x80"],
        ["a\xFFb", "a\xFFb"],
        ["\x80\x80", "\x80\x80"],
        ["\xC3\xC3\xA9", "\xC3\xC3\xA9"],
        ["\xF0\x9F\x98\x80\xF0", "\xF0\x9F\x98\x80\xF0"],
        ["\xE2\x82\xAC\xE2", "\xE2\x82\xAC\xE2"],
        ["ok\xC3", "ok\xC3"],
        ["\xEF\xBF\xBD", "\xEF\xBF\xBD"],
        ["", ""],
        ["plain text", "plain text"],
        ["<script>alert(1)</script>", "&lt;script&gt;alert(1)&lt;/script&gt;"],
        ["a&b<c>d\x22e'f", "a&amp;b&lt;c&gt;d&quot;e&#39;f"],
        ["Tom & Jerry's \x22show\x22", "Tom &amp; Jerry&#39;s &quot;show&quot;"],
        ["line1\x0Aline2\x0D\x0A\x09tabbed", "line1\x0Aline2\x0D\x0A\x09tabbed"],
        ["x=1;y='2'", "x=1;y=&#39;2&#39;"],
        ["path/to/file.txt?a=b&c=d#frag", "path/to/file.txt?a=b&amp;c=d#frag"],
        ["100% sure", "100% sure"],
        ["a b+c", "a b+c"],
        ["~tilde-dash_under.dot", "~tilde-dash_under.dot"],
        ["\x00\x01\x02\x7F\x1F", "\xEF\xBF\xBD\xEF\xBF\xBD\xEF\xBF\xBD\xEF\xBF\xBD\xEF\xBF\xBD"],
        ["</style><b>", "&lt;/style&gt;&lt;b&gt;"],
        ["\x5Cback\x5Cslash", "\x5Cback\x5Cslash"],
        ["{brace}\x24dollar", "{brace}\x24dollar"],
        [")\xEC\x22d\x8B\xD9\xC8\xE7\xE2\xDD", ")\xEC&quot;d\x8B\xD9\xC8\xE7\xE2\xDD"],
        ["=\x99\xF7\xC3\xE3v\xD8\xB9\xB6z", "=\x99\xF7\xC3\xE3v\xD8\xB9\xB6z"],
        ["\x88\xC9\xE2\xDCt\xD5\xCCr\x94\xE9_\x81", "\x88\xC9\xE2\xDCt\xD5\xCCr\x94\xE9_\x81"],
        ["\xFB\xCBI\x17\x0F\xA1x\xB8\xEF", "\xFB\xCBI\xEF\xBF\xBD\xEF\xBF\xBD\xA1x\xB8\xEF"],
        ["\xC4\xB7\x24dO\xDD", "\xC4\xB7\x24dO\xDD"],
        ["E)\x93\x90\x80`c", "E)\x93\x90\x80`c"],
        ["B\x91\x85\xEB\x9Cs)\xE0\xF0X\xC2", "B\x91\x85\xEB\x9Cs)\xE0\xF0X\xC2"],
        ["\xE8\xBB\xB8\xC3\xC2v0\xDD1", "\xE8\xBB\xB8\xC3\xC2v0\xDD1"],
        ["5\xB2c\xC6UO\x8A\x98", "5\xB2c\xC6UO\x8A\x98"],
        ["\x86\xEF\x22OuK\x90", "\x86\xEF&quot;OuK\x90"],
        ["\x91\xD9\x86\xEA\x8C-\xBC\x8D\xCA]\xD7\xA2", "\x91\xD9\x86\xEA\x8C-\xBC\x8D\xCA]\xD7\xA2"],
        ["\x17g\xC2\xD3y\xD8\x9C\xC4\x9A", "\xEF\xBF\xBDg\xC2\xD3y\xD8\x9C\xC4\x9A"],
        ["\xC5\xA6,\x8E\x87", "\xC5\xA6,\x8E\x87"],
        ["\xED\xD3\xC6\xDE!p\x86", "\xED\xD3\xC6\xDE!p\x86"],
        ["\xCFY\xB5Yd\xADk", "\xCFY\xB5Yd\xADk"],
        ["\x0D\xD9\xD5\xEAk\xE6\xDB\xE8!\x96\x24\xD0", "\x0D\xD9\xD5\xEAk\xE6\xDB\xE8!\x96\x24\xD0"],
        ["\xAC\x99\x08\x8DI\xBF\xDC", "\xAC\x99\xEF\xBF\xBD\x8DI\xBF\xDC"],
        ["3\x99\x17)\x97!\x97-", "3\x99\xEF\xBF\xBD)\x97!\x97-"],
        ["\xD3l\xA4\x84\x9D\xEB\xAD3`\xA0\x06\xDA", "\xD3l\xA4\x84\x9D\xEB\xAD3`\xA0\xEF\xBF\xBD\xDA"],
        ["\xE4B/\x9C\xE9\xB4", "\xE4B/\x9C\xE9\xB4"],
        ["'\xD2D\x24\xE5Y\xE7\xE4/\xE6", "&#39;\xD2D\x24\xE5Y\xE7\xE4/\xE6"],
        ["\x9Ae\xDBx\x81\xB8g;n\xEA\xDB\x8E", "\x9Ae\xDBx\x81\xB8g;n\xEA\xDB\x8E"],
        ["):\xD8C\xCF", "):\xD8C\xCF"],
        [")\xE9\xE6\xEB\xC2\xEA\xEFI\x81\xA9A", ")\xE9\xE6\xEB\xC2\xEA\xEFI\x81\xA9A"],
        ["\xC2", "\xC2"],
        ["\xCB\xD0", "\xCB\xD0"],
        ["4\xB2J\xC4P;8\xF6\xE2", "4\xB2J\xC4P;8\xF6\xE2"],
        ["\xBC\x7F\xF0/\x98\x7F", "\xBC\xEF\xBF\xBD\xF0/\x98\xEF\xBF\xBD"],
        ["\x22\xF0", "&quot;\xF0"],
        ["um>o\x95!\x9B\xD3\xD9\xC9@\x81", "um&gt;o\x95!\x9B\xD3\xD9\xC9@\x81"],
        ["t\x83\xD1\xF82", "t\x83\xD1\xF82"],
        ["s3E", "s3E"],
        ["\xE4_\x86", "\xE4_\x86"],
        ["p\xBBx\xED\xCC\x95\xF0", "p\xBBx\xED\xCC\x95\xF0"],
        ["\xCA\xFB\xAD+z\xDE\x16^", "\xCA\xFB\xAD+z\xDE\xEF\xBF\xBD^"],
        ["\x97B_k\x98\x975\xD5K\x99", "\x97B_k\x98\x975\xD5K\x99"],
        ["\x807\xDF'\xDE\xE6\xEE\xBD\xAB.", "\x807\xDF&#39;\xDE\xE6\xEE\xBD\xAB."],
        ["\xDA\x88\xCBz\x9Bj\xE4\xED", "\xDA\x88\xCBz\x9Bj\xE4\xED"],
        [" o\x8B", " o\x8B"],
        ["\xABk8", "\xABk8"],
    ];
    $ATTR = [
        ["\x00", "&#x00;"],
        ["\x01", "&#x01;"],
        ["\x02", "&#x02;"],
        ["\x03", "&#x03;"],
        ["\x04", "&#x04;"],
        ["\x05", "&#x05;"],
        ["\x06", "&#x06;"],
        ["\x07", "&#x07;"],
        ["\x08", "&#x08;"],
        ["\x09", "&#x09;"],
        ["\x0A", "&#x0A;"],
        ["\x0B", "&#x0B;"],
        ["\x0C", "&#x0C;"],
        ["\x0D", "&#x0D;"],
        ["\x0E", "&#x0E;"],
        ["\x0F", "&#x0F;"],
        ["\x10", "&#x10;"],
        ["\x11", "&#x11;"],
        ["\x12", "&#x12;"],
        ["\x13", "&#x13;"],
        ["\x14", "&#x14;"],
        ["\x15", "&#x15;"],
        ["\x16", "&#x16;"],
        ["\x17", "&#x17;"],
        ["\x18", "&#x18;"],
        ["\x19", "&#x19;"],
        ["\x1A", "&#x1A;"],
        ["\x1B", "&#x1B;"],
        ["\x1C", "&#x1C;"],
        ["\x1D", "&#x1D;"],
        ["\x1E", "&#x1E;"],
        ["\x1F", "&#x1F;"],
        [" ", "&#x20;"],
        ["!", "&#x21;"],
        ["\x22", "&#x22;"],
        ["#", "&#x23;"],
        ["\x24", "&#x24;"],
        ["%", "&#x25;"],
        ["&", "&#x26;"],
        ["'", "&#x27;"],
        ["(", "&#x28;"],
        [")", "&#x29;"],
        ["*", "&#x2A;"],
        ["+", "&#x2B;"],
        [",", ","],
        ["-", "-"],
        [".", "."],
        ["/", "&#x2F;"],
        ["0", "0"],
        ["1", "1"],
        ["2", "2"],
        ["3", "3"],
        ["4", "4"],
        ["5", "5"],
        ["6", "6"],
        ["7", "7"],
        ["8", "8"],
        ["9", "9"],
        [":", "&#x3A;"],
        [";", "&#x3B;"],
        ["<", "&#x3C;"],
        ["=", "&#x3D;"],
        [">", "&#x3E;"],
        ["?", "&#x3F;"],
        ["@", "&#x40;"],
        ["A", "A"],
        ["B", "B"],
        ["C", "C"],
        ["D", "D"],
        ["E", "E"],
        ["F", "F"],
        ["G", "G"],
        ["H", "H"],
        ["I", "I"],
        ["J", "J"],
        ["K", "K"],
        ["L", "L"],
        ["M", "M"],
        ["N", "N"],
        ["O", "O"],
        ["P", "P"],
        ["Q", "Q"],
        ["R", "R"],
        ["S", "S"],
        ["T", "T"],
        ["U", "U"],
        ["V", "V"],
        ["W", "W"],
        ["X", "X"],
        ["Y", "Y"],
        ["Z", "Z"],
        ["[", "&#x5B;"],
        ["\x5C", "&#x5C;"],
        ["]", "&#x5D;"],
        ["^", "&#x5E;"],
        ["_", "_"],
        ["`", "&#x60;"],
        ["a", "a"],
        ["b", "b"],
        ["c", "c"],
        ["d", "d"],
        ["e", "e"],
        ["f", "f"],
        ["g", "g"],
        ["h", "h"],
        ["i", "i"],
        ["j", "j"],
        ["k", "k"],
        ["l", "l"],
        ["m", "m"],
        ["n", "n"],
        ["o", "o"],
        ["p", "p"],
        ["q", "q"],
        ["r", "r"],
        ["s", "s"],
        ["t", "t"],
        ["u", "u"],
        ["v", "v"],
        ["w", "w"],
        ["x", "x"],
        ["y", "y"],
        ["z", "z"],
        ["{", "&#x7B;"],
        ["|", "&#x7C;"],
        ["}", "&#x7D;"],
        ["~", "&#x7E;"],
        ["\x7F", "&#x7F;"],
        ["\x80", "\x80"],
        ["\xBF", "\xBF"],
        ["\xC0", "\xC0"],
        ["\xC1", "\xC1"],
        ["\xC2", "\xC2"],
        ["\xDF", "\xDF"],
        ["\xE0", "\xE0"],
        ["\xEF", "\xEF"],
        ["\xF0", "\xF0"],
        ["\xF4", "\xF4"],
        ["\xF5", "\xF5"],
        ["\xFF", "\xFF"],
        ["\xC3\xA9", "\xC3\xA9"],
        ["\xE6\x97\xA5\xE6\x9C\xAC\xE8\xAA\x9E", "\xE6\x97\xA5\xE6\x9C\xAC\xE8\xAA\x9E"],
        ["\xF0\x9F\x98\x80", "\xF0\x9F\x98\x80"],
        ["a\xE2\x82\xACb", "a\xE2\x82\xACb"],
        ["\xCC\x80", "\xCC\x80"],
        ["\x7F", "&#x7F;"],
        ["\xC2\x80", "\xC2\x80"],
        ["\xDF\xBF", "\xDF\xBF"],
        ["\xE0\xA0\x80", "\xE0\xA0\x80"],
        ["\xEF\xBF\xBF", "\xEF\xBF\xBF"],
        ["\xF0\x90\x80\x80", "\xF0\x90\x80\x80"],
        ["\xF4\x8F\xBF\xBF", "\xF4\x8F\xBF\xBF"],
        ["\xED\x9F\xBF", "\xED\x9F\xBF"],
        ["\xEE\x80\x80", "\xEE\x80\x80"],
        ["\xC3", "\xC3"],
        ["\xE2\x82", "\xE2\x82"],
        ["\xE2(\xA1", "\xE2&#x28;\xA1"],
        ["\xF0\x9F\x98", "\xF0\x9F\x98"],
        ["\xC0\x80", "\xC0\x80"],
        ["\xE0\x80\x80", "\xE0\x80\x80"],
        ["\xE0\x9F\xBF", "\xE0\x9F\xBF"],
        ["\xED\xA0\x80", "\xED\xA0\x80"],
        ["\xED\xBF\xBF", "\xED\xBF\xBF"],
        ["\xF4\x90\x80\x80", "\xF4\x90\x80\x80"],
        ["\xF0\x80\x80\x80", "\xF0\x80\x80\x80"],
        ["a\xFFb", "a\xFFb"],
        ["\x80\x80", "\x80\x80"],
        ["\xC3\xC3\xA9", "\xC3\xC3\xA9"],
        ["\xF0\x9F\x98\x80\xF0", "\xF0\x9F\x98\x80\xF0"],
        ["\xE2\x82\xAC\xE2", "\xE2\x82\xAC\xE2"],
        ["ok\xC3", "ok\xC3"],
        ["\xEF\xBF\xBD", "\xEF\xBF\xBD"],
        ["", ""],
        ["plain text", "plain&#x20;text"],
        ["<script>alert(1)</script>", "&#x3C;script&#x3E;alert&#x28;1&#x29;&#x3C;&#x2F;script&#x3E;"],
        ["a&b<c>d\x22e'f", "a&#x26;b&#x3C;c&#x3E;d&#x22;e&#x27;f"],
        ["Tom & Jerry's \x22show\x22", "Tom&#x20;&#x26;&#x20;Jerry&#x27;s&#x20;&#x22;show&#x22;"],
        ["line1\x0Aline2\x0D\x0A\x09tabbed", "line1&#x0A;line2&#x0D;&#x0A;&#x09;tabbed"],
        ["x=1;y='2'", "x&#x3D;1&#x3B;y&#x3D;&#x27;2&#x27;"],
        ["path/to/file.txt?a=b&c=d#frag", "path&#x2F;to&#x2F;file.txt&#x3F;a&#x3D;b&#x26;c&#x3D;d&#x23;frag"],
        ["100% sure", "100&#x25;&#x20;sure"],
        ["a b+c", "a&#x20;b&#x2B;c"],
        ["~tilde-dash_under.dot", "&#x7E;tilde-dash_under.dot"],
        ["\x00\x01\x02\x7F\x1F", "&#x00;&#x01;&#x02;&#x7F;&#x1F;"],
        ["</style><b>", "&#x3C;&#x2F;style&#x3E;&#x3C;b&#x3E;"],
        ["\x5Cback\x5Cslash", "&#x5C;back&#x5C;slash"],
        ["{brace}\x24dollar", "&#x7B;brace&#x7D;&#x24;dollar"],
        [")\xEC\x22d\x8B\xD9\xC8\xE7\xE2\xDD", "&#x29;\xEC&#x22;d\x8B\xD9\xC8\xE7\xE2\xDD"],
        ["=\x99\xF7\xC3\xE3v\xD8\xB9\xB6z", "&#x3D;\x99\xF7\xC3\xE3v\xD8\xB9\xB6z"],
        ["\x88\xC9\xE2\xDCt\xD5\xCCr\x94\xE9_\x81", "\x88\xC9\xE2\xDCt\xD5\xCCr\x94\xE9_\x81"],
        ["\xFB\xCBI\x17\x0F\xA1x\xB8\xEF", "\xFB\xCBI&#x17;&#x0F;\xA1x\xB8\xEF"],
        ["\xC4\xB7\x24dO\xDD", "\xC4\xB7&#x24;dO\xDD"],
        ["E)\x93\x90\x80`c", "E&#x29;\x93\x90\x80&#x60;c"],
        ["B\x91\x85\xEB\x9Cs)\xE0\xF0X\xC2", "B\x91\x85\xEB\x9Cs&#x29;\xE0\xF0X\xC2"],
        ["\xE8\xBB\xB8\xC3\xC2v0\xDD1", "\xE8\xBB\xB8\xC3\xC2v0\xDD1"],
        ["5\xB2c\xC6UO\x8A\x98", "5\xB2c\xC6UO\x8A\x98"],
        ["\x86\xEF\x22OuK\x90", "\x86\xEF&#x22;OuK\x90"],
        ["\x91\xD9\x86\xEA\x8C-\xBC\x8D\xCA]\xD7\xA2", "\x91\xD9\x86\xEA\x8C-\xBC\x8D\xCA&#x5D;\xD7\xA2"],
        ["\x17g\xC2\xD3y\xD8\x9C\xC4\x9A", "&#x17;g\xC2\xD3y\xD8\x9C\xC4\x9A"],
        ["\xC5\xA6,\x8E\x87", "\xC5\xA6,\x8E\x87"],
        ["\xED\xD3\xC6\xDE!p\x86", "\xED\xD3\xC6\xDE&#x21;p\x86"],
        ["\xCFY\xB5Yd\xADk", "\xCFY\xB5Yd\xADk"],
        ["\x0D\xD9\xD5\xEAk\xE6\xDB\xE8!\x96\x24\xD0", "&#x0D;\xD9\xD5\xEAk\xE6\xDB\xE8&#x21;\x96&#x24;\xD0"],
        ["\xAC\x99\x08\x8DI\xBF\xDC", "\xAC\x99&#x08;\x8DI\xBF\xDC"],
        ["3\x99\x17)\x97!\x97-", "3\x99&#x17;&#x29;\x97&#x21;\x97-"],
        ["\xD3l\xA4\x84\x9D\xEB\xAD3`\xA0\x06\xDA", "\xD3l\xA4\x84\x9D\xEB\xAD3&#x60;\xA0&#x06;\xDA"],
        ["\xE4B/\x9C\xE9\xB4", "\xE4B&#x2F;\x9C\xE9\xB4"],
        ["'\xD2D\x24\xE5Y\xE7\xE4/\xE6", "&#x27;\xD2D&#x24;\xE5Y\xE7\xE4&#x2F;\xE6"],
        ["\x9Ae\xDBx\x81\xB8g;n\xEA\xDB\x8E", "\x9Ae\xDBx\x81\xB8g&#x3B;n\xEA\xDB\x8E"],
        ["):\xD8C\xCF", "&#x29;&#x3A;\xD8C\xCF"],
        [")\xE9\xE6\xEB\xC2\xEA\xEFI\x81\xA9A", "&#x29;\xE9\xE6\xEB\xC2\xEA\xEFI\x81\xA9A"],
        ["\xC2", "\xC2"],
        ["\xCB\xD0", "\xCB\xD0"],
        ["4\xB2J\xC4P;8\xF6\xE2", "4\xB2J\xC4P&#x3B;8\xF6\xE2"],
        ["\xBC\x7F\xF0/\x98\x7F", "\xBC&#x7F;\xF0&#x2F;\x98&#x7F;"],
        ["\x22\xF0", "&#x22;\xF0"],
        ["um>o\x95!\x9B\xD3\xD9\xC9@\x81", "um&#x3E;o\x95&#x21;\x9B\xD3\xD9\xC9&#x40;\x81"],
        ["t\x83\xD1\xF82", "t\x83\xD1\xF82"],
        ["s3E", "s3E"],
        ["\xE4_\x86", "\xE4_\x86"],
        ["p\xBBx\xED\xCC\x95\xF0", "p\xBBx\xED\xCC\x95\xF0"],
        ["\xCA\xFB\xAD+z\xDE\x16^", "\xCA\xFB\xAD&#x2B;z\xDE&#x16;&#x5E;"],
        ["\x97B_k\x98\x975\xD5K\x99", "\x97B_k\x98\x975\xD5K\x99"],
        ["\x807\xDF'\xDE\xE6\xEE\xBD\xAB.", "\x807\xDF&#x27;\xDE\xE6\xEE\xBD\xAB."],
        ["\xDA\x88\xCBz\x9Bj\xE4\xED", "\xDA\x88\xCBz\x9Bj\xE4\xED"],
        [" o\x8B", "&#x20;o\x8B"],
        ["\xABk8", "\xABk8"],
    ];
    $JS = [
        ["\x00", "\x5Cx00"],
        ["\x01", "\x5Cx01"],
        ["\x02", "\x5Cx02"],
        ["\x03", "\x5Cx03"],
        ["\x04", "\x5Cx04"],
        ["\x05", "\x5Cx05"],
        ["\x06", "\x5Cx06"],
        ["\x07", "\x5Cx07"],
        ["\x08", "\x5Cx08"],
        ["\x09", "\x5Cx09"],
        ["\x0A", "\x5Cx0A"],
        ["\x0B", "\x5Cx0B"],
        ["\x0C", "\x5Cx0C"],
        ["\x0D", "\x5Cx0D"],
        ["\x0E", "\x5Cx0E"],
        ["\x0F", "\x5Cx0F"],
        ["\x10", "\x5Cx10"],
        ["\x11", "\x5Cx11"],
        ["\x12", "\x5Cx12"],
        ["\x13", "\x5Cx13"],
        ["\x14", "\x5Cx14"],
        ["\x15", "\x5Cx15"],
        ["\x16", "\x5Cx16"],
        ["\x17", "\x5Cx17"],
        ["\x18", "\x5Cx18"],
        ["\x19", "\x5Cx19"],
        ["\x1A", "\x5Cx1A"],
        ["\x1B", "\x5Cx1B"],
        ["\x1C", "\x5Cx1C"],
        ["\x1D", "\x5Cx1D"],
        ["\x1E", "\x5Cx1E"],
        ["\x1F", "\x5Cx1F"],
        [" ", " "],
        ["!", "\x5Cx21"],
        ["\x22", "\x5Cx22"],
        ["#", "\x5Cx23"],
        ["\x24", "\x5Cx24"],
        ["%", "\x5Cx25"],
        ["&", "\x5Cx26"],
        ["'", "\x5Cx27"],
        ["(", "\x5Cx28"],
        [")", "\x5Cx29"],
        ["*", "\x5Cx2A"],
        ["+", "\x5Cx2B"],
        [",", ","],
        ["-", "-"],
        [".", "."],
        ["/", "\x5Cx2F"],
        ["0", "0"],
        ["1", "1"],
        ["2", "2"],
        ["3", "3"],
        ["4", "4"],
        ["5", "5"],
        ["6", "6"],
        ["7", "7"],
        ["8", "8"],
        ["9", "9"],
        [":", "\x5Cx3A"],
        [";", "\x5Cx3B"],
        ["<", "\x5Cx3C"],
        ["=", "\x5Cx3D"],
        [">", "\x5Cx3E"],
        ["?", "\x5Cx3F"],
        ["@", "\x5Cx40"],
        ["A", "A"],
        ["B", "B"],
        ["C", "C"],
        ["D", "D"],
        ["E", "E"],
        ["F", "F"],
        ["G", "G"],
        ["H", "H"],
        ["I", "I"],
        ["J", "J"],
        ["K", "K"],
        ["L", "L"],
        ["M", "M"],
        ["N", "N"],
        ["O", "O"],
        ["P", "P"],
        ["Q", "Q"],
        ["R", "R"],
        ["S", "S"],
        ["T", "T"],
        ["U", "U"],
        ["V", "V"],
        ["W", "W"],
        ["X", "X"],
        ["Y", "Y"],
        ["Z", "Z"],
        ["[", "\x5Cx5B"],
        ["\x5C", "\x5Cx5C"],
        ["]", "\x5Cx5D"],
        ["^", "\x5Cx5E"],
        ["_", "_"],
        ["`", "\x5Cx60"],
        ["a", "a"],
        ["b", "b"],
        ["c", "c"],
        ["d", "d"],
        ["e", "e"],
        ["f", "f"],
        ["g", "g"],
        ["h", "h"],
        ["i", "i"],
        ["j", "j"],
        ["k", "k"],
        ["l", "l"],
        ["m", "m"],
        ["n", "n"],
        ["o", "o"],
        ["p", "p"],
        ["q", "q"],
        ["r", "r"],
        ["s", "s"],
        ["t", "t"],
        ["u", "u"],
        ["v", "v"],
        ["w", "w"],
        ["x", "x"],
        ["y", "y"],
        ["z", "z"],
        ["{", "\x5Cx7B"],
        ["|", "\x5Cx7C"],
        ["}", "\x5Cx7D"],
        ["~", "\x5Cx7E"],
        ["\x7F", "\x5Cx7F"],
        ["\x80", "\x5CuFFFD"],
        ["\xBF", "\x5CuFFFD"],
        ["\xC0", "\x5CuFFFD"],
        ["\xC1", "\x5CuFFFD"],
        ["\xC2", "\x5CuFFFD"],
        ["\xDF", "\x5CuFFFD"],
        ["\xE0", "\x5CuFFFD"],
        ["\xEF", "\x5CuFFFD"],
        ["\xF0", "\x5CuFFFD"],
        ["\xF4", "\x5CuFFFD"],
        ["\xF5", "\x5CuFFFD"],
        ["\xFF", "\x5CuFFFD"],
        ["\xC3\xA9", "\x5Cu00E9"],
        ["\xE6\x97\xA5\xE6\x9C\xAC\xE8\xAA\x9E", "\x5Cu65E5\x5Cu672C\x5Cu8A9E"],
        ["\xF0\x9F\x98\x80", "\x5CuD83D\x5CuDE00"],
        ["a\xE2\x82\xACb", "a\x5Cu20ACb"],
        ["\xCC\x80", "\x5Cu0300"],
        ["\x7F", "\x5Cx7F"],
        ["\xC2\x80", "\x5Cu0080"],
        ["\xDF\xBF", "\x5Cu07FF"],
        ["\xE0\xA0\x80", "\x5Cu0800"],
        ["\xEF\xBF\xBF", "\x5CuFFFF"],
        ["\xF0\x90\x80\x80", "\x5CuD800\x5CuDC00"],
        ["\xF4\x8F\xBF\xBF", "\x5CuDBFF\x5CuDFFF"],
        ["\xED\x9F\xBF", "\x5CuD7FF"],
        ["\xEE\x80\x80", "\x5CuE000"],
        ["\xC3", "\x5CuFFFD"],
        ["\xE2\x82", "\x5CuFFFD\x5CuFFFD"],
        ["\xE2(\xA1", "\x5CuFFFD\x5Cx28\x5CuFFFD"],
        ["\xF0\x9F\x98", "\x5CuFFFD\x5CuFFFD\x5CuFFFD"],
        ["\xC0\x80", "\x5CuFFFD\x5CuFFFD"],
        ["\xE0\x80\x80", "\x5CuFFFD\x5CuFFFD\x5CuFFFD"],
        ["\xE0\x9F\xBF", "\x5CuFFFD\x5CuFFFD\x5CuFFFD"],
        ["\xED\xA0\x80", "\x5CuFFFD\x5CuFFFD\x5CuFFFD"],
        ["\xED\xBF\xBF", "\x5CuFFFD\x5CuFFFD\x5CuFFFD"],
        ["\xF4\x90\x80\x80", "\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFD"],
        ["\xF0\x80\x80\x80", "\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFD"],
        ["a\xFFb", "a\x5CuFFFDb"],
        ["\x80\x80", "\x5CuFFFD\x5CuFFFD"],
        ["\xC3\xC3\xA9", "\x5CuFFFD\x5Cu00E9"],
        ["\xF0\x9F\x98\x80\xF0", "\x5CuD83D\x5CuDE00\x5CuFFFD"],
        ["\xE2\x82\xAC\xE2", "\x5Cu20AC\x5CuFFFD"],
        ["ok\xC3", "ok\x5CuFFFD"],
        ["\xEF\xBF\xBD", "\x5CuFFFD"],
        ["", ""],
        ["plain text", "plain text"],
        ["<script>alert(1)</script>", "\x5Cx3Cscript\x5Cx3Ealert\x5Cx281\x5Cx29\x5Cx3C\x5Cx2Fscript\x5Cx3E"],
        ["a&b<c>d\x22e'f", "a\x5Cx26b\x5Cx3Cc\x5Cx3Ed\x5Cx22e\x5Cx27f"],
        ["Tom & Jerry's \x22show\x22", "Tom \x5Cx26 Jerry\x5Cx27s \x5Cx22show\x5Cx22"],
        ["line1\x0Aline2\x0D\x0A\x09tabbed", "line1\x5Cx0Aline2\x5Cx0D\x5Cx0A\x5Cx09tabbed"],
        ["x=1;y='2'", "x\x5Cx3D1\x5Cx3By\x5Cx3D\x5Cx272\x5Cx27"],
        ["path/to/file.txt?a=b&c=d#frag", "path\x5Cx2Fto\x5Cx2Ffile.txt\x5Cx3Fa\x5Cx3Db\x5Cx26c\x5Cx3Dd\x5Cx23frag"],
        ["100% sure", "100\x5Cx25 sure"],
        ["a b+c", "a b\x5Cx2Bc"],
        ["~tilde-dash_under.dot", "\x5Cx7Etilde-dash_under.dot"],
        ["\x00\x01\x02\x7F\x1F", "\x5Cx00\x5Cx01\x5Cx02\x5Cx7F\x5Cx1F"],
        ["</style><b>", "\x5Cx3C\x5Cx2Fstyle\x5Cx3E\x5Cx3Cb\x5Cx3E"],
        ["\x5Cback\x5Cslash", "\x5Cx5Cback\x5Cx5Cslash"],
        ["{brace}\x24dollar", "\x5Cx7Bbrace\x5Cx7D\x5Cx24dollar"],
        [")\xEC\x22d\x8B\xD9\xC8\xE7\xE2\xDD", "\x5Cx29\x5CuFFFD\x5Cx22d\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFD"],
        ["=\x99\xF7\xC3\xE3v\xD8\xB9\xB6z", "\x5Cx3D\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFDv\x5Cu0639\x5CuFFFDz"],
        ["\x88\xC9\xE2\xDCt\xD5\xCCr\x94\xE9_\x81", "\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFDt\x5CuFFFD\x5CuFFFDr\x5CuFFFD\x5CuFFFD_\x5CuFFFD"],
        ["\xFB\xCBI\x17\x0F\xA1x\xB8\xEF", "\x5CuFFFD\x5CuFFFDI\x5Cx17\x5Cx0F\x5CuFFFDx\x5CuFFFD\x5CuFFFD"],
        ["\xC4\xB7\x24dO\xDD", "\x5Cu0137\x5Cx24dO\x5CuFFFD"],
        ["E)\x93\x90\x80`c", "E\x5Cx29\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5Cx60c"],
        ["B\x91\x85\xEB\x9Cs)\xE0\xF0X\xC2", "B\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFDs\x5Cx29\x5CuFFFD\x5CuFFFDX\x5CuFFFD"],
        ["\xE8\xBB\xB8\xC3\xC2v0\xDD1", "\x5Cu8EF8\x5CuFFFD\x5CuFFFDv0\x5CuFFFD1"],
        ["5\xB2c\xC6UO\x8A\x98", "5\x5CuFFFDc\x5CuFFFDUO\x5CuFFFD\x5CuFFFD"],
        ["\x86\xEF\x22OuK\x90", "\x5CuFFFD\x5CuFFFD\x5Cx22OuK\x5CuFFFD"],
        ["\x91\xD9\x86\xEA\x8C-\xBC\x8D\xCA]\xD7\xA2", "\x5CuFFFD\x5Cu0646\x5CuFFFD\x5CuFFFD-\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5Cx5D\x5Cu05E2"],
        ["\x17g\xC2\xD3y\xD8\x9C\xC4\x9A", "\x5Cx17g\x5CuFFFD\x5CuFFFDy\x5Cu061C\x5Cu011A"],
        ["\xC5\xA6,\x8E\x87", "\x5Cu0166,\x5CuFFFD\x5CuFFFD"],
        ["\xED\xD3\xC6\xDE!p\x86", "\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5Cx21p\x5CuFFFD"],
        ["\xCFY\xB5Yd\xADk", "\x5CuFFFDY\x5CuFFFDYd\x5CuFFFDk"],
        ["\x0D\xD9\xD5\xEAk\xE6\xDB\xE8!\x96\x24\xD0", "\x5Cx0D\x5CuFFFD\x5CuFFFD\x5CuFFFDk\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5Cx21\x5CuFFFD\x5Cx24\x5CuFFFD"],
        ["\xAC\x99\x08\x8DI\xBF\xDC", "\x5CuFFFD\x5CuFFFD\x5Cx08\x5CuFFFDI\x5CuFFFD\x5CuFFFD"],
        ["3\x99\x17)\x97!\x97-", "3\x5CuFFFD\x5Cx17\x5Cx29\x5CuFFFD\x5Cx21\x5CuFFFD-"],
        ["\xD3l\xA4\x84\x9D\xEB\xAD3`\xA0\x06\xDA", "\x5CuFFFDl\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFD3\x5Cx60\x5CuFFFD\x5Cx06\x5CuFFFD"],
        ["\xE4B/\x9C\xE9\xB4", "\x5CuFFFDB\x5Cx2F\x5CuFFFD\x5CuFFFD\x5CuFFFD"],
        ["'\xD2D\x24\xE5Y\xE7\xE4/\xE6", "\x5Cx27\x5CuFFFDD\x5Cx24\x5CuFFFDY\x5CuFFFD\x5CuFFFD\x5Cx2F\x5CuFFFD"],
        ["\x9Ae\xDBx\x81\xB8g;n\xEA\xDB\x8E", "\x5CuFFFDe\x5CuFFFDx\x5CuFFFD\x5CuFFFDg\x5Cx3Bn\x5CuFFFD\x5Cu06CE"],
        ["):\xD8C\xCF", "\x5Cx29\x5Cx3A\x5CuFFFDC\x5CuFFFD"],
        [")\xE9\xE6\xEB\xC2\xEA\xEFI\x81\xA9A", "\x5Cx29\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFDI\x5CuFFFD\x5CuFFFDA"],
        ["\xC2", "\x5CuFFFD"],
        ["\xCB\xD0", "\x5CuFFFD\x5CuFFFD"],
        ["4\xB2J\xC4P;8\xF6\xE2", "4\x5CuFFFDJ\x5CuFFFDP\x5Cx3B8\x5CuFFFD\x5CuFFFD"],
        ["\xBC\x7F\xF0/\x98\x7F", "\x5CuFFFD\x5Cx7F\x5CuFFFD\x5Cx2F\x5CuFFFD\x5Cx7F"],
        ["\x22\xF0", "\x5Cx22\x5CuFFFD"],
        ["um>o\x95!\x9B\xD3\xD9\xC9@\x81", "um\x5Cx3Eo\x5CuFFFD\x5Cx21\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5Cx40\x5CuFFFD"],
        ["t\x83\xD1\xF82", "t\x5CuFFFD\x5CuFFFD\x5CuFFFD2"],
        ["s3E", "s3E"],
        ["\xE4_\x86", "\x5CuFFFD_\x5CuFFFD"],
        ["p\xBBx\xED\xCC\x95\xF0", "p\x5CuFFFDx\x5CuFFFD\x5Cu0315\x5CuFFFD"],
        ["\xCA\xFB\xAD+z\xDE\x16^", "\x5CuFFFD\x5CuFFFD\x5CuFFFD\x5Cx2Bz\x5CuFFFD\x5Cx16\x5Cx5E"],
        ["\x97B_k\x98\x975\xD5K\x99", "\x5CuFFFDB_k\x5CuFFFD\x5CuFFFD5\x5CuFFFDK\x5CuFFFD"],
        ["\x807\xDF'\xDE\xE6\xEE\xBD\xAB.", "\x5CuFFFD7\x5CuFFFD\x5Cx27\x5CuFFFD\x5CuFFFD\x5CuEF6B."],
        ["\xDA\x88\xCBz\x9Bj\xE4\xED", "\x5Cu0688\x5CuFFFDz\x5CuFFFDj\x5CuFFFD\x5CuFFFD"],
        [" o\x8B", " o\x5CuFFFD"],
        ["\xABk8", "\x5CuFFFDk8"],
    ];
    $URL = [
        ["\x00", "%00"],
        ["\x01", "%01"],
        ["\x02", "%02"],
        ["\x03", "%03"],
        ["\x04", "%04"],
        ["\x05", "%05"],
        ["\x06", "%06"],
        ["\x07", "%07"],
        ["\x08", "%08"],
        ["\x09", "%09"],
        ["\x0A", "%0A"],
        ["\x0B", "%0B"],
        ["\x0C", "%0C"],
        ["\x0D", "%0D"],
        ["\x0E", "%0E"],
        ["\x0F", "%0F"],
        ["\x10", "%10"],
        ["\x11", "%11"],
        ["\x12", "%12"],
        ["\x13", "%13"],
        ["\x14", "%14"],
        ["\x15", "%15"],
        ["\x16", "%16"],
        ["\x17", "%17"],
        ["\x18", "%18"],
        ["\x19", "%19"],
        ["\x1A", "%1A"],
        ["\x1B", "%1B"],
        ["\x1C", "%1C"],
        ["\x1D", "%1D"],
        ["\x1E", "%1E"],
        ["\x1F", "%1F"],
        [" ", "%20"],
        ["!", "%21"],
        ["\x22", "%22"],
        ["#", "%23"],
        ["\x24", "%24"],
        ["%", "%25"],
        ["&", "%26"],
        ["'", "%27"],
        ["(", "%28"],
        [")", "%29"],
        ["*", "%2A"],
        ["+", "%2B"],
        [",", "%2C"],
        ["-", "-"],
        [".", "."],
        ["/", "%2F"],
        ["0", "0"],
        ["1", "1"],
        ["2", "2"],
        ["3", "3"],
        ["4", "4"],
        ["5", "5"],
        ["6", "6"],
        ["7", "7"],
        ["8", "8"],
        ["9", "9"],
        [":", "%3A"],
        [";", "%3B"],
        ["<", "%3C"],
        ["=", "%3D"],
        [">", "%3E"],
        ["?", "%3F"],
        ["@", "%40"],
        ["A", "A"],
        ["B", "B"],
        ["C", "C"],
        ["D", "D"],
        ["E", "E"],
        ["F", "F"],
        ["G", "G"],
        ["H", "H"],
        ["I", "I"],
        ["J", "J"],
        ["K", "K"],
        ["L", "L"],
        ["M", "M"],
        ["N", "N"],
        ["O", "O"],
        ["P", "P"],
        ["Q", "Q"],
        ["R", "R"],
        ["S", "S"],
        ["T", "T"],
        ["U", "U"],
        ["V", "V"],
        ["W", "W"],
        ["X", "X"],
        ["Y", "Y"],
        ["Z", "Z"],
        ["[", "%5B"],
        ["\x5C", "%5C"],
        ["]", "%5D"],
        ["^", "%5E"],
        ["_", "_"],
        ["`", "%60"],
        ["a", "a"],
        ["b", "b"],
        ["c", "c"],
        ["d", "d"],
        ["e", "e"],
        ["f", "f"],
        ["g", "g"],
        ["h", "h"],
        ["i", "i"],
        ["j", "j"],
        ["k", "k"],
        ["l", "l"],
        ["m", "m"],
        ["n", "n"],
        ["o", "o"],
        ["p", "p"],
        ["q", "q"],
        ["r", "r"],
        ["s", "s"],
        ["t", "t"],
        ["u", "u"],
        ["v", "v"],
        ["w", "w"],
        ["x", "x"],
        ["y", "y"],
        ["z", "z"],
        ["{", "%7B"],
        ["|", "%7C"],
        ["}", "%7D"],
        ["~", "~"],
        ["\x7F", "%7F"],
        ["\x80", "%80"],
        ["\xBF", "%BF"],
        ["\xC0", "%C0"],
        ["\xC1", "%C1"],
        ["\xC2", "%C2"],
        ["\xDF", "%DF"],
        ["\xE0", "%E0"],
        ["\xEF", "%EF"],
        ["\xF0", "%F0"],
        ["\xF4", "%F4"],
        ["\xF5", "%F5"],
        ["\xFF", "%FF"],
        ["\xC3\xA9", "%C3%A9"],
        ["\xE6\x97\xA5\xE6\x9C\xAC\xE8\xAA\x9E", "%E6%97%A5%E6%9C%AC%E8%AA%9E"],
        ["\xF0\x9F\x98\x80", "%F0%9F%98%80"],
        ["a\xE2\x82\xACb", "a%E2%82%ACb"],
        ["\xCC\x80", "%CC%80"],
        ["\x7F", "%7F"],
        ["\xC2\x80", "%C2%80"],
        ["\xDF\xBF", "%DF%BF"],
        ["\xE0\xA0\x80", "%E0%A0%80"],
        ["\xEF\xBF\xBF", "%EF%BF%BF"],
        ["\xF0\x90\x80\x80", "%F0%90%80%80"],
        ["\xF4\x8F\xBF\xBF", "%F4%8F%BF%BF"],
        ["\xED\x9F\xBF", "%ED%9F%BF"],
        ["\xEE\x80\x80", "%EE%80%80"],
        ["\xC3", "%C3"],
        ["\xE2\x82", "%E2%82"],
        ["\xE2(\xA1", "%E2%28%A1"],
        ["\xF0\x9F\x98", "%F0%9F%98"],
        ["\xC0\x80", "%C0%80"],
        ["\xE0\x80\x80", "%E0%80%80"],
        ["\xE0\x9F\xBF", "%E0%9F%BF"],
        ["\xED\xA0\x80", "%ED%A0%80"],
        ["\xED\xBF\xBF", "%ED%BF%BF"],
        ["\xF4\x90\x80\x80", "%F4%90%80%80"],
        ["\xF0\x80\x80\x80", "%F0%80%80%80"],
        ["a\xFFb", "a%FFb"],
        ["\x80\x80", "%80%80"],
        ["\xC3\xC3\xA9", "%C3%C3%A9"],
        ["\xF0\x9F\x98\x80\xF0", "%F0%9F%98%80%F0"],
        ["\xE2\x82\xAC\xE2", "%E2%82%AC%E2"],
        ["ok\xC3", "ok%C3"],
        ["\xEF\xBF\xBD", "%EF%BF%BD"],
        ["", ""],
        ["plain text", "plain%20text"],
        ["<script>alert(1)</script>", "%3Cscript%3Ealert%281%29%3C%2Fscript%3E"],
        ["a&b<c>d\x22e'f", "a%26b%3Cc%3Ed%22e%27f"],
        ["Tom & Jerry's \x22show\x22", "Tom%20%26%20Jerry%27s%20%22show%22"],
        ["line1\x0Aline2\x0D\x0A\x09tabbed", "line1%0Aline2%0D%0A%09tabbed"],
        ["x=1;y='2'", "x%3D1%3By%3D%272%27"],
        ["path/to/file.txt?a=b&c=d#frag", "path%2Fto%2Ffile.txt%3Fa%3Db%26c%3Dd%23frag"],
        ["100% sure", "100%25%20sure"],
        ["a b+c", "a%20b%2Bc"],
        ["~tilde-dash_under.dot", "~tilde-dash_under.dot"],
        ["\x00\x01\x02\x7F\x1F", "%00%01%02%7F%1F"],
        ["</style><b>", "%3C%2Fstyle%3E%3Cb%3E"],
        ["\x5Cback\x5Cslash", "%5Cback%5Cslash"],
        ["{brace}\x24dollar", "%7Bbrace%7D%24dollar"],
        [")\xEC\x22d\x8B\xD9\xC8\xE7\xE2\xDD", "%29%EC%22d%8B%D9%C8%E7%E2%DD"],
        ["=\x99\xF7\xC3\xE3v\xD8\xB9\xB6z", "%3D%99%F7%C3%E3v%D8%B9%B6z"],
        ["\x88\xC9\xE2\xDCt\xD5\xCCr\x94\xE9_\x81", "%88%C9%E2%DCt%D5%CCr%94%E9_%81"],
        ["\xFB\xCBI\x17\x0F\xA1x\xB8\xEF", "%FB%CBI%17%0F%A1x%B8%EF"],
        ["\xC4\xB7\x24dO\xDD", "%C4%B7%24dO%DD"],
        ["E)\x93\x90\x80`c", "E%29%93%90%80%60c"],
        ["B\x91\x85\xEB\x9Cs)\xE0\xF0X\xC2", "B%91%85%EB%9Cs%29%E0%F0X%C2"],
        ["\xE8\xBB\xB8\xC3\xC2v0\xDD1", "%E8%BB%B8%C3%C2v0%DD1"],
        ["5\xB2c\xC6UO\x8A\x98", "5%B2c%C6UO%8A%98"],
        ["\x86\xEF\x22OuK\x90", "%86%EF%22OuK%90"],
        ["\x91\xD9\x86\xEA\x8C-\xBC\x8D\xCA]\xD7\xA2", "%91%D9%86%EA%8C-%BC%8D%CA%5D%D7%A2"],
        ["\x17g\xC2\xD3y\xD8\x9C\xC4\x9A", "%17g%C2%D3y%D8%9C%C4%9A"],
        ["\xC5\xA6,\x8E\x87", "%C5%A6%2C%8E%87"],
        ["\xED\xD3\xC6\xDE!p\x86", "%ED%D3%C6%DE%21p%86"],
        ["\xCFY\xB5Yd\xADk", "%CFY%B5Yd%ADk"],
        ["\x0D\xD9\xD5\xEAk\xE6\xDB\xE8!\x96\x24\xD0", "%0D%D9%D5%EAk%E6%DB%E8%21%96%24%D0"],
        ["\xAC\x99\x08\x8DI\xBF\xDC", "%AC%99%08%8DI%BF%DC"],
        ["3\x99\x17)\x97!\x97-", "3%99%17%29%97%21%97-"],
        ["\xD3l\xA4\x84\x9D\xEB\xAD3`\xA0\x06\xDA", "%D3l%A4%84%9D%EB%AD3%60%A0%06%DA"],
        ["\xE4B/\x9C\xE9\xB4", "%E4B%2F%9C%E9%B4"],
        ["'\xD2D\x24\xE5Y\xE7\xE4/\xE6", "%27%D2D%24%E5Y%E7%E4%2F%E6"],
        ["\x9Ae\xDBx\x81\xB8g;n\xEA\xDB\x8E", "%9Ae%DBx%81%B8g%3Bn%EA%DB%8E"],
        ["):\xD8C\xCF", "%29%3A%D8C%CF"],
        [")\xE9\xE6\xEB\xC2\xEA\xEFI\x81\xA9A", "%29%E9%E6%EB%C2%EA%EFI%81%A9A"],
        ["\xC2", "%C2"],
        ["\xCB\xD0", "%CB%D0"],
        ["4\xB2J\xC4P;8\xF6\xE2", "4%B2J%C4P%3B8%F6%E2"],
        ["\xBC\x7F\xF0/\x98\x7F", "%BC%7F%F0%2F%98%7F"],
        ["\x22\xF0", "%22%F0"],
        ["um>o\x95!\x9B\xD3\xD9\xC9@\x81", "um%3Eo%95%21%9B%D3%D9%C9%40%81"],
        ["t\x83\xD1\xF82", "t%83%D1%F82"],
        ["s3E", "s3E"],
        ["\xE4_\x86", "%E4_%86"],
        ["p\xBBx\xED\xCC\x95\xF0", "p%BBx%ED%CC%95%F0"],
        ["\xCA\xFB\xAD+z\xDE\x16^", "%CA%FB%AD%2Bz%DE%16%5E"],
        ["\x97B_k\x98\x975\xD5K\x99", "%97B_k%98%975%D5K%99"],
        ["\x807\xDF'\xDE\xE6\xEE\xBD\xAB.", "%807%DF%27%DE%E6%EE%BD%AB."],
        ["\xDA\x88\xCBz\x9Bj\xE4\xED", "%DA%88%CBz%9Bj%E4%ED"],
        [" o\x8B", "%20o%8B"],
        ["\xABk8", "%ABk8"],
    ];
    $CSS = [
        ["\x00", "\x5C0 "],
        ["\x01", "\x5C1 "],
        ["\x02", "\x5C2 "],
        ["\x03", "\x5C3 "],
        ["\x04", "\x5C4 "],
        ["\x05", "\x5C5 "],
        ["\x06", "\x5C6 "],
        ["\x07", "\x5C7 "],
        ["\x08", "\x5C8 "],
        ["\x09", "\x5C9 "],
        ["\x0A", "\x5CA "],
        ["\x0B", "\x5CB "],
        ["\x0C", "\x5CC "],
        ["\x0D", "\x5CD "],
        ["\x0E", "\x5CE "],
        ["\x0F", "\x5CF "],
        ["\x10", "\x5C10 "],
        ["\x11", "\x5C11 "],
        ["\x12", "\x5C12 "],
        ["\x13", "\x5C13 "],
        ["\x14", "\x5C14 "],
        ["\x15", "\x5C15 "],
        ["\x16", "\x5C16 "],
        ["\x17", "\x5C17 "],
        ["\x18", "\x5C18 "],
        ["\x19", "\x5C19 "],
        ["\x1A", "\x5C1A "],
        ["\x1B", "\x5C1B "],
        ["\x1C", "\x5C1C "],
        ["\x1D", "\x5C1D "],
        ["\x1E", "\x5C1E "],
        ["\x1F", "\x5C1F "],
        [" ", "\x5C20 "],
        ["!", "\x5C21 "],
        ["\x22", "\x5C22 "],
        ["#", "\x5C23 "],
        ["\x24", "\x5C24 "],
        ["%", "\x5C25 "],
        ["&", "\x5C26 "],
        ["'", "\x5C27 "],
        ["(", "\x5C28 "],
        [")", "\x5C29 "],
        ["*", "\x5C2A "],
        ["+", "\x5C2B "],
        [",", "\x5C2C "],
        ["-", "-"],
        [".", "\x5C2E "],
        ["/", "\x5C2F "],
        ["0", "0"],
        ["1", "1"],
        ["2", "2"],
        ["3", "3"],
        ["4", "4"],
        ["5", "5"],
        ["6", "6"],
        ["7", "7"],
        ["8", "8"],
        ["9", "9"],
        [":", "\x5C3A "],
        [";", "\x5C3B "],
        ["<", "\x5C3C "],
        ["=", "\x5C3D "],
        [">", "\x5C3E "],
        ["?", "\x5C3F "],
        ["@", "\x5C40 "],
        ["A", "A"],
        ["B", "B"],
        ["C", "C"],
        ["D", "D"],
        ["E", "E"],
        ["F", "F"],
        ["G", "G"],
        ["H", "H"],
        ["I", "I"],
        ["J", "J"],
        ["K", "K"],
        ["L", "L"],
        ["M", "M"],
        ["N", "N"],
        ["O", "O"],
        ["P", "P"],
        ["Q", "Q"],
        ["R", "R"],
        ["S", "S"],
        ["T", "T"],
        ["U", "U"],
        ["V", "V"],
        ["W", "W"],
        ["X", "X"],
        ["Y", "Y"],
        ["Z", "Z"],
        ["[", "\x5C5B "],
        ["\x5C", "\x5C5C "],
        ["]", "\x5C5D "],
        ["^", "\x5C5E "],
        ["_", "_"],
        ["`", "\x5C60 "],
        ["a", "a"],
        ["b", "b"],
        ["c", "c"],
        ["d", "d"],
        ["e", "e"],
        ["f", "f"],
        ["g", "g"],
        ["h", "h"],
        ["i", "i"],
        ["j", "j"],
        ["k", "k"],
        ["l", "l"],
        ["m", "m"],
        ["n", "n"],
        ["o", "o"],
        ["p", "p"],
        ["q", "q"],
        ["r", "r"],
        ["s", "s"],
        ["t", "t"],
        ["u", "u"],
        ["v", "v"],
        ["w", "w"],
        ["x", "x"],
        ["y", "y"],
        ["z", "z"],
        ["{", "\x5C7B "],
        ["|", "\x5C7C "],
        ["}", "\x5C7D "],
        ["~", "\x5C7E "],
        ["\x7F", "\x5C7F "],
        ["\x80", "\x80"],
        ["\xBF", "\xBF"],
        ["\xC0", "\xC0"],
        ["\xC1", "\xC1"],
        ["\xC2", "\xC2"],
        ["\xDF", "\xDF"],
        ["\xE0", "\xE0"],
        ["\xEF", "\xEF"],
        ["\xF0", "\xF0"],
        ["\xF4", "\xF4"],
        ["\xF5", "\xF5"],
        ["\xFF", "\xFF"],
        ["\xC3\xA9", "\xC3\xA9"],
        ["\xE6\x97\xA5\xE6\x9C\xAC\xE8\xAA\x9E", "\xE6\x97\xA5\xE6\x9C\xAC\xE8\xAA\x9E"],
        ["\xF0\x9F\x98\x80", "\xF0\x9F\x98\x80"],
        ["a\xE2\x82\xACb", "a\xE2\x82\xACb"],
        ["\xCC\x80", "\xCC\x80"],
        ["\x7F", "\x5C7F "],
        ["\xC2\x80", "\xC2\x80"],
        ["\xDF\xBF", "\xDF\xBF"],
        ["\xE0\xA0\x80", "\xE0\xA0\x80"],
        ["\xEF\xBF\xBF", "\xEF\xBF\xBF"],
        ["\xF0\x90\x80\x80", "\xF0\x90\x80\x80"],
        ["\xF4\x8F\xBF\xBF", "\xF4\x8F\xBF\xBF"],
        ["\xED\x9F\xBF", "\xED\x9F\xBF"],
        ["\xEE\x80\x80", "\xEE\x80\x80"],
        ["\xC3", "\xC3"],
        ["\xE2\x82", "\xE2\x82"],
        ["\xE2(\xA1", "\xE2\x5C28 \xA1"],
        ["\xF0\x9F\x98", "\xF0\x9F\x98"],
        ["\xC0\x80", "\xC0\x80"],
        ["\xE0\x80\x80", "\xE0\x80\x80"],
        ["\xE0\x9F\xBF", "\xE0\x9F\xBF"],
        ["\xED\xA0\x80", "\xED\xA0\x80"],
        ["\xED\xBF\xBF", "\xED\xBF\xBF"],
        ["\xF4\x90\x80\x80", "\xF4\x90\x80\x80"],
        ["\xF0\x80\x80\x80", "\xF0\x80\x80\x80"],
        ["a\xFFb", "a\xFFb"],
        ["\x80\x80", "\x80\x80"],
        ["\xC3\xC3\xA9", "\xC3\xC3\xA9"],
        ["\xF0\x9F\x98\x80\xF0", "\xF0\x9F\x98\x80\xF0"],
        ["\xE2\x82\xAC\xE2", "\xE2\x82\xAC\xE2"],
        ["ok\xC3", "ok\xC3"],
        ["\xEF\xBF\xBD", "\xEF\xBF\xBD"],
        ["", ""],
        ["plain text", "plain\x5C20 text"],
        ["<script>alert(1)</script>", "\x5C3C script\x5C3E alert\x5C28 1\x5C29 \x5C3C \x5C2F script\x5C3E "],
        ["a&b<c>d\x22e'f", "a\x5C26 b\x5C3C c\x5C3E d\x5C22 e\x5C27 f"],
        ["Tom & Jerry's \x22show\x22", "Tom\x5C20 \x5C26 \x5C20 Jerry\x5C27 s\x5C20 \x5C22 show\x5C22 "],
        ["line1\x0Aline2\x0D\x0A\x09tabbed", "line1\x5CA line2\x5CD \x5CA \x5C9 tabbed"],
        ["x=1;y='2'", "x\x5C3D 1\x5C3B y\x5C3D \x5C27 2\x5C27 "],
        ["path/to/file.txt?a=b&c=d#frag", "path\x5C2F to\x5C2F file\x5C2E txt\x5C3F a\x5C3D b\x5C26 c\x5C3D d\x5C23 frag"],
        ["100% sure", "100\x5C25 \x5C20 sure"],
        ["a b+c", "a\x5C20 b\x5C2B c"],
        ["~tilde-dash_under.dot", "\x5C7E tilde-dash_under\x5C2E dot"],
        ["\x00\x01\x02\x7F\x1F", "\x5C0 \x5C1 \x5C2 \x5C7F \x5C1F "],
        ["</style><b>", "\x5C3C \x5C2F style\x5C3E \x5C3C b\x5C3E "],
        ["\x5Cback\x5Cslash", "\x5C5C back\x5C5C slash"],
        ["{brace}\x24dollar", "\x5C7B brace\x5C7D \x5C24 dollar"],
        [")\xEC\x22d\x8B\xD9\xC8\xE7\xE2\xDD", "\x5C29 \xEC\x5C22 d\x8B\xD9\xC8\xE7\xE2\xDD"],
        ["=\x99\xF7\xC3\xE3v\xD8\xB9\xB6z", "\x5C3D \x99\xF7\xC3\xE3v\xD8\xB9\xB6z"],
        ["\x88\xC9\xE2\xDCt\xD5\xCCr\x94\xE9_\x81", "\x88\xC9\xE2\xDCt\xD5\xCCr\x94\xE9_\x81"],
        ["\xFB\xCBI\x17\x0F\xA1x\xB8\xEF", "\xFB\xCBI\x5C17 \x5CF \xA1x\xB8\xEF"],
        ["\xC4\xB7\x24dO\xDD", "\xC4\xB7\x5C24 dO\xDD"],
        ["E)\x93\x90\x80`c", "E\x5C29 \x93\x90\x80\x5C60 c"],
        ["B\x91\x85\xEB\x9Cs)\xE0\xF0X\xC2", "B\x91\x85\xEB\x9Cs\x5C29 \xE0\xF0X\xC2"],
        ["\xE8\xBB\xB8\xC3\xC2v0\xDD1", "\xE8\xBB\xB8\xC3\xC2v0\xDD1"],
        ["5\xB2c\xC6UO\x8A\x98", "5\xB2c\xC6UO\x8A\x98"],
        ["\x86\xEF\x22OuK\x90", "\x86\xEF\x5C22 OuK\x90"],
        ["\x91\xD9\x86\xEA\x8C-\xBC\x8D\xCA]\xD7\xA2", "\x91\xD9\x86\xEA\x8C-\xBC\x8D\xCA\x5C5D \xD7\xA2"],
        ["\x17g\xC2\xD3y\xD8\x9C\xC4\x9A", "\x5C17 g\xC2\xD3y\xD8\x9C\xC4\x9A"],
        ["\xC5\xA6,\x8E\x87", "\xC5\xA6\x5C2C \x8E\x87"],
        ["\xED\xD3\xC6\xDE!p\x86", "\xED\xD3\xC6\xDE\x5C21 p\x86"],
        ["\xCFY\xB5Yd\xADk", "\xCFY\xB5Yd\xADk"],
        ["\x0D\xD9\xD5\xEAk\xE6\xDB\xE8!\x96\x24\xD0", "\x5CD \xD9\xD5\xEAk\xE6\xDB\xE8\x5C21 \x96\x5C24 \xD0"],
        ["\xAC\x99\x08\x8DI\xBF\xDC", "\xAC\x99\x5C8 \x8DI\xBF\xDC"],
        ["3\x99\x17)\x97!\x97-", "3\x99\x5C17 \x5C29 \x97\x5C21 \x97-"],
        ["\xD3l\xA4\x84\x9D\xEB\xAD3`\xA0\x06\xDA", "\xD3l\xA4\x84\x9D\xEB\xAD3\x5C60 \xA0\x5C6 \xDA"],
        ["\xE4B/\x9C\xE9\xB4", "\xE4B\x5C2F \x9C\xE9\xB4"],
        ["'\xD2D\x24\xE5Y\xE7\xE4/\xE6", "\x5C27 \xD2D\x5C24 \xE5Y\xE7\xE4\x5C2F \xE6"],
        ["\x9Ae\xDBx\x81\xB8g;n\xEA\xDB\x8E", "\x9Ae\xDBx\x81\xB8g\x5C3B n\xEA\xDB\x8E"],
        ["):\xD8C\xCF", "\x5C29 \x5C3A \xD8C\xCF"],
        [")\xE9\xE6\xEB\xC2\xEA\xEFI\x81\xA9A", "\x5C29 \xE9\xE6\xEB\xC2\xEA\xEFI\x81\xA9A"],
        ["\xC2", "\xC2"],
        ["\xCB\xD0", "\xCB\xD0"],
        ["4\xB2J\xC4P;8\xF6\xE2", "4\xB2J\xC4P\x5C3B 8\xF6\xE2"],
        ["\xBC\x7F\xF0/\x98\x7F", "\xBC\x5C7F \xF0\x5C2F \x98\x5C7F "],
        ["\x22\xF0", "\x5C22 \xF0"],
        ["um>o\x95!\x9B\xD3\xD9\xC9@\x81", "um\x5C3E o\x95\x5C21 \x9B\xD3\xD9\xC9\x5C40 \x81"],
        ["t\x83\xD1\xF82", "t\x83\xD1\xF82"],
        ["s3E", "s3E"],
        ["\xE4_\x86", "\xE4_\x86"],
        ["p\xBBx\xED\xCC\x95\xF0", "p\xBBx\xED\xCC\x95\xF0"],
        ["\xCA\xFB\xAD+z\xDE\x16^", "\xCA\xFB\xAD\x5C2B z\xDE\x5C16 \x5C5E "],
        ["\x97B_k\x98\x975\xD5K\x99", "\x97B_k\x98\x975\xD5K\x99"],
        ["\x807\xDF'\xDE\xE6\xEE\xBD\xAB.", "\x807\xDF\x5C27 \xDE\xE6\xEE\xBD\xAB\x5C2E "],
        ["\xDA\x88\xCBz\x9Bj\xE4\xED", "\xDA\x88\xCBz\x9Bj\xE4\xED"],
        [" o\x8B", "\x5C20 o\x8B"],
        ["\xABk8", "\xABk8"],
    ];
    $UNHTML = [
        ["&amp;", "&"],
        ["&lt;", "<"],
        ["&gt;", ">"],
        ["&quot;", "\x22"],
        ["&#39;", "'"],
        ["&#x27;", "'"],
        ["&#X27;", "'"],
        ["&#39", "&#39"],
        ["&amp", "&amp"],
        ["&AMP;", "&AMP;"],
        ["&Amp;", "&Amp;"],
        ["&apos;", "&apos;"],
        ["&nbsp;", "&nbsp;"],
        ["&amp;lt;", "&lt;"],
        ["&amp;amp;", "&amp;"],
        ["&lt;b&gt;bold&lt;/b&gt;", "<b>bold</b>"],
        ["a &amp; b", "a & b"],
        ["&#65;&#66;&#67;", "ABC"],
        ["&#x41;&#x42;", "AB"],
        ["&#233;", "\xC3\xA9"],
        ["&#xe9;", "\xC3\xA9"],
        ["&#xE9;", "\xC3\xA9"],
        ["&#x65E5;&#x672C;", "\xE6\x97\xA5\xE6\x9C\xAC"],
        ["&#128512;", "\xF0\x9F\x98\x80"],
        ["&#x1F600;", "\xF0\x9F\x98\x80"],
        ["&#0;", "&#0;"],
        ["&#x0;", "&#x0;"],
        ["&#1;", "\x01"],
        ["&#55296;", "&#55296;"],
        ["&#xD800;", "&#xD800;"],
        ["&#xDFFF;", "&#xDFFF;"],
        ["&#57343;", "&#57343;"],
        ["&#57344;", "\xEE\x80\x80"],
        ["&#1114111;", "\xF4\x8F\xBF\xBF"],
        ["&#1114112;", "&#1114112;"],
        ["&#x10FFFF;", "\xF4\x8F\xBF\xBF"],
        ["&#x110000;", "&#x110000;"],
        ["&#00065;", "A"],
        ["&#0000065;", "A"],
        ["&#00000065;", "&#00000065;"],
        ["&#x000041;", "A"],
        ["&#x0000041;", "&#x0000041;"],
        ["&#;", "&#;"],
        ["&#x;", "&#x;"],
        ["&#xG1;", "&#xG1;"],
        ["&#12a;", "&#12a;"],
        ["& amp;", "& amp;"],
        ["&;", "&;"],
        ["&&amp;;", "&&;"],
        ["&#38;amp;", "&amp;"],
        ["&#x26;lt;", "&lt;"],
        ["mixed &lt;&#60;&#x3C;< raw", "mixed <<<< raw"],
        ["&#9;&#10;&#13;", "\x09\x0A\x0D"],
        ["&#-1;", "&#-1;"],
        ["&#+1;", "&#+1;"],
        ["&#x-1;", "&#x-1;"],
        ["x&#x41", "x&#x41"],
        ["&#x41;;", "A;"],
        ["&lt;&gt;&amp;&quot;&#39;", "<>&\x22'"],
    ];

    function show_bytes(string $s): string
    {
        return bin2hex($s);
    }

    test('html table', function () use ($HTML) {
        foreach ($HTML as [$in, $want]) {
            eq(Esc::html($in), $want, 'html(hex ' . show_bytes($in) . ')');
        }
    });

    test('attr table', function () use ($ATTR) {
        foreach ($ATTR as [$in, $want]) {
            eq(Esc::attr($in), $want, 'attr(hex ' . show_bytes($in) . ')');
        }
    });

    test('js table', function () use ($JS) {
        foreach ($JS as [$in, $want]) {
            eq(Esc::js($in), $want, 'js(hex ' . show_bytes($in) . ')');
        }
    });

    test('url table', function () use ($URL) {
        foreach ($URL as [$in, $want]) {
            eq(Esc::url($in), $want, 'url(hex ' . show_bytes($in) . ')');
        }
    });

    test('css table', function () use ($CSS) {
        foreach ($CSS as [$in, $want]) {
            eq(Esc::css($in), $want, 'css(hex ' . show_bytes($in) . ')');
        }
    });

    test('unhtml table', function () use ($UNHTML) {
        foreach ($UNHTML as [$in, $want]) {
            eq(Esc::unhtml($in), $want, 'unhtml(' . $in . ')');
        }
    });

    test('unhtml undoes html for text without control characters', function () {
        foreach (['plain', "a & b < c > d \" e ' f", "<script>alert('x')</script>", "caf\xC3\xA9 \xE6\x97\xA5", "&amp; already", '', "tab\there\nnl"] as $s) {
            eq(Esc::unhtml(Esc::html($s)), $s, 'round trip ' . bin2hex($s));
        }
    });

    test('functions are independent per call', function () {
        eq(Esc::js(Esc::js('<')), '\\x5Cx3C');
        eq(Esc::html(Esc::html('<')), '&amp;lt;');
        eq(Esc::url(Esc::url(' ')), '%2520');
        eq(Esc::attr(Esc::attr('<')), '&#x26;&#x23;x3C&#x3B;');
    });

    t_done();
''')

LIB = Lib(
    name="escapist", lang="php", title="the Esc output-escaping helper",
    blurb="The templating layer of the intranet portal escapes every dynamic value with the Esc helper, with a different function for each place the value ends up (HTML text, attribute, script, URL, stylesheet).",
    files={"README.md": README1, "src/Esc.php": F2},
    visible_tests={"tests/run.php": _lang3.php_test(V3)},
    hidden_tests={"tests/run.php": _lang3.php_test(H4)},
    mutate=["src/Esc.php"], difficulty=2, tags=["escaping", "security", "utf8"],
)

_lang3.add(LIB, n=8)
