"""Pagination helpers for a legacy web shop (php): page windows with ellipses, offsets, item ranges and summaries; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # Pager

    Pagination helpers for product listings (`src/Pager.php`, class `Pager`, all methods static). Pages and item numbers are **1-based**.
    Methods throw `InvalidArgumentException` for the invalid arguments listed.

    ## `Pager::pageCount(int $items, int $perPage): int`
    Number of pages: `ceil(items / perPage)`. There is always at least one page, even for 0 items (an empty listing is page 1 of 1).
    `$items < 0` or `$perPage < 1` is invalid.

    ## `Pager::clampPage(int $page, int $pages): int`
    `$page` limited to `1..$pages` (a `$pages` below 1 counts as 1).

    ## `Pager::offset(int $page, int $perPage): int`
    How many items to skip to reach `$page`: `(page - 1) * perPage`; a `$page` below 1 is treated as page 1. `$perPage < 1` is invalid.

    ## `Pager::range(int $page, int $perPage, int $items): array`
    `['from' => a, 'to' => b]`: the numbers of the first and last item on the page (inclusive). The page is first clamped with `clampPage` against `pageCount`; for 0 items
    the result is `['from' => 0, 'to' => 0]`. The last page may be short (`to` never exceeds `$items`).

    ## `Pager::summary(int $page, int $perPage, int $items): string`
    `"Showing 21-30 of 95"`, built from `range`; for 0 items `"No results"`; when a page has a single item, `"Showing 95 of 95"` (no range). Uses the clamped page like `range`.

    ## `Pager::prevNext(int $current, int $total): array`
    `['prev' => int|null, 'next' => int|null]` for a page `$current` (clamped to `1..$total`): `prev` is `current - 1`, or `null` on the first page; `next` is `current + 1`, or `null` on the last page.

    ## `Pager::window(int $current, int $total, int $around = 2, int $edges = 1): array`
    The list of page links to show: a list whose items are page numbers (ints) in increasing order and the string `'...'` for a gap.

    * `$current` is clamped into `1..$total`; for `$total < 1` the result is `[]`.
    * Shown pages: the first `$edges` pages, the last `$edges` pages, and the `$around` pages on each side of `$current` together with `$current` itself (all limited to `1..$total`).
    * A run of hidden pages is marked `'...'` **only when it holds at least two pages**; when exactly one page would be hidden, that page is shown instead of the dots. This applies to the runs between shown pages and also to the run before the first shown page and the one after the last (these exist when `$edges` is 0).
    * `$around < 0` or `$edges < 0` is invalid.

    Example: `window(10, 20)` is `[1, '...', 8, 9, 10, 11, 12, '...', 20]`; `window(5, 20, 1, 2)` is `[1, 2, 3, 4, 5, 6, '...', 19, 20]`.
''')

F2 = dd(r'''
    <?php
    declare(strict_types=1);

    class Pager
    {
        public static function pageCount(int $items, int $perPage): int
        {
            if ($items < 0 || $perPage < 1) {
                throw new InvalidArgumentException('bad pagination arguments');
            }
            if ($items === 0) {
                return 1;
            }
            return intdiv($items + $perPage - 1, $perPage);
        }

        public static function clampPage(int $page, int $pages): int
        {
            if ($pages < 1) {
                $pages = 1;
            }
            if ($page < 1) {
                return 1;
            }
            return $page > $pages ? $pages : $page;
        }

        public static function offset(int $page, int $perPage): int
        {
            if ($perPage < 1) {
                throw new InvalidArgumentException('perPage must be at least 1');
            }
            if ($page < 1) {
                $page = 1;
            }
            return ($page - 1) * $perPage;
        }

        public static function range(int $page, int $perPage, int $items): array
        {
            $pages = self::pageCount($items, $perPage);
            if ($items === 0) {
                return ['from' => 0, 'to' => 0];
            }
            $page = self::clampPage($page, $pages);
            $from = self::offset($page, $perPage) + 1;
            $to = min($from + $perPage - 1, $items);
            return ['from' => $from, 'to' => $to];
        }

        public static function summary(int $page, int $perPage, int $items): string
        {
            $r = self::range($page, $perPage, $items);
            if ($items === 0) {
                return 'No results';
            }
            if ($r['from'] === $r['to']) {
                return 'Showing ' . $r['from'] . ' of ' . $items;
            }
            return 'Showing ' . $r['from'] . '-' . $r['to'] . ' of ' . $items;
        }

        public static function prevNext(int $current, int $total): array
        {
            $current = self::clampPage($current, $total);
            return [
                'prev' => $current > 1 ? $current - 1 : null,
                'next' => $current < $total ? $current + 1 : null,
            ];
        }

        public static function window(int $current, int $total, int $around = 2, int $edges = 1): array
        {
            if ($around < 0 || $edges < 0) {
                throw new InvalidArgumentException('around and edges must not be negative');
            }
            if ($total < 1) {
                return [];
            }
            $current = self::clampPage($current, $total);
            $shown = [];
            for ($p = 1; $p <= $total; $p++) {
                if ($p <= $edges || $p > $total - $edges || abs($p - $current) <= $around) {
                    $shown[] = $p;
                }
            }
            $out = [];
            $prev = 0;
            foreach ($shown as $p) {
                $hidden = $p - $prev - 1;
                if ($hidden === 1) {
                    $out[] = $prev + 1;
                } elseif ($hidden >= 2) {
                    $out[] = '...';
                }
                $out[] = $p;
                $prev = $p;
            }
            $hidden = $total - $prev;
            if ($hidden === 1) {
                $out[] = $total;
            } elseif ($hidden >= 2) {
                $out[] = '...';
            }
            return $out;
        }
    }
''')

V3 = dd(r'''
    require __DIR__ . '/../src/Pager.php';

    test('basics', function () {
        eq(Pager::pageCount(95, 10), 10);
        eq(Pager::offset(3, 10), 20);
        eq(Pager::summary(3, 10, 95), 'Showing 21-30 of 95');
        eq(Pager::window(10, 20), [1, '...', 8, 9, 10, 11, 12, '...', 20]);
    });

    t_done();
''')

H4 = dd(r'''
    require __DIR__ . '/../src/Pager.php';

    // reference model of window(), written differently from the implementation
    function ref_window(int $cur, int $total, int $around, int $edges): array
    {
        if ($total < 1) {
            return [];
        }
        $cur = max(1, min($cur, $total));
        $keep = array_fill(1, $total, false);
        for ($p = 1; $p <= $total; $p++) {
            if ($p <= $edges || $p >= $total - $edges + 1 || ($p >= $cur - $around && $p <= $cur + $around)) {
                $keep[$p] = true;
            }
        }
        $out = [];
        $p = 1;
        while ($p <= $total) {
            if ($keep[$p]) {
                $out[] = $p;
                $p++;
                continue;
            }
            $q = $p;
            while ($q <= $total && !$keep[$q]) {
                $q++;
            }
            $len = $q - $p;
            if ($len == 1) {
                $out[] = $p;
            } else {
                $out[] = '...';
            }
            $p = $q;
        }
        return $out;
    }

    test('pageCount', function () {
        $cases = [[0, 10, 1], [1, 10, 1], [9, 10, 1], [10, 10, 1], [11, 10, 2], [95, 10, 10], [100, 10, 10], [101, 10, 11], [5, 1, 5], [1, 1, 1], [0, 1, 1], [7, 3, 3], [6, 3, 2], [1000000, 7, 142858]];
        foreach ($cases as [$items, $per, $want]) {
            eq(Pager::pageCount($items, $per), $want, "pageCount($items, $per)");
        }
        raises(fn() => Pager::pageCount(-1, 10), InvalidArgumentException::class, 'negative items');
        raises(fn() => Pager::pageCount(10, 0), InvalidArgumentException::class, 'perPage 0');
        raises(fn() => Pager::pageCount(10, -5), InvalidArgumentException::class, 'perPage -5');
    });

    test('clampPage', function () {
        $cases = [[1, 5, 1], [3, 5, 3], [5, 5, 5], [6, 5, 5], [99, 5, 5], [0, 5, 1], [-4, 5, 1], [1, 1, 1], [2, 1, 1], [3, 0, 1], [-3, 0, 1], [2, -7, 1], [7, 7, 7], [8, 7, 7]];
        foreach ($cases as [$page, $pages, $want]) {
            eq(Pager::clampPage($page, $pages), $want, "clampPage($page, $pages)");
        }
    });

    test('offset', function () {
        $cases = [[1, 10, 0], [2, 10, 10], [3, 10, 20], [0, 10, 0], [-5, 10, 0], [7, 25, 150], [1, 1, 0], [4, 1, 3], [100, 50, 4950]];
        foreach ($cases as [$page, $per, $want]) {
            eq(Pager::offset($page, $per), $want, "offset($page, $per)");
        }
        raises(fn() => Pager::offset(1, 0), InvalidArgumentException::class, 'perPage 0');
        raises(fn() => Pager::offset(1, -1), InvalidArgumentException::class, 'perPage -1');
    });

    test('range', function () {
        $cases = [
            [1, 10, 95, 1, 10], [2, 10, 95, 11, 20], [9, 10, 95, 81, 90], [10, 10, 95, 91, 95], [11, 10, 95, 91, 95], [99, 10, 95, 91, 95],
            [0, 10, 95, 1, 10], [-3, 10, 95, 1, 10], [1, 10, 10, 1, 10], [2, 10, 10, 1, 10], [1, 10, 3, 1, 3], [1, 10, 1, 1, 1],
            [1, 10, 0, 0, 0], [5, 10, 0, 0, 0], [3, 1, 3, 3, 3], [4, 1, 3, 3, 3], [2, 5, 6, 6, 6], [1, 5, 6, 1, 5], [3, 4, 9, 9, 9], [2, 4, 9, 5, 8],
        ];
        foreach ($cases as [$page, $per, $items, $from, $to]) {
            eq(Pager::range($page, $per, $items), ['from' => $from, 'to' => $to], "range($page, $per, $items)");
        }
        raises(fn() => Pager::range(1, 0, 10), InvalidArgumentException::class, 'perPage 0');
        raises(fn() => Pager::range(1, 10, -1), InvalidArgumentException::class, 'negative items');
    });

    test('summary', function () {
        $cases = [
            [3, 10, 95, 'Showing 21-30 of 95'], [1, 10, 95, 'Showing 1-10 of 95'], [10, 10, 95, 'Showing 91-95 of 95'], [11, 10, 95, 'Showing 91-95 of 95'],
            [1, 10, 0, 'No results'], [4, 10, 0, 'No results'], [1, 10, 1, 'Showing 1 of 1'], [10, 10, 91, 'Showing 91 of 91'], [2, 1, 5, 'Showing 2 of 5'],
            [0, 10, 25, 'Showing 1-10 of 25'], [3, 10, 25, 'Showing 21-25 of 25'], [1, 3, 2, 'Showing 1-2 of 2'], [2, 2, 3, 'Showing 3 of 3'],
        ];
        foreach ($cases as [$page, $per, $items, $want]) {
            eq(Pager::summary($page, $per, $items), $want, "summary($page, $per, $items)");
        }
        raises(fn() => Pager::summary(1, 0, 10), InvalidArgumentException::class, 'perPage 0');
    });

    test('prevNext', function () {
        eq(Pager::prevNext(1, 5), ['prev' => null, 'next' => 2]);
        eq(Pager::prevNext(2, 5), ['prev' => 1, 'next' => 3]);
        eq(Pager::prevNext(4, 5), ['prev' => 3, 'next' => 5]);
        eq(Pager::prevNext(5, 5), ['prev' => 4, 'next' => null]);
        eq(Pager::prevNext(9, 5), ['prev' => 4, 'next' => null]);
        eq(Pager::prevNext(0, 5), ['prev' => null, 'next' => 2]);
        eq(Pager::prevNext(-8, 5), ['prev' => null, 'next' => 2]);
        eq(Pager::prevNext(1, 1), ['prev' => null, 'next' => null]);
        eq(Pager::prevNext(3, 1), ['prev' => null, 'next' => null]);
        eq(Pager::prevNext(1, 0), ['prev' => null, 'next' => null]);
        eq(Pager::prevNext(2, 2), ['prev' => 1, 'next' => null]);
        eq(Pager::prevNext(1, 2), ['prev' => null, 'next' => 2]);
    });

    test('window examples', function () {
        eq(Pager::window(10, 20), [1, '...', 8, 9, 10, 11, 12, '...', 20]);
        eq(Pager::window(5, 20, 1, 2), [1, 2, 3, 4, 5, 6, '...', 19, 20]);
        eq(Pager::window(1, 1), [1]);
        eq(Pager::window(1, 0), []);
        eq(Pager::window(1, -4), []);
        eq(Pager::window(1, 2), [1, 2]);
        eq(Pager::window(1, 20), [1, 2, 3, '...', 20]);
        eq(Pager::window(20, 20), [1, '...', 18, 19, 20]);
        eq(Pager::window(4, 20), [1, 2, 3, 4, 5, 6, '...', 20]);
        eq(Pager::window(5, 20), [1, 2, 3, 4, 5, 6, 7, '...', 20]);
        eq(Pager::window(6, 20), [1, '...', 4, 5, 6, 7, 8, '...', 20]);
        eq(Pager::window(7, 20), [1, '...', 5, 6, 7, 8, 9, '...', 20]);
        eq(Pager::window(16, 20), [1, '...', 14, 15, 16, 17, 18, 19, 20]);
        eq(Pager::window(15, 20), [1, '...', 13, 14, 15, 16, 17, '...', 20]);
        eq(Pager::window(0, 20), [1, 2, 3, '...', 20]);
        eq(Pager::window(99, 20), [1, '...', 18, 19, 20]);
        eq(Pager::window(-3, 20), [1, 2, 3, '...', 20]);
        eq(Pager::window(3, 7, 0, 0), ['...', 3, '...']);
        eq(Pager::window(1, 7, 0, 0), [1, '...']);
        eq(Pager::window(7, 7, 0, 0), ['...', 7]);
        eq(Pager::window(2, 3, 0, 0), [1, 2, 3]);
        eq(Pager::window(2, 4, 0, 0), [1, 2, '...']);
        eq(Pager::window(3, 4, 0, 0), ['...', 3, 4]);
        eq(Pager::window(4, 9, 0, 1), [1, '...', 4, '...', 9]);
        eq(Pager::window(3, 9, 0, 1), [1, 2, 3, '...', 9]);
        eq(Pager::window(2, 9, 0, 1), [1, 2, '...', 9]);
        eq(Pager::window(5, 9, 0, 1), [1, '...', 5, '...', 9]);
        eq(Pager::window(5, 11, 1, 3), [1, 2, 3, 4, 5, 6, '...', 9, 10, 11]);
        eq(Pager::window(6, 11, 1, 3), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]);
        eq(Pager::window(6, 12, 1, 3), [1, 2, 3, 4, 5, 6, 7, '...', 10, 11, 12]);
        eq(Pager::window(2, 3, 5, 5), [1, 2, 3]);
        eq(Pager::window(50, 100, 3, 0), ['...', 47, 48, 49, 50, 51, 52, 53, '...']);
        eq(Pager::window(1, 100, 3, 0), [1, 2, 3, 4, '...']);
        eq(Pager::window(100, 100, 3, 0), ['...', 97, 98, 99, 100]);
        eq(Pager::window(3, 100, 0, 2), [1, 2, 3, '...', 99, 100]);
    });

    test('window gap of exactly one page', function () {
        // one hidden page is shown instead of '...'
        eq(Pager::window(5, 9, 0, 3), [1, 2, 3, 4, 5, 6, 7, 8, 9]);
        eq(Pager::window(6, 10, 1, 1), [1, '...', 5, 6, 7, '...', 10]);
        eq(Pager::window(5, 10, 1, 1), [1, '...', 4, 5, 6, '...', 10]);
        eq(Pager::window(4, 10, 1, 1), [1, 2, 3, 4, 5, '...', 10]);
        eq(Pager::window(3, 10, 0, 1), [1, 2, 3, '...', 10]);
        eq(Pager::window(4, 10, 0, 1), [1, '...', 4, '...', 10]);
        eq(Pager::window(8, 10, 0, 1), [1, '...', 8, 9, 10]);
        eq(Pager::window(7, 10, 0, 1), [1, '...', 7, '...', 10]);
    });

    test('window agrees with the reference model', function () {
        for ($total = 0; $total <= 14; $total++) {
            for ($cur = -1; $cur <= $total + 2; $cur++) {
                for ($around = 0; $around <= 3; $around++) {
                    for ($edges = 0; $edges <= 3; $edges++) {
                        eq(Pager::window($cur, $total, $around, $edges), ref_window($cur, $total, $around, $edges), "window($cur, $total, $around, $edges)");
                    }
                }
            }
        }
        eq(Pager::window(500, 1000, 2, 1), ref_window(500, 1000, 2, 1));
        eq(Pager::window(1, 1000, 4, 2), ref_window(1, 1000, 4, 2));
    });

    test('window argument checks', function () {
        raises(fn() => Pager::window(1, 10, -1, 1), InvalidArgumentException::class, 'negative around');
        raises(fn() => Pager::window(1, 10, 1, -1), InvalidArgumentException::class, 'negative edges');
        raises(fn() => Pager::window(1, 0, -1, 1), InvalidArgumentException::class, 'negative around, empty total');
        raises(fn() => Pager::window(1, 0, 1, -1), InvalidArgumentException::class, 'negative edges, empty total');
    });

    t_done();
''')

LIB = Lib(
    name="pagelinks", lang="php", title="the Pager pagination helper",
    blurb="The shop's product listings use the Pager helper to work out which page links to show and which items belong on a page.",
    files={"README.md": README1, "src/Pager.php": F2},
    visible_tests={"tests/run.php": _lang3.php_test(V3)},
    hidden_tests={"tests/run.php": _lang3.php_test(H4)},
    mutate=["src/Pager.php"], difficulty=1, tags=["pagination", "ui", "arithmetic"],
)

_lang3.add(LIB, n=8)
