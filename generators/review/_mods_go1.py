"""Slot modules (go), part 1: sessions, uploads, batch runner."""
from fx import dd, langs

from ._slots import Bad, Module, Slot, validate_module

GO_MOD = langs.go_mod("portal")

# ---------------------------------------------------------------------------------------------------------------------
# in-memory session store
# ---------------------------------------------------------------------------------------------------------------------

SESS_TEMPLATE = dd('''
    // Package sessions keeps the login sessions of the intranet portal in memory.
    package sessions

    @@imports@@

    // TTL is how long a session lives without activity.
    const TTL = 30 * time.Minute

    // ErrExpired is returned for unknown and expired sessions alike.
    var ErrExpired = errors.New("sessions: unknown or expired session")

    // Session is what the portal knows about a logged-in user.
    type Session struct {
        User    string
        Expires time.Time
    }

    // Store is an in-memory session table, safe for concurrent use.
    type Store struct {
        mu   sync.Mutex
        byID map[string]*Session
        now  func() time.Time
    }

    // NewStore returns an empty store that reads the time from now.
    func NewStore(now func() time.Time) *Store {
        return &Store{byID: make(map[string]*Session), now: now}
    }

    @@newid@@

    @@create@@

    @@get@@

    @@revoke@@

    @@sweep@@

    @@janitor@@
''')

_S_IMPORTS = dd('''
    import (
        "crypto/rand"
        "encoding/hex"
        "errors"
        "sync"
        "time"
    )
''')
_S_NEWID = dd('''
    // newID returns 128 random bits as hex.
    func newID() (string, error) {
        var b [16]byte
        if _, err := rand.Read(b[:]); err != nil {
            return "", err
        }
        return hex.EncodeToString(b[:]), nil
    }
''')
_S_CREATE = dd('''
    // Create starts a session for user and returns its id.
    func (s *Store) Create(user string) (string, error) {
        id, err := newID()
        if err != nil {
            return "", err
        }
        s.mu.Lock()
        defer s.mu.Unlock()
        s.byID[id] = &Session{User: user, Expires: s.now().Add(TTL)}
        return id, nil
    }
''')
_S_GET = dd('''
    // Get returns a copy of the session and extends it by TTL. Unknown and expired sessions give ErrExpired.
    func (s *Store) Get(id string) (Session, error) {
        s.mu.Lock()
        defer s.mu.Unlock()
        sess, ok := s.byID[id]
        if !ok || !s.now().Before(sess.Expires) {
            delete(s.byID, id)
            return Session{}, ErrExpired
        }
        sess.Expires = s.now().Add(TTL)
        return *sess, nil
    }
''')
_S_REVOKE = dd('''
    // RevokeUser removes every session of user and returns how many there were.
    func (s *Store) RevokeUser(user string) int {
        s.mu.Lock()
        defer s.mu.Unlock()
        n := 0
        for id, sess := range s.byID {
            if sess.User == user {
                delete(s.byID, id)
                n++
            }
        }
        return n
    }
''')
_S_SWEEP = dd('''
    // Sweep drops expired sessions and returns how many were removed.
    func (s *Store) Sweep() int {
        s.mu.Lock()
        defer s.mu.Unlock()
        now := s.now()
        n := 0
        for id, sess := range s.byID {
            if !now.Before(sess.Expires) {
                delete(s.byID, id)
                n++
            }
        }
        return n
    }
''')
_S_JANITOR = dd('''
    // StartJanitor sweeps every interval until the returned stop function is called; stop waits for the goroutine to exit
    // and may be called more than once.
    func (s *Store) StartJanitor(every time.Duration) (stop func()) {
        done := make(chan struct{})
        exited := make(chan struct{})
        var once sync.Once
        go func() {
            defer close(exited)
            t := time.NewTicker(every)
            defer t.Stop()
            for {
                select {
                case <-t.C:
                    s.Sweep()
                case <-done:
                    return
                }
            }
        }()
        return func() {
            once.Do(func() { close(done) })
            <-exited
        }
    }
''')

