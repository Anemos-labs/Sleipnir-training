"""Dot-notation array access (php): get/set/forget with escapes and wildcards, flatten and expand, deep merge that replaces lists, grouping and stable multi-key sorting; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # Dot

    Dot-notation helpers for nested PHP arrays (`src/Dot.php`, class `Dot`, static methods). `InvalidArgumentException` is thrown for the invalid arguments listed below.

    ## Paths

    A path is a string of keys separated by `.`: `db.hosts.0.port`. Rules:

    * a backslash escapes the next character when it is `.`, `*` or `\` (`a\.b` is the single key `a.b`, `\*` the literal key `*`, `\\` one backslash); any other backslash is an ordinary character;
    * a segment that is exactly an unescaped `*` is a **wildcard** (only `get` and `has` accept it; `set`, `forget` and `flatten`'s inverse never see one);
    * the empty path `''` is invalid; empty segments (`a..b`) are ordinary keys named `''`.

    Keys such as `'0'` and `0` are the same key, as in PHP.

    ## `Dot::get(array $a, string $path, mixed $default = null): mixed`
    The value at the path; `$default` when any step is missing. A value that exists but is `null` is returned as `null`, **not** replaced by the default. A step through a non-array value is a missing step.
    With wildcards the result is always a list: every wildcard expands to all elements of the array at that point (in order), and the values found at the rest of the path are collected; elements that lack the rest of the path are skipped
    (so the result may be `[]`); `$default` is not used.

    ## `Dot::has(array $a, string $path): bool`
    Whether the path exists (a `null` value exists). With wildcards: whether at least one expansion exists.

    ## `Dot::set(array &$a, string $path, mixed $value): void`
    Stores the value, creating arrays for missing steps. A step that currently holds a non-array value is replaced by a new array. A wildcard in the path is invalid.

    ## `Dot::forget(array &$a, string $path): bool`
    Removes the key at the path; returns whether something was removed. Parents stay (an emptied parent stays as `[]`); lists are not re-indexed. A wildcard in the path is invalid.

    ## `Dot::flatten(array $a): array`
    A flat map `path => value` in depth-first order. Every non-array value (including `null`) is a leaf, and so is an **empty array** (kept as `[]`). Keys are escaped as in paths (`.`, `*` and `\` get a backslash) so that every path is unambiguous.

    ## `Dot::expand(array $flat): array`
    The inverse of `flatten`: each key is split as a path and the value stored with `set`, in order (a later entry may replace a scalar by an array or the other way round). A wildcard key is invalid.

    ## `Dot::merge(array $base, array $over): array`
    Deep merge: for each key of `$over`: if both values are arrays and **both are maps**, they are merged recursively; in every other case the value from `$over` replaces the one in `$base`. A *list* is an
    array whose keys are exactly `0, 1, ..., n-1` in this order, and the empty array is a list. So lists are replaced as a whole, never combined, and a `[]` in `$over` clears a map. Keys that exist only in `$base` stay; keys that exist only in `$over` are appended.
    Key order: the keys of `$base` first (in their order), then the new keys of `$over`.

    ## `Dot::pluck(array $rows, string $path): array`
    `get` for every row (rows that are not arrays, or lack the path, are skipped), as a list.

    ## `Dot::groupBy(array $rows, string $path): array`
    Groups the rows by the scalar at `$path` (cast to string: `true` is `'1'`, `false` is `''`, `null` is `''`) into `['key' => [row, ...]]`, groups in order of first appearance and rows keeping their order. Rows that lack the path are skipped; a value that is
    an array is `InvalidArgumentException`.

    ## `Dot::sortBy(array $rows, array $keys): array`
    A stable sort of the rows by several paths. `$keys` is a list of paths; a path starting with `-` sorts descending (the dash is not part of the path). Rows are compared key by key with PHP's `<=>`; a missing path counts as `null`.
    The result is a list. `$keys` must not be empty.
''')

F2 = dd(r'''
    <?php
    declare(strict_types=1);

    class Dot
    {
        /** @return list<array{string,bool}> segments with a wildcard flag */
        private static function parse(string $path): array
        {
            if ($path === '') {
                throw new InvalidArgumentException('empty path');
            }
            $segments = [];
            $cur = '';
            $escaped = false;
            $n = strlen($path);
            for ($i = 0; $i < $n; $i++) {
                $c = $path[$i];
                if ($c === '\\' && $i + 1 < $n && ($path[$i + 1] === '.' || $path[$i + 1] === '*' || $path[$i + 1] === '\\')) {
                    $cur .= $path[$i + 1];
                    $escaped = true;
                    $i++;
                } elseif ($c === '.') {
                    $segments[] = [$cur, $cur === '*' && !$escaped];
                    $cur = '';
                    $escaped = false;
                } else {
                    $cur .= $c;
                }
            }
            $segments[] = [$cur, $cur === '*' && !$escaped];
            return $segments;
        }

        private static function noWildcard(array $segments): void
        {
            foreach ($segments as [, $wild]) {
                if ($wild) {
                    throw new InvalidArgumentException('wildcards are not allowed here');
                }
            }
        }

        private static function collect($node, array $segments, array &$found): void
        {
            if (count($segments) === 0) {
                $found[] = $node;
                return;
            }
            [$key, $wild] = $segments[0];
            $rest = array_slice($segments, 1);
            if (!is_array($node)) {
                return;
            }
            if ($wild) {
                foreach ($node as $child) {
                    self::collect($child, $rest, $found);
                }
            } elseif (array_key_exists($key, $node)) {
                self::collect($node[$key], $rest, $found);
            }
        }

        public static function get(array $a, string $path, $default = null)
        {
            $segments = self::parse($path);
            $found = [];
            self::collect($a, $segments, $found);
            foreach ($segments as [, $wild]) {
                if ($wild) {
                    return $found;
                }
            }
            return count($found) > 0 ? $found[0] : $default;
        }

        public static function has(array $a, string $path): bool
        {
            $found = [];
            self::collect($a, self::parse($path), $found);
            return count($found) > 0;
        }

        public static function set(array &$a, string $path, $value): void
        {
            $segments = self::parse($path);
            self::noWildcard($segments);
            $node = &$a;
            foreach ($segments as $i => [$key]) {
                if ($i === count($segments) - 1) {
                    $node[$key] = $value;
                    return;
                }
                if (!isset($node[$key]) || !is_array($node[$key])) {
                    $node[$key] = [];
                }
                $node = &$node[$key];
            }
        }

        public static function forget(array &$a, string $path): bool
        {
            $segments = self::parse($path);
            self::noWildcard($segments);
            $node = &$a;
            $last = count($segments) - 1;
            foreach ($segments as $i => [$key]) {
                if (!is_array($node) || !array_key_exists($key, $node)) {
                    return false;
                }
                if ($i === $last) {
                    unset($node[$key]);
                    return true;
                }
                $node = &$node[$key];
            }
            return false;
        }

        private static function escapeKey(string $key): string
        {
            return str_replace(['\\', '.', '*'], ['\\\\', '\\.', '\\*'], $key);
        }

        public static function flatten(array $a): array
        {
            $out = [];
            self::flattenInto($a, '', $out);
            return $out;
        }

        private static function flattenInto(array $node, string $prefix, array &$out): void
        {
            foreach ($node as $k => $v) {
                $path = $prefix . self::escapeKey((string)$k);
                if (is_array($v) && count($v) > 0) {
                    self::flattenInto($v, $path . '.', $out);
                } else {
                    $out[$path] = $v;
                }
            }
        }

        public static function expand(array $flat): array
        {
            $out = [];
            foreach ($flat as $path => $value) {
                self::set($out, (string)$path, $value);
            }
            return $out;
        }

        private static function isList(array $a): bool
        {
            return array_keys($a) === range(0, count($a) - 1) || count($a) === 0;
        }

        public static function merge(array $base, array $over): array
        {
            foreach ($over as $k => $v) {
                if (array_key_exists($k, $base) && is_array($v) && is_array($base[$k]) && !self::isList($v) && !self::isList($base[$k])) {
                    $base[$k] = self::merge($base[$k], $v);
                } else {
                    $base[$k] = $v;
                }
            }
            return $base;
        }

        public static function pluck(array $rows, string $path): array
        {
            $out = [];
            foreach ($rows as $row) {
                if (is_array($row) && self::has($row, $path)) {
                    $out[] = self::get($row, $path);
                }
            }
            return $out;
        }

        public static function groupBy(array $rows, string $path): array
        {
            $groups = [];
            foreach ($rows as $row) {
                if (!is_array($row) || !self::has($row, $path)) {
                    continue;
                }
                $v = self::get($row, $path);
                if (is_array($v)) {
                    throw new InvalidArgumentException('cannot group by an array value');
                }
                $key = is_bool($v) ? ($v ? '1' : '') : (string)$v;
                $groups[$key][] = $row;
            }
            return $groups;
        }

        public static function sortBy(array $rows, array $keys): array
        {
            if (count($keys) === 0) {
                throw new InvalidArgumentException('no sort keys');
            }
            $spec = [];
            foreach ($keys as $k) {
                $desc = strlen($k) > 0 && $k[0] === '-';
                $spec[] = [$desc ? substr($k, 1) : $k, $desc];
            }
            $rows = array_values($rows);
            usort($rows, function ($x, $y) use ($spec) {
                foreach ($spec as [$path, $desc]) {
                    $a = is_array($x) ? self::get($x, $path) : null;
                    $b = is_array($y) ? self::get($y, $path) : null;
                    $c = $a <=> $b;
                    if ($c !== 0) {
                        return $desc ? -$c : $c;
                    }
                }
                return 0;
            });
            return $rows;
        }
    }
''')

V3 = dd(r'''
    require __DIR__ . '/../src/Dot.php';

    test('basics', function () {
        $cfg = ['db' => ['host' => 'localhost', 'ports' => [5432, 5433]]];
        eq(Dot::get($cfg, 'db.host'), 'localhost');
        eq(Dot::get($cfg, 'db.ports.1'), 5433);
        eq(Dot::get($cfg, 'db.user', 'root'), 'root');
        Dot::set($cfg, 'cache.ttl', 60);
        eq($cfg['cache'], ['ttl' => 60]);
    });

    t_done();
''')

H4 = dd(r'''
    require __DIR__ . '/../src/Dot.php';

    $CFG = [
        'app' => ['name' => 'Reports', 'debug' => false, 'owner' => null, 'tags' => ['a', 'b', 'c']],
        'db' => ['hosts' => [['name' => 'h1', 'port' => 5432], ['name' => 'h2', 'port' => 5433], ['name' => 'h3']]],
        'a.b' => ['c' => 1],
        '*' => 'star',
        'x\\y' => 'slash',
        '' => ['' => 'empty'],
        'n' => ['0' => 'zero', '1' => 'one'],
        'e' => [],
    ];

    test('get: plain paths', function () use ($CFG) {
        eq(Dot::get($CFG, 'app.name'), 'Reports');
        eq(Dot::get($CFG, 'app.debug'), false);
        eq(Dot::get($CFG, 'app.tags.0'), 'a');
        eq(Dot::get($CFG, 'app.tags.2'), 'c');
        eq(Dot::get($CFG, 'app.tags.3'), null);
        eq(Dot::get($CFG, 'app.tags.3', 'dflt'), 'dflt');
        eq(Dot::get($CFG, 'db.hosts.1.port'), 5433);
        eq(Dot::get($CFG, 'db.hosts.2.port', 'none'), 'none');
        eq(Dot::get($CFG, 'e'), []);
        eq(Dot::get($CFG, 'e', 'dflt'), []);
        eq(Dot::get($CFG, 'e.x', 'dflt'), 'dflt');
        eq(Dot::get($CFG, 'app'), $CFG['app']);
        eq(Dot::get([], 'a', 5), 5);
        eq(Dot::get(['a' => 0], 'a', 5), 0);
        eq(Dot::get(['a' => ''], 'a', 5), '');
        eq(Dot::get(['a' => [1]], 'a.0.b', 5), 5);
        eq(Dot::get(['a' => 'str'], 'a.0', 'd'), 'd');
    });

    test('get: null values are values', function () use ($CFG) {
        eq(Dot::get($CFG, 'app.owner', 'dflt'), null);
        eq(Dot::get(['a' => null], 'a', 'dflt'), null);
        eq(Dot::get(['a' => ['b' => null]], 'a.b', 'dflt'), null);
        eq(Dot::get(['a' => ['b' => null]], 'a.c', 'dflt'), 'dflt');
    });

    test('get: escapes and odd keys', function () use ($CFG) {
        eq(Dot::get($CFG, 'a\\.b.c'), 1);
        eq(Dot::get($CFG, 'a.b.c', 'no'), 'no');
        eq(Dot::get($CFG, '\\*'), 'star');
        eq(Dot::get($CFG, 'x\\\\y'), 'slash');
        eq(Dot::get($CFG, '.'), 'empty');
        eq(Dot::get($CFG, 'n.0'), 'zero');
        eq(Dot::get($CFG, 'n.1'), 'one');
        eq(Dot::get(['a\\b' => 1], 'a\\b'), 1);
        eq(Dot::get(['a\\' => 1], 'a\\'), 1);
        eq(Dot::get(['a.' => 1], 'a\\.'), 1);
        eq(Dot::get(['\\' => 1], '\\\\'), 1);
        eq(Dot::get(['a' => ['' => ['b' => 7]]], 'a..b'), 7);
        raises(fn() => Dot::get([], ''), InvalidArgumentException::class, 'empty path');
    });

    test('get and has: wildcards', function () use ($CFG) {
        eq(Dot::get($CFG, 'db.hosts.*.name'), ['h1', 'h2', 'h3']);
        eq(Dot::get($CFG, 'db.hosts.*.port'), [5432, 5433]);
        eq(Dot::get($CFG, 'db.hosts.*.port', 'd'), [5432, 5433]);
        eq(Dot::get($CFG, 'db.hosts.*.zzz', 'd'), []);
        eq(Dot::get($CFG, 'app.tags.*'), ['a', 'b', 'c']);
        eq(Dot::get($CFG, 'nope.*', 'd'), []);
        eq(Dot::get($CFG, 'e.*'), []);
        eq(Dot::get($CFG, 'app.*'), ['Reports', false, null, ['a', 'b', 'c']]);
        eq(Dot::get($CFG, 'app.name.*'), []);
        eq(Dot::get(['a' => [['b' => [1, 2]], ['b' => [3]]]], 'a.*.b.*'), [1, 2, 3]);
        eq(Dot::get(['a' => [['b' => 1], ['c' => 2]]], 'a.*.b'), [1]);
        eq(Dot::get(['a' => [1, 2]], '*.0'), [1]);
        eq(Dot::get(['a' => ['x' => ['k' => 1]], 'b' => ['y' => ['k' => 2]]], '*.*.k'), [1, 2]);
        eq(Dot::has($CFG, 'db.hosts.*.port'), true);
        eq(Dot::has($CFG, 'db.hosts.*.zzz'), false);
        eq(Dot::has($CFG, 'app.owner'), true);
        eq(Dot::has($CFG, 'app.*'), true);
        eq(Dot::has($CFG, 'e.*'), false);
        eq(Dot::has($CFG, 'nope.*'), false);
        eq(Dot::has($CFG, '\\*'), true);
        eq(Dot::get($CFG, '\\*.x', 'd'), 'd');
    });

    test('has', function () use ($CFG) {
        eq(Dot::has($CFG, 'app.name'), true);
        eq(Dot::has($CFG, 'app.owner'), true);
        eq(Dot::has($CFG, 'app.debug'), true);
        eq(Dot::has($CFG, 'app.nothing'), false);
        eq(Dot::has($CFG, 'app.tags.2'), true);
        eq(Dot::has($CFG, 'app.tags.3'), false);
        eq(Dot::has($CFG, 'app.name.x'), false);
        eq(Dot::has($CFG, 'e'), true);
        eq(Dot::has($CFG, 'a\\.b'), true);
        eq(Dot::has($CFG, 'a.b'), false);
        eq(Dot::has([], 'x'), false);
        raises(fn() => Dot::has([], ''), InvalidArgumentException::class, 'empty path');
    });

    test('set', function () {
        $a = [];
        Dot::set($a, 'x', 1);
        eq($a, ['x' => 1]);
        Dot::set($a, 'p.q.r', 2);
        eq($a, ['x' => 1, 'p' => ['q' => ['r' => 2]]]);
        Dot::set($a, 'p.q.s', 3);
        eq($a['p']['q'], ['r' => 2, 's' => 3]);
        Dot::set($a, 'x.y', 4);   // a scalar in the way is replaced by an array
        eq($a['x'], ['y' => 4]);
        Dot::set($a, 'p', 'flat');
        eq($a['p'], 'flat');
        Dot::set($a, 'l.0', 'a');
        Dot::set($a, 'l.1', 'b');
        eq($a['l'], ['a', 'b']);
        Dot::set($a, 'l.0', 'z');
        eq($a['l'], ['z', 'b']);
        Dot::set($a, 'n', null);
        Dot::set($a, 'n.k', 1);   // null in the way is replaced as well
        eq($a['n'], ['k' => 1]);
        Dot::set($a, 'a\\.b.c', 5);
        eq($a['a.b'], ['c' => 5]);
        Dot::set($a, '\\*', 'lit');
        eq($a['*'], 'lit');
        Dot::set($a, 'e', []);
        Dot::set($a, 'e.k', 1);
        eq($a['e'], ['k' => 1]);
        Dot::set($a, 'f.', 'tail');
        eq($a['f'], ['' => 'tail']);
        $b = ['k' => ['x' => 1]];
        Dot::set($b, 'k', ['y' => 2]);
        eq($b, ['k' => ['y' => 2]]);
        $c = ['k' => ['x' => 1, 'y' => 2]];
        Dot::set($c, 'k.x', null);
        eq($c, ['k' => ['x' => null, 'y' => 2]]);
    });

    test('set: invalid paths', function () {
        $a = ['k' => 1];
        raises(function () use (&$a) { Dot::set($a, '', 1); }, InvalidArgumentException::class, 'empty path');
        raises(function () use (&$a) { Dot::set($a, 'a.*.b', 1); }, InvalidArgumentException::class, 'wildcard');
        raises(function () use (&$a) { Dot::set($a, '*', 1); }, InvalidArgumentException::class, 'lone wildcard');
        eq($a, ['k' => 1]);
    });

    test('forget', function () {
        $a = ['a' => ['b' => 1, 'c' => 2], 'l' => ['x', 'y', 'z'], 'n' => null, 'e' => []];
        eq(Dot::forget($a, 'a.b'), true);
        eq($a['a'], ['c' => 2]);
        eq(Dot::forget($a, 'a.b'), false);
        eq(Dot::forget($a, 'a.c'), true);
        eq($a['a'], []);
        eq(Dot::forget($a, 'l.1'), true);
        eq($a['l'], [0 => 'x', 2 => 'z']);
        eq(Dot::forget($a, 'n'), true);
        eq(array_key_exists('n', $a), false);
        eq(Dot::forget($a, 'zzz'), false);
        eq(Dot::forget($a, 'zzz.y'), false);
        eq(Dot::forget($a, 'l.0.x'), false);
        eq(Dot::forget($a, 'e'), true);
        eq(array_keys($a), ['a', 'l']);
        $b = ['a.b' => 1, 'a' => ['b' => 2]];
        eq(Dot::forget($b, 'a\\.b'), true);
        eq($b, ['a' => ['b' => 2]]);
        raises(function () use (&$a) { Dot::forget($a, 'l.*'); }, InvalidArgumentException::class, 'wildcard');
        raises(function () use (&$a) { Dot::forget($a, ''); }, InvalidArgumentException::class, 'empty path');
    });

    test('flatten', function () {
        eq(Dot::flatten([]), []);
        eq(Dot::flatten(['a' => 1]), ['a' => 1]);
        eq(Dot::flatten(['a' => ['b' => ['c' => 1], 'd' => 2], 'e' => 3]), ['a.b.c' => 1, 'a.d' => 2, 'e' => 3]);
        eq(Dot::flatten(['l' => [10, 20, ['x' => 1]]]), ['l.0' => 10, 'l.1' => 20, 'l.2.x' => 1]);
        eq(Dot::flatten(['a' => [], 'b' => ['c' => []]]), ['a' => [], 'b.c' => []]);
        eq(Dot::flatten(['a' => null, 'b' => false, 'c' => 0, 'd' => '']), ['a' => null, 'b' => false, 'c' => 0, 'd' => '']);
        eq(Dot::flatten(['a.b' => ['c' => 1], '*' => 2, 'x\\y' => 3, 'p.*' => 4]), ['a\\.b.c' => 1, '\\*' => 2, 'x\\\\y' => 3, 'p\\.\\*' => 4]);
        eq(Dot::flatten(['' => ['' => 1]]), ['.' => 1]);
        eq(array_keys(Dot::flatten(['b' => 1, 'a' => ['z' => 1, 'y' => 2], 'c' => 3])), ['b', 'a.z', 'a.y', 'c']);
    });

    test('expand', function () {
        eq(Dot::expand([]), []);
        eq(Dot::expand(['a.b.c' => 1, 'a.d' => 2, 'e' => 3]), ['a' => ['b' => ['c' => 1], 'd' => 2], 'e' => 3]);
        eq(Dot::expand(['l.0' => 'x', 'l.1' => 'y']), ['l' => ['x', 'y']]);
        eq(Dot::expand(['a\\.b.c' => 1, '\\*' => 2, 'x\\\\y' => 3]), ['a.b' => ['c' => 1], '*' => 2, 'x\\y' => 3]);
        eq(Dot::expand(['a' => 1, 'a.b' => 2]), ['a' => ['b' => 2]]);
        eq(Dot::expand(['a.b' => 2, 'a' => 1]), ['a' => 1]);
        eq(Dot::expand(['a' => []]), ['a' => []]);
        eq(Dot::expand(['a.b' => null]), ['a' => ['b' => null]]);
        raises(fn() => Dot::expand(['a.*' => 1]), InvalidArgumentException::class, 'wildcard key');
        raises(fn() => Dot::expand(['' => 1]), InvalidArgumentException::class, 'empty key');
    });

    test('flatten and expand round trip', function () {
        $samples = [
            [],
            ['a' => 1],
            ['a' => ['b' => ['c' => ['d' => null]]]],
            ['a.b' => 1, 'c' => ['d.e' => ['f*g' => 2]], '*' => ['*' => 3]],
            ['x\\y' => ['z\\' => 1], '\\' => 2, 'a\\.b' => 3],
            ['l' => [1, 2, [3, 4, ['k' => 5]]], 'm' => []],
            ['' => ['' => ['' => 1]]],
            ['0' => 'a', '1' => ['2' => 'b']],
            ['k' => ['.' => 1, '..' => 2, '.*.' => 3]],
        ];
        foreach ($samples as $i => $s) {
            eq(Dot::expand(Dot::flatten($s)), $s, "round trip of sample $i");
        }
    });

    test('merge', function () {
        eq(Dot::merge([], []), []);
        eq(Dot::merge(['a' => 1], []), ['a' => 1]);
        eq(Dot::merge([], ['a' => 1]), ['a' => 1]);
        eq(Dot::merge(['a' => 1, 'b' => 2], ['b' => 3, 'c' => 4]), ['a' => 1, 'b' => 3, 'c' => 4]);
        eq(array_keys(Dot::merge(['b' => 1, 'a' => 2], ['c' => 3, 'a' => 4, 'b' => 5])), ['b', 'a', 'c']);
        eq(Dot::merge(['m' => ['x' => 1, 'y' => 2]], ['m' => ['y' => 3, 'z' => 4]]), ['m' => ['x' => 1, 'y' => 3, 'z' => 4]]);
        eq(Dot::merge(['m' => ['n' => ['x' => 1]]], ['m' => ['n' => ['y' => 2]]]), ['m' => ['n' => ['x' => 1, 'y' => 2]]]);
        eq(Dot::merge(['l' => [1, 2, 3]], ['l' => [9]]), ['l' => [9]]);
        eq(Dot::merge(['l' => [1]], ['l' => [8, 9]]), ['l' => [8, 9]]);
        eq(Dot::merge(['m' => ['x' => 1]], ['m' => []]), ['m' => []]);
        eq(Dot::merge(['m' => []], ['m' => ['x' => 1]]), ['m' => ['x' => 1]]);
        eq(Dot::merge(['m' => ['x' => 1]], ['m' => [5]]), ['m' => [5]]);
        eq(Dot::merge(['m' => [5]], ['m' => ['x' => 1]]), ['m' => ['x' => 1]]);
        eq(Dot::merge(['m' => ['x' => 1]], ['m' => 'str']), ['m' => 'str']);
        eq(Dot::merge(['m' => 'str'], ['m' => ['x' => 1]]), ['m' => ['x' => 1]]);
        eq(Dot::merge(['a' => 1], ['a' => null]), ['a' => null]);
        eq(Dot::merge(['a' => null], ['a' => 1]), ['a' => 1]);
        eq(Dot::merge(['m' => ['x' => ['p' => 1, 'q' => 2]]], ['m' => ['x' => ['q' => 3]]]), ['m' => ['x' => ['p' => 1, 'q' => 3]]]);
        eq(Dot::merge([5 => 'a', 7 => 'b'], [5 => 'c']), [5 => 'c', 7 => 'b']);
        eq(Dot::merge(['m' => [1 => 'a', 2 => 'b']], ['m' => [2 => 'c']]), ['m' => [1 => 'a', 2 => 'c']]);
        eq(Dot::merge(['m' => [0 => 'a', 1 => 'b']], ['m' => [1 => 'c']]), ['m' => [1 => 'c']]);
        eq(Dot::merge(['m' => ['x' => 1]], ['m' => [1 => 'c']]), ['m' => ['x' => 1, 1 => 'c']]);
        $base = ['m' => ['x' => 1]];
        Dot::merge($base, ['m' => ['y' => 2]]);
        eq($base, ['m' => ['x' => 1]]);
    });

    test('pluck', function () {
        $rows = [['n' => 'a', 'v' => 1], ['n' => 'b'], 'junk', ['n' => 'c', 'v' => null], ['v' => 4], ['n' => 'd', 'v' => ['x' => 1]]];
        eq(Dot::pluck($rows, 'n'), ['a', 'b', 'c', 'd']);
        eq(Dot::pluck($rows, 'v'), [1, null, 4, ['x' => 1]]);
        eq(Dot::pluck($rows, 'v.x'), [1]);
        eq(Dot::pluck([], 'n'), []);
        eq(Dot::pluck(['k1' => ['n' => 1], 'k2' => ['n' => 2]], 'n'), [1, 2]);
        eq(Dot::pluck([['a.b' => 5]], 'a\\.b'), [5]);
    });

    test('groupBy', function () {
        $rows = [['t' => 'x', 'i' => 1], ['t' => 'y', 'i' => 2], ['t' => 'x', 'i' => 3], ['i' => 4], ['t' => 5, 'i' => 5], ['t' => '5', 'i' => 6], ['t' => true, 'i' => 7], ['t' => false, 'i' => 8], ['t' => null, 'i' => 9], 'junk'];
        eq(Dot::groupBy($rows, 't'), [
            'x' => [['t' => 'x', 'i' => 1], ['t' => 'x', 'i' => 3]],
            'y' => [['t' => 'y', 'i' => 2]],
            '5' => [['t' => 5, 'i' => 5], ['t' => '5', 'i' => 6]],
            '1' => [['t' => true, 'i' => 7]],
            '' => [['t' => false, 'i' => 8], ['t' => null, 'i' => 9]],
        ]);
        eq(array_keys(Dot::groupBy($rows, 't')), ['x', 'y', 5, 1, '']);
        eq(Dot::groupBy([['a' => ['b' => 'p']], ['a' => ['b' => 'q']], ['a' => ['b' => 'p']]], 'a.b'), ['p' => [['a' => ['b' => 'p']], ['a' => ['b' => 'p']]], 'q' => [['a' => ['b' => 'q']]]]);
        eq(Dot::groupBy([], 't'), []);
        raises(fn() => Dot::groupBy([['t' => [1]]], 't'), InvalidArgumentException::class, 'array value');
    });

    test('sortBy', function () {
        $rows = [
            ['n' => 'bob', 'age' => 30, 'city' => 'Oslo'],
            ['n' => 'amy', 'age' => 25, 'city' => 'Rome'],
            ['n' => 'cat', 'age' => 30, 'city' => 'Bern'],
            ['n' => 'dan', 'age' => 25, 'city' => 'Oslo'],
            ['n' => 'eve', 'age' => 30, 'city' => 'Oslo'],
            ['n' => 'fay'],
        ];
        $names = fn(array $r) => array_column($r, 'n');
        eq($names(Dot::sortBy($rows, ['age'])), ['fay', 'amy', 'dan', 'bob', 'cat', 'eve']);
        eq($names(Dot::sortBy($rows, ['-age'])), ['bob', 'cat', 'eve', 'amy', 'dan', 'fay']);
        eq($names(Dot::sortBy($rows, ['age', 'n'])), ['fay', 'amy', 'dan', 'bob', 'cat', 'eve']);
        eq($names(Dot::sortBy($rows, ['age', '-n'])), ['fay', 'dan', 'amy', 'eve', 'cat', 'bob']);
        eq($names(Dot::sortBy($rows, ['-age', 'city', '-n'])), ['cat', 'eve', 'bob', 'dan', 'amy', 'fay']);
        eq($names(Dot::sortBy($rows, ['city'])), ['fay', 'cat', 'bob', 'dan', 'eve', 'amy']);
        eq($names(Dot::sortBy($rows, ['-city'])), ['amy', 'bob', 'dan', 'eve', 'cat', 'fay']);
        eq($names(Dot::sortBy($rows, ['n'])), ['amy', 'bob', 'cat', 'dan', 'eve', 'fay']);
        eq($names(Dot::sortBy($rows, ['-n'])), ['fay', 'eve', 'dan', 'cat', 'bob', 'amy']);
        eq(array_keys(Dot::sortBy(['x' => $rows[1], 'y' => $rows[0]], ['n'])), [0, 1]);
        eq(Dot::sortBy([], ['n']), []);
        eq(Dot::sortBy([['k' => ['z' => 2]], ['k' => ['z' => 1]]], ['k.z']), [['k' => ['z' => 1]], ['k' => ['z' => 2]]]);
        eq(Dot::sortBy([['a.b' => 2], ['a.b' => 1]], ['a\\.b']), [['a.b' => 1], ['a.b' => 2]]);
        raises(fn() => Dot::sortBy($rows, []), InvalidArgumentException::class, 'no keys');
        $stable = [['g' => 1, 'i' => 'a'], ['g' => 0, 'i' => 'b'], ['g' => 1, 'i' => 'c'], ['g' => 0, 'i' => 'd'], ['g' => 1, 'i' => 'e']];
        eq(array_column(Dot::sortBy($stable, ['g']), 'i'), ['b', 'd', 'a', 'c', 'e']);
        eq(array_column(Dot::sortBy($stable, ['-g']), 'i'), ['a', 'c', 'e', 'b', 'd']);
    });

    t_done();
''')

LIB = Lib(
    name="dotpath", lang="php", title="the Dot array helper",
    blurb="The configuration loader of the reporting tool reads and rewrites nested settings arrays with the Dot helper instead of long chains of isset() checks.",
    files={"README.md": README1, "src/Dot.php": F2},
    visible_tests={"tests/run.php": _lang3.php_test(V3)},
    hidden_tests={"tests/run.php": _lang3.php_test(H4)},
    mutate=["src/Dot.php"], difficulty=2, tags=["arrays", "paths", "config"],
)

_lang3.add(LIB, n=8)
