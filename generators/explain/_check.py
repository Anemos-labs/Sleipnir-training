"""Answer plumbing for the explain families: the hidden checker for file answers and the two Task builders.

``file_task``  - fixture: the agent writes ``answer.json`` (or ``answer.txt``); the hidden checker grades it (json-score).
``say_task``   - answer mode: the final message must contain bracketed / distinctive strings.

Nothing here registers a family.
"""
from __future__ import annotations

import json

from fx import Task

CHECK_PATH = "checks/explain_check.py"

CHECK_PY = r'''#!/usr/bin/env python3
"""Grades the answer file the agent was asked to write. Prints notes and, as the last line, {"score": x}."""
import json, os, re, sys

SPEC = json.loads(r"""__SPEC__""")
notes = []


def n_exact(x):
    return re.sub(r"\s+", " ", str(x).strip())


def n_path(x):
    s = str(x).strip().strip("`'\" ").replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s


def n_name(x):
    s = str(x).strip().strip("`'\" ")
    s = re.sub(r"\(.*\)\s*$", "", s).rstrip(";,. ")
    parts = [p for p in re.split(r"::|\.|#|->|/", s) if p]
    return parts[-1] if parts else s


def n_qual(x):
    s = str(x).strip().strip("`'\" ")
    s = re.sub(r"\(.*\)\s*$", "", s).rstrip(";,. ")
    return s.replace("::", ".").replace("#", ".").replace("->", ".")


def n_site(x):
    s = n_path(x).replace(" ", "")
    m = re.match(r"^(.*?):(\d+)(?::\d+)?$", s)
    return f"{m.group(1)}:{int(m.group(2))}" if m else s


def n_fold(x):
    return re.sub(r"\s+", " ", str(x).strip().strip("`'\" ")).casefold()


NORMS = {"exact": n_exact, "path": n_path, "name": n_name, "qual": n_qual, "site": n_site, "fold": n_fold}


def to_int(v):
    if isinstance(v, bool):
        raise ValueError("bool")
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return int(str(v).strip().replace(",", "").replace("_", ""))


def same(kind, got, want, norm="exact"):
    try:
        if kind == "int":
            return to_int(got) == int(want)
        if kind == "str":
            return NORMS[norm](got) == NORMS[norm](want)
        if kind == "bool":
            if isinstance(got, bool):
                return got == want
            return n_fold(got) in (("true", "yes") if want else ("false", "no"))
        if kind == "set":
            return isinstance(got, list) and {NORMS[norm](x) for x in got} == {NORMS[norm](x) for x in want}
        if kind == "list":
            return isinstance(got, list) and [NORMS[norm](x) for x in got] == [NORMS[norm](x) for x in want]
    except (ValueError, TypeError):
        return False
    return False


def lcs(a, b):
    m = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a)):
        for j in range(len(b)):
            m[i + 1][j + 1] = m[i][j] + 1 if a[i] == b[j] else max(m[i][j + 1], m[i + 1][j])
    return m[-1][-1]


def score_field(f, got, key):
    kind, want, norm = f["type"], f["value"], f.get("norm", "exact")
    if kind == "set":
        if not isinstance(got, list):
            notes.append(f"{key}: expected a list")
            return 0.0
        g = {NORMS[norm](x) for x in got}
        w = {NORMS[norm](x) for x in want}
        tp = len(g & w)
        if g != w:
            miss, extra = sorted(w - g), sorted(g - w)
            notes.append(f"{key}: {len(miss)} missing, {len(extra)} unexpected")
        return 2 * tp / max(1, len(g) + len(w)) if (g or w) else 1.0
    if kind == "list":
        if not isinstance(got, list):
            notes.append(f"{key}: expected a list")
            return 0.0
        g = [NORMS[norm](x) for x in got]
        w = [NORMS[norm](x) for x in want]
        if g == w:
            return 1.0
        notes.append(f"{key}: list differs")
        return min(0.9, lcs(g, w) / max(len(g), len(w), 1))
    if kind == "map":
        if not isinstance(got, dict):
            notes.append(f"{key}: expected an object")
            return 0.0
        sub, knorm = f.get("sub", "int"), f.get("knorm", "name")
        gm = {NORMS[knorm](k): v for k, v in got.items()}
        wm = {NORMS[knorm](k): v for k, v in want.items()}
        hit = sum(1 for k, v in wm.items() if k in gm and same(sub, gm[k], v, norm))
        extra = sum(1 for k in gm if k not in wm)
        if hit != len(wm) or extra:
            notes.append(f"{key}: {len(wm) - hit} entries wrong or missing, {extra} unexpected")
        return max(0.0, (hit - 0.5 * extra) / max(1, len(wm)))
    ok = same(kind, got, want, norm)
    if not ok:
        notes.append(f"{key}: wrong value")
    return 1.0 if ok else 0.0


def check_json():
    path = SPEC["file"]
    if not os.path.exists(path):
        notes.append(f"{path}: not found")
        return 0.0
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:  # noqa: BLE001
        notes.append(f"{path}: not valid JSON ({e})")
        return 0.0
    if not isinstance(data, dict):
        notes.append("top level of the file must be a JSON object")
        return 0.0
    total, got_w = 0.0, 0.0
    for key, f in SPEC["fields"].items():
        w = f.get("weight", 1.0)
        total += w
        if key not in data:
            notes.append(f"missing key {key!r}")
            continue
        got_w += w * score_field(f, data[key], key)
    return got_w / total if total else 0.0


def check_text():
    path = SPEC["file"]
    if not os.path.exists(path):
        notes.append(f"{path}: not found")
        return 0.0
    raw = open(path, encoding="utf-8", errors="replace").read()
    got = [ln.rstrip() for ln in raw.replace("\r\n", "\n").split("\n")]
    while got and not got[-1].strip():
        got.pop()
    while got and not got[0].strip():
        got.pop(0)
    want = SPEC["lines"]
    if got == want:
        return 1.0
    notes.append(f"{len(got)} lines written, {len(want)} expected")
    return min(0.9, lcs(got, want) / max(len(got), len(want), 1))


KIND = SPEC["kind"]
score = {"json": check_json, "text": check_text}[KIND]()
for n in notes[:12]:
    print(n)
print(json.dumps({"score": round(score, 4)}))
sys.exit(0 if score >= 0.9999 else 1)
'''


