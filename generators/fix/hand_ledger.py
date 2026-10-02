"""A layered stock ledger in go: parsing, state machine, replay with snapshots and a live feed. Several defects
show up in a different layer than the one that holds the cause."""
from fx import dd, langs, family
from generators.fix._hand_kit import Base, Bug, tabify, tab_pairs, tasks_from

README = dd('''
    # ledger

    The stock ledger of a small distribution centre, as a Go package (`example.com/ledger`, files `event.go`,
    `state.go`, `log.go`, `snapshot.go`, `replay.go`, `feed.go`).

    Stock changes are *events* in an append-only log. Every event has a sequence number (`Seq`: 1, 2, 3, ... without
    gaps in a complete log), an idempotency key (`Key`, may be empty), a SKU, a kind and a quantity.

    ## Applying events (`State.Apply`)

    * `receive` adds `Qty` to the stock of the SKU, `ship` subtracts it, `adjust` *sets* the stock to `Qty` (a stock-take
      count, not a delta).
    * `receive` and `ship` need `Qty > 0`, `adjust` needs `Qty >= 0`; the SKU must not be empty and the kind must be
      one of the three. Otherwise the event is rejected with `ErrBadEvent`.
    * A `ship` for more than is in stock is rejected with `ErrInsufficient`; nothing is shipped partially.
    * A rejected event changes no stock and is appended to `State.Rejected` (sequence number, key, reason).
    * Idempotency: if the `Key` is not empty and an earlier event with this key was *applied*, the event is ignored
      (no change, not a rejection). A rejected event does not use up its key: a later retry with the same key is
      processed normally. Keys are recorded for applied events only.
    * `State.Applied` is the highest sequence number consumed, whatever happened to the event (applied, ignored as a
      duplicate, or rejected).

    ## Reading and merging logs

    * `Parse(text)` reads one event per line, `seq|key|sku|kind|qty`. Blank lines and lines starting with `#` are
      skipped. A bad line makes `Parse` fail with an error that starts with `line N:` where N is the 1-based line
      number in the text (skipped lines count). The kind is not validated by `Parse`.
    * `Merge(shards...)` returns the events of all shards ordered by `Seq`; events with equal `Seq` keep the order of
      the arguments.

    ## Replay and snapshots

    * `Replay(events, snap)` sorts the events by `Seq` (stable) and applies those with `Seq > snap.Applied` on top of
      the state restored from `snap` (`nil`: an empty state). So an event that appears twice in the input (overlapping
      shards) is applied once.
    * `Take(state)` captures `Applied`, the stock and the keys. A snapshot is independent of the state it was taken
      from, and `Restore(snap)` builds a new independent state: replaying from the same snapshot twice gives the same
      result. The invariant that holds the design together: for every split point k,
      `Replay(all[k:], Take(Replay(all[:k], nil)))` equals `Replay(all, nil)` (stock, keys and `Applied`).

    ## Live feed

    `Feed` consumes events that may arrive in any order and more than once. `Push(e)` returns the sequence numbers
    applied by this call, in order. Events are applied strictly in sequence order, starting after the snapshot's
    `Applied` (or at 1): an event ahead of a gap waits in the pending buffer (`Pending()` counts them). An event whose
    `Seq` is already consumed, or already pending, is dropped (the first copy wins). When all events have arrived, the
    feed's state equals `Replay` of the same events.
''')

EVENT = dd('''
    package ledger

    import "errors"

    // Kind is the type of a stock event.
    type Kind string

    const (
        Receive Kind = "receive"
        Ship    Kind = "ship"
        Adjust  Kind = "adjust"
    )

    var (
        ErrBadEvent     = errors.New("ledger: bad event")
        ErrInsufficient = errors.New("ledger: insufficient stock")
    )

    // Event is one line of the stock log.
    type Event struct {
        Seq  int64
        Key  string
        SKU  string
        Kind Kind
        Qty  int
    }
''')

STATE = dd('''
    package ledger

    import "fmt"

    // Rejection records an event that was refused.
    type Rejection struct {
        Seq    int64
        Key    string
        Reason error
    }

    // State is the stock after a prefix of the log.
    type State struct {
        Stock    map[string]int
        Keys     map[string]bool // keys of applied events
        Applied  int64           // highest sequence number consumed
        Rejected []Rejection
    }

    func NewState() *State {
        return &State{Stock: map[string]int{}, Keys: map[string]bool{}}
    }

    // Apply consumes one event.
    func (s *State) Apply(e Event) {
        s.Applied = e.Seq
        if e.Key != "" && s.Keys[e.Key] {
            return
        }
        if err := s.check(e); err != nil {
            s.Rejected = append(s.Rejected, Rejection{Seq: e.Seq, Key: e.Key, Reason: err})
            return
        }
        switch e.Kind {
        case Receive:
            s.Stock[e.SKU] += e.Qty
        case Ship:
            s.Stock[e.SKU] -= e.Qty
        case Adjust:
            s.Stock[e.SKU] = e.Qty
        }
        if e.Key != "" {
            s.Keys[e.Key] = true
        }
    }

    func (s *State) check(e Event) error {
        if e.SKU == "" {
            return fmt.Errorf("%w: empty sku", ErrBadEvent)
        }
        switch e.Kind {
        case Receive, Ship:
            if e.Qty <= 0 {
                return fmt.Errorf("%w: quantity %d", ErrBadEvent, e.Qty)
            }
            if e.Kind == Ship && s.Stock[e.SKU] < e.Qty {
                return fmt.Errorf("%w: %s has %d, need %d", ErrInsufficient, e.SKU, s.Stock[e.SKU], e.Qty)
            }
        case Adjust:
            if e.Qty < 0 {
                return fmt.Errorf("%w: count %d", ErrBadEvent, e.Qty)
            }
        default:
            return fmt.Errorf("%w: kind %q", ErrBadEvent, e.Kind)
        }
        return nil
    }
''')

