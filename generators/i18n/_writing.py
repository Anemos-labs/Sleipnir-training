"""Constrained-writing tasks in other languages: the agent writes one text file; a hidden script checks the constraints.

A scenario is ``(slug, difficulty, topic_prompt, facts, path, constraints, solution_text)``: ``facts`` is the content of the
``datos``-style file in the repository (the text must reuse some of it, which ``include`` constraints enforce), the constraints
are rendered into the prompt in the target language *and* embedded in the hidden checker, so the two cannot drift apart, and the
reference solution is verified against the checker while the family is built.

Checker kinds (all counted on the text of ``path`` read as UTF-8):

* ``sentences`` (min, max, terms): maximal runs of terminator characters; the text must end with a terminator.
* ``chars`` (min, max): characters that are not whitespace.   ``words`` (min, max): whitespace separated tokens that contain a letter or digit (bullet dashes do not count).
* ``syllables`` (min, max): Hangul syllables.   ``kanji`` (min): CJK ideographs.
* ``include`` / ``exclude`` (list): case-folded substrings that must / must not occur.
* ``bullets`` (n): exactly n non-empty lines, each starting with ``- `` (nothing else in the file except the title line when a
  ``title`` constraint is present).
* ``title``: the first line starts with ``# `` and is not empty after it.
* ``no_latin``: no ASCII letters.   ``no_ascii_digits``: no 0-9.   ``no_han``: no CJK ideographs.
* ``kana_only``: every character is hiragana, katakana, the prolonged sound mark, whitespace or one of ``、。！？-#``.
* ``endings`` (list, terms): every sentence ends (before its terminator) with one of the endings.
* ``indic_digits``: at least one Arabic-Indic digit and no ASCII digit.
* ``ar_punct``: no ``,`` ``?`` ``;``; at least one of ``،`` ``؟``.
* ``es_inverted``: every ``?`` / ``!`` is opened by ``¿`` / ``¡`` in the same sentence and at least one question exists.
* ``marks`` (list): every listed character occurs at least once.
* ``fr_spacing``: U+202F before ``? ! ;``, U+00A0 before ``:`` and inside guillemets, never an ordinary space there.
"""
from __future__ import annotations

import json

from fx import Task
from fx.run import merged, run

