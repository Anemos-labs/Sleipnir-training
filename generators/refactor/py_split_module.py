"""Split a god module into cohesive modules while keeping the old import path (python)."""
from __future__ import annotations

import ast
import json
from string import Template

from fx import Task, dd, family

from . import _kit
from ._kit import prove, py_behaviour, py_structlib
from ._py_gods import GODS

structlib = _kit.load_structlib()


def _defined(tree):
    """Public top-level names (functions, classes, constants) of a module tree."""
    out = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            out.append(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out.append(t.id)
    return out


def _all_top(tree):
    return set(_defined(tree))


def _loads(tree):
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def _loc(text):
    return sum(1 for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#"))


PROMPTS = [
    "`{pkg}/util.py` has become the place where everything goes: {topic} code for {areas}. It is {n} lines and every change conflicts with someone else's. "
    "Split it into separate modules inside the `{pkg}` package, one per responsibility, and keep `from {pkg}.util import ...` working for every public name, "
    "because other teams import from there. Each new module should stay under {limit} lines, nothing may be defined twice, and the modules must not import each other in a circle. "
    "`{pkg}/util.py` itself should end up as a thin facade (re-exports only).",
    "Break up `{pkg}/util.py` ({n} lines). It mixes {areas}. I want one module per concern inside `{pkg}/`, with `util.py` left as a compatibility layer that re-exports "
    "the public names so existing imports keep working. No circular imports, no copy-pasted definitions, and keep every module under {limit} lines.",
    "util.py in `{pkg}` is a {n}-line grab bag ({areas}). Refactor: separate modules per area, old `{pkg}.util` imports must still work (re-export), no import cycles, "
    "no name defined in two places, max {limit} lines per module. Behaviour unchanged.",
    "Our {topic} package keeps everything in `{pkg}/util.py`, which is how a typo in the {first} code once broke the {last} code. Please split it by area ({areas}) into "
    "modules of their own under `{pkg}/`. External callers do `from {pkg}.util import something`, so `util` must keep exporting every public name (re-exports are fine, "
    "definitions are not). Keep modules short (under {limit} lines) and avoid circular imports between them.",
]


@family("refactor-py-split-module", category="refactor", lang="python", kind="refactor", n=10,
        summary="split a god module into area modules, keep the old import path as a facade, avoid import cycles")
def gen(rng, n):
    order = list(GODS) * 4
    rng.shuffle(order)
    for i in range(n):
        god = order[i]
        params = god.params(rng)
        opt = [a for a in god.areas if a.optional]
        keep = {a.name for a in opt if rng.random() < 0.6}
        areas = [a for a in god.areas if not a.optional or a.name in keep]
        if len(areas) < 4:
            areas = list(god.areas)
        # keep dependencies consistent: drop deps on dropped areas (cannot happen: optional areas are leaves)
        texts = {a.name: Template(a.code).substitute(params).strip("\n") + "\n" for a in areas}
        pkg = god.package
        god_src = f'"""{god.doc}."""\n\n\n' + "\n\n".join(texts[a.name] for a in areas)
        start_files = {f"{pkg}/__init__.py": "", f"{pkg}/util.py": god_src, f"{pkg}/app.py": god.app}
        # --- reference solution
        tops = {a.name: _all_top(ast.parse(texts[a.name])) for a in areas}
        sol = {}
        public = []
        for a in areas:
            tree = ast.parse(texts[a.name])
            mine = tops[a.name]
            used = _loads(tree)
            imports = []
            for b in areas:
                if b.name == a.name:
                    continue
                need = sorted(x for x in used & tops[b.name] if x not in mine)
                if need:
                    imports.append(f"from .{b.name} import {', '.join(need)}")
            head = f'"""{god.doc}: {a.name}."""\n' + ("\n" + "\n".join(imports) + "\n" if imports else "")
            sol[f"{pkg}/{a.name}.py"] = head + "\n\n" + texts[a.name]
            public += [x for x in _defined(tree) if not x.startswith("_")]
        facade = [f'"""{god.doc}. The code lives in the sibling modules; this module re-exports it."""\n']
        for a in areas:
            names = sorted(x for x in _defined(ast.parse(texts[a.name])) if not x.startswith("_"))
            facade.append(f"from .{a.name} import {', '.join(names)}  # noqa: F401")
        sol[f"{pkg}/util.py"] = "\n".join(facade) + "\n"
        # --- behaviour
        cases = []
        for a in areas:
            if a.cases:
                cases += a.cases(rng, params)
        cases += god.app_cases(rng, params, areas)
        harness = (f"import importlib\n\ndef run_case(case):\n    if case[0] == 'app':\n        app = importlib.import_module('{pkg}.app')\n"
                   f"        return app.{god.app_fn}(*case[1])\n    util = importlib.import_module('{pkg}.util')\n    return getattr(util, case[0])(*case[1])\n")
        want = _kit.py_golden(start_files, harness, cases)
        beh = py_behaviour(start_files, harness, cases, "recorded")
        ok = [j for j, w in enumerate(want) if not (isinstance(w, dict) and "raises" in w)]
        pick = [j for j in ok if cases[j][0] != "app"][:2] + [j for j in ok if cases[j][0] == "app"][:1]
        vis = ["import json", "import unittest", "", harness.rstrip("\n"), "", "def norm(x):", "    return json.loads(json.dumps(x))", "", "",
               "class UtilTests(unittest.TestCase):"]
        for t, j in enumerate(pick):
            vis += [f"    def test_example_{t + 1}(self):", f"        case = json.loads({json.dumps(json.dumps(cases[j]))})",
                    f"        self.assertEqual(norm(run_case(case)), json.loads({json.dumps(json.dumps(want[j]))}))", ""]
        vis += ["", "if __name__ == '__main__':", "    unittest.main()", ""]
        start = {**start_files, "tests/test_util.py": "\n".join(vis)}
        # --- structure
        max_area = max(_loc(sol[f"{pkg}/{a.name}.py"]) for a in areas)
        limit = int(max_area * 1.6) + 5
        god_loc = _loc(god_src)
        if god_loc <= limit + 12:
            raise RuntimeError(f"{god.key}: god module {god_loc} lines, limit {limit}")
        struct = dd(f'''
        import ast
        import importlib
        import unittest

        import structlib as S

        PKG = "{pkg}"
        NAMES = {json.dumps(sorted(set(public)))}
        MIN_MODULES = {max(3, len(areas) - 1)}
        LIMIT = {limit}


        def modules():
            return [r for r in S.py_files(PKG) if not r.endswith("__init__.py")]


        class StructureTests(unittest.TestCase):
            def test_old_import_path_exports_everything(self):
                util = importlib.import_module(PKG + ".util")
                missing = [n for n in NAMES if not hasattr(util, n)]
                self.assertFalse(missing, "util no longer exports: %s" % missing)

            def test_util_is_only_a_facade(self):
                for rel in (PKG + "/util.py", PKG + "/util/__init__.py"):
                    if S.exists(rel):
                        tree = S.parse(rel)
                        defs = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
                        self.assertFalse(defs, "util should only re-export, but it defines %s" % defs)

            def test_split_into_several_modules(self):
                mods = [m for m in modules() if m not in (PKG + "/util.py", PKG + "/app.py") and not m.startswith(PKG + "/util/")]
                self.assertGreaterEqual(len(mods), MIN_MODULES, "found only %s" % mods)

            def test_modules_are_short(self):
                big = []
                for rel in modules():
                    n = sum(1 for ln in S.read(rel).splitlines() if ln.strip() and not ln.strip().startswith("#"))
                    if n > LIMIT:
                        big.append("%s has %d lines (limit %d)" % (rel, n, LIMIT))
                self.assertFalse(big, S.format_problems(big))

            def test_nothing_is_defined_twice(self):
                seen = {{}}
                for rel in modules():
                    for n in S.parse(rel).body:
                        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and not n.name.startswith("_"):
                            seen.setdefault(n.name, []).append(rel)
                dup = {{k: v for k, v in seen.items() if len(v) > 1}}
                self.assertFalse(dup, "defined in several modules: %s" % dup)

            def test_no_import_cycles(self):
                cycles = S.import_cycles(S.py_files("."))
                self.assertFalse(cycles, "import cycles: %s" % cycles)
        ''')
        hidden = {"tests/test_more_behaviour.py": beh, "tests/test_zz_structure.py": struct, **py_structlib()}
        prove(f"{god.key}", start, hidden, sol, _kit.PY_BEHAVIOUR_CMD, _kit.PY_STRUCT_CMD, "python3 -m unittest discover -s tests")
        area_names = [a.name for a in areas]
        prompt = rng.choice(PROMPTS).format(pkg=pkg, topic=god.topic, areas=", ".join(area_names[:-1]) + " and " + area_names[-1], n=god_loc, limit=limit,
                                            first=area_names[0], last=area_names[-1])
        d = 3 if len(areas) <= 4 else 4
        yield Task(slug=f"{i + 1:02d}-{god.key}-{len(areas)}areas", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=sol,
                   verify="python3 -m unittest discover -s tests -v", tags=["split-module", "facade", "import-graph"],
                   notes={"god": god.key, "areas": area_names, "limit": limit})
