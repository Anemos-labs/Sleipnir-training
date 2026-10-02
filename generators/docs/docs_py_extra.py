"""Two more python docs families: a quick one-or-two-function docstring fix (easy end) and a full overhaul of an undocumented package (hard end)."""
from __future__ import annotations

import ast

from fx import Task, family

from . import _pymods as P
from ._docscheck import TEXT as DOCSCHECK
from ._kit import prove_docs
from .docs_py_docstrings import CMD, STYLE, doc_for, stale_doc, style_test
from .docs_readme_snippets import readme_test


def _visible(mod, funcs, ns):
    vis = [f"import unittest\n\nfrom {mod.pkg}.{mod.mod} import *\n\n\nclass BehaviourTests(unittest.TestCase):\n"]
    for f in funcs[:3]:
        ex = f.examples[0]
        vis.append(f"    def test_{f.name}(self):\n        self.assertEqual({ex}, {eval(ex, dict(ns))!r})\n")
    vis.append("\nif __name__ == '__main__':\n    unittest.main()\n")
    return "".join(vis)


def _original(src):
    return {n.name: ast.dump(n) for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}


QUICK_PROMPTS = [
    "`{path}` has {state} for {what}. `DOCSTYLE.md` describes the house style (Google style: `Args`, `Returns`, `Raises`). Bring {what} up to it; the sections must match what the "
    "code really does. Only docstrings may change.",
    "docs lint fails on {what} in `{path}` ({state}). Fix the docstring following `DOCSTYLE.md`: every parameter in Args, Returns only when a value is returned, Raises = exactly the "
    "exceptions raised in the body. Code stays as it is.",
    "Small one: write the docstring for {what} in `{path}` per `DOCSTYLE.md`. Right now there is {state}. The checker derives the expected sections from the code.",
]


@family("docs-py-docstring-quick", category="docs", lang="python", kind="feature", n=9,
        summary="fix the docstring of one or two public functions to the house style (Args/Returns/Raises derived from the AST); the quick end of the docstring family")
def gen_quick(rng, n):
    mods = list(P.MODULES) * 3
    rng.shuffle(mods)
    seen = set()
    plan = [(1, "none"), (1, "stale"), (1, "none"), (1, "stale"), (2, "none"), (1, "none"), (2, "stale"), (1, "stale"), (2, "none")]
    for i in range(n):
        mod = mods[i]
        k, variant = plan[i % len(plan)]
        pool = [f for f in mod.funcs if not f.needs]
        for _ in range(40):
            chosen = rng.sample(pool, k)
            funcs = [f for f in mod.funcs if f in chosen]
            key = (mod.key, tuple(f.name for f in funcs), variant)
            if key not in seen:
                seen.add(key)
                break
        start_docs = {} if variant == "none" else {f.name: stale_doc(f, rng) for f in funcs}
        start_src = P.source(mod, funcs, start_docs)
        sol_src = P.source(mod, funcs, {f.name: doc_for(f) for f in funcs})
        path = f"{mod.pkg}/{mod.mod}.py"
        ns = {}
        exec(P.source(mod, funcs), ns)
        start = {path: start_src, f"{mod.pkg}/__init__.py": "", "DOCSTYLE.md": STYLE, "tests/test_behaviour.py": _visible(mod, funcs, ns)}
        test = style_test(path, _original(P.source(mod, funcs)))
        hidden = {"tests/docscheck.py": DOCSCHECK, "tests/test_docs_style.py": test}
        solution = {path: sol_src}
        prove_docs(f"quick-{mod.key}-{variant}", start, hidden, solution, CMD, "python3 -m unittest discover -s tests -p 'test_beh*.py'")
        what = f"`{funcs[0].name}`" if k == 1 else " and ".join(f"`{f.name}`" for f in funcs)
        state = "no docstring" if variant == "none" else "a stale docstring (written for an older signature)"
        if k > 1:
            state = state.replace("a stale docstring", "stale docstrings").replace("no docstring", "no docstrings")
        d = 1 if k == 1 else 2
        yield Task(slug=f"{i + 1:02d}-{mod.key}-{'-'.join(f.name for f in funcs)}", prompt=rng.choice(QUICK_PROMPTS).format(path=path, state=state, what=what), difficulty=d,
                   start=start, hidden=hidden, solution=solution, verify=CMD, tags=["docstrings", "google-style", "ast-check"],
                   notes={"module": mod.key, "variant": variant, "functions": [f.name for f in funcs]})


