"""jobq (go): an in-memory job queue extended with peeking, cancelling, unique keys, priorities, limits, retries, delays, draining and dependencies."""
import random

from fx import dd, langs
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # jobq

    A small deterministic job queue for a batch worker (Go, standard library only). There are no goroutines and no wall clock: the
    caller drives it. `go test ./...` runs the tests.

    ## Layout

    * `jobq.go`: `Queue`, `Job`.
    * `jobq_test.go`: tests.

    ## Basics

    Errors are package variables and are returned wrapped (`fmt.Errorf("%w: ...")`), so callers use `errors.Is`.

    * `New()` makes an empty queue. `Enqueue(name, payload string, opts ...Option) (int, error)` adds a job and returns its id
      (1, 2, 3, ... in the order of the successful calls). The name is trimmed and must not be empty (`ErrBadName`). `Option` is
      `func(*Job) error`; an option that returns an error makes `Enqueue` fail with that error and add nothing (there are no
      options yet; `ErrBadOption` is what option constructors return for bad arguments).
    * A `Job` has `ID`, `Name`, `Payload`, `State` and `Reason`. The states are the constants `Queued`, `Running`, `Done` and
      `Failed` (the strings `"queued"`, `"running"`, `"done"`, `"failed"`). A new job is `Queued`.
    * `Next() (Job, bool)` takes the queued job with the lowest id, marks it `Running` and returns a copy (`false` when
      nothing is queued). `Complete(id)` marks a running job `Done`; `Fail(id, reason)` marks a running job `Failed` and stores
      the reason. Both return `ErrNotFound` for an unknown id and `ErrState` for a job that is not running.
    * `Get(id) (Job, error)` returns a copy of a job (`ErrNotFound`). `Counts() map[string]int` has one entry for each state
      (zero included).
''')

JOBQ = '''\
// Package jobq is a small deterministic in-memory job queue.
package jobq

import (
	"errors"
	"fmt"
	"strings"
@@uniq imports
)

// Job states.
const (
	Queued  = "queued"
	Running = "running"
	Done    = "done"
	Failed  = "failed"
	@@slot state_consts
)

var (
	ErrBadName   = errors.New("jobq: bad job name")
	ErrBadOption = errors.New("jobq: bad option")
	ErrNotFound  = errors.New("jobq: no such job")
	ErrState     = errors.New("jobq: wrong job state")
	@@slot errors
)

// Job is one unit of work.
type Job struct {
	ID      int
	Name    string
	Payload string
	State   string
	Reason  string
	@@slot job_fields
}

// Option changes a job while it is enqueued.
type Option func(*Job) error

@@blocks types

// Queue holds the jobs.
type Queue struct {
	jobs []*Job
	@@slot queue_fields
}

// New returns an empty queue.
func New() *Queue {
	q := &Queue{}
	@@slot new_queue
	return q
}

// Enqueue adds a job and returns its id.
func (q *Queue) Enqueue(name, payload string, opts ...Option) (int, error) {
	name = strings.TrimSpace(name)
	if name == "" {
		return 0, ErrBadName
	}
	j := &Job{ID: len(q.jobs) + 1, Name: name, Payload: payload, State: Queued}
	@@slot job_init
	for _, o := range opts {
		if err := o(j); err != nil {
			return 0, err
		}
	}
	@@slot enqueue_checks
	q.jobs = append(q.jobs, j)
	@@slot on_enqueue
	return j.ID, nil
}

func (q *Queue) find(id int) (*Job, error) {
	if id < 1 || id > len(q.jobs) {
		return nil, fmt.Errorf("%w: %d", ErrNotFound, id)
	}
	return q.jobs[id-1], nil
}

func (q *Queue) isReady(j *Job) bool {
	if j.State != Queued {
		return false
	}
	@@slot ready_checks
	return true
}

@@default better_fn
// better reports whether a should be started before b.
func better(a, b *Job) bool { return a.ID < b.ID }
@@end

func (q *Queue) pick() *Job {
	var best *Job
	for _, j := range q.jobs {
		if q.isReady(j) && (best == nil || better(j, best)) {
			best = j
		}
	}
	return best
}

// Next starts the next ready job.
func (q *Queue) Next() (Job, bool) {
	@@slot next_pre
	j := q.pick()
	if j == nil {
		return Job{}, false
	}
	j.State = Running
	@@slot on_start
	return *j, true
}

// Complete marks a running job done.
func (q *Queue) Complete(id int) error {
	j, err := q.find(id)
	if err != nil {
		return err
	}
	if j.State != Running {
		return fmt.Errorf("%w: job %d is %s", ErrState, id, j.State)
	}
	j.State = Done
	@@slot on_complete
	return nil
}

// Fail marks a running job failed.
func (q *Queue) Fail(id int, reason string) error {
	j, err := q.find(id)
	if err != nil {
		return err
	}
	if j.State != Running {
		return fmt.Errorf("%w: job %d is %s", ErrState, id, j.State)
	}
	@@default fail_rule
	j.State = Failed
	j.Reason = reason
	@@end
	@@slot on_fail
	return nil
}

// Get returns a copy of a job.
func (q *Queue) Get(id int) (Job, error) {
	j, err := q.find(id)
	if err != nil {
		return Job{}, err
	}
	return *j, nil
}

// Counts returns the number of jobs in every state.
func (q *Queue) Counts() map[string]int {
	out := map[string]int{}
	for _, s := range []string{
		Queued, Running, Done, Failed,
		@@slot extra_states
	} {
		out[s] = 0
	}
	for _, j := range q.jobs {
		out[j.State]++
	}
	return out
}

@@blocks methods
'''

TEST_HELPERS = '''\
@@uniq imports

var _ = errors.Is
var _ = reflect.DeepEqual

func __P__Enq(t *testing.T, q *Queue, name string, opts ...Option) int {
	t.Helper()
	id, err := q.Enqueue(name, "payload of "+name, opts...)
	if err != nil {
		t.Fatalf("Enqueue(%q): %v", name, err)
	}
	return id
}

func __P__Take(t *testing.T, q *Queue) Job {
	t.Helper()
	j, ok := q.Next()
	if !ok {
		t.Fatal("Next: nothing ready")
	}
	return j
}

func __P__Total(q *Queue) int {
	n := 0
	for _, c := range q.Counts() {
		n += c
	}
	return n
}

func __P__State(t *testing.T, q *Queue, id int) string {
	t.Helper()
	j, err := q.Get(id)
	if err != nil {
		t.Fatal(err)
	}
	return j.State
}
'''

VISIBLE = '''\
package jobq

import (
	"errors"
	"reflect"
	"testing"
)

''' + TEST_HELPERS.replace("__P__", "v").replace("@@uniq imports\n\n", "") + '''
func TestEnqueueAndNext(t *testing.T) {
	q := New()
	if _, ok := q.Next(); ok {
		t.Fatal("empty queue")
	}
	a := vEnq(t, q, "  first ")
	b := vEnq(t, q, "second")
	if a != 1 || b != 2 {
		t.Fatalf("ids %d %d", a, b)
	}
	if _, err := q.Enqueue("  ", "x"); !errors.Is(err, ErrBadName) {
		t.Fatalf("blank name: %v", err)
	}
	j := vTake(t, q)
	if j.ID != 1 || j.Name != "first" || j.State != Running || j.Payload != "payload of   first " {
		t.Fatalf("job %+v", j)
	}
	if got := vState(t, q, 2); got != Queued {
		t.Fatalf("second is %s", got)
	}
}

