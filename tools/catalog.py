#!/usr/bin/env python3
"""Build the catalog: the browsable list of every admitted task, and the statistics.

  tools/catalog.py [--prune] [--strict]

Reads corpus/<category>/<family>.jsonl and admit/<category>/<family>.json (and catalog/quarantine.json, a map
id -> reason of tasks to leave out, written by hand or by tools/contam.py review). A task is in the catalog when
  * mode fixture/answer: its admission verdict is ok;  * mode rubric: it is structurally valid (no machine proof exists);
  * it is not quarantined.
Writes catalog/index.jsonl (id, family, category, mode, kind, lang, difficulty, tags, verify, prompt, ...) and
catalog/STATS.md. --prune rewrites the shards without the tasks that are not in the catalog (and removes empty ones).
--strict exits non-zero when any shard has a task without an ok verdict."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prune", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    quarantine = {}
    qp = ROOT / "catalog" / "quarantine.json"
    if qp.exists():
        quarantine = json.loads(qp.read_text())

    kept, dropped = [], []
    for shard in sorted((ROOT / "corpus").glob("*/*.jsonl")):
        cat, fam = shard.parent.name, shard.stem
        ap_ = ROOT / "admit" / cat / f"{fam}.json"
        verdicts = {v["id"]: v for v in json.loads(ap_.read_text())} if ap_.exists() else {}
        recs = [json.loads(line) for line in shard.read_text(encoding="utf-8").splitlines() if line.strip()]
        good = []
        for r in recs:
            reason = None
            if r["id"] in quarantine:
                reason = f"quarantined: {quarantine[r['id']]}"
            elif r["mode"] in ("fixture", "answer"):
                v = verdicts.get(r["id"])
                if v is None:
                    reason = "not admitted (no verdict)"
                elif not v["ok"]:
                    reason = f"admission failed: {v.get('reason', '')[:120]}"
            if reason:
                dropped.append((r["id"], reason))
            else:
                good.append(r)
                kept.append(r)
        if args.prune and len(good) != len(recs):
            if good:
                shard.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in good), encoding="utf-8")
            else:
                shard.unlink()
                if ap_.exists():
                    ap_.unlink()

    index = ROOT / "catalog" / "index.jsonl"
    index.parent.mkdir(exist_ok=True)
    with index.open("w", encoding="utf-8") as f:
        for r in sorted(kept, key=lambda r: r["id"]):
            row = {k: r[k] for k in ("id", "family", "category", "mode", "kind", "lang", "difficulty", "tags", "prompt") if k in r}
            row["team"] = r["team"].get("mode", "single") + (f":{r['team'].get('agents', '')}" if r["team"].get("mode") == "swarm" else "")
            row["budget"] = r["budget"]
            if r.get("verify"):
                row["verify"] = r["verify"]
            if r.get("answer"):
                row["answer_check"] = "final message contains " + json.dumps(r["answer"]["contains"], ensure_ascii=False)
            if r.get("rubric"):
                row["rubric"] = r["rubric"]
                row["checks"] = r.get("checks", {})
            row["sha"] = r["sha"]
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    write_stats(kept, dropped)
    print(f"catalog: {len(kept)} tasks, {len(dropped)} left out")
    for i, why in dropped[:20]:
        print("  left out", i, why)
    if args.strict and dropped:
        return 1
    return 0


def table(title: str, header: list[str], rows: list[list]) -> list[str]:
    out = [f"### {title}", "", "| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out + [""]


def write_stats(kept: list[dict], dropped: list[tuple[str, str]]) -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    from fx import CATEGORIES

    n = len(kept)
    by_cat: dict[str, Counter] = defaultdict(Counter)
    for r in kept:
        by_cat[r["category"]][r["difficulty"]] += 1
    langs = Counter(r["lang"] for r in kept)
    modes = Counter(r["mode"] for r in kept)
    kinds = Counter(r["kind"] for r in kept)
    fams = Counter(r["family"] for r in kept)
    swarm = sum(1 for r in kept if r["team"].get("mode") == "swarm")
    lines = ["# Corpus statistics", "", f"**{n} tasks** in **{len(fams)} families** across **{len(by_cat)} categories**; "
             f"{modes['fixture']} fixtures, {modes['answer']} answer-mode, {modes['rubric']} rubric; {swarm} for a swarm.", ""]
    rows = []
    for cat in CATEGORIES:
        c = by_cat.get(cat)
        if not c:
            continue
        tot = sum(c.values())
        rows.append([cat, tot, *[c.get(d, 0) for d in range(1, 6)], len({r['family'] for r in kept if r['category'] == cat})])
    rows.append(["**total**", n, *[sum(1 for r in kept if r["difficulty"] == d) for d in range(1, 6)], len(fams)])
    lines += table("By category and difficulty", ["category", "tasks", "d1", "d2", "d3", "d4", "d5", "families"], rows)
    lines += table("By language", ["language", "tasks"], [[k, v] for k, v in langs.most_common()])
    lines += table("By kind", ["kind", "tasks"], [[k, v] for k, v in kinds.most_common()])
    lines += table("Largest families", ["family", "tasks"], [[k, v] for k, v in fams.most_common(25)])
    plen = sorted(len(r["prompt"]) for r in kept)
    if plen:
        lines += [f"Prompt length (characters): median {plen[len(plen) // 2]}, p10 {plen[len(plen) // 10]}, p90 {plen[len(plen) * 9 // 10]}, max {plen[-1]}.", ""]
    if dropped:
        lines += [f"{len(dropped)} generated tasks are not in the catalog (admission failed, not admitted yet, or quarantined).", ""]
    (ROOT / "catalog" / "STATS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
