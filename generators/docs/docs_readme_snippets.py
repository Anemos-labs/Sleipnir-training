"""Stale README (python): the code was renamed and moved, the README still shows the old API; every fenced python block must run and its `# =>` outputs must hold."""
from __future__ import annotations

import ast
import json

from fx import Task, dd, family

from . import _pymods as P
from ._docscheck import TEXT as DOCSCHECK
from ._kit import prove_docs

CMD = "python3 -m unittest discover -s tests -v"
NEW_MOD = {"seedbank": "stock", "ferry": "timetable", "tidelab": "convert", "duty": "calc"}
INTROS = [
    "{summary} The functions below are the ones you will use most.",
    "{summary} A tour of the main entry points follows; every snippet is meant to be copy-pasteable.",
    "{summary} Install it by copying the `{pkg}` folder next to your script. Quick examples:",
]
HEADINGS = ["Quick start", "More examples", "Edge cases", "Helpers"]


def blocks_text(mod, funcs, names_map, ns, mod_name, per_block):
    """README body: python blocks with examples; names_map renames functions as the README shows them."""
    chunks = []
    n_blocks = 0
    pool = list(funcs)
    while pool:
        group, pool = pool[:per_block], pool[per_block:]
        used = []
        lines = []
        for f in group:
            for ex in f.examples[:2]:
                expr = ex
                shown = expr
                for new, old in names_map.items():
                    shown = shown.replace(f"{new}(", f"{old}(")
                val = repr(eval(ex, dict(ns)))
                lines.append(f"{shown}  # => {val}")
            name = names_map.get(f.name, f.name)
            used.append(name)
        imp = f"from {mod.pkg}.{mod_name} import {', '.join(sorted(set(used)))}"
        heading = HEADINGS[n_blocks % len(HEADINGS)]
        chunks.append(f"## {heading}\n\n```python\n{imp}\n\n" + "\n".join(lines) + "\n```\n")
        n_blocks += 1
    return "\n".join(chunks), n_blocks


PROMPTS = [
    "The README of `{pkg}` is out of date: after the last refactoring some functions were renamed and the module `{pkg}.{old_mod}` became `{pkg}.{new_mod}`, but the usage snippets in "
    "`README.md` still show the old names and import path, so copy-pasting them fails. Fix the README so that every ```python block runs, and the `# =>` comments show what the "
    "expressions really evaluate to. Don't change the code.",
    "Users are complaining that the examples in `README.md` don't work (ImportError / NameError). The code in `{pkg}/{new_mod}.py` is right and stays as it is. Update the documentation: "
    "every snippet must run top to bottom, and each `# =>` annotation must match the actual result.",
    "docs: README snippets are stale (old function names, old module name `{old_mod}`). Make them work against the current code in `{pkg}`. All fenced python blocks get executed in CI "
    "and the `# =>` values are compared with the real results. Keep the README's structure and content, just correct it; the code must not change.",
]


@family("docs-readme-snippets", category="docs", lang="python", kind="feature", n=8,
        summary="repair a README whose python snippets use renamed functions and a moved module; every block is executed and `# =>` results are compared")
