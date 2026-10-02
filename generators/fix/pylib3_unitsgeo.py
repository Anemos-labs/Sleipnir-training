"""Units, geometry and music in domain clothes (python, fix-py-3): guild units, no-fly polygons, chord symbols."""
from fx import Lib, dd

from generators.fix._pylib3 import chain, register_libs3

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# guildunits: quantities with dimension checking in an invented unit system (multi-module)
# ======================================================================================================================

GUILDUNITS_README = dd('''
    # guildunits

    Quantities with units for a trade guild's ledger. Besides the usual metric units the guild still uses its own
    traditional ones. All arithmetic is exact (`fractions.Fraction`).

    There are three base dimensions, always written in this order: `L` (length), `M` (mass) and `T` (time). A
    dimension is a tuple of three integer exponents `(l, m, t)`; `DIMLESS = (0, 0, 0)`.

    ## `guildunits.dims`

    * `dim_mul(a, b)`, `dim_div(a, b)`: add or subtract the exponents. `dim_pow(a, n)`: multiply them by the integer `n`.
    * `dim_name(d) -> str`: positive exponents form the numerator (`L`, `M`, `T` in that order, joined by `*`; an
      exponent other than 1 is written `L^2`), negative exponents the denominator. An empty numerator is `1`. A
      denominator with several terms is put in parentheses: `(1, 1, -2)` is `"L*M/T^2"`, `(0, 0, -1)` is `"1/T"`,
      `(1, -1, -2)` is `"L/(M*T^2)"`, `(0, 0, 0)` is `"1"`, `(2, 0, 0)` is `"L^2"`.

    ## `guildunits.units`

    `UnknownUnit` is a `ValueError`. `lookup(name) -> (factor, dim)` gives the size of a unit in the base units metre,
    kilogram and second (`factor` is a `Fraction`). Known names:

    * guild units: `span` = 9/50 m, `pace` = 3/4 m, `league` = 3600 m, `stone` = 6 kg, `quintal` = 100 kg,
      `tick` = 3 s, `watch` = 14400 s, `plot` = 400 m^2, `push` = 1 kg*m/s^2;
    * base units: `m`, `g` (= 1/1000 kg), `s`;
    * a base unit with one metric prefix: `k` (1000), `c` (1/100) or `m` (1/1000), e.g. `km`, `cm`, `mm`, `kg`,
      `mg`, `ms`. A name that is itself a known unit is never read as a prefix (`m` is the metre, `mm` the
      millimetre). Guild units take no prefix, names are case-sensitive, and anything else raises `UnknownUnit`.

    ## `guildunits.parser`

    `UnitSyntaxError` is a `ValueError`.

    * `parse_unit(expr) -> (factor, dim)`: a unit expression is terms joined by `*` and `/` (spaces around the
      operators are allowed). A term is a unit name, optionally followed by `^` and an integer exponent without
      spaces (`m^2`, `s^-1`). Operators are applied strictly left to right and a `/` divides by the one term
      after it only: `kg/m*s` means `(kg/m)*s`. An empty or blank expression is dimensionless `(1, DIMLESS)`.
      Malformed expressions (an empty term, a bad exponent, a term that is not a name with an optional exponent)
      raise `UnitSyntaxError`; unknown names raise `UnknownUnit`.
    * `split_quantity(text) -> (Fraction, str)`: split `"12.5 span/tick"` into the number and the unit text. The number
      is an optional sign and digits with an optional fractional part (`12`, `-0.5`, `+3`); spaces between the number
      and the unit are optional. `UnitSyntaxError` if the text does not start with such a number.

    ## `guildunits.quantity`

    `DimensionError` is a `ValueError`. `Quantity(base, dim=DIMLESS)` stores `base`, the value in base units, as a
    `Fraction`, and `dim`.

    * `parse_quantity(text) -> Quantity` and `convert(text, unit_expr) -> Fraction` (`parse_quantity(text).to(unit)`).
    * `q.to(unit_expr) -> Fraction`: the value in that unit; `DimensionError` (message
      `cannot convert L to M`, using `dim_name`) when the dimensions differ.
    * `+` and `-` need equal dimensions (`DimensionError`: `cannot add L and T` / `cannot subtract ...`).
      `*` and `/` accept a `Quantity` (dimensions multiply or divide; dividing by a zero quantity raises
      `ZeroDivisionError`) or a plain number (`3 * q` works too). `q ** n` for an integer `n`. Unary `-`.
    * `==` compares base value and dimension (different dimensions are simply unequal, equal quantities hash alike).
      `<` needs equal dimensions (`DimensionError`: `cannot compare ...`).
    * `q.format(unit_expr, places=2) -> str`: the value in the unit with exactly `places` decimals, rounded half away
      from zero (no decimal point when `places` is 0, no minus sign for a result that rounds to zero), then a space and
      the unit expression as given (stripped); for an empty unit expression just the number.
''')

GUILDUNITS_DIMS = dd('''
    """Dimension algebra over (length, mass, time) exponents."""

    NAMES = ("L", "M", "T")
    DIMLESS = (0, 0, 0)


    def dim_mul(a, b):
        return tuple(x + y for x, y in zip(a, b))


    def dim_div(a, b):
        return tuple(x - y for x, y in zip(a, b))


    def dim_pow(a, n):
        return tuple(x * n for x in a)


    def _term(name, exp):
        return name if exp == 1 else f"{name}^{exp}"


    def dim_name(d):
        top = [_term(n, e) for n, e in zip(NAMES, d) if e > 0]
        bottom = [_term(n, -e) for n, e in zip(NAMES, d) if e < 0]
        text = "*".join(top) or "1"
        if not bottom:
            return text
        den = bottom[0] if len(bottom) == 1 else "(" + "*".join(bottom) + ")"
        return f"{text}/{den}"
''')

GUILDUNITS_UNITS = dd('''
    """The unit table."""
    from fractions import Fraction as F


    class UnknownUnit(ValueError):
        pass


    BASE = {
        "m": (F(1), (1, 0, 0)),
        "g": (F(1, 1000), (0, 1, 0)),
        "s": (F(1), (0, 0, 1)),
    }
    PREFIXES = {"k": F(1000), "c": F(1, 100), "m": F(1, 1000)}
    GUILD = {
        "span": (F(9, 50), (1, 0, 0)),
        "pace": (F(3, 4), (1, 0, 0)),
        "league": (F(3600), (1, 0, 0)),
        "stone": (F(6), (0, 1, 0)),
        "quintal": (F(100), (0, 1, 0)),
        "tick": (F(3), (0, 0, 1)),
        "watch": (F(14400), (0, 0, 1)),
        "plot": (F(400), (2, 0, 0)),
        "push": (F(1), (1, 1, -2)),
    }


    def lookup(name):
        if name in GUILD:
            return GUILD[name]
        if name in BASE:
            return BASE[name]
        if len(name) > 1 and name[0] in PREFIXES and name[1:] in BASE:
            factor, dim = BASE[name[1:]]
            return PREFIXES[name[0]] * factor, dim
        raise UnknownUnit(name)
''')

GUILDUNITS_PARSER = dd('''
    """Parsing unit expressions and quantity text."""
    import re
    from fractions import Fraction

    from .dims import DIMLESS, dim_div, dim_mul, dim_pow
    from .units import lookup


    class UnitSyntaxError(ValueError):
        pass


    _TERM = re.compile(r"^([A-Za-z]+)(?:\\^(-?\\d+))?$")
    _NUMBER = re.compile(r"^\\s*([+-]?\\d+(?:\\.\\d+)?)\\s*(.*)$", re.S)


    def parse_unit(expr):
        expr = expr.strip()
        if not expr:
            return Fraction(1), DIMLESS
        parts = re.split(r"\\s*([*/])\\s*", expr)
        items = [("*", parts[0])] + [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]
        factor, dim = Fraction(1), DIMLESS
        for op, term in items:
            m = _TERM.match(term)
            if not m:
                raise UnitSyntaxError(f"bad unit term {term!r}")
            f, d = lookup(m.group(1))
            n = int(m.group(2)) if m.group(2) else 1
            f, d = f ** n, dim_pow(d, n)
            if op == "*":
                factor, dim = factor * f, dim_mul(dim, d)
            else:
                factor, dim = factor / f, dim_div(dim, d)
        return factor, dim


    def split_quantity(text):
        m = _NUMBER.match(text)
        if not m:
            raise UnitSyntaxError(f"no number at the start of {text!r}")
        return Fraction(m.group(1)), m.group(2)
''')

GUILDUNITS_QUANTITY = dd('''
    """Quantities."""
    from fractions import Fraction

    from .dims import DIMLESS, dim_div, dim_mul, dim_name, dim_pow
    from .parser import parse_unit, split_quantity


    class DimensionError(ValueError):
        pass


    def _fixed(value, places):
        scale = 10 ** places
        scaled = abs(value) * scale
        whole = int(scaled)
        if scaled - whole >= Fraction(1, 2):
            whole += 1
        sign = "-" if value < 0 and whole else ""
        if places == 0:
            return f"{sign}{whole}"
        return f"{sign}{whole // scale}.{whole % scale:0{places}d}"


    class Quantity:
        def __init__(self, base, dim=DIMLESS):
            self.base = Fraction(base)
            self.dim = tuple(dim)

        def _same(self, other, what):
            if self.dim != other.dim:
                raise DimensionError(f"cannot {what} {dim_name(self.dim)} and {dim_name(other.dim)}")

        def __add__(self, other):
            self._same(other, "add")
            return Quantity(self.base + other.base, self.dim)

        def __sub__(self, other):
            self._same(other, "subtract")
            return Quantity(self.base - other.base, self.dim)

        def __neg__(self):
            return Quantity(-self.base, self.dim)

        def __mul__(self, other):
            if isinstance(other, Quantity):
                return Quantity(self.base * other.base, dim_mul(self.dim, other.dim))
            return Quantity(self.base * other, self.dim)

        __rmul__ = __mul__

        def __truediv__(self, other):
            if isinstance(other, Quantity):
                return Quantity(self.base / other.base, dim_div(self.dim, other.dim))
            return Quantity(self.base / other, self.dim)

        def __pow__(self, n):
            return Quantity(self.base ** n, dim_pow(self.dim, n))

        def __eq__(self, other):
            return isinstance(other, Quantity) and self.base == other.base and self.dim == other.dim

        def __hash__(self):
            return hash((self.base, self.dim))

        def __lt__(self, other):
            self._same(other, "compare")
            return self.base < other.base

        def to(self, unit_expr):
            factor, dim = parse_unit(unit_expr)
            if dim != self.dim:
                raise DimensionError(f"cannot convert {dim_name(self.dim)} to {dim_name(dim)}")
            return self.base / factor

        def format(self, unit_expr, places=2):
            text = _fixed(self.to(unit_expr), places)
            return f"{text} {unit_expr.strip()}".strip()


    def parse_quantity(text):
        value, unit = split_quantity(text)
        factor, dim = parse_unit(unit)
        return Quantity(value * factor, dim)


    def convert(text, unit_expr):
        return parse_quantity(text).to(unit_expr)
''')

GUILDUNITS_VISIBLE = dd('''
    import unittest
    from fractions import Fraction as F

    from guildunits.dims import dim_name
    from guildunits.quantity import convert


    class BasicTests(unittest.TestCase):
        def test_names(self):
            self.assertEqual(dim_name((1, 1, -2)), "L*M/T^2")

        def test_convert(self):
            self.assertEqual(convert("1 league", "km"), F(18, 5))


    if __name__ == "__main__":
        unittest.main()
''')

