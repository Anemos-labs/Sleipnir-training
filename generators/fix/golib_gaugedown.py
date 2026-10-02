"""Gauge downsampling (go): aligned buckets with floor division, gap fill policies, min/max decimation, counter rates."""
from fx import Lib, dd, langs, register_libs

from generators.fix._lang1 import gosrc

README = dd('''
    # gaugedown

    Thinning helpers for the harbour dashboards: tide-gauge and flow-meter series are reduced before they are charted.
    A `Point` is `{T, V int64}` (seconds, millimetres or counts). All arithmetic is integer.

    ## `Downsample(points []Point, o Options) ([]Bucket, error)`
    `Options{Origin, Width int64; Agg Agg; Fill Fill}`. `Width <= 0` is `ErrWidth`. `points` must be in non-decreasing `T`
    order, otherwise `ErrUnsorted` (equal timestamps are fine and both count).

    The bucket of a point is `floor((T - Origin) / Width)` (a true floor, also for times before `Origin`) and the
    bucket starts at `Origin + index*Width`; it covers `[Start, Start+Width)`. Output buckets are in time order, a
    `Bucket` is `{Start, V int64; N int}` with `N` the number of points that fell in it.

    `Agg` picks `V`: `Mean`, `Min`, `Max`, `Sum`, `First`, `Last` (first/last in input order) or `Count`.
    `Mean` is rounded to the nearest integer, halves away from zero (`1.5 -> 2`, `-1.5 -> -2`).

    `Fill` decides what happens to buckets with no points *between* two non-empty buckets (there is never output before
    the first or after the last non-empty bucket). Filled buckets have `N == 0`:

    * `FillNone`: nothing is emitted for them (the default);
    * `FillZero`: `V = 0`;
    * `FillPrev`: `V` of the nearest earlier non-empty bucket;
    * `FillLinear`: with `prev` and `next` the surrounding non-empty buckets and `gap` the number of empty buckets
      between them, the `k`-th empty bucket (1-based) gets `prev.V + (next.V - prev.V)*k/(gap+1)`, with the division
      truncating toward zero.

    No points means no buckets.

    ## `Decimate(points []Point, keep int) ([]Point, error)`
    Keeps the visual envelope of a series. `keep < 2` is `ErrKeep`. When `len(points) <= keep` a copy of the input is
    returned. Otherwise `groups = keep/2` and the points are cut into consecutive groups of
    `size = ceil(len(points)/groups)` (the last group may be shorter). From each group the point with the smallest `V`
    and the point with the largest `V` are kept (first one on ties), in time order; a group whose minimum and maximum
    are the same point contributes it once.

    ## `Rates(points []Point) ([]Point, error)`
    Turns a counter into rates per 1000 time units. For each consecutive pair the result has a point at the *later*
    `T` with `V = delta * 1000 / dt`, truncated, where `dt` is the time difference and `delta` the value difference.
    If the counter went down (`delta < 0`) it was reset: `delta` is then the later value itself. Pairs with `dt <= 0` make
    the whole call fail with `ErrUnsorted`. Fewer than two points give an empty result.
''')

