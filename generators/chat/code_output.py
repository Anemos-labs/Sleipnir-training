"""'What does this print?' questions about short realistic snippets (Python 3.11 and Node 22), plus shell pipelines.
The expected output is produced by actually running the snippet while the family is built."""
from __future__ import annotations

import fx
from fx import family

from . import _common as C

THINGS = ["tea", "jam", "rye", "oats", "figs", "salt", "kale", "mint", "cider", "plums", "honey", "bread"]
CITIES = ["lyon", "oslo", "turin", "porto", "graz", "ghent", "bern", "riga", "split", "cork"]


# --------------------------------------------------------------------------------------------------------------------
# python snippet templates: each returns (code, story)

def p_late_binding(rng):
    rates = rng.sample([5, 10, 15, 20, 25, 30], 3)
    price = rng.choice([200, 400, 800, 1000])
    code = f'''rates = {rates}
rules = []
for r in rates:
    rules.append(lambda price: price * (100 - r) // 100)

print([rule({price}) for rule in rules])
'''
    return code, "a loyalty-discount table built in a loop"


def p_mutable_default(rng):
    a, b, c = rng.sample(THINGS, 3)
    code = f'''def add_item(item, cart=[]):
    cart.append(item)
    return cart

first = add_item("{a}")
second = add_item("{b}")
third = add_item("{c}", [])
print(first, second, third, len(first))
'''
    return code, "a shopping-cart helper"


def p_alias_grid(rng):
    r, c = rng.randint(3, 4), rng.randint(3, 4)
    i, j, v = rng.randrange(r), rng.randrange(c), rng.randint(2, 9)
    code = f'''board = [[0] * {c}] * {r}
board[{i}][{j}] = {v}
total = sum(sum(row) for row in board)
print(total, board[0] is board[{r - 1}])
'''
    return code, "a seating-plan grid"


def p_banker(rng):
    vals = rng.sample([0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 2.4, 3.6, 7.5, 8.5], 6)
    code = f'''readings = {vals}
rounded = [round(x) for x in readings]
print(rounded, sum(rounded), round(sum(readings)))
'''
    return code, "rounding sensor readings"


def p_slices(rng):
    words = rng.sample(["harbour", "lantern", "meadow", "copper", "orchard", "granite", "willow", "thistle", "ember", "juniper"], 5)
    st, sp = rng.choice([(0, 2), (1, 2), (0, 3)])
    code = f'''words = {words}
picked = words[{st}::{sp}]
print("-".join(w[::-1][:3] for w in picked), len(picked))
'''
    return code, "building a label from a word list"


def p_dict_order(rng):
    k = rng.sample(["alpha", "beta", "gamma", "delta", "eps"], 4)
    code = f'''base = {{"{k[0]}": 1, "{k[1]}": 2, "{k[2]}": 3}}
extra = {{"{k[1]}": 20, "{k[3]}": 40}}
merged = {{**base, **extra}}
del merged["{k[0]}"]
merged["{k[0]}"] = 100
print(list(merged.items()), sum(merged.values()))
'''
    return code, "merging two settings dictionaries"


def p_generator(rng):
    n = rng.randint(4, 7)
    m = rng.choice([2, 3, 5])
    code = f'''readings = (x * {m} for x in range({n}))
print(sum(readings), sum(readings), list(readings))
'''
    return code, "a one-shot generator of scaled readings"


def p_stable_sort(rng):
    names = rng.sample(["Ava", "Ben", "Cleo", "Dev", "Eli", "Fay", "Gus"], 5)
    scores = [rng.choice([70, 80, 80, 90]) for _ in names]
    rows = list(zip(names, scores))
    code = f'''rows = {rows}
rows.sort(key=lambda r: r[0])
rows.sort(key=lambda r: -r[1])
print([n for n, s in rows])
'''
    return code, "ranking students"


