"""Google-style docstrings (python): Args/Returns/Raises sections that must agree with what the code actually does (derived from the AST)."""
from __future__ import annotations

import json

from fx import Task, dd, family

from . import _pymods as P
from ._docscheck import TEXT as DOCSCHECK
from ._kit import prove_docs

CMD = "python3 -m unittest discover -s tests -v"

STYLE = dd('''
    # Docstring conventions

    Public functions (names without a leading underscore) follow the Google style:

    ```
    One-line summary ending with a period.

    Args:
        name: what it means (a type in parentheses after the name is fine)
        other (int): what it means

    Returns:
        what comes back

    Raises:
        ValueError: when it happens
    ```

    * The summary is a single line.
    * `Args:` lists **every** parameter, by its name, once (and nothing that is not a parameter). Functions without
      parameters have no `Args:` section.
    * `Returns:` is present exactly when the function returns a value.
    * `Raises:` is present exactly when the function itself raises an exception (a `raise` statement in its body) and
      lists exactly those exception classes. Exceptions that only propagate from helpers are not listed.
    * Every entry has a description of at least two words.
    * Every module has a module docstring.
''')


_NS = {}
_NS["__file__"] = "/x/tests/docscheck.py"
exec(DOCSCHECK, _NS)


def own_raises(f):
    import ast
    return {k: v for k, v in f.raises.items() if k in _NS["explicit_raises"](ast.parse(f.src).body[0])}


def doc_for(f):
    lines = [f.summary, ""]
    if f.args:
        lines.append("Args:")
        lines += [f"    {n}: {d}" for n, d in f.args.items()]
        lines.append("")
    if f.returns:
        lines += ["Returns:", f"    {f.returns[0].upper() + f.returns[1:]}", ""]
    raises = own_raises(f)
    if raises:
        lines.append("Raises:")
        lines += [f"    {n}: {d[0].upper() + d[1:]}" for n, d in raises.items()]
        lines.append("")
    return "\n".join(lines).rstrip("\n")


def stale_doc(f, rng):
    """A docstring that was right once: summary plus an Args section for an old signature and no Raises."""
    lines = [f.summary.rstrip(".") + "", ""]
    names = list(f.args)
    if names:
        lines += ["Args:", f"    {names[0]}: the {names[0]}"]
        lines += [f"    old_{names[0]}: not used any more"]
        lines.append("")
    return "\n".join(lines).rstrip("\n")


PROMPTS = [
    "The public functions in `{path}` have {state}. `DOCSTYLE.md` describes the house style (Google style docstrings: `Args`, `Returns`, `Raises`). Bring every public function and the module "
    "up to that standard. The sections must match what the code really does: every parameter documented, `Returns` only when something is returned, `Raises` listing exactly the exceptions "
    "the function raises itself. Only docstrings may change.",
    "docs lint is failing for `{path}`: {state}. Fix the docstrings so they satisfy `DOCSTYLE.md` (all params in Args, Returns iff it returns a value, Raises = the explicit raises). Don't touch the code.",
    "Please document `{path}` properly. Right now {state}. Follow `DOCSTYLE.md`; our checker derives the expected Args / Returns / Raises from the code, so they have to be accurate. "
    "No behaviour changes: docstrings only.",
]
STATES = {
    "none": "no docstrings at all",
    "stale": "docstrings that were written for an older signature (parameters that no longer exist, no mention of the exceptions or the return value)",
    "partial": "docstrings only on some of them",
}


