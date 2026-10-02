"""IPv4 address planning (go): CIDR blocks, aggregation, subtraction, splitting and variable-length allocation."""
from fx import Lib, dd, langs

from generators.fix._lang1 import gosrc, register_libs

README = dd('''
    # cidrplan

    Address planning helpers for the network inventory tool. Only IPv4 blocks in CIDR notation; everything is integer arithmetic on `uint32`.

    ## `Block`
    `Block{Addr uint32; Bits int}`: the block of `2^(32-Bits)` addresses that starts at `Addr`, whose host bits are zero. `Bits` is 0..32.
    * `ParseBlock(s string) (Block, error)`: `a.b.c.d/n`, or a bare `a.b.c.d` meaning `/32`. Each octet is 0..255 written without leading zeros (`0` alone is fine); the
      prefix is written without leading zeros either. Errors: `ErrSyntax` for anything malformed (wrong number of octets, non-digits, octet above 255, leading zeros,
      empty parts, whitespace), `ErrPrefix` for a prefix above 32 (however many digits it has), `ErrHostBits` when the address has bits set below the prefix (`10.0.0.1/24`). Syntax is
      checked before prefix range, prefix range before host bits.
    * `(Block) String() string` is `a.b.c.d/n` (always with the prefix, `/32` included).
    * `Size() uint64` number of addresses; `First()` and `Last() uint32` the first and last address; `Contains(addr uint32) bool`;
      `ContainsBlock(o Block) bool` (equal blocks contain each other); `Overlaps(o Block) bool`.
    * `Usable() uint64`: addresses that can be given to hosts: `Size() - 2` for prefixes up to `/30`, 2 for `/31`, 1 for `/32`.

    ## `Aggregate(blocks []Block) []Block`
    The shortest list of blocks that covers exactly the addresses covered by the input: blocks contained in others disappear, and two sibling blocks (the two
    halves of a bigger block) merge into their parent, repeatedly. Duplicates are fine. The result is sorted by address. The input is not modified. No blocks
    give an empty result (nil or empty).

    ## `Subtract(a, b Block) []Block`
    The addresses of `a` that are not in `b`, as the fewest blocks, sorted by address: `[a]` if they do not overlap, empty if `b` contains `a`.

    ## `Split(b Block, bits int) ([]Block, error)`
    All blocks of prefix length `bits` inside `b`, in address order. `ErrPrefix` when `bits < b.Bits` or `bits > 32`; `ErrTooMany` when there would be more than
    65536 of them.

    ## `Allocate(pool Block, hosts []int) ([]Block, error)`
    Variable-length subnetting: for each requested number of hosts, the smallest block whose `Usable()` count is at least that many (`hosts == 1` and `hosts == 2`
    both give a `/30`; a `/31` or `/32` is never handed out). A request below 1, or above what a `/0` can hold, is `ErrBadHosts`. The blocks are carved out of
    `pool` from its first address on, largest block first (requests of equal size keep the order in which they were asked), each at the next address that is a
    multiple of its size. The result lists the blocks in the order of the *requests*. `ErrNoSpace` if the pool runs out.
''')

