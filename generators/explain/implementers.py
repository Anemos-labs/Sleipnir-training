"""Which types satisfy an interface? Go's structural method sets (pointer receivers, signatures, embedding), Rust trait impls, Java's nominal typing, Python protocols and ABCs."""
from __future__ import annotations

from fx import family

from . import _check as C
from . import _fam as F
from . import _ifaces as N
from . import _voice as V

L4 = ["go", "rust", "java", "python"]


def _j(*parts) -> str:
    return " ".join(x for x in parts if x)


@family("explain-implementers", category="explain", lang="mixed", kind="greenfield", n=12,
        summary="which types satisfy an interface/trait/protocol: go method sets with pointer receivers and embedding, rust impl blocks, java nominal typing, python protocols and ABCs")
def implementers(rng, n):
    langs = F.lang_plan(rng, n, L4)
    tiers = F.tier_plan(rng, n, (8, 24, 32, 24, 12))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        for _ in range(60):
            mdl = N.make_model(rng, lang, tier)
            files = N.render(mdl)
            pointer = lang == "go" and tier >= 2 and rng.random() < 0.3
            cands = []
            try:
                for ifc in mdl.ifaces:
                    if lang == "python":
                        ans = N.python_implementers(mdl, files, ifc.name)
                    else:
                        ans = N.implementers(mdl, ifc.name, pointer)
                    if 1 <= len(ans) <= max(3, len(mdl.types) - 2) and len(ans) != len(mdl.types):
                        cands.append((ifc.name, ans))
            except RuntimeError:
                continue
            if cands:
                break
        else:
            raise RuntimeError("implementers: no model")
        iname, ans = rng.choice(cands)
        unit = {"go": "types", "rust": "types", "java": "classes", "python": "classes"}[lang]
        if lang == "go":
            how = ("a pointer to the type (`&T{}`)" if pointer else "a plain value of the type (`T{}`, not a pointer)")
            ask = rng.choice([
                f"Which types in the `{mdl.pkg}` package can be assigned to a variable of the interface type `{iname}` when you use {how}? Remember method sets and exact signatures.",
                f"List the types whose values satisfy `{iname}`, using {how}. Count promoted methods from embedded structs, and watch receivers and signatures.",
            ])
        elif lang == "rust":
            ask = rng.choice([
                f"Which types implement the trait `{iname}`? Only count real `impl {iname} for ...` blocks, not types that merely have methods with the same names.",
                f"List every type that implements `{iname}` (an explicit trait impl). Types with inherent methods of the same names do not count.",
            ])
        elif lang == "java":
            ask = rng.choice([
                f"Which classes are `{iname}`s, meaning an instance of the class can be assigned to a variable of type `{iname}`? Include classes that qualify through a superclass or through an interface that extends `{iname}`.",
                f"Name every class that `instanceof {iname}` would accept for a new instance, through any chain of `extends`/`implements`. Having the right method names is not enough in Java.",
            ])
        else:
            kind = "structural `Protocol` check" if mdl.style == "protocol" else "ABC `isinstance`/`register` check"
            ask = rng.choice([
                f"For which classes does `isinstance(obj, {iname})` return True when `obj` is an instance of the class, in this project ({kind})?",
                f"Which classes in `{mdl.pkg}/types.py` give `isinstance(Cls(), {iname})` -> True? Think about how `{iname}` is defined here.",
            ])
        spec = C.json_spec({"types": C.jf("set", ans, norm="name")})
        fmt = f"Write `answer.json` as {{\"types\": [\"Name\", ...]}}, each name once, order irrelevant."
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "The compiler accepts one assignment I did not expect.", "Reviewing a PR that adds a new implementation."]), tag=mdl.pkg[:3].upper())
        d = F.clamp(tier)
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{iname.lower()}", prompt=prompt, difficulty=d, start=files, spec=spec, answer={"types": ans}, lang=lang,
                          tags=["interfaces", lang, "answer-json"], notes={"tier": tier, "interface": iname, "pointer": pointer, "types": len(mdl.types)})
