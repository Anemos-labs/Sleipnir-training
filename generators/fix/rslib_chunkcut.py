"""Content-defined chunking (rust): gear rolling hash, normalised cut masks, streaming chunker, dedup store."""
from fx import Lib, dd

from generators.fix._lang1 import CARGO_CONFIG, cargo, register_libs

README = dd('''
    # chunkcut

    Content-defined chunking for the backup tool's dedup store: a byte stream is cut into variable-size chunks whose boundaries depend
    on the *content*, so inserting a byte near the start of a file only disturbs the chunks around it.

    ## Gear table
    `gear_table() -> [u64; 256]` is the table of per-byte random values: the first 256 outputs of splitmix64 started from state 0
    (`state += 0x9E3779B97F4A7C15`, then `z = state; z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9; z = (z ^ (z >> 27)) * 0x94D049BB133111EB;
    output z ^ (z >> 31)`, all arithmetic wrapping modulo 2^64). Entry `i` is the output for byte value `i`.

    ## `Chunker::new(min: usize, avg_bits: u32, max: usize) -> Result<Chunker, ChunkError>`
    Checked in this order: `min == 0` is `Err(ZeroMin)`; `avg_bits` outside `2..=20` is `Err(BadBits)`; `min > max` is `Err(BadRange)`.
    (`min == max` is allowed and gives fixed-size chunks.) With `normal = 1 << avg_bits`, two masks are derived:
    `strict = (1 << (avg_bits + 1)) - 1` and `loose = (1 << (avg_bits - 1)) - 1`.

    ## Finding a boundary
    `find(&self, data: &[u8]) -> Option<usize>` looks for the end of the first chunk of `data` and returns `Some(len)` only when that
    boundary is *determined* by the bytes given, `None` when more input could still move it:

    * the rolling hash `h` starts at 0 at offset `min`: bytes before offset `min` are skipped and never hashed;
    * for each byte at offset `i`, from `min` up to (excluding) `min(data.len(), max)`: `h = (h << 1) + gear[data[i]]` (wrapping), and if
      `h & mask == 0` the chunk ends after this byte, so `find` returns `Some(i + 1)`. `mask` is `strict` while the chunk would still be
      shorter than `normal` (`i + 1 < normal`) and `loose` from then on;
    * if no byte matched and `data.len() >= max`, the chunk is cut at `max`: `Some(max)`;
    * otherwise `None`.

    `cut(&self, data) -> usize` is `find` with the end of the data as the fallback (`data.len()` when `find` says `None`).
    `chunks(&self, data) -> Vec<Range<usize>>` cuts all of `data`, repeatedly applying `cut` to what is left; the ranges tile the data
    in order and empty data gives no ranges.

    ## `Stream`
    The same chunking for input that arrives in pieces. `Stream::new(chunker)`; `push(&mut self, bytes) -> Vec<Vec<u8>>` appends the bytes
    to what is pending and returns every chunk whose boundary is now determined (in order, possibly none); `pending(&self) -> usize` is the
    number of bytes held back; `finish(self) -> Option<Vec<u8>>` returns the held-back tail as the last chunk (`None` when nothing is
    pending). Concatenating everything `push` returned and the `finish` tail always gives exactly the chunks `Chunker::chunks` makes of
    the whole input, however it was split into pushes.

    ## `Store`
    A dedup store that only remembers chunk contents. `Store::new(chunker)`. `ingest(&mut self, data) -> Ingest` chunks `data` on its own (nothing
    carries over between calls) and reports `Ingest { chunks, new_chunks, bytes, new_bytes }`: the number of chunks, how many of them had
    not been seen before (a chunk repeated inside the same `data` is new only the first time), the length of `data` and the total size of
    the new chunks. Accessors: `chunks()` and `bytes()` count everything ever ingested; `unique_chunks()` and `unique_bytes()` count each
    distinct chunk once; `contains(&self, chunk: &[u8]) -> bool`; `saved_permille(&self) -> u64` is `(bytes - unique_bytes) * 1000 / bytes`
    rounded down, and 0 for an empty store.
''')

