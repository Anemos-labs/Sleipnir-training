"""Fixed-point money (go): minor units, a currency exponent table, rounding modes, largest-remainder allocation."""
from fx import Lib, dd, langs

from generators.fix._lang1 import gosrc, register_libs

README = dd('''
    # minorcash

    Money for the invoicing service, stored as an `int64` count of *minor units* (cents, yen, fils) next to its currency
    code. There is no floating point anywhere.

    ```go
    type Money struct { Minor int64; Cur string }
    ```
    Currency exponents (digits after the decimal point): `USD EUR GBP CHF` 2, `JPY KRW ISK` 0, `BHD KWD` 3, `CLF` 4. Any
    other code is `ErrCurrency`.

    ## Text
    * `(Money) String() string`: `CODE amount`, e.g. `USD 12.34`, `JPY 500`, `BHD 1.050`. Thousands are grouped with `,` in the
      integer part (`USD 1,234,567.80`), a negative amount has the `-` right before the digits (`USD -0.05`). Exactly
      `exponent` decimals are printed, none (and no point) for exponent 0.
    * `Parse(s string) (Money, error)`: two tokens separated by one space: the code (three upper-case letters) and the
      amount, in either order (`USD 12.34` or `12.34 USD`). The amount is an optional `-`, an integer part, and optionally
      `.` followed by 1 to `exponent` digits; fewer decimals than the exponent are fine (`USD 12.5` is 1250 minor units).
      The integer part is either plain digits or digits grouped by commas in the canonical way (1 to 3 digits, then groups
      of exactly 3: `1,234,567`). Errors: `ErrSyntax` for the wrong number of tokens, both or neither token being a
      code, a malformed amount (empty, a lone `-`, a trailing `.`, a bad comma grouping, a stray character);
      `ErrCurrency` for an unknown code (checked after the shape of the tokens); `ErrPrecision` for more decimals than the
      currency has (nothing is rounded silently); `ErrRange` if the value does not fit an `int64`.

    ## Arithmetic
    * `Add(a, b Money) (Money, error)`: `ErrMismatch` for different currencies, `ErrRange` on `int64` overflow.
    * `Mul(m Money, num, den int64, mode Rounding) (Money, error)`: `m * num / den`, rounded to a whole minor unit with
      `mode`. `den == 0` is `ErrDivZero`; a negative `den` is allowed (the sign moves to `num`). Overflow of the
      intermediate product (or of negating `math.MinInt64`) is `ErrRange`.
    * `Rounding`: `Floor` (toward minus infinity), `Ceil` (toward plus infinity), `HalfAway` (to nearest, ties away from zero),
      `HalfEven` (to nearest, ties to the even neighbour). Examples for 2.5, -2.5, 3.5, 2.4: Floor 2, -3, 3, 2; Ceil 3,
      -2, 4, 3; HalfAway 3, -3, 4, 2; HalfEven 2, -2, 4, 2.
    * `Convert(m Money, to string, num, den int64, mode Rounding) (Money, error)`: `num/den` is the price of one *major*
      unit of `m.Cur` in major units of `to` (so `USD`->`JPY` at `150/1` makes 1.00 USD = 150 JPY). The result is in the minor
      units of `to`. Same errors as `Mul`, plus `ErrCurrency` for an unknown target.

    ## `Allocate(m Money, weights []int64) ([]Money, error)`
    Splits `m` in proportion to `weights` so the parts add up to exactly `m`: each part is first the integer share
    `|m| * w / sum(w)` (rounded down, computed without overflow), then the units left over are handed out one per part, to the
    parts with the largest fractional remainder, ties going to the lower index. Negative amounts are split by magnitude and the
    parts get the sign of `m`. Zero weights get nothing unless leftovers fall to them. `ErrBadWeights` for an empty list, a
    negative weight, or a total weight of 0 (or one that overflows an `int64`).
''')

