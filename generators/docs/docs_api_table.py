"""API reference table (python): keep docs/API.md in sync with the code, or write the generator that does it (checked with --check against a modified copy)."""
from __future__ import annotations

import ast
import json

from fx import Task, dd, family

from . import _pymods as P
from ._docscheck import TEXT as DOCSCHECK
from ._kit import prove_docs

CMD = "python3 -m unittest discover -s tests -v"

TABLE_LIB = r'''import ast


def table_lines(source):
    """Rows of the API table for the public functions of a module, in definition order."""
    tree = ast.parse(source)
    rows = ["| Function | Signature | Summary |", "|---|---|---|"]
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            sig = "(" + ast.unparse(node.args) + ")"
            doc = (ast.get_docstring(node) or "").strip().split("\n")[0]
            rows.append("| `%s` | `%s` | %s |" % (node.name, sig, doc))
    return rows
'''


def table_for(src):
    ns = {}
    exec(TABLE_LIB, ns)
    return ns["table_lines"](src)


def stale_table(rows, rng):
    head, body = rows[:2], rows[2:]
    body = list(body)
    # drop one or two rows, rewrite a signature and a summary, shuffle two rows
    for _ in range(min(2, max(1, len(body) // 3))):
        body.pop(rng.randrange(len(body)))
    if body:
        k = rng.randrange(len(body))
        cells = body[k].split(" | ")
        cells[1] = "`(" + "old_" + cells[1].strip("`()").split(",")[0].strip() + ")`" if cells[1].strip("`()") else "`(legacy)`"
        body[k] = " | ".join(cells)
        k = rng.randrange(len(body))
        cells = body[k].split(" | ")
        cells[2] = "Does what it says on the tin. |"
        body[k] = " | ".join(cells)
    if len(body) > 2:
        a, b = rng.sample(range(len(body)), 2)
        body[a], body[b] = body[b], body[a]
    return head + body


PROMPTS_UPDATE = [
    "`docs/API.md` is supposed to list every public function of `{path}` with its signature and the first line of its docstring, but it has drifted: functions were added, signatures changed, summaries "
    "reworded. Bring the table up to date. The format is `# API` on the first line, then the table with the header `| Function | Signature | Summary |` and one row per public function in definition order, "
    "e.g. `| `name` | `(a, b=1)` | Summary text. |`: the signature is the parameter list exactly as `ast.unparse` prints it for the function's arguments, the summary is the docstring's first line. "
    "Don't change the code.",
    "Fix the API table in `docs/API.md` for `{path}` (rows: `| `name` | `(params)` | first docstring line |`, one per public function, in the order they are defined; header `| Function | Signature | Summary |`). "
    "It is stale. The code is the source of truth and must stay as is.",
]
PROMPTS_GEN = [
    "Nobody keeps `docs/API.md` up to date by hand, so please automate it. Write `tools/gen_api.py`: running `python3 tools/gen_api.py` regenerates `docs/API.md` from `{path}`, and "
    "`python3 tools/gen_api.py --check` exits 0 when the file is current and 1 (printing what differs) when it is not. Format: `# API` on the first line, then a table with the header "
    "`| Function | Signature | Summary |` and one row per public function in definition order: `| `name` | `(params)` | first docstring line |`, where the signature is the parameter list as `ast.unparse` "
    "prints it for the function's arguments. Run the generator once so the committed `docs/API.md` is correct. Standard library only; the module code stays untouched.",
    "Add a generator for the API reference: `tools/gen_api.py` writes `docs/API.md` (`# API`, then the table `| Function | Signature | Summary |` with one row per public function of `{path}` in definition order: "
    "`| `name` | `(params)` | first docstring line |`, parameters as `ast.unparse` prints `node.args`) and `tools/gen_api.py --check` fails with exit status 1 if the file on disk differs from what would be generated "
    "(0 otherwise). Generate the file once now. CI will modify the module and expect `--check` to notice.",
]


@family("docs-api-table", category="docs", lang="python", kind="feature", n=6,
        summary="update a stale API table from the code, or write the generator with a --check mode (verified against a modified copy of the repo)")
def gen(rng, n):
    mods = list(P.MODULES) * 2
    rng.shuffle(mods)
    for i in range(n):
        mod = mods[i]
        mode = "update" if i % 2 == 0 else "generator"
        funcs = P.pick(mod, rng, rng.choice([4, 5, 6]))
        src = P.source(mod, funcs, {f.name: f.summary for f in funcs})
        path = f"{mod.pkg}/{mod.mod}.py"
        rows = table_for(src)
        good = "# API\n\n" + "\n".join(rows) + "\n"
        stale = "# API\n\n" + "\n".join(stale_table(rows, rng)) + "\n"
        ns = {}
        exec(P.source(mod, funcs), ns)
        vis = (f"import unittest\n\nfrom {mod.pkg}.{mod.mod} import *\n\n\nclass BehaviourTests(unittest.TestCase):\n    def test_{funcs[0].name}(self):\n"
               f"        self.assertEqual({funcs[0].examples[0]}, {eval(funcs[0].examples[0], dict(ns))!r})\n\n\nif __name__ == '__main__':\n    unittest.main()\n")
        start = {path: src, f"{mod.pkg}/__init__.py": "", "docs/API.md": stale, "tests/test_behaviour.py": vis}
        original = {nd.name: ast.dump(nd) for nd in ast.parse(src).body if isinstance(nd, ast.FunctionDef)}
        common = dd(f'''
        import ast
        import os
        import shutil
        import subprocess
        import sys
        import tempfile
        import unittest

        import docscheck as D

        PATH = {json.dumps(path)}
        TABLE_LIB = {TABLE_LIB!r}
        ORIGINAL = {json.dumps(original)}


        def expected(source):
            ns = {{}}
            exec(TABLE_LIB, ns)
            return ns["table_lines"](source)


        def table_in(text):
            return [ln.rstrip() for ln in text.split("\\n") if ln.startswith("|")]


        class ApiTableTests(unittest.TestCase):
            def test_code_is_unchanged(self):
                tree = D.parse(PATH)
                now = {{n.name: ast.dump(n) for n in tree.body if isinstance(n, ast.FunctionDef)}}
                self.assertEqual(now, ORIGINAL, "the module must not change")

            def test_table_matches_the_code(self):
                text = D.read("docs/API.md")
                self.assertEqual(text.split("\\n")[0].strip(), "# API")
                self.assertEqual(table_in(text), expected(D.read(PATH)))
        ''')
        gen_tests = dd('''

            def run(self, cwd, *args):
                return subprocess.run([sys.executable, "tools/gen_api.py", *args], cwd=cwd, capture_output=True, text=True, timeout=60)

            def test_generator_regenerates_and_checks(self):
                tmp = tempfile.mkdtemp()
                try:
                    work = os.path.join(tmp, "repo")
                    shutil.copytree(D.ROOT, work, ignore=shutil.ignore_patterns("__pycache__", ".git"))
                    self.assertEqual(self.run(work, "--check").returncode, 0, "--check should accept the committed file")
                    mod = os.path.join(work, PATH)
                    with open(mod, "a", encoding="utf-8") as fh:
                        fh.write('\\n\\ndef added_later(a, b=2):\\n    """Brand new helper."""\\n    return a + b\\n')
                    bad = self.run(work, "--check")
                    self.assertEqual(bad.returncode, 1, "--check must fail when the module gained a function")
                    done = self.run(work)
                    self.assertEqual(done.returncode, 0, done.stderr)
                    with open(os.path.join(work, "docs/API.md"), encoding="utf-8") as fh:
                        fresh = fh.read()
                    with open(mod, encoding="utf-8") as fh:
                        self.assertEqual(table_in(fresh), expected(fh.read()))
                    self.assertEqual(self.run(work, "--check").returncode, 0, "--check should accept the regenerated file")
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
        ''')
        test = common + (gen_tests if mode == "generator" else "")
        hidden = {"tests/docscheck.py": DOCSCHECK, "tests/test_api_table.py": test}
        if mode == "update":
            solution = {"docs/API.md": good}
            prompt = rng.choice(PROMPTS_UPDATE).format(path=path)
            d = 2 if len(funcs) <= 5 else 3
        else:
            gen_src = dd(f'''
            """Regenerate docs/API.md from {path} (or check that it is current)."""
            import ast
            import pathlib
            import sys

            ROOT = pathlib.Path(__file__).resolve().parent.parent
            SOURCE = ROOT / {json.dumps(path)}
            TARGET = ROOT / "docs" / "API.md"


            def render():
                tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
                rows = ["| Function | Signature | Summary |", "|---|---|---|"]
                for node in tree.body:
                    if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                        sig = "(" + ast.unparse(node.args) + ")"
                        doc = (ast.get_docstring(node) or "").strip().split("\\n")[0]
                        rows.append("| `%s` | `%s` | %s |" % (node.name, sig, doc))
                return "# API\\n\\n" + "\\n".join(rows) + "\\n"


            def main(argv):
                text = render()
                if "--check" in argv:
                    current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
                    if current != text:
                        print("docs/API.md is out of date; run tools/gen_api.py")
                        return 1
                    return 0
                TARGET.write_text(text, encoding="utf-8")
                return 0


            if __name__ == "__main__":
                sys.exit(main(sys.argv[1:]))
            ''')
            solution = {"tools/gen_api.py": gen_src, "docs/API.md": good}
            prompt = rng.choice(PROMPTS_GEN).format(path=path)
            d = 3 if len(funcs) <= 5 else 4
        prove_docs(f"{mod.key}-{mode}", start, hidden, solution, CMD, "python3 -m unittest discover -s tests -p 'test_beh*.py'")
        yield Task(slug=f"{i + 1:02d}-{mod.key}-{mode}", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution, verify=CMD,
                   tags=["api-docs", "generated-docs", "ast"], notes={"module": mod.key, "mode": mode, "functions": [f.name for f in funcs]})
