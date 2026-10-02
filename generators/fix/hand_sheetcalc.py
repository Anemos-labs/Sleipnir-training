"""A layered python spreadsheet engine (tokens, parser, evaluator, reference ranges, dependency graph, incremental recalculation).
Defects sit in different modules than the symptom; review tickets combine causes."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, combo, tasks_from, with_bugs

README = dd('''
    # sheetcalc

    A tiny spreadsheet engine (`sheet/` package). `Sheet.set(cell, text)`, `Sheet.value(cell)`, `Sheet.show(cell)`.

    ## Cells and input

    A cell name is one letter and a row of 1 to 99 (`A1`, `Z99`), in any case; the canonical form is upper case. Anything else
    is a `ValueError`. The text of a cell:

    * empty text clears the cell;
    * text starting with `=` is a formula;
    * text that is a decimal number (`-3`, `007`, `2.5`, `.5`; no exponent, no `nan`) is a number;
    * anything else is text.

    ## Formulas (`tokens.py`, `parser.py`)

    Numbers, strings in double quotes (`""` inside a string is one quote), cell references, ranges `A1:B3`, function calls
    (`SUM`, `MIN`, `MAX`, `AVG`, `COUNT`, `IF`; names in any case) and the operators below, from the loosest binding to the tightest:

    1. comparisons `= <> < > <= >=` (one per expression: `1<2<3` is a syntax error);
    2. `+ -` (left to right);
    3. `* /` (left to right);
    4. unary minus;
    5. `^`, which associates to the right (`2^3^2` is `2^(3^2)` = 512). Unary minus binds looser than `^` (`-2^2` is -4), but
       the exponent itself may be negative (`2^-1` is 0.5).

    A formula with a syntax error shows `#SYNTAX!`. References such as `A0` or `A100` are syntax errors. Unknown functions give `#NAME?`.
    A range outside a function call gives `#VALUE!`. The two corners of a range may be given in any order (`B3:A1` is `A1:B3`).

    ## Values (`evaluate.py`)

    Numbers are floats, texts are strings, an empty cell is `None`; errors are `Err` values (`#DIV/0!`, `#VALUE!`, `#NUM!`, `#NAME?`,
    `#CYCLE!`, `#SYNTAX!`) and propagate through every operation (the left operand's error first).

    * In arithmetic an empty cell is 0 and a text is `#VALUE!`. `x/0` is `#DIV/0!`. `^` gives `#NUM!` when the result is not a real
      number or does not fit a float, and `#DIV/0!` for `0^negative`.
    * Comparing numbers, or comparing texts (case-insensitively), gives 1 or 0. An empty cell compares as 0 against a number and as
      the empty text against a text. A number against a text is `=` -> 0, `<>` -> 1 and `#VALUE!` for the ordering operators.
    * `IF(cond, a, b)` needs exactly three arguments (else `#VALUE!`); `cond` is true for a non-zero number (a text is `#VALUE!`).
      *Only the chosen branch is evaluated*: an error in the other branch is not an error of the IF.
    * `SUM MIN MAX AVG COUNT` take ranges and expressions. Numbers are collected: in a range, texts and empty cells are skipped;
      a direct argument that is a text is `#VALUE!` and an empty reference is skipped. An error anywhere gives that error.
      `COUNT` is the number of numbers, `SUM` of none is 0, `MIN` and `MAX` of none are 0, `AVG` of none is `#DIV/0!`.
    * A formula whose result is empty (a reference to an empty cell) has the value 0.

    ## Recalculation (`graph.py`, `sheet.py`)

    `Sheet.set` re-evaluates the cell and every cell that depends on it, directly or through other cells (a range depends on
    *every* cell in it). Each affected formula is evaluated exactly once, and only after all the cells it reads are up to date
    (`Sheet.recalc_count` counts formula evaluations). Cells that lie on a dependency cycle (including a cell that reads itself) are
    `#CYCLE!`; cells that merely read such a cell get the same error by propagation. A cell that no longer reads another one (its
    formula was replaced or cleared) no longer depends on it.

    `Sheet.show(cell)` is the text of the value: numbers with at most 10 significant digits and no trailing zeros (`3`, `0.3`,
    `0.3333333333`), the text itself, the error name, and the empty string for an empty cell.
''')

REFS = dd('''
    import re

    CELL = re.compile(r"[A-Za-z]([1-9][0-9]?)")


    def canonical(name):
        """Canonical (upper case) cell name; ValueError if it is not a cell."""
        if not isinstance(name, str) or not CELL.fullmatch(name.strip()):
            raise ValueError(f"bad cell name {name!r}")
        return name.strip().upper()


    def split(name):
        return ord(name[0]) - 65, int(name[1:])


    def cells_in(a, b):
        """Every cell of the rectangle with corners a and b (any order), row by row."""
        c1, r1 = split(a)
        c2, r2 = split(b)
        return [f"{chr(65 + c)}{r}" for r in range(min(r1, r2), max(r1, r2) + 1) for c in range(min(c1, c2), max(c1, c2) + 1)]
''')

TOKENS = dd('''
    from .refs import CELL


    class FormulaError(Exception):
        """A syntax error in a formula."""


    def tokenize(src):
        out = []
        i, n = 0, len(src)
        while i < n:
            c = src[i]
            if c.isspace():
                i += 1
                continue
            if c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit()):
                j = i
                while j < n and (src[j].isdigit() or src[j] == "."):
                    j += 1
                try:
                    out.append(("num", float(src[i:j])))
                except ValueError:
                    raise FormulaError(f"bad number {src[i:j]!r}") from None
                i = j
                continue
            if c == '"':
                j = i + 1
                buf = []
                while True:
                    if j >= n:
                        raise FormulaError("unterminated string")
                    if src[j] == '"':
                        if j + 1 < n and src[j + 1] == '"':
                            buf.append('"')
                            j += 2
                            continue
                        break
                    buf.append(src[j])
                    j += 1
                out.append(("str", "".join(buf)))
                i = j + 1
                continue
            if c.isalpha():
                j = i
                while j < n and src[j].isalnum():
                    j += 1
                word = src[i:j]
                if j < n and src[j] == "(":
                    out.append(("func", word.upper()))
                elif CELL.fullmatch(word):
                    out.append(("ref", word.upper()))
                else:
                    raise FormulaError(f"unknown name {word!r}")
                i = j
                continue
            if src[i:i + 2] in ("<>", "<=", ">="):
                out.append(("op", src[i:i + 2]))
                i += 2
                continue
            if c in "+-*/^=<>(),:":
                out.append(("op", c))
                i += 1
                continue
            raise FormulaError(f"unexpected {c!r}")
        return out
''')

PARSER = dd('''
    from .tokens import FormulaError, tokenize

    COMPARE = ("=", "<>", "<", ">", "<=", ">=")


    class _Parser:
        def __init__(self, tokens):
            self.t = tokens
            self.i = 0

        def peek(self):
            return self.t[self.i] if self.i < len(self.t) else ("end", None)

        def next(self):
            tok = self.peek()
            self.i += 1
            return tok

        def accept(self, value):
            tok = self.peek()
            if tok[0] == "op" and tok[1] == value:
                self.i += 1
                return True
            return False

        def expect(self, value):
            if not self.accept(value):
                raise FormulaError(f"expected {value!r}")

        def expr(self):
            left = self.sum()
            tok = self.peek()
            if tok[0] == "op" and tok[1] in COMPARE:
                self.next()
                return ("bin", tok[1], left, self.sum())
            return left

        def sum(self):
            left = self.term()
            while self.peek()[0] == "op" and self.peek()[1] in ("+", "-"):
                op = self.next()[1]
                left = ("bin", op, left, self.term())
            return left

        def term(self):
            left = self.unary()
            while self.peek()[0] == "op" and self.peek()[1] in ("*", "/"):
                op = self.next()[1]
                left = ("bin", op, left, self.unary())
            return left

        def unary(self):
            if self.accept("-"):
                return ("neg", self.unary())
            return self.power()

        def power(self):
            base = self.atom()
            if self.accept("^"):
                return ("bin", "^", base, self.unary())
            return base

        def atom(self):
            kind, val = self.next()
            if kind in ("num", "str"):
                return (kind, val)
            if kind == "ref":
                if self.accept(":"):
                    k2, v2 = self.next()
                    if k2 != "ref":
                        raise FormulaError("a range needs two cells")
                    return ("range", val, v2)
                return ("ref", val)
            if kind == "func":
                self.expect("(")
                args = []
                if not self.accept(")"):
                    args.append(self.expr())
                    while self.accept(","):
                        args.append(self.expr())
                    self.expect(")")
                return ("call", val, args)
            if kind == "op" and val == "(":
                inner = self.expr()
                self.expect(")")
                return inner
            raise FormulaError(f"unexpected {val!r}" if kind != "end" else "unexpected end")


    def parse(src):
        """Syntax tree of a formula (without the leading `=`)."""
        p = _Parser(tokenize(src))
        tree = p.expr()
        if p.peek()[0] != "end":
            raise FormulaError(f"unexpected {p.peek()[1]!r}")
        return tree
''')

EVALUATE = dd('''
    import math

    from .refs import cells_in


    class Err(str):
        """An error value such as #DIV/0!."""

        __slots__ = ()


    DIV0, VALUE, NAME, NUM = Err("#DIV/0!"), Err("#VALUE!"), Err("#NAME?"), Err("#NUM!")
    CYCLE, SYNTAX = Err("#CYCLE!"), Err("#SYNTAX!")
    COMPARE = ("=", "<>", "<", ">", "<=", ">=")
    AGGREGATES = ("SUM", "MIN", "MAX", "AVG", "COUNT")


    def number(v):
        if isinstance(v, Err):
            return v
        if v is None:
            return 0.0
        if isinstance(v, str):
            return VALUE
        return v


    def evaluate(node, read):
        """Value of a syntax tree; `read(cell)` gives the value of another cell."""
        kind = node[0]
        if kind in ("num", "str"):
            return node[1]
        if kind == "ref":
            return read(node[1])
        if kind == "range":
            return VALUE
        if kind == "neg":
            v = number(evaluate(node[1], read))
            return v if isinstance(v, Err) else -v
        if kind == "bin":
            return _binary(node[1], evaluate(node[2], read), evaluate(node[3], read))
        return _call(node[1], node[2], read)


    def _binary(op, left, right):
        if op in COMPARE:
            return _compare(op, left, right)
        left, right = number(left), number(right)
        for v in (left, right):
            if isinstance(v, Err):
                return v
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            return DIV0 if right == 0 else left / right
        return _power(left, right)


    def _power(a, b):
        try:
            r = a ** b
        except ZeroDivisionError:
            return DIV0
        except OverflowError:
            return NUM
        return NUM if isinstance(r, complex) else r


    def _compare(op, left, right):
        for v in (left, right):
            if isinstance(v, Err):
                return v
        if left is None:
            left = "" if isinstance(right, str) else 0.0
        if right is None:
            right = "" if isinstance(left, str) else 0.0
        if isinstance(left, str) != isinstance(right, str):
            if op == "=":
                return 0.0
            if op == "<>":
                return 1.0
            return VALUE
        if isinstance(left, str):
            left, right = left.lower(), right.lower()
        result = {"=": left == right, "<>": left != right, "<": left < right, ">": left > right, "<=": left <= right, ">=": left >= right}[op]
        return 1.0 if result else 0.0


    def _call(name, args, read):
        if name == "IF":
            if len(args) != 3:
                return VALUE
            cond = evaluate(args[0], read)
            if isinstance(cond, Err):
                return cond
            if cond is None:
                cond = 0.0
            if isinstance(cond, str):
                return VALUE
            return evaluate(args[1] if cond != 0 else args[2], read)
        if name not in AGGREGATES:
            return NAME
        nums = []
        for a in args:
            if a[0] == "range":
                for ref in cells_in(a[1], a[2]):
                    v = read(ref)
                    if isinstance(v, Err):
                        return v
                    if isinstance(v, float):
                        nums.append(v)
            else:
                v = evaluate(a, read)
                if isinstance(v, Err):
                    return v
                if v is None:
                    continue
                if isinstance(v, str):
                    return VALUE
                nums.append(v)
        if name == "COUNT":
            return float(len(nums))
        if name == "SUM":
            return math.fsum(nums)
        if not nums:
            return DIV0 if name == "AVG" else 0.0
        if name == "AVG":
            return math.fsum(nums) / len(nums)
        return min(nums) if name == "MIN" else max(nums)
