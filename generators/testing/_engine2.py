"""More testing task kinds built on ``_engine``: regression tests for bug reports, repairing a suite with wrong expectations,
and decoupling a suite from implementation details."""
from __future__ import annotations

import random
import re

from fx import Task, run
from fx.lib import _diff_line, _probe_diffs, _sanitize_excerpt
from fx.run import merged

from . import _engine as E
from ._engine import STRIP, VERIFY, TLib, choose, hidden_files, mutant_pool, protect_globs


def mutant_text(ref: str, edit: dict) -> str:
    lines = ref.split("\n")
    lines[edit["line"] - 1] = edit["new"]
    return "\n".join(lines)


def _tidy_tap(text: str) -> str:
    """node --test (TAP) output reduced to the failing assertions: no timings, locations or stack frames."""
    lines = text.split("\n")
    out: list[str] = []
    i, shown = 0, 0
    while i < len(lines):
        if not re.match(r"^not ok \d+ - ", lines[i]):
            i += 1
            continue
        if shown >= 2:
            break
        shown += 1
        out.append("not ok - nightly check")
        i += 1
        err: list[str] = []
        exp = act = None
        in_err = False
        while i < len(lines) and not re.match(r"^(not )?ok \d+ - |^1\.\.\d+|^# ", lines[i]):
            l = lines[i]
            if re.match(r"^\s{2}error:", l):
                in_err = True
                rest = l.split("error:", 1)[1].strip()
                rest = rest[2:].strip() if rest.startswith(("|-", "|+")) else rest.strip("|").strip()
                if rest:
                    err.append(rest)
            elif in_err and re.match(r"^\s{4,}\S", l):
                err.append(l.strip())
            elif re.match(r"^\s{2}\w+:", l):
                in_err = False
                t = l.strip()
                if t.startswith("expected:"):
                    exp = t
                elif t.startswith("actual:"):
                    act = t
            i += 1
        if err:
            out.append("  error: " + " / ".join(err))
        if act and exp:
            out += ["  " + act, "  " + exp]
    return "\n".join(out)


def _tidy_cargo(text: str) -> str:
    lines = [l for l in text.split("\n") if not re.match(r"^\s+\d+: |^\s+at /|^stack backtrace:|^note: run with `RUST_BACKTRACE|^note: Some details are omitted|^    [a-z_0-9]+$", l)]
    text = "\n".join(lines)
    text = re.sub(r"thread '[^']*'( \(\d+\))? panicked", "thread 'main' panicked", text)
    text = re.sub(r"^---- \S+ stdout ----", "---- check stdout ----", text, flags=re.M)
    text = re.sub(r"^\S+ --- FAILED$", "check --- FAILED", text, flags=re.M)
    return text


def clean_excerpt(ex: str) -> str:
    """A CI excerpt as a person would paste it: no test names, no source lines of tracebacks, no braces that look like template holes."""
    if re.search(r"^not ok \d+ - ", ex, re.M):
        ex = _tidy_tap(ex) or ex
    if "panicked at" in ex or re.search(r"^\S+ --- FAILED$", ex, re.M):
        ex = _tidy_cargo(ex)
    lines = ex.split("\n")
    if any(l.startswith("Traceback") for l in lines):
        lines = [l for l in lines if not (re.match(r"^\s{4,}\S", l) and "File " not in l)]
    lines = [l for l in lines if not l.startswith("Picked up JAVA_TOOL_OPTIONS")]
    text = "\n".join(lines)
    text = re.sub(r"FAIL (\w+\.)?test\w*:", "FAIL check:", text)
    text = re.sub(r"(FAIL|ERROR): test_\w+ \([^)]*\)", r"\1: nightly check", text)
    text = re.sub(r"--- FAIL: \w+", "--- FAIL: nightly check", text)
    text = re.sub(r"(not ok \d+ - )\S.*", r"\1nightly check", text)
    text = re.sub(r"thread '[^']*' panicked", "thread 'main' panicked", text)
    text = re.sub(r"^test \S+ \.\.\. FAILED", "test check ... FAILED", text, flags=re.M)
    text = re.sub(r"\{([a-z_]+)\}", r"<\1>", text)
    return text


def _clip(s: str, n: int = 150) -> str:
    return s if len(s) <= n else s[: n - 1] + "..."


