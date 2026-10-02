"""Log-linear latency histogram (rust): bucket arithmetic, quantiles clamped to the observed range, merging."""
from fx import Lib, dd

from generators.fix._lang1 import CARGO_CONFIG, cargo, register_libs

README = dd('''
    # loghist

    A fixed-memory histogram for request latencies (in microseconds, but any `u64` works). Recording is O(1), memory is a few
    thousand counters, and every value is stored with a bounded relative error.

    ## Bucket layout
    `Histogram::new(sub_bits, max_value)` with `1 <= sub_bits <= 10` and `max_value >= 1` (otherwise
    `Err(HistError::BadConfig)`). Let `S = 2^sub_bits`.

    * Values below `2S` each have their own bucket: `bucket_index(v) = v`.
    * A larger value `v` has `e = floor(log2(v))` and `shift = e - sub_bits` (so `shift >= 1`). Its bucket is
      `shift * S + (v >> shift)`. Within one power of two there are `S` buckets, each `2^shift` wide.

    For `sub_bits = 2` the indices of `0..=20` are `0 1 2 3 4 5 6 7 8 8 9 9 10 10 11 11 12 12 12 12 13`.

    * `bucket_index(&self, v: u64) -> usize` as above (it does not check `max_value`).
    * `lower_bound(&self, idx: usize) -> u64`: the smallest value in the bucket. For `idx < 2S` it is `idx`; otherwise
      `shift = idx / S - 1` and the bound is `(idx % S + S) << shift`.
    * `upper_bound(&self, idx: usize) -> u64`: the largest value in the bucket, i.e. one less than the next bucket's lower bound,
      and never more than `u64::MAX` (the bound of the last bucket of a histogram covering `u64::MAX` must not overflow).
    * `bucket_count(&self) -> usize`: `bucket_index(max_value) + 1`.

    ## Recording
    * `record(v) -> Result<(), HistError>` and `record_n(v, n)` (n copies; `n == 0` records nothing but still checks `v`).
      `v > max_value` is `Err(HistError::OutOfRange)` and changes nothing.
    * `count() -> u64`, `min() -> Option<u64>`, `max() -> Option<u64>` (exact observed values), `mean() -> Option<u64>`
      (exact sum divided by the count, rounded down; the sum may exceed `u64`). All `None` when empty.

    ## `quantile(&self, permille: u32) -> Option<u64>`
    `None` when empty. `permille` above 1000 counts as 1000. `0` gives the exact minimum and `1000` the exact maximum. For
    other values `rank = max(1, ceil(count * permille / 1000))`; walk the buckets in ascending order accumulating counts and stop at
    the first bucket whose running total reaches `rank`. The answer is that bucket's upper bound, but never above the observed
    maximum.

    ## Other operations
    * `buckets(&self) -> Vec<(u64, u64, u64)>`: `(lower, upper, count)` for every non-empty bucket, ascending.
    * `merge(&mut self, other: &Histogram) -> Result<(), HistError>`: adds the other's counts; both must have the same
      `sub_bits` and `max_value`, otherwise `Err(HistError::Mismatch)`. Merging gives the same histogram as recording all
      values in one.
    * `reset(&mut self)`: forgets everything, keeps the configuration.
''')