LOG = dd('''
    package ledger

    import (
        "fmt"
        "sort"
        "strconv"
        "strings"
    )

    // Parse reads a shard file: one event per line, "seq|key|sku|kind|qty".
    func Parse(text string) ([]Event, error) {
        var out []Event
        for i, raw := range strings.Split(text, "\\n") {
            line := strings.TrimSpace(raw)
            if line == "" || strings.HasPrefix(line, "#") {
                continue
            }
            e, err := parseLine(line)
            if err != nil {
                return nil, fmt.Errorf("line %d: %w", i+1, err)
            }
            out = append(out, e)
        }
        return out, nil
    }

    func parseLine(line string) (Event, error) {
        f := strings.Split(line, "|")
        if len(f) != 5 {
            return Event{}, fmt.Errorf("want 5 fields, got %d", len(f))
        }
        seq, err := strconv.ParseInt(strings.TrimSpace(f[0]), 10, 64)
        if err != nil || seq < 1 {
            return Event{}, fmt.Errorf("bad sequence number %q", f[0])
        }
        qty, err := strconv.Atoi(strings.TrimSpace(f[4]))
        if err != nil {
            return Event{}, fmt.Errorf("bad quantity %q", f[4])
        }
        return Event{
            Seq:  seq,
            Key:  strings.TrimSpace(f[1]),
            SKU:  strings.TrimSpace(f[2]),
            Kind: Kind(strings.TrimSpace(f[3])),
            Qty:  qty,
        }, nil
    }

    // Merge returns the events of all shards ordered by Seq.
    func Merge(shards ...[]Event) []Event {
        var all []Event
        for _, s := range shards {
            all = append(all, s...)
        }
        sort.SliceStable(all, func(i, j int) bool { return all[i].Seq < all[j].Seq })
        return all
    }
''')

SNAPSHOT = dd('''
    package ledger

    // Snapshot is a frozen copy of a State, used to restart a replay.
    type Snapshot struct {
        Applied int64
        Stock   map[string]int
        Keys    map[string]bool
    }

    // Take captures the state; the snapshot does not change when the state does.
    func Take(s *State) *Snapshot {
        return &Snapshot{Applied: s.Applied, Stock: copyStock(s.Stock), Keys: copyKeys(s.Keys)}
    }

    // Restore builds a new, independent state from a snapshot (nil: empty).
    func Restore(snap *Snapshot) *State {
        s := NewState()
        if snap == nil {
            return s
        }
        s.Applied = snap.Applied
        s.Stock = copyStock(snap.Stock)
        s.Keys = copyKeys(snap.Keys)
        return s
    }

    func copyStock(m map[string]int) map[string]int {
        out := make(map[string]int, len(m))
        for k, v := range m {
            out[k] = v
        }
        return out
    }

    func copyKeys(m map[string]bool) map[string]bool {
        out := make(map[string]bool, len(m))
        for k, v := range m {
            out[k] = v
        }
        return out
    }
''')

REPLAY = dd('''
    package ledger

    import "sort"

    // Replay applies the events, in sequence order, on top of the snapshot (nil: from scratch).
    func Replay(events []Event, snap *Snapshot) *State {
        s := Restore(snap)
        evs := append([]Event(nil), events...)
        sort.SliceStable(evs, func(i, j int) bool { return evs[i].Seq < evs[j].Seq })
        for _, e := range evs {
            if e.Seq <= s.Applied {
                continue
            }
            s.Apply(e)
        }
        return s
    }
''')

FEED = dd('''
    package ledger

    // Feed applies events that arrive in any order, strictly in sequence order.
    type Feed struct {
        state   *State
        pending map[int64]Event
    }

    func NewFeed(snap *Snapshot) *Feed {
        return &Feed{state: Restore(snap), pending: map[int64]Event{}}
    }

    func (f *Feed) State() *State { return f.state }

    // Pending is the number of events waiting for a gap to be filled.
    func (f *Feed) Pending() int { return len(f.pending) }

    // Push offers one event and returns the sequence numbers applied by this call.
    func (f *Feed) Push(e Event) []int64 {
        if e.Seq <= f.state.Applied {
            return nil
        }
        if _, dup := f.pending[e.Seq]; dup {
            return nil
        }
        f.pending[e.Seq] = e
        var done []int64
        for {
            next, ok := f.pending[f.state.Applied+1]
            if !ok {
                break
            }
            delete(f.pending, next.Seq)
            f.state.Apply(next)
            done = append(done, next.Seq)
        }
        return done
    }
''')

