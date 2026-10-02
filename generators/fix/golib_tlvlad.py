"""Ladder-coded TLV frames (go): a variable-width integer codec of our own design plus framing and a stream decoder."""
from fx import Lib, dd, langs

from generators.fix._lang1 import gosrc, register_libs

README = dd('''
    # tlvlad

    Binary framing used between the telemetry gateway and its sensors: tag, length, value, checksum. Lengths use the
    *ladder* integer code defined below (not LEB128, not a protobuf varint).

    ## Ladder code
    Unsigned 32-bit values, big-endian, in four rungs. Each rung starts where the previous one stops, so every value
    has exactly one shortest form.

    | values | bytes | layout |
    |---|---|---|
    | 0 ..= 127 | 1 | `0vvvvvvv` |
    | 128 ..= 16511 | 2 | `10vvvvvv vvvvvvvv`, payload = value - 128 |
    | 16512 ..= 2113663 | 3 | `110vvvvv vvvvvvvv vvvvvvvv`, payload = value - 16512 |
    | 2113664 ..= 4294967295 | 5 | `0xE0` then the value itself as 4 big-endian bytes |

    `AppendLadder(dst []byte, v uint32) []byte` appends the shortest form. `LadderLen(v uint32) int` is its length.

    `ReadLadder(b []byte) (v uint32, n int, err error)` decodes from the start of `b` and returns the bytes used.
    Errors: `ErrShort` when `b` ends inside the code; `ErrBadPrefix` for a first byte `0xE1..0xFF`; `ErrNonCanonical`
    for a 5-byte code holding a value below 2113664 (a shorter form exists). It checks that the first byte promises
    the rung's full length before looking at the remaining bytes, and reports `ErrShort` if they are missing.

    ## Frames
    A frame is `tag | ladder(len(value)) | value | checksum`. The checksum is one byte: the sum of every preceding byte
    of the frame (tag, length code and value), taken modulo 251.

    * Tag `0x00` is reserved for padding: `Encode` refuses it with `ErrBadTag`; `Decode` refuses it as well.
    * A value longer than `MaxValue` (1 MiB, 1048576 bytes) is `ErrTooBig` when encoding. `Decode` reports `ErrTooBig`
      as soon as the length code announces more than `MaxValue`, without waiting for the bytes.
    * `Encode(f Frame) ([]byte, error)`.
    * `Decode(b []byte) (Frame, int, error)` reads one frame from the start of `b` and returns the bytes used. `ErrShort`
      if the frame is incomplete, `ErrChecksum` if the checksum byte is wrong. The returned `Value` is a copy.
    * `DecodeAll(b []byte) ([]Frame, error)`: frames back to back; single `0x00` padding bytes between (or before, or
      after) frames are skipped. On the first error it returns the frames decoded so far and that error.
    * `Pad(b []byte, align int) []byte` appends zero bytes until `len(b)` is a multiple of `align` (`align <= 1` leaves
      `b` unchanged).

    ## Stream decoder
    `Decoder` collects bytes with `Write(p)` and hands out frames with `Next() (Frame, bool, error)`.
    Leading `0x00` bytes are discarded first. If the buffer is empty or holds an incomplete frame (`ErrShort`), `Next`
    returns `ok == false` and a nil error and keeps the bytes. On any other error it returns that error and drops
    exactly one byte (the tag), so a later call retries from the next byte. `Buffered()` is the number of bytes held.
''')

