"""Shared machinery for the `shell` category: data-driven scenarios run against the agent's script (or Makefile).

A *scenario* is a small world: a tree of fixture files (awkward names welcome), then one or more runs of the script
(arguments, stdin, environment, between-run operations such as `touch`). The expected stdout, exit status and resulting
tree of every scenario are produced at generation time by running the reference solution with exactly the harness that
the hidden checker uses (`HARNESS_SRC` below is both executed here and written to `tests/shx.py`).

    start/   README.md (with a generated example), the stub or buggy script, extra files
    hidden/  tests/check_shell.py, tests/shx.py, tests/spec.json (scenarios and expectations)

Scenario format (JSON):

    {"name": "...",
     "files": {"path": {"t": "f", "c": "text", "m": 1700000000, "x": false} | {"t": "d"} | {"t": "l", "to": "target"}},
     "runs": [{"args": [...], "stdin": "...", "env": {...}, "cwd": ".", "ops": [{"op": "touch|write|rm|mkdir|chmod", ...}],
               "stdout": "exact|sorted|ignore", "rc": true, "stderr": "ignore|empty|nonempty"}],
     "mtimes": ["paths whose mtime is part of the expected tree"], "dirs": "empty|all|none"}
"""
from __future__ import annotations

import json
import os
import random
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Callable

from fx import Task, merged, run

