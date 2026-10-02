"""Retry back-off schedules (go): capped exponential delays, deterministic jitter, budgets, and a failure tracker."""
from fx import Lib, dd, langs

from generators.fix._lang1 import gosrc, register_libs

README = dd('''
    # retrywin

    Retry timing for the job runner. Everything is deterministic: "randomness" comes from a seed passed in by the caller,
    and time is a plain `int64` number of milliseconds supplied by the caller.

    ## `Policy`
    ```go
    type Policy struct {
        Base, Cap   int64  // first delay and the ceiling, in ms
        Factor      int    // growth per attempt
        Jitter      Jitter // JitterNone, JitterFull or JitterEqual
        MaxAttempts int    // number of retries allowed; 0 means "no limit"
        Budget      int64  // total delay allowed by Schedule, in ms; 0 means "no limit"
        ResetAfter  int64  // Tracker forgets old failures after this much quiet time, in ms; 0 means never
    }
    ```
    `Validate()` returns `ErrBadPolicy` unless `Base >= 1`, `Cap >= Base`, `Factor >= 1`, `MaxAttempts >= 0`,
    `Budget >= 0` and `ResetAfter >= 0`.

    ## `(Policy) Delay(attempt int, seed uint64) (int64, bool)`
    Attempts are numbered from 1. The *nominal* delay is `Base * Factor^(attempt-1)`, never more than `Cap` (it
    must not overflow: huge attempt numbers just give `Cap`). Then the jitter is applied, with
    `m = mix(seed, attempt)` (below):

    * `JitterNone`: the nominal delay;
    * `JitterFull`: `m mod (nominal+1)`, which lies in `[0, nominal]`;
    * `JitterEqual`: `nominal/2 + m mod (nominal - nominal/2 + 1)`, which lies in `[nominal/2, nominal]` (integer halves).

    `mix` is splitmix64's finaliser: `z = seed + attempt*0x9E3779B97F4A7C15`; `z = (z ^ z>>30) * 0xBF58476D1CE4E5B9`;
    `z = (z ^ z>>27) * 0x94D049BB133111EB`; result `z ^ z>>31` (all arithmetic on `uint64`, wrapping).

    The bool is `false` (and the delay 0) when `attempt < 1` or when `MaxAttempts > 0 && attempt > MaxAttempts`.
    `Delay` does not validate the policy.

    ## `(Policy) Schedule(seed uint64) ([]int64, error)`
    All delays for attempts `1, 2, ...`, until `MaxAttempts` is reached, or until adding the next delay would push the
    running total *above* `Budget` (a total equal to the budget is fine; the delay that does not fit is not included).
    The policy is validated first. A policy with neither `MaxAttempts` nor `Budget` is `ErrUnbounded`. A schedule never
    has more than `MaxSchedule` (1000) entries.

    ## `Tracker`
    `NewTracker(p Policy, seed uint64) (*Tracker, error)` validates the policy. It follows one operation that keeps
    failing.

    * `Fail(now int64) (retryAt int64, ok bool)` records a failure at time `now`. First, if there are earlier failures,
      `ResetAfter > 0` and `now - (time of the previous failure) >= ResetAfter`, the failure count restarts from 0.
      Then the count goes up by one and `retryAt = now + Delay(count, seed)`. When the count exceeds `MaxAttempts` the
      tracker gives up: `ok` is false, `retryAt` 0.
    * `Succeed()` forgets all failures and a give-up.
    * `Attempts() int` is the failure count (including the failure that made it give up).
    * `Ready(now int64) bool`: true when there are no failures; false after a give-up; otherwise true once
      `now >= retryAt` of the latest failure.
''')

