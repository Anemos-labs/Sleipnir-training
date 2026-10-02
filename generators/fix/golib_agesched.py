"""Batch job scheduler (go): priorities that age, deadline urgency and infeasible-job dropping on a tick clock."""
from fx import Lib, dd, langs

from generators.fix._lang1 import gosrc, register_libs

README = dd('''
    # agesched

    The nightly batch runner's scheduling core. Time is an `int` tick counter that the caller advances; nothing here reads a
    clock, and nothing is concurrent.

    ```go
    type Job struct {
        ID       string
        Base     int // priority 0..9, higher runs first
        Cost     int // ticks of work, >= 1
        Deadline int // tick by which the job must be finished; 0 means none
    }
    ```

    ## `New(slots, ageEvery int) (*Scheduler, error)`
    `slots` is how many jobs may run at once, `ageEvery` how many ticks of waiting earn one priority point. Both must be at
    least 1, otherwise `ErrConfig`.

    ## `(*Scheduler) Submit(now int, j Job) error`
    Adds a waiting job that *arrived* at `now`. Errors, in this order:
    `ErrClock` if `now` is earlier than the latest tick the scheduler has seen (from `Submit` or `Tick`);
    `ErrBadJob` if `ID` is empty, `Base` is outside 0..9 or `Cost < 1`;
    `ErrDuplicate` if a waiting or running job has the same `ID`;
    `ErrInfeasible` if `Deadline != 0` and `now + Cost > Deadline` (it could not finish in time even if it started right now).

    ## Priority
    `(*Scheduler) Priority(id string, now int) (int, bool)` is the *effective priority* of a **waiting** job (`false` if there is
    none with that id):

    `Base + min(5, (now - arrived) / ageEvery)` (integer division), plus an urgency bonus for jobs with a deadline, using
    `slack = Deadline - now - Cost`: `+20` when `slack == 0`, `+3` when `1 <= slack <= 2`, nothing otherwise (a negative
    slack is a job that has already missed; see `Tick`).

    ## `(*Scheduler) Tick(now int) (Report, error)`
    `ErrClock` if `now` is earlier than the latest tick seen. Otherwise, in this order:

    1. **Finish**: every running job with `start + Cost <= now` finishes. `Report.Finished` lists them in the order they had
       started.
    2. **Drop**: every waiting job with a deadline and `now + Cost > Deadline` can no longer make it and is removed;
       `Report.Missed` lists them ordered by arrival tick, then ID.
    3. **Start**: while a slot is free and a job is waiting, the best waiting job starts (its start tick is `now`). `Report.Started`
       lists them in the order picked. "Best" is the highest effective priority at `now`; ties go to the job with the earlier
       deadline (any deadline beats none), then the earlier arrival, then the smaller ID.

    Calling `Tick` again with the same `now` changes nothing and reports empty lists. `Report` is
    `{Started, Finished, Missed []string}`; empty lists may be nil.

    ## Inspection
    `(*Scheduler) Waiting() int` is the number of waiting jobs. `(*Scheduler) Running() []string` the IDs of running jobs in the
    order they started.
''')

