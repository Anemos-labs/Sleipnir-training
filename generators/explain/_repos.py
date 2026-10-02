"""Generated repositories for the explain families.

``make_repo(rng, lang, tier, **flags)`` builds a small-to-medium project from the IR model (``_ir``), renders it in the
requested language (``_render``) and returns a ``Repo``: the files the agent sees plus ground truth that is known by
construction (call graph, import graph, public surface, coverage, printed output).

Two independent analysers cross-check the rendering while the family is built (a mismatch raises, so a build either
yields consistent truth or fails loudly):

* ``py_analyse`` parses the generated python with ``ast`` (resolving relative imports, aliases, function-local imports)
  and recovers definitions, call edges, import edges and star-export lists.
* ``lex_check`` scans the text of the other languages and recovers the same call edges from the rendered source
  (identifier uniqueness lets it work without a parser).
"""
from __future__ import annotations

import ast
import random
import re
from dataclasses import dataclass, field

from . import _ir as I
from . import _render as R

LANG_ORDER = ["python", "javascript", "go", "java", "rust", "ruby"]
LANG_LABEL = {"python": "Python", "javascript": "JavaScript", "go": "Go", "java": "Java", "rust": "Rust", "ruby": "Ruby"}
LANG_FNWORD = {"python": "function", "javascript": "function", "go": "function", "java": "method", "rust": "function", "ruby": "method"}


@dataclass
class Repo:
    lang: str
    proj: I.Project
    rend: R.Rendered
    files: dict
    flags: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ names and places
    def ident(self, fid: str) -> str:
        return self.rend.ident[fid]

    def idents(self, fids) -> list:
        return sorted(self.rend.ident[f] for f in fids)

    def quals(self, fids) -> list:
        return sorted(self.qual(f) for f in fids)

    def qual(self, fid: str) -> str:
        """module.function in the language's own spelling (what a human would write)"""
        m = self.proj.mod_of(fid)
        f = self.proj.fns[fid]
        i = self.rend.ident[fid]
        if self.lang == "python":
            return f"{m.base}.{i}"
        if self.lang == "javascript":
            return f"{m.base}.{i}"
        if self.lang == "go":
            return f"{m.base}.{i}"
        if self.lang == "java":
            return f"{R.cap1(m.base) if m.layer != 'cli' else 'Main'}.{i}"
        if self.lang == "rust":
            return f"{m.base}::{i}"
        return f"{R.pascal(m.base) if m.layer != 'cli' else 'Cli'}.{i}"

    def path_of(self, fid: str) -> str:
        return self.rend.fn_line[fid][0]

    def line_of(self, fid: str) -> int:
        return self.rend.fn_line[fid][1]

    def mod_path(self, mkey: str) -> str:
        return self.rend.path[mkey]

    def sites_of(self, callee: str, tests: bool = False) -> list:
        """(caller, path, line) for every call of ``callee`` in the sources (and, with tests=True, in the test files too;
        the caller of a test site is ``test:<case name>``), sorted by path and line"""
        out = [(c, p, ln) for c, e, p, ln in self.rend.sites if e == callee and (tests or not c.startswith("test:"))]
        return sorted(out, key=lambda t: (t[1], t[2], t[0]))

    def source_paths(self) -> list:
        tests = set(self.rend.test_paths)
        return sorted(p for p in self.files if p in self.rend.path.values() and p not in tests)

    def test_dir_files(self) -> list:
        return sorted(self.rend.test_paths)

    @property
    def fns(self) -> dict:
        return self.proj.fns

    def public_fns(self) -> list:
        return [f for f, fn in self.proj.fns.items() if fn.public and fn.kind == "fn"]

    def entry_run(self) -> str:
        return {"python": "python3 -m %s", "javascript": "node bin/%s.js", "go": "go run ./cmd/%s", "ruby": "ruby bin/%s",
                "rust": "cargo run --quiet --", "java": "java -cp build %s.Main"}[self.lang] % self.proj.name if self.lang not in ("rust",) else "cargo run --quiet --"

    def const_ident(self, mkey: str, name: str) -> str:
        """spelling of a module constant in the language"""
        if self.lang == "go":
            m = self.proj.mods[mkey]
            return self.rend_const(m, name)
        return name

    def rend_const(self, m, name: str) -> str:
        return R.camel(name.lower()) if "_" in name else R.camel(f"{m.base}_{name.lower()}")

    def run_cmd(self, a: int, b: int) -> str:
        n = self.proj.name
        return {"python": f"python3 -m {n} {a} {b}", "javascript": f"node bin/{n}.js {a} {b}", "go": f"go run ./cmd/{n} {a} {b}",
                "java": f"java -cp build {n}.Main {a} {b}", "rust": f"cargo run --quiet -- {a} {b}", "ruby": f"ruby bin/{n} {a} {b}"}[self.lang]

    def tests_mentioning(self, fid: str) -> list:
        return [c for c in self.proj.cases if c.fid == fid]

    def case_ident(self, case) -> str:
        return self.rend.tests[case.name][2]

    # ------------------------------------------------------------------ dynamic facts
    def run_main(self, count: int, days: int):
        tr = I.Trace()
        v = self.proj.run(self.proj.main_fid, [count, days], tr)
        return v, tr

    def coverage_of_case(self, case) -> list:
        tr = I.Trace()
        try:
            self.proj.run(case.fid, case.args, tr)
        except I.Raised:
            pass
        return list(tr.executed)

    def dead_from_main(self) -> list:
        live = set(self.proj.reach(self.proj.main_fid)) | {self.proj.main_fid}
        return sorted(f for f in self.proj.fns if f not in live)