def p_floor_div(rng):
    a, b = rng.randint(5, 40), rng.randint(2, 9)
    code = f'''offset = -{a}
step = {b}
print(offset // step, offset % step, divmod(offset, step), int(offset / step))
'''
    return code, "a scroll-offset calculation with a negative number"


def p_try_finally(rng):
    code = f'''def attempt(values):
    total = 0
    for v in values:
        try:
            if v < 0:
                raise ValueError(v)
            total += v
        except ValueError:
            total -= 1
            continue
        finally:
            total += 10
    return total

print(attempt([{rng.randint(1, 5)}, -2, {rng.randint(1, 5)}]), attempt([]))
'''
    return code, "a retry-ish accumulator with try/finally"


def p_closure_counter(rng):
    start, step = rng.randint(1, 5), rng.randint(2, 4)
    code = f'''def make_counter(start, step):
    count = start
    def tick():
        nonlocal count
        count += step
        return count
    return tick

a = make_counter({start}, {step})
b = make_counter(100, 1)
print(a(), a(), b(), a(), b())
'''
    return code, "ticket counters"


def p_comp_scope(rng):
    n = rng.randint(3, 6)
    x = rng.randint(10, 50)
    code = f'''x = {x}
squares = [x * x for x in range({n})]
total = 0
for x in range(2):
    total += x
print(x, total, squares[-1])
'''
    return code, "variable names reused in a comprehension and a loop"


def p_format(rng):
    pi = rng.choice([3.14159, 2.71828, 1.41421, 1.61803])
    n = rng.randint(5, 99)
    code = f'''label = "x"
print(f"[{{label:>4}}]", f"[{{{pi}:8.2f}}]", f"[{{{n}:04d}}]", f"[{{{n}/7:.3e}}]")
'''
    return code, "a report line with format specs"


def p_class_var(rng):
    code = f'''class Crate:
    items = []
    capacity = {rng.randint(2, 4)}

    def __init__(self, name):
        self.name = name

    def add(self, x):
        if len(self.items) < self.capacity:
            self.items.append(x)
        return len(self.items)

a, b = Crate("a"), Crate("b")
print(a.add(1), a.add(2), b.add(3), b.add(4), len(a.items), Crate.items)
'''
    return code, "warehouse crates with a shared list"


def p_zip_enum(rng):
    n1, n2 = rng.randint(3, 6), rng.randint(2, 5)
    code = f'''left = list(range({n1}))
right = list("abcdefg"[:{n2}])
pairs = list(zip(left, right))
print(len(pairs), pairs[-1], [i * j for i, j in enumerate(left, start=2)][-1])
'''
    return code, "pairing up two uneven lists"


def p_set_ops(rng):
    a = rng.sample(range(1, 15), 6)
    b = rng.sample(range(1, 15), 6)
    code = f'''monday = {sorted(a)}
tuesday = {sorted(b)}
both = set(monday) & set(tuesday)
either = set(monday) ^ set(tuesday)
print(sorted(both), len(either), max(set(monday) | set(tuesday)))
'''
    return code, "which customers came on which days"


def p_str_methods(rng):
    s = rng.choice(["  Spring,Summer ,autumn,  Winter", "  red;green ; blue ,yellow", "  mon, tue ,wed,thu  "])
    code = f'''raw = "{s}"
parts = [p.strip().title() for p in raw.replace(";", ",").split(",")]
print(parts, len(raw), raw.strip().count(" "))
'''
    return code, "cleaning up a hand-typed list"


PY_TEMPLATES = {
    1: [p_floor_div, p_slices, p_zip_enum, p_set_ops, p_str_methods],
    2: [p_banker, p_generator, p_format, p_comp_scope, p_dict_order],
    3: [p_late_binding, p_mutable_default, p_alias_grid, p_stable_sort, p_closure_counter],
    4: [p_class_var, p_try_finally, p_late_binding, p_mutable_default, p_alias_grid],
}


