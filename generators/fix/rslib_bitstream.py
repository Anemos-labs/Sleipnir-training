"""Bit-level reader/writer (rust): MSB-first fields, unary and Rice codes with an escape, zigzag signed values."""
from fx import Lib, dd

from generators.fix._lang1 import CARGO_CONFIG, cargo, register_libs

README = dd('''
    # bitstream

    Bit-granular I/O for the sensor-sample compressor: fixed-width fields, unary counts and Rice codes. Bits are written
    most significant first, so the first bit written is bit 7 of the first byte.

    ## `BitWriter`
    * `BitWriter::new()`, `bit_len(&self) -> usize` (bits written so far), `finish(self) -> Vec<u8>`: the bytes, the last one
      padded with zero bits at its low end.
    * `put_bit(&mut self, bit: bool)`.
    * `put_bits(&mut self, value: u64, n: u32) -> Result<(), BitError>`: the low `n` bits of `value`, high bit first
      (higher bits of `value` are ignored). `n == 0` writes nothing; `n > 64` is `Err(BitError::BadParam)` and writes nothing.
    * `align(&mut self) -> u32`: pads with zero bits up to the next byte boundary and returns how many were added (0 if
      already aligned).
    * `put_unary(&mut self, n: u32)`: `n` one bits followed by a zero bit.
    * `put_rice(&mut self, v: u32, k: u32) -> Result<(), BitError>`: Rice code with parameter `k` (`k > 31` is `BadParam`).
      With `q = v >> k`: when `q < 24` it is `q` ones, a zero, then the low `k` bits of `v`. When `q >= 24` an *escape* is used:
      exactly 24 ones (no terminating zero) followed by all 32 bits of `v`.
    * `put_signed_rice(&mut self, v: i32, k: u32) -> Result<(), BitError>`: `put_rice(zigzag(v), k)`.
    * free functions `zigzag(i32) -> u32` (`0, -1, 1, -2, 2 ...` map to `0, 1, 2, 3, 4 ...`: `(v << 1) ^ (v >> 31)`) and
      `unzigzag(u32) -> i32` (its inverse).

    ## `BitReader`
    `BitReader::new(data: &[u8])`, `position(&self) -> usize` (bits consumed), `bits_left(&self) -> usize`. **Every read that fails
    leaves the position unchanged.**

    * `get_bit(&mut self) -> Result<bool, BitError>`: `Err(BitError::Eof)` at the end of the data.
    * `get_bits(&mut self, n: u32) -> Result<u64, BitError>`: the next `n` bits as an integer (first bit most significant).
      `n == 0` gives 0; `n > 64` is `BadParam`; fewer than `n` bits left is `Eof`.
    * `align(&mut self) -> usize`: skips to the next byte boundary and returns the number of bits skipped (never fails; at
      the end of the data it simply stays there).
    * `get_unary(&mut self, limit: u32) -> Result<u32, BitError>`: counts ones up to the terminating zero. More than `limit` ones
      before a zero is `Err(BitError::Overflow)`; running out of data is `Eof`. (`limit` ones followed by a zero is fine.)
    * `get_rice(&mut self, k: u32) -> Result<u32, BitError>`: the inverse of `put_rice`: read up to 24 ones; if a zero comes first
      the quotient is the number of ones and `k` more bits follow; if 24 ones come first, the next 32 bits are the value.
      `k > 31` is `BadParam`; running out of data is `Eof`; a quotient/remainder combination that does not fit in a `u32`
      (possible only with hand-made data) is `Overflow`.
    * `get_signed_rice(&mut self, k: u32) -> Result<i32, BitError>`: `unzigzag(get_rice(k))`.
''')

