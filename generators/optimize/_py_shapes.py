"""Engine for python optimize families built from *shapes*: a slow implementation, a fast one, an oracle, and a counting test."""
from __future__ import annotations

import random
from string import Template

from fx import Task, dd

from ._kit import PY_ALL, PY_CORRECT, PY_PERF, prove_opt
from ._py_counting import TEXT as COUNTING


def test_text(sp, f, nargs, which, seed, n, pkg, mod, cfg):
    names = ["a", "b"][:nargs]
    arg_list = ", ".join(names)
    tail = "," if nargs == 1 else ""
    factor = sp.get("factor", cfg["factor"])
    metric = sp.get("metric", cfg["metric"])
    header = (f"import copy\nimport random\nimport unittest\n\nfrom counting import BudgetExceeded, Counted, Ops, ShiftList, Tracked as T, CountingSeq as Seq, plain\nfrom {pkg}.{mod} import {f}\n\n\n{sp.get('prelude', '')}\n\n{sp['oracle']}\n\n")
    common = dd(f'''
    def wrap({arg_list}):
        return ({sp["wrap"]}{tail})
    ''')
    if which == "correct":
        return header + common + "\n" + dd(f'''
        def small_args(rng):
            return ({sp["small"]}{tail})


        class CorrectnessTests(unittest.TestCase):
            def test_matches_the_reference_on_random_inputs(self):
                rng = random.Random({seed})
                for _ in range(120):
                    args = small_args(rng)
                    self.assertEqual({f}(*copy.deepcopy(args)), oracle(*copy.deepcopy(args)), args)

            def test_works_with_instrumented_values(self):
                rng = random.Random({seed + 1})
                for _ in range(40):
                    args = small_args(rng)
                    self.assertEqual(plain({f}(*wrap(*copy.deepcopy(args)))), oracle(*copy.deepcopy(args)), args)

            def test_empty_inputs(self):
                empty = {sp.get("empty_args", "tuple([] for _ in range(" + str(nargs) + "))")}
                self.assertEqual({f}(*copy.deepcopy(empty)), oracle(*copy.deepcopy(empty)))
        ''')
    return header + common + "\n" + dd(f'''
    def big_args(rng, n):
        return ({sp["big"]}{tail})


    class PerformanceTests(unittest.TestCase):
        def test_cost_grows_with_the_input(self):
            rng = random.Random({seed})
            n = {n}
            args = big_args(rng, n)
            wrapped = wrap(*copy.deepcopy(args))
            limit = {factor} * n
            Ops.reset()
            Ops.budget = limit * 20
            try:
                got = {f}(*wrapped)
            except BudgetExceeded:
                self.fail("PERF: gave up after %d {cfg["unit"]} for %d items (limit %d): {cfg["hint"]}" % (Ops.budget, n, limit))
            finally:
                Ops.budget = None
            ops = {metric}
            self.assertEqual(plain(got), oracle(*copy.deepcopy(args)))
            self.assertLessEqual(ops, limit, "PERF: %d {cfg["unit"]} for %d items (limit %d): {cfg["hint"]}" % (ops, n, limit))
    ''')


def shape_family(rng, n, shapes, cfg):
    order = list(shapes) * 4
    rng.shuffle(order)
    used = set()
    for i in range(n):
        shape = order[i]
        sp = shapes[shape]
        vocab = [v for v in sp["vocab"] if (shape, v[0]) not in used] or sp["vocab"]
        f, argn, doc = rng.choice(vocab)
        used.add((shape, f))
        pkg = rng.choice(cfg["pkgs"])
        mod = rng.choice(cfg["mods"])
        names = {"f": f, "doc": doc, "a": argn[0], "b": argn[1] if len(argn) > 1 else ""}
        naive = Template(sp["naive"]).substitute(names)
        fast = Template(sp["fast"]).substitute(names)
        helper = dd('''
        def describe(count, noun):
            """Pluralised count for log lines."""
            return "%d %s%s" % (count, noun, "" if count == 1 else "s")
        ''')
        head = f'"""{pkg}: small helpers used by the batch jobs."""\n' + sp.get("imports", "") + "\n\n"
        start_src = head + naive + "\n\n" + helper
        sol_src = head + fast + "\n\n" + helper
        spec = sp["spec"].format(a=argn[0], b=argn[1] if len(argn) > 1 else "")
        readme = dd(f'''
        # {pkg}

        ## `{mod}.{f}({", ".join(argn)})`

        {doc}

        {spec}

        {cfg["readme_note"]}
        ''')
        files = {f"{pkg}/{mod}.py": start_src, f"{pkg}/__init__.py": "", "README.md": readme}
        ns = {}
        exec(sp.get("prelude", ""), ns)
        exec(sp["oracle"], ns)
        r = random.Random(100 + i)
        if sp.get("callable"):
            tail1 = "," if len(argn) == 1 else ""
            vis_text = (f"import random\nimport unittest\n\nfrom {pkg}.{mod} import {f}\n\n\n{sp.get('prelude', '')}\n\n{sp['oracle']}\n\n\n"
                        f"def small_args(rng):\n    return ({sp['small']}{tail1})\n\n\nclass BasicTests(unittest.TestCase):\n"
                        f"    def test_small_examples(self):\n        rng = random.Random({7 + i})\n        for _ in range(5):\n"
                        f"            args = small_args(rng)\n            self.assertEqual({f}(*args), oracle(*args))\n\n\nif __name__ == '__main__':\n    unittest.main()\n")
        else:
            ex = []
            for _ in range(3):
                args = eval("(" + sp["small"] + ",)", {"rng": r, "Seq": lambda x: x})
                ex.append((args, ns["oracle"](*args)))
            vis = [f"import unittest\n\nfrom {pkg}.{mod} import {f}\n\n\nclass BasicTests(unittest.TestCase):\n"]
            for k, (args, want) in enumerate(ex):
                vis.append(f"    def test_example_{k + 1}(self):\n        self.assertEqual({f}({', '.join(repr(a) for a in args)}), {want!r})\n")
            vis.append("\nif __name__ == '__main__':\n    unittest.main()\n")
            vis_text = "".join(vis)
        seed = 1000 + i
        lo, hi = sp.get("n", cfg["n"])
        n_items = rng.choice([lo, (lo + hi) // 2, hi])
        corr = test_text(sp, f, len(argn), "correct", seed, n_items, pkg, mod, cfg)
        perf = test_text(sp, f, len(argn), "perf", seed, n_items, pkg, mod, cfg)
        hidden = {"tests/counting.py": COUNTING, "tests/test_correct_ops.py": corr, "tests/test_perf_ops.py": perf}
        start = {**files, "tests/test_basic.py": vis_text}
        solution = {f"{pkg}/{mod}.py": sol_src}
        prove_opt(f"{shape}/{f}", start, hidden, solution, PY_CORRECT, PY_PERF, PY_ALL)
        prompt = rng.choice(cfg["prompts"]).format(f=f, path=f"{pkg}/{mod}.py", doc=doc)
        yield Task(slug=f"{i + 1:02d}-{shape}-{f}", prompt=prompt, difficulty=sp["d"], start=start, hidden=hidden, solution=solution, verify=PY_ALL,
                   tags=cfg["tags"], notes={"shape": shape, "n": n_items, "factor": sp.get("factor", cfg["factor"])})
