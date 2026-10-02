"""Monorepos of independent library packages, each carrying its own defect (swarm: one worker per package)."""
from __future__ import annotations

import json

from fx import Task, dd, family, merged

from . import _bank, _mods_a  # noqa: F401  (registers the bank)
from ._bank import MAIN, MODS, describe, run_hidden, run_visible, symptoms
from ._kit import GRADE_CMD, COMPANIES, enum, oxford, pick, score_script, team, unit_test

from . import _mods_b  # noqa: F401,E402

PROJECTS = [
    ("harbourdesk", "Harbourdesk", "the harbour office's back-office libraries"),
    ("tallyroom", "Tallyroom", "a sailing club's membership and booking libraries"),
    ("islandops", "Islandops", "operations code for a small island's services"),
    ("fieldnotes", "Fieldnotes", "helper libraries for a remote field station"),
    ("counterhand", "Counterhand", "tools used at the counter of a lab reception"),
    ("quayside", "Quayside", "quay and ferry operations code"),
    ("northgate", "Northgate", "the Northgate town hall utilities"),
    ("marketbox", "Marketbox", "a market-stall cooperative's toolkit"),
    ("lanternworks", "Lantern Works", "the shared libraries of a small games and media studio"),
]


def apply_bugs(mod, bugs):
    text = mod.core
    for b in bugs:
        if text.count(b.old) != 1:
            raise ValueError(f"{mod.key}/{b.key}: pattern not unique in the current text")
        text = text.replace(b.old, b.new)
    return text


def module_tree(mod, bugs):
    files = mod.src_files(None)
    files[f"src/{mod.key}/core.py"] = apply_bugs(mod, bugs)
    return files


def compatible(mod, b1, b2) -> bool:
    return b1.where != b2.where and b1.key != b2.key and b1.old not in b2.new and b2.old not in b1.new and (b1.old not in b2.old) and (b2.old not in b1.old)


def repo_readme(project, blurb, mods, extra=""):
    rows = "\n".join(f"| `src/{m.key}` | {m.title.split(': ', 1)[1]} |" for m in mods)
    return dd(f'''
        # {project}

        {blurb[0].upper() + blurb[1:]}. Each package lives in `src/<name>/` and has a `SPEC.md` that is its contract.

        | package | purpose |
        |---|---|
        {rows}

        Run the visible checks with `python3 -m unittest discover -s tests`. They are a sample, not the whole story:
        the `SPEC.md` files describe more behaviour than the tests exercise.
    ''') + extra


def base_start(project, blurb, mods, bugmap, with_visible=True):
    files = {"README.md": repo_readme(project, blurb, mods)}
    for m in mods:
        files.update(module_tree(m, bugmap.get(m.key, [])))
        if with_visible:
            files.update(m.visible_files())
    return files


def pick_bugs(rng, mod, count, d_only_public=False):
    pool = [b for b in mod.bugs if (not d_only_public or b.where in mod.names)]
    first = pick(rng, pool)
    chosen = [first]
    if count > 1:
        others = [b for b in pool if compatible(mod, first, b)]
        if others:
            chosen.append(pick(rng, others))
    return chosen


def hidden_units(mods):
    files, units = {}, []
    for m in mods:
        files.update(m.hidden_files())
        units.append(unit_test(m.key, m.hidden_path()))
    return files, units


# ------------------------------------------------------------------------------------------------ monorepo-fixes
OPENERS = [
    "The nightly build of {proj} is red and nobody has time to chase it package by package. {blurb}.",
    "{proj} freezes for release tomorrow. QA filed these against it, one per package, and I need all of them gone before the cut. ({blurb})",
    "Support has been collecting complaints about {proj}: {blurb}. Several unrelated packages seem to have drifted from their specs.",
    "I inherited {proj} from a colleague who left; it is {blurb}. A handful of packages misbehave and each needs its own fix.",
    "Can you get {proj} back in shape? It holds {blurb}, and some packages no longer do what their SPEC.md says.",
    "I'm handing the {proj} repository ({blurb}) to a team of agents. Every package listed below has at least one defect.",
]
NO_REPRO = ["somebody noticed wrong output but we never found a repro", "reported as 'off' by a user; nobody has an example",
            "flagged in review as suspicious, no failing case on record", "a customer complained, details lost"]


