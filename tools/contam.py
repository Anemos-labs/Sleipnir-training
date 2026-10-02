#!/usr/bin/env python3
"""Decontamination: compare every task with the texts of public benchmarks and of Sleipnir's own bench.

  tools/contam.py fetch [--only NAME ...]      download benchmark texts into ~/.cache/fx/contam (never into this repo)
                                               and build the n-gram index
  tools/contam.py scan [--family G] [--category C] [--write]
                                               score the corpus; --write refreshes catalog/CONTAMINATION.md and
                                               catalog/contamination.jsonl and exits 1 if any task FAILS

Method (the standard n-gram decontamination, applied per channel):
  prompt channel  8-word shingles of the task prompt  vs.  problem statements / questions of the benchmarks
  code channel   12-token shingles of start+hidden+solution files  vs.  reference code and tests of the benchmarks and
                 of Sleipnir's own bench fixtures and source (shingles that are boilerplate in OUR corpus are ignored)
  names          rare benchmark entry-point identifiers (>= 10 characters, two or more words) defined in a task
  avoid terms    tools/data/avoid_terms.txt: subjects docs/AVOID.md excludes (soft: review by a human)
A task FAILS when it shares >= 10 prompt shingles (or >= 25% of them), or >= 40 code shingles covering >= 15% of its
code, or >= 4 rare names. It WARNS below that but above the noise floor. Which benchmarks were in the index is
recorded in the report: a source that could not be fetched is not covered, and a scan is evidence, not proof."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("FX_CACHE", Path.home() / ".cache" / "fx")) / "contam"
RAW = CACHE / "raw"
INDEX = CACHE / "index.pkl"
SLEIPNIR = Path(os.environ.get("SLEIPNIR_REPO", ROOT.parent / "Sleipnir"))
VENV_PY = Path.home() / ".cache" / "fx" / "venv" / "bin" / "python"

HF = "https://huggingface.co/datasets"
SOURCES = {
    # name: (urls, reader, channels)
    "humaneval": ([f"{HF}/openai/openai_humaneval/resolve/main/openai_humaneval/test-00000-of-00001.parquet"], "parquet", {"prompt": ["prompt"], "code": ["prompt", "canonical_solution", "test"], "names": ["entry_point"]}),
    "humanevalplus": ([f"{HF}/evalplus/humanevalplus/resolve/main/data/test-00000-of-00001-5973903632b82d40.parquet"], "parquet", {"prompt": ["prompt"], "code": ["canonical_solution", "test"], "names": ["entry_point"]}),
    "mbpp": ([f"{HF}/google-research-datasets/mbpp/resolve/main/full/test-00000-of-00001.parquet", f"{HF}/google-research-datasets/mbpp/resolve/main/full/train-00000-of-00001.parquet",
              f"{HF}/google-research-datasets/mbpp/resolve/main/full/validation-00000-of-00001.parquet", f"{HF}/google-research-datasets/mbpp/resolve/main/full/prompt-00000-of-00001.parquet"],
             "parquet", {"prompt": ["text"], "code": ["code", "test_list"]}),
    "swebench": ([f"{HF}/princeton-nlp/SWE-bench/resolve/main/data/test-00000-of-00001.parquet", f"{HF}/princeton-nlp/SWE-bench/resolve/main/data/dev-00000-of-00001.parquet",
                  f"{HF}/princeton-nlp/SWE-bench_Verified/resolve/main/data/test-00000-of-00001.parquet"], "parquet", {"prompt": ["problem_statement"]}),
    "cruxeval": (["https://raw.githubusercontent.com/facebookresearch/cruxeval/main/data/cruxeval.jsonl"], "jsonl", {"code": ["code"]}),
    "bigcodebench": ([f"{HF}/bigcode/bigcodebench/resolve/main/data/v0.1.4-00000-of-00001.parquet"], "parquet", {"prompt": ["instruct_prompt"], "code": ["complete_prompt", "canonical_solution", "test"]}),
    "classeval": (["https://raw.githubusercontent.com/FudanSELab/ClassEval/master/data/ClassEval_data.json"], "json", {"prompt": ["skeleton"], "code": ["solution_code", "test"]}),
    "ifeval": ([f"{HF}/google/IFEval/resolve/main/ifeval_input_data.jsonl"], "jsonl", {"prompt": ["prompt"]}),
    "gsm8k": ([f"{HF}/openai/gsm8k/resolve/main/main/test-00000-of-00001.parquet", f"{HF}/openai/gsm8k/resolve/main/main/train-00000-of-00001.parquet"], "parquet", {"prompt": ["question"]}),
    "mmlu": ([f"{HF}/cais/mmlu/resolve/main/all/test-00000-of-00001.parquet"], "parquet", {"prompt": ["question"]}),
    "spider": ([f"{HF}/xlangai/spider/resolve/main/spider/validation-00000-of-00001.parquet", f"{HF}/xlangai/spider/resolve/main/spider/train-00000-of-00001.parquet"], "parquet", {"prompt": ["question"], "code": ["query"]}),
    "apps": ([f"{HF}/codeparrot/apps/resolve/refs%2Fconvert%2Fparquet/all/test/0000.parquet"], "parquet", {"prompt": ["question"]}),
    "livecodebench": ([f"{HF}/livecodebench/code_generation_lite/resolve/main/test.jsonl"], "jsonl_partial", {"prompt": ["question_content"]}),
}
PARTIAL_BYTES = 150_000_000


def toks_words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", s.lower())


def toks_code(s: str) -> list[str]:
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+|[^\sA-Za-z0-9_]", s)


def h64(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8", "replace"), digest_size=8).digest(), "big")


def shingle_hashes(tokens: list[str], k: int) -> set[int]:
    if len(tokens) < k:
        return set()
    return {h64(" ".join(tokens[i : i + k])) for i in range(len(tokens) - k + 1)}


PK, CK = 8, 12
NAME_RE = re.compile(r"(?:def|func|function|fn|void|int|static|public|private|class)\s+([A-Za-z_][A-Za-z0-9_]*)")


def rare_names(src: str) -> set[str]:
    out = set()
    for n in NAME_RE.findall(src):
        parts = re.split(r"_|(?<=[a-z])(?=[A-Z])", n)
        if len(n) >= 10 and len([p for p in parts if p]) >= 2:
            out.add(n.lower())
    return out


# ---- fetch ---------------------------------------------------------------------------------------------------------

def download(url: str, dest: Path, partial: bool = False) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["curl", "-sS", "-L", "--fail", "-m", "600", "-o", str(dest) + ".part"]
    if partial:
        cmd += ["-r", f"0-{PARTIAL_BYTES}"]
    r = subprocess.run(cmd + [url], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  could not fetch {url}: {r.stderr.strip()[:120]}", file=sys.stderr)
        Path(str(dest) + ".part").unlink(missing_ok=True)
        return False
    os.replace(str(dest) + ".part", dest)
    return True


def read_rows(path: Path, kind: str) -> list[dict]:
    if kind == "parquet":
        code = ("import pyarrow.parquet as pq, json, sys\n"
                "t = pq.read_table(sys.argv[1]).to_pylist()\n"
                "json.dump(t, sys.stdout, default=str)\n")
        py = str(VENV_PY) if VENV_PY.exists() else sys.executable
        r = subprocess.run([py, "-c", code, str(path)], capture_output=True, text=True, check=True)
        return json.loads(r.stdout)
    text = path.read_text(encoding="utf-8", errors="replace")
    if kind == "json":
        d = json.loads(text)
        return d if isinstance(d, list) else list(d.values())
    rows = []
    for line in text.splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue  # a truncated last line of a partial download
    return rows


def flat(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "\n".join(flat(x) for x in v)
    if isinstance(v, dict):
        return "\n".join(flat(x) for x in v.values())
    return "" if v is None else str(v)


def local_sources() -> dict[str, dict]:
    """Sleipnir's own bench fixtures and source: text per channel."""
    out = {"prompt": [], "code": [], "names": set()}
    fx = SLEIPNIR / "bench" / "fixtures"
    if fx.is_dir():
        for d in sorted(fx.iterdir()):
            tj = d / "task.json"
            if tj.exists():
                out["prompt"].append(json.loads(tj.read_text()).get("prompt", ""))
            for p in d.rglob("*"):
                if p.is_file() and p.suffix in (".py", ".go", ".js", ".java", ".rs", ".md") and p.name != "task.json":
                    t = p.read_text(encoding="utf-8", errors="replace")
                    out["code"].append(t)
                    out["names"] |= rare_names(t)
    src = SLEIPNIR / "internal"
    if src.is_dir():
        for p in src.rglob("*.go"):
            out["code"].append(p.read_text(encoding="utf-8", errors="replace"))
    return out


