"""project-trials: a fixture-based test runner for suites written in a small invented format: scoped fixtures with dependencies, exact setup and
teardown ordering, parametrised tests, retries, timeouts on a virtual clock, skip/xfail marks, and a precise report.  Reference: Python (oracle)
and JavaScript."""
from __future__ import annotations

from fx import family

from generators.project import _kit as K

THEME = "trials"
TOOLS = ["trials", "assayer", "proving", "probatio", "touchstone", "crucible", "litmus", "bench"]
FX_NAMES = ["db", "cache", "session", "user", "config", "queue", "tmpdir", "clock", "tenant", "token", "mailer", "schema"]
TEST_NAMES = ["login", "logout", "save", "load", "refund", "export", "import", "sync", "audit", "render", "parse", "route", "index", "merge", "expire", "notify"]
MODULES = ["auth", "billing", "storage", "web", "jobs"]
WORDS = ["opened", "ready", "closed", "warm", "cold", "seeded", "bound", "released", "checked"]
VALUES = ["alice", "bob", "42", "7", "blue", "x1", "0", "100", "ok"]

PLAN = [
    dict(lang="javascript", timeout=100, flaky=True, skipslow=True, retries=True),
    dict(lang="python", timeout=50, flaky=True, skipslow=False, retries=True),
    dict(lang="javascript", timeout=200, flaky=False, skipslow=True, retries=False),
    dict(lang="python", timeout=80, flaky=True, skipslow=True, retries=True),
    dict(lang="javascript", timeout=30, flaky=False, skipslow=False, retries=True),
    dict(lang="python", timeout=150, flaky=True, skipslow=True, retries=False),
    dict(lang="javascript", timeout=60, flaky=True, skipslow=False, retries=False),
    dict(lang="python", timeout=120, flaky=False, skipslow=True, retries=True),
]

VOICES = [
    "We need a small test runner for suites written in a home-made format: fixtures with scopes and dependencies, parametrised tests, marks, retries, a virtual clock. `README.md` specifies the file format and *exactly* what the runner prints, down to the order of setup and teardown lines. The program is `{tool}`; write it in {Lang}: {run}. Visible examples: `python3 tests/run_examples.py`.",
    "build {tool} per README.md ({Lang}). fixture-based test runner reading suite.txt in the working dir. {run}. getting setup/teardown order right for test, module and session scopes (and what happens when a setup or teardown fails) is the main difficulty. examples: `python3 tests/run_examples.py`",
    "Ticket TST-{num}: implement the `{tool}` runner (spec: README.md).\n\nLanguage: {Lang}; the program is {run}. All output lines are part of the contract (module headers, setup/teardown events, step logs, result lines, summary, clock). Exit status is 1 when any test failed, errored, timed out or unexpectedly passed.",
    "Could you write the test runner described in README.md? It reads `suite.txt`, resolves fixtures by name and scope, runs the tests and prints a report. {Lang} please; the program is {run}. `python3 tests/run_examples.py` shows a few runs; the hidden checks use many different suites and options.",
    "Greenfield in {Lang}: `{tool}`, a mini test framework. The suite format, fixture lifetime rules, retry semantics, xfail handling, option behaviour and every message are in README.md. {run}. Hidden checks are grouped (scopes, failures, retries, marks, options, suite errors, ...) and scored per group.",
    "README.md has the spec for `{tool}`. Please build it in {Lang} ({run}). Details that matter: a failed module-scope setup is *cached* (later tests get the same error without a second setup line), a teardown error only turns a passing test into an error, retries re-create test-scope fixtures, and `--only` filters by the expanded test name. Visible examples: `python3 tests/run_examples.py`.",
    "short version: fixture-based test runner for suite.txt, spec in README.md, {Lang}, name it {tool}. {run}",
    "Please implement the test runner from README.md in {Lang}. Name: `{tool}`. How it is run: {run}. It has to be exact about ordering and about which message each failure gets, since the hidden checks compare whole reports.",
]


