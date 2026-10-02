"""Flaky-test families: replace sleeping by an injected clock, remove order dependence between tests.

Both families score with the generic checker (``_check_tests.py``): a list of scenarios, gate scenarios first, then the mutants of the reference code.
"""
from __future__ import annotations

import random
import re

from fx import Task, dd, run
from fx.run import merged

from . import _engine as E
from ._engine import TLib, choose, hidden_files, mutant_pool, protect_globs
from ._engine2 import clean_excerpt

# ---- hidden helper files --------------------------------------------------------------------------------------------

FROZEN_PY = dd('''
    """Real time stands still: every clock function returns one fixed instant and sleeping returns at once."""
    import time as _time

    _NOW = 1700000000.0


    def _frozen():
        return _NOW


    _time.time = _frozen
    _time.monotonic = _frozen
    _time.perf_counter = _frozen
    _time.sleep = lambda seconds: None
''')

FAST_PY = dd('''
    """Real time races ahead: every look at a clock is 40 seconds later than the previous one; sleeping returns at once."""
    import time as _time

    _t = [1700000000.0]


    def _tick():
        _t[0] += 40.0
        return _t[0]


    _time.time = _tick
    _time.monotonic = _tick
    _time.perf_counter = _tick
    _time.sleep = lambda seconds: None
''')

ORDER_PY = dd('''
    """Runs the unittest suite of tests/ in another order (reverse, a seeded shuffle) or every test alone in its own process."""
    import os
    import random
    import subprocess
    import sys
    import unittest


    def snapshot():
        found = set()
        for dirpath, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "_verify")]
            found.update(os.path.join(dirpath, f) for f in files)
        return found


    def flatten(suite):
        for t in suite:
            if isinstance(t, unittest.TestSuite):
                yield from flatten(t)
            else:
                yield t


    def main():
        mode = sys.argv[1]
        sys.path.insert(0, ".")
        tests = list(flatten(unittest.TestLoader().discover("tests", top_level_dir=".")))
        if mode == "reverse":
            tests.reverse()
        elif mode.startswith("shuffle:"):
            random.Random(int(mode.split(":")[1])).shuffle(tests)
        elif mode == "alone":
            bad = 0
            for t in tests:
                before = snapshot()
                p = subprocess.run([sys.executable, "-m", "unittest", t.id()], capture_output=True, text=True)
                for path in snapshot() - before:
                    os.remove(path)
                if p.returncode != 0:
                    bad += 1
                    print("FAILED ALONE: " + t.id())
                    print(p.stderr[-600:])
            print("%d tests, %d failed when run alone" % (len(tests), bad))
            sys.exit(1 if bad or not tests else 0)
        suite = unittest.TestSuite(tests)
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        sys.exit(0 if result.wasSuccessful() and result.testsRun else 1)


    main()
''')

NO_SLEEP = {"globs": ["tests/*.py", "tests/**/*.py"], "forbid": [r"\btime\.sleep\b", r"from\s+time\s+import[^\n]*\bsleep\b", r"freezegun|freeze_time"]}


# ---- clock injection ------------------------------------------------------------------------------------------------

def clock_prompt(rng: random.Random, lib: TLib, variant: str, k: int) -> str:
    cls, t, w, b = lib.extra["cls"], lib.title, lib.where, lib.blurb
    grading = rng.choice([
        "I will run your tests with real time frozen and with real time racing ahead, against the real code and against copies with bugs seeded in; they have to pass in the first two and fail on the buggy copies.",
        "To check the result I run the suite in a world where the system clock stands still, in another where it jumps 40 seconds on every look, and against mutated copies of the module (which must make it go red).",
        "The grader runs the tests under a frozen clock and under a wildly fast one, and also against deliberately broken versions of the module: green in the first two, red on the broken ones.",
    ])
    if variant == "inject":
        api = (f"Give `{cls}` a keyword argument `clock`: a callable without arguments that returns the current time in seconds as a float, with `time.monotonic` as the default. "
               "The class must read the time only through it (a clock handed in later is not enough: it has to work from the constructor). Everything README.md describes stays as it is.")
        voices = [
            f"The tests of {t} sleep their way through the timeouts: the run takes seconds, and on the shared runner one of them fails every other week. {b} Make them fast and deterministic. {api} Then rewrite the tests to drive a fake clock; nothing may sleep any more. {grading} {w}",
            f"{t[0].upper() + t[1:]} cannot be tested without waiting, so the existing tests wait. That has to stop. {api} Port the suite to a fake clock (no `time.sleep` anywhere in the tests) and keep it strong: boundaries included. {grading} {w}",
            f"flaky CI: the suite of {t} relies on real sleeps. {api} Replace the sleeps by a controllable clock in the tests. {grading} {w}",
            f"Ticket: make the tests of {t} deterministic. {b} The library hard-wires the system clock, so first make the time a dependency. {api} Then the tests: no sleeping, every documented rule pinned. {grading} {w}",
        ]
    else:
        voices = [
            f"The tests of {t} sleep their way through the timeouts: the run takes seconds, and on the shared runner one of them fails every other week. {b} The library already accepts a `clock` (see README.md), so there is no excuse: rewrite the tests around a fake clock and remove every sleep. Do not change the library. {grading} {w}",
            f"Rewrite the tests of {t} so they never wait. The module takes an injectable `clock`, the tests just don't use it. Keep them strong: they have to catch seeded bugs, boundaries included. {grading} {w}",
            f"CI timing: the suite of {t} is the slowest and the flakiest of the repository because it sleeps. Use the `clock` argument documented in README.md to make it instant and deterministic; leave the library alone. {grading} {w}",
        ]
    return rng.choice(voices)