HARNESS_SRC = r'''
import difflib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile

EPOCH = 1700000000


def apply_tree(box, tree):
    for path, ent in tree.items():
        full = os.path.join(box, path)
        t = ent.get("t", "f")
        if t == "d":
            os.makedirs(full, exist_ok=True)
        elif t == "l":
            os.makedirs(os.path.dirname(full), exist_ok=True)
            os.symlink(ent["to"], full)
        else:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as f:
                f.write(ent.get("c", "").encode("utf-8"))
            os.chmod(full, 0o755 if ent.get("x") else 0o644)
            os.utime(full, (ent.get("m", EPOCH), ent.get("m", EPOCH)))


def apply_ops(box, ops):
    for op in ops:
        full = os.path.join(box, op["path"])
        kind = op["op"]
        if kind == "write":
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as f:
                f.write(op.get("c", "").encode("utf-8"))
            if "m" in op:
                os.utime(full, (op["m"], op["m"]))
        elif kind == "touch":
            os.utime(full, (op["m"], op["m"]))
        elif kind == "rm":
            if os.path.isdir(full) and not os.path.islink(full):
                shutil.rmtree(full)
            elif os.path.lexists(full):
                os.remove(full)
        elif kind == "mkdir":
            os.makedirs(full, exist_ok=True)
        elif kind == "chmod":
            os.chmod(full, op["mode"])


def snapshot(box, mtimes, dirs):
    out = {}
    for d, dirnames, files in os.walk(box):
        dirnames.sort()
        rel = os.path.relpath(d, box)
        for dn in list(dirnames):
            p = os.path.join(d, dn)
            r = os.path.normpath(os.path.join(rel, dn))
            if os.path.islink(p):
                out[r] = {"t": "l", "to": os.readlink(p)}
                dirnames.remove(dn)
            elif dirs == "all" or (dirs == "empty" and not os.listdir(p)):
                out[r] = {"t": "d"}
        for fn in files:
            p = os.path.join(d, fn)
            r = os.path.normpath(os.path.join(rel, fn))
            if os.path.islink(p):
                out[r] = {"t": "l", "to": os.readlink(p)}
                continue
            with open(p, "rb") as fh:
                ent = {"t": "f", "c": fh.read().decode("utf-8", "replace")}
            if os.access(p, os.X_OK):
                ent["x"] = True
            if r in mtimes:
                ent["m"] = int(os.stat(p).st_mtime)
            out[r] = ent
    return out


def run_scenario(repo, spec, scn, timeout=20):
    tmp = tempfile.mkdtemp(prefix="shx-")
    box = os.path.join(tmp, "box")
    os.makedirs(box)
    try:
        apply_tree(box, scn.get("files", {}))
        script = os.path.join(repo, spec["script"])
        if spec.get("kind") == "make":
            shutil.copyfile(script, os.path.join(box, "Makefile"))
        results = []
        for r in scn["runs"]:
            apply_ops(box, r.get("ops", []))
            if spec.get("kind") == "make":
                argv = ["make", "--no-print-directory"] + list(r.get("args", []))
            else:
                argv = [spec.get("shell", "bash"), script] + list(r.get("args", []))
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tmp, "LC_ALL": "C.UTF-8", "TZ": "UTC", "USER": "tester"}
            env.update(r.get("env", {}))
            cwd = os.path.join(box, r.get("cwd", "."))
            p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                out, err = p.communicate(r.get("stdin", "").encode("utf-8"), timeout=timeout)
                rc = p.returncode
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                out, err = p.communicate()
                rc = 124
            results.append({"rc": rc, "stdout": out.decode("utf-8", "replace"), "stderr": err.decode("utf-8", "replace")})
        tree = snapshot(box, set(scn.get("mtimes", [])), scn.get("dirs", "empty"))
        return results, tree
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _lines(s):
    return s.split("\n")


def short_diff(got, want, label):
    d = list(difflib.unified_diff(_lines(want), _lines(got), "expected", "got", lineterm="", n=0))
    d = [l for l in d if not l.startswith(("---", "+++", "@@"))]
    return label + ":\n    " + "\n    ".join(l[:160] for l in d[:8]) + ("\n    ..." if len(d) > 8 else "")


def compare(scn, results, tree, expected):
    problems = []
    for i, (r, e, cfg) in enumerate(zip(results, expected["runs"], scn["runs"])):
        tag = f"run {i + 1}" if len(results) > 1 else "run"
        if cfg.get("rc", True) and r["rc"] != e["rc"]:
            problems.append(f"{tag}: exit status {r['rc']}, expected {e['rc']}" + (f" (stderr: {r['stderr'].strip().splitlines()[-1][:160]})" if r["stderr"].strip() else ""))
        mode = cfg.get("stdout", "exact")
        if mode != "ignore":
            g, w = r["stdout"], e["stdout"]
            if mode == "sorted":
                g, w = "\n".join(sorted(g.splitlines())), "\n".join(sorted(w.splitlines()))
            if g != w:
                problems.append(short_diff(g, w, f"{tag}: standard output differs"))
        se = cfg.get("stderr", "ignore")
        if se == "empty" and r["stderr"].strip():
            problems.append(f"{tag}: unexpected output on stderr: {r['stderr'].strip().splitlines()[0][:120]}")
        if se == "nonempty" and not r["stderr"].strip():
            problems.append(f"{tag}: expected a message on stderr")
    want = expected["tree"]
    if tree != want:
        missing = sorted(set(want) - set(tree))
        extra = sorted(set(tree) - set(want))
        changed = sorted(k for k in set(tree) & set(want) if tree[k] != want[k])
        msg = "resulting files differ:"
        if missing:
            msg += f"\n    missing: {[m for m in missing[:5]]}"
        if extra:
            msg += f"\n    unexpected: {[m for m in extra[:5]]}"
        if changed:
            k = changed[0]
            msg += f"\n    content/attributes differ: {k!r}" + (f" (+{len(changed) - 1} more)" if len(changed) > 1 else "")
            if tree[k].get("c") is not None and want[k].get("c") is not None and tree[k].get("c") != want[k].get("c"):
                msg += "\n" + short_diff(tree[k]["c"], want[k]["c"], "    first differing file")
        problems.append(msg)
    return problems


def main(repo=None):
    repo = repo or os.getcwd()
    spec = json.load(open(os.path.join(repo, "tests", "spec.json"), encoding="utf-8"))
    script = os.path.join(repo, spec["script"])
    if not os.path.isfile(script):
        print(f"FAIL: {spec['script']} does not exist")
        sys.exit(1)
    bad = 0
    for scn in spec["scenarios"]:
        results, tree = run_scenario(repo, spec, scn)
        problems = compare(scn, results, tree, scn["expected"])
        if problems:
            bad += 1
            print(f"FAIL scenario {scn['name']!r}:")
            for p in problems:
                print("  " + p)
    if bad:
        print(f"{bad} of {len(spec['scenarios'])} scenarios failed")
        sys.exit(1)
    print(f"ok: {len(spec['scenarios'])} scenarios")
'''

CHECK_SHELL = '''#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
import shx

shx.main()
'''

_NS: dict = {}


def harness():
    if not _NS:
        exec(compile(HARNESS_SRC, "shx.py", "exec"), _NS)
    return _NS


# ----------------------------------------------------------------------------------------------------------------
# scenario builders


def F(text: str = "", m: int | None = None, x: bool = False) -> dict:
    d = {"t": "f", "c": text}
    if m is not None:
        d["m"] = m
    if x:
        d["x"] = True
    return d


def D() -> dict:
    return {"t": "d"}


def L(to: str) -> dict:
    return {"t": "l", "to": to}