GUILDUNITS_HIDDEN_DIMS = dd('''
    import unittest
    from fractions import Fraction as F

    from guildunits.dims import DIMLESS, dim_div, dim_mul, dim_name, dim_pow
    from guildunits.units import UnknownUnit, lookup


    class DimAlgebra(unittest.TestCase):
        def test_ops(self):
            self.assertEqual(dim_mul((1, 0, 0), (0, 1, -2)), (1, 1, -2))
            self.assertEqual(dim_div((1, 1, 0), (0, 0, 2)), (1, 1, -2))
            self.assertEqual(dim_div((2, 0, 0), (2, 0, 0)), DIMLESS)
            self.assertEqual(dim_pow((1, -1, 2), 3), (3, -3, 6))
            self.assertEqual(dim_pow((1, -1, 2), -1), (-1, 1, -2))
            self.assertEqual(dim_pow((1, 5, 2), 0), (0, 0, 0))
            self.assertEqual(DIMLESS, (0, 0, 0))

        def test_ops_return_tuples(self):
            self.assertIsInstance(dim_mul((1, 0, 0), (1, 0, 0)), tuple)
            self.assertIsInstance(dim_pow((1, 0, 0), 2), tuple)

        def test_names(self):
            table = {
                (0, 0, 0): "1", (1, 0, 0): "L", (0, 1, 0): "M", (0, 0, 1): "T", (2, 0, 0): "L^2", (3, 0, 0): "L^3",
                (1, 1, -2): "L*M/T^2", (0, 0, -1): "1/T", (0, 0, -2): "1/T^2", (-1, 0, 0): "1/L", (1, 0, -1): "L/T",
                (2, 0, -1): "L^2/T", (1, -1, -2): "L/(M*T^2)", (0, -1, -1): "1/(M*T)", (-2, -1, 0): "1/(L^2*M)",
                (2, 1, 1): "L^2*M*T", (1, 2, 0): "L*M^2", (-1, -1, -1): "1/(L*M*T)", (0, 1, -3): "M/T^3",
            }
            for d, want in table.items():
                self.assertEqual(dim_name(d), want, d)


    class Lookup(unittest.TestCase):
        def test_base_and_prefixed(self):
            self.assertEqual(lookup("m"), (F(1), (1, 0, 0)))
            self.assertEqual(lookup("s"), (F(1), (0, 0, 1)))
            self.assertEqual(lookup("g"), (F(1, 1000), (0, 1, 0)))
            self.assertEqual(lookup("kg"), (F(1), (0, 1, 0)))
            self.assertEqual(lookup("km"), (F(1000), (1, 0, 0)))
            self.assertEqual(lookup("cm"), (F(1, 100), (1, 0, 0)))
            self.assertEqual(lookup("mm"), (F(1, 1000), (1, 0, 0)))
            self.assertEqual(lookup("mg"), (F(1, 1000000), (0, 1, 0)))
            self.assertEqual(lookup("ms"), (F(1, 1000), (0, 0, 1)))
            self.assertEqual(lookup("ks"), (F(1000), (0, 0, 1)))
            self.assertEqual(lookup("cg"), (F(1, 100000), (0, 1, 0)))

        def test_guild_units(self):
            table = {
                "span": (F(9, 50), (1, 0, 0)), "pace": (F(3, 4), (1, 0, 0)), "league": (F(3600), (1, 0, 0)),
                "stone": (F(6), (0, 1, 0)), "quintal": (F(100), (0, 1, 0)), "tick": (F(3), (0, 0, 1)),
                "watch": (F(14400), (0, 0, 1)), "plot": (F(400), (2, 0, 0)), "push": (F(1), (1, 1, -2)),
            }
            for name, want in table.items():
                self.assertEqual(lookup(name), want, name)

        def test_unknown(self):
            for name in ("", "k", "x", "M", "S", "kspan", "mmm", "kkg", "km2", "Km", "spans", "mspan", "gg", "c", "min"):
                with self.assertRaises(UnknownUnit, msg=name):
                    lookup(name)
            self.assertTrue(issubclass(UnknownUnit, ValueError))


    if __name__ == "__main__":
        unittest.main()
''')

GUILDUNITS_HIDDEN_PARSER = dd('''
    import unittest
    from fractions import Fraction as F

    from guildunits.dims import DIMLESS
    from guildunits.parser import UnitSyntaxError, parse_unit, split_quantity
    from guildunits.units import UnknownUnit


    class ParseUnit(unittest.TestCase):
        def test_simple(self):
            self.assertEqual(parse_unit("m"), (F(1), (1, 0, 0)))
            self.assertEqual(parse_unit("span"), (F(9, 50), (1, 0, 0)))
            self.assertEqual(parse_unit("plot"), (F(400), (2, 0, 0)))
            self.assertEqual(parse_unit("kg"), (F(1), (0, 1, 0)))

        def test_dimensionless(self):
            for text in ("", "   ", "\\t"):
                self.assertEqual(parse_unit(text), (F(1), DIMLESS))

        def test_exponents(self):
            self.assertEqual(parse_unit("m^2"), (F(1), (2, 0, 0)))
            self.assertEqual(parse_unit("s^-1"), (F(1), (0, 0, -1)))
            self.assertEqual(parse_unit("span^2"), (F(81, 2500), (2, 0, 0)))
            self.assertEqual(parse_unit("span^-1"), (F(50, 9), (-1, 0, 0)))
            self.assertEqual(parse_unit("km^3"), (F(10 ** 9), (3, 0, 0)))
            self.assertEqual(parse_unit("m^1"), (F(1), (1, 0, 0)))
            self.assertEqual(parse_unit("m^0"), (F(1), DIMLESS))
            self.assertEqual(parse_unit("cm^2"), (F(1, 10000), (2, 0, 0)))

        def test_products_and_quotients(self):
            self.assertEqual(parse_unit("kg*m/s^2"), (F(1), (1, 1, -2)))
            self.assertEqual(parse_unit("span/tick"), (F(3, 50), (1, 0, -1)))
            self.assertEqual(parse_unit("km/watch"), (F(5, 72), (1, 0, -1)))
            self.assertEqual(parse_unit("m*m"), (F(1), (2, 0, 0)))
            self.assertEqual(parse_unit("pace*stone"), (F(9, 2), (1, 1, 0)))
            self.assertEqual(parse_unit("stone/plot"), (F(3, 200), (-2, 1, 0)))

        def test_left_to_right(self):
            self.assertEqual(parse_unit("m/s/s"), (F(1), (1, 0, -2)))
            self.assertEqual(parse_unit("kg/m*s"), (F(1), (-1, 1, 1)))
            self.assertEqual(parse_unit("kg*m/s*s"), (F(1), (1, 1, 0)))
            self.assertEqual(parse_unit("tick/span*span"), (F(3), (0, 0, 1)))

        def test_spaces(self):
            self.assertEqual(parse_unit("  kg * m / s^2 "), (F(1), (1, 1, -2)))
            self.assertEqual(parse_unit("span / tick"), (F(3, 50), (1, 0, -1)))

        def test_syntax_errors(self):
            for text in ("*m", "m*", "/m", "m/", "m**s", "m//s", "m^", "m^x", "m ^2", "m^ 2", "2m", "m^2.5", "m s", "(m)", "m^--1", "m*/s"):
                with self.assertRaises(UnitSyntaxError, msg=text):
                    parse_unit(text)
            self.assertTrue(issubclass(UnitSyntaxError, ValueError))

        def test_unknown_names(self):
            for text in ("foo", "m/foo", "kspan", "M"):
                with self.assertRaises(UnknownUnit, msg=text):
                    parse_unit(text)


    class SplitQuantity(unittest.TestCase):
        def test_numbers(self):
            self.assertEqual(split_quantity("12 span"), (F(12), "span"))
            self.assertEqual(split_quantity("12.5 span/tick"), (F(25, 2), "span/tick"))
            self.assertEqual(split_quantity("-0.5 m"), (F(-1, 2), "m"))
            self.assertEqual(split_quantity("+3 m"), (F(3), "m"))
            self.assertEqual(split_quantity("7"), (F(7), ""))
            self.assertEqual(split_quantity("  7  "), (F(7), ""))
            self.assertEqual(split_quantity("3m"), (F(3), "m"))
            self.assertEqual(split_quantity("0.25kg*m"), (F(1, 4), "kg*m"))
            self.assertEqual(split_quantity("100   cm"), (F(100), "cm"))
            self.assertEqual(split_quantity("007 s"), (F(7), "s"))

        def test_bad_numbers(self):
            for text in ("", "span", "m 12", ".5 m", "- 3 m", "--3 m", "x", "abc 3"):
                with self.assertRaises(UnitSyntaxError, msg=text):
                    split_quantity(text)


    if __name__ == "__main__":
        unittest.main()
''')