SRC = gosrc(dd(r'''
    // Package gaugedown reduces time series for charting.
    package gaugedown

    import "errors"

    var (
        ErrWidth    = errors.New("gaugedown: bucket width must be positive")
        ErrUnsorted = errors.New("gaugedown: points out of order")
        ErrKeep     = errors.New("gaugedown: keep must be at least 2")
    )

    // Point is one sample.
    type Point struct{ T, V int64 }

    // Bucket is one aggregated interval.
    type Bucket struct {
        Start int64
        V     int64
        N     int
    }

    // Agg selects how a bucket's points are combined.
    type Agg int

    const (
        Mean Agg = iota
        Min
        Max
        Sum
        First
        Last
        Count
    )

    // Fill selects how empty buckets between data are treated.
    type Fill int

    const (
        FillNone Fill = iota
        FillZero
        FillPrev
        FillLinear
    )

    // Options configure Downsample.
    type Options struct {
        Origin, Width int64
        Agg           Agg
        Fill          Fill
    }

    func floorDiv(a, b int64) int64 {
        q := a / b
        if a%b != 0 && (a < 0) != (b < 0) {
            q--
        }
        return q
    }

    // divRound divides rounding to nearest, halves away from zero (n > 0).
    func divRound(a, n int64) int64 {
        if a >= 0 {
            return (a + n/2) / n
        }
        return -((-a + n/2) / n)
    }

    func aggregate(vals []int64, agg Agg) int64 {
        switch agg {
        case Min:
            m := vals[0]
            for _, v := range vals[1:] {
                m = min(m, v)
            }
            return m
        case Max:
            m := vals[0]
            for _, v := range vals[1:] {
                m = max(m, v)
            }
            return m
        case Sum:
            var s int64
            for _, v := range vals {
                s += v
            }
            return s
        case First:
            return vals[0]
        case Last:
            return vals[len(vals)-1]
        case Count:
            return int64(len(vals))
        }
        var s int64
        for _, v := range vals {
            s += v
        }
        return divRound(s, int64(len(vals)))
    }

    // Downsample groups points into aligned buckets.
    func Downsample(points []Point, o Options) ([]Bucket, error) {
        if o.Width <= 0 {
            return nil, ErrWidth
        }
        for i := 1; i < len(points); i++ {
            if points[i].T < points[i-1].T {
                return nil, ErrUnsorted
            }
        }
        var dense []Bucket
        var cur []int64
        var curStart int64
        flush := func() {
            if len(cur) > 0 {
                dense = append(dense, Bucket{Start: curStart, V: aggregate(cur, o.Agg), N: len(cur)})
                cur = nil
            }
        }
        for _, p := range points {
            start := o.Origin + floorDiv(p.T-o.Origin, o.Width)*o.Width
            if len(cur) > 0 && start != curStart {
                flush()
            }
            curStart = start
            cur = append(cur, p.V)
        }
        flush()
        if o.Fill == FillNone || len(dense) < 2 {
            return dense, nil
        }
        var out []Bucket
        for i, b := range dense {
            if i > 0 {
                prev := dense[i-1]
                gap := int((b.Start-prev.Start)/o.Width) - 1
                for k := 1; k <= gap; k++ {
                    var v int64
                    switch o.Fill {
                    case FillPrev:
                        v = prev.V
                    case FillLinear:
                        v = prev.V + (b.V-prev.V)*int64(k)/int64(gap+1)
                    }
                    out = append(out, Bucket{Start: prev.Start + int64(k)*o.Width, V: v})
                }
            }
            out = append(out, b)
        }
        return out, nil
    }

    // Decimate keeps the minimum and maximum of each group of points.
    func Decimate(points []Point, keep int) ([]Point, error) {
        if keep < 2 {
            return nil, ErrKeep
        }
        if len(points) <= keep {
            return append([]Point(nil), points...), nil
        }
        groups := keep / 2
        size := (len(points) + groups - 1) / groups
        var out []Point
        for lo := 0; lo < len(points); lo += size {
            hi := min(lo+size, len(points))
            imin, imax := lo, lo
            for i := lo + 1; i < hi; i++ {
                if points[i].V < points[imin].V {
                    imin = i
                }
                if points[i].V > points[imax].V {
                    imax = i
                }
            }
            if imin > imax {
                imin, imax = imax, imin
            }
            out = append(out, points[imin])
            if imax != imin {
                out = append(out, points[imax])
            }
        }
        return out, nil
    }

    // Rates converts a counter into per-1000-unit rates, treating a drop as a reset.
    func Rates(points []Point) ([]Point, error) {
        out := []Point{}
        for i := 1; i < len(points); i++ {
            dt := points[i].T - points[i-1].T
            if dt <= 0 {
                return nil, ErrUnsorted
            }
            delta := points[i].V - points[i-1].V
            if delta < 0 {
                delta = points[i].V
            }
            out = append(out, Point{T: points[i].T, V: delta * 1000 / dt})
        }
        return out, nil
    }
'''))

