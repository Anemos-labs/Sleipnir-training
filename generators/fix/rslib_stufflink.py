"""Byte-stuffed serial framing (rust): flag/escape stuffing, CRC-8 trailer, resynchronising stream decoder."""
from fx import Lib, dd

from generators.fix._lang1 import CARGO_CONFIG, cargo, register_libs

README = dd('''
    # stufflink

    Framing for the serial link between the controller and the field units. Frames are delimited by a flag byte, special
    bytes inside a frame are escaped, and every frame ends with a CRC-8.

    ## Wire format
    * `FLAG = 0x7E` delimits frames, `ESC = 0x7D` escapes. Bytes `0x7E`, `0x7D`, `0x11` and `0x13` must not appear raw
      inside a frame: each is sent as `ESC` followed by the byte xor `0x20` (`0x7E -> 7D 5E`, `0x7D -> 7D 5D`,
      `0x11 -> 7D 31`, `0x13 -> 7D 33`).
    * A frame's *body* is the payload followed by one CRC byte. The CRC is CRC-8 with polynomial `0x07`, initial value `0x00`,
      no reflection and no final xor, over the payload only (`crc8(b"123456789") == 0xF4`, `crc8(b"") == 0`).
    * On the wire a frame is `FLAG`, the stuffed body, `FLAG`. A single `FLAG` may serve as the end of one frame and the start
      of the next.
    * Payloads are at most `MAX_PAYLOAD = 256` bytes.

    ## Encoding
    * `crc8(data: &[u8]) -> u8`.
    * `encode(payload: &[u8]) -> Result<Vec<u8>, FrameError>`: `FLAG`, stuffed body, `FLAG`. A payload over `MAX_PAYLOAD` is
      `Err(FrameError::TooLong)`. `encode(b"hello")` is `7E 68 65 6C 6C 6F 92 7E`.
    * `encode_batch(frames: &[Vec<u8>]) -> Result<Vec<u8>, FrameError>`: the frames back to back sharing delimiters: one `FLAG`,
      then each stuffed body followed by a `FLAG`. An empty list gives an empty vector; any frame that is too long makes the
      whole call `Err(TooLong)`.

    ## `Decoder`
    `Decoder::new()`, `push(&mut self, bytes: &[u8]) -> Vec<Event>` accepts the stream in pieces of any size (a frame, or an escape
    pair, may be split across calls) and returns the events completed by this chunk, in order.
    `Event` is `Frame(Vec<u8>)` (payload, CRC removed) or `Error(FrameError)` with `FrameError` one of `BadCrc`, `BadEscape`,
    `Aborted`, `TooLong`. The decoder is a small state machine:

    * **Idle** (at the start, and after a frame error that needs resynchronisation): bytes are ignored until a `FLAG`, which
      starts a frame. Ignored bytes are counted in `stats().skipped`.
    * **In a frame**: bytes are collected into the body. `ESC` marks the next byte as escaped: it must be one of `5E 5D 31 33`
      (the byte xor `0x20` is stored); any other byte after `ESC` is `Error(BadEscape)` and the decoder goes **idle**, except
      that `FLAG` right after `ESC` is an *abort*: `Error(Aborted)`, the frame is dropped and a new frame starts at that `FLAG`.
      A `FLAG` outside an escape ends the frame: an empty body is ignored silently (back-to-back flags), otherwise the last
      body byte must equal the CRC of the rest, giving `Frame(payload)`, or `Error(BadCrc)`. Either way a new frame starts. Raw
      `0x11`/`0x13` in the input are accepted as data.
    * A body longer than `MAX_PAYLOAD + 1` bytes (counted after unescaping) is `Error(TooLong)`, reported once, and the decoder goes
      **idle** (so the rest of that frame is skipped until its closing `FLAG`).
    * `stats() -> Stats` with `Stats { frames: u64, errors: u64, skipped: u64 }`: good frames delivered, `Error` events emitted, and
      bytes ignored while idle (a `FLAG` that starts a frame is not counted).
''')

