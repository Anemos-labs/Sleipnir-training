"""Go libraries for the testing families: meter readings, bell schedules."""
from __future__ import annotations

from fx import dd, langs

from ._engine import TLib

WHERE_GO = ("Put your tests next to the code in `_test.go` files of the same package (the standard `testing` package only); "
            "they are run with `go test ./...` from the repository root.")

# ---------------------------------------------------------------------------------------------------------------------
# meter readings
# ---------------------------------------------------------------------------------------------------------------------

METER_README = dd('''
    # meter

    Reading helpers for the Hollin Water meter-reading app. A meter register has a fixed number of decimal dials (usually 5)
    and wraps from `99999` back to `00000`.

    ## `Parse(s string, digits int) (int, error)`
    `s` must be exactly `digits` ASCII digits (leading zeros are fine) and `digits` must be 1..9. Anything else (wrong length, a
    sign, a space, a letter) returns `ErrFormat`.

    ## `Consumption(prev, cur, digits int) (int, error)`
    Units used between two readings. Both readings must lie in `0 .. 10^digits - 1`, otherwise `ErrRange`. If `cur >= prev` the answer is
    `cur - prev`. If `cur < prev` the register wrapped once and the answer is `10^digits - prev + cur`; but a wrap that implies *more
    than half* of the register (`usage > 10^digits / 2`, integer division) is `ErrSuspicious` (a replaced meter or a misread is more
    likely). A reading that did not wrap is never suspicious, however large.

    ## `Spread(total, days int) ([]int, error)`
    Splits `total` units over `days` days. `days` must be at least 1 and `total` at least 0, otherwise `ErrRange`. Every day gets
    `total / days`; the remainder is handed out one unit at a time to the *earliest* days. The result always has `days` entries.

    ## `Bill(units int, tiers []Tier) int`
    Progressive pricing in pence. `Tier{Upto, Pence}`: the units from the previous tier's `Upto` (0 for the first tier) up to this tier's
    `Upto` cost `Pence` each. A tier with `Upto == 0` that is not the first is the last, unlimited tier. Negative `units` cost 0.
    Units above the last tier's `Upto` (when that is not 0) are not charged. The tiers are given in ascending order and are not validated.
''')

METER_SRC = dd('''
    // Package meter has the arithmetic of the Hollin Water meter-reading app.
    package meter

    import "errors"

    var (
        ErrFormat     = errors.New("meter: bad reading format")
        ErrRange      = errors.New("meter: value out of range")
        ErrSuspicious = errors.New("meter: implausible wrap-around")
    )

    // Tier is one band of the progressive tariff.
    type Tier struct {
        Upto  int // cumulative units up to which this band applies; 0 on the last band means unlimited
        Pence int // price per unit in this band
    }

    func pow10(n int) int {
        p := 1
        for i := 0; i < n; i++ {
            p *= 10
        }
        return p
    }

    // Parse reads a register value written with exactly digits digits.
    func Parse(s string, digits int) (int, error) {
        if digits < 1 || digits > 9 || len(s) != digits {
            return 0, ErrFormat
        }
        v := 0
        for _, c := range s {
            if c < '0' || c > '9' {
                return 0, ErrFormat
            }
            v = v*10 + int(c-'0')
        }
        return v, nil
    }

    // Consumption is the number of units between two readings of a register with the given number of dials.
    func Consumption(prev, cur, digits int) (int, error) {
        size := pow10(digits)
        if prev < 0 || cur < 0 || prev >= size || cur >= size {
            return 0, ErrRange
        }
        if cur >= prev {
            return cur - prev, nil
        }
        used := size - prev + cur
        if used > size/2 {
            return 0, ErrSuspicious
        }
        return used, nil
    }

    // Spread divides total units over days days, giving the remainder to the earliest days.
    func Spread(total, days int) ([]int, error) {
        if days < 1 || total < 0 {
            return nil, ErrRange
        }
        out := make([]int, days)
        base, rem := total/days, total%days
        for i := range out {
            out[i] = base
            if i < rem {
                out[i]++
            }
        }
        return out, nil
    }

    // Bill prices units with a progressive tariff, in pence.
    func Bill(units int, tiers []Tier) int {
        if units <= 0 {
            return 0
        }
        total, from := 0, 0
        for i, t := range tiers {
            upto := t.Upto
            if upto == 0 && i > 0 {
                upto = units
            }
            if upto > units {
                upto = units
            }
            if upto > from {
                total += (upto - from) * t.Pence
                from = upto
            }
            if from >= units {
                break
            }
        }
        return total
    }
''')

