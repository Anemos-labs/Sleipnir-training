"""Packed 32-bit timestamps (go): a calendar date-time squeezed into a uint32, with arithmetic and text form."""
from fx import Lib, dd, langs

from generators.fix._lang1 import gosrc, register_libs

README = dd('''
    # stamp32

    The firmware log stores event times in 4 bytes. A `Stamp` is a `uint32` laid out, from the most significant bit down, as

    | field | bits | range |
    |---|---|---|
    | year - 2000 | 6 | 2000 ..= 2063 |
    | month | 4 | 1 ..= 12 |
    | day | 5 | 1 ..= days in the month |
    | hour | 5 | 0 ..= 23 |
    | minute | 6 | 0 ..= 59 |
    | second | 6 | 0 ..= 59 |

    so for valid stamps numeric order is chronological order. Times are plain calendar times (no zone, no leap seconds,
    proleptic Gregorian rules).

    * `IsLeap(year int) bool`: divisible by 4, except centuries that are not divisible by 400. Works for any year.
    * `DaysIn(year, month int) int`: days in that month, `0` when `month` is not 1..12. Works for any year.
    * `Pack(year, month, day, hour, minute, second int) (Stamp, error)`: `ErrRange` when any field is outside its range
      (including a day that does not exist, like Feb 29 in 2023 or Apr 31).
    * `(Stamp) Fields() (year, month, day, hour, minute, second int)` unpacks the bits without validating.
    * `(Stamp) Valid() bool`: all six fields are in range.

    The methods below are only defined for valid stamps.

    * `(Stamp) String() string`: `2024-02-29T13:05:09` (zero padded, 4-digit year).
    * `Parse(text string) (Stamp, error)`: exactly that layout, with `T` or a single space between date and time. `ErrFormat`
      for anything that is not 19 characters of that shape (digits only in the number positions, no signs, no spaces
      around); `ErrRange` when the numbers do not make a valid stamp (month 13, Feb 30, year 1999 or 2064, hour 24...).
    * `(Stamp) Seconds() int64`: seconds since `2000-01-01T00:00:00`. `FromSeconds(n int64) (Stamp, error)` is the inverse;
      `ErrRange` outside `0 ..= 2019686399` (that is 2063-12-31T23:59:59).
    * `(Stamp) Add(seconds int64) (Stamp, error)`: shifts by a number of seconds, which may be negative or huge; `ErrRange`
      if the result would be before 2000 or after 2063 (including when the shift itself is beyond 64 years).
    * `Diff(a, b Stamp) int64`: seconds from `a` to `b` (negative when `b` is earlier).
    * `(Stamp) Weekday() int`: 0 for Sunday ... 6 for Saturday. 2000-01-01 was a Saturday.
    * `(Stamp) YearDay() int`: 1 for January 1st, 366 for December 31st of a leap year.
''')

