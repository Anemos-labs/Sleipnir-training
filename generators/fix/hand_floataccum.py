"""Floating point: accumulated error, exact-equality, bin edges, cancellation, NaN handling (python stats kit, rust numkit)."""
from fx import dd, family, langs
from generators.fix._hand_kit import Base, Bug, panic_excerpt, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): statistics helpers for a sensor dashboard.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # sensorstats

    Aggregations behind a sensor dashboard (floats in, floats out; run `python3 -m unittest discover -s tests`).

    * `mean(values)`: arithmetic mean of the **exactly summed** values: the sum is `math.fsum` (correctly rounded), then divided by the count (`mean([0.1] * 10)` is
      exactly `0.1`). An empty list is a `ValueError`.
    * `variance(values)`: population variance by the **two-pass** method (the mean first, then the mean squared deviation, both exactly summed): it
      stays accurate for readings like `1e9 + 1`. Empty is a `ValueError`.
    * `moving_average(values, k)`: the means of every window of `k` consecutive values (`len(values) - k + 1` of them), each computed from its own `k` values
      (never from the previous window's result), so the rounding error of earlier windows never carries over: a window of zeros is exactly `0.0`. `k < 1` is a `ValueError`; `k > len(values)` gives `[]`.
    * `bin_index(x, lo, hi, n)`: histogram bin of `x` for `n` equal bins on `[lo, hi]`, as a **decimal** calculation (the numbers are read by their decimal text, so `0.3`
      is 0.3): bin `i` covers `[lo + i*w, lo + (i+1)*w)` with `w = (hi - lo) / n`, and `hi` itself falls in the last bin. A value outside `[lo, hi]` is a `ValueError`.
    * `approx_equal(a, b, rel=1e-9, abs_tol=0.0)`: `math.isclose` semantics.
    * `percent_change(old, new)`: `(new - old) / |old| * 100`; `None` when `old` is 0.
''')

A_STATS = dd('''
    import math
    from decimal import Decimal


    def mean(values):
        if not values:
            raise ValueError("mean of nothing")
        return math.fsum(values) / len(values)


    def variance(values):
        m = mean(values)
        return math.fsum((x - m) ** 2 for x in values) / len(values)


    def moving_average(values, k):
        if k < 1:
            raise ValueError("window must be at least 1")
        return [math.fsum(values[i:i + k]) / k for i in range(len(values) - k + 1)]


    def bin_index(x, lo, hi, n):
        x, lo, hi = Decimal(str(x)), Decimal(str(lo)), Decimal(str(hi))
        if not lo <= x <= hi:
            raise ValueError("value outside the range")
        if x == hi:
            return n - 1
        return int((x - lo) * n / (hi - lo))


    def approx_equal(a, b, rel=1e-9, abs_tol=0.0):
        return math.isclose(a, b, rel_tol=rel, abs_tol=abs_tol)


    def percent_change(old, new):
        if old == 0:
            return None
        return (new - old) / abs(old) * 100
''')

A_VISIBLE = {
    "tests/test_stats.py": dd('''
        import unittest

        from sensorstats.stats import approx_equal, bin_index, mean, moving_average, percent_change, variance


        class StatsTests(unittest.TestCase):
            def test_mean(self):
                self.assertEqual(mean([1, 2, 3, 6]), 3)

            def test_variance(self):
                self.assertEqual(variance([2, 4, 4, 4, 5, 5, 7, 9]), 4)

            def test_moving_average(self):
                self.assertEqual(moving_average([1, 2, 3, 4], 2), [1.5, 2.5, 3.5])

            def test_bins(self):
                self.assertEqual(bin_index(5, 0, 10, 5), 2)

            def test_close(self):
                self.assertTrue(approx_equal(1.0, 1.0))
                self.assertEqual(percent_change(50, 75), 50)


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_stats.py": dd('''
        import unittest

        from sensorstats.stats import approx_equal, bin_index, mean, moving_average, percent_change, variance


        class Mean(unittest.TestCase):
            def test_exact_sums(self):
                self.assertEqual(mean([0.1] * 10), 0.1)
                self.assertEqual(mean([1e16, 1.0, -1e16, 1.0]), 0.5)

            def test_errors(self):
                with self.assertRaises(ValueError):
                    mean([])


        class Variance(unittest.TestCase):
            def test_small_numbers(self):
                self.assertEqual(variance([5]), 0)
                self.assertEqual(variance([2, 4, 4, 4, 5, 5, 7, 9]), 4)

            def test_large_offset_does_not_cancel(self):
                self.assertAlmostEqual(variance([1e9 + 1, 1e9 + 2, 1e9 + 3]), 2 / 3, places=12)
                self.assertAlmostEqual(variance([1e8 + 0.1, 1e8 + 0.2, 1e8 + 0.3, 1e8 + 0.4]), 0.0125, places=6)
                self.assertEqual(variance([1e9, 1e9, 1e9]), 0)

            def test_errors(self):
                with self.assertRaises(ValueError):
                    variance([])


        class MovingAverage(unittest.TestCase):
            def test_plain(self):
                self.assertEqual(moving_average([1, 2, 3, 4, 5], 3), [2, 3, 4])
                self.assertEqual(moving_average([1, 2, 3], 1), [1, 2, 3])
                self.assertEqual(moving_average([1, 2, 3], 3), [2])

            def test_windows_do_not_inherit_rounding_error(self):
                out = moving_average([0.1] * 6 + [0.0] * 6, 3)
                self.assertEqual(len(out), 10)
                self.assertAlmostEqual(out[0], 0.1, places=12)
                self.assertAlmostEqual(out[3], 0.1, places=12)
                self.assertEqual(out[-1], 0.0)
                self.assertEqual(out[-2], 0.0)
                self.assertEqual(out[-3], 0.0)
                big = moving_average([0.1] * 400 + [0.0] * 400, 5)
                self.assertEqual(big[-1], 0.0)
                self.assertTrue(all(abs(v - 0.1) < 1e-12 for v in big[:396]))
                self.assertEqual(big[-5:], [0.0] * 5)

            def test_edges(self):
                self.assertEqual(moving_average([1, 2], 3), [])
                self.assertEqual(moving_average([], 1), [])
                for k in (0, -2):
                    with self.assertRaises(ValueError):
                        moving_average([1, 2, 3], k)


        class Bins(unittest.TestCase):
            def test_boundaries_belong_to_the_upper_bin(self):
                self.assertEqual(bin_index(0.3, 0.0, 0.9, 3), 1)
                self.assertEqual(bin_index(0.6, 0.0, 0.9, 3), 2)
                self.assertEqual(bin_index(0.1, 0.0, 0.3, 3), 1)
                self.assertEqual(bin_index(0.2, 0.0, 0.3, 3), 2)
                self.assertEqual(bin_index(0.7, 0.1, 0.9, 4), 3)
                self.assertEqual(bin_index(0.29, 0.0, 0.58, 2), 1)

            def test_ends(self):
                self.assertEqual(bin_index(0, 0, 10, 5), 0)
                self.assertEqual(bin_index(10, 0, 10, 5), 4)
                self.assertEqual(bin_index(9.999, 0, 10, 5), 4)
                self.assertEqual(bin_index(-1.5, -3, 0, 3), 1)

            def test_outside(self):
                for x in (-0.1, 10.1):
                    with self.assertRaises(ValueError):
                        bin_index(x, 0, 10, 5)


        class Closeness(unittest.TestCase):
            def test_tolerances(self):
                self.assertTrue(approx_equal(0.1 + 0.2, 0.3))
                self.assertTrue(approx_equal(1e10, 1e10 + 1.0))
                self.assertFalse(approx_equal(1.0, 1.1))
                self.assertFalse(approx_equal(1e-12, 0.0))
                self.assertTrue(approx_equal(1e-12, 0.0, abs_tol=1e-9))
                self.assertTrue(approx_equal(100.0, 101.0, rel=0.02))
                self.assertFalse(approx_equal(100.0, 103.0, rel=0.02))
                self.assertTrue(approx_equal(float("inf"), float("inf")))
                self.assertFalse(approx_equal(float("nan"), float("nan")))


        class PercentChange(unittest.TestCase):
            def test_values(self):
                self.assertEqual(percent_change(50, 75), 50)
                self.assertEqual(percent_change(-50, -25), 50)
                self.assertEqual(percent_change(200, 100), -50)
                self.assertEqual(percent_change(80, 80), 0)

            def test_zero_baseline(self):
                self.assertIsNone(percent_change(0, 5))
                self.assertIsNone(percent_change(0.0, 0.0))


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["approx"] = (
        "`approx_equal(0.1 + 0.2, 0.3)` says False and so does comparing readings from two sensors that differ in the last bit. The helper is supposed to have "
        "`math.isclose` semantics, with the relative and absolute tolerances from the README."
    )
    p["pct-zero"] = lambda c: (
        "A newly installed sensor (baseline 0) crashes the report generator:\n\n```\n"
        + c.bad_run("from sensorstats.stats import percent_change\npercent_change(0, 5)\n").splitlines()[-1]
        + "\n```\n\nThe README says the change is `None` when the old value is 0."
    )
    p["mean"] = lambda c: (
        "The average of ten readings of 0.1 shows as "
        + c.probe("from sensorstats.stats import mean\nprint(mean([0.1] * 10))\n")[1]
        + " on the dashboard, and alerts that compare it with the nominal 0.1 fire every night. The README says the sum must be exact "
        "(`math.fsum`)."
    )
    p["bins"] = (
        "Histogram counts are off by one for readings exactly on a bin boundary: with the range 0 to 0.9 in three bins the reading 0.3 should be in bin 1 "
        "(boundaries belong to the upper bin) but lands in bin 0, while 0.6 is fine. It looks like a floating point rounding problem in the bin "
        "computation."
    )
    p["moving"] = (
        "The 5-point moving average of a signal that drops to exactly zero keeps showing tiny non-zero values (like 8e-18) long after the "
        "input is all zeros, and plateaus of 0.1 come out as 0.10000000000000002. Each window should be computed from its own values."
    )
    p["variance"] = (
        "Variance of readings around 1e9 (a counter with small jitter) comes out as 0 or even negative: `variance([1e9 + 1, 1e9 + 2, 1e9 + 3])` should be "
        "0.666... Spreads of such series are wrong, small-valued series are fine."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "sensorstats/__init__.py": '"""Sensor statistics."""\n', "sensorstats/stats.py": A_STATS}
    s = "sensorstats/stats.py"
    bugs = [
        Bug("approx-equal-is-exact-equality", 1, {s: [("    return math.isclose(a, b, rel_tol=rel, abs_tol=abs_tol)\n", "    return a == b\n")]}, P["approx"]),
        Bug("percent-change-divides-by-zero", 1, {s: [("    if old == 0:\n        return None\n", "")]}, P["pct-zero"]),
        Bug("mean-uses-plain-sum", 3, {s: [("    return math.fsum(values) / len(values)\n", "    return sum(values) / len(values)\n")]}, P["mean"]),
        Bug("bins-computed-in-binary-floats", 3, {s: [("    x, lo, hi = Decimal(str(x)), Decimal(str(lo)), Decimal(str(hi))\n", "    x, lo, hi = float(x), float(lo), float(hi)\n")]}, P["bins"]),
        Bug("moving-average-updates-a-running-sum", 4, {s: [("    return [math.fsum(values[i:i + k]) / k for i in range(len(values) - k + 1)]\n",
                                                             "    out = []\n    total = 0.0\n    for i, v in enumerate(values):\n        total += v\n        if i >= k:\n            total -= values[i - k]\n        if i >= k - 1:\n            out.append(total / k)\n    return out\n")]}, P["moving"]),
        Bug("variance-by-the-textbook-shortcut", 4, {s: [("    m = mean(values)\n    return math.fsum((x - m) ** 2 for x in values) / len(values)\n", "    return mean([x * x for x in values]) - mean(values) ** 2\n")]}, P["variance"]),
    ]
    return Base("sensorstats", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (rust): number helpers for a ledger tool.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # numkit

    Number helpers (Rust, no dependencies).

    * `to_cents(amount)`: a money amount in euros as whole cents, **rounded to the nearest cent** (halves away from zero): `0.29` is 29, `-0.29` is -29.
    * `approx_eq(a, b, eps)`: true when `a == b` (equal infinities included) or both are finite and `|a - b| <= eps * max(1, |a|, |b|)`; never true with a NaN, and
      an infinity is only equal to itself.
    * `mean_f32(xs)`: mean of `f32` values, **accumulated in `f64`** and converted back (a million values of `0.1f32` average to `0.1f32`); `0.0` for no values.
    * `median(values)`: the median of the numbers (the mean of the two middle ones for an even count); **NaN values are ignored**; `None` when nothing is left.
    * `argmax(xs)`: index of the largest value, the **first** one on ties; NaN values are ignored; `None` when there is no number.
''')

B_LIB = dd('''
    //! Number helpers.

    pub fn to_cents(amount: f64) -> i64 {
        (amount * 100.0).round() as i64
    }

    pub fn approx_eq(a: f64, b: f64, eps: f64) -> bool {
        a == b || (a.is_finite() && b.is_finite() && (a - b).abs() <= eps * 1.0_f64.max(a.abs()).max(b.abs()))
    }

    pub fn mean_f32(xs: &[f32]) -> f32 {
        if xs.is_empty() {
            return 0.0;
        }
        let sum: f64 = xs.iter().map(|&x| x as f64).sum();
        (sum / xs.len() as f64) as f32
    }

    pub fn median(values: &[f64]) -> Option<f64> {
        let mut v: Vec<f64> = values.iter().copied().filter(|x| !x.is_nan()).collect();
        if v.is_empty() {
            return None;
        }
        v.sort_by(|a, b| a.total_cmp(b));
        let mid = v.len() / 2;
        Some(if v.len() % 2 == 1 { v[mid] } else { (v[mid - 1] + v[mid]) / 2.0 })
    }

    pub fn argmax(xs: &[f64]) -> Option<usize> {
        let mut best: Option<usize> = None;
        for (i, &x) in xs.iter().enumerate() {
            if x.is_nan() {
                continue;
            }
            match best {
                Some(b) if xs[b] >= x => {}
                _ => best = Some(i),
            }
        }
        best
    }
''')

B_VISIBLE = {
    "tests/basic.rs": dd('''
        use numkit::*;

        #[test]
        fn easy_values() {
            assert_eq!(to_cents(12.5), 1250);
            assert!(approx_eq(1.0, 1.0, 1e-9));
            assert_eq!(mean_f32(&[1.0, 2.0, 3.0]), 2.0);
            assert_eq!(median(&[3.0, 1.0, 2.0]), Some(2.0));
            assert_eq!(argmax(&[1.0, 5.0, 2.0]), Some(1));
        }
    '''),
}

B_HIDDEN = {
    "tests/hidden_numkit.rs": dd('''
        use numkit::*;

        #[test]
        fn cents_are_rounded_not_truncated() {
            assert_eq!(to_cents(0.29), 29);
            assert_eq!(to_cents(0.57), 57);
            assert_eq!(to_cents(1.15), 115);
            assert_eq!(to_cents(19.99), 1999);
            assert_eq!(to_cents(-0.29), -29);
            assert_eq!(to_cents(-19.99), -1999);
            assert_eq!(to_cents(0.005), 1);
            assert_eq!(to_cents(-0.005), -1);
            assert_eq!(to_cents(0.0), 0);
            assert_eq!(to_cents(1234.56), 123456);
            assert_eq!(to_cents(0.004), 0);
        }

        #[test]
        fn approximate_equality() {
            assert!(approx_eq(0.1 + 0.2, 0.3, 1e-9));
            assert!(approx_eq(1e10, 1e10 + 1.0, 1e-9));
            assert!(approx_eq(0.0, 1e-12, 1e-9));
            assert!(!approx_eq(1.0, 1.1, 1e-9));
            assert!(approx_eq(1.0, 1.1, 0.2));
            assert!(approx_eq(f64::INFINITY, f64::INFINITY, 1e-9));
            assert!(!approx_eq(f64::INFINITY, f64::NEG_INFINITY, 1e-9));
            assert!(!approx_eq(f64::NAN, f64::NAN, 1e-9));
            assert!(!approx_eq(f64::NAN, 1.0, 1e9));
        }

        #[test]
        fn mean_accumulates_in_double_precision() {
            let xs = vec![0.1f32; 1_000_000];
            assert_eq!(mean_f32(&xs), 0.1f32);
            assert_eq!(mean_f32(&[]), 0.0);
            assert_eq!(mean_f32(&[1.5, 2.5]), 2.0);
            let big = vec![16_777_216.0f32, 1.0, 1.0, 1.0, 1.0];
            assert!((mean_f32(&big) - 3_355_443.8).abs() < 1.0);
        }

        #[test]
        fn median_ignores_nan() {
            assert_eq!(median(&[3.0, f64::NAN, 1.0, 2.0]), Some(2.0));
            assert_eq!(median(&[f64::NAN, f64::NAN]), None);
            assert_eq!(median(&[]), None);
            assert_eq!(median(&[4.0, 1.0, 3.0, 2.0]), Some(2.5));
            assert_eq!(median(&[7.0]), Some(7.0));
            assert_eq!(median(&[f64::NAN, 5.0]), Some(5.0));
            assert_eq!(median(&[f64::INFINITY, 1.0, f64::NEG_INFINITY]), Some(1.0));
            assert_eq!(median(&[-0.5, 0.5]), Some(0.0));
        }

        #[test]
        fn argmax_first_of_the_largest() {
            assert_eq!(argmax(&[1.0, 3.0, 3.0, 2.0]), Some(1));
            assert_eq!(argmax(&[5.0, 5.0]), Some(0));
            assert_eq!(argmax(&[f64::NAN, 2.0, f64::NAN, 2.0]), Some(1));
            assert_eq!(argmax(&[f64::NAN]), None);
            assert_eq!(argmax(&[]), None);
            assert_eq!(argmax(&[-3.0, -1.0, -2.0]), Some(1));
            assert_eq!(argmax(&[f64::NEG_INFINITY, f64::NEG_INFINITY]), Some(0));
        }
    '''),
}


def _b_prompts():
    p = {}
    p["cents"] = (
        "Invoices for 0.29 EUR come out as 28 cents and 19.99 as 1998: `to_cents` truncates instead of rounding. Only amounts whose binary representation "
        "is slightly below the decimal value are affected, which is why the test with 12.5 passed."
    )
    p["median-nan"] = lambda c: (
        "The statistics page panics when a sensor sends a NaN reading:\n\n```\n"
        + panic_excerpt(
            c.bad_run("use numkit::median;\n\n#[test]\nfn nan_reading() {\n    assert_eq!(median(&[3.0, f64::NAN, 1.0, 2.0]), Some(2.0));\n}\n",
                      cmd="cargo test --offline --quiet --test probe 2>&1", name="tests/probe.rs"))
        + "\n```\n\nThe documented behaviour is that NaN values are ignored."
    )
    p["mean32"] = (
        "The average of a million `0.1f32` samples comes out as 0.10095 instead of 0.1: the running sum loses precision once it gets large. The mean "
        "must be accumulated in double precision."
    )
    p["approx"] = (
        "`approx_eq(0.1 + 0.2, 0.3, 1e-9)` is false, so our unit conversion checks fail on perfectly good values. The comparison is supposed to use "
        "the tolerance from the README."
    )
    p["argmax"] = (
        "When several samples share the maximum, `argmax` reports the last of them, but the UI highlights the first peak. The first index must win."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "Cargo.toml": langs.cargo_toml("numkit"), "src/lib.rs": B_LIB}
    lib = "src/lib.rs"
    bugs = [
        Bug("approx-eq-is-exact", 1, {lib: [("    a == b || (a.is_finite() && b.is_finite() && (a - b).abs() <= eps * 1.0_f64.max(a.abs()).max(b.abs()))\n", "    a == b\n")]}, P["approx"]),
        Bug("cents-truncated", 2, {lib: [("    (amount * 100.0).round() as i64\n", "    (amount * 100.0) as i64\n")]}, P["cents"]),
        Bug("argmax-prefers-the-last-tie", 1, {lib: [("            Some(b) if xs[b] >= x => {}\n", "            Some(b) if xs[b] > x => {}\n")]}, P["argmax"]),
        Bug("mean-accumulated-in-f32", 3, {lib: [("    let sum: f64 = xs.iter().map(|&x| x as f64).sum();\n    (sum / xs.len() as f64) as f32\n", "    let sum: f32 = xs.iter().sum();\n    sum / xs.len() as f32\n")]}, P["mean32"]),
        Bug("median-sorts-with-partial-cmp", 3, {lib: [("    let mut v: Vec<f64> = values.iter().copied().filter(|x| !x.is_nan()).collect();\n", "    let mut v: Vec<f64> = values.to_vec();\n"),
                                                       ("    v.sort_by(|a, b| a.total_cmp(b));\n", "    v.sort_by(|a, b| a.partial_cmp(b).unwrap());\n")]}, P["median-nan"]),
    ]
    return Base("numkit", "rust", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-float-accum", category="fix", lang="python", kind="fix", n=11,
        summary="floating point: exact sums, bin edges, cancellation, exact equality, NaN (python stats kit, rust number helpers)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