def Run(*args, stdin: str = "", env: dict | None = None, cwd: str = ".", ops: list | None = None, stdout: str = "exact", rc: bool = True, stderr: str = "ignore") -> dict:
    r = {"args": list(args)}
    if stdin:
        r["stdin"] = stdin
    if env:
        r["env"] = env
    if cwd != ".":
        r["cwd"] = cwd
    if ops:
        r["ops"] = ops
    if stdout != "exact":
        r["stdout"] = stdout
    if not rc:
        r["rc"] = False
    if stderr != "ignore":
        r["stderr"] = stderr
    return r


def scn(name: str, files: dict, *runs: dict, mtimes: list | None = None, dirs: str = "empty") -> dict:
    s = {"name": name, "files": files, "runs": list(runs) or [Run()]}
    if mtimes:
        s["mtimes"] = list(mtimes)
    if dirs != "empty":
        s["dirs"] = dirs
    return s


def awkward_names(rng: random.Random) -> list[str]:
    """Names that break naive scripts: spaces, leading dashes, unicode, newlines, glob characters, quotes."""
    return rng.sample(["two words.txt", "-dash.txt", "naïve café.txt", "star*.txt", "q?mark.txt", "it's.txt", 'say "hi".txt', "tab\there.txt",
                       "line\nbreak.txt", "[brackets].txt", "dollar$HOME.txt", "back\\slash.txt", "  lead space.txt", "trail space .txt", "semi;colon.txt",
                       "ünï-çødé.log", "(parens).txt", "a&b.txt", "#hash.txt", "~tilde.txt"], 4)


# ----------------------------------------------------------------------------------------------------------------
# specs


@dataclass
class ShellSpec:
    slug: str
    d: int
    prompt: str
    doc: str  # README body
    ref: str  # reference script (or Makefile)
    make: Callable[[random.Random], tuple[dict, list[dict]]]  # (rng) -> (visible example scenario, hidden scenarios)
    script: str = "tidy.sh"
    shell: str = "bash"
    kind: str = "script"  # "script" or "make"
    buggy: str = ""
    wrong: tuple = ()
    oracle: Callable | None = None  # (scenario, results, tree) -> list of problems; independent check of the reference
    extra: dict = field(default_factory=dict)  # additional start files (helper libs, fixtures)
    title: str = ""
    tags: tuple = ()
    lang: str = "bash"
    notes: str = ""


def _fmt_name(n: str) -> str:
    return n.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")


def _render_example(spec: ShellSpec, s: dict, results: list, tree: dict) -> str:
    out = ["## Example", "", "Starting from these files (a `\\n` in a name below stands for a real line break, `\\t` for a tab):", "", "```"]
    for p in sorted(s["files"]):
        e = s["files"][p]
        if e["t"] == "d":
            out.append(_fmt_name(p) + "/")
        elif e["t"] == "l":
            out.append(f"{_fmt_name(p)} -> {e['to']}")
        else:
            body = e.get("c", "")
            first = body.split("\n")[0][:50]
            out.append(f"{_fmt_name(p)}" + (f"    [{first}{'...' if len(body) > len(first) + 1 else ''}]" if body else "    [empty]"))
    out.append("```")
    for r, res in zip(s["runs"], results):
        for op in r.get("ops", []):
            out.append(f"\n(then: {op['op']} `{_fmt_name(op['path'])}`)")
        shell = spec.shell if spec.kind == "script" else "make"
        cmd = (f"{shell} {spec.script} " if spec.kind == "script" else "make ") + " ".join(_q(a) for a in r.get("args", []))
        out += ["", f"running `{cmd.strip()}`" + (" with this on standard input:" if r.get("stdin") else ""), ""]
        if r.get("stdin"):
            out += ["```", r["stdin"].rstrip("\n"), "```", ""]
        if res["stdout"].strip():
            out += ["prints:", "", "```", res["stdout"].rstrip("\n"), "```"]
        else:
            out += ["prints nothing."]
        if res["rc"] != 0:
            out += ["", f"and exits with status {res['rc']}."]
    changed = [p for p in sorted(tree) if p not in s["files"] or tree[p] != s["files"][p]]
    gone = [p for p in sorted(s["files"]) if p not in tree and s["files"][p]["t"] != "d"]
    if changed or gone:
        out += ["", "and leaves the directory like this (only differences from the start are listed):", "", "```"]
        for p in gone:
            out.append(f"- {_fmt_name(p)}")
        for p in changed:
            e = tree[p]
            out.append(f"+ {_fmt_name(p)}" + ("/" if e["t"] == "d" else f" -> {e['to']}" if e["t"] == "l" else (f"    [{e.get('c', '').split(chr(10))[0][:50]}]" if e.get("c") else "")))
        out.append("```")
    return "\n".join(out) + "\n"