def clock_task(lib: TLib, chosen: list[E.Cand], variant: str, rng: random.Random, slug: str, inst: int) -> Task:
    x = lib.extra
    api_path = f"tests/test_zz_clock_api_{x['mod']}.py"
    scen = [E.sc_base(), E.sc_marker()]
    if variant == "inject":
        scen.append({"name": "the documented clock keyword works", "expect": "pass", "gate": True, "files": {api_path: x["api"]},
                     "cmd": f"python3 -m unittest tests.test_zz_clock_api_{x['mod']}"})
    scen += [
        {"name": "no sleeping in the tests", "expect": "pass", "grep": NO_SLEEP},
        {"name": "real time frozen", "expect": "pass", "files": {"_verify/frozen/sitecustomize.py": FROZEN_PY}, "env": {"PYTHONPATH": "_verify/frozen"}},
        {"name": "real time racing ahead", "expect": "pass", "files": {"_verify/fast/sitecustomize.py": FAST_PY}, "env": {"PYTHONPATH": "_verify/fast"}},
    ]
    spec = E.base_spec(lib, scen, E.mutant_specs(chosen))
    if variant == "inject":
        start = merged(lib.files, x["legacy"], {"README.md": x["readme_plain"]}, x["sleepy"])
        sol = merged({p: lib.files[p] for p in lib.mutate}, lib.gold)
        protected: list[str] = []
        kind = "refactor"
        d = lib.difficulty + (len(chosen) >= 8)
    else:
        start = merged(lib.files, x["sleepy"])
        sol = dict(lib.gold)
        protected = protect_globs(lib)
        kind = "fix"
        d = lib.difficulty - 1 + (len(chosen) >= 8)
    return Task(
        slug=slug, prompt=clock_prompt(rng, lib, variant, len(chosen)), difficulty=max(1, min(5, d)), kind=kind, start=start, hidden=hidden_files(spec),
        solution=sol, verify=E.VERIFY, pass_mode="json-score", protect_tests=False, protected=protected,
        timeout_s=max(150, lib.timeout * (len(chosen) + 6) + 60), tags=["flaky-tests", "fake-clock", variant, *lib.tags],
        notes={"library": lib.name, "variant": variant, "mutants": [c.desc for c in chosen], "instance": inst},
    )


def clock_family(factories, rng: random.Random, n: int):
    i, inst, guard = 0, 0, 0
    while i < n and guard < n * 4:
        guard += 1
        lib = factories[inst % len(factories)](rng)
        pool = mutant_pool(lib)
        used: set = set()
        for variant, k in (("tests", rng.choice([5, 6])), ("inject", rng.choice([6, 7])), ("inject", rng.choice([9, 10])), ("tests", rng.choice([8, 9]))):
            if i >= n:
                break
            chosen = choose(pool, rng, k, exclude=used if variant == "tests" and k < 7 else None)
            if len(chosen) < 4:
                continue
            used |= {(c.path, c.line) for c in chosen}
            yield clock_task(lib, chosen, variant, rng, f"{i + 1:02d}-{lib.name.split('-', 1)[-1]}-{variant}-{len(chosen)}m", inst)
            i += 1
        inst += 1


# ---- order dependence -----------------------------------------------------------------------------------------------
#
# An order lib keeps its test file as a template: ``@@name@@`` lines mark where a test starts to obtain its fixture.  Every *group* has an init test and read-only
# user tests; in a clean suite every test builds what it needs, in a dirty group only the init test does and the users rely on what it left behind.

def render_order(template: str, groups: dict, dirty: set[str]) -> str:
    out = template
    for g, spec in groups.items():
        for slot, variants in spec["slots"].items():
            kind = "init" if slot == spec["init"] else "user"
            text = variants[f"{kind}_{'dirty' if g in dirty else 'clean'}"]
            if text == "":
                out = re.sub(r"^[ \t]*@@" + re.escape(slot) + r"@@\n", "", out, flags=re.M)
            else:
                out = out.replace(f"@@{slot}@@", text)
    assert "@@" not in out, "unfilled slot"
    return out


