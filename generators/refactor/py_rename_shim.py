"""Rename across a small package with deprecation shims for the old names (python): functions, classes, methods, modules, keyword arguments."""
from __future__ import annotations

import json
import re
from string import Template

from fx import Task, family, merged, run

from . import _kit
from ._kit import prove, py_behaviour
from ._py_rename import SKELETONS

KIND_ORDER = ["function", "class", "method", "module", "param"]


def _sub_all(texts, pattern, repl):
    return {k: re.sub(pattern, repl, v) for k, v in texts.items()}


def _add_import_warnings(text):
    if re.search(r"^import warnings$", text, re.M):
        return text
    first, _, rest = text.partition("\n")
    return first + "\nimport warnings\n" + rest


def solution_files(sk, picks):
    """Apply the renames to the package texts and add the deprecation shims; returns {path: text} for every changed or new file."""
    pkg = sk["pkg"]
    texts = dict(sk["files"])
    renamed_fn = {}
    for kind, sym, new in picks:
        old = sym["old"]
        if kind in ("function", "class", "param"):
            texts = _sub_all(texts, rf"\b{old}\b", new)
            if kind == "function":
                renamed_fn[old] = new
        elif kind == "method":
            texts = _sub_all(texts, rf"(?<=\.){old}\b", new)
            texts = _sub_all(texts, rf"\bdef {old}\b", f"def {new}")
        else:  # module
            texts = _sub_all(texts, rf"\b{old}\b", new)
            texts[f"{pkg}/{new}.py"] = texts.pop(f"{pkg}/{old}.py")
    class_new = {sym["old"]: new for kind, sym, new in picks if kind == "class"}
    for kind, sym, new in picks:
        old, home = sym["old"], sym["home"]
        if kind == "module":
            texts[f"{pkg}/{old}.py"] = (f'"""Deprecated: use {pkg}.{new}."""\nimport warnings\n\nfrom .{new} import *  # noqa: F401,F403\n\n'
                                        f'warnings.warn("{pkg}.{old} is deprecated, use {pkg}.{new}", DeprecationWarning, stacklevel=2)\n')
            continue
        text = texts[home]
        if kind == "function":
            text = _add_import_warnings(text).rstrip("\n") + (
                f'\n\n\ndef {old}(*args, **kwargs):\n    """Deprecated alias of {new}."""\n'
                f'    warnings.warn("{old} is deprecated, use {new}", DeprecationWarning, stacklevel=2)\n    return {new}(*args, **kwargs)\n')
        elif kind == "class":
            text = _add_import_warnings(text).rstrip("\n") + (
                f'\n\n\ndef __getattr__(name):\n    """Deprecated alias {old} of {new} (PEP 562), so that isinstance checks keep working."""\n    if name == "{old}":\n'
                f'        warnings.warn("{old} is deprecated, use {new}", DeprecationWarning, stacklevel=2)\n        return {new}\n'
                f'    raise AttributeError("module %r has no attribute %r" % (__name__, name))\n')
        elif kind == "method":
            cls = class_new.get(sym["cls"], sym["cls"])
            text = _add_import_warnings(text)
            marker = f"    def {new}(self"
            alias = (f'    def {old}(self, *args, **kwargs):\n        """Deprecated alias of {new}()."""\n'
                     f'        warnings.warn("{cls}.{old} is deprecated, use {new}", DeprecationWarning, stacklevel=2)\n        return self.{new}(*args, **kwargs)\n\n')
            assert marker in text, (marker, home)
            text = text.replace(marker, alias + marker, 1)
        else:  # param
            fn = renamed_fn.get(sym["fn"], sym["fn"])
            m = re.search(rf'def {fn}\(([^)]*)\):\n(    """[^\n]*"""\n)', text)
            assert m, (fn, home)
            prelude = (f'    if "{old}" in legacy:\n        warnings.warn("{old} is deprecated, use {new}", DeprecationWarning, stacklevel=2)\n'
                       f'        {new} = legacy.pop("{old}")\n    if legacy:\n        raise TypeError("unexpected keyword arguments: " + ", ".join(sorted(legacy)))\n')
            text = text[:m.start()] + f"def {fn}({m.group(1)}, **legacy):\n" + m.group(2) + prelude + text[m.end():]
            text = _add_import_warnings(text)
        texts[home] = text
    return {k: v for k, v in texts.items() if sk["files"].get(k) != v}