SRC = gosrc(dd(r'''
    // Package agesched schedules batch jobs with aging priorities and deadlines.
    package agesched

    import (
        "errors"
        "sort"
    )

    var (
        ErrConfig     = errors.New("agesched: slots and ageEvery must be at least 1")
        ErrClock      = errors.New("agesched: time went backwards")
        ErrBadJob     = errors.New("agesched: invalid job")
        ErrDuplicate  = errors.New("agesched: duplicate job id")
        ErrInfeasible = errors.New("agesched: deadline cannot be met")
    )

    const maxBoost = 5

    // Job is a unit of work.
    type Job struct {
        ID       string
        Base     int
        Cost     int
        Deadline int
    }

    // Report lists what one Tick did.
    type Report struct {
        Started, Finished, Missed []string
    }

    type waiting struct {
        Job
        arrived int
    }

    type running struct {
        Job
        start int
    }

    // Scheduler holds the queue state.
    type Scheduler struct {
        slots, ageEvery int
        clock           int
        wait            []waiting
        run             []running
    }

    // New creates a scheduler.
    func New(slots, ageEvery int) (*Scheduler, error) {
        if slots < 1 || ageEvery < 1 {
            return nil, ErrConfig
        }
        return &Scheduler{slots: slots, ageEvery: ageEvery}, nil
    }

    func (s *Scheduler) priority(w waiting, now int) int {
        p := w.Base + min(maxBoost, (now-w.arrived)/s.ageEvery)
        if w.Deadline != 0 {
            switch slack := w.Deadline - now - w.Cost; {
            case slack == 0:
                p += 20
            case slack >= 1 && slack <= 2:
                p += 3
            }
        }
        return p
    }

    func (s *Scheduler) has(id string) bool {
        for _, w := range s.wait {
            if w.ID == id {
                return true
            }
        }
        for _, r := range s.run {
            if r.ID == id {
                return true
            }
        }
        return false
    }

    // Submit queues a job that arrives at tick now.
    func (s *Scheduler) Submit(now int, j Job) error {
        if now < s.clock {
            return ErrClock
        }
        if j.ID == "" || j.Base < 0 || j.Base > 9 || j.Cost < 1 {
            return ErrBadJob
        }
        if s.has(j.ID) {
            return ErrDuplicate
        }
        if j.Deadline != 0 && now+j.Cost > j.Deadline {
            return ErrInfeasible
        }
        s.clock = now
        s.wait = append(s.wait, waiting{j, now})
        return nil
    }

    // Priority is the effective priority of a waiting job.
    func (s *Scheduler) Priority(id string, now int) (int, bool) {
        for _, w := range s.wait {
            if w.ID == id {
                return s.priority(w, now), true
            }
        }
        return 0, false
    }

    // Waiting is the number of queued jobs.
    func (s *Scheduler) Waiting() int { return len(s.wait) }

    // Running lists the IDs of running jobs in start order.
    func (s *Scheduler) Running() []string {
        var ids []string
        for _, r := range s.run {
            ids = append(ids, r.ID)
        }
        return ids
    }

    // better reports whether a should start before b at time now.
    func (s *Scheduler) better(a, b waiting, now int) bool {
        pa, pb := s.priority(a, now), s.priority(b, now)
        if pa != pb {
            return pa > pb
        }
        if a.Deadline != b.Deadline {
            if a.Deadline == 0 {
                return false
            }
            if b.Deadline == 0 {
                return true
            }
            return a.Deadline < b.Deadline
        }
        if a.arrived != b.arrived {
            return a.arrived < b.arrived
        }
        return a.ID < b.ID
    }

    // Tick advances the clock to now and runs the three phases.
    func (s *Scheduler) Tick(now int) (Report, error) {
        var rep Report
        if now < s.clock {
            return rep, ErrClock
        }
        s.clock = now
        keep := s.run[:0]
        for _, r := range s.run {
            if r.start+r.Cost <= now {
                rep.Finished = append(rep.Finished, r.ID)
            } else {
                keep = append(keep, r)
            }
        }
        s.run = keep
        var alive, missed []waiting
        for _, w := range s.wait {
            if w.Deadline != 0 && now+w.Cost > w.Deadline {
                missed = append(missed, w)
            } else {
                alive = append(alive, w)
            }
        }
        s.wait = alive
        sort.SliceStable(missed, func(i, j int) bool {
            if missed[i].arrived != missed[j].arrived {
                return missed[i].arrived < missed[j].arrived
            }
            return missed[i].ID < missed[j].ID
        })
        for _, w := range missed {
            rep.Missed = append(rep.Missed, w.ID)
        }
        for len(s.run) < s.slots && len(s.wait) > 0 {
            best := 0
            for i := 1; i < len(s.wait); i++ {
                if s.better(s.wait[i], s.wait[best], now) {
                    best = i
                }
            }
            w := s.wait[best]
            s.wait = append(s.wait[:best], s.wait[best+1:]...)
            s.run = append(s.run, running{w.Job, now})
            rep.Started = append(rep.Started, w.ID)
        }
        return rep, nil
    }
'''))