# --------------------------------------------------------------------------------------------------------------------
# javascript snippet templates

def j_sort_default(rng):
    xs = rng.sample([2, 5, 9, 10, 25, 100, 111, 8, 19, 30], 6)
    code = f'''const ids = {xs};
const sorted = [...ids].sort();
console.log(JSON.stringify(sorted), ids[0]);
'''
    return code, "sorting order numbers"


def j_key_order(rng):
    ks = rng.sample(["b", "a", "k", "z"], 3) + [str(rng.randint(10, 40)), str(rng.randint(1, 9))]
    code = f'''const lookup = {{}};
for (const k of {ks!r}.map(String)) lookup[k] = k.length;
console.log(Object.keys(lookup).join(","));
'''
    return code, "a lookup table keyed by code"


def j_nullish(rng):
    v = rng.choice([0, "", 7])
    code = f'''const cfg = {{ retries: {v!r}, label: null }};
const a = cfg.retries || 5;
const b = cfg.retries ?? 5;
const c = cfg.label ?? "n/a";
const d = cfg.missing?.deep ?? "none";
console.log(a, b, c, d);
'''
    return code, "default handling in a config object"


def j_float(rng):
    a, b = rng.choice([(0.1, 0.2), (0.7, 0.1), (1.1, 2.2)])
    code = f'''const total = {a} + {b};
console.log(total === {round(a + b, 2)}, total.toFixed(2), Math.round(total * 100) / 100);
'''
    return code, "adding two prices"


def j_spread_copy(rng):
    code = f'''const base = {{ name: "kit", tags: ["a", "b"], size: {{ w: {rng.randint(2, 9)}, h: {rng.randint(2, 9)} }} }};
const copy = {{ ...base }};
copy.name = "kit2";
copy.tags.push("c");
copy.size.w = 99;
console.log(base.name, base.tags.length, base.size.w);
'''
    return code, "cloning a settings object"


def j_array_len(rng):
    n = rng.randint(3, 6)
    code = f'''const a = Array.from({{ length: {n} }}, (_, i) => i * 2);
a.length = 2;
a[{n + 1}] = 7;
console.log(a.length, a.indexOf(7), a.filter(x => x === undefined).length, a.join("|"));
'''
    return code, "trimming an array and writing past the end"


def j_reduce(rng):
    xs = [rng.randint(1, 9) for _ in range(rng.randint(4, 6))]
    code = f'''const parts = {xs};
const a = parts.reduce((acc, x) => acc + x);
const b = parts.reduce((acc, x) => acc + x * 2, 10);
const c = [].reduce((acc, x) => acc + x, "empty");
console.log(a, b, c);
'''
    return code, "totalling basket quantities"


def j_closure_var(rng):
    n = rng.randint(3, 4)
    code = f'''const fns = [];
for (var i = 0; i < {n}; i++) {{
  fns.push(() => i * 10);
}}
const gs = [];
for (let j = 0; j < {n}; j++) {{
  gs.push(() => j * 10);
}}
console.log(fns.map(f => f()).join(","), gs.map(f => f()).join(","));
'''
    return code, "queued callbacks from a loop"


def j_set_dedupe(rng):
    xs = [rng.choice(["a", "b", "c", "d"]) for _ in range(8)]
    code = f'''const tags = {xs!r};
const uniq = [...new Set(tags)];
const counts = new Map();
for (const t of tags) counts.set(t, (counts.get(t) || 0) + 1);
console.log(uniq.join(""), [...counts.entries()].sort((x, y) => y[1] - x[1] || x[0].localeCompare(y[0]))[0].join(":"));
'''
    return code, "counting tags"


JS_TEMPLATES = {1: [j_sort_default, j_key_order], 2: [j_nullish, j_float, j_reduce], 3: [j_spread_copy, j_array_len, j_closure_var], 4: [j_set_dedupe, j_closure_var, j_array_len]}


