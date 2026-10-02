"""Error propagation: swallowed errors, lost causes, missing rollbacks (python importer) and wrapped errors (go config loader)."""
from fx import dd, family, langs
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): a transactional batch importer with retries.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # importer

    Loads a batch of product records into a sink inside one transaction.

    ## `importer.batch.import_batch(records, sink, attempts=3)`
    A record is a dict that must have `id`, `name` and `qty`. The batch runs in a transaction (`sink.begin()` ...
    `sink.commit()`).

    * An invalid record (a missing field, or `qty` that is not a non-negative integer) is **rejected**: it is listed in
      `report["rejected"]` as `(index, message)` (0-based position in the batch, message from `validate`) and the batch
      carries on. A record without an `id`, `name` or `qty` must never raise anything but a rejection.
    * Inserting uses `call_with_retry(..., attempts, SinkError)`: a `SinkError` is retried up to `attempts` times in
      total; when the last attempt fails the **last** error is raised. Other exceptions are not retried.
    * Any `SinkError` that gets out (retries exhausted, or `commit` failing) aborts the batch: the transaction is
      rolled back (`sink.rollback()`, exactly once) and `ImportAborted` is raised **from** the original error (its
      `__cause__` is that `SinkError`), with the partial `report` attached as `.report` and a message that names where
      it stopped: `record <index>` or `commit`.
    * On success the transaction is committed and `{"inserted": n, "rejected": [...]}` is returned.
''')

A_ERRORS = dd('''
    class ValidationError(ValueError):
        pass


    class SinkError(Exception):
        """The sink refused or lost a write."""


    class ImportAborted(Exception):
        def __init__(self, message, report):
            super().__init__(message)
            self.report = report
''')

A_SINK = dd('''
    from .errors import SinkError


    class MemorySink:
        """A transactional in-memory sink with failure injection for tests."""

        def __init__(self, fail_on=(), flaky=None, fail_commit=False):
            self.rows = []
            self._pending = None
            self.fail_on = set(fail_on)
            self.flaky = dict(flaky or {})  # id -> number of attempts that fail before one succeeds
            self.fail_commit = fail_commit
            self.commits = 0
            self.rollbacks = 0

        def begin(self):
            if self._pending is not None:
                raise SinkError("transaction already open")
            self._pending = []

        def insert(self, rec):
            rid = rec["id"]
            if rid in self.fail_on:
                raise SinkError(f"sink refused {rid}")
            if self.flaky.get(rid, 0) > 0:
                self.flaky[rid] -= 1
                raise SinkError(f"transient failure on {rid}")
            self._pending.append(dict(rec))

        def commit(self):
            if self.fail_commit:
                raise SinkError("commit failed")
            self.rows.extend(self._pending)
            self._pending = None
            self.commits += 1

        def rollback(self):
            self._pending = None
            self.rollbacks += 1
''')

A_VALIDATE = dd('''
    from .errors import ValidationError

    REQUIRED = ("id", "name", "qty")


    def validate(rec):
        for field in REQUIRED:
            if field not in rec:
                raise ValidationError(f"missing field: {field}")
        qty = rec["qty"]
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 0:
            raise ValidationError("qty must be a non-negative integer")
        return rec
''')

A_RETRY = dd('''
    def call_with_retry(fn, attempts, retry_on):
        last = None
        for _ in range(attempts):
            try:
                return fn()
            except retry_on as exc:
                last = exc
        raise last
''')

A_BATCH = dd('''
    from .errors import ImportAborted, SinkError, ValidationError
    from .retry import call_with_retry
    from .validate import validate


    def import_batch(records, sink, attempts=3):
        report = {"inserted": 0, "rejected": []}
        sink.begin()
        position = "commit"
        try:
            for index, rec in enumerate(records):
                position = f"record {index}"
                try:
                    validate(rec)
                except ValidationError as exc:
                    report["rejected"].append((index, str(exc)))
                    continue
                call_with_retry(lambda: sink.insert(rec), attempts, SinkError)
                report["inserted"] += 1
            position = "commit"
            sink.commit()
        except SinkError as exc:
            sink.rollback()
            raise ImportAborted(f"import aborted at {position}: {exc}", report) from exc
        return report
