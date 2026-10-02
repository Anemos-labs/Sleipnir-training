"""Monorepos of independent library packages, each carrying its own defect (swarm: one worker per package)."""
from __future__ import annotations

from fx import Task, dd, family, merged

from . import _bank, _mods_a  # noqa: F401  (registers the bank)
from ._bank import MODS, describe, run_hidden, run_visible, symptoms
from ._kit import GRADE_CMD, COMPANIES, enum, oxford, pick, score_script, team, unit_test

try:  # later parts of the bank are optional while it grows
    from . import _mods_b  # noqa: F401
except ImportError:  # pragma: no cover
    pass

PROJECTS = [
    ("harbourdesk", "Harbourdesk", "the harbour office's back-office libraries"),
    ("tallyroom", "Tallyroom", "a sailing club's membership and booking libraries"),
    ("islandops", "Islandops", "operations code for a small island's services"),
    ("fieldnotes", "Fieldnotes", "helper libraries for a remote field station"),
    ("counterhand", "Counterhand", "tools used at the counter of a lab reception"),
    ("quayside", "Quayside", "quay and ferry operations code"),
    ("northgate", "Northgate", "the Northgate town hall utilities"),
    ("marketbox", "Marketbox", "a market-stall cooperative's toolkit"),
    ("lanternworks", "Lantern Works", "the shared libraries of a small games and media studio"),
]


def apply_bugs(mod, bugs):
    text = mod.core
    for b in bugs:
        if text.count(b.old) != 1:
            raise ValueError(f"{mod.key}/{b.key}: pattern not unique in the current text")
        text = text.replace(b.old, b.new)
    return text


def module_tree(mod, bugs):
    files = mod.src_files(None)
    files[f"src/{mod.key}/core.py"] = apply_bugs(mod, bugs)
    return files


def compatible(mod, b1, b2) -> bool:
    return b1.where != b2.where and b1.key != b2.key and b1.old not in b2.new and b2.old not in b1.new and (b1.old not in b2.old) and (b2.old not in b1.old)


def repo_readme(project, blurb, mods, extra=""):
    rows = "\n".join(f"| `src/{m.key}` | {m.title.split(': ', 1)[1]} |" for m in mods)
    return dd(f'''
        # {project}

        {blurb[0].upper() + blurb[1:]}. Each package lives in `src/<name>/` and has a `SPEC.md` that is its contract.

        | package | purpose |
        |---|---|
        {rows}

        Run the visible checks with `python3 -m unittest discover -s tests`. They are a sample, not the whole story:
        the `SPEC.md` files describe more behaviour than the tests exercise.
    ''') + extra


def base_start(project, blurb, mods, bugmap, with_visible=True):
    files = {"README.md": repo_readme(project, blurb, mods)}
    for m in mods:
        files.update(module_tree(m, bugmap.get(m.key, [])))
        if with_visible:
            files.update(m.visible_files())
    return files


def pick_bugs(rng, mod, count, d_only_public=False):
    pool = [b for b in mod.bugs if (not d_only_public or b.where in mod.names)]
    first = pick(rng, pool)
    chosen = [first]
    if count > 1:
        others = [b for b in pool if compatible(mod, first, b)]
        if others:
            chosen.append(pick(rng, others))
    return chosen


def hidden_units(mods):
    files, units = {}, []
    for m in mods:
        files.update(m.hidden_files())
        units.append(unit_test(m.key, m.hidden_path()))
    return files, units


# ------------------------------------------------------------------------------------------------ monorepo-fixes
OPENERS = [
    "The nightly build of {proj} is red and nobody has time to chase it package by package. {blurb}.",
    "{proj} freezes for release tomorrow. QA filed these against it, one per package, and I need all of them gone before the cut. ({blurb})",
    "Support has been collecting complaints about {proj}: {blurb}. Several unrelated packages seem to have drifted from their specs.",
    "I inherited {proj} from a colleague who left; it is {blurb}. A handful of packages misbehave and each needs its own fix.",
    "Can you get {proj} back in shape? It holds {blurb}, and some packages no longer do what their SPEC.md says.",
    "I'm handing the {proj} repository ({blurb}) to a team of agents. Every package listed below has at least one defect.",
]
NO_REPRO = ["somebody noticed wrong output but we never found a repro", "reported as 'off' by a user; nobody has an example",
            "flagged in review as suspicious, no failing case on record", "a customer complained, details lost"]


