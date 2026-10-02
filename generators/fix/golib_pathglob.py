"""Path globs and rule lists (go): wildcards, sets, brace alternatives, floating patterns, last-match-wins rules."""
from fx import Lib, dd, langs

from generators.fix._lang1 import gosrc, register_libs

README = dd(r'''
    # pathglob

    Path patterns for the build tool's file filters: glob matching on slash-separated paths, and ordered include/exclude
    rule lists. Paths are plain strings (`src/lib/util.go`); this package never touches the file system.

    ## Pattern syntax
    * `*` matches any run of characters (including none) inside one path segment; `?` matches exactly one character
      (a Unicode code point, not a byte).
    * `[abc]`, `[a-f]`, `[!a-f]`: one character from a set; `!` right after `[` negates it. `-` between two characters is a
      range (the first must not be larger than the second), `-` first or last is literal. `]` ends the set, so a set must
      have at least one member. `\x` inside a set is the literal `x` (also as a range end).
    * `\x` outside a set: the literal character `x`.
    * A segment that is exactly `**` matches zero or more whole segments, so `src/**` matches `src` itself and everything
      under it, and `a/**/b` matches `a/b`, `a/x/b`, `a/x/y/b`. `**` inside a longer segment (`a**b`) is just two `*`.
    * `{a,b,c}` alternatives, which may be empty (`a{,b}c` is `ac` or `abc`), contain wildcards and sets, and may occur
      several times in a pattern (`{a,b}{1,2}`). Braces do not nest. `\{`, `\,` and `\}` are literal; a lone `}` or `,`
      outside a group is literal too. A pattern may expand to at most 64 alternatives.

    ## `Match(pattern, path string) (bool, error)`
    Empty segments are ignored in both (`a//b` is `a/b`, leading and trailing `/` do not matter). A *floating* pattern - one
    segment after dropping empties and no leading `/` - is compared with the **last segment of the path** only, at any depth
    (`*.go` matches `cmd/main.go`). Every other pattern must match the whole path from the root, segment by segment
    (`/main.go` matches `main.go` but not `cmd/main.go`). A path with no segments never matches a floating pattern; the empty
    pattern matches only the empty path.

    Syntax problems are `ErrBadPattern`, reported for the whole pattern even when it would not match, in any alternative:
    an unclosed `[`, an empty set (`[]`, `[!]`), a reversed range (`[b-a]`), a trailing `\`, an unclosed or nested `{`, more than
    64 alternatives.

    ## `Literal(pattern string) string`
    The directory a walker can start in: the leading segments of the pattern (empty segments dropped) that contain none
    of `* ? [ { \`, **not counting the final segment**, joined with `/`. `src/lib/**/*.go` gives `src/lib`, `*.go` gives
    the empty string, `a/b/c.go` gives `a/b`, `/a/b` gives `a`.

    ## Rule lists
    `ParseRules(text string) ([]Rule, error)` reads one rule per line, `Rule{Include bool; Pattern string}`:
    `+ <pattern>` includes, `- <pattern>` excludes. The sign must be followed by a space; surrounding whitespace on a line
    (including `\r`) is ignored; blank lines and lines starting with `#` are skipped. Anything else - a missing sign or
    space, an empty pattern, a pattern that is an `ErrBadPattern` - gives an error wrapping `ErrBadRule` whose text contains
    `line N` (1-based, counting skipped lines).

    `Allowed(rules []Rule, path string) (bool, error)`: the **last** rule whose pattern matches `path` decides; with no
    matching rule the path is not allowed. A pattern error in a hand-built rule is returned.
''')

