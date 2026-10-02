"""Query strings with bracket notation (php): building from nested arrays, lenient parsing with appends and malformed keys, percent-encoding rules; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # Qs

    Builds and parses URL query strings with PHP-style bracket notation (`src/Qs.php`, class `Qs`, static methods). `InvalidArgumentException` is thrown for invalid arguments.

    ## `Qs::build(array $params): string`

    Turns a (nested) array into a query string, without a leading `?`. Pairs are joined with `&`, in array order.

    * A scalar value gives `key=value`. A **string** is written as is, an **int** in decimal, `true` as `1` and `false` as `0`. `null` values are left out. A float or an object is an `InvalidArgumentException`.
    * An array value is written element by element with bracket keys: the element at key `k` of the array at `a` gives `a[k]=...`, deeper arrays `a[k][j]=...`. If the array is a **list** (its keys are exactly `0, 1, ..., n-1` in this order)
      the brackets are empty: `a[]=x&a[]=y`. An empty array writes nothing. A top-level array that is a list still writes its numeric keys (`0=x&1=y`).
    * Percent-encoding (applies to every key and every value, to the text of each key part, not to the brackets that build adds): the unreserved characters `A-Z a-z 0-9 - . _ ~` stay as they are, every other **byte** becomes `%HH`
      with two upper-case hex digits (a space is `%20`, never `+`; `[` in a key is `%5B`).

    Example: `['q' => 'a b', 'f' => ['tags' => ['x', 'y'], 'owner' => 'bob', 'n' => null]]` gives `q=a%20b&f[tags][]=x&f[tags][]=y&f[owner]=bob`.

    ## `Qs::parse(string $query): array`

    Reads a query string into a nested array. It is lenient: it never throws.

    1. A single leading `?` is ignored. The text is split at `&`; empty pieces are skipped. Each piece is split at its first `=` into key and value (no `=` means an empty value).
    2. Key and value are *decoded*: `+` becomes a space and `%HH` (two hex digits, either case) the byte it stands for; a `%` not followed by two hex digits stays as it is. Values are always strings.
    3. A piece whose decoded key is empty is skipped. The key is a **base name** followed by zero or more bracket groups `[name]`, each group ending at the first `]` after its `[` (the name may be empty and may contain `[`):
       * no `[` in the key: just the base name;
       * the key *starts* with `[`: the piece is skipped;
       * if the text after the base name is not exactly a sequence of complete bracket groups (an unclosed `[`, or any character after a `]` that does not start the next group) or there are **more than 4 groups**, the whole decoded key is used as one plain name (so `a[b]c=1` sets the key `a[b]c`, `a[b=1` the key `a[b`).
    4. The value is stored at the path: for each name in turn, the current array gets (or already has) an element: a **non-empty** name selects that key (names that are canonical decimal integers become int keys, as in PHP:
       `'7'` is `7`; `'07'`, `'-0'` and `'+7'` stay strings; a negative integer is not used in the tests), an **empty** name appends a new element with the next integer key (the highest int key so far plus one, or 0). When a path goes through an element that is not an array
       (including an earlier scalar for the same key), that element is replaced by an empty array first. The last name receives the value, replacing whatever was there (`a=1&a=2` gives `'2'`).
       `a[]=1&a[]=2` appends twice; `a[][b]=1&a[][b]=2` appends two arrays.

    Example: `?q=a+b&f%5Btags%5D%5B%5D=x&f[tags][]=y&f[owner]=bob` parses to `['q' => 'a b', 'f' => ['tags' => ['x', 'y'], 'owner' => 'bob']]`.

    ## `Qs::without(string $query, string $key): string`

    The query with every piece removed whose decoded key is `$key` or starts with `$key` followed by `[`. The remaining pieces are kept exactly as written (not re-encoded), in order. The result has no leading `?`; a leading `?` of the input is dropped.
''')

F2 = dd(r'''
    <?php
    declare(strict_types=1);

    class Qs
    {
        private static function enc(string $s): string
        {
            $out = '';
            $n = strlen($s);
            for ($i = 0; $i < $n; $i++) {
                $c = ord($s[$i]);
                if (($c >= 0x30 && $c <= 0x39) || ($c >= 0x41 && $c <= 0x5A) || ($c >= 0x61 && $c <= 0x7A) || $c === 0x2D || $c === 0x2E || $c === 0x5F || $c === 0x7E) {
                    $out .= $s[$i];
                } else {
                    $out .= '%' . strtoupper(str_pad(dechex($c), 2, '0', STR_PAD_LEFT));
                }
            }
            return $out;
        }

        private static function dec(string $s): string
        {
            $out = '';
            $n = strlen($s);
            for ($i = 0; $i < $n; $i++) {
                $c = $s[$i];
                if ($c === '+') {
                    $out .= ' ';
                } elseif ($c === '%' && $i + 2 < $n && ctype_xdigit($s[$i + 1]) && ctype_xdigit($s[$i + 2])) {
                    $out .= chr((int)hexdec(substr($s, $i + 1, 2)));
                    $i += 2;
                } else {
                    $out .= $c;
                }
            }
            return $out;
        }

        private static function isList(array $a): bool
        {
            $i = 0;
            foreach ($a as $k => $_) {
                if ($k !== $i) {
                    return false;
                }
                $i++;
            }
            return true;
        }

        private static function scalar($v): ?string
        {
            if ($v === null) {
                return null;
            }
            if (is_bool($v)) {
                return $v ? '1' : '0';
            }
            if (is_int($v) || is_string($v)) {
                return (string)$v;
            }
            throw new InvalidArgumentException('unsupported value type');
        }

        private static function emit(string $prefix, $value, array &$out): void
        {
            if (is_array($value)) {
                $list = self::isList($value);
                foreach ($value as $k => $v) {
                    self::emit($prefix . '[' . ($list ? '' : self::enc((string)$k)) . ']', $v, $out);
                }
                return;
            }
            $s = self::scalar($value);
            if ($s !== null) {
                $out[] = $prefix . '=' . self::enc($s);
            }
        }

        public static function build(array $params): string
        {
            $out = [];
            foreach ($params as $k => $v) {
                self::emit(self::enc((string)$k), $v, $out);
            }
            return implode('&', $out);
        }

        /** @return list<string>|null group names, null when the key is not a clean sequence of groups */
        private static function groups(string $rest): ?array
        {
            $names = [];
            $pos = 0;
            $n = strlen($rest);
            while ($pos < $n) {
                if ($rest[$pos] !== '[') {
                    return null;
                }
                $close = strpos($rest, ']', $pos + 1);
                if ($close === false) {
                    return null;
                }
                $names[] = substr($rest, $pos + 1, $close - $pos - 1);
                $pos = $close + 1;
            }
            return count($names) > 4 ? null : $names;
        }

        private static function keyOf(string $name)
        {
            if (preg_match('/^(0|-?[1-9][0-9]*)$/', $name) === 1 && (string)(int)$name === $name) {
                return (int)$name;
            }
            return $name;
        }

        private static function store(array &$root, array $names, string $value): void
        {
            $node = &$root;
            $last = count($names) - 1;
            foreach ($names as $i => $name) {
                if ($name === '') {
                    $node[] = [];
                    $k = array_key_last($node);
                } else {
                    $k = self::keyOf($name);
                }
                if ($i === $last) {
                    $node[$k] = $value;
                    return;
                }
                if (!isset($node[$k]) || !is_array($node[$k])) {
                    $node[$k] = [];
                }
                $node = &$node[$k];
            }
        }

        public static function parse(string $query): array
        {
            if ($query !== '' && $query[0] === '?') {
                $query = substr($query, 1);
            }
            $result = [];
            foreach (explode('&', $query) as $piece) {
                if ($piece === '') {
                    continue;
                }
                $eq = strpos($piece, '=');
                $rawKey = $eq === false ? $piece : substr($piece, 0, $eq);
                $value = $eq === false ? '' : self::dec(substr($piece, $eq + 1));
                $key = self::dec($rawKey);
                if ($key === '') {
                    continue;
                }
                $open = strpos($key, '[');
                if ($open === false) {
                    $names = [$key];
                } elseif ($open === 0) {
                    continue;
                } else {
                    $groups = self::groups(substr($key, $open));
                    $names = $groups === null ? [$key] : array_merge([substr($key, 0, $open)], $groups);
                }
                self::store($result, $names, $value);
            }
            return $result;
        }

        public static function without(string $query, string $key): string
        {
            if ($query !== '' && $query[0] === '?') {
                $query = substr($query, 1);
            }
            $kept = [];
            foreach (explode('&', $query) as $piece) {
                if ($piece === '') {
                    continue;
                }
                $eq = strpos($piece, '=');
                $name = self::dec($eq === false ? $piece : substr($piece, 0, $eq));
                if ($name === $key || strncmp($name, $key . '[', strlen($key) + 1) === 0) {
                    continue;
                }
                $kept[] = $piece;
            }
            return implode('&', $kept);
        }
    }
''')

V3 = dd(r'''
    require __DIR__ . '/../src/Qs.php';

    test('basics', function () {
        eq(Qs::build(['q' => 'a b', 'f' => ['tags' => ['x', 'y'], 'owner' => 'bob', 'n' => null]]), 'q=a%20b&f[tags][]=x&f[tags][]=y&f[owner]=bob');
        eq(Qs::parse('?q=a+b&f[tags][]=x&f[tags][]=y&f[owner]=bob'), ['q' => 'a b', 'f' => ['tags' => ['x', 'y'], 'owner' => 'bob']]);
        eq(Qs::without('a=1&b[x]=2&b=3&c=4', 'b'), 'a=1&c=4');
    });

    t_done();
''')

H4 = dd(r'''
    require __DIR__ . '/../src/Qs.php';

    $PARSE = [
        ['', []],
        ['?', []],
        ['a=1', ['a' => '1']],
        ['?a=1', ['a' => '1']],
        ['??a=1', ['?a' => '1']],
        ['a', ['a' => '']],
        ['a=', ['a' => '']],
        ['=1', []],
        ['a=1&a=2', ['a' => '2']],
        ['a=1&b=2&a=3', ['a' => '3', 'b' => '2']],
        ['&&a=1&&b=2&', ['a' => '1', 'b' => '2']],
        ['a=b=c', ['a' => 'b=c']],
        ['a=%41%62', ['a' => 'Ab']],
        ['a=%4', ['a' => '%4']],
        ['a=%4g', ['a' => '%4g']],
        ['a=%', ['a' => '%']],
        ['a=%%41', ['a' => '%A']],
        ['a=100%', ['a' => '100%']],
        ['a+b=c+d', ['a b' => 'c d']],
        ['a%20b=c%20d', ['a b' => 'c d']],
        ['a=%e9', ['a' => '' . "\xE9" . '']],
        ['a=%C3%A9', ['a' => '' . "\xC3" . '' . "\xA9" . '']],
        ['a=%2b', ['a' => '+']],
        ['a=+', ['a' => ' ']],
        ['a=%20', ['a' => ' ']],
        ['a=%2', ['a' => '%2']],
        ['a=%zz%41', ['a' => '%zzA']],
        ['a[]=1', ['a' => [0 => '1']]],
        ['a[]=1&a[]=2', ['a' => [0 => '1', 1 => '2']]],
        ['a[]=1&a[]=2&a[]=3', ['a' => [0 => '1', 1 => '2', 2 => '3']]],
        ['a[b]=1', ['a' => ['b' => '1']]],
        ['a[b]=1&a[c]=2', ['a' => ['b' => '1', 'c' => '2']]],
        ['a[b][c]=1', ['a' => ['b' => ['c' => '1']]]],
        ['a[b][]=1&a[b][]=2', ['a' => ['b' => [0 => '1', 1 => '2']]]],
        ['a[0]=x&a[1]=y', ['a' => [0 => 'x', 1 => 'y']]],
        ['a[1]=x&a[0]=y', ['a' => [1 => 'x', 0 => 'y']]],
        ['a[5]=x&a[]=y', ['a' => [5 => 'x', 6 => 'y']]],
        ['a[]=x&a[5]=y&a[]=z', ['a' => [0 => 'x', 5 => 'y', 6 => 'z']]],
        ['a[07]=x&a[7]=y', ['a' => ['07' => 'x', 7 => 'y']]],
        ['a[-0]=x', ['a' => ['-0' => 'x']]],
        ['a[+7]=x', ['a' => [' 7' => 'x']]],
        ['a[ 7]=x', ['a' => [' 7' => 'x']]],
        ['a[7 ]=x', ['a' => ['7 ' => 'x']]],
        ['a[007]=x', ['a' => ['007' => 'x']]],
        ['a[1.5]=x', ['a' => ['1.5' => 'x']]],
        ['a[0x1]=x', ['a' => ['0x1' => 'x']]],
        ['a[9223372036854775808]=x', ['a' => ['9223372036854775808' => 'x']]],
        ['a[-5]=x', ['a' => [-5 => 'x']]],
        ['a=1&a[]=2', ['a' => [0 => '2']]],
        ['a[]=1&a=2', ['a' => '2']],
        ['a[b]=1&a=2', ['a' => '2']],
        ['a=2&a[b]=1', ['a' => ['b' => '1']]],
        ['a=1&a[b]=2&a[b]=3', ['a' => ['b' => '3']]],
        ['a[b]=1&a[b][c]=2', ['a' => ['b' => ['c' => '2']]]],
        ['a[b][c]=1&a[b]=2', ['a' => ['b' => '2']]],
        ['a[b]=1&a[b][]=2', ['a' => ['b' => [0 => '2']]]],
        ['a[]=1&a[][b]=2', ['a' => [0 => '1', 1 => ['b' => '2']]]],
        ['a[][b]=1&a[][b]=2', ['a' => [0 => ['b' => '1'], 1 => ['b' => '2']]]],
        ['a[][b]=1&a[][c]=2', ['a' => [0 => ['b' => '1'], 1 => ['c' => '2']]]],
        ['a[][]=1&a[][]=2', ['a' => [0 => [0 => '1'], 1 => [0 => '2']]]],
        ['a[b][][c]=1', ['a' => ['b' => [0 => ['c' => '1']]]]],
        ['a[][b][]=1&a[][b][]=2', ['a' => [0 => ['b' => [0 => '1']], 1 => ['b' => [0 => '2']]]]],
        ['[a]=1', []],
        ['[]=1', []],
        ['a[b=1', ['a[b' => '1']],
        ['a[b]c=1', ['a[b]c' => '1']],
        ['a[b]]=1', ['a[b]]' => '1']],
        ['a[b][=1', ['a[b][' => '1']],
        ['a]b=1', ['a]b' => '1']],
        ['a[[b]=1', ['a' => ['[b' => '1']]],
        ['a[b[c]]=1', ['a[b[c]]' => '1']],
        ['a[][[]=1', ['a' => [0 => ['[' => '1']]]],
        ['a[b][c][d][e]=1', ['a' => ['b' => ['c' => ['d' => ['e' => '1']]]]]],
        ['a[b][c][d][e][f]=1', ['a[b][c][d][e][f]' => '1']],
        ['a[b][c][d][e][f][g]=1', ['a[b][c][d][e][f][g]' => '1']],
        ['a[b][c][d]=1', ['a' => ['b' => ['c' => ['d' => '1']]]]],
        ['a[]b=1', ['a[]b' => '1']],
        ['a[]]=1', ['a[]]' => '1']],
        ['a[]][=1', ['a[]][' => '1']],
        ['a[b]%5Bc%5D=1', ['a' => ['b' => ['c' => '1']]]],
        ['a%5Bb%5D=1', ['a' => ['b' => '1']]],
        ['a%5B%5D=1&a%5B%5D=2', ['a' => [0 => '1', 1 => '2']]],
        ['a%5Bb=1', ['a[b' => '1']],
        ['%5Ba%5D=1', []],
        ['a[%5D]=1', ['a[]]' => '1']],
        ['a[b%5D=1', ['a' => ['b' => '1']]],
        ['a[%5B]=1', ['a' => ['[' => '1']]],
        ['a[%5Bb]=1', ['a' => ['[b' => '1']]],
        ['a[b]=1&a[b]c=2', ['a' => ['b' => '1'], 'a[b]c' => '2']],
        ['a[[]=1', ['a' => ['[' => '1']]],
        ['a[]=1&a[[]=2', ['a' => [0 => '1', '[' => '2']]],
        ['a[ ]=1', ['a' => [' ' => '1']]],
        ['a[+]=1', ['a' => [' ' => '1']]],
        ['a[%20]=1', ['a' => [' ' => '1']]],
        ['a[b]&a[c]', ['a' => ['b' => '', 'c' => '']]],
        ['a[]', ['a' => [0 => '']]],
        ['a[]&a[]', ['a' => [0 => '', 1 => '']]],
        ['x[y][z]=1&x[y][w]=2&x[v]=3', ['x' => ['y' => ['z' => '1', 'w' => '2'], 'v' => '3']]],
        ['q=hello+world&f[tags][]=a&f[tags][]=b&f[owner]=bob&page=2', ['q' => 'hello world', 'f' => ['tags' => [0 => 'a', 1 => 'b'], 'owner' => 'bob'], 'page' => '2']],
        ['ids[]=3&ids[]=1&ids[]=2&sort=name&dir=desc', ['ids' => [0 => '3', 1 => '1', 2 => '2'], 'sort' => 'name', 'dir' => 'desc']],
        ['a=1&b=2&c=3&a=4&b[]=5', ['a' => '4', 'b' => [0 => '5'], 'c' => '3']],
        ['k=v&k=w&k[]=x&k[y]=z', ['k' => [0 => 'x', 'y' => 'z']]],
        ['a[b]=1&a[b]=2&a[b]=3', ['a' => ['b' => '3']]],
        ['=&=x&a=', ['a' => '']],
        ['%41=1&A=2', ['A' => '2']],
        ['a%3Db=1', ['a=b' => '1']],
        ['a=%26&b=%3D', ['a' => '&', 'b' => '=']],
        ['a=1%262', ['a' => '1&2']],
        ['%3F=1', ['?' => '1']],
        ['a=1;b=2', ['a' => '1;b=2']],
        ['a=1#b', ['a' => '1#b']],
        ['a b=1', ['a b' => '1']],
        ['a=' . "\xC3" . '' . "\xA9" . '', ['a' => '' . "\xC3" . '' . "\xA9" . '']],
    ];
    $BUILD = [
        [[], ''],
        [['a' => '1'], 'a=1'],
        [['a' => 1], 'a=1'],
        [['a' => true], 'a=1'],
        [['a' => false], 'a=0'],
        [['a' => null], ''],
        [['a' => ''], 'a='],
        [['a' => 'x y'], 'a=x%20y'],
        [['a b' => 'c d'], 'a%20b=c%20d'],
        [['a' => 'é'], 'a=%C3%A9'],
        [['a' => '~-._'], 'a=~-._'],
        [['a' => '!*\'();:@&=+$,/?#[]'], 'a=%21%2A%27%28%29%3B%3A%40%26%3D%2B%24%2C%2F%3F%23%5B%5D'],
        [['a' => [0 => 'x', 1 => 'y']], 'a[]=x&a[]=y'],
        [['a' => [0 => 'x']], 'a[]=x'],
        [['a' => []], ''],
        [['a' => ['b' => '1', 'c' => '2']], 'a[b]=1&a[c]=2'],
        [['a' => ['b' => [0 => 'x', 1 => 'y'], 'c' => ['d' => 'z']]], 'a[b][]=x&a[b][]=y&a[c][d]=z'],
        [['a' => [0 => 'x', 2 => 'y']], 'a[0]=x&a[2]=y'],
        [['a' => [1 => 'x', 0 => 'y']], 'a[1]=x&a[0]=y'],
        [['a' => [0 => 'x', 1 => 'y']], 'a[]=x&a[]=y'],
        [['a' => [1 => 'x', 2 => 'y']], 'a[1]=x&a[2]=y'],
        [['a' => [0 => 'x', 1 => 'y', 3 => 'z']], 'a[0]=x&a[1]=y&a[3]=z'],
        [[0 => 'x', 1 => 'y'], '0=x&1=y'],
        [['x' => ['y' => ['z' => ['w' => 1]]]], 'x[y][z][w]=1'],
        [['a' => [0 => [0 => 'b', 1 => 'c'], 1 => [0 => 'd']]], 'a[][]=b&a[][]=c&a[][]=d'],
        [['a' => [0 => ['b' => 1], 1 => ['b' => 2]]], 'a[][b]=1&a[][b]=2'],
        [['a' => [0 => 'x', 1 => null, 2 => 'y']], 'a[]=x&a[]=y'],
        [['a' => [0 => null]], ''],
        [['a' => ['b' => null]], ''],
        [['q' => 'a b', 'f' => ['tags' => [0 => 'x', 1 => 'y'], 'owner' => 'bob', 'n' => null]], 'q=a%20b&f[tags][]=x&f[tags][]=y&f[owner]=bob'],
        [['a[b' => '1'], 'a%5Bb=1'],
        [['a]' => '1'], 'a%5D=1'],
        [['a' => ['b[c' => '1']], 'a[b%5Bc]=1'],
        [['a' => ['b]' => '1', '[' => '2']], 'a[b%5D]=1&a[%5B]=2'],
        [['' => 'x'], '=x'],
        [['a' => ['' => 'x']], 'a[]=x'],
        [['k' => 'v', 'k2' => [0 => '1', 1 => '2', 2 => '3'], 'k3' => ['p' => 'q'], 'z' => 0], 'k=v&k2[]=1&k2[]=2&k2[]=3&k3[p]=q&z=0'],
        [['n' => -5], 'n=-5'],
        [['n' => 0], 'n=0'],
        [['n' => 12345678901234], 'n=12345678901234'],
        [['a' => [-1 => 'x']], 'a[-1]=x'],
        [['a' => ['x' => []]], ''],
        [['a' => ['x' => [], 'y' => 1]], 'a[y]=1'],
        [['a' => [0 => []]], ''],
        [['a' => [0 => [], 1 => [0 => 1]]], 'a[][]=1'],
        [['日本' => '語'], '%E6%97%A5%E6%9C%AC=%E8%AA%9E'],
        [['ascii' => ' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~'], 'ascii=%20%21%22%23%24%25%26%27%28%29%2A%2B%2C-.%2F0123456789%3A%3B%3C%3D%3E%3F%40ABCDEFGHIJKLMNOPQRSTUVWXYZ%5B%5C%5D%5E_%60abcdefghijklmnopqrstuvwxyz%7B%7C%7D~'],
        [[' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~' => 'v'], '%20%21%22%23%24%25%26%27%28%29%2A%2B%2C-.%2F0123456789%3A%3B%3C%3D%3E%3F%40ABCDEFGHIJKLMNOPQRSTUVWXYZ%5B%5C%5D%5E_%60abcdefghijklmnopqrstuvwxyz%7B%7C%7D~=v'],
        [['azAZ09' => 'zZaA9_0-.~/:@[`{'], 'azAZ09=zZaA9_0-.~%2F%3A%40%5B%60%7B'],
        [['a' => [' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~' => [0 => 'q']]], 'a[%20%21%22%23%24%25%26%27%28%29%2A%2B%2C-.%2F0123456789%3A%3B%3C%3D%3E%3F%40ABCDEFGHIJKLMNOPQRSTUVWXYZ%5B%5C%5D%5E_%60abcdefghijklmnopqrstuvwxyz%7B%7C%7D~][]=q'],
        [['a' => '%'], 'a=%25'],
        [['a' => '+'], 'a=%2B'],
        [['a' => 'a+b'], 'a=a%2Bb'],
        [['a' => 'a%20b'], 'a=a%2520b'],
        [['a' => 1.5], null],
        [['a' => ['b' => 0.5]], null],
        [['a' => new stdClass()], null],
    ];
    $WITHOUT = [
        ['a=1&b=2&c=3', 'b', 'a=1&c=3'],
        ['a=1&b[x]=2&b=3&c=4', 'b', 'a=1&c=4'],
        ['a=1&b[]=2&bb=3&c=4', 'b', 'a=1&bb=3&c=4'],
        ['a=1&b%5Bx%5D=2&c=4', 'b', 'a=1&c=4'],
        ['a=1&%62=2&c=4', 'b', 'a=1&c=4'],
        ['?a=1&b=2', 'a', 'b=2'],
        ['?a=1&b=2', 'z', 'a=1&b=2'],
        ['', 'a', ''],
        ['a', 'a', ''],
        ['a=&b', 'b', 'a='],
        ['a[b]=1&a[c]=2&ab=3', 'a', 'ab=3'],
        ['a[b]=1&a[c]=2&ab=3', 'a[b]', 'a[c]=2&ab=3'],
        ['x[y][z]=1&x[y]=2&x=3&xy=4', 'x[y]', 'x=3&xy=4'],
        ['a=1&&b=2&', 'c', 'a=1&b=2'],
        ['a%2Bb=1&a+b=2', 'a+b', 'a+b=2'],
        ['a+b=1&a%20b=2&c=3', 'a b', 'c=3'],
        ['a=1&b=2', 'a=1', 'a=1&b=2'],
        ['[a]=1&a=2', '[a]', 'a=2'],
        ['a[]=1&a[]=2&b=3', 'a', 'b=3'],
    ];

    function try_call(callable $f)
    {
        try {
            return $f();
        } catch (InvalidArgumentException $e) {
            return null;
        }
    }

    /** what parse(build(x)) should give back: values as strings, nulls and empty arrays gone */
    function normalized($x)
    {
        if (!is_array($x)) {
            if ($x === null) {
                return null;
            }
            return is_bool($x) ? ($x ? '1' : '0') : (string)$x;
        }
        $out = [];
        foreach ($x as $k => $v) {
            $n = normalized($v);
            if ($n === null || $n === []) {
                continue;
            }
            $out[$k] = $n;
        }
        return $out;
    }

    test('parse table', function () use ($PARSE) {
        foreach ($PARSE as [$query, $want]) {
            eq(Qs::parse($query), $want, 'parse(' . $query . ')');
        }
    });

    test('build table', function () use ($BUILD) {
        foreach ($BUILD as [$params, $want]) {
            eq(try_call(fn() => Qs::build($params)), $want, 'build(' . json_encode($params) . ')');
        }
    });

    test('build then parse is a round trip for lists and maps of strings', function () {
        $samples = [
            ['a' => 'x', 'b' => 'y z'],
            ['a' => ['x', 'y', 'z']],
            ['a' => ['b' => ['c' => ['d' => 'e']]]],
            ['a' => [['b' => '1'], ['b' => '2']]],
            ['f' => ['tags' => ['x', 'y'], 'owner' => 'bob'], 'page' => '2'],
            ['a b' => ['c d' => 'e f'], 'é' => ['ü' => 'ö']],
            ['a' => ['[' => ']', 'x[y' => 'z]']],
            ['k' => ['a&b' => 'c=d', 'e' => '%41 +']],
            ['n' => 12, 't' => true, 'f' => false, 'z' => null, 'e' => []],
            ['a' => [1 => 'x', 2 => 'y']],
            ['a' => [3 => 'x', 0 => 'y']],
        ];
        foreach ($samples as $i => $s) {
            eq(Qs::parse(Qs::build($s)), normalized($s), "round trip of sample $i");
        }
    });

    test('without table', function () use ($WITHOUT) {
        foreach ($WITHOUT as [$query, $key, $want]) {
            eq(Qs::without($query, $key), $want, "without('$query', '$key')");
        }
    });

    test('parse never throws', function () {
        foreach (['', '&', '=', '[', ']', '[]', '[][]', '%', '%%', '&=&=', 'a[', 'a[]', 'a[][', "a=\x00", "\xff=\xfe", str_repeat('a[', 50), str_repeat('&', 100), 'a[b][c][d][e][f]=1'] as $q) {
            $r = Qs::parse($q);
            ok(is_array($r), 'result is an array for ' . bin2hex($q));
        }
    });

    t_done();
''')

LIB = Lib(
    name="nestedqs", lang="php", title="the Qs query-string helper",
    blurb="The search page of the intranet keeps its filters in the URL as nested query strings like `f[tags][]=a&f[owner]=bob`, and reads and writes them with the Qs helper.",
    files={"README.md": README1, "src/Qs.php": F2},
    visible_tests={"tests/run.php": _lang3.php_test(V3)},
    hidden_tests={"tests/run.php": _lang3.php_test(H4)},
    mutate=["src/Qs.php"], difficulty=3, tags=["url", "parsing", "encoding"],
)

_lang3.add(LIB, n=8)
