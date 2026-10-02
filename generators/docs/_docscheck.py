"""Hidden helper (tests/docscheck.py): what a docstring or README must say, derived mechanically from the code."""

TEXT = '''import ast
import copy
import inspect
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def parse(rel):
    return ast.parse(read(rel), rel)


def public_functions(tree):
    return [n for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]


def stripped_dump(fn):
    c = copy.deepcopy(fn)
    if c.body and isinstance(c.body[0], ast.Expr) and isinstance(getattr(c.body[0], "value", None), ast.Constant) \\
            and isinstance(c.body[0].value.value, str):
        c.body = c.body[1:] or [ast.Pass()]
    return ast.dump(c)


def explicit_raises(fn):
    names = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Raise) and n.exc is not None:
            e = n.exc.func if isinstance(n.exc, ast.Call) else n.exc
            if isinstance(e, ast.Name):
                names.add(e.id)
            elif isinstance(e, ast.Attribute):
                names.add(e.attr)
    return names


def returns_value(fn):
    for n in ast.walk(fn):
        if isinstance(n, ast.Return) and n.value is not None and not (isinstance(n.value, ast.Constant) and n.value.value is None):
            return True
    return False


def params(fn):
    a = fn.args
    names = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
    if a.vararg:
        names.append(a.vararg.arg)
    if a.kwarg:
        names.append(a.kwarg.arg)
    return [n for n in names if n not in ("self", "cls")]


SECTION_RE = re.compile(r"^(Args|Returns|Raises|Attributes|Example|Examples|Yields|Note|Notes):\\s*$")
ENTRY_RE = re.compile(r"^ {4}(\\*{0,2}\\w+)(?: \\(([^)]*)\\))?:\\s*(.*)$")


def sections(doc):
    """Parse a Google style docstring: summary, and per section the raw lines; Args/Raises entries as {name: description}."""
    lines = inspect.cleandoc(doc).split("\\n")
    out = {"summary": next((ln.strip() for ln in lines if ln.strip()), ""), "sections": {}}
    cur = None
    for ln in lines:
        m = SECTION_RE.match(ln)
        if m:
            cur = m.group(1)
            out["sections"][cur] = []
        elif cur is not None:
            out["sections"][cur].append(ln)
    parsed = {}
    for name, body in out["sections"].items():
        if name in ("Args", "Raises", "Attributes"):
            entries, last = {}, None
            for ln in body:
                m = ENTRY_RE.match(ln)
                if m:
                    last = m.group(1).lstrip("*")
                    entries[last] = m.group(3).strip()
                elif last is not None and ln.strip() and ln.startswith("     "):
                    entries[last] += " " + ln.strip()
            parsed[name] = entries
        else:
            parsed[name] = " ".join(x.strip() for x in body if x.strip())
    out["parsed"] = parsed
    return out


def words(text):
    return len(re.findall(r"[A-Za-z0-9]+", text))
'''
