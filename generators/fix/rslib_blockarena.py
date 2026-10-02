"""Best-fit block arena (rust): aligned allocation, splitting, coalescing, fragmentation figures."""
from fx import Lib, dd

from generators.fix._lang1 import CARGO_CONFIG, cargo, register_libs

README = dd('''
    # blockarena

    The bookkeeping half of a pool allocator for the packet buffers of a router: it hands out *offsets* into a fixed region, it
    never touches memory itself. Every length and offset is a multiple of `GRAIN = 8` bytes.

    ## `Arena::new(size: usize) -> Result<Arena, ArenaError>`
    `size` must be a positive multiple of 8, otherwise `Err(ArenaError::BadSize)`. A new arena is one free block covering
    `[0, size)`.

    ## `alloc(&mut self, len: usize, align: usize) -> Result<usize, ArenaError>`
    Reserves `len` bytes (rounded **up** to a multiple of 8) at an offset that is a multiple of `max(align, 8)` and returns the
    offset. Errors, checked in this order: `ZeroSize` for `len == 0`; `BadAlign` when `align` is 0 or not a power of two;
    `OutOfMemory` when no free block can hold the request (which can happen with plenty of free bytes in total, if they are
    scattered; a request too large to round up counts as not fitting).

    Placement is **best fit**: of the free blocks that can hold the request at an aligned offset, the one with the *smallest
    total length* is chosen, the lowest address winning a tie. Inside the chosen block the allocation goes to the first aligned
    offset; space in front of it (alignment padding) and behind it stays free as separate free blocks (a free block of length 0 is
    never created).

    ## `free(&mut self, offset: usize) -> Result<(), ArenaError>`
    Releases the allocation that starts exactly at `offset`. The freed block merges with a free block right before it and/or right
    after it, so there are never two adjacent free blocks. Errors: `DoubleFree` when `offset` is the start of a block that is already
    free, `InvalidFree` when `offset` is not the start of any block (including offsets inside a block or past the end).

    ## Queries
    * `size_of(&self, offset: usize) -> Option<usize>`: the (rounded) length of the allocation starting at `offset`, `None` if there is
      none.
    * `stats(&self) -> Stats` with `Stats { used, free, largest_free, blocks, free_blocks }` (all `usize`): bytes in allocations,
      bytes free, the longest free block (0 if none), number of blocks of either kind and number of free blocks.
    * `fragmentation(&self) -> u32`: `0` when nothing is free, otherwise `1000 - largest_free * 1000 / free` (integer division).
    * `check(&self) -> Result<(), String>`: verifies the invariants (blocks tile `[0, size)` in address order, every length is a positive
      multiple of 8, no two free blocks are adjacent) and describes the first violation.
''')