func TestCompleteFailCounts(t *testing.T) {
	q := New()
	vEnq(t, q, "a")
	vEnq(t, q, "b")
	vTake(t, q)
	vTake(t, q)
	if err := q.Complete(1); err != nil {
		t.Fatal(err)
	}
	if err := q.Fail(2, "boom"); err != nil {
		t.Fatal(err)
	}
	if err := q.Complete(1); !errors.Is(err, ErrState) {
		t.Fatalf("complete twice: %v", err)
	}
	if err := q.Fail(9, "x"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("unknown: %v", err)
	}
	c := q.Counts()
	if c["queued"] != 0 || c["running"] != 0 || c["done"] != 1 || c["failed"] != 1 {
		t.Fatalf("counts %v", c)
	}
}
@@blocks tests
'''

HIDDEN = '''\
package jobq

import (
	"errors"
	"reflect"
	"testing"
)

''' + TEST_HELPERS.replace("__P__", "h").replace("@@uniq imports\n\n", "") + '''
@@default tick_fn
// hTick moves the queue clock far ahead, so that jobs that wait for a time are ready (there is no clock yet).
func hTick(q *Queue) {}
@@end

@@default extra_counts
var hExtraCounts = map[string]int{}
@@end

func hWantCounts(m map[string]int) map[string]int {
	for k, v := range hExtraCounts {
		m[k] = v
	}
	return m
}

func hIs(t *testing.T, name string, err, target error) {
	t.Helper()
	if !errors.Is(err, target) {
		t.Errorf("%s: got %v, want %v", name, err, target)
	}
}

func hEq(t *testing.T, name string, got, want interface{}) {
	t.Helper()
	if !reflect.DeepEqual(got, want) {
		t.Errorf("%s: got %v, want %v", name, got, want)
	}
}

func TestBaseEnqueue(t *testing.T) {
	q := New()
	for _, bad := range []string{"", " ", "\\t\\n"} {
		_, err := q.Enqueue(bad, "p")
		hIs(t, "name "+bad, err, ErrBadName)
	}
	hEq(t, "first id", hEnq(t, q, "a"), 1)
	_, err := q.Enqueue("", "p")
	hIs(t, "bad again", err, ErrBadName)
	hEq(t, "second id", hEnq(t, q, "  b  "), 2)
	j, err := q.Get(2)
	hEq(t, "get", []interface{}{j.ID, j.Name, j.Payload, j.State, j.Reason, err}, []interface{}{2, "b", "payload of   b  ", Queued, "", error(nil)})
	_, err = q.Enqueue("c", "p", func(*Job) error { return ErrBadOption })
	hIs(t, "failing option", err, ErrBadOption)
	hEq(t, "nothing added", hTotal(q), 2)
	hEq(t, "id continues", hEnq(t, q, "c"), 3)
	hEq(t, "empty payload is fine", func() int { id, _ := q.Enqueue("d", ""); return id }(), 4)
}

func TestBaseNextOrder(t *testing.T) {
	q := New()
	for _, n := range []string{"a", "b", "c"} {
		hEnq(t, q, n)
	}
	hEq(t, "first", hTake(t, q).Name, "a")
	hEq(t, "second", hTake(t, q).Name, "b")
	hEnq(t, q, "d")
	hEq(t, "third", hTake(t, q).Name, "c")
	hEq(t, "fourth", hTake(t, q).Name, "d")
	if _, ok := q.Next(); ok {
		t.Error("nothing left")
	}
	hEq(t, "state", hState(t, q, 1), Running)
}

