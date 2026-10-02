"""Decorators, closures and wrapper order in python, javascript and ruby. The output is what the program really prints (computed by running it)."""
from __future__ import annotations

import fx
from fx import dd, family

from . import _check as C
from . import _fam as F
from . import _ir as I
from . import _voice as V


def _j(*parts) -> str:
    return " ".join(x for x in parts if x)


def _run(files: dict, cmd: str) -> list:
    res = fx.run(files, cmd + " 2>&1", timeout=30)
    if not res.ok:
        raise RuntimeError(res.out[-300:])
    return [ln for ln in res.out.split("\n") if ln != ""]


# ---------------------------------------------------------------------------------------------------------------- python
def py_stack(rng, tier):
    dom = rng.choice(I.DOMAINS)
    noun = rng.choice(dom.nouns)
    labels = rng.sample(["audit", "metered", "traced", "guarded", "timed"], 3)
    k = rng.randint(2, 3) if tier >= 3 else 2
    consts = [rng.randint(2, 9) for _ in range(3)]
    kinds = rng.sample(["log", "scale", "plus", "cap"], k) if tier >= 2 else ["log", "scale"]
    deco_defs = []
    names = []
    for i, kd in enumerate(kinds):
        nm = f"{labels[i]}"
        names.append(nm)
        if kd == "log":
            deco_defs.append(f"def {nm}(fn):\n    def wrapper(x):\n        LOG.append(\"{nm}>\")\n        result = fn(x)\n        LOG.append(\"<{nm}\")\n        return result\n\n    return wrapper\n")
        elif kd == "scale":
            deco_defs.append(f"def {nm}(fn):\n    def wrapper(x):\n        LOG.append(\"{nm}:x{consts[i]}\")\n        return fn(x * {consts[i]})\n\n    return wrapper\n")
        elif kd == "plus":
            deco_defs.append(f"def {nm}(fn):\n    def wrapper(x):\n        result = fn(x)\n        LOG.append(\"{nm}:+{consts[i]}\")\n        return result + {consts[i]}\n\n    return wrapper\n")
        else:
            deco_defs.append(f"def {nm}(fn):\n    def wrapper(x):\n        result = fn(x)\n        LOG.append(\"{nm}:cap{consts[i] * 10}\")\n        return min(result, {consts[i] * 10})\n\n    return wrapper\n")
    files = {"wrappers.py": '"""Wrappers for the ' + dom.title + ' price functions."""\n\nLOG = []\n\n\n' + "\n\n".join(deco_defs),
             "README.md": f"# {dom.title} pricing\n\nPrice functions wrapped with small decorators; `main.py` calls one of them.\n"}
    order = names[:]
    rng.shuffle(order)
    deco_lines = "\n".join(f"@{n}" for n in order)
    files["pricing.py"] = f'"""Price of one {noun}."""\nfrom wrappers import {", ".join(sorted(names))}\n\n\n{deco_lines}\ndef price(units):\n    return units * {rng.randint(3, 12)} + 1\n'
    arg = rng.randint(2, 12)
    files["main.py"] = f"from pricing import price\nfrom wrappers import LOG\n\nprint(price({arg}))\nprint(LOG)\n" + (f"print(price({arg + 1}))\nprint(len(LOG))\n" if tier >= 4 else "")
    return files, "python3 main.py", 3 + (tier >= 4)


def py_closure(rng, tier):
    dom = rng.choice(I.DOMAINS)
    noun = rng.choice(dom.nouns)
    a, b = rng.sample(range(1, 20), 2)
    step = rng.randint(2, 7)
    files = {"counters.py": dd(f'''
        """Counters for {noun} tallies."""


        def make(start, step={step}):
            total = start

            def bump(extra=0):
                nonlocal total
                total += step + extra
                return total

            def peek():
                return total

            return bump, peek


        def shared(items):
            return [lambda: item for item in items]


        def pinned(items):
            return [lambda item=item: item for item in items]
    '''), "README.md": f"# {noun} counters\n\nSmall closure helpers.\n"}
    main = ["from counters import make, shared, pinned", "", f"bump1, peek1 = make({a})", f"bump2, peek2 = make({b}, 1)",
            f"print(bump1(), bump1(1), peek1())", f"print(bump2(), peek2(), peek1())"]
    if tier >= 2:
        main += ["print([f() for f in shared([1, 2, 3])])", "print([f() for f in pinned([1, 2, 3])])"]
    if tier >= 3:
        main += ["fs = shared(['a', 'b'])", "print(fs[0](), fs[1]())", f"print(bump1(2), peek2())"]
    files["main.py"] = "\n".join(main) + "\n"
    return files, "python3 main.py", 2 + (tier >= 3)


