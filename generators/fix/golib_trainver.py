"""Release-train versions (go): YY.MM.PATCH versions with beta/rc channels, month-aware constraints, support windows."""
from fx import Lib, dd, langs

from generators.fix._lang1 import gosrc, register_libs

README = dd('''
    # trainver

    The release manager of a monthly release train versions its builds `YY.MM.PATCH` (year, month, patch within the month) and the
    packaging tool selects builds with month-aware constraints.

    ## Versions
    `Version{Year, Month, Patch int; Channel Channel; Pre int}` with `Channel` one of `Beta`, `RC`, `Stable` (in that order of precedence).
    `ParseVersion(s string) (Version, error)` accepts `24.06.3` (stable) and `24.06.0-beta.2` / `24.06.0-rc.1` (`Pre` is the number after the
    dot). `YY` and `MM` are exactly two digits, `MM` is 01..12; the patch is a number without leading zeros; `Pre` is at least 1
    without leading zeros; a pre-release is only allowed with patch 0. Anything else is `ErrVersion`.

    * `(Version) String() string` is the inverse (`24.06.3`, `24.06.0-rc.1`).
    * `Compare(a, b Version) int` (-1, 0, 1): by year, month, patch; then by channel (`Beta < RC < Stable`); then by `Pre`.

    ## Constraints
    `ParseConstraint(s string) (Constraint, error)` and `(Constraint) Satisfies(v Version) bool`.
    A constraint is one or more *alternatives* separated by `|`; a version satisfies the constraint if it satisfies at least one alternative.
    An alternative is whitespace-separated *terms* that must all hold. The alternative `*` (or `x`) has no restriction. The term `pre` opts the
    alternative in to pre-releases: **without `pre` a Beta or RC never satisfies the alternative**, whatever its other terms say. Empty
    constraints, empty alternatives (also one that has no term besides `pre`), unknown terms and invalid versions are errors (`ErrSyntax`, or `ErrVersion` when a version inside a term is
    malformed).

    A *version operand* is `YY`, `YY.MM` (both "partial") or a full version (`YY.MM.P`, optionally with a `-beta.N` / `-rc.N` suffix; suffixes are
    only valid on full versions). A partial operand stands for a block of time: `YY.MM` is the whole month, `YY` the whole year. The first
    version of a block is its *floor*: `YY.MM.0-beta.1` (for `YY` the floor of January); the block ends right before the floor of the next month
    (next year). With operators:

    | term | meaning for a full version `V` | meaning for a partial block `B` |
    |---|---|---|
    | `>=X` | `v >= V` | `v >=` floor of `B` |
    | `>X` | `v > V` | `v >=` end of `B` (after the whole block) |
    | `<X` | `v < V` | `v <` floor of `B` |
    | `<=X` | `v <= V` | `v <` end of `B` (up to the end of the block) |
    | `=X` or `X` | `v == V` | `v` inside `B` |

    More terms: `YY.x`, `YY.*`, `YY.MM.x`, `YY.MM.*` (same as the partial operand); `~X` with `X = YY.MM` or `YY.MM.P`: at least X, within the same
    month (`~YY` is the same as `YY`); `^X` with `X = YY`, `YY.MM` or `YY.MM.P`: at least X (the floor for a partial one), within the same year; and
    `A..B`: from operand A (at least its floor, or the full version) up to operand B inclusive (whole block for a partial B, up to and including the
    version for a full B).

    ## Helpers
    * `Latest(c Constraint, versions []Version) (Version, bool)`: the highest version that satisfies `c`; `false` if none does.
    * `NextVersion(prev Version, year, month int) (Version, error)`: the version the release manager cuts in `(year, month)` after `prev`.
      `ErrBackwards` if that month is earlier than `prev`'s; `ErrVersion` if `year` is not 0..99 or `month` not 1..12. In the same month as a
      stable `prev` it is the next patch; in the same month as a pre-release it is the stable `YY.MM.0`; in a later month it is `YY.MM.0`.
    * `MonthsBehind(v, latest Version) int`: `12*(latest.Year - v.Year) + latest.Month - v.Month` (negative when `v` is newer).
    * `Supported(v, latest Version, window int) bool`: `v` is stable, not newer than `latest`, and at most `window` months behind it.
''')

