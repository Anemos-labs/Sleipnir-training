"""project-codemod-go: retire a legacy helper package (`oldkit`) from a 20-40 module Go application by moving every call site to
the replacement package (`kit`), with output unchanged.  Each module is its own `package main` under app/ and is scored on its
own (build and output with the legacy package poisoned; no mention of it left in the source)."""
from __future__ import annotations

from fx import family

from generators.project import _cm_go as A
from generators.project import _kit as K

PLAN = [
    dict(n_modules=18, shapes=False, common=False, common_share=0.0, cur="EUR", unit="pc", log=("[", "]"), title="each", min_snip=3, max_snip=4),
    dict(n_modules=22, shapes=True, common=False, common_share=0.0, cur="GBP", unit="ea", log=("<", ">"), title="first", min_snip=3, max_snip=5),
    dict(n_modules=24, shapes=True, common=True, common_share=0.5, cur="USD", unit="pc", log=("(", ")"), title="each", min_snip=3, max_snip=5),
    dict(n_modules=26, shapes=True, common=False, common_share=0.0, cur="CHF", unit="unit", log=("{", "}"), title="first", min_snip=4, max_snip=5),
    dict(n_modules=28, shapes=True, common=True, common_share=0.35, cur="EUR", unit="ea", log=("[", "]"), title="each", min_snip=4, max_snip=5),
    dict(n_modules=20, shapes=True, common=True, common_share=0.6, cur="GBP", unit="unit", log=("<", ">"), title="first", min_snip=3, max_snip=5),
    dict(n_modules=32, shapes=True, common=False, common_share=0.0, cur="USD", unit="pc", log=("(", ")"), title="each", min_snip=4, max_snip=5),
    dict(n_modules=36, shapes=True, common=True, common_share=0.25, cur="CHF", unit="ea", log=("{", "}"), title="first", min_snip=4, max_snip=5),
]

VOICES = [
    "The `oldkit` package is being deleted and every module under `app/` still imports it: plain imports, renamed imports, a dot-import, function values passed around. Please move all of `app/` to the `kit` package described in `README.md`, keeping what each module prints exactly the same. `python3 tests/run_examples.py` runs a few of the modules; the real check swaps in a poisoned `oldkit` and runs all of them.",
    "migrate app/ from oldkit to kit, the table and the traps are in README.md. each module under app/ is its own main package and must print exactly what it printed before. don't touch kit/, model/ or tests/. a script for the edits is fine if you check the result with `go run ./app/<name>`",
    "Ticket MIG-{num}: retire package `oldkit`.\n\nAcceptance: with `oldkit` replaced by a package whose functions all panic, `go run ./app/<module>` prints the same lines as before for every module, and no file under `app/` mentions `oldkit` any more. `kit` is finished and read-only; README.md has the mapping.",
    "We are replacing our homegrown helper package by `kit`. Could you port the whole `app/` tree? The README lists each old function and its replacement, including where the types change (a `bool` becomes an `error`, a map becomes a slice of groups, variadic key/value pairs become a `kit.F`). Compare the output of every module before and after.",
    "Port the application to `kit`. README.md is the migration guide. Every module is a small program under `app/<name>/`; some import `oldkit` normally, some under an alias, one style uses a dot import, and some go through the shared `app/common` wrappers. Hidden checks build and run each module on its own, so a half-finished migration still earns credit for the modules that are done.",
    "Deprecation sweep: oldkit -> kit across app/. See README.md. Output must stay identical. Watch out: `Pad` now takes an alignment constant that points the opposite way from the old function names, `FmtAmount` had a default currency, and `Pick` takes a slice.",
    "can you do the oldkit -> kit migration described in README.md? there are a lot of modules, so write a script if you want, but run every module before and after and diff. nothing else should change",
    "`oldkit` is retired. Every module under `app/` has to use `kit` instead, with identical output. README.md documents the mapping. Hidden checks run each module with `oldkit` disabled (it panics) and scan the sources for the old name, so leftover imports count against you.",
]


