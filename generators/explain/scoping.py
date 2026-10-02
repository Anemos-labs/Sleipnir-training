"""Python name-resolution and import-order puzzles inside small multi-file programs: star imports, import-time side effects, rebinding,
shared defaults, class attributes. The answer is what the program really prints (computed by running it)."""
from __future__ import annotations

import fx
from fx import dd, family

from . import _check as C
from . import _fam as F
from . import _ir as I
from . import _voice as V


def _j(*parts) -> str:
    return " ".join(x for x in parts if x)


def _run(files: dict, cmd: str = "python3 main.py") -> list:
    res = fx.run(files, cmd + " 2>&1", timeout=30)
    if not res.ok:
        raise RuntimeError(res.out[-300:])
    return [ln for ln in res.out.split("\n") if ln != ""]


# ---------------------------------------------------------------------------------------------------------------- templates
def t_star(rng, tier):
    dom = rng.choice(I.DOMAINS)
    names = rng.sample(["fee", "rate", "limit", "unit", "cap", "base"], 4)
    mods = ["tariffs", "legacy", "overrides", "seasonal"][: {1: 2, 2: 2, 3: 3, 4: 3, 5: 4}[tier]]
    files = {}
    allm = {}
    for k, m in enumerate(mods):
        body = [f'"""{m.capitalize()} values for {dom.title}."""', ""]
        defined = rng.sample(names, rng.randint(2, 3))
        for n in defined:
            body.append(f"{n.upper()} = {rng.randint(2, 99)}")
        if rng.random() < 0.5:
            fn = rng.choice(defined)
            body += ["", "", f"def {fn}_total(count):", f'    """Total for ``count`` units at the {fn} defined here."""', f"    return count * {fn.upper()}"]
            defined.append(fn + "_total")
        if tier >= 3 and rng.random() < 0.5:
            allm[m] = rng.sample(defined, max(1, len(defined) - 1))
            body.insert(2, "__all__ = [" + ", ".join(repr(n.upper() if not n.endswith("_total") else n) for n in allm[m]) + "]")
            body.insert(3, "")
        files[f"{m}.py"] = "\n".join(body) + "\n"
    order = mods[:]
    rng.shuffle(order)
    lines = ["from " + m + " import *" for m in order]
    if tier >= 4:
        m2 = rng.choice(mods)
        cand = [ln.split("=")[0].strip() for ln in files[f"{m2}.py"].split("\n") if ln.isupper() or (ln.split("=")[0].strip().isupper() and "=" in ln)]
        cand = [c for c in cand if c and c.isupper()]
        if cand:
            lines.append(f"from {m2} import {cand[0]}")
    shown = sorted({c for m in mods for c in [ln.split("=")[0].strip() for ln in files[f"{m}.py"].split("\n") if "=" in ln and ln.split("=")[0].strip().isupper()]})
    pr = []
    for c in shown:
        pr.append(f"print(\"{c}\", globals().get(\"{c}\"))")
    if any("_total" in f for f in files.values()):
        for m in mods:
            for ln in files[f"{m}.py"].split("\n"):
                if ln.startswith("def ") and "_total" in ln:
                    fn = ln[4:].split("(")[0]
                    pr.append(f"print(\"{fn}\", globals().get(\"{fn}\", lambda c: None)(3))")
    files["main.py"] = '"""Prints the constants and helpers visible after the imports."""\n' + "\n".join(lines) + "\n\n" + "\n".join(dict.fromkeys(pr)) + "\n"
    files["README.md"] = f"# {dom.title} rates\n\nSeveral modules define pricing constants; `main.py` pulls them in.\n"
    return files, "main.py: which value does each name end up with after the imports?", 2 + (tier >= 3)


