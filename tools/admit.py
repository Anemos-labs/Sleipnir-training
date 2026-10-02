#!/usr/bin/env python3
"""Prove corpus tasks sound with Sleipnir's own tooling.

  tools/admit.py [--category C] [--family NAME ...] [--id GLOB ...] [--concurrency N] [--repeats R]
                 [--sleipnir BIN] [--keep] [--build-dir DIR]

What it does, for the selected shards under corpus/:

1. writes every task as a Sleipnir *fixture* (task.json, start/, hidden/, solution/) in a scratch build directory;
2. runs ``sleipnir rl taskgen fixture`` (the official materializer: one git repo per task, hidden files and the
   reference solution as content-addressed blobs), then adjusts verifier fields the fixture format cannot express
   (json-score, answer expectations) and validates the result with ``sleipnir rl tasks validate``;
3. runs ``sleipnir rl tasks check``: the verifier must FAIL on the untouched start and PASS with the reference
   solution applied, ``--repeats`` times in a row;
4. for ``answer`` tasks (final-message checks) the Go checker cannot supply an answer, so this script checks that the
   gold answer satisfies the expectation, that an empty answer does not, and (when the task also has a verifier
   command) that the command passes on the solved workspace;
5. writes ``admit/<category>/<family>.json``: one verdict per task. ``tools/catalog.py`` only admits tasks with ``ok``.

Needs a sleipnir binary: ``go build -o ~/.cache/fx/sleipnir ./cmd/sleipnir`` in the Sleipnir repository, or pass
--sleipnir / set $SLEIPNIR. With ``--dist DIR`` the materialised, ready-to-run tasks.jsonl + blobs/ + repos/ of the
admitted tasks are left there (this is how ``make dist`` builds them)."""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from fx import core  # noqa: E402
from fx.run import GOCACHE, run as fx_run, write_tree  # noqa: E402

MARK_HIDDEN = ".fx-answer-hidden"
MARK_SOL = ".fx-answer-gold"


def find_sleipnir(arg: str | None) -> str:
    cands = [arg, os.environ.get("SLEIPNIR"), str(Path.home() / ".cache" / "fx" / "sleipnir"), shutil.which("sleipnir")]
    for c in cands:
        if c and Path(c).exists() and os.access(c, os.X_OK):
            return c
    sys.exit("admit: no sleipnir binary (build one: cd ../Sleipnir && go build -o ~/.cache/fx/sleipnir ./cmd/sleipnir; or pass --sleipnir)")


def load(args) -> list[dict]:
    recs = []
    for p in sorted((ROOT / "corpus").glob("*/*.jsonl")):
        cat = p.parent.name
        fam = p.stem
        if args.category and cat not in args.category:
            continue
        if args.family and not any(fnmatch.fnmatch(fam, f) for f in args.family):
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                recs.append(json.loads(line))
    if args.id:
        recs = [r for r in recs if any(fnmatch.fnmatch(r["id"], g) for g in args.id)]
    return recs


def difficulty_word(d: int) -> str:
    return core.fixture_difficulty(d)


