"""The data path of a field through a record pipeline: the exact output record for an input, or which input fields a final field is computed from."""
from __future__ import annotations

from fx import family

from . import _check as C
from . import _fam as F
from . import _flow as W
from . import _voice as V

L3 = ["python", "javascript", "ruby"]


def _j(*parts) -> str:
    return " ".join(x for x in parts if x)


@family("explain-field-dataflow", category="explain", lang="mixed", kind="greenfield", n=10,
        summary="record pipeline stages that set, rename, default and drop fields: the output record for one input, or the input fields a result field really depends on")
def dataflow(rng, n):
    langs = F.lang_plan(rng, n, L3)
    tiers = F.tier_plan(rng, n, (6, 22, 34, 24, 14))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        mode = "record" if tier <= 2 or rng.random() < 0.5 else "lineage"
        for _ in range(60):
            fl = W.make_flow(rng, lang, tier)
            files, cmd = W.render(fl)
            rec = W.random_record(rng, fl)
            want = W.simulate(fl, rec)
            try:
                real = W.run_real(fl, files, cmd, rec)
            except RuntimeError:
                continue
            if real != want:
                continue
            if mode == "lineage":
                ends = sorted(want)
                cands = []
                for t in ends:
                    ln = W.lineage(fl, t)
                    if 1 <= len(ln) < len(fl.inputs):
                        cands.append((t, ln))
                if not cands or len(fl.inputs) - min(len(l) for _, l in cands) < 1:
                    continue
                target, ln = rng.choice(cands)
            break
        else:
            raise RuntimeError("dataflow: nothing suitable")
        fw = {"python": "dict", "javascript": "object", "ruby": "hash"}[lang]
        stages = " -> ".join(st.name for st in fl.stages)
        if mode == "record":
            shown = W.json.dumps(rec, sort_keys=True)
            ask = rng.choice([
                f"I feed the record `{shown}` through the pipeline in `{fl.pkg}` (`{cmd} '<json>'`). What is the complete record that comes out the other end? List every field with its final value.",
                f"What does the pipeline return for the input `{shown}`? I need every field of the output record, including ones the stages created, and none of the ones they renamed away or dropped.",
            ])
            spec = C.json_spec({"record": C.jf("map", want, sub="int", knorm="exact")})
            fmt = "Write `answer.json` as {\"record\": {\"field\": value, ...}} with all fields of the final record."
            obj = {"record": want}
            d = F.clamp(tier)
        else:
            ans = sorted(ln)
            ask = rng.choice([
                f"In the final record, which of the *input* fields does `{target}` get its value from? Count a field if `{target}` is computed from it (even through a rename, `min`/`max`, or because a condition on it guards an assignment), and ignore fields that never reach it.",
                f"Trace `{target}` backwards through the stages. Which input fields can influence its final value? Follow renames, and count a field that only appears in an `if` guarding an assignment.",
            ])
            spec = C.json_spec({"inputs": C.jf("set", ans, norm="exact")})
            fmt = f"Write `answer.json` as {{\"inputs\": [\"field\", ...]}} using the input field names: {', '.join(fl.inputs)}."
            obj = {"inputs": ans}
            d = F.clamp(tier)
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "A downstream report shows a surprising number.", "I want to know what to validate on the way in."]), tag="FLW")
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{mode}", prompt=prompt, difficulty=d, start=files, spec=spec, answer=obj, lang=lang,
                          tags=["data-flow", mode, "answer-json"], notes={"tier": tier, "mode": mode, "stages": len(fl.stages), "inputs": fl.inputs})
