"""Text-format libraries (python), batch: env-file dialect, query strings, layered config."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# stashenv: an env-file dialect with append / set-if-absent operators and ${X:-d} expansion
# ======================================================================================================================
STASH_README = dd(r'''
    # stashenv

    Reader for the `.stash` environment files used by the deploy scripts. It is a small dialect of its own.

    ## `parse_env(text, base=None) -> dict`

    `text` is the whole file; `base` is an optional mapping of already-existing variables (it is read, never changed
    and never copied into the result). The result maps each variable defined by the file to its final value, in the
    order of first definition.

    ### Lines
    * Blank lines and lines whose first non-space character is `#` are ignored. Lines may end in `\n` or `\r\n`.
    * Otherwise a line is `[export ]NAME<op>VALUE`. `NAME` is `[A-Za-z_][A-Za-z0-9_]*`. The optional `export` keyword
      (followed by whitespace) is ignored. Spaces around `NAME` and around the operator are allowed and ignored.
    * `<op>` is one of
      * `=` set the variable (replacing any earlier value);
      * `?=` set the variable only if it is not defined yet, neither by an earlier line nor in `base`;
      * `+=` append: if the variable currently has a non-empty value (an earlier line, else `base`), the new value is
        that value, one space, and VALUE; otherwise just VALUE.
    * A line with a non-blank remainder that does not fit this shape (no operator, bad name) is a `ValueError` whose
      message starts with `line N:` (N counts from 1).
    * A value never spans lines.

    ### Values
    * Unquoted: runs from the first non-space character after the operator up to the end of the line, or up to the
      first `#` that is preceded by whitespace (a trailing comment); trailing whitespace is removed. `${...}`
      expansions apply; backslashes are literal.
    * Single-quoted `'...'`: taken literally, no expansion, no escapes; ends at the next `'`.
    * Double-quoted `"..."`: `${...}` expansion applies, and a backslash escapes: `\n` newline, `\t` tab, `\"`, `\\`
      and `\$` (a literal dollar sign that is not expanded). Any other backslash sequence is kept as is (both
      characters).
    * After a closing quote only whitespace or a `#` comment may follow, otherwise `ValueError` (`line N: ...`). A
      missing closing quote is a `ValueError` too.

    ### Expansion (unquoted and double-quoted values)
    * `$$` is a literal `$`.
    * `${NAME}` is the current value of `NAME` (earlier lines first, then `base`), or the empty string if undefined.
    * `${NAME:-text}` is `text` when `NAME` is undefined **or empty**; `${NAME-text}` only when it is undefined.
      `text` is taken literally (it ends at the first `}`), no nested expansion.
    * A lone `$` that does not start one of the forms above is kept literally. A `${` without `}` or with an invalid
      body is a `ValueError`.
    * Expansion sees the variable values as they are at the moment the line is read.
''')

STASH_SRC = dd(r'''
    """The .stash environment-file dialect."""
    import re

    _LINE = re.compile(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(\?=|\+=|=)(.*)", re.S)
    _EXPR = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:(:-|-)(.*))?", re.S)
    _ESC = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "$": "$"}


    def _current(name, env, base):
        if name in env:
            return True, env[name]
        if base and name in base:
            return True, base[name]
        return False, ""


    def _expand_at(text, i, env, base):
        """text[i] == '$'. Returns (replacement, next_index)."""
        if text.startswith("$$", i):
            return "$", i + 2
        if not text.startswith("${", i):
            return "$", i + 1
        end = text.find("}", i + 2)
        if end < 0:
            raise ValueError("unterminated ${")
        m = _EXPR.fullmatch(text[i + 2:end])
        if not m:
            raise ValueError("bad expansion: ${%s}" % text[i + 2:end])
        name, op, default = m.groups()
        defined, val = _current(name, env, base)
        if op == ":-" and val == "":
            val = default
        elif op == "-" and not defined:
            val = default
        return val, end + 1


    def _read_quoted(raw, env, base):
        """raw[0] is a double quote. Returns (value, index after closing quote)."""
        out = []
        i = 1
        while i < len(raw):
            c = raw[i]
            if c == "\\" and i + 1 < len(raw):
                nxt = raw[i + 1]
                out.append(_ESC.get(nxt, "\\" + nxt))
                i += 2
            elif c == "$":
                rep, i = _expand_at(raw, i, env, base)
                out.append(rep)
            elif c == '"':
                return "".join(out), i + 1
            else:
                out.append(c)
                i += 1
        raise ValueError("unterminated quote")


    def _read_unquoted(raw, env, base):
        m = re.search(r"\s#", raw)
        if m:
            raw = raw[:m.start()]
        raw = raw.rstrip()
        out = []
        i = 0
        while i < len(raw):
            if raw[i] == "$":
                rep, i = _expand_at(raw, i, env, base)
                out.append(rep)
            else:
                out.append(raw[i])
                i += 1
        return "".join(out)


    def _value(raw, env, base):
        raw = raw.strip()
        if raw.startswith("'"):
            end = raw.find("'", 1)
            if end < 0:
                raise ValueError("unterminated quote")
            value, rest = raw[1:end], raw[end + 1:]
        elif raw.startswith('"'):
            value, end = _read_quoted(raw, env, base)
            rest = raw[end:]
        else:
            return _read_unquoted(raw, env, base)
        rest = rest.strip()
        if rest and not rest.startswith("#"):
            raise ValueError("unexpected text after closing quote")
        return value


    def parse_env(text, base=None):
        env = {}
        for no, line in enumerate(text.splitlines(), 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            m = _LINE.fullmatch(line)
            if not m:
                raise ValueError("line %d: cannot parse %r" % (no, line.strip()))
            name, op, raw = m.groups()
            try:
                if op == "?=":
                    if _current(name, env, base)[0]:
                        continue
                    env[name] = _value(raw, env, base)
                elif op == "+=":
                    value = _value(raw, env, base)
                    old = _current(name, env, base)[1]
                    env[name] = (old + " " + value) if old else value
                else:
                    env[name] = _value(raw, env, base)
            except ValueError as exc:
                raise ValueError("line %d: %s" % (no, exc)) from None
        return env
''')

STASH_VISIBLE = dd(r'''
    import unittest

    from stashenv import parse_env


    class BasicTests(unittest.TestCase):
        def test_simple(self):
            self.assertEqual(parse_env("A=1\nB = two words  \n# note\n"), {"A": "1", "B": "two words"})

        def test_expansion(self):
            self.assertEqual(parse_env("A=x\nB=${A}y\n"), {"A": "x", "B": "xy"})

        def test_single_quotes_literal(self):
            self.assertEqual(parse_env("A='${B} #1'\n"), {"A": "${B} #1"})


    if __name__ == "__main__":
        unittest.main()
''')

STASH_HIDDEN = dd(r'''
    import unittest

    from stashenv import parse_env


    class Lines(unittest.TestCase):
        def test_comments_blank_and_endings(self):
            text = "\n# c\n   # indented\nA=1\r\nB=2\r\n\r\n"
            self.assertEqual(parse_env(text), {"A": "1", "B": "2"})

        def test_export_and_spaces(self):
            self.assertEqual(parse_env("export A=1\nexport   B  =  2\n  C=3\nexportD=4\n"),
                             {"A": "1", "B": "2", "C": "3", "exportD": "4"})

        def test_order_of_first_definition(self):
            self.assertEqual(list(parse_env("B=1\nA=2\nB=3\n")), ["B", "A"])
            self.assertEqual(parse_env("B=1\nA=2\nB=3\n")["B"], "3")

        def test_empty_value(self):
            self.assertEqual(parse_env("A=\nB=  \nC=''\n"), {"A": "", "B": "", "C": ""})

        def test_errors_carry_line_number(self):
            for text, n in (("A=1\nnonsense\n", 2), ("1A=2\n", 1), ("\n\n=x\n", 3), ("A=1\nB=1\nC 1\n", 3), ("A-B=1\n", 1)):
                with self.assertRaises(ValueError) as cm:
                    parse_env(text)
                self.assertTrue(str(cm.exception).startswith("line %d:" % n), str(cm.exception))

        def test_value_errors_carry_line_number(self):
            for text, n in (("A=1\nB='open\n", 2), ('X="open\n', 1), ('A="x" y\n', 1), ("\nA='x'z\n", 2), ("A=${B\n", 1),
                            ("A=1\nB=${1x}\n", 2)):
                with self.assertRaises(ValueError) as cm:
                    parse_env(text)
                self.assertTrue(str(cm.exception).startswith("line %d:" % n), str(cm.exception))


    class Values(unittest.TestCase):
        def test_unquoted_comment(self):
            self.assertEqual(parse_env("A=hello # world\n"), {"A": "hello"})
            self.assertEqual(parse_env("A=hello#world\n"), {"A": "hello#world"})
            self.assertEqual(parse_env("A=x     # c\nB=y \n"), {"A": "x", "B": "y"})
            self.assertEqual(parse_env("A=\tx\t#c\n"), {"A": "x"})
            self.assertEqual(parse_env("A=# whole\n"), {"A": "# whole"})

        def test_unquoted_keeps_inner_quotes_and_backslashes(self):
            self.assertEqual(parse_env("A=it's \\n here\n"), {"A": "it's \\n here"})
            self.assertEqual(parse_env("A=a=b=c\n"), {"A": "a=b=c"})

        def test_single_quotes(self):
            self.assertEqual(parse_env("A='a\\nb $X ${Y}'\n"), {"A": "a\\nb $X ${Y}"})
            self.assertEqual(parse_env("A='x'   # c\n"), {"A": "x"})
            self.assertEqual(parse_env("A='x' #c\nB=1\n"), {"A": "x", "B": "1"})
            self.assertEqual(parse_env("A='say \"hi\"'\n"), {"A": 'say "hi"'})
            self.assertEqual(parse_env("A='  padded  '\n"), {"A": "  padded  "})

        def test_double_quote_escapes(self):
            self.assertEqual(parse_env(r'A="a\nb\tc"' + "\n"), {"A": "a\nb\tc"})
            self.assertEqual(parse_env(r'A="say \"hi\" \\ \$X"' + "\n"), {"A": 'say "hi" \\ $X'})
            self.assertEqual(parse_env(r'A="\q\x"' + "\n"), {"A": "\\q\\x"})
            self.assertEqual(parse_env('A="keeps  # hash and  spaces "\n'), {"A": "keeps  # hash and  spaces "})
            self.assertEqual(parse_env('A="x"  # c\n'), {"A": "x"})
            self.assertEqual(parse_env('A="x"#c\n'), {"A": "x"})

        def test_escaped_dollar_is_not_expanded(self):
            self.assertEqual(parse_env('B=1\nA="\\${B} ${B}"\n'), {"B": "1", "A": "${B} 1"})

        def test_trailing_backslash_in_quotes(self):
            with self.assertRaises(ValueError):
                parse_env('A="abc\\\n')


    class Expansion(unittest.TestCase):
        def test_plain(self):
            self.assertEqual(parse_env("A=1\nB=${A}-${A}\n"), {"A": "1", "B": "1-1"})
            self.assertEqual(parse_env('A=1\nB="<${A}>"\n')["B"], "<1>")

        def test_undefined_is_empty(self):
            self.assertEqual(parse_env("B=[${NOPE}]\n"), {"B": "[]"})

        def test_base_is_visible_but_not_returned(self):
            base = {"HOME": "/h", "A": "base"}
            got = parse_env("P=${HOME}/x\nQ=${A}\n", base)
            self.assertEqual(got, {"P": "/h/x", "Q": "base"})
            self.assertEqual(base, {"HOME": "/h", "A": "base"})

        def test_file_beats_base(self):
            self.assertEqual(parse_env("A=file\nB=${A}\n", {"A": "base"}), {"A": "file", "B": "file"})

        def test_default_colon_dash(self):
            self.assertEqual(parse_env("A=${X:-d}\n"), {"A": "d"})
            self.assertEqual(parse_env("X=\nA=${X:-d}\n")["A"], "d")
            self.assertEqual(parse_env("X=v\nA=${X:-d}\n")["A"], "v")
            self.assertEqual(parse_env("A=${X:-}\n"), {"A": ""})

        def test_default_dash(self):
            self.assertEqual(parse_env("A=${X-d}\n"), {"A": "d"})
            self.assertEqual(parse_env("X=\nA=${X-d}\n")["A"], "")
            self.assertEqual(parse_env("A=${X-d}\n", {"X": ""}), {"A": ""})
            self.assertEqual(parse_env("A=${X:-d}\n", {"X": ""}), {"A": "d"})
            self.assertEqual(parse_env("A=${X-d}\n", {"X": "q"}), {"A": "q"})

        def test_default_is_literal(self):
            self.assertEqual(parse_env("Y=1\nA=${X:-${Y}\n"), {"Y": "1", "A": "${Y"})
            self.assertEqual(parse_env("A=${X:-$Y}\n"), {"A": "$Y"})

        def test_dollar_forms(self):
            self.assertEqual(parse_env("A=$$HOME\n"), {"A": "$HOME"})
            self.assertEqual(parse_env("A=cost $5 and $\n"), {"A": "cost $5 and $"})
            self.assertEqual(parse_env("A=$$${B}\n"), {"A": "$"})
            self.assertEqual(parse_env('A="$$"\n'), {"A": "$"})

        def test_expansion_sees_current_value(self):
            self.assertEqual(parse_env("A=1\nB=${A}\nA=2\nC=${A}\n"), {"A": "2", "B": "1", "C": "2"})

        def test_self_reference(self):
            self.assertEqual(parse_env("A=x\nA=${A}y\nA=${A}z\n"), {"A": "xyz"})

        def test_expansion_inside_text_with_spaces(self):
            self.assertEqual(parse_env("A=one\nB=a ${A} b # tail\n"), {"A": "one", "B": "a one b"})

        def test_bad_bodies(self):
            for body in ("${}", "${1}", "${a b}", "${a:b}", "${a:-b"):
                with self.assertRaises(ValueError):
                    parse_env("A=" + body + "\n")


    class Operators(unittest.TestCase):
        def test_set_if_absent(self):
            self.assertEqual(parse_env("A=1\nA?=2\nB?=3\n"), {"A": "1", "B": "3"})
            self.assertEqual(parse_env("B?=1\nB?=2\n"), {"B": "1"})

        def test_set_if_absent_respects_base_and_empty(self):
            self.assertEqual(parse_env("A?=x\n", {"A": "base"}), {})
            self.assertEqual(parse_env("A?=x\n", {"A": ""}), {})
            self.assertEqual(parse_env("A=\nA?=x\n"), {"A": ""})
            self.assertEqual(parse_env("B?=x\n", {"A": "1"}), {"B": "x"})

        def test_append(self):
            self.assertEqual(parse_env("P=a\nP+=b\nP+=c d\n"), {"P": "a b c d"})
            self.assertEqual(parse_env("P+=b\n"), {"P": "b"})
            self.assertEqual(parse_env("P=\nP+=b\n"), {"P": "b"})
            self.assertEqual(parse_env("P=a\nP+=\n"), {"P": "a "})

        def test_append_uses_base(self):
            self.assertEqual(parse_env("PATH+=/x\n", {"PATH": "/bin"}), {"PATH": "/bin /x"})
            self.assertEqual(parse_env("PATH+=/x\nPATH+=/y\n", {"PATH": "/bin"}), {"PATH": "/bin /x /y"})
            self.assertEqual(parse_env("A+=1\n", {"A": ""}), {"A": "1"})

        def test_append_expands_new_part_only(self):
            self.assertEqual(parse_env("X=1\nP='${X}'\nP+=${X}\n")["P"], "${X} 1")
            self.assertEqual(parse_env("X=1\nP=\"$$\"\nP+=${X}\n")["P"], "$ 1")

        def test_operator_spacing(self):
            self.assertEqual(parse_env("A = 1\nA += 2\nB ?= 3\n"), {"A": "1 2", "B": "3"})
            self.assertEqual(parse_env("export A+=2\n", {"A": "1"}), {"A": "1 2"})


    if __name__ == "__main__":
        unittest.main()
''')

STASH = Lib(
    name="stashenv", lang="python", title="the `.stash` env-file reader (`stashenv.py`)",
    blurb="The deploy scripts read their settings from `.stash` environment files through this module.",
    files={"stashenv.py": STASH_SRC, "README.md": STASH_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": STASH_VISIBLE},
    hidden_tests={"tests/test_full.py": STASH_HIDDEN},
    mutate=["stashenv.py"], difficulty=3, tags=["config", "parsing"],
    probes=[
        'parse_env("A=${X:-d}\\nB=${Y-e}\\n", {"X": ""})',
        'parse_env("A=hello # world\\nB=a#b\\n")',
        'parse_env("A=\\"x\\\\ty\\\\\\\\ \\\\$Z\\"\\n")',
        'parse_env("A?=1\\nA?=2\\nB+=3\\nB+=4\\n", {"B": "0"})',
        'parse_env("A=1\\nB=${A}\\nA=2\\nC=${A}\\n")',
        'parse_env("A=$$x $y\\n")',
        'parse_env("A=\'${Q} # k\'  # tail\\n")',
        'parse_env("export  A = 1\\n\\n# c\\n  B=2\\r\\n")',
    ],
    probe_import="from stashenv import *",
)


# ======================================================================================================================
# querybag: query-string decoding, structured parsing, canonical form
# ======================================================================================================================
QB_README = dd(r"""
    # querybag

    Query-string helpers for the gateway: decode, structured parse, canonical form and building.

    ## `decode(text) -> str` / `encode(text) -> str`
    * `decode`: `+` becomes a space; `%XX` (two hex digits, either case) is one byte; all bytes are then read as UTF-8
      with undecodable bytes replaced by U+FFFD. A `%` not followed by two hex digits stays a literal `%`.
    * `encode`: the text as UTF-8; the bytes `A-Z a-z 0-9 - . _ ~` are kept, every other byte becomes `%XX` with
      upper-case hex digits (a space is `%20`, never `+`).

    ## `parse(qs) -> dict`
    One leading `?` is ignored. The string is split on `&`; empty segments and segments with an empty (raw) key are
    skipped. A segment is `key=value` (split at the first `=`); without `=` the value is `""`. Key and value are
    decoded. Then, in order of appearance (the dict keeps first-appearance order of its keys):

    * `name=v` plain key: the first occurrence stores a `str`; further occurrences turn the value into a list that
      keeps the order of appearance.
    * `name[]=v`: always a list; appended to whatever list `name` already has (a scalar already stored is first
      turned into a one-element list).
    * `name[sub]=v` (`sub` non-empty, no brackets inside; `name` is everything before the *last* bracket pair): the value
      of `name` is a `dict` and `dict[sub] = v` (a repeated `sub` keeps the last value).
    * Mixing a dict-valued `name` with plain or `[]` use of the same `name` is a `ValueError`.

    ## `first(params, key, default=None)`
    The scalar value of `key`, or the first item of a list; `default` for a missing key, an empty list or a dict value.

    ## `get_int(params, key, default=0, minimum=None, maximum=None) -> int`
    `first(...)` read as a decimal integer (surrounding whitespace allowed, optional `+`/`-` sign). When missing or not
    an integer the result is `default`. The result, `default` included, is then raised to `minimum` and lowered to
    `maximum` when those are given.

    ## `normalize(qs, drop=(), drop_empty=False) -> str`
    The canonical flat form: decode every pair (same splitting rules as `parse`), remove pairs whose decoded key equals
    an entry of `drop` (an entry ending in `*` matches every key that starts with the text before the `*`), remove
    pairs with an empty value when `drop_empty` is true, stable-sort the rest by decoded key (code point order; equal
    keys keep their relative order), then write each pair as `encode(key)=encode(value)` joined by `&` (a pair
    without value is written `key=`). Nothing remains: the empty string.

    ## `build(params) -> str`
    The inverse of `parse` for dict inputs: keys in sorted order; a `str` value gives `key=value`; a list gives one
    `key[]=item` per item in order; a dict gives `key[sub]=value` for its sorted sub-keys. Items are converted with
    `str()`; `None` values (also inside lists and dicts) are skipped. Keys, sub-keys and values are `encode`d, the `[` `]`
    that express structure are written literally.
