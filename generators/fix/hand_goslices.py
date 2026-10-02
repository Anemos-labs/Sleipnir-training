"""Go slices, aliasing and closures: a playlist queue and a sliding window toolkit."""
from fx import dd, family, langs
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A: playlist queue.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # playlist

    The play queue of a music player (Go; `go.mod` says `go 1.21`, so every loop iteration shares its loop variables).

    * `New(tracks...)`, `Add(t)`, `Len()`, `Titles()` (the titles in queue order).
    * `RemoveWhere(pred)` removes every track for which `pred` is true, keeps the order of the others and returns how many it removed.
    * `Insert(i, t)` puts `t` at position `i` (0 to `Len()`); the track that was there and everything after it move up by one. Nothing is lost
      or duplicated.
    * `Snapshot()` returns a copy of the tracks: it never changes when the queue changes, and changing it never changes the queue.
    * `Page(n, size)` returns page `n` (0-based) of `size` tracks as an **independent slice**: appending to it or editing it never affects the queue
      (`nil` past the end; the last page may be shorter).
    * `Top(n)` returns the `n` most played tracks, most played first, ties in queue order; **the queue itself keeps its order**.
    * `Announcers()` returns one function per track, in queue order; calling a function later gives `"Now playing: <title of its track>"`.
''')

A_PLAYLIST = dd('''
    package playlist

    import "sort"

    // Track is one entry of the queue.
    type Track struct {
    	Title string
    	Plays int
    }

    // Queue is the play queue.
    type Queue struct {
    	items []Track
    }

    // New makes a queue with the given tracks.
    func New(tracks ...Track) *Queue {
    	q := &Queue{}
    	q.items = append(q.items, tracks...)
    	return q
    }

    func (q *Queue) Len() int { return len(q.items) }

    func (q *Queue) Add(t Track) { q.items = append(q.items, t) }

    func (q *Queue) Titles() []string {
    	out := make([]string, 0, len(q.items))
    	for _, t := range q.items {
    		out = append(out, t.Title)
    	}
    	return out
    }

    func (q *Queue) RemoveWhere(pred func(Track) bool) int {
    	kept := q.items[:0]
    	for _, t := range q.items {
    		if !pred(t) {
    			kept = append(kept, t)
    		}
    	}
    	removed := len(q.items) - len(kept)
    	for i := len(kept); i < len(q.items); i++ {
    		q.items[i] = Track{}
    	}
    	q.items = kept
    	return removed
    }

    func (q *Queue) Insert(i int, t Track) {
    	q.items = append(q.items, Track{})
    	copy(q.items[i+1:], q.items[i:])
    	q.items[i] = t
    }

    func (q *Queue) Snapshot() []Track {
    	out := make([]Track, len(q.items))
    	copy(out, q.items)
    	return out
    }

    func (q *Queue) Page(n, size int) []Track {
    	start := n * size
    	if start >= len(q.items) {
    		return nil
    	}
    	end := start + size
    	if end > len(q.items) {
    		end = len(q.items)
    	}
    	out := make([]Track, end-start)
    	copy(out, q.items[start:end])
    	return out
    }

    func (q *Queue) Top(n int) []Track {
    	tmp := q.Snapshot()
    	sort.SliceStable(tmp, func(i, j int) bool { return tmp[i].Plays > tmp[j].Plays })
    	if n > len(tmp) {
    		n = len(tmp)
    	}
    	return tmp[:n]
    }

    func (q *Queue) Announcers() []func() string {
    	var out []func() string
    	for _, t := range q.items {
    		t := t
    		out = append(out, func() string { return "Now playing: " + t.Title })
    	}
    	return out
    }
