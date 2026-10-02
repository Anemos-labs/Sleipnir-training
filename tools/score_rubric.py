#!/usr/bin/env python3
"""Cheap, deterministic scoring of a rubric-mode task's `checks` against a message (no model involved).

  tools/score_rubric.py TASK_ID_OR_JSONL_FILE --message FILE        (use - for stdin)

Supported keys of ``checks`` (all optional):
  max_words, min_words, max_lines, min_lines     size limits on the whole message
  bullets_min, bullets_max                       number of list items (lines starting with -, *, a bullet or `1.`/`1)`)
  must_include_all, must_include_any             lists of strings (case-insensitive unless "case_sensitive": true)
  must_not_include                               list of strings that must not occur
  regex_all, regex_none                          lists of regular expressions (re.search, multiline)
The rubric criteria themselves still need a judge; this only covers what can be checked mechanically. Prints a JSON
report and exits 0 when every check passes."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BULLET = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+\S")


def check_message(checks: dict, text: str) -> dict:
    cs = bool(checks.get("case_sensitive"))
    hay = text if cs else text.lower()
    norm = (lambda s: s) if cs else (lambda s: s.lower())
    words = len(re.findall(r"\S+", text))
    lines = [ln for ln in text.splitlines() if ln.strip()]
    bullets = sum(1 for ln in text.splitlines() if BULLET.match(ln))
    res: dict[str, bool] = {}

    def put(name: str, ok: bool) -> None:
        res[name] = bool(ok)

    if "max_words" in checks:
        put("max_words", words <= checks["max_words"])
    if "min_words" in checks:
        put("min_words", words >= checks["min_words"])
    if "max_lines" in checks:
        put("max_lines", len(lines) <= checks["max_lines"])
    if "min_lines" in checks:
        put("min_lines", len(lines) >= checks["min_lines"])
    if "bullets_min" in checks:
        put("bullets_min", bullets >= checks["bullets_min"])
    if "bullets_max" in checks:
        put("bullets_max", bullets <= checks["bullets_max"])
    for s in checks.get("must_include_all", []):
        put(f"include:{s}", norm(s) in hay)
    if checks.get("must_include_any"):
        put("include_any", any(norm(s) in hay for s in checks["must_include_any"]))
    for s in checks.get("must_not_include", []):
        put(f"exclude:{s}", norm(s) not in hay)
    for r in checks.get("regex_all", []):
        put(f"regex:{r}", re.search(r, text, re.M) is not None)
    for r in checks.get("regex_none", []):
        put(f"no_regex:{r}", re.search(r, text, re.M) is None)
    return {"ok": all(res.values()), "score": (sum(res.values()) / len(res)) if res else 1.0, "results": res,
            "stats": {"words": words, "lines": len(lines), "bullets": bullets}}


def find_task(arg: str) -> dict:
    p = Path(arg)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8").split("\n")[0])
    for f in (ROOT / "corpus").glob("*/*.jsonl"):
        for line in f.read_text(encoding="utf-8").split("\n"):
            if f'"id": "{arg}"' in line:
                return json.loads(line)
    sys.exit(f"score_rubric: no task {arg!r}")


def main() -> int:
    if len(sys.argv) < 4 or sys.argv[2] != "--message":
        print(__doc__)
        return 2
    task = find_task(sys.argv[1])
    msg = sys.stdin.read() if sys.argv[3] == "-" else Path(sys.argv[3]).read_text(encoding="utf-8")
    rep = check_message(task.get("checks", {}), msg)
    print(json.dumps(rep, indent=1))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
