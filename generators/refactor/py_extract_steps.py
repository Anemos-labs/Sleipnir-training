"""Extract-function refactors (python): a long function that does everything becomes small named steps."""
from __future__ import annotations

import pprint
import random
from string import Template

from fx import Task, dd, family

from . import _kit
from ._kit import indent, prove, py_behaviour, py_structlib
from ._py_domains import DOMAINS, Domain

structlib = _kit.load_structlib()


def _module_doc(dom: Domain) -> str:
    return f'"""{dom.doc[:-1] if dom.doc.endswith(".") else dom.doc} ({dom.topic})."""\n'


def _epilogue(dom, stages):
    names = [s.name for s in stages]
    return dom.epilogue(names) if callable(dom.epilogue) else dom.epilogue


def build_start(dom: Domain, stages, params, header: str) -> str:
    parts = [f"# --- {s.title} ---\n" + Template(s.body).substitute(params).strip("\n") for s in stages]
    body = "\n\n".join(parts) + "\n\n" + _epilogue(dom, stages)
    return (_module_doc(dom) + f"\n{header}\n\ndef {dom.entry}({dom.sig}):\n    \"\"\"{dom.doc}\"\"\"\n" + indent(body, 4) + "\n")


def _helper(s: Stage, params, name: str) -> str:
    body = Template(s.body).substitute(params).strip("\n")
    if s.outs:
        body += "\nreturn " + ", ".join(s.outs)
    return f'\ndef {name}({", ".join(s.ins)}):\n    """{s.doc}"""\n' + indent(body, 4) + "\n"


def _calls(stages, prefix: str, qual: str = "") -> str:
    out = []
    for s in stages:
        lhs = ", ".join(s.outs)
        out.append(f"{lhs + ' = ' if lhs else ''}{qual}{prefix}{s.name}({', '.join(s.ins)})")
    return "\n".join(out)


def build_solution(dom: Domain, stages, params, header: str, public: set) -> str:
    """Whole-module extraction: every stage a helper (names in `public` without the leading underscore)."""
    out = [_module_doc(dom), header]
    for s in stages:
        out.append(_helper(s, params, s.name if s.name in public else "_" + s.name))
    calls = "\n".join(
        f"{', '.join(s.outs) + ' = ' if s.outs else ''}{s.name if s.name in public else '_' + s.name}({', '.join(s.ins)})" for s in stages)
    out.append(f'\ndef {dom.entry}({dom.sig}):\n    """{dom.doc}"""\n' + indent(calls + "\n" + _epilogue(dom, stages), 4) + "\n")
    return "\n".join(out)


def build_split(dom: Domain, stages, params, header: str, other: str) -> tuple[str, str]:
    """(entry module, helper module): helpers public in the helper module, entry module just calls them."""
    helpers = [_module_doc(dom), header] + [_helper(s, params, s.name) for s in stages]
    entry = (_module_doc(dom) + f"\nfrom . import {other}\n\n\ndef {dom.entry}({dom.sig}):\n    \"\"\"{dom.doc}\"\"\"\n"
             + indent(_calls(stages, "", other + ".") + "\n" + _epilogue(dom, stages), 4) + "\n")
    return entry, "\n".join(helpers)


def _visible_test(dom: Domain, cases, want, cls):
    lines = [f"import unittest", "", f"from {dom.package}.{dom.module} import {dom.entry}", "", "", f"class {cls}Tests(unittest.TestCase):"]
    ok = [i for i, w in enumerate(want) if not (isinstance(w, dict) and "raises" in w)][:3]
    bad = [i for i, w in enumerate(want) if isinstance(w, dict) and "raises" in w][:1]
    for k, i in enumerate(ok):
        lines += [f"    def test_case_{k + 1}(self):", f"        args = {pprint.pformat(cases[i], width=88, compact=True)}",
                  f"        self.assertEqual({dom.entry}(*args), {pprint.pformat(want[i], width=88, compact=True)})", ""]
    for i in bad:
        lines += ["    def test_rejects_bad_input(self):", f"        args = {pprint.pformat(cases[i], width=88, compact=True)}",
                  f"        with self.assertRaises({want[i]['raises']}):", f"            {dom.entry}(*args)", ""]
    lines += ["", "if __name__ == '__main__':", "    unittest.main()", ""]
    return "\n".join(lines)


