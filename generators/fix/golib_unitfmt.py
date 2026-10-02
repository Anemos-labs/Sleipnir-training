"""Size and duration text (go): integer-only formatting and parsing with rounding and carry rules."""
from fx import Lib, dd, langs

from generators.fix._lang1 import gosrc, register_libs

README = dd('''
    # unitfmt

    Human-readable sizes and durations for the storage console. No floating point anywhere: results must be exact for
    the whole `int64` range.

    ## `FormatBytes(n int64) string`
    Binary units `B KiB MiB GiB TiB PiB` (powers of 1024). A negative size is formatted like its magnitude with a
    leading `-`.

    * Below 1024 the exact count and ` B`: `0 B`, `1023 B`.
    * Otherwise the largest unit with `n >= 1024^k` is used, and the value `n / 1024^k` is written with a number
      of decimals that depends on the *exact* value: below 10 two decimals, from 10 to below 100 one decimal, from 100
      on none. Rounding is to nearest, halves up.
    * If a value written without decimals rounds up to 1024, the next unit is used instead (computed from `n`, so
      `1048575` is `1.00 MiB`). There is nothing above `PiB`.

    Examples: `1536 -> 1.50 KiB`, `10240 -> 10.0 KiB`, `102399 -> 100.0 KiB`, `102400 -> 100 KiB`,
    `1024000 -> 1000 KiB`, `1048575 -> 1.00 MiB`.

    ## `ParseBytes(s string) (int64, error)`
    `<digits>[.<digits>][ws]<unit>` with optional surrounding whitespace. Units, matched case-insensitively:
    `B` or none (bytes), binary `KiB MiB GiB TiB PiB`, decimal `kB MB GB TB PB` (powers of 1000, so `1.5 kB` is 1500).
    At most 9 decimals. The result is rounded to a whole number of bytes, halves up (`0.5 B` is 1, `2.5 B` is 3).
    Errors: `ErrSyntax` for an empty string, no leading digit, a dangling or repeated `.`, more than 9 decimals, a sign,
    an unknown unit or trailing text; `ErrRange` when the value does not fit in an `int64`.

    ## `FormatDuration(ms int64, parts int) (string, error)`
    Units `d h m s ms` (86400000, 3600000, 60000, 1000, 1 milliseconds). `parts` must be 1..5, otherwise `ErrParts`.
    The first unit shown is the largest one that fits into the magnitude; at most `parts` consecutive units starting
    there take part, and the magnitude is rounded to the nearest multiple of the last of them (halves up). Then the rounded
    magnitude is written as a sequence of `<count><unit>` for every unit with a non-zero count, from `d` down (so a
    rounding carry can promote to a bigger unit, and zero components are left out). A negative value gets a leading `-`.
    Zero is `0s`.

    Examples: `3723000, 2 -> 1h2m`; `3599600, 2 -> 1h`; `90061001, 3 -> 1d1h1m`; `432000007, 5 -> 5d7ms`.

    ## `ParseDuration(s string) (int64, error)`
    An optional `-`, then one or more `<digits><unit>` groups with the units above, in strictly decreasing order (each at
    most once): `1d2h3m4s5ms`. Whitespace, fractions and a bare `0` are not accepted (`0s` is). `ErrSyntax` for anything
    malformed, wrong order or repeated units; `ErrRange` if the magnitude exceeds `math.MaxInt64` milliseconds.
''')

