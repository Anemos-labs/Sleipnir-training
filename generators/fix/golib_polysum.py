"""Sensor-bus checksums (go): a parameterised CRC register (width 1..16, reflect option) plus a prime-modulus tally."""
from fx import Lib, dd, langs

from generators.fix._lang1 import gosrc, register_libs

README = dd('''
    # polysum

    Checksums for frames on the sensor bus. Two families: a parameterised CRC for the wire, and a cheap `Tally` for
    log lines.

    ## `Spec`
    ```go
    type Spec struct {
        Width   int    // 1..16 bits
        Poly    uint16 // generator polynomial without its top bit, e.g. 0x80F for x^12+x^11+x^3+x^2+x+1
        Init    uint16 // register start value
        XorOut  uint16 // xor-ed into the final value
        Reflect bool   // feed each byte LSB first and reflect the register before XorOut
    }
    ```
    `(Spec) Validate() error` returns `ErrBadSpec` unless `1 <= Width <= 16`, `Poly != 0`, and `Poly`, `Init` and
    `XorOut` all fit in `Width` bits (no bit set at or above position `Width`).

    `(Spec) String()` renders `crc<Width>/<poly> init=<init> xor=<xorout> <order>` with every number as `%#x` and the
    order `lsb` when `Reflect` is set and `msb` otherwise, e.g. `crc12/0x80f init=0x0 xor=0x0 msb`.

    ## The register
    `New(s Spec) (*Hasher, error)` validates the spec (and returns its error) and starts with the register at `Init`.
    For every input byte, for each of its 8 bits (most significant first, or least significant first when `Reflect`):

    1. `feedback` is true when the register's top bit (bit `Width-1`) differs from the input bit;
    2. the register is shifted left by one and truncated to `Width` bits;
    3. if `feedback`, the register is xor-ed with `Poly`.

    `Sum()` is the register, bit-reversed within `Width` bits when `Reflect`, xor-ed with `XorOut`. It does not change
    the state: more bytes can be written afterwards. `Reset()` returns to `Init`. `Write(p)` feeds bytes; writing in
    pieces gives the same result as writing everything at once.

    This is the usual "Rocksoft" CRC model, so the common presets behave as published (CRC-16/ARC of `123456789` is
    `0xbb3d`).

    `Checksum(s Spec, data []byte) (uint16, error)` is `New` + `Write` + `Sum` in one call.

    ## Framing helpers
    `Append(s Spec, data []byte) ([]byte, error)` returns a new slice: `data` followed by its checksum in
    `(Width+7)/8` bytes, big-endian. `Verify(s Spec, framed []byte) (bool, error)` splits the trailing checksum bytes off,
    recomputes over the rest and compares; a frame shorter than the checksum is simply `false`. For a width that is not a multiple
    of 8 the unused high bits of the first checksum byte must be zero, otherwise `Verify` says `false`.

    ## `Tally(data []byte) uint16`
    Adler-style with prime 251: start with `a = 1`, `b = 0`; for each byte `c`: `a = (a + c) mod 251`, then
    `b = (b + a) mod 251`. The result is `b<<8 | a`.
''')

