"""String templates with ${path|filter} placeholders (php): dotted lookups, filter chains with quoted arguments, escapes and positioned errors; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # Tpl

    A tiny template renderer (`src/Tpl.php`, class `Tpl`, static methods, plus `TemplateError`).

        Tpl::render(string $template, array $vars): string

    ## Syntax

    * `${expr}` is replaced by the value of `expr`. `expr` is a **path** (dotted keys into `$vars`: `user.name`, `items.0`) optionally followed by filters, `${path|filter|filter:arg}`. Spaces and tabs around the path, the filters and the `|`
      separators are ignored (`${ user.name | upper }`).
    * A path segment is made of letters, digits and `_`; the path must not be empty. A path that does not exist (a missing key, or a step through a non-array), or whose value is `null`, is *missing*.
    * `$${` stands for the literal text `${` (nothing is substituted after it). A `$` that is not followed by `{`, and a `}` outside a placeholder, are ordinary text.
    * The end of a placeholder is the first `}` that is **not inside a quoted filter argument**. An argument may be quoted with `'...'` or `"..."`; inside the quotes a backslash escapes the next character (`\'`, `\"`, `\\`, anything else is that character
      without the backslash), and `|`, `}` and the other quote character are ordinary. An unquoted argument runs up to the next `|` (spaces and tabs around it are trimmed).

    ## Values

    The final value of a placeholder is turned into text: a string as is, an int in decimal, `true` as `1`, `false` and a missing value as the empty string. A float or an array (that no filter has turned into text) is a `TemplateError`.

    ## Filters (applied left to right)

    | filter | effect |
    |---|---|
    | `upper`, `lower` | ASCII upper/lower case |
    | `trim` | removes spaces, tabs, carriage returns and newlines at both ends |
    | `title` | lower-cases everything, then upper-cases the first letter of every word (a word starts after the start of the text or after a space) |
    | `default:X` | when the value is missing, `null`, or the empty string, the value becomes `X` (an int `0` or `false` is *not* replaced) |
    | `pad:N` | pads on the left with spaces to at least `N` bytes (text that is already longer is left as it is) |
    | `padr:N` | the same on the right |
    | `truncate:N` | text longer than `N` bytes is cut so that the result is exactly `N` bytes: the first `N - 3` bytes and `...`; `N < 3` is a `TemplateError`; shorter text is left as it is |
    | `join:SEP` | an array becomes the text of its values (each as for the final value; nested arrays are an error) joined by `SEP`; any other value is unchanged. `SEP` defaults to `, ` when the argument is missing (`join` alone) |
    | `count` | an array becomes the number of its elements, a string the number of its bytes, `null`/missing becomes `0`; any other value is a `TemplateError` |
    | `money` | an int (or an integer string) of cents becomes `12.34` (negative: `-0.05`); anything else is a `TemplateError` |
    | `e` | HTML-escapes `&` `<` `>` `"` `'` (as `&amp;` `&lt;` `&gt;` `&quot;` `&#39;`) |

    Filters that work on text first turn the value into text as described under *Values* (a missing value is `''`, an array is an error unless the filter is `join` or `count`).
    `pad`, `padr`, `truncate` need an integer argument `N >= 0` (digits only), `money`, `upper`, `lower`, `trim`, `title`, `e` and `count` take no argument (an argument is a `TemplateError`), `default` needs an argument (it may be empty:
    `default:""`). An unknown filter name is a `TemplateError`.

    ## Errors

    `TemplateError` extends `Exception`; `getPosition(): int` is the 0-based byte offset of the `$` of the `${` that started the offending placeholder. Raised for: an unclosed placeholder (no closing `}`, or an unterminated quote), an empty or invalid path, an unknown
    filter, a filter with a bad argument, and the value errors above. `render` never partially returns: it either gives the full text or throws.
''')

F2 = dd(r'''
    <?php
    declare(strict_types=1);

    class TemplateError extends Exception
    {
        private int $position;

        public function __construct(string $message, int $position)
        {
            parent::__construct($message);
            $this->position = $position;
        }

        public function getPosition(): int
        {
            return $this->position;
        }
    }

    class Tpl
    {
        private const FILTERS = ['upper', 'lower', 'trim', 'title', 'default', 'pad', 'padr', 'truncate', 'join', 'count', 'money', 'e'];

        public static function render(string $template, array $vars): string
        {
            $out = '';
            $n = strlen($template);
            $i = 0;
            while ($i < $n) {
                $c = $template[$i];
                if ($c === '$' && $i + 2 < $n && $template[$i + 1] === '$' && $template[$i + 2] === '{') {
                    $out .= '${';
                    $i += 3;
                    continue;
                }
                if ($c === '$' && $i + 1 < $n && $template[$i + 1] === '{') {
                    [$path, $filters, $end] = self::parsePlaceholder($template, $i);
                    $out .= self::evaluate($vars, $path, $filters, $i);
                    $i = $end;
                    continue;
                }
                $out .= $c;
                $i++;
            }
            return $out;
        }

        private static function blank(string $c): bool
        {
            return $c === ' ' || $c === "\t";
        }

        /** @return array{string, list<array{string,?string}>, int} */
        private static function parsePlaceholder(string $t, int $start): array
        {
            $n = strlen($t);
            $p = $start + 2;
            $skip = function () use ($t, $n, &$p): void {
                while ($p < $n && self::blank($t[$p])) {
                    $p++;
                }
            };
            $skip();
            $from = $p;
            while ($p < $n && $t[$p] !== '|' && $t[$p] !== '}' && !self::blank($t[$p])) {
                $p++;
            }
            $path = substr($t, $from, $p - $from);
            if (preg_match('/^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$/', $path) !== 1) {
                throw new TemplateError('invalid path', $start);
            }
            $filters = [];
            while (true) {
                $skip();
                if ($p >= $n) {
                    throw new TemplateError('unclosed placeholder', $start);
                }
                if ($t[$p] === '}') {
                    return [$path, $filters, $p + 1];
                }
                if ($t[$p] !== '|') {
                    throw new TemplateError('unexpected text in placeholder', $start);
                }
                $p++;
                $skip();
                $from = $p;
                while ($p < $n && $t[$p] !== ':' && $t[$p] !== '|' && $t[$p] !== '}' && !self::blank($t[$p])) {
                    $p++;
                }
                $name = substr($t, $from, $p - $from);
                if (!in_array($name, self::FILTERS, true)) {
                    throw new TemplateError("unknown filter: $name", $start);
                }
                $skip();
                $arg = null;
                if ($p < $n && $t[$p] === ':') {
                    $p++;
                    $skip();
                    if ($p < $n && ($t[$p] === "'" || $t[$p] === '"')) {
                        $quote = $t[$p++];
                        $arg = '';
                        $closed = false;
                        while ($p < $n) {
                            $ch = $t[$p++];
                            if ($ch === '\\' && $p < $n) {
                                $arg .= $t[$p++];
                            } elseif ($ch === $quote) {
                                $closed = true;
                                break;
                            } else {
                                $arg .= $ch;
                            }
                        }
                        if (!$closed) {
                            throw new TemplateError('unterminated quote', $start);
                        }
                        $skip();
                        if ($p < $n && $t[$p] !== '|' && $t[$p] !== '}') {
                            throw new TemplateError('text after a quoted argument', $start);
                        }
                    } else {
                        $from = $p;
                        while ($p < $n && $t[$p] !== '|' && $t[$p] !== '}') {
                            $p++;
                        }
                        $arg = trim(substr($t, $from, $p - $from), " \t");
                    }
                }
                $filters[] = [$name, $arg];
            }
        }

        private static function lookup(array $vars, string $path)
        {
            $node = $vars;
            foreach (explode('.', $path) as $seg) {
                if (!is_array($node) || !array_key_exists($seg, $node)) {
                    return null;
                }
                $node = $node[$seg];
            }
            return $node;
        }

        private static function text($v, int $pos): string
        {
            if ($v === null) {
                return '';
            }
            if (is_bool($v)) {
                return $v ? '1' : '';
            }
            if (is_int($v) || is_string($v)) {
                return (string)$v;
            }
            throw new TemplateError('value cannot be written as text', $pos);
        }

        private static function intArg(?string $arg, int $pos): int
        {
            if ($arg === null || preg_match('/^[0-9]+$/', $arg) !== 1) {
                throw new TemplateError('bad numeric argument', $pos);
            }
            return (int)$arg;
        }

        private static function evaluate(array $vars, string $path, array $filters, int $pos): string
        {
            $v = self::lookup($vars, $path);
            foreach ($filters as [$name, $arg]) {
                if ($arg !== null && !in_array($name, ['default', 'pad', 'padr', 'truncate', 'join'], true)) {
                    throw new TemplateError("filter $name takes no argument", $pos);
                }
                switch ($name) {
                    case 'upper':
                        $v = strtoupper(self::text($v, $pos));
                        break;
                    case 'lower':
                        $v = strtolower(self::text($v, $pos));
                        break;
                    case 'trim':
                        $v = trim(self::text($v, $pos), " \t\n\r");
                        break;
                    case 'title':
                        $v = ucwords(strtolower(self::text($v, $pos)), ' ');
                        break;
                    case 'default':
                        if ($arg === null) {
                            throw new TemplateError('default needs an argument', $pos);
                        }
                        if ($v === null || $v === '') {
                            $v = $arg;
                        }
                        break;
                    case 'pad':
                        $v = str_pad(self::text($v, $pos), self::intArg($arg, $pos), ' ', STR_PAD_LEFT);
                        break;
                    case 'padr':
                        $v = str_pad(self::text($v, $pos), self::intArg($arg, $pos), ' ', STR_PAD_RIGHT);
                        break;
                    case 'truncate':
                        $max = self::intArg($arg, $pos);
                        if ($max < 3) {
                            throw new TemplateError('truncate needs at least 3', $pos);
                        }
                        $s = self::text($v, $pos);
                        $v = strlen($s) > $max ? substr($s, 0, $max - 3) . '...' : $s;
                        break;
                    case 'join':
                        if (is_array($v)) {
                            $parts = [];
                            foreach ($v as $item) {
                                $parts[] = self::text($item, $pos);
                            }
                            $v = implode($arg ?? ', ', $parts);
                        }
                        break;
                    case 'count':
                        if (is_array($v)) {
                            $v = count($v);
                        } elseif (is_string($v)) {
                            $v = strlen($v);
                        } elseif ($v === null) {
                            $v = 0;
                        } else {
                            throw new TemplateError('cannot count this value', $pos);
                        }
                        break;
                    case 'money':
                        if (!(is_int($v) || (is_string($v) && preg_match('/^-?[0-9]+$/', $v) === 1))) {
                            throw new TemplateError('money needs an integer', $pos);
                        }
                        $cents = (int)$v;
                        $abs = abs($cents);
                        $v = ($cents < 0 ? '-' : '') . intdiv($abs, 100) . '.' . str_pad((string)($abs % 100), 2, '0', STR_PAD_LEFT);
                        break;
                    case 'e':
                        $v = str_replace(['&', '<', '>', '"', "'"], ['&amp;', '&lt;', '&gt;', '&quot;', '&#39;'], self::text($v, $pos));
                        break;
                }
            }
            return self::text($v, $pos);
        }
    }
''')

V3 = dd(r'''
    require __DIR__ . '/../src/Tpl.php';

    test('basics', function () {
        eq(Tpl::render('Hello ${name|upper}!', ['name' => 'ada']), 'Hello ADA!');
        eq(Tpl::render('${a.b} and ${missing|default:"n/a"}', ['a' => ['b' => 5]]), '5 and n/a');
        eq(Tpl::render('Total: ${total|money}', ['total' => 1999]), 'Total: 19.99');
        eq(Tpl::render('Cost $${5}', []), 'Cost ${5}');
    });

    t_done();
''')

H4 = dd(r'''
    require __DIR__ . '/../src/Tpl.php';

    $VARS = ['name' => 'ada lovelace', 'user' => ['first' => 'Grace', 'last' => 'hopper', 'tags' => ['a', 'b', 'c'], 'nested' => [[1, 2], [3]], 'age' => 36, 'zero' => 0, 'off' => false, 'on' => true, 'none' => null, 'empty' => ''], 'n' => 1999, 'neg' => -5, 'cents' => '105', 'big' => 123456789, 'list' => ['x', 'y', 3, true, false, null], 'empty' => '', 'sp' => '  padded text  ', 'html' => '<a href="x">Tom & Jerry\'s</a>', 'f' => 1.5, 'long' => 'abcdefghijklmnopqrstuvwxyz', 'mixed' => 'hELLO wORLD  foo', 'arr' => [], 'word' => 'éa'];

    $CASES = [
        ['', ''],
        ['plain text', 'plain text'],
        ['${name}', 'ada lovelace'],
        ['${ name }', 'ada lovelace'],
        ['${	name	}', 'ada lovelace'],
        ['${name|upper}', 'ADA LOVELACE'],
        ['${name|lower}', 'ada lovelace'],
        ['${name|title}', 'Ada Lovelace'],
        ['${ name | upper | lower }', 'ada lovelace'],
        ['${name|upper|title}', 'Ada Lovelace'],
        ['${name}${name}', 'ada lovelaceada lovelace'],
        ['a${name}b${name}c', 'aada lovelacebada lovelacec'],
        ['${user.first}', 'Grace'],
        ['${user.last|upper}', 'HOPPER'],
        ['${user.tags}', ['E', 0]],
        ['${user.tags|join}', 'a, b, c'],
        ['${user.tags|join:-}', 'a-b-c'],
        ['${user.tags|join:\' / \'}', 'a / b / c'],
        ['${user.tags|join: , }', 'a,b,c'],
        ['${user.nested|join}', ['E', 0]],
        ['${user.tags.1}', 'b'],
        ['${user.tags.5}', ''],
        ['${user.tags.5|default:none}', 'none'],
        ['${user.nested.0|join:+}', '1+2'],
        ['${user.nested.1.0}', '3'],
        ['${user.age}', '36'],
        ['${user.age|pad:6}', '    36'],
        ['${user.age|padr:6}|', '36    |'],
        ['${user.age|pad:1}', '36'],
        ['${user.age|pad:0}', '36'],
        ['${user.zero}', '0'],
        ['${user.zero|default:x}', '0'],
        ['${user.off}', ''],
        ['${user.off|default:x}', ''],
        ['${user.on}', '1'],
        ['${user.none}', ''],
        ['${user.none|default:x}', 'x'],
        ['${user.empty|default:x}', 'x'],
        ['${user.empty|default:}', ''],
        ['${user.empty|default:""}', ''],
        ['${missing|default:x}', 'x'],
        ['${missing.deeper|default:x}', 'x'],
        ['${name.deeper|default:x}', 'x'],
        ['${missing}', ''],
        ['${missing|upper}', ''],
        ['${missing|count}', '0'],
        ['${user.none|count}', '0'],
        ['${user.tags|count}', '3'],
        ['${name|count}', '12'],
        ['${word|count}', '3'],
        ['${arr|count}', '0'],
        ['${arr|join}', ''],
        ['${arr|join:,}|', '|'],
        ['${n|count}', ['E', 0]],
        ['${user.on|count}', ['E', 0]],
        ['${f|count}', ['E', 0]],
        ['${n|money}', '19.99'],
        ['${neg|money}', '-0.05'],
        ['${cents|money}', '1.05'],
        ['${big|money}', '1234567.89'],
        ['${name|money}', ['E', 0]],
        ['${missing|money}', ['E', 0]],
        ['${user.on|money}', ['E', 0]],
        ['${f|money}', ['E', 0]],
        ['${user.tags|money}', ['E', 0]],
        ['${\'5\'|money}', ['E', 0]],
        ['${html|e}', '&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&#39;s&lt;/a&gt;'],
        ['${html|e|upper}', '&LT;A HREF=&QUOT;X&QUOT;&GT;TOM &AMP; JERRY&#39;S&LT;/A&GT;'],
        ['${html|upper|e}', '&lt;A HREF=&quot;X&quot;&gt;TOM &amp; JERRY&#39;S&lt;/A&gt;'],
        ['${sp|trim}', 'padded text'],
        ['${sp|trim|pad:20}', '         padded text'],
        ['${sp|pad:20}|', '       padded text  |'],
        ['${sp|padr:20}|', '  padded text       |'],
        ['${sp|trim|truncate:6}', 'pad...'],
        ['${long|truncate:10}', 'abcdefg...'],
        ['${long|truncate:26}', 'abcdefghijklmnopqrstuvwxyz'],
        ['${long|truncate:25}', 'abcdefghijklmnopqrstuv...'],
        ['${long|truncate:3}', '...'],
        ['${long|truncate:2}', ['E', 0]],
        ['${long|truncate:0}', ['E', 0]],
        ['${long|truncate:a}', ['E', 0]],
        ['${long|truncate}', ['E', 0]],
        ['${long|truncate: 10 }', 'abcdefg...'],
        ['${long|truncate:-5}', ['E', 0]],
        ['${long|truncate:1.5}', ['E', 0]],
        ['${long|pad}', ['E', 0]],
        ['${long|pad:x}', ['E', 0]],
        ['${long|pad:-1}', ['E', 0]],
        ['${long|truncate:4}', 'a...'],
        ['${long|truncate:5}', 'ab...'],
        ['${word|truncate:3}', 'éa'],
        ['${mixed|title}', 'Hello World  Foo'],
        ['${mixed|lower|title}', 'Hello World  Foo'],
        ['${mixed|upper}', 'HELLO WORLD  FOO'],
        ['${html|title}', '<a Href="x">tom & Jerry\'s</a>'],
        ['${user.tags|upper}', ['E', 0]],
        ['${user|upper}', ['E', 0]],
        ['${user.tags|trim}', ['E', 0]],
        ['${f}', ['E', 0]],
        ['${f|upper}', ['E', 0]],
        ['${list}', ['E', 0]],
        ['${list|join}', 'x, y, 3, 1, , '],
        ['${list|join:;}', 'x;y;3;1;;'],
        ['${list|count}', '6'],
        ['${user.on}${user.off}x', '1x'],
        ['$${name}', '${name}'],
        ['$${', '${'],
        ['$${}', '${}'],
        ['a $${name} b ${name}', 'a ${name} b ada lovelace'],
        ['$$${name}', '$${name}'],
        ['$$$${name}', '$$${name}'],
        ['$ ${name}', '$ ada lovelace'],
        ['$name', '$name'],
        ['${', ['E', 0]],
        ['${name', ['E', 0]],
        ['${name|', ['E', 0]],
        ['${name|upper', ['E', 0]],
        ['${name|upper|', ['E', 0]],
        ['${name|}', ['E', 0]],
        ['${name||upper}', ['E', 0]],
        ['${}', ['E', 0]],
        ['${ }', ['E', 0]],
        ['${|upper}', ['E', 0]],
        ['${na me}', ['E', 0]],
        ['${name upper}', ['E', 0]],
        ['${name|up per}', ['E', 0]],
        ['${name|bogus}', ['E', 0]],
        ['${name|upper:x}', ['E', 0]],
        ['${name|upper:}', ['E', 0]],
        ['${name|trim:1}', ['E', 0]],
        ['${name|count:1}', ['E', 0]],
        ['${name|money:1}', ['E', 0]],
        ['${name|e:1}', ['E', 0]],
        ['${name|title:}', ['E', 0]],
        ['${name|default}', ['E', 0]],
        ['${name|default:}', 'ada lovelace'],
        ['${name|default:"a|b"}', 'ada lovelace'],
        ['${missing|default:"a|b"|upper}', 'A|B'],
        ['${missing|default:\'it\\\'s\'}', 'it\'s'],
        ['${missing|default:"say \\"hi\\""}', 'say "hi"'],
        ['${missing|default:\'}\'}', '}'],
        ['${missing|default:"}"}', '}'],
        ['${missing|default:\'a\\\\b\'}', 'a\\b'],
        ['${missing|default:\'a\\nb\'}', 'anb'],
        ['${missing|default:\'x\' }', 'x'],
        ['${missing|default:\'x\' |upper}', 'X'],
        ['${missing|default:\'x\'y}', ['E', 0]],
        ['${missing|default:\'x}', ['E', 0]],
        ['${missing|default:"x}', ['E', 0]],
        ['${missing|default:it\'s}', 'it\'s'],
        ['${missing|default:a}b}', 'ab}'],
        ['${missing|default: spaced out }|', 'spaced out|'],
        ['${missing|default:a b|upper}', 'A B'],
        ['${missing|default:x|upper|pad:4}', '   X'],
        ['${missing|default:\'|\'|pad:3}', '  |'],
        ['${a-b}', ['E', 0]],
        ['${a.}', ['E', 0]],
        ['${.a}', ['E', 0]],
        ['${a..b}', ['E', 0]],
        ['${a b}', ['E', 0]],
        ['${é}', ['E', 0]],
        ['${a.b-c}', ['E', 0]],
        ['${A_1.b2}', ''],
        ['${user.first|}', ['E', 0]],
        ['${user.first|upper|}', ['E', 0]],
        ['${user.first |upper}', 'GRACE'],
        ['${user.first| upper}', 'GRACE'],
        ['${user.first | upper }', 'GRACE'],
        ['${user.first|upper }', 'GRACE'],
        ['${user.first|pad :5}', 'Grace'],
        ['${user.first|pad: 5}', 'Grace'],
        ['${user.first|pad:5 }', 'Grace'],
        ['${user.first|pad : 5 }|', 'Grace|'],
        ['${user.first|default : x}', 'Grace'],
        ['}', '}'],
        ['}${name}}', '}ada lovelace}'],
        ['{name}', '{name}'],
        ['${name}}', 'ada lovelace}'],
        ['${{name}', ['E', 0]],
        ['a}b${name|upper}c}d', 'a}bADA LOVELACEc}d'],
        ['text ${name|title} and ${user.last|title} end', 'text Ada Lovelace and Hopper end'],
        ['${name|title}, your balance is ${n|money} EUR', 'Ada Lovelace, your balance is 19.99 EUR'],
        ['Dear ${user.first|upper},

    Balance: ${n|money|pad:10}
    ', 'Dear GRACE,

    Balance:      19.99
    '],
        ['tab	${name}	end', 'tab	ada lovelace	end'],
        ['${name}
    ${name}', 'ada lovelace
    ada lovelace'],
        ['${missing|default:x}${missing|default:y}', 'xy'],
        ['${user.tags|join:\'}\'}', 'a}b}c'],
        ['${user.tags|join:"|"}', 'a|b|c'],
        ['${user.tags|join:\\}', 'a\\b\\c'],
        ['${user.tags|join:\'\\\'\'}', 'a\'b\'c'],
        ['${user.nested|count}', '2'],
        ['${user.tags|count}}
    ${user.tags|join:, }', '3}
    a,b,c'],
        ['${name}$', 'ada lovelace$'],
        ['${bad|nope}${user.tags|count}${missing|default:x}$${missing|default:\'q}\'}', ['E', 0]],
        ['${user.first|upper}{${long|truncate:8}${bad|nope}${html|e}', ['E', 38]],
        ['${long|truncate:8}text ', 'abcde...text '],
        ['${n|money}', '19.99'],
        ['${name|${user.age|pad:5}|', ['E', 0]],
        ['{', '{'],
        ['${n|money} $${lit}text ${html|e}${missing|default:x}', '19.99 ${lit}text &lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&#39;s&lt;/a&gt;x'],
        ['$${lit}{
    ', '${lit}{
    '],
        ['${user.first|upper}$${lit}${name}', 'GRACE${lit}ada lovelace'],
        ['${user.first|upper}{${${user.tags|join:, }', ['E', 20]],
        ['text ', 'text '],
        ['${n|money}${user.tags|count}${name}${n|money}', '19.993ada lovelace19.99'],
        ['$${lit}$${lit}$${name}${missing|default:x}', '${lit}${lit}${name}x'],
        ['${missing|default:\'q}\'}${name}', 'q}ada lovelace'],
        ['${missing|default:x}${user.age|pad:5}|${${missing|default:\'q}\'}$${lit}', ['E', 38]],
        ['${missing|default:x}{$${lit}${missing|default:x}', 'x{${lit}x'],
        ['${user.age|pad:5}|${user.tags|join:, }${long|truncate:8}${user.tags|count}${user.first|upper}${user.first|upper}', '   36|a,b,cabcde...3GRACEGRACE'],
        ['${missing|default:\'q}\'}${user.tags|count}${user.tags|join:, }', 'q}3a,b,c'],
        ['
    ${user.age|pad:5}|${user.first|upper}${n|money}{text ', '
       36|GRACE19.99{text '],
        ['${user.tags|count}${name|', ['E', 18]],
        ['}', '}'],
        ['${name|${user.age|pad:5}|${user.age|pad:5}|${missing|default:x}}${n|money}', ['E', 0]],
        ['}${bad|nope}$${lit}{$${lit}', ['E', 1]],
        ['${name}{${user.tags|count}$${name}', 'ada lovelace{3${name}'],
        ['${n|money}$${lit}text ${bad|nope}', ['E', 22]],
        ['$${missing|default:x} ', '${missing|default:x} '],
        [' ${n|money}${name|${user.first|upper}${name}{', ['E', 11]],
        ['${html|e}${}text ${user.age|pad:5}|', ['E', 9]],
        ['${missing|default:x}${html|e}text ${n|money}{${name|', ['E', 45]],
        ['${missing|default:\'q}\'}}${user.tags|join:, }', 'q}}a,b,c'],
        [' ${long|truncate:8}
    ${name}${user.first|upper}${long|truncate:8}', ' abcde...
    ada lovelaceGRACEabcde...'],
        ['${long|truncate:8}${n|money}${user.tags|count}', 'abcde...19.993'],
        ['${name}${user.first|upper}', 'ada lovelaceGRACE'],
        ['${bad|nope}', ['E', 0]],
        ['{ ', '{ '],
        ['${name}} ${user.tags|join:, }${', ['E', 29]],
        ['
    ${user.tags|join:, }${missing|default:x}${missing|default:\'q}\'} ', '
    a,b,cxq} '],
        ['${n|money}${missing|default:x}${html|e}${bad|nope}${user.tags|join:, }${missing|default:\'q}\'}', ['E', 39]],
        ['${user.age|pad:5}|${long|truncate:8}
    ${user.tags|count}', '   36|abcde...
    3'],
        ['${}${n|money}${user.first|upper}
    ', ['E', 0]],
        ['${user.tags|join:, }${long|truncate:8}${missing|default:x}${long|truncate:8}text ', 'a,b,cabcde...xabcde...text '],
        ['$${lit}', '${lit}'],
        ['${${bad|nope}', ['E', 0]],
        ['${missing|default:\'q}\'}${missing|default:\'q}\'}{${missing|default:x}${long|truncate:8}', 'q}q}{xabcde...'],
        ['${${user.age|pad:5}|
    ${missing|default:\'q}\'}${missing|default:x}', ['E', 0]],
        ['${name}${user.age|pad:5}|${user.age|pad:5}|${html|e}${missing|default:\'q}\'} ', 'ada lovelace   36|   36|&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&#39;s&lt;/a&gt;q} '],
        ['${name|${missing|default:\'q}\'}${missing|default:x}${user.age|pad:5}|${missing|default:\'q}\'}', ['E', 0]],
        ['${missing|default:x}text ${user.tags|join:, }', 'xtext a,b,c'],
        ['${n|money}', '19.99'],
        ['${${bad|nope}${user.first|upper}${${user.first|upper}${user.tags|count}', ['E', 0]],
        ['}', '}'],
        ['${bad|nope}text ', ['E', 0]],
        ['${user.age|pad:5}|${user.tags|count}${', ['E', 36]],
        ['${user.first|upper}${user.tags|count}', 'GRACE3'],
        ['${missing|default:x}${user.tags|count}${user.first|upper}${html|e}${html|e}', 'x3GRACE&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&#39;s&lt;/a&gt;&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&#39;s&lt;/a&gt;'],
        ['${missing|default:x}${missing|default:x}$${lit}${user.first|upper}${user.tags|count}', 'xx${lit}GRACE3'],
        ['${missing|default:x}${missing|default:x}', 'xx'],
        ['}', '}'],
        ['${${missing|default:\'q}\'}${missing|default:\'q}\'}${${name}', ['E', 0]],
        ['${missing|default:x}$${missing|default:x}$${name}${bad|nope}', ['E', 49]],
        ['${user.age|pad:5}|${user.tags|join:, }{${', ['E', 39]],
        ['${n|money}}', '19.99}'],
        ['text ${bad|nope}${user.tags|join:, }$${lit}text ${n|money}', ['E', 5]],
        ['${user.first|upper}', 'GRACE'],
        ['${missing|default:x}', 'x'],
        ['${missing|default:x}}${n|money}${name}${bad|nope}${name|', ['E', 38]],
        ['}${missing|default:x}', '}x'],
        ['${name}
    ', 'ada lovelace
    '],
        ['$${lit}${name}${bad|nope}
    ${user.tags|count}', ['E', 14]],
        ['${n|money}', '19.99'],
        ['${html|e}${user.first|upper}
    ${$', ['E', 29]],
        ['text ${user.first|upper}
    ${user.tags|join:, } ', 'text GRACE
    a,b,c '],
        ['${long|truncate:8}', 'abcde...'],
        ['{${name} ', '{ada lovelace '],
        ['${name}', 'ada lovelace'],
        ['${bad|nope}text ${html|e}', ['E', 0]],
        ['$${${user.age|pad:5}|}{', '${   36|}{'],
        ['$${lit}${missing|default:x}
     ', '${lit}x
     '],
        ['${bad|nope}${user.tags|count}${user.age|pad:5}|${bad|nope}', ['E', 0]],
        ['{${long|truncate:8}${', ['E', 19]],
        ['$', '$'],
        ['${long|truncate:8}', 'abcde...'],
        ['${missing|default:\'q}\'}${name}$${lit}', 'q}ada lovelace${lit}'],
        ['}${user.tags|join:, }', '}a,b,c'],
        ['${missing|default:x}$${bad|nope}${user.tags|count}${user.tags|count}{', 'x${bad|nope}33{'],
        ['${missing|default:\'q}\'}$', 'q}$'],
        ['${name}', 'ada lovelace'],
        ['${missing|default:\'q}\'}${html|e}${text $${name|', ['E', 32]],
        ['${n|money}${bad|nope}${name} ${missing|default:\'q}\'}', ['E', 10]],
        ['${missing|default:x}text ', 'xtext '],
        ['$', '$'],
        ['${missing|default:x}', 'x'],
        ['$${long|truncate:8}', '${long|truncate:8}'],
        ['${n|money}${name|{{{${user.age|pad:5}|', ['E', 10]],
        ['${user.tags|join:, }${name|}}
    ', ['E', 20]],
        ['${', ['E', 0]],
        ['${long|truncate:8}${user.tags|count}${long|truncate:8}${user.age|pad:5}|${long|truncate:8}', 'abcde...3abcde...   36|abcde...'],
        [' ', ' '],
        ['${name}
    ${${name|${html|e}${missing|default:x}', ['E', 8]],
        [' ${user.tags|join:, }${name|', ['E', 21]],
        ['${text ${long|truncate:8}$', ['E', 0]],
        ['}${user.tags|count}', '}3'],
        ['${missing|default:\'q}\'}', 'q}'],
        ['}${name}${user.age|pad:5}|', '}ada lovelace   36|'],
        ['${missing|default:\'q}\'}${n|money}', 'q}19.99'],
        ['${user.tags|join:, }$$${lit}${missing|default:\'q}\'}', 'a,b,c$${lit}q}'],
        ['${html|e}$${lit}', '&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&#39;s&lt;/a&gt;${lit}'],
        ['$${lit}${user.age|pad:5}|${html|e}${name}${missing|default:\'q}\'}', '${lit}   36|&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&#39;s&lt;/a&gt;ada lovelaceq}'],
        ['}', '}'],
        ['}${user.first|upper}}{', '}GRACE}{'],
        ['${html|e}$${lit}${missing|default:\'q}\'}${n|money}', '&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&#39;s&lt;/a&gt;${lit}q}19.99'],
        ['${user.age|pad:5}|${missing|default:x}', '   36|x'],
        ['
    text ${', ['E', 6]],
        ['${long|truncate:8}${name|${name}${missing|default:\'q}\'}$', ['E', 18]],
        ['text ${long|truncate:8}${name}${user.first|upper}${user.age|pad:5}|${user.age|pad:5}|', 'text abcde...ada lovelaceGRACE   36|   36|'],
        ['$ ', '$ '],
        ['${user.tags|join:, }$ {${user.first|upper}${missing|default:x}', 'a,b,c$ {GRACEx'],
        ['text ${bad|nope}${bad|nope}${user.first|upper}', ['E', 5]],
    ];

    function run_template(string $t, array $vars)
    {
        try {
            return Tpl::render($t, $vars);
        } catch (TemplateError $e) {
            return ['E', $e->getPosition()];
        }
    }

    test('template table', function () use ($CASES, $VARS) {
        foreach ($CASES as [$template, $want]) {
            eq(run_template($template, $VARS), $want, 'render(' . json_encode($template) . ')');
        }
    });

    test('errors are TemplateError exceptions', function () {
        raises(fn() => Tpl::render('${', []), TemplateError::class, 'unclosed');
        raises(fn() => Tpl::render('${x|nope}', []), TemplateError::class, 'unknown filter');
        try {
            Tpl::render('ab ${x|nope}', []);
            ok(false, 'should have thrown');
        } catch (Exception $e) {
            ok($e instanceof TemplateError, 'is a TemplateError');
            eq($e->getPosition(), 3, 'position of the placeholder');
        }
    });

    test('no variables', function () {
        eq(Tpl::render('no placeholders at all', []), 'no placeholders at all');
        eq(Tpl::render('', []), '');
        eq(Tpl::render('${x}', []), '');
        eq(Tpl::render('${x|default:ok}', []), 'ok');
    });

    t_done();
''')

LIB = Lib(
    name="tplbrace", lang="php", title="the Tpl template renderer",
    blurb="The mailer fills its message templates, such as `Dear ${user.name|title}, your balance is ${balance|money} EUR`, with the Tpl renderer.",
    files={"README.md": README1, "src/Tpl.php": F2},
    visible_tests={"tests/run.php": _lang3.php_test(V3)},
    hidden_tests={"tests/run.php": _lang3.php_test(H4)},
    mutate=["src/Tpl.php"], difficulty=3, tags=["templates", "parsing", "strings"],
)

_lang3.add(LIB, n=8)
