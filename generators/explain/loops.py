"""Loop-reading puzzles over a data file: chunking, windows, strides, inclusive bounds, reverse scans, early exit, pair search (python, javascript, go, ruby)."""
from __future__ import annotations

from fx import family

from . import _check as C
from . import _fam as F
from . import _loops as L
from . import _voice as V


def _j(*parts) -> str:
    return " ".join(x for x in parts if x)


@family("explain-loop-reading", category="explain", lang="mixed", kind="greenfield", n=10,
        summary="off-by-one and bounds reading: what a loop-based report prints for the readings file (chunks, windows, strides, inclusive ranges, reverse scans, early exit, pairs)")
def loop_reading(rng, n):
    langs = F.lang_plan(rng, n, L.LANGS)
    tiers = F.tier_plan(rng, n, (14, 26, 30, 20, 10))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        files, lines, cmd, tpls, items = L.build(rng, lang, tier)
        mode = "output" if (tier <= 2 or len(lines) <= 8 or rng.random() < 0.5) else "summary"
        if mode == "output":
            spec = C.json_spec({"lines": C.jf("list", lines, norm="exact")})
            ask = rng.choice([
                f"`{cmd}` reads `data/readings.txt` and prints a report. What exactly does it print? Every line, in order.",
                f"Predict the output of `{cmd}` for the readings in `data/readings.txt`, line by line (careful with the loop bounds).",
            ])
            fmt = "Write `answer.json` as {\"lines\": [\"first line\", ...]}, each line exactly as printed."
            obj = {"lines": lines}
            d = tier
        else:
            spec = C.json_spec({"count": C.jf("int", len(lines)), "last": C.jf("str", lines[-1], 0.5, norm="exact")})
            ask = rng.choice([
                f"How many lines does `{cmd}` print for `data/readings.txt`, and what is the last one?",
                f"I only need two facts about the output of `{cmd}` on the current readings: the number of lines printed and the text of the last line.",
            ])
            fmt = "Write `answer.json` as {\"count\": N, \"last\": \"the last line exactly as printed\"}."
            obj = {"count": len(lines), "last": lines[-1]}
            d = tier
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "I suspect an off-by-one in one of the loops.", "The summary is missing a row and I don't know whether the data or the code is at fault."]), tag="LOP")
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{mode}-{len(tpls)}loops", prompt=prompt, difficulty=F.clamp(d), start=files, spec=spec, answer=obj, lang=lang,
                          tags=["loops", "off-by-one", mode, "answer-json"], notes={"tier": tier, "mode": mode, "loops": [t for t, _ in tpls], "readings": len(items)})
