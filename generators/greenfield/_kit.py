"""Shared scaffolding for the greenfield families.

Two interface "molds" cover every language we use:

* **lib** - a pure function ``fn(arg: str, ...) -> str`` (1 to 3 string arguments, one string result). The task ships
  a skeleton (stub with the exact signature, build files, README, a few visible tests); the hidden tests call the
  function with many inputs and compare the whole result text. Errors are reported *in-band* in the result text so
  that no language-specific exception type is part of the contract.
* **cli** - a program run as ``tool [args] < stdin``; stdout and the exit code are compared by a bash harness.

Expected values are never typed by hand: ``record_lib`` / ``record_cli`` run the *reference solution* (the task's
``solution``) on every case and the hidden tests embed what it printed.  Each family also has a Python oracle (its
Python solution); ports in other languages are cross-checked against the oracle at generation time, so a mismatch
between two independent implementations of the README fails the build instead of shipping an unfair task.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field

from fx import Task, dd, langs, merged, run

LIB_LANGS = ["python", "javascript", "go", "rust", "java", "ruby", "c"]
SEP = "\x1e"


# ---------------------------------------------------------------------------------------------------------------
# naming
# ---------------------------------------------------------------------------------------------------------------

def pascal(s: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in s.split("_"))


def camel(s: str) -> str:
    p = pascal(s)
    return p[:1].lower() + p[1:]


@dataclass
class Api:
    mod: str  # lower-case identifier: module / package / crate / header name (not a Rust keyword)
    fn: str  # snake_case function name
    args: list[str]  # snake_case argument names
    arg_docs: list[str] = field(default_factory=list)
    ret_doc: str = "the result text"
    doc: str = ""  # one line used in stubs

    def name(self, lang: str) -> str:
        if lang in ("javascript", "java"):
            return camel(self.fn)
        if lang == "go":
            return pascal(self.fn)
        return self.fn

    def argname(self, lang: str, i: int) -> str:
        a = self.args[i]
        return camel(a) if lang in ("javascript", "java", "go") else a

    @property
    def cls(self) -> str:
        return pascal(self.mod)

    @property
    def n(self) -> int:
        return len(self.args)

    def path(self, lang: str) -> str:
        return {
            "python": f"src/{self.mod}.py",
            "javascript": f"src/{self.mod}.js",
            "go": f"{self.mod}.go",
            "rust": "src/lib.rs",
            "java": f"src/{self.cls}.java",
            "ruby": f"lib/{self.mod}.rb",
            "c": f"src/{self.mod}.c",
        }[lang]

    def signature(self, lang: str) -> str:
        a = self.args
        if lang == "python":
            return f"def {self.fn}({', '.join(a)}) -> str"
        if lang == "javascript":
            return f"function {self.name(lang)}({', '.join(camel(x) for x in a)})  // returns a string; exported with module.exports"
        if lang == "go":
            return f"func {self.name(lang)}({', '.join(camel(x) for x in a)} string) string"
        if lang == "rust":
            return f"pub fn {self.fn}({', '.join(x + ': &str' for x in a)}) -> String"
        if lang == "java":
            return f"public static String {self.name(lang)}({', '.join('String ' + camel(x) for x in a)})"
        if lang == "ruby":
            return f"{self.cls}.{self.fn}({', '.join(a)})"
        if lang == "c":
            return f"char *{self.fn}({', '.join('const char *' + x for x in a)})"
        raise ValueError(lang)

    def where(self, lang: str) -> str:
        p = self.path(lang)
        if lang == "go":
            return f"`{p}` (package `{self.mod}`, module `example.com/{self.mod}`)"
        if lang == "java":
            return f"`{p}` (class `{self.cls}`, default package)"
        if lang == "ruby":
            return f"`{p}` (module `{self.cls}`)"
        if lang == "c":
            return f"`{p}`; the declaration is already in `include/{self.mod}.h`. The returned string is allocated with `malloc` and the caller frees it"
        if lang == "rust":
            return f"`{p}` (library crate `{self.mod}`)"
        return f"`{p}`"


# ---------------------------------------------------------------------------------------------------------------
# literals
# ---------------------------------------------------------------------------------------------------------------

def lit(lang: str, s: str) -> str:
    """A double-quoted string literal in ``lang`` (ASCII only)."""
    out = []
    for i, ch in enumerate(s):
        o = ord(ch)
        if o >= 128:
            raise ValueError(f"non-ASCII text in a test case: {s!r}")
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"' and lang != "bash":
            out.append('\\"')
        elif ch == "'" and lang == "bash":
            out.append("\\'")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "#" and lang == "ruby":
            out.append("\\#")
        elif ch == "?" and lang == "c":
            out.append("\\?")
        elif o < 32 or o == 127:
            if lang == "java":
                out.append("\\u%04x" % o)
            elif lang == "c":
                out.append("\\%03o" % o)
            else:
                out.append("\\x%02x" % o)
        else:
            out.append(ch)
    body = "".join(out)
    if lang == "bash":
        return "$'" + body + "'"
    return '"' + body + '"'


# ---------------------------------------------------------------------------------------------------------------
# skeletons and stubs (lib mold)
# ---------------------------------------------------------------------------------------------------------------

def skeleton(api: Api, lang: str) -> dict[str, str]:
    """Build files that exist in the start repository (and are not tests)."""
    f: dict[str, str] = {}
    g = langs.GITIGNORE.get(lang, "")
    if g:
        f[".gitignore"] = g
    if lang == "go":
        f["go.mod"] = langs.go_mod(api.mod)
    if lang == "rust":
        f["Cargo.toml"] = langs.cargo_toml(api.mod)
    if lang == "c":
        guard = api.mod.upper() + "_H"
        f[f"include/{api.mod}.h"] = (
            f"#ifndef {guard}\n#define {guard}\n\n"
            f"/* {api.doc or api.fn}\n * Returns a malloc'd, NUL-terminated string; the caller frees it. */\n"
            f"char *{api.fn}({', '.join('const char *' + x for x in api.args)});\n\n#endif\n"
        )
    return f


def stub(api: Api, lang: str) -> dict[str, str]:
    doc = api.doc or f"see README.md for {api.fn}"
    a = api.args
    if lang == "python":
        body = f'"""{doc}"""\n\n\ndef {api.fn}({", ".join(x + ": str" for x in a)}) -> str:\n    raise NotImplementedError("write me: see README.md")\n'
    elif lang == "javascript":
        body = f"'use strict';\n\n// {doc}\nfunction {api.name(lang)}({', '.join(camel(x) for x in a)}) {{\n  throw new Error('write me: see README.md');\n}}\n\nmodule.exports = {{ {api.name(lang)} }};\n"
    elif lang == "go":
        body = f"// Package {api.mod}: {doc}\npackage {api.mod}\n\n// {api.name(lang)}: see README.md.\nfunc {api.name(lang)}({', '.join(camel(x) for x in a)} string) string {{\n\treturn \"\"\n}}\n"
    elif lang == "rust":
        body = f"//! {doc}\n\n/// See README.md.\npub fn {api.fn}({', '.join(x + ': &str' for x in a)}) -> String {{\n    todo!(\"write me: see README.md\")\n}}\n"
    elif lang == "java":
        body = f"/** {doc} */\npublic class {api.cls} {{\n    public static String {api.name(lang)}({', '.join('String ' + camel(x) for x in a)}) {{\n        throw new UnsupportedOperationException(\"write me: see README.md\");\n    }}\n}}\n"
    elif lang == "ruby":
        body = f"# {doc}\nmodule {api.cls}\n  def self.{api.fn}({', '.join(a)})\n    raise NotImplementedError, 'write me: see README.md'\n  end\nend\n"
    elif lang == "c":
        body = (f"#include <stdlib.h>\n#include \"{api.mod}.h\"\n\n/* {doc} */\nchar *{api.fn}({', '.join('const char *' + x for x in a)}) {{\n"
                f"{''.join(f'    (void){x};' + chr(10) for x in a)}    char *r = malloc(1);\n    if (r) r[0] = '\\0';\n    return r; /* write me: see README.md */\n}}\n")
    else:
        raise ValueError(lang)
    return {api.path(lang): body}


# ---------------------------------------------------------------------------------------------------------------
# test emitters (lib mold)
# ---------------------------------------------------------------------------------------------------------------

def test_path(api: Api, lang: str) -> str:
    return {
        "python": f"tests/test_{api.mod}.py",
        "javascript": f"test/{api.mod}.test.js",
        "go": f"{api.mod}_test.go",
        "rust": f"tests/{api.mod}.rs",
        "java": "tests/TestMain.java",
        "ruby": f"test/test_{api.mod}.rb",
        "c": f"tests/test_{api.mod}.c",
    }[lang]


def verify_cmd(lang: str) -> str:
    if lang == "javascript":
        return "node --test test/*.test.js"
    return langs.VERIFY[lang]


def _py_cases(cases, want):
    rows = []
    for c, w in zip(cases, want):
        rows.append(f"    ({json.dumps(list(c), ensure_ascii=True)}, {json.dumps(w, ensure_ascii=True)}),")
    return "\n".join(rows)


def test_files(api: Api, lang: str, cases: list[tuple], want: list[str]) -> dict[str, str]:
    """A native-framework test file for the cases; ``want`` are the expected results."""
    p = test_path(api, lang)
    fn, n = api.name(lang), api.n
    L = lambda s: lit(lang, s)  # noqa: E731
    if lang == "python":
        rows = "\n".join(f"    ({'(' + ', '.join(L(x) for x in c) + (',' if n == 1 else '') + ')'}, {L(w)})," for c, w in zip(cases, want))
        src = (
            "import os\nimport sys\nimport unittest\n\n"
            "sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), \"..\", \"src\"))\n"
            f"from {api.mod} import {fn}  # noqa: E402\n\n"
            f"CASES = [\n{rows}\n]\n\n\n"
            "class Cases(unittest.TestCase):\n"
            "    def test_cases(self):\n"
            "        for args, want in CASES:\n"
            "            with self.subTest(args=args):\n"
            f"                self.assertEqual({fn}(*args), want)\n\n\n"
            "if __name__ == \"__main__\":\n    unittest.main()\n"
        )
    elif lang == "javascript":
        rows = "\n".join(f"  [[{', '.join(L(x) for x in c)}], {L(w)}]," for c, w in zip(cases, want))
        src = (
            "'use strict';\nconst test = require('node:test');\nconst assert = require('node:assert');\n"
            f"const {{ {fn} }} = require('../src/{api.mod}');\n\n"
            f"const CASES = [\n{rows}\n];\n\n"
            "CASES.forEach(([args, want], i) => {\n"
            "  test(`case ${i}: ${JSON.stringify(args)}`, () => {\n"
            f"    assert.strictEqual({fn}(...args), want);\n  }});\n}});\n"
        )
    elif lang == "go":
        rows = "\n".join(f"\t\t{{[]string{{{', '.join(L(x) for x in c)}}}, {L(w)}}}," for c, w in zip(cases, want))
        call = f"{fn}({', '.join(f'c.in[{i}]' for i in range(n))})"
        src = (
            f"package {api.mod}\n\nimport \"testing\"\n\n"
            "func TestCases(t *testing.T) {\n\tcases := []struct {\n\t\tin   []string\n\t\twant string\n\t}{\n"
            f"{rows}\n\t}}\n\tfor i, c := range cases {{\n\t\tgot := {call}\n"
            "\t\tif got != c.want {\n\t\t\tt.Errorf(\"case %d %q:\\n got  %q\\n want %q\", i, c.in, got, c.want)\n\t\t}\n\t}\n}\n"
        )
    elif lang == "rust":
        rows = "\n".join(f"        (vec![{', '.join(L(x) for x in c)}], {L(w)})," for c, w in zip(cases, want))
        call = f"{fn}({', '.join(f'a[{i}]' for i in range(n))})"
        src = (
            f"use {api.mod}::{fn};\n\n#[test]\nfn cases() {{\n    let cases: Vec<(Vec<&str>, &str)> = vec![\n{rows}\n    ];\n"
            f"    for (i, (a, want)) in cases.iter().enumerate() {{\n        let got = {call};\n"
            "        assert_eq!(got, *want, \"case {} {:?}\", i, a);\n    }\n}\n"
        )
    elif lang == "java":
        rows = "\n".join(f"        {{{', '.join(L(x) for x in c)}, {L(w)}}}," for c, w in zip(cases, want))
        call = f"{api.cls}.{fn}({', '.join(f'c[{i}]' for i in range(n))})"
        src = (
            "public class TestMain {\n    public static void main(String[] args) {\n        String[][] cases = {\n"
            f"{rows}\n        }};\n        int failed = 0;\n        for (int i = 0; i < cases.length; i++) {{\n"
            f"            String[] c = cases[i];\n            String want = c[{n}];\n            String got;\n"
            f"            try {{\n                got = {call};\n            }} catch (Throwable e) {{\n                got = \"EXCEPTION \" + e;\n            }}\n"
            "            if (!want.equals(got)) {\n                failed++;\n"
            "                System.out.println(\"case \" + i + \" FAILED\\n  args: \" + String.join(\" | \", java.util.Arrays.copyOf(c, "
            f"{n}))"
            " + \"\\n  got:  \" + got + \"\\n  want: \" + want);\n            }\n        }\n"
            "        System.out.println((cases.length - failed) + \"/\" + cases.length + \" cases passed\");\n"
            "        if (failed > 0) System.exit(1);\n    }\n}\n"
        )
    elif lang == "ruby":
        rows = "\n".join(f"  [[{', '.join(L(x) for x in c)}], {L(w)}]," for c, w in zip(cases, want))
        src = (
            f"require 'minitest/autorun'\nrequire '{api.mod}'\n\nclass Test{api.cls} < Minitest::Test\n  CASES = [\n{rows}\n  ]\n\n"
            "  CASES.each_with_index do |(args, want), i|\n    define_method(\"test_case_#{i}\") do\n"
            f"      assert_equal want, {api.cls}.{fn}(*args), \"args: #{{args.inspect}}\"\n    end\n  end\nend\n"
        )
    elif lang == "c":
        blocks = []
        for i, (c, w) in enumerate(zip(cases, want)):
            blocks.append(f"    check({i}, {fn}({', '.join(L(x) for x in c)}), {L(w)});")
        src = (
            "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n"
            f"#include \"{api.mod}.h\"\n\nstatic int failed = 0;\n\n"
            "static void check(int i, char *got, const char *want) {\n"
            "    if (!got || strcmp(got, want) != 0) {\n        failed++;\n"
            "        printf(\"case %d FAILED\\n  got:  [%s]\\n  want: [%s]\\n\", i, got ? got : \"(null)\", want);\n    }\n    free(got);\n}\n\n"
            "int main(void) {\n" + "\n".join(blocks) + "\n    if (failed) {\n        printf(\"%d case(s) failed\\n\", failed);\n        return 1;\n    }\n"
            "    printf(\"all cases passed\\n\");\n    return 0;\n}\n"
        )
    else:
        raise ValueError(lang)
    return {p: src}


# recording programs: print hex(result) for every case, one per line


def _rec_files(api: Api, lang: str, cases: list[tuple]) -> dict[str, str]:
    fn, n = api.name(lang), api.n
    L = lambda s: lit(lang, s)  # noqa: E731
    if lang == "python":
        rows = "\n".join(f"    ({', '.join(L(x) for x in c)}{',' if n == 1 else ''})," for c in cases)
        return {"tests/_rec.py": (
            "import os, sys\nsys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))\n"
            f"from {api.mod} import {fn}\nCASES = [\n{rows}\n]\nfor a in CASES:\n    print({fn}(*a).encode().hex())\n")}
    if lang == "javascript":
        rows = "\n".join(f"  [{', '.join(L(x) for x in c)}]," for c in cases)
        return {"tests/_rec.js": (
            f"const {{ {fn} }} = require('../src/{api.mod}');\nconst CASES = [\n{rows}\n];\n"
            f"for (const a of CASES) console.log(Buffer.from({fn}(...a)).toString('hex'));\n")}
    if lang == "go":
        rows = "\n".join(f"\t\t{{{', '.join(L(x) for x in c)}}}," for c in cases)
        call = f"{api.mod}.{fn}({', '.join(f'a[{i}]' for i in range(n))})"
        return {"_rec/main.go": (
            f"package main\n\nimport (\n\t\"encoding/hex\"\n\t\"fmt\"\n\n\t\"example.com/{api.mod}\"\n)\n\n"
            f"func main() {{\n\tcases := [][]string{{\n{rows}\n\t}}\n\tfor _, a := range cases {{\n\t\tfmt.Println(hex.EncodeToString([]byte({call})))\n\t}}\n}}\n")}
    if lang == "rust":
        rows = "\n".join(f"        vec![{', '.join(L(x) for x in c)}]," for c in cases)
        call = f"{api.mod}::{fn}({', '.join(f'a[{i}]' for i in range(n))})"
        return {"examples/_rec.rs": (
            f"fn main() {{\n    let cases: Vec<Vec<&str>> = vec![\n{rows}\n    ];\n    for a in cases {{\n        let r = {call};\n"
            "        let h: String = r.bytes().map(|b| format!(\"{:02x}\", b)).collect();\n        println!(\"{}\", h);\n    }\n}\n")}
    if lang == "java":
        rows = "\n".join(f"        {{{', '.join(L(x) for x in c)}}}," for c in cases)
        call = f"{api.cls}.{fn}({', '.join(f'c[{i}]' for i in range(n))})"
        return {"tests/Rec.java": (
            "public class Rec {\n    public static void main(String[] args) throws Exception {\n        String[][] cases = {\n"
            f"{rows}\n        }};\n        for (String[] c : cases) {{\n            byte[] b = {call}.getBytes(\"UTF-8\");\n"
            "            StringBuilder sb = new StringBuilder();\n            for (byte x : b) sb.append(String.format(\"%02x\", x & 0xff));\n"
            "            System.out.println(sb);\n        }\n    }\n}\n")}
    if lang == "ruby":
        rows = "\n".join(f"  [{', '.join(L(x) for x in c)}]," for c in cases)
        return {"tests/_rec.rb": (
            f"require '{api.mod}'\nCASES = [\n{rows}\n]\nCASES.each {{ |a| puts {api.cls}.{fn}(*a).unpack1('H*') }}\n")}
    if lang == "c":
        blocks = "\n".join(f"    show({fn}({', '.join(L(x) for x in c)}));" for c in cases)
        return {"tests/_rec.c": (
            "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n"
            f"#include \"{api.mod}.h\"\n\nstatic void show(char *s) {{\n    if (!s) {{ printf(\"NULL\\n\"); return; }}\n"
            "    for (size_t i = 0; s[i]; i++) printf(\"%02x\", (unsigned char)s[i]);\n    printf(\"\\n\");\n    free(s);\n}\n\n"
            f"int main(void) {{\n{blocks}\n    return 0;\n}}\n")}
    raise ValueError(lang)


def _rec_cmd(lang: str) -> str:
    return {
        "python": "python3 tests/_rec.py",
        "javascript": "node tests/_rec.js",
        "go": "go run ./_rec",
        "rust": "cargo run --offline --quiet --example _rec",
        "java": "rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java') && java -cp build Rec",
        "ruby": "ruby -Ilib tests/_rec.rb",
        "c": "mkdir -p build && gcc -std=c11 -O1 -Iinclude -Isrc -o build/rec $(find src -name '*.c') tests/_rec.c && ./build/rec",
    }[lang]


class RecordError(RuntimeError):
    pass


def record_lib(api: Api, lang: str, tree: dict[str, str], cases: list[tuple], timeout: int = 150) -> list[str]:
    """Run the reference solution ``tree`` (a complete repository) on ``cases`` and return the results."""
    if not cases:
        return []
    files = merged(tree, _rec_files(api, lang, cases))
    r = run(files, _rec_cmd(lang), timeout=timeout)
    if not r.ok:
        raise RecordError(f"{api.mod} [{lang}] reference solution failed:\n{r.out[-1500:]}")
    lines = [ln.strip() for ln in r.out.splitlines() if re.fullmatch(r"[0-9a-f]*", ln.strip())]
    # the build may print noise; keep only hex-looking lines at the tail. fx.run keeps only the last 24000 characters of
    # the output, so a long output may have lost its head: record such cases in smaller batches
    if len(lines) < len(cases) or len(r.out) >= 23_000:
        if len(cases) > 1:  # output may have been truncated: record in halves
            h = len(cases) // 2
            return record_lib(api, lang, tree, cases[:h], timeout) + record_lib(api, lang, tree, cases[h:], timeout)
        raise RecordError(f"{api.mod} [{lang}] recorded {len(lines)} of {len(cases)} results:\n{r.out[-800:]}")
    lines = lines[-len(cases):]
    return [bytes.fromhex(x).decode("utf-8") for x in lines]


# ---------------------------------------------------------------------------------------------------------------
# cli mold
# ---------------------------------------------------------------------------------------------------------------

@dataclass
class CliSpec:
    tool: str  # program name, lower-case identifier

    def path(self, lang: str) -> str:
        return {
            "python": f"src/{self.tool}.py",
            "javascript": f"src/{self.tool}.js",
            "go": "main.go",
            "rust": "src/main.rs",
            "java": "src/Main.java",
            "ruby": f"src/{self.tool}.rb",
            "bash": f"src/{self.tool}.sh",
            "c": "src/main.c",
        }[lang]

    def build(self, lang: str) -> str:
        t = self.tool
        return {
            "python": "true",
            "javascript": "true",
            "ruby": "true",
            "bash": "true",
            "go": f"go build -o build/{t} .",
            "rust": "cargo build --offline --quiet",
            "java": "rm -rf build && mkdir -p build && javac -d build $(find src -name '*.java')",
            "c": f"mkdir -p build && gcc -std=c11 -O1 -Wall -Wextra -o build/{t} $(find src -name '*.c')",
        }[lang]

    def runcmd(self, lang: str) -> str:
        t = self.tool
        return {
            "python": f"python3 src/{t}.py",
            "javascript": f"node src/{t}.js",
            "ruby": f"ruby src/{t}.rb",
            "bash": f"bash src/{t}.sh",
            "go": f"build/{t}",
            "rust": f"target/debug/{t}",
            "java": "java -cp build Main",
            "c": f"build/{t}",
        }[lang]

    def short(self, lang: str) -> str:
        """Just the entry file, for prompts."""
        return {"go": "`main.go`", "rust": "`src/main.rs`", "java": "`src/Main.java`", "c": "`src/main.c`"}.get(lang, f"`{self.path(lang)}`")

    def how(self, lang: str) -> str:
        return {
            "python": f"`src/{self.tool}.py` (run as `python3 src/{self.tool}.py`)",
            "javascript": f"`src/{self.tool}.js` (run as `node src/{self.tool}.js`)",
            "ruby": f"`src/{self.tool}.rb` (run as `ruby src/{self.tool}.rb`)",
            "bash": f"`src/{self.tool}.sh` (run as `bash src/{self.tool}.sh`; bash 5 and the usual POSIX tools such as awk and sed are available)",
            "go": f"`main.go` and any other `.go` files in the module root (package `main`; built with `go build -o build/{self.tool} .`)",
            "rust": f"`src/main.rs` (binary crate `{self.tool}`; built with `cargo build --offline`)",
            "java": "`src/Main.java` (class `Main` in the default package; any further classes go in `src/` too; run as `java -cp build Main`)",
            "c": f"`src/main.c` (plus any other `.c` files under `src/`; built with `gcc -std=c11 -Wall -Wextra`)",
        }[lang]

    def skeleton(self, lang: str) -> dict[str, str]:
        f: dict[str, str] = {}
        g = langs.GITIGNORE.get(lang, "")
        if lang in ("go", "java", "c"):
            g = "build/\n"
        if g:
            f[".gitignore"] = g
        if lang == "go":
            f["go.mod"] = langs.go_mod(self.tool)
        if lang == "rust":
            f["Cargo.toml"] = (f'[package]\nname = "{self.tool}"\nversion = "0.1.0"\nedition = "2021"\n\n[[bin]]\nname = "{self.tool}"\npath = "src/main.rs"\n\n[dependencies]\n')
        return f

    def stub(self, lang: str) -> dict[str, str]:
        msg = "not implemented: see README.md"
        body = {
            "python": f"import sys\n\n\ndef main():\n    sys.stderr.write(\"{msg}\\n\")\n    return 2\n\n\nif __name__ == \"__main__\":\n    sys.exit(main())\n",
            "javascript": f"'use strict';\nprocess.stderr.write('{msg}\\n');\nprocess.exit(2);\n",
            "ruby": f"$stderr.puts '{msg}'\nexit 2\n",
            "bash": f"#!/usr/bin/env bash\necho '{msg}' >&2\nexit 2\n",
            "go": f"package main\n\nimport (\n\t\"fmt\"\n\t\"os\"\n)\n\nfunc main() {{\n\tfmt.Fprintln(os.Stderr, \"{msg}\")\n\tos.Exit(2)\n}}\n",
            "rust": f"fn main() {{\n    eprintln!(\"{msg}\");\n    std::process::exit(2);\n}}\n",
            "java": f"public class Main {{\n    public static void main(String[] args) {{\n        System.err.println(\"{msg}\");\n        System.exit(2);\n    }}\n}}\n",
            "c": f"#include <stdio.h>\n\nint main(void) {{\n    fprintf(stderr, \"{msg}\\n\");\n    return 2;\n}}\n",
        }[lang]
        return {self.path(lang): body}

    def verify(self, lang: str) -> str:
        return f"{self.build(lang)} && bash tests/run.sh {self.runcmd(lang)}"


@dataclass
class CliCase:
    args: list[str] = field(default_factory=list)
    stdin: str = ""
    out: str | None = None  # expected stdout
    code: int = 0
    fresh: bool = True  # start from an empty state directory; False continues the previous case's state (`@STATE@` in an argument is the state file path)

    def key(self):
        return (tuple(self.args), self.stdin, self.fresh)


_HARNESS_HEAD = """#!/usr/bin/env bash
# Usage: bash tests/run.sh COMMAND [ARGS...]   (the program under test, e.g. `python3 src/tool.py`)
CMD=("$@")
fail=0
n=0
# check NAME EXPECTED_CODE EXPECTED_STDOUT STDIN [ARG...]
check() {
  local name=$1 ecode=$2 eout=$3 sin=$4
  shift 4
  n=$((n + 1))
  local res out code
  res=$(printf '%s' "$sin" | "${CMD[@]}" "$@" 2>/dev/null; printf '\\n~%d' "$?")
  code=${res##*~}
  out=${res%$'\\n'~*}
  if [ "$code" != "$ecode" ] || [ "$(printf '%s' "$out")" != "$(printf '%s' "$eout")" ]; then
    fail=$((fail + 1))
    echo "FAIL [$name] args: $*  (stdin: $(printf '%s' "$sin" | head -c 200 | tr '\n' '|'))"
    echo "  exit code: got $code, want $ecode"
    echo "  stdout got:"; printf '%s\\n' "$out" | sed 's/^/    | /' | head -n 12
    echo "  stdout want:"; printf '%s\\n' "$eout" | sed 's/^/    | /' | head -n 12
  fi
}
"""


def _cli_call(c: CliCase, i: int, out: str | None, code: int | None) -> str:
    args = " ".join(lit("bash", a) for a in c.args)
    pre = "newstate\n" if c.fresh else ""
    return pre + f"check c{i} {code} {lit('bash', out or '')} {lit('bash', c.stdin)}" + (f" {args}" if args else "")


def cli_tests(cases: list[CliCase], want: list[tuple[str, int]]) -> dict[str, str]:
    body = [_HARNESS_HEAD]
    for i, (c, (o, code)) in enumerate(zip(cases, want)):
        body.append(_cli_call(c, i, o, code))
    body.append('\nif [ "$fail" -ne 0 ]; then\n  echo "$fail of $n checks failed"\n  exit 1\nfi\necho "all $n checks passed"\n')
    return {"tests/run.sh": "\n".join(body)}


def _cli_rec(cases: list[CliCase]) -> str:
    head = """#!/usr/bin/env bash
CMD=("$@")
STATE_DIR=$(mktemp -d)
STATE="$STATE_DIR/state"
trap 'rm -rf "$STATE_DIR"' EXIT
newstate() { rm -rf "$STATE_DIR"/*; }
rec() {
  local sin=$1
  shift
  local args=() a res out code
  for a in "$@"; do args+=("${a//@STATE@/$STATE}"); done
  res=$(printf '%s' "$sin" | "${CMD[@]}" "${args[@]}" 2>/dev/null; printf '\\n~%d' "$?")
  code=${res##*~}
  out=${res%$'\\n'~*}
  printf '%s %s\\n' "$code" "$(printf '%s' "$out" | od -An -v -tx1 | tr -d ' \\n')"
}
"""
    lines = [head]
    for c in cases:
        args = " ".join(lit("bash", a) for a in c.args)
        if c.fresh:
            lines.append("newstate")
        lines.append(f"rec {lit('bash', c.stdin)}" + (f" {args}" if args else ""))
    return "\n".join(lines) + "\n"


def record_cli(spec: CliSpec, lang: str, tree: dict[str, str], cases: list[CliCase], timeout: int = 150) -> list[tuple[str, int]]:
    if not cases:
        return []
    files = merged(tree, {"tests/_rec.sh": _cli_rec(cases)})
    r = run(files, f"{spec.build(lang)} && bash tests/_rec.sh {spec.runcmd(lang)}", timeout=timeout)
    if not r.ok:
        raise RecordError(f"{spec.tool} [{lang}] reference solution failed:\n{r.out[-1500:]}")
    res = []
    truncated = len(r.out) >= 23_000  # fx.run keeps only the last 24000 characters: the head may be cut
    if not truncated:
        for ln in r.out.splitlines():
            m = re.fullmatch(r"(\d+) ?([0-9a-f]*)", ln.strip())
            if m and len(m.group(2)) % 2 == 0:
                res.append((bytes.fromhex(m.group(2)).decode("utf-8", "replace"), int(m.group(1))))
    if truncated or len(res) < len(cases):
        mid = len(cases) // 2
        cuts = [i for i in range(1, len(cases)) if cases[i].fresh]
        if cuts:
            h = min(cuts, key=lambda i: abs(i - mid))
            return record_cli(spec, lang, tree, cases[:h], timeout) + record_cli(spec, lang, tree, cases[h:], timeout)
        raise RecordError(f"{spec.tool} [{lang}] recorded {len(res)} of {len(cases)}:\n{r.out[-800:]}")
    return res[-len(cases):]


# ---------------------------------------------------------------------------------------------------------------
# oracle
# ---------------------------------------------------------------------------------------------------------------

def py_namespace(src: str) -> dict:
    ns: dict = {"__name__": "oracle"}
    exec(compile(src, "<oracle>", "exec"), ns)
    return ns


def crosscheck(label: str, got: list, oracle: list, cases: list) -> None:
    for i, (g, o) in enumerate(zip(got, oracle)):
        if g != o:
            raise RecordError(f"{label}: port and oracle disagree on case {i}: {cases[i]!r}\n port:   {g!r}\n oracle: {o!r}")


# ---------------------------------------------------------------------------------------------------------------
# README helpers
# ---------------------------------------------------------------------------------------------------------------

def fence(s: str, info: str = "") -> str:
    s = s if s.endswith("\n") else s + "\n"
    return f"```{info}\n{s}```\n"


def interface_section(api: Api, lang: str) -> str:
    lines = ["## Interface", "", f"Implement this function in {api.where(lang)}:", "", "```", api.signature(lang), "```", ""]
    for a, d in zip(api.args, api.arg_docs):
        lines.append(f"* `{api.argname(lang, api.args.index(a))}`: {d}")
    lines.append(f"* returns {api.ret_doc}.")
    lines.append("")
    lines.append("All inputs and the result are plain strings. Invalid input is reported *inside the result text* as the "
                 "rules in this document say; the function itself never throws, panics or exits.")
    lines.append("")
    return "\n".join(lines)


def run_hint(lang: str, name: str = "name") -> str:
    return {
        "python": "Run the visible tests with `python3 -m unittest discover -s tests -v`.",
        "javascript": "Run the visible tests with `node --test test/*.test.js`.",
        "go": "Run the visible tests with `go test ./...`.",
        "rust": "Run the visible tests with `cargo test --offline`.",
        "java": "Run the visible tests with `mkdir -p build && javac -d build $(find . -name '*.java') && java -cp build TestMain`.",
        "ruby": f"Run the visible tests with `ruby -Ilib -Itest test/test_{name}.rb`.",
        "c": "Run the visible tests with `mkdir -p build && gcc -std=c11 -Wall -Wextra -Iinclude -Isrc -o build/tests $(find src tests -name '*.c') && ./build/tests`.",
        "bash": "Run the visible checks with `bash tests/run.sh COMMAND`.",
    }[lang]


LANG_NAME = {"python": "Python", "javascript": "JavaScript", "go": "Go", "rust": "Rust", "java": "Java", "ruby": "Ruby", "c": "C", "bash": "Bash"}


# ---------------------------------------------------------------------------------------------------------------
# prompts
# ---------------------------------------------------------------------------------------------------------------

def pick(rng: random.Random, seq):
    return seq[rng.randrange(len(seq))]


CLOSERS = [
    "No third-party packages are available.",
    "Standard library only.",
    "Keep it dependency-free.",
    "",
    "",
    "Please don't edit the files under the test directory.",
    "Run the visible tests before you call it done; there are more checks than the ones you can see.",
    "The README is the contract; hidden checks follow it exactly.",
]


def closer(rng: random.Random) -> str:
    return pick(rng, CLOSERS)


# ---------------------------------------------------------------------------------------------------------------
# task factories
# ---------------------------------------------------------------------------------------------------------------

def _want_fixture_files(tree_start: dict[str, str]) -> dict[str, str]:
    return tree_start


def lib_task(*, api: Api, lang: str, readme: str, solutions: dict[str, str], cases: list[tuple], examples: int,
             prompt: str, difficulty: int, slug: str, oracle=None, extra_start: dict[str, str] | None = None,
             tags: list[str] | None = None, notes: dict | None = None, timeout_s: int = 180,
             visible: list[int] | None = None) -> Task:
    """Assemble one lib-mold task.

    ``solutions[lang]`` is the reference solution source for the implementation file; ``cases`` the hidden cases
    (the first ``examples`` of them are also visible); ``oracle`` an optional callable ``(args...) -> str`` computing
    expected values independently (cross-check for ports and python solutions alike).
    """
    sk = skeleton(api, lang)
    st = stub(api, lang)
    start = merged(sk, st, {"README.md": readme}, extra_start or {})
    sol_tree = merged(start, {api.path(lang): solutions[lang]})
    want = record_lib(api, lang, sol_tree, cases)
    if oracle is not None:
        crosscheck(f"{api.mod} [{lang}] {slug}", want, [oracle(*c) for c in cases], cases)
    vis = visible if visible is not None else list(range(min(examples, len(cases))))
    start_tests = test_files(api, lang, [cases[i] for i in vis], [want[i] for i in vis])
    hidden = test_files(api, lang, cases, want)
    start = merged(start, start_tests)
    return Task(
        prompt=prompt, difficulty=difficulty, slug=slug, lang=lang, start=start, hidden=hidden,
        solution={api.path(lang): solutions[lang]}, verify=verify_cmd(lang), tags=["greenfield", *(tags or [])],
        notes=notes or {}, timeout_s=timeout_s,
    )


def cli_task(*, spec: CliSpec, lang: str, readme: str, solutions: dict[str, str], cases: list[CliCase], examples: int,
             prompt: str, difficulty: int, slug: str, oracle=None, extra_start: dict[str, str] | None = None,
             tags: list[str] | None = None, notes: dict | None = None, timeout_s: int = 180) -> Task:
    """Assemble one cli-mold task. ``oracle(case) -> (stdout, code)`` optionally cross-checks the reference; when the
    family also ships a Python solution (``solutions["python"]``) and ``lang`` is not python, that solution is run on
    the same cases and must agree with the port."""
    start = merged(spec.skeleton(lang), spec.stub(lang), {"README.md": readme}, extra_start or {})
    sol_tree = merged(start, {spec.path(lang): solutions[lang]})
    want = record_cli(spec, lang, sol_tree, cases)
    refs = []
    if oracle is not None:
        refs.append(("oracle", [oracle(c) for c in cases]))
    if lang != "python" and "python" in solutions:
        pt = merged(spec.skeleton("python"), spec.stub("python"), extra_start or {}, {spec.path("python"): solutions["python"]})
        refs.append(("python solution", record_cli(spec, "python", pt, cases)))
    for label, o in refs:
        for i, (g, w) in enumerate(zip(want, o)):
            if (g[0].rstrip("\n"), g[1]) != (w[0].rstrip("\n"), w[1]):
                raise RecordError(f"{spec.tool} [{lang}] {slug}: port and {label} disagree on case {i}: {cases[i]!r}\n port:   {g!r}\n ref:    {w!r}")
    # final newlines are not compared by the harness, but record them as the solution printed them
    start = merged(start, cli_tests(cases[:examples], want[:examples]))
    hidden = cli_tests(cases, want)
    return Task(
        prompt=prompt, difficulty=difficulty, slug=slug, lang=lang, start=start, hidden=hidden,
        solution={spec.path(lang): solutions[lang]}, verify=spec.verify(lang), tags=["greenfield", *(tags or [])],
        notes=notes or {}, timeout_s=timeout_s,
    )


def subst(src: str, **kw) -> str:
    """Replace ``@NAME@`` markers in a solution template."""
    for k, v in kw.items():
        src = src.replace(f"@{k}@", str(v))
    left = re.findall(r"@[A-Z][A-Z0-9_]*@", src)
    if left:
        raise ValueError(f"unfilled template markers: {sorted(set(left))}")
    return src


def uniq_cases(cases: list) -> list:
    seen, out = set(), []
    for c in cases:
        k = c.key() if hasattr(c, "key") else c
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out