''')

A_VISIBLE = {
    "playlist_test.go": dd('''
        package playlist

        import (
        	"reflect"
        	"testing"
        )

        func TestBasics(t *testing.T) {
        	q := New(Track{"a", 1}, Track{"b", 5}, Track{"c", 3})
        	q.Add(Track{"d", 0})
        	if !reflect.DeepEqual(q.Titles(), []string{"a", "b", "c", "d"}) {
        		t.Fatalf("titles %v", q.Titles())
        	}
        	q.Insert(0, Track{"z", 9})
        	if q.Titles()[0] != "z" || q.Len() != 5 {
        		t.Fatalf("titles %v", q.Titles())
        	}
        }
    '''),
}

A_HIDDEN = {
    "playlist_hidden_test.go": dd('''
        package playlist

        import (
        	"reflect"
        	"testing"
        )

        func queue(titles ...string) *Queue {
        	q := New()
        	for i, s := range titles {
        		q.Add(Track{Title: s, Plays: i})
        	}
        	return q
        }

        func TestRemoveWhere(t *testing.T) {
        	cases := []struct {
        		in   []string
        		drop map[string]bool
        		want []string
        	}{
        		{[]string{"a", "b", "c", "d", "e"}, map[string]bool{"b": true, "d": true}, []string{"a", "c", "e"}},
        		{[]string{"a", "b", "c"}, map[string]bool{"a": true, "b": true, "c": true}, []string{}},
        		{[]string{"a", "b", "c"}, map[string]bool{}, []string{"a", "b", "c"}},
        		{[]string{"x", "x", "x", "y"}, map[string]bool{"x": true}, []string{"y"}},
        		{[]string{"a", "b", "c", "d"}, map[string]bool{"d": true}, []string{"a", "b", "c"}},
        		{[]string{"a", "b", "b", "a"}, map[string]bool{"b": true}, []string{"a", "a"}},
        	}
        	for _, c := range cases {
        		q := queue(c.in...)
        		removed := q.RemoveWhere(func(tr Track) bool { return c.drop[tr.Title] })
        		if got := q.Titles(); !reflect.DeepEqual(got, c.want) {
        			t.Errorf("remove %v from %v: got %v want %v", c.drop, c.in, got, c.want)
        		}
        		if removed != len(c.in)-len(c.want) {
        			t.Errorf("removed %d, want %d", removed, len(c.in)-len(c.want))
        		}
        	}
        }

        func TestRemoveWhereKeepsSnapshotsIntact(t *testing.T) {
        	q := queue("a", "b", "c")
        	snap := q.Snapshot()
        	q.RemoveWhere(func(tr Track) bool { return tr.Title == "a" })
        	if snap[0].Title != "a" || snap[1].Title != "b" || snap[2].Title != "c" {
        		t.Fatalf("snapshot changed: %v", snap)
        	}
        }

        func TestInsertLosesAndDuplicatesNothing(t *testing.T) {
        	for i := 0; i <= 4; i++ {
        		q := queue("a", "b", "c", "d")
        		q.Insert(i, Track{Title: "NEW"})
        		want := append(append(append([]string{}, []string{"a", "b", "c", "d"}[:i]...), "NEW"), []string{"a", "b", "c", "d"}[i:]...)
        		if got := q.Titles(); !reflect.DeepEqual(got, want) {
        			t.Errorf("Insert(%d): got %v want %v", i, got, want)
        		}
        	}
        	q := New()
        	q.Insert(0, Track{Title: "only"})
        	if !reflect.DeepEqual(q.Titles(), []string{"only"}) {
        		t.Errorf("insert into empty: %v", q.Titles())
        	}
        }

        func TestInsertWithSpareCapacity(t *testing.T) {
        	q := New()
        	for _, s := range []string{"a", "b", "c", "d", "e"} {
        		q.Add(Track{Title: s})
        	}
        	q.RemoveWhere(func(tr Track) bool { return tr.Title == "e" })
        	q.Insert(1, Track{Title: "X"})
        	if got := q.Titles(); !reflect.DeepEqual(got, []string{"a", "X", "b", "c", "d"}) {
        		t.Errorf("got %v", got)
        	}
        }

        func TestSnapshotIsACopy(t *testing.T) {
        	q := queue("a", "b")
        	snap := q.Snapshot()
        	snap[0].Title = "changed"
        	q.Add(Track{Title: "c"})
        	q.Insert(0, Track{Title: "z"})
        	if !reflect.DeepEqual(q.Titles(), []string{"z", "a", "b", "c"}) {
        		t.Errorf("queue %v", q.Titles())
        	}
        	if len(snap) != 2 || snap[1].Title != "b" {
        		t.Errorf("snapshot %v", snap)
        	}
        }

        func TestPagesAreIndependent(t *testing.T) {
        	q := queue("a", "b", "c", "d", "e")
        	p := q.Page(0, 2)
        	p = append(p, Track{Title: "intruder"})
        	p[0].Title = "edited"
        	if !reflect.DeepEqual(q.Titles(), []string{"a", "b", "c", "d", "e"}) {
        		t.Fatalf("the queue was changed through a page: %v", q.Titles())
        	}
        	if len(p) != 3 {
        		t.Fatalf("page length %d", len(p))
        	}
        	if got := q.Page(2, 2); len(got) != 1 || got[0].Title != "e" {
        		t.Errorf("last page %v", got)
        	}
        	if got := q.Page(3, 2); got != nil {
        		t.Errorf("past the end: %v", got)
        	}
        	if got := q.Page(1, 2); len(got) != 2 || got[0].Title != "c" || got[1].Title != "d" {
        		t.Errorf("middle page %v", got)
        	}
        }

        func TestTopDoesNotReorderTheQueue(t *testing.T) {
        	q := New(Track{"a", 1}, Track{"b", 5}, Track{"c", 3}, Track{"d", 5}, Track{"e", 0})
        	top := q.Top(3)
        	titles := []string{top[0].Title, top[1].Title, top[2].Title}
        	if !reflect.DeepEqual(titles, []string{"b", "d", "c"}) {
        		t.Errorf("top %v", titles)
        	}
        	if !reflect.DeepEqual(q.Titles(), []string{"a", "b", "c", "d", "e"}) {
        		t.Errorf("queue reordered: %v", q.Titles())
        	}
        	if got := q.Top(99); len(got) != 5 {
        		t.Errorf("Top(99) has %d tracks", len(got))
        	}
        	if got := q.Top(0); len(got) != 0 {
        		t.Errorf("Top(0) has %d tracks", len(got))
        	}
        }

        func TestAnnouncersRememberTheirOwnTrack(t *testing.T) {
        	q := queue("alpha", "beta", "gamma")
        	fns := q.Announcers()
        	if len(fns) != 3 {
        		t.Fatalf("%d announcers", len(fns))
        	}
        	want := []string{"Now playing: alpha", "Now playing: beta", "Now playing: gamma"}
        	for i, f := range fns {
        		if got := f(); got != want[i] {
        			t.Errorf("announcer %d says %q, want %q", i, got, want[i])
        		}
        	}
        }
    '''),
}


def _a_prompts():
    p = {}
    p["remove"] = lambda c: (
        "Clearing played tracks from the queue crashes the player intermittently, and when it does not crash it leaves some "
        "of the tracks it should have removed. The crash we got:\n\n```\n"
        + "\n".join(ln for ln in c.bad_run("package playlist\n\nimport \"testing\"\n\nfunc TestProbe(t *testing.T) {\n\tq := New(Track{\"a\", 0}, Track{\"b\", 0}, Track{\"c\", 0}, Track{\"d\", 0})\n\tq.RemoveWhere(func(tr Track) bool { return tr.Title == \"c\" || tr.Title == \"d\" })\n}\n",
                                         cmd="go test -count=1 -run TestProbe ./... 2>&1", name="probe_test.go").splitlines() if ln.startswith(("panic: ", "--- FAIL")))
        + "\n```\n\nRemoving must keep the order of what stays."
    )
    p["insert"] = (
        "Inserting a track into the middle of the queue duplicates the new track and loses the one that used to be at that position (insert \"X\" "
        "at 1 in a, b, c, d and we get a, X, X, c, d). Appending at the end works."
    )
    p["page"] = (
        "The queue view pages through the queue with `Page`, and when the UI appends an extra row to a page the *next page's first track* is "
        "replaced by it. Editing a row of a page also edits the queue. Pages must be independent."
    )
    p["top"] = (
        "Showing the \"most played\" panel reorders the actual play queue: after calling `Top(3)` the next track to play is no longer the one the "
        "user queued. `Top` must not touch the queue."
    )
    p["loopvar"] = (
        "The \"now playing\" announcer functions all say the title of the *last* track. We create one announcer per track in the queue and "
        "call them later when each track starts. (The module is on Go 1.21 semantics, where loop variables are shared.)"
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "go.mod": langs.go_mod("playlist"), "playlist.go": A_PLAYLIST}
    f = "playlist.go"
    remove = ("\tkept := q.items[:0]\n\tfor _, t := range q.items {\n\t\tif !pred(t) {\n\t\t\tkept = append(kept, t)\n\t\t}\n\t}\n\tremoved := len(q.items) - len(kept)\n\tfor i := len(kept); i < len(q.items); i++ {\n\t\tq.items[i] = Track{}\n\t}\n\tq.items = kept\n\treturn removed\n",
              "\tremoved := 0\n\tfor i, t := range q.items {\n\t\tif pred(t) {\n\t\t\tq.items = append(q.items[:i], q.items[i+1:]...)\n\t\t\tremoved++\n\t\t}\n\t}\n\treturn removed\n")
    bugs = [
        Bug("top-sorts-the-queue-itself", 2, {f: [("\ttmp := q.Snapshot()\n\tsort.SliceStable(tmp,", "\ttmp := q.items\n\tsort.SliceStable(tmp,")]}, P["top"]),
        Bug("remove-while-ranging", 3, {f: [remove]}, P["remove"]),
        Bug("page-is-a-view", 3, {f: [("\tout := make([]Track, end-start)\n\tcopy(out, q.items[start:end])\n\treturn out\n", "\treturn q.items[start:end]\n")]}, P["page"]),
        Bug("announcers-share-the-loop-variable", 3, {f: [("\t\tt := t\n\t\tout = append(out, func() string", "\t\tout = append(out, func() string")]}, P["loopvar"]),
        Bug("insert-through-an-aliased-tail", 4, {f: [("\tq.items = append(q.items, Track{})\n\tcopy(q.items[i+1:], q.items[i:])\n\tq.items[i] = t\n",
                                                      "\ttail := q.items[i:]\n\tq.items = append(q.items[:i], t)\n\tq.items = append(q.items, tail...)\n")]}, P["insert"]),
    ]
    return Base("playlist", "go", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B: sliding window helpers.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # window

    Small slice helpers for a metrics agent (Go).

    * `New(size)` makes a `Window` that keeps the last `size` values pushed; `Push(v)`; `Values()` returns the stored values, oldest first, as a **new
      slice**: it never changes after later pushes and editing it never changes the window.
    * `Chunk(xs, n)` splits `xs` into consecutive chunks of `n` (the last may be shorter; `n < 1` gives `nil`). The chunks are views of `xs`, but
      appending to one chunk must never overwrite the elements of the next chunk or of `xs`.
    * `Dedup(xs)` returns the values of `xs` without repeats, keeping first occurrences, in a **new slice**; `xs` itself is left untouched.
    * `Counter` counts strings: `Inc(key)`, `Get(key)`; the zero value is ready to use. `Keys()` returns the counted keys in sorted order.
''')

