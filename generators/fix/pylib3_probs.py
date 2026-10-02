"""Probabilistic, numeric and text algorithms in domain clothes (python, fix-py-3): seed-catalog Bloom filter, plate heat solver, recommendations, token diff, command palette."""
from fx import Lib, dd

from generators.fix._pylib3 import chain, register_libs3

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# seedfilter: a Bloom filter with two named hash functions
# ======================================================================================================================

SEEDFILTER_README = dd('''
    # seedfilter

    A Bloom filter that a seed-library catalogue uses to remember which packet codes it has already seen.

    ## Hash functions

    * `fnv1a(text) -> int`: 32-bit FNV-1a over the UTF-8 bytes: `h = 2166136261`; for each byte `h ^= byte` then
      `h = (h * 16777619) mod 2**32` (`fnv1a("a") == 3826002220`).
    * `djb2(text) -> int`: `h = 5381`; for each UTF-8 byte `h = (h * 33 + byte) mod 2**32` (`djb2("") == 5381`,
      `djb2("a") == 177670`).

    ## `BloomFilter(bits, hashes)`

    `bits` and `hashes` are positive integers (`ValueError` otherwise; they are kept as the attributes `bits` and `hashes`).
    The filter owns a bit array of `bits` bits, all clear at the start.

    * `positions(item) -> list[int]`: the `hashes` bit positions of an item (a string) by double hashing:
      with `h1 = fnv1a(item)` and `h2 = djb2(item) | 1` (the lowest bit forced to one) position `i` (from 0) is
      `(h1 + i * h2) mod bits`. Positions may repeat.
    * `add(item)`: set the bits of `positions(item)`. `item in bloom` / `might_contain(item)`: all those bits are set.
    * `count_bits() -> int`: how many bits are set; `fill_pct() -> int`: `100 * count_bits // bits` (rounded down).
    * `union(other) -> BloomFilter`: a new filter whose bit array is the bitwise OR of both; `ValueError` unless both
      have the same `bits` and `hashes`. Neither input changes.
    * `to_hex() -> str`: the bit array as lower-case hex of `ceil(bits / 8)` bytes, byte `b` holding bits `8b .. 8b+7`
      with bit `8b + j` as the value `2**j` of the byte; `BloomFilter.from_hex(text, bits, hashes)` is the inverse and
      raises `ValueError` when the text is not hex of exactly that many bytes or has a bit set at a position `>= bits`.

    ## Sizing

    * `optimal_bits(items, error_rate) -> int`: `ceil(-items * ln(error_rate) / (ln 2) ** 2)`;
      `optimal_hashes(bits, items) -> int`: `round(bits / items * ln 2)`, at least 1. `items` must be positive and
      `error_rate` strictly between 0 and 1, otherwise `ValueError`. `BloomFilter.for_capacity(items, error_rate)`
      builds a filter with those two numbers.
''')

SEEDFILTER_SRC = dd('''
    """A Bloom filter with double hashing."""
    import math


    def fnv1a(text):
        h = 2166136261
        for byte in text.encode("utf-8"):
            h ^= byte
            h = (h * 16777619) % 2 ** 32
        return h


    def djb2(text):
        h = 5381
        for byte in text.encode("utf-8"):
            h = (h * 33 + byte) % 2 ** 32
        return h


    def optimal_bits(items, error_rate):
        if items < 1 or not 0 < error_rate < 1:
            raise ValueError("items must be positive and error_rate between 0 and 1")
        return math.ceil(-items * math.log(error_rate) / math.log(2) ** 2)


    def optimal_hashes(bits, items):
        if items < 1 or bits < 1:
            raise ValueError("bits and items must be positive")
        return max(1, round(bits / items * math.log(2)))


    class BloomFilter:
        def __init__(self, bits, hashes):
            if bits < 1 or hashes < 1:
                raise ValueError("bits and hashes must be positive")
            self.bits = bits
            self.hashes = hashes
            self._array = 0

        @classmethod
        def for_capacity(cls, items, error_rate):
            bits = optimal_bits(items, error_rate)
            return cls(bits, optimal_hashes(bits, items))

        def positions(self, item):
            h1, h2 = fnv1a(item), djb2(item) | 1
            return [(h1 + i * h2) % self.bits for i in range(self.hashes)]

        def add(self, item):
            for pos in self.positions(item):
                self._array |= 1 << pos

        def might_contain(self, item):
            return all(self._array >> pos & 1 for pos in self.positions(item))

        __contains__ = might_contain

        def count_bits(self):
            return bin(self._array).count("1")

        def fill_pct(self):
            return 100 * self.count_bits() // self.bits

        def union(self, other):
            if (self.bits, self.hashes) != (other.bits, other.hashes):
                raise ValueError("filters differ in size")
            out = BloomFilter(self.bits, self.hashes)
            out._array = self._array | other._array
            return out

        def to_hex(self):
            return self._array.to_bytes((self.bits + 7) // 8, "little").hex()

        @classmethod
        def from_hex(cls, text, bits, hashes):
            out = cls(bits, hashes)
            try:
                raw = bytes.fromhex(text)
            except ValueError:
                raise ValueError("not hex") from None
            if len(raw) != (bits + 7) // 8 or text != text.lower():
                raise ValueError("wrong length")
            value = int.from_bytes(raw, "little")
            if value >> bits:
                raise ValueError("bits beyond the end are set")
            out._array = value
            return out
''')

SEEDFILTER_VISIBLE = dd('''
    import unittest

    from seedfilter.bloom import BloomFilter, fnv1a


    class BasicTests(unittest.TestCase):
        def test_hash_vector(self):
            self.assertEqual(fnv1a("a"), 3826002220)

        def test_membership(self):
            b = BloomFilter(256, 3)
            b.add("tomato-17")
            self.assertIn("tomato-17", b)


    if __name__ == "__main__":
        unittest.main()
''')

