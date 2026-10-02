"""Predict what a small regex/format pipeline does to inputs (python, javascript, ruby, go agree on every example; RE2-safe patterns only)."""
from __future__ import annotations

from fx import family

from . import _check as C
from . import _fam as F
from . import _text as T
from . import _voice as V

L4 = ["python", "javascript", "ruby", "go"]


def _j(*parts) -> str:
    return " ".join(x for x in parts if x)


@family("explain-text-transform", category="explain", lang="mixed", kind="greenfield", n=10,
        summary="regex substitution and padding pipelines: output for new inputs the file does not contain, or how many distinct results the data file produces")
def text_transform(rng, n):
    langs = F.lang_plan(rng, n, L4)
    tiers = F.tier_plan(rng, n, (8, 24, 32, 24, 12))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        files, ins, outs, cmd, steps, extra = T.build(rng, lang, tier, {1: 5, 2: 6, 3: 8, 4: 10, 5: 14}[tier])
        mode = "new-input" if (tier <= 3 or rng.random() < 0.6) else "distinct"
        if mode == "new-input":
            labels = ["A", "B", "C"][: len(extra)]
            ans = {lb: res for lb, (_, res) in zip(labels, extra)}
            listing = "; ".join(f"{lb} = `{raw}`" for lb, (raw, _) in zip(labels, extra))
            ask = rng.choice([
                f"`clean()` in this repo normalises the codes in `data/inputs.txt`. What would it return for these new codes: {listing}? Give each result exactly, without the surrounding brackets the script prints.",
                f"I want to add these codes to `data/inputs.txt` and need to know their canonical forms in advance: {listing}. What does `clean()` produce for each? (Just the string, not the `i: [..]` wrapper.)",
            ])
            spec = C.json_spec({"results": C.jf("map", ans, sub="str", knorm="exact", norm="exact")})
            fmt = "Write `answer.json` as {\"results\": {\"A\": \"...\", \"B\": \"...\"}} keyed by the letters above, with the exact result strings."
            obj = {"results": ans}
            d = F.clamp(tier)
        else:
            dist = len(set(outs))
            spec = C.json_spec({"distinct": C.jf("int", dist)})
            ask = rng.choice([
                f"How many *different* canonical codes does `clean()` produce for the {len(ins)} lines of `data/inputs.txt`? (Two lines that normalise to the same string count once.)",
                f"Of the {len(ins)} raw codes in `data/inputs.txt`, how many distinct strings come out after `clean()`?",
            ])
            fmt = "Write `answer.json` as {\"distinct\": N}."
            obj = {"distinct": dist}
            d = F.clamp(tier)
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "Two systems disagree about the canonical form of some codes.", "Preparing a migration of old item codes."]), tag="TXT")
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{mode}", prompt=prompt, difficulty=d, start=files, spec=spec, answer=obj, lang=lang,
                          tags=["regex", "format", mode, "answer-json"], notes={"tier": tier, "mode": mode, "steps": [s.kind for s in steps]})