SRC = dd('''
    //! A best-fit offset allocator.

    pub const GRAIN: usize = 8;

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum ArenaError {
        BadSize,
        ZeroSize,
        BadAlign,
        OutOfMemory,
        InvalidFree,
        DoubleFree,
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub struct Stats {
        pub used: usize,
        pub free: usize,
        pub largest_free: usize,
        pub blocks: usize,
        pub free_blocks: usize,
    }

    #[derive(Debug, Clone, Copy)]
    struct Block {
        off: usize,
        len: usize,
        free: bool,
    }

    #[derive(Debug)]
    pub struct Arena {
        size: usize,
        blocks: Vec<Block>,
    }

    fn align_up(x: usize, align: usize) -> Option<usize> {
        Some(x.checked_add(align - 1)? & !(align - 1))
    }

    impl Arena {
        pub fn new(size: usize) -> Result<Arena, ArenaError> {
            if size == 0 || size % GRAIN != 0 {
                return Err(ArenaError::BadSize);
            }
            Ok(Arena { size, blocks: vec![Block { off: 0, len: size, free: true }] })
        }

        pub fn alloc(&mut self, len: usize, align: usize) -> Result<usize, ArenaError> {
            if len == 0 {
                return Err(ArenaError::ZeroSize);
            }
            if align == 0 || !align.is_power_of_two() {
                return Err(ArenaError::BadAlign);
            }
            let rounded = align_up(len, GRAIN).ok_or(ArenaError::OutOfMemory)?;
            let align = align.max(GRAIN);
            let mut best: Option<usize> = None;
            for (i, b) in self.blocks.iter().enumerate() {
                if !b.free {
                    continue;
                }
                let fits = match align_up(b.off, align) {
                    Some(start) => start.checked_add(rounded).map_or(false, |end| end <= b.off + b.len),
                    None => false,
                };
                if fits && best.map_or(true, |j| b.len < self.blocks[j].len) {
                    best = Some(i);
                }
            }
            let i = best.ok_or(ArenaError::OutOfMemory)?;
            let Block { off, len: block_len, .. } = self.blocks[i];
            let start = align_up(off, align).unwrap();
            let end = start + rounded;
            let mut pieces = Vec::with_capacity(3);
            if start > off {
                pieces.push(Block { off, len: start - off, free: true });
            }
            pieces.push(Block { off: start, len: rounded, free: false });
            if end < off + block_len {
                pieces.push(Block { off: end, len: off + block_len - end, free: true });
            }
            self.blocks.splice(i..=i, pieces);
            Ok(start)
        }

        pub fn free(&mut self, offset: usize) -> Result<(), ArenaError> {
            let i = self.blocks.iter().position(|b| b.off == offset).ok_or(ArenaError::InvalidFree)?;
            if self.blocks[i].free {
                return Err(ArenaError::DoubleFree);
            }
            self.blocks[i].free = true;
            if i + 1 < self.blocks.len() && self.blocks[i + 1].free {
                self.blocks[i].len += self.blocks[i + 1].len;
                self.blocks.remove(i + 1);
            }
            if i > 0 && self.blocks[i - 1].free {
                self.blocks[i - 1].len += self.blocks[i].len;
                self.blocks.remove(i);
            }
            Ok(())
        }

        pub fn size_of(&self, offset: usize) -> Option<usize> {
            self.blocks.iter().find(|b| b.off == offset && !b.free).map(|b| b.len)
        }

        pub fn stats(&self) -> Stats {
            let mut s = Stats { used: 0, free: 0, largest_free: 0, blocks: self.blocks.len(), free_blocks: 0 };
            for b in &self.blocks {
                if b.free {
                    s.free += b.len;
                    s.free_blocks += 1;
                    s.largest_free = s.largest_free.max(b.len);
                } else {
                    s.used += b.len;
                }
            }
            s
        }

        pub fn fragmentation(&self) -> u32 {
            let s = self.stats();
            if s.free == 0 {
                return 0;
            }
            (1000 - s.largest_free * 1000 / s.free) as u32
        }

        pub fn check(&self) -> Result<(), String> {
            let mut next = 0;
            let mut prev_free = false;
            for (i, b) in self.blocks.iter().enumerate() {
                if b.off != next {
                    return Err(format!("block {i} starts at {} but {next} was expected", b.off));
                }
                if b.len == 0 || b.len % GRAIN != 0 {
                    return Err(format!("block {i} has bad length {}", b.len));
                }
                if b.free && prev_free {
                    return Err(format!("blocks {} and {i} are both free and adjacent", i - 1));
                }
                prev_free = b.free;
                next += b.len;
            }
            if next != self.size {
                return Err(format!("blocks end at {next}, arena size is {}", self.size));
            }
            Ok(())
        }
    }
''')

VISIBLE = dd('''
    use blockarena::*;

    #[test]
    fn sequential_allocations() {
        let mut a = Arena::new(256).unwrap();
        assert_eq!(a.alloc(10, 1), Ok(0));
        assert_eq!(a.alloc(8, 1), Ok(16));
        assert!(a.check().is_ok());
    }

    #[test]
    fn free_and_reuse() {
        let mut a = Arena::new(64).unwrap();
        let x = a.alloc(64, 8).unwrap();
        assert_eq!(a.alloc(8, 8), Err(ArenaError::OutOfMemory));
        a.free(x).unwrap();
        assert_eq!(a.alloc(8, 8), Ok(0));
    }
''')