def py_wraps(rng, tier):
    dom = rng.choice(I.DOMAINS)
    files = {"deco.py": dd(f'''
        import functools

        CALLS = []


        def plain(fn):
            def wrapper(*args):
                CALLS.append(fn.__name__)
                return fn(*args)
            return wrapper


        def kept(fn):
            @functools.wraps(fn)
            def wrapper(*args):
                CALLS.append(fn.__name__)
                return fn(*args)
            return wrapper
    '''), "service.py": dd(f'''
        """{dom.title} service."""
        from deco import plain, kept


        @plain
        def quote(units):
            """Quote for ``units``."""
            return units * {rng.randint(2, 9)}


        @kept
        def refund(units):
            """Refund for ``units``."""
            return -units


        @kept
        @plain
        def settle(units):
            """Settle ``units``."""
            return units + {rng.randint(2, 9)}
    '''), "README.md": f"# {dom.title} service\n\nSmall service functions with decorators.\n"}
    a = rng.randint(2, 9)
    main = ["import service", "from deco import CALLS", "", f"print(service.quote({a}), service.refund({a}), service.settle({a}))", "print(service.quote.__name__, service.refund.__name__, service.settle.__name__)",
            "print(service.quote.__doc__, '|', service.refund.__doc__, '|', service.settle.__doc__)", "print(CALLS)"]
    files["main.py"] = "\n".join(main) + "\n"
    return files, "python3 main.py", 3 + (tier >= 4)


# ---------------------------------------------------------------------------------------------------------------- javascript
def js_loop(rng, tier):
    dom = rng.choice(I.DOMAINS)
    n = rng.randint(3, 4)
    files = {"tasks.js": dd(f'''
        'use strict';

        /** Builds one task per slot. */
        function withVar(n) {{
          var tasks = [];
          for (var i = 0; i < n; i++) {{
            tasks.push(() => i * {rng.randint(2, 5)});
          }}
          return tasks;
        }}

        function withLet(n) {{
          const tasks = [];
          for (let i = 0; i < n; i++) {{
            tasks.push(() => i * {rng.randint(2, 5)});
          }}
          return tasks;
        }}

        function withIife(n) {{
          const tasks = [];
          for (var i = 0; i < n; i++) {{
            tasks.push(((slot) => () => slot + 100)(i));
          }}
          return tasks;
        }}

        module.exports = {{ withVar, withLet, withIife }};
    '''), "README.md": f"# {dom.title} tasks\n\nTask builders.\n"}
    main = ["'use strict';", "", "const { withVar, withLet, withIife } = require('./tasks');", "", f"console.log(withVar({n}).map((f) => f()).join(','));", f"console.log(withLet({n}).map((f) => f()).join(','));",
            f"console.log(withIife({n}).map((f) => f()).join(','));"]
    files["main.js"] = "\n".join(main) + "\n"
    return files, "node main.js", 2 + (tier >= 3)