SRC = dd('''
    //! A log-linear histogram.

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum HistError {
        BadConfig,
        OutOfRange,
        Mismatch,
    }

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub struct Histogram {
        sub_bits: u32,
        max_value: u64,
        counts: Vec<u64>,
        total: u64,
        sum: u128,
        min: u64,
        max: u64,
    }

    fn index_for(sub_bits: u32, v: u64) -> usize {
        let s = 1u64 << sub_bits;
        if v < 2 * s {
            return v as usize;
        }
        let e = 63 - v.leading_zeros();
        let shift = e - sub_bits;
        (shift as u64 * s + (v >> shift)) as usize
    }

    impl Histogram {
        pub fn new(sub_bits: u32, max_value: u64) -> Result<Histogram, HistError> {
            if sub_bits < 1 || sub_bits > 10 || max_value < 1 {
                return Err(HistError::BadConfig);
            }
            let n = index_for(sub_bits, max_value) + 1;
            Ok(Histogram { sub_bits, max_value, counts: vec![0; n], total: 0, sum: 0, min: u64::MAX, max: 0 })
        }

        pub fn bucket_index(&self, v: u64) -> usize {
            index_for(self.sub_bits, v)
        }

        pub fn bucket_count(&self) -> usize {
            self.counts.len()
        }

        fn lower_wide(&self, idx: usize) -> u128 {
            let s = 1usize << self.sub_bits;
            if idx < 2 * s {
                return idx as u128;
            }
            let shift = idx / s - 1;
            ((idx % s + s) as u128) << shift
        }

        pub fn lower_bound(&self, idx: usize) -> u64 {
            self.lower_wide(idx) as u64
        }

        pub fn upper_bound(&self, idx: usize) -> u64 {
            let next = self.lower_wide(idx + 1);
            (next - 1).min(u64::MAX as u128) as u64
        }

        pub fn record(&mut self, v: u64) -> Result<(), HistError> {
            self.record_n(v, 1)
        }

        pub fn record_n(&mut self, v: u64, n: u64) -> Result<(), HistError> {
            if v > self.max_value {
                return Err(HistError::OutOfRange);
            }
            if n == 0 {
                return Ok(());
            }
            let idx = self.bucket_index(v);
            self.counts[idx] += n;
            self.total += n;
            self.sum += v as u128 * n as u128;
            self.min = self.min.min(v);
            self.max = self.max.max(v);
            Ok(())
        }

        pub fn count(&self) -> u64 {
            self.total
        }

        pub fn min(&self) -> Option<u64> {
            if self.total == 0 { None } else { Some(self.min) }
        }

        pub fn max(&self) -> Option<u64> {
            if self.total == 0 { None } else { Some(self.max) }
        }

        pub fn mean(&self) -> Option<u64> {
            if self.total == 0 {
                return None;
            }
            Some((self.sum / self.total as u128) as u64)
        }

        pub fn quantile(&self, permille: u32) -> Option<u64> {
            if self.total == 0 {
                return None;
            }
            let p = permille.min(1000) as u128;
            if p == 0 {
                return Some(self.min);
            }
            if p == 1000 {
                return Some(self.max);
            }
            let rank = ((self.total as u128 * p + 999) / 1000).max(1) as u64;
            let mut seen = 0u64;
            for (idx, &c) in self.counts.iter().enumerate() {
                seen += c;
                if seen >= rank {
                    return Some(self.upper_bound(idx).min(self.max));
                }
            }
            Some(self.max)
        }

        pub fn buckets(&self) -> Vec<(u64, u64, u64)> {
            let mut out = Vec::new();
            for (idx, &c) in self.counts.iter().enumerate() {
                if c > 0 {
                    out.push((self.lower_bound(idx), self.upper_bound(idx), c));
                }
            }
            out
        }

        pub fn merge(&mut self, other: &Histogram) -> Result<(), HistError> {
            if self.sub_bits != other.sub_bits || self.max_value != other.max_value {
                return Err(HistError::Mismatch);
            }
            for (mine, theirs) in self.counts.iter_mut().zip(&other.counts) {
                *mine += *theirs;
            }
            self.total += other.total;
            self.sum += other.sum;
            self.min = self.min.min(other.min);
            self.max = self.max.max(other.max);
            Ok(())
        }

        pub fn reset(&mut self) {
            self.counts.iter_mut().for_each(|c| *c = 0);
            self.total = 0;
            self.sum = 0;
            self.min = u64::MAX;
            self.max = 0;
        }
    }
''')

VISIBLE = dd('''
    use loghist::*;

    #[test]
    fn small_values_have_their_own_bucket() {
        let h = Histogram::new(2, 1_000_000).unwrap();
        for v in 0..8u64 {
            assert_eq!(h.bucket_index(v), v as usize);
        }
    }

    #[test]
    fn records_and_counts() {
        let mut h = Histogram::new(3, 1000).unwrap();
        h.record(5).unwrap();
        h.record(7).unwrap();
        assert_eq!(h.count(), 2);
        assert_eq!(h.min(), Some(5));
    }
''')