# ---- (b) regression tests -------------------------------------------------------------------------------------------

def _symptom(lib: TLib, cand: E.Cand, bug_files: dict) -> tuple[str, str, str]:
    """(kind, text, one-liner) describing how the bug shows; kind is 'probes' or 'excerpt'."""
    diffs = _probe_diffs(lib, lib.files, bug_files) if lib.lang == "python" else []
    if diffs:
        lines = "\n".join(_diff_line(e, g, b) for e, g, b in diffs[:2])
        e, g, b = diffs[0]
        return "probes", lines, _diff_line(e, g, b)[2:]
    ex = clean_excerpt(_sanitize_excerpt(cand.out, sorted(lib.gold)))
    if ex.strip():
        return "excerpt", ex, _clip(_one_liner(ex))
    return "", "", ""


def _one_liner(ex: str) -> str:
    """The most telling single line of a cleaned CI excerpt."""
    m_act, m_exp = re.search(r"^\s*actual: (.*)$", ex, re.M), re.search(r"^\s*expected: (.*)$", ex, re.M)
    if m_act and m_exp:
        return f"got {m_act.group(1)}, expected {m_exp.group(1)}"
    m_l, m_r = re.search(r"^\s*left: (.*)$", ex, re.M), re.search(r"^\s*right: (.*)$", ex, re.M)
    if m_l and m_r:
        return f"left {m_l.group(1)}, right {m_r.group(1)}"
    m_e = re.search(r"^\s*error: (.*)$", ex, re.M)
    if m_e:
        return m_e.group(1).strip()
    sal = [ln for ln in ex.splitlines() if re.search(r"expected|got|want|!=|!==|Error|panick|assert", ln) and not re.match(r"^\s*[+-] (actual|expected)", ln)] or ex.splitlines()
    return sal[-1].strip()


def regress_prompt(rng: random.Random, lib: TLib, kind: str, text: str, one: str, fix_too: bool) -> str:
    where = lib.where
    if fix_too:
        tail = rng.choice([
            "Fix the bug and add a regression test for it. The test must fail on the broken code and pass on the fixed code; I will check it against both, and the fix against the full behaviour described in README.md.",
            "Please fix it, test-first: write the test that exposes the bug, then repair the code. Both parts are checked: the test against the broken and a correct version, the code against the whole specification.",
            "Two things: a regression test that fails now and passes after the fix, and the fix itself.",
        ])
    else:
        tail = rng.choice([
            "Write a regression test for it. It has to fail on the current code and pass once the bug is fixed (somebody else is fixing it), so do not change the library; I will run your test against the broken code and against a corrected one.",
            "Add a test that reproduces this and pins the correct behaviour. Don't fix the bug in this change: the test must go red on today's code and green on a fixed version, and I will check both.",
            "Before we fix it we want a failing test. Write it (tests only, leave the library alone); it must pass against a correct implementation and fail against the current one.",
        ])
    t = lib.title
    if kind == "probes":
        voices = [
            f"Support ticket: the {t[4:] if t.startswith('the ') else t} gives wrong answers. {lib.blurb} Examples from the customer:\n\n{text}\n\nOur existing tests did not notice. {tail} {where}",
            f"**Bug report** for {t}\n\n{text}\n\n_Expected_ is what README.md says. {tail} {where}",
            f"bug in {t}: {one}. {tail} {where}",
            f"A user of {t} reports that {one}. {lib.blurb} {tail} {where}",
            f"Postmortem action item: \"add a regression test for the defect in {t}\". What happened: {one}. {tail} {where}",
        ]
    else:
        voices = [
            f"Our nightly cross-check against the reference implementation flagged a difference in {t}. {lib.blurb} What it printed:\n\n```\n{text}\n```\n\nNone of our unit tests fail on this. {tail} {where}",
            f"There is a defect in {t}: {one}. {tail} {where}",
            f"Triage note for {t}: one of the documented rules is broken in the current code (symptom: `{one}`). {tail} {where}",
            f"Something is wrong in {t}. The reproduction we have is only this fragment of a check run:\n\n```\n{text}\n```\n\n{tail} {where}",
        ]
    return rng.choice(voices)