SRC = gosrc(dd(r'''
    // Package pathglob matches slash-separated paths against glob patterns and rule lists.
    package pathglob

    import (
        "errors"
        "fmt"
        "strings"
    )

    var (
        ErrBadPattern = errors.New("pathglob: bad pattern")
        ErrBadRule    = errors.New("pathglob: bad rule")
    )

    const maxAlternatives = 64

    // expand resolves {a,b} groups (no nesting) into plain patterns.
    func expand(p string) ([]string, error) {
        start, end := -1, -1
        var cuts []int
        inSet := false
        for i := 0; i < len(p) && end < 0; i++ {
            c := p[i]
            switch {
            case c == '\\':
                i++
            case inSet:
                inSet = c != ']'
            case c == '[':
                inSet = true
            case c == '{':
                if start >= 0 {
                    return nil, ErrBadPattern
                }
                start = i
            case c == ',' && start >= 0:
                cuts = append(cuts, i)
            case c == '}' && start >= 0:
                end = i
            }
        }
        if start < 0 {
            return []string{p}, nil
        }
        if end < 0 {
            return nil, ErrBadPattern
        }
        bounds := append(append([]int{start}, cuts...), end)
        var out []string
        for k := 0; k+1 < len(bounds); k++ {
            alt := p[bounds[k]+1 : bounds[k+1]]
            sub, err := expand(p[:start] + alt + p[end+1:])
            if err != nil {
                return nil, err
            }
            out = append(out, sub...)
            if len(out) > maxAlternatives {
                return nil, ErrBadPattern
            }
        }
        return out, nil
    }

    type span struct{ lo, hi rune }

    // parseSet reads a [...] set at the start of p and returns the rest of the pattern.
    func parseSet(p []rune) (neg bool, spans []span, rest []rune, err error) {
        i := 1
        if i < len(p) && p[i] == '!' {
            neg = true
            i++
        }
        read := func() (rune, bool) {
            if i >= len(p) {
                return 0, false
            }
            c := p[i]
            i++
            if c == '\\' {
                if i >= len(p) {
                    return 0, false
                }
                c = p[i]
                i++
            }
            return c, true
        }
        for {
            if i >= len(p) {
                return false, nil, nil, ErrBadPattern
            }
            if p[i] == ']' {
                if len(spans) == 0 {
                    return false, nil, nil, ErrBadPattern
                }
                return neg, spans, p[i+1:], nil
            }
            lo, ok := read()
            if !ok {
                return false, nil, nil, ErrBadPattern
            }
            hi := lo
            if i+1 < len(p) && p[i] == '-' && p[i+1] != ']' {
                i++
                if hi, ok = read(); !ok || hi < lo {
                    return false, nil, nil, ErrBadPattern
                }
            }
            spans = append(spans, span{lo, hi})
        }
    }

    // validate checks the syntax of an expanded pattern.
    func validate(p []rune) error {
        for i := 0; i < len(p); {
            switch p[i] {
            case '\\':
                if i+1 >= len(p) {
                    return ErrBadPattern
                }
                i += 2
            case '[':
                _, _, rest, err := parseSet(p[i:])
                if err != nil {
                    return err
                }
                i = len(p) - len(rest)
            default:
                i++
            }
        }
        return nil
    }

    // matchSeg matches one pattern segment against one path segment.
    func matchSeg(p, s []rune) bool {
        for len(p) > 0 {
            switch p[0] {
            case '*':
                for len(p) > 0 && p[0] == '*' {
                    p = p[1:]
                }
                if len(p) == 0 {
                    return true
                }
                for i := 0; i <= len(s); i++ {
                    if matchSeg(p, s[i:]) {
                        return true
                    }
                }
                return false
            case '?':
                if len(s) == 0 {
                    return false
                }
                p, s = p[1:], s[1:]
            case '[':
                if len(s) == 0 {
                    return false
                }
                neg, spans, rest, _ := parseSet(p)
                in := false
                for _, sp := range spans {
                    if s[0] >= sp.lo && s[0] <= sp.hi {
                        in = true
                    }
                }
                if in == neg {
                    return false
                }
                p, s = rest, s[1:]
            case '\\':
                if len(s) == 0 || s[0] != p[1] {
                    return false
                }
                p, s = p[2:], s[1:]
            default:
                if len(s) == 0 || s[0] != p[0] {
                    return false
                }
                p, s = p[1:], s[1:]
            }
        }
        return len(s) == 0
    }

    func matchSegs(pat, path []string) bool {
        for len(pat) > 0 {
            if pat[0] == "**" {
                for len(pat) > 0 && pat[0] == "**" {
                    pat = pat[1:]
                }
                if len(pat) == 0 {
                    return true
                }
                for i := 0; i <= len(path); i++ {
                    if matchSegs(pat, path[i:]) {
                        return true
                    }
                }
                return false
            }
            if len(path) == 0 || !matchSeg([]rune(pat[0]), []rune(path[0])) {
                return false
            }
            pat, path = pat[1:], path[1:]
        }
        return len(path) == 0
    }

    func splitPath(p string) []string {
        var out []string
        for _, s := range strings.Split(p, "/") {
            if s != "" {
                out = append(out, s)
            }
        }
        return out
    }

    // Match reports whether path matches the glob pattern.
    func Match(pattern, path string) (bool, error) {
        alts, err := expand(pattern)
        if err != nil {
            return false, err
        }
        for _, a := range alts {
            if err := validate([]rune(a)); err != nil {
                return false, err
            }
        }
        segs := splitPath(path)
        for _, a := range alts {
            ps := splitPath(a)
            floating := len(ps) == 1 && !strings.HasPrefix(a, "/")
            var ok bool
            if floating {
                ok = len(segs) > 0 && matchSeg([]rune(ps[0]), []rune(segs[len(segs)-1]))
            } else {
                ok = matchSegs(ps, segs)
            }
            if ok {
                return true, nil
            }
        }
        return false, nil
    }

    // Literal is the longest directory prefix of the pattern without wildcards.
    func Literal(pattern string) string {
        segs := splitPath(pattern)
        var out []string
        for i := 0; i < len(segs)-1; i++ {
            if strings.ContainsAny(segs[i], "*?[{\\") {
                break
            }
            out = append(out, segs[i])
        }
        return strings.Join(out, "/")
    }

    // Rule is one include or exclude line.
    type Rule struct {
        Include bool
        Pattern string
    }

    // ParseRules reads a rule list.
    func ParseRules(text string) ([]Rule, error) {
        var rules []Rule
        for n, line := range strings.Split(text, "\n") {
            line = strings.TrimSpace(line)
            if line == "" || strings.HasPrefix(line, "#") {
                continue
            }
            if len(line) < 3 || (line[0] != '+' && line[0] != '-') || line[1] != ' ' {
                return nil, fmt.Errorf("line %d: %w", n+1, ErrBadRule)
            }
            pat := strings.TrimSpace(line[2:])
            if _, err := Match(pat, ""); err != nil {
                return nil, fmt.Errorf("line %d: %w", n+1, ErrBadRule)
            }
            rules = append(rules, Rule{Include: line[0] == '+', Pattern: pat})
        }
        return rules, nil
    }

    // Allowed applies the rules: the last matching one decides, no match means no.
    func Allowed(rules []Rule, path string) (bool, error) {
        allowed := false
        for _, r := range rules {
            ok, err := Match(r.Pattern, path)
            if err != nil {
                return false, err
            }
            if ok {
                allowed = r.Include
            }
        }
        return allowed, nil
    }
'''))

