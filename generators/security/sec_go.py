"""Security family for Go: template escaping, command injection, open redirects, path traversal in handlers and archive extraction, data races."""
from fx import dd, family

from . import _sec
from ._sec import patched, readme

GO = []

VERIFY_RACE = "go test -race -count=1 ./..."


def go_task(slug, d, pkg, product, func, cwe, finding, source, readme_text, solution, test, verify=None, timeout_s=180):
    mod = f"example.com/{pkg}"
    start = {"go.mod": f"module {mod}\n\ngo 1.21\n", f"{pkg}.go": source, "README.md": readme(slug, readme_text)}
    sol = {f"{pkg}.go": solution}
    t = dict(slug=slug, d=d, lang="go", product=product, func=func, cwe=cwe, finding=finding, start=start, solution=sol,
             hidden={f"{pkg}_test.go": dd(test)}, tags=["go"], timeout_s=timeout_s)
    if verify:
        t["verify"] = verify
    return t


# ---------------------------------------------------------------------------------------------------------------------------------
CARD = dd(r'''
    // Package card renders profile cards.
    package card

    import (
    	"bytes"
    	"text/template"
    )

    var cardTemplate = template.Must(template.New("card").Parse(`<div class="card"><h2>{{.Name}}</h2><input value="{{.Name}}"><p>{{.Bio}}</p></div>`))

    // RenderCard returns the HTML of a profile card. Name and bio are plain text typed by users; they must be escaped for the HTML context they are
    // inserted into (element text and attribute value), so that `<script>` or `" onfocus="` in them stays text.
    func RenderCard(name, bio string) (string, error) {
    	var buf bytes.Buffer
    	err := cardTemplate.Execute(&buf, struct{ Name, Bio string }{name, bio})
    	return buf.String(), err
    }
''')
GO.append(go_task("card-template", 1, "card", "the profile cards", "RenderCard", "CWE-79",
                  "`RenderCard` is built on `text/template`, which inserts values verbatim: a display name such as `\"><script>alert(1)</script>` breaks out of the attribute and the element and runs in every visitor's browser.",
                  CARD,
                  "`RenderCard` returns the same markup for the same inputs, with name and bio escaped for their contexts (`html/template` does this automatically). Plain names such as `Ann` come out unchanged; the output of hostile names parses back to exactly the typed text.",
                  patched(CARD, ('"text/template"', '"html/template"')),
                  r'''
    package card

    import (
    	"html"
    	"strings"
    	"testing"
    )

    func between(s, start, end string) string {
    	i := strings.Index(s, start)
    	if i < 0 {
    		return "\x00missing"
    	}
    	i += len(start)
    	j := strings.Index(s[i:], end)
    	if j < 0 {
    		return "\x00missing"
    	}
    	return s[i : i+j]
    }

    func TestPlainText(t *testing.T) {
    	out, err := RenderCard("Ann", "Hi there")
    	if err != nil || out != `<div class="card"><h2>Ann</h2><input value="Ann"><p>Hi there</p></div>` {
    		t.Fatalf("unexpected output %q (%v)", out, err)
    	}
    	out, _ = RenderCard("", "")
    	if out != `<div class="card"><h2></h2><input value=""><p></p></div>` {
    		t.Fatalf("unexpected output %q", out)
    	}
    }

    func TestHostileText(t *testing.T) {
    	for _, s := range []string{`<script>alert(1)</script>`, `"><img src=x onerror=alert(1)>`, `" onfocus="alert(1)`, `'><svg onload=alert(1)>`, `</p><p>forged`, `a & b < c > d`, `&lt;already&gt;`, "café 中文", `O'Neil "the" man`} {
    		out, err := RenderCard(s, s)
    		if err != nil {
    			t.Fatal(err)
    		}
    		if n := strings.Count(out, "<"); n != 7 {
    			t.Errorf("%q: %d tags in %q", s, n, out)
    		}
    		if strings.Count(out, `"`) != 4 {
    			t.Errorf("%q: attribute quotes broken in %q", s, out)
    		}
    		if got := html.UnescapeString(between(out, "<h2>", "</h2>")); got != s {
    			t.Errorf("%q: heading shows %q", s, got)
    		}
    		if got := html.UnescapeString(between(out, `<input value="`, `">`)); got != s {
    			t.Errorf("%q: attribute holds %q", s, got)
    		}
    		if got := html.UnescapeString(between(out, "<p>", "</p>")); got != s {
    			t.Errorf("%q: paragraph shows %q", s, got)
    		}
    	}
    }
    '''))