def new_harness(sk, picks):
    h = sk["harness"]
    for kind, sym, new in picks:
        old = sym["old"]
        if kind == "method":
            h = re.sub(rf"(?<=\.){old}\b", new, h)
        else:
            h = re.sub(rf"\b{old}\b", new, h)
    return h


def probes(picks):
    return {sym["old"]: sym["probe"] for kind, sym, new in picks}


STRUCT = '''import ast
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = ${pkg}
RENAMES = json.loads(${renames})
PROBES = json.loads(${probes})
NEW_SCRIPT = json.loads(${new_script})


def package_files():
    out = []
    for dp, dns, fns in os.walk(os.path.join(ROOT, PKG)):
        dns[:] = [d for d in dns if d != "__pycache__"]
        for fn in sorted(fns):
            if fn.endswith(".py"):
                out.append(os.path.join(dp, fn))
    return out


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def run_py(code, *flags):
    return subprocess.run([sys.executable, *flags, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)


def defining_nodes(tree, old):
    """Nodes that define the old name (a def, class or assignment): a shim may mention the name inside them."""
    found = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == old:
            found.append(n)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if (isinstance(t, ast.Name) and t.id == old) or (isinstance(t, ast.Attribute) and t.attr == old):
                    found.append(n)
    return found


def imports_module(node, old):
    if isinstance(node, ast.Import):
        return any(a.name == PKG + "." + old or a.name.startswith(PKG + "." + old + ".") for a in node.names)
    if isinstance(node, ast.ImportFrom):
        if node.module == PKG + "." + old or (node.level and node.module == old):
            return True
        if node.module in (PKG, None):
            return any(a.name == old for a in node.names)
    return False


class RenameTests(unittest.TestCase):
    def test_new_names_exist(self):
        trees = [ast.parse(read(p)) for p in package_files()]
        for r in RENAMES:
            kind, new = r["kind"], r["new"]
            if kind == "module":
                self.assertTrue(os.path.exists(os.path.join(ROOT, PKG, new + ".py")), "missing module %s/%s.py" % (PKG, new))
            elif kind == "param":
                ok = any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in (r["fn"], r["fn_new"]) and
                         new in [a.arg for a in n.args.args + n.args.kwonlyargs] for t in trees for n in ast.walk(t))
                self.assertTrue(ok, "no function has the parameter %s" % new)
            else:
                want = ast.ClassDef if kind == "class" else (ast.FunctionDef, ast.AsyncFunctionDef)
                self.assertTrue(any(isinstance(n, want) and n.name == new for t in trees for n in ast.walk(t)), "%s %s is not defined" % (kind, new))

    def test_package_no_longer_uses_the_old_names(self):
        problems = []
        for path in package_files():
            tree = ast.parse(read(path))
            for r in RENAMES:
                old, kind = r["old"], r["kind"]
                if kind == "module":
                    if rel(path) == PKG + "/" + old + ".py":
                        continue
                    for n in ast.walk(tree):
                        if imports_module(n, old):
                            problems.append("%s:%d still imports the module %s" % (rel(path), n.lineno, old))
                    continue
                allowed = set()
                if rel(path) == r["home"]:
                    for d in defining_nodes(tree, old):
                        allowed.update(id(x) for x in ast.walk(d))
                for n in ast.walk(tree):
                    if id(n) in allowed:
                        continue
                    if kind in ("function", "class"):
                        hit = ((isinstance(n, ast.Name) and n.id == old) or (isinstance(n, ast.Attribute) and n.attr == old) or
                               (isinstance(n, ast.alias) and n.name == old))
                    elif kind == "method":
                        hit = (isinstance(n, ast.Attribute) and n.attr == old) or (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == old)
                    else:
                        hit = (isinstance(n, ast.keyword) and n.arg == old) or (isinstance(n, ast.arg) and n.arg == old)
                    if hit:
                        problems.append("%s:%d still uses the old name %s" % (rel(path), getattr(n, "lineno", 0), old))
        self.assertFalse(problems, "\\n".join(problems[:12]))

    def test_old_names_still_work_and_warn(self):
        for old, probe in PROBES.items():
            code = ("import warnings\\nwith warnings.catch_warnings(record=True) as caught:\\n    warnings.simplefilter('always')\\n" +
                    "\\n".join("    " + ln for ln in probe.splitlines()) +
                    "\\nprint('DEPRECATIONS', sum(1 for w in caught if issubclass(w.category, DeprecationWarning)))\\n")
            res = run_py(code)
            self.assertEqual(res.returncode, 0, "the old name %s no longer works:\\n%s" % (old, res.stderr[-800:]))
            count = int(res.stdout.split("DEPRECATIONS")[1].split()[0])
            self.assertGreaterEqual(count, 1, "using the old name %s must emit a DeprecationWarning" % old)

    def test_new_names_do_not_warn(self):
        res = run_py(NEW_SCRIPT, "-W", "error::DeprecationWarning")
        self.assertEqual(res.returncode, 0, "the new API warns or fails:\\n%s" % res.stderr[-1200:])


if __name__ == "__main__":
    unittest.main()
'''

