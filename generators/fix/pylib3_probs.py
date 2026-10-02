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

    `bits` and `hashes` are positive integers (`ValueError` otherwise). The filter owns a bit array of `bits` bits, all
    clear at the start.

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

LIBS = [SEEDFILTER, PLATEHEAT]
register_libs3(LIBS, n=10)
