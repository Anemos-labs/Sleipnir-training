"""Render a ``_ir.Project`` into a real repository in python, javascript, go, java, rust or ruby.

``render(proj, rng)`` returns a ``Rendered``: the files plus the facts a question needs that depend on the text
(where each function is defined, on which line each call sits, how each module is imported, the test names).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from ._ir import Fn, Mod, Project, VARS, PARAMS


def snake(n: str) -> str:
    return n


def camel(n: str) -> str:
    p = n.split("_")
    return p[0] + "".join(x[:1].upper() + x[1:] for x in p[1:])


def pascal(n: str) -> str:
    return "".join(x[:1].upper() + x[1:] for x in n.split("_"))


def cap1(n: str) -> str:
    return n[:1].upper() + n[1:]


@dataclass
class Rendered:
    files: dict = field(default_factory=dict)
    path: dict = field(default_factory=dict)         # module key -> source path
    main_path: str = ""
    fn_line: dict = field(default_factory=dict)      # fid -> (path, line)
    sites: list = field(default_factory=list)        # (caller fid, callee fid, path, line)
    ident: dict = field(default_factory=dict)        # fid -> identifier in the language
    style: dict = field(default_factory=dict)        # (module, callee module) -> import style
    tests: dict = field(default_factory=dict)        # case name -> (path, line, test identifier)
    test_paths: list = field(default_factory=list)
    mod_ident: dict = field(default_factory=dict)    # module key -> class/module/package identifier


class Buf:
    def __init__(self, unit: str):
        self.unit = unit
        self.lines: list = []
        self.marks: list = []   # (line index 0-based, caller fid, callee fid)
        self.level = 0
        self.cur: str = ""

    def line(self, text: str = "", calls=()):
        if text == "":
            self.lines.append("")
        else:
            self.lines.append(self.unit * self.level + text)
        for c in calls:
            self.marks.append((len(self.lines) - 1, self.cur, c))

    def blank(self):
        if self.lines and self.lines[-1] != "":
            self.lines.append("")

    def gap(self, n: int):
        while self.lines and self.lines[-1] == "":
            self.lines.pop()
        if self.lines:
            self.lines.extend([""] * n)

    def indent(self, n=1):
        self.level += n

    def dedent(self, n=1):
        self.level -= n


PREC = {"+": 1, "*": 2, "//": 2, "%": 2}


class Base:
    LANG = ""
    EXT = ""
    UNIT = "    "
    AND = "&&"
    OR = "||"

    def __init__(self, proj: Project, rng: random.Random):
        self.p = proj
        self.rng = rng
        self.r = Rendered()
        self.mods = proj.mods
        self.cur_mod: Mod | None = None
        self.vars_assigned: set = set()
        self.alias_map: dict = {}

    # ------------------------------------------------------------------ naming
    def ident(self, fn: Fn) -> str:
        return fn.name

    def const_name(self, name: str, m: Mod | None = None) -> str:
        return name

    def module_ident(self, m: Mod) -> str:
        return m.base

    # ------------------------------------------------------------------ expressions
    def callhead(self, m: Mod, fid: str) -> str:
        raise NotImplementedError

    def minmax(self, o: str, a: str, b: str) -> str:
        return f"{o}({a}, {b})"

    def sub(self, a: str, b: str) -> str:
        return f"max({a} - {b}, 0)"

    def fdiv(self, a: str, b: str, ea, eb) -> str:
        return f"{a} // {b}"

    def num(self, v: int) -> str:
        return str(v)

    def e(self, ex, m: Mod, calls: list, pp: int = 0, right: bool = False, pop: str = "") -> str:
        t = ex[0]
        if t == "n":
            return self.num(ex[1])
        if t == "v":
            return ex[1]
        if t == "k":
            return self.const_ref(m, ex[1])
        if t == "call":
            calls.append(ex[1])
            args = ", ".join(self.e(a, m, calls) for a in ex[2])
            return f"{self.callhead(m, ex[1])}({args})"
        o = ex[1]
        if o in ("min", "max"):
            return self.minmax(o, self.e(ex[2], m, calls), self.e(ex[3], m, calls))
        if o == "sub":
            return self.sub(self.e(ex[2], m, calls), self.e(ex[3], m, calls))
        if o == "//" and self.LANG == "javascript":
            a = self.e(ex[2], m, calls, 2)
            b = self.e(ex[3], m, calls, 2, True, "//")
            return f"Math.floor({a} / {b})"
        pr = PREC[o]
        a = self.e(ex[2], m, calls, pr, False, o)
        b = self.e(ex[3], m, calls, pr, True, o)
        sym = "/" if (o == "//" and self.LANG != "python") else o
        s = f"{a} {sym} {b}"
        need = pr < pp or (pr == pp and right and (o in ("//", "%") or pop in ("//", "%")))
        if pr == pp and not right and False:
            need = False
        return f"({s})" if need else s

    def const_ref(self, m: Mod, name: str) -> str:
        return self.const_name(name, m)

    def cond(self, c, m: Mod, calls: list, top: bool = True) -> str:
        t = c[0]
        if t == "cmp":
            return f"{self.e(c[2], m, calls)} {c[1]} {self.e(c[3], m, calls)}"
        op = self.AND if t == "and" else self.OR
        s = f"{self.cond(c[1], m, calls, False)} {op} {self.cond(c[2], m, calls, False)}"
        return s if top else f"({s})"

    def tpl_parts(self, tpl: str) -> list:
        return tpl.split("{}")

    # ------------------------------------------------------------------ file assembly helpers
    def add_file(self, path: str, text: str):
        self.r.files[path] = text if text.endswith("\n") else text + "\n"

    def finish_buf(self, path: str, buf: Buf, header_lines: int = 0, fn_marks: dict | None = None):
        for idx, caller, callee in buf.marks:
            self.r.sites.append((caller, callee, path, idx + 1))

    def fns_of(self, m: Mod) -> list:
        return [self.p.fns[f] for f in m.fids if self.p.fns[f].kind == "fn"]

    def choose_style(self, m: Mod, used: dict) -> dict:
        """import style for every module m depends on; resolves name clashes by forcing qualified use"""
        rng = self.rng
        defined = {self.ident(f) for f in self.fns_of(m)}
        locals_ = set(PARAMS) | set(VARS) | {p for f in self.fns_of(m) for p in f.params}
        out = {}
        seen_names: dict = {}
        for ck in used:
            cm = self.mods[ck]
            names = [self.sym_ident(x) for x in used[ck]]
            style = self.pick_style(m, cm)
            if style in self.NAME_STYLES and any(n in defined or n in seen_names for n in names):
                style = self.QUAL_STYLE
            if style in self.QUAL_STYLES:
                al = self.module_alias(cm)
                if al in locals_ or al in defined:
                    self.alias_map[(m.key, ck)] = al + self.ALIAS_SUFFIX
                    if self.LANG == "python":
                        style = "as"
            if style in self.NAME_STYLES:
                for n in names:
                    seen_names[n] = ck
            out[ck] = style
            self.r.style[(m.key, ck)] = style
        return out

    ALIAS_SUFFIX = "_mod"

    def module_alias(self, cm: Mod) -> str:
        return cm.base

    def alias_of(self, m: Mod, ck: str) -> str:
        return self.alias_map.get((m.key, ck), self.module_alias(self.mods[ck]))

    def sym_ident(self, s: str) -> str:
        if s in self.p.fns:
            return self.ident(self.p.fns[s])
        return s

    NAME_STYLES: tuple = ()
    QUAL_STYLES: tuple = ()
    QUAL_STYLE = ""
    ALIAS_STYLE = ""

    def pick_style(self, m: Mod, cm: Mod) -> str:
        raise NotImplementedError

    # ------------------------------------------------------------------ driver
    def render(self) -> Rendered:
        raise NotImplementedError

    def readme(self, layout: list, run_cmd: str, test_cmd: str) -> str:
        p = self.p
        out = [f"# {p.title}", "", f"{p.title} {p.blurb}.", "", "## Layout", ""]
        out += [f"- `{a}`: {b}" for a, b in layout]
        out += ["", "## Running", "", "```", run_cmd, "```", "", "Prints a few progress lines and then the day total.", "",
                "## Tests", "", "```", test_cmd, "```", ""]
        return "\n".join(out)

    def layout_notes(self) -> list:
        notes = []
        for m in sorted(self.mods.values(), key=lambda m: m.rank):
            if m.key in self.r.path:
                what = {"util": "small numeric helpers", "core": "rules and rates", "svc": "workflows built on the rules", "cli": "command line entry point",
                        "errors": "exception types"}[m.layer]
                notes.append((self.r.path[m.key], what))
        return notes

    def test_name_for(self, c) -> str:
        return "test_" + c.name


# ====================================================================================================================
# python
# ====================================================================================================================
class PyR(Base):
    LANG, EXT, UNIT = "python", ".py", "    "
    AND, OR = "and", "or"
    NAME_STYLES = ("abs", "rel")
    QUAL_STYLES = ("from", "as")
    QUAL_STYLE = "from"
    ALIAS_STYLE = ""

    def ident(self, fn):
        return fn.name if fn.public else "_" + fn.name

    def modpath(self, m: Mod) -> str:
        return f"{self.p.name}/{m.pkg + '/' if m.pkg else ''}{m.base}.py"

    def dotted(self, m: Mod) -> str:
        return ".".join([self.p.name] + ([m.pkg] if m.pkg else []) + [m.base])

    def pick_style(self, m, cm):
        return self.rng.choices(["abs", "rel", "from", "as"], [40, 18, 27, 15])[0]

    def callhead(self, m, fid):
        f = self.p.fns[fid]
        if f.mod == m.key:
            return self.ident(f)
        st = self.styles[f.mod]
        if st in self.NAME_STYLES:
            return self.ident(f)
        return f"{self.alias_of(m, f.mod)}.{self.ident(f)}"

    def excname(self, m, name):
        em = self.p.exc_mod()
        st = self.styles.get(em)
        if st in self.QUAL_STYLES:
            return f"{self.alias_of(m, em)}.{name}"
        return name

    def imports_for(self, m: Mod, used: dict, buf: Buf):
        std = []
        local = []
        for ck, syms in used.items():
            cm = self.mods[ck]
            st = self.styles[ck]
            names = sorted({self.sym_ident(s) for s in syms})
            if st == "abs":
                local.append(f"from {self.dotted(cm)} import {', '.join(names)}")
            elif st == "rel":
                up = 1 if not m.pkg else 2
                if m.pkg and m.pkg == cm.pkg:
                    pre = "."
                elif not m.pkg:
                    pre = "."
                else:
                    pre = ".."
                mid = ".".join(([cm.pkg] if cm.pkg and cm.pkg != m.pkg else []) + [cm.base])
                local.append(f"from {pre}{mid} import {', '.join(names)}")
            elif st == "from":
                parent = ".".join([self.p.name] + ([cm.pkg] if cm.pkg else []))
                local.append(f"from {parent} import {cm.base}")
            else:
                local.append(f"import {self.dotted(cm)} as {self.alias_of(m, ck)}")
        for dk in m.decoys:
            dm = self.mods[dk]
            if dk in used:
                continue
            ex = self.p.exports(dk)
            parent = ".".join([self.p.name] + ([dm.pkg] if dm.pkg else []))
            if ex and self.rng.random() < 0.5:
                local.append(f"from {self.dotted(dm)} import {self.ident(self.p.fns[ex[0]])}  # noqa: F401")
            else:
                local.append(f"from {parent} import {dm.base}  # noqa: F401")
        return std, local

    def render(self):
        p, rng = self.p, self.rng
        root = p.name
        self.styles: dict = {}
        self.add_file(f"{root}/__init__.py", f'"""{p.title}: {p.blurb}."""\n')
        for pkg in sorted({m.pkg for m in self.mods.values() if m.pkg}):
            self.add_file(f"{root}/{pkg}/__init__.py", f'"""{cap1(pkg)} modules of {p.title}."""\n')
        for m in sorted(self.mods.values(), key=lambda m: m.rank):
            self.render_module(m)
        self.render_tests()
        self.add_file(f"{root}/__main__.py", f"from .cli import main\n\nraise SystemExit(main())\n")
        self.r.main_path = self.r.path["cli"]
        self.add_file("README.md", self.readme(self.layout_notes() + [(f"{root}/__main__.py", "so that `python3 -m " + root + "` works"), ("tests/", "unit tests")],
                                              f"python3 -m {root} 5 3", "python3 -m unittest discover -s tests -v"))
        self.add_file(".gitignore", "__pycache__/\n*.pyc\n")
        return self.r

    def body(self, fn: Fn, m: Mod, buf: Buf):
        buf.cur = fn.fid
        self.vars_assigned = set()
        hdr = f"def {self.ident(fn)}({', '.join(fn.params)}):"
        buf.line(hdr)
        buf.indent()
        buf.line(f'"""{fn.doc}"""')
        for lm in m.lazy:
            if any(self.p.fns[c].mod == lm for c in self.p.callees(fn.fid)):
                cm = self.mods[lm]
                names = sorted({self.ident(self.p.fns[c]) for c in self.p.callees(fn.fid) if self.p.fns[c].mod == lm})
                buf.line(f"from {self.dotted(cm)} import {', '.join(names)}")
        for s in fn.body:
            self.st(s, m, buf)
        buf.dedent()

    def lazy_call_ok(self, m, fid):
        return True

    def st(self, s, m, buf):
        t = s[0]
        calls: list = []
        if t in ("let", "set"):
            buf.line(f"{s[1]} = {self.e(s[2], m, calls)}", calls)
        elif t == "do":
            buf.line(self.e(s[1], m, calls), calls)
        elif t == "ret":
            buf.line(f"return {self.e(s[1], m, calls)}", calls)
        elif t == "if":
            buf.line(f"if {self.cond(s[1], m, calls)}:", calls)
            self.block(s[2], m, buf)
            if s[3]:
                buf.line("else:")
                self.block(s[3], m, buf)
        elif t == "for":
            buf.line(f"for {s[1]} in range({self.e(s[2], m, calls)}, {self.e(s[3], m, calls)}):", calls)
            self.block(s[4], m, buf)
        elif t == "emit":
            buf.line(f'print(f"{self.fstr(s[1], s[2], m, calls)}")', calls)
        elif t == "raise":
            buf.line(f'raise {self.excname(m, s[1])}(f"{self.fstr(s[2], s[3], m, calls)}")', calls)
        elif t == "try":
            buf.line("try:")
            self.block(s[1], m, buf)
            for exc, h in s[2]:
                buf.line(f"except {self.excname(m, exc)}:")
                self.block(h, m, buf)
            if s[3]:
                buf.line("finally:")
                self.block(s[3], m, buf)
        else:
            raise ValueError(t)

    def block(self, body, m, buf):
        buf.indent()
        if not body:
            buf.line("pass")
        for s in body:
            self.st(s, m, buf)
        buf.dedent()

    def fstr(self, tpl, args, m, calls):
        parts = self.tpl_parts(tpl)
        out = parts[0]
        for a, ptxt in zip(args, parts[1:]):
            out += "{" + self.e(a, m, calls) + "}" + ptxt
        return out

    def render_module(self, m: Mod):
        p = self.p
        buf = Buf(self.UNIT)
        path = self.modpath(m)
        self.r.path[m.key] = path
        self.cur_mod = m
        if m.layer == "errors":
            buf.line(f'"""Exception types for {p.title}."""')
            for name, base in p.excs:
                buf.gap(2)
                buf.line(f"class {name}({base or 'Exception'}):")
                buf.indent()
                buf.line(f'"""{"Base class for all errors raised by " + p.title if not base else name[:-5] + " problems"}."""')
                buf.dedent()
            self.styles = {}
            self.add_file(path, "\n".join(buf.lines).rstrip("\n") + "\n")
            return
        used = p.used_imports(m.key)
        self.styles = self.choose_style(m, used)
        # lazy modules (cycle breakers) are imported inside the function instead of at the top
        top_used = {k: v for k, v in used.items() if k not in m.lazy}
        for k in m.lazy:
            self.styles[k] = "abs"
            self.r.style[(m.key, k)] = "lazy"
        _, local = self.imports_for(m, top_used, buf)
        buf.line(f'"""{m.doc}"""')
        if m.layer == "cli":
            buf.blank()
            buf.line("import sys")
        buf.blank()
        for ln in sorted(set(local), key=lambda s: (s.startswith("import "), s)):
            buf.line(ln)
        if m.layer != "cli" and m.all_list:
            buf.blank()
            names = [self.ident(p.fns[f]) for f in m.all_names]
            buf.line("__all__ = [")
            buf.indent()
            for n in names:
                buf.line(f'"{n}",')
            buf.dedent()
            buf.line("]")
        if m.consts:
            buf.blank()
            for k, v in m.consts:
                buf.line(f"{k} = {v}")
        for fid in m.fids:
            fn = p.fns[fid]
            if fn.kind == "main":
                continue
            buf.gap(2)
            start = len(buf.lines)
            self.body(fn, m, buf)
            self.r.fn_line[fid] = (path, start + 1)
            self.r.ident[fid] = self.ident(fn)
        if m.layer == "cli":
            fn = p.fns["cli.main"]
            buf.gap(2)
            self.r.fn_line[fn.fid] = (path, len(buf.lines) + 1)
            self.r.ident[fn.fid] = "main"
            buf.cur = fn.fid
            buf.line("def main(argv=None):")
            buf.indent()
            buf.line('"""Command line entry point."""')
            buf.line("argv = sys.argv[1:] if argv is None else argv")
            buf.line("count, days = int(argv[0]), int(argv[1])")
            buf.line("print(run(count, days))", ["cli.run"])
            buf.line("return 0")
            buf.dedent()
        self.finish_buf(path, buf)
        self.add_file(path, "\n".join(buf.lines).rstrip("\n") + "\n")

    def render_tests(self):
        p = self.p
        by_mod: dict = {}
        for c in p.cases:
            by_mod.setdefault(p.fns[c.fid].mod, []).append(c)
        for mk, cases in by_mod.items():
            m = self.mods[mk]
            buf = Buf(self.UNIT)
            path = f"tests/test_{m.base}.py"
            used_exc = sorted({c.exc for c in cases if c.expect == "raises"})
            needs_io = any(c.lines for c in cases)
            head = ["import contextlib", "import io"] if needs_io else []
            head.append("import unittest")
            buf.line(f'"""Tests for {m.base}."""')
            buf.blank()
            for h in head:
                buf.line(h)
            buf.blank()
            style = self.rng.choice(["names", "module"])
            fns = sorted({c.fid for c in cases})
            if style == "names":
                names = sorted({self.ident(p.fns[f]) for f in fns})
                # tests import by name; a private name never appears here
                buf.line(f"from {self.dotted(m)} import {', '.join(names)}")
                ref = lambda f: self.ident(p.fns[f])  # noqa: E731
            else:
                parent = ".".join([p.name] + ([m.pkg] if m.pkg else []))
                buf.line(f"from {parent} import {m.base}")
                ref = lambda f: f"{m.base}.{self.ident(p.fns[f])}"  # noqa: E731
            if used_exc:
                em = self.mods[p.exc_mod()]
                buf.line(f"from {self.dotted(em)} import {', '.join(used_exc)}")
            buf.gap(2)
            buf.line(f"class {cap1(m.base)}Tests(unittest.TestCase):")
            buf.indent()
            for c in cases:
                buf.blank()
                tname = "test_" + c.name
                self.r.tests[c.name] = (path, len(buf.lines) + 1, tname)
                buf.line(f"def {tname}(self):")
                buf.indent()
                buf.cur = "test:" + c.name
                args = ", ".join(str(a) for a in c.args)
                call = f"{ref(c.fid)}({args})"
                if c.expect == "raises":
                    buf.line(f"with self.assertRaises({c.exc}):")
                    buf.line(f"    {call}", [c.fid])
                elif c.lines:
                    buf.line("buf = io.StringIO()")
                    buf.line("with contextlib.redirect_stdout(buf):")
                    buf.line(f"    result = {call}", [c.fid])
                    buf.line(f"self.assertEqual(result, {c.value})")
                    buf.line("self.assertEqual(buf.getvalue().splitlines(), [")
                    buf.indent()
                    for ln in c.lines:
                        buf.line(f'"{ln}",')
                    buf.dedent()
                    buf.line("])")
                else:
                    buf.line(f"self.assertEqual({call}, {c.value})", [c.fid])
                buf.dedent()
            buf.dedent()
            self.r.test_paths.append(path)
            self.finish_buf(path, buf)
            self.add_file(path, "\n".join(buf.lines).rstrip("\n") + "\n")
        # the report test lives with cli
        # (cases for cli.run are grouped under module "cli" above)


# ====================================================================================================================
# javascript (CommonJS, node:test)
# ====================================================================================================================
class JsR(Base):
    LANG, EXT, UNIT = "javascript", ".js", "  "
    NAME_STYLES = ("destr",)
    QUAL_STYLES = ("whole",)
    QUAL_STYLE = "whole"

    def ident(self, fn):
        return camel(fn.name)

    def const_name(self, name, m=None):
        return name

    def modpath(self, m):
        return f"src/{m.pkg + '/' if m.pkg else ''}{m.base}.js"

    def pick_style(self, m, cm):
        return self.rng.choices(["destr", "whole"], [60, 40])[0]

    def callhead(self, m, fid):
        f = self.p.fns[fid]
        if f.mod == m.key:
            return self.ident(f)
        if self.styles[f.mod] == "destr":
            return self.ident(f)
        return f"{self.alias_of(m, f.mod)}.{self.ident(f)}"

    ALIAS_SUFFIX_JS = "Mod"

    def alias(self, mk, m=None):
        return self.alias_of(m, mk) if m is not None else self.mods[mk].base

    def relpath(self, m, cm):
        a = m.pkg
        b = cm.pkg
        if a == b:
            pre = "./"
        elif not a:
            pre = "./"
        elif not b:
            pre = "../"
        else:
            pre = "../"
        mid = (b + "/" if b and a != b else "") + cm.base
        return pre + mid

    ALIAS_SUFFIX = "Mod"

    def excname(self, m, name):
        em = self.p.exc_mod()
        if self.styles.get(em) == "whole":
            return f"{self.alias_of(m, em)}.{name}"
        return name

    def render(self):
        p = self.p
        self.styles = {}
        for m in sorted(self.mods.values(), key=lambda m: m.rank):
            self.render_module(m)
        self.render_tests()
        self.add_file(f"bin/{p.name}.js", f"#!/usr/bin/env node\n'use strict';\n\nconst {{ main }} = require('../src/cli');\n\nprocess.exitCode = main(process.argv.slice(2));\n")
        self.add_file("package.json", f'{{\n  "name": "{p.name}",\n  "version": "0.3.0",\n  "description": "{p.title} {p.blurb}",\n  "bin": {{ "{p.name}": "bin/{p.name}.js" }},\n  "scripts": {{ "test": "node --test test/*.test.js" }},\n  "license": "MIT"\n}}\n')
        self.r.main_path = self.r.path["cli"]
        self.add_file("README.md", self.readme(self.layout_notes() + [(f"bin/{p.name}.js", "executable wrapper"), ("test/", "node:test suites")],
                                              f"node bin/{p.name}.js 5 3", "node --test test/*.test.js"))
        self.add_file(".gitignore", "node_modules/\n")
        return self.r

    def render_module(self, m):
        p = self.p
        buf = Buf(self.UNIT)
        path = self.modpath(m)
        self.r.path[m.key] = path
        buf.line("'use strict';")
        buf.blank()
        if m.layer == "errors":
            for name, base in p.excs:
                buf.line(f"class {name} extends {base or 'Error'} {{")
                buf.indent()
                buf.line("constructor(message) {")
                buf.indent()
                buf.line("super(message);")
                buf.line(f"this.name = '{name}';")
                buf.dedent()
                buf.line("}")
                buf.dedent()
                buf.line("}")
                buf.blank()
            buf.line("module.exports = { " + ", ".join(n for n, _ in p.excs) + " };")
            self.add_file(path, "\n".join(buf.lines))
            return
        used = p.used_imports(m.key)
        self.styles = self.choose_style(m, used)
        top_used = {k: v for k, v in used.items() if k not in m.lazy}
        for k in m.lazy:
            self.styles[k] = "destr"
            self.r.style[(m.key, k)] = "lazy"
        for ck, syms in top_used.items():
            cm = self.mods[ck]
            rp = self.relpath(m, cm)
            if self.styles[ck] == "destr":
                names = sorted({self.sym_ident(s) for s in syms})
                buf.line(f"const {{ {', '.join(names)} }} = require('{rp}');")
            else:
                buf.line(f"const {self.alias_of(m, ck)} = require('{rp}');")
        for dk in m.decoys:
            if dk in used:
                continue
            dm = self.mods[dk]
            buf.line(f"const {dm.base} = require('{self.relpath(m, dm)}'); // eslint-disable-line no-unused-vars")
        if buf.lines[-1] != "":
            buf.blank()
        if m.consts:
            for k, v in m.consts:
                buf.line(f"const {k} = {v};")
            buf.blank()
        for fid in m.fids:
            fn = p.fns[fid]
            if fn.kind == "main":
                continue
            start = len(buf.lines)
            self.fn(fn, m, buf)
            self.r.fn_line[fid] = (path, start + 2)
            self.r.ident[fid] = self.ident(fn)
            buf.blank()
        if m.layer == "cli":
            fn = p.fns["cli.main"]
            buf.cur = fn.fid
            self.r.fn_line[fn.fid] = (path, len(buf.lines) + 2)
            self.r.ident[fn.fid] = "main"
            buf.line("/** Command line entry point. */")
            buf.line("function main(argv) {")
            buf.indent()
            buf.line("const count = parseInt(argv[0], 10);")
            buf.line("const days = parseInt(argv[1], 10);")
            buf.line("console.log(String(run(count, days)));", ["cli.run"])
            buf.line("return 0;")
            buf.dedent()
            buf.line("}")
            buf.blank()
        exports = [self.ident(p.fns[f]) for f in m.fids if p.fns[f].public and p.fns[f].kind == "fn"]
        if m.layer == "cli":
            exports.append("main")
        buf.line("module.exports = {")
        buf.indent()
        for n in exports:
            buf.line(f"{n},")
        buf.dedent()
        buf.line("};")
        self.finish_buf(path, buf)
        self.add_file(path, "\n".join(buf.lines))

    def fn(self, fn, m, buf):
        buf.cur = fn.fid
        self.vars_assigned = set()
        buf.line(f"/** {fn.doc} */")
        buf.line(f"function {self.ident(fn)}({', '.join(fn.params)}) {{")
        buf.indent()
        for lm in m.lazy:
            callees = [c for c in self.p.callees(fn.fid) if self.p.fns[c].mod == lm]
            if callees:
                names = sorted({self.ident(self.p.fns[c]) for c in callees})
                buf.line(f"const {{ {', '.join(names)} }} = require('{self.relpath(m, self.mods[lm])}');")
        for s in fn.body:
            self.st(s, m, buf)
        buf.dedent()
        buf.line("}")

    def declare(self, v):
        return f"let {v} = "

    def st(self, s, m, buf):
        t = s[0]
        calls: list = []
        if t == "let":
            buf.line(f"let {s[1]} = {self.e(s[2], m, calls)};", calls)
        elif t == "set":
            buf.line(f"{s[1]} = {self.e(s[2], m, calls)};", calls)
        elif t == "do":
            buf.line(self.e(s[1], m, calls) + ";", calls)
        elif t == "ret":
            buf.line(f"return {self.e(s[1], m, calls)};", calls)
        elif t == "if":
            buf.line(f"if ({self.cond(s[1], m, calls)}) {{", calls)
            self.block(s[2], m, buf)
            if s[3]:
                buf.line("} else {")
                self.block(s[3], m, buf)
            buf.line("}")
        elif t == "for":
            buf.line(f"for (let {s[1]} = {self.e(s[2], m, calls)}; {s[1]} < {self.e(s[3], m, calls)}; {s[1]}++) {{", calls)
            self.block(s[4], m, buf)
            buf.line("}")
        elif t == "emit":
            buf.line(f"console.log(`{self.tstr(s[1], s[2], m, calls)}`);", calls)
        elif t == "raise":
            buf.line(f"throw new {self.excname(m, s[1])}(`{self.tstr(s[2], s[3], m, calls)}`);", calls)
        elif t == "try":
            buf.line("try {")
            self.block(s[1], m, buf)
            buf.line("} catch (err) {")
            buf.indent()
            first = True
            for exc, h in s[2]:
                buf.line(f"{'if' if first else '} else if'} (err instanceof {self.excname(m, exc)}) {{")
                self.block(h, m, buf)
                first = False
            buf.line("} else {")
            buf.indent()
            buf.line("throw err;")
            buf.dedent()
            buf.line("}")
            buf.dedent()
            if s[3]:
                buf.line("} finally {")
                self.block(s[3], m, buf)
            buf.line("}")
        else:
            raise ValueError(t)

    def block(self, body, m, buf):
        buf.indent()
        for s in body:
            self.st(s, m, buf)
        buf.dedent()

    def tstr(self, tpl, args, m, calls):
        parts = self.tpl_parts(tpl)
        out = parts[0]
        for a, ptxt in zip(args, parts[1:]):
            out += "${" + self.e(a, m, calls) + "}" + ptxt
        return out

    def minmax(self, o, a, b):
        return f"Math.{o}({a}, {b})"

    def sub(self, a, b):
        return f"Math.max({a} - {b}, 0)"

    def render_tests(self):
        p = self.p
        by_mod: dict = {}
        for c in p.cases:
            by_mod.setdefault(p.fns[c.fid].mod, []).append(c)
        for mk, cases in by_mod.items():
            m = self.mods[mk]
            buf = Buf(self.UNIT)
            path = f"test/{m.base}.test.js"
            buf.line("'use strict';")
            buf.blank()
            buf.line("const test = require('node:test');")
            buf.line("const assert = require('node:assert/strict');")
            rel = f"../src/{m.pkg + '/' if m.pkg else ''}{m.base}"
            names = sorted({self.ident(p.fns[c.fid]) for c in cases})
            buf.line(f"const {{ {', '.join(names)} }} = require('{rel}');")
            exc = sorted({c.exc for c in cases if c.expect == "raises"})
            if exc:
                em = self.mods[p.exc_mod()]
                buf.line(f"const {{ {', '.join(exc)} }} = require('../src/{em.pkg + '/' if em.pkg else ''}errors');")
            buf.blank()
            for c in cases:
                fnid = self.ident(p.fns[c.fid])
                tname = f"{fnid}: {c.name[len(p.fns[c.fid].name) + 1:].replace('_', ' ')}"
                self.r.tests[c.name] = (path, len(buf.lines) + 1, tname)
                args = ", ".join(str(a) for a in c.args)
                buf.cur = "test:" + c.name
                if c.expect == "raises":
                    buf.line(f"test('{tname}', () => {{")
                    buf.line(f"  assert.throws(() => {fnid}({args}), {c.exc});", [c.fid])
                else:
                    buf.line(f"test('{tname}', () => {{")
                    buf.line(f"  assert.equal({fnid}({args}), {c.value});", [c.fid])
                buf.line("});")
                buf.blank()
            self.r.test_paths.append(path)
            self.finish_buf(path, buf)
            self.add_file(path, "\n".join(buf.lines))


# ====================================================================================================================
# go
# ====================================================================================================================
class GoR(Base):
    LANG, EXT, UNIT = "go", ".go", "\t"

    def ident(self, fn):
        if fn.mod == "cli" and fn.name == "run":
            return "run"
        return pascal(fn.name) if fn.public else camel(fn.name)

    def const_name(self, name, m=None):
        if "_" in name:
            return camel(name.lower())
        return camel(f"{m.base}_{name.lower()}")

    def modpath(self, m):
        if m.layer == "cli":
            return f"cmd/{self.p.name}/main.go"
        return f"internal/{m.pkg + '/' if m.pkg else ''}{m.base}/{m.base}.go"

    def importpath(self, m):
        return f"example.com/{self.p.name}/internal/{m.pkg + '/' if m.pkg else ''}{m.base}"

    def pick_style(self, m, cm):
        return "pkg"

    def callhead(self, m, fid):
        f = self.p.fns[fid]
        if f.mod == m.key:
            return self.ident(f)
        return f"{self.aliases.get(f.mod, self.mods[f.mod].base)}.{self.ident(f)}"

    def minmax(self, o, a, b):
        return f"{o}({a}, {b})"

    def sub(self, a, b):
        return f"max({a}-{b}, 0)" if False else f"max({a} - {b}, 0)"

    def render(self):
        p = self.p
        self.aliases = {}
        self.add_file("go.mod", f"module example.com/{p.name}\n\ngo 1.21\n")
        for m in sorted(self.mods.values(), key=lambda m: m.rank):
            if m.layer == "errors":
                continue
            self.render_module(m)
        self.render_tests()
        self.r.main_path = self.r.path["cli"]
        notes = self.layout_notes()
        self.add_file("README.md", self.readme(notes + [("go.mod", "module definition"), ("*_test.go", "unit tests next to the code")],
                                              f"go run ./cmd/{p.name} 5 3", "go test ./..."))
        self.add_file(".gitignore", "")
        return self.r

    def render_module(self, m):
        p = self.p
        buf = Buf(self.UNIT)
        path = self.modpath(m)
        self.r.path[m.key] = path
        used = p.used_imports(m.key)
        local = {x for f in self.fns_of(m) for x in f.params} | set(VARS) | set(PARAMS)
        self.aliases = {}
        for ck in used:
            cb = self.mods[ck].base
            if cb in local:
                self.aliases[ck] = cb + "pkg"
            self.r.style[(m.key, ck)] = "pkg"
        pkgname = "main" if m.layer == "cli" else m.base
        buf.line(f"// Package {pkgname} {m.doc[0].lower() + m.doc[1:]}" if m.layer != "cli" else f"// Command {p.name} {p.blurb}.")
        buf.line(f"package {pkgname}")
        buf.blank()
        imps = []
        if m.layer == "cli":
            imps += ['"fmt"', '"os"', '"strconv"']
        elif any(self.fn_emits(f) for f in self.fns_of(m)):
            imps += ['"fmt"']
        for ck in used:
            al = self.aliases.get(ck)
            imps.append((f"{al} " if al else "") + f'"{self.importpath(self.mods[ck])}"')
        if imps:
            std = [i for i in imps if "." not in i.split('"')[1].split("/")[0]]
            loc = [i for i in imps if i not in std]
            buf.line("import (")
            buf.indent()
            for i in sorted(std):
                buf.line(i)
            if std and loc:
                buf.line("")
            for i in sorted(loc, key=lambda s: s.split('"')[1]):
                buf.line(i)
            buf.dedent()
            buf.line(")")
            buf.blank()
        if m.consts:
            buf.line("const (")
            buf.indent()
            for k, v in m.consts:
                buf.line(f"{self.const_name(k, m)} = {v}")
            buf.dedent()
            buf.line(")")
            buf.blank()
        for fid in m.fids:
            fn = p.fns[fid]
            if fn.kind == "main":
                continue
            start = len(buf.lines)
            self.fn(fn, m, buf)
            self.r.fn_line[fid] = (path, start + 2)
            self.r.ident[fid] = self.ident(fn)
            buf.blank()
        if m.layer == "cli":
            fn = p.fns["cli.main"]
            buf.cur = fn.fid
            self.r.fn_line[fn.fid] = (path, len(buf.lines) + 2)
            self.r.ident[fn.fid] = "main"
            buf.line("// main reads the batch size and day count from the command line.")
            buf.line("func main() {")
            buf.indent()
            buf.line("count, _ := strconv.Atoi(os.Args[1])")
            buf.line("days, _ := strconv.Atoi(os.Args[2])")
            buf.line("fmt.Println(run(count, days))", ["cli.run"])
            buf.dedent()
            buf.line("}")
        text = "\n".join(buf.lines).rstrip("\n") + "\n"
        self.finish_buf(path, buf)
        self.add_file(path, text)

    def fn_emits(self, fn):
        return any(st[0] == "emit" for st in self._flat(fn.body))

    def _flat(self, body):
        for s in body:
            yield s
            if s[0] == "if":
                yield from self._flat(s[2])
                yield from self._flat(s[3])
            elif s[0] == "for":
                yield from self._flat(s[4])

    def fn(self, fn, m, buf):
        buf.cur = fn.fid
        self.vars_assigned = set()
        nm = self.ident(fn)
        buf.line(f"// {nm} {fn.doc[0].lower() + fn.doc[1:]}")
        ps = ", ".join(f"{x} int" for x in fn.params)
        buf.line(f"func {nm}({ps}) int {{")
        buf.indent()
        for s in fn.body:
            self.st(s, m, buf)
        buf.dedent()
        buf.line("}")

    def st(self, s, m, buf):
        t = s[0]
        calls: list = []
        if t == "let":
            buf.line(f"{s[1]} := {self.e(s[2], m, calls)}", calls)
        elif t == "set":
            buf.line(f"{s[1]} = {self.e(s[2], m, calls)}", calls)
        elif t == "do":
            buf.line(self.e(s[1], m, calls), calls)
        elif t == "ret":
            buf.line(f"return {self.e(s[1], m, calls)}", calls)
        elif t == "if":
            buf.line(f"if {self.cond(s[1], m, calls)} {{", calls)
            self.block(s[2], m, buf)
            if s[3]:
                buf.line("} else {")
                self.block(s[3], m, buf)
            buf.line("}")
        elif t == "for":
            buf.line(f"for {s[1]} := {self.e(s[2], m, calls)}; {s[1]} < {self.e(s[3], m, calls)}; {s[1]}++ {{", calls)
            self.block(s[4], m, buf)
            buf.line("}")
        elif t == "emit":
            parts = self.tpl_parts(s[1])
            fmt = "%d".join(parts) + "\\n"
            args = ", ".join(self.e(a, m, calls) for a in s[2])
            buf.line(f'fmt.Printf("{fmt}", {args})', calls)
        else:
            raise ValueError(f"go cannot render {t}")

    def block(self, body, m, buf):
        buf.indent()
        for s in body:
            self.st(s, m, buf)
        buf.dedent()

    def render_tests(self):
        p = self.p
        by_mod: dict = {}
        for c in p.cases:
            by_mod.setdefault(p.fns[c.fid].mod, []).append(c)
        for mk, cases in by_mod.items():
            m = self.mods[mk]
            if m.layer == "cli":
                continue
            buf = Buf(self.UNIT)
            path = self.r.path[mk].replace(".go", "_test.go")
            buf.line(f"package {m.base}")
            buf.blank()
            buf.line('import "testing"')
            buf.blank()
            for c in cases:
                tname = "Test" + pascal(c.name)
                self.r.tests[c.name] = (path, len(buf.lines) + 1, tname)
                args = ", ".join(str(a) for a in c.args)
                fnid = self.ident(p.fns[c.fid])
                buf.line(f"func {tname}(t *testing.T) {{")
                buf.indent()
                buf.cur = "test:" + c.name
                buf.line(f"if got := {fnid}({args}); got != {c.value} {{", [c.fid])
                buf.line(f'\tt.Errorf("{fnid}({args}) = %d, want {c.value}", got)')
                buf.line("}")
                buf.dedent()
                buf.line("}")
                buf.blank()
            self.r.test_paths.append(path)
            self.finish_buf(path, buf)
            self.add_file(path, "\n".join(buf.lines).rstrip("\n") + "\n")


# ====================================================================================================================
# java
# ====================================================================================================================
class JavaR(Base):
    LANG, EXT, UNIT = "java", ".java", "    "
    NAME_STYLES = ("static",)
    QUAL_STYLES = ("class",)
    QUAL_STYLE = "class"

    def ident(self, fn):
        return camel(fn.name)

    def module_ident(self, m):
        return "Main" if m.layer == "cli" else cap1(m.base)

    def pkgname(self, m):
        return ".".join([self.p.name] + ([m.pkg] if m.pkg else []))

    def modpath(self, m):
        return f"src/{self.p.name}/{m.pkg + '/' if m.pkg else ''}{self.module_ident(m)}.java"

    def pick_style(self, m, cm):
        return self.rng.choices(["static", "class"], [35, 65])[0]

    def callhead(self, m, fid):
        f = self.p.fns[fid]
        if f.mod == m.key:
            return self.ident(f)
        if self.styles[f.mod] == "static":
            return self.ident(f)
        return f"{self.module_ident(self.mods[f.mod])}.{self.ident(f)}"

    def minmax(self, o, a, b):
        return f"Math.{o}({a}, {b})"

    def sub(self, a, b):
        return f"Math.max({a} - {b}, 0)"

    def render(self):
        p = self.p
        self.styles = {}
        for m in sorted(self.mods.values(), key=lambda m: m.rank):
            self.render_module(m)
        self.render_tests()
        self.r.main_path = self.r.path["cli"]
        self.add_file("README.md", self.readme(self.layout_notes() + [("tests/TestMain.java", "plain assertions, no framework")],
                                              f"javac -d build $(find . -name '*.java') && java -cp build {p.name}.Main 5 3",
                                              "javac -d build $(find . -name '*.java') && java -cp build TestMain"))
        self.add_file(".gitignore", "build/\n")
        return self.r

    def render_module(self, m):
        p = self.p
        buf = Buf(self.UNIT)
        if m.layer == "errors":
            for name, base in p.excs:
                b = Buf(self.UNIT)
                path = f"src/{p.name}/{m.pkg + '/' if m.pkg else ''}{name}.java"
                b.line(f"package {self.pkgname(m)};")
                b.blank()
                b.line(f"/** {name[:-5] + ' problems' if base else 'Base class for all errors raised by ' + p.title}. */")
                b.line(f"public class {name} extends {base or 'RuntimeException'} {{")
                b.indent()
                b.line(f"public {name}(String message) {{")
                b.indent()
                b.line("super(message);")
                b.dedent()
                b.line("}")
                b.dedent()
                b.line("}")
                self.add_file(path, "\n".join(b.lines))
                self.r.mod_ident[name] = name
            self.r.path[m.key] = f"src/{p.name}/{m.pkg + '/' if m.pkg else ''}{p.excs[0][0]}.java"
            return
        path = self.modpath(m)
        self.r.path[m.key] = path
        used = p.used_imports(m.key)
        self.styles = self.choose_style(m, used)
        top_used = {k: v for k, v in used.items() if k not in m.lazy}
        for k in m.lazy:
            self.styles[k] = "class"
            self.r.style[(m.key, k)] = "class"
        buf.line(f"package {self.pkgname(m)};")
        buf.blank()
        imps = []
        for ck, syms in used.items():
            cm = self.mods[ck]
            if cm.layer == "errors":
                for s in syms:
                    imps.append(f"import {self.pkgname(cm)}.{s};")
                continue
            if self.styles[ck] == "static":
                for s in sorted({self.sym_ident(x) for x in syms}):
                    imps.append(f"import static {self.pkgname(cm)}.{self.module_ident(cm)}.{s};")
            else:
                if cm.pkg != m.pkg or True:
                    imps.append(f"import {self.pkgname(cm)}.{self.module_ident(cm)};")
        for dk in m.decoys:
            if dk not in used:
                dm = self.mods[dk]
                imps.append(f"import {self.pkgname(dm)}.{self.module_ident(dm)};")
        # same-package classes need no import
        imps = sorted({i for i in imps if not self.same_pkg_import(i, m)})
        for i in imps:
            buf.line(i)
        if imps:
            buf.blank()
        buf.line(f"/** {m.doc} */")
        buf.line(f"public final class {self.module_ident(m)} {{")
        buf.indent()
        buf.line(f"private {self.module_ident(m)}() {{")
        buf.line("}")
        if m.consts:
            buf.blank()
            for k, v in m.consts:
                buf.line(f"private static final long {k} = {v};")
        for fid in m.fids:
            fn = p.fns[fid]
            if fn.kind == "main":
                continue
            buf.blank()
            start = len(buf.lines)
            self.fn(fn, m, buf)
            self.r.fn_line[fid] = (path, start + 2)
            self.r.ident[fid] = self.ident(fn)
        if m.layer == "cli":
            fn = p.fns["cli.main"]
            buf.blank()
            buf.cur = fn.fid
            self.r.fn_line[fn.fid] = (path, len(buf.lines) + 2)
            self.r.ident[fn.fid] = "main"
            buf.line("/** Command line entry point. */")
            buf.line("public static void main(String[] args) {")
            buf.indent()
            buf.line("long count = Long.parseLong(args[0]);")
            buf.line("long days = Long.parseLong(args[1]);")
            buf.line("System.out.println(run(count, days));", ["cli.run"])
            buf.dedent()
            buf.line("}")
        buf.dedent()
        buf.line("}")
        self.finish_buf(path, buf)
        self.add_file(path, "\n".join(buf.lines))

    def same_pkg_import(self, imp: str, m: Mod) -> bool:
        if imp.startswith("import static"):
            return False
        name = imp[len("import "):-1]
        pk = name.rsplit(".", 1)[0]
        return pk == self.pkgname(m)

    def fn(self, fn, m, buf):
        buf.cur = fn.fid
        vis = "public" if fn.public else "private"
        ps = ", ".join(f"long {x}" for x in fn.params)
        buf.line(f"/** {fn.doc} */")
        buf.line(f"{vis} static long {self.ident(fn)}({ps}) {{")
        buf.indent()
        for s in fn.body:
            self.st(s, m, buf)
        buf.dedent()
        buf.line("}")

    def excname(self, m, name):
        return name

    def st(self, s, m, buf):
        t = s[0]
        calls: list = []
        if t == "let":
            buf.line(f"long {s[1]} = {self.e(s[2], m, calls)};", calls)
        elif t == "set":
            buf.line(f"{s[1]} = {self.e(s[2], m, calls)};", calls)
        elif t == "do":
            buf.line(self.e(s[1], m, calls) + ";", calls)
        elif t == "ret":
            buf.line(f"return {self.e(s[1], m, calls)};", calls)
        elif t == "if":
            buf.line(f"if ({self.cond(s[1], m, calls)}) {{", calls)
            self.block(s[2], m, buf)
            if s[3]:
                buf.line("} else {")
                self.block(s[3], m, buf)
            buf.line("}")
        elif t == "for":
            buf.line(f"for (long {s[1]} = {self.e(s[2], m, calls)}; {s[1]} < {self.e(s[3], m, calls)}; {s[1]}++) {{", calls)
            self.block(s[4], m, buf)
            buf.line("}")
        elif t == "emit":
            buf.line(f"System.out.println({self.cat(s[1], s[2], m, calls)});", calls)
        elif t == "raise":
            buf.line(f"throw new {s[1]}({self.cat(s[2], s[3], m, calls)});", calls)
        elif t == "try":
            buf.line("try {")
            self.block(s[1], m, buf)
            for exc, h in s[2]:
                buf.line(f"}} catch ({exc} err) {{")
                self.block(h, m, buf)
            if s[3]:
                buf.line("} finally {")
                self.block(s[3], m, buf)
            buf.line("}")
        else:
            raise ValueError(t)

    def block(self, body, m, buf):
        buf.indent()
        for s in body:
            self.st(s, m, buf)
        buf.dedent()

    def cat(self, tpl, args, m, calls):
        parts = self.tpl_parts(tpl)
        out = ['""'] if not parts[0] else [f'"{parts[0]}"']
        for a, ptxt in zip(args, parts[1:]):
            out.append("(" + self.e(a, m, calls) + ")" if a[0] == "op" else self.e(a, m, calls))
            if ptxt:
                out.append(f'"{ptxt}"')
        if out[0] != '""' and not out[0].startswith('"'):
            out.insert(0, '""')
        return " + ".join(out)

    def render_tests(self):
        p = self.p
        buf = Buf(self.UNIT)
        path = "tests/TestMain.java"
        by_mod: dict = {}
        for c in p.cases:
            if p.fns[c.fid].mod == "cli":
                continue
            by_mod.setdefault(p.fns[c.fid].mod, []).append(c)
        imports = set()
        for mk in by_mod:
            m = self.mods[mk]
            imports.add(f"import {self.pkgname(m)}.{self.module_ident(m)};")
        exc = {c.exc for cs in by_mod.values() for c in cs if c.expect == "raises"}
        for e in exc:
            em = self.mods[p.exc_mod()]
            imports.add(f"import {self.pkgname(em)}.{e};")
        for i in sorted(imports):
            buf.line(i)
        buf.blank()
        buf.line("/** Plain-assert test runner; no framework needed. */")
        buf.line("public class TestMain {")
        buf.indent()
        buf.line("private static int failures = 0;")
        buf.blank()
        buf.line("private static void check(String name, long got, long want) {")
        buf.line("    if (got != want) {")
        buf.line('        System.out.println("FAIL " + name + ": got " + got + ", want " + want);')
        buf.line("        failures++;")
        buf.line("    }")
        buf.line("}")
        names = []
        for mk, cases in by_mod.items():
            m = self.mods[mk]
            for c in cases:
                buf.blank()
                tname = "test" + pascal(c.name)
                names.append(tname)
                self.r.tests[c.name] = (path, len(buf.lines) + 1, tname)
                args = ", ".join(str(a) for a in c.args)
                call = f"{self.module_ident(m)}.{self.ident(p.fns[c.fid])}({args})"
                buf.line(f"static void {tname}() {{")
                buf.indent()
                buf.cur = "test:" + c.name
                if c.expect == "raises":
                    buf.line("try {")
                    buf.line(f"    {call};", [c.fid])
                    buf.line(f'    System.out.println("FAIL {tname}: expected {c.exc}");')
                    buf.line("    failures++;")
                    buf.line(f"}} catch ({c.exc} expected) {{")
                    buf.line("    // ok")
                    buf.line("}")
                else:
                    buf.line(f'check("{tname}", {call}, {c.value});', [c.fid])
                buf.dedent()
                buf.line("}")
        buf.blank()
        buf.line("public static void main(String[] args) {")
        buf.indent()
        for n in names:
            buf.line(f"{n}();")
        buf.line("if (failures > 0) {")
        buf.line("    System.exit(1);")
        buf.line("}")
        buf.line(f'System.out.println("ok: {len(names)} tests");')
        buf.dedent()
        buf.line("}")
        buf.dedent()
        buf.line("}")
        self.r.test_paths.append(path)
        self.finish_buf(path, buf)
        self.add_file(path, "\n".join(buf.lines))


# ====================================================================================================================
# rust
# ====================================================================================================================
class RustR(Base):
    LANG, EXT, UNIT = "rust", ".rs", "    "
    NAME_STYLES = ("use",)
    QUAL_STYLES = ("mod",)
    QUAL_STYLE = "mod"

    def ident(self, fn):
        return fn.name

    def modpath(self, m):
        if m.layer == "cli":
            return "src/cli.rs"
        return f"src/{m.pkg + '/' if m.pkg else ''}{m.base}.rs"

    def pick_style(self, m, cm):
        return self.rng.choices(["use", "mod"], [60, 40])[0]

    def crate_path(self, m):
        return "crate::" + "::".join(([m.pkg] if m.pkg else []) + [m.base])

    def callhead(self, m, fid):
        f = self.p.fns[fid]
        if f.mod == m.key:
            return self.ident(f)
        if self.styles[f.mod] == "use":
            return self.ident(f)
        return f"{self.mods[f.mod].base}::{self.ident(f)}"

    def minmax(self, o, a, b):
        return f"std::cmp::{o}({a}, {b})"

    def sub(self, a, b):
        return f"std::cmp::max({a} - {b}, 0)"

    def render(self):
        p = self.p
        self.styles = {}
        self.add_file("Cargo.toml", f'[package]\nname = "{p.name}"\nversion = "0.2.0"\nedition = "2021"\n\n[dependencies]\n')
        pkgs = sorted({m.pkg for m in self.mods.values() if m.pkg})
        lib = [f"//! {p.title} {p.blurb}.", ""]
        top = [m for m in sorted(self.mods.values(), key=lambda m: m.rank) if not m.pkg and m.layer != "errors"]
        for pk in pkgs:
            lib.append(f"pub mod {pk};")
        for m in top:
            lib.append(f"pub mod {m.base};")
        self.add_file("src/lib.rs", "\n".join(lib))
        for pk in pkgs:
            ms = [m for m in sorted(self.mods.values(), key=lambda m: m.rank) if m.pkg == pk and m.layer != "errors"]
            self.add_file(f"src/{pk}/mod.rs", "\n".join(f"pub mod {m.base};" for m in ms))
        for m in sorted(self.mods.values(), key=lambda m: m.rank):
            if m.layer == "errors":
                continue
            self.render_module(m)
        self.render_tests()
        self.add_file("src/main.rs", f"use {p.name}::cli;\n\nfn main() {{\n    let args: Vec<String> = std::env::args().collect();\n    let count: i64 = args[1].parse().expect(\"count must be a number\");\n    let days: i64 = args[2].parse().expect(\"days must be a number\");\n    println!(\"{{}}\", cli::run(count, days));\n}}\n")
        self.r.fn_line["cli.main"] = ("src/main.rs", 3)
        self.r.sites.append(("cli.main", "cli.run", "src/main.rs", 7))
        self.r.ident["cli.main"] = "main"
        self.r.main_path = "src/main.rs"
        self.add_file("README.md", self.readme(self.layout_notes() + [("src/main.rs", "binary entry point"), ("tests/", "integration tests, one file per module")],
                                              "cargo run --quiet -- 5 3", "cargo test"))
        self.add_file(".gitignore", "target/\n")
        return self.r

    def render_module(self, m):
        p = self.p
        buf = Buf(self.UNIT)
        path = self.modpath(m)
        self.r.path[m.key] = path
        used = p.used_imports(m.key)
        self.styles = self.choose_style(m, used)
        buf.line(f"//! {m.doc}")
        buf.blank()
        for ck, syms in used.items():
            cm = self.mods[ck]
            if self.styles[ck] == "use":
                names = sorted({self.sym_ident(s) for s in syms})
                if len(names) == 1:
                    buf.line(f"use {self.crate_path(cm)}::{names[0]};")
                else:
                    buf.line(f"use {self.crate_path(cm)}::{{{', '.join(names)}}};")
            else:
                buf.line(f"use {self.crate_path(cm)};")
        if used:
            buf.blank()
        for k, v in m.consts:
            buf.line(f"const {k}: i64 = {v};")
        if m.consts:
            buf.blank()
        for fid in m.fids:
            fn = p.fns[fid]
            if fn.kind == "main":
                continue
            start = len(buf.lines)
            self.fn(fn, m, buf)
            self.r.fn_line[fid] = (path, start + 2)
            self.r.ident[fid] = self.ident(fn)
            buf.blank()
        self.finish_buf(path, buf)
        self.add_file(path, "\n".join(buf.lines).rstrip("\n") + "\n")

    def fn(self, fn, m, buf):
        buf.cur = fn.fid
        self.vars_assigned = {s[1] for s in self.p_stmts(fn.body) if s[0] == "set"}
        vis = "pub " if fn.public else ""
        ps = ", ".join(f"{x}: i64" for x in fn.params)
        buf.line(f"/// {fn.doc}")
        buf.line(f"{vis}fn {self.ident(fn)}({ps}) -> i64 {{")
        buf.indent()
        for s in fn.body:
            self.st(s, m, buf)
        buf.dedent()
        buf.line("}")

    def p_stmts(self, body):
        for s in body:
            yield s
            if s[0] == "if":
                yield from self.p_stmts(s[2])
                yield from self.p_stmts(s[3])
            elif s[0] == "for":
                yield from self.p_stmts(s[4])

    def st(self, s, m, buf):
        t = s[0]
        calls: list = []
        if t == "let":
            mut = "mut " if s[1] in self.vars_assigned else ""
            buf.line(f"let {mut}{s[1]} = {self.e(s[2], m, calls)};", calls)
        elif t == "set":
            buf.line(f"{s[1]} = {self.e(s[2], m, calls)};", calls)
        elif t == "do":
            buf.line(self.e(s[1], m, calls) + ";", calls)
        elif t == "ret":
            buf.line(f"return {self.e(s[1], m, calls)};", calls)
        elif t == "if":
            buf.line(f"if {self.cond(s[1], m, calls)} {{", calls)
            self.block(s[2], m, buf)
            if s[3]:
                buf.line("} else {")
                self.block(s[3], m, buf)
            buf.line("}")
        elif t == "for":
            buf.line(f"for {s[1]} in {self.e(s[2], m, calls)}..{self.e(s[3], m, calls)} {{", calls)
            self.block(s[4], m, buf)
            buf.line("}")
        elif t == "emit":
            parts = self.tpl_parts(s[1])
            fmt = "{}".join(parts)
            args = ", ".join(self.e(a, m, calls) for a in s[2])
            buf.line(f'println!("{fmt}", {args});', calls)
        else:
            raise ValueError(f"rust cannot render {t}")

    def block(self, body, m, buf):
        buf.indent()
        for s in body:
            self.st(s, m, buf)
        buf.dedent()

    def render_tests(self):
        p = self.p
        by_mod: dict = {}
        for c in p.cases:
            if p.fns[c.fid].mod == "cli":
                continue
            by_mod.setdefault(p.fns[c.fid].mod, []).append(c)
        for mk, cases in by_mod.items():
            m = self.mods[mk]
            buf = Buf(self.UNIT)
            path = f"tests/{m.base}.rs"
            names = sorted({self.ident(p.fns[c.fid]) for c in cases})
            buf.line(f"use {p.name}::{'::'.join(([m.pkg] if m.pkg else []) + [m.base])}::{{{', '.join(names)}}};" if len(names) > 1 else
                     f"use {p.name}::{'::'.join(([m.pkg] if m.pkg else []) + [m.base])}::{names[0]};")
            buf.blank()
            for c in cases:
                tname = c.name
                self.r.tests[c.name] = (path, len(buf.lines) + 2, tname)
                args = ", ".join(str(a) for a in c.args)
                buf.line("#[test]")
                buf.line(f"fn {tname}() {{")
                buf.cur = "test:" + c.name
                buf.line(f"    assert_eq!({self.ident(p.fns[c.fid])}({args}), {c.value});", [c.fid])
                buf.line("}")
                buf.blank()
            self.r.test_paths.append(path)
            self.finish_buf(path, buf)
            self.add_file(path, "\n".join(buf.lines).rstrip("\n") + "\n")


# ====================================================================================================================
# ruby
# ====================================================================================================================
class RubyR(Base):
    LANG, EXT, UNIT = "ruby", ".rb", "  "
    AND, OR = "&&", "||"

    def ident(self, fn):
        return fn.name

    def module_ident(self, m):
        return pascal(m.base) if m.layer != "cli" else "Cli"

    def pkg_ident(self, m):
        return {"util": "Util", "core": "Core", "services": "Services"}.get(m.pkg, "")

    def modpath(self, m):
        return f"lib/{self.p.name}/{m.pkg + '/' if m.pkg else ''}{m.base}.rb"

    def root(self):
        return pascal(self.p.name)

    def pick_style(self, m, cm):
        return "const"

    def qual(self, m, cm):
        if cm.pkg and cm.pkg != m.pkg:
            return f"{self.pkg_ident(cm)}::{self.module_ident(cm)}"
        return self.module_ident(cm)

    def callhead(self, m, fid):
        f = self.p.fns[fid]
        if f.mod == m.key:
            return self.ident(f)
        return f"{self.qual(m, self.mods[f.mod])}.{self.ident(f)}"

    def excname(self, m, name):
        em = self.mods[self.p.exc_mod()]
        return f"{self.pkg_ident(em)}::{name}" if em.pkg else name

    def minmax(self, o, a, b):
        return f"[{a}, {b}].{o}"

    def sub(self, a, b):
        return f"[{a} - {b}, 0].max"

    def relpath(self, m, cm):
        if m.pkg == cm.pkg:
            return f"{cm.base}" if not m.pkg else f"{cm.base}"
        if not m.pkg:
            return f"{cm.pkg}/{cm.base}"
        return f"../{cm.pkg}/{cm.base}" if cm.pkg else f"../{cm.base}"

    def render(self):
        p = self.p
        mods = [m for m in sorted(self.mods.values(), key=lambda m: m.rank)]
        req = []
        for m in mods:
            self.render_module(m)
            req.append(f"require_relative '{p.name}/{m.pkg + '/' if m.pkg else ''}{m.base}'")
        self.add_file(f"lib/{p.name}.rb", f"# frozen_string_literal: true\n\n# {p.title} {p.blurb}.\n" + "\n".join(req) + "\n")
        self.add_file(f"bin/{p.name}", f"#!/usr/bin/env ruby\n# frozen_string_literal: true\n\nrequire_relative '../lib/{p.name}'\n\nexit {self.root()}::Cli.main(ARGV)\n")
        self.render_tests()
        self.r.main_path = self.r.path["cli"]
        self.add_file("README.md", self.readme(self.layout_notes() + [(f"bin/{p.name}", "executable"), ("test/", "minitest files")],
                                              f"ruby bin/{p.name} 5 3", "ruby -Ilib -Itest -e 'Dir[\"test/test_*.rb\"].each { |f| require \"./#{f}\" }'"))
        self.add_file("Gemfile", "source 'https://rubygems.org'\n")
        return self.r

    def open_mods(self, m, buf):
        names = [self.root()] + ([self.pkg_ident(m)] if m.pkg else []) + [self.module_ident(m)]
        for n in names:
            buf.line(f"module {n}")
            buf.indent()
        return len(names)

    def close_mods(self, n, buf):
        for _ in range(n):
            buf.dedent()
            buf.line("end")

    def render_module(self, m):
        p = self.p
        buf = Buf(self.UNIT)
        path = self.modpath(m)
        self.r.path[m.key] = path
        buf.line("# frozen_string_literal: true")
        buf.blank()
        if m.layer == "errors":
            buf.line(f"module {self.root()}")
            buf.indent()
            if m.pkg:
                buf.line(f"module {self.pkg_ident(m)}")
                buf.indent()
            for name, base in p.excs:
                buf.line(f"class {name} < {base or 'StandardError'}")
                buf.line("end")
                buf.blank()
            while buf.lines[-1] == "":
                buf.lines.pop()
            if m.pkg:
                buf.dedent()
                buf.line("end")
            buf.dedent()
            buf.line("end")
            self.add_file(path, "\n".join(buf.lines))
            return
        used = p.used_imports(m.key)
        for ck in used:
            self.r.style[(m.key, ck)] = "const"
        reqs = [self.relpath(m, self.mods[k]) for k in used if k not in m.lazy]
        reqs += [self.relpath(m, self.mods[d]) for d in m.decoys if d not in used]
        for r in sorted(set(reqs)):
            buf.line(f"require_relative '{r}'")
        if reqs:
            buf.blank()
        n = self.open_mods(m, buf)
        first = True
        for k, v in m.consts:
            buf.line(f"{k} = {v}")
            first = False
        privates = []
        for fid in m.fids:
            fn = p.fns[fid]
            if fn.kind == "main":
                continue
            if not first:
                buf.blank()
            first = False
            start = len(buf.lines)
            self.fn(fn, m, buf)
            self.r.fn_line[fid] = (path, start + 2)
            self.r.ident[fid] = self.ident(fn)
            if not fn.public:
                privates.append(fn.name)
        if m.layer == "cli":
            fn = p.fns["cli.main"]
            buf.blank()
            buf.cur = fn.fid
            self.r.fn_line[fn.fid] = (path, len(buf.lines) + 2)
            self.r.ident[fn.fid] = "main"
            buf.line("# Command line entry point.")
            buf.line("def self.main(argv)")
            buf.indent()
            buf.line("count, days = argv.map(&:to_i)")
            buf.line("puts run(count, days)", ["cli.run"])
            buf.line("0")
            buf.dedent()
            buf.line("end")
        if privates:
            buf.blank()
            buf.line("private_class_method " + ", ".join(f":{x}" for x in privates))
        self.close_mods(n, buf)
        self.finish_buf(path, buf)
        self.add_file(path, "\n".join(buf.lines))

    def fn(self, fn, m, buf):
        buf.cur = fn.fid
        buf.line(f"# {fn.doc}")
        buf.line(f"def self.{self.ident(fn)}({', '.join(fn.params)})")
        buf.indent()
        for lm in m.lazy:
            if any(self.p.fns[c].mod == lm for c in self.p.callees(fn.fid)):
                buf.line(f"require_relative '{self.relpath(m, self.mods[lm])}'")
        for s in fn.body:
            self.st(s, m, buf)
        buf.dedent()
        buf.line("end")

    def st(self, s, m, buf):
        t = s[0]
        calls: list = []
        if t in ("let", "set"):
            buf.line(f"{s[1]} = {self.e(s[2], m, calls)}", calls)
        elif t == "do":
            buf.line(self.e(s[1], m, calls), calls)
        elif t == "ret":
            buf.line(f"return {self.e(s[1], m, calls)}", calls)
        elif t == "if":
            buf.line(f"if {self.cond(s[1], m, calls)}", calls)
            self.block(s[2], m, buf)
            if s[3]:
                buf.line("else")
                self.block(s[3], m, buf)
            buf.line("end")
        elif t == "for":
            buf.line(f"({self.e(s[2], m, calls)}...{self.e(s[3], m, calls)}).each do |{s[1]}|", calls)
            self.block(s[4], m, buf)
            buf.line("end")
        elif t == "emit":
            buf.line(f'puts "{self.istr(s[1], s[2], m, calls)}"', calls)
        elif t == "raise":
            buf.line(f'raise {self.excname(m, s[1])}, "{self.istr(s[2], s[3], m, calls)}"', calls)
        elif t == "try":
            buf.line("begin")
            self.block(s[1], m, buf)
            for exc, h in s[2]:
                buf.line(f"rescue {self.excname(m, exc)}")
                self.block(h, m, buf)
            if s[3]:
                buf.line("ensure")
                self.block(s[3], m, buf)
            buf.line("end")
        else:
            raise ValueError(t)

    def block(self, body, m, buf):
        buf.indent()
        for s in body:
            self.st(s, m, buf)
        buf.dedent()

    def istr(self, tpl, args, m, calls):
        parts = self.tpl_parts(tpl)
        out = parts[0]
        for a, ptxt in zip(args, parts[1:]):
            out += "#{" + self.e(a, m, calls) + "}" + ptxt
        return out

    def render_tests(self):
        p = self.p
        by_mod: dict = {}
        for c in p.cases:
            if p.fns[c.fid].mod == "cli":
                continue
            by_mod.setdefault(p.fns[c.fid].mod, []).append(c)
        for mk, cases in by_mod.items():
            m = self.mods[mk]
            buf = Buf(self.UNIT)
            path = f"test/test_{m.base}.rb"
            buf.line("# frozen_string_literal: true")
            buf.blank()
            buf.line("require 'minitest/autorun'")
            buf.line(f"require '{p.name}'")
            buf.blank()
            buf.line(f"class {pascal(m.base)}Test < Minitest::Test")
            buf.indent()
            qual = f"{self.root()}::" + (self.pkg_ident(m) + "::" if m.pkg else "") + self.module_ident(m)
            exc_q = ""
            if p.exc_mod():
                exc_q = f"{self.root()}::" + (self.pkg_ident(self.mods[p.exc_mod()]) + "::" if self.mods[p.exc_mod()].pkg else "")
            for i, c in enumerate(cases):
                if i:
                    buf.blank()
                tname = "test_" + c.name
                self.r.tests[c.name] = (path, len(buf.lines) + 1, tname)
                args = ", ".join(str(a) for a in c.args)
                buf.line(f"def {tname}")
                buf.cur = "test:" + c.name
                if c.expect == "raises":
                    buf.line(f"  assert_raises({exc_q}{c.exc}) {{ {qual}.{self.ident(p.fns[c.fid])}({args}) }}", [c.fid])
                else:
                    buf.line(f"  assert_equal {c.value}, {qual}.{self.ident(p.fns[c.fid])}({args})", [c.fid])
                buf.line("end")
            buf.dedent()
            buf.line("end")
            self.r.test_paths.append(path)
            self.finish_buf(path, buf)
            self.add_file(path, "\n".join(buf.lines))


RENDERERS = {"python": PyR, "javascript": JsR, "go": GoR, "java": JavaR, "rust": RustR, "ruby": RubyR}


def render(proj: Project, rng: random.Random) -> Rendered:
    return RENDERERS[proj.lang](proj, rng).render()
