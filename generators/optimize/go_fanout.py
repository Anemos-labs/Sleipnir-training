"""Go concurrency optimisation: sequential requests, unbounded fan-out, repeated ids, no cancellation on error.
A fake backend counts requests and requests in flight; a rendezvous barrier (with a long safety timeout) makes the overlap deterministic: no tight timing."""
from __future__ import annotations

import json
from string import Template

from fx import Task, family, langs

from ._kit import prove_opt

GO_ALL = "go test -count=1 -timeout 120s ./..."
GO_CORRECT = "go test -count=1 -timeout 120s -run 'Test(Basic|Correct)' ./..."
GO_PERF = "go test -count=1 -timeout 120s -run TestPerf ./..."


def tabify(text):
    out = []
    for ln in text.split("\n"):
        n = len(ln) - len(ln.lstrip(" "))
        out.append("\t" * (n // 4) + ln.lstrip(" "))
    return "\n".join(out)


TYPES = '''package $pkg

import "context"

// Item is a record held by the remote service.
type Item struct {
    ID    string
    Value int
}

// Backend is the remote service. Get is a network call: it can take a while, and it honours ctx.
type Backend interface {
    Get(ctx context.Context, id string) (Item, error)
}
'''

SEQUENTIAL = '''package $pkg

import "context"

// $Fn loads the items for ids.
func $Fn(ctx context.Context, b Backend, ids []string) ([]Item, error) {
    out := make([]Item, 0, len(ids))
    for _, id := range ids {
        item, err := b.Get(ctx, id)
        if err != nil {
            return nil, err
        }
        out = append(out, item)
    }
    return out, nil
}
'''

UNBOUNDED = '''package $pkg

import (
    "context"
    "sync"
)

// $Fn loads the items for ids.
func $Fn(ctx context.Context, b Backend, ids []string) ([]Item, error) {
    out := make([]Item, len(ids))
    errs := make([]error, len(ids))
    var wg sync.WaitGroup
    for i, id := range ids {
        wg.Add(1)
        go func(i int, id string) {
            defer wg.Done()
            out[i], errs[i] = b.Get(ctx, id)
        }(i, id)
    }
    wg.Wait()
    for _, err := range errs {
        if err != nil {
            return nil, err
        }
    }
    return out, nil
}
'''

POOL = '''package $pkg

import (
    "context"
    "sync"
)

// $Fn loads the items for ids.
func $Fn(ctx context.Context, b Backend, ids []string) ([]Item, error) {
    out := make([]Item, len(ids))
    errs := make([]error, len(ids))
    jobs := make(chan int)
    var wg sync.WaitGroup
    for w := 0; w < 4 && w < len(ids); w++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for i := range jobs {
                out[i], errs[i] = b.Get(ctx, ids[i])
            }
        }()
    }
    for i := range ids {
        jobs <- i
    }
    close(jobs)
    wg.Wait()
    for _, err := range errs {
        if err != nil {
            return nil, err
        }
    }
    return out, nil
}
'''

DEDUPE = '''package $pkg

import (
    "context"
    "sync"
)

// $Fn loads the items for ids.
func $Fn(ctx context.Context, b Backend, ids []string) ([]Item, error) {
    index := map[string]int{}
    var distinct []string
    for _, id := range ids {
        if _, ok := index[id]; !ok {
            index[id] = len(distinct)
            distinct = append(distinct, id)
        }
    }
    items := make([]Item, len(distinct))
    errs := make([]error, len(distinct))
    var wg sync.WaitGroup
    for i, id := range distinct {
        wg.Add(1)
        go func(i int, id string) {
            defer wg.Done()
            items[i], errs[i] = b.Get(ctx, id)
        }(i, id)
    }
    wg.Wait()
    out := make([]Item, len(ids))
    for k, id := range ids {
        j := index[id]
        if errs[j] != nil {
            return nil, errs[j]
        }
        out[k] = items[j]
    }
    return out, nil
}
'''

CANCEL = '''package $pkg

import (
    "context"
    "sync"
)

// $Fn loads the items for ids.
func $Fn(ctx context.Context, b Backend, ids []string) ([]Item, error) {
    ctx, cancel := context.WithCancel(ctx)
    defer cancel()
    out := make([]Item, len(ids))
    jobs := make(chan int)
    var once sync.Once
    var first error
    var wg sync.WaitGroup
    for w := 0; w < 4 && w < len(ids); w++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for i := range jobs {
                if ctx.Err() != nil {
                    continue
                }
                item, err := b.Get(ctx, ids[i])
                if err != nil {
                    once.Do(func() {
                        first = err
                        cancel()
                    })
                    continue
                }
                out[i] = item
            }
        }()
    }
    for i := range ids {
        jobs <- i
    }
    close(jobs)
    wg.Wait()
    if first != nil {
        return nil, first
    }
    return out, nil
}
'''

FAKE = '''package ${pkg}_test

import (
    "context"
    "fmt"
    "sync"
    "time"

    "example.com/${mod}/${pkg}"
)

// missingErr is what the fake returns for unknown or failing ids.
type missingErr struct{ id string }

func (e *missingErr) Error() string { return "missing " + e.id }

// slowBackend records how many requests were made and how many overlapped. The first calls wait for a rendezvous: until `barrier`
// requests are in flight at the same time (then everybody is released) or, as a safety net, for three seconds.
type slowBackend struct {
    items   map[string]${pkg}.Item
    failing map[string]bool
    barrier int

    mu          sync.Mutex
    started     int
    inflight    int
    maxInflight int
    tripped     chan struct{}
    once        sync.Once
    open        bool
}

func newSlow(items map[string]${pkg}.Item, barrier int) *slowBackend {
    return &slowBackend{items: items, failing: map[string]bool{}, barrier: barrier, tripped: make(chan struct{})}
}

func (b *slowBackend) Get(ctx context.Context, id string) (${pkg}.Item, error) {
    b.mu.Lock()
    b.started++
    if b.failing[id] {
        b.mu.Unlock()
        return ${pkg}.Item{}, &missingErr{id}
    }
    b.inflight++
    if b.inflight > b.maxInflight {
        b.maxInflight = b.inflight
    }
    if b.barrier > 0 && b.inflight >= b.barrier {
        b.once.Do(func() { close(b.tripped) })
    }
    waiting := b.barrier > 0 && !b.open
    b.mu.Unlock()
    defer func() {
        b.mu.Lock()
        b.inflight--
        b.mu.Unlock()
    }()
    if waiting {
        select {
        case <-b.tripped:
        case <-ctx.Done():
            return ${pkg}.Item{}, ctx.Err()
        case <-time.After(3 * time.Second):
            b.mu.Lock()
            b.open = true
            b.mu.Unlock()
        }
    }
    if err := ctx.Err(); err != nil {
        return ${pkg}.Item{}, err
    }
    item, ok := b.items[id]
    if !ok {
        return ${pkg}.Item{}, &missingErr{id}
    }
    return item, nil
}

func makeItems(n int) map[string]${pkg}.Item {
    items := map[string]${pkg}.Item{}
    for i := 0; i < n; i++ {
        id := fmt.Sprintf("id%d", i)
        items[id] = ${pkg}.Item{ID: id, Value: i * 7}
    }
    return items
}
'''

CORRECT = '''package ${pkg}_test

import (
    "context"
    "errors"
    "fmt"
    "math/rand"
    "testing"

    "example.com/${mod}/${pkg}"
)

func TestCorrectResultsAndErrors(t *testing.T) {
    rng := rand.New(rand.NewSource(${seed}))
    for round := 0; round < 60; round++ {
        n := rng.Intn(14)
        items := makeItems(n + 3)
        ids := make([]string, n)
        wantErr := ""
        for i := range ids {
            if rng.Intn(${ghost}) == 0 && (wantErr == "" || ${multi}) {
                ids[i] = fmt.Sprintf("ghost%d", i)
                if wantErr == "" {
                    wantErr = ids[i]
                }
            } else {
                ids[i] = fmt.Sprintf("id%d", rng.Intn(${pool}))
            }
        }
        got, err := ${pkg}.${Fn}(context.Background(), newSlow(items, 0), ids)
        if wantErr != "" {
            var me *missingErr
            if err == nil || !errors.As(err, &me) || me.id != wantErr {
                t.Fatalf("ids %v: error = %v, want missing %s", ids, err, wantErr)
            }
            if got != nil {
                t.Fatalf("ids %v: a failed call must return a nil slice, got %v", ids, got)
            }
            continue
        }
        if err != nil {
            t.Fatalf("ids %v: unexpected error %v", ids, err)
        }
        if len(got) != len(ids) {
            t.Fatalf("ids %v: got %d items", ids, len(got))
        }
        for i, id := range ids {
            if got[i] != items[id] {
                t.Fatalf("ids %v: item %d = %v, want %v", ids, i, got[i], items[id])
            }
        }
    }
}

func TestCorrectEmpty(t *testing.T) {
    got, err := ${pkg}.${Fn}(context.Background(), newSlow(makeItems(2), 0), nil)
    if err != nil || len(got) != 0 {
        t.Fatalf("empty input: %v, %v", got, err)
    }
}
'''

PERF_HEAD = '''package ${pkg}_test

import (
    "context"
    "errors"
    "fmt"
    "testing"

    "example.com/${mod}/${pkg}"
)

var _ = errors.As
var _ = fmt.Sprintf

func sequence(n int) []string {
    ids := make([]string, n)
    for i := range ids {
        ids[i] = fmt.Sprintf("id%d", i)
    }
    return ids
}

func checkItems(t *testing.T, items map[string]${pkg}.Item, ids []string, got []${pkg}.Item, err error) {
    t.Helper()
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }
    if len(got) != len(ids) {
        t.Fatalf("got %d items for %d ids", len(got), len(ids))
    }
    for i, id := range ids {
        if got[i] != items[id] {
            t.Fatalf("item %d = %v, want %v", i, got[i], items[id])
        }
    }
}

'''

PERF = {
    "parallel": '''func TestPerfRequestsOverlap(t *testing.T) {
    items := makeItems(30)
    ids := sequence(24)
    b := newSlow(items, 4)
    got, err := ${pkg}.${Fn}(context.Background(), b, ids)
    checkItems(t, items, ids, got, err)
    if b.maxInflight < 4 {
        t.Fatalf("PERF: at most %d request(s) were in flight at once for %d independent ids: the requests wait for each other", b.maxInflight, len(ids))
    }
}
''',
    "bounded": '''func TestPerfBoundedConcurrency(t *testing.T) {
    items := makeItems(50)
    ids := sequence(40)
    b := newSlow(items, 5)
    got, err := ${pkg}.${Fn}(context.Background(), b, ids)
    checkItems(t, items, ids, got, err)
    if b.maxInflight > 4 {
        t.Fatalf("PERF: %d requests were in flight at once (the backend allows 4): the fan-out is not bounded", b.maxInflight)
    }
    if b.maxInflight < 3 {
        t.Fatalf("PERF: only %d request(s) overlapped: use the allowed concurrency", b.maxInflight)
    }
}
''',
    "dedupe": '''func TestPerfDistinctIdsOnce(t *testing.T) {
    items := makeItems(14)
    ids := make([]string, 0, 60)
    for i := 0; i < 60; i++ {
        ids = append(ids, fmt.Sprintf("id%d", (i*7)%12))
    }
    b := newSlow(items, 3)
    got, err := ${pkg}.${Fn}(context.Background(), b, ids)
    checkItems(t, items, ids, got, err)
    if b.started > 12 {
        t.Fatalf("PERF: %d requests for 12 distinct ids: every id should be requested once", b.started)
    }
    if b.maxInflight < 3 {
        t.Fatalf("PERF: at most %d request(s) in flight at once: requests for different ids wait for each other", b.maxInflight)
    }
}
''',
    "cancel": '''func TestPerfBoundedOnSuccess(t *testing.T) {
    items := makeItems(40)
    ids := sequence(30)
    b := newSlow(items, 3)
    got, err := ${pkg}.${Fn}(context.Background(), b, ids)
    checkItems(t, items, ids, got, err)
    if b.maxInflight > 4 || b.maxInflight < 3 {
        t.Fatalf("PERF: %d requests in flight at once (allowed: 3 or 4 with this much work)", b.maxInflight)
    }
}

func TestPerfStopsAfterTheFirstError(t *testing.T) {
    items := makeItems(60)
    ids := sequence(40)
    b := newSlow(items, 100)
    b.failing["id3"] = true
    got, err := ${pkg}.${Fn}(context.Background(), b, ids)
    var me *missingErr
    if err == nil || !errors.As(err, &me) || me.id != "id3" {
        t.Fatalf("error = %v, want the error of id3 (not a context error)", err)
    }
    if got != nil {
        t.Fatalf("a failed call must return a nil slice")
    }
    if b.maxInflight > 4 {
        t.Fatalf("PERF: %d requests were in flight at once (the backend allows 4)", b.maxInflight)
    }
    if b.started > 8 {
        t.Fatalf("PERF: %d requests were started although the fourth one failed at once: new requests must stop after the first error", b.started)
    }
}
''',
}

BASIC = '''package ${pkg}_test

import (
    "context"
    "errors"
    "testing"

    "example.com/${mod}/${pkg}"
)

type plainBackend map[string]${pkg}.Item

func (p plainBackend) Get(ctx context.Context, id string) (${pkg}.Item, error) {
    if it, ok := p[id]; ok {
        return it, nil
    }
    return ${pkg}.Item{}, errors.New("no such item: " + id)
}

func TestBasicLoadsInOrder(t *testing.T) {
    b := plainBackend{"a": {ID: "a", Value: 1}, "b": {ID: "b", Value: 2}, "c": {ID: "c", Value: 3}}
    got, err := ${pkg}.${Fn}(context.Background(), b, []string{"c", "a", "b", "a"})
    if err != nil {
        t.Fatal(err)
    }
    want := []string{"c", "a", "b", "a"}
    if len(got) != len(want) {
        t.Fatalf("got %v", got)
    }
    for i, id := range want {
        if got[i].ID != id {
            t.Fatalf("item %d = %v, want %s", i, got[i], id)
        }
    }
}

func TestBasicReportsAnUnknownId(t *testing.T) {
    b := plainBackend{"a": {ID: "a", Value: 1}}
    got, err := ${pkg}.${Fn}(context.Background(), b, []string{"a", "zzz"})
    if err == nil || got != nil {
        t.Fatalf("got %v, %v; want a nil slice and an error", got, err)
    }
}
'''

SHAPES = {
    "parallel": dict(
        d=3, naive=SEQUENTIAL, fast=UNBOUNDED, test=PERF["parallel"], ghost=5, multi="true", pool="n+3",
        spec="`{Fn}(ctx, b, ids)` loads every id with `b.Get(ctx, id)` and returns the items in the order of `ids`. The requests are independent and the backend has plenty of capacity, so they must "
             "not wait for each other: with enough ids, at least four requests have to be in flight at the same time. If requests fail, the error of the first failing id (in the order of `ids`) "
             "is returned together with a nil slice.",
        hint="the requests are issued one after the other although they are independent"),
    "bounded": dict(
        d=4, naive=UNBOUNDED, fast=POOL, test=PERF["bounded"], ghost=5, multi="true", pool="n+3",
        spec="`{Fn}(ctx, b, ids)` loads every id with `b.Get(ctx, id)` and returns the items in the order of `ids`. The backend throttles clients that have more than 4 requests in flight: "
             "use at most 4 concurrent requests (3 or more when there is enough work), never more. If requests fail, the error of the first failing id (in the order of `ids`) is returned "
             "together with a nil slice.",
        hint="one goroutine per id, so hundreds of requests are in flight at once and the backend throttles us"),
    "dedupe": dict(
        d=4, naive=SEQUENTIAL, fast=DEDUPE, test=PERF["dedupe"], ghost=5, multi="true", pool="n+3",
        spec="`{Fn}(ctx, b, ids)` loads the ids with `b.Get(ctx, id)` and returns the items in the order of `ids` (repeats included). `ids` contains many repeats: every distinct id must be "
             "requested exactly once (a request is expensive), and requests for different ids must not wait for each other (at least three in flight at the same time when there are enough "
             "distinct ids). If requests fail, the error of the first failing id (in the order of `ids`) is returned together with a nil slice.",
        hint="every occurrence of an id is requested again, and one after the other"),
    "cancel": dict(
        d=5, naive=POOL, fast=CANCEL, test=PERF["cancel"], ghost=9, multi="false", pool="n+3",
        spec="`{Fn}(ctx, b, ids)` loads every id with `b.Get(ctx, id)` and returns the items in the order of `ids`. Use at most 4 concurrent requests (3 or more when there is enough work). "
             "When a request fails: no new request may be started, the requests in flight must be cancelled through `ctx` (the backend honours it), and the call returns the error of the "
             "request that failed (not a `context.Canceled` caused by the cancellation) together with a nil slice.",
        hint="after a failed request the remaining ids are still requested, so a bad id wastes the whole batch"),
}

VOCAB = [
    ("profiles", "LoadProfiles", "Loads user profiles for a page of a directory listing."),
    ("sensorhub", "FetchReadings", "Fetches the latest reading of each sensor in a plant."),
    ("authordir", "ResolveAuthors", "Resolves author records for a list of articles."),
    ("mirrorsync", "PullDocuments", "Pulls documents from a store for a nightly mirror."),
    ("geoenrich", "LookupPlaces", "Looks up places for rows of an import in a geocoding service."),
]

PROMPTS = [
    "`{fn}` in `{pkg}/load.go` makes the {noun} job crawl against the real service: {hint}. {doc} Fix it so it follows the rules in the README (results and errors stay exactly as "
    "described). The tests count requests and measure how many are in flight at once with a fake backend, so there is no timing to tune.",
    "perf: `{fn}` ({pkg}/load.go). {doc} Problem: {hint}. Rewrite the concurrency as described in the README. The check uses a fake service that records the requests and how many overlap, "
    "not a stopwatch.",
    "Ops says the {noun} import spends all its time waiting on the backend. Looking at `{fn}` in `{pkg}/load.go`: {hint}. {doc} Please make it behave as the README says, same results and "
    "same errors. CI uses an instrumented fake backend (request counts and maximum concurrency).",
]


@family("optimize-go-fanout", category="optimize", lang="go", kind="feature", n=8,
        summary="sequential requests, unbounded fan-out, repeated ids and missing cancellation (go): a fake backend with a rendezvous barrier counts requests and requests in flight")
def gen(rng, n):
    order = list(SHAPES) * 3
    rng.shuffle(order)
    vocab = list(VOCAB)
    rng.shuffle(vocab)
    for i in range(n):
        shape = order[i]
        sp = SHAPES[shape]
        pkg, fn, doc = vocab[i % len(vocab)]
        mod = pkg + "mod"
        seed = 500 + i
        sub = dict(pkg=pkg, mod=mod, Fn=fn, seed=seed, ghost=sp["ghost"], multi=sp["multi"], pool=sp["pool"].replace("n", "n"))
        readme = f"# {pkg}\n\n## `{fn}`\n\n{doc}\n\n{sp['spec'].format(Fn=fn)}\n"
        types_src = tabify(Template(TYPES).substitute(sub))
        files = {"go.mod": langs.go_mod(mod), f"{pkg}/types.go": types_src, f"{pkg}/load.go": tabify(Template(sp["naive"]).substitute(sub)), "README.md": readme,
                 f"{pkg}/basic_test.go": tabify(Template(BASIC).substitute(sub))}
        sol = {f"{pkg}/load.go": tabify(Template(sp["fast"]).substitute(sub))}
        pool_expr = sp["pool"]
        correct = Template(CORRECT).substitute({**sub, "pool": pool_expr})
        perf = Template(PERF_HEAD).substitute(sub) + Template(sp["test"]).substitute(sub)
        hidden = {f"{pkg}/fake_test.go": tabify(Template(FAKE).substitute(sub)), f"{pkg}/correct_test.go": tabify(correct), f"{pkg}/perf_test.go": tabify(perf)}
        prove_opt(f"{shape}/{fn}", files, hidden, sol, GO_CORRECT, GO_PERF, GO_ALL, timeout=240)
        prompt = rng.choice(PROMPTS).format(fn=fn, pkg=pkg, doc=doc, hint=sp["hint"], noun=pkg)
        yield Task(slug=f"{i + 1:02d}-{shape}-{fn.lower()}", prompt=prompt, difficulty=sp["d"], start=files, hidden=hidden, solution=sol, verify=GO_ALL, timeout_s=240,
                   tags=["go", "concurrency", "goroutines", "context", "fake-backend"], notes={"shape": shape})