VISIBLE = {
    "ledger_test.go": dd('''
        package ledger

        import (
            "errors"
            "testing"
        )

        func TestReceiveShipAndRefuse(t *testing.T) {
            s := NewState()
            s.Apply(Event{Seq: 1, Key: "a", SKU: "bolt", Kind: Receive, Qty: 10})
            s.Apply(Event{Seq: 2, Key: "b", SKU: "bolt", Kind: Ship, Qty: 4})
            s.Apply(Event{Seq: 3, Key: "c", SKU: "bolt", Kind: Ship, Qty: 7})
            if s.Stock["bolt"] != 6 {
                t.Fatalf("stock = %d, want 6", s.Stock["bolt"])
            }
            if len(s.Rejected) != 1 || !errors.Is(s.Rejected[0].Reason, ErrInsufficient) {
                t.Fatalf("rejected = %+v", s.Rejected)
            }
            if s.Applied != 3 {
                t.Fatalf("applied = %d, want 3", s.Applied)
            }
        }

        func TestSameKeyIsAppliedOnce(t *testing.T) {
            s := NewState()
            s.Apply(Event{Seq: 1, Key: "a", SKU: "nut", Kind: Receive, Qty: 5})
            s.Apply(Event{Seq: 2, Key: "a", SKU: "nut", Kind: Receive, Qty: 5})
            if s.Stock["nut"] != 5 {
                t.Fatalf("stock = %d, want 5", s.Stock["nut"])
            }
        }

        func TestReplayOfSortedEvents(t *testing.T) {
            evs := []Event{
                {Seq: 1, SKU: "x", Kind: Receive, Qty: 3},
                {Seq: 2, SKU: "x", Kind: Ship, Qty: 1},
            }
            s := Replay(evs, nil)
            if s.Stock["x"] != 2 || s.Applied != 2 {
                t.Fatalf("got %+v", s)
            }
        }

        func TestParseSimple(t *testing.T) {
            evs, err := Parse("1|k1|bolt|receive|10\\n2||bolt|ship|3\\n")
            if err != nil || len(evs) != 2 || evs[1].Qty != 3 || evs[0].Key != "k1" {
                t.Fatalf("got %+v, %v", evs, err)
            }
        }
    '''),
}