SRC = gosrc(dd(r'''
    // Package unitfmt formats and parses byte sizes and durations without floating point.
    package unitfmt

    import (
        "errors"
        "math"
        "math/bits"
        "strconv"
        "strings"
    )

    var (
        ErrSyntax = errors.New("unitfmt: syntax error")
        ErrRange  = errors.New("unitfmt: value out of range")
        ErrParts  = errors.New("unitfmt: parts must be between 1 and 5")
    )

    var iecNames = []string{"B", "KiB", "MiB", "GiB", "TiB", "PiB"}

    // scaled renders u in unit k (1 = KiB ...) and reports whether the rounded whole number reached 1024.
    func scaled(u uint64, k int) (string, bool) {
        d := uint64(1) << (10 * uint(k))
        q, r := u/d, u%d
        switch {
        case q >= 100:
            w := q
            if r*2 >= d {
                w++
            }
            return strconv.FormatUint(w, 10), w >= 1024
        case q >= 10:
            t := q*10 + (r*10+d/2)/d
            return strconv.FormatUint(t/10, 10) + "." + strconv.FormatUint(t%10, 10), false
        }
        h := q*100 + (r*100+d/2)/d
        frac := strconv.FormatUint(h%100, 10)
        if len(frac) < 2 {
            frac = "0" + frac
        }
        return strconv.FormatUint(h/100, 10) + "." + frac, false
    }

    // FormatBytes writes a size in binary units.
    func FormatBytes(n int64) string {
        sign := ""
        u := uint64(n)
        if n < 0 {
            sign = "-"
            u = -u
        }
        if u < 1024 {
            return sign + strconv.FormatUint(u, 10) + " B"
        }
        k := 1
        for k < len(iecNames)-1 && u >= uint64(1)<<(10*uint(k+1)) {
            k++
        }
        s, carry := scaled(u, k)
        if carry && k < len(iecNames)-1 {
            k++
            s, _ = scaled(u, k)
        }
        return sign + s + " " + iecNames[k]
    }

    var byteScale = map[string]uint64{
        "": 1, "b": 1,
        "kib": 1 << 10, "mib": 1 << 20, "gib": 1 << 30, "tib": 1 << 40, "pib": 1 << 50,
        "kb": 1000, "mb": 1000000, "gb": 1000000000, "tb": 1000000000000, "pb": 1000000000000000,
    }

    func isDigit(c byte) bool { return c >= '0' && c <= '9' }

    // ParseBytes reads a size such as "1.5 GiB" or "20MB".
    func ParseBytes(s string) (int64, error) {
        s = strings.TrimSpace(s)
        i := 0
        for i < len(s) && isDigit(s[i]) {
            i++
        }
        if i == 0 {
            return 0, ErrSyntax
        }
        whole, frac := s[:i], ""
        if i < len(s) && s[i] == '.' {
            j := i + 1
            for j < len(s) && isDigit(s[j]) {
                j++
            }
            if j == i+1 || j-i-1 > 9 {
                return 0, ErrSyntax
            }
            frac = s[i+1 : j]
            i = j
        }
        scale, ok := byteScale[strings.ToLower(strings.TrimSpace(s[i:]))]
        if !ok {
            return 0, ErrSyntax
        }
        ip, err := strconv.ParseUint(whole, 10, 64)
        if err != nil || ip > math.MaxInt64/scale {
            return 0, ErrRange
        }
        total := ip * scale
        if frac != "" {
            fv, _ := strconv.ParseUint(frac, 10, 64)
            den := uint64(1)
            for range frac {
                den *= 10
            }
            hi, lo := bits.Mul64(fv, scale)
            lo, carry := bits.Add64(lo, den/2, 0)
            hi += carry
            q, _ := bits.Div64(hi, lo, den)
            total += q
        }
        if total > math.MaxInt64 {
            return 0, ErrRange
        }
        return int64(total), nil
    }

    var durUnits = []struct {
        name string
        ms   uint64
    }{
        {"d", 86400000}, {"h", 3600000}, {"m", 60000}, {"s", 1000}, {"ms", 1},
    }

    // FormatDuration writes a duration using at most parts units.
    func FormatDuration(ms int64, parts int) (string, error) {
        if parts < 1 || parts > len(durUnits) {
            return "", ErrParts
        }
        u := uint64(ms)
        neg := ms < 0
        if neg {
            u = -u
        }
        if u == 0 {
            return "0s", nil
        }
        first := 0
        for first < len(durUnits)-1 && u < durUnits[first].ms {
            first++
        }
        last := min(first+parts-1, len(durUnits)-1)
        unit := durUnits[last].ms
        u = (u + unit/2) / unit * unit
        var b strings.Builder
        if neg {
            b.WriteByte('-')
        }
        for _, du := range durUnits {
            if q := u / du.ms; q > 0 {
                b.WriteString(strconv.FormatUint(q, 10))
                b.WriteString(du.name)
                u -= q * du.ms
            }
        }
        return b.String(), nil
    }

    // ParseDuration reads "1h30m" style durations into milliseconds.
    func ParseDuration(s string) (int64, error) {
        neg := false
        if strings.HasPrefix(s, "-") {
            neg = true
            s = s[1:]
        }
        if s == "" {
            return 0, ErrSyntax
        }
        var total uint64
        prev := -1
        for s != "" {
            i := 0
            for i < len(s) && isDigit(s[i]) {
                i++
            }
            if i == 0 {
                return 0, ErrSyntax
            }
            n, err := strconv.ParseUint(s[:i], 10, 64)
            if err != nil {
                return 0, ErrRange
            }
            s = s[i:]
            j := 0
            for j < len(s) && s[j] >= 'a' && s[j] <= 'z' {
                j++
            }
            idx := -1
            for k, du := range durUnits {
                if du.name == s[:j] {
                    idx = k
                }
            }
            if idx <= prev {
                return 0, ErrSyntax
            }
            prev = idx
            s = s[j:]
            unit := durUnits[idx].ms
            if n > math.MaxInt64/unit {
                return 0, ErrRange
            }
            total += n * unit
            if total > math.MaxInt64 {
                return 0, ErrRange
            }
        }
        if neg {
            return -int64(total), nil
        }
        return int64(total), nil
    }
'''))