def t_order(rng, tier):
    dom = rng.choice(I.DOMAINS)
    pkg = dom.name
    subs = rng.sample(["rates", "ledger", "audit", "cache", "report"], {1: 2, 2: 3, 3: 3, 4: 4, 5: 4}[tier])
    files = {f"{pkg}/__init__.py": f'print("init {pkg}")\n'}
    deps: dict = {}
    for i, s in enumerate(subs):
        d = [x for x in subs[:i] if rng.random() < 0.5]
        deps[s] = d
        lines = []
        for x in d:
            lines.append(f"from . import {x}")
        lines.append(f'print("load {s}")')
        lines += ["", "", f"def run_{s}():", f'    print("run {s}")']
        if d:
            lines.append(f"    {d[0]}.run_{d[0]}()")
        files[f"{pkg}/{s}.py"] = "\n".join(lines) + "\n"
    first, second = rng.sample(subs, 2)
    main = [f"print(\"start\")", f"import {pkg}.{second}", f"print(\"imported {second}\")", f"from {pkg} import {first}", f"print(\"imported {first}\")"]
    if tier >= 3:
        lazy = rng.choice(subs)
        main += [f"def late():", f"    from {pkg} import {lazy}", f"    {lazy}.run_{lazy}()", "", "", "late()", "late()"]
    else:
        main += [f"{pkg}.{second}.run_{second}()"]
    files["main.py"] = "\n".join(main) + "\n"
    files["README.md"] = f"# {dom.title}\n\nA package of small modules that announce themselves when loaded.\n"
    return files, "main.py: which lines are printed, in order?", 3 + (tier >= 4)


def t_rebind(rng, tier):
    dom = rng.choice(I.DOMAINS)
    v0, v1, v2 = rng.sample(range(2, 99), 3)
    files = {"settings.py": f'"""Settings of {dom.title}."""\nLIMIT = {v0}\nNAMES = ["a"]\n\n\ndef limit():\n    return LIMIT\n',
             "flags.py": 'from settings import LIMIT, NAMES\nimport settings\n\n\ndef copy_limit():\n    return LIMIT\n\n\ndef live_limit():\n    return settings.LIMIT\n\n\ndef via_function():\n    return settings.limit()\n'}
    main = ["import settings", "import flags", "", f"settings.LIMIT = {v1}", "print(flags.copy_limit(), flags.live_limit(), flags.via_function())"]
    if tier >= 2:
        main += ["settings.NAMES.append('b')", "print(flags.NAMES, settings.NAMES, flags.NAMES is settings.NAMES)"]
    if tier >= 3:
        main += [f"flags.LIMIT = {v2}", "print(flags.copy_limit(), flags.live_limit(), settings.LIMIT)"]
    if tier >= 4:
        main += ["settings.NAMES = ['z']", "print(flags.NAMES, settings.NAMES)", "from settings import LIMIT", "print(LIMIT, flags.LIMIT)"]
    files["main.py"] = "\n".join(main) + "\n"
    files["README.md"] = f"# {dom.title} settings\n\nModule-level settings and a helper module that reads them.\n"
    return files, "main.py: what does each print statement show?", 2 + (tier >= 3)


def t_default(rng, tier):
    dom = rng.choice(I.DOMAINS)
    noun = rng.choice(dom.nouns)
    a, b = rng.sample(range(2, 40), 2)
    files = {"queue.py": dd(f'''
        """A tiny work queue for {dom.title}."""

        PENDING = []


        def add(item, batch=[], seen=set()):
            batch.append(item)
            seen.add(item)
            PENDING.append(len(batch))
            return len(batch), len(seen)


        def fresh(item, batch=None):
            batch = [] if batch is None else batch
            batch.append(item)
            return len(batch)
    '''), "README.md": f"# {dom.title} queue\n\nHelpers that add {noun} items to a batch.\n"}
    main = ["import queue", "", f"print(queue.add({a}))", f"print(queue.add({b}))", f"print(queue.add({a}, []))", f"print(queue.add({a}))", "print(queue.fresh(1), queue.fresh(2))", "print(queue.PENDING)"]
    if tier >= 3:
        main += [f"print(queue.add.__defaults__[0], sorted(queue.add.__defaults__[1]))"]
    files["main.py"] = "\n".join(main) + "\n"
    return files, "main.py: what does each print statement show?", 3 + (tier >= 3)