def readme(p: dict, tool: str, lang: str, by_name: dict) -> str:
    o: list[str] = []
    w = o.append
    w(f"# {tool}: a fixture-based test runner\n")
    w(f"`{tool}` reads a suite description from `suite.txt` in the current directory, runs its tests with fixtures that are set up and torn down according to their scope, and prints a report. "
      "Nothing real is executed: tests and fixtures consist of *steps* (logging, failing, ticking a virtual clock, comparing fixture values), so the whole behaviour is deterministic and exactly specified.\n")
    w(f"Build and run it as {K.how_to_run(lang, tool)}. The exit status is 1 when a test failed, errored, timed out or unexpectedly passed (see the outcomes), or when an option or the suite is wrong; otherwise 0.\n")
    w("## 1. suite.txt\n")
    w("Lines are split into words at white space; `#` starts a comment; empty lines are skipped (all lines count for line numbers, starting at 1). A line that starts with a space or tab belongs to the block (fixture or test) opened by the last unindented line; "
      "an `module` line closes any block. A **name** is a letter followed by letters, digits and `_`. A **literal** is 1 to 16 characters from `A-Z a-z 0-9 _ . -`.\n")
    w("* `module NAME`: tests declared after it belong to that module (tests before any `module` line belong to the module `main`). The same module may be opened again later; modules are run in the order of their first appearance, each with its tests in file order.")
    w("* `fixture NAME [scope S] [needs A B ...]`: declares a fixture. `S` is `test` (the default), `module` or `session`. The clauses may come in any order, each at most once and with at least one word.")
    w("  Indented lines: `setup STEP`, `teardown STEP` (any number, in order) and `value LITERAL` (the value tests can compare, default `-`).")
    w("* `test NAME [needs A B ...] [marks M ...] [param V ...]`: declares a test; the clauses as above. Indented lines: `step STEP`. A test with `param` values is expanded into one test per value, named `NAME[V]`, in the order of the values; `NAME` itself must be unique among tests.")
    w("\n**Steps.** `log TEXT...` (the rest of the line, words joined with single spaces), `fail TEXT...` (same; empty text means `failed`), `raise NAME`, `tick N` (N is 1 to 5 digits)" +
      (", and in tests only: `expect NAME OP LITERAL` (`OP` is `==`, `!=`, `<` or `>`)" ) + (", `flaky N` (N one digit)" if p["flaky"] else "") + ". `expect` is only allowed in tests" + (", and so is `flaky`" if p["flaky"] else "") + ".\n")
    w("**Errors in the suite** print `error: suite.txt:LINE: MESSAGE` (or `error: cannot read suite.txt`) and stop with status 1; the first in this order wins: while reading line by line: `indented line outside a block`, `unknown fixture line 'W'` / `unknown test line 'W'` (first word of an indented line), "
      "`bad step 'TEXT'` (TEXT: the step's words joined by spaces; also for a `setup`/`teardown` without a step), `bad value`, `unknown directive 'W'`, `bad line` (wrong shape of a declaration, a repeated or empty clause), `bad scope 'S'`, `duplicate fixture 'N'`, `duplicate test 'N'`; "
      "after the whole file: `unknown fixture 'N'` (fixtures first in file order, then tests; reported at the line of the declaration that mentions it), `fixture cycle A -> B -> A` (fixtures in file order; the path starts at the first fixture that repeats), "
      "`fixture 'A' has a wider scope than its dependency 'B'` (a fixture may only need fixtures of the same or a wider scope: `session` is wider than `module`, wider than `test`; checked per fixture in file order, its needs in order).\n")
    w("## 2. Running\n")
    w("**Selection and order.** The expanded tests are filtered by `--only` (below). Modules run in order; a module with no selected test is not mentioned. Output for a run:\n")
    w("```\nmodule NAME\n  ...events of the tests of the module...\nsummary: ...\nclock: N ms\n```")
    w("**Fixture instances.** A fixture is set up *lazily*: when a test needs it. Needing a fixture means needing, first, the fixtures it `needs` (recursively, in order), then itself. A fixture that has an instance is not set up again: a `session` fixture has one instance for the whole run, "
      "a `module` fixture one per module, a `test` fixture one per test attempt. To set up fixture `F`: first set up its needs in order (those without an instance), then print `  setup F` (two spaces), then run its `setup` steps. When all its steps succeed, the instance exists "
      "and is added, in this order, to the list of instances of its scope.\n")
    w("**Step output.** `log TEXT` prints `    log: TEXT` (four spaces). `tick N` adds `N` to the **clock** (all ticks of the run, in fixtures and tests, every attempt) and, in a test, to the test's **ticks**; if a test's ticks exceed " + f"**{p['timeout']}**" + " the test stops at once with outcome `timeout` and the message `timeout after T ms` (`T` = its ticks so far). "
      "`fail TEXT` fails the test (outcome `fail`, message `TEXT`); in a fixture it is a setup or teardown *failure*. `raise NAME` is an `error` with the message `raised NAME` (in tests and fixtures alike). " +
      ("`flaky N`: in the test's `A`th attempt (counting from 1), if `A <= N` the test fails with `flaky failure (attempt A)`. " if p["flaky"] else "") +
      "`expect NAME OP LITERAL` compares the value of fixture `NAME` (`value` of the fixture; only fixtures the test needs, directly or through others, are visible) or the test's own param value (`NAME` = `param` in a parametrised test) with the literal as text (`==`, `!=`); "
      "for `<` and `>` both sides must be integers (an optional `-` and digits), otherwise the comparison is false. A false comparison fails the test with the message `expected NAME OP LITERAL but got VALUE`; an unknown `NAME` is an `error` with `unknown name 'NAME'`.\n")
    w("**A failing setup.** If a step of a fixture's setup fails or raises, the fixture has **no instance** and gets no teardown; the failure is remembered *in its scope*: every later request for that fixture in the same scope instance (the same attempt, module or run) fails again immediately, "
      "without a `setup` line, with the same message. The message is `setup F failed: M` where `M` is the message of the failing step. The test that needed the fixture (directly or through another fixture) does not run its steps: outcome `error` with that message. "
      "Fixtures already set up for the attempt are torn down as usual.\n")
    w("**Teardown.** After the steps of a test attempt (also after a failure, an error or a timeout, and also when setup failed), the test-scope instances created in this attempt are torn down in **reverse order of setup**: for each, print `  teardown F` and run its `teardown` steps. "
      "A teardown step that fails or raises ends the steps of that fixture only, remembers the *first* teardown error `teardown F failed: M`, and the remaining teardowns still run. A remembered teardown error turns an attempt that passed into `error` with that message; it does not change any other outcome. "
      "Module-scope instances are torn down (reverse order of setup, same printing) after the last selected test of the module; session-scope instances at the very end. If such a teardown fails, one line `  ERROR teardown F failed: M` (for the first error of that batch) is printed after the batch and counts as one error in the summary.\n")
    retry = ("`--retries N`: " if p["retries"] else "")
    w("**Test outcomes.** After the attempt(s) a result line is printed (two spaces): `  PASS NAME`, `  FAIL NAME: MESSAGE`, `  ERROR NAME: MESSAGE`, `  TIMEOUT NAME: MESSAGE`, `  SKIP NAME`, `  XFAIL NAME: MESSAGE`, `  XPASS NAME` (the name is the expanded name). "
      "A test marked `skip`" + (" (or marked `slow` when `--skip-slow` is given)" if p["skipslow"] else "") + " is not run at all (no fixtures, no events): `SKIP`. The mark `xfail` turns a final `FAIL` into `XFAIL` (message kept) and a final `PASS` into `XPASS` (an `ERROR` or `TIMEOUT` stays what it is). Other marks have no effect.\n")
    if p["retries"]:
        w("**Retries.** With `--retries N` (0 to 5, default 0) a test whose attempt ends in `fail`, `error` or `timeout` (before the xfail rule) is run again, at most `N` more times: before each repeated attempt the line `  retry K` (`K` = 1, 2, ...) is printed, "
          "then everything happens again from the beginning (test-scope fixtures are set up again; module and session instances stay). Retrying stops at the first attempt that passes. The result line of the test is the last attempt's, with ` [retried K]` appended when `K > 0` (also for a test that still fails).\n")
    w("**Summary.** After all modules (and after the session teardown): `summary: P passed, F failed, E errors, T timeouts, S skipped, X xfailed, U xpassed` (final outcomes, plus the teardown errors counted above), then `clock: N ms`.\n")
    w("## 3. Options\n")
    opts = ["`--only TEXT`: select only the expanded test names that contain `TEXT` as a substring (module names do not count)", "`--fail-fast`: after the result line of a test whose final outcome is `fail`, `error`, `timeout` or `xpass`, print `  stopped by --fail-fast`, run no more tests, but still tear down the module (if any test of it ran) and session instances and print the summary",
            "`--list`: print one line per selected test instead of running: `MODULE/NAME` and, if it has marks, two spaces and `[marks joined by spaces]`; nothing else (no summary); status 0"]
    if p["retries"]:
        opts.insert(2, "`--retries N`: as above; `N` must be one digit from 0 to 5")
    if p["skipslow"]:
        opts.append("`--skip-slow`: tests marked `slow` are skipped")
    for x in opts:
        w("* " + x)
    w("\nOptions are read left to right; the last repeat of an option wins. Errors (one `error:` line, status 1, checked before the suite is read): `error: unknown option 'X'` (any other word), `error: missing value for --X`, `error: bad value 'V' for --retries`.\n" if p["retries"] else
      "\nOptions are read left to right; the last repeat of an option wins. Errors (one `error:` line, status 1, checked before the suite is read): `error: unknown option 'X'` (any other word, including `--retries`), `error: missing value for --only`.\n")
    w("## 4. Examples\n")
    ex = [(c, r) for (c, r) in by_name.values() if c.visible]
    for c, r in ex[:3]:
        w(K.show_case(tool, c, r))
    w("The visible examples (`tests/examples.json`, run with `python3 tests/run_examples.py`) use the same format as the hidden checks: a `suite.txt`, the command line, the expected output and exit status.")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# suites