SRC = gosrc(dd(r'''
    // Package retrywin computes retry delays.
    package retrywin

    import "errors"

    // MaxSchedule bounds the length of a schedule.
    const MaxSchedule = 1000

    var (
        ErrBadPolicy = errors.New("retrywin: invalid policy")
        ErrUnbounded = errors.New("retrywin: policy has neither MaxAttempts nor Budget")
    )

    // Jitter selects how nominal delays are randomised.
    type Jitter int

    const (
        JitterNone Jitter = iota
        JitterFull
        JitterEqual
    )

    // Policy describes a back-off.
    type Policy struct {
        Base, Cap   int64
        Factor      int
        Jitter      Jitter
        MaxAttempts int
        Budget      int64
        ResetAfter  int64
    }

    // Validate checks the parameters.
    func (p Policy) Validate() error {
        if p.Base < 1 || p.Cap < p.Base || p.Factor < 1 || p.MaxAttempts < 0 || p.Budget < 0 || p.ResetAfter < 0 {
            return ErrBadPolicy
        }
        return nil
    }

    func mix(seed uint64, attempt int) uint64 {
        z := seed + uint64(attempt)*0x9E3779B97F4A7C15
        z = (z ^ z>>30) * 0xBF58476D1CE4E5B9
        z = (z ^ z>>27) * 0x94D049BB133111EB
        return z ^ z>>31
    }

    func (p Policy) nominal(attempt int) int64 {
        d := p.Base
        for i := 1; i < attempt && d < p.Cap; i++ {
            if d > p.Cap/int64(p.Factor) {
                d = p.Cap
            } else {
                d *= int64(p.Factor)
            }
        }
        return min(d, p.Cap)
    }

    // Delay is the wait before retry number attempt (1-based).
    func (p Policy) Delay(attempt int, seed uint64) (int64, bool) {
        if attempt < 1 || (p.MaxAttempts > 0 && attempt > p.MaxAttempts) {
            return 0, false
        }
        n := p.nominal(attempt)
        m := mix(seed, attempt)
        switch p.Jitter {
        case JitterFull:
            return int64(m % uint64(n+1)), true
        case JitterEqual:
            half := n / 2
            return half + int64(m%uint64(n-half+1)), true
        }
        return n, true
    }

    // Schedule lists the delays a caller would wait through.
    func (p Policy) Schedule(seed uint64) ([]int64, error) {
        if err := p.Validate(); err != nil {
            return nil, err
        }
        if p.MaxAttempts == 0 && p.Budget == 0 {
            return nil, ErrUnbounded
        }
        var out []int64
        var total int64
        for a := 1; len(out) < MaxSchedule; a++ {
            d, ok := p.Delay(a, seed)
            if !ok {
                break
            }
            if p.Budget > 0 && total+d > p.Budget {
                break
            }
            total += d
            out = append(out, d)
        }
        return out, nil
    }

    // Tracker follows a failing operation.
    type Tracker struct {
        p        Policy
        seed     uint64
        count    int
        lastFail int64
        retryAt  int64
        gaveUp   bool
    }

    // NewTracker starts tracking with a valid policy.
    func NewTracker(p Policy, seed uint64) (*Tracker, error) {
        if err := p.Validate(); err != nil {
            return nil, err
        }
        return &Tracker{p: p, seed: seed}, nil
    }

    // Fail records a failure at time now.
    func (t *Tracker) Fail(now int64) (int64, bool) {
        if t.count > 0 && t.p.ResetAfter > 0 && now-t.lastFail >= t.p.ResetAfter {
            t.count = 0
            t.gaveUp = false
        }
        t.count++
        t.lastFail = now
        d, ok := t.p.Delay(t.count, t.seed)
        if !ok {
            t.gaveUp = true
            return 0, false
        }
        t.retryAt = now + d
        return t.retryAt, true
    }

    // Succeed forgets every failure.
    func (t *Tracker) Succeed() {
        t.count = 0
        t.gaveUp = false
    }

    // Attempts is the number of failures recorded since the last reset.
    func (t *Tracker) Attempts() int { return t.count }

    // Ready reports whether the operation may be tried again at time now.
    func (t *Tracker) Ready(now int64) bool {
        if t.count == 0 {
            return true
        }
        if t.gaveUp {
            return false
        }
        return now >= t.retryAt
    }
'''))