def make_repo(rng: random.Random, lang: str, tier: int, check: bool = True, **flags) -> Repo:
    spec = I.Spec(lang=lang, tier=tier, **flags)
    for attempt in range(25):
        proj = I.make_project(rng, spec)
        try:
            rend = R.render(proj, rng)
        except Exception:  # noqa: BLE001
            continue
        repo = Repo(lang=lang, proj=proj, rend=rend, files=rend.files, flags=dict(flags))
        if check:
            cross_check(repo)
        return repo
    raise RuntimeError("cannot build a repo")


# ====================================================================================================================
# python analyser (ast)
# ====================================================================================================================
def py_analyse(files: dict, root: str) -> dict:
    mods: dict = {}
    for path, text in files.items():
        if path.startswith(root + "/") and path.endswith(".py"):
            dotted = path[:-3].replace("/", ".")
            if dotted.endswith(".__init__"):
                dotted = dotted[: -len(".__init__")]
            mods[dotted] = (path, ast.parse(text, path))
    defs: dict = {}
    for dotted, (path, tree) in mods.items():
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                defs[(dotted, node.name)] = node.lineno

    def pkg_of(dotted: str) -> str:
        path = mods[dotted][0]
        return dotted if path.endswith("__init__.py") else dotted.rsplit(".", 1)[0]

    def bindings(stmts, dotted):
        b: dict = {}
        edges: set = set()
        for node in stmts:
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    base_pkg = pkg_of(dotted)
                    for _ in range(node.level - 1):
                        base_pkg = base_pkg.rsplit(".", 1)[0]
                    base = base_pkg + ("." + node.module if node.module else "")
                else:
                    base = node.module
                for al in node.names:
                    full = f"{base}.{al.name}"
                    name = al.asname or al.name
                    if full in mods:
                        b[name] = ("mod", full)
                        edges.add(full)
                    else:
                        b[name] = ("sym", (base, al.name))
                        if base in mods:
                            edges.add(base)
            elif isinstance(node, ast.Import):
                for al in node.names:
                    name = al.asname or al.name.split(".")[0]
                    if al.name in mods:
                        b[name] = ("mod", al.name) if al.asname else ("pkg", al.name)
                        edges.add(al.name)
        return b, edges

    calls: set = set()
    imports: dict = {}
    exports: dict = {}
    for dotted, (path, tree) in mods.items():
        top, edges = bindings(tree.body, dotted)
        allnames = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
                allnames = [e.value for e in node.value.elts]
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            loc, ledges = bindings(node.body, dotted)
            edges |= ledges
            env = {**top, **loc}
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                fn = sub.func
                if isinstance(fn, ast.Name):
                    if fn.id in env and env[fn.id][0] == "sym":
                        tgt = env[fn.id][1]
                    elif (dotted, fn.id) in defs:
                        tgt = (dotted, fn.id)
                    else:
                        continue
                elif isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and env.get(fn.value.id, ("",))[0] == "mod":
                    tgt = (env[fn.value.id][1], fn.attr)
                else:
                    continue
                if tgt in defs:
                    calls.add(((dotted, node.name), tgt))
        imports[dotted] = edges - {dotted}
        names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]
        if allnames is not None:
            names = [n for n in names if n in allnames]
        exports[dotted] = sorted(names)
    return {"defs": defs, "calls": calls, "imports": imports, "exports": exports, "mods": set(mods)}