''')

GRAPH = dd('''
    from .refs import cells_in


    def refs_of(node):
        """The set of cells a syntax tree reads (every cell of a range)."""
        kind = node[0]
        if kind == "ref":
            return {node[1]}
        if kind == "range":
            return set(cells_in(node[1], node[2]))
        if kind == "neg":
            return refs_of(node[1])
        if kind == "bin":
            return refs_of(node[2]) | refs_of(node[3])
        if kind == "call":
            out = set()
            for a in node[2]:
                out |= refs_of(a)
            return out
        return set()


    def closure(start, users):
        """`start` and every cell that reads it, directly or through others."""
        seen = {start}
        todo = [start]
        while todo:
            c = todo.pop()
            for u in users.get(c, ()):
                if u not in seen:
                    seen.add(u)
                    todo.append(u)
        return seen


    def cyclic(nodes, users):
        """The nodes that lie on a cycle of the `users` graph (a node that is its own user included)."""
        out = set()
        for n in nodes:
            seen = set()
            todo = [u for u in users.get(n, ()) if u in nodes]
            while todo:
                c = todo.pop()
                if c == n:
                    out.add(n)
                    break
                if c in seen:
                    continue
                seen.add(c)
                todo.extend(u for u in users.get(c, ()) if u in nodes)
        return out


    def toposort(nodes, deps):
        """The nodes ordered so that every cell comes after the cells it reads (only edges inside `nodes` count)."""
        order = []
        done = set()

        def visit(c):
            if c in done:
                return
            done.add(c)
            for d in sorted(deps.get(c, ())):
                if d in nodes:
                    visit(d)
            order.append(c)

        for c in sorted(nodes):
            visit(c)
        return order