def run_py(code):
    r = fx.run({"main.py": code}, "python3 main.py", timeout=20)
    return r


def run_js(code):
    r = fx.run({"main.js": code}, "node main.js", timeout=20)
    return r


@family("chat-code-output", category="chat", lang="mixed", kind="lookup", n=12, mode="answer",
        summary="what does this short Python or JavaScript snippet print? (output produced by really running it; several traps per snippet at higher levels)")
def gen_code(rng, n):
    plan = [1, 1, 2, 2, 3, 3, 3, 4, 4, 5, 2, 3]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            lang = "python" if rng.random() < 0.65 else "javascript"
            if d == 5:
                lang = rng.choice(["python", "python", "javascript"])
            tmpls = (PY_TEMPLATES if lang == "python" else JS_TEMPLATES)
            if d <= 4:
                fn = rng.choice(tmpls[d])
                code, story = fn(rng)
                parts = 1
            else:
                pool = tmpls[3] + tmpls[4]
                k = rng.randint(3, 4)
                fns = rng.sample(pool, k) if len(set(f.__name__ for f in pool)) >= k else pool[:k]
                fns = list({f.__name__: f for f in fns}.values())
                if len(fns) < 3:
                    continue
                blocks = []
                for f in fns:
                    cd, _ = f(rng)
                    blocks.append(cd)
                if lang == "python":
                    # namespace each block in its own function to avoid name clashes
                    body = []
                    for bi, cd in enumerate(blocks):
                        ind = "\n".join(("    " + ln if ln.strip() else ln) for ln in cd.rstrip("\n").split("\n"))
                        body.append(f"def check_{bi + 1}():\n{ind}\n")
                    code = "\n".join(body) + "\n" + "\n".join(f"check_{bi + 1}()" for bi in range(len(blocks))) + "\n"
                else:
                    body = []
                    for bi, cd in enumerate(blocks):
                        ind = "\n".join(("  " + ln if ln.strip() else ln) for ln in cd.rstrip("\n").split("\n"))
                        body.append(f"function check{bi + 1}() {{\n{ind}\n}}\n")
                    code = "\n".join(body) + "\n" + "\n".join(f"check{bi + 1}();" for bi in range(len(blocks))) + "\n"
                story = "a little diagnostics script a colleague wrote"
                parts = len(blocks)
            res = run_py(code) if lang == "python" else run_js(code)
            if not res.ok:
                continue
            out = res.out.strip("\n")
            lines = [ln for ln in out.split("\n")]
            if not lines or any(len(ln) > 150 for ln in lines) or any(ln.strip() == "" for ln in lines):
                continue
            version = "Python 3.11" if lang == "python" else "Node 22"
            intro = rng.choice([f"My colleague swears this snippet prints something different from what I get in my head. It is {story} and runs on {version}.",
                                f"I'm reviewing {story} ({version}) and I'd like to know the exact output without running it on the shared box.",
                                f"quick one about {story}, runs on {version}",
                                f"Interview-prep style question from my study group, but it's the kind of thing that really bites in real code: {story}, {version}."])
            ask = rng.choice(["What exactly does it print? Copy the output lines.", "What is the exact output?", "Give me the exact text it prints, line by line."])
            reg = C.register_for(rng)
            fence = "python" if lang == "python" else "javascript"
            data = f"```{fence}\n{code.rstrip()}\n```"
            prompt = C.chat(rng, intro, ask, data, reg)
            contains = []
            for ln in lines:
                if ln.strip() and ln.strip() not in contains:
                    contains.append(ln.strip())
            keep = C.unseen(prompt, contains, False, min_keep=len(contains))
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{lang[:2]}-{story.split()[1] if len(story.split()) > 1 else 'x'}-d{d}", prompt, d, keep, "\n".join(lines), tags=["code-reading", lang], lang=lang,
                                notes={"lang": lang, "parts": parts})
            break
        else:
            raise RuntimeError("code-output: no instance")
