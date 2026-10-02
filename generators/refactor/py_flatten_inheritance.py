"""Replace a deep class hierarchy with composition (python): same public classes and behaviour, no inheritance between the package's classes."""
from __future__ import annotations

import json
from string import Template

from fx import Task, family

from . import _kit
from ._kit import prove, py_behaviour
from ._py_hier import HIERARCHIES

STRUCT = '''import ast
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = ${pkg}
CLASSES = json.loads(${classes})


def package_trees():
    out = {}
    for dp, dns, fns in os.walk(os.path.join(ROOT, PKG)):
        dns[:] = [d for d in dns if d != "__pycache__"]
        for fn in sorted(fns):
            if fn.endswith(".py"):
                path = os.path.join(dp, fn)
                with open(path, encoding="utf-8") as f:
                    out[os.path.relpath(path, ROOT).replace(os.sep, "/")] = ast.parse(f.read())
    return out


def base_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return base_name(node.value)
    return ""


class CompositionTests(unittest.TestCase):
    def test_no_class_inherits_from_a_class_of_the_package(self):
        trees = package_trees()
        defined = {n.name for t in trees.values() for n in ast.walk(t) if isinstance(n, ast.ClassDef)}
        problems = []
        for rel, tree in trees.items():
            for n in ast.walk(tree):
                if isinstance(n, ast.ClassDef):
                    for b in n.bases:
                        if base_name(b) in defined:
                            problems.append("%s: class %s extends %s" % (rel, n.name, base_name(b)))
        self.assertFalse(problems, "inheritance is still there:\\n  " + "\\n  ".join(problems))

    def test_no_super_calls(self):
        problems = []
        for rel, tree in package_trees().items():
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "super":
                    problems.append("%s:%d" % (rel, n.lineno))
        self.assertFalse(problems, "super() is still used at %s" % problems)

    def test_the_public_classes_remain(self):
        defined = {n.name for t in package_trees().values() for n in ast.walk(t) if isinstance(n, ast.ClassDef)}
        missing = [c for c in CLASSES if c not in defined]
        self.assertFalse(missing, "classes disappeared: %s" % missing)


if __name__ == "__main__":
    unittest.main()
'''

PROMPTS = [
    "`{path}` has a {depth}-level class hierarchy ({chain}): every class extends the previous one, overrides or extends its methods, calls `super()` and relies on virtual dispatch. "
    "It is hard to follow and impossible to test in isolation. Restructure it with composition instead of inheritance: no class in the package may inherit from another class of "
    "the package (mixins included) and there must be no `super()` calls. Class names, constructor signatures, public methods and the attributes {attrs} must keep working exactly "
    "as they do today, including exceptions; `isinstance` relationships between these classes do not have to survive.",
    "Replace inheritance with composition in `{path}` ({chain}). Same classes, same constructors, same public methods and attributes ({attrs}), same results and exceptions, "
    "but none of the package's classes may extend another one and `super()` goes away.",
    "I want to get rid of the inheritance chain {chain} in `{path}`. Build the behaviour from small collaborating objects (or plain functions) instead. The public classes must remain "
    "with the same constructors, methods and data attributes ({attrs}), producing exactly the same results. The check is simple: no package class subclasses another package class, "
    "and `super()` disappears; behaviour is compared with recordings of the current code.",
]


def _texts(h, kinds, variant):
    start_parts, sol_parts = [], []
    for kind in kinds:
        st = h["start"][kind]
        if isinstance(st, tuple):
            start_text, sol_text = st
        else:
            start_text, sol_text = st, h["sol"][kind]
        start_parts.append(start_text)
        sol_parts.append(sol_text)
    head = f'"""{h["doc"]}"""\n\n\n'
    start = head + "\n\n".join(start_parts)
    sol = head + h["head_sol"] + "\n\n".join(sol_parts)
    return Template(start).substitute(variant), Template(sol).substitute(variant)


def _harness(h, kinds, variant):
    text = h["harness"]
    if len(kinds) == 3:
        text = "\n".join(ln for ln in text.splitlines() if "$C3(" not in ln).replace(", $C3", "") + "\n"
    return Template(text).substitute(variant)


@family("refactor-py-flatten-inheritance", category="refactor", lang="python", kind="refactor", n=12,
        summary="replace a 3-4 level class hierarchy (template methods, virtual dispatch, super calls) with composition, keeping the public classes and recorded behaviour")
def gen(rng, n):
    plan = [("channels", 3), ("channels", 4), ("plans", 3), ("plans", 4), ("stores", 3), ("stores", 4), ("stores", 4), ("channels", 4), ("plans", 4), ("stores", 3), ("stores", 4), ("channels", 4)]
    rng.shuffle(plan)
    used = set()
    for i in range(n):
        hname, depth = plan[i % len(plan)]
        h = HIERARCHIES[hname]
        for _ in range(20):
            vi = rng.randrange(len(h["variants"]))
            if (hname, depth, vi) not in used:
                used.add((hname, depth, vi))
                break
        variant = h["variants"][vi]
        kinds = h["kinds"][:depth]
        pkg = variant["PKG"]
        path = f"{pkg}/core.py"
        start_src, sol_src = _texts(h, kinds, variant)
        files = {path: start_src, f"{pkg}/__init__.py": ""}
        harness = _harness(h, kinds, variant)
        cases = h["cases"](rng, 40, kinds)
        golden = _kit.py_golden(files, harness, cases)
        vis_idx = [j for j, w in enumerate(golden) if not (isinstance(w, dict) and set(w) == {"raises"})][:3]
        vis = ["import json", "import unittest", "", harness.rstrip("\n"), "", "", "def norm(x):", "    return json.loads(json.dumps(x))", "", "", "class BasicTests(unittest.TestCase):"]
        for t, j in enumerate(vis_idx):
            vis += [f"    def test_example_{t + 1}(self):", f"        case = json.loads({json.dumps(json.dumps(cases[j]))})",
                    f"        self.assertEqual(norm(run_case(case)), json.loads({json.dumps(json.dumps(golden[j]))}))", ""]
        vis += ["", "if __name__ == '__main__':", "    unittest.main()", ""]
        start = {**files, "tests/test_basic.py": "\n".join(vis)}
        classes = [variant[f"C{k}"] for k in range(depth)]
        struct = Template(STRUCT).substitute(pkg=json.dumps(pkg), classes=json.dumps(json.dumps(classes)))
        hidden = {"tests/test_more_behaviour.py": py_behaviour(files, harness, cases, "recorded"), "tests/test_zz_composition.py": struct}
        solution = {path: sol_src}
        prove(f"flatten-{i}-{hname}-{depth}", start, hidden, solution, _kit.PY_BEHAVIOUR_CMD, _kit.PY_STRUCT_CMD, "python3 -m unittest discover -s tests")
        chain = " -> ".join(f"`{c}`" for c in classes)
        prompt = rng.choice(PROMPTS).format(path=path, depth=depth, chain=chain, attrs=h["attrs"])
        yield Task(slug=f"{i + 1:02d}-{hname}-depth{depth}-{variant['C0'].lower()}", prompt=prompt, difficulty=h["d"][depth], start=start, hidden=hidden, solution=solution,
                   verify="python3 -m unittest discover -s tests -v", tags=["inheritance", "composition", "refactor-design"],
                   notes={"hierarchy": hname, "depth": depth, "classes": classes})
