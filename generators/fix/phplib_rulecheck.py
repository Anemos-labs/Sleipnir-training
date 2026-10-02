"""Request validation with pipe-delimited rules (php): presence, types, size rules by type, email, dates, wildcards and messages; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # Validator

    Validates request data against a rule table (`src/Validator.php`, class `Validator`).

        Validator::check(array $data, array $rules): array

    `$rules` maps a field name to its rules: either a string of rules separated by `|` (`'required|int|between:18,99'`) or an array of rule strings (needed when a rule contains a `|`, such as a `regex`).
    The result maps each **failing field** to the list of its error messages, fields in the order of `$rules` (wildcard fields in index order); fields without errors are not in it. `[]` means everything is valid.
    A rule is `name` or `name:arguments` (arguments are everything after the first `:`). An unknown rule name throws `InvalidArgumentException`.

    ## Fields and wildcards

    A field name is a path of keys separated by dots: `address.city` is `$data['address']['city']`. A segment `*` stands for every element of the array found there, in order: `items.*.qty` is checked once for each `items.0.qty`,
    `items.1.qty`, ... (if the array in front of a `*` is missing, is not an array or is empty there is nothing to check for that rule line). The messages use the expanded path (`items.1.qty`). A path whose parent is missing is simply *absent*.

    ## Presence

    * A value is **absent** when its path does not exist or is `null`. An absent field passes without checking any other rule, **unless** it has the rule `required`.
    * `required` fails for an absent value, for a string that is empty after trimming spaces/tabs/newlines, and for an empty array. The values `0`, `'0'` and `false` are present.
    * Rules are checked in the order written; every failing rule adds its message, **except** that after the rule `bail` (it must come first to matter) only the first failure is reported.

    ## Rules and messages (`{f}` is the field path)

    | rule | passes when | message |
    |---|---|---|
    | `required` | see above | `The {f} field is required.` |
    | `string` | the value is a PHP string | `The {f} field must be a string.` |
    | `int` | an int, or a string of digits with an optional leading `-` (`'007'`, `'-5'`; not `'+5'`, `' 5'`, `'5.0'`) | `The {f} field must be an integer.` |
    | `numeric` | an int or a float, or a string like `12`, `-3.5`, `0.25` (digits, optional `-`, optional `.digits`; no exponent, no `.5`, no `5.`) | `The {f} field must be a number.` |
    | `array` | the value is an array | `The {f} field must be an array.` |
    | `email` | a string `local@domain`; local: 1-64 characters from letters, digits and `._%+-`, not starting or ending with `.` and without `..`; domain: at least two labels separated by `.`, each of letters, digits and `-`, not starting or ending with `-`; the last label has at least 2 letters | `The {f} field must be a valid email address.` |
    | `in:a,b,c` | the value, as a string (ints and floats converted the usual way, `true` is `'1'`, `false` is `''`), equals one of the listed items exactly (case matters) | `The selected {f} is invalid.` |
    | `regex:/p/` | `preg_match` finds the pattern in the value as a string (all of the text after `regex:` is the pattern) | `The {f} field format is invalid.` |
    | `same:other` | the value is identical (`===`) to the value of the field `other` (a dotted path, no wildcards) | `The {f} field must match other.` (with the actual name) |
    | `date` | a string `YYYY-MM-DD`: four digits, `-`, two digits, `-`, two digits, being a real calendar date (years `0001`-`9999`; leap years follow the Gregorian rules) | `The {f} field must be a valid date (YYYY-MM-DD).` |
    | `after:YYYY-MM-DD` | the value is a valid date (as for `date`) strictly later than the given one; an invalid value fails; the given date must itself be valid (else `InvalidArgumentException`) | `The {f} field must be a date after YYYY-MM-DD.` (with the given date) |
    | `min:n`, `max:n`, `between:a,b` | the *size* of the value is at least `n`, at most `n`, or between `a` and `b` inclusive | see below |

    ### Size rules

    The *size* is: the number of items for an array; the numeric value when the field **also has the rule `int` or `numeric`** and the value is a valid number (as for `numeric`; otherwise the size rule is skipped for that value);
    for anything else, the number of **characters** of the value as a string (UTF-8 characters; if the string is not valid UTF-8, its bytes). The arguments of `min`, `max` and `between` are numbers (`between` takes two);
    bad arguments throw `InvalidArgumentException`.

    Messages: for a string size, `The {f} field must be at least {n} characters.`, `The {f} field must not be greater than {n} characters.`, `The {f} field must be between {a} and {b} characters.`;
    for a numeric size: `The {f} field must be at least {n}.`, `The {f} field must not be greater than {n}.`, `The {f} field must be between {a} and {b}.`; for an array:
    `The {f} field must have at least {n} items.`, `The {f} field must not have more than {n} items.`, `The {f} field must have between {a} and {b} items.` The numbers are written as given in the rule.
''')

F2 = dd(r'''
    <?php
    declare(strict_types=1);

    class Validator
    {
        public static function check(array $data, array $rules): array
        {
            $errors = [];
            foreach ($rules as $path => $spec) {
                $list = is_array($spec) ? $spec : explode('|', (string)$spec);
                $parsed = [];
                foreach ($list as $item) {
                    $pos = strpos($item, ':');
                    $name = $pos === false ? $item : substr($item, 0, $pos);
                    $arg = $pos === false ? null : substr($item, $pos + 1);
                    self::assertKnown($name);
                    $parsed[] = [$name, $arg];
                }
                foreach (self::expand($data, explode('.', (string)$path)) as [$field, $present, $value]) {
                    $msgs = self::checkField($data, $field, $present, $value, $parsed);
                    if ($msgs) {
                        $errors[$field] = $msgs;
                    }
                }
            }
            return $errors;
        }

        private static function assertKnown(string $name): void
        {
            $known = ['required', 'string', 'int', 'numeric', 'array', 'email', 'in', 'regex', 'same', 'date', 'after', 'min', 'max', 'between', 'bail'];
            if (!in_array($name, $known, true)) {
                throw new InvalidArgumentException("unknown rule: $name");
            }
        }

        /** @return list<array{string,bool,mixed}> */
        private static function expand($node, array $segments, string $prefix = ''): array
        {
            if (count($segments) === 0) {
                return [[$prefix, true, $node]];
            }
            $seg = array_shift($segments);
            if ($seg === '*') {
                $out = [];
                if (is_array($node)) {
                    foreach ($node as $k => $child) {
                        $out = array_merge($out, self::expand($child, $segments, $prefix === '' ? (string)$k : $prefix . '.' . $k));
                    }
                }
                return $out;
            }
            $next = $prefix === '' ? $seg : $prefix . '.' . $seg;
            if (is_array($node) && array_key_exists($seg, $node)) {
                return self::expand($node[$seg], $segments, $next);
            }
            if (in_array('*', $segments, true)) {
                return [];
            }
            return [[self::joinRest($next, $segments), false, null]];
        }

        private static function joinRest(string $prefix, array $segments): string
        {
            return count($segments) ? $prefix . '.' . implode('.', $segments) : $prefix;
        }

        private static function lookup(array $data, string $path)
        {
            $node = $data;
            foreach (explode('.', $path) as $seg) {
                if (!is_array($node) || !array_key_exists($seg, $node)) {
                    return null;
                }
                $node = $node[$seg];
            }
            return $node;
        }

        private static function isInt($v): bool
        {
            return is_int($v) || (is_string($v) && preg_match('/^-?[0-9]+$/', $v) === 1);
        }

        private static function isNumeric($v): bool
        {
            return is_int($v) || is_float($v) || (is_string($v) && preg_match('/^-?[0-9]+(\.[0-9]+)?$/', $v) === 1);
        }

        private static function asString($v): string
        {
            if (is_bool($v)) {
                return $v ? '1' : '';
            }
            return (string)$v;
        }

        private static function validDate(string $s): ?array
        {
            if (preg_match('/^([0-9]{4})-([0-9]{2})-([0-9]{2})$/', $s, $m) !== 1) {
                return null;
            }
            $y = (int)$m[1];
            $mo = (int)$m[2];
            $d = (int)$m[3];
            if ($y < 1 || $mo < 1 || $mo > 12 || $d < 1) {
                return null;
            }
            $days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
            $leap = ($y % 4 === 0 && $y % 100 !== 0) || $y % 400 === 0;
            $max = $days[$mo - 1] + ($mo === 2 && $leap ? 1 : 0);
            if ($d > $max) {
                return null;
            }
            return [$y, $mo, $d];
        }

        private static function validEmail($v): bool
        {
            if (!is_string($v) || substr_count($v, '@') !== 1) {
                return false;
            }
            [$local, $domain] = explode('@', $v);
            $ln = strlen($local);
            if ($ln < 1 || $ln > 64 || preg_match('/^[A-Za-z0-9._%+-]+$/', $local) !== 1) {
                return false;
            }
            if ($local[0] === '.' || $local[$ln - 1] === '.' || strpos($local, '..') !== false) {
                return false;
            }
            $labels = explode('.', $domain);
            if (count($labels) < 2) {
                return false;
            }
            foreach ($labels as $label) {
                if (preg_match('/^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$/', $label) !== 1) {
                    return false;
                }
            }
            return preg_match('/^[A-Za-z]{2,}$/', end($labels)) === 1;
        }

        private static function sizeOf($value, bool $numericSemantics): ?array
        {
            if (is_array($value)) {
                return [count($value), 'items'];
            }
            if ($numericSemantics) {
                if (!self::isNumeric($value)) {
                    return null;
                }
                return [$value + 0, 'number'];
            }
            $s = self::asString($value);
            $n = preg_match_all('/./su', $s);
            return [$n === false || ($n === 0 && $s !== '') ? strlen($s) : $n, 'chars'];
        }

        private static function num(string $text): float
        {
            if (!is_numeric($text)) {
                throw new InvalidArgumentException("bad number: $text");
            }
            return $text + 0;
        }

        private static function checkField(array $data, string $field, bool $present, $value, array $rules): array
        {
            $names = array_column($rules, 0);
            $isPresent = $present && $value !== null;
            $messages = [];
            $bail = false;
            foreach ($rules as [$name, $arg]) {
                if ($name === 'bail') {
                    $bail = true;
                    continue;
                }
                if ($name === 'required') {
                    $blank = !$isPresent || (is_string($value) && trim($value, " \t\n\r") === '') || (is_array($value) && count($value) === 0);
                    if ($blank) {
                        $messages[] = "The $field field is required.";
                    }
                } elseif (!$isPresent) {
                    continue;
                } else {
                    $msg = self::applyRule($data, $field, $value, $name, $arg, $names);
                    if ($msg !== null) {
                        $messages[] = $msg;
                    }
                }
                if ($bail && count($messages) > 0) {
                    break;
                }
            }
            return $messages;
        }

        private static function applyRule(array $data, string $f, $value, string $name, ?string $arg, array $names): ?string
        {
            switch ($name) {
                case 'string':
                    return is_string($value) ? null : "The $f field must be a string.";
                case 'int':
                    return self::isInt($value) ? null : "The $f field must be an integer.";
                case 'numeric':
                    return self::isNumeric($value) ? null : "The $f field must be a number.";
                case 'array':
                    return is_array($value) ? null : "The $f field must be an array.";
                case 'email':
                    return self::validEmail($value) ? null : "The $f field must be a valid email address.";
                case 'in':
                    return in_array(self::asString($value), explode(',', (string)$arg), true) ? null : "The selected $f is invalid.";
                case 'regex':
                    return preg_match((string)$arg, self::asString($value)) === 1 ? null : "The $f field format is invalid.";
                case 'same':
                    return $value === self::lookup($data, (string)$arg) ? null : "The $f field must match $arg.";
                case 'date':
                    return is_string($value) && self::validDate($value) !== null ? null : "The $f field must be a valid date (YYYY-MM-DD).";
                case 'after':
                    $limit = self::validDate((string)$arg);
                    if ($limit === null) {
                        throw new InvalidArgumentException("bad date: $arg");
                    }
                    $d = is_string($value) ? self::validDate($value) : null;
                    if ($d !== null && $d > $limit) {
                        return null;
                    }
                    return "The $f field must be a date after $arg.";
                default:
                    return self::sizeRule($f, $value, $name, (string)$arg, $names);
            }
        }

        private static function sizeRule(string $f, $value, string $name, string $arg, array $names): ?string
        {
            $numeric = in_array('int', $names, true) || in_array('numeric', $names, true);
            $size = self::sizeOf($value, $numeric);
            if ($size === null) {
                return null;
            }
            [$n, $kind] = $size;
            if ($name === 'between') {
                $parts = explode(',', $arg);
                if (count($parts) !== 2) {
                    throw new InvalidArgumentException('between needs two numbers');
                }
                $a = self::num($parts[0]);
                $b = self::num($parts[1]);
                if ($n >= $a && $n <= $b) {
                    return null;
                }
                $what = $kind === 'items' ? ' items' : ($kind === 'chars' ? ' characters' : '');
                $start = $kind === 'items' ? "The $f field must have between " : "The $f field must be between ";
                return $start . $parts[0] . ' and ' . $parts[1] . $what . '.';
            }
            $limit = self::num($arg);
            if ($name === 'min') {
                if ($n >= $limit) {
                    return null;
                }
                if ($kind === 'items') {
                    return "The $f field must have at least $arg items.";
                }
                return "The $f field must be at least $arg" . ($kind === 'chars' ? ' characters.' : '.');
            }
            if ($n <= $limit) {
                return null;
            }
            if ($kind === 'items') {
                return "The $f field must not have more than $arg items.";
            }
            return "The $f field must not be greater than $arg" . ($kind === 'chars' ? ' characters.' : '.');
        }
    }
''')

V3 = dd(r'''
    require __DIR__ . '/../src/Validator.php';

    test('basics', function () {
        eq(Validator::check(['name' => 'Ada'], ['name' => 'required|string|min:2']), []);
        eq(Validator::check(['name' => ''], ['name' => 'required']), ['name' => ['The name field is required.']]);
        eq(Validator::check(['age' => '17'], ['age' => 'required|int|between:18,99']), ['age' => ['The age field must be between 18 and 99.']]);
    });

    t_done();
''')

H4 = dd(r'''
    require __DIR__ . '/../src/Validator.php';

    $CASES = [
        [['name' => 'Ada'], ['name' => 'required|string|min:2|max:10'], []],
        [['name' => ''], ['name' => 'required'], ['name' => ['The name field is required.']]],
        [['name' => '   '], ['name' => 'required'], ['name' => ['The name field is required.']]],
        [['name' => ' 	

    '], ['name' => 'required'], ['name' => ['The name field is required.']]],
        [['name' => '0'], ['name' => 'required'], []],
        [['name' => 0], ['name' => 'required'], []],
        [['name' => false], ['name' => 'required'], []],
        [['name' => []], ['name' => 'required'], ['name' => ['The name field is required.']]],
        [['name' => [0]], ['name' => 'required'], []],
        [['name' => null], ['name' => 'required'], ['name' => ['The name field is required.']]],
        [[], ['name' => 'required'], ['name' => ['The name field is required.']]],
        [[], ['name' => 'string|min:3'], []],
        [['name' => null], ['name' => 'string|min:3'], []],
        [['name' => ''], ['name' => 'string|min:3'], ['name' => ['The name field must be at least 3 characters.']]],
        [['name' => 'ab'], ['name' => 'min:3'], ['name' => ['The name field must be at least 3 characters.']]],
        [['name' => 'abc'], ['name' => 'min:3'], []],
        [['name' => 'abcd'], ['name' => 'max:3'], ['name' => ['The name field must not be greater than 3 characters.']]],
        [['name' => 'abc'], ['name' => 'max:3'], []],
        [['name' => 'abc'], ['name' => 'between:3,5'], []],
        [['name' => 'ab'], ['name' => 'between:3,5'], ['name' => ['The name field must be between 3 and 5 characters.']]],
        [['name' => 'abcdef'], ['name' => 'between:3,5'], ['name' => ['The name field must be between 3 and 5 characters.']]],
        [['name' => 'abcde'], ['name' => 'between:3,5'], []],
        [['name' => 'héllo'], ['name' => 'max:5'], []],
        [['name' => '日本語'], ['name' => 'min:3|max:3'], []],
        [['name' => '日本語'], ['name' => 'max:2'], ['name' => ['The name field must not be greater than 2 characters.']]],
        [['name' => '😀😀'], ['name' => 'max:2'], []],
        [['name' => '😀😀'], ['name' => 'max:1'], ['name' => ['The name field must not be greater than 1 characters.']]],
        [['age' => '17'], ['age' => 'required|int|between:18,99'], ['age' => ['The age field must be between 18 and 99.']]],
        [['age' => '18'], ['age' => 'required|int|between:18,99'], []],
        [['age' => '99'], ['age' => 'int|between:18,99'], []],
        [['age' => '100'], ['age' => 'int|between:18,99'], ['age' => ['The age field must be between 18 and 99.']]],
        [['age' => 17], ['age' => 'int|min:18'], ['age' => ['The age field must be at least 18.']]],
        [['age' => 'abc'], ['age' => 'int|min:18'], ['age' => ['The age field must be an integer.']]],
        [['age' => 'abc'], ['age' => 'min:18'], ['age' => ['The age field must be at least 18 characters.']]],
        [['age' => '5.5'], ['age' => 'int|min:6'], ['age' => ['The age field must be an integer.', 'The age field must be at least 6.']]],
        [['age' => 5.5], ['age' => 'numeric|min:6'], ['age' => ['The age field must be at least 6.']]],
        [['age' => 5.5], ['age' => 'numeric|max:5.5'], []],
        [['age' => '5.50'], ['age' => 'numeric|max:5.5'], []],
        [['age' => '-3'], ['age' => 'int|min:-5|max:-3'], []],
        [['age' => '-3'], ['age' => 'int|min:-2'], ['age' => ['The age field must be at least -2.']]],
        [['n' => '12'], ['n' => 'min:3'], ['n' => ['The n field must be at least 3 characters.']]],
        [['n' => '12'], ['n' => 'int|min:3'], []],
        [['n' => '12'], ['n' => 'numeric|max:11.99'], ['n' => ['The n field must not be greater than 11.99.']]],
        [['n' => 12], ['n' => 'max:1'], ['n' => ['The n field must not be greater than 1 characters.']]],
        [['n' => 12], ['n' => 'int|max:1'], ['n' => ['The n field must not be greater than 1.']]],
        [['x' => '007'], ['x' => 'int'], []],
        [['x' => '+5'], ['x' => 'int'], ['x' => ['The x field must be an integer.']]],
        [['x' => ' 5'], ['x' => 'int'], ['x' => ['The x field must be an integer.']]],
        [['x' => '5.0'], ['x' => 'int'], ['x' => ['The x field must be an integer.']]],
        [['x' => ''], ['x' => 'int'], ['x' => ['The x field must be an integer.']]],
        [['x' => '-'], ['x' => 'int'], ['x' => ['The x field must be an integer.']]],
        [['x' => -5], ['x' => 'int'], []],
        [['x' => 5.0], ['x' => 'int'], ['x' => ['The x field must be an integer.']]],
        [['x' => true], ['x' => 'int'], ['x' => ['The x field must be an integer.']]],
        [['x' => '-3.5'], ['x' => 'numeric'], []],
        [['x' => '0.25'], ['x' => 'numeric'], []],
        [['x' => '.5'], ['x' => 'numeric'], ['x' => ['The x field must be a number.']]],
        [['x' => '5.'], ['x' => 'numeric'], ['x' => ['The x field must be a number.']]],
        [['x' => '1e3'], ['x' => 'numeric'], ['x' => ['The x field must be a number.']]],
        [['x' => '12'], ['x' => 'numeric'], []],
        [['x' => 7], ['x' => 'numeric'], []],
        [['x' => 7.25], ['x' => 'numeric'], []],
        [['x' => 'abc'], ['x' => 'numeric'], ['x' => ['The x field must be a number.']]],
        [['x' => true], ['x' => 'numeric'], ['x' => ['The x field must be a number.']]],
        [['x' => '--1'], ['x' => 'numeric'], ['x' => ['The x field must be a number.']]],
        [['x' => 'a'], ['x' => 'string'], []],
        [['x' => 5], ['x' => 'string'], ['x' => ['The x field must be a string.']]],
        [['x' => ['a']], ['x' => 'string'], ['x' => ['The x field must be a string.']]],
        [['x' => ['a']], ['x' => 'array'], []],
        [['x' => 'a'], ['x' => 'array'], ['x' => ['The x field must be an array.']]],
        [['x' => []], ['x' => 'array'], []],
        [['x' => ['a' => 1]], ['x' => 'array'], []],
        [['t' => ['a', 'b']], ['t' => 'array|min:2|max:3'], []],
        [['t' => ['a']], ['t' => 'array|min:2'], ['t' => ['The t field must have at least 2 items.']]],
        [['t' => ['a', 'b', 'c', 'd']], ['t' => 'array|max:3'], ['t' => ['The t field must not have more than 3 items.']]],
        [['t' => ['a', 'b', 'c', 'd']], ['t' => 'between:2,3'], ['t' => ['The t field must have between 2 and 3 items.']]],
        [['t' => ['a']], ['t' => 'between:2,3'], ['t' => ['The t field must have between 2 and 3 items.']]],
        [['t' => ['a', 'b']], ['t' => 'between:2,3'], []],
        [['t' => [1, 2, 3]], ['t' => 'int|max:2'], ['t' => ['The t field must be an integer.', 'The t field must not have more than 2 items.']]],
        [['v' => 'red'], ['v' => 'in:red,green,blue'], []],
        [['v' => 'Red'], ['v' => 'in:red,green,blue'], ['v' => ['The selected v is invalid.']]],
        [['v' => 'redd'], ['v' => 'in:red,green,blue'], ['v' => ['The selected v is invalid.']]],
        [['v' => 'gre'], ['v' => 'in:red,green,blue'], ['v' => ['The selected v is invalid.']]],
        [['v' => 5], ['v' => 'in:4,5,6'], []],
        [['v' => '5'], ['v' => 'in:4,5,6'], []],
        [['v' => 7], ['v' => 'in:4,5,6'], ['v' => ['The selected v is invalid.']]],
        [['v' => true], ['v' => 'in:1,2'], []],
        [['v' => false], ['v' => 'required|in:0,1'], ['v' => ['The selected v is invalid.']]],
        [['v' => ''], ['v' => 'in:a,b'], ['v' => ['The selected v is invalid.']]],
        [['v' => 'a b'], ['v' => 'in:a b,c'], []],
        [['v' => 'a,b'], ['v' => 'in:a,b'], ['v' => ['The selected v is invalid.']]],
        [['p' => 'abc123'], ['p' => ['regex:/^[a-z]+[0-9]+$/']], []],
        [['p' => '123abc'], ['p' => ['regex:/^[a-z]+[0-9]+$/']], ['p' => ['The p field format is invalid.']]],
        [['p' => 'a|b'], ['p' => ['regex:/^a|b$/']], []],
        [['p' => 'x'], ['p' => ['regex:/^(a|b)$/']], ['p' => ['The p field format is invalid.']]],
        [['p' => 'b'], ['p' => ['regex:/^(a|b)$/']], []],
        [['p' => 12], ['p' => ['regex:/^[0-9]+$/']], []],
        [['p' => 'ab'], ['p' => ['required', 'regex:/^[a-z]{3}$/', 'min:3']], ['p' => ['The p field format is invalid.', 'The p field must be at least 3 characters.']]],
        [['p' => 'abc'], ['p' => 'regex:/b/'], []],
        [['p' => 'abc'], ['p' => 'regex:/^b/'], ['p' => ['The p field format is invalid.']]],
        [['pw' => 'secret', 'pw2' => 'secret'], ['pw2' => 'same:pw'], []],
        [['pw' => 'secret', 'pw2' => 'Secret'], ['pw2' => 'same:pw'], ['pw2' => ['The pw2 field must match pw.']]],
        [['pw' => 'secret'], ['pw2' => 'same:pw'], []],
        [['pw' => 'secret'], ['pw2' => 'required|same:pw'], ['pw2' => ['The pw2 field is required.']]],
        [['pw' => 1, 'pw2' => '1'], ['pw2' => 'same:pw'], ['pw2' => ['The pw2 field must match pw.']]],
        [['pw' => 1, 'pw2' => 1], ['pw2' => 'same:pw'], []],
        [['a' => ['b' => 'x'], 'c' => 'x'], ['c' => 'same:a.b'], []],
        [['a' => ['b' => 'x'], 'c' => 'y'], ['c' => 'same:a.b'], ['c' => ['The c field must match a.b.']]],
        [['a' => 'x', 'c' => 'x'], ['c' => 'same:a.b'], ['c' => ['The c field must match a.b.']]],
        [['pw' => null, 'pw2' => 'x'], ['pw2' => 'same:pw'], ['pw2' => ['The pw2 field must match pw.']]],
        [['d' => '2024-02-29'], ['d' => 'date'], []],
        [['d' => '2023-02-29'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '1900-02-29'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '2000-02-29'], ['d' => 'date'], []],
        [['d' => '2100-02-29'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '2024-04-31'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '2024-04-30'], ['d' => 'date'], []],
        [['d' => '2024-13-01'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '2024-12-31'], ['d' => 'date'], []],
        [['d' => '2024-00-10'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '2024-01-00'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '0001-01-01'], ['d' => 'date'], []],
        [['d' => '0000-01-01'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '9999-12-31'], ['d' => 'date'], []],
        [['d' => '2024-1-5'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '24-01-05'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '2024/01/05'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '2024-01-05 '], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => ' 2024-01-05'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => 20240105], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '2024-01-31'], ['d' => 'date'], []],
        [['d' => '2024-01-32'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '2024-06-31'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '2024-09-31'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '2024-11-31'], ['d' => 'date'], ['d' => ['The d field must be a valid date (YYYY-MM-DD).']]],
        [['d' => '2024-03-31'], ['d' => 'date'], []],
        [['d' => '2024-05-31'], ['d' => 'date'], []],
        [['d' => '2024-07-31'], ['d' => 'date'], []],
        [['d' => '2024-08-31'], ['d' => 'date'], []],
        [['d' => '2024-10-31'], ['d' => 'date'], []],
        [['d' => '2023-02-28'], ['d' => 'date'], []],
        [['d' => '2024-03-01'], ['d' => 'after:2024-02-29'], []],
        [['d' => '2024-02-29'], ['d' => 'after:2024-02-29'], ['d' => ['The d field must be a date after 2024-02-29.']]],
        [['d' => '2024-02-28'], ['d' => 'after:2024-02-29'], ['d' => ['The d field must be a date after 2024-02-29.']]],
        [['d' => '2025-01-01'], ['d' => 'after:2024-12-31'], []],
        [['d' => '2024-12-31'], ['d' => 'after:2025-01-01'], ['d' => ['The d field must be a date after 2025-01-01.']]],
        [['d' => '2024-02-30'], ['d' => 'after:2020-01-01'], ['d' => ['The d field must be a date after 2020-01-01.']]],
        [['d' => 'nope'], ['d' => 'after:2020-01-01'], ['d' => ['The d field must be a date after 2020-01-01.']]],
        [['d' => 5], ['d' => 'after:2020-01-01'], ['d' => ['The d field must be a date after 2020-01-01.']]],
        [['d' => '2024-10-01'], ['d' => 'after:2024-09-30'], []],
        [['d' => '2024-09-30'], ['d' => 'after:2023-10-01'], []],
        [['d' => '2023-10-01'], ['d' => 'after:2024-09-30'], ['d' => ['The d field must be a date after 2024-09-30.']]],
        [['d' => '2024-01-01'], ['d' => 'after:2023-12-31'], []],
        [['d' => '2024-01-01'], ['d' => 'after:2023-02-30'], null],
        [['d' => '2024-01-01'], ['d' => 'after:nonsense'], null],
        [['d' => '2024-01-01'], ['d' => 'foo'], null],
        [['d' => 'x'], ['d' => 'min:abc'], null],
        [['d' => 'x'], ['d' => 'between:1'], null],
        [['d' => 'x'], ['d' => 'between:1,2,3'], null],
        [['d' => 'x'], ['d' => 'max'], null],
        [['e' => 'a@b.co'], ['e' => 'email'], []],
        [['e' => 'a@b.c'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'user.name+tag@example.com'], ['e' => 'email'], []],
        [['e' => 'user@sub.example.org'], ['e' => 'email'], []],
        [['e' => 'user@example'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => '@example.com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'user@'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a@@b.com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a@b@c.com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => '.a@b.com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a.@b.com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a..b@c.com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a@-b.com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a@b-.com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a@b..com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a@.com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a@b.com.'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a@b.c0m'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a@b.123'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a b@c.com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a@b c.com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a@b_c.com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa@x.com'], ['e' => 'email'], []],
        [['e' => 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa@x.com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a%b@c.com'], ['e' => 'email'], []],
        [['e' => 'a-b@c-d.co'], ['e' => 'email'], []],
        [['e' => 'a@b.co.uk'], ['e' => 'email'], []],
        [['e' => 5], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'é@x.com'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a@x.cé'], ['e' => 'email'], ['e' => ['The e field must be a valid email address.']]],
        [['e' => 'a@b.cO'], ['e' => 'email'], []],
        [['e' => 'A@B.CO'], ['e' => 'email'], []],
        [['e' => 'a@0b.com'], ['e' => 'email'], []],
        [['e' => 'a@b0.com'], ['e' => 'email'], []],
        [['n' => 'x'], ['n' => 'bail|required|string|min:3|max:5'], ['n' => ['The n field must be at least 3 characters.']]],
        [['n' => ''], ['n' => 'bail|required|string|min:3'], ['n' => ['The n field is required.']]],
        [['n' => ''], ['n' => 'required|string|min:3'], ['n' => ['The n field is required.', 'The n field must be at least 3 characters.']]],
        [['n' => 5], ['n' => 'bail|string|min:3'], ['n' => ['The n field must be a string.']]],
        [['n' => 5], ['n' => 'string|min:3'], ['n' => ['The n field must be a string.', 'The n field must be at least 3 characters.']]],
        [['n' => 5], ['n' => 'string|bail|min:3'], ['n' => ['The n field must be a string.', 'The n field must be at least 3 characters.']]],
        [['n' => 'ab'], ['n' => 'min:3|bail|max:1'], ['n' => ['The n field must be at least 3 characters.', 'The n field must not be greater than 1 characters.']]],
        [['n' => 'ab'], ['n' => 'bail|min:3|max:1'], ['n' => ['The n field must be at least 3 characters.']]],
        [['address' => ['city' => 'Oslo']], ['address.city' => 'required|min:3'], []],
        [['address' => ['city' => 'O']], ['address.city' => 'required|min:3'], ['address.city' => ['The address.city field must be at least 3 characters.']]],
        [['address' => []], ['address.city' => 'required'], ['address.city' => ['The address.city field is required.']]],
        [['address' => 'x'], ['address.city' => 'required'], ['address.city' => ['The address.city field is required.']]],
        [[], ['address.city' => 'required'], ['address.city' => ['The address.city field is required.']]],
        [['address' => ['city' => null]], ['address.city' => 'required'], ['address.city' => ['The address.city field is required.']]],
        [['a' => ['b' => ['c' => '']]], ['a.b.c' => 'required'], ['a.b.c' => ['The a.b.c field is required.']]],
        [['a' => ['b' => ['c' => 'x']]], ['a.b.c' => 'required|min:2'], ['a.b.c' => ['The a.b.c field must be at least 2 characters.']]],
        [['items' => [['qty' => '2', 'sku' => 'A'], ['qty' => '0', 'sku' => ''], ['qty' => 'x', 'sku' => 'C']]], ['items.*.qty' => 'required|int|min:1', 'items.*.sku' => 'required|string'], ['items.1.qty' => ['The items.1.qty field must be at least 1.'], 'items.2.qty' => ['The items.2.qty field must be an integer.'], 'items.1.sku' => ['The items.1.sku field is required.']]],
        [['items' => []], ['items.*.qty' => 'required'], []],
        [[], ['items.*.qty' => 'required'], []],
        [['items' => 'x'], ['items.*.qty' => 'required'], []],
        [['items' => [['qty' => 1]]], ['items.*.qty' => 'int', 'items.*.sku' => 'required'], ['items.0.sku' => ['The items.0.sku field is required.']]],
        [['items' => [['qty' => 1], []]], ['items.*.qty' => 'required|int'], ['items.1.qty' => ['The items.1.qty field is required.']]],
        [['items' => [1, 2]], ['items.*.qty' => 'required'], ['items.0.qty' => ['The items.0.qty field is required.'], 'items.1.qty' => ['The items.1.qty field is required.']]],
        [['a' => [[1, 2], [3]]], ['a.*.*' => 'required|int|min:2'], ['a.0.0' => ['The a.0.0 field must be at least 2.']]],
        [['a' => ['x' => ['v' => '1'], 'y' => ['v' => '']]], ['a.*.v' => 'required'], ['a.y.v' => ['The a.y.v field is required.']]],
        [['a' => [['v' => [1]], ['v' => []]]], ['a.*.v' => 'required|array|min:1'], ['a.1.v' => ['The a.1.v field is required.', 'The a.1.v field must have at least 1 items.']]],
        [['name' => 'A', 'email' => 'bad'], ['name' => 'required|min:2', 'email' => 'required|email', 'age' => 'required|int'], ['name' => ['The name field must be at least 2 characters.'], 'email' => ['The email field must be a valid email address.'], 'age' => ['The age field is required.']]],
        [['name' => 'ok'], [], []],
        [[], [], []],
        [['a' => 1], ['a' => []], []],
        [['a' => 1], ['a' => ''], null],
        [['name' => 2.5, 'age' => '4.5', 'email' => null, 'address' => ['city' => 'a@b.co'], 'items' => [], 'dob' => 'abc'], ['email' => 'min:0.5', 'pw2' => 'bail', 'age' => 'in:1,2,3|int|string'], ['age' => ['The selected age is invalid.', 'The age field must be an integer.']]],
        [['name' => '日本', 'age' => '2019-03-01', 'tags' => '2019-03-01', 'items' => [['qty' => true]], 'pw2' => 'x@y'], ['dob' => 'max:-1|max:-1|required|int'], ['dob' => ['The dob field is required.']]],
        [['age' => '4.5', 'address' => ['city' => '123'], 'items' => [['qty' => null]], 'dob' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'pw2' => 'x@y'], ['tags' => ['string', 'max:-1', 'regex:/^[a-z]+$/', 'min:3']], []],
        [['name' => '', 'age' => '@', 'email' => -3, 'address' => ['city' => '007'], 'items' => [['qty' => '日本'], ['qty' => 'abcdef'], ['qty' => 'a@b.co']], 'pw2' => 'é'], ['name' => 'email|required|min:3', 'email' => ['regex:/^[a-z]+$/', 'bail', 'between:2,6']], ['name' => ['The name field must be a valid email address.', 'The name field is required.', 'The name field must be at least 3 characters.'], 'email' => ['The email field format is invalid.']]],
        [['name' => '123', 'age' => '日本', 'tags' => '@', 'address' => ['city' => 'a@b.co'], 'dob' => '-4', 'pw2' => ''], ['items.*.qty' => 'min:2|bail|required|array', 'dob' => 'same:name|min:2|string', 'address.city' => 'string|min:0.5|in:1,2,3'], ['dob' => ['The dob field must match name.'], 'address.city' => ['The selected address.city is invalid.']]],
        [['name' => '4.5', 'email' => '2024-02-29', 'tags' => null, 'address' => ['city' => null]], ['dob' => 'in:a,bb,ccc', 'pw2' => ['regex:/^[a-z]+$/', 'after:2020-02-29', 'numeric']], []],
        [['name' => 2.5, 'age' => '日本', 'email' => '4.5', 'tags' => 2.5, 'address' => ['city' => false], 'items' => [['qty' => '4.5'], ['qty' => 'abcdef'], ['qty' => null]], 'dob' => 12, 'pw2' => 'abcdef'], ['items.*.qty' => 'min:3|numeric|required|in:a,bb,ccc'], ['items.0.qty' => ['The selected items.0.qty is invalid.'], 'items.1.qty' => ['The items.1.qty field must be a number.', 'The selected items.1.qty is invalid.'], 'items.2.qty' => ['The items.2.qty field is required.']]],
        [['name' => '2019-03-01', 'age' => 'x@y', 'tags' => true, 'address' => ['city' => '2024-02-29'], 'items' => [['qty' => 'a@b.co']], 'dob' => 'x', 'pw2' => []], ['dob' => ['bail', 'string', 'regex:/^[a-z]+$/', 'min:0.5'], 'address.city' => 'required|after:2020-02-29|max:10'], []],
        [['name' => [1], 'age' => '123', 'email' => '2019-03-01', 'address' => 12, 'items' => [['qty' => 'abc'], ['qty' => 'abc']], 'dob' => ''], ['dob' => 'same:name|after:2020-02-29|in:1,2,3', 'tags' => 'email|max:5', 'address.city' => 'bail|in:a,bb,ccc|max:10', 'email' => 'min:2|required|string'], ['dob' => ['The dob field must match name.', 'The dob field must be a date after 2020-02-29.', 'The selected dob is invalid.']]],
        [['name' => 'abcdef', 'age' => [1], 'email' => 'é', 'items' => [], 'dob' => '@', 'pw2' => 'a@b.co'], ['name' => 'in:1,2,3|max:10'], ['name' => ['The selected name is invalid.']]],
        [['name' => '2024-02-29', 'tags' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'address' => '@', 'dob' => 'a'], ['dob' => 'in:a,bb,ccc|numeric', 'address.city' => 'required', 'email' => 'numeric', 'name' => 'min:0.5'], ['dob' => ['The dob field must be a number.'], 'address.city' => ['The address.city field is required.']]],
        [['age' => 'é', 'email' => '007', 'tags' => 0, 'dob' => -3, 'pw2' => ''], ['email' => 'max:-1|max:5|min:3|same:name', 'pw2' => 'between:2,6|in:1,2,3|after:2020-02-29|max:-1', 'name' => 'int|in:1,2,3|min:0.5'], ['email' => ['The email field must not be greater than -1 characters.', 'The email field must match name.'], 'pw2' => ['The pw2 field must be between 2 and 6 characters.', 'The selected pw2 is invalid.', 'The pw2 field must be a date after 2020-02-29.', 'The pw2 field must not be greater than -1 characters.']]],
        [['name' => 'a@b.co', 'email' => '2019-03-01', 'address' => ['city' => '@'], 'items' => [['qty' => '2024-02-29'], ['qty' => '007']], 'dob' => '4.5'], ['pw2' => 'min:2|max:-1|in:a,bb,ccc|array', 'name' => 'in:1,2,3|between:2,6|int', 'age' => 'max:5'], ['name' => ['The selected name is invalid.', 'The name field must be an integer.']]],
        [['name' => '  ', 'age' => 'abcdef', 'tags' => '  ', 'items' => [], 'dob' => 1, 'pw2' => false], ['pw2' => 'date|in:a,bb,ccc|min:2|bail', 'age' => 'bail|max:-1|between:2,6|max:10', 'tags' => 'max:10'], ['pw2' => ['The pw2 field must be a valid date (YYYY-MM-DD).', 'The selected pw2 is invalid.', 'The pw2 field must be at least 2 characters.'], 'age' => ['The age field must not be greater than -1 characters.']]],
        [['email' => 'x', 'tags' => 1, 'address' => ['city' => '2019-03-01'], 'dob' => 'a@b.co', 'pw2' => '-4'], ['email' => ['regex:/^[a-z]+$/'], 'age' => 'bail|max:-1|min:2|min:3'], []],
        [['name' => '123', 'email' => '4.5', 'address' => ['city' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], 'items' => [['qty' => ''], ['qty' => 0]], 'dob' => 'a@b.co', 'pw2' => 12], ['name' => 'required|in:1,2,3|in:1,2,3', 'tags' => ['regex:/^[a-z]+$/', 'regex:/^[a-z]+$/', 'in:1,2,3', 'bail']], ['name' => ['The selected name is invalid.', 'The selected name is invalid.']]],
        [['age' => [1], 'email' => 2.5, 'tags' => '-4', 'address' => ['city' => [1]], 'items' => [], 'pw2' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], ['items.*.qty' => 'int|string|array', 'pw2' => 'array|bail', 'email' => ['regex:/^[a-z]+$/', 'in:a,bb,ccc']], ['email' => ['The email field format is invalid.', 'The selected email is invalid.']]],
        [['name' => '2024-02-29', 'age' => 'abc', 'email' => 1, 'tags' => '007', 'pw2' => []], ['tags' => 'in:a,bb,ccc|max:-1|same:name', 'age' => 'min:0.5', 'name' => 'max:10', 'address.city' => 'array|string|min:3'], ['tags' => ['The selected tags is invalid.', 'The tags field must not be greater than -1 characters.', 'The tags field must match name.']]],
        [['name' => true, 'tags' => '  ', 'address' => ['city' => ['a', 'b']], 'dob' => '123'], ['tags' => 'between:2,6', 'email' => 'min:2|max:-1|numeric|after:2020-02-29', 'dob' => 'bail|date', 'items.*.qty' => 'between:2,6|array|email|date'], ['dob' => ['The dob field must be a valid date (YYYY-MM-DD).']]],
        [['name' => -3, 'age' => 'abcdef', 'email' => '  ', 'tags' => 2.5, 'address' => ['city' => -3], 'items' => [['qty' => -3]], 'dob' => '  ', 'pw2' => 'abcdef'], ['email' => 'after:2020-02-29|array|int|date', 'name' => 'array|after:2020-02-29', 'age' => 'max:5|max:-1'], ['email' => ['The email field must be a date after 2020-02-29.', 'The email field must be an array.', 'The email field must be an integer.', 'The email field must be a valid date (YYYY-MM-DD).'], 'name' => ['The name field must be an array.', 'The name field must be a date after 2020-02-29.'], 'age' => ['The age field must not be greater than 5 characters.', 'The age field must not be greater than -1 characters.']]],
        [['age' => '  ', 'email' => 0, 'tags' => 0, 'items' => [], 'dob' => 'x@y', 'pw2' => 'é'], ['email' => 'numeric', 'items.*.qty' => 'in:1,2,3|min:2', 'name' => 'bail', 'dob' => 'int|in:1,2,3|between:2,6'], ['dob' => ['The dob field must be an integer.', 'The selected dob is invalid.']]],
        [['name' => 'a', 'age' => '123', 'tags' => '-4', 'items' => [['qty' => 'a@b.co']], 'dob' => false, 'pw2' => true], ['dob' => 'numeric', 'email' => 'between:2,6|max:5', 'pw2' => 'after:2020-02-29|numeric|required|date', 'items.*.qty' => 'in:1,2,3|int|email|email'], ['dob' => ['The dob field must be a number.'], 'pw2' => ['The pw2 field must be a date after 2020-02-29.', 'The pw2 field must be a number.', 'The pw2 field must be a valid date (YYYY-MM-DD).'], 'items.0.qty' => ['The selected items.0.qty is invalid.', 'The items.0.qty field must be an integer.']]],
        [['email' => '-4', 'address' => ['city' => 'é'], 'items' => [['qty' => []], ['qty' => true]]], ['dob' => 'int|in:1,2,3'], []],
        [['name' => '4.5', 'age' => '007', 'email' => 'a', 'tags' => '日本', 'address' => ['city' => 'abc'], 'items' => [], 'pw2' => 'a'], ['email' => 'in:a,bb,ccc'], []],
        [['name' => 'é', 'age' => '2019-03-01', 'email' => '  ', 'items' => [['qty' => 'abc']], 'dob' => false, 'pw2' => '2019-03-01'], ['email' => 'max:10|numeric'], ['email' => ['The email field must be a number.']]],
        [['name' => '', 'age' => false, 'email' => '007', 'items' => [['qty' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], ['qty' => '  '], ['qty' => '007']], 'pw2' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], ['name' => 'same:name|min:0.5|bail|same:name'], ['name' => ['The name field must be at least 0.5 characters.']]],
        [['name' => '2024-02-29', 'age' => 'é', 'email' => 'a@b.co', 'address' => ['city' => '日本'], 'dob' => 12], ['tags' => 'email|required'], ['tags' => ['The tags field is required.']]],
        [['name' => ['k' => 1], 'age' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'email' => 12, 'tags' => 2.5, 'address' => ['city' => 2.5], 'pw2' => '007'], ['pw2' => ['regex:/^[a-z]+$/'], 'age' => 'min:3'], ['pw2' => ['The pw2 field format is invalid.']]],
        [['name' => true, 'age' => '-4', 'email' => -3, 'address' => ['city' => 12], 'items' => [], 'dob' => 0, 'pw2' => []], ['name' => 'same:name', 'pw2' => 'max:-1'], ['pw2' => ['The pw2 field must not have more than -1 items.']]],
        [['age' => 'abcdef', 'email' => 'é', 'address' => ['city' => -3], 'items' => [['qty' => 2.5]], 'dob' => '007', 'pw2' => 'abcdef'], ['pw2' => 'min:2|numeric|int|array', 'address.city' => ['in:a,bb,ccc', 'in:1,2,3', 'regex:/^[a-z]+$/', 'after:2020-02-29']], ['pw2' => ['The pw2 field must be a number.', 'The pw2 field must be an integer.', 'The pw2 field must be an array.'], 'address.city' => ['The selected address.city is invalid.', 'The selected address.city is invalid.', 'The address.city field format is invalid.', 'The address.city field must be a date after 2020-02-29.']]],
        [['name' => 2.5, 'age' => '123', 'tags' => 2.5, 'items' => [['qty' => true]], 'dob' => 12, 'pw2' => 'abc'], ['name' => 'required|max:5|array|max:-1'], ['name' => ['The name field must be an array.', 'The name field must not be greater than -1 characters.']]],
        [['age' => 12, 'email' => '', 'tags' => 'a', 'address' => ['city' => '123'], 'items' => [['qty' => 'abcdef'], ['qty' => 'abc'], ['qty' => ['a', 'b']]], 'dob' => 1, 'pw2' => ''], ['pw2' => 'between:2,6|in:1,2,3|min:0.5'], ['pw2' => ['The pw2 field must be between 2 and 6 characters.', 'The selected pw2 is invalid.', 'The pw2 field must be at least 0.5 characters.']]],
        [['age' => 'a', 'email' => '@', 'tags' => ['a', 'b'], 'dob' => ['k' => 1]], ['age' => 'int|array', 'items.*.qty' => 'numeric|numeric|numeric|after:2020-02-29'], ['age' => ['The age field must be an integer.', 'The age field must be an array.']]],
        [['name' => '日本', 'age' => '2019-03-01', 'email' => true, 'tags' => 2.5, 'address' => 12, 'dob' => '-4', 'pw2' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], ['address.city' => 'bail|min:3', 'tags' => 'required|max:-1|numeric', 'age' => 'in:a,bb,ccc|max:-1', 'email' => 'max:10'], ['tags' => ['The tags field must not be greater than -1.'], 'age' => ['The selected age is invalid.', 'The age field must not be greater than -1 characters.']]],
        [['name' => 'x@y', 'age' => true, 'email' => '@', 'tags' => '007', 'address' => ['city' => -3], 'dob' => 12], ['pw2' => 'min:0.5|date'], []],
        [['name' => false, 'age' => -3, 'email' => '4.5', 'address' => ['city' => false], 'items' => [['qty' => '日本'], ['qty' => 'abc'], ['qty' => ['k' => 1]]], 'dob' => 1, 'pw2' => '2019-03-01'], ['age' => ['regex:/^[a-z]+$/', 'same:name']], ['age' => ['The age field format is invalid.', 'The age field must match name.']]],
        [['name' => false, 'age' => ['a', 'b'], 'email' => '@', 'tags' => 'a@b.co', 'address' => ['city' => 'x@y'], 'items' => [['qty' => 0], ['qty' => '  ']], 'dob' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'pw2' => '@'], ['email' => 'after:2020-02-29|min:0.5|min:3|min:3'], ['email' => ['The email field must be a date after 2020-02-29.', 'The email field must be at least 3 characters.', 'The email field must be at least 3 characters.']]],
        [['name' => false, 'address' => 1, 'items' => []], ['dob' => 'int|int', 'email' => 'bail|numeric', 'items.*.qty' => ['max:-1', 'regex:/^[a-z]+$/', 'max:5', 'regex:/^[a-z]+$/'], 'name' => 'max:5'], []],
        [['name' => '2019-03-01', 'age' => 'é', 'email' => '007', 'tags' => ['k' => 1], 'address' => ['city' => null], 'pw2' => '@'], ['pw2' => ['bail', 'max:5', 'required', 'regex:/^[a-z]+$/']], ['pw2' => ['The pw2 field format is invalid.']]],
        [['name' => ['a', 'b'], 'email' => '2019-03-01', 'dob' => '007', 'pw2' => -3], ['name' => 'string|max:10', 'email' => 'email|string|min:0.5'], ['name' => ['The name field must be a string.'], 'email' => ['The email field must be a valid email address.']]],
        [['name' => '2024-02-29', 'age' => '2019-03-01', 'email' => 2.5, 'tags' => -3, 'address' => ['a', 'b'], 'items' => [['qty' => -3], ['qty' => -3], ['qty' => 'x@y']], 'pw2' => '2019-03-01'], ['email' => 'after:2020-02-29', 'pw2' => ['regex:/^[a-z]+$/'], 'tags' => ['regex:/^[a-z]+$/', 'max:10', 'required', 'numeric']], ['email' => ['The email field must be a date after 2020-02-29.'], 'pw2' => ['The pw2 field format is invalid.'], 'tags' => ['The tags field format is invalid.']]],
        [['name' => ['a', 'b'], 'age' => true, 'tags' => 2.5, 'address' => ['city' => 0], 'items' => [['qty' => -3], ['qty' => '4.5']], 'dob' => '  ', 'pw2' => '@'], ['age' => 'between:2,6'], ['age' => ['The age field must be between 2 and 6 characters.']]],
        [['name' => '', 'age' => 'a@b.co', 'tags' => 0, 'address' => ['city' => '007'], 'items' => [['qty' => '@']], 'pw2' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], ['pw2' => 'email|min:0.5|max:-1', 'dob' => 'int|string', 'tags' => 'date|numeric|in:a,bb,ccc|string'], ['pw2' => ['The pw2 field must be a valid email address.', 'The pw2 field must not have more than -1 items.'], 'tags' => ['The tags field must be a valid date (YYYY-MM-DD).', 'The selected tags is invalid.', 'The tags field must be a string.']]],
        [['name' => true, 'email' => [], 'tags' => false, 'address' => ['city' => 'abc'], 'items' => [['qty' => '日本'], ['qty' => 1]], 'dob' => '', 'pw2' => 'x@y'], ['name' => 'array'], ['name' => ['The name field must be an array.']]],
        [['name' => '123', 'age' => '@', 'email' => [1], 'tags' => '日本', 'address' => '日本', 'items' => 2.5, 'dob' => 'x@y', 'pw2' => 0], ['items.*.qty' => 'in:1,2,3', 'email' => 'after:2020-02-29', 'tags' => 'date|in:1,2,3'], ['email' => ['The email field must be a date after 2020-02-29.'], 'tags' => ['The tags field must be a valid date (YYYY-MM-DD).', 'The selected tags is invalid.']]],
        [['name' => [], 'age' => 'abcdef', 'email' => true, 'address' => ['city' => -3], 'items' => 0], ['age' => 'email', 'email' => 'in:a,bb,ccc|max:10|max:-1', 'items.*.qty' => 'same:name|array', 'name' => 'email|min:0.5|email|date'], ['age' => ['The age field must be a valid email address.'], 'email' => ['The selected email is invalid.', 'The email field must not be greater than -1 characters.'], 'name' => ['The name field must be a valid email address.', 'The name field must have at least 0.5 items.', 'The name field must be a valid email address.', 'The name field must be a valid date (YYYY-MM-DD).']]],
        [['name' => 'abc', 'age' => null, 'email' => 'abc', 'tags' => '4.5', 'address' => ['city' => '2024-02-29'], 'dob' => '123', 'pw2' => '  '], ['age' => ['numeric', 'regex:/^[a-z]+$/'], 'name' => 'after:2020-02-29', 'email' => 'array|int|max:5'], ['name' => ['The name field must be a date after 2020-02-29.'], 'email' => ['The email field must be an array.', 'The email field must be an integer.']]],
        [['name' => null, 'age' => 2.5, 'email' => ['a', 'b'], 'tags' => 'x', 'items' => [], 'dob' => true], ['age' => 'numeric|email', 'pw2' => 'string|min:2', 'tags' => 'in:1,2,3|email'], ['age' => ['The age field must be a valid email address.'], 'tags' => ['The selected tags is invalid.', 'The tags field must be a valid email address.']]],
        [['name' => '4.5', 'age' => null, 'email' => ['a', 'b'], 'tags' => '4.5', 'items' => [['qty' => []]]], ['tags' => 'date|array'], ['tags' => ['The tags field must be a valid date (YYYY-MM-DD).', 'The tags field must be an array.']]],
        [['name' => '4.5', 'age' => -3, 'email' => -3, 'address' => ['city' => null], 'items' => [['qty' => '  '], ['qty' => 0], ['qty' => true]]], ['address.city' => 'in:a,bb,ccc|max:10|max:10'], []],
        [['name' => '-4', 'email' => '123', 'tags' => 'abcdef', 'address' => ['city' => 'a@b.co'], 'dob' => 12], ['tags' => ['max:10', 'max:5', 'regex:/^[a-z]+$/', 'string'], 'email' => ['regex:/^[a-z]+$/']], ['tags' => ['The tags field must not be greater than 5 characters.'], 'email' => ['The email field format is invalid.']]],
        [['name' => 1, 'email' => 0, 'items' => [['qty' => [1]], ['qty' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']]], 'dob' => -3, 'pw2' => ['k' => 1]], ['dob' => 'max:10|min:3|bail|in:1,2,3', 'name' => 'array', 'email' => 'int|required', 'age' => 'same:name'], ['dob' => ['The dob field must be at least 3 characters.', 'The selected dob is invalid.'], 'name' => ['The name field must be an array.']]],
        [['age' => 'abc', 'email' => 2.5, 'tags' => '  ', 'pw2' => 'abcdef'], ['tags' => 'date', 'age' => 'min:2|after:2020-02-29|max:10|in:a,bb,ccc', 'items.*.qty' => 'string|between:2,6'], ['tags' => ['The tags field must be a valid date (YYYY-MM-DD).'], 'age' => ['The age field must be a date after 2020-02-29.', 'The selected age is invalid.']]],
        [['name' => 'x@y', 'age' => '007', 'address' => '2019-03-01', 'items' => [['qty' => '123']], 'dob' => false, 'pw2' => '007'], ['email' => 'date', 'dob' => ['max:5', 'regex:/^[a-z]+$/'], 'items.*.qty' => 'min:0.5|same:name'], ['dob' => ['The dob field format is invalid.'], 'items.0.qty' => ['The items.0.qty field must match name.']]],
        [['name' => 'x@y', 'age' => '2019-03-01', 'tags' => 'x@y', 'address' => ['city' => '日本'], 'dob' => 'x@y', 'pw2' => ['k' => 1]], ['age' => 'max:5|int|max:-1', 'pw2' => 'after:2020-02-29', 'dob' => 'bail|date|between:2,6', 'name' => 'int|max:-1|date|min:3'], ['age' => ['The age field must be an integer.'], 'pw2' => ['The pw2 field must be a date after 2020-02-29.'], 'dob' => ['The dob field must be a valid date (YYYY-MM-DD).'], 'name' => ['The name field must be an integer.', 'The name field must be a valid date (YYYY-MM-DD).']]],
        [['name' => false, 'age' => ['k' => 1], 'tags' => ['a', 'b'], 'address' => ['city' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']]], ['age' => 'min:2|max:-1', 'pw2' => ['email', 'regex:/^[a-z]+$/'], 'email' => ['regex:/^[a-z]+$/', 'numeric'], 'dob' => 'max:5|string|min:2|bail'], ['age' => ['The age field must have at least 2 items.', 'The age field must not have more than -1 items.']]],
        [['name' => false, 'email' => '123', 'tags' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'address' => ['city' => '4.5'], 'items' => [], 'pw2' => 'a@b.co'], ['pw2' => 'required', 'dob' => ['email', 'same:name', 'regex:/^[a-z]+$/', 'min:0.5'], 'email' => 'in:1,2,3|max:10|min:3|max:5'], ['email' => ['The selected email is invalid.']]],
        [['email' => ['a', 'b'], 'tags' => -3, 'address' => ['city' => '日本'], 'items' => ['a', 'b']], ['address.city' => 'int|bail|after:2020-02-29|in:1,2,3', 'dob' => 'array'], ['address.city' => ['The address.city field must be an integer.', 'The address.city field must be a date after 2020-02-29.']]],
        [['name' => '2019-03-01', 'age' => 'abc', 'email' => '  ', 'address' => ['city' => 'abc'], 'items' => [['qty' => 'é'], ['qty' => 0], ['qty' => 'abc']], 'pw2' => '2024-02-29'], ['email' => 'min:3|min:3', 'items.*.qty' => 'max:10', 'address.city' => 'max:-1', 'tags' => 'bail|numeric|array'], ['email' => ['The email field must be at least 3 characters.', 'The email field must be at least 3 characters.'], 'address.city' => ['The address.city field must not be greater than -1 characters.']]],
        [['name' => '007', 'age' => ['a', 'b'], 'email' => 'x@y', 'tags' => '  ', 'items' => [['qty' => '4.5'], ['qty' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']]], 'dob' => 2.5, 'pw2' => '007'], ['pw2' => 'bail|string', 'dob' => 'between:2,6|after:2020-02-29'], ['dob' => ['The dob field must be a date after 2020-02-29.']]],
        [['address' => ['city' => 'a'], 'items' => [['qty' => '007'], ['qty' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']]], 'dob' => '@', 'pw2' => 'abcdef'], ['tags' => 'max:5|required|same:name', 'dob' => 'numeric|max:-1'], ['tags' => ['The tags field is required.'], 'dob' => ['The dob field must be a number.']]],
        [['email' => '123', 'tags' => '123', 'dob' => '-4'], ['pw2' => 'min:2|min:0.5|max:10|min:3'], []],
        [['name' => 'abcdef', 'age' => null, 'email' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'address' => ['city' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], 'items' => '2019-03-01', 'dob' => '4.5'], ['name' => 'string|min:0.5'], []],
        [['name' => ['k' => 1], 'age' => '', 'email' => 2.5, 'tags' => '123', 'items' => [], 'pw2' => false], ['tags' => ['regex:/^[a-z]+$/', 'bail', 'in:1,2,3'], 'pw2' => 'after:2020-02-29|max:5|max:5|string'], ['tags' => ['The tags field format is invalid.', 'The selected tags is invalid.'], 'pw2' => ['The pw2 field must be a date after 2020-02-29.', 'The pw2 field must be a string.']]],
        [['age' => true, 'email' => 'abcdef', 'tags' => [1], 'address' => ['city' => '007'], 'items' => [], 'pw2' => ['a', 'b']], ['tags' => 'max:-1'], ['tags' => ['The tags field must not have more than -1 items.']]],
        [['age' => '-4', 'address' => ['city' => [1]], 'items' => [['qty' => '  ']], 'dob' => '日本'], ['email' => 'in:a,bb,ccc|max:5|min:3'], []],
        [['name' => 12, 'age' => [], 'email' => 'é', 'tags' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'address' => ['city' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], 'items' => [['qty' => 'a']], 'dob' => 'abcdef', 'pw2' => 1], ['name' => 'max:-1|min:0.5|email', 'email' => ['regex:/^[a-z]+$/', 'min:2', 'array', 'max:5']], ['name' => ['The name field must not be greater than -1 characters.', 'The name field must be a valid email address.'], 'email' => ['The email field format is invalid.', 'The email field must be at least 2 characters.', 'The email field must be an array.']]],
        [['age' => -3, 'address' => ['city' => 0], 'items' => []], ['email' => 'bail', 'tags' => 'same:name|max:5|numeric', 'dob' => 'min:3|max:5|max:10', 'name' => 'min:0.5|in:1,2,3|between:2,6|bail'], []],
        [['age' => '2019-03-01', 'email' => '  ', 'tags' => '2024-02-29', 'address' => ['city' => 2.5], 'dob' => -3, 'pw2' => '日本'], ['age' => 'min:2|required|max:5'], ['age' => ['The age field must not be greater than 5 characters.']]],
        [['name' => 'a@b.co', 'email' => true, 'tags' => ['a', 'b'], 'items' => [['qty' => '007'], ['qty' => 'x@y']], 'dob' => ['a', 'b'], 'pw2' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], ['tags' => 'int', 'items.*.qty' => 'min:0.5', 'age' => 'between:2,6|string|between:2,6|same:name'], ['tags' => ['The tags field must be an integer.']]],
        [['name' => [1], 'age' => '4.5', 'email' => 12, 'address' => ['city' => '4.5'], 'items' => [['qty' => 1], ['qty' => '2024-02-29']], 'dob' => '-4', 'pw2' => '-4'], ['age' => 'int|email|numeric|between:2,6', 'items.*.qty' => 'min:3|max:10|between:2,6|email', 'email' => 'max:-1|email'], ['age' => ['The age field must be an integer.', 'The age field must be a valid email address.'], 'items.0.qty' => ['The items.0.qty field must be at least 3 characters.', 'The items.0.qty field must be between 2 and 6 characters.', 'The items.0.qty field must be a valid email address.'], 'items.1.qty' => ['The items.1.qty field must be between 2 and 6 characters.', 'The items.1.qty field must be a valid email address.'], 'email' => ['The email field must not be greater than -1 characters.', 'The email field must be a valid email address.']]],
        [['name' => 'é', 'age' => '@', 'email' => 2.5, 'tags' => false, 'address' => ['city' => '日本'], 'dob' => 2.5, 'pw2' => '007'], ['address.city' => 'required|min:2|in:a,bb,ccc', 'name' => 'required|same:name|min:2|in:a,bb,ccc', 'age' => 'bail|max:10|string', 'items.*.qty' => 'min:3|max:-1|same:name'], ['address.city' => ['The selected address.city is invalid.'], 'name' => ['The name field must be at least 2 characters.', 'The selected name is invalid.']]],
        [['name' => [], 'email' => ['k' => 1], 'address' => ['city' => ['a', 'b']], 'dob' => '007', 'pw2' => '2019-03-01'], ['age' => 'string|numeric|date|max:5', 'address.city' => 'bail', 'dob' => 'between:2,6|date'], ['dob' => ['The dob field must be a valid date (YYYY-MM-DD).']]],
        [['name' => 'abc', 'age' => ['k' => 1], 'tags' => true, 'address' => ['city' => [1]], 'items' => [['qty' => ''], ['qty' => false], ['qty' => '  ']], 'dob' => 2.5], ['name' => 'max:-1|min:3|min:2', 'items.*.qty' => 'max:10|date|int|min:2'], ['name' => ['The name field must not be greater than -1 characters.'], 'items.0.qty' => ['The items.0.qty field must be a valid date (YYYY-MM-DD).', 'The items.0.qty field must be an integer.'], 'items.1.qty' => ['The items.1.qty field must be a valid date (YYYY-MM-DD).', 'The items.1.qty field must be an integer.'], 'items.2.qty' => ['The items.2.qty field must be a valid date (YYYY-MM-DD).', 'The items.2.qty field must be an integer.']]],
        [['name' => 'a', 'items' => [], 'dob' => '@', 'pw2' => 1], ['email' => 'min:2|min:3'], []],
        [['age' => 2.5, 'email' => 'a@b.co', 'address' => 1, 'dob' => true, 'pw2' => '2019-03-01'], ['tags' => 'max:10|min:0.5|min:2|min:3', 'items.*.qty' => 'max:10|max:5'], []],
        [['name' => '007', 'age' => false, 'email' => -3, 'tags' => false, 'dob' => '日本', 'pw2' => ['k' => 1]], ['pw2' => 'between:2,6|min:0.5|same:name|min:3', 'address.city' => 'email|between:2,6|max:-1', 'tags' => 'string|max:10'], ['pw2' => ['The pw2 field must have between 2 and 6 items.', 'The pw2 field must match name.', 'The pw2 field must have at least 3 items.'], 'tags' => ['The tags field must be a string.']]],
        [['name' => 'a', 'age' => 'abcdef', 'tags' => '', 'pw2' => '2019-03-01'], ['items.*.qty' => 'between:2,6|required', 'name' => 'between:2,6|max:10|max:-1|int', 'email' => ['regex:/^[a-z]+$/']], ['name' => ['The name field must be an integer.']]],
        [['name' => '123', 'age' => -3, 'items' => [['qty' => '']], 'dob' => null, 'pw2' => 'a@b.co'], ['name' => 'between:2,6', 'tags' => 'min:0.5|string|same:name|max:-1'], []],
        [['email' => 'abc', 'tags' => 'x', 'address' => ['city' => 'x@y'], 'items' => [['qty' => '@'], ['qty' => '123'], ['qty' => ['a', 'b']]], 'dob' => '@'], ['dob' => 'max:5|max:-1', 'address.city' => 'max:5', 'tags' => ['regex:/^[a-z]+$/', 'date', 'min:2']], ['dob' => ['The dob field must not be greater than -1 characters.'], 'tags' => ['The tags field must be a valid date (YYYY-MM-DD).', 'The tags field must be at least 2 characters.']]],
        [['age' => '', 'email' => 'x', 'tags' => '  ', 'address' => ['city' => 'a@b.co'], 'pw2' => [1]], ['dob' => ['bail', 'in:1,2,3', 'regex:/^[a-z]+$/'], 'items.*.qty' => 'min:2', 'age' => ['regex:/^[a-z]+$/', 'date'], 'email' => 'in:1,2,3|min:3'], ['age' => ['The age field format is invalid.', 'The age field must be a valid date (YYYY-MM-DD).'], 'email' => ['The selected email is invalid.', 'The email field must be at least 3 characters.']]],
        [['address' => '007', 'items' => [['qty' => ['a', 'b']]], 'pw2' => 'a@b.co'], ['name' => 'int|in:a,bb,ccc|min:0.5|max:10', 'tags' => 'same:name|int|array|required', 'email' => 'between:2,6|same:name'], ['tags' => ['The tags field is required.']]],
        [['age' => '日本', 'address' => ['city' => [1]], 'items' => true, 'dob' => '2024-02-29', 'pw2' => -3], ['email' => 'bail|min:0.5|between:2,6|same:name', 'pw2' => 'min:2', 'address.city' => 'bail|required|between:2,6|after:2020-02-29'], ['address.city' => ['The address.city field must have between 2 and 6 items.']]],
        [['name' => '2024-02-29', 'age' => 'abcdef', 'email' => 'a', 'tags' => -3, 'items' => [['qty' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']]], 'pw2' => 'x@y'], ['age' => 'between:2,6|in:1,2,3', 'address.city' => 'numeric'], ['age' => ['The selected age is invalid.']]],
        [['age' => null, 'email' => 0, 'address' => ['city' => '@'], 'items' => [['qty' => ['a', 'b']]], 'dob' => ['a', 'b'], 'pw2' => ['a', 'b']], ['age' => 'in:1,2,3', 'email' => 'in:1,2,3|between:2,6|numeric', 'items.*.qty' => 'between:2,6|max:-1', 'tags' => 'required|min:2|string|int'], ['email' => ['The selected email is invalid.', 'The email field must be between 2 and 6.'], 'items.0.qty' => ['The items.0.qty field must not have more than -1 items.'], 'tags' => ['The tags field is required.']]],
        [['name' => '@', 'email' => 12, 'address' => ['city' => true], 'dob' => '123', 'pw2' => '@'], ['dob' => 'between:2,6|required|max:-1'], ['dob' => ['The dob field must not be greater than -1 characters.']]],
        [['name' => '123', 'age' => true, 'tags' => ['a', 'b'], 'address' => ['city' => '@'], 'items' => [['qty' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']]], 'dob' => 2.5], ['address.city' => 'max:-1|between:2,6|in:a,bb,ccc', 'tags' => 'date|string|between:2,6|date', 'email' => 'in:a,bb,ccc', 'items.*.qty' => 'required|array|max:-1|min:3'], ['address.city' => ['The address.city field must not be greater than -1 characters.', 'The address.city field must be between 2 and 6 characters.', 'The selected address.city is invalid.'], 'tags' => ['The tags field must be a valid date (YYYY-MM-DD).', 'The tags field must be a string.', 'The tags field must be a valid date (YYYY-MM-DD).'], 'items.0.qty' => ['The items.0.qty field must not have more than -1 items.']]],
        [['name' => 'a@b.co', 'age' => 2.5, 'tags' => 1, 'address' => ['city' => 'a@b.co'], 'dob' => true, 'pw2' => '-4'], ['dob' => 'date', 'name' => 'in:1,2,3', 'age' => 'string|min:2|required'], ['dob' => ['The dob field must be a valid date (YYYY-MM-DD).'], 'name' => ['The selected name is invalid.'], 'age' => ['The age field must be a string.']]],
        [['tags' => '007', 'address' => ['city' => '2019-03-01'], 'items' => [], 'dob' => '123', 'pw2' => 12], ['address.city' => 'max:5|max:-1', 'age' => 'int'], ['address.city' => ['The address.city field must not be greater than 5 characters.', 'The address.city field must not be greater than -1 characters.']]],
        [['name' => '  ', 'email' => ['k' => 1], 'tags' => ['a', 'b'], 'address' => 'a', 'items' => [], 'pw2' => 2.5], ['name' => 'in:1,2,3|email|min:3|max:-1'], ['name' => ['The selected name is invalid.', 'The name field must be a valid email address.', 'The name field must be at least 3 characters.', 'The name field must not be greater than -1 characters.']]],
        [['name' => null, 'age' => 0, 'address' => ['city' => []], 'items' => -3, 'pw2' => 0], ['name' => 'same:name|in:1,2,3'], []],
        [['name' => -3, 'age' => ['a', 'b'], 'tags' => null, 'address' => ['city' => ['k' => 1]], 'dob' => '日本'], ['address.city' => 'same:name|email|array', 'dob' => 'max:-1|numeric|date'], ['address.city' => ['The address.city field must match name.', 'The address.city field must be a valid email address.'], 'dob' => ['The dob field must be a number.', 'The dob field must be a valid date (YYYY-MM-DD).']]],
        [['email' => [], 'tags' => '4.5', 'address' => ['city' => ''], 'items' => 1, 'dob' => '日本', 'pw2' => true], ['dob' => 'min:2', 'name' => 'min:3', 'pw2' => 'max:10|max:10|numeric', 'tags' => 'string'], ['pw2' => ['The pw2 field must be a number.']]],
        [['name' => false, 'email' => '4.5', 'tags' => 'abcdef', 'items' => [['qty' => []], ['qty' => ''], ['qty' => [1]]], 'dob' => '  ', 'pw2' => '@'], ['dob' => 'bail|date|between:2,6'], ['dob' => ['The dob field must be a valid date (YYYY-MM-DD).']]],
        [['age' => '', 'email' => 0, 'address' => ['city' => ['a', 'b']], 'items' => [['qty' => '-4']]], ['dob' => 'in:1,2,3|int|min:0.5'], []],
        [['age' => 'abc', 'email' => 'x@y', 'tags' => 'é', 'address' => ['city' => 1]], ['pw2' => ['in:1,2,3', 'after:2020-02-29', 'max:10', 'regex:/^[a-z]+$/'], 'email' => 'min:3|email|email', 'age' => 'max:5|email|bail|min:0.5', 'dob' => ['required', 'min:3', 'regex:/^[a-z]+$/', 'after:2020-02-29']], ['email' => ['The email field must be a valid email address.', 'The email field must be a valid email address.'], 'age' => ['The age field must be a valid email address.'], 'dob' => ['The dob field is required.']]],
        [['name' => [1], 'age' => ['a', 'b'], 'email' => ['k' => 1], 'tags' => 'é', 'address' => ['city' => ['k' => 1]], 'dob' => '123'], ['dob' => 'string|numeric', 'pw2' => 'numeric', 'address.city' => 'between:2,6|between:2,6'], ['address.city' => ['The address.city field must have between 2 and 6 items.', 'The address.city field must have between 2 and 6 items.']]],
        [['name' => ['k' => 1], 'age' => '4.5', 'email' => '123', 'tags' => '-4', 'address' => '123', 'items' => [['qty' => '-4'], ['qty' => 'abcdef'], ['qty' => 2.5]], 'dob' => 1], ['dob' => ['regex:/^[a-z]+$/', 'numeric', 'email'], 'name' => 'min:0.5|array', 'age' => ['regex:/^[a-z]+$/', 'min:3', 'max:5', 'max:10'], 'items.*.qty' => 'min:3|array|max:5|bail'], ['dob' => ['The dob field format is invalid.', 'The dob field must be a valid email address.'], 'age' => ['The age field format is invalid.'], 'items.0.qty' => ['The items.0.qty field must be at least 3 characters.', 'The items.0.qty field must be an array.'], 'items.1.qty' => ['The items.1.qty field must be an array.', 'The items.1.qty field must not be greater than 5 characters.'], 'items.2.qty' => ['The items.2.qty field must be an array.']]],
        [['name' => 'a@b.co', 'age' => '日本', 'tags' => '123', 'items' => [['qty' => '4.5']], 'dob' => '日本', 'pw2' => 'abcdef'], ['dob' => ['regex:/^[a-z]+$/', 'min:3'], 'age' => 'numeric|in:1,2,3|required', 'address.city' => ['in:1,2,3', 'in:a,bb,ccc', 'regex:/^[a-z]+$/', 'min:0.5'], 'email' => 'int|max:5'], ['dob' => ['The dob field format is invalid.', 'The dob field must be at least 3 characters.'], 'age' => ['The age field must be a number.', 'The selected age is invalid.']]],
        [['name' => [], 'tags' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'address' => null, 'dob' => 'é', 'pw2' => null], ['pw2' => ['after:2020-02-29', 'required', 'min:3', 'regex:/^[a-z]+$/'], 'items.*.qty' => 'same:name'], ['pw2' => ['The pw2 field is required.']]],
        [['age' => '123', 'email' => '日本', 'address' => ['city' => 2.5], 'dob' => [1], 'pw2' => 'abcdef'], ['email' => 'in:a,bb,ccc|bail|numeric|between:2,6', 'pw2' => 'numeric|required|min:3|email'], ['email' => ['The selected email is invalid.', 'The email field must be a number.'], 'pw2' => ['The pw2 field must be a number.', 'The pw2 field must be a valid email address.']]],
        [['name' => 12, 'age' => '2024-02-29', 'address' => '-4', 'items' => [['qty' => -3]], 'dob' => '-4', 'pw2' => -3], ['address.city' => 'bail|after:2020-02-29|array', 'age' => 'after:2020-02-29|numeric', 'email' => ['after:2020-02-29', 'min:3', 'array', 'regex:/^[a-z]+$/']], ['age' => ['The age field must be a number.']]],
        [['age' => 'abcdef', 'email' => '日本', 'tags' => '日本', 'address' => ['city' => [1]], 'items' => []], ['age' => 'max:5'], ['age' => ['The age field must not be greater than 5 characters.']]],
        [['age' => 'abc', 'address' => ['city' => '2019-03-01'], 'items' => [['qty' => 'abc'], ['qty' => '  ']], 'pw2' => [1]], ['tags' => ['after:2020-02-29', 'between:2,6', 'regex:/^[a-z]+$/', 'regex:/^[a-z]+$/'], 'pw2' => 'between:2,6|max:10|max:10', 'age' => 'in:a,bb,ccc|same:name|numeric|min:0.5'], ['pw2' => ['The pw2 field must have between 2 and 6 items.'], 'age' => ['The selected age is invalid.', 'The age field must match name.', 'The age field must be a number.']]],
        [['name' => -3, 'email' => null, 'tags' => 12, 'items' => 12, 'dob' => '4.5', 'pw2' => ''], ['pw2' => 'int', 'tags' => 'int|min:3|string', 'email' => 'date|min:2|min:3|bail', 'dob' => 'email|email'], ['pw2' => ['The pw2 field must be an integer.'], 'tags' => ['The tags field must be a string.'], 'dob' => ['The dob field must be a valid email address.', 'The dob field must be a valid email address.']]],
        [['name' => '日本', 'age' => 2.5, 'tags' => '-4', 'address' => ['city' => 'abcdef'], 'items' => [['qty' => -3], ['qty' => []], ['qty' => '']], 'pw2' => 'é'], ['email' => 'max:5', 'pw2' => 'email|numeric|after:2020-02-29|min:2', 'name' => 'int'], ['pw2' => ['The pw2 field must be a valid email address.', 'The pw2 field must be a number.', 'The pw2 field must be a date after 2020-02-29.'], 'name' => ['The name field must be an integer.']]],
        [['age' => '', 'email' => '  ', 'tags' => true, 'items' => [['qty' => 'x'], ['qty' => '-4'], ['qty' => 'x']], 'pw2' => 'abcdef'], ['age' => 'array|after:2020-02-29|min:3|between:2,6', 'address.city' => 'min:3|max:10', 'pw2' => 'numeric|after:2020-02-29|bail', 'items.*.qty' => 'in:1,2,3|in:1,2,3'], ['age' => ['The age field must be an array.', 'The age field must be a date after 2020-02-29.', 'The age field must be at least 3 characters.', 'The age field must be between 2 and 6 characters.'], 'pw2' => ['The pw2 field must be a number.', 'The pw2 field must be a date after 2020-02-29.'], 'items.0.qty' => ['The selected items.0.qty is invalid.', 'The selected items.0.qty is invalid.'], 'items.1.qty' => ['The selected items.1.qty is invalid.', 'The selected items.1.qty is invalid.'], 'items.2.qty' => ['The selected items.2.qty is invalid.', 'The selected items.2.qty is invalid.']]],
        [['address' => ['city' => '  '], 'dob' => -3, 'pw2' => 'abc'], ['tags' => ['same:name', 'min:3', 'regex:/^[a-z]+$/', 'between:2,6'], 'age' => 'bail|int|max:5'], []],
        [['age' => true, 'email' => ['k' => 1], 'address' => ['city' => -3], 'dob' => '123', 'pw2' => 0], ['dob' => 'same:name|int'], ['dob' => ['The dob field must match name.']]],
        [['name' => '4.5', 'age' => ['a', 'b'], 'address' => ['city' => 'a'], 'items' => 2.5, 'dob' => '4.5', 'pw2' => -3], ['email' => 'max:5|max:10|max:5', 'address.city' => ['email', 'regex:/^[a-z]+$/']], ['address.city' => ['The address.city field must be a valid email address.']]],
        [['name' => null, 'email' => -3, 'tags' => 'é', 'address' => ['city' => []], 'pw2' => 'abc'], ['pw2' => 'int|max:-1|min:2|after:2020-02-29', 'dob' => 'in:1,2,3|array|min:2|min:3'], ['pw2' => ['The pw2 field must be an integer.', 'The pw2 field must be a date after 2020-02-29.']]],
        [['name' => 'a', 'email' => [1], 'address' => ['city' => 'x@y'], 'items' => [['qty' => '123'], ['qty' => false], ['qty' => 'x@y']], 'pw2' => []], ['items.*.qty' => 'string|email|required|bail', 'name' => ['string', 'in:1,2,3', 'regex:/^[a-z]+$/', 'email']], ['items.0.qty' => ['The items.0.qty field must be a valid email address.'], 'items.1.qty' => ['The items.1.qty field must be a string.', 'The items.1.qty field must be a valid email address.'], 'items.2.qty' => ['The items.2.qty field must be a valid email address.'], 'name' => ['The selected name is invalid.', 'The name field must be a valid email address.']]],
        [['name' => '4.5', 'email' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'tags' => 1, 'address' => ['city' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], 'items' => [], 'dob' => '2024-02-29', 'pw2' => 'x@y'], ['items.*.qty' => 'max:5', 'email' => 'bail', 'address.city' => 'int|email|bail', 'name' => 'email|max:-1|between:2,6|same:name'], ['address.city' => ['The address.city field must be an integer.', 'The address.city field must be a valid email address.'], 'name' => ['The name field must be a valid email address.', 'The name field must not be greater than -1 characters.']]],
        [['name' => '4.5', 'age' => '2019-03-01', 'email' => ['k' => 1], 'address' => ['city' => '2019-03-01'], 'items' => [['qty' => '-4']], 'dob' => 'a@b.co'], ['items.*.qty' => 'bail|min:2', 'age' => ['regex:/^[a-z]+$/', 'after:2020-02-29', 'regex:/^[a-z]+$/'], 'tags' => 'after:2020-02-29'], ['age' => ['The age field format is invalid.', 'The age field must be a date after 2020-02-29.', 'The age field format is invalid.']]],
        [['age' => '2024-02-29', 'email' => 'a', 'tags' => '007', 'items' => [], 'pw2' => true], ['tags' => 'max:-1|max:-1', 'age' => 'required|int|date', 'address.city' => 'string'], ['tags' => ['The tags field must not be greater than -1 characters.', 'The tags field must not be greater than -1 characters.'], 'age' => ['The age field must be an integer.']]],
        [['name' => '123', 'age' => '2019-03-01', 'email' => '4.5', 'tags' => ['a', 'b'], 'items' => [['qty' => ['a', 'b']]], 'pw2' => '4.5'], ['email' => 'required|required|after:2020-02-29'], ['email' => ['The email field must be a date after 2020-02-29.']]],
        [['age' => '-4', 'email' => 'abc', 'address' => 'é', 'items' => [['qty' => null], ['qty' => -3], ['qty' => 'abcdef']], 'dob' => '@'], ['items.*.qty' => 'string|min:3|max:10'], ['items.1.qty' => ['The items.1.qty field must be a string.', 'The items.1.qty field must be at least 3 characters.']]],
        [['name' => 12, 'age' => true, 'email' => ['k' => 1], 'items' => [], 'dob' => 'a', 'pw2' => 'x'], ['pw2' => ['regex:/^[a-z]+$/', 'required'], 'name' => 'min:2', 'age' => 'bail|date'], ['age' => ['The age field must be a valid date (YYYY-MM-DD).']]],
        [['name' => [], 'age' => 2.5, 'email' => '  ', 'tags' => 'a', 'address' => [], 'items' => ['k' => 1], 'dob' => [1]], ['dob' => 'same:name', 'name' => 'bail|min:3|string|max:-1', 'pw2' => 'string|in:a,bb,ccc', 'age' => 'same:name|bail'], ['dob' => ['The dob field must match name.'], 'name' => ['The name field must have at least 3 items.'], 'age' => ['The age field must match name.']]],
        [['name' => 0, 'age' => 'a@b.co', 'email' => '2019-03-01', 'tags' => ['a', 'b'], 'address' => ['city' => true], 'dob' => '007', 'pw2' => 'a'], ['age' => 'same:name|same:name', 'address.city' => 'in:1,2,3|array', 'tags' => 'max:5', 'name' => ['max:-1', 'regex:/^[a-z]+$/', 'min:2']], ['age' => ['The age field must match name.', 'The age field must match name.'], 'address.city' => ['The address.city field must be an array.'], 'name' => ['The name field must not be greater than -1 characters.', 'The name field format is invalid.', 'The name field must be at least 2 characters.']]],
        [['name' => '123', 'tags' => '2024-02-29', 'address' => ['city' => true], 'items' => [['qty' => 'x']], 'pw2' => '4.5'], ['name' => 'bail|min:0.5', 'items.*.qty' => 'in:1,2,3'], ['items.0.qty' => ['The selected items.0.qty is invalid.']]],
        [['age' => '2019-03-01', 'email' => 'abcdef', 'address' => '007', 'items' => [['qty' => [1]], ['qty' => '  '], ['qty' => []]], 'dob' => 1], ['tags' => 'min:3|after:2020-02-29|date|string', 'age' => 'between:2,6|between:2,6|date|int', 'pw2' => 'date'], ['age' => ['The age field must be an integer.']]],
        [['name' => '-4', 'tags' => 'abcdef', 'address' => true], ['items.*.qty' => 'min:2|email'], []],
        [['name' => ['a', 'b'], 'email' => 'a@b.co', 'tags' => '  ', 'address' => ['city' => 2.5], 'items' => [['qty' => -3]], 'dob' => '4.5', 'pw2' => 'x@y'], ['dob' => 'bail|string|min:3|int'], ['dob' => ['The dob field must be an integer.']]],
        [['name' => 0, 'age' => 0, 'email' => 'x', 'address' => 'a@b.co', 'pw2' => 'abcdef'], ['email' => 'bail|numeric|array|in:a,bb,ccc'], ['email' => ['The email field must be a number.']]],
        [['age' => 2.5, 'tags' => 'a', 'dob' => '', 'pw2' => '2024-02-29'], ['name' => 'date|string|min:0.5|int', 'pw2' => 'after:2020-02-29|required|in:a,bb,ccc', 'email' => 'in:a,bb,ccc|bail|min:0.5'], ['pw2' => ['The selected pw2 is invalid.']]],
        [['name' => 'é', 'age' => 'x@y', 'tags' => 'é', 'address' => ['city' => '-4'], 'dob' => 'abc', 'pw2' => 12], ['age' => 'bail', 'name' => 'between:2,6', 'tags' => 'max:5|email', 'address.city' => 'in:1,2,3'], ['name' => ['The name field must be between 2 and 6 characters.'], 'tags' => ['The tags field must be a valid email address.'], 'address.city' => ['The selected address.city is invalid.']]],
        [['name' => 'é', 'age' => '4.5', 'email' => -3, 'tags' => [], 'address' => ['city' => ['a', 'b']], 'dob' => 12, 'pw2' => null], ['address.city' => 'array', 'email' => 'same:name', 'pw2' => ['email', 'after:2020-02-29', 'regex:/^[a-z]+$/', 'bail']], ['email' => ['The email field must match name.']]],
        [['name' => 'abc', 'age' => [1], 'address' => ['city' => 'a@b.co'], 'items' => [['qty' => 0], ['qty' => '123']], 'pw2' => null], ['dob' => 'bail|array', 'pw2' => 'email'], []],
        [['name' => 0, 'age' => 2.5, 'email' => '4.5', 'tags' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'items' => [], 'pw2' => 2.5], ['email' => 'between:2,6', 'pw2' => 'in:1,2,3|between:2,6|string', 'age' => 'between:2,6|date|numeric|email', 'tags' => 'bail|date'], ['pw2' => ['The selected pw2 is invalid.', 'The pw2 field must be a string.'], 'age' => ['The age field must be a valid date (YYYY-MM-DD).', 'The age field must be a valid email address.'], 'tags' => ['The tags field must be a valid date (YYYY-MM-DD).']]],
        [['name' => '4.5', 'tags' => null, 'items' => [['qty' => '2019-03-01']], 'dob' => [1]], ['items.*.qty' => ['date', 'bail', 'max:5', 'regex:/^[a-z]+$/'], 'name' => 'email|email|string|in:1,2,3', 'age' => 'min:2|min:3|max:-1'], ['items.0.qty' => ['The items.0.qty field must not be greater than 5 characters.'], 'name' => ['The name field must be a valid email address.', 'The name field must be a valid email address.', 'The selected name is invalid.']]],
        [['name' => [1], 'age' => [], 'email' => '2024-02-29', 'address' => ['city' => '日本'], 'items' => [['qty' => ['k' => 1]], ['qty' => 0], ['qty' => null]]], ['dob' => 'array|min:0.5|min:2|email', 'name' => 'int|numeric'], ['name' => ['The name field must be an integer.', 'The name field must be a number.']]],
        [['name' => '', 'age' => 'a', 'email' => 0, 'tags' => '  ', 'address' => ['city' => '4.5'], 'items' => [['qty' => 'a@b.co'], ['qty' => '  ']], 'dob' => '123', 'pw2' => -3], ['address.city' => 'email|array|same:name|between:2,6', 'email' => 'date'], ['address.city' => ['The address.city field must be a valid email address.', 'The address.city field must be an array.', 'The address.city field must match name.'], 'email' => ['The email field must be a valid date (YYYY-MM-DD).']]],
        [['name' => '007', 'email' => 1, 'tags' => 12, 'items' => [['qty' => 'a'], ['qty' => ''], ['qty' => 'é']], 'pw2' => null], ['tags' => 'date|int|min:0.5|bail'], ['tags' => ['The tags field must be a valid date (YYYY-MM-DD).']]],
        [['name' => -3, 'age' => true, 'email' => '2019-03-01', 'tags' => 'x@y', 'address' => ['city' => ''], 'items' => '123', 'pw2' => [1]], ['address.city' => 'between:2,6'], ['address.city' => ['The address.city field must be between 2 and 6 characters.']]],
        [['name' => 2.5, 'tags' => '  ', 'address' => ['city' => '4.5'], 'pw2' => [1]], ['email' => 'in:a,bb,ccc|in:1,2,3', 'name' => 'bail', 'pw2' => 'min:2', 'tags' => 'email|after:2020-02-29|max:-1'], ['pw2' => ['The pw2 field must have at least 2 items.'], 'tags' => ['The tags field must be a valid email address.', 'The tags field must be a date after 2020-02-29.', 'The tags field must not be greater than -1 characters.']]],
        [['name' => 'x', 'age' => '123', 'email' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'address' => 'é', 'items' => [['qty' => 1]], 'dob' => '日本', 'pw2' => ''], ['address.city' => 'max:5|min:3|same:name', 'name' => 'numeric|min:2|in:a,bb,ccc', 'tags' => 'min:2|required|numeric|min:3'], ['name' => ['The name field must be a number.', 'The selected name is invalid.'], 'tags' => ['The tags field is required.']]],
        [['name' => 'é', 'age' => '-4', 'email' => 'abc', 'tags' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'address' => 2.5, 'pw2' => 0], ['age' => 'email', 'tags' => 'max:10', 'address.city' => 'min:0.5|email|string'], ['age' => ['The age field must be a valid email address.']]],
        [['age' => 0, 'email' => ['k' => 1], 'tags' => -3, 'address' => ['city' => 2.5], 'items' => [], 'dob' => 2.5], ['pw2' => 'string|in:1,2,3', 'dob' => 'min:3|array', 'items.*.qty' => 'date|array|string|max:10', 'age' => 'same:name'], ['dob' => ['The dob field must be an array.'], 'age' => ['The age field must match name.']]],
        [['name' => null, 'age' => true, 'email' => false, 'tags' => 'x@y', 'items' => [['qty' => 'abc']], 'dob' => true, 'pw2' => 12], ['address.city' => ['regex:/^[a-z]+$/', 'in:a,bb,ccc', 'min:2', 'email'], 'pw2' => 'after:2020-02-29'], ['pw2' => ['The pw2 field must be a date after 2020-02-29.']]],
        [['age' => '-4', 'email' => false, 'address' => ['city' => 12], 'items' => 2.5, 'dob' => 2.5], ['dob' => 'numeric|between:2,6|same:name'], ['dob' => ['The dob field must match name.']]],
        [['name' => ['k' => 1], 'age' => null, 'email' => 12, 'tags' => '2019-03-01', 'address' => ['city' => 'x@y'], 'items' => [], 'dob' => '123', 'pw2' => [1]], ['age' => 'between:2,6|array|string|string'], []],
        [['name' => 0, 'age' => [], 'email' => 0, 'address' => ['city' => false], 'items' => [['qty' => ['a', 'b']], ['qty' => 12], ['qty' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']]], 'dob' => 'abc', 'pw2' => '  '], ['dob' => 'min:3|bail|in:a,bb,ccc', 'tags' => 'int|email|same:name', 'age' => 'max:-1|string|between:2,6', 'email' => ['regex:/^[a-z]+$/', 'regex:/^[a-z]+$/', 'array', 'max:5']], ['dob' => ['The selected dob is invalid.'], 'age' => ['The age field must not have more than -1 items.', 'The age field must be a string.', 'The age field must have between 2 and 6 items.'], 'email' => ['The email field format is invalid.', 'The email field format is invalid.', 'The email field must be an array.']]],
        [['age' => null, 'email' => false, 'address' => ['city' => false], 'items' => 'é', 'pw2' => ['k' => 1]], ['tags' => 'min:2|date|max:-1', 'age' => 'string|max:-1|in:1,2,3|in:a,bb,ccc'], []],
        [['age' => true, 'email' => [], 'tags' => 'a', 'address' => ['city' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], 'items' => [['qty' => true], ['qty' => 'abc']], 'dob' => 'abcdef', 'pw2' => 1], ['dob' => 'array|min:3', 'name' => 'bail|min:0.5|min:2', 'tags' => 'after:2020-02-29', 'pw2' => 'min:0.5|array'], ['dob' => ['The dob field must be an array.'], 'tags' => ['The tags field must be a date after 2020-02-29.'], 'pw2' => ['The pw2 field must be an array.']]],
        [['name' => 1, 'age' => '@', 'address' => ['city' => 'abcdef'], 'items' => '4.5', 'pw2' => 'abcdef'], ['age' => 'bail|between:2,6|email|string', 'items.*.qty' => 'max:5|min:3|between:2,6', 'pw2' => 'in:a,bb,ccc|required|max:-1|min:2', 'address.city' => ['array', 'regex:/^[a-z]+$/', 'int']], ['age' => ['The age field must be between 2 and 6 characters.'], 'pw2' => ['The selected pw2 is invalid.', 'The pw2 field must not be greater than -1 characters.'], 'address.city' => ['The address.city field must be an array.', 'The address.city field must be an integer.']]],
        [['name' => 'abc', 'age' => [1], 'email' => 'abc', 'address' => 'a', 'items' => [['qty' => 'abcdef'], ['qty' => 'abcdef'], ['qty' => 'x@y']], 'dob' => 'a'], ['tags' => 'in:a,bb,ccc|int|between:2,6', 'email' => 'bail|min:3'], []],
        [['name' => [], 'email' => 0, 'tags' => '日本', 'address' => 2.5, 'items' => [['qty' => 2.5], ['qty' => 'abcdef']], 'dob' => 'abcdef', 'pw2' => [1]], ['age' => 'min:0.5', 'address.city' => ['regex:/^[a-z]+$/', 'max:-1', 'date', 'string'], 'dob' => 'max:5|min:2', 'pw2' => 'array|after:2020-02-29'], ['dob' => ['The dob field must not be greater than 5 characters.'], 'pw2' => ['The pw2 field must be a date after 2020-02-29.']]],
        [['name' => ['a', 'b'], 'tags' => '-4', 'address' => ['city' => 'a@b.co'], 'items' => [['qty' => 1]], 'dob' => '-4', 'pw2' => 2.5], ['tags' => 'in:a,bb,ccc|max:10|after:2020-02-29|bail', 'pw2' => 'array|min:0.5|min:0.5|max:5', 'age' => 'after:2020-02-29'], ['tags' => ['The selected tags is invalid.', 'The tags field must be a date after 2020-02-29.'], 'pw2' => ['The pw2 field must be an array.']]],
        [['age' => 2.5, 'tags' => '123', 'address' => ['city' => false], 'items' => [['qty' => 'a']], 'dob' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'pw2' => 1], ['items.*.qty' => 'between:2,6|array|email', 'address.city' => 'int|in:a,bb,ccc', 'dob' => 'max:5|after:2020-02-29|numeric|string'], ['items.0.qty' => ['The items.0.qty field must be between 2 and 6 characters.', 'The items.0.qty field must be an array.', 'The items.0.qty field must be a valid email address.'], 'address.city' => ['The address.city field must be an integer.', 'The selected address.city is invalid.'], 'dob' => ['The dob field must not have more than 5 items.', 'The dob field must be a date after 2020-02-29.', 'The dob field must be a number.', 'The dob field must be a string.']]],
        [['name' => 'abc', 'age' => false, 'email' => '2024-02-29', 'tags' => 'a@b.co', 'address' => ['city' => 2.5], 'items' => [['qty' => 0], ['qty' => '']], 'dob' => false, 'pw2' => []], ['address.city' => 'max:-1|bail|in:1,2,3|after:2020-02-29', 'age' => 'min:2|email|max:-1|same:name', 'dob' => 'between:2,6|min:0.5|string|bail'], ['address.city' => ['The address.city field must not be greater than -1 characters.', 'The selected address.city is invalid.'], 'age' => ['The age field must be at least 2 characters.', 'The age field must be a valid email address.', 'The age field must not be greater than -1 characters.', 'The age field must match name.'], 'dob' => ['The dob field must be between 2 and 6 characters.', 'The dob field must be at least 0.5 characters.', 'The dob field must be a string.']]],
        [['name' => '4.5', 'age' => '123', 'address' => ['city' => 'abc'], 'items' => [['qty' => null]], 'pw2' => 'a@b.co'], ['dob' => 'after:2020-02-29|max:5'], []],
        [['name' => ['k' => 1], 'tags' => 1, 'items' => [], 'dob' => '', 'pw2' => true], ['address.city' => 'min:2|min:2|numeric|max:5', 'dob' => 'string'], []],
        [['name' => '2019-03-01', 'age' => true, 'email' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'tags' => '-4', 'address' => ['city' => 0], 'items' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'pw2' => 'é'], ['dob' => 'string', 'items.*.qty' => 'between:2,6', 'address.city' => 'between:2,6|min:2|max:10|int', 'tags' => 'in:a,bb,ccc|same:name|int|bail'], ['address.city' => ['The address.city field must be between 2 and 6.', 'The address.city field must be at least 2.'], 'tags' => ['The selected tags is invalid.', 'The tags field must match name.']]],
        [['age' => false, 'email' => '2019-03-01', 'tags' => -3, 'address' => ['city' => ['a', 'b']], 'items' => [], 'dob' => '007', 'pw2' => false], ['items.*.qty' => 'numeric|date|string|in:a,bb,ccc'], []],
        [['age' => true, 'tags' => false, 'address' => [], 'items' => [['qty' => [1]], ['qty' => '2024-02-29']], 'pw2' => 12], ['dob' => 'bail', 'age' => 'string|between:2,6|same:name', 'email' => 'date|max:5', 'tags' => 'email|in:a,bb,ccc|in:a,bb,ccc'], ['age' => ['The age field must be a string.', 'The age field must be between 2 and 6 characters.', 'The age field must match name.'], 'tags' => ['The tags field must be a valid email address.', 'The selected tags is invalid.', 'The selected tags is invalid.']]],
        [['name' => '-4', 'email' => 2.5, 'tags' => false, 'items' => [], 'dob' => '2024-02-29', 'pw2' => 'x@y'], ['tags' => 'min:3|numeric|array', 'pw2' => 'array|min:3', 'dob' => 'min:0.5', 'email' => 'max:5|after:2020-02-29|min:3'], ['tags' => ['The tags field must be a number.', 'The tags field must be an array.'], 'pw2' => ['The pw2 field must be an array.'], 'email' => ['The email field must be a date after 2020-02-29.']]],
        [['name' => '4.5', 'tags' => 12, 'items' => [], 'pw2' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], ['email' => 'array'], []],
        [['name' => '4.5', 'age' => 'a', 'address' => 'x', 'dob' => true], ['age' => 'bail', 'dob' => 'string|int|after:2020-02-29|string', 'address.city' => 'in:a,bb,ccc', 'tags' => 'bail|date'], ['dob' => ['The dob field must be a string.', 'The dob field must be an integer.', 'The dob field must be a date after 2020-02-29.', 'The dob field must be a string.']]],
        [['name' => '4.5', 'age' => 'a@b.co', 'email' => ['k' => 1], 'tags' => 'x', 'address' => ['city' => 'é'], 'items' => [['qty' => '2024-02-29'], ['qty' => '-4']], 'dob' => '2024-02-29', 'pw2' => [1]], ['address.city' => 'required|max:10|numeric|after:2020-02-29', 'tags' => 'in:a,bb,ccc|min:3|min:0.5|max:10', 'items.*.qty' => ['min:3', 'array', 'numeric', 'regex:/^[a-z]+$/']], ['address.city' => ['The address.city field must be a number.', 'The address.city field must be a date after 2020-02-29.'], 'tags' => ['The selected tags is invalid.', 'The tags field must be at least 3 characters.'], 'items.0.qty' => ['The items.0.qty field must be an array.', 'The items.0.qty field must be a number.', 'The items.0.qty field format is invalid.'], 'items.1.qty' => ['The items.1.qty field must be at least 3.', 'The items.1.qty field must be an array.', 'The items.1.qty field format is invalid.']]],
        [['name' => -3, 'age' => null, 'address' => ['city' => ''], 'items' => [['qty' => 0], ['qty' => '4.5']]], ['name' => 'min:2|min:2|date|required', 'tags' => 'in:a,bb,ccc|max:5|max:10'], ['name' => ['The name field must be a valid date (YYYY-MM-DD).']]],
        [['name' => 0, 'age' => '日本', 'address' => ['city' => '007'], 'dob' => '007', 'pw2' => 1], ['email' => ['min:0.5', 'numeric', 'regex:/^[a-z]+$/', 'between:2,6']], []],
        [['age' => -3, 'email' => false, 'tags' => '-4', 'address' => ['city' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], 'items' => [['qty' => 'é'], ['qty' => 1], ['qty' => 'abcdef']], 'dob' => ['a', 'b'], 'pw2' => '123'], ['email' => 'required|between:2,6', 'items.*.qty' => 'after:2020-02-29|min:0.5|max:10', 'address.city' => 'max:5|after:2020-02-29|email|bail'], ['email' => ['The email field must be between 2 and 6 characters.'], 'items.0.qty' => ['The items.0.qty field must be a date after 2020-02-29.'], 'items.1.qty' => ['The items.1.qty field must be a date after 2020-02-29.'], 'items.2.qty' => ['The items.2.qty field must be a date after 2020-02-29.'], 'address.city' => ['The address.city field must not have more than 5 items.', 'The address.city field must be a date after 2020-02-29.', 'The address.city field must be a valid email address.']]],
        [['age' => '007', 'email' => 0, 'items' => [], 'pw2' => '2019-03-01'], ['email' => 'after:2020-02-29|string|min:3', 'dob' => ['regex:/^[a-z]+$/'], 'age' => 'numeric|array', 'tags' => ['regex:/^[a-z]+$/', 'email', 'max:-1']], ['email' => ['The email field must be a date after 2020-02-29.', 'The email field must be a string.', 'The email field must be at least 3 characters.'], 'age' => ['The age field must be an array.']]],
        [['age' => ['k' => 1], 'address' => ['city' => 'a@b.co'], 'dob' => ['a', 'b']], ['address.city' => 'required|between:2,6|in:1,2,3|in:1,2,3', 'age' => 'max:5|numeric', 'items.*.qty' => ['int', 'regex:/^[a-z]+$/', 'min:2', 'min:2'], 'name' => ['regex:/^[a-z]+$/', 'int']], ['address.city' => ['The selected address.city is invalid.', 'The selected address.city is invalid.'], 'age' => ['The age field must be a number.']]],
        [['name' => -3, 'age' => ['k' => 1], 'dob' => '-4', 'pw2' => ['k' => 1]], ['dob' => 'max:5|max:5', 'email' => 'required|same:name', 'items.*.qty' => 'min:2', 'pw2' => 'date'], ['email' => ['The email field is required.'], 'pw2' => ['The pw2 field must be a valid date (YYYY-MM-DD).']]],
        [['age' => [1], 'email' => '-4', 'items' => [['qty' => '日本']], 'pw2' => true], ['address.city' => 'max:-1'], []],
        [['address' => ['city' => 'a'], 'items' => [['qty' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], ['qty' => [1]]]], ['tags' => 'min:0.5|in:a,bb,ccc|bail|min:3', 'age' => 'bail|min:3'], []],
        [['age' => '', 'email' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'tags' => '123', 'address' => 'abcdef', 'items' => [['qty' => '123'], ['qty' => 'x@y']], 'dob' => '2024-02-29', 'pw2' => 'a'], ['tags' => 'max:-1|after:2020-02-29|min:0.5'], ['tags' => ['The tags field must not be greater than -1 characters.', 'The tags field must be a date after 2020-02-29.']]],
        [['age' => '123', 'email' => 0, 'tags' => '007', 'items' => true, 'dob' => 12, 'pw2' => 2.5], ['pw2' => 'max:-1|email', 'name' => 'string|bail|email|array', 'items.*.qty' => 'string', 'dob' => 'min:0.5|bail|array|bail'], ['pw2' => ['The pw2 field must not be greater than -1 characters.', 'The pw2 field must be a valid email address.'], 'dob' => ['The dob field must be an array.']]],
        [['name' => 0, 'age' => '  ', 'tags' => 'x@y', 'address' => ['city' => '-4'], 'items' => [['qty' => 12], ['qty' => 'é']], 'dob' => '2019-03-01'], ['age' => 'numeric', 'name' => 'array|bail|between:2,6|max:-1', 'pw2' => 'max:5|max:5|max:10', 'email' => 'between:2,6|date'], ['age' => ['The age field must be a number.'], 'name' => ['The name field must be an array.', 'The name field must be between 2 and 6 characters.']]],
        [['age' => true, 'email' => ['a', 'b'], 'tags' => '@', 'address' => '2019-03-01', 'items' => []], ['dob' => 'same:name|email|required|in:a,bb,ccc', 'age' => 'bail|after:2020-02-29', 'tags' => ['in:1,2,3', 'numeric', 'in:1,2,3', 'regex:/^[a-z]+$/']], ['dob' => ['The dob field is required.'], 'age' => ['The age field must be a date after 2020-02-29.'], 'tags' => ['The selected tags is invalid.', 'The tags field must be a number.', 'The selected tags is invalid.', 'The tags field format is invalid.']]],
        [['email' => 0, 'address' => ['city' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], 'dob' => '2019-03-01'], ['email' => 'after:2020-02-29|max:-1', 'name' => 'date|in:a,bb,ccc|min:3'], ['email' => ['The email field must be a date after 2020-02-29.', 'The email field must not be greater than -1 characters.']]],
        [['name' => false, 'age' => '-4', 'email' => 1, 'tags' => [], 'address' => ['city' => '123'], 'items' => [['qty' => 1], ['qty' => null], ['qty' => '4.5']], 'pw2' => '  '], ['pw2' => 'min:0.5|max:-1|min:2', 'tags' => 'bail|max:-1'], ['pw2' => ['The pw2 field must not be greater than -1 characters.'], 'tags' => ['The tags field must not have more than -1 items.']]],
        [['name' => 2.5, 'tags' => 12, 'address' => ['city' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], 'items' => [], 'dob' => '', 'pw2' => '日本'], ['name' => 'date|min:3|max:10'], ['name' => ['The name field must be a valid date (YYYY-MM-DD).']]],
        [['email' => '-4', 'tags' => true, 'address' => ['city' => '123'], 'dob' => 'x@y'], ['dob' => 'required|min:3', 'pw2' => 'bail|email|array|in:a,bb,ccc'], []],
        [['name' => '123', 'age' => ['a', 'b'], 'email' => '  ', 'tags' => 2.5, 'items' => [['qty' => '']], 'dob' => [1], 'pw2' => '2019-03-01'], ['pw2' => 'in:a,bb,ccc|between:2,6', 'tags' => 'numeric|between:2,6|max:5|in:a,bb,ccc'], ['pw2' => ['The selected pw2 is invalid.', 'The pw2 field must be between 2 and 6 characters.'], 'tags' => ['The selected tags is invalid.']]],
        [['name' => '123', 'email' => '4.5', 'tags' => '123', 'address' => ['city' => '007'], 'items' => [], 'dob' => '-4'], ['email' => ['regex:/^[a-z]+$/'], 'address.city' => 'date|email'], ['email' => ['The email field format is invalid.'], 'address.city' => ['The address.city field must be a valid date (YYYY-MM-DD).', 'The address.city field must be a valid email address.']]],
        [['age' => '日本', 'email' => '  ', 'tags' => 2.5, 'address' => ['city' => 'a@b.co'], 'items' => '2019-03-01', 'pw2' => 12], ['dob' => ['in:a,bb,ccc', 'in:1,2,3', 'max:5', 'regex:/^[a-z]+$/'], 'items.*.qty' => 'numeric|min:2|date|bail'], []],
        [['name' => -3, 'email' => 'x', 'tags' => false, 'address' => ['city' => '2019-03-01']], ['email' => 'in:1,2,3|required|string', 'age' => 'int|max:10', 'items.*.qty' => 'min:3', 'name' => ['same:name', 'date', 'min:0.5', 'regex:/^[a-z]+$/']], ['email' => ['The selected email is invalid.'], 'name' => ['The name field must be a valid date (YYYY-MM-DD).', 'The name field format is invalid.']]],
        [['name' => -3, 'age' => 'abc', 'email' => '2019-03-01', 'tags' => '2019-03-01', 'address' => ['city' => ['k' => 1]], 'dob' => -3], ['name' => 'max:-1|int|max:5', 'age' => 'max:5', 'items.*.qty' => 'string|between:2,6'], []],
        [['name' => 1, 'email' => '', 'tags' => 1, 'address' => ['city' => 'a@b.co'], 'items' => [], 'dob' => 1, 'pw2' => '123'], ['tags' => 'same:name|min:2|in:1,2,3', 'address.city' => 'after:2020-02-29|array', 'age' => 'bail|bail|after:2020-02-29'], ['tags' => ['The tags field must be at least 2 characters.'], 'address.city' => ['The address.city field must be a date after 2020-02-29.', 'The address.city field must be an array.']]],
        [['name' => '2019-03-01', 'age' => 'x@y', 'email' => '2019-03-01', 'address' => ['city' => false], 'dob' => [], 'pw2' => 12], ['age' => 'between:2,6', 'address.city' => ['min:0.5', 'regex:/^[a-z]+$/', 'after:2020-02-29', 'numeric'], 'email' => 'min:2|min:3', 'pw2' => 'after:2020-02-29|max:5'], ['address.city' => ['The address.city field format is invalid.', 'The address.city field must be a date after 2020-02-29.', 'The address.city field must be a number.'], 'pw2' => ['The pw2 field must be a date after 2020-02-29.']]],
        [['name' => [1], 'age' => [1], 'email' => '007', 'tags' => -3], ['address.city' => 'between:2,6|in:a,bb,ccc'], []],
        [['name' => false, 'age' => 1, 'tags' => ['a', 'b'], 'items' => true, 'dob' => 12, 'pw2' => 1], ['name' => 'max:5|min:3|max:5|min:3'], ['name' => ['The name field must be at least 3 characters.', 'The name field must be at least 3 characters.']]],
        [['age' => 'é', 'email' => 'é', 'address' => false, 'items' => ['a', 'b'], 'dob' => 'x', 'pw2' => ['k' => 1]], ['email' => 'min:2|min:3|in:1,2,3', 'dob' => 'min:2|min:0.5|in:1,2,3', 'pw2' => 'min:0.5|min:0.5|max:-1', 'age' => 'in:1,2,3|email|min:3'], ['email' => ['The email field must be at least 2 characters.', 'The email field must be at least 3 characters.', 'The selected email is invalid.'], 'dob' => ['The dob field must be at least 2 characters.', 'The selected dob is invalid.'], 'pw2' => ['The pw2 field must not have more than -1 items.'], 'age' => ['The selected age is invalid.', 'The age field must be a valid email address.', 'The age field must be at least 3 characters.']]],
        [['name' => '日本', 'age' => 12, 'email' => 2.5, 'tags' => ['k' => 1], 'address' => ['city' => '@'], 'items' => [['qty' => '123'], ['qty' => '2024-02-29'], ['qty' => null]], 'pw2' => ''], ['pw2' => 'date|after:2020-02-29|after:2020-02-29|bail', 'address.city' => 'string'], ['pw2' => ['The pw2 field must be a valid date (YYYY-MM-DD).', 'The pw2 field must be a date after 2020-02-29.', 'The pw2 field must be a date after 2020-02-29.']]],
        [['name' => 'x@y', 'age' => ['k' => 1], 'email' => false, 'tags' => '', 'items' => [], 'pw2' => 0], ['tags' => 'array|min:0.5', 'pw2' => 'max:5', 'name' => 'in:1,2,3|in:1,2,3'], ['tags' => ['The tags field must be an array.', 'The tags field must be at least 0.5 characters.'], 'name' => ['The selected name is invalid.', 'The selected name is invalid.']]],
        [['name' => '-4', 'tags' => '', 'items' => [['qty' => []], ['qty' => '  '], ['qty' => true]]], ['age' => ['min:0.5', 'regex:/^[a-z]+$/', 'array', 'max:10'], 'address.city' => ['regex:/^[a-z]+$/', 'array', 'in:a,bb,ccc'], 'name' => 'required|same:name'], []],
        [['name' => true, 'age' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'email' => '2024-02-29', 'tags' => ['k' => 1], 'dob' => true], ['pw2' => 'same:name'], []],
        [['name' => 'abc', 'age' => false, 'email' => '007', 'tags' => 0, 'items' => [], 'pw2' => '007'], ['items.*.qty' => 'in:a,bb,ccc', 'pw2' => 'int', 'name' => 'min:2|min:0.5|max:-1'], ['name' => ['The name field must not be greater than -1 characters.']]],
        [['name' => '@', 'age' => '@', 'email' => '  ', 'items' => []], ['dob' => 'in:a,bb,ccc', 'items.*.qty' => 'min:2|bail|in:a,bb,ccc', 'email' => 'max:10|string'], []],
        [['name' => '', 'age' => '', 'tags' => 'é', 'address' => ['city' => '日本'], 'items' => [['qty' => 'abcdef']], 'dob' => 'a', 'pw2' => 'abc'], ['pw2' => 'string', 'email' => 'bail|same:name|string|array', 'name' => 'max:-1|array', 'address.city' => ['required', 'regex:/^[a-z]+$/', 'in:a,bb,ccc']], ['name' => ['The name field must not be greater than -1 characters.', 'The name field must be an array.'], 'address.city' => ['The address.city field format is invalid.', 'The selected address.city is invalid.']]],
        [['name' => false, 'age' => 'a', 'email' => '2024-02-29', 'tags' => 'abc', 'items' => [['qty' => true]], 'dob' => null, 'pw2' => 0], ['name' => 'email|in:a,bb,ccc|between:2,6'], ['name' => ['The name field must be a valid email address.', 'The selected name is invalid.', 'The name field must be between 2 and 6 characters.']]],
        [['age' => 'a@b.co', 'email' => '2024-02-29', 'tags' => null, 'dob' => 'a', 'pw2' => ''], ['dob' => ['same:name', 'regex:/^[a-z]+$/'], 'address.city' => 'max:10', 'tags' => 'string|email|max:-1|numeric'], ['dob' => ['The dob field must match name.']]],
        [['name' => '123', 'email' => 'abc', 'tags' => 'x', 'address' => ['city' => '2024-02-29'], 'items' => [], 'pw2' => '4.5'], ['tags' => ['min:3', 'int', 'regex:/^[a-z]+$/'], 'name' => 'bail|in:a,bb,ccc|in:a,bb,ccc'], ['tags' => ['The tags field must be an integer.'], 'name' => ['The selected name is invalid.']]],
        [['name' => '4.5', 'email' => -3, 'address' => ['city' => 'abc'], 'items' => 'a@b.co', 'dob' => '', 'pw2' => [1]], ['items.*.qty' => 'in:1,2,3|min:2', 'age' => 'in:1,2,3', 'name' => 'after:2020-02-29|min:0.5'], ['name' => ['The name field must be a date after 2020-02-29.']]],
        [['name' => 2.5, 'age' => '123', 'email' => null, 'address' => ['city' => 'abcdef'], 'items' => [], 'dob' => -3, 'pw2' => '日本'], ['address.city' => 'in:1,2,3|string|in:a,bb,ccc', 'email' => 'required|max:5|array', 'pw2' => 'email|min:0.5|after:2020-02-29'], ['address.city' => ['The selected address.city is invalid.', 'The selected address.city is invalid.'], 'email' => ['The email field is required.'], 'pw2' => ['The pw2 field must be a valid email address.', 'The pw2 field must be a date after 2020-02-29.']]],
        [['name' => 'a', 'age' => 'x@y', 'email' => 'abcdef', 'tags' => ['k' => 1], 'address' => ['city' => null], 'items' => [['qty' => '2024-02-29']], 'dob' => '007', 'pw2' => ['a', 'b']], ['email' => ['required', 'regex:/^[a-z]+$/', 'min:0.5'], 'address.city' => 'bail|min:0.5|array'], []],
        [['name' => '', 'email' => 'é', 'tags' => 'a@b.co', 'address' => true, 'items' => '', 'dob' => 'x', 'pw2' => 'a@b.co'], ['pw2' => 'bail|max:10|required|max:10', 'dob' => ['regex:/^[a-z]+$/', 'min:0.5', 'max:-1', 'between:2,6'], 'address.city' => 'required|required', 'tags' => 'string|numeric|in:1,2,3'], ['dob' => ['The dob field must not be greater than -1 characters.', 'The dob field must be between 2 and 6 characters.'], 'address.city' => ['The address.city field is required.', 'The address.city field is required.'], 'tags' => ['The tags field must be a number.', 'The selected tags is invalid.']]],
        [['age' => '日本', 'tags' => ['a', 'b'], 'address' => ['city' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], 'items' => [], 'dob' => 'x@y'], ['dob' => 'email|in:1,2,3|min:0.5|max:-1', 'name' => 'max:-1|max:5|max:-1', 'age' => 'same:name|date'], ['dob' => ['The dob field must be a valid email address.', 'The selected dob is invalid.', 'The dob field must not be greater than -1 characters.'], 'age' => ['The age field must match name.', 'The age field must be a valid date (YYYY-MM-DD).']]],
        [['name' => 'a@b.co', 'email' => '2019-03-01', 'tags' => 'é', 'address' => ['city' => ''], 'items' => [], 'dob' => [], 'pw2' => 'é'], ['items.*.qty' => 'min:3', 'pw2' => 'array|int', 'address.city' => 'in:a,bb,ccc|int|required'], ['pw2' => ['The pw2 field must be an array.', 'The pw2 field must be an integer.'], 'address.city' => ['The selected address.city is invalid.', 'The address.city field must be an integer.', 'The address.city field is required.']]],
        [['name' => 'x@y', 'email' => 'x@y', 'tags' => false, 'address' => ['city' => 0], 'items' => [['qty' => '-4']], 'pw2' => ['k' => 1]], ['address.city' => 'between:2,6|numeric|in:1,2,3', 'age' => 'min:3|in:1,2,3|min:3|max:10', 'items.*.qty' => 'in:a,bb,ccc'], ['address.city' => ['The address.city field must be between 2 and 6.', 'The selected address.city is invalid.'], 'items.0.qty' => ['The selected items.0.qty is invalid.']]],
        [['name' => 'é', 'age' => true, 'email' => -3, 'address' => ['city' => 'abc'], 'items' => '2019-03-01', 'dob' => 0, 'pw2' => 'é'], ['pw2' => ['regex:/^[a-z]+$/', 'max:10'], 'dob' => 'min:0.5', 'email' => 'array'], ['pw2' => ['The pw2 field format is invalid.'], 'email' => ['The email field must be an array.']]],
        [['name' => ['k' => 1], 'items' => [['qty' => 'abc'], ['qty' => 'abcdef'], ['qty' => 2.5]], 'dob' => '日本'], ['address.city' => 'after:2020-02-29|bail|max:10', 'tags' => 'min:2', 'dob' => 'numeric|numeric|between:2,6|email'], ['dob' => ['The dob field must be a number.', 'The dob field must be a number.', 'The dob field must be a valid email address.']]],
        [['name' => 1, 'age' => 1, 'email' => 'x', 'tags' => 12, 'address' => ['city' => '-4'], 'items' => [['qty' => 0]], 'pw2' => '4.5'], ['email' => 'int|array|in:a,bb,ccc|same:name', 'address.city' => ['string', 'regex:/^[a-z]+$/', 'bail'], 'items.*.qty' => 'string|min:0.5', 'age' => 'after:2020-02-29|string'], ['email' => ['The email field must be an integer.', 'The email field must be an array.', 'The selected email is invalid.', 'The email field must match name.'], 'address.city' => ['The address.city field format is invalid.'], 'items.0.qty' => ['The items.0.qty field must be a string.'], 'age' => ['The age field must be a date after 2020-02-29.', 'The age field must be a string.']]],
        [['name' => '2019-03-01', 'age' => '2019-03-01', 'tags' => 'a@b.co', 'address' => ['city' => '日本'], 'dob' => 12, 'pw2' => ['k' => 1]], ['items.*.qty' => 'string|max:-1', 'address.city' => 'email|same:name', 'email' => ['regex:/^[a-z]+$/', 'bail'], 'tags' => 'in:1,2,3'], ['address.city' => ['The address.city field must be a valid email address.', 'The address.city field must match name.'], 'tags' => ['The selected tags is invalid.']]],
        [['address' => ['city' => 'x@y'], 'items' => [['qty' => 'é'], ['qty' => '日本'], ['qty' => 'a']], 'dob' => '123'], ['email' => 'same:name|between:2,6', 'tags' => 'in:a,bb,ccc|string|min:0.5|int', 'address.city' => 'max:-1|bail'], ['address.city' => ['The address.city field must not be greater than -1 characters.']]],
        [['name' => '4.5', 'age' => '2024-02-29', 'email' => [], 'tags' => '007', 'address' => ['city' => [1]], 'items' => [], 'dob' => '2024-02-29', 'pw2' => 'a@b.co'], ['dob' => 'max:-1', 'items.*.qty' => 'date|in:a,bb,ccc'], ['dob' => ['The dob field must not be greater than -1 characters.']]],
        [['name' => true, 'email' => 'abc', 'tags' => '@', 'items' => [['qty' => 'a@b.co'], ['qty' => '4.5']], 'dob' => true], ['items.*.qty' => 'email|required', 'address.city' => 'min:0.5|date|between:2,6', 'tags' => 'same:name', 'dob' => 'email|email|email'], ['items.1.qty' => ['The items.1.qty field must be a valid email address.'], 'tags' => ['The tags field must match name.'], 'dob' => ['The dob field must be a valid email address.', 'The dob field must be a valid email address.', 'The dob field must be a valid email address.']]],
        [['name' => 'a', 'age' => false, 'email' => 'x', 'tags' => 'x@y', 'address' => ['city' => ['a', 'b']], 'dob' => '-4', 'pw2' => '4.5'], ['tags' => 'max:10', 'email' => 'in:1,2,3|bail|required|numeric', 'age' => ['max:-1', 'date', 'regex:/^[a-z]+$/'], 'items.*.qty' => 'string|required|numeric'], ['email' => ['The selected email is invalid.'], 'age' => ['The age field must not be greater than -1 characters.', 'The age field must be a valid date (YYYY-MM-DD).', 'The age field format is invalid.']]],
        [['name' => ['a', 'b'], 'age' => '123', 'email' => ['k' => 1], 'tags' => '日本', 'items' => [['qty' => null]], 'dob' => [], 'pw2' => 'x@y'], ['age' => 'int|min:2', 'address.city' => 'email', 'name' => 'min:2|bail|between:2,6|email'], ['name' => ['The name field must be a valid email address.']]],
        [['age' => 2.5, 'email' => '日本', 'tags' => ['k' => 1], 'dob' => '', 'pw2' => ['a', 'b']], ['address.city' => 'numeric', 'age' => 'int|in:a,bb,ccc|between:2,6|same:name'], ['age' => ['The age field must be an integer.', 'The selected age is invalid.', 'The age field must match name.']]],
        [['email' => ['a', 'b'], 'tags' => 2.5, 'address' => ['city' => -3], 'items' => []], ['dob' => 'min:0.5', 'tags' => 'max:5|email|email', 'items.*.qty' => ['regex:/^[a-z]+$/', 'int']], ['tags' => ['The tags field must be a valid email address.', 'The tags field must be a valid email address.']]],
        [['name' => [1], 'age' => 'abc', 'email' => [], 'tags' => true, 'address' => ['city' => '日本'], 'pw2' => ['k' => 1]], ['email' => 'array|same:name|numeric'], ['email' => ['The email field must match name.', 'The email field must be a number.']]],
        [['name' => ['k' => 1], 'email' => '日本', 'tags' => 'abc', 'address' => ['city' => 'a@b.co'], 'dob' => '4.5', 'pw2' => '2024-02-29'], ['address.city' => ['date', 'bail', 'min:2', 'regex:/^[a-z]+$/'], 'tags' => 'between:2,6|array|email', 'pw2' => 'max:-1|required|between:2,6'], ['address.city' => ['The address.city field must be a valid date (YYYY-MM-DD).'], 'tags' => ['The tags field must be an array.', 'The tags field must be a valid email address.'], 'pw2' => ['The pw2 field must not be greater than -1 characters.', 'The pw2 field must be between 2 and 6 characters.']]],
        [['age' => 'abc', 'email' => '007', 'tags' => 0, 'address' => ['city' => 0], 'items' => [['qty' => null], ['qty' => 'x']], 'dob' => ['a', 'b', 'c', 'd', 'e', 'f', 'g'], 'pw2' => ''], ['name' => ['min:0.5', 'array', 'regex:/^[a-z]+$/', 'max:10'], 'items.*.qty' => 'numeric|between:2,6|in:a,bb,ccc|numeric', 'address.city' => 'int|same:name'], ['items.1.qty' => ['The items.1.qty field must be a number.', 'The selected items.1.qty is invalid.', 'The items.1.qty field must be a number.'], 'address.city' => ['The address.city field must match name.']]],
        [['name' => false, 'age' => 2.5, 'email' => '日本', 'address' => ['city' => 12], 'items' => [['qty' => [1]], ['qty' => '2024-02-29']], 'pw2' => ['a', 'b', 'c', 'd', 'e', 'f', 'g']], ['pw2' => 'numeric|required|min:3|same:name', 'tags' => 'array|after:2020-02-29'], ['pw2' => ['The pw2 field must be a number.', 'The pw2 field must match name.']]],
        [['name' => 1, 'age' => 12, 'email' => '2019-03-01', 'dob' => 'a', 'pw2' => '-4'], ['name' => 'min:2', 'pw2' => 'string'], ['name' => ['The name field must be at least 2 characters.']]],
        [['age' => null, 'email' => 12, 'tags' => '007', 'address' => ['city' => '123'], 'items' => [], 'dob' => 'abcdef'], ['dob' => 'min:0.5|in:a,bb,ccc|between:2,6', 'age' => 'int', 'pw2' => 'min:0.5|array|int|min:0.5', 'tags' => 'min:0.5|same:name'], ['dob' => ['The selected dob is invalid.'], 'tags' => ['The tags field must match name.']]],
    ];

    function describe_case($data, $rules): string
    {
        return json_encode($rules, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) . ' on ' . json_encode($data, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    }

    test('rule table', function () use ($CASES) {
        foreach ($CASES as $i => [$data, $rules, $want]) {
            $label = describe_case($data, $rules);
            if ($want === null) {
                raises(fn() => Validator::check($data, $rules), InvalidArgumentException::class, $label);
            } else {
                eq(Validator::check($data, $rules), $want, $label);
            }
        }
    });

    test('field order follows the rule table', function () {
        $r = Validator::check([], ['z' => 'required', 'a' => 'required', 'm' => 'required']);
        eq(array_keys($r), ['z', 'a', 'm']);
        $r = Validator::check(['items' => [['q' => ''], ['q' => ''], ['q' => '']]], ['other' => 'required', 'items.*.q' => 'required']);
        eq(array_keys($r), ['other', 'items.0.q', 'items.1.q', 'items.2.q']);
    });

    test('valid data gives an empty list', function () {
        eq(Validator::check(['a' => 'x'], ['a' => 'required']), []);
        eq(Validator::check([], []), []);
    });

    test('unknown rules are rejected even for absent fields', function () {
        raises(fn() => Validator::check([], ['a' => 'frobnicate']), InvalidArgumentException::class, 'unknown rule');
        raises(fn() => Validator::check(['a' => 1], ['a' => 'required|nope:3']), InvalidArgumentException::class, 'unknown rule with args');
        raises(fn() => Validator::check([], ['a' => ['required', 'Required']]), InvalidArgumentException::class, 'rule names are case sensitive');
    });

    test('rule arguments keep everything after the first colon', function () {
        eq(Validator::check(['t' => 'a:b'], ['t' => ['regex:/^a:b$/']]), []);
        eq(Validator::check(['t' => 'a:c'], ['t' => ['regex:/^a:b$/']]), ['t' => ['The t field format is invalid.']]);
        eq(Validator::check(['t' => 'x:y'], ['t' => 'in:x:y,z']), []);
        eq(Validator::check(['t' => 'x'], ['t' => 'in:x:y,z']), ['t' => ['The selected t is invalid.']]);
    });
    test('every month has its own length', function () {
        $len = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
        $leap = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
        for ($m = 1; $m <= 12; $m++) {
            foreach ([[2023, $len], [2024, $leap]] as [$y, $table]) {
                $ok = sprintf('%04d-%02d-%02d', $y, $m, $table[$m - 1]);
                $bad = sprintf('%04d-%02d-%02d', $y, $m, $table[$m - 1] + 1);
                eq(Validator::check(['d' => $ok], ['d' => 'date']), [], "valid $ok");
                eq(Validator::check(['d' => $bad], ['d' => 'date']), ['d' => ['The d field must be a valid date (YYYY-MM-DD).']], "invalid $bad");
            }
        }
        foreach ([1600 => true, 1700 => false, 1800 => false, 1900 => false, 2000 => true, 2004 => true, 2023 => false, 2100 => false, 2400 => true, 4 => true, 100 => false, 400 => true] as $y => $isLeap) {
            $d = sprintf('%04d-02-29', $y);
            eq(Validator::check(['d' => $d], ['d' => 'date']) === [], $isLeap, "leap year $y");
        }
    });

    test('strings that are not valid UTF-8 are measured in bytes', function () {
        eq(Validator::check(['s' => "\xff\xfe\xfd"], ['s' => 'max:2']), ['s' => ['The s field must not be greater than 2 characters.']]);
        eq(Validator::check(['s' => "\xff\xfe\xfd"], ['s' => 'max:3']), []);
        eq(Validator::check(['s' => "ab\xc3"], ['s' => 'min:4']), ['s' => ['The s field must be at least 4 characters.']]);
        eq(Validator::check(['s' => "\xc3\xa9\xc3\xa9"], ['s' => 'max:2']), []);
    });

    t_done();
''')

LIB = Lib(
    name="rulecheck", lang="php", title="the Validator rule checker",
    blurb="The intranet's forms are validated by a small Validator class that turns a rule table like `'age' => 'required|int|between:18,99'` into a list of error messages.",
    files={"README.md": README1, "src/Validator.php": F2},
    visible_tests={"tests/run.php": _lang3.php_test(V3)},
    hidden_tests={"tests/run.php": _lang3.php_test(H4)},
    mutate=["src/Validator.php"], difficulty=4, tags=["validation", "forms", "parsing"],
)

_lang3.add(LIB, n=8)