""")

QB_SRC = dd(r"""
    """ + '"""' + r"""Query-string helpers.""" + '"""' + r"""
    import re

    _UNRESERVED = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
    _HEX = "0123456789abcdefABCDEF"
    _BRACKET = re.compile(r"(.+?)\[([^\[\]]*)\]")
    _INT = re.compile(r"[+-]?\d+")


    def decode(text):
        out = bytearray()
        i = 0
        while i < len(text):
            c = text[i]
            hexpair = text[i + 1:i + 3]
            if c == "%" and len(hexpair) == 2 and all(h in _HEX for h in hexpair):
                out.append(int(hexpair, 16))
                i += 3
            elif c == "+":
                out.append(32)
                i += 1
            else:
                out += c.encode("utf-8")
                i += 1
        return out.decode("utf-8", "replace")


    def encode(text):
        out = []
        for b in text.encode("utf-8"):
            out.append(chr(b) if b in _UNRESERVED else "%%%02X" % b)
        return "".join(out)


    def _pairs(qs):
        if qs.startswith("?"):
            qs = qs[1:]
        out = []
        for seg in qs.split("&"):
            key, _, value = seg.partition("=")
            if not key:
                continue
            out.append((decode(key), decode(value)))
        return out


    def parse(qs):
        out = {}
        for key, value in _pairs(qs):
            m = _BRACKET.fullmatch(key)
            if m and m.group(2) == "":
                name = m.group(1)
                cur = out.get(name)
                if isinstance(cur, dict):
                    raise ValueError("conflicting use of %r" % name)
                if cur is None:
                    out[name] = [value]
                elif isinstance(cur, list):
                    cur.append(value)
                else:
                    out[name] = [cur, value]
            elif m:
                name, sub = m.group(1), m.group(2)
                cur = out.setdefault(name, {})
                if not isinstance(cur, dict):
                    raise ValueError("conflicting use of %r" % name)
                cur[sub] = value
            else:
                cur = out.get(key)
                if cur is None:
                    out[key] = value
                elif isinstance(cur, dict):
                    raise ValueError("conflicting use of %r" % key)
                elif isinstance(cur, list):
                    cur.append(value)
                else:
                    out[key] = [cur, value]
        return out


    def first(params, key, default=None):
        v = params.get(key)
        if isinstance(v, list):
            return v[0] if v else default
        if v is None or isinstance(v, dict):
            return default
        return v


    def get_int(params, key, default=0, minimum=None, maximum=None):
        raw = first(params, key)
        if raw is None or not _INT.fullmatch(raw.strip()):
            n = default
        else:
            n = int(raw)
        if minimum is not None and n < minimum:
            n = minimum
        if maximum is not None and n > maximum:
            n = maximum
        return n


    def _matches(key, patterns):
        for p in patterns:
            if p.endswith("*"):
                if key.startswith(p[:-1]):
                    return True
            elif key == p:
                return True
        return False


    def normalize(qs, drop=(), drop_empty=False):
        pairs = [(k, v) for k, v in _pairs(qs) if not _matches(k, drop) and not (drop_empty and v == "")]
        pairs.sort(key=lambda kv: kv[0])
        return "&".join(encode(k) + "=" + encode(v) for k, v in pairs)


    def build(params):
        parts = []
        for key in sorted(params):
            value = params[key]
            k = encode(key)
            if value is None:
                continue
            if isinstance(value, dict):
                for sub in sorted(value):
                    if value[sub] is not None:
                        parts.append("%s[%s]=%s" % (k, encode(sub), encode(str(value[sub]))))
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if item is not None:
                        parts.append("%s[]=%s" % (k, encode(str(item))))
            else:
                parts.append("%s=%s" % (k, encode(str(value))))
        return "&".join(parts)
