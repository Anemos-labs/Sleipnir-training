#!/usr/bin/env python3
"""Hidden checker for the testing tasks (written next to spec.json by the generator; never visible to the agent).

It runs the agent's workspace through a list of *scenarios* and prints a partial-credit score as the last line.

A scenario is a world: a scratch copy of the workspace (the agent's tests included) with some files replaced, an
environment, a command and an expectation:

    {"name": ..., "expect": "pass" | "fail", "gate": bool,
     "sources": {path: text},   # files written over the copy (reference code, a mutant, a refactored variant ...)
     "files":   {path: text},   # extra files (hidden tests, helpers); removed again afterwards
     "strip":   [glob, ...],    # files removed from the copy first (the agent's tests, for "fresh" scenarios)
     "env":     {...}, "cmd": "...", "timeout": s}

If any gate scenario does not behave as expected the score is 0 (a suite that is red on the real code kills every
mutant for free, so nothing else may count).  Otherwise the score is the share of scenarios that behave as expected.
"""
import fnmatch
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = json.load(open(os.path.join(HERE, "spec.json"), encoding="utf-8"))
ROOT = os.getcwd()
SKIP_DIRS = {".git", "_verify", "__pycache__", "target", "build", "node_modules", ".pytest_cache"}
_CLOCK = [time.time()]


def log(msg):
    print(msg, flush=True)


def copy_tree(src, dst):
    for dirpath, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        rel = os.path.relpath(dirpath, src)
        os.makedirs(os.path.join(dst, rel) if rel != "." else dst, exist_ok=True)
        for f in sorted(files):
            shutil.copy2(os.path.join(dirpath, f), os.path.join(dst, rel, f) if rel != "." else os.path.join(dst, f))


def list_files(root):
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files):
            out.append(os.path.relpath(os.path.join(dirpath, f), root))
    return out


def touch(path):
    # strictly newer than anything built so far (cargo and javac compare modification times)
    _CLOCK[0] = max(_CLOCK[0] + 2.0, time.time() + 2.0)
    os.utime(path, (_CLOCK[0], _CLOCK[0]))


def run_cmd(cmd, cwd, env, timeout):
    p = subprocess.Popen(["bash", "-c", cmd], cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out, False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, _ = p.communicate()
        return 124, out or "", True


def base_env(tmp):
    env = dict(os.environ)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0", NO_COLOR="1", TZ="UTC", LC_ALL="C.UTF-8",
               TMPDIR=tmp)
    env.setdefault("GOFLAGS", "-mod=mod")
    env.setdefault("GOTOOLCHAIN", "local")
    env.setdefault("GOPROXY", "off")
    env.setdefault("CARGO_NET_OFFLINE", "true")
    env.setdefault("CARGO_TARGET_DIR", os.path.join(tmp, "cargo-target"))
    return env


def mutate_text(text, edit):
    lines = text.split("\n")
    i = edit["line"] - 1
    if i >= len(lines) or lines[i].strip() != edit["old"].strip():
        raise SystemExit("checker error: a mutant does not apply to the reference source")
    lines[i] = edit["new"]
    return "\n".join(lines)


def with_marker(text, comment):
    """The same program with a leading comment line and a trailing one: every line number and the file hash change."""
    return f"{comment} build marker 7f3a\n{text}\n{comment} end of file\n"


def purge_caches(w):
    for dirpath, dirs, _ in os.walk(w):
        for d in list(dirs):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)
                dirs.remove(d)


def main():
    tmp = tempfile.mkdtemp(prefix="fxcheck-")
    w = os.path.join(tmp, "w")
    try:
        copy_tree(ROOT, w)
        env0 = base_env(tmp)
        scenarios = list(SPEC["scenarios"])
        ref = SPEC.get("ref", {})
        comment = SPEC.get("comment", "#")
        for m in SPEC.get("mutants", []):
            scenarios.append({"name": "mutant " + m["id"], "expect": "fail", "sources": {m["path"]: mutate_text(ref[m["path"]], m)}})
        ok_count, total, gate_failed = 0, 0, False
        base_files = set(list_files(w))
        for sc in scenarios:
            undo = []  # (kind, path, data)

            def put(path, text):
                full = os.path.join(w, path)
                if os.path.exists(full):
                    undo.append(("restore", path, open(full, "rb").read()))
                else:
                    undo.append(("delete", path, None))
                os.makedirs(os.path.dirname(full) or w, exist_ok=True)
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(text)
                touch(full)

            try:
                for g in sc.get("strip", []):
                    for r in list_files(w):
                        if fnmatch.fnmatch(r, g):
                            full = os.path.join(w, r)
                            undo.append(("restore", r, open(full, "rb").read()))
                            os.remove(full)
                for path, text in sc.get("sources", {}).items():
                    put(path, with_marker(text, comment) if sc.get("marker") else text)
                if sc.get("marker") and not sc.get("sources"):
                    for path, text in ref.items():
                        put(path, with_marker(text, comment))
                for path, text in sc.get("files", {}).items():
                    put(path, text)
                purge_caches(w)
                env = dict(env0)
                env.update(sc.get("env", {}))
                t0 = time.time()
                if sc.get("grep"):
                    g = sc["grep"]
                    hits = []
                    for r in list_files(w):
                        if any(fnmatch.fnmatch(r, pat) for pat in g["globs"]):
                            text = open(os.path.join(w, r), encoding="utf-8", errors="replace").read()
                            hits += [f"{r}: {rx}" for rx in g["forbid"] if re.search(rx, text)]
                    rc, out, timed_out = (1 if hits else 0), "\n".join(hits), False
                else:
                    rc, out, timed_out = run_cmd(sc.get("cmd") or SPEC["cmd"], w, env, sc.get("timeout", SPEC.get("timeout", 40)))
                dt = time.time() - t0
            finally:
                for kind, path, data in reversed(undo):
                    full = os.path.join(w, path)
                    if kind == "restore":
                        os.makedirs(os.path.dirname(full) or w, exist_ok=True)
                        with open(full, "wb") as fh:
                            fh.write(data)
                        touch(full)
                    elif os.path.exists(full):
                        os.remove(full)
                for r in list_files(w):  # whatever the tests left behind (scratch files, databases) must not help the next scenario
                    if r not in base_files:
                        os.remove(os.path.join(w, r))
            passed = rc == 0 and not timed_out
            met = passed if sc["expect"] == "pass" else not passed
            total += 1
            ok_count += 1 if met else 0
            log(f"[{'ok' if met else 'FAIL'}] {sc['name']}: expected {sc['expect']}, got {'pass' if passed else ('timeout' if timed_out else 'fail')} ({dt:.1f}s)")
            if not met and sc["expect"] == "pass":
                tail = "\n".join(out.strip().splitlines()[-25:])
                log("    " + tail.replace("\n", "\n    "))
            if sc.get("gate") and not met:
                gate_failed = True
                break
        score = 0.0 if gate_failed else (ok_count / total if total else 0.0)
        log(json.dumps({"score": score}))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