B_WINDOW = dd('''
    package window

    import "sort"

    // Window keeps the last N values pushed.
    type Window struct {
    	buf          []int
    	size, start, n int
    }

    // New makes a window of the given size.
    func New(size int) *Window {
    	return &Window{buf: make([]int, size), size: size}
    }

    // Push adds a value, dropping the oldest when full.
    func (w *Window) Push(v int) {
    	if w.n < w.size {
    		w.buf[(w.start+w.n)%w.size] = v
    		w.n++
    		return
    	}
    	w.buf[w.start] = v
    	w.start = (w.start + 1) % w.size
    }

    // Values returns the stored values, oldest first.
    func (w *Window) Values() []int {
    	out := make([]int, 0, w.n)
    	for i := 0; i < w.n; i++ {
    		out = append(out, w.buf[(w.start+i)%w.size])
    	}
    	return out
    }

    // Chunk splits xs into chunks of n.
    func Chunk(xs []int, n int) [][]int {
    	if n < 1 {
    		return nil
    	}
    	var out [][]int
    	for i := 0; i < len(xs); i += n {
    		end := i + n
    		if end > len(xs) {
    			end = len(xs)
    		}
    		out = append(out, xs[i:end:end])
    	}
    	return out
    }

    // Dedup removes repeats, keeping first occurrences.
    func Dedup(xs []int) []int {
    	seen := map[int]bool{}
    	out := make([]int, 0, len(xs))
    	for _, x := range xs {
    		if !seen[x] {
    			seen[x] = true
    			out = append(out, x)
    		}
    	}
    	return out
    }

    // Counter counts strings.
    type Counter struct {
    	m map[string]int
    }

    // Inc adds one to key.
    func (c *Counter) Inc(key string) {
    	if c.m == nil {
    		c.m = map[string]int{}
    	}
    	c.m[key]++
    }

    // Get returns the count of key.
    func (c *Counter) Get(key string) int { return c.m[key] }

    // Keys returns the counted keys, sorted.
    func (c *Counter) Keys() []string {
    	keys := make([]string, 0, len(c.m))
    	for k := range c.m {
    		keys = append(keys, k)
    	}
    	sort.Strings(keys)
    	return keys
    }
''')