PROMPTS = [
    "We are aligning the vocabulary of `{pkg}` with the new service: {renames}. Rename them everywhere inside the package. Code outside the package (and the visible tests in "
    "`tests/test_basic.py`, which you must not edit) still uses the old names, so every old name has to keep working, exactly as before, and emit a `DeprecationWarning` when it is "
    "used. Nothing inside `{pkg}` may use an old name any more, and using the new names must not warn. Behaviour stays the same.",
    "rename job in `{pkg}`: {renames}. Update all the callers in the package, and leave a deprecated alias for each old name (it must warn with `DeprecationWarning` when used and "
    "otherwise behave as before, `isinstance` checks included) because other teams still import the old ones. The visible tests exercise the old API and must keep passing; the new "
    "names must not trigger warnings.",
    "Please do these renames in `{pkg}`: {renames}. We cannot change external callers this quarter, so each old name stays available as a shim that raises a `DeprecationWarning` "
    "(`warnings.warn(..., DeprecationWarning, stacklevel=2)` is the usual way) and works as it did, while the package itself switches to the new names completely. "
    "Don't edit the tests; same behaviour everywhere.",
]


def phrase(kind, sym, new, picks, pkg):
    old = sym["old"]
    if kind == "function":
        return f"the function `{old}` becomes `{new}`"
    if kind == "class":
        return f"the class `{old}` becomes `{new}`"
    if kind == "method":
        cls = next((n for k, s, n in picks if k == "class" and s["old"] == sym["cls"]), sym["cls"])
        return f"the method `{cls}.{old}()` becomes `{cls}.{new}()`"
    if kind == "module":
        return f"the module `{pkg}.{old}` becomes `{pkg}.{new}`"
    fn = next((n for k, s, n in picks if k == "function" and s["old"] == sym["fn"]), sym["fn"])
    return f"the keyword argument `{old}` of `{fn}()` becomes `{new}`"


def _ok_case(w):
    return not (isinstance(w, dict) and set(w) == {"raises"})


@family("refactor-py-rename-shim", category="refactor", lang="python", kind="refactor", n=16,
        summary="rename functions, classes, methods, modules and keyword arguments across a package, keeping deprecated aliases that warn")
