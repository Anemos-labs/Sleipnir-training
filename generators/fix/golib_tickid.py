"""Dock-ticket identifiers (go): bit-packed 64-bit ids with a clock-skew policy, check bits and a text form."""
from fx import Lib, dd, langs

from generators.fix._lang1 import gosrc, register_libs

README = dd('''
    # tickid

    Identifier generator for the dock-ticket service. An `ID` is a `uint64` packed, from the most significant bit down, as

    | field | bits | meaning |
    |---|---|---|
    | tick | 40 | 10 ms ticks since the generator's epoch |
    | lane | 10 | which issuing lane produced the ID (0..1023) |
    | seq  | 11 | counter inside one tick (0..2047) |
    | check | 3 | `(tick + 3*lane + 5*seq) mod 7` |

    Numeric order of IDs from one generator is therefore issue order.

    ## `Compose(p Parts) ID` and `Decode(id ID) (Parts, error)`
    `Parts` is `{Tick uint64; Lane, Seq uint16}`. `Compose` packs the fields (callers pass in-range values) and fills in
    the check bits. `Decode` unpacks; when the stored check bits do not equal the recomputed ones it returns
    `ErrBadCheck`.

    `(p Parts) UnixMillis(epochMs int64) int64` is the start of the tick: `epochMs + 10*Tick`.

    ## `NewGenerator(epochMs int64, lane uint16) (*Generator, error)`
    `lane > 1023` is `ErrBadLane`. `epochMs` is a Unix time in milliseconds.

    ## `(*Generator) Next(nowMs int64) (ID, error)`
    The tick of `nowMs` is `(nowMs - epochMs) / 10`, rounded down. A `nowMs` before the epoch is `ErrBeforeEpoch`
    (checked first; the generator is not changed by a failed call).

    * First call, or a tick later than the generator's current tick: the generator moves to that tick with `seq = 0`.
    * Otherwise the generator stays on its current tick and `seq` goes up by one. This also covers a clock that stepped
      back by at most 5 ticks compared with the generator's current tick.
    * A clock more than 5 ticks behind the generator's current tick is `ErrClockBackwards` (state unchanged).
    * When `seq` is already 2047 and another ID is needed, the generator *borrows* the next tick: tick + 1, `seq = 0`.
      Real time later catches up with the borrowed tick without duplicating IDs.

    ## Text form
    `(ID) String()` writes the 64 bits as 13 base-32 digits, most significant first, using the alphabet
    `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (the first digit carries only 4 bits). The result is grouped `4-4-5` with dashes,
    e.g. `AAAA-AAAA-SBAA3`.

    `Parse(s string) (ID, error)` accepts the canonical dashed form (15 chars, dashes at positions 4 and 9) or the same
    13 digits without dashes, in either letter case. Anything else (other length, misplaced dash, a character outside
    the alphabet, a first digit above `R`) is `ErrBadText`. `Parse` does not look at the check bits; use `Decode`.
''')