B_VISIBLE = {
    "window_test.go": dd('''
        package window

        import (
        	"reflect"
        	"testing"
        )

        func TestWindowKeepsTheLastValues(t *testing.T) {
        	w := New(3)
        	for _, v := range []int{1, 2, 3, 4} {
        		w.Push(v)
        	}
        	if got := w.Values(); !reflect.DeepEqual(got, []int{2, 3, 4}) {
        		t.Fatalf("got %v", got)
        	}
        }

        func TestChunkAndDedup(t *testing.T) {
        	if got := Chunk([]int{1, 2, 3, 4, 5}, 2); !reflect.DeepEqual(got, [][]int{{1, 2}, {3, 4}, {5}}) {
        		t.Fatalf("chunks %v", got)
        	}
        	if got := Dedup([]int{1, 2, 1, 3, 2}); !reflect.DeepEqual(got, []int{1, 2, 3}) {
        		t.Fatalf("dedup %v", got)
        	}
        }
    '''),
}

B_HIDDEN = {
    "window_hidden_test.go": dd('''
        package window

        import (
        	"fmt"
        	"reflect"
        	"sort"
        	"testing"
        )

        func TestValuesIsACopyInEveryState(t *testing.T) {
        	for pushed := 0; pushed <= 7; pushed++ {
        		w := New(4)
        		for i := 1; i <= pushed; i++ {
        			w.Push(i)
        		}
        		v := w.Values()
        		before := append([]int{}, v...)
        		w.Push(100)
        		w.Push(101)
        		if !reflect.DeepEqual(v, before) {
        			t.Errorf("after %d pushes the slice returned earlier changed: %v -> %v", pushed, before, v)
        		}
        		if len(v) > 0 {
        			stored := w.Values()
        			v[0] = -1
        			if !reflect.DeepEqual(w.Values(), stored) {
        				t.Errorf("editing the returned slice changed the window (%d pushes)", pushed)
        			}
        		}
        	}
        }

        func TestWindowOrder(t *testing.T) {
        	w := New(3)
        	if got := w.Values(); len(got) != 0 {
        		t.Fatalf("empty window gives %v", got)
        	}
        	for i := 1; i <= 8; i++ {
        		w.Push(i)
        	}
        	if got := w.Values(); !reflect.DeepEqual(got, []int{6, 7, 8}) {
        		t.Fatalf("got %v", got)
        	}
        	w.Values()[1] = 99
        	if got := w.Values(); !reflect.DeepEqual(got, []int{6, 7, 8}) {
        		t.Fatalf("after an edit of the copy: %v", got)
        	}
        }

        func TestChunksDoNotOverlapWhenAppended(t *testing.T) {
        	xs := []int{1, 2, 3, 4, 5, 6}
        	chunks := Chunk(xs, 2)
        	if !reflect.DeepEqual(chunks, [][]int{{1, 2}, {3, 4}, {5, 6}}) {
        		t.Fatalf("chunks %v", chunks)
        	}
        	chunks[0] = append(chunks[0], 99)
        	chunks[1] = append(chunks[1], 98, 97)
        	if !reflect.DeepEqual(xs, []int{1, 2, 3, 4, 5, 6}) {
        		t.Fatalf("appending to chunks overwrote the input: %v", xs)
        	}
        	if !reflect.DeepEqual(chunks[2], []int{5, 6}) {
        		t.Fatalf("last chunk damaged: %v", chunks[2])
        	}
        }

        func TestChunkShapes(t *testing.T) {
        	if got := Chunk(nil, 3); len(got) != 0 {
        		t.Errorf("nil input: %v", got)
        	}
        	if got := Chunk([]int{1, 2, 3}, 5); !reflect.DeepEqual(got, [][]int{{1, 2, 3}}) {
        		t.Errorf("one short chunk: %v", got)
        	}
        	if got := Chunk([]int{1, 2, 3}, 0); got != nil {
        		t.Errorf("n=0: %v", got)
        	}
        	if got := Chunk([]int{1, 2, 3}, -2); got != nil {
        		t.Errorf("n<0: %v", got)
        	}
        	if got := Chunk([]int{1, 2, 3, 4}, 4); !reflect.DeepEqual(got, [][]int{{1, 2, 3, 4}}) {
        		t.Errorf("exact fit: %v", got)
        	}
        }

        func TestDedupLeavesItsInputAlone(t *testing.T) {
        	in := []int{3, 1, 3, 2, 1, 2, 5}
        	orig := append([]int{}, in...)
        	got := Dedup(in)
        	if !reflect.DeepEqual(got, []int{3, 1, 2, 5}) {
        		t.Errorf("dedup %v", got)
        	}
        	if !reflect.DeepEqual(in, orig) {
        		t.Errorf("the input was modified: %v", in)
        	}
        	got[0] = 42
        	if in[0] != 3 {
        		t.Errorf("the result shares memory with the input")
        	}
        	if got := Dedup(nil); len(got) != 0 {
        		t.Errorf("nil: %v", got)
        	}
        }

        func TestCounterZeroValue(t *testing.T) {
        	var c Counter
        	if c.Get("x") != 0 || len(c.Keys()) != 0 {
        		t.Fatal("zero counter is not empty")
        	}
        	c.Inc("x")
        	c.Inc("x")
        	c.Inc("y")
        	if c.Get("x") != 2 || c.Get("y") != 1 || c.Get("z") != 0 {
        		t.Fatalf("counts %d %d %d", c.Get("x"), c.Get("y"), c.Get("z"))
        	}
        }

        func TestKeysAreSorted(t *testing.T) {
        	var c Counter
        	for i := 0; i < 40; i++ {
        		c.Inc(fmt.Sprintf("key-%02d", (i*17)%40))
        	}
        	keys := c.Keys()
        	if len(keys) != 40 || !sort.StringsAreSorted(keys) {
        		t.Fatalf("keys not sorted: %v", keys)
        	}
        }
    '''),
}