METER_TEST = dd('''
    package meter

    import (
        "errors"
        "reflect"
        "testing"
    )

    func TestParse(t *testing.T) {
        cases := []struct {
            in     string
            digits int
            want   int
            err    error
        }{
            {"00000", 5, 0, nil},
            {"00123", 5, 123, nil},
            {"99999", 5, 99999, nil},
            {"7", 1, 7, nil},
            {"123456789", 9, 123456789, nil},
            {"0123", 5, 0, ErrFormat},
            {"001234", 5, 0, ErrFormat},
            {"", 5, 0, ErrFormat},
            {"12a45", 5, 0, ErrFormat},
            {"-1234", 5, 0, ErrFormat},
            {"+1234", 5, 0, ErrFormat},
            {" 1234", 5, 0, ErrFormat},
            {"1234:", 5, 0, ErrFormat},
            {"12/45", 5, 0, ErrFormat},
            {"00001", 0, 0, ErrFormat},
            {"1", 0, 0, ErrFormat},
            {"1234567890", 10, 0, ErrFormat},
            {"-", 1, 0, ErrFormat},
        }
        for _, c := range cases {
            got, err := Parse(c.in, c.digits)
            if !errors.Is(err, c.err) || got != c.want {
                t.Errorf("Parse(%q, %d) = %d, %v; want %d, %v", c.in, c.digits, got, err, c.want, c.err)
            }
        }
    }

    func TestConsumption(t *testing.T) {
        cases := []struct {
            prev, cur, digits int
            want              int
            err               error
        }{
            {100, 250, 5, 150, nil},
            {100, 100, 5, 0, nil},
            {0, 99999, 5, 99999, nil},
            {99950, 20, 5, 70, nil},
            {99999, 0, 5, 1, nil},
            {60000, 9999, 5, 49999, nil},
            {60000, 10000, 5, 50000, nil},
            {60000, 10001, 5, 0, ErrSuspicious},
            {50001, 0, 5, 49999, nil},
            {50000, 0, 5, 50000, nil},
            {20, 10, 5, 0, ErrSuspicious},
            {500, 100, 3, 0, ErrSuspicious},
            {500, 20, 3, 0, ErrSuspicious},
            {800, 450, 3, 0, ErrSuspicious},
            {600, 200, 3, 0, ErrSuspicious},
            {900, 450, 3, 0, ErrSuspicious},
            {990, 10, 3, 20, nil},
            {-1, 5, 5, 0, ErrRange},
            {5, -1, 5, 0, ErrRange},
            {100000, 5, 5, 0, ErrRange},
            {5, 100000, 5, 0, ErrRange},
            {99999, 99999, 5, 0, nil},
            {5, 1000, 3, 0, ErrRange},
            {1000, 5, 3, 0, ErrRange},
        }
        for _, c := range cases {
            got, err := Consumption(c.prev, c.cur, c.digits)
            if !errors.Is(err, c.err) || got != c.want {
                t.Errorf("Consumption(%d, %d, %d) = %d, %v; want %d, %v", c.prev, c.cur, c.digits, got, err, c.want, c.err)
            }
        }
    }

    func TestConsumptionHalfRegister(t *testing.T) {
        // 3 dials: the register holds 1000, half is 500. A wrap using exactly 500 is allowed, 501 is not.
        if got, err := Consumption(700, 200, 3); err != nil || got != 500 {
            t.Errorf("exactly half: got %d, %v", got, err)
        }
        if _, err := Consumption(700, 201, 3); !errors.Is(err, ErrSuspicious) {
            t.Errorf("just over half should be suspicious, got %v", err)
        }
        if got, err := Consumption(700, 199, 3); err != nil || got != 499 {
            t.Errorf("just under half: got %d, %v", got, err)
        }
        // 1 dial: size 10, half 5
        if got, err := Consumption(7, 2, 1); err != nil || got != 5 {
            t.Errorf("one dial exactly half: got %d, %v", got, err)
        }
        if _, err := Consumption(7, 3, 1); !errors.Is(err, ErrSuspicious) {
            t.Errorf("one dial over half: got %v", err)
        }
    }

    func TestSpread(t *testing.T) {
        cases := []struct {
            total, days int
            want        []int
            err         error
        }{
            {10, 5, []int{2, 2, 2, 2, 2}, nil},
            {10, 3, []int{4, 3, 3}, nil},
            {11, 3, []int{4, 4, 3}, nil},
            {2, 5, []int{1, 1, 0, 0, 0}, nil},
            {0, 3, []int{0, 0, 0}, nil},
            {7, 1, []int{7}, nil},
            {1, 1, []int{1}, nil},
            {5, 0, nil, ErrRange},
            {5, -2, nil, ErrRange},
            {-1, 3, nil, ErrRange},
            {100, 7, []int{15, 15, 14, 14, 14, 14, 14}, nil},
        }
        for _, c := range cases {
            got, err := Spread(c.total, c.days)
            if !errors.Is(err, c.err) || !reflect.DeepEqual(got, c.want) {
                t.Errorf("Spread(%d, %d) = %v, %v; want %v, %v", c.total, c.days, got, err, c.want, c.err)
            }
        }
    }

    var tariff = []Tier{{Upto: 10, Pence: 100}, {Upto: 30, Pence: 80}, {Upto: 0, Pence: 50}}

    func TestBill(t *testing.T) {
        cases := []struct {
            units int
            tiers []Tier
            want  int
        }{
            {0, tariff, 0},
            {-5, tariff, 0},
            {1, tariff, 100},
            {10, tariff, 1000},
            {11, tariff, 1080},
            {30, tariff, 1000 + 20*80},
            {31, tariff, 1000 + 20*80 + 50},
            {100, tariff, 1000 + 20*80 + 70*50},
            {25, []Tier{{Upto: 10, Pence: 3}}, 30},
            {15, []Tier{{Upto: 10, Pence: 3}, {Upto: 20, Pence: 4}}, 30 + 20},
            {20, []Tier{{Upto: 10, Pence: 3}, {Upto: 20, Pence: 4}}, 30 + 40},
            {12, nil, 0},
        }
        for _, c := range cases {
            if got := Bill(c.units, c.tiers); got != c.want {
                t.Errorf("Bill(%d, %v) = %d, want %d", c.units, c.tiers, got, c.want)
            }
        }
    }
''')