def fixes_prompt(rng, style, proj, blurb, mods, bugmap, sym):
    op = pick(rng, OPENERS).format(proj=proj, blurb=blurb)
    end = pick(rng, ["", "Fix the code, not the tests.", "The SPEC.md in each package is the reference.", "Don't change any public signature.",
                     "Every package has its own hidden checks beyond the visible tests.", "Leave the specs as they are."])
    if style == "reports":
        lines = []
        for m in mods:
            s = sym[m.key]
            lines.append(f"`{m.key}`: " + "; ".join(describe(x, rng.randrange(3)) for x in s[:2]))
        return f"{op}\n\nWhat we have so far:\n\n{enum(lines)}\n\n{end}".strip()
    if style == "mixed":
        lines = []
        for i, m in enumerate(mods):
            s = sym[m.key]
            if i % 2 == 0:
                lines.append(f"`{m.key}`: " + describe(s[0], rng.randrange(3)))
            else:
                lines.append(f"`{m.key}`: " + NO_REPRO[i % len(NO_REPRO)])
        return f"{op}\n\n{enum(lines)}\n\n{end}".strip()
    if style == "audit":
        names = oxford([f"`{m.key}`" for m in mods])
        return (f"{op} An audit flagged {names} as not matching their specifications, without saying how. "
                f"Read each package's SPEC.md, find what deviates and fix it. {end}").strip()
    if style == "terse":
        return f"Packages {oxford([m.key for m in mods])} in {proj} each have a bug (see their SPEC.md). Fix them all. {end}".strip()
    # "ticket"
    lines = []
    for i, m in enumerate(mods):
        s = sym[m.key]
        who = pick(rng, ["Support", "QA", "Finance", "Ops", "A user", "The night shift"])
        lines.append(f"{who} on `{m.key}`: " + describe(s[0], rng.randrange(3)))
    return f"{op}\n\nTickets:\n\n{enum(lines, 'numbered')}\n\n{end}".strip()


@family("swarm-monorepo-fixes", category="swarm", lang="python", kind="fix", n=16,
        summary="a monorepo of k small library packages, each with a different injected defect; score = fraction of packages whose hidden suite passes")
def monorepo_fixes(rng, n):
    keys = sorted(MODS)
    plan = [(3, "ticket"), (3, "reports"), (3, "terse"), (4, "ticket"), (4, "mixed"), (4, "audit"), (4, "reports"), (5, "mixed"),
            (5, "ticket"), (5, "audit"), (5, "terse"), (6, "mixed"), (7, "audit"), (6, "reports"), (3, "audit"), (7, "ticket")]
    for i in range(n):
        k, style = plan[i % len(plan)]
        k = min(k, len(keys))
        mods = [MODS[x] for x in rng.sample(keys, k)]
        double = k >= 5 and i % 2 == 0
        bugmap, sym = {}, {}
        for j, m in enumerate(mods):
            cnt = 2 if (double and j == 0) else 1
            bugmap[m.key] = pick_bugs(rng, m, cnt)
            if run_hidden(m, bugmap[m.key][0]).ok:
                raise RuntimeError(f"{m.key}: hidden tests miss {bugmap[m.key][0].key}")
            sym[m.key] = symptoms(m, bugmap[m.key][0])
        proj, disp, blurb = pick(rng, PROJECTS)
        start = base_start(disp, blurb, mods, bugmap)
        hidden, units = hidden_units(mods)
        hidden[".grade/score.py"] = score_script(units)
        solution = {}
        for m in mods:
            solution.update(m.solution_files())
        d = 3 if k <= 3 else 4 if k <= 5 else 5
        if style in ("audit", "terse") and d < 4:
            d += 1
        yield Task(
            slug=f"{i + 1:02d}-k{k}-{style}" + ("-double" if double else ""),
            prompt=fixes_prompt(rng, style, disp, blurb, mods, bugmap, sym),
            difficulty=d, start=start, hidden=hidden, solution=solution,
            verify=GRADE_CMD, pass_mode="json-score",
            team=team(rng, min(k, 6)),
            tags=["monorepo", "independent-components", style],
            notes={"packages": [m.key for m in mods], "bugs": {m.key: [b.key for b in bugmap[m.key]] for m in mods}, "style": style},
        )


