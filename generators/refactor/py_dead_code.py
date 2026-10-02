"""Remove dead code from a package (python): unused functions, chains of dead helpers, imports, constants, flags, leftovers, shadowed definitions.

The package also contains things that look unused but are live (decorator registries, name-based dispatch, package exports, helpers that only the
tests call), so deleting by grep alone breaks behaviour.
"""
from __future__ import annotations

import json
from string import Template

from fx import Task, family

from . import _kit
from ._kit import prove, py_behaviour
from ._py_dead import SKELETONS


def apply_edits(files, items, chosen):
    out = dict(files)
    for key in chosen:
        for edit in items[key]["edits"]:
            if edit[0] == "replace":
                _, path, old, new = edit
                assert out[path].count(old) == 1, (key, path, old)
                out[path] = out[path].replace(old, new)
            else:
                _, path, text = edit
                out[path] = out[path].rstrip("\n") + "\n" + text
    return out


STRUCT = '''import ast
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = ${pkg}
CHECKS = json.loads(${checks})


def package_files():
    out = []
    for dp, dns, fns in os.walk(os.path.join(ROOT, PKG)):
        dns[:] = [d for d in dns if d != "__pycache__"]
        for fn in sorted(fns):
            if fn.endswith(".py"):
                out.append(os.path.relpath(os.path.join(dp, fn), ROOT).replace(os.sep, "/"))
    return out


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def trees():
    return {rel: ast.parse(read(rel)) for rel in package_files()}


def blocks(tree):
    for n in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            seq = getattr(n, field, None)
            if isinstance(seq, list) and seq and isinstance(seq[0], ast.stmt):
                yield n, seq


class DeadCodeTests(unittest.TestCase):
    def test_dead_functions_and_classes_are_gone(self):
        defined = {}
        for rel, tree in trees().items():
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    defined.setdefault(n.name, []).append(rel)
        left = [(name, defined[name]) for name in CHECKS["names"] if name in defined]
        self.assertFalse(left, "dead definitions are still there: %s" % left)

    def test_dead_constants_are_gone(self):
        left = []
        for rel, tree in trees().items():
            for n in tree.body:
                targets = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, ast.AnnAssign) else []
                for t in targets:
                    if isinstance(t, ast.Name) and t.id in CHECKS["consts"]:
                        left.append((t.id, rel))
        self.assertFalse(left, "unused constants (and the branches they guard) are still there: %s" % left)

    def test_unused_imports_are_gone(self):
        left = []
        for rel, name in CHECKS["imports"]:
            if not os.path.exists(os.path.join(ROOT, rel)):
                continue
            for n in ast.walk(ast.parse(read(rel))):
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    for a in n.names:
                        if (a.asname or a.name).split(".")[0] == name:
                            left.append((rel, name))
        self.assertFalse(left, "imports that nothing uses are still there: %s" % left)

    def test_commented_out_code_is_gone(self):
        left = [(rel, m) for rel, m in CHECKS["markers"] if os.path.exists(os.path.join(ROOT, rel)) and m in read(rel)]
        self.assertFalse(left, "commented-out code is still there: %s" % left)

    def test_shadowed_definitions_are_gone(self):
        for rel, name in CHECKS["dups"]:
            count = sum(1 for n in ast.parse(read(rel)).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
            self.assertEqual(count, 1, "%s defines %s %d times: the first definition is dead (it is overwritten)" % (rel, name, count))

    def test_no_statements_after_return(self):
        if "unreachable" not in CHECKS["generic"]:
            return
        problems = []
        for rel, tree in trees().items():
            for node, seq in blocks(tree):
                for i, stmt in enumerate(seq[:-1]):
                    if isinstance(stmt, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
                        problems.append("%s:%d" % (rel, seq[i + 1].lineno))
        self.assertFalse(problems, "unreachable statements at %s" % problems)

    def test_no_constant_false_branches(self):
        if "if_false" not in CHECKS["generic"]:
            return
        problems = []
        for rel, tree in trees().items():
            for n in ast.walk(tree):
                if isinstance(n, (ast.If, ast.While)) and isinstance(n.test, ast.Constant) and not n.test.value:
                    problems.append("%s:%d" % (rel, n.lineno))
        self.assertFalse(problems, "branches that can never run at %s" % problems)


if __name__ == "__main__":
    unittest.main()
'''