VISIBLE = gosrc(dd(r'''
    package pathglob

    import "testing"

    func TestStarFloats(t *testing.T) {
        ok, err := Match("*.go", "cmd/main.go")
        if err != nil || !ok {
            t.Fatalf("got %v, %v", ok, err)
        }
    }

    func TestDoubleStar(t *testing.T) {
        ok, _ := Match("src/**/test", "src/a/b/test")
        if !ok {
            t.Fatal("src/**/test should match src/a/b/test")
        }
    }
'''))

CASES = '''
    {"*.go", "main.go", true},
    {"*.go", "cmd/main.go", true},
    {"*.go", "main.rs", false},
    {"*.go", ".go", true},
    {"*.go", "a.go/", true},
    {"*.go", "a.go/b.txt", false},
    {"main.go", "cmd/x/main.go", true},
    {"/main.go", "main.go", true},
    {"/main.go", "cmd/main.go", false},
    {"cmd/main.go", "cmd/main.go", true},
    {"cmd/main.go", "x/cmd/main.go", false},
    {"src/**", "src", true},
    {"src/**", "src/a", true},
    {"src/**", "src/a/b/c", true},
    {"src/**", "other/src/a", false},
    {"**/*.go", "a.go", true},
    {"**/*.go", "a/b/c.go", true},
    {"**/*.go", "a/b/c.rs", false},
    {"src/**/test", "src/test", true},
    {"src/**/test", "src/a/test", true},
    {"src/**/test", "src/a/b/test", true},
    {"src/**/test", "src/a/b/tes", false},
    {"src/**/test", "src/test/x", false},
    {"a/**/**/b", "a/b", true},
    {"a/**/**/b", "a/x/y/b", true},
    {"**", "anything/at/all", true},
    {"**", "x", true},
    {"**", "", false},
    {"a/*/c", "a/b/c", true},
    {"a/*/c", "a/c", false},
    {"a/*/c", "a/b/d/c", false},
    {"a/*", "a/", false},
    {"a/*", "a", false},
    {"f?le.txt", "file.txt", true},
    {"f?le.txt", "fle.txt", false},
    {"f?le.txt", "fiile.txt", false},
    {"?", "é", true},
    {"??", "é", false},
    {"?.go", "é.go", true},
    {"[abc].txt", "a.txt", true},
    {"[abc].txt", "d.txt", false},
    {"[a-c].txt", "b.txt", true},
    {"[a-c].txt", "d.txt", false},
    {"[!a-c].txt", "d.txt", true},
    {"[!a-c].txt", "b.txt", false},
    {"[-a].txt", "-.txt", true},
    {"[a-].txt", "-.txt", true},
    {"[a-].txt", "a.txt", true},
    {"[a-].txt", "b.txt", false},
    {"[\\\\]].txt", "].txt", true},
    {"[a\\\\-c].txt", "-.txt", true},
    {"[a\\\\-c].txt", "b.txt", false},
    {"{a,b}.txt", "a.txt", true},
    {"{a,b}.txt", "b.txt", true},
    {"{a,b}.txt", "c.txt", false},
    {"a{,b}c", "ac", true},
    {"a{,b}c", "abc", true},
    {"a{,b}c", "abbc", false},
    {"src/{lib,cmd}/*.go", "src/lib/x.go", true},
    {"src/{lib,cmd}/*.go", "src/cmd/x.go", true},
    {"src/{lib,cmd}/*.go", "src/pkg/x.go", false},
    {"{a,b}{1,2}", "a1", true},
    {"{a,b}{1,2}", "b2", true},
    {"{a,b}{1,2}", "a3", false},
    {"*.{go,rs}", "x.rs", true},
    {"*.{go,rs}", "x.py", false},
    {"{x}", "x", true},
    {"{*.go,*.rs}", "m.rs", true},
    {"{a,[bc]}", "c", true},
    {"{a,[,]}", ",", true},
    {"a\\\\{b", "a{b", true},
    {"a\\\\,b", "a,b", true},
    {"{a\\\\,b,c}", "a,b", true},
    {"{a\\\\,b,c}", "a", false},
    {"a*b", "ab", true},
    {"a*b", "axxb", true},
    {"a*b", "axxbx", false},
    {"a*b*c", "aXbYc", true},
    {"a**b", "aXb", true},
    {"a**b", "a/b", false},
    {"*a*", "bab", true},
    {"*", "/", false},
    {"*", "", false},
    {"\\\\*", "*", true},
    {"\\\\*", "a", false},
    {"\\\\?x", "?x", true},
    {"a\\\\b", "ab", true},
    {"*/*", "a/b", true},
    {"*/*", "a/b/c", false},
    {"*/*", "a", false},
    {"/*/*", "a/b", true},
    {"*/", "a", true},
    {"*/", "x/a", true},
    {"a//b", "a/b", true},
    {"a/b", "a//b", true},
    {"a/b", "/a/b/", true},
    {"/a", "a", true},
    {"a/", "a", true},
    {"a/", "x/a", true},
    {"日本*", "日本語", true},
    {"*語", "日本語", true},
    {"日?語", "日本語", true},
    {"[あ-ん]", "か", true},
    {"[あ-ん]", "a", false},
    {"{a,[x,y]}", "y", true},
    {"{a,[x,y]}", ",", true},
    {"{a,[x,y]}", "b", false},
    {"{[ab],[cd]}", "d", true},
    {"a[bc]", "a", false},
    {"x?", "x", false},
    {"a*[bc]", "a", false},
    {"[a-c]?", "b", false},
    {"", "", true},
    {"", "a", false},
    {"/", "", true},
    {"/", "a", false},
'''.strip("\n")