# ---------------------------------------------------------------------------------------------------------------

SCOPE_RANK = {"test": 0, "module": 1, "session": 2}


def make_suite(rng, p, nfx=None, ntests=None, hard=True):
    nfx = nfx or rng.randint(4, 6)
    names = rng.sample(FX_NAMES, nfx)
    fx = []
    for i, nm in enumerate(names):
        scope = rng.choice(["test", "test", "module", "module", "session"])
        pool = [f for f in fx if SCOPE_RANK[f["scope"]] >= SCOPE_RANK[scope]]
        needs = rng.sample([f["name"] for f in pool], min(len(pool), rng.choice([0, 0, 1, 1, 2]))) if pool else []
        setup, teardown = [], []
        setup.append(f"log {nm} {rng.choice(WORDS)}")
        if rng.random() < 0.3:
            setup.append(f"tick {rng.choice([1, 5, 10])}")
        if hard and rng.random() < 0.12:
            setup.append(rng.choice(["fail cannot connect", "raise ConnError", "fail"]))
        if rng.random() < 0.7:
            teardown.append(f"log {nm} {rng.choice(['released', 'closed', 'dropped'])}")
        if hard and rng.random() < 0.1:
            teardown.append(rng.choice(["fail leak", "raise Leak"]))
        fx.append(dict(name=nm, scope=scope, needs=needs, setup=setup, teardown=teardown, value=rng.choice(VALUES)))
    mods = rng.sample(MODULES, rng.randint(2, 3))
    tests = []
    tnames = rng.sample(TEST_NAMES, ntests or rng.randint(7, 11))
    for i, tn in enumerate(tnames):
        pool = [f["name"] for f in fx]
        needs = rng.sample(pool, min(len(pool), rng.choice([0, 1, 1, 2, 3])))
        marks = []
        r = rng.random()
        if r < 0.1:
            marks.append("skip")
        elif r < 0.22:
            marks.append("xfail")
        if rng.random() < 0.2:
            marks.append("slow")
        params = rng.sample(VALUES, rng.randint(2, 3)) if rng.random() < 0.2 else []
        steps = []
        for _ in range(rng.randint(1, 4)):
            q = rng.random()
            if q < 0.3:
                steps.append(f"log {tn} {rng.choice(WORDS)}")
            elif q < 0.45:
                steps.append(f"tick {rng.choice([5, 10, 20, 40, 70])}")
            elif q < 0.75 and needs:
                pick_name = rng.choice(needs)
                f = next(x for x in fx if x["name"] == pick_name)
                op = rng.choice(["==", "==", "!=", "<", ">"])
                lit = f["value"] if rng.random() < 0.6 else rng.choice(VALUES)
                steps.append(f"expect {f['name']} {op} {lit}")
            elif q < 0.82 and params:
                steps.append(f"expect param {rng.choice(['==', '!='])} {rng.choice(params)}")
            elif q < 0.88 and hard:
                steps.append(rng.choice(["fail broken", "fail", "raise Boom"]))
            elif q < 0.94 and p["flaky"]:
                steps.append(f"flaky {rng.randint(1, 2)}")
        tests.append(dict(name=tn, needs=needs, marks=marks, params=params, steps=steps, module=mods[min(i * len(mods) // len(tnames), len(mods) - 1)]))
    return fx, tests, mods


def render(fx, tests, mods, rng=None):
    lines = ["# generated suite", ""]
    for f in fx:
        head = f"fixture {f['name']}" + (f" scope {f['scope']}" if f["scope"] != "test" or (rng and rng.random() < 0.3) else "") + (" needs " + " ".join(f["needs"]) if f["needs"] else "")
        lines.append(head)
        lines += ["  setup " + s for s in f["setup"]] + ["  teardown " + s for s in f["teardown"]]
        if f["value"]:
            lines.append(f"  value {f['value']}")
        lines.append("")
    cur = None
    for t in tests:
        if t["module"] != cur:
            cur = t["module"]
            lines.append(f"module {cur}")
        head = f"test {t['name']}" + (" needs " + " ".join(t["needs"]) if t["needs"] else "") + (" marks " + " ".join(t["marks"]) if t["marks"] else "") + (" param " + " ".join(t["params"]) if t["params"] else "")
        lines.append(head)
        lines += ["  step " + s for s in t["steps"]]
        lines.append("")
    return "\n".join(lines)


def make_cases(p: dict, tool: str, rng) -> list[K.Case]:
    cases: list[K.Case] = []
    cnt: dict[str, int] = {}

    def add(group, args, text, visible=False):
        cnt[group] = cnt.get(group, 0) + 1
        cases.append(K.Case(name=f"{group}-{cnt[group]:02d}", group=group, args=args, files={"suite.txt": text}, visible=visible))

    def flag_pool():
        pool = [["--fail-fast"], ["--list"], ["--only", rng.choice(TEST_NAMES)]]
        if p["retries"]:
            pool.append(["--retries", str(rng.randint(0, 3))])
        if p["skipslow"]:
            pool.append(["--skip-slow"])
        return pool

    # plain runs of generated suites
    for k in range(6):
        fx, tests, mods = make_suite(rng, p, hard=(k % 2 == 1))
        add("run", [], render(fx, tests, mods, rng), visible=(k == 0))
    # options on a generated suite
    for k in range(6):
        fx, tests, mods = make_suite(rng, p)
        text = render(fx, tests, mods, rng)
        pool = flag_pool()
        add("options", rng.choice(pool) + (rng.choice(pool) if rng.random() < 0.5 else []), text)
    # scope ordering: a fixed shape with fixtures of every scope and dependencies between them
    for k in range(3):
        a, b, c, d = rng.sample(FX_NAMES, 4)
        text = f"""
fixture {a} scope session
  setup log {a} up
  teardown log {a} down
fixture {b} scope module needs {a}
  setup log {b} up
  teardown log {b} down
fixture {c} needs {b}
  setup log {c} up
  setup tick 3
  teardown log {c} down
fixture {d} scope module
  setup log {d} up
  teardown log {d} down
  value {rng.choice(VALUES)}
module one
test t1 needs {c}
  step log t1
test t2 needs {d} {c}
  step expect {d} == {rng.choice(VALUES)}
test t3
  step log no fixtures
module two
test t4 needs {b}
  step log t4
test t5 needs {c} {d} marks skip
test t6 needs {d}
  step tick 5
"""
        add("scopes", rng.choice([[], ["--only", "t"], ["--fail-fast"], ["--only", "t4"]]), text, visible=False)
    # failures in setup and teardown
    for k in range(5):
        a, b, c = rng.sample(FX_NAMES, 3)
        kinds = [("fail cannot start", "fail"), ("raise Boom", "raise"), ("fail", "fail")]
        s1 = rng.choice(kinds)[0]
        text = f"""
fixture {a} scope {rng.choice(['module', 'session'])}
  setup log {a} start
  setup {s1}
  teardown log {a} never
fixture {b} needs {a}
  setup log {b} start
  teardown log {b} stop
fixture {c}
  setup log {c} start
  teardown log {c} stop
  teardown {rng.choice(['fail leaked', 'raise Leak'])}
  teardown log {c} after error
fixture other
  setup log other start
  teardown log other stop
  teardown fail first
  value 1
test t1 needs {c}
  step log t1
test t2 needs {b}
  step log t2
test t3 needs {a}
  step log t3
test t4 needs {c} other
  step fail broken
test t5 needs other
  step log t5
module m2
test t6 needs {b} other
  step log t6
test t7
  step log plain
"""
        add("failures", rng.choice([[], [], ["--fail-fast"], ["--only", "t"]]), text)
    # retries
    if p["retries"]:
        for k in range(4):
            a = rng.choice(FX_NAMES)
            fl = "  step flaky 2\n" if p["flaky"] else "  step fail often\n"
            text = f"""
fixture {a}
  setup log {a} up
  teardown log {a} down
  value 5
fixture shared scope module
  setup log shared up
  teardown log shared down
test t1 needs {a} shared
{fl}  step log survived
test t2 needs shared
  step fail always
test t3 marks xfail
  step fail expected
test t4 needs {a}
  step raise Boom
test t5
  step tick 500
test t6
  step log fine
"""
            add("retries", ["--retries", str(k)] + rng.choice([[], ["--fail-fast"], ["--only", "t1"]]), text)
    # marks and params
    for k in range(3):
        text = """
fixture n
  setup log n up
  teardown log n down
  value 3
module marks
test good needs n marks xfail
  step expect n == 3
test bad marks xfail
  step expect n == 3
test boom marks xfail
  step raise Oops
test slowpoke marks slow xfail
  step tick 40
test sleeper marks skip
  step fail never runs
test sized param 1 2 3 marks slow
  step expect param < 3
test words param a b
  step expect param != b
  step log checked
test cmp needs n
  step expect n < 10
  step expect n > 5
  step expect n > -1
  step expect n == 03
"""
        add("marks", rng.choice([[], ["--list"], ["--only", "s"], ["--only", "sized"]] + ([["--skip-slow"]] if p["skipslow"] else [])), text)
    # timeouts
    for k in range(2):
        t = p["timeout"]
        text = f"""
fixture slow_setup
  setup tick {t * 3}
  setup log done
test within needs slow_setup
  step tick {t}
test over
  step tick {t - 1}
  step tick 2
  step log unreachable
test twice
  step tick {t // 2}
  step tick {t // 2}
  step tick 1
"""
        add("timeouts", [] if k == 0 else ["--fail-fast"], text)
    # suite errors
    bad = [
        "  setup log x\n", "fixture f\n  frob 1\n", "test t\n  frob 1\n", "test t\n  step\n", "test t\n  step log\n", "test t\n  step tick x\n", "test t\n  step tick 123456\n", "fixture f\n  setup expect a == 1\n", "test t\n  step expect a === 1\n",
        "test t\n  step expect a == bad!literal\n", "test t\n  step raise 9x\n", "fixture f\n  value\n", "fixture f\n  value a b\n", "frob x\n", "module\n", "module a b\n", "fixture\n", "fixture 9\n", "fixture f scope\n", "fixture f scope session test\n",
        "fixture f scope weird\n", "fixture f needs\n", "fixture f needs a needs b\n", "fixture f junk\n", "fixture f\nfixture f\n", "test t\ntest t\n", "test t param 1 2 bad!\n", "test t marks\n", "test t needs x\n", "fixture f needs g\n",
        "fixture a needs b\nfixture b needs a\n", "fixture a needs a\n", "fixture a needs b\nfixture b needs c\nfixture c needs a\n", "fixture a scope session needs b\nfixture b\n", "fixture a scope module\nfixture b scope session needs a\n",
        "fixture a scope module needs b c\nfixture b scope session\nfixture c\n", "test t needs q\nfixture q needs nope\n", "test t1\n  step flaky 1\n" if p["flaky"] else "test t1\n  step flaky\n", "# nothing but comments\n\n",
        "test t\n  step log a\n\tstep log b\n", "test t\n step log a\n",
    ]
    rng.shuffle(bad)
    for text in bad[:16]:
        add("suite-errors", [], text)
    add("suite-errors", [], "")
    # option errors
    fx, tests, mods = make_suite(rng, p, 3, 4, hard=False)
    base = render(fx, tests, mods)
    bad_opts = [["--bogus"], ["--only"], ["run"], ["--fail-fast", "--list", "-x"], ["--only", "a", "--only"], ["--retries", "2"], ["--retries"], ["--retries", "9"], ["--retries", "x"], ["--skip-slow"], ["--list", "--list"], ["--only", "a", "--only", "login"]]
    for a in bad_opts:
        add("cli", a, base)
    cases.append(K.Case(name="cli-missing", group="cli", args=[], files={}))
    # random suites with random options
    for k in range(8):
        fx, tests, mods = make_suite(rng, p, rng.randint(5, 8), rng.randint(9, 14))
        args = []
        for _ in range(rng.randint(0, 2)):
            args += rng.choice(flag_pool())
        add("fuzz", args, render(fx, tests, mods, rng))
    return cases


@family("project-trials", category="project", lang="javascript", kind="greenfield", n=8,
        summary="a fixture-based test runner for suites in an invented format: scoped fixtures with dependencies, exact setup/teardown ordering, retries, timeouts on a virtual clock, xfail/skip marks")
def gen(rng, n):
    for i in range(n):
        plan = dict(PLAN[i])
        tool = TOOLS[i]
        lang = plan.pop("lang")
        p = dict(plan)
        cfg = dict(TIMEOUT=p["timeout"], HAS_FLAKY=p["flaky"], HAS_SKIP_SLOW=p["skipslow"], HAS_RETRIES=p["retries"])
        cases = make_cases(p, tool, rng)
        py_sol = K.merged(K.load_src(THEME, "python", tool), K.render_config("python", cfg))
        sol = py_sol if lang == "python" else K.merged(K.load_src(THEME, lang, tool), K.render_config(lang, cfg))
        prompt = VOICES[i % len(VOICES)].format(tool=tool, Lang=K.LANG_NAME[lang], run=K.how_to_run(lang, tool), num=1500 + i * 21)
        nfeat = sum([p["flaky"], p["skipslow"], p["retries"]])
        yield K.project_task(
            theme=THEME, tool=tool, lang=lang, cases=cases, solution=sol, py_solution=py_sol,
            readme=lambda by_name, p=p, tool=tool, lang=lang: readme(p, tool, lang, by_name),
            prompt=prompt, difficulty=4 if nfeat <= 1 else 5, slug=f"{i + 1:02d}-{tool}-{p['timeout']}ms-{lang}",
            notes={k_: p[k_] for k_ in ("timeout", "flaky", "skipslow", "retries")}, tags=["test-framework", "fixtures"],
        )