SEEDFILTER_HIDDEN = dd('''
    import unittest

    from seedfilter.bloom import BloomFilter, djb2, fnv1a, optimal_bits, optimal_hashes


    class Hashes(unittest.TestCase):
        def test_fnv1a(self):
            self.assertEqual(fnv1a(""), 2166136261)
            self.assertEqual(fnv1a("a"), 3826002220)
            self.assertEqual(fnv1a("foobar"), 3214735720)

        def test_djb2(self):
            self.assertEqual(djb2(""), 5381)
            self.assertEqual(djb2("a"), 177670)
            self.assertEqual(djb2("ab"), 5863208)
            self.assertEqual(djb2("abc"), (5863208 * 33 + 99))

        def test_djb2_wraps_at_32_bits(self):
            h = 5381
            for ch in "x" * 40:
                h = (h * 33 + ord(ch)) % 2 ** 32
            self.assertEqual(djb2("x" * 40), h)
            self.assertTrue(0 <= djb2("x" * 40) < 2 ** 32)

        def test_many_strings_stay_in_32_bits_and_match_the_definition(self):
            for i in range(40):
                text = f"seed-packet-{i}-" + "z" * i
                h = 5381
                for byte in text.encode("utf-8"):
                    h = (h * 33 + byte) % 2 ** 32
                self.assertEqual(djb2(text), h)
                f = 2166136261
                for byte in text.encode("utf-8"):
                    f = ((f ^ byte) * 16777619) % 2 ** 32
                self.assertEqual(fnv1a(text), f)

        def test_unicode_uses_utf8_bytes(self):
            h = 2166136261
            for byte in (0xC3, 0xA9):
                h = ((h ^ byte) * 16777619) % 2 ** 32
            self.assertEqual(fnv1a("\\u00e9"), h)
            self.assertEqual(djb2("\\u00e9"), (5381 * 33 + 0xC3) * 33 + 0xA9)


    class Positions(unittest.TestCase):
        def test_double_hashing(self):
            b = BloomFilter(64, 3)
            self.assertEqual(b.positions("a"), [44, 51, 58])
            self.assertEqual(BloomFilter(64, 5).positions("a"), [44, 51, 58, 1, 8])

        def test_h2_is_forced_odd(self):
            # djb2("a") = 177670 is even: the step is 177671, not 177670
            b = BloomFilter(1000, 2)
            self.assertEqual(b.positions("a"), [3826002220 % 1000, (3826002220 + 177671) % 1000])
            # djb2("ab") = 5863208 is even too; djb2("abc") is odd and stays as it is
            self.assertEqual(BloomFilter(1000, 2).positions("abc")[1], (fnv1a("abc") + (djb2("abc") | 1)) % 1000)
            self.assertEqual(djb2("abc") % 2, 1)

        def test_formula(self):
            for bits in (7, 100, 1024, 4093):
                b = BloomFilter(bits, 4)
                for item in ("tomato", "bean-01", "z", "kale/curly"):
                    h1, h2 = fnv1a(item), djb2(item) | 1
                    self.assertEqual(b.positions(item), [(h1 + i * h2) % bits for i in range(4)])

        def test_positions_stay_in_range(self):
            b = BloomFilter(10, 8)
            for item in ("a", "b", "carrot", "x" * 50):
                self.assertTrue(all(0 <= p < 10 for p in b.positions(item)))
                self.assertEqual(len(b.positions(item)), 8)


    class Membership(unittest.TestCase):
        def test_add_and_contains(self):
            b = BloomFilter(512, 3)
            self.assertNotIn("kale", b)
            self.assertFalse(b.might_contain("kale"))
            b.add("kale")
            self.assertIn("kale", b)
            self.assertTrue(b.might_contain("kale"))
            self.assertEqual(b.count_bits(), len(set(b.positions("kale"))))

        def test_no_false_negatives(self):
            b = BloomFilter(2048, 4)
            items = [f"packet-{i}" for i in range(100)]
            for item in items:
                b.add(item)
            for item in items:
                self.assertIn(item, b)
            misses = sum(1 for i in range(100, 300) if f"packet-{i}" in b)
            self.assertLess(misses, 60)

        def test_empty_filter_contains_nothing(self):
            b = BloomFilter(128, 2)
            for item in ("", "a", "b"):
                self.assertNotIn(item, b)

        def test_bit_counts(self):
            b = BloomFilter(64, 3)
            self.assertEqual((b.count_bits(), b.fill_pct()), (0, 0))
            b.add("a")
            self.assertEqual(b.count_bits(), 3)
            self.assertEqual(b.fill_pct(), 4)        # 300 // 64
            b.add("a")
            self.assertEqual(b.count_bits(), 3)

        def test_fill_pct_rounds_down(self):
            self.assertEqual(BloomFilter.from_hex("05", 3, 1).fill_pct(), 66)
            self.assertEqual(BloomFilter.from_hex("ff", 8, 1).fill_pct(), 100)
            self.assertEqual(BloomFilter.from_hex("01", 8, 1).fill_pct(), 12)

        def test_validation(self):
            for args in ((0, 3), (-1, 3), (8, 0), (8, -2)):
                with self.assertRaises(ValueError):
                    BloomFilter(*args)


    class Union(unittest.TestCase):
        def test_union(self):
            a, b = BloomFilter(256, 3), BloomFilter(256, 3)
            a.add("alpha")
            b.add("beta")
            u = a.union(b)
            self.assertIn("alpha", u)
            self.assertIn("beta", u)
            self.assertNotIn("gamma", u)
            self.assertNotIn("beta", a)
            self.assertNotIn("alpha", b)
            self.assertIsNot(u, a)
            self.assertEqual(u.count_bits(), len(set(a.positions("alpha")) | set(a.positions("beta"))))
            u.add("delta")
            self.assertNotIn("delta", a)

        def test_union_needs_equal_parameters(self):
            with self.assertRaises(ValueError):
                BloomFilter(64, 3).union(BloomFilter(65, 3))
            with self.assertRaises(ValueError):
                BloomFilter(64, 3).union(BloomFilter(64, 4))


    class Hex(unittest.TestCase):
        def test_to_hex(self):
            b = BloomFilter(64, 3)
            b.add("a")
            self.assertEqual(b.to_hex(), "0000000000100804")      # bits 44, 51 and 58

        def test_hex_layout(self):
            self.assertEqual(BloomFilter(8, 1).to_hex(), "00")
            self.assertEqual(BloomFilter(9, 1).to_hex(), "0000")
            self.assertEqual(BloomFilter(1, 1).to_hex(), "00")
            self.assertEqual(BloomFilter(20, 1).to_hex(), "000000")
            for text in ("010000", "000200", "000008", "debc0a", "ffff0f"):
                self.assertEqual(BloomFilter.from_hex(text, 20, 1).to_hex(), text)
            self.assertEqual(BloomFilter.from_hex("010000", 20, 1).count_bits(), 1)
            self.assertEqual(BloomFilter.from_hex("000008", 20, 1).count_bits(), 1)
            self.assertEqual(BloomFilter.from_hex("debc0a", 20, 1).count_bits(), bin(0x0ABCDE).count("1"))

        def test_round_trip(self):
            b = BloomFilter(100, 3)
            for item in ("a", "bb", "ccc", "tomato"):
                b.add(item)
            c = BloomFilter.from_hex(b.to_hex(), 100, 3)
            self.assertEqual(c.to_hex(), b.to_hex())
            for item in ("a", "bb", "ccc", "tomato"):
                self.assertIn(item, c)
            self.assertEqual(c.count_bits(), b.count_bits())
            self.assertEqual((c.bits, c.hashes), (100, 3))

        def test_from_hex_errors(self):
            for text in ("zz", "0", "00", "0000000", "00000000000000000000", "FF" + "00" * 12, "0g" + "00" * 12):
                with self.assertRaises(ValueError, msg=text):
                    BloomFilter.from_hex(text, 100, 3)
            BloomFilter.from_hex("00" * 13, 100, 3)
            BloomFilter.from_hex("0000", 9, 1)
            with self.assertRaises(ValueError):
                BloomFilter.from_hex("00", 9, 1)
            with self.assertRaises(ValueError):
                BloomFilter.from_hex("0000", 8, 1)
            with self.assertRaises(ValueError):
                BloomFilter.from_hex("00" * 12 + "10", 100, 3)      # bit 100 is set
            BloomFilter.from_hex("00" * 12 + "08", 100, 3)          # bit 99 is fine
            with self.assertRaises(ValueError):
                BloomFilter.from_hex("00", 0, 3)


    class Sizing(unittest.TestCase):
        def test_optimal_bits(self):
            self.assertEqual(optimal_bits(1000, 0.01), 9586)
            self.assertEqual(optimal_bits(100, 0.001), 1438)
            self.assertEqual(optimal_bits(10, 0.5), 15)
            self.assertEqual(optimal_bits(1, 0.5), 2)
            self.assertEqual(optimal_bits(5000, 0.05), 31177)

        def test_optimal_hashes(self):
            self.assertEqual(optimal_hashes(9586, 1000), 7)
            self.assertEqual(optimal_hashes(1438, 100), 10)
            self.assertEqual(optimal_hashes(15, 10), 1)
            self.assertEqual(optimal_hashes(1, 100), 1)
            self.assertEqual(optimal_hashes(20, 10), 1)
            self.assertEqual(optimal_hashes(21, 10), 1)
            self.assertEqual(optimal_hashes(25, 10), 2)
            self.assertEqual(optimal_hashes(1, 1), 1)
            self.assertEqual(optimal_hashes(30, 1), 21)

        def test_for_capacity(self):
            b = BloomFilter.for_capacity(1000, 0.01)
            self.assertEqual((b.bits, b.hashes), (9586, 7))
            b = BloomFilter.for_capacity(100, 0.001)
            self.assertEqual((b.bits, b.hashes), (1438, 10))

        def test_errors(self):
            for args in ((0, 0.01), (-5, 0.01), (10, 0), (10, 1), (10, 1.5), (10, -0.1)):
                with self.assertRaises(ValueError):
                    optimal_bits(*args)
            for args in ((0, 10), (10, 0), (-1, 10)):
                with self.assertRaises(ValueError):
                    optimal_hashes(*args)


    if __name__ == "__main__":
        unittest.main()
''')