METER_STUB = dd('''
    package meter

    import "testing"

    func TestSmoke(t *testing.T) {
        if _, err := Parse("00001", 5); err != nil {
            t.Fatal(err)
        }
    }
''')


def meter(rng) -> TLib:
    files = {"README.md": METER_README, "go.mod": langs.go_mod("hollin"), "meter/meter.go": METER_SRC}
    wrong = [
        ("meter/meter_gold_test.go", '{"00123", 5, 123, nil},', '{"00123", 5, 124, nil},'),
        ("meter/meter_gold_test.go", '{99950, 20, 5, 70, nil},', '{99950, 20, 5, 69, nil},'),
        ("meter/meter_gold_test.go", '{60000, 10000, 5, 50000, nil},', '{60000, 10000, 5, 0, ErrSuspicious},'),
        ("meter/meter_gold_test.go", '{11, 3, []int{4, 4, 3}, nil},', '{11, 3, []int{4, 3, 4}, nil},'),
        ("meter/meter_gold_test.go", '{11, tariff, 1080},', '{11, tariff, 1100},'),
        ("meter/meter_gold_test.go", '{"1234567890", 10, 0, ErrFormat},', '{"1234567890", 10, 1234567890, nil},'),
    ]
    return TLib(
        name="go-meter", lang="go", title="the Hollin Water meter arithmetic", blurb="The meter-reading app turns dial readings into consumption and bills.",
        files=files, stub={"meter/smoke_test.go": METER_STUB}, gold={"meter/meter_gold_test.go": METER_TEST}, mutate=["meter/meter.go"], cmd="go test -count=1 ./...",
        where=WHERE_GO, difficulty=3, wrong_edits=wrong, strip_keep={}, timeout=60, focus="the register wrap-around (and when it is suspicious), the remainder rule of Spread, and the tier boundaries of Bill",
    )