''')

SHEET = dd(r'''
    import re

    from .evaluate import CYCLE, SYNTAX, Err, evaluate
    from .graph import closure, cyclic, refs_of, toposort
    from .parser import parse
    from .refs import canonical
    from .tokens import FormulaError

    NUMBER = re.compile(r"-?(\d+\.?\d*|\.\d+)")


    class Sheet:
        def __init__(self):
            self._text = {}
            self._ast = {}
            self._value = {}
            self._deps = {}
            self._users = {}
            self.recalc_count = 0

        def set(self, cell, text):
            cell = canonical(cell)
            text = text.strip()
            self._unlink(cell)
            self._ast.pop(cell, None)
            if text == "":
                self._text.pop(cell, None)
                self._value.pop(cell, None)
            else:
                self._text[cell] = text
                if text.startswith("="):
                    try:
                        self._ast[cell] = parse(text[1:])
                    except FormulaError:
                        self._value[cell] = SYNTAX
                    else:
                        self._link(cell, refs_of(self._ast[cell]))
                elif NUMBER.fullmatch(text):
                    self._value[cell] = float(text)
                else:
                    self._value[cell] = text
            self._recalc(cell)

        def value(self, cell):
            return self._value.get(canonical(cell))

        def show(self, cell):
            v = self.value(cell)
            if v is None:
                return ""
            if isinstance(v, float):
                return format(v + 0.0, ".10g")
            return str(v)

        def cells(self):
            return sorted(self._text)

        def _link(self, cell, reads):
            self._deps[cell] = set(reads)
            for r in reads:
                self._users.setdefault(r, set()).add(cell)

        def _unlink(self, cell):
            for r in self._deps.pop(cell, ()):
                self._users.get(r, set()).discard(cell)

        def _read(self, cell):
            return self._value.get(cell)

        def _recalc(self, start):
            affected = closure(start, self._users)
            loops = cyclic(affected, self._users)
            for c in loops:
                self._value[c] = CYCLE
            rest = affected - loops
            for c in toposort(rest, self._deps):
                if c in self._ast:
                    v = evaluate(self._ast[c], self._read)
                    self._value[c] = 0.0 if v is None else v
                    self.recalc_count += 1