SRC = gosrc(dd(r'''
    // Package tickid generates and decodes bit-packed 64-bit identifiers.
    package tickid

    import (
        "errors"
        "strings"
    )

    const (
        TickMillis = 10
        laneBits   = 10
        seqBits    = 11
        checkBits  = 3

        MaxLane = 1<<laneBits - 1
        MaxSeq  = 1<<seqBits - 1
        // MaxSkew is how many ticks the clock may step back before Next gives up.
        MaxSkew = 5
    )

    var (
        ErrBeforeEpoch    = errors.New("tickid: time is before the epoch")
        ErrClockBackwards = errors.New("tickid: clock moved backwards")
        ErrBadLane        = errors.New("tickid: lane out of range")
        ErrBadCheck       = errors.New("tickid: check bits do not match")
        ErrBadText        = errors.New("tickid: malformed text")
    )

    // ID is a packed identifier.
    type ID uint64

    // Parts are the fields of an ID.
    type Parts struct {
        Tick uint64
        Lane uint16
        Seq  uint16
    }

    func checkOf(tick uint64, lane, seq uint16) uint64 {
        return (tick + 3*uint64(lane) + 5*uint64(seq)) % 7
    }

    // Compose packs the parts into an ID.
    func Compose(p Parts) ID {
        body := p.Tick<<(laneBits+seqBits) | uint64(p.Lane)<<seqBits | uint64(p.Seq)
        return ID(body<<checkBits | checkOf(p.Tick, p.Lane, p.Seq))
    }

    // Decode unpacks an ID and verifies its check bits.
    func Decode(id ID) (Parts, error) {
        v := uint64(id)
        check := v & (1<<checkBits - 1)
        v >>= checkBits
        p := Parts{
            Seq:  uint16(v & MaxSeq),
            Lane: uint16(v >> seqBits & MaxLane),
            Tick: v >> (seqBits + laneBits),
        }
        if checkOf(p.Tick, p.Lane, p.Seq) != check {
            return Parts{}, ErrBadCheck
        }
        return p, nil
    }

    // UnixMillis is the start of the tick, given the generator's epoch.
    func (p Parts) UnixMillis(epochMs int64) int64 {
        return epochMs + int64(p.Tick)*TickMillis
    }

    // Generator hands out IDs for one lane. It is not safe for concurrent use.
    type Generator struct {
        epochMs int64
        lane    uint16
        started bool
        tick    int64
        seq     uint16
    }

    // NewGenerator returns a generator for the lane.
    func NewGenerator(epochMs int64, lane uint16) (*Generator, error) {
        if lane > MaxLane {
            return nil, ErrBadLane
        }
        return &Generator{epochMs: epochMs, lane: lane}, nil
    }

    func (g *Generator) tickAt(nowMs int64) (int64, error) {
        if nowMs < g.epochMs {
            return 0, ErrBeforeEpoch
        }
        return (nowMs - g.epochMs) / TickMillis, nil
    }

    // Next issues the next ID for the given wall-clock time.
    func (g *Generator) Next(nowMs int64) (ID, error) {
        t, err := g.tickAt(nowMs)
        if err != nil {
            return 0, err
        }
        switch {
        case !g.started || t > g.tick:
            g.started = true
            g.tick, g.seq = t, 0
        case g.tick-t > MaxSkew:
            return 0, ErrClockBackwards
        default:
            // same tick, a tick we borrowed earlier, or a small step back of the clock
            if g.seq == MaxSeq {
                g.tick++
                g.seq = 0
            } else {
                g.seq++
            }
        }
        return Compose(Parts{Tick: uint64(g.tick), Lane: g.lane, Seq: g.seq}), nil
    }

    const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    // String is the dashed base-32 text form.
    func (id ID) String() string {
        var buf [13]byte
        v := uint64(id)
        for i := 12; i >= 0; i-- {
            buf[i] = alphabet[v&31]
            v >>= 5
        }
        s := string(buf[:])
        return s[:4] + "-" + s[4:8] + "-" + s[8:]
    }

    func upper(c byte) byte {
        if c >= 'a' && c <= 'z' {
            return c - 'a' + 'A'
        }
        return c
    }

    // Parse reads the text form back.
    func Parse(s string) (ID, error) {
        if len(s) == 15 {
            if s[4] != '-' || s[9] != '-' {
                return 0, ErrBadText
            }
            s = s[:4] + s[5:9] + s[10:]
        }
        if len(s) != 13 {
            return 0, ErrBadText
        }
        var v uint64
        for i := 0; i < 13; i++ {
            idx := strings.IndexByte(alphabet, upper(s[i]))
            if idx < 0 || (i == 0 && idx > 15) {
                return 0, ErrBadText
            }
            v = v<<5 | uint64(idx)
        }
        return ID(v), nil
    }
'''))

VISIBLE = gosrc(dd(r'''
    package tickid

    import "testing"

    func TestFirstIDs(t *testing.T) {
        g, err := NewGenerator(1_700_000_000_000, 7)
        if err != nil {
            t.Fatal(err)
        }
        a, _ := g.Next(1_700_000_000_000)
        b, _ := g.Next(1_700_000_000_003)
        pa, _ := Decode(a)
        pb, _ := Decode(b)
        if pa.Seq != 0 || pb.Seq != 1 || pa.Lane != 7 {
            t.Fatalf("got %+v then %+v", pa, pb)
        }
    }

    func TestComposeDecode(t *testing.T) {
        p := Parts{Tick: 99, Lane: 3, Seq: 4}
        got, err := Decode(Compose(p))
        if err != nil || got != p {
            t.Fatalf("got %+v, %v", got, err)
        }
    }
'''))