GUILDUNITS_HIDDEN_QUANTITY = dd('''
    import unittest
    from fractions import Fraction as F

    from guildunits.dims import DIMLESS
    from guildunits.parser import UnitSyntaxError
    from guildunits.quantity import DimensionError, Quantity, convert, parse_quantity
    from guildunits.units import UnknownUnit

    Q = parse_quantity


    class Parsing(unittest.TestCase):
        def test_base_values(self):
            self.assertEqual(Q("12 span").base, F(54, 25))
            self.assertEqual(Q("12 span").dim, (1, 0, 0))
            self.assertEqual(Q("12.5 span/tick").base, F(3, 4))
            self.assertEqual(Q("12.5 span/tick").dim, (1, 0, -1))
            self.assertEqual(Q("3 stone").base, 18)
            self.assertEqual(Q("-2 km").base, -2000)
            self.assertEqual(Q("5").dim, DIMLESS)
            self.assertEqual(Q("5").base, 5)

        def test_errors(self):
            with self.assertRaises(UnitSyntaxError):
                Q("span")
            with self.assertRaises(UnknownUnit):
                Q("3 parsec")

        def test_constructor_defaults(self):
            q = Quantity(3)
            self.assertEqual((q.base, q.dim), (F(3), DIMLESS))
            self.assertIsInstance(Quantity(0.5).base, F)
            self.assertEqual(Quantity(1, [1, 0, 0]).dim, (1, 0, 0))


    class Conversion(unittest.TestCase):
        def test_convert(self):
            self.assertEqual(convert("12 span", "m"), F(54, 25))
            self.assertEqual(convert("1 league", "km"), F(18, 5))
            self.assertEqual(convert("1 league", "pace"), 4800)
            self.assertEqual(convert("3 stone", "kg"), 18)
            self.assertEqual(convert("1 quintal", "stone"), F(50, 3))
            self.assertEqual(convert("2 watch", "tick"), 9600)
            self.assertEqual(convert("1 watch", "s"), 14400)
            self.assertEqual(convert("250 mm", "cm"), 25)
            self.assertEqual(convert("2 plot", "m^2"), 800)
            self.assertEqual(convert("1 km^2", "plot"), 2500)
            self.assertEqual(convert("36 km/watch", "m/s"), F(5, 2))
            self.assertEqual(convert("1 push", "kg*m/s^2"), 1)
            self.assertEqual(convert("1 push", "g*cm/s^2"), 100000)
            self.assertEqual(convert("5", ""), 5)

        def test_dimension_mismatch(self):
            with self.assertRaises(DimensionError) as cm:
                convert("5 m", "kg")
            self.assertEqual(str(cm.exception), "cannot convert L to M")
            with self.assertRaises(DimensionError) as cm:
                convert("5 span/tick", "stone")
            self.assertEqual(str(cm.exception), "cannot convert L/T to M")
            with self.assertRaises(DimensionError) as cm:
                convert("5 push", "m")
            self.assertEqual(str(cm.exception), "cannot convert L*M/T^2 to L")
            with self.assertRaises(DimensionError):
                convert("5 m", "")
            self.assertTrue(issubclass(DimensionError, ValueError))

        def test_same_dimension_different_shape(self):
            self.assertEqual(convert("4 m^2", "m*m"), 4)
            self.assertEqual(convert("4 m/s", "s^-1*m"), 4)


    class Arithmetic(unittest.TestCase):
        def test_add_sub(self):
            self.assertEqual((Q("3 m") + Q("2 span")).base, F(84, 25))
            self.assertEqual((Q("3 m") - Q("2 span")).base, F(66, 25))
            self.assertEqual(Q("1 m") + Q("100 cm"), Q("2 m"))
            self.assertEqual((Q("3 m") + Q("2 span")).dim, (1, 0, 0))

        def test_add_sub_errors(self):
            with self.assertRaises(DimensionError) as cm:
                Q("3 m") + Q("2 s")
            self.assertEqual(str(cm.exception), "cannot add L and T")
            with self.assertRaises(DimensionError) as cm:
                Q("3 m") - Q("2 kg")
            self.assertEqual(str(cm.exception), "cannot subtract L and M")
            with self.assertRaises(DimensionError):
                Q("3") + Q("2 m")

        def test_neg(self):
            self.assertEqual((-Q("3 m")).base, -3)
            self.assertEqual((-Q("3 m")).dim, (1, 0, 0))

        def test_mul_div_quantities(self):
            area = Q("3 m") * Q("2 m")
            self.assertEqual((area.base, area.dim), (6, (2, 0, 0)))
            self.assertEqual(area, Q("6 m^2"))
            speed = Q("10 m") / Q("2 s")
            self.assertEqual((speed.base, speed.dim), (5, (1, 0, -1)))
            self.assertEqual(Q("6 m^2") / Q("3 m"), Q("2 m"))
            inv = Q("1 m") / Q("1 span")
            self.assertEqual((inv.base, inv.dim), (F(50, 9), DIMLESS))
            ratio = Q("9 span") / Q("2 m")
            self.assertEqual((ratio.base, ratio.dim), (F(81, 100), DIMLESS))

        def test_mul_div_numbers(self):
            self.assertEqual((Q("3 m") * 4).base, 12)
            self.assertEqual((4 * Q("3 m")).base, 12)
            self.assertEqual((Q("3 m") * F(1, 2)).base, F(3, 2))
            self.assertEqual((Q("3 m") / 4).base, F(3, 4))
            self.assertEqual((Q("3 m") * 4).dim, (1, 0, 0))
            self.assertEqual((Q("3 m") / 4).dim, (1, 0, 0))

        def test_division_by_zero(self):
            with self.assertRaises(ZeroDivisionError):
                Q("3 m") / Q("0 s")

        def test_power(self):
            sq = Q("3 m") ** 2
            self.assertEqual((sq.base, sq.dim), (9, (2, 0, 0)))
            inv = Q("2 s") ** -1
            self.assertEqual((inv.base, inv.dim), (F(1, 2), (0, 0, -1)))
            zero = Q("5 kg") ** 0
            self.assertEqual((zero.base, zero.dim), (1, DIMLESS))
            cube = Q("2 span") ** 3
            self.assertEqual((cube.base, cube.dim), (F(729, 15625), (3, 0, 0)))

        def test_equality_and_order(self):
            self.assertEqual(Q("100 cm"), Q("1 m"))
            self.assertNotEqual(Q("1 m"), Q("1 s"))
            self.assertNotEqual(Q("1 m"), Q("2 m"))
            self.assertNotEqual(Q("1 m"), 1)
            self.assertEqual(hash(Q("100 cm")), hash(Q("1 m")))
            self.assertLess(Q("1 m"), Q("2 m"))
            self.assertFalse(Q("2 m") < Q("1 m"))
            self.assertFalse(Q("2 m") < Q("2 m"))
            self.assertLess(Q("1 span"), Q("1 pace"))
            with self.assertRaises(DimensionError) as cm:
                Q("1 m") < Q("1 s")
            self.assertEqual(str(cm.exception), "cannot compare L and T")


    class Format(unittest.TestCase):
        def test_format(self):
            self.assertEqual(Q("12 span").format("m", 3), "2.160 m")
            self.assertEqual(Q("12 span").format("span"), "12.00 span")
            self.assertEqual(Q("12 span").format("cm", 0), "216 cm")
            self.assertEqual(Q("1 m").format("pace", 2), "1.33 pace")
            self.assertEqual(Q("2 m").format("pace", 2), "2.67 pace")
            self.assertEqual(Q("-1 m").format("span", 1), "-5.6 span")
            self.assertEqual(Q("1 m").format("km", 4), "0.0010 km")
            self.assertEqual(Q("3").format("", 1), "3.0")
            self.assertEqual(Q("3").format("  "), "3.00")
            self.assertEqual(Q("5 m").format("  m  ", 1), "5.0 m")

        def test_rounding_half_away_from_zero(self):
            self.assertEqual(Q("1 m").format("m", 0), "1 m")
            self.assertEqual(Q("5 mm").format("cm", 0), "1 cm")
            self.assertEqual(Q("-5 mm").format("cm", 0), "-1 cm")
            self.assertEqual(Q("4 mm").format("cm", 0), "0 cm")
            self.assertEqual(Q("-4 mm").format("cm", 0), "0 cm")
            self.assertEqual(Q("125 mm").format("m", 2), "0.13 m")
            self.assertEqual(Q("-125 mm").format("m", 2), "-0.13 m")
            self.assertEqual(Q("124 mm").format("m", 2), "0.12 m")
            self.assertEqual(Q("1 mm").format("m", 2), "0.00 m")
            self.assertEqual(Q("-1 mm").format("m", 2), "0.00 m")

        def test_format_dimension_error(self):
            with self.assertRaises(DimensionError):
                Q("1 m").format("kg")


    if __name__ == "__main__":
        unittest.main()
''')