def write_fixture(root: Path, r: dict) -> None:
    d = root / r["id"]
    files = r["files"]
    start, hidden, sol = dict(files["start"]), dict(files["hidden"]), dict(files["solution"])
    if r["mode"] == "answer":
        if not hidden:
            hidden = {MARK_HIDDEN: "marker: this fixture is checked by its final message\n"}
        if not sol:
            sol = {MARK_SOL: "marker\n"}
    spec = {
        "id": r["id"],
        "kind": r["kind"] if r["mode"] == "fixture" else "feature",
        "lang": r["lang"],
        "difficulty": difficulty_word(r["difficulty"]),
        "prompt": r["prompt"],
        "verify": r["verify"] or "true",
        "timeout_s": r["timeout_s"],
        "protected": [g for g in r["protected"]],
        "team": r["team"],
        "tags": [t for t in r["tags"]],
        "budget": r["budget"],
    }
    if r.get("setup"):
        spec["setup"] = r["setup"]
    d.mkdir(parents=True)
    (d / "task.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, tree in (("start", start), ("hidden", hidden), ("solution", sol)):
        write_tree(d / name, tree)


def run_cmd(cmd: list[str], cwd: Path, env: dict | None = None, timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def postprocess(raw: Path, out: Path, recs: dict[str, dict]) -> int:
    n = 0
    with raw.open(encoding="utf-8") as f, out.open("w", encoding="utf-8") as g:
        for line in f:
            t = json.loads(line)
            r = recs[t["id"]]
            v = t["verifier"]
            meta = t.get("meta") or {}
            if r.get("pass") == "json-score":
                v["pass"] = "json-score"
            if r["mode"] == "answer":
                v["expect"] = {"contains": r["answer"]["contains"], **({"fold": True} if r["answer"].get("fold") else {})}
                real_hidden = {k: x for k, x in (v.get("hidden") or {}).items() if k != MARK_HIDDEN}
                v["hidden"] = real_hidden
                v["protected"] = [p for p in v.get("protected", []) if not p.endswith(MARK_HIDDEN.replace(".", r"\."))
                                  and MARK_HIDDEN not in p]
                if not r["verify"]:
                    v["cmd"] = ""
                    v.pop("pass", None)
                    v.pop("timeout_s", None)
                    v["protected"] = []
                meta.pop("gold_blob", None)  # `tasks check` cannot supply an answer: this script checks these tasks
            t["tags"] = r["tags"]
            meta.update({"family": r["family"], "category": r["category"], "difficulty": r["difficulty"], "mode": r["mode"], "sha": r["sha"]})
            t["meta"] = meta
            g.write(json.dumps(t, ensure_ascii=False) + "\n")
            n += 1
    return n


def check_answer_task(r: dict) -> tuple[bool, str]:
    ans = r["answer"]
    fold = bool(ans.get("fold"))
    gold = r["gold_answer"].lower() if fold else r["gold_answer"]
    for c in ans["contains"]:
        if (c.lower() if fold else c) not in gold:
            return False, f"gold answer lacks {c!r}"
    if r["verify"]:
        files = dict(r["files"]["start"])
        files.update(r["files"]["hidden"])
        files.update(r["files"]["solution"])
        res = fx_run(files, r["verify"], timeout=min(int(r["timeout_s"]), 300), cache=False)
        if not res.ok:
            return False, f"verify fails on the solved workspace (exit {res.code}):\n{res.out[-800:]}"
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--category", action="append")
    ap.add_argument("--family", action="append", help="glob ok")
    ap.add_argument("--id", action="append", help="glob ok")
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--repeats", type=int, default=1, help="verifier repeats: fail on start every time, pass on solution every time")
    ap.add_argument("--sleipnir")
    ap.add_argument("--keep", action="store_true", help="keep the build directory")
    ap.add_argument("--build-dir")
    ap.add_argument("--dist", help="leave tasks.jsonl, blobs/ and repos/ of the admitted tasks in this directory")
    ap.add_argument("--no-write", action="store_true", help="do not write admit/ verdict files")
    args = ap.parse_args()

    sl = find_sleipnir(args.sleipnir)
    recs = [r for r in load(args) if r["mode"] in ("fixture", "answer")]
    if not recs:
        print("admit: nothing selected")
        return 0
    by_id = {r["id"]: r for r in recs}
    build = Path(args.build_dir or tempfile.mkdtemp(prefix="fx-admit-"))
    build.mkdir(parents=True, exist_ok=True)
    fixtures = build / "fixtures"
    if fixtures.exists():
        shutil.rmtree(fixtures)
    for r in recs:
        write_fixture(fixtures, r)

    verdicts: dict[str, dict] = {r["id"]: {"id": r["id"], "ok": False, "reason": "not checked"} for r in recs}
    for sub in ("repos", "blobs"):
        shutil.rmtree(build / sub, ignore_errors=True)
    p = run_cmd([sl, "rl", "taskgen", "fixture", "--dir", str(fixtures), "--repo-root", "repos", "--repo-path-prefix", "repos", "-o", "tasks.raw.jsonl", "--blobs", "blobs"], build)
    if p.returncode != 0:
        print(p.stdout + p.stderr)
        print("admit: taskgen fixture failed")
        return 2
    raw = build / "tasks.raw.jsonl"
    full = build / "tasks.jsonl"
    postprocess(raw, full, by_id)
    p = run_cmd([sl, "rl", "tasks", "validate", "tasks.jsonl"], build)
    if p.returncode != 0:
        print(p.stdout + p.stderr)
        print("admit: tasks validate failed")
        return 2

    # tasks.check.jsonl: fixtures that the Go checker can prove (everything with a verifier command and no expect)
    checkable = [json.loads(l) for l in full.read_text(encoding="utf-8").splitlines() if l.strip()]
    chk = [t for t in checkable if by_id[t["id"]]["mode"] == "fixture"]
    (build / "tasks.check.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in chk), encoding="utf-8")
    if chk:
        gocache = GOCACHE
        gocache.mkdir(parents=True, exist_ok=True)
        cmd = [sl, "rl", "tasks", "check", "tasks.check.jsonl", "--blobs", "blobs", "--concurrency", str(args.concurrency),
               "--verify-repeats", str(args.repeats), "--work-dir", str(build / "work"), "--report", "admit.json",
               "--set-env", f"GOCACHE={gocache}", "--set-env", "GOFLAGS=-mod=mod", "--set-env", "GOTOOLCHAIN=local",
               "--set-env", "GOPROXY=off", "--set-env", "CARGO_NET_OFFLINE=true"]
        p = run_cmd(cmd, build)
        rep = build / "admit.json"
        if rep.exists():
            for v in json.loads(rep.read_text()):
                verdicts[v["id"]] = {"id": v["id"], "ok": bool(v.get("ok")), **({"reason": v["reason"][:600]} if v.get("reason") else {})}
        else:
            print(p.stdout + p.stderr)
            print("admit: tasks check produced no report")
            return 2
    for r in recs:
        if r["mode"] == "answer":
            ok, why = check_answer_task(r)
            verdicts[r["id"]] = {"id": r["id"], "ok": ok, **({"reason": why} if why else {})}

    bad = [v for v in verdicts.values() if not v["ok"]]
    for v in bad[:40]:
        print(f"FAIL {v['id']}: {v.get('reason', '')[:700]}")
    if len(bad) > 40:
        print(f"... and {len(bad) - 40} more failures")
    print(f"admit: {len(verdicts) - len(bad)} ok, {len(bad)} failed of {len(verdicts)} tasks")

    if not args.no_write:
        groups: dict[tuple[str, str], list] = {}
        for r in recs:
            groups.setdefault((r["category"], r["family"]), []).append(verdicts[r["id"]])
        for (cat, fam), vs in groups.items():
            d = ROOT / "admit" / cat
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{fam}.json").write_text(json.dumps(sorted(vs, key=lambda v: v["id"]), indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.dist:
        dist = Path(args.dist)
        dist.mkdir(parents=True, exist_ok=True)
        good = {i for i, v in verdicts.items() if v["ok"]}
        with (dist / "tasks.jsonl").open("w", encoding="utf-8") as g:
            for t in checkable:
                if t["id"] in good:
                    g.write(json.dumps(t, ensure_ascii=False) + "\n")
        for sub in ("repos", "blobs"):
            shutil.copytree(build / sub, dist / sub, dirs_exist_ok=True)
    if not args.keep and not args.build_dir:
        shutil.rmtree(build, ignore_errors=True)
    else:
        print("admit: build directory kept at", build)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
