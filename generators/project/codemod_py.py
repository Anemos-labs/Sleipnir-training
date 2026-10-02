"""project-codemod-py: retire a legacy helper module (`oldkit`) from a 20-40 module Python application by moving every call site to
the replacement package (`kit`), with output unchanged.  Scored per module: behaviour with the legacy module poisoned, and no
mention of it left in the source."""
from __future__ import annotations

from fx import family

from generators.project import _cm_py as A
from generators.project import _kit as K

THEME = "codemod-py"

PLAN = [
    dict(n_modules=18, shapes=False, common=False, common_share=0.0, cur="EUR", unit="pc", log=("[", "]"), title="each", min_snip=3, max_snip=4),
    dict(n_modules=22, shapes=True, common=False, common_share=0.0, cur="USD", unit="ea", log=("<", ">"), title="first", min_snip=3, max_snip=5),
    dict(n_modules=24, shapes=False, common=True, common_share=0.6, cur="GBP", unit="pc", log=("(", ")"), title="each", min_snip=3, max_snip=4),
    dict(n_modules=26, shapes=True, common=True, common_share=0.35, cur="EUR", unit="unit", log=("[", "]"), title="first", min_snip=4, max_snip=5),
    dict(n_modules=30, shapes=True, common=False, common_share=0.0, cur="CHF", unit="ea", log=("{", "}"), title="each", min_snip=3, max_snip=5),
    dict(n_modules=28, shapes=True, common=True, common_share=0.5, cur="USD", unit="pc", log=("<", ">"), title="each", min_snip=4, max_snip=5),
    dict(n_modules=34, shapes=True, common=False, common_share=0.0, cur="GBP", unit="unit", log=("(", ")"), title="first", min_snip=4, max_snip=5),
    dict(n_modules=36, shapes=True, common=True, common_share=0.25, cur="CHF", unit="pc", log=("[", "]"), title="first", min_snip=4, max_snip=5),
]

VOICES = [
    "The helper module `oldkit` is on its way out and the next sprint deletes it. Every module under `app/` still uses it, in more call shapes than you would think (aliases, callbacks, wrappers, star-arguments). Please move all of `app/` over to the `kit` package described in `README.md` without changing what the application prints. `python3 tests/run_examples.py` runs a few of the demos; the real check poisons `oldkit` and runs all of them.",
    "migrate app/ off oldkit onto kit, see README.md for the mapping and the traps. behaviour must stay byte-identical (python3 run.py <module> prints each module's demo). don't touch kit/, run.py or tests/. a codemod script is fine if you verify it.",
    "Ticket MIG-{num}: retire `oldkit`.\n\nScope: every file in `app/`. Acceptance: (1) with `oldkit` replaced by a stub that raises on every call, `python3 run.py <module>` prints exactly what it printed before, for every module; (2) the text `oldkit` no longer appears in any file under `app/`. `kit/` is complete and must not be changed. The README has the old-to-new table.",
    "We are replacing our homegrown helper module with the new `kit` package, and I need the whole `app/` directory ported. The README lists each old function with its replacement, including the places where the semantics differ (return types, argument order, defaults). Please be careful: the demos print everything, so small differences show up. Start from the visible examples, then check `python3 run.py all` before and after.",
    "Port the application from `oldkit` to `kit`. The README is the migration guide; `run.py` prints the demo of each module so you can diff before/after. Some modules import helpers directly, some under an alias, some pass the functions around as callbacks. Hidden checks run each module separately against a poisoned `oldkit` and also grep for leftovers, so a partial migration still earns partial credit.",
    "Deprecation sweep: `oldkit` -> `kit` across app/. See README.md. Output must not change at all. Heads-up: the old `pad_*` names and the new `align` argument point in opposite directions, and `parse_qty`/`group_by` return different types now.",
    "can you do the oldkit -> kit migration described in README.md? it's a lot of small edits (dozens of modules), so write a script if you like, but check the diff of `python3 run.py all` before and after. nothing else should change",
    "The `oldkit` helper module is being retired. All modules in `app/` must use `kit` instead, with identical output. README.md documents the mapping; `kit/` itself is finished and read-only for this job. Hidden checks run every module's demo with `oldkit` disabled and scan the sources for the old name, so please do not leave imports behind either.",
]


