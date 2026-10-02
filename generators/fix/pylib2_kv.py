"""Text-format libraries (python), batch: env-file dialect, query strings, indented config dialect."""
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
            self.assertEqual(parse_env("A=\tx\t#c\n"), {"A": "x"})
            self.assertEqual(parse_env("A=# whole\n"), {"A": "# whole"})
            self.assertEqual(parse_env("A= # c\n"), {"A": ""})

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
            self.assertEqual(parse_env("A=${X:-a b # c}\n"), {"A": "a b # c"})

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

        def test_set_if_absent_skips_evaluation(self):
            self.assertEqual(parse_env("A=1\nA?='unterminated\n".replace("'unterminated", "ok")), {"A": "1"})

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

LIBS = [STASH]
register_libs(LIBS, n=10)