SRC = gosrc(dd(r'''
    // Package trainver models monthly release-train versions and constraints.
    package trainver

    import (
        "errors"
        "fmt"
        "strconv"
        "strings"
    )

    var (
        ErrVersion   = errors.New("trainver: invalid version")
        ErrSyntax    = errors.New("trainver: invalid constraint")
        ErrBackwards = errors.New("trainver: month is before the previous release")
    )

    // Channel is the stability of a build.
    type Channel int

    const (
        Beta Channel = iota
        RC
        Stable
    )

    // Version is a train version.
    type Version struct {
        Year, Month, Patch int
        Channel            Channel
        Pre                int
    }

    func (v Version) String() string {
        s := fmt.Sprintf("%02d.%02d.%d", v.Year, v.Month, v.Patch)
        switch v.Channel {
        case Beta:
            s += fmt.Sprintf("-beta.%d", v.Pre)
        case RC:
            s += fmt.Sprintf("-rc.%d", v.Pre)
        }
        return s
    }

    // Compare orders two versions.
    func Compare(a, b Version) int {
        for _, d := range []int{a.Year - b.Year, a.Month - b.Month, a.Patch - b.Patch, int(a.Channel) - int(b.Channel), a.Pre - b.Pre} {
            if d < 0 {
                return -1
            }
            if d > 0 {
                return 1
            }
        }
        return 0
    }

    func number(s string, width int) (int, bool) {
        if s == "" || (width > 0 && len(s) != width) || (width == 0 && len(s) > 1 && s[0] == '0') {
            return 0, false
        }
        n, err := strconv.Atoi(s)
        if err != nil || n < 0 || strings.ContainsAny(s, "+-") {
            return 0, false
        }
        return n, true
    }

    // parseOperand reads YY, YY.MM or a full version; parts says which.
    func parseOperand(s string) (v Version, parts int, err error) {
        main, suffix, hasSuffix := strings.Cut(s, "-")
        f := strings.Split(main, ".")
        if len(f) < 1 || len(f) > 3 || (hasSuffix && len(f) != 3) {
            return v, 0, ErrVersion
        }
        yy, ok := number(f[0], 2)
        if !ok {
            return v, 0, ErrVersion
        }
        v = Version{Year: yy, Month: 1, Channel: Stable}
        parts = len(f)
        if parts >= 2 {
            mm, ok := number(f[1], 2)
            if !ok || mm < 1 || mm > 12 {
                return v, 0, ErrVersion
            }
            v.Month = mm
        }
        if parts == 3 {
            p, ok := number(f[2], 0)
            if !ok {
                return v, 0, ErrVersion
            }
            v.Patch = p
        }
        if hasSuffix {
            kind, num, ok := strings.Cut(suffix, ".")
            n, nok := number(num, 0)
            if !ok || !nok || n < 1 || v.Patch != 0 || (kind != "beta" && kind != "rc") {
                return v, 0, ErrVersion
            }
            v.Pre = n
            v.Channel = Beta
            if kind == "rc" {
                v.Channel = RC
            }
        }
        return v, parts, nil
    }

    // ParseVersion reads a full version.
    func ParseVersion(s string) (Version, error) {
        v, parts, err := parseOperand(s)
        if err != nil || parts != 3 {
            return Version{}, ErrVersion
        }
        return v, nil
    }

    func floor(y, m int) Version { return Version{Year: y, Month: m, Channel: Beta, Pre: 1} }

    // blockFloor and blockEnd bound a partial operand.
    func blockFloor(v Version, parts int) Version { return floor(v.Year, v.Month) }

    func blockEnd(v Version, parts int) Version {
        if parts == 1 {
            return floor(v.Year+1, 1)
        }
        if v.Month == 12 {
            return floor(v.Year+1, 1)
        }
        return floor(v.Year, v.Month+1)
    }

    type limit struct {
        v    Version
        incl bool
    }

    type term struct{ lo, hi *limit }

    func (t term) holds(v Version) bool {
        if t.lo != nil {
            if c := Compare(v, t.lo.v); c < 0 || (c == 0 && !t.lo.incl) {
                return false
            }
        }
        if t.hi != nil {
            if c := Compare(v, t.hi.v); c > 0 || (c == 0 && !t.hi.incl) {
                return false
            }
        }
        return true
    }

    type alternative struct {
        terms []term
        pre   bool
    }

    // Constraint is a parsed constraint.
    type Constraint struct{ alts []alternative }

    func lim(v Version, incl bool) *limit { return &limit{v, incl} }

    func parseTerm(tok string) (term, error) {
        for _, op := range []string{">=", "<=", ">", "<", "="} {
            if rest, ok := strings.CutPrefix(tok, op); ok {
                v, parts, err := parseOperand(rest)
                if err != nil {
                    return term{}, err
                }
                return opTerm(op, v, parts), nil
            }
        }
        if rest, ok := strings.CutPrefix(tok, "~"); ok {
            v, parts, err := parseOperand(rest)
            if err != nil {
                return term{}, err
            }
            if parts == 1 {
                return opTerm("=", v, parts), nil
            }
            lo := v
            if parts == 2 {
                lo = blockFloor(v, parts)
            }
            return term{lim(lo, true), lim(blockEnd(v, 2), false)}, nil
        }
        if rest, ok := strings.CutPrefix(tok, "^"); ok {
            v, parts, err := parseOperand(rest)
            if err != nil {
                return term{}, err
            }
            lo := v
            if parts < 3 {
                lo = blockFloor(v, parts)
            }
            return term{lim(lo, true), lim(blockEnd(v, 1), false)}, nil
        }
        if a, b, ok := strings.Cut(tok, ".."); ok {
            va, pa, err := parseOperand(a)
            if err != nil {
                return term{}, err
            }
            vb, pb, err := parseOperand(b)
            if err != nil {
                return term{}, err
            }
            t := opTerm(">=", va, pa)
            t.hi = opTerm("<=", vb, pb).hi
            return t, nil
        }
        for _, wild := range []string{".x", ".*"} {
            if rest, ok := strings.CutSuffix(tok, wild); ok {
                v, parts, err := parseOperand(rest)
                if err != nil || parts == 3 {
                    return term{}, ErrSyntax
                }
                return opTerm("=", v, parts), nil
            }
        }
        v, parts, err := parseOperand(tok)
        if err != nil {
            return term{}, err
        }
        return opTerm("=", v, parts), nil
    }

    func opTerm(op string, v Version, parts int) term {
        if parts == 3 {
            switch op {
            case ">=":
                return term{lo: lim(v, true)}
            case ">":
                return term{lo: lim(v, false)}
            case "<":
                return term{hi: lim(v, false)}
            case "<=":
                return term{hi: lim(v, true)}
            }
            return term{lim(v, true), lim(v, true)}
        }
        lo, end := blockFloor(v, parts), blockEnd(v, parts)
        switch op {
        case ">=":
            return term{lo: lim(lo, true)}
        case ">":
            return term{lo: lim(end, true)}
        case "<":
            return term{hi: lim(lo, false)}
        case "<=":
            return term{hi: lim(end, false)}
        }
        return term{lim(lo, true), lim(end, false)}
    }

    // ParseConstraint reads a constraint such as ">=24.03 <25 | 23.12.x".
    func ParseConstraint(s string) (Constraint, error) {
        var c Constraint
        for _, altText := range strings.Split(s, "|") {
            toks := strings.Fields(altText)
            if len(toks) == 0 {
                return Constraint{}, ErrSyntax
            }
            var alt alternative
            for _, tok := range toks {
                switch tok {
                case "pre":
                    alt.pre = true
                case "*", "x":
                    alt.terms = append(alt.terms, term{})
                default:
                    t, err := parseTerm(tok)
                    if err != nil {
                        return Constraint{}, err
                    }
                    alt.terms = append(alt.terms, t)
                }
            }
            if len(alt.terms) == 0 {
                return Constraint{}, ErrSyntax
            }
            c.alts = append(c.alts, alt)
        }
        return c, nil
    }

    // Satisfies reports whether v meets the constraint.
    func (c Constraint) Satisfies(v Version) bool {
        for _, alt := range c.alts {
            if v.Channel != Stable && !alt.pre {
                continue
            }
            ok := true
            for _, t := range alt.terms {
                if !t.holds(v) {
                    ok = false
                    break
                }
            }
            if ok {
                return true
            }
        }
        return false
    }

    // Latest picks the highest satisfying version.
    func Latest(c Constraint, versions []Version) (Version, bool) {
        var best Version
        found := false
        for _, v := range versions {
            if c.Satisfies(v) && (!found || Compare(v, best) > 0) {
                best, found = v, true
            }
        }
        return best, found
    }

    // NextVersion is the version cut in (year, month) after prev.
    func NextVersion(prev Version, year, month int) (Version, error) {
        if year < 0 || year > 99 || month < 1 || month > 12 {
            return Version{}, ErrVersion
        }
        if year < prev.Year || (year == prev.Year && month < prev.Month) {
            return Version{}, ErrBackwards
        }
        next := Version{Year: year, Month: month, Channel: Stable}
        if year == prev.Year && month == prev.Month && prev.Channel == Stable {
            next.Patch = prev.Patch + 1
        }
        return next, nil
    }

    // MonthsBehind counts months from v to latest.
    func MonthsBehind(v, latest Version) int {
        return 12*(latest.Year-v.Year) + latest.Month - v.Month
    }

    // Supported reports whether v is still inside the support window.
    func Supported(v, latest Version, window int) bool {
        return v.Channel == Stable && Compare(v, latest) <= 0 && MonthsBehind(v, latest) <= window
    }
'''))