VISIBLE = gosrc(dd(r'''
    package agesched

    import "testing"

    func TestStartsHighestPriorityFirst(t *testing.T) {
        s, err := New(1, 10)
        if err != nil {
            t.Fatal(err)
        }
        s.Submit(0, Job{ID: "low", Base: 2, Cost: 3})
        s.Submit(0, Job{ID: "high", Base: 8, Cost: 3})
        rep, _ := s.Tick(0)
        if len(rep.Started) != 1 || rep.Started[0] != "high" {
            t.Fatalf("started %v", rep.Started)
        }
    }

    func TestRejectsBadConfig(t *testing.T) {
        if _, err := New(0, 1); err == nil {
            t.Fatal("slots 0 should fail")
        }
    }
'''))

HIDDEN = gosrc(dd(r'''
    package agesched

    import (
        "errors"
        "reflect"
        "testing"
    )

    func mustNew(t *testing.T, slots, age int) *Scheduler {
        t.Helper()
        s, err := New(slots, age)
        if err != nil {
            t.Fatal(err)
        }
        return s
    }

    func submit(t *testing.T, s *Scheduler, now int, jobs ...Job) {
        t.Helper()
        for _, j := range jobs {
            if err := s.Submit(now, j); err != nil {
                t.Fatalf("Submit(%d, %+v): %v", now, j, err)
            }
        }
    }

    func tick(t *testing.T, s *Scheduler, now int) Report {
        t.Helper()
        r, err := s.Tick(now)
        if err != nil {
            t.Fatalf("Tick(%d): %v", now, err)
        }
        return r
    }

    func same(a, b []string) bool {
        if len(a) == 0 && len(b) == 0 {
            return true
        }
        return reflect.DeepEqual(a, b)
    }

    func expect(t *testing.T, label string, got Report, started, finished, missed []string) {
        t.Helper()
        if !same(got.Started, started) || !same(got.Finished, finished) || !same(got.Missed, missed) {
            t.Errorf("%s: got started=%v finished=%v missed=%v; want started=%v finished=%v missed=%v",
                label, got.Started, got.Finished, got.Missed, started, finished, missed)
        }
    }

    func TestConfigErrors(t *testing.T) {
        for _, c := range [][2]int{{0, 1}, {1, 0}, {-1, 5}, {2, -1}, {0, 0}} {
            if _, err := New(c[0], c[1]); !errors.Is(err, ErrConfig) {
                t.Errorf("New(%d, %d): %v", c[0], c[1], err)
            }
        }
        if _, err := New(1, 1); err != nil {
            t.Errorf("New(1, 1): %v", err)
        }
    }

    func TestSingleSlotOrder(t *testing.T) {
        s := mustNew(t, 1, 10)
        submit(t, s, 0, Job{ID: "A", Base: 5, Cost: 3}, Job{ID: "C", Base: 7, Cost: 1}, Job{ID: "B", Base: 7, Cost: 2})
        expect(t, "t0", tick(t, s, 0), []string{"B"}, nil, nil)
        expect(t, "t1", tick(t, s, 1), nil, nil, nil)
        expect(t, "t2", tick(t, s, 2), []string{"C"}, []string{"B"}, nil)
        expect(t, "t3", tick(t, s, 3), []string{"A"}, []string{"C"}, nil)
        expect(t, "t5", tick(t, s, 5), nil, nil, nil)
        expect(t, "t6", tick(t, s, 6), nil, []string{"A"}, nil)
        if s.Waiting() != 0 || len(s.Running()) != 0 {
            t.Errorf("not drained: %d waiting, %v running", s.Waiting(), s.Running())
        }
    }

    func TestTwoSlotsFillAndFreeUp(t *testing.T) {
        s := mustNew(t, 2, 10)
        submit(t, s, 0, Job{ID: "a", Base: 3, Cost: 4}, Job{ID: "b", Base: 4, Cost: 2}, Job{ID: "c", Base: 5, Cost: 2}, Job{ID: "d", Base: 1, Cost: 1})
        expect(t, "t0", tick(t, s, 0), []string{"c", "b"}, nil, nil)
        if got := s.Running(); !reflect.DeepEqual(got, []string{"c", "b"}) {
            t.Errorf("running %v", got)
        }
        expect(t, "t2", tick(t, s, 2), []string{"a", "d"}, []string{"c", "b"}, nil)
        expect(t, "t3", tick(t, s, 3), nil, []string{"d"}, nil)
        expect(t, "t6", tick(t, s, 6), nil, []string{"a"}, nil)
    }

    func TestTickIsIdempotent(t *testing.T) {
        s := mustNew(t, 1, 5)
        submit(t, s, 0, Job{ID: "a", Base: 1, Cost: 2}, Job{ID: "b", Base: 1, Cost: 2})
        expect(t, "first", tick(t, s, 0), []string{"a"}, nil, nil)
        expect(t, "again", tick(t, s, 0), nil, nil, nil)
        expect(t, "t2", tick(t, s, 2), []string{"b"}, []string{"a"}, nil)
        expect(t, "t2 again", tick(t, s, 2), nil, nil, nil)
    }

    func TestTieBreaks(t *testing.T) {
        s := mustNew(t, 1, 100)
        submit(t, s, 0, Job{ID: "zz", Base: 4, Cost: 1})
        submit(t, s, 1, Job{ID: "aa", Base: 4, Cost: 1})
        // same priority, no deadlines: the earlier arrival wins even though its ID sorts later
        expect(t, "arrival", tick(t, s, 1), []string{"zz"}, nil, nil)
        s = mustNew(t, 1, 100)
        submit(t, s, 0, Job{ID: "m", Base: 4, Cost: 1}, Job{ID: "b", Base: 4, Cost: 1})
        expect(t, "id", tick(t, s, 0), []string{"b"}, nil, nil)
        s = mustNew(t, 1, 100)
        submit(t, s, 0, Job{ID: "a", Base: 4, Cost: 1}, Job{ID: "b", Base: 4, Cost: 1, Deadline: 50}, Job{ID: "c", Base: 4, Cost: 1, Deadline: 40})
        expect(t, "deadline", tick(t, s, 0), []string{"c"}, nil, nil)
        expect(t, "next", tick(t, s, 1), []string{"b"}, []string{"c"}, nil)
        expect(t, "last", tick(t, s, 2), []string{"a"}, []string{"b"}, nil)
        // a job with a deadline beats an equal one without, whatever the submit order
        s = mustNew(t, 1, 100)
        submit(t, s, 0, Job{ID: "d", Base: 4, Cost: 1, Deadline: 50}, Job{ID: "n", Base: 4, Cost: 1})
        expect(t, "deadline job first", tick(t, s, 0), []string{"d"}, nil, nil)
        // deadlines 1 and 2 both have slack 0 at tick 0: equal priority, the earlier deadline starts
        s = mustNew(t, 1, 100)
        submit(t, s, 0, Job{ID: "late", Base: 4, Cost: 2, Deadline: 2}, Job{ID: "early", Base: 4, Cost: 1, Deadline: 1})
        expect(t, "tight", tick(t, s, 0), []string{"early"}, nil, nil)
        s = mustNew(t, 1, 100)
        submit(t, s, 0, Job{ID: "early", Base: 4, Cost: 1, Deadline: 1}, Job{ID: "late", Base: 4, Cost: 2, Deadline: 2})
        expect(t, "tight, other order", tick(t, s, 0), []string{"early"}, nil, nil)
    }

    func TestAgingLetsOldJobsOvertake(t *testing.T) {
        s := mustNew(t, 1, 5)
        submit(t, s, 0, Job{ID: "old", Base: 1, Cost: 1})
        submit(t, s, 30, Job{ID: "new", Base: 6, Cost: 1})
        // at tick 30 "old" has waited 30 ticks: 1 + min(5, 6) = 6, which ties with "new" (6); the older arrival wins
        if p, ok := s.Priority("old", 30); !ok || p != 6 {
            t.Fatalf("old priority at 30 = %d, %v", p, ok)
        }
        if p, _ := s.Priority("new", 30); p != 6 {
            t.Fatalf("new priority at 30 = %d", p)
        }
        expect(t, "t30", tick(t, s, 30), []string{"old"}, nil, nil)
    }

    func TestAgingFormula(t *testing.T) {
        s := mustNew(t, 1, 4)
        submit(t, s, 10, Job{ID: "x", Base: 2, Cost: 1})
        cases := []struct{ now, want int }{{10, 2}, {13, 2}, {14, 3}, {17, 3}, {18, 4}, {30, 7}, {31, 7}, {100, 7}, {1000, 7}}
        for _, c := range cases {
            if p, ok := s.Priority("x", c.now); !ok || p != c.want {
                t.Errorf("Priority at %d = %d, %v; want %d", c.now, p, ok, c.want)
            }
        }
        if _, ok := s.Priority("nope", 10); ok {
            t.Errorf("unknown job has a priority")
        }
    }

    func TestUrgencyBonus(t *testing.T) {
        s := mustNew(t, 1, 1000)
        submit(t, s, 0, Job{ID: "d", Base: 1, Cost: 5, Deadline: 20})
        // slack = 20 - now - 5 is 15, 3, 2, 1, 0 at these ticks
        for _, c := range []struct{ now, want int }{{0, 1}, {12, 1}, {13, 4}, {14, 4}, {15, 21}} {
            if p, ok := s.Priority("d", c.now); !ok || p != c.want {
                t.Errorf("Priority at %d = %d, %v; want %d", c.now, p, ok, c.want)
            }
        }
        // a job without a deadline never gets a bonus
        submit(t, s, 15, Job{ID: "n", Base: 1, Cost: 5})
        if p, _ := s.Priority("n", 15); p != 1 {
            t.Errorf("no-deadline job: %d", p)
        }
    }

    func TestSmallestDeadlines(t *testing.T) {
        s := mustNew(t, 1, 1000)
        // deadline 1 is a deadline like any other: this job has slack 0 at tick 0
        submit(t, s, 0, Job{ID: "one", Base: 2, Cost: 1, Deadline: 1})
        submit(t, s, 0, Job{ID: "two", Base: 2, Cost: 1, Deadline: 3})
        if p, ok := s.Priority("one", 0); !ok || p != 22 {
            t.Errorf("deadline 1: %d, %v; want 22", p, ok)
        }
        if p, ok := s.Priority("two", 0); !ok || p != 5 {
            t.Errorf("deadline 3, slack 2: %d, %v; want 5", p, ok)
        }
    }

    func TestUrgentDeadlineJumpsTheQueue(t *testing.T) {
        s := mustNew(t, 1, 1000)
        submit(t, s, 0, Job{ID: "busy", Base: 9, Cost: 7})
        submit(t, s, 0, Job{ID: "late", Base: 0, Cost: 5, Deadline: 12})
        submit(t, s, 0, Job{ID: "hi1", Base: 9, Cost: 3}, Job{ID: "hi2", Base: 9, Cost: 3})
        expect(t, "t0", tick(t, s, 0), []string{"busy"}, nil, nil)
        // tick 7: busy finishes; "late" has slack 12-7-5 = 0 -> priority 20 beats the Base-9 jobs
        expect(t, "t7", tick(t, s, 7), []string{"late"}, []string{"busy"}, nil)
        expect(t, "t12", tick(t, s, 12), []string{"hi1"}, []string{"late"}, nil)
    }

    func TestMissedDeadlinesAreDropped(t *testing.T) {
        s := mustNew(t, 1, 1000)
        submit(t, s, 0, Job{ID: "hog", Base: 9, Cost: 10}, Job{ID: "m1", Base: 0, Cost: 4, Deadline: 12})
        expect(t, "t0", tick(t, s, 0), []string{"hog"}, nil, nil)
        submit(t, s, 1, Job{ID: "m0", Base: 0, Cost: 4, Deadline: 11}, Job{ID: "ok", Base: 0, Cost: 2, Deadline: 100})
        // at tick 7 both could still finish in time (7+4 = 11 <= 11 and <= 12)
        expect(t, "t7", tick(t, s, 7), nil, nil, nil)
        // tick 8: m0 would end at 12 > 11
        expect(t, "t8", tick(t, s, 8), nil, nil, []string{"m0"})
        if s.Waiting() != 2 {
            t.Errorf("waiting = %d", s.Waiting())
        }
        // tick 10: hog finishes; m1 (10+4 = 14 > 12) is dropped; "ok" starts
        expect(t, "t10", tick(t, s, 10), []string{"ok"}, []string{"hog"}, []string{"m1"})
    }

    func TestDeadlineExactlyMet(t *testing.T) {
        s := mustNew(t, 1, 1000)
        submit(t, s, 0, Job{ID: "block", Base: 9, Cost: 3})
        submit(t, s, 0, Job{ID: "edge", Base: 0, Cost: 4, Deadline: 7})
        expect(t, "t0", tick(t, s, 0), []string{"block"}, nil, nil)
        // at tick 3, 3 + 4 == 7: still feasible, starts
        expect(t, "t3", tick(t, s, 3), []string{"edge"}, []string{"block"}, nil)
        expect(t, "t7", tick(t, s, 7), nil, []string{"edge"}, nil)
    }

    func TestMissedOrdering(t *testing.T) {
        s := mustNew(t, 1, 1000)
        submit(t, s, 0, Job{ID: "hog", Base: 9, Cost: 50})
        expect(t, "t0", tick(t, s, 0), []string{"hog"}, nil, nil)
        submit(t, s, 1, Job{ID: "z", Base: 1, Cost: 2, Deadline: 10})
        submit(t, s, 3, Job{ID: "b", Base: 1, Cost: 2, Deadline: 10}, Job{ID: "a", Base: 1, Cost: 2, Deadline: 10})
        expect(t, "t8", tick(t, s, 8), nil, nil, nil)
        // all three miss at tick 9: by arrival tick (z first), then by ID (a before b)
        expect(t, "t9", tick(t, s, 9), nil, nil, []string{"z", "a", "b"})
        if s.Waiting() != 0 {
            t.Errorf("waiting = %d", s.Waiting())
        }
    }

    func TestSubmitErrors(t *testing.T) {
        s := mustNew(t, 1, 5)
        bad := []Job{
            {ID: "", Base: 1, Cost: 1}, {ID: "x", Base: -1, Cost: 1}, {ID: "x", Base: 10, Cost: 1}, {ID: "x", Base: 1, Cost: 0}, {ID: "x", Base: 1, Cost: -2},
        }
        for _, j := range bad {
            if err := s.Submit(0, j); !errors.Is(err, ErrBadJob) {
                t.Errorf("Submit(%+v): %v", j, err)
            }
        }
        if err := s.Submit(0, Job{ID: "x", Base: 0, Cost: 1}); err != nil {
            t.Errorf("base 0: %v", err)
        }
        if err := s.Submit(0, Job{ID: "y", Base: 9, Cost: 1}); err != nil {
            t.Errorf("base 9: %v", err)
        }
        if err := s.Submit(0, Job{ID: "x", Base: 3, Cost: 1}); !errors.Is(err, ErrDuplicate) {
            t.Errorf("duplicate waiting: %v", err)
        }
        tick(t, s, 0)
        if err := s.Submit(0, Job{ID: "y", Base: 3, Cost: 1}); !errors.Is(err, ErrDuplicate) {
            t.Errorf("duplicate running: %v", err)
        }
        // once finished the id is free again
        tick(t, s, 1)
        tick(t, s, 2)
        if err := s.Submit(2, Job{ID: "y", Base: 3, Cost: 1}); err != nil {
            t.Errorf("reuse of a finished id: %v", err)
        }
    }

    func TestInfeasibleOnSubmit(t *testing.T) {
        s := mustNew(t, 1, 5)
        if err := s.Submit(10, Job{ID: "a", Base: 1, Cost: 5, Deadline: 14}); !errors.Is(err, ErrInfeasible) {
            t.Errorf("14: %v", err)
        }
        if err := s.Submit(10, Job{ID: "a", Base: 1, Cost: 5, Deadline: 15}); err != nil {
            t.Errorf("15: %v", err)
        }
        if s.Waiting() != 1 {
            t.Errorf("waiting = %d", s.Waiting())
        }
    }

    func TestSubmitCheckOrder(t *testing.T) {
        s := mustNew(t, 1, 5)
        tick(t, s, 10)
        // clock first, then validity, then duplicates, then feasibility
        if err := s.Submit(9, Job{ID: "", Base: 99, Cost: 0}); !errors.Is(err, ErrClock) {
            t.Errorf("clock: %v", err)
        }
        submit(t, s, 10, Job{ID: "dup", Base: 1, Cost: 1})
        if err := s.Submit(10, Job{ID: "dup", Base: 1, Cost: 5, Deadline: 11}); !errors.Is(err, ErrDuplicate) {
            t.Errorf("duplicate before feasibility: %v", err)
        }
        if err := s.Submit(10, Job{ID: "", Base: 1, Cost: 5, Deadline: 11}); !errors.Is(err, ErrBadJob) {
            t.Errorf("bad job before feasibility: %v", err)
        }
    }

    func TestClockNeverGoesBackwards(t *testing.T) {
        s := mustNew(t, 1, 5)
        tick(t, s, 5)
        if _, err := s.Tick(4); !errors.Is(err, ErrClock) {
            t.Errorf("Tick(4): %v", err)
        }
        if err := s.Submit(4, Job{ID: "a", Base: 1, Cost: 1}); !errors.Is(err, ErrClock) {
            t.Errorf("Submit(4): %v", err)
        }
        submit(t, s, 7, Job{ID: "a", Base: 1, Cost: 1})
        if _, err := s.Tick(6); !errors.Is(err, ErrClock) {
            t.Errorf("Tick(6) after Submit(7): %v", err)
        }
        if _, err := s.Tick(7); err != nil {
            t.Errorf("Tick(7): %v", err)
        }
        if err := s.Submit(7, Job{ID: "b", Base: 1, Cost: 1}); err != nil {
            t.Errorf("Submit at the current tick: %v", err)
        }
        if _, err := s.Tick(5); !errors.Is(err, ErrClock) {
            t.Errorf("late Tick(5): %v", err)
        }
    }

    func TestFailedTickChangesNothing(t *testing.T) {
        s := mustNew(t, 1, 5)
        submit(t, s, 5, Job{ID: "a", Base: 1, Cost: 1})
        s.Tick(5)
        s.Tick(3)
        if got := s.Running(); !reflect.DeepEqual(got, []string{"a"}) {
            t.Errorf("running %v", got)
        }
        expect(t, "t6", tick(t, s, 6), nil, []string{"a"}, nil)
    }

    func TestAgingUsesArrivalNotSubmitOrder(t *testing.T) {
        s := mustNew(t, 1, 10)
        submit(t, s, 0, Job{ID: "early", Base: 3, Cost: 1})
        submit(t, s, 25, Job{ID: "late", Base: 4, Cost: 1})
        // early: 3 + 2 = 5 at tick 25; late: 4 -> early first
        expect(t, "t25", tick(t, s, 25), []string{"early"}, nil, nil)
        expect(t, "t26", tick(t, s, 26), []string{"late"}, []string{"early"}, nil)
    }

    func TestBigScenario(t *testing.T) {
        s := mustNew(t, 3, 4)
        submit(t, s, 0,
            Job{ID: "j1", Base: 5, Cost: 6}, Job{ID: "j2", Base: 5, Cost: 2}, Job{ID: "j3", Base: 9, Cost: 4}, Job{ID: "j4", Base: 2, Cost: 3, Deadline: 20},
            Job{ID: "j5", Base: 7, Cost: 1}, Job{ID: "j6", Base: 0, Cost: 2, Deadline: 8})
        var log []string
        for now := 0; now <= 14; now++ {
            if now == 3 {
                submit(t, s, 3, Job{ID: "j7", Base: 6, Cost: 5, Deadline: 12})
            }
            r := tick(t, s, now)
            for _, id := range r.Started {
                log = append(log, "S"+id)
            }
            for _, id := range r.Finished {
                log = append(log, "F"+id)
            }
            for _, id := range r.Missed {
                log = append(log, "M"+id)
            }
        }
        want := []string{"Sj3", "Sj5", "Sj1", "Sj2", "Fj5", "Sj7", "Fj2", "Sj6", "Fj3", "Sj4", "Fj1", "Fj6", "Fj7", "Fj4"}
        if !reflect.DeepEqual(log, want) {
            t.Errorf("log %v\nwant %v", log, want)
        }
    }
'''))

LIB = Lib(
    name="agesched", lang="go", title="the agesched package",
    blurb="The nightly batch runner schedules its jobs with agesched, which orders them by priority that grows while they wait and by deadline urgency.",
    files={"go.mod": langs.go_mod("agesched"), "agesched.go": SRC, "README.md": README},
    visible_tests={"agesched_basic_test.go": VISIBLE},
    hidden_tests={"agesched_full_test.go": HIDDEN},
    mutate=["agesched.go"], difficulty=3, tags=["scheduling", "priority", "deadlines"],
)

register_libs([LIB], n=8)