TRACE = '''
        Op::Alloc(64, 1, Ok(0)), Op::Alloc(16, 1, Ok(64)), Op::Alloc(40, 64, Ok(128)), Op::Alloc(100, 1, Ok(168)), Op::Alloc(64, 8, Ok(272)),
        Op::Alloc(130, 1, Ok(336)), Op::Free(336), Op::Free(0), Op::Alloc(9, 64, Ok(0)), Op::Alloc(64, 64, Ok(384)), Op::Alloc(8, 32, Ok(32)),
        Op::Free(272), Op::Alloc(24, 64, Ok(320)), Op::Alloc(3, 64, Ok(448)), Op::Alloc(24, 16, Ok(352)), Op::Free(0), Op::Free(448),
        Op::Free(128), Op::Alloc(40, 1, Ok(272)), Op::Free(352), Op::Free(64), Op::Alloc(16, 32, Ok(0)), Op::Free(272), Op::Alloc(40, 32, Ok(64)),
        Op::Free(64), Op::Alloc(9, 1, Ok(16)), Op::Alloc(24, 1, Ok(344)), Op::Free(320), Op::Alloc(8, 8, Ok(368)), Op::Free(32), Op::Free(368),
        Op::Alloc(64, 1, Ok(272)), Op::Alloc(8, 8, Ok(336)), Op::Alloc(130, 64, Ok(448)), Op::Free(0), Op::Free(384), Op::Alloc(9, 8, Ok(0)),
        Op::Free(16), Op::Alloc(9, 64, Ok(384)), Op::Alloc(16, 16, Ok(368)), Op::Alloc(40, 64, Ok(64)), Op::Alloc(9, 1, Ok(16)), Op::Free(448),
        Op::Free(0), Op::Alloc(64, 1, Ok(104)), Op::Alloc(40, 1, Ok(400)), Op::Alloc(9, 8, Ok(0)), Op::Free(168), Op::Alloc(100, 16, Ok(448)),
        Op::Alloc(3, 1, Ok(440)), Op::Free(400), Op::Free(384), Op::Alloc(130, 1, Ok(552)), Op::Alloc(8, 1, Ok(32)), Op::Alloc(8, 1, Ok(40)),
        Op::Free(440), Op::Free(552), Op::Alloc(130, 64, Ok(576)), Op::Free(272), Op::Alloc(100, 64, Ok(192)), Op::Free(336), Op::Free(64),
        Op::Free(192), Op::Alloc(9, 32, Ok(64)), Op::Free(104), Op::Alloc(64, 8, Ok(384)), Op::Free(576), Op::Alloc(9, 16, Ok(48)),
        Op::Alloc(64, 16, Ok(80)), Op::Alloc(8, 1, Ok(144)),
'''.strip("\n")