SRC = gosrc(dd(r'''
    // Package tlvlad implements ladder-coded integers and tag/length/value frames.
    package tlvlad

    import "errors"

    const (
        MaxValue = 1 << 20

        rung2 = 128
        rung3 = rung2 + 1<<14
        rung5 = rung3 + 1<<21
    )

    var (
        ErrShort        = errors.New("tlvlad: short buffer")
        ErrBadPrefix    = errors.New("tlvlad: bad ladder prefix")
        ErrNonCanonical = errors.New("tlvlad: non-canonical ladder code")
        ErrBadTag       = errors.New("tlvlad: reserved tag")
        ErrTooBig       = errors.New("tlvlad: value too big")
        ErrChecksum     = errors.New("tlvlad: checksum mismatch")
    )

    // LadderLen is the length in bytes of the shortest ladder code for v.
    func LadderLen(v uint32) int {
        switch {
        case v < rung2:
            return 1
        case v < rung3:
            return 2
        case v < rung5:
            return 3
        }
        return 5
    }

    // AppendLadder appends the shortest ladder code of v to dst.
    func AppendLadder(dst []byte, v uint32) []byte {
        switch {
        case v < rung2:
            return append(dst, byte(v))
        case v < rung3:
            x := v - rung2
            return append(dst, 0x80|byte(x>>8), byte(x))
        case v < rung5:
            x := v - rung3
            return append(dst, 0xC0|byte(x>>16), byte(x>>8), byte(x))
        }
        return append(dst, 0xE0, byte(v>>24), byte(v>>16), byte(v>>8), byte(v))
    }

    // ReadLadder decodes one ladder code from the start of b.
    func ReadLadder(b []byte) (uint32, int, error) {
        if len(b) == 0 {
            return 0, 0, ErrShort
        }
        c := b[0]
        switch {
        case c < 0x80:
            return uint32(c), 1, nil
        case c < 0xC0:
            if len(b) < 2 {
                return 0, 0, ErrShort
            }
            return (uint32(c&0x3F)<<8 | uint32(b[1])) + rung2, 2, nil
        case c < 0xE0:
            if len(b) < 3 {
                return 0, 0, ErrShort
            }
            return (uint32(c&0x1F)<<16 | uint32(b[1])<<8 | uint32(b[2])) + rung3, 3, nil
        case c == 0xE0:
            if len(b) < 5 {
                return 0, 0, ErrShort
            }
            v := uint32(b[1])<<24 | uint32(b[2])<<16 | uint32(b[3])<<8 | uint32(b[4])
            if v < rung5 {
                return 0, 0, ErrNonCanonical
            }
            return v, 5, nil
        }
        return 0, 0, ErrBadPrefix
    }

    // Frame is one tag/value record.
    type Frame struct {
        Tag   byte
        Value []byte
    }

    func checksum(b []byte) byte {
        sum := 0
        for _, c := range b {
            sum += int(c)
        }
        return byte(sum % 251)
    }

    // Encode serialises a frame.
    func Encode(f Frame) ([]byte, error) {
        if f.Tag == 0 {
            return nil, ErrBadTag
        }
        if len(f.Value) > MaxValue {
            return nil, ErrTooBig
        }
        out := []byte{f.Tag}
        out = AppendLadder(out, uint32(len(f.Value)))
        out = append(out, f.Value...)
        return append(out, checksum(out)), nil
    }

    // Decode reads one frame from the start of b.
    func Decode(b []byte) (Frame, int, error) {
        if len(b) == 0 {
            return Frame{}, 0, ErrShort
        }
        if b[0] == 0 {
            return Frame{}, 0, ErrBadTag
        }
        n, k, err := ReadLadder(b[1:])
        if err != nil {
            return Frame{}, 0, err
        }
        if n > MaxValue {
            return Frame{}, 0, ErrTooBig
        }
        end := 1 + k + int(n)
        if len(b) < end+1 {
            return Frame{}, 0, ErrShort
        }
        if checksum(b[:end]) != b[end] {
            return Frame{}, 0, ErrChecksum
        }
        value := append([]byte(nil), b[1+k:end]...)
        return Frame{Tag: b[0], Value: value}, end + 1, nil
    }

    // DecodeAll reads frames back to back, skipping padding bytes.
    func DecodeAll(b []byte) ([]Frame, error) {
        var out []Frame
        for len(b) > 0 {
            if b[0] == 0 {
                b = b[1:]
                continue
            }
            f, n, err := Decode(b)
            if err != nil {
                return out, err
            }
            out = append(out, f)
            b = b[n:]
        }
        return out, nil
    }

    // Pad appends zero bytes until len(b) is a multiple of align.
    func Pad(b []byte, align int) []byte {
        if align <= 1 {
            return b
        }
        for len(b)%align != 0 {
            b = append(b, 0)
        }
        return b
    }

    // Decoder reassembles frames from arbitrary chunks.
    type Decoder struct {
        buf []byte
    }

    // Write adds received bytes.
    func (d *Decoder) Write(p []byte) { d.buf = append(d.buf, p...) }

    // Buffered is the number of bytes waiting.
    func (d *Decoder) Buffered() int { return len(d.buf) }

    // Next returns the next complete frame, if there is one.
    func (d *Decoder) Next() (Frame, bool, error) {
        for len(d.buf) > 0 && d.buf[0] == 0 {
            d.buf = d.buf[1:]
        }
        if len(d.buf) == 0 {
            return Frame{}, false, nil
        }
        f, n, err := Decode(d.buf)
        switch {
        case err == nil:
            d.buf = d.buf[n:]
            return f, true, nil
        case errors.Is(err, ErrShort):
            return Frame{}, false, nil
        }
        d.buf = d.buf[1:]
        return Frame{}, false, err
    }
'''))