# ---------------------------------------------------------------------------------------------------------------------
# bell schedule
# ---------------------------------------------------------------------------------------------------------------------

BELLS_README = dd('''
    # bells

    Bell schedule resolver for the Lowmoor school. A schedule is a text file, one entry per line:

        # comments and blank lines are ignored
        Mon-Fri 08:30 Assembly
        Mon,Wed 13:15 Sports
        Fri-Mon 18:00 Evening club
        2025-03-14 09:00 Staff training
        2025-03-12 00:00 -

    An entry is `<days> <HH:MM> <label>`. `<days>` is either a comma-separated list whose items are single days (`Mon`) or ranges
    (`Mon-Fri`; a range may wrap over the weekend: `Fri-Mon` is Fri, Sat, Sun, Mon), or one calendar date `YYYY-MM-DD`. Day names are
    exactly `Mon Tue Wed Thu Fri Sat Sun`. The time is 24 hour `HH:MM` with two digits each (`08:30`, not `8:30`; `00:00`..`23:59`). The
    label is the rest of the line, trimmed, with runs of blanks collapsed to one space. The label `-` means "no bell".

    ## `Parse(text string) (*Schedule, error)`
    Reads a schedule. A malformed line gives an error for which `errors.Is(err, ErrSyntax)` is true and whose text contains `line N`
    (the 1-based line number).

    ## `(*Schedule) On(day time.Time) []Bell`
    The bells that ring on a calendar day, ordered by time and then by label. Entries with a date replace the recurring entries for that
    day completely (a date entry with label `-` therefore means a silent day). Never returns nil: a day without bells gives an empty
    slice. `Bell{At: "08:30", Label: "Assembly"}`.

    ## `(*Schedule) Next(now time.Time) (Bell, time.Time, bool)`
    The next bell that rings *strictly after* `now`, searching today and the following 13 days (14 days in all). The returned time is
    on the bell's day at its `HH:MM`, in `now`'s location. `false` if there is none in that window.
''')

