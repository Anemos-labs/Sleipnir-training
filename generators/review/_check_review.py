#!/usr/bin/env python3
"""Hidden checker for the review tasks: scores review.json against the planted defects in spec.json.

Strict about the schema, lenient about wording: a finding is matched to a planted defect by file and line window only.

score = max(0, matched / planted - 0.25 * false_positives)

* findings with category "style" are never penalised (and never count as a hit);
* a finding that lands on no in-scope planted defect (including a harmless decoy or an out-of-scope defect) is a false
  positive; several findings on one defect count once;
* verdict mode: the verdict must be right as well, otherwise the score is capped at 0.5.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = json.load(open(os.path.join(HERE, "spec.json"), encoding="utf-8"))
CATS = {"logic", "security", "concurrency", "resource-leak", "api-misuse", "off-by-one", "validation", "performance",
        "error-handling", "style"}


def finish(score, msg=""):
    if msg:
        print(msg)
    print(json.dumps({"score": max(0.0, min(1.0, score))}))
    sys.exit(0)


def norm(p):
    p = p.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if p.startswith(("a/", "b/")):
        p = p[2:]
    return p


def same_file(a, b):
    a, b = norm(a), norm(b)
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def main():
    path = SPEC.get("answer_file", "review.json")
    if not os.path.exists(path):
        finish(0.0, f"{path} not found")
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        finish(0.0, f"{path} is not valid JSON: {e}")
    verdict = None
    if SPEC["format"] == "object":
        if not isinstance(data, dict) or set(data) - {"verdict", "findings"} or "findings" not in data or "verdict" not in data:
            finish(0.0, 'expected an object {"verdict": ..., "findings": [...]}')
        verdict = data["verdict"]
        if verdict not in ("approve", "request-changes"):
            finish(0.0, 'verdict must be "approve" or "request-changes"')
        findings = data["findings"]
    else:
        findings = data
    if not isinstance(findings, list):
        finish(0.0, "findings must be a JSON list")
    if len(findings) > 40:
        finish(0.0, "far too many findings")
    clean = []
    for i, f in enumerate(findings):
        if not isinstance(f, dict) or set(f) != {"file", "line", "category", "summary"}:
            finish(0.0, f"finding {i}: expected exactly the keys file, line, category, summary")
        if not isinstance(f["file"], str) or not f["file"].strip():
            finish(0.0, f"finding {i}: file must be a non-empty string")
        if not isinstance(f["line"], int) or isinstance(f["line"], bool) or f["line"] < 1:
            finish(0.0, f"finding {i}: line must be a positive integer")
        if f["category"] not in CATS:
            finish(0.0, f"finding {i}: category must be one of {sorted(CATS)}")
        if not isinstance(f["summary"], str) or len(f["summary"].strip()) < 8:
            finish(0.0, f"finding {i}: summary must be a sentence (at least 8 characters)")
        clean.append(f)

    slack = SPEC.get("slack", 1)
    defects = [d for d in SPEC["defects"] if d.get("in_scope", True)]
    matched = set()
    fp = 0
    for f in clean:
        if f["category"] == "style":
            continue
        best, best_dist = None, None
        for d in defects:
            if same_file(f["file"], d["file"]) and d["start"] - slack <= f["line"] <= d["end"] + slack:
                dist = abs(f["line"] - (d["start"] + d["end"]) / 2)
                if best is None or dist < best_dist:
                    best, best_dist = d["id"], dist
        if best is not None:
            matched.add(best)
            continue
        fp += 1
    total = len(defects)
    recall = 1.0 if total == 0 else len(matched) / total
    score = recall - 0.25 * fp
    if verdict is not None:
        want = "request-changes" if total else "approve"
        if verdict != want:
            score = min(score, 0.5)
    print(f"planted={total} matched={len(matched)} false_positives={fp}" + (f" verdict={verdict}" if verdict else ""))
    finish(score)


if __name__ == "__main__":
    main()
