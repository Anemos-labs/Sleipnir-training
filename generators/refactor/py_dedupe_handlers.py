"""De-duplication refactors (python): copy-pasted handlers become one generic function plus data."""
from __future__ import annotations

import json
import pprint

from fx import Task, dd, family

from . import _kit
from ._kit import prove, py_behaviour, py_structlib
from ._py_handlers import SKELETONS, start_module

structlib = _kit.load_structlib()

PROMPTS = [
    "The {unit}s in `{path}` ({k} of them) were created by copy and paste: they share all of their logic and differ in a few constants "
    "and, in places, one extra check. Every new {what} means another 15 lines of copied code and the copies have already started to drift. "
    "Refactor so the shared logic exists once and the differences are data (or at most a line or two of code per {what}). "
    "All {k} public functions must keep their names, signatures, results and error behaviour.",
    "dedupe `{path}`: {k} near-identical {unit}s. one shared implementation, per-{what} settings in a table, keep the public function names. tests must pass",
    "Reviewer note: \"I diffed `{path}` and the {k} {unit}s are the same function with different numbers. Please collapse them.\" "
    "Keep each existing function importable under its current name with the same behaviour (including the exceptions), but don't leave "
    "copy-pasted bodies behind.",
    "We want to add a new {what} to the {topic} code next week and I refuse to paste the same block a {n1}th time. Refactor `{path}` first: "
    "the repeated logic goes into one place, and what differs per {what} lives in a small table or parameters. Existing callers import the current "
    "function names, so keep those working exactly as they do today.",
    "`{path}` contains {k} functions that are the same code with a different set of constants, plus an extra `if` in some of them. Remove the duplication "
    "without changing behaviour: same names, same return values, same exceptions with the same messages. A good result makes adding another {what} a "
    "one-row change.",
]


def _loc_of(files, extra=""):
    total = 0
    for rel, text in files.items():
        if rel.endswith(".py") and not rel.startswith("tests/"):
            total += sum(1 for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#"))
    return total


@family("refactor-py-dedupe-handlers", category="refactor", lang="python", kind="refactor", n=12,
        summary="collapse copy-pasted handler functions (billing, feeds, stock moves, quotes, retries) into one implementation plus data")
def gen(rng, n):
    order = list(SKELETONS) * 3
    rng.shuffle(order)
    for i in range(n):
        sk = order[i]
        k = min(rng.choice([3, 4, 4, 5, 5, 6, 7]), len(sk.names))
        variants, taken = [], set()
        for j in range(k):
            for _ in range(40):
                v = sk.variant(rng, taken)
                if j >= 2 or not sk.extras(v):
                    break
            taken.add(v["name"])
            variants.append(v)
        start_src = start_module(sk, variants)
        sol_src = sk.solution(sk, variants)
        init = f"{sk.package}/__init__.py"
        start_files = {sk.path: start_src, init: ""}
        cases = sk.cases(rng, variants, 30)
        want = _kit.py_golden(start_files, sk.harness, cases)
        beh = py_behaviour(start_files, sk.harness, cases, "recorded")
        vis_cases = [c for c, w in zip(cases, want) if not (isinstance(w, dict) and "raises" in w)][:3]
        vis_want = [w for w in want if not (isinstance(w, dict) and "raises" in w)][:3]
        err = [(c, w) for c, w in zip(cases, want) if isinstance(w, dict) and "raises" in w][:1]
        vis = ["import unittest", "", sk.harness.rstrip("\n"), "", "def norm(x):", "    return json.loads(json.dumps(x))", "", "", f"class {sk.module.title()}Tests(unittest.TestCase):"]
        for t, (c, w) in enumerate(zip(vis_cases, vis_want)):
            vis += [f"    def test_example_{t + 1}(self):", f"        case = json.loads({json.dumps(json.dumps(c))})",
                    f"        self.assertEqual(norm(run_case(case)), json.loads({json.dumps(json.dumps(w))}))", ""]
        for c, w in err:
            vis += ["    def test_error_example(self):", f"        case = json.loads({json.dumps(json.dumps(c))})",
                    "        with self.assertRaises(Exception) as caught:", "            run_case(case)",
                    f"        self.assertEqual(type(caught.exception).__name__, {w['raises']!r})", ""]
        vis += ["", "if __name__ == '__main__':", "    unittest.main()", ""]
        vis_text = "import json\n" + "\n".join(vis)
        start = {**start_files, f"tests/test_{sk.module}.py": vis_text}
        start_loc, sol_loc = _loc_of(start_files), _loc_of({sk.path: sol_src})
        max_loc = int(sol_loc * 1.3) + 2
        loc_check = max_loc < start_loc * 0.9
        extras_n = sum(1 for v in variants if sk.extras(v))
        struct = dd(f'''
        import unittest

        import structlib as S

        MAX_TOTAL_LOC = {max_loc if loc_check else 10**6}
        EXPECTED_FUNCTIONS = {json.dumps(sorted(v["fn"] for v in variants))}


        class StructureTests(unittest.TestCase):
            def test_no_copy_pasted_functions(self):
                groups = S.duplicate_functions(S.py_files("."), min_stmts=5)
                self.assertFalse(groups, "functions with the same body shape are still duplicated: %s" % groups)

            def test_public_functions_remain(self):
                import ast
                names = set()
                for rel in S.py_files("."):
                    names |= {{n.name for n in S.parse(rel).body if isinstance(n, ast.FunctionDef)}}
                missing = [f for f in EXPECTED_FUNCTIONS if f not in names]
                self.assertFalse(missing, "public functions disappeared: %s" % missing)

            def test_code_got_smaller(self):
                total = 0
                for rel in S.py_files("."):
                    total += sum(1 for ln in S.read(rel).splitlines() if ln.strip() and not ln.strip().startswith("#"))
                self.assertLessEqual(total, MAX_TOTAL_LOC, "the package still has %d lines of code (limit %d)" % (total, MAX_TOTAL_LOC))
        ''')
        hidden = {"tests/test_more_behaviour.py": beh, "tests/test_zz_structure.py": struct, **py_structlib()}
        solution = {sk.path: sol_src}
        prove(f"{sk.key}", start, hidden, solution, _kit.PY_BEHAVIOUR_CMD, _kit.PY_STRUCT_CMD, "python3 -m unittest discover -s tests")
        d = 1 if (k == 3 and extras_n == 0) else 2 if (k <= 5 and extras_n <= 1) else 3 if extras_n < 3 or k < 7 else 4
        what = {"makerspace": "machine", "garden": "event kind", "seedbank": "stock movement", "courier": "carrier", "retry": "policy"}[sk.key]
        prompt = rng.choice(PROMPTS).format(unit=sk.unit, path=sk.path, k=k, what=what, topic=sk.topic, n1=k + 1)
        yield Task(slug=f"{i + 1:02d}-{sk.key}-{k}x", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution,
                   verify="python3 -m unittest discover -s tests -v", tags=["deduplication", "copy-paste"],
                   notes={"skeleton": sk.key, "handlers": [v["name"] for v in variants], "extras": extras_n})
