"""Brute-force algorithms that need a better algorithm (python): the check counts executed lines inside the package, not seconds."""
from __future__ import annotations

import math
import random
from string import Template

from fx import Task, dd, family, merged, run

from ._kit import PY_ALL, PY_CORRECT, PY_PERF, prove_opt
from ._py_lines import TEXT as LINEMETER

from ._alg_shapes import SHAPES

PKGS = ["harborops", "datajobs", "faretools", "opsmath", "batchcalc", "buildgraph", "nightly", "ledgerlab"]
MODS = ["core", "algos", "compute", "queries", "analysis"]

PROMPTS = [
    "`{f}` in `{path}` gives the right answers, but its work explodes with the input: the nightly job feeds it {size} and never finishes. {doc} Rewrite it with a better algorithm "
    "({want} is what we are after). The signature and the results must stay exactly the same. There is no stopwatch in the check: it counts the Python lines executed inside the "
    "`{pkg}` package on a large input, with a budget that leaves a sensible solution plenty of room, so only a real improvement in complexity will get under it.",
    "perf: `{f}` ({path}). {doc} It is hopeless for {size}. Keep the contract in the README but change the algorithm (target: {want}). "
    "The grader counts executed lines in `{pkg}/` instead of seconds, so shaving a constant factor will not be enough.",
    "Could you speed up `{f}` in `{path}`? {doc} Profiling says the algorithm itself is the problem: it is the brute-force version and with {size} it needs orders of magnitude more "
    "steps than a good solution. Same inputs, same outputs, same signature. Target complexity: {want}. The check counts how many lines of `{pkg}` get executed on a big input and "
    "compares that with a budget.",
]


def test_text(sp, f, nargs, which, seed, n, pkg, mod, limit):
    names = ["a", "b", "c", "d"][:nargs]
    header = (f"import copy\nimport importlib\nimport os\nimport random\nimport unittest\n\nfrom linemeter import BudgetExceeded, LineMeter\nfrom {pkg}.{mod} import {f}\n\n\n"
              f"{sp['oracle']}\n\n{sp['gen']}\n\n")
    if which == "correct":
        return header + dd(f'''
        class CorrectnessTests(unittest.TestCase):
            def test_matches_the_reference_on_random_inputs(self):
                rng = random.Random({seed})
                for _ in range(150):
                    args = small_args(rng)
                    self.assertEqual({f}(*copy.deepcopy(args)), oracle(*copy.deepcopy(args)), args)

            def test_inputs_are_not_modified(self):
                rng = random.Random({seed + 1})
                for _ in range(40):
                    args = small_args(rng)
                    before = copy.deepcopy(args)
                    {f}(*args)
                    self.assertEqual(args, before)
        ''')
    return header + dd(f'''
    PACKAGE_DIR = os.path.dirname(os.path.abspath(importlib.import_module("{pkg}").__file__))
    LIMIT = {limit}


    class PerformanceTests(unittest.TestCase):
        def test_executed_lines_stay_within_budget(self):
            rng = random.Random({seed})
            n = {n}
            args = big_args(rng, n)
            expected = oracle(*copy.deepcopy(args))
            meter = LineMeter(PACKAGE_DIR, budget=2 * LIMIT)
            try:
                with meter:
                    got = {f}(*copy.deepcopy(args))
            except BudgetExceeded:
                self.fail("PERF: still running after %d executed lines of {pkg} code (budget %d) on an input of size %d: the algorithm does far too much work" % (meter.lines, LIMIT, n))
            self.assertEqual(got, expected)
            self.assertLessEqual(meter.lines, LIMIT, "PERF: %d executed lines of {pkg} code on an input of size %d (budget %d): the algorithm does too much work" % (meter.lines, n, LIMIT))
    ''')


def calib_text(sp, f, seed, n, pkg, mod):
    return (f"import importlib, os, random\nfrom linemeter import LineMeter\nfrom {pkg}.{mod} import {f}\n\n{sp['gen']}\n\n"
            f"root = os.path.dirname(os.path.abspath(importlib.import_module('{pkg}').__file__))\nargs = big_args(random.Random({seed}), {n})\n"
            f"m = LineMeter(root)\nwith m:\n    {f}(*args)\nprint('LINES', m.lines)\n")


@family("optimize-py-algorithms", category="optimize", lang="python", kind="feature", n=18,
        summary="brute-force batch computations with invented domain rules (berth occupancy, fare caps, ledger as-of balances, rebuild sets, alert escalation, fair shares, trailing top-3) that need a better algorithm: a budget on executed lines, not seconds")