PROMPTS = [
    "`{pkg}` ({topic}) has been maintained by many hands and is full of dead code: things nothing uses any more, leftovers and abandoned experiments. I count about {k} separate spots "
    "to remove (unused functions or classes, helpers only the dead code calls, unused imports and constants, flags that are never switched on, statements that can never run, "
    "commented-out code, a function defined twice). Remove all of it. Be careful: this package also uses registries, name-based lookups and package exports, so 'nothing "
    "mentions it' is not always the same as 'dead', and the tests (visible and hidden) run the real behaviour. Everything that is alive must keep working exactly as before.",
    "dead code cleanup in `{pkg}` (about {k} items): unused definitions, imports and constants, branches that can never execute, commented-out code, shadowed duplicates. "
    "Delete them. Watch out for things that are reached indirectly (decorator registration, `getattr` dispatch, `__all__` exports, functions the tests call). Behaviour must not change.",
    "Time to prune `{pkg}`. Dead code has piled up over the years; I found {k} separate spots by eye and there may be helpers that are only used by other dead code. "
    "Remove whatever is really dead, keep whatever is reachable (including through registries and dynamic lookups), and keep the test suite green.",
]


def score_to_d(score, k):
    if score <= 3:
        return 1
    if score <= 7:
        return 2
    if score <= 11:
        return 3
    if score <= 17:
        return 4
    return 5


@family("refactor-py-dead-code", category="refactor", lang="python", kind="refactor", n=16,
        summary="remove planted dead code (unused defs, dead chains, imports, constants, flags, unreachable code, comments, shadowed defs) while keeping registry/dynamic/export-reached code")
def gen(rng, n):
    names = list(SKELETONS)
    plan = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 11, 6, 10, 9, 11, 10]
    rng.shuffle(plan)
    seen = set()
    for i in range(n):
        k = plan[i % len(plan)]
        for _ in range(50):
            name = names[(i + rng.randrange(3)) % 3]
            sk = SKELETONS[name]
            chosen = sorted(rng.sample(list(sk["items"]), min(k, len(sk["items"]))))
            if (name, tuple(chosen)) not in seen:
                seen.add((name, tuple(chosen)))
                break
        items = sk["items"]
        pkg = sk["pkg"]
        base = dict(sk["files"])
        dirty = apply_edits(base, items, chosen)
        cases = sk["cases"](rng, 30)
        want_base = _kit.py_golden(base, sk["harness"], cases)
        want_dirty = _kit.py_golden(dirty, sk["harness"], cases)
        if want_base != want_dirty:
            raise RuntimeError(f"dead-{i}: planting dead code changed the behaviour ({name}, {chosen})")
        shown = [(c, w) for c, w in zip(cases, want_dirty) if not (isinstance(w, dict) and set(w) == {"raises"})][:3]
        vis = ["import json", "import unittest", "", sk["harness"].rstrip("\n"), "", "", "def norm(x):", "    return json.loads(json.dumps(x))", "", "", "class BasicTests(unittest.TestCase):"]
        for t, (c, w) in enumerate(shown):
            vis += [f"    def test_example_{t + 1}(self):", f"        case = json.loads({json.dumps(json.dumps(c))})",
                    f"        self.assertEqual(norm(run_case(case)), json.loads({json.dumps(json.dumps(w))}))", ""]
        vis += ["", "if __name__ == '__main__':", "    unittest.main()", ""]
        start = {**dirty, "tests/test_basic.py": "\n".join(vis)}
        checks = dict(names=[], consts=[], imports=[], markers=[], dups=[], generic=[])
        for key in chosen:
            for field, vals in items[key]["check"].items():
                checks[field].extend(vals)
        struct = Template(STRUCT).substitute(pkg=json.dumps(pkg), checks=json.dumps(json.dumps(checks)))
        hidden = {"tests/test_more_behaviour.py": py_behaviour(base, sk["harness"], cases, "recorded"), "tests/test_zz_dead_code.py": struct}
        solution = {p: base[p] for p in dirty if dirty[p] != base[p]}
        prove(f"dead-{i}-{name}", start, hidden, solution, _kit.PY_BEHAVIOUR_CMD, _kit.PY_STRUCT_CMD, "python3 -m unittest discover -s tests")
        score = sum(items[key]["w"] for key in chosen)
        d = score_to_d(score, k)
        prompt = rng.choice(PROMPTS).format(pkg=pkg, topic=sk["topic"], k=len(chosen))
        yield Task(slug=f"{i + 1:02d}-{name}-{len(chosen)}items", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution,
                   verify="python3 -m unittest discover -s tests -v", tags=["dead-code", "cleanup", "static-analysis"],
                   notes={"skeleton": name, "items": chosen, "score": score})
