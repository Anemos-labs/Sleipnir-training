"""Text-format libraries (python), batch: shell-like splitting and spreadsheet formulas."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# wordsplit: shell-like command-line splitting with a house dialect
# ======================================================================================================================

WS_README = dd(r'''
    # wordsplit

    Splits the command lines of the job runner's `.job` files into words, in a small shell-like dialect, and quotes words
    back. All functions are in `wordsplit.py`.

    ## `split(line, env=None, strict=False) -> list[str]`
    * **Words** are separated by runs of space, tab, `\r` or `\n`. Adjacent quoted and unquoted pieces form one word:
      `a"b c"d` is one word `ab cd`.
    * `'...'` takes everything literally up to the next `'`. A missing closing quote is a `ValueError`.
    * `"..."`: inside, a backslash followed by one of `"`, `\`, `$`, `n`, `t` is an escape (a quote, backslash, dollar,
      newline, tab); a backslash before any other character stays a backslash and that character is read normally.
      `$` expansions apply (below). A missing closing quote is a `ValueError`.
    * Outside quotes a backslash makes the next character literal; a backslash directly before a newline is a line
      continuation and produces nothing (it neither starts nor ends a word). A backslash that is the very last character
      is a `ValueError`.
    * Empty quotes make an empty word: `a "" b` is `["a", "", "b"]`.
    * A `#` that begins a word (outside quotes, at a word boundary) starts a comment that runs up to the next `\n`;
      the newline itself ends the word as usual. A `#` inside a word is an ordinary character.
    * A `~` at the start of an unquoted word that is followed by the end of the text, whitespace, `/` (or `;` in `split_commands`) becomes `env["HOME"]` if
      `env` has it, and stays `~` otherwise. `~name` is not special.
    * `;` is an ordinary character here (see `split_commands`).

    ### Expansion
    In unquoted text and inside double quotes: `$NAME` (`NAME` is `[A-Za-z_][A-Za-z0-9_]*`, read greedily) and `${NAME}` are
    replaced by `str(env[NAME])`; an undefined name (or `env=None`) gives the empty string, or `KeyError(NAME)` when
    `strict` is true. A `$` followed by anything else is a literal `$`; `${` without `}` or with a body that is not a name
    is a `ValueError`. Expanded text is never split or re-scanned, and expansion never creates or removes words: a word
    that only expands to nothing stays as an empty word. `\$` (unquoted or in double quotes) is a literal `$`.

    ## `split_commands(line, env=None, strict=False) -> list[list[str]]`
    Like `split`, but an unquoted `;` that is not part of a comment ends the current word and the current command.
    Returns the list of commands as lists of words; commands without words are dropped.

    ## `quote(word) -> str`
    `''` for the empty word; the word itself if it consists only of `A-Z a-z 0-9 _ @ % + = : , . / -`; otherwise the
    word in single quotes, where each `'` inside is written as `'"'"'`.

    ## `join(words) -> str`
    The quoted words joined by single spaces. `split(join(words)) == words` for any list of strings (with any `env`).
''')

WS_SRC = dd(r'''
    """Shell-like word splitting."""
    import re

    _SPACE = " \t\r\n"
    _NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    _SAFE = re.compile(r"[A-Za-z0-9_@%+=:,./-]+")
    _DQ_ESC = {'"': '"', "\\": "\\", "$": "$", "n": "\n", "t": "\t"}


    def _lookup(name, env, strict):
        if env and name in env:
            return str(env[name])
        if strict:
            raise KeyError(name)
        return ""


    def _expand(line, i, env, strict):
        """line[i] == '$'. Returns (text, next index)."""
        if line.startswith("${", i):
            j = line.find("}", i + 2)
            if j < 0:
                raise ValueError("unterminated ${")
            name = line[i + 2:j]
            if not _NAME.fullmatch(name):
                raise ValueError("bad substitution: ${%s}" % name)
            return _lookup(name, env, strict), j + 1
        m = _NAME.match(line, i + 1)
        if m:
            return _lookup(m.group(), env, strict), m.end()
        return "$", i + 1


    def _parse(line, env, strict, semicolons):
        cmds = [[]]
        word = None
        i, n = 0, len(line)
        while i < n:
            c = line[i]
            if c in _SPACE:
                if word is not None:
                    cmds[-1].append("".join(word))
                    word = None
                i += 1
            elif c == "#" and word is None:
                while i < n and line[i] != "\n":
                    i += 1
            elif c == ";" and semicolons:
                if word is not None:
                    cmds[-1].append("".join(word))
                    word = None
                cmds.append([])
                i += 1
            elif c == "'":
                j = line.find("'", i + 1)
                if j < 0:
                    raise ValueError("unterminated single quote")
                if word is None:
                    word = []
                word.append(line[i + 1:j])
                i = j + 1
            elif c == '"':
                if word is None:
                    word = []
                i += 1
                while True:
                    if i >= n:
                        raise ValueError("unterminated double quote")
                    d = line[i]
                    if d == '"':
                        i += 1
                        break
                    if d == "\\" and i + 1 < n and line[i + 1] in _DQ_ESC:
                        word.append(_DQ_ESC[line[i + 1]])
                        i += 2
                    elif d == "$":
                        text, i = _expand(line, i, env, strict)
                        word.append(text)
                    else:
                        word.append(d)
                        i += 1
            elif c == "\\":
                if i + 1 >= n:
                    raise ValueError("dangling backslash")
                if line[i + 1] == "\n":
                    i += 2
                    continue
                if word is None:
                    word = []
                word.append(line[i + 1])
                i += 2
            elif c == "$":
                if word is None:
                    word = []
                text, i = _expand(line, i, env, strict)
                word.append(text)
            elif c == "~" and word is None and (i + 1 == n or line[i + 1] in _SPACE + "/" + (";" if semicolons else "")):
                word = [env["HOME"] if env and "HOME" in env else "~"]
                i += 1
            else:
                if word is None:
                    word = []
                word.append(c)
                i += 1
        if word is not None:
            cmds[-1].append("".join(word))
        return [c for c in cmds if c]


    def split(line, env=None, strict=False):
        cmds = _parse(line, env, strict, False)
        return cmds[0] if cmds else []


    def split_commands(line, env=None, strict=False):
        return _parse(line, env, strict, True)


    def quote(word):
        if word == "":
            return "''"
        if _SAFE.fullmatch(word):
            return word
        return "'" + word.replace("'", "'\"'\"'") + "'"


    def join(words):
        return " ".join(quote(w) for w in words)
''')

WS_VISIBLE = dd(r'''
    import unittest

    from wordsplit import join, quote, split, split_commands


    class BasicTests(unittest.TestCase):
        def test_split(self):
            self.assertEqual(split("run  --fast 'a b' \"c d\""), ["run", "--fast", "a b", "c d"])

        def test_expand(self):
            self.assertEqual(split("echo $USER", {"USER": "ada"}), ["echo", "ada"])

        def test_commands(self):
            self.assertEqual(split_commands("a b; c"), [["a", "b"], ["c"]])

        def test_quote(self):
            self.assertEqual(quote("a b"), "'a b'")


    if __name__ == "__main__":
        unittest.main()
''')

WS_HIDDEN = dd(r'''
    import unittest

    from wordsplit import join, quote, split, split_commands


    class Words(unittest.TestCase):
        def test_whitespace(self):
            self.assertEqual(split("  a \t b\r\nc  "), ["a", "b", "c"])
            self.assertEqual(split(""), [])
            self.assertEqual(split(" \t\n "), [])

        def test_concatenation(self):
            self.assertEqual(split('a"b c"d'), ["ab cd"])
            self.assertEqual(split("a'b c'\"d e\"f"), ["ab cd ef"])
            self.assertEqual(split("''a"), ["a"])

        def test_empty_words(self):
            self.assertEqual(split("a \"\" b ''"), ["a", "", "b", ""])
            self.assertEqual(split("\"\"\"\""), [""])

        def test_semicolon_is_ordinary(self):
            self.assertEqual(split("a;b c;"), ["a;b", "c;"])


    class Quotes(unittest.TestCase):
        def test_single_literal(self):
            self.assertEqual(split(r"'a\nb $X \" #c ~'", {"X": "v"}), [r"a\nb $X \" #c ~"])
            self.assertEqual(split("'  spaced  '"), ["  spaced  "])
            self.assertEqual(split("'multi\nline'"), ["multi\nline"])

        def test_single_unterminated(self):
            with self.assertRaises(ValueError):
                split("a 'b")

        def test_double_escapes(self):
            self.assertEqual(split(r'"a\"b"'), ['a"b'])
            self.assertEqual(split(r'"a\\b"'), ["a\\b"])
            self.assertEqual(split(r'"\$HOME"', {"HOME": "/h"}), ["$HOME"])
            self.assertEqual(split(r'"a\nb\tc"'), ["a\nb\tc"])

        def test_double_other_backslashes_stay(self):
            self.assertEqual(split(r'"a\qb"'), ["a\\qb"])
            self.assertEqual(split(r'"\ "'), ["\\ "])
            self.assertEqual(split(r'"\#"'), ["\\#"])
            self.assertEqual(split('"x\\\ny"'), ["x\\\ny"])

        def test_double_keeps_hash_semicolon_tilde(self):
            self.assertEqual(split('"# not ; a ~ comment"', {"HOME": "/h"}), ["# not ; a ~ comment"])

        def test_double_unterminated(self):
            for bad in ('"abc', '"abc\\', '"a\\"'):
                with self.assertRaises(ValueError, msg=bad):
                    split(bad)

        def test_backslash_outside(self):
            self.assertEqual(split(r"a\ b c"), ["a b", "c"])
            self.assertEqual(split(r"\'\"\\"), ["'\"\\"])
            self.assertEqual(split(r"\$X", {"X": "v"}), ["$X"])
            self.assertEqual(split(r"a\nb"), ["anb"])
            self.assertEqual(split(r"\#x"), ["#x"])
            self.assertEqual(split(r"\;"), [";"])

        def test_line_continuation(self):
            self.assertEqual(split("ab\\\ncd"), ["abcd"])
            self.assertEqual(split("ab \\\ncd"), ["ab", "cd"])
            self.assertEqual(split("\\\n"), [])
            self.assertEqual(split("a\\\n\\\nb"), ["ab"])

        def test_dangling_backslash(self):
            with self.assertRaises(ValueError):
                split("abc\\")
            with self.assertRaises(ValueError):
                split("\\")


    class Comments(unittest.TestCase):
        def test_comment_at_word_start(self):
            self.assertEqual(split("a b # c d"), ["a", "b"])
            self.assertEqual(split("# only"), [])
            self.assertEqual(split("a #b"), ["a"])

        def test_hash_inside_word(self):
            self.assertEqual(split("a#b c#"), ["a#b", "c#"])
            self.assertEqual(split("x\"\"#y"), ["x#y"])
            self.assertEqual(split("'a'#b"), ["a#b"])

        def test_comment_ends_at_newline(self):
            self.assertEqual(split("a # c1\nb # c2\nc"), ["a", "b", "c"])
            self.assertEqual(split("a #c\r\nb"), ["a", "b"])

        def test_comment_hides_quotes_and_semicolons(self):
            self.assertEqual(split("a # it's \"broken\nb"), ["a", "b"])
            self.assertEqual(split_commands("a # x; y\nb"), [["a", "b"]])

        def test_hash_after_empty_quotes_is_inside_word(self):
            self.assertEqual(split("'' #x"), [""])


    class Tilde(unittest.TestCase):
        ENV = {"HOME": "/hdir/u"}

        def test_expansion(self):
            self.assertEqual(split("~", self.ENV), ["/hdir/u"])
            self.assertEqual(split("~/bin ~/", self.ENV), ["/hdir/u/bin", "/hdir/u/"])
            self.assertEqual(split("a ~\tb", self.ENV), ["a", "/hdir/u", "b"])
            self.assertEqual(split("x\n~", self.ENV), ["x", "/hdir/u"])

        def test_not_expanded(self):
            self.assertEqual(split("~bob ~x/y a~ a~/b", self.ENV), ["~bob", "~x/y", "a~", "a~/b"])
            self.assertEqual(split("'~' \"~\" \\~", self.ENV), ["~", "~", "~"])
            self.assertEqual(split("~~", self.ENV), ["~~"])

        def test_without_home(self):
            self.assertEqual(split("~ ~/x"), ["~", "~/x"])
            self.assertEqual(split("~/x", {"OTHER": "1"}), ["~/x"])
            self.assertEqual(split("~", {}), ["~"])

        def test_home_value_not_rescanned(self):
            self.assertEqual(split("~/x", {"HOME": "$X y"}), ["$X y/x"])


    class Expansion(unittest.TestCase):
        ENV = {"A": "alpha", "B": "b b", "N": 5, "E": "", "_u1": "u"}

        def test_plain(self):
            self.assertEqual(split("$A ${A} x$A.y ${A}z", self.ENV), ["alpha", "alpha", "xalpha.y", "alphaz"])
            self.assertEqual(split("$N ${N}", self.ENV), ["5", "5"])
            self.assertEqual(split("$_u1x $_u1", self.ENV), ["", "u"])

        def test_name_is_read_greedily(self):
            self.assertEqual(split("$A1", {"A": "x", "A1": "y"}), ["y"])
            self.assertEqual(split("$A-1", {"A": "x"}), ["x-1"])
            self.assertEqual(split("$A_B", {"A": "x", "A_B": "z"}), ["z"])

        def test_in_double_quotes(self):
            self.assertEqual(split('"<$A>" "${B}!"', self.ENV), ["<alpha>", "b b!"])

        def test_not_in_single_quotes(self):
            self.assertEqual(split("'$A'", self.ENV), ["$A"])

        def test_no_splitting_of_values(self):
            self.assertEqual(split("$B", self.ENV), ["b b"])
            self.assertEqual(split("x$B y", self.ENV), ["xb b", "y"])
            self.assertEqual(split("$B", {"B": "$A"}), ["$A"])

        def test_undefined_and_empty_keep_words(self):
            self.assertEqual(split("a $NOPE b", self.ENV), ["a", "", "b"])
            self.assertEqual(split("a $E b", self.ENV), ["a", "", "b"])
            self.assertEqual(split("$NOPE"), [""])
            self.assertEqual(split('"$NOPE"'), [""])
            self.assertEqual(split("x$NOPE"), ["x"])

        def test_strict(self):
            with self.assertRaises(KeyError) as cm:
                split("a $NOPE", self.ENV, strict=True)
            self.assertEqual(cm.exception.args, ("NOPE",))
            with self.assertRaises(KeyError):
                split('"${NOPE}"', strict=True)
            self.assertEqual(split("$E", self.ENV, strict=True), [""])
            self.assertEqual(split("'$NOPE'", strict=True), ["$NOPE"])
            self.assertEqual(split("\\$NOPE", strict=True), ["$NOPE"])

        def test_literal_dollar(self):
            self.assertEqual(split("$ $1 $- a$ $$ '$'"), ["$", "$1", "$-", "a$", "$$", "$"])
            self.assertEqual(split('"$" "a$" "$ x"'), ["$", "a$", "$ x"])
            self.assertEqual(split("cost$"), ["cost$"])

        def test_bad_braces(self):
            for bad in ("${A", "${}", "${1}", "${A B}", "${A-b}", '"${A"', "${A:-x}"):
                with self.assertRaises(ValueError, msg=bad):
                    split(bad, {"A": "1"})

        def test_brace_ends_at_first_close(self):
            self.assertEqual(split("${A}}", {"A": "x"}), ["x}"])

        def test_expansion_across_pieces(self):
            self.assertEqual(split("'a'$A\"b\"", self.ENV), ["aalphab"])


    class Commands(unittest.TestCase):
        def test_basic(self):
            self.assertEqual(split_commands("a b; c d ;e"), [["a", "b"], ["c", "d"], ["e"]])
            self.assertEqual(split_commands("a;b"), [["a"], ["b"]])

        def test_empty_commands_dropped(self):
            self.assertEqual(split_commands(";; a ;; ; b ;"), [["a"], ["b"]])
            self.assertEqual(split_commands(""), [])
            self.assertEqual(split_commands(" ; "), [])

        def test_quoted_and_escaped_semicolons(self):
            self.assertEqual(split_commands("a 'b;c'; \"d;e\" f\\;g"), [["a", "b;c"], ["d;e", "f;g"]])

        def test_semicolon_after_empty_word(self):
            self.assertEqual(split_commands("a '';b"), [["a", ""], ["b"]])

        def test_newlines_do_not_separate(self):
            self.assertEqual(split_commands("a\nb; c"), [["a", "b"], ["c"]])

        def test_expansion_and_tilde(self):
            self.assertEqual(split_commands("cd ~; echo $X", {"HOME": "/h", "X": "1"}), [["cd", "/h"], ["echo", "1"]])
            self.assertEqual(split_commands("echo $NOPE; x"), [["echo", ""], ["x"]])

        def test_semicolon_inside_comment(self):
            self.assertEqual(split_commands("a; # b; c\nd"), [["a"], ["d"]])

        def test_errors(self):
            with self.assertRaises(ValueError):
                split_commands("a; 'b")
            with self.assertRaises(KeyError):
                split_commands("a; $Q", strict=True)


    class Quote(unittest.TestCase):
        def test_safe_words_unchanged(self):
            for w in ("abc", "A_9", "a-b", "x/y.z", "k=v", "a,b", "u@h:p", "50%", "+1"):
                self.assertEqual(quote(w), w)

        def test_empty(self):
            self.assertEqual(quote(""), "''")

        def test_unsafe_words(self):
            self.assertEqual(quote("a b"), "'a b'")
            self.assertEqual(quote("$HOME"), "'$HOME'")
            self.assertEqual(quote("~"), "'~'")
            self.assertEqual(quote("#x"), "'#x'")
            self.assertEqual(quote("a;b"), "'a;b'")
            self.assertEqual(quote("a\nb"), "'a\nb'")
            self.assertEqual(quote("a\\b"), "'a\\b'")
            self.assertEqual(quote('say "hi"'), "'say \"hi\"'")
            self.assertEqual(quote("é"), "'é'")

        def test_single_quote_inside(self):
            self.assertEqual(quote("it's"), "'it'\"'\"'s'")
            self.assertEqual(quote("'"), "''\"'\"''")
            self.assertEqual(quote("''"), "''\"'\"''\"'\"''")

        def test_join(self):
            self.assertEqual(join(["a", "b c", "", "it's"]), "a 'b c' '' 'it'\"'\"'s'")
            self.assertEqual(join([]), "")

        def test_round_trip(self):
            words = ["plain", "", " ", "a b", "$X", "~", "~/x", "#c", "it's", "q\"q", "back\\slash", "a;b", "new\nline", "\t", "'", "x=$Y"]
            self.assertEqual(split(join(words), {"X": "1", "Y": "2", "HOME": "/h"}), words)
            self.assertEqual(split(join(words)), words)
            self.assertEqual(split_commands(join(words)), [words])
            self.assertEqual(split(join(words[::-1])), words[::-1])


    if __name__ == "__main__":
        unittest.main()
''')

WS = Lib(
    name="wordsplit", lang="python", title="the command-line splitter (`wordsplit.py`)",
    blurb="The job runner reads the commands of `.job` files through this splitter and quotes arguments with it.",
    files={"wordsplit.py": WS_SRC, "README.md": WS_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": WS_VISIBLE},
    hidden_tests={"tests/test_full.py": WS_HIDDEN},
    mutate=["wordsplit.py"], difficulty=3, tags=["shell", "parsing"],
    probes=[
        'split("a\\"b c\\"d \'e f\' \\"\\" # comment")',
        'split("x \\\\\\ny z")',
        'split("~ ~/b ~u a~", {"HOME": "/h"})',
        'split("$A ${A}b x$NOPE $", {"A": "1"})',
        'split("\\"\\\\q \\\\$A \\\\n\\"", {"A": "1"})',
        'split_commands("a b; c \'d;e\' ;; f\\\\;g # h; i\\nj")',
        'quote("it\'s a")',
        'join(["a", "", "$x", "~"])',
        'split("a#b c# #d")',
    ],
    probe_import="from wordsplit import *",
)


# ======================================================================================================================
# cellcalc: spreadsheet-style formulas (tokenizer, parser, evaluator with cell references)
# ======================================================================================================================

CALC_README = dd(r'''
    # cellcalc

    The formula engine of the budget sheets. One module, `cellcalc.py`.

    ## Values
    A value is a number (`int` when it is a whole number, else `float`), a text (`str`), or an error: a `CalcError`
    (a `str` subclass) with one of the texts `#DIV/0!`, `#VALUE!`, `#CYCLE!`, `#REF!`, `#SYNTAX!`. Module constants
    `DIV0`, `VALUE`, `CYCLE`, `REF`, `SYNTAX` hold them. Results that are floats with an integral value (and `abs < 1e15`)
    are turned into `int`. `fmt(value) -> str` renders a value: `""` for `None`, `"%.10g"` for floats, `str()` otherwise.

    ## `tokenize(src) -> list[(kind, value)]`
    Whitespace between tokens is skipped. Kinds:
    * `num`: `123`, `4.5`, `.5` (digits, optional fraction); the value is an `int` without a dot, a `float` with one;
    * `ref`: one letter and digits, not followed by a letter, digit, `_` or `(`: `A1`, `b12`; the value is upper-cased
      with the row written without leading zeros (`b012` gives `B12`);
    * `name`: letters, digits and `_` starting with a letter or `_`, upper-cased: function names;
    * `op`: one of `<>` `<=` `>=` `+ - * / ^ ( ) , : = < >`.
    Any other character is a `ValueError`.

    ## `parse(src)` and `evaluate(src, cells=None)`
    Grammar, loosest first: comparison (`= <> < <= > >=`, left to right) over sums (`+ -`) over products (`* /`)
    over unary signs (`-x`, `+x`) over powers (`a ^ b`, right-associative: `2^3^2` is `2^9`; the exponent may carry a
    sign: `2^-1`) over primaries: a number, a reference, a range `A1:B3` (only allowed as a function argument), a call
    `NAME(args)` or a parenthesised expression. So `-2^2` is `-4`. Comparisons give `1` or `0`.
    `parse` raises `ValueError` for syntax errors: tokens left over, a missing `)`, a `name` not followed by `(`, an
    unknown function, a wrong argument count (see below), or an empty formula. `evaluate` parses `src` and evaluates it
    against `cells` (a `Sheet`, or a dict that is turned into one; `None` means no cells) and returns the value.

    ### References
    A reference to a blank cell is `0` in arithmetic and comparisons. A reference to a text cell in arithmetic is
    `#VALUE!`. Row `0` is `#REF!`. The result of a formula that is just one reference is the cell's value as it is (text stays
    text, a blank is `0`). A range as a whole formula or inside an operator is `#VALUE!`.

    ### Errors in operators
    In `a op b` the left operand is evaluated first and the first error wins. `x / 0` is `#DIV/0!`; `0 ^ negative` is
    `#DIV/0!`; a negative base with a non-integer exponent is `#VALUE!`; results that overflow or are not finite are `#VALUE!`.

    ### Functions
    | call | result |
    |---|---|
    | `SUM(args)`, `AVG`, `MIN`, `MAX`, `COUNT` (at least one argument) | over the *numbers* among the arguments. An argument is a range (all its cells, rows first), a reference, or any other expression. Blank and text cells (in a range or referenced directly) are skipped; an error in a cell is returned (first one found, ranges in row-major order). Any other expression must yield a number (or an error). `SUM` of nothing is `0`, `AVG` of nothing is `#DIV/0!`, `MIN`/`MAX` of nothing are `0`, `COUNT` counts the numbers. |
    | `IF(c, a, b)` | `a` if `c` is non-zero else `b`; only the chosen branch is evaluated; `c` must be a number |
    | `ABS(x)` | absolute value |
    | `ROUND(x, n)` | `x` rounded to `n` decimals (`n` may be negative), halves away from zero: `ROUND(2.5, 0) = 3`, `ROUND(-2.5, 0) = -3`, `ROUND(1250, -2) = 1300`; `n` must be a whole number else `#VALUE!` |
    `IF` takes exactly 3 arguments, `ABS` 1, `ROUND` 2 (else `ValueError` at parse time).

    ## `Sheet(cells)`
    `cells` maps references (case-insensitive, normalised like tokens; an invalid one is a `ValueError`) to raw contents:
    * a `str` starting with `=`: a formula (the text after `=`);
    * a `str` that is a plain decimal number (`[-+]?digits[.digits]`, no spaces): a number;
    * an empty `str` or `None`: blank; any other `str`: text; an `int`/`float`: a number.
    `Sheet.value(ref)` is the computed value of a cell: `None` for a blank or missing cell, a number, a text, or an error.
    A formula that does not parse is `#SYNTAX!` (never an exception). A cell that depends on itself, directly or through
    others, is `#CYCLE!` and so is everything that uses it. `Sheet.values()` returns a dict of all non-blank cells
    (by normalised reference), ordered by column letter, then row number.
''')

CALC_SRC = dd(r'''
    """Spreadsheet formulas."""
    import math
    import re


    class CalcError(str):
        pass


    DIV0 = CalcError("#DIV/0!")
    VALUE = CalcError("#VALUE!")
    CYCLE = CalcError("#CYCLE!")
    REF = CalcError("#REF!")
    SYNTAX = CalcError("#SYNTAX!")

    _TOKEN = re.compile(
        r"\s*(?:(?P<num>\d+(?:\.\d+)?|\.\d+)"
        r"|(?P<ref>[A-Za-z][0-9]+)(?![A-Za-z0-9_(])"
        r"|(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
        r"|(?P<op><>|<=|>=|[-+*/^(),:=<>]))"
    )
    _REF = re.compile(r"([A-Za-z])([0-9]+)")
    _NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")
    _ARITY = {"SUM": (1, None), "AVG": (1, None), "MIN": (1, None), "MAX": (1, None), "COUNT": (1, None),
              "IF": (3, 3), "ABS": (1, 1), "ROUND": (2, 2)}


    def _norm_ref(text):
        m = _REF.fullmatch(text)
        if not m:
            raise ValueError("bad reference: %r" % text)
        return m.group(1).upper() + str(int(m.group(2)))


    def tokenize(src):
        out = []
        pos = 0
        while True:
            if src[pos:].strip() == "":
                return out
            m = _TOKEN.match(src, pos)
            if not m:
                raise ValueError("unexpected character at %d" % pos)
            pos = m.end()
            if m.group("num") is not None:
                t = m.group("num")
                out.append(("num", float(t) if "." in t else int(t)))
            elif m.group("ref") is not None:
                out.append(("ref", _norm_ref(m.group("ref"))))
            elif m.group("name") is not None:
                out.append(("name", m.group("name").upper()))
            else:
                out.append(("op", m.group("op")))


    class _Parser:
        def __init__(self, toks):
            self.toks = toks
            self.i = 0

        def peek(self):
            return self.toks[self.i] if self.i < len(self.toks) else (None, None)

        def take(self):
            t = self.peek()
            self.i += 1
            return t

        def accept(self, *ops):
            kind, val = self.peek()
            if kind == "op" and val in ops:
                self.i += 1
                return val
            return None

        def expect(self, op):
            if not self.accept(op):
                raise ValueError("expected %r" % op)

        def expr(self):
            node = self.add()
            while True:
                op = self.accept("=", "<>", "<=", ">=", "<", ">")
                if not op:
                    return node
                node = ("bin", op, node, self.add())

        def add(self):
            node = self.mul()
            while True:
                op = self.accept("+", "-")
                if not op:
                    return node
                node = ("bin", op, node, self.mul())

        def mul(self):
            node = self.unary()
            while True:
                op = self.accept("*", "/")
                if not op:
                    return node
                node = ("bin", op, node, self.unary())

        def unary(self):
            if self.accept("-"):
                return ("neg", self.unary())
            if self.accept("+"):
                return self.unary()
            return self.power()

        def power(self):
            node = self.primary()
            if self.accept("^"):
                return ("bin", "^", node, self.unary())
            return node

        def primary(self):
            kind, val = self.take()
            if kind == "num":
                return ("num", val)
            if kind == "ref":
                if self.accept(":"):
                    k2, v2 = self.take()
                    if k2 != "ref":
                        raise ValueError("range needs a reference after ':'")
                    return ("range", val, v2)
                return ("ref", val)
            if kind == "name":
                if val not in _ARITY:
                    raise ValueError("unknown function: %s" % val)
                self.expect("(")
                args = []
                if not self.accept(")"):
                    args.append(self.expr())
                    while self.accept(","):
                        args.append(self.expr())
                    self.expect(")")
                lo, hi = _ARITY[val]
                if len(args) < lo or (hi is not None and len(args) > hi):
                    raise ValueError("wrong number of arguments for %s" % val)
                return ("call", val, args)
            if kind == "op" and val == "(":
                node = self.expr()
                self.expect(")")
                return node
            raise ValueError("unexpected token")


    def parse(src):
        p = _Parser(tokenize(src))
        if not p.toks:
            raise ValueError("empty formula")
        node = p.expr()
        if p.i != len(p.toks):
            raise ValueError("unexpected trailing tokens")
        return node


    def _clean(x):
        if isinstance(x, float):
            if math.isnan(x) or math.isinf(x):
                return VALUE
            if x == int(x) and abs(x) < 1e15:
                return int(x)
        return x


    def fmt(value):
        if value is None:
            return ""
        if isinstance(value, float):
            return "%.10g" % value
        return str(value)


    class Sheet:
        def __init__(self, cells):
            self.raw = {_norm_ref(k): v for k, v in cells.items()}
            self._memo = {}
            self._stack = []

        def _source(self, ref):
            v = self.raw.get(ref)
            if v is None or v == "":
                return ("blank", None)
            if isinstance(v, str):
                if v.startswith("="):
                    return ("formula", v[1:])
                if _NUMBER.fullmatch(v):
                    return ("number", float(v) if "." in v else int(v))
                return ("text", v)
            return ("number", v)

        def value(self, ref):
            ref = _norm_ref(ref)
            if ref in self._memo:
                return self._memo[ref]
            if ref in self._stack:
                return CYCLE
            kind, content = self._source(ref)
            if kind == "formula":
                self._stack.append(ref)
                try:
                    try:
                        node = parse(content)
                    except ValueError:
                        result = SYNTAX
                    else:
                        result = _top(node, self)
                finally:
                    self._stack.pop()
            else:
                result = content
            self._memo[ref] = result
            return result

        def values(self):
            out = {}
            for ref in sorted(self.raw, key=lambda r: (r[0], int(r[1:]))):
                v = self.value(ref)
                if v is not None:
                    out[ref] = v
            return out


    def _cell(ref, sheet):
        if int(ref[1:]) == 0:
            return REF
        return sheet.value(ref)


    def _scalar(node, sheet):
        v = _ev(node, sheet)
        if v is None:
            return 0
        if isinstance(v, CalcError):
            return v
        if isinstance(v, str):
            return VALUE
        return v


    def _range_cells(a, b):
        c1, c2 = sorted((a[0], b[0]))
        r1, r2 = sorted((int(a[1:]), int(b[1:])))
        return [chr(c) + str(r) for r in range(r1, r2 + 1) for c in range(ord(c1), ord(c2) + 1)]


    def _numbers(args, sheet):
        """Numbers among the function arguments, or the first error."""
        out = []
        for node in args:
            if node[0] == "range":
                for ref in _range_cells(node[1], node[2]):
                    v = _cell(ref, sheet)
                    if isinstance(v, CalcError):
                        return v
                    if isinstance(v, (int, float)):
                        out.append(v)
            elif node[0] == "ref":
                v = _cell(node[1], sheet)
                if isinstance(v, CalcError):
                    return v
                if isinstance(v, (int, float)):
                    out.append(v)
            else:
                v = _scalar(node, sheet)
                if isinstance(v, CalcError):
                    return v
                out.append(v)
        return out


    def _round(x, n):
        sign = -1 if x < 0 else 1
        if n >= 0:
            scale = 10 ** n
            return sign * math.floor(abs(x) * scale + 0.5) / scale
        scale = 10 ** (-n)
        return sign * math.floor(abs(x) / scale + 0.5) * scale


    def _call(name, args, sheet):
        if name == "IF":
            c = _scalar(args[0], sheet)
            if isinstance(c, CalcError):
                return c
            return _scalar(args[1] if c != 0 else args[2], sheet)
        if name == "ABS":
            x = _scalar(args[0], sheet)
            return x if isinstance(x, CalcError) else abs(x)
        if name == "ROUND":
            x = _scalar(args[0], sheet)
            if isinstance(x, CalcError):
                return x
            n = _scalar(args[1], sheet)
            if isinstance(n, CalcError):
                return n
            if n != int(n):
                return VALUE
            return _round(x, int(n))
        nums = _numbers(args, sheet)
        if isinstance(nums, CalcError):
            return nums
        if name == "SUM":
            return sum(nums)
        if name == "COUNT":
            return len(nums)
        if name == "AVG":
            return sum(nums) / len(nums) if nums else DIV0
        return (min(nums) if name == "MIN" else max(nums)) if nums else 0


    def _binary(op, left, right):
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            return DIV0 if right == 0 else left / right
        if op == "^":
            if left == 0 and right < 0:
                return DIV0
            if left < 0 and right != int(right):
                return VALUE
            try:
                return float(left) ** float(right)
            except OverflowError:
                return VALUE
        res = {"=": left == right, "<>": left != right, "<": left < right, "<=": left <= right, ">": left > right, ">=": left >= right}[op]
        return 1 if res else 0


    def _ev(node, sheet):
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "ref":
            return _cell(node[1], sheet)
        if kind == "range":
            return VALUE
        if kind == "neg":
            x = _scalar(node[1], sheet)
            return x if isinstance(x, CalcError) else -x
        if kind == "bin":
            left = _scalar(node[2], sheet)
            if isinstance(left, CalcError):
                return left
            right = _scalar(node[3], sheet)
            if isinstance(right, CalcError):
                return right
            return _clean(_binary(node[1], left, right))
        return _clean(_call(node[1], node[2], sheet))


    def _top(node, sheet):
        v = _ev(node, sheet)
        return 0 if v is None else v


    def evaluate(src, cells=None):
        node = parse(src)
        sheet = cells if isinstance(cells, Sheet) else Sheet(cells or {})
        return _top(node, sheet)
''')

CALC_VISIBLE = dd(r'''
    import unittest

    from cellcalc import Sheet, evaluate, fmt, tokenize


    class BasicTests(unittest.TestCase):
        def test_tokens(self):
            self.assertEqual(tokenize("a1+2"), [("ref", "A1"), ("op", "+"), ("num", 2)])

        def test_arithmetic(self):
            self.assertEqual(evaluate("1+2*3"), 7)

        def test_sheet(self):
            s = Sheet({"A1": "4", "A2": "=A1*2"})
            self.assertEqual(s.value("A2"), 8)

        def test_fmt(self):
            self.assertEqual(fmt(1.5), "1.5")


    if __name__ == "__main__":
        unittest.main()
''')

CALC_HIDDEN = dd(r'''
    import unittest

    from cellcalc import CYCLE, DIV0, REF, SYNTAX, VALUE, CalcError, Sheet, evaluate, fmt, parse, tokenize


    class Tokens(unittest.TestCase):
        def test_kinds(self):
            self.assertEqual(tokenize("SUM(a1:B2, 3.5) <> .5"), [
                ("name", "SUM"), ("op", "("), ("ref", "A1"), ("op", ":"), ("ref", "B2"), ("op", ","), ("num", 3.5), ("op", ")"),
                ("op", "<>"), ("num", 0.5)])

        def test_numbers(self):
            self.assertEqual(tokenize("12 3.0 .25 007"), [("num", 12), ("num", 3.0), ("num", 0.25), ("num", 7)])
            self.assertIsInstance(tokenize("3")[0][1], int)
            self.assertIsInstance(tokenize("3.0")[0][1], float)

        def test_two_char_ops_win(self):
            self.assertEqual([t[1] for t in tokenize("<= >= <> < > =")], ["<=", ">=", "<>", "<", ">", "="])
            self.assertEqual([t[1] for t in tokenize("1<2")], [1, "<", 2])
            self.assertEqual([t[1] for t in tokenize("1<=2")], [1, "<=", 2])

        def test_refs_and_names(self):
            self.assertEqual(tokenize("b012")[0], ("ref", "B12"))
            self.assertEqual(tokenize("z9")[0], ("ref", "Z9"))
            self.assertEqual(tokenize("abs(")[0], ("name", "ABS"))
            self.assertEqual(tokenize("log10(")[0], ("name", "LOG10"))
            self.assertEqual(tokenize("A1B")[0], ("name", "A1B"))
            self.assertEqual(tokenize("A1_")[0], ("name", "A1_"))
            self.assertEqual(tokenize("_x")[0], ("name", "_X"))
            self.assertEqual(tokenize("A1(")[0], ("name", "A1"))
            self.assertEqual(tokenize("a")[0], ("name", "A"))
            self.assertEqual(tokenize("A1")[0], ("ref", "A1"))
            self.assertEqual(tokenize("A1:B2"), [("ref", "A1"), ("op", ":"), ("ref", "B2")])

        def test_whitespace_and_empty(self):
            self.assertEqual(tokenize(""), [])
            self.assertEqual(tokenize("   \t "), [])
            self.assertEqual(tokenize(" 1 +  2 "), [("num", 1), ("op", "+"), ("num", 2)])

        def test_bad_characters(self):
            for src in ("1 $ 2", "a & b", "3..4", "1 ; 2", "\"x\"", "#REF!", "5%"):
                with self.assertRaises(ValueError, msg=src):
                    tokenize(src)


    class Arithmetic(unittest.TestCase):
        def test_precedence(self):
            self.assertEqual(evaluate("1+2*3"), 7)
            self.assertEqual(evaluate("(1+2)*3"), 9)
            self.assertEqual(evaluate("10-4-3"), 3)
            self.assertEqual(evaluate("100/10/5"), 2)
            self.assertEqual(evaluate("2*3+4*5"), 26)
            self.assertEqual(evaluate("1+2=3"), 1)
            self.assertEqual(evaluate("2*3<5+2"), 1)

        def test_unary_and_power(self):
            self.assertEqual(evaluate("-2^2"), -4)
            self.assertEqual(evaluate("(-2)^2"), 4)
            self.assertEqual(evaluate("2^3^2"), 512)
            self.assertEqual(evaluate("2^-1"), 0.5)
            self.assertEqual(evaluate("--3"), 3)
            self.assertEqual(evaluate("+-3"), -3)
            self.assertEqual(evaluate("-3+5"), 2)
            self.assertEqual(evaluate("3-(-2)"), 5)
            self.assertEqual(evaluate("-2*-3"), 6)
            self.assertEqual(evaluate("2^0"), 1)
            self.assertEqual(evaluate("4^0.5"), 2)
            self.assertEqual(evaluate("-3^2*2"), -18)

        def test_division_and_ints(self):
            self.assertEqual(evaluate("7/2"), 3.5)
            self.assertEqual(evaluate("6/3"), 2)
            self.assertIsInstance(evaluate("6/3"), int)
            self.assertIsInstance(evaluate("0.5+0.5"), int)
            self.assertIsInstance(evaluate("1.5+1"), float)
            self.assertEqual(evaluate("1.5*2"), 3)
            self.assertIsInstance(evaluate("1.5*2"), int)
            self.assertEqual(evaluate("1/4"), 0.25)

        def test_comparisons(self):
            for src, want in (("1=1", 1), ("1=2", 0), ("1<>2", 1), ("1<>1", 0), ("1<2", 1), ("2<2", 0), ("2<=2", 1), ("3<=2", 0),
                              ("3>2", 1), ("2>2", 0), ("2>=2", 1), ("1>=2", 0), ("1=1=1", 1), ("2=2=2", 0)):
                self.assertEqual(evaluate(src), want, src)

        def test_errors_in_operators(self):
            self.assertEqual(evaluate("1/0"), DIV0)
            self.assertEqual(evaluate("1/(2-2)"), DIV0)
            self.assertEqual(evaluate("0/5"), 0)
            self.assertEqual(evaluate("0^-1"), DIV0)
            self.assertEqual(evaluate("(-8)^0.5"), VALUE)
            self.assertEqual(evaluate("(-8)^2"), 64)
            self.assertEqual(evaluate("(-2)^-1"), -0.5)
            self.assertEqual(evaluate("10^400"), VALUE)
            self.assertEqual(evaluate("1.5^1000000"), VALUE)
            self.assertEqual(evaluate("2^10"), 1024)

        def test_error_propagation_order(self):
            self.assertEqual(evaluate("1/0+A1", {"A1": "x"}), DIV0)
            self.assertEqual(evaluate("A1+1/0", {"A1": "x"}), VALUE)
            self.assertEqual(evaluate("-(1/0)"), DIV0)
            self.assertEqual(evaluate("(1/0)=(1/0)"), DIV0)
            self.assertEqual(evaluate("2+(1/0)*3"), DIV0)

        def test_error_type(self):
            self.assertIsInstance(evaluate("1/0"), CalcError)
            self.assertEqual(DIV0, "#DIV/0!")
            self.assertEqual((VALUE, CYCLE, REF, SYNTAX), ("#VALUE!", "#CYCLE!", "#REF!", "#SYNTAX!"))


    class SyntaxErrors(unittest.TestCase):
        def test_bad_formulas(self):
            for src in ("", "  ", "1+", "(1", "1)", "1 2", "*3", "1+*2", "SUM", "SUM(", "SUM(1", "SUM(1,)", "SUM(,1)", "FOO(1)", "A1:", "A1:2",
                        "A1:B2:C3", "()", "1 +", "2^", "x", "SUM()", "IF(1,2)", "IF(1,2,3,4)", "ABS()", "ABS(1,2)", "ROUND(1)", "ROUND(1,2,3)",
                        "1 = ", "<3", "1,2", "A1 B1"):
                with self.assertRaises(ValueError, msg=repr(src)):
                    parse(src)

        def test_good_formulas_parse(self):
            for src in ("1", "A1", "(A1)", "SUM(A1:B2)", "sum(a1:b2, 3)", "IF(A1>2, 1, 2)", "-A1", "ABS(-1)", "ROUND(2.5, 0)"):
                parse(src)

        def test_range_outside_function(self):
            self.assertEqual(evaluate("A1:B2"), VALUE)
            self.assertEqual(evaluate("A1:B2+1"), VALUE)
            self.assertEqual(evaluate("-A1:B2"), VALUE)


    CELLS = {
        "A1": "10", "A2": "20", "A3": "30", "B1": "2.5", "B2": "hello", "B3": "", "C1": "=A1+A2", "C2": "=C1*2",
        "D1": "=A1/0", "D2": "=D1+1", "E1": "=SUM(A1:A3)", "E2": " 12", "E3": "-7", "F1": "+3",
    }


    class References(unittest.TestCase):
        def test_values_and_blanks(self):
            s = Sheet(CELLS)
            self.assertEqual(s.value("A1"), 10)
            self.assertEqual(s.value("B1"), 2.5)
            self.assertEqual(s.value("B2"), "hello")
            self.assertEqual(s.value("B3"), None)
            self.assertEqual(s.value("Z9"), None)
            self.assertEqual(s.value("a1"), 10)
            self.assertEqual(s.value("A01"), 10)
            self.assertEqual(s.value("E2"), " 12")
            self.assertEqual(s.value("E3"), -7)
            self.assertEqual(s.value("F1"), 3)

        def test_reference_in_formulas(self):
            self.assertEqual(evaluate("A1+A2*2", CELLS), 50)
            self.assertEqual(evaluate("a1+b1", CELLS), 12.5)
            self.assertEqual(evaluate("Z9+1", CELLS), 1)
            self.assertEqual(evaluate("B3*5", CELLS), 0)
            self.assertEqual(evaluate("A1>A2", CELLS), 0)
            self.assertEqual(evaluate("Z9=0", CELLS), 1)

        def test_text_in_arithmetic(self):
            self.assertEqual(evaluate("B2+1", CELLS), VALUE)
            self.assertEqual(evaluate("-B2", CELLS), VALUE)
            self.assertEqual(evaluate("B2=B2", CELLS), VALUE)
            self.assertEqual(evaluate("E2+1", CELLS), VALUE)

        def test_bare_reference_keeps_value(self):
            self.assertEqual(evaluate("B2", CELLS), "hello")
            self.assertEqual(evaluate("(B2)", CELLS), "hello")
            self.assertEqual(evaluate("B3", CELLS), 0)
            self.assertEqual(evaluate("Z9", CELLS), 0)
            self.assertEqual(evaluate("D1", CELLS), DIV0)
            self.assertEqual(evaluate("B1", CELLS), 2.5)

        def test_row_zero(self):
            self.assertEqual(evaluate("A0", CELLS), REF)
            self.assertEqual(evaluate("A0+1", CELLS), REF)
            self.assertEqual(evaluate("SUM(A0)", CELLS), REF)
            self.assertEqual(evaluate("SUM(A0:A1)", CELLS), REF)
            self.assertEqual(evaluate("1+A00"), REF)

        def test_formula_cells_chain(self):
            s = Sheet(CELLS)
            self.assertEqual(s.value("C1"), 30)
            self.assertEqual(s.value("C2"), 60)
            self.assertEqual(s.value("D1"), DIV0)
            self.assertEqual(s.value("D2"), DIV0)
            self.assertEqual(s.value("E1"), 60)

        def test_evaluate_accepts_sheet(self):
            s = Sheet(CELLS)
            self.assertEqual(evaluate("C2+1", s), 61)

        def test_bad_cell_reference_in_sheet(self):
            for key in ("1A", "AA1", "A", "", "A-1"):
                with self.assertRaises(ValueError, msg=repr(key)):
                    Sheet({key: "1"})

        def test_raw_python_numbers(self):
            s = Sheet({"A1": 5, "A2": 2.5, "A3": "=A1*A2"})
            self.assertEqual(s.value("A1"), 5)
            self.assertEqual(s.value("A3"), 12.5)

        def test_none_and_empty_are_blank(self):
            s = Sheet({"A1": None, "A2": "", "A3": "=A1+A2+1"})
            self.assertEqual((s.value("A1"), s.value("A2"), s.value("A3")), (None, None, 1))

        def test_formula_source_is_after_equals(self):
            s = Sheet({"A1": "=2*3", "A2": " =2*3", "A3": "=", "A4": "==1"})
            self.assertEqual(s.value("A1"), 6)
            self.assertEqual(s.value("A2"), " =2*3")
            self.assertEqual(s.value("A3"), SYNTAX)
            self.assertEqual(s.value("A4"), SYNTAX)


    class Cycles(unittest.TestCase):
        def test_direct_and_indirect(self):
            s = Sheet({"A1": "=A1+1", "B1": "=C1", "C1": "=B1", "D1": "=A1", "E1": "=1+D1", "F1": "=2"})
            self.assertEqual(s.value("A1"), CYCLE)
            self.assertEqual(s.value("B1"), CYCLE)
            self.assertEqual(s.value("C1"), CYCLE)
            self.assertEqual(s.value("D1"), CYCLE)
            self.assertEqual(s.value("E1"), CYCLE)
            self.assertEqual(s.value("F1"), 2)

        def test_shared_dependency_is_not_a_cycle(self):
            s = Sheet({"A1": "1", "B1": "=A1", "C1": "=A1", "D1": "=B1+C1"})
            self.assertEqual(s.value("D1"), 2)

        def test_order_of_asking_does_not_matter(self):
            cells = {"A1": "=B1+1", "B1": "=C1+1", "C1": "=A1+1", "D1": "=A1", "E1": "5"}
            for order in (["A1", "B1", "C1", "D1"], ["D1", "C1", "B1", "A1"], ["B1", "D1", "A1", "C1"]):
                s = Sheet(cells)
                self.assertEqual([s.value(r) for r in order], [CYCLE] * 4)

        def test_cycle_in_range_and_if(self):
            s = Sheet({"A1": "=SUM(A1:A2)", "A2": "1", "B1": "=IF(1, 3, B1)", "B2": "=IF(0, 3, B2)"})
            self.assertEqual(s.value("A1"), CYCLE)
            self.assertEqual(s.value("B1"), 3)
            self.assertEqual(s.value("B2"), CYCLE)

        def test_syntax_error_cell(self):
            s = Sheet({"A1": "=1+", "A2": "=A1+1", "A3": "=FOO(1)", "A4": "=(", "A5": "=SUM(A1)"})
            self.assertEqual(s.value("A1"), SYNTAX)
            self.assertEqual(s.value("A2"), SYNTAX)
            self.assertEqual(s.value("A3"), SYNTAX)
            self.assertEqual(s.value("A4"), SYNTAX)
            self.assertEqual(s.value("A5"), SYNTAX)


    class Functions(unittest.TestCase):
        def test_sum_over_ranges(self):
            self.assertEqual(evaluate("SUM(A1:A3)", CELLS), 60)
            self.assertEqual(evaluate("SUM(A3:A1)", CELLS), 60)
            self.assertEqual(evaluate("SUM(A1:B3)", CELLS), 62.5)
            self.assertEqual(evaluate("SUM(B1:A1)", CELLS), 12.5)
            self.assertEqual(evaluate("SUM(A1)", CELLS), 10)
            self.assertEqual(evaluate("SUM(A1, A2, 5)", CELLS), 35)
            self.assertEqual(evaluate("SUM(A1:A2, B1, 1+1)", CELLS), 34.5)
            self.assertEqual(evaluate("SUM(Z1:Z9)", CELLS), 0)

        def test_text_and_blank_skipped(self):
            self.assertEqual(evaluate("SUM(B2)", CELLS), 0)
            self.assertEqual(evaluate("SUM(B3)", CELLS), 0)
            self.assertEqual(evaluate("SUM(B1:B3)", CELLS), 2.5)
            self.assertEqual(evaluate("SUM(E2, A1)", CELLS), 10)
            self.assertEqual(evaluate("COUNT(A1:B3)", CELLS), 4)
            self.assertEqual(evaluate("COUNT(B2, B3, A1)", CELLS), 1)

        def test_expression_arguments_must_be_numbers(self):
            self.assertEqual(evaluate("SUM(B2+0)", CELLS), VALUE)
            self.assertEqual(evaluate("SUM(1, -B2)", CELLS), VALUE)

        def test_errors_in_cells_propagate(self):
            self.assertEqual(evaluate("SUM(D1)", CELLS), DIV0)
            self.assertEqual(evaluate("SUM(A1:D2)", CELLS), DIV0)
            self.assertEqual(evaluate("MAX(1, D1)", CELLS), DIV0)
            self.assertEqual(evaluate("COUNT(D1:D2)", CELLS), DIV0)
            s = Sheet({"A1": "=1/0", "B1": "=A9+", "C1": "=SUM(A1:B1)", "D1": "=SUM(B1:A1)"})
            self.assertEqual(s.value("C1"), DIV0)
            self.assertEqual(s.value("D1"), DIV0)

        def test_first_error_row_major(self):
            s = Sheet({"A1": "=1/0", "B1": "=A9+", "A2": "x", "B2": "=C9:C9"})
            self.assertEqual(evaluate("SUM(A1:B2)", s), DIV0)
            s = Sheet({"A1": "1", "B1": "=A9+", "A2": "=1/0"})
            self.assertEqual(evaluate("SUM(A1:B2)", s), SYNTAX)
            self.assertEqual(evaluate("SUM(A2, B1)", s), DIV0)
            self.assertEqual(evaluate("SUM(B1, A2)", s), SYNTAX)

        def test_avg(self):
            self.assertEqual(evaluate("AVG(A1:A3)", CELLS), 20)
            self.assertEqual(evaluate("AVG(A1:B3)", CELLS), 15.625)
            self.assertEqual(evaluate("AVG(1, 2)", CELLS), 1.5)
            self.assertEqual(evaluate("AVG(B2:B3)", CELLS), DIV0)
            self.assertEqual(evaluate("AVG(Z1)", CELLS), DIV0)

        def test_min_max_count(self):
            self.assertEqual(evaluate("MIN(A1:A3)", CELLS), 10)
            self.assertEqual(evaluate("MAX(A1:A3)", CELLS), 30)
            self.assertEqual(evaluate("MIN(A1:A3, E3)", CELLS), -7)
            self.assertEqual(evaluate("MAX(E3, -9)", CELLS), -7)
            self.assertEqual(evaluate("MIN(B2:B3)", CELLS), 0)
            self.assertEqual(evaluate("MAX(B2)", CELLS), 0)
            self.assertEqual(evaluate("MAX(-5, -3)", CELLS), -3)
            self.assertEqual(evaluate("MIN(5, 3)", CELLS), 3)
            self.assertEqual(evaluate("COUNT(A1:A3)", CELLS), 3)
            self.assertEqual(evaluate("COUNT(Z1:Z3)", CELLS), 0)
            self.assertEqual(evaluate("COUNT(1, 2, 3+4)", CELLS), 3)

        def test_if_is_lazy(self):
            self.assertEqual(evaluate("IF(1, 5, 1/0)"), 5)
            self.assertEqual(evaluate("IF(0, 1/0, 6)"), 6)
            self.assertEqual(evaluate("IF(A1>5, A1, A2)", CELLS), 10)
            self.assertEqual(evaluate("IF(A1>50, A1, A2)", CELLS), 20)
            self.assertEqual(evaluate("IF(-1, 1, 2)"), 1)
            self.assertEqual(evaluate("IF(0.5, 1, 2)"), 1)
            self.assertEqual(evaluate("IF(B3, 1, 2)", CELLS), 2)
            self.assertEqual(evaluate("IF(1/0, 1, 2)"), DIV0)
            self.assertEqual(evaluate("IF(B2, 1, 2)", CELLS), VALUE)
            self.assertEqual(evaluate("IF(1, B2, 2)", CELLS), VALUE)

        def test_abs(self):
            self.assertEqual(evaluate("ABS(-3)"), 3)
            self.assertEqual(evaluate("ABS(3)"), 3)
            self.assertEqual(evaluate("ABS(-2.5)"), 2.5)
            self.assertEqual(evaluate("ABS(E3)", CELLS), 7)
            self.assertEqual(evaluate("ABS(B2)", CELLS), VALUE)
            self.assertEqual(evaluate("ABS(D1)", CELLS), DIV0)

        def test_round(self):
            for src, want in (("ROUND(2.5, 0)", 3), ("ROUND(-2.5, 0)", -3), ("ROUND(2.4, 0)", 2), ("ROUND(-2.4, 0)", -2), ("ROUND(1.25, 1)", 1.3),
                              ("ROUND(-1.25, 1)", -1.3), ("ROUND(3.14159, 2)", 3.14), ("ROUND(1250, -2)", 1300), ("ROUND(1249, -2)", 1200),
                              ("ROUND(-1250, -2)", -1300), ("ROUND(7, 3)", 7), ("ROUND(0.5, 0)", 1), ("ROUND(0, 2)", 0), ("ROUND(15, -1)", 20),
                              ("ROUND(14, -1)", 10), ("ROUND(2.5, 0.0)", 3)):
                self.assertEqual(evaluate(src), want, src)

        def test_round_errors(self):
            self.assertEqual(evaluate("ROUND(1, 0.5)"), VALUE)
            self.assertEqual(evaluate("ROUND(B2, 0)", CELLS), VALUE)
            self.assertEqual(evaluate("ROUND(1, B2)", CELLS), VALUE)
            self.assertEqual(evaluate("ROUND(1/0, 0)"), DIV0)
            self.assertEqual(evaluate("ROUND(1, 1/0)"), DIV0)

        def test_nested_calls_and_case(self):
            self.assertEqual(evaluate("sum(abs(-2), Max(1, 5), round(2.5, 0))"), 10)
            self.assertEqual(evaluate("IF(SUM(A1:A3)>50, ROUND(AVG(A1:A3)/3, 1), 0)", CELLS), 6.7)


    class Values(unittest.TestCase):
        def test_values_listing(self):
            s = Sheet({"B2": "x", "A10": "1", "A2": "=A10+1", "B1": "", "C1": None, "A1": "5", "D1": "=1/0"})
            got = s.values()
            self.assertEqual(list(got), ["A1", "A2", "A10", "B2", "D1"])
            self.assertEqual(got["A2"], 2)
            self.assertEqual(got["D1"], DIV0)
            self.assertEqual(got["B2"], "x")

        def test_values_is_empty_for_empty(self):
            self.assertEqual(Sheet({}).values(), {})
            self.assertEqual(Sheet({"A1": ""}).values(), {})

        def test_keys_normalised(self):
            s = Sheet({"a01": "3", "B2": "=a1*2"})
            self.assertEqual(s.values(), {"A1": 3, "B2": 6})


    class Fmt(unittest.TestCase):
        def test_values(self):
            self.assertEqual(fmt(None), "")
            self.assertEqual(fmt(3), "3")
            self.assertEqual(fmt(-7), "-7")
            self.assertEqual(fmt(1.5), "1.5")
            self.assertEqual(fmt(0.1 + 0.2), "0.3")
            self.assertEqual(fmt(1 / 3), "0.3333333333")
            self.assertEqual(fmt("text"), "text")
            self.assertEqual(fmt(DIV0), "#DIV/0!")
            self.assertEqual(fmt(2.0), "2")
            self.assertEqual(fmt(123456789.125), "123456789.1")


    if __name__ == "__main__":
        unittest.main()
''')

CALC = Lib(
    name="cellcalc", lang="python", title="the spreadsheet formula engine (`cellcalc.py`)",
    blurb="The budget sheets evaluate their cell formulas with this engine.",
    files={"cellcalc.py": CALC_SRC, "README.md": CALC_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": CALC_VISIBLE},
    hidden_tests={"tests/test_full.py": CALC_HIDDEN},
    mutate=["cellcalc.py"], difficulty=4, tags=["parsing", "evaluator"],
    probes=[
        'tokenize("b012 <= SUM(a1:B2) .5")',
        'evaluate("-2^2")',
        'evaluate("2^3^2")',
        'evaluate("2*3<5+2")',
        'evaluate("1/0+A1", {"A1": "x"})',
        'evaluate("A1+1/0", {"A1": "x"})',
        'evaluate("SUM(A1:B3)", {"A1": "10", "A2": "oops", "B1": "2.5"})',
        'evaluate("AVG(A1:A2)", {"A1": "x"})',
        'evaluate("IF(A1, 5, 1/0)", {"A1": "1"})',
        'evaluate("ROUND(-2.5, 0)")',
        'evaluate("ROUND(1250, -2)")',
        'evaluate("B2", {"B2": "hello"})',
        'Sheet({"A1": "=B1", "B1": "=A1", "C1": "=A1+1", "D1": "=1+"}).values()',
        'Sheet({"A2": "=A10+1", "A10": "1", "A1": "5"}).values()',
    ],
    probe_import="from cellcalc import *",
)


LIBS = [WS, CALC]
register_libs(LIBS, n=10)