# ------------------------------------------------------------------------------------------------ test-split
GOLD_PRELUDE = "import os, sys, unittest\nimport context  # noqa: F401\n\n"

MUT_UNIT = dd('''
    import json
    import math
    import os
    import re
    import shutil
    import subprocess
    import sys
    import tempfile

    DATA = json.loads(%(data)r)
    FORBIDDEN = [r"\\bopen\\s*\\(", r"\\binspect\\b", r"hashlib", r"__code__", r"co_code", r"\\bdis\\b", r"read_text", r"read_bytes", r"\\bpathlib\\b",
                 r"importlib", r"os\\.walk", r"os\\.listdir", r"getsource", r"linecache", r"\\bast\\b", r"sys\\.modules", r"__dict__"]


    def fail(msg):
        print("FAILED:", msg, file=sys.stderr)
        sys.exit(1)


    def run_tests(tree, key):
        p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_%%s.py" %% key], cwd=tree, capture_output=True, text=True,
                           timeout=60, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        return p.returncode, p.stderr


    def main(key):
        info = DATA[key]
        path = os.path.join("tests", "test_%%s.py" %% key)
        if not os.path.exists(path):
            fail("tests/test_%%s.py does not exist" %% key)
        text = open(path, encoding="utf-8").read()
        for pat in FORBIDDEN:
            if re.search(pat, text):
                fail("tests may exercise the package only through its public functions (found %%r)" %% pat)
        tmp = tempfile.mkdtemp()
        try:
            tree = os.path.join(tmp, "t")
            shutil.copytree(".", tree, ignore=shutil.ignore_patterns(".git", "__pycache__", ".grade"))
            core = os.path.join(tree, "src", key, "core.py")

            def with_core(src):
                with open(core, "w", encoding="utf-8") as f:
                    f.write(src)

            with_core(info["good"])
            code, err = run_tests(tree, key)
            m = re.search(r"Ran (\\d+) tests?", err)
            ran = int(m.group(1)) if m else 0
            sk = re.search(r"skipped=(\\d+)", err)
            skipped = int(sk.group(1)) if sk else 0
            if code != 0:
                fail("the tests fail on the correct package:\\n" + err[-600:])
            if ran - skipped < 3:
                fail("fewer than three tests actually ran")
            killed = 0
            for name, src in sorted(info["mutants"].items()):
                with_core(src)
                try:
                    code, _ = run_tests(tree, key)
                except subprocess.TimeoutExpired:
                    code = 0
                if code != 0:
                    killed += 1
            need = math.ceil(0.7 * len(info["mutants"]))
            print("%%s: %%d of %%d broken variants caught (need %%d)" %% (key, killed, len(info["mutants"]), need), file=sys.stderr)
            sys.exit(0 if killed >= need else 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


    main(sys.argv[1])
''')

CONTEXT_PY = dd('''
    """Import this first in a test file: it puts src/ on the import path."""
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
''')


@family("swarm-test-split", category="swarm", lang="python", kind="feature", n=10,
        summary="k untested packages; every package needs a test suite that catches hidden broken variants of it (one worker per package)")