GUILDUNITS = Lib(
    name="guildunits", lang="python", title="the guildunits quantity package",
    blurb="The guild's ledger tool uses guildunits to read quantities such as '12 span/tick' and convert them between traditional and metric units.",
    files={
        "guildunits/__init__.py": "", "guildunits/dims.py": GUILDUNITS_DIMS, "guildunits/units.py": GUILDUNITS_UNITS,
        "guildunits/parser.py": GUILDUNITS_PARSER, "guildunits/quantity.py": GUILDUNITS_QUANTITY,
        "README.md": GUILDUNITS_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": GUILDUNITS_VISIBLE},
    hidden_tests={
        "tests/test_dims.py": GUILDUNITS_HIDDEN_DIMS, "tests/test_parser.py": GUILDUNITS_HIDDEN_PARSER,
        "tests/test_quantity.py": GUILDUNITS_HIDDEN_QUANTITY,
    },
    mutate=["guildunits/dims.py", "guildunits/units.py", "guildunits/parser.py", "guildunits/quantity.py"],
    difficulty=4, tags=["units", "dimensions", "multi-module"],
    probes=[
        "dim_name((1, -1, -2))", "dim_name((0, 0, -1))", "dim_name((2, 1, 1))",
        "lookup('mg')", "lookup('km')",
        "parse_unit('kg/m*s')", "parse_unit('span^-1')", "parse_unit('km/watch')", "parse_unit('m/s/s')",
        "split_quantity('-0.5 m')", "split_quantity('3m')",
        "convert('1 league', 'pace')", "convert('1 quintal', 'stone')", "convert('1 km^2', 'plot')",
        "convert('36 km/watch', 'm/s')", "convert('1 push', 'g*cm/s^2')",
        "(parse_quantity('3 m') + parse_quantity('2 span')).base",
        "(parse_quantity('3 m') * parse_quantity('2 m')).dim",
        "(parse_quantity('2 s') ** -1).base",
        "parse_quantity('12 span').format('m', 3)", "parse_quantity('-1 m').format('span', 1)", "parse_quantity('-4 mm').format('cm', 0)",
        "parse_quantity('5 m').to('kg')", "parse_quantity('3 m') + parse_quantity('2 s')",
    ],
    probe_import=(
        "from guildunits.dims import dim_name\nfrom guildunits.units import lookup\n"
        "from guildunits.parser import parse_unit, split_quantity\nfrom guildunits.quantity import parse_quantity, convert\n"
    ),
)

# ======================================================================================================================
# airlane: exact geometry for drone no-fly polygons (multi-module)
# ======================================================================================================================

AIRLANE_README = dd('''
    # airlane

    Exact planar geometry on integer points, used by a drone operator to check flight routes against no-fly polygons.
    A point is an `(x, y)` tuple of integers; a polygon is a list of points (its vertices in order, the last one is
    joined to the first). Results that need fractions are `fractions.Fraction`s.

    ## `airlane.geom`

    * `cross(o, a, b)`: the cross product `(a - o) x (b - o)`; positive when `o -> a -> b` turns counter-clockwise.
    * `area2(poly) -> int`: twice the signed area (shoelace formula): positive for counter-clockwise, negative for
      clockwise. `area(poly) -> Fraction`: the (unsigned) area. `orientation(poly) -> str`: `"ccw"`, `"cw"` or
      `"degenerate"` (zero area).
    * `on_segment(p, a, b) -> bool`: `p` lies on the closed segment `ab` (end points included).
    * `contains(poly, p, boundary=True) -> bool`: is `p` inside the polygon? A point on the boundary (an edge or a
      vertex) gives the value of `boundary`. Any simple polygon, convex or not. `ValueError` for fewer than 3 vertices.
    * `centroid(poly) -> (Fraction, Fraction)`: the centre of area of a simple polygon, either orientation.
      `ValueError` for fewer than 3 vertices or zero area.
    * `clip_segment(a, b, rect) -> ((x, y), (x, y)) | None`: the part of the segment `ab` inside the closed rectangle
      `rect = (xmin, ymin, xmax, ymax)` (`ValueError` unless `xmin <= xmax` and `ymin <= ymax`), as two points of
      `Fraction`s in the direction `a -> b`; `None` if no point of the segment lies in the rectangle. A segment that
      only touches the rectangle in one point gives that point twice.

    ## `airlane.fence`

    * `segments_intersect(a, b, c, d) -> bool`: the closed segments `ab` and `cd` have at least one point in common
      (touching, an end point on the other segment and collinear overlaps all count).
    * `leg_hits(poly, a, b) -> bool`: the flight leg `ab` touches the polygon: an end point is inside or on its
      boundary, or the leg meets one of its edges.
    * `leg_violations(polys, route) -> list[(leg, poly)]`: for a route (a list of waypoints) every pair of a leg index
      `i` (the leg from `route[i]` to `route[i + 1]`) and a polygon index `j` such that the leg hits the polygon,
      ordered by leg and then by polygon. A route with fewer than 2 waypoints has no legs.
    * `first_violation(polys, route)`: the first pair of `leg_violations`, or `None`; `route_clear(polys, route)`:
      there is no violation.
    * `crop_route(route, rect) -> list`: the `clip_segment` result of every leg that has one, in route order.
''')

AIRLANE_GEOM = dd('''
    """Exact planar geometry on integer points."""
    from fractions import Fraction


    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


    def area2(poly):
        total = 0
        for i, (x1, y1) in enumerate(poly):
            x2, y2 = poly[(i + 1) % len(poly)]
            total += x1 * y2 - x2 * y1
        return total


    def area(poly):
        return Fraction(abs(area2(poly)), 2)


    def orientation(poly):
        a2 = area2(poly)
        if a2 > 0:
            return "ccw"
        if a2 < 0:
            return "cw"
        return "degenerate"


    def on_segment(p, a, b):
        if cross(a, b, p) != 0:
            return False
        return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


    def _check(poly):
        if len(poly) < 3:
            raise ValueError("a polygon needs at least 3 vertices")


    def contains(poly, p, boundary=True):
        _check(poly)
        inside = False
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            if on_segment(p, a, b):
                return boundary
            if (a[1] > p[1]) != (b[1] > p[1]):
                num = (p[1] - a[1]) * (b[0] - a[0]) + (a[0] - p[0]) * (b[1] - a[1])
                if (num > 0) == (b[1] - a[1] > 0):
                    inside = not inside
        return inside


    def centroid(poly):
        _check(poly)
        a2 = area2(poly)
        if a2 == 0:
            raise ValueError("degenerate polygon")
        cx = cy = 0
        for i, (x1, y1) in enumerate(poly):
            x2, y2 = poly[(i + 1) % len(poly)]
            w = x1 * y2 - x2 * y1
            cx += (x1 + x2) * w
            cy += (y1 + y2) * w
        return Fraction(cx, 3 * a2), Fraction(cy, 3 * a2)


    def clip_segment(a, b, rect):
        xmin, ymin, xmax, ymax = rect
        if xmin > xmax or ymin > ymax:
            raise ValueError("empty rectangle")
        (x0, y0), (x1, y1) = a, b
        dx, dy = x1 - x0, y1 - y0
        t0, t1 = Fraction(0), Fraction(1)
        for p, q in ((-dx, x0 - xmin), (dx, xmax - x0), (-dy, y0 - ymin), (dy, ymax - y0)):
            if p == 0:
                if q < 0:
                    return None
                continue
            r = Fraction(q, p)
            if p < 0:
                if r > t1:
                    return None
                t0 = max(t0, r)
            else:
                if r < t0:
                    return None
                t1 = min(t1, r)
        return (x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy)
''')

AIRLANE_FENCE = dd('''
    """Flight legs against no-fly polygons."""
    from .geom import clip_segment, contains, cross, on_segment


    def segments_intersect(a, b, c, d):
        d1, d2 = cross(a, b, c), cross(a, b, d)
        d3, d4 = cross(c, d, a), cross(c, d, b)
        if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
            return True
        return on_segment(c, a, b) or on_segment(d, a, b) or on_segment(a, c, d) or on_segment(b, c, d)


    def leg_hits(poly, a, b):
        if contains(poly, a) or contains(poly, b):
            return True
        n = len(poly)
        return any(segments_intersect(a, b, poly[i], poly[(i + 1) % n]) for i in range(n))


    def leg_violations(polys, route):
        found = []
        for i in range(len(route) - 1):
            for j, poly in enumerate(polys):
                if leg_hits(poly, route[i], route[i + 1]):
                    found.append((i, j))
        return found


    def first_violation(polys, route):
        found = leg_violations(polys, route)
        return found[0] if found else None


    def route_clear(polys, route):
        return not leg_violations(polys, route)


    def crop_route(route, rect):
        pieces = []
        for a, b in zip(route, route[1:]):
            piece = clip_segment(a, b, rect)
            if piece is not None:
                pieces.append(piece)
        return pieces
''')

AIRLANE_VISIBLE = dd('''
    import unittest

    from airlane.fence import leg_violations
    from airlane.geom import area, contains

    SQUARE = [(0, 0), (4, 0), (4, 4), (0, 4)]


    class BasicTests(unittest.TestCase):
        def test_area(self):
            self.assertEqual(area(SQUARE), 16)

        def test_contains(self):
            self.assertTrue(contains(SQUARE, (2, 2)))
            self.assertFalse(contains(SQUARE, (9, 9)))

        def test_leg_through_square(self):
            self.assertEqual(leg_violations([SQUARE], [(-2, 2), (6, 2)]), [(0, 0)])


    if __name__ == "__main__":
        unittest.main()
''')

AIRLANE_HIDDEN_GEOM = dd('''
    import unittest
    from fractions import Fraction as F

    from airlane.geom import area, area2, centroid, clip_segment, contains, cross, on_segment, orientation

    S = [(0, 0), (4, 0), (4, 4), (0, 4)]
    L = [(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)]
    T = [(5, 8), (8, 8), (6, 12)]


    class Basics(unittest.TestCase):
        def test_cross(self):
            self.assertEqual(cross((0, 0), (1, 0), (0, 1)), 1)
            self.assertEqual(cross((0, 0), (0, 1), (1, 0)), -1)
            self.assertEqual(cross((0, 0), (2, 2), (5, 5)), 0)
            self.assertEqual(cross((1, 1), (4, 2), (2, 5)), 3 * 4 - 1 * 1)

        def test_area(self):
            self.assertEqual(area2(S), 32)
            self.assertEqual(area2(S[::-1]), -32)
            self.assertEqual(area(S), 16)
            self.assertEqual(area(S[::-1]), 16)
            self.assertEqual(area2(L), 24)
            self.assertEqual(area(L), 12)
            self.assertEqual(area2(T), 12)
            self.assertEqual(area(T), 6)
            self.assertEqual(area([(0, 0), (3, 0), (0, 3)]), F(9, 2))
            self.assertIsInstance(area(S), F)

        def test_area_translation_invariant(self):
            moved = [(x + 1000, y - 77) for x, y in L]
            self.assertEqual(area2(moved), 24)

        def test_orientation(self):
            self.assertEqual(orientation(S), "ccw")
            self.assertEqual(orientation(S[::-1]), "cw")
            self.assertEqual(orientation([(0, 0), (1, 1), (2, 2)]), "degenerate")
            self.assertEqual(orientation([(0, 0), (5, 0)]), "degenerate")
            self.assertEqual(orientation(L), "ccw")
            self.assertEqual(orientation([(0, 0), (1, 0), (0, 1)]), "ccw")
            self.assertEqual(orientation([(0, 0), (0, 1), (1, 0)]), "cw")

        def test_on_segment(self):
            a, b = (0, 0), (4, 2)
            self.assertTrue(on_segment((2, 1), a, b))
            self.assertTrue(on_segment((0, 0), a, b))
            self.assertTrue(on_segment((4, 2), a, b))
            self.assertFalse(on_segment((6, 3), a, b))
            self.assertFalse(on_segment((-2, -1), a, b))
            self.assertFalse(on_segment((2, 2), a, b))
            self.assertTrue(on_segment((1, 5), (1, 0), (1, 9)))
            self.assertFalse(on_segment((1, 10), (1, 0), (1, 9)))
            self.assertTrue(on_segment((3, 3), (5, 5), (1, 1)))
            self.assertTrue(on_segment((2, 2), (2, 2), (2, 2)))
            self.assertFalse(on_segment((2, 3), (2, 2), (2, 2)))


    class Contains(unittest.TestCase):
        def test_square(self):
            for p in ((2, 2), (1, 3), (3, 1)):
                self.assertTrue(contains(S, p), p)
            for p in ((5, 2), (-1, 2), (2, 5), (2, -1), (9, 9), (-1, -1)):
                self.assertFalse(contains(S, p), p)

        def test_boundary_flag(self):
            for p in ((0, 0), (4, 4), (4, 2), (2, 0), (0, 3)):
                self.assertTrue(contains(S, p))
                self.assertTrue(contains(S, p, boundary=True))
                self.assertFalse(contains(S, p, boundary=False))
            self.assertTrue(contains(S, (2, 2), boundary=False))

        def test_concave(self):
            for p in ((1, 1), (3, 1), (1, 3), (1, 2), (0, 1)):
                self.assertTrue(contains(L, p), p)
            for p in ((3, 3), (3, 4), (5, 1), (-1, 2), (2, 5), (4, 3)):
                self.assertFalse(contains(L, p), p)
            for p in ((2, 3), (3, 2), (2, 2), (4, 1), (4, 2), (1, 4)):
                self.assertTrue(contains(L, p), p)
                self.assertFalse(contains(L, p, boundary=False), p)

        def test_rays_through_vertices(self):
            for y in range(-1, 6):
                self.assertEqual(contains(L, (-3, y)), False)
                self.assertEqual(contains(L, (9, y)), False)
            self.assertTrue(contains(L, (1, 0)))
            self.assertTrue(contains(L, (1, 4)))
            self.assertFalse(contains(L, (3, 4)))

        def test_orientation_does_not_matter(self):
            for p in ((1, 1), (3, 3), (2, 3), (1, 2)):
                self.assertEqual(contains(L, p), contains(L[::-1], p))
                self.assertEqual(contains(L, p, boundary=False), contains(L[::-1], p, boundary=False))

        def test_triangle(self):
            self.assertTrue(contains(T, (6, 9)))
            self.assertFalse(contains(T, (5, 11)))
            self.assertTrue(contains(T, (6, 8)))
            self.assertFalse(contains(T, (6, 8), boundary=False))
            self.assertFalse(contains(T, (7, 11)))
            self.assertTrue(contains(T, (7, 10)))
            self.assertFalse(contains(T, (7, 10), boundary=False))

        def test_too_few_vertices(self):
            for poly in ([], [(0, 0)], [(0, 0), (1, 1)]):
                with self.assertRaises(ValueError):
                    contains(poly, (0, 0))


    DIAMOND = [(2, 0), (4, 2), (2, 4), (0, 2)]


    def l_state(x, y):
        """'in', 'edge' or 'out' for the L polygon, from its description as a union of two rectangles"""
        edges = (
            (y == 0 and 0 <= x <= 4) or (x == 4 and 0 <= y <= 2) or (y == 2 and 2 <= x <= 4)
            or (x == 2 and 2 <= y <= 4) or (y == 4 and 0 <= x <= 2) or (x == 0 and 0 <= y <= 4)
        )
        if edges:
            return "edge"
        if (0 < x < 4 and 0 < y < 2) or (0 < x < 2 and 0 < y < 4):
            return "in"
        return "out"


    def diamond_state(x, y):
        d = abs(x - 2) + abs(y - 2)
        return "in" if d < 2 else "edge" if d == 2 else "out"


    class ContainsExhaustive(unittest.TestCase):
        def check(self, poly, state):
            for x in range(-2, 7):
                for y in range(-2, 7):
                    want = state(x, y)
                    self.assertEqual(contains(poly, (x, y)), want != "out", (x, y))
                    self.assertEqual(contains(poly, (x, y), boundary=False), want == "in", (x, y))
                    self.assertEqual(contains(poly[::-1], (x, y), boundary=False), want == "in", (x, y))

        def test_l_shape(self):
            self.check(L, l_state)

        def test_diamond(self):
            self.check(DIAMOND, diamond_state)

        def test_rotated_start_vertex(self):
            self.check(L[2:] + L[:2], l_state)
            self.check(DIAMOND[1:] + DIAMOND[:1], diamond_state)


    class Centroid(unittest.TestCase):
        def test_values(self):
            self.assertEqual(centroid(S), (2, 2))
            self.assertEqual(centroid(L), (F(5, 3), F(5, 3)))
            self.assertEqual(centroid(T), (F(19, 3), F(28, 3)))
            self.assertEqual(centroid(S[::-1]), (2, 2))
            self.assertEqual(centroid(L[::-1]), (F(5, 3), F(5, 3)))
            self.assertEqual(centroid([(0, 0), (6, 0), (0, 3)]), (2, 1))

        def test_translation(self):
            moved = [(x + 10, y - 4) for x, y in L]
            self.assertEqual(centroid(moved), (F(5, 3) + 10, F(5, 3) - 4))

        def test_errors(self):
            with self.assertRaises(ValueError):
                centroid([(0, 0), (1, 1), (2, 2)])
            with self.assertRaises(ValueError):
                centroid([(0, 0), (1, 1)])
            with self.assertRaises(ValueError):
                centroid([])


    class Clip(unittest.TestCase):
        R = (0, 0, 10, 10)

        def test_horizontal_and_vertical(self):
            self.assertEqual(clip_segment((-5, 5), (15, 5), self.R), ((0, 5), (10, 5)))
            self.assertEqual(clip_segment((5, -5), (5, 15), self.R), ((5, 0), (5, 10)))
            self.assertEqual(clip_segment((15, 5), (-5, 5), self.R), ((10, 5), (0, 5)))
            self.assertEqual(clip_segment((5, 15), (5, -5), self.R), ((5, 10), (5, 0)))

        def test_inside_and_outside(self):
            self.assertEqual(clip_segment((1, 1), (9, 2), self.R), ((1, 1), (9, 2)))
            self.assertEqual(clip_segment((0, 0), (10, 10), self.R), ((0, 0), (10, 10)))
            self.assertIsNone(clip_segment((11, 0), (11, 10), self.R))
            self.assertIsNone(clip_segment((-5, 11), (15, 11), self.R))
            self.assertIsNone(clip_segment((-5, -1), (15, -1), self.R))
            self.assertIsNone(clip_segment((-3, 12), (12, 12), self.R))
            self.assertIsNone(clip_segment((-5, 12), (-1, 15), self.R))

        def test_diagonals(self):
            self.assertEqual(clip_segment((-5, -5), (5, 5), self.R), ((0, 0), (5, 5)))
            self.assertEqual(clip_segment((-5, -5), (15, 15), self.R), ((0, 0), (10, 10)))
            self.assertEqual(clip_segment((15, 15), (-5, -5), self.R), ((10, 10), (0, 0)))
            self.assertEqual(clip_segment((-5, 15), (5, 5), self.R), ((0, 10), (5, 5)))
            self.assertEqual(clip_segment((-5, 15), (15, -5), self.R), ((0, 10), (10, 0)))

        def test_fractions(self):
            got = clip_segment((-3, 0), (7, 5), self.R)
            self.assertEqual(got, ((0, F(3, 2)), (7, 5)))
            self.assertIsInstance(got[0][0], F)
            got = clip_segment((0, 0), (30, 10), self.R)
            self.assertEqual(got, ((0, 0), (10, F(10, 3))))
            got = clip_segment((-1, 2), (4, 12), (0, 0, 10, 10))
            self.assertEqual(got, ((0, 4), (3, 10)))

        def test_boundary_lines_count(self):
            self.assertEqual(clip_segment((-5, 10), (15, 10), self.R), ((0, 10), (10, 10)))
            self.assertEqual(clip_segment((0, -5), (0, 15), self.R), ((0, 0), (0, 10)))
            self.assertEqual(clip_segment((10, -5), (10, 15), self.R), ((10, 0), (10, 10)))
            self.assertEqual(clip_segment((-5, 0), (15, 0), self.R), ((0, 0), (10, 0)))

        def test_touching_only_at_a_corner(self):
            self.assertEqual(clip_segment((-5, 15), (0, 10), self.R), ((0, 10), (0, 10)))
            self.assertEqual(clip_segment((-5, 5), (0, 5), self.R), ((0, 5), (0, 5)))
            self.assertEqual(clip_segment((10, 10), (15, 15), self.R), ((10, 10), (10, 10)))

        def test_point_segments(self):
            self.assertEqual(clip_segment((5, 5), (5, 5), self.R), ((5, 5), (5, 5)))
            self.assertEqual(clip_segment((0, 10), (0, 10), self.R), ((0, 10), (0, 10)))
            self.assertIsNone(clip_segment((11, 11), (11, 11), self.R))
            self.assertIsNone(clip_segment((-1, 5), (-1, 5), self.R))

        def test_rect_offset_and_degenerate(self):
            self.assertEqual(clip_segment((0, 0), (20, 20), (5, 5, 8, 8)), ((5, 5), (8, 8)))
            self.assertEqual(clip_segment((0, 6), (20, 6), (5, 5, 5, 8)), ((5, 6), (5, 6)))
            self.assertEqual(clip_segment((0, 6), (20, 6), (5, 6, 15, 6)), ((5, 6), (15, 6)))

        def test_against_interval_arithmetic(self):
            def oracle(a, b, rect):
                (x0, y0), (x1, y1) = a, b
                lo, hi = F(0), F(1)
                for start, delta, mn, mx in ((x0, x1 - x0, rect[0], rect[2]), (y0, y1 - y0, rect[1], rect[3])):
                    if delta == 0:
                        if not mn <= start <= mx:
                            return None
                    else:
                        ta, tb = F(mn - start, delta), F(mx - start, delta)
                        lo, hi = max(lo, min(ta, tb)), min(hi, max(ta, tb))
                if lo > hi:
                    return None
                return (x0 + lo * (x1 - x0), y0 + lo * (y1 - y0)), (x0 + hi * (x1 - x0), y0 + hi * (y1 - y0))

            coords = (-3, 0, 2, 5, 10, 13)
            for rect in ((0, 0, 10, 10), (2, 3, 7, 8), (-1, -2, 4, 6)):
                for ax in coords:
                    for ay in coords:
                        for bx in coords:
                            for by in coords:
                                self.assertEqual(clip_segment((ax, ay), (bx, by), rect), oracle((ax, ay), (bx, by), rect), ((ax, ay), (bx, by), rect))

        def test_bad_rect(self):
            with self.assertRaises(ValueError):
                clip_segment((0, 0), (1, 1), (5, 0, 4, 10))
            with self.assertRaises(ValueError):
                clip_segment((0, 0), (1, 1), (0, 5, 10, 4))


    if __name__ == "__main__":
        unittest.main()
''')

AIRLANE_HIDDEN_FENCE = dd('''
    import unittest
    from fractions import Fraction as F

    from airlane.fence import crop_route, first_violation, leg_hits, leg_violations, route_clear, segments_intersect

    S = [(0, 0), (4, 0), (4, 4), (0, 4)]
    T = [(5, 8), (8, 8), (6, 12)]


    class Intersect(unittest.TestCase):
        def test_proper_crossing(self):
            self.assertTrue(segments_intersect((0, 0), (4, 4), (0, 4), (4, 0)))
            self.assertTrue(segments_intersect((0, 0), (4, 4), (4, 0), (0, 4)))
            self.assertTrue(segments_intersect((1, 0), (1, 9), (0, 5), (9, 5)))

        def test_touching(self):
            self.assertTrue(segments_intersect((0, 0), (4, 0), (2, 0), (2, 3)))       # T junction
            self.assertTrue(segments_intersect((2, 3), (2, 0), (0, 0), (4, 0)))
            self.assertTrue(segments_intersect((0, 0), (2, 2), (2, 2), (5, 0)))       # shared end point
            self.assertTrue(segments_intersect((0, 0), (2, 2), (-3, 5), (0, 0)))
            self.assertTrue(segments_intersect((0, 0), (4, 4), (2, 2), (9, 0)))       # end point on the other segment

        def test_collinear(self):
            self.assertTrue(segments_intersect((0, 0), (4, 0), (2, 0), (6, 0)))
            self.assertTrue(segments_intersect((0, 0), (4, 0), (1, 0), (3, 0)))
            self.assertTrue(segments_intersect((0, 0), (4, 0), (4, 0), (8, 0)))
            self.assertFalse(segments_intersect((0, 0), (1, 0), (2, 0), (3, 0)))
            self.assertFalse(segments_intersect((0, 0), (1, 1), (2, 2), (3, 3)))

        def test_apart(self):
            self.assertFalse(segments_intersect((0, 0), (4, 0), (0, 1), (4, 1)))       # parallel
            self.assertFalse(segments_intersect((0, 0), (2, 2), (3, 0), (3, 5)))
            self.assertFalse(segments_intersect((0, 0), (1, 0), (2, -1), (2, 1)))
            self.assertFalse(segments_intersect((0, 0), (4, 0), (5, 1), (9, 9)))
            self.assertFalse(segments_intersect((0, 0), (4, 0), (2, 1), (2, 5)))
            self.assertFalse(segments_intersect((0, 0), (4, 4), (0, 2), (1, 2)))


    class IntersectExhaustive(unittest.TestCase):
        def test_against_parametric_solution(self):
            def oracle(a, b, c, d):
                r = (b[0] - a[0], b[1] - a[1])
                s = (d[0] - c[0], d[1] - c[1])
                qp = (c[0] - a[0], c[1] - a[1])
                denom = r[0] * s[1] - r[1] * s[0]
                if denom != 0:
                    t = F(qp[0] * s[1] - qp[1] * s[0], denom)
                    u = F(qp[0] * r[1] - qp[1] * r[0], denom)
                    return 0 <= t <= 1 and 0 <= u <= 1
                if qp[0] * r[1] - qp[1] * r[0] != 0:
                    return False
                axis = 0 if r[0] != 0 else 1
                lo1, hi1 = sorted((a[axis], b[axis]))
                lo2, hi2 = sorted((c[axis], d[axis]))
                return max(lo1, lo2) <= min(hi1, hi2)

            pts = [(x, y) for x in range(4) for y in range(4)]
            for a in pts:
                for b in pts:
                    if a == b:
                        continue
                    for c in pts:
                        for d in pts:
                            if c == d:
                                continue
                            self.assertEqual(segments_intersect(a, b, c, d), oracle(a, b, c, d), (a, b, c, d))

        def test_degenerate_segments(self):
            self.assertTrue(segments_intersect((1, 1), (1, 1), (0, 0), (2, 2)))
            self.assertFalse(segments_intersect((1, 2), (1, 2), (0, 0), (2, 2)))
            self.assertTrue(segments_intersect((0, 0), (2, 2), (1, 1), (1, 1)))
            self.assertTrue(segments_intersect((3, 3), (3, 3), (3, 3), (3, 3)))
            self.assertFalse(segments_intersect((3, 3), (3, 3), (3, 4), (3, 4)))


    class Legs(unittest.TestCase):
        def test_hits(self):
            self.assertTrue(leg_hits(S, (-2, 2), (6, 2)))           # through
            self.assertTrue(leg_hits(S, (1, 1), (2, 2)))            # fully inside
            self.assertTrue(leg_hits(S, (-2, 2), (2, 2)))           # ends inside
            self.assertTrue(leg_hits(S, (2, 2), (9, 9)))            # starts inside
            self.assertTrue(leg_hits(S, (4, 6), (4, 4)))            # ends on a vertex
            self.assertTrue(leg_hits(S, (0, -1), (0, 5)))           # along an edge
            self.assertTrue(leg_hits(S, (6, 2), (4, 2)))            # ends on an edge
            self.assertTrue(leg_hits(S, (-1, 5), (5, -1)))          # the diagonal from corner to corner

        def test_misses(self):
            self.assertFalse(leg_hits(S, (5, 0), (5, 9)))
            self.assertFalse(leg_hits(S, (-1, 5), (5, 5)))
            self.assertFalse(leg_hits(S, (10, 10), (12, 12)))
            self.assertFalse(leg_hits(S, (-3, 0), (-1, 0)))
            self.assertFalse(leg_hits(S, (-5, 5), (5, 10)))
            self.assertFalse(leg_hits(S, (-2, 4), (4, 10)))
            self.assertFalse(leg_hits(S, (5, 5), (5, 5)))

        def test_point_leg(self):
            self.assertTrue(leg_hits(S, (2, 2), (2, 2)))
            self.assertTrue(leg_hits(S, (4, 4), (4, 4)))


    class Routes(unittest.TestCase):
        def test_violations_in_order(self):
            route = [(-2, 2), (6, 2), (6, 10)]
            self.assertEqual(leg_violations([S, T], route), [(0, 0), (1, 1)])
            self.assertEqual(leg_violations([T, S], route), [(0, 1), (1, 0)])
            self.assertEqual(first_violation([S, T], route), (0, 0))
            self.assertFalse(route_clear([S, T], route))

        def test_multiple_polygons_one_leg(self):
            shifted = [(x + 6, y) for x, y in S]
            route = [(-2, 2), (12, 2)]
            self.assertEqual(leg_violations([shifted, S], route), [(0, 0), (0, 1)])
            self.assertEqual(leg_violations([S, [(20, 20), (30, 20), (25, 30)], shifted], route), [(0, 0), (0, 2)])

        def test_clear_routes(self):
            route = [(10, 10), (12, 12), (20, 0)]
            self.assertEqual(leg_violations([S, T], route), [])
            self.assertIsNone(first_violation([S, T], route))
            self.assertTrue(route_clear([S, T], route))

        def test_short_routes(self):
            for route in ([], [(1, 1)]):
                self.assertEqual(leg_violations([S], route), [])
                self.assertTrue(route_clear([S], route))
                self.assertIsNone(first_violation([S], route))
            self.assertEqual(leg_violations([], [(0, 0), (1, 1)]), [])

        def test_second_leg_only(self):
            route = [(10, 10), (10, 2), (2, 2)]
            self.assertEqual(leg_violations([S], route), [(1, 0)])
            self.assertEqual(first_violation([S], route), (1, 0))


    class Crop(unittest.TestCase):
        def test_crop(self):
            route = [(-5, 5), (5, 5), (5, 15)]
            self.assertEqual(crop_route(route, (0, 0, 10, 10)), [((0, 5), (5, 5)), ((5, 5), (5, 10))])

        def test_outside_legs_are_dropped(self):
            route = [(-5, 20), (-5, 30), (5, 5), (15, 5), (30, 30)]
            got = crop_route(route, (0, 0, 10, 10))
            self.assertEqual(got, [((3, 10), (5, 5)), ((5, 5), (10, 5))])

        def test_empty_and_single(self):
            self.assertEqual(crop_route([], (0, 0, 1, 1)), [])
            self.assertEqual(crop_route([(5, 5)], (0, 0, 10, 10)), [])
            self.assertEqual(crop_route([(1, 1), (2, 2)], (0, 0, 10, 10)), [((1, 1), (2, 2))])


    if __name__ == "__main__":
        unittest.main()
''')

AIRLANE = Lib(
    name="airlane", lang="python", title="the airlane no-fly geometry package",
    blurb="The drone operator's planner uses airlane to test flight routes against no-fly polygons and to crop routes to a service area.",
    files={
        "airlane/__init__.py": "", "airlane/geom.py": AIRLANE_GEOM, "airlane/fence.py": AIRLANE_FENCE,
        "README.md": AIRLANE_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": AIRLANE_VISIBLE},
    hidden_tests={"tests/test_geom.py": AIRLANE_HIDDEN_GEOM, "tests/test_fence.py": AIRLANE_HIDDEN_FENCE},
    mutate=["airlane/geom.py", "airlane/fence.py"],
    difficulty=3, tags=["geometry", "polygons", "multi-module"],
    probes=[
        "area2([(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)])",
        "orientation([(0, 0), (0, 4), (4, 4), (4, 0)])",
        "[contains([(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)], p) for p in [(1, 2), (3, 3), (2, 3), (3, 2), (-3, 2)]]",
        "contains([(0, 0), (4, 0), (4, 4), (0, 4)], (4, 2), boundary=False)",
        "centroid([(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)])",
        "clip_segment((-3, 0), (7, 5), (0, 0, 10, 10))", "clip_segment((-5, 15), (0, 10), (0, 0, 10, 10))",
        "clip_segment((15, 5), (-5, 5), (0, 0, 10, 10))", "clip_segment((-5, 11), (15, 11), (0, 0, 10, 10))",
        "segments_intersect((0, 0), (4, 0), (2, 0), (2, 3))", "segments_intersect((0, 0), (1, 0), (2, 0), (3, 0))",
        "segments_intersect((0, 0), (4, 0), (4, 0), (8, 0))",
        "leg_violations([[(0, 0), (4, 0), (4, 4), (0, 4)], [(5, 8), (8, 8), (6, 12)]], [(-2, 2), (6, 2), (6, 10)])",
        "leg_hits([(0, 0), (4, 0), (4, 4), (0, 4)], (4, 6), (4, 4))",
        "crop_route([(-5, 5), (5, 5), (5, 15)], (0, 0, 10, 10))",
    ],
    probe_import="from airlane.geom import area2, orientation, contains, centroid, clip_segment\nfrom airlane.fence import segments_intersect, leg_violations, leg_hits, crop_route\n",
)

# ======================================================================================================================
# chordbook: note names, intervals and chord symbols for a lead-sheet tool (multi-module)
# ======================================================================================================================

CHORDBOOK_README = dd('''
    # chordbook

    Note arithmetic and chord symbols for a lead-sheet editor. Pitches use scientific pitch notation where `C4` is
    middle C and has MIDI number 60 (`C-1` is 0).

    ## `chordbook.notes`

    * `parse_note(text) -> (letter, accidental, octave)`: `text` is a letter `A`-`G` (upper case), an optional
      accidental (`#` sharp = +1, `b` flat = -1, `x` double sharp = +2, `bb` double flat = -2) and an optional octave
      (an integer, may be negative); `octave` is `None` when absent. Anything else (`"H4"`, `"c4"`, `"C##4"`, `""`)
      is a `ValueError`.
    * `pitch_class(text) -> int`: 0 to 11 for `C` to `B`, counting accidentals, modulo 12 (`B#` is 0, `Cb` is 11).
    * `midi(text) -> int`: `12 * (octave + 1) + pitch value + accidental` (so `B#3` is 60 and `Cb4` is 59);
      `ValueError` if the note has no octave.
    * `name_of(number, prefer="sharp") -> str`: the note name with octave for a MIDI number: sharp spelling
      `C C# D D# E F F# G G# A A# B` or, with `prefer="flat"`, `C Db D Eb E F Gb G Ab A Bb B`; the octave is
      `number // 12 - 1`. Any other `prefer` is a `ValueError`.
    * `transpose(text, semitones, prefer=None) -> str`: shift a note up (or down when negative). With an octave the
      result is `name_of(midi(text) + semitones, ...)`; without one only the pitch class moves and the result has no
      octave. The spelling is `prefer` when given, otherwise flat when the note's accidental is `b` or `bb` and sharp
      in every other case.

    ## `chordbook.intervals`

    * `interval_name(semitones) -> str`: for an absolute size 0..12 the names `P1 m2 M2 m3 M3 P4 TT P5 m6 M6 m7 M7
      P8`; above 12 the name of the remainder (`s % 12`, but 12 instead of 0) followed by `+` and the number of whole
      octaves added, `(s - 1) // 12`: 14 is `M2+1`, 19 is `P5+1`, 24 is `P8+1`, 25 is `m2+2`. A negative size gets a
      leading `-`.
    * `interval(a, b) -> (semitones, name)`: from note `a` to note `b`, both with octaves (`ValueError` otherwise):
      `midi(b) - midi(a)` and its name.
    * `class_interval(a, b) -> (semitones, name)`: the ascending distance between the *pitch classes*, `(pc(b) -
      pc(a)) % 12` (octaves are ignored; the same pitch class is 0, `P1`).

    ## `chordbook.chords`

    `QUALITIES` maps a quality suffix to its semitone offsets above the root, in this order: `""` (0 4 7), `m` (0 3
    7), `dim` (0 3 6), `aug` (0 4 8), `7` (0 4 7 10), `maj7` (0 4 7 11), `m7` (0 3 7 10), `m7b5` (0 3 6 10), `dim7`
    (0 3 6 9), `sus2` (0 2 7), `sus4` (0 5 7), `6` (0 4 7 9), `m6` (0 3 7 9) and `9` (0 4 7 10 14).

    * `parse_chord(symbol) -> (root, quality, bass)`: `root` is a letter with an optional `#` or `b` (a `b` right
      after the letter is always an accidental), then the quality suffix, then optionally `/` and a bass note (a
      letter with an optional `#` or `b`); `bass` is `None` without a slash. `ValueError` for an unknown quality, a
      bad root or bass.
    * `chord_notes(symbol, octave=4) -> list[str]`: the chord tones as note names with octave, lowest first: the root
      in `octave` and every other tone above it by its offset, all spelled with the sharp table, or with the flat
      table when the root's accidental is `b`. A slash chord starts with its bass note written as in the symbol, in
      `octave - 1`.
    * `identify(notes) -> str | None`: the symbol for a list of note names (with or without octaves, lowest first).
      Take the distinct pitch classes in order of first appearance and try each as the root (in that order); for a
      root try the qualities in `QUALITIES` order; the first quality whose offsets (modulo 12) form exactly the set of
      pitch classes wins. The root is spelled from the flat table if any given note has a flat accidental and from
      the sharp table otherwise; when the root is not the first note the symbol gets `/` and the first note's name
      (spelled the same way). `None` when nothing matches; `ValueError` for an empty list.
    * `transpose_chord(symbol, semitones) -> str`: transpose the root (and the bass), keep the quality. Names come from
      the flat table when the root or the bass of the symbol has a `b`, otherwise from the sharp table.
''')

CHORDBOOK_NOTES = dd('''
    """Note names and numbers."""
    import re

    PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    ACC = {"": 0, "#": 1, "b": -1, "x": 2, "bb": -2}
    SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
    _NOTE = re.compile(r"^([A-G])(#|bb|b|x)?(-?\\d+)?$")


    def parse_note(text):
        m = _NOTE.match(text)
        if not m:
            raise ValueError(f"not a note: {text!r}")
        octave = int(m.group(3)) if m.group(3) is not None else None
        return m.group(1), ACC[m.group(2) or ""], octave


    def pitch_class(text):
        letter, acc, _ = parse_note(text)
        return (PC[letter] + acc) % 12


    def midi(text):
        letter, acc, octave = parse_note(text)
        if octave is None:
            raise ValueError(f"note {text!r} has no octave")
        return 12 * (octave + 1) + PC[letter] + acc


    def table(prefer):
        if prefer == "sharp":
            return SHARP
        if prefer == "flat":
            return FLAT
        raise ValueError(f"unknown spelling {prefer!r}")


    def name_of(number, prefer="sharp"):
        return f"{table(prefer)[number % 12]}{number // 12 - 1}"


    def transpose(text, semitones, prefer=None):
        letter, acc, octave = parse_note(text)
        if prefer is None:
            prefer = "flat" if acc < 0 else "sharp"
        if octave is None:
            return table(prefer)[(pitch_class(text) + semitones) % 12]
        return name_of(midi(text) + semitones, prefer)
''')

CHORDBOOK_INTERVALS = dd('''
    """Intervals between notes."""
    from .notes import midi, pitch_class

    NAMES = ["P1", "m2", "M2", "m3", "M3", "P4", "TT", "P5", "m6", "M6", "m7", "M7", "P8"]


    def interval_name(semitones):
        size = abs(semitones)
        if size <= 12:
            name = NAMES[size]
        else:
            name = f"{NAMES[size % 12 or 12]}+{(size - 1) // 12}"
        return ("-" if semitones < 0 else "") + name


    def interval(a, b):
        semis = midi(b) - midi(a)
        return semis, interval_name(semis)


    def class_interval(a, b):
        semis = (pitch_class(b) - pitch_class(a)) % 12
        return semis, interval_name(semis)
''')

CHORDBOOK_CHORDS = dd('''
    """Chord symbols."""
    import re

    from .notes import FLAT, SHARP, midi, name_of, parse_note, pitch_class

    QUALITIES = {
        "": [0, 4, 7], "m": [0, 3, 7], "dim": [0, 3, 6], "aug": [0, 4, 8], "7": [0, 4, 7, 10],
        "maj7": [0, 4, 7, 11], "m7": [0, 3, 7, 10], "m7b5": [0, 3, 6, 10], "dim7": [0, 3, 6, 9],
        "sus2": [0, 2, 7], "sus4": [0, 5, 7], "6": [0, 4, 7, 9], "m6": [0, 3, 7, 9], "9": [0, 4, 7, 10, 14],
    }
    _CHORD = re.compile(r"^([A-G][#b]?)([^/]*)(?:/([A-G][#b]?))?$")


    def parse_chord(symbol):
        m = _CHORD.match(symbol)
        if not m or m.group(2) not in QUALITIES:
            raise ValueError(f"not a chord symbol: {symbol!r}")
        return m.group(1), m.group(2), m.group(3)


    def chord_notes(symbol, octave=4):
        root, quality, bass = parse_chord(symbol)
        prefer = "flat" if root.endswith("b") else "sharp"
        base = midi(f"{root}{octave}")
        notes = [name_of(base + step, prefer) for step in QUALITIES[quality]]
        if bass is not None:
            notes.insert(0, f"{bass}{octave - 1}")
        return notes


    def identify(notes):
        if not notes:
            raise ValueError("no notes")
        pcs = [pitch_class(n) for n in notes]
        names = FLAT if any(parse_note(n)[1] < 0 for n in notes) else SHARP
        present = set(pcs)
        for root in dict.fromkeys(pcs):
            relative = {(p - root) % 12 for p in present}
            for quality, steps in QUALITIES.items():
                if relative == {s % 12 for s in steps}:
                    symbol = names[root] + quality
                    if root != pcs[0]:
                        symbol += "/" + names[pcs[0]]
                    return symbol
        return None


    def transpose_chord(symbol, semitones):
        root, quality, bass = parse_chord(symbol)
        names = FLAT if root.endswith("b") or (bass or "").endswith("b") else SHARP
        out = names[(pitch_class(root) + semitones) % 12] + quality
        if bass is not None:
            out += "/" + names[(pitch_class(bass) + semitones) % 12]
        return out
''')

CHORDBOOK_VISIBLE = dd('''
    import unittest

    from chordbook.chords import chord_notes, identify
    from chordbook.intervals import interval
    from chordbook.notes import midi


    class BasicTests(unittest.TestCase):
        def test_midi(self):
            self.assertEqual(midi("C4"), 60)

        def test_interval(self):
            self.assertEqual(interval("C4", "E4"), (4, "M3"))

        def test_chords(self):
            self.assertEqual(chord_notes("C"), ["C4", "E4", "G4"])
            self.assertEqual(identify(["C4", "E4", "G4"]), "C")


    if __name__ == "__main__":
        unittest.main()
''')

CHORDBOOK_HIDDEN_NOTES = dd('''
    import unittest

    from chordbook.notes import midi, name_of, parse_note, pitch_class, transpose


    class Parse(unittest.TestCase):
        def test_valid(self):
            table = {
                "C4": ("C", 0, 4), "C#4": ("C", 1, 4), "Bb3": ("B", -1, 3), "Fx": ("F", 2, None), "Dbb2": ("D", -2, 2),
                "E": ("E", 0, None), "C-1": ("C", 0, -1), "Ab": ("A", -1, None), "G10": ("G", 0, 10), "Bbb": ("B", -2, None),
                "Gx-2": ("G", 2, -2),
            }
            for text, want in table.items():
                self.assertEqual(parse_note(text), want, text)

        def test_invalid(self):
            for text in ("H4", "c4", "C##4", "", "4", "C#b4", "Cbbb", "C4#", "C 4", "Cb#", "cb4", "X", "C--1", "C+4", "C4.5", " C4"):
                with self.assertRaises(ValueError, msg=text):
                    parse_note(text)


    class Numbers(unittest.TestCase):
        def test_pitch_class(self):
            table = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11, "C#": 1, "Db": 1, "B#": 0, "Cb": 11, "Fx": 7,
                     "Dbb": 0, "E#": 5, "Fb": 4, "Gbb": 5, "Ax": 11, "C4": 0, "Bb7": 10}
            for text, want in table.items():
                self.assertEqual(pitch_class(text), want, text)

        def test_midi(self):
            table = {"C4": 60, "A4": 69, "C-1": 0, "B#3": 60, "Cb4": 59, "C#4": 61, "G9": 127, "B3": 59, "Dbb4": 60, "Fx2": 43}
            for text, want in table.items():
                self.assertEqual(midi(text), want, text)

        def test_midi_needs_octave(self):
            with self.assertRaises(ValueError):
                midi("C")
            with self.assertRaises(ValueError):
                midi("Bb")

        def test_name_of(self):
            table = {60: "C4", 61: "C#4", 70: "A#4", 69: "A4", 0: "C-1", 71: "B4", 72: "C5", 127: "G9", 59: "B3", 11: "B-1"}
            for number, want in table.items():
                self.assertEqual(name_of(number), want, number)
            self.assertEqual(name_of(61, "flat"), "Db4")
            self.assertEqual(name_of(70, "flat"), "Bb4")
            self.assertEqual(name_of(60, "flat"), "C4")
            self.assertEqual(name_of(63, prefer="sharp"), "D#4")
            for prefer in ("sharps", "", None, "Flat"):
                with self.assertRaises(ValueError):
                    name_of(60, prefer)

        def test_name_of_midi_round_trip(self):
            for n in range(0, 128):
                self.assertEqual(midi(name_of(n)), n)
                self.assertEqual(midi(name_of(n, "flat")), n)


    class Transpose(unittest.TestCase):
        def test_with_octave(self):
            self.assertEqual(transpose("C4", 7), "G4")
            self.assertEqual(transpose("C4", -1), "B3")
            self.assertEqual(transpose("C4", 12), "C5")
            self.assertEqual(transpose("C4", 0), "C4")
            self.assertEqual(transpose("C4", 1), "C#4")
            self.assertEqual(transpose("F#3", 1), "G3")
            self.assertEqual(transpose("F#3", 2), "G#3")
            self.assertEqual(transpose("A4", -33), "C2")

        def test_flat_input_gets_flat_names(self):
            self.assertEqual(transpose("Bb3", 2), "C4")
            self.assertEqual(transpose("Bb3", 5), "Eb4")
            self.assertEqual(transpose("Eb4", 1), "E4")
            self.assertEqual(transpose("Db4", 3), "E4")
            self.assertEqual(transpose("Ab4", 2), "Bb4")
            self.assertEqual(transpose("Dbb4", 1), "Db4")

        def test_prefer(self):
            self.assertEqual(transpose("C4", 1, prefer="flat"), "Db4")
            self.assertEqual(transpose("Bb3", 3, prefer="sharp"), "C#4")
            self.assertEqual(transpose("F#3", 3, prefer="flat"), "A3")
            self.assertEqual(transpose("C4", 3, "flat"), "Eb4")
            with self.assertRaises(ValueError):
                transpose("C4", 1, prefer="blue")

        def test_without_octave(self):
            self.assertEqual(transpose("A", 3), "C")
            self.assertEqual(transpose("Bb", 1), "B")
            self.assertEqual(transpose("C", -1), "B")
            self.assertEqual(transpose("C", 13), "C#")
            self.assertEqual(transpose("C", 25), "C#")
            self.assertEqual(transpose("C", 1, prefer="flat"), "Db")
            self.assertEqual(transpose("Eb", 2), "F")
            self.assertEqual(transpose("G", -24), "G")
            self.assertEqual(transpose("F#", 7), "C#")

        def test_errors(self):
            with self.assertRaises(ValueError):
                transpose("H4", 1)


    if __name__ == "__main__":
        unittest.main()
''')

CHORDBOOK_HIDDEN_INTERVALS = dd('''
    import unittest

    from chordbook.intervals import class_interval, interval, interval_name


    class Names(unittest.TestCase):
        def test_simple(self):
            want = ["P1", "m2", "M2", "m3", "M3", "P4", "TT", "P5", "m6", "M6", "m7", "M7", "P8"]
            self.assertEqual([interval_name(i) for i in range(13)], want)

        def test_compound(self):
            table = {13: "m2+1", 14: "M2+1", 19: "P5+1", 23: "M7+1", 24: "P8+1", 25: "m2+2", 26: "M2+2", 36: "P8+2", 37: "m2+3", 48: "P8+3"}
            for n, want in table.items():
                self.assertEqual(interval_name(n), want, n)

        def test_negative(self):
            table = {-4: "-M3", -1: "-m2", -12: "-P8", -13: "-m2+1", -24: "-P8+1", 0: "P1", -7: "-P5"}
            for n, want in table.items():
                self.assertEqual(interval_name(n), want, n)


    class Between(unittest.TestCase):
        def test_interval(self):
            self.assertEqual(interval("C4", "E4"), (4, "M3"))
            self.assertEqual(interval("E4", "C4"), (-4, "-M3"))
            self.assertEqual(interval("C4", "C5"), (12, "P8"))
            self.assertEqual(interval("C4", "D5"), (14, "M2+1"))
            self.assertEqual(interval("C4", "C4"), (0, "P1"))
            self.assertEqual(interval("Bb3", "D4"), (4, "M3"))
            self.assertEqual(interval("C4", "G4"), (7, "P5"))
            self.assertEqual(interval("G4", "C4"), (-7, "-P5"))
            self.assertEqual(interval("C3", "C5"), (24, "P8+1"))
            self.assertEqual(interval("F#4", "C5"), (6, "TT"))
            self.assertEqual(interval("B3", "C4"), (1, "m2"))
            self.assertEqual(interval("E#4", "F4"), (0, "P1"))

        def test_needs_octaves(self):
            for a, b in (("C", "E4"), ("C4", "E"), ("C", "E")):
                with self.assertRaises(ValueError):
                    interval(a, b)

        def test_class_interval(self):
            self.assertEqual(class_interval("C", "E"), (4, "M3"))
            self.assertEqual(class_interval("E", "C"), (8, "m6"))
            self.assertEqual(class_interval("C", "C"), (0, "P1"))
            self.assertEqual(class_interval("G", "F"), (10, "m7"))
            self.assertEqual(class_interval("C4", "C5"), (0, "P1"))
            self.assertEqual(class_interval("B", "C"), (1, "m2"))
            self.assertEqual(class_interval("Bb", "A"), (11, "M7"))
            self.assertEqual(class_interval("C#", "Db"), (0, "P1"))
            self.assertEqual(class_interval("A5", "C2"), (3, "m3"))
            self.assertEqual(class_interval("F#", "C"), (6, "TT"))


    if __name__ == "__main__":
        unittest.main()
''')

CHORDBOOK_HIDDEN_CHORDS = dd('''
    import unittest

    from chordbook.chords import QUALITIES, chord_notes, identify, parse_chord, transpose_chord


    class Qualities(unittest.TestCase):
        def test_table(self):
            self.assertEqual(list(QUALITIES), ["", "m", "dim", "aug", "7", "maj7", "m7", "m7b5", "dim7", "sus2", "sus4", "6", "m6", "9"])
            self.assertEqual(QUALITIES[""], [0, 4, 7])
            self.assertEqual(QUALITIES["m7b5"], [0, 3, 6, 10])
            self.assertEqual(QUALITIES["9"], [0, 4, 7, 10, 14])


    class Parse(unittest.TestCase):
        def test_valid(self):
            table = {
                "Cmaj7": ("C", "maj7", None), "Bb7": ("Bb", "7", None), "F#m7b5": ("F#", "m7b5", None), "Dsus4": ("D", "sus4", None),
                "E": ("E", "", None), "Am": ("A", "m", None), "C/E": ("C", "", "E"), "Bbm/Db": ("Bb", "m", "Db"),
                "G7/F": ("G", "7", "F"), "Cb": ("Cb", "", None), "Bbm7b5": ("Bb", "m7b5", None), "Bm7b5": ("B", "m7b5", None),
                "Gdim7/F#": ("G", "dim7", "F#"), "A9": ("A", "9", None), "Ebm6": ("Eb", "m6", None), "B": ("B", "", None),
            }
            for text, want in table.items():
                self.assertEqual(parse_chord(text), want, text)

        def test_invalid(self):
            for text in ("Cfoo", "H", "", "c", "C/", "C/H", "C/E/G", "Cmaj", "C#x", "Cmaj7/", "m7", "C7b9", "Bbb", "/E"):
                with self.assertRaises(ValueError, msg=text):
                    parse_chord(text)


    class Notes(unittest.TestCase):
        def test_triads(self):
            self.assertEqual(chord_notes("C"), ["C4", "E4", "G4"])
            self.assertEqual(chord_notes("Cm"), ["C4", "D#4", "G4"])
            self.assertEqual(chord_notes("D"), ["D4", "F#4", "A4"])
            self.assertEqual(chord_notes("Ebm"), ["Eb4", "Gb4", "Bb4"])
            self.assertEqual(chord_notes("Eb"), ["Eb4", "G4", "Bb4"])
            self.assertEqual(chord_notes("Bdim"), ["B4", "D5", "F5"])
            self.assertEqual(chord_notes("Caug"), ["C4", "E4", "G#4"])

        def test_extended(self):
            self.assertEqual(chord_notes("G7"), ["G4", "B4", "D5", "F5"])
            self.assertEqual(chord_notes("F#m7b5"), ["F#4", "A4", "C5", "E5"])
            self.assertEqual(chord_notes("Bb9"), ["Bb4", "D5", "F5", "Ab5", "C6"])
            self.assertEqual(chord_notes("Cmaj7"), ["C4", "E4", "G4", "B4"])
            self.assertEqual(chord_notes("Asus2"), ["A4", "B4", "E5"])
            self.assertEqual(chord_notes("Asus4"), ["A4", "D5", "E5"])
            self.assertEqual(chord_notes("C6"), ["C4", "E4", "G4", "A4"])
            self.assertEqual(chord_notes("Cm6"), ["C4", "D#4", "G4", "A4"])
            self.assertEqual(chord_notes("Cdim7"), ["C4", "D#4", "F#4", "A4"])
            self.assertEqual(chord_notes("Dbmaj7"), ["Db4", "F4", "Ab4", "C5"])

        def test_octave(self):
            self.assertEqual(chord_notes("C", octave=3), ["C3", "E3", "G3"])
            self.assertEqual(chord_notes("A", 2), ["A2", "C#3", "E3"])
            self.assertEqual(chord_notes("B", 5), ["B5", "D#6", "F#6"])
            self.assertEqual(chord_notes("Bb", 0), ["Bb0", "D1", "F1"])

        def test_slash_chords(self):
            self.assertEqual(chord_notes("C/E"), ["E3", "C4", "E4", "G4"])
            self.assertEqual(chord_notes("Bb/D"), ["D3", "Bb4", "D5", "F5"])
            self.assertEqual(chord_notes("C/Eb"), ["Eb3", "C4", "E4", "G4"])
            self.assertEqual(chord_notes("Am/G", 3), ["G2", "A3", "C4", "E4"])

        def test_errors(self):
            with self.assertRaises(ValueError):
                chord_notes("Cfoo")


    class Identify(unittest.TestCase):
        def test_triads_and_sevenths(self):
            table = [
                (["C4", "E4", "G4"], "C"), (["A3", "C4", "E4"], "Am"), (["C4", "Eb4", "G4"], "Cm"), (["G3", "B3", "D4", "F4"], "G7"),
                (["C4", "E4", "G4", "B4"], "Cmaj7"), (["A3", "C4", "E4", "G4"], "Am7"), (["B3", "D4", "F4"], "Bdim"),
                (["C4", "E4", "G#4"], "Caug"), (["B3", "D4", "F4", "A4"], "Bm7b5"), (["C4", "D4", "G4"], "Csus2"),
                (["C4", "F4", "G4"], "Csus4"), (["C4", "E4", "G4", "A4"], "C6"), (["D4", "F4", "A4", "B4"], "Dm6"),
            ]
            for notes, want in table:
                self.assertEqual(identify(notes), want, notes)

        def test_spelling(self):
            self.assertEqual(identify(["Eb4", "G4", "Bb4"]), "Eb")
            self.assertEqual(identify(["F#3", "A3", "C#4"]), "F#m")
            self.assertEqual(identify(["Bb3", "D4", "F4", "Ab4"]), "Bb7")
            self.assertEqual(identify(["C#4", "E#4", "G#4"]), "C#")
            self.assertEqual(identify(["C4", "Eb4", "Gb4"]), "Cdim")
            self.assertEqual(identify(["Db4", "F4", "Ab4"]), "Db")
            self.assertEqual(identify(["D4", "F#4", "A4"]), "D")

        def test_inversions_become_slash_chords(self):
            self.assertEqual(identify(["E4", "G4", "C5"]), "C/E")
            self.assertEqual(identify(["G3", "C4", "E4"]), "C/G")
            self.assertEqual(identify(["Bb3", "D4", "G4"]), "Gm/Bb")
            self.assertEqual(identify(["D3", "F#3", "A3", "C4"]), "D7")
            self.assertEqual(identify(["F3", "A3", "C4", "D4"]), "F6")
            self.assertEqual(identify(["D3", "F3", "A3", "C4"]), "Dm7")

        def test_roots_are_tried_in_order_of_appearance(self):
            self.assertEqual(identify(["C4", "E4", "G4", "A4"]), "C6")
            self.assertEqual(identify(["A3", "C4", "E4", "G4"]), "Am7")
            self.assertEqual(identify(["C4", "D4", "G4"]), "Csus2")
            self.assertEqual(identify(["G3", "C4", "D4"]), "Gsus4")
            self.assertEqual(identify(["E4", "G#4", "C5"]), "Eaug")
            self.assertEqual(identify(["C4", "Eb4", "Gb4", "A4"]), "Cdim7")
            self.assertEqual(identify(["Eb4", "Gb4", "A4", "C5"]), "Ebdim7")

        def test_octaves_and_duplicates_do_not_matter(self):
            self.assertEqual(identify(["C", "E", "G"]), "C")
            self.assertEqual(identify(["C4", "C5", "E5", "G5", "G3"]), "C")
            self.assertEqual(identify(["G2", "G3", "B3", "D4", "F4", "B4"]), "G7")
            self.assertEqual(identify(["C3", "E5", "G2"]), "C")

        def test_ninth(self):
            self.assertEqual(identify(["C4", "E4", "G4", "Bb4", "D5"]), "C9")

        def test_no_match(self):
            self.assertIsNone(identify(["C4", "D4"]))
            self.assertIsNone(identify(["C4"]))
            self.assertIsNone(identify(["C4", "C#4", "D4"]))
            self.assertIsNone(identify(["C4", "E4", "G4", "A#4", "D5", "F5"]))

        def test_empty(self):
            with self.assertRaises(ValueError):
                identify([])


    class TransposeChord(unittest.TestCase):
        def test_roots(self):
            table = [
                ("C", 2, "D"), ("Cmaj7", 7, "Gmaj7"), ("Bb7", 2, "C7"), ("Bb", 1, "B"), ("F#m", 1, "Gm"), ("Am", -2, "Gm"),
                ("C", 1, "C#"), ("Eb", 1, "E"), ("C", 12, "C"), ("C", -13, "B"), ("F#m7b5", -1, "Fm7b5"), ("Ab", 3, "B"),
                ("G7", 5, "C7"), ("D", 3, "F"), ("E", 6, "A#"), ("Bbm", 5, "Ebm"), ("Db", 4, "F"), ("A", 3, "C"),
            ]
            for symbol, n, want in table:
                self.assertEqual(transpose_chord(symbol, n), want, (symbol, n))

        def test_sharp_and_flat_tables(self):
            self.assertEqual(transpose_chord("C", 3), "D#")
            self.assertEqual(transpose_chord("Eb", 3), "Gb")
            self.assertEqual(transpose_chord("Bb7", 1), "B7")
            self.assertEqual(transpose_chord("Bb7", 4), "D7")
            self.assertEqual(transpose_chord("Bb7", 8), "Gb7")
            self.assertEqual(transpose_chord("F#", 3), "A")
            self.assertEqual(transpose_chord("F#", 4), "A#")

        def test_slash_chords(self):
            self.assertEqual(transpose_chord("Cm/Eb", 2), "Dm/F")
            self.assertEqual(transpose_chord("C/E", 1), "C#/F")
            self.assertEqual(transpose_chord("C/Bb", 1), "Db/B")
            self.assertEqual(transpose_chord("C/E", 4), "E/G#")
            self.assertEqual(transpose_chord("G/B", -2), "F/A")
            self.assertEqual(transpose_chord("Eb/G", 2), "F/A")
            self.assertEqual(transpose_chord("D/F#", 1), "D#/G")

        def test_errors(self):
            with self.assertRaises(ValueError):
                transpose_chord("Cfoo", 2)


    if __name__ == "__main__":
        unittest.main()
''')

CHORDBOOK = Lib(
    name="chordbook", lang="python", title="the chordbook note and chord package",
    blurb="The lead-sheet editor uses chordbook to transpose chord symbols, list chord tones and name a chord from the notes a player holds.",
    files={
        "chordbook/__init__.py": "", "chordbook/notes.py": CHORDBOOK_NOTES, "chordbook/intervals.py": CHORDBOOK_INTERVALS,
        "chordbook/chords.py": CHORDBOOK_CHORDS, "README.md": CHORDBOOK_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": CHORDBOOK_VISIBLE},
    hidden_tests={
        "tests/test_notes.py": CHORDBOOK_HIDDEN_NOTES, "tests/test_intervals.py": CHORDBOOK_HIDDEN_INTERVALS,
        "tests/test_chords.py": CHORDBOOK_HIDDEN_CHORDS,
    },
    mutate=["chordbook/notes.py", "chordbook/intervals.py", "chordbook/chords.py"],
    difficulty=3, tags=["music", "chords", "multi-module"],
    probes=[
        "midi('B#3')", "midi('Cb4')", "pitch_class('Fb')", "name_of(70)", "name_of(61, 'flat')",
        "transpose('Bb3', 5)", "transpose('F#3', 3, prefer='flat')", "transpose('Bb', 1)", "transpose('C', -1)",
        "interval('C4', 'D5')", "interval('E4', 'C4')", "interval_name(24)", "interval_name(-13)", "class_interval('E', 'C')",
        "parse_chord('Bbm7b5')", "parse_chord('Bm7b5')",
        "chord_notes('F#m7b5')", "chord_notes('Bb9')", "chord_notes('C/E')", "chord_notes('Ebm', 3)",
        "identify(['E4', 'G4', 'C5'])", "identify(['Eb4', 'G4', 'Bb4'])", "identify(['A3', 'C4', 'E4', 'G4'])", "identify(['C4', 'D4', 'G4'])",
        "identify(['E4', 'G#4', 'C5'])",
        "transpose_chord('Cm/Eb', 2)", "transpose_chord('Bb7', 8)", "transpose_chord('C/E', 1)", "transpose_chord('F#m7b5', -1)",
    ],
    probe_import=(
        "from chordbook.notes import midi, pitch_class, name_of, transpose\n"
        "from chordbook.intervals import interval, interval_name, class_interval\n"
        "from chordbook.chords import parse_chord, chord_notes, identify, transpose_chord\n"
    ),
)

LIBS = [GUILDUNITS, AIRLANE, CHORDBOOK]
register_libs3(LIBS, n=10)