LABEL = dd(r'''
    // Package label talks to the archive labelling tool.
    package label

    import "os/exec"

    // Label runs the labelling tool (stand-in: `echo archiving <name>`) and returns what it printed. The name reaches the tool as ONE argument, unchanged,
    // whatever characters it contains; no shell is involved.
    func Label(name string) (string, error) {
    	out, err := exec.Command("sh", "-c", "echo archiving "+name).Output()
    	return string(out), err
    }
''')
GO.append(go_task("label-exec", 1, "label", "the archive tool", "Label", "CWE-78",
                  "`Label` hands a shell the string `echo archiving ` plus the archive name: a name like `x; echo INJECTED` or `$(echo INJECTED)` runs extra commands, and names with quotes, `$` or `*` are mangled.",
                  LABEL,
                  "`Label(name)` returns exactly `archiving <name>\\n` for every name: the tool is started directly with the name as a single argument.",
                  patched(LABEL, ('exec.Command("sh", "-c", "echo archiving "+name)', 'exec.Command("echo", "archiving", name)')),
                  r'''
    package label

    import "testing"

    func TestNameIsOneArgument(t *testing.T) {
    	names := []string{"plain", "two words", "it's", `say "hi"`, "$HOME and ${PATH}", "wild * ? [a-z]", "a;b", "x; echo INJECTED", "x && echo INJECTED", "x | echo INJECTED", "$(echo INJECTED)",
    		"`echo INJECTED`", "x\necho INJECTED", "'; echo INJECTED; '", `"; echo INJECTED; "`, "-n", "-e", `back\slash`, "tab\there", "ünïcöde"}
    	for _, name := range names {
    		out, err := Label(name)
    		if err != nil {
    			t.Fatalf("%q: %v", name, err)
    		}
    		if want := "archiving " + name + "\n"; out != want {
    			t.Errorf("%q: got %q, want %q", name, out, want)
    		}
    	}
    }
    '''))

REDIR = dd(r'''
    // Package redirect decides where users are sent after logging in.
    package redirect

    import "strings"

    // Target returns the URL to redirect to after login: `next` when it is a path on this site - it starts with exactly one '/' (`/dashboard`, `/a/b?x=1#frag`,
    // `/search?q=//x`) - and "/" for everything else: absolute URLs, `//host`, `/\host`, other schemes, plain words, control characters (tab, CR, LF and the rest below 0x20 or 0x7f), and the empty string.
    func Target(next string) string {
    	if strings.HasPrefix(next, "/") {
    		return next
    	}
    	return "/"
    }
''')
GO.append(go_task("login-next", 2, "redirect", "the login page", "Target", "CWE-601",
                  "`Target` accepts anything that starts with `/`, so `//evil.io`, `/\\evil.io` and `/\t/evil.io` (browsers read them as links to another site) pass: the login page redirects victims to an attacker's site after they typed their real password.",
                  REDIR,
                  "`Target(next)` returns `next` only for paths with a single leading `/` and no control characters in them; everything else gives `\"/\"`.",
                  patched(REDIR, ('''	if strings.HasPrefix(next, "/") {
		return next
	}
	return "/"
''', '''	if !strings.HasPrefix(next, "/") || strings.HasPrefix(next, "//") || strings.HasPrefix(next, "/\\\\") {
		return "/"
	}
	for _, c := range next {
		if c < 0x20 || c == 0x7f {
			return "/"
		}
	}
	return next
''')),
                  r'''
    package redirect

    import (
    	"strings"
    	"testing"
    )

    func TestLocalPaths(t *testing.T) {
    	for _, p := range []string{"/dashboard", "/a/b?x=1&y=2#frag", "/search?q=//x", "/", "/a//b", "/~user/page", "/%2F/not-a-host"} {
    		if got := Target(p); got != p {
    			t.Errorf("Target(%q) = %q", p, got)
    		}
    	}
    }

    func TestOffSite(t *testing.T) {
    	for _, p := range []string{"", "https://evil.io/", "http://evil.io", "//evil.io", "/\\evil.io", "\\\\evil.io", "\\/evil.io", "/\t/evil.io", "///evil.io", "http:evil.io", "javascript:alert(1)", " //evil.io",
    		"evil.io", "data:text/html,x", "/\r\n/evil.io", "/\n/evil.io", "\t//evil.io", "mailto:a@b.c", "dashboard", "/ok\x00bad", "/ok\x7f"} {
    		if got := Target(p); got != "/" {
    			t.Errorf("Target(%q) = %q, want /", p, got)
    		}
    		if strings.HasPrefix(Target(p), "//") {
    			t.Errorf("Target(%q) is protocol-relative", p)
    		}
    	}
    }
    '''))