SESSIONS = Module(
    name="go-sessions", lang="go", path="sessions/store.go", difficulty=3,
    title="In-memory session store with sliding expiry and a janitor",
    blurb="The `portal` module is the back end of a company intranet; `sessions` keeps who is logged in.",
    intro="Sessions used to live in a signed cookie only, which made logging someone out impossible. This PR adds a server-side store:",
    outro="Handlers call the store from many goroutines. I ran it under the staging load generator for ten minutes without errors.",
    new_file=True,
    template=SESS_TEMPLATE,
    ctx={"go.mod": GO_MOD, "README.md": "# portal\n\nIntranet back end.\n"},
    slots=[
        Slot("imports", "<imports>", _S_IMPORTS, []),
        Slot("newid", "newID", _S_NEWID, [
            Bad(dd('''
                // newID returns 128 random bits as hex.
                func newID() (string, error) {
                    var b [16]byte
                    rand.Read(b[:])
                    return hex.EncodeToString(b[:]), nil
                }
            '''), "security", "session ids come from math/rand (predictable, seeded deterministically) instead of crypto/rand", ("math/rand", "crypto/rand", "predictable", "session id"),
                imports=_S_IMPORTS.replace('    "crypto/rand"\n', '').replace('    "errors"\n', '    "errors"\n    "math/rand"\n')),
            Bad(_S_NEWID.replace("    if _, err := rand.Read(b[:]); err != nil {\n        return \"\", err\n    }\n", "    rand.Read(b[:])\n"), "error-handling", "the error from crypto/rand.Read is ignored; on failure the id would be all zeros", ("error", "rand.Read", "ignored", "zeros")),
            Bad(_S_NEWID.replace("var b [16]byte", "var b [4]byte"), "security", "only 32 random bits: session ids are guessable by brute force", ("bits", "entropy", "16", "guess")),
        ], note="adds random session ids"),
        Slot("create", "Store.Create", _S_CREATE, [
            Bad(_S_CREATE.replace("    s.mu.Lock()\n    defer s.mu.Unlock()\n", ""), "concurrency", "the map is written without holding the mutex: a data race with every other method", ("mutex", "lock", "race", "map")),
            Bad(_S_CREATE.replace("s.now().Add(TTL)", "s.now()"), "logic", "the expiry is the creation time, so a new session is already expired", ("TTL", "Expires", "expired", "Add")),
        ], note="adds `Create`"),
        Slot("get", "Store.Get", _S_GET, [
            Bad(_S_GET.replace("!s.now().Before(sess.Expires)", "s.now().After(sess.Expires)"), "off-by-one", "a session is still valid at the exact expiry instant (After instead of !Before), inconsistent with Sweep", ("After", "Before", "boundary", "expiry")),
            Bad(dd('''
                // Get returns a copy of the session and extends it by TTL. Unknown and expired sessions give ErrExpired.
                func (s *Store) Get(id string) (Session, error) {
                    s.mu.Lock()
                    sess, ok := s.byID[id]
                    if !ok || !s.now().Before(sess.Expires) {
                        delete(s.byID, id)
                        return Session{}, ErrExpired
                    }
                    sess.Expires = s.now().Add(TTL)
                    s.mu.Unlock()
                    return *sess, nil
                }
            '''), "concurrency", "the early return for an unknown or expired session leaves the mutex locked, so the next call deadlocks", ("unlock", "deadlock", "defer", "return")),
            Bad(_S_GET.replace("    sess.Expires = s.now().Add(TTL)\n", ""), "logic", "the expiry is never extended, so a session ends TTL after login even for an active user", ("sliding", "extend", "Expires", "TTL")),
        ], note="adds `Get` with sliding expiry"),
        Slot("revoke", "Store.RevokeUser", _S_REVOKE, [
            Bad(_S_REVOKE.replace("            n++\n", "            n++\n            break\n"), "logic", "the loop stops after the first match, so only one of the user's sessions is revoked", ("break", "first", "all sessions", "revoke")),
            Bad(_S_REVOKE.replace("    s.mu.Lock()\n    defer s.mu.Unlock()\n", ""), "concurrency", "RevokeUser iterates and deletes from the map without the mutex", ("mutex", "lock", "race", "map")),
        ], note="adds `RevokeUser` for forced logout"),
        Slot("sweep", "Store.Sweep", _S_SWEEP, [
            Bad(_S_SWEEP.replace("!now.Before(sess.Expires)", "now.After(sess.Expires)"), "off-by-one", "Sweep keeps a session that expires exactly now while Get already treats it as expired", ("After", "Before", "boundary", "inconsistent")),
            Bad(_S_SWEEP.replace("            delete(s.byID, id)\n            n++\n", "            delete(s.byID, id)\n        }\n        n++\n        if false {\n"), "logic", "n is incremented for every session, not just the removed ones", ("count", "n++", "removed")),
        ], note="adds `Sweep`"),
        Slot("janitor", "Store.StartJanitor", _S_JANITOR, [
            Bad(_S_JANITOR.replace("        defer t.Stop()\n", ""), "resource-leak", "the ticker is never stopped", ("ticker", "Stop", "leak")),
            Bad(dd('''
                // StartJanitor sweeps every interval until the returned stop function is called; stop waits for the goroutine to exit
                // and may be called more than once.
                func (s *Store) StartJanitor(every time.Duration) (stop func()) {
                    go func() {
                        for range time.Tick(every) {
                            s.Sweep()
                        }
                    }()
                    return func() {}
                }
            '''), "resource-leak", "the goroutine and the time.Tick ticker can never be stopped: stop() is a no-op, so every StartJanitor leaks both", ("goroutine", "leak", "time.Tick", "stop")),
            Bad(_S_JANITOR.replace("        once.Do(func() { close(done) })\n", "        close(done)\n").replace("    var once sync.Once\n", ""), "concurrency", "calling stop twice closes the channel twice and panics although the comment promises it may be called repeatedly", ("close", "once", "panic", "twice")),
        ], note="adds `StartJanitor` to sweep expired sessions in the background"),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# ticket attachments
# ---------------------------------------------------------------------------------------------------------------------

UPLOAD_TEMPLATE = dd('''
    // Package uploads stores the files members attach to support tickets.
    package uploads

    @@imports@@

    // MaxBytes is the largest attachment we accept.
    const MaxBytes = 5 << 20

    var (
        errBadName  = errors.New("uploads: bad file name")
        errTooLarge = errors.New("uploads: file too large")
    )

    // Store keeps the attachments in one flat directory.
    type Store struct {
        Root string
    }

    @@clean@@

    @@save@@

    @@handler@@

    @@list@@

    @@delete@@

    @@checksum@@
''')

_U_IMPORTS = dd('''
    import (
        "crypto/sha256"
        "encoding/hex"
        "errors"
        "fmt"
        "io"
        "net/http"
        "os"
        "path/filepath"
        "strings"
    )
''')
_U_CLEAN = dd('''
    // cleanName reduces a client-supplied file name to a plain base name.
    func cleanName(name string) (string, error) {
        base := filepath.Base(strings.ReplaceAll(name, "\\\\", "/"))
        if base == "." || base == ".." || base == "/" || base == "" {
            return "", errBadName
        }
        return base, nil
    }
''')
_U_SAVE = dd('''
    // Save copies r into Root under a cleaned name and returns the stored path. Files above MaxBytes are refused and not kept,
    // and an existing attachment is never overwritten.
    func (s *Store) Save(name string, r io.Reader) (string, error) {
        base, err := cleanName(name)
        if err != nil {
            return "", err
        }
        path := filepath.Join(s.Root, base)
        f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
        if err != nil {
            return "", err
        }
        defer f.Close()
        n, err := io.Copy(f, io.LimitReader(r, MaxBytes+1))
        if err != nil {
            os.Remove(path)
            return "", err
        }
        if n > MaxBytes {
            os.Remove(path)
            return "", errTooLarge
        }
        return path, nil
    }
''')
_U_HANDLER = dd('''
    // Handler accepts POST with a multipart field "file" and answers 201 with the stored name.
    func (s *Store) Handler(w http.ResponseWriter, req *http.Request) {
        if req.Method != http.MethodPost {
            http.Error(w, "POST only", http.StatusMethodNotAllowed)
            return
        }
        req.Body = http.MaxBytesReader(w, req.Body, MaxBytes+1<<20)
        file, hdr, err := req.FormFile("file")
        if err != nil {
            http.Error(w, "missing file", http.StatusBadRequest)
            return
        }
        defer file.Close()
        path, err := s.Save(hdr.Filename, file)
        switch {
        case errors.Is(err, errTooLarge):
            http.Error(w, "file too large", http.StatusRequestEntityTooLarge)
        case err != nil:
            http.Error(w, "could not store file", http.StatusInternalServerError)
        default:
            w.WriteHeader(http.StatusCreated)
            fmt.Fprint(w, filepath.Base(path))
        }
    }
''')
_U_LIST = dd('''
    // List returns the names of the stored files in alphabetical order.
    func (s *Store) List() ([]string, error) {
        entries, err := os.ReadDir(s.Root)
        if err != nil {
            return nil, err
        }
        var names []string
        for _, e := range entries {
            if e.Type().IsRegular() {
                names = append(names, e.Name())
            }
        }
        return names, nil
    }
''')
_U_DELETE = dd('''
    // Delete removes one stored file.
    func (s *Store) Delete(name string) error {
        base, err := cleanName(name)
        if err != nil {
            return err
        }
        return os.Remove(filepath.Join(s.Root, base))
    }
''')
_U_CHECKSUM = dd('''
    // Checksum returns the hex SHA-256 of a stored file.
    func (s *Store) Checksum(name string) (string, error) {
        base, err := cleanName(name)
        if err != nil {
            return "", err
        }
        f, err := os.Open(filepath.Join(s.Root, base))
        if err != nil {
            return "", err
        }
        defer f.Close()
        h := sha256.New()
        if _, err := io.Copy(h, f); err != nil {
            return "", err
        }
        return hex.EncodeToString(h.Sum(nil)), nil
    }
''')

UPLOADS = Module(
    name="go-attachments", lang="go", path="uploads/store.go", difficulty=3,
    title="Ticket attachments: store, list, delete, checksum, upload handler",
    blurb="The `helpdesk` module is the back end of a support-ticket system; `uploads` stores customers' attachments.",
    intro="Customers can currently only describe problems in words. This PR lets them attach files to a ticket:",
    outro="The file name in the multipart form is whatever the customer's browser sends. I tried 1 KB, 4 MB and 6 MB files with curl.",
    new_file=True,
    template=UPLOAD_TEMPLATE,
    ctx={"go.mod": langs.go_mod("helpdesk"), "README.md": "# helpdesk\n\nSupport ticket back end.\n"},
    slots=[
        Slot("imports", "<imports>", _U_IMPORTS, []),
        Slot("clean", "cleanName", _U_CLEAN, [
            Bad(dd('''
                // cleanName reduces a client-supplied file name to a plain base name.
                func cleanName(name string) (string, error) {
                    if name == "" {
                        return "", errBadName
                    }
                    return name, nil
                }
            '''), "security", "the client's file name is used as it is, so `../../x` writes outside the storage directory (path traversal)", ("traversal", "../", "Base", "filepath"),
                imports=_U_IMPORTS.replace('    "strings"\n', '')),
            Bad(_U_CLEAN.replace('filepath.Base(strings.ReplaceAll(name, "\\\\", "/"))', 'strings.TrimPrefix(name, "../")'), "security", "only one leading `../` is removed; `../../x`, `a/../../x` and absolute paths still escape the directory", ("traversal", "TrimPrefix", "../", "filepath.Base")),
        ], note="adds `cleanName()` for client-supplied names"),
        Slot("save", "Store.Save", _U_SAVE, [
            Bad(_U_SAVE.replace("    defer f.Close()\n", ""), "resource-leak", "the file is never closed", ("close", "defer", "descriptor", "leak")),
            Bad(_U_SAVE.replace("io.Copy(f, io.LimitReader(r, MaxBytes+1))", "io.Copy(f, r)"), "validation", "the size limit is only checked after the whole body has been written to disk, so a huge upload still fills the disk", ("LimitReader", "limit", "disk", "unbounded")),
            Bad(_U_SAVE.replace("os.O_WRONLY|os.O_CREATE|os.O_EXCL", "os.O_WRONLY|os.O_CREATE|os.O_TRUNC"), "logic", "O_TRUNC instead of O_EXCL: an upload with an existing name silently overwrites another customer's attachment", ("O_EXCL", "O_TRUNC", "overwrite", "existing")),
            Bad(_U_SAVE.replace("if n > MaxBytes {", "if n >= MaxBytes {"), "off-by-one", "a file of exactly MaxBytes is refused as too large", (">=", "MaxBytes", "boundary", "exactly")),
            Bad(_U_SAVE.replace("n, err := io.Copy(f, io.LimitReader(r, MaxBytes+1))", "n, _ := io.Copy(f, io.LimitReader(r, MaxBytes+1))").replace("    if err != nil {\n        os.Remove(path)\n        return \"\", err\n    }\n", ""), "error-handling", "the error from io.Copy is discarded, so a truncated upload is reported as success", ("error", "io.Copy", "ignored", "truncated")),
        ], note="adds `Store.Save()`: size limit, no overwrite"),
        Slot("handler", "Store.Handler", _U_HANDLER, [
            Bad(_U_HANDLER.replace("    req.Body = http.MaxBytesReader(w, req.Body, MaxBytes+1<<20)\n", ""), "validation", "the request body is not limited before the multipart form is parsed, so a client can stream unbounded data", ("MaxBytesReader", "limit", "body", "unbounded")),
            Bad(_U_HANDLER.replace('http.Error(w, "could not store file", http.StatusInternalServerError)', "http.Error(w, err.Error(), http.StatusInternalServerError)"), "security", "the raw error text, which contains the server's storage path, is sent to the client (information disclosure)", ("err.Error", "disclosure", "path", "leak")),
            Bad(_U_HANDLER.replace("    defer file.Close()\n", ""), "resource-leak", "the uploaded file handle is never closed", ("close", "defer", "file", "leak")),
            Bad(_U_HANDLER.replace('''    if req.Method != http.MethodPost {
        http.Error(w, "POST only", http.StatusMethodNotAllowed)
        return
    }
''', ""), "validation", "any HTTP method is accepted, including GET with a query-string trick or HEAD probes", ("method", "POST", "MethodNotAllowed")),
        ], note="adds the HTTP upload `Handler`"),
        Slot("list", "Store.List", _U_LIST, [
            Bad(_U_LIST.replace("if e.Type().IsRegular() {", "if true {"), "logic", "directories and symlinks are listed as if they were attachments", ("IsRegular", "directory", "symlink", "filter")),
        ], note="adds `List()`"),
        Slot("delete", "Store.Delete", _U_DELETE, [
            Bad(dd('''
                // Delete removes one stored file.
                func (s *Store) Delete(name string) error {
                    return os.Remove(filepath.Join(s.Root, name))
                }
            '''), "security", "the name is not cleaned, so `../../etc/something` deletes files outside the storage directory", ("cleanName", "traversal", "../", "Join")),
        ], note="adds `Delete()`"),
        Slot("checksum", "Store.Checksum", _U_CHECKSUM, [
            Bad(_U_CHECKSUM.replace("    defer f.Close()\n", ""), "resource-leak", "the file is not closed after hashing", ("close", "defer", "file")),
            Bad(_U_CHECKSUM.replace('        return "", err\n    }\n    return hex.EncodeToString(h.Sum(nil)), nil', '        return "", err\n    }\n    return hex.EncodeToString(h.Sum(nil)[:16]), nil'), "logic", "the digest is cut to 16 bytes although the doc promises the full SHA-256", ("digest", "truncat", "16", "SHA-256")),
        ], note="adds `Checksum()` (SHA-256 of a stored file)"),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# batch runner
# ---------------------------------------------------------------------------------------------------------------------

BATCH_TEMPLATE = dd('''
    // Package batch runs independent jobs on a small pool and gathers their results in input order.
    package batch

    import (
        "context"
        "fmt"
        "sync"
        "time"
    )

    // Job is one unit of work.
    type Job func(ctx context.Context) (string, error)

    // Result is the outcome of the job with the same index.
    type Result struct {
        Index int
        Value string
        Err   error
    }

    @@run@@

    @@first@@

    @@retry@@

    @@timeout@@

    @@merge@@
''')

_B_RUN = dd('''
    // Run executes the jobs on at most `workers` goroutines (at least one) and returns the results in input order.
    // Jobs that have not started when ctx ends report ctx.Err().
    func Run(ctx context.Context, jobs []Job, workers int) []Result {
        if workers < 1 {
            workers = 1
        }
        results := make([]Result, len(jobs))
        sem := make(chan struct{}, workers)
        var wg sync.WaitGroup
        for i := range jobs {
            i := i
            wg.Add(1)
            sem <- struct{}{}
            go func() {
                defer wg.Done()
                defer func() { <-sem }()
                if err := ctx.Err(); err != nil {
                    results[i] = Result{Index: i, Err: err}
                    return
                }
                v, err := jobs[i](ctx)
                results[i] = Result{Index: i, Value: v, Err: err}
            }()
        }
        wg.Wait()
        return results
    }
''')
_B_FIRST = dd('''
    // FirstError returns the error of the lowest-indexed failed result, wrapped with its index, or nil.
    func FirstError(rs []Result) error {
        for _, r := range rs {
            if r.Err != nil {
                return fmt.Errorf("job %d: %w", r.Index, r.Err)
            }
        }
        return nil
    }
''')
_B_RETRY = dd('''
    // Retry wraps job so that it is tried up to attempts times with delay between tries; it gives up early when ctx ends.
    func Retry(attempts int, delay time.Duration, job Job) Job {
        return func(ctx context.Context) (string, error) {
            var err error
            for n := 0; n < attempts; n++ {
                var v string
                if v, err = job(ctx); err == nil {
                    return v, nil
                }
                if n == attempts-1 {
                    break
                }
                select {
                case <-time.After(delay):
                case <-ctx.Done():
                    return "", ctx.Err()
                }
            }
            return "", err
        }
    }
''')
_B_TIMEOUT = dd('''
    // WithTimeout limits job to d.
    func WithTimeout(d time.Duration, job Job) Job {
        return func(ctx context.Context) (string, error) {
            ctx, cancel := context.WithTimeout(ctx, d)
            defer cancel()
            return job(ctx)
        }
    }
''')
_B_MERGE = dd('''
    // Merge forwards everything from the inputs to the returned channel, which is closed once every input is closed.
    func Merge(inputs ...<-chan string) <-chan string {
        out := make(chan string)
        var wg sync.WaitGroup
        wg.Add(len(inputs))
        for _, in := range inputs {
            in := in
            go func() {
                defer wg.Done()
                for v := range in {
                    out <- v
                }
            }()
        }
        go func() {
            wg.Wait()
            close(out)
        }()
        return out
    }
''')

BATCH = Module(
    name="go-batchrun", lang="go", path="batch/batch.go", difficulty=4,
    title="batch: bounded worker pool, retry, timeout and merge helpers",
    blurb="The `pipeline` module copies product photos between storage buckets; `batch` is its concurrency helper.",
    intro="The importer ran jobs one by one and took hours. This PR adds a small concurrency toolbox:",
    outro="Used by the importer with 8 workers against the staging bucket; the run finished in 11 minutes instead of 70.",
    new_file=True,
    template=BATCH_TEMPLATE,
    ctx={"go.mod": langs.go_mod("pipeline"), "README.md": "# pipeline\n\nPhoto import tooling.\n"},
    slots=[
        Slot("run", "Run", _B_RUN, [
            Bad(_B_RUN.replace("        i := i\n", ""), "concurrency", "the loop variable i is captured by the goroutine without a per-iteration copy (module is go 1.21), so jobs may all see the last index", ("loop variable", "capture", "i := i", "goroutine")),
            Bad(_B_RUN.replace("        wg.Add(1)\n        sem <- struct{}{}\n        go func() {\n            defer wg.Done()", "        sem <- struct{}{}\n        go func() {\n            wg.Add(1)\n            defer wg.Done()"), "concurrency", "wg.Add is called inside the goroutine, so wg.Wait can return before the goroutines have registered", ("wg.Add", "WaitGroup", "race", "Wait")),
            Bad(_B_RUN.replace("    if workers < 1 {\n        workers = 1\n    }\n", ""), "validation", "workers == 0 creates an unbuffered semaphore that nobody receives from, so Run blocks forever", ("workers", "deadlock", "zero", "semaphore")),
            Bad(_B_RUN.replace("            defer func() { <-sem }()\n", ""), "concurrency", "the semaphore slot is never released, so after `workers` jobs Run blocks forever", ("semaphore", "release", "deadlock", "<-sem")),
        ], note="adds `Run`: a bounded pool that keeps results in input order"),
        Slot("first", "FirstError", _B_FIRST, [
            Bad(_B_FIRST.replace("%w", "%v"), "api-misuse", "%v flattens the error, so errors.Is/As on the returned error no longer work", ("%w", "%v", "errors.Is", "wrap")),
            Bad(_B_FIRST.replace("    for _, r := range rs {\n        if r.Err != nil {\n            return fmt.Errorf(\"job %d: %w\", r.Index, r.Err)\n        }\n    }\n    return nil", "    var err error\n    for _, r := range rs {\n        if r.Err != nil {\n            err = fmt.Errorf(\"job %d: %w\", r.Index, r.Err)\n        }\n    }\n    return err"), "logic", "the loop keeps overwriting err, so the *last* failure is returned instead of the first", ("first", "last", "overwrite", "lowest")),
        ], note="adds `FirstError`"),
        Slot("retry", "Retry", _B_RETRY, [
            Bad(_B_RETRY.replace("for n := 0; n < attempts; n++ {", "for n := 0; n <= attempts; n++ {"), "off-by-one", "one attempt too many: the job runs attempts+1 times", ("<=", "attempts", "extra", "off by one")),
            Bad(_B_RETRY.replace("            select {\n            case <-time.After(delay):\n            case <-ctx.Done():\n                return \"\", ctx.Err()\n            }\n", "            time.Sleep(delay)\n"), "api-misuse", "time.Sleep ignores ctx, so cancellation is not noticed until the delay is over", ("time.Sleep", "ctx", "cancel", "select")),
            Bad(_B_RETRY.replace("        return \"\", err\n", "        return \"\", nil\n"), "error-handling", "when every attempt fails the wrapper returns a nil error, hiding the failure", ("nil", "error", "swallow", "return")),
        ], note="adds `Retry`"),
        Slot("timeout", "WithTimeout", _B_TIMEOUT, [
            Bad(_B_TIMEOUT.replace("        ctx, cancel := context.WithTimeout(ctx, d)\n        defer cancel()\n", "        ctx, _ = context.WithTimeout(ctx, d)\n"), "resource-leak", "the cancel function is never called, so the timer and context stay alive until the timeout fires", ("cancel", "defer", "leak", "context")),
            Bad(_B_TIMEOUT.replace("context.WithTimeout(ctx, d)", "context.WithTimeout(context.Background(), d)"), "logic", "the parent context is dropped, so cancelling the caller no longer cancels the job", ("Background", "parent", "ctx", "cancel")),
        ], note="adds `WithTimeout`"),
        Slot("merge", "Merge", _B_MERGE, [
            Bad(_B_MERGE.replace("        in := in\n", ""), "concurrency", "the range variable `in` is shared by all goroutines (go 1.21 semantics), so most inputs are never drained", ("loop variable", "capture", "in := in")),
            Bad(dd('''
                // Merge forwards everything from the inputs to the returned channel, which is closed once every input is closed.
                func Merge(inputs ...<-chan string) <-chan string {
                    out := make(chan string)
                    for _, in := range inputs {
                        in := in
                        go func() {
                            for v := range in {
                                out <- v
                            }
                            close(out)
                        }()
                    }
                    return out
                }
            '''), "concurrency", "every goroutine closes out when its own input ends, so the first to finish makes the others panic with a send on a closed channel", ("close", "closed channel", "panic", "wg.Wait")),
        ], note="adds `Merge` (fan-in)"),
    ],
)

MODULES = [SESSIONS, UPLOADS, BATCH]

from ._traps import apply_traps  # noqa: E402

apply_traps(MODULES)

for _m in MODULES:
    validate_module(_m)
