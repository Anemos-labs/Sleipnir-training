"""A small hidden-checker engine for file-delivered chat tasks (`reply.md` and friends).

``check_files(rules, extra="")`` returns the hidden tree ``{".check/check.py": source}``; the verify command is
``python3 .check/check.py``. ``rules`` is a list of dicts (see ENGINE); ``extra`` is optional python source that defines
``extra(text) -> list[str]`` (failure messages) for family-specific logic. ``run_checks(rules, text, extra)`` runs the
same engine in-process so a generator can assert that its gold reply passes (and that junk fails).

Counting conventions (stated here because the prompts rely on them): a *word* is a whitespace-separated token that
contains a letter or digit; ``max_words`` counts only those (so list dashes and em-dashes are free), ``min_words``
counts every token. Both are therefore the lenient reading for whichever bound is being tested.
"""
from __future__ import annotations

import json

VERIFY = "python3 .check/check.py"

ENGINE = r'''
import json, re, sys
from pathlib import Path

RULES = json.loads(__RULES__)
TARGET = "__TARGET__"

BULLET = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+\S")
ABBR = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Prof|St|vs|etc|No|approx|Inc|Ltd|Jr|Sr)\.|\b(?:e\.g|i\.e)\.|\d\.\d")


def words_all(text):
    return text.split()


def words_alnum(text):
    return [t for t in text.split() if re.search(r"[A-Za-z0-9]", t)]


def sentences(text):
    t = re.sub(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+", "", text)
    t = ABBR.sub(lambda m: m.group(0).replace(".", ""), t)
    parts = re.split(r"(?<=[.!?])[\"')\]]*\s+", t.strip())
    return [p for p in parts if re.search(r"[A-Za-z0-9]", p)]


def match_any(pats, text):
    for p in pats:
        if p.startswith("re:"):
            if re.search(p[3:], text, re.I | re.M):
                return True
        elif p.lower() in text.lower():
            return True
    return False


def has_word(w, text):
    return re.search(r"(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])", text, re.I) is not None


def body_of(text, r):
    pre = r.get("skip_prefix")
    if pre:
        lines = text.splitlines()
        while lines and re.match(pre, lines[0]):
            lines.pop(0)
        return "\n".join(lines)
    return text


def run_checks(rules, text, extra_fn=None):
    fails = []
    for r in rules:
        t = r["t"]
        b = body_of(text, r)
        if t == "max_words":
            n = len(words_alnum(b))
            if n > r["n"]:
                fails.append(f"too long: {n} words, the limit is {r['n']}")
        elif t == "min_words":
            n = len(words_all(b))
            if n < r["n"]:
                fails.append(f"too short: {n} words, at least {r['n']} wanted")
        elif t == "max_chars":
            n = len(b.strip())
            if n > r["n"]:
                fails.append(f"too long: {n} characters, the limit is {r['n']}")
        elif t == "min_chars":
            n = len(b.strip())
            if n < r["n"]:
                fails.append(f"too short: {n} characters, at least {r['n']} wanted")
        elif t == "bullets":
            n = sum(1 for ln in b.splitlines() if BULLET.match(ln))
            if "min" in r and n < r["min"]:
                fails.append(f"{n} list items, at least {r['min']} wanted")
            if "max" in r and n > r["max"]:
                fails.append(f"{n} list items, at most {r['max']} allowed")
        elif t == "lines":
            n = len([ln for ln in b.splitlines() if ln.strip()])
            if "min" in r and n < r["min"]:
                fails.append(f"{n} non-blank lines, at least {r['min']} wanted")
            if "max" in r and n > r["max"]:
                fails.append(f"{n} non-blank lines, at most {r['max']} allowed")
        elif t == "paragraphs":
            blocks = [x for x in re.split(r"\n\s*\n", b.strip()) if x.strip()]
            n = len(blocks)
            if "min" in r and n < r["min"]:
                fails.append(f"{n} paragraphs, at least {r['min']} wanted")
            if "max" in r and n > r["max"]:
                fails.append(f"{n} paragraphs, at most {r['max']} allowed")
        elif t == "sentences":
            n = len(sentences(b))
            if "min" in r and n < r["min"]:
                fails.append(f"{n} sentences, at least {r['min']} wanted")
            if "max" in r and n > r["max"]:
                fails.append(f"{n} sentences, at most {r['max']} allowed")
        elif t == "include":
            if not match_any(r["any"], b):
                fails.append(f"missing: {r.get('label') or r['any'][0]}")
        elif t == "exclude":
            for w in r["words"]:
                if w.startswith("re:"):
                    if re.search(w[3:], b, re.I | re.M):
                        fails.append(f"must not contain /{w[3:]}/")
                elif has_word(w, b):
                    fails.append(f"must not contain {w!r}")
        elif t == "first_line":
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if not lines or not re.search(r["re"], lines[0].strip()):
                fails.append(f"first line must match /{r['re']}/ (label: {r.get('label', '')})")
        elif t == "last_line":
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if not lines or not re.search(r["re"], lines[-1].strip()):
                fails.append(f"last line must match /{r['re']}/ (label: {r.get('label', '')})")
        elif t == "every_line":
            for ln in b.splitlines():
                if not ln.strip():
                    continue
                if r.get("skip") and re.search(r["skip"], ln):
                    continue
                if not re.search(r["re"], ln):
                    fails.append(f"line does not match /{r['re']}/: {ln[:60]!r}")
                    break
        elif t == "no_line":
            for ln in b.splitlines():
                if re.search(r["re"], ln):
                    fails.append(f"forbidden line pattern /{r['re']}/: {ln[:60]!r}")
                    break
        elif t == "max_line_chars":
            for ln in b.splitlines():
                if len(ln) > r["n"]:
                    fails.append(f"a line is {len(ln)} characters, the limit is {r['n']}: {ln[:40]!r}")
                    break
        elif t == "headings":
            hs = [re.sub(r"^#+\s*", "", ln).strip() for ln in b.splitlines() if re.match(r"^#{1,6}\s+\S", ln)]
            want = r["list"]
            if r.get("ci", True):
                hs_c = [h.lower() for h in hs]
                want_c = [w.lower() for w in want]
            else:
                hs_c, want_c = hs, want
            if r.get("exact", True):
                if hs_c != want_c:
                    fails.append(f"headings should be {want} in order, found {hs}")
            else:
                it = iter(hs_c)
                if not all(w in it for w in want_c):
                    fails.append(f"headings should include {want} in order, found {hs}")
        elif t == "numbers_subset":
            allowed = set(str(x) for x in r["allowed"])
            for m in re.finditer(r"(?<![A-Za-z0-9.])\d[\d,]*(?:\.\d+)?%?", b):
                tok = m.group(0).rstrip(",").replace(",", "")
                if tok not in allowed and tok.rstrip("%") not in allowed:
                    fails.append(f"number {tok!r} does not appear in the source material")
                    break
        elif t == "json_file":
            pass
        else:
            fails.append(f"unknown rule {t}")
    if extra_fn:
        try:
            fails.extend(extra_fn(text))
        except Exception as e:
            fails.append(f"extra check raised {type(e).__name__}: {e}")
    return fails


__EXTRA__


def main():
    p = Path(TARGET)
    if not p.exists():
        print(f"FAIL: {TARGET} does not exist")
        return 1
    text = p.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        print(f"FAIL: {TARGET} is empty")
        return 1
    fails = run_checks(RULES, text, globals().get("extra"))
    if fails:
        print("FAIL:")
        for f in fails:
            print(" -", f)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def source(rules: list[dict], extra: str = "", target: str = "reply.md") -> str:
    return (ENGINE.replace("__RULES__", json.dumps(json.dumps(rules, ensure_ascii=False)))
            .replace("__TARGET__", target).replace("__EXTRA__", extra))


def check_files(rules: list[dict], extra: str = "", target: str = "reply.md") -> dict[str, str]:
    return {".check/check.py": source(rules, extra, target)}


def run_checks(rules: list[dict], text: str, extra: str = "") -> list[str]:
    """Run the engine in-process. Returns failure messages (empty = pass)."""
    ns: dict = {"__name__": "chatcheck"}
    exec(compile(source(rules, extra), "check.py", "exec"), ns)
    return ns["run_checks"](rules, text, ns.get("extra"))


def assert_passes(rules: list[dict], gold: str, extra: str = "", what: str = "") -> None:
    f = run_checks(rules, gold, extra)
    if f:
        raise AssertionError(f"gold reply fails its own checker ({what}): {f}\n---\n{gold}")
    bad = run_checks(rules, "ok", extra)
    if not bad:
        raise AssertionError(f"checker accepts a junk reply ({what})")