def t_class(rng, tier):
    dom = rng.choice(I.DOMAINS)
    base = rng.choice(dom.nouns).capitalize()
    a, b = rng.sample(range(2, 30), 2)
    files = {"model.py": dd(f'''
        """{base} model."""


        class {base}:
            count = {a}
            tags = []

            def bump(self):
                self.count += 1
                return self.count

            def tag(self, name):
                self.tags.append(name)
                return len(self.tags)


        class Heavy{base}({base}):
            count = {b}

            def reset(self):
                self.__class__.count = 0
    '''), "README.md": f"# {base} model\n\nA base class and one subclass with class-level counters.\n"}
    main = ["from model import " + base + ", Heavy" + base, "", f"x, y = {base}(), Heavy{base}()", "print(x.bump(), x.bump(), y.bump())", f"print({base}.count, Heavy{base}.count, y.count)",
            "print(x.tag('p'), y.tag('q'))", f"print({base}.tags, Heavy{base}.tags is {base}.tags)"]
    if tier >= 3:
        main += ["y.reset()", f"print(x.count, y.count, Heavy{base}.count, {base}.count)", "print(x.bump(), y.bump())"]
    files["main.py"] = "\n".join(main) + "\n"
    return files, "main.py: what does each print statement show?", 3 + (tier >= 3)


def t_cycle(rng, tier):
    dom = rng.choice(I.DOMAINS)
    x, y = rng.sample(["rates", "ledger", "audit", "stock"], 2)
    files = {f"{x}.py": f'print("loading {x}")\nimport {y}\nprint("{x} sees {y}:", hasattr({y}, "VALUE"))\nVALUE = "{x}"\n\n\ndef show():\n    return {y}.VALUE\n',
             f"{y}.py": f'print("loading {y}")\nimport {x}\nprint("{y} sees {x}:", hasattr({x}, "VALUE"))\nVALUE = "{y}"\n\n\ndef show():\n    return {x}.VALUE\n',
             "main.py": f'print("start")\nimport {x}\nprint("done")\nprint({x}.show(), {x}.{y}.show())\n',
             "README.md": f"# {dom.title}\n\nTwo modules that look at each other.\n"}
    return files, "main.py: which lines are printed, in order?", 4


WHY = {"star": ["", "", "A colleague swears the output changes if the imports are reordered.", "Two modules define the same constant and I don't know which wins."],
       "order": ["", "", "Someone moved an import and the log lines shifted.", "I'm trying to understand what runs at import time."],
       "rebind": ["", "", "A setting changed at runtime is not seen by one of the modules."],
       "default": ["", "", "Calls with the same arguments give different answers."],
       "class": ["", "", "Two objects share a counter and I don't know why."],
       "cycle": ["", "", "Python did not complain about the circular import, but I do not trust it."]}
TEMPLATES = {"star": t_star, "order": t_order, "rebind": t_rebind, "default": t_default, "class": t_class, "cycle": t_cycle}
BY_TIER = {1: ["rebind", "order"], 2: ["rebind", "star", "order", "default"], 3: ["star", "order", "default", "class", "cycle"], 4: ["star", "order", "class", "cycle", "default"], 5: ["star", "order", "class", "cycle"]}


@family("explain-python-scoping", category="explain", lang="python", kind="greenfield", n=10,
        summary="what a small python program prints: star-import overrides, __all__, import-time side effects and order, circular imports, rebinding vs copies, shared defaults, class attributes")
def scoping(rng, n):
    tiers = F.tier_plan(rng, n, (8, 24, 32, 24, 12))
    for i in range(n):
        tier = tiers[i]
        kind = rng.choice(BY_TIER[tier])
        files, what, d0 = TEMPLATES[kind](rng, tier)
        lines = _run(files)
        spec = C.json_spec({"lines": C.jf("list", lines, norm="exact")})
        ask = rng.choice([
            f"Without changing anything: what does `python3 main.py` print here? ({what.split(': ', 1)[1]}) Give every output line in order.",
            f"Predict the complete output of `python3 main.py` for this repo, line by line.",
            f"What gets printed when I run `python3 main.py`? I'm after the exact lines, in order.",
        ])
        fmt = "Write `answer.json` as {\"lines\": [\"first line\", ...]}, one string per output line exactly as printed (booleans print as `True`/`False`)."
        prompt = V.frame(rng, ask, fmt, rng.choice(["", "", "My mental model of Python imports says something different from CI.", "A colleague swears the output changes if the imports are reordered."]), tag="PYS")
        d = F.clamp(tier)
        yield C.file_task(slug=f"{i + 1:02d}-{kind}", prompt=prompt, difficulty=d, start=files, spec=spec, answer={"lines": lines}, lang="python",
                          tags=["python", "name-resolution", kind, "answer-json"], notes={"tier": tier, "kind": kind})