def regress_task(lib: TLib, cand: E.Cand, rng: random.Random, slug: str, fix_too: bool, inst: int) -> Task | None:
    ref = lib.files[cand.path]
    bug = mutant_text(ref, cand.edit())
    bug_files = merged(lib.files, {cand.path: bug})
    kind, text, one = _symptom(lib, cand, bug_files)
    if not kind:
        return None
    prompt = regress_prompt(rng, lib, kind, text, one, fix_too)
    scen = [
        {"name": "fixed code, your tests", "expect": "pass", "gate": True, "sources": {cand.path: ref}},
        {"name": "fixed code, shifted lines and file hash", "expect": "pass", "gate": True, "marker": True, "sources": {cand.path: ref}},
        {"name": "buggy code, your tests", "expect": "fail", "sources": {cand.path: bug}},
    ]
    if fix_too:
        scen.append({"name": "your fix against the full behaviour suite", "expect": "pass", "strip": STRIP[lib.lang],
                     "files": merged(lib.gold, {p: lib.files[p] for p in lib.files if p == "tests/__init__.py"}, lib.strip_keep), "sources": {}})
    spec = E.base_spec(lib, scen)
    spec["ref"] = {cand.path: ref}
    d = lib.difficulty - 1 + (1 if kind == "excerpt" else 0) + (1 if fix_too else 0)
    sol = dict(lib.gold)
    if fix_too:
        sol[cand.path] = ref
    return Task(
        slug=slug, prompt=prompt, difficulty=max(1, min(5, d)), kind="fix", start=merged(bug_files, lib.stub), hidden=hidden_files(spec),
        solution=sol, verify=VERIFY, pass_mode="json-score", protect_tests=False, protected=[] if fix_too else protect_globs(lib),
        timeout_s=max(150, lib.timeout * 6 + 60), tags=["regression-test", *(["fix-too"] if fix_too else []), *lib.tags],
        notes={"library": lib.name, "bug": cand.desc, "symptom": kind, "instance": inst},
    )


def regress_family(factories, rng: random.Random, n: int, per_instance: int = 3, fix_too_every: int = 0):
    i = 0
    inst = 0
    guard = 0
    while i < n and guard < n * 6:
        guard += 1
        lib = factories[inst % len(factories)](rng)
        pool = mutant_pool(lib)
        used: set = set()
        made = 0
        order = list(range(len(pool)))
        rng.shuffle(order)
        for idx in order:
            if made >= per_instance or i >= n:
                break
            c = pool[idx]
            if (c.path, c.line) in used:
                continue
            fix_too = bool(fix_too_every) and (i % fix_too_every == fix_too_every - 1)
            t = regress_task(lib, c, rng, f"{i + 1:02d}-{lib.name.split('-', 1)[-1]}-{c.op}", fix_too, inst)
            if t is None:
                continue
            used.add((c.path, c.line))
            made += 1
            i += 1
            yield t
        inst += 1


# ---- (c1) wrong expectations ----------------------------------------------------------------------------------------

def _failure_summary(out: str) -> str:
    ex = _sanitize_excerpt(out, [])
    return clean_excerpt(ex or "\n".join(out.strip().splitlines()[-12:]))


def broken_suite(lib: TLib, rng: random.Random, k: int) -> tuple[dict[str, str], dict[str, str], str] | None:
    """(start tests with k wrong expectations, fixed tests = gold, CI output of the broken suite on the real code)."""
    from ._pygold import corrupt_literal, eq_index, gold_tests, run_groups

    if lib.lang == "python":
        if not getattr(lib, "py_groups", None):
            return None
        results = run_groups(lib.files, lib.py_imports, lib.py_groups)
        idx = eq_index(lib.py_groups, results)
        rng.shuffle(idx)
        chosen, seen_groups = {}, set()
        for n_, gi, si, expr, val in idx:
            if gi in seen_groups and len(chosen) < k - 1 and rng.random() < 0.7:
                continue
            bad = corrupt_literal(val, n_)
            if bad is None or bad == val:
                continue
            chosen[n_] = bad
            seen_groups.add(gi)
            if len(chosen) >= k:
                break
        if len(chosen) < k:
            return None
        gpath = next(iter(lib.gold))
        cls = re.search(r"class (\w+)\(", lib.gold[gpath]).group(1)
        tests = gold_tests(lib.files, lib.py_imports, lib.py_groups, header=lib.py_header, path=gpath, cls=cls, corrupt=chosen)
    else:
        if len(lib.wrong_edits) < k:
            return None
        picks = rng.sample(lib.wrong_edits, k)
        tests = dict(lib.gold)
        for path, old, new in picks:
            assert tests[path].count(old) == 1, (lib.name, old)
            tests[path] = tests[path].replace(old, new)
    r = run(merged(lib.files, tests), lib.cmd, timeout=max(lib.timeout, 60))
    if r.ok:
        return None
    return tests, dict(lib.gold), _failure_summary(r.out)


