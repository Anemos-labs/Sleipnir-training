"""Structural analysis helpers for refactoring checks (python, standard library only)."""
import ast
import copy
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def path(*parts):
    return os.path.join(ROOT, *parts)


def read(rel):
    with open(path(rel), encoding="utf-8") as f:
        return f.read()


def exists(rel):
    return os.path.exists(path(rel))


def parse(rel):
    return ast.parse(read(rel), rel)


def py_files(rel_dir="."):
    """Every .py file below rel_dir (relative paths), skipping tests, caches and hidden directories."""
    out = []
    base = path(rel_dir)
    for dp, dns, fns in os.walk(base):
        dns[:] = sorted(d for d in dns if d not in ("tests", "test", "__pycache__", "checks") and not d.startswith("."))
        for fn in sorted(fns):
            if fn.endswith(".py"):
                out.append(os.path.relpath(os.path.join(dp, fn), ROOT).replace(os.sep, "/"))
    return out


def functions(tree, prefix=""):
    """(qualified name, node) for every function and method, nested ones included."""
    out = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            q = prefix + node.name
            out.append((q, node))
            out.extend(functions(node, q + "."))
        elif isinstance(node, ast.ClassDef):
            out.extend(functions(node, prefix + node.name + "."))
        else:
            out.extend(functions(node, prefix))
    return out


def classes(tree):
    return [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]


def loc(node, src):
    """Non-blank, non-comment source lines of a node, docstring excluded."""
    lines = src.splitlines()
    first = node.lineno
    last = node.end_lineno
    skip = set()
    body = getattr(node, "body", [])
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        skip = set(range(body[0].lineno, body[0].end_lineno + 1))
    n = 0
    for i in range(first, last + 1):
        if i in skip:
            continue
        s = lines[i - 1].strip()
        if s and not s.startswith("#"):
            n += 1
    return n


def complexity(node):
    c = 1
    for n in ast.walk(node):
        if isinstance(n, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler, ast.comprehension)):
            c += 1
        elif isinstance(n, ast.BoolOp):
            c += len(n.values) - 1
        elif hasattr(ast, "match_case") and isinstance(n, ast.match_case):
            c += 1
    return c


def branch_nodes(node):
    """Number of if/elif/match-case/ternary decision points inside node."""
    c = 0
    for n in ast.walk(node):
        if isinstance(n, (ast.If, ast.IfExp)):
            c += 1
        elif hasattr(ast, "match_case") and isinstance(n, ast.match_case):
            c += 1
    return c


class _Norm(ast.NodeTransformer):
    def visit_Name(self, node):
        return ast.copy_location(ast.Name(id="_", ctx=node.ctx), node)

    def visit_arg(self, node):
        return ast.copy_location(ast.arg(arg="_", annotation=None), node)

    def visit_Attribute(self, node):
        self.generic_visit(node)
        return ast.copy_location(ast.Attribute(value=node.value, attr="_", ctx=node.ctx), node)

    def visit_Constant(self, node):
        v = node.value
        if isinstance(v, bool) or v is None:
            return node
        return ast.copy_location(ast.Constant(value=type(v)()), node)

    def visit_keyword(self, node):
        self.generic_visit(node)
        return ast.keyword(arg="_" if node.arg else None, value=node.value)

    def visit_JoinedStr(self, node):
        return ast.copy_location(ast.Constant(value=""), node)


def stmt_count(nodes):
    return sum(1 for b in nodes for n in ast.walk(b) if isinstance(n, ast.stmt))


def fingerprint(stmts):
    """Shape of a statement list with names, attributes, argument names and literal values abstracted away."""
    mod = ast.Module(body=copy.deepcopy(list(stmts)), type_ignores=[])
    mod = _Norm().visit(mod)
    return ast.dump(mod, annotate_fields=False)


def body_without_doc(fn):
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return body


def duplicate_functions(files, min_stmts=4):
    """Groups of functions (across files) whose bodies have the same shape and at least min_stmts statements."""
    seen = {}
    for rel in files:
        tree = parse(rel)
        for q, fn in functions(tree):
            body = body_without_doc(fn)
            if stmt_count(body) < min_stmts:
                continue
            seen.setdefault(fingerprint(body), []).append(rel + ":" + q)
    return [v for v in seen.values() if len(v) > 1]


def repeated_windows(files, k=4):
    """Number of distinct k-statement sequences (shape only) that occur more than once, across all bodies."""
    seen = {}
    for rel in files:
        tree = parse(rel)
        for node in ast.walk(tree):
            for field in ("body", "orelse", "finalbody"):
                stmts = getattr(node, field, None)
                if not isinstance(stmts, list) or len(stmts) < k:
                    continue
                if not all(isinstance(s, ast.stmt) for s in stmts):
                    continue
                for i in range(len(stmts) - k + 1):
                    win = stmts[i:i + k]
                    if stmt_count(win) < k + 2:
                        continue
                    key = fingerprint(win)
                    seen.setdefault(key, set()).add((rel, win[0].lineno))
    return sum(1 for v in seen.values() if len(v) > 1)


def imports(rel):
    """Names of modules imported by a file (dotted, as written; relative imports resolved against the file)."""
    tree = parse(rel)
    pkg = os.path.dirname(rel).replace("/", ".")
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:
                parts = pkg.split(".") if pkg else []
                parts = parts[: len(parts) - (n.level - 1)] if n.level > 1 else parts
                base = ".".join(p for p in parts + ([n.module] if n.module else []) if p)
                for a in n.names:
                    out.add(base + "." + a.name if base else a.name)
            if base:
                out.add(base)
            if not n.level:
                for a in n.names:
                    out.add(base + "." + a.name)
    return out


def module_name(rel):
    m = rel[:-3].replace("/", ".")
    return m[: -len(".__init__")] if m.endswith(".__init__") else m


def import_cycles(files):
    """Cycles in the import graph restricted to the given project files (module names)."""
    mods = {module_name(f): f for f in files}
    graph = {}
    for name, rel in mods.items():
        deps = set()
        for imp in imports(rel):
            parts = imp.split(".")
            for i in range(len(parts), 0, -1):
                cand = ".".join(parts[:i])
                if cand in mods and cand != name:
                    deps.add(cand)
                    break
        graph[name] = deps
    cycles = []
    state = {}

    def dfs(n, stack):
        state[n] = 1
        for m in sorted(graph.get(n, ())):
            if state.get(m) == 1:
                cycles.append(stack[stack.index(m):] + [m] if m in stack else [n, m])
            elif m not in state:
                dfs(m, stack + [m])
        state[n] = 2

    for n in sorted(graph):
        if n not in state:
            dfs(n, [n])
    return cycles


def top_level_names(tree):
    out = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                for x in ast.walk(t):
                    if isinstance(x, ast.Name):
                        out.add(x.id)
    return out


def called_names(node):
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                out.append(f.id)
            elif isinstance(f, ast.Attribute):
                out.append(f.attr)
    return out


def dotted_calls(node):
    """Dotted call targets such as time.time or datetime.datetime.now."""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            parts = []
            f = n.func
            while isinstance(f, ast.Attribute):
                parts.append(f.attr)
                f = f.value
            if isinstance(f, ast.Name):
                parts.append(f.id)
                out.append(".".join(reversed(parts)))
    return out


def format_problems(problems):
    return "\n".join("  - " + p for p in problems)