def test_split(rng, n):
    keys = sorted(MODS)
    ks = [3, 3, 4, 4, 4, 5, 5, 3, 5, 4]
    for i in range(n):
        k = ks[i % len(ks)]
        mods = [MODS[x] for x in rng.sample(keys, k)]
        proj, disp, blurb = pick(rng, PROJECTS)
        start = {"README.md": repo_readme(disp, blurb, mods, extra=dd('''

            ## Tests

            Tests go in `tests/test_<package>.py` (one file per package, standard `unittest`). Start every file with `import context` (it puts `src/` on the
            import path) and then import the package normally. Run them all with `python3 -m unittest discover -s tests`.
            A test file may exercise a package only through its public functions: it must not open or inspect the package's source files.
        ''')), "tests/context.py": CONTEXT_PY}
        for m in mods:
            start.update(m.src_files(None))
        data, hidden = {}, {}
        units = []
        solution = {}
        for m in mods:
            data[m.key] = {"good": m.core, "mutants": {b.key: m.core_with(b) for b in m.bugs}}
            for b in m.bugs:
                if run_hidden(m, b).ok:
                    raise RuntimeError(f"{m.key}/{b.key} not caught")
            body = GOLD_PRELUDE + m.hidden + MAIN
            solution[f"tests/test_{m.key}.py"] = body
            units.append({"name": f"tests for {m.key}", "cmd": ["python3", ".grade/mut_unit.py", m.key], "weight": 1, "timeout": 120})
        hidden[".grade/mut_unit.py"] = MUT_UNIT % {"data": json.dumps(data, sort_keys=True)}
        hidden[".grade/score.py"] = score_script(units)
        voices = [
            f"{disp} ({blurb}) has {k} packages and not a single test. Before anyone refactors them I want a real safety net: a test file per package that would "
            f"notice if someone broke the behaviour described in its SPEC.md. We'll check your suites against deliberately broken copies of each package, "
            f"and they must of course pass on the real one.",
            f"Write the missing tests for {oxford([m.key for m in mods])} (tests/test_<package>.py, see the README for the layout). They are judged by how many hidden "
            f"broken variants of each package they catch, so cover the documented edge cases and error behaviour, not just the happy path.",
            f"Test-writing sprint: one thorough unittest file for each package under src/. The SPEC.md next to each package is the contract. A suite that passes on the "
            f"current code but would also pass on a subtly broken package is not good enough.",
            f"Nobody trusts the {oxford([m.key for m in mods])} packages because they have no tests. Please add suites that pin down every rule in the SPEC.md files "
            f"(boundaries, rounding, ordering, errors). Quality is measured against mutated copies of the code.",
        ]
        d = 3 if k <= 3 else 4 if k <= 4 else 5
        yield Task(
            slug=f"{i + 1:02d}-k{k}-" + mods[0].key,
            prompt=voices[i % len(voices)], difficulty=d, start=start, hidden=hidden, solution=solution,
            verify=GRADE_CMD, pass_mode="json-score", timeout_s=600,
            team=team(rng, min(k, 6), ["tester", "backend"] if i % 2 else ["tester", "reviewer"]),
            tags=["tests", "mutation-scored", "independent-components"],
            notes={"packages": [m.key for m in mods], "mutants": {m.key: len(m.bugs) for m in mods}},
        )


# ------------------------------------------------------------------------------------------------ review-fix
REVIEW_CHECK = dd('''
    import json
    import re
    import sys

    TRUTH = set(json.loads(%(truth)r))
    text = open("REVIEW.md", encoding="utf-8").read() if __import__("os").path.exists("REVIEW.md") else ""
    found = set()
    for line in text.splitlines():
        m = re.match(r"^\\s*[-*]\\s+`?([a-z][a-z0-9]*)\\.([A-Za-z_][A-Za-z0-9_]*)`?\\s*:", line)
        if m:
            found.add(m.group(1) + "." + m.group(2))
    if found != TRUTH:
        print("FAILED: REVIEW.md lists %%s; missing %%s, not defective %%s" %% (sorted(found), sorted(TRUTH - found), sorted(found - TRUTH)), file=sys.stderr)
        sys.exit(1)
''')