HIDDEN = {
    "ledger_hidden_test.go": dd('''
        package ledger

        import (
            "errors"
            "fmt"
            "sort"
            "strings"
            "testing"
        )

        // ---- an independent model of the specification -------------------------------------------------------

        type model struct {
            stock    map[string]int
            keys     map[string]bool
            applied  int64
            rejected int
        }

        func newModel() *model { return &model{stock: map[string]int{}, keys: map[string]bool{}} }

        func (m *model) apply(e Event) {
            m.applied = e.Seq
            if e.Key != "" && m.keys[e.Key] {
                return
            }
            ok := e.SKU != ""
            switch e.Kind {
            case Receive:
                ok = ok && e.Qty > 0
            case Ship:
                ok = ok && e.Qty > 0 && m.stock[e.SKU] >= e.Qty
            case Adjust:
                ok = ok && e.Qty >= 0
            default:
                ok = false
            }
            if !ok {
                m.rejected++
                return
            }
            switch e.Kind {
            case Receive:
                m.stock[e.SKU] += e.Qty
            case Ship:
                m.stock[e.SKU] -= e.Qty
            case Adjust:
                m.stock[e.SKU] = e.Qty
            }
            if e.Key != "" {
                m.keys[e.Key] = true
            }
        }

        func modelOf(evs []Event) *model {
            sorted := append([]Event(nil), evs...)
            sort.SliceStable(sorted, func(i, j int) bool { return sorted[i].Seq < sorted[j].Seq })
            m := newModel()
            for _, e := range sorted {
                if e.Seq <= m.applied {
                    continue
                }
                m.apply(e)
            }
            return m
        }

        func nonZero(m map[string]int) map[string]int {
            out := map[string]int{}
            for k, v := range m {
                if v != 0 {
                    out[k] = v
                }
            }
            return out
        }

        func sameStock(a, b map[string]int) bool {
            a, b = nonZero(a), nonZero(b)
            if len(a) != len(b) {
                return false
            }
            for k, v := range a {
                if b[k] != v {
                    return false
                }
            }
            return true
        }

        func sameKeys(a, b map[string]bool) bool {
            if len(a) != len(b) {
                return false
            }
            for k := range a {
                if !b[k] {
                    return false
                }
            }
            return true
        }

        func checkState(t *testing.T, what string, got *State, want *model) {
            t.Helper()
            if !sameStock(got.Stock, want.stock) {
                t.Errorf("%s: stock %v, want %v", what, nonZero(got.Stock), nonZero(want.stock))
            }
            if !sameKeys(got.Keys, want.keys) {
                t.Errorf("%s: keys %v, want %v", what, got.Keys, want.keys)
            }
            if got.Applied != want.applied {
                t.Errorf("%s: applied %d, want %d", what, got.Applied, want.applied)
            }
            if len(got.Rejected) != want.rejected {
                t.Errorf("%s: %d rejections, want %d", what, len(got.Rejected), want.rejected)
            }
        }

        // ---- deterministic event generator -------------------------------------------------------------------

        type lcg uint64

        func (l *lcg) next(n int) int {
            *l = *l*6364136223846793005 + 1442695040888963407
            return int((uint64(*l) >> 33) % uint64(n))
        }

        func events(seed uint64, n int) []Event {
            r := lcg(seed)
            skus := []string{"A", "B", "C"}
            var out []Event
            for i := 1; i <= n; i++ {
                e := Event{Seq: int64(i), SKU: skus[r.next(3)], Qty: r.next(6)}
                switch r.next(8) {
                case 0, 1, 2:
                    e.Kind = Receive
                case 3, 4, 5:
                    e.Kind = Ship
                case 6:
                    e.Kind = Adjust
                default:
                    e.Kind = Kind("bogus")
                }
                if r.next(3) > 0 {
                    e.Key = fmt.Sprintf("k%d", r.next(7))
                }
                out = append(out, e)
            }
            return out
        }

        // ---- State ---------------------------------------------------------------------------------------------

        func TestApplyAgainstModel(t *testing.T) {
            for seed := uint64(1); seed <= 12; seed++ {
                evs := events(seed, 40)
                s := NewState()
                m := newModel()
                for _, e := range evs {
                    s.Apply(e)
                    m.apply(e)
                }
                checkState(t, fmt.Sprintf("seed %d", seed), s, m)
            }
        }

        func TestAdjustSetsTheCount(t *testing.T) {
            s := NewState()
            s.Apply(Event{Seq: 1, SKU: "x", Kind: Receive, Qty: 7})
            s.Apply(Event{Seq: 2, SKU: "x", Kind: Adjust, Qty: 5})
            if s.Stock["x"] != 5 {
                t.Fatalf("after adjust to 5: %d", s.Stock["x"])
            }
            s.Apply(Event{Seq: 3, SKU: "x", Kind: Adjust, Qty: 0})
            s.Apply(Event{Seq: 4, SKU: "y", Kind: Adjust, Qty: 9})
            if s.Stock["x"] != 0 || s.Stock["y"] != 9 {
                t.Fatalf("stock %v", s.Stock)
            }
            s.Apply(Event{Seq: 5, SKU: "y", Kind: Adjust, Qty: -1})
            if s.Stock["y"] != 9 || len(s.Rejected) != 1 || !errors.Is(s.Rejected[0].Reason, ErrBadEvent) {
                t.Fatalf("negative count: %v %+v", s.Stock, s.Rejected)
            }
        }

        func TestRejections(t *testing.T) {
            s := NewState()
            s.Apply(Event{Seq: 1, SKU: "x", Kind: Receive, Qty: 0})
            s.Apply(Event{Seq: 2, SKU: "", Kind: Receive, Qty: 1})
            s.Apply(Event{Seq: 3, SKU: "x", Kind: Kind("move"), Qty: 1})
            s.Apply(Event{Seq: 4, SKU: "x", Kind: Ship, Qty: 1})
            wantErr := []error{ErrBadEvent, ErrBadEvent, ErrBadEvent, ErrInsufficient}
            if len(s.Rejected) != 4 {
                t.Fatalf("rejected = %+v", s.Rejected)
            }
            for i, r := range s.Rejected {
                if !errors.Is(r.Reason, wantErr[i]) || r.Seq != int64(i+1) {
                    t.Errorf("rejection %d = %+v", i, r)
                }
            }
            if len(s.Stock) != 0 && s.Stock["x"] != 0 {
                t.Errorf("stock changed: %v", s.Stock)
            }
        }

        func TestRefusedEventKeepsItsKey(t *testing.T) {
            s := NewState()
            s.Apply(Event{Seq: 1, Key: "order-9", SKU: "x", Kind: Ship, Qty: 2})
            if len(s.Rejected) != 1 {
                t.Fatalf("first attempt: %+v", s.Rejected)
            }
            s.Apply(Event{Seq: 2, SKU: "x", Kind: Receive, Qty: 5})
            s.Apply(Event{Seq: 3, Key: "order-9", SKU: "x", Kind: Ship, Qty: 2})
            if s.Stock["x"] != 3 || len(s.Rejected) != 1 {
                t.Fatalf("retry after restock: stock %d, rejected %d", s.Stock["x"], len(s.Rejected))
            }
            s.Apply(Event{Seq: 4, Key: "order-9", SKU: "x", Kind: Ship, Qty: 2})
            if s.Stock["x"] != 3 || len(s.Rejected) != 1 {
                t.Fatalf("second retry must be ignored: stock %d, rejected %d", s.Stock["x"], len(s.Rejected))
            }
        }

        func TestIgnoredDuplicateStillCountsAsConsumed(t *testing.T) {
            s := NewState()
            s.Apply(Event{Seq: 1, Key: "a", SKU: "x", Kind: Receive, Qty: 1})
            s.Apply(Event{Seq: 2, Key: "a", SKU: "x", Kind: Receive, Qty: 1})
            if s.Applied != 2 {
                t.Fatalf("applied = %d, want 2", s.Applied)
            }
            s.Apply(Event{Seq: 3, SKU: "x", Kind: Ship, Qty: 9})
            if s.Applied != 3 {
                t.Fatalf("applied after a rejection = %d, want 3", s.Applied)
            }
        }

        // ---- log ------------------------------------------------------------------------------------------------

        func TestParse(t *testing.T) {
            text := "# shard 1\\n\\n 1 | k1 | bolt | receive | 10 \\n2||nut|adjust|4\\n\\n3|k3|bolt|ship|2"
            evs, err := Parse(text)
            if err != nil {
                t.Fatal(err)
            }
            want := []Event{
                {Seq: 1, Key: "k1", SKU: "bolt", Kind: Receive, Qty: 10},
                {Seq: 2, Key: "", SKU: "nut", Kind: Adjust, Qty: 4},
                {Seq: 3, Key: "k3", SKU: "bolt", Kind: Ship, Qty: 2},
            }
            if len(evs) != len(want) {
                t.Fatalf("got %+v", evs)
            }
            for i := range want {
                if evs[i] != want[i] {
                    t.Errorf("event %d = %+v, want %+v", i, evs[i], want[i])
                }
            }
            evs, err = Parse("")
            if err != nil || len(evs) != 0 {
                t.Errorf("empty text: %v %v", evs, err)
            }
            evs, err = Parse("1|k|x|teleport|3")
            if err != nil || len(evs) != 1 || evs[0].Kind != "teleport" {
                t.Errorf("unknown kind must parse: %v %v", evs, err)
            }
        }

        func TestParseErrorsNameThePhysicalLine(t *testing.T) {
            cases := []struct {
                text, prefix string
            }{
                {"1|a|x|receive|1\\nnonsense\\n", "line 2:"},
                {"# header\\n\\n# more\\n1|a|x|receive|1\\n2|b|x|receive|many\\n", "line 5:"},
                {"\\n\\n\\nx|a|x|receive|1", "line 4:"},
                {"1|a|x|receive|1\\n\\n\\n0|a|x|receive|1", "line 4:"},
                {"1|a|x|receive", "line 1:"},
            }
            for _, c := range cases {
                _, err := Parse(c.text)
                if err == nil || !strings.HasPrefix(err.Error(), c.prefix) {
                    t.Errorf("Parse(%q) error = %v, want prefix %q", c.text, err, c.prefix)
                }
            }
        }

        func TestMergeOrdersNumerically(t *testing.T) {
            var a, b []Event
            for i := 1; i <= 25; i++ {
                e := Event{Seq: int64(i), SKU: "x", Kind: Receive, Qty: 1}
                if i%3 == 0 {
                    b = append(b, e)
                } else {
                    a = append(a, e)
                }
            }
            got := Merge(b, a)
            if len(got) != 25 {
                t.Fatalf("len = %d", len(got))
            }
            for i, e := range got {
                if e.Seq != int64(i+1) {
                    t.Fatalf("position %d has seq %d", i, e.Seq)
                }
            }
        }

        func TestMergeKeepsArgumentOrderOnTies(t *testing.T) {
            a := []Event{{Seq: 5, SKU: "first", Kind: Receive, Qty: 1}}
            b := []Event{{Seq: 5, SKU: "second", Kind: Receive, Qty: 1}}
            got := Merge(a, b)
            if got[0].SKU != "first" || got[1].SKU != "second" {
                t.Fatalf("got %+v", got)
            }
            got = Merge(b, a)
            if got[0].SKU != "second" {
                t.Fatalf("got %+v", got)
            }
        }

        // ---- replay and snapshots -----------------------------------------------------------------------------

        func TestReplayAgainstModelInAnyOrder(t *testing.T) {
            for seed := uint64(1); seed <= 8; seed++ {
                evs := events(seed, 30)
                shuffled := append([]Event(nil), evs...)
                r := lcg(seed * 77)
                for i := len(shuffled) - 1; i > 0; i-- {
                    j := r.next(i + 1)
                    shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
                }
                checkState(t, fmt.Sprintf("seed %d", seed), Replay(shuffled, nil), modelOf(evs))
            }
        }

        func TestReplayDoesNotChangeItsInput(t *testing.T) {
            evs := []Event{{Seq: 2, SKU: "x", Kind: Receive, Qty: 1}, {Seq: 1, SKU: "x", Kind: Receive, Qty: 1}}
            Replay(evs, nil)
            if evs[0].Seq != 2 || evs[1].Seq != 1 {
                t.Fatalf("input was reordered: %+v", evs)
            }
        }

        func TestOverlappingShardsApplyOnce(t *testing.T) {
            a := []Event{{Seq: 1, SKU: "x", Kind: Receive, Qty: 5}, {Seq: 2, SKU: "x", Kind: Receive, Qty: 5}}
            b := []Event{{Seq: 2, SKU: "x", Kind: Receive, Qty: 5}, {Seq: 3, SKU: "x", Kind: Ship, Qty: 2}}
            s := Replay(Merge(a, b), nil)
            if s.Stock["x"] != 8 || s.Applied != 3 {
                t.Fatalf("stock %d applied %d, want 8 and 3", s.Stock["x"], s.Applied)
            }
        }

        func TestSnapshotSplitInvariant(t *testing.T) {
            for seed := uint64(1); seed <= 6; seed++ {
                evs := events(seed, 28)
                full := modelOf(evs)
                for k := 0; k <= len(evs); k++ {
                    snap := Take(Replay(evs[:k], nil))
                    what := fmt.Sprintf("seed %d split %d", seed, k)
                    checkRest := func(s *State, label string) {
                        t.Helper()
                        // rejections before the snapshot are not persisted: compare the other parts only
                        if !sameStock(s.Stock, full.stock) || !sameKeys(s.Keys, full.keys) || s.Applied != full.applied {
                            t.Errorf("%s %s: stock %v keys %v applied %d; want %v %v %d", what, label,
                                nonZero(s.Stock), s.Keys, s.Applied, nonZero(full.stock), full.keys, full.applied)
                        }
                    }
                    checkRest(Replay(evs[k:], snap), "tail")
                    checkRest(Replay(evs, snap), "whole log")
                }
            }
        }

        func TestSnapshotIsIndependent(t *testing.T) {
            s := NewState()
            s.Apply(Event{Seq: 1, Key: "a", SKU: "x", Kind: Receive, Qty: 5})
            snap := Take(s)
            s.Apply(Event{Seq: 2, Key: "b", SKU: "x", Kind: Receive, Qty: 5})
            if snap.Stock["x"] != 5 || snap.Applied != 1 || snap.Keys["b"] {
                t.Fatalf("snapshot changed with the state: %+v", snap)
            }
        }

        func TestRestoreIsIndependent(t *testing.T) {
            s := NewState()
            s.Apply(Event{Seq: 1, Key: "a", SKU: "x", Kind: Receive, Qty: 5})
            snap := Take(s)
            tail := []Event{{Seq: 2, Key: "b", SKU: "x", Kind: Receive, Qty: 4}, {Seq: 3, SKU: "y", Kind: Receive, Qty: 1}}
            first := Replay(tail, snap)
            second := Replay(tail, snap)
            if first.Stock["x"] != 9 || second.Stock["x"] != 9 || second.Stock["y"] != 1 {
                t.Fatalf("first %v, second %v", first.Stock, second.Stock)
            }
            if snap.Stock["x"] != 5 || snap.Applied != 1 || snap.Keys["b"] || len(snap.Stock) != 1 {
                t.Fatalf("snapshot was modified by a replay: %+v", snap)
            }
        }

        func TestSnapshotRemembersKeys(t *testing.T) {
            s := NewState()
            s.Apply(Event{Seq: 1, Key: "pay-1", SKU: "x", Kind: Receive, Qty: 5})
            snap := Take(s)
            r := Replay([]Event{{Seq: 2, Key: "pay-1", SKU: "x", Kind: Receive, Qty: 5}}, snap)
            if r.Stock["x"] != 5 || r.Applied != 2 {
                t.Fatalf("a retried key after a restore was applied again: %v", r.Stock)
            }
        }

        // ---- feed ----------------------------------------------------------------------------------------------

        func permutations(n int) [][]int {
            var out [][]int
            var rec func(cur []int, used []bool)
            rec = func(cur []int, used []bool) {
                if len(cur) == n {
                    out = append(out, append([]int(nil), cur...))
                    return
                }
                for i := 0; i < n; i++ {
                    if !used[i] {
                        used[i] = true
                        rec(append(cur, i), used)
                        used[i] = false
                    }
                }
            }
            rec(nil, make([]bool, n))
            return out
        }

        func TestFeedAnyArrivalOrderEqualsReplay(t *testing.T) {
            for seed := uint64(1); seed <= 4; seed++ {
                evs := events(seed, 6)
                want := modelOf(evs)
                for _, perm := range permutations(6) {
                    f := NewFeed(nil)
                    var applied []int64
                    for _, i := range perm {
                        applied = append(applied, f.Push(evs[i])...)
                    }
                    for i, s := range applied {
                        if s != int64(i+1) {
                            t.Fatalf("seed %d perm %v: applied order %v", seed, perm, applied)
                        }
                    }
                    if f.Pending() != 0 || len(applied) != 6 {
                        t.Fatalf("seed %d perm %v: pending %d applied %v", seed, perm, f.Pending(), applied)
                    }
                    got := f.State()
                    if !sameStock(got.Stock, want.stock) || !sameKeys(got.Keys, want.keys) || got.Applied != want.applied || len(got.Rejected) != want.rejected {
                        t.Fatalf("seed %d perm %v: stock %v keys %v, want %v %v", seed, perm, nonZero(got.Stock), got.Keys, nonZero(want.stock), want.keys)
                    }
                }
            }
        }

        func TestFeedWaitsForGaps(t *testing.T) {
            f := NewFeed(nil)
            if got := f.Push(Event{Seq: 3, SKU: "x", Kind: Receive, Qty: 1}); len(got) != 0 {
                t.Fatalf("applied %v with a gap", got)
            }
            f.Push(Event{Seq: 2, SKU: "x", Kind: Receive, Qty: 1})
            if f.Pending() != 2 || f.State().Stock["x"] != 0 {
                t.Fatalf("pending %d stock %v", f.Pending(), f.State().Stock)
            }
            got := f.Push(Event{Seq: 1, SKU: "x", Kind: Receive, Qty: 1})
            if len(got) != 3 || got[0] != 1 || got[2] != 3 || f.State().Stock["x"] != 3 || f.Pending() != 0 {
                t.Fatalf("got %v stock %v pending %d", got, f.State().Stock, f.Pending())
            }
        }

        func TestFeedDropsOldAndPendingDuplicates(t *testing.T) {
            f := NewFeed(nil)
            f.Push(Event{Seq: 1, SKU: "x", Kind: Receive, Qty: 1})
            if got := f.Push(Event{Seq: 1, SKU: "x", Kind: Receive, Qty: 100}); got != nil || f.State().Stock["x"] != 1 {
                t.Fatalf("an old event was applied: %v %v", got, f.State().Stock)
            }
            f.Push(Event{Seq: 3, SKU: "x", Kind: Receive, Qty: 2})
            f.Push(Event{Seq: 3, SKU: "x", Kind: Receive, Qty: 50})
            f.Push(Event{Seq: 2, SKU: "x", Kind: Receive, Qty: 4})
            if f.State().Stock["x"] != 7 {
                t.Fatalf("first copy must win: stock %v", f.State().Stock)
            }
        }

        func TestFeedDoesNotStallOnADuplicateKey(t *testing.T) {
            f := NewFeed(nil)
            f.Push(Event{Seq: 1, Key: "a", SKU: "x", Kind: Receive, Qty: 1})
            f.Push(Event{Seq: 2, Key: "a", SKU: "x", Kind: Receive, Qty: 1}) // a retry of 1: ignored, but consumed
            got := f.Push(Event{Seq: 3, SKU: "x", Kind: Receive, Qty: 1})
            if len(got) != 1 || got[0] != 3 || f.Pending() != 0 || f.State().Stock["x"] != 2 {
                t.Fatalf("got %v pending %d stock %v", got, f.Pending(), f.State().Stock)
            }
        }

        func TestRetryOfARefusedEventIsProcessedLiveToo(t *testing.T) {
            f := NewFeed(nil)
            f.Push(Event{Seq: 1, Key: "o-1", SKU: "x", Kind: Ship, Qty: 2})
            f.Push(Event{Seq: 2, SKU: "x", Kind: Receive, Qty: 5})
            f.Push(Event{Seq: 3, Key: "o-1", SKU: "x", Kind: Ship, Qty: 2})
            if f.State().Stock["x"] != 3 || len(f.State().Rejected) != 1 {
                t.Fatalf("stock %v rejected %d", f.State().Stock, len(f.State().Rejected))
            }
            // the same retry arriving while the original is still waiting behind a gap
            g := NewFeed(nil)
            g.Push(Event{Seq: 2, SKU: "x", Kind: Receive, Qty: 5})
            g.Push(Event{Seq: 4, Key: "o-1", SKU: "x", Kind: Ship, Qty: 2})
            g.Push(Event{Seq: 3, Key: "o-1", SKU: "x", Kind: Ship, Qty: 2})
            g.Push(Event{Seq: 1, SKU: "x", Kind: Receive, Qty: 1})
            if g.State().Stock["x"] != 4 || g.Pending() != 0 {
                t.Fatalf("stock %v pending %d", g.State().Stock, g.Pending())
            }
        }

        func TestFeedFromASnapshot(t *testing.T) {
            evs := events(5, 20)
            snap := Take(Replay(evs[:12], nil))
            f := NewFeed(snap)
            for i := len(evs) - 1; i >= 0; i-- {
                f.Push(evs[i])
            }
            want := modelOf(evs)
            got := f.State()
            if !sameStock(got.Stock, want.stock) || !sameKeys(got.Keys, want.keys) || got.Applied != 20 || f.Pending() != 0 {
                t.Fatalf("stock %v keys %v applied %d pending %d", nonZero(got.Stock), got.Keys, got.Applied, f.Pending())
            }
        }
    '''),
}


