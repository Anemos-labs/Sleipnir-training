"""Leased slot pool (go): expiring leases, fencing tokens, per-owner quota, renewal cap, single-threaded and clock-driven."""
from fx import Lib, dd, langs

from generators.fix._lang1 import gosrc, register_libs

README = dd('''
    # leasepool

    A bounded pool of numbered slots (licence seats, GPU partitions, worker ids) that clients borrow through *leases*. A lease
    expires by itself, so a crashed client cannot hold a slot forever. The pool is single-threaded and driven by an explicit clock:
    every method takes `now` (an `int64`, any unit) and `now` must never go backwards.

    ## `New(slots int, ttl, maxLife int64, perOwner int) (*Pool, error)`
    `slots`, `ttl`, `perOwner` must be at least 1 and `maxLife >= ttl`, otherwise `ErrConfig`.

    ## Leases
    ```go
    type Lease struct { Slot int; Token uint64; Owner string; Expires int64 }
    ```
    A lease is *live* from the moment it is granted until `now == Expires` (so it is live while `now < Expires`) or until it is released.
    Expired leases free their slot automatically; the slot may then be granted again.

    Every method first checks the clock (`ErrClock` when `now` is earlier than the latest `now` any method has seen; a rejected call
    changes nothing) and then reclaims the leases that have expired by `now` (each counts once in `Stats.Reclaimed`).

    * `Acquire(owner string, now int64) (Lease, error)`: an empty `owner` is `ErrBadOwner`; an owner that already holds `perOwner` live
      leases gets `ErrQuota`; when no slot is free `ErrFull`. Otherwise the **lowest-numbered** free slot is granted with
      `Expires = now + ttl` and a fresh `Token`: tokens are 1, 2, 3, ... in order of grant, across all slots.
    * `Renew(l Lease, now int64) (Lease, error)`: the lease must be the current live lease of its slot (same `Token`), otherwise
      `ErrStale`. The new expiry is `min(now + ttl, grantedAt + maxLife)` where `grantedAt` is the tick of the original `Acquire`. If that
      is not later than the current expiry the lease is already at its cap and the call fails with `ErrMaxLife` (nothing changes).
      Otherwise the returned lease carries the new `Expires` (the token stays).
    * `Release(l Lease, now int64) error`: frees the slot; `ErrStale` if `l` is not the current live lease of its slot (already released,
      expired, or the slot has since been granted to someone else).
    * `Holder(slot int, now int64) (owner string, ok bool, err error)`: who holds `slot`; `ok` is false for a free or unknown slot.
    * `Live(now int64) ([]Lease, error)`: all live leases ordered by slot.
    * `Stats(now int64) (Stats, error)`: `Stats{InUse, Free, Granted, Reclaimed, HighWater int}`: live leases, free slots, leases ever granted,
      leases that ended by expiring (not by `Release`), and the largest number of simultaneously live leases ever seen
      *right after a grant*.
''')

