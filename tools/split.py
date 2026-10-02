#!/usr/bin/env python3
"""Split the corpus into train / val / test by *family*, stratified by category.

  tools/split.py [--spec train:0.9,val:0.05,test:0.05] [--seed 1] [--tasks dist/tasks.jsonl]

Tasks cut from one family share a library, a world or a skeleton, so a random per-task split would leak: the model
trains on one mutant of a library and is validated on another. Whole families go to one part. Writes
catalog/splits.json ({part: [family, ...]}) and, with --tasks, <prefix>.<part>.jsonl next to that tasks file."""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default="train:0.9,val:0.05,test:0.05")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tasks")
    a = ap.parse_args()
    shares = {k: float(v) for k, v in (p.split(":") for p in a.spec.split(","))}
    rows = [json.loads(l) for l in (ROOT / "catalog" / "index.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    fams: dict[str, dict[str, int]] = defaultdict(dict)
    for r in rows:
        fams[r["category"]][r["family"]] = fams[r["category"]].get(r["family"], 0) + 1
    parts: dict[str, list[str]] = {k: [] for k in shares}
    rng = random.Random(a.seed)
    held = [k for k in shares if k != "train"]
    for cat in sorted(fams):
        names = sorted(fams[cat])
        rng.shuffle(names)
        total = sum(fams[cat].values())
        got = {k: 0 for k in held}
        for f in names:
            n = fams[cat][f]
            # give the family to the held-out part furthest below its target (if any is below), else train
            need = {k: shares[k] * total - got[k] for k in held}
            k = max(need, key=need.get) if need else None
            if k is not None and len(names) >= 6 and need[k] > 0 and need[k] >= n / 2:
                parts[k].append(f)
                got[k] += n
            else:
                parts.setdefault("train", []).append(f)
    out = {k: sorted(v) for k, v in parts.items()}
    (ROOT / "catalog" / "splits.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    where = {f: k for k, v in out.items() for f in v}
    counts = {k: sum(1 for r in rows if where.get(r["family"]) == k) for k in out}
    print("families:", {k: len(v) for k, v in out.items()}, "tasks:", counts)
    if a.tasks:
        p = Path(a.tasks)
        fam_of = {r["id"]: r["family"] for r in rows}
        handles = {k: (p.with_suffix("").parent / f"{p.stem}.{k}.jsonl").open("w", encoding="utf-8") for k in out}
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                t = json.loads(line)
                k = where.get(fam_of.get(t["id"], ""))
                if k:
                    handles[k].write(line + "\n")
        finally:
            for h in handles.values():
                h.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