HIDDEN = gosrc(dd(r'''
    package tickid

    import (
        "errors"
        "testing"
    )

    const epoch = 1_700_000_000_000

    func mustGen(t *testing.T, lane uint16) *Generator {
        t.Helper()
        g, err := NewGenerator(epoch, lane)
        if err != nil {
            t.Fatal(err)
        }
        return g
    }

    func next(t *testing.T, g *Generator, now int64) Parts {
        t.Helper()
        id, err := g.Next(now)
        if err != nil {
            t.Fatalf("Next(%d): %v", now, err)
        }
        p, err := Decode(id)
        if err != nil {
            t.Fatalf("Decode: %v", err)
        }
        return p
    }

    func TestComposeLiterals(t *testing.T) {
        cases := []struct {
            p    Parts
            want uint64
        }{
            {Parts{1, 2, 3}, 16810009},
            {Parts{0, 0, 0}, 0},
            {Parts{123456789, 1023, 2047}, 2071261232496637},
            {Parts{1 << 39, 5, 6}, 9223372036854857780},
            {Parts{4242, 17, 100}, 71169229605},
        }
        for _, c := range cases {
            if got := Compose(c.p); uint64(got) != c.want {
                t.Errorf("Compose(%+v) = %d, want %d", c.p, got, c.want)
            }
            back, err := Decode(ID(c.want))
            if err != nil || back != c.p {
                t.Errorf("Decode(%d) = %+v, %v; want %+v", c.want, back, err, c.p)
            }
        }
    }

    func TestDecodeDetectsDamage(t *testing.T) {
        id := Compose(Parts{Tick: 4242, Lane: 17, Seq: 100})
        for bit := 0; bit < 3; bit++ {
            if _, err := Decode(id ^ (1 << bit)); !errors.Is(err, ErrBadCheck) {
                t.Errorf("flipping check bit %d: err = %v", bit, err)
            }
        }
        // a change in the seq field alone must also be noticed: seq+1 changes the check by 5
        if _, err := Decode(id + 8); !errors.Is(err, ErrBadCheck) {
            t.Errorf("seq damage: err = %v", err)
        }
        // lane+1 changes it by 3
        if _, err := Decode(id + (1 << 14)); !errors.Is(err, ErrBadCheck) {
            t.Errorf("lane damage: err = %v", err)
        }
        // tick+1 changes it by 1
        if _, err := Decode(id + (1 << 24)); !errors.Is(err, ErrBadCheck) {
            t.Errorf("tick damage: err = %v", err)
        }
        // tick+7 leaves the check unchanged: still decodes (the check is only 3 bits)
        p, err := Decode(Compose(Parts{Tick: 4249, Lane: 17, Seq: 100}))
        if err != nil || p.Tick != 4249 {
            t.Errorf("got %+v %v", p, err)
        }
    }

    func TestUnixMillis(t *testing.T) {
        if got := (Parts{Tick: 0}).UnixMillis(epoch); got != epoch {
            t.Errorf("got %d", got)
        }
        if got := (Parts{Tick: 12345}).UnixMillis(epoch); got != epoch+123450 {
            t.Errorf("got %d", got)
        }
    }

    func TestLaneRange(t *testing.T) {
        if _, err := NewGenerator(epoch, 1023); err != nil {
            t.Errorf("lane 1023: %v", err)
        }
        if _, err := NewGenerator(epoch, 1024); !errors.Is(err, ErrBadLane) {
            t.Errorf("lane 1024: %v", err)
        }
        if _, err := NewGenerator(epoch, 65535); !errors.Is(err, ErrBadLane) {
            t.Errorf("lane 65535: %v", err)
        }
    }

    func TestSequenceWithinTick(t *testing.T) {
        g := mustGen(t, 9)
        a := next(t, g, epoch+5)
        b := next(t, g, epoch+9)
        c := next(t, g, epoch+10)
        d := next(t, g, epoch+19)
        e := next(t, g, epoch+20)
        want := []Parts{{0, 9, 0}, {0, 9, 1}, {1, 9, 0}, {1, 9, 1}, {2, 9, 0}}
        for i, got := range []Parts{a, b, c, d, e} {
            if got != want[i] {
                t.Errorf("id %d = %+v, want %+v", i, got, want[i])
            }
        }
    }

    func TestTickRoundsDown(t *testing.T) {
        g := mustGen(t, 0)
        if p := next(t, g, epoch+99); p.Tick != 9 {
            t.Errorf("tick %d", p.Tick)
        }
        g = mustGen(t, 0)
        if p := next(t, g, epoch+100); p.Tick != 10 {
            t.Errorf("tick %d", p.Tick)
        }
    }

    func TestBeforeEpoch(t *testing.T) {
        g := mustGen(t, 1)
        if _, err := g.Next(epoch - 1); !errors.Is(err, ErrBeforeEpoch) {
            t.Fatalf("err = %v", err)
        }
        if p := next(t, g, epoch); p.Tick != 0 || p.Seq != 0 {
            t.Errorf("after error: %+v", p)
        }
        // epoch itself is fine, one millisecond earlier is not, also once started
        if _, err := g.Next(epoch - 5000); !errors.Is(err, ErrBeforeEpoch) {
            t.Fatalf("err = %v", err)
        }
    }

    func TestBorrowNextTick(t *testing.T) {
        g := mustGen(t, 2)
        now := int64(epoch + 40)
        var last Parts
        for i := 0; i <= MaxSeq; i++ {
            last = next(t, g, now)
            if last.Tick != 4 || int(last.Seq) != i {
                t.Fatalf("call %d: %+v", i, last)
            }
        }
        // the 2049th call within the tick spills into tick 5
        b := next(t, g, now)
        if b.Tick != 5 || b.Seq != 0 {
            t.Fatalf("borrowed: %+v", b)
        }
        // the clock is still on tick 4, we stay on the borrowed tick and keep counting
        c := next(t, g, now)
        if c.Tick != 5 || c.Seq != 1 {
            t.Fatalf("after borrow: %+v", c)
        }
        // real time reaches tick 5: no reset of seq (we are already there)
        d := next(t, g, epoch+50)
        if d.Tick != 5 || d.Seq != 2 {
            t.Fatalf("catching up: %+v", d)
        }
        // and tick 6 starts a fresh sequence
        e := next(t, g, epoch+60)
        if e.Tick != 6 || e.Seq != 0 {
            t.Fatalf("next real tick: %+v", e)
        }
    }

    func TestBorrowCanChain(t *testing.T) {
        g := mustGen(t, 2)
        for i := 0; i < 2*(MaxSeq+1)+1; i++ {
            if _, err := g.Next(epoch); err != nil {
                t.Fatal(err)
            }
        }
        // 2*2048+1 IDs issued at tick 0: the last is tick 2 seq 0
        p := next(t, g, epoch)
        if p.Tick != 2 || p.Seq != 1 {
            t.Errorf("got %+v", p)
        }
    }

    func TestClockSkew(t *testing.T) {
        g := mustGen(t, 4)
        first := next(t, g, epoch+1000) // tick 100
        if first.Tick != 100 {
            t.Fatalf("tick %d", first.Tick)
        }
        p := next(t, g, epoch+950) // 5 ticks back: tolerated, stays on tick 100
        if p.Tick != 100 || p.Seq != 1 {
            t.Errorf("5 back: %+v", p)
        }
        if _, err := g.Next(epoch + 940); !errors.Is(err, ErrClockBackwards) { // 6 back
            t.Errorf("6 back: err = %v", err)
        }
        // the failed call did not consume a sequence number
        p = next(t, g, epoch+1000)
        if p.Tick != 100 || p.Seq != 2 {
            t.Errorf("after failure: %+v", p)
        }
        p = next(t, g, epoch+969) // 4 ticks back
        if p.Tick != 100 || p.Seq != 3 {
            t.Errorf("4 back: %+v", p)
        }
    }

    func TestSkewMeasuredFromBorrowedTick(t *testing.T) {
        g := mustGen(t, 4)
        for i := 0; i <= MaxSeq+1; i++ { // ends on borrowed tick 51
            g.Next(epoch + 500)
        }
        if _, err := g.Next(epoch + 450); !errors.Is(err, ErrClockBackwards) { // tick 45 is 6 behind tick 51
            t.Fatalf("err = %v", err)
        }
        if _, err := g.Next(epoch + 460); err != nil { // tick 46: 5 behind
            t.Errorf("5 behind borrowed tick: %v", err)
        }
    }

    func TestIDsStrictlyIncrease(t *testing.T) {
        g := mustGen(t, 600)
        now := int64(epoch)
        seed := uint32(12345)
        var prev ID
        for i := 0; i < 6000; i++ {
            seed = seed*1664525 + 1013904223
            if seed>>28 < 6 { // sometimes stay on the same millisecond
                now += int64(seed>>24&15) * 3
            }
            id, err := g.Next(now)
            if err != nil {
                t.Fatal(err)
            }
            if id <= prev {
                t.Fatalf("id %d (%v) not above previous (%v)", i, id, prev)
            }
            prev = id
        }
    }

    func TestStringLiterals(t *testing.T) {
        cases := map[uint64]string{
            0:                   "AAAA-AAAA-AAAAA",
            16810009:            "AAAA-AAAA-SBAA3",
            2071261232496637:    "AAB4-53WL-99997",
            9223372036854857780: "JAAA-AAAA-ACSBW",
            71169229605:         "AAAA-ACCK-AJS3F",
        }
        for v, want := range cases {
            if got := ID(v).String(); got != want {
                t.Errorf("String(%d) = %q, want %q", v, got, want)
            }
        }
    }

    func TestParseForms(t *testing.T) {
        want := ID(2071261232496637)
        for _, s := range []string{"AAB4-53WL-99997", "AAB453WL99997", "aab4-53wl-99997", "aAb453Wl99997"} {
            got, err := Parse(s)
            if err != nil || got != want {
                t.Errorf("Parse(%q) = %d, %v", s, got, err)
            }
        }
        z, err := Parse("aaaa-aaaa-zzzzz")
        if err != nil || z != ID(23*(1<<20)+23*(1<<15)+23*(1<<10)+23*32+23) {
            t.Errorf("lower-case z: %d %v", z, err)
        }
        if got, err := Parse("R999-9999-99999"); err != nil || uint64(got) != 1<<64-1 {
            t.Errorf("max id: %d %v", got, err)
        }
    }

    func TestParseErrors(t *testing.T) {
        bad := []string{
            "", "AAB4-53WL-9999", "AAB4-53WL-999977", "AAB453WL9999", "AAB453WL999977",
            "AAB45-3WL-99997", "AAB4-53WL9-9997", "AAB4_53WL-99997", "AAB4-53WL_99997", "AAB4_53WL_99997", "AAB4 53WL 99997",
            "AAB4-53WL-9999I", "AAB4-53WL-9999O", "AAB4-53WL-9999 ", "0AB4-53WL-99997", "AAB4-53WL-9999!",
            "SAAA-AAAA-AAAAA", "ZAAA-AAAA-AAAAA", "AAB4-53WL-99-97", "AAB4-53WL-1AAAA",
        }
        for _, s := range bad {
            if _, err := Parse(s); !errors.Is(err, ErrBadText) {
                t.Errorf("Parse(%q): err = %v", s, err)
            }
        }
    }

    func TestRoundTripText(t *testing.T) {
        seed := uint64(88172645463325252)
        for i := 0; i < 300; i++ {
            seed ^= seed << 13
            seed ^= seed >> 7
            seed ^= seed << 17
            v := seed >> 1 // keep the top digit within 'R'
            id := ID(v)
            back, err := Parse(id.String())
            if err != nil || back != id {
                t.Fatalf("%d: %v %v", v, back, err)
            }
        }
    }
'''))

LIB = Lib(
    name="tickid", lang="go", title="the tickid package",
    blurb="The dock-ticket service issues its ticket numbers with tickid, a generator of bit-packed, sortable 64-bit identifiers with a text form.",
    files={"go.mod": langs.go_mod("tickid"), "tickid.go": SRC, "README.md": README},
    visible_tests={"tickid_basic_test.go": VISIBLE},
    hidden_tests={"tickid_full_test.go": HIDDEN},
    mutate=["tickid.go"], difficulty=1, tags=["ids", "bitpacking", "clock"],
)

register_libs([LIB], n=8)