VISIBLE = gosrc(dd(r'''
    package gaugedown

    import "testing"

    func TestSimpleMean(t *testing.T) {
        pts := []Point{{0, 10}, {5, 20}, {12, 7}}
        got, err := Downsample(pts, Options{Width: 10})
        if err != nil || len(got) != 2 || got[0] != (Bucket{0, 15, 2}) || got[1] != (Bucket{10, 7, 1}) {
            t.Fatalf("got %+v, %v", got, err)
        }
    }

    func TestRatesBasic(t *testing.T) {
        got, err := Rates([]Point{{0, 0}, {10, 50}})
        if err != nil || len(got) != 1 || got[0] != (Point{10, 5000}) {
            t.Fatalf("got %+v, %v", got, err)
        }
    }
'''))

HIDDEN = gosrc(dd(r'''
    package gaugedown

    import (
        "errors"
        "reflect"
        "testing"
    )

    var series = []Point{{0, 5}, {3, 7}, {9, -2}, {10, 4}, {25, 10}, {26, 20}, {27, 30}, {55, 1}}

    func opts(agg Agg, fill Fill) Options { return Options{Width: 10, Agg: agg, Fill: fill} }

    func TestAggregations(t *testing.T) {
        cases := []struct {
            agg  Agg
            want []int64
        }{
            {Mean, []int64{3, 4, 20, 1}},
            {Min, []int64{-2, 4, 10, 1}},
            {Max, []int64{7, 4, 30, 1}},
            {Sum, []int64{10, 4, 60, 1}},
            {First, []int64{5, 4, 10, 1}},
            {Last, []int64{-2, 4, 30, 1}},
            {Count, []int64{3, 1, 3, 1}},
        }
        starts := []int64{0, 10, 20, 50}
        counts := []int{3, 1, 3, 1}
        for _, c := range cases {
            got, err := Downsample(series, opts(c.agg, FillNone))
            if err != nil || len(got) != 4 {
                t.Fatalf("agg %d: %+v, %v", c.agg, got, err)
            }
            for i, b := range got {
                if b.V != c.want[i] || b.Start != starts[i] || b.N != counts[i] {
                    t.Errorf("agg %d bucket %d: %+v, want V=%d start=%d n=%d", c.agg, i, b, c.want[i], starts[i], counts[i])
                }
            }
        }
    }

    func TestFillPolicies(t *testing.T) {
        zero, _ := Downsample(series, opts(Mean, FillZero))
        wantZero := []Bucket{{0, 3, 3}, {10, 4, 1}, {20, 20, 3}, {30, 0, 0}, {40, 0, 0}, {50, 1, 1}}
        if !reflect.DeepEqual(zero, wantZero) {
            t.Errorf("zero: %+v", zero)
        }
        prev, _ := Downsample(series, opts(Mean, FillPrev))
        wantPrev := []Bucket{{0, 3, 3}, {10, 4, 1}, {20, 20, 3}, {30, 20, 0}, {40, 20, 0}, {50, 1, 1}}
        if !reflect.DeepEqual(prev, wantPrev) {
            t.Errorf("prev: %+v", prev)
        }
        lin, _ := Downsample(series, opts(Mean, FillLinear))
        wantLin := []Bucket{{0, 3, 3}, {10, 4, 1}, {20, 20, 3}, {30, 14, 0}, {40, 8, 0}, {50, 1, 1}}
        if !reflect.DeepEqual(lin, wantLin) {
            t.Errorf("linear: %+v", lin)
        }
    }

    func TestLinearFillRisingAndTruncation(t *testing.T) {
        pts := []Point{{0, 0}, {40, 10}}
        got, _ := Downsample(pts, Options{Width: 10, Agg: Last, Fill: FillLinear})
        want := []Bucket{{0, 0, 1}, {10, 2, 0}, {20, 5, 0}, {30, 7, 0}, {40, 10, 1}}
        if !reflect.DeepEqual(got, want) {
            t.Errorf("rising: %+v", got)
        }
        pts = []Point{{0, 0}, {30, -10}}
        got, _ = Downsample(pts, Options{Width: 10, Agg: Last, Fill: FillLinear})
        want = []Bucket{{0, 0, 1}, {10, -3, 0}, {20, -6, 0}, {30, -10, 1}}
        if !reflect.DeepEqual(got, want) {
            t.Errorf("falling: %+v", got)
        }
    }

    func TestFillNeverExtendsTheEnds(t *testing.T) {
        pts := []Point{{35, 1}}
        for _, f := range []Fill{FillZero, FillPrev, FillLinear} {
            got, _ := Downsample(pts, Options{Width: 10, Fill: f})
            if len(got) != 1 || got[0] != (Bucket{30, 1, 1}) {
                t.Errorf("fill %d: %+v", f, got)
            }
        }
        adj := []Point{{1, 5}, {11, 9}}
        got, _ := Downsample(adj, Options{Width: 10, Fill: FillLinear})
        if len(got) != 2 {
            t.Errorf("adjacent buckets got filled: %+v", got)
        }
    }

    func TestNoPoints(t *testing.T) {
        for _, in := range [][]Point{nil, {}} {
            got, err := Downsample(in, Options{Width: 10, Fill: FillZero})
            if err != nil || len(got) != 0 {
                t.Errorf("got %+v, %v", got, err)
            }
        }
    }

    func TestMeanRounding(t *testing.T) {
        cases := []struct {
            vals []int64
            want int64
        }{
            {[]int64{1, 2}, 2}, {[]int64{-1, -2}, -2}, {[]int64{1, 1, 2}, 1}, {[]int64{-1, -1, -2}, -1},
            {[]int64{0, 1}, 1}, {[]int64{-1, 0}, -1}, {[]int64{3, 4, 4, 4}, 4}, {[]int64{-3, -4, -4, -4}, -4},
            {[]int64{5}, 5}, {[]int64{-5}, -5}, {[]int64{2, 2, 3}, 2}, {[]int64{1, 1, 1, 2}, 1}, {[]int64{-7, 8}, 1},
        }
        for _, c := range cases {
            pts := make([]Point, len(c.vals))
            for i, v := range c.vals {
                pts[i] = Point{int64(i), v}
            }
            got, _ := Downsample(pts, Options{Width: 100, Agg: Mean})
            if len(got) != 1 || got[0].V != c.want {
                t.Errorf("mean of %v = %+v, want %d", c.vals, got, c.want)
            }
        }
    }

    func TestFloorBucketsBeforeOrigin(t *testing.T) {
        pts := []Point{{-21, 1}, {-20, 2}, {-11, 3}, {-10, 4}, {-1, 5}, {0, 6}, {9, 7}, {10, 8}}
        got, err := Downsample(pts, Options{Width: 10, Agg: Sum})
        want := []Bucket{{-30, 1, 1}, {-20, 5, 2}, {-10, 9, 2}, {0, 13, 2}, {10, 8, 1}}
        if err != nil || !reflect.DeepEqual(got, want) {
            t.Errorf("got %+v, %v", got, err)
        }
    }

    func TestOrigin(t *testing.T) {
        pts := []Point{{-6, 9}, {4, 1}, {5, 2}, {14, 3}, {15, 4}}
        got, err := Downsample(pts, Options{Origin: 5, Width: 10, Agg: Sum})
        want := []Bucket{{-15, 9, 1}, {-5, 1, 1}, {5, 5, 2}, {15, 4, 1}}
        if err != nil || !reflect.DeepEqual(got, want) {
            t.Errorf("got %+v, %v", got, err)
        }
    }

    func TestWidthOne(t *testing.T) {
        got, err := Downsample([]Point{{3, 1}, {3, 2}, {5, 4}}, Options{Width: 1, Agg: Sum})
        want := []Bucket{{3, 3, 2}, {5, 4, 1}}
        if err != nil || !reflect.DeepEqual(got, want) {
            t.Errorf("got %+v, %v", got, err)
        }
    }

    func TestEqualTimestampsCount(t *testing.T) {
        got, err := Downsample([]Point{{5, 1}, {5, 2}, {5, 3}}, Options{Width: 10, Agg: Count})
        if err != nil || len(got) != 1 || got[0].V != 3 || got[0].N != 3 {
            t.Errorf("got %+v, %v", got, err)
        }
        got, _ = Downsample([]Point{{5, 1}, {5, 9}}, Options{Width: 10, Agg: Last})
        if got[0].V != 9 {
            t.Errorf("last: %+v", got)
        }
        got, _ = Downsample([]Point{{5, 1}, {5, 9}}, Options{Width: 10, Agg: First})
        if got[0].V != 1 {
            t.Errorf("first: %+v", got)
        }
    }

    func TestDownsampleErrors(t *testing.T) {
        for _, w := range []int64{0, -1, -10} {
            if _, err := Downsample(series, Options{Width: w}); !errors.Is(err, ErrWidth) {
                t.Errorf("width %d: %v", w, err)
            }
        }
        if _, err := Downsample(nil, Options{Width: 0}); !errors.Is(err, ErrWidth) {
            t.Errorf("width check comes first: %v", err)
        }
        if _, err := Downsample([]Point{{5, 1}, {4, 1}}, Options{Width: 10}); !errors.Is(err, ErrUnsorted) {
            t.Errorf("unsorted: %v", err)
        }
        if _, err := Downsample([]Point{{1, 1}, {2, 1}, {3, 1}, {2, 1}}, Options{Width: 10}); !errors.Is(err, ErrUnsorted) {
            t.Errorf("unsorted late: %v", err)
        }
    }

    func mk(vs ...int64) []Point {
        out := make([]Point, len(vs))
        for i, v := range vs {
            out[i] = Point{int64(i), v}
        }
        return out
    }

    func TestDecimate(t *testing.T) {
        pts := mk(5, 1, 9, 3, 7, 7, 2, 8, 8, 0, 4, 6)
        got, err := Decimate(pts, 6)
        want := []Point{{1, 1}, {2, 9}, {6, 2}, {7, 8}, {8, 8}, {9, 0}}
        if err != nil || !reflect.DeepEqual(got, want) {
            t.Errorf("got %+v, %v", got, err)
        }
    }

    func TestDecimateGroupSizes(t *testing.T) {
        // 7 points, keep 4: two groups of size 4 and 3
        got, _ := Decimate(mk(1, 9, 2, 3, 8, 0, 5), 4)
        // group 2 holds T=4..6: values 8,0,5 -> min at T=5, max at T=4: time order gives T=4 then T=5
        want := []Point{{0, 1}, {1, 9}, {4, 8}, {5, 0}}
        if !reflect.DeepEqual(got, want) {
            t.Errorf("got %+v, want %+v", got, want)
        }
        // odd keep uses keep/2 groups: keep 5 -> 2 groups over 10 points
        got, _ = Decimate(mk(3, 1, 4, 1, 5, 9, 2, 6, 5, 3), 5)
        want = []Point{{1, 1}, {4, 5}, {5, 9}, {6, 2}}
        if !reflect.DeepEqual(got, want) {
            t.Errorf("odd keep: got %+v, want %+v", got, want)
        }
        // never more than keep points
        for n := 3; n < 60; n++ {
            vs := make([]int64, n)
            for i := range vs {
                vs[i] = int64((i*37 + 11) % 23)
            }
            for keep := 2; keep < n; keep++ {
                out, _ := Decimate(mk(vs...), keep)
                if len(out) > keep || len(out) == 0 {
                    t.Fatalf("n=%d keep=%d: %d points", n, keep, len(out))
                }
                for i := 1; i < len(out); i++ {
                    if out[i].T <= out[i-1].T {
                        t.Fatalf("n=%d keep=%d: not in time order: %+v", n, keep, out)
                    }
                }
            }
        }
    }

    func TestDecimateTiesAndFlat(t *testing.T) {
        got, _ := Decimate(mk(4, 4, 4, 4, 4, 4), 2)
        if len(got) != 1 || got[0] != (Point{0, 4}) {
            t.Errorf("flat: %+v", got)
        }
        got, _ = Decimate(mk(2, 7, 7, 2, 7, 2), 2)
        if len(got) != 2 || got[0] != (Point{0, 2}) || got[1] != (Point{1, 7}) {
            t.Errorf("ties: %+v", got)
        }
        got, _ = Decimate(mk(1, 2, 3, 4, 5, 6, 7, 8, 9), 2)
        if len(got) != 2 || got[0].V != 1 || got[1].V != 9 {
            t.Errorf("keep 2: %+v", got)
        }
    }

    func TestDecimateSmallInputAndErrors(t *testing.T) {
        in := mk(3, 1, 2)
        got, err := Decimate(in, 3)
        if err != nil || !reflect.DeepEqual(got, in) {
            t.Errorf("got %+v, %v", got, err)
        }
        got[0].V = 99
        if in[0].V == 99 {
            t.Errorf("result aliases the input")
        }
        if got, err := Decimate(nil, 4); err != nil || len(got) != 0 {
            t.Errorf("nil: %+v %v", got, err)
        }
        for _, k := range []int{1, 0, -4} {
            if _, err := Decimate(in, k); !errors.Is(err, ErrKeep) {
                t.Errorf("keep %d: %v", k, err)
            }
        }
        if _, err := Decimate(nil, 1); !errors.Is(err, ErrKeep) {
            t.Errorf("keep check first: %v", err)
        }
    }

    func TestRates(t *testing.T) {
        pts := []Point{{0, 0}, {10, 50}, {20, 120}, {30, 20}, {40, 45}, {41, 45}, {48, 55}}
        got, err := Rates(pts)
        want := []Point{{10, 5000}, {20, 7000}, {30, 2000}, {40, 2500}, {41, 0}, {48, 1428}}
        if err != nil || !reflect.DeepEqual(got, want) {
            t.Errorf("got %+v, %v", got, err)
        }
    }

    func TestRatesEdges(t *testing.T) {
        for _, in := range [][]Point{nil, {{5, 5}}} {
            got, err := Rates(in)
            if err != nil || got == nil || len(got) != 0 {
                t.Errorf("got %#v, %v", got, err)
            }
        }
        if _, err := Rates([]Point{{0, 0}, {10, 1}, {10, 2}}); !errors.Is(err, ErrUnsorted) {
            t.Errorf("equal times: %v", err)
        }
        if _, err := Rates([]Point{{0, 0}, {10, 1}, {5, 2}}); !errors.Is(err, ErrUnsorted) {
            t.Errorf("backwards: %v", err)
        }
        // a reset to exactly zero counts as a reset: delta = 0
        got, _ := Rates([]Point{{0, 10}, {10, 0}})
        if len(got) != 1 || got[0].V != 0 {
            t.Errorf("reset to zero: %+v", got)
        }
        // no change is no reset
        got, _ = Rates([]Point{{0, 10}, {10, 10}})
        if len(got) != 1 || got[0].V != 0 {
            t.Errorf("flat: %+v", got)
        }
    }
'''))

LIB = Lib(
    name="gaugedown", lang="go", title="the gaugedown package",
    blurb="The harbour dashboards use gaugedown to thin tide-gauge and flow-meter series into aligned buckets before charting them.",
    files={"go.mod": langs.go_mod("gaugedown"), "gaugedown.go": SRC, "README.md": README},
    visible_tests={"gaugedown_basic_test.go": VISIBLE},
    hidden_tests={"gaugedown_full_test.go": HIDDEN},
    mutate=["gaugedown.go"], difficulty=3, tags=["timeseries", "buckets", "aggregation"],
)

register_libs([LIB], n=8)
