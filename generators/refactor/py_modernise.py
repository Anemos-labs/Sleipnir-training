"""Modernise legacy python idioms (python): a module written in an older style is brought up to date, idiom by idiom."""
from __future__ import annotations

import json
from string import Template

from fx import Task, dd, family

from . import _kit
from ._kit import prove, py_behaviour, py_structlib

structlib = _kit.load_structlib()

NOUNS = [("hive", "apiary"), ("crate", "depot"), ("plot", "allotment"), ("berth", "marina"), ("shelf", "stockroom"), ("sensor", "greenhouse"),
         ("loom", "weaving mill"), ("kiln", "pottery")]

# each idiom: legacy source, modern source (both templates over $n = noun), call cases, hidden-check key, prompt bullet
IDIOMS = {
    "percent": dict(
        legacy='''def ${n}_label(name, qty, unit):
    return "%s: %d %s" % (name, qty, unit)
''', modern='''def ${n}_label(name, qty, unit):
    return f"{name}: {qty} {unit}"
''', calls=lambda r: [["${n}_label", [r.choice(["north", "b7", "old"]), r.randrange(0, 90), r.choice(["kg", "m", "pcs"])]] for _ in range(3)],
        check="fstring", bullet="`%` string formatting and `str.format` become f-strings"),
    "format": dict(
        legacy='''def ${n}_summary(owner, count, total):
    return "{} owns {} of {} ({:.1f}%)".format(owner, count, total, 100.0 * count / total)
''', modern='''def ${n}_summary(owner, count, total):
    return f"{owner} owns {count} of {total} ({100.0 * count / total:.1f}%)"
''', calls=lambda r: [["${n}_summary", [r.choice(["ana", "bo"]), r.randrange(1, 9), r.randrange(10, 50)]] for _ in range(3)] + [["${n}_summary", ["x", 1, 0]]],
        check="fstring", bullet="`%` string formatting and `str.format` become f-strings"),
    "with_open": dict(
        legacy='''def read_${n}_notes(path):
    f = open(path)
    text = f.read()
    f.close()
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def append_${n}_note(path, note):
    f = open(path, "a")
    f.write(note + "\\n")
    f.close()
''', modern='''def read_${n}_notes(path):
    with open(path) as f:
        text = f.read()
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def append_${n}_note(path, note):
    with open(path, "a") as f:
        f.write(note + "\\n")
''', calls=None, check="with_open", bullet="files are opened with `with` (or pathlib helpers), never opened and closed by hand", files=True),
    "pathlib": dict(
        legacy='''def ${n}_log_path(base, name):
    return os.path.join(base, "logs", name + ".txt")


def ${n}_archive_name(path):
    stem, ext = os.path.splitext(os.path.basename(path))
    return os.path.join(os.path.dirname(path), "archive", stem + ".old" + ext)
''', modern='''def ${n}_log_path(base, name):
    return str(Path(base) / "logs" / f"{name}.txt")


def ${n}_archive_name(path):
    p = Path(path)
    return str(p.parent / "archive" / f"{p.stem}.old{p.suffix}")
''', calls=lambda r: [["${n}_log_path", [r.choice(["/srv/data", "data", "/var/lib/x"]), r.choice(["jan", "q3", "audit"])]] for _ in range(2)]
        + [["${n}_archive_name", [r.choice(["logs/jan.txt", "/srv/logs/q3.csv", "notes.md"])]] for _ in range(3)],
        check="pathlib", bullet="`os.path` calls become `pathlib.Path` operations", imports_legacy="import os", imports_modern="from pathlib import Path"),
    "comprehension": dict(
        legacy='''def ${n}_squares(values):
    out = []
    for v in values:
        if v % 2 == 0:
            out.append(v * v)
    return out


def ${n}_names(rows):
    names = []
    for row in rows:
        names.append(row["name"].title())
    return names
''', modern='''def ${n}_squares(values):
    return [v * v for v in values if v % 2 == 0]


def ${n}_names(rows):
    return [row["name"].title() for row in rows]
''', calls=lambda r: [["${n}_squares", [[r.randrange(0, 20) for _ in range(r.randrange(0, 8))]]] for _ in range(3)]
        + [["${n}_names", [[{"name": r.choice(["ada lovelace", "bo", "cy twombly"])} for _ in range(r.randrange(0, 4))]]] for _ in range(2)],
        check="comprehension", bullet="loops that only build a list with `append` become comprehensions"),
    "keys": dict(
        legacy='''def ${n}_lookup(table, key, default=None):
    if key in table.keys():
        return table[key]
    return default


def ${n}_report(table):
    lines = []
    for key in sorted(table.keys()):
        lines.append("%s=%s" % (key, table[key]))
    return lines
''', modern='''def ${n}_lookup(table, key, default=None):
    return table.get(key, default) if key in table else default


def ${n}_report(table):
    return [f"{key}={value}" for key, value in sorted(table.items())]
''', calls=lambda r: [["${n}_lookup", [{"a": 1, "b": 2}, r.choice(["a", "z"]), r.choice([None, 0])]] for _ in range(3)]
        + [["${n}_report", [{"x": 1, "b": 2, "m": 3}]], ["${n}_report", [{}]]],
        check="keys", bullet="`in d.keys()` and loops over `d.keys()` use the dict directly or `.items()`"),
    "isinstance": dict(
        legacy='''def ${n}_kind(value):
    if type(value) == int or type(value) == float:
        return "number"
    if type(value) == str:
        return "text"
    if type(value) == list or type(value) == tuple:
        return "sequence"
    return "other"
''', modern='''def ${n}_kind(value):
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, (list, tuple)):
        return "sequence"
    return "other"
''', calls=lambda r: [["${n}_kind", [v]] for v in [1, 2.5, "x", [1], None, {"a": 1}]],
        check="isinstance", bullet="`type(x) == T` comparisons become `isinstance`", note="bool is an int either way here: the tests avoid it"),
    "range_len": dict(
        legacy='''def ${n}_dot(weights, values):
    total = 0
    for i in range(len(weights)):
        total += weights[i] * values[i]
    return total


def ${n}_marked(items):
    out = []
    for i in range(len(items)):
        out.append("%d.%s" % (i + 1, items[i]))
    return out
''', modern='''def ${n}_dot(weights, values):
    return sum(w * v for w, v in zip(weights, values))


def ${n}_marked(items):
    return [f"{i}.{item}" for i, item in enumerate(items, 1)]
''', calls=lambda r: [["${n}_dot", [[r.randrange(1, 5) for _ in range(k)], [r.randrange(1, 9) for _ in range(k)]]] for k in (0, 2, 4)]
        + [["${n}_marked", [["a", "b", "c"][: r.randrange(0, 4)]]] for _ in range(2)],
        check="range_len", bullet="`range(len(x))` index loops become `zip`/`enumerate`"),
    "none_is": dict(
        legacy='''def ${n}_pick(first, second):
    if first != None:
        return first
    if second == None:
        return "none"
    return second
''', modern='''def ${n}_pick(first, second):
    if first is not None:
        return first
    if second is None:
        return "none"
    return second
''', calls=lambda r: [["${n}_pick", [a, b]] for a, b in [(None, None), (0, None), (None, "x"), ("", 3)]],
        check="none_is", bullet="comparisons with `None` use `is` / `is not`"),
    "lambda": dict(
        legacy='''${n}_double = lambda x: x * 2
${n}_clamp = lambda x, lo, hi: max(lo, min(hi, x))
''', modern='''def ${n}_double(x):
    return x * 2


def ${n}_clamp(x, lo, hi):
    return max(lo, min(hi, x))
''', calls=lambda r: [["${n}_double", [r.randrange(-5, 50)]] for _ in range(2)] + [["${n}_clamp", [r.randrange(-20, 60), 0, 40]] for _ in range(3)],
        check="lambda", bullet="names bound to a `lambda` become real `def` functions"),
    "except": dict(
        legacy='''def ${n}_to_int(text, default=None):
    try:
        return int(text)
    except:
        return default
''', modern='''def ${n}_to_int(text, default=None):
    try:
        return int(text)
    except (ValueError, TypeError):
        return default
''', calls=lambda r: [["${n}_to_int", [t, r.choice([None, -1])]] for t in ["12", "x", "", " 7 ", "3.5", None]],
        check="except", bullet="bare `except:` clauses name the exceptions they handle"),
    "class": dict(
        legacy='''class ${N}Base(object):
    def __init__(self, name):
        self.name = name

    def describe(self):
        return "base:" + self.name


class ${N}Entry(${N}Base):
    def __init__(self, name, count):
        super(${N}Entry, self).__init__(name)
        self.count = count

    def describe(self):
        return super(${N}Entry, self).describe() + ":%d" % self.count


def ${n}_entry_text(name, count):
    return ${N}Entry(name, count).describe()
''', modern='''class ${N}Base:
    def __init__(self, name):
        self.name = name

    def describe(self):
        return "base:" + self.name


class ${N}Entry(${N}Base):
    def __init__(self, name, count):
        super().__init__(name)
        self.count = count

    def describe(self):
        return super().describe() + f":{self.count}"


def ${n}_entry_text(name, count):
    return ${N}Entry(name, count).describe()
''', calls=lambda r: [["${n}_entry_text", [r.choice(["a", "bee"]), r.randrange(0, 30)]] for _ in range(3)],
        check="class", bullet="`class X(object)` and `super(X, self)` use the modern spelling"),
    "len_zero": dict(
        legacy='''def ${n}_state(items):
    if len(items) == 0:
        return "empty"
    if len(items) > 0 and len(items) < 3:
        return "few"
    return "many"
''', modern='''def ${n}_state(items):
    if not items:
        return "empty"
    if len(items) < 3:
        return "few"
    return "many"
''', calls=lambda r: [["${n}_state", [[0] * k]] for k in (0, 1, 2, 3, 7)],
        check="len_zero", bullet="emptiness is tested by truthiness, not by comparing `len()` with zero"),
}