def gen(rng, n):
    mods = list(P.MODULES) * 2
    rng.shuffle(mods)
    for i in range(n):
        mod = mods[i]
        renames = P.RENAMES[mod.key]
        funcs = P.pick(mod, rng, rng.choice([4, 5, 6]))
        have = {f.name for f in funcs}
        for old in renames:
            if old not in have:
                funcs.append(next(f for f in mod.funcs if f.name == old))
        funcs = [f for f in mod.funcs if f in funcs or f.name in {x.name for x in funcs}]
        new_mod = NEW_MOD[mod.key]
        code_new = P.source(mod, funcs, None, renames)
        ns_new = {}
        exec(code_new, ns_new)
        # new -> old name used by the stale README
        new_to_old = {new: old for old, new in renames.items() if old in {f.name for f in funcs}}
        per_block = rng.choice([2, 3])
        # build examples against the new code, written with the new names
        funcs_new = []
        for f in funcs:
            nf = type(f)(**{**f.__dict__})
            if f.name in renames:
                nf.name = renames[f.name]
            nf.examples = [e for e in f.examples]
            for old, new in renames.items():
                nf.examples = [e.replace(f"{old}(", f"{new}(") for e in nf.examples]
            funcs_new.append(nf)
        # evaluate examples with the renamed code, but present them with old names in the start README
        def build(readme_names):
            chunks, nb = [], 0
            pool = list(funcs_new)
            while pool:
                group, pool = pool[:per_block], pool[per_block:]
                used, lines = [], []
                for f in group:
                    for ex in f.examples[:2]:
                        val = repr(eval(ex, dict(ns_new)))
                        shown = ex
                        for new, old in readme_names.items():
                            shown = shown.replace(f"{new}(", f"{old}(")
                        lines.append(f"{shown}  # => {val}")
                    used.append(readme_names.get(f.name, f.name))
                mod_name = new_mod if not readme_names else mod.mod
                imp = f"from {mod.pkg}.{mod_name} import {', '.join(sorted(set(used)))}"
                chunks.append(f"## {HEADINGS[nb % len(HEADINGS)]}\n\n```python\n{imp}\n\n" + "\n".join(lines) + "\n```\n")
                nb += 1
            return "\n".join(chunks), nb
        intro = rng.choice(INTROS).format(summary=mod.summary, pkg=mod.pkg)
        stale_body, nb = build(new_to_old)
        good_body, _ = build({})
        stale_readme = f"# {mod.pkg}\n\n{intro}\n\n{stale_body}"
        good_readme = f"# {mod.pkg}\n\n{intro}\n\n{good_body}"
        required = sorted({f.name for f in funcs_new})
        path = f"{mod.pkg}/{new_mod}.py"
        vis = (f"import unittest\n\nfrom {mod.pkg}.{new_mod} import *\n\n\nclass BehaviourTests(unittest.TestCase):\n"
               f"    def test_{funcs_new[0].name}(self):\n        self.assertEqual({funcs_new[0].examples[0]}, {eval(funcs_new[0].examples[0], dict(ns_new))!r})\n\n\nif __name__ == '__main__':\n    unittest.main()\n")
        start = {path: code_new, f"{mod.pkg}/__init__.py": "", "README.md": stale_readme, "tests/test_behaviour.py": vis}
        tree = ast.parse(code_new)
        original = {nd.name: ast.dump(nd) for nd in tree.body if isinstance(nd, ast.FunctionDef)}
        test = dd(f'''
        import ast
        import re
        import unittest

        import docscheck as D

        PATH = {json.dumps(path)}
        ORIGINAL = {json.dumps(original)}
        REQUIRED_NAMES = {json.dumps(required)}
        MIN_BLOCKS = {nb}
        MIN_CHECKS = {sum(min(2, len(f.examples)) for f in funcs_new)}
        BLOCK_RE = re.compile(r"```python\\n(.*?)```", re.S)
        ARROW_RE = re.compile(r"#\\s*=>\\s*(.+)$")


        class ReadmeTests(unittest.TestCase):
            def test_code_is_unchanged(self):
                tree = D.parse(PATH)
                now = {{n.name: D.stripped_dump(n) for n in tree.body if isinstance(n, ast.FunctionDef)}}
                self.assertEqual(now, ORIGINAL, "the code must not change, only the README")

            def test_snippets_run_and_show_the_real_results(self):
                text = D.read("README.md")
                blocks = BLOCK_RE.findall(text)
                self.assertGreaterEqual(len(blocks), MIN_BLOCKS, "the README lost some of its python blocks")
                ns = {{}}
                checked = 0
                for number, block in enumerate(blocks, 1):
                    tree = ast.parse(block)
                    lines = block.split("\\n")
                    for node in tree.body:
                        if isinstance(node, ast.Expr):
                            m = ARROW_RE.search(lines[node.end_lineno - 1])
                            if m:
                                value = eval(compile(ast.Expression(node.value), "<readme>", "eval"), ns)
                                self.assertEqual(repr(value), m.group(1).strip(), "block %d, line %d" % (number, node.lineno))
                                checked += 1
                                continue
                        exec(compile(ast.Module([node], []), "<readme %d>" % number, "exec"), ns)
                self.assertGreaterEqual(checked, MIN_CHECKS, "expected at least %d checked results, found %d" % (MIN_CHECKS, checked))

            def test_all_functions_are_still_documented(self):
                text = D.read("README.md")
                missing = [n for n in REQUIRED_NAMES if n not in text]
                self.assertFalse(missing, "the README no longer mentions: %s" % missing)
        ''')
        hidden = {"tests/docscheck.py": DOCSCHECK, "tests/test_readme_snippets.py": test}
        solution = {"README.md": good_readme}
        prove_docs(f"{mod.key}", start, hidden, solution, CMD, "python3 -m unittest discover -s tests -p 'test_beh*.py'")
        prompt = rng.choice(PROMPTS).format(pkg=mod.pkg, old_mod=mod.mod, new_mod=new_mod)
        d = 1 if nb <= 2 and len(new_to_old) <= 1 else 2 if nb <= 2 else 3
        yield Task(slug=f"{i + 1:02d}-{mod.key}-{nb}blocks", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution, verify=CMD,
                   tags=["readme", "snippets", "stale-docs"], notes={"module": mod.key, "blocks": nb, "renamed": sorted(new_to_old.values())})