SRC = dd('''
    //! Content-defined chunking with a gear hash.

    use std::collections::HashSet;
    use std::ops::Range;

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub enum ChunkError {
        ZeroMin,
        BadBits,
        BadRange,
    }

    pub fn gear_table() -> [u64; 256] {
        let mut table = [0u64; 256];
        let mut state: u64 = 0;
        for slot in table.iter_mut() {
            state = state.wrapping_add(0x9E37_79B9_7F4A_7C15);
            let mut z = state;
            z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
            z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
            *slot = z ^ (z >> 31);
        }
        table
    }

    #[derive(Debug, Clone)]
    pub struct Chunker {
        min: usize,
        max: usize,
        normal: usize,
        strict: u64,
        loose: u64,
        gear: [u64; 256],
    }

    impl Chunker {
        pub fn new(min: usize, avg_bits: u32, max: usize) -> Result<Chunker, ChunkError> {
            if min == 0 {
                return Err(ChunkError::ZeroMin);
            }
            if !(2..=20).contains(&avg_bits) {
                return Err(ChunkError::BadBits);
            }
            if min > max {
                return Err(ChunkError::BadRange);
            }
            Ok(Chunker {
                min,
                max,
                normal: 1usize << avg_bits,
                strict: (1u64 << (avg_bits + 1)) - 1,
                loose: (1u64 << (avg_bits - 1)) - 1,
                gear: gear_table(),
            })
        }

        pub fn find(&self, data: &[u8]) -> Option<usize> {
            let limit = data.len().min(self.max);
            let mut h: u64 = 0;
            for i in self.min..limit {
                h = (h << 1).wrapping_add(self.gear[data[i] as usize]);
                let mask = if i + 1 < self.normal { self.strict } else { self.loose };
                if h & mask == 0 {
                    return Some(i + 1);
                }
            }
            if data.len() >= self.max {
                Some(self.max)
            } else {
                None
            }
        }

        pub fn cut(&self, data: &[u8]) -> usize {
            self.find(data).unwrap_or(data.len())
        }

        pub fn chunks(&self, data: &[u8]) -> Vec<Range<usize>> {
            let mut out = Vec::new();
            let mut pos = 0;
            while pos < data.len() {
                let n = self.cut(&data[pos..]);
                out.push(pos..pos + n);
                pos += n;
            }
            out
        }
    }

    #[derive(Debug, Clone)]
    pub struct Stream {
        chunker: Chunker,
        buf: Vec<u8>,
    }

    impl Stream {
        pub fn new(chunker: Chunker) -> Stream {
            Stream { chunker, buf: Vec::new() }
        }

        pub fn push(&mut self, bytes: &[u8]) -> Vec<Vec<u8>> {
            self.buf.extend_from_slice(bytes);
            let mut out = Vec::new();
            while let Some(n) = self.chunker.find(&self.buf) {
                let rest = self.buf.split_off(n);
                out.push(std::mem::replace(&mut self.buf, rest));
            }
            out
        }

        pub fn pending(&self) -> usize {
            self.buf.len()
        }

        pub fn finish(self) -> Option<Vec<u8>> {
            if self.buf.is_empty() {
                None
            } else {
                Some(self.buf)
            }
        }
    }

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub struct Ingest {
        pub chunks: usize,
        pub new_chunks: usize,
        pub bytes: usize,
        pub new_bytes: usize,
    }

    #[derive(Debug, Clone)]
    pub struct Store {
        chunker: Chunker,
        seen: HashSet<Vec<u8>>,
        chunks: usize,
        bytes: usize,
        unique_bytes: usize,
    }

    impl Store {
        pub fn new(chunker: Chunker) -> Store {
            Store { chunker, seen: HashSet::new(), chunks: 0, bytes: 0, unique_bytes: 0 }
        }

        pub fn ingest(&mut self, data: &[u8]) -> Ingest {
            let mut report = Ingest { chunks: 0, new_chunks: 0, bytes: data.len(), new_bytes: 0 };
            for range in self.chunker.chunks(data) {
                let piece = &data[range];
                report.chunks += 1;
                if self.seen.insert(piece.to_vec()) {
                    report.new_chunks += 1;
                    report.new_bytes += piece.len();
                }
            }
            self.chunks += report.chunks;
            self.bytes += report.bytes;
            self.unique_bytes += report.new_bytes;
            report
        }

        pub fn chunks(&self) -> usize {
            self.chunks
        }

        pub fn bytes(&self) -> usize {
            self.bytes
        }

        pub fn unique_chunks(&self) -> usize {
            self.seen.len()
        }

        pub fn unique_bytes(&self) -> usize {
            self.unique_bytes
        }

        pub fn contains(&self, chunk: &[u8]) -> bool {
            self.seen.contains(chunk)
        }

        pub fn saved_permille(&self) -> u64 {
            if self.bytes == 0 {
                return 0;
            }
            ((self.bytes - self.unique_bytes) as u64 * 1000) / self.bytes as u64
        }
    }
''')