def style_test(path, original):
    """Text of the hidden docstring-style test for one module."""
    return dd(f'''
        import ast
        import unittest

        import docscheck as D

        PATH = {json.dumps(path)}
        ORIGINAL = {json.dumps(original)}


        class DocstringTests(unittest.TestCase):
            def setUp(self):
                self.tree = D.parse(PATH)

            def test_code_is_unchanged(self):
                now = {{n.name: D.stripped_dump(n) for n in self.tree.body if isinstance(n, ast.FunctionDef)}}
                self.assertEqual(now, ORIGINAL, "only docstrings may change")

            def test_module_docstring(self):
                self.assertTrue((ast.get_docstring(self.tree) or "").strip(), "the module needs a docstring")

            def test_every_public_function_matches_the_style(self):
                problems = []
                for fn in D.public_functions(self.tree):
                    doc = ast.get_docstring(fn)
                    if not doc:
                        problems.append("%s: no docstring" % fn.name)
                        continue
                    info = D.sections(doc)
                    parsed = info["parsed"]
                    if not info["summary"].endswith("."):
                        problems.append("%s: the summary line should end with a period" % fn.name)
                    want_args = set(D.params(fn))
                    got_args = set(parsed.get("Args", {{}}))
                    if want_args != got_args:
                        problems.append("%s: Args documents %s but the parameters are %s" % (fn.name, sorted(got_args), sorted(want_args)))
                    for name, text in parsed.get("Args", {{}}).items():
                        if D.words(text) < 2:
                            problems.append("%s: the description of %s is too short" % (fn.name, name))
                    if D.returns_value(fn) != ("Returns" in parsed):
                        problems.append("%s: Returns must be present exactly when the function returns a value" % fn.name)
                    elif "Returns" in parsed and D.words(parsed["Returns"]) < 2:
                        problems.append("%s: the Returns description is too short" % fn.name)
                    want_raises = D.explicit_raises(fn)
                    got_raises = set(parsed.get("Raises", {{}}))
                    if want_raises != got_raises:
                        problems.append("%s: Raises lists %s but the function raises %s" % (fn.name, sorted(got_raises), sorted(want_raises)))
                    for name, text in parsed.get("Raises", {{}}).items():
                        if D.words(text) < 2:
                            problems.append("%s: the description of %s is too short" % (fn.name, name))
                self.assertFalse(problems, "\\n".join(problems))
''')


@family("docs-py-docstrings", category="docs", lang="python", kind="feature", n=8,
        summary="write or repair Google-style docstrings so Args/Returns/Raises match the code (checked via AST); behaviour must stay unchanged")
def gen(rng, n):
    mods = list(P.MODULES) * 3
    rng.shuffle(mods)
    variants = ["none", "stale", "partial", "none", "stale", "partial", "stale", "none", "partial", "stale"]
    for i in range(n):
        mod = mods[i]
        variant = variants[i % len(variants)]
        funcs = P.pick(mod, rng, rng.choice([4, 5, 6, 7]))
        if variant == "none":
            start_docs = {}
        elif variant == "stale":
            start_docs = {f.name: stale_doc(f, rng) for f in funcs}
        else:
            start_docs = {f.name: doc_for(f) for f in funcs if rng.random() < 0.5}
            if len(start_docs) == len(funcs):
                start_docs.pop(funcs[0].name)
        start_src = P.source(mod, funcs, start_docs)
        sol_src = P.source(mod, funcs, {f.name: doc_for(f) for f in funcs}).replace(f'"""{mod.summary}"""', f'"""{mod.summary}"""', 1)
        path = f"{mod.pkg}/{mod.mod}.py"
        ns = {}
        exec(P.source(mod, funcs), ns)
        vis = [f"import unittest\n\nfrom {mod.pkg}.{mod.mod} import *\n\n\nclass BehaviourTests(unittest.TestCase):\n"]
        for f in funcs[:3]:
            ex = f.examples[0]
            vis.append(f"    def test_{f.name}(self):\n        self.assertEqual({ex}, {eval(ex, dict(ns))!r})\n")
        vis.append("\nif __name__ == '__main__':\n    unittest.main()\n")
        start = {path: start_src, f"{mod.pkg}/__init__.py": "", "DOCSTYLE.md": STYLE, "tests/test_behaviour.py": "".join(vis)}
        import ast
        tree = ast.parse(P.source(mod, funcs))
        original = {n.name: ast.dump(n) for n in tree.body if isinstance(n, ast.FunctionDef)}
        test = style_test(path, original)
        hidden = {"tests/docscheck.py": DOCSCHECK, "tests/test_docs_style.py": test}
        solution = {path: sol_src}
        prove_docs(f"{mod.key}-{variant}", start, hidden, solution, CMD, "python3 -m unittest discover -s tests -p 'test_beh*.py'")
        d = 2 if (variant == "none" and len(funcs) <= 5) else 3 if variant != "stale" or len(funcs) <= 5 else 4
        prompt = rng.choice(PROMPTS).format(path=path, state=STATES[variant])
        yield Task(slug=f"{i + 1:02d}-{mod.key}-{variant}", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution, verify=CMD,
                   tags=["docstrings", "google-style", "ast-check"], notes={"module": mod.key, "variant": variant, "functions": [f.name for f in funcs]})
