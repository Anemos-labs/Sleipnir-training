"""Colour maths (go): bugs injected into a small colour library."""
from fx import Lib, dd, langs, register_libs

README = dd('''
    # colorkit

    Colour helpers for a design-token tool. Colours are `Color{R, G, B, A uint8}`.

    ## `ParseHex(s string) (Color, error)`
    Accepts `#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa` (the `#` is required; hex digits in either case). Short forms
    repeat each digit: `#f80` is `#ff8800`. When there is no alpha, `A` is 255. Anything else (wrong length, a
    non-hex digit, missing `#`) returns an error.

    ## `(Color) Hex() string`
    Lower-case `#rrggbb` when `A == 255`, otherwise `#rrggbbaa`.

    ## `Luminance(c Color) float64`
    WCAG relative luminance: each channel `v/255` is linearised (`v <= 0.03928 ? v/12.92 : ((v+0.055)/1.055)^2.4`)
    and the result is `0.2126*R + 0.7152*G + 0.0722*B`. Alpha is ignored.

    ## `Contrast(a, b Color) float64`
    WCAG contrast ratio `(L1 + 0.05) / (L2 + 0.05)` where `L1` is the larger luminance. Always `>= 1`.

    ## `Mix(a, b Color, t float64) Color`
    Linear interpolation per channel including alpha, `t` clamped to `[0, 1]`; `t = 0` is `a`, `t = 1` is `b`.
    Channels are rounded to the nearest integer (halves round up).

    ## `Lighten(c Color, amount float64) Color`
    Mix with white by `amount` (clamped to `[0,1]`), keeping the original alpha.
''')

SRC = dd('''
    package colorkit

    import (
        "fmt"
        "math"
        "strconv"
        "strings"
    )

    // Color is an 8-bit RGBA colour.
    type Color struct{ R, G, B, A uint8 }

    // ParseHex parses #rgb, #rgba, #rrggbb and #rrggbbaa.
    func ParseHex(s string) (Color, error) {
        if !strings.HasPrefix(s, "#") {
            return Color{}, fmt.Errorf("colorkit: missing #: %q", s)
        }
        h := s[1:]
        switch len(h) {
        case 3, 4:
            var b strings.Builder
            for _, r := range h {
                b.WriteRune(r)
                b.WriteRune(r)
            }
            h = b.String()
        case 6, 8:
        default:
            return Color{}, fmt.Errorf("colorkit: bad length: %q", s)
        }
        var v [4]uint8
        v[3] = 255
        for i := 0; i < len(h)/2; i++ {
            n, err := strconv.ParseUint(h[2*i:2*i+2], 16, 8)
            if err != nil {
                return Color{}, fmt.Errorf("colorkit: bad digit in %q", s)
            }
            v[i] = uint8(n)
        }
        return Color{v[0], v[1], v[2], v[3]}, nil
    }

    // Hex formats the colour as lower-case hex.
    func (c Color) Hex() string {
        if c.A == 255 {
            return fmt.Sprintf("#%02x%02x%02x", c.R, c.G, c.B)
        }
        return fmt.Sprintf("#%02x%02x%02x%02x", c.R, c.G, c.B, c.A)
    }

    func linear(v uint8) float64 {
        x := float64(v) / 255
        if x <= 0.03928 {
            return x / 12.92
        }
        return math.Pow((x+0.055)/1.055, 2.4)
    }

    // Luminance is the WCAG relative luminance.
    func Luminance(c Color) float64 {
        return 0.2126*linear(c.R) + 0.7152*linear(c.G) + 0.0722*linear(c.B)
    }

    // Contrast is the WCAG contrast ratio of two colours.
    func Contrast(a, b Color) float64 {
        la, lb := Luminance(a), Luminance(b)
        if la < lb {
            la, lb = lb, la
        }
        return (la + 0.05) / (lb + 0.05)
    }

    func clamp01(t float64) float64 {
        if t < 0 {
            return 0
        }
        if t > 1 {
            return 1
        }
        return t
    }

    func mixChannel(a, b uint8, t float64) uint8 {
        return uint8(math.Floor(float64(a) + (float64(b)-float64(a))*t + 0.5))
    }

    // Mix interpolates linearly between a and b.
    func Mix(a, b Color, t float64) Color {
        t = clamp01(t)
        return Color{
            mixChannel(a.R, b.R, t),
            mixChannel(a.G, b.G, t),
            mixChannel(a.B, b.B, t),
            mixChannel(a.A, b.A, t),
        }
    }

    // Lighten mixes the colour with white, keeping its alpha.
    func Lighten(c Color, amount float64) Color {
        m := Mix(c, Color{255, 255, 255, c.A}, amount)
        m.A = c.A
        return m
    }
''')