class Multiset:
    """Shingles seen once or twice. A shingle seen three or more times is an idiom (`if err != nil {{ return ...`) and
    carries no evidence of copying, so it is dropped for good."""

    def __init__(self):
        self.once: set[int] = set()
        self.twice: set[int] = set()
        self.common: set[int] = set()

    def update(self, shingles: set[int]) -> None:
        for h in shingles:
            if h in self.common:
                continue
            if h in self.twice:
                self.twice.discard(h)
                self.common.add(h)
            elif h in self.once:
                self.once.discard(h)
                self.twice.add(h)
            else:
                self.once.add(h)

    def result(self) -> set[int]:
        return self.once | self.twice


def fetch_exercism(prompt_idx: set[int]) -> dict:
    """Exercism problem descriptions (the instructions behind Aider's polyglot benchmark): one raw file per slug."""
    slugs = [s for s in (ROOT / "tools" / "data" / "exercism_slugs.txt").read_text().split() if s]
    got = 0
    for slug in slugs:
        dest = RAW / "exercism" / f"{slug}.md"
        url = f"https://raw.githubusercontent.com/exercism/problem-specifications/main/exercises/{slug}/description.md"
        if download(url, dest):
            prompt_idx |= shingle_hashes(toks_words(dest.read_text(encoding="utf-8", errors="replace")), PK)
            got += 1
    return {"files_fetched": got, "files_wanted": len(slugs), "rows": got}