''')

INIT = '"""A tiny spreadsheet engine."""\nfrom .sheet import Sheet\nfrom .evaluate import Err\n\n__all__ = ["Sheet", "Err"]\n'

VISIBLE = {
    "tests/test_basic.py": dd('''
        import unittest

        from sheet import Sheet


        class Basic(unittest.TestCase):
            def test_formula_and_dependents(self):
                s = Sheet()
                s.set("A1", "2")
                s.set("B1", "=A1*3")
                s.set("C1", "=B1+1")
                self.assertEqual(s.show("C1"), "7")
                s.set("A1", "10")
                self.assertEqual(s.show("C1"), "31")

            def test_text_and_sum(self):
                s = Sheet()
                s.set("A1", "1")
                s.set("A2", "x")
                s.set("A3", "4.5")
                s.set("B1", "=SUM(A1:A3)")
                self.assertEqual(s.show("A2"), "x")
                self.assertEqual(s.show("B1"), "5.5")

            def test_division_by_zero(self):
                s = Sheet()
                s.set("A1", "=1/0")
                self.assertEqual(s.show("A1"), "#DIV/0!")


        if __name__ == "__main__":
            unittest.main()
    '''),
}


HIDDEN = {
    "tests/test_hidden_sheet.py": dd('''
        import random
        import unittest

        from sheet import Err, Sheet
        from sheet.tokens import tokenize


        def book(**cells):
            s = Sheet()
            for k, v in cells.items():
                s.set(k, v)
            return s


        def shown(formula, **cells):
            s = book(**cells)
            s.set("Z1", "=" + formula)
            return s.show("Z1")


        class Input(unittest.TestCase):
            def test_cell_names(self):
                s = Sheet()
                s.set("a1", "1")
                self.assertEqual(s.value("A1"), 1.0)
                self.assertEqual(s.value("a1"), 1.0)
                for bad in ["A0", "AA1", "1A", "A100", "", "A-1", "A 1", "A01"]:
                    with self.assertRaises(ValueError, msg=bad):
                        s.set(bad, "1")
                with self.assertRaises(ValueError):
                    s.value("A100")

            def test_numbers_and_text(self):
                s = book(A1="007", A2="-3", A3=".5", A4="2.5", A5="1e5", A6="nan", A7=" 12 ", A8="abc", A9="=")
                self.assertEqual([s.value(c) for c in ("A1", "A2", "A3", "A4", "A7")], [7.0, -3.0, 0.5, 2.5, 12.0])
                self.assertEqual([s.value(c) for c in ("A5", "A6", "A8")], ["1e5", "nan", "abc"])
                self.assertEqual(s.show("A9"), "#SYNTAX!")

            def test_clearing(self):
                s = book(A1="5")
                s.set("A1", "")
                self.assertIsNone(s.value("A1"))
                self.assertEqual(s.show("A1"), "")
                self.assertEqual(s.cells(), [])


        class Tokens(unittest.TestCase):
            def test_tokens(self):
                self.assertEqual(tokenize("1.5+a1"), [("num", 1.5), ("op", "+"), ("ref", "A1")])
                self.assertEqual(tokenize("sum(A1:B2)")[0], ("func", "SUM"))

            def test_leading_dot_numbers(self):
                self.assertEqual(shown(".5+1"), "1.5")
                self.assertEqual(shown("1.2.3"), "#SYNTAX!")
                self.assertEqual(shown("2*.25"), "0.5")

            def test_string_escapes(self):
                self.assertEqual(shown('"say ""hi"""'), 'say "hi"')
                self.assertEqual(shown('""'), "")
                self.assertEqual(shown('"a""b"'), 'a"b')
                self.assertEqual(shown('"abc'), "#SYNTAX!")

            def test_lowercase_references_read_the_cell(self):
                self.assertEqual(shown("a1*3", A1="2"), "6")
                s = book(A1="2")
                s.set("B1", "=a1+1")
                s.set("A1", "10")
                self.assertEqual(s.show("B1"), "11")
                s.set("C1", "=SUM(a1:a2)")
                s.set("A2", "5")
                self.assertEqual(s.show("C1"), "15")


        class Parser(unittest.TestCase):
            def test_precedence_and_associativity(self):
                cases = [
                    ("2+3*4", "14"), ("(2+3)*4", "20"), ("2^3^2", "512"), ("-2^2", "-4"), ("2^-1", "0.5"), ("10-4-3", "3"),
                    ("2*3^2", "18"), ("100/10/5", "2"), ("2*-3", "-6"), ("--3", "3"), ("-(2+3)^2", "-25"), ("2^2*3", "12"),
                ]
                for text, want in cases:
                    self.assertEqual(shown(text), want, text)
                self.assertEqual(shown("-A1^2", A1="3"), "-9")

            def test_comparisons_are_loosest(self):
                cases = [("1+2>2", "1"), ("1>2+3", "0"), ("2*3=6", "1"), ("1<2", "1"), ('"b">"a"', "1"), ("1+1<>2", "0"), ("5>=2+3", "1"), ("1<=2-3", "0")]
                for text, want in cases:
                    self.assertEqual(shown(text), want, text)
                self.assertEqual(shown("A1>B1+1", A1="5", B1="3"), "1")

            def test_comparisons_do_not_chain(self):
                self.assertEqual(shown("1<2<3"), "#SYNTAX!")
                self.assertEqual(shown("1=1=1"), "#SYNTAX!")

            def test_syntax_errors(self):
                for text in ["1+", "(1", "SUM(1,", ")", "1 2", "*3", "1+*2", "A0", "A100", '"x', "AA1", "SUM(A1:)", "A1:B", "1..2", "#", "2^"]:
                    self.assertEqual(shown(text), "#SYNTAX!", text)

            def test_names_and_ranges(self):
                self.assertEqual(shown("FOO(1)"), "#NAME?")
                self.assertEqual(shown("sum(1,2)"), "3")
                self.assertEqual(shown("A1:B2"), "#VALUE!")
                self.assertEqual(shown("1+A1:A2"), "#VALUE!")
                self.assertEqual(shown("SUM()"), "0")

            def test_range_corners_in_any_order(self):
                cells = dict(A1="1", B1="2", A2="3", B2="4", A3="5", B3="6")
                self.assertEqual(shown("SUM(A1:B3)", **cells), "21")
                self.assertEqual(shown("SUM(B3:A1)", **cells), "21")
                self.assertEqual(shown("SUM(A3:B1)", **cells), "21")
                self.assertEqual(shown("COUNT(B1:A3)", **cells), "6")


        class Evaluate(unittest.TestCase):
            def test_errors_propagate_left_first(self):
                s = book(A1="=1/0")
                s.set("B1", "=A1+1")
                s.set("C1", "=SUM(A1:A2)")
                s.set("D1", "=IF(A1,1,2)")
                s.set("E1", "=-A1")
                self.assertEqual([s.show(f"{c}1") for c in "BCDE"], ["#DIV/0!"] * 4)
                self.assertIsInstance(s.value("B1"), Err)
                self.assertEqual(shown("1/0+(-8)^0.5"), "#DIV/0!")
                self.assertEqual(shown("(-8)^0.5+1/0"), "#NUM!")

            def test_empty_and_text_in_arithmetic(self):
                self.assertEqual(shown("Q9+1"), "1")
                self.assertEqual(shown("Q9"), "0")
                self.assertEqual(shown("A1+1", A1="x"), "#VALUE!")
                self.assertEqual(shown("-A1", A1="x"), "#VALUE!")
                self.assertEqual(shown('"a"+1'), "#VALUE!")
                s = book(A1="=B9")
                self.assertEqual(s.value("A1"), 0.0)

            def test_power_domain(self):
                cases = [("0^-1", "#DIV/0!"), ("(-8)^0.5", "#NUM!"), ("10^400", "#NUM!"), ("(-8)^(1/3)", "#NUM!"), ("2^0.5", "1.414213562"),
                         ("(-2)^3", "-8"), ("0^0", "1"), ("2^-2", "0.25")]
                for text, want in cases:
                    self.assertEqual(shown(text), want, text)

            def test_comparison_semantics(self):
                cases = [('"a"="A"', "1"), ('"a"<"b"', "1"), ('1="1"', "0"), ('1<>"1"', "1"), ('1<"1"', "#VALUE!"), ("Q9=0", "1"),
                         ('Q9=""', "1"), ("Q9<1", "1"), ('Q9<"a"', "1"), ("1/0=1", "#DIV/0!")]
                for text, want in cases:
                    self.assertEqual(shown(text), want, text)

            def test_if_takes_the_chosen_branch_only(self):
                self.assertEqual(shown('IF(1,"y","n")'), "y")
                self.assertEqual(shown('IF(0,"y","n")'), "n")
                self.assertEqual(shown('IF(B1=0,"n/a",A1/B1)', A1="5", B1="0"), "n/a")
                self.assertEqual(shown("IF(B1,A1/B1,0)", A1="5", B1="0"), "0")
                self.assertEqual(shown("IF(B1,A1/B1,0)", A1="5", B1="2"), "2.5")
                self.assertEqual(shown('IF(1,2,"x"+1)'), "2")
                self.assertEqual(shown("IF(1,1/0,2)"), "#DIV/0!")
                self.assertEqual(shown("IF(Q9,1,2)"), "2")
                self.assertEqual(shown('IF("x",1,2)'), "#VALUE!")
                self.assertEqual(shown("IF(1,2)"), "#VALUE!")
                self.assertEqual(shown("IF(1,2,3,4)"), "#VALUE!")
                self.assertEqual(shown("IF(1/0,2,3)"), "#DIV/0!")

            def test_aggregates_on_ranges(self):
                cells = dict(A1="1", A2="x", A4="4", A5="-3", B1="=2")
                self.assertEqual(shown("SUM(A1:A4)", **cells), "5")
                self.assertEqual(shown("MIN(A1:A4)", **cells), "1")
                self.assertEqual(shown("MAX(A1:A4)", **cells), "4")
                self.assertEqual(shown("AVG(A1:A4)", **cells), "2.5")
                self.assertEqual(shown("COUNT(A1:A4)", **cells), "2")
                self.assertEqual(shown("MAX(A5:A6)", **cells), "-3")
                self.assertEqual(shown("MIN(A4:A6)", **cells), "-3")
                self.assertEqual(shown("AVG(A5:A6)", **cells), "-3")
                self.assertEqual(shown("COUNT(A1:B2)", **cells), "2")

            def test_aggregates_of_nothing(self):
                self.assertEqual(shown("SUM(C1:C3)"), "0")
                self.assertEqual(shown("MIN(C1:C3)"), "0")
                self.assertEqual(shown("MAX(C1:C3)"), "0")
                self.assertEqual(shown("AVG(C1:C3)"), "#DIV/0!")
                self.assertEqual(shown("COUNT(C1:C3)"), "0")

            def test_aggregates_on_direct_arguments(self):
                cells = dict(A1="1", A2="x", A4="4")
                self.assertEqual(shown("SUM(A1,A4,10)", **cells), "15")
                self.assertEqual(shown("SUM(A2)", **cells), "#VALUE!")
                self.assertEqual(shown("SUM(Q9,1)"), "1")
                self.assertEqual(shown("MAX(-5,-2)"), "-2")
                self.assertEqual(shown("SUM(A1:A4,100)", **cells), "105")
                self.assertEqual(shown("SUM(A1:A2,B1)", A1="1", B1="=1/0"), "#DIV/0!")

            def test_errors_inside_ranges(self):
                self.assertEqual(shown("SUM(A1:A3)", A1="1", A3="=1/0"), "#DIV/0!")
                self.assertEqual(shown("COUNT(A1:A3)", A1="1", A3="=1/0"), "#DIV/0!")


        class Recalc(unittest.TestCase):
            def test_chain_each_cell_once(self):
                s = book(A1="1", B1="=A1+1", C1="=B1+1", D1="=C1+1")
                before = s.recalc_count
                s.set("A1", "5")
                self.assertEqual(s.recalc_count - before, 3)
                self.assertEqual(s.show("D1"), "8")

            def test_chain_against_the_alphabet(self):
                s = book(D1="1", C1="=D1+1", B1="=C1+1", A1="=B1+1")
                self.assertEqual(s.show("A1"), "4")
                before = s.recalc_count
                s.set("D1", "10")
                self.assertEqual([s.show(c) for c in ("C1", "B1", "A1")], ["11", "12", "13"])
                self.assertEqual(s.recalc_count - before, 3)

            def test_diamond(self):
                s = book(A1="1", B1="=A1+1", C1="=A1*10", D1="=B1+C1")
                self.assertEqual(s.show("D1"), "12")
                before = s.recalc_count
                s.set("A1", "2")
                self.assertEqual(s.show("D1"), "23")
                self.assertEqual(s.recalc_count - before, 3)

            def test_fan_out_and_in(self):
                s = book(A1="1", C1="=SUM(B1:B5)")
                for r in range(1, 6):
                    s.set(f"B{r}", "=A1+1")
                self.assertEqual(s.show("C1"), "10")
                before = s.recalc_count
                s.set("A1", "2")
                self.assertEqual(s.show("C1"), "15")
                self.assertEqual(s.recalc_count - before, 6)

            def test_counts_only_formulas(self):
                s = Sheet()
                s.set("A1", "5")
                self.assertEqual(s.recalc_count, 0)
                s.set("B1", "=A1")
                self.assertEqual(s.recalc_count, 1)

            def test_cycles(self):
                s = book(A1="=B1")
                s.set("B1", "=A1")
                s.set("C1", "=A1+1")
                s.set("D1", "=1+1")
                s.set("E1", "=E1+1")
                self.assertEqual([s.show(c) for c in ("A1", "B1", "C1", "D1", "E1")], ["#CYCLE!", "#CYCLE!", "#CYCLE!", "2", "#CYCLE!"])
                self.assertIsInstance(s.value("A1"), Err)

            def test_longer_cycles_and_breaking_them(self):
                s = book(F1="=G1", G1="=H1", H1="=F1")
                s.set("I1", "=F1")
                self.assertEqual([s.show(c) for c in ("F1", "G1", "H1", "I1")], ["#CYCLE!"] * 4)
                s.set("H1", "7")
                self.assertEqual([s.show(c) for c in ("F1", "G1", "H1", "I1")], ["7"] * 4)

            def test_cycle_through_a_range(self):
                s = book(A1="=SUM(B1:B3)")
                s.set("B2", "=A1")
                self.assertEqual((s.show("A1"), s.show("B2")), ("#CYCLE!", "#CYCLE!"))
                s.set("B2", "4")
                self.assertEqual(s.show("A1"), "4")

            def test_no_phantom_cycles(self):
                s = book(A1="=B1")
                s.set("A1", "5")
                s.set("B1", "=A1")
                self.assertEqual((s.show("A1"), s.show("B1")), ("5", "5"))
                t = book(A1="=B1+1")
                t.set("A1", "=C1+1")
                t.set("B1", "=A1")
                self.assertEqual((t.show("A1"), t.show("B1")), ("1", "1"))

            def test_replaced_formulas_stop_depending(self):
                s = book(A1="=B1")
                s.set("A1", "=C1")
                before = s.recalc_count
                s.set("B1", "9")
                self.assertEqual(s.recalc_count - before, 0)
                s.set("C1", "3")
                self.assertEqual(s.show("A1"), "3")
                s.set("A1", "8")
                before = s.recalc_count
                s.set("C1", "4")
                self.assertEqual(s.recalc_count - before, 0)

            def test_ranges_depend_on_every_cell(self):
                s = book(A1="1", A2="2", A3="3", B1="=SUM(A1:A3)")
                s.set("A2", "10")
                self.assertEqual(s.show("B1"), "14")
                s.set("A3", "x")
                self.assertEqual(s.show("B1"), "11")
                t = book(C1="=MAX(A1:B3)")
                t.set("B2", "99")
                self.assertEqual(t.show("C1"), "99")
                t.set("B2", "")
                self.assertEqual(t.show("C1"), "0")

            def test_clearing_a_cell(self):
                s = book(A1="5", B1="=A1+1")
                self.assertEqual(s.show("B1"), "6")
                s.set("A1", "")
                self.assertEqual(s.show("B1"), "1")

            def test_syntax_errors_and_recovery(self):
                s = book(A1="=1+", B1="=A1+1")
                self.assertEqual(s.show("B1"), "#SYNTAX!")
                s.set("A1", "2")
                self.assertEqual(s.show("B1"), "3")
                t = book(A1="=1/0", B1="=A1+1")
                t.set("A1", "4")
                self.assertEqual(t.show("B1"), "5")

            def test_display_formats(self):
                cases = [("0.1+0.2", "0.3"), ("6/2", "3"), ("1/3", "0.3333333333"), ("2^70", "1.180591621e+21"), ("-0*1", "0"),
                         ("1/8", "0.125"), ("100*1.1", "110"), ("2/3*3", "2")]
                for text, want in cases:
                    self.assertEqual(shown(text), want, text)
                s = book(A1="x")
                self.assertEqual(s.show("A1"), "x")
                self.assertEqual(s.show("A2"), "")

            def test_incremental_equals_from_scratch(self):
                rng = random.Random(1234)
                names = [f"{c}{r}" for c in "ABCD" for r in range(1, 5)]
                templates = ["{n}", "=-{a}", "={a}+{b}", "={a}*2", "=SUM({a}:{b})", "=IF({a},{b},{c})", "=MAX({a}:{b})-1", "={a}/{b}",
                             "=AVG({a}:{b})", "=COUNT({a}:{b})+{c}", '="t"', "x", "", "={a}"]
                texts = {}
                s = Sheet()
                for step in range(300):
                    cell = rng.choice(names)
                    t = rng.choice(templates)
                    text = str(rng.randint(-3, 9)) if t == "{n}" else t.format(a=rng.choice(names), b=rng.choice(names), c=rng.choice(names))
                    s.set(cell, text)
                    if text.strip() == "":
                        texts.pop(cell, None)
                    else:
                        texts[cell] = text.strip()
                    fresh = Sheet()
                    for c in sorted(texts):
                        fresh.set(c, texts[c])
                    got = {c: s.show(c) for c in names}
                    want = {c: fresh.show(c) for c in names}
                    self.assertEqual(got, want, f"step {step}: {cell} <- {text!r}")


        if __name__ == "__main__":
            unittest.main()
    '''),
}


REPORTED_POWER = {
    "tests/test_reported.py": dd('''
        import unittest

        from sheet import Sheet


        class Reported(unittest.TestCase):
            def test_exponent_chain(self):
                s = Sheet()
                s.set("A1", "=2^3^2")
                self.assertEqual(s.show("A1"), "512")


        if __name__ == "__main__":
            unittest.main()
    '''),
}

REPORTED_DISPLAY = {
    "tests/test_reported.py": dd('''
        import unittest

        from sheet import Sheet


        class Reported(unittest.TestCase):
            def test_sum_of_tenths(self):
                s = Sheet()
                s.set("A1", "0.1")
                s.set("A2", "0.2")
                s.set("A3", "=A1+A2")
                self.assertEqual(s.show("A3"), "0.3")


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _prompts() -> dict:
    p = {}
    p["lowercase"] = (
        "Typing `=a1*3` in the formula bar next to a filled A1 gives 0, although `=A1*3` works, and when A1 is changed later the "
        "lowercase formula does not update either. The README says cell names are case-insensitive."
    )
    p["dot"] = "`=.5+1` is rejected as a syntax error but `=0.5+1` works. Our users paste numbers like `.25` from other tools."
    p["quotes"] = (
        "Tester note: a text formula with doubled quotes, `=\"say \"\"hi\"\"\"`, shows #SYNTAX! (it should be the text `say \"hi\"`; the README "
        "says `\"\"` inside a string is one quote)."
    )
    p["power-left"] = lambda c: (
        "`=2^3^2` shows 64, but the reference says `^` associates to the right (512). A reduced test from CI:\n\n```\n"
        + c.visible_out(12) + "\n```\n"
    )
    p["minus"] = (
        "`=-2^2` shows 4. The README says unary minus binds looser than `^`, so it is -4 (and `=--3` should be 3, it is rejected as a syntax error)."
    )
    p["compare"] = (
        "`=A1>B1+1` with A1=5 and B1=3 shows 2 instead of 1: it looks as if the comparison is done before the addition. Comparison "
        "operators are the loosest in the language, and `=1<2<3` should be a syntax error but is accepted."
    )
    p["corners"] = (
        "`=SUM(B3:A1)` is 0 while `=SUM(A1:B3)` is 21. People drag a selection from the bottom right to the top left and get reversed "
        "corners; the README says the corners may be in any order."
    )

    def power_domain(c):
        tb = c.bad_run('from sheet import Sheet\ns = Sheet()\ns.set("A1", "=0^-1")\nprint(s.show("A1"))\n')
        return (
            "Our fuzzing job found that entering `=0^-1` crashes the whole sheet with a Python exception:\n\n```\n" + tb + "\n```\n\n"
            "`=(-8)^0.5` does not crash but shows a complex number such as `(1.7e-16+2.8j)` and `=10^400` crashes with an OverflowError. "
            "The README says what these must show."
        )

    p["power-domain"] = power_domain
    p["if-both"] = (
        "`=IF(B1=0,\"n/a\",A1/B1)` shows #DIV/0! when B1 is 0: the whole point of the IF is to avoid the division. Only the chosen branch "
        "should be evaluated."
    )
    p["empties-zero"] = (
        "MIN over a column with blank cells shows 0, MAX over negative numbers with a blank cell shows 0, and AVG is too small. Blank "
        "cells (and texts) in a range must be skipped."
    )
    p["avg"] = (
        "`=AVG(A1:A4)` over the cells 1, x, (blank), 4 shows 1.25; it should be 2.5, the average of the numbers. It seems to divide by the "
        "number of cells in the range."
    )
    p["show"] = lambda c: (
        "The grid shows totals like 0.30000000000000004 and 3.0. A reduced test from CI:\n\n```\n" + c.visible_out(12) + "\n```\n"
    )
    p["transitive"] = (
        "In a chain A1 -> B1 -> C1 -> D1 only B1 updates when I change A1; C1 and D1 keep their old values until I retype them."
    )
    p["cycles"] = (
        "Three-cell circular references (F1 `=G1`, G1 `=H1`, H1 `=F1`) are not reported: the cells show stale numbers instead of #CYCLE!. "
        "A cell that refers to itself is reported correctly."
    )
    p["order"] = (
        "Cells sometimes keep a stale value after a change, depending on how they are named: with A1 `=B1+1`, B1 `=C1+1`, C1 `=D1+1`, "
        "changing D1 updates C1 and B1 but A1 shows the old number (or some of them do)."
    )
    p["stale"] = (
        "After I replace a formula by a constant, a later `=A1` in the other cell reports #CYCLE! (A1 used to be `=B1`, now it is just 5, and "
        "B1 is `=A1`). The pair is not circular. Also, editing B1 recalculates A1 although A1 no longer reads it."
    )
    p["range-middle"] = "`=SUM(A1:A3)` does not change when I edit A2, only when I edit A1 or A3."
    return p


