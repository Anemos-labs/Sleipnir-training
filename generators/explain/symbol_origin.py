"""Where does a re-exported name really come from? Package facades with renames, later imports that override earlier ones, star imports and fallbacks."""
from __future__ import annotations

from fx import family

from . import _check as C
from . import _fam as F
from . import _reexport as R
from . import _voice as V

L3 = ["python", "javascript", "rust"]


def _j(*parts) -> str:
    return " ".join(x for x in parts if x)


@family("explain-symbol-origin", category="explain", lang="mixed", kind="lookup", n=10, mode="answer",
        summary="a client imports a name from a package facade: which file really defines the function it calls, and under what name (python, javascript, rust re-exports)")
def symbol_origin(rng, n):
    langs = F.lang_plan(rng, n, L3)
    tiers = F.tier_plan(rng, n, (8, 22, 32, 24, 14))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        files, x, truth, cmd = R.build(rng, lang, tier)
        path, orig = truth.split(":", 1)
        client = {"python": "app.py", "javascript": "app.js", "rust": "src/main.rs"}[lang]
        how = {"python": f"`{client}` does `from <package> import {x}` and then calls `{x}()`.", "javascript": f"`{client}` does `const {{ {x} }} = require('./index')` and then calls `{x}()`.",
               "rust": f"`{client}` calls `<crate>::{x}()`."}[lang]
        ask = rng.choice([
            f"{how} Which source file contains the function that actually runs, and what is that function called where it is defined?",
            f"When `{cmd}` calls `{x}()` in `{client}`, whose code is that? Follow the re-exports and tell me the defining file and the function's original name.",
            f"I can't tell which implementation `{x}` resolves to in `{client}`: several files define something with that name. Give me the file where the executed function is defined and its definition name.",
        ])
        fmt = "Reply with two lines at the end: `File: [path]` and `Name: [function name]`, the path relative to the repo root."
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "A bug report says the wrong implementation is used.", "Trying to delete what I think is dead code."]), tag="EXP")
        d = F.clamp(tier)
        yield C.say_task(slug=f"{i + 1:02d}-{lang}-{x}", prompt=prompt, difficulty=d, start=files, contains=[f"File: [{path}]", f"Name: [{orig}]"],
                         gold=f"The call ends up in `{path}`, function `{orig}`.\n\nFile: [{path}]\nName: [{orig}]", lang=lang, tags=["re-exports", lang],
                         notes={"tier": tier, "symbol": x, "files": len(files)})