SRC = gosrc(dd(r'''
    // Package stamp32 packs a calendar date-time into 32 bits.
    package stamp32

    import (
        "errors"
        "fmt"
    )

    const (
        BaseYear   = 2000
        MaxYear    = 2063
        maxSeconds = 2019686399
    )

    var (
        ErrRange  = errors.New("stamp32: value out of range")
        ErrFormat = errors.New("stamp32: malformed timestamp text")
    )

    // Stamp is a packed date-time.
    type Stamp uint32

    // IsLeap reports whether the year has 366 days.
    func IsLeap(year int) bool {
        return year%4 == 0 && (year%100 != 0 || year%400 == 0)
    }

    // DaysIn is the length of a month, 0 for an invalid month.
    func DaysIn(year, month int) int {
        switch month {
        case 1, 3, 5, 7, 8, 10, 12:
            return 31
        case 4, 6, 9, 11:
            return 30
        case 2:
            if IsLeap(year) {
                return 29
            }
            return 28
        }
        return 0
    }

    // Pack builds a stamp from calendar fields.
    func Pack(year, month, day, hour, minute, second int) (Stamp, error) {
        if year < BaseYear || year > MaxYear || month < 1 || month > 12 ||
            day < 1 || day > DaysIn(year, month) ||
            hour < 0 || hour > 23 || minute < 0 || minute > 59 || second < 0 || second > 59 {
            return 0, ErrRange
        }
        v := uint32(year-BaseYear)<<26 | uint32(month)<<22 | uint32(day)<<17 |
            uint32(hour)<<12 | uint32(minute)<<6 | uint32(second)
        return Stamp(v), nil
    }

    // Fields unpacks the stamp.
    func (s Stamp) Fields() (year, month, day, hour, minute, second int) {
        v := uint32(s)
        return int(v>>26) + BaseYear, int(v >> 22 & 0xF), int(v >> 17 & 0x1F), int(v >> 12 & 0x1F), int(v >> 6 & 0x3F), int(v & 0x3F)
    }

    // Valid reports whether every field is in range.
    func (s Stamp) Valid() bool {
        y, mo, d, h, mi, sec := s.Fields()
        _, err := Pack(y, mo, d, h, mi, sec)
        return err == nil
    }

    func (s Stamp) String() string {
        y, mo, d, h, mi, sec := s.Fields()
        return fmt.Sprintf("%04d-%02d-%02dT%02d:%02d:%02d", y, mo, d, h, mi, sec)
    }

    func digits(s string) (int, bool) {
        n := 0
        for i := 0; i < len(s); i++ {
            if s[i] < '0' || s[i] > '9' {
                return 0, false
            }
            n = n*10 + int(s[i]-'0')
        }
        return n, true
    }

    // Parse reads "2006-01-02T15:04:05" (a space may replace the T).
    func Parse(text string) (Stamp, error) {
        if len(text) != 19 || text[4] != '-' || text[7] != '-' || (text[10] != 'T' && text[10] != ' ') || text[13] != ':' || text[16] != ':' {
            return 0, ErrFormat
        }
        var f [6]int
        for i, span := range [6][2]int{{0, 4}, {5, 7}, {8, 10}, {11, 13}, {14, 16}, {17, 19}} {
            n, ok := digits(text[span[0]:span[1]])
            if !ok {
                return 0, ErrFormat
            }
            f[i] = n
        }
        return Pack(f[0], f[1], f[2], f[3], f[4], f[5])
    }

    func (s Stamp) days() int {
        y, mo, d, _, _, _ := s.Fields()
        days := 0
        for yr := BaseYear; yr < y; yr++ {
            days += 365
            if IsLeap(yr) {
                days++
            }
        }
        for m := 1; m < mo; m++ {
            days += DaysIn(y, m)
        }
        return days + d - 1
    }

    // Seconds counts seconds since 2000-01-01T00:00:00.
    func (s Stamp) Seconds() int64 {
        _, _, _, h, mi, sec := s.Fields()
        return int64(s.days())*86400 + int64(h*3600+mi*60+sec)
    }

    // FromSeconds is the inverse of Seconds.
    func FromSeconds(n int64) (Stamp, error) {
        if n < 0 || n > maxSeconds {
            return 0, ErrRange
        }
        days, rem := int(n/86400), int(n%86400)
        year := BaseYear
        for {
            yd := 365
            if IsLeap(year) {
                yd = 366
            }
            if days < yd {
                break
            }
            days -= yd
            year++
        }
        month := 1
        for days >= DaysIn(year, month) {
            days -= DaysIn(year, month)
            month++
        }
        return Pack(year, month, days+1, rem/3600, rem%3600/60, rem%60)
    }

    // Add shifts the stamp by a number of seconds.
    func (s Stamp) Add(seconds int64) (Stamp, error) {
        if seconds > maxSeconds || seconds < -maxSeconds {
            return 0, ErrRange
        }
        return FromSeconds(s.Seconds() + seconds)
    }

    // Diff is the number of seconds from a to b.
    func Diff(a, b Stamp) int64 { return b.Seconds() - a.Seconds() }

    // Weekday is 0 for Sunday.
    func (s Stamp) Weekday() int { return (s.days() + 6) % 7 }

    // YearDay is the 1-based day of the year.
    func (s Stamp) YearDay() int {
        y, mo, d, _, _, _ := s.Fields()
        n := d
        for m := 1; m < mo; m++ {
            n += DaysIn(y, m)
        }
        return n
    }
'''))