def cross_check(repo: Repo):
    if repo.lang == "python":
        py_cross_check(repo)
    else:
        lex_cross_check(repo)
        lex_import_check(repo)


def py_cross_check(repo: Repo):
    p, root = repo.proj, repo.proj.name
    a = py_analyse(repo.files, root)

    def fid_of(dotted: str, name: str) -> str:
        key = dotted[len(root) + 1:] if dotted != root else ""
        return f"{key}.{name.lstrip('_')}"

    model = {(c, e) for c in p.fns for e in p.callees(c)}
    got = {(fid_of(*x), fid_of(*y)) for x, y in a["calls"]}
    if model != got:
        raise AssertionError(f"python call edges differ: model-only {sorted(model - got)[:5]} ast-only {sorted(got - model)[:5]}")
    # imports between project modules
    def mkey(dotted):
        return dotted[len(root) + 1:]
    for k, v in p.import_edges().items():
        d = f"{root}.{k}"
        g = {mkey(x) for x in a["imports"].get(d, set()) if x != root and mkey(x) in p.mods}
        if g != set(v):
            raise AssertionError(f"python import edges differ for {k}: model {sorted(v)} ast {sorted(g)}")
    # star exports
    for k, m in p.mods.items():
        if m.layer in ("errors",):
            continue
        d = f"{root}.{k}"
        want = sorted(r_name for r_name in repo.exported_names(k))
        if want != a["exports"].get(d, []):
            raise AssertionError(f"python exports differ for {k}: model {want} ast {a['exports'].get(d)}")
    # definition lines
    for fid, (path, line) in repo.rend.fn_line.items():
        f = p.fns[fid]
        if f.kind == "main" or fid == "cli.main":
            continue
        d = f"{root}.{f.mod}"
        nm = repo.rend.ident[fid]
        if a["defs"].get((d, nm)) != line:
            raise AssertionError(f"python def line differs for {fid}: model {line} ast {a['defs'].get((d, nm))}")


def _exported_names(self: Repo, mkey: str) -> list:
    """names `from module import *` would bring in (python) / the module's public surface (other languages)"""
    p = self.proj
    m = p.mods[mkey]
    fids = [f for f in m.fids if p.fns[f].public and p.fns[f].kind == "fn" or (p.fns[f].kind == "main")]
    if self.lang == "python" and m.all_list:
        fids = [f for f in fids if f in m.all_names]
    return sorted(self.rend.ident[f] for f in fids)


Repo.exported_names = _exported_names


# ====================================================================================================================
# lexical analyser for the other languages
# ====================================================================================================================
DEF_RE = {
    "javascript": re.compile(r"^function (\w+)\("),
    "go": re.compile(r"^func (\w+)\("),
    "java": re.compile(r"^\s+(?:public|private) static (?:long|void) (\w+)\("),
    "rust": re.compile(r"^(?:pub )?fn (\w+)\("),
    "ruby": re.compile(r"^\s+def self\.(\w+)"),
}
CALL_RE = re.compile(r"(?<![\w.])((?:[A-Za-z_][\w]*(?:::|\.))*[A-Za-z_]\w*)\(")