VISIBLE = gosrc(dd(r'''
    package retrywin

    import "testing"

    func TestPlainDoubling(t *testing.T) {
        p := Policy{Base: 100, Cap: 5000, Factor: 2, MaxAttempts: 4}
        got, err := p.Schedule(0)
        if err != nil || len(got) != 4 || got[0] != 100 || got[3] != 800 {
            t.Fatalf("got %v, %v", got, err)
        }
    }

    func TestTrackerFirstFailure(t *testing.T) {
        tr, _ := NewTracker(Policy{Base: 50, Cap: 1000, Factor: 2, MaxAttempts: 3}, 1)
        at, ok := tr.Fail(1000)
        if !ok || at != 1050 {
            t.Fatalf("got %d %v", at, ok)
        }
    }
'''))

HIDDEN = gosrc(dd(r'''
    package retrywin

    import (
        "errors"
        "reflect"
        "testing"
    )

    var base = Policy{Base: 100, Cap: 5000, Factor: 2, MaxAttempts: 8}

    func delays(p Policy, seed uint64, n int) []int64 {
        var out []int64
        for a := 1; a <= n; a++ {
            d, _ := p.Delay(a, seed)
            out = append(out, d)
        }
        return out
    }

    func TestNominalGrowth(t *testing.T) {
        got := delays(base, 0, 8)
        want := []int64{100, 200, 400, 800, 1600, 3200, 5000, 5000}
        if !reflect.DeepEqual(got, want) {
            t.Errorf("got %v", got)
        }
        p := Policy{Base: 7, Cap: 1000, Factor: 3}
        if got, want := delays(p, 0, 8), []int64{7, 21, 63, 189, 567, 1000, 1000, 1000}; !reflect.DeepEqual(got, want) {
            t.Errorf("factor 3: %v", got)
        }
        p = Policy{Base: 250, Cap: 250, Factor: 4}
        if got, want := delays(p, 0, 3), []int64{250, 250, 250}; !reflect.DeepEqual(got, want) {
            t.Errorf("cap == base: %v", got)
        }
        p = Policy{Base: 40, Cap: 900, Factor: 1}
        if got, want := delays(p, 0, 4), []int64{40, 40, 40, 40}; !reflect.DeepEqual(got, want) {
            t.Errorf("factor 1: %v", got)
        }
    }

    func TestCapIsExactNotRoundedDown(t *testing.T) {
        // 10 -> 30 -> 90 -> 270 -> 810 -> 1000 (not 2430)
        p := Policy{Base: 10, Cap: 1000, Factor: 3}
        if got, want := delays(p, 0, 7), []int64{10, 30, 90, 270, 810, 1000, 1000}; !reflect.DeepEqual(got, want) {
            t.Errorf("got %v", got)
        }
        // a step that lands exactly on the cap
        p = Policy{Base: 125, Cap: 1000, Factor: 2}
        if got, want := delays(p, 0, 5), []int64{125, 250, 500, 1000, 1000}; !reflect.DeepEqual(got, want) {
            t.Errorf("exact: %v", got)
        }
    }

    func TestCapBoundaryNotDivisible(t *testing.T) {
        // 333 * 3 = 999 is still below the cap of 1000, so it is not clamped
        p := Policy{Base: 37, Cap: 1000, Factor: 3}
        if got, want := delays(p, 0, 6), []int64{37, 111, 333, 999, 1000, 1000}; !reflect.DeepEqual(got, want) {
            t.Errorf("got %v", got)
        }
    }

    func TestNoOverflow(t *testing.T) {
        p := Policy{Base: 1, Cap: 1 << 62, Factor: 10}
        if d, ok := p.Delay(40, 0); !ok || d != 1<<62 {
            t.Errorf("attempt 40: %d %v", d, ok)
        }
        if d, ok := p.Delay(1000000, 0); !ok || d != 1<<62 {
            t.Errorf("attempt 1e6: %d %v", d, ok)
        }
        if d, ok := p.Delay(19, 0); !ok || d != 1000000000000000000 {
            t.Errorf("attempt 19: %d %v", d, ok)
        }
        p = Policy{Base: 1 << 40, Cap: 1<<63 - 1, Factor: 1 << 30}
        if d, ok := p.Delay(3, 0); !ok || d != 1<<63-1 {
            t.Errorf("huge factor: %d %v", d, ok)
        }
    }

    func TestDelayLimits(t *testing.T) {
        for _, a := range []int{0, -1, -100, 9, 10, 1000} {
            if d, ok := base.Delay(a, 5); ok || d != 0 {
                t.Errorf("attempt %d: %d %v", a, d, ok)
            }
        }
        if _, ok := base.Delay(8, 5); !ok {
            t.Errorf("attempt 8 should be allowed")
        }
        if _, ok := base.Delay(1, 5); !ok {
            t.Errorf("attempt 1 should be allowed")
        }
        unlimited := Policy{Base: 1, Cap: 10, Factor: 2}
        if d, ok := unlimited.Delay(500, 0); !ok || d != 10 {
            t.Errorf("unlimited: %d %v", d, ok)
        }
        if d, ok := unlimited.Delay(0, 0); ok || d != 0 {
            t.Errorf("unlimited attempt 0: %d %v", d, ok)
        }
    }

    func TestFullJitterLiterals(t *testing.T) {
        p := base
        p.Jitter = JitterFull
        cases := map[uint64][]int64{
            1:          {15, 7, 303, 398, 1531, 1343, 2874, 2268},
            42:         {23, 49, 111, 657, 1036, 2319, 3439, 2648},
            0xDEADBEEF: {81, 92, 324, 60, 1567, 245, 2042, 2527},
        }
        for seed, want := range cases {
            if got := delays(p, seed, 8); !reflect.DeepEqual(got, want) {
                t.Errorf("seed %d: got %v want %v", seed, got, want)
            }
        }
    }

    func TestEqualJitterLiterals(t *testing.T) {
        p := base
        p.Jitter = JitterEqual
        cases := map[uint64][]int64{
            1:          {94, 135, 263, 563, 857, 3053, 3244, 3003},
            42:         {63, 163, 233, 504, 1509, 2783, 3676, 4268},
            0xDEADBEEF: {69, 153, 241, 729, 1496, 3084, 3106, 4035},
        }
        for seed, want := range cases {
            if got := delays(p, seed, 8); !reflect.DeepEqual(got, want) {
                t.Errorf("seed %d: got %v want %v", seed, got, want)
            }
        }
    }

    func TestJitterRanges(t *testing.T) {
        for _, j := range []Jitter{JitterFull, JitterEqual} {
            p := Policy{Base: 3, Cap: 600, Factor: 2, Jitter: j}
            for seed := uint64(0); seed < 200; seed++ {
                for a := 1; a <= 12; a++ {
                    nominal := Policy{Base: 3, Cap: 600, Factor: 2}
                    n, _ := nominal.Delay(a, seed)
                    d, ok := p.Delay(a, seed)
                    lo := int64(0)
                    if j == JitterEqual {
                        lo = n / 2
                    }
                    if !ok || d < lo || d > n {
                        t.Fatalf("jitter %d seed %d attempt %d: %d outside [%d,%d]", j, seed, a, d, lo, n)
                    }
                }
            }
        }
        // jitter on a delay of 1: full gives 0 or 1, equal gives 0 or 1 (nominal/2 = 0)
        p := Policy{Base: 1, Cap: 1, Factor: 1, Jitter: JitterEqual}
        seen := map[int64]bool{}
        for seed := uint64(0); seed < 50; seed++ {
            d, _ := p.Delay(1, seed)
            seen[d] = true
        }
        if !seen[0] || !seen[1] || len(seen) != 2 {
            t.Errorf("equal jitter on 1: %v", seen)
        }
    }

    func TestSeedsDiffer(t *testing.T) {
        p := base
        p.Jitter = JitterFull
        if reflect.DeepEqual(delays(p, 1, 8), delays(p, 2, 8)) {
            t.Errorf("different seeds gave the same schedule")
        }
        if !reflect.DeepEqual(delays(p, 7, 8), delays(p, 7, 8)) {
            t.Errorf("same seed gave different schedules")
        }
    }

    func TestScheduleByAttempts(t *testing.T) {
        got, err := base.Schedule(0)
        want := []int64{100, 200, 400, 800, 1600, 3200, 5000, 5000}
        if err != nil || !reflect.DeepEqual(got, want) {
            t.Errorf("got %v, %v", got, err)
        }
        p := base
        p.Jitter = JitterFull
        got, _ = p.Schedule(42)
        if want := []int64{23, 49, 111, 657, 1036, 2319, 3439, 2648}; !reflect.DeepEqual(got, want) {
            t.Errorf("jittered: %v", got)
        }
    }

    func TestScheduleBudget(t *testing.T) {
        cases := []struct {
            budget int64
            want   []int64
        }{
            {1000, []int64{100, 200, 400}},
            {700, []int64{100, 200, 400}},
            {699, []int64{100, 200}},
            {100, []int64{100}},
            {99, nil},
            {1, nil},
            {20000, []int64{100, 200, 400, 800, 1600, 3200, 5000, 5000}},
            {16300, []int64{100, 200, 400, 800, 1600, 3200, 5000, 5000}},
            {16299, []int64{100, 200, 400, 800, 1600, 3200, 5000}},
        }
        for _, c := range cases {
            p := base
            p.Budget = c.budget
            got, err := p.Schedule(0)
            if err != nil || len(got) != len(c.want) || (len(got) > 0 && !reflect.DeepEqual(got, c.want)) {
                t.Errorf("budget %d: got %v, %v; want %v", c.budget, got, err, c.want)
            }
        }
    }

    func TestScheduleBudgetOnly(t *testing.T) {
        p := Policy{Base: 100, Cap: 100, Factor: 1, Budget: 450}
        got, err := p.Schedule(0)
        if err != nil || !reflect.DeepEqual(got, []int64{100, 100, 100, 100}) {
            t.Errorf("got %v, %v", got, err)
        }
        p.Budget = 500
        got, _ = p.Schedule(0)
        if len(got) != 5 {
            t.Errorf("exact budget: %v", got)
        }
    }

    func TestScheduleLengthCap(t *testing.T) {
        p := Policy{Base: 1, Cap: 1, Factor: 1, Budget: 1 << 40}
        got, err := p.Schedule(0)
        if err != nil || len(got) != 1000 {
            t.Errorf("budget-only: %d entries, %v", len(got), err)
        }
        p = Policy{Base: 1, Cap: 1, Factor: 1, MaxAttempts: 5000}
        got, _ = p.Schedule(0)
        if len(got) != 1000 {
            t.Errorf("attempts: %d entries", len(got))
        }
        p.MaxAttempts = 1000
        got, _ = p.Schedule(0)
        if len(got) != 1000 {
            t.Errorf("exactly 1000: %d entries", len(got))
        }
        p.MaxAttempts = 999
        got, _ = p.Schedule(0)
        if len(got) != 999 {
            t.Errorf("999: %d entries", len(got))
        }
    }

    func TestScheduleErrors(t *testing.T) {
        if _, err := (Policy{Base: 1, Cap: 10, Factor: 2}).Schedule(0); !errors.Is(err, ErrUnbounded) {
            t.Errorf("unbounded: %v", err)
        }
        if _, err := (Policy{Base: 0, Cap: 10, Factor: 2, MaxAttempts: 3}).Schedule(0); !errors.Is(err, ErrBadPolicy) {
            t.Errorf("bad policy: %v", err)
        }
        // validation comes before the unbounded check
        if _, err := (Policy{Base: 10, Cap: 5, Factor: 2}).Schedule(0); !errors.Is(err, ErrBadPolicy) {
            t.Errorf("bad and unbounded: %v", err)
        }
    }

    func TestValidate(t *testing.T) {
        good := []Policy{
            {Base: 1, Cap: 1, Factor: 1}, {Base: 5, Cap: 50, Factor: 2, MaxAttempts: 3, Budget: 10, ResetAfter: 1},
            {Base: 1, Cap: 2, Factor: 100, Jitter: JitterEqual},
        }
        for _, p := range good {
            if err := p.Validate(); err != nil {
                t.Errorf("%+v: %v", p, err)
            }
        }
        bad := []Policy{
            {Base: 0, Cap: 1, Factor: 1}, {Base: -1, Cap: 1, Factor: 1}, {Base: 5, Cap: 4, Factor: 1},
            {Base: 1, Cap: 1, Factor: 0}, {Base: 1, Cap: 1, Factor: -2}, {Base: 1, Cap: 1, Factor: 1, MaxAttempts: -1},
            {Base: 1, Cap: 1, Factor: 1, Budget: -1}, {Base: 1, Cap: 1, Factor: 1, ResetAfter: -1},
        }
        for _, p := range bad {
            if err := p.Validate(); !errors.Is(err, ErrBadPolicy) {
                t.Errorf("%+v: err = %v", p, err)
            }
            if _, err := NewTracker(p, 0); !errors.Is(err, ErrBadPolicy) {
                t.Errorf("NewTracker(%+v): err = %v", p, err)
            }
        }
    }

    func TestTrackerFlow(t *testing.T) {
        p := Policy{Base: 100, Cap: 5000, Factor: 2, MaxAttempts: 3}
        tr, err := NewTracker(p, 0)
        if err != nil {
            t.Fatal(err)
        }
        if !tr.Ready(0) || tr.Attempts() != 0 {
            t.Fatalf("fresh tracker not ready")
        }
        at, ok := tr.Fail(1000)
        if !ok || at != 1100 || tr.Attempts() != 1 {
            t.Fatalf("first: %d %v", at, ok)
        }
        if tr.Ready(1099) || !tr.Ready(1100) || !tr.Ready(5000) {
            t.Errorf("ready window wrong")
        }
        at, ok = tr.Fail(1100)
        if !ok || at != 1300 {
            t.Fatalf("second: %d %v", at, ok)
        }
        at, ok = tr.Fail(1300)
        if !ok || at != 1700 {
            t.Fatalf("third: %d %v", at, ok)
        }
        at, ok = tr.Fail(1700)
        if ok || at != 0 || tr.Attempts() != 4 {
            t.Fatalf("fourth: %d %v attempts=%d", at, ok, tr.Attempts())
        }
        if tr.Ready(1700) || tr.Ready(1 << 40) {
            t.Errorf("gave up but Ready")
        }
        tr.Succeed()
        if !tr.Ready(0) || tr.Attempts() != 0 {
            t.Errorf("Succeed did not reset")
        }
        if at, ok := tr.Fail(50); !ok || at != 150 {
            t.Errorf("after succeed: %d %v", at, ok)
        }
    }

    func TestTrackerUsesSeedAndJitter(t *testing.T) {
        p := base
        p.Jitter = JitterFull
        tr, _ := NewTracker(p, 42)
        now := int64(10)
        for i, d := range []int64{23, 49, 111, 657} {
            at, ok := tr.Fail(now)
            if !ok || at != now+d {
                t.Fatalf("failure %d: %d %v, want %d", i+1, at, ok, now+d)
            }
            now = at
        }
    }

    func TestTrackerResetAfter(t *testing.T) {
        p := Policy{Base: 100, Cap: 5000, Factor: 2, MaxAttempts: 5, ResetAfter: 1000}
        tr, _ := NewTracker(p, 0)
        tr.Fail(0)
        at, _ := tr.Fail(500)
        if at != 700 {
            t.Fatalf("second failure: %d", at)
        }
        at, _ = tr.Fail(1499) // 999 after the previous failure: not reset
        if at != 1499+400 || tr.Attempts() != 3 {
            t.Fatalf("999ms later: %d attempts=%d", at, tr.Attempts())
        }
        at, _ = tr.Fail(2499) // exactly 1000 after: reset
        if at != 2499+100 || tr.Attempts() != 1 {
            t.Fatalf("1000ms later: %d attempts=%d", at, tr.Attempts())
        }
        // the quiet time counts from the previous failure, not from the retry time
        tr2, _ := NewTracker(p, 0)
        tr2.Fail(0)
        tr2.Fail(100)
        at, _ = tr2.Fail(1099)
        if at != 1099+400 {
            t.Fatalf("not reset yet: %d", at)
        }
    }

    func TestResetAfterOneFailure(t *testing.T) {
        p := Policy{Base: 100, Cap: 5000, Factor: 2, MaxAttempts: 5, ResetAfter: 1000}
        tr, _ := NewTracker(p, 0)
        tr.Fail(0)
        at, _ := tr.Fail(1000)
        if at != 1100 || tr.Attempts() != 1 {
            t.Errorf("got %d attempts=%d", at, tr.Attempts())
        }
        p.ResetAfter = 1
        tr, _ = NewTracker(p, 0)
        tr.Fail(5)
        at, _ = tr.Fail(6)
        if at != 106 || tr.Attempts() != 1 {
            t.Errorf("ResetAfter 1: got %d attempts=%d", at, tr.Attempts())
        }
    }

    func TestSucceedClearsGiveUp(t *testing.T) {
        p := Policy{Base: 10, Cap: 100, Factor: 2, MaxAttempts: 1}
        tr, _ := NewTracker(p, 0)
        tr.Fail(0)
        tr.Fail(1)
        tr.Succeed()
        at, ok := tr.Fail(100)
        if !ok || at != 110 {
            t.Fatalf("got %d %v", at, ok)
        }
        if tr.Ready(109) || !tr.Ready(110) {
            t.Errorf("Ready after recovering from a give-up")
        }
    }

    func TestResetAfterClearsGiveUp(t *testing.T) {
        p := Policy{Base: 10, Cap: 100, Factor: 2, MaxAttempts: 1, ResetAfter: 500}
        tr, _ := NewTracker(p, 0)
        tr.Fail(0)
        if _, ok := tr.Fail(10); ok {
            t.Fatalf("should give up")
        }
        if tr.Ready(100) {
            t.Errorf("ready after give-up")
        }
        at, ok := tr.Fail(600)
        if !ok || at != 610 || !tr.Ready(610) || tr.Ready(609) {
            t.Errorf("after quiet period: %d %v", at, ok)
        }
    }

    func TestNoResetWithoutResetAfter(t *testing.T) {
        p := Policy{Base: 10, Cap: 1000, Factor: 2, MaxAttempts: 10}
        tr, _ := NewTracker(p, 0)
        tr.Fail(0)
        at, _ := tr.Fail(1 << 40)
        if at != 1<<40+20 {
            t.Errorf("got %d", at)
        }
    }

    func TestUnlimitedTrackerNeverGivesUp(t *testing.T) {
        p := Policy{Base: 1, Cap: 8, Factor: 2}
        tr, _ := NewTracker(p, 0)
        now := int64(0)
        for i := 0; i < 50; i++ {
            at, ok := tr.Fail(now)
            if !ok {
                t.Fatalf("gave up at failure %d", i+1)
            }
            now = at
        }
        if tr.Attempts() != 50 || tr.Ready(now-1) || !tr.Ready(now) {
            t.Errorf("attempts=%d", tr.Attempts())
        }
    }
'''))

LIB = Lib(
    name="retrywin", lang="go", title="the retrywin package",
    blurb="The job runner decides when to retry failed jobs with retrywin, which turns a back-off policy and a seed into delays and tracks repeated failures.",
    files={"go.mod": langs.go_mod("retrywin"), "retrywin.go": SRC, "README.md": README},
    visible_tests={"retrywin_basic_test.go": VISIBLE},
    hidden_tests={"retrywin_full_test.go": HIDDEN},
    mutate=["retrywin.go"], difficulty=3, tags=["backoff", "retry", "jitter"],
)

register_libs([LIB], n=8)