def fetch(only: list[str] | None) -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    prompt_idx: set[int] = set()
    code_ms = Multiset()
    names: dict[str, str] = {}
    manifest: dict[str, dict] = {}
    for name, (urls, kind, ch) in SOURCES.items():
        if only and name not in only:
            continue
        got, rows_total = 0, 0
        for i, u in enumerate(urls):
            dest = RAW / name / f"{i}.{'parquet' if kind == 'parquet' else 'json'}"
            if not download(u, dest, partial=(kind == "jsonl_partial")):
                continue
            try:
                rows = read_rows(dest, "jsonl" if kind == "jsonl_partial" else kind)
            except Exception as e:  # noqa: BLE001
                print(f"  {name}: cannot read {dest.name}: {e}", file=sys.stderr)
                continue
            got += 1
            rows_total += len(rows)
            for row in rows:
                for f in ch.get("prompt", []):
                    prompt_idx |= shingle_hashes(toks_words(flat(row.get(f))), PK)
                code_text = "\n".join(flat(row.get(f)) for f in ch.get("code", []))
                if code_text:
                    code_ms.update(shingle_hashes(toks_code(code_text), CK))
                for f in ch.get("names", []):
                    n = flat(row.get(f)).strip().lower()
                    if len(n) >= 10:
                        names[n] = name
        manifest[name] = {"files_fetched": got, "files_wanted": len(urls), "rows": rows_total}
        print(f"{name}: {rows_total} rows from {got}/{len(urls)} files")
    loc = local_sources()
    for t in loc["prompt"]:
        prompt_idx |= shingle_hashes(toks_words(t), PK)
    for t in loc["code"]:
        code_ms.update(shingle_hashes(toks_code(t), CK))
    if not only or "exercism" in only:
        manifest["exercism"] = fetch_exercism(prompt_idx)
        print("exercism:", manifest["exercism"]["rows"], "descriptions")
    code_idx = code_ms.result()
    for n in loc["names"]:
        names.setdefault(n, "sleipnir-bench")
    manifest["sleipnir-bench-and-source"] = {"prompts": len(loc["prompt"]), "code_files": len(loc["code"])}
    with INDEX.open("wb") as f:
        pickle.dump({"prompt": prompt_idx, "code": code_idx, "names": names, "manifest": manifest}, f)
    print(f"index: {len(prompt_idx)} prompt shingles, {len(code_idx)} code shingles, {len(names)} names -> {INDEX}")
    return 0


# ---- scan ----------------------------------------------------------------------------------------------------------

def load_corpus(family: str | None, category: str | None):
    import fnmatch
    for p in sorted((ROOT / "corpus").glob("*/*.jsonl")):
        if category and p.parent.name != category:
            continue
        if family and not fnmatch.fnmatch(p.stem, family):
            continue
        for line in p.read_text(encoding="utf-8").split("\n"):
            if line.strip():
                yield json.loads(line)


def task_code(r: dict) -> str:
    files = r.get("files", {})
    parts = []
    for tree in ("start", "hidden", "solution"):
        for path, content in sorted(files.get(tree, {}).items()):
            if not path.endswith((".md", ".txt", ".json", ".csv", ".log", ".conf", ".ini", ".toml", ".yaml", ".yml")):
                parts.append(content)
    return "\n".join(parts)


def avoid_regexes() -> list[tuple[str, re.Pattern]]:
    p = ROOT / "tools" / "data" / "avoid_terms.txt"
    out = []
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                out.append((line, re.compile(line, re.I)))
    return out


