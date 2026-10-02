"""Scenarios (reproduction programs) for the go slot modules of the review bank: ``go run ./cmd/scenario``."""
from __future__ import annotations

from fx import dd

SESSIONS_SCENARIO = dd('''
    package main

    import (
    	"fmt"
    	"os"
    	"runtime"
    	"sync"
    	"time"

    	"example.com/portal/sessions"
    )

    func try(label string, f func()) {
    	defer func() {
    		if r := recover(); r != nil {
    			fmt.Printf("%s: panic: %v\\n", label, r)
    		}
    	}()
    	f()
    }

    func main() {
    	time.AfterFunc(8*time.Second, func() {
    		fmt.Println("scenario stuck for 8s (deadlock?)")
    		os.Exit(3)
    	})
    	var mu sync.Mutex
    	clock := time.Date(2025, 3, 14, 9, 0, 0, 0, time.UTC)
    	now := func() time.Time {
    		mu.Lock()
    		defer mu.Unlock()
    		return clock
    	}
    	advance := func(d time.Duration) {
    		mu.Lock()
    		clock = clock.Add(d)
    		mu.Unlock()
    	}
    	st := sessions.NewStore(now)

    	ann, err := st.Create("ann")
    	if err != nil {
    		fmt.Println("create failed:", err)
    		return
    	}
    	fmt.Println("session id length:", len(ann))
    	s, err := st.Get(ann)
    	fmt.Println("fresh session:", s.User, err)

    	advance(20 * time.Minute)
    	_, err = st.Get(ann)
    	fmt.Println("get after 20m:", err)
    	advance(20 * time.Minute)
    	_, err = st.Get(ann)
    	fmt.Println("get 20m after the previous get:", err)

    	_, err = st.Get("no-such-session")
    	fmt.Println("get unknown id:", err)

    	bob, _ := st.Create("bob")
    	advance(sessions.TTL)
    	_, err = st.Get(bob)
    	fmt.Println("get exactly at the expiry time:", err)

    	cy, _ := st.Create("cy")
    	advance(sessions.TTL)
    	dave, _ := st.Create("dave")
    	fmt.Println("sweep removed:", st.Sweep())
    	_, err = st.Get(cy)
    	fmt.Println("cy after sweep:", err)
    	_, err = st.Get(dave)
    	fmt.Println("dave after sweep:", err)

    	for i := 0; i < 3; i++ {
    		st.Create("eve")
    	}
    	st.Create("fay")
    	fmt.Println("revoked eve:", st.RevokeUser("eve"))
    	fmt.Println("revoked nobody:", st.RevokeUser("nobody"))

    	base := runtime.NumGoroutine()
    	stop := st.StartJanitor(5 * time.Millisecond)
    	time.Sleep(30 * time.Millisecond)
    	try("stop", stop)
    	try("stop again", stop)
    	time.Sleep(30 * time.Millisecond)
    	fmt.Println("goroutines left behind by the janitor:", runtime.NumGoroutine()-base)
    }
''')

UPLOADS_SCENARIO = dd('''
    package main

    import (
    	"bytes"
    	"fmt"
    	"io"
    	"io/fs"
    	"mime/multipart"
    	"net/http"
    	"net/http/httptest"
    	"os"
    	"path/filepath"
    	"sort"
    	"strings"

    	"example.com/helpdesk/uploads"
    )

    type flaky struct{ n int }

    func (f *flaky) Read(p []byte) (int, error) {
    	if f.n <= 0 {
    		return 0, fmt.Errorf("connection reset by peer")
    	}
    	if len(p) > f.n {
    		p = p[:f.n]
    	}
    	for i := range p {
    		p[i] = 'x'
    	}
    	f.n -= len(p)
    	return len(p), nil
    }

    func tree(base string) string {
    	var out []string
    	filepath.WalkDir(base, func(p string, d fs.DirEntry, err error) error {
    		if err == nil && p != base {
    			rel, _ := filepath.Rel(base, p)
    			if d.IsDir() {
    				rel += "/"
    			}
    			out = append(out, rel)
    		}
    		return nil
    	})
    	sort.Strings(out)
    	return strings.Join(out, " ")
    }

    func rel(base, p string) string {
    	r, err := filepath.Rel(base, p)
    	if err != nil {
    		return p
    	}
    	return r
    }

    func upload(st *uploads.Store, name, body string) (int, string) {
    	var buf bytes.Buffer
    	mw := multipart.NewWriter(&buf)
    	fw, _ := mw.CreateFormFile("file", name)
    	io.WriteString(fw, body)
    	mw.Close()
    	req := httptest.NewRequest(http.MethodPost, "/upload", &buf)
    	req.Header.Set("Content-Type", mw.FormDataContentType())
    	rec := httptest.NewRecorder()
    	st.Handler(rec, req)
    	return rec.Code, strings.TrimSpace(strings.ReplaceAll(rec.Body.String(), "\\n", " "))
    }

    func main() {
    	base, err := os.MkdirTemp("", "uploads")
    	if err != nil {
    		panic(err)
    	}
    	defer os.RemoveAll(base)
    	root := filepath.Join(base, "site", "data", "files")
    	os.MkdirAll(root, 0o755)
    	st := &uploads.Store{Root: root}

    	for _, name := range []string{"report.pdf", "../../escape.txt", "..\\\\win.txt", "report.pdf", "", ".."} {
    		p, err := st.Save(name, strings.NewReader("hello"))
    		if err != nil {
    			fmt.Printf("Save(%q): error: %s\\n", name, rel(base, strings.ReplaceAll(err.Error(), base, ".")))
    			continue
    		}
    		fmt.Printf("Save(%q) -> %s\\n", name, rel(base, p))
    	}
    	fmt.Println("tree:", tree(base))

    	p, err := st.Save("edge.bin", io.LimitReader(&flaky{n: uploads.MaxBytes}, uploads.MaxBytes))
    	fmt.Println("exactly MaxBytes:", rel(base, p), err)
    	_, err = st.Save("big.bin", &flaky{n: uploads.MaxBytes + 10})
    	fmt.Println("MaxBytes+10:", err)
    	_, err = st.Save("broken.bin", &flaky{n: 100})
    	fmt.Println("connection drops after 100 bytes:", err)
    	fmt.Println("tree:", tree(base))

    	os.Mkdir(filepath.Join(root, "subdir"), 0o755)
    	names, err := st.List()
    	fmt.Printf("List: %q %v\\n", names, err)

    	sum, err := st.Checksum("report.pdf")
    	fmt.Println("Checksum(report.pdf):", sum, err)

    	fmt.Println("Delete(report.pdf):", st.Delete("report.pdf"))
    	fmt.Println("Delete(../../escape.txt):", strings.ReplaceAll(fmt.Sprint(st.Delete("../../escape.txt")), base, "."))
    	fmt.Println("tree:", tree(base))

    	code, body := upload(st, "ticket.txt", "my printer is on fire")
    	fmt.Println("POST ticket.txt:", code, body)
    	code, body = upload(st, "ticket.txt", "again")
    	fmt.Println("POST ticket.txt again:", code, strings.ReplaceAll(body, base, "."))
    	rec := httptest.NewRecorder()
    	st.Handler(rec, httptest.NewRequest(http.MethodGet, "/upload", nil))
    	fmt.Println("GET:", rec.Code, strings.TrimSpace(rec.Body.String()))
    }
''')