CHECK_SRC = r'''
import json
import re
import sys
import unicodedata
from pathlib import Path

PATH = __PATH__
CONSTRAINTS = json.loads(__CONSTRAINTS__)


def fold(s):
    return unicodedata.normalize("NFC", s).casefold()


def runs(text, terms):
    return re.findall("[" + re.escape(terms) + "]+", text)


def split_sentences(text, terms):
    parts = re.split("[" + re.escape(terms) + "]+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def check(kind, p, text):
    """Return an error string or None."""
    body = text.strip()
    if kind == "sentences":
        terms = p["terms"]
        if not body or body[-1] not in terms:
            return "the text must end with a sentence terminator (%s)" % terms
        n = len(runs(body, terms))
        if not p["min"] <= n <= p["max"]:
            return "%d sentences, expected %d to %d" % (n, p["min"], p["max"])
    elif kind == "chars":
        n = len(re.sub(r"\s", "", body))
        if not p["min"] <= n <= p["max"]:
            return "%d characters (without whitespace), expected %d to %d" % (n, p["min"], p["max"])
    elif kind == "words":
        n = len([w for w in body.split() if re.search(r"\w", w)])
        if not p["min"] <= n <= p["max"]:
            return "%d words, expected %d to %d" % (n, p["min"], p["max"])
    elif kind == "syllables":
        n = len(re.findall("[가-힣]", body))
        if not p["min"] <= n <= p["max"]:
            return "%d Hangul syllables, expected %d to %d" % (n, p["min"], p["max"])
    elif kind == "kanji":
        n = len(re.findall("[一-鿿]", body))
        if n < p["min"]:
            return "%d kanji, expected at least %d" % (n, p["min"])
    elif kind == "include":
        low = fold(body)
        miss = [w for w in p["words"] if fold(w) not in low]
        if miss:
            return "missing: %s" % ", ".join(miss)
    elif kind == "exclude":
        low = fold(body)
        bad = [w for w in p["words"] if fold(w) in low]
        if bad:
            return "forbidden: %s" % ", ".join(bad)
    elif kind == "bullets":
        lines = [ln for ln in body.split("\n") if ln.strip()]
        if any(c["kind"] == "title" for c in CONSTRAINTS):
            lines = lines[1:]   # the title line is not a bullet
        if len(lines) != p["n"] or not all(ln.startswith("- ") and ln[2:].strip() for ln in lines):
            return "expected exactly %d bullet lines starting with '- ' and nothing else (got %d lines)" % (p["n"], len(lines))
    elif kind == "title":
        first = body.split("\n", 1)[0]
        if not (first.startswith("# ") and first[2:].strip()):
            return "the first line must be a '# ' title"
    elif kind == "no_latin":
        m = re.search("[A-Za-z]", body)
        if m:
            return "Latin letter %r found" % m.group()
    elif kind == "no_ascii_digits":
        m = re.search("[0-9]", body)
        if m:
            return "ASCII digit %r found" % m.group()
    elif kind == "no_han":
        m = re.search("[一-鿿]", body)
        if m:
            return "ideograph %r found" % m.group()
    elif kind == "kana_only":
        for ch in body:
            if ch.isspace() or ch in "、。！？ー-#":
                continue
            name = unicodedata.name(ch, "")
            if not (name.startswith("HIRAGANA") or name.startswith("KATAKANA")):
                return "character %r is not hiragana/katakana" % ch
    elif kind == "endings":
        for s in split_sentences(body, p["terms"]):
            if not any(s.endswith(e) for e in p["endings"]):
                return "sentence %r does not end with one of %s" % (s, " ".join(p["endings"]))
    elif kind == "indic_digits":
        if re.search("[0-9]", body) or not re.search("[٠-٩]", body):
            return "numbers must be written with Arabic-Indic digits (at least one) and no ASCII digits"
    elif kind == "ar_punct":
        if re.search("[,?;]", body) or not re.search("[،؟]", body):
            return "use the Arabic comma and question mark, not , ? ;"
    elif kind == "es_inverted":
        questions = 0
        for sent in re.findall(r"[^.?!]*[?!]", body):
            opener = "\u00bf" if sent[-1] == "?" else "\u00a1"
            if opener not in sent:
                return "sentence %r lacks its opening %s" % (sent.strip(), opener)
            questions += sent[-1] == "?"
        if questions < 1:
            return "at least one question is required"
    elif kind == "marks":
        miss = [m for m in p["marks"] if m not in body]
        if miss:
            return "missing mark(s): %s" % " ".join(miss)
    elif kind == "fr_spacing":
        N, T = " ", " "
        for i, ch in enumerate(body):
            if ch in "?!;":
                if i == 0:
                    continue
                prev = body[i - 1]
                if prev in "?!;":
                    continue
                if prev != T:
                    return "expected U+202F before %r at %d" % (ch, i)
                if i >= 2 and body[i - 2] in "   ":
                    return "double space before %r at %d" % (ch, i)
            elif ch == ":":
                if i == 0:
                    continue
                prev = body[i - 1]
                nxt = body[i + 1] if i + 1 < len(body) else ""
                if prev.isdigit() and nxt.isdigit():
                    continue
                if body[i + 1:i + 3] == "//":
                    continue
                if prev != N:
                    return "expected U+00A0 before ':' at %d" % i
            elif ch == "«":
                if body[i + 1:i + 2] != N:
                    return "expected U+00A0 after the opening guillemet"
            elif ch == "»":
                if body[i - 1:i] != N:
                    return "expected U+00A0 before the closing guillemet"
        if " ?" in body or " !" in body or " ;" in body or " :" in body:
            return "an ordinary space stands before ? ! ; or :"
    else:
        return "unknown constraint %r" % kind
    return None


def main():
    f = Path(PATH)
    if not f.is_file():
        print("FAIL: %s does not exist" % PATH)
        return 1
    try:
        text = f.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print("FAIL: %s is not valid UTF-8" % PATH)
        return 1
    errors = []
    for c in CONSTRAINTS:
        err = check(c["kind"], c, text)
        if err:
            errors.append("%s: %s" % (c["kind"], err))
    if errors:
        print("\n".join("FAIL " + e for e in errors))
        return 1
    print("ok")
    return 0


sys.exit(main())
'''


def checker(path: str, constraints: list[dict]) -> str:
    return CHECK_SRC.replace("__PATH__", json.dumps(path)).replace("__CONSTRAINTS__", repr(json.dumps(constraints, ensure_ascii=False)))


def writing_task(slug: str, difficulty: int, prompt: str, facts: dict[str, str], path: str, constraints: list[dict], solution: str,
                 tags: list[str], notes: dict) -> Task:
    """One constrained-writing fixture, verified at build time (the solution passes, the untouched start fails)."""
    check = checker(path, constraints)
    start = dict(facts)
    sol = {path: solution if solution.endswith("\n") else solution + "\n"}
    ok = run(merged(start, sol, {".check/check.py": check}), "python3 .check/check.py", timeout=30)
    if not ok.ok:
        raise RuntimeError("writing scenario %s: the reference solution fails its own checker:\n%s" % (slug, ok.out))
    bad = run(merged(start, {".check/check.py": check}), "python3 .check/check.py", timeout=30)
    if bad.ok:
        raise RuntimeError("writing scenario %s: the checker passes on the untouched start" % slug)
    return Task(slug=slug, prompt=prompt, difficulty=difficulty, start=start, hidden={".check/check.py": check}, solution=sol,
                verify="python3 .check/check.py", kind="feature", lang="text", tags=["native", "writing", *tags], notes=notes)