func TestBaseCompleteAndFail(t *testing.T) {
	q := New()
	hEnq(t, q, "a")
	hEnq(t, q, "b")
	hEnq(t, q, "c")
	hIs(t, "complete a queued job", q.Complete(1), ErrState)
	hIs(t, "fail a queued job", q.Fail(1, "x"), ErrState)
	hIs(t, "complete unknown", q.Complete(0), ErrNotFound)
	hIs(t, "complete unknown 2", q.Complete(99), ErrNotFound)
	hIs(t, "fail unknown", q.Fail(-1, "x"), ErrNotFound)
	hTake(t, q)
	hTake(t, q)
	hEq(t, "complete", q.Complete(1), error(nil))
	hEq(t, "fail", q.Fail(2, "disk full"), error(nil))
	hIs(t, "complete a done job", q.Complete(1), ErrState)
	hIs(t, "fail a done job", q.Fail(1, "x"), ErrState)
	hIs(t, "complete a failed job", q.Complete(2), ErrState)
	hIs(t, "fail a failed job", q.Fail(2, "x"), ErrState)
	j1, _ := q.Get(1)
	j2, _ := q.Get(2)
	hEq(t, "states", []string{j1.State, j2.State, hState(t, q, 3)}, []string{Done, Failed, Queued})
	hEq(t, "reason", []string{j1.Reason, j2.Reason}, []string{"", "disk full"})
	_, err := q.Get(7)
	hIs(t, "get unknown", err, ErrNotFound)
	hEq(t, "counts", q.Counts(), hWantCounts(map[string]int{"queued": 1, "running": 0, "done": 1, "failed": 1}))
	got, _ := q.Get(1)
	got.State = "hacked"
	hEq(t, "Get returns a copy", hState(t, q, 1), Done)
	hEq(t, "counts of an empty queue", New().Counts(), hWantCounts(map[string]int{"queued": 0, "running": 0, "done": 0, "failed": 0}))
}
@@blocks tests
'''


def make_slices(rng: random.Random):
    max_attempts_cap = rng.choice([5, 10])
    S = []

    S.append(Slice(
        id="peek", title="Peeking at the next job", d=1,
        pitch=("The dashboard wants to show what runs next without starting it.",
               "Callers need to look at the next job without taking it."),
        reqs=("`queue.Peek() (Job, bool)` returns a copy of the job that `Next` would start, or `false` when there is none. It changes nothing: the job stays in its state.",),
        code={
            "jobq.go::methods": '''
                // Peek returns the job that Next would start, without starting it.
                func (q *Queue) Peek() (Job, bool) {
                	j := q.pick()
                	if j == nil {
                		return Job{}, false
                	}
                	return *j, true
                }
            ''',
        },
        readme="## Peeking at the next job\n\n`queue.Peek()` returns the job `Next` would start without changing it.\n",
        vtests='''
            func TestPeekBasic(t *testing.T) {
            	q := New()
            	vEnq(t, q, "a")
            	if j, ok := q.Peek(); !ok || j.Name != "a" || j.State != Queued {
            		t.Fatalf("%+v %v", j, ok)
            	}
            }
        ''',
        tests='''
            func TestPeek(t *testing.T) {
            	q := New()
            	if _, ok := q.Peek(); ok {
            		t.Error("empty queue")
            	}
            	hEnq(t, q, "a")
            	hEnq(t, q, "b")
            	j, ok := q.Peek()
            	hEq(t, "peek", []interface{}{j.ID, j.Name, j.State, ok}, []interface{}{1, "a", Queued, true})
            	j, _ = q.Peek()
            	hEq(t, "peek again", j.ID, 1)
            	hEq(t, "still queued", hState(t, q, 1), Queued)
            	hEq(t, "next agrees", hTake(t, q).ID, 1)
            	j, _ = q.Peek()
            	hEq(t, "after next", j.ID, 2)
            	hTake(t, q)
            	if _, ok := q.Peek(); ok {
            		t.Error("nothing left")
            	}
            	hEq(t, "counts", q.Counts()["queued"], 0)
            }
        ''',
    ))

    S.append(Slice(
        id="cancel", title="Cancelling jobs", d=2,
        pitch=("A customer withdraws an order and the matching jobs still run.",
               "Queued jobs need to be cancellable."),
        reqs=("`queue.Cancel(id) error` cancels a queued job: its state becomes the new constant `Canceled` (`\"canceled\"`) and its `Reason` is `\"canceled\"`. Unknown ids are `ErrNotFound`; a job in any other state (running, done, failed, already canceled) is `ErrState`. Canceled jobs are never started, and `Counts()` has an entry `\"canceled\"` as well.",),
        code={
            "jobq.go::state_consts": 'Canceled = "canceled"',
            "jobq.go::extra_states": "Canceled,",
            "T::extra_counts": 'var hExtraCounts = map[string]int{"canceled": 0}',
            "jobq.go::methods": '''
                // Cancel cancels a queued job.
                func (q *Queue) Cancel(id int) error {
                	j, err := q.find(id)
                	if err != nil {
                		return err
                	}
                	if j.State != Queued {
                		return fmt.Errorf("%w: job %d is %s", ErrState, id, j.State)
                	}
                	j.State = Canceled
                	j.Reason = "canceled"
                	@@slot on_cancel
                	return nil
                }
            ''',
        },
        readme="## Cancelling jobs\n\n`queue.Cancel(id)` turns a queued job into `Canceled` (reason `canceled`); other states are `ErrState`. `Counts()` gets a `canceled` entry.\n",
        vtests='''
            func TestCancelBasic(t *testing.T) {
            	q := New()
            	vEnq(t, q, "a")
            	if err := q.Cancel(1); err != nil {
            		t.Fatal(err)
            	}
            	if _, ok := q.Next(); ok {
            		t.Fatal("a canceled job must not run")
            	}
            }
        ''',
        tests='''
            func TestCancel(t *testing.T) {
            	q := New()
            	for _, n := range []string{"a", "b", "c", "d"} {
            		hEnq(t, q, n)
            	}
            	hEq(t, "cancel", q.Cancel(2), error(nil))
            	j, _ := q.Get(2)
            	hEq(t, "canceled", []string{j.State, j.Reason}, []string{Canceled, "canceled"})
            	hEq(t, "constant", Canceled, "canceled")
            	hEq(t, "next skips it", []string{hTake(t, q).Name, hTake(t, q).Name}, []string{"a", "c"})
            	hIs(t, "running", q.Cancel(1), ErrState)
            	hIs(t, "again", q.Cancel(2), ErrState)
            	hIs(t, "unknown", q.Cancel(9), ErrNotFound)
            	hIs(t, "unknown 0", q.Cancel(0), ErrNotFound)
            	q.Complete(1)
            	hIs(t, "done", q.Cancel(1), ErrState)
            	q.Fail(3, "x")
            	hIs(t, "failed", q.Cancel(3), ErrState)
            	hEq(t, "counts", q.Counts(), map[string]int{"queued": 1, "running": 0, "done": 1, "failed": 1, "canceled": 1})
            	hEq(t, "d is next", hTake(t, q).Name, "d")
            }
        ''',
        cross={
            "peek": {"tests": '''
                func TestPeekSkipsCanceled(t *testing.T) {
                	q := New()
                	hEnq(t, q, "a")
                	hEnq(t, q, "b")
                	q.Cancel(1)
                	j, ok := q.Peek()
                	hEq(t, "peek", []interface{}{j.ID, ok}, []interface{}{2, true})
                	q.Cancel(2)
                	if _, ok := q.Peek(); ok {
                		t.Error("nothing to peek at")
                	}
                }
            '''},
        },
    ))

    S.append(Slice(
        id="unique", title="Unique jobs", d=2,
        pitch=("An impatient user clicked 'export' five times and five identical exports ran.",
               "Jobs with the same key must not be queued twice."),
        reqs=("`jobq.Unique(key string) Option` gives a job a key (`Job.Key`; an empty or blank key is `ErrBadOption`). When `Enqueue` is called with a key that belongs to a job that is still active (queued or running), nothing is added and the result is the id of that active job together with the new error `ErrDuplicate`. A job that is done or failed (or canceled, if the queue can cancel) no longer holds its key. Jobs without a key never clash, and the id counter is not used up by a refused call.",),
        code={
            "jobq.go::errors": 'ErrDuplicate = errors.New("jobq: a job with this key is already active")',
            "jobq.go::job_fields": "Key     string",
            "jobq.go::types": '''
                // Unique gives a job a key: only one job with a key can be active at a time.
                func Unique(key string) Option {
                	return func(j *Job) error {
                		if strings.TrimSpace(key) == "" {
                			return fmt.Errorf("%w: a key must not be blank", ErrBadOption)
                		}
                		j.Key = key
                		return nil
                	}
                }
            ''',
            "jobq.go::enqueue_checks": '''
                if j.Key != "" {
                	for _, o := range q.jobs {
                		if o.Key == j.Key && (o.State == Queued || o.State == Running) {
                			return o.ID, ErrDuplicate
                		}
                	}
                }
            ''',
        },
        readme="## Unique jobs\n\n`jobq.Unique(key)` allows one active (queued or running) job per key; a clash returns the existing id and `ErrDuplicate`.\n",
        vtests='''
            func TestUniqueBasic(t *testing.T) {
            	q := New()
            	vEnq(t, q, "export", Unique("exp-1"))
            	if id, err := q.Enqueue("export", "x", Unique("exp-1")); id != 1 || !errors.Is(err, ErrDuplicate) {
            		t.Fatalf("%d %v", id, err)
            	}
            }
        ''',
        tests='''
            func TestUnique(t *testing.T) {
            	q := New()
            	a := hEnq(t, q, "export", Unique("k1"))
            	id, err := q.Enqueue("export", "again", Unique("k1"))
            	hIs(t, "duplicate", err, ErrDuplicate)
            	hEq(t, "existing id", id, a)
            	hEq(t, "nothing added", hTotal(q), 1)
            	hEq(t, "other key", hEnq(t, q, "export", Unique("k2")), 2)
            	hEq(t, "no key", hEnq(t, q, "plain"), 3)
            	hEq(t, "no key again", hEnq(t, q, "plain"), 4)
            	hEq(t, "id counter", hEnq(t, q, "next"), 5)
            	hEq(t, "key is stored", func() string { j, _ := q.Get(1); return j.Key }(), "k1")
            	j := hTake(t, q)
            	hEq(t, "running", j.State, Running)
            	id, err = q.Enqueue("export", "again", Unique("k1"))
            	hIs(t, "duplicate while running", err, ErrDuplicate)
            	hEq(t, "id while running", id, 1)
            	q.Complete(1)
            	id, err = q.Enqueue("export", "later", Unique("k1"))
            	hEq(t, "free after done", []interface{}{id, err}, []interface{}{6, error(nil)})
            	hTake(t, q)
            	hTake(t, q)
            	hTake(t, q)
            	hTake(t, q)
            	hTake(t, q)
            	q.Fail(6, "boom")
            	id, err = q.Enqueue("export", "after failure", Unique("k1"))
            	hEq(t, "free after failure", []interface{}{id, err}, []interface{}{7, error(nil)})
            }

            func TestUniqueKeyValidation(t *testing.T) {
            	q := New()
            	for _, bad := range []string{"", " ", "\\t"} {
            		_, err := q.Enqueue("a", "p", Unique(bad))
            		hIs(t, "key "+bad, err, ErrBadOption)
            	}
            	hEq(t, "nothing added", hTotal(q), 0)
            	hEq(t, "first id", hEnq(t, q, "a", Unique(" padded ")), 1)
            	_, err := q.Enqueue("a", "p", Unique(" padded "))
            	hIs(t, "keys are compared as given", err, ErrDuplicate)
            	hEq(t, "a different spelling is a different key", hEnq(t, q, "a", Unique("padded")), 2)
            }
        ''',
        cross={
            "cancel": {
                "reqs": ("A canceled job no longer holds its key.",),
                "tests": '''
                    func TestCancelFreesTheKey(t *testing.T) {
                    	q := New()
                    	hEnq(t, q, "a", Unique("k"))
                    	_, err := q.Enqueue("a", "p", Unique("k"))
                    	hIs(t, "clash", err, ErrDuplicate)
                    	q.Cancel(1)
                    	hEq(t, "free after cancel", hEnq(t, q, "a", Unique("k")), 2)
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="priority", title="Priorities", d=2,
        pitch=("Password reset mails wait behind five thousand newsletter jobs.",
               "Urgent jobs must be able to jump the queue."),
        reqs=("`jobq.Priority(n int) Option` sets `Job.Priority` (any integer, higher is more urgent, the default is 0). `Next` (and everything that picks a job) now takes the ready job with the highest priority and, among jobs with the same priority, the lowest id. A running job is never interrupted.",),
        code={
            "jobq.go::job_fields": "Priority int",
            "jobq.go::types": '''
                // Priority makes a job more (or less) urgent; the default is 0.
                func Priority(n int) Option {
                	return func(j *Job) error {
                		j.Priority = n
                		return nil
                	}
                }
            ''',
            "jobq.go::better_fn": '''
                func better(a, b *Job) bool {
                	if a.Priority != b.Priority {
                		return a.Priority > b.Priority
                	}
                	return a.ID < b.ID
                }
            ''',
        },
        readme="## Priorities\n\n`jobq.Priority(n)` (default 0, higher first); equal priorities run in id order.\n",
        vtests='''
            func TestPriorityBasic(t *testing.T) {
            	q := New()
            	vEnq(t, q, "low")
            	vEnq(t, q, "urgent", Priority(5))
            	if j := vTake(t, q); j.Name != "urgent" {
            		t.Fatalf("%+v", j)
            	}
            }
        ''',
        tests='''
            func TestPriorityOrder(t *testing.T) {
            	q := New()
            	hEnq(t, q, "a", Priority(1))
            	hEnq(t, q, "b", Priority(5))
            	hEnq(t, q, "c", Priority(5))
            	hEnq(t, q, "d")
            	hEnq(t, q, "e", Priority(-3))
            	hEnq(t, q, "f", Priority(0))
            	var order []string
            	for i := 0; i < 6; i++ {
            		order = append(order, hTake(t, q).Name)
            	}
            	hEq(t, "order", order, []string{"b", "c", "a", "d", "f", "e"})
            	hEq(t, "stored", func() int { j, _ := q.Get(2); return j.Priority }(), 5)
            	hEq(t, "default", func() int { j, _ := q.Get(4); return j.Priority }(), 0)
            }

            func TestPriorityDoesNotInterrupt(t *testing.T) {
            	q := New()
            	hEnq(t, q, "slow")
            	first := hTake(t, q)
            	hEnq(t, q, "urgent", Priority(100))
            	hEq(t, "running job is untouched", hState(t, q, first.ID), Running)
            	hEq(t, "urgent is next", hTake(t, q).Name, "urgent")
            	_, err := q.Enqueue("x", "p", func(*Job) error { return ErrBadOption })
            	hIs(t, "other options still fail", err, ErrBadOption)
            }
        ''',
        cross={
            "peek": {"tests": '''
                func TestPeekFollowsPriority(t *testing.T) {
                	q := New()
                	hEnq(t, q, "a")
                	hEnq(t, q, "b", Priority(2))
                	j, _ := q.Peek()
                	hEq(t, "peek", j.Name, "b")
                }
            '''},
            "cancel": {"tests": '''
                func TestCanceledJobsDoNotBlockPriorities(t *testing.T) {
                	q := New()
                	hEnq(t, q, "a")
                	hEnq(t, q, "b", Priority(9))
                	q.Cancel(2)
                	hEq(t, "a runs", hTake(t, q).Name, "a")
                }
            '''},
        },
    ))

    S.append(Slice(
        id="limit", title="Concurrency limit", d=2,
        pitch=("The worker pool has four slots and nothing stops the caller from starting forty jobs.",
               "The queue should refuse to start more jobs than the workers can handle."),
        reqs=("`queue.SetLimit(n int) error` sets the largest number of jobs that may be running at the same time (`n` of 0 means no limit, the default; a negative `n` is `ErrBadOption`) and `queue.Running() int` returns the number of jobs that are running. While the limit is reached `Next` returns `false` even if jobs are queued; completing or failing a running job makes room again. Lowering the limit does not stop jobs that already run.",),
        code={
            "jobq.go::queue_fields": "limit int",
            "jobq.go::next_pre": '''
                if q.limit > 0 && q.Running() >= q.limit {
                	return Job{}, false
                }
            ''',
            "jobq.go::methods": '''
                // SetLimit sets the number of jobs that may run at once (0 means no limit).
                func (q *Queue) SetLimit(n int) error {
                	if n < 0 {
                		return fmt.Errorf("%w: limit must not be negative", ErrBadOption)
                	}
                	q.limit = n
                	return nil
                }

                // Running is the number of running jobs.
                func (q *Queue) Running() int {
                	n := 0
                	for _, j := range q.jobs {
                		if j.State == Running {
                			n++
                		}
                	}
                	return n
                }
            ''',
        },
        readme="## Concurrency limit\n\n`queue.SetLimit(n)` (0 = unlimited, negative is `ErrBadOption`) and `queue.Running()`: `Next` returns `false` while `n` jobs run.\n",
        vtests='''
            func TestLimitBasic(t *testing.T) {
            	q := New()
            	q.SetLimit(1)
            	vEnq(t, q, "a")
            	vEnq(t, q, "b")
            	vTake(t, q)
            	if _, ok := q.Next(); ok {
            		t.Fatal("limit reached")
            	}
            }
        ''',
        tests='''
            func TestLimit(t *testing.T) {
            	q := New()
            	for _, n := range []string{"a", "b", "c", "d"} {
            		hEnq(t, q, n)
            	}
            	hEq(t, "set", q.SetLimit(2), error(nil))
            	hTake(t, q)
            	hTake(t, q)
            	hEq(t, "running", q.Running(), 2)
            	if _, ok := q.Next(); ok {
            		t.Error("third job must wait")
            	}
            	q.Complete(1)
            	hEq(t, "running after complete", q.Running(), 1)
            	hEq(t, "room again", hTake(t, q).Name, "c")
            	if _, ok := q.Next(); ok {
            		t.Error("full again")
            	}
            	q.Fail(2, "x")
            	hEq(t, "room after failure", hTake(t, q).Name, "d")
            	hEq(t, "queued", q.Counts()["queued"], 0)
            }

            func TestLimitChanges(t *testing.T) {
            	q := New()
            	for _, n := range []string{"a", "b", "c", "d"} {
            		hEnq(t, q, n)
            	}
            	hEq(t, "default is unlimited", q.Running(), 0)
            	hTake(t, q)
            	hTake(t, q)
            	hTake(t, q)
            	hEq(t, "three running", q.Running(), 3)
            	q.SetLimit(1)
            	hEq(t, "running jobs are not stopped", q.Running(), 3)
            	if _, ok := q.Next(); ok {
            		t.Error("over the lowered limit")
            	}
            	q.Complete(1)
            	q.Complete(2)
            	if _, ok := q.Next(); ok {
            		t.Error("one running, limit 1")
            	}
            	q.Complete(3)
            	hEq(t, "now", hTake(t, q).Name, "d")
            	hEq(t, "unlimited again", q.SetLimit(0), error(nil))
            	hIs(t, "negative", q.SetLimit(-1), ErrBadOption)
            	for _, n := range []string{"e", "f", "g"} {
            		hEnq(t, q, n)
            	}
            	hTake(t, q)
            	hTake(t, q)
            	hTake(t, q)
            	hEq(t, "a failed call leaves the limit alone", q.Running(), 4)
            }
        ''',
        cross={
            "peek": {
                "reqs": ("`Peek` ignores the limit: it shows the job that would start once a slot is free.",),
                "tests": '''
                    func TestPeekIgnoresTheLimit(t *testing.T) {
                    	q := New()
                    	q.SetLimit(1)
                    	hEnq(t, q, "a")
                    	hEnq(t, q, "b")
                    	hTake(t, q)
                    	if _, ok := q.Next(); ok {
                    		t.Error("limit reached")
                    	}
                    	j, ok := q.Peek()
                    	hEq(t, "peek", []interface{}{j.Name, ok}, []interface{}{"b", true})
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="retry", title="Retries", d=3,
        pitch=("A flaky API makes jobs fail once in a while and every failure needs a manual restart.",
               "Failed jobs should be retried a few times before they are given up."),
        reqs=(f"`jobq.MaxAttempts(n int) Option` sets how often a job may be started (`n` from 1 to {max_attempts_cap}, otherwise `ErrBadOption`; the default is 1). `Job` gets the fields `Attempts` (how often it has been started: `Next` increases it) and `MaxAttempts`.",
              "`Fail(id, reason)` on a running job whose `Attempts` is below `MaxAttempts` puts it back to `Queued` (the reason is stored in `Reason`) instead of failing it; it keeps its place in line, which is decided by its id (and priority, if there are priorities). When the attempts are used up the job is `Failed` for good, with the reason of the last failure. `Complete` works as before whatever the attempt number."),
        code={
            "jobq.go::job_fields": '''
                Attempts    int
                MaxAttempts int
            ''',
            "jobq.go::job_init": "j.MaxAttempts = 1",
            "jobq.go::types": f'''
                // MaxAttempts sets how often a job may be started (1 to {max_attempts_cap}).
                func MaxAttempts(n int) Option {{
                	return func(j *Job) error {{
                		if n < 1 || n > {max_attempts_cap} {{
                			return fmt.Errorf("%w: attempts must be between 1 and {max_attempts_cap}", ErrBadOption)
                		}}
                		j.MaxAttempts = n
                		return nil
                	}}
                }}
            ''',
            "jobq.go::on_start": "j.Attempts++",
            "jobq.go::fail_rule": '''
                j.Reason = reason
                if j.Attempts < j.MaxAttempts {
                	j.State = Queued
                	@@slot on_retry
                } else {
                	j.State = Failed
                }
            ''',
        },
        readme=f"## Retries\n\n`jobq.MaxAttempts(n)` (1 to {max_attempts_cap}, default 1), `Job.Attempts` and `Job.MaxAttempts`. `Fail` requeues a job that has attempts left (keeping its place in line) and fails it for good otherwise.\n",
        vtests='''
            func TestRetryBasic(t *testing.T) {
            	q := New()
            	vEnq(t, q, "flaky", MaxAttempts(2))
            	vTake(t, q)
            	q.Fail(1, "boom")
            	if got := vState(t, q, 1); got != Queued {
            		t.Fatalf("state %s", got)
            	}
            }
        ''',
        tests=fmt('''
            func TestRetries(t *testing.T) {
            	q := New()
            	hEnq(t, q, "flaky", MaxAttempts(3))
            	j := hTake(t, q)
            	hEq(t, "first start", []interface{}{j.Attempts, j.MaxAttempts}, []interface{}{1, 3})
            	hEq(t, "fail", q.Fail(1, "first failure"), error(nil))
            	got, _ := q.Get(1)
            	hEq(t, "requeued", []interface{}{got.State, got.Reason, got.Attempts}, []interface{}{Queued, "first failure", 1})
            	hTick(q)
            	hEq(t, "second start", hTake(t, q).Attempts, 2)
            	q.Fail(1, "second failure")
            	hTick(q)
            	hEq(t, "third start", hTake(t, q).Attempts, 3)
            	q.Fail(1, "last failure")
            	got, _ = q.Get(1)
            	hEq(t, "given up", []interface{}{got.State, got.Reason, got.Attempts}, []interface{}{Failed, "last failure", 3})
            	if _, ok := q.Next(); ok {
            		t.Error("a failed job does not run again")
            	}
            }

            func TestRetriesKeepTheirPlace(t *testing.T) {
            	q := New()
            	hEnq(t, q, "a", MaxAttempts(2))
            	hEnq(t, q, "b")
            	hEq(t, "a", hTake(t, q).Name, "a")
            	q.Fail(1, "again")
            	hTick(q)
            	hEq(t, "a is first again", hTake(t, q).Name, "a")
            	q.Complete(1)
            	got, _ := q.Get(1)
            	hEq(t, "done after a retry", []interface{}{got.State, got.Attempts, got.Reason}, []interface{}{Done, 2, "again"})
            	hEq(t, "b", hTake(t, q).Name, "b")
            	hEq(t, "plain jobs fail at once", q.Fail(2, "x"), error(nil))
            	hEq(t, "b failed", hState(t, q, 2), Failed)
            }

            func TestAttemptOptionValidation(t *testing.T) {
            	q := New()
            	for _, bad := range []int{0, -1, __M__ + 1, 100} {
            		_, err := q.Enqueue("a", "p", MaxAttempts(bad))
            		hIs(t, "attempts", err, ErrBadOption)
            	}
            	hEq(t, "nothing added", hTotal(q), 0)
            	hEq(t, "maximum", hEnq(t, q, "a", MaxAttempts(__M__)), 1)
            	hEq(t, "one", hEnq(t, q, "b", MaxAttempts(1)), 2)
            	hEq(t, "no option", hEnq(t, q, "c"), 3)
            	j, _ := q.Get(3)
            	hEq(t, "default is 1", j.MaxAttempts, 1)
            }
        ''', M=max_attempts_cap),
        cross={
            "priority": {"tests": '''
                func TestRetriedJobsKeepTheirPriority(t *testing.T) {
                	q := New()
                	hEnq(t, q, "a", MaxAttempts(2), Priority(5))
                	hEnq(t, q, "b", Priority(5))
                	hEnq(t, q, "c", Priority(9))
                	hEq(t, "c first", hTake(t, q).Name, "c")
                	hEq(t, "a", hTake(t, q).Name, "a")
                	q.Fail(1, "x")
                	hTick(q)
                	hEq(t, "a again before b", hTake(t, q).Name, "a")
                	hEq(t, "then b", hTake(t, q).Name, "b")
                }
            '''},
            "unique": {"tests": '''
                func TestRetryingJobsHoldTheirKey(t *testing.T) {
                	q := New()
                	hEnq(t, q, "a", MaxAttempts(2), Unique("k"))
                	hTake(t, q)
                	q.Fail(1, "x")
                	_, err := q.Enqueue("a", "p", Unique("k"))
                	hIs(t, "queued again", err, ErrDuplicate)
                	hTick(q)
                	hTake(t, q)
                	q.Fail(1, "x")
                	hEq(t, "free after the last failure", hEnq(t, q, "a", Unique("k")), 2)
                }
            '''},
            "limit": {"tests": '''
                func TestRetriedJobsFreeTheirSlot(t *testing.T) {
                	q := New()
                	q.SetLimit(1)
                	hEnq(t, q, "a", MaxAttempts(2))
                	hEnq(t, q, "b")
                	hTake(t, q)
                	q.Fail(1, "x")
                	hEq(t, "running", q.Running(), 0)
                	hTick(q)
                	hEq(t, "a again", hTake(t, q).Name, "a")
                }
            '''},
        },
    ))

    S.append(Slice(
        id="delay", title="Delayed jobs", d=3,
        pitch=("Reminder mails should go out in an hour, not right now.",
               "Jobs need a way to wait before they become ready."),
        reqs=("The queue has a logical clock: `queue.Now() int` starts at 0 and `queue.Advance(n int) error` moves it forward by `n` (`n` of at least 0, otherwise `ErrBadOption`). `jobq.RunAfter(t int) Option` (`t` of at least 0, otherwise `ErrBadOption`) sets `Job.RunAfter`: the job is not ready (not started by `Next`, not shown by `Peek`) while `Now()` is below it. The default is 0. A delayed job does not block jobs behind it.",),
        code={
            "T::tick_fn": '''
                // hTick moves the queue clock far ahead, so that every waiting job is ready.
                func hTick(q *Queue) { q.Advance(100) }
            ''',
            "jobq.go::job_fields": "RunAfter int",
            "jobq.go::queue_fields": "now int",
            "jobq.go::types": '''
                // RunAfter keeps a job from starting before the queue clock reaches t.
                func RunAfter(t int) Option {
                	return func(j *Job) error {
                		if t < 0 {
                			return fmt.Errorf("%w: the start time must not be negative", ErrBadOption)
                		}
                		j.RunAfter = t
                		return nil
                	}
                }
            ''',
            "jobq.go::ready_checks": '''
                if j.RunAfter > q.now {
                	return false
                }
            ''',
            "jobq.go::methods": '''
                // Now is the queue clock.
                func (q *Queue) Now() int { return q.now }

                // Advance moves the queue clock forward.
                func (q *Queue) Advance(n int) error {
                	if n < 0 {
                		return fmt.Errorf("%w: cannot go back in time", ErrBadOption)
                	}
                	q.now += n
                	return nil
                }
            ''',
        },
        readme="## Delayed jobs\n\nA logical clock (`queue.Now()`, `queue.Advance(n)`) and `jobq.RunAfter(t)`: a job is only ready once `Now() >= t`; delayed jobs do not block the ones behind them.\n",
        vtests='''
            func TestDelayBasic(t *testing.T) {
            	q := New()
            	vEnq(t, q, "later", RunAfter(5))
            	if _, ok := q.Next(); ok {
            		t.Fatal("not yet")
            	}
            	q.Advance(5)
            	vTake(t, q)
            }
        ''',
        tests='''
            func TestDelay(t *testing.T) {
            	q := New()
            	hEq(t, "clock", q.Now(), 0)
            	hEnq(t, q, "later", RunAfter(5))
            	hEnq(t, q, "now")
            	hEnq(t, q, "zero", RunAfter(0))
            	hEq(t, "now first", hTake(t, q).Name, "now")
            	hEq(t, "zero", hTake(t, q).Name, "zero")
            	if _, ok := q.Next(); ok {
            		t.Error("later is not ready")
            	}
            	hEq(t, "advance", q.Advance(4), error(nil))
            	hEq(t, "clock", q.Now(), 4)
            	if _, ok := q.Next(); ok {
            		t.Error("still one tick early")
            	}
            	q.Advance(1)
            	hEq(t, "ready", hTake(t, q).Name, "later")
            	hEq(t, "stored", func() int { j, _ := q.Get(1); return j.RunAfter }(), 5)
            	hEq(t, "advance by zero", q.Advance(0), error(nil))
            	hEq(t, "clock stays", q.Now(), 5)
            }

            func TestDelayValidation(t *testing.T) {
            	q := New()
            	_, err := q.Enqueue("a", "p", RunAfter(-1))
            	hIs(t, "negative start", err, ErrBadOption)
            	hEq(t, "nothing added", hTotal(q), 0)
            	hIs(t, "negative advance", q.Advance(-1), ErrBadOption)
            	hEq(t, "clock unchanged", q.Now(), 0)
            	hEq(t, "a job in the past is ready", func() int { q.Advance(10); return hEnq(t, q, "past", RunAfter(3)) }(), 1)
            	hEq(t, "and starts", hTake(t, q).Name, "past")
            }
        ''',
        cross={
            "peek": {"tests": '''
                func TestPeekSkipsDelayedJobs(t *testing.T) {
                	q := New()
                	hEnq(t, q, "later", RunAfter(3))
                	if _, ok := q.Peek(); ok {
                		t.Error("nothing is ready")
                	}
                	hEnq(t, q, "now")
                	j, _ := q.Peek()
                	hEq(t, "peek", j.Name, "now")
                	q.Advance(3)
                	j, _ = q.Peek()
                	hEq(t, "later is first now", j.Name, "later")
                }
            '''},
            "priority": {"tests": '''
                func TestDelayedUrgentJobsWait(t *testing.T) {
                	q := New()
                	hEnq(t, q, "urgent later", Priority(9), RunAfter(2))
                	hEnq(t, q, "normal")
                	hEq(t, "normal first", hTake(t, q).Name, "normal")
                	q.Advance(2)
                	hEq(t, "urgent now", hTake(t, q).Name, "urgent later")
                }
            '''},
            "retry": {
                "reqs": ("A failed job that is retried waits before it is tried again: its `RunAfter` becomes `Now()` plus 1 after the first failed attempt, plus 2 after the second, plus 4 after the third, and so on (doubling).",),
                "code": {"jobq.go::on_retry": "j.RunAfter = q.now + (1 << uint(j.Attempts-1))"},
                "tests": '''
                    func TestRetryBackoff(t *testing.T) {
                    	q := New()
                    	hEnq(t, q, "flaky", MaxAttempts(4))
                    	hTake(t, q)
                    	q.Fail(1, "x")
                    	hEq(t, "after the first failure", func() int { j, _ := q.Get(1); return j.RunAfter }(), 1)
                    	if _, ok := q.Next(); ok {
                    		t.Error("must wait one tick")
                    	}
                    	q.Advance(1)
                    	hTake(t, q)
                    	q.Fail(1, "x")
                    	hEq(t, "after the second", func() int { j, _ := q.Get(1); return j.RunAfter }(), 3)
                    	q.Advance(1)
                    	if _, ok := q.Next(); ok {
                    		t.Error("must wait two ticks")
                    	}
                    	q.Advance(1)
                    	hTake(t, q)
                    	q.Fail(1, "x")
                    	hEq(t, "after the third", func() int { j, _ := q.Get(1); return j.RunAfter }(), 7)
                    	q.Advance(3)
                    	if _, ok := q.Next(); ok {
                    		t.Error("must wait four ticks")
                    	}
                    	q.Advance(1)
                    	hTake(t, q)
                    	q.Fail(1, "last")
                    	hEq(t, "given up", hState(t, q, 1), Failed)
                    	hEq(t, "no backoff for the final failure", func() int { j, _ := q.Get(1); return j.RunAfter }(), 7)
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="drain", title="Draining the queue", d=3,
        pitch=("Every caller writes the same loop around Next, Complete and Fail.",
               "The queue should be able to run all ready jobs through a handler."),
        reqs=("`queue.Drain(handler func(Job) error) (done, failed int, err error)` takes ready jobs with `Next` until there are none and passes each (the copy `Next` returns) to `handler`. A `nil` handler is `ErrBadOption` and nothing runs. When the handler returns `nil` the job is completed; when it returns an error the job is failed with `err.Error()` as the reason. The result counts the jobs that were completed (`done`) and the handler calls that returned an error (`failed`). `Drain` does not move any clock and stops as soon as `Next` has nothing to offer. Panics of the handler are not caught.",),
        code={
            "jobq.go::methods": '''
                // Drain runs every ready job through handler.
                func (q *Queue) Drain(handler func(Job) error) (done, failed int, err error) {
                	if handler == nil {
                		return 0, 0, fmt.Errorf("%w: handler is nil", ErrBadOption)
                	}
                	for {
                		j, ok := q.Next()
                		if !ok {
                			return done, failed, nil
                		}
                		if herr := handler(j); herr != nil {
                			failed++
                			q.Fail(j.ID, herr.Error())
                		} else {
                			done++
                			q.Complete(j.ID)
                		}
                	}
                }
            ''',
        },
        readme="## Draining the queue\n\n`queue.Drain(handler)` runs ready jobs through `handler` (nil error: complete, error: fail with its text) and returns `done` and `failed` counts.\n",
        vtests='''
            func TestDrainBasic(t *testing.T) {
            	q := New()
            	vEnq(t, q, "a")
            	vEnq(t, q, "b")
            	done, failed, err := q.Drain(func(Job) error { return nil })
            	if done != 2 || failed != 0 || err != nil {
            		t.Fatalf("%d %d %v", done, failed, err)
            	}
            }
        ''',
        tests='''
            func TestDrain(t *testing.T) {
            	q := New()
            	for _, n := range []string{"a", "bad", "c", "worse"} {
            		hEnq(t, q, n)
            	}
            	var seen []string
            	done, failed, err := q.Drain(func(j Job) error {
            		seen = append(seen, j.Name)
            		if j.Name == "bad" || j.Name == "worse" {
            			return errors.New("cannot handle " + j.Name)
            		}
            		return nil
            	})
            	hEq(t, "result", []interface{}{done, failed, err}, []interface{}{2, 2, error(nil)})
            	hEq(t, "order", seen, []string{"a", "bad", "c", "worse"})
            	j, _ := q.Get(2)
            	hEq(t, "reason", []string{j.State, j.Reason}, []string{Failed, "cannot handle bad"})
            	hEq(t, "done jobs", []string{hState(t, q, 1), hState(t, q, 3)}, []string{Done, Done})
            	hEq(t, "counts", q.Counts()["queued"]+q.Counts()["running"], 0)
            	done, failed, err = q.Drain(func(Job) error { t.Error("nothing is left"); return nil })
            	hEq(t, "empty drain", []interface{}{done, failed, err}, []interface{}{0, 0, error(nil)})
            }

            func TestDrainHandlerSeesRunningJobs(t *testing.T) {
            	q := New()
            	hEnq(t, q, "a")
            	hEnq(t, q, "b")
            	q.Drain(func(j Job) error {
            		hEq(t, "state in the handler", []interface{}{j.State, hState(t, q, j.ID)}, []interface{}{Running, Running})
            		if j.Name == "a" || j.Name == "b" {
            			hEnq(t, q, "child of "+j.Name)
            		}
            		return nil
            	})
            	hEq(t, "jobs added by the handler are run too", q.Counts()["done"], 4)
            	_, _, err := q.Drain(nil)
            	hIs(t, "nil handler", err, ErrBadOption)
            }
        ''',
        cross={
            "priority": {"tests": '''
                func TestDrainFollowsPriorities(t *testing.T) {
                	q := New()
                	hEnq(t, q, "a")
                	hEnq(t, q, "b", Priority(3))
                	var seen []string
                	q.Drain(func(j Job) error { seen = append(seen, j.Name); return nil })
                	hEq(t, "order", seen, []string{"b", "a"})
                }
            '''},
            "retry": {
                "reqs": ("A job that is retried is handled again within the same `Drain`; every failed call counts in `failed`, and `done` counts the job once when it finally succeeds.",),
                "tests": '''
                    func TestDrainRetries(t *testing.T) {
                    	q := New()
                    	hEnq(t, q, "flaky", MaxAttempts(3))
                    	hEnq(t, q, "hopeless", MaxAttempts(2))
                    	calls := map[string]int{}
                    	handler := func(j Job) error {
                    		calls[j.Name]++
                    		if j.Name == "hopeless" || calls[j.Name] < 3 {
                    			return errors.New("no")
                    		}
                    		return nil
                    	}
                    	done, failed := 0, 0
                    	for round := 0; round < 5; round++ {
                    		d, f, _ := q.Drain(handler)
                    		done, failed = done+d, failed+f
                    		hTick(q)
                    	}
                    	hEq(t, "calls", calls, map[string]int{"flaky": 3, "hopeless": 2})
                    	hEq(t, "result", []int{done, failed}, []int{1, 4})
                    	hEq(t, "states", []string{hState(t, q, 1), hState(t, q, 2)}, []string{Done, Failed})
                    }
                '''},
            "delay": {
                "reqs": ("`Drain` leaves delayed jobs alone: it stops when only jobs that are not ready yet are left.",),
                "tests": '''
                    func TestDrainStopsAtDelayedJobs(t *testing.T) {
                    	q := New()
                    	hEnq(t, q, "now")
                    	hEnq(t, q, "later", RunAfter(2))
                    	done, _, _ := q.Drain(func(Job) error { return nil })
                    	hEq(t, "first drain", done, 1)
                    	hEq(t, "later is still queued", hState(t, q, 2), Queued)
                    	q.Advance(2)
                    	done, _, _ = q.Drain(func(Job) error { return nil })
                    	hEq(t, "second drain", done, 1)
                    }
                '''},
            "limit": {"tests": '''
                func TestDrainWithALimit(t *testing.T) {
                	q := New()
                	q.SetLimit(1)
                	hEnq(t, q, "a")
                	hEnq(t, q, "b")
                	hEnq(t, q, "c")
                	done, _, _ := q.Drain(func(Job) error { return nil })
                	hEq(t, "all three run one after another", done, 3)
                }
            '''},
            "cancel": {"tests": '''
                func TestDrainSkipsCanceledJobs(t *testing.T) {
                	q := New()
                	hEnq(t, q, "a")
                	hEnq(t, q, "b")
                	q.Cancel(1)
                	var seen []string
                	q.Drain(func(j Job) error { seen = append(seen, j.Name); return nil })
                	hEq(t, "only b", seen, []string{"b"})
                }
            '''},
        },
    ))

    S.append(Slice(
        id="deps", title="Job dependencies", d=4,
        pitch=("The thumbnails job started before the upload it needs had finished.",
               "Jobs must be able to wait for other jobs."),
        reqs=("`jobq.DependsOn(ids ...int) Option` makes a job wait for other jobs (`Job.Deps` lists the ids, duplicates removed, in the given order). Every id must belong to a job that already exists, otherwise `Enqueue` fails with `ErrNotFound` and adds nothing. A job with dependencies is only ready when every one of them is `Done`.",
              "When a job fails (its state becomes `Failed`), the queued jobs that depend on it fail too, and so do the queued jobs that depend on those, and so on down the chain. Each of them becomes `Failed` with the `Reason` `dependency N failed`, where N is the first id in the job's `Deps` list that is the failed job itself or one of the jobs that failed because of it. Jobs that are not queued are not touched."),
        code={
            "jobq.go::job_fields": "Deps    []int",
            "jobq.go::types": '''
                // DependsOn makes a job wait until all the given jobs are done.
                func DependsOn(ids ...int) Option {
                	return func(j *Job) error {
                		for _, id := range ids {
                			dup := false
                			for _, d := range j.Deps {
                				if d == id {
                					dup = true
                				}
                			}
                			if !dup {
                				j.Deps = append(j.Deps, id)
                			}
                		}
                		return nil
                	}
                }
            ''',
            "jobq.go::enqueue_checks": '''
                for _, d := range j.Deps {
                	if d < 1 || d > len(q.jobs) {
                		return 0, fmt.Errorf("%w: dependency %d", ErrNotFound, d)
                	}
                }
            ''',
            "jobq.go::ready_checks": '''
                for _, d := range j.Deps {
                	if q.jobs[d-1].State != Done {
                		return false
                	}
                }
            ''',
            "jobq.go::on_fail": '''
                if j.State == Failed {
                	q.failDependents(j)
                }
            ''',
            "jobq.go::methods": '''
                // failDependents fails the queued jobs that depend on root (directly or through other
                // jobs that fail because of it).
                func (q *Queue) failDependents(root *Job) {
                	hit := map[int]bool{root.ID: true}
                	var failed []*Job
                	for changed := true; changed; {
                		changed = false
                		for _, o := range q.jobs {
                			if o.State != Queued {
                				continue
                			}
                			for _, d := range o.Deps {
                				if hit[d] {
                					o.State = Failed
                					hit[o.ID] = true
                					failed = append(failed, o)
                					changed = true
                					break
                				}
                			}
                		}
                	}
                	for _, o := range failed {
                		for _, d := range o.Deps {
                			if hit[d] {
                				o.Reason = fmt.Sprintf("dependency %d %s", d, q.jobs[d-1].State)
                				break
                			}
                		}
                	}
                }
            ''',
        },
        readme="## Job dependencies\n\n`jobq.DependsOn(ids...)`: a job is ready once all its dependencies are done; when a dependency fails for good the queued dependents fail with `dependency N failed`, down the chain.\n",
        vtests='''
            func TestDepsBasic(t *testing.T) {
            	q := New()
            	vEnq(t, q, "upload")
            	vEnq(t, q, "thumbs", DependsOn(1))
            	vTake(t, q)
            	if _, ok := q.Next(); ok {
            		t.Fatal("thumbs must wait for the upload")
            	}
            	q.Complete(1)
            	vTake(t, q)
            }
        ''',
        tests='''
            func TestDependencies(t *testing.T) {
            	q := New()
            	a := hEnq(t, q, "a")
            	b := hEnq(t, q, "b")
            	c := hEnq(t, q, "c", DependsOn(a, b))
            	d := hEnq(t, q, "d", DependsOn(c, c, a))
            	hEq(t, "deps are stored without duplicates", func() []int { j, _ := q.Get(d); return j.Deps }(), []int{c, a})
            	hEq(t, "first", hTake(t, q).Name, "a")
            	hEq(t, "second", hTake(t, q).Name, "b")
            	if _, ok := q.Next(); ok {
            		t.Error("c waits for a and b")
            	}
            	q.Complete(a)
            	if _, ok := q.Next(); ok {
            		t.Error("c still waits for b")
            	}
            	q.Complete(b)
            	hEq(t, "c", hTake(t, q).Name, "c")
            	if _, ok := q.Next(); ok {
            		t.Error("d waits for c")
            	}
            	q.Complete(c)
            	hEq(t, "d", hTake(t, q).Name, "d")
            }

            func TestFailureCascades(t *testing.T) {
            	q := New()
            	hEnq(t, q, "root")
            	hEnq(t, q, "child", DependsOn(1))
            	hEnq(t, q, "grandchild", DependsOn(2))
            	hEnq(t, q, "other", DependsOn(1, 3))
            	hEnq(t, q, "independent")
            	hEnq(t, q, "late", DependsOn(5))
            	hTake(t, q)
            	hEq(t, "fail", q.Fail(1, "boom"), error(nil))
            	reasons := []string{}
            	for id := 1; id <= 6; id++ {
            		j, _ := q.Get(id)
            		reasons = append(reasons, j.State+":"+j.Reason)
            	}
            	hEq(t, "states", reasons, []string{"failed:boom", "failed:dependency 1 failed", "failed:dependency 2 failed", "failed:dependency 1 failed", "queued:", "queued:"})
            	hEq(t, "independent runs", hTake(t, q).Name, "independent")
            	if _, ok := q.Next(); ok {
            		t.Error("late waits for independent")
            	}
            }

            func TestDependencyErrors(t *testing.T) {
            	q := New()
            	hEnq(t, q, "a")
            	for _, bad := range [][]int{{2}, {0}, {-1}, {1, 5}} {
            		_, err := q.Enqueue("x", "p", DependsOn(bad...))
            		hIs(t, "unknown dependency", err, ErrNotFound)
            	}
            	hEq(t, "nothing added", hTotal(q), 1)
            	hEq(t, "no ids is fine", hEnq(t, q, "b", DependsOn()), 2)
            	hEq(t, "a first", hTake(t, q).Name, "a")
            	hEq(t, "b next", hTake(t, q).Name, "b")
            	hEq(t, "running jobs are not touched by a failure", func() string { q.Fail(1, "x"); return hState(t, q, 2) }(), Running)
            }
        ''',
        cross={
            "cancel": {
                "reqs": ("Canceling a job fails the queued jobs that depend on it in the same way (and the ones that depend on those). The reason is `dependency N canceled` when N is the canceled job and `dependency N failed` when N is a job that failed because of the cancellation.",),
                "code": {"jobq.go::on_cancel": "q.failDependents(j)"},
                "tests": '''
                    func TestCancelCascades(t *testing.T) {
                    	q := New()
                    	hEnq(t, q, "a")
                    	hEnq(t, q, "b", DependsOn(1))
                    	hEnq(t, q, "c", DependsOn(2))
                    	hEnq(t, q, "d")
                    	hEq(t, "cancel", q.Cancel(1), error(nil))
                    	b, _ := q.Get(2)
                    	c, _ := q.Get(3)
                    	hEq(t, "b", []string{b.State, b.Reason}, []string{Failed, "dependency 1 canceled"})
                    	hEq(t, "c", []string{c.State, c.Reason}, []string{Failed, "dependency 2 failed"})
                    	hEq(t, "d is untouched", hState(t, q, 4), Queued)
                    }
                '''},
            "retry": {
                "reqs": ("A job that is put back to `Queued` for another attempt has not failed yet: its dependents stay queued until it fails for good.",),
                "tests": '''
                func TestDependentsWaitForRetries(t *testing.T) {
                	q := New()
                	hEnq(t, q, "flaky", MaxAttempts(2))
                	hEnq(t, q, "child", DependsOn(1))
                	hTake(t, q)
                	q.Fail(1, "first")
                	hEq(t, "child waits", hState(t, q, 2), Queued)
                	hTick(q)
                	hEq(t, "the parent runs again", hTake(t, q).Name, "flaky")
                	q.Fail(1, "second")
                	child, _ := q.Get(2)
                	hEq(t, "child fails with the dependency", []string{child.State, child.Reason}, []string{Failed, "dependency 1 failed"})
                }
            '''},
            "delay": {"tests": '''
                func TestDependenciesAndDelays(t *testing.T) {
                	q := New()
                	hEnq(t, q, "a")
                	hEnq(t, q, "b", DependsOn(1), RunAfter(5))
                	hTake(t, q)
                	q.Complete(1)
                	if _, ok := q.Next(); ok {
                		t.Error("b is delayed")
                	}
                	q.Advance(5)
                	hEq(t, "b", hTake(t, q).Name, "b")
                }
            '''},
            "priority": {"tests": '''
                func TestDependenciesBeatPriorities(t *testing.T) {
                	q := New()
                	hEnq(t, q, "a")
                	hEnq(t, q, "urgent child", DependsOn(1), Priority(9))
                	hEnq(t, q, "plain")
                	hEq(t, "a", hTake(t, q).Name, "a")
                	hEq(t, "plain runs while the urgent child waits", hTake(t, q).Name, "plain")
                	q.Complete(1)
                	hEq(t, "child", hTake(t, q).Name, "urgent child")
                }
            '''},
            "drain": {
                "reqs": ("`Drain` runs dependencies before their dependents; jobs that fail because of a failed dependency never reach the handler and are not counted in `failed`.",),
                "tests": '''
                    func TestDrainWithDependencies(t *testing.T) {
                    	q := New()
                    	hEnq(t, q, "root")
                    	hEnq(t, q, "child", DependsOn(1))
                    	hEnq(t, q, "grandchild", DependsOn(2))
                    	hEnq(t, q, "alone")
                    	var seen []string
                    	done, failed, _ := q.Drain(func(j Job) error {
                    		seen = append(seen, j.Name)
                    		if j.Name == "root" {
                    			return errors.New("no")
                    		}
                    		return nil
                    	})
                    	hEq(t, "handled", seen, []string{"root", "alone"})
                    	hEq(t, "counts", []int{done, failed}, []int{1, 1})
                    	hEq(t, "states", []string{hState(t, q, 2), hState(t, q, 3)}, []string{Failed, Failed})
                    }
                '''},
        },
    ))
    order = ["peek", "cancel", "unique", "priority", "limit", "retry", "delay", "drain", "deps"]
    S.sort(key=lambda x: order.index(x.id))
    return S


APP = App(
    name="jobq", lang="go", title="the job queue library", role="a batch worker developer", key="JOBQ",
    base={
        "README.md": README + "\n@@blocks features\n",
        "go.mod": langs.go_mod("jobq"),
        "jobq.go": JOBQ,
        ".gitignore": "*.test\n",
    },
    visible={"jobq_test.go": VISIBLE},
    hidden={"features_test.go": HIDDEN},
)

register_app("feature-go-jobq", APP, make_slices, n=18, summary="job queue: peek, cancel, unique keys, priorities, limits, retries, delays, draining, dependencies")