def review_ok(b):
    w = b.where
    return w.isidentifier() and not w.startswith("_") and not w.isupper()


@family("swarm-review-fix", category="swarm", lang="python", kind="fix", n=10,
        summary="review k+decoys packages against their specs, list exactly the defective functions in REVIEW.md, and fix them")
def review_fix(rng, n):
    keys = sorted(MODS)
    plan = [(3, 1), (3, 2), (4, 1), (4, 2), (5, 1), (3, 1), (4, 2), (5, 2), (6, 2), (4, 3)]
    for i in range(n):
        k, decoys = plan[i % len(plan)]
        picked = rng.sample(keys, k + decoys)
        bad = [MODS[x] for x in picked[:k]]
        clean = [MODS[x] for x in picked[k:]]
        bugmap, truth = {}, []
        for m in bad:
            pool = [b for b in m.bugs if review_ok(b)]
            b = pick(rng, pool)
            if run_hidden(m, b).ok:
                raise RuntimeError(f"{m.key}/{b.key} not caught")
            bugmap[m.key] = [b]
            truth.append(f"{m.key}.{b.where}")
        mods = bad + clean
        rng.shuffle(mods)
        proj, disp, blurb = pick(rng, PROJECTS)
        start = base_start(disp, blurb, mods, bugmap)
        start["REVIEW.md"] = dd('''
            # Review

            (Replace this with the findings: one line per defect, in exactly this form, where `package` is the directory under `src/` and `function` the function or
            method that contains the defect, without the class name:)

            - `package.function`: what is wrong, in a sentence.
        ''')
        hidden, units = hidden_units(bad + clean)
        # one unit per package for the hidden behaviour (clean packages stay clean: a regression there fails its unit too)
        hidden[".grade/review_check.py"] = REVIEW_CHECK % {"truth": json.dumps(sorted(truth))}
        units.append({"name": "review lists exactly the defective functions", "cmd": ["python3", ".grade/review_check.py"], "weight": max(1, (k + 1) // 2)})
        hidden[".grade/score.py"] = score_script(units)
        solution = {}
        for m in bad:
            solution.update(m.solution_files())
        solution["REVIEW.md"] = "# Review\n\n" + "\n".join(f"- `{t}`: deviates from its SPEC.md." for t in sorted(truth)) + "\n"
        names = oxford([m.key for m in mods])
        voices = [
            f"{disp} had {len(mods)} packages delivered by a contractor ({names}) and QA thinks some of them contain defects, not all. "
            f"Please review every package against its SPEC.md and write REVIEW.md listing exactly the defective functions (the format is in the file), "
            f"then fix them. Listing a function that is fine counts against you.",
            f"Code review plus repair: {len(mods)} packages under src/, an unknown number of them broken (exactly one function each at most). Read the specs, find the "
            f"defects, record them in REVIEW.md in the given format, and fix the code. Packages that are correct must stay untouched.",
            f"A reviewer should go through {names} and report the defects, an implementer should fix them. The report goes into REVIEW.md, one line per defective "
            f"function. I will compare it with what is really wrong, so be precise.",
        ]
        d = 4 if k <= 4 else 5
        yield Task(
            slug=f"{i + 1:02d}-k{k}-decoy{decoys}",
            prompt=voices[i % len(voices)], difficulty=d, start=start, hidden=hidden, solution=solution,
            verify=GRADE_CMD, pass_mode="json-score",
            team=team(rng, min(k + 1, 6), ["reviewer", "backend"] if i % 2 else ["reviewer", "backend", "tester"]),
            tags=["review", "fix", "precision"],
            notes={"defective": sorted(truth), "clean": [m.key for m in clean]},
        )