VISIBLE = gosrc(dd(r'''
    package tlvlad

    import (
        "bytes"
        "testing"
    )

    func TestLadderSmall(t *testing.T) {
        if got := AppendLadder(nil, 5); !bytes.Equal(got, []byte{5}) {
            t.Fatalf("got %x", got)
        }
        if got := AppendLadder(nil, 300); !bytes.Equal(got, []byte{0x80, 0xac}) {
            t.Fatalf("got %x", got)
        }
    }

    func TestFrameRoundTrip(t *testing.T) {
        raw, err := Encode(Frame{Tag: 7, Value: []byte("hello")})
        if err != nil {
            t.Fatal(err)
        }
        f, n, err := Decode(raw)
        if err != nil || n != len(raw) || f.Tag != 7 || string(f.Value) != "hello" {
            t.Fatalf("got %+v %d %v", f, n, err)
        }
    }
'''))

HIDDEN = gosrc(dd(r'''
    package tlvlad

    import (
        "bytes"
        "errors"
        "testing"
    )

    func TestLadderLiterals(t *testing.T) {
        cases := []struct {
            v    uint32
            want []byte
        }{
            {0, []byte{0x00}},
            {1, []byte{0x01}},
            {127, []byte{0x7f}},
            {128, []byte{0x80, 0x00}},
            {129, []byte{0x80, 0x01}},
            {300, []byte{0x80, 0xac}},
            {16383, []byte{0xbf, 0x7f}},
            {16511, []byte{0xbf, 0xff}},
            {16512, []byte{0xc0, 0x00, 0x00}},
            {16513, []byte{0xc0, 0x00, 0x01}},
            {70000, []byte{0xc0, 0xd0, 0xf0}},
            {2113663, []byte{0xdf, 0xff, 0xff}},
            {2113664, []byte{0xe0, 0x00, 0x20, 0x40, 0x80}},
            {2113665, []byte{0xe0, 0x00, 0x20, 0x40, 0x81}},
            {16777216, []byte{0xe0, 0x01, 0x00, 0x00, 0x00}},
            {4294967295, []byte{0xe0, 0xff, 0xff, 0xff, 0xff}},
        }
        for _, c := range cases {
            got := AppendLadder(nil, c.v)
            if !bytes.Equal(got, c.want) {
                t.Errorf("AppendLadder(%d) = %x, want %x", c.v, got, c.want)
            }
            if LadderLen(c.v) != len(c.want) {
                t.Errorf("LadderLen(%d) = %d, want %d", c.v, LadderLen(c.v), len(c.want))
            }
            v, n, err := ReadLadder(c.want)
            if err != nil || v != c.v || n != len(c.want) {
                t.Errorf("ReadLadder(%x) = %d, %d, %v; want %d, %d", c.want, v, n, err, c.v, len(c.want))
            }
        }
    }

    func TestAppendKeepsPrefix(t *testing.T) {
        got := AppendLadder([]byte{9, 9}, 200)
        if !bytes.Equal(got, []byte{9, 9, 0x80, 0x48}) {
            t.Errorf("got %x", got)
        }
    }

    func TestReadLadderIgnoresTrailingBytes(t *testing.T) {
        v, n, err := ReadLadder([]byte{0x80, 0x01, 0xff, 0xff})
        if err != nil || v != 129 || n != 2 {
            t.Errorf("got %d %d %v", v, n, err)
        }
        v, n, err = ReadLadder([]byte{0x05, 0xe0})
        if err != nil || v != 5 || n != 1 {
            t.Errorf("got %d %d %v", v, n, err)
        }
    }

    func TestLadderSweep(t *testing.T) {
        vals := []uint32{}
        for v := uint32(0); v < 300; v++ {
            vals = append(vals, v)
        }
        for _, edge := range []uint32{16511, 16512, 2113663, 2113664} {
            for d := uint32(0); d < 4; d++ {
                vals = append(vals, edge-2+d)
            }
        }
        x := uint32(2463534242)
        for i := 0; i < 500; i++ {
            x ^= x << 13
            x ^= x >> 17
            x ^= x << 5
            vals = append(vals, x>>(x%29))
        }
        for _, v := range vals {
            enc := AppendLadder(nil, v)
            got, n, err := ReadLadder(enc)
            if err != nil || got != v || n != len(enc) || n != LadderLen(v) {
                t.Fatalf("v=%d enc=%x got=%d n=%d err=%v", v, enc, got, n, err)
            }
        }
    }

    func TestReadLadderErrors(t *testing.T) {
        short := [][]byte{nil, {}, {0x80}, {0xbf}, {0xc0}, {0xc0, 0x01}, {0xdf, 0xff}, {0xe0}, {0xe0, 0x01, 0x00}, {0xe0, 0x01, 0x00, 0x00}}
        for _, b := range short {
            if _, _, err := ReadLadder(b); !errors.Is(err, ErrShort) {
                t.Errorf("ReadLadder(%x): err = %v, want ErrShort", b, err)
            }
        }
        for _, c := range []byte{0xe1, 0xe2, 0xf0, 0xff} {
            if _, _, err := ReadLadder([]byte{c, 0, 0, 0, 0, 0}); !errors.Is(err, ErrBadPrefix) {
                t.Errorf("prefix %#x: err = %v, want ErrBadPrefix", c, err)
            }
        }
        // a bad prefix is reported even when the buffer is just that byte
        if _, _, err := ReadLadder([]byte{0xe1}); !errors.Is(err, ErrBadPrefix) {
            t.Errorf("lone bad prefix: err = %v", err)
        }
        nc := [][]byte{
            {0xe0, 0, 0, 0, 0}, {0xe0, 0, 0, 0, 5}, {0xe0, 0, 0, 0x20, 0x3f}, {0xe0, 0, 0x1f, 0xff, 0xff}, {0xe0, 0, 0x20, 0x40, 0x7f},
        }
        for _, b := range nc {
            if _, _, err := ReadLadder(b); !errors.Is(err, ErrNonCanonical) {
                t.Errorf("ReadLadder(%x): err = %v, want ErrNonCanonical", b, err)
            }
        }
    }

    func TestEncodeLiterals(t *testing.T) {
        got, err := Encode(Frame{Tag: 7, Value: []byte("hello")})
        want := []byte{0x07, 0x05, 'h', 'e', 'l', 'l', 'o', 0x2a}
        if err != nil || !bytes.Equal(got, want) {
            t.Errorf("got %x, %v; want %x", got, err, want)
        }
        got, _ = Encode(Frame{Tag: 1})
        if !bytes.Equal(got, []byte{0x01, 0x00, 0x01}) {
            t.Errorf("empty value: %x", got)
        }
        got, _ = Encode(Frame{Tag: 255, Value: []byte{0, 0}})
        if !bytes.Equal(got, []byte{0xff, 0x02, 0x00, 0x00, 0x06}) {
            t.Errorf("tag 255: %x", got)
        }
        v := bytes.Repeat([]byte{250}, 130)
        got, _ = Encode(Frame{Tag: 9, Value: v})
        if len(got) != 134 || got[0] != 9 || got[1] != 0x80 || got[2] != 0x02 || got[133] != 9 {
            t.Errorf("long value: len %d head %x tail %x", len(got), got[:4], got[130:])
        }
    }

    func TestChecksumWraps(t *testing.T) {
        v := make([]byte, 30)
        for i := range v {
            v[i] = byte(200 + i)
        }
        got, _ := Encode(Frame{Tag: 0x42, Value: v})
        if got[len(got)-1] != 5 || got[1] != 30 {
            t.Errorf("checksum byte %d, length byte %d", got[len(got)-1], got[1])
        }
    }

    func TestEncodeErrors(t *testing.T) {
        if _, err := Encode(Frame{Tag: 0, Value: []byte("x")}); !errors.Is(err, ErrBadTag) {
            t.Errorf("tag 0: %v", err)
        }
        if _, err := Encode(Frame{Tag: 1, Value: make([]byte, 1048577)}); !errors.Is(err, ErrTooBig) {
            t.Errorf("too big: %v", err)
        }
        raw, err := Encode(Frame{Tag: 1, Value: make([]byte, 1048576)})
        if err != nil || len(raw) != 1+3+1048576+1 {
            t.Errorf("max value: len %d err %v", len(raw), err)
        }
    }

    func TestDecodeRoundTrip(t *testing.T) {
        for _, n := range []int{0, 1, 5, 127, 128, 129, 1000, 16511, 16512, 20000} {
            val := make([]byte, n)
            for i := range val {
                val[i] = byte(i*7 + n)
            }
            raw, err := Encode(Frame{Tag: byte(1 + n%250), Value: val})
            if err != nil {
                t.Fatal(err)
            }
            raw = append(raw, 0xAA, 0xBB) // trailing bytes belong to somebody else
            f, used, err := Decode(raw)
            if err != nil || used != len(raw)-2 || f.Tag != byte(1+n%250) || !bytes.Equal(f.Value, val) {
                t.Fatalf("n=%d: tag %d used %d err %v", n, f.Tag, used, err)
            }
        }
    }

    func TestDecodeValueIsACopy(t *testing.T) {
        raw, _ := Encode(Frame{Tag: 3, Value: []byte("abc")})
        f, _, err := Decode(raw)
        if err != nil {
            t.Fatal(err)
        }
        raw[2] = 'Z'
        if string(f.Value) != "abc" {
            t.Errorf("value aliases the input: %q", f.Value)
        }
    }

    func TestDecodeErrors(t *testing.T) {
        good, _ := Encode(Frame{Tag: 7, Value: []byte("hello")})
        for cut := 0; cut < len(good); cut++ {
            if _, _, err := Decode(good[:cut]); !errors.Is(err, ErrShort) {
                t.Errorf("cut at %d: err = %v, want ErrShort", cut, err)
            }
        }
        for i := 2; i < len(good); i++ { // value bytes and the checksum byte itself
            bad := append([]byte(nil), good...)
            bad[i] ^= 0x10
            if _, _, err := Decode(bad); !errors.Is(err, ErrChecksum) {
                t.Errorf("flip at %d: err = %v, want ErrChecksum", i, err)
            }
        }
        bad := append([]byte(nil), good...)
        bad[0] = 8
        if _, _, err := Decode(bad); !errors.Is(err, ErrChecksum) {
            t.Errorf("changed tag: %v", err)
        }
        if _, _, err := Decode([]byte{0, 0, 0}); !errors.Is(err, ErrBadTag) {
            t.Errorf("tag 0: %v", err)
        }
        if _, _, err := Decode(nil); !errors.Is(err, ErrShort) {
            t.Errorf("empty: %v", err)
        }
        if _, _, err := Decode([]byte{5, 0xe3, 0, 0, 0}); !errors.Is(err, ErrBadPrefix) {
            t.Errorf("bad prefix: %v", err)
        }
        if _, _, err := Decode([]byte{5, 0xe0, 0, 0, 0, 3, 'a', 'b', 'c', 0}); !errors.Is(err, ErrNonCanonical) {
            t.Errorf("non-canonical: %v", err)
        }
    }

    func TestDecodeTooBigWithoutBody(t *testing.T) {
        hdr := AppendLadder([]byte{1}, 1048577)
        if _, _, err := Decode(hdr); !errors.Is(err, ErrTooBig) {
            t.Errorf("err = %v, want ErrTooBig", err)
        }
        hdr = AppendLadder([]byte{1}, 1048576)
        if _, _, err := Decode(hdr); !errors.Is(err, ErrShort) {
            t.Errorf("err = %v, want ErrShort", err)
        }
        hdr = AppendLadder([]byte{1}, 4000000000)
        if _, _, err := Decode(hdr); !errors.Is(err, ErrTooBig) {
            t.Errorf("err = %v, want ErrTooBig", err)
        }
    }

    func mustEncode(t *testing.T, tag byte, v string) []byte {
        t.Helper()
        b, err := Encode(Frame{Tag: tag, Value: []byte(v)})
        if err != nil {
            t.Fatal(err)
        }
        return b
    }

    func TestDecodeAll(t *testing.T) {
        var buf []byte
        buf = append(buf, 0, 0)
        buf = append(buf, mustEncode(t, 1, "one")...)
        buf = append(buf, 0)
        buf = append(buf, mustEncode(t, 2, "")...)
        buf = append(buf, mustEncode(t, 3, "three")...)
        buf = append(buf, 0, 0, 0)
        frames, err := DecodeAll(buf)
        if err != nil || len(frames) != 3 {
            t.Fatalf("got %d frames, %v", len(frames), err)
        }
        if frames[0].Tag != 1 || string(frames[0].Value) != "one" || frames[1].Tag != 2 || len(frames[1].Value) != 0 || frames[2].Tag != 3 || string(frames[2].Value) != "three" {
            t.Errorf("frames: %+v", frames)
        }
        if fr, err := DecodeAll(nil); err != nil || len(fr) != 0 {
            t.Errorf("nil: %v %v", fr, err)
        }
        if fr, err := DecodeAll([]byte{0, 0}); err != nil || len(fr) != 0 {
            t.Errorf("only padding: %v %v", fr, err)
        }
    }

    func TestDecodeAllStopsAtError(t *testing.T) {
        a := mustEncode(t, 1, "aa")
        b := mustEncode(t, 2, "bb")
        b[len(b)-1]++
        c := mustEncode(t, 3, "cc")
        frames, err := DecodeAll(append(append(append([]byte(nil), a...), b...), c...))
        if !errors.Is(err, ErrChecksum) || len(frames) != 1 || frames[0].Tag != 1 {
            t.Errorf("got %+v, %v", frames, err)
        }
        frames, err = DecodeAll(append(append([]byte(nil), a...), c[:3]...))
        if !errors.Is(err, ErrShort) || len(frames) != 1 {
            t.Errorf("truncated tail: %+v, %v", frames, err)
        }
        frames, err = DecodeAll(append(append([]byte(nil), a...), c[0]))
        if !errors.Is(err, ErrShort) || len(frames) != 1 {
            t.Errorf("one stray byte: %+v, %v", frames, err)
        }
        if _, err = DecodeAll([]byte{7}); !errors.Is(err, ErrShort) {
            t.Errorf("lone byte: %v", err)
        }
    }

    func TestPad(t *testing.T) {
        cases := []struct{ n, align, want int }{{0, 4, 0}, {1, 4, 4}, {4, 4, 4}, {5, 4, 8}, {7, 8, 8}, {9, 1, 9}, {9, 0, 9}, {9, -3, 9}, {10, 3, 12}}
        for _, c := range cases {
            got := Pad(bytes.Repeat([]byte{7}, c.n), c.align)
            if len(got) != c.want {
                t.Errorf("Pad(%d, %d): len %d, want %d", c.n, c.align, len(got), c.want)
                continue
            }
            for i, x := range got {
                want := byte(0)
                if i < c.n {
                    want = 7
                }
                if x != want {
                    t.Errorf("Pad(%d, %d): byte %d = %d", c.n, c.align, i, x)
                }
            }
        }
    }

    func TestDecoderByteAtATime(t *testing.T) {
        var stream []byte
        stream = append(stream, mustEncode(t, 1, "alpha")...)
        stream = append(stream, 0)
        stream = append(stream, mustEncode(t, 2, string(bytes.Repeat([]byte("z"), 200)))...)
        stream = append(stream, mustEncode(t, 3, "")...)
        var d Decoder
        var got []Frame
        for _, c := range stream {
            d.Write([]byte{c})
            for {
                f, ok, err := d.Next()
                if err != nil {
                    t.Fatal(err)
                }
                if !ok {
                    break
                }
                got = append(got, f)
            }
        }
        if len(got) != 3 || got[0].Tag != 1 || len(got[1].Value) != 200 || got[2].Tag != 3 {
            t.Fatalf("got %+v", got)
        }
        if d.Buffered() != 0 {
            t.Errorf("buffered = %d", d.Buffered())
        }
    }

    func TestDecoderKeepsPartial(t *testing.T) {
        raw := mustEncode(t, 5, "partial")
        var d Decoder
        d.Write(raw[:4])
        f, ok, err := d.Next()
        if ok || err != nil || f.Tag != 0 {
            t.Fatalf("early: %+v %v %v", f, ok, err)
        }
        if d.Buffered() != 4 {
            t.Errorf("buffered = %d, want 4", d.Buffered())
        }
        d.Write(raw[4:])
        f, ok, err = d.Next()
        if !ok || err != nil || string(f.Value) != "partial" {
            t.Fatalf("late: %+v %v %v", f, ok, err)
        }
        if _, ok, _ := d.Next(); ok {
            t.Errorf("a second frame appeared")
        }
    }

    func TestDecoderPaddingOnly(t *testing.T) {
        var d Decoder
        d.Write([]byte{0, 0, 0})
        if _, ok, err := d.Next(); ok || err != nil {
            t.Fatalf("%v %v", ok, err)
        }
        if d.Buffered() != 0 {
            t.Errorf("buffered = %d", d.Buffered())
        }
        d.Write(mustEncode(t, 9, "x"))
        if f, ok, _ := d.Next(); !ok || f.Tag != 9 {
            t.Errorf("%+v %v", f, ok)
        }
    }

    func TestDecoderDropsOneByteOnError(t *testing.T) {
        good := mustEncode(t, 4, "ok")
        bad := append([]byte(nil), good...)
        bad[len(bad)-1]++
        var d Decoder
        d.Write(bad)
        total := d.Buffered()
        _, ok, err := d.Next()
        if ok || !errors.Is(err, ErrChecksum) {
            t.Fatalf("ok=%v err=%v", ok, err)
        }
        if d.Buffered() != total-1 {
            t.Errorf("buffered = %d, want %d", d.Buffered(), total-1)
        }
    }

    func TestDecoderResyncsAfterGarbage(t *testing.T) {
        // 0x05 starts a "frame" whose length code is invalid; 0xF0 is then read as a tag and fails too (0xF1 is no prefix)
        good := mustEncode(t, 0xF1, "found")
        var d Decoder
        d.Write(append([]byte{0x05, 0xF0}, good...))
        errs := 0
        for i := 0; i < 5; i++ {
            f, ok, err := d.Next()
            if err != nil {
                errs++
                continue
            }
            if ok {
                if f.Tag != 0xF1 || string(f.Value) != "found" {
                    t.Fatalf("frame %+v", f)
                }
                if errs != 2 {
                    t.Errorf("errors before the frame: %d, want 2", errs)
                }
                return
            }
            t.Fatalf("stalled after %d errors", errs)
        }
        t.Fatal("never found the frame")
    }

    func TestDecoderTooBigIsImmediate(t *testing.T) {
        var d Decoder
        d.Write(AppendLadder([]byte{1}, 1048577))
        if _, ok, err := d.Next(); ok || !errors.Is(err, ErrTooBig) {
            t.Errorf("ok=%v err=%v", ok, err)
        }
    }
'''))

LIB = Lib(
    name="tlvlad", lang="go", title="the tlvlad package",
    blurb="The telemetry gateway frames sensor messages with tlvlad, a tag-length-value format whose lengths use a custom ladder integer code.",
    files={"go.mod": langs.go_mod("tlvlad"), "tlvlad.go": SRC, "README.md": README},
    visible_tests={"tlvlad_basic_test.go": VISIBLE},
    hidden_tests={"tlvlad_full_test.go": HIDDEN},
    mutate=["tlvlad.go"], difficulty=3, tags=["binary", "framing", "codec"],
)

register_libs([LIB], n=8)
