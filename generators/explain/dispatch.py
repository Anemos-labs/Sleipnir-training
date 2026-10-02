"""Which method body runs? Overrides, super calls, virtual calls from a parent method, python MRO, ruby include/prepend."""
from __future__ import annotations

from fx import family

from . import _check as C
from . import _fam as F
from . import _oop as O
from . import _voice as V

L4 = ["python", "javascript", "java", "ruby"]


def _j(*parts) -> str:
    return " ".join(x for x in parts if x)


def _build(rng, lang, tier):
    cap = {1: 6, 2: 10, 3: 14, 4: 20, 5: 28}[tier]
    floor = {1: 2, 2: 3, 3: 5, 4: 7, 5: 9}[tier]
    for _ in range(40):
        h = O.make_hier(rng, lang, tier)
        files = O.render(h)
        calls, value = O.run_hier(h, files)
        if floor <= len(calls) <= cap:
            return h, files, calls, value
    raise RuntimeError("dispatch: no hierarchy of the right size")


def _entry_text(h: O.Hier) -> str:
    return f"`{h.entry_cls}` object and calls its `{h.entry_method}()` method"


@family("explain-method-dispatch", category="explain", lang="mixed", kind="greenfield", n=12,
        summary="which method bodies run, in order, for one call on an object (overrides, super, virtual calls, python MRO, ruby include/prepend); also MRO lists")
def dispatch(rng, n):
    langs = F.lang_plan(rng, n, L4)
    tiers = F.tier_plan(rng, n, (6, 22, 32, 26, 14))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        h, files, calls, value = _build(rng, lang, tier)
        mode = "trace"
        if tier >= 3 and lang in ("python", "ruby") and rng.random() < 0.4:
            mode = "mro"
        elif tier <= 1:
            mode = "first"
        fw = "method"
        cmd = O.cmd_for(h)
        if mode == "trace":
            spec = C.json_spec({"calls": C.jf("list", calls, norm="exact"), "value": C.jf("int", value, 0.5)})
            ask = rng.choice([
                f"The program (`{cmd}`) creates a {_entry_text(h)}. Which method bodies run, in the order they start, and what number does the call return? Every body logs `Class.method` when it begins.",
                f"Trace one call: `{cmd}` builds a {_entry_text(h)}. List the `Class.method` entries that get logged, in order, and the final value it prints.",
            ])
            fmt = "Write `answer.json` as {\"calls\": [\"Class.method\", ...], \"value\": N}."
            obj = {"calls": calls, "value": value}
            d = F.clamp(tier)
        elif mode == "first":
            spec = C.json_spec({"first": C.jf("str", calls[0], norm="exact")})
            ask = f"When `{cmd}` creates a {_entry_text(h)}, which implementation runs first? Give it as `Class.method`."
            fmt = "Write `answer.json` as {\"first\": \"Class.method\"}."
            obj = {"first": calls[0]}
            d = 1
        else:
            target = h.entry_cls if lang == "python" else h.entry_cls
            mro = O.mro_of(h, files, target)
            term = "method resolution order (the `__mro__`)" if lang == "python" else "`ancestors` chain"
            spec = C.json_spec({"order": C.jf("list", mro, norm="exact")})
            ask = rng.choice([
                f"What is the {term} of `{target}` in this project? Only list classes and modules that are defined in the repo, from `{target}` itself down to the root.",
                f"Give me the lookup order Python/Ruby uses for methods of `{target}`: the {term}, restricted to this project's own classes and modules.",
            ]).replace("Python/Ruby", "the interpreter")
            fmt = "Write `answer.json` as {\"order\": [\"Name\", ...]} with the first class searched first."
            obj = {"order": mro}
            d = F.clamp(tier)
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "I'm trying to understand why a subclass override seems to be ignored.", "Debugging a surprising total."]), tag=h.pkg[:3].upper())
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{mode}", prompt=prompt, difficulty=d, start=files, spec=spec, answer=obj, lang=lang,
                          tags=["dispatch", mode, "answer-json"], notes={"tier": tier, "mode": mode, "classes": len(h.classes), "entry": h.entry_cls, "method": h.entry_method})


@family("explain-dispatch-value", category="explain", lang="mixed", kind="trace", n=8, mode="answer",
        summary="what number does a method call on an object of a subclass return (overrides, super, virtual calls)")
def dispatch_value(rng, n):
    langs = F.lang_plan(rng, n, L4)
    tiers = F.tier_plan(rng, n, (8, 24, 32, 24, 12))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        h, files, calls, value = _build(rng, lang, tier)
        cmd = O.cmd_for(h)
        mode = rng.choice(["value", "count"])
        label = rng.choice(["Value", "Result", "Returns"])
        if mode == "value":
            contains = [f"{label}: [{value}]"]
            ask = rng.choice([
                f"`{cmd}` creates a {_entry_text(h)} and prints the returned number at the end. What number is that?",
                f"What does `{h.entry_cls}().{h.entry_method}()` return in this project? Work it out from the class hierarchy.",
            ])
            fmt = f"End your reply with `{label}: [N]`."
            gold = f"{label}: [{value}]"
        else:
            contains = [f"Bodies: [{len(calls)}]"]
            ask = rng.choice([
                f"How many method bodies run in total (counting repeated runs of the same body) when `{cmd}` makes its one call on a {_entry_text(h)}?",
                f"Count the method invocations that happen during `{h.entry_cls}().{h.entry_method}()`, including nested calls to parent and virtual methods.",
            ])
            fmt = "End your reply with `Bodies: [N]`."
            gold = f"Bodies: [{len(calls)}]"
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "My unit test expects a different total."]), tag=h.pkg[:3].upper())
        yield C.say_task(slug=f"{i + 1:02d}-{lang}-{mode}", prompt=prompt, difficulty=F.clamp(tier), start=files, contains=contains,
                         gold=gold, lang=lang, tags=["dispatch", mode], notes={"tier": tier, "mode": mode, "classes": len(h.classes)})