SRC = gosrc(dd(r'''
    // Package polysum computes parameterised CRCs and a simple tally for sensor frames.
    package polysum

    import (
        "errors"
        "fmt"
    )

    // ErrBadSpec is returned for an invalid CRC specification.
    var ErrBadSpec = errors.New("polysum: bad spec")

    // Spec describes a CRC in the Rocksoft model.
    type Spec struct {
        Width   int
        Poly    uint16
        Init    uint16
        XorOut  uint16
        Reflect bool
    }

    func widthMask(width int) uint16 {
        if width >= 16 {
            return 0xFFFF
        }
        return 1<<uint(width) - 1
    }

    // Validate checks the spec.
    func (s Spec) Validate() error {
        if s.Width < 1 || s.Width > 16 || s.Poly == 0 {
            return ErrBadSpec
        }
        m := widthMask(s.Width)
        if s.Poly&^m != 0 || s.Init&^m != 0 || s.XorOut&^m != 0 {
            return ErrBadSpec
        }
        return nil
    }

    func (s Spec) String() string {
        order := "msb"
        if s.Reflect {
            order = "lsb"
        }
        return fmt.Sprintf("crc%d/%#x init=%#x xor=%#x %s", s.Width, s.Poly, s.Init, s.XorOut, order)
    }

    func reverse(x uint16, n int) uint16 {
        var r uint16
        for i := 0; i < n; i++ {
            if x>>uint(i)&1 == 1 {
                r |= 1 << uint(n-1-i)
            }
        }
        return r
    }

    // Hasher is a running CRC.
    type Hasher struct {
        spec Spec
        reg  uint16
    }

    // New returns a hasher for a valid spec.
    func New(s Spec) (*Hasher, error) {
        if err := s.Validate(); err != nil {
            return nil, err
        }
        return &Hasher{spec: s, reg: s.Init}, nil
    }

    // Reset restarts the computation.
    func (h *Hasher) Reset() { h.reg = h.spec.Init }

    // Write feeds bytes into the register.
    func (h *Hasher) Write(p []byte) {
        m := widthMask(h.spec.Width)
        top := uint16(1) << uint(h.spec.Width-1)
        for _, b := range p {
            for i := 0; i < 8; i++ {
                var bit uint16
                if h.spec.Reflect {
                    bit = uint16(b>>uint(i)) & 1
                } else {
                    bit = uint16(b>>uint(7-i)) & 1
                }
                feedback := (h.reg&top != 0) != (bit == 1)
                h.reg = (h.reg << 1) & m
                if feedback {
                    h.reg ^= h.spec.Poly
                }
            }
        }
    }

    // Sum returns the checksum of everything written so far.
    func (h *Hasher) Sum() uint16 {
        r := h.reg
        if h.spec.Reflect {
            r = reverse(r, h.spec.Width)
        }
        return r ^ h.spec.XorOut
    }

    // Checksum computes the CRC of data in one call.
    func Checksum(s Spec, data []byte) (uint16, error) {
        h, err := New(s)
        if err != nil {
            return 0, err
        }
        h.Write(data)
        return h.Sum(), nil
    }

    // Append returns data followed by its big-endian checksum.
    func Append(s Spec, data []byte) ([]byte, error) {
        sum, err := Checksum(s, data)
        if err != nil {
            return nil, err
        }
        size := (s.Width + 7) / 8
        out := make([]byte, 0, len(data)+size)
        out = append(out, data...)
        for i := size - 1; i >= 0; i-- {
            out = append(out, byte(sum>>uint(8*i)))
        }
        return out, nil
    }

    // Verify checks a frame produced by Append.
    func Verify(s Spec, framed []byte) (bool, error) {
        if err := s.Validate(); err != nil {
            return false, err
        }
        size := (s.Width + 7) / 8
        if len(framed) < size {
            return false, nil
        }
        body, tail := framed[:len(framed)-size], framed[len(framed)-size:]
        var got uint16
        for _, c := range tail {
            got = got<<8 | uint16(c)
        }
        if got&^widthMask(s.Width) != 0 {
            return false, nil
        }
        want, _ := Checksum(s, body)
        return got == want, nil
    }

    // Tally is a cheap prime-modulus checksum for log lines.
    func Tally(data []byte) uint16 {
        a, b := uint16(1), uint16(0)
        for _, c := range data {
            a = (a + uint16(c)) % 251
            b = (b + a) % 251
        }
        return b<<8 | a
    }
'''))

VISIBLE = gosrc(dd(r'''
    package polysum

    import "testing"

    func TestArcPreset(t *testing.T) {
        arc := Spec{Width: 16, Poly: 0x8005, Reflect: true}
        got, err := Checksum(arc, []byte("123456789"))
        if err != nil || got != 0xbb3d {
            t.Fatalf("got %#x, %v", got, err)
        }
    }

    func TestTallyOfNothing(t *testing.T) {
        if got := Tally(nil); got != 1 {
            t.Fatalf("got %d", got)
        }
    }
'''))