PROMPTS_ALL = [
    "`{entry}` in `{path}` has grown into one {n}-line function that does everything in a single pass. "
    "Please break it into smaller named steps so it reads as an outline. No function (the entry point included) should be longer "
    "than {limit} lines, not counting blank lines, comments and docstrings. Behaviour must stay exactly the same; the existing tests are the safety net.",
    "Code review comment on the {topic} code: \"`{entry}` is {n} lines and does at least {k} unrelated things. I can't review it. "
    "Split it into helpers with clear names and keep each function under {limit} lines.\" Can you address that? The public function and what it returns must not change.",
    "refactor `{entry}` ({path}): too long, split into steps, max {limit} lines per function. same outputs for every input, tests must stay green",
    "We keep touching `{entry}` for every rule change in our {topic} code and every time someone breaks a neighbouring rule, because it is one long block "
    "of {n} lines. Restructure it into separate steps (one function per concern) so the rules can be changed in isolation. Keep every function "
    "at {limit} lines or fewer (blank lines, comments and docstrings are not counted). Don't change the observable behaviour, including which "
    "exceptions are raised and what the messages say.",
    "Tidy-up task: the {topic} code's `{entry}` works but nobody wants to read it ({n} lines). Extract helper functions so that no function is "
    "over {limit} lines. Keep `{entry}` as the entry point with the same signature, and make sure the visible tests still pass.",
]

PROMPTS_ONE = [
    "In `{path}`, the `{entry}` function mixes several rules. Pull the part that handles {title} out into its own function called `{fname}` "
    "and call it from `{entry}`. Behaviour must not change.",
    "Please extract the {title} logic from `{entry}` ({path}) into a separate function named `{fname}`. It is the first step of breaking the "
    "function up, so do just this one; everything else stays put and all tests must still pass.",
    "`{entry}` is hard to follow. Start by moving the {title} block into a helper named `{fname}` that `{entry}` calls. Keep the results identical.",
]

PROMPTS_SPLIT = [
    "`{entry}` in `{path}` is a {n}-line monolith. Break it into steps no longer than {limit} lines each, and move those step functions into a new "
    "module `{package}/{other}.py` so that `{path}` only orchestrates them. `from {package}.{module} import {entry}` has to keep working and the "
    "behaviour must not change. Watch out for import cycles between the two modules.",
    "Refactor request for the {topic} code: split `{entry}` ({n} lines) into small helpers (max {limit} lines each) living in `{package}/{other}.py`; "
    "`{package}/{module}.py` keeps the public `{entry}` and just calls the helpers. No circular imports, same results as before.",
]


def _compose(dom: Domain, rng: random.Random, k_opt: int):
    header, ctx = dom.header(rng)
    params = dom.params(rng, ctx)
    opts = [s for s in dom.stages if s.optional]
    keep = set(rng.sample([s.name for s in opts], min(k_opt, len(opts))))
    stages = [s for s in dom.stages if not s.optional or s.name in keep]
    return header, ctx, params, stages


@family("refactor-py-extract-steps", category="refactor", lang="python", kind="refactor", n=14,
        summary="break a long multi-purpose function into small named steps (whole function, one named helper, or helpers in a new module)")