''')

A_VISIBLE = {
    "tests/test_import.py": dd('''
        import unittest

        from importer.batch import import_batch
        from importer.sink import MemorySink


        def rec(i, qty=1):
            return {"id": f"p{i}", "name": f"product {i}", "qty": qty}


        class HappyPath(unittest.TestCase):
            def test_inserts_everything(self):
                sink = MemorySink()
                report = import_batch([rec(1), rec(2), rec(3)], sink)
                self.assertEqual(report, {"inserted": 3, "rejected": []})
                self.assertEqual([r["id"] for r in sink.rows], ["p1", "p2", "p3"])

            def test_rejects_a_bad_quantity(self):
                sink = MemorySink()
                report = import_batch([rec(1), rec(2, qty=-4)], sink)
                self.assertEqual(report["inserted"], 1)
                self.assertEqual(report["rejected"], [(1, "qty must be a non-negative integer")])


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_import.py": dd('''
        import unittest

        from importer.batch import import_batch
        from importer.errors import ImportAborted, SinkError
        from importer.retry import call_with_retry
        from importer.sink import MemorySink


        def rec(name, qty=1):
            return {"id": name, "name": f"product {name}", "qty": qty}


        class Rejections(unittest.TestCase):
            def test_missing_fields_are_rejections_not_crashes(self):
                sink = MemorySink()
                batch = [rec("a"), {"name": "no id", "qty": 1}, {"id": "c", "qty": 2}, {"id": "d", "name": "x"}, {}, rec("f")]
                report = import_batch(batch, sink)
                self.assertEqual(report["inserted"], 2)
                self.assertEqual(report["rejected"], [(1, "missing field: id"), (2, "missing field: name"), (3, "missing field: qty"), (4, "missing field: id")])
                self.assertEqual([r["id"] for r in sink.rows], ["a", "f"])
                self.assertEqual((sink.commits, sink.rollbacks), (1, 0))

            def test_quantity_rules(self):
                sink = MemorySink()
                report = import_batch([rec("a", 0), rec("b", -1), rec("c", 2.5), rec("d", "7"), rec("e", True)], sink)
                self.assertEqual(report["inserted"], 1)
                self.assertEqual([i for i, _ in report["rejected"]], [1, 2, 3, 4])


        class Aborts(unittest.TestCase):
            def test_refused_record_aborts_and_rolls_back(self):
                sink = MemorySink(fail_on={"c"})
                with self.assertRaises(ImportAborted) as cm:
                    import_batch([rec("a"), rec("b"), rec("c"), rec("d")], sink)
                exc = cm.exception
                self.assertIsInstance(exc.__cause__, SinkError)
                self.assertIn("sink refused c", str(exc.__cause__))
                self.assertIn("record 2", str(exc))
                self.assertEqual(exc.report["inserted"], 2)
                self.assertEqual(sink.rows, [])
                self.assertEqual((sink.commits, sink.rollbacks), (0, 1))

            def test_the_sink_is_usable_again_after_an_abort(self):
                sink = MemorySink(fail_on={"c"})
                with self.assertRaises(ImportAborted):
                    import_batch([rec("a"), rec("c")], sink)
                report = import_batch([rec("x"), rec("y")], sink)
                self.assertEqual(report["inserted"], 2)
                self.assertEqual([r["id"] for r in sink.rows], ["x", "y"])

            def test_failing_commit_aborts_too(self):
                sink = MemorySink(fail_commit=True)
                with self.assertRaises(ImportAborted) as cm:
                    import_batch([rec("a")], sink)
                self.assertIsInstance(cm.exception.__cause__, SinkError)
                self.assertIn("commit", str(cm.exception))
                self.assertEqual((sink.rows, sink.rollbacks), ([], 1))

            def test_empty_batch_commit_failure(self):
                sink = MemorySink(fail_commit=True)
                with self.assertRaises(ImportAborted) as cm:
                    import_batch([], sink)
                self.assertIn("commit", str(cm.exception))
                self.assertEqual(sink.rollbacks, 1)


        class Retries(unittest.TestCase):
            def test_flaky_record_is_retried(self):
                sink = MemorySink(flaky={"b": 2})
                report = import_batch([rec("a"), rec("b"), rec("c")], sink, attempts=3)
                self.assertEqual(report["inserted"], 3)
                self.assertEqual([r["id"] for r in sink.rows], ["a", "b", "c"])

            def test_exhausted_retries_abort_the_batch(self):
                sink = MemorySink(flaky={"b": 3})
                with self.assertRaises(ImportAborted) as cm:
                    import_batch([rec("a"), rec("b"), rec("c")], sink, attempts=3)
                self.assertIn("record 1", str(cm.exception))
                self.assertEqual(sink.rows, [])
                self.assertEqual(sink.rollbacks, 1)

            def test_call_with_retry_raises_the_last_error_itself(self):
                errors = [SinkError("one"), SinkError("two"), SinkError("three")]
                calls = []

                def fn():
                    calls.append(1)
                    raise errors[len(calls) - 1]

                with self.assertRaises(SinkError) as cm:
                    call_with_retry(fn, 3, SinkError)
                self.assertIs(cm.exception, errors[2])
                self.assertEqual(len(calls), 3)

            def test_call_with_retry_returns_the_value_and_ignores_other_errors(self):
                state = {"n": 0}

                def fn():
                    state["n"] += 1
                    if state["n"] < 3:
                        raise SinkError("again")
                    return "done"

                self.assertEqual(call_with_retry(fn, 5, SinkError), "done")
                self.assertEqual(state["n"], 3)
                hits = []

                def boom():
                    hits.append(1)
                    raise KeyError("not retried")

                with self.assertRaises(KeyError):
                    call_with_retry(boom, 5, SinkError)
                self.assertEqual(len(hits), 1)


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["swallowed"] = (
        "Ops found 40 products missing after last night's catalog import that reported success with a handful of rejections. "
        "The sink had been down for a few seconds in the middle of the batch. According to the README a sink failure must abort "
        "the whole import and roll it back; here it seems to have been treated like a bad record. Find out why."
    )
    p["no-rollback"] = lambda c: (
        "After a failed import (sink refused a record) the next import on the same connection dies with "
        + (c.bad_run("from importer.batch import import_batch\nfrom importer.errors import ImportAborted\nfrom importer.sink import MemorySink\n"
                     "s = MemorySink(fail_on={'c'})\ntry:\n    import_batch([{'id': 'a', 'name': 'x', 'qty': 1}, {'id': 'c', 'name': 'y', 'qty': 1}], s)\n"
                     "except ImportAborted:\n    pass\nimport_batch([{'id': 'x', 'name': 'x', 'qty': 1}], s)\n").splitlines() or ["?"])[-1]
        + ". A failed batch must leave the sink clean; it does not seem to be rolled back."
    )
    p["lost-cause"] = (
        "Our alerting groups failures by the exception behind an `ImportAborted`, and since last month they all show up as "
        "\"unknown cause\". The message text is fine but `__cause__` is empty, so the SinkError details never reach the logs. "
        "The README says the abort is raised *from* the original error."
    )
    p["retry-silent"] = (
        "Silent data loss: when the sink is flaky for longer than our retry budget, the import reports every record as "
        "inserted and commits, but the rows are not there. I'd expect the batch to abort when the retries run out. "
        "Look at the retry helper."
    )
    p["keyerror"] = lambda c: (
        "A single malformed line in a supplier's file kills the whole import with a raw traceback instead of a rejection:\n\n```\n"
        + "\n".join((c.bad_run("from importer.batch import import_batch\nfrom importer.sink import MemorySink\n"
                             "import_batch([{'name': 'no id', 'qty': 1}], MemorySink())\n").splitlines() or ["?"])[-5:])
        + "\n```\n\nRecords with missing fields are supposed to be listed as rejected and skipped."
    )
    p["retry-and-rollback"] = (
        "Two symptoms in the importer that I believe have different causes. (1) Our flaky-sink replay harness no longer sees "
        "any aborted imports even when the sink fails every write, but the row counts are wrong. (2) When the final "
        "commit fails, the next import on that connection fails with 'transaction already open'. Both used to work "
        "and the visible tests never exercise failures. Please find what is wrong in each place."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "importer/__init__.py": '"""Batch importer."""\n', "importer/errors.py": A_ERRORS,
            "importer/sink.py": A_SINK, "importer/validate.py": A_VALIDATE, "importer/retry.py": A_RETRY, "importer/batch.py": A_BATCH}
    b, v, r = "importer/batch.py", "importer/validate.py", "importer/retry.py"
    no_rb = ("        sink.rollback()\n        raise ImportAborted(", "        raise ImportAborted(")
    retry_bug = ("    raise last\n", "    return None\n")
    bugs = [
        Bug("sink-error-treated-as-rejection", 3, {b: [(
            "            try:\n                validate(rec)\n            except ValidationError as exc:\n                report[\"rejected\"].append((index, str(exc)))\n                continue\n            call_with_retry(lambda: sink.insert(rec), attempts, SinkError)\n            report[\"inserted\"] += 1\n",
            "            try:\n                validate(rec)\n                call_with_retry(lambda: sink.insert(rec), attempts, SinkError)\n            except Exception as exc:\n                report[\"rejected\"].append((index, str(exc)))\n                continue\n            report[\"inserted\"] += 1\n")]}, P["swallowed"]),
        Bug("abort-without-rollback", 2, {b: [no_rb]}, P["no-rollback"]),
        Bug("cause-dropped", 1, {b: [('", report) from exc', '", report)')]}, P["lost-cause"]),
        Bug("retry-returns-none", 3, {r: [retry_bug]}, P["retry-silent"]),
        Bug("missing-field-keyerror", 3, {v: [("    for field in REQUIRED:\n        if field not in rec:\n            raise ValidationError(f\"missing field: {field}\")\n    qty = rec[\"qty\"]\n",
                                               "    rec[\"id\"], rec[\"name\"]\n    qty = rec[\"qty\"]\n")]}, P["keyerror"]),
        Bug("retry-silent-and-no-rollback", 5, {r: [retry_bug], b: [no_rb]}, P["retry-and-rollback"]),
    ]
    return Base("importer", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (go): a layered configuration loader with includes and wrapped errors.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # confload

    Reads a configuration file and the files it includes from a small read-only file system interface.

    * Lines are `key = value`, `include <path>`, blank, or `#` comments. Keys are lower case: a letter followed by
      letters, digits, `_`, `.` or `-`. A key may appear only once per file.
    * `Parse(text)` returns the entries in file order, or a `*ParseError` (1-based `Line`) for the first bad line:
      a missing `=`, an empty or invalid key, a duplicate key. A parse of valid text returns a **nil** error.
    * `Load(fsys, path)` expands includes depth first at the position of the include line; a later setting overrides an
      earlier one.
    * Errors always wrap their cause so `errors.Is` and `errors.As` work through every layer:
      * the entry file is missing: the error wraps `ErrNoConfig`;
      * an included file is missing or invalid: an `*IncludeError` whose `File` is the file that contains the
        include line, wrapping the underlying error (`fs.ErrNotExist`, or the `*ParseError`);
      * files that include each other in a loop: the error wraps `ErrCycle`. A file that is included from several
        places (a diamond) is **not** a cycle.
''')

B_ERRORS = dd('''
    package confload

    import (
    	"errors"
    	"fmt"
    )

    var (
    	ErrNoConfig = errors.New("configuration file not found")
    	ErrCycle    = errors.New("include cycle")
    )

    // ParseError is a syntax problem on a line (1-based).
    type ParseError struct {
    	Line int
    	Msg  string
    }

    func (e *ParseError) Error() string { return fmt.Sprintf("line %d: %s", e.Line, e.Msg) }

    // IncludeError says in which file an include failed.
    type IncludeError struct {
    	File string
    	Err  error
    }

    func (e *IncludeError) Error() string { return fmt.Sprintf("in %s: %v", e.File, e.Err) }

    func (e *IncludeError) Unwrap() error { return e.Err }
''')

B_FSYS = dd('''
    package confload

    import "io/fs"

    // FS is the read-only file system the loader uses.
    type FS interface {
    	ReadFile(name string) ([]byte, error)
    }

    // MemFS is an in-memory FS.
    type MemFS map[string]string

    func (m MemFS) ReadFile(name string) ([]byte, error) {
    	text, ok := m[name]
    	if !ok {
    		return nil, &fs.PathError{Op: "open", Path: name, Err: fs.ErrNotExist}
    	}
    	return []byte(text), nil
    }
''')

B_PARSE = dd('''
    package confload

    import (
    	"fmt"
    	"strings"
    )

    // Entry is one meaningful line of a file.
    type Entry struct {
    	Key, Value string
    	Include    bool
    	Line       int
    }

    func validKey(k string) bool {
    	if k == "" || k[0] < 'a' || k[0] > 'z' {
    		return false
    	}
    	for _, c := range k {
    		ok := c >= 'a' && c <= 'z' || c >= '0' && c <= '9' || c == '_' || c == '.' || c == '-'
    		if !ok {
    			return false
    		}
    	}
    	return true
    }

    func checkKeys(entries []Entry) *ParseError {
    	for _, e := range entries {
    		if !e.Include && !validKey(e.Key) {
    			return &ParseError{Line: e.Line, Msg: fmt.Sprintf("invalid key %q", e.Key)}
    		}
    	}
    	return nil
    }

    // Parse reads the lines of one file.
    func Parse(text string) ([]Entry, error) {
    	var out []Entry
    	seen := map[string]int{}
    	for i, raw := range strings.Split(text, "\\n") {
    		line := strings.TrimSpace(raw)
    		if line == "" || strings.HasPrefix(line, "#") {
    			continue
    		}
    		n := i + 1
    		if rest, ok := strings.CutPrefix(line, "include "); ok {
    			out = append(out, Entry{Value: strings.TrimSpace(rest), Include: true, Line: n})
    			continue
    		}
    		key, value, ok := strings.Cut(line, "=")
    		if !ok {
    			return nil, &ParseError{Line: n, Msg: "expected key = value"}
    		}
    		key, value = strings.TrimSpace(key), strings.TrimSpace(value)
    		if key == "" {
    			return nil, &ParseError{Line: n, Msg: "empty key"}
    		}
    		if first, dup := seen[key]; dup {
    			return nil, &ParseError{Line: n, Msg: fmt.Sprintf("duplicate key %q (first on line %d)", key, first)}
    		}
    		seen[key] = n
    		out = append(out, Entry{Key: key, Value: value, Line: n})
    	}
    	if perr := checkKeys(out); perr != nil {
    		return nil, perr
    	}
    	return out, nil
    }
''')

B_LOAD = dd('''
    package confload

    import (
    	"errors"
    	"fmt"
    	"io/fs"
    )

    // Config is the effective settings.
    type Config map[string]string

    // Load reads path and everything it includes.
    func Load(fsys FS, path string) (Config, error) {
    	cfg := Config{}
    	if err := load(fsys, path, cfg, map[string]bool{}, ""); err != nil {
    		return nil, err
    	}
    	return cfg, nil
    }

    func load(fsys FS, path string, cfg Config, active map[string]bool, includer string) error {
    	if active[path] {
    		return fmt.Errorf("%s: %w", path, ErrCycle)
    	}
    	data, err := fsys.ReadFile(path)
    	if err != nil {
    		if errors.Is(err, fs.ErrNotExist) {
    			if includer == "" {
    				return fmt.Errorf("load %s: %w", path, ErrNoConfig)
    			}
    			return &IncludeError{File: includer, Err: fmt.Errorf("include %s: %w", path, err)}
    		}
    		return fmt.Errorf("load %s: %w", path, err)
    	}
    	entries, err := Parse(string(data))
    	if err != nil {
    		wrapped := fmt.Errorf("load %s: %w", path, err)
    		if includer != "" {
    			return &IncludeError{File: includer, Err: wrapped}
    		}
    		return wrapped
    	}
    	active[path] = true
    	defer delete(active, path)
    	for _, e := range entries {
    		if e.Include {
    			if err := load(fsys, e.Value, cfg, active, path); err != nil {
    				return err
    			}
    			continue
    		}
    		cfg[e.Key] = e.Value
    	}
    	return nil
    }
''')

B_VISIBLE = {
    "confload_test.go": dd('''
        package confload

        import "testing"

        func TestLoadSimple(t *testing.T) {
        	cfg, err := Load(MemFS{"app.conf": "a = 1\\nb = two\\n"}, "app.conf")
        	if err != nil {
        		t.Fatal(err)
        	}
        	if cfg["a"] != "1" || cfg["b"] != "two" {
        		t.Fatalf("got %v", cfg)
        	}
        }

        func TestIncludeOverrides(t *testing.T) {
        	fsys := MemFS{"app.conf": "a = 1\\ninclude base.conf\\n", "base.conf": "a = 0\\nc = 9\\n"}
        	cfg, err := Load(fsys, "app.conf")
        	if err != nil {
        		t.Fatal(err)
        	}
        	if cfg["a"] != "0" || cfg["c"] != "9" {
        		t.Fatalf("got %v", cfg)
        	}
        }
    '''),
}

B_HIDDEN = {
    "confload_hidden_test.go": dd('''
        package confload

        import (
        	"errors"
        	"io/fs"
        	"reflect"
        	"strings"
        	"testing"
        )

        func TestParseValidTextReturnsNilError(t *testing.T) {
        	entries, err := Parse("a = 1\\n# note\\n\\nb.c-d = x y\\n")
        	if err != nil {
        		t.Fatalf("unexpected error %v", err)
        	}
        	if len(entries) != 2 || entries[1].Key != "b.c-d" || entries[1].Value != "x y" || entries[1].Line != 4 {
        		t.Fatalf("entries %+v", entries)
        	}
        	entries, err = Parse("")
        	if err != nil || len(entries) != 0 {
        		t.Fatalf("empty text: %v %v", entries, err)
        	}
        }

        func TestParseErrors(t *testing.T) {
        	cases := []struct {
        		text string
        		line int
        		sub  string
        	}{
        		{"a = 1\\nnovalue\\n", 2, "expected key = value"},
        		{"# c\\n = 5\\n", 2, "empty key"},
        		{"a = 1\\nb = 2\\na = 3\\n", 3, "duplicate key"},
        		{"Bad = 1\\n", 1, "invalid key"},
        		{"9lives = 1\\n", 1, "invalid key"},
        		{"ok = 1\\nsp ace = 2\\n", 2, "invalid key"},
        	}
        	for _, c := range cases {
        		_, err := Parse(c.text)
        		var pe *ParseError
        		if !errors.As(err, &pe) {
        			t.Errorf("Parse(%q): want *ParseError, got %v", c.text, err)
        			continue
        		}
        		if pe.Line != c.line || !strings.Contains(pe.Msg, c.sub) {
        			t.Errorf("Parse(%q): got line %d %q, want line %d %q", c.text, pe.Line, pe.Msg, c.line, c.sub)
        		}
        	}
        }

        func TestLoadValidFileReturnsNilError(t *testing.T) {
        	cfg, err := Load(MemFS{"app.conf": "a = 1\\n"}, "app.conf")
        	if err != nil || cfg["a"] != "1" {
        		t.Fatalf("got %v, %v", cfg, err)
        	}
        }

        func TestIncludeOrderAndNesting(t *testing.T) {
        	fsys := MemFS{
        		"app.conf":  "a = 1\\ninclude mid.conf\\nb = 2\\n",
        		"mid.conf":  "a = 5\\nc = 5\\ninclude deep.conf\\nd = 5\\n",
        		"deep.conf": "d = 0\\ne = 0\\nc = 0\\n",
        	}
        	cfg, err := Load(fsys, "app.conf")
        	if err != nil {
        		t.Fatal(err)
        	}
        	want := Config{"a": "5", "b": "2", "c": "0", "d": "5", "e": "0"}
        	if !reflect.DeepEqual(cfg, want) {
        		t.Fatalf("got %v want %v", cfg, want)
        	}
        }

        func TestMissingEntryFile(t *testing.T) {
        	_, err := Load(MemFS{}, "app.conf")
        	if !errors.Is(err, ErrNoConfig) {
        		t.Fatalf("errors.Is(err, ErrNoConfig) is false for %v", err)
        	}
        	if !strings.Contains(err.Error(), "app.conf") {
        		t.Fatalf("message does not name the file: %v", err)
        	}
        }

        func TestMissingInclude(t *testing.T) {
        	fsys := MemFS{"app.conf": "a = 1\\ninclude gone.conf\\n"}
        	_, err := Load(fsys, "app.conf")
        	var ie *IncludeError
        	if !errors.As(err, &ie) {
        		t.Fatalf("want *IncludeError, got %v", err)
        	}
        	if ie.File != "app.conf" {
        		t.Fatalf("IncludeError.File = %q, want the including file app.conf", ie.File)
        	}
        	if !errors.Is(err, fs.ErrNotExist) {
        		t.Fatalf("fs.ErrNotExist is not reachable from %v", err)
        	}
        	if errors.Is(err, ErrNoConfig) {
        		t.Fatalf("a missing include is not a missing entry file: %v", err)
        	}
        	if !strings.Contains(err.Error(), "gone.conf") {
        		t.Fatalf("message does not name the missing file: %v", err)
        	}
        }

        func TestParseErrorInsideInclude(t *testing.T) {
        	fsys := MemFS{"app.conf": "include one.conf\\n", "one.conf": "a = 1\\nbroken\\n"}
        	_, err := Load(fsys, "app.conf")
        	var ie *IncludeError
        	var pe *ParseError
        	if !errors.As(err, &ie) || !errors.As(err, &pe) {
        		t.Fatalf("want IncludeError and ParseError, got %v", err)
        	}
        	if ie.File != "app.conf" || pe.Line != 2 {
        		t.Fatalf("File=%q Line=%d", ie.File, pe.Line)
        	}
        }

        func TestParseErrorInEntryFile(t *testing.T) {
        	_, err := Load(MemFS{"app.conf": "x\\n"}, "app.conf")
        	var pe *ParseError
        	var ie *IncludeError
        	if !errors.As(err, &pe) || errors.As(err, &ie) {
        		t.Fatalf("want a bare ParseError, got %v", err)
        	}
        }

        func TestCycles(t *testing.T) {
        	_, err := Load(MemFS{"a.conf": "include b.conf\\n", "b.conf": "include a.conf\\n"}, "a.conf")
        	if !errors.Is(err, ErrCycle) {
        		t.Fatalf("a<->b: got %v", err)
        	}
        	_, err = Load(MemFS{"a.conf": "include a.conf\\n"}, "a.conf")
        	if !errors.Is(err, ErrCycle) {
        		t.Fatalf("self include: got %v", err)
        	}
        }

        func TestDiamondIsNotACycle(t *testing.T) {
        	fsys := MemFS{
        		"app.conf":    "include left.conf\\ninclude right.conf\\n",
        		"left.conf":   "l = 1\\ninclude shared.conf\\n",
        		"right.conf":  "r = 2\\ninclude shared.conf\\n",
        		"shared.conf": "s = 3\\n",
        	}
        	cfg, err := Load(fsys, "app.conf")
        	if err != nil {
        		t.Fatalf("diamond rejected: %v", err)
        	}
        	want := Config{"l": "1", "r": "2", "s": "3"}
        	if !reflect.DeepEqual(cfg, want) {
        		t.Fatalf("got %v", cfg)
        	}
        }

        func TestSameFileIncludedTwiceInARow(t *testing.T) {
        	fsys := MemFS{"app.conf": "include s.conf\\ninclude s.conf\\n", "s.conf": "k = v\\n"}
        	cfg, err := Load(fsys, "app.conf")
        	if err != nil || cfg["k"] != "v" {
        		t.Fatalf("got %v, %v", cfg, err)
        	}
        }
    '''),
}


def _b_prompts():
    p = {}
    p["verb-not-w"] = lambda c: (
        "Our wrapper script that falls back to the built-in defaults when the config file is absent has stopped working: "
        "`errors.Is(err, confload.ErrNoConfig)` is false although the message still says "
        "\"configuration file not found\". This is what the CI job prints for the reproduction:\n\n```\n"
        + c.visible_out() + "\n```\n"
    )
    p["typed-nil"] = (
        "Since the key-name check was added every config file fails to load, even a one-line `a = 1`, with an error whose message "
        "is a nil-pointer panic text or just `<nil>`. Syntax errors are reported fine. The check itself is correct; "
        "something about how its result is returned is off."
    )
    p["no-unwrap"] = (
        "When an included file is missing we can no longer tell \"file not found\" from other failures in the caller "
        "(`errors.Is(err, fs.ErrNotExist)` is false) and `errors.As` cannot get at the `*ParseError` of a broken included "
        "file, so the editor integration cannot jump to the offending line. Top-level files work."
    )
    p["diamond"] = (
        "A config tree where two profile files both include a shared `limits.conf` is rejected with an \"include cycle\" error, "
        "although nothing includes itself. The README says a file may be included from several places."
    )
    p["wrong-file"] = (
        "The error for a missing include names the wrong file in `IncludeError.File`: our editor shows the squiggle in the "
        "file that is missing instead of in the file that contains the `include` line."
    )
    p["two-wrapping"] = (
        "Two reports from the tooling team about error wrapping in confload: (1) `errors.Is(err, fs.ErrNotExist)` does not "
        "see through an `*IncludeError`, (2) a shared include (diamond) is reported as a cycle. They may be one problem or "
        "two. Please make the error behaviour match the README everywhere."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "go.mod": langs.go_mod("confload"), "errors.go": B_ERRORS, "fsys.go": B_FSYS, "parse.go": B_PARSE, "load.go": B_LOAD}
    rep = {"reported_test.go": dd('''
        package confload

        import (
        	"errors"
        	"testing"
        )

        func TestMissingEntryFileIsErrNoConfig(t *testing.T) {
        	_, err := Load(MemFS{}, "app.conf")
        	if !errors.Is(err, ErrNoConfig) {
        		t.Fatalf("errors.Is(err, ErrNoConfig) = false; err = %v", err)
        	}
        }
    ''')}
    ld, ps, er = "load.go", "parse.go", "errors.go"
    nounwrap = ("\nfunc (e *IncludeError) Unwrap() error { return e.Err }\n", "")
    diamond = ("\tactive[path] = true\n\tdefer delete(active, path)\n", "\tactive[path] = true\n")
    bugs = [
        Bug("missing-file-not-wrapped", 1, {ld: [('return fmt.Errorf("load %s: %w", path, ErrNoConfig)', 'return fmt.Errorf("load %s: %v", path, ErrNoConfig)')]},
            P["verb-not-w"], reported=rep),
        Bug("include-error-names-wrong-file", 2, {ld: [("return &IncludeError{File: includer, Err: fmt.Errorf(\"include %s: %w\", path, err)}",
                                                      "return &IncludeError{File: path, Err: fmt.Errorf(\"include %s: %w\", path, err)}")]}, P["wrong-file"]),
        Bug("typed-nil-error", 3, {ps: [("\tif perr := checkKeys(out); perr != nil {\n\t\treturn nil, perr\n\t}\n\treturn out, nil\n",
                                         "\tvar err error = checkKeys(out)\n\treturn out, err\n")]}, P["typed-nil"]),
        Bug("include-error-cannot-unwrap", 3, {er: [nounwrap]}, P["no-unwrap"]),
        Bug("diamond-reported-as-cycle", 4, {ld: [diamond]}, P["diamond"]),
        Bug("no-unwrap-and-diamond", 5, {er: [nounwrap], ld: [diamond]}, P["two-wrapping"]),
    ]
    return Base("confload", "go", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-error-flow", category="fix", lang="python", kind="fix", n=12,
        summary="swallowed errors, lost causes, missing rollbacks (python importer) and broken error wrapping (go config loader)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