def _b_prompts():
    p = {}
    p["values-view"] = (
        "The chart widget keeps the slice it got from `Values()` and its history graph changes by itself when new points are pushed. It only "
        "happens until the window has wrapped around once. `Values()` is documented to return a copy."
    )
    p["chunk-cap"] = (
        "Batching with `Chunk` corrupts data: when the sender appends a trailer value to one batch, the first element of the *next* batch is "
        "overwritten (and the input array is changed too). Appending to a batch must never touch anything else."
    )
    p["dedup"] = (
        "After we call `Dedup(samples)` our original `samples` slice is garbled (it contains the deduplicated values followed by leftovers). "
        "Dedup is documented to leave its input alone and return a new slice."
    )
    p["keys"] = (
        "The metrics report lists counter names in a different order on every run (diffs of the output are useless). `Keys()` should be sorted."
    )
    p["nil-map"] = (
        "`var c window.Counter; c.Inc(\"x\")` panics with `assignment to entry in nil map`, although the README says the zero value is ready to use."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "go.mod": langs.go_mod("window"), "window.go": B_WINDOW}
    f = "window.go"
    bugs = [
        Bug("keys-in-map-order", 1, {f: [("\tsort.Strings(keys)\n\treturn keys\n", "\treturn keys\n"), ('import "sort"\n\n', "")]}, P["keys"]),
        Bug("counter-needs-make", 1, {f: [("\tif c.m == nil {\n\t\tc.m = map[string]int{}\n\t}\n", "")]}, P["nil-map"]),
        Bug("values-returns-a-view", 3, {f: [("func (w *Window) Values() []int {\n", "func (w *Window) Values() []int {\n\tif w.start+w.n <= w.size {\n\t\treturn w.buf[w.start : w.start+w.n]\n\t}\n")]}, P["values-view"]),
        Bug("dedup-in-place", 3, {f: [("\tout := make([]int, 0, len(xs))\n\tfor _, x := range xs {\n\t\tif !seen[x] {", "\tout := xs[:0]\n\tfor _, x := range xs {\n\t\tif !seen[x] {")]}, P["dedup"]),
        Bug("chunks-share-spare-capacity", 4, {f: [("\t\tout = append(out, xs[i:end:end])\n", "\t\tout = append(out, xs[i:end])\n")]}, P["chunk-cap"]),
    ]
    return Base("window", "go", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-go-slices", category="fix", lang="go", kind="fix", n=10,
        summary="go slice aliasing, in-place edits while ranging and shared loop variables (playlist queue, sliding window)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