FILES = dd(r'''
    // Package files serves documents from a directory.
    package files

    import (
    	"net/http"
    	"os"
    	"path/filepath"
    )

    // NewHandler serves files below root: `GET /?file=<relative path>` answers 200 with the file's content. Paths that leave root - `..` climbing, absolute paths, symbolic links that point
    // out - are answered with 400 and no content; an empty `file` parameter is 400 too; files that do not exist are 404.
    func NewHandler(root string) http.Handler {
    	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
    		data, err := os.ReadFile(filepath.Join(root, r.URL.Query().Get("file")))
    		if err != nil {
    			http.Error(w, "not found", http.StatusNotFound)
    			return
    		}
    		w.Write(data)
    	})
    }
''')
GO.append(go_task("file-handler", 2, "files", "the document server", "NewHandler", "CWE-22",
                  "`NewHandler` joins the `file` query parameter onto the document root with `filepath.Join`, which normalises `../` away: `/?file=../../etc/passwd` (or a symlink inside the root) reads files anywhere the server can.",
                  FILES,
                  "`NewHandler` follows its comment: 200 with the content for files that really live below `root` (after resolving symbolic links, `sub/../ok.txt` is fine), 400 for anything that escapes or is empty, 404 for missing files. No content of outside files is ever written to the response.",
                  patched(FILES, ('''	"net/http"
	"os"
	"path/filepath"
)''', '''	"net/http"
	"os"
	"path/filepath"
	"strings"
)'''), ('''		data, err := os.ReadFile(filepath.Join(root, r.URL.Query().Get("file")))
		if err != nil {
			http.Error(w, "not found", http.StatusNotFound)
			return
		}
		w.Write(data)
''', '''		name := r.URL.Query().Get("file")
		realRoot, err := filepath.EvalSymlinks(root)
		if err != nil || name == "" || filepath.IsAbs(name) || strings.ContainsRune(name, 0) {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		target := filepath.Join(realRoot, name)
		if rel, err := filepath.Rel(realRoot, target); err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		real, err := filepath.EvalSymlinks(target)
		if err != nil {
			http.Error(w, "not found", http.StatusNotFound)
			return
		}
		if rel, err := filepath.Rel(realRoot, real); err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		data, err := os.ReadFile(real)
		if err != nil {
			http.Error(w, "not found", http.StatusNotFound)
			return
		}
		w.Write(data)
''')),
                  r'''
    package files

    import (
    	"net/http"
    	"net/http/httptest"
    	"net/url"
    	"os"
    	"path/filepath"
    	"strings"
    	"testing"
    )

    func setup(t *testing.T) (root, base string) {
    	base = t.TempDir()
    	root = filepath.Join(base, "docs")
    	if err := os.MkdirAll(filepath.Join(root, "sub"), 0o755); err != nil {
    		t.Fatal(err)
    	}
    	write := func(p, s string) {
    		if err := os.WriteFile(p, []byte(s), 0o644); err != nil {
    			t.Fatal(err)
    		}
    	}
    	write(filepath.Join(root, "ok.txt"), "ok")
    	write(filepath.Join(root, "sub", "a.txt"), "a")
    	write(filepath.Join(root, "a..b.txt"), "dots")
    	write(filepath.Join(base, "secret.txt"), "SECRET")
    	write(filepath.Join(base, "docs-evil.txt"), "SIBLING")
    	if err := os.Symlink(filepath.Join(base, "secret.txt"), filepath.Join(root, "link.txt")); err != nil {
    		t.Fatal(err)
    	}
    	if err := os.Symlink(filepath.Join(root, "ok.txt"), filepath.Join(root, "inner.txt")); err != nil {
    		t.Fatal(err)
    	}
    	return root, base
    }

    func get(h http.Handler, name string) (int, string) {
    	rec := httptest.NewRecorder()
    	req := httptest.NewRequest("GET", "/?file="+url.QueryEscape(name), nil)
    	h.ServeHTTP(rec, req)
    	return rec.Code, rec.Body.String()
    }

    func TestFilesInsideRoot(t *testing.T) {
    	root, _ := setup(t)
    	h := NewHandler(root)
    	for name, want := range map[string]string{"ok.txt": "ok", "sub/a.txt": "a", "sub/../ok.txt": "ok", "./ok.txt": "ok", "a..b.txt": "dots", "inner.txt": "ok"} {
    		if code, body := get(h, name); code != 200 || body != want {
    			t.Errorf("%q: %d %q", name, code, body)
    		}
    	}
    	if code, _ := get(h, "missing.txt"); code != 404 {
    		t.Errorf("missing file: %d", code)
    	}
    }

    func TestEscapes(t *testing.T) {
    	root, base := setup(t)
    	h := NewHandler(root)
    	for _, name := range []string{"../secret.txt", "sub/../../secret.txt", filepath.Join(base, "secret.txt"), "/etc/hostname", "../docs-evil.txt", "link.txt", "../docs/../secret.txt", "", "..", "sub/../../docs-evil.txt"} {
    		code, body := get(h, name)
    		if code != 400 {
    			t.Errorf("%q: status %d, want 400", name, code)
    		}
    		if strings.Contains(body, "SECRET") || strings.Contains(body, "SIBLING") {
    			t.Errorf("%q leaked %q", name, body)
    		}
    	}
    }
    '''))