def readme(p: dict, mods: list[str], with_common: bool) -> str:
    cur, unit = p["cur"], p["unit"]
    o = []
    w = o.append
    w("# Retiring `oldkit`\n")
    w(f"The application under `app/` is a collection of {len(mods)} small demo programs (`app/{mods[0]}`, `app/{mods[1]}`, ...). Each one is its own `package main` that formats prices, parses quantities, reads rate tables, groups records, logs events and so on, "
      "and prints a few lines. Run one with `go run ./app/NAME`. All modules share the module `shop` (`go.mod`), the record type in `model/`, and two helper packages: the old `oldkit/` and the new `kit/`.\n")
    w("Everything was written against `oldkit`, which is now deprecated. Its replacement, the package `kit`, is complete: **do not edit anything under `kit/`, `model/` or `tests/`**. "
      "`oldkit/oldkit.go` itself stays in the repository for now (files cannot be deleted in this job) but nothing may import it any more.\n")
    w("## What has to be true afterwards\n")
    w("1. For every module, `go run ./app/NAME` builds and prints **exactly** what it printed before the migration (byte for byte), exit status 0.")
    w("2. The migrated code works when `oldkit` is replaced by a package with the same exported names in which every function panics (that is how the checks run it: any call that still goes to `oldkit` kills the module).")
    w("3. The text `oldkit` does not appear in any file under `app/` (imports, comments and strings included), and the files that used it now use `kit` (or `app/common`).")
    w("\nThe score is the average of two shares: the share of modules that still build and print the right output with `oldkit` disabled, and the share of files under `app/` that no longer mention `oldkit`.\n")
    w("## The mapping\n")
    w("| `oldkit` | `kit` | what is different |")
    w("|---|---|---|")
    w(f"| `FmtAmount(cents int, cur ...string) string` | `kit.Money{{Cents: cents, Cur: cur}}.Text()` | `Cur` is not optional: the old default was `\"{cur}\"`. |")
    w("| `ParseQty(text) (count int, unit string, ok bool)` | `kit.ParseQty(text) (kit.Qty, error)` with `Qty{Count, Unit}` | an `error` replaces the `ok` flag (nil means success). |")
    w("| `PadRight(s, width)` | `kit.Pad(s, width, kit.AlignLeft)` | the old name says where the *padding* goes, the alignment says where the *text* goes. |")
    w("| `PadLeft(s, width)` | `kit.Pad(s, width, kit.AlignRight)` | same remark. |")
    w("| `Title(s)` | `kit.TitleCase(s)` | |")
    w("| `CompareNames(a, b) int` | `kit.CompareNames(a, b)` | |")
    w("| `Pick(m, keys ...string) any` | `kit.Dig(m, path []string, def any) any` | the keys are one `[]string`; `def` is returned for a missing key (the old function returned `nil`). |")
    w("| `Take(xs, n)` | `kit.First(xs, n)` | |")
    w("| `GroupBy(items, key) oldkit.Groups` with fields `Keys` (first-seen order) and `M` (key -> items) | `kit.GroupBy(items, key) []kit.Group` with fields `Key` and `Items`, in first-seen order | a slice of buckets replaces the keys-plus-map pair. |")
    w("| `Log(level, msg string, kv ...any) string` appends to a global buffer and returns the line | `kit.Default().Emit(level, msg, kit.F{...})` appends to the shared `Events` and returns **nothing**; `kit.Default().Last()` is the most recent line | the key/value pairs become a `kit.F` map. |")
    w("| `FlushLog() []string` | `kit.Default().Drain()` | returns the lines and clears them. |")
    w("| `Clamp(x, lo, hi)` | `kit.Limit(x, lo, hi)` | |")
    w("\nFunctions are also passed around as values (`oldkit.Title` handed to a helper, `[]func(string, int) string{oldkit.PadRight, oldkit.PadLeft}`), and modules import the old package in several styles "
      "(`\"shop/oldkit\"`, `ok \"shop/oldkit\"`, `. \"shop/oldkit\"`)." +
      (" Part of the application goes through `app/common`, a package of thin wrappers around `oldkit`; the modules that import it need no change if you rewrite `common` (keeping its exported names and signatures) on top of `kit`, or you may migrate those modules directly." if with_common else ""))
    w("\nRead `oldkit/oldkit.go` for the exact behaviour of each old function (defaults, formats): the new code must reproduce it. Mind Go's usual rules (an unused import or variable is a compile error).\n")
    w("## How to check your work\n")
    w("* Run every module before you start (`for d in app/*/; do go run ./$d; done > before.txt`) and again at the end: the outputs must be identical.")
    w("* `python3 tests/run_examples.py` compares a few modules with the expected output (the real checks cover every module and run with `oldkit` disabled).")
    return "\n".join(o) + "\n"


@family("project-codemod-go", category="project", lang="go", kind="refactor", n=8,
        summary="move a 20-40 module Go application from a retired helper package to a new one: import aliases, dot-imports, function values, changed return types")
def gen(rng, n):
    for i in range(n):
        p = dict(PLAN[i])
        app = A.build_app(rng, p)
        start = dict(app["start"])
        mods = app["modules"]
        with_common = p["common"]
        start["README.md"] = readme(p, mods, with_common)
        cases = []
        for k, m in enumerate(mods):
            cases.append(K.Case(name=f"module-{m}", group="behaviour", args=[f"./app/{m}"], visible=k in (0, len(mods) // 2, len(mods) - 1)))
        files = [f"app/{m}/main.go" for m in mods] + (["app/common/common.go"] if with_common else [])
        for f in files:
            name = f.split("/")[1]
            direct = name in app["direct"] or name == "common"
            st = {"path": f, "forbid": "oldkit"}
            if direct:
                st["require"] = "kit|common"
            cases.append(K.Case(name="clean-" + name, group="static", static=st))
        prompt = VOICES[i % len(VOICES)].format(num=3500 + i * 17)
        yield K.codemod_task(
            start=start, solution=app["solution"], hidden_extra={"oldkit/oldkit.go": A.POISON}, cases=cases,
            program=("", ["go", "-C", "@/", "run"]), lang="go", tool="shop",
            prompt=prompt, difficulty=5 if p["n_modules"] >= 30 else 4, slug=f"{i + 1:02d}-{p['n_modules']}mods-{p['cur'].lower()}{'-common' if with_common else ''}",
            notes={"modules": p["n_modules"], "shapes": p["shapes"], "common": with_common, "cur": p["cur"], "unit": p["unit"], "log": list(p["log"]), "title": p["title"]},
            tags=["codemod", "api-migration"], protected=["kit/**", "model/**", "go.mod"],
        )