BELLS_SRC = dd('''
    // Package bells resolves the school bell schedule for a given day.
    package bells

    import (
        "errors"
        "fmt"
        "sort"
        "strings"
        "time"
    )

    // ErrSyntax is wrapped by every Parse error.
    var ErrSyntax = errors.New("bells: syntax error")

    // Bell is one ring of the bell.
    type Bell struct {
        At    string // "HH:MM"
        Label string
    }

    type entry struct {
        days map[time.Weekday]bool // recurring entries
        date string                // "2006-01-02" for one-off entries
        bell Bell
        none bool // label "-": rings nothing
    }

    // Schedule is a parsed bell schedule.
    type Schedule struct {
        entries []entry
    }

    var dayNames = map[string]time.Weekday{
        "Mon": time.Monday, "Tue": time.Tuesday, "Wed": time.Wednesday, "Thu": time.Thursday,
        "Fri": time.Friday, "Sat": time.Saturday, "Sun": time.Sunday,
    }

    func parseDays(spec string) (map[time.Weekday]bool, error) {
        set := map[time.Weekday]bool{}
        for _, part := range strings.Split(spec, ",") {
            if i := strings.Index(part, "-"); i >= 0 {
                a, okA := dayNames[part[:i]]
                b, okB := dayNames[part[i+1:]]
                if !okA || !okB {
                    return nil, fmt.Errorf("bad day range %q", part)
                }
                for d := a; ; d = (d + 1) % 7 {
                    set[d] = true
                    if d == b {
                        break
                    }
                }
                continue
            }
            d, ok := dayNames[part]
            if !ok {
                return nil, fmt.Errorf("bad day %q", part)
            }
            set[d] = true
        }
        return set, nil
    }

    func parseClock(s string) (int, int, bool) {
        if len(s) != 5 || s[2] != ':' {
            return 0, 0, false
        }
        for _, i := range []int{0, 1, 3, 4} {
            if s[i] < '0' || s[i] > '9' {
                return 0, 0, false
            }
        }
        h := int(s[0]-'0')*10 + int(s[1]-'0')
        m := int(s[3]-'0')*10 + int(s[4]-'0')
        return h, m, h < 24 && m < 60
    }

    // Parse reads a schedule file.
    func Parse(text string) (*Schedule, error) {
        s := &Schedule{}
        for n, raw := range strings.Split(text, "\\n") {
            line := strings.TrimSpace(raw)
            if line == "" || strings.HasPrefix(line, "#") {
                continue
            }
            f := strings.Fields(line)
            if len(f) < 3 {
                return nil, fmt.Errorf("line %d: want <days> <HH:MM> <label>: %w", n+1, ErrSyntax)
            }
            if _, _, ok := parseClock(f[1]); !ok {
                return nil, fmt.Errorf("line %d: bad time %q: %w", n+1, f[1], ErrSyntax)
            }
            label := strings.Join(f[2:], " ")
            e := entry{bell: Bell{At: f[1], Label: label}, none: label == "-"}
            if _, err := time.Parse("2006-01-02", f[0]); err == nil {
                e.date = f[0]
            } else {
                days, err := parseDays(f[0])
                if err != nil {
                    return nil, fmt.Errorf("line %d: %v: %w", n+1, err, ErrSyntax)
                }
                e.days = days
            }
            s.entries = append(s.entries, e)
        }
        return s, nil
    }

    // On returns the bells of one calendar day.
    func (s *Schedule) On(day time.Time) []Bell {
        key := day.Format("2006-01-02")
        out := []Bell{}
        dated := false
        for _, e := range s.entries {
            if e.date == key {
                dated = true
                if !e.none {
                    out = append(out, e.bell)
                }
            }
        }
        if !dated {
            for _, e := range s.entries {
                if e.days[day.Weekday()] && !e.none {
                    out = append(out, e.bell)
                }
            }
        }
        sort.Slice(out, func(i, j int) bool {
            if out[i].At != out[j].At {
                return out[i].At < out[j].At
            }
            return out[i].Label < out[j].Label
        })
        return out
    }

    // Next finds the next bell strictly after now, looking at most 14 days ahead.
    func (s *Schedule) Next(now time.Time) (Bell, time.Time, bool) {
        for i := 0; i < 14; i++ {
            day := now.AddDate(0, 0, i)
            for _, b := range s.On(day) {
                h, m, _ := parseClock(b.At)
                t := time.Date(day.Year(), day.Month(), day.Day(), h, m, 0, 0, now.Location())
                if t.After(now) {
                    return b, t, true
                }
            }
        }
        return Bell{}, time.Time{}, false
    }
''')