EXTRACT = dd(r'''
    // Package extract unpacks archive entries into a directory.
    package extract

    import (
    	"os"
    	"path/filepath"
    )

    // File is one archive entry: a slash-separated relative name (a name ending in "/" is a directory), a mode and the content.
    type File struct {
    	Name string
    	Mode os.FileMode
    	Data []byte
    }

    // Extract writes the entries below dst, creating parent directories as needed (later entries overwrite earlier ones with the same name). Archives are untrusted: an entry whose name would
    // land outside dst (`..` climbing, absolute names, backslashes, NUL bytes, empty names), and any symbolic link entry (Mode has os.ModeSymlink), is an error - and then nothing at all is written,
    // not even the harmless entries before it.
    func Extract(dst string, files []File) error {
    	for _, f := range files {
    		target := filepath.Join(dst, f.Name)
    		if len(f.Name) > 0 && f.Name[len(f.Name)-1] == '/' {
    			if err := os.MkdirAll(target, 0o755); err != nil {
    				return err
    			}
    			continue
    		}
    		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
    			return err
    		}
    		if err := os.WriteFile(target, f.Data, 0o644); err != nil {
    			return err
    		}
    	}
    	return nil
    }
''')
GO.append(go_task("archive-extract", 3, "extract", "the archive importer", "Extract", "CWE-22",
                  "`Extract` joins every entry name onto the destination with `filepath.Join`: an entry called `../../home/user/.bashrc` (zip slip) or `/etc/cron.d/x` is written outside the destination directory, entries are written before later ones are validated, and symlink entries are not refused.",
                  EXTRACT,
                  "`Extract` validates *all* entries first (names must be local, slash-separated, without backslashes or NUL, not empty; no symbolic links) and returns an error without writing anything if one fails; valid archives extract exactly as before, including odd but legal names such as `a..b`, `..hidden` and `./x`.",
                  patched(EXTRACT, ('''import (
	"os"
	"path/filepath"
)''', '''import (
	"errors"
	"os"
	"path/filepath"
	"strings"
)'''), ('''	for _, f := range files {
		target := filepath.Join(dst, f.Name)
		if len(f.Name) > 0''', '''	for _, f := range files {
		if f.Name == "" || strings.ContainsAny(f.Name, "\\\\\\x00") || f.Mode&os.ModeSymlink != 0 || !filepath.IsLocal(filepath.FromSlash(f.Name)) {
			return errors.New("unsafe archive entry: " + f.Name)
		}
	}
	for _, f := range files {
		target := filepath.Join(dst, f.Name)
		if len(f.Name) > 0''')),
                  r'''
    package extract

    import (
    	"os"
    	"path/filepath"
    	"sort"
    	"testing"
    )

    func tree(t *testing.T, root string) []string {
    	var out []string
    	filepath.Walk(root, func(p string, info os.FileInfo, err error) error {
    		if err == nil && p != root {
    			rel, _ := filepath.Rel(root, p)
    			out = append(out, rel)
    		}
    		return nil
    	})
    	sort.Strings(out)
    	return out
    }

    func TestValidArchive(t *testing.T) {
    	base := t.TempDir()
    	dst := filepath.Join(base, "out")
    	os.MkdirAll(dst, 0o755)
    	files := []File{{Name: "a.txt", Data: []byte("A")}, {Name: "dir/", Mode: os.ModeDir}, {Name: "dir/b.txt", Data: []byte("B")}, {Name: "deep/er/c.txt", Data: []byte("C")}, {Name: "a..b", Data: []byte("D")},
    		{Name: "..hidden", Data: []byte("E")}, {Name: "./x.txt", Data: []byte("F")}, {Name: "a.txt", Data: []byte("A2")}, {Name: "dir/../ok.txt", Data: []byte("G")}}
    	if err := Extract(dst, files); err != nil {
    		t.Fatal(err)
    	}
    	for name, want := range map[string]string{"a.txt": "A2", "dir/b.txt": "B", "deep/er/c.txt": "C", "a..b": "D", "..hidden": "E", "x.txt": "F", "ok.txt": "G"} {
    		got, err := os.ReadFile(filepath.Join(dst, name))
    		if err != nil || string(got) != want {
    			t.Errorf("%s: %q %v", name, got, err)
    		}
    	}
    }

    func TestUnsafeEntries(t *testing.T) {
    	base := t.TempDir()
    	bad := []File{{Name: "../evil.txt"}, {Name: "a/../../evil.txt"}, {Name: filepath.Join(base, "abs.txt")}, {Name: "/etc/cron.d/evil"}, {Name: ".."}, {Name: "../"}, {Name: `a\..\evil.txt`}, {Name: "x\x00y"},
    		{Name: ""}, {Name: "link", Mode: os.ModeSymlink, Data: []byte("/etc/passwd")}, {Name: "sub/../../evil.txt"}}
    	for _, b := range bad {
    		dst := filepath.Join(base, "out")
    		os.RemoveAll(dst)
    		os.MkdirAll(dst, 0o755)
    		before := tree(t, base)
    		err := Extract(dst, []File{{Name: "first.txt", Data: []byte("1")}, b, {Name: "last.txt", Data: []byte("2")}})
    		if err == nil {
    			t.Errorf("%q: no error", b.Name)
    		}
    		after := tree(t, base)
    		if len(after) != len(before) {
    			t.Errorf("%q: wrote %v", b.Name, after)
    		}
    		if _, statErr := os.Stat(filepath.Join(dst, "first.txt")); statErr == nil {
    			t.Errorf("%q: the entry before the bad one was written", b.Name)
    		}
    	}
    }
    '''))