SRC = gosrc(dd(r'''
    // Package minorcash is fixed-point money in minor units.
    package minorcash

    import (
        "errors"
        "math"
        "math/bits"
        "sort"
        "strconv"
        "strings"
    )

    var (
        ErrSyntax     = errors.New("minorcash: syntax error")
        ErrCurrency   = errors.New("minorcash: unknown currency")
        ErrPrecision  = errors.New("minorcash: too many decimals for the currency")
        ErrRange      = errors.New("minorcash: amount out of range")
        ErrMismatch   = errors.New("minorcash: currency mismatch")
        ErrDivZero    = errors.New("minorcash: division by zero")
        ErrBadWeights = errors.New("minorcash: invalid weights")
    )

    var exponents = map[string]int{
        "USD": 2, "EUR": 2, "GBP": 2, "CHF": 2, "JPY": 0, "KRW": 0, "ISK": 0, "BHD": 3, "KWD": 3, "CLF": 4,
    }

    // Money is an amount of minor units of one currency.
    type Money struct {
        Minor int64
        Cur   string
    }

    func pow10(n int) int64 {
        p := int64(1)
        for i := 0; i < n; i++ {
            p *= 10
        }
        return p
    }

    // String formats the amount with grouped thousands.
    func (m Money) String() string {
        exp := exponents[m.Cur]
        u := uint64(m.Minor)
        neg := m.Minor < 0
        if neg {
            u = -u
        }
        digits := strconv.FormatUint(u, 10)
        for len(digits) < exp+1 {
            digits = "0" + digits
        }
        whole, frac := digits[:len(digits)-exp], digits[len(digits)-exp:]
        var b strings.Builder
        for i, c := range whole {
            if i > 0 && (len(whole)-i)%3 == 0 {
                b.WriteByte(',')
            }
            b.WriteRune(c)
        }
        out := b.String()
        if exp > 0 {
            out += "." + frac
        }
        if neg {
            out = "-" + out
        }
        return m.Cur + " " + out
    }

    func isCode(s string) bool {
        if len(s) != 3 {
            return false
        }
        for i := 0; i < 3; i++ {
            if s[i] < 'A' || s[i] > 'Z' {
                return false
            }
        }
        return true
    }

    func allDigits(s string) bool {
        if s == "" {
            return false
        }
        for i := 0; i < len(s); i++ {
            if s[i] < '0' || s[i] > '9' {
                return false
            }
        }
        return true
    }

    // groupedInt reads digits, optionally comma-grouped in threes.
    func groupedInt(s string) (string, bool) {
        if !strings.Contains(s, ",") {
            return s, allDigits(s)
        }
        parts := strings.Split(s, ",")
        if len(parts[0]) < 1 || len(parts[0]) > 3 {
            return "", false
        }
        for _, p := range parts[1:] {
            if len(p) != 3 {
                return "", false
            }
        }
        joined := strings.Join(parts, "")
        return joined, allDigits(joined)
    }

    // Parse reads "USD 12.34" or "12.34 USD".
    func Parse(s string) (Money, error) {
        toks := strings.Split(s, " ")
        if len(toks) != 2 || isCode(toks[0]) == isCode(toks[1]) {
            return Money{}, ErrSyntax
        }
        code, amt := toks[0], toks[1]
        if !isCode(code) {
            code, amt = amt, code
        }
        neg := strings.HasPrefix(amt, "-")
        amt = strings.TrimPrefix(amt, "-")
        whole, frac := amt, ""
        if i := strings.IndexByte(amt, '.'); i >= 0 {
            whole, frac = amt[:i], amt[i+1:]
            if frac == "" || !allDigits(frac) {
                return Money{}, ErrSyntax
            }
        }
        whole, ok := groupedInt(whole)
        if !ok {
            return Money{}, ErrSyntax
        }
        exp, known := exponents[code]
        if !known {
            return Money{}, ErrCurrency
        }
        if len(frac) > exp {
            return Money{}, ErrPrecision
        }
        frac += strings.Repeat("0", exp-len(frac))
        v, err := strconv.ParseUint(whole+frac, 10, 64)
        if err != nil || v > uint64(math.MaxInt64)+1 || (v == uint64(math.MaxInt64)+1 && !neg) {
            return Money{}, ErrRange
        }
        minor := int64(v)
        if neg {
            minor = int64(-v)
        }
        return Money{minor, code}, nil
    }

    // Add sums two amounts of the same currency.
    func Add(a, b Money) (Money, error) {
        if a.Cur != b.Cur {
            return Money{}, ErrMismatch
        }
        s := a.Minor + b.Minor
        if (b.Minor > 0 && s < a.Minor) || (b.Minor < 0 && s > a.Minor) {
            return Money{}, ErrRange
        }
        return Money{s, a.Cur}, nil
    }

    // Rounding selects how fractions of a minor unit are resolved.
    type Rounding int

    const (
        Floor Rounding = iota
        Ceil
        HalfAway
        HalfEven
    )

    func divRound(p, d int64, mode Rounding) int64 {
        q, r := p/d, p%d
        if r == 0 {
            return q
        }
        floor := q
        if r < 0 {
            floor = q - 1
        }
        switch mode {
        case Floor:
            return floor
        case Ceil:
            return floor + 1
        }
        rem := p - floor*d
        switch {
        case rem < d-rem:
            return floor
        case rem > d-rem:
            return floor + 1
        }
        if mode == HalfAway {
            if p < 0 {
                return floor
            }
            return floor + 1
        }
        if floor%2 == 0 {
            return floor
        }
        return floor + 1
    }

    func mulCheck(a, b int64) (int64, bool) {
        if a == 0 || b == 0 {
            return 0, true
        }
        p := a * b
        if p/b != a || (a == -1 && b == math.MinInt64) || (b == -1 && a == math.MinInt64) {
            return 0, false
        }
        return p, true
    }

    func scale(minor, num, den int64, mode Rounding) (int64, error) {
        if den == 0 {
            return 0, ErrDivZero
        }
        if den < 0 {
            if num == math.MinInt64 || den == math.MinInt64 {
                return 0, ErrRange
            }
            num, den = -num, -den
        }
        p, ok := mulCheck(minor, num)
        if !ok {
            return 0, ErrRange
        }
        return divRound(p, den, mode), nil
    }

    // Mul multiplies by the fraction num/den.
    func Mul(m Money, num, den int64, mode Rounding) (Money, error) {
        v, err := scale(m.Minor, num, den, mode)
        if err != nil {
            return Money{}, err
        }
        return Money{v, m.Cur}, nil
    }

    // Convert changes currency at the price num/den (major unit for major unit).
    func Convert(m Money, to string, num, den int64, mode Rounding) (Money, error) {
        toExp, ok := exponents[to]
        if !ok {
            return Money{}, ErrCurrency
        }
        fromExp := exponents[m.Cur]
        if den < 0 {
            if num == math.MinInt64 || den == math.MinInt64 {
                return Money{}, ErrRange
            }
            num, den = -num, -den
        }
        var ok2 bool
        if toExp >= fromExp {
            num, ok2 = mulCheck(num, pow10(toExp-fromExp))
        } else {
            den, ok2 = mulCheck(den, pow10(fromExp-toExp))
        }
        if !ok2 {
            return Money{}, ErrRange
        }
        v, err := scale(m.Minor, num, den, mode)
        if err != nil {
            return Money{}, err
        }
        return Money{v, to}, nil
    }

    // Allocate splits m by weights with the largest remainder method.
    func Allocate(m Money, weights []int64) ([]Money, error) {
        if len(weights) == 0 {
            return nil, ErrBadWeights
        }
        var total uint64
        for _, w := range weights {
            if w < 0 {
                return nil, ErrBadWeights
            }
            total += uint64(w)
            if total > math.MaxInt64 {
                return nil, ErrBadWeights
            }
        }
        if total == 0 {
            return nil, ErrBadWeights
        }
        mag := uint64(m.Minor)
        neg := m.Minor < 0
        if neg {
            mag = -mag
        }
        shares := make([]uint64, len(weights))
        rems := make([]uint64, len(weights))
        var given uint64
        for i, w := range weights {
            hi, lo := bits.Mul64(mag, uint64(w))
            shares[i], rems[i] = bits.Div64(hi, lo, total)
            given += shares[i]
        }
        order := make([]int, len(weights))
        for i := range order {
            order[i] = i
        }
        sort.SliceStable(order, func(a, b int) bool { return rems[order[a]] > rems[order[b]] })
        for k := uint64(0); k < mag-given; k++ {
            shares[order[k]]++
        }
        out := make([]Money, len(weights))
        for i, s := range shares {
            v := int64(s)
            if neg {
                v = -v
            }
            out[i] = Money{v, m.Cur}
        }
        return out, nil
    }
'''))