def gen(rng, n):
    keys = list(SHAPES)
    rng.shuffle(keys)
    extra = [k for k in keys if SHAPES[k]["d"] >= 4]
    rng.shuffle(extra)
    order = keys + extra
    used = set()
    for i in range(n):
        shape = order[i % len(order)]
        sp = SHAPES[shape]
        vocab = [v for v in sp["vocab"] if (shape, v[0]) not in used] or sp["vocab"]
        f, argn, doc = rng.choice(vocab)
        used.add((shape, f))
        pkg, mod = rng.choice(PKGS), rng.choice(MODS)
        names = {"f": f, "doc": doc, "a": argn[0], "b": argn[1] if len(argn) > 1 else "", "c": argn[2] if len(argn) > 2 else "", "d": argn[3] if len(argn) > 3 else ""}
        naive = Template(sp["naive"]).substitute(names)
        fast = Template(sp["fast"]).substitute(names)
        helper = dd('''
        def describe(count, noun):
            """Pluralised count for log lines."""
            return "%d %s%s" % (count, noun, "" if count == 1 else "s")
        ''')
        head = f'"""{pkg}: calculations used by the nightly batch jobs."""\n'
        start_src = head + "\n\n" + naive + "\n\n" + helper
        sol_src = head + sp["imports"] + "\n\n" + fast + "\n\n" + helper
        spec = sp["spec"].format(a=names["a"], b=names["b"], c=names["c"], d=names["d"])
        readme = dd(f'''
        # {pkg}

        ## `{mod}.{f}({", ".join(argn)})`

        {doc}

        {spec}

        The batch job calls it with large inputs, so the amount of work has to grow slowly with their size. The function must not modify its arguments.
        ''')
        files = {f"{pkg}/{mod}.py": start_src, f"{pkg}/__init__.py": "", "README.md": readme}
        ns = {}
        exec(sp["oracle"], ns)
        exec(sp["gen"], ns)
        r = random.Random(100 + i)
        ex = []
        while len(ex) < 3:
            args = ns["small_args"](r)
            if len(ex) == 0 or any(a for a in args):
                ex.append((args, ns["oracle"](*args)))
        vis = [f"import unittest\n\nfrom {pkg}.{mod} import {f}\n\n\nclass BasicTests(unittest.TestCase):\n"]
        for k, (args, want) in enumerate(ex):
            vis.append(f"    def test_example_{k + 1}(self):\n        self.assertEqual({f}({', '.join(repr(a) for a in args)}), {want!r})\n")
        vis.append("\nif __name__ == '__main__':\n    unittest.main()\n")
        seed = 2000 + i
        lo, hi = sp["n"]
        size = rng.choice(sorted({lo, (lo + hi) // 2, hi}))
        big = ns["big_args"](random.Random(seed), size)
        limit = int(eval(sp["limit"], {"n": size, "args": big, "len": len, "sum": sum}))
        corr = test_text(sp, f, len(argn), "correct", seed, size, pkg, mod, limit)
        perf = test_text(sp, f, len(argn), "perf", seed, size, pkg, mod, limit)
        hidden = {"tests/linemeter.py": LINEMETER, "tests/test_correct_lines.py": corr, "tests/test_perf_lines.py": perf}
        start = {**files, "tests/test_basic.py": "".join(vis)}
        solution = {f"{pkg}/{mod}.py": sol_src}
        # calibration: the reference must use at most a third of the budget
        r = run(merged(start, hidden, solution, {"calib.py": calib_text(sp, f, seed, size, pkg, mod)}), "python3 -c \"import sys; sys.path.insert(0, 'tests'); exec(open('calib.py').read())\"", timeout=180)
        if "LINES" not in r.out:
            raise RuntimeError(f"{shape}/{f}: calibration failed:\n{r.out[-1500:]}")
        used_lines = int(r.out.split("LINES")[1].split()[0])
        if used_lines * 3 > limit:
            raise RuntimeError(f"{shape}/{f}: reference uses {used_lines} lines, budget {limit} leaves less than 3x headroom")
        prove_opt(f"{shape}/{f}", start, hidden, solution, PY_CORRECT, PY_PERF, PY_ALL, timeout=240)
        sizetxt = sp["size"].format(n=f"{size:,}", q=f"{size // 2:,}")
        prompt = rng.choice(PROMPTS).format(f=f, path=f"{pkg}/{mod}.py", doc=doc, size=sizetxt, want=sp["want"], pkg=pkg)
        yield Task(slug=f"{i + 1:02d}-{shape}-{f}", prompt=prompt, difficulty=sp["d"], start=start, hidden=hidden, solution=solution, verify=PY_ALL, timeout_s=300,
                   tags=["algorithms", "complexity", "line-budget"], notes={"shape": shape, "n": size, "limit": limit, "reference_lines": used_lines})