def lex_cross_check(repo: Repo):
    """Recover call edges from rendered text: every identifier followed by ``(`` inside a function body that spells a
    known function (unique names), optionally qualified by its module, is an edge."""
    p = repo.proj
    if repo.flags.get("dup"):
        return
    by_ident: dict = {}
    for fid, f in p.fns.items():
        if f.kind == "fn" or fid == "cli.main":
            by_ident.setdefault(repo.rend.ident[fid], []).append(fid)
    if any(len(v) > 1 for k, v in by_ident.items() if k != "main"):
        return
    rx = DEF_RE[repo.lang]
    got: set = set()
    # sources
    for mk, path in repo.rend.path.items():
        m = p.mods[mk]
        if m.layer == "errors":
            continue
        lines = repo.files[path].split("\n")
        cur = None
        for ln in lines:
            d = rx.match(ln)
            if d:
                nm = d.group(1)
                cur = by_ident.get(nm, [None])[0] if nm != "main" else "cli.main"
                continue
            if cur is None:
                continue
            for mm in CALL_RE.finditer(ln):
                head = mm.group(1)
                last = re.split(r"::|\.", head)[-1]
                if last in by_ident and last != "main":
                    got.add((cur, by_ident[last][0]))
    # main wrappers
    if repo.lang == "rust":
        got.add(("cli.main", "cli.run"))
    model = {(c, e) for c in p.fns for e in p.callees(c)}
    if repo.lang == "go":
        model = {(c, e) for c, e in model}
    if model != got:
        raise AssertionError(f"{repo.lang} call edges differ: model-only {sorted(model - got)[:5]} lexical-only {sorted(got - model)[:5]}")


# ====================================================================================================================
# lexical import analyser (non-python)
# ====================================================================================================================
def lex_import_check(repo: Repo):
    """Recover module-to-module dependencies from the import lines (and, for Java, same-package class references)."""
    import posixpath
    p = repo.proj
    path2mod = {pth: k for k, pth in repo.rend.path.items() if p.mods[k].layer != "errors"}
    errs = p.exc_mod()
    key_set = {k for k in p.mods if p.mods[k].layer != "errors"}
    got: dict = {}
    for mk, path in repo.rend.path.items():
        m = p.mods[mk]
        if m.layer == "errors":
            continue
        text = repo.files[path]
        deps: set = set()
        if repo.lang == "javascript":
            for rel in re.findall(r"require\('([^']+)'\)", text):
                tgt = posixpath.normpath(posixpath.join(posixpath.dirname(path), rel)) + ".js"
                if tgt in path2mod:
                    deps.add(path2mod[tgt])
                elif posixpath.basename(tgt) == "errors.js" and errs:
                    deps.add(errs)
        elif repo.lang == "ruby":
            for rel in re.findall(r"require_relative '([^']+)'", text):
                tgt = posixpath.normpath(posixpath.join(posixpath.dirname(path), rel)) + ".rb"
                if tgt in path2mod:
                    deps.add(path2mod[tgt])
                elif tgt.endswith("errors.rb") and errs:
                    deps.add(errs)
        elif repo.lang == "go":
            pre = f"example.com/{p.name}/internal/"
            for imp in re.findall(r'"(example\.com/[^"]+)"', text):
                rest = imp[len(pre):]
                key = ".".join(rest.split("/")[:-1] + [rest.split("/")[-1]])
                if key in key_set:
                    deps.add(key)
        elif repo.lang == "rust":
            for u in re.findall(r"^use crate::([^;]+);", text, re.M):
                segs = [x for x in re.split(r"::", u.split("{")[0].rstrip(":")) if x]
                for j in range(len(segs), 0, -1):
                    key = ".".join(segs[:j])
                    if key in key_set:
                        deps.add(key)
                        break
        elif repo.lang == "java":
            for imp in re.findall(r"^import (?:static )?([\w.]+);", text, re.M):
                parts = imp.split(".")
                for j in range(len(parts), 0, -1):
                    cand = ".".join(parts[:j])
                    for k2 in key_set:
                        m2 = p.mods[k2]
                        full = ".".join([p.name] + ([m2.pkg] if m2.pkg else []) + [repo.rend_class(k2)])
                        if cand == full:
                            deps.add(k2)
            # same package classes referenced by simple name
            for k2 in key_set:
                m2 = p.mods[k2]
                if k2 != mk and m2.pkg == m.pkg and re.search(r"\b" + repo.rend_class(k2) + r"\.", text):
                    deps.add(k2)
        deps.discard(mk)
        deps.discard(errs)
        got[mk] = deps
    for mk, want in p.import_edges().items():
        if p.mods[mk].layer == "errors":
            continue
        w = {x for x in want if p.mods[x].layer != "errors"}
        if w != got.get(mk, set()):
            raise AssertionError(f"{repo.lang} import edges differ for {mk}: model {sorted(w)} lexical {sorted(got.get(mk, set()))}")


def _rend_class(self: Repo, mkey: str) -> str:
    m = self.proj.mods[mkey]
    return "Main" if m.layer == "cli" else R.cap1(m.base)


Repo.rend_class = _rend_class