def jf(kind: str, value, weight: float = 1.0, **kw) -> dict:
    """one expected field of a json answer: kind is set|list|int|str|bool|map; norm is exact|path|name|qual|site|fold"""
    d = {"type": kind, "value": value, "weight": weight}
    d.update(kw)
    return d


def json_spec(fields: dict[str, dict], file: str = "answer.json") -> dict:
    return {"kind": "json", "file": file, "fields": fields}


def text_spec(lines: list[str], file: str = "answer.txt") -> dict:
    return {"kind": "text", "file": file, "lines": list(lines)}


def checker(spec: dict) -> dict[str, str]:
    s = json.dumps(spec, ensure_ascii=True, sort_keys=True)
    assert '"""' not in s
    return {CHECK_PATH: CHECK_PY.replace("__SPEC__", s)}


def dumps(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def file_task(*, slug: str, prompt: str, difficulty: int, start: dict[str, str], spec: dict, answer, lang: str = "",
              tags: list[str] | None = None, notes: dict | None = None, timeout_s: int = 60, context_window: int | None = None) -> Task:
    """A file-delivered answer. ``answer`` is the reference content of the answer file: a JSON-able object (json spec) or
    a list of lines (text spec)."""
    if spec["kind"] == "json":
        content = dumps(answer)
    else:
        content = "\n".join(answer) + "\n"
    return Task(slug=slug, prompt=prompt, difficulty=difficulty, start=start, hidden=checker(spec),
                solution={spec["file"]: content}, verify=f"python3 {CHECK_PATH}", pass_mode="json-score", lang=lang,
                tags=list(tags or []), notes=notes or {}, timeout_s=timeout_s, context_window=context_window)


def say_task(*, slug: str, prompt: str, difficulty: int, start: dict[str, str], contains: list[str], gold: str, lang: str = "",
             fold: bool = False, tags: list[str] | None = None, notes: dict | None = None, context_window: int | None = None) -> Task:
    """Answer mode: the final message must contain every string in ``contains``."""
    return Task(slug=slug, prompt=prompt, difficulty=difficulty, start=start, answer={"contains": contains, "fold": fold},
                gold_answer=gold, lang=lang, tags=list(tags or []), notes=notes or {}, context_window=context_window)