SRC = gosrc(dd(r'''
    // Package leasepool hands out expiring leases on numbered slots.
    package leasepool

    import "errors"

    var (
        ErrConfig   = errors.New("leasepool: invalid configuration")
        ErrClock    = errors.New("leasepool: time went backwards")
        ErrBadOwner = errors.New("leasepool: owner must not be empty")
        ErrQuota    = errors.New("leasepool: owner holds too many leases")
        ErrFull     = errors.New("leasepool: no free slot")
        ErrStale    = errors.New("leasepool: lease is no longer current")
        ErrMaxLife  = errors.New("leasepool: lease reached its maximum lifetime")
    )

    // Lease is a grant of one slot.
    type Lease struct {
        Slot    int
        Token   uint64
        Owner   string
        Expires int64
    }

    // Stats summarises the pool.
    type Stats struct {
        InUse, Free, Granted, Reclaimed, HighWater int
    }

    type slot struct {
        held    bool
        token   uint64
        owner   string
        granted int64
        expires int64
    }

    // Pool is the slot table.
    type Pool struct {
        slots     []slot
        ttl       int64
        maxLife   int64
        perOwner  int
        last      int64
        nextToken uint64
        granted   int
        reclaimed int
        highWater int
    }

    // New builds a pool.
    func New(slots int, ttl, maxLife int64, perOwner int) (*Pool, error) {
        if slots < 1 || ttl < 1 || perOwner < 1 || maxLife < ttl {
            return nil, ErrConfig
        }
        return &Pool{slots: make([]slot, slots), ttl: ttl, maxLife: maxLife, perOwner: perOwner, nextToken: 1}, nil
    }

    func (p *Pool) enter(now int64) error {
        if now < p.last {
            return ErrClock
        }
        p.last = now
        for i := range p.slots {
            if s := &p.slots[i]; s.held && now >= s.expires {
                s.held = false
                p.reclaimed++
            }
        }
        return nil
    }

    func (p *Pool) inUse() int {
        n := 0
        for _, s := range p.slots {
            if s.held {
                n++
            }
        }
        return n
    }

    func (p *Pool) current(l Lease) *slot {
        if l.Slot < 0 || l.Slot >= len(p.slots) {
            return nil
        }
        if s := &p.slots[l.Slot]; s.held && s.token == l.Token {
            return s
        }
        return nil
    }

    // Acquire grants the lowest free slot to owner.
    func (p *Pool) Acquire(owner string, now int64) (Lease, error) {
        if err := p.enter(now); err != nil {
            return Lease{}, err
        }
        if owner == "" {
            return Lease{}, ErrBadOwner
        }
        held := 0
        for _, s := range p.slots {
            if s.held && s.owner == owner {
                held++
            }
        }
        if held >= p.perOwner {
            return Lease{}, ErrQuota
        }
        for i := range p.slots {
            if p.slots[i].held {
                continue
            }
            s := slot{held: true, token: p.nextToken, owner: owner, granted: now, expires: now + p.ttl}
            p.nextToken++
            p.slots[i] = s
            p.granted++
            if n := p.inUse(); n > p.highWater {
                p.highWater = n
            }
            return Lease{Slot: i, Token: s.token, Owner: owner, Expires: s.expires}, nil
        }
        return Lease{}, ErrFull
    }

    // Renew extends a live lease, up to its maximum lifetime.
    func (p *Pool) Renew(l Lease, now int64) (Lease, error) {
        if err := p.enter(now); err != nil {
            return Lease{}, err
        }
        s := p.current(l)
        if s == nil {
            return Lease{}, ErrStale
        }
        next := min(now+p.ttl, s.granted+p.maxLife)
        if next <= s.expires {
            return Lease{}, ErrMaxLife
        }
        s.expires = next
        l.Expires = next
        return l, nil
    }

    // Release gives a slot back early.
    func (p *Pool) Release(l Lease, now int64) error {
        if err := p.enter(now); err != nil {
            return err
        }
        s := p.current(l)
        if s == nil {
            return ErrStale
        }
        s.held = false
        return nil
    }

    // Holder reports who holds a slot.
    func (p *Pool) Holder(slot int, now int64) (string, bool, error) {
        if err := p.enter(now); err != nil {
            return "", false, err
        }
        if slot < 0 || slot >= len(p.slots) || !p.slots[slot].held {
            return "", false, nil
        }
        return p.slots[slot].owner, true, nil
    }

    // Live lists live leases by slot.
    func (p *Pool) Live(now int64) ([]Lease, error) {
        if err := p.enter(now); err != nil {
            return nil, err
        }
        var out []Lease
        for i, s := range p.slots {
            if s.held {
                out = append(out, Lease{Slot: i, Token: s.token, Owner: s.owner, Expires: s.expires})
            }
        }
        return out, nil
    }

    // Stats returns the counters.
    func (p *Pool) Stats(now int64) (Stats, error) {
        if err := p.enter(now); err != nil {
            return Stats{}, err
        }
        n := p.inUse()
        return Stats{InUse: n, Free: len(p.slots) - n, Granted: p.granted, Reclaimed: p.reclaimed, HighWater: p.highWater}, nil
    }
'''))

VISIBLE = gosrc(dd(r'''
    package leasepool

    import "testing"

    func TestAcquireLowestSlot(t *testing.T) {
        p, err := New(3, 10, 30, 2)
        if err != nil {
            t.Fatal(err)
        }
        a, _ := p.Acquire("alice", 0)
        b, _ := p.Acquire("bob", 0)
        if a.Slot != 0 || b.Slot != 1 || a.Token != 1 || b.Token != 2 {
            t.Fatalf("got %+v and %+v", a, b)
        }
    }

    func TestConfigRejected(t *testing.T) {
        if _, err := New(0, 10, 30, 1); err == nil {
            t.Fatal("0 slots should fail")
        }
    }
'''))