SRC = gosrc(dd(r'''
    // Package cidrplan plans IPv4 address space.
    package cidrplan

    import (
        "errors"
        "fmt"
        "sort"
        "strconv"
        "strings"
    )

    var (
        ErrSyntax   = errors.New("cidrplan: syntax error")
        ErrPrefix   = errors.New("cidrplan: prefix length out of range")
        ErrHostBits = errors.New("cidrplan: host bits set")
        ErrTooMany  = errors.New("cidrplan: too many blocks")
        ErrBadHosts = errors.New("cidrplan: bad host count")
        ErrNoSpace  = errors.New("cidrplan: pool exhausted")
    )

    // Block is an aligned IPv4 range.
    type Block struct {
        Addr uint32
        Bits int
    }

    func plainNumber(s string, max uint64) (uint64, bool) {
        if s == "" || (len(s) > 1 && s[0] == '0') {
            return 0, false
        }
        for i := 0; i < len(s); i++ {
            if s[i] < '0' || s[i] > '9' {
                return 0, false
            }
        }
        n, err := strconv.ParseUint(s, 10, 64)
        if err != nil || n > max {
            return 0, false
        }
        return n, true
    }

    // ParseBlock reads "10.0.0.0/22" or a bare address.
    func ParseBlock(s string) (Block, error) {
        addrText, prefixText, hasPrefix := strings.Cut(s, "/")
        octets := strings.Split(addrText, ".")
        if len(octets) != 4 {
            return Block{}, ErrSyntax
        }
        var addr uint32
        for _, o := range octets {
            n, ok := plainNumber(o, 255)
            if !ok {
                return Block{}, ErrSyntax
            }
            addr = addr<<8 | uint32(n)
        }
        bits := 32
        if hasPrefix {
            digits := prefixText
            if digits == "" || (len(digits) > 1 && digits[0] == '0') {
                return Block{}, ErrSyntax
            }
            for i := 0; i < len(digits); i++ {
                if digits[i] < '0' || digits[i] > '9' {
                    return Block{}, ErrSyntax
                }
            }
            if len(digits) > 2 {
                return Block{}, ErrPrefix
            }
            n, _ := strconv.Atoi(digits)
            if n > 32 {
                return Block{}, ErrPrefix
            }
            bits = n
        }
        b := Block{addr, bits}
        if addr&^b.mask() != 0 {
            return Block{}, ErrHostBits
        }
        return b, nil
    }

    func (b Block) mask() uint32 {
        if b.Bits == 0 {
            return 0
        }
        return ^uint32(0) << (32 - b.Bits)
    }

    func (b Block) String() string {
        return fmt.Sprintf("%d.%d.%d.%d/%d", b.Addr>>24, b.Addr>>16&255, b.Addr>>8&255, b.Addr&255, b.Bits)
    }

    // Size is the number of addresses in the block.
    func (b Block) Size() uint64 { return 1 << (32 - b.Bits) }

    // First is the lowest address.
    func (b Block) First() uint32 { return b.Addr }

    // Last is the highest address.
    func (b Block) Last() uint32 { return b.Addr | ^b.mask() }

    // Contains reports whether addr lies in the block.
    func (b Block) Contains(addr uint32) bool { return addr&b.mask() == b.Addr }

    // ContainsBlock reports whether o lies entirely inside b.
    func (b Block) ContainsBlock(o Block) bool { return o.Bits >= b.Bits && b.Contains(o.Addr) }

    // Overlaps reports whether the blocks share an address.
    func (b Block) Overlaps(o Block) bool { return b.ContainsBlock(o) || o.ContainsBlock(b) }

    // Usable is the number of host addresses.
    func (b Block) Usable() uint64 {
        switch {
        case b.Bits >= 32:
            return 1
        case b.Bits == 31:
            return 2
        }
        return b.Size() - 2
    }

    // Aggregate merges blocks into the smallest equivalent list.
    func Aggregate(blocks []Block) []Block {
        sorted := append([]Block(nil), blocks...)
        sort.Slice(sorted, func(i, j int) bool {
            if sorted[i].Addr != sorted[j].Addr {
                return sorted[i].Addr < sorted[j].Addr
            }
            return sorted[i].Bits < sorted[j].Bits
        })
        var out []Block
        for _, b := range sorted {
            if n := len(out); n > 0 && out[n-1].ContainsBlock(b) {
                continue
            }
            out = append(out, b)
            for n := len(out); n >= 2; n = len(out) {
                a, c := out[n-2], out[n-1]
                if a.Bits != c.Bits || a.Bits == 0 || a.Addr&(1<<(32-a.Bits)) != 0 || c.Addr != a.Addr|1<<(32-a.Bits) {
                    break
                }
                out = append(out[:n-2], Block{a.Addr, a.Bits - 1})
            }
        }
        return out
    }

    // Subtract returns a minus b.
    func Subtract(a, b Block) []Block {
        if !a.Overlaps(b) {
            return []Block{a}
        }
        if b.ContainsBlock(a) {
            return nil
        }
        low := Block{a.Addr, a.Bits + 1}
        high := Block{a.Addr | 1<<(31-a.Bits), a.Bits + 1}
        return append(Subtract(low, b), Subtract(high, b)...)
    }

    // Split cuts a block into equal sub-blocks.
    func Split(b Block, bits int) ([]Block, error) {
        if bits < b.Bits || bits > 32 {
            return nil, ErrPrefix
        }
        count := uint64(1) << (bits - b.Bits)
        if count > 65536 {
            return nil, ErrTooMany
        }
        step := uint64(1) << (32 - bits)
        out := make([]Block, 0, count)
        for i := uint64(0); i < count; i++ {
            out = append(out, Block{uint32(uint64(b.Addr) + i*step), bits})
        }
        return out, nil
    }

    // Allocate carves subnets for the requested host counts out of pool.
    func Allocate(pool Block, hosts []int) ([]Block, error) {
        bitsFor := make([]int, len(hosts))
        for i, h := range hosts {
            if h < 1 || uint64(h) > 1<<32-2 {
                return nil, ErrBadHosts
            }
            bits := 30
            for (Block{Bits: bits}).Usable() < uint64(h) {
                bits--
            }
            bitsFor[i] = bits
        }
        order := make([]int, len(hosts))
        for i := range order {
            order[i] = i
        }
        sort.SliceStable(order, func(a, b int) bool { return bitsFor[order[a]] < bitsFor[order[b]] })
        out := make([]Block, len(hosts))
        cursor := uint64(pool.First())
        end := uint64(pool.Last())
        for _, i := range order {
            size := uint64(1) << (32 - bitsFor[i])
            cursor = (cursor + size - 1) / size * size
            if cursor+size-1 > end {
                return nil, ErrNoSpace
            }
            out[i] = Block{uint32(cursor), bitsFor[i]}
            cursor += size
        }
        return out, nil
    }
'''))