def gen(rng, n):
    plan = [1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 5, 5, 4, 5, 5, 3]
    rng.shuffle(plan)
    skel = list(SKELETONS)
    seen = set()
    for i in range(n):
        k = plan[i % len(plan)]
        for _ in range(50):
            name = skel[(i + rng.randrange(3)) % 3]
            sk = SKELETONS[name]
            kinds = sorted(rng.sample(KIND_ORDER, k), key=KIND_ORDER.index)
            picks = [(kd, sk["symbols"][kd], rng.choice(sk["symbols"][kd]["news"])) for kd in kinds]
            key = (name, tuple((kd, new) for kd, _, new in picks))
            if key not in seen:
                seen.add(key)
                break
        pkg = sk["pkg"]
        all_text = "\n".join(sk["files"].values()) + sk["harness"]
        for kd, sym, new in picks:
            assert not re.search(rf"\b{new}\b", all_text), (name, new)
        files = dict(sk["files"])
        cases = sk["cases"](rng, 30)
        old_h = sk["harness"]
        new_h = new_harness(sk, picks)
        golden = _kit.py_golden(files, old_h, cases)
        shown = [(c, w) for c, w in zip(cases, golden) if _ok_case(w)][:3]
        vis = ["import json", "import unittest", "", old_h.rstrip("\n"), "", "", "def norm(x):", "    return json.loads(json.dumps(x))", "", "", "class BasicTests(unittest.TestCase):"]
        for t, (c, w) in enumerate(shown):
            vis += [f"    def test_example_{t + 1}(self):", f"        case = json.loads({json.dumps(json.dumps(c))})",
                    f"        self.assertEqual(norm(run_case(case)), json.loads({json.dumps(json.dumps(w))}))", ""]
        vis += ["", "if __name__ == '__main__':", "    unittest.main()", ""]
        start = {**files, "tests/test_basic.py": "\n".join(vis)}
        sol = solution_files(sk, picks)
        renames = []
        for kd, sym, new in picks:
            fn_new = next((n2 for k2, s2, n2 in picks if k2 == "function" and s2["old"] == sym.get("fn")), sym.get("fn", ""))
            renames.append(dict(kind=kd, old=sym["old"], new=new, home=sym["home"], fn=sym.get("fn", ""), fn_new=fn_new))
        first_ok = next(c for c, w in zip(cases, golden) if _ok_case(w))
        new_script = f"import json\nsys_case = json.loads({json.dumps(json.dumps(first_ok))})\n" + new_h + "\nrun_case(sys_case)\n"
        struct = Template(STRUCT).substitute(pkg=json.dumps(pkg), renames=json.dumps(json.dumps(renames)), probes=json.dumps(json.dumps(probes(picks))),
                                             new_script=json.dumps(json.dumps(new_script)))
        hidden = {
            "tests/test_more_new_names.py": py_behaviour(files, old_h, cases, "new names", test_harness=new_h),
            "tests/test_more_old_names.py": py_behaviour(files, old_h, cases, "old names"),
            "tests/test_zz_renames.py": struct,
        }
        # the old-API behaviour test must pass on the start; the new-API one cannot (the new names do not exist yet)
        r0 = run(merged(start, {"tests/test_more_old_names.py": hidden["tests/test_more_old_names.py"]}), _kit.PY_BEHAVIOUR_CMD, timeout=120)
        if not r0.ok:
            raise RuntimeError(f"rename-{i}: old-API behaviour fails on the start:\n{r0.out[-1500:]}")
        prove(f"rename-{i}-{name}", start, hidden, sol, _kit.PY_BEHAVIOUR_CMD, _kit.PY_STRUCT_CMD, "python3 -m unittest discover -s tests", behaviour_on_start=False)
        renames_text = "; ".join(phrase(kd, sym, new, picks, pkg) for kd, sym, new in picks)
        d = {1: 2, 2: 3, 3: 4, 4: 5, 5: 5}[k]
        if k == 1 and picks[0][0] != "function":
            d = 3
        if k == 2 and {"module", "param"} & set(kinds):
            d = 4
        prompt = rng.choice(PROMPTS).format(pkg=pkg, renames=renames_text)
        yield Task(slug=f"{i + 1:02d}-{name}-{'-'.join(kinds)}", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=sol,
                   verify="python3 -m unittest discover -s tests -v", tags=["rename", "deprecation", "compatibility-shim"],
                   notes={"skeleton": name, "renames": [(kd, sym["old"], new) for kd, sym, new in picks]})
