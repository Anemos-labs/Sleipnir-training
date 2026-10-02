"""Port library: a tiny template renderer with filters (strict grammar, ASCII-only case mapping, code-point lengths)."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

TPL_SPEC = dd('''
    A template is text with `{{ expression }}` placeholders. Texts are sequences of Unicode code points. The only
    *whitespace* here is space, tab, line feed and carriage return.

    **Variables.** The variables come as a list of `key=value` strings. Each entry is split at its **first** `=`; the
    key must match `[A-Za-z_][A-Za-z0-9_.]*` (ASCII) and an entry without `=` or with a bad key makes the whole call fail.
    The value may be empty and may contain `=`. A later entry with the same key replaces an earlier one.

    **Scanning** runs left to right over the template:

    * `\\{{` (a backslash directly followed by two open braces) produces the literal text `{{`; the three characters
      are consumed. Any other backslash is ordinary text.
    * `{{` starts a placeholder that ends at the next `}}` after it. No closing `}}` is an error. A `}}` outside a
      placeholder is ordinary text.

    **Expressions.** The text between the braces is split at every `|`; each piece loses leading and trailing whitespace.
    The first piece is the variable name (it must match the key pattern above) and the rest are filters; an empty
    piece (`{{ }}`, `{{ a| }}`, `{{|upper}}`) is an error.

    **Value.** If the variable exists its value is used. If it does not, the *first filter* must be `default:TEXT`, and
    then `TEXT` (everything after the first `:`, trimmed of whitespace; it may be empty) is the value; otherwise
    the call fails. Filters are applied in order:

    * `upper`, `lower`: change only the ASCII letters `a-z` / `A-Z`; every other character stays as it is. No argument allowed.
    * `trim`: remove whitespace at both ends. No argument allowed.
    * `len`: replace the value with the number of code points it has, as decimal digits. No argument allowed.
    * `pad:N`: `N` is 1 or 2 ASCII digits without a leading zero (after trimming); pad the value on the left with spaces
      until it has `N` code points (a longer value is unchanged).
    * `default:TEXT`: does nothing at this point (it already did its work when the variable was missing); the colon
      is required.
    * any other filter name (or a filter with an argument where none is allowed) is an error.

    `render(template, vars)` returns the output. `count_placeholders(template)` is the number of placeholders (escaped
    ones do not count) and `names(template)` lists the distinct variable names in order of first use; both fail on the same
    syntax errors as `render` (unterminated placeholder, bad name, empty piece) but do not look at variable values or
    validate filter names.
''')

TPL_FNS = [
    Fn("render", [("template", "str"), ("vars", "list<str>")], "str", err=True),
    Fn("count_placeholders", [("template", "str")], "int", err=True),
    Fn("names", [("template", "str")], "list<str>", err=True),
]

TPL_PY = dd(r'''
import re

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_PAD = re.compile(r"[1-9][0-9]?")
_WS = " \t\n\r"


def _vars(items):
    env = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not _NAME.fullmatch(key):
            raise ValueError("bad variable entry")
        env[key] = value
    return env


def _scan(template):
    parts, buf, i, n = [], [], 0, len(template)
    while i < n:
        if template.startswith("\\{{", i):
            buf.append("{{")
            i += 3
        elif template.startswith("{{", i):
            end = template.find("}}", i + 2)
            if end < 0:
                raise ValueError("unterminated placeholder")
            if buf:
                parts.append(("text", "".join(buf)))
                buf = []
            parts.append(("expr", template[i + 2:end]))
            i = end + 2
        else:
            buf.append(template[i])
            i += 1
    if buf:
        parts.append(("text", "".join(buf)))
    return parts


def _expr(text):
    pieces = [p.strip(_WS) for p in text.split("|")]
    if any(p == "" for p in pieces) or not _NAME.fullmatch(pieces[0]):
        raise ValueError("bad expression")
    return pieces[0], pieces[1:]


def _ascii(s, up):
    lo, hi, d = ("a", "z", -32) if up else ("A", "Z", 32)
    return "".join(chr(ord(c) + d) if lo <= c <= hi else c for c in s)


def _apply(value, f):
    name, sep, arg = f.partition(":")
    if name in ("upper", "lower", "trim", "len"):
        if sep:
            raise ValueError("filter takes no argument")
        if name == "upper":
            return _ascii(value, True)
        if name == "lower":
            return _ascii(value, False)
        if name == "trim":
            return value.strip(_WS)
        return str(len(value))
    if name == "pad":
        a = arg.strip(_WS)
        if not sep or not _PAD.fullmatch(a):
            raise ValueError("bad pad width")
        return " " * max(0, int(a) - len(value)) + value
    if name == "default":
        if not sep:
            raise ValueError("default needs a value")
        return value
    raise ValueError("unknown filter")


def render(template, vars):
    env = _vars(vars)
    out = []
    for kind, s in _scan(template):
        if kind == "text":
            out.append(s)
            continue
        name, filters = _expr(s)
        if name in env:
            value = env[name]
        elif filters and filters[0].partition(":")[0] == "default" and ":" in filters[0]:
            value = filters[0].partition(":")[2].strip(_WS)
        else:
            raise ValueError("missing variable " + name)
        for f in filters:
            value = _apply(value, f)
        out.append(value)
    return "".join(out)


def count_placeholders(template):
    return sum(1 for kind, s in _scan(template) if kind == "expr" and _expr(s))


def names(template):
    out = []
    for kind, s in _scan(template):
        if kind == "expr":
            n = _expr(s)[0]
            if n not in out:
                out.append(n)
    return out
''')

TPL_PHP = dd(r'''
<?php
final class TplLite
{
    private const WS = " \t\n\r";

    private static function isName(string $s): bool
    {
        return preg_match('/\A[A-Za-z_][A-Za-z0-9_.]*\z/', $s) === 1;
    }

    private static function vars(array $items): array
    {
        $env = [];
        foreach ($items as $item) {
            $pos = strpos($item, '=');
            if ($pos === false) throw new InvalidArgumentException('bad variable entry');
            $key = substr($item, 0, $pos);
            if (!self::isName($key)) throw new InvalidArgumentException('bad variable key');
            $env[$key] = substr($item, $pos + 1);
        }
        return $env;
    }

    private static function scan(string $t): array
    {
        $parts = [];
        $buf = '';
        $i = 0;
        $n = strlen($t);
        while ($i < $n) {
            if (substr($t, $i, 3) === '\\{{') {
                $buf .= '{{';
                $i += 3;
            } elseif (substr($t, $i, 2) === '{{') {
                $end = strpos($t, '}}', $i + 2);
                if ($end === false) throw new InvalidArgumentException('unterminated placeholder');
                if ($buf !== '') {
                    $parts[] = ['text', $buf];
                    $buf = '';
                }
                $parts[] = ['expr', substr($t, $i + 2, $end - $i - 2)];
                $i = $end + 2;
            } else {
                $buf .= $t[$i];
                $i++;
            }
        }
        if ($buf !== '') $parts[] = ['text', $buf];
        return $parts;
    }

    private static function expr(string $text): array
    {
        $pieces = array_map(fn($p) => trim($p, self::WS), explode('|', $text));
        foreach ($pieces as $p) {
            if ($p === '') throw new InvalidArgumentException('empty piece');
        }
        if (!self::isName($pieces[0])) throw new InvalidArgumentException('bad name');
        return [$pieces[0], array_slice($pieces, 1)];
    }

    private static function ascii(string $s, bool $up): string
    {
        return $up ? strtr($s, 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
                   : strtr($s, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz');
    }

    private static function apply(string $value, string $f): string
    {
        $pos = strpos($f, ':');
        $name = $pos === false ? $f : substr($f, 0, $pos);
        $arg = $pos === false ? null : substr($f, $pos + 1);
        if (in_array($name, ['upper', 'lower', 'trim', 'len'], true)) {
            if ($arg !== null) throw new InvalidArgumentException('filter takes no argument');
            if ($name === 'upper') return self::ascii($value, true);
            if ($name === 'lower') return self::ascii($value, false);
            if ($name === 'trim') return trim($value, self::WS);
            return (string)mb_strlen($value, 'UTF-8');
        }
        if ($name === 'pad') {
            $a = $arg === null ? '' : trim($arg, self::WS);
            if ($arg === null || preg_match('/\A[1-9][0-9]?\z/', $a) !== 1) throw new InvalidArgumentException('bad pad width');
            return str_repeat(' ', max(0, (int)$a - mb_strlen($value, 'UTF-8'))) . $value;
        }
        if ($name === 'default') {
            if ($arg === null) throw new InvalidArgumentException('default needs a value');
            return $value;
        }
        throw new InvalidArgumentException('unknown filter');
    }

    public static function render(string $template, array $vars): string
    {
        $env = self::vars($vars);
        $out = '';
        foreach (self::scan($template) as [$kind, $s]) {
            if ($kind === 'text') {
                $out .= $s;
                continue;
            }
            [$name, $filters] = self::expr($s);
            if (array_key_exists($name, $env)) {
                $value = $env[$name];
            } elseif ($filters && strpos($filters[0], ':') !== false && substr($filters[0], 0, strpos($filters[0], ':')) === 'default') {
                $value = trim(substr($filters[0], strpos($filters[0], ':') + 1), self::WS);
            } else {
                throw new InvalidArgumentException('missing variable ' . $name);
            }
            foreach ($filters as $f) $value = self::apply($value, $f);
            $out .= $value;
        }
        return $out;
    }

    public static function countPlaceholders(string $template): int
    {
        $n = 0;
        foreach (self::scan($template) as [$kind, $s]) {
            if ($kind === 'expr') {
                self::expr($s);
                $n++;
            }
        }
        return $n;
    }

    public static function names(string $template): array
    {
        $out = [];
        foreach (self::scan($template) as [$kind, $s]) {
            if ($kind === 'expr') {
                $name = self::expr($s)[0];
                if (!in_array($name, $out, true)) $out[] = $name;
            }
        }
        return $out;
    }
}
''')

TPL_GO = dd(r'''
package tpllite

import (
	"errors"
	"strconv"
	"strings"
	"unicode/utf8"
)

const ws = " \t\n\r"

var errBad = errors.New("tpllite: bad input")

func isName(s string) bool {
	if s == "" {
		return false
	}
	for i := 0; i < len(s); i++ {
		c := s[i]
		alpha := (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_'
		digit := (c >= '0' && c <= '9') || c == '.'
		if i == 0 && !alpha {
			return false
		}
		if !alpha && !digit {
			return false
		}
	}
	return true
}

func parseVars(items []string) (map[string]string, error) {
	env := map[string]string{}
	for _, item := range items {
		k, v, ok := strings.Cut(item, "=")
		if !ok || !isName(k) {
			return nil, errBad
		}
		env[k] = v
	}
	return env, nil
}

type part struct {
	expr bool
	text string
}

func scan(t string) ([]part, error) {
	var parts []part
	var buf strings.Builder
	i := 0
	for i < len(t) {
		switch {
		case strings.HasPrefix(t[i:], "\\{{"):
			buf.WriteString("{{")
			i += 3
		case strings.HasPrefix(t[i:], "{{"):
			end := strings.Index(t[i+2:], "}}")
			if end < 0 {
				return nil, errBad
			}
			if buf.Len() > 0 {
				parts = append(parts, part{false, buf.String()})
				buf.Reset()
			}
			parts = append(parts, part{true, t[i+2 : i+2+end]})
			i += 2 + end + 2
		default:
			buf.WriteByte(t[i])
			i++
		}
	}
	if buf.Len() > 0 {
		parts = append(parts, part{false, buf.String()})
	}
	return parts, nil
}

func parseExpr(text string) (string, []string, error) {
	pieces := strings.Split(text, "|")
	for i := range pieces {
		pieces[i] = strings.Trim(pieces[i], ws)
		if pieces[i] == "" {
			return "", nil, errBad
		}
	}
	if !isName(pieces[0]) {
		return "", nil, errBad
	}
	return pieces[0], pieces[1:], nil
}

func asciiMap(s string, up bool) string {
	b := []byte(s)
	for i, c := range b {
		if up && c >= 'a' && c <= 'z' {
			b[i] = c - 32
		} else if !up && c >= 'A' && c <= 'Z' {
			b[i] = c + 32
		}
	}
	return string(b)
}

func apply(value, f string) (string, error) {
	name, arg, hasArg := strings.Cut(f, ":")
	switch name {
	case "upper", "lower", "trim", "len":
		if hasArg {
			return "", errBad
		}
		switch name {
		case "upper":
			return asciiMap(value, true), nil
		case "lower":
			return asciiMap(value, false), nil
		case "trim":
			return strings.Trim(value, ws), nil
		}
		return strconv.Itoa(utf8.RuneCountInString(value)), nil
	case "pad":
		a := strings.Trim(arg, ws)
		if !hasArg || len(a) < 1 || len(a) > 2 || a[0] < '1' || a[0] > '9' || (len(a) == 2 && (a[1] < '0' || a[1] > '9')) {
			return "", errBad
		}
		n, _ := strconv.Atoi(a)
		if have := utf8.RuneCountInString(value); have < n {
			return strings.Repeat(" ", n-have) + value, nil
		}
		return value, nil
	case "default":
		if !hasArg {
			return "", errBad
		}
		return value, nil
	}
	return "", errBad
}

func Render(template string, vars []string) (string, error) {
	env, err := parseVars(vars)
	if err != nil {
		return "", err
	}
	parts, err := scan(template)
	if err != nil {
		return "", err
	}
	var out strings.Builder
	for _, p := range parts {
		if !p.expr {
			out.WriteString(p.text)
			continue
		}
		name, filters, err := parseExpr(p.text)
		if err != nil {
			return "", err
		}
		value, ok := env[name]
		if !ok {
			if len(filters) == 0 {
				return "", errBad
			}
			fname, farg, has := strings.Cut(filters[0], ":")
			if fname != "default" || !has {
				return "", errBad
			}
			value = strings.Trim(farg, ws)
		}
		for _, f := range filters {
			if value, err = apply(value, f); err != nil {
				return "", err
			}
		}
		out.WriteString(value)
	}
	return out.String(), nil
}

func CountPlaceholders(template string) (int64, error) {
	parts, err := scan(template)
	if err != nil {
		return 0, err
	}
	var n int64
	for _, p := range parts {
		if p.expr {
			if _, _, err := parseExpr(p.text); err != nil {
				return 0, err
			}
			n++
		}
	}
	return n, nil
}

func Names(template string) ([]string, error) {
	parts, err := scan(template)
	if err != nil {
		return nil, err
	}
	out := []string{}
	seen := map[string]bool{}
	for _, p := range parts {
		if p.expr {
			name, _, err := parseExpr(p.text)
			if err != nil {
				return nil, err
			}
			if !seen[name] {
				seen[name] = true
				out = append(out, name)
			}
		}
	}
	return out, nil
}
''')


def tpl_cases(rng):
    V = ["name=Ada", "city=  Oslo  ", "empty=", "eq=a=b=c", "emoji=\U0001F600", "uni=école", "n.1=dot", "_u=under", "Mixed=Case Text", "tab=\tx\t"]
    out = [("render", ["Hello {{ name }}!", V]), ("render", ["{{city|trim|upper}}", V]), ("render", ["{{missing|default:fallback}}", V]), ("render", ["\\{{ name }} is {{ name }}", V]),
           ("count_placeholders", ["a {{b}} \\{{c}} {{d}}"]), ("names", ["{{b}} {{a}} {{b}}"]), ("render", ["{{emoji|len}}", V]), ("render", ["{{name|pad:6}}|", V])]
    templates = [
        "", "plain text", "{{name}}", "{{ name }}", "{{\tname\n}}", "[{{name}}][{{city}}]", "{{name|upper}}", "{{uni|upper}}", "{{Mixed|lower}}", "{{Mixed|upper|lower}}", "{{city|trim}}", "{{city}}", "{{tab|trim}}", "{{tab|len}}",
        "{{emoji|len}}", "{{uni|len}}", "{{empty|len}}", "{{empty}}.", "{{eq}}", "{{eq|upper}}", "{{n.1}}", "{{_u|upper}}", "{{name|pad:3}}", "{{name|pad:10}}|", "{{emoji|pad:4}}|", "{{uni|pad: 7 }}|", "{{name|pad:0}}", "{{name|pad:00}}", "{{name|pad:100}}",
        "{{name|pad:05}}", "{{name|pad}}", "{{name|pad:}}", "{{name|pad:x}}", "{{name|upper:1}}", "{{name|len:}}", "{{name|bogus}}", "{{name|UPPER}}", "{{name|default}}", "{{name|default:z}}", "{{missing|default:z}}", "{{missing|default:  z z  }}",
        "{{missing|default:}}|", "{{missing|upper|default:z}}", "{{missing|default:abc|upper}}", "{{missing|default:abc|pad:6}}|", "{{missing}}", "{{missing|trim}}", "{{missing|default}}", "{{ missing | default : q }}", "{{missing |default:q}}",
        "{{missing|default:a:b}}", "{{missing|default:a=b}}", "{{ }}", "{{}}", "{{|upper}}", "{{name|}}", "{{name||upper}}", "{{ name | }}", "{{1a}}", "{{a-b}}", "{{a b}}", "{{é}}", "{{name", "{{name}", "name}}", "}}{{name}}{{", "{{name}}}}",
        "{{name}}{{city}}{{name}}", "\\{{name}}", "\\\\{{name}}", "\\{{{name}}}", "{{{name}}}", "a\\b{{name}}\\", "\\{", "\\{{", "x\\{{y", "{{name}} \\{{ {{name}} }}", "\\\\\\{{name}}", "{ {name} }", "{{name|upper}}{{name|lower}}", "{{n.1|upper}} {{_u}}",
        "line1\n{{name}}\nline3\r\n", "é{{name}}é", "\U0001F600{{emoji}}\U0001F600", "{{ Mixed | lower | pad:12 }}|", "{{name|trim|trim|upper|len}}", "{{emoji|len|pad:3}}", "{{city|len}}", "{{city|trim|len}}",
    ]
    for t in templates:
        out.append(("render", [t, V]))
        out.append(("count_placeholders", [t]))
        out.append(("names", [t]))
    for vs in [[], ["a"], ["a="], ["=a"], ["1a=b"], ["a b=c"], ["a=b", "a=c"], ["a=1", "b=2", "a=3"], ["é=x"], ["a.b=c"], ["a-b=c"], ["a=b\nc"], ["A=1", "a=2"]]:
        out.append(("render", ["{{a}}{{A}}", vs]))
        out.append(("render", ["plain", vs]))
    toks = ["{{a}}", "{{b|upper}}", "{{c|default:x}}", " ", "\\{{", "text", "}}", "{{", "é", "{{a|pad:4}}", "\U0001F600", "|", "{{ a | len }}", "{{b|trim}}"]
    for _ in range(40):
        t = "".join(rng.choice(toks) for _ in range(rng.randint(0, 8)))
        out.append(("render", [t, ["a=hello", "b= wor ld ", "d=é\U0001F600"]]))
        out.append(("count_placeholders", [t]))
        out.append(("names", [t]))
    return out


TPL = PortLib(
    slug="tpl-lite",
    title="a small template renderer",
    blurb="A mailer service fills message templates from key/value lists with a small, deliberately strict substitution language.",
    spec=TPL_SPEC,
    fns=TPL_FNS,
    impls={"python": {"tpl_lite.py": TPL_PY}, "php": {"src/TplLite.php": TPL_PHP}, "go": {"tpllite.go": TPL_GO}},
    cases=tpl_cases,
    difficulty=4,
    traps=["strict grammar", "ASCII-only case mapping", "length in code points", "narrow whitespace trimming (PHP trim defaults)", "error idioms"],
    tags=["templating", "strict-parsing"],
    pairs=[("python", "php", "full"), ("python", "go", "full"), ("go", "php", "stub"), ("php", "python", "stub")],
    diff_adj={"python>php": 0},
)
register_port(TPL, __name__)