VISIBLE = dd('''
    use chunkcut::*;

    #[test]
    fn first_gear_value() {
        assert_eq!(gear_table()[0], 0xe220a8397b1dcdaf);
    }

    #[test]
    fn invalid_parameters() {
        assert_eq!(Chunker::new(0, 6, 100).unwrap_err(), ChunkError::ZeroMin);
        assert_eq!(Chunker::new(10, 6, 5).unwrap_err(), ChunkError::BadRange);
    }

    #[test]
    fn fixed_size_chunks() {
        let c = Chunker::new(8, 3, 8).unwrap();
        let data = vec![7u8; 20];
        let lens: Vec<usize> = c.chunks(&data).iter().map(|r| r.len()).collect();
        assert_eq!(lens, vec![8, 8, 4]);
    }

    #[test]
    fn short_data_is_one_chunk() {
        let c = Chunker::new(16, 6, 256).unwrap();
        assert_eq!(c.chunks(&[1, 2, 3]), vec![0..3]);
        assert!(c.chunks(&[]).is_empty());
    }
''')

HIDDEN = dd('''
    use chunkcut::*;

    fn bytes(seed: u64, n: usize) -> Vec<u8> {
        let mut st = seed;
        (0..n)
            .map(|_| {
                st ^= st >> 12;
                st ^= st << 25;
                st ^= st >> 27;
                (st.wrapping_mul(0x2545F4914F6CDD1D) >> 56) as u8
            })
            .collect()
    }

    fn lens(c: &Chunker, data: &[u8]) -> Vec<usize> {
        let ranges = c.chunks(data);
        let mut pos = 0;
        for r in &ranges {
            assert_eq!(r.start, pos, "ranges must tile the data");
            pos = r.end;
        }
        assert_eq!(pos, data.len());
        ranges.iter().map(|r| r.len()).collect()
    }

    #[test]
    fn gear_table_values() {
        let t = gear_table();
        assert_eq!(t[0], 0xe220a8397b1dcdaf);
        assert_eq!(t[1], 0x6e789e6aa1b965f4);
        assert_eq!(t[2], 0x06c45d188009454f);
        assert_eq!(t[255], 0x5a5832bb47bcf19e);
        let mut sorted = t.to_vec();
        sorted.sort();
        sorted.dedup();
        assert_eq!(sorted.len(), 256);
    }

    #[test]
    fn parameter_validation_order() {
        assert_eq!(Chunker::new(0, 1, 5).unwrap_err(), ChunkError::ZeroMin);
        assert_eq!(Chunker::new(0, 6, 100).unwrap_err(), ChunkError::ZeroMin);
        assert_eq!(Chunker::new(0, 6, 0).unwrap_err(), ChunkError::ZeroMin);
        assert_eq!(Chunker::new(5, 1, 3).unwrap_err(), ChunkError::BadBits);
        assert_eq!(Chunker::new(5, 0, 50).unwrap_err(), ChunkError::BadBits);
        assert_eq!(Chunker::new(5, 21, 50).unwrap_err(), ChunkError::BadBits);
        assert_eq!(Chunker::new(5, 30, 3).unwrap_err(), ChunkError::BadBits);
        assert_eq!(Chunker::new(5, 4, 4).unwrap_err(), ChunkError::BadRange);
        assert_eq!(Chunker::new(1000, 8, 999).unwrap_err(), ChunkError::BadRange);
        assert!(Chunker::new(5, 2, 5).is_ok());
        assert!(Chunker::new(5, 20, 6).is_ok());
        assert!(Chunker::new(1, 2, 1).is_ok());
        assert!(Chunker::new(1, 20, 1 << 22).is_ok());
    }

    #[test]
    fn boundaries_default_shape() {
        let c = Chunker::new(16, 6, 256).unwrap();
        let data = bytes(1, 3000);
        assert_eq!(lens(&c, &data), vec![41, 122, 28, 83, 26, 114, 50, 31, 67, 77, 149, 91, 79, 97, 94, 72, 86, 79, 77, 95, 68, 38, 64, 107, 76, 101, 66, 92, 97, 74, 30, 67, 62, 129, 78, 76, 94, 123]);
    }

    #[test]
    fn boundaries_wide_range() {
        let c = Chunker::new(32, 8, 1024).unwrap();
        let data = bytes(2, 12000);
        assert_eq!(lens(&c, &data), vec![369, 306, 447, 438, 110, 108, 260, 281, 506, 239, 146, 260, 218, 275, 256, 153, 306, 382, 207, 289, 212, 488, 290, 251, 42, 464, 710, 464, 298, 499, 655, 462, 130, 159, 282, 131, 74, 381, 275, 177]);
    }

    #[test]
    fn boundaries_tiny_parameters() {
        let c = Chunker::new(1, 2, 8).unwrap();
        let data = bytes(3, 200);
        assert_eq!(lens(&c, &data), vec![4, 7, 4, 6, 2, 4, 2, 2, 5, 7, 4, 5, 2, 6, 7, 4, 4, 2, 4, 4, 4, 2, 2, 8, 5, 8, 6, 3, 5, 4, 2, 2, 5, 4, 4, 2, 4, 4, 7, 4, 8, 7, 4, 6, 4, 1]);
    }

    #[test]
    fn boundaries_fixed_size() {
        let c = Chunker::new(64, 5, 64).unwrap();
        let data = bytes(4, 1000);
        assert_eq!(lens(&c, &data), vec![64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 40]);
    }

    #[test]
    fn boundaries_large_min() {
        let c = Chunker::new(100, 7, 4000).unwrap();
        let data = bytes(5, 20000);
        assert_eq!(lens(&c, &data), vec![158, 216, 130, 322, 103, 125, 298, 141, 156, 266, 329, 175, 179, 138, 139, 162, 152, 125, 208, 461, 161, 262, 133, 144, 341, 171, 148, 155, 131, 245, 181, 183, 153, 134, 295, 161, 178, 177, 111, 142, 164, 167, 264, 143, 159, 140, 129, 208, 286, 162, 246, 135, 149, 168, 277, 114, 196, 292, 144, 103, 119, 284, 196, 145, 280, 193, 294, 158, 151, 223, 182, 211, 177, 138, 249, 151, 190, 197, 242, 170, 138, 173, 188, 154, 256, 162, 180, 162, 620, 176, 174, 202, 144, 144, 204, 269, 135, 127, 221, 199, 175, 208, 101, 140, 163]);
    }

    #[test]
    fn boundaries_min_above_normal() {
        let c = Chunker::new(300, 6, 1000).unwrap();
        let data = bytes(6, 8000);
        assert_eq!(lens(&c, &data), vec![306, 314, 309, 320, 313, 305, 312, 302, 352, 324, 334, 350, 309, 303, 315, 312, 320, 301, 331, 335, 357, 325, 309, 364, 278]);
    }

    #[test]
    fn cut_and_find_on_short_input() {
        let c = Chunker::new(16, 6, 256).unwrap();
        let data = bytes(1, 3000);
        for n in [0usize, 1, 5, 15, 16] {
            assert_eq!(c.find(&data[..n]), None, "prefix of {} bytes", n);
            assert_eq!(c.cut(&data[..n]), n);
        }
        let first = c.cut(&data);
        assert_eq!(first, 41);
        assert_eq!(c.find(&data), Some(first));
        assert_eq!(c.find(&data[..first]), Some(first));
        assert_eq!(c.find(&data[..first - 1]), None);
        assert_eq!(c.cut(&data[..first - 1]), first - 1);
        assert_eq!(c.cut(&data[..first + 10]), first);
    }

    #[test]
    fn cut_at_min_plus_one() {
        // a boundary may fall on the very first hashed byte
        let c = Chunker::new(4, 3, 40).unwrap();
        let data = bytes(12, 60);
        assert_eq!(c.find(&data), Some(5));
        assert_eq!(c.find(&data[..5]), Some(5));
        assert_eq!(c.find(&data[..4]), None);
        assert_eq!(c.cut(&data[..4]), 4);
    }

    #[test]
    fn mask_switches_exactly_at_the_normal_size() {
        // with min 4 and 3 bits the strict mask applies to chunks shorter than 8 bytes
        let c = Chunker::new(4, 3, 40).unwrap();
        let data = bytes(24, 60);
        assert_eq!(c.find(&data), Some(8));
        assert_eq!(c.find(&data[..8]), Some(8));
        assert_eq!(c.find(&data[..7]), None);
    }

    #[test]
    fn max_forces_a_cut() {
        let c = Chunker::new(8, 12, 40).unwrap();
        // with 12 bits a hash match inside 40 bytes is very unlikely; the model says none for this data
        let data = bytes(77, 400);
        assert_eq!(lens(&c, &data), vec![40, 40, 40, 40, 40, 40, 40, 40, 40, 40]);
        assert_eq!(c.find(&data[..39]), None);
        assert_eq!(c.find(&data[..40]), Some(40));
        assert_eq!(c.find(&data[..41]), Some(40));
        assert_eq!(c.cut(&data[..39]), 39);
    }

    #[test]
    fn uniform_data() {
        let c = Chunker::new(16, 6, 256).unwrap();
        assert_eq!(lens(&c, &vec![0xFFu8; 2000]), vec![256, 256, 256, 256, 256, 256, 256, 208]);
        assert_eq!(lens(&c, &vec![0u8; 2000]), vec![256, 256, 256, 256, 256, 256, 256, 208]);
    }

    #[test]
    fn stream_matches_whole_buffer_chunking() {
        let cases: Vec<(Chunker, Vec<u8>)> = vec![
            (Chunker::new(16, 6, 256).unwrap(), bytes(1, 3000)),
            (Chunker::new(32, 8, 1024).unwrap(), bytes(2, 12000)),
            (Chunker::new(300, 6, 1000).unwrap(), bytes(6, 8000)),
            (Chunker::new(1, 2, 8).unwrap(), bytes(3, 200)),
            (Chunker::new(64, 5, 64).unwrap(), bytes(4, 1000)),
        ];
        for (c, data) in cases {
            let want: Vec<Vec<u8>> = c.chunks(&data).into_iter().map(|r| data[r].to_vec()).collect();
            for piece in [1usize, 3, 64, 255, 1000, 100_000] {
                let mut s = Stream::new(c.clone());
                let mut got: Vec<Vec<u8>> = Vec::new();
                for part in data.chunks(piece) {
                    got.extend(s.push(part));
                }
                let held = s.pending();
                let tail = s.finish();
                match tail {
                    Some(t) => {
                        assert_eq!(t.len(), held);
                        got.push(t);
                    }
                    None => assert_eq!(held, 0),
                }
                assert_eq!(got, want, "pieces of {}", piece);
            }
        }
    }

    #[test]
    fn stream_holds_back_undetermined_bytes() {
        let c = Chunker::new(16, 6, 256).unwrap();
        let data = bytes(1, 3000);
        let first = c.cut(&data);
        let mut s = Stream::new(c.clone());
        assert!(s.push(&data[..first - 1]).is_empty());
        assert_eq!(s.pending(), first - 1);
        let out = s.push(&data[first - 1..first]);
        assert_eq!(out, vec![data[..first].to_vec()]);
        assert_eq!(s.pending(), 0);
        let out = s.push(&data[first..first + 5]);
        assert!(out.is_empty());
        assert_eq!(s.pending(), 5);
        assert_eq!(s.finish(), Some(data[first..first + 5].to_vec()));
    }

    #[test]
    fn stream_emits_several_chunks_from_one_push() {
        let c = Chunker::new(16, 6, 256).unwrap();
        let data = bytes(1, 3000);
        let mut s = Stream::new(c.clone());
        let out = s.push(&data);
        let lens_out: Vec<usize> = out.iter().map(|v| v.len()).collect();
        assert_eq!(lens_out, c.chunks(&data).iter().map(|r| r.len()).collect::<Vec<_>>()[..lens_out.len()].to_vec());
        assert!(lens_out.len() >= 30);
        assert_eq!(s.pending() + lens_out.iter().sum::<usize>(), 3000);
    }

    #[test]
    fn empty_stream() {
        let c = Chunker::new(16, 6, 256).unwrap();
        let mut s = Stream::new(c);
        assert!(s.push(&[]).is_empty());
        assert_eq!(s.pending(), 0);
        assert_eq!(s.finish(), None);
    }

    #[test]
    fn store_counts_new_and_repeated_chunks() {
        let c = Chunker::new(16, 6, 256).unwrap();
        let a = bytes(10, 6000);
        let mut st = Store::new(c.clone());
        assert_eq!(st.saved_permille(), 0);
        let first = st.ingest(&a);
        assert_eq!(first, Ingest { chunks: 80, new_chunks: 80, bytes: 6000, new_bytes: 6000 });
        let again = st.ingest(&a);
        assert_eq!(again, Ingest { chunks: 80, new_chunks: 0, bytes: 6000, new_bytes: 0 });
        assert_eq!(st.chunks(), 160);
        assert_eq!(st.unique_chunks(), 80);
        assert_eq!(st.bytes(), 12000);
        assert_eq!(st.unique_bytes(), 6000);
        assert_eq!(st.saved_permille(), 500);
        let ranges = c.chunks(&a);
        assert!(st.contains(&a[ranges[0].clone()]));
        assert!(st.contains(&a[ranges[ranges.len() - 1].clone()]));
        assert!(!st.contains(&a[..ranges[0].end - 1]));
        assert!(!st.contains(&[1, 2, 3]));
    }

    #[test]
    fn store_resyncs_after_an_insertion() {
        let c = Chunker::new(16, 6, 256).unwrap();
        let a = bytes(10, 6000);
        let mut shifted = vec![0x55u8];
        shifted.extend_from_slice(&a);
        let mut st = Store::new(c);
        st.ingest(&a);
        let r = st.ingest(&shifted);
        assert_eq!(r, Ingest { chunks: 81, new_chunks: 2, bytes: 6001, new_bytes: 85 });
        assert_eq!(st.unique_chunks(), 82);
        assert_eq!(st.unique_bytes(), 6085);
        assert_eq!(st.bytes(), 12001);
        assert_eq!(st.saved_permille(), 492);
    }

    #[test]
    fn store_repeats_inside_one_ingest() {
        let c = Chunker::new(16, 6, 256).unwrap();
        let block = bytes(11, 700);
        let mut data = Vec::new();
        for _ in 0..6 {
            data.extend_from_slice(&block);
        }
        let mut st = Store::new(c);
        let r = st.ingest(&data);
        assert_eq!(r, Ingest { chunks: 60, new_chunks: 12, bytes: 4200, new_bytes: 842 });
        assert_eq!(st.unique_chunks(), 12);
        assert_eq!(st.unique_bytes(), 842);
        assert_eq!(st.saved_permille(), 799);
    }

    #[test]
    fn store_edge_cases() {
        let c = Chunker::new(1, 2, 1).unwrap();
        let mut st = Store::new(c);
        let r = st.ingest(&[]);
        assert_eq!(r, Ingest { chunks: 0, new_chunks: 0, bytes: 0, new_bytes: 0 });
        assert_eq!(st.saved_permille(), 0);
        let r = st.ingest(&[1, 1, 2, 3, 3, 3, 3]);
        assert_eq!(r, Ingest { chunks: 7, new_chunks: 3, bytes: 7, new_bytes: 3 });
        assert_eq!(st.saved_permille(), 571);
        let r = st.ingest(&[3, 4]);
        assert_eq!(r, Ingest { chunks: 2, new_chunks: 1, bytes: 2, new_bytes: 1 });
        assert_eq!(st.chunks(), 9);
        assert_eq!(st.bytes(), 9);
        assert_eq!(st.unique_chunks(), 4);
        assert_eq!(st.unique_bytes(), 4);
        assert_eq!(st.saved_permille(), 555);
        assert!(st.contains(&[4]));
        assert!(!st.contains(&[5]));
        assert!(!st.contains(&[]));
    }
''')

LIB = Lib(
    name="chunkcut", lang="rust", title="the chunkcut crate",
    blurb="The backup tool splits files with chunkcut, a gear-hash content-defined chunker with a streaming mode and a dedup store.",
    files={"Cargo.toml": cargo("chunkcut"), "src/lib.rs": SRC, "README.md": README, ".gitignore": "target/\n", ".cargo/config.toml": CARGO_CONFIG},
    visible_tests={"tests/basic.rs": VISIBLE},
    hidden_tests={"tests/full.rs": HIDDEN},
    mutate=["src/lib.rs"], difficulty=3, tags=["chunking", "dedup", "hashing"],
)

register_libs([LIB], n=8)