VISIBLE = gosrc(dd(r'''
    package cidrplan

    import "testing"

    func TestParseAndPrint(t *testing.T) {
        b, err := ParseBlock("10.0.0.0/22")
        if err != nil || b.String() != "10.0.0.0/22" || b.Size() != 1024 {
            t.Fatalf("got %v %v", b, err)
        }
    }

    func TestAggregateSiblings(t *testing.T) {
        a, _ := ParseBlock("10.0.0.0/24")
        c, _ := ParseBlock("10.0.1.0/24")
        got := Aggregate([]Block{c, a})
        if len(got) != 1 || got[0].String() != "10.0.0.0/23" {
            t.Fatalf("got %v", got)
        }
    }
'''))

HIDDEN = gosrc(dd(r'''
    package cidrplan

    import (
        "errors"
        "reflect"
        "testing"
    )

    func blk(t *testing.T, s string) Block {
        t.Helper()
        b, err := ParseBlock(s)
        if err != nil {
            t.Fatalf("ParseBlock(%q): %v", s, err)
        }
        return b
    }

    func blocks(t *testing.T, ss ...string) []Block {
        t.Helper()
        out := make([]Block, 0, len(ss))
        for _, s := range ss {
            out = append(out, blk(t, s))
        }
        return out
    }

    func strs(bs []Block) []string {
        out := []string{}
        for _, b := range bs {
            out = append(out, b.String())
        }
        return out
    }

    func TestParseValid(t *testing.T) {
        cases := []struct {
            in   string
            addr uint32
            bits int
        }{
            {"0.0.0.0/0", 0, 0}, {"10.0.0.0/8", 10 << 24, 8}, {"10.0.0.0/22", 10 << 24, 22}, {"192.168.1.128/25", 192<<24 | 168<<16 | 1<<8 | 128, 25},
            {"255.255.255.255/32", 0xFFFFFFFF, 32}, {"255.255.255.254/31", 0xFFFFFFFE, 31}, {"1.2.3.4", 1<<24 | 2<<16 | 3<<8 | 4, 32},
            {"0.0.0.0", 0, 32}, {"172.16.0.0/12", 172<<24 | 16<<16, 12}, {"128.0.0.0/1", 1 << 31, 1}, {"0.0.0.0/32", 0, 32}, {"203.0.113.0/24", 203<<24 | 113<<8, 24},
        }
        for _, c := range cases {
            b, err := ParseBlock(c.in)
            if err != nil || b.Addr != c.addr || b.Bits != c.bits {
                t.Errorf("ParseBlock(%q) = %+v, %v; want %d/%d", c.in, b, err, c.addr, c.bits)
            }
        }
    }

    func TestParseErrors(t *testing.T) {
        syntax := []string{
            "", "10.0.0", "10.0.0.0.0", "10.0.0.256/24", "10.0.0.-1", "10.0.0.a/8", "10.0.0.00/8", "10.00.0.0/8", "010.0.0.0/8", "10..0.0/8", ".10.0.0.0",
            "10.0.0.0/", "10.0.0.0/08", "10.0.0.0/a", "10.0.0.0/-1", "10.0.0.0/+8", " 10.0.0.0/8", "10.0.0.0/8 ", "10.0.0.0/8/8", "10.0.0.0 /8", "10.0.0.0/ 8",
            "1.2.3.4.", "0x10.0.0.0/8", "10.0.0.0/8.0", "10,0,0,0/8", "1000.0.0.0/8", "256.0.0.0",
        }
        for _, s := range syntax {
            if b, err := ParseBlock(s); !errors.Is(err, ErrSyntax) {
                t.Errorf("ParseBlock(%q) = %+v, %v; want ErrSyntax", s, b, err)
            }
        }
        for _, s := range []string{"10.0.0.0/33", "10.0.0.0/64", "10.0.0.0/100", "1.1.1.1/33", "10.0.0.0/99", "10.0.0.0/4294967296", "10.0.0.0/999999999999", "10.0.0.0/99999999999999999999999"} {
            if _, err := ParseBlock(s); !errors.Is(err, ErrPrefix) {
                t.Errorf("ParseBlock(%q): %v; want ErrPrefix", s, err)
            }
        }
        for _, s := range []string{"10.0.0.1/24", "10.0.0.129/25", "10.0.1.0/23", "10.0.0.255/24", "0.0.0.1/0", "128.0.0.0/0", "10.0.0.1/31", "10.0.0.3/31", "10.0.0.4/28"} {
            if _, err := ParseBlock(s); !errors.Is(err, ErrHostBits) {
                t.Errorf("ParseBlock(%q): %v; want ErrHostBits", s, err)
            }
        }
        // precedence: syntax, then prefix range, then host bits
        if _, err := ParseBlock("10.0.0.1/33"); !errors.Is(err, ErrPrefix) {
            t.Errorf("prefix before host bits: %v", err)
        }
        if _, err := ParseBlock("10.0.0.300/33"); !errors.Is(err, ErrSyntax) {
            t.Errorf("syntax before prefix: %v", err)
        }
    }

    func TestStringRoundTrip(t *testing.T) {
        for _, s := range []string{"0.0.0.0/0", "10.0.0.0/8", "10.0.0.0/22", "192.168.1.128/25", "255.255.255.255/32", "1.2.3.4/32", "172.16.0.0/12"} {
            if got := blk(t, s).String(); got != s {
                t.Errorf("%q -> %q", s, got)
            }
        }
        if got := blk(t, "1.2.3.4").String(); got != "1.2.3.4/32" {
            t.Errorf("bare address: %q", got)
        }
    }

    func TestBlockQueries(t *testing.T) {
        b := blk(t, "10.0.4.0/22")
        if b.Size() != 1024 || b.First() != 10<<24|4<<8 || b.Last() != 10<<24|7<<8|255 {
            t.Errorf("size %d first %d last %d", b.Size(), b.First(), b.Last())
        }
        all := blk(t, "0.0.0.0/0")
        if all.Size() != 1<<32 || all.First() != 0 || all.Last() != 0xFFFFFFFF {
            t.Errorf("/0: %d %d %d", all.Size(), all.First(), all.Last())
        }
        one := blk(t, "9.9.9.9/32")
        if one.Size() != 1 || one.First() != one.Last() {
            t.Errorf("/32: %d", one.Size())
        }
        for addr, want := range map[uint32]bool{10<<24 | 4<<8: true, 10<<24 | 7<<8 | 255: true, 10<<24 | 4<<8 - 1: false, 10<<24 | 8<<8: false, 0: false, 10<<24 | 5<<8 | 77: true} {
            if b.Contains(addr) != want {
                t.Errorf("Contains(%d) = %v", addr, !want)
            }
        }
        if !all.Contains(0) || !all.Contains(0xFFFFFFFF) || !all.Contains(12345) {
            t.Errorf("/0 must contain everything")
        }
        if one.Contains(one.Addr-1) || one.Contains(one.Addr+1) || !one.Contains(one.Addr) {
            t.Errorf("/32 contains")
        }
    }

    func TestContainsAndOverlaps(t *testing.T) {
        cases := []struct {
            a, b             string
            aHasB, bHasA, ov bool
        }{
            {"10.0.0.0/8", "10.1.0.0/16", true, false, true},
            {"10.1.0.0/16", "10.0.0.0/8", false, true, true},
            {"10.0.0.0/24", "10.0.0.0/24", true, true, true},
            {"10.0.0.0/24", "10.0.1.0/24", false, false, false},
            {"10.0.0.0/25", "10.0.0.128/25", false, false, false},
            {"10.0.0.0/24", "10.0.0.255/32", true, false, true},
            {"0.0.0.0/0", "255.255.255.255/32", true, false, true},
            {"10.0.0.0/23", "10.0.2.0/24", false, false, false},
            {"10.0.0.0/23", "10.0.1.0/24", true, false, true},
        }
        for _, c := range cases {
            a, b := blk(t, c.a), blk(t, c.b)
            if a.ContainsBlock(b) != c.aHasB || b.ContainsBlock(a) != c.bHasA || a.Overlaps(b) != c.ov || b.Overlaps(a) != c.ov {
                t.Errorf("%s vs %s: has=%v rev=%v overlap=%v", c.a, c.b, a.ContainsBlock(b), b.ContainsBlock(a), a.Overlaps(b))
            }
        }
    }

    func TestUsable(t *testing.T) {
        cases := map[string]uint64{"10.0.0.0/24": 254, "10.0.0.0/30": 2, "10.0.0.0/31": 2, "10.0.0.1/32": 1, "10.0.0.0/29": 6, "0.0.0.0/0": 1<<32 - 2, "10.0.0.0/16": 65534, "10.0.0.0/8": 1<<24 - 2}
        for s, want := range cases {
            if got := blk(t, s).Usable(); got != want {
                t.Errorf("Usable(%s) = %d, want %d", s, got, want)
            }
        }
    }

    func TestAggregateTable(t *testing.T) {
        cases := []struct {
            in   []string
            want []string
        }{
            {[]string{"10.0.0.0/24", "10.0.1.0/24"}, []string{"10.0.0.0/23"}},
            {[]string{"10.0.0.0/24", "10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"}, []string{"10.0.0.0/22"}},
            {[]string{"10.0.0.0/24", "10.0.2.0/24"}, []string{"10.0.0.0/24", "10.0.2.0/24"}},
            {[]string{"10.0.0.0/16", "10.0.5.0/24", "10.0.200.0/24"}, []string{"10.0.0.0/16"}},
            {[]string{"192.168.1.0/25", "192.168.1.128/25", "192.168.0.0/24"}, []string{"192.168.0.0/23"}},
            {[]string{"0.0.0.0/1", "128.0.0.0/1"}, []string{"0.0.0.0/0"}},
            {[]string{"10.0.0.1/32", "10.0.0.0/32"}, []string{"10.0.0.0/31"}},
            {[]string{"10.0.0.0/32", "10.0.0.1/32", "10.0.0.2/32", "10.0.0.3/32"}, []string{"10.0.0.0/30"}},
            {[]string{"10.0.1.0/24", "10.0.0.0/24", "10.0.3.0/24", "10.0.2.0/24", "10.0.4.0/23"}, []string{"10.0.0.0/22", "10.0.4.0/23"}},
            {[]string{"10.0.0.0/24", "10.0.0.0/24"}, []string{"10.0.0.0/24"}},
            {[]string{"10.0.0.0/25", "10.0.0.128/26", "10.0.0.192/26"}, []string{"10.0.0.0/24"}},
            {[]string{"172.16.0.0/12", "172.31.0.0/16", "10.0.0.0/8", "11.0.0.0/8"}, []string{"10.0.0.0/7", "172.16.0.0/12"}},
            {[]string{"1.0.0.0/8", "3.0.0.0/8", "2.0.0.0/8", "0.0.0.0/8"}, []string{"0.0.0.0/6"}},
            {[]string{"255.255.255.254/31", "255.255.255.252/31"}, []string{"255.255.255.252/30"}},
            {[]string{"10.0.1.0/24", "10.0.2.0/24"}, []string{"10.0.1.0/24", "10.0.2.0/24"}},
            {[]string{"10.0.0.0/24", "10.0.0.128/25"}, []string{"10.0.0.0/24"}},
            {[]string{}, []string{}},
        }
        for _, c := range cases {
            got := strs(Aggregate(blocks(t, c.in...)))
            if !reflect.DeepEqual(got, c.want) {
                t.Errorf("Aggregate(%v) = %v, want %v", c.in, got, c.want)
            }
        }
    }

    func TestAggregateDoesNotTouchItsInput(t *testing.T) {
        in := blocks(t, "10.0.1.0/24", "10.0.0.0/24", "10.0.2.0/24")
        copyOf := append([]Block(nil), in...)
        Aggregate(in)
        if !reflect.DeepEqual(in, copyOf) {
            t.Errorf("input changed: %v", in)
        }
        if got := Aggregate(nil); len(got) != 0 {
            t.Errorf("nil input: %v", got)
        }
    }

    func TestAggregateCoversTheSameAddresses(t *testing.T) {
        seed := uint32(99)
        for round := 0; round < 40; round++ {
            var in []Block
            for i := 0; i < 12; i++ {
                seed = seed*1664525 + 1013904223
                bits := 24 + int(seed>>29)
                seed = seed*1664525 + 1013904223
                addr := (10<<24 | (seed>>16)&0x3FF) &^ (1<<(32-uint(bits)) - 1)
                in = append(in, Block{addr, bits})
            }
            out := Aggregate(in)
            for i, b := range out {
                if i > 0 && out[i-1].Overlaps(b) {
                    t.Fatalf("overlap in %v", out)
                }
                if i > 0 && out[i-1].Last()+1 == b.First() && out[i-1].Bits == b.Bits && out[i-1].Addr&(1<<(32-b.Bits)) == 0 {
                    t.Fatalf("siblings left unmerged in %v", out)
                }
            }
            for addr := uint32(10 << 24); addr < 10<<24+0x500; addr++ {
                inIn, inOut := false, false
                for _, b := range in {
                    inIn = inIn || b.Contains(addr)
                }
                for _, b := range out {
                    inOut = inOut || b.Contains(addr)
                }
                if inIn != inOut {
                    t.Fatalf("round %d: address %d covered=%v after aggregation=%v (in %v out %v)", round, addr, inIn, inOut, in, out)
                }
            }
        }
    }

    func TestSubtract(t *testing.T) {
        cases := []struct {
            a, b string
            want []string
        }{
            {"10.0.0.0/24", "10.0.0.64/26", []string{"10.0.0.0/26", "10.0.0.128/25"}},
            {"10.0.0.0/24", "10.0.0.0/25", []string{"10.0.0.128/25"}},
            {"10.0.0.0/24", "10.0.0.255/32", []string{"10.0.0.0/25", "10.0.0.128/26", "10.0.0.192/27", "10.0.0.224/28", "10.0.0.240/29", "10.0.0.248/30", "10.0.0.252/31", "10.0.0.254/32"}},
            {"10.0.0.0/24", "10.0.1.0/24", []string{"10.0.0.0/24"}},
            {"10.0.0.0/24", "10.0.0.0/24", []string{}},
            {"10.0.0.0/24", "10.0.0.0/16", []string{}},
            {"0.0.0.0/0", "10.0.0.0/8", []string{"0.0.0.0/5", "8.0.0.0/7", "11.0.0.0/8", "12.0.0.0/6", "16.0.0.0/4", "32.0.0.0/3", "64.0.0.0/2", "128.0.0.0/1"}},
            {"10.0.0.0/30", "10.0.0.1/32", []string{"10.0.0.0/32", "10.0.0.2/31"}},
        }
        for _, c := range cases {
            got := strs(Subtract(blk(t, c.a), blk(t, c.b)))
            if !reflect.DeepEqual(got, c.want) {
                t.Errorf("Subtract(%s, %s) = %v, want %v", c.a, c.b, got, c.want)
            }
        }
        deep := strs(Subtract(blk(t, "10.0.0.0/8"), blk(t, "10.255.255.255/32")))
        if len(deep) != 24 || deep[0] != "10.0.0.0/9" || deep[23] != "10.255.255.254/32" {
            t.Errorf("deep subtraction: %v", deep)
        }
    }

    func TestSplit(t *testing.T) {
        got, err := Split(blk(t, "10.0.0.0/22"), 24)
        if err != nil || !reflect.DeepEqual(strs(got), []string{"10.0.0.0/24", "10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"}) {
            t.Errorf("got %v, %v", strs(got), err)
        }
        got, err = Split(blk(t, "10.0.0.0/24"), 24)
        if err != nil || !reflect.DeepEqual(strs(got), []string{"10.0.0.0/24"}) {
            t.Errorf("same size: %v, %v", strs(got), err)
        }
        got, err = Split(blk(t, "255.255.255.0/24"), 26)
        if err != nil || !reflect.DeepEqual(strs(got), []string{"255.255.255.0/26", "255.255.255.64/26", "255.255.255.128/26", "255.255.255.192/26"}) {
            t.Errorf("top of the space: %v, %v", strs(got), err)
        }
        got, err = Split(blk(t, "10.0.0.0/30"), 32)
        if err != nil || len(got) != 4 || got[3].String() != "10.0.0.3/32" {
            t.Errorf("to /32: %v, %v", strs(got), err)
        }
        got, err = Split(blk(t, "10.0.0.0/8"), 24)
        if err != nil || len(got) != 65536 || got[65535].String() != "10.255.255.0/24" || got[256].String() != "10.1.0.0/24" {
            t.Errorf("65536 blocks: len %d err %v", len(got), err)
        }
    }

    func TestSplitErrors(t *testing.T) {
        if _, err := Split(blk(t, "10.0.0.0/24"), 23); !errors.Is(err, ErrPrefix) {
            t.Errorf("shorter prefix: %v", err)
        }
        if _, err := Split(blk(t, "10.0.0.0/24"), 33); !errors.Is(err, ErrPrefix) {
            t.Errorf("prefix 33: %v", err)
        }
        if _, err := Split(blk(t, "10.0.0.0/8"), 25); !errors.Is(err, ErrTooMany) {
            t.Errorf("131072 blocks: %v", err)
        }
        if _, err := Split(blk(t, "0.0.0.0/0"), 32); !errors.Is(err, ErrTooMany) {
            t.Errorf("/0 to /32: %v", err)
        }
        if _, err := Split(blk(t, "10.0.0.0/16"), 33); !errors.Is(err, ErrPrefix) {
            t.Errorf("prefix check comes before the count: %v", err)
        }
    }

    func TestAllocate(t *testing.T) {
        got, err := Allocate(blk(t, "10.0.0.0/24"), []int{50, 10, 100, 2, 25})
        want := []string{"10.0.0.128/26", "10.0.0.224/28", "10.0.0.0/25", "10.0.0.240/30", "10.0.0.192/27"}
        if err != nil || !reflect.DeepEqual(strs(got), want) {
            t.Errorf("got %v, %v; want %v", strs(got), err, want)
        }
    }

    func TestAllocateSizing(t *testing.T) {
        pool := blk(t, "10.0.0.0/8")
        cases := map[int]string{1: "10.0.0.0/30", 2: "10.0.0.0/30", 3: "10.0.0.0/29", 6: "10.0.0.0/29", 7: "10.0.0.0/28", 14: "10.0.0.0/28", 15: "10.0.0.0/27", 30: "10.0.0.0/27",
            31: "10.0.0.0/26", 62: "10.0.0.0/26", 63: "10.0.0.0/25", 126: "10.0.0.0/25", 127: "10.0.0.0/24", 254: "10.0.0.0/24", 255: "10.0.0.0/23", 1000: "10.0.0.0/22", 65534: "10.0.0.0/16", 65535: "10.0.0.0/15"}
        for h, want := range cases {
            got, err := Allocate(pool, []int{h})
            if err != nil || got[0].String() != want {
                t.Errorf("hosts %d: %v, %v; want %s", h, strs(got), err, want)
            }
        }
    }

    func TestAllocateOrderingAndAlignment(t *testing.T) {
        // small blocks are placed after the big ones so nothing is wasted on alignment
        got, err := Allocate(blk(t, "192.168.0.0/24"), []int{2, 2, 60, 2, 120})
        want := []string{"192.168.0.192/30", "192.168.0.196/30", "192.168.0.128/26", "192.168.0.200/30", "192.168.0.0/25"}
        if err != nil || !reflect.DeepEqual(strs(got), want) {
            t.Errorf("got %v, %v; want %v", strs(got), err, want)
        }
        // equal sizes keep request order
        got, _ = Allocate(blk(t, "10.0.0.0/24"), []int{10, 10, 10})
        if !reflect.DeepEqual(strs(got), []string{"10.0.0.0/28", "10.0.0.16/28", "10.0.0.32/28"}) {
            t.Errorf("equal sizes: %v", strs(got))
        }
        // a pool that does not start at zero in its low bits of a smaller block
        got, err = Allocate(blk(t, "10.1.2.64/26"), []int{30, 14})
        if err != nil || !reflect.DeepEqual(strs(got), []string{"10.1.2.64/27", "10.1.2.96/28"}) {
            t.Errorf("offset pool: %v, %v", strs(got), err)
        }
        // allocating into the very top of the address space
        got, err = Allocate(blk(t, "255.255.255.0/24"), []int{50, 100})
        if err != nil || !reflect.DeepEqual(strs(got), []string{"255.255.255.128/26", "255.255.255.0/25"}) {
            t.Errorf("top of the address space: %v, %v", strs(got), err)
        }
    }

    func TestAllocateExhaustion(t *testing.T) {
        pool := blk(t, "10.0.0.0/24")
        if _, err := Allocate(pool, []int{100, 100, 100}); !errors.Is(err, ErrNoSpace) {
            t.Errorf("3x /25 in a /24: %v", err)
        }
        if got, err := Allocate(pool, []int{100, 100}); err != nil || !reflect.DeepEqual(strs(got), []string{"10.0.0.0/25", "10.0.0.128/25"}) {
            t.Errorf("2x /25: %v, %v", strs(got), err)
        }
        if _, err := Allocate(pool, []int{254}); err != nil {
            t.Errorf("exactly the pool: %v", err)
        }
        if _, err := Allocate(pool, []int{255}); !errors.Is(err, ErrNoSpace) {
            t.Errorf("one more than the pool: %v", err)
        }
        if _, err := Allocate(pool, []int{126, 126, 2}); !errors.Is(err, ErrNoSpace) {
            t.Errorf("full pool plus a /30: %v", err)
        }
        if _, err := Allocate(blk(t, "255.255.255.252/30"), []int{2}); err != nil {
            t.Errorf("last /30 of the address space: %v", err)
        }
        if _, err := Allocate(blk(t, "255.255.255.252/30"), []int{2, 2}); !errors.Is(err, ErrNoSpace) {
            t.Errorf("past the end of the address space: %v", err)
        }
        if got, err := Allocate(pool, nil); err != nil || len(got) != 0 {
            t.Errorf("no requests: %v, %v", got, err)
        }
    }

    func TestAllocateBadHosts(t *testing.T) {
        pool := blk(t, "10.0.0.0/8")
        for _, h := range []int{0, -1, -100, 1<<32 - 1, 1 << 40} {
            if _, err := Allocate(pool, []int{5, h}); !errors.Is(err, ErrBadHosts) {
                t.Errorf("hosts %d: %v", h, err)
            }
        }
        if got, err := Allocate(blk(t, "0.0.0.0/0"), []int{1<<32 - 2}); err != nil || got[0].String() != "0.0.0.0/0" {
            t.Errorf("a /0 worth of hosts: %v, %v", strs(got), err)
        }
    }
'''))

LIB = Lib(
    name="cidrplan", lang="go", title="the cidrplan package",
    blurb="The network inventory tool plans address space with cidrplan: CIDR parsing, route aggregation, block subtraction and variable-length subnet allocation.",
    files={"go.mod": langs.go_mod("cidrplan"), "cidrplan.go": SRC, "README.md": README},
    visible_tests={"cidrplan_basic_test.go": VISIBLE},
    hidden_tests={"cidrplan_full_test.go": HIDDEN},
    mutate=["cidrplan.go"], difficulty=3, tags=["network", "cidr", "allocation"],
)

register_libs([LIB], n=8)
