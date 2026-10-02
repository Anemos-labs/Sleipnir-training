"""Shared machinery for the python ETL / wrangling families of the `data` category.

An *ETL spec* is one task: the agent writes (or repairs) a python script that reads files from an input directory and
writes files to an output directory (and/or prints to stdout). The hidden checker runs the script on several hidden
input directories (different from the visible sample) and compares the outputs with the expected ones.

    start/   README.md (the format specification), sample/in/..., sample/expected/..., etl.py (stub or buggy script)
    hidden/  tests/check_etl.py, tests/spec.json, tests/cases/<name>/in/..., tests/cases/<name>/expected/...

Expected outputs are produced at generation time by running the reference script (`ref`) on every input; an optional
``alt`` script (a plausible different implementation, e.g. float rounding instead of decimal) must give identical
outputs, which proves the spec leaves no hidden decision; a ``wrong`` list of scripts must each be rejected by the checker.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Callable

from fx import Task, merged, run

CHECK_ETL = r'''#!/usr/bin/env python3
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

SPEC = json.load(open("tests/spec.json", encoding="utf-8"))


def read_tree(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root).replace(os.sep, "/")] = fh.read().decode("utf-8", "replace")
    return out


def norm_text(s):
    s = s.replace("\r\n", "\n")
    return s if s.endswith("\n") or not s else s + "\n"


def as_json(s):
    return json.loads(s)


def close(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(close(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
    return a == b


def compare(mode, got, want):
    """None if equal, else a short reason."""
    if mode == "text":
        g, w = norm_text(got).split("\n"), norm_text(want).split("\n")
        for i, (x, y) in enumerate(zip(g, w), 1):
            if x != y:
                return f"line {i} differs", (x, y)
        if len(g) != len(w):
            return f"{len(g) - 1} lines, expected {len(w) - 1}", None
        return None
    if mode in ("csv", "csv-set"):
        try:
            g = list(csv.reader(io.StringIO(norm_text(got))))
        except csv.Error as e:
            return f"not valid CSV ({e})", None
        w = list(csv.reader(io.StringIO(norm_text(want))))
        if mode == "csv-set":
            hg, hw = g[:1], w[:1]
            if hg != hw:
                return "header differs", (hg, hw)
            g, w = sorted(g[1:]), sorted(w[1:])
        for i, (x, y) in enumerate(zip(g, w), 1):
            if x != y:
                return f"row {i} differs", (x, y)
        if len(g) != len(w):
            return f"{len(g)} rows, expected {len(w)}", None
        return None
    if mode == "json":
        try:
            g = as_json(got)
        except ValueError as e:
            return f"not valid JSON ({e})", None
        return None if close(g, as_json(want)) else ("JSON content differs", (g, as_json(want)))
    if mode == "lines-set":
        g = sorted(l for l in norm_text(got).split("\n") if l)
        w = sorted(l for l in norm_text(want).split("\n") if l)
        return None if g == w else ("set of lines differs", None)
    raise SystemExit("bad mode " + mode)


def main():
    bad = 0
    for case in SPEC["cases"]:
        name = case["name"]
        base = os.path.join("tests", "cases", name)
        tmp = tempfile.mkdtemp(prefix="etl-")
        try:
            indir, outdir = os.path.join(tmp, "in"), os.path.join(tmp, "out")
            shutil.copytree(os.path.join(base, "in"), indir)
            args = [a.replace("{in}", indir).replace("{out}", outdir) for a in SPEC["args"]]
            env = dict(os.environ, LC_ALL="C.UTF-8", TZ="UTC", PYTHONHASHSEED="0")
            try:
                p = subprocess.run([sys.executable, SPEC["script"]] + args, capture_output=True, text=True, timeout=180, env=env,
                                   input=case.get("stdin", ""))
            except subprocess.TimeoutExpired:
                print(f"FAIL case {name}: the script took longer than 180 s")
                bad += 1
                continue
            if p.returncode != 0 and not SPEC.get("allow_exit"):
                print(f"FAIL case {name}: exit status {p.returncode}: {p.stderr.strip().splitlines()[-1][:200] if p.stderr.strip() else ''}")
                bad += 1
                continue
            exp = read_tree(os.path.join(base, "expected"))
            got = read_tree(outdir) if os.path.isdir(outdir) else {}
            msgs = []
            for fname, mode in SPEC["outputs"].items():
                if fname == "_stdout":
                    g, w = p.stdout, exp.get("_stdout", "")
                elif fname not in got:
                    msgs.append(f"{fname} was not written")
                    continue
                else:
                    g, w = got[fname], exp[fname]
                r = compare(mode, g, w)
                if r:
                    msgs.append(f"{fname}: {r[0]}")
            for m in msgs:
                print(f"FAIL case {name}: {m}")
            if msgs:
                bad += 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if bad:
        print(f"{bad} of {len(SPEC['cases'])} hidden cases failed")
        sys.exit(1)
    print(f"ok: {len(SPEC['cases'])} cases")


main()
'''


@dataclass
class EtlSpec:
    slug: str
    d: int
    prompt: str
    doc: str  # README body: the format specification (markdown)
    make: Callable[[random.Random, bool], dict[str, str]]  # (rng, big) -> input files {relative path: text}
    ref: str  # reference script
    outputs: dict[str, str]  # expected output file -> compare mode ("text", "csv", "csv-set", "json", "lines-set"); "_stdout" for stdout
    script: str = "etl.py"
    args: tuple = ("{in}", "{out}")
    alt: str = ""  # a different but equally valid implementation: must give identical outputs
    wrong: tuple = ()  # scripts the checker must reject
    buggy: str = ""  # start script of a "fix" task
    cases: int = 3
    title: str = ""
    tags: tuple = ()
    stdin: bool = False
    notes: str = ""


def _exec(script_text: str, script: str, args: tuple, files: dict[str, str], stdin: str = "") -> tuple[dict[str, str], str, int, str]:
    tmp = tempfile.mkdtemp(prefix="etlgen-")
    try:
        indir, outdir = os.path.join(tmp, "in"), os.path.join(tmp, "out")
        for rel, text in files.items():
            p = os.path.join(indir, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        os.makedirs(indir, exist_ok=True)
        with open(os.path.join(tmp, script), "w", encoding="utf-8") as f:
            f.write(script_text)
        a = [x.replace("{in}", indir).replace("{out}", outdir) for x in args]
        env = dict(os.environ, LC_ALL="C.UTF-8", TZ="UTC", PYTHONHASHSEED="0")
        p = subprocess.run(["python3", script] + a, cwd=tmp, capture_output=True, text=True, timeout=180, env=env, input=stdin)
        out = {}
        if os.path.isdir(outdir):
            for d, _, fs in os.walk(outdir):
                for fn in fs:
                    fp = os.path.join(d, fn)
                    with open(fp, "rb") as fh:
                        out[os.path.relpath(fp, outdir).replace(os.sep, "/")] = fh.read().decode("utf-8")
        return out, p.stdout, p.returncode, p.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _expected(spec: EtlSpec, script_text: str, files: dict[str, str], what: str) -> dict[str, str]:
    out, stdout, code, err = _exec(script_text, spec.script, spec.args, files)
    if code != 0:
        raise RuntimeError(f"{spec.slug}: {what} script failed (exit {code}):\n{err[-800:]}")
    res = {}
    for fname in spec.outputs:
        if fname == "_stdout":
            res["_stdout"] = stdout
        elif fname in out:
            res[fname] = out[fname]
        else:
            raise RuntimeError(f"{spec.slug}: {what} script did not write {fname} (wrote {sorted(out)})")
    return res


def etl_tasks(family_key: str, specs: list[EtlSpec], rng: random.Random, n: int, title: str = "") -> list[Task]:
    tasks: list[Task] = []
    for si, spec in enumerate(specs[:n]):
        srng = random.Random(rng.random())
        def draw(big, avoid):
            for _ in range(40):
                files = spec.make(random.Random(srng.random()), big)
                seen = {v for a in avoid for v in a.values() if len(v) > 40}
                if not any(len(v) > 40 and v in seen for v in files.values()):
                    return files
            raise RuntimeError(f"{spec.slug}: could not draw an input different from the earlier ones")

        vis_in = draw(False, [])
        hidden_in = []
        for _ in range(spec.cases):
            hidden_in.append(draw(True, [vis_in]))
        vis_exp = _expected(spec, spec.ref, vis_in, "reference")
        hidden_exp = [_expected(spec, spec.ref, h, "reference") for h in hidden_in]
        # guards: hidden expectations are not trivially empty, differ from each other and from the sample
        sigs = {json.dumps(e, sort_keys=True) for e in hidden_exp}
        if len(sigs) < len(hidden_exp) or json.dumps(vis_exp, sort_keys=True) in sigs:
            raise RuntimeError(f"{spec.slug}: cases are not distinct")
        for fname, text in vis_exp.items():
            if len(text.strip()) < 3:
                raise RuntimeError(f"{spec.slug}: sample output {fname} is empty")
        if spec.alt:
            for h, e in zip([vis_in] + hidden_in, [vis_exp] + hidden_exp):
                if _expected(spec, spec.alt, h, "alternative") != e:
                    raise RuntimeError(f"{spec.slug}: the alternative implementation disagrees with the reference (under-specified)")
        sample_files = {f"sample/in/{k}": v for k, v in vis_in.items()}
        for fname, text in vis_exp.items():
            sample_files["sample/expected/" + ("stdout.txt" if fname == "_stdout" else fname)] = text
        usage = (f"python3 {spec.script} sample/in /tmp/out" if spec.args == ("{in}", "{out}") else f"python3 {spec.script} " + " ".join(a.replace("{in}", "sample/in").replace("{out}", "/tmp/out") for a in spec.args))
        readme = (f"# {spec.title or title}\n\n{spec.doc.strip()}\n\n## Running it\n\n`{usage}`\n\n"
                  "`sample/in/` is a small example input and `sample/expected/` is exactly what a correct script writes for it "
                  "(compare with `diff -r`). The real inputs are bigger and nastier than the sample, so handle the rules above, not just the sample.\n")
        start = {"README.md": readme, spec.script: (spec.buggy or f"#!/usr/bin/env python3\n\"\"\"TODO: write the {family_key} script described in README.md.\"\"\"\n").strip("\n") + "\n", **sample_files}
        spec_json = {"script": spec.script, "args": list(spec.args), "outputs": spec.outputs, "cases": [{"name": f"c{k + 1}"} for k in range(len(hidden_in))]}
        hidden = {"tests/check_etl.py": CHECK_ETL, "tests/spec.json": json.dumps(spec_json, indent=1) + "\n"}
        for k, (h, e) in enumerate(zip(hidden_in, hidden_exp)):
            for rel, text in h.items():
                hidden[f"tests/cases/c{k + 1}/in/{rel}"] = text
            for rel, text in e.items():
                hidden[f"tests/cases/c{k + 1}/expected/{rel}"] = text
        t = Task(slug=f"{si + 1:02d}-{spec.slug}", prompt=spec.prompt.strip(), difficulty=spec.d, start=start, hidden=hidden,
                 solution={spec.script: spec.ref.strip("\n") + "\n"}, verify="python3 tests/check_etl.py", kind="fix" if spec.buggy else "feature",
                 lang="python", tags=["etl", *spec.tags], notes={"family": family_key, "spec": spec.slug})
        for wi, w in enumerate(spec.wrong):
            res = run(merged(start, hidden, {spec.script: w.strip("\n") + "\n"}), t.verify, timeout=90, cache=False)
            if res.ok:
                raise RuntimeError(f"{spec.slug}: checker accepted wrong script #{wi}")
        res = run(merged(start, hidden), t.verify, timeout=90, cache=False)
        if res.ok:
            raise RuntimeError(f"{spec.slug}: the start state already passes")
        tasks.append(t)
    return tasks
