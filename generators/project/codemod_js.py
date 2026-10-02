"""project-codemod-js: retire a legacy helper module (`oldkit`) from a 20-40 module JavaScript (CommonJS) application by moving
every call site to the replacement package (`kit`), with output unchanged.  Scored per module."""
from __future__ import annotations

from fx import family

from generators.project import _cm_js as A
from generators.project import _kit as K

PLAN = [
    dict(n_modules=20, shapes=False, common=False, common_share=0.0, cur="USD", unit="ea", log=("<", ">"), title="first", min_snip=3, max_snip=4),
    dict(n_modules=24, shapes=True, common=True, common_share=0.5, cur="EUR", unit="pc", log=("[", "]"), title="each", min_snip=3, max_snip=5),
    dict(n_modules=26, shapes=True, common=False, common_share=0.0, cur="GBP", unit="unit", log=("(", ")"), title="each", min_snip=4, max_snip=5),
    dict(n_modules=28, shapes=True, common=True, common_share=0.3, cur="CHF", unit="ea", log=("{", "}"), title="first", min_snip=4, max_snip=5),
    dict(n_modules=32, shapes=True, common=False, common_share=0.0, cur="EUR", unit="pc", log=("<", ">"), title="each", min_snip=4, max_snip=5),
    dict(n_modules=22, shapes=True, common=True, common_share=0.6, cur="USD", unit="unit", log=("[", "]"), title="first", min_snip=3, max_snip=5),
    dict(n_modules=36, shapes=True, common=True, common_share=0.25, cur="GBP", unit="ea", log=("(", ")"), title="first", min_snip=4, max_snip=5),
    dict(n_modules=30, shapes=True, common=False, common_share=0.0, cur="CHF", unit="pc", log=("{", "}"), title="each", min_snip=4, max_snip=5),
]

VOICES = [
    "The `oldkit` helper module is being deleted next sprint, and the whole of `app/` still depends on it, through plain requires, destructuring, renamed imports and callbacks. Please move every module to the `kit` package described in `README.md` and keep the output of `node run.js MODULE` byte-identical. `python3 tests/run_examples.py` runs a few demos; the real check disables `oldkit` and runs all of them.",
    "port app/ from oldkit to kit (README.md has the table and the gotchas). node run.js <module> must print exactly what it printed before. leave kit/, run.js and tests/ alone. scripting the edit is fine if you verify the result",
    "Ticket MIG-{num}: remove the dependency on `oldkit`.\n\nAcceptance: with `oldkit` replaced by a module whose functions all throw, `node run.js <module>` prints the same lines as before for each module in `app/`, and no file under `app/` mentions `oldkit` any more. `kit/` is finished; the mapping from old to new is in README.md.",
    "We are moving our helper layer from `oldkit` to `kit` and I would like the whole `app/` directory ported. README.md lists every old function with its replacement and the places where behaviour differs (return shapes, optional arguments, argument order). Please compare `node run.js all` before and after your change.",
    "Migrate the application to `kit`. The README is the guide. Each module prints a demo through `run.js`; some modules import the old helpers directly, some through destructuring with renames, some via a shared wrapper file. Hidden checks run each module separately with `oldkit` disabled and also look for leftovers, so you get partial credit for a partial migration.",
    "Deprecation sweep: oldkit -> kit in app/. See README.md. Output must stay identical. Watch the new argument conventions: `pad` takes an options object, `group` returns pairs, and parsing a quantity no longer returns an array.",
    "could you do the oldkit -> kit migration from README.md? lots of small edits across dozens of modules; a script is fine, but diff the output of `node run.js all` before/after. nothing else may change",
    "`oldkit` is retired. Every module under `app/` has to use `kit` instead, with identical output. See README.md for the mapping. Hidden checks run each module's demo with `oldkit` disabled and scan the sources for the old name, so leftover requires count against you.",
]