def expect_prompt(rng: random.Random, lib: TLib, k: int, summary: str, frozen_note: str) -> str:
    t = lib.title
    where = lib.where
    voices = [
        f"CI has been red since a new colleague's test suite for {t} landed. {lib.blurb} The output:\n\n```\n{summary}\n```\n\n{frozen_note} README.md is the specification. Repair the suite; do not just delete the failing tests, it still has to catch real regressions.",
        f"The tests for {t} fail and the author insists the module is buggy. I suspect the tests, not the module. {frozen_note} Check every failing expectation against README.md and fix whichever side is wrong. {where}",
        f"tests red. which side is wrong, tests or code? spec: README.md. {frozen_note} output:\n\n```\n{summary}\n```",
        f"Release freeze: the library is not allowed to change. Yet its test suite fails ({k} {'failure' if k == 1 else 'failures'} reported in CI). Find out why, using README.md as the arbiter, and make the suite green *and* meaningful: it will also be run against deliberately broken copies of the module, and it must still reject them. {where}",
        f"Could you look at why the suite of {t} fails? {lib.blurb} CI says:\n\n```\n{summary}\n```\n\nI can't tell if the tests or the code are at fault. The README describes what should happen. {frozen_note}",
    ]
    return rng.choice(voices)


def expect_task(lib: TLib, rng: random.Random, k_wrong: int, chosen: list[E.Cand], slug: str, inst: int) -> Task | None:
    bs = broken_suite(lib, rng, k_wrong)
    if bs is None:
        return None
    start_tests, fixed, summary = bs
    # the suite under repair replaces the gold file(s) in the start tree; stub tests are dropped
    note = rng.choice(["The library code is frozen for this release.", "Only the tests may change; the module itself is locked.", "Don't touch the library, it is frozen until the release is out.", ""])
    prompt = expect_prompt(rng, lib, k_wrong, summary, note)
    spec = E.base_spec(lib, [E.sc_base(), E.sc_marker()], E.mutant_specs(chosen))
    d = lib.difficulty - 1 + (k_wrong >= 3) + (1 if not note else 0)
    return Task(
        slug=slug, prompt=prompt, difficulty=max(1, min(5, d)), kind="fix", start=merged(lib.files, start_tests), hidden=hidden_files(spec),
        solution=fixed, verify=VERIFY, pass_mode="json-score", protect_tests=False, protected=protect_globs(lib),
        timeout_s=max(150, lib.timeout * (len(chosen) + 3) + 60), tags=["repair-suite", "wrong-expectation", *lib.tags],
        notes={"library": lib.name, "wrong": k_wrong, "mutants": [c.desc for c in chosen], "instance": inst},
    )


def expect_family(factories, rng: random.Random, n: int, per_instance: int = 3):
    i, inst, guard = 0, 0, 0
    while i < n and guard < n * 6:
        guard += 1
        lib = factories[inst % len(factories)](rng)
        pool = mutant_pool(lib)
        used: set = set()
        for j in range(per_instance):
            if i >= n:
                break
            k_wrong = rng.choice([1, 2, 2, 3, 4])
            chosen = choose(pool, rng, rng.choice([4, 5, 6, 8]), exclude=used)
            if len(chosen) < 3:
                continue
            used |= {(c.path, c.line) for c in chosen}
            t = expect_task(lib, rng, k_wrong, chosen, f"{i + 1:02d}-{lib.name.split('-', 1)[-1]}-{k_wrong}wrong", inst)
            if t is None:
                continue
            i += 1
            yield t
        inst += 1


# ---- (c2) decouple from implementation details ----------------------------------------------------------------------

def refactor_text(text: str, renames: dict[str, str], msg_swaps: dict[str, str]) -> str:
    for old, new in renames.items():
        text = re.sub(r"\b" + re.escape(old) + r"\b", new, text)
    for old, new in msg_swaps.items():
        text = text.replace(old, new)
    return text