HIDDEN = gosrc(dd(r'''
    package pathglob

    import (
        "errors"
        "strings"
        "testing"
    )

    var matchCases = []struct {
        pattern, path string
        want          bool
    }{
    ''') + CASES + "\n" + dd(r'''
    }

    func TestMatchTable(t *testing.T) {
        for _, c := range matchCases {
            got, err := Match(c.pattern, c.path)
            if err != nil || got != c.want {
                t.Errorf("Match(%q, %q) = %v, %v; want %v", c.pattern, c.path, got, err, c.want)
            }
        }
    }

    func TestBadPatterns(t *testing.T) {
        bad := []string{
            "[!]a]", "[", "[a", "[]", "[!]", "a[]b", "[b-a]", "\\", "a\\", "{a", "{a,b", "{a,{b,c}}", "{{a}}", "[a-", "[a\\",
            "a{b", "{[a,b}", "{a,b}}[", "x/[", "[/", "x/{a,b", "{a,[}",
            "\\a[", "x\\*[", "\\[[", "{a,b}{c", "{a,b}{c,{d,e}}", "{a}{b,{c}}",
        }
        for _, p := range bad {
            for _, path := range []string{"x", "", "a/b"} {
                if got, err := Match(p, path); !errors.Is(err, ErrBadPattern) || got {
                    t.Errorf("Match(%q, %q) = %v, %v; want ErrBadPattern", p, path, got, err)
                }
            }
        }
    }

    func TestErrorsInLaterAlternativesAreReported(t *testing.T) {
        // the first alternative matches, the second is broken: still an error
        if got, err := Match("{x,[}", "x"); !errors.Is(err, ErrBadPattern) || got {
            t.Errorf("got %v, %v", got, err)
        }
        if got, err := Match("{x,y\\}", "x"); !errors.Is(err, ErrBadPattern) || got {
            t.Errorf("got %v, %v", got, err)
        }
        // an early mismatch does not hide a syntax error further right
        if _, err := Match("a[", "b"); !errors.Is(err, ErrBadPattern) {
            t.Errorf("a[ vs b: %v", err)
        }
        if _, err := Match("a/b/[x-", "z"); !errors.Is(err, ErrBadPattern) {
            t.Errorf("late error: %v", err)
        }
    }

    func TestAlternativeLimit(t *testing.T) {
        six := strings.Repeat("{a,b}", 6)
        if got, err := Match(six, "aaaaaa"); err != nil || !got {
            t.Errorf("64 alternatives: %v, %v", got, err)
        }
        if got, err := Match(six, "ababab"); err != nil || !got {
            t.Errorf("64 alternatives: %v, %v", got, err)
        }
        sixtyFour := "{1,2,3,4}{a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p}"
        if got, err := Match(sixtyFour, "4p"); err != nil || !got {
            t.Errorf("4x16 alternatives: %v, %v", got, err)
        }
        sixtyFive := "{1,2,3,4,5}{a,b,c,d,e,f,g,h,i,j,k,l,m}"
        if _, err := Match(sixtyFive, "5m"); !errors.Is(err, ErrBadPattern) {
            t.Errorf("5x13 alternatives: %v", err)
        }
        seven := strings.Repeat("{a,b}", 7)
        if _, err := Match(seven, "aaaaaaa"); !errors.Is(err, ErrBadPattern) {
            t.Errorf("128 alternatives: %v", err)
        }
        if _, err := Match("{a,b}{a,b}{a,b}{a,b}{a,b}{a,b,c}", "aaaaaa"); !errors.Is(err, ErrBadPattern) {
            t.Errorf("96 alternatives: %v", err)
        }
    }

    func TestSetsRangesAndEscapes(t *testing.T) {
        cases := []struct {
            pattern, path string
            want          bool
        }{
            {"[a-cx-z]", "y", true},
            {"[a-cx-z]", "m", false},
            {"[a-cx-z]", "c", true},
            {"[a-cx-z]", "a", true},
            {"[a-cx-z]", "x", true},
            {"[a-cx-z]", "z", true},
            {"[!a-cx-z]", "m", true},
            {"[!a-cx-z]", "y", false},
            {"[a-a]", "a", true},
            {"[!!]", "!", false},
            {"[!!]", "?", true},
        }
        for _, c := range cases {
            got, err := Match(c.pattern, c.path)
            if err != nil || got != c.want {
                t.Errorf("Match(%q, %q) = %v, %v; want %v", c.pattern, c.path, got, err, c.want)
            }
        }
    }

    func TestSetsMatchWholeRunes(t *testing.T) {
        for pat, path := range map[string]string{"[é]": "é", "[à-ü]": "é", "[!a]": "é", "a[é-ë]b": "aêb"} {
            if got, err := Match(pat, path); err != nil || !got {
                t.Errorf("Match(%q, %q) = %v, %v", pat, path, got, err)
            }
        }
        if got, _ := Match("[é]", "e"); got {
            t.Errorf("[é] matched e")
        }
        if got, _ := Match("?", "日"); !got {
            t.Errorf("? should match one code point")
        }
        if got, _ := Match("??", "日本"); !got {
            t.Errorf("?? should match two code points")
        }
    }

    func TestStarDoesNotCrossSlash(t *testing.T) {
        if got, _ := Match("a/*", "a/b/c"); got {
            t.Errorf("a/* matched a/b/c")
        }
        if got, _ := Match("a/*c", "a/b/c"); got {
            t.Errorf("a/*c matched a/b/c")
        }
        if got, _ := Match("a/?", "a/bc"); got {
            t.Errorf("a/? matched a/bc")
        }
        if got, _ := Match("a/[bc]", "a/b/c"); got {
            t.Errorf("a/[bc] matched a/b/c")
        }
        if got, _ := Match("a/{b,c}", "a/b/c"); got {
            t.Errorf("a/{b,c} matched a/b/c")
        }
    }

    func TestDoubleStarVariants(t *testing.T) {
        cases := []struct {
            pattern, path string
            want          bool
        }{
            {"**/a/**", "a", true},
            {"**/a/**", "x/y/a/z", true},
            {"**/a/**", "x/y/b/z", false},
            {"/**/a", "a", true},
            {"/**/a", "x/a", true},
            {"x/**/y/**/z", "x/y/z", true},
            {"x/**/y/**/z", "x/a/y/b/z", true},
            {"x/**/y/**/z", "x/a/b/z", false},
            {"x/**/y/**/z", "x/y/y/z", true},
            {"**/*", "a/b", true},
            {"**/*", "a", true},
            {"a/**/*.go", "a/b/c/d.go", true},
            {"a/**/*.go", "a/d.go", true},
            {"a/**/*.go", "a/b/c/d.rs", false},
            {"a/**/*.go", "b/a/d.go", false},
            {"a/**", "a/b/c/", true},
            {"**/**", "a/b", true},
        }
        for _, c := range cases {
            got, err := Match(c.pattern, c.path)
            if err != nil || got != c.want {
                t.Errorf("Match(%q, %q) = %v, %v; want %v", c.pattern, c.path, got, err, c.want)
            }
        }
    }

    func TestLiteral(t *testing.T) {
        cases := map[string]string{
            "src/lib/**/*.go":  "src/lib",
            "*.go":             "",
            "/a/b":             "a",
            "a/b/c.go":         "a/b",
            "a/*/c":            "a",
            "a/{b,c}/d":        "a",
            "a/b[0-9]/c":       "a",
            "a\\*/b/c":         "",
            "x/y/":             "x",
            "/":                "",
            "":                 "",
            "a/b/**":           "a/b",
            "a//b/c/*.txt":     "a/b/c",
            "docs/v1.2/*.md":   "docs/v1.2",
            "src/?/x":          "src",
            "a/b/c/d":          "a/b/c",
            "single":           "",
            "one/two":          "one",
            "w?/lib/x":         "",
            "ok/w{a}/x/y":      "ok",
            "ok/fine/*/x/y/z":  "ok/fine",
        }
        for pat, want := range cases {
            if got := Literal(pat); got != want {
                t.Errorf("Literal(%q) = %q, want %q", pat, got, want)
            }
        }
    }

    const sampleRules = `
    # what the packager ships
    + **/*.rs
    + **/*.toml
      - **/target/**

    - *.tmp
    + keep.tmp
    `

    func TestParseRules(t *testing.T) {
        rules, err := ParseRules(sampleRules)
        if err != nil {
            t.Fatal(err)
        }
        want := []Rule{{true, "**/*.rs"}, {true, "**/*.toml"}, {false, "**/target/**"}, {false, "*.tmp"}, {true, "keep.tmp"}}
        if len(rules) != len(want) {
            t.Fatalf("got %+v", rules)
        }
        for i := range want {
            if rules[i] != want[i] {
                t.Errorf("rule %d = %+v, want %+v", i, rules[i], want[i])
            }
        }
    }

    func TestParseRulesWindowsLineEndingsAndSpaces(t *testing.T) {
        rules, err := ParseRules("+ a b\r\n-   spaced pattern  \r\n#c\r\n\r\n+ x\r\n")
        if err != nil || len(rules) != 3 {
            t.Fatalf("got %+v, %v", rules, err)
        }
        if rules[0] != (Rule{true, "a b"}) || rules[1] != (Rule{false, "spaced pattern"}) || rules[2] != (Rule{true, "x"}) {
            t.Errorf("got %+v", rules)
        }
        rules, err = ParseRules("")
        if err != nil || len(rules) != 0 {
            t.Errorf("empty text: %+v, %v", rules, err)
        }
        rules, err = ParseRules("# only\n\n   \n")
        if err != nil || len(rules) != 0 {
            t.Errorf("comments only: %+v, %v", rules, err)
        }
    }

    func TestParseRulesErrors(t *testing.T) {
        cases := []struct {
            text string
            line string
        }{
            {"* foo", "line 1"},
            {"+foo", "line 1"},
            {"+", "line 1"},
            {"+ ", "line 1"},
            {"# fine\n\n? what", "line 3"},
            {"+ ok\n- a[\n+ ok", "line 2"},
            {"+ ok\n# c\n\n- {a", "line 4"},
            {"+ ok\n++ x", "line 2"},
            {"- ok\n-x", "line 2"},
            {"+ ok\n+ [b-a]", "line 2"},
            {"ok", "line 1"},
        }
        for _, c := range cases {
            rules, err := ParseRules(c.text)
            if !errors.Is(err, ErrBadRule) || rules != nil || !strings.Contains(err.Error(), c.line) {
                t.Errorf("ParseRules(%q) = %+v, %v; want ErrBadRule at %s", c.text, rules, err, c.line)
            }
        }
    }

    func TestAllowedLastMatchWins(t *testing.T) {
        rules, _ := ParseRules(sampleRules)
        cases := []struct {
            path string
            want bool
        }{
            {"src/lib.rs", true},
            {"Cargo.toml", true},
            {"crates/a/Cargo.toml", true},
            {"target/debug/a.rs", false},
            {"crates/x/target/release/b.toml", false},
            {"target", false},
            {"notes.tmp", false},
            {"a/notes.tmp", false},
            {"keep.tmp", true},
            {"sub/keep.tmp", true},
            {"README.md", false},
            {"", false},
        }
        for _, c := range cases {
            got, err := Allowed(rules, c.path)
            if err != nil || got != c.want {
                t.Errorf("Allowed(%q) = %v, %v; want %v", c.path, got, err, c.want)
            }
        }
    }

    func TestAllowedOrderMatters(t *testing.T) {
        a, _ := ParseRules("- *.log\n+ important.log")
        b, _ := ParseRules("+ important.log\n- *.log")
        if ok, _ := Allowed(a, "x/important.log"); !ok {
            t.Errorf("include after exclude should win")
        }
        if ok, _ := Allowed(b, "x/important.log"); ok {
            t.Errorf("exclude after include should win")
        }
        if ok, _ := Allowed(nil, "x"); ok {
            t.Errorf("no rules means not allowed")
        }
        if ok, _ := Allowed(a, "x/other.txt"); ok {
            t.Errorf("unmatched path is not allowed")
        }
    }

    func TestAllowedReportsBadHandBuiltRule(t *testing.T) {
        rules := []Rule{{true, "**"}, {false, "["}}
        if ok, err := Allowed(rules, "x"); ok || !errors.Is(err, ErrBadPattern) {
            t.Errorf("got %v, %v", ok, err)
        }
    }
'''))

LIB = Lib(
    name="pathglob", lang="go", title="the pathglob package",
    blurb="The build tool filters files through pathglob, which matches slash-separated paths against glob patterns and ordered include/exclude rules.",
    files={"go.mod": langs.go_mod("pathglob"), "pathglob.go": SRC, "README.md": README},
    visible_tests={"pathglob_basic_test.go": VISIBLE},
    hidden_tests={"pathglob_full_test.go": HIDDEN},
    mutate=["pathglob.go"], difficulty=4, tags=["glob", "matching", "rules"],
)

register_libs([LIB], n=8)