VISIBLE = gosrc(dd(r'''
    package minorcash

    import "testing"

    func TestFormatBasics(t *testing.T) {
        if got := (Money{1234, "USD"}).String(); got != "USD 12.34" {
            t.Fatalf("got %q", got)
        }
    }

    func TestParseBasics(t *testing.T) {
        m, err := Parse("EUR 5.5")
        if err != nil || m != (Money{550, "EUR"}) {
            t.Fatalf("got %+v, %v", m, err)
        }
    }
'''))

# expected values for the hidden suite were computed with an independent python model of the README
HIDDEN = gosrc(dd(r'''
    package minorcash

    import (
        "errors"
        "math"
        "reflect"
        "testing"
    )

    func TestStringTable(t *testing.T) {
        cases := []struct {
            m    Money
            want string
        }{
            {Money{1234, "USD"}, "USD 12.34"}, {Money{0, "USD"}, "USD 0.00"}, {Money{5, "USD"}, "USD 0.05"}, {Money{-5, "USD"}, "USD -0.05"},
            {Money{100, "USD"}, "USD 1.00"}, {Money{123456780, "USD"}, "USD 1,234,567.80"}, {Money{99999, "USD"}, "USD 999.99"},
            {Money{100000, "USD"}, "USD 1,000.00"}, {Money{-100000, "EUR"}, "EUR -1,000.00"}, {Money{500, "JPY"}, "JPY 500"},
            {Money{0, "JPY"}, "JPY 0"}, {Money{-1234567, "JPY"}, "JPY -1,234,567"}, {Money{1050, "BHD"}, "BHD 1.050"},
            {Money{7, "BHD"}, "BHD 0.007"}, {Money{12, "CLF"}, "CLF 0.0012"}, {Money{123456789, "CLF"}, "CLF 12,345.6789"},
            {Money{math.MaxInt64, "USD"}, "USD 92,233,720,368,547,758.07"}, {Money{math.MinInt64, "USD"}, "USD -92,233,720,368,547,758.08"},
            {Money{999, "JPY"}, "JPY 999"}, {Money{1000, "JPY"}, "JPY 1,000"}, {Money{12345, "KWD"}, "KWD 12.345"},
            {Money{100, "CHF"}, "CHF 1.00"}, {Money{-1, "ISK"}, "ISK -1"}, {Money{10, "GBP"}, "GBP 0.10"},
        }
        for _, c := range cases {
            if got := c.m.String(); got != c.want {
                t.Errorf("%+v.String() = %q, want %q", c.m, got, c.want)
            }
        }
    }

    func TestParseTable(t *testing.T) {
        cases := []struct {
            in   string
            want Money
        }{
            {"USD 12.34", Money{1234, "USD"}}, {"12.34 USD", Money{1234, "USD"}}, {"USD 12.5", Money{1250, "USD"}}, {"USD 12", Money{1200, "USD"}},
            {"USD 0.05", Money{5, "USD"}}, {"USD -0.05", Money{-5, "USD"}}, {"-0.05 USD", Money{-5, "USD"}}, {"USD 1,234,567.80", Money{123456780, "USD"}},
            {"USD 1,000", Money{100000, "USD"}}, {"USD 999,999.99", Money{99999999, "USD"}}, {"USD 007.5", Money{750, "USD"}},
            {"JPY 500", Money{500, "JPY"}}, {"500 JPY", Money{500, "JPY"}}, {"JPY -1,234,567", Money{-1234567, "JPY"}}, {"BHD 1.05", Money{1050, "BHD"}},
            {"BHD 0.007", Money{7, "BHD"}}, {"CLF 12,345.6789", Money{123456789, "CLF"}}, {"USD -0", Money{0, "USD"}}, {"USD 0.0", Money{0, "USD"}},
            {"EUR 0", Money{0, "EUR"}}, {"USD 92,233,720,368,547,758.07", Money{math.MaxInt64, "USD"}},
            {"USD -92,233,720,368,547,758.08", Money{math.MinInt64, "USD"}}, {"KWD 12.3", Money{12300, "KWD"}}, {"ISK 12", Money{12, "ISK"}},
            {"USD 123,456", Money{12345600, "USD"}},
        }
        for _, c := range cases {
            got, err := Parse(c.in)
            if err != nil || got != c.want {
                t.Errorf("Parse(%q) = %+v, %v; want %+v", c.in, got, err, c.want)
            }
        }
    }

    func TestParseSyntaxErrors(t *testing.T) {
        bad := []string{
            "", "USD", "12.34", "USD 12.34 extra", " USD 12.34", "USD  12.34", "USD 12.34 ", "USD USD", "12 34", "usd 12.34", "US 12.34",
            "USDX 12.34", "USD -", "USD ", "USD .5", "USD 5.", "USD 1,23", "USD 1,2345", "USD ,123", "USD 1234,567", "USD 12,34,567", "USD 1,,000",
            "USD 1.000,5", "USD 1_000", "USD +5", "USD 5e2", "USD --5", "USD 5-", "USD 1.2.3", "USD 0x10", "USD 1,000.", "USD 1,000.a",
            "USD ٣", "USD 12.3a", "USD - 5", "1,00 USD", "USD 1 000",
        }
        for _, s := range bad {
            if got, err := Parse(s); !errors.Is(err, ErrSyntax) {
                t.Errorf("Parse(%q) = %+v, %v; want ErrSyntax", s, got, err)
            }
        }
    }

    func TestParseOtherErrors(t *testing.T) {
        cases := []struct {
            in   string
            want error
        }{
            {"XXX 12.34", ErrCurrency}, {"12.34 ABC", ErrCurrency}, {"ZZZ -5", ErrCurrency}, {"XXX 1.234", ErrCurrency},
            {"USD 12.345", ErrPrecision}, {"JPY 5.0", ErrPrecision}, {"JPY 0.5", ErrPrecision}, {"BHD 1.2345", ErrPrecision}, {"EUR 1.001", ErrPrecision},
            {"USD 92,233,720,368,547,758.08", ErrRange}, {"USD -92,233,720,368,547,758.09", ErrRange}, {"JPY 9223372036854775808", ErrRange},
            {"JPY -9223372036854775809", ErrRange}, {"USD 99999999999999999999", ErrRange}, {"CLF 922,337,203,685,477.5808", ErrRange},
        }
        for _, c := range cases {
            if got, err := Parse(c.in); !errors.Is(err, c.want) {
                t.Errorf("Parse(%q) = %+v, %v; want %v", c.in, got, err, c.want)
            }
        }
        if m, err := Parse("JPY 9223372036854775807"); err != nil || m.Minor != math.MaxInt64 {
            t.Errorf("max yen: %+v %v", m, err)
        }
        if m, err := Parse("JPY -9223372036854775808"); err != nil || m.Minor != math.MinInt64 {
            t.Errorf("min yen: %+v %v", m, err)
        }
        if m, err := Parse("CLF 922,337,203,685,477.5807"); err != nil || m.Minor != math.MaxInt64 {
            t.Errorf("max clf: %+v %v", m, err)
        }
    }

    func TestParseStringRoundTrip(t *testing.T) {
        for _, cur := range []string{"USD", "JPY", "BHD", "CLF"} {
            for _, v := range []int64{0, 1, 9, 10, 99, 100, 999, 1000, 123456, 1234567, 100000000, -1, -1000, -999999, math.MaxInt64, math.MinInt64} {
                m := Money{v, cur}
                back, err := Parse(m.String())
                if err != nil || back != m {
                    t.Errorf("%+v -> %q -> %+v, %v", m, m.String(), back, err)
                }
            }
        }
    }

    func TestAdd(t *testing.T) {
        got, err := Add(Money{150, "USD"}, Money{-275, "USD"})
        if err != nil || got != (Money{-125, "USD"}) {
            t.Errorf("got %+v, %v", got, err)
        }
        if _, err := Add(Money{1, "USD"}, Money{1, "EUR"}); !errors.Is(err, ErrMismatch) {
            t.Errorf("mismatch: %v", err)
        }
        if _, err := Add(Money{math.MaxInt64, "USD"}, Money{1, "USD"}); !errors.Is(err, ErrRange) {
            t.Errorf("overflow: %v", err)
        }
        if _, err := Add(Money{math.MinInt64, "USD"}, Money{-1, "USD"}); !errors.Is(err, ErrRange) {
            t.Errorf("underflow: %v", err)
        }
        if got, err := Add(Money{math.MaxInt64, "USD"}, Money{-1, "USD"}); err != nil || got.Minor != math.MaxInt64-1 {
            t.Errorf("edge: %+v %v", got, err)
        }
        if got, err := Add(Money{math.MaxInt64 - 1, "USD"}, Money{1, "USD"}); err != nil || got.Minor != math.MaxInt64 {
            t.Errorf("edge 2: %+v %v", got, err)
        }
        if got, err := Add(Money{math.MinInt64 + 1, "USD"}, Money{-1, "USD"}); err != nil || got.Minor != math.MinInt64 {
            t.Errorf("edge 3: %+v %v", got, err)
        }
        if got, err := Add(Money{0, "USD"}, Money{0, "USD"}); err != nil || got.Minor != 0 {
            t.Errorf("zero: %+v %v", got, err)
        }
    }

    func TestRoundingModes(t *testing.T) {
        // value*num/den with den=2 gives x.5 for odd minor units
        type row struct{ minor, num, den int64 }
        cases := []struct {
            in                         row
            floor, ceil, away, even    int64
        }{
            {row{5, 1, 2}, 2, 3, 3, 2},       // 2.5
            {row{-5, 1, 2}, -3, -2, -3, -2},  // -2.5
            {row{7, 1, 2}, 3, 4, 4, 4},       // 3.5
            {row{-7, 1, 2}, -4, -3, -4, -4},  // -3.5
            {row{12, 1, 5}, 2, 3, 2, 2},      // 2.4
            {row{-12, 1, 5}, -3, -2, -2, -2}, // -2.4
            {row{13, 1, 5}, 2, 3, 3, 3},      // 2.6
            {row{-13, 1, 5}, -3, -2, -3, -3}, // -2.6
            {row{6, 1, 2}, 3, 3, 3, 3},       // exact
            {row{-6, 1, 2}, -3, -3, -3, -3},
            {row{0, 7, 3}, 0, 0, 0, 0},
            {row{1, 1, 2}, 0, 1, 1, 0},       // 0.5
            {row{-1, 1, 2}, -1, 0, -1, 0},    // -0.5
            {row{3, 1, 2}, 1, 2, 2, 2},       // 1.5
            {row{-3, 1, 2}, -2, -1, -2, -2},  // -1.5
            {row{10, 1, -4}, -3, -2, -3, -2}, // -2.5 through a negative denominator
            {row{-10, -1, -4}, -3, -2, -3, -2},
            {row{10, -1, 4}, -3, -2, -3, -2},
        }
        for _, c := range cases {
            for mode, want := range map[Rounding]int64{Floor: c.floor, Ceil: c.ceil, HalfAway: c.away, HalfEven: c.even} {
                got, err := Mul(Money{c.in.minor, "USD"}, c.in.num, c.in.den, mode)
                if err != nil || got.Minor != want || got.Cur != "USD" {
                    t.Errorf("Mul(%v, mode %d) = %+v, %v; want %d", c.in, mode, got, err, want)
                }
            }
        }
    }

    func TestMulTax(t *testing.T) {
        // 7.25% of 19.99 is 1.449275 -> 1.45 (half away) / 1.44 (floor) / 1.45 (ceil)
        net := Money{1999, "USD"}
        for mode, want := range map[Rounding]int64{Floor: 144, Ceil: 145, HalfAway: 145, HalfEven: 145} {
            got, err := Mul(net, 725, 10000, mode)
            if err != nil || got.Minor != want {
                t.Errorf("mode %d: %+v %v want %d", mode, got, err, want)
            }
        }
        // exactly half a cent: 10.10 * 5% = 0.505
        half := Money{1010, "USD"}
        for mode, want := range map[Rounding]int64{Floor: 50, Ceil: 51, HalfAway: 51, HalfEven: 50} {
            got, _ := Mul(half, 5, 100, mode)
            if got.Minor != want {
                t.Errorf("0.505, mode %d: %d want %d", mode, got.Minor, want)
            }
        }
        // 10.30 * 5% = 0.515 -> even picks 52
        got, _ := Mul(Money{1030, "USD"}, 5, 100, HalfEven)
        if got.Minor != 52 {
            t.Errorf("0.515 even: %d", got.Minor)
        }
        got, _ = Mul(Money{-1030, "USD"}, 5, 100, HalfEven)
        if got.Minor != -52 {
            t.Errorf("-0.515 even: %d", got.Minor)
        }
        got, _ = Mul(Money{-1010, "USD"}, 5, 100, HalfAway)
        if got.Minor != -51 {
            t.Errorf("-0.505 away: %d", got.Minor)
        }
    }

    func TestMulErrors(t *testing.T) {
        if _, err := Mul(Money{5, "USD"}, 1, 0, Floor); !errors.Is(err, ErrDivZero) {
            t.Errorf("den 0: %v", err)
        }
        if _, err := Mul(Money{0, "USD"}, 1, 0, Floor); !errors.Is(err, ErrDivZero) {
            t.Errorf("den 0 on zero: %v", err)
        }
        if _, err := Mul(Money{math.MaxInt64, "USD"}, 2, 1, Floor); !errors.Is(err, ErrRange) {
            t.Errorf("overflow: %v", err)
        }
        if _, err := Mul(Money{math.MinInt64, "USD"}, -1, 1, Floor); !errors.Is(err, ErrRange) {
            t.Errorf("min * -1: %v", err)
        }
        if _, err := Mul(Money{-1, "USD"}, math.MinInt64, 1, Floor); !errors.Is(err, ErrRange) {
            t.Errorf("-1 * min: %v", err)
        }
        if _, err := Mul(Money{3, "USD"}, math.MinInt64, 1, Floor); !errors.Is(err, ErrRange) {
            t.Errorf("3 * min: %v", err)
        }
        if _, err := Mul(Money{3, "USD"}, 1, math.MinInt64, Floor); !errors.Is(err, ErrRange) {
            t.Errorf("den min: %v", err)
        }
        if got, err := Mul(Money{math.MaxInt64, "USD"}, 1, 1, Floor); err != nil || got.Minor != math.MaxInt64 {
            t.Errorf("identity at max: %+v %v", got, err)
        }
        if got, err := Mul(Money{math.MinInt64, "USD"}, 1, 1, Floor); err != nil || got.Minor != math.MinInt64 {
            t.Errorf("identity at min: %+v %v", got, err)
        }
        if got, err := Mul(Money{1 << 62, "USD"}, 1, 2, Floor); err != nil || got.Minor != 1<<61 {
            t.Errorf("big half: %+v %v", got, err)
        }
        if got, err := Mul(Money{math.MaxInt64, "USD"}, 0, 5, Floor); err != nil || got.Minor != 0 {
            t.Errorf("times zero: %+v %v", got, err)
        }
    }

    func TestConvert(t *testing.T) {
        cases := []struct {
            m        Money
            to       string
            num, den int64
            mode     Rounding
            want     Money
        }{
            {Money{100, "USD"}, "JPY", 150, 1, HalfAway, Money{150, "JPY"}},
            {Money{1234, "USD"}, "JPY", 150, 1, HalfAway, Money{1851, "JPY"}},
            {Money{1234, "USD"}, "JPY", 150, 1, Floor, Money{1851, "JPY"}},
            {Money{1235, "USD"}, "JPY", 1505, 10, HalfAway, Money{1859, "JPY"}},
            {Money{500, "JPY"}, "USD", 1, 150, HalfAway, Money{333, "USD"}},
            {Money{500, "JPY"}, "USD", 1, 150, Ceil, Money{334, "USD"}},
            {Money{1, "JPY"}, "USD", 1, 150, HalfAway, Money{1, "USD"}},
            {Money{1, "JPY"}, "USD", 1, 300, HalfAway, Money{0, "USD"}},
            {Money{1000, "BHD"}, "USD", 265, 100, HalfAway, Money{265, "USD"}},
            {Money{1, "BHD"}, "USD", 265, 100, HalfAway, Money{0, "USD"}},
            {Money{10, "BHD"}, "USD", 265, 100, HalfAway, Money{3, "USD"}},
            {Money{100, "USD"}, "BHD", 38, 100, HalfAway, Money{380, "BHD"}},
            {Money{100, "USD"}, "CLF", 1, 40, HalfAway, Money{250, "CLF"}},
            {Money{20000, "CLF"}, "USD", 40, 1, HalfAway, Money{8000, "USD"}},
            {Money{100, "USD"}, "EUR", 92, 100, HalfAway, Money{92, "EUR"}},
            {Money{101, "USD"}, "EUR", 92, 100, HalfEven, Money{93, "EUR"}},
            {Money{-100, "USD"}, "EUR", 925, 1000, HalfAway, Money{-93, "EUR"}},
            {Money{-100, "USD"}, "EUR", 925, 1000, HalfEven, Money{-92, "EUR"}},
            {Money{100, "USD"}, "EUR", -92, -100, Floor, Money{92, "EUR"}},
            {Money{100, "USD"}, "USD", 1, 1, Floor, Money{100, "USD"}},
        }
        for _, c := range cases {
            got, err := Convert(c.m, c.to, c.num, c.den, c.mode)
            if err != nil || got != c.want {
                t.Errorf("Convert(%+v, %s, %d/%d, %d) = %+v, %v; want %+v", c.m, c.to, c.num, c.den, c.mode, got, err, c.want)
            }
        }
    }

    func TestConvertErrors(t *testing.T) {
        if _, err := Convert(Money{1, "USD"}, "XXX", 1, 1, Floor); !errors.Is(err, ErrCurrency) {
            t.Errorf("unknown target: %v", err)
        }
        if _, err := Convert(Money{1, "USD"}, "EUR", 1, 0, Floor); !errors.Is(err, ErrDivZero) {
            t.Errorf("den 0: %v", err)
        }
        if _, err := Convert(Money{math.MaxInt64 / 2, "USD"}, "JPY", 1000, 1, Floor); !errors.Is(err, ErrRange) {
            t.Errorf("overflow: %v", err)
        }
        if _, err := Convert(Money{1, "USD"}, "CLF", math.MaxInt64/50, 1, Floor); !errors.Is(err, ErrRange) {
            t.Errorf("exponent shift overflow: %v", err)
        }
        if _, err := Convert(Money{1, "CLF"}, "JPY", 1, math.MaxInt64/50, Floor); !errors.Is(err, ErrRange) {
            t.Errorf("den shift overflow: %v", err)
        }
    }

    func amounts(ms []Money) []int64 {
        out := make([]int64, len(ms))
        for i, m := range ms {
            out[i] = m.Minor
        }
        return out
    }

    func TestAllocateTable(t *testing.T) {
        cases := []struct {
            total   int64
            weights []int64
            want    []int64
        }{
            {100, []int64{1, 1, 1}, []int64{34, 33, 33}},
            {100, []int64{3, 2, 1}, []int64{50, 33, 17}},
            {5, []int64{1, 1}, []int64{3, 2}},
            {1, []int64{1, 1, 1}, []int64{1, 0, 0}},
            {0, []int64{1, 2}, []int64{0, 0}},
            {101, []int64{1, 0, 1}, []int64{51, 0, 50}},
            {10, []int64{7}, []int64{10}},
            {-100, []int64{1, 1, 1}, []int64{-34, -33, -33}},
            {-100, []int64{3, 2, 1}, []int64{-50, -33, -17}},
            {7, []int64{5, 3, 2}, []int64{4, 2, 1}},
            {1000, []int64{333, 333, 334}, []int64{333, 333, 334}},
            {10, []int64{1, 2, 3, 4}, []int64{1, 2, 3, 4}},
            {11, []int64{1, 2, 3, 4}, []int64{1, 2, 3, 5}},
            {2, []int64{0, 1, 1}, []int64{0, 1, 1}},
            {3, []int64{2, 2, 2, 2}, []int64{1, 1, 1, 0}},
            {99, []int64{1, 10, 100}, []int64{1, 9, 89}},
        }
        for _, c := range cases {
            got, err := Allocate(Money{c.total, "EUR"}, c.weights)
            if err != nil || !reflect.DeepEqual(amounts(got), c.want) {
                t.Errorf("Allocate(%d, %v) = %v, %v; want %v", c.total, c.weights, amounts(got), err, c.want)
                continue
            }
            for _, m := range got {
                if m.Cur != "EUR" {
                    t.Errorf("currency lost: %+v", m)
                }
            }
        }
    }

    func TestAllocateRemainderOrder(t *testing.T) {
        // 10 split 1:1:1:1:1:1:1 -> floor 1 each, 3 left over: the first three parts get them
        got, _ := Allocate(Money{10, "USD"}, []int64{1, 1, 1, 1, 1, 1, 1})
        if want := []int64{2, 2, 2, 1, 1, 1, 1}; !reflect.DeepEqual(amounts(got), want) {
            t.Errorf("got %v", amounts(got))
        }
        // remainders 0.8, 0.4, 0.9 (of total 10 with weights 3.8:3.4:... ) -> largest remainder first, not first index
        got, _ = Allocate(Money{10, "USD"}, []int64{19, 17, 14})
        // shares 3.8, 3.4, 2.8 -> floors 3,3,2 leftover 2 -> to .8 (index 0) and .8 (index 2): ties by index
        if want := []int64{4, 3, 3}; !reflect.DeepEqual(amounts(got), want) {
            t.Errorf("tie: got %v", amounts(got))
        }
        got, _ = Allocate(Money{10, "USD"}, []int64{12, 19, 19})
        // shares 2.4, 3.8, 3.8 -> floors 2,3,3 leftover 2 -> indices 1 and 2
        if want := []int64{2, 4, 4}; !reflect.DeepEqual(amounts(got), want) {
            t.Errorf("largest first: got %v", amounts(got))
        }
        got, _ = Allocate(Money{10, "USD"}, []int64{2, 7, 1})
        // shares 2, 7, 1 exactly
        if want := []int64{2, 7, 1}; !reflect.DeepEqual(amounts(got), want) {
            t.Errorf("exact: got %v", amounts(got))
        }
        got, _ = Allocate(Money{100, "USD"}, []int64{1, 6, 3, 0, 0})
        if want := []int64{10, 60, 30, 0, 0}; !reflect.DeepEqual(amounts(got), want) {
            t.Errorf("zero weights: got %v", amounts(got))
        }
    }

    func TestAllocateSumsToTotal(t *testing.T) {
        seed := uint32(7)
        for round := 0; round < 400; round++ {
            seed = seed*1664525 + 1013904223
            n := int(seed>>28)%6 + 1
            ws := make([]int64, n)
            var sum int64
            for i := range ws {
                seed = seed*1664525 + 1013904223
                ws[i] = int64(seed >> 26)
                sum += ws[i]
            }
            if sum == 0 {
                ws[0] = 1
            }
            seed = seed*1664525 + 1013904223
            total := int64(int32(seed)) / 3
            got, err := Allocate(Money{total, "JPY"}, ws)
            if err != nil {
                t.Fatal(err)
            }
            var s int64
            for i, m := range got {
                s += m.Minor
                if total >= 0 && m.Minor < 0 || total < 0 && m.Minor > 0 {
                    t.Fatalf("sign of part %d: %v of %d", i, amounts(got), total)
                }
            }
            if s != total {
                t.Fatalf("parts %v sum to %d, want %d (weights %v)", amounts(got), s, total, ws)
            }
        }
    }

    func TestAllocateHugeAmounts(t *testing.T) {
        got, err := Allocate(Money{math.MaxInt64, "USD"}, []int64{1, 1})
        if err != nil || got[0].Minor != 4611686018427387904 || got[1].Minor != 4611686018427387903 {
            t.Errorf("got %v, %v", amounts(got), err)
        }
        got, err = Allocate(Money{math.MinInt64, "USD"}, []int64{1, 1, 1, 1})
        if err != nil || got[0].Minor != -(1<<61) || got[3].Minor != -(1<<61) {
            t.Errorf("min: %v, %v", amounts(got), err)
        }
        got, err = Allocate(Money{math.MaxInt64, "USD"}, []int64{math.MaxInt64 - 1, 1})
        if err != nil || got[0].Minor+got[1].Minor != math.MaxInt64 {
            t.Errorf("big weights: %v, %v", amounts(got), err)
        }
    }

    func TestAllocateErrors(t *testing.T) {
        bad := [][]int64{nil, {}, {0}, {0, 0, 0}, {1, -1}, {-5}, {math.MaxInt64, 1}, {math.MaxInt64, math.MaxInt64}}
        for _, w := range bad {
            if got, err := Allocate(Money{100, "USD"}, w); !errors.Is(err, ErrBadWeights) || got != nil {
                t.Errorf("Allocate(%v) = %v, %v; want ErrBadWeights", w, got, err)
            }
        }
        if _, err := Allocate(Money{100, "USD"}, []int64{math.MaxInt64}); err != nil {
            t.Errorf("single max weight: %v", err)
        }
    }
'''))

LIB = Lib(
    name="minorcash", lang="go", title="the minorcash package",
    blurb="The invoicing service keeps money as integer minor units with minorcash, which parses and prints amounts, applies rates with explicit rounding and splits totals by weights.",
    files={"go.mod": langs.go_mod("minorcash"), "minorcash.go": SRC, "README.md": README},
    visible_tests={"minorcash_basic_test.go": VISIBLE},
    hidden_tests={"minorcash_full_test.go": HIDDEN},
    mutate=["minorcash.go"], difficulty=4, tags=["money", "rounding", "fixed-point"],
)

register_libs([LIB], n=8)