""")

QB_VISIBLE = dd(r"""
    import unittest

    from querybag import decode, encode, parse


    class BasicTests(unittest.TestCase):
        def test_decode(self):
            self.assertEqual(decode("a+b%20c%C3%A9"), "a b cé")

        def test_encode(self):
            self.assertEqual(encode("a b/c"), "a%20b%2Fc")

        def test_parse_repeated(self):
            self.assertEqual(parse("a=1&b=2&a=3"), {"a": ["1", "3"], "b": "2"})


    if __name__ == "__main__":
        unittest.main()
""")

QB_HIDDEN = dd(r"""
    import unittest

    from querybag import build, decode, encode, first, get_int, normalize, parse


    class Decode(unittest.TestCase):
        def test_plus_and_percent(self):
            self.assertEqual(decode("a+b"), "a b")
            self.assertEqual(decode("a%2bb"), "a+b")
            self.assertEqual(decode("%41%62%7e%7E"), "Ab~~")
            self.assertEqual(decode("%2B+%2b"), "+ +")

        def test_utf8(self):
            self.assertEqual(decode("%C3%A9%e2%82%ac"), "é€")
            self.assertEqual(decode("café"), "café")
            self.assertEqual(decode("%F0%9F%99%82"), "\U0001F642")

        def test_bad_sequences_stay_literal(self):
            self.assertEqual(decode("100%"), "100%")
            self.assertEqual(decode("%"), "%")
            self.assertEqual(decode("%4"), "%4")
            self.assertEqual(decode("%zz"), "%zz")
            self.assertEqual(decode("%4g"), "%4g")
            self.assertEqual(decode("%g4"), "%g4")
            self.assertEqual(decode("5%%41"), "5%A")
            self.assertEqual(decode("%2"), "%2")
            self.assertEqual(decode("a%41"), "aA")

        def test_invalid_utf8_replaced(self):
            self.assertEqual(decode("a%FFb"), "a�b")
            self.assertEqual(decode("%C3"), "�")

        def test_empty(self):
            self.assertEqual(decode(""), "")


    class Encode(unittest.TestCase):
        def test_unreserved_kept(self):
            s = "ABCxyz0189-._~"
            self.assertEqual(encode(s), s)

        def test_reserved_and_space(self):
            self.assertEqual(encode("a b"), "a%20b")
            self.assertEqual(encode("a+b&c=d/e?f#g"), "a%2Bb%26c%3Dd%2Fe%3Ff%23g")
            self.assertEqual(encode("[]*!'()%"), "%5B%5D%2A%21%27%28%29%25")
            self.assertEqual(encode("é"), "%C3%A9")
            self.assertEqual(encode("€"), "%E2%82%AC")
            self.assertEqual(encode("\n\x7f"), "%0A%7F")
            self.assertEqual(encode(""), "")

        def test_round_trip(self):
            for s in ("a b+c", "100%", "é€\U0001F642", "x=y&z", "%41"):
                self.assertEqual(decode(encode(s)), s)


    class Parse(unittest.TestCase):
        def test_basic(self):
            self.assertEqual(parse("a=1&b=2"), {"a": "1", "b": "2"})
            self.assertEqual(parse(""), {})
            self.assertEqual(parse("?a=1"), {"a": "1"})
            self.assertEqual(parse("??a=1"), {"?a": "1"})
            self.assertEqual(parse("?"), {})

        def test_value_forms(self):
            self.assertEqual(parse("flag&e=&x=a=b"), {"flag": "", "e": "", "x": "a=b"})

        def test_skips(self):
            self.assertEqual(parse("&&a=1&&=zz&b=2&"), {"a": "1", "b": "2"})
            self.assertEqual(parse("=only"), {})

        def test_decoding(self):
            self.assertEqual(parse("k%20ey=v+w&%C3%A9=%C3%A9"), {"k ey": "v w", "é": "é"})
            self.assertEqual(parse("%2B=%26&a%3Db=c"), {"+": "&", "a=b": "c"})

        def test_repeated_plain(self):
            self.assertEqual(parse("a=1&a=2&a=3"), {"a": ["1", "2", "3"]})
            self.assertEqual(parse("a&a=&a=x"), {"a": ["", "", "x"]})

        def test_key_order_is_first_appearance(self):
            self.assertEqual(list(parse("b=1&a=1&b=2&c=1")), ["b", "a", "c"])

        def test_list_keys(self):
            self.assertEqual(parse("t[]=x"), {"t": ["x"]})
            self.assertEqual(parse("t[]=x&t[]=y&u=1"), {"t": ["x", "y"], "u": "1"})
            self.assertEqual(parse("t=a&t[]=b"), {"t": ["a", "b"]})
            self.assertEqual(parse("t[]=a&t=b&t=c"), {"t": ["a", "b", "c"]})
            self.assertEqual(parse("t%5B%5D=a"), {"t": ["a"]})

        def test_nested(self):
            self.assertEqual(parse("f[s]=open&f[tag]=x"), {"f": {"s": "open", "tag": "x"}})
            self.assertEqual(parse("f[s]=1&f[s]=2"), {"f": {"s": "2"}})
            self.assertEqual(parse("a[b]=1&c=2&a[d]=3"), {"a": {"b": "1", "d": "3"}, "c": "2"})
            self.assertEqual(list(parse("z=1&a[b]=1")), ["z", "a"])

        def test_nested_last_bracket_pair(self):
            self.assertEqual(parse("a[b][c]=1"), {"a[b]": {"c": "1"}})
            self.assertEqual(parse("a[b]x=1"), {"a[b]x": "1"})
            self.assertEqual(parse("[b]=1"), {"[b]": "1"})
            self.assertEqual(parse("a[=1"), {"a[": "1"})

        def test_conflicts(self):
            for qs in ("a=1&a[b]=2", "a[b]=2&a=1", "a[b]=2&a[]=1", "a[]=1&a[b]=2", "a=1&a=2&a[b]=3", "a[b]=1&a=1&a=2"):
                with self.assertRaises(ValueError, msg=qs):
                    parse(qs)


    class First(unittest.TestCase):
        def test_values(self):
            p = parse("a=1&b=2&b=3&c[x]=1&e[]=z")
            self.assertEqual(first(p, "a"), "1")
            self.assertEqual(first(p, "b"), "2")
            self.assertEqual(first(p, "e"), "z")
            self.assertEqual(first(p, "c"), None)
            self.assertEqual(first(p, "c", "d"), "d")
            self.assertEqual(first(p, "nope", 7), 7)
            self.assertEqual(first({"k": []}, "k", "dflt"), "dflt")
            self.assertEqual(first({"k": ""}, "k", "dflt"), "")


    class GetInt(unittest.TestCase):
        def test_parsing(self):
            p = parse("a=12&b=-3&c=+4&d=%2012%20&e=x&f=&g=1.5&h=1&h=9&i=0&j=007")
            self.assertEqual(get_int(p, "a"), 12)
            self.assertEqual(get_int(p, "b"), -3)
            self.assertEqual(get_int(p, "c"), 4)
            self.assertEqual(get_int(p, "d"), 12)
            self.assertEqual(get_int(p, "e", 5), 5)
            self.assertEqual(get_int(p, "f", 6), 6)
            self.assertEqual(get_int(p, "g", 7), 7)
            self.assertEqual(get_int(p, "h"), 1)
            self.assertEqual(get_int(p, "i", 9), 0)
            self.assertEqual(get_int(p, "j"), 7)
            self.assertEqual(get_int(p, "missing"), 0)
            self.assertEqual(get_int(p, "missing", 3), 3)
            self.assertEqual(get_int({"k": {"a": "1"}}, "k", 8), 8)

        def test_clamping(self):
            p = parse("a=50&b=-50&c=5")
            self.assertEqual(get_int(p, "a", maximum=10), 10)
            self.assertEqual(get_int(p, "b", minimum=-10), -10)
            self.assertEqual(get_int(p, "c", minimum=5, maximum=5), 5)
            self.assertEqual(get_int(p, "c", minimum=1, maximum=9), 5)
            self.assertEqual(get_int(p, "c", minimum=6), 6)
            self.assertEqual(get_int(p, "c", maximum=4), 4)
            self.assertEqual(get_int(p, "a", minimum=1, maximum=100), 50)

        def test_default_is_clamped_too(self):
            self.assertEqual(get_int({}, "x", default=500, maximum=100), 100)
            self.assertEqual(get_int({}, "x", default=-5, minimum=0), 0)
            self.assertEqual(get_int({"x": "oops"}, "x", default=500, maximum=100), 100)


    class Normalize(unittest.TestCase):
        def test_sorted_and_stable(self):
            self.assertEqual(normalize("b=2&a=1&b=1&a=0"), "a=1&a=0&b=2&b=1")

        def test_code_point_order(self):
            self.assertEqual(normalize("b=1&B=2&a=3&_=4&1=5"), "1=5&B=2&_=4&a=3&b=1")

        def test_reencoding(self):
            self.assertEqual(normalize("k+1=a+b&k%2d2=%7e&q=%c3%a9"), "k%201=a%20b&k-2=~&q=%C3%A9")
            self.assertEqual(normalize("a=%2f&b=/"), "a=%2F&b=%2F")
            self.assertEqual(normalize("x=a%3Db"), "x=a%3Db")

        def test_flags_and_empty(self):
            self.assertEqual(normalize("flag&a=1"), "a=1&flag=")
            self.assertEqual(normalize("?a=1&&b="), "a=1&b=")
            self.assertEqual(normalize(""), "")

        def test_drop_exact_and_prefix(self):
            qs = "a=1&utm_source=x&utm_medium=y&utmx=3&b=2"
            self.assertEqual(normalize(qs, drop=["utm_*"]), "a=1&b=2&utmx=3")
            self.assertEqual(normalize(qs, drop=["utm*"]), "a=1&b=2")
            self.assertEqual(normalize(qs, drop=["a", "b"]), "utm_medium=y&utm_source=x&utmx=3")
            self.assertEqual(normalize(qs, drop=["utm_source"]), "a=1&b=2&utm_medium=y&utmx=3")
            self.assertEqual(normalize("a=1&ab=2", drop=["a"]), "ab=2")
            self.assertEqual(normalize("a=1&ab=2", drop=["a*"]), "")
            self.assertEqual(normalize("a=1", drop=["*"]), "")

        def test_drop_matches_decoded_key(self):
            self.assertEqual(normalize("a%5F1=x&b=2", drop=["a_1"]), "b=2")

        def test_drop_empty(self):
            self.assertEqual(normalize("a=&b=1&c&d=%20", drop_empty=True), "b=1&d=%20")
            self.assertEqual(normalize("a=&b=1", drop_empty=False), "a=&b=1")

        def test_drop_and_drop_empty_together(self):
            self.assertEqual(normalize("a=&b=1&c=2", drop=["c"], drop_empty=True), "b=1")


    class Build(unittest.TestCase):
        def test_scalars_sorted(self):
            self.assertEqual(build({"b": "2", "a": "1"}), "a=1&b=2")
            self.assertEqual(build({"a": "1", "b": "2"}), "a=1&b=2")
            self.assertEqual(build({}), "")
            self.assertEqual(build({"n": 5, "t": True}), "n=5&t=True")

        def test_lists_keep_order(self):
            self.assertEqual(build({"t": ["z", "a"], "u": "1"}), "t[]=z&t[]=a&u=1")
            self.assertEqual(build({"t": ("x",)}), "t[]=x")
            self.assertEqual(build({"t": []}), "")

        def test_dicts_sorted(self):
            self.assertEqual(build({"f": {"b": "2", "a": "1"}}), "f[a]=1&f[b]=2")
            self.assertEqual(build({"f": {"a": "1", "b": "2"}}), "f[a]=1&f[b]=2")

        def test_none_skipped(self):
            self.assertEqual(build({"a": None, "b": "1", "c": ["x", None, "y"], "d": {"k": None, "j": "1"}}),
                             "b=1&c[]=x&c[]=y&d[j]=1")

        def test_encoding(self):
            self.assertEqual(build({"a b": "c&d", "[x]": "é"}), "%5Bx%5D=%C3%A9&a%20b=c%26d")
            self.assertEqual(build({"f": {"a b": "x y"}}), "f[a%20b]=x%20y")
            self.assertEqual(build({"l": ["a b"]}), "l[]=a%20b")

        def test_round_trip(self):
            d = {"a": "1", "t": ["x y", "z"], "f": {"k": "v&w", "j": ""}, "e": ""}
            back = parse(build(d))
            self.assertEqual(back, d)


    if __name__ == "__main__":
        unittest.main()