HIDDEN = dd('''
    use loghist::*;

    fn hist(sub_bits: u32, max: u64, values: &[u64]) -> Histogram {
        let mut h = Histogram::new(sub_bits, max).unwrap();
        for &v in values {
            h.record(v).unwrap();
        }
        h
    }

    fn skewed() -> Vec<u64> {
        let mut v = vec![100u64; 50];
        v.extend([1000u64; 30]);
        v.extend([10000u64; 15]);
        v.extend([100000u64; 5]);
        v
    }

    #[test]
    fn config_validation() {
        assert_eq!(Histogram::new(0, 100).unwrap_err(), HistError::BadConfig);
        assert_eq!(Histogram::new(11, 100).unwrap_err(), HistError::BadConfig);
        assert_eq!(Histogram::new(3, 0).unwrap_err(), HistError::BadConfig);
        assert!(Histogram::new(1, 1).is_ok());
        assert!(Histogram::new(10, u64::MAX).is_ok());
        assert!(Histogram::new(4, 1).is_ok());
    }

    #[test]
    fn index_table_two_sub_bits() {
        let h = Histogram::new(2, u64::MAX).unwrap();
        let want = [
            0usize, 1, 2, 3, 4, 5, 6, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 12, 12, 13, 13, 13, 13, 14, 14, 14, 14, 15, 15, 15, 15, 16, 16,
            16, 16, 16, 16, 16, 16,
        ];
        for (v, &w) in want.iter().enumerate() {
            assert_eq!(h.bucket_index(v as u64), w, "bucket_index({v})");
        }
    }

    #[test]
    fn bounds_table_two_sub_bits() {
        let h = Histogram::new(2, u64::MAX).unwrap();
        let want = [
            (0u64, 0u64), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 9), (10, 11), (12, 13), (14, 15), (16, 19), (20, 23),
            (24, 27), (28, 31), (32, 39), (40, 47), (48, 55), (56, 63),
        ];
        for (idx, &(lo, hi)) in want.iter().enumerate() {
            assert_eq!(h.lower_bound(idx), lo, "lower_bound({idx})");
            assert_eq!(h.upper_bound(idx), hi, "upper_bound({idx})");
        }
    }

    #[test]
    fn large_values() {
        let h = Histogram::new(3, u64::MAX).unwrap();
        assert_eq!(h.bucket_index(1u64 << 40), 304);
        assert_eq!(h.lower_bound(304), 1u64 << 40);
        assert_eq!(h.upper_bound(h.bucket_index((1u64 << 40) + 12345)), 1236950581247);
        let h = Histogram::new(4, u64::MAX).unwrap();
        assert_eq!(h.bucket_index(u64::MAX), 975);
        assert_eq!(h.lower_bound(975), 17870283321406128128);
        assert_eq!(h.upper_bound(975), u64::MAX);
        assert_eq!(h.bucket_count(), 976);
    }

    #[test]
    fn every_value_sits_inside_its_bucket() {
        for sub_bits in [1u32, 2, 3, 5, 10] {
            let h = Histogram::new(sub_bits, u64::MAX).unwrap();
            let mut x = 0x9E37_79B9_7F4A_7C15u64;
            let mut values: Vec<u64> = (0..3000).collect();
            for _ in 0..500 {
                x ^= x << 13;
                x ^= x >> 7;
                x ^= x << 17;
                values.push(x >> (x % 60));
            }
            values.push(u64::MAX);
            values.push(1 << 63);
            for v in values {
                let i = h.bucket_index(v);
                assert!(h.lower_bound(i) <= v && v <= h.upper_bound(i), "sub_bits {sub_bits}, v {v}");
                assert_eq!(h.bucket_index(h.lower_bound(i)), i);
                assert_eq!(h.bucket_index(h.upper_bound(i)), i);
                if i + 1 < h.bucket_count() {
                    assert_eq!(h.upper_bound(i) + 1, h.lower_bound(i + 1));
                }
            }
        }
    }

    #[test]
    fn bucket_count_follows_max_value() {
        assert_eq!(Histogram::new(2, 7).unwrap().bucket_count(), 8);
        assert_eq!(Histogram::new(2, 8).unwrap().bucket_count(), 9);
        assert_eq!(Histogram::new(2, 63).unwrap().bucket_count(), 20);
        assert_eq!(Histogram::new(2, 64).unwrap().bucket_count(), 21);
        assert_eq!(Histogram::new(3, 1_000_000).unwrap().bucket_count(), 144);
    }

    #[test]
    fn empty_histogram() {
        let h = Histogram::new(3, 1000).unwrap();
        assert_eq!((h.count(), h.min(), h.max(), h.mean()), (0, None, None, None));
        for p in [0, 1, 500, 1000, 5000] {
            assert_eq!(h.quantile(p), None);
        }
        assert!(h.buckets().is_empty());
    }

    #[test]
    fn range_check() {
        let mut h = Histogram::new(3, 1000).unwrap();
        assert_eq!(h.record(1001), Err(HistError::OutOfRange));
        assert_eq!(h.record_n(5000, 0), Err(HistError::OutOfRange));
        assert_eq!(h.count(), 0);
        assert!(h.record(1000).is_ok());
        assert!(h.record(0).is_ok());
        assert_eq!(h.count(), 2);
        assert_eq!((h.min(), h.max()), (Some(0), Some(1000)));
    }

    #[test]
    fn record_n_matches_repeated_record() {
        let mut a = Histogram::new(3, 100_000).unwrap();
        a.record_n(777, 5).unwrap();
        a.record_n(3, 2).unwrap();
        a.record_n(9, 0).unwrap();
        let b = hist(3, 100_000, &[777, 777, 777, 777, 777, 3, 3]);
        assert_eq!(a, b);
        assert_eq!(a.min(), Some(3));
        assert_eq!(a.count(), 7);
    }

    #[test]
    fn mean_is_exact_and_rounded_down() {
        let h = hist(3, 1_000_000, &[1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946]);
        assert_eq!(h.mean(), Some(1432));
        assert_eq!(hist(2, 100, &[1, 2]).mean(), Some(1));
        assert_eq!(hist(2, 100, &[7]).mean(), Some(7));
        assert_eq!(hist(2, 100, &[0, 0, 1]).mean(), Some(0));
        let mut big = Histogram::new(5, u64::MAX).unwrap();
        big.record_n(u64::MAX, 4).unwrap();
        assert_eq!(big.mean(), Some(u64::MAX));
        assert_eq!(big.count(), 4);
    }

    #[test]
    fn quantile_table_fibonacci() {
        let h = hist(3, 1_000_000, &[1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946]);
        let want = [(0, 1), (1, 1), (100, 2), (250, 8), (500, 95), (750, 1023), (900, 4607), (950, 7167), (990, 10946), (999, 10946), (1000, 10946)];
        for (p, w) in want {
            assert_eq!(h.quantile(p), Some(w), "quantile({p})");
        }
        assert_eq!(h.quantile(1001), Some(10946));
        assert_eq!(h.quantile(u32::MAX), Some(10946));
    }

    #[test]
    fn quantile_clamps_to_the_observed_range() {
        let h = hist(2, 1_000_000, &skewed());
        let want = [(0, 100), (1, 111), (500, 111), (501, 1023), (800, 1023), (801, 10239), (950, 10239), (951, 100000), (990, 100000), (999, 100000), (1000, 100000)];
        for (p, w) in want {
            assert_eq!(h.quantile(p), Some(w), "quantile({p})");
        }
        // the bucket of 100 is [96, 111]: a single sample at 100 reports 100, not 111
        assert_eq!(hist(2, 1_000_000, &[100]).quantile(500), Some(100));
        assert_eq!(hist(2, 1_000_000, &[100, 105]).quantile(10), Some(105));
        // the upper bound is clamped to the maximum seen
        assert_eq!(hist(2, 1_000_000, &[110, 100]).quantile(1), Some(110));
    }

    #[test]
    fn quantile_rank_rounds_up() {
        // three samples: rank for 334 permille is ceil(1.002) = 2
        let h = hist(3, 100, &[10, 20, 30]);
        assert_eq!(h.quantile(333), Some(10));
        assert_eq!(h.quantile(334), Some(21)); // bucket [20, 21]
        assert_eq!(h.quantile(666), Some(21));
        assert_eq!(h.quantile(667), Some(30));
        assert_eq!(h.quantile(1), Some(10));
        let one = hist(3, 100, &[42]);
        for p in [0, 1, 500, 999, 1000] {
            assert_eq!(one.quantile(p), Some(42));
        }
    }

    #[test]
    fn bucket_listing() {
        let h = hist(2, 1_000_000, &skewed());
        assert_eq!(h.buckets(), vec![(96, 111, 50), (896, 1023, 30), (8192, 10239, 15), (98304, 114687, 5)]);
        let small = hist(2, 100, &[3, 3, 8, 9]);
        assert_eq!(small.buckets(), vec![(3, 3, 2), (8, 9, 2)]);
    }

    #[test]
    fn merge_equals_recording_everything() {
        let mut x = 12345u64;
        let mut all = Histogram::new(4, 10_000_000).unwrap();
        let mut a = Histogram::new(4, 10_000_000).unwrap();
        let mut b = Histogram::new(4, 10_000_000).unwrap();
        for i in 0..2000 {
            x = x.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            let v = (x >> 33) % 5_000_000;
            all.record(v).unwrap();
            if i % 3 == 0 { a.record(v).unwrap() } else { b.record(v).unwrap() }
        }
        a.merge(&b).unwrap();
        assert_eq!(a, all);
        for p in [0, 10, 500, 900, 990, 1000] {
            assert_eq!(a.quantile(p), all.quantile(p));
        }
        assert_eq!(a.mean(), all.mean());
    }

    #[test]
    fn merge_with_empty_and_into_empty() {
        let full = hist(3, 1000, &[5, 500]);
        let empty = Histogram::new(3, 1000).unwrap();
        let mut a = full.clone();
        a.merge(&empty).unwrap();
        assert_eq!(a, full);
        let mut e = empty.clone();
        e.merge(&full).unwrap();
        assert_eq!(e, full);
        assert_eq!((e.min(), e.max()), (Some(5), Some(500)));
    }

    #[test]
    fn merge_mismatch() {
        let mut a = Histogram::new(3, 1000).unwrap();
        a.record(5).unwrap();
        assert_eq!(a.merge(&Histogram::new(4, 1000).unwrap()), Err(HistError::Mismatch));
        assert_eq!(a.merge(&Histogram::new(3, 2000).unwrap()), Err(HistError::Mismatch));
        assert_eq!(a.count(), 1);
    }

    #[test]
    fn reset_keeps_configuration() {
        let mut h = hist(3, 1000, &[5, 500, 1000]);
        h.reset();
        assert_eq!((h.count(), h.min(), h.max(), h.mean()), (0, None, None, None));
        assert!(h.buckets().is_empty());
        assert_eq!(h.record(1001), Err(HistError::OutOfRange));
        h.record(7).unwrap();
        assert_eq!((h.min(), h.max()), (Some(7), Some(7)));
        assert_eq!(h, hist(3, 1000, &[7]));
    }
''')

LIB = Lib(
    name="loghist", lang="rust", title="the loghist crate",
    blurb="The metrics agent records request latencies with loghist, a fixed-memory log-linear histogram with percentile queries.",
    files={"Cargo.toml": cargo("loghist"), "src/lib.rs": SRC, "README.md": README, ".gitignore": "target/\n", ".cargo/config.toml": CARGO_CONFIG},
    visible_tests={"tests/basic.rs": VISIBLE},
    hidden_tests={"tests/full.rs": HIDDEN},
    mutate=["src/lib.rs"], difficulty=3, tags=["metrics", "histogram", "percentiles"],
)

register_libs([LIB], n=8)