CHECKS = {
    "fstring": '''
    def test_fstring(self):
        bad = []
        for n in ast.walk(self.tree):
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod) and isinstance(n.left, (ast.Constant, ast.JoinedStr)) \\
                    and isinstance(getattr(n.left, "value", ""), str):
                bad.append("line %d: %% formatting" % n.lineno)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "format" and isinstance(n.func.value, ast.Constant):
                bad.append("line %d: str.format" % n.lineno)
        self.assertFalse(bad, S.format_problems(bad))
''',
    "with_open": '''
    def test_with_open(self):
        bad = []
        in_with = set()
        for n in ast.walk(self.tree):
            if isinstance(n, ast.With):
                for item in n.items:
                    for sub in ast.walk(item.context_expr):
                        in_with.add(id(sub))
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open" and id(n) not in in_with:
                bad.append("line %d: open() outside a with statement" % n.lineno)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "close":
                bad.append("line %d: explicit close()" % n.lineno)
        self.assertFalse(bad, S.format_problems(bad))
''',
    "pathlib": '''
    def test_pathlib(self):
        bad = []
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "os" and n.attr == "path":
                bad.append("line %d: os.path" % n.lineno)
            if isinstance(n, ast.ImportFrom) and n.module == "os.path":
                bad.append("line %d: from os.path import" % n.lineno)
        self.assertFalse(bad, S.format_problems(bad))
''',
    "comprehension": '''
    def test_comprehension(self):
        bad = []
        for n in ast.walk(self.tree):
            if isinstance(n, ast.For) and len(n.body) == 1 and not n.orelse:
                st = n.body[0]
                if isinstance(st, ast.If) and len(st.body) == 1 and not st.orelse:
                    st = st.body[0]
                if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) and isinstance(st.value.func, ast.Attribute) and st.value.func.attr == "append":
                    bad.append("line %d: loop that only appends" % n.lineno)
        self.assertFalse(bad, S.format_problems(bad))
''',
    "keys": '''
    def test_keys(self):
        bad = []
        def is_keys(x):
            return isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == "keys"
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Compare) and any(isinstance(o, (ast.In, ast.NotIn)) for o in n.ops) and any(is_keys(c) for c in n.comparators):
                bad.append("line %d: `in x.keys()`" % n.lineno)
            if isinstance(n, ast.For) and is_keys(n.iter):
                bad.append("line %d: loop over x.keys()" % n.lineno)
            if isinstance(n, ast.comprehension) and is_keys(n.iter):
                bad.append("line %d: comprehension over x.keys()" % n.iter.lineno)
        self.assertFalse(bad, S.format_problems(bad))
''',
    "isinstance": '''
    def test_isinstance(self):
        bad = []
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Compare) and isinstance(n.left, ast.Call) and isinstance(n.left.func, ast.Name) and n.left.func.id == "type":
                bad.append("line %d: type(x) comparison" % n.lineno)
        self.assertFalse(bad, S.format_problems(bad))
''',
    "range_len": '''
    def test_range_len(self):
        bad = []
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "range" and n.args \\
                    and any(isinstance(a, ast.Call) and isinstance(a.func, ast.Name) and a.func.id == "len" for a in n.args):
                bad.append("line %d: range(len(...))" % n.lineno)
        self.assertFalse(bad, S.format_problems(bad))
''',
    "none_is": '''
    def test_none_is(self):
        bad = []
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Compare) and any(isinstance(o, (ast.Eq, ast.NotEq)) for o in n.ops) \\
                    and any(isinstance(c, ast.Constant) and c.value is None for c in [n.left] + n.comparators):
                bad.append("line %d: == None" % n.lineno)
        self.assertFalse(bad, S.format_problems(bad))
''',
    "lambda": '''
    def test_lambda(self):
        bad = []
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Lambda) and all(isinstance(t, ast.Name) for t in n.targets):
                bad.append("line %d: lambda assigned to a name" % n.lineno)
        self.assertFalse(bad, S.format_problems(bad))
''',
    "except": '''
    def test_except(self):
        bad = ["line %d: bare except" % n.lineno for n in ast.walk(self.tree) if isinstance(n, ast.ExceptHandler) and n.type is None]
        self.assertFalse(bad, S.format_problems(bad))
''',
    "class": '''
    def test_class(self):
        bad = []
        for n in ast.walk(self.tree):
            if isinstance(n, ast.ClassDef) and any(isinstance(b, ast.Name) and b.id == "object" for b in n.bases):
                bad.append("line %d: class(object)" % n.lineno)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "super" and n.args:
                bad.append("line %d: super(...) with arguments" % n.lineno)
        self.assertFalse(bad, S.format_problems(bad))
''',
    "len_zero": '''
    def test_len_zero(self):
        bad = []
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Compare) and isinstance(n.left, ast.Call) and isinstance(n.left.func, ast.Name) and n.left.func.id == "len" \\
                    and any(isinstance(c, ast.Constant) and c.value == 0 for c in n.comparators):
                bad.append("line %d: len(x) compared with 0" % n.lineno)
        self.assertFalse(bad, S.format_problems(bad))
''',
}

