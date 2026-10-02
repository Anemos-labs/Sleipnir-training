#!/usr/bin/env python3
"""Run generators and write corpus shards.

  tools/build.py [--category C] [--family NAME ...] [--jobs N] [--scale X] [--twice] [--list]

Each family writes ``corpus/<category>/<family>.jsonl`` (one task record per line, sorted by id). A family with
problems writes nothing and the run exits non-zero. ``--twice`` builds every selected family a second time and
fails if the bytes differ (determinism)."""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib
import json
import os
import pkgutil
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import fx  # noqa: E402


def discover(categories: list[str] | None = None) -> list[str]:
    """Import every non-underscore module under generators/<category>/. Returns import errors."""
    errors = []
    gdir = ROOT / "generators"
    for cat in sorted(p.name for p in gdir.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
        if categories and cat not in categories:
            continue
        pkg = gdir / cat
        if not (pkg / "__init__.py").exists():
            (pkg / "__init__.py").write_text("")
        for mod in sorted(pkgutil.iter_modules([str(pkg)]), key=lambda m: m.name):
            if mod.name.startswith("_"):
                continue
            name = f"generators.{cat}.{mod.name}"
            try:
                importlib.import_module(name)
            except Exception:  # noqa: BLE001
                errors.append(f"{name}: import failed\n{traceback.format_exc()}")
    return errors


def shard_path(fam: fx.Family) -> Path:
    return ROOT / "corpus" / fam.category / f"{fam.name}.jsonl"


def build_one(name: str, scale: float, twice: bool) -> tuple[str, int, list[str], float]:
    fam = fx.REGISTRY[name]
    t0 = time.time()
    try:
        n = max(1, round(fam.n * scale)) if scale != 1.0 else None
        recs, problems = fx.run_family(fam, n)
        if twice and not problems:
            recs2, _ = fx.run_family(fam, n)
            if json.dumps(recs, sort_keys=True) != json.dumps(recs2, sort_keys=True):
                problems.append(f"{name}: not deterministic (two builds differ)")
    except Exception:  # noqa: BLE001
        return name, 0, [f"{name}: generator raised\n{traceback.format_exc()}"], time.time() - t0
    if problems:
        return name, 0, problems, time.time() - t0
    if not recs:
        return name, 0, [f"{name}: produced no tasks"], time.time() - t0
    p = shard_path(fam)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in recs)
    p.write_text(text, encoding="utf-8")
    return name, len(recs), [], time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", action="append", help="build only these categories (repeatable)")
    ap.add_argument("--family", action="append", help="build only these families (repeatable; glob ok)")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--scale", type=float, default=1.0, help="multiply every family's n")
    ap.add_argument("--twice", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    errs = discover(args.category)
    if errs:
        print("\n".join(errs), file=sys.stderr)
    names = sorted(fx.REGISTRY)
    if args.category:
        names = [n for n in names if fx.REGISTRY[n].category in args.category]
    if args.family:
        import fnmatch
        names = [n for n in names if any(fnmatch.fnmatch(n, f) for f in args.family)]
    if args.list:
        for n in names:
            f = fx.REGISTRY[n]
            print(f"{f.category:10} {n:48} n={f.n:<3} {f.lang:11} {f.mode}")
        print(len(names), "families")
        return 1 if errs else 0
    total, bad = 0, 0
    with cf.ProcessPoolExecutor(max_workers=args.jobs) if args.jobs > 1 else _Serial() as ex:
        futs = [ex.submit(build_one, n, args.scale, args.twice) for n in names]
        for f in futs:
            name, cnt, problems, dt = f.result()
            if problems:
                bad += 1
                print(f"FAIL {name} ({dt:.0f}s)")
                for p in problems[:12]:
                    print("   ", p.replace("\n", "\n    "))
                if len(problems) > 12:
                    print(f"    ... {len(problems) - 12} more")
            else:
                total += cnt
                print(f"ok   {name}: {cnt} tasks ({dt:.0f}s)")
    print(f"{len(names) - bad} families built, {bad} failed, {total} tasks written")
    return 1 if (bad or errs) else 0


class _Serial:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def submit(self, fn, *a):
        class F:
            def __init__(s, r):
                s.r = r

            def result(s):
                return s.r

        return F(fn(*a))


if __name__ == "__main__":
    sys.exit(main())
