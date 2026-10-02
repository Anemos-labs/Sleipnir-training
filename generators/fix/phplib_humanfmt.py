"""Human-friendly formatting helpers (php): byte sizes in binary or decimal units, durations, ordinals, plurals, relative times and middle truncation; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # Human

    Human-friendly formatting for an admin dashboard (`src/Human.php`, class `Human`, static methods). `InvalidArgumentException` is thrown for the invalid arguments listed.

    ## `Human::size(int $bytes, bool $binary = true, int $decimals = 1): string`
    A byte count with a unit. Binary units (`B`, `KiB`, `MiB`, `GiB`, `TiB`, `PiB`) go up in steps of 1024, decimal units (`B`, `kB`, `MB`, `GB`, `TB`, `PB`) in steps of 1000.

    * The unit is the largest one for which the count is at least one whole unit (`1023` is `1023 B`, `1024` is `1.0 KiB`).
    * The number is `bytes / unit` rounded to `$decimals` places (`0..3`), halves up, with exactly that many decimals (`1.5 KiB`, `2.00 MiB` for 2 decimals). The `B` unit has no decimals: `512 B`. With `$decimals` 0 there is no point: `3 MiB`.
    * When rounding brings the number up to the step (1024 or 1000) and a larger unit exists, that larger unit is used instead, and the number is worked out again for it (`1048575` is `1.0 MiB`, not `1024.0 KiB`).
    * Beyond the largest unit the number simply grows (`PiB`).
    * Negative sizes and `$decimals` outside `0..3` are invalid. Exact integer arithmetic is expected (a float rounding error must not change a digit).

    ## `Human::duration(int $seconds, int $maxParts = 2): string`
    `'1d 2h'`, `'3m 5s'`, `'45s'`: the units `d` (86400 s), `h`, `m`, `s`, largest first; units that are zero are left out and at most `$maxParts` parts are shown (the largest non-zero ones). `0` seconds is `'0s'`. A negative
    duration is written like the positive one with a `-` in front. `$maxParts < 1` is invalid.

    ## `Human::ordinal(int $n): string`
    `1st 2nd 3rd 4th ... 11th 12th 13th ... 21st 22nd 23rd ... 101st 111th 112th`. Zero is `0th`; negative numbers get a `-` and use their absolute value for the suffix (`-1st`, `-12th`).

    ## `Human::plural(int $n, string $one, ?string $many = null): string`
    `"1 item"`, `"2 items"`: the number, a space, and `$one` when `$n` is exactly 1 or -1, else `$many` (default: `$one` followed by `s`). `0` takes the plural form.

    ## `Human::ago(int $seconds): string`
    How long ago something happened, `$seconds` being the age. The first row that matches wins (`s` is the absolute value of `$seconds`):

    | `s` | text |
    |---|---|
    | below 10 | `just now` |
    | below 60 | `N seconds ago` (`N = s`) |
    | below 3600 | `N minute(s) ago`, `N = floor(s / 60)` |
    | below 86400 | `N hour(s) ago`, `N = floor(s / 3600)` |
    | below 172800 | `yesterday` |
    | below 604800 (7 days) | `N days ago`, `N = floor(s / 86400)` |
    | below 2592000 (30 days) | `N week(s) ago`, `N = floor(s / 604800)` |
    | below 31536000 (365 days) | `N month(s) ago`, `N = floor(s / 2592000)` |
    | otherwise | `N year(s) ago`, `N = floor(s / 31536000)` |

    "1 minute", "1 hour", "1 week", "1 month", "1 year" are singular, the rest plural. A negative `$seconds` is the future: the text is `in N minutes` instead of `N minutes ago`, `tomorrow` instead of `yesterday`, and `just now` stays `just now`.

    ## `Human::truncateMiddle(string $s, int $max, string $ellipsis = '...'): string`
    `$s` itself when `strlen($s) <= $max`. Otherwise the start and the end of the string with the ellipsis in the middle, `$max` bytes in total: with `keep = $max - strlen($ellipsis)`, the first `ceil(keep / 2)` bytes, the ellipsis, and the last `floor(keep / 2)` bytes.
    `$max` smaller than `strlen($ellipsis) + 2` is invalid (even if the string is short).
''')

F2 = dd(r'''
    <?php
    declare(strict_types=1);

    class Human
    {
        private const BINARY = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
        private const DECIMAL = ['B', 'kB', 'MB', 'GB', 'TB', 'PB'];

        public static function size(int $bytes, bool $binary = true, int $decimals = 1): string
        {
            if ($bytes < 0 || $decimals < 0 || $decimals > 3) {
                throw new InvalidArgumentException('bad size arguments');
            }
            $units = $binary ? self::BINARY : self::DECIMAL;
            $base = $binary ? 1024 : 1000;
            $last = count($units) - 1;
            $k = 0;
            $unit = 1;
            while ($k < $last && $bytes >= $unit * $base) {
                $unit *= $base;
                $k++;
            }
            if ($k === 0) {
                return $bytes . ' B';
            }
            while (true) {
                $scale = 10 ** $decimals;
                $whole = intdiv($bytes, $unit);
                $rem = $bytes % $unit;
                $frac = intdiv($rem * $scale * 2 + $unit, 2 * $unit);
                if ($frac >= $scale) {
                    $whole++;
                    $frac -= $scale;
                }
                if ($whole >= $base && $k < $last) {
                    $unit *= $base;
                    $k++;
                    continue;
                }
                break;
            }
            $text = (string)$whole;
            if ($decimals > 0) {
                $text .= '.' . str_pad((string)$frac, $decimals, '0', STR_PAD_LEFT);
            }
            return $text . ' ' . $units[$k];
        }

        public static function duration(int $seconds, int $maxParts = 2): string
        {
            if ($maxParts < 1) {
                throw new InvalidArgumentException('maxParts must be at least 1');
            }
            $sign = $seconds < 0 ? '-' : '';
            $rest = abs($seconds);
            $parts = [];
            foreach ([['d', 86400], ['h', 3600], ['m', 60], ['s', 1]] as [$name, $size]) {
                $n = intdiv($rest, $size);
                $rest -= $n * $size;
                if ($n > 0 && count($parts) < $maxParts) {
                    $parts[] = $n . $name;
                }
            }
            if (count($parts) === 0) {
                return '0s';
            }
            return $sign . implode(' ', $parts);
        }

        public static function ordinal(int $n): string
        {
            $a = abs($n);
            $mod100 = $a % 100;
            if ($mod100 >= 11 && $mod100 <= 13) {
                $suffix = 'th';
            } else {
                switch ($a % 10) {
                    case 1:
                        $suffix = 'st';
                        break;
                    case 2:
                        $suffix = 'nd';
                        break;
                    case 3:
                        $suffix = 'rd';
                        break;
                    default:
                        $suffix = 'th';
                }
            }
            return $n . $suffix;
        }

        public static function plural(int $n, string $one, ?string $many = null): string
        {
            $word = abs($n) === 1 ? $one : ($many ?? $one . 's');
            return $n . ' ' . $word;
        }

        public static function ago(int $seconds): string
        {
            $s = abs($seconds);
            $future = $seconds < 0;
            if ($s < 10) {
                return 'just now';
            }
            if ($s < 60) {
                $text = $s . ' seconds';
            } elseif ($s < 3600) {
                $text = self::plural(intdiv($s, 60), 'minute');
            } elseif ($s < 86400) {
                $text = self::plural(intdiv($s, 3600), 'hour');
            } elseif ($s < 172800) {
                return $future ? 'tomorrow' : 'yesterday';
            } elseif ($s < 604800) {
                $text = intdiv($s, 86400) . ' days';
            } elseif ($s < 2592000) {
                $text = self::plural(intdiv($s, 604800), 'week');
            } elseif ($s < 31536000) {
                $text = self::plural(intdiv($s, 2592000), 'month');
            } else {
                $text = self::plural(intdiv($s, 31536000), 'year');
            }
            return $future ? 'in ' . $text : $text . ' ago';
        }

        public static function truncateMiddle(string $s, int $max, string $ellipsis = '...'): string
        {
            if ($max < strlen($ellipsis) + 2) {
                throw new InvalidArgumentException('max is too small for the ellipsis');
            }
            if (strlen($s) <= $max) {
                return $s;
            }
            $keep = $max - strlen($ellipsis);
            $head = intdiv($keep + 1, 2);
            $tail = intdiv($keep, 2);
            return substr($s, 0, $head) . $ellipsis . ($tail > 0 ? substr($s, -$tail) : '');
        }
    }
''')

V3 = dd(r'''
    require __DIR__ . '/../src/Human.php';

    test('basics', function () {
        eq(Human::size(1536), '1.5 KiB');
        eq(Human::duration(93784), '1d 2h');
        eq(Human::ordinal(22), '22nd');
        eq(Human::plural(2, 'file'), '2 files');
        eq(Human::ago(300), '5 minutes ago');
    });

    t_done();
''')

H4 = dd(r'''
    require __DIR__ . '/../src/Human.php';

    function try_call(callable $f)
    {
        try {
            return $f();
        } catch (InvalidArgumentException $e) {
            return null;
        }
    }

    $SIZE = [
        [0, true, 0, '0 B'],
        [0, true, 1, '0 B'],
        [0, true, 2, '0 B'],
        [0, true, 3, '0 B'],
        [0, false, 0, '0 B'],
        [0, false, 1, '0 B'],
        [0, false, 2, '0 B'],
        [0, false, 3, '0 B'],
        [1, true, 0, '1 B'],
        [1, true, 1, '1 B'],
        [1, true, 2, '1 B'],
        [1, true, 3, '1 B'],
        [1, true, -1, null],
        [1, true, 4, null],
        [1, false, 0, '1 B'],
        [1, false, 1, '1 B'],
        [1, false, 2, '1 B'],
        [1, false, 3, '1 B'],
        [1, false, -1, null],
        [1, false, 4, null],
        [512, true, 0, '512 B'],
        [512, true, 1, '512 B'],
        [512, true, 2, '512 B'],
        [512, true, 3, '512 B'],
        [512, false, 0, '512 B'],
        [512, false, 1, '512 B'],
        [512, false, 2, '512 B'],
        [512, false, 3, '512 B'],
        [1023, true, 0, '1023 B'],
        [1023, true, 1, '1023 B'],
        [1023, true, 2, '1023 B'],
        [1023, true, 3, '1023 B'],
        [1023, false, 0, '1 kB'],
        [1023, false, 1, '1.0 kB'],
        [1023, false, 2, '1.02 kB'],
        [1023, false, 3, '1.023 kB'],
        [1024, true, 0, '1 KiB'],
        [1024, true, 1, '1.0 KiB'],
        [1024, true, 2, '1.00 KiB'],
        [1024, true, 3, '1.000 KiB'],
        [1024, true, -1, null],
        [1024, true, 4, null],
        [1024, false, 0, '1 kB'],
        [1024, false, 1, '1.0 kB'],
        [1024, false, 2, '1.02 kB'],
        [1024, false, 3, '1.024 kB'],
        [1024, false, -1, null],
        [1024, false, 4, null],
        [1025, true, 0, '1 KiB'],
        [1025, true, 1, '1.0 KiB'],
        [1025, true, 2, '1.00 KiB'],
        [1025, true, 3, '1.001 KiB'],
        [1025, false, 0, '1 kB'],
        [1025, false, 1, '1.0 kB'],
        [1025, false, 2, '1.03 kB'],
        [1025, false, 3, '1.025 kB'],
        [1536, true, 0, '2 KiB'],
        [1536, true, 1, '1.5 KiB'],
        [1536, true, 2, '1.50 KiB'],
        [1536, true, 3, '1.500 KiB'],
        [1536, false, 0, '2 kB'],
        [1536, false, 1, '1.5 kB'],
        [1536, false, 2, '1.54 kB'],
        [1536, false, 3, '1.536 kB'],
        [1048575, true, 0, '1 MiB'],
        [1048575, true, 1, '1.0 MiB'],
        [1048575, true, 2, '1.00 MiB'],
        [1048575, true, 3, '1023.999 KiB'],
        [1048575, false, 0, '1 MB'],
        [1048575, false, 1, '1.0 MB'],
        [1048575, false, 2, '1.05 MB'],
        [1048575, false, 3, '1.049 MB'],
        [1048576, true, 0, '1 MiB'],
        [1048576, true, 1, '1.0 MiB'],
        [1048576, true, 2, '1.00 MiB'],
        [1048576, true, 3, '1.000 MiB'],
        [1048576, false, 0, '1 MB'],
        [1048576, false, 1, '1.0 MB'],
        [1048576, false, 2, '1.05 MB'],
        [1048576, false, 3, '1.049 MB'],
        [1049000, true, 0, '1 MiB'],
        [1049000, true, 1, '1.0 MiB'],
        [1049000, true, 2, '1.00 MiB'],
        [1049000, true, 3, '1.000 MiB'],
        [1049000, false, 0, '1 MB'],
        [1049000, false, 1, '1.0 MB'],
        [1049000, false, 2, '1.05 MB'],
        [1049000, false, 3, '1.049 MB'],
        [1073741823, true, 0, '1 GiB'],
        [1073741823, true, 1, '1.0 GiB'],
        [1073741823, true, 2, '1.00 GiB'],
        [1073741823, true, 3, '1.000 GiB'],
        [1073741823, false, 0, '1 GB'],
        [1073741823, false, 1, '1.1 GB'],
        [1073741823, false, 2, '1.07 GB'],
        [1073741823, false, 3, '1.074 GB'],
        [1073741824, true, 0, '1 GiB'],
        [1073741824, true, 1, '1.0 GiB'],
        [1073741824, true, 2, '1.00 GiB'],
        [1073741824, true, 3, '1.000 GiB'],
        [1073741824, false, 0, '1 GB'],
        [1073741824, false, 1, '1.1 GB'],
        [1073741824, false, 2, '1.07 GB'],
        [1073741824, false, 3, '1.074 GB'],
        [1000, true, 0, '1000 B'],
        [1000, true, 1, '1000 B'],
        [1000, true, 2, '1000 B'],
        [1000, true, 3, '1000 B'],
        [1000, false, 0, '1 kB'],
        [1000, false, 1, '1.0 kB'],
        [1000, false, 2, '1.00 kB'],
        [1000, false, 3, '1.000 kB'],
        [999, true, 0, '999 B'],
        [999, true, 1, '999 B'],
        [999, true, 2, '999 B'],
        [999, true, 3, '999 B'],
        [999, false, 0, '999 B'],
        [999, false, 1, '999 B'],
        [999, false, 2, '999 B'],
        [999, false, 3, '999 B'],
        [999999, true, 0, '977 KiB'],
        [999999, true, 1, '976.6 KiB'],
        [999999, true, 2, '976.56 KiB'],
        [999999, true, 3, '976.562 KiB'],
        [999999, false, 0, '1 MB'],
        [999999, false, 1, '1.0 MB'],
        [999999, false, 2, '1.00 MB'],
        [999999, false, 3, '999.999 kB'],
        [1000000, true, 0, '977 KiB'],
        [1000000, true, 1, '976.6 KiB'],
        [1000000, true, 2, '976.56 KiB'],
        [1000000, true, 3, '976.563 KiB'],
        [1000000, false, 0, '1 MB'],
        [1000000, false, 1, '1.0 MB'],
        [1000000, false, 2, '1.00 MB'],
        [1000000, false, 3, '1.000 MB'],
        [1500000, true, 0, '1 MiB'],
        [1500000, true, 1, '1.4 MiB'],
        [1500000, true, 2, '1.43 MiB'],
        [1500000, true, 3, '1.431 MiB'],
        [1500000, false, 0, '2 MB'],
        [1500000, false, 1, '1.5 MB'],
        [1500000, false, 2, '1.50 MB'],
        [1500000, false, 3, '1.500 MB'],
        [999950, true, 0, '977 KiB'],
        [999950, true, 1, '976.5 KiB'],
        [999950, true, 2, '976.51 KiB'],
        [999950, true, 3, '976.514 KiB'],
        [999950, false, 0, '1 MB'],
        [999950, false, 1, '1.0 MB'],
        [999950, false, 2, '999.95 kB'],
        [999950, false, 3, '999.950 kB'],
        [999949, true, 0, '977 KiB'],
        [999949, true, 1, '976.5 KiB'],
        [999949, true, 2, '976.51 KiB'],
        [999949, true, 3, '976.513 KiB'],
        [999949, false, 0, '1 MB'],
        [999949, false, 1, '999.9 kB'],
        [999949, false, 2, '999.95 kB'],
        [999949, false, 3, '999.949 kB'],
        [1023999, true, 0, '1000 KiB'],
        [1023999, true, 1, '1000.0 KiB'],
        [1023999, true, 2, '1000.00 KiB'],
        [1023999, true, 3, '999.999 KiB'],
        [1023999, false, 0, '1 MB'],
        [1023999, false, 1, '1.0 MB'],
        [1023999, false, 2, '1.02 MB'],
        [1023999, false, 3, '1.024 MB'],
        [1048064, true, 0, '1 MiB'],
        [1048064, true, 1, '1023.5 KiB'],
        [1048064, true, 2, '1023.50 KiB'],
        [1048064, true, 3, '1023.500 KiB'],
        [1048064, false, 0, '1 MB'],
        [1048064, false, 1, '1.0 MB'],
        [1048064, false, 2, '1.05 MB'],
        [1048064, false, 3, '1.048 MB'],
        [1048063, true, 0, '1023 KiB'],
        [1048063, true, 1, '1023.5 KiB'],
        [1048063, true, 2, '1023.50 KiB'],
        [1048063, true, 3, '1023.499 KiB'],
        [1048063, false, 0, '1 MB'],
        [1048063, false, 1, '1.0 MB'],
        [1048063, false, 2, '1.05 MB'],
        [1048063, false, 3, '1.048 MB'],
        [1048575, true, 0, '1 MiB'],
        [1048575, true, 1, '1.0 MiB'],
        [1048575, true, 2, '1.00 MiB'],
        [1048575, true, 3, '1023.999 KiB'],
        [1048575, false, 0, '1 MB'],
        [1048575, false, 1, '1.0 MB'],
        [1048575, false, 2, '1.05 MB'],
        [1048575, false, 3, '1.049 MB'],
        [1000000000000, true, 0, '931 GiB'],
        [1000000000000, true, 1, '931.3 GiB'],
        [1000000000000, true, 2, '931.32 GiB'],
        [1000000000000, true, 3, '931.323 GiB'],
        [1000000000000, false, 0, '1 TB'],
        [1000000000000, false, 1, '1.0 TB'],
        [1000000000000, false, 2, '1.00 TB'],
        [1000000000000, false, 3, '1.000 TB'],
        [1000000000000000, true, 0, '909 TiB'],
        [1000000000000000, true, 1, '909.5 TiB'],
        [1000000000000000, true, 2, '909.49 TiB'],
        [1000000000000000, true, 3, '909.495 TiB'],
        [1000000000000000, false, 0, '1 PB'],
        [1000000000000000, false, 1, '1.0 PB'],
        [1000000000000000, false, 2, '1.00 PB'],
        [1000000000000000, false, 3, '1.000 PB'],
        [5000000000000000, true, 0, '4 PiB'],
        [5000000000000000, true, 1, '4.4 PiB'],
        [5000000000000000, true, 2, '4.44 PiB'],
        [5000000000000000, true, 3, '4.441 PiB'],
        [5000000000000000, false, 0, '5 PB'],
        [5000000000000000, false, 1, '5.0 PB'],
        [5000000000000000, false, 2, '5.00 PB'],
        [5000000000000000, false, 3, '5.000 PB'],
        [1125899906842624, true, 0, '1 PiB'],
        [1125899906842624, true, 1, '1.0 PiB'],
        [1125899906842624, true, 2, '1.00 PiB'],
        [1125899906842624, true, 3, '1.000 PiB'],
        [1125899906842624, false, 0, '1 PB'],
        [1125899906842624, false, 1, '1.1 PB'],
        [1125899906842624, false, 2, '1.13 PB'],
        [1125899906842624, false, 3, '1.126 PB'],
        [1125899906842623, true, 0, '1 PiB'],
        [1125899906842623, true, 1, '1.0 PiB'],
        [1125899906842623, true, 2, '1.00 PiB'],
        [1125899906842623, true, 3, '1.000 PiB'],
        [1125899906842623, false, 0, '1 PB'],
        [1125899906842623, false, 1, '1.1 PB'],
        [1125899906842623, false, 2, '1.13 PB'],
        [1125899906842623, false, 3, '1.126 PB'],
        [1152921504606846976, true, 0, '1024 PiB'],
        [1152921504606846976, true, 1, '1024.0 PiB'],
        [1152921504606846976, true, 2, '1024.00 PiB'],
        [1152921504606846976, true, 3, '1024.000 PiB'],
        [1152921504606846976, false, 0, '1153 PB'],
        [1152921504606846976, false, 1, '1152.9 PB'],
        [1152921504606846976, false, 2, '1152.92 PB'],
        [1152921504606846976, false, 3, '1152.922 PB'],
        [4611686018427387904, true, 0, '4096 PiB'],
        [4611686018427387904, true, 1, '4096.0 PiB'],
        [4611686018427387904, true, 2, '4096.00 PiB'],
        [4611686018427387904, true, 3, '4096.000 PiB'],
        [4611686018427387904, false, 0, '4612 PB'],
        [4611686018427387904, false, 1, '4611.7 PB'],
        [4611686018427387904, false, 2, '4611.69 PB'],
        [4611686018427387904, false, 3, '4611.686 PB'],
        [9007199254740993, true, 0, '8 PiB'],
        [9007199254740993, true, 1, '8.0 PiB'],
        [9007199254740993, true, 2, '8.00 PiB'],
        [9007199254740993, true, 3, '8.000 PiB'],
        [9007199254740993, false, 0, '9 PB'],
        [9007199254740993, false, 1, '9.0 PB'],
        [9007199254740993, false, 2, '9.01 PB'],
        [9007199254740993, false, 3, '9.007 PB'],
        [1125899906842624, true, 0, '1 PiB'],
        [1125899906842624, true, 1, '1.0 PiB'],
        [1125899906842624, true, 2, '1.00 PiB'],
        [1125899906842624, true, 3, '1.000 PiB'],
        [1125899906842624, false, 0, '1 PB'],
        [1125899906842624, false, 1, '1.1 PB'],
        [1125899906842624, false, 2, '1.13 PB'],
        [1125899906842624, false, 3, '1.126 PB'],
        [1152921504606846976, true, 0, '1024 PiB'],
        [1152921504606846976, true, 1, '1024.0 PiB'],
        [1152921504606846976, true, 2, '1024.00 PiB'],
        [1152921504606846976, true, 3, '1024.000 PiB'],
        [1152921504606846976, false, 0, '1153 PB'],
        [1152921504606846976, false, 1, '1152.9 PB'],
        [1152921504606846976, false, 2, '1152.92 PB'],
        [1152921504606846976, false, 3, '1152.922 PB'],
        [3221225473, true, 0, '3 GiB'],
        [3221225473, true, 1, '3.0 GiB'],
        [3221225473, true, 2, '3.00 GiB'],
        [3221225473, true, 3, '3.000 GiB'],
        [3221225473, false, 0, '3 GB'],
        [3221225473, false, 1, '3.2 GB'],
        [3221225473, false, 2, '3.22 GB'],
        [3221225473, false, 3, '3.221 GB'],
        [1048575, true, 0, '1 MiB'],
        [1048575, true, 1, '1.0 MiB'],
        [1048575, true, 2, '1.00 MiB'],
        [1048575, true, 3, '1023.999 KiB'],
        [1048575, false, 0, '1 MB'],
        [1048575, false, 1, '1.0 MB'],
        [1048575, false, 2, '1.05 MB'],
        [1048575, false, 3, '1.049 MB'],
        [1073741823, true, 0, '1 GiB'],
        [1073741823, true, 1, '1.0 GiB'],
        [1073741823, true, 2, '1.00 GiB'],
        [1073741823, true, 3, '1.000 GiB'],
        [1073741823, false, 0, '1 GB'],
        [1073741823, false, 1, '1.1 GB'],
        [1073741823, false, 2, '1.07 GB'],
        [1073741823, false, 3, '1.074 GB'],
        [-1, true, 0, null],
        [-1, true, 1, null],
        [-1, true, 2, null],
        [-1, true, 3, null],
        [-1, true, -1, null],
        [-1, true, 4, null],
        [-1, false, 0, null],
        [-1, false, 1, null],
        [-1, false, 2, null],
        [-1, false, 3, null],
        [-1, false, -1, null],
        [-1, false, 4, null],
        [-1024, true, 0, null],
        [-1024, true, 1, null],
        [-1024, true, 2, null],
        [-1024, true, 3, null],
        [-1024, false, 0, null],
        [-1024, false, 1, null],
        [-1024, false, 2, null],
        [-1024, false, 3, null],
        [592, true, 3, '592 B'],
        [580793999141620, true, 3, '528.229 TiB'],
        [550784, false, 3, '550.784 kB'],
        [856452879959, true, 1, '797.6 GiB'],
        [634, true, 0, '634 B'],
        [777234681427713, false, 0, '777 TB'],
        [1170114, true, 3, '1.116 MiB'],
        [806944656530118, true, 3, '733.912 TiB'],
        [878, true, 3, '878 B'],
        [264, false, 2, '264 B'],
        [519366091, false, 3, '519.366 MB'],
        [348579714866, false, 0, '349 GB'],
        [990989, false, 2, '990.99 kB'],
        [904605514913, true, 1, '842.5 GiB'],
        [831524769480326, true, 0, '756 TiB'],
        [4, true, 0, '4 B'],
        [897096158, true, 3, '855.538 MiB'],
        [0, false, 3, '0 B'],
        [586316459906258, false, 2, '586.32 TB'],
        [235951557744, true, 0, '220 GiB'],
        [5, false, 3, '5 B'],
        [610467, false, 2, '610.47 kB'],
        [360196, false, 3, '360.196 kB'],
        [460363591, true, 0, '439 MiB'],
        [972786054919, true, 1, '906.0 GiB'],
        [656168, false, 2, '656.17 kB'],
        [7, true, 3, '7 B'],
        [589203146339, true, 2, '548.74 GiB'],
        [529373787, false, 2, '529.37 MB'],
        [489453919424714, true, 0, '445 TiB'],
        [257124, true, 2, '251.10 KiB'],
        [545, false, 2, '545 B'],
        [787301, false, 0, '787 kB'],
        [683732850366, true, 1, '636.8 GiB'],
        [803807670394913, true, 3, '731.059 TiB'],
        [698066406674849, false, 2, '698.07 TB'],
        [853460471065528, false, 1, '853.5 TB'],
        [3, false, 3, '3 B'],
        [225027, true, 1, '219.8 KiB'],
        [806696, true, 2, '787.79 KiB'],
        [807226, false, 2, '807.23 kB'],
        [194533706694, false, 2, '194.53 GB'],
        [354632147, true, 3, '338.204 MiB'],
        [9, true, 3, '9 B'],
        [1010500891383, false, 1, '1.0 TB'],
        [7, false, 2, '7 B'],
        [861, false, 0, '861 B'],
        [45, false, 3, '45 B'],
        [50536484397, false, 1, '50.5 GB'],
        [299888068728, false, 3, '299.888 GB'],
        [9, true, 1, '9 B'],
        [971893, true, 0, '949 KiB'],
        [220803, false, 0, '221 kB'],
        [359, false, 1, '359 B'],
        [4, false, 0, '4 B'],
        [248233, false, 3, '248.233 kB'],
        [4, false, 1, '4 B'],
        [1, true, 0, '1 B'],
        [86119394934572, true, 1, '78.3 TiB'],
        [73490, false, 2, '73.49 kB'],
        [397395, true, 1, '388.1 KiB'],
        [3572303665, false, 1, '3.6 GB'],
        [3, false, 3, '3 B'],
        [801080793468169, false, 0, '801 TB'],
        [941166, true, 3, '919.107 KiB'],
        [17925152, false, 0, '18 MB'],
        [224440957, false, 2, '224.44 MB'],
        [968714, false, 2, '968.71 kB'],
        [4, false, 3, '4 B'],
        [162944161151370, false, 0, '163 TB'],
        [733708317727, true, 3, '683.319 GiB'],
        [5, true, 3, '5 B'],
        [1229, false, 0, '1 kB'],
        [8, false, 2, '8 B'],
        [299382111420, true, 1, '278.8 GiB'],
        [5, false, 0, '5 B'],
        [324214442831, true, 0, '302 GiB'],
        [998, true, 3, '998 B'],
        [376253, false, 3, '376.253 kB'],
        [3, false, 3, '3 B'],
        [990204729478503, false, 3, '990.205 TB'],
        [642, true, 3, '642 B'],
        [483452882415970, false, 1, '483.5 TB'],
        [267, true, 2, '267 B'],
        [851, false, 2, '851 B'],
        [722190757070747, false, 2, '722.19 TB'],
        [460, true, 3, '460 B'],
        [258, true, 3, '258 B'],
        [428, false, 1, '428 B'],
        [580458970, true, 0, '554 MiB'],
        [783115109, true, 1, '746.8 MiB'],
        [648, false, 2, '648 B'],
        [1335, true, 0, '1 KiB'],
        [169709, true, 3, '165.731 KiB'],
        [7, true, 2, '7 B'],
        [36988, false, 2, '36.99 kB'],
        [0, true, 3, '0 B'],
        [2, false, 3, '2 B'],
        [188138103, true, 2, '179.42 MiB'],
        [6, true, 2, '6 B'],
        [7, false, 2, '7 B'],
        [443301040, true, 2, '422.76 MiB'],
        [565990732441944, true, 3, '514.766 TiB'],
        [528236658046, false, 1, '528.2 GB'],
        [645667804257567, true, 3, '587.231 TiB'],
        [1, true, 2, '1 B'],
        [720405322060166, true, 2, '655.20 TiB'],
        [191369916408829, true, 1, '174.0 TiB'],
        [68596274461008, false, 3, '68.596 TB'],
        [149781, true, 1, '146.3 KiB'],
        [7, true, 2, '7 B'],
        [967629, false, 0, '968 kB'],
        [498005, true, 0, '486 KiB'],
        [112684775623369, true, 1, '102.5 TiB'],
        [426613399393, false, 1, '426.6 GB'],
        [622422724590, false, 1, '622.4 GB'],
        [268333299481, true, 2, '249.90 GiB'],
        [8, false, 3, '8 B'],
        [552551, true, 3, '539.601 KiB'],
        [1029945202621, false, 3, '1.030 TB'],
    ];
    $DUR = [
        [0, 1, '0s'],
        [0, 2, '0s'],
        [0, 3, '0s'],
        [0, 4, '0s'],
        [0, 5, '0s'],
        [0, 0, null],
        [0, -1, null],
        [1, 1, '1s'],
        [1, 2, '1s'],
        [1, 3, '1s'],
        [1, 4, '1s'],
        [1, 5, '1s'],
        [1, 0, null],
        [1, -1, null],
        [59, 1, '59s'],
        [59, 2, '59s'],
        [59, 3, '59s'],
        [59, 4, '59s'],
        [59, 5, '59s'],
        [60, 1, '1m'],
        [60, 2, '1m'],
        [60, 3, '1m'],
        [60, 4, '1m'],
        [60, 5, '1m'],
        [60, 0, null],
        [60, -1, null],
        [61, 1, '1m'],
        [61, 2, '1m 1s'],
        [61, 3, '1m 1s'],
        [61, 4, '1m 1s'],
        [61, 5, '1m 1s'],
        [3599, 1, '59m'],
        [3599, 2, '59m 59s'],
        [3599, 3, '59m 59s'],
        [3599, 4, '59m 59s'],
        [3599, 5, '59m 59s'],
        [3600, 1, '1h'],
        [3600, 2, '1h'],
        [3600, 3, '1h'],
        [3600, 4, '1h'],
        [3600, 5, '1h'],
        [3601, 1, '1h'],
        [3601, 2, '1h 1s'],
        [3601, 3, '1h 1s'],
        [3601, 4, '1h 1s'],
        [3601, 5, '1h 1s'],
        [86399, 1, '23h'],
        [86399, 2, '23h 59m'],
        [86399, 3, '23h 59m 59s'],
        [86399, 4, '23h 59m 59s'],
        [86399, 5, '23h 59m 59s'],
        [86400, 1, '1d'],
        [86400, 2, '1d'],
        [86400, 3, '1d'],
        [86400, 4, '1d'],
        [86400, 5, '1d'],
        [86401, 1, '1d'],
        [86401, 2, '1d 1s'],
        [86401, 3, '1d 1s'],
        [86401, 4, '1d 1s'],
        [86401, 5, '1d 1s'],
        [90000, 1, '1d'],
        [90000, 2, '1d 1h'],
        [90000, 3, '1d 1h'],
        [90000, 4, '1d 1h'],
        [90000, 5, '1d 1h'],
        [93784, 1, '1d'],
        [93784, 2, '1d 2h'],
        [93784, 3, '1d 2h 3m'],
        [93784, 4, '1d 2h 3m 4s'],
        [93784, 5, '1d 2h 3m 4s'],
        [172800, 1, '2d'],
        [172800, 2, '2d'],
        [172800, 3, '2d'],
        [172800, 4, '2d'],
        [172800, 5, '2d'],
        [172861, 1, '2d'],
        [172861, 2, '2d 1m'],
        [172861, 3, '2d 1m 1s'],
        [172861, 4, '2d 1m 1s'],
        [172861, 5, '2d 1m 1s'],
        [604800, 1, '7d'],
        [604800, 2, '7d'],
        [604800, 3, '7d'],
        [604800, 4, '7d'],
        [604800, 5, '7d'],
        [31536000, 1, '365d'],
        [31536000, 2, '365d'],
        [31536000, 3, '365d'],
        [31536000, 4, '365d'],
        [31536000, 5, '365d'],
        [100000000, 1, '1157d'],
        [100000000, 2, '1157d 9h'],
        [100000000, 3, '1157d 9h 46m'],
        [100000000, 4, '1157d 9h 46m 40s'],
        [100000000, 5, '1157d 9h 46m 40s'],
        [-1, 1, '-1s'],
        [-1, 2, '-1s'],
        [-1, 3, '-1s'],
        [-1, 4, '-1s'],
        [-1, 5, '-1s'],
        [-60, 1, '-1m'],
        [-60, 2, '-1m'],
        [-60, 3, '-1m'],
        [-60, 4, '-1m'],
        [-60, 5, '-1m'],
        [-3661, 1, '-1h'],
        [-3661, 2, '-1h 1m'],
        [-3661, 3, '-1h 1m 1s'],
        [-3661, 4, '-1h 1m 1s'],
        [-3661, 5, '-1h 1m 1s'],
        [-90000, 1, '-1d'],
        [-90000, 2, '-1d 1h'],
        [-90000, 3, '-1d 1h'],
        [-90000, 4, '-1d 1h'],
        [-90000, 5, '-1d 1h'],
        [7200, 1, '2h'],
        [7200, 2, '2h'],
        [7200, 3, '2h'],
        [7200, 4, '2h'],
        [7200, 5, '2h'],
        [7260, 1, '2h'],
        [7260, 2, '2h 1m'],
        [7260, 3, '2h 1m'],
        [7260, 4, '2h 1m'],
        [7260, 5, '2h 1m'],
        [7261, 1, '2h'],
        [7261, 2, '2h 1m'],
        [7261, 3, '2h 1m 1s'],
        [7261, 4, '2h 1m 1s'],
        [7261, 5, '2h 1m 1s'],
        [86460, 1, '1d'],
        [86460, 2, '1d 1m'],
        [86460, 3, '1d 1m'],
        [86460, 4, '1d 1m'],
        [86460, 5, '1d 1m'],
        [86465, 1, '1d'],
        [86465, 2, '1d 1m'],
        [86465, 3, '1d 1m 5s'],
        [86465, 4, '1d 1m 5s'],
        [86465, 5, '1d 1m 5s'],
        [90061, 1, '1d'],
        [90061, 2, '1d 1h'],
        [90061, 3, '1d 1h 1m'],
        [90061, 4, '1d 1h 1m 1s'],
        [90061, 5, '1d 1h 1m 1s'],
        [3660, 1, '1h'],
        [3660, 2, '1h 1m'],
        [3660, 3, '1h 1m'],
        [3660, 4, '1h 1m'],
        [3660, 5, '1h 1m'],
        [3605, 1, '1h'],
        [3605, 2, '1h 5s'],
        [3605, 3, '1h 5s'],
        [3605, 4, '1h 5s'],
        [3605, 5, '1h 5s'],
        [360000, 1, '4d'],
        [360000, 2, '4d 4h'],
        [360000, 3, '4d 4h'],
        [360000, 4, '4d 4h'],
        [360000, 5, '4d 4h'],
    ];
    $ORD = [
        [-3, '-3rd'],
        [-2, '-2nd'],
        [-1, '-1st'],
        [0, '0th'],
        [1, '1st'],
        [2, '2nd'],
        [3, '3rd'],
        [4, '4th'],
        [5, '5th'],
        [6, '6th'],
        [7, '7th'],
        [8, '8th'],
        [9, '9th'],
        [10, '10th'],
        [11, '11th'],
        [12, '12th'],
        [13, '13th'],
        [14, '14th'],
        [15, '15th'],
        [16, '16th'],
        [17, '17th'],
        [18, '18th'],
        [19, '19th'],
        [20, '20th'],
        [21, '21st'],
        [22, '22nd'],
        [23, '23rd'],
        [24, '24th'],
        [25, '25th'],
        [26, '26th'],
        [27, '27th'],
        [28, '28th'],
        [29, '29th'],
        [30, '30th'],
        [100, '100th'],
        [101, '101st'],
        [102, '102nd'],
        [103, '103rd'],
        [104, '104th'],
        [110, '110th'],
        [111, '111th'],
        [112, '112th'],
        [113, '113th'],
        [114, '114th'],
        [120, '120th'],
        [121, '121st'],
        [122, '122nd'],
        [123, '123rd'],
        [1000, '1000th'],
        [1001, '1001st'],
        [1011, '1011th'],
        [1012, '1012th'],
        [1013, '1013th'],
        [2011, '2011th'],
        [2112, '2112th'],
        [1000000001, '1000000001st'],
        [-11, '-11th'],
        [-12, '-12th'],
        [-13, '-13th'],
        [-21, '-21st'],
        [-111, '-111th'],
        [-101, '-101st'],
    ];
    $PLURAL = [
        [-2, 'item', null, '-2 items'],
        [-2, 'box', 'boxes', '-2 boxes'],
        [-2, 'child', 'children', '-2 children'],
        [-2, 'sheep', 'sheep', '-2 sheep'],
        [-2, '', '', '-2 '],
        [-1, 'item', null, '-1 item'],
        [-1, 'box', 'boxes', '-1 box'],
        [-1, 'child', 'children', '-1 child'],
        [-1, 'sheep', 'sheep', '-1 sheep'],
        [-1, '', '', '-1 '],
        [0, 'item', null, '0 items'],
        [0, 'box', 'boxes', '0 boxes'],
        [0, 'child', 'children', '0 children'],
        [0, 'sheep', 'sheep', '0 sheep'],
        [0, '', '', '0 '],
        [1, 'item', null, '1 item'],
        [1, 'box', 'boxes', '1 box'],
        [1, 'child', 'children', '1 child'],
        [1, 'sheep', 'sheep', '1 sheep'],
        [1, '', '', '1 '],
        [2, 'item', null, '2 items'],
        [2, 'box', 'boxes', '2 boxes'],
        [2, 'child', 'children', '2 children'],
        [2, 'sheep', 'sheep', '2 sheep'],
        [2, '', '', '2 '],
        [3, 'item', null, '3 items'],
        [3, 'box', 'boxes', '3 boxes'],
        [3, 'child', 'children', '3 children'],
        [3, 'sheep', 'sheep', '3 sheep'],
        [3, '', '', '3 '],
        [10, 'item', null, '10 items'],
        [10, 'box', 'boxes', '10 boxes'],
        [10, 'child', 'children', '10 children'],
        [10, 'sheep', 'sheep', '10 sheep'],
        [10, '', '', '10 '],
        [11, 'item', null, '11 items'],
        [11, 'box', 'boxes', '11 boxes'],
        [11, 'child', 'children', '11 children'],
        [11, 'sheep', 'sheep', '11 sheep'],
        [11, '', '', '11 '],
        [100, 'item', null, '100 items'],
        [100, 'box', 'boxes', '100 boxes'],
        [100, 'child', 'children', '100 children'],
        [100, 'sheep', 'sheep', '100 sheep'],
        [100, '', '', '100 '],
        [1000000, 'item', null, '1000000 items'],
        [1000000, 'box', 'boxes', '1000000 boxes'],
        [1000000, 'child', 'children', '1000000 children'],
        [1000000, 'sheep', 'sheep', '1000000 sheep'],
        [1000000, '', '', '1000000 '],
    ];
    $AGO = [
        [0, 'just now'],
        [1, 'just now'],
        [9, 'just now'],
        [10, '10 seconds ago'],
        [11, '11 seconds ago'],
        [59, '59 seconds ago'],
        [60, '1 minute ago'],
        [61, '1 minute ago'],
        [119, '1 minute ago'],
        [120, '2 minutes ago'],
        [179, '2 minutes ago'],
        [180, '3 minutes ago'],
        [3599, '59 minutes ago'],
        [3600, '1 hour ago'],
        [3601, '1 hour ago'],
        [7199, '1 hour ago'],
        [7200, '2 hours ago'],
        [10799, '2 hours ago'],
        [10800, '3 hours ago'],
        [86399, '23 hours ago'],
        [86400, 'yesterday'],
        [86401, 'yesterday'],
        [172799, 'yesterday'],
        [172800, '2 days ago'],
        [172801, '2 days ago'],
        [259199, '2 days ago'],
        [259200, '3 days ago'],
        [604799, '6 days ago'],
        [604800, '1 week ago'],
        [604801, '1 week ago'],
        [1209599, '1 week ago'],
        [1209600, '2 weeks ago'],
        [1814399, '2 weeks ago'],
        [1814400, '3 weeks ago'],
        [2591999, '4 weeks ago'],
        [2592000, '1 month ago'],
        [2592001, '1 month ago'],
        [5183999, '1 month ago'],
        [5184000, '2 months ago'],
        [7775999, '2 months ago'],
        [7776000, '3 months ago'],
        [31535999, '12 months ago'],
        [31536000, '1 year ago'],
        [31536001, '1 year ago'],
        [63071999, '1 year ago'],
        [63072000, '2 years ago'],
        [94607999, '2 years ago'],
        [94608000, '3 years ago'],
        [1000000000, '31 years ago'],
        [-1, 'just now'],
        [-9, 'just now'],
        [-10, 'in 10 seconds'],
        [-59, 'in 59 seconds'],
        [-60, 'in 1 minute'],
        [-3600, 'in 1 hour'],
        [-86399, 'in 23 hours'],
        [-86400, 'tomorrow'],
        [-172800, 'in 2 days'],
        [-604800, 'in 1 week'],
        [-2592000, 'in 1 month'],
        [-31536000, 'in 1 year'],
        [-1000000000, 'in 31 years'],
    ];
    $TRUNC = [
        ['hello', 10, '...', 'hello'],
        ['hello', 5, '...', 'hello'],
        ['hello', 4, '...', null],
        ['hello', 3, '...', null],
        ['hello', 2, '...', null],
        ['hello', 1, '...', null],
        ['abcdefghij', 8, '...', 'abc...ij'],
        ['abcdefghij', 7, '...', 'ab...ij'],
        ['abcdefghij', 6, '...', 'ab...j'],
        ['abcdefghij', 5, '...', 'a...j'],
        ['abcdefghij', 9, '...', 'abc...hij'],
        ['abcdefghij', 10, '...', 'abcdefghij'],
        ['abcdefghij', 11, '...', 'abcdefghij'],
        ['/var/log/nginx/error.log', 15, '...', '/var/l...or.log'],
        ['/var/log/nginx/error.log', 12, '..', '/var/..r.log'],
        ['/var/log/nginx/error.log', 6, '...', '/v...g'],
        ['/var/log/nginx/error.log', 5, '...', '/...g'],
        ['/var/log/nginx/error.log', 3, '...', null],
        ['abcdef', 4, '', 'abef'],
        ['abcdef', 3, '', 'abf'],
        ['abcdef', 2, '', 'af'],
        ['abcdef', 1, '', null],
        ['abcdef', 5, '~', 'ab~ef'],
        ['abcdef', 6, '~', 'abcdef'],
        ['abcdef', 3, '~', 'a~f'],
        ['', 3, '...', null],
        ['', 5, '...', ''],
        ['', 4, '...', null],
        ['ab', 6, '...', 'ab'],
        ['abcdefghijklmnop', 10, '[..]', 'abc[..]nop'],
        ['abcdefghijklmnop', 7, '[..]', 'ab[..]p'],
        ['abcdefghijklmnop', 6, '[..]', 'a[..]p'],
        ['abcdefghijklmnop', 5, '[..]', null],
    ];

    test('size', function () use ($SIZE) {
        foreach ($SIZE as [$bytes, $binary, $dec, $want]) {
            eq(try_call(fn() => Human::size($bytes, $binary, $dec)), $want, "size($bytes, " . ($binary ? 'binary' : 'decimal') . ", $dec)");
        }
    });

    test('size defaults', function () {
        eq(Human::size(1536), '1.5 KiB');
        eq(Human::size(1536, true), '1.5 KiB');
        eq(Human::size(1500, false), '1.5 kB');
        eq(Human::size(0), '0 B');
    });

    test('duration', function () use ($DUR) {
        foreach ($DUR as [$s, $mp, $want]) {
            eq(try_call(fn() => Human::duration($s, $mp)), $want, "duration($s, $mp)");
        }
        eq(Human::duration(93784), '1d 2h');
    });

    test('ordinal', function () use ($ORD) {
        foreach ($ORD as [$n, $want]) {
            eq(Human::ordinal($n), $want, "ordinal($n)");
        }
    });

    test('plural', function () use ($PLURAL) {
        foreach ($PLURAL as [$n, $one, $many, $want]) {
            eq($many === null ? Human::plural($n, $one) : Human::plural($n, $one, $many), $want, "plural($n, '$one')");
        }
    });

    test('ago', function () use ($AGO) {
        foreach ($AGO as [$s, $want]) {
            eq(Human::ago($s), $want, "ago($s)");
        }
    });

    test('truncateMiddle', function () use ($TRUNC) {
        foreach ($TRUNC as [$s, $max, $el, $want]) {
            eq(try_call(fn() => Human::truncateMiddle($s, $max, $el)), $want, "truncateMiddle('$s', $max, '$el')");
        }
        eq(Human::truncateMiddle('abcdefghijklmnop', 9), 'abc...nop');
        eq(Human::truncateMiddle('abcdefghijklmnop', 10), 'abcd...nop');
    });

    t_done();
''')

LIB = Lib(
    name="humanfmt", lang="php", title="the Human formatting helpers",
    blurb="The admin dashboard prints file sizes, uptimes, ranks and 'x minutes ago' labels with the Human helper class.",
    files={"README.md": README1, "src/Human.php": F2},
    visible_tests={"tests/run.php": _lang3.php_test(V3)},
    hidden_tests={"tests/run.php": _lang3.php_test(H4)},
    mutate=["src/Human.php"], difficulty=1, tags=["formatting", "units", "text"],
)

_lang3.add(LIB, n=8)