def fixes_prompt(rng, style, proj, blurb, mods, bugmap, sym):
    op = pick(rng, OPENERS).format(proj=proj, blurb=blurb)
    end = pick(rng, ["", "Fix the code, not the tests.", "The SPEC.md in each package is the reference.", "Don't change any public signature.",
                     "Every package has its own hidden checks beyond the visible tests.", "Leave the specs as they are."])
    if style == "reports":
        lines = []
        for m in mods:
            s = sym[m.key]
            lines.append(f"`{m.key}`: " + "; ".join(describe(x, rng.randrange(3)) for x in s[:2]))
        return f"{op}\n\nWhat we have so far:\n\n{enum(lines)}\n\n{end}".strip()
    if style == "mixed":
        lines = []
        for i, m in enumerate(mods):
            s = sym[m.key]
            if i % 2 == 0:
                lines.append(f"`{m.key}`: " + describe(s[0], rng.randrange(3)))
            else:
                lines.append(f"`{m.key}`: " + NO_REPRO[i % len(NO_REPRO)])
        return f"{op}\n\n{enum(lines)}\n\n{end}".strip()
    if style == "audit":
        names = oxford([f"`{m.key}`" for m in mods])
        return (f"{op} An audit flagged {names} as not matching their specifications, without saying how. "
                f"Read each package's SPEC.md, find what deviates and fix it. {end}").strip()
    if style == "terse":
        return f"Packages {oxford([m.key for m in mods])} in {proj} each have a bug (see their SPEC.md). Fix them all. {end}".strip()
    # "ticket"
    lines = []
    for i, m in enumerate(mods):
        s = sym[m.key]
        who = pick(rng, ["Support", "QA", "Finance", "Ops", "A user", "The night shift"])
        lines.append(f"{who} on `{m.key}`: " + describe(s[0], rng.randrange(3)))
    return f"{op}\n\nTickets:\n\n{enum(lines, 'numbered')}\n\n{end}".strip()


@family("swarm-monorepo-fixes", category="swarm", lang="python", kind="fix", n=16,
        summary="a monorepo of k small library packages, each with a different injected defect; score = fraction of packages whose hidden suite passes")
def monorepo_fixes(rng, n):
    keys = sorted(MODS)
    plan = [(3, "ticket"), (3, "reports"), (3, "terse"), (4, "ticket"), (4, "mixed"), (4, "audit"), (4, "reports"), (5, "mixed"),
            (5, "ticket"), (5, "audit"), (5, "terse"), (6, "mixed"), (6, "audit"), (6, "reports"), (3, "audit"), (4, "terse")]
    for i in range(n):
        k, style = plan[i % len(plan)]
        k = min(k, len(keys))
        mods = [MODS[x] for x in rng.sample(keys, k)]
        double = k >= 5 and i % 2 == 0
        bugmap, sym = {}, {}
        for j, m in enumerate(mods):
            cnt = 2 if (double and j == 0) else 1
            bugmap[m.key] = pick_bugs(rng, m, cnt)
            if run_hidden(m, bugmap[m.key][0]).ok:
                raise RuntimeError(f"{m.key}: hidden tests miss {bugmap[m.key][0].key}")
            sym[m.key] = symptoms(m, bugmap[m.key][0])
        proj, disp, blurb = pick(rng, PROJECTS)
        start = base_start(disp, blurb, mods, bugmap)
        hidden, units = hidden_units(mods)
        hidden[".grade/score.py"] = score_script(units)
        solution = {}
        for m in mods:
            solution.update(m.solution_files())
        d = 3 if k <= 3 else 4 if k <= 5 else 5
        if style in ("audit", "terse") and d < 5:
            d = min(5, d + 1)
        yield Task(
            slug=f"{i + 1:02d}-k{k}-{style}" + ("-double" if double else ""),
            prompt=fixes_prompt(rng, style, disp, blurb, mods, bugmap, sym),
            difficulty=d, start=start, hidden=hidden, solution=solution,
            verify=GRADE_CMD, pass_mode="json-score",
            team=team(rng, min(k, 6)),
            tags=["monorepo", "independent-components", style],
            notes={"packages": [m.key for m in mods], "bugs": {m.key: [b.key for b in bugmap[m.key]] for m in mods}, "style": style},
        )