def js_this(rng, tier):
    dom = rng.choice(I.DOMAINS)
    noun = rng.choice(dom.nouns)
    a, b = rng.sample(range(2, 30), 2)
    files = {"meter.js": dd(f'''
        'use strict';

        class Meter {{
          constructor(label, start) {{
            this.label = label;
            this.value = start;
          }}

          bump() {{
            this.value += 1;
            return `${{this.label}}:${{this.value}}`;
          }}

          bumper() {{
            return () => this.bump();
          }}

          lazy() {{
            return function () {{
              return this === undefined ? 'detached' : this.bump();
            }};
          }}
        }}

        module.exports = {{ Meter }};
    '''), "README.md": f"# {noun} meter\n\nA counter class.\n"}
    main = ["'use strict';", "", "const { Meter } = require('./meter');", "", f"const m = new Meter('{noun}', {a});", "const free = m.bump;", "const arrow = m.bumper();", "const bound = m.bump.bind(m);",
            "console.log(m.bump(), arrow(), bound());", "console.log(m.lazy()());", "console.log(m.value);"]
    if tier >= 3:
        main += [f"const other = new Meter('x', {b});", "console.log(m.bump.call(other), other.value, m.value);", "try {", "  free();", "} catch (e) {", "  console.log(e.constructor.name);", "}"]
    files["main.js"] = "\n".join(main) + "\n"
    return files, "node main.js", 3 + (tier >= 3)


def js_hof(rng, tier):
    dom = rng.choice(I.DOMAINS)
    names = rng.sample(["audited", "metered", "traced", "capped", "doubled"], 3)
    c = rng.sample(range(2, 9), 3)
    files = {"wrap.js": dd(f'''
        'use strict';

        const LOG = [];

        const {names[0]} = (fn) => (x) => {{
          LOG.push('{names[0]}>');
          const out = fn(x);
          LOG.push('<{names[0]}');
          return out;
        }};

        const {names[1]} = (fn) => (x) => {{
          LOG.push('{names[1]}:x{c[0]}');
          return fn(x * {c[0]});
        }};

        const {names[2]} = (fn) => (x) => {{
          const out = fn(x);
          LOG.push('{names[2]}:+{c[1]}');
          return out + {c[1]};
        }};

        const compose = (...fns) => (fn) => fns.reduceRight((acc, wrap) => wrap(acc), fn);

        module.exports = {{ LOG, {', '.join(names)}, compose }};
    '''), "README.md": f"# {dom.title} wrappers\n\nHigher-order helpers.\n"}
    order = names[:]
    rng.shuffle(order)
    main = ["'use strict';", "", f"const {{ LOG, {', '.join(names)}, compose }} = require('./wrap');", "", f"const price = compose({', '.join(order)})((units) => units * {rng.randint(2, 9)});", f"console.log(price({rng.randint(2, 12)}));", "console.log(LOG.join(' '));"]
    files["main.js"] = "\n".join(main) + "\n"
    return files, "node main.js", 3 + (tier >= 4)


# ---------------------------------------------------------------------------------------------------------------- ruby
def rb_prepend(rng, tier):
    dom = rng.choice(I.DOMAINS)
    noun = rng.choice(dom.nouns).capitalize()
    mods = rng.sample(["Audited", "Metered", "Capped", "Traced"], 3)
    c = rng.sample(range(2, 9), 3)
    body = ["# frozen_string_literal: true", "", f"module {dom.name.capitalize()}", "  LOG = []", ""]
    for i, m in enumerate(mods):
        body += [f"  module {m}", "    def price(units)", f"      LOG << '{m}>'", f"      out = super(units + {c[i]})" if i == 0 else "      out = super", f"      LOG << '<{m}'", "      out", "    end", "  end", ""]
    body += [f"  class {noun}", "    def price(units)", "      LOG << 'base'", f"      units * {rng.randint(2, 9)}", "    end", "  end", "end"]
    files = {"lib/pricing.rb": "\n".join(body) + "\n", "README.md": f"# {dom.title} pricing\n\nPrice calculation with wrapper modules.\n"}
    order = mods[:]
    rng.shuffle(order)
    kinds = [rng.choice(["prepend", "include", "prepend"]) for _ in order]
    deco = "\n".join(f"{dom.name.capitalize()}::{noun}.{k} {dom.name.capitalize()}::{m}" for k, m in zip(kinds, order))
    main = f"# frozen_string_literal: true\n\nrequire_relative 'lib/pricing'\n\n{deco}\nputs {dom.name.capitalize()}::{noun}.new.price({rng.randint(2, 9)})\nputs {dom.name.capitalize()}::LOG.join(' ')\n"
    files["main.rb"] = main
    return files, "ruby main.rb", 4


