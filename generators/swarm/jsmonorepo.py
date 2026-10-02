"""A monorepo of small JavaScript libraries, each carrying its own defect (swarm: one worker per package)."""
from __future__ import annotations

import json

from fx import Task, dd, family

from . import _jsmods  # noqa: F401  (registers the JavaScript bank)
from ._jsbank import JS_MODS, describe, run_hidden, symptoms
from ._kit import GRADE_CMD, enum, oxford, pick, score_script, team

PROJECTS = [
    ("Quayline", "the quay office's scheduling libraries"), ("Tallybar", "a trade-fair booth system's helpers"), ("Wickerdesk", "the front-desk tooling of a small hostel"),
    ("Cairnworks", "the shared packages of a hill-walking club's site"), ("Fennet", "back-end helpers for a farm-shop web app"),
]


def js_tree(mod, bug, readme=None):
    files = mod.src_files(None)
    files[f"src/{mod.key}/index.js"] = mod.core_with(bug)
    files.update(mod.visible_files())
    return files


def js_readme(project, blurb, mods):
    rows = "\n".join(f"| `src/{m.key}` | {m.title.split(': ', 1)[1]} |" for m in mods)
    return dd(f'''
        # {project}

        {blurb[0].upper() + blurb[1:]}. Each package is a CommonJS module in `src/<name>/` with a `SPEC.md` that is its contract.

        | package | purpose |
        |---|---|
        {rows}

        Run the visible tests with `node --test test/*.test.js`. They are a sample, not the whole story: the `SPEC.md` files describe more behaviour than they exercise.
    ''')


@family("swarm-js-monorepo", category="swarm", lang="javascript", kind="fix", n=8,
        summary="a node monorepo of k small libraries with one defect each; score = fraction of packages whose hidden node:test suite passes")
def js_monorepo(rng, n):
    keys = sorted(JS_MODS)
    plan = [2, 3, 3, 4, 4, 5, 5, 3]
    styles = ["ticket", "reports", "terse", "audit"]
    for i in range(n):
        k = min(plan[i % len(plan)], len(keys))
        mods = [JS_MODS[x] for x in rng.sample(keys, k)]
        project, blurb = pick(rng, PROJECTS)
        start = {"README.md": js_readme(project, blurb, mods), "package.json": json.dumps({"name": project.lower(), "private": True, "scripts": {"test": "node --test test/*.test.js"}}, indent=2) + "\n"}
        sym, bugs, units, hidden, solution = {}, {}, [], {}, {}
        for m in mods:
            b = pick(rng, m.bugs)
            if run_hidden(m, b).ok:
                raise RuntimeError(f"{m.key}: hidden tests miss {b.key}")
            bugs[m.key] = b
            sym[m.key] = symptoms(m, b)
            start.update(js_tree(m, b))
            hidden.update(m.hidden_files())
            units.append({"name": m.key, "cmd": ["node", "--test", m.hidden_path()], "weight": 1})
            solution.update(m.solution_files())
        hidden[".grade/score.py"] = score_script(units)
        style = styles[i % len(styles)]
        if style == "ticket":
            body = "Tickets:\n\n" + enum([f"{pick(rng, ['Support', 'QA', 'Ops', 'A user'])} on `{m.key}`: {describe(sym[m.key][0], rng.randrange(3))}" for m in mods], "numbered")
            prompt = f"{project} ({blurb}) has a defect in each of these packages and I need all of them gone before the cut.\n\n{body}"
        elif style == "reports":
            body = enum([f"`{m.key}`: {describe(sym[m.key][0], rng.randrange(3))}" for m in mods])
            prompt = f"The nightly build of {project} is red. What we know so far:\n\n{body}\n\nFix the code, not the tests; each package's SPEC.md is the contract."
        elif style == "terse":
            prompt = f"Packages {oxford([m.key for m in mods])} in {project} each have a bug (see their SPEC.md). Fix them all, leave the specs alone."
        else:
            prompt = (f"An audit flagged {oxford([f'`{m.key}`' for m in mods])} in {project} as not matching their specifications, without saying how. "
                      f"Read each package's SPEC.md, find the deviations and fix the code. The visible tests are only a sample.")
        d = 2 if k <= 2 else 3 if k <= 3 else 4 if k <= 4 else 5
        yield Task(
            slug=f"{i + 1:02d}-k{k}-{style}", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution,
            verify=GRADE_CMD, pass_mode="json-score", team=team(rng, min(max(k, 2), 6)),
            tags=["monorepo", "independent-components", "node", style],
            notes={"packages": [m.key for m in mods], "bugs": {m.key: bugs[m.key].key for m in mods}},
        )