SRC = dd('''
    //! MSB-first bit I/O with Rice codes.

    const ESCAPE: u32 = 24;

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum BitError {
        Eof,
        BadParam,
        Overflow,
    }

    pub fn zigzag(v: i32) -> u32 {
        ((v << 1) ^ (v >> 31)) as u32
    }

    pub fn unzigzag(u: u32) -> i32 {
        ((u >> 1) as i32) ^ -((u & 1) as i32)
    }

    #[derive(Debug, Default)]
    pub struct BitWriter {
        bytes: Vec<u8>,
        nbits: usize,
    }

    impl BitWriter {
        pub fn new() -> BitWriter {
            BitWriter::default()
        }

        pub fn bit_len(&self) -> usize {
            self.nbits
        }

        pub fn finish(self) -> Vec<u8> {
            self.bytes
        }

        pub fn put_bit(&mut self, bit: bool) {
            let offset = self.nbits % 8;
            if offset == 0 {
                self.bytes.push(0);
            }
            if bit {
                *self.bytes.last_mut().unwrap() |= 0x80 >> offset;
            }
            self.nbits += 1;
        }

        pub fn put_bits(&mut self, value: u64, n: u32) -> Result<(), BitError> {
            if n > 64 {
                return Err(BitError::BadParam);
            }
            for i in (0..n).rev() {
                self.put_bit((value >> i) & 1 == 1);
            }
            Ok(())
        }

        pub fn align(&mut self) -> u32 {
            let mut added = 0;
            while self.nbits % 8 != 0 {
                self.put_bit(false);
                added += 1;
            }
            added
        }

        pub fn put_unary(&mut self, n: u32) {
            for _ in 0..n {
                self.put_bit(true);
            }
            self.put_bit(false);
        }

        pub fn put_rice(&mut self, v: u32, k: u32) -> Result<(), BitError> {
            if k > 31 {
                return Err(BitError::BadParam);
            }
            let q = v >> k;
            if q < ESCAPE {
                self.put_unary(q);
                self.put_bits(v as u64 & ((1u64 << k) - 1), k)
            } else {
                for _ in 0..ESCAPE {
                    self.put_bit(true);
                }
                self.put_bits(v as u64, 32)
            }
        }

        pub fn put_signed_rice(&mut self, v: i32, k: u32) -> Result<(), BitError> {
            self.put_rice(zigzag(v), k)
        }
    }

    #[derive(Debug)]
    pub struct BitReader<'a> {
        data: &'a [u8],
        pos: usize,
    }

    impl<'a> BitReader<'a> {
        pub fn new(data: &'a [u8]) -> BitReader<'a> {
            BitReader { data, pos: 0 }
        }

        pub fn position(&self) -> usize {
            self.pos
        }

        pub fn bits_left(&self) -> usize {
            self.data.len() * 8 - self.pos
        }

        pub fn get_bit(&mut self) -> Result<bool, BitError> {
            if self.pos >= self.data.len() * 8 {
                return Err(BitError::Eof);
            }
            let bit = (self.data[self.pos / 8] >> (7 - self.pos % 8)) & 1 == 1;
            self.pos += 1;
            Ok(bit)
        }

        pub fn get_bits(&mut self, n: u32) -> Result<u64, BitError> {
            if n > 64 {
                return Err(BitError::BadParam);
            }
            if self.bits_left() < n as usize {
                return Err(BitError::Eof);
            }
            let mut v = 0u64;
            for _ in 0..n {
                v = (v << 1) | self.get_bit()? as u64;
            }
            Ok(v)
        }

        pub fn align(&mut self) -> usize {
            let skip = (8 - self.pos % 8) % 8;
            let skip = skip.min(self.bits_left());
            self.pos += skip;
            skip
        }

        fn restoring<T>(&mut self, f: impl FnOnce(&mut Self) -> Result<T, BitError>) -> Result<T, BitError> {
            let start = self.pos;
            let r = f(self);
            if r.is_err() {
                self.pos = start;
            }
            r
        }

        pub fn get_unary(&mut self, limit: u32) -> Result<u32, BitError> {
            self.restoring(|r| {
                let mut ones = 0u32;
                while r.get_bit()? {
                    ones += 1;
                    if ones > limit {
                        return Err(BitError::Overflow);
                    }
                }
                Ok(ones)
            })
        }

        pub fn get_rice(&mut self, k: u32) -> Result<u32, BitError> {
            if k > 31 {
                return Err(BitError::BadParam);
            }
            self.restoring(|r| {
                let mut q = 0u32;
                loop {
                    if q == ESCAPE {
                        return Ok(r.get_bits(32)? as u32);
                    }
                    if !r.get_bit()? {
                        break;
                    }
                    q += 1;
                }
                let low = r.get_bits(k)?;
                u32::try_from(((q as u64) << k) | low).map_err(|_| BitError::Overflow)
            })
        }

        pub fn get_signed_rice(&mut self, k: u32) -> Result<i32, BitError> {
            self.get_rice(k).map(unzigzag)
        }
    }
''')