def _q(a: str) -> str:
    return a if a and all(c.isalnum() or c in "-_./=:,@%+" for c in a) else "'" + a.replace("'", "'\\''") + "'"


def shell_tasks(family_key: str, specs: list[ShellSpec], rng: random.Random, n: int) -> list[Task]:
    H = harness()
    tasks: list[Task] = []
    for si, spec in enumerate(specs[:n]):
        srng = random.Random(rng.random())
        example, hidden_scns = spec.make(srng)
        spec_json = {"script": spec.script, "shell": spec.shell, "kind": spec.kind}
        ref_repo = tempfile.mkdtemp(prefix="shref-")
        try:
            with open(os.path.join(ref_repo, spec.script), "w", encoding="utf-8") as f:
                f.write(spec.ref)
            for k, v in spec.extra.items():
                p = os.path.join(ref_repo, k)
                os.makedirs(os.path.dirname(p) or ref_repo, exist_ok=True)
                open(p, "w", encoding="utf-8").write(v)
            ex_res, ex_tree = H["run_scenario"](ref_repo, spec_json, example)
            built = []
            for s in hidden_scns:
                res, tree = H["run_scenario"](ref_repo, spec_json, s)
                if spec.oracle is not None:
                    probs = spec.oracle(s, res, tree)
                    if probs:
                        raise RuntimeError(f"{spec.slug}: oracle disagrees with the reference on {s['name']}: {probs[:3]}")
                for r in res:
                    if r["rc"] == 124:
                        raise RuntimeError(f"{spec.slug}: reference timed out on {s['name']}")
                s = dict(s)
                s["expected"] = {"runs": [{"rc": r["rc"], "stdout": r["stdout"]} for r in res], "tree": tree}
                built.append(s)
            if spec.oracle is not None:
                probs = spec.oracle(example, ex_res, ex_tree)
                if probs:
                    raise RuntimeError(f"{spec.slug}: oracle disagrees with the reference on the example: {probs[:3]}")
        finally:
            shutil.rmtree(ref_repo, ignore_errors=True)
        spec_json["scenarios"] = built
        readme = f"# {spec.title or family_key}\n\n{spec.doc.strip()}\n\n" + _render_example(spec, example, ex_res, ex_tree)
        if spec.kind == "script":
            readme += (f"\nThe tests run `{spec.shell} {spec.script} ...` in a fresh scratch directory, with a minimal environment "
                       f"(`PATH`, `HOME`, `LC_ALL=C.UTF-8`, `TZ=UTC`); only the working directory and the files it contains matter."
                       f" File names in the real tests are nastier than the example.\n")
        else:
            readme += "\nThe tests copy your `Makefile` into a fresh scratch directory next to the project files and run `make` there, several times when a scenario needs it.\n"
        stub = spec.buggy or (f"#!/usr/bin/env {spec.shell}\n# TODO: see README.md\n" if spec.kind == "script" else "# TODO: see README.md\n")
        start = {"README.md": readme, spec.script: stub.strip("\n") + "\n", **spec.extra}
        hidden = {"tests/check_shell.py": CHECK_SHELL, "tests/shx.py": HARNESS_SRC, "tests/spec.json": json.dumps(spec_json, indent=1, ensure_ascii=False) + "\n"}
        t = Task(slug=f"{si + 1:02d}-{spec.slug}", prompt=spec.prompt.strip(), difficulty=spec.d, start=start, hidden=hidden,
                 solution={spec.script: spec.ref.strip("\n") + "\n"}, verify="python3 tests/check_shell.py", kind="fix" if spec.buggy else "feature",
                 lang=spec.lang, tags=["shell", *spec.tags], notes={"family": family_key, "spec": spec.slug, **({"shell": spec.shell} if spec.shell != "bash" else {})})
        # guards: the start state fails; every `wrong` script fails
        res = run(merged(start, hidden), t.verify, timeout=120, cache=False)
        if res.ok:
            raise RuntimeError(f"{spec.slug}: the start state already passes the checker")
        for wi, w in enumerate(spec.wrong):
            res = run(merged(start, hidden, {spec.script: w.strip("\n") + "\n"}), t.verify, timeout=120, cache=False)
            if res.ok:
                raise RuntimeError(f"{spec.slug}: checker accepted wrong script #{wi}")
        res = run(merged(start, hidden, t.solution), t.verify, timeout=120, cache=False)
        if not res.ok:
            raise RuntimeError(f"{spec.slug}: the reference does not pass its own checker:\n{res.out[-1500:]}")
        tasks.append(t)
    return tasks