def internals_prompt(rng: random.Random, lib: TLib) -> str:
    t, where = lib.title, lib.where
    voices = [
        f"We are about to restructure {t}: private helpers get renamed and moved, error messages get reworded, the public behaviour in README.md stays exactly the same. The current tests reach into the private helpers and match message texts, so they would all break. Rewrite the suite so it only depends on documented behaviour but still catches real bugs; I will run it against a restructured copy of the module and against copies with seeded bugs. {where}",
        f"Our tests for {t} are brittle: they call underscore-prefixed functions and assert on exact error messages. Last month a harmless rename turned CI red for a day. Please make them test behaviour (see README.md) instead. They will be checked against a refactored version of the module that behaves identically, and against broken versions. {where}",
        f"{lib.blurb} The refactor of {t} lands next sprint (internal names and wording will change, the README contract won't). Port the existing tests so they survive it: public API only, no peeking at internals, no matching of message text. Don't lose coverage: mutated copies of the module must still fail them. {where}",
        f"review comment on the tests of {t}: \"these assert implementation details, not behaviour\". Fix that. The module will be refactored (same documented behaviour, different internals) and your suite has to pass on both; it also has to fail on buggy variants. {where}",
    ]
    return rng.choice(voices)


def internals_task(lib: TLib, rng: random.Random, chosen: list[E.Cand], slug: str, inst: int) -> Task | None:
    if not lib.internals or not lib.renames:
        return None
    refac = {p: refactor_text(lib.files[p], lib.renames, lib.msg_swaps) for p in lib.mutate}
    if any(refac[p] == lib.files[p] for p in lib.mutate):
        raise RuntimeError(f"{lib.name}: renames do not change {lib.mutate}")
    chk = run(merged(lib.files, refac, lib.gold), lib.cmd, timeout=max(lib.timeout, 60))
    if not chk.ok:
        raise RuntimeError(f"{lib.name}: gold fails on the refactored variant:\n{chk.out[-1500:]}")
    on_ref = run(merged(lib.files, lib.internals), lib.cmd, timeout=max(lib.timeout, 60))
    on_ref2 = run(merged(lib.files, refac, lib.internals), lib.cmd, timeout=max(lib.timeout, 60))
    if not on_ref.ok or on_ref2.ok:
        raise RuntimeError(f"{lib.name}: internals suite must pass on the original and fail on the refactored variant")
    scen = [E.sc_base(), E.sc_marker(), {"name": "refactored module, your tests", "expect": "pass", "sources": refac}]
    # the solution cannot delete files: the behavioural suite takes the place of the internals suite
    (ipath,) = list(lib.internals)
    (gpath,) = list(lib.gold)
    sol = {ipath: lib.gold[gpath]}
    spec = E.base_spec(lib, scen, E.mutant_specs(chosen))
    return Task(
        slug=slug, prompt=internals_prompt(rng, lib), difficulty=max(1, min(5, lib.difficulty)), kind="refactor",
        start=merged(lib.files, lib.stub, lib.internals), hidden=hidden_files(spec), solution=sol, verify=VERIFY,
        pass_mode="json-score", protect_tests=False, protected=protect_globs(lib), timeout_s=max(150, lib.timeout * (len(chosen) + 4) + 60),
        tags=["repair-suite", "implementation-details", *lib.tags], notes={"library": lib.name, "mutants": [c.desc for c in chosen], "instance": inst},
    )


def internals_family(factories, rng: random.Random, n: int, per_instance: int = 2):
    i, inst, guard = 0, 0, 0
    while i < n and guard < n * 6:
        guard += 1
        lib = factories[inst % len(factories)](rng)
        pool = mutant_pool(lib)
        used: set = set()
        for j in range(per_instance):
            if i >= n:
                break
            chosen = choose(pool, rng, rng.choice([5, 6, 8, 10]), exclude=used)
            if len(chosen) < 4:
                continue
            used |= {(c.path, c.line) for c in chosen}
            t = internals_task(lib, rng, chosen, f"{i + 1:02d}-{lib.name.split('-', 1)[-1]}-internals", inst)
            if t is None:
                continue
            i += 1
            yield t
        inst += 1