STATS = dd(r'''
    // Package stats counts events from many goroutines.
    package stats

    // Stats counts events by name. It is used concurrently: Inc, Get and Snapshot may be called from any number of goroutines at the same time.
    type Stats struct {
    	counts map[string]int
    }

    // New returns an empty Stats.
    func New() *Stats { return &Stats{counts: map[string]int{}} }

    // Inc adds one to the counter called name.
    func (s *Stats) Inc(name string) { s.counts[name]++ }

    // Get returns the counter called name (0 when it was never incremented).
    func (s *Stats) Get(name string) int { return s.counts[name] }

    // Snapshot returns a copy of all counters.
    func (s *Stats) Snapshot() map[string]int {
    	out := make(map[string]int, len(s.counts))
    	for k, v := range s.counts {
    		out[k] = v
    	}
    	return out
    }
''')
GO.append(go_task("stats-race", 3, "stats", "the metrics collector", "Stats", "CWE-362",
                  "`Stats` is called from the request goroutines but guards its map with nothing: concurrent increments are lost, `Snapshot` races with writers, and Go's runtime kills the whole server with `fatal error: concurrent map writes` under load.",
                  STATS,
                  "`Inc`, `Get` and `Snapshot` are safe for concurrent use (the tests run with the race detector): no lost updates, no data races, snapshots are consistent copies. The API stays as it is.",
                  patched(STATS, ('package stats\n', 'package stats\n\nimport "sync"\n'), ('type Stats struct {\n\tcounts map[string]int\n}', 'type Stats struct {\n\tmu     sync.Mutex\n\tcounts map[string]int\n}'),
                          ('func (s *Stats) Inc(name string) { s.counts[name]++ }', 'func (s *Stats) Inc(name string) {\n\ts.mu.Lock()\n\tdefer s.mu.Unlock()\n\ts.counts[name]++\n}'),
                          ('func (s *Stats) Get(name string) int { return s.counts[name] }', 'func (s *Stats) Get(name string) int {\n\ts.mu.Lock()\n\tdefer s.mu.Unlock()\n\treturn s.counts[name]\n}'),
                          ('func (s *Stats) Snapshot() map[string]int {\n', 'func (s *Stats) Snapshot() map[string]int {\n\ts.mu.Lock()\n\tdefer s.mu.Unlock()\n')),
                  r'''
    package stats

    import (
    	"fmt"
    	"sync"
    	"testing"
    )

    func TestSequential(t *testing.T) {
    	s := New()
    	s.Inc("a")
    	s.Inc("a")
    	s.Inc("b")
    	if s.Get("a") != 2 || s.Get("b") != 1 || s.Get("zzz") != 0 {
    		t.Fatalf("wrong counts: %v", s.Snapshot())
    	}
    	snap := s.Snapshot()
    	snap["a"] = 100
    	if s.Get("a") != 2 {
    		t.Fatal("snapshot is not a copy")
    	}
    }

    func TestConcurrentUse(t *testing.T) {
    	s := New()
    	var wg sync.WaitGroup
    	for g := 0; g < 40; g++ {
    		wg.Add(1)
    		go func(g int) {
    			defer wg.Done()
    			for i := 0; i < 250; i++ {
    				s.Inc("total")
    				s.Inc(fmt.Sprintf("worker-%d", g%5))
    				if i%50 == 0 {
    					_ = s.Snapshot()
    					_ = s.Get("total")
    				}
    			}
    		}(g)
    	}
    	wg.Wait()
    	if got := s.Get("total"); got != 10000 {
    		t.Fatalf("lost updates: total = %d", got)
    	}
    	sum := 0
    	for k, v := range s.Snapshot() {
    		if k != "total" {
    			sum += v
    		}
    	}
    	if sum != 10000 {
    		t.Fatalf("per-worker counters add up to %d", sum)
    	}
    }
    ''', verify=VERIFY_RACE))

ORDER = ["card-template", "label-exec", "login-next", "file-handler", "archive-extract", "stats-race"]
GO.sort(key=lambda s: (s["d"], ORDER.index(s["slug"])))


@family("security-go", category="security", lang="go", kind="fix", n=6,
        summary="Go: html/template escaping, command injection, open redirects, path traversal in handlers and archive extraction, data races")
def gen_go(rng, n):
    return list(_sec.emit(rng, GO[:n], tags=["go"]))