BATCH_SCENARIO = dd('''
    package main

    import (
    	"context"
    	"errors"
    	"fmt"
    	"os"
    	"sort"
    	"sync/atomic"
    	"time"

    	"example.com/pipeline/batch"
    )

    var errBoom = errors.New("boom")

    func try(label string, f func()) {
    	defer func() {
    		if r := recover(); r != nil {
    			fmt.Printf("%s: panic: %v\\n", label, r)
    		}
    	}()
    	f()
    }

    func main() {
    	time.AfterFunc(8*time.Second, func() {
    		fmt.Println("scenario stuck for 8s (deadlock?)")
    		os.Exit(3)
    	})
    	ctx := context.Background()

    	jobs := make([]batch.Job, 6)
    	for i := range jobs {
    		i := i
    		jobs[i] = func(ctx context.Context) (string, error) {
    			if i == 2 || i == 4 {
    				return "", fmt.Errorf("job body %d: %w", i, errBoom)
    			}
    			return fmt.Sprintf("value-%d", i), nil
    		}
    	}
    	for _, w := range []int{2, 0} {
    		res := batch.Run(ctx, jobs, w)
    		fmt.Printf("Run with %d workers:", w)
    		for _, r := range res {
    			fmt.Printf(" [%d %q %v]", r.Index, r.Value, r.Err != nil)
    		}
    		fmt.Println()
    		err := batch.FirstError(res)
    		fmt.Println("FirstError:", err, "| is boom:", errors.Is(err, errBoom))
    	}

    	var calls int32
    	failing := func(ctx context.Context) (string, error) {
    		atomic.AddInt32(&calls, 1)
    		return "", errBoom
    	}
    	_, err := batch.Retry(3, time.Millisecond, failing)(ctx)
    	fmt.Println("Retry(3) all failing:", err, "after", atomic.LoadInt32(&calls), "calls")

    	atomic.StoreInt32(&calls, 0)
    	flaky := func(ctx context.Context) (string, error) {
    		if atomic.AddInt32(&calls, 1) < 3 {
    			return "", errBoom
    		}
    		return "third time lucky", nil
    	}
    	v, err := batch.Retry(5, time.Millisecond, flaky)(ctx)
    	fmt.Println("Retry(5) flaky:", v, err, "after", atomic.LoadInt32(&calls), "calls")

    	cctx, cancel := context.WithCancel(ctx)
    	time.AfterFunc(20*time.Millisecond, cancel)
    	start := time.Now()
    	_, err = batch.Retry(3, 2*time.Second, failing)(cctx)
    	fmt.Println("Retry cancelled during the delay:", err, "| returned within 700ms:", time.Since(start) < 700*time.Millisecond)

    	slow := func(ctx context.Context) (string, error) {
    		select {
    		case <-ctx.Done():
    			return "", ctx.Err()
    		case <-time.After(300 * time.Millisecond):
    			return "finished", nil
    		}
    	}
    	v, err = batch.WithTimeout(50*time.Millisecond, slow)(ctx)
    	fmt.Println("WithTimeout of 50 ms on a slow job:", v, err)
    	pctx, pcancel := context.WithCancel(ctx)
    	time.AfterFunc(20*time.Millisecond, pcancel)
    	v, err = batch.WithTimeout(5*time.Second, slow)(pctx)
    	fmt.Println("parent cancelled, then WithTimeout of 5 seconds:", v, err)

    	a, b := make(chan string), make(chan string)
    	go func() {
    		for _, s := range []string{"a1", "a2", "a3"} {
    			a <- s
    		}
    		close(a)
    	}()
    	go func() {
    		for _, s := range []string{"b1", "b2"} {
    			b <- s
    		}
    		close(b)
    	}()
    	var got []string
    	try("merge", func() {
    		for s := range batch.Merge(a, b) {
    			got = append(got, s)
    		}
    	})
    	sort.Strings(got)
    	fmt.Println("Merge:", got)
    }
''')

SCENARIOS = {"go-sessions": SESSIONS_SCENARIO, "go-attachments": UPLOADS_SCENARIO, "go-batchrun": BATCH_SCENARIO}