def _g(tree: dict[str, str]) -> dict[str, str]:
    return {p: tabify(t) if p.endswith(".go") else t for p, t in tree.items()}


def _prompts() -> dict:
    p = {}
    p["parse-lines"] = (
        "Our import tool reports the wrong line for a bad record: for a shard file that starts with a comment block, the "
        "message points a few lines too early and people open the editor at the wrong place. The README says what `N` in `line N:` means."
    )
    p["adjust"] = (
        "The weekly stock-take is making the numbers worse. A shelf with 7 bolts is counted as 5 and the ledger then shows 12. "
        "The warehouse staff say the count they enter is what is on the shelf."
    )

    def merge_text(c):
        out = c.visible_out(12)
        return (
            "The merged archive that the nightly job writes from the two shard files is out of order once sequence numbers have "
            "two digits: event 10 is listed between 1 and 2, which makes the diff against the previous archive unreadable. "
            "A reduced reproduction in our CI looks like this:\n\n```\n" + out + "\n```\n"
        )

    p["merge"] = merge_text
    p["replay-skip"] = (
        "When we restart the service from last night's snapshot and give it the whole log again (we do not bother cutting it), "
        "the receipt that was the very last event before the snapshot is counted twice. The same thing happens for an event "
        "that is present in both shards when we merge them. Events that appear twice must be applied once."
    )
    p["keys-dropped"] = (
        "Duplicate postings come back after a restart. A payment-driven `receive` with key `pay-1` was applied before the "
        "snapshot; when the payment processor retried it after the restart the stock went up a second time. Without a restart the retry is ignored as it should be."
    )
    p["restore-aliases"] = (
        "Rebuilding twice from the same snapshot gives different numbers: the second rebuild starts from the stock the first one "
        "ended with (the nightly job runs the rebuild again when its checksum step fails). I would have guessed that `Replay` "
        "keeps state between calls, but it is a plain function."
    )
    p["key-on-reject"] = (
        "A customer order that was refused for lack of stock never ships, even after we receive more: the client retries "
        "with the same key (`order-9`) and the ledger answers by ignoring it. The README explains what a refused event does with its key."
    )
    p["dup-no-advance"] = (
        "The live stock view froze at event 310 on Tuesday: `Pending()` grew all afternoon while the nightly rebuild from the log "
        "showed all the events as fine. The first thing that happened at 310 was an ordinary retry from the payment processor (same key as an "
        "event a minute before)."
    )
    p["arrival-order"] = (
        "The live view disagrees with the nightly rebuild whenever two warehouses report at about the same time: receipts are "
        "missing from the live numbers (ships get refused as insufficient), and the pending count is always 0. The rebuild from the log is right."
    )
    p["refused-retry"] = (
        "Ops ticket 5521: after a restock, the refused order retry (same key as the first attempt, a new sequence number) "
        "is still not shipped. Neither the live view nor the nightly rebuild ships it, and both agree with each other, so the "
        "ledger believes it is correct. Retries of events that were *applied* must still be ignored; only refused ones may be retried."
    )
    return p