HIDDEN = gosrc(dd(r'''
    package polysum

    import (
        "bytes"
        "errors"
        "testing"
    )

    func seq(n int) []byte {
        b := make([]byte, n)
        for i := range b {
            b[i] = byte(i)
        }
        return b
    }

    var inputs = [][]byte{
        {}, []byte("123456789"), {0}, {255, 255, 255}, []byte("sensor-7:21.5C"), seq(40),
    }

    var table = []struct {
        spec Spec
        want [6]uint16
    }{
        {Spec{12, 0x80F, 0, 0, false}, [6]uint16{0x0, 0xf5b, 0x0, 0x19e, 0x579, 0xd9d}},
        {Spec{8, 0x1D, 0xFF, 0, false}, [6]uint16{0xff, 0xb4, 0xc4, 0x85, 0xad, 0xf1}},
        {Spec{8, 0x07, 0, 0x55, true}, [6]uint16{0x55, 0x75, 0x55, 0xa5, 0x51, 0x12}},
        {Spec{16, 0x8005, 0, 0, true}, [6]uint16{0x0, 0xbb3d, 0x0, 0x8031, 0x60fd, 0x45c4}},
        {Spec{16, 0x1021, 0xFFFF, 0, false}, [6]uint16{0xffff, 0x29b1, 0xe1f0, 0x1ef0, 0xba47, 0x476}},
        {Spec{5, 0x05, 0x1F, 0x1F, true}, [6]uint16{0x0, 0x19, 0x1, 0xd, 0x16, 0x11}},
        {Spec{3, 0x3, 0, 0, false}, [6]uint16{0x0, 0x3, 0x0, 0x2, 0x7, 0x4}},
        {Spec{16, 0xA2B7, 0x1234, 0xFFFF, false}, [6]uint16{0xedcb, 0x7a7c, 0x3a85, 0x51f, 0x18fc, 0xa5ae}},
        {Spec{1, 1, 0, 0, false}, [6]uint16{0x0, 0x1, 0x0, 0x0, 0x1, 0x0}},
        {Spec{10, 0x233, 0x3FF, 0, true}, [6]uint16{0x3ff, 0x19f, 0x21f, 0x11, 0x171, 0x378}},
    }

    func TestChecksumTable(t *testing.T) {
        for _, row := range table {
            for i, in := range inputs {
                got, err := Checksum(row.spec, in)
                if err != nil || got != row.want[i] {
                    t.Errorf("%v input %d: got %#x, %v; want %#x", row.spec, i, got, err, row.want[i])
                }
            }
        }
    }

    func TestSumDoesNotDisturbState(t *testing.T) {
        for _, row := range table {
            h, err := New(row.spec)
            if err != nil {
                t.Fatal(err)
            }
            h.Write([]byte("123456"))
            _ = h.Sum()
            _ = h.Sum()
            h.Write([]byte("789"))
            if got := h.Sum(); got != row.want[1] {
                t.Errorf("%v: got %#x want %#x", row.spec, got, row.want[1])
            }
        }
    }

    func TestChunkedWrites(t *testing.T) {
        data := seq(40)
        for _, row := range table {
            for _, step := range []int{1, 3, 7, 39} {
                h, _ := New(row.spec)
                for i := 0; i < len(data); i += step {
                    end := i + step
                    if end > len(data) {
                        end = len(data)
                    }
                    h.Write(data[i:end])
                }
                if got := h.Sum(); got != row.want[5] {
                    t.Errorf("%v step %d: got %#x want %#x", row.spec, step, got, row.want[5])
                }
            }
        }
    }

    func TestReset(t *testing.T) {
        h, _ := New(Spec{16, 0xA2B7, 0x1234, 0xFFFF, false})
        h.Write([]byte("garbage"))
        h.Reset()
        if got := h.Sum(); got != 0xedcb {
            t.Errorf("after reset, empty sum = %#x", got)
        }
        h.Write([]byte("123456789"))
        if got := h.Sum(); got != 0x7a7c {
            t.Errorf("after reset: %#x", got)
        }
    }

    func TestValidate(t *testing.T) {
        good := []Spec{
            {16, 0xFFFF, 0xFFFF, 0xFFFF, false}, {1, 1, 1, 1, true}, {12, 0xFFF, 0xFFF, 0xFFF, false},
            {8, 0xFF, 0, 0, true}, {9, 0x1FF, 0x100, 0x1FF, false}, {16, 1, 0, 0, true},
        }
        for _, s := range good {
            if err := s.Validate(); err != nil {
                t.Errorf("%v: %v", s, err)
            }
        }
        bad := []Spec{
            {0, 1, 0, 0, false}, {-3, 1, 0, 0, false}, {17, 1, 0, 0, false}, {12, 0, 0, 0, false},
            {12, 0x1000, 0, 0, false}, {12, 0x80F, 0x1000, 0, false}, {12, 0x80F, 0, 0x1000, false},
            {8, 0x100, 0, 0, false}, {1, 2, 0, 0, false}, {1, 1, 2, 0, false}, {1, 1, 0, 2, false}, {5, 0x20, 0, 0, true},
        }
        for _, s := range bad {
            if err := s.Validate(); !errors.Is(err, ErrBadSpec) {
                t.Errorf("%v: err = %v, want ErrBadSpec", s, err)
            }
            if _, err := New(s); !errors.Is(err, ErrBadSpec) {
                t.Errorf("New(%v): err = %v", s, err)
            }
            if _, err := Checksum(s, nil); !errors.Is(err, ErrBadSpec) {
                t.Errorf("Checksum(%v): err = %v", s, err)
            }
            if _, err := Append(s, nil); !errors.Is(err, ErrBadSpec) {
                t.Errorf("Append(%v): err = %v", s, err)
            }
            if ok, err := Verify(s, []byte{1, 2, 3}); ok || !errors.Is(err, ErrBadSpec) {
                t.Errorf("Verify(%v): %v, err = %v", s, ok, err)
            }
        }
    }

    func TestString(t *testing.T) {
        cases := map[Spec]string{
            {12, 0x80F, 0, 0, false}:          "crc12/0x80f init=0x0 xor=0x0 msb",
            {16, 0x8005, 0, 0, true}:          "crc16/0x8005 init=0x0 xor=0x0 lsb",
            {16, 0xA2B7, 0x1234, 0xFFFF, false}: "crc16/0xa2b7 init=0x1234 xor=0xffff msb",
            {5, 0x05, 0x1F, 0x1F, true}:       "crc5/0x5 init=0x1f xor=0x1f lsb",
        }
        for s, want := range cases {
            if got := s.String(); got != want {
                t.Errorf("got %q, want %q", got, want)
            }
        }
    }

    func TestAppendLayout(t *testing.T) {
        data := []byte("123456789")
        got, err := Append(Spec{16, 0x8005, 0, 0, true}, data)
        if err != nil || !bytes.Equal(got, append(append([]byte(nil), data...), 0xbb, 0x3d)) {
            t.Errorf("crc16: %x %v", got, err)
        }
        got, _ = Append(Spec{12, 0x80F, 0, 0, false}, data)
        if !bytes.Equal(got[len(data):], []byte{0x0f, 0x5b}) {
            t.Errorf("crc12 tail: %x", got[len(data):])
        }
        got, _ = Append(Spec{8, 0x1D, 0xFF, 0, false}, data)
        if !bytes.Equal(got[len(data):], []byte{0xb4}) || len(got) != len(data)+1 {
            t.Errorf("crc8 tail: %x", got[len(data):])
        }
        got, _ = Append(Spec{1, 0x1, 0, 0, false}, data)
        if !bytes.Equal(got[len(data):], []byte{0x01}) || len(got) != len(data)+1 {
            t.Errorf("crc1 tail: %x", got[len(data):])
        }
        got, _ = Append(Spec{9, 0x119, 0x1FF, 0, false}, data)
        if !bytes.Equal(got[len(data):], []byte{0x01, 0xa9}) {
            t.Errorf("crc9 tail: %x", got[len(data):])
        }
        got, _ = Append(Spec{3, 0x3, 0, 0, false}, data)
        if !bytes.Equal(got[len(data):], []byte{0x03}) {
            t.Errorf("crc3 tail: %x", got[len(data):])
        }
        // Append must not write into the caller's backing array
        buf := make([]byte, 3, 64)
        copy(buf, "abc")
        out, _ := Append(Spec{8, 0x1D, 0xFF, 0, false}, buf)
        if buf[:4][3] != 0 {
            t.Errorf("caller's buffer was written")
        }
        if len(buf) != 3 || string(out[:3]) != "abc" {
            t.Errorf("out = %q", out)
        }
    }

    func TestVerify(t *testing.T) {
        for _, row := range table {
            for _, in := range inputs {
                framed, err := Append(row.spec, in)
                if err != nil {
                    t.Fatal(err)
                }
                ok, err := Verify(row.spec, framed)
                if err != nil || !ok {
                    t.Errorf("%v len %d: verify = %v, %v", row.spec, len(in), ok, err)
                }
                if len(in) > 0 {
                    framed[0] ^= 0x01
                    if ok, _ := Verify(row.spec, framed); ok {
                        t.Errorf("%v: corrupted body accepted", row.spec)
                    }
                    framed[0] ^= 0x01
                }
            }
        }
    }

    func TestVerifyEdges(t *testing.T) {
        s := Spec{16, 0x8005, 0, 0, true}
        if ok, err := Verify(s, nil); ok || err != nil {
            t.Errorf("nil frame: %v %v", ok, err)
        }
        if ok, err := Verify(s, []byte{0xbb}); ok || err != nil {
            t.Errorf("one byte: %v %v", ok, err)
        }
        // an empty body with a matching checksum is a valid frame (checksum of nothing is 0 for this spec)
        if ok, _ := Verify(s, []byte{0, 0}); !ok {
            t.Errorf("empty body, zero checksum rejected")
        }
        if ok, _ := Verify(s, []byte{0, 1}); ok {
            t.Errorf("wrong checksum accepted")
        }
        // last byte of the frame damaged
        framed, _ := Append(s, []byte("hello"))
        framed[len(framed)-1] ^= 0x80
        if ok, _ := Verify(s, framed); ok {
            t.Errorf("damaged checksum accepted")
        }
        // width 12: top nibble of the first checksum byte must be zero
        s12 := Spec{12, 0x80F, 0, 0, false}
        good, _ := Append(s12, []byte("123456789")) // checksum 0x0f5b
        if ok, _ := Verify(s12, good); !ok {
            t.Fatalf("good 12-bit frame rejected")
        }
        bad := append([]byte(nil), good...)
        bad[len(bad)-2] |= 0x10
        if ok, _ := Verify(s12, bad); ok {
            t.Errorf("stray high bit accepted (12-bit)")
        }
        // width 3 in one byte
        s3 := Spec{3, 0x3, 0, 0, false}
        good, _ = Append(s3, []byte("123456789")) // checksum 3
        bad = append([]byte(nil), good...)
        bad[len(bad)-1] |= 0x08
        if ok, _ := Verify(s3, bad); ok {
            t.Errorf("stray high bit accepted (3-bit)")
        }
        if ok, _ := Verify(s3, good); !ok {
            t.Errorf("good 3-bit frame rejected")
        }
    }

    func TestTally(t *testing.T) {
        want := []uint16{1, 19427, 257, 6925, 56662, 40476}
        for i, in := range inputs {
            if got := Tally(in); got != want[i] {
                t.Errorf("Tally(input %d) = %d, want %d", i, got, want[i])
            }
        }
        // the modulus matters: 251 bytes of 1 wrap a back to 1 + 251 mod 251
        long := bytes.Repeat([]byte{1}, 300)
        a, b := 1, 0
        for range long {
            a = (a + 1) % 251
            b = (b + a) % 251
        }
        if got := Tally(long); got != uint16(b<<8|a) {
            t.Errorf("long input: got %d, want %d", got, b<<8|a)
        }
    }
'''))

LIB = Lib(
    name="polysum", lang="go", title="the polysum package",
    blurb="The sensor-bus gateway uses polysum to protect frames with a configurable CRC and to tag log lines with a cheap tally.",
    files={"go.mod": langs.go_mod("polysum"), "polysum.go": SRC, "README.md": README},
    visible_tests={"polysum_basic_test.go": VISIBLE},
    hidden_tests={"polysum_full_test.go": HIDDEN},
    mutate=["polysum.go"], difficulty=3, tags=["checksum", "bits", "crc"],
)

register_libs([LIB], n=8)