BELLS_TEST = dd('''
    package bells

    import (
        "errors"
        "reflect"
        "strings"
        "testing"
        "time"
    )

    const sample = `
    # Lowmoor school bells
    Mon-Fri 08:30 Assembly
    Mon,Wed 13:15 Sports
    Fri-Mon 18:00   Evening   club
    Tue 09:05 Choir
    2025-03-14 09:00 Staff training
    2025-03-12 00:00 -
    `

    func day(d int) time.Time { return time.Date(2025, 3, d, 12, 0, 0, 0, time.UTC) }

    func mustParse(t *testing.T, text string) *Schedule {
        t.Helper()
        s, err := Parse(text)
        if err != nil {
            t.Fatalf("Parse: %v", err)
        }
        return s
    }

    func TestOnRecurring(t *testing.T) {
        s := mustParse(t, sample)
        cases := []struct {
            d    int
            want []Bell
        }{
            {10, []Bell{{"08:30", "Assembly"}, {"13:15", "Sports"}, {"18:00", "Evening club"}}}, // Monday
            {11, []Bell{{"08:30", "Assembly"}, {"09:05", "Choir"}}},                           // Tuesday
            {13, []Bell{{"08:30", "Assembly"}}},                                               // Thursday
            {15, []Bell{{"18:00", "Evening club"}}},                                           // Saturday (Fri-Mon wraps)
            {16, []Bell{{"18:00", "Evening club"}}},                                           // Sunday
            {17, []Bell{{"08:30", "Assembly"}, {"13:15", "Sports"}, {"18:00", "Evening club"}}},
        }
        for _, c := range cases {
            if got := s.On(day(c.d)); !reflect.DeepEqual(got, c.want) {
                t.Errorf("On(2025-03-%d) = %v, want %v", c.d, got, c.want)
            }
        }
    }

    func TestOnDateEntriesReplace(t *testing.T) {
        s := mustParse(t, sample)
        if got, want := s.On(day(14)), []Bell{{"09:00", "Staff training"}}; !reflect.DeepEqual(got, want) {
            t.Errorf("Friday with a date entry: got %v want %v", got, want)
        }
        got := s.On(day(12)) // Wednesday, silenced by "-"
        if got == nil || len(got) != 0 {
            t.Errorf("silent day: got %#v, want an empty non-nil slice", got)
        }
        empty := mustParse(t, "")
        if got := empty.On(day(10)); got == nil || len(got) != 0 {
            t.Errorf("empty schedule: got %#v", got)
        }
    }

    func TestOnOrderingValid(t *testing.T) {
        s := mustParse(t, "Mon 09:00 Zebra\\nMon 09:00 Apple\\nMon 08:59 Early\\nMon 23:59 Night\\nMon 00:00 Dawn\\nMon 10:00 Ten")
        want := []Bell{{"00:00", "Dawn"}, {"08:59", "Early"}, {"09:00", "Apple"}, {"09:00", "Zebra"}, {"10:00", "Ten"}, {"23:59", "Night"}}
        if got := s.On(day(10)); !reflect.DeepEqual(got, want) {
            t.Errorf("got %v want %v", got, want)
        }
    }

    func TestDayLists(t *testing.T) {
        s := mustParse(t, "Mon,Wed-Thu,Sun 07:00 A\\nSat-Sun 07:30 B\\nTue 07:45 C\\nWed-Wed 08:00 D")
        var seen []string
        for d := 10; d <= 16; d++ {
            names := []string{}
            for _, b := range s.On(day(d)) {
                names = append(names, b.Label)
            }
            seen = append(seen, strings.Join(names, ""))
        }
        want := []string{"A", "C", "AD", "A", "", "B", "AB"}
        if !reflect.DeepEqual(seen, want) {
            t.Errorf("got %v want %v", seen, want)
        }
    }

    func TestParseErrors(t *testing.T) {
        bad := []struct{ text, line string }{
            {"Mon 08:30", "line 1"},
            {"Mon", "line 1"},
            {"Mun 08:30 X", "line 1"},
            {"Mon-Xyz 08:30 X", "line 1"},
            {"Mon,Foo 08:30 X", "line 1"},
            {"Mon 8:30 X", "line 1"},
            {"Mon 24:00 X", "line 1"},
            {"Mon 12:60 X", "line 1"},
            {"Mon 12-30 X", "line 1"},
            {"Mon 1a:30 X", "line 1"},
            {"Mon 08:3 X", "line 1"},
            {"Mon 08:301 X", "line 1"},
            {"2025-13-01 08:30 X", "line 1"},
            {"# fine\\n\\nMon 08:30 ok\\nMon nonsense X", "line 4"},
            {"Mon 08:30 ok\\n\\n\\nbogus", "line 4"},
            {"mon 08:30 X", "line 1"},
        }
        for _, c := range bad {
            _, err := Parse(c.text)
            if !errors.Is(err, ErrSyntax) {
                t.Errorf("Parse(%q): want ErrSyntax, got %v", c.text, err)
                continue
            }
            if !strings.Contains(err.Error(), c.line) {
                t.Errorf("Parse(%q): error %q should mention %q", c.text, err, c.line)
            }
        }
    }

    func TestParseAccepts(t *testing.T) {
        for _, text := range []string{"Mon 00:00 X", "Mon 23:59 X", "  Mon   08:30   Two   words  ", "Mon 08:30 -", "2024-02-29 10:00 Leap", "# only a comment", "\\n\\n"} {
            if _, err := Parse(text); err != nil {
                t.Errorf("Parse(%q): %v", text, err)
            }
        }
        s := mustParse(t, "  Mon   08:30   Two   words  ")
        if got := s.On(day(10)); len(got) != 1 || got[0].Label != "Two words" {
            t.Errorf("label not normalised: %v", got)
        }
    }

    func at(d, h, m int) time.Time { return time.Date(2025, 3, d, h, m, 0, 0, time.UTC) }

    func TestNext(t *testing.T) {
        s := mustParse(t, sample)
        cases := []struct {
            now  time.Time
            want Bell
            when time.Time
        }{
            {at(10, 8, 0), Bell{"08:30", "Assembly"}, at(10, 8, 30)},
            {at(10, 8, 29), Bell{"08:30", "Assembly"}, at(10, 8, 30)},
            {at(10, 8, 30), Bell{"13:15", "Sports"}, at(10, 13, 15)},
            {at(10, 8, 31), Bell{"13:15", "Sports"}, at(10, 13, 15)},
            {at(10, 18, 0), Bell{"08:30", "Assembly"}, at(11, 8, 30)},
            {at(11, 9, 5), Bell{"08:30", "Assembly"}, at(13, 8, 30)},
            {at(12, 12, 0), Bell{"08:30", "Assembly"}, at(13, 8, 30)},
            {at(14, 10, 0), Bell{"18:00", "Evening club"}, at(15, 18, 0)},
            {at(16, 19, 0), Bell{"08:30", "Assembly"}, at(17, 8, 30)},
        }
        for _, c := range cases {
            b, when, ok := s.Next(c.now)
            if !ok || b != c.want || !when.Equal(c.when) {
                t.Errorf("Next(%v) = %v, %v, %v; want %v at %v", c.now, b, when, ok, c.want, c.when)
            }
        }
    }

    func TestNextHorizon(t *testing.T) {
        s := mustParse(t, "2025-03-25 09:00 Exam")
        if _, _, ok := s.Next(at(11, 12, 0)); ok {
            t.Errorf("day 14 ahead (the 15th day) must not be searched")
        }
        b, when, ok := s.Next(at(12, 0, 0))
        if !ok || b.Label != "Exam" || !when.Equal(at(25, 9, 0)) {
            t.Errorf("13 days ahead should be found: %v %v %v", b, when, ok)
        }
        if _, _, ok := mustParse(t, "# nothing").Next(at(10, 0, 0)); ok {
            t.Errorf("empty schedule has no next bell")
        }
    }

    func TestNextKeepsLocation(t *testing.T) {
        loc := time.FixedZone("X", 3600)
        s := mustParse(t, "Mon 08:30 A")
        now := time.Date(2025, 3, 10, 7, 0, 0, 0, loc)
        _, when, ok := s.Next(now)
        if !ok || when.Location() != loc || when.Hour() != 8 || when.Minute() != 30 {
            t.Errorf("got %v %v", when, ok)
        }
    }
''')