""")

QB = Lib(
    name="querybag", lang="python", title="the query-string helpers (`querybag.py`)",
    blurb="The API gateway decodes, canonicalises and rebuilds query strings with this module.",
    files={"querybag.py": QB_SRC, "README.md": QB_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": QB_VISIBLE},
    hidden_tests={"tests/test_full.py": QB_HIDDEN},
    mutate=["querybag.py"], difficulty=3, tags=["url", "parsing"],
    probes=[
        'decode("a%2bb+100%&%4g")',
        'encode("a b+~[]\\u00e9")',
        'parse("t=a&t[]=b&f[x]=1&f[x]=2&flag")',
        'parse("?&=z&a%20b=c+d")',
        'get_int(parse("n=50"), "n", minimum=1, maximum=10)',
        'get_int({}, "n", default=99, maximum=10)',
        'normalize("b=2&B=1&a&a=0&utm_x=1", drop=["utm_*"])',
        'normalize("a=&b=1", drop_empty=True)',
        'build({"t": ["z", "a"], "f": {"b": 1, "a": None}, "k": "x y"})',
    ],
    probe_import="from querybag import *",
)


# ======================================================================================================================
# cfglayers: layered configuration merge with directive keys and provenance
# ======================================================================================================================

CL_README = dd(r'''
    # cfglayers

    Merging of layered configuration documents (plain `dict`s of `str`/number/bool/`None`, lists and nested dicts).
    Keys that end or start with a directive character change how an *override* is applied. A real key name never
    starts with `+` or ends with `+ - ! ~`.

    ## `merge(base, override) -> dict`
    Returns a new dict (neither input is modified or shared with the result; nested containers are copied).
    Every key of `override` is processed in turn:

    | key form | effect |
    |---|---|
    | `name` | if the value is `None` the key `name` is removed (nothing happens if it is absent). If the value is a dict, it is merged recursively into the base value when that is a dict, otherwise into an empty dict. Any other value replaces the base value (lists are replaced, not joined). |
    | `name+` | append: the value (must be a list) is added after the base list; a missing base counts as `[]` |
    | `+name` | prepend: the value (must be a list) goes before the base list; a missing base counts as `[]` |
    | `name-` | remove: every element equal to one in the value list is removed from the base list, order kept; nothing happens if `name` is absent |
    | `name!` | the value is stored under `name` exactly as given: no merging, and directive keys inside it stay literal |
    | `name~` | default: the value is stored under `name` only when `name` is not in the result yet |

    A directive that needs a list raises `ValueError` when the override value is not a list or when the base value
    exists and is not a list. A key that is only the directive character (such as `"+"` or `"-"`) is an ordinary name.

    ## `resolve(layers) -> dict`
    Merges the layers left to right starting from `{}`: later layers override earlier ones.

    ## `flatten(doc) -> dict`
    Leaves of `doc` keyed by their dotted path: `{"a": {"b": 1}, "c": [1]}` gives `{"a.b": 1, "c": [1]}`. Lists and
    empty dicts are leaves.

    ## `explain(layers) -> dict`
    For every leaf path of `resolve(layers)` (as in `flatten`), the index of the last layer that changed it: the layer
    that introduced the path or changed its value. A layer that sets a value equal to the one already there does not
    take over responsibility. The keys come out in sorted order.

    ## `lookup(doc, path, default=None)`
    The value at the dotted `path` (`"a.b.c"`), or `default` when any step is missing or passes through a non-dict.
''')

CL_SRC = dd(r'''
    """Layered configuration merge."""
    import copy


    def _split_key(key):
        if len(key) > 1:
            if key[0] == "+":
                return key[1:], "prepend"
            last = key[-1]
            if last == "+":
                return key[:-1], "append"
            if last == "-":
                return key[:-1], "remove"
            if last == "!":
                return key[:-1], "replace"
            if last == "~":
                return key[:-1], "default"
        return key, "set"


    def _need_list(value, what):
        if not isinstance(value, list):
            raise ValueError("%s needs a list" % what)


    def merge(base, override):
        out = copy.deepcopy(base)
        for key, value in override.items():
            name, how = _split_key(key)
            if how == "set":
                if value is None:
                    out.pop(name, None)
                elif isinstance(value, dict):
                    cur = out.get(name)
                    out[name] = merge(cur if isinstance(cur, dict) else {}, value)
                else:
                    out[name] = copy.deepcopy(value)
            elif how == "replace":
                out[name] = copy.deepcopy(value)
            elif how == "default":
                if name not in out:
                    out[name] = copy.deepcopy(value)
            else:
                _need_list(value, key)
                if how == "remove":
                    if name not in out:
                        continue
                    _need_list(out[name], name)
                    out[name] = [x for x in out[name] if x not in value]
                    continue
                cur = out.get(name, [])
                _need_list(cur, name)
                out[name] = cur + copy.deepcopy(value) if how == "append" else copy.deepcopy(value) + cur
        return out


    def resolve(layers):
        doc = {}
        for layer in layers:
            doc = merge(doc, layer)
        return doc


    def flatten(doc, prefix=""):
        out = {}
        for key, value in doc.items():
            path = prefix + key
            if isinstance(value, dict) and value:
                out.update(flatten(value, path + "."))
            else:
                out[path] = value
        return out


    def explain(layers):
        doc = {}
        flat = {}
        who = {}
        for i, layer in enumerate(layers):
            doc = merge(doc, layer)
            new = flatten(doc)
            for path, value in new.items():
                if path not in flat or flat[path] != value:
                    who[path] = i
            for path in list(who):
                if path not in new:
                    del who[path]
            flat = new
        return {path: who[path] for path in sorted(who)}


    def lookup(doc, path, default=None):
        cur = doc
        for step in path.split("."):
            if not isinstance(cur, dict) or step not in cur:
                return default
            cur = cur[step]
        return cur
''')

CL_VISIBLE = dd(r'''
    import unittest

    from cfglayers import flatten, merge, resolve


    class BasicTests(unittest.TestCase):
        def test_deep_merge(self):
            self.assertEqual(merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 5}}), {"a": {"b": 5, "c": 2}})

        def test_append(self):
            self.assertEqual(merge({"x": [1]}, {"x+": [2]}), {"x": [1, 2]})

        def test_flatten(self):
            self.assertEqual(flatten({"a": {"b": 1}, "c": [1]}), {"a.b": 1, "c": [1]})


    if __name__ == "__main__":
        unittest.main()
''')

CL_HIDDEN = dd(r'''
    import copy
    import unittest

    from cfglayers import explain, flatten, lookup, merge, resolve


    class MergePlain(unittest.TestCase):
        def test_scalars_and_new_keys(self):
            self.assertEqual(merge({"a": 1}, {"a": 2, "b": 3}), {"a": 2, "b": 3})
            self.assertEqual(merge({}, {"a": 1}), {"a": 1})
            self.assertEqual(merge({"a": 1}, {}), {"a": 1})

        def test_falsy_values_override(self):
            self.assertEqual(merge({"a": 1, "b": "x", "c": [1]}, {"a": 0, "b": "", "c": []}), {"a": 0, "b": "", "c": []})
            self.assertEqual(merge({"a": 1}, {"a": False}), {"a": False})

        def test_nested(self):
            base = {"s": {"h": "x", "p": {"a": 1, "b": 2}}, "t": 1}
            self.assertEqual(merge(base, {"s": {"p": {"b": 9, "c": 3}}}), {"s": {"h": "x", "p": {"a": 1, "b": 9, "c": 3}}, "t": 1})

        def test_lists_replaced(self):
            self.assertEqual(merge({"l": [1, 2, 3]}, {"l": [9]}), {"l": [9]})

        def test_dict_over_scalar_and_scalar_over_dict(self):
            self.assertEqual(merge({"a": 1}, {"a": {"b": 2}}), {"a": {"b": 2}})
            self.assertEqual(merge({"a": {"b": 2}}, {"a": 1}), {"a": 1})
            self.assertEqual(merge({"a": [1]}, {"a": {"b": 2}}), {"a": {"b": 2}})

        def test_dict_over_missing_applies_directives(self):
            self.assertEqual(merge({}, {"a": {"x+": [1], "y~": 2, "z": None}}), {"a": {"x": [1], "y": 2}})

        def test_none_deletes(self):
            self.assertEqual(merge({"a": 1, "b": 2}, {"a": None}), {"b": 2})
            self.assertEqual(merge({"a": {"b": 1, "c": 2}}, {"a": {"b": None}}), {"a": {"c": 2}})
            self.assertEqual(merge({"a": 1}, {"zz": None}), {"a": 1})
            self.assertEqual(merge({"a": {"b": 1}}, {"a": None}), {})

        def test_inputs_untouched_and_unshared(self):
            base = {"a": {"b": [1]}, "l": [1]}
            over = {"a": {"c": [2]}, "m": [3], "n": {"k": 1}}
            b0, o0 = copy.deepcopy(base), copy.deepcopy(over)
            out = merge(base, over)
            self.assertEqual((base, over), (b0, o0))
            out["a"]["b"].append(99)
            out["m"].append(99)
            out["n"]["k"] = 99
            out["l"].append(99)
            self.assertEqual((base, over), (b0, o0))


    class Directives(unittest.TestCase):
        def test_append(self):
            self.assertEqual(merge({"x": [1, 2]}, {"x+": [3, 1]}), {"x": [1, 2, 3, 1]})
            self.assertEqual(merge({}, {"x+": [3]}), {"x": [3]})
            self.assertEqual(merge({"x": []}, {"x+": []}), {"x": []})

        def test_prepend(self):
            self.assertEqual(merge({"x": [1, 2]}, {"+x": [8, 9]}), {"x": [8, 9, 1, 2]})
            self.assertEqual(merge({}, {"+x": [3]}), {"x": [3]})

        def test_remove(self):
            self.assertEqual(merge({"x": [1, 2, 3, 2]}, {"x-": [2]}), {"x": [1, 3]})
            self.assertEqual(merge({"x": [1, 2, 3]}, {"x-": [3, 1, 7]}), {"x": [2]})
            self.assertEqual(merge({"x": [1]}, {"x-": [1]}), {"x": []})
            self.assertEqual(merge({"x": [1]}, {"y-": [1]}), {"x": [1]})
            self.assertEqual(merge({"x": ["a", "b"]}, {"x-": []}), {"x": ["a", "b"]})

        def test_replace(self):
            self.assertEqual(merge({"a": {"b": 1, "c": 2}}, {"a!": {"d": 3}}), {"a": {"d": 3}})
            self.assertEqual(merge({}, {"a!": {"b+": [1]}}), {"a": {"b+": [1]}})
            self.assertEqual(merge({"a": 1}, {"a!": None}), {"a": None})
            self.assertEqual(merge({"a": [1]}, {"a!": [2]}), {"a": [2]})

        def test_default(self):
            self.assertEqual(merge({"a": 1}, {"a~": 2, "b~": 3}), {"a": 1, "b": 3})
            self.assertEqual(merge({"a": None}, {"a~": 2}), {"a": None})
            self.assertEqual(merge({"a": 0}, {"a~": 2}), {"a": 0})
            self.assertEqual(merge({}, {"a~": {"b": 1}}), {"a": {"b": 1}})

        def test_list_errors(self):
            for base, over in (({"x": [1]}, {"x+": 5}), ({"x": 5}, {"x+": [1]}), ({"x": [1]}, {"+x": "ab"}),
                               ({"x": {"a": 1}}, {"+x": [1]}), ({"x": [1]}, {"x-": 1}), ({"x": 1}, {"x-": [1]})):
                with self.assertRaises(ValueError):
                    merge(base, over)

        def test_remove_missing_still_checks_value_type(self):
            with self.assertRaises(ValueError):
                merge({}, {"x-": 5})

        def test_plain_directive_characters_are_names(self):
            self.assertEqual(merge({}, {"+": 1, "-": 2, "!": 3, "~": 4}), {"+": 1, "-": 2, "!": 3, "~": 4})
            self.assertEqual(merge({"+": [1]}, {"+": [2]}), {"+": [2]})

        def test_directives_inside_nested_overrides(self):
            base = {"srv": {"ports": [80], "tls": {"on": True}}}
            over = {"srv": {"ports+": [443], "tls": {"on": False, "ciphers~": ["a"]}}}
            self.assertEqual(merge(base, over), {"srv": {"ports": [80, 443], "tls": {"on": False, "ciphers": ["a"]}}})

        def test_directive_order_follows_override(self):
            self.assertEqual(merge({"x": [1]}, {"x+": [2], "+x": [0]}), {"x": [0, 1, 2]})
            self.assertEqual(merge({"x": [1, 2]}, {"x-": [1], "x+": [1]}), {"x": [2, 1]})


    class Resolve(unittest.TestCase):
        def test_order(self):
            self.assertEqual(resolve([{"a": 1}, {"a": 2}, {"b": 3}]), {"a": 2, "b": 3})
            self.assertEqual(resolve([]), {})
            self.assertEqual(resolve([{"x+": [1]}, {"x+": [2]}, {"+x": [0]}]), {"x": [0, 1, 2]})

        def test_directives_apply_across_layers(self):
            self.assertEqual(resolve([{"a": {"b": 1}}, {"a!": {"c": 2}}, {"a": {"d": 3}}]), {"a": {"c": 2, "d": 3}})


    class Flatten(unittest.TestCase):
        def test_paths(self):
            self.assertEqual(flatten({"a": {"b": {"c": 1}, "d": 2}, "e": 3}), {"a.b.c": 1, "a.d": 2, "e": 3})
            self.assertEqual(flatten({}), {})

        def test_lists_and_empty_dicts_are_leaves(self):
            self.assertEqual(flatten({"a": [1, {"x": 1}], "b": {}, "c": {"d": {}}}), {"a": [1, {"x": 1}], "b": {}, "c.d": {}})

        def test_none_and_falsy_leaves(self):
            self.assertEqual(flatten({"a": None, "b": 0, "c": ""}), {"a": None, "b": 0, "c": ""})


    class Explain(unittest.TestCase):
        def test_last_changer(self):
            layers = [{"a": 1, "b": {"c": 1, "d": 1}}, {"a": 2, "b": {"c": 1}}, {"b": {"d": 3}, "e": 1}]
            self.assertEqual(explain(layers), {"a": 1, "b.c": 0, "b.d": 2, "e": 2})

        def test_same_value_keeps_original_owner(self):
            self.assertEqual(explain([{"a": 1}, {"a": 1}, {"b": 2}]), {"a": 0, "b": 2})

        def test_deleted_paths_disappear_and_return(self):
            layers = [{"a": 1, "b": 1}, {"a": None}, {"c": 1}]
            self.assertEqual(explain(layers), {"b": 0, "c": 2})
            self.assertEqual(explain([{"a": 1}, {"a": None}, {"a": 1}]), {"a": 2})

        def test_directives(self):
            layers = [{"x": [1]}, {"x+": [2]}, {"y~": 5}, {"y~": 6, "x-": [9]}]
            self.assertEqual(explain(layers), {"x": 1, "y": 2})

        def test_dict_replaced_by_scalar_and_back(self):
            layers = [{"a": {"b": 1}}, {"a": 5}, {"a": {"b": 1}}]
            self.assertEqual(explain(layers), {"a.b": 2})

        def test_sorted_keys_and_empty(self):
            self.assertEqual(list(explain([{"z": 1, "a": 1}, {"m": 1}])), ["a", "m", "z"])
            self.assertEqual(explain([]), {})
            self.assertEqual(explain([{}]), {})


    class Lookup(unittest.TestCase):
        def test_paths(self):
            d = {"a": {"b": {"c": 5}}, "n": None, "z": 0, "l": [1]}
            self.assertEqual(lookup(d, "a.b.c"), 5)
            self.assertEqual(lookup(d, "a.b"), {"c": 5})
            self.assertEqual(lookup(d, "z", 9), 0)
            self.assertEqual(lookup(d, "n", 9), None)
            self.assertEqual(lookup(d, "a.x", "d"), "d")
            self.assertEqual(lookup(d, "a.b.c.d", "d"), "d")
            self.assertEqual(lookup(d, "l.0", "d"), "d")
            self.assertEqual(lookup(d, "q"), None)
            self.assertEqual(lookup(d, "q.r", 1), 1)


    if __name__ == "__main__":
        unittest.main()
''')

CL = Lib(
    name="cfglayers", lang="python", title="the layered config merge (`cfglayers.py`)",
    blurb="The platform tooling builds the effective settings of a service by merging default, site and per-host layers with this module.",
    files={"cfglayers.py": CL_SRC, "README.md": CL_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": CL_VISIBLE},
    hidden_tests={"tests/test_full.py": CL_HIDDEN},
    mutate=["cfglayers.py"], difficulty=4, tags=["config", "merge"],
    probes=[
        'merge({"x": [1, 2]}, {"x+": [3], "+x": [0]})',
        'merge({"x": [1, 2, 3, 2]}, {"x-": [2]})',
        'merge({"a": {"b": 1}}, {"a!": {"c": 2}})',
        'merge({"a": 0}, {"a~": 2, "b~": 3})',
        'merge({"a": {"b": 1, "c": 2}}, {"a": {"b": None}})',
        'merge({}, {"a": {"x+": [1]}})',
        'explain([{"a": 1, "b": 1}, {"a": 1, "b": 2}, {"c": 1}])',
        'explain([{"a": 1}, {"a": None}, {"b": 1}])',
        'flatten({"a": {"b": 1}, "c": {}, "d": [1]})',
        'lookup({"a": {"b": 0}}, "a.b", 5)',
    ],
    probe_import="from cfglayers import *",
)


LIBS = [STASH, QB, CL]
register_libs(LIBS, n=10)