def rb_proc(rng, tier):
    dom = rng.choice(I.DOMAINS)
    noun = rng.choice(dom.nouns)
    a, b, c = rng.sample(range(2, 30), 3)
    files = {"lib/runner.rb": dd(f'''
        # frozen_string_literal: true

        # Small helpers around procs and lambdas for {noun} jobs.
        module Runner
          def self.with_proc(values)
            values.each do |v|
              pr = proc {{ |x| return x * 2 if x > {a} }}
              pr.call(v)
            end
            :finished
          end

          def self.with_lambda(values)
            values.each do |v|
              la = lambda {{ |x| return x * 2 if x > {a} }}
              la.call(v)
            end
            :finished
          end

          def self.counter
            n = {b}
            [-> {{ n += 1 }}, -> {{ n }}]
          end
        end
    '''), "README.md": f"# {noun} runner\n\nProc and lambda helpers.\n"}
    main = ["# frozen_string_literal: true", "", "require_relative 'lib/runner'", "", f"p Runner.with_proc([1, {a + 5}, 2])", f"p Runner.with_lambda([1, {a + 5}, 2])", "inc, get = Runner.counter", "inc.call", "inc.call", "p get.call"]
    if tier >= 3:
        main += ["inc2, get2 = Runner.counter", "inc2.call", f"p [get.call, get2.call]"]
    files["main.rb"] = "\n".join(main) + "\n"
    return files, "ruby main.rb", 3 + (tier >= 3)


TEMPLATES = {
    "python": {"stack": py_stack, "closure": py_closure, "wraps": py_wraps},
    "javascript": {"loop": js_loop, "this": js_this, "hof": js_hof},
    "ruby": {"prepend": rb_prepend, "proc": rb_proc},
}
TIER_KINDS = {"python": {1: ["closure"], 2: ["closure", "stack"], 3: ["stack", "closure", "wraps"], 4: ["stack", "wraps", "closure"], 5: ["stack", "wraps"]},
              "javascript": {1: ["loop"], 2: ["loop"], 3: ["loop", "this", "hof"], 4: ["this", "hof"], 5: ["this", "hof"]},
              "ruby": {1: ["proc"], 2: ["proc"], 3: ["proc", "prepend"], 4: ["prepend", "proc"], 5: ["prepend"]}}


@family("explain-closures-decorators", category="explain", lang="mixed", kind="greenfield", n=10,
        summary="decorator order, closures and late binding, this binding, prepend/include wrapper order, procs vs lambdas: what the program prints (python, javascript, ruby)")
def closures(rng, n):
    langs = F.lang_plan(rng, n, ["python", "python", "javascript", "ruby"])
    tiers = F.tier_plan(rng, n, (8, 24, 32, 24, 12))
    for i in range(n):
        lang, tier = langs[i], tiers[i]
        kind = rng.choice(TIER_KINDS[lang][tier])
        files, cmd, d0 = TEMPLATES[lang][kind](rng, tier)
        lines = _run(files, cmd)
        spec = C.json_spec({"lines": C.jf("list", lines, norm="exact")})
        ask = rng.choice([
            f"What does `{cmd}` print here? Give every output line in order.",
            f"Predict the exact output of `{cmd}` for this repo, line by line.",
            f"I run `{cmd}`. What are the lines it prints, in order?",
        ])
        fmt = "Write `answer.json` as {\"lines\": [\"first line\", ...]}, one string per output line exactly as printed."
        prompt = V.frame(rng, _j(F.intro(rng, lang), ask), fmt, rng.choice(["", "", "The wrappers don't seem to run in the order the decorators are written.", "A teammate and I disagree about the output.", "Closures confuse me; I want to check my reading."]), tag="CLO")
        yield C.file_task(slug=f"{i + 1:02d}-{lang}-{kind}", prompt=prompt, difficulty=F.clamp(tier), start=files, spec=spec, answer={"lines": lines}, lang=lang,
                          tags=["closures", "decorators", kind, "answer-json"], notes={"tier": tier, "kind": kind})
