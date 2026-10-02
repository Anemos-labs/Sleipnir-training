"""Doctests (python): every public function gets runnable examples; the hidden check runs them and verifies the code is untouched."""
from __future__ import annotations

import json

from fx import Task, dd, family

from . import _pymods as P
from ._docscheck import TEXT as DOCSCHECK
from ._kit import prove_docs

CMD = "python3 -m unittest discover -s tests -v"


def run_ns(mod, funcs):
    ns = {}
    exec(P.source(mod, funcs), ns)
    return ns


def eval_example(ns, expr):
    try:
        return "ok", repr(eval(expr, dict(ns)))
    except Exception as e:  # noqa: BLE001
        return "err", (type(e).__name__, str(e))


def make_doc(f, ns, n_ex, with_err):
    lines = [f.summary, ""]
    exs = f.examples[:n_ex] if f.examples else []
    for expr in exs:
        state, out = eval_example(ns, expr)
        assert state == "ok", (f.name, expr, out)
        lines += [f">>> {expr}", out]
    if with_err:
        for expr in f.errors[:1]:
            state, out = eval_example(ns, expr)
            assert state == "err", (f.name, expr)
            exc, msg = out
            lines += [f">>> {expr}", "Traceback (most recent call last):", "    ...", f"{exc}: {msg}"]
    return "\n".join(lines)


PROMPTS = [
    "The functions in `{path}` are all documented with a one-line summary but no examples, and the docs build keeps being criticised for it. Add doctest examples to the docstring of every "
    "public function: at least {n_ex} per function, and for functions that raise on bad input, one example that shows the exception (a `Traceback` block). The examples must pass under "
    "`python -m doctest`. Do not change any code, only docstrings.",
    "docs: add runnable `>>>` examples to every public function in `{path}` ({n_ex}+ each; show the error for the ones that raise). They have to pass with doctest. Docstrings only, no code changes.",
    "New contributors can't tell how the helpers in `{path}` are called. Please give every public function at least {n_ex} doctest examples with correct output{err_clause}. "
    "The module's behaviour must not change, and `python -m doctest {path}` should be green.",
    "Review feedback on the {topic} module `{path}`: \"no examples anywhere.\" Add doctests ({n_ex} or more per public function{err_clause}). Keep the code untouched; the doctests are run in CI together with the unit tests.",
]


@family("docs-py-doctests", category="docs", lang="python", kind="feature", n=6,
        summary="add passing doctest examples (including error examples) to every public function of a small module; code must stay unchanged")
def gen(rng, n):
    mods = list(P.MODULES) * 3
    rng.shuffle(mods)
    for i in range(n):
        mod = mods[i]
        k = rng.choice([3, 4, 5, 6, 7])
        funcs = P.pick(mod, rng, k)
        n_ex = rng.choice([2, 2, 3])
        want_err = rng.random() < 0.6
        n_ex = min(n_ex, min(len(f.examples) + (1 if want_err and f.errors else 0) for f in funcs))
        ns = run_ns(mod, funcs)
        start_docs = {f.name: f.summary for f in funcs}
        start_src = P.source(mod, funcs, start_docs)
        sol_docs = {f.name: make_doc(f, ns, n_ex, want_err) for f in funcs}
        sol_src = P.source(mod, funcs, sol_docs)
        path = f"{mod.pkg}/{mod.mod}.py"
        files = {path: start_src, f"{mod.pkg}/__init__.py": ""}
        # visible tests: plain behaviour checks (pass before and after)
        vis_lines = [f"import unittest\n\nfrom {mod.pkg}.{mod.mod} import *\n\n\nclass BehaviourTests(unittest.TestCase):\n"]
        for j, f in enumerate(funcs[:3]):
            ex = f.examples[0]
            state, out = eval_example(ns, ex)
            vis_lines.append(f"    def test_{f.name}(self):\n        self.assertEqual({ex}, {out})\n")
        vis_lines.append("\nif __name__ == '__main__':\n    unittest.main()\n")
        start = {**files, "tests/test_behaviour.py": "".join(vis_lines)}
        original_dumps = {}
        import ast
        tree = ast.parse(P.source(mod, funcs))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                original_dumps[node.name] = ast.dump(node)
        needs_err = {f.name: bool(f.errors) and want_err for f in funcs}
        raises = {f.name: sorted(f.raises) for f in funcs}
        check = DOCSCHECK + "\n"
        test = dd(f'''
        import ast
        import doctest
        import importlib
        import unittest

        import docscheck as D

        PATH = {json.dumps(path)}
        MODULE = {json.dumps(mod.pkg + "." + mod.mod)}
        MIN_EXAMPLES = {n_ex}
        NEEDS_ERROR_EXAMPLE = {needs_err!r}
        RAISES = {json.dumps(raises)}
        ORIGINAL = {json.dumps(original_dumps)}


        class DocTests(unittest.TestCase):
            def setUp(self):
                self.tree = D.parse(PATH)

            def test_code_is_unchanged(self):
                now = {{n.name: D.stripped_dump(n) for n in self.tree.body if isinstance(n, ast.FunctionDef)}}
                self.assertEqual(now, ORIGINAL, "only docstrings may change")

            def test_every_public_function_has_enough_examples(self):
                parser = doctest.DocTestParser()
                short = []
                for fn in D.public_functions(self.tree):
                    doc = ast.get_docstring(fn) or ""
                    n = len(parser.get_examples(doc))
                    if n < MIN_EXAMPLES:
                        short.append("%s has %d example(s), needs %d" % (fn.name, n, MIN_EXAMPLES))
                self.assertFalse(short, "\\n".join(short))

            def test_functions_that_raise_show_the_error(self):
                missing = []
                parser = doctest.DocTestParser()
                for fn in D.public_functions(self.tree):
                    if not NEEDS_ERROR_EXAMPLE.get(fn.name):
                        continue
                    examples = parser.get_examples(ast.get_docstring(fn) or "")
                    excs = [ex.exc_msg for ex in examples if ex.exc_msg]
                    if not any(any(e.startswith(r) for r in RAISES[fn.name]) for e in excs):
                        missing.append(fn.name)
                self.assertFalse(missing, "no example shows the exception for: %s" % missing)

            def test_doctests_pass(self):
                module = importlib.import_module(MODULE)
                result = doctest.testmod(module, verbose=False)
                self.assertEqual(result.failed, 0, "%d doctest(s) fail" % result.failed)
                self.assertGreaterEqual(result.attempted, MIN_EXAMPLES * len(D.public_functions(self.tree)))
        ''')
        hidden = {"tests/docscheck.py": check, "tests/test_docs_doctests.py": test}
        solution = {path: sol_src}
        prove_docs(f"{mod.key}-{len(funcs)}", start, hidden, solution, CMD, "python3 -m unittest discover -s tests -p 'test_beh*.py'")
        d = 1 if (len(funcs) <= 3 and not want_err) else 2 if len(funcs) <= 5 else 3
        err_clause = ", and an example that shows the exception wherever a function raises" if want_err else ""
        prompt = rng.choice(PROMPTS).format(path=path, n_ex=n_ex, err_clause=err_clause, topic=mod.summary.rstrip(".").lower())
        yield Task(slug=f"{i + 1:02d}-{mod.key}-{len(funcs)}fn", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution, verify=CMD,
                   tags=["doctest", "docstrings", "examples"], notes={"module": mod.key, "functions": [f.name for f in funcs], "min_examples": n_ex, "error_examples": want_err})