VISIBLE = dd('''
    package colorkit

    import "testing"

    func TestParseShort(t *testing.T) {
        c, err := ParseHex("#f80")
        if err != nil || c != (Color{255, 136, 0, 255}) {
            t.Fatalf("got %v %v", c, err)
        }
    }

    func TestHexRoundTrip(t *testing.T) {
        c, _ := ParseHex("#1a2b3c")
        if c.Hex() != "#1a2b3c" {
            t.Fatalf("got %s", c.Hex())
        }
    }
''')

HIDDEN = dd('''
    package colorkit

    import (
        "math"
        "testing"
    )

    func near(a, b float64) bool { return math.Abs(a-b) < 1e-3 }

    func TestParseForms(t *testing.T) {
        cases := map[string]Color{
            "#000":       {0, 0, 0, 255},
            "#fff":       {255, 255, 255, 255},
            "#abc":       {170, 187, 204, 255},
            "#ABC8":      {170, 187, 204, 136},
            "#102030":    {16, 32, 48, 255},
            "#10203040":  {16, 32, 48, 64},
            "#FFFFFF00":  {255, 255, 255, 0},
            "#0a0B0c":    {10, 11, 12, 255},
        }
        for in, want := range cases {
            got, err := ParseHex(in)
            if err != nil || got != want {
                t.Errorf("ParseHex(%q) = %v, %v; want %v", in, got, err, want)
            }
        }
    }

    func TestParseErrors(t *testing.T) {
        for _, in := range []string{"", "#", "fff", "#ff", "#fffff", "#fffffff", "#fffffffff", "#ggg", "#12345z", "#12 456", "ff8800"} {
            if _, err := ParseHex(in); err == nil {
                t.Errorf("ParseHex(%q) should fail", in)
            }
        }
    }

    func TestHex(t *testing.T) {
        if got := (Color{255, 136, 0, 255}).Hex(); got != "#ff8800" {
            t.Errorf("got %s", got)
        }
        if got := (Color{1, 2, 3, 4}).Hex(); got != "#01020304" {
            t.Errorf("got %s", got)
        }
        if got := (Color{0, 0, 0, 0}).Hex(); got != "#00000000" {
            t.Errorf("got %s", got)
        }
        if got := (Color{171, 205, 239, 255}).Hex(); got != "#abcdef" {
            t.Errorf("got %s", got)
        }
    }

    func TestLuminance(t *testing.T) {
        if l := Luminance(Color{0, 0, 0, 255}); l != 0 {
            t.Errorf("black %v", l)
        }
        if l := Luminance(Color{255, 255, 255, 255}); !near(l, 1) {
            t.Errorf("white %v", l)
        }
        if l := Luminance(Color{255, 0, 0, 255}); !near(l, 0.2126) {
            t.Errorf("red %v", l)
        }
        if l := Luminance(Color{0, 255, 0, 255}); !near(l, 0.7152) {
            t.Errorf("green %v", l)
        }
        if l := Luminance(Color{0, 0, 255, 255}); !near(l, 0.0722) {
            t.Errorf("blue %v", l)
        }
        if l := Luminance(Color{128, 128, 128, 255}); !near(l, 0.2159) {
            t.Errorf("grey %v", l)
        }
        // the linear segment: 10/255 = 0.0392 <= 0.03928
        if l := Luminance(Color{10, 10, 10, 255}); !near(l, 0.003035) {
            t.Errorf("dark grey %v", l)
        }
        if l := Luminance(Color{50, 50, 50, 255}); !near(l, 0.03189) {
            t.Errorf("grey 50 %v", l)
        }
        if Luminance(Color{128, 128, 128, 0}) != Luminance(Color{128, 128, 128, 255}) {
            t.Errorf("alpha must be ignored")
        }
    }

    func TestContrast(t *testing.T) {
        w, b := Color{255, 255, 255, 255}, Color{0, 0, 0, 255}
        if c := Contrast(w, b); !near(c, 21) {
            t.Errorf("wb %v", c)
        }
        if c := Contrast(b, w); !near(c, 21) {
            t.Errorf("bw %v", c)
        }
        if c := Contrast(w, w); !near(c, 1) {
            t.Errorf("ww %v", c)
        }
        g := Color{119, 119, 119, 255}
        if c := Contrast(g, w); !near(c, 4.478) {
            t.Errorf("grey on white %v", c)
        }
        if c := Contrast(Color{0, 0, 255, 255}, Color{255, 255, 0, 255}); !near(c, 8.0) && !near(c, 8.0013) {
            // blue 0.0722 vs yellow 0.9278: (0.9778)/(0.1222) = 8.0
            t.Errorf("blue yellow %v", c)
        }
    }

    func TestMix(t *testing.T) {
        a, b := Color{0, 0, 0, 255}, Color{255, 255, 255, 255}
        if got := Mix(a, b, 0); got != a {
            t.Errorf("t=0 %v", got)
        }
        if got := Mix(a, b, 1); got != b {
            t.Errorf("t=1 %v", got)
        }
        if got := Mix(a, b, 0.5); got != (Color{128, 128, 128, 255}) {
            t.Errorf("t=.5 %v", got)
        }
        if got := Mix(a, b, 0.2); got != (Color{51, 51, 51, 255}) {
            t.Errorf("t=.2 %v", got)
        }
        if got := Mix(a, b, -3); got != a {
            t.Errorf("clamp low %v", got)
        }
        if got := Mix(a, b, 7); got != b {
            t.Errorf("clamp high %v", got)
        }
        // downward and alpha
        if got := Mix(Color{200, 100, 50, 0}, Color{100, 200, 150, 200}, 0.25); got != (Color{175, 125, 75, 50}) {
            t.Errorf("mixed %v", got)
        }
        if got := Mix(Color{255, 0, 0, 255}, Color{0, 0, 255, 255}, 0.1); got != (Color{230, 0, 26, 255}) {
            t.Errorf("rb %v", got)
        }
    }

    func TestLighten(t *testing.T) {
        if got := Lighten(Color{0, 0, 0, 255}, 0.5); got != (Color{128, 128, 128, 255}) {
            t.Errorf("got %v", got)
        }
        if got := Lighten(Color{100, 150, 200, 77}, 0); got != (Color{100, 150, 200, 77}) {
            t.Errorf("zero %v", got)
        }
        if got := Lighten(Color{100, 150, 200, 77}, 1); got != (Color{255, 255, 255, 77}) {
            t.Errorf("one %v", got)
        }
        if got := Lighten(Color{100, 150, 200, 77}, 2); got != (Color{255, 255, 255, 77}) {
            t.Errorf("over %v", got)
        }
        if got := Lighten(Color{100, 150, 200, 255}, 0.4); got != (Color{162, 192, 222, 255}) {
            t.Errorf("0.4 %v", got)
        }
    }
''')

LIB = Lib(
    name="colorkit", lang="go", title="the colorkit package",
    blurb="The design-token tool uses colorkit to parse brand colours, check text contrast and derive lighter shades.",
    files={"go.mod": langs.go_mod("colorkit"), "colorkit.go": SRC, "README.md": README},
    visible_tests={"colorkit_basic_test.go": VISIBLE},
    hidden_tests={"colorkit_full_test.go": HIDDEN},
    mutate=["colorkit.go"], difficulty=3, tags=["colour", "wcag", "parsing"],
)

register_libs([LIB], n=8)