def gen(rng, n):
    modes = ["one"] * 3 + ["all"] * 7 + ["split"] * 4
    rng.shuffle(modes)
    doms = list(DOMAINS) * 3
    rng.shuffle(doms)
    for i in range(n):
        mode = modes[i]
        dom = doms[i]
        k_opt = {"one": rng.choice([2, 3]), "all": rng.choice([2, 3, 4, 5]), "split": rng.choice([3, 4, 5])}[mode]
        header, ctx, params, stages = _compose(dom, rng, k_opt)
        start_src = build_start(dom, stages, params, header)
        pkg_init = {f"{dom.package}/__init__.py": ""}
        cases = dom.cases(rng, ctx, 26)
        harness = f"from {dom.package}.{dom.module} import {dom.entry}\n\ndef run_case(a):\n    return {dom.harness_call}\n"
        start_files = {dom.path: start_src, **pkg_init}
        want = _kit.py_golden(start_files, harness, cases)
        hidden = {"tests/test_more_behaviour.py": py_behaviour(start_files, harness, cases, "recorded"), **py_structlib()}
        visible = {f"tests/test_{dom.module}.py": _visible_test(dom, cases, want, dom.module.title())}
        start = {**start_files, **visible}
        n_lines = structlib.loc(_find(start_src, dom.entry), start_src)

        if mode == "one":
            st = rng.choice([s for s in stages if len(Template(s.body).substitute(params).strip().splitlines()) >= 4])
            pub = {st.name}
            sol_src = build_solution(dom, stages, params, header, pub)
            # only the named stage is extracted in the reference; keep it simple: full extraction also satisfies the check
            stage_loc = len([ln for ln in Template(st.body).substitute(params).splitlines() if ln.strip()])
            struct = _struct_one(dom, st.name, n_lines, stage_loc)
            prompt = rng.choice(PROMPTS_ONE).format(entry=dom.entry, path=dom.path, title=st.title, fname=st.name)
            diff = 1 if stage_loc <= 7 else 2
            solution = {dom.path: sol_src}
            tags = ["extract-function", "single-extraction"]
        else:
            sol_src = build_solution(dom, stages, params, header, set())
            helpers_loc = [structlib.loc(f, sol_src) for _, f in structlib.functions(__import__("ast").parse(sol_src))]
            limit = max(15, -(-(max(helpers_loc) + 3) // 5) * 5)
            if n_lines <= limit + 8:
                limit = max(12, -(-(max(helpers_loc) + 1) // 5) * 5 - 5)
                limit = max(limit, max(helpers_loc) + 1)
            if n_lines <= limit + 6:
                raise RuntimeError(f"{dom.key}: start entry has {n_lines} lines, limit {limit}: not a meaningful refactor")
            if mode == "all":
                struct = _struct_all(dom, limit, len(stages))
                prompt = rng.choice(PROMPTS_ALL).format(entry=dom.entry, path=dom.path, n=n_lines, limit=limit, k=min(len(stages), 4),
                                                        topic=dom.topic)
                diff = 2 if len(stages) <= 5 else 3 if len(stages) <= 6 else 4
                solution = {dom.path: sol_src}
                tags = ["extract-function", "split-long-function"]
            else:
                other = rng.choice(["steps", "rules", "stages", "helpers"])
                entry_mod, helper_mod = build_split(dom, stages, params, header, other)
                solution = {dom.path: entry_mod, f"{dom.package}/{other}.py": helper_mod}
                struct = _struct_split(dom, limit, other, len(stages))
                prompt = rng.choice(PROMPTS_SPLIT).format(entry=dom.entry, path=dom.path, n=n_lines, limit=limit, package=dom.package,
                                                          module=dom.module, other=other, topic=dom.topic)
                diff = 4
                tags = ["extract-function", "split-module", "import-cycles"]
        hidden["tests/test_zz_structure.py"] = struct
        prove(f"{dom.key}/{mode}", start, hidden, solution, _kit.PY_BEHAVIOUR_CMD, _kit.PY_STRUCT_CMD,
              "python3 -m unittest discover -s tests")
        yield Task(
            slug=f"{i + 1:02d}-{dom.key}-{mode}", prompt=prompt, difficulty=diff, start=start, hidden=hidden, solution=solution,
            verify="python3 -m unittest discover -s tests -v", tags=tags, notes={"domain": dom.key, "mode": mode, "stages": [s.name for s in stages], "entry_lines": n_lines})


def _find(src: str, name: str):
    import ast
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise RuntimeError("entry not found")


_STRUCT_HEAD = '''import ast
import unittest

import structlib as S

ENTRY_PATH = "{path}"
ENTRY = "{entry}"
'''


def _struct_all(dom, limit, nstages):
    return _STRUCT_HEAD.format(path=dom.path, entry=dom.entry) + dd(f'''
    LIMIT = {limit}
    MIN_FUNCTIONS = {max(3, nstages - 1)}


    class StructureTests(unittest.TestCase):
        def test_entry_point_still_exists(self):
            tree = S.parse(ENTRY_PATH)
            self.assertIn(ENTRY, [n.name for n in tree.body if isinstance(n, ast.FunctionDef)])

        def test_no_function_is_too_long(self):
            long_ones = []
            for rel in S.py_files("."):
                src = S.read(rel)
                for q, fn in S.functions(ast.parse(src)):
                    n = S.loc(fn, src)
                    if n > LIMIT:
                        long_ones.append("%s:%s has %d lines (limit %d)" % (rel, q, n, LIMIT))
            self.assertFalse(long_ones, "functions that are still too long:\\n" + S.format_problems(long_ones))

        def test_work_is_split_into_several_functions(self):
            count = 0
            for rel in S.py_files("."):
                count += len(S.functions(S.parse(rel)))
            self.assertGreaterEqual(count, MIN_FUNCTIONS, "expected the logic to be spread over several functions")
    ''')


def _struct_one(dom, fname, start_lines, stage_loc):
    return _STRUCT_HEAD.format(path=dom.path, entry=dom.entry) + dd(f'''
    NAME = "{fname}"
    START_LINES = {start_lines}
    STAGE_LINES = {stage_loc}


    class StructureTests(unittest.TestCase):
        def _all(self):
            out = []
            for rel in S.py_files("."):
                src = S.read(rel)
                for q, fn in S.functions(ast.parse(src)):
                    out.append((rel, q, fn, src))
            return out

        def test_helper_exists(self):
            names = [q.split(".")[-1] for _, q, _, _ in self._all()]
            self.assertIn(NAME, names, "expected a function called %s" % NAME)

        def test_entry_calls_helper(self):
            for rel, q, fn, src in self._all():
                if rel == ENTRY_PATH and q == ENTRY:
                    self.assertIn(NAME, S.called_names(fn), "%s should call %s" % (ENTRY, NAME))
                    return
            self.fail("entry point %s is missing" % ENTRY)

        def test_entry_got_shorter(self):
            for rel, q, fn, src in self._all():
                if rel == ENTRY_PATH and q == ENTRY:
                    n = S.loc(fn, src)
                    self.assertLessEqual(n, START_LINES - max(2, STAGE_LINES - 3),
                                         "%s still has %d lines; the extracted logic should have left it" % (ENTRY, n))
                    return
            self.fail("entry point %s is missing" % ENTRY)
    ''')


def _struct_split(dom, limit, other, nstages):
    return _STRUCT_HEAD.format(path=dom.path, entry=dom.entry) + dd(f'''
    LIMIT = {limit}
    PACKAGE = "{dom.package}"
    MIN_HELPERS = {max(3, nstages - 2)}


    class StructureTests(unittest.TestCase):
        def test_entry_point_still_exists(self):
            tree = S.parse(ENTRY_PATH)
            self.assertIn(ENTRY, [n.name for n in tree.body if isinstance(n, ast.FunctionDef)])

        def test_no_function_is_too_long(self):
            long_ones = []
            for rel in S.py_files("."):
                src = S.read(rel)
                for q, fn in S.functions(ast.parse(src)):
                    n = S.loc(fn, src)
                    if n > LIMIT:
                        long_ones.append("%s:%s has %d lines (limit %d)" % (rel, q, n, LIMIT))
            self.assertFalse(long_ones, S.format_problems(long_ones))

        def test_helpers_live_in_another_module_of_the_package(self):
            total = 0
            for rel in S.py_files(PACKAGE):
                if rel in (ENTRY_PATH, PACKAGE + "/__init__.py"):
                    continue
                total += len(S.functions(S.parse(rel)))
            self.assertGreaterEqual(total, MIN_HELPERS, "expected the step functions in a new module of the package")

        def test_entry_module_only_orchestrates(self):
            own = [q for q, fn in S.functions(S.parse(ENTRY_PATH))]
            self.assertLessEqual(len(own), 2, "the entry module should only keep the entry point (found %s)" % own)

        def test_no_import_cycles(self):
            cycles = S.import_cycles(S.py_files("."))
            self.assertFalse(cycles, "import cycles: %s" % cycles)
    ''')