def scan(args) -> int:
    if not INDEX.exists():
        print("contam: no index; run `tools/contam.py fetch` first", file=sys.stderr)
        return 2
    idx = pickle.load(INDEX.open("rb"))
    pidx, cidx, names, manifest = idx["prompt"], idx["code"], idx["names"], idx["manifest"]
    recs = list(load_corpus(args.family, args.category))
    avoid = avoid_regexes()

    # boilerplate: code shingles that occur in >= 4 different families of our own corpus
    fam_df: Counter = Counter()
    per_task_code: dict[str, set[int]] = {}
    for r in recs:
        sh = shingle_hashes(toks_code(task_code(r)), CK)
        per_task_code[r["id"]] = sh
    seen_fam: dict[int, set[str]] = {}
    for r in recs:
        for s in per_task_code[r["id"]]:
            seen_fam.setdefault(s, set()).add(r["family"])
    boiler = {s for s, fams in seen_fam.items() if len(fams) >= 4}

    flagged = []
    counts = Counter()
    for r in recs:
        ps = shingle_hashes(toks_words(r["prompt"]), PK)
        pm = len(ps & pidx)
        pfrac = pm / len(ps) if ps else 0.0
        cs = per_task_code[r["id"]] - boiler
        cm = len(cs & cidx)
        cfrac = cm / len(cs) if cs else 0.0
        nh = sorted({n for n in rare_names(task_code(r))} & set(names))
        av = [pat for pat, rx in avoid if rx.search(r["prompt"]) or rx.search(r["family"])]
        level = "ok"
        reasons = []
        if pm >= 10 or (pfrac >= 0.25 and pm >= 4):
            level, reasons = "FAIL", reasons + [f"prompt shares {pm} 8-word shingles ({pfrac:.0%}) with a benchmark text"]
        elif pm >= 3:
            level, reasons = "WARN", reasons + [f"prompt shares {pm} 8-word shingles"]
        if cm >= 40 and cfrac >= 0.15:
            level, reasons = "FAIL", reasons + [f"code shares {cm} 12-token shingles ({cfrac:.0%}) with benchmark or Sleipnir code"]
        elif cm >= 15 and cfrac >= 0.05 and level != "FAIL":
            level, reasons = "WARN", reasons + [f"code shares {cm} 12-token shingles"]
        if len(nh) >= 4:
            level, reasons = "FAIL", reasons + [f"defines {len(nh)} rare benchmark identifiers: {nh[:4]}"]
        elif len(nh) >= 2 and level == "ok":
            level, reasons = "WARN", reasons + [f"defines rare benchmark identifiers: {nh}"]
        if av:
            level = "WARN" if level == "ok" else level
            reasons.append(f"mentions an avoid-listed subject: {av[:3]}")
        counts[level] += 1
        if level != "ok":
            flagged.append({"id": r["id"], "family": r["family"], "level": level, "reasons": reasons})
    print(f"contam: scanned {len(recs)} tasks: {counts['ok']} ok, {counts['WARN']} warn, {counts['FAIL']} fail")
    for f in flagged[:30]:
        print(f"  {f['level']} {f['id']}: {'; '.join(f['reasons'])[:200]}")
    if args.write:
        write_report(recs, flagged, counts, manifest)
    return 1 if counts["FAIL"] else 0


def write_report(recs, flagged, counts, manifest) -> None:
    cat = ROOT / "catalog"
    cat.mkdir(exist_ok=True)
    with (cat / "contamination.jsonl").open("w", encoding="utf-8") as f:
        for x in flagged:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    by_fam = Counter(x["family"] for x in flagged)
    lines = ["# Contamination scan", "",
             f"{len(recs)} tasks scanned: **{counts['ok']} clean**, {counts['WARN']} warnings, {counts['FAIL']} failures.", "",
             "Reference texts that were in the index (a source that could not be downloaded is not covered):", "",
             "| source | files fetched | rows |", "|---|---|---|"]
    for k, v in sorted(manifest.items()):
        lines.append(f"| {k} | {v.get('files_fetched', '-')}/{v.get('files_wanted', '-')} | {v.get('rows', v.get('prompts', '-'))} |")
    lines += ["", "Method: see `tools/contam.py` (8-word prompt shingles, 12-token code shingles with boilerplate removed, rare",
              "benchmark identifiers, avoid-listed subjects). This is evidence of non-overlap with those texts, not proof",
              "that no task resembles some benchmark we did not index.", ""]
    if by_fam:
        lines += ["## Flagged families", "", "| family | flagged tasks |", "|---|---|"] + [f"| {f} | {n} |" for f, n in by_fam.most_common(40)]
    (cat / "CONTAMINATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--only", action="append")
    s = sub.add_parser("scan")
    s.add_argument("--family")
    s.add_argument("--category")
    s.add_argument("--write", action="store_true")
    a = ap.parse_args()
    return fetch(a.only) if a.cmd == "fetch" else scan(a)


if __name__ == "__main__":
    sys.exit(main())