VISIBLE = gosrc(dd(r'''
    package unitfmt

    import "testing"

    func TestFormatBytesBasics(t *testing.T) {
        if got := FormatBytes(1536); got != "1.50 KiB" {
            t.Fatalf("got %q", got)
        }
    }

    func TestParseDurationBasics(t *testing.T) {
        got, err := ParseDuration("1h30m")
        if err != nil || got != 5400000 {
            t.Fatalf("got %d, %v", got, err)
        }
    }
'''))

HIDDEN = gosrc(dd(r'''
    package unitfmt

    import (
        "errors"
        "math"
        "testing"
    )

    func TestFormatBytesTable(t *testing.T) {
        cases := []struct {
            n    int64
            want string
        }{
            {0, "0 B"}, {1, "1 B"}, {1023, "1023 B"}, {1024, "1.00 KiB"}, {1025, "1.00 KiB"}, {1536, "1.50 KiB"},
            {10239, "10.00 KiB"}, {10240, "10.0 KiB"}, {10250, "10.0 KiB"}, {102399, "100.0 KiB"}, {102400, "100 KiB"},
            {1048575, "1.00 MiB"}, {1048576, "1.00 MiB"}, {1024000, "1000 KiB"}, {1048152, "1.00 MiB"},
            {1 << 30, "1.00 GiB"}, {3 << 29, "1.50 GiB"}, {123456789, "118 MiB"}, {1000000000000, "931 GiB"},
            {1 << 50, "1.00 PiB"}, {1023 << 50, "1023 PiB"}, {9222246136947945529, "8191 PiB"}, {math.MaxInt64, "8192 PiB"},
            {-1, "-1 B"}, {-1024, "-1.00 KiB"}, {-1536, "-1.50 KiB"}, {math.MinInt64, "-8192 PiB"},
        }
        for _, c := range cases {
            if got := FormatBytes(c.n); got != c.want {
                t.Errorf("FormatBytes(%d) = %q, want %q", c.n, got, c.want)
            }
        }
    }

    func TestFormatBytesRoundingEdges(t *testing.T) {
        // 2.995 KiB is 3067 bytes: 2.9951 -> 3.00; 2.994 KiB (3066) -> 2.99
        if got := FormatBytes(3067); got != "3.00 KiB" {
            t.Errorf("3067: %q", got)
        }
        if got := FormatBytes(3066); got != "2.99 KiB" {
            t.Errorf("3066: %q", got)
        }
        // exactly x.5 rounds up with no decimals: 100.5 KiB = 102912
        if got := FormatBytes(102912); got != "101 KiB" {
            t.Errorf("102912: %q", got)
        }
        if got := FormatBytes(102911); got != "100 KiB" {
            t.Errorf("102911: %q", got)
        }
        // one decimal: 12.25 KiB = 12544 -> 12.3 (half up), 12.2 for 12543
        if got := FormatBytes(12544); got != "12.3 KiB" {
            t.Errorf("12544: %q", got)
        }
        if got := FormatBytes(12543); got != "12.2 KiB" {
            t.Errorf("12543: %q", got)
        }
        // two decimals: 1.005 KiB = 1029.12 B -> 1.01 ; 1029 -> 1.00 (1.0049)
        if got := FormatBytes(1029); got != "1.00 KiB" {
            t.Errorf("1029: %q", got)
        }
        if got := FormatBytes(1030); got != "1.01 KiB" {
            t.Errorf("1030: %q", got)
        }
        // the last decimal digit can be 9 (10.9 KiB = 11161 B) and the whole part can exceed 9
        if got := FormatBytes(11161); got != "10.9 KiB" {
            t.Errorf("11161: %q", got)
        }
        if got := FormatBytes(102376); got != "100.0 KiB" {
            t.Errorf("102376: %q", got)
        }
        // 1023.5 KiB rounds to 1024 -> carries to MiB; 1023.4 KiB stays
        if got := FormatBytes(1048063); got != "1023 KiB" {
            t.Errorf("1048063: %q", got)
        }
        if got := FormatBytes(1048064); got != "1.00 MiB" {
            t.Errorf("1048064: %q", got)
        }
        // carry across the top of each unit
        if got := FormatBytes(1<<40 - 1); got != "1.00 TiB" {
            t.Errorf("TiB carry: %q", got)
        }
        if got := FormatBytes(1<<50 - 1); got != "1.00 PiB" {
            t.Errorf("PiB carry: %q", got)
        }
        if got := FormatBytes(1<<30 - 1); got != "1.00 GiB" {
            t.Errorf("GiB carry: %q", got)
        }
    }

    func TestParseBytesTable(t *testing.T) {
        cases := []struct {
            in   string
            want int64
        }{
            {"0", 0}, {"512", 512}, {"512B", 512}, {"512 b", 512}, {"1KiB", 1024}, {"1 KiB", 1024}, {"1 kib", 1024}, {"1 KIB", 1024},
            {"  1\tKiB  ", 1024}, {"1.5 KiB", 1536}, {"1.5 kB", 1500}, {"1.5kb", 1500}, {"5 MB", 5000000}, {"5 MiB", 5242880},
            {"2 GB", 2000000000}, {"2 GiB", 2147483648}, {"3 TB", 3000000000000}, {"3 TiB", 3298534883328},
            {"1 PB", 1000000000000000}, {"1 PiB", 1125899906842624}, {"0.5 B", 1}, {"2.5 B", 3}, {"0.4 B", 0}, {"0.49 B", 0},
            {"1.000000001 KiB", 1024}, {"0.999999999 PiB", 1125899905716724}, {"8191.999999999 PiB", 9223372036853649908},
            {"9223372036854775807", math.MaxInt64}, {"8191 PiB", 9222246136947933184}, {"0.1 PB", 100000000000000},
            {"123.456 MB", 123456000}, {"3.333333333 GiB", 3579139413}, {"0.000000005 KiB", 0}, {"0.5 KiB", 512}, {"7.25 kB", 7250},
            {"007 B", 7}, {"1.50 KiB", 1536},
        }
        for _, c := range cases {
            got, err := ParseBytes(c.in)
            if err != nil || got != c.want {
                t.Errorf("ParseBytes(%q) = %d, %v; want %d", c.in, got, err, c.want)
            }
        }
    }

    func TestParseBytesSyntaxErrors(t *testing.T) {
        bad := []string{
            "", " ", "KiB", "-5", "-5 KiB", "+5", "1..5", "1.", ".5", "1.2.3", "5 furlongs", "5 K", "5 KiB x", "1 000", "1e3",
            "0x10", "5 B B", "1.0000000001", "1.0000000001 KiB", "5 ki", "5 Mi", "5 m", "5 EiB", "5,5 KiB", "5 K iB",
        }
        for _, s := range bad {
            if got, err := ParseBytes(s); !errors.Is(err, ErrSyntax) {
                t.Errorf("ParseBytes(%q) = %d, %v; want ErrSyntax", s, got, err)
            }
        }
    }

    func TestParseBytesRange(t *testing.T) {
        bad := []string{
            "9223372036854775808", "99999999999999999999", "8192 PiB", "9000 PiB", "9223372036854775807.5", "10000 PB",
            "9223373 TB", "8589934592 GiB", "16384 PiB", "16385 PiB", "18446744073709551616", "18446744073709551615 B",
        }
        for _, s := range bad {
            if got, err := ParseBytes(s); !errors.Is(err, ErrRange) {
                t.Errorf("ParseBytes(%q) = %d, %v; want ErrRange", s, got, err)
            }
        }
        if got, err := ParseBytes("9223372036854 MB"); err != nil || got != 9223372036854000000 {
            t.Errorf("large MB: %d %v", got, err)
        }
        if got, err := ParseBytes("9223372036854.775807 MB"); err != nil || got != 9223372036854775807 {
            t.Errorf("exact max: %d %v", got, err)
        }
        if _, err := ParseBytes("9223372036854.775808 MB"); !errors.Is(err, ErrRange) {
            t.Errorf("one past max: %v", err)
        }
    }

    func TestFormatParseBytesAgree(t *testing.T) {
        for _, n := range []int64{0, 5, 1023, 1024, 4096, 1 << 20, 3 << 30, 7 << 40, 5 << 50, 1536, 1 << 40} {
            s := FormatBytes(n)
            back, err := ParseBytes(s)
            if err != nil {
                t.Errorf("%q: %v", s, err)
                continue
            }
            // formatting is lossy only when digits are dropped; these inputs are exact
            if back != n {
                t.Errorf("%d -> %q -> %d", n, s, back)
            }
        }
    }

    func TestFormatDurationTable(t *testing.T) {
        cases := []struct {
            ms    int64
            parts int
            want  string
        }{
            {0, 1, "0s"}, {0, 5, "0s"}, {1, 1, "1ms"}, {999, 2, "999ms"}, {1000, 1, "1s"}, {1499, 1, "1s"}, {1500, 1, "2s"},
            {61000, 1, "1m"}, {61000, 2, "1m1s"}, {3723000, 2, "1h2m"}, {3723000, 3, "1h2m3s"}, {3723004, 5, "1h2m3s4ms"},
            {3599600, 2, "1h"}, {3599500, 2, "1h"}, {3599999, 3, "59m59s999ms"}, {86399999, 2, "1d"}, {86400000, 3, "1d"},
            {90061001, 5, "1d1h1m1s1ms"}, {90061001, 4, "1d1h1m1s"}, {90061001, 3, "1d1h1m"}, {90061001, 2, "1d1h"},
            {90061001, 1, "1d"}, {432000007, 5, "5d7ms"}, {432000007, 2, "5d"}, {-1500, 1, "-2s"}, {-3723000, 2, "-1h2m"},
            {1770000, 1, "30m"}, {1769999, 1, "29m"}, {172799000, 2, "2d"}, {86371000, 2, "1d"},
            {math.MaxInt64, 5, "106751991167d7h12m55s807ms"}, {math.MaxInt64, 2, "106751991167d7h"},
        }
        for _, c := range cases {
            got, err := FormatDuration(c.ms, c.parts)
            if err != nil || got != c.want {
                t.Errorf("FormatDuration(%d, %d) = %q, %v; want %q", c.ms, c.parts, got, err, c.want)
            }
        }
    }

    func TestFormatDurationPartsAndFirstUnit(t *testing.T) {
        // 2 parts start at the largest unit that fits, not at "d"
        if got, _ := FormatDuration(125000, 2); got != "2m5s" {
            t.Errorf("got %q", got)
        }
        if got, _ := FormatDuration(125300, 2); got != "2m5s" {
            t.Errorf("got %q", got)
        }
        if got, _ := FormatDuration(125600, 3); got != "2m5s600ms" {
            t.Errorf("got %q", got)
        }
        if got, _ := FormatDuration(59999, 1); got != "1m" {
            t.Errorf("59999 ms: %q", got)
        }
        if got, _ := FormatDuration(59999, 2); got != "59s999ms" {
            t.Errorf("59999 ms in 2 parts: %q", got)
        }
        if got, _ := FormatDuration(3600000+59000, 1); got != "1h" {
            t.Errorf("got %q", got)
        }
        if got, _ := FormatDuration(3600000+1800000, 1); got != "2h" {
            t.Errorf("half rounds up: %q", got)
        }
        if got, _ := FormatDuration(3600000+1799999, 1); got != "1h" {
            t.Errorf("just under half: %q", got)
        }
        if got, _ := FormatDuration(1, 5); got != "1ms" {
            t.Errorf("got %q", got)
        }
        // zero components are skipped in the middle
        if got, _ := FormatDuration(3600000+5000, 4); got != "1h5s" {
            t.Errorf("got %q", got)
        }
        if got, _ := FormatDuration(86400000+60000, 5); got != "1d1m" {
            t.Errorf("got %q", got)
        }
        // below one second the first unit is the millisecond, however few parts are asked for
        for _, c := range []struct {
            ms    int64
            parts int
            want  string
        }{{500, 1, "500ms"}, {7, 1, "7ms"}, {999, 1, "999ms"}, {999, 2, "999ms"}, {1499, 1, "1s"}, {1500, 1, "2s"}, {-500, 1, "-500ms"}} {
            if got, err := FormatDuration(c.ms, c.parts); err != nil || got != c.want {
                t.Errorf("FormatDuration(%d, %d) = %q, %v; want %q", c.ms, c.parts, got, err, c.want)
            }
        }
    }

    func TestFormatDurationBadParts(t *testing.T) {
        for _, p := range []int{0, -1, 6, 100} {
            if got, err := FormatDuration(1000, p); !errors.Is(err, ErrParts) || got != "" {
                t.Errorf("parts %d: %q %v", p, got, err)
            }
        }
        for _, p := range []int{1, 5} {
            if _, err := FormatDuration(1000, p); err != nil {
                t.Errorf("parts %d: %v", p, err)
            }
        }
    }

    func TestParseDurationTable(t *testing.T) {
        cases := []struct {
            in   string
            want int64
        }{
            {"1d2h3m4s5ms", 93784005}, {"90m", 5400000}, {"1h30m", 5400000}, {"2h", 7200000}, {"0s", 0}, {"-0s", 0},
            {"-1h", -3600000}, {"1s1ms", 1001}, {"5ms", 5}, {"5m", 300000}, {"007s", 7000}, {"1d", 86400000}, {"3m4ms", 180004},
            {"1h1ms", 3600001}, {"-1d1ms", -86400001}, {"106751991167d7h12m55s807ms", math.MaxInt64}, {"9223372036854775807ms", math.MaxInt64},
        }
        for _, c := range cases {
            got, err := ParseDuration(c.in)
            if err != nil || got != c.want {
                t.Errorf("ParseDuration(%q) = %d, %v; want %d", c.in, got, err, c.want)
            }
        }
    }

    func TestParseDurationSyntax(t *testing.T) {
        bad := []string{
            "", "-", "h", "10", "0", "1h1h", "1m1h", "1s1m", "1ms1s", "5mm", "1.5h", "1d ", " 1d", "1 d", "1h 30m", "+1h", "--1h",
            "1x", "1H", "1hh", "1d2d", "1w", "1h30", "m5", "1h-30m", "1sec", "1d1h1m1s1ms1ms",
        }
        for _, s := range bad {
            if got, err := ParseDuration(s); !errors.Is(err, ErrSyntax) {
                t.Errorf("ParseDuration(%q) = %d, %v; want ErrSyntax", s, got, err)
            }
        }
    }

    func TestParseDurationRange(t *testing.T) {
        bad := []string{
            "106751991167d7h12m55s808ms", "9223372036854775808ms", "999999999999999d", "99999999999999999999ms", "-9223372036854775808ms",
            "9223372036854776s", "106751991168d", "106751991167d8h", "213503982335d", "5124095576031h",
        }
        for _, s := range bad {
            if got, err := ParseDuration(s); !errors.Is(err, ErrRange) {
                t.Errorf("ParseDuration(%q) = %d, %v; want ErrRange", s, got, err)
            }
        }
    }

    func TestDurationRoundTrip(t *testing.T) {
        x := uint64(88172645463325252)
        for i := 0; i < 400; i++ {
            x ^= x << 13
            x ^= x >> 7
            x ^= x << 17
            ms := int64(x>>(x%40+20)) * int64(1-2*int(x&1))
            s, err := FormatDuration(ms, 5)
            if err != nil {
                t.Fatal(err)
            }
            back, err := ParseDuration(s)
            if err != nil || back != ms {
                t.Fatalf("%d -> %q -> %d, %v", ms, s, back, err)
            }
        }
    }
'''))

LIB = Lib(
    name="unitfmt", lang="go", title="the unitfmt package",
    blurb="The storage console prints and accepts sizes and durations through unitfmt, which does all of its rounding with integers.",
    files={"go.mod": langs.go_mod("unitfmt"), "unitfmt.go": SRC, "README.md": README},
    visible_tests={"unitfmt_basic_test.go": VISIBLE},
    hidden_tests={"unitfmt_full_test.go": HIDDEN},
    mutate=["unitfmt.go"], difficulty=3, tags=["formatting", "parsing", "rounding"],
)

register_libs([LIB], n=8)