VISIBLE = dd('''
    use bitstream::*;

    #[test]
    fn fields_round_trip() {
        let mut w = BitWriter::new();
        w.put_bits(5, 3).unwrap();
        w.put_bits(0x1FF, 9).unwrap();
        let bytes = w.finish();
        let mut r = BitReader::new(&bytes);
        assert_eq!(r.get_bits(3), Ok(5));
        assert_eq!(r.get_bits(9), Ok(0x1FF));
    }

    #[test]
    fn zigzag_small_values() {
        assert_eq!(zigzag(-1), 1);
        assert_eq!(zigzag(2), 4);
    }
''')

HIDDEN = dd('''
    use bitstream::*;

    fn written(f: impl FnOnce(&mut BitWriter)) -> (Vec<u8>, usize) {
        let mut w = BitWriter::new();
        f(&mut w);
        let n = w.bit_len();
        (w.finish(), n)
    }

    #[test]
    fn put_bits_layout() {
        let (bytes, n) = written(|w| {
            w.put_bits(5, 3).unwrap();
            w.put_bits(0x1FF, 9).unwrap();
            w.put_bits(0, 1).unwrap();
            w.put_bits(0xABCD, 16).unwrap();
        });
        assert_eq!(n, 29);
        assert_eq!(bytes, [0xbf, 0xf5, 0x5e, 0x68]);
    }

    #[test]
    fn put_bits_masks_high_bits() {
        let (bytes, n) = written(|w| w.put_bits(0xFF, 4).unwrap());
        assert_eq!((bytes, n), (vec![0xf0], 4));
        let (bytes, n) = written(|w| w.put_bits(0b1_0110, 4).unwrap());
        assert_eq!((bytes, n), (vec![0x60], 4));
        let (bytes, _) = written(|w| w.put_bits(u64::MAX, 1).unwrap());
        assert_eq!(bytes, [0x80]);
    }

    #[test]
    fn put_bits_zero_width_and_sixty_four() {
        let (bytes, n) = written(|w| {
            w.put_bits(0xdead, 0).unwrap();
            w.put_bits(0x0123456789ABCDEF, 64).unwrap();
            w.put_bits(1, 1).unwrap();
        });
        assert_eq!(n, 65);
        assert_eq!(bytes, [0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef, 0x80]);
        let mut w = BitWriter::new();
        assert_eq!(w.put_bits(1, 65), Err(BitError::BadParam));
        assert_eq!(w.bit_len(), 0);
        assert!(w.put_bits(u64::MAX, 64).is_ok());
    }

    #[test]
    fn empty_writer() {
        let w = BitWriter::new();
        assert_eq!(w.bit_len(), 0);
        assert!(w.finish().is_empty());
    }

    #[test]
    fn writer_align() {
        let mut w = BitWriter::new();
        assert_eq!(w.align(), 0);
        w.put_bits(3, 2).unwrap();
        assert_eq!(w.align(), 6);
        assert_eq!(w.bit_len(), 8);
        assert_eq!(w.align(), 0);
        w.put_bits(0x1FF, 9).unwrap();
        assert_eq!(w.align(), 7);
        assert_eq!(w.finish(), [0xc0, 0xff, 0x80]);
        let mut w = BitWriter::new();
        w.put_bits(0xFF, 8).unwrap();
        assert_eq!(w.align(), 0);
        assert_eq!(w.bit_len(), 8);
    }

    #[test]
    fn unary_codes() {
        let (bytes, n) = written(|w| {
            w.put_unary(0);
            w.put_unary(3);
            w.put_unary(8);
        });
        assert_eq!(n, 14);
        assert_eq!(bytes, [0x77, 0xf8]);
        let mut r = BitReader::new(&bytes);
        assert_eq!(r.get_unary(8), Ok(0));
        assert_eq!(r.get_unary(8), Ok(3));
        assert_eq!(r.get_unary(8), Ok(8));
        assert_eq!(r.position(), 14);
    }

    #[test]
    fn unary_limit_is_inclusive_and_atomic() {
        let (bytes, _) = written(|w| {
            w.put_unary(5);
            w.put_unary(2);
        });
        let mut r = BitReader::new(&bytes);
        assert_eq!(r.get_unary(4), Err(BitError::Overflow));
        assert_eq!(r.position(), 0);
        assert_eq!(r.get_unary(5), Ok(5));
        assert_eq!(r.get_unary(2), Ok(2));
        // all ones until the end of the data
        let mut r = BitReader::new(&[0xff]);
        assert_eq!(r.get_unary(100), Err(BitError::Eof));
        assert_eq!(r.position(), 0);
        let mut r = BitReader::new(&[]);
        assert_eq!(r.get_unary(0), Err(BitError::Eof));
        let mut r = BitReader::new(&[0x00]);
        assert_eq!(r.get_unary(0), Ok(0));
    }

    #[test]
    fn rice_literals() {
        let (bytes, n) = written(|w| {
            for v in [0u32, 1, 2, 3, 4, 5, 10, 37, 100, 1000] {
                w.put_rice(v, 2).unwrap();
            }
        });
        assert_eq!(n, 149);
        assert_eq!(
            bytes,
            [0x05, 0x38, 0x9d, 0x7f, 0xcf, 0xff, 0xff, 0xf8, 0x00, 0x00, 0x03, 0x27, 0xff, 0xff, 0xf8, 0x00, 0x00, 0x1f, 0x40]
        );
        let (bytes, n) = written(|w| {
            for v in [0u32, 1, 2, 3, 4, 5, 10, 37, 100, 1000] {
                w.put_rice(v, 0).unwrap();
            }
        });
        assert_eq!(n, 200);
        assert_eq!(&bytes[..8], [0x5b, 0xbd, 0xf7, 0xfe, 0xff, 0xff, 0xff, 0x00]);
        assert_eq!(&bytes[17..], [0x64, 0xff, 0xff, 0xff, 0x00, 0x00, 0x03, 0xe8]);
    }

    #[test]
    fn rice_escape_boundary() {
        // q = 23: regular code, 23 ones + zero + 2 bits
        let (bytes, n) = written(|w| w.put_rice(95, 2).unwrap());
        assert_eq!((n, bytes), (26, vec![0xff, 0xff, 0xfe, 0xc0]));
        // q = 24: escape, 24 ones + 32 raw bits
        let (bytes, n) = written(|w| w.put_rice(96, 2).unwrap());
        assert_eq!((n, bytes), (56, vec![0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x60]));
        let (bytes, n) = written(|w| w.put_rice(u32::MAX, 0).unwrap());
        assert_eq!((n, bytes), (56, vec![0xff; 7]));
        let (bytes, n) = written(|w| w.put_rice(u32::MAX, 31).unwrap());
        assert_eq!((n, bytes), (33, vec![0xbf, 0xff, 0xff, 0xff, 0x80]));
        for v in [95u32, 96, 97, 1000, u32::MAX, u32::MAX - 1] {
            let (bytes, _) = written(|w| w.put_rice(v, 2).unwrap());
            assert_eq!(BitReader::new(&bytes).get_rice(2), Ok(v), "v = {v}");
        }
    }

    #[test]
    fn rice_round_trip_all_parameters() {
        let mut x = 0x2545_F491_4F6C_DD1Du64;
        let mut values = vec![0u32, 1, 2, 3, 7, 8, 255, 256, 65535, 65536, u32::MAX, u32::MAX - 1, 1 << 31];
        for _ in 0..200 {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            values.push((x >> (x % 40 + 20)) as u32);
        }
        for k in 0..=31u32 {
            let (bytes, _) = written(|w| {
                for &v in &values {
                    w.put_rice(v, k).unwrap();
                }
            });
            let mut r = BitReader::new(&bytes);
            for &v in &values {
                assert_eq!(r.get_rice(k), Ok(v), "k = {k}");
            }
        }
    }

    #[test]
    fn rice_parameter_checks() {
        let mut w = BitWriter::new();
        assert_eq!(w.put_rice(1, 32), Err(BitError::BadParam));
        assert_eq!(w.put_signed_rice(1, 40), Err(BitError::BadParam));
        assert_eq!(w.bit_len(), 0);
        assert!(w.put_rice(1, 31).is_ok());
        let mut r = BitReader::new(&[0, 0, 0, 0, 0, 0, 0, 0]);
        assert_eq!(r.get_rice(32), Err(BitError::BadParam));
        assert_eq!(r.get_signed_rice(99), Err(BitError::BadParam));
        assert_eq!(r.get_bits(65), Err(BitError::BadParam));
        assert_eq!(r.position(), 0);
    }

    #[test]
    fn rice_decode_errors_leave_position_alone() {
        // seven ones and then the data ends
        let mut r = BitReader::new(&[0xff]);
        assert_eq!(r.get_bits(1), Ok(1));
        assert_eq!(r.get_rice(2), Err(BitError::Eof));
        assert_eq!(r.position(), 1);
        // "10" then only two of the three remainder bits
        let mut r = BitReader::new(&[0b0000_1001]);
        r.get_bits(4).unwrap();
        assert_eq!(r.get_rice(3), Err(BitError::Eof));
        assert_eq!(r.position(), 4);
        // escape with a truncated payload
        let mut r = BitReader::new(&[0xff, 0xff, 0xff, 0x00, 0x00]);
        assert_eq!(r.get_rice(0), Err(BitError::Eof));
        assert_eq!(r.position(), 0);
        assert_eq!(r.get_signed_rice(0), Err(BitError::Eof));
        assert_eq!(r.position(), 0);
    }

    #[test]
    fn rice_overflow_from_handmade_data() {
        // 23 ones, zero, then 31 bits of 1: (23 << 31) | 0x7FFFFFFF does not fit in 32 bits
        let mut w = BitWriter::new();
        w.put_unary(23);
        w.put_bits(0x7FFF_FFFF, 31).unwrap();
        let bytes = w.finish();
        let mut r = BitReader::new(&bytes);
        assert_eq!(r.get_rice(31), Err(BitError::Overflow));
        assert_eq!(r.position(), 0);
        // q = 1, k = 31, all ones: exactly u32::MAX fits
        let mut w = BitWriter::new();
        w.put_unary(1);
        w.put_bits(0x7FFF_FFFF, 31).unwrap();
        let bytes = w.finish();
        assert_eq!(BitReader::new(&bytes).get_rice(31), Ok(u32::MAX));
        // q = 2, k = 31 overflows
        let mut w = BitWriter::new();
        w.put_unary(2);
        w.put_bits(0, 31).unwrap();
        let bytes = w.finish();
        assert_eq!(BitReader::new(&bytes).get_rice(31), Err(BitError::Overflow));
    }

    #[test]
    fn zigzag_mapping() {
        let values = [0i32, -1, 1, -2, 2, -3, 3, 100, -100, i32::MAX, i32::MIN];
        let want = [0u32, 1, 2, 3, 4, 5, 6, 200, 199, 4294967294, 4294967295];
        for (v, w) in values.iter().zip(want) {
            assert_eq!(zigzag(*v), w, "zigzag({v})");
            assert_eq!(unzigzag(w), *v, "unzigzag({w})");
        }
        for v in -1000..1000 {
            assert_eq!(unzigzag(zigzag(v)), v);
        }
    }

    #[test]
    fn signed_rice_literals() {
        let values = [0i32, -1, 1, -2, 2, -3, 3, 100, -100, i32::MAX, i32::MIN];
        let (bytes, n) = written(|w| {
            for &v in &values {
                w.put_signed_rice(v, 3).unwrap();
            }
        });
        assert_eq!(n, 252);
        assert_eq!(&bytes[..7], [0x01, 0x23, 0x45, 0x6f, 0xff, 0xff, 0xf0]);
        let mut r = BitReader::new(&bytes);
        for &v in &values {
            assert_eq!(r.get_signed_rice(3), Ok(v));
        }
    }

    #[test]
    fn reader_bits_and_eof() {
        let data = [0b1011_0010, 0b0110_1111];
        let mut r = BitReader::new(&data);
        assert_eq!(r.bits_left(), 16);
        assert_eq!(r.get_bit(), Ok(true));
        assert_eq!(r.get_bits(0), Ok(0));
        assert_eq!(r.get_bits(4), Ok(0b0110));
        assert_eq!(r.position(), 5);
        assert_eq!(r.get_bits(7), Ok(0b010_0110));
        assert_eq!(r.bits_left(), 4);
        assert_eq!(r.get_bits(5), Err(BitError::Eof));
        assert_eq!(r.bits_left(), 4, "a failed read must not consume");
        assert_eq!(r.get_bits(4), Ok(0b1111));
        assert_eq!(r.get_bit(), Err(BitError::Eof));
        assert_eq!(r.get_bits(0), Ok(0));
        assert_eq!(r.bits_left(), 0);
    }

    #[test]
    fn reader_sixty_four_bits() {
        let data = [0xde, 0xad, 0xbe, 0xef, 0x01, 0x23, 0x45, 0x67, 0x89];
        let mut r = BitReader::new(&data);
        assert_eq!(r.get_bits(64), Ok(0xdeadbeef01234567));
        assert_eq!(r.get_bits(8), Ok(0x89));
        let mut r = BitReader::new(&data);
        r.get_bits(4).unwrap();
        assert_eq!(r.get_bits(64), Ok(0xeadbeef012345678));
        assert_eq!(r.get_bits(5), Err(BitError::Eof));
        assert_eq!(r.get_bits(4), Ok(9));
    }

    #[test]
    fn reader_align() {
        let data = [0xff, 0x0f, 0xaa];
        let mut r = BitReader::new(&data);
        assert_eq!(r.align(), 0);
        r.get_bits(3).unwrap();
        assert_eq!(r.align(), 5);
        assert_eq!(r.position(), 8);
        assert_eq!(r.get_bits(4), Ok(0));
        assert_eq!(r.align(), 4);
        assert_eq!(r.get_bits(8), Ok(0xaa));
        assert_eq!(r.align(), 0);
        let mut r = BitReader::new(&[]);
        assert_eq!(r.align(), 0);
        let mut r = BitReader::new(&[0x80]);
        r.get_bit().unwrap();
        assert_eq!(r.align(), 7);
        assert_eq!(r.bits_left(), 0);
    }

    #[test]
    fn mixed_stream_round_trip() {
        let (bytes, _) = written(|w| {
            w.put_bits(0b101, 3).unwrap();
            w.put_unary(4);
            w.put_signed_rice(-77, 4).unwrap();
            w.align();
            w.put_bits(0xCAFE, 16).unwrap();
            w.put_rice(5000, 6).unwrap();
            w.put_bit(true);
        });
        let mut r = BitReader::new(&bytes);
        assert_eq!(r.get_bits(3), Ok(0b101));
        assert_eq!(r.get_unary(10), Ok(4));
        assert_eq!(r.get_signed_rice(4), Ok(-77));
        r.align();
        assert_eq!(r.get_bits(16), Ok(0xCAFE));
        assert_eq!(r.get_rice(6), Ok(5000));
        assert_eq!(r.get_bit(), Ok(true));
        assert!(r.bits_left() < 8);
    }
''')

LIB = Lib(
    name="bitstream", lang="rust", title="the bitstream crate",
    blurb="The sensor-sample compressor reads and writes its output with bitstream, which packs fixed-width fields and Rice-coded integers MSB first.",
    files={"Cargo.toml": cargo("bitstream"), "src/lib.rs": SRC, "README.md": README, ".gitignore": "target/\n", ".cargo/config.toml": CARGO_CONFIG},
    visible_tests={"tests/basic.rs": VISIBLE},
    hidden_tests={"tests/full.rs": HIDDEN},
    mutate=["src/lib.rs"], difficulty=2, tags=["bits", "compression", "codec"],
)

register_libs([LIB], n=8)