SRC = dd('''
    //! Byte-stuffed framing with a CRC-8 trailer.

    pub const FLAG: u8 = 0x7E;
    pub const ESC: u8 = 0x7D;
    pub const MAX_PAYLOAD: usize = 256;

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum FrameError {
        BadCrc,
        BadEscape,
        Aborted,
        TooLong,
    }

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub enum Event {
        Frame(Vec<u8>),
        Error(FrameError),
    }

    #[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
    pub struct Stats {
        pub frames: u64,
        pub errors: u64,
        pub skipped: u64,
    }

    pub fn crc8(data: &[u8]) -> u8 {
        let mut crc = 0u8;
        for &b in data {
            crc ^= b;
            for _ in 0..8 {
                crc = if crc & 0x80 != 0 { (crc << 1) ^ 0x07 } else { crc << 1 };
            }
        }
        crc
    }

    fn needs_escape(b: u8) -> bool {
        matches!(b, FLAG | ESC | 0x11 | 0x13)
    }

    fn stuff_into(out: &mut Vec<u8>, payload: &[u8]) {
        let crc = crc8(payload);
        for &b in payload.iter().chain(std::iter::once(&crc)) {
            if needs_escape(b) {
                out.push(ESC);
                out.push(b ^ 0x20);
            } else {
                out.push(b);
            }
        }
    }

    pub fn encode(payload: &[u8]) -> Result<Vec<u8>, FrameError> {
        if payload.len() > MAX_PAYLOAD {
            return Err(FrameError::TooLong);
        }
        let mut out = vec![FLAG];
        stuff_into(&mut out, payload);
        out.push(FLAG);
        Ok(out)
    }

    pub fn encode_batch(frames: &[Vec<u8>]) -> Result<Vec<u8>, FrameError> {
        if frames.iter().any(|f| f.len() > MAX_PAYLOAD) {
            return Err(FrameError::TooLong);
        }
        if frames.is_empty() {
            return Ok(Vec::new());
        }
        let mut out = vec![FLAG];
        for f in frames {
            stuff_into(&mut out, f);
            out.push(FLAG);
        }
        Ok(out)
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    enum State {
        Idle,
        InFrame,
    }

    #[derive(Debug)]
    pub struct Decoder {
        state: State,
        body: Vec<u8>,
        escaped: bool,
        stats: Stats,
    }

    impl Default for Decoder {
        fn default() -> Self {
            Decoder::new()
        }
    }

    impl Decoder {
        pub fn new() -> Decoder {
            Decoder { state: State::Idle, body: Vec::new(), escaped: false, stats: Stats::default() }
        }

        pub fn stats(&self) -> Stats {
            self.stats
        }

        fn fail(&mut self, events: &mut Vec<Event>, err: FrameError, resync: bool) {
            events.push(Event::Error(err));
            self.stats.errors += 1;
            self.body.clear();
            self.escaped = false;
            if resync {
                self.state = State::Idle;
            }
        }

        pub fn push(&mut self, bytes: &[u8]) -> Vec<Event> {
            let mut events = Vec::new();
            for &b in bytes {
                if self.state == State::Idle {
                    if b == FLAG {
                        self.state = State::InFrame;
                        self.body.clear();
                        self.escaped = false;
                    } else {
                        self.stats.skipped += 1;
                    }
                    continue;
                }
                if self.escaped {
                    if b == FLAG {
                        self.fail(&mut events, FrameError::Aborted, false);
                        continue;
                    }
                    self.escaped = false;
                    let plain = b ^ 0x20;
                    if !needs_escape(plain) {
                        self.fail(&mut events, FrameError::BadEscape, true);
                        continue;
                    }
                    self.body.push(plain);
                } else if b == FLAG {
                    if let Some((&crc, payload)) = self.body.split_last() {
                        if crc8(payload) == crc {
                            events.push(Event::Frame(payload.to_vec()));
                            self.stats.frames += 1;
                        } else {
                            events.push(Event::Error(FrameError::BadCrc));
                            self.stats.errors += 1;
                        }
                    }
                    self.body.clear();
                    continue;
                } else if b == ESC {
                    self.escaped = true;
                    continue;
                } else {
                    self.body.push(b);
                }
                if self.body.len() > MAX_PAYLOAD + 1 {
                    self.fail(&mut events, FrameError::TooLong, true);
                }
            }
            events
        }
    }
''')

