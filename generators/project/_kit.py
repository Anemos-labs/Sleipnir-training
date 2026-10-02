"""Shared scaffolding for the `project` families: long-horizon builds whose deliverable is a command-line program.

Every task in this category has the same shape:

* the agent starts from a README (the specification, 100-300 lines), a stub program that exits with an error, the build
  files of the language, and a handful of visible example checks (`tests/run_examples.py` + `tests/examples.json`);
* the hidden verifier is `tests/run_checks.py` + `tests/checks.json`: dozens of *cases* (command line, stdin, input
  files, expected stdout, exit code, expected output files) grouped by feature.  The score is the mean, over groups, of
  the share of cases that pass; the reference solution scores exactly 1.0, the stub 0.0 (`pass_mode="json-score"`);
* expected values are never typed by hand.  They are recorded from the **Python oracle** (the Python implementation of
  the family, run on the very same cases).  A solution in another language is then *proven* against the oracle by
  running the real hidden checks against it at generation time: if two independent implementations of the README
  disagree, the build fails instead of shipping an unfair task.

Reference solutions live as ordinary source files under `generators/project/_src/<theme>/<lang>/...` (laid out exactly as
in the task repository, so they can be compiled and run by hand); only the generated constants file of each instance
(`render_config`) is produced here.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from fx import Task, langs, merged, run

SRC = Path(__file__).with_name("_src")
CACHE = Path(os.environ.get("FX_CACHE", Path.home() / ".cache" / "fx")) / "proj"

LANG_NAME = {"python": "Python", "javascript": "JavaScript", "go": "Go", "rust": "Rust", "java": "Java"}

VISIBLE_HARNESS = "tests/run_examples.py"
VISIBLE_CASES = "tests/examples.json"
HIDDEN_HARNESS = "tests/run_checks.py"
HIDDEN_CASES = "tests/checks.json"
VERIFY = f"python3 {HIDDEN_HARNESS}"


class BuildError(RuntimeError):
    pass


# ---------------------------------------------------------------------------------------------------------------
# language layout
# ---------------------------------------------------------------------------------------------------------------

def entry_path(lang: str, tool: str) -> str:
    return {"python": f"src/{tool}.py", "javascript": f"src/{tool}.js", "go": "main.go", "rust": "src/main.rs", "java": "src/Main.java"}[lang]


def build_cmd(lang: str, tool: str) -> str:
    return {
        "python": "",
        "javascript": "",
        "go": f"go build -o build/{tool} .",
        "rust": "cargo build --offline --quiet",
        "java": "rm -rf build && mkdir -p build && javac -d build $(find src -name '*.java')",
    }[lang]


def run_argv(lang: str, tool: str) -> list[str]:
    """argv of the program; entries starting with ``@/`` are relative to the repository root."""
    return {
        "python": ["python3", f"@/src/{tool}.py"],
        "javascript": ["node", f"@/src/{tool}.js"],
        "go": [f"@/build/{tool}"],
        "rust": [f"@/target/debug/{tool}"],
        "java": ["java", "-cp", "@/build", "Main"],
    }[lang]


def how_to_run(lang: str, tool: str) -> str:
    return {
        "python": f"`python3 src/{tool}.py` (entry point `src/{tool}.py`; other modules go next to it in `src/`)",
        "javascript": f"`node src/{tool}.js` (entry point `src/{tool}.js`, CommonJS; other modules go next to it in `src/`)",
        "go": f"`build/{tool}`, built with `go build -o build/{tool} .` (package `main` in the module root; `go.mod` is provided, standard library only)",
        "rust": f"`target/debug/{tool}`, built with `cargo build --offline` (binary crate `{tool}`, entry point `src/main.rs`, no dependencies)",
        "java": "`java -cp build Main`, built with `javac -d build $(find src -name '*.java')` (class `Main` in the default package, entry point `src/Main.java`; more classes go in `src/` too)",
    }[lang]


def skeleton(lang: str, tool: str) -> dict[str, str]:
    f: dict[str, str] = {}
    g = {"python": "__pycache__/\n*.pyc\n", "javascript": "node_modules/\n", "go": "build/\n", "rust": "target/\n", "java": "build/\n"}[lang]
    f[".gitignore"] = g
    if lang == "go":
        f["go.mod"] = langs.go_mod(tool)
    if lang == "rust":
        f["Cargo.toml"] = langs.cargo_toml(tool)
    return f


def stub(lang: str, tool: str) -> dict[str, str]:
    msg = "not implemented: see README.md"
    body = {
        "python": f"import sys\n\n\ndef main():\n    sys.stderr.write(\"{msg}\\n\")\n    return 2\n\n\nif __name__ == \"__main__\":\n    sys.exit(main())\n",
        "javascript": f"'use strict';\nprocess.stderr.write('{msg}\\n');\nprocess.exit(2);\n",
        "go": f"package main\n\nimport (\n\t\"fmt\"\n\t\"os\"\n)\n\nfunc main() {{\n\tfmt.Fprintln(os.Stderr, \"{msg}\")\n\tos.Exit(2)\n}}\n",
        "rust": f"fn main() {{\n    eprintln!(\"{msg}\");\n    std::process::exit(2);\n}}\n",
        "java": f"public class Main {{\n    public static void main(String[] args) {{\n        System.err.println(\"{msg}\");\n        System.exit(2);\n    }}\n}}\n",
    }[lang]
    return {entry_path(lang, tool): body}


GENERIC_ENTRY = {"python": "src/main.py", "javascript": "src/main.js"}


def load_src(theme: str, lang: str, tool: str) -> dict[str, str]:
    """The static reference sources of a theme/language, keyed by repository path.  A python/javascript entry file is
    stored as ``src/main.<ext>`` and installed as ``src/<tool>.<ext>``."""
    root = SRC / theme / lang
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith((".pyc", ".class")):
            rel = p.relative_to(root).as_posix()
            if GENERIC_ENTRY.get(lang) == rel:
                rel = entry_path(lang, tool)
            out[rel] = p.read_text(encoding="utf-8")
    if not out:
        raise BuildError(f"no sources under {root}")
    return out


# ---------------------------------------------------------------------------------------------------------------
# generated constants file
# ---------------------------------------------------------------------------------------------------------------

def _lit(lang: str, v) -> tuple[str, str]:
    """(type, literal) of a value for ``lang``; types are only meaningful for go/rust/java."""
    if isinstance(v, bool):
        return "bool", ("True" if v else "False") if lang == "python" else ("true" if v else "false")
    if isinstance(v, int):
        return "int", str(v)
    if isinstance(v, str):
        if lang == "python":
            return "str", json.dumps(v)
        return "str", json.dumps(v)
    if isinstance(v, (list, tuple)):
        if all(isinstance(x, str) for x in v):
            return "strs", "[" + ", ".join(json.dumps(x) for x in v) + "]"
        if all(isinstance(x, int) and not isinstance(x, bool) for x in v):
            return "ints", "[" + ", ".join(str(x) for x in v) + "]"
    raise BuildError(f"unsupported config value {v!r}")


def render_config(lang: str, cfg: dict) -> dict[str, str]:
    """The generated constants file of one instance: ``{path: text}`` (config.py / config.js / config.go / src/config.rs /
    src/Config.java).  Values: bool, int, str, list of str, list of int."""
    items = list(cfg.items())
    if lang == "python":
        body = '"""Constants of this build; the rules they stand for are in README.md."""\n\n'
        for k, v in items:
            body += f"{k} = {_lit('python', v)[1]}\n"
        return {"src/config.py": body}
    if lang == "javascript":
        body = "'use strict';\n// Constants of this build; the rules they stand for are in README.md.\nmodule.exports = Object.freeze({\n"
        for k, v in items:
            body += f"  {k}: {json.dumps(list(v) if isinstance(v, tuple) else v)},\n"
        return {"src/config.js": body + "});\n"}
    if lang == "go":
        body = "package main\n\n// Constants of this build; the rules they stand for are in README.md.\n\n"
        for k, v in items:
            t, lit = _lit("go", v)
            if t in ("bool", "int", "str"):
                body += f"const {k} = {lit}\n"
            elif t == "strs":
                body += f"var {k} = []string{{{lit[1:-1]}}}\n"
            else:
                body += f"var {k} = []int{{{lit[1:-1]}}}\n"
        return {"config.go": body}
    if lang == "rust":
        body = "#![allow(dead_code)]\n//! Constants of this build; the rules they stand for are in README.md.\n\n"
        for k, v in items:
            t, lit = _lit("rust", v)
            if t == "bool":
                body += f"pub const {k}: bool = {lit};\n"
            elif t == "int":
                body += f"pub const {k}: i64 = {lit};\n"
            elif t == "str":
                body += f"pub const {k}: &str = {lit};\n"
            elif t == "strs":
                body += f"pub const {k}: &[&str] = &[{lit[1:-1]}];\n"
            else:
                body += f"pub const {k}: &[i64] = &[{lit[1:-1]}];\n"
        return {"src/config.rs": body}
    if lang == "java":
        body = "// Constants of this build; the rules they stand for are in README.md.\nfinal class Config {\n    private Config() {}\n\n"
        for k, v in items:
            t, lit = _lit("java", v)
            if t == "bool":
                body += f"    static final boolean {k} = {lit};\n"
            elif t == "int":
                body += f"    static final int {k} = {lit};\n"
            elif t == "str":
                body += f"    static final String {k} = {lit};\n"
            elif t == "strs":
                body += f"    static final String[] {k} = {{{lit[1:-1]}}};\n"
            else:
                body += f"    static final int[] {k} = {{{lit[1:-1]}}};\n"
        return {"src/Config.java": body + "}\n"}
    raise BuildError(lang)


# ---------------------------------------------------------------------------------------------------------------
# cases and the check harness
# ---------------------------------------------------------------------------------------------------------------

@dataclass
class Case:
    name: str
    group: str
    args: list[str] = field(default_factory=list)
    stdin: str = ""
    files: dict[str, str] = field(default_factory=dict)  # written into the working directory before the run
    watch: list[str] = field(default_factory=list)  # files whose final content is part of the expectation
    visible: bool = False  # shipped as an example (README + tests/examples.json)
    static: dict | None = None  # {"path": file, "forbid": regex, "require": regex}: passes unless the file matches `forbid` or lacks `require` (no program is run)

    def inputs(self) -> dict:
        d = {"name": self.name, "group": self.group, "args": list(self.args), "stdin": self.stdin, "files": dict(self.files), "watch": list(self.watch)}
        if self.static:
            d["static"] = dict(self.static)
        return d


@dataclass
class Rec:
    stdout: str
    code: int
    files: dict
    stderr: str = ""


HARNESS = r'''#!/usr/bin/env python3
"""__DOC__"""
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "tests", "__CASES__")
BUILD = __BUILD__
RUN = [(ROOT + "/" + p[2:]) if p.startswith("@/") else p for p in __RUN__]
TIMEOUT = 30
WORKERS = 3


def build():
    if not BUILD:
        return True
    r = subprocess.run(["bash", "-c", BUILD], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print("BUILD FAILED")
        print((r.stdout + r.stderr)[-3000:])
        return False
    return True


def execute(c):
    if c.get("static"):
        fp = os.path.join(ROOT, c["static"]["path"])
        text = open(fp, encoding="utf-8", errors="replace").read() if os.path.isfile(fp) else ""
        hits = sorted(set(re.findall(c["static"]["forbid"], text)))[:3]
        need = c["static"].get("require")
        return {"stdout": "", "code": 0, "files": {}, "stderr": "", "hits": hits, "missing": bool(need and not re.search(need, text))}
    d = tempfile.mkdtemp(prefix="chk-")
    try:
        for p, t in sorted(c.get("files", {}).items()):
            fp = os.path.join(d, p)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8", newline="") as f:
                f.write(t)
        try:
            r = subprocess.run(RUN + list(c.get("args", [])), input=c.get("stdin", "").encode(), cwd=d, capture_output=True, timeout=TIMEOUT)
            out = r.stdout.decode("utf-8", "replace").replace("\r\n", "\n")
            err = r.stderr.decode("utf-8", "replace")
            code = r.returncode
        except subprocess.TimeoutExpired:
            out, err, code = "", "timed out after %d s" % TIMEOUT, 124
        files = {}
        for p in c.get("watch", []) or list((c.get("out_files") or {}).keys()):
            fp = os.path.join(d, p)
            files[p] = open(fp, encoding="utf-8", newline="").read() if os.path.isfile(fp) else None
        return {"stdout": out, "code": code, "files": files, "stderr": err[-600:]}
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def first_diff(got, want):
    g, w = got.split("\n"), want.split("\n")
    for i in range(max(len(g), len(w))):
        a = g[i] if i < len(g) else "<missing>"
        b = w[i] if i < len(w) else "<missing>"
        if a != b:
            return "line %d:\n      got:  %s\n      want: %s" % (i + 1, a[:200], b[:200])
    return "(no difference found)"


def judge(c, res):
    why = []
    if c.get("static"):
        if res["hits"]:
            why.append("%s still contains %s" % (c["static"]["path"], ", ".join(repr(h) for h in res["hits"])))
        if res.get("missing"):
            why.append("%s does not use the new API" % c["static"]["path"])
        return why
    if res["stdout"].rstrip("\n") != c["stdout"].rstrip("\n"):
        why.append("stdout differs at " + first_diff(res["stdout"].rstrip("\n"), c["stdout"].rstrip("\n")))
    if res["code"] != c.get("code", 0):
        why.append("exit code %s, expected %s" % (res["code"], c.get("code", 0)))
        if res["stderr"].strip():
            why.append("stderr: " + res["stderr"].strip().replace("\n", " | ")[-300:])
    for p, want in sorted((c.get("out_files") or {}).items()):
        got = res["files"].get(p)
        if got != want:
            if want is None:
                why.append("file %s should not exist" % p)
            elif got is None:
                why.append("file %s was not written" % p)
            else:
                why.append("file %s differs at " % p + first_diff(got.rstrip("\n"), want.rstrip("\n")))
    return why


def main(argv):
    cases = json.load(open(CASES, encoding="utf-8"))
    if "--record" in argv:
        out = argv[argv.index("--record") + 1]
        if not build():
            return 3
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            results = list(ex.map(execute, cases))
        with open(out, "w", encoding="utf-8") as f:
            json.dump(results, f)
        return 0
    verbose = "-v" in argv
    pick = [a for a in argv if not a.startswith("-")]
    if pick:
        cases = [c for c in cases if any(s in c["name"] or s == c["group"] for s in pick)]
    if not build():
        print(json.dumps({"score": 0.0}))
        return 1
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        results = list(ex.map(execute, cases))
    groups = {}
    shown = 0
    for c, res in zip(cases, results):
        why = judge(c, res)
        groups.setdefault(c["group"], []).append(not why)
        if why and (verbose or shown < 6):
            shown += 1
            print("FAIL [%s] %s" % (c["group"], c["name"]))
            if c.get("args"):
                print("    args: " + " ".join(c["args"]))
            for w in why:
                print("    " + w)
    total = sum(len(v) for v in groups.values())
    passed = sum(sum(v) for v in groups.values())
    for g, v in groups.items():
        print("  %-22s %d/%d" % (g, sum(v), len(v)))
    score = sum(sum(v) / len(v) for v in groups.values()) / len(groups) if groups else 0.0
    score = 1.0 if passed == total and total else round(score, 4)
    print("%d of %d checks passed" % (passed, total))
    print(json.dumps({"score": score}))
    return 0 if score == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''


def harness_text(lang: str, tool: str, hidden: bool, program: tuple[str, list[str]] | None = None) -> str:
    """``program`` overrides the default (build command, argv) of the language, for repositories with another layout."""
    cases = HIDDEN_CASES if hidden else VISIBLE_CASES
    doc = ("Hidden checks: build the program, run every case, print the score." if hidden else
           "Example checks: python3 tests/run_examples.py [-v] [group-or-name-fragment]  (builds the program first)")
    b, argv = program if program else (build_cmd(lang, tool), run_argv(lang, tool))
    return (HARNESS.replace("__DOC__", doc).replace("__CASES__", cases.split("/")[-1])
            .replace("__BUILD__", json.dumps(b)).replace("__RUN__", json.dumps(argv)))


def _cases_json(cases: list[Case], recs: list[Rec]) -> str:
    rows = []
    for c, r in zip(cases, recs):
        row = {"name": c.name, "group": c.group, "args": c.args, "stdin": c.stdin, "files": c.files, "stdout": r.stdout, "code": r.code}
        if c.static:
            row["static"] = c.static
        if c.watch:
            row["out_files"] = {p: r.files.get(p) for p in c.watch}
        rows.append({k: v for k, v in row.items() if v not in ({}, [], "") or k in ("stdout", "code", "name", "group")})
    return json.dumps(rows, indent=0, ensure_ascii=True, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# recording the oracle
# ---------------------------------------------------------------------------------------------------------------

def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if not any(s in k for s in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
    env.update(PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", LC_ALL="C.UTF-8", TZ="UTC", NO_COLOR="1")
    return env


def record(tree: dict[str, str], tool: str, cases: list[Case], lang: str = "python", timeout: int = 600, program=None) -> list[Rec]:
    """Run ``tree`` (a complete repository in ``lang``) on the cases through the recording harness; return what it printed."""
    key_src = json.dumps([sorted(tree.items()), [c.inputs() for c in cases], lang, program], sort_keys=True)
    key = hashlib.sha256(key_src.encode()).hexdigest()
    cf = CACHE / key[:2] / f"{key}.json"
    if cf.exists():
        try:
            return [Rec(**d) for d in json.loads(cf.read_text())]
        except Exception:  # noqa: BLE001
            pass
    tmp = tempfile.mkdtemp(prefix="projrec-")
    try:
        root = Path(tmp) / "w"
        root.mkdir()
        files = dict(tree)
        files["tests/_record.py"] = harness_text(lang, tool, True, program)
        files[HIDDEN_CASES] = json.dumps([c.inputs() for c in cases])
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        outp = Path(tmp) / "out.json"
        env = _env()
        env.update(GOFLAGS="-mod=mod", GOTOOLCHAIN="local", GOPROXY="off", CARGO_NET_OFFLINE="true", TMPDIR=tmp)
        p = subprocess.run(["python3", "tests/_record.py", "--record", str(outp)], cwd=root, env=env, capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0 or not outp.exists():
            raise BuildError(f"recording the {lang} reference failed:\n{(p.stdout + p.stderr)[-2500:]}")
        raw = json.loads(outp.read_text())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    recs = [Rec(stdout=d["stdout"], code=d["code"], files=d["files"], stderr=d.get("stderr", "")) for d in raw]
    for c, r in zip(cases, recs):
        if r.code not in (0, 1, 2) or "Traceback" in r.stderr or "panicked" in r.stderr or "Exception in thread" in r.stderr:
            raise BuildError(f"the oracle crashed on case {c.name}: exit {r.code}\n{r.stderr}\nargs={c.args} stdin={c.stdin[:600]!r}")
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps([r.__dict__ for r in recs]))
    return recs


def oracle_runner(tool: str, py_solution: dict[str, str]):
    """A function ``cases -> [Rec]`` that runs the Python oracle (for choosing cases by what the oracle answers)."""
    tree = merged(skeleton("python", tool), stub("python", tool), py_solution)

    def run_cases(cases: list[Case]) -> list[Rec]:
        return record(tree, tool, cases, "python")

    return run_cases


def probe(py_solution: dict[str, str], tool: str, code: str, payload, timeout: int = 300):
    """Run ``code`` (python source) with the oracle's ``src/`` importable and the working directory at the repository root;
    ``payload`` is given as JSON on standard input and the JSON printed on standard output comes back.  This lets a generator
    ask the oracle about *how* it answers (for example how much it had to backtrack) when choosing cases."""
    key = hashlib.sha256(json.dumps([sorted(py_solution.items()), code, payload], sort_keys=True).encode()).hexdigest()
    cf = CACHE / "probe" / f"{key}.json"
    if cf.exists():
        return json.loads(cf.read_text())
    tmp = tempfile.mkdtemp(prefix="projprobe-")
    try:
        root = Path(tmp) / "w"
        for rel, text in merged(skeleton("python", tool), stub("python", tool), py_solution).items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        env = _env()
        env["TMPDIR"] = tmp
        r = subprocess.run(["python3", "-c", code], cwd=root, env=env, input=json.dumps(payload), capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise BuildError("probe failed:\n" + (r.stdout + r.stderr)[-2500:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps(out))
    return out


def parse_score(out: str) -> float | None:
    for ln in reversed(out.strip().splitlines()):
        ln = ln.strip()
        if ln.startswith("{") and '"score"' in ln:
            try:
                return float(json.loads(ln)["score"])
            except Exception:  # noqa: BLE001
                return None
    return None


# ---------------------------------------------------------------------------------------------------------------
# README helpers
# ---------------------------------------------------------------------------------------------------------------

def fence(s: str, info: str = "") -> str:
    s = s if s.endswith("\n") else s + "\n"
    return f"```{info}\n{s}```\n"


def show_case(tool: str, c: Case, r: Rec, files_label: str = "files") -> str:
    """A README example: how the program is invoked, what it reads, what it prints."""
    parts = []
    cmd = " ".join([tool] + [shlex.quote(a) for a in c.args])
    if c.files:
        for p in sorted(c.files):
            parts.append(f"{files_label} {p}:\n" + fence(c.files[p]))
    if c.stdin:
        parts.append(f"`{cmd}` reading this on standard input:\n\n" + fence(c.stdin))
    else:
        parts.append(f"`{cmd}`:\n")
    out = r.stdout if r.stdout.endswith("\n") or not r.stdout else r.stdout + "\n"
    parts.append("prints:\n\n" + fence(out if out else "(nothing)\n"))
    for p in c.watch:
        v = r.files.get(p)
        parts.append(f"and leaves `{p}` " + ("absent.\n" if v is None else "containing:\n\n" + fence(v)))
    if r.code:
        parts.append(f"and exits with status {r.code}.\n")
    return "\n".join(parts)


def pick(rng: random.Random, seq):
    return seq[rng.randrange(len(seq))]


def lang_phrase(lang: str) -> str:
    return LANG_NAME[lang]


# ---------------------------------------------------------------------------------------------------------------
# task assembly
# ---------------------------------------------------------------------------------------------------------------

def project_task(*, theme: str, tool: str, lang: str, cases: list[Case], solution: dict[str, str], py_solution: dict[str, str],
                 readme, prompt: str, difficulty: int, slug: str, notes: dict | None = None, extra_start: dict[str, str] | None = None,
                 tags: list[str] | None = None, timeout_s: int = 300, protected: list[str] | None = None) -> Task:
    """Assemble one task.

    ``solution`` / ``py_solution`` are the complete reference sources (``{path: text}``, constants file included) in the
    task language and in Python; ``readme(recs_by_name)`` renders the README once the oracle has been recorded."""
    names = [c.name for c in cases]
    if len(set(names)) != len(names):
        raise BuildError(f"{slug}: duplicate case names")
    py_tree = merged(skeleton("python", tool), stub("python", tool), py_solution)
    recs = record(py_tree, tool, cases, "python")
    by_name = {c.name: (c, r) for c, r in zip(cases, recs)}
    vis = [(c, r) for c, r in zip(cases, recs) if c.visible]
    if not vis:
        raise BuildError(f"{slug}: no visible examples")
    readme_text = readme(by_name)
    start = merged(skeleton(lang, tool), stub(lang, tool), {"README.md": readme_text}, extra_start or {},
                   {VISIBLE_HARNESS: harness_text(lang, tool, False), VISIBLE_CASES: _cases_json([c for c, _ in vis], [r for _, r in vis])})
    hidden = {HIDDEN_HARNESS: harness_text(lang, tool, True), HIDDEN_CASES: _cases_json(cases, recs)}
    sol = {p: t for p, t in solution.items()}
    # prove the reference solution against the recorded expectations (a port is thereby proven against the oracle)
    full = merged(start, hidden, sol)
    r = run(full, VERIFY, timeout=timeout_s)
    sc = parse_score(r.out)
    if not r.ok or sc != 1.0:
        raise BuildError(f"{slug} [{lang}]: the reference solution does not pass the recorded checks (exit {r.code}, score {sc}):\n{r.out[-3500:]}")
    return Task(prompt=prompt, difficulty=difficulty, slug=slug, lang=lang, kind="greenfield", start=start, hidden=hidden, solution=sol,
                verify=VERIFY, pass_mode="json-score", tags=["project", *(tags or [])], notes=notes or {}, timeout_s=timeout_s,
                protected=protected or [])


def codemod_task(*, start: dict[str, str], solution: dict[str, str], hidden_extra: dict[str, str], cases: list[Case], program: tuple[str, list[str]],
                 lang: str, tool: str, prompt: str, difficulty: int, slug: str, notes: dict | None = None, tags: list[str] | None = None,
                 timeout_s: int = 300, protected: list[str] | None = None) -> Task:
    """A migration task: ``start`` is the working, unmigrated repository (README included); ``hidden_extra`` replaces the legacy
    module with a poisoned one at verification time; the expectations are what the *unmigrated* repository prints on the
    cases (static cases need none); the reference solution (``solution``: the migrated files) must reproduce them."""
    names = [c.name for c in cases]
    if len(set(names)) != len(names):
        raise BuildError(f"{slug}: duplicate case names")
    run_cases = [c for c in cases if not c.static]
    recs_run = record(merged(start, {}), tool, run_cases, lang, program=program)
    by = {c.name: r for c, r in zip(run_cases, recs_run)}
    recs = [by.get(c.name, Rec(stdout="", code=0, files={})) for c in cases]
    for c, r in zip(cases, recs):
        if not c.static and r.code != 0:
            raise BuildError(f"{slug}: the unmigrated repository fails case {c.name}: {r.stdout[-400:]} {r.stderr[-400:]}")
    vis = [(c, r) for c, r in zip(cases, recs) if c.visible]
    start_full = merged(start, {VISIBLE_HARNESS: harness_text(lang, tool, False, program), VISIBLE_CASES: _cases_json([c for c, _ in vis], [r for _, r in vis])})
    hidden = merged({HIDDEN_HARNESS: harness_text(lang, tool, True, program), HIDDEN_CASES: _cases_json(cases, recs)}, hidden_extra)
    full = merged(start_full, hidden, solution)
    r = run(full, VERIFY, timeout=timeout_s)
    sc = parse_score(r.out)
    if not r.ok or sc != 1.0:
        raise BuildError(f"{slug} [{lang}]: the reference migration does not pass the checks (exit {r.code}, score {sc}):\n{r.out[-3500:]}")
    st = run(merged(start_full, hidden), VERIFY, timeout=timeout_s)
    ssc = parse_score(st.out)
    if st.ok or ssc is None or ssc >= 1.0:
        raise BuildError(f"{slug}: the unmigrated repository passes the hidden checks (score {ssc})")
    return Task(prompt=prompt, difficulty=difficulty, slug=slug, lang=lang, kind="refactor", start=start_full, hidden=hidden, solution=solution,
                verify=VERIFY, pass_mode="json-score", tags=["project", "migration", *(tags or [])], notes=notes or {}, timeout_s=timeout_s,
                protected=protected or [])