HARNESS = '''
import importlib, os, tempfile
MOD = "$pkg.$mod"
FILES = $files

def run_case(case):
    mod = importlib.import_module(MOD)
    with tempfile.TemporaryDirectory() as tmp:
        for name, text in FILES.items():
            with open(os.path.join(tmp, name), "w") as fh:
                fh.write(text)
        args = [a.replace("@tmp", tmp) if isinstance(a, str) else a for a in case[1]]
        res = getattr(mod, case[0])(*args)
        if case[0].startswith("append_"):
            with open(args[0]) as fh:
                res = fh.read()
        return res
'''

PROMPTS = [
    "`{path}` was written in the style of a decade ago and the linter backlog for it is long. Bring it up to date without changing what any function does. "
    "Specifically:\n{bullets}\nThe module's public function and class names stay the same.",
    "Modernise `{path}`. I don't want a rewrite, only the idioms replaced, so behaviour (including error cases and exact output strings) must stay identical:\n{bullets}",
    "Please clean up `{path}` ({topic}). Things to change:\n{bullets}\nSame names, same results.",
    "Our {topic} helpers in `{path}` still look like python 2 era code. Update them: \n{bullets}\nNothing else should change; the existing tests must keep passing.",
]


def _filter(calls, noun):
    return [[c[0].replace("${n}", noun), c[1]] for c in calls]