def readme(p: dict, mods: list[str], with_common: bool) -> str:
    cur, unit = p["cur"], p["unit"]
    o = []
    w = o.append
    w("# Retiring `oldkit`\n")
    w(f"The application in `app/` is a collection of {len(mods)} small demo modules (`{mods[0]}`, `{mods[1]}`, ...; the full list is `app.MODULES`). "
      "Each module formats prices, parses quantities, reads rate tables, groups records, logs events and so on, and has a `demo()` function that returns the lines the module prints. "
      "`python3 run.py MODULE` prints the demo of one module (`python3 run.py all` prints all of them). `run.py` exits with status 1 and prints `error: ...` if a demo raises.\n")
    w("All of this was written against `oldkit.py`, a helper module that is now deprecated. Its replacement, the package `kit/`, is complete and tested: **do not edit anything under `kit/`, `run.py` or `tests/`**. "
      "`oldkit.py` itself stays in the repository for now (files cannot be deleted in this job) but nothing may use it any more.\n")
    w("## What has to be true afterwards\n")
    w("1. For every module, `python3 run.py MODULE` prints **exactly** what it printed before the migration (byte for byte), exit status 0.")
    w("2. The migrated code works when `oldkit.py` is replaced by a module in which every function raises `RuntimeError` (that is how the checks run it: any call that still goes to `oldkit` fails the module).")
    w("3. The text `oldkit` does not appear in any file under `app/` (imports, comments and strings included), and the files that used it now use `kit` (or `app.common`).")
    w("\nThe score is the average of two shares: the share of modules whose demo still prints the right output with `oldkit` disabled, and the share of files under `app/` that no longer mention `oldkit`.\n")
    w("## The mapping\n")
    w("| `oldkit` | `kit` | what is different |")
    w("|---|---|---|")
    w(f"| `fmt_amount(cents, cur=\"{cur}\")` | `kit.money.Money(cents, cur).text()` | `cur` is required by `Money`: the old default was `\"{cur}\"`. |")
    w(f"| `parse_qty(text)` gives `(count, unit)` or `None` | `kit.qty.Qty.try_parse(text)` gives a `Qty` with attributes `.count` and `.unit`, or `None`; `kit.qty.Qty.parse(text)` raises `kit.qty.QtyError` instead of returning `None` | a `Qty` is **not** a tuple: no unpacking, no indexing. |")
    w("| `pad_right(s, width)` | `kit.text.pad(s, width, align=\"left\")` | the old name says where the *padding* goes, the new `align` says where the *text* goes. |")
    w("| `pad_left(s, width)` | `kit.text.pad(s, width, align=\"right\")` | same remark. `align` is keyword-only. |")
    w("| `title(s)` | `kit.text.title_case(s)` | |")
    w("| `sort_key(s)` | `kit.text.sort_key(s)` | |")
    w("| `pick(d, *keys, default=None)` | `kit.data.dig(d, keys, default=None)` | the keys are passed as **one tuple** (or other sequence). |")
    w("| `take(seq, n)` | `kit.data.first(seq, n)` | |")
    w("| `group_by(items, keyfn)` gives a `dict` | `kit.data.group(items, key=keyfn)` gives a **list of `(key, items)` pairs**, keys in order of first appearance | `dict(kit.data.group(...))` is the old result. |")
    w("| `log(level, msg, **ctx)` appends to a global buffer and returns the line | `kit.events.default().emit(level, msg, **ctx)` appends to the shared `Events` object and returns **nothing**; `.last()` is the most recent line | |")
    w("| `flush_log()` | `kit.events.default().drain()` | returns the lines and clears them, like the old function. |")
    w("| `clamp(x, lo, hi)` | `kit.data.limit(x, lo, hi)` | |")
    w("\nThe keyword names of the old functions (`cents=`, `cur=`, `s=`, `width=`, `default=`) are still used in some call sites; check the signatures in `kit/` for the new names. "
      "Functions are also passed around as values (`sorted(..., key=oldkit.sort_key)`, `map(oldkit.title, ...)`, `functools.partial(oldkit.pad_left, width=8)`, `reduce`), and modules import the old names in several styles "
      "(`import oldkit`, `import oldkit as ok`, `from oldkit import fmt_amount`, `from oldkit import fmt_amount as money`)." +
      (" Part of the application goes through `app/common.py`, a layer of thin wrappers around `oldkit`; the modules that import it need no change if you rewrite `common` (keeping its function names and signatures) on top of `kit`, or you may migrate those modules directly." if with_common else ""))
    w("\nRead `oldkit.py` for the exact behaviour of each old function (defaults, formats): the new code must reproduce it.\n")
    w("## How to check your work\n")
    w("* `python3 run.py all > before.txt` *before* you start, and again at the end: the two outputs must be identical.")
    w("* `python3 tests/run_examples.py` compares a few modules with the expected output (the real checks cover every module and run with `oldkit` disabled).")
    return "\n".join(o) + "\n"


@family("project-codemod-py", category="project", lang="python", kind="refactor", n=8,
        summary="move a 20-40 module Python application from a retired helper module to a new package: aliases, callbacks, wrappers, changed return types")
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
            cases.append(K.Case(name=f"module-{m}", group="behaviour", args=[m], visible=k in (0, len(mods) // 2, len(mods) - 1)))
        files = [f"app/{m}.py" for m in mods] + (["app/common.py"] if with_common else [])
        for f in files:
            direct = f[4:-3] in app["direct"] or f == "app/common.py"
            st = {"path": f, "forbid": "oldkit"}
            if direct:
                st["require"] = "kit|common"
            cases.append(K.Case(name="clean-" + f[4:-3], group="static", static=st))
        voice = VOICES[i % len(VOICES)]
        prompt = voice.format(num=3100 + i * 23)
        hard = p["n_modules"] >= 28 or (p["common"] and p["shapes"] is False)
        yield K.codemod_task(
            start=start, solution=app["solution"], hidden_extra={"oldkit.py": A.POISON}, cases=cases,
            program=("", ["python3", "@/run.py"]), lang="python", tool="shop",
            prompt=prompt, difficulty=5 if p["n_modules"] >= 30 else 4, slug=f"{i + 1:02d}-{p['n_modules']}mods-{p['cur'].lower()}{'-common' if with_common else ''}",
            notes={"modules": p["n_modules"], "shapes": p["shapes"], "common": with_common, "cur": p["cur"], "unit": p["unit"], "log": list(p["log"]), "title": p["title"]},
            tags=["codemod", "api-migration"], protected=["kit/**", "run.py", "oldkit.py", "app/__init__.py"],
        )