VISIBLE = gosrc(dd(r'''
    package trainver

    import "testing"

    func TestParseAndPrint(t *testing.T) {
        v, err := ParseVersion("24.06.3")
        if err != nil || v.String() != "24.06.3" || v.Channel != Stable {
            t.Fatalf("got %+v, %v", v, err)
        }
    }

    func TestSimpleConstraint(t *testing.T) {
        c, err := ParseConstraint(">=24.03 <25")
        if err != nil {
            t.Fatal(err)
        }
        v, _ := ParseVersion("24.07.1")
        if !c.Satisfies(v) {
            t.Fatal("24.07.1 should satisfy >=24.03 <25")
        }
    }
'''))

HIDDEN = gosrc(dd(r'''
    package trainver

    import (
        "errors"
        "testing"
    )

    func ver(t *testing.T, s string) Version {
        t.Helper()
        v, err := ParseVersion(s)
        if err != nil {
            t.Fatalf("ParseVersion(%q): %v", s, err)
        }
        return v
    }

    func cons(t *testing.T, s string) Constraint {
        t.Helper()
        c, err := ParseConstraint(s)
        if err != nil {
            t.Fatalf("ParseConstraint(%q): %v", s, err)
        }
        return c
    }

    func TestParseVersionValid(t *testing.T) {
        cases := map[string]Version{
            "24.06.3":         {24, 6, 3, Stable, 0},
            "00.01.0":         {0, 1, 0, Stable, 0},
            "99.12.120":       {99, 12, 120, Stable, 0},
            "24.06.0-beta.2":  {24, 6, 0, Beta, 2},
            "24.06.0-rc.11":   {24, 6, 0, RC, 11},
            "25.01.0":         {25, 1, 0, Stable, 0},
            "24.11.10":        {24, 11, 10, Stable, 0},
        }
        for s, want := range cases {
            got, err := ParseVersion(s)
            if err != nil || got != want {
                t.Errorf("ParseVersion(%q) = %+v, %v; want %+v", s, got, err, want)
            }
            if got.String() != s {
                t.Errorf("String() of %q = %q", s, got.String())
            }
        }
    }

    func TestParseVersionInvalid(t *testing.T) {
        bad := []string{
            "", "24", "24.06", "24.06.", "24.6.0", "4.06.0", "024.06.0", "24.006.0", "24.00.0", "24.13.0", "24.06.03", "24.06.-1", "24.06.x",
            "24.06.0-beta", "24.06.0-beta.0", "24.06.0-beta.01", "24.06.1-beta.1", "24.06.0-alpha.1", "24.06.0-rc", "24.06.0-rc.", "24.06.0-RC.1",
            "24.06.0-rc.1-x", "24.06.0+build", " 24.06.0", "24.06.0 ", "24.06.0.1", "ab.06.0", "24.06.a", "+4.06.0", "24.+6.0", "24.06.0-beta.+1",
        }
        for _, s := range bad {
            if v, err := ParseVersion(s); !errors.Is(err, ErrVersion) {
                t.Errorf("ParseVersion(%q) = %+v, %v; want ErrVersion", s, v, err)
            }
        }
    }

    func TestCompare(t *testing.T) {
        order := []string{
            "23.12.9", "24.01.0-beta.1", "24.01.0-beta.2", "24.01.0-beta.10", "24.01.0-rc.1", "24.01.0-rc.2", "24.01.0", "24.01.1", "24.01.10",
            "24.02.0-beta.1", "24.02.0", "24.10.0", "25.01.0",
        }
        for i, a := range order {
            for j, b := range order {
                want := 0
                if i < j {
                    want = -1
                } else if i > j {
                    want = 1
                }
                if got := Compare(ver(t, a), ver(t, b)); got != want {
                    t.Errorf("Compare(%s, %s) = %d, want %d", a, b, got, want)
                }
            }
        }
    }

    func check(t *testing.T, constraint string, yes, no []string) {
        t.Helper()
        c := cons(t, constraint)
        for _, s := range yes {
            if !c.Satisfies(ver(t, s)) {
                t.Errorf("%q should accept %s", constraint, s)
            }
        }
        for _, s := range no {
            if c.Satisfies(ver(t, s)) {
                t.Errorf("%q should reject %s", constraint, s)
            }
        }
    }

    func TestFullOperators(t *testing.T) {
        check(t, ">=24.06.2", []string{"24.06.2", "24.06.3", "24.07.0", "25.01.0"}, []string{"24.06.1", "24.05.9", "23.12.0"})
        check(t, ">24.06.2", []string{"24.06.3", "24.07.0"}, []string{"24.06.2", "24.06.1"})
        check(t, "<24.06.2", []string{"24.06.1", "24.05.0"}, []string{"24.06.2", "24.06.3", "24.07.0"})
        check(t, "<=24.06.2", []string{"24.06.2", "24.06.1"}, []string{"24.06.3", "24.07.0"})
        check(t, "=24.06.2", []string{"24.06.2"}, []string{"24.06.1", "24.06.3"})
        check(t, "24.06.2", []string{"24.06.2"}, []string{"24.06.1", "24.06.3", "24.07.2"})
        check(t, ">=24.06.2 <24.08.0", []string{"24.06.2", "24.07.9"}, []string{"24.08.0", "24.06.1"})
    }

    func TestPartialOperands(t *testing.T) {
        check(t, ">=24.06", []string{"24.06.0", "24.06.4", "24.07.0", "25.03.0"}, []string{"24.05.9", "23.06.0"})
        check(t, ">24.06", []string{"24.07.0", "25.01.0"}, []string{"24.06.0", "24.06.7", "24.05.0"})
        check(t, "<24.06", []string{"24.05.7", "23.12.0"}, []string{"24.06.0", "24.06.1", "24.07.0"})
        check(t, "<=24.06", []string{"24.06.0", "24.06.9", "24.05.1"}, []string{"24.07.0", "25.01.0"})
        check(t, "=24.06", []string{"24.06.0", "24.06.12"}, []string{"24.05.9", "24.07.0"})
        check(t, "24.06", []string{"24.06.0", "24.06.12"}, []string{"24.05.9", "24.07.0"})
        check(t, ">=24", []string{"24.01.0", "30.01.0"}, []string{"23.12.9"})
        check(t, ">24", []string{"25.01.0"}, []string{"24.12.9", "24.01.0"})
        check(t, "<24", []string{"23.12.9", "00.01.0"}, []string{"24.01.0"})
        check(t, "<=24", []string{"24.12.9", "23.01.0"}, []string{"25.01.0"})
        check(t, "24", []string{"24.01.0", "24.12.9"}, []string{"23.12.9", "25.01.0"})
    }

    func TestDecemberRollsIntoNextYear(t *testing.T) {
        check(t, "=24.12", []string{"24.12.0", "24.12.5"}, []string{"25.01.0", "24.11.9"})
        check(t, "<=24.12", []string{"24.12.7"}, []string{"25.01.0"})
        check(t, ">24.12", []string{"25.01.0"}, []string{"24.12.7"})
        check(t, "~24.12.1", []string{"24.12.1", "24.12.9"}, []string{"25.01.0", "24.12.0"})
        check(t, "24.12.x", []string{"24.12.3"}, []string{"25.01.0"})
    }

    func TestWildcards(t *testing.T) {
        check(t, "24.x", []string{"24.01.0", "24.12.3"}, []string{"23.12.0", "25.01.0"})
        check(t, "24.*", []string{"24.06.0"}, []string{"25.06.0"})
        check(t, "24.06.x", []string{"24.06.0", "24.06.8"}, []string{"24.05.0", "24.07.0"})
        check(t, "24.06.*", []string{"24.06.2"}, []string{"24.07.2"})
        check(t, "*", []string{"00.01.0", "24.06.3", "99.12.9"}, nil)
        check(t, "x", []string{"24.06.3"}, nil)
    }

    func TestTildeAndCaret(t *testing.T) {
        check(t, "~24.06.2", []string{"24.06.2", "24.06.30"}, []string{"24.06.1", "24.07.0", "24.05.5"})
        check(t, "~24.06", []string{"24.06.0", "24.06.9"}, []string{"24.07.0", "24.05.9"})
        check(t, "~24", []string{"24.01.0", "24.12.9"}, []string{"25.01.0", "23.12.9"})
        check(t, "^24.06.2", []string{"24.06.2", "24.07.0", "24.12.9"}, []string{"24.06.1", "25.01.0", "24.05.9"})
        check(t, "^24.06", []string{"24.06.0", "24.09.1", "24.12.0"}, []string{"24.05.9", "25.01.0"})
        check(t, "^24", []string{"24.01.0", "24.12.5"}, []string{"23.12.9", "25.01.0"})
    }

    func TestRanges(t *testing.T) {
        check(t, "24.01..24.06", []string{"24.01.0", "24.03.4", "24.06.0", "24.06.9"}, []string{"23.12.9", "24.07.0"})
        check(t, "24.01.2..24.06.3", []string{"24.01.2", "24.06.3", "24.04.0"}, []string{"24.01.1", "24.06.4", "24.07.0"})
        check(t, "23..24", []string{"23.01.0", "24.12.9"}, []string{"22.12.0", "25.01.0"})
        check(t, "24.03..24.03.5", []string{"24.03.0", "24.03.5"}, []string{"24.03.6", "24.02.9"})
        check(t, "24.03.2..24.04", []string{"24.03.2", "24.04.9"}, []string{"24.03.1", "24.05.0"})
        check(t, "23.11..24.02", []string{"23.12.0", "24.01.5", "24.02.1"}, []string{"23.10.9", "24.03.0"})
    }

    func TestAlternativesAndAnd(t *testing.T) {
        check(t, "24.06.x | 24.09.x", []string{"24.06.1", "24.09.0"}, []string{"24.07.0", "24.10.0"})
        check(t, ">=24.03 <24.06 | >=24.09", []string{"24.03.0", "24.05.9", "24.09.0", "25.01.0"}, []string{"24.06.0", "24.08.9", "24.02.0"})
        check(t, "  >=24.03    <24.06  ", []string{"24.04.0"}, []string{"24.06.0"})
        check(t, ">=24.03 <24.01", nil, []string{"24.03.0", "24.02.0", "23.01.0"})
        check(t, "24.06.x|24.07.x|24.08.x", []string{"24.07.2"}, []string{"24.09.0"})
    }

    func TestPrereleasesNeedOptIn(t *testing.T) {
        check(t, ">=24.01", []string{"24.01.0"}, []string{"24.01.0-beta.1", "24.01.0-rc.1", "24.05.0-rc.2"})
        check(t, "*", []string{"24.01.0"}, []string{"24.01.0-beta.1"})
        check(t, "24.06.x", []string{"24.06.0"}, []string{"24.06.0-rc.1"})
        check(t, ">=24.06 pre", []string{"24.06.0-beta.1", "24.06.0-rc.1", "24.06.0", "24.07.0-beta.3"}, []string{"24.05.0-rc.1", "24.05.9"})
        check(t, "24.06 pre", []string{"24.06.0-beta.1", "24.06.0-rc.2", "24.06.2"}, []string{"24.07.0-beta.1", "24.05.0-rc.1"})
        check(t, "pre >=24.06.0-rc.1 <24.07", []string{"24.06.0-rc.1", "24.06.0-rc.5", "24.06.0", "24.06.1"}, []string{"24.06.0-beta.9", "24.07.0-beta.1"})
        check(t, "pre *", []string{"24.06.0-beta.1", "24.06.0"}, nil)
        // the opt-in belongs to one alternative only
        check(t, "24.06 pre | 24.07", []string{"24.06.0-rc.1", "24.07.1"}, []string{"24.07.0-rc.1"})
        // exact prerelease versions
        check(t, "=24.06.0-rc.1 pre", []string{"24.06.0-rc.1"}, []string{"24.06.0-rc.2", "24.06.0"})
        check(t, ">24.06.0-rc.1 pre", []string{"24.06.0-rc.2", "24.06.0"}, []string{"24.06.0-rc.1", "24.06.0-beta.3"})
    }

    func TestBlockFloorIsTheFirstBeta(t *testing.T) {
        // "<24.06" must not admit 24.06.0-beta.1 even with pre; ">=24.06" must admit it
        check(t, "<24.06 pre", []string{"24.05.0-rc.3", "24.05.4"}, []string{"24.06.0-beta.1", "24.06.0"})
        check(t, ">=24.06 pre", []string{"24.06.0-beta.1"}, []string{"24.05.9"})
        check(t, ">24.06 pre", []string{"24.07.0-beta.1"}, []string{"24.06.0-rc.1", "24.06.3"})
        check(t, "<=24.06 pre", []string{"24.06.0-rc.1", "24.06.9"}, []string{"24.07.0-beta.1"})
        // tilde and caret blocks start at the floor too, and end right before the next month / year
        check(t, "pre ~24.06", []string{"24.06.0-beta.1", "24.06.0-rc.2", "24.06.7"}, []string{"24.05.9", "24.07.0-beta.1"})
        check(t, "pre ~24", []string{"24.01.0-beta.1", "24.12.0-rc.1"}, []string{"23.12.9", "25.01.0-beta.1"})
        check(t, "pre ^24.06", []string{"24.06.0-beta.1", "24.12.3"}, []string{"24.05.9", "25.01.0-beta.1"})
        check(t, "pre ^24", []string{"24.01.0-beta.1", "24.12.3"}, []string{"23.12.9", "25.01.0-beta.1"})
        check(t, "pre ^24.06.2", []string{"24.06.2", "24.12.3"}, []string{"24.06.1", "25.01.0-beta.1"})
    }

    func TestConstraintErrors(t *testing.T) {
        syntax := []string{"", "   ", "|", "24.06 |", "| 24.06", "24.06 || 24.07", "pre", "24.06.x.x", "24.06.0.x", "~", "^", ">=", "..", "24.06..", "..24.06", "foo", "24.06,24.07"}
        for _, s := range syntax {
            if c, err := ParseConstraint(s); err == nil {
                t.Errorf("ParseConstraint(%q) = %+v, want an error", s, c)
            }
        }
        versions := []string{">=24.13", ">=24.6", "<24.06.03", "=24.06.0-gamma.1", "~24.06.0-rc", "^4", "24.00.x", "1.x", ">=24.06.0-beta.0", "24.06..24.13", "24.06.1-rc.1", ">=24.06.0.1", "=24.06.0.1.2", "~24.06.0.1", "^24.06.0.1", "24.06.0.1", "24.06.0.1..24.07"}
        for _, s := range versions {
            if _, err := ParseConstraint(s); !errors.Is(err, ErrVersion) && !errors.Is(err, ErrSyntax) {
                t.Errorf("ParseConstraint(%q): err = %v", s, err)
            }
            if _, err := ParseConstraint(s); err == nil {
                t.Errorf("ParseConstraint(%q) should fail", s)
            }
        }
        if _, err := ParseConstraint(">=24.13"); !errors.Is(err, ErrVersion) {
            t.Errorf(">=24.13: %v", err)
        }
        if _, err := ParseConstraint("24.06 | foo"); err == nil {
            t.Errorf("second alternative must be checked")
        }
        if _, err := ParseConstraint("24.06 |  "); !errors.Is(err, ErrSyntax) {
            t.Errorf("empty alternative: %v", err)
        }
    }

    func TestLatest(t *testing.T) {
        var vs []Version
        for _, s := range []string{"24.01.0", "24.01.3", "24.02.0-beta.1", "24.02.0-rc.2", "24.02.0", "24.02.1", "24.03.0-rc.1", "23.12.5", "24.02.10"} {
            vs = append(vs, ver(t, s))
        }
        cases := []struct {
            c    string
            want string
            ok   bool
        }{
            {"*", "24.02.10", true},
            {"24.01.x", "24.01.3", true},
            {"<24.02", "24.01.3", true},
            {"~24.02.1", "24.02.10", true},
            {"* pre", "24.03.0-rc.1", true},
            {"24.02 pre", "24.02.10", true},
            {"<=24.02.0 pre", "24.02.0", true},
            {"<24.02.0 pre", "24.02.0-rc.2", true},
            {">=25", "", false},
            {"24.04.x", "", false},
        }
        for _, c := range cases {
            got, ok := Latest(cons(t, c.c), vs)
            if ok != c.ok || (ok && got.String() != c.want) {
                t.Errorf("Latest(%q) = %v, %v; want %s, %v", c.c, got, ok, c.want, c.ok)
            }
        }
        if _, ok := Latest(cons(t, "*"), nil); ok {
            t.Errorf("empty list")
        }
        // order of the input does not matter
        rev := make([]Version, len(vs))
        for i, v := range vs {
            rev[len(vs)-1-i] = v
        }
        if got, _ := Latest(cons(t, "*"), rev); got.String() != "24.02.10" {
            t.Errorf("reversed input: %v", got)
        }
    }

    func TestNextVersion(t *testing.T) {
        cases := []struct {
            prev        string
            year, month int
            want        string
        }{
            {"24.06.0", 24, 6, "24.06.1"},
            {"24.06.3", 24, 6, "24.06.4"},
            {"24.06.9", 24, 7, "24.07.0"},
            {"24.12.2", 25, 1, "25.01.0"},
            {"24.06.0", 25, 3, "25.03.0"},
            {"24.06.0-rc.2", 24, 6, "24.06.0"},
            {"24.06.0-beta.1", 24, 6, "24.06.0"},
            {"24.06.0-rc.2", 24, 7, "24.07.0"},
            {"99.11.4", 99, 12, "99.12.0"},
        }
        for _, c := range cases {
            got, err := NextVersion(ver(t, c.prev), c.year, c.month)
            if err != nil || got.String() != c.want {
                t.Errorf("NextVersion(%s, %d, %d) = %v, %v; want %s", c.prev, c.year, c.month, got, err, c.want)
            }
        }
    }

    func TestNextVersionErrors(t *testing.T) {
        prev := ver(t, "24.06.3")
        for _, c := range [][2]int{{24, 5}, {23, 12}, {23, 7}, {0, 1}} {
            if got, err := NextVersion(prev, c[0], c[1]); !errors.Is(err, ErrBackwards) {
                t.Errorf("NextVersion(%d, %d) = %v, %v", c[0], c[1], got, err)
            }
        }
        for _, c := range [][2]int{{24, 0}, {24, 13}, {-1, 6}, {100, 1}, {100, 13}} {
            if got, err := NextVersion(prev, c[0], c[1]); !errors.Is(err, ErrVersion) {
                t.Errorf("NextVersion(%d, %d) = %v, %v", c[0], c[1], got, err)
            }
        }
        // the range check comes first
        if _, err := NextVersion(prev, 23, 13); !errors.Is(err, ErrVersion) {
            t.Errorf("range before order: %v", err)
        }
    }

    func TestMonthsBehindAndSupported(t *testing.T) {
        latest := ver(t, "24.06.2")
        cases := []struct {
            v      string
            behind int
        }{
            {"24.06.0", 0}, {"24.05.9", 1}, {"24.01.0", 5}, {"23.12.0", 6}, {"23.06.1", 12}, {"22.01.0", 29}, {"24.07.0", -1}, {"25.06.0", -12},
        }
        for _, c := range cases {
            if got := MonthsBehind(ver(t, c.v), latest); got != c.behind {
                t.Errorf("MonthsBehind(%s) = %d, want %d", c.v, got, c.behind)
            }
        }
        sup := []struct {
            v      string
            window int
            want   bool
        }{
            {"24.06.2", 0, true}, {"24.06.0", 0, true}, {"24.05.0", 0, false}, {"24.05.0", 1, true}, {"24.03.5", 3, true}, {"24.03.5", 2, false},
            {"23.12.0", 6, true}, {"23.12.0", 5, false}, {"24.06.3", 12, false}, {"24.07.0", 12, false}, {"24.06.0-rc.1", 12, false},
            {"24.05.0-beta.1", 12, false},
        }
        for _, c := range sup {
            if got := Supported(ver(t, c.v), latest, c.window); got != c.want {
                t.Errorf("Supported(%s, window %d) = %v, want %v", c.v, c.window, got, c.want)
            }
        }
    }
'''))

LIB = Lib(
    name="trainver", lang="go", title="the trainver package",
    blurb="The packaging tool picks builds of a monthly release train with trainver, which parses YY.MM.PATCH versions and month-aware constraints.",
    files={"go.mod": langs.go_mod("trainver", "1.22"), "trainver.go": SRC, "README.md": README},
    visible_tests={"trainver_basic_test.go": VISIBLE},
    hidden_tests={"trainver_full_test.go": HIDDEN},
    mutate=["trainver.go"], difficulty=4, tags=["versions", "constraints", "calendar"],
)

register_libs([LIB], n=8)