def _base() -> Base:
    P = _prompts()
    good = {
        "README.md": README, "sheet/__init__.py": INIT, "sheet/refs.py": REFS, "sheet/tokens.py": TOKENS, "sheet/parser.py": PARSER,
        "sheet/evaluate.py": EVALUATE, "sheet/graph.py": GRAPH, "sheet/sheet.py": SHEET,
    }
    rf, tk, pa, ev, gr, sh = ("sheet/refs.py", "sheet/tokens.py", "sheet/parser.py", "sheet/evaluate.py", "sheet/graph.py", "sheet/sheet.py")
    lowercase = ('            out.append(("ref", word.upper()))\n'.replace("            ", "                ", 1), '                out.append(("ref", word))\n')
    dot = ('        if c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit()):\n', "        if c.isdigit():\n")
    quotes = ("                if src[j] == '\"':\n                    if j + 1 < n and src[j + 1] == '\"':\n                        buf.append('\"')\n                        j += 2\n                        continue\n                    break\n",
              "                if src[j] == '\"':\n                    break\n")
    power_left = ("    def power(self):\n        base = self.atom()\n        if self.accept(\"^\"):\n            return (\"bin\", \"^\", base, self.unary())\n        return base\n",
                  "    def power(self):\n        base = self.atom()\n        while self.accept(\"^\"):\n            exponent = (\"neg\", self.atom()) if self.accept(\"-\") else self.atom()\n            base = (\"bin\", \"^\", base, exponent)\n        return base\n")
    minus = [("    def unary(self):\n        if self.accept(\"-\"):\n            return (\"neg\", self.unary())\n        return self.power()\n", "    def unary(self):\n        return self.power()\n"),
             ("    def power(self):\n        base = self.atom()\n", "    def power(self):\n        base = (\"neg\", self.atom()) if self.accept(\"-\") else self.atom()\n")]
    compare = ("        while self.peek()[0] == \"op\" and self.peek()[1] in (\"+\", \"-\"):\n", "        while self.peek()[0] == \"op\" and self.peek()[1] in (\"+\", \"-\") + COMPARE:\n")
    corners = ("    return [f\"{chr(65 + c)}{r}\" for r in range(min(r1, r2), max(r1, r2) + 1) for c in range(min(c1, c2), max(c1, c2) + 1)]\n",
               "    return [f\"{chr(65 + c)}{r}\" for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]\n")
    power_domain = ("def _power(a, b):\n    try:\n        r = a ** b\n    except ZeroDivisionError:\n        return DIV0\n    except OverflowError:\n        return NUM\n    return NUM if isinstance(r, complex) else r\n",
                    "def _power(a, b):\n    return a ** b\n")
    if_both = ("        return evaluate(args[1] if cond != 0 else args[2], read)\n",
               "        a, b = evaluate(args[1], read), evaluate(args[2], read)\n        for v in (a, b):\n            if isinstance(v, Err):\n                return v\n        return a if cond != 0 else b\n")
    empties = ("                if isinstance(v, float):\n                    nums.append(v)\n", "                nums.append(v if isinstance(v, float) else 0.0)\n")
    avg = [("    nums = []\n    for a in args:\n", "    nums = []\n    cells = 0\n    for a in args:\n"),
           ("            for ref in cells_in(a[1], a[2]):\n                v = read(ref)\n", "            for ref in cells_in(a[1], a[2]):\n                cells += 1\n                v = read(ref)\n"),
           ("    if name == \"AVG\":\n        return math.fsum(nums) / len(nums)\n", "    if name == \"AVG\":\n        return math.fsum(nums) / max(cells, len(nums))\n")]
    show = ("            return format(v + 0.0, \".10g\")\n", "            return str(v)\n")
    transitive = ("    seen = {start}\n    todo = [start]\n    while todo:\n        c = todo.pop()\n        for u in users.get(c, ()):\n            if u not in seen:\n                seen.add(u)\n                todo.append(u)\n    return seen\n",
                  "    return {start} | set(users.get(start, ()))\n")
    loops = ("    out = set()\n    for n in nodes:\n        seen = set()\n        todo = [u for u in users.get(n, ()) if u in nodes]\n        while todo:\n            c = todo.pop()\n            if c == n:\n                out.add(n)\n                break\n            if c in seen:\n                continue\n            seen.add(c)\n            todo.extend(u for u in users.get(c, ()) if u in nodes)\n    return out\n",
             "    return {n for n in nodes if n in users.get(n, ())}\n")
    order = ("    order = []\n    done = set()\n\n    def visit(c):\n        if c in done:\n            return\n        done.add(c)\n        for d in sorted(deps.get(c, ())):\n            if d in nodes:\n                visit(d)\n        order.append(c)\n\n    for c in sorted(nodes):\n        visit(c)\n    return order\n",
             "    return sorted(nodes)\n")
    stale = ("        for r in self._deps.pop(cell, ()):\n            self._users.get(r, set()).discard(cell)\n", "        self._deps.pop(cell, None)\n")
    range_middle = ("        return set(cells_in(node[1], node[2]))\n", "        return {node[1], node[2]}\n")
    bugs = [
        Bug("leading-dot-numbers-rejected", 2, {tk: [dot]}, P["dot"]),
        Bug("doubled-quotes-not-unescaped", 2, {tk: [quotes]}, P["quotes"]),
        Bug("lowercase-references-read-nothing", 4, {tk: [lowercase]}, P["lowercase"]),
        Bug("power-associates-left", 3, {pa: [power_left]}, P["power-left"], reported=REPORTED_POWER),
        Bug("minus-binds-tighter-than-power", 3, {pa: minus}, P["minus"]),
        Bug("comparison-as-tight-as-plus", 3, {pa: [compare]}, P["compare"]),
        Bug("range-corners-must-be-ordered", 3, {rf: [corners]}, P["corners"]),
        Bug("power-domain-escapes", 2, {ev: [power_domain]}, P["power-domain"]),
        Bug("if-evaluates-both-branches", 3, {ev: [if_both]}, P["if-both"]),
        Bug("empties-count-as-zero-in-ranges", 3, {ev: [empties]}, P["empties-zero"]),
        Bug("average-divides-by-the-range-size", 3, {ev: avg}, P["avg"]),
        Bug("show-prints-the-raw-float", 2, {sh: [show]}, P["show"], reported=REPORTED_DISPLAY),
        Bug("only-direct-readers-are-updated", 3, {gr: [transitive]}, P["transitive"]),
        Bug("only-self-loops-are-cycles", 3, {gr: [loops]}, P["cycles"]),
        Bug("recalc-in-cell-name-order", 4, {gr: [order]}, P["order"]),
        Bug("replaced-formulas-keep-their-readers", 4, {sh: [stale]}, P["stale"]),
        Bug("range-middle-cells-not-tracked", 3, {gr: [range_middle]}, P["range-middle"]),
    ]
    base = Base("sheetcalc", "python", good, VISIBLE, HIDDEN, bugs)
    extra = [
        combo(base, ["power-associates-left", "comparison-as-tight-as-plus", "lowercase-references-read-nothing", "leading-dot-numbers-rejected"], 4,
              "formula-language-review", "Review of the formula language against the README found four problems in the tokenizer and the parser:"),
        combo(base, ["power-domain-escapes", "if-evaluates-both-branches", "empties-count-as-zero-in-ranges"], 4,
              "error-values-review", "Three reports about error handling and blanks in the evaluator, collected by QA:"),
        combo(base, ["lowercase-references-read-nothing", "range-corners-must-be-ordered"], 4,
              "typing-and-selecting", "Two reports from the same user study session:"),
        combo(base, ["recalc-in-cell-name-order", "replaced-formulas-keep-their-readers", "range-middle-cells-not-tracked"], 5,
              "incremental-recalc-review", "Recalculation review. These three symptoms were reported separately but all concern what is recomputed after an edit:"),
        combo(base, ["only-self-loops-are-cycles", "only-direct-readers-are-updated", "replaced-formulas-keep-their-readers"], 5,
              "cycles-and-stale-edges", "Support tickets about circular references and stale cells, filed within one week:"),
    ]
    base.bugs.extend(extra)
    return base


@family("fix-hand-sheet-calc", category="fix", lang="python", kind="fix", n=22,
        summary="a layered python spreadsheet engine (tokenizer, parser, evaluator, ranges, dependency graph, recalculation) with cross-module defects")
def gen(rng, n):
    return tasks_from([_base()])