SEEDFILTER = Lib(
    name="seedfilter", lang="python", title="the seedfilter Bloom filter (`seedfilter/bloom.py`)",
    blurb="The seed library's catalogue uses seedfilter to remember which packet codes it has already seen without storing them all.",
    files={"seedfilter/__init__.py": "", "seedfilter/bloom.py": SEEDFILTER_SRC, "README.md": SEEDFILTER_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": SEEDFILTER_VISIBLE},
    hidden_tests={"tests/test_full.py": SEEDFILTER_HIDDEN},
    mutate=["seedfilter/bloom.py"], difficulty=1, tags=["bloom-filter", "hashing"],
    probes=[
        "fnv1a('foobar')", "djb2('ab')",
        "BloomFilter(64, 5).positions('a')", "BloomFilter(1000, 2).positions('tomato')",
        chain("BloomFilter(64, 3)", ["add('a')", "count_bits()", "fill_pct()", "to_hex()"]),
        "optimal_bits(1000, 0.01)", "optimal_bits(10, 0.5)", "optimal_hashes(9586, 1000)", "optimal_hashes(1, 100)",
        "BloomFilter.for_capacity(100, 0.001).hashes",
        "BloomFilter.from_hex('00' * 13, 100, 3).bits",
        "BloomFilter(20, 1).union(BloomFilter(20, 1)).to_hex()",
    ],
    probe_import="from seedfilter.bloom import BloomFilter, fnv1a, djb2, optimal_bits, optimal_hashes\n",
)

# ======================================================================================================================
# plateheat: exact conjugate gradients for a heated plate (multi-module)
# ======================================================================================================================

PLATEHEAT_README = dd('''
    # plateheat

    Steady-state heat on a rectangular plate whose edges are held at zero, solved exactly with fractions and a
    *matrix-free* conjugate-gradient solver (the matrix is never built, only a function that multiplies by it).

    ## `plateheat.cg`

    * `dot(u, v) -> Fraction`: the inner product (`Fraction(0)` for empty vectors).
    * `axpy(alpha, x, y) -> list`: `alpha * x + y` element by element.
    * `conjugate_gradient(apply, b, max_iter=None) -> (x, iterations)`: solve `A x = b` where `apply(v)` returns `A v`
      as a list and `A` is symmetric positive definite. Everything is computed with `Fraction`s, so the result is
      exact. Start with `x = 0`, `r = b`, `p = r`, `rs = dot(r, r)`. While `rs != 0` and fewer than `limit`
      iterations were made (`limit` is `len(b)` when `max_iter` is `None`, else `max_iter`): `ap = apply(p)`,
      `alpha = rs / dot(p, ap)`, `x = x + alpha p`, `r = r - alpha ap`, `rs_new = dot(r, r)`,
      `p = r + (rs_new / rs) p`, `rs = rs_new`, one more iteration counted. Returns the vector `x` (a list of
      `Fraction`s) and the number of iterations made. A zero right-hand side needs no iteration; for a symmetric
      positive definite operator exact arithmetic reaches `rs == 0` after at most `len(b)` iterations.
    * `residual2(apply, x, b) -> Fraction`: `dot(r, r)` with `r = b - apply(x)`.

    ## `plateheat.plate`

    * `plate_operator(width, height) -> function`: the 5-point operator on a `height` rows by `width` columns plate
      stored as one list in row-major order: `(A x)[r][c] = 4 * x[r][c]` minus the values of the (up to four) existing
      neighbours left, right, above and below; there are no cells beyond the edge (the edges are cold).
    * `solve_plate(width, height, heat) -> list[list[Fraction]]`: `heat` is a list of `height` rows of `width` numbers
      (the heat source in every cell); the result has the same shape and satisfies `A x = heat` exactly. `ValueError`
      for `width < 1`, `height < 1` or a `heat` of the wrong shape.
    * `hottest(grid) -> (value, (row, col))`: the largest value; ties go to the first cell in row-major order.
    * `format_grid(grid, places=2) -> str`: every value with exactly `places` decimals, rounded half away from zero
      (no minus sign for a value that rounds to zero), each right-aligned to the width of the widest cell, the cells of
      a row separated by one space and the rows joined with `"\\n"`.
''')

PLATEHEAT_CG = dd('''
    """Exact conjugate gradients with a matrix-free operator."""
    from fractions import Fraction


    def dot(u, v):
        return sum((a * b for a, b in zip(u, v)), Fraction(0))


    def axpy(alpha, x, y):
        return [alpha * a + b for a, b in zip(x, y)]


    def residual2(apply, x, b):
        r = axpy(-1, apply(x), b)
        return dot(r, r)


    def conjugate_gradient(apply, b, max_iter=None):
        n = len(b)
        x = [Fraction(0)] * n
        r = [Fraction(v) for v in b]
        p = list(r)
        rs = dot(r, r)
        limit = n if max_iter is None else max_iter
        done = 0
        while rs != 0 and done < limit:
            ap = apply(p)
            alpha = rs / dot(p, ap)
            x = axpy(alpha, p, x)
            r = axpy(-alpha, ap, r)
            rs_new = dot(r, r)
            p = axpy(rs_new / rs, p, r)
            rs = rs_new
            done += 1
        return x, done
''')

PLATEHEAT_PLATE = dd('''
    """The heated plate."""
    from fractions import Fraction

    from .cg import conjugate_gradient


    def plate_operator(width, height):
        def apply(x):
            out = []
            for r in range(height):
                for c in range(width):
                    value = 4 * x[r * width + c]
                    if c > 0:
                        value -= x[r * width + c - 1]
                    if c < width - 1:
                        value -= x[r * width + c + 1]
                    if r > 0:
                        value -= x[(r - 1) * width + c]
                    if r < height - 1:
                        value -= x[(r + 1) * width + c]
                    out.append(value)
            return out

        return apply


    def solve_plate(width, height, heat):
        if width < 1 or height < 1 or len(heat) != height or any(len(row) != width for row in heat):
            raise ValueError("heat must have height rows of width numbers")
        flat = [Fraction(v) for row in heat for v in row]
        x, _ = conjugate_gradient(plate_operator(width, height), flat)
        return [x[r * width:(r + 1) * width] for r in range(height)]


    def hottest(grid):
        best, where = None, None
        for r, row in enumerate(grid):
            for c, v in enumerate(row):
                if best is None or v > best:
                    best, where = v, (r, c)
        return best, where


    def _fixed(value, places):
        value = Fraction(value)
        scale = 10 ** places
        scaled = abs(value) * scale
        whole = int(scaled)
        if scaled - whole >= Fraction(1, 2):
            whole += 1
        sign = "-" if value < 0 and whole else ""
        if places == 0:
            return f"{sign}{whole}"
        return f"{sign}{whole // scale}.{whole % scale:0{places}d}"


    def format_grid(grid, places=2):
        cells = [[_fixed(v, places) for v in row] for row in grid]
        width = max((len(c) for row in cells for c in row), default=0)
        return "\\n".join(" ".join(c.rjust(width) for c in row) for row in cells)
''')

PLATEHEAT_VISIBLE = dd('''
    import unittest
    from fractions import Fraction as F

    from plateheat.cg import dot
    from plateheat.plate import solve_plate


    class BasicTests(unittest.TestCase):
        def test_dot(self):
            self.assertEqual(dot([1, 2, 3], [4, 5, 6]), 32)

        def test_single_cell(self):
            self.assertEqual(solve_plate(1, 1, [[8]]), [[F(2)]])


    if __name__ == "__main__":
        unittest.main()
''')

PLATEHEAT_HIDDEN_CG = dd('''
    import unittest
    from fractions import Fraction as F

    from plateheat.cg import axpy, conjugate_gradient, dot, residual2


    def diag(*d):
        return lambda v: [a * b for a, b in zip(d, v)]


    def tridiag(v):
        n = len(v)
        return [2 * v[i] - (v[i - 1] if i else 0) - (v[i + 1] if i < n - 1 else 0) for i in range(n)]


    class Vectors(unittest.TestCase):
        def test_dot(self):
            self.assertEqual(dot([1, 2, 3], [4, 5, 6]), 32)
            self.assertEqual(dot([], []), 0)
            self.assertEqual(dot([F(1, 2), F(1, 3)], [4, 6]), 4)
            self.assertIsInstance(dot([1], [1]), F)
            self.assertIsInstance(dot([], []), F)
            self.assertEqual(dot([1, 2], [3, 4, 5]), 11)

        def test_axpy(self):
            self.assertEqual(axpy(2, [1, 2], [10, 20]), [12, 24])
            self.assertEqual(axpy(-1, [1, 2], [1, 2]), [0, 0])
            self.assertEqual(axpy(F(1, 2), [4, 6], [1, 1]), [3, 4])
            self.assertEqual(axpy(0, [4, 6], [1, 1]), [1, 1])
            self.assertEqual(axpy(3, [], []), [])

        def test_residual2(self):
            a = diag(2, 3)
            self.assertEqual(residual2(a, [2, 3], [4, 9]), 0)
            self.assertEqual(residual2(a, [0, 0], [4, 9]), 97)
            self.assertEqual(residual2(a, [1, 1], [4, 9]), 4 + 36)
            self.assertEqual(residual2(a, [F(7, 4), 3], [4, 9]), F(1, 4))


    class Solver(unittest.TestCase):
        def test_identity_takes_one_iteration(self):
            x, it = conjugate_gradient(lambda v: list(v), [1, 2, 3])
            self.assertEqual(x, [1, 2, 3])
            self.assertEqual(it, 1)
            self.assertTrue(all(isinstance(v, F) for v in x))

        def test_zero_rhs(self):
            x, it = conjugate_gradient(tridiag, [0, 0, 0])
            self.assertEqual((x, it), ([0, 0, 0], 0))
            self.assertEqual(conjugate_gradient(tridiag, []), ([], 0))

        def test_diagonal_two_eigenvalues(self):
            x, it = conjugate_gradient(diag(2, 3), [4, 9])
            self.assertEqual(x, [2, 3])
            self.assertEqual(it, 2)

        def test_eigenvector_converges_at_once(self):
            x, it = conjugate_gradient(tridiag, [1, 0, -1])      # an eigenvector with eigenvalue 2
            self.assertEqual(x, [F(1, 2), 0, F(-1, 2)])
            self.assertEqual(it, 1)

        def test_two_eigenvalues_take_two_iterations(self):
            x, it = conjugate_gradient(tridiag, [1, 0, 1])
            self.assertEqual(x, [1, 1, 1])
            self.assertEqual(it, 2)

        def test_tridiagonal(self):
            x, it = conjugate_gradient(tridiag, [1, 0, 0])
            self.assertEqual(x, [F(3, 4), F(1, 2), F(1, 4)])
            self.assertLessEqual(it, 3)
            self.assertEqual(residual2(tridiag, x, [1, 0, 0]), 0)

        def test_exact_for_many_right_hand_sides(self):
            for b in ([1, 2, 3, 4], [5, -3, 0, 7], [0, 0, 0, 1], [F(1, 3), F(-2, 7), 1, 5], [9, 9, 9, 9]):
                x, it = conjugate_gradient(tridiag, b)
                self.assertEqual(tridiag(x), [F(v) for v in b], b)
                self.assertLessEqual(it, 4)

        def test_max_iter(self):
            x, it = conjugate_gradient(diag(2, 3), [4, 9], max_iter=1)
            self.assertEqual((x, it), ([F(388, 275), F(873, 275)], 1))
            x, it = conjugate_gradient(diag(2, 3), [4, 9], max_iter=0)
            self.assertEqual((x, it), ([0, 0], 0))
            x, it = conjugate_gradient(diag(2, 3), [4, 9], max_iter=50)
            self.assertEqual((x, it), ([2, 3], 2))

        def test_default_limit_is_the_dimension(self):
            calls = []

            def counting(v):
                calls.append(1)
                return tridiag(v)

            conjugate_gradient(counting, [1, 2, 3, 4, 5])
            self.assertLessEqual(len(calls), 5)

        def test_input_is_not_modified(self):
            b = [1, 2, 3]
            conjugate_gradient(tridiag, b)
            self.assertEqual(b, [1, 2, 3])


    if __name__ == "__main__":
        unittest.main()
''')

PLATEHEAT_HIDDEN_PLATE = dd('''
    import unittest
    from fractions import Fraction as F

    from plateheat.cg import residual2
    from plateheat.plate import format_grid, hottest, plate_operator, solve_plate


    class Operator(unittest.TestCase):
        def test_single_cell(self):
            self.assertEqual(plate_operator(1, 1)([5]), [20])

        def test_two_cells(self):
            a = plate_operator(2, 1)
            self.assertEqual(a([1, 0]), [4, -1])
            self.assertEqual(a([0, 1]), [-1, 4])
            self.assertEqual(plate_operator(1, 2)([1, 0]), [4, -1])

        def test_two_by_two(self):
            a = plate_operator(2, 2)
            self.assertEqual(a([1, 0, 0, 0]), [4, -1, -1, 0])
            self.assertEqual(a([1, 1, 1, 1]), [2, 2, 2, 2])

        def test_three_by_three_centre(self):
            a = plate_operator(3, 3)
            out = a([0, 0, 0, 0, 1, 0, 0, 0, 0])
            self.assertEqual(out, [0, -1, 0, -1, 4, -1, 0, -1, 0])
            corner = a([1, 0, 0, 0, 0, 0, 0, 0, 0])
            self.assertEqual(corner, [4, -1, 0, -1, 0, 0, 0, 0, 0])

        def test_non_square(self):
            a = plate_operator(3, 2)
            self.assertEqual(a([0, 1, 0, 0, 0, 0]), [-1, 4, -1, 0, -1, 0])
            self.assertEqual(a([0, 0, 0, 0, 1, 0]), [0, -1, 0, -1, 4, -1])
            b = plate_operator(2, 3)
            self.assertEqual(b([0, 0, 1, 0, 0, 0]), [-1, 0, 4, -1, -1, 0])

        def test_symmetry(self):
            import random
            rng = random.Random(5)
            a = plate_operator(4, 3)
            for _ in range(5):
                u = [rng.randint(-5, 5) for _ in range(12)]
                v = [rng.randint(-5, 5) for _ in range(12)]
                self.assertEqual(sum(x * y for x, y in zip(u, a(v))), sum(x * y for x, y in zip(a(u), v)))


    class Solve(unittest.TestCase):
        def test_single_cell(self):
            self.assertEqual(solve_plate(1, 1, [[8]]), [[2]])
            self.assertEqual(solve_plate(1, 1, [[1]]), [[F(1, 4)]])

        def test_two_cells(self):
            self.assertEqual(solve_plate(2, 1, [[1, 0]]), [[F(4, 15), F(1, 15)]])
            self.assertEqual(solve_plate(2, 1, [[1, 1]]), [[F(1, 3), F(1, 3)]])
            self.assertEqual(solve_plate(1, 2, [[0], [1]]), [[F(1, 15)], [F(4, 15)]])

        def test_two_by_two(self):
            self.assertEqual(solve_plate(2, 2, [[1, 1], [1, 1]]), [[F(1, 2), F(1, 2)], [F(1, 2), F(1, 2)]])
            self.assertEqual(solve_plate(2, 2, [[1, 0], [0, 0]]), [[F(7, 24), F(1, 12)], [F(1, 12), F(1, 24)]])

        def test_shape_and_residual(self):
            heat = [[1, 0, 2, 5], [0, 3, 0, 1], [4, 0, 0, 7]]
            grid = solve_plate(4, 3, heat)
            self.assertEqual([len(r) for r in grid], [4, 4, 4])
            self.assertEqual(len(grid), 3)
            flat = [v for row in grid for v in row]
            applied = plate_operator(4, 3)(flat)
            self.assertEqual(applied, [F(v) for row in heat for v in row])
            self.assertEqual(residual2(plate_operator(4, 3), flat, [v for row in heat for v in row]), 0)

        def test_rectangular_plates(self):
            for width, height in ((5, 1), (1, 5), (3, 4), (4, 3)):
                heat = [[(r * 3 + c * 7) % 5 - 2 for c in range(width)] for r in range(height)]
                grid = solve_plate(width, height, heat)
                flat = [v for row in grid for v in row]
                self.assertEqual(plate_operator(width, height)(flat), [F(v) for row in heat for v in row], (width, height))

        def test_zero_heat(self):
            self.assertEqual(solve_plate(2, 2, [[0, 0], [0, 0]]), [[0, 0], [0, 0]])

        def test_validation(self):
            for args in ((0, 1, [[]]), (1, 0, []), (2, 2, [[1, 2]]), (2, 1, [[1, 2], [3, 4]]), (2, 1, [[1]]), (2, 2, [[1, 2], [3]]), (-1, 1, [[1]])):
                with self.assertRaises(ValueError, msg=str(args)):
                    solve_plate(*args)

        def test_heat_input_is_not_modified(self):
            heat = [[1, 0], [0, 2]]
            solve_plate(2, 2, heat)
            self.assertEqual(heat, [[1, 0], [0, 2]])


    class Reporting(unittest.TestCase):
        def test_hottest(self):
            self.assertEqual(hottest([[1, 5], [5, 2]]), (5, (0, 1)))
            self.assertEqual(hottest([[F(1, 2), F(1, 3)], [F(2, 3), F(3, 5)]]), (F(2, 3), (1, 0)))
            self.assertEqual(hottest([[-3, -1, -2]]), (-1, (0, 1)))
            self.assertEqual(hottest([[4]]), (4, (0, 0)))
            self.assertEqual(hottest([[0, 0], [0, 0]]), (0, (0, 0)))
            self.assertEqual(hottest([[1], [3], [2]]), (3, (1, 0)))

        def test_format(self):
            grid = [[F(7, 24), F(1, 12)], [F(1, 12), F(1, 24)]]
            self.assertEqual(format_grid(grid), "0.29 0.08\\n0.08 0.04")
            self.assertEqual(format_grid(grid, 3), "0.292 0.083\\n0.083 0.042")
            self.assertEqual(format_grid(grid, 0), "0 0\\n0 0")
            self.assertEqual(format_grid([[F(10), F(5, 2)]], 1), "10.0  2.5")
            self.assertEqual(format_grid([[F(1, 2), F(-1, 2)], [F(3, 2), F(-5, 2)]], 0), " 1 -1\\n 2 -3")

        def test_format_rounding_and_signs(self):
            self.assertEqual(format_grid([[F(1, 8)]], 2), "0.13")
            self.assertEqual(format_grid([[F(-1, 8)]], 2), "-0.13")
            self.assertEqual(format_grid([[F(-1, 300)]], 2), "0.00")
            self.assertEqual(format_grid([[F(0)]], 1), "0.0")
            self.assertEqual(format_grid([[3]], 2), "3.00")
            self.assertEqual(format_grid([[F(999, 1000)]], 2), "1.00")

        def test_format_alignment(self):
            self.assertEqual(format_grid([[F(1), F(100)], [F(25), F(3)]], 0), "  1 100\\n 25   3")
            self.assertEqual(format_grid([[F(1)]], 0), "1")
            self.assertEqual(format_grid([], 2), "")


    if __name__ == "__main__":
        unittest.main()
''')

PLATEHEAT = Lib(
    name="plateheat", lang="python", title="the plateheat solver",
    blurb="The greenhouse engineers use plateheat to predict how the heat from a few pipes spreads over a cold concrete floor.",
    files={
        "plateheat/__init__.py": "", "plateheat/cg.py": PLATEHEAT_CG, "plateheat/plate.py": PLATEHEAT_PLATE,
        "README.md": PLATEHEAT_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": PLATEHEAT_VISIBLE},
    hidden_tests={"tests/test_cg.py": PLATEHEAT_HIDDEN_CG, "tests/test_plate.py": PLATEHEAT_HIDDEN_PLATE},
    mutate=["plateheat/cg.py", "plateheat/plate.py"],
    difficulty=3, tags=["numeric", "linear-algebra", "multi-module"],
    probes=[
        "dot([1, 2, 3], [4, 5, 6])", "axpy(2, [1, 2], [10, 20])",
        "conjugate_gradient(lambda v: [2 * v[0], 3 * v[1]], [4, 9])",
        "conjugate_gradient(lambda v: [2 * v[0], 3 * v[1]], [4, 9], max_iter=1)",
        "conjugate_gradient(lambda v: list(v), [1, 2, 3])[1]",
        "plate_operator(3, 2)([0, 1, 0, 0, 0, 0])",
        "plate_operator(2, 2)([1, 0, 0, 0])",
        "solve_plate(2, 1, [[1, 0]])", "solve_plate(2, 2, [[1, 0], [0, 0]])", "solve_plate(1, 2, [[0], [1]])",
        "hottest([[1, 5], [5, 2]])", "format_grid([[Fraction(7, 24), Fraction(1, 12)], [Fraction(1, 12), Fraction(1, 24)]])",
        "format_grid([[Fraction(1, 2), Fraction(-1, 2)], [Fraction(3, 2), Fraction(-5, 2)]], 0)",
    ],
    probe_import="from fractions import Fraction\nfrom plateheat.cg import dot, axpy, conjugate_gradient\nfrom plateheat.plate import plate_operator, solve_plate, hottest, format_grid\n",
)

# ======================================================================================================================
# alsobought: "customers also bought" with recency weights and a category cap
# ======================================================================================================================

ALSOBOUGHT_README = dd('''
    # alsobought

    Item-to-item recommendations for a bookshop's checkout page, computed from past baskets. All numbers are exact
    `fractions.Fraction`s.

    ## `weight(age_days, half_life=30) -> Fraction`

    How much a basket still counts: `1 / 2 ** (age_days // half_life)` (whole half-lives only, so a basket that is
    29 days old counts fully). `ValueError` if `age_days < 0` or `half_life < 1`.

    ## `Model(baskets, today, half_life=30, categories=None)`

    `baskets` is a list of `(day, items)` pairs: the day number of the purchase and the collection of item names bought
    together. A basket's weight is `weight(today - day, half_life)`; a basket from the future (`day > today`) is a
    `ValueError`. Duplicate items in a basket count once and an empty basket changes nothing. `categories` maps an item
    to a category name (items without an entry have no category).

    * `single(item) -> Fraction`: the summed weight of the baskets containing the item (`0` for an unknown item).
    * `pair(a, b) -> Fraction`: the summed weight of the baskets containing both items (`0` when `a == b` is
      not asked: `pair(a, a)` is `single(a)`).
    * `similarity(a, b) -> Fraction`: the weighted Jaccard index `pair / (single(a) + single(b) - pair)`; `0` when the
      items never occur together (`similarity(a, a)` is `1` for a known item and `0` for an unknown one).
    * `recommend(history, k, max_per_category=None) -> list[(item, score)]`: for every known item that is not in
      `history` the score is the sum of `similarity(h, item)` over the history items `h`; items with a score of `0`
      are dropped. Sort by descending score, then by item name. Walk this list and keep an item unless its category is
      known and `max_per_category` items of that category are already kept; stop after `k` items. Items without a
      category are never capped. `k < 0` or `max_per_category < 1` (when given) is a `ValueError`.
''')

ALSOBOUGHT_SRC = dd('''
    """Item-to-item recommendations."""
    from fractions import Fraction


    def weight(age_days, half_life=30):
        if age_days < 0 or half_life < 1:
            raise ValueError("age must not be negative and the half-life must be at least 1")
        return Fraction(1, 2 ** (age_days // half_life))


    class Model:
        def __init__(self, baskets, today, half_life=30, categories=None):
            self._single = {}
            self._pair = {}
            self.categories = dict(categories or {})
            for day, items in baskets:
                if day > today:
                    raise ValueError("basket from the future")
                w = weight(today - day, half_life)
                names = sorted(set(items))
                for a in names:
                    self._single[a] = self._single.get(a, 0) + w
                for i, a in enumerate(names):
                    for b in names[i + 1:]:
                        self._pair[(a, b)] = self._pair.get((a, b), 0) + w

        def single(self, item):
            return Fraction(self._single.get(item, 0))

        def pair(self, a, b):
            if a == b:
                return self.single(a)
            return Fraction(self._pair.get((min(a, b), max(a, b)), 0))

        def similarity(self, a, b):
            if a == b:
                return Fraction(1 if a in self._single else 0)
            both = self.pair(a, b)
            if both == 0:
                return Fraction(0)
            return both / (self.single(a) + self.single(b) - both)

        def recommend(self, history, k, max_per_category=None):
            if k < 0 or (max_per_category is not None and max_per_category < 1):
                raise ValueError("k must not be negative and max_per_category must be at least 1")
            seen = set(history)
            scored = []
            for item in self._single:
                if item in seen:
                    continue
                score = sum((self.similarity(h, item) for h in sorted(seen)), Fraction(0))
                if score > 0:
                    scored.append((item, score))
            scored.sort(key=lambda e: (-e[1], e[0]))
            kept, used = [], {}
            for item, score in scored:
                if len(kept) >= k:
                    break
                cat = self.categories.get(item)
                if max_per_category is not None and cat is not None and used.get(cat, 0) >= max_per_category:
                    continue
                kept.append((item, score))
                if cat is not None:
                    used[cat] = used.get(cat, 0) + 1
            return kept
''')

ALSOBOUGHT_VISIBLE = dd('''
    import unittest
    from fractions import Fraction as F

    from alsobought.model import Model, weight


    class BasicTests(unittest.TestCase):
        def test_weight(self):
            self.assertEqual(weight(0), 1)
            self.assertEqual(weight(60), F(1, 4))

        def test_similarity(self):
            m = Model([(10, {"a", "b"}), (10, {"a"})], today=10)
            self.assertEqual(m.similarity("a", "b"), F(1, 2))


    if __name__ == "__main__":
        unittest.main()
''')

ALSOBOUGHT_HIDDEN = dd('''
    import unittest
    from fractions import Fraction as F

    from alsobought.model import Model, weight

    BASKETS = [(100, {"a", "b", "c"}), (70, {"a", "b"}), (40, {"a", "c"}), (5, {"b", "c", "d"})]


    def model(**kw):
        return Model(BASKETS, 100, **kw)


    class Weights(unittest.TestCase):
        def test_half_lives(self):
            table = {0: F(1), 29: F(1), 30: F(1, 2), 59: F(1, 2), 60: F(1, 4), 90: F(1, 8), 95: F(1, 8), 300: F(1, 1024)}
            for age, want in table.items():
                self.assertEqual(weight(age), want, age)
            self.assertIsInstance(weight(3), F)

        def test_custom_half_life(self):
            self.assertEqual(weight(9, 10), 1)
            self.assertEqual(weight(10, 10), F(1, 2))
            self.assertEqual(weight(25, 10), F(1, 4))
            self.assertEqual(weight(5, 1), F(1, 32))
            self.assertEqual(weight(7, 100), 1)

        def test_errors(self):
            for args in ((-1,), (5, 0), (5, -3)):
                with self.assertRaises(ValueError):
                    weight(*args)


    class Counts(unittest.TestCase):
        def test_single(self):
            m = model()
            self.assertEqual(m.single("a"), F(7, 4))
            self.assertEqual(m.single("b"), F(13, 8))
            self.assertEqual(m.single("c"), F(11, 8))
            self.assertEqual(m.single("d"), F(1, 8))
            self.assertEqual(m.single("zzz"), 0)

        def test_pair(self):
            m = model()
            self.assertEqual(m.pair("a", "b"), F(3, 2))
            self.assertEqual(m.pair("b", "a"), F(3, 2))
            self.assertEqual(m.pair("a", "c"), F(5, 4))
            self.assertEqual(m.pair("b", "c"), F(9, 8))
            self.assertEqual(m.pair("b", "d"), F(1, 8))
            self.assertEqual(m.pair("c", "d"), F(1, 8))
            self.assertEqual(m.pair("a", "d"), 0)
            self.assertEqual(m.pair("a", "a"), F(7, 4))
            self.assertEqual(m.pair("a", "zzz"), 0)

        def test_duplicates_and_empty_baskets(self):
            m = Model([(10, ["x", "x", "y"]), (10, []), (10, ["y"])], 10)
            self.assertEqual(m.single("x"), 1)
            self.assertEqual(m.single("y"), 2)
            self.assertEqual(m.pair("x", "y"), 1)

        def test_default_half_life_is_thirty_days(self):
            m = Model([(71, {"a"}), (70, {"a"})], 100)
            self.assertEqual(m.single("a"), F(3, 2))

        def test_half_life_parameter(self):
            m = Model([(100, {"a"}), (90, {"a"})], 100, half_life=10)
            self.assertEqual(m.single("a"), F(3, 2))

        def test_future_basket(self):
            with self.assertRaises(ValueError):
                Model([(11, {"a"})], 10)
            Model([(10, {"a"})], 10)

        def test_no_baskets(self):
            m = Model([], 10)
            self.assertEqual(m.single("a"), 0)
            self.assertEqual(m.recommend(["a"], 3), [])


    class Similarity(unittest.TestCase):
        def test_values(self):
            m = model()
            self.assertEqual(m.similarity("a", "b"), F(4, 5))
            self.assertEqual(m.similarity("b", "a"), F(4, 5))
            self.assertEqual(m.similarity("a", "c"), F(2, 3))
            self.assertEqual(m.similarity("b", "c"), F(3, 5))
            self.assertEqual(m.similarity("b", "d"), F(1, 13))
            self.assertEqual(m.similarity("c", "d"), F(1, 11))
            self.assertEqual(m.similarity("a", "d"), 0)

        def test_identity_and_unknown(self):
            m = model()
            self.assertEqual(m.similarity("a", "a"), 1)
            self.assertEqual(m.similarity("zzz", "zzz"), 0)
            self.assertEqual(m.similarity("a", "zzz"), 0)
            self.assertEqual(m.similarity("zzz", "a"), 0)

        def test_always_together_is_one(self):
            m = Model([(1, {"p", "q"}), (1, {"p", "q"})], 1)
            self.assertEqual(m.similarity("p", "q"), 1)


    class Recommend(unittest.TestCase):
        def test_single_history_item(self):
            m = model()
            self.assertEqual(m.recommend(["a"], 3), [("b", F(4, 5)), ("c", F(2, 3))])
            self.assertEqual(m.recommend({"a"}, 1), [("b", F(4, 5))])
            self.assertEqual(m.recommend(["a"], 0), [])

        def test_scores_add_up(self):
            m = model()
            self.assertEqual(m.recommend(["a", "b"], 5), [("c", F(19, 15)), ("d", F(1, 13))])
            self.assertEqual(m.recommend(["b", "a", "a"], 5), [("c", F(19, 15)), ("d", F(1, 13))])

        def test_history_items_are_never_recommended(self):
            m = model()
            for h in (["a"], ["b"], ["c"], ["d"], ["a", "c"]):
                got = [item for item, _ in m.recommend(h, 10)]
                self.assertTrue(set(got).isdisjoint(h))

        def test_ties_sorted_by_name(self):
            m = Model([(1, {"h", "x"}), (1, {"h", "y"}), (1, {"h", "a"})], 1)
            got = m.recommend(["h"], 3)
            self.assertEqual([i for i, _ in got], ["a", "x", "y"])
            self.assertEqual({s for _, s in got}, {F(1, 3)})

        def test_zero_scores_dropped(self):
            m = model()
            self.assertEqual([i for i, _ in m.recommend(["d"], 10)], ["c", "b"])
            self.assertEqual(m.recommend(["zzz"], 5), [])
            self.assertEqual(m.recommend([], 5), [])

        def test_k_limits(self):
            m = model()
            self.assertEqual(len(m.recommend(["c"], 2)), 2)
            self.assertEqual(len(m.recommend(["c"], 10)), 3)

        def test_category_cap(self):
            cats = {"a": "x", "b": "x", "d": "y"}
            m = model(categories=cats)
            self.assertEqual(m.recommend(["c"], 3, max_per_category=1), [("a", F(2, 3)), ("d", F(1, 11))])
            self.assertEqual(m.recommend(["c"], 3, max_per_category=2), [("a", F(2, 3)), ("b", F(3, 5)), ("d", F(1, 11))])
            self.assertEqual(m.recommend(["c"], 1, max_per_category=1), [("a", F(2, 3))])
            self.assertEqual(m.recommend(["c"], 3), [("a", F(2, 3)), ("b", F(3, 5)), ("d", F(1, 11))])

        def test_uncategorised_items_are_not_capped(self):
            m = model(categories={"a": "x"})
            self.assertEqual([i for i, _ in m.recommend(["c"], 5, max_per_category=1)], ["a", "b", "d"])
            m = model(categories={"b": "x"})
            self.assertEqual([i for i, _ in m.recommend(["d"], 5, max_per_category=1)], ["c", "b"])

        def test_cap_counts_only_kept_items(self):
            m = model(categories={"a": "x", "b": "x", "c": "x", "d": "y"})
            got = m.recommend(["d"], 5, max_per_category=1)
            self.assertEqual(got, [("c", F(1, 11))])
            self.assertEqual(m.recommend(["d"], 5, max_per_category=2), [("c", F(1, 11)), ("b", F(1, 13))])

        def test_errors(self):
            m = model()
            with self.assertRaises(ValueError):
                m.recommend(["a"], -1)
            with self.assertRaises(ValueError):
                m.recommend(["a"], 3, max_per_category=0)


    if __name__ == "__main__":
        unittest.main()
''')

_BK = "[(100, {'a', 'b', 'c'}), (70, {'a', 'b'}), (40, {'a', 'c'}), (5, {'b', 'c', 'd'})]"
_M = f"Model({_BK}, 100)"

ALSOBOUGHT = Lib(
    name="alsobought", lang="python", title="the alsobought recommender (`alsobought/model.py`)",
    blurb="The bookshop's checkout page uses alsobought to suggest titles that customers with a similar basket also bought.",
    files={"alsobought/__init__.py": "", "alsobought/model.py": ALSOBOUGHT_SRC, "README.md": ALSOBOUGHT_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": ALSOBOUGHT_VISIBLE},
    hidden_tests={"tests/test_full.py": ALSOBOUGHT_HIDDEN},
    mutate=["alsobought/model.py"], difficulty=3, tags=["recommendation", "similarity"],
    probes=[
        "[weight(n) for n in (0, 29, 30, 59, 60, 95)]", "weight(25, 10)",
        f"{_M}.single('a')", f"{_M}.pair('b', 'c')", f"{_M}.similarity('a', 'b')", f"{_M}.similarity('c', 'd')",
        f"{_M}.recommend(['a'], 3)", f"{_M}.recommend(['a', 'b'], 5)", f"{_M}.recommend(['d'], 10)",
        f"Model({_BK}, 100, categories={{'a': 'x', 'b': 'x', 'd': 'y'}}).recommend(['c'], 3, max_per_category=1)",
        f"Model({_BK}, 100, categories={{'a': 'x'}}).recommend(['c'], 5, max_per_category=1)",
        "Model([(100, {'a'}), (90, {'a'})], 100, half_life=10).single('a')",
    ],
    probe_import="from alsobought.model import Model, weight\n",
)


# ======================================================================================================================
# redline: word-level change tracking for contract drafts
# ======================================================================================================================

REDLINE_README = dd('''
    # redline

    Word-level change tracking for a contract editor: compare two drafts of a clause and show what changed.

    ## `tokenize(text) -> list[str]`

    The tokens of a text: every maximal run of word characters (`\\w+`) and every other non-space character on its own
    (`"pay 5% now."` gives `pay`, `5`, `%`, `now`, `.`). Whitespace only separates tokens.

    ## `diff(old, new) -> list[(op, token)]`

    `old` and `new` are lists of tokens. The result is an edit script of `("=", token)` (kept), `("-", token)` (only in
    `old`) and `("+", token)` (only in `new`) whose `=` entries form a longest common subsequence. Ties are broken by a
    fixed procedure: let `lcs[i][j]` be the length of a longest common subsequence of `old[i:]` and `new[j:]`; starting at
    `i = j = 0` repeat: if both lists have tokens left and `old[i] == new[j]`, emit `=` and advance both; otherwise, if
    both have tokens left and `lcs[i+1][j] >= lcs[i][j+1]`, emit `-` for `old[i]` and advance `i`; otherwise if
    `new` has tokens left emit `+` for `new[j]` and advance `j` (and if only `old` has tokens left emit its `-`). So in
    ambiguous cases deletions come before insertions. `diff_text(a, b)` is `diff(tokenize(a), tokenize(b))`.

    ## `apply_ops(ops, side) -> list[str]`

    The tokens of one side: `side="old"` keeps the `=` and `-` tokens, `side="new"` the `=` and `+` tokens (in order).
    Any other `side` is a `ValueError`.

    ## `render(ops) -> str`

    Markup for people: a maximal run of `-` entries becomes `[-w1 w2-]`, a maximal run of `+` entries becomes
    `{+w1 w2+}` (words separated by one space), and `=` tokens are written as they are. The pieces are joined by one
    space, except that a deletion run directly followed by an insertion run is written without a space between them
    (`[-cat-]{+dog+}`). No ops give an empty string.

    ## `stats(ops) -> dict`

    `{"equal": e, "deleted": d, "inserted": i, "similarity_pct": p}` with `p = 100 * 2e / (2e + d + i)` rounded half up
    to a whole number (`100` when there are no ops).
''')

REDLINE_SRC = dd('''
    """Word-level diff."""
    import re


    def tokenize(text):
        return re.findall(r"\\w+|[^\\w\\s]", text)


    def diff(old, new):
        n, m = len(old), len(new)
        lcs = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(n - 1, -1, -1):
            for j in range(m - 1, -1, -1):
                if old[i] == new[j]:
                    lcs[i][j] = lcs[i + 1][j + 1] + 1
                else:
                    lcs[i][j] = max(lcs[i + 1][j], lcs[i][j + 1])
        ops = []
        i = j = 0
        while i < n and j < m:
            if old[i] == new[j]:
                ops.append(("=", old[i]))
                i += 1
                j += 1
            elif lcs[i + 1][j] >= lcs[i][j + 1]:
                ops.append(("-", old[i]))
                i += 1
            else:
                ops.append(("+", new[j]))
                j += 1
        ops.extend(("-", t) for t in old[i:])
        ops.extend(("+", t) for t in new[j:])
        return ops


    def diff_text(a, b):
        return diff(tokenize(a), tokenize(b))


    def apply_ops(ops, side):
        if side not in ("old", "new"):
            raise ValueError("side must be 'old' or 'new'")
        drop = "+" if side == "old" else "-"
        return [t for op, t in ops if op != drop]


    def render(ops):
        pieces = []
        i = 0
        while i < len(ops):
            op = ops[i][0]
            j = i
            while j < len(ops) and ops[j][0] == op:
                j += 1
            words = " ".join(t for _, t in ops[i:j])
            if op == "=":
                pieces.append((words, False))
            elif op == "-":
                pieces.append(("[-" + words + "-]", True))
            else:
                pieces.append(("{+" + words + "+}", False))
            i = j
        out = ""
        prev_is_deletion = False
        for k, (text, is_deletion) in enumerate(pieces):
            if k:
                glued = prev_is_deletion and text.startswith("{+")
                out += ("" if glued else " ")
            out += text
            prev_is_deletion = is_deletion
        return out


    def stats(ops):
        equal = sum(1 for op, _ in ops if op == "=")
        deleted = sum(1 for op, _ in ops if op == "-")
        inserted = sum(1 for op, _ in ops if op == "+")
        total = 2 * equal + deleted + inserted
        pct = 100 if total == 0 else (200 * 2 * equal + total) // (2 * total)
        return {"equal": equal, "deleted": deleted, "inserted": inserted, "similarity_pct": pct}
''')

REDLINE_VISIBLE = dd('''
    import unittest

    from redline.diff import diff_text, render


    class BasicTests(unittest.TestCase):
        def test_replace_word(self):
            self.assertEqual(render(diff_text("the cat sat", "the dog sat")), "the [-cat-]{+dog+} sat")


    if __name__ == "__main__":
        unittest.main()
''')

REDLINE_HIDDEN = dd('''
    import unittest

    from redline.diff import apply_ops, diff, diff_text, render, stats, tokenize


    class Tokens(unittest.TestCase):
        def test_tokenize(self):
            self.assertEqual(tokenize("pay 5% now."), ["pay", "5", "%", "now", "."])
            self.assertEqual(tokenize("  a   b\\tc\\n"), ["a", "b", "c"])
            self.assertEqual(tokenize(""), [])
            self.assertEqual(tokenize("   "), [])
            self.assertEqual(tokenize("(x,y)"), ["(", "x", ",", "y", ")"])
            self.assertEqual(tokenize("snake_case 12ab"), ["snake_case", "12ab"])
            self.assertEqual(tokenize("a--b"), ["a", "-", "-", "b"])

        def test_unicode_words(self):
            self.assertEqual(tokenize("caf\\u00e9 cr\\u00e8me"), ["caf\\u00e9", "cr\\u00e8me"])


    class Diff(unittest.TestCase):
        def test_identical_and_empty(self):
            self.assertEqual(diff(["a", "b"], ["a", "b"]), [("=", "a"), ("=", "b")])
            self.assertEqual(diff([], []), [])
            self.assertEqual(diff(["a"], []), [("-", "a")])
            self.assertEqual(diff([], ["a"]), [("+", "a")])
            self.assertEqual(diff(["a", "b"], []), [("-", "a"), ("-", "b")])
            self.assertEqual(diff([], ["a", "b"]), [("+", "a"), ("+", "b")])

        def test_replacement(self):
            self.assertEqual(diff(["the", "cat", "sat"], ["the", "dog", "sat"]), [("=", "the"), ("-", "cat"), ("+", "dog"), ("=", "sat")])

        def test_insert_and_delete(self):
            self.assertEqual(diff(["a", "c"], ["a", "b", "c"]), [("=", "a"), ("+", "b"), ("=", "c")])
            self.assertEqual(diff(["a", "b", "c"], ["a", "c"]), [("=", "a"), ("-", "b"), ("=", "c")])
            self.assertEqual(diff(["x"], ["y", "x"]), [("+", "y"), ("=", "x")])
            self.assertEqual(diff(["x", "y"], ["x"]), [("=", "x"), ("-", "y")])

        def test_disjoint_deletes_first(self):
            self.assertEqual(diff(["p", "q"], ["r"]), [("-", "p"), ("-", "q"), ("+", "r")])
            self.assertEqual(diff(["p"], ["r", "s"]), [("-", "p"), ("+", "r"), ("+", "s")])

        def test_deletion_before_insertion_in_ambiguous_cases(self):
            self.assertEqual(diff(["x", "y"], ["z", "y"]), [("-", "x"), ("+", "z"), ("=", "y")])
            self.assertEqual(diff(["a", "b"], ["b", "a"]), [("-", "a"), ("=", "b"), ("+", "a")])
            self.assertEqual(diff(["b", "a"], ["a", "b"]), [("-", "b"), ("=", "a"), ("+", "b")])

        def test_repeated_tokens(self):
            self.assertEqual(diff(["a", "a", "b"], ["a", "b"]), [("=", "a"), ("-", "a"), ("=", "b")])
            self.assertEqual(diff(["a", "b"], ["a", "a", "b"]), [("=", "a"), ("+", "a"), ("=", "b")])
            self.assertEqual(diff(list("abcabba"), list("cbabac"))[0], ("-", "a"))

        def test_is_a_longest_common_subsequence(self):
            pairs = [("abcabba", "cbabac"), ("kitten", "sitting"), ("xyz", "zyx"), ("aaaa", "aa"), ("abcdef", "badcfe"), ("", "abc")]
            for a, b in pairs:
                ops = diff(list(a), list(b))
                kept = [t for op, t in ops if op == "="]
                self.assertEqual(len(kept), self.lcs_len(a, b), (a, b))
                self.assertEqual(apply_ops(ops, "old"), list(a))
                self.assertEqual(apply_ops(ops, "new"), list(b))

        @staticmethod
        def lcs_len(a, b):
            row = [0] * (len(b) + 1)
            for x in a:
                prev = 0
                for j, y in enumerate(b, 1):
                    cur = row[j]
                    row[j] = prev + 1 if x == y else max(row[j], row[j - 1])
                    prev = cur
            return row[-1]

        def test_exhaustive_small_cases_follow_the_documented_procedure(self):
            import itertools
            from functools import lru_cache

            def reference(old, new):
                @lru_cache(maxsize=None)
                def lcs(i, j):
                    if i == len(old) or j == len(new):
                        return 0
                    if old[i] == new[j]:
                        return 1 + lcs(i + 1, j + 1)
                    return max(lcs(i + 1, j), lcs(i, j + 1))

                ops, i, j = [], 0, 0
                while i < len(old) and j < len(new):
                    if old[i] == new[j]:
                        ops.append(("=", old[i]))
                        i, j = i + 1, j + 1
                    elif lcs(i + 1, j) >= lcs(i, j + 1):
                        ops.append(("-", old[i]))
                        i += 1
                    else:
                        ops.append(("+", new[j]))
                        j += 1
                return ops + [("-", t) for t in old[i:]] + [("+", t) for t in new[j:]]

            words = ["".join(p) for n in range(0, 6) for p in itertools.product("ab", repeat=n)]
            for a in words:
                for b in words:
                    self.assertEqual(diff(list(a), list(b)), reference(tuple(a), tuple(b)), (a, b))

        def test_exhaustive_three_letter_alphabet(self):
            import itertools

            words = ["".join(p) for n in range(0, 5) for p in itertools.product("abc", repeat=n)]
            for a in words:
                for b in words:
                    ops = diff(list(a), list(b))
                    self.assertEqual("".join(apply_ops(ops, "old")), a)
                    self.assertEqual("".join(apply_ops(ops, "new")), b)
                    self.assertEqual(len([1 for op, _ in ops if op == "="]), self.lcs_len(a, b), (a, b))

        def test_diff_text(self):
            ops = diff_text("Pay 5% now.", "Pay 7% later.")
            self.assertEqual(ops, [("=", "Pay"), ("-", "5"), ("+", "7"), ("=", "%"), ("-", "now"), ("+", "later"), ("=", ".")])

        def test_inputs_not_modified(self):
            a, b = ["a", "b"], ["b", "c"]
            diff(a, b)
            self.assertEqual((a, b), (["a", "b"], ["b", "c"]))


    class Apply(unittest.TestCase):
        OPS = [("=", "a"), ("-", "b"), ("+", "c"), ("=", "d")]

        def test_sides(self):
            self.assertEqual(apply_ops(self.OPS, "old"), ["a", "b", "d"])
            self.assertEqual(apply_ops(self.OPS, "new"), ["a", "c", "d"])
            self.assertEqual(apply_ops([], "old"), [])

        def test_bad_side(self):
            for side in ("both", "", None, "OLD"):
                with self.assertRaises(ValueError):
                    apply_ops(self.OPS, side)


    class Render(unittest.TestCase):
        def test_examples(self):
            self.assertEqual(render(diff_text("the cat sat", "the dog sat")), "the [-cat-]{+dog+} sat")
            self.assertEqual(render(diff_text("a b c", "a b c")), "a b c")
            self.assertEqual(render(diff_text("a c", "a b c")), "a {+b+} c")
            self.assertEqual(render(diff_text("a b c", "a c")), "a [-b-] c")
            self.assertEqual(render([]), "")

        def test_runs(self):
            self.assertEqual(render([("-", "p"), ("-", "q"), ("+", "r")]), "[-p q-]{+r+}")
            self.assertEqual(render([("-", "p"), ("+", "r"), ("+", "s"), ("=", "t")]), "[-p-]{+r s+} t")
            self.assertEqual(render([("=", "a"), ("=", "b"), ("-", "c"), ("=", "d")]), "a b [-c-] d")
            self.assertEqual(render([("+", "x"), ("=", "y")]), "{+x+} y")
            self.assertEqual(render([("=", "y"), ("+", "x")]), "y {+x+}")

        def test_insertion_then_deletion_keeps_a_space(self):
            self.assertEqual(render([("+", "x"), ("-", "y")]), "{+x+} [-y-]")
            self.assertEqual(render([("-", "y"), ("=", "m"), ("+", "x")]), "[-y-] m {+x+}")
            self.assertEqual(render([("-", "a"), ("=", "m"), ("-", "b"), ("+", "c")]), "[-a-] m [-b-]{+c+}")

        def test_full_sentence(self):
            text = render(diff_text("Pay 5% now.", "Pay 7% later."))
            self.assertEqual(text, "Pay [-5-]{+7+} % [-now-]{+later+} .")


    class Stats(unittest.TestCase):
        def test_counts(self):
            ops = diff_text("the cat sat", "the dog sat")
            self.assertEqual(stats(ops), {"equal": 2, "deleted": 1, "inserted": 1, "similarity_pct": 67})

        def test_edges(self):
            self.assertEqual(stats([])["similarity_pct"], 100)
            self.assertEqual(stats([("=", "a")])["similarity_pct"], 100)
            self.assertEqual(stats([("-", "a"), ("+", "b")]), {"equal": 0, "deleted": 1, "inserted": 1, "similarity_pct": 0})
            self.assertEqual(stats([("-", "a")]), {"equal": 0, "deleted": 1, "inserted": 0, "similarity_pct": 0})

        def test_rounding(self):
            # 2*1 / (2 + 1 + 1) = 50 %; 2*1 / (2 + 2 + 3) = 28.57 -> 29 %; 2*3/(6+1) = 85.7 -> 86 %
            self.assertEqual(stats([("=", "a"), ("-", "b"), ("+", "c")])["similarity_pct"], 50)
            self.assertEqual(stats([("=", "a"), ("-", "b"), ("-", "c"), ("+", "d"), ("+", "e"), ("+", "f")])["similarity_pct"], 29)
            self.assertEqual(stats([("=", "a")] * 3 + [("-", "x")])["similarity_pct"], 86)
            ops = [("=", "a")] + [("-", "x")] * 7
            self.assertEqual(stats(ops)["similarity_pct"], 22)
            # exactly 12.5 % and 37.5 % round up
            self.assertEqual(stats([("=", "a")] + [("-", "x")] * 14)["similarity_pct"], 13)
            self.assertEqual(stats([("=", "a")] * 3 + [("-", "x")] * 5 + [("+", "y")] * 5)["similarity_pct"], 38)


    if __name__ == "__main__":
        unittest.main()
''')

REDLINE = Lib(
    name="redline", lang="python", title="the redline word diff (`redline/diff.py`)",
    blurb="The contract editor uses redline to show reviewers which words changed between two drafts of a clause.",
    files={"redline/__init__.py": "", "redline/diff.py": REDLINE_SRC, "README.md": REDLINE_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": REDLINE_VISIBLE},
    hidden_tests={"tests/test_full.py": REDLINE_HIDDEN},
    mutate=["redline/diff.py"], difficulty=3, tags=["diff", "text"],
    probes=[
        "tokenize('pay 5% now.')", "tokenize('a--b')",
        "diff(['the', 'cat', 'sat'], ['the', 'dog', 'sat'])", "diff(['x', 'y'], ['z', 'y'])",
        "diff(['a', 'b'], ['b', 'a'])", "diff(['p', 'q'], ['r'])", "diff(['a', 'a', 'b'], ['a', 'b'])",
        "apply_ops(diff(['a', 'b'], ['b', 'c']), 'new')", "apply_ops(diff(['a', 'b'], ['b', 'c']), 'old')",
        "render(diff_text('the cat sat', 'the dog sat'))", "render(diff_text('Pay 5% now.', 'Pay 7% later.'))",
        "render([('+', 'x'), ('-', 'y')])", "render([('-', 'p'), ('-', 'q'), ('+', 'r')])",
        "stats(diff_text('the cat sat', 'the dog sat'))", "stats([('=', 'a')] + [('-', 'x')] * 3 + [('+', 'y')] * 4)",
    ],
    probe_import="from redline.diff import tokenize, diff, diff_text, apply_ops, render, stats\n",
)

# ======================================================================================================================
# palette: fuzzy command matching with word-start bonuses
# ======================================================================================================================

PALETTE_README = dd('''
    # palette

    The fuzzy matcher behind an editor's command palette. A query matches a candidate when its characters appear in the
    candidate in the same order (not necessarily next to each other), ignoring case. Several alignments may be
    possible; the best-scoring one counts.

    ## Scoring one alignment

    An alignment is the list of candidate positions `p0 < p1 < ...` that the query characters are matched to. Every
    matched character scores:

    * `10` for the match;
    * `+15` when its position is `0` (the very start of the candidate);
    * `+10` when it starts a word: position `0`, or the previous candidate character is one of space, `-`, `_`, `/`
      or `.`, or the previous character is lower case and this one is upper case (a camelCase boundary; judged on the
      original candidate text);
    * for the first matched character a penalty of `min(position, 5)` (a late start costs at most 5);
    * for every later matched character `+5` when it directly follows the previous match (`p == previous + 1`) and a
      penalty of the number of candidate characters skipped between the two matches (`p - previous - 1`).

    The score of an alignment is the sum over its characters. The score of a candidate is the best alignment's score
    and its positions are the best alignment's positions; among alignments with the same score the one with the
    lexicographically smallest list of positions is used.

    ## Functions

    * `match(query, candidate) -> (score, positions) | None`: `None` when the query is not a subsequence of the
      candidate. An empty query matches everything with `(0, ())`.
    * `rank(query, candidates, limit=None) -> list[(candidate, score)]`: the candidates that match, ordered by descending
      score, then by shorter candidate, then alphabetically (plain string order). `limit` keeps only that many entries
      (`ValueError` if negative).
    * `highlight(query, candidate) -> str | None`: the candidate with every maximal run of matched positions wrapped
      in `[` and `]` (`"x[ab]c"`), or `None` when it does not match; with an empty query the candidate is returned as
      it is.
''')

PALETTE_SRC = dd('''
    """Fuzzy command matching."""

    SEPARATORS = " -_/."


    def _word_start(cand, i):
        if i == 0:
            return True
        prev = cand[i - 1]
        return prev in SEPARATORS or (prev.islower() and cand[i].isupper())


    def _char_score(cand, i, prev):
        score = 10
        if i == 0:
            score += 15
        if _word_start(cand, i):
            score += 10
        if prev is None:
            score -= min(i, 5)
        else:
            if i == prev + 1:
                score += 5
            score -= i - prev - 1
        return score


    def match(query, candidate):
        q, c = query.lower(), candidate.lower()
        memo = {}

        def best(qi, start, prev):
            if qi == len(q):
                return 0, ()
            key = (qi, start, prev)
            if key in memo:
                return memo[key]
            found = None
            for p in range(start, len(c)):
                if c[p] != q[qi]:
                    continue
                rest = best(qi + 1, p + 1, p)
                if rest is None:
                    continue
                total = _char_score(candidate, p, prev) + rest[0]
                if found is None or total > found[0]:
                    found = (total, (p,) + rest[1])
            memo[key] = found
            return found

        return best(0, 0, None)


    def rank(query, candidates, limit=None):
        if limit is not None and limit < 0:
            raise ValueError("limit must not be negative")
        scored = []
        for cand in candidates:
            m = match(query, cand)
            if m is not None:
                scored.append((cand, m[0]))
        scored.sort(key=lambda e: (-e[1], len(e[0]), e[0]))
        return scored if limit is None else scored[:limit]


    def highlight(query, candidate):
        m = match(query, candidate)
        if m is None:
            return None
        marked = set(m[1])
        out, inside = [], False
        for i, ch in enumerate(candidate):
            if i in marked and not inside:
                out.append("[")
                inside = True
            elif i not in marked and inside:
                out.append("]")
                inside = False
            out.append(ch)
        if inside:
            out.append("]")
        return "".join(out)
''')

PALETTE_VISIBLE = dd('''
    import unittest

    from palette.fuzzy import match, rank


    class BasicTests(unittest.TestCase):
        def test_exact(self):
            self.assertEqual(match("ab", "ab"), (50, (0, 1)))

        def test_no_match(self):
            self.assertIsNone(match("ba", "ab"))

        def test_rank_order(self):
            self.assertEqual([c for c, _ in rank("ab", ["xab", "ab"])], ["ab", "xab"])


    if __name__ == "__main__":
        unittest.main()
''')

PALETTE_HIDDEN = dd('''
    import unittest

    from palette.fuzzy import highlight, match, rank


    class Scores(unittest.TestCase):
        def test_start_of_candidate(self):
            self.assertEqual(match("ab", "ab"), (50, (0, 1)))
            self.assertEqual(match("a", "a"), (35, (0,)))
            self.assertEqual(match("abc", "abc"), (65, (0, 1, 2)))

        def test_leading_penalty(self):
            self.assertEqual(match("ab", "xab"), (24, (1, 2)))
            self.assertEqual(match("z", "abcdefgz"), (5, (7,)))
            self.assertEqual(match("z", "az"), (9, (1,)))
            self.assertEqual(match("z", "abcdefz"), (5, (6,)))
            self.assertEqual(match("z", "abcdez"), (5, (5,)))
            self.assertEqual(match("z", "abcdz"), (6, (4,)))

        def test_word_starts(self):
            self.assertEqual(match("ab", "a-b"), (54, (0, 2)))
            self.assertEqual(match("z", "a z"), (18, (2,)))
            self.assertEqual(match("z", "a_z"), (18, (2,)))
            self.assertEqual(match("z", "a/z"), (18, (2,)))
            self.assertEqual(match("z", "a.z"), (18, (2,)))
            self.assertEqual(match("z", "a-z"), (18, (2,)))
            self.assertEqual(match("z", "a+z"), (8, (2,)))

        def test_camel_case_boundary(self):
            self.assertEqual(match("fb", "FooBar"), (53, (0, 3)))
            self.assertEqual(match("fb", "foobar"), (43, (0, 3)))
            self.assertEqual(match("fb", "FOOBar"), (43, (0, 3)))       # an upper case letter after an upper case one is no boundary
            self.assertEqual(match("b", "fooBar"), (10 + 10 - 3, (3,)))
            self.assertEqual(match("b", "FOOBar"), (10 - 3, (3,)))

        def test_case_insensitive(self):
            self.assertEqual(match("AB", "ab"), (50, (0, 1)))
            self.assertEqual(match("ab", "AB"), (50, (0, 1)))
            self.assertEqual(match("Fb", "foobar"), (43, (0, 3)))

        def test_best_alignment_is_chosen(self):
            self.assertEqual(match("ab", "aXbab"), (44, (0, 2)))
            self.assertEqual(match("o", "foo"), (9, (1,)))
            self.assertEqual(match("aa", "aaa"), (50, (0, 1)))

        def test_alignment_can_skip_an_early_match(self):
            # the greedy leftmost 'a' (position 0) loses to the 'a' that starts a word
            self.assertEqual(match("ac", "xa ac"), (32, (3, 4)))

        def test_gaps_cost_one_per_skipped_character(self):
            self.assertEqual(match("ab", "a..b")[0], 35 + 10 + 10 - 2)
            self.assertEqual(match("ab", "azzzb")[0], 35 + 10 - 3)
            self.assertEqual(match("ab", "azzzzzzb")[0], 35 + 10 - 6)

        def test_consecutive_bonus(self):
            self.assertEqual(match("xyz", "xyz")[0], 35 + 15 + 15)
            self.assertEqual(match("xz", "xyz")[0], 35 + 10 - 1)
            self.assertEqual(match("yz", "xyz")[0], (10 - 1) + 15)

        def test_positions_prefer_the_smallest_on_ties(self):
            self.assertEqual(match("a", "zzzzzzaa"), (5, (6,)))      # both 'a's lose the maximal 5 points for a late start
            self.assertEqual(match("a", "bab-a"), (16, (4,)))
            self.assertEqual(match("aa", "aXa")[1], (0, 2))

        def test_empty_query_and_no_match(self):
            self.assertEqual(match("", "anything"), (0, ()))
            self.assertEqual(match("", ""), (0, ()))
            self.assertIsNone(match("a", ""))
            self.assertIsNone(match("ba", "ab"))
            self.assertIsNone(match("aa", "a"))
            self.assertIsNone(match("abc", "ab"))
            self.assertIsNone(match("x", "abc"))


    class Ranking(unittest.TestCase):
        def test_order(self):
            got = rank("ab", ["xab", "ab", "a-b", "cab", "zz"])
            self.assertEqual(got, [("a-b", 54), ("ab", 50), ("cab", 24), ("xab", 24)])

        def test_ties_shorter_then_alphabetical(self):
            self.assertEqual(rank("a", ["ba", "ab", "a", "aa"]), [("a", 35), ("aa", 35), ("ab", 35), ("ba", 9)])
            self.assertEqual([c for c, _ in rank("zz", ["zzb", "zza", "zz"])], ["zz", "zza", "zzb"])
            self.assertEqual([c for c, _ in rank("a", ["xa", "ya", "wa", "a"])], ["a", "wa", "xa", "ya"])

        def test_limit(self):
            cands = ["ab", "a-b", "xab", "cab"]
            self.assertEqual([c for c, _ in rank("ab", cands, limit=2)], ["a-b", "ab"])
            self.assertEqual(rank("ab", cands, limit=0), [])
            self.assertEqual(len(rank("ab", cands, limit=10)), 4)
            with self.assertRaises(ValueError):
                rank("ab", cands, limit=-1)

        def test_empty_query_lists_everything_by_length(self):
            self.assertEqual(rank("", ["bb", "a", "ab", "c"]), [("a", 0), ("c", 0), ("ab", 0), ("bb", 0)])

        def test_no_candidates(self):
            self.assertEqual(rank("a", []), [])
            self.assertEqual(rank("a", ["b", "c"]), [])

        def test_realistic(self):
            cmds = ["Open File", "Open Folder", "Close File", "toggleFullscreen", "file-explorer.open", "Reload"]
            got = [c for c, _ in rank("of", cmds)]
            self.assertEqual(got, ["Open File", "Open Folder", "Close File", "toggleFullscreen"])
            self.assertEqual([c for c, _ in rank("tf", cmds)], ["toggleFullscreen"])


    class Highlight(unittest.TestCase):
        def test_runs(self):
            self.assertEqual(highlight("ab", "xabc"), "x[ab]c")
            self.assertEqual(highlight("fb", "FooBar"), "[F]oo[B]ar")
            self.assertEqual(highlight("ab", "ab"), "[ab]")
            self.assertEqual(highlight("abc", "a-b-c"), "[a]-[b]-[c]")
            self.assertEqual(highlight("a", "a"), "[a]")
            self.assertEqual(highlight("z", "abcz"), "abc[z]")

        def test_original_case_is_kept(self):
            self.assertEqual(highlight("OF", "open file"), "[o]pen [f]ile")

        def test_empty_query_and_no_match(self):
            self.assertEqual(highlight("", "abc"), "abc")
            self.assertIsNone(highlight("q", "abc"))
            self.assertIsNone(highlight("ba", "ab"))


    if __name__ == "__main__":
        unittest.main()
''')

PALETTE = Lib(
    name="palette", lang="python", title="the palette fuzzy matcher (`palette/fuzzy.py`)",
    blurb="The editor's command palette uses palette to rank commands against what the user has typed so far.",
    files={"palette/__init__.py": "", "palette/fuzzy.py": PALETTE_SRC, "README.md": PALETTE_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": PALETTE_VISIBLE},
    hidden_tests={"tests/test_full.py": PALETTE_HIDDEN},
    mutate=["palette/fuzzy.py"], difficulty=2, tags=["fuzzy", "ranking"],
    probes=[
        "match('ab', 'xab')", "match('ab', 'a-b')", "match('z', 'abcdefgz')", "match('fb', 'FooBar')", "match('fb', 'foobar')",
        "match('ab', 'aXbab')", "match('o', 'foo')", "match('xz', 'xyz')", "match('z', 'a+z')", "match('b', 'fooBar')",
        "rank('ab', ['xab', 'ab', 'a-b', 'cab', 'zz'])", "rank('zz', ['zzb', 'zza', 'zz'])",
        "rank('ab', ['ab', 'a-b', 'xab', 'cab'], limit=2)", "rank('', ['bb', 'a', 'ab', 'c'])",
        "highlight('fb', 'FooBar')", "highlight('abc', 'a-b-c')", "highlight('OF', 'open file')",
    ],
    probe_import="from palette.fuzzy import match, rank, highlight\n",
)

LIBS = [SEEDFILTER, PLATEHEAT, ALSOBOUGHT, REDLINE, PALETTE]
register_libs3(LIBS, n=10)