VISIBLE = gosrc(dd(r'''
    package stamp32

    import "testing"

    func TestPackAndFields(t *testing.T) {
        s, err := Pack(2024, 2, 29, 13, 5, 9)
        if err != nil {
            t.Fatal(err)
        }
        y, mo, d, h, mi, sec := s.Fields()
        if y != 2024 || mo != 2 || d != 29 || h != 13 || mi != 5 || sec != 9 {
            t.Fatalf("got %d-%d-%d %d:%d:%d", y, mo, d, h, mi, sec)
        }
    }

    func TestLeapYears(t *testing.T) {
        if !IsLeap(2024) || IsLeap(2023) {
            t.Fatal("leap years wrong")
        }
    }
'''))

HIDDEN = gosrc(dd(r'''
    package stamp32

    import (
        "errors"
        "testing"
    )

    func mustPack(t *testing.T, y, mo, d, h, mi, s int) Stamp {
        t.Helper()
        st, err := Pack(y, mo, d, h, mi, s)
        if err != nil {
            t.Fatalf("Pack(%d,%d,%d,%d,%d,%d): %v", y, mo, d, h, mi, s, err)
        }
        return st
    }

    func TestLeapRule(t *testing.T) {
        yes := []int{2000, 2004, 2024, 2060, 1600, 2400, 4}
        no := []int{2001, 2023, 2100, 1900, 2200, 2300, 2063, 1, 2062}
        for _, y := range yes {
            if !IsLeap(y) {
                t.Errorf("%d should be leap", y)
            }
        }
        for _, y := range no {
            if IsLeap(y) {
                t.Errorf("%d should not be leap", y)
            }
        }
    }

    func TestDaysIn(t *testing.T) {
        want := []int{31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31}
        for m, w := range want {
            if got := DaysIn(2023, m+1); got != w {
                t.Errorf("DaysIn(2023, %d) = %d, want %d", m+1, got, w)
            }
        }
        if DaysIn(2024, 2) != 29 || DaysIn(2000, 2) != 29 || DaysIn(2100, 2) != 28 || DaysIn(1900, 2) != 28 {
            t.Errorf("february lengths wrong")
        }
        for _, m := range []int{0, 13, -1, 100} {
            if got := DaysIn(2024, m); got != 0 {
                t.Errorf("DaysIn(2024, %d) = %d, want 0", m, got)
            }
        }
    }

    func TestPackLiterals(t *testing.T) {
        cases := []struct {
            y, mo, d, h, mi, s int
            want               uint32
        }{
            {2000, 1, 1, 0, 0, 0, 4325376},
            {2024, 2, 29, 13, 5, 9, 1622856009},
            {2063, 12, 31, 23, 59, 59, 4282351355},
            {2000, 12, 31, 23, 59, 59, 54492923},
            {2000, 2, 29, 0, 0, 0, 12189696},
            {2038, 1, 19, 3, 14, 7, 2556834695},
            {2023, 7, 4, 12, 0, 0, 1573437440},
        }
        for _, c := range cases {
            st := mustPack(t, c.y, c.mo, c.d, c.h, c.mi, c.s)
            if uint32(st) != c.want {
                t.Errorf("Pack(%v) = %d, want %d", c, st, c.want)
            }
            y, mo, d, h, mi, s := Stamp(c.want).Fields()
            if y != c.y || mo != c.mo || d != c.d || h != c.h || mi != c.mi || s != c.s {
                t.Errorf("Fields(%d) = %d-%d-%d %d:%d:%d", c.want, y, mo, d, h, mi, s)
            }
            if !Stamp(c.want).Valid() {
                t.Errorf("%d should be valid", c.want)
            }
        }
    }

    func TestPackRejects(t *testing.T) {
        bad := [][6]int{
            {1999, 12, 31, 23, 59, 59}, {2064, 1, 1, 0, 0, 0}, {2024, 0, 1, 0, 0, 0}, {2024, 13, 1, 0, 0, 0},
            {2024, 1, 0, 0, 0, 0}, {2024, 1, 32, 0, 0, 0}, {2023, 2, 29, 0, 0, 0}, {2024, 2, 30, 0, 0, 0}, {2024, 4, 31, 0, 0, 0},
            {2024, 1, 1, 24, 0, 0}, {2024, 1, 1, -1, 0, 0}, {2024, 1, 1, 0, 60, 0}, {2024, 1, 1, 0, -1, 0}, {2024, 1, 1, 0, 0, 60},
            {2024, 1, 1, 0, 0, -1}, {-5, 1, 1, 0, 0, 0},
        }
        for _, b := range bad {
            if _, err := Pack(b[0], b[1], b[2], b[3], b[4], b[5]); !errors.Is(err, ErrRange) {
                t.Errorf("Pack(%v): err = %v", b, err)
            }
        }
        good := [][6]int{{2000, 1, 1, 0, 0, 0}, {2063, 12, 31, 23, 59, 59}, {2024, 2, 29, 0, 0, 0}, {2023, 2, 28, 23, 59, 59}, {2024, 4, 30, 0, 0, 0}, {2000, 2, 29, 0, 0, 0}}
        for _, g := range good {
            if _, err := Pack(g[0], g[1], g[2], g[3], g[4], g[5]); err != nil {
                t.Errorf("Pack(%v): %v", g, err)
            }
        }
    }

    func TestValid(t *testing.T) {
        if (Stamp(0)).Valid() {
            t.Errorf("all-zero fields (month 0) are not valid")
        }
        s := mustPack(t, 2024, 6, 15, 12, 30, 30)
        if !s.Valid() {
            t.Errorf("valid stamp reported invalid")
        }
        month13 := Stamp(uint32(s)&^(0xF<<22) | 13<<22)
        if month13.Valid() {
            t.Errorf("month 13 reported valid")
        }
        sec60 := Stamp(uint32(s)&^0x3F | 60)
        if sec60.Valid() {
            t.Errorf("second 60 reported valid")
        }
        day31 := Stamp(uint32(s)&^(0x1F<<17) | 31<<17) // June 31
        if day31.Valid() {
            t.Errorf("June 31 reported valid")
        }
        hour24 := Stamp(uint32(s)&^(0x1F<<12) | 24<<12)
        if hour24.Valid() {
            t.Errorf("hour 24 reported valid")
        }
        min60 := Stamp(uint32(s)&^(0x3F<<6) | 60<<6)
        if min60.Valid() {
            t.Errorf("minute 60 reported valid")
        }
    }

    func TestOrderIsChronological(t *testing.T) {
        times := [][6]int{{2000, 1, 1, 0, 0, 0}, {2000, 1, 1, 0, 0, 1}, {2000, 1, 1, 0, 1, 0}, {2000, 1, 1, 1, 0, 0}, {2000, 1, 2, 0, 0, 0}, {2000, 2, 1, 0, 0, 0}, {2001, 1, 1, 0, 0, 0}, {2063, 12, 31, 23, 59, 59}}
        var prev Stamp
        for i, tm := range times {
            s := mustPack(t, tm[0], tm[1], tm[2], tm[3], tm[4], tm[5])
            if i > 0 && s <= prev {
                t.Errorf("%v not after the previous", tm)
            }
            prev = s
        }
    }

    func TestString(t *testing.T) {
        cases := map[uint32]string{
            4325376:    "2000-01-01T00:00:00",
            1622856009: "2024-02-29T13:05:09",
            4282351355: "2063-12-31T23:59:59",
            2556834695: "2038-01-19T03:14:07",
        }
        for v, want := range cases {
            if got := Stamp(v).String(); got != want {
                t.Errorf("String(%d) = %q, want %q", v, got, want)
            }
        }
    }

    func TestParse(t *testing.T) {
        cases := map[string]uint32{
            "2000-01-01T00:00:00": 4325376,
            "2024-02-29T13:05:09": 1622856009,
            "2024-02-29 13:05:09": 1622856009,
            "2063-12-31T23:59:59": 4282351355,
            "2038-01-19 03:14:07": 2556834695,
        }
        for text, want := range cases {
            got, err := Parse(text)
            if err != nil || uint32(got) != want {
                t.Errorf("Parse(%q) = %d, %v; want %d", text, got, err, want)
            }
        }
    }

    func TestParseFormatErrors(t *testing.T) {
        bad := []string{
            "", "2024-02-29", "2024-02-29T13:05", "2024-02-29T13:05:09Z", "2024-2-29T13:05:09", "2024/02/29T13:05:09",
            "2024-02-29t13:05:09", "2024-02-29  13:05:09", "2024-02-29T13.05.09", "2024-02-29T13:05-09", "+024-02-29T13:05:09",
            "2024-02-29T13:05:0x", "2024-0a-29T13:05:09", " 2024-02-29T13:05:09", "2024-02-29T13:05:09 ", "2024-02--9T13:05:09",
            "2024-02-29T-3:05:09", "2024-02-29T13:+5:09", "20240229T130509", "2024-02-29T13:05:090",
        }
        for _, s := range bad {
            if got, err := Parse(s); !errors.Is(err, ErrFormat) {
                t.Errorf("Parse(%q) = %d, %v; want ErrFormat", s, got, err)
            }
        }
    }

    func TestParseRangeErrors(t *testing.T) {
        bad := []string{
            "1999-12-31T23:59:59", "2064-01-01T00:00:00", "2024-13-01T00:00:00", "2024-00-10T00:00:00", "2023-02-29T00:00:00",
            "2024-02-30T00:00:00", "2024-04-31T00:00:00", "2024-01-00T00:00:00", "2024-01-01T24:00:00", "2024-01-01T00:60:00",
            "2024-01-01T00:00:60", "0000-01-01T00:00:00", "9999-12-31T23:59:59",
        }
        for _, s := range bad {
            if got, err := Parse(s); !errors.Is(err, ErrRange) {
                t.Errorf("Parse(%q) = %d, %v; want ErrRange", s, got, err)
            }
        }
    }

    func TestSecondsLiterals(t *testing.T) {
        cases := []struct {
            v    uint32
            want int64
        }{
            {4325376, 0}, {1622856009, 762527109}, {4282351355, 2019686399}, {54492923, 31622399}, {12189696, 5097600},
            {2556834695, 1200798847}, {1573437440, 741787200},
        }
        for _, c := range cases {
            if got := Stamp(c.v).Seconds(); got != c.want {
                t.Errorf("Seconds(%v) = %d, want %d", Stamp(c.v), got, c.want)
            }
            back, err := FromSeconds(c.want)
            if err != nil || uint32(back) != c.v {
                t.Errorf("FromSeconds(%d) = %d, %v; want %d", c.want, back, err, c.v)
            }
        }
    }

    func TestFromSecondsRange(t *testing.T) {
        for _, n := range []int64{-1, -86400, 2019686400, 2019686401, 1 << 40, -(1 << 40)} {
            if got, err := FromSeconds(n); !errors.Is(err, ErrRange) {
                t.Errorf("FromSeconds(%d) = %d, %v", n, got, err)
            }
        }
        if s, err := FromSeconds(2019686399); err != nil || s.String() != "2063-12-31T23:59:59" {
            t.Errorf("last second: %v %v", s, err)
        }
        if s, err := FromSeconds(0); err != nil || s.String() != "2000-01-01T00:00:00" {
            t.Errorf("first second: %v %v", s, err)
        }
    }

    func TestSecondsRoundTripEveryDayAndEdges(t *testing.T) {
        for n := int64(0); n <= maxSeconds; n += 86400 + 3607 {
            s, err := FromSeconds(n)
            if err != nil {
                t.Fatalf("FromSeconds(%d): %v", n, err)
            }
            if !s.Valid() || s.Seconds() != n {
                t.Fatalf("round trip of %d gave %v (%d)", n, s, s.Seconds())
            }
        }
        for _, y := range []int{2000, 2004, 2023, 2024, 2059, 2060, 2063} {
            for m := 1; m <= 12; m++ {
                for _, d := range []int{1, DaysIn(y, m)} {
                    s := mustPack(t, y, m, d, 23, 59, 59)
                    back, err := FromSeconds(s.Seconds())
                    if err != nil || back != s {
                        t.Fatalf("%v: round trip gave %v, %v", s, back, err)
                    }
                }
            }
        }
    }

    func TestAdd(t *testing.T) {
        cases := []struct {
            from string
            sec  int64
            want string
        }{
            {"2024-02-28T23:59:59", 1, "2024-02-29T00:00:00"},
            {"2024-02-29T00:00:00", -1, "2024-02-28T23:59:59"},
            {"2023-12-31T23:59:59", 1, "2024-01-01T00:00:00"},
            {"2024-01-31T12:00:00", 86400 * 29, "2024-02-29T12:00:00"},
            {"2024-03-01T00:00:00", -86400, "2024-02-29T00:00:00"},
            {"2023-03-01T00:00:00", -86400, "2023-02-28T00:00:00"},
            {"2000-02-28T12:00:00", 86400, "2000-02-29T12:00:00"},
            {"2010-06-15T08:30:00", 10*365*86400 + 3*3600, "2020-06-12T11:30:00"},
            {"2024-06-15T12:00:00", 0, "2024-06-15T12:00:00"},
            {"2000-01-01T00:00:00", 2019686399, "2063-12-31T23:59:59"},
            {"2063-12-31T23:59:59", -2019686399, "2000-01-01T00:00:00"},
        }
        for _, c := range cases {
            from, err := Parse(c.from)
            if err != nil {
                t.Fatal(err)
            }
            got, err := from.Add(c.sec)
            if err != nil || got.String() != c.want {
                t.Errorf("%s + %d = %v, %v; want %s", c.from, c.sec, got, err, c.want)
            }
        }
    }

    func TestAddOutOfRange(t *testing.T) {
        first, _ := Parse("2000-01-01T00:00:00")
        last, _ := Parse("2063-12-31T23:59:59")
        mid, _ := Parse("2030-01-01T00:00:00")
        cases := []struct {
            from Stamp
            sec  int64
        }{
            {first, -1}, {last, 1}, {mid, 1 << 40}, {mid, -(1 << 40)}, {mid, 9223372036854775807}, {mid, -9223372036854775807},
            {first, 2019686400}, {last, -2019686400}, {mid, 1 << 62},
        }
        for _, c := range cases {
            if got, err := c.from.Add(c.sec); !errors.Is(err, ErrRange) {
                t.Errorf("%v + %d = %v, %v; want ErrRange", c.from, c.sec, got, err)
            }
        }
    }

    func TestDiff(t *testing.T) {
        a, _ := Parse("2024-02-28T23:59:59")
        b, _ := Parse("2024-03-01T00:00:00")
        if got := Diff(a, b); got != 86401 {
            t.Errorf("Diff = %d", got)
        }
        if got := Diff(b, a); got != -86401 {
            t.Errorf("reverse Diff = %d", got)
        }
        if Diff(a, a) != 0 {
            t.Errorf("self Diff")
        }
        c, _ := Parse("2023-02-28T00:00:00")
        d, _ := Parse("2023-03-01T00:00:00")
        e, _ := Parse("2024-02-28T00:00:00")
        f, _ := Parse("2024-03-01T00:00:00")
        if Diff(c, d) != 86400 || Diff(e, f) != 2*86400 {
            t.Errorf("february lengths: %d %d", Diff(c, d), Diff(e, f))
        }
    }

    func TestWeekdayAndYearDay(t *testing.T) {
        cases := []struct {
            text    string
            weekday int
            yday    int
        }{
            {"2000-01-01T00:00:00", 6, 1},
            {"2024-02-29T13:05:09", 4, 60},
            {"2063-12-31T23:59:59", 1, 365},
            {"2000-12-31T23:59:59", 0, 366},
            {"2000-02-29T00:00:00", 2, 60},
            {"2038-01-19T03:14:07", 2, 19},
            {"2023-07-04T12:00:00", 2, 185},
            {"2024-03-01T00:00:00", 5, 61},
            {"2023-03-01T00:00:00", 3, 60},
            {"2024-12-31T00:00:00", 2, 366},
        }
        for _, c := range cases {
            s, err := Parse(c.text)
            if err != nil {
                t.Fatal(err)
            }
            if got := s.Weekday(); got != c.weekday {
                t.Errorf("Weekday(%s) = %d, want %d", c.text, got, c.weekday)
            }
            if got := s.YearDay(); got != c.yday {
                t.Errorf("YearDay(%s) = %d, want %d", c.text, got, c.yday)
            }
        }
    }
'''))

LIB = Lib(
    name="stamp32", lang="go", title="the stamp32 package",
    blurb="The firmware log stores event times in four bytes, and stamp32 packs, prints, parses and does arithmetic on those 32-bit timestamps.",
    files={"go.mod": langs.go_mod("stamp32"), "stamp32.go": SRC, "README.md": README},
    visible_tests={"stamp32_basic_test.go": VISIBLE},
    hidden_tests={"stamp32_full_test.go": HIDDEN},
    mutate=["stamp32.go"], difficulty=1, tags=["time", "bitpacking", "calendar"],
)

register_libs([LIB], n=8)