def readme(p: dict, mods: list[str], with_common: bool) -> str:
    cur, unit = p["cur"], p["unit"]
    o = []
    w = o.append
    w("# Retiring `oldkit`\n")
    w(f"The application in `app/` is a collection of {len(mods)} small demo modules (`{mods[0]}`, `{mods[1]}`, ...; the full list is exported by `app/index.js`). "
      "Each module formats prices, parses quantities, reads rate tables, groups records, logs events and so on, and exports a `demo()` function that returns the lines the module prints. "
      "`node run.js MODULE` prints the demo of one module (`node run.js all` prints all of them). `run.js` exits with status 1 and prints `error: ...` if a demo throws.\n")
    w("All of this was written against `oldkit.js`, a helper module that is now deprecated. Its replacement, the package `kit/`, is complete and tested: **do not edit anything under `kit/`, `run.js` or `tests/`**. "
      "`oldkit.js` itself stays in the repository for now (files cannot be deleted in this job) but nothing may use it any more.\n")
    w("## What has to be true afterwards\n")
    w("1. For every module, `node run.js MODULE` prints **exactly** what it printed before the migration (byte for byte), exit status 0.")
    w("2. The migrated code works when `oldkit.js` is replaced by a module in which every function throws an `Error` (that is how the checks run it: any call that still goes to `oldkit` fails the module).")
    w("3. The text `oldkit` does not appear in any file under `app/` (requires, comments and strings included), and the files that used it now use `kit` (or `app/common.js`).")
    w("\nThe score is the average of two shares: the share of modules whose demo still prints the right output with `oldkit` disabled, and the share of files under `app/` that no longer mention `oldkit`.\n")
    w("## The mapping\n")
    w("| `oldkit` | `kit` | what is different |")
    w("|---|---|---|")
    w(f"| `fmtAmount(cents, cur = '{cur}')` | `new kit.money.Money(cents, cur).text()` | `Money` requires `cur`: the old default was `'{cur}'`. |")
    w("| `parseQty(text)` returns `[count, unit]` or `null` | `kit.qty.Qty.tryParse(text)` returns a `Qty` (properties `.count`, `.unit`) or `null`; `kit.qty.Qty.parse(text)` throws `kit.qty.QtyError` instead of returning `null` | a `Qty` is **not** an array: no destructuring, no indexing. |")
    w("| `padRight(s, width)` | `kit.text.pad(s, width, { align: 'left' })` | the old name says where the *padding* goes, the new `align` says where the *text* goes. |")
    w("| `padLeft(s, width)` | `kit.text.pad(s, width, { align: 'right' })` | same remark; the options object is the third argument. |")
    w("| `title(s)` | `kit.text.titleCase(s)` | |")
    w("| `cmpNames(a, b)` | `kit.text.compare(a, b)` | comparator for `Array.prototype.sort`. |")
    w("| `pick(obj, ...keys)` returns `undefined` for a missing key | `kit.data.dig(obj, keys, def)` | the keys are passed as **one array**; the default is the third argument (`undefined` stays `undefined` if omitted). |")
    w("| `take(seq, n)` | `kit.data.first(seq, n)` | |")
    w("| `groupBy(items, keyfn)` returns a plain object | `kit.data.group(items, keyfn)` returns an **array of `[key, items]` pairs**, keys in order of first appearance | `Object.fromEntries(kit.data.group(...))` is the old result. |")
    w("| `log(level, msg, ctx)` appends to a global buffer and returns the line | `kit.events.default().emit(level, msg, ctx)` appends to the shared `Events` object and returns **nothing**; `.last()` is the most recent line | |")
    w("| `flushLog()` | `kit.events.default().drain()` | returns the lines and clears them, like the old function. |")
    w("| `clamp(x, lo, hi)` | `kit.data.limit(x, lo, hi)` | |")
    w("\n`kit` is loaded with `require('../kit')` from the modules in `app/`. "
      "Functions are also passed around as values (`names.map(oldkit.title)`, `[...names].sort(oldkit.cmpNames)`, `reduce`), and modules import the old names in several styles "
      "(`const oldkit = require(...)`, `const ok = require(...)`, `const { fmtAmount } = require(...)`, `const { fmtAmount: money } = require(...)`)." +
      (" Part of the application goes through `app/common.js`, a layer of thin wrappers around `oldkit`; the modules that require it need no change if you rewrite `common` (keeping its function names and signatures) on top of `kit`, or you may migrate those modules directly." if with_common else ""))
    w("\nRead `oldkit.js` for the exact behaviour of each old function (defaults, formats): the new code must reproduce it.\n")
    w("## How to check your work\n")
    w("* `node run.js all > before.txt` *before* you start, and again at the end: the two outputs must be identical.")
    w("* `python3 tests/run_examples.py` compares a few modules with the expected output (the real checks cover every module and run with `oldkit` disabled).")
    return "\n".join(o) + "\n"


@family("project-codemod-js", category="project", lang="javascript", kind="refactor", n=8,
        summary="move a 20-40 module JavaScript application from a retired helper module to a new package: renamed imports, callbacks, wrappers, changed return types")
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
        files = [f"app/{m}.js" for m in mods] + (["app/common.js"] if with_common else [])
        for f in files:
            direct = f[4:-3] in app["direct"] or f == "app/common.js"
            st = {"path": f, "forbid": "oldkit"}
            if direct:
                st["require"] = "kit|common"
            cases.append(K.Case(name="clean-" + f[4:-3], group="static", static=st))
        prompt = VOICES[i % len(VOICES)].format(num=3300 + i * 19)
        yield K.codemod_task(
            start=start, solution=app["solution"], hidden_extra={"oldkit.js": A.POISON}, cases=cases,
            program=("", ["node", "@/run.js"]), lang="javascript", tool="shop",
            prompt=prompt, difficulty=5 if p["n_modules"] >= 30 else 4, slug=f"{i + 1:02d}-{p['n_modules']}mods-{p['cur'].lower()}{'-common' if with_common else ''}",
            notes={"modules": p["n_modules"], "shapes": p["shapes"], "common": with_common, "cur": p["cur"], "unit": p["unit"], "log": list(p["log"]), "title": p["title"]},
            tags=["codemod", "api-migration"], protected=["kit/**", "run.js", "oldkit.js", "app/index.js"],
        )