VISIBLE = dd('''
    use stufflink::*;

    #[test]
    fn crc_check_value() {
        assert_eq!(crc8(b"123456789"), 0xF4);
    }

    #[test]
    fn simple_frame_round_trip() {
        let wire = encode(b"hello").unwrap();
        let mut d = Decoder::new();
        assert_eq!(d.push(&wire), vec![Event::Frame(b"hello".to_vec())]);
    }
''')

HIDDEN = dd('''
    use stufflink::*;

    fn frames(events: &[Event]) -> Vec<Vec<u8>> {
        events
            .iter()
            .filter_map(|e| match e {
                Event::Frame(p) => Some(p.clone()),
                _ => None,
            })
            .collect()
    }

    #[test]
    fn crc_values() {
        assert_eq!(crc8(b"123456789"), 0xF4);
        assert_eq!(crc8(b""), 0);
        assert_eq!(crc8(b"hello"), 0x92);
        assert_eq!(crc8(&[0x00]), 0x00);
        assert_eq!(crc8(&[0x01]), 0x07);
        assert_eq!(crc8(&[0xFF]), 0xF3);
        assert_eq!(crc8(b"ab"), 0xC9);
        assert_eq!(crc8(&[0x7E, 0x7D, 0x11, 0x13, 0x20]), 0x41);
    }

    #[test]
    fn encode_literals() {
        assert_eq!(encode(b"").unwrap(), [0x7e, 0x00, 0x7e]);
        assert_eq!(encode(b"hello").unwrap(), [0x7e, 0x68, 0x65, 0x6c, 0x6c, 0x6f, 0x92, 0x7e]);
        assert_eq!(
            encode(&[0x7e, 0x7d, 0x11, 0x13, 0x20]).unwrap(),
            [0x7e, 0x7d, 0x5e, 0x7d, 0x5d, 0x7d, 0x31, 0x7d, 0x33, 0x20, 0x41, 0x7e]
        );
    }

    #[test]
    fn crc_byte_is_stuffed_too() {
        // payload [0x23] has crc8 == 0x7E-ish? find one whose crc needs escaping and check the wire form
        let mut found = 0;
        for b in 0..=255u8 {
            let p = [b];
            let c = crc8(&p);
            if c == FLAG || c == ESC || c == 0x11 || c == 0x13 {
                found += 1;
                let wire = encode(&p).unwrap();
                assert_eq!(wire.last(), Some(&FLAG));
                assert_eq!(wire[wire.len() - 2], c ^ 0x20, "payload {b:#04x}");
                assert_eq!(wire[wire.len() - 3], ESC);
                let mut d = Decoder::new();
                assert_eq!(d.push(&wire), vec![Event::Frame(p.to_vec())]);
            }
        }
        assert!(found >= 2, "expected payloads whose crc needs stuffing, found {found}");
    }

    #[test]
    fn encode_length_limit() {
        assert_eq!(encode(&vec![0u8; 257]), Err(FrameError::TooLong));
        assert_eq!(encode(&vec![0u8; 1000]), Err(FrameError::TooLong));
        let wire = encode(&vec![0x41u8; 256]).unwrap();
        assert_eq!(wire.len(), 2 + 256 + 1);
        let max: Vec<u8> = (0..=255u8).collect();
        assert_eq!(encode(&max).unwrap().len(), 263);
    }

    #[test]
    fn encode_batch_shares_delimiters() {
        let wire = encode_batch(&[b"ab".to_vec(), vec![], vec![0x7e]]).unwrap();
        assert_eq!(wire, [0x7e, 0x61, 0x62, 0xc9, 0x7e, 0x00, 0x7e, 0x7d, 0x5e, 0x7d, 0x5d, 0x7e]);
        assert_eq!(encode_batch(&[]).unwrap(), Vec::<u8>::new());
        assert_eq!(encode_batch(&[vec![1], vec![0u8; 300]]), Err(FrameError::TooLong));
        assert_eq!(encode_batch(&[vec![0u8; 300], vec![1]]), Err(FrameError::TooLong));
        assert_eq!(encode_batch(&[vec![0u8; 256]]).unwrap().len(), 1 + 257 + 1 - 0);
    }

    #[test]
    fn decode_back_to_back_frames() {
        let mut d = Decoder::new();
        let mut wire = encode(b"hello").unwrap();
        wire.extend(encode(b"").unwrap());
        wire.extend(encode(b"x").unwrap());
        assert_eq!(
            d.push(&wire),
            vec![Event::Frame(b"hello".to_vec()), Event::Frame(vec![]), Event::Frame(b"x".to_vec())]
        );
        assert_eq!(d.stats(), Stats { frames: 3, errors: 0, skipped: 0 });
    }

    #[test]
    fn decode_shared_delimiters() {
        let wire = encode_batch(&[b"one".to_vec(), b"two".to_vec(), vec![0x7e, 0x7d]]).unwrap();
        let mut d = Decoder::new();
        assert_eq!(frames(&d.push(&wire)), vec![b"one".to_vec(), b"two".to_vec(), vec![0x7e, 0x7d]]);
        assert_eq!(d.stats().errors, 0);
    }

    #[test]
    fn noise_before_the_first_flag_is_skipped() {
        let mut d = Decoder::new();
        let mut wire = b"noise".to_vec();
        wire.extend(encode(b"hi").unwrap());
        assert_eq!(d.push(&wire), vec![Event::Frame(b"hi".to_vec())]);
        assert_eq!(d.stats(), Stats { frames: 1, errors: 0, skipped: 5 });
    }

    #[test]
    fn repeated_flags_are_silent() {
        let mut d = Decoder::new();
        assert!(d.push(&[FLAG, FLAG, FLAG, FLAG]).is_empty());
        assert_eq!(d.stats(), Stats::default());
        let mut d = Decoder::new();
        let mut wire = vec![FLAG, FLAG];
        wire.extend(encode(b"a").unwrap());
        wire.push(FLAG);
        assert_eq!(d.push(&wire), vec![Event::Frame(b"a".to_vec())]);
    }

    #[test]
    fn bad_crc() {
        let mut wire = encode(b"hello").unwrap();
        wire[3] ^= 1;
        let mut d = Decoder::new();
        assert_eq!(d.push(&wire), vec![Event::Error(FrameError::BadCrc)]);
        assert_eq!(d.stats(), Stats { frames: 0, errors: 1, skipped: 0 });
        // the decoder carries on with the next frame
        assert_eq!(d.push(&encode(b"next").unwrap()), vec![Event::Frame(b"next".to_vec())]);
        // a body that is just a wrong crc byte
        let mut d = Decoder::new();
        assert_eq!(d.push(&[FLAG, 0x01, FLAG]), vec![Event::Error(FrameError::BadCrc)]);
        // a lone crc byte of 0 is the empty payload
        let mut d = Decoder::new();
        assert_eq!(d.push(&[FLAG, 0x00, FLAG]), vec![Event::Frame(vec![])]);
    }

    #[test]
    fn abort_sequence() {
        let mut d = Decoder::new();
        let ev = d.push(&[FLAG, 0x41, ESC, FLAG, 0x42, 0x42, FLAG]);
        assert_eq!(ev, vec![Event::Error(FrameError::Aborted), Event::Error(FrameError::BadCrc)]);
        assert_eq!(d.stats().errors, 2);
        // after an abort the FLAG that follows the ESC starts the next frame, which decodes normally
        let mut d = Decoder::new();
        let mut wire = vec![FLAG, 0x41, 0x42, ESC];
        wire.extend(&encode(b"fine").unwrap());
        assert_eq!(d.push(&wire), vec![Event::Error(FrameError::Aborted), Event::Frame(b"fine".to_vec())]);
        assert_eq!(d.stats(), Stats { frames: 1, errors: 1, skipped: 0 });
    }

    #[test]
    fn bad_escape_resynchronises_on_the_next_flag() {
        let mut d = Decoder::new();
        let mut wire = vec![FLAG, 0x41, ESC, 0x41, 0x42, FLAG, FLAG];
        wire.extend(encode(b"ok").unwrap());
        let ev = d.push(&wire);
        assert_eq!(ev, vec![Event::Error(FrameError::BadEscape), Event::Frame(b"ok".to_vec())]);
        assert_eq!(d.stats(), Stats { frames: 1, errors: 1, skipped: 1 });
        let mut d = Decoder::new();
        assert_eq!(d.push(&[FLAG, ESC, ESC, 0x00, FLAG]), vec![Event::Error(FrameError::BadEscape)]);
        assert_eq!(d.stats().skipped, 1);
    }

    #[test]
    fn only_four_bytes_may_be_escaped() {
        for plain in 0..=255u8 {
            let mut d = Decoder::new();
            let esc = plain ^ 0x20;
            let ev = d.push(&[FLAG, ESC, plain]);
            let valid = matches!(esc, 0x7e | 0x7d | 0x11 | 0x13);
            if valid {
                assert!(ev.is_empty(), "ESC {plain:#04x} should be accepted");
            } else if plain == FLAG {
                assert_eq!(ev, vec![Event::Error(FrameError::Aborted)]);
            } else {
                assert_eq!(ev, vec![Event::Error(FrameError::BadEscape)], "ESC {plain:#04x}");
            }
        }
    }

    #[test]
    fn raw_xon_xoff_are_accepted_as_data() {
        let payload = [0x11u8, 0x13, 0x41];
        let mut wire = vec![FLAG];
        wire.extend(payload);
        wire.push(crc8(&payload));
        wire.push(FLAG);
        let mut d = Decoder::new();
        assert_eq!(d.push(&wire), vec![Event::Frame(payload.to_vec())]);
    }

    #[test]
    fn length_limits() {
        let max: Vec<u8> = (0..=255u8).collect();
        let mut d = Decoder::new();
        assert_eq!(d.push(&encode(&max).unwrap()), vec![Event::Frame(max.clone())]);
        // 256 payload bytes + crc is fine; one more body byte is too long
        let mut body = vec![FLAG];
        body.extend(vec![0x41u8; 258]);
        body.push(FLAG);
        let mut d = Decoder::new();
        assert_eq!(d.push(&body), vec![Event::Error(FrameError::TooLong)]);
        // the rest of the long frame is skipped (1 byte after the error: 258th is the trigger, nothing after) then idle
        let mut body = vec![FLAG];
        body.extend(vec![0x41u8; 300]);
        body.push(FLAG);
        let mut d = Decoder::new();
        assert_eq!(d.push(&body), vec![Event::Error(FrameError::TooLong)]);
        assert_eq!(d.stats(), Stats { frames: 0, errors: 1, skipped: 42 });
        // exactly 257 body bytes with a wrong crc: BadCrc, not TooLong
        let mut body = vec![FLAG];
        body.extend(vec![0x41u8; 257]);
        body.push(FLAG);
        let mut d = Decoder::new();
        assert_eq!(d.push(&body), vec![Event::Error(FrameError::BadCrc)]);
    }

    #[test]
    fn long_junk_is_skipped_not_reframed() {
        // a very long frame: one TooLong, then everything up to the closing flag is skipped
        let mut body = vec![FLAG];
        body.extend(vec![0x41u8; 1000]);
        body.push(FLAG);
        let mut d = Decoder::new();
        assert_eq!(d.push(&body), vec![Event::Error(FrameError::TooLong)]);
        assert_eq!(d.stats(), Stats { frames: 0, errors: 1, skipped: 742 });
        // that closing flag started a new frame, so a good frame can be finished right away
        let mut rest = encode(b"after").unwrap();
        rest.remove(0);
        assert_eq!(d.push(&rest), vec![Event::Frame(b"after".to_vec())]);
        // long noise before the first flag only counts as skipped bytes
        let mut d = Decoder::new();
        assert!(d.push(&vec![0x55u8; 600]).is_empty());
        assert_eq!(d.stats(), Stats { frames: 0, errors: 0, skipped: 600 });
        assert_eq!(d.push(&encode(b"ok").unwrap()), vec![Event::Frame(b"ok".to_vec())]);
        assert_eq!(d.stats(), Stats { frames: 1, errors: 0, skipped: 600 });
    }

    #[test]
    fn length_limit_counts_unescaped_bytes() {
        // 257 escaped bytes (two wire bytes each) are fine, the 258th is too long
        let mut wire = vec![FLAG];
        for _ in 0..257 {
            wire.extend([ESC, 0x5e]);
        }
        wire.push(FLAG);
        let mut d = Decoder::new();
        assert_eq!(d.push(&wire), vec![Event::Error(FrameError::BadCrc)]);
        let mut wire = vec![FLAG];
        for _ in 0..258 {
            wire.extend([ESC, 0x5e]);
        }
        wire.push(FLAG);
        let mut d = Decoder::new();
        assert_eq!(d.push(&wire), vec![Event::Error(FrameError::TooLong)]);
    }

    #[test]
    fn chunking_makes_no_difference() {
        let mut wire = b"junk".to_vec();
        wire.extend(encode(b"first").unwrap());
        let mut bad = encode(b"broken").unwrap();
        bad[4] ^= 0x40;
        wire.extend(bad);
        wire.extend([FLAG, 0x41, ESC, 0x42, 0x43, FLAG]);
        wire.extend(encode(&[0x7e, 0x7d, 0x00, 0x11]).unwrap());
        wire.extend([FLAG, 0x01, ESC, FLAG]);
        wire.extend(encode(b"last").unwrap());
        let mut whole = Decoder::new();
        let want = whole.push(&wire);
        assert!(want.len() >= 6);
        for chunk in [1usize, 2, 3, 5, 7, 11] {
            let mut d = Decoder::new();
            let mut got = Vec::new();
            for piece in wire.chunks(chunk) {
                got.extend(d.push(piece));
            }
            assert_eq!(got, want, "chunk size {chunk}");
            assert_eq!(d.stats(), whole.stats(), "stats, chunk size {chunk}");
        }
    }

    #[test]
    fn escape_pair_split_across_pushes() {
        let wire = encode(&[0x7e]).unwrap();
        let mut d = Decoder::new();
        assert!(d.push(&wire[..2]).is_empty());
        assert!(d.push(&wire[2..3]).is_empty());
        assert_eq!(d.push(&wire[3..]), vec![Event::Frame(vec![0x7e])]);
    }

    #[test]
    fn stats_accumulate() {
        let mut d = Decoder::new();
        d.push(b"xx");
        d.push(&encode(b"a").unwrap());
        d.push(&[FLAG, 0x09, FLAG]);
        // the decoder is inside a frame here (the FLAG above started one), so "?" is body data, not noise
        d.push(b"?");
        d.push(&encode(b"b").unwrap());
        assert_eq!(d.stats(), Stats { frames: 2, errors: 2, skipped: 2 });
    }

    #[test]
    fn round_trip_random_payloads() {
        let mut x = 0x1234_5678_9ABC_DEF1u64;
        let mut d = Decoder::new();
        for round in 0..300 {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            let len = (x % 257) as usize;
            let payload: Vec<u8> = (0..len).map(|i| ((x >> (i % 56)) as u8).wrapping_add(i as u8)).collect();
            let ev = d.push(&encode(&payload).unwrap());
            assert_eq!(ev, vec![Event::Frame(payload)], "round {round}");
        }
        assert_eq!(d.stats(), Stats { frames: 300, errors: 0, skipped: 0 });
    }
''')

LIB = Lib(
    name="stufflink", lang="rust", title="the stufflink crate",
    blurb="The controller talks to its field units over a serial link framed by stufflink: flag-delimited, byte-stuffed frames with a CRC-8 and a resynchronising decoder.",
    files={"Cargo.toml": cargo("stufflink"), "src/lib.rs": SRC, "README.md": README, ".gitignore": "target/\n", ".cargo/config.toml": CARGO_CONFIG},
    visible_tests={"tests/basic.rs": VISIBLE},
    hidden_tests={"tests/full.rs": HIDDEN},
    mutate=["src/lib.rs"], difficulty=3, tags=["framing", "serial", "state-machine"],
)

register_libs([LIB], n=8)