BELLS_STUB = dd('''
    package bells

    import "testing"

    func TestSmoke(t *testing.T) {
        if _, err := Parse("Mon 08:30 Assembly"); err != nil {
            t.Fatal(err)
        }
    }
''')


def bells(rng) -> TLib:
    files = {"README.md": BELLS_README, "go.mod": langs.go_mod("lowmoor"), "bells/bells.go": BELLS_SRC}
    wrong = [
        ("bells/bells_gold_test.go", '{15, []Bell{{"18:00", "Evening club"}}},                                           // Saturday (Fri-Mon wraps)',
         '{15, []Bell{}},                                           // Saturday (Fri-Mon wraps)'),
        ("bells/bells_gold_test.go", '{at(10, 8, 30), Bell{"13:15", "Sports"}, at(10, 13, 15)},', '{at(10, 8, 30), Bell{"08:30", "Assembly"}, at(10, 8, 30)},'),
        ("bells/bells_gold_test.go", 'want := []string{"A", "C", "AD", "A", "", "B", "AB"}', 'want := []string{"A", "C", "AD", "A", "D", "B", "AB"}'),
        ("bells/bells_gold_test.go", '{"Mon 08:30", "line 1"},', '{"Mon 08:30 ok", "line 1"},'),
    ]
    return TLib(
        name="go-bells", lang="go", title="the Lowmoor bell-schedule resolver", blurb="The school's signage and the staff app both read the bell schedule through `bells`.",
        files=files, stub={"bells/smoke_test.go": BELLS_STUB}, gold={"bells/bells_gold_test.go": BELLS_TEST}, mutate=["bells/bells.go"], cmd="go test -count=1 ./...",
        where=WHERE_GO, difficulty=3, wrong_edits=wrong, timeout=60, focus="the weekday ranges that wrap over the weekend, dated entries replacing the recurring ones, time and syntax validation, and the 14-day horizon of Next",
    )