def _base() -> Base:
    P = _prompts()
    good = _g({
        "README.md": README, "go.mod": langs.go_mod("ledger"),
        "event.go": EVENT, "state.go": STATE, "log.go": LOG, "snapshot.go": SNAPSHOT, "replay.go": REPLAY, "feed.go": FEED,
    })
    visible = _g(VISIBLE)
    hidden = _g(HIDDEN)

    parse_old = [(
        "    var out []Event\n    for i, raw := range strings.Split(text, \"\\n\") {\n        line := strings.TrimSpace(raw)\n"
        "        if line == \"\" || strings.HasPrefix(line, \"#\") {\n            continue\n        }\n        e, err := parseLine(line)\n"
        "        if err != nil {\n            return nil, fmt.Errorf(\"line %d: %w\", i+1, err)\n        }\n",
        "    var out []Event\n    n := 0\n    for _, raw := range strings.Split(text, \"\\n\") {\n        line := strings.TrimSpace(raw)\n"
        "        if line == \"\" || strings.HasPrefix(line, \"#\") {\n            continue\n        }\n        n++\n        e, err := parseLine(line)\n"
        "        if err != nil {\n            return nil, fmt.Errorf(\"line %d: %w\", n, err)\n        }\n",
    )]
    merge_bug = [("all[i].Seq < all[j].Seq })\n    return all", "fmt.Sprint(all[i].Seq) < fmt.Sprint(all[j].Seq) })\n    return all")]
    merge_bug[0] = ("sort.SliceStable(all, func(i, j int) bool { return all[i].Seq < all[j].Seq })",
                    "sort.SliceStable(all, func(i, j int) bool { return fmt.Sprint(all[i].Seq) < fmt.Sprint(all[j].Seq) })")
    reported_merge = {
        "reported_test.go": tabify(dd('''
            package ledger

            import "testing"

            func TestMergeListsTenAfterNine(t *testing.T) {
                a := []Event{{Seq: 1, SKU: "x", Kind: Receive, Qty: 5}, {Seq: 9, SKU: "x", Kind: Receive, Qty: 1}}
                b := []Event{{Seq: 10, SKU: "x", Kind: Ship, Qty: 6}, {Seq: 2, SKU: "x", Kind: Receive, Qty: 1}}
                var seqs []int64
                for _, e := range Merge(a, b) {
                    seqs = append(seqs, e.Seq)
                }
                want := []int64{1, 2, 9, 10}
                for i := range want {
                    if len(seqs) != len(want) || seqs[i] != want[i] {
                        t.Fatalf("merged order %v, want %v", seqs, want)
                    }
                }
            }
        ''')),
    }
    bugs = [
        Bug("parse-line-numbers-skip-comments", 2, {"log.go": tab_pairs(parse_old)}, P["parse-lines"]),
        Bug("adjust-adds-instead-of-sets", 2, {"state.go": tab_pairs([("        s.Stock[e.SKU] = e.Qty\n", "        s.Stock[e.SKU] += e.Qty\n")])}, P["adjust"]),
        Bug("merge-compares-seq-as-text", 3, {"log.go": tab_pairs(merge_bug)}, P["merge"], reported=reported_merge),
        Bug("replay-reapplies-the-snapshot-event", 3, {"replay.go": tab_pairs([("        if e.Seq <= s.Applied {\n", "        if e.Seq < s.Applied {\n")])}, P["replay-skip"]),
        Bug("snapshot-forgets-the-keys", 4, {"snapshot.go": tab_pairs([("Applied: s.Applied, Stock: copyStock(s.Stock), Keys: copyKeys(s.Keys)}", "Applied: s.Applied, Stock: copyStock(s.Stock)}")])}, P["keys-dropped"]),
        Bug("restore-aliases-the-snapshot", 4, {"snapshot.go": tab_pairs([("    s.Stock = copyStock(snap.Stock)\n    s.Keys = copyKeys(snap.Keys)\n", "    s.Stock = snap.Stock\n    s.Keys = snap.Keys\n")])}, P["restore-aliases"]),
        Bug("rejected-event-uses-up-its-key", 3, {"state.go": tab_pairs([(
            "    s.Applied = e.Seq\n    if e.Key != \"\" && s.Keys[e.Key] {\n        return\n    }\n",
            "    s.Applied = e.Seq\n    if e.Key != \"\" {\n        if s.Keys[e.Key] {\n            return\n        }\n        s.Keys[e.Key] = true\n    }\n"),
        ])}, P["key-on-reject"]),
        Bug("ignored-duplicate-does-not-advance-applied", 4, {"state.go": tab_pairs([(
            "    s.Applied = e.Seq\n    if e.Key != \"\" && s.Keys[e.Key] {\n        return\n    }\n",
            "    if e.Key != \"\" && s.Keys[e.Key] {\n        return\n    }\n    s.Applied = e.Seq\n"),
        ])}, P["dup-no-advance"]),
        Bug("feed-applies-in-arrival-order", 4, {"feed.go": tab_pairs([(
            "    f.pending[e.Seq] = e\n    var done []int64\n    for {\n        next, ok := f.pending[f.state.Applied+1]\n        if !ok {\n            break\n        }\n        delete(f.pending, next.Seq)\n        f.state.Apply(next)\n        done = append(done, next.Seq)\n    }\n    return done\n",
            "    f.state.Apply(e)\n    return []int64{e.Seq}\n"),
        ])}, P["arrival-order"]),
        Bug("refused-retry-lost-live-and-rebuilt", 5, {
            "state.go": tab_pairs([(
                "    s.Applied = e.Seq\n    if e.Key != \"\" && s.Keys[e.Key] {\n        return\n    }\n",
                "    s.Applied = e.Seq\n    if e.Key != \"\" {\n        if s.Keys[e.Key] {\n            return\n        }\n        s.Keys[e.Key] = true\n    }\n")]),
            "feed.go": tab_pairs([
                ("    state   *State\n    pending map[int64]Event\n}", "    state   *State\n    pending map[int64]Event\n    seen    map[string]bool\n}"),
                ("return &Feed{state: Restore(snap), pending: map[int64]Event{}}", "return &Feed{state: Restore(snap), pending: map[int64]Event{}, seen: map[string]bool{}}"),
                ("    f.pending[e.Seq] = e\n    var done", "    if e.Key != \"\" {\n        if f.seen[e.Key] {\n            return nil\n        }\n        f.seen[e.Key] = true\n    }\n    f.pending[e.Seq] = e\n    var done"),
            ]),
        }, P["refused-retry"]),
    ]
    return Base("ledger", "go", good, visible, hidden, bugs)


@family("fix-hand-event-ledger", category="fix", lang="go", kind="fix", n=10,
        summary="a layered go stock ledger (parse, state machine, replay, snapshots, live feed) with defects that surface in another layer")
def gen(rng, n):
    return tasks_from([_base()])