HIDDEN = gosrc(dd(r'''
    package leasepool

    import (
        "errors"
        "reflect"
        "testing"
    )

    func mustNew(t *testing.T, slots int, ttl, maxLife int64, perOwner int) *Pool {
        t.Helper()
        p, err := New(slots, ttl, maxLife, perOwner)
        if err != nil {
            t.Fatal(err)
        }
        return p
    }

    func acquire(t *testing.T, p *Pool, owner string, now int64) Lease {
        t.Helper()
        l, err := p.Acquire(owner, now)
        if err != nil {
            t.Fatalf("Acquire(%q, %d): %v", owner, now, err)
        }
        return l
    }

    func stats(t *testing.T, p *Pool, now int64) Stats {
        t.Helper()
        s, err := p.Stats(now)
        if err != nil {
            t.Fatal(err)
        }
        return s
    }

    func TestConfigErrors(t *testing.T) {
        bad := [][4]int64{{0, 10, 30, 1}, {-1, 10, 30, 1}, {2, 0, 30, 1}, {2, -5, 30, 1}, {2, 10, 9, 1}, {2, 10, 30, 0}, {2, 10, 30, -1}}
        for _, c := range bad {
            if _, err := New(int(c[0]), c[1], c[2], int(c[3])); !errors.Is(err, ErrConfig) {
                t.Errorf("New%v: %v", c, err)
            }
        }
        if _, err := New(1, 10, 10, 1); err != nil {
            t.Errorf("maxLife == ttl should be fine: %v", err)
        }
    }

    func TestLowestFreeSlotAndTokens(t *testing.T) {
        p := mustNew(t, 3, 10, 50, 3)
        a := acquire(t, p, "a", 0)
        b := acquire(t, p, "b", 1)
        c := acquire(t, p, "c", 2)
        if a.Slot != 0 || b.Slot != 1 || c.Slot != 2 {
            t.Fatalf("slots %d %d %d", a.Slot, b.Slot, c.Slot)
        }
        if a.Token != 1 || b.Token != 2 || c.Token != 3 {
            t.Fatalf("tokens %d %d %d", a.Token, b.Token, c.Token)
        }
        if a.Expires != 10 || b.Expires != 11 || c.Expires != 12 || a.Owner != "a" {
            t.Fatalf("leases %+v %+v %+v", a, b, c)
        }
        if _, err := p.Acquire("d", 3); !errors.Is(err, ErrFull) {
            t.Fatalf("full: %v", err)
        }
        if err := p.Release(b, 4); err != nil {
            t.Fatal(err)
        }
        d := acquire(t, p, "d", 5)
        if d.Slot != 1 || d.Token != 4 {
            t.Fatalf("reused slot: %+v", d)
        }
        if err := p.Release(a, 6); err != nil {
            t.Fatal(err)
        }
        e := acquire(t, p, "e", 6)
        if e.Slot != 0 || e.Token != 5 {
            t.Fatalf("lowest free: %+v", e)
        }
    }

    func TestExpiryBoundary(t *testing.T) {
        p := mustNew(t, 1, 10, 50, 1)
        a := acquire(t, p, "a", 100)
        if a.Expires != 110 {
            t.Fatalf("expires %d", a.Expires)
        }
        if _, err := p.Acquire("b", 109); !errors.Is(err, ErrFull) {
            t.Fatalf("at 109 the lease is still live: %v", err)
        }
        b, err := p.Acquire("b", 110)
        if err != nil || b.Slot != 0 || b.Owner != "b" {
            t.Fatalf("at 110 the slot is free again: %+v %v", b, err)
        }
        if s := stats(t, p, 110); s.Reclaimed != 1 || s.InUse != 1 || s.Granted != 2 {
            t.Fatalf("stats %+v", s)
        }
    }

    func TestRenew(t *testing.T) {
        p := mustNew(t, 2, 10, 25, 2)
        a := acquire(t, p, "a", 0)
        a2, err := p.Renew(a, 5)
        if err != nil || a2.Expires != 15 || a2.Token != a.Token || a2.Slot != a.Slot || a2.Owner != "a" {
            t.Fatalf("renew: %+v %v", a2, err)
        }
        a3, err := p.Renew(a2, 14)
        if err != nil || a3.Expires != 24 {
            t.Fatalf("second renew: %+v %v", a3, err)
        }
        // cap: granted at 0, maxLife 25 -> 25 at most
        a4, err := p.Renew(a3, 20)
        if err != nil || a4.Expires != 25 {
            t.Fatalf("capped renew: %+v %v", a4, err)
        }
        if _, err := p.Renew(a4, 21); !errors.Is(err, ErrMaxLife) {
            t.Fatalf("at the cap: %v", err)
        }
        if _, err := p.Renew(a4, 24); !errors.Is(err, ErrMaxLife) {
            t.Fatalf("still at the cap: %v", err)
        }
        // the Expires inside the lease value is not trusted: the pool's own record decides
        stale := a
        stale.Expires = 9999
        if _, err := p.Renew(stale, 24); !errors.Is(err, ErrMaxLife) {
            t.Fatalf("forged expiry: %v", err)
        }
        if _, err := p.Renew(a4, 25); !errors.Is(err, ErrStale) {
            t.Fatalf("expired lease cannot be renewed: %v", err)
        }
    }

    func TestRenewThatDoesNotExtendIsRejected(t *testing.T) {
        p := mustNew(t, 1, 10, 100, 1)
        a := acquire(t, p, "a", 0)
        // renewing at time 0 would give the same expiry (0 + 10): nothing to extend
        if _, err := p.Renew(a, 0); !errors.Is(err, ErrMaxLife) {
            t.Fatalf("no extension: %v", err)
        }
        // one tick later it does extend by one
        a2, err := p.Renew(a, 1)
        if err != nil || a2.Expires != 11 {
            t.Fatalf("renew at 1: %+v %v", a2, err)
        }
    }

    func TestStaleLeases(t *testing.T) {
        p := mustNew(t, 1, 10, 50, 1)
        a := acquire(t, p, "a", 0)
        if err := p.Release(a, 1); err != nil {
            t.Fatal(err)
        }
        if err := p.Release(a, 2); !errors.Is(err, ErrStale) {
            t.Errorf("double release: %v", err)
        }
        if _, err := p.Renew(a, 2); !errors.Is(err, ErrStale) {
            t.Errorf("renew after release: %v", err)
        }
        b := acquire(t, p, "b", 3)
        // slot 0 now belongs to b: a's old lease must not touch it
        if err := p.Release(a, 4); !errors.Is(err, ErrStale) {
            t.Errorf("release with an old token: %v", err)
        }
        if _, err := p.Renew(a, 4); !errors.Is(err, ErrStale) {
            t.Errorf("renew with an old token: %v", err)
        }
        if owner, ok, _ := p.Holder(0, 4); !ok || owner != "b" {
            t.Errorf("holder %q %v", owner, ok)
        }
        if err := p.Release(b, 5); err != nil {
            t.Errorf("b's own release: %v", err)
        }
        for _, bogus := range []Lease{{Slot: -1, Token: 1}, {Slot: 1, Token: 1}, {Slot: 7, Token: 3}} {
            if err := p.Release(bogus, 6); !errors.Is(err, ErrStale) {
                t.Errorf("Release(%+v): %v", bogus, err)
            }
            if _, err := p.Renew(bogus, 6); !errors.Is(err, ErrStale) {
                t.Errorf("Renew(%+v): %v", bogus, err)
            }
        }
    }

    func TestExpiredLeaseCannotBeReleasedOrRenewed(t *testing.T) {
        p := mustNew(t, 2, 10, 50, 1)
        a := acquire(t, p, "a", 0)
        if err := p.Release(a, 10); !errors.Is(err, ErrStale) {
            t.Errorf("release at expiry: %v", err)
        }
        a = acquire(t, p, "a", 10)
        if _, err := p.Renew(a, 19); err != nil {
            t.Errorf("renew just before expiry: %v", err)
        }
        s := stats(t, p, 19)
        if s.Reclaimed != 1 {
            t.Errorf("stats %+v", s)
        }
    }

    func TestQuotaCountsLiveLeasesOnly(t *testing.T) {
        p := mustNew(t, 5, 10, 50, 2)
        a1 := acquire(t, p, "a", 0)
        acquire(t, p, "a", 1)
        if _, err := p.Acquire("a", 2); !errors.Is(err, ErrQuota) {
            t.Fatalf("third: %v", err)
        }
        if _, err := p.Acquire("b", 2); err != nil {
            t.Fatalf("another owner: %v", err)
        }
        if err := p.Release(a1, 3); err != nil {
            t.Fatal(err)
        }
        if _, err := p.Acquire("a", 3); err != nil {
            t.Fatalf("after a release: %v", err)
        }
        if _, err := p.Acquire("a", 4); !errors.Is(err, ErrQuota) {
            t.Fatalf("again at quota: %v", err)
        }
        // everything held by "a" expires at 10 and 11 / 13
        if _, err := p.Acquire("a", 13); err != nil {
            t.Fatalf("after expiry: %v", err)
        }
    }

    func TestQuotaBeforeFull(t *testing.T) {
        p := mustNew(t, 1, 10, 50, 1)
        acquire(t, p, "a", 0)
        if _, err := p.Acquire("a", 1); !errors.Is(err, ErrQuota) {
            t.Errorf("quota should win over full: %v", err)
        }
        if _, err := p.Acquire("b", 1); !errors.Is(err, ErrFull) {
            t.Errorf("full: %v", err)
        }
        if _, err := p.Acquire("", 1); !errors.Is(err, ErrBadOwner) {
            t.Errorf("empty owner: %v", err)
        }
    }

    func TestClockRules(t *testing.T) {
        p := mustNew(t, 2, 10, 50, 1)
        a := acquire(t, p, "a", 20)
        if _, err := p.Acquire("b", 19); !errors.Is(err, ErrClock) {
            t.Errorf("Acquire in the past: %v", err)
        }
        if _, err := p.Renew(a, 19); !errors.Is(err, ErrClock) {
            t.Errorf("Renew in the past: %v", err)
        }
        if err := p.Release(a, 19); !errors.Is(err, ErrClock) {
            t.Errorf("Release in the past: %v", err)
        }
        if _, _, err := p.Holder(0, 19); !errors.Is(err, ErrClock) {
            t.Errorf("Holder in the past: %v", err)
        }
        if _, err := p.Live(19); !errors.Is(err, ErrClock) {
            t.Errorf("Live in the past: %v", err)
        }
        if _, err := p.Stats(19); !errors.Is(err, ErrClock) {
            t.Errorf("Stats in the past: %v", err)
        }
        // a rejected call changes nothing: the lease is still there and the same instant is allowed
        if _, ok, err := p.Holder(0, 20); !ok || err != nil {
            t.Errorf("holder after rejected calls: %v %v", ok, err)
        }
        // the clock check comes before the owner check
        if _, err := p.Acquire("", 5); !errors.Is(err, ErrClock) {
            t.Errorf("clock before owner: %v", err)
        }
    }

    func TestReadsAdvanceTheClockAndReap(t *testing.T) {
        p := mustNew(t, 2, 10, 50, 2)
        acquire(t, p, "a", 0)
        if s := stats(t, p, 50); s.Reclaimed != 1 || s.InUse != 0 || s.Free != 2 {
            t.Errorf("stats %+v", s)
        }
        if _, err := p.Acquire("b", 40); !errors.Is(err, ErrClock) {
            t.Errorf("Stats moved the clock: %v", err)
        }
    }

    func TestHolderAndLive(t *testing.T) {
        p := mustNew(t, 4, 10, 50, 2)
        a := acquire(t, p, "a", 0)
        b := acquire(t, p, "b", 1)
        c := acquire(t, p, "c", 2)
        if err := p.Release(b, 3); err != nil {
            t.Fatal(err)
        }
        live, err := p.Live(4)
        if err != nil || !reflect.DeepEqual(live, []Lease{a, c}) {
            t.Fatalf("live %+v %v", live, err)
        }
        for slot, want := range map[int]string{0: "a", 2: "c"} {
            if owner, ok, _ := p.Holder(slot, 4); !ok || owner != want {
                t.Errorf("Holder(%d) = %q %v", slot, owner, ok)
            }
        }
        for _, slot := range []int{1, 3, -1, 4, 100} {
            if owner, ok, err := p.Holder(slot, 4); ok || owner != "" || err != nil {
                t.Errorf("Holder(%d) = %q %v %v", slot, owner, ok, err)
            }
        }
        live, _ = p.Live(10)
        if !reflect.DeepEqual(live, []Lease{c}) {
            t.Errorf("a expired at 10: %+v", live)
        }
        live, _ = p.Live(12)
        if len(live) != 0 {
            t.Errorf("all expired: %+v", live)
        }
        if _, ok, _ := p.Holder(0, 12); ok {
            t.Errorf("expired slot has a holder")
        }
    }

    func TestRenewedLeaseShowsUpInLive(t *testing.T) {
        p := mustNew(t, 2, 10, 50, 1)
        a := acquire(t, p, "a", 0)
        a2, _ := p.Renew(a, 4)
        live, _ := p.Live(5)
        if len(live) != 1 || live[0] != a2 || live[0].Expires != 14 {
            t.Errorf("live %+v", live)
        }
        if _, err := p.Acquire("z", 12); err != nil {
            t.Errorf("slot 1 is free: %v", err)
        }
        if s := stats(t, p, 13); s.InUse != 2 {
            t.Errorf("a's renewed lease is live at 13: %+v", s)
        }
        if s := stats(t, p, 14); s.InUse != 1 || s.Reclaimed != 1 {
            t.Errorf("a's lease ended at 14: %+v", s)
        }
    }

    func TestStatsCounters(t *testing.T) {
        p := mustNew(t, 3, 10, 50, 3)
        if s := stats(t, p, 0); s != (Stats{Free: 3}) {
            t.Fatalf("fresh: %+v", s)
        }
        a := acquire(t, p, "a", 0)
        acquire(t, p, "b", 0)
        acquire(t, p, "c", 0)
        if s := stats(t, p, 1); s != (Stats{InUse: 3, Granted: 3, HighWater: 3}) {
            t.Fatalf("full: %+v", s)
        }
        p.Release(a, 2)
        if s := stats(t, p, 2); s != (Stats{InUse: 2, Free: 1, Granted: 3, HighWater: 3}) {
            t.Fatalf("after release: %+v", s)
        }
        // b and c expire at 10: both reclaimed; the high-water mark stays
        if s := stats(t, p, 10); s != (Stats{Free: 3, Granted: 3, Reclaimed: 2, HighWater: 3}) {
            t.Fatalf("after expiry: %+v", s)
        }
        acquire(t, p, "d", 11)
        if s := stats(t, p, 11); s != (Stats{InUse: 1, Free: 2, Granted: 4, Reclaimed: 2, HighWater: 3}) {
            t.Fatalf("later: %+v", s)
        }
    }

    func TestHighWaterIsMeasuredAfterGrants(t *testing.T) {
        p := mustNew(t, 4, 5, 50, 4)
        acquire(t, p, "a", 0)
        acquire(t, p, "b", 1)
        // both expire at 5 and 6; at 7 only a grant is made, so the peak stays at 2
        acquire(t, p, "c", 7)
        if s := stats(t, p, 7); s.HighWater != 2 || s.InUse != 1 {
            t.Errorf("stats %+v", s)
        }
        acquire(t, p, "d", 8)
        acquire(t, p, "e", 8)
        if s := stats(t, p, 8); s.HighWater != 3 {
            t.Errorf("stats %+v", s)
        }
    }

    func TestFencingTokensNeverRepeat(t *testing.T) {
        p := mustNew(t, 2, 3, 10, 2)
        seen := map[uint64]bool{}
        var last uint64
        for i := int64(0); i < 60; i++ {
            l, err := p.Acquire([]string{"x", "y", "z"}[i%3], i)
            if err != nil {
                continue
            }
            if seen[l.Token] || l.Token <= last {
                t.Fatalf("token %d reused or out of order (last %d)", l.Token, last)
            }
            seen[l.Token] = true
            last = l.Token
        }
        if len(seen) < 20 {
            t.Errorf("only %d grants", len(seen))
        }
    }
'''))

LIB = Lib(
    name="leasepool", lang="go", title="the leasepool package",
    blurb="The licence server hands out numbered seats through leasepool, a clock-driven pool of expiring leases with fencing tokens and per-owner quotas.",
    files={"go.mod": langs.go_mod("leasepool"), "leasepool.go": SRC, "README.md": README},
    visible_tests={"leasepool_basic_test.go": VISIBLE},
    hidden_tests={"leasepool_full_test.go": HIDDEN},
    mutate=["leasepool.go"], difficulty=2, tags=["pool", "leases", "expiry"],
)

register_libs([LIB], n=8)