def order_prompt(rng: random.Random, lib: TLib, summary: str, k: int) -> str:
    t, w, b = lib.title, lib.where, lib.blurb
    nightly = f"\n\n```\n{summary}\n```\n" if summary else " "
    voices = [
        f"The test suite of {t} is green in CI but our nightly job, which runs the tests in a shuffled order and also one test at a time, is red.{nightly}Find out why and make every test independent of the others and of the order they run in. The library is not to blame and must not change; the tests must stay as strict as they are (mutated copies of the module will be run against them, in the normal order). {w}",
        f"Tests of {t} depend on each other. {b} Running a single one of them fails, running them backwards fails.{nightly}Repair the suite: each test sets up what it needs, nothing leaks from one test into the next, and no assertion gets weaker. Do not touch the library. {w}",
        f"We want to turn on random test ordering for {t}. Before that happens the suite has to survive it.{nightly}Make the tests order-independent (each one must pass alone, after any other, and in a reversed run) without losing coverage: the grader also runs them against seeded bugs. {w}",
        f"review comment: \"these tests only pass because of the order they run in\" (suite of {t}).{nightly}Fix them. Keep the checks, change how the tests prepare their state. Library code is off limits. {w}",
    ]
    return rng.choice(voices)


def _summary_from(out: str) -> str:
    lines = [l for l in out.splitlines() if re.match(r"^(Ran \d+ tests?|FAILED \(|\d+ tests, \d+ failed)", l)]
    return "\n".join(lines[-3:])


def order_scenarios(chosen_extra: list[dict] | None = None) -> list[dict]:
    files = {"_verify/order.py": ORDER_PY}
    return [
        E.sc_base(), E.sc_marker(),
        {"name": "tests in reverse order", "expect": "pass", "files": files, "cmd": "python3 _verify/order.py reverse"},
        {"name": "tests shuffled (seed 11)", "expect": "pass", "files": files, "cmd": "python3 _verify/order.py shuffle:11"},
        {"name": "tests shuffled (seed 4242)", "expect": "pass", "files": files, "cmd": "python3 _verify/order.py shuffle:4242"},
        {"name": "every test alone", "expect": "pass", "files": files, "cmd": "python3 _verify/order.py alone", "timeout": 120},
    ]


def order_task(lib: TLib, rng: random.Random, dirty: set[str], chosen: list[E.Cand], slug: str, inst: int) -> Task | None:
    x = lib.extra
    start_tests = {x["test_path"]: render_order(x["template"], x["groups"], dirty)}
    start = merged(lib.files, start_tests)
    # the start suite must be green in file order and red when shuffled: otherwise the task is not what it says
    base = run(start, lib.cmd, timeout=60)
    if not base.ok:
        raise RuntimeError(f"{lib.name}: dirty suite {sorted(dirty)} is not green in file order:\n{base.out[-1500:]}")
    rev = run(merged(start, {"_verify/order.py": ORDER_PY}), "python3 _verify/order.py reverse", timeout=60)
    alone = run(merged(start, {"_verify/order.py": ORDER_PY}), "python3 _verify/order.py alone", timeout=120)
    if rev.ok or alone.ok:
        raise RuntimeError(f"{lib.name}: dirty suite {sorted(dirty)} does not depend on the order (reverse ok={rev.ok}, alone ok={alone.ok})")
    spec = E.base_spec(lib, order_scenarios(), E.mutant_specs(chosen))
    n_dirty_tests = sum(len(x["groups"][g]["slots"]) for g in dirty)
    d = lib.difficulty - 2 + (len(dirty) >= 2) + (len(dirty) >= 3) + (n_dirty_tests >= 7)
    return Task(
        slug=slug, prompt=order_prompt(rng, lib, _summary_from(rev.out), len(dirty)), difficulty=max(1, min(5, d)), kind="fix", start=start, hidden=hidden_files(spec),
        solution=dict(lib.gold), verify=E.VERIFY, pass_mode="json-score", protect_tests=False, protected=protect_globs(lib),
        timeout_s=max(180, lib.timeout * (len(chosen) + 8) + 60), tags=["flaky-tests", "order-dependence", x["leak"], *lib.tags],
        notes={"library": lib.name, "dirty_groups": sorted(dirty), "mutants": [c.desc for c in chosen], "instance": inst},
    )


def _subsets(names: list[str]) -> list[list[str]]:
    out = [list(names)] + [[g] for g in names]
    out += [[a, b] for ai, a in enumerate(names) for b in names[ai + 1:] if len(names) > 2]
    return out


def order_family(factories, rng: random.Random, n: int):
    libs = [f(rng) for f in factories]
    queues = [[(lib, set(c)) for c in _subsets(sorted(lib.extra["groups"]))] for lib in libs]
    used: dict[str, set] = {lib.name: set() for lib in libs}
    i = 0
    while i < n and any(queues):
        for q in queues:
            if not q or i >= n:
                continue
            lib, dirty = q.pop(0)
            pool = mutant_pool(lib)
            chosen = choose(pool, rng, rng.choice([4, 5, 6, 8]), exclude=used[lib.name])
            if len(chosen) < 4:
                used[lib.name] = set()
                chosen = choose(pool, rng, rng.choice([4, 5, 6, 8]))
            used[lib.name] |= {(c.path, c.line) for c in chosen}
            yield order_task(lib, rng, dirty, chosen, f"{i + 1:02d}-{lib.name.split('-', 1)[-1]}-{len(dirty)}leaks", 0)
            i += 1