HIDDEN = dd('''
    use blockarena::*;

    fn st(used: usize, free: usize, largest_free: usize, blocks: usize, free_blocks: usize) -> Stats {
        Stats { used, free, largest_free, blocks, free_blocks }
    }

    #[test]
    fn new_arena() {
        assert_eq!(Arena::new(0).unwrap_err(), ArenaError::BadSize);
        assert_eq!(Arena::new(7).unwrap_err(), ArenaError::BadSize);
        assert_eq!(Arena::new(12).unwrap_err(), ArenaError::BadSize);
        assert_eq!(Arena::new(9).unwrap_err(), ArenaError::BadSize);
        let a = Arena::new(8).unwrap();
        assert_eq!(a.stats(), st(0, 8, 8, 1, 1));
        let a = Arena::new(1024).unwrap();
        assert_eq!(a.stats(), st(0, 1024, 1024, 1, 1));
        assert_eq!(a.fragmentation(), 0);
        assert!(a.check().is_ok());
    }

    #[test]
    fn requests_are_rounded_up() {
        let mut a = Arena::new(256).unwrap();
        let x = a.alloc(10, 1).unwrap();
        assert_eq!(a.size_of(x), Some(16));
        let y = a.alloc(1, 1).unwrap();
        assert_eq!(y, 16);
        assert_eq!(a.size_of(y), Some(8));
        let z = a.alloc(8, 1).unwrap();
        assert_eq!(a.size_of(z), Some(8));
        let w = a.alloc(17, 1).unwrap();
        assert_eq!(a.size_of(w), Some(24));
        assert_eq!(a.stats().used, 16 + 8 + 8 + 24);
    }

    #[test]
    fn script_with_alignment() {
        let mut a = Arena::new(256).unwrap();
        assert_eq!(a.alloc(10, 1), Ok(0));
        assert_eq!(a.alloc(8, 1), Ok(16));
        assert_eq!(a.alloc(100, 16), Ok(32));
        assert_eq!(a.alloc(1, 64), Ok(192));
        assert_eq!(a.stats(), st(136, 120, 56, 7, 3));
        a.check().unwrap();
        assert_eq!(a.free(8), Err(ArenaError::InvalidFree));
        assert_eq!(a.free(3), Err(ArenaError::InvalidFree));
        assert_eq!(a.free(24), Err(ArenaError::DoubleFree)); // the 8-byte alignment gap before the 100-byte block
        assert_eq!(a.free(0), Ok(()));
        assert_eq!(a.stats(), st(120, 136, 56, 7, 4));
        assert_eq!(a.alloc(8, 1), Ok(24));
        assert_eq!(a.alloc(200, 1), Err(ArenaError::OutOfMemory));
        assert_eq!(a.stats(), st(128, 128, 56, 7, 3));
        assert_eq!(a.fragmentation(), 563);
        a.check().unwrap();
    }

    #[test]
    fn padding_and_tail_become_free_blocks() {
        let mut a = Arena::new(256).unwrap();
        assert_eq!(a.alloc(8, 1), Ok(0));
        assert_eq!(a.alloc(8, 64), Ok(64));
        assert_eq!(a.stats(), st(16, 240, 184, 4, 2));
        a.check().unwrap();
        // an exact fit leaves no empty free block behind
        let mut b = Arena::new(64).unwrap();
        assert_eq!(b.alloc(24, 1), Ok(0));
        assert_eq!(b.alloc(40, 1), Ok(24));
        assert_eq!(b.stats(), st(64, 0, 0, 2, 0));
        assert_eq!(b.fragmentation(), 0);
        b.check().unwrap();
        assert_eq!(b.alloc(1, 1), Err(ArenaError::OutOfMemory));
    }

    #[test]
    fn best_fit_beats_first_fit() {
        let mut a = Arena::new(256).unwrap();
        assert_eq!(a.alloc(64, 1), Ok(0));
        assert_eq!(a.alloc(8, 1), Ok(64));
        assert_eq!(a.alloc(32, 1), Ok(72));
        assert_eq!(a.alloc(8, 1), Ok(104));
        a.free(0).unwrap();
        a.free(72).unwrap();
        assert_eq!(a.stats(), st(16, 240, 144, 5, 3));
        // holes: 64 at 0, 32 at 72, 144 at 112: the 32-byte hole is the tightest for 24 bytes
        assert_eq!(a.alloc(24, 1), Ok(72));
        // the 8 bytes left over at 96 are the tightest for 8
        assert_eq!(a.alloc(8, 1), Ok(96));
        // 60 bytes (64 rounded) fit the 64-byte hole exactly
        assert_eq!(a.alloc(60, 1), Ok(0));
        assert_eq!(a.stats(), st(112, 144, 144, 6, 1));
        assert_eq!(a.fragmentation(), 0);
        a.check().unwrap();
    }

    #[test]
    fn ties_go_to_the_lowest_address() {
        let mut a = Arena::new(96).unwrap();
        let offs: Vec<usize> = (0..4).map(|_| a.alloc(16, 1).unwrap()).collect();
        assert_eq!(offs, [0, 16, 32, 48]);
        a.free(32).unwrap();
        a.free(0).unwrap();
        // free blocks: 16 at 0, 16 at 32, 32 at 64
        assert_eq!(a.alloc(16, 1), Ok(0));
        assert_eq!(a.alloc(16, 1), Ok(32));
        assert_eq!(a.alloc(16, 1), Ok(64));
        assert_eq!(a.alloc(16, 1), Ok(80));
    }

    #[test]
    fn fragmentation_can_block_a_request() {
        let mut a = Arena::new(64).unwrap();
        let offs: Vec<usize> = (0..8).map(|_| a.alloc(8, 1).unwrap()).collect();
        assert_eq!(offs, [0, 8, 16, 24, 32, 40, 48, 56]);
        assert_eq!(a.alloc(8, 1), Err(ArenaError::OutOfMemory));
        for o in offs.iter().step_by(2) {
            a.free(*o).unwrap();
        }
        assert_eq!(a.stats(), st(32, 32, 8, 8, 4));
        assert_eq!(a.fragmentation(), 750);
        assert_eq!(a.alloc(16, 1), Err(ArenaError::OutOfMemory));
        assert_eq!(a.alloc(8, 1), Ok(0));
        a.check().unwrap();
    }

    #[test]
    fn coalescing_in_every_order() {
        for order in [[0, 1, 2], [2, 1, 0], [1, 0, 2], [0, 2, 1], [2, 0, 1], [1, 2, 0]] {
            let mut a = Arena::new(64).unwrap();
            let offs: Vec<usize> = (0..3).map(|_| a.alloc(16, 1).unwrap()).collect();
            for i in order {
                a.free(offs[i]).unwrap();
                a.check().unwrap();
            }
            assert_eq!(a.stats(), st(0, 64, 64, 1, 1), "order {order:?}");
            assert_eq!(a.alloc(64, 1), Ok(0));
        }
    }

    #[test]
    fn coalescing_with_both_neighbours() {
        let mut a = Arena::new(64).unwrap();
        let o: Vec<usize> = (0..4).map(|_| a.alloc(16, 1).unwrap()).collect();
        a.free(o[0]).unwrap();
        a.free(o[2]).unwrap();
        assert_eq!(a.stats(), st(32, 32, 16, 4, 2));
        a.free(o[1]).unwrap(); // merges with the free block on both sides
        assert_eq!(a.stats(), st(16, 48, 48, 2, 1));
        assert_eq!(a.alloc(48, 1), Ok(0));
        assert_eq!(a.alloc(8, 1), Err(ArenaError::OutOfMemory));
    }

    #[test]
    fn alignment_rules() {
        let mut a = Arena::new(128).unwrap();
        assert_eq!(a.alloc(8, 1), Ok(0));
        assert_eq!(a.alloc(8, 64), Ok(64));
        assert_eq!(a.alloc(8, 32), Ok(32));
        assert_eq!(a.alloc(1, 128), Err(ArenaError::OutOfMemory));
        assert_eq!(a.alloc(1, 3), Err(ArenaError::BadAlign));
        assert_eq!(a.alloc(1, 0), Err(ArenaError::BadAlign));
        assert_eq!(a.alloc(1, 12), Err(ArenaError::BadAlign));
        assert_eq!(a.alloc(0, 8), Err(ArenaError::ZeroSize));
        assert_eq!(a.alloc(0, 0), Err(ArenaError::ZeroSize));
        assert_eq!(a.alloc(0, 3), Err(ArenaError::ZeroSize));
        assert_eq!(a.stats(), st(24, 104, 56, 6, 3));
        // small alignments are raised to the 8-byte grain
        let mut b = Arena::new(64).unwrap();
        assert_eq!(b.alloc(1, 1), Ok(0));
        assert_eq!(b.alloc(1, 2), Ok(8));
        assert_eq!(b.alloc(1, 4), Ok(16));
        assert_eq!(b.alloc(1, 8), Ok(24));
        assert_eq!(b.alloc(1, 16), Ok(32));
        assert_eq!(b.alloc(1, 16), Ok(48));
    }

    #[test]
    fn exact_and_oversize_requests() {
        let mut a = Arena::new(128).unwrap();
        assert_eq!(a.alloc(8, 1), Ok(0));
        assert_eq!(a.alloc(120, 1), Ok(8));
        assert_eq!(a.alloc(1, 1), Err(ArenaError::OutOfMemory));
        let mut b = Arena::new(256).unwrap();
        assert_eq!(b.alloc(257, 1), Err(ArenaError::OutOfMemory));
        assert_eq!(b.alloc(256, 8), Ok(0));
        let mut c = Arena::new(256).unwrap();
        assert_eq!(c.alloc(249, 8), Ok(0));
        assert_eq!(c.size_of(0), Some(256));
        let mut d = Arena::new(256).unwrap();
        assert_eq!(d.alloc(usize::MAX, 8), Err(ArenaError::OutOfMemory));
        assert_eq!(d.alloc(usize::MAX - 3, 1), Err(ArenaError::OutOfMemory));
        assert_eq!(d.alloc(8, 8), Ok(0));
        assert_eq!(d.alloc(8, 1 << 62), Err(ArenaError::OutOfMemory));
        assert_eq!(d.alloc(8, 1 << (usize::BITS - 1)), Err(ArenaError::OutOfMemory));
        assert_eq!(d.stats(), st(8, 248, 248, 2, 1));
        // offset 0 is aligned to anything
        let mut e = Arena::new(256).unwrap();
        assert_eq!(e.alloc(8, 1 << 20), Ok(0));
    }

    #[test]
    fn free_errors() {
        let mut a = Arena::new(64).unwrap();
        let x = a.alloc(16, 1).unwrap();
        let y = a.alloc(16, 1).unwrap();
        assert_eq!(a.free(100_000), Err(ArenaError::InvalidFree));
        assert_eq!(a.free(64), Err(ArenaError::InvalidFree));
        assert_eq!(a.free(x + 8), Err(ArenaError::InvalidFree));
        assert_eq!(a.free(32), Err(ArenaError::DoubleFree));
        a.free(x).unwrap();
        assert_eq!(a.free(x), Err(ArenaError::DoubleFree));
        a.free(y).unwrap();
        // x and y are merged into one block now
        assert_eq!(a.free(y), Err(ArenaError::InvalidFree));
        assert_eq!(a.free(x), Err(ArenaError::DoubleFree));
        assert_eq!(a.stats(), st(0, 64, 64, 1, 1));
    }

    #[test]
    fn size_of_only_describes_allocations() {
        let mut a = Arena::new(64).unwrap();
        let x = a.alloc(20, 1).unwrap();
        assert_eq!(a.size_of(x), Some(24));
        assert_eq!(a.size_of(x + 8), None);
        assert_eq!(a.size_of(24), None); // free block
        assert_eq!(a.size_of(64), None);
        assert_eq!(a.size_of(1000), None);
        a.free(x).unwrap();
        assert_eq!(a.size_of(x), None);
    }

    enum Op {
        Alloc(usize, usize, Result<usize, ArenaError>),
        Free(usize),
    }

    #[test]
    fn long_trace_matches_the_model() {
        use Op::*;
        let trace = [
''') + TRACE.replace("        Op::", "        ").replace(" Op::", " ") + "\n" + dd('''
        ];
        let mut a = Arena::new(1024).unwrap();
        for (step, op) in trace.iter().enumerate() {
            match op {
                Alloc(len, align, want) => assert_eq!(&a.alloc(*len, *align), want, "step {step}"),
                Free(off) => assert_eq!(a.free(*off), Ok(()), "step {step}"),
            }
            if let Err(e) = a.check() {
                panic!("step {step}: {e}");
            }
        }
        assert_eq!(a.stats(), st(360, 664, 472, 14, 2));
        assert_eq!(a.fragmentation(), 290);
    }

    #[test]
    fn requests_near_usize_max() {
        let mut a = Arena::new(64).unwrap();
        assert_eq!(a.alloc(usize::MAX, 8), Err(ArenaError::OutOfMemory));
        assert_eq!(a.alloc(usize::MAX - 7, 8), Err(ArenaError::OutOfMemory));
        assert_eq!(a.alloc(8, 8), Ok(0));
        // the only free block starts at 8: 8 + (usize::MAX - 7) does not fit in a usize
        assert_eq!(a.alloc(usize::MAX - 7, 8), Err(ArenaError::OutOfMemory));
        assert_eq!(a.alloc(usize::MAX - 15, 16), Err(ArenaError::OutOfMemory));
        assert_eq!(a.alloc(8, 1 << 63), Err(ArenaError::OutOfMemory));
        let s = a.stats();
        assert_eq!((s.used, s.free, s.blocks), (8, 56, 2));
        assert_eq!(a.check(), Ok(()));
    }
''')

LIB = Lib(
    name="blockarena", lang="rust", title="the blockarena crate",
    blurb="The router's packet-buffer pool tracks its regions with blockarena, a best-fit offset allocator with alignment, splitting and coalescing.",
    files={"Cargo.toml": cargo("blockarena"), "src/lib.rs": SRC, "README.md": README, ".gitignore": "target/\n", ".cargo/config.toml": CARGO_CONFIG},
    visible_tests={"tests/basic.rs": VISIBLE},
    hidden_tests={"tests/full.rs": HIDDEN},
    mutate=["src/lib.rs"], difficulty=4, tags=["allocator", "memory", "invariants"],
)

register_libs([LIB], n=8)