OVERHAUL_PROMPTS = [
    "`{pkg}` has no documentation to speak of: the functions in `{path}` have no docstrings and `README.md` is a stub with nothing in it. Please write it properly. (1) Every public function gets a "
    "docstring in the style described in `DOCSTYLE.md` (the Args, Returns and Raises sections must match what the code really does) and the module keeps its docstring. (2) The README "
    "gets a usage section: ```python blocks that import from `{pkg}.{mod}` and show at least one example for every public function, each annotated with `# => result` (the "
    "annotations are executed and compared with the real results, top to bottom, so write them against the real code). Only docstrings and the README may change.",
    "docs sprint for `{pkg}`: the code in `{path}` is undocumented and the README is a one-line stub. Deliver both halves: docstrings for all public functions following `DOCSTYLE.md` "
    "(accurate Args/Returns/Raises), and a README usage section with runnable ```python snippets, one example per public function, using `# => value` comments that must match what "
    "the code returns. Don't change any code.",
    "Documentation overhaul for `{pkg}`. Right now: no docstrings, README is empty apart from a title. Wanted: Google-style docstrings as per `DOCSTYLE.md` on every public function "
    "(parameters, return value and the exceptions the function raises itself), and a README with a usage chapter where each public function appears in a snippet with its real "
    "result as a `# =>` comment. Both are machine-checked; the code must stay untouched.",
]


def example_readme(mod, funcs, ns):
    lines = [f"# {mod.pkg}", "", mod.summary, "", "## Usage", "", "```python", f"from {mod.pkg}.{mod.mod} import {', '.join(sorted(f.name for f in funcs))}", ""]
    for f in funcs:
        ex = f.examples[0]
        lines.append(f"{ex}  # => {eval(ex, dict(ns))!r}")
    lines += ["```", ""]
    return "\n".join(lines)


@family("docs-py-overhaul", category="docs", lang="python", kind="feature", n=6,
        summary="document an undocumented package end to end: docstrings for every public function (AST-checked) and a README usage section whose executed snippets must be right")
def gen_overhaul(rng, n):
    mods = list(P.MODULES) * 2
    rng.shuffle(mods)
    plan = [5, 5, 6, 7, 7, 5]
    for i in range(n):
        mod = mods[i]
        k = min(plan[i % len(plan)], len(mod.funcs))
        funcs = P.pick(mod, rng, k)
        path = f"{mod.pkg}/{mod.mod}.py"
        code = P.source(mod, funcs)
        ns = {}
        exec(code, ns)
        sol_code = P.source(mod, funcs, {f.name: doc_for(f) for f in funcs})
        start = {path: code, f"{mod.pkg}/__init__.py": "", "DOCSTYLE.md": STYLE, "README.md": f"# {mod.pkg}\n\nTODO: usage.\n", "tests/test_behaviour.py": _visible(mod, funcs, ns)}
        original = _original(code)
        required = sorted(f.name for f in funcs)
        hidden = {"tests/docscheck.py": DOCSCHECK, "tests/test_docs_style.py": style_test(path, original),
                  "tests/test_readme_usage.py": readme_test(path, original, required, 1, len(funcs))}
        solution = {path: sol_code, "README.md": example_readme(mod, funcs, ns)}
        prove_docs(f"overhaul-{mod.key}-{len(funcs)}", start, hidden, solution, CMD, "python3 -m unittest discover -s tests -p 'test_beh*.py'")
        d = 4 if len(funcs) <= 5 else 5
        prompt = rng.choice(OVERHAUL_PROMPTS).format(pkg=mod.pkg, path=path, mod=mod.mod)
        yield Task(slug=f"{i + 1:02d}-{mod.key}-{len(funcs)}funcs", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution, verify=CMD,
                   tags=["docstrings", "readme", "executed-snippets", "overhaul"], notes={"module": mod.key, "functions": required})