@family("refactor-py-modernise", category="refactor", lang="python", kind="refactor", n=10,
        summary="replace legacy python idioms (percent formatting, open/close, os.path, index loops, bare except, ...) while behaviour is unchanged")
def gen(rng, n):
    for i in range(n):
        noun, place = NOUNS[i % len(NOUNS)] if i < len(NOUNS) else rng.choice(NOUNS)
        k = rng.choice([4, 5, 6, 7, 8, 9]) if i % 3 else rng.choice([3, 4])
        keys = rng.sample(list(IDIOMS), k)
        keys.sort(key=list(IDIOMS).index)
        if "percent" in keys and "format" in keys and rng.random() < 0.5:
            keys.remove("format")
        pkg, mod = f"{noun}tools", "helpers"
        path = f"{pkg}/{mod}.py"
        N = noun.capitalize()
        imports_l = sorted({IDIOMS[x].get("imports_legacy", "") for x in keys} - {""})
        imports_m = sorted({IDIOMS[x].get("imports_modern", "") for x in keys} - {""})

        def build(kind, imports):
            blocks = [Template(IDIOMS[x][kind]).safe_substitute(n=noun, N=N) for x in keys]
            head = f'"""Small helpers for the {place}."""\n' + ("\n".join(imports) + "\n" if imports else "")
            return head + "\n\n" + "\n\n".join(b.rstrip("\n") + "\n" for b in blocks)
        legacy, modern = build("legacy", imports_l), build("modern", imports_m)
        files_needed = "with_open" in keys
        calls = []
        for x in keys:
            spec = IDIOMS[x]
            if spec.get("calls"):
                calls += _filter(spec["calls"](rng), noun)
        file_text = {"notes.txt": "first note\n\n  second note  \nthird\n", "empty.txt": ""}
        if files_needed:
            calls += [[f"read_{noun}_notes", ["@tmp/notes.txt"]], [f"read_{noun}_notes", ["@tmp/empty.txt"]], [f"read_{noun}_notes", ["@tmp/missing.txt"]],
                      [f"append_{noun}_note", ["@tmp/new.txt", "hello"]], [f"append_{noun}_note", ["@tmp/notes.txt", "fourth"]]]
        files = {path: legacy, f"{pkg}/__init__.py": ""}
        harness = Template(HARNESS).substitute(pkg=pkg, mod=mod, files=repr(file_text))
        beh = py_behaviour(files, harness, calls, "recorded")
        want = _kit.py_golden(files, harness, calls)
        pick = [j for j, w in enumerate(want) if not (isinstance(w, dict) and "raises" in w)]
        pick = pick[:: max(1, len(pick) // 4)][:4]
        vis = ["import json", "import unittest", "", harness.strip("\n"), "", "def norm(x):", "    return json.loads(json.dumps(x))", "", "",
               "class HelperTests(unittest.TestCase):"]
        for t, j in enumerate(pick):
            vis += [f"    def test_example_{t + 1}(self):", f"        case = json.loads({json.dumps(json.dumps(calls[j]))})",
                    f"        self.assertEqual(norm(run_case(case)), json.loads({json.dumps(json.dumps(want[j]))}))", ""]
        vis += ["", "if __name__ == '__main__':", "    unittest.main()", ""]
        start = {**files, f"tests/test_{mod}.py": "\n".join(vis)}
        checks = "".join(CHECKS[IDIOMS[x]["check"]] for x in dict.fromkeys(IDIOMS[x]["check"] for x in keys) and
                         [x for x in keys if IDIOMS[x]["check"] not in [IDIOMS[y]["check"] for y in keys[: keys.index(x)]]])
        struct = ("import ast\nimport unittest\n\nimport structlib as S\n\nPATH = " + json.dumps(path) + "\n\n\nclass StructureTests(unittest.TestCase):\n"
                  "    def setUp(self):\n        self.tree = S.parse(PATH)\n" + checks)
        hidden = {"tests/test_more_behaviour.py": beh, "tests/test_zz_structure.py": struct, **py_structlib()}
        solution = {path: modern}
        prove(f"{noun}", start, hidden, solution, _kit.PY_BEHAVIOUR_CMD, _kit.PY_STRUCT_CMD, "python3 -m unittest discover -s tests")
        seen, bullets = set(), []
        for x in keys:
            b = IDIOMS[x]["bullet"]
            if b not in seen:
                seen.add(b)
                bullets.append("- " + b)
        d = 1 if len(set(IDIOMS[x]["check"] for x in keys)) <= 3 else 2 if len(keys) <= 5 else 3 if len(keys) <= 7 else 4
        prompt = rng.choice(PROMPTS).format(path=path, bullets="\n".join(bullets), topic=place)
        yield Task(slug=f"{i + 1:02d}-{noun}-{len(keys)}idioms", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution,
                   verify="python3 -m unittest discover -s tests -v", tags=["modernise", "idioms", "pathlib", "f-strings"], notes={"idioms": keys})
